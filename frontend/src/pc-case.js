// 3D case of the PC builder (three.js). The models come from Blender: backend/scripts/make_builder_models.py
// → resources/models/builder.glb. Every part of the build is cloned from that file and put on its mount point
// (empties named mount_* in the case and the motherboard), so positions live in one place — the Blender script.
//
// The view follows the specs of the products: the case is stretched to its size and gets its front panel and
// colour, the card is stretched to its length, coolers, cards and RAM are painted in their colour.
//
// The build changes → the parts that left fly out, the new ones fly into their place one after another
// (the order of a real assembly), with a soft overshoot at the end. When the build is complete and compatible
// it "powers on": fans spin, RGB and the power LED glow.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

// ?v=: browsers that kept an older version (it was cached then) take the new one
const MODEL_URL = "/resources/models/builder.glb?v=6";
const DRACO_PATH = "/vendor/three/examples/jsm/libs/draco/gltf/";
const ORDER = ["motherboard", "cpu", "cooler", "ram", "psu", "gpu", "storage", "cable"]; // assembly order: stagger of fly-ins
const FLY_IN = 900; // ms
const FLY_OUT = 450;
const STAGGER = 170;
const reduceMotion = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// where a part comes from, relative to its place (mm; +z = out of the open side, +y = up)
const FROM = {
  motherboard: [0, 40, 420],
  cpu: [0, 60, 160],
  cooler: [0, 90, 320],
  ram: [0, 0, 190],
  gpu: [-60, 0, 360],
  psu: [0, 0, 380],
  storage: [0, 0, 300],
  cable: [0, 0, 240],
};

let library = null;
/** The glTF file is loaded once per visit; progress(share 0..1) while it comes. */
function loadLibrary(progress) {
  if (!library) {
    const loader = new GLTFLoader();
    loader.setDRACOLoader(new DRACOLoader().setDecoderPath(DRACO_PATH));
    library = loader.loadAsync(MODEL_URL, (event) => {
      // a gzipped answer has no length: then only the text, without a percent
      if (event.lengthComputable && event.total) progress(event.loaded / event.total);
    }).then((gltf) => prepareLibrary(gltf.scene));
  }
  return library;
}

const easeOutBack = (t) => {
  const c = 1.25;
  return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2;
};
const easeInCubic = (t) => t * t * t;
const clamp01 = (t) => Math.min(1, Math.max(0, t));
/** Blender names are unique: the second "mount_board" is "mount_board.001" ("mount_board001" in three.js). */
const baseName = (name) => name.replace(/\.?\d{3}$/, "");

// ---------------------------------------------------------------- textures, drawn once on canvases

function canvasTexture(width, height, draw, { repeat = [1, 1], srgb = false } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext("2d"), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(...repeat);
  texture.anisotropy = 8;
  if (srgb) texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** A seeded random: the same pictures on every visit. */
function seeded(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

let textureSet = null;
/** The faces carry UVs in millimetres / 100 (see the Blender script), so repeat = 100 / tile size in mm. */
function textures() {
  if (textureSet || typeof document === "undefined") return textureSet;
  const rnd = seeded(7);
  // perforated steel: round holes in a hexagonal grid, 4 mm apart (white = metal, black = hole)
  const perforated = canvasTexture(128, 222, (g, w, h) => {
    g.fillStyle = "#fff";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#000";
    const step = w / 4;
    for (let row = 0; row < 8; row++) {
      for (let col = -1; col <= 4; col++) {
        const x = col * step + (row % 2 ? step / 2 : 0) + step / 2;
        const y = row * (h / 8) + h / 16;
        g.beginPath();
        g.arc(x, y, step * 0.36, 0, Math.PI * 2);
        g.fill();
      }
    }
  }, { repeat: [100 / 16, 100 / 13.86] });
  // honeycomb grill of the PSU
  const honeycomb = canvasTexture(128, 222, (g, w, h) => {
    g.fillStyle = "#fff";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#000";
    const step = w / 2;
    for (let row = 0; row < 4; row++) {
      for (let col = -1; col <= 2; col++) {
        const cx = col * step + (row % 2 ? step / 2 : 0) + step / 2;
        const cy = row * (h / 4) + h / 8;
        const r = step * 0.5;
        g.beginPath();
        for (let k = 0; k < 6; k++) g.lineTo(cx + r * Math.cos(Math.PI / 6 + (k * Math.PI) / 3), cy + r * Math.sin(Math.PI / 6 + (k * Math.PI) / 3));
        g.fill();
      }
    }
  }, { repeat: [100 / 10, 100 / 17.3] });
  // brushed metal: fine streaks along u (used as roughness and as a faint bump)
  const brushed = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = "#c8c8c8";
    g.fillRect(0, 0, w, h);
    for (let i = 0; i < 900; i++) {
      const v = 150 + Math.floor(rnd() * 105);
      g.fillStyle = `rgb(${v},${v},${v})`;
      g.globalAlpha = 0.35;
      g.fillRect(rnd() * w, rnd() * h, 20 + rnd() * 140, 1);
    }
    g.globalAlpha = 1;
  }, { repeat: [100 / 60, 100 / 60] });
  // powder coat: a soft speckle
  const powder = canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = "#d8d8d8";
    g.fillRect(0, 0, w, h);
    for (let i = 0; i < 2600; i++) {
      const v = 180 + Math.floor(rnd() * 75);
      g.fillStyle = `rgb(${v},${v},${v})`;
      g.fillRect(rnd() * w, rnd() * h, 1, 1);
    }
  }, { repeat: [100 / 20, 100 / 20] });
  // PCB: traces, vias and some silkscreen (multiplied with the board colour)
  const pcb = canvasTexture(512, 512, (g, w, h) => {
    g.fillStyle = "#b8b8b8";
    g.fillRect(0, 0, w, h);
    g.lineCap = "round";
    for (let i = 0; i < 170; i++) {
      let x = rnd() * w;
      let y = rnd() * h;
      g.strokeStyle = rnd() < 0.5 ? "#d4d4d4" : "#c8c8c8";
      g.lineWidth = rnd() < 0.8 ? 1.5 : 3;
      g.beginPath();
      g.moveTo(x, y);
      for (let k = 0; k < 4; k++) {
        const len = 10 + rnd() * 60;
        const dir = Math.floor(rnd() * 8) * (Math.PI / 4);
        x += Math.cos(dir) * len;
        y += Math.sin(dir) * len;
        g.lineTo(x, y);
      }
      g.stroke();
      g.fillStyle = "#d2d2d2";
      g.beginPath();
      g.arc(x, y, 1.8, 0, Math.PI * 2);
      g.fill();
    }
    g.fillStyle = "#dadada";
    for (let i = 0; i < 12; i++) g.fillRect(rnd() * w, rnd() * h, 8 + rnd() * 22, 2);
  }, { repeat: [100 / 80, 100 / 80] });
  // wood: long grain along v
  const wood = canvasTexture(256, 1024, (g, w, h) => {
    g.fillStyle = "#9c6a42";
    g.fillRect(0, 0, w, h);
    for (let i = 0; i < 140; i++) {
      const x = rnd() * w;
      const dark = rnd() < 0.5;
      g.strokeStyle = dark ? "rgba(70,40,20,0.35)" : "rgba(200,150,100,0.25)";
      g.lineWidth = 1 + rnd() * 3;
      g.beginPath();
      g.moveTo(x, 0);
      for (let y = 0; y <= h; y += 32) g.lineTo(x + Math.sin(y / 90 + i) * 4 + Math.sin(y / 23 + i * 3) * 1.2, y);
      g.stroke();
    }
  }, { repeat: [100 / 60, 100 / 240], srgb: true });
  // sleeved cable: a braid along the cable (u) around it (v)
  const braid = canvasTexture(64, 64, (g, w, h) => {
    g.fillStyle = "#808080";
    g.fillRect(0, 0, w, h);
    g.strokeStyle = "#e0e0e0";
    g.lineWidth = 3;
    for (let k = -4; k < 8; k++) {
      g.beginPath();
      g.moveTo(k * 16, 0);
      g.lineTo(k * 16 + 32, h);
      g.stroke();
      g.beginPath();
      g.moveTo(k * 16 + 32, 0);
      g.lineTo(k * 16, h);
      g.stroke();
    }
  });
  // fin stacks: bright fin edges with dark gaps, 1.8 mm apart; mipmaps keep them calm far away
  const finDraw = (g, w, h) => {
    g.fillStyle = "#3a3d42";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#ffffff";
    g.fillRect(0, 0, w * 0.3, h);
    g.fillStyle = "#c8ccd2";
    g.fillRect(w * 0.3, 0, w * 0.08, h);
  };
  const finsU = canvasTexture(16, 4, finDraw, { repeat: [100 / 1.8, 1], srgb: true });
  const finsV = canvasTexture(16, 4, finDraw, { repeat: [100 / 1.8, 1], srgb: true });
  finsV.rotation = Math.PI / 2;
  textureSet = { perforated, honeycomb, brushed, powder, pcb, wood, braid, finsU, finsV };
  return textureSet;
}

