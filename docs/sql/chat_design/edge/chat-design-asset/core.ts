// Núcleo testável da função chat-design-asset: entrega os BYTES de um logo de cliente ao chat, sem criar URL assinada.
// Regras: método POST; chave própria em tempo constante; caminho validado e conferido na view de logos (só cliente elegível);
// só PNG/JPEG/WEBP pela assinatura dos bytes (SVG recusado); até 10 MiB; nenhum log com caminho nem conteúdo.
export const MAX_BYTES = 10 * 1024 * 1024;
export const PATH_RE = /^[0-9a-fA-F-]{36}\/[A-Za-z0-9_./-]+$/;

export interface Deps {
  secretSha256: string; // SHA-256 (hex) da chave; o projeto está no limite de 100 segredos, então a função guarda só o hash, nunca a chave
  isListed: (path: string) => Promise<boolean>;           // consulta chat_design.vw_chat_logos_cliente
  download: (path: string) => Promise<Uint8Array | null>; // bucket onboarding-identity, com service_role (a chave nunca sai daqui)
  now?: () => number;
}

export function sniff(b: Uint8Array): string | null {
  const eq = (o: number, s: number[]) => s.every((v, i) => b[o + i] === v);
  if (b.length >= 8 && eq(0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (b.length >= 3 && eq(0, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (b.length >= 12 && eq(0, [0x52, 0x49, 0x46, 0x46]) && eq(8, [0x57, 0x45, 0x42, 0x50])) return "image/webp";
  return null;
}

function safeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a), eb = new TextEncoder().encode(b);
  let d = ea.length ^ eb.length;
  for (let i = 0; i < Math.max(ea.length, eb.length); i++) d |= (ea[i % (ea.length || 1)] ?? 0) ^ (eb[i % (eb.length || 1)] ?? 0);
  return d === 0;
}

export async function sha256hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const hits: number[] = []; // limite simples por instância: 60 pedidos por minuto
const resp = (status: number, msg: string) => new Response(JSON.stringify({ error: msg }), { status, headers: { "content-type": "application/json" } });

export async function handle(req: Request, deps: Deps): Promise<Response> {
  if (req.method !== "POST") return resp(405, "método não permitido");
  if (!/^[0-9a-f]{64}$/.test(deps.secretSha256)) return resp(503, "indisponível"); // sem hash válido configurado, nunca atende
  const got = req.headers.get("x-chat-design-key") ?? "";
  if (got.length < 24 || !safeEqual(await sha256hex(got), deps.secretSha256)) return resp(401, "não autorizado");
  const t = (deps.now ?? Date.now)();
  while (hits.length && t - hits[0] > 60_000) hits.shift();
  if (hits.length >= 60) return resp(429, "muitas requisições");
  hits.push(t);
  let path = "";
  try {
    const body = await req.json();
    path = typeof body?.storage_path === "string" ? body.storage_path : "";
  } catch { return resp(400, "pedido inválido"); }
  if (!PATH_RE.test(path) || path.includes("..")) return resp(400, "caminho inválido");
  if (!(await deps.isListed(path))) return resp(404, "não encontrado"); // fora da view = cliente não elegível ou arquivo que o chat não pode listar
  const bytes = await deps.download(path);
  if (!bytes) return resp(404, "não encontrado");
  if (bytes.length > MAX_BYTES) return resp(413, "arquivo grande demais");
  const mime = sniff(bytes);
  if (!mime) return resp(415, "tipo não permitido");
  return new Response(new Uint8Array(bytes).buffer as ArrayBuffer, { status: 200, headers: { "content-type": mime, "cache-control": "no-store", "x-content-type-options": "nosniff" } });
}
