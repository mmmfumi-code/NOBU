"""ばぁる「いないいないばぁ」ダンス動画（試作版）ジェネレーター.

python3 make_video.py [out.mp4]
キャラクター描画・音楽・効果音をすべてプログラムで生成し、ffmpeg で MP4 にする。
"""
import math
import random
import subprocess
import sys
import wave

import cairo
import numpy as np

W, H = 1280, 720
FPS = 30
BPM = 100
SPB = 60.0 / BPM  # 1拍の秒数
SR = 44100

# ---- 構成（小節番号） ----
INTRO = 0      # 0-3   イントロ：草むらからばぁ
A1 = 4         # 4-11  ダンス
CH1 = 12       # 12-19 いないいないばぁ x4
A2 = 20        # 20-27 ダンス2（横ステップ・くるり）
CH2 = 28       # 28-35 おともだちと いないいないばぁ
OUTRO = 36     # 36-39 おわり
END_BAR = 40
TAIL = 2.5
DURATION = END_BAR * 4 * SPB + TAIL

GROUND = 590


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def ease(v):
    v = clamp(v)
    return v * v * (3 - 2 * v)


def ease_out_back(v, s=2.2):
    v = clamp(v) - 1
    return 1 + v * v * ((s + 1) * v + s)


def hexc(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lerpc(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


SCHEMES = {
    'purple': dict(body=hexc('A98BD9'), line=hexc('7B5CB8'), dark=hexc('6A4AA6')),
    'pink': dict(body=hexc('F5A3C7'), line=hexc('D46F9A'), dark=hexc('B8557F')),
    'mint': dict(body=hexc('86D9C0'), line=hexc('4FAE92'), dark=hexc('3C8F77')),
}
FACE = hexc('FFF6E6')
CHEEK = hexc('F7A8A8')
MOUTH = hexc('F28C9C')
MOUTH_IN = hexc('C8506A')
EYE = hexc('2A2238')

# ---------------------------------------------------------------- 描画部品


def spline_path(ctx, pts):
    """閉じた Catmull-Rom スプラインをベジェで描く."""
    n = len(pts)
    ctx.move_to(*pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        ctx.curve_to(*c1, *c2, *p2)
    ctx.close_path()


BODY_PTS = [
    (-0.30, -0.64), (-0.13, -0.46), (0.05, -0.43), (0.25, -0.45), (0.41, -0.37),
    (0.53, -0.22), (0.46, -0.07), (0.48, 0.15), (0.41, 0.40), (0.15, 0.52),
    (-0.15, 0.52), (-0.40, 0.42), (-0.50, 0.15), (-0.50, -0.15), (-0.45, -0.46),
]
FACE_PTS = [(math.cos(a) * rx, math.sin(a) * ry) for a, rx, ry in [
    (2 * math.pi * i / 12, 0.36 + 0.015 * math.sin(i * 2.3), 0.33 + 0.012 * math.cos(i * 1.7))
    for i in range(12)]]
FACE_C = (-0.04, 0.05)


def body_points(ear, t):
    pts = list(BODY_PTS)
    # 左の大きい耳：ear で左右にゆれる
    ex, ey = pts[0]
    px, py = -0.25, -0.30
    a = ear * 0.35
    dx, dy = ex - px, ey - py
    pts[0] = (px + dx * math.cos(a) - dy * math.sin(a), py + dx * math.sin(a) + dy * math.cos(a))
    # 右の小さい耳：ぷるぷる
    w = 0.03 * math.sin(t * 9) * abs(ear) + ear * 0.04
    pts[5] = (pts[5][0] + abs(w) + 0.01, pts[5][1] - w)
    return pts


def draw_baaru(ctx, st, t):
    if st.get('alpha', 1) <= 0.01 or st.get('size', 1) <= 1:
        return
    sc = SCHEMES[st.get('scheme', 'purple')]
    size = st['size']
    x, y = st['x'], st['y']
    hop = st.get('hop', 0)

    # 影（地面に固定）
    ctx.save()
    sh = 1 - clamp(hop / 260) * 0.5
    ctx.translate(x, GROUND + 4)
    ctx.scale(size * 0.42 * sh, size * 0.05 * sh)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.set_source_rgba(0.2, 0.15, 0.3, 0.18 * st.get('alpha', 1))
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.translate(x, y - hop)
    ctx.rotate(st.get('rot', 0))
    flip = st.get('flip', 1.0)
    ctx.scale(size * st.get('sx', 1) * flip, size * st.get('sy', 1))
    ctx.translate(0, -0.52)
    ctx.push_group()

    pts = body_points(st.get('ear', 0), t)
    spline_path(ctx, pts)
    ctx.set_source_rgb(*sc['body'])
    ctx.fill_preserve()
    ctx.set_line_width(0.035)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_source_rgb(*sc['line'])
    ctx.stroke()
    # ほんのりハイライト
    ctx.save()
    ctx.translate(-0.32, -0.38)
    ctx.rotate(-0.5)
    ctx.scale(0.05, 0.11)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.set_source_rgba(1, 1, 1, 0.35)
    ctx.fill()
    ctx.restore()

    back = flip < 0
    k = st.get('face', 1.0)
    if back:
        # うしろ姿：フードの縫い目
        ctx.set_source_rgba(*sc['dark'], 0.5)
        ctx.set_line_width(0.025)
        ctx.move_to(-0.02, -0.38)
        ctx.curve_to(0.02, -0.1, -0.04, 0.2, 0.0, 0.45)
        ctx.stroke()
    elif k > 0.02:
        draw_face(ctx, st, k)
    if not back and k < 0.35:
        # フードがとじた合わせ目
        a = (0.35 - k) / 0.35
        ctx.set_source_rgba(*sc['dark'], 0.8 * a)
        ctx.set_line_width(0.03)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(FACE_C[0], FACE_C[1] - 0.3)
        ctx.curve_to(FACE_C[0] + 0.05, FACE_C[1] - 0.1, FACE_C[0] - 0.05, FACE_C[1] + 0.1, FACE_C[0], FACE_C[1] + 0.3)
        ctx.stroke()

    ctx.pop_group_to_source()
    ctx.paint_with_alpha(st.get('alpha', 1))
    ctx.restore()


def draw_face(ctx, st, k):
    ctx.save()
    ctx.translate(*FACE_C)
    ctx.scale(k, k)
    spline_path(ctx, FACE_PTS)
    ctx.set_source_rgb(*FACE)
    ctx.fill()

    happy = st.get('happy', 0)
    blink = st.get('blink', 0)
    look = st.get('look', 0) * 0.03
    for ex in (-0.14, 0.15):
        ctx.save()
        ctx.translate(ex + look, -0.06)
        if happy > 0.5:
            ctx.set_source_rgb(*EYE)
            ctx.set_line_width(0.035)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.arc_negative(0, 0.03, 0.055, -0.3, -math.pi + 0.3)
            ctx.stroke()
        else:
            ctx.save()
            ctx.scale(0.058, 0.088 * max(0.08, 1 - blink))
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.set_source_rgb(*EYE)
            ctx.fill()
            if blink < 0.5:
                ctx.arc(-0.018, -0.03, 0.018, 0, 2 * math.pi)
                ctx.set_source_rgb(1, 1, 1)
                ctx.fill()
        ctx.restore()
    for cx in (-0.26, 0.27):
        ctx.save()
        ctx.translate(cx, 0.07)
        ctx.scale(0.065, 0.04)
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(*CHEEK, 0.85)
        ctx.fill()
    m = st.get('mouth', 0)
    ctx.save()
    ctx.translate(0.0, 0.1 + m * 0.02)
    ctx.scale(0.045 + m * 0.03, 0.045 + m * 0.06)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source_rgb(*MOUTH)
    ctx.fill()
    if m > 0.2:
        ctx.save()
        ctx.translate(0.0, 0.13 + m * 0.02)
        ctx.scale((0.025 + m * 0.02), (0.02 + m * 0.035))
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgb(*MOUTH_IN)
        ctx.fill()
    ctx.restore()


def star_path(ctx, r, n=5, inner=0.5):
    for i in range(n * 2):
        a = -math.pi / 2 + i * math.pi / n
        rr = r if i % 2 == 0 else r * inner
        (ctx.move_to if i == 0 else ctx.line_to)(math.cos(a) * rr, math.sin(a) * rr)
    ctx.close_path()


def draw_text(ctx, text, x, y, size, fill, stroke, alpha=1.0, rot=0.0):
    if alpha <= 0.01 or size < 2:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.select_font_face('WenQuanYi Zen Hei', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    ext = ctx.text_extents(text)
    ctx.move_to(-ext.width / 2 - ext.x_bearing, -ext.height / 2 - ext.y_bearing)
    ctx.text_path(text)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_width(size * 0.16)
    ctx.set_source_rgba(*stroke, alpha)
    ctx.stroke_preserve()
    ctx.set_source_rgba(*fill, alpha)
    ctx.fill()
    ctx.restore()


# ---------------------------------------------------------------- 背景

PALETTES = [  # (空の上, 空の下, 丘, 手前の丘)
    (hexc('9ED8FF'), hexc('E6F6FF'), hexc('9BDB8C'), hexc('7CCB6E')),   # intro
    (hexc('FFE27A'), hexc('FFF6CF'), hexc('A8E6A1'), hexc('86D47E')),   # A1
    (hexc('FFB8D6'), hexc('FFEAF3'), hexc('B6E3A8'), hexc('93D488')),   # chorus1
    (hexc('8EE5CF'), hexc('E2FBF4'), hexc('C2E89A'), hexc('A2D877')),   # A2
    (hexc('C9B5FF'), hexc('F1ECFF'), hexc('A8E6A1'), hexc('86D47E')),   # chorus2
    (hexc('FFC59E'), hexc('FFF0E3'), hexc('B6E3A8'), hexc('93D488')),   # outro
]
SECTION_START = [INTRO, A1, CH1, A2, CH2, OUTRO]

rng = random.Random(7)
BUBBLES = [dict(x=rng.uniform(0, W), sp=rng.uniform(18, 45), r=rng.uniform(14, 40),
                ph=rng.uniform(0, 100), c=rng.choice(['FF8FB1', '7FC8FF', 'FFD25F', '9BE38F', 'C49BFF']))
           for _ in range(14)]
STARS = [dict(x=rng.uniform(40, W - 40), y=rng.uniform(40, 300), r=rng.uniform(8, 16), ph=rng.random())
         for _ in range(12)]
CLOUDS = [dict(y=rng.uniform(70, 230), sp=rng.uniform(10, 22), s=rng.uniform(0.7, 1.2), ph=rng.uniform(0, W))
          for _ in range(4)]


def palette_at(bar_f):
    idx = 0
    for i, s in enumerate(SECTION_START):
        if bar_f >= s:
            idx = i
    if idx + 1 < len(SECTION_START):
        nxt = SECTION_START[idx + 1]
        f = ease((bar_f - (nxt - 0.25)) / 0.25)
        if f > 0:
            return tuple(lerpc(a, b, f) for a, b in zip(PALETTES[idx], PALETTES[idx + 1]))
    return PALETTES[idx]


def draw_background(ctx, t, beat, flash):
    bar_f = beat / 4
    top, bot, hill, hill2 = palette_at(bar_f)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(0.8, *bot)
    ctx.set_source(g)
    ctx.paint()

    # 太陽（ゆっくり回る）
    ctx.save()
    ctx.translate(1110, 110)
    ctx.rotate(t * 0.2)
    pulse = 1 + 0.06 * math.cos(beat * math.pi * 2) ** 8
    for i in range(10):
        ctx.save()
        ctx.rotate(i * math.pi / 5)
        ctx.rectangle(62 * pulse, -7, 30, 14)
        ctx.restore()
    ctx.set_source_rgba(*hexc('FFC93C'), 0.9)
    ctx.fill()
    ctx.arc(0, 0, 55 * pulse, 0, 2 * math.pi)
    ctx.set_source_rgb(*hexc('FFD54F'))
    ctx.fill()
    ctx.restore()

    for c in CLOUDS:
        cx = (c['ph'] + t * c['sp']) % (W + 300) - 150
        ctx.save()
        ctx.translate(cx, c['y'])
        ctx.scale(c['s'], c['s'])
        for dx, dy, r in [(-50, 10, 34), (0, -8, 46), (52, 8, 36), (0, 20, 36)]:
            ctx.arc(dx, dy, r, 0, 2 * math.pi)
            ctx.new_sub_path()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.fill()
        ctx.restore()

    for s in STARS:
        tw = 0.5 + 0.5 * math.sin(2 * math.pi * (beat / 2 + s['ph']))
        ctx.save()
        ctx.translate(s['x'], s['y'])
        ctx.rotate(t * 0.5 + s['ph'] * 6)
        star_path(ctx, s['r'] * (0.7 + 0.5 * tw))
        ctx.set_source_rgba(1, 1, 1, 0.35 + 0.5 * tw)
        ctx.fill()
        ctx.restore()

    # 奥の丘
    ctx.move_to(0, 520)
    ctx.curve_to(300, 430, 600, 540, 900, 470)
    ctx.curve_to(1050, 440, 1200, 470, W, 500)
    ctx.line_to(W, H)
    ctx.line_to(0, H)
    ctx.close_path()
    ctx.set_source_rgb(*hill)
    ctx.fill()
    # 地面
    ctx.rectangle(0, GROUND - 20, W, H)
    ctx.set_source_rgb(*hill2)
    ctx.fill()
    ctx.move_to(0, GROUND - 20)
    for i in range(0, W + 1, 80):
        ctx.curve_to(i + 20, GROUND - 40, i + 60, GROUND - 40, i + 80, GROUND - 20)
    ctx.line_to(W, H)
    ctx.line_to(0, H)
    ctx.close_path()
    ctx.set_source_rgb(*hill2)
    ctx.fill()
    # お花
    for i, fx in enumerate(range(60, W, 140)):
        fy = GROUND + 50 + (i % 2) * 40
        sway = math.sin(beat * math.pi + i) * 0.2
        ctx.save()
        ctx.translate(fx, fy)
        ctx.rotate(sway)
        col = hexc(['FF8FB1', 'FFD25F', 'FFFFFF', '7FC8FF', 'C49BFF'][i % 5])
        for p in range(5):
            a = p * 2 * math.pi / 5
            ctx.arc(math.cos(a) * 11, math.sin(a) * 11, 9, 0, 2 * math.pi)
            ctx.new_sub_path()
        ctx.set_source_rgb(*col)
        ctx.fill()
        ctx.arc(0, 0, 7, 0, 2 * math.pi)
        ctx.set_source_rgb(*hexc('FFB300'))
        ctx.fill()
        ctx.restore()

    if flash > 0:
        ctx.set_source_rgba(1, 1, 1, flash * 0.45)
        ctx.paint()


def draw_bubbles(ctx, t):
    for b in BUBBLES:
        y = H + 60 - ((t * b['sp'] + b['ph'] * 10) % (H + 140))
        x = b['x'] + 25 * math.sin(t * 0.8 + b['ph'])
        ctx.arc(x, y, b['r'], 0, 2 * math.pi)
        ctx.set_source_rgba(*hexc(b['c']), 0.35)
        ctx.fill_preserve()
        ctx.set_line_width(3)
        ctx.set_source_rgba(1, 1, 1, 0.7)
        ctx.stroke()
        ctx.arc(x - b['r'] * 0.35, y - b['r'] * 0.35, b['r'] * 0.18, 0, 2 * math.pi)
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.fill()


BURST_COLORS = [hexc(c) for c in ['FF5C8A', 'FFC233', '3EC6FF', '7BDB5A', 'B57BFF', 'FF8A3D']]


def draw_burst(ctx, x, y, age, big=1.0):
    """ばぁ！のときに飛び散るお星さま."""
    if age < 0 or age > 1.4:
        return
    a = 1 - clamp((age - 0.8) / 0.6)
    n = 14
    for i in range(n):
        ang = i * 2 * math.pi / n + 0.2
        d = (60 + 260 * big) * (1 - math.exp(-age * 4))
        ctx.save()
        ctx.translate(x + math.cos(ang) * d, y + math.sin(ang) * d * 0.8)
        ctx.rotate(age * 4 + i)
        star_path(ctx, 22 * big * (1 - age * 0.3))
        ctx.set_source_rgba(*BURST_COLORS[i % len(BURST_COLORS)], a)
        ctx.fill()
        ctx.restore()
    # 輪っか
    r = 40 + 300 * big * (1 - math.exp(-age * 5))
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.set_line_width(10 * (1 - clamp(age / 0.7)))
    ctx.set_source_rgba(1, 1, 1, 0.8 * (1 - clamp(age / 0.7)))
    ctx.stroke()


# ---------------------------------------------------------------- 振り付け

def base_state(scheme='purple', x=640, size=300):
    return dict(x=x, y=GROUND, size=size, sx=1, sy=1, rot=0, face=1, mouth=0, happy=0,
                blink=0, ear=0, hop=0, flip=1, alpha=1, scheme=scheme, look=0)


def blink_at(t, seed=0):
    p = (t + seed * 1.37) % 3.3
    return clamp(1 - abs(p - 0.1) / 0.08)


def peekaboo(st, p, pops=True, x_from=None, x_to=None):
    """p: 2小節（8拍）内の拍位置。0-1 でフードを閉じ、4 で「ばぁ！」."""
    if p < 1:
        st['face'] = 1 - ease(p)
        st['sy'] = 1 - 0.08 * math.sin(math.pi * p)
        st['ear'] = -0.6 * ease(p)
    elif p < 4 or not pops:
        st['face'] = 0
        q = p - 1
        st['hop'] = 14 * abs(math.sin(math.pi * q))
        st['rot'] = 0.06 * math.sin(math.pi * q)
        st['ear'] = -0.6 + 0.15 * math.sin(2 * math.pi * q)
        if x_from is not None and p < 3:
            st['x'] = x_from + (x_to - x_from) * ease((p - 1) / 2)
            st['hop'] = 70 * math.sin(math.pi * clamp((p - 1) / 2))
        elif x_to is not None:
            st['x'] = x_to
        if p > 3.4 and pops:  # ためる
            a = ease((p - 3.4) / 0.6)
            st['sy'] = 1 - 0.18 * a
            st['sx'] = 1 + 0.12 * a
            st['hop'] = 0
            st['rot'] = 0.04 * math.sin(p * 40) * a
    else:
        q = p - 4
        if x_to is not None:
            st['x'] = x_to
        st['face'] = ease_out_back(q / 0.3, 3.0)
        st['hop'] = 90 * math.sin(math.pi * clamp(q / 0.9))
        st['sy'] = 1 + 0.2 * math.exp(-q * 4) * math.cos(q * 12)
        st['sx'] = 1 - 0.1 * math.exp(-q * 4) * math.cos(q * 12)
        st['ear'] = 0.8 * math.exp(-q * 1.5) * math.sin(q * 10)
        st['happy'] = 1 if q < 2.2 else 0
        st['mouth'] = clamp(1 - (q - 1.5) / 1.0)
        if q > 2.5:
            st['rot'] = 0.08 * math.sin(math.pi * q)
    return st


def dance_bounce(st, b):
    ph = b % 1
    st['hop'] = 38 * math.sin(math.pi * ph)
    land = math.exp(-ph * 9) + math.exp(-(1 - ph) * 12) * 0.4
    st['sy'] = 1 - 0.14 * land + 0.06 * math.sin(math.pi * ph)
    st['sx'] = 1 + 0.12 * land
    st['rot'] = 0.12 * math.sin(math.pi * b / 2)
    st['ear'] = 0.5 * math.sin(math.pi * b)
    st['mouth'] = 0.3 * math.sin(math.pi * ph)


def dance_sway(st, b):
    st['x'] += 140 * math.sin(math.pi * b / 4)
    st['rot'] = -0.22 * math.sin(math.pi * b / 2)
    st['hop'] = 12 * abs(math.sin(math.pi * b))
    st['ear'] = 0.7 * math.sin(math.pi * b / 2 + 0.6)
    st['look'] = -math.sin(math.pi * b / 2)
    st['sy'] = 1 + 0.05 * math.cos(math.pi * b * 2)


def dance_spin_jump(st, q):
    """1小節（4拍）でジャンプしながらくるっと回る."""
    j = clamp((q - 1) / 2)
    st['hop'] = 170 * math.sin(math.pi * j)
    st['flip'] = math.cos(2 * math.pi * j) if 0 < j < 1 else 1
    if abs(st['flip']) < 0.04:
        st['flip'] = 0.04 if st['flip'] >= 0 else -0.04
    if q < 1:
        a = math.sin(math.pi * q)
        st['sy'] = 1 - 0.2 * a
        st['sx'] = 1 + 0.12 * a
    elif q > 3:
        a = math.exp(-(q - 3) * 6)
        st['sy'] = 1 - 0.18 * a
        st['sx'] = 1 + 0.14 * a
        st['happy'] = 1
        st['mouth'] = 0.8
    st['ear'] = 0.9 * math.sin(math.pi * j * 2)


def dance_sidestep(st, b):
    seg = int(b // 2)
    ph = (b % 2) / 2
    pos = [-170, 170]
    x0 = pos[(seg + 1) % 2]
    x1 = pos[seg % 2]
    st['x'] = 640 + x0 + (x1 - x0) * ease(ph)
    st['hop'] = 60 * math.sin(math.pi * ph)
    st['rot'] = 0.25 * math.sin(math.pi * ph) * (1 if x1 > x0 else -1)
    st['look'] = 1 if x1 > x0 else -1
    st['ear'] = 0.6 * math.sin(math.pi * ph * 2)
    land = math.exp(-ph * 2 * 8)
    st['sy'] = 1 - 0.12 * land
    st['sx'] = 1 + 0.1 * land
    st['mouth'] = 0.4 * math.sin(math.pi * ph)


def dance_turn(st, b):
    """2拍ごとにうしろを向いて、また前を向く（ミニいないいないばぁ）."""
    ph = (b % 4) / 4
    st['flip'] = math.cos(2 * math.pi * ph)
    if abs(st['flip']) < 0.04:
        st['flip'] = 0.04 if st['flip'] >= 0 else -0.04
    st['hop'] = 25 * abs(math.sin(math.pi * b))
    st['rot'] = 0.06 * math.sin(math.pi * b)
    st['ear'] = 0.5 * math.sin(math.pi * b)
    if ph > 0.85 or ph < 0.1:
        st['happy'] = 1
        st['mouth'] = 0.6


def scene(t):
    """時刻 t の全キャラクター状態と演出を返す."""
    beat = t / SPB
    bar = int(beat // 4)
    q = beat - bar * 4  # 小節内の拍
    chars = []
    texts = []
    bursts = []  # (x, y, age, big)
    flash = 0.0
    bush = None

    main = base_state()
    main['blink'] = blink_at(t)

    if bar < A1:
        # イントロ：草むらから耳がのぞいて…ばぁ！
        bush_y = 0
        if beat < 12:
            peek = 0
            if 2 <= beat < 4:
                peek = math.sin(math.pi * (beat - 2) / 2)
            if 6 <= beat < 8:
                peek = math.sin(math.pi * (beat - 6) / 2) * 1.3
            if 10 <= beat < 12:
                peek = math.sin(math.pi * (beat - 10) / 2) * 0.6
            main['y'] = GROUND + 260 - peek * 90
            main['ear'] = 0.4 * math.sin(beat * 3)
            main['face'] = 1
            if beat >= 8:
                texts.append(('いない いない…', 640, 140, 70 * ease_out_back((beat - 8) / 0.5),
                              hexc('FFFFFF'), hexc('8A6BC9'), 1.0))
        else:
            qq = beat - 12
            main['y'] = GROUND
            peekaboo(main, 4 + qq)
            bush_y = 400 * ease((qq - 0.1) / 1.5)
            bursts.append((640, GROUND - 200, qq * SPB, 1.0))
            flash = math.exp(-qq * 5)
            texts.append(('ばぁ！', 640, 130, 130 * ease_out_back(qq / 0.35),
                          hexc('FFFFFF'), hexc('FF5C8A'), clamp(1 - (qq - 3.2) / 0.6)))
        bush = bush_y
        chars.append(main)
    elif bar < CH1:
        b = beat - A1 * 4
        if b < 16:
            dance_bounce(main, b)
        elif b < 28:
            dance_sway(main, b)
        else:
            dance_spin_jump(main, b - 28)
        chars.append(main)
    elif bar < A2:
        b = beat - CH1 * 4
        n = int(b // 8)
        p = b % 8
        spots = [640, 400, 880, 640]
        prev = spots[n - 1] if n > 0 else 640
        main['x'] = prev
        peekaboo(main, p, x_from=prev, x_to=spots[n])
        if p < 4:
            texts.append(('いない', 400, 130, 72 * ease_out_back(p / 0.4), hexc('FFFFFF'), hexc('8A6BC9'), 1))
            if p >= 2:
                texts.append(('いない', 880, 130, 72 * ease_out_back((p - 2) / 0.4), hexc('FFFFFF'), hexc('8A6BC9'), 1))
        else:
            qq = p - 4
            texts.append(('ばぁ！', 640, 130, 140 * ease_out_back(qq / 0.35), hexc('FFFFFF'),
                          hexc(['FF5C8A', 'FF8A3D', '3EA6FF', '7BC94A'][n]), clamp(1 - (qq - 3) / 0.7)))
            bursts.append((spots[n], GROUND - 200, qq * SPB, 1.0))
            flash = math.exp(-qq * 5)
        chars.append(main)
    elif bar < CH2:
        b = beat - A2 * 4
        if b < 16:
            dance_sidestep(main, b)
        elif b < 28:
            dance_turn(main, b - 16)
        else:
            dance_spin_jump(main, b - 28)
            # おともだち登場
        chars.append(main)
        if b >= 30:
            e = ease_out_back((b - 30) / 1.0)
            for sch, x in (('pink', 330), ('mint', 950)):
                f = base_state(sch, x, 210 * e)
                f['blink'] = blink_at(t, 1 if sch == 'pink' else 2)
                f['hop'] = 120 * math.sin(math.pi * clamp((b - 30) / 1.2))
                f['happy'] = 1
                f['mouth'] = 0.5
                chars.append(f)
    elif bar < OUTRO:
        b = beat - CH2 * 4
        n = int(b // 8)
        p = b % 8
        order = [['pink'], ['mint'], ['purple'], ['pink', 'mint', 'purple']]
        cast = [('pink', 330, 210), ('mint', 950, 210), ('purple', 640, 300)]
        for i, (sch, x, size) in enumerate(cast):
            c = base_state(sch, x, size)
            c['blink'] = blink_at(t, i)
            pops = sch in order[n]
            peekaboo(c, p, pops=pops)
            if not pops and p >= 4:
                # 自分の番じゃない子は、かくれたまま ゆらゆら
                c['face'] = 0
                c['ear'] = -0.6 + 0.2 * math.sin(math.pi * p)
                c['hop'] = 10 * abs(math.sin(math.pi * p))
            chars.append(c)
            if pops and p >= 4:
                bursts.append((x, GROUND - size * 0.7, (p - 4) * SPB, 1.4 if n == 3 else size / 300))
        if p < 4:
            texts.append(('いない', 400, 120, 72 * ease_out_back(p / 0.4), hexc('FFFFFF'), hexc('8A6BC9'), 1))
            if p >= 2:
                texts.append(('いない', 880, 120, 72 * ease_out_back((p - 2) / 0.4), hexc('FFFFFF'), hexc('8A6BC9'), 1))
        else:
            qq = p - 4
            texts.append(('ばぁ！', 640, 120, (150 if n == 3 else 130) * ease_out_back(qq / 0.35), hexc('FFFFFF'),
                          hexc(['FF5C8A', '2FBF9A', 'A06BE0', 'FF8A3D'][n]), clamp(1 - (qq - 3) / 0.7)))
            flash = math.exp(-qq * 5)
    else:
        b = beat - OUTRO * 4
        cast = [('pink', 330, 210), ('mint', 950, 210), ('purple', 640, 300)]
        for i, (sch, x, size) in enumerate(cast):
            c = base_state(sch, x, size)
            c['blink'] = blink_at(t, i)
            if b < 8:
                c['rot'] = 0.15 * math.sin(math.pi * b / 2 + i)
                c['ear'] = 0.9 * math.sin(math.pi * b + i)  # 耳でばいばい
                c['hop'] = 15 * abs(math.sin(math.pi * b))
                c['mouth'] = 0.3
            else:
                peekaboo(c, b - 8)
                if b - 8 >= 4:
                    c['happy'] = 1
                    c['mouth'] = 0.7
            chars.append(c)
        if b < 8:
            texts.append(('またね〜', 640, 120, 90 * ease_out_back(b / 0.6), hexc('FFFFFF'), hexc('FF8A3D'), 1))
        elif b < 12:
            texts.append(('いない いない', 640, 120, 72 * ease_out_back((b - 8) / 0.4), hexc('FFFFFF'),
                          hexc('8A6BC9'), 1))
        else:
            qq = b - 12
            texts.append(('ばぁ！', 640, 120, 160 * ease_out_back(qq / 0.35), hexc('FFFFFF'), hexc('FF5C8A'), 1))
            bursts.append((640, GROUND - 220, qq * SPB, 1.5))
            flash = math.exp(-qq * 5)
        fade = clamp((t - (DURATION - 1.2)) / 1.2)
        if fade > 0:
            texts.append(('__fade__', fade))
    return beat, chars, texts, bursts, flash, bush


def draw_bush(ctx, offset):
    if offset is None or offset > 380:
        return
    ctx.save()
    ctx.translate(640, GROUND + 40 + offset)
    for dx, dy, r in [(-150, -40, 90), (-60, -110, 110), (60, -120, 115), (160, -50, 90),
                      (0, -20, 130), (-200, 10, 70), (210, 10, 70),
                      (-130, 70, 120), (130, 70, 120), (0, 90, 150)]:
        ctx.arc(dx, dy, r, 0, 2 * math.pi)
        ctx.new_sub_path()
    path = ctx.copy_path()
    ctx.set_line_width(12)
    ctx.set_source_rgb(*hexc('3E9A4A'))
    ctx.stroke()
    ctx.append_path(path)
    ctx.set_source_rgb(*hexc('5DBB63'))
    ctx.fill()
    for dx, dy in [(-120, -90), (70, -150), (150, -40), (-30, -40)]:
        ctx.arc(dx, dy, 12, 0, 2 * math.pi)
        ctx.set_source_rgb(*hexc('FF6F91'))
        ctx.fill()
    ctx.restore()


def render_frame(surface, t):
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    beat, chars, texts, bursts, flash, bush = scene(t)
    draw_background(ctx, t, beat, flash)
    draw_bubbles(ctx, t)
    for (x, y, age, big) in bursts:
        draw_burst(ctx, x, y, age, big)
    for c in sorted(chars, key=lambda c: c['size']):
        draw_baaru(ctx, c, t)
    draw_bush(ctx, bush)
    fade = 0
    for tx in texts:
        if tx[0] == '__fade__':
            fade = tx[1]
            continue
        text, x, y, size, fill, stroke, alpha = tx
        draw_text(ctx, text, x, y, size, fill, stroke, alpha, rot=0.04 * math.sin(beat * math.pi))
    if fade > 0:
        ctx.set_source_rgba(1, 1, 1, fade)
        ctx.paint()


# ---------------------------------------------------------------- 音楽

def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Mixer:
    def __init__(self, dur):
        self.buf = np.zeros(int(dur * SR) + SR, dtype=np.float64)

    def add(self, t0, sig, gain=1.0):
        i = int(t0 * SR)
        n = min(len(sig), len(self.buf) - i)
        if n > 0:
            self.buf[i:i + n] += sig[:n] * gain


def env_t(dur):
    return np.arange(int(dur * SR)) / SR


def marimba(f, dur=0.9):
    t = env_t(dur)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 25)
    s += 0.15 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 8)
    return s * np.exp(-t * 5) * np.minimum(1, t * 400)


def toy_piano(f, dur=1.2):
    t = env_t(dur)
    s = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4)
         + 0.25 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 7))
    return s * np.exp(-t * 3.2) * np.minimum(1, t * 600)


def bell(f, dur=2.0):
    t = env_t(dur)
    s = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t * 3)
         + 0.3 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t * 6))
    return s * np.exp(-t * 2.2) * np.minimum(1, t * 800)


