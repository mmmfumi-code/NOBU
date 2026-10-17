"""ばぁる「いないいないばぁ」ダンス 3DCG 版.

python3 render3d.py [out.mp4] [--frames a:b] [--pct 75] [--samples 10] [--stills t1,t2,...]
振り付け・音楽・声は make_video.py（2D 版）と共通。キャラクターと背景を Blender (Cycles) で描き、
文字と「ばぁ！」のお星さまだけ 2D で重ねる。途中のコマは frames3d/ に保存されるので、止まっても続きから描ける。
"""
import argparse
import math
import os
import random
import subprocess
import time

import bpy
import cairo
import numpy as np
from PIL import Image

import baaru3d as b3
import make_video as mv

HERE = os.path.dirname(os.path.abspath(__file__))
PX = 300.0           # 2D の 300px = 3D の 1 単位
BASE_LENS = 52.0
CAM_DIST = 6.2
AIM_Z = 0.77

# ---------------------------------------------------------------- シーン


def sky_world():
    w = bpy.data.worlds.new('Sky')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    N = nt.nodes
    for n in list(N):
        if n.type != 'OUTPUT_WORLD':
            N.remove(n)
    out = N['World Output']
    lp = N.new('ShaderNodeLightPath')
    tc = N.new('ShaderNodeTexCoord')
    sep = N.new('ShaderNodeSeparateXYZ')
    ramp = N.new('ShaderNodeValToRGB')
    bg_cam = N.new('ShaderNodeBackground')
    bg_light = N.new('ShaderNodeBackground')
    mix = N.new('ShaderNodeMixShader')
    nt.links.new(tc.outputs['Window'], sep.inputs[0])
    nt.links.new(sep.outputs['Y'], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bg_cam.inputs[0])
    bg_light.inputs[0].default_value = b3.hexc('DCEBFF')
    bg_light.inputs[1].default_value = 0.55
    bg_cam.inputs[1].default_value = 1.0
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs[0])
    nt.links.new(bg_light.outputs[0], mix.inputs[1])
    nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 1.0
    return ramp


def blob_cluster(name, material, parts, loc, scale=1.0):
    root = b3.empty(name, None, loc)
    root.scale = (scale,) * 3
    for i, (x, y, z, r) in enumerate(parts):
        b3.uv_sphere(f'{name}{i}', material, root, (x, y, z), (r, r * 0.9, r * 0.85), 32, 16)
    return root


