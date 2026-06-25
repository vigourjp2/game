#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download Pokemon Gen1 images from official Pokemon Zukan detail pages and convert
each image into 30x30 grid cell colors for index-mine.html information plane textures.

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
from urllib.parse import urljoin
from html import unescape

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

DETAIL_URL_PATTERN = "https://zukan.pokemon.co.jp/detail/{n:04d}"

# Common UI/social assets are also present in the detail page. Exclude those so the
# extractor picks the Pokemon art, not the site logo/search buttons/SNS icons.
REJECT_IMAGE_WORDS = (
    "logo", "header", "footer", "sns", "twitter", "facebook", "line",
    "search", "sort", "arrow", "pagetop", "close", "btn", "icon_type",
    "loading", "spinner", "blank", "common", "sprite", "parts",
)

IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|webp)(?:[?#][^\s\"'<>)]*)?$", re.I)


def url_for(n: int) -> str:
    """Detail page URL, e.g. https://zukan.pokemon.co.jp/detail/0001."""
    return DETAIL_URL_PATTERN.format(n=n)


def fetch_bytes(url: str, *, accept: str = "*/*") -> tuple[bytes, str]:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Pokemon texture-builder",
            "Accept": accept,
            "Referer": "https://zukan.pokemon.co.jp/",
        },
    )
    with urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "")


def fetch_text(url: str) -> str:
    data, _ = fetch_bytes(url, accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    return data.decode("utf-8", "ignore")


def normalize_url(raw: str, base_url: str) -> str | None:
    raw = unescape(raw or "").strip().strip('"\'')
    if not raw or raw.startswith(("data:", "javascript:", "mailto:")):
        return None
    raw = raw.replace("\\/", "/")
    return urljoin(base_url, raw)


def add_candidate(candidates: list[str], seen: set[str], raw: str, base_url: str) -> None:
    url = normalize_url(raw, base_url)
    if not url:
        return
    if not IMAGE_EXT_RE.search(url):
        return
    low = url.lower()
    if any(word in low for word in REJECT_IMAGE_WORDS):
        return
    if url not in seen:
        seen.add(url)
        candidates.append(url)




def walk_json_for_images(obj, page_url: str, candidates: list[str], seen: set[str]) -> None:
    """Collect image URLs from parsed json-data, preserving priority/order."""
    if isinstance(obj, dict):
        # On the official Zukan detail page, the current Pokemon is under
        # json-data.pokemon. Prefer the large/medium/small fields in that order.
        for key in ("image_l", "image_m", "image_s", "img", "image", "url"):
            value = obj.get(key)
            if isinstance(value, str):
                add_candidate(candidates, seen, value, page_url)
        for value in obj.values():
            walk_json_for_images(value, page_url, candidates, seen)
    elif isinstance(obj, list):
        for value in obj:
            walk_json_for_images(value, page_url, candidates, seen)

def extract_image_urls(html: str, page_url: str) -> list[str]:
    """Extract likely Pokemon image URLs from the official Zukan detail page."""
    candidates: list[str] = []
    seen: set[str] = set()
    doc = unescape(html).replace("\\/", "/")

    # Official Zukan detail pages expose the main data in
    # <script id="json-data" type="application/json">. Pull that first so
    # current Pokemon images beat evolution/news/social images.
    script_re = re.compile(
        r"<script[^>]+id=[\"']json-data[\"'][^>]*>(.*?)</script>",
        re.I | re.S,
    )
    for m in script_re.finditer(doc):
        raw_json = m.group(1).strip()
        try:
            data = json.loads(raw_json)
            pokemon = data.get("pokemon") if isinstance(data, dict) else None
            if isinstance(pokemon, dict):
                for key in ("image_l", "image_m", "image_s"):
                    value = pokemon.get(key)
                    if isinstance(value, str):
                        add_candidate(candidates, seen, value, page_url)
            walk_json_for_images(data, page_url, candidates, seen)
        except Exception:
            # Fall through to regex extraction below.
            pass

    # Prefer OGP/Twitter card images if present.
    meta_re = re.compile(
        r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    )
    for m in meta_re.finditer(doc):
        add_candidate(candidates, seen, m.group(1), page_url)

    # img/source attributes and lazy-load variants.
    attr_re = re.compile(
        r"(?:src|data-src|data-original|data-lazy|data-image|content)=[\"']([^\"']+)[\"']",
        re.I,
    )
    for m in attr_re.finditer(doc):
        value = m.group(1)
        # srcset may contain multiple URLs with widths.
        for part in value.split(","):
            add_candidate(candidates, seen, part.strip().split(" ")[0], page_url)

    srcset_re = re.compile(r"srcset=[\"']([^\"']+)[\"']", re.I)
    for m in srcset_re.finditer(doc):
        for part in m.group(1).split(","):
            add_candidate(candidates, seen, part.strip().split(" ")[0], page_url)

    # CSS url(...) and JSON/string embedded image paths.
    for m in re.finditer(r"url\(([^)]+)\)", doc, re.I):
        add_candidate(candidates, seen, m.group(1), page_url)
    for m in re.finditer(r"https?://[^\"'<> )]+\.(?:png|jpe?g|webp)(?:[?#][^\"'<> )]+)?", doc, re.I):
        add_candidate(candidates, seen, m.group(0), page_url)
    for m in re.finditer(r"/[A-Za-z0-9_./%~@-]+\.(?:png|jpe?g|webp)(?:[?#][^\"'<> )]+)?", doc, re.I):
        add_candidate(candidates, seen, m.group(0), page_url)

    return candidates


def score_image_candidate(url: str, n: int) -> int:
    low = url.lower()
    no3 = f"{n:03d}"
    no4 = f"{n:04d}"
    score = 0
    if no4 in low:
        score += 120
    if no3 in low:
        score += 40
    if "pokemon" in low or "zukan" in low or "pm" in low:
        score += 30
    if "detail" in low or "main" in low or "image" in low or "img" in low:
        score += 20
    if low.endswith(".png") or ".png?" in low:
        score += 10
    return score


def save_as_jpeg(data: bytes, out: Path) -> None:
    img = Image.open(BytesIO(data)).convert("RGBA")
    # Official art may have transparency. Composite on white so the existing
    # background/grid filtering still behaves predictably.
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    bg.convert("RGB").save(out, "JPEG", quality=95)


def download(n: int) -> tuple[Path, str]:
    out = ASSET_DIR / f"pokeicon-{n:03d}.jpg"
    page_url = url_for(n)
    if out.exists() and out.stat().st_size > 1000:
        return out, page_url

    last = None
    try:
        html = fetch_text(page_url)
        candidates = extract_image_urls(html, page_url)
        candidates.sort(key=lambda u: score_image_candidate(u, n), reverse=True)
        if not candidates:
            raise RuntimeError("no candidate image URL found in detail page")

        for img_url in candidates:
            try:
                data, ctype = fetch_bytes(img_url, accept="image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")
                if len(data) < 1000:
                    raise RuntimeError(f"too small: {len(data)} bytes")
                if "svg" in ctype.lower() or data.lstrip().startswith(b"<svg"):
                    raise RuntimeError("svg image is not supported by Pillow")
                save_as_jpeg(data, out)
                return out, img_url
            except Exception as e:
                last = e
                time.sleep(0.25)
    except Exception as e:
        last = e

    raise RuntimeError(f"download failed #{n:03d} from {page_url}: {last}")

def is_grid_or_bg(r,g,b,a=255):
    # Official artwork may contain white/very-light backing, and old generated assets may contain gray grid lines.
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
            path, source_image_url = download(n)
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
                "sourceImageUrl": source_image_url,
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
