// Pieces used on several pages.
import { api } from "./api.js";
import { t } from "./i18n.js";
import { headerChanged } from "./router.js";
import { isLoggedIn, session } from "./session.js";
import { attempt, date, flash, h, image, link, money, navigate } from "./ui.js";

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

export function productCard(product) {
  return h(
    "div",
    { class: "card" },
    image(product.image_url, product.name),
    h("div", { class: "muted" }, product.category_name),
    link(`/product/${product.id}`, h("b", {}, product.name)),
    priceRow(product),
    h("div", { class: "muted" }, stockText(product)),
    h("button", { disabled: product.stock <= 0, onclick: () => addToCart(product.id) }, t("product.add_to_cart")),
  );
}

export function priceRow(product) {
  return h(
    "div",
    { class: "row" },
    h("b", {}, money(product.price)),
    product.old_price ? h("span", { class: "old-price" }, money(product.old_price)) : null,
    product.discount_percent > 0 ? h("span", { class: "badge" }, t("product.discount_badge", { percent: product.discount_percent })) : null,
  );
}

export function stockText(product) {
  return product.stock > 0 ? t("product.in_stock", { count: product.stock }) : t("product.out_of_stock");
}

export function newsCard(news) {
  return h(
    "article",
    { class: "card" },
    image(news.image_url, news.title),
    h("div", { class: "muted" }, `${t(`news_types.${news.type}`)} · ${date(news.created_at)}`),
    h("h3", {}, news.title),
    h("p", {}, news.text),
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

/** List of the build checks with simple markers. */
export function checksList(checks) {
  const marks = { ok: "✓", error: "✗", warning: "!", skip: "–" };
  return h(
    "ul",
    {},
    checks.map((c) => h("li", { class: c.status === "skip" ? "muted" : c.status }, `${marks[c.status]} ${c.message}`)),
  );
}
