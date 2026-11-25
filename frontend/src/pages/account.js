// Personal account: profile, orders, bonuses, saved builds (tabs in the address: ?tab=orders).
import { api, uploadFile } from "../api.js";
import { checksList, statusPill } from "../components.js";
import { t } from "../i18n.js";
import { headerChanged, reload } from "../router.js";
import { can, logout, session } from "../session.js";
import { attempt, avatar, date, emptyState, field, flash, formData, h, icon, link, money, navigate } from "../ui.js";
import { openInBuilder } from "./builder.js";
import { myRepairs } from "./staff.js";

const TABS = ["profile", "orders", "repairs", "bonus", "builds"];

export async function accountPage({ query }) {
  const tab = TABS.includes(query.get("tab")) ? query.get("tab") : "profile";
  const tabs = h("nav", { class: "tabs", "aria-label": t("account.title") }, TABS.map((name) =>
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
    // roles are shown only to those who manage users (the admin), nobody else sees their own role
    can("users.manage") ? field(t("account.role"), h("input", { value: t(`roles.${user.role}`), disabled: true })) : null,
    field(t("auth.name"), h("input", { name: "name", required: true, value: user.name })),
    field(t("auth.phone"), h("input", { name: "phone", type: "tel", value: user.phone || "" })),
    h("button", {}, t("account.save_profile")),
    errors,
  );
  return h("div", { class: "profile" }, profileCard(), form);
}

/** Avatar with the photo controls, name, role and the logout button. */
function profileCard() {
  const user = session.user;
  const picker = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif", hidden: true });
  const photo = h("button", { type: "button", class: "avatar-drop", "aria-label": t("account.photo_upload"), onclick: () => picker.click() },
    avatar(user, "big"), h("span", { class: "avatar-edit" }, icon("actions/edit")));
  const card = h(
    "section",
    { class: "panel profile-card" },
    photo,
    h("div", { class: "profile-info" },
      h("strong", { class: "profile-name" }, user.name),
      h("span", { class: "muted" }, user.email, can("users.manage") ? ` · ${t(`roles.${user.role}`)}` : ""),
      h("div", { class: "row" },
        h("button", { type: "button", class: "small", onclick: () => picker.click() }, icon("content/image"), t("account.photo_upload")),
        user.avatar_url
          ? h("button", { type: "button", class: "small ghost", onclick: () => setPhoto(() => api("/api/auth/me/avatar", { method: "DELETE" })) },
              icon("actions/delete"), t("account.photo_remove"))
          : null),
      h("span", { class: "muted field-hint" }, t("account.photo_hint"))),
    h("button", { type: "button", class: "logout-button", onclick: () => {
      logout();
      headerChanged();
      navigate("/");
    } }, icon("navigation/logout"), t("account.logout")),
    picker,
  );

  async function setPhoto(request) {
    card.classList.add("busy");
    const updated = await attempt(request);
    card.classList.remove("busy");
    if (!updated) return;
    session.user = updated;
    headerChanged();
    card.replaceWith(profileCard());
  }
  const send = (file) => file && setPhoto(() => uploadFile("/api/auth/me/avatar", file));
  picker.addEventListener("change", () => send(picker.files[0]));
  // a photo can also be dropped onto the avatar
  photo.addEventListener("dragover", (e) => {
    e.preventDefault();
    photo.classList.add("over");
  });
  photo.addEventListener("dragleave", () => photo.classList.remove("over"));
  photo.addEventListener("drop", (e) => {
    e.preventDefault();
    photo.classList.remove("over");
    send(e.dataTransfer.files[0]);
  });
  return card;
}

async function orders() {
  const list = await api("/api/orders/my");
  if (!list.length) return emptyState("orders/order", t("orders.empty"), ["/catalog", t("cart.go_to_catalog")]);
  return h("div", {}, list.map((order) => h(
    "div",
    { class: "card" },
    h("div", { class: "section-head" }, h("h3", {}, t("orders.order_number", { id: order.id })), statusPill(order.status)),
    h("div", { class: "muted" }, date(order.created_at), " · ", order.address),
    h("ul", {}, order.items.map((i) => h("li", {}, `${i.product_name} × ${i.quantity} — ${money(i.price * i.quantity)}`))),
    h("p", {},
      `${t("checkout.subtotal")}: ${money(order.subtotal)} · ${t("checkout.bonus_used")}: ${money(order.bonus_used)} · `,
      h("b", { class: "price" }, `${t("orders.total")}: ${money(order.total)}`)),
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
  if (!list.length) return emptyState("navigation/builder", t("account.no_builds"), ["/builder", t("builder.title")]);
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
