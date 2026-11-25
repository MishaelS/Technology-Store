// Admin sections for staff work: repairs (engineers), stock receipts (employees), tech support (senior engineer).
import { adminList, cell, pagedSource } from "../admin-list.js";
import { api, query as toQuery } from "../api.js";
import { statusPill } from "../components.js";
import { t } from "../i18n.js";
import { reload } from "../router.js";
import { attempt, date, field, flash, formData, h, icon, link, money, select } from "../ui.js";

// ---------- repairs ----------

const REPAIR_STATUSES = ["accepted", "diagnostics", "repairing", "ready", "issued", "cancelled"];
// Same rules as the backend (routers/repairs.py)
const REPAIR_NEXT = {
  accepted: ["diagnostics", "cancelled"],
  diagnostics: ["repairing", "ready", "cancelled"],
  repairing: ["ready", "cancelled"],
  ready: ["issued"],
  issued: [],
  cancelled: [],
};

export const repairStatus = (status) => t(`repairs.status.${status}`);

export function repairsSection(query) {

  const errors = h("div");
  const createForm = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const body = formData(createForm);
        body.price = body.price === "" ? null : Number(body.price);
        if (!body.client_email) delete body.client_email;
        const repair = await attempt(() => api("/api/admin/repairs", { method: "POST", body }), errors);
        if (repair) {
          flash(t("repairs.created", { id: repair.id }));
          reload();
        }
      },
    },
    field(`${t("repairs.client_name")} *`, h("input", { name: "client_name", required: true })),
    field(`${t("repairs.client_phone")} *`, h("input", { name: "client_phone", type: "tel", required: true })),
    field(t("repairs.client_email"), h("input", { name: "client_email", type: "email" })),
    field(`${t("repairs.device")} *`, h("input", { name: "device", required: true })),
    field(`${t("repairs.problem")} *`, h("textarea", { name: "problem", required: true, rows: 3 })),
    field(t("repairs.price"), h("input", { name: "price", type: "number", min: 0 })),
    h("button", { class: "primary" }, t("repairs.accept")),
    errors,
  );

  const list = adminList({
    section: "repairs",
    source: (params) => pagedSource("/api/admin/repairs", params),
    params: { status: query.get("status") || "", search: query.get("search") || "" },
    search: t("repairs.search"),
    filters: [{ name: "status", options: [["", t("admin.all_statuses")], ...REPAIR_STATUSES.map((s) => [s, repairStatus(s)])] }],
    emptyText: t("repairs.empty"),
    head: ["#", t("repairs.client"), t("repairs.device"), t("common.status"), t("repairs.comment")],
    render: (repair, update) => {
      const price = h("input", { type: "number", min: 0, value: repair.price ?? "", class: "input-small", placeholder: t("repairs.price") });
      const comment = h("textarea", { rows: 2, placeholder: t("repairs.comment") }, repair.engineer_comment);
      const save = (extra = {}) => async () => {
        const body = { engineer_comment: comment.value, price: price.value === "" ? null : Number(price.value), ...extra };
        const changed = await attempt(() => api(`/api/admin/repairs/${repair.id}`, { method: "PATCH", body }));
        if (changed) {
          update(changed);
          flash(t("common.saved"));
        }
      };
      return h(
        "tr",
        {},
        h("td", {}, cell(`#${repair.id}`, date(repair.created_at))),
        h("td", {}, cell(repair.client_name, repair.client_phone, repair.client_id ? t("repairs.has_account") : null)),
        h("td", {}, cell(repair.device, repair.problem)),
        h("td", {}, h("div", { class: "cell-actions" },
          statusPill(repair.status, repairStatus(repair.status)),
          repair.engineer ? h("span", { class: "cell-sub" }, repair.engineer.name) : null,
          REPAIR_NEXT[repair.status].map((next) =>
            h("button", { class: "small", onclick: save({ status: next }) }, `→ ${repairStatus(next)}`)))),
        h("td", {}, h("div", { class: "edit-cell" }, price, comment, h("button", { class: "small", onclick: save() }, t("common.save")))),
      );
    },
  });

  return h(
    "div",
    { class: "admin-stack" },
    h("details", { class: "panel create-box" }, h("summary", {}, icon("actions/plus"), t("repairs.accept")), createForm),
    list,
  );
}

/** Repairs of the client in the personal account. */
export async function myRepairs() {
  const list = await api("/api/repairs/my");
  if (!list.length) return h("p", {}, t("repairs.empty"));
  return h("div", {}, list.map((repair) => h(
    "div",
    { class: "card" },
    h("h3", {}, t("repairs.number", { id: repair.id }), " · ", repair.device),
    h("p", { class: "row" }, statusPill(repair.status, repairStatus(repair.status)), h("span", { class: "muted" }, date(repair.updated_at))),
    h("p", {}, `${t("repairs.problem")}: ${repair.problem}`),
    h("p", {}, `${t("repairs.price_label")}: `, repair.price === null ? t("repairs.price_not_set") : money(repair.price)),
    repair.engineer_comment ? h("p", {}, h("b", {}, `${t("repairs.comment")}: `), repair.engineer_comment) : null,
  )));
}

