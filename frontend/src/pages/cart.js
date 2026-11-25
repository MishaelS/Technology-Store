// Cart and checkout on one page.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { headerChanged } from "../router.js";
import { loadUser, session } from "../session.js";
import { attempt, field, flash, formData, h, link, money, navigate } from "../ui.js";

export async function cartPage() {
  const root = h("div");

  async function update(action) {
    const cart = await attempt(action);
    draw(cart || (await api("/api/cart")));
  }

  function draw(cart) {
    session.cartCount = cart.count;
    headerChanged();
    if (!cart.items.length) {
      root.replaceChildren(h("h1", {}, t("cart.title")), h("p", {}, t("cart.empty")), link("/catalog", t("cart.go_to_catalog")));
      return;
    }
    const rows = cart.items.map(({ product, quantity, sum }) => {
      const input = h("input", { type: "number", min: 0, max: 99, value: quantity, style: "width: 88px" });
      input.addEventListener("change", () =>
        update(() => api(`/api/cart/${product.id}`, { method: "PATCH", body: { quantity: Number(input.value) } })),
      );
      return h(
        "tr",
        {},
        h("td", {}, h("a", { href: `#/product/${product.id}`, class: "item-link" }, product.name)),
        h("td", { class: "price" }, money(product.price)),
        h("td", {}, input),
        h("td", { class: "price" }, money(sum)),
        h("td", {}, h("button", { type: "button", onclick: () => update(() => api(`/api/cart/${product.id}`, { method: "DELETE" })) }, t("cart.remove"))),
      );
    });
    root.replaceChildren(
      h("h1", {}, t("cart.title")),
      h(
        "div",
        { class: "columns" },
        h(
          "div",
          { class: "section" },
          h("div", { class: "table-box" }, h("table", {},
            h("tr", {}, h("th", {}, t("admin.products")), h("th", {}, t("admin.price")), h("th", {}, t("cart.quantity")), h("th", {}, t("common.sum")), h("th", {})),
            rows)),
          h("div", { class: "section-head" },
            h("span", {}, t("cart.items_count", { count: cart.count }), " · ", h("b", { class: "price" }, `${t("cart.total")}: ${money(cart.total)}`)),
            h("button", { type: "button", onclick: () => update(() => api("/api/cart", { method: "DELETE" })) }, t("cart.clear"))),
        ),
        checkoutForm(cart),
      ),
    );
  }

  draw(await api("/api/cart"));
  return root;
}

function checkoutForm(cart) {
  const errors = h("div");
  const summary = h("p");
  const bonusInput = h("input", { name: "bonus_to_use", type: "number", min: 0, max: cart.max_bonus, value: 0 });

  const showSummary = () => {
    const bonus = Math.min(Math.max(Number(bonusInput.value) || 0, 0), cart.max_bonus);
    summary.replaceChildren(
      `${t("checkout.subtotal")}: ${money(cart.total)} · ${t("checkout.bonus_used")}: ${money(bonus)} · `,
      h("b", {}, `${t("checkout.total")}: ${money(cart.total - bonus)}`),
    );
  };
  bonusInput.addEventListener("input", showSummary);
  showSummary();

  const form = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(form);
        data.bonus_to_use = Number(data.bonus_to_use) || 0;
        const order = await attempt(() => api("/api/orders", { method: "POST", body: data }), errors);
        if (!order) return;
        session.cartCount = 0; // the order empties the cart
        await loadUser(); // bonus balance changed
        headerChanged();
        flash(t("checkout.success", { id: order.id }));
        navigate("/account?tab=orders");
      },
    },
    field(t("checkout.address"), h("input", { name: "address", required: true, minLength: 5 })),
    field(t("checkout.phone"), h("input", { name: "phone", type: "tel", required: true, value: session.user?.phone || "" })),
    field(t("checkout.comment"), h("input", { name: "comment" })),
    field(`${t("checkout.use_bonus")} (${t("cart.max_bonus", { count: cart.max_bonus })})`, bonusInput),
    h("p", { class: "muted" }, t("bonus.rules"), " ", t("checkout.payment_note")),
    summary,
    h("button", {}, t("checkout.place_order")),
    errors,
  );
  return h("aside", { class: "sidebar" }, h("h2", {}, t("checkout.title")), form);
}
