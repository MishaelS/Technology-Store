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
    rotor*    fan blades: the site spins them around their own Y axis (Blender Z) when the build is powered on
    label*    flat panels with UVs: the site paints the brand / wattage on them
Materials named RGB* glow and change color on the site; LED* light up when the build is powered on.
"""

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "resources" / "models" / "builder.glb"

# ---------------------------------------------------------------- case sheets, mm (sizes: CASES below)
T = 2.0                            # steel sheet
FLOOR = 22.0                       # inner floor: feet + bottom sheet

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
        "mesh": mat("CaseMesh", "#0E0F12", metal=0.5, rough=0.35, double=True),
        "accent": mat("CaseAccent", "#3A3F48", metal=0.8, rough=0.25),
        "rubber": mat("Rubber", "#101114", rough=0.85),
        "pcb": mat("PCB", "#252A33", rough=0.5, coat=0.3),
        "pcb_green": mat("PCBGreen", "#0F3B2A", rough=0.5, coat=0.3),
        "slot": mat("Slot", "#2A2D33", rough=0.6),
        "slot_steel": mat("SlotSteel", "#B9BEC6", metal=1.0, rough=0.22),
        "alu": mat("Aluminium", "#9CA3AD", metal=1.0, rough=0.3),
        "alu_dark": mat("AluminiumDark", "#3B4048", metal=0.9, rough=0.32),
        "black_metal": mat("BlackMetal", "#17191D", metal=0.7, rough=0.35),
        "copper": mat("Copper", "#C9774A", metal=1.0, rough=0.25),
        "nickel": mat("Nickel", "#D4D8DE", metal=1.0, rough=0.16),
        "gold": mat("Gold", "#D9A441", metal=1.0, rough=0.25),
        "chip": mat("Chip", "#0B0C0E", rough=0.35),
        "plastic": mat("Plastic", "#1C1E22", rough=0.45),
        "plastic_grey": mat("PlasticGrey", "#5A606A", rough=0.45),
        "white": mat("White", "#E9ECEF", rough=0.4),
        "fan_frame": mat("FanFrame", "#16181C", rough=0.5),
        "fan_blade": mat("FanBlade", "#1F2228", rough=0.35, double=True),
        "fan_blade_clear": mat("RGBFanBlade", "#C8D0DA", rough=0.2, emit="#7C9CFF", strength=0.0, double=True),
        "rgb": mat("RGB", "#E6ECF5", rough=0.3, emit="#7C9CFF", strength=0.0),
        "led": mat("LEDPower", "#2C3038", rough=0.3, emit="#4DABF7", strength=0.0),
        "label": mat("LabelDark", "#1A1D22", rough=0.5),
        "label_light": mat("LabelLight", "#EDEFF2", rough=0.45),
        "cable": mat("Cable", "#101113", rough=0.6),
        "glass": mat("Glass", "#0B0D10", metal=0.0, rough=0.05, coat=1.0),
    }


# ---------------------------------------------------------------- geometry helpers


class Part:
    """One mesh object filled piece by piece (one draw call per material in the browser)."""

    def __init__(self, name, parent=None, location=(0, 0, 0)):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.slots: list[bpy.types.Material] = []
        self.parent = parent
        self.location = Vector(location)

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
        faces = []
        for i in range(segments):
            j = (i + 1) % segments
            ti, to = top
            bi, bo = bottom
            faces += [self.bm.faces.new((ti[i], to[i], to[j], ti[j])), self.bm.faces.new((bi[j], bo[j], bo[i], bi[i])),
                      self.bm.faces.new((to[i], bo[i], bo[j], to[j])), self.bm.faces.new((ti[j], bi[j], bi[i], ti[i]))]
        self._orient(verts, center, axis)
        fs = self._finish(verts, m)
        for f in fs:
            f.smooth = True
        return fs

    def square_frame(self, size, r, depth, center, m, axis="Z", segments=48):
        """A square plate with a round hole: the frame of a fan."""
        verts, rows = [], []
        for z in (depth / 2, -depth / 2):
            inner, outer = [], []
            for i in range(segments):
                a = 2 * math.pi * i / segments
                c, s = math.cos(a), math.sin(a)
                k = (size / 2) / max(abs(c), abs(s))
                inner.append(self.bm.verts.new((r * c, r * s, z)))
                outer.append(self.bm.verts.new((k * c, k * s, z)))
            rows.append((inner, outer))
            verts += inner + outer
        (ti, to), (bi, bo) = rows
        for i in range(segments):
            j = (i + 1) % segments
            self.bm.faces.new((ti[i], to[i], to[j], ti[j]))
            self.bm.faces.new((bi[j], bo[j], bo[i], bi[i]))
            self.bm.faces.new((to[i], bo[i], bo[j], to[j]))
            self.bm.faces.new((ti[j], bi[j], bi[i], ti[i]))
        self._orient(verts, center, axis)
        return self._finish(verts, m)

    def tube(self, points, radius, m, segments=14):
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
        self.bm.faces.new(list(reversed(rings[0])))
        self.bm.faces.new(rings[-1])
        fs = self._finish([v for r in rings for v in r], m)
        for f in fs:
            f.smooth = True
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
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=0.001)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
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


AXIS_TURN = {"X": Matrix.Rotation(math.pi / 2, 3, "Y"), "Y": Matrix.Rotation(-math.pi / 2, 3, "X"), "Z": Matrix.Identity(3)}


def fan(parent, name, center, size, depth, axis, M, blades=9, clear=False, rim_rgb=False):
    """A fan: frame with a round hole, struts and motor on the back, and a rotor that spins.
    Built around Z and turned to axis ("X", "Y" or "Z": the airflow); the rotor's own Z (glTF Y) is that axis."""
    r = size / 2 - 3.5
    frame = Part(f"{name}_frame", parent)
    frame.square_frame(size, r, depth, (0, 0, 0), M["fan_frame"])
    if rim_rgb:
        frame.ring(r - 1.4, r + 0.2, depth * 0.72, (0, 0, 0), M["rgb"])
    back = -(depth / 2 - 2)
    frame.cyl(size * 0.16, 4, (0, 0, back), M["fan_frame"], segments=24)
    for k in range(4):  # struts from the motor to the frame corners
        a = math.pi / 4 + k * math.pi / 2
        frame.box((r * 0.95, 3, 2.2), (math.cos(a) * r * 0.55, math.sin(a) * r * 0.55, back), M["fan_frame"],
                  rotate=("Z", math.degrees(a)))
    turn = AXIS_TURN[axis]
    bmesh.ops.rotate(frame.bm, verts=frame.bm.verts, cent=(0, 0, 0), matrix=turn)
    bmesh.ops.translate(frame.bm, vec=Vector(center), verts=frame.bm.verts)
    frame.build()

    # the rotor: hub + curved blades around its own Z; the object rotation turns it to the axis
    rotor = Part(f"rotor_{name}", parent, location=center)
    hub_r = size * 0.17
    rotor.cyl(hub_r, depth * 0.62, (0, 0, 0.5), M["fan_frame"], segments=32, bevel=0.8)
    blade_m = M["fan_blade_clear"] if clear else M["fan_blade"]
    idx = rotor._index(blade_m)
    ni, nj = 7, 5
    for b in range(blades):
        a0 = 2 * math.pi * b / blades
        rows = []
        for i in range(ni + 1):
            t = i / ni
            rr = hub_r - 1 + (r - 1.6 - hub_r + 1) * t
            span = (2 * math.pi / blades) * (0.62 + 0.18 * t)
            row = []
            for j in range(nj + 1):
                sj = j / nj
                theta = a0 + 0.42 * t * t + span * sj
                z = (sj - 0.5) * depth * 0.55 * (1 - 0.25 * t) + 0.5
                row.append(rotor.bm.verts.new((rr * math.cos(theta), rr * math.sin(theta), z)))
            rows.append(row)
        for i in range(ni):
            for j in range(nj):
                f = rotor.bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]))
                f.material_index = idx
                f.smooth = True
    ob = rotor.build()
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = turn.to_quaternion()
    return ob


