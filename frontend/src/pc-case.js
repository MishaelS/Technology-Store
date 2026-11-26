// 3D case of the PC builder (three.js). The models come from Blender: backend/scripts/make_builder_models.py
// → resources/models/builder.glb. Every part of the build is cloned from that file and put on its mount point
// (empties named mount_* in the case and the motherboard), so positions live in one place — the Blender script.
//
// The build changes → the parts that left fly out, the new ones fly into their place one after another
// (the order of a real assembly), with a soft overshoot at the end. When the build is complete and compatible
// it "powers on": fans spin, RGB and the power LED glow.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

// ?v=: browsers that kept the first version for a day (it was cached then) take the new one
const MODEL_URL = "/resources/models/builder.glb?v=2";
const ORDER = ["motherboard", "cpu", "cooler", "ram", "psu", "gpu", "storage"]; // assembly order: stagger of fly-ins
const FLY_IN = 900; // ms
const FLY_OUT = 450;
const STAGGER = 170;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// where a part comes from, relative to its place (mm; +z = out of the open side, +y = up)
const FROM = {
  motherboard: [0, 40, 420],
  cpu: [0, 60, 160],
  cooler: [0, 90, 320],
  ram: [0, 0, 190],
  gpu: [-60, 0, 360],
  psu: [0, 0, 380],
  storage: [0, 0, 300],
};

let library = null;
/** The glTF file is loaded once per visit; progress(share 0..1) while it comes. */
function loadLibrary(progress) {
  library ||= new GLTFLoader().loadAsync(MODEL_URL, (event) => {
    // a gzipped answer has no length: then only the text, without a percent
    if (event.lengthComputable && event.total) progress(event.loaded / event.total);
  }).then((gltf) => gltf.scene);
  return library;
}

const easeOutBack = (t) => {
  const c = 1.25;
  return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2;
};
const easeInCubic = (t) => t * t * t;
const clamp01 = (t) => Math.min(1, Math.max(0, t));

