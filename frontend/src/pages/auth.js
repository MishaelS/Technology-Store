import { api } from "../api.js";
import { t } from "../i18n.js";
import { headerChanged } from "../router.js";
import { refreshCartCount, saveLogin } from "../session.js";
import { attempt, field, formData, h, link, navigate } from "../ui.js";

function afterLogin(result, query) {
  saveLogin(result);
  refreshCartCount().catch(() => {}).finally(headerChanged);
  const next = query.get("next");
  navigate(next && next.startsWith("/") ? next : "/");
}

export function loginPage({ query }) {
  const errors = h("div");
  const form = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const result = await attempt(() => api("/api/auth/login", { method: "POST", body: formData(form) }), errors);
        if (result) afterLogin(result, query);
      },
    },
    field(t("auth.email"), h("input", { name: "email", type: "email", required: true, autocomplete: "username" })),
    field(t("auth.password"), h("input", { name: "password", type: "password", required: true, autocomplete: "current-password" })),
    h("button", {}, t("auth.login_button")),
    errors,
  );
  return h(
    "div",
    {},
    h("h1", {}, t("auth.login_title")),
    form,
    h("p", {}, t("auth.no_account"), " ", link(`/register?${query}`, t("auth.register_button"))),
  );
}

export function registerPage({ query }) {
  const errors = h("div");
  const form = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        const data = formData(form);
        if (!data.phone) delete data.phone;
        const result = await attempt(() => api("/api/auth/register", { method: "POST", body: data }), errors);
        if (result) afterLogin(result, query);
      },
    },
    field(t("auth.name"), h("input", { name: "name", required: true, autocomplete: "name" })),
    field(t("auth.email"), h("input", { name: "email", type: "email", required: true, autocomplete: "email" })),
    field(t("auth.password"), h("input", { name: "password", type: "password", required: true, minLength: 6, autocomplete: "new-password" })),
    field(t("auth.phone"), h("input", { name: "phone", type: "tel", autocomplete: "tel" })),
    h("button", {}, t("auth.register_button")),
    errors,
  );
  return h(
    "div",
    {},
    h("h1", {}, t("auth.register_title")),
    h("p", { class: "ok" }, t("auth.welcome_bonus", { count: 500 })),
    form,
    h("p", {}, t("auth.have_account"), " ", link(`/login?${query}`, t("auth.login_button"))),
  );
}
