#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assets/pokemon-gen1-icons/pokeicon-001.jpg ... を、index-mine.html の平面情報テクスチャで使える
高解像度ドット絵セルデータへ変換する。

狙い:
- 外周からつながる白い余白/薄い方眼罫線だけを除外
- 最大成分だけでなく、羽・針・足などの分離パーツも拾う
- 元画像内で無理に正方形cropせず、本体を安全余白つき白キャンバス中央へ配置
- 本体内部の白い目・角・爪・腹/ハイライトは残し、色スポイト相当でセルごとの代表色を取得
- generated/pokemon-info-textures.gen1.30x30.generated.js へ互換出力

使い方:
  python tools/build-pokemon-info-textures.py
  python tools/build-pokemon-info-textures.py --grid 96 --safe-pad 0.22 --input assets/pokemon-gen1-icons --out generated/pokemon-info-textures.gen1.30x30.generated.js

注意:
- ファイル名は互換のため 30x30 のままでもOK。ただし中身の grid は --grid の値になる。
- index-mine.html 側は d.grid / plane.grid を見て描画すること。
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
from PIL import Image

POKEMON_NAMES_JA = [
    '', 'フシギダネ','フシギソウ','フシギバナ','ヒトカゲ','リザード','リザードン','ゼニガメ','カメール','カメックス','キャタピー',
    'トランセル','バタフリー','ビードル','コクーン','スピアー','ポッポ','ピジョン','ピジョット','コラッタ','ラッタ',
    'オニスズメ','オニドリル','アーボ','アーボック','ピカチュウ','ライチュウ','サンド','サンドパン','ニドラン♀','ニドリーナ',
    'ニドクイン','ニドラン♂','ニドリーノ','ニドキング','ピッピ','ピクシー','ロコン','キュウコン','プリン','プクリン',
    'ズバット','ゴルバット','ナゾノクサ','クサイハナ','ラフレシア','パラス','パラセクト','コンパン','モルフォン','ディグダ',
    'ダグトリオ','ニャース','ペルシアン','コダック','ゴルダック','マンキー','オコリザル','ガーディ','ウインディ','ニョロモ',
    'ニョロゾ','ニョロボン','ケーシィ','ユンゲラー','フーディン','ワンリキー','ゴーリキー','カイリキー','マダツボミ','ウツドン',
    'ウツボット','メノクラゲ','ドククラゲ','イシツブテ','ゴローン','ゴローニャ','ポニータ','ギャロップ','ヤドン','ヤドラン',
    'コイル','レアコイル','カモネギ','ドードー','ドードリオ','パウワウ','ジュゴン','ベトベター','ベトベトン','シェルダー',
    'パルシェン','ゴース','ゴースト','ゲンガー','イワーク','スリープ','スリーパー','クラブ','キングラー','ビリリダマ',
    'マルマイン','タマタマ','ナッシー','カラカラ','ガラガラ','サワムラー','エビワラー','ベロリンガ','ドガース','マタドガス',
    'サイホーン','サイドン','ラッキー','モンジャラ','ガルーラ','タッツー','シードラ','トサキント','アズマオウ','ヒトデマン',
    'スターミー','バリヤード','ストライク','ルージュラ','エレブー','ブーバー','カイロス','ケンタロス','コイキング','ギャラドス',
    'ラプラス','メタモン','イーブイ','シャワーズ','サンダース','ブースター','ポリゴン','オムナイト','オムスター','カブト',
    'カブトプス','プテラ','カビゴン','フリーザー','サンダー','ファイヤー','ミニリュウ','ハクリュー','カイリュー','ミュウツー','ミュウ'
]




# -----------------------------------------------------------------------------
# Pokemon field3d model generator - REAL 96x96x96 full-grid source volume v6
# -----------------------------------------------------------------------------
# 根本原因:
#   前の3D生成は、いったん 16x16 に縮小したり、耳/尻尾/羽/球根などを
#   仕様表から「想像」で足していた。だから元画像に無い巨大耳・謎パーツが出た。
#
# v6方針:
#   - field3d の座標空間は必ず 96x96x96。
#   - 2D情報テクスチャの 96x96 cells を、そのまま前面シルエットとして使う。
#   - 16x16縮小は禁止。
#   - No別の fake parts 表は禁止。
#   - 元画像に無い耳/尻尾/羽/角/球根は足さない。
#   - ただし板ではなく、シルエットを奥行き方向へ膨らませた「表面ボリューム」にする。
#   - 出力セルは数千〜数万。確認HTML/本番側で外面描画する前提。
FIELD3D_GENERATOR_VERSION = 'REAL_96X96X96_SOURCE_VOLUME_V6_FULLGRID_NO_FAKE_PARTS'
FIELD3D_GRID = 96
FIELD3D_MAX_CELLS = 36000


