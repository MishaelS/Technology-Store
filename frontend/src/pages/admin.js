// Admin panel. Every section is shown only if the user has its permission (from the API).
// The backend checks the same permissions, so hiding here is only for convenience.
import { api, query as toQuery } from "../api.js";
import { adminList, cell, iconButton, pagedSource } from "../admin-list.js";
import { checksList, statusName, statusPill } from "../components.js";
import { t } from "../i18n.js";
import { imageDrop } from "../image-drop.js";
import { infiniteList } from "../infinite.js";
import { onLeave, reload } from "../router.js";
import { backupsSection } from "./backups.js";
import { repairsSection, stockSection, systemSection } from "./staff.js";
import { can, session } from "../session.js";
import { attempt, date, field, flash, formData, h, icon, link, money, select, skeletons } from "../ui.js";

const SECTIONS = [
  ["dashboard", "stats.view", dashboard],
  ["orders", "orders.manage", orders],
  ["products", "products.manage", products],
  ["builds", "builds.review", builds],
  ["receipts", "stock.receive", stockSection],
  ["repairs", "repairs.manage", repairsSection],
  ["content", "content.manage", content],
  ["users", "users.manage", users],
  ["system", "system.view", systemSection],
  ["backups", "system.backup", backupsSection],
];
const STATUSES = ["new", "confirmed", "assembling", "shipped", "done", "cancelled"];
// Same rules as the backend (services/orders.py): which status can follow which
const NEXT_STATUSES = {
  new: ["confirmed", "cancelled"],
  confirmed: ["assembling", "cancelled"],
  assembling: ["shipped", "cancelled"],
  shipped: ["done"],
  done: [],
  cancelled: [],
};

export async function adminPage({ query }) {
  const allowed = SECTIONS.filter(([, permission]) => can(permission));
  const name = query.get("section");
  const [current, , render] = allowed.find(([key]) => key === name) || allowed[0];
  const menu = h("nav", { class: "side-menu", "aria-label": t("admin.title") }, allowed.map(([key]) =>
    key === current ? h("b", { "aria-current": "page" }, t(`admin.${key}`)) : link(`/admin?section=${key}`, t(`admin.${key}`))));
  return h(
    "div",
    { class: "admin-layout" },
    menu,
    h("div", { class: "admin-content" }, h("h1", {}, t(`admin.${current}`)), await render(query)),
  );
}

// ---------- dashboard ----------

async function dashboard() {
  const s = await api("/api/admin/stats");
  const tiles = [
    ["orders_total", s.orders_total, "orders/order"], ["revenue_done", money(s.revenue_done), "shop/price"],
    ["revenue_active", money(s.revenue_active), "orders/payment"], ["users_total", s.users_total, "admin/users"],
    ["new_users_7d", s.new_users_7d, "navigation/register"], ["builds_total", s.builds_total, "navigation/builder"],
    ["low_stock", s.low_stock, "admin/low-stock"],
  ];
  return h(
    "div",
    { class: "dashboard" },
    h("div", { class: "stat-grid" }, tiles.map(([key, value, iconName]) =>
      h("div", { class: `stat-tile${key === "low_stock" && s.low_stock ? " warn" : ""}` },
        h("span", { class: "stat-icon" }, icon(iconName)), h("span", { class: "stat-label" }, t(`admin.stats.${key}`)), h("strong", { class: "stat-value num" }, value)))),
    h("div", { class: "split" },
      h("section", { class: "panel" },
        h("h3", {}, t("admin.orders_by_status")),
        h("ul", { class: "status-list" }, Object.entries(s.orders_by_status).map(([status, count]) =>
          h("li", {}, statusPill(status), h("span", { class: "num" }, count))))),
      h("section", { class: "panel" },
        h("h3", {}, t("admin.stats.top_products")),
        h("ol", { class: "top-list" }, s.top_products.map((p) =>
          h("li", {}, h("span", {}, p.name), h("span", { class: "muted num" }, t("common.pieces", { count: p.sold }))))))),
  );
}

// ---------- orders ----------

function orders(query) {
  return adminList({
    section: "orders",
    source: (params) => pagedSource("/api/admin/orders", params),
    params: { status: query.get("status") || "", search: query.get("search") || "" },
    search: t("admin.order_search"),
    filters: [{ name: "status", options: [["", t("admin.all_statuses")], ...STATUSES.map((s) => [s, statusName(s)])] }],
    head: ["#", t("admin.date"), t("admin.client"), t("orders.items"), t("orders.total"), t("common.status")],
    render: (order, update) => h(
      "tr",
      {},
      h("td", { class: "num" }, order.id),
      h("td", { class: "nowrap" }, date(order.created_at)),
      h("td", {}, cell(order.user.name, order.user.email, order.phone, order.address),
        order.comment ? h("p", { class: "cell-note" }, order.comment) : null),
      h("td", {}, h("ul", { class: "plain-list" }, order.items.map((i) => h("li", {}, `${i.product_name} × ${i.quantity}`)))),
      h("td", { class: "nowrap" }, cell(h("span", { class: "price" }, money(order.total)),
        order.bonus_used ? `${t("checkout.bonus_used")}: ${order.bonus_used}` : null)),
      h("td", {}, h("div", { class: "cell-actions" }, statusPill(order.status),
        NEXT_STATUSES[order.status].map((next) =>
          h("button", {
            class: "small",
            onclick: async () => {
              const changed = await attempt(() => api(`/api/admin/orders/${order.id}/status`, { method: "PATCH", body: { status: next } }));
              if (changed) update(changed);
            },
          }, `→ ${statusName(next)}`)))),
    ),
  });
}

