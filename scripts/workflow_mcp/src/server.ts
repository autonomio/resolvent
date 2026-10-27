import { McpServer, createMcpHandler } from "@modelcontextprotocol/server";
import { z } from "zod";
import { compatibility, loadWorkflow, manifestSchema } from "./workflow.ts";

function createServer() {
  const server = new McpServer({ name: "resolvent-workflows", version: "1.0.0" });
  server.registerTool("get_resolvent_workflow", {
    description: "Retrieve the current public Resolvent workflow, verified against its pinned Git revision, byte sizes, SHA-256 and Git blob identities. Use when refreshing Resolvent guidance. No repository, question or conversation content is accepted. This tool cannot read or write a world model.",
    inputSchema: z.object({}).strict(),
    outputSchema: z.object({ manifest: manifestSchema, files: z.record(z.string(), z.string()) }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  }, async () => {
    try {
      const packet = await loadWorkflow();
      return { content: [{ type: "text", text: JSON.stringify(packet) }], structuredContent: packet };
    } catch {
      return { content: [{ type: "text", text: "The current public workflow could not be retrieved and verified. No world-model operation was performed. Try the installed direct GitHub verification route or retry later; do not treat stale or unverified guidance as current." }], isError: true };
    }
  });
  const protocolVersion = z.string().max(20).regex(/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/);
  server.registerTool("check_resolvent_compatibility", {
    description: "Compare the installed Resolvent client protocol and a world's declared submission-protocol version with this verifier's supported versions. Send only version numbers. This does not inspect a repository, validate claims, grant access, upgrade governance or write data.",
    inputSchema: z.object({ client_protocol: protocolVersion, world_submission_protocol: protocolVersion }).strict(),
    outputSchema: z.object({
      client_protocol: z.string(), world_submission_protocol: z.string(),
      client_compatible: z.boolean(), world_protocol_supported: z.boolean(),
      supported_client_protocol: z.string(), supported_world_submission_protocols: z.array(z.string()),
      limitation: z.string(),
    }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async ({ client_protocol, world_submission_protocol }) => {
    const result = compatibility(client_protocol, world_submission_protocol);
    return { content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result };
  });
  return server;
}

const handler = createMcpHandler(createServer, {
  maxRequestBodySize: 4096,
});
export async function mcpResponse(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (path === "/health" && request.method === "GET") return Response.json({ status: "ok", service: "resolvent-workflows", version: "1.0.0" });
    if (path !== "/mcp") return new Response("Not found", { status: 404 });
    if (request.headers.has("authorization")) return new Response("This public service requires no credentials. Do not send tokens.", { status: 400 });
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, Accept, MCP-Protocol-Version" } });
    const response = await handler.fetch(request);
    const headers = new Headers(response.headers);
    headers.set("Access-Control-Allow-Origin", "*");
    return new Response(response.body, { status: response.status, headers });
}