def bass(f, dur=0.6):
    t = env_t(dur)
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    return s * np.exp(-t * 4) * np.minimum(1, t * 200)


def pad(freqs, dur):
    t = env_t(dur)
    s = sum(np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.004 * t) for f in freqs)
    e = np.minimum(1, t / 0.3) * np.minimum(1, (dur - t) / 0.4)
    return s * e / (2 * len(freqs))


def kick():
    t = env_t(0.25)
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)


NOISE = np.random.default_rng(1).standard_normal(SR)


def shaker():
    t = env_t(0.08)
    n = NOISE[:len(t)]
    n = np.diff(n, prepend=0)
    return n * np.exp(-t * 60)


def wood():
    t = env_t(0.12)
    return (np.sin(2 * np.pi * 1100 * t) + 0.5 * np.sin(2 * np.pi * 1750 * t)) * np.exp(-t * 45)


def pop_sfx():
    t = env_t(0.18)
    f = 350 + 1300 * (1 - np.exp(-t * 25))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 18)
    return s + 0.3 * NOISE[:len(t)] * np.exp(-t * 120)


def whoosh_down():
    t = env_t(0.5)
    f = 1400 * np.exp(-t * 3) + 300
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.5) * 0.6


def boing():
    t = env_t(0.45)
    f = 220 + 260 * (1 - np.exp(-t * 8)) + 40 * np.sin(2 * np.pi * 14 * t) * np.exp(-t * 4)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)


