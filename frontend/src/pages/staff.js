// Admin sections for staff work: repairs (engineers), stock receipts (employees), tech support (senior engineer).
import { api, query as toQuery } from "../api.js";
import { pager, statusPill } from "../components.js";
import { t } from "../i18n.js";
import { reload } from "../router.js";
import { attempt, date, field, flash, formData, h, link, money, navigate, select } from "../ui.js";

function go(section, params) {
  navigate(`/admin${toQuery({ section, ...params })}`);
}

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

export async function repairsSection(query) {
  const params = { status: query.get("status") || "", search: query.get("search") || "", page: Number(query.get("page")) || 1 };
  const data = await api(`/api/admin/repairs${toQuery({ ...params, page_size: 20 })}`);

  const errors = h("div");
  const createForm = h(
    "form",
    {
      class: "stack card",
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
    h("button", {}, t("repairs.accept")),
    errors,
  );

  const filters = h(
    "form",
    { class: "row", onsubmit: (e) => { e.preventDefault(); go("repairs", { ...formData(e.target), page: 1 }); } },
    select("status", [["", t("admin.all_statuses")], ...REPAIR_STATUSES.map((s) => [s, repairStatus(s)])], params.status),
    h("input", { name: "search", type: "search", value: params.search, placeholder: t("repairs.search") }),
    h("button", {}, t("common.search")),
  );

  const rows = data.items.map((repair) => {
    const price = h("input", { type: "number", min: 0, value: repair.price ?? "", style: "width: 90px" });
    const comment = h("textarea", { rows: 2 }, repair.engineer_comment);
    const save = (extra = {}) => async () => {
      const body = { engineer_comment: comment.value, price: price.value === "" ? null : Number(price.value), ...extra };
      if (await attempt(() => api(`/api/admin/repairs/${repair.id}`, { method: "PATCH", body }))) reload();
    };
    return h(
      "tr",
      {},
      h("td", {}, `#${repair.id}`, h("div", { class: "muted" }, date(repair.created_at))),
      h("td", {}, repair.client_name, h("br"), repair.client_phone,
        repair.client_id ? h("div", { class: "muted" }, t("repairs.has_account")) : null),
      h("td", {}, h("b", {}, repair.device), h("div", {}, repair.problem)),
      h("td", {},
        statusPill(repair.status, repairStatus(repair.status)),
        repair.engineer ? h("div", { class: "muted" }, repair.engineer.name) : null,
        h("div", {}, REPAIR_NEXT[repair.status].map((next) =>
          h("button", { onclick: save({ status: next }) }, `→ ${repairStatus(next)}`)))),
      h("td", {}, field(t("repairs.price"), price), field(t("repairs.comment"), comment),
        h("button", { onclick: save() }, t("common.save"))),
    );
  });

  return h(
    "div",
    {},
    h("details", {}, h("summary", {}, t("repairs.accept")), createForm),
    filters,
    data.items.length
      ? h("table", {},
          h("tr", {}, ["#", t("repairs.client"), t("repairs.device"), t("common.status"), ""].map((x) => h("th", {}, x))),
          rows)
      : h("p", {}, t("repairs.empty")),
    pager(data, (page) => go("repairs", { ...params, page })),
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

export async function stockSection(query) {
  const params = { page: Number(query.get("page")) || 1 };
  const [categories, log] = await Promise.all([
    api("/api/categories"),
    api(`/api/admin/stock/receipts${toQuery({ ...params, page_size: 20 })}`),
  ]);

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
      class: "stack card",
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
    h("h3", {}, t("stock.receive")),
    field(t("catalog.category"), categorySelect),
    field(`${t("stock.product")} *`, productSelect),
    field(`${t("stock.quantity")} *`, h("input", { name: "quantity", type: "number", min: 1, required: true })),
    field(t("stock.supplier"), h("input", { name: "supplier" })),
    field(t("stock.comment"), h("input", { name: "comment" })),
    h("button", {}, t("stock.receive")),
    errors,
  );

  return h(
    "div",
    {},
    form,
    h("h3", {}, t("stock.log")),
    log.items.length
      ? h("table", {},
          h("tr", {}, [t("admin.date"), t("stock.product"), t("stock.quantity"), t("stock.supplier"), t("stock.comment"), t("stock.received_by")]
            .map((x) => h("th", {}, x))),
          log.items.map((r) => h("tr", {},
            h("td", {}, date(r.created_at)),
            h("td", {}, link(`/admin/products/${r.product.id}`, r.product.name)),
            h("td", {}, `+${r.quantity}`),
            h("td", {}, r.supplier),
            h("td", {}, r.comment),
            h("td", {}, r.received_by?.name || "—"))))
      : h("p", {}, t("common.nothing_found")),
    pager(log, (page) => go("receipts", { page })),
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
    {},
    h("button", { onclick: () => reload() }, t("system.refresh")),
    h("table", {}, rows.map(([name, value]) => h("tr", {}, h("th", {}, name), h("td", {}, value)))),
    h("h3", {}, t("system.errors")),
    info.recent_errors.length
      ? [
          h("table", {}, info.recent_errors.map((e) => h("tr", {},
            h("td", {}, date(e.created_at)),
            h("td", {}, `${e.method} ${e.path}`),
            h("td", {}, h("code", {}, e.error))))),
          h("button", {
            onclick: async () => {
              if (!confirm(`${t("system.clear_errors")}?`)) return;
              if ((await attempt(() => api("/api/admin/system/errors", { method: "DELETE" }))) !== undefined) reload();
            },
          }, t("system.clear_errors")),
        ]
      : h("p", { class: "ok" }, t("system.no_errors")),
  );
}
