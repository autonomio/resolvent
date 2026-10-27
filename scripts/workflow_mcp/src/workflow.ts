import { z } from "zod";

export const SOURCE = "https://raw.githubusercontent.com/autonomio/resolvent/";
export const INDEX = SOURCE + "workflow-release/workflow.json";
export const CLIENT_PROTOCOL = "1.0";
export const WORLD_PROTOCOLS = ["1.0", "1.1", "1.2"] as const;
const MAX_INDEX = 65_536;
const MAX_FILE = 262_144;
const MAX_TOTAL = 1_048_576;
const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const encoder = new TextEncoder();

const fileRecord = z.object({
  size: z.number().int().positive().max(MAX_FILE),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  git_blob_sha1: z.string().regex(/^[0-9a-f]{40}$/),
}).strict();

export const manifestSchema = z.object({
  format_version: z.literal("1.0"),
  client_protocol: z.literal(CLIENT_PROTOCOL),
  workflow_version: z.string().regex(/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/),
  source_commit: z.string().regex(/^[0-9a-f]{40}$/),
  entrypoint: z.string(),
  files: z.record(z.string(), fileRecord),
}).strict().superRefine((value, ctx) => {
  const files = Object.entries(value.files);
  if (files.length < 1 || files.length > 32 || files.reduce((n, [, r]) => n + r.size, 0) > MAX_TOTAL)
    ctx.addIssue({ code: "custom", message: "Workflow inventory exceeds bounds" });
  for (const [path] of files) {
    if (path.length > 200 || !/^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_.-]+)*\.(md|json)$/.test(path) ||
        path.split("/").some(p => p === "." || p === ".."))
      ctx.addIssue({ code: "custom", message: "Unsafe workflow path" });
  }
  if (!Object.hasOwn(value.files, value.entrypoint) || !value.entrypoint.endsWith(".md"))
    ctx.addIssue({ code: "custom", message: "Missing workflow entrypoint" });
});

export type Manifest = z.infer<typeof manifestSchema>;

// JSON.parse validates grammar; this pass also rejects duplicate keys, including
// escaped spellings. Strings are skipped so braces in content remain data.
export function parseJson(text: string): unknown {
  const value: unknown = JSON.parse(text);
  const stack: (Set<string> | null)[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '"') {
      const start = i++;
      while (text[i] !== '"') { if (text[i] === "\\") i++; i++; }
      let next = i + 1;
      while (/\s/.test(text[next] ?? "x")) next++;
      if (text[next] === ":") {
        const key: string = JSON.parse(text.slice(start, i + 1));
        const keys = stack.at(-1);
        if (!keys || keys.has(key)) throw new Error("Duplicate manifest member");
        keys.add(key);
      }
    } else if (text[i] === "{") stack.push(new Set());
    else if (text[i] === "[") stack.push(null);
    else if (text[i] === "}" || text[i] === "]") stack.pop();
  }
  return value;
}

export async function boundedBytes(response: Response, limit: number): Promise<Uint8Array<ArrayBuffer>> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Empty response");
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) { await reader.cancel(); throw new Error("Response exceeds size limit"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}

export async function readPublic(url: string, limit: number): Promise<Uint8Array<ArrayBuffer>> {
  const response = await fetch(url, {
    redirect: "manual", signal: AbortSignal.timeout(15_000),
    headers: { "User-Agent": "Resolvent-workflow-MCP/1.0" },
  });
  if (!response.ok) throw new Error("Public workflow unavailable");
  return boundedBytes(response, limit);
}

export type Reader = typeof readPublic;
export async function loadManifest(reader: Reader = readPublic): Promise<Manifest> {
  const bytes = await reader(INDEX, MAX_INDEX);
  if (!bytes.length || bytes.length > MAX_INDEX) throw new Error("Invalid manifest size");
  return manifestSchema.parse(parseJson(decoder.decode(bytes)));
}

async function digest(algorithm: string, bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest(algorithm, bytes)), b => b.toString(16).padStart(2, "0")).join("");
}

export async function loadWorkflow(reader: Reader = readPublic) {
  const manifest = await loadManifest(reader);
  const files: Record<string, string> = Object.create(null);
  for (const [path, record] of Object.entries(manifest.files).sort(([a], [b]) => a.localeCompare(b))) {
    const bytes = await reader(SOURCE + manifest.source_commit + "/workflows/resolvent/" + path, record.size);
    const header = encoder.encode("blob " + bytes.length + "\0");
    const blob = new Uint8Array(header.length + bytes.length);
    blob.set(header); blob.set(bytes, header.length);
    if (bytes.length !== record.size || await digest("SHA-256", bytes) !== record.sha256 ||
        await digest("SHA-1", blob) !== record.git_blob_sha1)
      throw new Error("Workflow content does not match its manifest");
    files[path] = decoder.decode(bytes);
  }
  return { manifest, files };
}

export function compatibility(clientProtocol: string, worldProtocol: string) {
  return {
    client_protocol: clientProtocol, world_submission_protocol: worldProtocol,
    client_compatible: clientProtocol === CLIENT_PROTOCOL,
    world_protocol_supported: (WORLD_PROTOCOLS as readonly string[]).includes(worldProtocol),
    supported_client_protocol: CLIENT_PROTOCOL,
    supported_world_submission_protocols: WORLD_PROTOCOLS,
    limitation: "Version compatibility does not verify repository access, adoption, governance or model integrity. The selected world's approved contracts remain authoritative.",
  };
}