def fins(part, count, start, step, size, m):
    """A stack of thin plates: radiator and heatsink fins. step: offset between plates (x, y, z)."""
    s, d = Vector(start), Vector(step)
    for i in range(count):
        part.box(size, s + d * i, m)


# ---------------------------------------------------------------- the case


def make_case(M, name, D, H, W, cage_levels, radiator_max):
    """An open case of D x H x W mm. Origin: front-bottom corner at the tray side."""
    root = Part(name)
    st, si = M["steel"], M["steel_in"]
    # tray (the motherboard wall) with cable cut-outs and the CPU cut-out drawn as dark insets
    root.span((T, -T, FLOOR), (D - T, 0, H - T), si)
    root.span((D - 205, -T - 0.2, H - 210), (D - 95, -T, H - 110), M["rubber"])           # CPU back-plate cut-out
    for z0 in range(int(FLOOR) + 100, int(H) - 120, 110):
        root.span((D - 262, -T - 0.4, z0), (D - 250, -T, z0 + 70), M["rubber"], bevel=3)   # grommets near the board
    # bottom and top sheets
    root.span((0, -W, FLOOR - T), (D, 0, FLOOR), st, bevel=0.6)
    root.span((0, -W, H - T), (D, 0, H), st, bevel=0.6)
    # top vents: slats over the radiator area
    for i in range(int((D - 80) / 15)):
        x = D - 40 - i * 15
        root.span((x - 5, -W + 30, H - 0.2), (x + 5, -40, H + 0.6), M["mesh"])
    # power button and LED on top, near the front
    root.cyl(7, 3, (30, -W / 2, H + 1.5), M["accent"], segments=32)
    root.ring(7.2, 8.6, 1.2, (30, -W / 2, H + 1.2), M["led"], segments=32)
    root.span((52, -W / 2 - 6, H), (58, -W / 2 + 6, H + 1.2), M["plastic"])                 # USB-C
    root.span((64, -W / 2 - 7, H), (76, -W / 2 + 7, H + 1.2), M["plastic"])                 # USB-A
    # rear sheet: IO opening, slot covers, PSU opening
    root.span((D - T, -W, FLOOR), (D, 0, H - T), si)
    root.span((D + 0.1, -60, H - 190), (D + 0.6, -8, H - 30), M["rubber"])                   # IO shield opening
    slots = max(2, min(7, int((H - 32 - 175 - FLOOR - 100) / 20.3) + 1))
    for i in range(slots):                                                                     # PCI slot covers
        z = H - 32 - 175 - 10 - i * 20.3
        root.span((D - 0.2, -125, z - 7), (D + 1.2, -12, z + 7), M["accent"], bevel=0.4)
    root.span((D + 0.1, -195, FLOOR + 4), (D + 0.6, -40, FLOOR + 88), M["rubber"])           # PSU opening
    # front: a frame with a vented panel and intake fans behind it
    root.span((0, -W, FLOOR - T), (T, 0, H), si)
    root.span((-24, -W - 2, 8), (-2, 2, H + 2), st, bevel=4, segments=3)                      # front panel
    for i in range(int((H - 70) / 16)):                                                        # vent slots
        z = 40 + i * 16
        root.span((-24.6, -W + 22, z), (-23.6, -22, z + 8), M["mesh"])
    root.span((-24.8, -W + 20, H - 26), (-23.8, -20, H - 22), M["accent"])                  # front accent line
    # rails along the open side (where the glass would sit)
    root.span((0, -W, FLOOR), (D, -W + 6, FLOOR + 10), st, bevel=0.8)
    root.span((0, -W, H - 12), (D, -W + 6, H - T), st, bevel=0.8)
    root.span((D - 12, -W, FLOOR), (D - T, -W + 6, H - T), st, bevel=0.8)
    root.span((T, -W, FLOOR), (14, -W + 6, H - T), st, bevel=0.8)
    # drive cage at the bottom front: open toward the open side, so the drives in it are seen
    cage_top = FLOOR + 33 * cage_levels
    if cage_levels > 1:
        root.span((22, -60, FLOOR), (180, -57, cage_top), si)                                  # back wall
        for x in (22, 177):
            root.span((x, -172, FLOOR), (x + 3, -57, cage_top), si)                            # side walls
        for k in range(1, cage_levels):
            z = FLOOR + 33 * k
            for y0 in (-172, -70):                                                             # rails, not shelves
                root.span((22, y0, z - 1), (180, y0 + 10, z + 1), si)
    # feet
    for x in (30, D - 30):
        for y in (-25, -W + 25):
            root.cyl(14, 10, (x, y, FLOOR - T - 5), M["rubber"], segments=24, bevel=1.5)
    case = root.build()
    # fans: in front above the drive cage, one at the rear
    lowest = max(cage_top, FLOOR) + 70
    z = H - 85
    i = 0
    while z >= lowest:
        fan(case, f"{name}_front{i}", (T + 16, -W / 2, z), 120, 25, "X", M, clear=True, rim_rgb=True)
        z -= 130
        i += 1
    fan(case, f"{name}_rear", (D - T - 14, -112, H - 110), 120 if H > 380 else 92, 25, "X", M, clear=True, rim_rgb=True)
    # mounts
    empty("mount_board", (D - 20, -8, H - 32), case)
    empty("mount_psu", (D - T, -40, FLOOR), case)
    for k in range(max(1, cage_levels)):
        empty(f"mount_drive_{k}", (26, -116, FLOOR + 1 + k * 33), case)
    empty("mount_radiator", (D - 26, -130, H - T - 1), case)
    empty(f"radiator_max_{radiator_max}", (D - 26, -130, H - T - 1), case)
    return case