const BRUSHED = new Set(["Aluminium", "AluminiumDark", "CaseAccent", "SlotSteel", "GPUAccent", "RAMSpreader", "GPUBackplate", "CoolerCover", "BlackMetal"]);

/** Gives the materials of the library their textures and finer settings, by name. */
function prepareLibrary(scene3d) {
  const tex = textures();
  const done = new Set();
  scene3d.traverse((child) => {
    if (!child.isMesh || done.has(child.material)) return;
    const material = child.material;
    done.add(material);
    const name = material.name || "";
    if (!tex) return;
    if (name === "CaseMesh" || name === "PSUGrill") {
      material.alphaMap = name === "CaseMesh" ? tex.perforated : tex.honeycomb;
      material.alphaToCoverage = true;
      material.side = THREE.DoubleSide;
    } else if (BRUSHED.has(name)) {
      // dark metals: rougher, or they mirror the bright room and look grey-white at grazing angles
      if (material.color.getHSL({}).l < 0.15) material.roughness = Math.max(material.roughness, 0.5);
      material.roughnessMap = tex.brushed;
      material.bumpMap = tex.brushed;
      material.bumpScale = 0.15;
    } else if (name === "CaseBody" || name === "CaseInner") {
      material.roughnessMap = tex.powder;
      material.metalness = Math.min(material.metalness, 0.2);
    } else if (name === "PCB") {
      material.map = tex.pcb;
      material.roughnessMap = tex.pcb;
      material.color.multiplyScalar(1.25);
    } else if (name === "FinsU" || name === "FinsV") {
      material.map = name === "FinsU" ? tex.finsU : tex.finsV;
      material.roughness = 0.42;
    } else if (name === "GlassSide") {
      material.transparent = true;
      material.opacity = 0.06;
      material.depthWrite = false;
      material.roughness = 0.04;
      material.envMapIntensity = 0.5;
    } else if (name === "Wood") {
      material.map = tex.wood;
      material.color.set(0xffffff);
    } else if (name === "GlassTint") {
      material.transparent = true;
      material.opacity = 0.3;
      material.depthWrite = false;
      material.envMapIntensity = 1.6;
    } else if (name === "Mirror" || name === "Nickel") {
      material.envMapIntensity = 1.3;
    }
  });
  return scene3d;
}

