#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full 151 Pokemon info texture builder, based on the confirmed 001 smoke-test path.
Downloads/caches 150x150 jpg icons, converts each to max 30x30 cell color data,
and writes files for index-mine.html loader.
"""
from __future__ import annotations
from pathlib import Path
from urllib.request import Request, urlopen
from PIL import Image
from collections import Counter
import json, sys, time, socket

socket.setdefaulttimeout(90)
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "pokemon-gen1-icons"
GEN_DIR = ROOT / "generated"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
GEN_DIR.mkdir(parents=True, exist_ok=True)

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

URLS = [
    "https://web.archive.org/web/20200829022319im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-{n}-150x150.jpg",
    "https://web.archive.org/web/20240319000051im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-{n}-150x150.jpg",
]
HEADERS = {
    "User-Agent":"Mozilla/5.0 GitHubActions PokemonInfoTextureFull151/1.0",
    "Accept":"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Connection":"close",
}

def download(n:int) -> tuple[Path,str]:
    out = ASSET_DIR / f"pokeicon-{n:03d}.jpg"
    if out.exists() and out.stat().st_size > 1000:
        return out, "cached"
    last = None
    for attempt in range(1, 5):
        for tmpl in URLS:
            url = tmpl.format(n=n)
            try:
                print(f"DL {n:03d} attempt={attempt} url={url}", flush=True)
                req = Request(url, headers=HEADERS)
                with urlopen(req, timeout=90) as r:
                    data = r.read()
                    ctype = r.headers.get("content-type", "")
                if len(data) < 1000:
                    raise RuntimeError(f"too small: {len(data)} bytes content-type={ctype}")
                out.write_bytes(data)
                return out, url
            except Exception as e:
                last = e
                print(f"NG {n:03d}: {e!r}", file=sys.stderr, flush=True)
                time.sleep(3 * attempt)
    raise RuntimeError(f"download failed #{n:03d}: {last!r}")

def is_bg(r,g,b,a):
    if a < 16: return True
    if r >= 235 and g >= 235 and b >= 235: return True
    if abs(r-g) <= 8 and abs(g-b) <= 8 and r >= 170: return True
    return False

def qhex(rgb):
    r,g,b = rgb
    q = lambda v: int(round(v/8)*8) if v < 248 else 255
    return f"#{q(r):02x}{q(g):02x}{q(b):02x}"

def extract_cells(path:Path, grid:int=30):
    img = Image.open(path).convert("RGBA")
    if img.size != (150, 150):
        img = img.resize((150,150), Image.Resampling.NEAREST)
    cells = []
    step = 150 / grid
    for y in range(grid):
        for x in range(grid):
            x0, x1 = int(round(x*step)), int(round((x+1)*step))
            y0, y1 = int(round(y*step)), int(round((y+1)*step))
            pix=[]
            for py in range(y0, y1):
                for px in range(x0, x1):
                    r,g,b,a = img.getpixel((min(px,149), min(py,149)))
                    if not is_bg(r,g,b,a):
                        pix.append((r,g,b))
            if pix:
                color = Counter(qhex(p) for p in pix).most_common(1)[0][0]
                cells.append({"x":x,"y":y,"color":color})
    return cells

def main():
    defs=[]
    failures=[]
    for n,name in enumerate(NAMES,1):
        try:
            path, src = download(n)
            cells = extract_cells(path, 30)
            if not cells:
                raise RuntimeError("no colored cells extracted")
            defs.append({
                "id": f"info-pokemon-{n:03d}",
                "no": n,
                "name": f"情報テクスチャ:{n:03d} {name}",
                "kind": "plane",
                "grid": 30,
                "cells": cells,
                "infoTexture": True,
                "infoType": f"pokemon-{n:03d}",
                "infoRole": "pokemon-gen1",
                "infoBehavior": f"第1世代ポケモン手持ちアイコン由来の30×30情報テクスチャ: {name}",
                "sourceUrl": URLS[0].format(n=n),
            })
            print(f"OK {n:03d} {name}: {len(cells)} cells src={src}", flush=True)
        except Exception as e:
            failures.append({"no":n,"name":name,"error":str(e)})
            print(f"FAIL {n:03d} {name}: {e}", file=sys.stderr, flush=True)
    payload = {"ok": len(defs)==151, "grid":30, "count":len(defs), "failures":failures, "defs":defs}
    (GEN_DIR / "pokemon-info-textures.gen1.30x30.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    (GEN_DIR / "pokemon-info-textures.gen1.30x30.generated.js").write_text(
        "/* Generated from 150x150 source icons, max 30x30 cells */\n" +
        "window.POKEMON_INFO_TEXTURE_DEFS_30 = " + json.dumps(defs, ensure_ascii=False, separators=(",",":")) + ";\n",
        encoding="utf-8"
    )
    print(f"FULL151_RESULT count={len(defs)} failures={len(failures)}", flush=True)
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
