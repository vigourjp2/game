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
# Gen1 Pokemon individual nanoblock-style 3D model generator
# -----------------------------------------------------------------------------
# 151体をテンプレ1個に逃がさず、No.ごとの個別スペックを持たせる。
# 形状は個別スペック、色は各pokeicon画像から抽出した2Dセル色を使う。
MODEL_SPECS_RAW = """
001|quad|0.88|bulb,ears,spots,short_tail
002|quad|1.04|big_bulb,ears,spots,claws
003|quad|1.24|flower,ears,spots,claws,wide_body
004|biped|0.82|flame_tail,claws,small_head
005|biped|1.00|flame_tail,claws,horn_head
006|dragon|1.30|wings,flame_tail,horns,claws,long_neck
007|biped|0.78|shell_back,round_head,short_tail
008|biped|0.96|shell_back,tail,ears
009|turtle|1.18|cannons,shell_back,tail,claws
010|worm|0.62|segments,antenna,feet
011|cocoon|0.72|shell,eyes
012|butterfly|0.95|large_wings,antenna,thin_body
013|worm|0.56|segments,horn_tail,feet
014|cocoon|0.76|shell,spikes,eyes
015|insect|1.02|large_wings,stingers,arms,legs
016|bird|0.70|wings,beak,tail_feathers
017|bird|0.92|wings,crest,tail_feathers
018|bird|1.16|large_wings,crest,long_tail
019|quad|0.58|big_ears,whiskers,tail
020|quad|0.82|big_teeth,whiskers,tail,large_body
021|bird|0.70|wings,beak,tail_feathers,crest
022|bird|1.10|large_wings,long_beak,crest,long_tail
023|serpent|0.82|snake_body,tongue,tail_rattle
024|serpent|1.04|cobra_hood,tongue,marking
025|biped|0.74|long_ears,tail_bolt,cheeks
026|biped|0.96|long_ears,tail_bolt,cheeks,big_feet
027|biped|0.72|claws,spines,round_body
028|biped|0.98|claws,spines,slasher_arms
029|quad|0.66|ears,horn_head,spots,small_body
030|quad|0.86|ears,horn_head,spots,claws
031|kaiju|1.16|horn_head,ears,spikes,tail,wide_body
032|quad|0.66|ears,horn_head,spikes,small_body
033|quad|0.86|ears,horn_head,spikes,claws
034|kaiju|1.18|horn_head,ears,spikes,tail,wide_body
035|biped|0.72|round_body,ears,small_wings
036|biped|0.95|round_body,ears,small_wings,tail
037|quad|0.72|many_tails,ears,fox_body
038|quad|1.02|many_tails,ears,fox_body,mane
039|balloon|0.64|round_body,ears,curl
040|balloon|0.88|round_body,ears,curl,big_arms
041|bat|0.66|wings,big_mouth,ears
042|bat|0.96|large_wings,big_mouth,ears,feet
043|plant|0.58|leaf_head,feet,round_body
044|plant|0.78|leaf_head,drool,feet
045|plant|0.96|flower,petals,feet,round_body
046|insect|0.70|mushroom_back,claws,legs
047|insect|0.94|big_mushroom,claws,legs
048|insect|0.76|antenna,big_eyes,legs
049|moth|0.96|large_wings,antenna,thin_body
050|mole|0.55|head_only,nose
051|mole_trio|0.80|triple_heads,noses
052|quad|0.68|cat_ears,whiskers,tail,coin
053|quad|0.94|cat_ears,whiskers,tail,slender
054|duck|0.72|bill,tail,web_feet,round_body
055|duck|0.96|bill,web_feet,arms,spikes
056|biped|0.72|monkey_tail,arms,feet
057|biped|0.96|monkey_tail,boxing_arms,angry_brow
058|quad|0.80|dog_mane,tail,ears
059|quad|1.16|dog_mane,big_tail,ears,large_body
060|balloon|0.62|swirl_belly,tail,feet
061|biped|0.82|swirl_belly,arms,feet
062|biped|1.02|swirl_belly,boxing_arms,feet
063|biped|0.66|fox_head,tail,spoon
064|biped|0.90|fox_head,tail,spoon,ears
065|biped|1.06|fox_head,tail,two_spoons,mustache
066|biped|0.76|muscle_arms,feet
067|biped|0.98|muscle_arms,belt,feet
068|biped|1.15|four_arms,belt,feet
069|plant|0.72|vine_body,leaf_head,feet
070|plant|0.90|bell_head,vine_body,leaf_arms
071|plant|1.06|big_mouth,leaf_arms,vine_body
072|jellyfish|0.70|tentacles,head_orb
073|jellyfish|1.02|many_tentacles,head_orb,spikes
074|rock|0.66|rock_ball,arms
075|rock|0.88|rock_ball,arms,chunky
076|rock|1.12|rock_ball,arms,legs,chunky
077|quad|0.86|horse_body,mane,tail_flame
078|quad|1.10|horse_body,mane,tail_flame,horn_head
079|quad|0.82|hippo_body,tail,round_head
080|quad|1.02|hippo_body,shell_tail,round_head
081|magnet|0.58|magnet_sides,screw,eye
082|magnet|0.90|triple_magnets,screws,eyes
083|bird|0.80|leek,beak,wings,tail_feathers
084|bird|0.80|two_heads,legs,tail_feathers
085|bird|1.05|three_heads,legs,tail_feathers
086|seal|0.78|seal_body,tail,flippers,horn_head
087|seal|1.02|seal_body,tail,flippers,horn_head
088|slime|0.78|blob_body,arms,drip
089|slime|1.04|blob_body,arms,drip,wide_body
090|shell|0.66|shell_body,tongue,spikes
091|shell|0.96|shell_body,spikes,horn_head
092|ghost|0.68|gas_cloud,face
093|ghost|0.90|gas_cloud,hands,face
094|ghost|1.05|spiky_ghost,arms,face
095|serpent|1.18|rock_segments,horn_head,long_body
096|biped|0.78|tapir_head,pendulum,ears
097|biped|1.00|tapir_head,pendulum,collar
098|crab|0.76|claws,legs,shell_body
099|crab|1.00|big_claws,legs,shell_body,spikes
100|ball|0.62|sphere,face_band
101|ball|0.82|sphere,face_band,inverted
102|plant_cluster|0.70|six_eggs,faces
103|palm|1.08|triple_heads,palm_leaves,legs
104|biped|0.72|skull_head,bone_club,tail
105|biped|0.92|skull_head,bone_club,spikes
106|biped|0.96|long_legs,kicking_pose
107|biped|0.92|boxing_gloves,arms
108|quad|0.82|long_tongue,tail,round_body
109|gas|0.76|gas_orbs,skull_face
110|gas|1.02|double_gas_orbs,skull_face
111|quad|0.90|rhino_body,horn_head,tail,spikes
112|kaiju|1.12|rhino_body,horn_head,tail,drill,wide_body
113|balloon|0.98|egg_body,arms,hair
114|vine|0.86|vine_ball,red_feet
115|kaiju|1.10|kangaroo_body,pouch,tail,ears
116|fish|0.58|seahorse_body,snout,fin
117|fish|0.82|seahorse_body,snout,fin,spikes
118|fish|0.64|fish_body,fins,horn_head,tail_fin
119|fish|0.92|fish_body,fins,horn_head,tail_fin
120|star|0.78|star_body,gem
121|star|1.00|double_star,gem
122|biped|0.92|mime_hands,round_head,feet
123|insect|1.02|scythe_arms,wings,legs
124|biped|0.92|dress_body,hair,arms
125|biped|0.98|electric_arms,horns,tail
126|biped|0.96|flame_head,tail,duck_bill
127|insect|1.04|horn_head,big_claws,legs
128|quad|1.02|bull_body,horns,three_tails
129|fish|0.58|fish_body,fins,whiskers,tail_fin
130|serpent|1.30|sea_dragon,crest,whiskers,long_body
131|sea|1.22|shell_back,long_neck,flippers
132|blob|0.70|blob_body,face
133|quad|0.68|fox_body,big_ears,tail_mane
134|quad|0.96|fish_tail,neck_fin,fox_body
135|quad|0.92|spikes,fox_body,big_ears
136|quad|0.96|flame_mane,fox_body,big_ears
137|poly|0.72|lowpoly_body,duck_bill,tail
138|shell|0.72|spiral_shell,tentacles
139|shell|0.96|spiral_shell,tentacles,spikes
140|crab|0.68|shell_body,legs,claws
141|crab|0.96|blade_arms,shell_body,legs
142|dragon|1.12|large_wings,beak,tail,claws
143|giant|1.25|huge_body,short_arms,feet
144|bird|1.18|large_wings,crest,long_tail
145|bird|1.16|large_wings,spiky_wings,beak
146|bird|1.16|large_wings,flame_wings,crest
147|serpent|0.82|snake_body,round_head,ear_fins
148|serpent|1.02|snake_body,ear_fins,horn_head
149|dragon|1.26|small_wings,horns,tail,belly
150|biped|1.22|alien_body,tail,horns,three_fingers
151|biped|0.72|cat_head,long_tail,small_body
"""