// ---------- stock receipts ----------

export async function stockSection() {
  const categories = await api("/api/categories");

  const productSelect = h("select", { name: "product_id", required: true }, h("option", { value: "" }, t("stock.choose_product")));
  async function loadProducts(category) {
    const data = await api(`/api/admin/products${toQuery({ category, page_size: 100 })}`);
    productSelect.replaceChildren(
      h("option", { value: "" }, t("stock.choose_product")),
      ...data.items.map((p) => h("option", { value: p.id }, `${p.name} (${t("admin.stock")}: ${p.stock})`)),
    );
  }
  const categorySelect = select("category", categories.map((c) => [c.slug, c.name]), categories[0].slug);
  categorySelect.addEventListener("change", () => loadProducts(categorySelect.value));
  await loadProducts(categories[0].slug);

  const errors = h("div");
  const form = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(form);
        const body = { product_id: Number(data.product_id), quantity: Number(data.quantity), supplier: data.supplier, comment: data.comment };
        const receipt = await attempt(() => api("/api/admin/stock/receipts", { method: "POST", body }), errors);
        if (receipt) {
          flash(t("stock.received", { name: receipt.product.name, quantity: receipt.quantity, stock: receipt.product.stock }));
          reload();
        }
      },
    },
    field(t("catalog.category"), categorySelect),
    field(`${t("stock.product")} *`, productSelect),
    field(`${t("stock.quantity")} *`, h("input", { name: "quantity", type: "number", min: 1, required: true })),
    field(t("stock.supplier"), h("input", { name: "supplier" })),
    field(t("stock.comment"), h("input", { name: "comment" })),
    h("button", { class: "primary" }, t("stock.receive")),
    errors,
  );

  const log = adminList({
    section: "receipts",
    source: (params) => pagedSource("/api/admin/stock/receipts", params),
    params: {},
    head: [t("admin.date"), t("stock.product"), t("stock.quantity"), t("stock.supplier"), t("stock.received_by")],
    render: (r) => h("tr", {},
      h("td", { class: "nowrap" }, date(r.created_at)),
      h("td", {}, cell(link(`/admin/products/${r.product.id}`, r.product.name), r.comment)),
      h("td", { class: "num ok" }, `+${r.quantity}`),
      h("td", {}, r.supplier || "—"),
      h("td", {}, r.received_by?.name || "—")),
  });

  return h(
    "div",
    { class: "admin-stack" },
    h("section", { class: "panel" }, h("h2", {}, t("stock.receive")), form),
    h("section", { class: "admin-stack" }, h("h2", {}, t("stock.log")), log),
  );
}

// ---------- tech support ----------

export async function systemSection() {
  const info = await api("/api/admin/system");
  const uptime = t("system.uptime_value", {
    hours: Math.floor(info.uptime_seconds / 3600),
    minutes: Math.floor((info.uptime_seconds % 3600) / 60),
  });
  const db = info.database;
  const rows = [
    [t("system.api"), info.api_version],
    ["Python", info.python_version],
    [t("system.uptime"), uptime],
    [t("system.database"), h("span", { class: db.ok ? "ok" : "error" }, db.ok ? t("system.db_ok") : t("system.db_down"))],
    [t("system.db_version"), db.version],
    [t("system.db_size"), db.size],
    [t("system.migration"), db.migration || "—"],
    ...Object.entries(info.counts).map(([key, value]) => [t(`system.count_${key}`), value]),
  ];
  return h(
    "div",
    { class: "admin-stack" },
    h("div", { class: "toolbar" }, h("button", { type: "button", onclick: () => reload() }, icon("actions/reset"), t("system.refresh"))),
    h("table", { class: "admin-table kv-table" }, rows.map(([name, value]) => h("tr", {}, h("th", {}, name), h("td", {}, value)))),
    h("h2", {}, t("system.errors")),
    info.recent_errors.length
      ? [
          h("table", { class: "admin-table" }, info.recent_errors.map((e) => h("tr", {},
            h("td", { class: "nowrap" }, date(e.created_at)),
            h("td", { class: "nowrap" }, `${e.method} ${e.path}`),
            h("td", {}, h("code", {}, e.error))))),
          h("button", {
            type: "button",
            class: "small",
            onclick: async () => {
              if (!confirm(`${t("system.clear_errors")}?`)) return;
              if ((await attempt(() => api("/api/admin/system/errors", { method: "DELETE" }))) !== undefined) reload();
            },
          }, t("system.clear_errors")),
        ]
      : h("p", { class: "ok" }, t("system.no_errors")),
  );
}
