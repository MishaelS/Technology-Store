// Admin section "Backups": make a backup, upload one from the computer, download, restore, delete,
// and the auto backup switch (off by default). The work is done by the API (/api/admin/backups).
import { api, uploadFile } from "../api.js";
import { API_URL } from "../config.js";
import { t } from "../i18n.js";
import { reload } from "../router.js";
import { loadUser } from "../session.js";
import { attempt, date, emptyState, flash, h, icon } from "../ui.js";
import { iconButton, labelCells } from "../admin-list.js";

const size = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Downloads a backup: the file needs the token, so it goes through fetch and a temporary link. */
async function download(name) {
  const response = await fetch(`${API_URL}/api/admin/backups/${encodeURIComponent(name)}/download`, {
    headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
  });
  if (!response.ok) return flash(t("common.error"), "error");
  const url = URL.createObjectURL(await response.blob());
  const link = h("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function backupsSection() {
  const data = await api("/api/admin/backups");

  // ---------- make / upload ----------
  const picker = h("input", { type: "file", accept: ".zip,application/zip", hidden: true });
  const busy = (on) => box.classList.toggle("busy", on);
  async function make() {
    busy(true);
    const made = await attempt(() => api("/api/admin/backups", { method: "POST" }));
    busy(false);
    if (made) {
      flash(t("backups.made", { name: made.name }));
      reload();
    }
  }
  async function upload(file) {
    if (!file) return;
    busy(true);
    const saved = await attempt(() => uploadFile("/api/admin/backups/upload", file));
    busy(false);
    if (saved) {
      flash(t("backups.uploaded", { name: saved.name }));
      reload();
    }
  }
  picker.addEventListener("change", () => upload(picker.files[0]));
  const dropZone = h("div", { class: "backup-drop", role: "button", tabindex: "0", onclick: () => picker.click() },
    icon("actions/save"), h("span", {}, t("backups.drop_hint")));
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("over");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("over"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("over");
    upload(e.dataTransfer.files[0]);
  });

  // ---------- auto backup ----------
  const auto = data.auto;
  const autoSave = (changes) => attempt(() => api("/api/admin/backups/auto", { method: "PATCH", body: changes }));
  const enabled = h("input", { type: "checkbox", checked: auto.enabled });
  const every = h("input", { type: "number", min: 1, max: 720, value: auto.every_hours, class: "input-small", "aria-label": t("backups.every_hours") });
  const keep = h("input", { type: "number", min: 1, max: 100, value: auto.keep, class: "input-small", "aria-label": t("backups.keep") });
  const autoFields = h("div", { class: "auto-fields" },
    h("label", {}, t("backups.every_hours"), every), h("label", {}, t("backups.keep"), keep));
  const showFields = () => autoFields.classList.toggle("off", !enabled.checked);
  enabled.addEventListener("change", async () => {
    const saved = await autoSave({ enabled: enabled.checked });
    if (!saved) enabled.checked = !enabled.checked;
    else flash(enabled.checked ? t("backups.auto_on") : t("backups.auto_off"));
    showFields();
  });
  every.addEventListener("change", () => autoSave({ every_hours: Number(every.value) }));
  keep.addEventListener("change", () => autoSave({ keep: Number(keep.value) }));
  showFields();

  // ---------- list ----------
  const kindName = (kind) => t(`backups.kind_${kind}`);
  const restore = async (backup) => {
    if (!confirm(t("backups.restore_confirm", { date: date(backup.created_at) }))) return;
    busy(true);
    const done = await attempt(() => api(`/api/admin/backups/${encodeURIComponent(backup.name)}/restore`, { method: "POST" }));
    busy(false);
    if (!done) return;
    flash(t("backups.restored", { rows: done.rows }));
    await loadUser(); // the restored data may not have this user any more
    reload();
  };
  const remove = async (backup, row) => {
    if (!confirm(`${t("common.delete")}: ${backup.name}?`)) return;
    if ((await attempt(() => api(`/api/admin/backups/${encodeURIComponent(backup.name)}`, { method: "DELETE" }))) !== undefined) row.remove();
  };
  const head = [t("admin.date"), t("backups.kind"), t("backups.size"), t("backups.contents"), ""];
  const list = data.items.length
    ? h("div", { class: "admin-list-body" }, h("table", { class: "admin-table" },
        h("thead", {}, h("tr", {}, head.map((x) => h("th", {}, x)))),
        h("tbody", {}, data.items.map((backup) => {
          const row = h("tr", { class: backup.ok ? null : "is-hidden" },
            h("td", { class: "nowrap" }, h("div", { class: "cell" }, h("span", { class: "cell-main" }, date(backup.created_at)), h("span", { class: "cell-sub" }, backup.name))),
            h("td", {}, h("span", { class: `pill backup-${backup.kind}` }, kindName(backup.kind))),
            h("td", { class: "num nowrap" }, size(backup.size)),
            h("td", {}, backup.ok
              ? h("div", { class: "cell" }, h("span", {}, t("backups.rows", { count: backup.rows })), h("span", { class: "cell-sub" }, t("backups.pictures", { count: backup.uploads })))
              : h("span", { class: "error" }, t("errors.backup_broken"))),
            h("td", { class: "shrink" }, h("div", { class: "cell-actions" },
              iconButton("navigation/arrow-up", t("backups.download"), { class: "flip-down", onclick: () => download(backup.name) }),
              backup.ok ? iconButton("actions/reset", t("backups.restore"), { onclick: () => restore(backup) }) : null,
              iconButton("actions/delete", t("common.delete"), { class: "danger", onclick: () => remove(backup, row) }))),
          );
          labelCells(row, head);
          return row;
        }))))
    : emptyState("actions/save", t("backups.empty"));

  const box = h(
    "div",
    { class: "admin-stack backups" },
    h("section", { class: "panel" },
      h("div", { class: "toolbar" },
        h("button", { type: "button", class: "primary", onclick: make }, icon("actions/save"), t("backups.make")),
        h("span", { class: "muted" }, t("backups.what"))),
      dropZone, picker),
    h("section", { class: "panel" },
      h("label", { class: "check-row" }, enabled, h("span", {}, t("backups.auto"))),
      h("p", { class: "muted field-hint" }, t("backups.auto_hint"),
        auto.last_run ? ` ${t("backups.last_auto", { date: date(auto.last_run) })}` : ""),
      autoFields),
    h("section", { class: "admin-stack" }, h("h2", {}, t("backups.list")), list),
  );
  return box;
}
