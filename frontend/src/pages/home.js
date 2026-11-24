import { api } from "../api.js";
import { newsCard, productCard } from "../components.js";
import { t } from "../i18n.js";
import { h, link } from "../ui.js";

function section(title, ...content) {
  return h("section", {}, h("h2", {}, title), ...content);
}

export async function homePage() {
  const data = await api("/api/home");
  return h(
    "div",
    {},
    h("h1", {}, t("app.name")),
    h("p", { class: "muted" }, t("app.tagline")),
    data.promos.length ? section(t("home.promos"), h("div", { class: "grid" }, data.promos.map(newsCard))) : null,
    section(t("home.build_cta"), h("p", {}, t("home.build_cta_text")), link("/builder", `${t("builder.title")} →`)),
    section(t("home.discounts"), h("div", { class: "grid" }, data.discounts.map(productCard))),
    section(t("home.hits"), h("div", { class: "grid" }, data.hits.map(productCard))),
    section(t("home.news"), h("div", { class: "grid" }, data.news.map(newsCard)), h("p", {}, link("/news", `${t("nav.news")} →`))),
    data.fact ? section(t("home.fact"), h("p", {}, data.fact.text)) : null,
  );
}
