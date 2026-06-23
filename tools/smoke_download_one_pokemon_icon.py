#!/usr/bin/env python3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from PIL import Image
import json
import sys
import time

OUT_DIR = Path('assets/pokemon-gen1-icons')
GEN_DIR = Path('generated')
OUT_DIR.mkdir(parents=True, exist_ok=True)
GEN_DIR.mkdir(parents=True, exist_ok=True)

URLS = [
    'https://web.archive.org/web/20200829022319im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-1-150x150.jpg',
    'https://web.archive.org/web/20240319000051im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-1-150x150.jpg',
]

headers = {
    'User-Agent': 'Mozilla/5.0 GitHubActions PokemonTextureSmokeTest/1.0',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
}

def download_one(url: str, dest: Path, timeout: int = 60):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        status = getattr(r, 'status', 200)
        ctype = r.headers.get('content-type', '')
        data = r.read()
    if status >= 400:
        raise RuntimeError(f'HTTP status {status}')
    if len(data) < 1000:
        raise RuntimeError(f'too small response: {len(data)} bytes, content-type={ctype}')
    dest.write_bytes(data)
    return {'status': status, 'content_type': ctype, 'bytes': len(data)}

last_error = None
img_path = OUT_DIR / 'pokeicon-001.jpg'
for i, url in enumerate(URLS, 1):
    try:
        print(f'TRY {i}: {url}', flush=True)
        meta = download_one(url, img_path)
        print(f'OK download: {meta}', flush=True)
        break
    except Exception as e:
        last_error = repr(e)
        print(f'NG download from candidate {i}: {last_error}', flush=True)
        time.sleep(2)
else:
    report = {
        'ok': False,
        'target': '001 フシギダネ',
        'errors': last_error,
        'tested_urls': URLS,
    }
    (GEN_DIR / 'pokemon-info-texture-smoke-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SMOKE_TEST_RESULT=NG', flush=True)
    sys.exit(1)

try:
    im = Image.open(img_path).convert('RGBA')
    original_size = im.size
    im30 = im.resize((30, 30), Image.Resampling.NEAREST)
    cells = []
    for y in range(30):
        row = []
        for x in range(30):
            r, g, b, a = im30.getpixel((x, y))
            row.append('#%02x%02x%02x%02x' % (r, g, b, a))
        cells.append(row)
    report = {
        'ok': True,
        'target': '001 フシギダネ',
        'downloaded_file': str(img_path),
        'original_size': original_size,
        'converted_size': [30, 30],
        'source_url': url,
        'download_meta': meta,
        'sample_top_left': cells[0][0],
        'sample_center': cells[15][15],
    }
    (GEN_DIR / 'pokemon-info-texture-smoke-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    js = 'window.POKEMON_INFO_TEXTURE_SMOKE_TEST = ' + json.dumps(report, ensure_ascii=False, indent=2) + ';\n'
    (GEN_DIR / 'pokemon-info-texture-smoke-test.js').write_text(js, encoding='utf-8')
    print('OK convert 30x30', flush=True)
    print('SMOKE_TEST_RESULT=OK', flush=True)
except Exception as e:
    print(f'NG convert: {e!r}', flush=True)
    sys.exit(1)