CHORDS = {
    'C': [60, 64, 67], 'F': [65, 69, 72], 'G': [62, 67, 71], 'G7': [62, 65, 71], 'Am': [60, 64, 69],
}
ROOT = {'C': 48, 'F': 41, 'G': 43, 'G7': 43, 'Am': 45}

MEL_A = [
    [(72, 1), (76, 1), (79, 1), (76, 1)],
    [(77, 1), (81, 1), (79, 2)],
    [(76, 1), (74, 1), (72, 1), (74, 1)],
    [(76, 2), (74, 2)],
    [(72, 1), (76, 1), (79, 1), (76, 1)],
    [(77, 1), (81, 1), (79, 1), (76, 1)],
    [(74, 1), (76, 1), (77, 1), (74, 1)],
    [(72, 4)],
]
CH_A = ['C', 'F', 'C', 'G', 'C', 'F', 'G7', 'C']
PEEK = [('C', [79, 76, 79, 76]), ('F', [81, 77, 81, 77]), ('G', [83, 79, 83, 79]), ('C', [84, 79, 84, 79])]


def bar_t(bar, beat=0.0):
    return (bar * 4 + beat) * SPB


def build_audio(path):
    mx = Mixer(DURATION)

    def drums(bar, light=False):
        for bt in range(4):
            if bt in (0, 2):
                mx.add(bar_t(bar, bt), kick(), 0.55)
            else:
                mx.add(bar_t(bar, bt), wood(), 0.12)
        if not light:
            for e in range(8):
                mx.add(bar_t(bar, e * 0.5), shaker(), 0.07 if e % 2 else 0.04)

    def chord_bar(bar, ch, beats=4):
        mx.add(bar_t(bar), pad([mtof(m) for m in CHORDS[ch]], beats * SPB), 0.16)
        for bt in (0, 2):
            mx.add(bar_t(bar, bt), bass(mtof(ROOT[ch])), 0.35)

    def melody(bar, notes, inst=marimba, gain=0.32, octave=0):
        bt = 0
        for m, d in notes:
            if m is not None:
                mx.add(bar_t(bar, bt), inst(mtof(m + octave), max(0.6, d * SPB + 0.3)), gain)
            bt += d

    def peek_pair(bar, ch, notes, sfx=True):
        chord_bar(bar, ch)
        chord_bar(bar + 1, ch)
        drums(bar, light=True)
        drums(bar + 1)
        melody(bar, [(m, 1) for m in notes], inst=toy_piano, gain=0.3)
        if sfx:
            mx.add(bar_t(bar), whoosh_down(), 0.12)
        # ばぁ！
        t = bar_t(bar + 1)
        mx.add(t, pop_sfx(), 0.35)
        for m in CHORDS[ch]:
            mx.add(t, bell(mtof(m + 24)), 0.12)
        mx.add(t, bell(mtof(84)), 0.2)
        for i, m in enumerate([CHORDS[ch][0] + 12, CHORDS[ch][1] + 12, CHORDS[ch][2] + 12, CHORDS[ch][0] + 24]):
            mx.add(bar_t(bar + 1, 2 + i * 0.5), marimba(mtof(m)), 0.22)

    # イントロ
    tw = random.Random(3)
    penta = [72, 74, 76, 79, 81, 84, 86, 88]
    for bar in range(0, 3):
        ch = ['C', 'G', 'C'][bar]
        mx.add(bar_t(bar), pad([mtof(m) for m in CHORDS[ch]], 4 * SPB), 0.18)
        for e in range(8):
            if tw.random() < 0.7:
                mx.add(bar_t(bar, e * 0.5), bell(mtof(tw.choice(penta)), 1.2), 0.06)
    for bt in (2, 6, 10):  # 耳がのぞく
        mx.add(bt * SPB, boing(), 0.18)
    mx.add(bar_t(2), whoosh_down(), 0.1)
    # イントロのばぁ！
    mx.add(bar_t(3), pop_sfx(), 0.4)
    for m in [72, 76, 79, 84]:
        mx.add(bar_t(3), bell(mtof(m + 12)), 0.12)
    chord_bar(3, 'C')
    for i, m in enumerate([72, 76, 79, 84]):
        mx.add(bar_t(3, 2 + i * 0.5), marimba(mtof(m)), 0.22)

    # A1
    for i in range(8):
        bar = A1 + i
        chord_bar(bar, CH_A[i])
        drums(bar)
        melody(bar, MEL_A[i])
    mx.add(bar_t(A1 + 7, 1), boing(), 0.25)  # くるっとジャンプ

    # サビ1
    for i, (ch, notes) in enumerate(PEEK):
        peek_pair(CH1 + i * 2, ch, notes)

    # A2（メロディを1オクターブ上 + トイピアノ）
    for i in range(8):
        bar = A2 + i
        chord_bar(bar, CH_A[i])
        drums(bar)
        melody(bar, MEL_A[i], inst=toy_piano, gain=0.26)
        melody(bar, MEL_A[i], inst=marimba, gain=0.12, octave=-12)
    for bt in range(0, 16, 2):  # 横ステップ
        mx.add(bar_t(A2, bt + 0.2), boing(), 0.08)
    mx.add(bar_t(A2 + 7, 1), boing(), 0.25)
    mx.add(bar_t(A2 + 7, 2.5), pop_sfx(), 0.2)  # おともだち登場
    mx.add(bar_t(A2 + 7, 2.6), pop_sfx(), 0.2)

    # サビ2
    for i, (ch, notes) in enumerate(PEEK):
        peek_pair(CH2 + i * 2, ch, notes)
    for m in [72, 76, 79, 84, 88]:
        mx.add(bar_t(CH2 + 7), bell(mtof(m + 12)), 0.08)

    # アウトロ
    for i, (ch, mel) in enumerate([('C', MEL_A[4]), ('F', MEL_A[5])]):
        chord_bar(OUTRO + i, ch)
        drums(OUTRO + i, light=True)
        melody(OUTRO + i, mel, inst=toy_piano, gain=0.26)
    chord_bar(OUTRO + 2, 'G7')
    melody(OUTRO + 2, [(79, 1), (76, 1), (79, 1), (76, 1)], inst=toy_piano, gain=0.3)
    mx.add(bar_t(OUTRO + 2), whoosh_down(), 0.12)
    t = bar_t(OUTRO + 3)
    mx.add(t, pop_sfx(), 0.4)
    mx.add(t, pad([mtof(m) for m in CHORDS['C']], 4 * SPB + TAIL), 0.2)
    mx.add(t, bass(mtof(36), 2.5), 0.4)
    for i, m in enumerate([72, 76, 79, 84, 88, 91]):
        mx.add(t + i * 0.08, bell(mtof(m), 3.0), 0.1)

    x = mx.buf[:int(DURATION * SR)]
    # かんたんなリバーブ（ディレイの重ね合わせ）
    wet = np.zeros_like(x)
    for d, g in [(0.031, 0.25), (0.047, 0.2), (0.071, 0.16), (0.113, 0.12), (0.167, 0.08), (0.241, 0.05)]:
        k = int(d * SR)
        wet[k:] += x[:-k] * g
    x = x + wet * 0.6
    x = np.tanh(x / (np.max(np.abs(x)) + 1e-9) * 1.2) * 0.85
    fade = int(1.2 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (x * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


# ---------------------------------------------------------------- 書き出し

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'baaru_peekaboo_dance.mp4'
    audio = out.rsplit('.', 1)[0] + '.wav'
    build_audio(audio)
    proc = subprocess.Popen([
        'ffmpeg', '-y', '-loglevel', 'error',
        '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
        '-i', audio,
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', out,
    ], stdin=subprocess.PIPE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    nframes = int(DURATION * FPS)
    for i in range(nframes):
        render_frame(surface, i / FPS)
        surface.flush()
        proc.stdin.write(surface.get_data())
    proc.stdin.close()
    proc.wait()
    print('done', out, f'{DURATION:.1f}s')


if __name__ == '__main__':
    main()