def parse_model_specs() -> Dict[int, Dict[str, Any]]:
    specs: Dict[int, Dict[str, Any]] = {}
    for raw in MODEL_SPECS_RAW.strip().splitlines():
        no_s, archetype, scale_s, feats_s = raw.strip().split('|')
        specs[int(no_s)] = {'archetype': archetype, 'modelScale': float(scale_s), 'features': [x for x in feats_s.split(',') if x]}
    return specs

MODEL_SPECS = parse_model_specs()

def _hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = str(c or '#888888').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', c):
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    return (136, 136, 136)

def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in rgb)

def _mix(c1: str, c2: str, t: float) -> str:
    a = _hex_to_rgb(c1); b = _hex_to_rgb(c2); t=max(0,min(1,float(t)))
    return _rgb_to_hex(tuple(round(a[i]*(1-t)+b[i]*t) for i in range(3)))

def _luma(c: str) -> float:
    r,g,b = _hex_to_rgb(c); return 0.2126*r + 0.7152*g + 0.0722*b

def _sat(c: str) -> float:
    r,g,b=_hex_to_rgb(c); return max(r,g,b)-min(r,g,b)

def _palette_from_cells(cells: List[Dict]) -> Dict[str, str]:
    colors = [str(c.get('color', '#888888')).lower() for c in cells if re.fullmatch(r'#[0-9a-fA-F]{6}', str(c.get('color', '')))]
    if not colors: colors = ['#88aa66', '#1f2937', '#f8fafc']
    counts: Dict[str, int] = {}
    for c in colors: counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts, key=lambda c: counts[c], reverse=True)
    non_white = [c for c in ranked if not (_luma(c) > 238 and _sat(c) < 26)]
    base_pool = non_white or ranked
    body = base_pool[0]; dark = min(base_pool, key=_luma); light = max(base_pool, key=_luma)
    accent = max(base_pool, key=lambda c: _sat(c) * 1.4 + abs(_luma(c)-145) * .15)
    mid2 = base_pool[min(1, len(base_pool)-1)]
    return {'body': body, 'dark': dark, 'light': light, 'accent': accent, 'mid2': mid2, 'eye': '#101010', 'white': '#f8fafc', 'shadow': _mix(body, '#000000', .32), 'hi': _mix(body, '#ffffff', .35)}

