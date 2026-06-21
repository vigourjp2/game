export class Room {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.sessions = new Map();
    this.players = new Map();
    this.objectsLoaded = false;
    this.objects = [];
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

  normalizeHex(color) {
    const c = String(color || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(c) ? c : '#22c55e';
  }

  cleanCellSize(size, fallback = 0.10) {
    const fb = Number(fallback) || 0.10;
    const n = Number(size);
    return Math.max(0.03, Math.min(0.70, Number.isFinite(n) ? n : fb));
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
      else cells.push({ x, y, z, color, size: this.cleanCellSize(c.size, Number(def.scale) || 0.10) });
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

    return clean;
  }

  async fetch(request) {
    await this.loadObjects();

    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('mine-server-git2 WebSocket server OK / decals enabled', {
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

    const clientId = String(msg.clientId || session.playerId);
    const base = { ...msg, clientId, serverTime: Date.now() };

    if (msg.type === 'ping') {
      try { ws.send(JSON.stringify({ type: 'pong', clientId, time: Date.now() })); } catch {}
      return;
    }

    if (msg.type === 'objectCatalogReq') {
      try { ws.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects, time: Date.now() })); } catch {}
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

    if (msg.type === 'join' || msg.type === 'playerState' || msg.type === 'playerUpdate' || msg.type === 'faceSnapshot' || msg.type === 'blockEdit' || msg.type === 'objectInstanceRemove' || msg.type === 'objectInstancePlace') {
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
    const id = session.playerId;
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
