// PC builder: the build is assembled step by step (CPU → motherboard → … → case).
// Each step is a card; "Choose" opens a list of parts as tiles with their main specs and a hint
// whether the part fits the parts already chosen. The panel on the right is checked by the API
// on every change. The selection is kept in localStorage, so it survives page reloads.
import { api } from "../api.js";
import { checksList, goToLogin } from "../components.js";
import { t } from "../i18n.js";
import { headerChanged } from "../router.js";
import { isLoggedIn, session } from "../session.js";
import { countTo } from "../effects.js";
import { attempt, flash, h, icon, image, link, money, navigate } from "../ui.js";

const SLOTS = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case"];
const MULTIPLE = ["ram", "storage"]; // several pieces allowed
const OPTIONAL = ["gpu"]; // the build can work without it (graphics in the CPU)
const STORAGE_KEY = "builder";

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
    motherboard: [s.socket, s.ram_type, s.form_factor],
    ram: [s.ram_type, s.sticks && s.size_gb && t("builder.spec.sticks", { sticks: s.sticks, size: s.size_gb / s.sticks })],
    gpu: [s.vram_gb && gb(s.vram_gb), s.length_mm && t("builder.spec.mm", { mm: s.length_mm }), s.tdp && t("builder.spec.watts", { watts: s.tdp })],
    storage: [s.type, s.size_gb && gb(s.size_gb)],
    psu: [s.wattage && t("builder.spec.watts", { watts: s.wattage })],
    case: [...(s.form_factors || []), s.max_gpu_mm && t("builder.spec.gpu_up_to", { mm: s.max_gpu_mm })],
  }[product.category] || [];
  return h("div", { class: "spec-chips" }, chips.filter(Boolean).map((text) => h("span", {}, text)));
}

