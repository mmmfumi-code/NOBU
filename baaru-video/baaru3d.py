"""ばぁる 3DCG 版：Blender (bpy) でシーンを組み立てる部品."""
import math

import bpy
import numpy as np
from mathutils import Vector, Euler


def hexc(h, a=1.0):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    # sRGB -> linear
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*c, a)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, rough=0.45, sss=0.0, coat=0.0, emit=0.0, sheen=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = hexc(color)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Specular IOR Level'].default_value = spec
    if sss:
        b.inputs['Subsurface Weight'].default_value = sss
        b.inputs['Subsurface Radius'].default_value = (0.25, 0.12, 0.2)
        b.inputs['Subsurface Scale'].default_value = 0.08
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.15
    if sheen:
        b.inputs['Sheen Weight'].default_value = sheen
        b.inputs['Sheen Tint'].default_value = (1, 1, 1, 1)
    if emit:
        b.inputs['Emission Color'].default_value = hexc(color)
        b.inputs['Emission Strength'].default_value = emit
    return m


def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def empty(name, parent=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    link(o)
    o.parent = parent
    o.location = loc
    return o


def uv_sphere(name, material, parent=None, loc=(0, 0, 0), scale=(1, 1, 1), seg=48, ring=24):
    me = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    link(o)
    o.parent = parent
    o.location = loc
    o.scale = scale
    return o


def arc_curve(name, material, parent, loc, radius=0.05, width=0.012):
    """にっこり目（^ の形）."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = width
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    pts = []
    for i in range(13):
        a = math.pi * (0.15 + 0.7 * i / 12)
        pts.append((math.cos(a) * radius, 0, math.sin(a) * radius - radius * 0.5))
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1)
    cu.materials.append(material)
    o = bpy.data.objects.new(name, cu)
    link(o)
    o.parent = parent
    o.location = loc
    return o


SCHEMES = {
    'purple': ('A98BD9', 'FFF6E6'),
    'pink': ('F5A3C7', 'FFF6E6'),
    'mint': ('86D9C0', 'FFF6E6'),
}


# 2D 版と同じ輪郭（x 右, y 下, 単位は体の高さ 約1.16）
OUTLINE = [
    (-0.30, -0.64), (-0.13, -0.46), (0.05, -0.43), (0.25, -0.45), (0.41, -0.37),
    (0.53, -0.22), (0.46, -0.07), (0.48, 0.15), (0.41, 0.40), (0.15, 0.52),
    (-0.15, 0.52), (-0.40, 0.42), (-0.50, 0.15), (-0.50, -0.15), (-0.45, -0.46),
]
NA, NR = 160, 22          # 角度方向・半径方向の分割数
CENTER = np.array([0.0, 0.02])
ROUND = 0.38              # ふちの丸み
DEPTH = 0.34              # 厚み（前側）


def catmull(pts, per=24):
    P = np.array(pts)
    n = len(P)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
        for t in np.linspace(0, 1, per, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return np.array(out)


def polar_radius(poly, angles):
    """中心から各角度に伸ばした光線が輪郭とぶつかる距離（いちばん遠い交点）."""
    a = poly - CENTER
    b = np.roll(a, -1, axis=0)
    d = np.stack([np.cos(angles), np.sin(angles)], 1)
    R = np.zeros(len(angles))
    e = b - a
    for i, (dx, dy) in enumerate(d):
        den = dx * e[:, 1] - dy * e[:, 0]
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / den
            u = (a[:, 0] * dy - a[:, 1] * dx) / den
        ok = (np.abs(den) > 1e-9) & (u >= 0) & (u <= 1) & (t > 0)
        R[i] = t[ok].max() if ok.any() else 0.3
    return R


def dist_to_poly(pts, poly):
    a = poly
    b = np.roll(poly, -1, axis=0)
    ab = b - a
    L = (ab ** 2).sum(1) + 1e-12
    ap = pts[:, None, :] - a[None]
    t = np.clip((ap * ab[None]).sum(2) / L[None], 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.sqrt(((pts[:, None, :] - proj) ** 2).sum(2)).min(1)


class Baaru:
    """2D の輪郭をふっくら膨らませた ぷにぷにの ばぁる."""

    def __init__(self, scheme='purple', scale=1.0):
        self.scheme = scheme
        self.base_scale = scale
        body_col, face_col = SCHEMES[scheme]
        tag = scheme.capitalize()
        self.root = empty(f'Root{tag}')
        self.squash = empty(f'Squash{tag}', self.root)

        m_body = mat(f'Body{tag}', body_col, rough=0.35, sss=0.3, coat=0.4, sheen=0.25)
        self.angles = np.linspace(0, 2 * np.pi, NA, endpoint=False)
        self.rho = np.sin(0.5 * np.pi * np.arange(1, NR + 1) / NR)
        me = bpy.data.meshes.new(f'Body{tag}')
        verts, faces = self._topology()
        me.from_pydata(verts, [], faces)
        me.materials.append(m_body)
        me.shade_smooth()
        self.me = me
        ob = bpy.data.objects.new(f'Body{tag}', me)
        link(ob)
        ob.parent = self.squash
        sub = ob.modifiers.new('sub', 'SUBSURF')
        sub.levels = 1
        sub.render_levels = 1
        self.body_obj = ob
        self._last_ear = None
        self._update_body(0.0)

        # 顔
        self.face_pivot = empty(f'FacePivot{tag}', self.squash, (-0.03, -0.42, 0.40))
        self.face = empty(f'Face{tag}', self.face_pivot)
        m_face = mat(f'Face{tag}', face_col, rough=0.5, sss=0.2, sheen=0.2)
        m_eye = mat(f'Eye{tag}', '231C30', rough=0.06, coat=1.0, spec=0.8)
        m_white = mat(f'Hi{tag}', 'FFFFFF', emit=6.0)
        m_cheek = mat(f'Cheek{tag}', 'F59AA2', rough=0.6, sss=0.2)
        m_mouth = mat(f'Mouth{tag}', 'F07F94', rough=0.35)
        m_mouth_in = mat(f'MouthIn{tag}', 'A8344F', rough=0.6)
        uv_sphere(f'FaceDisc{tag}', m_face, self.face, (0, 0, 0), (0.36, 0.11, 0.33))
        self.eyes = []
        self.eyes_happy = []
        for i, ex in enumerate((-0.135, 0.145)):
            e = uv_sphere(f'Eye{tag}{i}', m_eye, self.face, (ex, -0.085, 0.04), (0.055, 0.03, 0.082), 32, 16)
            uv_sphere(f'EyeHi{tag}{i}', m_white, e, (-0.3, -0.9, 0.38), (0.3, 0.3, 0.24), 16, 8)
            self.eyes.append(e)
            h = arc_curve(f'EyeHappy{tag}{i}', m_eye, self.face, (ex, -0.1, 0.04), 0.055, 0.014)
            h.hide_render = True
            self.eyes_happy.append(h)
        for i, cx in enumerate((-0.25, 0.26)):
            uv_sphere(f'Cheek{tag}{i}', m_cheek, self.face, (cx, -0.075, -0.06), (0.065, 0.02, 0.04), 24, 12)
        self.mouth = uv_sphere(f'Mouth{tag}', m_mouth, self.face, (0.0, -0.1, -0.08), (0.04, 0.02, 0.04), 24, 12)
        self.mouth_in = uv_sphere(f'MouthIn{tag}', m_mouth_in, self.mouth, (0, -0.7, 0.1), (0.62, 0.5, 0.62), 24, 12)

        self.root.scale = (scale, scale, scale)
        self.set({})

    def _topology(self):
        verts = [(0, 0, 0)] * (2 + 2 * NA * NR)
        faces = []
        F0, B0 = 0, 1  # 前・うしろの中心

        def vid(side, r, a):  # r: 0..NR-1, リングの最外周 r=NR-1 は前後で共有
            if r == NR - 1:
                return 2 + (a % NA) * NR + r
            return 2 + (side * NA * NR) + (a % NA) * NR + r
        for side, c in ((0, F0), (1, B0)):
            for a in range(NA):
                tri = (c, vid(side, 0, a), vid(side, 0, a + 1))
                faces.append(tri if side == 0 else tri[::-1])
                for r in range(NR - 1):
                    q = (vid(side, r, a), vid(side, r + 1, a), vid(side, r + 1, a + 1), vid(side, r, a + 1))
                    faces.append(q if side == 0 else q[::-1])
        self._vid = vid
        return verts, faces

    def _update_body(self, ear):
        key = round(ear, 3)
        if key == self._last_ear:
            return
        self._last_ear = key
        pts = [list(p) for p in OUTLINE]
        # 左の大きい耳をゆらす
        px, py = -0.25, -0.30
        a = ear * 0.35
        dx, dy = pts[0][0] - px, pts[0][1] - py
        pts[0] = [px + dx * math.cos(a) - dy * math.sin(a), py + dx * math.sin(a) + dy * math.cos(a)]
        w = ear * 0.04
        pts[5] = [pts[5][0] + abs(w) + 0.01, pts[5][1] - w]
        poly = catmull(pts)
        R = polar_radius(poly, self.angles)
        u = np.stack([np.cos(self.angles), np.sin(self.angles)], 1)
        P = CENTER[None, None] + self.rho[None, :, None] * R[:, None, None] * u[:, None, :]  # (NA, NR, 2)
        flat = P.reshape(-1, 2)
        d = dist_to_poly(flat, poly).reshape(NA, NR)
        s = np.clip(d / ROUND, 0, 1)
        dome = 1 + 0.35 * (1 - self.rho[None, :] ** 2)
        depth = DEPTH * np.sqrt(1 - (1 - s) ** 2) * dome
        depth[:, -1] = 0
        co = np.zeros((2 + 2 * NA * NR, 3))
        cz = -CENTER[1] + 0.52
        co[0] = (CENTER[0], -DEPTH * 1.35, cz)
        co[1] = (CENTER[0], DEPTH * 1.35 * 0.85, cz)
        for side, sign in ((0, -1), (1, 0.85)):
            base = 2 + side * NA * NR
            blk = np.zeros((NA, NR, 3))
            blk[..., 0] = P[..., 0]
            blk[..., 2] = -P[..., 1] + 0.52
            blk[..., 1] = sign * depth
            if side == 0:
                co[2:2 + NA * NR] = blk.reshape(-1, 3)
            else:
                b = blk.reshape(-1, 3).copy()
                idx = np.arange(NA * NR)
                keep = (idx % NR) != NR - 1
                co[base:base + NA * NR][keep] = b[keep]
        self.me.vertices.foreach_set('co', co.ravel())
        self.me.update()

    def set(self, st):
        """2D 版と同じ状態辞書を反映."""
        st = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v) for k, v in st.items()}
        s = self.base_scale * st.get('size_mul', 1.0)
        hide = bool(s < 0.01)
        self.root.hide_render = hide
        for o in self.root.children_recursive:
            o.hide_render = hide
        if hide:
            return
        self.root.scale = (s, s, s)
        self.root.location = (st.get('X', 0.0), st.get('Y', 0.0), st.get('Z', 0.0))
        self.root.rotation_euler = (0, st.get('rot', 0.0), st.get('turn', 0.0))
        sx, sy = st.get('sx', 1.0), st.get('sy', 1.0)
        self.squash.scale = (sx, sx, sy)
        self._update_body(st.get('ear', 0.0))

        k = st.get('face', 1.0)
        self.face.scale = (max(k, 0.001),) * 3
        # かくれるときは顔がフードの中へ沈む
        self.face_pivot.location = (-0.03, -0.42 + 0.4 * (1 - k), 0.40)

        happy = st.get('happy', 0) > 0.5
        blink = st.get('blink', 0.0)
        for e, h in zip(self.eyes, self.eyes_happy):
            e.hide_render = bool(happy or k < 0.05)
            for c in e.children:
                c.hide_render = e.hide_render
            h.hide_render = bool((not happy) or k < 0.05)
            e.scale = (0.055, 0.03, 0.082 * max(0.08, 1 - blink))
        m = st.get('mouth', 0.0)
        self.mouth.scale = (0.04 + 0.03 * m, 0.02, 0.04 + 0.05 * m)
        self.mouth.location = (0.0, -0.1, -0.08 - 0.02 * m)
        self.mouth_in.hide_render = bool(m < 0.2 or k < 0.05)
