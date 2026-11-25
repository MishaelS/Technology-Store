// Catalog: filters in the address (#/catalog?category=gpu&sort=price_asc) + infinite scroll.
// Filters live in a sticky panel on the left, grouped into sections with icons.
// When the user opens a product and presses "Back", the list and scroll position are restored.
import { api, query as toQuery } from "../api.js";
import { productCard } from "../components.js";
import { t } from "../i18n.js";
import { infiniteList, toTopButton } from "../infinite.js";
import { afterRender, onLeave } from "../router.js";
import { formData, h, icon, link, navigate, select, skeletons } from "../ui.js";

// sort value -> icon
const SORTS = [
  ["new", "content/calendar"],
  ["price_asc", "navigation/arrow-up"],
  ["price_desc", "navigation/arrow-up", "flip"],
  ["name", "admin/content"],
];
let saved = null; // {key, state, scrollY} of the last visited catalog list

/** One row of a choice list: a hidden radio + icon + text. */
function option(name, value, checked, iconName, text, iconClass = "") {
  return h(
    "label",
    { class: "filter-option" },
    h("input", { type: "radio", name, value, checked }),
    h("span", { class: iconClass }, icon(iconName)),
    h("span", { class: "filter-text" }, text),
  );
}

// What the user collapsed: kept in the browser, so the panel looks the same next time.
const UI_KEY = "catalogFilters";
function loadUi() {
  try {
    return JSON.parse(localStorage.getItem(UI_KEY)) || {};
  } catch {
    return {};
  }
}
function saveUi(ui) {
  try {
    localStorage.setItem(UI_KEY, JSON.stringify(ui));
  } catch {
    /* storage can be blocked: collapsing still works, it just isn't remembered */
  }
}

/** A collapsible section of the panel. `rowClass` "scroll-row": on phones the options become a row of chips. */
function filterSection(ui, id, iconName, title, content, rowClass = "") {
  const closed = (ui.closed || []).includes(id);
  const details = h(
    "details",
    { class: "filter-section", open: !closed },
    h("summary", {}, icon(iconName), h("span", {}, title)),
    h("div", { class: `filter-body ${rowClass}` }, content),
  );
  details.addEventListener("toggle", () => {
    const set = new Set(ui.closed || []);
    if (details.open) set.delete(id);
    else set.add(id);
    ui.closed = [...set];
    saveUi(ui);
  });
  return details;
}

