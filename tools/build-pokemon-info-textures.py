#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assets/pokemon-gen1-icons/pokeicon-001.jpg ... を、index-mine.html の平面情報テクスチャで使える
30x30ドット絵セルデータへ変換する。

狙い:
- 白い余白/薄い方眼罫線を除外
- モンスターの描画領域だけを正方形でトリミング
- 色スポイト相当でセルごとの代表色を取得
- generated/pokemon-info-textures.gen1.30x30.generated.js に出力

使い方:
  python tools/build-pokemon-info-textures.py
  python tools/build-pokemon-info-textures.py --grid 30 --input assets/pokemon-gen1-icons --out generated/pokemon-info-textures.gen1.30x30.generated.js
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
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = mx - mn
    # 白背景/薄い灰色の方眼は除外。色付きセルと黒縁は残す。
    colored = (sat >= 22) & (mx < 250)
    dark_outline = (mx < 115) & ~((sat < 12) & (mx > 70))
    mask = colored | dark_outline
    # 画面下の小さい注釈文字や上部UIが混じる素材用に、小面積ノイズは後段のbboxで自然に落とす。
    return mask


def largest_component_bbox(mask: np.ndarray) -> Tuple[int, int, int, int] | None:
    """numpyだけで8近傍ラベル。最大成分のbboxを返す。"""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=np.uint8)
    best = None
    best_area = 0
    ys, xs = np.where(mask)
    pts = set(zip(xs.tolist(), ys.tolist()))
    for sx, sy in list(pts):
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
            for ny in (y-1, y, y+1):
                if ny < 0 or ny >= h: continue
                for nx in (x-1, x, x+1):
                    if nx < 0 or nx >= w or (nx == x and ny == y): continue
                    if mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = 1
                        stack.append((nx, ny))
        if area > best_area:
            best_area = area
            best = (minx, miny, maxx + 1, maxy + 1)
    return best


def square_bbox(bbox: Tuple[int, int, int, int], w: int, h: int, pad_ratio: float = 0.10) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    side = int(math.ceil(max(bw, bh) * (1.0 + pad_ratio * 2)))
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    x1 = int(round(cx - side / 2)); y1 = int(round(cy - side / 2))
    x2 = x1 + side; y2 = y1 + side
    if x1 < 0: x2 -= x1; x1 = 0
    if y1 < 0: y2 -= y1; y1 = 0
    if x2 > w: x1 -= (x2 - w); x2 = w
    if y2 > h: y1 -= (y2 - h); y2 = h
    x1 = max(0, x1); y1 = max(0, y1); x2 = min(w, x2); y2 = min(h, y2)
    return (x1, y1, x2, y2)


def dominant_color(px: np.ndarray) -> Tuple[int, int, int]:
    if len(px) == 0:
        return (0, 0, 0)
    q = quantize_rgb(px[:, :3], 8)
    packed = q[:, 0].astype(np.uint32) << 16 | q[:, 1].astype(np.uint32) << 8 | q[:, 2].astype(np.uint32)
    vals, counts = np.unique(packed, return_counts=True)
    p = int(vals[int(np.argmax(counts))])
    return ((p >> 16) & 255, (p >> 8) & 255, p & 255)


def image_to_cells(path: Path, grid: int) -> Dict:
    im = Image.open(path).convert('RGB')
    arr = np.array(im)
    mask = foreground_mask(arr)
    bbox = largest_component_bbox(mask)
    if bbox is None:
        raise RuntimeError(f'foreground not found: {path}')
    x1, y1, x2, y2 = square_bbox(bbox, arr.shape[1], arr.shape[0], 0.10)
    crop = arr[y1:y2, x1:x2]
    crop_mask = foreground_mask(crop)
    ch, cw = crop.shape[:2]
    cells: List[Dict] = []
    for gy in range(grid):
        py1 = int(round(gy * ch / grid)); py2 = int(round((gy + 1) * ch / grid))
        for gx in range(grid):
            px1 = int(round(gx * cw / grid)); px2 = int(round((gx + 1) * cw / grid))
            m = crop_mask[py1:py2, px1:px2]
            if m.size == 0:
                continue
            # セルの中に前景が少しでもあれば採用。細い黒縁が消えないよう低め。
            if int(m.sum()) < max(1, int(m.size * 0.10)):
                continue
            pix = crop[py1:py2, px1:px2][m]
            color = dominant_color(pix)
            # ほぼ白/薄灰は最後の保険で捨てる
            if max(color) > 238 and (max(color) - min(color)) < 24:
                continue
            cells.append({'x': gx, 'y': gy, 'color': hex_color(color)})
    return {
        'source': str(path).replace('\\', '/'),
        'grid': grid,
        'crop': {'x': x1, 'y': y1, 'w': x2 - x1, 'h': y2 - y1},
        'cells': cells,
    }


