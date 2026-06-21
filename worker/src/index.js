export default {
  async fetch(request, env, ctx) {
    return new Response("mine-server OK", {
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "access-control-allow-origin": "*"
      }
    });
  }
};
