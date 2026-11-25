// Admin panel. Every section is shown only if the user has its permission (from the API).
// The backend checks the same permissions, so hiding here is only for convenience.
import { api, query as toQuery } from "../api.js";
import { checksList, pager, statusName } from "../components.js";
import { t } from "../i18n.js";
import { reload } from "../router.js";
import { repairsSection, stockSection, systemSection } from "./staff.js";
import { can, session } from "../session.js";
import { attempt, date, field, flash, formData, h, icon, link, money, navigate, select } from "../ui.js";

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
  const menu = h("div", { class: "row" }, allowed.map(([key]) =>
    key === current ? h("b", {}, t(`admin.${key}`)) : link(`/admin?section=${key}`, t(`admin.${key}`))));
  return h("div", {}, h("h1", {}, t("admin.title")), menu, h("hr"), await render(query));
}

function go(section, params) {
  navigate(`/admin${toQuery({ section, ...params })}`);
}

// ---------- dashboard ----------

async function dashboard() {
  const s = await api("/api/admin/stats");
  const rows = [
    ["orders_total", s.orders_total], ["revenue_done", money(s.revenue_done)], ["revenue_active", money(s.revenue_active)],
    ["users_total", s.users_total], ["new_users_7d", s.new_users_7d], ["builds_total", s.builds_total], ["low_stock", s.low_stock],
  ];
  return h(
    "div",
    {},
    h("table", {}, rows.map(([key, value]) => h("tr", {}, h("th", {}, t(`admin.stats.${key}`)), h("td", {}, value)))),
    h("h3", {}, t("admin.orders_by_status")),
    h("table", {}, Object.entries(s.orders_by_status).map(([status, count]) => h("tr", {}, h("th", {}, statusName(status)), h("td", {}, count)))),
    h("h3", {}, t("admin.stats.top_products")),
    h("ol", {}, s.top_products.map((p) => h("li", {}, `${p.name} — ${t("common.pieces", { count: p.sold })}`))),
  );
}

// ---------- orders ----------

async function orders(query) {
  const params = { status: query.get("status") || "", search: query.get("search") || "", page: Number(query.get("page")) || 1 };
  const data = await api(`/api/admin/orders${toQuery({ ...params, page_size: 20 })}`);
  const filters = h(
    "form",
    {
      class: "row",
      onsubmit: (e) => {
        e.preventDefault();
        go("orders", { ...formData(e.target), page: 1 });
      },
    },
    select("status", [["", t("admin.all_statuses")], ...STATUSES.map((s) => [s, statusName(s)])], params.status),
    h("input", { name: "search", type: "search", value: params.search, placeholder: t("admin.order_search") }),
    h("button", {}, t("common.search")),
  );
  const table = h(
    "table",
    {},
    h("tr", {}, ["#", t("admin.date"), t("admin.client"), t("orders.items"), t("orders.total"), t("common.status")].map((x) => h("th", {}, x))),
    data.items.map((order) => h(
      "tr",
      {},
      h("td", {}, order.id),
      h("td", {}, date(order.created_at)),
      h("td", {}, order.user.name, h("br"), h("span", { class: "muted" }, order.user.email), h("br"), order.phone, h("br"), order.address,
        order.comment ? [h("br"), h("i", {}, order.comment)] : null),
      h("td", {}, h("ul", {}, order.items.map((i) => h("li", {}, `${i.product_name} × ${i.quantity}`)))),
      h("td", {}, money(order.total), order.bonus_used ? h("div", { class: "muted" }, `${t("checkout.bonus_used")}: ${order.bonus_used}`) : null),
      h("td", {}, h("b", {}, statusName(order.status)), h("div", {}, NEXT_STATUSES[order.status].map((next) =>
        h("button", {
          onclick: async () => {
            const done = await attempt(() => api(`/api/admin/orders/${order.id}/status`, { method: "PATCH", body: { status: next } }));
            if (done) reload();
          },
        }, `→ ${statusName(next)}`)))),
    )),
  );
  return h("div", {}, filters, table, pager(data, (page) => go("orders", { ...params, page })));
}

// ---------- products ----------