/** Picture of a label: brand big, a second line small (PSU wattage, drive size). */
function labelTexture(text, sub = "", { dark = true, ratio = 3 } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = Math.round(512 / ratio);
  const g = canvas.getContext("2d");
  g.fillStyle = dark ? "#16181c" : "#eceff3";
  g.fillRect(0, 0, canvas.width, canvas.height);
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
  return texture;
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
  scene.environmentIntensity = 0.85;

  const camera = new THREE.PerspectiveCamera(28, 1, 10, 8000);
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
  const rim = new THREE.DirectionalLight(0xb8c8ff, 1.1);
  rim.position.set(1400, 700, -600);
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
      if (child.name.startsWith("mount_") || child.name.startsWith("hose_")) {
        // Blender keeps names unique: the second case's "mount_board" is "mount_board.001" ("mount_board001" here)
        result[child.name.replace(/\.?\d{3}$/, "")] = child.getWorldPosition(new THREE.Vector3());
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

  const boardModel = (product) => ({ ATX: "board_atx", mATX: "board_matx", "Mini-ITX": "board_itx" })[product?.specs?.form_factor] || "board_atx";
  const gpuModel = (length) => (length < 205 ? ["gpu1", 175] : length < 275 ? ["gpu2", 240] : ["gpu3", 310]);
  const coolerKind = (product) => {
    const type = (product?.specs?.type || "").toLowerCase();
    if (product?.specs?.radiator_mm || type.includes("сжо") || type.includes("aio") || type.includes("liquid")) return "aio";
    if (type.includes("низк") || type.includes("low")) return "low";
    return "tower";
  };

  /** The case model by the boards it takes: the biggest one decides. */
  const caseModel = (product) => {
    const sizes = product?.specs?.form_factors || ["ATX"];
    return sizes.includes("ATX") ? "case_atx" : sizes.includes("mATX") ? "case_matx" : "case_itx";
  };

  /** Puts another case model in (on the first load and when a case of another size is chosen). */
  function setCase(name) {
    if (caseObj?.name === name) return;
    const old = caseObj;
    if (old) {
      old.removeFromParent();
      forget(old);
    }
    const made = instance(name);
    caseObj = made.object;
    caseObj.name = name;
    caseObj.traverse((child) => {
      if (child.isMesh && child.material.name === "CaseBody") caseObj.userData.body = child.material;
      if (child.isMesh && child.material.name === "CaseInner") caseObj.userData.inner = child.material;
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
    const add = (slot, key, make) => list.push({ slot, key: `${key}-${caseObj.name}`, make });

    if (board) {
      add("motherboard", `board-${board.id}-${boardName}`, () => {
        const { object, materials } = instance(boardName);
        object.position.copy(caseMounts.mount_board);
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
      add("cooler", `cooler-${build.cooler.id}-${boardName}`, () => {
        if (kind !== "aio") {
          const { object, materials } = instance(kind === "low" ? "cooler_low" : "cooler_tower");
          object.position.copy(boardMounts.mount_cooler);
          return { objects: [object], materials };
        }
        const pump = instance("aio_pump");
        pump.object.position.copy(boardMounts.mount_cooler);
        const size = (build.cooler.specs.radiator_mm || 240) >= 300 ? 360 : 240;
        const radiator = instance(`radiator_${size}`);
        radiator.object.position.copy(caseMounts.mount_radiator);
        // hoses: soft curves from the pump fittings up to the radiator
        const pumpEnds = mountsOf(pump.object);
        const radEnds = mountsOf(radiator.object);
        const hoseMaterial = new THREE.MeshStandardMaterial({ color: 0x111215, roughness: 0.55, metalness: 0.05 });
        const hoses = ["hose_a", "hose_b"].map((name) => {
          const a = pumpEnds[name];
          const b = radEnds[name];
          const curve = new THREE.CatmullRomCurve3([
            a, a.clone().add(new THREE.Vector3(38, 10, 4)),
            new THREE.Vector3(b.x - 20, (a.y + b.y) / 2 + 30, (a.z + b.z) / 2 + 6),
            b.clone().add(new THREE.Vector3(0, -30, 0)), b,
          ]);
          const hose = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 5.2, 14), hoseMaterial);
          hose.castShadow = true;
          return hose;
        });
        return { objects: [pump.object, radiator.object, ...hoses], materials: [...pump.materials, ...radiator.materials, hoseMaterial] };
      });
    }
    // RAM: sticks fill the slots like a manual says (A2, B2 first)
    const sticks = build.ram.flatMap((product) => Array.from({ length: product.specs.sticks || 1 }, () => product));
    const slotCount = Object.keys(boardMounts).filter((name) => name.startsWith("mount_ram_")).length;
    const order = slotCount === 2 ? [1, 0] : sticks.length === 1 ? [1] : sticks.length === 2 ? [1, 3] : [1, 3, 0, 2];
    sticks.slice(0, slotCount).forEach((product, i) => {
      const slotIndex = order[i] ?? i;
      add("ram", `ram-${i}-${product.id}-${boardName}-${slotIndex}`, () => {
        const { object, materials } = instance("ram");
        object.position.copy(boardMounts[`mount_ram_${slotIndex}`]);
        setLabel(object, product.brand || "", "");
        return { objects: [object], materials };
      });
    });
    if (build.gpu) {
      const length = build.gpu.specs.length_mm || 250;
      const [name, base] = gpuModel(length);
      add("gpu", `gpu-${build.gpu.id}-${boardName}`, () => {
        const { object, materials } = instance(name);
        object.position.copy(boardMounts.mount_gpu);
        const scale = length / base;
        object.scale.x = scale;
        object.traverse((child) => {
          if (child.name.startsWith("rotor_") || child.name.endsWith("_frame")) {
            child.scale.x = 1 / scale; // fans stay round
          }
        });
        setLabel(object, build.gpu.brand || "", `${build.gpu.specs.vram_gb || ""} GB`);
        return { objects: [object], materials };
      });
    }
    if (build.psu) {
      add("psu", `psu-${build.psu.id}`, () => {
        const { object, materials } = instance("psu");
        object.position.copy(caseMounts.mount_psu);
        setLabel(object, build.psu.brand || "", `${build.psu.specs.wattage} W`, { ratio: 2.2 });
        return { objects: [object], materials };
      });
    }
    // drives: NVMe on the board while it has M.2 slots, the rest (and SATA SSD, HDD) in the drive cage
    let m2 = 0;
    let bay = 0;
    build.storage.forEach((product, i) => {
      const nvme = (product.specs.type || "").toLowerCase().includes("nvme");
      const onBoard = nvme && boardMounts[`mount_m2_${m2}`];
      const mount = onBoard ? boardMounts[`mount_m2_${m2++}`] : caseMounts[`mount_drive_${bay++}`];
      if (!mount) return; // the case is full: the panel still lists the drive
      const model = nvme ? "m2" : (product.specs.type || "").toUpperCase().includes("HDD") ? "hdd" : "ssd";
      add("storage", `storage-${i}-${product.id}-${boardName}`, () => {
        const { object, materials } = instance(model);
        object.position.copy(mount);
        const size = product.specs.size_gb >= 1000 ? `${product.specs.size_gb / 1000} TB` : `${product.specs.size_gb} GB`;
        setLabel(object, product.brand || "", size, { dark: model !== "hdd", ratio: model === "m2" ? 3.8 : 1.4 });
        return { objects: [object], materials };
      });
    });
    return list;
  }

  function flyIn(entry, delay) {
    const made = entry.make();
    const group = new THREE.Group();
    for (const object of made.objects) group.add(object);
    group.userData.slot = entry.slot;
    world.add(group);
    for (const material of made.materials) {
      material.userData.opaque = !material.transparent;
      material.transparent = true;
      material.opacity = 0;
    }
    registerGlow(made.materials);
    const record = { group, slot: entry.slot, materials: made.materials, state: "in", t0: performance.now() + delay, from: new THREE.Vector3(...FROM[entry.slot]) };
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

  function update(build) {
    if (!lib) {
      pending = build;
      return;
    }
    setCase(caseModel(build.case));
    // the case itself: primer grey while no case is chosen, painted when it is
    const body = caseObj.userData.body;
    const paint = build.case ? (/(white|snow|бел)/i.test(build.case.name) ? 0xe6e9ed : 0x2a2e35) : 0x8a9099;
    body?.color.set(paint);
    caseObj.userData.inner?.color.set(paint).multiplyScalar(0.82);
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

    // what is in the case now, readable from the page (checks, tests): "case_atx motherboard:1 ram:2 …"
    const count = {};
    for (const entry of wanted) count[entry.slot] = (count[entry.slot] || 0) + 1;
    node.dataset.parts = [caseObj.name, ...Object.entries(count).map(([slot, n]) => `${slot}:${n}`)].join(" ");

    powered = Boolean(build.powered);
    for (const [slot, record] of parts) if (record.state !== "out") record.problem = build.problems?.has(record.slot);
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
    const hit = raycaster.intersectObjects(targets, true)[0];
    let object = hit?.object;
    while (object && !object.userData.slot) object = object.parent;
    return object?.userData.slot || (hit ? null : null);
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
            material.map?.dispose();
            material.dispose();
          }
          parts.delete(key);
        }
      }
      // a short flash of the accent when a part clicks into place, red while it doesn't fit
      const flash = record.landed ? clamp01(1 - (now - record.landed) / 600) : 0;
      if (record.state !== "out") {
        for (const material of record.materials) {
          if (!material.emissive || material.name.startsWith("RGB") || material.name.startsWith("LED")) continue;
          if (record.problem) material.emissive.setRGB(0.16 + 0.08 * Math.sin(now / 320), 0.01, 0.01); // a soft red pulse
          else material.emissive.setRGB(0.05 * flash, 0.09 * flash, 0.25 * flash);
        }
      }
    }

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
      setCase(caseModel(pending?.case));
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

  return { node, update, highlight, refit: fit };
}