/** Picture of a label: brand big, a second line small (PSU wattage, drive size). */
function labelTexture(text, sub = "", { dark = true, ratio = 3, accent = null } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = Math.round(512 / ratio);
  const g = canvas.getContext("2d");
  g.fillStyle = dark ? "#16181c" : "#eceff3";
  g.fillRect(0, 0, canvas.width, canvas.height);
  if (accent) {
    g.fillStyle = accent;
    g.fillRect(0, 0, canvas.width, canvas.height * 0.12);
  }
  g.fillStyle = dark ? "#f1f3f5" : "#1b1e23";
  g.textAlign = "center";
  g.textBaseline = "middle";
  const size = Math.min(canvas.height * (sub ? 0.42 : 0.55), (canvas.width * 1.5) / Math.max(4, text.length));
  g.font = `800 ${size}px Manrope, system-ui, sans-serif`;
  g.fillText(text.toUpperCase(), canvas.width / 2, canvas.height * (sub ? 0.4 : 0.5));
  if (sub) {
    g.font = `600 ${canvas.height * 0.22}px "JetBrains Mono", monospace`;
    g.globalAlpha = 0.75;
    g.fillText(sub, canvas.width / 2, canvas.height * 0.76);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.flipY = false; // glTF UVs start at the top
  texture.anisotropy = 8;
  texture.userData.own = true; // disposed with its part
  return texture;
}

// ---------------------------------------------------------------- what the specs say

/** Colours of the shop's spec "color" (and English names, just in case). */
const COLORS = {
  black: { hex: 0x22252b }, white: { hex: 0xe6e9ed, light: true }, grey: { hex: 0x6b7079 },
  silver: { hex: 0xb9bec5, metal: 0.85 }, brown: { hex: 0x6b4a33 },
};
const COLOR_NAMES = { "чёрный": "black", "черный": "black", "белый": "white", "серый": "grey", "серебристый": "silver", "коричневый": "brown", gray: "grey" };
export function colorOf(product) {
  const raw = String(product?.specs?.color || "").trim().toLowerCase();
  const key = COLOR_NAMES[raw] || raw;
  if (COLORS[key]) return key;
  if (/(white|snow|бел)/i.test(product?.name || "")) return "white";
  return null;
}

const FRONTS = { "сетка": "mesh", "стекло": "glass", "глухая": "solid", "дерево": "wood", mesh: "mesh", glass: "glass", solid: "solid", wood: "wood" };
const frontOf = (product) => FRONTS[String(product?.specs?.front_panel || "").trim().toLowerCase()] || "mesh";

/** The case model by the boards it takes: the biggest one decides. */
export function caseModel(product) {
  const sizes = product?.specs?.form_factors || ["ATX"];
  return sizes.includes("ATX") ? "case_atx" : sizes.includes("mATX") ? "case_matx" : "case_itx";
}
export const boardModel = (product) => ({ ATX: "board_atx", mATX: "board_matx", "Mini-ITX": "board_itx" })[product?.specs?.form_factor] || "board_atx";
const textOf = (product) => `${product?.brand || ""} ${product?.name || ""}`.toLowerCase();

/** The look of a card's shroud by its brand and series (the Blender file has a style_<gpu>_<style> for each). */
export function gpuStyle(product) {
  const text = textOf(product);
  if (/intel|\barc\b|founders|nvidia/.test(text)) return "flow";
  if (/ventus|dual|stormx|fighter|prime|pulse/.test(text)) return "plain";
  if (/asus|rog|tuf|sapphire|xfx/.test(text)) return "angular";
  if (/msi|suprim|gaming trio/.test(text)) return "trio";
  if (/gigabyte|aorus|windforce/.test(text)) return "wind";
  return "plain";
}
export const GPU_STYLES = ["plain", "angular", "trio", "wind", "flow"];
const GPU_BASE = { gpu1: 175, gpu2s: 200, gpu2: 250, gpu3: 320 };

/** Which card model, how much to stretch it (length, thickness by the power it takes) and its style. */
export function gpuPlan(product) {
  const s = product?.specs || {};
  const length = Number(s.length_mm) || 250;
  const fans = Number(s.fans) || (length < 180 ? 1 : length < 285 ? 2 : 3);
  const name = fans <= 1 ? "gpu1" : fans === 2 ? (length < 225 ? "gpu2s" : "gpu2") : "gpu3";
  const tdp = Number(s.tdp) || 200;
  const thick = tdp >= 400 ? 1.38 : tdp >= 300 ? 1.22 : tdp >= 200 ? 1 : 0.84;
  return { name, scale: length / GPU_BASE[name], thick, style: gpuStyle(product) };
}

export function coolerKind(product) {
  const type = (product?.specs?.type || "").toLowerCase();
  if (product?.specs?.radiator_mm || type.includes("сжо") || type.includes("aio") || type.includes("liquid")) return "aio";
  if (type.includes("низк") || type.includes("low")) return "low";
  return "tower";
}

/** The model of a cooler: single or dual tower, a round or a flat low cooler, a round or a square pump. */
export function coolerModel(product) {
  const kind = coolerKind(product);
  const text = textOf(product);
  if (kind === "low") return /intel|laminar/.test(text) ? "cooler_flat" : "cooler_low";
  if (kind === "tower") return Number(product?.specs?.fans) >= 2 || /d15|assassin|phantom|dark rock pro|dual/.test(text) ? "cooler_dual" : "cooler_tower";
  return /liquid freezer|arctic/.test(text) ? "aio_pump_square" : "aio_pump";
}

/** RAM: tall with a light bar (RGB kits), low profile, or a plain thin spreader. */
export function ramModel(product) {
  const text = textOf(product);
  if (product?.specs?.rgb === true || /rgb/.test(text)) return "ram";
  if (/crucial|value|basics/.test(text)) return "ram_plain";
  return "ram_lp";
}

/** ATX power supplies are 140, 160 or 180 mm long, longer with more watts (the model is 160 mm). */
export const psuScale = (product) => {
  const watts = Number(product?.specs?.wattage) || 750;
  return (watts <= 650 ? 140 : watts <= 1000 ? 160 : 180) / 160;
};

/** NVMe drives with a heatsink of their own (spec heatsink, or the name says so). */
export const m2Model = (product) => (product?.specs?.heatsink === true || /heatsink|радиатор/i.test(product?.name || "") ? "m2_hs" : "m2");

/** The colour band on a drive's label by its series. */
function driveAccent(product) {
  const text = textOf(product);
  if (/ironwolf/.test(text)) return "#f08a24";
  if (/\bred\b/.test(text)) return "#c8102e";
  if (/barracuda/.test(text)) return "#2e9d5b";
  if (/toshiba|p300/.test(text)) return "#d7262c";
  if (/blue/.test(text)) return "#1c6fc4";
  if (/black/.test(text)) return "#e5e7ea";
  return null;
}

/** Heatsink colours of a board by its series: [heatsinks, accents]. */
function boardColors(product) {
  const text = textOf(product);
  if (/rog|strix/.test(text)) return [0x1a1c20, 0xa3a9b2];
  if (/tuf/.test(text)) return [0x3a3d41, 0xb39a4a];
  if (/aorus/.test(text)) return [0x1d1f23, 0xc3c8ce];
  if (/tomahawk|\bmag\b/.test(text)) return [0x44484e, 0x8f959d];
  if (/prime|\bpro\b|pro4|ds3h|a520m|h610m/.test(text)) return [0x9ba1a9, 0xd3d7dc];
  return null;
}

/** Keeps one of the variants (children named like names) and removes the others. */
function keepVariant(object, names, chosen) {
  const set = new Set(names);
  const drop = [];
  object.traverse((child) => {
    const base = baseName(child.name);
    if (set.has(base) && base !== chosen) drop.push(child);
  });
  for (const child of drop) child.removeFromParent();
}

/** The base size of a case model (inner depth D, height H, width W), from its "size" empty. */
function modelSize(caseObj) {
  const size = childNamed(caseObj, "size");
  return size ? { D: size.position.x, H: size.position.y, W: size.position.z } : { D: 450, H: 470, W: 200 };
}

/** The first object inside root with this name (without Blender's .001 suffix). */
function childNamed(root, name) {
  let found = null;
  root.traverse((child) => {
    if (!found && baseName(child.name) === name) found = child;
  });
  return found;
}

/** The largest radiator a case model takes (its empty radiator_max_<mm>). */
function modelRadiatorMax(caseObj) {
  let max = 360;
  caseObj.traverse((child) => {
    const m = child.name.match(/^radiator_max_(\d{3})/);
    if (m) max = Number(m[1]);
  });
  return max;
}

/** How much to stretch a case model (mm) to the product's outside size: only bigger, so every compatible
 *  part still fits (the model is the smallest case of its kind). The longest card and radiator it takes
 *  must fit too. */
export function caseStretch(product, base) {
  const s = product?.specs || {};
  const num = (v) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : 0);
  const radiator = num(s.max_radiator_mm);
  // without its own depth a case is made long enough for its biggest radiator on the top
  const D = Math.max(base.D, num(s.depth_mm) - 26, num(s.max_gpu_mm) + 38, !num(s.depth_mm) && radiator ? radiator + 96 : 0);
  const H = Math.max(base.H, num(s.height_mm));
  const W = Math.max(base.W, num(s.width_mm) - 2);
  // the top takes a 360 mm radiator only when the case is that long (else a 240 stands in for it)
  const fits = D >= 456 ? 360 : 240;
  return { dD: D - base.D, dH: H - base.H, dW: W - base.W, radiatorMax: Math.min(radiator || fits, fits) };
}

/**
 * Stretches a case object in place (its own copies of the geometry): the part in front of the split planes
 * moves to the front, the part above to the top, the open side outward. Fans, empties and other compact
 * pieces move whole; sheets that cross a split get longer.
 */