// ---------- products ----------

async function products(query) {
  const categories = await api("/api/categories");
  const category = query.get("category") || "";
  return adminList({
    section: "products",
    source: (params) => pagedSource("/api/admin/products", params),
    params: { search: query.get("search") || "", category },
    search: t("admin.product_search"),
    filters: [{ name: "category", options: [["", t("catalog.all_categories")], ...categories.map((c) => [c.slug, c.name])] }],
    actions: h("a", { href: `#/admin/products/new${toQuery({ category })}`, class: "btn primary" }, icon("actions/plus"), t("admin.new_product")),
    head: ["#", t("common.name"), t("admin.price"), t("admin.stock"), t("common.status"), ""],
    render: (p, update) => h(
      "tr",
      { class: p.is_active ? null : "is-hidden" },
      h("td", { class: "num" }, p.id),
      h("td", {}, cell(p.name, p.category_name)),
      h("td", { class: "nowrap" }, cell(h("span", { class: "price" }, money(p.price)), p.old_price ? h("s", {}, money(p.old_price)) : null)),
      h("td", { class: `num${p.stock <= 3 ? " warning" : ""}` }, p.stock),
      h("td", {}, p.is_active ? h("span", { class: "pill s-done" }, t("admin.active")) : h("span", { class: "pill s-cancelled" }, t("admin.hidden"))),
      h("td", { class: "shrink" }, h("div", { class: "cell-actions" },
        iconButton("actions/edit", t("common.edit"), { href: `#/admin/products/${p.id}` }),
        iconButton("actions/copy", t("editor.copy"), { href: `#/admin/products/new?copy=${p.id}` }),
        iconButton(p.is_active ? "actions/hide" : "actions/show", p.is_active ? t("admin.hide") : t("admin.show"), {
          onclick: async () => {
            const action = p.is_active
              ? () => api(`/api/admin/products/${p.id}`, { method: "DELETE" })
              : () => api(`/api/admin/products/${p.id}`, { method: "PATCH", body: { is_active: true } });
            if ((await attempt(action)) !== undefined) update({ ...p, is_active: !p.is_active });
          },
        }))),
    ),
  });
}

// ---------- client builds ----------

function builds(query) {
  return adminList({
    section: "builds",
    source: (params) => pagedSource("/api/admin/builds", params, 10),
    params: { without_comment: query.get("without_comment") || "" },
    filters: [{ name: "without_comment", type: "checkbox", label: t("admin.without_comment") }],
    skeleton: () => skeletons("news", 2),
    render: (build) => {
      const comment = h("textarea", { rows: 3 }, build.engineer_comment || "");
      return h(
        "article",
        { class: "card admin-card" },
        h("div", { class: "admin-card-head" },
          h("h3", {}, build.name),
          h("span", { class: build.check.is_compatible ? "pill s-done" : "pill s-cancelled" },
            build.check.is_compatible ? t("builder.compatible") : t("builder.incompatible"))),
        h("p", { class: "muted" }, `${build.user.name} · ${build.user.email} · ${date(build.created_at)}`),
        h("p", {}, h("b", {}, build.check.tier_name), " · ", h("span", { class: "price" }, money(build.check.total_price))),
        h("ul", { class: "plain-list" }, build.items.map((p) => h("li", {}, h("span", { class: "muted" }, `${p.category_name}: `), p.name))),
        h("details", {}, h("summary", {}, t("builder.checks_title")), checksList(build.check.checks)),
        field(t("builder.engineer_comment"), comment),
        h("button", {
          onclick: async () => {
            const saved = await attempt(() => api(`/api/admin/builds/${build.id}/comment`, { method: "PATCH", body: { comment: comment.value } }));
            if (saved) flash(t("common.saved"));
          },
        }, t("admin.save_comment")),
      );
    },
  });
}

// ---------- news and facts ----------

