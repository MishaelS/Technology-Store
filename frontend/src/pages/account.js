// Personal account: profile, orders, bonuses, saved builds (tabs in the address: ?tab=orders).
import { api } from "../api.js";
import { checksList, statusName } from "../components.js";
import { t } from "../i18n.js";
import { headerChanged, reload } from "../router.js";
import { session } from "../session.js";
import { attempt, date, field, flash, formData, h, link, money } from "../ui.js";
import { openInBuilder } from "./builder.js";
import { myRepairs } from "./staff.js";

const TABS = ["profile", "orders", "repairs", "bonus", "builds"];

export async function accountPage({ query }) {
  const tab = TABS.includes(query.get("tab")) ? query.get("tab") : "profile";
  const tabs = h("div", { class: "row" }, TABS.map((name) =>
    name === tab ? h("b", {}, t(`account.${name}`)) : link(`/account?tab=${name}`, t(`account.${name}`))));
  const content = await { profile, orders, repairs: myRepairs, bonus, builds }[tab]();
  return h("div", {}, h("h1", {}, t("account.title")), tabs, content);
}

function profile() {
  const user = session.user;
  const errors = h("div");
  const form = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(form);
        if (!data.phone) data.phone = null;
        const updated = await attempt(() => api("/api/auth/me", { method: "PATCH", body: data }), errors);
        if (!updated) return;
        session.user = updated;
        errors.replaceChildren();
        headerChanged();
        flash(t("common.saved"));
      },
    },
    field(t("auth.email"), h("input", { value: user.email, disabled: true })),
    field(t("account.role"), h("input", { value: t(`roles.${user.role}`), disabled: true })),
    field(t("auth.name"), h("input", { name: "name", required: true, value: user.name })),
    field(t("auth.phone"), h("input", { name: "phone", type: "tel", value: user.phone || "" })),
    h("button", {}, t("account.save_profile")),
    errors,
  );
  return form;
}

async function orders() {
  const list = await api("/api/orders/my");
  if (!list.length) return h("p", {}, t("orders.empty"));
  return h("div", {}, list.map((order) => h(
    "div",
    { class: "card" },
    h("h3", {}, t("orders.order_number", { id: order.id }), " · ", statusName(order.status)),
    h("div", { class: "muted" }, date(order.created_at), " · ", order.address),
    h("ul", {}, order.items.map((i) => h("li", {}, `${i.product_name} × ${i.quantity} — ${money(i.price * i.quantity)}`))),
    h("p", {},
      `${t("checkout.subtotal")}: ${money(order.subtotal)} · ${t("checkout.bonus_used")}: ${money(order.bonus_used)} · `,
      h("b", {}, `${t("orders.total")}: ${money(order.total)}`)),
    order.bonus_earned ? h("p", { class: "ok" }, t("orders.bonus_earned", { count: order.bonus_earned })) : null,
    order.status === "new"
      ? h("button", {
          onclick: async () => {
            if (!confirm(t("orders.cancel_confirm"))) return;
            if (await attempt(() => api(`/api/orders/${order.id}/cancel`, { method: "POST" }))) reload();
          },
        }, t("orders.cancel"))
      : null,
  )));
}

async function bonus() {
  const data = await api("/api/bonus");
  return h(
    "div",
    {},
    h("h2", {}, t("bonus.balance", { count: data.balance })),
    h("p", { class: "muted" }, t("bonus.rules")),
    h("h3", {}, t("bonus.history")),
    h("table", {}, data.history.map((row) => h(
      "tr",
      {},
      h("td", {}, date(row.created_at)),
      h("td", { class: row.amount > 0 ? "ok" : "error" }, row.amount > 0 ? `+${row.amount}` : String(row.amount)),
      h("td", {}, row.reason),
    ))),
  );
}

async function builds() {
  const list = await api("/api/builds");
  if (!list.length) return h("p", {}, t("account.no_builds"), " ", link("/builder", t("builder.title")));
  return h("div", {}, list.map((build) => h(
    "div",
    { class: "card" },
    h("h3", {}, build.name),
    h("div", { class: "muted" }, date(build.created_at), " · ", build.check.tier_name, " · ",
      build.check.is_compatible ? t("builder.compatible") : t("builder.incompatible"),
      " · ", money(build.check.total_price)),
    h("ul", {}, build.items.map((p) => h("li", {}, `${p.category_name}: ${p.name}`))),
    build.engineer_comment ? h("p", {}, h("b", {}, `${t("builder.engineer_comment")}: `), build.engineer_comment) : null,
    h("details", {}, h("summary", {}, t("builder.checks_title")), checksList(build.check.checks)),
    h("div", { class: "row" },
      h("button", { onclick: () => openInBuilder(build.items.map((p) => p.id)) }, t("builder.open")),
      h("button", {
        onclick: async () => {
          const cart = await attempt(() => api("/api/cart/add-many", { method: "POST", body: { product_ids: build.items.map((p) => p.id) } }));
          if (cart) {
            session.cartCount = cart.count;
            headerChanged();
            flash(t("builder.added_to_cart"));
          }
        },
      }, t("builder.add_all_to_cart")),
      h("button", {
        onclick: async () => {
          if (!confirm(t("common.delete") + "?")) return;
          if ((await attempt(() => api(`/api/builds/${build.id}`, { method: "DELETE" }))) !== undefined) {
            reload();
          }
        },
      }, t("common.delete")),
    ),
  )));
}
