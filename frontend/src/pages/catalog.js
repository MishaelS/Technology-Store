// Catalog: filters in the address (#/catalog?category=gpu&sort=price_asc) + infinite scroll.
// When the user opens a product and presses "Back", the list and scroll position are restored.
import { api, query as toQuery } from "../api.js";
import { productCard } from "../components.js";
import { t } from "../i18n.js";
import { infiniteList, toTopButton } from "../infinite.js";
import { afterRender, onLeave } from "../router.js";
import { field, formData, h, link, navigate, select } from "../ui.js";

const SORTS = ["new", "price_asc", "price_desc", "name"];
let saved = null; // {key, state, scrollY} of the last visited catalog list

export async function catalogPage({ query }) {
  const params = Object.fromEntries(query.entries());
  const [categories, brands] = await Promise.all([
    api("/api/categories"),
    api(`/api/products/brands${toQuery({ category: params.category })}`),
  ]);

  const form = h(
    "form",
    {
      class: "row filters",
      onchange: () => apply(),
      onsubmit: (event) => {
        event.preventDefault();
        apply();
      },
    },
    h("input", { name: "search", type: "search", placeholder: t("nav.search_placeholder"), value: params.search || "" }),
    select("category", [["", t("catalog.all_categories")], ...categories.map((c) => [c.slug, c.name])], params.category),
    select("brand", [["", `${t("catalog.brand")}: ${t("common.all")}`], ...brands.map((b) => [b, b])], params.brand),
    h("input", { name: "min_price", type: "number", min: 0, placeholder: t("catalog.price_from"), value: params.min_price || "", style: "width: 90px" }),
    h("input", { name: "max_price", type: "number", min: 0, placeholder: t("catalog.price_to"), value: params.max_price || "", style: "width: 90px" }),
    field(t("catalog.in_stock"), h("input", { name: "in_stock", type: "checkbox", checked: params.in_stock === "true" })),
    field(t("catalog.discount"), h("input", { name: "discount", type: "checkbox", checked: params.discount === "true" })),
    select("sort", SORTS.map((s) => [s, t(`catalog.sort_${s}`)]), params.sort || "new"),
    link("/catalog", t("catalog.reset_filters")),
  );

  function apply() {
    const data = formData(form);
    for (const box of ["in_stock", "discount"]) data[box] = data[box] ? "true" : "";
    if (data.sort === "new") data.sort = "";
    // brand of another category makes no sense
    if (data.category !== (params.category || "")) data.brand = "";
    navigate(`/catalog${toQuery(data)}`);
  }

  const found = h("p", { class: "muted" });
  const grid = h("div", { class: "grid" });
  const listBox = h("div", {}, grid);

  const key = query.toString();
  const restore = saved && saved.key === key ? saved : null;
  const list = infiniteList({
    container: grid,
    fetchPage: (cursor) => api(`/api/products${toQuery({ ...params, limit: 20, cursor })}`),
    renderItem: productCard,
    state: restore?.state,
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

  return h("div", {}, h("h1", {}, t("catalog.title")), form, found, listBox);
}
