import { api } from "../api.js";
import { productCard } from "../components.js";
import { t } from "../i18n.js";
import { date, h, icon, link } from "../ui.js";

function section(title, content, more = null) {
  return h("section", { class: "section" }, h("div", { class: "section-head" }, h("h2", {}, title), more), content);
}

export async function homePage() {
  const [data, categories] = await Promise.all([api("/api/home"), api("/api/categories")]);

  const hero = h(
    "section",
    { class: "hero" },
    h(
      "div",
      { class: "copy" },
      h("h1", {}, t("app.tagline")),
      h("p", {}, t("home.build_cta_text")),
      h(
        "div",
        { class: "row" },
        h("a", { href: "#/builder", class: "btn primary big" }, icon("navigation/builder"), t("nav.builder")),
        h("a", { href: "#/catalog", class: "btn big" }, t("nav.catalog")),
      ),
    ),
    h(
      "div",
      { class: "hero-card" },
      h("strong", {}, t("builder.title")),
      h("span", { class: "muted" }, t("home.build_steps")),
      h("ul", { class: "checks" },
        ["socket", "ram", "psu"].map((key) => h("li", {}, icon("feedback/success"), h("span", {}, t(`home.build_check_${key}`))))),
    ),
  );

  // Categories in a sticky panel on the left, like in the catalog. The list can be collapsed;
  // the choice is kept in the browser.
  let closed = false;
  try {
    closed = localStorage.getItem("homeCategoriesClosed") === "1";
  } catch {
    /* storage blocked: the list just starts open */
  }
  const categoryList = h(
    "details",
    { class: "filter-section", open: !closed },
    h("summary", {}, icon("navigation/catalog"), h("span", {}, t("home.categories"))),
    h(
      "nav",
      { class: "filter-body scroll-row", "aria-label": t("home.categories") },
      h("a", { href: "#/catalog", class: "filter-option" }, icon("navigation/catalog"), h("span", { class: "filter-text" }, t("catalog.all_categories"))),
      categories.map((c) =>
        h("a", { href: `#/catalog?category=${c.slug}`, class: "filter-option" }, icon(`categories/${c.slug}`), h("span", { class: "filter-text" }, c.name))),
    ),
  );
  categoryList.addEventListener("toggle", () => {
    try {
      localStorage.setItem("homeCategoriesClosed", categoryList.open ? "0" : "1");
    } catch {
      /* not remembered, still works */
    }
  });
  const sidebar = h("aside", { class: "filters-panel" }, categoryList);

  const news = data.promos.concat(data.news);
  return h(
    "div",
    { class: "catalog-layout" },
    sidebar,
    h(
    "div",
    { class: "section home-content" },
    hero,
    data.discounts.length
      ? section(t("home.discounts"), h("div", { class: "grid" }, data.discounts.slice(0, 4).map(productCard)),
          link("/catalog?discount=true", t("catalog.discount")))
      : null,
    section(t("home.hits"), h("div", { class: "grid" }, data.hits.slice(0, 4).map(productCard)), link("/catalog", t("nav.catalog"))),
    h(
      "div",
      { class: "split" },
      section(
        t("home.news"),
        h("div", { class: "news-list" }, news.map((n) => h(
          "article",
          {},
          h("span", { class: "muted", style: "font-size: 13px" }, `${t(`news_types.${n.type}`)} · ${date(n.created_at)}`),
          h("strong", {}, n.title),
          h("span", { class: "muted" }, n.text),
        ))),
        link("/news", t("nav.news")),
      ),
      data.fact
        ? h("aside", { class: "card" }, h("span", { class: "muted" }, t("home.fact")), h("p", { style: "font-size: 17px; font-weight: 600" }, data.fact.text))
        : null,
    ),
  );
}
