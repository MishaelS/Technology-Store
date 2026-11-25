// Picture field: drag a file onto it or click to choose one; it's uploaded at once
// (POST /api/admin/uploads) and its address goes into the linked text input,
// so forms keep reading the picture from that input as before. A link can still be typed there.
import { uploadFile } from "./api.js";
import { t } from "./i18n.js";
import { flash, h, icon, image } from "./ui.js";

const TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MAX_MB = 5;

/** `input` — the text input with the picture address. Returns the drop zone element. */
export function imageDrop(input) {
  const picker = h("input", { type: "file", accept: TYPES.join(","), hidden: true });
  const preview = h("div", { class: "drop-preview" });
  const status = h("span", { class: "drop-status" });
  const removeButton = h("button", { type: "button", class: "small ghost", onclick: (e) => { e.stopPropagation(); set(""); } },
    icon("actions/delete"), t("upload.remove"));
  const zone = h(
    "div",
    { class: "drop-zone", role: "button", tabindex: "0", "aria-label": t("upload.hint") },
    preview,
    h("div", { class: "drop-text" },
      h("strong", {}, t("upload.hint")),
      h("span", { class: "muted" }, t("upload.types", { mb: MAX_MB })),
      status),
    removeButton,
    picker,
  );

  function draw() {
    const url = input.value.trim();
    const picture = image(url);
    preview.replaceChildren(picture || h("span", { class: "drop-empty" }, icon("content/image")));
    zone.classList.toggle("has-image", Boolean(picture));
    removeButton.hidden = !url;
  }
  function set(url) {
    input.value = url;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    draw();
  }

  async function send(file) {
    if (!file) return;
    if (!TYPES.includes(file.type)) return flash(t("errors.upload_type"), "error");
    if (file.size > MAX_MB * 1024 * 1024) return flash(t("errors.upload_too_big", { mb: MAX_MB }), "error");
    zone.classList.add("busy");
    status.textContent = t("upload.uploading");
    try {
      const { url } = await uploadFile("/api/admin/uploads", file);
      set(url);
      status.textContent = "";
    } catch (error) {
      status.textContent = "";
      flash(error.message, "error");
    } finally {
      zone.classList.remove("busy");
    }
  }

  zone.addEventListener("click", (e) => {
    if (e.target === picker) return;
    picker.click();
  });
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      picker.click();
    }
  });
  picker.addEventListener("change", () => {
    send(picker.files[0]);
    picker.value = ""; // the same file can be chosen again
  });
  // dragging over: highlight; the counter keeps it on while moving over child elements
  let depth = 0;
  zone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    depth++;
    zone.classList.add("over");
  });
  zone.addEventListener("dragover", (e) => e.preventDefault());
  zone.addEventListener("dragleave", () => {
    if (--depth <= 0) zone.classList.remove("over");
  });
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    zone.classList.remove("over");
    send(e.dataTransfer.files[0]);
  });
  // also paste from the clipboard (Cmd+V on the focused zone)
  zone.addEventListener("paste", (e) => {
    const file = [...e.clipboardData.files][0];
    if (file) send(file);
  });
  input.addEventListener("input", draw);
  draw();
  return zone;
}

/**
 * Several pictures (extra photos of a product): thumbnails with a remove button, and a tile to add more —
 * drop several files onto it or choose them. Returns {node, read()}; read() gives the list of addresses.
 */
export function imageList(initial = [], onChange = () => {}, max = 10) {
  let urls = [...initial];
  const picker = h("input", { type: "file", accept: TYPES.join(","), multiple: true, hidden: true });
  const grid = h("div", { class: "image-list" });
  const node = h("div", { class: "image-list-box" }, grid, picker);

  function draw() {
    const tiles = urls.map((url, i) => h("div", { class: "image-tile" },
      image(url, "") || h("span", { class: "drop-empty" }, icon("content/image")),
      h("button", { type: "button", class: "icon-only small", title: t("upload.remove"), "aria-label": t("upload.remove"),
        onclick: () => {
          urls.splice(i, 1);
          draw();
          onChange();
        } }, icon("actions/close"))));
    const add = urls.length < max
      ? h("button", { type: "button", class: "image-add", onclick: () => picker.click() }, icon("actions/plus"), t("upload.add_more"))
      : null;
    grid.replaceChildren(...tiles, add || "");
    if (add) {
      add.addEventListener("dragover", (e) => {
        e.preventDefault();
        add.classList.add("over");
      });
      add.addEventListener("dragleave", () => add.classList.remove("over"));
      add.addEventListener("drop", (e) => {
        e.preventDefault();
        add.classList.remove("over");
        send([...e.dataTransfer.files]);
      });
    }
  }

  async function send(files) {
    const room = max - urls.length;
    for (const file of files.slice(0, room)) {
      if (!TYPES.includes(file.type)) {
        flash(t("errors.upload_type"), "error");
        continue;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        flash(t("errors.upload_too_big", { mb: MAX_MB }), "error");
        continue;
      }
      node.classList.add("busy");
      try {
        const { url } = await uploadFile("/api/admin/uploads", file);
        urls.push(url);
        draw();
        onChange();
      } catch (error) {
        flash(error.message, "error");
      } finally {
        node.classList.remove("busy");
      }
    }
  }
  picker.addEventListener("change", () => {
    send([...picker.files]);
    picker.value = "";
  });
  draw();
  return { node, read: () => [...urls] };
}
