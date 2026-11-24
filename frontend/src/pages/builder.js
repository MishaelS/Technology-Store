// PC builder: pick a part for each slot, the panel on the right is checked by the API on every change.
// The selection is kept in localStorage, so it survives page reloads.
import { api } from "../api.js";
import { checksList, goToLogin } from "../components.js";
import { t } from "../i18n.js";
import { headerChanged } from "../router.js";
import { isLoggedIn, session } from "../session.js";
import { attempt, flash, h, link, money, navigate } from "../ui.js";

const SLOTS = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case"];
const MULTIPLE = ["ram", "storage"]; // several pieces allowed
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

/** Used by "Open in builder" in the account. */
export function openInBuilder(ids) {
  saveSelection(ids);
  navigate("/builder");
}

export async function builderPage() {
  const lists = await Promise.all(SLOTS.map((slot) => api(`/api/products?category=${slot}&limit=100&sort=price_asc`)));
  const bySlot = Object.fromEntries(SLOTS.map((slot, i) => [slot, lists[i].items]));
  const products = new Map(lists.flatMap((list) => list.items).map((p) => [p.id, p]));

  let selection = loadSelection().filter((id) => products.has(id)); // drop hidden products
  const slotsBox = h("div");
  const panel = h("div", { class: "sidebar" });

  const idsOf = (slot) => selection.filter((id) => products.get(id).category === slot);

  function setSlot(slot, ids) {
    selection = [...selection.filter((id) => products.get(id).category !== slot), ...ids];
    saveSelection(selection);
    draw();
  }

  function slotSelect(slot, value, onChange) {
    const select = h(
      "select",
      { onchange: (e) => onChange(e.target.value ? Number(e.target.value) : null) },
      h("option", { value: "" }, t("builder.not_selected")),
      bySlot[slot].map((p) =>
        h("option", { value: p.id, selected: p.id === value, disabled: p.stock <= 0 }, `${p.name} — ${money(p.price)}`)),
    );
    return select;
  }

  function drawSlots() {
    slotsBox.replaceChildren(...SLOTS.map((slot) => {
      const ids = idsOf(slot);
      const rows = (ids.length ? ids : [null]).map((id, index) => h(
        "div",
        { class: "row" },
        slotSelect(slot, id, (newId) => {
          const next = [...ids];
          if (newId === null) next.splice(index, 1);
          else next[index] = newId;
          setSlot(slot, next);
        }),
        id ? link(`/product/${id}`, "↗") : null,
      ));
      return h(
        "section",
        {},
        h("h3", {}, t(`categories.${slot}`)),
        rows,
        MULTIPLE.includes(slot) && ids.length
          ? h("button", { onclick: () => setSlot(slot, [...ids, ids[ids.length - 1]]) }, t("builder.add_more"))
          : null,
      );
    }));
  }

  let checkCounter = 0;
  async function drawPanel() {
    const current = ++checkCounter;
    const check = await attempt(() => api("/api/builder/check", { method: "POST", body: { product_ids: selection } }), panel);
    if (!check || current !== checkCounter) return;

    const nameInput = h("input", { placeholder: t("builder.build_name"), required: true, maxLength: 100 });
    const saveErrors = h("div");
    panel.replaceChildren(
      h("h2", {}, money(check.total_price)),
      h("p", {}, h("b", {}, check.tier_name)),
      h("p", {}, t("builder.score", { score: check.score })),
      h("progress", { max: 100, value: check.score }),
      h("p", {}, t("builder.power_draw", { watts: check.power_draw }), h("br"), t("builder.recommended_psu", { watts: check.recommended_psu })),
      h("p", { class: check.is_compatible ? "ok" : "error" }, check.is_compatible ? t("builder.compatible") : t("builder.incompatible")),
      h("h3", {}, t("builder.checks_title")),
      checksList(check.checks),
      selection.length
        ? h(
            "div",
            {},
            h("button", { onclick: addAllToCart }, t("builder.add_all_to_cart")),
            isLoggedIn()
              ? h(
                  "form",
                  {
                    class: "row",
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
                  h("button", {}, t("builder.save")),
                )
              : h("p", { class: "muted" }, link(`/login?next=${encodeURIComponent("/builder")}`, t("builder.login_to_save"))),
            saveErrors,
            h("button", { onclick: () => { selection = []; saveSelection(selection); draw(); } }, t("builder.clear")),
          )
        : null,
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
    drawSlots();
    drawPanel();
  }

  draw();
  return h("div", {}, h("h1", {}, t("builder.title")), h("div", { class: "columns" }, slotsBox, panel));
}