def _hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = str(c or '#888888').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', c):
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    return (136, 136, 136)


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in rgb)


def _mix(c1: str, c2: str, t: float) -> str:
    a = _hex_to_rgb(c1)
    b = _hex_to_rgb(c2)
    t = max(0, min(1, float(t)))
    return _rgb_to_hex(tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3)))


def _luma(c: str) -> float:
    r, g, b = _hex_to_rgb(c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sat(c: str) -> float:
    r, g, b = _hex_to_rgb(c)
    return max(r, g, b) - min(r, g, b)


def _is_backgroundish(c: str) -> bool:
    # 完全な外周白背景は image_to_cells 側で除外済み。
    # ここでは field3d の膨張対象から、ほぼ白の残りカスだけ落とす。
    return _luma(c) > 248 and _sat(c) < 16


def _dominant_cell_color(counts: Dict[str, int]) -> str:
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    for c, _ in ranked:
        if not _is_backgroundish(c):
            return c
    return ranked[0][0] if ranked else '#888888'


def _normalize_plane_cells_to_96(plane_cells: List[Dict], source_grid: int) -> Dict[Tuple[int, int], str]:
    """plane cells を 96x96 座標へ正規化する。16x16等への縮小は一切しない。"""
    src = max(1, int(source_grid or 96))
    buckets: Dict[Tuple[int, int], Dict[str, int]] = {}
    for c in plane_cells:
        try:
            gx = int(c.get('x', 0))
            gy = int(c.get('y', 0))
        except Exception:
            continue
        color = str(c.get('color', '#888888')).lower()
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            continue
        if _is_backgroundish(color):
            continue
        # source_grid が96ならそのまま。そうでなくても96座標へ拡大する。
        x = max(0, min(95, int(round(gx * 95 / max(1, src - 1)))))
        y = max(0, min(95, int(round(gy * 95 / max(1, src - 1)))))
        buckets.setdefault((x, y), {})[color] = buckets.setdefault((x, y), {}).get(color, 0) + 1

    pix: Dict[Tuple[int, int], str] = {}
    for key, counts in buckets.items():
        pix[key] = _dominant_cell_color(counts)
    return pix


def _remove_isolated_noise(pix: Dict[Tuple[int, int], str]) -> Dict[Tuple[int, int], str]:
    if len(pix) < 8:
        return pix
    out: Dict[Tuple[int, int], str] = {}
    for (x, y), color in pix.items():
        n8 = sum((x + dx, y + dy) in pix
                 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if not (dx == 0 and dy == 0))
        if n8 >= 1:
            out[(x, y)] = color
    return out or pix


def _boundary_and_ring_depth(pix: Dict[Tuple[int, int], str]) -> Tuple[set, Dict[Tuple[int, int], int]]:
    """外周境界と、境界からの距離っぽい値を返す。距離が大きいほど厚くする。"""
    boundary = set()
    for x, y in pix:
        if sum((x + dx, y + dy) in pix for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) < 4:
            boundary.add((x, y))
    # BFSで境界距離をざっくり出す。96x96なので軽い。
    dist: Dict[Tuple[int, int], int] = {p: 0 for p in boundary}
    queue = list(boundary)
    head = 0
    while head < len(queue):
        x, y = queue[head]
        head += 1
        nd = dist[(x, y)] + 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q in pix and q not in dist:
                dist[q] = nd
                queue.append(q)
    return boundary, dist


def build_pokemon_voxel3d_cells(no: int, name: str, plane_cells: List[Dict], grid: int) -> List[Dict]:
    """
    96x96 の元ドット絵 cells から、96x96x96 の3Dボクセルモデルを生成する。

    重要:
      - 16x16縮小なし。
      - 偽パーツなし。
      - 元画像の全シルエットを前面として保持。
      - 奥行きは shell/volume として付与。
      - grid は field3d 側では必ず96。
    """
    pix = _normalize_plane_cells_to_96(plane_cells, grid)
    pix = _remove_isolated_noise(pix)
    if not pix:
        return []

    xs = [x for x, _ in pix]
    ys = [y for _, y in pix]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = max(1, maxx - minx + 1)
    h = max(1, maxy - miny + 1)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0

    boundary, ring_dist = _boundary_and_ring_depth(pix)
    max_ring = max(ring_dist.values() or [1])

    model_grid = FIELD3D_GRID
    cell_size = round(2.55 / model_grid, 6)
    z_front = 78
    # 最大奥行き。小型でも厚みを出し、大型はさらに厚く。
    max_depth = max(18, min(52, int(round(max(w, h) * 0.48))))

    cells: List[Dict[str, Any]] = []
    occupied = set()

    def put(x: int, y_img: int, z: int, color: str, shade: float = 0.0, priority: int = 2) -> None:
        yy = model_grid - 1 - int(y_img)  # field3dではy=0下
        if not (0 <= x < model_grid and 0 <= yy < model_grid and 0 <= z < model_grid):
            return
        key = (int(x), int(yy), int(z))
        if key in occupied:
            return
        occupied.add(key)
        cc = _mix(color, '#000000', shade) if shade > 0 else color
        cells.append({'x': int(x), 'y': int(yy), 'z': int(z), 'color': cc, 'size': cell_size, '_p': int(priority)})

    def depth_for(x: int, y: int) -> int:
        # 境界から遠い中心部ほど厚い。さらに縦横中心からの楕円距離でも丸みをつける。
        ring = ring_dist.get((x, y), 0) / max(1, max_ring)
        nx = abs((x - cx) / max(1.0, w / 2.0))
        ny = abs((y - cy) / max(1.0, h / 2.0))
        radial = min(1.0, math.sqrt(nx * nx + ny * ny))
        d = 8 + max_depth * (0.30 + 0.50 * ring + 0.20 * (1.0 - radial))
        return max(8, min(max_depth, int(round(d))))

    # 1) 前面: 96x96元画像シルエットそのもの。最優先。
    for (x, y), color in pix.items():
        put(x, y, z_front, color, 0.0, priority=0)

    # 2) 背面: 前面と同じ形を奥に置いて、板ではなく厚みを持たせる。
    for (x, y), color in pix.items():
        d = depth_for(x, y)
        z_back = max(1, z_front - d)
        put(x, y, z_back, color, 0.24, priority=1)

    # 3) 外周側面: 境界は全奥行きでつなぐ。これで横から見てもスカスカ板にならない。
    for (x, y) in boundary:
        color = pix[(x, y)]
        d = depth_for(x, y)
        z_back = max(1, z_front - d)
        for z in range(z_back + 1, z_front):
            shade = 0.08 + 0.16 * ((z_front - z) / max(1, d))
            put(x, y, z, color, shade, priority=1)

    # 4) 内部の曲面サンプル: 全埋めは重すぎるので、見える曲面っぽく間引きながら数層入れる。
    for (x, y), color in pix.items():
        if (x, y) in boundary:
            continue
        d = depth_for(x, y)
        z_back = max(1, z_front - d)
        # 中心部は複数層、端は少なめ。96^3空間内でちゃんと奥行きを使う。
        samples = (2, 3, 4) if ring_dist.get((x, y), 0) > max_ring * 0.45 else (2,)
        for k in samples:
            if ((x * 17 + y * 31 + no + k) % (3 if k == 2 else 5)) != 0:
                continue
            z = z_front - max(1, int(round(d * k / 5.0)))
            if z_back < z < z_front:
                put(x, y, z, color, 0.10 + 0.04 * k, priority=3)

    # 5) 接地補強: 下端だけ少し奥行きを太くする。元シルエット範囲しか使わない。
    bottom_y = maxy
    for (x, y), color in pix.items():
        if y >= bottom_y - 1 and ((x + no) % 2) == 0:
            d = min(max_depth, depth_for(x, y) + 4)
            for z in range(max(1, z_front - d), z_front + 1, 2):
                put(x, min(95, y + 1), z, color, 0.18, priority=2)

    # 上限を超えた場合も、前面・背面・外周側面を優先して残す。
    if len(cells) > FIELD3D_MAX_CELLS:
        cells.sort(key=lambda c: (c.get('_p', 9), abs(int(c.get('z', 0)) - z_front)))
        cells = cells[:FIELD3D_MAX_CELLS]

    for c in cells:
        c.pop('_p', None)
    return cells

def hex_color(rgb: Tuple[int, int, int]) -> str:
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in rgb)


