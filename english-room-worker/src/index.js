export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/room/')) {
      const roomName = (url.pathname.split('/').filter(Boolean)[1] || 'english').replace(/[^a-zA-Z0-9_-]/g, '') || 'english';
      const id = env.ROOM.idFromName(roomName);
      return env.ROOM.get(id).fetch(request);
    }
    if (url.pathname === '/health') {
      return Response.json({ ok: true, service: 'english-pittan-room-worker', version: 'v113-board-full-winner' });
    }
    return new Response('English Pittan room worker. Use /room/english for WebSocket.', { status: 200 });
  }
};

const COLORS = ['#38bdf8', '#f472b6', '#a3e635', '#facc15'];

function normalizePlayerCount(n) {
  n = Number(n || 2);
  if (!Number.isFinite(n)) n = 2;
  return Math.max(2, Math.min(4, Math.floor(n)));
}
function safeName(name, fallback = '') {
  return String(name || fallback || '').trim().slice(0, 18);
}
function clone(x) {
  return x == null ? x : JSON.parse(JSON.stringify(x));
}

export class EnglishRoom {
  constructor(state, env) {
    this.stateStore = state;
    this.env = env;
    this.sessions = new Map();
    this.room = null;
  }

  async loadRoom() {
    if (!this.room) {
      this.room = await this.stateStore.storage.get('room');
      if (!this.room) {
        this.room = {
          createdAt: Date.now(),
          playerCount: 2,
          seats: [],
          state: null,
          updateSeq: 0
        };
      }
    }
    return this.room;
  }

  async saveRoom() {
    if (this.room) await this.stateStore.storage.put('room', this.room);
  }

