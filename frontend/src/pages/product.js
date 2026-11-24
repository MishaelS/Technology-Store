import { api } from "../api.js";
import { addToCart, priceRow, specsTable, stockText } from "../components.js";
import { t } from "../i18n.js";
import { h, image } from "../ui.js";

export async function productPage({ params }) {
  const product = await api(`/api/products/${encodeURIComponent(params.id)}`);
  const quantity = h("input", { type: "number", min: 1, max: Math.max(1, product.stock), value: 1, style: "width: 60px" });
  return h(
    "div",
    {},
    h("p", {}, h("button", { onclick: () => history.back() }, `← ${t("common.back")}`)),
    h("div", { class: "muted" }, product.category_name, " · ", product.brand),
    h("h1", {}, product.name),
    image(product.image_url, product.name),
    priceRow(product),
    h("p", {}, stockText(product)),
    h(
      "div",
      { class: "row" },
      quantity,
      h("button", { disabled: product.stock <= 0, onclick: () => addToCart(product.id, Number(quantity.value) || 1) }, t("product.add_to_cart")),
    ),
    h("h2", {}, t("product.description")),
    h("p", {}, product.description),
    h("h2", {}, t("product.specs")),
    specsTable(product.specs),
  );
}