export async function builderPage() {
  const lists = await Promise.all(SLOTS.map((slot) => api(`/api/products?category=${slot}&limit=100&sort=price_asc`)));
  const bySlot = Object.fromEntries(SLOTS.map((slot, i) => [slot, lists[i].items]));
  const products = new Map(lists.flatMap((list) => list.items).map((p) => [p.id, p]));

  let selection = loadSelection().filter((id) => products.has(id)); // drop hidden products
  let picker = null; // {slot, index}: which step has its list open; index = which piece is replaced
  let lastCheck = null; // last API answer, used for the PSU hint
  let shown = { total: 0, score: 0, cpu: 0, gpu: 0, load: 0 }; // numbers on the panel now: the next ones animate from them

  const track = h("ol", { class: "build-track" });
  const stepsBox = h("div", { class: "build-steps" });
  const panel = h("aside", { class: "build-summary" });

  const idsOf = (slot) => selection.filter((id) => products.get(id).category === slot);
  const first = (slot) => products.get(idsOf(slot)[0]);

  /** Does a part fit the parts already chosen in other steps? null = nothing to compare with yet. */
  function fit(product) {
    const s = product.specs || {};
    const cpu = first("cpu")?.specs;
    const mb = first("motherboard")?.specs;
    const gpu = first("gpu")?.specs;
    const box = first("case")?.specs;
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

  function choose(slot, index, id) {
    const ids = idsOf(slot);
    const wasEmpty = ids.length === 0;
    ids[index] = id;
    setSlot(slot, ids);
    picker = null;
    // a step is done: open the next empty one, so the build goes on by itself
    if (wasEmpty && !MULTIPLE.includes(slot)) {
      const next = SLOTS.find((s, i) => i > SLOTS.indexOf(slot) && idsOf(s).length === 0 && !OPTIONAL.includes(s));
      if (next) picker = { slot: next, index: 0 };
    }
    draw(picker?.slot);
  }

  function remove(slot, index) {
    const ids = idsOf(slot);
    ids.splice(index, 1);
    setSlot(slot, ids);
    draw();
  }

  function togglePicker(slot, index) {
    picker = picker && picker.slot === slot && picker.index === index ? null : { slot, index };
    draw();
  }

  /** The progress line on top: one node per step, filled steps are colored. */
  function drawTrack() {
    const done = SLOTS.filter((slot) => idsOf(slot).length).length;
    track.replaceChildren(...SLOTS.map((slot, i) => h(
      "li",
      { class: idsOf(slot).length ? "done" : picker?.slot === slot ? "current" : "" },
      h(
        "a",
        { href: `#step-${slot}`, onclick: (event) => {
          event.preventDefault(); // the address is the router's: just scroll
          document.getElementById(`step-${slot}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        } },
        h("span", { class: "node" }, icon(`categories/${slot}`)),
        h("span", { class: "node-label" }, `${i + 1}. ${t(`categories.${slot}`)}`),
      ),
    )));
    track.style.setProperty("--progress", String(done / SLOTS.length));
    track.dataset.done = t("builder.progress", { done, total: SLOTS.length });
  }

  function partRow(slot, product, index) {
    return h(
      "div",
      { class: "chosen-part" },
      h("span", { class: "part-thumb" }, image(product.image_url, "") || icon(`categories/${slot}`)),
      h(
        "div",
        { class: "part-info" },
        link(`/product/${product.id}`, product.name),
        specChips(product),
      ),
      h("span", { class: "price" }, money(product.price)),
      h(
        "div",
        { class: "part-actions" },
        h("button", { type: "button", class: "ghost", onclick: () => togglePicker(slot, index) }, icon("actions/edit"), t("builder.change")),
        h("button", { type: "button", class: "ghost icon-only", "aria-label": t("builder.remove"), title: t("builder.remove"), onclick: () => remove(slot, index) }, icon("actions/close")),
      ),
    );
  }

  /** The list of parts for a step: search + tiles, the parts that fit go first. */
  function pickerBox(slot, index) {
    const currentId = idsOf(slot)[index];
    const items = bySlot[slot]
      .map((product) => ({ product, fit: fit(product) }))
      .sort((a, b) => Number(a.fit?.ok === false) - Number(b.fit?.ok === false));
    const tiles = items.map(({ product, fit: match }) => {
      const out = product.stock <= 0;
      const tile = h(
        "button",
        {
          type: "button",
          class: `option-tile${product.id === currentId ? " selected" : ""}${match?.ok === false ? " misfit" : ""}`,
          disabled: out,
          onclick: () => choose(slot, index, product.id),
        },
        h("span", { class: "option-name" }, product.name),
        specChips(product),
        h(
          "span",
          { class: "option-foot" },
          h("span", { class: "price" }, money(product.price)),
          out
            ? h("span", { class: "fit muted" }, t("product.out_of_stock"))
            : match
              ? h("span", { class: `fit ${match.ok ? "ok" : "error"}` }, icon(match.ok ? "feedback/success" : "feedback/warning"),
                  match.ok ? t("builder.fit_ok") : t("builder.fit_bad", { reason: match.reason }))
              : "",
        ),
      );
      tile.dataset.name = product.name.toLowerCase();
      return tile;
    });
    const grid = h("div", { class: "option-grid" }, tiles);
    const search = h("input", {
      type: "search",
      placeholder: t("builder.search_in_list"),
      "aria-label": t("builder.search_in_list"),
      oninput: () => {
        const text = search.value.trim().toLowerCase();
        for (const tile of tiles) tile.hidden = !tile.dataset.name.includes(text);
      },
    });
    return h(
      "div",
      { class: "picker" },
      h("div", { class: "picker-head" }, h("label", { class: "filter-search" }, icon("actions/search"), search),
        h("button", { type: "button", class: "ghost", onclick: () => togglePicker(slot, index) }, t("builder.close_list"))),
      grid,
    );
  }

  function drawSteps() {
    stepsBox.replaceChildren(...SLOTS.map((slot, i) => {
      const ids = idsOf(slot);
      const open = picker?.slot === slot;
      const sum = ids.reduce((total, id) => total + products.get(id).price, 0);
      return h(
        "section",
        { class: `build-step${ids.length ? " done" : ""}${open ? " open" : ""}`, id: `step-${slot}` },
        h(
          "header",
          { class: "step-head" },
          h("span", { class: "step-number" }, ids.length ? icon("actions/check") : String(i + 1)),
          h(
            "div",
            { class: "step-title" },
            h("h3", {}, t(`categories.${slot}`), OPTIONAL.includes(slot) ? h("span", { class: "optional" }, t("builder.optional")) : null),
            h("p", { class: "muted" }, t(`builder.hints.${slot}`)),
          ),
          ids.length ? h("span", { class: "step-sum price" }, money(sum)) : null,
        ),
        ids.map((id, index) => [
          partRow(slot, products.get(id), index),
          open && picker.index === index ? pickerBox(slot, index) : null,
        ]),
        ids.length === 0
          ? open
            ? pickerBox(slot, 0)
            : h("button", { type: "button", class: "choose-part", onclick: () => togglePicker(slot, 0) }, icon("actions/plus"), t("builder.choose"))
          : MULTIPLE.includes(slot)
            ? open && picker.index === ids.length
              ? pickerBox(slot, ids.length)
              : h("button", { type: "button", class: "choose-part small", onclick: () => togglePicker(slot, ids.length) }, icon("actions/plus"), t("builder.add_more"))
            : null,
      );
    }));
  }

  let checkCounter = 0;
  async function drawPanel() {
    const current = ++checkCounter;
    const check = await attempt(() => api("/api/builder/check", { method: "POST", body: { product_ids: selection } }), panel);
    if (!check || current !== checkCounter) return;
    const firstCheck = lastCheck === null;
    lastCheck = check;
    if (firstCheck && picker?.slot === "psu") drawSteps(); // PSU hints need the recommended wattage

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
            check.is_compatible ? t("builder.compatible") : t("builder.incompatible"))
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
            h("button", { type: "button", class: "ghost", onclick: () => { selection = []; picker = null; saveSelection(selection); draw(); } },
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

  function draw(scrollTo = null) {
    drawTrack();
    drawSteps();
    drawPanel();
    if (scrollTo) requestAnimationFrame(() => document.getElementById(`step-${scrollTo}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }

  draw();
  return h(
    "div",
    { class: "builder" },
    h("div", { class: "section-head" }, h("h1", {}, t("builder.title")), h("p", { class: "muted" }, t("builder.subtitle"))),
    track,
    h("div", { class: "builder-layout" }, stepsBox, panel),
  );
}
