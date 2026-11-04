#!/usr/bin/env python3
"""Benchmark versionado do harness de imagens: validação, execução, checagens automáticas, comparação cega e relatório.
Só stdlib (usa provider.py e ocr.py do repositório). Casos em bench/dev.json (desenvolvimento) e bench/final.json
(avaliação final, travado por bench/LOCK.json).

  python3 test/bench.py validate
  python3 test/bench.py lock --reason "texto"
  python3 test/bench.py run --split dev --generate fake
  python3 test/bench.py run --split dev --generate openai --max-calls 5 --i-approve-paid-calls
  python3 test/bench.py check --run RUN
  python3 test/bench.py blind-pack --a RUN_A --b RUN_B --seed 7
  python3 test/bench.py blind-score --ratings ratings.csv --key key.json
  python3 test/bench.py report --run RUN [--ratings ratings.csv --key key.json]

Regras que este módulo faz cumprir:
- Dev x final: resultados do final NÃO servem para ajustar prompts, regras nem modelo. O final só roda com
  --confirm-final, cada uso é registrado em bench/final_runs.jsonl e o conteúdo é travado por hash (LOCK.json).
- Nenhuma chamada paga sem --max-calls >= 1, --i-approve-paid-calls e OPENAI_API_KEY; o orçamento é um Budget do
  provider (cada tentativa HTTP conta) e o que sobra sem rodar é registrado (budget_exhausted).
- Nada vira "passou" sem evidência: critérios humanos ficam pending_human; OCR indisponível fica not_verified;
  preservação de pixels fica not_implemented.
- Sem baseline externo legítimo com avaliação cega, o relatório diz "paridade ainda não demonstrada".

Limites conhecidos: ver bench/README.md (o `run --generate openai` chama o adapter de imagens com o brief literal; o
Runner e o briefing do harness NÃO estão no caminho).
"""
import argparse, csv, datetime, hashlib, json, os, random, re, struct, sys, time, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:  # `python3 -I` não põe a pasta do script no caminho
    sys.path.insert(0, str(HERE))
import ocr  # noqa: E402
import provider  # noqa: E402

CATEGORIES = [
    "fotografia", "ilustração", "cena complexa", "texto em português", "produto", "personagem recorrente",
    "edição local", "troca de fundo", "preservação de identidade", "múltiplas referências", "peça de marketing",
    "diagrama com dados fornecidos pelo usuário", "pedido ambíguo", "caso de falha esperada",
]
ROLES = ("identidade", "estilo", "logo", "base", "produto", "dados")
CHECKS = ("human", "auto:size", "auto:ocr", "auto:preservation")
SIZES = ("1024x1024", "1536x1024", "1024x1536", "auto")
SPLITS = ("dev", "final")
DIFFICULTIES = ("baixa", "media", "alta")
REQUIRED_KEYS = ("id", "split", "category", "brief", "references", "required_criteria", "preservation", "text_literals", "expected_size", "eval_method")
OPTIONAL_KEYS = ("difficulty", "notes", "known_failure_mode")
# categorias que exigem imagem de entrada do usuário e uma lista do que não pode mudar
NEEDS_INPUT = {"edição local": {"base"}, "troca de fundo": {"base"}, "preservação de identidade": {"identidade", "base"}}
MIN_DEV, MIN_FINAL, MIN_FINAL_CATEGORIES = 14, 6, 5
NEAR_DUPLICATE = 0.5  # similaridade de palavras entre um caso de dev e um de final a partir da qual são "quase iguais"
REF_EXTS = ("png", "jpg", "jpeg", "webp")
ID_RE = re.compile(r"^(dev|final)-[a-z0-9]+(-[a-z0-9]+)*-\d\d$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DEFAULT_RULE = ("bench/final.json só muda de propósito: depois de alterar, rode `bench.py lock --reason \"...\"`, que regrava o hash e "
                "anexa data e razão em history. Resultados do final nunca são usados para ajustar prompts, regras ou modelo.")
FINAL_WARNING = ("AVISO: resultados do conjunto FINAL NÃO podem ser usados para ajustar prompts, regras nem modelo. "
                 "Este uso será registrado em bench/final_runs.jsonl.")
DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"
PARITY_PHRASE = "paridade ainda não demonstrada"


class BenchError(Exception):
    """Falha de uso ou de dados, com mensagem clara. A CLI sai com código 2."""


class Paths:
    """Todos os caminhos configuráveis, para os testes nunca tocarem em bench/ nem em test/bench_out/."""

    def __init__(self, bench_dir=None, out_root=None, final_runs=None, refs_dir=None):
        self.bench = Path(bench_dir) if bench_dir else ROOT / "bench"
        self.dev, self.final, self.lock = self.bench / "dev.json", self.bench / "final.json", self.bench / "LOCK.json"
        self.refs = Path(refs_dir) if refs_dir else self.bench / "refs"
        self.out_root = Path(out_root) if out_root else HERE / "bench_out"
        self.final_runs = Path(final_runs) if final_runs else Path(os.environ.get("BENCH_FINAL_RUNS") or self.bench / "final_runs.jsonl")

    def split_file(self, split):
        return self.dev if split == "dev" else self.final


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def benchmark_version(paths):
    """Versão do benchmark = hashes do conteúdo exato dos dois arquivos (None se o arquivo não existe)."""
    return {"dev_sha256": sha256_file(paths.dev) if paths.dev.exists() else None,
            "final_sha256": sha256_file(paths.final) if paths.final.exists() else None}