CASES = {  # by the boards they take: the biggest one decides
    "case_atx": dict(D=450, H=470, W=230, cage_levels=3, radiator_max=360),
    "case_matx": dict(D=400, H=410, W=215, cage_levels=3, radiator_max=360),
    "case_itx": dict(D=380, H=360, W=200, cage_levels=1, radiator_max=240),
}


# ---------------------------------------------------------------- motherboards

BOARDS = {  # name: length, height, RAM slots, layout
    "board_atx": dict(L=244, Hb=305, ram=4, socket=(-95, -82), pcie=[-175, -255], m2=[-132, -290]),
    "board_matx": dict(L=244, Hb=244, ram=4, socket=(-95, -82), pcie=[-175], m2=[-132, -228]),
    "board_itx": dict(L=170, Hb=170, ram=2, socket=(-80, -68), pcie=[-152], m2=[-120]),
}


def make_board(name, M, L, Hb, ram, socket, pcie, m2):
    """Origin: the board's rear-top corner, on its back side. The board lies at y -1.6..0, toward -y."""
    p = Part(name)
    pcb_y = -1.6
    p.span((-L, pcb_y, -Hb), (0, 0, 0), M["pcb"], bevel=0.3)
    sx, sz = socket
    # rear IO block and its RGB-lit cover
    p.span((-28, pcb_y - 36, -150), (2, pcb_y, -6), M["black_metal"], bevel=2, segments=3)
    p.span((-29, pcb_y - 37, -146), (-27.5, pcb_y - 4, -10), M["rgb"])
    p.span((-26, pcb_y - 36.6, -140), (-4, pcb_y - 35.6, -16), M["alu_dark"])
    # VRM heatsinks: above and left of the socket, with grooves
    vrm_top = (sx - 30, sx + 22)
    p.span((vrm_top[0], pcb_y - 26, sz + 34), (vrm_top[1], pcb_y, sz + 60), M["alu_dark"], bevel=1.2)
    for i in range(8):
        z = sz + 37 + i * 3
        p.span((vrm_top[0] - 0.2, pcb_y - 26.4, z), (vrm_top[1] + 0.2, pcb_y - 24, z + 1.2), M["black_metal"])
    p.span((sx - 58, pcb_y - 24, sz - 40), (sx - 34, pcb_y, sz + 50), M["alu_dark"], bevel=1.2)
    for i in range(10):
        z = sz - 36 + i * 8
        p.span((sx - 58.2, pcb_y - 24.4, z), (sx - 33.8, pcb_y - 22, z + 2), M["black_metal"])
    # chokes and power stages around the socket
    for i in range(6):
        p.span((sx - 24 + i * 9, pcb_y - 6, sz + 26), (sx - 17 + i * 9, pcb_y, sz + 33), M["plastic_grey"], bevel=0.6)
    # socket: frame, lever, contacts plate
    p.span((sx - 27, pcb_y - 2.5, sz - 27), (sx + 27, pcb_y, sz + 27), M["slot"], bevel=0.8)
    p.span((sx - 24, pcb_y - 3, sz - 24), (sx + 24, pcb_y - 2.5, sz + 24), M["slot_steel"])
    p.tube([(sx + 30, pcb_y - 3, sz - 26), (sx + 30, pcb_y - 3, sz + 26), (sx + 26, pcb_y - 6, sz + 30)], 0.9, M["slot_steel"])
    for dx in (-31, 31):
        for dz in (-31, 31):
            p.cyl(2.5, 2, (sx + dx, pcb_y - 1, sz + dz), M["slot_steel"], axis="Y", segments=12)
    # RAM slots with latches
    ram_x = [sx - 55 - i * 9.5 for i in range(ram)]
    for i, x in enumerate(ram_x):
        p.span((x - 3, pcb_y - 7, -153), (x + 3, pcb_y, -22), M["slot"] if i % 2 else M["plastic_grey"], bevel=0.4)
        for z in (-158, -17):
            p.span((x - 3.4, pcb_y - 9, z - 4), (x + 3.4, pcb_y, z + 4), M["plastic_grey"], bevel=0.6)
    # 24-pin power and 8-pin CPU power
    p.span((-L + 2, pcb_y - 14, -112), (-L + 18, pcb_y, -60), M["chip"], bevel=0.8)
    p.span((sx - 10, pcb_y - 12, -14), (sx + 16, pcb_y, -4), M["chip"], bevel=0.6)
    # PCIe slots: the first with a steel cover
    for i, z in enumerate(pcie):
        p.span((-106, pcb_y - 11, z - 3.5), (-16, pcb_y, z + 3.5), M["slot"], bevel=0.4)
        if i == 0:
            p.span((-107, pcb_y - 11.4, z - 4.2), (-15, pcb_y - 9.5, z + 4.2), M["slot_steel"], bevel=0.3)
        p.span((-22, pcb_y - 13, z - 4.5), (-16, pcb_y, z + 4.5), M["plastic_grey"], bevel=0.5)  # latch
    if Hb >= 240:  # a x1 slot
        z = pcie[0] - 42
        p.span((-56, pcb_y - 11, z - 3.5), (-16, pcb_y, z + 3.5), M["slot"], bevel=0.4)
    # M.2 slots (the drive sits on top) and their standoffs
    for z in m2:
        p.span((-34, pcb_y - 4.5, z - 11), (-26, pcb_y, z + 11), M["slot"], bevel=0.4)
        p.cyl(2.4, 3.5, (-112, pcb_y - 1.75, z), M["gold"], axis="Y", segments=12)
    # chipset heatsink with a glossy cap
    cz = (pcie[0] + (pcie[-1] if len(pcie) > 1 else -Hb + 20)) / 2 - 10 if Hb > 200 else -Hb + 30
    if Hb > 200:
        p.span((-L + 10, pcb_y - 12, cz - 30), (-L + 70, pcb_y, cz + 30), M["alu_dark"], bevel=2, segments=3)
        p.span((-L + 16, pcb_y - 12.6, cz - 22), (-L + 64, pcb_y - 12, cz + 22), M["glass"])
    # small parts: capacitors, battery, chips, headers
    p.cyl(10, 3, (-L + 30, pcb_y - 1.5, -Hb + 40), M["nickel"], axis="Y", segments=28)
    for i in range(5):
        p.cyl(3.2, 9, (-40 - i * 8, pcb_y - 4.5, -Hb + 14), M["alu"], axis="Y", segments=16)
    p.span((-80, pcb_y - 1.4, -Hb + 60), (-62, pcb_y, -Hb + 78), M["chip"], bevel=0.4)
    for i in range(4):
        x0 = -L + 20 + i * 26
        p.span((x0, pcb_y - 8, -Hb + 2), (x0 + 18, pcb_y, -Hb + 8), M["chip"], bevel=0.3)
    # thin decorative lines (traces) on the bare PCB
    for i in range(6):
        p.span((-L + 6, pcb_y - 0.05, -Hb + 100 + i * 7), (-L + 90, pcb_y, -Hb + 100.8 + i * 7), M["accent"])
    board = p.build()
    # mounts
    empty("mount_cpu", (sx, pcb_y - 2.5, sz), board)
    empty("mount_cooler", (sx, pcb_y - 7.5, sz), board)
    for i, x in enumerate(ram_x):
        empty(f"mount_ram_{i}", (x, pcb_y - 4, -87.5), board)
    empty("mount_gpu", (-16, pcb_y - 7, pcie[0]), board)
    for i, z in enumerate(m2):
        empty(f"mount_m2_{i}", (-30, pcb_y - 3.5, z), board)
    return board