async function products(query) {
  const params = { search: query.get("search") || "", category: query.get("category") || "", page: Number(query.get("page")) || 1 };
  const [data, categories] = await Promise.all([
    api(`/api/admin/products${toQuery({ ...params, page_size: 20 })}`),
    api("/api/categories"),
  ]);
  const filters = h(
    "form",
    { class: "row", onsubmit: (e) => { e.preventDefault(); go("products", { ...formData(e.target), page: 1 }); } },
    select("category", [["", t("catalog.all_categories")], ...categories.map((c) => [c.slug, c.name])], params.category),
    h("input", { name: "search", type: "search", value: params.search, placeholder: t("common.search") }),
    h("button", {}, t("common.search")),
    link(`/admin/products/new${toQuery({ category: params.category })}`, icon("actions/plus"), ` ${t("admin.new_product")}`),
  );
  const table = h(
    "table",
    {},
    h("tr", {}, ["#", t("common.name"), t("catalog.category"), t("admin.price"), t("admin.stock"), t("admin.active"), ""].map((x) => h("th", {}, x))),
    data.items.map((p) => h(
      "tr",
      {},
      h("td", {}, p.id),
      h("td", {}, p.name),
      h("td", {}, p.category_name),
      h("td", {}, money(p.price), p.old_price ? h("div", { class: "old-price" }, money(p.old_price)) : null),
      h("td", {}, p.stock),
      h("td", {}, p.is_active ? t("common.yes") : h("span", { class: "muted" }, t("admin.hidden"))),
      h("td", {},
        link(`/admin/products/${p.id}`, icon("actions/edit"), ` ${t("common.edit")}`), " ",
        link(`/admin/products/new?copy=${p.id}`, t("editor.copy")), " ",
        h("button", {
          onclick: async () => {
            const action = p.is_active
              ? () => api(`/api/admin/products/${p.id}`, { method: "DELETE" })
              : () => api(`/api/admin/products/${p.id}`, { method: "PATCH", body: { is_active: true } });
            if ((await attempt(action)) !== undefined) reload();
          },
        }, p.is_active ? t("admin.hide") : t("admin.show"))),
    )),
  );
  return h("div", {}, filters, table, pager(data, (page) => go("products", { ...params, page })));
}

// ---------- client builds ----------

async function builds(query) {
  const params = { without_comment: query.get("without_comment") || "", page: Number(query.get("page")) || 1 };
  const data = await api(`/api/admin/builds${toQuery({ ...params, page_size: 10 })}`);
  const filter = h("label", {}, h("input", {
    type: "checkbox",
    checked: params.without_comment === "true",
    onchange: (e) => go("builds", { without_comment: e.target.checked ? "true" : "", page: 1 }),
  }), " ", t("admin.without_comment"));
  return h(
    "div",
    {},
    filter,
    data.items.map((build) => {
      const comment = h("textarea", { rows: 3 }, build.engineer_comment || "");
      return h(
        "div",
        { class: "card" },
        h("h3", {}, build.name),
        h("div", { class: "muted" }, `${build.user.name} (${build.user.email}) · ${date(build.created_at)}`),
        h("p", {}, h("b", {}, build.check.tier_name), " · ", money(build.check.total_price), " · ",
          h("span", { class: build.check.is_compatible ? "ok" : "error" },
            build.check.is_compatible ? t("builder.compatible") : t("builder.incompatible"))),
        h("ul", {}, build.items.map((p) => h("li", {}, `${p.category_name}: ${p.name}`))),
        h("details", {}, h("summary", {}, t("builder.checks_title")), checksList(build.check.checks)),
        field(t("builder.engineer_comment"), comment),
        h("button", {
          onclick: async () => {
            const saved = await attempt(() => api(`/api/admin/builds/${build.id}/comment`, { method: "PATCH", body: { comment: comment.value } }));
            if (saved) flash(t("common.saved"));
          },
        }, t("admin.save_comment")),
      );
    }),
    data.items.length ? pager(data, (page) => go("builds", { ...params, page })) : h("p", {}, t("common.nothing_found")),
  );
}

// ---------- news and facts ----------