def quantize_rgb(rgb: np.ndarray, step: int = 8) -> np.ndarray:
    return (np.round(rgb.astype(np.float32) / step) * step).clip(0, 255).astype(np.uint8)


def foreground_mask(arr: np.ndarray) -> np.ndarray:
    """白背景/薄い方眼/文字をできるだけ除外し、実モンスター色と黒縁を拾う。"""
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = mx - mn

    # 色付き本体。白背景/薄い灰色の方眼は除外する。
    colored = (sat >= 22) & (mx < 250)

    # 黒/濃色アウトライン。灰色方眼の薄い線は拾いにくくする。
    dark_outline = (mx < 115) & ~((sat < 12) & (mx > 70))

    return colored | dark_outline


def likely_background_mask(arr: np.ndarray) -> np.ndarray:
    """
    外周背景として扱う候補を返す。

    重要: 白いピクセルを全部背景にしない。
    ここではあくまで「外周から連結していたら背景にしてよい候補」を作るだけ。
    本体内部の白い目・角・爪・腹などは、後段のborder floodで残す。
    """
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = mx - mn

    # 公式図鑑画像の背景/薄い方眼/薄グレーを背景候補にする。
    # ただし、この時点では候補でしかない。外周連結していない白は残す。
    near_white = (mn >= 232) & (sat <= 34)
    light_gray = (mx >= 214) & (sat <= 18)
    very_light = (mx >= 246) & (sat <= 48)
    return near_white | light_gray | very_light


