(function(){
  'use strict';

  var LOADER_VERSION = 'pokemon-info-textures-loader.v1';
  var SOURCE_NAME = 'generated/pokemon-info-textures.gen1.30x30.generated.js';

  function safeNow(){ return Date.now ? Date.now() : new Date().getTime(); }
  function normHex(c){
    c = String(c || '').trim();
    if(/^#[0-9a-fA-F]{6}$/.test(c)) return c.toLowerCase();
    if(/^#[0-9a-fA-F]{3}$/.test(c)) return ('#'+c[1]+c[1]+c[2]+c[2]+c[3]+c[3]).toLowerCase();
    return '#22c55e';
  }
  function pokemonId(no){
    no = Math.max(1, Math.min(999, Math.trunc(Number(no)||0)));
    return 'info-pokemon-' + String(no).padStart(3, '0');
  }
  function pokemonName(src, no){
    var n = String((src && src.name) || '').trim();
    return '情報テクスチャ:' + String(no).padStart(3, '0') + (n ? ' ' + n : '');
  }
  function normalizeCells(src, grid){
    var out = [], seen = Object.create(null);
    var cells = Array.isArray(src && src.cells) ? src.cells : [];
    for(var i=0; i<cells.length; i++){
      var c = cells[i] || {};
      var x = Math.trunc(Number(c.x));
      var y = Math.trunc(Number(c.y));
      if(!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= grid || y >= grid) continue;
      var key = x + ',' + y;
      if(seen[key]) continue;
      seen[key] = 1;
      out.push({ x:x, y:y, color:normHex(c.color) });
    }
    return out;
  }
  function registerOne(src){
    if(!src) return false;
    var m = String(src.id || '').match(/(\d+)/);
    var no = Math.trunc(Number(src.no || (m && m[1]) || 0));
    if(!no) return false;
    var grid = Math.max(8, Math.min(128, Math.trunc(Number(src.grid)||30)));
    var cells = normalizeCells(src, grid);
    if(!cells.length) return false;
    var def = {
      id: String(src.id || pokemonId(no)).slice(0,96),
      no: no,
      name: pokemonName(src, no),
      kind: 'plane',
      grid: grid,
      // 30x30は貼付時に潰れすぎないよう少し大きめ。OBJ貼付倍率側でさらに調整可。
      scale: Math.max(0.005, Math.min(0.50, Number(src.scale)||0.055)),
      cells: cells,
      infoTexture: true,
      infoType: 'pokemon',
      infoRole: 'pokemon',
      infoBehavior: 'GitHub Actions生成の30x30多色ドット絵。3Dエディターでブロック面に貼る情報テクスチャ。',
      infoPhysics: { massKg: 6, gravityScale: 1, terminalVelocity: 18, bounce: 0 },
      hp: 12,
      createdAt: 1,
      updatedAt: safeNow(),
      source: SOURCE_NAME
    };
    var clean = (typeof validateObjectDef === 'function') ? validateObjectDef(def) : def;
    if(!clean) return false;
    // validateObjectDefで落ちる補助メタは戻す。既存の情報テクスチャ判定・解放処理に乗せるため。
    clean.no = no;
    clean.infoTexture = true;
    clean.infoType = 'pokemon';
    clean.infoRole = 'pokemon';
    clean.infoBehavior = def.infoBehavior;
    clean.infoPhysics = def.infoPhysics;
    clean.hp = def.hp;
    clean.updatedAt = def.updatedAt;
    clean.source = SOURCE_NAME;
    customObjectDefs.set(clean.id, clean);
    return true;
  }
  function loadPokemonInfoTextures(){
    var arr = window.POKEMON_INFO_TEXTURE_DEFS_30;
    if(!Array.isArray(arr) || !arr.length){
      console.warn(LOADER_VERSION + ': window.POKEMON_INFO_TEXTURE_DEFS_30 が無い。' + SOURCE_NAME + ' の読み込み順/配置を確認。');
      return 0;
    }
    if(typeof customObjectDefs === 'undefined'){
      console.warn(LOADER_VERSION + ': customObjectDefs がまだ無い。index-mine.html本体の後にloaderを読む必要あり。');
      return 0;
    }
    var ok = 0;
    for(var i=0; i<arr.length; i++){
      try{ if(registerOne(arr[i])) ok++; }catch(e){ console.warn(LOADER_VERSION + ': register failed', arr[i] && arr[i].id, e); }
    }
    try{ if(typeof renderObjectManager === 'function') renderObjectManager(); }catch(e){}
    try{ if(typeof updateTexturePasteOptions === 'function') updateTexturePasteOptions(); }catch(e){}
    try{ if(typeof setObjHud === 'function') setObjHud(); }catch(e){}
    try{ if(typeof setMsg === 'function') setMsg('ポケモン情報テクスチャ読込: ' + ok + '件 / 倒すと平面テクスチャ解放', ok ? 'good' : 'bad'); }catch(e){}
    console.log(LOADER_VERSION + ': loaded ' + ok + ' pokemon info textures');
    window.POKEMON_INFO_TEXTURE_LOADED_COUNT = ok;
    return ok;
  }

  window.loadPokemonInfoTextures = loadPokemonInfoTextures;
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', loadPokemonInfoTextures, { once:true });
  }else{
    loadPokemonInfoTextures();
  }
})();
