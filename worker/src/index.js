export class Room {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.sessions = new Map();
    this.players = new Map();
    this.objectsLoaded = false;
    this.objects = [];
    this.instancesLoaded = false;
    this.instances = [];
    this.linksLoaded = false;
    this.links = [];
    this.worldEditsLoaded = false;
    this.worldEdits = [];
    this.worldStateLoaded = false;
    this.worldState = null;
    this.instancesSaveTimer = null;
    this.linksSaveTimer = null;
    this.worldEditsSaveTimer = null;
  }

  async loadObjects() {
    if (this.objectsLoaded) return;
    this.objectsLoaded = true;
    const saved = await this.state.storage.get('customObjects');
    this.objects = Array.isArray(saved) ? saved.slice(-100) : [];
  }

  async saveObjects() {
    await this.state.storage.put('customObjects', this.objects.slice(-100));
  }

  async loadInstances() {
    if (this.instancesLoaded) return;
    this.instancesLoaded = true;
    const saved = await this.state.storage.get('customObjectInstances');
    this.instances = Array.isArray(saved) ? saved.slice(-300) : [];
  }

  async saveInstances() {
    await this.state.storage.put('customObjectInstances', this.instances.slice(-300));
  }

  async loadLinks() {
    if (this.linksLoaded) return;
    this.linksLoaded = true;
    const saved = await this.state.storage.get('customObjectLinks');
    this.links = Array.isArray(saved) ? saved.slice(-500) : [];
  }

  async saveLinks() {
    await this.state.storage.put('customObjectLinks', this.links.slice(-500));
  }

  async loadWorldEdits() {
    if (this.worldEditsLoaded) return;
    this.worldEditsLoaded = true;
    const saved = await this.state.storage.get('worldEdits');
    this.worldEdits = Array.isArray(saved) ? saved.slice(-5000) : [];
  }

  async saveWorldEdits() {
    await this.state.storage.put('worldEdits', this.worldEdits.slice(-5000));
  }

  async loadWorldState() {
    if (this.worldStateLoaded) return;
    this.worldStateLoaded = true;
    const saved = await this.state.storage.get('sharedWorldState');
    if (saved && typeof saved === 'object' && Number.isFinite(Number(saved.startEpochMs))) {
      this.worldState = saved;
      return;
    }
    this.worldState = {
      type: 'worldState',
      version: 'v12-shared-time-weather-spawn',
      startEpochMs: Date.now(),
      dayLengthMs: 720000,
      weatherPeriodMs: 240000,
      weatherSeed: Math.floor(Math.random() * 1000000000),
      updatedAt: Date.now()
    };
    await this.state.storage.put('sharedWorldState', this.worldState);
  }

  worldStateMessage() {
    return {
      type: 'worldState',
      state: this.worldState,
      serverNow: Date.now(),
      time: Date.now()
    };
  }


  scheduleSaveInstances() {
    if (this.instancesSaveTimer) return;
    this.instancesSaveTimer = setTimeout(async () => {
      this.instancesSaveTimer = null;
      try { await this.saveInstances(); } catch {}
    }, 650);
  }

  scheduleSaveLinks() {
    if (this.linksSaveTimer) return;
    this.linksSaveTimer = setTimeout(async () => {
      this.linksSaveTimer = null;
      try { await this.saveLinks(); } catch {}
    }, 350);
  }

  scheduleSaveWorldEdits() {
    if (this.worldEditsSaveTimer) return;
    this.worldEditsSaveTimer = setTimeout(async () => {
      this.worldEditsSaveTimer = null;
      try { await this.saveWorldEdits(); } catch {}
    }, 450);
  }

  cleanBlockEdit(msg) {
    if (!msg) return null;
    const x = Math.trunc(Number(msg.x));
    const y = Math.trunc(Number(msg.y));
    const z = Math.trunc(Number(msg.z));
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
    const isBreak = msg.block === null || msg.type === 'break';
    const block = isBreak ? null : String(msg.block || msg.blockType || msg.kind || 'grass').slice(0, 30);
    return { type:'blockEdit', x, y, z, block, updatedAt: Date.now() };
  }

  cleanLink(msg) {
    const a = String(msg && (msg.a || msg.instanceKey || msg.from) || '').slice(0, 160);
    const b = String(msg && (msg.b || msg.other || msg.to) || '').slice(0, 160);
    if (!a || !b || a === b) return null;
    const aa = a < b ? a : b;
    const bb = a < b ? b : a;
    return { type: 'objectInstanceAttach', a: aa, b: bb, updatedAt: Date.now() };
  }

  cleanInstance(msg) {
    if (!msg) return null;
    const defId = String(msg.objectId || msg.defId || msg.id || '').slice(0, 96);
    const instanceKey = String(msg.instanceKey || '').slice(0, 160);
    const x = Number(msg.x), y = Number(msg.y), z = Number(msg.z);
    const yaw = Number(msg.yaw) || 0;
    if (!defId || !instanceKey) return null;
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
    return {
      type: 'objectInstancePlace',
      objectId: defId,
      defId,
      instanceKey,
      x: Math.round(x * 1000) / 1000,
      y: Math.round(y * 1000) / 1000,
      z: Math.round(z * 1000) / 1000,
      yaw: Math.round(yaw * 1000000) / 1000000,
      updatedAt: Date.now()
    };
  }

  normalizeHex(color) {
    const c = String(color || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(c) ? c : '#22c55e';
  }

  cleanTextureCells(cells, grid) {
    const out = [];
    const seen = new Set();
    if (!Array.isArray(cells)) return out;
    for (const c of cells.slice(0, 128 * 128)) {
      const x = Math.trunc(Number(c.x));
      const y = Math.trunc(Number(c.y));
      if (x < 0 || x >= grid || y < 0 || y >= grid) continue;
      const key = `${x},${y}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ x, y, color: this.normalizeHex(c.color) });
    }
    return out;
  }

  cleanDecal(d) {
    if (!d) return null;
    const x = Math.trunc(Number(d.x));
    const y = Math.trunc(Number(d.y));
    const z = Math.trunc(Number(d.z));
    if (x < 0 || x >= 16 || y < 0 || y >= 16 || z < 0 || z >= 16) return null;

    const face = ['px', 'nx', 'py', 'ny', 'pz', 'nz'].includes(d.face) ? d.face : 'pz';
    const grid = Math.max(8, Math.min(128, Math.trunc(Number(d.grid) || 64)));
    const cells = this.cleanTextureCells(d.cells, grid);
    if (!cells.length) return null;

    return {
      x,
      y,
      z,
      face,
      textureId: String(d.textureId || '').slice(0, 96),
      grid,
      cells
    };
  }

  cleanObject(def) {
    if (!def || !Array.isArray(def.cells)) return null;

    const kind = def.kind === 'plane' ? 'plane' : 'voxel3d';
    const grid = kind === 'plane'
      ? Math.max(8, Math.min(128, Math.trunc(Number(def.grid) || 64)))
      : Math.max(4, Math.min(32, Math.trunc(Number(def.grid) || 16)));

    const maxCells = kind === 'plane' ? 128 * 128 : 1536;
    const cells = [];
    const seen = new Set();

    for (const c of def.cells.slice(0, maxCells)) {
      const x = Math.trunc(Number(c.x));
      const y = Math.trunc(Number(c.y));
      const z = kind === 'plane' ? 0 : Math.trunc(Number(c.z));
      const color = this.normalizeHex(c.color);

      if (x < 0 || x >= grid || y < 0 || y >= grid) continue;
      if (kind === 'voxel3d' && (z < 0 || z >= grid)) continue;
      const key = kind === 'plane' ? `${x},${y}` : `${x},${y},${z}`;
      if (seen.has(key)) continue;
      seen.add(key);

      if (kind === 'plane') cells.push({ x, y, color });
      else {
        const size = Math.max(0.03, Math.min(0.70, Number(c.size) || Number(def.scale) || 0.16));
        const cell = { x, y, z, color, size };
        const lx = Number(c.lx), ly = Number(c.ly), lz = Number(c.lz);
        const lim = grid * Math.max(0.03, Number(def.scale) || size || 0.16) * 1.2;
        if (Number.isFinite(lx) && Number.isFinite(ly) && Number.isFinite(lz)
            && Math.abs(lx) <= lim && ly >= -0.5 && ly <= lim && Math.abs(lz) <= lim) {
          cell.lx = Math.round(lx * 10000) / 10000;
          cell.ly = Math.round(ly * 10000) / 10000;
          cell.lz = Math.round(lz * 10000) / 10000;
        }
        cells.push(cell);
      }
    }

    if (!cells.length) return null;

    const clean = {
      id: String(def.id || crypto.randomUUID()).slice(0, 96),
      name: String(def.name || 'object').slice(0, 40),
      kind,
      grid,
      scale: kind === 'plane'
        ? Math.max(0.005, Math.min(0.5, Number(def.scale) || 0.04))
        : Math.max(0.03, Math.min(0.8, Number(def.scale) || 0.16)),
      cells,
      createdAt: Number(def.createdAt) || Date.now(),
      updatedAt: Number(def.updatedAt) || Date.now()
    };

    if (kind === 'voxel3d' && Array.isArray(def.decals)) {
      const decals = [];
      for (const d of def.decals.slice(0, 64)) {
        const cleanDecal = this.cleanDecal(d);
        if (cleanDecal) decals.push(cleanDecal);
      }
      if (decals.length) clean.decals = decals;
    }

    const infoTextureIds = [];
    const pushInfo = (v) => {
      const id = String(v || '').slice(0, 96);
      if (id && !infoTextureIds.includes(id)) infoTextureIds.push(id);
    };
    if (Array.isArray(def.infoTextureIds)) def.infoTextureIds.forEach(pushInfo);
    if (def.infoTexture) clean.infoTexture = true;
    if (def.infoType) clean.infoType = String(def.infoType).slice(0, 40);
    if (def.infoCarrier) clean.infoCarrier = String(def.infoCarrier).slice(0, 40);
    if (def.worldSpawn) clean.worldSpawn = true;
    if (Number.isFinite(Number(def.hp))) clean.hp = Math.max(1, Math.min(200, Math.trunc(Number(def.hp))));
    if (infoTextureIds.length) clean.infoTextureIds = infoTextureIds;

    return clean;
  }

  async fetch(request) {
    await this.loadObjects();
    await this.loadInstances();
    await this.loadLinks();
    await this.loadWorldEdits();
    await this.loadWorldState();

    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('mine-server-git2 WebSocket server OK / worldState + shared info-texture spawn sync enabled', {
        headers: { 'content-type': 'text/plain; charset=utf-8' }
      });
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    server.accept();

    const serverPlayerId = crypto.randomUUID();
    this.sessions.set(server, { playerId: serverPlayerId, connectedAt: Date.now() });

    server.send(JSON.stringify({ type: 'welcome', playerId: serverPlayerId, time: Date.now() }));
    server.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects, time: Date.now() }));
    server.send(JSON.stringify({ type: 'objectInstances', instances: this.instances, time: Date.now() }));
    server.send(JSON.stringify({ type: 'objectInstanceLinks', links: this.links, time: Date.now() }));
    server.send(JSON.stringify({ type: 'worldEdits', edits: this.worldEdits.slice(-5000), time: Date.now() }));
    server.send(JSON.stringify(this.worldStateMessage()));
    server.send(JSON.stringify({ type: 'players', players: Array.from(this.players.values()), time: Date.now() }));

    server.addEventListener('message', async (event) => {
      await this.onMessage(server, event.data);
    });
    server.addEventListener('close', () => this.onClose(server));
    server.addEventListener('error', () => this.onClose(server));

    return new Response(null, { status: 101, webSocket: client });
  }

  async onMessage(ws, raw) {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    if (!msg || typeof msg !== 'object') return;

    const session = this.sessions.get(ws);
    if (!session) return;

    const clientId = String(msg.clientId || session.clientId || session.playerId);
    session.clientId = clientId;
    const base = { ...msg, clientId, serverTime: Date.now() };

    if (msg.type === 'ping') {
      try { ws.send(JSON.stringify({ type: 'pong', clientId, time: Date.now() })); } catch {}
      return;
    }

    if (msg.type === 'worldStateReq') {
      try { ws.send(JSON.stringify(this.worldStateMessage())); } catch {}
      return;
    }

    if (msg.type === 'objectCatalogReq') {
      try { ws.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects, time: Date.now() })); } catch {}
      try { ws.send(JSON.stringify({ type: 'objectInstances', instances: this.instances, time: Date.now() })); } catch {}
      try { ws.send(JSON.stringify({ type: 'objectInstanceLinks', links: this.links, time: Date.now() })); } catch {}
      try { ws.send(JSON.stringify({ type: 'worldEdits', edits: this.worldEdits.slice(-5000), time: Date.now() })); } catch {}
      try { ws.send(JSON.stringify(this.worldStateMessage())); } catch {}
      try { ws.send(JSON.stringify({ type: 'players', players: Array.from(this.players.values()), time: Date.now() })); } catch {}
      return;
    }

    if (msg.type === 'worldReset') {
      this.worldEdits = [];
      await this.saveWorldEdits();
      this.broadcast({ type: 'worldReset', clientId, time: Date.now() }, null);
      return;
    }

    if (msg.type === 'objectWorldReset') {
      this.instances = [];
      this.links = [];
      await this.saveInstances();
      await this.saveLinks();
      this.broadcast({ type: 'objectWorldReset', clientId, time: Date.now() }, null);
      return;
    }

    if (msg.type === 'objectCatalog' && Array.isArray(msg.objects)) {
      let changed = false;
      for (const d of msg.objects) {
        const clean = this.cleanObject(d);
        if (!clean) continue;
        const idx = this.objects.findIndex(o => o.id === clean.id);
        if (idx >= 0) this.objects[idx] = clean;
        else this.objects.push(clean);
        changed = true;
      }
      if (changed) {
        this.objects = this.objects.slice(-100);
        await this.saveObjects();
        this.broadcast({ type: 'objectCatalog', objects: this.objects, time: Date.now() }, null);
      }
      return;
    }

    if (msg.type === 'objectDelete') {
      const objectId = String(msg.objectId || msg.id || '').slice(0, 96);
      if (!objectId) return;
      const before = this.objects.length;
      this.objects = this.objects.filter(o => o.id !== objectId);
      if (this.objects.length !== before) await this.saveObjects();
      this.broadcast({ type: 'objectDelete', objectId, clientId, time: Date.now() }, null);
      try { ws.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects, time: Date.now() })); } catch {}
      return;
    }

    if (msg.type === 'objectRegister') {
      const clean = this.cleanObject(msg.object || msg.def || msg);
      if (!clean) return;
      const idx = this.objects.findIndex(o => o.id === clean.id);
      if (idx >= 0) this.objects[idx] = clean;
      else this.objects.push(clean);
      this.objects = this.objects.slice(-100);
      await this.saveObjects();
      this.broadcast({ type: 'objectRegister', object: clean, clientId, time: Date.now() }, ws);
      try { ws.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects, time: Date.now() })); } catch {}
      return;
    }

    if (msg.type === 'objectInstancePlace') {
      const cleanObj = this.cleanObject(msg.object || msg.def || null);
      if (cleanObj) {
        const idx = this.objects.findIndex(o => o.id === cleanObj.id);
        if (idx >= 0) this.objects[idx] = cleanObj;
        else this.objects.push(cleanObj);
        this.objects = this.objects.slice(-100);
        await this.saveObjects();
      }
      const inst = this.cleanInstance(msg);
      if (!inst) return;
      const idx = this.instances.findIndex(i => i.instanceKey === inst.instanceKey);
      if (idx >= 0) this.instances[idx] = inst;
      else this.instances.push(inst);
      this.instances = this.instances.slice(-300);
      await this.saveInstances();
      if (cleanObj) this.broadcast({ type: 'objectRegister', object: cleanObj, clientId, time: Date.now() }, ws);
      this.broadcast({ ...inst, clientId, time: Date.now() }, ws);
      return;
    }

    if (msg.type === 'objectInstanceRemove') {
      const instanceKey = String(msg.instanceKey || '').slice(0, 160);
      if (!instanceKey) return;
      const before = this.instances.length;
      this.instances = this.instances.filter(i => i.instanceKey !== instanceKey);
      if (this.instances.length !== before) await this.saveInstances();
      this.broadcast({ type: 'objectInstanceRemove', instanceKey, clientId, time: Date.now() }, ws);
      return;
    }

    if (msg.type === 'objectInstanceTransform') {
      const instanceKey = String(msg.instanceKey || '').slice(0, 160);
      const existing = this.instances.find(i => i.instanceKey === instanceKey);
      if (existing) {
        const x = Number(msg.x), y = Number(msg.y), z = Number(msg.z), yaw = Number(msg.yaw) || 0;
        if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
          existing.x = Math.round(x * 1000) / 1000;
          existing.y = Math.round(y * 1000) / 1000;
          existing.z = Math.round(z * 1000) / 1000;
          existing.yaw = Math.round(yaw * 1000000) / 1000000;
          existing.updatedAt = Date.now();
          this.scheduleSaveInstances();
        }
      }
      this.broadcast(base, ws);
      return;
    }

    if (msg.type === 'objectInstanceAttach') {
      const link = this.cleanLink(msg);
      if (!link) return;
      const idx = this.links.findIndex(l => (l.a === link.a && l.b === link.b));
      if (idx >= 0) this.links[idx] = link;
      else this.links.push(link);
      this.links = this.links.slice(-500);
      this.scheduleSaveLinks();
      this.broadcast({ ...link, clientId, time: Date.now() }, ws);
      return;
    }

    if (msg.type === 'objectInstanceDetach') {
      const link = this.cleanLink(msg);
      if (!link) return;
      const before = this.links.length;
      this.links = this.links.filter(l => !(l.a === link.a && l.b === link.b));
      if (this.links.length !== before) this.scheduleSaveLinks();
      this.broadcast({ type: 'objectInstanceDetach', a: link.a, b: link.b, clientId, time: Date.now() }, ws);
      return;
    }

    if (msg.type === 'blockEdit') {
      const edit = this.cleanBlockEdit(msg);
      if (!edit) return;
      const k = `${edit.x},${edit.y},${edit.z}`;
      const idx = this.worldEdits.findIndex(e => `${e.x},${e.y},${e.z}` === k);
      if (idx >= 0) this.worldEdits[idx] = edit;
      else this.worldEdits.push(edit);
      this.worldEdits = this.worldEdits.slice(-5000);
      this.scheduleSaveWorldEdits();
      this.broadcast({ ...edit, clientId, time: Date.now() }, ws);
      return;
    }

    if (msg.type === 'join' || msg.type === 'playerState' || msg.type === 'playerUpdate' || msg.type === 'faceSnapshot') {
      if (msg.type === 'join' || msg.type === 'playerState' || msg.type === 'playerUpdate') {
        this.players.set(clientId, {
          clientId,
          name: String(msg.name || clientId).slice(0, 30),
          x: Number(msg.x) || 0,
          y: Number(msg.y) || 0,
          z: Number(msg.z) || 0,
          yaw: Number(msg.yaw) || 0,
          pitch: Number(msg.pitch) || 0,
          t: Date.now()
        });
      }
      this.broadcast(base, ws);
      return;
    }

    if (String(raw).length < 20000) this.broadcast(base, ws);
  }

  onClose(ws) {
    const session = this.sessions.get(ws);
    if (!session) return;
    this.sessions.delete(ws);
    const id = session.clientId || session.playerId;
    this.players.delete(id);
    this.broadcast({ type: 'leave', playerId: id, clientId: id, time: Date.now() }, ws);
  }

  broadcast(obj, exceptWs = null) {
    const text = JSON.stringify(obj);
    for (const socket of this.sessions.keys()) {
      if (socket === exceptWs) continue;
      try { socket.send(text); } catch { this.onClose(socket); }
    }
  }
}

export { Room as MineRoom };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const roomName = url.pathname.startsWith('/room/')
      ? decodeURIComponent(url.pathname.slice('/room/'.length) || 'main')
      : (url.searchParams.get('room') || 'main');

    const binding = env.ROOM || env.MINE_ROOM;
    if (!binding) return new Response('Missing Durable Object binding ROOM', { status: 500 });

    const id = binding.idFromName(roomName || 'main');
    const room = binding.get(id);
    return room.fetch(request);
  }
};