def build(input_dir: Path, out_file: Path, grid: int) -> List[Dict]:
    files = sorted(input_dir.glob('pokeicon-*.jpg')) + sorted(input_dir.glob('pokeicon-*.png')) + sorted(input_dir.glob('pokeicon-*.webp'))
    rows = []
    for p in files:
        m = re.search(r'(\d{3})', p.name)
        if not m:
            continue
        no = int(m.group(1))
        if not (1 <= no <= 151):
            continue
        try:
            data = image_to_cells(p, grid)
            name = POKEMON_NAMES_JA[no] if no < len(POKEMON_NAMES_JA) else f'No.{no:03d}'
            rows.append({
                'id': f'info-poke_{no:03d}',
                'type': f'poke_{no:03d}',
                'no': no,
                'name': f'No.{no:03d} {name}',
                'grid': grid,
                'scale': 0.085,
                'cells': data['cells'],
                'source': data['source'],
                'crop': data['crop'],
            })
            print(f'OK pokeicon-{no:03d}: cells={len(data["cells"])} crop={data["crop"]}')
        except Exception as e:
            print(f'NG {p}: {e}')
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    js = f"""// Auto-generated by tools/build-pokemon-info-textures.py. Do not hand edit.\n// Source: assets/pokemon-gen1-icons/pokeicon-###.jpg -> 30x30 cropped dot cells.\n(function(){{\n  const defs = {payload};\n  window.POKEMON_INFO_TEXTURE_DEFS_30 = defs;\n  function apply(){{\n    if(!Array.isArray(defs)) return false;\n    const hasMaps = !!(window.customObjectDefs && window.INFO_TEXTURE_META_V3);\n    for(const d of defs){{\n      const id = d.id || ('info-poke_'+String(d.no).padStart(3,'0'));\n      const type = d.type || ('poke_'+String(d.no).padStart(3,'0'));\n      const plane = {{\n        id, type, infoType:type, name:'情報テクスチャ:'+d.name, kind:'plane', grid:d.grid||30, scale:d.scale||0.085,\n        cells:d.cells||[], infoTexture:true, infoRole:'pokemon', hp:12,\n        infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n        behavior:'図鑑ドット絵セル変換済み。野生出現・撃破登録・面貼り付け対象。',\n        createdAt:1, updatedAt:Date.now()\n      }};\n      if(window.customObjectDefs) window.customObjectDefs.set(id, plane);\n      if(window.INFO_TEXTURE_META_V3){{\n        const meta = window.INFO_TEXTURE_META_V3[id] || window.INFO_TEXTURE_META_V3[type] || {{}};\n        Object.assign(meta, {{id,type,name:d.name,generatedCells30:true,iconUrl:'',cells:d.cells,grid:d.grid||30}});\n        window.INFO_TEXTURE_META_V3[id] = meta;\n        window.INFO_TEXTURE_META_V3[type] = meta;\n      }}\n    }}\n    try{{ if(window.INFO_TEXTURE_MATERIAL_CACHE_V4) window.INFO_TEXTURE_MATERIAL_CACHE_V4.clear(); }}catch(e){{}}\n    return hasMaps;\n  }}\n  window.applyPokemonGeneratedInfoTextures30 = apply;\n  if(!apply()) window.addEventListener('load', apply);\n  setTimeout(apply, 300);\n}})();\n"""
    out_file.write_text(js, encoding='utf-8')
    print(f'WROTE {out_file} entries={len(rows)}')
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='assets/pokemon-gen1-icons', help='pokeicon-###.jpg folder')
    ap.add_argument('--out', default='generated/pokemon-info-textures.gen1.30x30.generated.js')
    ap.add_argument('--grid', type=int, default=30)
    args = ap.parse_args()
    build(Path(args.input), Path(args.out), args.grid)

if __name__ == '__main__':
    main()