# ---------------------------------------------------------------- CPU and coolers


def make_cpu(M):
    p = Part("cpu")
    p.span((-20, -1.2, -20), (20, 0, 20), M["pcb_green"], bevel=0.3)
    # heat spreader with "legs" like a modern desktop CPU
    p.span((-16, -5, -16), (16, -2.4, 16), M["nickel"], bevel=1.4, segments=3)
    for dx in (-17.5, 17.5):
        for dz in (-10, 10):
            p.span((dx - 2.5, -2.6, dz - 3), (dx + 2.5, -1.2, dz + 3), M["nickel"], bevel=0.4)
    p.span((-12, -5.05, -12), (12, -5.0, -9), M["alu"])
    for dx in (-18, 18):
        for dz in (-18, 18):
            p.span((dx - 1.2, -1.3, dz - 1.2), (dx + 1.2, -1.2, dz + 1.2), M["gold"])
    return p.build()


def make_cooler_tower(M):
    """Origin: the top of the CPU. A tower: copper base, 4 heat pipes, a fin stack and one fan in front."""
    p = Part("cooler_tower")
    p.span((-22, -8, -22), (22, 0, 22), M["copper"], bevel=1)
    p.span((-30, -14, -16), (30, -8, 16), M["nickel"], bevel=1.5, segments=3)
    p.span((-40, -11, -4), (40, -9, 4), M["black_metal"], bevel=0.6)                      # mounting bar
    # heat pipes: up from the base, bent into the fin stack
    for k, x in enumerate((-12, -4, 4, 12)):
        side = -1 if k % 2 else 1
        p.tube([(x, -10, side * 8), (x, -30, side * 8), (x, -42, side * 22), (x, -70, side * 22),
                (x, -150, side * 22), (x, -156, side * 22)], 3.0, M["copper"])
    # fin stack: thin plates parallel to the board
    fins(p, 46, (0, -40, 0), (0, -2.55, 0), (52, 0.5, 124), M["alu"])
    p.span((-26, -158, -62), (26, -154, 62), M["black_metal"], bevel=1.4, segments=3)      # top cover
    p.span((-24, -158.4, -55), (24, -158.1, 55), M["rgb"])                                 # lit strip
    q = p.build()
    fan(q, "cooler", (-40, -97, 0), 120, 25, "X", M, blades=9)
    return q