def border_connected_background(mask: np.ndarray) -> np.ndarray:
    """背景候補maskのうち、画像外周からつながる領域だけを背景として返す。"""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=np.uint8)
    stack: List[Tuple[int, int]] = []

    def push(x: int, y: int) -> None:
        if 0 <= x < w and 0 <= y < h and mask[y, x] and not seen[y, x]:
            seen[y, x] = 1
            stack.append((x, y))

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)

    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            push(nx, ny)

    return seen.astype(bool)


def object_mask_preserve_internal_white(arr: np.ndarray) -> np.ndarray:
    """
    セル出力用の本体mask。
    外周から連結した白/薄灰だけを背景として抜き、内部の白パーツは残す。
    """
    bg = border_connected_background(likely_background_mask(arr))
    mask = ~bg

    # 念のため、色付き/濃色アウトラインは必ず残す。
    # JPG圧縮や背景しきい値の巻き込みで輪郭が消えるのを防ぐ。
    mask |= foreground_mask(arr)
    return mask


def significant_components_bbox(
    mask: np.ndarray,
    min_area: int = 8,
    keep_ratio: float = 0.012,
) -> Tuple[int, int, int, int] | None:
    """
    最大成分だけでなく、一定以上の前景成分をまとめてbbox化する。
    スピアーの羽・針・足のような細い/分離気味パーツを落とさない。
    戻り値は x1,y1,x2,y2。x2/y2 はスライス用に +1 済み。
    """
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=np.uint8)
    components: List[Tuple[int, int, int, int, int]] = []

    ys, xs = np.where(mask)
    for sx, sy in zip(xs.tolist(), ys.tolist()):
        if seen[sy, sx]:
            continue

        stack = [(sx, sy)]
        seen[sy, sx] = 1
        area = 0
        minx = maxx = sx
        miny = maxy = sy

        while stack:
            x, y = stack.pop()
            area += 1
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y

            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= h:
                    continue
                for nx in (x - 1, x, x + 1):
                    if nx < 0 or nx >= w or (nx == x and ny == y):
                        continue
                    if mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = 1
                        stack.append((nx, ny))

        if area >= min_area:
            components.append((area, minx, miny, maxx + 1, maxy + 1))

    if not components:
        return None

    max_area = max(c[0] for c in components)
    threshold = max(min_area, int(max_area * keep_ratio))
    kept = [c for c in components if c[0] >= threshold]
    if not kept:
        kept = [max(components, key=lambda c: c[0])]

    x1 = min(c[1] for c in kept)
    y1 = min(c[2] for c in kept)
    x2 = max(c[3] for c in kept)
    y2 = max(c[4] for c in kept)
    return (x1, y1, x2, y2)


