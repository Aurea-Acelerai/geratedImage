// Sem dependência de rede: o assertEquals é local (compara por JSON; Uint8Array vira lista).
function assertEquals(a: unknown, b: unknown, msg = "") {
  const j = (x: unknown) => JSON.stringify(x instanceof Uint8Array ? [...x] : x);
  if (j(a) !== j(b)) throw new Error(`${msg} esperado ${j(b)} obtido ${j(a)}`);
}
import { handle, MAX_BYTES, sha256hex, sniff } from "./core.ts";
const KEY = "chave-de-teste-com-mais-de-24-caracteres";
const ID = "c0000000-0000-0000-0000-00000000000a", P = `${ID}/logo.png`;
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3]);
const HASH = await sha256hex(KEY);
const mk = (o: Partial<Parameters<typeof handle>[1]> = {}) => ({ secretSha256: HASH, isListed: async (p: string) => p === P, download: async () => PNG, ...o });
const req = (body: unknown, key: string | null = KEY, method = "POST") =>
  new Request("https://x.test/", { method, headers: key === null ? {} : { "x-chat-design-key": key }, body: method === "POST" ? JSON.stringify(body) : undefined });

Deno.test("entrega os bytes de um logo listado, com o tipo pela assinatura e sem cache", async () => {
  const r = await handle(req({ storage_path: P }), mk());
  assertEquals(r.status, 200); assertEquals(r.headers.get("content-type"), "image/png"); assertEquals(r.headers.get("cache-control"), "no-store");
  assertEquals(new Uint8Array(await r.arrayBuffer()), PNG);
});
Deno.test("sem chave, chave errada ou segredo fraco: nunca entrega nem consulta", async () => {
  let consultas = 0; const d = mk({ isListed: async () => { consultas++; return true; } });
  assertEquals((await handle(req({ storage_path: P }, null), d)).status, 401);
  assertEquals((await handle(req({ storage_path: P }, "errada"), d)).status, 401);
  assertEquals((await handle(req({ storage_path: P }, KEY + "x"), d)).status, 401);
  assertEquals((await handle(req({ storage_path: P }), { ...d, secretSha256: "" })).status, 503);
  assertEquals((await handle(req({ storage_path: P }), { ...d, secretSha256: "abc" })).status, 503);
  assertEquals((await handle(req({ storage_path: P }, HASH), d)).status, 401); // o próprio hash NÃO serve como chave
  assertEquals((await handle(req({ storage_path: P }, "curta"), d)).status, 401);
  assertEquals(consultas, 0);
});
Deno.test("só POST", async () => { assertEquals((await handle(req(null, KEY, "GET"), mk())).status, 405); });
Deno.test("caminhos inválidos: .., absoluto, sem uuid, bucket injetado, tipo errado", async () => {
  let consultas = 0; const d = mk({ isListed: async () => { consultas++; return true; } });
  for (const p of [`${ID}/../x.png`, "/etc/passwd", "logo.png", `${ID}/a b.png`, `${ID}\\x.png`, "http://evil/x.png", 5, null, ""])
    assertEquals((await handle(req({ storage_path: p }), d)).status, 400, String(p));
  assertEquals((await handle(new Request("https://x.test/", { method: "POST", headers: { "x-chat-design-key": KEY }, body: "{lixo" }), d)).status, 400);
  assertEquals(consultas, 0);
});
Deno.test("arquivo fora da view (cliente não elegível) = 404 sem baixar nada", async () => {
  let baixou = false;
  const r = await handle(req({ storage_path: `${ID}/outro.png` }), mk({ download: async () => { baixou = true; return PNG; } }));
  assertEquals(r.status, 404); assertEquals(baixou, false);
});
Deno.test("SVG, HTML e arquivo vazio são recusados pela assinatura; tamanho acima de 10 MiB também", async () => {
  const svg = new TextEncoder().encode("<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>");
  assertEquals((await handle(req({ storage_path: P }), mk({ download: async () => svg }))).status, 415);
  assertEquals((await handle(req({ storage_path: P }), mk({ download: async () => new Uint8Array() }))).status, 415);
  assertEquals((await handle(req({ storage_path: P }), mk({ download: async () => new Uint8Array(MAX_BYTES + 1).fill(1) }))).status, 413);
  assertEquals((await handle(req({ storage_path: P }), mk({ download: async () => null }))).status, 404);
});
Deno.test("assinaturas: png, jpeg, webp; extensão não engana", () => {
  assertEquals(sniff(PNG), "image/png"); assertEquals(sniff(new Uint8Array([0xff, 0xd8, 0xff, 0xe0])), "image/jpeg");
  assertEquals(sniff(new TextEncoder().encode("RIFF\0\0\0\0WEBPVP8 ")), "image/webp"); assertEquals(sniff(new TextEncoder().encode("GIF89a....")), null);
});
Deno.test("limite de 60 pedidos por minuto", async () => {
  const d = mk({ now: () => 1_000_000 }); let last = 0;
  for (let i = 0; i < 70; i++) last = (await handle(req({ storage_path: P }), d)).status;
  assertEquals(last, 429);
});
