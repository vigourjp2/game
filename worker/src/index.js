export class MineRoom {
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
    this.objects = Array.isArray(saved) ? saved.slice(-80) : [];
  }

  async saveObjects() {
    await this.state.storage.put('customObjects', this.objects.slice(-80));
  }

  cleanObject(def) {
    if (!def || !Array.isArray(def.cells)) return null;
    const cells = [];
    for (const c of def.cells.slice(0, 512)) {
      const x = Math.trunc(Number(c.x));
      const y = Math.trunc(Number(c.y));
      const color = String(c.color || '').trim().toLowerCase();
      if (x < 0 || x >= 16 || y < 0 || y >= 16) continue;
      if (!/^#[0-9a-f]{6}$/.test(color)) continue;
      cells.push({ x, y, color });
    }
    if (!cells.length) return null;
    return {
      id: String(def.id || crypto.randomUUID()).slice(0, 80),
      name: String(def.name || 'object').slice(0, 40),
      grid: 16,
      scale: Math.max(0.25, Math.min(1.2, Number(def.scale) || 0.55)),
      cells,
      createdAt: Number(def.createdAt) || Date.now()
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
    server.send(JSON.stringify({ type: 'objectCatalog', objects: this.objects }));

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
        if (this.objects.some(o => o.id === clean.id)) continue;
        this.objects.push(clean);
        changed = true;
      }
      if (changed) {
        this.objects = this.objects.slice(-80);
        await this.saveObjects();
        this.broadcast({ type: 'objectCatalog', objects: this.objects }, null);
      }
      return;
    }

    if (msg.type === 'objectRegister') {
      const clean = this.cleanObject(msg.object || msg.def || msg);
      if (!clean) return;
      if (!this.objects.some(o => o.id === clean.id)) {
        this.objects.push(clean);
        this.objects = this.objects.slice(-80);
        await this.saveObjects();
      }
      this.broadcast({ type: 'objectRegister', object: clean, clientId, time: Date.now() }, ws);
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

    // 未知タイプも小さければ中継。将来の拡張用。
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/room/')) {
      return new Response('mine-server-git2 WebSocket server OK', {
        headers: { 'content-type': 'text/plain; charset=utf-8' }
      });
    }
    const roomId = decodeURIComponent(url.pathname.slice('/room/'.length) || 'main');
    const id = env.MINE_ROOM.idFromName(roomId);
    const room = env.MINE_ROOM.get(id);
    return room.fetch(request);
  }
};