def build_scene(pct, samples):
    b3.reset()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.resolution_percentage = pct
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.use_denoising = True
    sc.cycles.denoising_quality = 'FAST'
    sc.cycles.denoising_prefilter = 'FAST'
    sc.cycles.use_light_tree = False
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.use_persistent_data = True
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Khronos PBR Neutral'
    sc.view_settings.exposure = 0.0

    S = {}
    S['sky'] = sky_world()
    sc.world.cycles.sampling_method = 'NONE'

    # 地面と丘
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 20, 0))
    ground = bpy.context.object
    ground.data.materials.append(b3.mat('Ground', '79C966', rough=0.85, sheen=0.4))
    m_hill = b3.mat('Hill', '98DB86', rough=0.85, sheen=0.4)
    m_hill2 = b3.mat('Hill2', '6CBF5E', rough=0.85, sheen=0.4)
    for i, (x, y, r, m) in enumerate([(-9, 16, 7, m_hill), (2, 22, 9, m_hill2), (12, 17, 7.5, m_hill),
                                      (-20, 24, 10, m_hill2), (24, 25, 11, m_hill2)]):
        b3.uv_sphere(f'HillS{i}', m, None, (x, y, -r * 0.8), (r * 1.5, r, r), 48, 24)

    # 雲
    m_cloud = b3.mat('Cloud', 'FFFFFF', rough=0.9, sheen=0.6, emit=0.35)
    S['clouds'] = []
    rng = random.Random(5)
    for i in range(5):
        parts = [(-0.9, 0, 0, 0.7), (0, 0, 0.35, 0.95), (0.95, 0, 0.05, 0.75), (0.4, -0.2, -0.2, 0.6),
                 (-0.4, -0.2, -0.25, 0.6)]
        c = blob_cluster(f'Cloud{i}', m_cloud, parts, (rng.uniform(-12, 12), 18, rng.uniform(3.2, 4.6)),
                         rng.uniform(0.9, 1.4))
        S['clouds'].append((c, rng.uniform(0.15, 0.35)))

    # 太陽
    m_sun = b3.mat('SunM', 'FFD54F', emit=2.5)
    sun = b3.uv_sphere('SunDisc', m_sun, None, (8.0, 22, 5.6), (1.3, 0.3, 1.3))
    S['sun'] = sun

    # お花
    m_stem = b3.mat('Stem', '5DB85A', rough=0.7)
    petals = [b3.mat(f'Petal{i}', c, rough=0.5, sheen=0.4) for i, c in
              enumerate(['FF8FB1', 'FFD25F', 'FFFFFF', '7FC8FF', 'C49BFF'])]
    m_core = b3.mat('Core', 'FFB300', rough=0.5)
    S['flowers'] = []
    rng = random.Random(11)
    for i in range(18):
        x = rng.uniform(-4.2, 4.2)
        y = rng.uniform(-1.6, 3.5)
        if abs(x) < 1.6 and y < 0.8:
            continue
        f = b3.empty(f'Flower{i}', None, (x, y, 0))
        s = rng.uniform(0.7, 1.1)
        f.scale = (s, s, s)
        b3.uv_sphere(f'Stem{i}', m_stem, f, (0, 0, 0.12), (0.018, 0.018, 0.12), 12, 6)
        head = b3.empty(f'FHead{i}', f, (0, 0, 0.25))
        head.rotation_euler = (math.radians(-60), 0, 0)
        pm = petals[i % len(petals)]
        for k in range(5):
            a = k * 2 * math.pi / 5
            b3.uv_sphere(f'Pet{i}_{k}', pm, head, (math.cos(a) * 0.07, math.sin(a) * 0.07, 0), (0.055, 0.055, 0.02), 16, 8)
        b3.uv_sphere(f'Core{i}', m_core, head, (0, 0, 0.012), (0.04, 0.04, 0.025), 16, 8)
        S['flowers'].append((f, rng.uniform(0, 6)))

    # ふわふわ浮かぶボール
    S['balls'] = []
    rng = random.Random(3)
    for i in range(10):
        m = b3.mat(f'Ball{i}', rng.choice(['FF8FB1', '7FC8FF', 'FFD25F', '9BE38F', 'C49BFF']), rough=0.15, coat=1.0)
        r = rng.uniform(0.07, 0.16)
        o = b3.uv_sphere(f'BallO{i}', m, None, (0, 0, 0), (r, r, r), 24, 12)
        S['balls'].append(dict(o=o, x=rng.uniform(-4.5, 4.5), y=rng.uniform(1.5, 4.0), sp=rng.uniform(0.15, 0.35),
                               ph=rng.uniform(0, 10)))

    # イントロの草むら
    m_bush = b3.mat('Bush', '4FAE58', rough=0.7, sheen=0.5)
    m_berry = b3.mat('Berry', 'FF5F8A', rough=0.25, coat=1.0)
    parts = [(-0.75, 0, 0.35, 0.5), (-0.3, -0.05, 0.75, 0.55), (0.3, -0.05, 0.78, 0.55), (0.78, 0, 0.4, 0.5),
             (0, -0.15, 0.3, 0.65), (-0.4, -0.2, 0.0, 0.6), (0.4, -0.2, 0.0, 0.6)]
    bush = blob_cluster('Bush', m_bush, parts, (0, -0.85, 0))
    for i, (x, z) in enumerate([(-0.5, 0.75), (0.35, 1.1), (0.75, 0.55), (-0.1, 0.5), (-0.85, 0.4)]):
        b3.uv_sphere(f'Berry{i}', m_berry, bush, (x, -0.62, z), (0.07, 0.07, 0.07), 16, 8)
    S['bush'] = bush

    # ライト
    bpy.ops.object.light_add(type='SUN', rotation=(math.radians(48), math.radians(12), math.radians(-28)))
    key = bpy.context.object
    key.data.energy = 2.4
    key.data.angle = math.radians(20)
    key.data.color = (1.0, 0.97, 0.92)
    bpy.ops.object.light_add(type='AREA', location=(-3.5, -5, 3.5))
    fill = bpy.context.object
    fill.data.energy = 260
    fill.data.size = 5
    fill.rotation_euler = (math.radians(55), 0, math.radians(-35))
    bpy.ops.object.light_add(type='AREA', location=(2.5, 3.5, 3.0))
    rim = bpy.context.object
    rim.data.energy = 220
    rim.data.size = 3
    rim.data.color = (1.0, 0.92, 0.98)
    rim.rotation_euler = (math.radians(-55), 0, math.radians(150))

    # カメラ
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    sc.camera = cam
    cam.data.lens = BASE_LENS
    cam.data.sensor_fit = 'HORIZONTAL'
    cam.data.sensor_width = 36
    S['cam'] = cam

    # キャラクター
    S['chars'] = {k: b3.Baaru(k, 1.0) for k in ('purple', 'pink', 'mint')}
    return S


