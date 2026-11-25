// Pieces used on several pages.
import { api } from "./api.js";
import { t } from "./i18n.js";
import { headerChanged } from "./router.js";
import { isLoggedIn, session } from "./session.js";
import { attempt, date, flash, h, icon, image, money, navigate } from "./ui.js";

export function goToLogin() {
  navigate(`/login?next=${encodeURIComponent(location.hash.slice(1) || "/")}`);
}

export async function addToCart(productId, quantity = 1) {
  if (!isLoggedIn()) return goToLogin();
  const cart = await attempt(() => api("/api/cart", { method: "POST", body: { product_id: productId, quantity } }));
  if (cart) {
    session.cartCount = cart.count;
    headerChanged();
    flash(t("product.added"));
  }
}

/** Picture of a product, or its category icon while there is no photo. */
export function productThumb(product, href) {
  const content = image(product.image_url, product.name) || icon(`categories/${product.category}`);
  return h("a", { href: `#${href}`, class: "thumb", "aria-hidden": "true", tabindex: -1 }, content);
}

export function productCard(product) {
  const href = `/product/${product.id}`;
  return h(
    "article",
    { class: "card product-card" },
    productThumb(product, href),
    h("span", { class: "muted", style: "font-size: 13px" }, product.category_name),
    h("a", { href: `#${href}`, class: "title" }, product.name),
    priceRow(product),
    h(
      "div",
      { class: "foot" },
      h("span", { class: product.stock > 0 ? "stock" : "stock out" }, stockText(product)),
      h("button", { type: "button", class: "primary", disabled: product.stock <= 0, onclick: () => addToCart(product.id) }, t("product.add_to_cart")),
    ),
  );
}

export function priceRow(product) {
  return h(
    "div",
    { class: "row price-row" },
    h("span", { class: "price" }, money(product.price)),
    product.old_price ? h("span", { class: "old-price" }, money(product.old_price)) : null,
    product.discount_percent > 0 ? h("span", { class: "discount" }, t("product.discount_badge", { percent: product.discount_percent })) : null,
  );
}

export function stockText(product) {
  return product.stock > 0 ? t("product.in_stock", { count: product.stock }) : t("product.out_of_stock");
}

// news type -> icon of its badge
export const NEWS_ICONS = { news: "navigation/news", promo: "content/promo", game: "content/game" };

/** A news tile: colored badge with the type, date, title and text. */
export function newsCard(news) {
  return h(
    "article",
    { class: `news-tile news-${news.type}` },
    image(news.image_url, news.title),
    h(
      "div",
      { class: "news-meta" },
      h("span", { class: "news-badge" }, icon(NEWS_ICONS[news.type] || "navigation/news"), t(`news_types.${news.type}`)),
      h("time", { datetime: news.created_at }, date(news.created_at)),
    ),
    h("h3", {}, news.title),
    h("p", {}, news.text),
  );
}

/** "Interesting fact" tile. */
export function factCard(fact) {
  return h(
    "aside",
    { class: "news-tile fact-tile" },
    h("div", { class: "news-meta" }, h("span", { class: "news-badge" }, icon("content/fact"), t("home.fact"))),
    h("p", {}, fact.text),
  );
}

export function specValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  return String(value);
}

export function specsTable(specs) {
  return h(
    "table",
    {},
    Object.entries(specs).map(([key, value]) => h("tr", {}, h("th", {}, t(`specs.${key}`)), h("td", {}, specValue(value)))),
  );
}

export function statusName(status) {
  return t(`orders.status.${status}`);
}

/** Colored status label. `text` defaults to the order status name. */
export function statusPill(status, text = statusName(status)) {
  return h("span", { class: `pill s-${status}` }, text);
}

/** "← Назад  Страница 1 из 3  Вперёд →" for admin tables. */
export function pager({ page, pages }, go) {
  return h(
    "div",
    { class: "row" },
    h("button", { disabled: page <= 1, onclick: () => go(page - 1) }, t("common.prev")),
    h("span", {}, t("admin.page", { page, pages })),
    h("button", { disabled: page >= pages, onclick: () => go(page + 1) }, t("common.next")),
  );
}

/** List of the build checks with status icons. */
export function checksList(checks) {
  const icons = { ok: "feedback/success", error: "feedback/error", warning: "feedback/warning", skip: "feedback/skip" };
  return h(
    "ul",
    { class: "checks" },
    checks.map((c) => h(
      "li",
      { class: c.status === "skip" ? "muted" : c.status },
      icon(icons[c.status], t(`builder.check_status.${c.status}`)),
      h("span", {}, c.message),
    )),
  );
}
