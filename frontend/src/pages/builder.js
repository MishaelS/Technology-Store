// PC builder: a 3D case in the middle (pc-case.js), the sections of parts under it in the order of a real
// assembly (motherboard → CPU → cooler → RAM → PSU → GPU → drives → case). A click on a section opens a strip
// of its parts right under it; the chosen part flies into the case. The panel on the right is checked by
// the API on every change. The selection is kept in localStorage, so it survives page reloads.
import { api } from "../api.js";
import { cautionTape, checksList, goToLogin } from "../components.js";
import { t } from "../i18n.js";
import { headerChanged } from "../router.js";
import { isLoggedIn, session } from "../session.js";
import { countTo } from "../effects.js";
import { attempt, flash, h, icon, image, link, money, navigate } from "../ui.js";

const SLOTS = ["motherboard", "cpu", "cooler", "ram", "psu", "gpu", "storage", "case"];
const MULTIPLE = ["ram", "storage"]; // several pieces allowed
const OPTIONAL = ["gpu"]; // the build can work without it (graphics in the CPU)
const STORAGE_KEY = "builder";
// which sections a failed check points at (codes: services/compatibility.py)
const CHECK_SLOTS = {
  socket: ["cpu", "motherboard"], cooler: ["cooler"], ram_type: ["ram"], ram_slots: ["ram"], psu: ["psu"],
  gpu_length: ["gpu", "case"], form_factor: ["motherboard", "case"], graphics: ["gpu"],
  cooler_height: ["cooler", "case"], radiator: ["cooler", "case"],
};

function loadSelection() {
  try {
    const ids = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(ids) ? ids.filter(Number.isInteger) : [];
  } catch {
    return [];
  }
}

function saveSelection(ids) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* storage blocked: the build just isn't remembered */
  }
}

/** Used by "Open in builder" in the account. */
export function openInBuilder(ids) {
  saveSelection(ids);
  navigate("/builder");
}

/** Short spec chips of a part: what matters for choosing and for compatibility. */
function specChips(product) {
  const s = product.specs || {};
  const gb = (size) => (size >= 1000 ? t("builder.spec.tb", { size: size / 1000 }) : t("builder.spec.gb", { size }));
  const chips = {
    cpu: [s.socket, s.cores && t("builder.spec.cores", { count: s.cores }), s.tdp && t("builder.spec.watts", { watts: s.tdp })],
    cooler: [s.type, s.radiator_mm && t("builder.spec.mm", { mm: s.radiator_mm }), s.tdp && t("builder.spec.cools", { watts: s.tdp })],
    motherboard: [s.socket, s.ram_type, s.form_factor],
    ram: [s.ram_type, s.sticks && s.size_gb && t("builder.spec.sticks", { sticks: s.sticks, size: s.size_gb / s.sticks })],
    gpu: [s.vram_gb && gb(s.vram_gb), s.length_mm && t("builder.spec.mm", { mm: s.length_mm }), s.tdp && t("builder.spec.watts", { watts: s.tdp })],
    storage: [s.type, s.size_gb && gb(s.size_gb)],
    psu: [s.wattage && t("builder.spec.watts", { watts: s.wattage })],
    case: [...(s.form_factors || []), s.max_gpu_mm && t("builder.spec.gpu_up_to", { mm: s.max_gpu_mm }),
      s.max_cooler_mm && t("builder.spec.cooler_up_to", { mm: s.max_cooler_mm }), s.color],
  }[product.category] || [];
  return h("div", { class: "spec-chips" }, chips.filter(Boolean).map((text) => h("span", {}, text)));
}