def make_safe_square_crop(
    arr: np.ndarray,
    bbox: Tuple[int, int, int, int],
    safe_pad: float = 0.22,
) -> Tuple[np.ndarray, Dict]:
    """
    元画像内で正方形cropを完結させない。
    本体bboxだけ抜き、新しい白背景の正方形キャンバス中央に安全余白つきで置く。
    これにより、元画像の右端/下端に寄った素材でも右・下の余白が潰れない。
    """
    h, w = arr.shape[:2]
    x1, y1, x2, y2 = bbox

    x1 = max(0, min(w, int(x1)))
    x2 = max(0, min(w, int(x2)))
    y1 = max(0, min(h, int(y1)))
    y2 = max(0, min(h, int(y2)))

    if x2 <= x1 or y2 <= y1:
        raise RuntimeError(f'bad bbox: {bbox}')

    obj = arr[y1:y2, x1:x2]
    oh, ow = obj.shape[:2]

    base_side = max(ow, oh)
    pad = int(math.ceil(base_side * safe_pad))
    side = base_side + pad * 2

    canvas = np.full((side, side, 3), 255, dtype=arr.dtype)
    dx = (side - ow) // 2
    dy = (side - oh) // 2
    canvas[dy:dy + oh, dx:dx + ow] = obj

    meta = {
        'x': int(x1),
        'y': int(y1),
        'w': int(x2 - x1),
        'h': int(y2 - y1),
        'safePadRatio': float(safe_pad),
        'safePadPx': int(pad),
        'canvasSide': int(side),
        'placedX': int(dx),
        'placedY': int(dy),
    }
    return canvas, meta


def dominant_color(px: np.ndarray) -> Tuple[int, int, int]:
    if len(px) == 0:
        return (0, 0, 0)
    q = quantize_rgb(px[:, :3], 8)
    packed = q[:, 0].astype(np.uint32) << 16 | q[:, 1].astype(np.uint32) << 8 | q[:, 2].astype(np.uint32)
    vals, counts = np.unique(packed, return_counts=True)
    p = int(vals[int(np.argmax(counts))])
    return ((p >> 16) & 255, (p >> 8) & 255, p & 255)


def image_to_cells(path: Path, grid: int, safe_pad: float = 0.22) -> Dict:
    im = Image.open(path).convert('RGB')
    arr = np.array(im)

    mask = foreground_mask(arr)
    bbox = significant_components_bbox(mask)
    if bbox is None:
        raise RuntimeError(f'foreground not found: {path}')

    crop, crop_meta = make_safe_square_crop(arr, bbox, safe_pad=safe_pad)
    # セル採用用mask。白を一律に捨てず、外周連結背景だけを透明扱いにする。
    # これで白い目・角・爪・腹/ハイライトを残す。
    crop_mask = object_mask_preserve_internal_white(crop)
    ch, cw = crop.shape[:2]

    cells: List[Dict] = []

    # round連打ではなくlinspace境界で安定分割。
    y_edges = np.linspace(0, ch, grid + 1)
    x_edges = np.linspace(0, cw, grid + 1)

    for gy in range(grid):
        py1 = int(math.floor(y_edges[gy]))
        py2 = int(math.ceil(y_edges[gy + 1]))
        py1 = max(0, min(ch, py1))
        py2 = max(0, min(ch, py2))
        if py2 <= py1:
            continue

        for gx in range(grid):
            px1 = int(math.floor(x_edges[gx]))
            px2 = int(math.ceil(x_edges[gx + 1]))
            px1 = max(0, min(cw, px1))
            px2 = max(0, min(cw, px2))
            if px2 <= px1:
                continue

            m = crop_mask[py1:py2, px1:px2]
            if m.size == 0:
                continue

            # 細い羽・針・足を拾うため、しきい値を旧0.10から0.05へ下げる。
            need = max(1, int(m.size * 0.05))
            if int(m.sum()) < need:
                continue

            pix = crop[py1:py2, px1:px2][m]
            if len(pix) == 0:
                continue

            color = dominant_color(pix)

            # ここで白/薄灰を捨ててはいけない。
            # 背景は crop_mask 側で外周連結背景として除外済み。
            # 本体内部の白い目・角・爪・腹・ハイライトはセルとして残す。
            cells.append({'x': int(gx), 'y': int(gy), 'color': hex_color(color)})

    return {
        'source': str(path).replace('\\', '/'),
        'grid': int(grid),
        'crop': crop_meta,
        'cells': cells,
    }


