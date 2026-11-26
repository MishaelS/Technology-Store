"""3D models of the PC builder: the case and every part, built in Blender and saved as one glTF file.

Run from the repository root (Blender 4.2+ is enough, no add-ons):
    blender -b -P backend/scripts/make_builder_models.py
    ./run.sh models                      (the same, finds Blender by itself)

Result: resources/models/builder.glb. frontend/src/pc-case.js loads it and puts the parts into the case.

Units are millimetres, axes as the parts sit in the case (Blender, Z up):
    X — from the front of the case to the rear, Z — up, Y — from the open side (-W) to the motherboard tray (0).
glTF turns it into Y up, so in the browser the open side looks at +Z.

Every part is a top-level object named like "gpu3" or "board_atx" with its origin at its mount point.
Objects inside a part:
    mount_*   empties: where other parts go (the board's CPU socket, RAM slots, PCIe slot...)
    cable_*   empties: the ends of the power cables (a grommet in the case, a socket on the board or the card)
    rotor*    fan blades: the site spins them around their own Y axis (Blender Z) when the build is powered on
    label*    flat panels with UVs: the site paints the brand / wattage on them
    fixed_*   pieces of a graphics card that keep their size when the site stretches the card (bracket, contact)
    m2shield_<n>  the heatsink over an empty M.2 slot: the site hides it when a drive sits there
Materials named RGB* glow and change color on the site; LED* light up when the build is powered on.
Every face gets UVs in millimetres / 100 (a box projection), so the site can put tiling textures on them
(perforated mesh, brushed metal, PCB traces).

The layout keeps the parts apart in every build the shop calls compatible: the sizes below are chosen so
that the longest card a case takes, any cooler, four RAM sticks and the drives never touch each other.
"""

import math
import os
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BUILDER_GLB") or ROOT / "resources" / "models" / "builder.glb")
DRACO = os.environ.get("BUILDER_DRACO", "1") != "0"   # compressed meshes (the site has the decoder); 0: plain, for checks

# ---------------------------------------------------------------- case sheets, mm (sizes: CASES below)
T = 2.0                            # steel sheet
FLOOR = 22.0                       # inner floor: feet + bottom sheet
SHROUD = 92.0                      # top of the PSU shroud above the floor
IO_HOLE = (-0.6, -44.6, 8.0, -151.0)   # the IO shield on the board: y from, y to, z from, z to (from the board's corner)
SPLIT_Z = 126.0                    # the site stretches the case's height above this level (over the drive cage)
BOARD_X = 8.0                      # the board's rear edge: this far from the outer rear face
UV_MM = 100.0                      # 1 UV unit = 100 mm

# ---------------------------------------------------------------- materials

MATS: dict[str, bpy.types.Material] = {}