def place_camera(cam, zoom, fx, fy, shake, t):
    h = 1.25
    pitch = math.atan2(h - AIM_Z, CAM_DIST)
    cam.location = (0, -CAM_DIST, h)
    cam.rotation_euler = (math.pi / 2 - pitch, 0, 0)
    cam.data.lens = BASE_LENS * zoom
    sx = (fx - 640) * (zoom - 1) / 1280
    sy = -(fy - 360) * (zoom - 1) / 1280
    if shake > 0.1:
        sx += shake * math.sin(t * 61) / 1280
        sy += shake * math.cos(t * 47) / 1280
    cam.data.shift_x = sx
    cam.data.shift_y = sy


# ---------------------------------------------------------------- 動き（2D の状態 → 3D）


class Spring:
    """目標値に ぷるんと追いつくバネ（CG らしい揺れ戻し）."""

    def __init__(self, v=0.0, freq=5.0, damp=0.32):
        self.v, self.vel = v, 0.0
        self.w = 2 * math.pi * freq
        self.z = damp

    def step(self, target, dt):
        for _ in range(4):
            h = dt / 4
            acc = self.w * self.w * (target - self.v) - 2 * self.z * self.w * self.vel
            self.vel += acc * h
            self.v += self.vel * h
        return self.v


def precompute(nframes):
    """全フレームの状態を先に計算する（バネは時間順に積分が必要なため）."""
    dt = 1 / mv.FPS
    springs = {k: dict(sy=Spring(1.0, 4.5, 0.28), ear=Spring(0.0, 3.2, 0.22), rot=Spring(0.0, 5.0, 0.45))
               for k in ('purple', 'pink', 'mint')}
    frames = []
    for i in range(nframes):
        t = i * dt
        beat, chars, texts, bursts, flash, bush, cam = mv.scene(t)
        fi = min(i, mv.MOUTH_ENV['purple'].size - 1) if mv.MOUTH_ENV else 0
        cs = {}
        for c in chars:
            if mv.MOUTH_ENV and c['face'] > 0.3:
                c['mouth'] = max(c['mouth'], min(1.0, mv.MOUTH_ENV[c['scheme']][fi] * 1.3))
            sp = springs[c['scheme']]
            sy = sp['sy'].step(c.get('sy', 1.0), dt)
            sx = 1 / math.sqrt(max(sy, 0.3))   # 体積を保つ
            cs[c['scheme']] = dict(
                X=(c['x'] - 640) / PX,
                Z=(c.get('hop', 0) - (c['y'] - mv.GROUND)) / PX,
                rot=sp['rot'].step(c.get('rot', 0.0), dt),
                turn=c.get('turn', 0.0),
                sx=sx, sy=sy,
                face=c.get('face', 1.0), mouth=c.get('mouth', 0.0), happy=c.get('happy', 0),
                blink=c.get('blink', 0.0), ear=sp['ear'].step(c.get('ear', 0.0), dt),
                size_mul=c['size'] / PX,
            )
        frames.append(dict(t=t, beat=beat, chars=cs, texts=texts, bursts=bursts, flash=flash,
                           bush=bush, cam=cam))
    return frames


