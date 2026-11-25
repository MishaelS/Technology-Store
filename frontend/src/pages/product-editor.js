// Product editor: create and edit products with a normal form instead of code or JSON.
// Spec fields come from the API (/api/admin/products/spec-schema), so a new spec added on the
// backend appears here without changes in the frontend.
//   #/admin/products/new                 new product
//   #/admin/products/new?category=gpu     new product in a category
//   #/admin/products/new?copy=7           new product based on product 7
//   #/admin/products/7                    edit product 7
import { api } from "../api.js";
import { priceRow, specsTable, stockText } from "../components.js";
import { t } from "../i18n.js";
import { attempt, field, flash, h, image, link, navigate, select } from "../ui.js";

export async function productEditorPage({ params, query }) {
  const editing = Boolean(params.id);
  const copyId = query.get("copy");
  const [categories, schema, brands, source] = await Promise.all([
    api("/api/categories"),
    api("/api/admin/products/spec-schema"),
    api("/api/products/brands"),
    editing ? api(`/api/admin/products/${encodeURIComponent(params.id)}`)
      : copyId ? api(`/api/admin/products/${encodeURIComponent(copyId)}`) : null,
  ]);
  const categoryNames = Object.fromEntries(categories.map((c) => [c.slug, c.name]));
  const startCategory = source?.category || (schema[query.get("category")] ? query.get("category") : categories[0].slug);

  // ---------- inputs ----------
  const inputs = {
    category: select("category", categories.map((c) => [c.slug, c.name]), startCategory),
    name: h("input", { name: "name", required: true, maxLength: 200, value: source?.name || "" }),
    brand: h("input", { name: "brand", required: true, maxLength: 100, list: "brand-list", value: source?.brand || "" }),
    description: h("textarea", { name: "description", rows: 4 }, source?.description || ""),
    price: h("input", { name: "price", type: "number", min: 1, step: 1, required: true, value: source?.price ?? "" }),
    old_price: h("input", { name: "old_price", type: "number", min: 1, step: 1, value: source?.old_price ?? "" }),
    stock: h("input", { name: "stock", type: "number", min: 0, step: 1, value: source?.stock ?? 0 }),
    image_url: h("input", { name: "image_url", maxLength: 500, placeholder: "https://…", value: source?.image_url || "" }),
    is_active: h("input", { type: "checkbox", checked: source ? source.is_active : true }),
  };
  inputs.brand.setAttribute("list", "brand-list");
  const brandList = h("datalist", { id: "brand-list" }, brands.map((b) => h("option", { value: b })));

  // ---------- specs ----------
  const specsBox = h("div");
  let specInputs = {}; // key -> {field, read()}
  let specValues = { ...(source?.specs || {}) }; // kept when the category changes

  function specInput(spec) {
    const value = specValues[spec.key];
    const label = `${t(`specs.${spec.key}`)}${spec.required ? " *" : ""}`;
    if (spec.kind === "flag") {
      const box = h("input", { type: "checkbox", checked: value === true });
      return { node: h("label", { class: "row" }, box, label), read: () => box.checked };
    }
    if (spec.kind === "text_list") {
      const current = Array.isArray(value) ? value : [];
      const boxes = spec.suggestions.map((s) => h("input", { type: "checkbox", value: s, checked: current.includes(s) }));
      const other = h("input", {
        placeholder: t("editor.list_other"),
        value: current.filter((v) => !spec.suggestions.includes(v)).join(", "),
      });
      return {
        node: h("fieldset", {}, h("legend", {}, label),
          h("div", { class: "row" }, boxes.map((b) => h("label", {}, b, ` ${b.value}`))), other),
        read: () => [
          ...boxes.filter((b) => b.checked).map((b) => b.value),
          ...other.value.split(",").map((v) => v.trim()).filter(Boolean),
        ],
      };
    }
    if (spec.kind === "text") {
      const listId = `list-${spec.key}`;
      const input = h("input", { required: spec.required, value: value ?? "" });
      input.setAttribute("list", listId);
      return {
        node: field(label, h("span", {}, input, h("datalist", { id: listId }, spec.suggestions.map((s) => h("option", { value: s }))))),
        read: () => input.value.trim(),
      };
    }
    // number or score
    const input = h("input", {
      type: "number", required: spec.required, step: "any",
      min: spec.kind === "score" ? 0 : 0.01, max: spec.kind === "score" ? 100 : null, value: value ?? "",
    });
    return {
      node: field(label, h("span", {}, input, spec.kind === "score" ? h("div", { class: "muted" }, t("editor.score_hint")) : null)),
      read: () => (input.value === "" ? "" : Number(input.value)),
    };
  }

  function drawSpecs() {
    const fields = schema[inputs.category.value] || [];
    specInputs = Object.fromEntries(fields.map((spec) => [spec.key, specInput(spec)]));
    specsBox.replaceChildren(...Object.values(specInputs).map((s) => s.node));
  }

  /** Filled spec fields of the current category. */
  function currentValues() {
    const values = {};
    for (const [key, input] of Object.entries(specInputs)) {
      const value = input.read();
      if (value !== "" && !(Array.isArray(value) && !value.length)) values[key] = value;
    }
    return values;
  }

  const isKnownKey = (key) => Object.values(schema).some((fields) => fields.some((f) => f.key === key));

  /** Specs to save: the current category's fields + extra keys the form doesn't know (kept as is). */
  function readSpecs() {
    const extras = Object.fromEntries(Object.entries(specValues).filter(([key]) => !isKnownKey(key)));
    return { ...extras, ...currentValues() };
  }

  // Switching the category keeps typed values: shared fields (tdp, socket, ram_type) carry over,
  // and switching back restores the rest.
  inputs.category.addEventListener("change", () => {
    const values = currentValues();
    for (const key of Object.keys(specInputs)) delete specValues[key];
    specValues = { ...specValues, ...values };
    drawSpecs();
    updatePreview();
  });

  // ---------- preview ----------
  const preview = h("div");
  const discountNote = h("div", { class: "muted" });
  const imagePreview = h("div");

  function readProduct() {
    const price = Number(inputs.price.value) || 0;
    const oldPrice = inputs.old_price.value ? Number(inputs.old_price.value) : null;
    return {
      category: inputs.category.value,
      name: inputs.name.value.trim(),
      brand: inputs.brand.value.trim(),
      description: inputs.description.value.trim(),
      price,
      old_price: oldPrice,
      stock: Number(inputs.stock.value) || 0,
      image_url: inputs.image_url.value.trim() || null,
      specs: readSpecs(),
    };
  }

  function updatePreview() {
    const p = readProduct();
    const discount = p.old_price && p.old_price > p.price && p.price > 0 ? Math.round(((p.old_price - p.price) * 100) / p.old_price) : 0;
    discountNote.textContent = discount ? t("editor.discount", { percent: discount }) : t("editor.old_price_hint");
    imagePreview.replaceChildren(image(p.image_url, p.name) || h("span", { class: "muted" }, t("editor.no_image")));
    const card = { ...p, discount_percent: discount, category_name: categoryNames[p.category] };
    preview.replaceChildren(
      h("div", { class: "card" },
        image(p.image_url, p.name),
        h("div", { class: "muted" }, card.category_name, p.brand ? ` · ${p.brand}` : ""),
        h("b", {}, p.name || t("editor.title_new")),
        priceRow(card),
        h("div", { class: "muted" }, stockText(card))),
      Object.keys(p.specs).length ? specsTable(p.specs) : null,
    );
  }

  // ---------- save ----------
  const errors = h("div");
  let saveAndNew = false;

  async function save(event) {
    event.preventDefault();
    const body = readProduct();
    if (editing) body.is_active = inputs.is_active.checked;
    const saved = await attempt(
      () => (editing
        ? api(`/api/admin/products/${source.id}`, { method: "PATCH", body })
        : api("/api/admin/products", { method: "POST", body })),
      errors,
    );
    if (!saved) return;
    errors.replaceChildren();
    if (!editing && !inputs.is_active.checked) {
      await attempt(() => api(`/api/admin/products/${saved.id}`, { method: "DELETE" })); // created hidden
    }
    flash(editing ? t("editor.saved") : t("editor.created"));
    if (saveAndNew) navigate(`/admin/products/new?category=${saved.category}&r=${Date.now()}`);
    else navigate(`/admin/products/${saved.id}`);
  }

  const form = h(
    "form",
    { class: "stack", onsubmit: save, oninput: updatePreview, onchange: updatePreview, style: "max-width: none" },
    h("p", { class: "muted" }, t("editor.required_hint")),
    h("h2", {}, t("editor.basics")),
    field(`${t("catalog.category")} *`, inputs.category),
    field(`${t("common.name")} *`, inputs.name),
    field(`${t("catalog.brand")} *`, inputs.brand),
    brandList,
    field(t("product.description"), inputs.description),
    h("h2", {}, t("editor.price_stock")),
    field(`${t("admin.price")}, ₽ *`, inputs.price),
    field(`${t("admin.old_price")}, ₽`, h("span", {}, inputs.old_price, discountNote)),
    field(t("admin.stock"), inputs.stock),
    h("h2", {}, t("editor.image")),
    field(t("admin.image_url"), h("span", {}, inputs.image_url, h("div", { class: "muted" }, t("editor.image_hint")))),
    imagePreview,
    h("h2", {}, t("editor.specs")),
    specsBox,
    h("h2", {}, t("editor.visibility")),
    h("label", { class: "row" }, inputs.is_active, t("editor.active")),
    h("div", { class: "row" },
      h("button", { onclick: () => (saveAndNew = false) }, t("common.save")),
      h("button", { onclick: () => (saveAndNew = true) }, t("editor.save_and_new")),
      link("/admin?section=products", t("editor.back_to_list"))),
    errors,
  );

  drawSpecs();
  updatePreview();

  const title = editing ? t("editor.title_edit", { name: source.name }) : t("editor.title_new");
  return h(
    "div",
    {},
    h("p", {}, link("/admin?section=products", `← ${t("editor.back_to_list")}`)),
    h("h1", {}, title),
    editing
      ? h("div", { class: "row" },
          source.is_active ? link(`/product/${source.id}`, t("editor.open_on_site")) : h("span", { class: "muted" }, t("admin.hidden")),
          link(`/admin/products/new?copy=${source.id}`, t("editor.copy")))
      : null,
    h("div", { class: "columns" }, form, h("div", { class: "sidebar" }, h("h3", {}, t("editor.preview")), preview)),
  );
}