def mat(name, color, metal=0.0, rough=0.5, emit=None, strength=0.0, coat=0.0, alpha=1.0, double=False):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    if getattr(m, "node_tree", None) is None:
        m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    srgb = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)  # node colors are linear
    p.inputs["Base Color"].default_value = (*srgb, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    if coat and "Coat Weight" in p.inputs:
        p.inputs["Coat Weight"].default_value = coat
    if emit:
        e = tuple(int(emit[i:i + 2], 16) / 255 for i in (1, 3, 5))
        p.inputs["Emission Color"].default_value = (*e, 1)
        p.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND" if hasattr(m, "blend_method") else None
    m.use_backface_culling = not double
    m.diffuse_color = (*srgb, alpha)
    MATS[name] = m
    return m


def materials():
    return {
        "steel": mat("CaseBody", "#22252B", metal=0.35, rough=0.42),
        "steel_in": mat("CaseInner", "#1A1C21", metal=0.3, rough=0.55),
        "mesh": mat("CaseMesh", "#0E0F12", metal=0.5, rough=0.4, double=True),       # the site punches holes in it
        "accent": mat("CaseAccent", "#3A3F48", metal=0.8, rough=0.25),
        "rubber": mat("Rubber", "#101114", rough=0.85),
        "pcb": mat("PCB", "#20252D", rough=0.45, coat=0.3),
        "pcb_green": mat("PCBGreen", "#0F3B2A", rough=0.5, coat=0.3),
        "slot": mat("Slot", "#2A2D33", rough=0.6),
        "latch": mat("SlotLatch", "#7D848E", rough=0.45),
        "slot_steel": mat("SlotSteel", "#B9BEC6", metal=1.0, rough=0.22),
        "alu": mat("Aluminium", "#A7AEB8", metal=1.0, rough=0.3),
        "alu_dark": mat("AluminiumDark", "#3B4048", metal=0.9, rough=0.32),
        "black_metal": mat("BlackMetal", "#17191D", metal=0.7, rough=0.35),
        "copper": mat("Copper", "#C9774A", metal=1.0, rough=0.25),
        "nickel": mat("Nickel", "#D4D8DE", metal=1.0, rough=0.16),
        "gold": mat("Gold", "#D9A441", metal=1.0, rough=0.25),
        "chip": mat("Chip", "#0B0C0E", rough=0.35),
        "smd": mat("SMD", "#4A4038", rough=0.5),
        "choke": mat("Choke", "#2C2F35", metal=0.4, rough=0.5),
        "audio_cap": mat("AudioCap", "#C9A43C", metal=0.3, rough=0.35),
        "header": mat("Header", "#E3E5E8", rough=0.5),
        "plastic": mat("Plastic", "#1C1E22", rough=0.45),
        "plastic_grey": mat("PlasticGrey", "#5A606A", rough=0.45),
        "white": mat("White", "#E9ECEF", rough=0.4),
        "shroud": mat("GPUShroud", "#1D2025", metal=0.3, rough=0.38),
        "shroud_accent": mat("GPUAccent", "#6A717C", metal=0.9, rough=0.26),
        "fan_frame": mat("FanFrame", "#16181C", rough=0.5),
        "fan_cap": mat("FanCap", "#30343B", metal=0.75, rough=0.22),
        "fan_blade": mat("FanBlade", "#1F2228", rough=0.35, double=True),
        "fan_blade_clear": mat("RGBFanBlade", "#C8D0DA", rough=0.2, emit="#7C9CFF", strength=0.0, double=True),
        "rgb": mat("RGB", "#E6ECF5", rough=0.3, emit="#7C9CFF", strength=0.0),
        "led": mat("LEDPower", "#2C3038", rough=0.3, emit="#4DABF7", strength=0.0),
        "label": mat("LabelDark", "#1A1D22", rough=0.5),
        "label_light": mat("LabelLight", "#EDEFF2", rough=0.45),
        "cable": mat("Cable", "#101113", rough=0.6),
        "glass": mat("Glass", "#0B0D10", metal=0.0, rough=0.05, coat=1.0),
        "mirror": mat("Mirror", "#E6E9ED", metal=1.0, rough=0.05),
        "grill": mat("PSUGrill", "#141619", metal=0.6, rough=0.4, double=True),    # the site punches hexagons in it
        "glass_tint": mat("GlassTint", "#1A1F26", metal=0.0, rough=0.04, alpha=0.35),  # see-through on the site
        "glass_side": mat("GlassSide", "#C8D2DC", metal=0.0, rough=0.02, alpha=0.08),
        "wood": mat("Wood", "#8A5A35", rough=0.62),                                  # the site gives it grain
        # parts the site repaints by the product's colour
        "gpu_back": mat("GPUBackplate", "#1B1D21", metal=0.75, rough=0.32),
        "ram_spreader": mat("RAMSpreader", "#30343B", metal=0.85, rough=0.3),
        "cooler_cover": mat("CoolerCover", "#17191D", metal=0.7, rough=0.3),
        "cooler_fan": mat("CoolerFanFrame", "#16181C", rough=0.5),
        "cooler_blade": mat("CoolerFanBlade", "#1F2228", rough=0.35, double=True),
        "fins_u": mat("FinsU", "#AEB5BF", metal=1.0, rough=0.35),     # fin stacks: the site draws the fins
        "fins_v": mat("FinsV", "#AEB5BF", metal=1.0, rough=0.35),     # (stripes along u / along v of the UVs)
        "board_hs": mat("BoardHeatsink", "#2E3238", metal=0.9, rough=0.3),
        "board_accent": mat("BoardAccent", "#7A818C", metal=0.9, rough=0.24),
    }


# ---------------------------------------------------------------- geometry helpers


def rrect(w, h, r, n=4, cx=0.0, cy=0.0):
    """Points of a rounded rectangle (w x h, corner radius r, n points per corner), counter-clockwise."""
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        a0 = k * math.pi / 2
        ox, oy = cx + sx * (w / 2 - r), cy + sy * (h / 2 - r)
        for i in range(n + 1):
            a = a0 + (math.pi / 2) * i / n
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return pts


def chamfered(x0, y0, x1, y1, c):
    """Points of a rectangle with its four corners cut by c (c: one value or four: x1y1, x0y1, x0y0, x1y0)."""
    c = (c,) * 4 if isinstance(c, (int, float)) else c
    return [(x1, y1 - c[0]), (x1 - c[0], y1), (x0 + c[1], y1), (x0, y1 - c[1]),
            (x0, y0 + c[2]), (x0 + c[2], y0), (x1 - c[3], y0), (x1, y0 + c[3])]


class Part:
    """One mesh object filled piece by piece (one draw call per material in the browser)."""

    def __init__(self, name, parent=None, location=(0, 0, 0), auto_uv=True):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.slots: list[bpy.types.Material] = []
        self.parent = parent
        self.location = Vector(location)
        self.auto_uv = auto_uv

    def _index(self, m):
        if m not in self.slots:
            self.slots.append(m)
        return self.slots.index(m)

    def _finish(self, verts, m, bevel=0.0, segments=2, smooth=False):
        faces = {f for v in verts for f in v.link_faces}
        if bevel:
            edges = {e for f in faces for e in f.edges}
            res = bmesh.ops.bevel(self.bm, geom=list(edges) + list(verts), offset=bevel, segments=segments,
                                  profile=0.5, affect="EDGES", clamp_overlap=True)
            faces |= set(res["faces"])
            faces = {f for f in faces if f.is_valid}
            faces |= {f for v in res.get("verts", []) for f in v.link_faces}
        # normals out, per piece: a piece is closed, so this is reliable (the whole mesh, with pieces
        # touching each other, is not: some faces would turn inward and show the background)
        bmesh.ops.recalc_face_normals(self.bm, faces=list(faces))
        index = self._index(m)
        for f in faces:
            f.material_index = index
            f.smooth = smooth
        return faces

    def box(self, size, center, m, bevel=0.0, segments=2, rotate=None):
        """size (x, y, z) around center; rotate: (axis, degrees) around the center."""
        res = bmesh.ops.create_cube(self.bm, size=1.0)
        verts = res["verts"]
        bmesh.ops.scale(self.bm, vec=Vector(size), verts=verts)
        if rotate:
            bmesh.ops.rotate(self.bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(rotate[1]), 3, rotate[0]))
        bmesh.ops.translate(self.bm, vec=Vector(center), verts=verts)
        return self._finish(verts, m, bevel, segments)

    def span(self, lo, hi, m, bevel=0.0, segments=2):
        """Box from corner lo to corner hi."""
        lo, hi = Vector(lo), Vector(hi)
        return self.box(hi - lo, (lo + hi) / 2, m, bevel, segments)

    def cyl(self, radius, depth, center, m, axis="Z", segments=32, radius2=None, bevel=0.0, smooth=True):
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segments,
                                    radius1=radius, radius2=radius if radius2 is None else radius2, depth=depth)
        verts = res["verts"]
        if axis == "X":
            bmesh.ops.rotate(self.bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
        elif axis == "Y":
            bmesh.ops.rotate(self.bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(self.bm, vec=Vector(center), verts=verts)
        faces = self._finish(verts, m, bevel, 2)
        if smooth:  # smooth sides, flat caps
            n = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
            for f in faces:
                f.smooth = abs(f.normal.dot(n)) < 0.9
        return faces

    def ring(self, r_in, r_out, depth, center, m, axis="Z", segments=48):
        """A flat washer (fan rims, RGB rings)."""
        verts = []
        top, bottom = [], []
        for side, z in ((top, depth / 2), (bottom, -depth / 2)):
            for r in (r_in, r_out):
                row = [self.bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                       for a in (2 * math.pi * i / segments for i in range(segments))]
                side.append(row)
                verts += row
        for i in range(segments):
            j = (i + 1) % segments
            ti, to = top
            bi, bo = bottom
            self.bm.faces.new((ti[i], to[i], to[j], ti[j]))
            self.bm.faces.new((bi[j], bo[j], bo[i], bi[i]))
            self.bm.faces.new((to[i], bo[i], bo[j], to[j]))
            self.bm.faces.new((ti[j], bi[j], bi[i], ti[i]))
        self._orient(verts, center, axis)
        fs = self._finish(verts, m)
        for f in fs:
            f.smooth = abs(f.normal.dot(Vector(AXIS_VEC[axis]))) < 0.9
        return fs

    def rect_frame(self, w, h, r, depth, center, m, axis="Z", segments=48, corner=0.0):
        """A rectangular plate with a round hole (fan frames, the holes of a card's fan plate).
        corner: rounds the outer corners by this radius."""
        corners = [math.atan2(h, w), math.pi - math.atan2(h, w), math.pi + math.atan2(h, w), 2 * math.pi - math.atan2(h, w)]
        angles = sorted({round(2 * math.pi * i / segments, 6) for i in range(segments)} | {round(a, 6) for a in corners})
        verts, rows = [], []
        for z in (depth / 2, -depth / 2):
            inner, outer = [], []
            for a in angles:
                c, s = math.cos(a), math.sin(a)
                k = min((w / 2) / abs(c) if abs(c) > 1e-9 else 1e9, (h / 2) / abs(s) if abs(s) > 1e-9 else 1e9)
                ox, oy = k * c, k * s
                if corner:  # pull the corner points onto a rounded corner
                    cx, cy = max(min(ox, w / 2 - corner), -w / 2 + corner), max(min(oy, h / 2 - corner), -h / 2 + corner)
                    dx, dy = ox - cx, oy - cy
                    d = math.hypot(dx, dy)
                    if d > corner:
                        ox, oy = cx + dx / d * corner, cy + dy / d * corner
                inner.append(self.bm.verts.new((r * c, r * s, z)))
                outer.append(self.bm.verts.new((ox, oy, z)))
            rows.append((inner, outer))
            verts += inner + outer
        (ti, to), (bi, bo) = rows
        n = len(angles)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new((ti[i], to[i], to[j], ti[j]))
            self.bm.faces.new((bi[j], bo[j], bo[i], bi[i]))
            self.bm.faces.new((to[i], bo[i], bo[j], to[j]))
            self.bm.faces.new((ti[j], bi[j], bi[i], ti[i]))
        self._orient(verts, center, axis)
        fs = self._finish(verts, m)
        for f in fs:  # the round hole is smooth, the rest flat
            f.smooth = False
        return fs

    def square_frame(self, size, r, depth, center, m, axis="Z", segments=48, corner=0.0):
        return self.rect_frame(size, size, r, depth, center, m, axis, segments, corner)

    def prism(self, pts, a0, a1, m, plane="XZ", bevel=0.0, segments=1):
        """A flat outline pts (2D, counter-clockwise) pushed out between levels a0 and a1 of the third axis.
        plane XZ: points are (x, z), depth along y; XY: (x, y), along z; YZ: (y, z), along x."""
        def p3(u, v, w):
            return {"XZ": (u, w, v), "XY": (u, v, w), "YZ": (w, u, v)}[plane]
        lo = [self.bm.verts.new(p3(u, v, a0)) for u, v in pts]
        hi = [self.bm.verts.new(p3(u, v, a1)) for u, v in pts]
        self.bm.faces.new(list(reversed(lo)))
        self.bm.faces.new(hi)
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        return self._finish(lo + hi, m, bevel, segments)

    def tube(self, points, radius, m, segments=14, caps=True):
        """A round pipe along a polyline (heat pipes, cables)."""
        pts = [Vector(p) for p in points]
        rings = []
        normal = None
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            if normal is None:
                helper = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
                normal = t.cross(helper).normalized()
            normal = (normal - t * normal.dot(t)).normalized()  # parallel transport
            binormal = t.cross(normal)
            rings.append([self.bm.verts.new(p + radius * (math.cos(a) * normal + math.sin(a) * binormal))
                          for a in (2 * math.pi * k / segments for k in range(segments))])
        for a, b in zip(rings, rings[1:]):
            for k in range(segments):
                k2 = (k + 1) % segments
                self.bm.faces.new((a[k], a[k2], b[k2], b[k]))
        if caps:
            self.bm.faces.new(list(reversed(rings[0])))
            self.bm.faces.new(rings[-1])
        fs = self._finish([v for r in rings for v in r], m)
        for f in fs:
            f.smooth = len(f.verts) == 4
        return fs

    def quad(self, corners, m, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        """A flat panel with UVs (labels)."""
        vs = [self.bm.verts.new(c) for c in corners]
        f = self.bm.faces.new(vs)
        for loop, (u, v) in zip(f.loops, uv):
            loop[self.uv].uv = (u, v)
        f.material_index = self._index(m)
        return {f}

    def _orient(self, verts, center, axis):
        if axis == "X":
            bmesh.ops.rotate(self.bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
        elif axis == "Y":
            bmesh.ops.rotate(self.bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(self.bm, vec=Vector(center), verts=verts)

    def build(self):
        if self.auto_uv:  # box projection in millimetres: tiling textures keep their size on every face
            for f in self.bm.faces:
                f.normal_update()
                n = f.normal
                ax = max(range(3), key=lambda k: abs(n[k]))
                u_ax, v_ax = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[ax]
                for loop in f.loops:
                    co = loop.vert.co + self.location
                    loop[self.uv].uv = (co[u_ax] / UV_MM, co[v_ax] / UV_MM)
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.slots:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(ob)
        ob.location = self.location
        if self.parent is not None:
            ob.parent = self.parent
        return ob


def empty(name, location, parent):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 6
    ob.location = location
    ob.parent = parent
    bpy.context.collection.objects.link(ob)
    return ob


AXIS_VEC = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
AXIS_TURN = {"X": Matrix.Rotation(math.pi / 2, 3, "Y"), "Y": Matrix.Rotation(-math.pi / 2, 3, "X"), "Z": Matrix.Identity(3)}
FLIP = Matrix.Rotation(math.pi, 3, "X")


def blades(part, m, count, r_hub, r_tip, depth, sweep=0.55, chord=0.66, z0=0.0):
    """Curved fan blades around Z: each a thin twisted surface, wider and swept back at the tip."""
    idx = part._index(m)
    ni, nj = 7, 5
    for b in range(count):
        a0 = 2 * math.pi * b / count
        rows = []
        for i in range(ni + 1):
            t = i / ni
            rr = r_hub - 0.6 + (r_tip - r_hub + 0.6) * t
            span = (2 * math.pi / count) * (chord + 0.16 * t)
            row = []
            for j in range(nj + 1):
                sj = j / nj
                theta = a0 + sweep * t * t + span * sj
                camber = math.sin(sj * math.pi) * depth * 0.08
                z = (sj - 0.5) * depth * 0.62 * (1 - 0.3 * t) + z0 + camber
                row.append(part.bm.verts.new((rr * math.cos(theta), rr * math.sin(theta), z)))
            rows.append(row)
        for i in range(ni):
            for j in range(nj):
                f = part.bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]))
                f.material_index = idx
                f.smooth = True


def fan(parent, name, center, size, depth, axis, M, count=9, clear=False, rim_rgb=False, flip=False, style="case",
        frame_m=None, blade_m=None):
    """A fan, built around Z and turned to axis ("X", "Y" or "Z": the airflow); flip turns it over.
    style "case": square frame with rubber corners and struts; "open": a lip ring with three struts
    (the fans of a graphics card); "round": a round shroud (a box cooler).
    The rotor's own Z (glTF Y) is the axis; its hub cap looks to local +Z before the turn."""
    r = size / 2 - (3.5 if style == "case" else 2.0)
    fm = frame_m or M["fan_frame"]
    frame = Part(f"{name}_frame", parent)
    back = -(depth / 2 - 1.8)
    if style == "case":
        frame.square_frame(size, r, depth, (0, 0, 0), fm, corner=6)
        if rim_rgb:
            frame.ring(r - 1.2, r + 0.1, depth * 0.62, (0, 0, 0), M["rgb"], segments=64)
        for sx in (-1, 1):  # rubber pads on the corners (both faces)
            for sy in (-1, 1):
                frame.cyl(4.2, 1.2, (sx * (size / 2 - 7.5), sy * (size / 2 - 7.5), depth / 2 + 0.4), M["rubber"], segments=10)
    elif style == "open":
        frame.ring(r + 0.3, r + 3.2, 2.4, (0, 0, -depth / 2 + 1.2), fm, segments=64)
    else:
        frame.ring(r + 0.2, r + 2.6, depth, (0, 0, 0), M["black_metal"], segments=64)
    frame.cyl(size * 0.17, 3, (0, 0, back), fm, segments=28)                                  # the motor
    struts = 4 if style == "case" else 3
    for k in range(struts):
        a = math.pi / 4 + k * 2 * math.pi / struts
        frame.box((r * 0.9, 2.6, 2.0), (math.cos(a) * r * 0.55, math.sin(a) * r * 0.55, back), fm,
                  rotate=("Z", math.degrees(a)))
    turn = AXIS_TURN[axis] @ (FLIP if flip else Matrix.Identity(3))
    bmesh.ops.rotate(frame.bm, verts=frame.bm.verts, cent=(0, 0, 0), matrix=turn)
    bmesh.ops.translate(frame.bm, vec=Vector(center), verts=frame.bm.verts)
    frame.build()

    # the rotor: hub with a logo cap + curved blades around its own Z; the object rotation turns it to the axis
    rotor = Part(f"rotor_{name}", parent, location=center)
    hub_r = size * 0.18
    rotor.cyl(hub_r, depth * 0.66, (0, 0, 0.6), M["fan_blade_clear"] if clear else fm, segments=36, bevel=0.8)
    rotor.cyl(hub_r * 0.72, 0.8, (0, 0, 0.6 + depth * 0.33 + 0.3), M["fan_cap"], segments=36)
    rotor.ring(hub_r * 0.74, hub_r * 0.8, 0.9, (0, 0, 0.6 + depth * 0.33 + 0.35), M["shroud_accent"], segments=36)
    blade_m = blade_m or (M["fan_blade_clear"] if clear else M["fan_blade"])
    tip = r - (1.4 if style == "case" else 2.2)
    blades(rotor, blade_m, count, hub_r, tip, depth, z0=0.4)
    if style == "open":  # the ring that ties the blade tips together
        rotor.ring(tip - 0.2, tip + 1.0, depth * 0.3, (0, 0, 0.4), blade_m, segments=64)
    ob = rotor.build()
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = turn.to_quaternion()
    return ob


def fins(part, count, start, step, size, m):
    """A stack of thin plates: radiator and heatsink fins. step: offset between plates (x, y, z)."""
    s, d = Vector(start), Vector(step)
    for i in range(count):
        part.box(size, s + d * i, m)


def grid_sheet(part, axis, a0, a1, rect, holes, m, bevel=0.0):
    """A flat sheet between a0..a1 along axis ("X", "Y" or "Z") over rect (u0, u1, v0, v1) with rectangular holes
    (u0, u1, v0, v1): cut into boxes along the edges of the holes."""
    u0, u1, v0, v1 = rect
    us = sorted({u0, u1, *[h[0] for h in holes], *[h[1] for h in holes]})
    vs = sorted({v0, v1, *[h[2] for h in holes], *[h[3] for h in holes]})
    us = [u for u in us if u0 <= u <= u1]
    vs = [v for v in vs if v0 <= v <= v1]

    def inside(u, v):
        return any(h[0] <= u <= h[1] and h[2] <= v <= h[3] for h in holes)
    for ua, ub in zip(us, us[1:]):
        for va, vb in zip(vs, vs[1:]):
            if inside((ua + ub) / 2, (va + vb) / 2):
                continue
            if axis == "X":
                part.span((a0, ua, va), (a1, ub, vb), m, bevel)
            elif axis == "Y":
                part.span((ua, a0, va), (ub, a1, vb), m, bevel)
            else:
                part.span((ua, va, a0), (ub, vb, a1), m, bevel)


# ---------------------------------------------------------------- the case


def make_case(M, name, D, H, W, cage_levels, radiator_max):
    """An open case of D x H x W mm. Origin: front-bottom corner at the tray side."""
    root = Part(name)
    st, si = M["steel"], M["steel_in"]
    board_x = D - BOARD_X
    # tray (the motherboard wall): CPU back-plate cut-out, grommets for the cables
    root.span((T, -T, FLOOR), (D - T, 0, H - T), si)
    root.prism(rrect(108, 96, 10, cx=board_x - 103, cy=H - 32 - 82), -T - 0.25, -T, M["rubber"], plane="XZ")
    grommet_x = D - 279
    grommets = [H - 118, H - 222, FLOOR + SHROUD + 60]
    for gz in grommets:                                                                     # rubber, with a slit
        root.prism(rrect(22, 62, 6, cx=grommet_x, cy=gz), -T - 1.4, -T, M["rubber"], plane="XZ")
        root.prism(rrect(3.4, 46, 1.6, cx=grommet_x, cy=gz), -T - 1.5, -T - 1.4, M["chip"], plane="XZ")
    eps_x = board_x - 63
    root.prism(rrect(70, 13, 5, cx=eps_x, cy=H - 17), -T - 1.4, -T, M["rubber"], plane="XZ")   # top, for the CPU cable
    root.prism(rrect(56, 3.2, 1.5, cx=eps_x, cy=H - 17), -T - 1.5, -T - 1.4, M["chip"], plane="XZ")
    for k in range(3):                                                                      # tie-down points
        root.span((grommet_x + 18, -T - 1.2, grommets[k] - 30), (grommet_x + 22, -T, grommets[k] - 26), si)
    # bottom sheet and the top sheet with a perforated panel over the radiator area
    root.span((0, -W, FLOOR - T), (D, 0, FLOOR), st, bevel=0.6)
    top_hole = (36, D - 30, -W + 26, -26)
    grid_sheet(root, "Z", H - T, H, (0, D, -W, 0), [top_hole], st)
    root.span((top_hole[0], top_hole[2], H - T + 0.4), (top_hole[1], top_hole[3], H - 0.6), M["mesh"])
    grid_sheet(root, "Z", H, H + 0.6, (top_hole[0] - 3, top_hole[1] + 3, top_hole[2] - 3, top_hole[3] + 3), [top_hole], M["accent"])
    # power button with a lit ring, USB ports
    root.cyl(6.5, 3, (14, -W / 2, H + 1.5), M["accent"], segments=32, bevel=0.6)
    root.ring(6.9, 8.4, 1.2, (14, -W / 2, H + 0.6), M["led"], segments=32)
    for k, (w, d) in enumerate(((9, 3.4), (13, 5.4), (13, 5.4))):
        y = -W / 2 + 22 + k * 20
        root.span((14 - d / 2, y - w / 2, H - 0.4), (14 + d / 2, y + w / 2, H + 0.3), M["chip"], bevel=0.3)
    root.cyl(2.2, 1, (14, -W / 2 - 18, H + 0.2), M["chip"], segments=16)                    # audio jack
    # rear sheet: openings for the IO shield, the slot covers, the fan and the PSU
    # (each opening is exactly the size of what fills it: the board's IO shield, the PSU's rear face)
    io = IO_HOLE[1] - 8, IO_HOLE[0] - 8, H - 32 + IO_HOLE[3], H - 32 + IO_HOLE[2]
    slot_top = H - 32 - 175 + 16
    slots = max(2, min(7, int((slot_top - FLOOR - SHROUD - 14) / 20.3)))
    slot_holes = [(-130, -18, slot_top - (i + 0.5) * 20.3 - 7.5, slot_top - (i + 0.5) * 20.3 + 7.5) for i in range(slots)]
    psu_hole = (-190, -40, FLOOR, FLOOR + 86)
    fan_size = 120 if H > 380 else 92
    fan_z = H - 58 - fan_size / 2                        # above the highest card, under a top radiator
    fan_hole = (-112 - fan_size / 2 + 4, -112 + fan_size / 2 - 4, fan_z - fan_size / 2 + 4, fan_z + fan_size / 2 - 4)
    grid_sheet(root, "X", D - T, D, (-W, 0, FLOOR, H - T), [io, psu_hole, fan_hole, *slot_holes], si)
    root.span((D - T + 0.6, fan_hole[0], fan_hole[2]), (D - 0.6, fan_hole[1], fan_hole[3]), M["mesh"])
    for h in slot_holes:                                                                    # vented slot covers in their cut-outs
        root.span((D - 1.6, h[0], h[2]), (D - 0.5, h[1], h[3]), M["accent"])
        root.span((D - 0.5, h[0] + 16, h[2] + 3.5), (D - 0.2, h[1] - 22, h[3] - 3.5), M["mesh"])
        root.cyl(2.4, 1.2, (D - 0.2, h[0] + 7, (h[2] + h[3]) / 2), M["nickel"], axis="X", segments=12)
    root.span((D - 0.2, -136, slot_top - 0.5), (D + 1.0, -12, slot_top + 5), M["accent"], bevel=0.3)   # retention bar
    # front: an inner sheet open where the fans are, the shell of the front panel (its face: front_* below)
    open_lo = FLOOR + 33 * cage_levels + 8
    grid_sheet(root, "X", 0, T, (-W, 0, FLOOR - T, H), [(-W + 16, -16, open_lo, H - 18)], si)
    grid_sheet(root, "X", -22.5, -T, (-W - 1, 1, 10, H), [(-W + 12, -12, 30, H - 16)], st)
    # rails along the open side (where the glass would sit), rounded
    root.span((0, -W, FLOOR), (D, -W + 6, FLOOR + 10), st, bevel=1.4, segments=3)
    root.span((0, -W, H - 12), (D, -W + 6, H - T), st, bevel=1.4, segments=3)
    root.span((D - 12, -W, FLOOR), (D - T, -W + 6, H - T), st, bevel=1.4, segments=3)
    root.span((T, -W, FLOOR), (16, -W + 6, H - T), st, bevel=1.4, segments=3)
    # PSU shroud: a top plate with a vented part over the PSU fan and a cut-out for the card's cable
    sx0 = D - T - 196                     # room for a 180 mm PSU
    shroud_z = FLOOR + SHROUD
    cut = (sx0 + 14, sx0 + 62, -166, -134)
    vent = (cut[1] + 12, D - 30, -165, -60)
    grid_sheet(root, "Z", shroud_z - T, shroud_z, (sx0, D - T, -W + 6, -T), [cut, vent], st, bevel=0.0)
    root.span((vent[0], vent[2], shroud_z - T + 0.5), (vent[1], vent[3], shroud_z - 0.5), M["mesh"])
    for a in ((cut[0] - 3, cut[0], cut[2] - 3, cut[3] + 3), (cut[1], cut[1] + 3, cut[2] - 3, cut[3] + 3),
              (cut[0], cut[1], cut[2] - 3, cut[2]), (cut[0], cut[1], cut[3], cut[3] + 3)):          # a rubber edge
        root.span((a[0], a[2], shroud_z - T - 0.6), (a[1], a[3], shroud_z + 1.0), M["rubber"], bevel=0.4)
    root.span((sx0, -W + 6, shroud_z - 14), (sx0 + T, -T, shroud_z - T), st)               # its front lip
    root.span((sx0 + 12, -W + 5.6, shroud_z - 6), (D - 20, -W + 6, shroud_z - 3), M["accent"])  # an accent line
    # drive cage at the bottom front: open toward the open side, so the drives in it are seen
    cage_top = FLOOR + 33 * cage_levels
    if cage_levels > 1:
        root.span((22, -60, FLOOR), (180, -57, cage_top), si)                                  # back wall
        for x in (22, 177):
            root.span((x, -172, FLOOR), (x + 3, -57, cage_top), si, bevel=0.4)                # side walls
        root.span((22, -172, cage_top), (180, -57, cage_top + 2), si, bevel=0.4)               # its lid
        for k in range(1, cage_levels):
            z = FLOOR + 33 * k
            for y0 in (-172, -70):                                                             # rails, not shelves
                root.span((25, y0, z - 1), (177, y0 + 10, z + 0.6), si)
        for x in (22, 177):                                                                    # thumb screws
            for k in range(cage_levels):
                root.cyl(3.4, 2.4, (x + (-1.2 if x == 22 else 4.2), -114, FLOOR + 16 + 33 * k), M["nickel"], axis="X", segments=14)
    # feet
    for x in (30, D - 30):
        for y in (-25, -W + 25):
            root.cyl(14, FLOOR - T, (x, y, (FLOOR - T) / 2), M["rubber"], segments=24, bevel=1.5)
    case = root.build()
    # fans: in front above the drive cage, one at the rear
    lowest = max(cage_top, FLOOR) + 70
    z = H - 85
    i = 0
    while z >= lowest:
        fan(case, f"{name}_front{i}", (T + 16, -W / 2, z), 120, 25, "X", M, clear=True, rim_rgb=True)
        z -= 130
        i += 1
    fan(case, f"{name}_rear", (D - T - 14, -112, fan_z), fan_size, 25, "X", M, clear=True, rim_rgb=True)
    # mounts
    empty("mount_board", (board_x, -8, H - 32), case)
    empty("mount_psu", (D - T, -40, FLOOR), case)
    for k in range(max(1, cage_levels)):
        empty(f"mount_drive_{k}", (26, -116, FLOOR + 1 + k * 33), case)
    empty("mount_radiator", (D - 26, -130, H - T - 1), case)
    empty(f"radiator_max_{radiator_max}", (D - 26, -130, H - T - 1), case)
    empty("size", (D, -W, H), case)                                                         # inner size: the site reads it
    # cable ends: the grommets (24-pin, CPU) and the cut-out in the shroud (graphics card)
    empty("cable_24pin", (grommet_x, -T - 1.4, H - 118), case)
    empty("cable_eps", (eps_x, -T - 1.4, H - 17), case)
    empty("cable_gpu", ((cut[0] + cut[1]) / 2, (cut[2] + cut[3]) / 2, shroud_z - 1), case)
    # where the site stretches the case to the product's size: in front of x (below / above z) and outside of y
    empty("split_front_low", (190, 0, SPLIT_Z), case)
    empty("split_front_high", (grommet_x - 20, 0, SPLIT_Z), case)
    empty("split_side", (0, -W + 15, SPLIT_Z), case)
    make_fronts(case, M, W, H)
    g = Part("glass_side", case)   # tempered glass on the open side: barely there, a dark print along its edges
    g.span((-1, -W - 4, FLOOR - 1), (D + 1, -W - 0.2, H + 1), M["glass_side"])
    for a in ((-1, D + 1, FLOOR - 1, FLOOR + 9), (-1, D + 1, H - 9, H + 1), (-1, 9, FLOOR - 1, H + 1), (D - 9, D + 1, FLOOR - 1, H + 1)):
        g.span((a[0], -W - 4.3, a[2]), (a[1], -W - 4, a[3]), M["chip"])
    g.build()
    return case


def make_fronts(case, M, W, H):
    """The faces of the front panel, one object each; the site shows the one of the product (spec front_panel)."""
    st = M["steel"]
    hole = (-W + 12, -12, 30, H - 16)
    rect = (-W - 1, 1, 10, H)
    # mesh: a bezel and a perforated insert
    p = Part("front_mesh", case)
    grid_sheet(p, "X", -26, -22.5, rect, [hole], st)
    p.span((-25.2, hole[0], hole[2]), (-24.6, hole[1], hole[3]), M["mesh"])
    p.span((-26.4, -W + 4, H - 10), (-26, -4, H - 7), M["accent"])
    p.build()
    # glass: tinted glass in a thin frame, a dark print along its edges
    p = Part("front_glass", case)
    g = (-W + 4, -4, 16, H - 6)
    grid_sheet(p, "X", -26, -22.5, rect, [g], st)
    p.span((-25.6, g[0], g[2]), (-23.6, g[1], g[3]), M["glass_tint"])
    for a in ((g[0], g[0] + 6, g[2], g[3]), (g[1] - 6, g[1], g[2], g[3]), (g[0], g[1], g[2], g[2] + 6), (g[0], g[1], g[3] - 6, g[3])):
        p.span((-25.8, a[0], a[2]), (-25.6, a[1], a[3]), M["chip"])
    p.build()
    # solid: a flat face, air comes in through slots on its sides
    p = Part("front_solid", case)
    p.prism(rrect(W + 2, H - 10, 4, cx=-W / 2, cy=(H + 10) / 2), -26.5, -22.5, st, plane="YZ", bevel=0.8)
    p.span((-27, -W / 2 - 50, H - 40), (-26.5, -W / 2 + 50, H - 38), M["accent"])
    for y in (-W - 1.2, 1.0):
        p.span((-20, y, 30), (-6, y + 0.2, H - 20), M["mesh"])
    p.build()
    # wood: vertical slats over a mesh, like a Fractal North
    p = Part("front_wood", case)
    grid_sheet(p, "X", -26, -22.5, rect, [hole], st)
    p.span((-25.2, hole[0], hole[2]), (-24.6, hole[1], hole[3]), M["mesh"])
    n = int((hole[1] - hole[0]) / 14)
    w = (hole[1] - hole[0]) / n
    for k in range(n):
        y = hole[0] + k * w
        p.span((-30, y + 2.2, hole[2] - 6), (-26, y + w - 2.2, hole[3] + 6), M["wood"], bevel=1.2)
    p.build()


CASES = {  # by the boards they take: the biggest one decides
    "case_atx": dict(D=456, H=470, W=200, cage_levels=3, radiator_max=360),
    "case_matx": dict(D=400, H=410, W=200, cage_levels=3, radiator_max=240),
    "case_itx": dict(D=380, H=380, W=200, cage_levels=1, radiator_max=240),
}


# ---------------------------------------------------------------- motherboards

BOARDS = {  # name: length, height, RAM slots, layout (x from the rear edge, z from the top, both negative)
    "board_atx": dict(L=244, Hb=305, ram=4, socket=(-95, -82), ram_gap=55, ram_z=-87.5, io_z=(-6, -160),
                      eps=(-78, -52), vrm_top=(-140, -84), pcie=[-175, -255], x1=[-217], m2=[(-30, -138), (-42, -290)],
                      audio=True),
    "board_matx": dict(L=244, Hb=244, ram=4, socket=(-95, -82), ram_gap=55, ram_z=-87.5, io_z=(-6, -160),
                       eps=(-78, -52), vrm_top=(-140, -84), pcie=[-175], x1=[], m2=[(-30, -138), (-30, -207)],
                       audio=True),
    "board_itx": dict(L=170, Hb=170, ram=2, socket=(-85, -70), ram_gap=52, ram_z=-74, io_z=(-18, -140),
                      eps=(-50, -32), vrm_top=(-115, -56), pcie=[-158], x1=[], m2=[(-30, -124)], audio=False),
}
KEEPOUT = 46          # around the socket: nothing tall, so every cooler fits


def make_board(name, M, L, Hb, ram, socket, ram_gap, ram_z, io_z, eps, vrm_top, pcie, x1, m2, audio):
    """Origin: the board's rear-top corner, on its back side. The board lies at y -1.6..0, toward -y."""
    p = Part(name)
    pcb_y = -1.6
    rnd = random.Random(len(name) * 7 + Hb)
    p.span((-L, pcb_y, -Hb), (0, 0, 0), M["pcb"], bevel=0.3)
    sx, sz = socket
    busy = []  # rectangles (x0, x1, z0, z1) taken by big parts: the small ones go around them

    def taken(x0, x1, z0, z1):
        busy.append((min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1)))

    # --- rear IO: the ports reach the case's rear sheet, a sculpted cover with a lit strip over them
    io_top, io_bottom = io_z
    p.span((-24, pcb_y - 30, io_bottom + 4), (BOARD_X - T - 1.2, pcb_y, io_top - 4), M["black_metal"], bevel=0.6)
    # the IO shield sits in the case's rear cut-out (inside the sheet), the ports show through it
    sy0, sy1, sz0, sz1 = IO_HOLE
    p.span((BOARD_X - T - 1.2, sy1, sz1), (BOARD_X - 0.5, sy0, sz0), M["black_metal"])
    for k in range(6):  # ports in the shield: USB pairs, network, audio
        z = io_top - 14 - k * (io_top - io_bottom - 24) / 6
        if k < 4:
            p.span((BOARD_X - 0.6, pcb_y - 28, z - 4), (BOARD_X - 0.3, pcb_y - 15, z + 2), M["slot_steel"])
            p.span((BOARD_X - 0.55, pcb_y - 26.5, z - 2.4), (BOARD_X - 0.25, pcb_y - 16.5, z + 0.6), M["chip"])
            p.span((BOARD_X - 0.6, pcb_y - 12, z - 4), (BOARD_X - 0.3, pcb_y - 3, z + 2), M["slot"])
        else:
            for j in range(3):
                p.cyl(2.6, 0.4, (BOARD_X - 0.4, pcb_y - 8 - j * 9, z), M["audio_cap"] if j == 1 else M["chip"], axis="X", segments=14)
    cover = [(-30, io_top), (-30, io_bottom + 14), (-22, io_bottom), (2, io_bottom), (2, io_top)]
    p.prism([(x, z) for x, z in cover], pcb_y - 38, pcb_y - 6, M["black_metal"], plane="XZ", bevel=0.8)
    p.prism([(x, z) for x, z in [(-26, io_top - 6), (-26, io_bottom + 16), (-19, io_bottom + 6), (-6, io_bottom + 6), (-6, io_top - 6)]],
            pcb_y - 38.8, pcb_y - 38, M["alu_dark"], plane="XZ")
    p.span((-31, pcb_y - 37, io_bottom + 18), (-29.6, pcb_y - 8, io_top - 8), M["rgb"])
    p.span((-26, pcb_y - 39.2, io_top - 40), (-8, pcb_y - 38.8, io_top - 12), M["board_accent"])
    taken(-31, BOARD_X, io_bottom, io_top)

    # --- VRM: a finned heatsink above the socket and one between the socket and the IO, a heat pipe between them
    vx0, vx1 = vrm_top
    vz0, vz1 = sz + KEEPOUT, min(sz + KEEPOUT + 26, -3)
    p.span((vx0, pcb_y - 8, vz0), (vx1, pcb_y, vz1), M["board_hs"], bevel=0.8)
    n_fins = int((vx1 - vx0 - 4) / 3.2)
    for i in range(n_fins):
        x = vx0 + 2 + i * 3.2
        p.span((x, pcb_y - 24, vz0 + 1), (x + 1.8, pcb_y - 8, vz1 - 1), M["board_hs"])
    p.prism(chamfered(vx0 - 0.4, vz0 + 2, vx1 + 0.4, vz1 - 4, (0, 0, 4, 4)), pcb_y - 25.5, pcb_y - 24, M["shroud_accent"], plane="XZ")
    taken(vx0, vx1, vz0, vz1)
    rx0, rx1 = sx + KEEPOUT, -32.5
    rz0, rz1 = sz - 40, min(sz + 40, io_top - 14)
    p.span((rx0, pcb_y - 8, rz0), (rx1, pcb_y, rz1), M["board_hs"], bevel=0.8)
    for i in range(int((rz1 - rz0 - 4) / 3.2)):
        z = rz0 + 2 + i * 3.2
        p.span((rx0 + 1, pcb_y - 24, z), (rx1 - 1, pcb_y - 8, z + 1.8), M["board_hs"])
    p.prism(chamfered(rx0 + 1, rz0 - 0.4, rx1 - 1, rz1 + 0.4, (2, 2, 2, 2)), pcb_y - 25.5, pcb_y - 24, M["black_metal"], plane="XZ")
    taken(rx0, rx1, rz0, rz1)
    hp_z = vz0 + 5
    p.tube([(vx1 - 2, pcb_y - 4, hp_z), (rx0 + 4, pcb_y - 4, hp_z), (rx0 + 6, pcb_y - 4, hp_z - 4), (rx0 + 6, pcb_y - 4, rz1 - 4)],
           2.0, M["nickel"], segments=10)
    # chokes and power stages along the heatsinks
    for i in range(int((vx1 - vx0) / 8.5)):
        x = vx0 + 1 + i * 8.5
        p.span((x, pcb_y - 5, vz0 - 8), (x + 7, pcb_y, vz0 - 1.2), M["choke"], bevel=0.5)
    for i in range(int((rz1 - rz0) / 8.5)):
        z = rz0 + 1 + i * 8.5
        p.span((rx0 - 8, pcb_y - 5, z), (rx0 - 1.2, pcb_y, z + 7), M["choke"], bevel=0.5)
    # 8-pin CPU power at the top edge
    p.span((eps[0], pcb_y - 13, -14), (eps[1], pcb_y, -4), M["chip"], bevel=0.6)
    for i in range(4):
        for j in range(2):
            p.span((eps[0] + 2.5 + i * 5.6, pcb_y - 13.2, -12 + j * 4.4), (eps[0] + 6.5 + i * 5.6, pcb_y - 13, -8.6 + j * 4.4), M["slot"])
    taken(eps[0], eps[1], -16, -2)

    # --- socket: frame, load plate, lever, the cooler's screw posts
    p.span((sx - 27, pcb_y - 2.5, sz - 27), (sx + 27, pcb_y, sz + 27), M["slot"], bevel=0.8)
    p.span((sx - 24, pcb_y - 3, sz - 24), (sx + 24, pcb_y - 2.5, sz + 24), M["slot_steel"])
    p.tube([(sx + 30, pcb_y - 3, sz - 26), (sx + 30, pcb_y - 3, sz + 26), (sx + 26, pcb_y - 6, sz + 30)], 0.9, M["slot_steel"])
    for dx in (-37, 37):
        for dz in (-37, 37):
            p.cyl(3.0, 2.4, (sx + dx, pcb_y - 1.2, sz + dz), M["nickel"], axis="Y", segments=14)
    taken(sx - 40, sx + 40, sz - 40, sz + 40)

    # --- RAM slots: one latch at the top end
    ram_x = [sx - ram_gap - i * 9.5 for i in range(ram)]
    for i, x in enumerate(ram_x):
        p.span((x - 3, pcb_y - 7, ram_z - 68), (x + 3, pcb_y, ram_z + 68), M["slot"] if i % 2 else M["slot_steel"], bevel=0.4)
        p.span((x - 2.4, pcb_y - 7.4, ram_z - 64), (x + 2.4, pcb_y - 6.8, ram_z + 62), M["chip"])
        p.span((x - 3.4, pcb_y - 10, ram_z + 68), (x + 3.4, pcb_y, ram_z + 73), M["latch"], bevel=0.6)
        p.span((x - 2.2, pcb_y - 7.5, ram_z - 72), (x + 2.2, pcb_y, ram_z - 68), M["slot"], bevel=0.4)
    taken(ram_x[-1] - 4, ram_x[0] + 4, ram_z - 72, ram_z + 73)

    # --- 24-pin power at the front edge (right-angled: the plug comes in from the front)
    p.span((-L + 1, pcb_y - 10, -112), (-L + 16, pcb_y, -60), M["chip"], bevel=0.6)
    for j in range(12):
        for i in range(2):
            p.span((-L + 0.8, pcb_y - 8.2 + i * 4, -110 + j * 4.2), (-L + 1, pcb_y - 5.2 + i * 4, -107 + j * 4.2), M["slot"])
    taken(-L, -L + 17, -113, -59)
    # SATA ports (right-angled, stacked) and a USB 3 header on the front edge
    if Hb > 200:
        for k in range(2):
            z = -180 - k * 24
            for j in range(2):
                p.span((-L + 1, pcb_y - 6 - j * 7, z - 10), (-L + 9, pcb_y - 0.5 - j * 7, z + 10), M["chip"], bevel=0.4)
        taken(-L, -L + 10, -192 - 24, -168)
    p.span((-L + 1, pcb_y - 9, -132), (-L + 10, pcb_y, -120), M["slot"], bevel=0.4)
    taken(-L, -L + 11, -133, -119)

    # --- PCIe x16 with a steel armor and a latch, x1 slots
    for i, z in enumerate(pcie):
        p.span((-94, pcb_y - 11, z - 3.5), (-4, pcb_y, z + 3.5), M["slot"], bevel=0.4)
        if i == 0:
            p.span((-95, pcb_y - 11.4, z - 4.3), (-3, pcb_y - 9.5, z + 4.3), M["slot_steel"], bevel=0.3)
            p.span((-95, pcb_y - 11.4, z - 4.3), (-3, pcb_y - 1, z - 3.8), M["slot_steel"])
            p.span((-95, pcb_y - 11.4, z + 3.8), (-3, pcb_y - 1, z + 4.3), M["slot_steel"])
        p.span((-103, pcb_y - 13, z - 4.2), (-94, pcb_y, z + 4.2), M["latch"], bevel=0.5)
        taken(-104, -2, z - 5, z + 5)
    for z in x1:
        p.span((-34, pcb_y - 11, z - 3.5), (-4, pcb_y, z + 3.5), M["slot"], bevel=0.4)
        taken(-35, -3, z - 4, z + 4)

    # --- M.2 slots: the connector, the standoff, a heatsink over each (the site hides it under a drive)
    for i, (mx, mz) in enumerate(m2):
        p.span((mx - 4, pcb_y - 4.5, mz - 11), (mx + 4, pcb_y, mz + 11), M["slot"], bevel=0.4)
        p.cyl(2.4, 3.5, (mx - 82, pcb_y - 1.75, mz), M["gold"], axis="Y", segments=12)
        taken(mx - 86, mx + 5, mz - 13, mz + 13)
        sh = Part(f"m2shield_{i}", None)
        sh.prism(chamfered(mx - 86, mz - 13, mx + 5, mz + 13, (5, 0, 0, 5)), pcb_y - 9.5, pcb_y - 5.2, M["board_hs"], plane="XZ", bevel=0.5)
        sh.prism(chamfered(mx - 80, mz - 9, mx - 2, mz + 9, (3, 0, 0, 3)), pcb_y - 10.1, pcb_y - 9.5, M["black_metal"], plane="XZ")
        for k in range(6):
            sh.span((mx - 76 + k * 12, pcb_y - 10.2, mz - 7), (mx - 70 + k * 12, pcb_y - 10.0, mz + 7), M["board_accent"])
        sh.cyl(1.8, 1.2, (mx - 82, pcb_y - 10, mz), M["nickel"], axis="Y", segments=10)
        sh.span((mx - 86, pcb_y - 5.2, mz - 2), (mx - 84, pcb_y, mz + 2), M["alu_dark"])
        sh.span((mx + 3, pcb_y - 5.2, mz - 2), (mx + 5, pcb_y, mz + 2), M["alu_dark"])
        sh_parts.append(sh)

    # --- chipset heatsink: a faceted block with a glossy inlay
    if Hb > 200:
        cz = (pcie[0] + (pcie[1] if len(pcie) > 1 else -Hb + 20)) / 2 - 8
        cx0, cx1 = -L + 22, -L + 80
        p.prism(chamfered(cx0, cz - 26, cx1, cz + 26, (10, 4, 10, 4)), pcb_y - 10, pcb_y, M["board_hs"], plane="XZ", bevel=0.8)
        p.prism(chamfered(cx0 + 6, cz - 18, cx1 - 6, cz + 18, (7, 3, 7, 3)), pcb_y - 10.6, pcb_y - 10, M["glass"], plane="XZ")
        p.prism(chamfered(cx0 + 10, cz - 4, cx1 - 18, cz + 2, 1), pcb_y - 10.8, pcb_y - 10.6, M["board_accent"], plane="XZ")
        taken(cx0, cx1, cz - 26, cz + 26)
        # CMOS battery
        p.cyl(10, 3.2, (-L + 110, pcb_y - 1.6, pcie[0] - 30), M["nickel"], axis="Y", segments=28)
        p.cyl(7, 0.4, (-L + 110, pcb_y - 3.3, pcie[0] - 30), M["slot_steel"], axis="Y", segments=20)
        taken(-L + 99, -L + 121, pcie[0] - 41, pcie[0] - 19)

    # --- audio: a shielded codec, gold capacitors and a line that splits the board
    if audio:
        az1 = pcie[-1] - 12 if Hb > 300 else pcie[-1] - 14
        az0 = -Hb + 6
        ax0, ax1 = -36, -3
        if az1 - az0 > 18:
            p.span((ax0, pcb_y - 0.3, az0), (ax0 + 0.8, pcb_y, az1), M["header"])
            p.span((ax0 + 4, pcb_y - 1.6, az1 - 14), (ax0 + 14, pcb_y, az1 - 4), M["nickel"], bevel=0.3)
            caps = [(ax0 + 22, az1 - 8), (ax0 + 29, az1 - 8), (ax0 + 22, az1 - 16), (ax0 + 29, az1 - 16)]
            for cxp, czp in caps:
                if czp - 3.5 > az0:
                    p.cyl(2.8, 7, (cxp, pcb_y - 3.5, czp), M["audio_cap"], axis="Y", segments=16)
                    p.cyl(2.2, 0.3, (cxp, pcb_y - 7.1, czp), M["slot_steel"], axis="Y", segments=12)
            taken(ax0, ax1, az0, az1)

    # --- headers along the bottom edge (front panel, USB 2), fan headers, a debug LED pair
    for k in range(4):
        x0 = -L + 20 + k * 28
        p.span((x0, pcb_y - 8, -Hb + 3), (x0 + 18, pcb_y, -Hb + 9), M["chip"] if k else M["header"], bevel=0.3)
        taken(x0, x0 + 18, -Hb + 2, -Hb + 10)
    for x0, z0 in ((eps[0] - 16, -8), (-L + 24, -40), (-L + 24, -150)):
        if not any(b[0] - 1 < x0 < b[1] + 1 and b[2] - 1 < z0 < b[3] + 1 for b in busy):
            p.span((x0, pcb_y - 6, z0 - 2.5), (x0 + 10, pcb_y, z0 + 2.5), M["header"], bevel=0.3)
            taken(x0, x0 + 10, z0 - 3, z0 + 3)
    for k, lm in enumerate((M["led"], M["rgb"])):
        p.span((-L + 22 + k * 5, pcb_y - 1, -60), (-L + 25 + k * 5, pcb_y, -57), lm)

    # --- small parts: SMD resistors and capacitors, a few chips, round capacitors, all in the free space
    def free(x0, x1, z0, z1):
        return all(x1 < b[0] - 1 or x0 > b[1] + 1 or z1 < b[2] - 1 or z0 > b[3] + 1 for b in busy)
    placed = 0
    for _ in range(1600):
        if placed >= 240:
            break
        w, h = rnd.choice(((1.6, 0.8), (1.0, 0.5), (2.0, 1.2), (0.8, 1.6)))
        x, z = rnd.uniform(-L + 4, -4), rnd.uniform(-Hb + 4, -4)
        if free(x, x + w, z, z + h):
            p.span((x, pcb_y - 0.55, z), (x + w, pcb_y, z + h), M["smd"])
            busy.append((x, x + w, z, z + h))
            placed += 1
    for _ in range(80):
        w, h = rnd.choice(((6, 6), (8, 5), (10, 10), (5, 3)))
        x, z = rnd.uniform(-L + 6, -8), rnd.uniform(-Hb + 14, -10)
        if free(x - 1, x + w + 1, z - 1, z + h + 1):
            p.span((x, pcb_y - 1.2, z), (x + w, pcb_y, z + h), M["chip"], bevel=0.2)
            taken(x, x + w, z, z + h)
    for _ in range(60):
        x, z = rnd.uniform(-L + 8, -8), rnd.uniform(-Hb + 14, -10)
        if free(x - 3.5, x + 3.5, z - 3.5, z + 3.5):
            p.cyl(3, 6, (x, pcb_y - 3, z), M["alu"], axis="Y", segments=14)
            p.cyl(2.6, 0.2, (x, pcb_y - 6.05, z), M["chip"], axis="Y", segments=12)
            taken(x - 3, x + 3, z - 3, z + 3)
    # mounting screws (and standoffs behind the board)
    for hx in (-7, -126, -L + 8):
        for hz in (-10, -150, -Hb + 10):
            if -L < hx < 0 and -Hb < hz < 0:
                p.cyl(3.2, 6.0, (hx, 3.0, hz), M["nickel"], axis="Y", segments=6, smooth=False)
                if free(hx - 4, hx + 4, hz - 4, hz + 4):
                    p.cyl(3.6, 1.2, (hx, pcb_y - 0.6, hz), M["nickel"], axis="Y", segments=16)
    board = p.build()
    for sh in sh_parts:
        sh.parent = board
        sh.build()
    sh_parts.clear()
    # mounts
    empty("mount_cpu", (sx, pcb_y - 2.5, sz), board)
    empty("mount_cooler", (sx, pcb_y - 7.5, sz), board)
    for i, x in enumerate(ram_x):
        empty(f"mount_ram_{i}", (x, pcb_y - 4, ram_z), board)
    empty("mount_gpu", (BOARD_X - T, pcb_y - 7, pcie[0]), board)
    for i, (mx, mz) in enumerate(m2):
        empty(f"mount_m2_{i}", (mx, pcb_y - 3.5, mz), board)
    empty("cable_24pin", (-L + 1, pcb_y - 5, -86), board)
    empty("cable_eps", ((eps[0] + eps[1]) / 2, pcb_y - 13, -9), board)
    return board


sh_parts: list[Part] = []


# ---------------------------------------------------------------- CPU and coolers


def make_cpu(M):
    p = Part("cpu")
    p.span((-20, -1.2, -20), (20, 0, 20), M["pcb_green"], bevel=0.3)
    # heat spreader with "legs" like a modern desktop CPU
    p.prism(chamfered(-16, -16, 16, 16, 2.5), -5, -2.4, M["nickel"], plane="XZ", bevel=0.8)
    for dx in (-17.5, 17.5):
        for dz in (-10, 10):
            p.span((dx - 2.5, -2.6, dz - 3), (dx + 2.5, -1.2, dz + 3), M["nickel"], bevel=0.4)
    p.span((-12, -5.3, -12), (12, -5.0, -9), M["alu"])
    for dx in (-18, 18):
        for dz in (-18, 18):
            p.span((dx - 1.2, -1.3, dz - 1.2), (dx + 1.2, -1.2, dz + 1.2), M["gold"])
    for i in range(10):
        p.span((-14 + i * 3, -1.25, -19.4), (-13 + i * 3, -1.2, -18.4), M["gold"])
    return p.build()


def fin_stack(p, M, x0, x1, pipes_x, fins_n=45, y0=-38):
    """A tower's fin stack from x0 to x1 (along the board), 124 mm tall, fins from 38 to 146 mm over the CPU,
    pierced by heat pipes at pipes_x, with folded edges and a cover with the pipe ends on top."""
    w = x1 - x0
    # the stack as one block: the site draws the fins on its faces (no shimmering of thin plates)
    p.prism(chamfered(x0, -62, x1, 62, (6, 6, 6, 6)), -146, y0, M["fins_u"], plane="XZ")
    for z in (-62.4, 62):                                                                    # its front and back faces
        p.span((x0 + 6, -146, z), (x1 - 6, y0, z + 0.4), M["fins_v"])
    del fins_n
    p.prism(chamfered(x0, -62, x1, 62, 6), -149, -146.6, M["cooler_cover"], plane="XZ", bevel=0.6)  # top cover
    p.prism(chamfered(x0 + 6, -50, x1 - 6, 50, 5), -149.5, -149, M["shroud_accent"], plane="XZ")
    for x, z in pipes_x:
        p.cyl(3.15, 4.2, (x, -149, z), M["nickel"], axis="Y", segments=14)                  # pipe ends over the cover
        p.cyl(3.9, 0.3, (x, -149.6, z), M["chip"], axis="Y", segments=14)
    del w


def make_cooler_tower(M, name="cooler_tower", dual=False):
    """Origin: the top of the CPU. A tower: copper base, heat pipes, a dense fin stack with nickel pipe ends on
    top, a fan on the front held by wire clips; dual: two stacks with a fan between them and one in front.
    158 mm from the board (the site stretches the stack to the product's height). The fans sit high enough
    to clear tall RAM; the rear stack stays clear of the case's rear fan."""
    p = Part(name)
    p.span((-20, -6, -20), (20, 0, 20), M["copper"], bevel=0.8)
    p.prism(chamfered(-28, -18, 28, 18, 5), -14, -6, M["nickel"], plane="XZ", bevel=1.0)
    p.prism(chamfered(-24, -14, 24, 14, 4), -14.6, -14, M["cooler_cover"], plane="XZ")
    p.span((-32, -11, -4.5), (32, -9, 4.5), M["black_metal"], bevel=0.6)                    # mounting bar
    for dx in (-30, 30):
        p.cyl(2.6, 5, (dx, -11, 0), M["nickel"], axis="Y", segments=12)
    stacks = [(-60, -14), (14, 60)] if dual else [(-26, 26)]
    xs = (-15, -9, -3, 3, 9, 15) if not dual else (-12, -6, 0, 6, 12, 18, -18)
    ends = {k: [] for k in range(len(stacks))}
    for k, x in enumerate(xs):
        z = (-1 if k % 2 else 1) * (6 + (k // 2) * 6) if not dual else (-45, -30, -15, 0, 15, 30, 45)[k]
        if dual:  # every pipe goes into both stacks: a U from the base
            for side, (sx0, sx1) in enumerate(stacks):
                tx = sx0 + 14 + (k % 6) * ((sx1 - sx0 - 20) / 5) if side == 0 else sx0 + 6 + (k % 6) * ((sx1 - sx0 - 12) / 5)
                p.tube([(x * 0.6, -8, z * 0.3), (x * 0.6, -18, z * 0.6), ((x * 0.6 + tx) / 2, -30, z), (tx, -40, z), (tx, -146, z)], 3.0, M["copper"], segments=10, caps=False)
                ends[side].append((tx, z))
        else:
            p.tube([(x, -8, z * 0.3), (x, -22, z * 0.6), (x, -34, z), (x, -60, z), (x, -146, z)], 3.0, M["copper"], segments=12, caps=False)
            ends[0].append((x, z))
    for side, (sx0, sx1) in enumerate(stacks):
        # the front stack of a dual tower hangs over the RAM: its fins start higher
        fin_stack(p, M, sx0, sx1, ends[side], fins_n=40 if dual and side == 0 else 45, y0=-52 if dual and side == 0 else -38)
    q = p.build()
    front_x = stacks[0][0] - 14
    fan(q, f"{name}_fan0", (front_x, -101, 0), 120, 25, "X", M, count=7, flip=True,
        frame_m=M["cooler_fan"], blade_m=M["cooler_blade"])
    if dual:
        fan(q, f"{name}_fan1", (0, -101, 0), 120, 25, "X", M, count=7, flip=True,
            frame_m=M["cooler_fan"], blade_m=M["cooler_blade"])
    # wire clips that hold the front fan on the fin stack
    c = Part(f"{name}_clips", q)
    for y in (-44, -158):
        c.tube([(front_x - 12, y, -56), (front_x + 8, y, -56), (front_x + 14, y, -50), (front_x + 14, y, 50), (front_x + 8, y, 56), (front_x - 12, y, 56)],
               0.8, M["nickel"], segments=8)
    c.build()
    return q


def make_cooler_low(M):
    """A box-style cooler: round fin heatsink, a fan on top in a round shroud with an RGB ring.
    It stays inside the keep-out circle around the socket (radius KEEPOUT)."""
    p = Part("cooler_low")
    p.span((-20, -4, -20), (20, 0, 20), M["copper"], bevel=0.8)
    p.cyl(17, 14, (0, -11, 0), M["alu"], axis="Y", segments=32)
    for i in range(40):
        a = 2 * math.pi * i / 40
        p.box((1.1, 28, 22), (math.cos(a) * 29, -18, math.sin(a) * 29), M["alu"], rotate=("Y", -math.degrees(a) + 12))
    p.ring(40, 43, 30, (0, -18, 0), M["black_metal"], axis="Y", segments=64)
    p.ring(37, 43, 4, (0, -34, 0), M["rgb"], axis="Y", segments=64)
    p.span((-43, -4, -7), (43, -1, 7), M["black_metal"], bevel=0.6)
    for dx in (-39, 39):
        p.cyl(2.6, 4, (dx, -4.5, 0), M["nickel"], axis="Y", segments=12)
    q = p.build()
    fan(q, "cooler_low", (0, -42, 0), 82, 12, "Y", M, count=11, clear=True, flip=True, style="round")
    return q


def make_cooler_flat(M):
    """A flat top-flow cooler (Intel Laminar): a short round heatsink, a fan under a flat cover with
    four spokes and a ring. Lower than the round one, inside the keep-out circle."""
    p = Part("cooler_flat")
    p.span((-18, -4, -18), (18, 0, 18), M["copper"], bevel=0.8)
    p.cyl(15, 10, (0, -9, 0), M["alu"], axis="Y", segments=32)
    for i in range(48):
        a = 2 * math.pi * i / 48
        p.box((0.9, 18, 24), (math.cos(a) * 28, -13, math.sin(a) * 28), M["alu"], rotate=("Y", -math.degrees(a)))
    p.ring(40, 42.5, 20, (0, -16, 0), M["cooler_cover"], axis="Y", segments=64)
    p.ring(36, 42.5, 2.0, (0, -27, 0), M["cooler_cover"], axis="Y", segments=64)
    p.ring(34.5, 36, 1.6, (0, -27.4, 0), M["rgb"], axis="Y", segments=64)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        p.box((36, 1.4, 4), (math.cos(a) * 18, -27.6, math.sin(a) * 18), M["cooler_cover"], rotate=("Y", -math.degrees(a)))
    p.cyl(10, 1.6, (0, -27.6, 0), M["cooler_cover"], axis="Y", segments=32)
    p.cyl(7, 0.3, (0, -28.5, 0), M["shroud_accent"], axis="Y", segments=24)
    p.span((-43, -4, -7), (43, -1, 7), M["black_metal"], bevel=0.6)
    q = p.build()
    fan(q, "cooler_flat", (0, -22, 0), 76, 8, "Y", M, count=9, flip=True, style="round",
        frame_m=M["cooler_fan"], blade_m=M["cooler_blade"])
    return q


def make_aio_pump_square(M):
    """A square pump block (Arctic Liquid Freezer, DeepCool): rounded square body, a mirror cap in an RGB frame."""
    p = Part("aio_pump_square")
    p.span((-24, -6, -24), (24, 0, 24), M["copper"], bevel=1)
    p.span((-34, -10, -4.5), (34, -7, 4.5), M["black_metal"], bevel=0.6)
    p.prism(rrect(62, 62, 9, n=5), -26, -6, M["black_metal"], plane="XZ", bevel=1.2)
    p.prism(rrect(58, 58, 7, n=5), -28.4, -26, M["rgb"], plane="XZ")
    p.prism(rrect(52, 52, 5, n=5), -29.2, -28.4, M["mirror"], plane="XZ")
    p.cyl(9, 0.3, (0, -29.5, 0), M["shroud_accent"], axis="Y", segments=24)
    for z in (-14, 14):
        p.cyl(6.5, 6, (33, -16, z), M["black_metal"], axis="X", segments=20)
        p.tube([(36, -16, z), (39, -16, z), (40, -19, z), (40, -24, z)], 5.0, M["black_metal"], segments=16)
        p.cyl(6.0, 4, (40, -26, z), M["nickel"], axis="Y", segments=20)
    q = p.build()
    empty("hose_a", (40, -28, -14), q)
    empty("hose_b", (40, -28, 14), q)
    return q


def make_aio_pump(M):
    """The pump block: copper plate, a body with a mirror cap and an RGB ring, two fittings looking out
    of the open side (the hoses go out first, then up to the radiator)."""
    p = Part("aio_pump")
    p.span((-24, -6, -24), (24, 0, 24), M["copper"], bevel=1)
    p.span((-34, -10, -4.5), (34, -7, 4.5), M["black_metal"], bevel=0.6)
    p.cyl(31, 22, (0, -17, 0), M["black_metal"], axis="Y", segments=56, bevel=1.5)
    p.cyl(29, 3, (0, -29.5, 0), M["alu_dark"], axis="Y", segments=56, radius2=27)
    p.ring(26.5, 30.5, 2.2, (0, -30.5, 0), M["rgb"], axis="Y", segments=64)
    p.cyl(26, 1.4, (0, -31, 0), M["mirror"], axis="Y", segments=56)
    p.cyl(8, 0.3, (0, -31.8, 0), M["shroud_accent"], axis="Y", segments=24)
    for z in (-14, 14):                                                                      # fittings on the side
        p.cyl(6.5, 6, (28, -16, z), M["black_metal"], axis="X", segments=20)
        p.tube([(31, -16, z), (36, -16, z), (39, -19, z), (40, -24, z)], 5.0, M["black_metal"], segments=16)
        p.cyl(6.0, 4, (40, -26, z), M["nickel"], axis="Y", segments=20)
    q = p.build()
    empty("hose_a", (40, -28, -14), q)
    empty("hose_b", (40, -28, 14), q)
    return q


def make_radiator(M, size):
    """Origin: rear end, top center. Hangs from the top: a core of size mm with fins and flat tubes,
    end tanks (17 mm each) and fans under the core."""
    name = f"radiator_{size}"
    p = Part(name)
    core = size
    length = size + 34
    p.span((-length + 17, -60, -26), (-17, -57, -1), M["black_metal"])                       # side rails
    p.span((-length + 17, 57, -26), (-17, 60, -1), M["black_metal"])
    p.span((-length + 17, -57, -2), (-17, 57, -1), M["black_metal"])                         # top plate (hidden)
    p.span((-length + 17, -57, -25.5), (-17, 57, -2), M["fins_u"])                          # the core: fins and flat tubes
    for k in range(12):
        y = -52 + k * (104 / 11)
        p.span((-length + 17, y - 0.7, -25.8), (-17, y + 0.7, -25.5), M["black_metal"])
    p.span((-length + 17, -57, -26.6), (-17, 57, -26), M["fan_frame"])                       # fan gasket rim
    for x0 in (-length, -17):                                                                # end tanks
        p.prism(chamfered(-60, -27, 60, 0, (3, 3, 6, 6)), x0, x0 + 17, M["plastic"], plane="YZ", bevel=1.2)
    p.prism(chamfered(-40, -22, 40, -6, 2), -length - 0.6, -length, M["shroud_accent"], plane="YZ")
    for y in (-40, -16):                                                                     # inlets under the rear tank
        p.cyl(6.5, 4, (-10, y, -28.5), M["black_metal"], segments=20)
    q = p.build()
    for i in range(size // 120):
        fan(q, f"{name}_{i}", (-17 - 60 - i * 120, 0, -27 - 12.5), 120, 25, "Z", M, clear=True, rim_rgb=True, flip=True)
    empty("hose_a", (-10, -40, -30.5), q)   # the lower pump fitting goes to the outer inlet: the hoses never cross
    empty("hose_b", (-10, -16, -30.5), q)
    return q


# ---------------------------------------------------------------- RAM, GPU, PSU, drives


def make_ram(M, name="ram", kind="rgb"):
    """Origin: the middle of the contact edge. The stick stands out of the board toward -y.
    kind rgb: tall heatspreaders with a stepped profile and a light bar (Trident Z5 RGB, Delta RGB);
    lp: low profile, a notched top (Vengeance LPX, Fury Beast); plain: a thin flat spreader (Crucial Pro)."""
    p = Part(name)
    p.span((-0.6, -32, -66.5), (0.6, 0, 66.5), M["pcb"], bevel=0.2)
    p.span((-0.62, -2.2, -66.5), (0.62, 0, -6), M["gold"])
    p.span((-0.62, -2.2, -4), (0.62, 0, 66.5), M["gold"])
    if kind == "rgb":
        profile = [(-3, -66.8), (-3, 66.8), (-36, 66.8), (-38.5, 62), (-38.5, 30), (-36.5, 26), (-36.5, -20), (-38.5, -24),
                   (-38.5, -62), (-36, -66.8)]
        t = 2.2
    elif kind == "lp":
        profile = [(-3, -66.8), (-3, 66.8), (-31, 66.8), (-32.5, 64), (-32.5, 8), (-30.5, 4), (-30.5, -4), (-32.5, -8),
                   (-32.5, -64), (-31, -66.8)]
        t = 1.8
    else:
        profile = [(-3, -66.5), (-3, 66.5), (-30.5, 66.5), (-31, 65.5), (-31, -65.5), (-30.5, -66.5)]
        t = 0.9
    for side in (-1, 1):
        x0, x1 = side * 0.7, side * (0.7 + t)
        lo, hi = min(x0, x1), max(x0, x1)
        p.prism([(y, z) for y, z in profile], lo, hi, M["ram_spreader"], plane="YZ", bevel=0.4 if t > 1 else 0.2)
        a, b = (hi, hi + 0.35) if side > 0 else (lo - 0.35, lo)
        if kind == "rgb":  # an angled inlay and a bright edge
            inlay = [(-10, -50), (-10, 38), (-27, 50), (-30, 50), (-30, -40), (-20, -50)]
            p.prism([(y, z) for y, z in inlay], a, b, M["black_metal"], plane="YZ")
            a2, b2 = (hi, hi + 0.7) if side > 0 else (lo - 0.7, lo)
            p.prism([(y, z) for y, z in [(-32, 46), (-32, 52), (-35, 56), (-35, 30)]], a2, b2, M["shroud_accent"], plane="YZ")
        elif kind == "lp":  # pressed ribs
            for k in range(5):
                z = -50 + k * 8
                p.prism([(-24, z), (-24, z + 3), (-28, z + 7), (-28, z + 4)], a, b, M["shroud_accent"], plane="YZ")
        else:  # a sticker
            p.prism([(-8, -55), (-8, 55), (-26, 55), (-26, -55)], a, b, M["label_light"], plane="YZ")
    if kind == "rgb":
        p.prism(rrect(5.2, 128, 1.6, cx=0, cy=0), -38.5, -44, M["rgb"], plane="XZ")           # light bar
        p.span((-2.7, -38.6, -66), (2.7, -36.4, 66), M["black_metal"])
    else:
        top = min(y for y, z in profile)
        p.span((-0.7, top, -60), (0.7, top + 1, 60), M["ram_spreader"])                        # the spreaders' clip
    q = p.build()
    p2 = Part(f"label_{name}", q, auto_uv=False)
    xl = -(0.7 + t) - 0.45
    zl = 44 if kind != "plain" else 40
    yl = (-26, -12) if kind == "rgb" else (-24, -12)
    p2.quad([(xl, yl[0], -zl), (xl, yl[0], zl), (xl, yl[1], zl), (xl, yl[1], -zl)], M["label"])
    p2.build()
    return q


GPU_STYLES = ("plain", "angular", "trio", "wind", "flow")


def make_gpu(M, name, length, fans_count, fan_size):
    """Origin: the inner face of the bracket (it touches the case's rear sheet), at the PCIe slot.
    The card lies across the case toward -x, its fans look down (-z), the backplate up.
    The site stretches the card along x to the product's length (and along z to its thickness);
    fixed_* pieces keep their size. The common body is one object; the brand styles are children
    style_<name> (GPU_STYLES), the site shows one of them."""
    p = Part(name)
    L = length
    y0, y1 = -7, -121                  # the cooler body: from near the board to the top edge
    pz0, pz1 = -51.5, -48              # the fan plate
    pcb_end = L - 6 if fans_count == 1 else L * 0.72
    flow = fans_count > 1
    # PCB and its top edge
    p.span((-pcb_end, -112, -1.6), (-4, -4, 0), M["pcb"], bevel=0.3)
    # backplate: brushed plate with vents, screws and a flow-through opening at the end
    bp0, bp1 = 0.2, 2.6
    open_x0, open_x1 = -L + 14, -pcb_end - 4
    holes = [(open_x0, open_x1, -106, -20)] if flow else []
    grid_sheet(p, "Z", bp0, bp1, (-L + 1, -2, -121, -9), holes, M["gpu_back"])
    p.span((-L + 1, -121.6, bp0), (-2, -121, bp1 + 0.4), M["gpu_back"], bevel=0.3)           # folded edge
    for k in range(6):  # vent slots
        x = -24 - k * 6
        p.span((x - 2.2, -98, bp1 - 0.1), (x, -36, bp1 + 0.35), M["chip"])
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cyl(2.2, 1.0, (-L * 0.3 + sx * 26, -64 + sy * 26, bp1 + 0.4), M["nickel"], segments=10)
    p.prism(chamfered(-L * 0.3 - 18, -82, -L * 0.3 + 18, -46, 4), bp1, bp1 + 0.5, M["shroud_accent"], plane="XY")
    # fins: plates across the card, under the PCB; under the flow-through opening they reach the backplate
    p.span((-L + 6, -117, -45), (-6, -11, -2.4), M["fins_u"])                                 # the fin stack
    if flow:
        p.span((open_x0 + 1, -105, -2.4), (open_x1 - 1, -21, 1.6), M["fins_u"])
    p.span((-L + 6, -117, -46), (-6, -11, -45), M["alu"])                                    # fin base
    # heat pipes along the top edge, bent back into the stack at both ends
    for k in range(4):
        z = -12 - k * 7.5
        xa, xb = -22 - k * 6, -L + 18 + k * 5
        p.tube([(xa, -96, z), (xa, -114, z), (xa - 6, -119, z), (xb + 6, -119, z), (xb, -114, z), (xb, -96, z)], 2.8, M["nickel"], segments=12, caps=False)
    # the fan plate with round holes
    fan_pitch = (L - 24) / fans_count
    cells_x0 = -L + 14
    hole_r = fan_size / 2 + 1.2
    for i in range(fans_count):
        cx = cells_x0 + fan_pitch * (i + 0.5)
        p.rect_frame(fan_pitch, y0 - y1, hole_r, pz1 - pz0, (cx, (y0 + y1) / 2, (pz0 + pz1) / 2), M["shroud"], segments=56)
        p.ring(hole_r, hole_r + 2.2, 1.2, (cx, (y0 + y1) / 2, pz0 - 0.6), M["shroud_accent"], segments=56)
    p.prism(chamfered(cells_x0 + fan_pitch * fans_count, y1, -1, y0, 0), pz0, pz1, M["shroud"], plane="XY")
    p.prism(chamfered(-L, y1, cells_x0, y0, (0, 10, 10, 0)), pz0, pz1, M["shroud"], plane="XY")
    # front end cap, the side toward the board, the outer side: a solid lower band, open over the fins
    p.prism(chamfered(-L, pz0, -L + 10, -4, (0, 6, 8, 0)), y1, y0, M["shroud"], plane="XZ", bevel=0.6)
    p.span((-L + 6, y0 - 3, pz1), (-1, y0, -8), M["shroud"])
    p.prism([(-L + 8, pz1), (-1, pz1), (-1, -38), (-L + 8, -38)], y1, y1 + 3, M["shroud"], plane="XZ")
    p.prism([(-L + 8, -12), (-1, -12), (-1, -5), (-L + 8, -5)], y1, y1 + 3, M["shroud"], plane="XZ")
    # the power socket on the top edge
    conn_x = -pcb_end + (14 if flow else 40)
    p.span((conn_x - 36, -121, -8), (conn_x + 2, -110, 0), M["chip"], bevel=0.6)
    for i in range(8):
        for j in range(2):
            p.span((conn_x - 34 + i * 4.4, -121.2, -7 + j * 3.6), (conn_x - 31 + i * 4.4, -121, -4.4 + j * 3.6), M["slot"])
    q = p.build()
    # the parts that keep their size: bracket, PCIe contact
    f = Part(f"fixed_{name}", q)
    f.span((-1.4, -126, -54), (0, 4, 4), M["slot_steel"], bevel=0.2)
    f.span((-1.5, -122, -48), (-1.4, -10, -2), M["mesh"])
    f.span((-10, -126, 2.6), (0, -118, 4), M["slot_steel"])
    for k in range(3):  # display outputs behind the bracket
        f.span((-9, -105 + k * 22, -14), (-1.4, -91 + k * 22, -6), M["chip"])
    f.span((-97, -4, -1.7), (-13, 3, 0.1), M["gold"])
    f.span((-97, -4, -1.5), (-13, 2.5, -0.1), M["pcb"])
    f.build()
    # fans under the card, axis Z (they blow up into the heatsink), hub caps looking down
    fan_centers = [cells_x0 + fan_pitch * (i + 0.5) for i in range(fans_count)]
    for i, cx in enumerate(fan_centers):
        fan(q, f"{name}_{i}", (cx, (y0 + y1) / 2, (pz0 + pz1) / 2 + 1.0), fan_size, 10, "Z", M, count=11, flip=True, style="open")
    for style in GPU_STYLES:
        gpu_style(q, M, name, style, L, fan_centers, fan_pitch, hole_r, (y0, y1), (pz0, pz1))
    p3 = Part(f"label_{name}", q, auto_uv=False)
    lx0, lx1 = -L * 0.92 + 8, -L * 0.62 - 4
    p3.quad([(lx0, y1 - 2.7, -36), (lx1, y1 - 2.7, -36), (lx1, y1 - 2.7, -26), (lx0, y1 - 2.7, -26)], M["label"])
    p3.build()
    empty("cable_gpu", (conn_x - 17, -122, -4), q)
    return q


def gpu_style(q, M, name, style, L, fan_centers, fan_pitch, hole_r, ys, pzs):
    """The styled pieces of a card's shroud (one object per style): angled panels on the outer side
    and ribs on the fan plate. The outer side is at y1, the plate's face at pz0."""
    y0, y1 = ys
    pz0, pz1 = pzs
    s = Part(f"style_{name}_{style}", q)
    acc, sh, rgb = M["shroud_accent"], M["shroud"], M["rgb"]
    yo = y1 - 1.4                       # just outside the outer side
    gaps = [fan_centers[0] - fan_pitch / 2] + [(a + b) / 2 for a, b in zip(fan_centers, fan_centers[1:])] + [fan_centers[-1] + fan_pitch / 2]
    clamp = lambda x: min(max(x, -L + 9), -3)  # noqa: E731
    if style == "plain":
        # a thin accent line along the lower band and small chevrons between the fans
        s.prism([(-L + 10, -44), (-4, -44), (-4, -42.6), (-L + 10, -42.6)], yo, y1, acc, plane="XZ")
        for gx in gaps[1:-1]:
            s.prism([(gx - 6, -38), (gx + 6, -38), (gx + 2, -30), (gx - 2, -30)], yo, y1, acc, plane="XZ")
        s.span((-L * 0.6, yo - 0.2, -10.5), (-L * 0.25, y1, -7.5), rgb)
    elif style == "angular":
        # heavy faceted plates (ASUS TUF / ROG): wedges over the lower band and across the fan plate
        for i, gx in enumerate(gaps):
            w = 22
            pts = [(clamp(gx - w), pz1), (clamp(gx + w * 0.4), pz1), (clamp(gx + w * 0.9), -30), (clamp(gx + w * 0.2), -14), (clamp(gx - w * 0.6), -14), (clamp(gx - w * 0.2), -30)]
            s.prism(pts, yo - 1.0, y1, sh if i % 2 else acc, plane="XZ", bevel=0.3)
        for gx in gaps:
            for side in (-1, 1):
                yy = y0 - 3 if side > 0 else y1 + 3
                rib = [(clamp(gx - 5), yy), (clamp(gx + 5), yy), (clamp(gx + 2), yy - side * 26), (clamp(gx - 2), yy - side * 26)]
                if side < 0:
                    rib = list(reversed(rib))
                s.prism(rib, pz0 - 1.6, pz0, acc, plane="XY")
        s.span((-L * 0.55, yo - 1.2, -12), (-L * 0.15, yo - 0.4, -8.5), rgb, bevel=0.3)
        s.prism(chamfered(-L, pz0 - 1.2, -L + 16, -6, (0, 6, 8, 0)), y1 - 0.8, y1 + 8, acc, plane="XZ")
    elif style == "trio":
        # MSI: sweeping wings around each fan on the plate, an RGB arc on the outer side
        for cx in fan_centers:
            for a0 in (0.15, math.pi + 0.15):
                pts = []
                for k in range(9):
                    a = a0 + k * (math.pi * 0.55 / 8)
                    pts.append((cx + (hole_r + 2.5) * math.cos(a), (y0 + y1) / 2 + (hole_r + 2.5) * math.sin(a)))
                for k in reversed(range(9)):
                    a = a0 + k * (math.pi * 0.55 / 8)
                    pts.append((cx + (hole_r + 7) * math.cos(a), (y0 + y1) / 2 + (hole_r + 7) * math.sin(a)))
                pts = [(min(max(x, -L + 2), -2), min(max(y, y1 + 1), y0 - 1)) for x, y in pts]
                s.prism(pts, pz0 - 1.4, pz0, acc, plane="XY")
        arc = [(x, -9 - 5 * math.sin(math.pi * (x + L * 0.85) / (L * 0.7))) for x in [(-L * 0.85) + k * (L * 0.7) / 16 for k in range(17)]]
        s.prism(arc + [(x, z - 2.6) for x, z in reversed(arc)], yo - 0.4, y1, rgb, plane="XZ")
        s.prism([(-L + 10, -44), (-4, -44), (-4, -39), (-L + 30, -39)], yo - 0.8, y1, acc, plane="XZ", bevel=0.3)
    elif style == "wind":
        # Gigabyte: blade-like diagonal stripes between the fans and along the outer side
        for gx in gaps:
            stripe = [(clamp(gx - 10), y1 + 4), (clamp(gx - 4), y1 + 4), (clamp(gx + 10), y0 - 4), (clamp(gx + 4), y0 - 4)]
            s.prism(stripe, pz0 - 1.2, pz0, acc, plane="XY")
        for k in range(int(L / 26)):
            x = -10 - k * 26
            if x - 14 < -L + 8:
                break
            s.prism([(x, -44), (x - 3, -44), (x - 14, -38.5), (x - 11, -38.5)], yo - 0.6, y1, acc, plane="XZ")
        s.span((-L * 0.5, yo - 0.4, -10.5), (-L * 0.12, y1, -8), rgb)
    else:  # flow: a smooth metal body (Intel Arc LE, Founders): a full outer cover with a light bar
        s.prism([(-L + 4, pz0 - 0.6), (-2, pz0 - 0.6), (-2, -4), (-L + 12, -4), (-L + 4, -12)], yo - 0.8, y1, acc, plane="XZ", bevel=0.8)
        s.span((-L * 0.75, yo - 1.4, -24), (-L * 0.25, yo - 0.8, -21), rgb, bevel=0.4)
        for cx in fan_centers:
            s.ring(hole_r + 2.2, hole_r + 4.5, 1.6, (cx, (y0 + y1) / 2, pz0 - 0.8), acc, segments=56)
        s.prism(chamfered(-L + 2, y1 + 2, -2, y0 - 2, 6), pz0 - 0.5, pz0, acc, plane="XY")
    s.build()


def make_psu(M):
    """Origin: rear face, the edge nearer the tray, bottom. Extends to -x (front), -y (open side), +z.
    A fan grill on top, modular sockets in front, a honeycomb grill, the plug and the switch at the rear."""
    p = Part("psu")
    Lp, Wp, Hp = 160, 150, 86
    p.span((-Lp, -Wp, 0), (0, 0, Hp), M["black_metal"], bevel=1.6, segments=2)
    fx, fy = -Lp / 2 - 6, -Wp / 2
    # front: modular sockets in a recessed panel
    p.span((-Lp - 0.6, -Wp + 8, 6), (-Lp + 0.2, -8, Hp - 6), M["chip"], bevel=0.4)
    sockets = [(-Wp + 14, 10, 24, 30), (-Wp + 14, 46, 24, 30)] + [(-Wp + 46 + k * 22, 12, 16, 18) for k in range(4)] + \
              [(-Wp + 46 + k * 22, 40, 16, 18) for k in range(4)]
    for y, z, w, h in sockets:
        p.span((-Lp - 2.2, y, z), (-Lp - 0.6, y + w, z + h), M["plastic"], bevel=0.4)
        p.span((-Lp - 2.4, y + 1.5, z + 1.5), (-Lp - 2.2, y + w - 1.5, z + h - 1.5), M["slot"])
    # rear: honeycomb grill, plug, switch
    p.span((0, -Wp + 8, 8), (0.8, -54, Hp - 8), M["grill"])
    p.prism(chamfered(-46, 28, -16, 50, (0, 0, 4, 4)), 0, 1.2, M["chip"], plane="YZ")
    p.prism(chamfered(-42, 31, -20, 47, (0, 0, 3, 3)), 1.2, 1.5, M["slot"], plane="YZ")
    p.span((0, -44, 58), (1.0, -28, 70), M["chip"], bevel=0.3)
    p.span((1.0, -42, 61), (1.7, -30, 67), M["plastic_grey"], bevel=0.2)
    # side: an embossed frame around the sticker
    p.span((-Lp + 8, -Wp - 0.4, 10), (-8, -Wp + 0.2, Hp - 10), M["alu_dark"], bevel=0.6)
    for x in (-Lp + 3, -3):
        p.span((x - 1, -Wp - 0.5, 4), (x + 1, -Wp, Hp - 4), M["accent"])
    q = p.build()
    # the fan on top behind a wire grill: keeps its round shape when the site makes the PSU longer
    f = Part("fixed_psufan", q, location=(fx, fy, Hp))
    f.cyl(64, 0.6, (0, 0, 0.1), M["chip"], segments=56)
    for r in (16, 28, 40, 52, 62):
        f.ring(r - 0.7, r + 0.7, 1.6, (0, 0, 0.7), M["nickel"] if r == 62 else M["black_metal"], segments=48)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        f.box((60, 1.4, 1.4), (math.cos(a) * 32, math.sin(a) * 32, 0.9), M["black_metal"], rotate=("Z", math.degrees(a)))
    f.cyl(12, 1.6, (0, 0, 0.9), M["fan_cap"], segments=28)
    f.build()
    p2 = Part("label_psu", q, auto_uv=False)
    p2.quad([(-Lp + 12, -Wp - 0.7, 14), (-12, -Wp - 0.7, 14), (-12, -Wp - 0.7, Hp - 14), (-Lp + 12, -Wp - 0.7, Hp - 14)], M["label"])
    p2.build()
    return q


def make_m2(M):
    """Origin: the contact end (rear), the drive goes toward -x, flat on the board."""
    p = Part("m2")
    p.span((-80, -0.8, -11), (0, 0, 11), M["pcb"], bevel=0.2)
    p.span((-3.5, -0.85, -10), (0, 0.05, 10), M["gold"])
    p.span((-3.6, -0.9, 4.5), (0.2, 0.1, 6), M["slot"])                                     # the key notch
    p.span((-22, -2.2, -8), (-8, -0.8, 8), M["chip"], bevel=0.3)
    for x0 in (-48, -72):
        p.span((x0, -2.2, -9), (x0 + 20, -0.8, 9), M["chip"], bevel=0.3)
    p.span((-79, -2.5, -10.5), (-6, -2.2, 10.5), M["label_light"])
    p.cyl(2.8, 0.6, (-80, -1.1, 0), M["gold"], axis="Y", segments=14)
    q = p.build()
    p2 = Part("label_m2", q, auto_uv=False)
    p2.quad([(-76, -2.9, -9), (-8, -2.9, -9), (-8, -2.9, 9), (-76, -2.9, 9)], M["label"], uv=((0, 0), (1, 0), (1, 1), (0, 1)))
    p2.build()
    return q


def make_m2_heatsink(M):
    """An M.2 drive with its own finned heatsink (the label sits on top of it)."""
    p = Part("m2_hs")
    p.span((-80, -0.8, -11), (0, 0, 11), M["pcb"], bevel=0.2)
    p.span((-3.5, -0.85, -10), (0, 0.05, 10), M["gold"])
    p.prism(chamfered(-79, -10.8, -4, 10.8, 1.5), -3.2, -0.8, M["black_metal"], plane="XZ", bevel=0.3)
    for k in range(11):
        z = -9.5 + k * 1.9
        p.span((-76, -8.6, z), (-30, -3.2, z + 0.9), M["black_metal"])
    p.prism(chamfered(-28, -10, -6, 10, 2), -6.4, -3.2, M["black_metal"], plane="XZ", bevel=0.3)
    q = p.build()
    p2 = Part("label_m2_hs", q, auto_uv=False)
    p2.quad([(-27, -6.8, -9), (-7, -6.8, -9), (-7, -6.8, 9), (-27, -6.8, 9)], M["label"])
    p2.build()
    return q


def make_ssd(M):
    """2.5" SATA SSD. Origin: front end, middle, bottom; lies flat in the drive cage."""
    p = Part("ssd")
    p.prism(chamfered(0, -35, 100, 35, 2), 0, 7, M["alu_dark"], plane="XY", bevel=0.8)
    p.span((96, -22, 1.5), (100.6, 14, 5.5), M["chip"], bevel=0.3)
    p.span((100, -20, 2.2), (100.8, -4, 4.8), M["gold"])
    for x in (14, 90):
        for y in (-35.3, 35):
            p.cyl(1.6, 0.3, (x, y + 0.15, 3.5), M["nickel"], axis="Y", segments=10)
    q = p.build()
    p2 = Part("label_ssd", q, auto_uv=False)
    p2.quad([(8, 30, 7.4), (92, 30, 7.4), (92, -30, 7.4), (8, -30, 7.4)], M["label"])
    p2.build()
    return q


def make_hdd(M):
    """3.5" HDD. Origin: front end, middle, bottom."""
    p = Part("hdd")
    p.span((0, -50.8, 0), (147, 50.8, 22), M["alu"], bevel=1.4, segments=3)
    p.prism(chamfered(2, -49, 145, 49, (10, 4, 4, 10)), 22, 26, M["alu"], plane="XY", bevel=0.8)
    p.cyl(17, 0.6, (48, 0, 26.1), M["nickel"], segments=40)
    p.cyl(9, 0.4, (110, 22, 26.1), M["nickel"], segments=24)
    for x, y in ((6, -45), (6, 45), (141, -45), (141, 45), (48, -14), (48, 14), (34, 0), (62, 0)):
        p.cyl(1.6, 0.6, (x, y, 26.2), M["black_metal"], segments=8)
    p.span((140, -40, -0.4), (147.6, 40, 1.4), M["pcb_green"])
    p.span((147, -36, 4), (147.8, 10, 12), M["chip"], bevel=0.3)
    for x in (20, 80, 130):
        for y in (-51.2, 50.6):
            p.cyl(1.8, 0.6, (x, y + 0.3, 7), M["black_metal"], axis="Y", segments=10)
    q = p.build()
    p2 = Part("label_hdd", q, auto_uv=False)
    p2.quad([(70, 40, 26.7), (136, 40, 26.7), (136, -40, 26.7), (70, -40, 26.7)], M["label_light"])
    p2.build()
    return q


# ---------------------------------------------------------------- main


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = materials()
    for name, spec in CASES.items():
        make_case(M, name, **spec)
    for name, spec in BOARDS.items():
        make_board(name, M, **spec)
    make_cpu(M)
    make_cooler_tower(M)
    make_cooler_tower(M, "cooler_dual", dual=True)
    make_cooler_low(M)
    make_aio_pump(M)
    make_aio_pump_square(M)
    make_cooler_flat(M)
    make_radiator(M, 240)
    make_radiator(M, 360)
    make_ram(M)
    make_ram(M, "ram_lp", "lp")
    make_ram(M, "ram_plain", "plain")
    make_gpu(M, "gpu1", 175, 1, 92)
    make_gpu(M, "gpu2s", 200, 2, 82)
    make_gpu(M, "gpu2", 250, 2, 96)
    make_gpu(M, "gpu3", 320, 3, 88)
    make_psu(M)
    make_m2(M)
    make_m2_heatsink(M)
    make_ssd(M)
    make_hdd(M)
    # every part at the world origin: the site puts them in place
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT), export_format="GLB", export_apply=True, export_yup=True,
        export_materials="EXPORT", export_cameras=False, export_lights=False, export_extras=False,
        export_animations=False,
        export_draco_mesh_compression_enable=DRACO, export_draco_mesh_compression_level=7,
        export_draco_position_quantization=14, export_draco_normal_quantization=10,
        export_draco_texcoord_quantization=12,
    )
    tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print(f"made {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}: {OUT.stat().st_size // 1024} KB, {tris} faces")


if __name__ == "__main__" or "bpy" in sys.modules:
    main()