async function content() {
  const facts = await api("/api/admin/facts");
  const newsErrors = h("div");
  const newsForm = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(newsForm);
        data.image_url = data.image_url || null;
        if (await attempt(() => api("/api/admin/news", { method: "POST", body: data }), newsErrors)) reload();
      },
    },
    field(t("admin.type"), select("type", ["news", "promo", "game"].map((x) => [x, t(`news_types.${x}`)]), "news")),
    field(t("admin.title_field"), h("input", { name: "title", required: true })),
    field(t("admin.text"), h("textarea", { name: "text", required: true, rows: 4 })),
    (() => {
      const url = h("input", { name: "image_url" });
      return [imageDrop(url), field(t("admin.image_url"), url)];
    })(),
    h("button", { class: "primary" }, t("common.create")),
    newsErrors,
  );
  const remove = (url, node) => async () => {
    if (!confirm(`${t("common.delete")}?`)) return;
    if ((await attempt(() => api(url, { method: "DELETE" }))) !== undefined) node().remove();
  };

  // news come from the public cursor API: the same infinite list as on the news page
  const newsTable = h("table", { class: "admin-table" },
    h("thead", {}, h("tr", {}, [t("admin.date"), t("admin.type"), t("admin.title_field"), ""].map((x) => h("th", {}, x)))));
  const newsList = infiniteList({
    container: newsTable,
    fetchPage: (cursor) => api(`/api/news${toQuery({ limit: 20, cursor })}`),
    endText: t("admin.list_end"),
    emptyText: t("common.nothing_found"),
    renderItem: (n) => {
      const row = h(
        "tr",
        {},
        h("td", { class: "nowrap" }, date(n.created_at)),
        h("td", {}, h("span", { class: `news-badge news-${n.type}` }, t(`news_types.${n.type}`))),
        h("td", {}, cell(n.title, n.text)),
        h("td", { class: "shrink" }, iconButton("actions/delete", t("common.delete"), { class: "danger", onclick: remove(`/api/admin/news/${n.id}`, () => row) })),
      );
      return row;
    },
  });
  onLeave(() => newsList.destroy());

  const factInput = h("input", { required: true, placeholder: t("admin.fact_placeholder") });
  const factForm = h(
    "form",
    {
      class: "inline-form",
      onsubmit: async (event) => {
        event.preventDefault();
        if (await attempt(() => api("/api/admin/facts", { method: "POST", body: { text: factInput.value } }))) reload();
      },
    },
    factInput,
    h("button", { class: "primary" }, icon("actions/plus"), t("admin.new_fact")),
  );
  return h(
    "div",
    { class: "admin-stack" },
    h("details", { class: "panel create-box" }, h("summary", {}, icon("actions/plus"), t("admin.new_news")), newsForm),
    h("section", { class: "admin-stack" }, h("h2", {}, t("admin.news")), newsTable),
    h("section", { class: "admin-stack" },
      h("h2", {}, t("admin.facts")),
      factForm,
      h("table", { class: "admin-table" }, h("tbody", {}, facts.map((f) => {
        const row = h("tr", {},
          h("td", {}, f.text),
          h("td", { class: "shrink" }, iconButton("actions/delete", t("common.delete"), { class: "danger", onclick: remove(`/api/admin/facts/${f.id}`, () => row) })));
        return row;
      })))),
  );
}

// ---------- users ----------

async function users(query) {
  const roles = await api("/api/admin/roles");
  const roleNames = roles.map((r) => [r.role, t(`roles.${r.role}`)]);
  return adminList({
    section: "users",
    source: (params) => pagedSource("/api/admin/users", params),
    params: { search: query.get("search") || "", role: query.get("role") || "" },
    search: t("admin.user_search"),
    filters: [{ name: "role", options: [["", t("admin.all_roles")], ...roleNames] }],
    head: ["#", t("auth.name"), t("account.role"), t("admin.bonus_balance"), ""],
    render: (user, update) => {
      const isMe = user.id === session.user.id;
      const patch = (body) => async () => {
        const changed = await attempt(() => api(`/api/admin/users/${user.id}`, { method: "PATCH", body }));
        if (changed) update(changed);
      };
      const roleSelect = select("role", roleNames, user.role);
      roleSelect.disabled = isMe;
      roleSelect.addEventListener("change", patch({ role: roleSelect.value }));
      const amount = h("input", { type: "number", placeholder: t("admin.amount"), class: "input-small", required: true });
      const reason = h("input", { placeholder: t("admin.reason"), required: true });
      return h(
        "tr",
        { class: user.is_blocked ? "is-hidden" : null },
        h("td", { class: "num" }, user.id),
        h("td", {}, cell(user.name, user.email), user.is_blocked ? h("span", { class: "pill s-cancelled" }, t("admin.blocked")) : null),
        h("td", {}, roleSelect),
        h("td", {}, h("div", { class: "num bonus-value" }, user.bonus_balance), h("form", {
          class: "inline-form",
          onsubmit: async (e) => {
            e.preventDefault();
            const body = { amount: Number(amount.value), reason: reason.value };
            const changed = await attempt(() => api(`/api/admin/users/${user.id}/bonus`, { method: "POST", body }));
            if (changed) update(changed);
          },
        }, amount, reason, h("button", { class: "small" }, t("admin.grant_bonus")))),
        h("td", { class: "shrink" }, isMe ? null : iconButton(user.is_blocked ? "actions/unlock" : "actions/block",
          user.is_blocked ? t("admin.unblock") : t("admin.block"), { class: user.is_blocked ? "" : "danger", onclick: patch({ is_blocked: !user.is_blocked }) })),
      );
    },
  });
}