async function content() {
  const [news, facts] = await Promise.all([api("/api/news?limit=50"), api("/api/admin/facts")]);
  const newsErrors = h("div");
  const newsForm = h(
    "form",
    {
      class: "stack card",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(newsForm);
        data.image_url = data.image_url || null;
        if (await attempt(() => api("/api/admin/news", { method: "POST", body: data }), newsErrors)) reload();
      },
    },
    h("h3", {}, t("admin.new_news")),
    field(t("admin.type"), select("type", ["news", "promo", "game"].map((x) => [x, t(`news_types.${x}`)]), "news")),
    field(t("admin.title_field"), h("input", { name: "title", required: true })),
    field(t("admin.text"), h("textarea", { name: "text", required: true })),
    field(t("admin.image_url"), h("input", { name: "image_url" })),
    h("button", {}, t("common.create")),
    newsErrors,
  );
  const factInput = h("input", { required: true, style: "width: 400px" });
  const factForm = h(
    "form",
    {
      class: "row",
      onsubmit: async (event) => {
        event.preventDefault();
        if (await attempt(() => api("/api/admin/facts", { method: "POST", body: { text: factInput.value } }))) reload();
      },
    },
    factInput,
    h("button", {}, t("admin.new_fact")),
  );
  const remove = (url) => async () => {
    if (!confirm(`${t("common.delete")}?`)) return;
    if ((await attempt(() => api(url, { method: "DELETE" }))) !== undefined) reload();
  };
  return h(
    "div",
    {},
    h("h2", {}, t("admin.news")),
    newsForm,
    h("table", {}, news.items.map((n) => h(
      "tr",
      {},
      h("td", {}, date(n.created_at)),
      h("td", {}, t(`news_types.${n.type}`)),
      h("td", {}, h("b", {}, n.title), h("div", {}, n.text)),
      h("td", {}, h("button", { onclick: remove(`/api/admin/news/${n.id}`) }, t("common.delete"))),
    ))),
    h("h2", {}, t("admin.facts")),
    factForm,
    h("table", {}, facts.map((f) => h(
      "tr",
      {},
      h("td", {}, f.text),
      h("td", {}, h("button", { onclick: remove(`/api/admin/facts/${f.id}`) }, t("common.delete"))),
    ))),
  );
}

// ---------- users ----------

async function users(query) {
  const params = { search: query.get("search") || "", role: query.get("role") || "", page: Number(query.get("page")) || 1 };
  const [data, roles] = await Promise.all([
    api(`/api/admin/users${toQuery({ ...params, page_size: 20 })}`),
    api("/api/admin/roles"),
  ]);
  const roleNames = roles.map((r) => [r.role, t(`roles.${r.role}`)]);
  const filters = h(
    "form",
    { class: "row", onsubmit: (e) => { e.preventDefault(); go("users", { ...formData(e.target), page: 1 }); } },
    select("role", [["", t("admin.all_roles")], ...roleNames], params.role),
    h("input", { name: "search", type: "search", value: params.search, placeholder: t("common.search") }),
    h("button", {}, t("common.search")),
  );
  const patch = (user, body) => async () => {
    if (await attempt(() => api(`/api/admin/users/${user.id}`, { method: "PATCH", body }))) reload();
  };

  const table = h(
    "table",
    {},
    h("tr", {}, ["#", t("auth.name"), t("account.role"), t("admin.bonus_balance"), ""].map((x) => h("th", {}, x))),
    data.items.map((user) => {
      const isMe = user.id === session.user.id;
      const roleSelect = select("role", roleNames, user.role);
      roleSelect.disabled = isMe;
      roleSelect.addEventListener("change", patch(user, { role: roleSelect.value }));
      const amount = h("input", { type: "number", placeholder: t("admin.amount"), style: "width: 80px", required: true });
      const reason = h("input", { placeholder: t("admin.reason"), required: true });
      return h(
        "tr",
        {},
        h("td", {}, user.id),
        h("td", {}, user.name, h("br"), h("span", { class: "muted" }, user.email),
          user.is_blocked ? h("div", { class: "error" }, t("admin.blocked")) : null),
        h("td", {}, roleSelect, h("div", { class: "muted" }, user.permissions.join(", "))),
        h("td", {}, user.bonus_balance, h("form", {
          class: "row",
          onsubmit: async (e) => {
            e.preventDefault();
            const body = { amount: Number(amount.value), reason: reason.value };
            if (await attempt(() => api(`/api/admin/users/${user.id}/bonus`, { method: "POST", body }))) reload();
          },
        }, amount, reason, h("button", {}, t("admin.grant_bonus")))),
        h("td", {}, isMe ? null : h("button", { onclick: patch(user, { is_blocked: !user.is_blocked }) },
          user.is_blocked ? t("admin.unblock") : t("admin.block"))),
      );
    }),
  );
  return h("div", {}, filters, table, pager(data, (page) => go("users", { ...params, page })));
}

