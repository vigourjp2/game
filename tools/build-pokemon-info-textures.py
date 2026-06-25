#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assets/pokemon-gen1-icons/pokeicon-001.jpg ... を、index-mine.html の平面情報テクスチャで使える
高解像度ドット絵セルデータへ変換する。

狙い:
- 白い余白/薄い方眼罫線を除外
- 最大成分だけでなく、羽・針・足などの分離パーツも拾う
- 元画像内で無理に正方形cropせず、本体を安全余白つき白キャンバス中央へ配置
- 色スポイト相当でセルごとの代表色を取得
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
from typing import Dict, List, Tuple

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
    crop_mask = foreground_mask(crop)
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
            if max(color) > 238 and (max(color) - min(color)) < 24:
                continue

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
            rows.append({
                'id': f'info-poke_{no:03d}',
                'type': f'poke_{no:03d}',
                'no': no,
                'name': f'No.{no:03d} {name}',
                'grid': int(grid),
                'scale': float(scale),
                'cells': data['cells'],
                'source': data['source'],
                'crop': data['crop'],
            })
            print(f'OK pokeicon-{no:03d}: grid={grid} cells={len(data["cells"])} crop={data["crop"]}')
        except Exception as e:
            print(f'NG {p}: {e}')

    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    js = f"""// Auto-generated by tools/build-pokemon-info-textures.py. Do not hand edit.\n// Source: assets/pokemon-gen1-icons/pokeicon-###.jpg -> generated cropped dot cells.\n// Important: the generated grid is stored per definition as d.grid. The filename may remain 30x30 for compatibility.\n(function(){{\n  const defs = {payload};\n  window.POKEMON_INFO_TEXTURE_DEFS_30 = defs;\n  window.POKEMON_INFO_TEXTURE_DEFS = defs;\n  function apply(){{\n    if(!Array.isArray(defs)) return false;\n    const hasMaps = !!(window.customObjectDefs && window.INFO_TEXTURE_META_V3);\n    for(const d of defs){{\n      const id = d.id || ('info-poke_'+String(d.no).padStart(3,'0'));\n      const type = d.type || ('poke_'+String(d.no).padStart(3,'0'));\n      const grid = Number(d.grid || {grid});\n      const plane = {{\n        id, type, infoType:type, name:'情報テクスチャ:'+d.name, kind:'plane', grid:grid, scale:d.scale||{scale},\n        cells:d.cells||[], infoTexture:true, infoRole:'pokemon', hp:12,\n        infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n        behavior:'図鑑ドット絵セル変換済み。野生出現・撃破登録・面貼り付け対象。',\n        createdAt:1, updatedAt:Date.now()\n      }};\n      if(window.customObjectDefs) window.customObjectDefs.set(id, plane);\n      if(window.INFO_TEXTURE_META_V3){{\n        const meta = window.INFO_TEXTURE_META_V3[id] || window.INFO_TEXTURE_META_V3[type] || {{}};\n        Object.assign(meta, {{id,type,name:d.name,generatedCells:true,generatedCells30:true,iconUrl:'',cells:d.cells,grid:grid,scale:d.scale||{scale}}});\n        window.INFO_TEXTURE_META_V3[id] = meta;\n        window.INFO_TEXTURE_META_V3[type] = meta;\n      }}\n    }}\n    try{{ if(window.INFO_TEXTURE_MATERIAL_CACHE_V4) window.INFO_TEXTURE_MATERIAL_CACHE_V4.clear(); }}catch(e){{}}\n    return hasMaps;\n  }}\n  window.applyPokemonGeneratedInfoTextures30 = apply;\n  window.applyPokemonGeneratedInfoTextures = apply;\n  if(!apply()) window.addEventListener('load', apply);\n  setTimeout(apply, 300);\n}})();\n"""
    out_file.write_text(js, encoding='utf-8')
    print(f'WROTE {out_file} entries={len(rows)} grid={grid} safe_pad={safe_pad} scale={scale}')
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='assets/pokemon-gen1-icons', help='pokeicon-###.jpg folder')
    ap.add_argument('--out', default='generated/pokemon-info-textures.gen1.30x30.generated.js')
    ap.add_argument('--grid', type=int, default=96, help='cell grid resolution. 96 recommended for high-res info texture')
    ap.add_argument('--safe-pad', type=float, default=0.22, help='safe blank margin ratio around detected pokemon body')
    ap.add_argument('--scale', type=float, default=None, help='plane scale written to generated definitions. Default keeps old visual size: 2.55 / grid')
    args = ap.parse_args()
    build(Path(args.input), Path(args.out), args.grid, safe_pad=args.safe_pad, scale=args.scale)


if __name__ == '__main__':
    main()