export function stretchCase(caseObj, { dD, dH, dW }) {
  if (!dD && !dH && !dW) return;
  const split = {};
  caseObj.traverse((child) => {
    if (child.name.startsWith("split_")) split[baseName(child.name)] = child.position;
  });
  const lowX = split.split_front_low?.x ?? 190;
  const highX = split.split_front_high?.x ?? 120;
  const splitY = split.split_front_low?.y ?? 126;
  const sideZ = split.split_side?.z ?? 185;
  const shift = (p, out) => out.set(p.x < (p.y < splitY ? lowX : highX) ? -dD : 0, p.y > splitY ? dH : 0, p.z > sideZ ? dW : 0);
  caseObj.updateMatrixWorld(true);
  const toCase = new THREE.Matrix4().copy(caseObj.matrixWorld).invert();
  const whole = (object) => object.name.startsWith("rotor_") || object.name.endsWith("_frame") || !object.isMesh && object.children.length === 0;
  const moved = new THREE.Vector3();
  const p = new THREE.Vector3();
  const visit = (object, insideWhole) => {
    for (const child of [...object.children]) {
      if (whole(child) && !insideWhole) {
        // by the middle of what it holds (a fan's frame has its origin at the case's corner)
        const box = new THREE.Box3().setFromObject(child);
        const at = (box.isEmpty() ? child.getWorldPosition(new THREE.Vector3()) : box.getCenter(new THREE.Vector3())).applyMatrix4(toCase);
        child.position.add(shift(at, moved));
        visit(child, true);
        continue;
      }
      if (child.isMesh && !insideWhole) {
        child.geometry = child.geometry.clone();
        const toLocal = new THREE.Matrix4().multiplyMatrices(toCase, child.matrixWorld);
        const back = toLocal.clone().invert();
        const pos = child.geometry.attributes.position;
        for (let i = 0; i < pos.count; i++) {
          p.fromBufferAttribute(pos, i).applyMatrix4(toLocal);
          p.add(shift(p, moved)).applyMatrix4(back);
          pos.setXYZ(i, p.x, p.y, p.z);
        }
        pos.needsUpdate = true;
        child.geometry.computeBoundingBox();
        child.geometry.computeBoundingSphere();
      }
      visit(child, insideWhole);
    }
  };
  visit(caseObj, false);
  caseObj.updateMatrixWorld(true);
}

/** A tower cooler's fin stack follows its height (spec height_mm, from the board); the fan stays where it
 *  clears the RAM. Base: the model's fins start 38 mm over the CPU and end 149 mm over it (158 from the board). */
export function stretchTower(object, heightMm) {
  const h = Number(heightMm);
  if (!Number.isFinite(h) || h <= 0) return;
  const z0 = 38;
  const s = (h - 9 - z0) / (149 - z0);
  if (Math.abs(s - 1) < 0.005) return;
  object.updateMatrixWorld(true);
  const toRoot = new THREE.Matrix4().copy(object.matrixWorld).invert();
  const p = new THREE.Vector3();
  object.traverse((child) => {
    if (!child.isMesh) return;
    let parent = child;
    while (parent && parent !== object) {
      if (parent.name.startsWith("rotor_") || parent.name.endsWith("_frame") || parent.name.endsWith("_clips")) return;
      parent = parent.parent;
    }
    child.geometry = child.geometry.clone();
    const toLocal = new THREE.Matrix4().multiplyMatrices(toRoot, child.matrixWorld);
    const back = toLocal.clone().invert();
    const pos = child.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      p.fromBufferAttribute(pos, i).applyMatrix4(toLocal);
      if (p.z > z0) p.z = z0 + (p.z - z0) * s;
      p.applyMatrix4(back);
      pos.setXYZ(i, p.x, p.y, p.z);
    }
    pos.needsUpdate = true;
    child.geometry.computeBoundingBox();
    child.geometry.computeBoundingSphere();
  });
}

/** Repaints the materials of a part by its colour (null: the model's own colours). */
function paint(materials, kind, color) {
  const c = COLORS[color];
  if (!c) return;
  const light = Boolean(c.light);
  const set = (material, hex, metal) => {
    material.color.set(hex);
    if (metal !== undefined) material.metalness = metal;
  };
  for (const material of materials) {
    const name = material.name || "";
    if (kind === "gpu") {
      if (name === "GPUShroud") set(material, c.hex, c.metal ?? (light ? 0.1 : 0.3));
      else if (name === "GPUBackplate") set(material, light ? 0xd9dce0 : c.hex, c.metal ?? (light ? 0.4 : 0.75));
      else if (light && (name === "FanBlade" || name === "FanFrame")) set(material, 0xeef0f2);
    } else if (kind === "ram" && name === "RAMSpreader") {
      set(material, c.hex, c.metal ?? (light ? 0.3 : 0.85));
    } else if (kind === "cooler") {
      if (color === "brown") {
        // Noctua: beige frames, brown blades
        if (name === "CoolerFanFrame") set(material, 0xd6c3a3);
        else if (name === "CoolerFanBlade") set(material, 0x6e4632);
        else if (name === "CoolerCover") set(material, 0x2b2420, 0.6);
      } else if (name === "CoolerFanFrame" || name === "CoolerFanBlade" || name === "CoolerCover") {
        set(material, c.hex, name === "CoolerCover" ? c.metal ?? (light ? 0.3 : 0.7) : undefined);
      }
    }
  }
}

// ---------------------------------------------------------------- hoses and cables

/** The hose from a pump fitting (a, it looks out of the open side) up to a radiator inlet (b, from below). */
export function hoseCurve(a, b) {
  return new THREE.CatmullRomCurve3([
    a, a.clone().add(new THREE.Vector3(4, 0, 26)),
    new THREE.Vector3(b.x - 8, a.y + 30, b.z - 30),
    b.clone().add(new THREE.Vector3(0, -28, 0)), b,
  ]);
}

/** The power cables: from a grommet in the case (a) to a socket (b). cols x rows wires of the plug,
 *  side: the axis along the plug's long side, out: where the plug looks from the socket. */
const CABLES = {
  "24pin": { cols: 12, rows: 2, side: [0, 1, 0], out: [-1, 0, 0] },
  eps: { cols: 4, rows: 2, side: [1, 0, 0], out: [0, 0, 1] },
  gpu: { cols: 8, rows: 2, side: [1, 0, 0], out: [0, 0, 1] },
};
const PITCH = 4.2;
const PLUG = 16;

/** The path of a cable's middle line, from the grommet a to the end of the plug on the socket b. */
export function cablePath(kind, a, b) {
  const { out } = CABLES[kind];
  const o = new THREE.Vector3(...out);
  const p = b.clone().addScaledVector(o, PLUG); // the end of the plug: the wires start here
  const v = (x, y, z) => new THREE.Vector3(x, y, z);
  if (kind === "24pin") {
    const reach = Math.max(14, (p.x - a.x) * 0.5);
    return [a, v(a.x, a.y, a.z + 9), v(a.x + reach * 0.6, a.y, p.z + 2), v(p.x - 6, p.y, p.z), p];
  }
  if (kind === "eps") {
    return [a, v(a.x, a.y, a.z + 10), v(a.x, a.y - 5, a.z + 32), v(p.x, p.y + 8, p.z + 9), v(p.x, p.y + 1, p.z + 7), p];
  }
  return [a, v(a.x, a.y + 16, a.z), v((a.x + p.x) / 2, (a.y + p.y) / 2 - 10, p.z + 10), v(p.x, p.y - 12, p.z + 11), v(p.x, p.y - 1, p.z + 8), p];
}

