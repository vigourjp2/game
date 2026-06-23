/*
 Pokemon Gen1 information texture loader for index-mine.html.
 - Use generated/pokemon-info-textures.gen1.30x30.generated.js when built.
 - Registers 151 plane information textures as kind:"plane", grid:30.
*/
(function(){
  'use strict';
  const NAMES = ["フシギダネ", "フシギソウ", "フシギバナ", "ヒトカゲ", "リザード", "リザードン", "ゼニガメ", "カメール", "カメックス", "キャタピー", "トランセル", "バタフリー", "ビードル", "コクーン", "スピアー", "ポッポ", "ピジョン", "ピジョット", "コラッタ", "ラッタ", "オニスズメ", "オニドリル", "アーボ", "アーボック", "ピカチュウ", "ライチュウ", "サンド", "サンドパン", "ニドラン♀", "ニドリーナ", "ニドクイン", "ニドラン♂", "ニドリーノ", "ニドキング", "ピッピ", "ピクシー", "ロコン", "キュウコン", "プリン", "プクリン", "ズバット", "ゴルバット", "ナゾノクサ", "クサイハナ", "ラフレシア", "パラス", "パラセクト", "コンパン", "モルフォン", "ディグダ", "ダグトリオ", "ニャース", "ペルシアン", "コダック", "ゴルダック", "マンキー", "オコリザル", "ガーディ", "ウインディ", "ニョロモ", "ニョロゾ", "ニョロボン", "ケーシィ", "ユンゲラー", "フーディン", "ワンリキー", "ゴーリキー", "カイリキー", "マダツボミ", "ウツドン", "ウツボット", "メノクラゲ", "ドククラゲ", "イシツブテ", "ゴローン", "ゴローニャ", "ポニータ", "ギャロップ", "ヤドン", "ヤドラン", "コイル", "レアコイル", "カモネギ", "ドードー", "ドードリオ", "パウワウ", "ジュゴン", "ベトベター", "ベトベトン", "シェルダー", "パルシェン", "ゴース", "ゴースト", "ゲンガー", "イワーク", "スリープ", "スリーパー", "クラブ", "キングラー", "ビリリダマ", "マルマイン", "タマタマ", "ナッシー", "カラカラ", "ガラガラ", "サワムラー", "エビワラー", "ベロリンガ", "ドガース", "マタドガス", "サイホーン", "サイドン", "ラッキー", "モンジャラ", "ガルーラ", "タッツー", "シードラ", "トサキント", "アズマオウ", "ヒトデマン", "スターミー", "バリヤード", "ストライク", "ルージュラ", "エレブー", "ブーバー", "カイロス", "ケンタロス", "コイキング", "ギャラドス", "ラプラス", "メタモン", "イーブイ", "シャワーズ", "サンダース", "ブースター", "ポリゴン", "オムナイト", "オムスター", "カブト", "カブトプス", "プテラ", "カビゴン", "フリーザー", "サンダー", "ファイヤー", "ミニリュウ", "ハクリュー", "カイリュー", "ミュウツー", "ミュウ"];
  const PACK_KEY = 'pokemon-info-textures.gen1.30x30';
  const PREFIX = 'info-pokemon-';
  const SOURCE_BASE = 'https://web.archive.org/web/20240319000051im_/https://pixel-art.tsurezure-brog.com/home/images/pokeicon-';

  function pad3(n){ return String(n).padStart(3,'0'); }
  function sourceUrl(n){ return SOURCE_BASE + n + '-150x150.jpg'; }
  function baseDef(n, cells){
    const no = pad3(n), name = NAMES[n-1] || no;
    return {
      id: PREFIX + no,
      no: n,
      name: '情報テクスチャ:' + no + ' ' + name,
      kind: 'plane',
      grid: 30,
      scale: 0.045,
      cells: Array.isArray(cells) ? cells : [],
      infoTexture: true,
      infoType: 'pokemon-' + no,
      infoRole: 'pokemon-gen1',
      infoBehavior: '第1世代ポケモン手持ちアイコン由来の30×30情報テクスチャ: ' + name,
      infoPhysics: {massKg:1, gravityScale:1, terminalVelocity:18, bounce:0},
      hp: 8,
      sourceUrl: sourceUrl(n),
      createdAt: 1,
      updatedAt: 1
    };
  }
  function hasGameRegistry(){ return !!(window.customObjectDefs && typeof window.validateObjectDef === 'function'); }
  function register(def){
    if(!hasGameRegistry() || !def || !Array.isArray(def.cells) || !def.cells.length) return false;
    const clean = window.validateObjectDef(def) || def;
    clean.infoTexture = true;
    clean.infoType = def.infoType;
    clean.infoRole = def.infoRole;
    clean.infoBehavior = def.infoBehavior;
    clean.infoPhysics = def.infoPhysics;
    clean.hp = def.hp;
    clean.no = def.no;
    clean.sourceUrl = def.sourceUrl;
    window.customObjectDefs.set(clean.id, clean);
    return true;
  }
  function loadGeneratedDefs(){
    if(Array.isArray(window.POKEMON_INFO_TEXTURE_DEFS_30)) return window.POKEMON_INFO_TEXTURE_DEFS_30;
    try{
      const raw = localStorage.getItem(PACK_KEY);
      const arr = raw ? JSON.parse(raw) : null;
      if(Array.isArray(arr)) return arr;
    }catch(e){}
    return [];
  }
  function registerPokemonInfoTextures(){
    const defs = loadGeneratedDefs();
    let ok = 0;
    for(let n=1;n<=151;n++){
      const no = pad3(n);
      const found = defs.find(d => String(d.id) === PREFIX + no || Number(d.no) === n);
      if(found && register(Object.assign(baseDef(n, found.cells), found))) ok++;
    }
    try{ if(typeof window.setObjHud === 'function') window.setObjHud(); }catch(e){}
    try{ if(typeof window.renderObjectManager === 'function') window.renderObjectManager(); }catch(e){}
    window.POKEMON_INFO_TEXTURE_STATUS = {registered: ok, expected: 151, generatedLoaded: defs.length};
    return ok;
  }

  window.POKEMON_INFO_TEXTURE_NAMES = NAMES;
  window.registerPokemonInfoTextures = registerPokemonInfoTextures;

  // Run after the game has defined customObjectDefs/validateObjectDef.
  function boot(retry){
    if(hasGameRegistry()){ registerPokemonInfoTextures(); return; }
    if(retry < 80) setTimeout(() => boot(retry+1), 250);
  }
  boot(0);
})();