export async function catalogPage({ query }) {
  const params = Object.fromEntries(query.entries());
  const [categories, brands] = await Promise.all([
    api("/api/categories"),
    api(`/api/products/brands${toQuery({ category: params.category })}`),
  ]);
  const currentCategory = params.category || "";
  const currentSort = params.sort || "new";

  const ui = loadUi();
  // on phones the panel always starts collapsed, so the products are visible right away;
  // on a computer it stays the way the user left it
  const phone = window.matchMedia("(max-width: 860px)").matches;
  const collapsed = phone || (ui.collapsed ?? false);

  const body = h(
    "div",
    { class: "filters-content", id: "catalog-filters" },
    h(
      "label",
      { class: "filter-search" },
      icon("actions/search"),
      h("input", { name: "search", type: "search", placeholder: t("nav.search_placeholder"), "aria-label": t("common.search"), value: params.search || "" }),
    ),
    filterSection(ui, "categories", "navigation/catalog", t("home.categories"), [
      option("category", "", currentCategory === "", "navigation/catalog", t("catalog.all_categories")),
      ...categories.map((c) => option("category", c.slug, currentCategory === c.slug, `categories/${c.slug}`, c.name)),
    ], "scroll-row"),
    filterSection(ui, "sort", "actions/sort", t("catalog.sort"),
      SORTS.map(([value, iconName, flip]) =>
        option("sort", value, currentSort === value, iconName, t(`catalog.sort_${value}`), flip ? "flip" : "")),
      "scroll-row"),
    filterSection(ui, "price", "shop/price", t("catalog.price"), h(
      "div",
      { class: "price-range" },
      h("input", { name: "min_price", type: "number", min: 0, placeholder: t("catalog.price_from"), "aria-label": t("catalog.price_from"), value: params.min_price || "" }),
      h("span", { class: "muted" }, "—"),
      h("input", { name: "max_price", type: "number", min: 0, placeholder: t("catalog.price_to"), "aria-label": t("catalog.price_to"), value: params.max_price || "" }),
    )),
    filterSection(ui, "brand", "actions/filter", t("catalog.brand"),
      select("brand", [["", t("common.all")], ...brands.map((b) => [b, b])], params.brand)),
    filterSection(ui, "availability", "shop/in-stock", t("catalog.availability"), [
      h("label", { class: "filter-check" }, h("input", { name: "in_stock", type: "checkbox", checked: params.in_stock === "true" }), icon("shop/in-stock"), t("catalog.in_stock")),
      h("label", { class: "filter-check" }, h("input", { name: "discount", type: "checkbox", checked: params.discount === "true" }), icon("shop/discount"), t("catalog.discount")),
    ]),
    link("/catalog", icon("actions/reset"), ` ${t("catalog.reset_filters")}`),
  );
  body.hidden = collapsed;

  const toggle = h(
    "button",
    {
      type: "button",
      class: "filters-toggle",
      "aria-expanded": String(!collapsed),
      "aria-controls": "catalog-filters",
      onclick: () => {
        const open = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(open));
        body.hidden = !open;
        if (!phone) ui.collapsed = !open;
        saveUi(ui);
      },
    },
    icon("actions/filter"),
    h("span", {}, t("catalog.filters")),
    h("span", { class: "icon toggle-chevron", style: "--m: url(/resources/icons/navigation/chevron-down.svg)", "aria-hidden": "true" }),
  );

  const form = h(
    "form",
    {
      class: "filters-panel",
      "aria-label": t("catalog.filters"),
      onchange: () => apply(),
      onsubmit: (event) => {
        event.preventDefault();
        apply();
      },
    },
    toggle,
    body,
  );

  function apply() {
    const data = formData(form);
    for (const box of ["in_stock", "discount"]) data[box] = data[box] ? "true" : "";
    if (data.sort === "new") data.sort = "";
    // brand of another category makes no sense
    if ((data.category || "") !== currentCategory) data.brand = "";
    navigate(`/catalog${toQuery(data)}`);
  }

  const found = h("span", { class: "muted" });
  const grid = h("div", { class: "grid" });
  const listBox = h("div", {}, grid);

  const key = query.toString();
  const restore = saved && saved.key === key ? saved : null;
  const fetchPage = (cursor) => api(`/api/products${toQuery({ ...params, limit: 20, cursor })}`);
  // load the first products before the page is shown: no empty grid that fills in a moment later
  let state = restore?.state;
  if (!state) {
    const first = await fetchPage(null);
    state = { items: first.items, cursor: first.next_cursor, done: first.next_cursor === null, total: first.total };
  }
  const list = infiniteList({
    container: grid,
    fetchPage,
    renderItem: productCard,
    skeleton: () => skeletons("product", 4),
    state,
    onTotal: (total) => (found.textContent = t("catalog.found", { count: total })),
  });
  saved = { key, state: list.state, scrollY: restore?.scrollY || 0 };
  if (restore) afterRender(() => window.scrollTo(0, restore.scrollY));

  const removeTopButton = toTopButton();
  onLeave(() => {
    saved.scrollY = window.scrollY;
    list.destroy();
    removeTopButton();
  });

  const title = categories.find((c) => c.slug === currentCategory)?.name || t("catalog.title");
  return h(
    "div",
    { class: "catalog-layout" },
    form,
    h("section", { class: "section catalog-results" }, h("div", { class: "section-head" }, h("h1", {}, title), found), listBox),
  );
}