/** A sleeved cable: cols x rows round wires along the path, merged into one geometry, and its plug. */
export function cableGeometry(kind, a, b) {
  const { cols, rows, side, out } = CABLES[kind];
  const path = new THREE.CatmullRomCurve3(cablePath(kind, a, b), false, "centripetal");
  const n = 48;
  const hint = new THREE.Vector3(...side);
  const wires = [];
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const points = [];
      for (let k = 0; k <= n; k++) {
        const t = k / n;
        const at = path.getPointAt(t);
        const tangent = path.getTangentAt(t);
        const s = hint.clone().addScaledVector(tangent, -hint.dot(tangent)).normalize();
        const r = new THREE.Vector3().crossVectors(tangent, s);
        points.push(at.addScaledVector(s, (i - (cols - 1) / 2) * PITCH).addScaledVector(r, (j - (rows - 1) / 2) * PITCH));
      }
      const wire = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), n, PITCH * 0.46, 6);
      const length = path.getLength();
      const uv = wire.attributes.uv;
      for (let q = 0; q < uv.count; q++) uv.setX(q, uv.getX(q) * length / 3);
      wires.push(wire);
    }
  }
  const cable = mergeGeometries(wires);
  for (const wire of wires) wire.dispose();
  // the plug: a box from the socket outward
  const o = new THREE.Vector3(...out);
  const plug = new THREE.BoxGeometry(cols * PITCH + 2, rows * PITCH + 2.4, PLUG);
  const basis = new THREE.Matrix4().makeBasis(hint, new THREE.Vector3().crossVectors(o, hint), o);
  plug.applyMatrix4(basis).translate(...b.clone().addScaledVector(o, PLUG / 2).toArray());
  return { cable, plug };
}

/**
 * The view. Returns {node, update(build), highlight(slot), refit()}.
 * build: {case, motherboard, cpu, cooler, gpu, psu: product | null, ram, storage: product[], powered, problems: Set}
 * onPick(slot) — a part (or its empty place) was clicked.
 */