def build(input_dir: Path, out_file: Path, grid: int, safe_pad: float = 0.22, scale: float | None = None) -> List[Dict]:
    if scale is None:
        # 旧30セル時代の見た目サイズ(30 * 0.085 = 2.55)を維持する。
        # grid=96なら 2.55 / 96 = 0.0265625。
        scale = 2.55 / float(grid)

    files = (
        sorted(input_dir.glob('pokeicon-*.jpg'))
        + sorted(input_dir.glob('pokeicon-*.png'))
        + sorted(input_dir.glob('pokeicon-*.webp'))
    )
    rows = []

    for p in files:
        m = re.search(r'(\d{3})', p.name)
        if not m:
            continue
        no = int(m.group(1))
        if not (1 <= no <= 151):
            continue

        try:
            data = image_to_cells(p, grid, safe_pad=safe_pad)
            name = POKEMON_NAMES_JA[no] if no < len(POKEMON_NAMES_JA) else f'No.{no:03d}'
            field3d_cells = build_pokemon_voxel3d_cells(no, name, data['cells'], grid)
            spec = {'archetype': FIELD3D_GENERATOR_VERSION, 'modelScale': 1.0, 'features': ['real_96x96x96_source_volume', 'no_fake_parts', 'no_16x16_downscale', 'generated_from_cells']}
            rows.append({
                'id': f'info-poke_{no:03d}',
                'type': f'poke_{no:03d}',
                'no': no,
                'name': f'No.{no:03d} {name}',
                'grid': int(grid),
                'scale': float(scale),
                'cells': data['cells'],
                'field3d': {
                    'id': f'info-poke3d_{no:03d}',
                    'type': f'poke_{no:03d}',
                    'name': f'No.{no:03d} {name} 3D',
                    'kind': 'voxel3d',
                    'grid': FIELD3D_GRID,
                    'scale': round(2.55 / float(FIELD3D_GRID), 6),
                    'cells': field3d_cells,
                    'archetype': spec.get('archetype'),
                    'features': spec.get('features', []),
                    'sourceInfoTextureId': f'info-poke_{no:03d}',
                },
                'source': data['source'],
                'crop': data['crop'],
            })
            print(f'OK pokeicon-{no:03d}: grid={grid} cells={len(data["cells"])} field3d={len(field3d_cells)} archetype={spec.get("archetype")} crop={data["crop"]}')
        except Exception as e:
            print(f'NG {p}: {e}')

    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    js = f"""// Auto-generated by tools/build-pokemon-info-textures.py. Do not hand edit.\n// Generator: {FIELD3D_GENERATOR_VERSION}; field3d grid={FIELD3D_GRID}, max_cells={FIELD3D_MAX_CELLS}.\n// Source: assets/pokemon-gen1-icons/pokeicon-###.jpg -> generated cropped dot cells + real 96x96x96 source-volume field3d models. No fake parts.\n// Important: d.cells is the plane info texture. d.field3d is the per-Pokemon individual 3D field model.\n(function(){{\n  const defs = {payload};\n  window.POKEMON_INFO_TEXTURE_DEFS_30 = defs;\n  window.POKEMON_INFO_TEXTURE_DEFS = defs;\n  window.POKEMON_INFO_TEXTURE_FIELD3D_DEFS = defs.map(d=>d.field3d).filter(Boolean);\n  function normalizeHex(c){{ c=String(c||'#22c55e'); if(/^#[0-9a-fA-F]{{6}}$/.test(c)) return c.toLowerCase(); return '#22c55e'; }}\n  function buildField3d(d, plane){{\n    const f=d&&d.field3d; if(!f || !Array.isArray(f.cells) || !f.cells.length) return null;\n    const no=String(d.no||'').padStart(3,'0'); const id=f.id||('info-poke3d_'+no); const type=d.type||('poke_'+no);\n    return {{\n      id, type, infoType:type, name:'情報テクスチャ3D:'+d.name, kind:'voxel3d', grid:Math.max(1,Math.min(128,Math.trunc(Number(f.grid)||96))), scale:Number(f.scale)||Number(d.field3d&&d.field3d.scale)||(2.55/96),\n      cells:f.cells.map(c=>({{x:Math.trunc(Number(c.x)),y:Math.trunc(Number(c.y)),z:Math.trunc(Number(c.z)),color:normalizeHex(c.color),size:Number(c.size)||Number(f.scale)||(2.55/96)}})),\n      infoTexture:false, infoTextureIds:[plane.id], sourceInfoTextureId:plane.id, infoRole:'pokemon', hp:12,\n      infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n      behavior:'96x96元画像シルエットから生成した個別3Dボリュームモデル。16縮小なし。偽耳/偽尻尾などの想像パーツは追加しない。',\n      pokemonIndividual3d:true, pokemon3dArchetype:f.archetype||'', pokemon3dFeatures:f.features||[],\n      createdAt:1, updatedAt:Date.now()\n    }};\n  }}\n  function apply(){{\n    if(!Array.isArray(defs)) return false;\n    const hasMaps = !!(window.customObjectDefs && window.INFO_TEXTURE_META_V3);\n    for(const d of defs){{\n      const id = d.id || ('info-poke_'+String(d.no).padStart(3,'0'));\n      const type = d.type || ('poke_'+String(d.no).padStart(3,'0'));\n      const grid = Number(d.grid || {grid});\n      const plane = {{\n        id, type, infoType:type, name:'情報テクスチャ:'+d.name, kind:'plane', grid:grid, scale:d.scale||{scale},\n        cells:d.cells||[], infoTexture:true, infoRole:'pokemon', hp:12,\n        infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n        behavior:'図鑑ドット絵セル変換済み。野生出現・撃破登録・面貼り付け対象。',\n        field3dId:(d.field3d&&d.field3d.id)||'', pokemonHasIndividual3d:!!(d.field3d&&d.field3d.cells&&d.field3d.cells.length),\n        createdAt:1, updatedAt:Date.now()\n      }};\n      if(window.customObjectDefs){{\n        window.customObjectDefs.set(id, plane);\n        const field3d = buildField3d(d, plane);\n        if(field3d) window.customObjectDefs.set(field3d.id, field3d);\n      }}\n      if(window.INFO_TEXTURE_META_V3){{\n        const meta = window.INFO_TEXTURE_META_V3[id] || window.INFO_TEXTURE_META_V3[type] || {{}};\n        Object.assign(meta, {{id,type,name:d.name,generatedCells:true,generatedCells30:true,iconUrl:'',cells:d.cells,grid:grid,scale:d.scale||{scale},field3d:d.field3d||null,field3dId:(d.field3d&&d.field3d.id)||''}});\n        window.INFO_TEXTURE_META_V3[id] = meta;\n        window.INFO_TEXTURE_META_V3[type] = meta;\n      }}\n    }}\n    try{{ if(window.INFO_TEXTURE_MATERIAL_CACHE_V4) window.INFO_TEXTURE_MATERIAL_CACHE_V4.clear(); }}catch(e){{}}\n    return hasMaps;\n  }}\n  window.applyPokemonGeneratedInfoTextures30 = apply;\n  window.applyPokemonGeneratedInfoTextures = apply;\n  if(!apply()) window.addEventListener('load', apply);\n  setTimeout(apply, 300);\n}})();\n"""
    out_file.write_text(js, encoding='utf-8')
    print(f'WROTE {out_file} entries={len(rows)} grid={grid} safe_pad={safe_pad} scale={scale} white=border_flood_preserve_internal')
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='assets/pokemon-gen1-icons', help='pokeicon-###.jpg folder')
    ap.add_argument('--out', default='generated/pokemon-info-textures.gen1.30x30.generated.js')
    ap.add_argument('--grid', type=int, default=96, help='cell grid resolution. 96 recommended for high-res info texture')
    ap.add_argument('--safe-pad', type=float, default=0.22, help='safe blank margin ratio around detected pokemon body')
    ap.add_argument('--scale', type=float, default=None, help='plane scale written to generated definitions. Default keeps old visual size: 2.55 / grid')
    ap.add_argument('--field3d-grid', type=int, default=96, help='3D voxel coordinate grid. Default 96 means real 96x96x96 output.')
    ap.add_argument('--field3d-max-cells', type=int, default=36000, help='safety cap for 3D cells per Pokemon. Raise if needed for denser models.')
    args = ap.parse_args()

    global FIELD3D_GRID, FIELD3D_MAX_CELLS
    FIELD3D_GRID = max(16, min(128, int(args.field3d_grid)))
    FIELD3D_MAX_CELLS = max(1000, int(args.field3d_max_cells))

    build(Path(args.input), Path(args.out), args.grid, safe_pad=args.safe_pad, scale=args.scale)


if __name__ == '__main__':
    main()