def make_cooler_low(M):
    """A box-style cooler: round fin heatsink, a fan on top with an RGB ring."""
    p = Part("cooler_low")
    p.span((-20, -4, -20), (20, 0, 20), M["copper"], bevel=0.8)
    p.cyl(18, 14, (0, -11, 0), M["alu"], axis="Y", segments=32)
    for i in range(36):
        a = 2 * math.pi * i / 36
        p.box((1.2, 26, 30), (math.cos(a) * 32, -16, math.sin(a) * 32), M["alu"], rotate=("Y", -math.degrees(a)))
    p.ring(44, 50, 30, (0, -16, 0), M["black_metal"], axis="Y", segments=64)
    p.ring(40, 44, 6, (0, -33, 0), M["rgb"], axis="Y", segments=64)
    p.span((-56, -4, -9), (56, -1, 9), M["black_metal"], bevel=0.6)
    q = p.build()
    fan(q, "cooler_low", (0, -42, 0), 92, 14, "Y", M, blades=11, clear=True)
    return q


def make_aio_pump(M):
    p = Part("aio_pump")
    p.span((-24, -6, -24), (24, 0, 24), M["copper"], bevel=1)
    p.cyl(31, 24, (0, -18, 0), M["black_metal"], axis="Y", segments=48, bevel=1.5)
    p.ring(26, 31.5, 2.2, (0, -30.2, 0), M["rgb"], axis="Y", segments=64)
    p.cyl(25.5, 1.2, (0, -30.4, 0), M["glass"], axis="Y", segments=48)
    for z in (-12, 12):                                                                      # hose fittings
        p.cyl(5.5, 10, (28, -20, z), M["black_metal"], axis="X", segments=20)
    q = p.build()
    empty("hose_a", (33, -20, -12), q)
    empty("hose_b", (33, -20, 12), q)
    return q