export function createCaseView({ onPick, loadingText, failedText, hintText }) {
  const node = document.createElement("div");
  node.className = "case-stage";
  const status = document.createElement("div");
  status.className = "case-status";
  status.textContent = loadingText(null);
  const hint = document.createElement("div");
  hint.className = "case-hint";
  hint.textContent = hintText;
  node.append(status, hint);

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  } catch {
    status.textContent = failedText;
    node.classList.add("failed");
    return { node, update() {}, highlight() {}, refit() {} };
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  node.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.6;

  const camera = new THREE.PerspectiveCamera(28, 1, 60, 6000); // a far near plane: fine depth, no flicker of insets
  const center = new THREE.Vector3(225, 225, 115);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(center);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.enableZoom = false; // the wheel and a vertical swipe scroll the page, not the case
  renderer.domElement.style.touchAction = "pan-y";
  controls.minDistance = 650;
  controls.maxDistance = 2100;
  controls.minPolarAngle = Math.PI * 0.18;
  controls.maxPolarAngle = Math.PI * 0.56;
  controls.minAzimuthAngle = -Math.PI * 0.62;
  controls.maxAzimuthAngle = Math.PI * 0.42;
  controls.rotateSpeed = 0.7;

  // light: a soft key from the front-left above, a cool rim from behind, a warm fill inside the case
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(-500, 1200, 1100);
  key.target.position.copy(center);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -500, right: 500, top: 500, bottom: -500, near: 200, far: 3500 });
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 1.2;
  key.shadow.radius = 4;
  // (from behind and low: it passes the walls, so it only touches the case's rear edges, not the parts' tops)
  const rim = new THREE.DirectionalLight(0xdfe6ff, 0.5);
  rim.position.set(1400, 200, -900);
  // the inside of the case is in the shadow of its own top: a soft light from the open side and one inside
  const fill = new THREE.DirectionalLight(0xffffff, 1.3);
  fill.position.set(300, 420, 1400);
  fill.target.position.copy(center);
  const inside = new THREE.PointLight(0xffffff, 1.1, 0, 0);
  inside.position.set(200, 380, 150);
  scene.add(key, key.target, rim, fill, fill.target, inside, new THREE.HemisphereLight(0xffffff, 0x445066, 0.6));

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.ShadowMaterial({ opacity: 0.22 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = 0.5;
  ground.receiveShadow = true;
  scene.add(ground);

  const world = new THREE.Group(); // the case and the parts
  scene.add(world);

  let lib = null;
  let caseObj = null;
  let template = null; // an invisible ATX board: mount points while no board is chosen
  const parts = new Map(); // key -> {group, slot, state, t0, from, materials, dispose}
  const ghosts = new Map(); // slot -> group
  let highlighted = null;
  let pending = null; // the last build given before the model loaded
  let powered = false;
  let powerLevel = 0; // 0..1, eased
  const glowing = []; // {material, kind}
  const pointer = { x: 0, y: 0, down: false, moved: false };
  let usedM2 = 0; // M.2 slots of the board with a drive in them: their heatsinks are hidden

  function fit() {
    const width = node.clientWidth || 600;
    const height = node.clientHeight || 480;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  /** The starting view: three quarters from the front, the whole case fits with a margin. */
  function homeCamera() {
    const direction = new THREE.Vector3(-0.62, 0.38, 1).normalize();
    const half = THREE.MathUtils.degToRad(camera.fov / 2);
    const byHeight = 350 / Math.tan(half);
    const byWidth = 360 / (Math.tan(half) * camera.aspect);
    camera.position.copy(center).addScaledVector(direction, Math.max(byHeight, byWidth));
    controls.update();
  }
  new ResizeObserver(fit).observe(node);

  /** A copy of a library object with its own materials (they fade and glow on their own). */
  function instance(name) {
    const source = lib.getObjectByName(name);
    const copy = source.clone(true);
    const materials = [];
    copy.traverse((child) => {
      if (!child.isMesh) return;
      child.castShadow = true;
      child.receiveShadow = true;
      child.material = child.material.clone();
      materials.push(child.material);
    });
    copy.position.set(0, 0, 0);
    copy.quaternion.identity();
    return { object: copy, materials };
  }

  function mountsOf(object) {
    const result = {};
    object.updateMatrixWorld(true);
    object.traverse((child) => {
      if (child.name.startsWith("mount_") || child.name.startsWith("hose_") || child.name.startsWith("cable_")) {
        result[baseName(child.name)] = child.getWorldPosition(new THREE.Vector3());
      }
    });
    return result;
  }

  function setLabel(object, text, sub, options) {
    object.traverse((child) => {
      if (child.isMesh && child.name.startsWith("label")) {
        child.material = new THREE.MeshStandardMaterial({ map: labelTexture(text, sub, options), roughness: 0.55, metalness: 0.1 });
      }
    });
  }

  function registerGlow(materials) {
    for (const material of materials) {
      const name = material.name || "";
      if (name === "RGB") material.color.set(0x3a3f48); // a milky diffuser: the light gives it the color
      if (name.startsWith("RGB")) glowing.push({ material, kind: "rgb" });
      else if (name.startsWith("LED")) glowing.push({ material, kind: "led" });
    }
  }

  /** Puts another case in (on the first load, when a case of another size, front or colour is chosen). */
  function setCase(product) {
    const name = caseModel(product);
    const front = frontOf(product);
    const sourceSize = modelSize(lib.getObjectByName(name));
    const stretch = caseStretch(product, sourceSize);
    const id = `${name}|${front}|${stretch.dD}|${stretch.dH}|${stretch.dW}`;
    if (caseObj?.userData.id === id) return;
    const old = caseObj;
    if (old) {
      old.removeFromParent();
      forget(old);
    }
    const made = instance(name);
    caseObj = made.object;
    caseObj.name = name;
    caseObj.userData.id = id;
    caseObj.userData.radiatorMax = stretch.radiatorMax || modelRadiatorMax(caseObj);
    stretchCase(caseObj, stretch);
    keepVariant(caseObj, ["front_mesh", "front_glass", "front_solid", "front_wood"], `front_${front}`);
    caseObj.traverse((child) => {
      if (child.isMesh && child.material.name === "CaseBody") (caseObj.userData.body ||= []).push(child.material);
      if (child.isMesh && child.material.name === "CaseInner") (caseObj.userData.inner ||= []).push(child.material);
    });
    registerGlow(made.materials);
    world.add(caseObj);
    if (old) caseObj.userData.bump = performance.now();
    // the view turns around the middle of the case
    const box = new THREE.Box3().setFromObject(caseObj);
    box.getCenter(center);
    center.y -= 10;
    // the empty places of the parts follow the case
    for (const ghost of ghosts.values()) ghost.removeFromParent();
    ghosts.clear();
    template = instance("board_atx").object;
    template.position.copy(mountsOf(caseObj).mount_board);
    world.add(template);
    template.visible = false;
    makeGhosts();
    template.removeFromParent();
  }

  /** Materials of a removed object stop glowing. */
  function forget(object) {
    const gone = new Set();
    object.traverse((child) => {
      if (child.isMesh) gone.add(child.material);
    });
    for (let i = glowing.length - 1; i >= 0; i--) if (gone.has(glowing[i].material)) glowing.splice(i, 1);
  }

  /** What the build needs in the case: one entry per piece, with a key that changes when it must be re-placed. */
  function plan(build) {
    const caseMounts = mountsOf(caseObj);
    const board = build.motherboard;
    const boardName = boardModel(board);
    const boardMounts = (() => {
      template.removeFromParent();
      const t = instance(boardName).object;
      t.position.copy(caseMounts.mount_board);
      world.add(t);
      const result = mountsOf(t);
      t.removeFromParent();
      return result;
    })();
    const list = [];
    const caseKey = caseObj.userData.id;
    const add = (slot, key, make) => list.push({ slot, key: `${key}-${caseKey}`, make });

    if (board) {
      add("motherboard", `board-${board.id}-${boardName}`, () => {
        const { object, materials } = instance(boardName);
        object.position.copy(caseMounts.mount_board);
        const colors = boardColors(board);
        for (const material of colors ? materials : []) {
          if (material.name === "BoardHeatsink") material.color.set(colors[0]);
          if (material.name === "BoardAccent") material.color.set(colors[1]);
        }
        return { objects: [object], materials };
      });
    }
    if (build.cpu) {
      add("cpu", `cpu-${build.cpu.id}-${boardName}`, () => {
        const { object, materials } = instance("cpu");
        object.position.copy(boardMounts.mount_cpu);
        return { objects: [object], materials };
      });
    }
    if (build.cooler) {
      const kind = coolerKind(build.cooler);
      const color = colorOf(build.cooler);
      add("cooler", `cooler-${build.cooler.id}-${boardName}`, () => {
        const model = coolerModel(build.cooler);
        if (kind !== "aio") {
          const { object, materials } = instance(model);
          object.position.copy(boardMounts.mount_cooler);
          if (kind === "tower") stretchTower(object, build.cooler.specs?.height_mm);
          paint(materials, "cooler", color);
          return { objects: [object], materials };
        }
        const pump = instance(model);
        pump.object.position.copy(boardMounts.mount_cooler);
        const want = (build.cooler.specs.radiator_mm || 240) >= 300 ? 360 : 240;
        const size = Math.min(want, caseObj.userData.radiatorMax >= 360 ? 360 : 240);
        const radiator = instance(`radiator_${size}`);
        radiator.object.position.copy(caseMounts.mount_radiator);
        // hoses: soft curves from the pump fittings out and up to the radiator
        const pumpEnds = mountsOf(pump.object);
        const radEnds = mountsOf(radiator.object);
        const hoseMaterial = new THREE.MeshStandardMaterial({ color: 0x111215, roughness: 0.55, metalness: 0.05 });
        const hoses = ["hose_a", "hose_b"].map((name) => {
          const hose = new THREE.Mesh(new THREE.TubeGeometry(hoseCurve(pumpEnds[name], radEnds[name]), 64, 5.2, 14), hoseMaterial);
          hose.castShadow = true;
          return hose;
        });
        const materials = [...pump.materials, ...radiator.materials, hoseMaterial];
        paint(materials, "cooler", color);
        return { objects: [pump.object, radiator.object, ...hoses], materials };
      });
    }
    // RAM: sticks fill the slots like a manual says (A2, B2 first)
    const sticks = build.ram.flatMap((product) => Array.from({ length: product.specs.sticks || 1 }, () => product));
    const slotCount = Object.keys(boardMounts).filter((name) => name.startsWith("mount_ram_")).length;
    const order = slotCount === 2 ? [1, 0] : sticks.length === 1 ? [1] : sticks.length === 2 ? [1, 3] : [1, 3, 0, 2];
    sticks.slice(0, slotCount).forEach((product, i) => {
      const slotIndex = order[i] ?? i;
      add("ram", `ram-${i}-${product.id}-${boardName}-${slotIndex}`, () => {
        const { object, materials } = instance(ramModel(product));
        object.position.copy(boardMounts[`mount_ram_${slotIndex}`]);
        setLabel(object, product.brand || "", "");
        paint(materials, "ram", colorOf(product));
        return { objects: [object], materials };
      });
    });
    let gpuCable = null; // the card's power socket, for the cable
    if (build.gpu) {
      const { name, scale, thick, style } = gpuPlan(build.gpu);
      const socket = childNamed(lib.getObjectByName(name), "cable_gpu")?.position;
      if (socket) gpuCable = boardMounts.mount_gpu.clone().add(new THREE.Vector3(socket.x * scale, socket.y * thick, socket.z));
      add("gpu", `gpu-${build.gpu.id}-${boardName}`, () => {
        const { object, materials } = instance(name);
        keepVariant(object, GPU_STYLES.map((st) => `style_${name}_${st}`), `style_${name}_${style}`);
        object.position.copy(boardMounts.mount_gpu);
        object.scale.set(scale, thick, 1);
        object.traverse((child) => {
          // fans stay round, the bracket and the contact keep their size
          if (child.name.startsWith("rotor_") || child.name.endsWith("_frame") || child.name.startsWith("fixed_")) child.scale.x = 1 / scale;
        });
        setLabel(object, build.gpu.brand || "", `${build.gpu.specs.vram_gb || ""} GB`);
        paint(materials, "gpu", colorOf(build.gpu));
        return { objects: [object], materials };
      });
    }
    if (build.psu) {
      add("psu", `psu-${build.psu.id}`, () => {
        const { object, materials } = instance("psu");
        object.position.copy(caseMounts.mount_psu);
        const scale = psuScale(build.psu);
        object.scale.x = scale;
        object.traverse((child) => {
          if (child.name.startsWith("fixed_")) child.scale.x = 1 / scale; // the fan stays round
        });
        setLabel(object, build.psu.brand || "", `${build.psu.specs.wattage} W`, { ratio: 2.2 });
        return { objects: [object], materials };
      });
    }
    // drives: NVMe on the board while it has M.2 slots, the rest (and SATA SSD, HDD) in the drive cage
    // (an NVMe drive there sits in a 2.5" enclosure)
    let m2 = 0;
    let bay = 0;
    build.storage.forEach((product, i) => {
      const nvme = (product.specs.type || "").toLowerCase().includes("nvme");
      const onBoard = nvme && boardMounts[`mount_m2_${m2}`];
      const mount = onBoard ? boardMounts[`mount_m2_${m2++}`] : caseMounts[`mount_drive_${bay++}`];
      if (!mount) return; // the case is full: the panel still lists the drive
      const model = onBoard ? m2Model(product) : (product.specs.type || "").toUpperCase().includes("HDD") ? "hdd" : "ssd";
      add("storage", `storage-${i}-${product.id}-${boardName}`, () => {
        const { object, materials } = instance(model);
        object.position.copy(mount);
        const size = product.specs.size_gb >= 1000 ? `${product.specs.size_gb / 1000} TB` : `${product.specs.size_gb} GB`;
        const ratio = model === "m2" ? 3.8 : model === "m2_hs" ? 1.1 : 1.4;
        setLabel(object, product.brand || "", size, { dark: model !== "hdd", ratio, accent: driveAccent(product) });
        return { objects: [object], materials };
      });
    });
    usedM2 = m2;
    // power cables: shown when both of their ends are in the case
    const sleeve = colorOf(build.case) === "white" ? 0xe9ebee : 0x17181b;
    const cable = (kind, a, b, key) => {
      if (!a || !b) return;
      add("cable", `cable-${kind}-${key}-${sleeve}`, () => {
        const { cable: geometry, plug } = cableGeometry(kind, a, b);
        const tex = textures();
        const material = new THREE.MeshStandardMaterial({ color: sleeve, roughness: 0.62, metalness: 0.05, bumpMap: tex?.braid, bumpScale: 0.6, name: "Sleeve" });
        const plugMaterial = new THREE.MeshStandardMaterial({ color: 0x0d0e10, roughness: 0.45, name: "Plug" });
        const meshes = [new THREE.Mesh(geometry, material), new THREE.Mesh(plug, plugMaterial)];
        for (const mesh of meshes) mesh.castShadow = mesh.receiveShadow = true;
        return { objects: meshes, materials: [material, plugMaterial], geometries: [geometry, plug] };
      });
    };
    if (build.psu && board) {
      cable("24pin", caseMounts.cable_24pin, boardMounts.cable_24pin, `${board.id}-${boardName}`);
      cable("eps", caseMounts.cable_eps, boardMounts.cable_eps, `${board.id}-${boardName}`);
    }
    if (build.psu && gpuCable) cable("gpu", caseMounts.cable_gpu, gpuCable, `${build.gpu.id}-${boardName}`);
    return list;
  }

  function flyIn(entry, delay) {
    const made = entry.make();
    const group = new THREE.Group();
    for (const object of made.objects) group.add(object);
    group.userData.slot = entry.slot === "cable" ? "psu" : entry.slot; // a click on a cable opens the PSUs
    world.add(group);
    for (const material of made.materials) {
      material.userData.opaque = !material.transparent;
      material.transparent = true;
      material.opacity = 0;
    }
    registerGlow(made.materials);
    const record = {
      group, slot: entry.slot, materials: made.materials, geometries: made.geometries || [],
      state: "in", t0: performance.now() + delay, from: new THREE.Vector3(...FROM[entry.slot]),
    };
    group.position.copy(record.from);
    parts.set(entry.key, record);
  }

  function flyOut(key, record) {
    record.state = "out";
    record.t0 = performance.now();
    for (const material of record.materials) material.transparent = true;
    parts.delete(key);
    parts.set(`${key}#out${record.t0}`, record);
  }

  /** The heatsinks over the board's M.2 slots: hidden where a drive sits. */
  function refreshShields() {
    for (const record of parts.values()) {
      if (record.slot !== "motherboard" || record.state === "out") continue;
      record.group.traverse((child) => {
        const m = baseName(child.name).match(/^m2shield_(\d)/);
        if (m) child.visible = Number(m[1]) >= usedM2;
      });
    }
  }

  function update(build) {
    if (!lib) {
      pending = build;
      return;
    }
    setCase(build.case);
    // the case itself: primer grey while no case is chosen, painted in its colour when it is
    const color = COLORS[colorOf(build.case)] || COLORS.black;
    const paintHex = build.case ? color.hex : 0x8a9099;
    for (const material of caseObj.userData.body || []) {
      material.color.set(paintHex);
      material.metalness = color.metal ?? 0.2;
    }
    for (const material of caseObj.userData.inner || []) material.color.set(paintHex).multiplyScalar(color.light ? 0.92 : 0.82);
    if (build.case && caseObj.userData.caseId !== build.case.id && caseObj.userData.caseId !== undefined) {
      caseObj.userData.bump = performance.now();
    }
    caseObj.userData.caseId = build.case?.id ?? null;

    const wanted = plan(build);
    const keys = new Set(wanted.map((entry) => entry.key));
    for (const [key, record] of [...parts]) {
      if (record.state !== "out" && !keys.has(key)) flyOut(key, record);
    }
    const fresh = wanted.filter((entry) => !parts.has(entry.key));
    fresh.sort((a, b) => ORDER.indexOf(a.slot) - ORDER.indexOf(b.slot));
    // a part that only moved (another board) comes after the one it sits on
    fresh.forEach((entry, i) => flyIn(entry, reduceMotion ? 0 : i * (fresh.length > 2 ? STAGGER : 90) + 60));
    refreshShields();

    // what is in the case now, readable from the page (checks, tests): "case_atx motherboard:1 ram:2 …"
    const count = {};
    for (const entry of wanted) if (entry.slot !== "cable") count[entry.slot] = (count[entry.slot] || 0) + 1;
    node.dataset.parts = [caseObj.name, ...Object.entries(count).map(([slot, n]) => `${slot}:${n}`)].join(" ");

    powered = Boolean(build.powered);
    for (const record of parts.values()) if (record.state !== "out") record.problem = build.problems?.has(record.slot);
    refreshGhost();
  }

  /** The place of a missing part glows softly while its section is open or under the mouse. */
  function refreshGhost() {
    for (const [slot, ghost] of ghosts) ghost.visible = slot === highlighted && ![...parts.values()].some((r) => r.slot === slot && r.state !== "out");
  }

  function makeGhosts() {
    const caseMounts = mountsOf(caseObj);
    const boardMounts = mountsOf(template);
    const ghostMaterial = new THREE.MeshBasicMaterial({ color: 0x6c8cff, transparent: true, opacity: 0.25, depthWrite: false });
    const place = (slot, name, position) => {
      const object = lib.getObjectByName(name).clone(true);
      object.position.copy(position);
      object.traverse((child) => {
        if (child.isMesh) child.material = ghostMaterial;
        if (baseName(child.name).startsWith("m2shield_")) child.visible = false;
      });
      const group = new THREE.Group();
      group.add(object);
      group.visible = false;
      group.userData.slot = slot;
      world.add(group);
      ghosts.set(slot, group);
    };
    place("motherboard", "board_atx", caseMounts.mount_board);
    place("cpu", "cpu", boardMounts.mount_cpu);
    place("cooler", "cooler_tower", boardMounts.mount_cooler);
    place("ram", "ram", boardMounts.mount_ram_1);
    place("gpu", "gpu2", boardMounts.mount_gpu);
    place("psu", "psu", caseMounts.mount_psu);
    place("storage", "m2", boardMounts.mount_m2_0);
    ghosts.material = ghostMaterial;
  }

  function highlight(slot) {
    highlighted = slot;
    if (lib) refreshGhost();
  }

  // clicks on parts: a click (not a drag) opens the section of what was clicked
  const raycaster = new THREE.Raycaster();
  renderer.domElement.addEventListener("pointerdown", (event) => {
    Object.assign(pointer, { x: event.clientX, y: event.clientY, down: true, moved: false });
    node.classList.add("grabbing");
  });
  renderer.domElement.addEventListener("pointermove", (event) => {
    if (pointer.down && Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > 5) pointer.moved = true;
    if (!pointer.down && lib) node.classList.toggle("pointing", Boolean(slotAt(event)));
  });
  addEventListener("pointerup", () => {
    pointer.down = false;
    node.classList.remove("grabbing");
  });
  renderer.domElement.addEventListener("click", (event) => {
    if (pointer.moved || !lib) return;
    const slot = slotAt(event);
    if (slot) onPick(slot);
  });
  function slotAt(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const targets = [...[...parts.values()].filter((r) => r.state !== "out").map((r) => r.group), ...[...ghosts.values()].filter((g) => g.visible)];
    const hit = raycaster.intersectObjects(targets, true).find((h) => h.object.visible);
    let object = hit?.object;
    while (object && !object.userData.slot) object = object.parent;
    return object?.userData.slot || null;
  }

  // the red outline of parts that don't fit: the back faces of every mesh, pushed out along the normals
  const outlineMaterial = new THREE.MeshBasicMaterial({ color: 0xff3b3b, side: THREE.BackSide, transparent: true, depthWrite: false, toneMapped: false });
  outlineMaterial.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\n  transformed += normalize(normal) * 1.4;");
  };
  // small parts spread over a board would give red specks: only the big shapes get the outline
  const NO_OUTLINE = new Set(["SMD", "Chip", "Header", "Gold", "Slot", "SlotLatch", "AudioCap", "Choke", "Nickel", "LabelDark", "LabelLight", "Sleeve", "Plug", "RGB", "LEDPower"]);
  function addOutline(group) {
    const meshes = [];
    group.traverse((child) => {
      if (child.isMesh && child.visible && !child.name.startsWith("label") && !NO_OUTLINE.has(child.material.name)) meshes.push(child);
    });
    return meshes.map((mesh) => {
      const shell = new THREE.Mesh(mesh.geometry, outlineMaterial);
      shell.raycast = () => {};
      mesh.add(shell);
      return shell;
    });
  }

  const clock = new THREE.Clock();
  function frame() {
    if (!node.isConnected) {
      dispose();
      return;
    }
    const dt = Math.min(clock.getDelta(), 0.05);
    const now = performance.now();
    controls.target.lerp(center, Math.min(1, dt * 4)); // a case of another size: the view glides to its middle
    controls.update();

    for (const [key, record] of parts) {
      const t = clamp01((now - record.t0) / (record.state === "out" ? FLY_OUT : FLY_IN));
      if (record.state === "in") {
        const e = reduceMotion ? 1 : easeOutBack(t);
        record.group.position.copy(record.from).multiplyScalar(1 - e);
        record.group.rotation.x = (1 - e) * -0.18;
        record.group.rotation.y = (1 - e) * 0.12;
        const alpha = reduceMotion ? 1 : clamp01(t * 2.6);
        for (const material of record.materials) material.opacity = alpha;
        if (t >= 1) {
          record.state = "idle";
          for (const material of record.materials) if (material.userData.opaque) material.transparent = false;
          record.landed = now;
        }
      } else if (record.state === "out") {
        const e = easeInCubic(t);
        record.group.position.copy(record.from).multiplyScalar(e);
        for (const material of record.materials) material.opacity = 1 - t;
        if (t >= 1) {
          record.group.removeFromParent();
          forget(record.group);
          for (const material of record.materials) {
            if (material.map?.userData.own) material.map.dispose();
            material.dispose();
          }
          for (const geometry of record.geometries) geometry.dispose();
          parts.delete(key);
        }
      }
      // a short flash of the accent when a part clicks into place
      const flash = record.landed ? clamp01(1 - (now - record.landed) / 600) : 0;
      if (record.state !== "out" && (flash > 0 || record.flashing)) {
        record.flashing = flash > 0;
        for (const material of record.materials) {
          if (!material.emissive || material.name.startsWith("RGB") || material.name.startsWith("LED")) continue;
          material.emissive.setRGB(0.05 * flash, 0.09 * flash, 0.25 * flash);
        }
      }
      // a part that doesn't fit: a red outline around it (the part itself keeps its look)
      const outlined = Boolean(record.problem) && record.state !== "out";
      if (outlined && !record.outline) record.outline = addOutline(record.group);
      if (record.outline && record.outlined !== outlined) {
        record.outlined = outlined;
        for (const shell of record.outline) shell.visible = outlined;
      }
    }
    outlineMaterial.opacity = 0.55 + 0.35 * Math.sin(now / 260);

    // power: fans speed up, RGB fades in and slowly shifts its hue
    powerLevel += ((powered ? 1 : 0) - powerLevel) * Math.min(1, dt * 1.8);
    const hue = (now / 9000) % 1;
    for (let i = glowing.length - 1; i >= 0; i--) {
      const { material, kind } = glowing[i];
      if (!material.emissive) continue;
      if (kind === "led") material.emissive.setHSL(0.58, 0.9, 0.55 * powerLevel);
      else material.emissive.setHSL((hue + i * 0.004) % 1, 0.95, 0.55 * powerLevel);
      material.emissiveIntensity = material.name === "RGB" ? 2.6 : 1.2;
    }
    const spin = (0.4 + powerLevel * 22) * dt;
    world.traverse((child) => {
      if (child.name.startsWith("rotor_")) child.rotateY(powerLevel > 0.02 ? spin : 0);
    });
    inside.color.setHSL(hue, 0.08 * powerLevel, 0.9); // a faint tint of the RGB on the parts

    // a new case "settles" with a small bounce
    if (caseObj?.userData.bump) {
      const t = clamp01((now - caseObj.userData.bump) / 700);
      caseObj.scale.setScalar(1 - 0.025 * Math.sin(t * Math.PI) * (1 - t));
    }
    if (ghosts.material) ghosts.material.opacity = 0.16 + 0.12 * Math.sin(now / 280);
    renderer.render(scene, camera);
  }

  function dispose() {
    renderer.setAnimationLoop(null);
    controls.dispose();
    pmrem.dispose();
    renderer.dispose();
  }

  fit();
  homeCamera();
  renderer.setAnimationLoop(frame);

  loadLibrary((share) => {
    status.textContent = loadingText(Math.round(share * 100));
  }).then(
    (scene3d) => {
      lib = scene3d;
      setCase(pending?.case);
      controls.target.copy(center);
      status.remove();
      node.classList.add("ready");
      fit();
      homeCamera();
      if (pending) update(pending);
    },
    () => {
      status.textContent = failedText;
      node.classList.add("failed");
    },
  );

  node.__view = { camera, controls, scene }; // for checks: scripts set exact angles, look at the scene
  return { node, update, highlight, refit: fit };
}
