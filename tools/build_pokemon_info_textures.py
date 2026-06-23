#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download archived Pokemon Gen1 hand-held icons and convert each 150x150 image into
30x30 grid cell colors for index-mine.html information plane textures.

Output:
  generated/pokemon-info-textures.gen1.30x30.generated.js
  generated/pokemon-info-textures.gen1.30x30.json
  assets/pokemon-gen1-icons/pokeicon-001.jpg ... pokeicon-151.jpg
"""
from __future__ import annotations
import json, os, re, sys, time
from collections import Counter
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

try:
    from PIL import Image
except Exception:
    print("Pillow is required: pip install pillow", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "pokemon-gen1-icons"
OUT_DIR = ROOT / "generated"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

NAMES = [
"フシギダネ","フシギソウ","フシギバナ","ヒトカゲ","リザード","リザードン","ゼニガメ","カメール","カメックス","キャタピー",
"トランセル","バタフリー","ビードル","コクーン","スピアー","ポッポ","ピジョン","ピジョット","コラッタ","ラッタ",
"オニスズメ","オニドリル","アーボ","アーボック","ピカチュウ","ライチュウ","サンド","サンドパン","ニドラン♀","ニドリーナ",
"ニドクイン","ニドラン♂","ニドリーノ","ニドキング","ピッピ","ピクシー","ロコン","キュウコン","プリン","プクリン",
"ズバット","ゴルバット","ナゾノクサ","クサイハナ","ラフレシア","パラス","パラセクト","コンパン","モルフォン","ディグダ",
"ダグトリオ","ニャース","ペルシアン","コダック","ゴルダック","マンキー","オコリザル","ガーディ","ウインディ","ニョロモ",
"ニョロゾ","ニョロボン","ケーシィ","ユンゲラー","フーディン","ワンリキー","ゴーリキー","カイリキー","マダツボミ","ウツドン",
"ウツボット","メノクラゲ","ドククラゲ","イシツブテ","ゴローン","ゴローニャ","ポニータ","ギャロップ","ヤドン","ヤドラン",
"コイル","レアコイル","カモネギ","ドードー","ドードリオ","パウワウ","ジュゴン","ベトベター","ベトベトン","シェルダー",
"パルシェン","ゴース","ゴースト","ゲンガー","イワーク","スリープ","スリーパー","クラブ","キングラー","ビリリダマ",
"マルマイン","タマタマ","ナッシー","カラカラ","ガラガラ","サワムラー","エビワラー","ベロリンガ","ドガース","マタドガス",
"サイホーン","サイドン","ラッキー","モンジャラ","ガルーラ","タッツー","シードラ","トサキント","アズマオウ","ヒトデマン",
"スターミー","バリヤード","ストライク","ルージュラ","エレブー","ブーバー","カイロス","ケンタロス","コイキング","ギャラドス",
"ラプラス","メタモン","イーブイ","シャワーズ","サンダース","ブースター","ポリゴン","オムナイト","オムスター","カブト",
"カブトプス","プテラ","カビゴン","フリーザー","サンダー","ファイヤー","ミニリュウ","ハクリュー","カイリュー","ミュウツー","ミュウ"
]

URL_PATTERNS = [
    "https://web.archive.org/web/20240319000051im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-{n}-150x150.jpg",
    "https://web.archive.org/web/20200829022319im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-{n}-150x150.jpg",
]

def url_for(n: int) -> str:
    return URL_PATTERNS[0].format(n=n)

def download(n: int) -> Path:
    out = ASSET_DIR / f"pokeicon-{n:03d}.jpg"
    if out.exists() and out.stat().st_size > 1000:
        return out
    last = None
    for pat in URL_PATTERNS:
        url = pat.format(n=n)
        try:
            req = Request(url, headers={"User-Agent":"Mozilla/5.0 texture-builder"})
            with urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) < 1000:
                raise RuntimeError(f"too small: {len(data)} bytes")
            out.write_bytes(data)
            return out
        except Exception as e:
            last = e
            time.sleep(0.25)
    raise RuntimeError(f"download failed #{n:03d}: {last}")

def is_grid_or_bg(r,g,b,a=255):
    # Archive/icon page images contain white/very-light backing and gray grid lines.
    if a < 16:
        return True
    # very light background
    if r >= 235 and g >= 235 and b >= 235:
        return True
    # gray grid lines, low saturation and light
    if abs(r-g) <= 8 and abs(g-b) <= 8 and r >= 170:
        return True
    return False

def quant_hex(rgb):
    r,g,b = rgb
    # mild quantization removes JPEG noise while preserving source colors.
    q = lambda v: int(round(v/8)*8) if v < 248 else 255
    return f"#{q(r):02x}{q(g):02x}{q(b):02x}"

def analyze_image(path: Path, grid: int = 30):
    img = Image.open(path).convert("RGBA")
    # The source icon is 150x150. Resize/crop only if a mirror returns a different dimension.
    if img.size != (150,150):
        img = img.resize((150,150), Image.Resampling.NEAREST)
    w,h = img.size
    cell_w = w / grid
    cell_h = h / grid
    cells = []
    for y in range(grid):
        for x in range(grid):
            x0, x1 = int(round(x*cell_w)), int(round((x+1)*cell_w))
            y0, y1 = int(round(y*cell_h)), int(round((y+1)*cell_h))
            pix = []
            for py in range(y0, y1):
                for px in range(x0, x1):
                    r,g,b,a = img.getpixel((min(px,w-1), min(py,h-1)))
                    if not is_grid_or_bg(r,g,b,a):
                        pix.append((r,g,b))
            if not pix:
                continue
            # dominant quantized color in the 5x5 cell.
            hexcol, count = Counter(quant_hex(p) for p in pix).most_common(1)[0]
            # Ignore a cell if almost all surviving pixels are tiny JPG dirt.
            if len(pix) >= 2:
                cells.append({"x":x,"y":y,"color":hexcol})
    return cells

def main():
    defs = []
    failures = []
    for n, name in enumerate(NAMES, 1):
        try:
            path = download(n)
            cells = analyze_image(path, 30)
            if not cells:
                raise RuntimeError("no colored cells extracted")
            defs.append({
                "id": f"info-pokemon-{n:03d}",
                "no": n,
                "name": f"情報テクスチャ:{n:03d} {name}",
                "kind": "plane",
                "grid": 30,
                "scale": 0.045,
                "cells": cells,
                "infoTexture": True,
                "infoType": f"pokemon-{n:03d}",
                "infoRole": "pokemon-gen1",
                "infoBehavior": f"第1世代ポケモン手持ちアイコン由来の30×30情報テクスチャ: {name}",
                "infoPhysics": {"massKg": 1, "gravityScale": 1, "terminalVelocity": 18, "bounce": 0},
                "hp": 8,
                "sourceUrl": url_for(n),
                "createdAt": 1,
                "updatedAt": 1
            })
            print(f"OK {n:03d} {name}: {len(cells)} cells")
        except Exception as e:
            failures.append({"no": n, "name": name, "error": str(e)})
            print(f"NG {n:03d} {name}: {e}", file=sys.stderr)
    payload = {"grid":30, "count":len(defs), "defs":defs, "failures":failures}
    (OUT_DIR / "pokemon-info-textures.gen1.30x30.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    js = "/* Generated by tools/build_pokemon_info_textures.py */\n" \
         "window.POKEMON_INFO_TEXTURE_DEFS_30 = " + json.dumps(defs, ensure_ascii=False, separators=(",",":")) + ";\n"
    (OUT_DIR / "pokemon-info-textures.gen1.30x30.generated.js").write_text(js, encoding="utf-8")
    print(f"Wrote {len(defs)} definitions, failures={len(failures)}")
    if failures:
        sys.exit(2)

if __name__ == "__main__":
    main()
