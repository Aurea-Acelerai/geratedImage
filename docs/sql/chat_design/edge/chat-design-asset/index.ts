// Entrada da Edge Function (deploy: supabase functions deploy chat-design-asset --no-verify-jwt; a autenticação é a chave própria).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";
import { Pool } from "https://deno.land/x/postgres@v0.19.3/mod.ts";
import { handle } from "./core.ts";

const pool = new Pool(Deno.env.get("SUPABASE_DB_URL")!, 2, true);
const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

// O hash da chave vem de key_hash.ts (gerado no deploy, fora do repositório) ou da variável CHAT_DESIGN_ASSET_KEY_SHA256.
let secretSha256 = Deno.env.get("CHAT_DESIGN_ASSET_KEY_SHA256") ?? "";
if (!secretSha256) { try { secretSha256 = (await import("./key_hash.ts")).KEY_SHA256; } catch { /* sem hash: a função responde 503 */ } }

Deno.serve((req) => handle(req, {
  secretSha256,
  isListed: async (path) => {
    const c = await pool.connect();
    try {
      const r = await c.queryArray("select 1 from chat_design.vw_chat_logos_cliente where storage_bucket = 'onboarding-identity' and storage_path = $1 limit 1", [path]);
      return r.rows.length > 0;
    } finally { c.release(); }
  },
  download: async (path) => {
    const { data, error } = await sb.storage.from("onboarding-identity").download(path);
    if (error || !data) return null;
    return new Uint8Array(await data.arrayBuffer());
  },
}));