# ------------------------------------------------------------------ validação


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def validate_case(c, split, label):
    """Todos os problemas de um caso (lista vazia = ok). `split` é o split do arquivo onde o caso está."""
    if not isinstance(c, dict):
        return [f"{label}: o caso deve ser um objeto"]
    p = []
    ident = c.get("id")
    label = ident if _s(ident) else label
    for k in REQUIRED_KEYS:
        if k not in c:
            p.append(f"{label}: campo obrigatório ausente: {k}")
    for k in c:
        if k not in REQUIRED_KEYS and k not in OPTIONAL_KEYS:
            p.append(f"{label}: campo desconhecido: {k}")
    if "id" in c and not (_s(ident) and ID_RE.match(ident)):
        p.append(f"{label}: id inválido {ident!r} (esperado, por exemplo, dev-foto-01)")
    elif _s(ident) and not ident.startswith(split + "-"):
        p.append(f"{label}: id deve começar com '{split}-' neste arquivo")
    if "split" in c and c["split"] not in SPLITS:
        p.append(f"{label}: split inválido {c['split']!r}")
    elif "split" in c and c["split"] != split:
        p.append(f"{label}: split '{c['split']}' no arquivo do split '{split}'")
    cat = c.get("category")
    if "category" in c and cat not in CATEGORIES:
        p.append(f"{label}: categoria desconhecida {cat!r}")
    if "brief" in c and not (_s(c["brief"]) and len(c["brief"].strip()) >= 20):
        p.append(f"{label}: brief vazio ou curto demais (mínimo 20 caracteres)")
    if "expected_size" in c and c["expected_size"] not in SIZES:
        p.append(f"{label}: expected_size inválido {c['expected_size']!r} (use {', '.join(SIZES)})")
    if "eval_method" in c and not _s(c["eval_method"]):
        p.append(f"{label}: eval_method vazio")
    if "difficulty" in c and c["difficulty"] not in DIFFICULTIES:
        p.append(f"{label}: difficulty inválida {c['difficulty']!r}")
    for k in ("notes", "known_failure_mode"):
        if k in c and not _s(c[k]):
            p.append(f"{label}: {k} vazio")
    refs = c.get("references")
    roles = set()
    if "references" in c:
        if not isinstance(refs, list):
            p.append(f"{label}: references deve ser uma lista")
        else:
            seen = set()
            for i, r in enumerate(refs):
                where = f"{label}: references[{i}]"
                if not isinstance(r, dict):
                    p.append(f"{where} deve ser um objeto")
                    continue
                extra = set(r) - {"id", "role", "description", "user_supplied"}
                miss = {"id", "role", "description", "user_supplied"} - set(r)
                if extra or miss:
                    p.append(f"{where}: campos incorretos (sobra {sorted(extra)}, falta {sorted(miss)})")
                if "id" in r and not (_s(r["id"]) and SLUG_RE.match(r["id"])):
                    p.append(f"{where}: id inválido {r['id']!r} (use minúsculas, números e hífen)")
                elif r.get("id") in seen:
                    p.append(f"{where}: id de referência repetido {r['id']!r}")
                seen.add(r.get("id"))
                if "role" in r and r["role"] not in ROLES:
                    p.append(f"{where}: role inválido {r['role']!r} (use {', '.join(ROLES)})")
                else:
                    roles.add(r.get("role"))
                if "description" in r and not _s(r["description"]):
                    p.append(f"{where}: description vazia")
                if "user_supplied" in r and not isinstance(r["user_supplied"], bool):
                    p.append(f"{where}: user_supplied deve ser true ou false")
    crit = c.get("required_criteria")
    checks = set()
    if "required_criteria" in c:
        if not isinstance(crit, list) or not crit:
            p.append(f"{label}: required_criteria deve ser uma lista não vazia")
        else:
            seen = set()
            for i, k in enumerate(crit):
                where = f"{label}: required_criteria[{i}]"
                if not isinstance(k, dict) or set(k) != {"id", "text", "check"}:
                    p.append(f"{where}: esperado objeto com id, text e check")
                    continue
                if not (_s(k["id"]) and SLUG_RE.match(k["id"])):
                    p.append(f"{where}: id inválido {k['id']!r}")
                elif k["id"] in seen:
                    p.append(f"{where}: id de critério repetido {k['id']!r}")
                seen.add(k["id"])
                if not _s(k["text"]):
                    p.append(f"{where}: text vazio")
                if k["check"] not in CHECKS:
                    p.append(f"{where}: check inválido {k['check']!r} (use {', '.join(CHECKS)})")
                else:
                    checks.add(k["check"])
    pres, lits = c.get("preservation"), c.get("text_literals")
    for name, val in (("preservation", pres), ("text_literals", lits)):
        if name in c and not (isinstance(val, list) and all(_s(x) for x in val)):
            p.append(f"{label}: {name} deve ser uma lista de textos não vazios")
    pres_ok = isinstance(pres, list) and all(_s(x) for x in pres)
    lits_ok = isinstance(lits, list) and all(_s(x) for x in lits)
    # regras entre campos
    if "auto:ocr" in checks and lits_ok and not lits:
        p.append(f"{label}: critério auto:ocr sem text_literals")
    if lits_ok and lits and "auto:ocr" not in checks and "required_criteria" in c and isinstance(crit, list):
        p.append(f"{label}: text_literals preenchido exige um critério auto:ocr")
    if "auto:preservation" in checks and pres_ok and not pres:
        p.append(f"{label}: critério auto:preservation sem itens em preservation")
    if "auto:size" in checks and c.get("expected_size") == "auto":
        p.append(f"{label}: critério auto:size exige expected_size explícito (não 'auto')")
    if cat in NEEDS_INPUT:
        if not (roles & NEEDS_INPUT[cat]):
            p.append(f"{label}: categoria '{cat}' exige referência com role {' ou '.join(sorted(NEEDS_INPUT[cat]))}")
        if pres_ok and not pres:
            p.append(f"{label}: categoria '{cat}' exige preservation não vazio")
    if cat == "múltiplas referências" and isinstance(refs, list) and len(refs) < 2:
        p.append(f"{label}: 'múltiplas referências' exige pelo menos 2 referências")
    if cat == "caso de falha esperada" and "known_failure_mode" not in c:
        p.append(f"{label}: 'caso de falha esperada' exige known_failure_mode")
    if cat == "pedido ambíguo" and isinstance(crit, list) and not any(isinstance(k, dict) and k.get("check") == "human" for k in crit):
        p.append(f"{label}: 'pedido ambíguo' exige critério human de esclarecimento ou suposição declarada")
    return p


def _words(text):
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= 4}


def similarity(a, b):
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def _load_cases(path, split, problems):
    if not path.exists():
        problems.append(f"{path.name}: arquivo não existe")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        problems.append(f"{path.name}: JSON inválido ({e})")
        return []
    if not isinstance(data, list):
        problems.append(f"{path.name}: deve conter uma lista de casos")
        return []
    return data


