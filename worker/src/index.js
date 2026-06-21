export class Room {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.sockets = new Set();
  }

  async fetch(request) {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("WebSocket only", { status: 400 });
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];

    server.accept();
    this.sockets.add(server);

    server.send(JSON.stringify({
      type: "welcome",
      message: "connected to room"
    }));

    server.addEventListener("message", (event) => {
      const data = event.data;

      for (const socket of this.sockets) {
        if (socket !== server) {
          try {
            socket.send(data);
          } catch (e) {
            this.sockets.delete(socket);
          }
        }
      }
    });

    const cleanup = () => {
      this.sockets.delete(server);
    };

    server.addEventListener("close", cleanup);
    server.addEventListener("error", cleanup);

    return new Response(null, {
      status: 101,
      webSocket: client
    });
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/") {
      return new Response("mine-server-git2 WebSocket server OK", {
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "access-control-allow-origin": "*"
        }
      });
    }

    if (url.pathname.startsWith("/room/")) {
      const roomName = url.pathname.split("/room/")[1] || "main";
      const id = env.ROOM.idFromName(roomName);
      const room = env.ROOM.get(id);
      return room.fetch(request);
    }

    return new Response("Not found", { status: 404 });
  }
};