def make_radiator(M, length):
    """Origin: rear end, top center. Hangs from the top: core, end tanks and fans under it."""
    name = f"radiator_{length}"
    p = Part(name)
    core = length - 34
    p.span((-length, -60, -27), (0, 60, 0), M["black_metal"], bevel=1)                     # frame (hidden inside)
    p.span((-length + 17, -61, -25), (-17, 61, -2), M["fan_frame"])
    fins(p, int(core / 2.2), (-length + 18, -61.4, -13.5), (2.2, 0, 0), (0.4, 0.6, 22), M["alu_dark"])
    for x0 in (-length, -17):                                                               # end tanks
        p.span((x0, -60, -27), (x0 + 17, 60, 0), M["plastic"], bevel=2, segments=3)
    q = p.build()
    for i in range(length // 120):
        fan(q, f"{name}_{i}", (-17 - 60 - i * 120 - (core - (length // 120) * 120) / 2 + 0, 0, -27 - 12.5), 120, 25, "Z", M, clear=True, rim_rgb=True)
    empty("hose_a", (-8, -40, -27), q)
    empty("hose_b", (-8, -16, -27), q)
    return q


# ---------------------------------------------------------------- RAM, GPU, PSU, drives


def make_ram(M):
    """Origin: the middle of the contact edge. The stick stands out of the board toward -y."""
    p = Part("ram")
    p.span((-0.6, -32, -66.5), (0.6, 0, 66.5), M["pcb"], bevel=0.2)
    for side in (-1, 1):
        x0 = side * 0.6
        x1 = side * 3.2
        lo, hi = (min(x0, x1), max(x0, x1))
        p.span((lo, -36, -67), (hi, -3, 67), M["alu_dark"], bevel=0.6)
        p.span((lo - 0.1 * side, -34, -50), (hi + 0.1 * side, -30, 40), M["black_metal"])      # styling groove
    p.span((-2.6, -43, -66), (2.6, -36, 66), M["rgb"], bevel=1.2, segments=3)                   # diffuser on top
    p.span((-0.6, -2, -66.5), (0.6, 0, 66.5), M["gold"])
    q = p.build()
    p2 = Part("label_ram", q)
    p2.quad([(-3.3, -26, -44), (-3.3, -26, 44), (-3.3, -12, 44), (-3.3, -12, -44)], M["label"])
    p2.build()
    return q


def make_gpu(M, name, length, fans_count):
    """Origin: the rear end of the PCIe contact. The card lies across the case, fans down, toward -x."""
    p = Part(name)
    L = length
    pcb_y0, pcb_y1 = -4, -112          # PCB edge in the slot → its top edge toward the open side
    # PCB and the gold contact
    p.span((-L + 6, pcb_y1, -1.6), (12, pcb_y0, 0), M["pcb"], bevel=0.3)
    p.span((-89, -4, -1.0), (-6, 3, 0.6), M["gold"])
    # backplate on top
    p.span((-L + 4, pcb_y1 - 2, 0.2), (12, pcb_y0 + 2, 3.2), M["black_metal"], bevel=1.2, segments=3)
    p.span((-L + 30, pcb_y1 + 8, 3.2), (-30, pcb_y1 + 30, 3.6), M["alu_dark"], bevel=0.5)
    # heatsink under the PCB (visible through the side grill) and the shroud
    fins(p, int((L - 30) / 2.4), (-L + 18, -60, -24), (2.4, 0, 0), (0.5, 104, 40), M["alu"])
    shroud_y0, shroud_y1 = -2, -118
    p.span((-L, shroud_y1, -50), (8, shroud_y0, -44), M["plastic"], bevel=2.2, segments=3)       # bottom plate
    p.span((-L, shroud_y1, -44), (8, shroud_y1 + 5, -4), M["plastic"], bevel=1.6, segments=3)    # side toward the open side
    p.span((-L, shroud_y0 - 5, -44), (8, shroud_y0, -10), M["plastic"], bevel=1.6, segments=3)   # side toward the board
    p.span((-L - 1, shroud_y1, -50), (-L + 6, shroud_y0, 0), M["plastic"], bevel=1.6, segments=3)  # front end
    # windows in the outer side showing the fins, and the lit bar with a label
    for k in range(max(2, fans_count + 1)):
        x0 = -L + 20 + k * (L - 60) / max(2, fans_count + 1)
        p.span((x0, shroud_y1 - 0.5, -40), (x0 + (L - 80) / max(2, fans_count + 1) - 8, shroud_y1 + 0.5, -26), M["mesh"])
    p.span((-L + 16, shroud_y1 - 0.8, -22), (-16, shroud_y1 - 0.2, -14), M["rgb"], bevel=0.3)
    p.span((-L + 2, shroud_y1 - 0.2, -48), (6, shroud_y1 + 0.2, -45), M["alu_dark"])           # trim line
    # power connector on the top edge
    p.span((-L * 0.42 - 12, pcb_y1 - 8, -6), (-L * 0.42 + 12, pcb_y1, 2), M["chip"], bevel=0.6)
    # bracket at the rear with display outputs
    p.span((12, -122, -56), (14, 12, 6), M["slot_steel"], bevel=0.3)
    for i in range(4):
        p.span((14, -100 + i * 22, -30), (14.4, -88 + i * 22, -20), M["chip"])
    p.span((14, -110, -50), (14.4, -10, -36), M["mesh"])
    q = p.build()
    # fans under the card, axis Z (they blow up into the heatsink)
    pitch = (L - 30) / fans_count
    size = min(92 if fans_count == 3 and L < 290 else 100, pitch - 4)
    for i in range(fans_count):
        fan(q, f"{name}_{i}", (-L + 16 + pitch * (i + 0.5), -60, -52), size, 9, "Z", M, blades=11)
    p3 = Part(f"label_{name}", q)
    p3.quad([(-L + 18, shroud_y1 - 1.0, -42), (-L * 0.45, shroud_y1 - 1.0, -42),
             (-L * 0.45, shroud_y1 - 1.0, -24), (-L + 18, shroud_y1 - 1.0, -24)], M["label"])
    p3.build()
    return q


def make_psu(M):
    """Origin: rear face, the edge nearer the tray, bottom. Extends to -x (front), -y (open side), +z."""
    p = Part("psu")
    Lp, Wp, Hp = 160, 150, 86
    p.span((-Lp, -Wp, 0), (0, 0, Hp), M["black_metal"], bevel=2.2, segments=3)
    # top grill and the fan under it is hidden: show a vented top
    for i in range(12):
        x = -Lp + 18 + i * 11
        p.span((x, -Wp + 18, Hp - 0.2), (x + 6, -18, Hp + 0.4), M["mesh"])
    # modular sockets on the front face
    for i in range(6):
        p.span((-Lp - 1.4, -Wp + 14 + i * 21, 12), (-Lp + 0.2, -Wp + 30 + i * 21, 28 + (i % 2) * 18), M["chip"], bevel=0.5)
    # rear: honeycomb area + plug and switch
    p.span((0, -Wp + 10, 8), (0.8, -60, Hp - 8), M["mesh"])
    p.span((0, -46, 30), (2.5, -16, 56), M["chip"], bevel=0.8)
    # side sticker frame
    p.span((-Lp + 10, -Wp - 0.5, 12), (-10, -Wp + 0.2, Hp - 12), M["alu_dark"], bevel=0.6)
    q = p.build()
    p2 = Part("label_psu", q)
    p2.quad([(-Lp + 14, -Wp - 0.8, 16), (-14, -Wp - 0.8, 16), (-14, -Wp - 0.8, Hp - 16), (-Lp + 14, -Wp - 0.8, Hp - 16)], M["label"])
    p2.build()
    return q


def make_m2(M):
    """Origin: the contact end (rear), the drive goes toward -x, flat on the board."""
    p = Part("m2")
    p.span((-80, -0.8, -11), (0, 0, 11), M["pcb"], bevel=0.2)
    p.span((-3.5, -0.8, -10), (0, 0.6, 10), M["gold"])
    p.span((-22, -2.2, -8), (-8, -0.8, 8), M["chip"], bevel=0.3)
    for x0 in (-48, -72):
        p.span((x0, -2.2, -9), (x0 + 20, -0.8, 9), M["chip"], bevel=0.3)
    p.span((-79, -2.6, -10.5), (-6, -2.25, 10.5), M["label_light"])
    q = p.build()
    p2 = Part("label_m2", q)
    p2.quad([(-76, -2.7, -9), (-8, -2.7, -9), (-8, -2.7, 9), (-76, -2.7, 9)], M["label"], uv=((0, 0), (1, 0), (1, 1), (0, 1)))
    p2.build()
    return q


def make_ssd(M):
    """2.5" SATA SSD. Origin: front end, middle, bottom; lies flat in the drive cage."""
    p = Part("ssd")
    p.span((0, -35, 0), (100, 35, 7), M["alu_dark"], bevel=1.2, segments=3)
    p.span((96, -20, 1.5), (100.5, 12, 5.5), M["chip"])
    q = p.build()
    p2 = Part("label_ssd", q)
    p2.quad([(8, 30, 7.15), (92, 30, 7.15), (92, -30, 7.15), (8, -30, 7.15)], M["label"])
    p2.build()
    return q


def make_hdd(M):
    """3.5" HDD. Origin: front end, middle, bottom."""
    p = Part("hdd")
    p.span((0, -50.8, 0), (147, 50.8, 26), M["alu"], bevel=1.4, segments=3)
    p.span((6, -46, 25.6), (141, 46, 26.4), M["alu_dark"], bevel=1)
    p.span((140, -40, 3), (147.6, 40, 10), M["pcb_green"])
    p.cyl(15, 1, (50, 0, 26.6), M["nickel"], segments=40)
    q = p.build()
    p2 = Part("label_hdd", q)
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
    make_cooler_low(M)
    make_aio_pump(M)
    make_radiator(M, 240)
    make_radiator(M, 360)
    make_ram(M)
    make_gpu(M, "gpu1", 175, 1)
    make_gpu(M, "gpu2", 240, 2)
    make_gpu(M, "gpu3", 310, 3)
    make_psu(M)
    make_m2(M)
    make_ssd(M)
    make_hdd(M)
    # every part at the world origin: the site puts them in place
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT), export_format="GLB", export_apply=True, export_yup=True,
        export_materials="EXPORT", export_cameras=False, export_lights=False, export_extras=False,
        export_animations=False,
    )
    tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print(f"made {OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB, {tris} faces")


if __name__ == "__main__" or "bpy" in sys.modules:
    main()