def check_lock(paths):
    """Problemas do lock do final (lista vazia = o final é exatamente o que foi travado)."""
    if not paths.final.exists():
        return []  # já reportado como arquivo ausente
    if not paths.lock.exists():
        return [f"{paths.lock.name}: arquivo não existe (rode `bench.py lock --reason \"...\"`)"]
    try:
        lock = json.loads(paths.lock.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return [f"{paths.lock.name}: JSON inválido ({e})"]
    want = lock.get("final_sha256") if isinstance(lock, dict) else None
    if not (isinstance(want, str) and re.fullmatch(r"[0-9a-f]{64}", want)):
        return [f"{paths.lock.name}: final_sha256 ausente ou inválido"]
    got = sha256_file(paths.final)
    if got != want:
        return [f"final.json mudou desde o lock (sha256 atual {got[:12]}..., travado {want[:12]}...). Se foi de propósito, rode "
                f"`bench.py lock --reason \"...\"`; senão, restaure o arquivo. Resultados do final não servem para ajustar prompts."]
    return []


def validate_all(paths, lock=True):
    """(problemas, casos_por_split). Junta TODOS os problemas: esquema, ids únicos, splits, cobertura, quase duplicatas, lock."""
    problems, cases = [], {}
    for split in SPLITS:
        raw = _load_cases(paths.split_file(split), split, problems)
        cases[split] = raw
        for i, c in enumerate(raw):
            problems += validate_case(c, split, f"{paths.split_file(split).name}[{i}]")
    seen = {}
    for split in SPLITS:
        for c in cases[split]:
            cid = c.get("id") if isinstance(c, dict) else None
            if _s(cid):
                if cid in seen:
                    problems.append(f"id repetido: {cid} (em {seen[cid]} e {split}.json)")
                seen[cid] = f"{split}.json"
    if len(cases["dev"]) < MIN_DEV:
        problems.append(f"dev.json tem {len(cases['dev'])} casos (mínimo {MIN_DEV})")
    if len(cases["final"]) < MIN_FINAL:
        problems.append(f"final.json tem {len(cases['final'])} casos (mínimo {MIN_FINAL})")
    allc = [c for s in SPLITS for c in cases[s] if isinstance(c, dict)]
    present = {c.get("category") for c in allc}
    for cat in CATEGORIES:
        if cat not in present:
            problems.append(f"categoria obrigatória sem nenhum caso: {cat}")
    final_cats = {c.get("category") for c in cases["final"] if isinstance(c, dict)}
    if cases["final"] and len(final_cats) < MIN_FINAL_CATEGORIES:
        problems.append(f"final.json tem só {len(final_cats)} categorias distintas (mínimo {MIN_FINAL_CATEGORIES}): o final precisa ser variado")
    for d in cases["dev"]:
        for f in cases["final"]:
            if isinstance(d, dict) and isinstance(f, dict) and _s(d.get("brief")) and _s(f.get("brief")):
                sim = similarity(d["brief"], f["brief"])
                if sim >= NEAR_DUPLICATE:
                    problems.append(f"{d.get('id')} (dev) e {f.get('id')} (final) são quase iguais (similaridade {sim:.2f}): o final existe para detectar sobreajuste")
    if lock:
        problems += check_lock(paths)
    return problems, cases


def cmd_validate(paths, out=print):
    problems, cases = validate_all(paths)
    if problems:
        out(f"INVÁLIDO: {len(problems)} problema(s)")
        for x in problems:
            out(f"  - {x}")
        return 1
    cats = {c["category"] for s in SPLITS for c in cases[s]}
    out(f"OK: {len(cases['dev'])} casos de dev, {len(cases['final'])} de final, {len(cats)}/{len(CATEGORIES)} categorias, lock do final confere")
    return 0


def do_lock(paths, reason, today=None):
    """Regrava o lock do final. Devolve (problemas, lock). Recusa razão vazia e final inválido."""
    if not _s(reason):
        raise BenchError("lock exige --reason com a razão da mudança do conjunto final")
    problems, _ = validate_all(paths, lock=False)
    if problems:
        return problems, None
    today = today or utcnow().strftime("%Y-%m-%d")
    old = {}
    if paths.lock.exists():
        try:
            old = json.loads(paths.lock.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            old = {}
    old = old if isinstance(old, dict) else {}
    sha = sha256_file(paths.final)
    history = old.get("history") if isinstance(old.get("history"), list) else []
    history = history + [{"date": today, "reason": reason.strip(), "final_sha256": sha, "previous_sha256": old.get("final_sha256")}]
    lock = {"final_sha256": sha, "locked_on": today, "rule": old.get("rule") or DEFAULT_RULE, "history": history}
    write_json(paths.lock, lock)
    return [], lock


def cmd_lock(paths, reason, today=None, out=print):
    problems, lock = do_lock(paths, reason, today)
    if problems:
        out("NÃO travei: final.json (ou dev.json) tem problemas:")
        for x in problems:
            out(f"  - {x}")
        return 1
    out(f"OK: lock regravado ({lock['final_sha256'][:12]}..., {lock['locked_on']}); history com {len(lock['history'])} entrada(s)")
    return 0


# ------------------------------------------------------------------ PNG (stdlib)


def png_dims(data):
    """(largura, altura) de um PNG, ou None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24 and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def fake_png(case_id, w, h):
    """PNG RGB determinístico (faixas horizontais cujas cores vêm do hash do id). Não contém texto nem desenho: serve só
    para exercitar o pipeline do benchmark, sem rede e sem custo."""
    d = hashlib.sha256(case_id.encode("utf-8")).digest()
    rows = []
    for y in range(h):
        band = y * 16 // h
        color = bytes((d[(band * 3) % 32], d[(band * 3 + 1) % 32], d[(band * 3 + 2) % 32]))
        rows.append(b"\x00" + color * w)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + _chunk(b"IEND", b""))


KEEP_CHUNKS = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND", b"sRGB", b"gAMA"}


def strip_png_metadata(data):
    """Remove blocos auxiliares (texto, EXIF, proveniência/C2PA, perfis) de um PNG; mantém os que definem a imagem.
    Devolve (bytes, removidos). Não-PNG volta intacto com None (metadados de JPEG/WebP NÃO são removidos)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data, None
    out, removed, i = [data[:8]], [], 8
    while i + 8 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        t = data[i + 4:i + 8]
        end = i + 12 + n
        if end > len(data):
            return data, None  # PNG truncado: não mexo
        (out.append(data[i:end]) if t in KEEP_CHUNKS else removed.append(t.decode("latin-1")))
        i = end
    return b"".join(out), removed


def sniff_ext(data):
    fmt = provider.sniff_format(data)
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(fmt)


# ------------------------------------------------------------------ execução


def _rel(path):
    """Caminho relativo à raiz do repositório quando possível (mensagens e relatórios não expõem pastas pessoais)."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def find_ref_files(paths, case):
    """({ref_id: arquivo}, [ref_id sem arquivo]) para as referências user_supplied em bench/refs/<caso>/<ref>.<ext>."""
    found, missing = {}, []
    for r in case["references"]:
        if not r["user_supplied"]:
            continue
        for ext in REF_EXTS:
            f = paths.refs / case["id"] / f"{r['id']}.{ext}"
            if f.is_file():
                found[r["id"]] = f
                break
        else:
            missing.append(r["id"])
    return found, missing


def read_final_runs(paths):
    if not paths.final_runs.exists():
        return []
    out = []
    for line in paths.final_runs.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def append_final_run(paths, record):
    paths.final_runs.parent.mkdir(parents=True, exist_ok=True)
    with open(paths.final_runs, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def default_client_factory(env, budget):
    """Cliente real do provider com o Budget do benchmark. Só é chamado depois de todas as exigências do run openai."""
    return provider.OpenAIImages(env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), env.get("OPENAI_API_KEY"), budgets=[budget])


def _size_for(case):
    w, h = ("1024", "1024") if case["expected_size"] == "auto" else case["expected_size"].split("x")
    return int(w), int(h)


def _openai_case(client, budget, case, ref_files, model, quality):
    """Uma chamada paga (com as repetições seguras do adapter). Devolve campos do resultado do caso."""
    inputs = []
    order = sorted(case["references"], key=lambda r: (r["role"] != "base", r["id"]))  # a base vai primeiro (a máscara vale para a primeira)
    for r in order:
        f = ref_files.get(r["id"])
        if f is None:
            continue
        data = f.read_bytes()
        fmt = provider.sniff_format(data)
        if not fmt:
            return {"status": "failed", "error": f"referência '{r['id']}' não é PNG, JPEG nem WebP", "attempts": 0, "paid_calls": 0}
        inputs.append({"bytes": data, "mime": fmt})
    before = budget.calls
    t0 = time.time()
    try:
        if inputs:
            res = client.edit(case["brief"], model, case["expected_size"], quality=quality, inputs=inputs)
        else:
            res = client.generate(case["brief"], model, case["expected_size"], quality=quality)
    except provider.ProviderError as e:
        return {"status": "budget_exhausted" if e.kind == "budget" else "failed", "error": f"{e.kind}: {e}"[:500],
                "attempts": e.attempts, "paid_calls": budget.calls - before, "request_ids": [e.request_id] if e.request_id else [],
                "latency_ms": round((time.time() - t0) * 1000)}
    u = res.get("usage")
    return {"status": "done", "bytes": res["bytes"], "ext": res["ext"], "attempts": res["attempts"], "paid_calls": budget.calls - before,
            "request_ids": [res["request_id"]] if res.get("request_id") else [], "latency_ms": res["ms"], "warnings": list(res.get("warnings") or []),
            "usage": {k: v for k, v in u.items() if isinstance(v, int)} if isinstance(u, dict) else None}


def run_benchmark(paths, split, generate, max_calls=None, approve_paid=False, confirm_final=False, out_dir=None, only=None,
                  run_id=None, env=None, now=None, client_factory=None, model=None, quality=None, log=print):
    """Executa um split. Devolve (código_de_saída, pasta_do_run | None). 2 = recusa por exigência faltando; 1 = benchmark inválido."""
    env = os.environ if env is None else env
    now = now or utcnow
    refusals = []
    if generate == "openai":
        if max_calls is None or max_calls < 1:
            refusals.append("--generate openai exige --max-calls N com N >= 1 (orçamento de chamadas pagas)")
        if not approve_paid:
            refusals.append("--generate openai exige --i-approve-paid-calls (confirmação explícita de gasto)")
        if not env.get("OPENAI_API_KEY"):
            refusals.append("--generate openai exige OPENAI_API_KEY no ambiente")
    if split == "final" and not confirm_final:
        refusals.append("--split final exige --confirm-final (o conjunto final não pode ser usado para ajustar prompts)")
    if refusals:
        for r in refusals:
            log(f"RECUSADO: {r}")
        return 2, None
    problems, cases = validate_all(paths)
    if problems:
        log(f"RECUSADO: o benchmark é inválido ({len(problems)} problema(s)); rode `bench.py validate`:")
        for x in problems:
            log(f"  - {x}")
        return 1, None
    selected = cases[split]
    if only:
        ids = {c["id"] for c in selected}
        unknown = [i for i in only if i not in ids]
        if unknown:
            log(f"RECUSADO: ids fora do split {split}: {', '.join(unknown)}")
            return 2, None
        selected = [c for c in selected if c["id"] in set(only)]
    start = now()
    run_id = run_id or f"{start:%Y%m%d-%H%M%S}-{split}-{generate}-{os.urandom(2).hex()}"
    if not SLUG_RE.match(run_id.lower()) or "/" in run_id:
        log(f"RECUSADO: run id inválido: {run_id!r}")
        return 2, None
    run_dir = Path(out_dir) if out_dir else paths.out_root / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        log(f"RECUSADO: a pasta de saída já existe e não está vazia: {run_dir}")
        return 2, None
    if split == "final":
        log(FINAL_WARNING)
        log(f"Uso nº {len(read_final_runs(paths)) + 1} do conjunto final.")
        append_final_run(paths, {"date": iso(start), "run_id": run_id, "generate": generate, "cases": len(selected)})
    if generate == "fake" and max_calls is not None:
        log("aviso: --max-calls é ignorado com --generate fake (sem chamadas pagas)")
    model = "fake-local" if generate == "fake" else (model or env.get("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL)
    quality = None if generate == "fake" else (quality or env.get("IMAGE_QUALITY") or "medium")
    version = benchmark_version(paths)
    budget = client = None
    if generate == "openai":
        budget = provider.Budget("bench", max_calls)
        client = (client_factory or default_client_factory)(env, budget)
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    doc = {"schema": 1, "run_id": run_id, "created": iso(start), "split": split, "generate": generate, "model": model, "quality": quality,
           "benchmark_version": version, "max_calls": max_calls if generate == "openai" else None, "paid_calls_total": 0,
           "prompt_policy": "o brief literal do caso é o prompt; o Runner e o briefing do harness não estão no caminho", "cases": []}

    def save():
        doc["paid_calls_total"] = sum(c["paid_calls"] for c in doc["cases"])
        doc["counts"] = {s: sum(1 for c in doc["cases"] if c["status"] == s) for s in ("done", "skipped", "failed", "budget_exhausted")}
        write_json(run_dir / "results.json", doc)

    for case in selected:
        t_case = now()
        rec = {"id": case["id"], "category": case["category"], "status": None, "date": iso(t_case), "model": model,
               "size_requested": case["expected_size"], "size_actual": None, "benchmark_version": version, "latency_ms": None,
               "attempts": 0, "paid_calls": 0, "request_ids": [], "warnings": [], "usage": None, "image": None}
        if case["category"] == "pedido ambíguo":
            rec["warnings"].append("a chamada direta ao provedor não pede esclarecimento: avalie o critério de esclarecimento no harness, não nesta imagem")
        ref_files, missing = find_ref_files(paths, case)
        if missing:
            rec.update(status="skipped", reason=f"referência(s) user_supplied sem arquivo em {_rel(paths.refs / case['id'])}/: {', '.join(missing)} "
                       f"(forneça <id>.png|jpg|webp; nada é gerado nem aprovado sem elas)")
            log(f"PULADO  {case['id']}: faltam referências {', '.join(missing)}")
        elif generate == "fake":
            w, h = _size_for(case)
            t0 = time.time()
            data = fake_png(case["id"], w, h)
            rec.update(status="done", attempts=1, latency_ms=round((time.time() - t0) * 1000), bytes=data, ext="png")
            if ref_files:
                rec["warnings"].append("o gerador fake não usa as referências")
        elif budget.remaining() == 0:
            rec.update(status="budget_exhausted", reason=f"orçamento de {max_calls} chamadas pagas esgotado antes deste caso; nada foi enviado")
            log(f"SEM ORÇAMENTO  {case['id']}: não rodou")
        else:
            rec.update(_openai_case(client, budget, case, ref_files, model, quality))
        data = rec.pop("bytes", None)
        ext = rec.pop("ext", None)
        if rec["status"] == "done":
            rel = f"images/{case['id']}.{ext}"
            (run_dir / rel).write_bytes(data)
            rec["image"] = rel
            dims = png_dims(data)
            rec["size_actual"] = f"{dims[0]}x{dims[1]}" if dims else None
            if not dims:
                rec["warnings"].append("tamanho real não verificável: só PNG é lido")
            log(f"FEITO   {case['id']} ({rec['size_actual'] or '?'})")
        elif rec["status"] in ("failed", "budget_exhausted") and rec.get("error"):
            log(f"{rec['status'].upper()}  {case['id']}: {rec['error']}")
        doc["cases"].append(rec)
        save()
    save()
    log(f"Run '{run_id}' em {run_dir}: " + ", ".join(f"{n} {s}" for s, n in doc["counts"].items()) + f"; {doc['paid_calls_total']} chamadas pagas")
    return 0, run_dir


# ------------------------------------------------------------------ checagens automáticas


def resolve_run(paths, ref):
    """Pasta de um run: caminho existente ou id dentro de paths.out_root."""
    for cand in (Path(ref), paths.out_root / ref):
        if (cand / "results.json").is_file():
            return cand
    raise BenchError(f"run não encontrado: {ref} (procurei como pasta e em {paths.out_root})")


def load_run(paths, ref):
    d = resolve_run(paths, ref)
    try:
        return d, json.loads((d / "results.json").read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise BenchError(f"results.json ilegível em {d}: {e}")


def check_run(paths, ref, ocr_backend=None):
    """Aplica as checagens automáticas aplicáveis e grava checks.json no run. Nada vira 'pass' sem evidência.

    Status por critério: pass/fail (só auto:size: dimensões lidas do PNG), ocr_match/ocr_mismatch/not_verified (auto:ocr: o OCR é
    auxiliar, nunca prova), not_implemented (auto:preservation: não há comparação de pixels fora de máscara aqui),
    pending_human (critérios human), not_run (o caso não gerou imagem)."""
    run_dir, doc = load_run(paths, ref)
    by_id = {}
    for split in SPLITS:
        for c in _load_cases(paths.split_file(split), split, []):
            if isinstance(c, dict) and "id" in c:
                by_id[c["id"]] = c
    cur = benchmark_version(paths)
    changed = {k: (doc.get("benchmark_version") or {}).get(k) != cur[k] for k in ("dev_sha256", "final_sha256")}
    out_cases = []
    for rec in doc["cases"]:
        case = by_id.get(rec["id"])
        entry = {"id": rec["id"], "status": rec["status"], "criteria": []}
        if case is None:
            entry["problem"] = "caso não existe mais no benchmark atual"
            out_cases.append(entry)
            continue
        img = None
        if rec["status"] == "done" and rec.get("image") and (run_dir / rec["image"]).is_file():
            img = (run_dir / rec["image"]).read_bytes()
        for k in case["required_criteria"]:
            e = {"id": k["id"], "check": k["check"]}
            if img is None:
                e.update(status="not_run", evidence=f"sem imagem gerada (status do caso: {rec['status']})")
            elif k["check"] == "human":
                e.update(status="pending_human", evidence="exige avaliador humano")
            elif k["check"] == "auto:size":
                dims = png_dims(img)
                if case["expected_size"] == "auto" or not dims:
                    e.update(status="not_verified", evidence="sem tamanho esperado ou arquivo que não é PNG")
                else:
                    got = f"{dims[0]}x{dims[1]}"
                    e.update(status="pass" if got == case["expected_size"] else "fail", evidence=f"tamanho real {got}, esperado {case['expected_size']}; "
                             "dimensões válidas não provam fidelidade textual nem de conteúdo")
            elif k["check"] == "auto:ocr":
                read = ocr.read_text(img, backend=ocr_backend)
                fid = ocr.text_fidelity(case["text_literals"], read)
                st = "not_verified" if fid["all_match"] is None else ("ocr_match" if fid["all_match"] else "ocr_mismatch")
                e.update(status=st, ocr_status=read["status"], verdicts=fid["results"], ocr_text=read["text"][:500],
                         evidence=read.get("reason") or "o OCR é auxiliar: nunca prova de fidelidade; casos críticos vão para revisão humana")
            else:  # auto:preservation
                e.update(status="not_implemented", evidence="não há comparação de pixels fora de máscara neste benchmark (nem máscara por caso): "
                         "conferir a lista de preservation com avaliador humano")
            entry["criteria"].append(e)
        out_cases.append(entry)
    summary = {}
    for c in out_cases:
        for e in c["criteria"]:
            summary[e["status"]] = summary.get(e["status"], 0) + 1
    res = {"run_id": doc["run_id"], "checked": iso(utcnow()), "benchmark_changed_since_run": changed, "summary": summary, "cases": out_cases}
    write_json(run_dir / "checks.json", res)
    return res


def cmd_check(paths, ref, out=print, ocr_backend=None):
    res = check_run(paths, ref, ocr_backend=ocr_backend)
    out(f"Checagens do run {res['run_id']}: " + ", ".join(f"{k}={v}" for k, v in sorted(res["summary"].items())))
    if any(res["benchmark_changed_since_run"].values()):
        out("aviso: o benchmark mudou desde este run (hash diferente); as checagens usam a definição ATUAL dos casos")
    return 0


# ------------------------------------------------------------------ comparação cega


def blind_pack(paths, ref_a, ref_b, seed, out_dir=None, label_a=None, label_b=None, baseline_arm=None, baseline_source=None, now=None):
    """Gera pacote anonimizado e a chave. Devolve o dicionário da chave. Estrutura:
        <out>/avaliador/  imagens <caso>_X|Y.<ext>, ratings_template.csv, INSTRUCOES.txt   (isto é o que o avaliador abre)
        <out>/key.json    mapeamento X/Y -> braço e seed (NÃO compartilhar com o avaliador)"""
    if baseline_arm not in (None, "A", "B"):
        raise BenchError("--baseline-arm deve ser A ou B")
    if baseline_arm and not _s(baseline_source):
        raise BenchError("--baseline-arm exige --baseline-source descrevendo como as imagens do baseline foram obtidas de forma legítima")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise BenchError("--seed deve ser um inteiro")
    da, a = load_run(paths, ref_a)
    db, b = load_run(paths, ref_b)
    if a["run_id"] == b["run_id"]:
        raise BenchError("os dois braços são o mesmo run")
    ca, cb = {c["id"]: c for c in a["cases"]}, {c["id"]: c for c in b["cases"]}
    usable, excluded = [], []
    for cid in sorted(set(ca) | set(cb)):
        why = None
        for name, cs, d in (("A", ca, da), ("B", cb, db)):
            c = cs.get(cid)
            if c is None:
                why = f"ausente no braço {name}"
            elif c["status"] != "done" or not c.get("image") or not (d / c["image"]).is_file():
                why = f"sem imagem no braço {name} (status {c['status']})"
        (excluded.append({"id": cid, "reason": why}) if why else usable.append(cid))
    if not usable:
        raise BenchError("nenhum caso concluído nos dois runs: nada para comparar")
    rng = random.Random(seed)
    marks = [True] * (len(usable) // 2) + [False] * (len(usable) - len(usable) // 2)  # metade dos casos com os braços trocados: X não fica sempre com o mesmo
    rng.shuffle(marks)
    flips = dict(zip(usable, marks))  # ids em ordem fixa: mesma seed, mesma atribuição
    order = list(usable)
    rng.shuffle(order)
    now = now or utcnow
    out_dir = Path(out_dir) if out_dir else paths.out_root / f"blind-{now():%Y%m%d-%H%M%S}-{os.urandom(2).hex()}"
    if out_dir.exists() and any(out_dir.iterdir()):
        raise BenchError(f"a pasta de saída já existe e não está vazia: {out_dir}")
    pack = out_dir / "avaliador"
    pack.mkdir(parents=True)
    labels = {"A": label_a or a["run_id"], "B": label_b or b["run_id"]}
    assignment, warnings = {}, []
    briefs = {}
    for split in SPLITS:
        for c in _load_cases(paths.split_file(split), split, []):
            if isinstance(c, dict) and "id" in c:
                briefs[c["id"]] = c.get("brief", "")
    for cid in usable:
        arms = ("B", "A") if flips[cid] else ("A", "B")  # arms[0] vai para X, arms[1] para Y
        assignment[cid] = {"X": arms[0], "Y": arms[1]}
        exts = {}
        for pos, arm in zip(("X", "Y"), arms):
            d, rec = (da, ca[cid]) if arm == "A" else (db, cb[cid])
            data = (d / rec["image"]).read_bytes()
            clean, removed = strip_png_metadata(data)
            if removed is None:
                warnings.append(f"{cid}: imagem do braço em {pos} não é PNG; metadados podem revelar a origem")
            ext = sniff_ext(clean) or "bin"
            exts[pos] = ext
            (pack / f"{cid}_{pos}.{ext}").write_bytes(clean)
        if exts["X"] != exts["Y"]:
            warnings.append(f"{cid}: formatos diferentes entre X e Y ({exts['X']}, {exts['Y']}): a extensão pode revelar o braço")
    with open(pack / "ratings_template.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "brief", "preferred", "fidelity_x", "fidelity_y", "notes"])
        for cid in order:
            w.writerow([cid, briefs.get(cid, ""), "", "", "", ""])
    (pack / "INSTRUCOES.txt").write_text(
        "Para cada linha de ratings_template.csv, abra as duas imagens do caso (<case_id>_X e <case_id>_Y) e leia o pedido (coluna brief).\n"
        "preferred: X, Y ou empate (deixe vazio para não avaliar o caso).\n"
        "fidelity_x e fidelity_y: nota de 1 a 5 para o quanto a imagem cumpre o pedido (1 = não cumpre, 5 = cumpre por completo).\n"
        "notes: livre. Não tente descobrir a origem das imagens; avalie só o que vê.\n", encoding="utf-8")
    key = {"seed": seed, "created": iso(now()), "arms": {k: {"run_id": r["run_id"], "label": labels[k], "generate": r.get("generate"), "model": r.get("model"),
           "source": r.get("source")} for k, r in (("A", a), ("B", b))}, "baseline_arm": baseline_arm,
           "baseline_source": baseline_source.strip() if baseline_arm else None, "assignment": assignment, "row_order": order,
           "excluded": excluded, "warnings": warnings, "benchmark_version": a.get("benchmark_version")}
    write_json(out_dir / "key.json", key)
    return key, out_dir


def load_key(path):
    try:
        key = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BenchError(f"key.json ilegível: {e}")
    if not isinstance(key, dict) or not isinstance(key.get("assignment"), dict) or not isinstance(key.get("arms"), dict):
        raise BenchError("key.json sem assignment/arms: não parece a chave de um blind-pack")
    return key


def read_ratings(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError) as e:
        raise BenchError(f"ratings ilegível: {e}")


def score_ratings(rows, key):
    """Agrega preferência por braço e fidelidade média. Levanta BenchError com TODOS os problemas ou se não há avaliação."""
    problems, seen, graded = [], set(), []
    need = {"case_id", "preferred", "fidelity_x", "fidelity_y"}
    if rows and not need <= set(rows[0].keys()):
        raise BenchError(f"ratings sem as colunas {sorted(need - set(rows[0].keys()))}: use o ratings_template.csv gerado pelo blind-pack")
    for i, r in enumerate(rows, 2):
        cid = (r.get("case_id") or "").strip()
        if cid not in key["assignment"]:
            problems.append(f"linha {i}: case_id {cid!r} não está no pacote")
            continue
        if cid in seen:
            problems.append(f"linha {i}: case_id {cid!r} repetido")
            continue
        seen.add(cid)
        pref = (r.get("preferred") or "").strip()
        fx, fy = (r.get("fidelity_x") or "").strip(), (r.get("fidelity_y") or "").strip()
        if not (pref or fx or fy):
            continue  # não avaliado
        p = None
        if pref:
            if pref.upper() in ("X", "Y"):
                p = pref.upper()
            elif pref.lower() == "empate":
                p = "empate"
            else:
                problems.append(f"linha {i} ({cid}): preferred {pref!r} inválido (use X, Y ou empate)")
        fids = {}
        for pos, v in (("X", fx), ("Y", fy)):
            if v:
                if re.fullmatch(r"[1-5]", v):
                    fids[pos] = int(v)
                else:
                    problems.append(f"linha {i} ({cid}): fidelity_{pos.lower()} {v!r} inválida (1 a 5)")
        graded.append((cid, p, fids))
    if problems:
        raise BenchError("ratings inválidos:\n  - " + "\n  - ".join(problems))
    if not graded:
        raise BenchError("sem avaliações: nenhuma linha de ratings tem preferred ou fidelity preenchido")
    arms = {k: {"label": v.get("label"), "run_id": v.get("run_id"), "wins": 0, "fidelity_n": 0, "fidelity_sum": 0} for k, v in key["arms"].items()}
    ties = n_pref = 0
    for cid, p, fids in graded:
        asg = key["assignment"][cid]
        if p is not None:
            n_pref += 1
            if p == "empate":
                ties += 1
            else:
                arms[asg[p]]["wins"] += 1
        for pos, v in fids.items():
            arms[asg[pos]]["fidelity_n"] += 1
            arms[asg[pos]]["fidelity_sum"] += v
    for a in arms.values():
        a["fidelity_mean"] = round(a["fidelity_sum"] / a["fidelity_n"], 3) if a["fidelity_n"] else None
    return {"arms": arms, "ties": ties, "n_preference": n_pref, "n_graded_cases": len(graded), "cases_in_pack": len(key["assignment"]),
            "unrated_cases": sorted(set(key["assignment"]) - {g[0] for g in graded})}


def format_score(score):
    lines = [f"Casos no pacote: {score['cases_in_pack']}; avaliados: {score['n_graded_cases']}; com preferência: {score['n_preference']}; empates: {score['ties']}"]
    for k in sorted(score["arms"]):
        a = score["arms"][k]
        fid = f"{a['fidelity_mean']} (n={a['fidelity_n']})" if a["fidelity_n"] else "sem notas"
        lines.append(f"  braço {k} [{a['label']}]: {a['wins']} preferências; fidelidade média {fid}")
    if score["unrated_cases"]:
        lines.append(f"  sem avaliação: {', '.join(score['unrated_cases'])}")
    return "\n".join(lines)


# ------------------------------------------------------------------ relatório


def build_report(paths, ref, ratings=None, key_path=None, now=None):
    """Markdown do run. Contém 'paridade ainda não demonstrada' a menos que exista baseline externo legítimo com avaliação cega."""
    run_dir, doc = load_run(paths, ref)
    now = (now or utcnow)()
    score = key = None
    if ratings:
        if not key_path:
            raise BenchError("report com --ratings exige --key (a chave do blind-pack)")
        key = load_key(key_path)
        if doc["run_id"] not in {v.get("run_id") for v in key["arms"].values()}:
            raise BenchError("a chave não pertence a este run: o run do relatório não é nenhum dos braços do blind-pack")
        rows = read_ratings(ratings)
        score = score_ratings(rows, key)
    legit = False
    if score and key.get("baseline_arm") in ("A", "B") and _s(key.get("baseline_source")) and score["n_preference"] > 0:
        base, other = key["arms"][key["baseline_arm"]], key["arms"]["B" if key["baseline_arm"] == "A" else "A"]
        legit = base.get("generate") == "external" and other.get("generate") not in ("fake", "external", None)
    checks = None
    if (run_dir / "checks.json").is_file():
        checks = json.loads((run_dir / "checks.json").read_text(encoding="utf-8"))
    done = [c for c in doc["cases"] if c["status"] == "done"]
    L = [f"# Relatório do benchmark: {doc['run_id']}", "", f"Gerado em {iso(now)}.", "", "## Condições", "",
         f"- Run: `{doc['run_id']}` (criado em {doc['created']})", f"- Split: {doc['split']}; gerador: {doc['generate']}; modelo: {doc['model']}; qualidade: {doc.get('quality')}",
         f"- Versão do benchmark: dev {str((doc['benchmark_version'] or {}).get('dev_sha256'))[:12]}..., final {str((doc['benchmark_version'] or {}).get('final_sha256'))[:12]}...",
         f"- Prompt: {doc.get('prompt_policy')}",
         f"- Orçamento: {doc.get('max_calls')} chamadas pagas; usadas: {doc.get('paid_calls_total')}",
         f"- Casos: {len(doc['cases'])} ({', '.join(f'{n} {s}' for s, n in (doc.get('counts') or {}).items())})", ""]
    if doc["generate"] == "fake":
        L += ["> Este run usou o gerador **fake**: imagens sintéticas sem conteúdo. Serve só para testar o pipeline do benchmark e **não mede qualidade nenhuma**.", ""]
    if doc["split"] == "final":
        L += ["> Run do conjunto **final**: estes resultados não podem ser usados para ajustar prompts, regras ou modelo.", ""]
    L += ["## Custo, latência e tentativas por caso aceito", "",
          "Custo é contado em chamadas pagas (cada tentativa HTTP conta); não há valor em dinheiro porque os modelos 2.5 cobram por tokens e não há tabela por imagem. "
          "O campo usage, quando a API o devolve, está em results.json.", ""]
    if done:
        L += ["| caso | categoria | tamanho | tentativas | chamadas pagas | latência (ms) |", "|---|---|---|---|---|---|"]
        for c in done:
            L.append(f"| {c['id']} | {c['category']} | {c['size_actual'] or '?'} | {c['attempts']} | {c['paid_calls']} | {c['latency_ms']} |")
        lat = [c["latency_ms"] for c in done if isinstance(c["latency_ms"], (int, float))]
        L += ["", f"Totais dos casos aceitos: {sum(c['paid_calls'] for c in done)} chamadas pagas; latência média {round(sum(lat) / len(lat)) if lat else 'n/d'} ms.", ""]
    else:
        L += ["Nenhum caso concluído neste run.", ""]
    others = [c for c in doc["cases"] if c["status"] != "done"]
    if others:
        L += ["## Casos que não rodaram", ""]
        for c in others:
            L.append(f"- {c['id']} ({c['status']}): {c.get('reason') or c.get('error') or 'sem detalhe'}")
        L.append("")
    L += ["## Checagens automáticas", ""]
    if checks:
        L.append(", ".join(f"{k}: {v}" for k, v in sorted(checks["summary"].items())) + ".")
        L.append("")
        L.append("`pending_human` é trabalho para avaliador humano, `not_verified` e `not_implemented` NÃO são aprovação. Nada aqui foi aprovado sem evidência.")
    else:
        L.append("`bench.py check` ainda não foi executado neste run: nenhuma checagem automática foi aplicada e nenhum critério foi avaliado.")
    L += ["", "## Comparação cega", ""]
    if score:
        L.append(f"Casos no pacote: {score['cases_in_pack']}; avaliados: {score['n_graded_cases']}; com preferência: {score['n_preference']}; empates: {score['ties']}.")
        L.append("")
        for k in sorted(score["arms"]):
            a = score["arms"][k]
            fid = f"{a['fidelity_mean']} (n={a['fidelity_n']})" if a["fidelity_n"] else "sem notas"
            L.append(f"- braço {k} ({a['label']}): {a['wins']} preferências; fidelidade média {fid}")
        L += ["", f"Seed do sorteio: registrada na chave (não divulgada ao avaliador). Declarado como baseline: braço {key.get('baseline_arm') or 'nenhum'}"
               + (f", obtido assim: {key['baseline_source']}" if key.get("baseline_source") else "") + "."]
    else:
        L.append("Nenhuma avaliação cega foi fornecida a este relatório.")
    L += ["", "## Paridade com o ChatGPT", ""]
    if legit:
        L += [f"Há um braço de baseline externo com avaliação cega (n={score['n_preference']} casos com preferência). Este relatório descreve os números e **não afirma paridade nem superioridade**: "
              "n pequeno e avaliadores não independentes não sustentam conclusão estatística."]
    else:
        L += [f"Situação: **{PARITY_PHRASE}**. Não existe, neste relatório, um braço de baseline externo legítimo com avaliação cega. Nada aqui afirma superioridade ou igualdade em relação ao ChatGPT."]
    L += ["", "A comparação com o ChatGPT exige referências obtidas legitimamente (imagens geradas pelo próprio avaliador, de forma manual, conforme os termos do serviço) e ordem aleatória. "
          "O acesso à interface do ChatGPT NÃO é automatizado por este benchmark.", "", "## Limitações", "",
          "- O benchmark é pequeno e escrito pela própria equipe: serve para detectar regressões e falhas grosseiras, não para provar qualidade geral.",
          "- Com `--generate openai`, o prompt é o brief literal enviado ao adapter de imagens; o Runner, o briefing e o critic do harness não participam.",
          "- Referências reais (bench/refs/) vêm do usuário; casos sem elas são pulados, nunca aprovados.",
          "- OCR é auxiliar (texto pequeno, fontes decorativas, baixo contraste, texto curvo e outros idiomas não são verificáveis); preços, datas e números críticos exigem revisão humana.",
          "- Preservação fora da região editada não é medida automaticamente (not_implemented).",
          "- Critérios humanos (aderência, estética, identidade, esclarecimento de pedidos ambíguos) ficam pending_human até serem avaliados por pessoas.", ""]
    return "\n".join(L)


# ------------------------------------------------------------------ CLI


def build_parser():
    ap = argparse.ArgumentParser(prog="bench.py", description="Benchmark versionado do harness de imagens")
    ap.add_argument("--bench-dir", help="pasta dos casos (padrão: bench/ na raiz do repositório)")
    ap.add_argument("--refs-dir", help="pasta das referências do usuário (padrão: <bench>/refs)")
    ap.add_argument("--out-root", help="pasta onde os runs ficam (padrão: test/bench_out)")
    ap.add_argument("--final-runs", help="arquivo de auditoria do uso do final (padrão: <bench>/final_runs.jsonl ou $BENCH_FINAL_RUNS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="valida esquema, ids, splits, cobertura de categorias e lock do final")
    p = sub.add_parser("lock", help="regrava o lock do final com a razão")
    p.add_argument("--reason", required=True)
    p = sub.add_parser("run", help="executa um split")
    p.add_argument("--split", choices=SPLITS, required=True)
    p.add_argument("--generate", choices=("fake", "openai"), required=True)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--i-approve-paid-calls", action="store_true")
    p.add_argument("--confirm-final", action="store_true")
    p.add_argument("--out")
    p.add_argument("--only", nargs="+")
    p.add_argument("--run-id")
    p.add_argument("--model")
    p.add_argument("--quality")
    p = sub.add_parser("check", help="aplica as checagens automáticas a um run")
    p.add_argument("--run", required=True)
    p = sub.add_parser("blind-pack", help="gera o pacote cego e a chave")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out")
    p.add_argument("--label-a")
    p.add_argument("--label-b")
    p.add_argument("--baseline-arm", choices=("A", "B"))
    p.add_argument("--baseline-source")
    p = sub.add_parser("blind-score", help="agrega as avaliações cegas")
    p.add_argument("--ratings", required=True)
    p.add_argument("--key", required=True)
    p = sub.add_parser("report", help="relatório em markdown de um run")
    p.add_argument("--run", required=True)
    p.add_argument("--ratings")
    p.add_argument("--key")
    p.add_argument("--out")
    return ap


def main(argv=None, env=None, now=None, client_factory=None, ocr_backend=None):
    args = build_parser().parse_args(argv)
    paths = Paths(args.bench_dir, args.out_root, args.final_runs, args.refs_dir)
    try:
        if args.cmd == "validate":
            return cmd_validate(paths)
        if args.cmd == "lock":
            return cmd_lock(paths, args.reason)
        if args.cmd == "run":
            code, _ = run_benchmark(paths, args.split, args.generate, max_calls=args.max_calls, approve_paid=args.i_approve_paid_calls,
                                    confirm_final=args.confirm_final, out_dir=args.out, only=args.only, run_id=args.run_id, env=env, now=now,
                                    client_factory=client_factory, model=args.model, quality=args.quality)
            return code
        if args.cmd == "check":
            return cmd_check(paths, args.run, ocr_backend=ocr_backend)
        if args.cmd == "blind-pack":
            key, out = blind_pack(paths, args.a, args.b, args.seed, args.out, args.label_a, args.label_b, args.baseline_arm, args.baseline_source, now=now)
            print(f"Pacote cego: {len(key['assignment'])} casos.\n  entregue ao avaliador: {out / 'avaliador'}\n  NÃO entregue (chave e seed): {out / 'key.json'}")
            for w in key["warnings"]:
                print(f"aviso: {w}")
            for e in key["excluded"]:
                print(f"excluído: {e['id']} ({e['reason']})")
            return 0
        if args.cmd == "blind-score":
            rows = read_ratings(args.ratings)
            print(format_score(score_ratings(rows, load_key(args.key))))
            return 0
        if args.cmd == "report":
            md = build_report(paths, args.run, args.ratings, args.key, now=now)
            if args.out:
                Path(args.out).write_text(md, encoding="utf-8")
                print(f"Relatório gravado em {args.out}")
            else:
                print(md)
            return 0
    except BenchError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