def apply_frame(S, f):
    t = f['t']
    for k, ch in S['chars'].items():
        ch.set(f['chars'].get(k, {'size_mul': 0.0}))
    bush = f['bush']
    S['bush'].hide_render = bush is None or bush > 380
    for c in S['bush'].children_recursive:
        c.hide_render = S['bush'].hide_render
    if bush is not None:
        S['bush'].location = (0, -0.85, -bush / PX * 1.1)
    top, bot, _, _ = mv.palette_at(f['beat'] / 4)
    ramp = S['sky'].color_ramp
    ramp.elements[0].color = b3.hexc('%02x%02x%02x' % tuple(int(v * 255) for v in bot))
    ramp.elements[1].color = b3.hexc('%02x%02x%02x' % tuple(int(v * 255) for v in top))
    for c, sp in S['clouds']:
        x = c.location.x + 0
        c.location.x = ((c['x0'] if 'x0' in c else x) + t * sp + 16) % 32 - 16
        c['x0'] = c.get('x0', x)
    for fl, ph in S['flowers']:
        fl.rotation_euler = (0, 0.18 * math.sin(f['beat'] * math.pi + ph), 0)
    for b in S['balls']:
        z = ((t * b['sp'] + b['ph']) % 4.5) - 0.3
        b['o'].location = (b['x'] + 0.3 * math.sin(t * 0.7 + b['ph']), b['y'], z + 0.4)
    pulse = 1 + 0.05 * math.cos(f['beat'] * math.pi * 2) ** 8
    S['sun'].scale = (1.3 * pulse, 0.3, 1.3 * pulse)
    z, fx, fy, shake = f['cam']
    place_camera(S['cam'], z, fx, fy, shake, t)


# ---------------------------------------------------------------- 2D の重ね描き

def composite(png, f, out_jpg):
    im = Image.open(png).convert('RGB')
    if im.size != (mv.W, mv.H):
        im = im.resize((mv.W, mv.H), Image.LANCZOS)
    rgba = np.dstack([np.asarray(im)[..., ::-1], np.full((mv.H, mv.W), 255, np.uint8)]).copy()
    surf = cairo.ImageSurface.create_for_data(rgba, cairo.FORMAT_ARGB32, mv.W, mv.H)
    ctx = cairo.Context(surf)
    if f['flash'] > 0:
        ctx.set_source_rgba(1, 1, 1, f['flash'] * 0.35)
        ctx.paint()
    for (x, y, age, big) in f['bursts']:
        mv.draw_burst(ctx, x, y, age, big)
    fade = 0
    for tx in f['texts']:
        if tx[0] == '__fade__':
            fade = tx[1]
            continue
        text, x, y, size, fill, stroke, alpha = tx
        mv.draw_text(ctx, text, x, y, size, fill, stroke, alpha, rot=0.04 * math.sin(f['beat'] * math.pi))
    if fade > 0:
        ctx.set_source_rgba(1, 1, 1, fade)
        ctx.paint()
    surf.flush()
    Image.fromarray(rgba[..., 2::-1].copy()).save(out_jpg, quality=94)


# ---------------------------------------------------------------- メイン

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?', default=os.path.join(HERE, 'baaru_peekaboo_dance_3d.mp4'))
    ap.add_argument('--frames', default=None)
    ap.add_argument('--pct', type=int, default=75)
    ap.add_argument('--samples', type=int, default=6)
    ap.add_argument('--stills', default=None)
    ap.add_argument('--workdir', default=os.path.join(HERE, 'frames3d'))
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    wav = os.path.join(a.workdir, 'audio.wav')
    mv.build_audio(wav)
    nframes = int(mv.DURATION * mv.FPS)
    frames = precompute(nframes)
    S = build_scene(a.pct, a.samples)
    sc = bpy.context.scene
    tmp = os.path.join(a.workdir, '_render.png')
    sc.render.filepath = tmp

    if a.stills:
        idx = [int(float(s) * mv.FPS) for s in a.stills.split(',')]
    else:
        lo, hi = (0, nframes)
        if a.frames:
            lo, hi = (int(v) for v in a.frames.split(':'))
        idx = range(lo, hi)
    t0 = time.time()
    done = 0
    for i in idx:
        out = os.path.join(a.workdir, f'{i:05d}.jpg')
        if os.path.exists(out) and not a.stills:
            continue
        apply_frame(S, frames[i])
        bpy.ops.render.render(write_still=True)
        composite(tmp, frames[i], out)
        done += 1
        if done % 10 == 0 or a.stills:
            el = time.time() - t0
            print(f'frame {i} ({done} done, {el / done:.1f}s/frame)', flush=True)

    if a.stills:
        return
    missing = [i for i in range(nframes) if not os.path.exists(os.path.join(a.workdir, f'{i:05d}.jpg'))]
    if missing:
        print('missing frames:', len(missing))
        return
    subprocess.run([
        'ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(mv.FPS),
        '-i', os.path.join(a.workdir, '%05d.jpg'), '-i', wav,
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', a.out,
    ], check=True)
    print('done', a.out)


if __name__ == '__main__':
    main()