def build_pokemon_voxel3d_cells(no: int, name: str, plane_cells: List[Dict], grid: int) -> List[Dict]:
    spec = MODEL_SPECS.get(no, {'archetype': 'biped', 'modelScale': 1.0, 'features': []})
    feats = set(spec['features']); p = _palette_from_cells(plane_cells); scale = float(spec.get('modelScale', 1.0))
    cells: List[Dict[str, Any]] = []; occupied = set()
    def add(x:int,y:int,z:int,color:str,size:float=0.115):
        x=int(round(x)); y=int(round(y)); z=int(round(z))
        if not (0 <= x < 16 and 0 <= y < 16 and 0 <= z < 16): return
        key=(x,y,z)
        if key in occupied: return
        occupied.add(key); cells.append({'x':x,'y':y,'z':z,'color':color,'size':size})
    def box(x1,x2,y1,y2,z1,z2,color,size=0.115):
        for y in range(int(y1), int(y2)+1):
            for x in range(int(x1), int(x2)+1):
                for z in range(int(z1), int(z2)+1): add(x,y,z,color,size)
    def ellipsoid(cx,cy,cz,rx,ry,rz,color,size=0.115,hollow=False):
        for y in range(math.floor(cy-ry), math.ceil(cy+ry)+1):
            for x in range(math.floor(cx-rx), math.ceil(cx+rx)+1):
                for z in range(math.floor(cz-rz), math.ceil(cz+rz)+1):
                    v=((x-cx)/(rx or 1))**2+((y-cy)/(ry or 1))**2+((z-cz)/(rz or 1))**2
                    if v <= 1.0 and (not hollow or v > .55): add(x,y,z,color,size)
    def eye_pair(y=9,z=3,sep=1): add(7-sep,y,z,p['eye']); add(8+sep,y,z,p['eye'])
    def horns(y=12,z=5):
        add(5,y,z,p['light']); add(10,y,z,p['light']); add(5,y+1,z,p['light']); add(10,y+1,z,p['light'])
    def ears(y=11,z=5):
        add(5,y,z,p['accent']); add(10,y,z,p['accent']); add(5,y+1,z,p['dark']); add(10,y+1,z,p['dark'])
    def tail(x=8,y=6,z=11,length=3,color=None):
        color=color or p['accent']
        for i in range(length): add(x, y+i//2, z+i, color)
    arch = spec['archetype']
    if arch in ('quad','kaiju'):
        ellipsoid(8,5,8,3.4*scale,2.0*scale,3.0*scale,p['body']); ellipsoid(8,8,4,2.0*scale,1.8*scale,1.8*scale,p['body'])
        for lx,lz in [(5,6),(11,6),(5,10),(11,10)]: box(lx,lx+1,1,3,lz,lz,p['dark'])
        eye_pair(9,3)
        if 'wide_body' in feats or arch=='kaiju': ellipsoid(8,5,8,4.4*scale,2.2*scale,3.5*scale,p['body'])
        if {'ears','big_ears','cat_ears'} & feats: ears(10,4)
        if {'horn_head','horns'} & feats: horns(10,4)
        if {'tail','short_tail','fox_body'} & feats: tail(8,5,11,4,p['accent'])
    elif arch in ('biped','duck'):
        ellipsoid(8,8,5,2.1*scale,2.0*scale,1.8*scale,p['body']); ellipsoid(8,5,8,2.4*scale,2.4*scale,2.0*scale,p['body'])
        box(5,6,4,7,7,8,p['body']); box(10,11,4,7,7,8,p['body']); box(6,7,1,4,7,8,p['dark']); box(9,10,1,4,7,8,p['dark'])
        eye_pair(9,4)
        if {'long_ears','ears','fox_head','cat_head'} & feats: ears(10,4)
        if {'horn_head','horns'} & feats: horns(10,4)
        if {'tail','long_tail','monkey_tail'} & feats: tail(8,4,10,5,p['accent'])
    elif arch == 'dragon':
        ellipsoid(8,6,8,3.2*scale,2.2*scale,2.7*scale,p['body']); ellipsoid(8,10,4,2.1*scale,1.8*scale,1.7*scale,p['body']); box(7,8,7,10,5,6,p['body'])
        for lx,lz in [(5,7),(11,7),(6,11),(10,11)]: box(lx,lx,1,4,lz,lz,p['dark'])
        eye_pair(11,3); horns(12,4); tail(8,5,11,5,p['accent'])
        box(2,5,7,10,8,8,p['light']); box(11,14,7,10,8,8,p['light']); box(3,4,6,8,9,9,p['accent']); box(12,13,6,8,9,9,p['accent'])
    elif arch in ('bird','bat','butterfly','moth'):
        ellipsoid(8,6,7,2.2*scale,2.1*scale,2.0*scale,p['body']); ellipsoid(8,9,4,1.7*scale,1.5*scale,1.4*scale,p['body']); eye_pair(10,3)
        box(4,6,6,8,7,7,p['light']); box(10,12,6,8,7,7,p['light'])
        if 'large_wings' in feats or arch in ('bat','butterfly','moth'): box(1,5,6,10,7,8,p['accent']); box(11,15,6,10,7,8,p['accent'])
        if {'beak','long_beak'} & feats: box(7,8,8,8,2,2,p['accent'])
        if 'crest' in feats: box(7,8,11,12,4,4,p['accent'])
        tail(8,5,10,3,p['dark'])
    elif arch in ('fish','seal','sea'):
        ellipsoid(8,6,7,3.5*scale,1.8*scale,2.1*scale,p['body']); box(4,5,6,8,7,7,p['accent']); box(11,12,6,8,7,7,p['accent']); box(7,9,5,8,11,12,p['accent']); eye_pair(7,4)
        if 'horn_head' in feats: horns(8,4)
        if 'long_neck' in feats: box(7,9,8,11,5,6,p['body'])
    elif arch in ('serpent','worm'):
        length = 7 if arch=='serpent' else 5
        for i in range(length): ellipsoid(8+int(math.sin(i*.8)*2),4+i//3,4+i,1.7*scale,1.2*scale,1.4*scale,p['body'])
        ellipsoid(8,7,3,2.0*scale,1.6*scale,1.5*scale,p['body']); eye_pair(8,2)
        if 'cobra_hood' in feats: box(5,11,6,9,3,4,p['accent'])
        if 'rock_segments' in feats:
            for i in range(3): ellipsoid(6+i*2,5+i//2,6+i*2,1.6,1.3,1.3,p['dark'],hollow=True)
    elif arch in ('insect','crab'):
        ellipsoid(8,5,7,3.0*scale,1.7*scale,2.2*scale,p['body']); ellipsoid(8,7,4,1.9*scale,1.5*scale,1.5*scale,p['body']); eye_pair(8,3)
        for yy in [4,5,6]: box(3,5,yy,yy,6,6,p['dark']); box(11,13,yy,yy,6,6,p['dark'])
        if {'big_claws','claws'} & feats: box(2,4,6,8,3,4,p['accent']); box(12,14,6,8,3,4,p['accent'])
        if {'wings','large_wings'} & feats: box(3,6,8,10,7,8,p['light']); box(10,13,8,10,7,8,p['light'])
        if 'horn_head' in feats: horns(9,4)
    elif arch in ('rock','ball','balloon','blob','slime','ghost','gas'):
        ellipsoid(8,6,7,3.0*scale,3.0*scale,3.0*scale,p['body'],hollow=(arch=='ghost'))
        eye_pair(7,4)
        if arch in ('rock','gas'): box(4,5,5,7,6,7,p['dark']); box(11,12,5,7,6,7,p['dark'])
        if {'arms','big_arms'} & feats: box(4,5,5,7,6,7,p['body']); box(11,12,5,7,6,7,p['body'])
        if 'face_band' in feats: box(5,11,6,7,4,4,p['dark'])
    elif arch in ('plant','plant_cluster','palm','vine'):
        ellipsoid(8,5,7,2.5*scale,2.2*scale,2.0*scale,p['body']); eye_pair(6,4)
        if {'leaf_head','palm_leaves'} & feats:
            for dx,dz in [(-2,0),(2,0),(0,-2),(0,2)]: box(7+dx,8+dx,8,10,6+dz,7+dz,p['accent'])
        if {'flower','petals'} & feats:
            for dx,dz in [(-2,0),(2,0),(0,-2),(0,2),(0,0)]: ellipsoid(8+dx,9,6+dz,1.2,1.0,1.2,p['accent'])
        if 'six_eggs' in feats:
            cells.clear(); occupied.clear()
            for cx,cz in [(6,5),(9,5),(5,8),(8,8),(11,8),(7,11)]: ellipsoid(cx,4,cz,1.3,1.2,1.3,p['body']); add(cx,5,cz-1,p['eye'])
    elif arch in ('jellyfish','shell','star','poly','magnet','mole','mole_trio','giant','turtle','cocoon'):
        ellipsoid(8,6,7,3.0*scale,2.4*scale,2.6*scale,p['body']); eye_pair(7,4)
        if arch=='star':
            cells.clear(); occupied.clear()
            for dx,dz in [(0,0),(0,-2),(-2,0),(2,0),(0,2)]: box(7+dx,9+dx,5,7,6+dz,8+dz,p['body'])
            add(8,7,5,p['accent']); add(8,7,6,p['accent'])
        if {'tentacles','many_tentacles'} & feats:
            for x in [5,7,9,11]: box(x,x,1,4,8,8,p['accent'])
        if {'magnet_sides','triple_magnets'} & feats: box(3,4,5,7,7,7,p['accent']); box(12,13,5,7,7,7,p['accent'])
        if 'triple_heads' in feats or arch=='mole_trio':
            cells.clear(); occupied.clear()
            for cx,cz in [(6,6),(10,6),(8,10)]: ellipsoid(cx,5,cz,1.8,1.8,1.6,p['body']); add(cx-1,6,cz-1,p['eye']); add(cx+1,6,cz-1,p['eye'])
    else:
        ellipsoid(8,6,7,3,3,3,p['body']); eye_pair(7,4)
    if 'bulb' in feats: ellipsoid(8,8,9,1.8,1.5,1.8,p['accent'])
    if 'big_bulb' in feats: ellipsoid(8,9,9,2.4,1.8,2.2,p['accent'])
    if 'flower' in feats:
        for dx,dz in [(-2,0),(2,0),(0,-2),(0,2)]: ellipsoid(8+dx,10,8+dz,1.2,1.0,1.2,p['accent'])
        ellipsoid(8,10,8,1.1,1.0,1.1,p['light'])
    if {'flame_tail','tail_flame'} & feats: tail(8,6,11,3,p['accent']); add(8,8,14,'#ff7a18'); add(8,9,14,'#ffd166')
    if {'shell_back','shell_body'} & feats: ellipsoid(8,6,9,3.0,2.0,2.2,p['dark'],hollow=True)
    if 'cannons' in feats: box(5,6,9,11,8,9,p['dark']); box(10,11,9,11,8,9,p['dark'])
    if {'spikes','spines'} & feats:
        for z in [5,7,9,11]: add(8,10,z,p['light']); add(8,11,z,p['light'])
    if 'many_tails' in feats:
        for dx in [-2,-1,0,1,2]: tail(8+dx,5,11,4,p['accent'])
    if {'wings','small_wings'} & feats: box(3,5,7,9,8,8,p['light']); box(11,13,7,9,8,8,p['light'])
    if 'large_wings' in feats: box(1,5,7,11,8,9,p['light']); box(11,15,7,11,8,9,p['light'])
    if {'scythe_arms','blade_arms'} & feats: box(2,4,6,9,4,4,p['light']); box(12,14,6,9,4,4,p['light'])
    if {'boxing_gloves','boxing_arms'} & feats: ellipsoid(4,6,5,1.3,1.3,1.3,p['accent']); ellipsoid(12,6,5,1.3,1.3,1.3,p['accent'])
    if {'bone_club','leek','spoon','two_spoons'} & feats:
        box(3,3,5,9,4,4,p['light'])
        if 'two_spoons' in feats: box(13,13,5,9,4,4,p['light'])
    if 'long_tongue' in feats: box(8,8,5,5,1,3,'#ff6b9a')
    if 'gem' in feats: add(8,7,4,p['accent']); add(8,8,4,p['light'])
    if 'cheeks' in feats: add(5,7,4,'#ef4444'); add(11,7,4,'#ef4444')
    if 'coin' in feats: add(8,11,4,'#facc15')
    if 'swirl_belly' in feats: add(8,5,4,p['light']); add(9,5,4,p['light']); add(9,6,4,p['dark'])
    if 'belt' in feats: box(5,11,5,5,6,7,p['dark'])
    if 'pouch' in feats: box(7,9,5,6,4,4,p['light'])
    if 'three_tails' in feats:
        for dx in [-1,0,1]: tail(8+dx,5,11,4,p['dark'])
    if 'whiskers' in feats: box(4,5,8,8,3,3,p['dark']); box(11,12,8,8,3,3,p['dark'])
    if {'mane','dog_mane','flame_mane'} & feats: ellipsoid(8,8,5,2.8,2.2,2.2,p['accent'],hollow=True)
    return cells[:720]

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
            spec = MODEL_SPECS.get(no, {'archetype': 'biped', 'modelScale': 1.0, 'features': []})
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
                    'grid': 16,
                    'scale': 0.115,
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
    js = f"""// Auto-generated by tools/build-pokemon-info-textures.py. Do not hand edit.\n// Source: assets/pokemon-gen1-icons/pokeicon-###.jpg -> generated cropped dot cells + individual field3d nanoblock models.\n// Important: d.cells is the plane info texture. d.field3d is the per-Pokemon individual 3D field model.\n(function(){{\n  const defs = {payload};\n  window.POKEMON_INFO_TEXTURE_DEFS_30 = defs;\n  window.POKEMON_INFO_TEXTURE_DEFS = defs;\n  window.POKEMON_INFO_TEXTURE_FIELD3D_DEFS = defs.map(d=>d.field3d).filter(Boolean);\n  function normalizeHex(c){{ c=String(c||'#22c55e'); if(/^#[0-9a-fA-F]{{6}}$/.test(c)) return c.toLowerCase(); return '#22c55e'; }}\n  function buildField3d(d, plane){{\n    const f=d&&d.field3d; if(!f || !Array.isArray(f.cells) || !f.cells.length) return null;\n    const no=String(d.no||'').padStart(3,'0'); const id=f.id||('info-poke3d_'+no); const type=d.type||('poke_'+no);\n    return {{\n      id, type, infoType:type, name:'情報テクスチャ3D:'+d.name, kind:'voxel3d', grid:16, scale:Number(f.scale)||0.115,\n      cells:f.cells.map(c=>({{x:Math.trunc(Number(c.x)),y:Math.trunc(Number(c.y)),z:Math.trunc(Number(c.z)),color:normalizeHex(c.color),size:Number(c.size)||0.115}})),\n      infoTexture:false, infoTextureIds:[plane.id], sourceInfoTextureId:plane.id, infoRole:'pokemon', hp:12,\n      infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n      behavior:'151体個別ナノブロック3Dモデル。フィールド表示用。図鑑/貼付は平面情報テクスチャを使用。',\n      pokemonIndividual3d:true, pokemon3dArchetype:f.archetype||'', pokemon3dFeatures:f.features||[],\n      createdAt:1, updatedAt:Date.now()\n    }};\n  }}\n  function apply(){{\n    if(!Array.isArray(defs)) return false;\n    const hasMaps = !!(window.customObjectDefs && window.INFO_TEXTURE_META_V3);\n    for(const d of defs){{\n      const id = d.id || ('info-poke_'+String(d.no).padStart(3,'0'));\n      const type = d.type || ('poke_'+String(d.no).padStart(3,'0'));\n      const grid = Number(d.grid || {grid});\n      const plane = {{\n        id, type, infoType:type, name:'情報テクスチャ:'+d.name, kind:'plane', grid:grid, scale:d.scale||{scale},\n        cells:d.cells||[], infoTexture:true, infoRole:'pokemon', hp:12,\n        infoPhysics:{{massKg:1,gravityScale:1,terminalVelocity:18,bounce:0}},\n        behavior:'図鑑ドット絵セル変換済み。野生出現・撃破登録・面貼り付け対象。',\n        field3dId:(d.field3d&&d.field3d.id)||'', pokemonHasIndividual3d:!!(d.field3d&&d.field3d.cells&&d.field3d.cells.length),\n        createdAt:1, updatedAt:Date.now()\n      }};\n      if(window.customObjectDefs){{\n        window.customObjectDefs.set(id, plane);\n        const field3d = buildField3d(d, plane);\n        if(field3d) window.customObjectDefs.set(field3d.id, field3d);\n      }}\n      if(window.INFO_TEXTURE_META_V3){{\n        const meta = window.INFO_TEXTURE_META_V3[id] || window.INFO_TEXTURE_META_V3[type] || {{}};\n        Object.assign(meta, {{id,type,name:d.name,generatedCells:true,generatedCells30:true,iconUrl:'',cells:d.cells,grid:grid,scale:d.scale||{scale},field3d:d.field3d||null,field3dId:(d.field3d&&d.field3d.id)||''}});\n        window.INFO_TEXTURE_META_V3[id] = meta;\n        window.INFO_TEXTURE_META_V3[type] = meta;\n      }}\n    }}\n    try{{ if(window.INFO_TEXTURE_MATERIAL_CACHE_V4) window.INFO_TEXTURE_MATERIAL_CACHE_V4.clear(); }}catch(e){{}}\n    return hasMaps;\n  }}\n  window.applyPokemonGeneratedInfoTextures30 = apply;\n  window.applyPokemonGeneratedInfoTextures = apply;\n  if(!apply()) window.addEventListener('load', apply);\n  setTimeout(apply, 300);\n}})();\n"""
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
    args = ap.parse_args()
    build(Path(args.input), Path(args.out), args.grid, safe_pad=args.safe_pad, scale=args.scale)


if __name__ == '__main__':
    main()
