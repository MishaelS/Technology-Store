import { api } from "../api.js";
import { addToCart, priceRow, productThumb, specsTable, stockText } from "../components.js";
import { t } from "../i18n.js";
import { can } from "../session.js";
import { h, icon, link } from "../ui.js";

export async function productPage({ params }) {
  const product = await api(`/api/products/${encodeURIComponent(params.id)}`);
  const quantity = h("input", { type: "number", min: 1, max: Math.max(1, product.stock), value: 1, style: "width: 76px", "aria-label": t("cart.quantity") });
  return h(
    "div",
    {},
    h("p", {}, h("button", { type: "button", onclick: () => history.back() }, `← ${t("common.back")}`)),
    h(
      "section",
      { class: "split product-page" },
      h("div", { class: "card product-card" }, productThumb(product, `/product/${product.id}`)),
      h(
        "div",
        { class: "section" },
        h("span", { class: "muted" }, product.category_name, " · ", product.brand),
        h("h1", {}, product.name),
        can("products.manage") ? link(`/admin/products/${product.id}`, icon("actions/edit"), ` ${t("editor.edit")}`) : null,
        h("div", { class: "big-price" }, priceRow(product)),
        h("span", { class: product.stock > 0 ? "stock" : "stock out" }, stockText(product)),
        h(
          "div",
          { class: "row" },
          quantity,
          h("button", { type: "button", class: "primary big", disabled: product.stock <= 0, onclick: () => addToCart(product.id, Number(quantity.value) || 1) },
            icon("navigation/cart"), t("product.add_to_cart")),
          h("a", { href: "#/builder", class: "btn big" }, icon("navigation/builder"), t("nav.builder")),
        ),
      ),
    ),
    h(
      "section",
      { class: "split" },
      h("div", { class: "section" }, h("h2", {}, t("product.specs")), specsTable(product.specs)),
      h("div", { class: "section" }, h("h2", {}, t("product.description")), h("p", {}, product.description)),
    ),
  );
}