  async fetch(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }
    await this.loadRoom();
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    const sid = crypto.randomUUID().slice(0, 12);
    const session = { sid, ws: server, clientId: '', name: '', seatIndex: -1, joinedAt: Date.now() };
    this.sessions.set(sid, session);
    server.addEventListener('message', event => this.onMessage(session, event.data).catch(err => {
      this.send(session, { type: 'actionRejected', server: true, reason: String(err?.message || err) });
    }));
    const close = () => this.sessions.delete(sid);
    server.addEventListener('close', close);
    server.addEventListener('error', close);
    return new Response(null, { status: 101, webSocket: client });
  }

  roomHostId() {
    return this.room?.seats?.[0]?.clientId || null;
  }

  seatIndexForClient(clientId) {
    const cid = String(clientId || '');
    if (!cid) return -1;
    return (this.room.seats || []).findIndex(s => s && s.clientId === cid);
  }

  assignSeat(session) {
    const cid = String(session.clientId || '');
    if (!cid) return -1;
    const existing = this.seatIndexForClient(cid);
    if (existing >= 0) {
      this.room.seats[existing] = { clientId: cid, name: safeName(session.name, this.room.seats[existing]?.name || `Player ${existing + 1}`) };
      session.seatIndex = existing;
      return existing;
    }
    for (let i = 0; i < this.room.playerCount; i++) {
      if (!this.room.seats[i]) {
        this.room.seats[i] = { clientId: cid, name: safeName(session.name, `Player ${i + 1}`) };
        session.seatIndex = i;
        return i;
      }
    }
    session.seatIndex = -1;
    return -1;
  }

  stampState(state) {
    if (!state || !Array.isArray(state.players)) return state;
    state.playerCount = normalizePlayerCount(state.playerCount || this.room.playerCount);
    this.room.playerCount = normalizePlayerCount(state.playerCount);
    state.roomHostId = this.roomHostId();
    state.roomCreatedAt = this.room.createdAt;
    state.serverUpdateSeq = this.room.updateSeq;
    for (let i = 0; i < this.room.playerCount; i++) {
      if (!state.players[i]) state.players[i] = { name: `Player ${i + 1}`, clientId: null, score: 0, tiles: 0, color: COLORS[i] };
      const seat = this.room.seats[i];
      state.players[i].clientId = seat?.clientId || null;
      if (seat?.name) state.players[i].name = seat.name;
      if (!state.players[i].color) state.players[i].color = COLORS[i];
    }
    return state;
  }

  send(session, obj) {
    try { session.ws.send(JSON.stringify({ server: true, time: Date.now(), ...obj })); } catch {}
  }

  broadcast(obj, exceptSid = '') {
    const msg = JSON.stringify({ server: true, time: Date.now(), roomHostId: this.roomHostId(), roomCreatedAt: this.room.createdAt, ...obj });
    for (const s of this.sessions.values()) {
      if (s.sid === exceptSid) continue;
      try { s.ws.send(msg); } catch {}
    }
  }

  sendSeatAssigned(session, reason = 'seat-assigned') {
    const state = this.room.state ? this.stampState(clone(this.room.state)) : null;
    this.send(session, {
      type: 'seatAssigned',
      roomId: 'english',
      roomHostId: this.roomHostId(),
      roomCreatedAt: this.room.createdAt,
      seatIndex: session.seatIndex,
      playerCount: this.room.playerCount,
      seats: (this.room.seats || []).map((s, i) => s ? { seatIndex: i, clientId: s.clientId, name: s.name } : null),
      state,
      needNewGame: !state && session.seatIndex === 0,
      reason
    });
  }

  canUpdate(session, msg) {
    if (session.seatIndex < 0) return { ok: false, reason: '観戦中の端末は操作できません。' };
    if (msg.type === 'englishNewGame') {
      return session.seatIndex === 0 ? { ok: true } : { ok: false, reason: '新規ゲームはP1だけです。' };
    }
    if (!this.room.state) {
      return session.seatIndex === 0 ? { ok: true } : { ok: false, reason: 'P1の新規ゲーム開始待ちです。' };
    }
    if (this.room.state.gameOver) {
      return { ok: false, reason: 'ゲーム終了済みです。新規ゲームで再開してください。' };
    }
    const turn = Number(this.room.state.turn || 0) % normalizePlayerCount(this.room.state.playerCount || this.room.playerCount);
    if (session.seatIndex !== turn) {
      return { ok: false, reason: `ちょっと待って。今はP${turn + 1}のターンです。あなたはP${session.seatIndex + 1}です。` };
    }
    return { ok: true };
  }

  async onMessage(session, raw) {
    let msg;
    try { msg = typeof raw === 'string' ? JSON.parse(raw) : JSON.parse(new TextDecoder().decode(raw)); } catch { return; }
    if (!msg || typeof msg !== 'object') return;
    if (msg.clientId && !session.clientId) session.clientId = String(msg.clientId).slice(0, 80);
    if (msg.name) session.name = safeName(msg.name);
    if (msg.playerCount) this.room.playerCount = normalizePlayerCount(msg.playerCount);

    if (!session.clientId) return;
    if (session.seatIndex == null || session.seatIndex < 0 || this.seatIndexForClient(session.clientId) < 0) {
      this.assignSeat(session);
      this.sendSeatAssigned(session, 'join-order');
      this.broadcast({ type: 'roomPresence', seats: (this.room.seats || []).map((s, i) => s ? { seatIndex: i, clientId: s.clientId, name: s.name } : null) }, session.sid);
      await this.saveRoom();
    }

    if (msg.type === 'ping') { this.send(session, { type: 'pong' }); return; }
    if (msg.type === 'englishJoin' || msg.type === 'join' || msg.type === 'englishHello' || msg.type === 'englishSeatRequest') {
      this.sendSeatAssigned(session, msg.type);
      return;
    }
    if (msg.state && (msg.type === 'englishNewGame' || msg.type === 'englishState' || msg.type === 'englishPlace')) {
      const allowed = this.canUpdate(session, msg);
      if (!allowed.ok) {
        this.send(session, { type: 'actionRejected', reason: allowed.reason, seatIndex: session.seatIndex });
        if (this.room.state) this.send(session, { type: 'englishState', reason: 'authoritative-resync', state: this.stampState(clone(this.room.state)) });
        return;
      }
      this.room.updateSeq++;
      this.room.state = this.stampState(clone(msg.state));
      await this.saveRoom();
      this.broadcast({ type: 'englishState', reason: msg.reason || msg.type, state: this.stampState(clone(this.room.state)) });
    }
  }
}
