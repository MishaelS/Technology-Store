// News page: tiles with news, promos and game news + a sticky panel on the left to pick the type.
import { api, query as toQuery } from "../api.js";
import { NEWS_ICONS, newsCard } from "../components.js";
import { t } from "../i18n.js";
import { infiniteList, toTopButton } from "../infinite.js";
import { onLeave } from "../router.js";
import { h, icon, skeletons } from "../ui.js";

const TYPES = ["news", "promo", "game"];

export async function newsPage({ query }) {
  const type = TYPES.includes(query.get("type")) ? query.get("type") : "";

  const typeLink = (value, iconName, text) =>
    h(
      "a",
      { href: `#/news${toQuery({ type: value })}`, class: "filter-option", "aria-current": value === type ? "page" : null },
      icon(iconName),
      h("span", { class: "filter-text" }, text),
    );
  const sidebar = h(
    "aside",
    { class: "filters-panel" },
    h(
      "section",
      { class: "filter-section" },
      h("h2", { class: "filter-title" }, icon("actions/filter"), h("span", {}, t("catalog.filters"))),
      h(
        "nav",
        { class: "filter-body scroll-row", "aria-label": t("nav.news") },
        typeLink("", "navigation/news", t("common.all")),
        TYPES.map((x) => typeLink(x, NEWS_ICONS[x], t(`news_types.${x}`))),
      ),
    ),
  );

  const fetchPage = (cursor) => api(`/api/news${toQuery({ type, limit: 12, cursor })}`);
  // first tiles are loaded before the page is shown, so it doesn't open with "Loading…"
  const first = await fetchPage(null);
  const grid = h("div", { class: "news-grid" });
  const box = h("div", {}, grid);
  const scroll = infiniteList({
    container: grid,
    fetchPage,
    renderItem: newsCard,
    skeleton: () => skeletons("news", 3),
    endText: t("home.news_end"),
    state: { items: first.items, cursor: first.next_cursor, done: first.next_cursor === null, total: null },
  });
  const removeTopButton = toTopButton();
  onLeave(() => {
    scroll.destroy();
    removeTopButton();
  });

  const title = type ? t(`news_types.${type}`) : t("nav.news");
  return h(
    "div",
    { class: "catalog-layout" },
    sidebar,
    h("section", { class: "section catalog-results" }, h("div", { class: "section-head" }, h("h1", {}, title)), box),
  );
}
