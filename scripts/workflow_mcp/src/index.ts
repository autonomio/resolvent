import { hostHeaderValidationResponse } from "@modelcontextprotocol/server";
import { mcpResponse } from "./server.ts";
import { publicPage } from "./pages.ts";

export default {
  async fetch(request, env) {
    const invalidHost = hostHeaderValidationResponse(request, [env.PUBLIC_HOSTNAME, env.WORKERS_DEV_HOSTNAME, "localhost", "127.0.0.1"]);
    if (invalidHost) return invalidHost;
    const path = new URL(request.url).pathname;
    if (path === "/.well-known/openai-apps-challenge") {
      const challenge = "OPENAI_PLUGIN_CHALLENGE" in env ? env.OPENAI_PLUGIN_CHALLENGE : undefined;
      if (request.method !== "GET" || typeof challenge !== "string" || !challenge) return new Response("Not found", { status: 404 });
      return new Response(challenge, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }
    return publicPage(path, request.method) ?? mcpResponse(request);
  },
} satisfies ExportedHandler<Env>;
