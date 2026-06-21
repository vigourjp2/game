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

  cleanObject(def) {
    if (!def || !Array.isArray(def.cells)) return null;

    const kind = def.kind === 'plane' ? 'plane' : 'voxel3d';
    const grid = Math.max(4, Math.min(32, Math.trunc(Number(def.grid) || 16)));
    const maxCells = kind === 'plane' ? 512 : 1536;
    const cells = [];

    for (const c of def.cells.slice(0, maxCells)) {
      const x = Math.trunc(Number(c.x));
      const y = Math.trunc(Number(c.y));
      const z = kind === 'plane' ? 0 : Math.trunc(Number(c.z));
      const color = String(c.color || '').trim().toLowerCase();

      if (x < 0 || x >= grid || y < 0 || y >= grid) continue;
      if (kind === 'voxel3d' && (z < 0 || z >= grid)) continue;
      if (!/^#[0-9a-f]{6}$/.test(color)) continue;

      if (kind === 'plane') cells.push({ x, y, color });
      else cells.push({ x, y, z, color });
    }

    if (!cells.length) return null;

    return {
      id: String(def.id || crypto.randomUUID()).slice(0, 96),
      name: String(def.name || 'object').slice(0, 40),
      kind,
      grid,
      scale: Math.max(0.03, Math.min(0.8, Number(def.scale) || 0.16)),
      cells,
      createdAt: Number(def.createdAt) || Date.now(),
      updatedAt: Number(def.updatedAt) || Date.now()
    };
  }

  async fetch(request) {
    await this.loadObjects();

    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('mine-server-git2 WebSocket server OK', {
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

    if (msg.type === 'join' || msg.type === 'playerState' || msg.type === 'playerUpdate' || msg.type === 'faceSnapshot' || msg.type === 'blockEdit') {
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
    for (const ws of Array.from(this.sessions.keys())) {
      if (ws === exceptWs) continue;
      try { ws.send(text); }
      catch { this.onClose(ws); }
    }
  }
}

// wrangler側が MineRoom 指定でも壊れないように別名もexportする。
export { Room as MineRoom };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/room/')) {
      return new Response('mine-server-git2 WebSocket server OK', {
        headers: { 'content-type': 'text/plain; charset=utf-8' }
      });
    }

    const roomId = decodeURIComponent(url.pathname.slice('/room/'.length) || 'main');
    const namespace = env.MINE_ROOM || env.ROOM;
    if (!namespace) {
      return new Response('Durable Object binding not found. Expected env.MINE_ROOM or env.ROOM.', { status: 500 });
    }

    const id = namespace.idFromName(roomId);
    const room = namespace.get(id);
    return room.fetch(request);
  }
};
