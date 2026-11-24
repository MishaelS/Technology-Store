import { api, query as toQuery } from "../api.js";
import { newsCard } from "../components.js";
import { t } from "../i18n.js";
import { infiniteList, toTopButton } from "../infinite.js";
import { onLeave } from "../router.js";
import { h, navigate, select } from "../ui.js";

const TYPES = ["news", "promo", "game"];

export function newsPage({ query }) {
  const type = query.get("type") || "";
  const filter = select("type", [["", t("common.all")], ...TYPES.map((x) => [x, t(`news_types.${x}`)])], type);
  filter.addEventListener("change", () => navigate(`/news${toQuery({ type: filter.value })}`));

  const list = h("div", { class: "grid" });
  const box = h("div", {}, list);
  const scroll = infiniteList({
    container: list,
    fetchPage: (cursor) => api(`/api/news${toQuery({ type, limit: 10, cursor })}`),
    renderItem: newsCard,
  });
  const removeTopButton = toTopButton();
  onLeave(() => {
    scroll.destroy();
    removeTopButton();
  });
  return h("div", {}, h("h1", {}, t("nav.news")), filter, box);
}