export async function builderPage() {
  const lists = await Promise.all(SLOTS.map((slot) => api(`/api/products?category=${slot}&limit=100&sort=price_asc`)));
  const bySlot = Object.fromEntries(SLOTS.map((slot, i) => [slot, lists[i].items]));
  const products = new Map(lists.flatMap((list) => list.items).map((p) => [p.id, p]));

  let selection = loadSelection().filter((id) => products.has(id)); // drop hidden products
  let open = null; // the section whose parts are shown under the case
  let lastCheck = null; // last API answer: PSU hint, problems, "powered on"
  let shown = { total: 0, score: 0, cpu: 0, gpu: 0, load: 0 }; // numbers on the panel now: the next ones animate from them

  const idsOf = (slot) => selection.filter((id) => products.get(id).category === slot);
  const first = (slot) => products.get(idsOf(slot)[0]);
  open = SLOTS.find((slot) => idsOf(slot).length === 0 && !OPTIONAL.includes(slot)) || null;

  const sectionsBox = h("nav", { class: "part-sections", "aria-label": t("builder.title") });
  const pickerBox = h("section", { class: "part-picker" });
  const panel = h("aside", { class: "build-summary" });
  const stageBadge = h("div", { class: "stage-badge", hidden: true });
  const stageBox = h("div", { class: "case-stage-box" }, h("div", { class: "case-stage loading" }));

  // the 3D view loads on its own: the page works (and can be used) before it is there
  let view = null;
  import("../pc-case.js").then(({ createCaseView }) => {
    view = createCaseView({
      onPick: (slot) => openSection(slot, true),
      loadingText: (percent) => (percent === null ? t("builder.loading_3d_plain") : t("builder.loading_3d", { percent })),
      failedText: t("builder.no_3d"),
      hintText: t("builder.case_hint"),
    });
    stageBox.replaceChildren(view.node, stageBadge);
    view.highlight(open);
    drawCase();
  }, () => stageBox.replaceChildren(h("div", { class: "case-stage failed" }, h("div", { class: "case-status" }, t("builder.no_3d")))));

  function problemSlots() {
    const result = new Set();
    for (const check of lastCheck?.checks || []) {
      if (check.status !== "error") continue;
      const slots = CHECK_SLOTS[check.code] || (check.code.startsWith("single_") ? [check.code.slice(7)] : []);
      for (const slot of slots) result.add(slot);
    }
    return result;
  }

  function drawCase() {
    if (!view) return;
    view.update({
      case: first("case") || null, motherboard: first("motherboard") || null, cpu: first("cpu") || null,
      cooler: first("cooler") || null, gpu: first("gpu") || null, psu: first("psu") || null,
      ram: idsOf("ram").map((id) => products.get(id)), storage: idsOf("storage").map((id) => products.get(id)),
      powered: Boolean(lastCheck && selection.length && lastCheck.is_complete && lastCheck.is_compatible),
      problems: problemSlots(),
    });
  }

  /** Does a part fit the parts already chosen in other sections? null = nothing to compare with yet. */
  function fit(product) {
    const s = product.specs || {};
    const cpu = first("cpu")?.specs;
    const mb = first("motherboard")?.specs;
    const gpu = first("gpu")?.specs;
    const box = first("case")?.specs;
    const cooler = first("cooler")?.specs;
    const problems = [];
    let compared = false;
    const need = (known, ok, reason) => {
      if (!known) return;
      compared = true;
      if (!ok) problems.push(reason);
    };
    switch (product.category) {
      case "cpu":
        need(mb, mb?.socket === s.socket, s.socket);
        need(cooler, cooler?.sockets?.includes(s.socket), s.socket);
        break;
      case "cooler":
        need(cpu, s.sockets?.includes(cpu?.socket), cpu?.socket);
        need(cpu, s.tdp >= (cpu?.tdp || 0), t("builder.spec.cools", { watts: s.tdp }));
        // in the chosen case: the tower's height or the radiator's size (when both are known)
        if (s.type === "СЖО") need(box?.max_radiator_mm && s.radiator_mm, s.radiator_mm <= box?.max_radiator_mm, t("builder.spec.mm", { mm: s.radiator_mm }));
        else need(box?.max_cooler_mm && s.height_mm, s.height_mm <= box?.max_cooler_mm, t("builder.spec.mm", { mm: s.height_mm }));
        break;
      case "motherboard":
        need(cpu, cpu?.socket === s.socket, s.socket);
        need(idsOf("ram").length, idsOf("ram").every((id) => products.get(id).specs.ram_type === s.ram_type), s.ram_type);
        need(box, box?.form_factors?.includes(s.form_factor), s.form_factor);
        break;
      case "ram":
        need(mb, mb?.ram_type === s.ram_type, s.ram_type);
        break;
      case "gpu":
        need(box, s.length_mm <= box?.max_gpu_mm, t("builder.spec.mm", { mm: s.length_mm }));
        break;
      case "case":
        need(mb, s.form_factors?.includes(mb?.form_factor), mb?.form_factor);
        if (cooler?.type === "СЖО") need(cooler.radiator_mm && s.max_radiator_mm, cooler.radiator_mm <= s.max_radiator_mm, t("builder.spec.mm", { mm: cooler.radiator_mm }));
        else need(cooler?.height_mm && s.max_cooler_mm, cooler?.height_mm <= s.max_cooler_mm, t("builder.spec.cooler_up_to", { mm: s.max_cooler_mm }));
        need(gpu, gpu?.length_mm <= s.max_gpu_mm, t("builder.spec.gpu_up_to", { mm: s.max_gpu_mm }));
        break;
      case "psu":
        need(lastCheck && selection.some((id) => ["cpu", "gpu"].includes(products.get(id).category)),
          s.wattage >= (lastCheck?.recommended_psu || 0), t("builder.spec.watts", { watts: s.wattage }));
        break;
    }
    if (!compared) return null;
    return { ok: problems.length === 0, reason: problems.join(", ") };
  }

  function setSlot(slot, ids) {
    selection = [...selection.filter((id) => products.get(id).category !== slot), ...ids];
    saveSelection(selection);
  }

  function choose(slot, id) {
    const ids = idsOf(slot);
    const wasEmpty = ids.length === 0;
    if (MULTIPLE.includes(slot)) ids.push(id);
    else if (ids[0] === id) return;
    else ids.splice(0, ids.length, id);
    setSlot(slot, ids);
    showCase();
    // a section is done: the next empty one opens, so the build goes on by itself
    if (wasEmpty && !MULTIPLE.includes(slot)) {
      const next = SLOTS.find((s, i) => i > SLOTS.indexOf(slot) && idsOf(s).length === 0 && !OPTIONAL.includes(s));
      if (next) open = next;
    }
    draw();
  }

  /** The case scrolled away (the list of parts is long): bring it back, so the part is seen flying in. */
  function showCase() {
    const rect = stageBox.getBoundingClientRect();
    if (rect.bottom < innerHeight * 0.45 || rect.top > innerHeight * 0.6) {
      scrollBy({ top: rect.top - 90, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  }

  function remove(slot, index) {
    const ids = idsOf(slot);
    ids.splice(index, 1);
    setSlot(slot, ids);
    draw();
  }

  function openSection(slot, scroll = false) {
    open = open === slot && !scroll ? null : slot;
    draw();
    if (scroll) requestAnimationFrame(() => pickerBox.scrollIntoView({ behavior: "smooth", block: "nearest" }));
    else if (open) requestAnimationFrame(() => {
      // the list of the open section in sight (its top), the case stays where it is
      const top = pickerBox.getBoundingClientRect().top;
      if (top > innerHeight * 0.75) pickerBox.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function drawSections() {
    const problems = problemSlots();
    const done = SLOTS.filter((slot) => idsOf(slot).length).length;
    sectionsBox.dataset.done = t("builder.progress", { done, total: SLOTS.length });
    sectionsBox.replaceChildren(...SLOTS.map((slot, i) => {
      const ids = idsOf(slot);
      const chosen = ids.map((id) => products.get(id));
      const sum = chosen.reduce((total, p) => total + p.price, 0);
      const button = h(
        "button",
        {
          type: "button",
          class: `part-section${ids.length ? " done" : ""}${open === slot ? " open" : ""}${problems.has(slot) ? " problem" : ""}`,
          "aria-expanded": String(open === slot),
          onclick: () => openSection(slot),
          onpointerenter: () => view?.highlight(slot),
          onpointerleave: () => view?.highlight(open),
        },
        h("span", { class: "section-icon" }, icon(`categories/${slot}`), h("span", { class: "section-step" }, ids.length ? icon("actions/check") : String(i + 1))),
        h("span", { class: "section-name" }, t(`categories.${slot}`)),
        h("span", { class: "section-choice" }, chosen.length
          ? chosen.length > 1 ? t("builder.pieces", { count: chosen.length }) : chosen[0].name
          : OPTIONAL.includes(slot) ? t("builder.optional") : t("builder.not_selected_short")),
        ids.length ? h("span", { class: "section-price price" }, money(sum)) : null,
      );
      return button;
    }));
  }

  function optionTile(slot, product, chosenIds) {
    const match = fit(product);
    const out = product.stock <= 0;
    const selected = chosenIds.includes(product.id);
    const tile = h(
      "button",
      {
        type: "button",
        class: `option-tile${selected ? " selected" : ""}${match?.ok === false ? " misfit" : ""}${out ? " is-out" : ""}`,
        disabled: out,
        onclick: () => choose(slot, product.id),
      },
      h("span", { class: "option-thumb" }, image(product.image_url, "")),
      h("span", { class: "option-name" }, product.name),
      specChips(product),
      h(
        "span",
        { class: "option-foot" },
        h("span", { class: "price" }, money(product.price)),
        out
          ? h("span", { class: "fit muted" }, t("product.out_of_stock"))
          : selected && !MULTIPLE.includes(slot)
            ? h("span", { class: "fit ok" }, icon("actions/check"), t("builder.in_case"))
            : match
              ? h("span", { class: `fit ${match.ok ? "ok" : "error"}` }, icon(match.ok ? "feedback/success" : "feedback/warning"),
                  match.ok ? t("builder.fit_ok") : t("builder.fit_bad", { reason: match.reason }))
              : "",
      ),
      out ? cautionTape() : null, // the same barrier tape as on the catalog card
    );
    tile.dataset.name = product.name.toLowerCase();
    return tile;
  }

  /** The strip of parts of the open section: the chosen pieces, search, the parts that fit first. */
  function drawPicker() {
    if (!open) {
      pickerBox.hidden = true;
      return;
    }
    pickerBox.hidden = false;
    const slot = open;
    const ids = idsOf(slot);
    const items = bySlot[slot]
      .map((product) => ({ product, match: fit(product) }))
      .sort((a, b) => Number(a.match?.ok === false) - Number(b.match?.ok === false) || Number(a.product.stock <= 0) - Number(b.product.stock <= 0));
    const tiles = items.map(({ product }) => optionTile(slot, product, ids));
    const strip = h("div", { class: "option-strip" }, tiles);
    const search = h("input", {
      type: "search",
      placeholder: t("builder.search_in_list"),
      "aria-label": t("builder.search_in_list"),
      oninput: () => {
        const text = search.value.trim().toLowerCase();
        for (const tile of tiles) tile.hidden = !tile.dataset.name.includes(text);
      },
    });
    const scrollBy = (direction) => strip.scrollBy({ left: direction * strip.clientWidth * 0.8, behavior: "smooth" });
    pickerBox.replaceChildren(
      h(
        "header",
        { class: "picker-head" },
        h("div", { class: "picker-title" },
          h("h2", {}, icon(`categories/${slot}`), t(`categories.${slot}`), OPTIONAL.includes(slot) ? h("span", { class: "optional" }, t("builder.optional")) : null),
          h("p", { class: "muted" }, t(`builder.hints.${slot}`))),
        h("label", { class: "filter-search" }, icon("actions/search"), search),
        h("div", { class: "strip-arrows" },
          h("button", { type: "button", class: "ghost icon-only", "aria-label": "←", onclick: () => scrollBy(-1) }, icon("navigation/arrow-left")),
          h("button", { type: "button", class: "ghost icon-only", "aria-label": "→", onclick: () => scrollBy(1) }, icon("navigation/arrow-right"))),
      ),
      ids.length
        ? h("div", { class: "chosen-chips" }, ids.map((id, index) => {
            const product = products.get(id);
            return h("span", { class: "chosen-chip" },
              link(`/product/${product.id}`, product.name), h("span", { class: "price" }, money(product.price)),
              h("button", { type: "button", class: "ghost icon-only", "aria-label": t("builder.remove"), title: t("builder.remove"), onclick: () => remove(slot, index) }, icon("actions/close")));
          }), MULTIPLE.includes(slot) ? h("span", { class: "muted chosen-more" }, t("builder.add_more_hint")) : null)
        : null,
      strip,
    );
    // the chosen part in view, the strip remembers nothing else
    const selected = strip.querySelector(".option-tile.selected");
    if (selected) requestAnimationFrame(() => { strip.scrollLeft = selected.offsetLeft - strip.clientWidth / 2 + selected.clientWidth / 2; });
  }

  let checkCounter = 0;
  async function drawPanel() {
    const current = ++checkCounter;
    const check = await attempt(() => api("/api/builder/check", { method: "POST", body: { product_ids: selection } }), panel);
    if (!check || current !== checkCounter) return;
    const firstCheck = lastCheck === null;
    lastCheck = check;
    drawCase(); // problems and "powered on" come from the check
    drawSections();
    if (firstCheck && open === "psu") drawPicker(); // PSU hints need the recommended wattage

    // the price and the verdict stay in sight on the case while the parts are chosen
    stageBadge.hidden = !selection.length;
    stageBadge.className = `stage-badge ${check.is_compatible ? "ok" : "error"}`;
    stageBadge.replaceChildren(
      h("b", { class: "price" }, money(check.total_price)),
      h("span", {}, icon(check.is_compatible ? "feedback/success" : "feedback/error"),
        check.is_compatible ? (check.is_complete ? t("builder.powered_short") : t("builder.compatible")) : t("builder.incompatible")),
    );

    const psu = first("psu");
    const load = psu ? Math.min(1, check.power_draw / psu.specs.wattage) : 0;
    // the panel is drawn with the old values, then moves to the new ones: bars grow, numbers count
    const before = shown;
    shown = { total: check.total_price, score: check.score, cpu: check.cpu_score, gpu: check.gpu_score, load };
    const fills = [];
    const fill = (from, to) => {
      const node = h("span", { style: `--value: ${from}` });
      fills.push([node, to]);
      return node;
    };
    const bar = (label, from, value) => {
      const number = h("b", { class: "num" });
      countTo(number, from, value);
      return h("div", { class: "meter" }, h("span", {}, label), h("span", { class: "meter-track" }, fill(from / 100, value / 100)), number);
    };
    const total = h("strong", { class: "total price" });
    countTo(total, before.total, check.total_price, money);
    const scoreText = h("b");
    countTo(scoreText, before.score, check.score);
    const ring = h("div", { class: "score-ring", style: `--score: ${before.score}`, role: "img", "aria-label": t("builder.score", { score: check.score }) },
      scoreText, h("small", {}, "/100"));
    requestAnimationFrame(() => requestAnimationFrame(() => {
      ring.style.setProperty("--score", String(check.score));
      for (const [node, value] of fills) node.style.setProperty("--value", String(value));
    }));

    const nameInput = h("input", { placeholder: t("builder.build_name"), "aria-label": t("builder.build_name"), required: true, maxLength: 100 });
    const saveErrors = h("div");
    panel.replaceChildren(
      h(
        "div",
        { class: "summary-top" },
        ring,
        h("div", {}, h("span", { class: "muted" }, t("builder.total_price")), total,
          h("span", { class: "tier" }, check.tier_name)),
      ),
      h("div", { class: "meters" }, bar(t("builder.cpu_score"), before.cpu, check.cpu_score), bar(t("builder.gpu_score"), before.gpu, check.gpu_score)),
      h(
        "div",
        { class: `power${load > 0.9 ? " high" : ""}` },
        h("div", { class: "power-head" }, icon("shop/power"), h("span", {}, t("builder.power_title")),
          h("b", { class: "num" }, psu ? t("builder.psu_load", { draw: check.power_draw, psu: psu.specs.wattage }) : t("builder.spec.watts", { watts: check.power_draw }))),
        h("span", { class: "meter-track" }, fill(before.load, load)),
        h("small", { class: "muted" }, t("builder.recommended_psu", { watts: check.recommended_psu })),
      ),
      selection.length // an empty build is not "compatible" yet
        ? h("p", { class: `verdict ${check.is_compatible ? "ok" : "error"}` }, icon(check.is_compatible ? "feedback/success" : "feedback/error"),
            check.is_compatible ? (check.is_complete ? t("builder.powered") : t("builder.compatible")) : t("builder.incompatible"))
        : "",
      h("details", { class: "checks-box", open: !check.is_compatible }, h("summary", {}, t("builder.checks_title")), checksList(check.checks)),
      selection.length
        ? h(
            "div",
            { class: "summary-actions" },
            h("button", { type: "button", class: "primary big", onclick: addAllToCart }, icon("navigation/cart"), t("builder.add_all_to_cart")),
            isLoggedIn()
              ? h(
                  "form",
                  {
                    class: "save-build",
                    onsubmit: async (event) => {
                      event.preventDefault();
                      const build = await attempt(
                        () => api("/api/builds", { method: "POST", body: { name: nameInput.value, product_ids: selection } }),
                        saveErrors,
                      );
                      if (build) {
                        saveErrors.replaceChildren();
                        flash(t("builder.saved"));
                      }
                    },
                  },
                  nameInput,
                  h("button", { type: "submit", class: "btn" }, icon("actions/save"), t("builder.save")),
                )
              : h("p", { class: "muted" }, link(`/login?next=${encodeURIComponent("/builder")}`, t("builder.login_to_save"))),
            saveErrors,
            h("button", { type: "button", class: "ghost", onclick: () => { selection = []; open = SLOTS[0]; saveSelection(selection); draw(); } },
              icon("actions/reset"), t("builder.clear")),
          )
        : h("p", { class: "muted" }, t("builder.start_hint")),
    );
  }

  async function addAllToCart() {
    if (!isLoggedIn()) return goToLogin();
    const cart = await attempt(() => api("/api/cart/add-many", { method: "POST", body: { product_ids: selection } }));
    if (cart) {
      session.cartCount = cart.count;
      headerChanged();
      flash(t("builder.added_to_cart"));
    }
  }

  function draw() {
    drawSections();
    drawPicker();
    drawCase();
    view?.highlight(open);
    drawPanel();
  }

  draw();
  return h(
    "div",
    { class: "builder" },
    h("div", { class: "section-head" }, h("h1", {}, t("builder.title")), h("p", { class: "muted" }, t("builder.subtitle"))),
    // the case stays on the screen (sticky) while the column on the right is scrolled: sections, parts, summary
    h("div", { class: "builder-top" }, stageBox, h("div", { class: "builder-side" }, sectionsBox, pickerBox, panel)),
  );
}
