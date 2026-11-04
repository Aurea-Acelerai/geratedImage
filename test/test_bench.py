#!/usr/bin/env python3
"""Testes de bench.py. Offline, rápidos e determinísticos: sem rede (qualquer conexão de socket derruba o teste), sem custo,
tudo em pastas temporárias (nunca escreve em bench/ nem em test/bench_out/).

  python3 -I test/test_bench.py        (da raiz do repositório)
  cd test && python3 -I test_bench.py

Cada caso afirma comportamento observável (problemas listados, status gravado, arquivos criados, o que foi enviado ao
transporte), não que um mock foi chamado. O caminho `--generate openai` só é exercitado com transporte injetado (sem rede).
"""
import base64, contextlib, copy, csv, io, json, pathlib, shutil, socket, sys, tempfile, threading

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import bench  # noqa: E402
import ocr  # noqa: E402
import provider as pv  # noqa: E402

REPO = ROOT.parent
N = {"ok": 0}
FIXED = bench.datetime.datetime(2026, 11, 4, 12, 0, 0, tzinfo=bench.datetime.timezone.utc)


def now():
    return FIXED


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def no_network(*a, **kw):
    raise AssertionError("tentativa de acesso à rede: o benchmark offline nunca deve chamar a rede")


class patched:
    def __init__(self, *triples):
        self.triples = triples

    def __enter__(self):
        self.old = [(o, n, getattr(o, n)) for o, n, _ in self.triples]
        for o, n, v in self.triples:
            setattr(o, n, v)

    def __exit__(self, *exc):
        for o, n, v in self.old:
            setattr(o, n, v)


def no_tesseract():
    return patched((ocr.shutil, "which", lambda n: None))


class sandbox:
    """Pasta temporária com bench/ (cópia dos arquivos reais, com lock próprio), saída e auditoria do final isoladas."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bench_test_")
        t = pathlib.Path(self.tmp.name)
        (t / "bench").mkdir()
        for f in ("dev.json", "final.json"):
            shutil.copy(REPO / "bench" / f, t / "bench" / f)
        self.paths = bench.Paths(bench_dir=t / "bench", out_root=t / "out", final_runs=t / "final_runs.jsonl")
        self.t = t
        problems, _ = bench.do_lock(self.paths, "lock de teste", today="2026-11-04")
        assert not problems, problems
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()

    def load(self, split):
        return json.loads(self.paths.split_file(split).read_text(encoding="utf-8"))

    def save(self, split, data, relock=False, force=False):
        """relock=True usa o `lock` de verdade (que recusa benchmark inválido); force=True grava o hash direto, para montar cenários inválidos travados."""
        self.paths.split_file(split).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if force:
            lock = json.loads(self.paths.lock.read_text(encoding="utf-8"))
            lock["final_sha256"] = bench.sha256_file(self.paths.final)
            self.paths.lock.write_text(json.dumps(lock), encoding="utf-8")
        elif relock:
            problems, _ = bench.do_lock(self.paths, "mudança de teste", today="2026-11-04")
            assert not problems, problems

    def run(self, run_id, only=None, split="dev", **kw):
        lines = []
        kw.setdefault("now", now)
        code, d = bench.run_benchmark(self.paths, split, "fake", run_id=run_id, only=only, log=lines.append, **kw)
        return code, d, lines

    def results(self, d):
        return json.loads((pathlib.Path(d) / "results.json").read_text(encoding="utf-8"))

    def ref(self, case_id, ref_id, data=None):
        f = self.paths.refs / case_id / f"{ref_id}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data or bench.fake_png("ref-" + ref_id, 8, 8))
        return f


def cli(*argv, env=None, factory=None, ocr_backend=None):
    """Roda main() e devolve (código, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = bench.main(list(argv), env=env, now=now, client_factory=factory, ocr_backend=ocr_backend)
        except SystemExit as e:  # argparse
            code = e.code
    return code, out.getvalue(), err.getvalue()


def raises(fn, frag):
    try:
        fn()
    except bench.BenchError as e:
        return frag in str(e)
    return False


def by_id(items):
    return {c["id"]: c for c in items}


# ---------------------------------------------------------------- validate


def test_real_bench_files():
    paths = bench.Paths()
    problems, cases = bench.validate_all(paths)
    ok(problems == [], "os arquivos reais de bench/ validam (esquema, cobertura e lock do final): " + "; ".join(problems[:3]))
    ok(len(cases["dev"]) >= 14 and len(cases["final"]) >= 6, f"dev tem {len(cases['dev'])} casos e final tem {len(cases['final'])}")
    cats = {c["category"] for s in cases.values() for c in s}
    ok(cats == set(bench.CATEGORIES), "as 14 categorias obrigatórias estão presentes no total dev+final")
    ok(len({c["category"] for c in cases["final"]}) >= 5, "o final tem categorias variadas")
    ok(all(c["split"] == "dev" for c in cases["dev"]) and all(c["split"] == "final" for c in cases["final"]), "splits nos arquivos certos")
    lock = json.loads((REPO / "bench" / "LOCK.json").read_text(encoding="utf-8"))
    ok(lock["final_sha256"] == bench.sha256_file(REPO / "bench" / "final.json") and lock["locked_on"] and lock["rule"] and lock["history"], "LOCK.json tem hash do final, data, regra e history")
    ok(not any((REPO / "bench" / "refs").glob("*")) if (REPO / "bench" / "refs").exists() else True, "nenhuma imagem de referência versionada em bench/refs/")
    flat = json.dumps(cases, ensure_ascii=False)
    ok("lorem" not in flat.lower(), "sem texto de preenchimento")
    ok(sum(1 for s in cases.values() for c in s if c["category"] == "pedido ambíguo" and any(k["check"] == "human" for k in c["required_criteria"])) >= 2,
       "pedidos ambíguos têm critério humano de esclarecimento")


def test_validate_failures():
    with sandbox() as sb:
        problems, _ = bench.validate_all(sb.paths)
        ok(problems == [], "cópia temporária íntegra e travada valida")
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "validate")
        ok(code == 0 and out.startswith("OK"), "CLI validate sai com 0 quando está tudo certo")

        # categoria some do total (dev e final)
        dev, fin = sb.load("dev"), sb.load("final")
        sb.save("dev", [c for c in dev if c["category"] != "pedido ambíguo"])
        sb.save("final", [c for c in fin if c["category"] != "pedido ambíguo"], force=True)
        problems, _ = bench.validate_all(sb.paths)
        ok(problems == ["categoria obrigatória sem nenhum caso: pedido ambíguo"], "validate falha quando uma categoria some do total (e só por isso)")
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "validate")
        ok(code == 1 and "pedido ambíguo" in out, "CLI validate sai com 1 e lista o problema")

        # a categoria só no final continua cobrindo (a cobertura é do total)
        sb.save("final", fin, force=True)
        sb.save("dev", [c for c in dev if c["category"] != "pedido ambíguo"])
        problems, _ = bench.validate_all(sb.paths)
        ok(not any("categoria obrigatória" in p for p in problems), "categoria ausente do dev mas presente no final conta como coberta")

        # id repetido
        d = copy.deepcopy(dev)
        d[1]["id"] = d[0]["id"]
        sb.save("dev", d)
        problems, _ = bench.validate_all(sb.paths)
        ok(any("id repetido" in p and d[0]["id"] in p for p in problems), "validate falha quando um id repete")
        d2 = copy.deepcopy(dev)
        f2 = copy.deepcopy(fin)
        f2[0]["id"], f2[0]["split"] = d2[0]["id"], "dev"
        sb.save("dev", d2)
        sb.save("final", f2, force=True)
        problems, _ = bench.validate_all(sb.paths)
        ok(any("id repetido" in p for p in problems), "id repetido entre dev e final também é pego")
        sb.save("final", fin, force=True)
        sb.save("dev", dev)

        # final muda sem lock
        f3 = copy.deepcopy(fin)
        f3[0]["brief"] = f3[0]["brief"] + " Com um poste de luz amarelo no canto."
        sb.save("final", f3)  # sem relock
        problems, _ = bench.validate_all(sb.paths)
        ok(len(problems) == 1 and "mudou desde o lock" in problems[0], "validate falha quando o final muda sem atualizar o lock (e só por isso)")
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "validate")
        ok(code == 1 and "bench.py lock --reason" in out, "a mensagem diz como atualizar o lock de propósito")
        before = json.loads(sb.paths.lock.read_text(encoding="utf-8"))
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "lock", "--reason", "ajuste do poste de luz")
        after = json.loads(sb.paths.lock.read_text(encoding="utf-8"))
        ok(code == 0 and after["final_sha256"] == bench.sha256_file(sb.paths.final) != before["final_sha256"], "lock --reason regrava o hash do final")
        h = after["history"]
        ok(len(h) == len(before["history"]) + 1 and h[-1]["reason"] == "ajuste do poste de luz" and h[-1]["date"] and h[-1]["previous_sha256"] == before["final_sha256"],
           "e anexa razão, data e hash anterior em history")
        ok(bench.validate_all(sb.paths)[0] == [], "depois do lock de propósito, validate passa")
        code, _, err = cli("--bench-dir", str(sb.t / "bench"), "lock", "--reason", "   ")
        ok(code == 2 and "--reason" in err, "lock com razão vazia é recusado")
        ok(json.loads(sb.paths.lock.read_text(encoding="utf-8")) == after, "e não altera o lock")
        sb.save("final", fin, relock=True)

        # lock ausente / corrompido
        sb.paths.lock.unlink()
        ok(any("LOCK.json" in p for p in bench.validate_all(sb.paths)[0]), "sem LOCK.json, validate falha")
        sb.paths.lock.write_text("{não é json", encoding="utf-8")
        ok(any("JSON inválido" in p for p in bench.validate_all(sb.paths)[0]), "LOCK.json corrompido, validate falha")
        sb.paths.lock.write_text(json.dumps({"final_sha256": "0" * 64}), encoding="utf-8")
        ok(any("mudou desde o lock" in p for p in bench.validate_all(sb.paths)[0]), "hash errado no lock, validate falha")
        sb.save("final", fin, relock=True)

        # lock recusa final inválido e não grava
        bad = copy.deepcopy(fin)
        bad[0]["category"] = "inventada"
        sb.save("final", bad)
        snap = sb.paths.lock.read_text(encoding="utf-8")
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "lock", "--reason", "x")
        ok(code == 1 and "inventada" in out and sb.paths.lock.read_text(encoding="utf-8") == snap, "lock não trava um final inválido")
        sb.save("final", fin, relock=True)

        # final sem variedade de categorias
        many = [fin[0], fin[1], fin[6]] + [dict(fin[0], id=f"final-foto-0{i}") for i in (2, 3, 4)]
        sb.save("final", many, force=True)
        ok(any("3 categorias distintas" in p for p in bench.validate_all(sb.paths)[0]), "final com poucas categorias distintas falha (precisa ser variado)")
        sb.save("final", fin, force=True)

        # mínimos de quantidade
        sb.save("dev", dev[:13])
        ok(any("dev.json tem 13 casos" in p for p in bench.validate_all(sb.paths)[0]), "dev com menos de 14 casos falha")
        sb.save("dev", dev)
        sb.save("final", fin[:5], force=True)
        ok(any("final.json tem 5 casos" in p for p in bench.validate_all(sb.paths)[0]), "final com menos de 6 casos falha")
        sb.save("final", fin, relock=True)

        # caso no arquivo errado
        moved = copy.deepcopy(fin[0])
        sb.save("dev", dev + [moved])
        ok(any("split 'final' no arquivo do split 'dev'" in p for p in bench.validate_all(sb.paths)[0]), "caso final dentro de dev.json é pego")
        sb.save("dev", dev)

        # quase duplicata entre dev e final
        f4 = copy.deepcopy(fin)
        f4[0]["brief"] = dev[0]["brief"]
        sb.save("final", f4, force=True)
        ok(any("quase iguais" in p for p in bench.validate_all(sb.paths)[0]), "brief do final copiado do dev é pego como quase igual")
        sb.save("final", fin, relock=True)

        # arquivos ausentes / lista inválida
        sb.paths.dev.write_text('{"nao": "lista"}', encoding="utf-8")
        ok(any("deve conter uma lista" in p for p in bench.validate_all(sb.paths)[0]), "dev.json que não é lista falha")
        sb.paths.dev.unlink()
        ok(any("dev.json: arquivo não existe" in p for p in bench.validate_all(sb.paths)[0]), "dev.json ausente falha")


def test_schema_rules():
    with sandbox() as sb:
        dev = sb.load("dev")
        by = by_id(dev)
        ok(bench.validate_case(by["dev-foto-01"], "dev", "x") == [], "caso íntegro não tem problema")

        def mut(case_id, fn, frag, what):
            c = copy.deepcopy(by[case_id])
            fn(c)
            p = bench.validate_case(c, "dev", "x")
            ok(any(frag in x for x in p), f"{what}: {p[:2]}")

        mut("dev-foto-01", lambda c: c.pop("brief"), "campo obrigatório ausente: brief", "campo obrigatório ausente")
        mut("dev-foto-01", lambda c: c.update(extra=1), "campo desconhecido: extra", "campo desconhecido")
        mut("dev-foto-01", lambda c: c.update(category="foto"), "categoria desconhecida", "categoria fora da lista")
        mut("dev-foto-01", lambda c: c.update(expected_size="800x600"), "expected_size inválido", "tamanho fora da lista")
        mut("dev-foto-01", lambda c: c.update(brief="curto"), "brief vazio ou curto", "brief curto")
        mut("dev-foto-01", lambda c: c.update(id="foto-01"), "id inválido", "id fora do padrão")
        mut("dev-foto-01", lambda c: c.update(id="final-foto-01"), "deve começar com 'dev-'", "prefixo do id diferente do split do arquivo")
        mut("dev-foto-01", lambda c: c.update(split="final"), "split 'final' no arquivo do split 'dev'", "split do caso diferente do arquivo")
        mut("dev-foto-01", lambda c: c.update(difficulty="extrema"), "difficulty inválida", "dificuldade inválida")
        mut("dev-foto-01", lambda c: c.update(required_criteria=[]), "required_criteria deve ser uma lista não vazia", "sem critérios")
        mut("dev-foto-01", lambda c: c["required_criteria"][0].update(check="auto:magia"), "check inválido", "check desconhecido")
        mut("dev-foto-01", lambda c: c["required_criteria"][1].update(id=c["required_criteria"][0]["id"]), "id de critério repetido", "critério repetido")
        mut("dev-foto-01", lambda c: c["required_criteria"].append({"id": "t2", "text": "x", "check": "auto:ocr"}), "auto:ocr sem text_literals", "auto:ocr sem literais")
        mut("dev-foto-01", lambda c: c.update(text_literals=["Olá"]), "text_literals preenchido exige um critério auto:ocr", "literais sem critério ocr")
        mut("dev-foto-01", lambda c: c.update(expected_size="auto"), "auto:size exige expected_size explícito", "auto:size com tamanho auto")
        mut("dev-foto-01", lambda c: c["required_criteria"].append({"id": "p", "text": "x", "check": "auto:preservation"}), "auto:preservation sem itens", "preservação automática sem lista")
        mut("dev-edicao-01", lambda c: c.update(preservation=[]), "exige preservation não vazio", "edição sem lista de preservação")
        mut("dev-edicao-01", lambda c: c.update(references=[]), "exige referência com role base", "edição sem base")
        mut("dev-edicao-01", lambda c: c["references"][0].update(role="dados"), "exige referência com role base", "edição com referência de papel errado")
        mut("dev-edicao-01", lambda c: c["references"][0].update(user_supplied="sim"), "user_supplied deve ser true ou false", "user_supplied que não é booleano")
        mut("dev-edicao-01", lambda c: c["references"][0].update(role="paisagem"), "role inválido", "role fora da lista")
        mut("dev-edicao-01", lambda c: c["references"].append(dict(c["references"][0])), "id de referência repetido", "referência repetida")
        mut("dev-edicao-01", lambda c: c["references"][0].pop("description"), "campos incorretos", "referência sem descrição")
        mut("dev-multirref-01", lambda c: c.update(references=c["references"][:1]), "pelo menos 2 referências", "múltiplas referências com uma só")
        mut("dev-falha-01", lambda c: c.pop("known_failure_mode"), "exige known_failure_mode", "caso de falha sem modo de falha")
        mut("dev-ambiguo-01", lambda c: c.update(required_criteria=[{"id": "a", "text": "x", "check": "auto:size"}]), "exige critério human", "ambíguo sem critério humano")
        mut("dev-personagem-01", lambda c: c["references"][0].update(id="Tuca Ref"), "id inválido", "id de referência com espaço")
        p = bench.validate_case([], "dev", "x[0]")
        ok(p and "deve ser um objeto" in p[0], "caso que não é objeto é pego")
        # todos os problemas juntos
        c = copy.deepcopy(by["dev-foto-01"])
        c.update(category="x", expected_size="1x1", required_criteria=[])
        c.pop("brief")
        ok(len(bench.validate_case(c, "dev", "x")) >= 4, "problemas de um mesmo caso saem todos juntos")


# ---------------------------------------------------------------- run fake


def test_run_fake():
    with sandbox() as sb:
        code, d, lines = sb.run("r1")
        ok(code == 0 and d == sb.paths.out_root / "r1", "run fake termina com 0 e grava em out_root/<run_id>")
        doc = sb.results(d)
        cases = by_id(sb.load("dev"))
        ok(set(c["id"] for c in doc["cases"]) == set(cases), "results.json tem todos os casos do split")
        ok(doc["generate"] == "fake" and doc["model"] == "fake-local" and doc["split"] == "dev" and doc["paid_calls_total"] == 0, "cabeçalho: gerador, modelo, split e zero chamadas pagas")
        ok(doc["benchmark_version"] == {"dev_sha256": bench.sha256_file(sb.paths.dev), "final_sha256": bench.sha256_file(sb.paths.final)},
           "versão do benchmark = sha256 de dev e final")
        needs_ref = {cid for cid, c in cases.items() if any(r["user_supplied"] for r in c["references"])}
        res = by_id(doc["cases"])
        ok({i for i, r in res.items() if r["status"] == "skipped"} == needs_ref and len(needs_ref) >= 5, "pulados = exatamente os casos com referência user_supplied sem arquivo")
        ok(all(res[i]["status"] == "done" for i in cases if i not in needs_ref), "os demais foram feitos")
        ok(all(res[i]["image"] is None and res[i]["paid_calls"] == 0 and "bench/refs/" in res[i]["reason"] for i in needs_ref), "pulado não tem imagem e explica onde colocar a referência")
        ok(all(i not in "".join(l for l in lines if l.startswith("FEITO")) for i in needs_ref), "pulado nunca aparece como feito no log")
        r = res["dev-foto-01"]
        ok(r["date"] == "2026-11-04T12:00:00Z" and r["model"] == "fake-local" and r["size_requested"] == "1536x1024" and r["size_actual"] == "1536x1024"
           and r["benchmark_version"] == doc["benchmark_version"], "por caso: data, modelo, tamanho pedido e real, versão")
        ok(r["attempts"] == 1 and r["paid_calls"] == 0 and r["request_ids"] == [] and isinstance(r["latency_ms"], int) and r["warnings"] == [], "por caso: tentativas, chamadas pagas, request_ids, latência, avisos")
        sizes_ok = True
        for i, c in cases.items():
            if res[i]["status"] == "done":
                data = (d / res[i]["image"]).read_bytes()
                dims = bench.png_dims(data)
                want = (1024, 1024) if c["expected_size"] == "auto" else tuple(int(x) for x in c["expected_size"].split("x"))
                sizes_ok = sizes_ok and dims == want
        ok(sizes_ok, "toda imagem fake tem o tamanho do caso (1024x1024 quando auto)")
        ok("esclarecimento" in " ".join(res["dev-ambiguo-01"]["warnings"]), "pedido ambíguo recebe o aviso de que imagem sozinha não mede esclarecimento")
        ok(doc["counts"]["done"] + doc["counts"]["skipped"] == len(cases), "contagens batem")
        # determinismo
        code, d2, _ = sb.run("r2", only=["dev-foto-01", "dev-texto-01"])
        ok((d / "images/dev-foto-01.png").read_bytes() == (d2 / "images/dev-foto-01.png").read_bytes(), "o gerador fake é determinístico")
        ok((d / "images/dev-foto-01.png").read_bytes() != (d / "images/dev-foto-02.png").read_bytes(), "casos diferentes geram imagens diferentes")

        # --only
        ok(set(c["id"] for c in sb.results(d2)["cases"]) == {"dev-foto-01", "dev-texto-01"}, "--only limita os casos")
        code, d3, lines = sb.run("r3", only=["dev-inexistente-01"])
        ok(code == 2 and d3 is None and not (sb.paths.out_root / "r3").exists(), "--only com id fora do split é recusado sem criar saída")
        code, d3, lines = sb.run("r3", only=["final-foto-01"])
        ok(code == 2, "id do final em run de dev é recusado")
        code, d3, lines = sb.run("r1")
        ok(code == 2 and any("já existe" in l for l in lines), "não sobrescreve um run existente")
        code, d3, lines = sb.run("../fora")
        ok(code == 2 and not (sb.t / "fora").exists(), "run id com caminho é recusado")

        # referência fornecida: o caso passa a rodar; faltando uma de três continua pulado
        sb.ref("dev-edicao-01", "sala-base")
        sb.ref("dev-multirref-01", "pote-geleia")
        code, d4, _ = sb.run("r4", only=["dev-edicao-01", "dev-multirref-01"])
        res4 = by_id(sb.results(d4)["cases"])
        ok(res4["dev-edicao-01"]["status"] == "done" and any("não usa as referências" in w for w in res4["dev-edicao-01"]["warnings"]), "com a referência no lugar, o caso roda (e o fake avisa que não a usa)")
        ok(res4["dev-multirref-01"]["status"] == "skipped" and "estilo-aquarela" in res4["dev-multirref-01"]["reason"] and "logo-horta" in res4["dev-multirref-01"]["reason"]
           and "pote-geleia" not in res4["dev-multirref-01"]["reason"], "com 1 de 3 referências o caso segue pulado e lista as que faltam")

        # referências com user_supplied false não exigem arquivo
        ok(res["dev-diagrama-01"]["status"] == "done", "referência de dados user_supplied=false não exige arquivo")

        # CLI fake com saída explícita
        code, out, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "run", "--split", "dev", "--generate", "fake",
                             "--only", "dev-foto-02", "--run-id", "r5", "--max-calls", "3")
        ok(code == 0 and (sb.t / "out" / "r5" / "results.json").exists() and "ignorado" in out, "CLI run fake funciona (e avisa que --max-calls não vale para fake)")
        code, out, err = cli("--bench-dir", str(sb.t / "bench"), "run", "--split", "dev", "--generate", "fake", "--only", "dev-foto-02", "--out", str(sb.t / "saida"))
        ok(code == 0 and (sb.t / "saida" / "images" / "dev-foto-02.png").exists(), "--out escolhe a pasta de saída")

        # benchmark inválido bloqueia o run
        dev = sb.load("dev")
        dev[0]["category"] = "inventada"
        sb.save("dev", dev)
        code, d6, lines = sb.run("r6")
        ok(code == 1 and d6 is None and any("inventada" in l for l in lines) and not (sb.paths.out_root / "r6").exists(), "run recusa benchmark inválido, com os problemas")


def test_final_gate():
    with sandbox() as sb:
        code, d, lines = sb.run("f0", split="final")
        ok(code == 2 and d is None and any("--confirm-final" in l for l in lines), "run final sem --confirm-final recusa")
        ok(not (sb.paths.out_root / "f0").exists() and not sb.paths.final_runs.exists(), "e não cria saída nem registra uso")
        code, d, lines = sb.run("f1", split="final", confirm_final=True)
        ok(code == 0 and d is not None, "com --confirm-final roda")
        ok(any("NÃO podem ser usados para ajustar" in l for l in lines), "imprime o aviso de que o final não serve para ajustar prompts")
        log = [json.loads(l) for l in sb.paths.final_runs.read_text(encoding="utf-8").splitlines()]
        ok(len(log) == 1 and log[0]["run_id"] == "f1" and log[0]["generate"] == "fake" and log[0]["cases"] == 9 and log[0]["date"] == "2026-11-04T12:00:00Z",
           "grava uma linha em final_runs.jsonl com data, run_id, gerador e nº de casos")
        ok(sb.results(d)["split"] == "final", "results.json marca o split final")
        code, d, lines = sb.run("f2", split="final", confirm_final=True, only=["final-foto-01", "final-falha-01"])
        log = [json.loads(l) for l in sb.paths.final_runs.read_text(encoding="utf-8").splitlines()]
        ok(len(log) == 2 and log[1]["cases"] == 2 and any("Uso nº 2" in l for l in lines), "cada uso acrescenta uma linha (a auditoria conta quantas vezes o final foi usado)")
        # final alterado sem lock: não roda e não registra
        fin = sb.load("final")
        orig = copy.deepcopy(fin)
        fin[0]["brief"] += " Mais um detalhe qualquer."
        sb.save("final", fin)
        code, d, lines = sb.run("f3", split="final", confirm_final=True)
        ok(code == 1 and d is None and len(sb.paths.final_runs.read_text(encoding="utf-8").splitlines()) == 2, "final alterado sem lock: run recusado e sem registro de uso")
        # dev não registra nada
        code, _, _ = sb.run("d1", only=["dev-foto-01"])
        ok(len(sb.paths.final_runs.read_text(encoding="utf-8").splitlines()) == 2, "run de dev não mexe na auditoria do final")
        # CLI
        sb.save("final", orig, relock=True)
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "--final-runs", str(sb.paths.final_runs),
                           "run", "--split", "final", "--generate", "fake", "--only", "final-foto-01", "--run-id", "f4")
        ok(code == 2 and "--confirm-final" in out, "CLI: final sem --confirm-final sai com 2")
        code, out, _ = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "--final-runs", str(sb.paths.final_runs),
                           "run", "--split", "final", "--generate", "fake", "--only", "final-foto-01", "--run-id", "f4", "--confirm-final")
        ok(code == 0 and len(sb.paths.final_runs.read_text(encoding="utf-8").splitlines()) == 3, "CLI: com --confirm-final roda e registra")
    real = REPO / "bench" / "final_runs.jsonl"
    ok(not real.exists() or real.stat().st_size == FINAL_RUNS_SIZE0, "os testes não tocaram em bench/final_runs.jsonl")


FINAL_RUNS_SIZE0 = (REPO / "bench" / "final_runs.jsonl").stat().st_size if (REPO / "bench" / "final_runs.jsonl").exists() else 0


# ---------------------------------------------------------------- openai: recusas e transporte injetado


def boom(env, budget):
    raise AssertionError("o cliente da OpenAI não pode ser criado quando há recusa")


def good_png_response(w, h, rid="req_1"):
    img = bench.fake_png("resp", w, h)
    return 200, {"x-request-id": rid}, json.dumps({"data": [{"b64_json": base64.b64encode(img).decode()}], "usage": {"total_tokens": 11, "detail": {"x": 1}}}).encode()


class Script:
    def __init__(self, *responses):
        self.responses, self.calls, self.lock = list(responses), [], threading.Lock()

    def __call__(self, method, url, headers, body, timeout):
        with self.lock:
            self.calls.append({"url": url, "body": body, "headers": headers})
            r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r(len(self.calls)) if callable(r) else r


def factory_for(transport):
    return lambda env, budget: pv.OpenAIImages("http://invalido.test/v1", "k-test", budgets=[budget], transport=transport, sleep=lambda s: None,
                                               rng=type("R", (), {"random": lambda self: 1.0})())


def test_openai_refusals():
    key = {"OPENAI_API_KEY": "sk-teste"}
    with sandbox() as sb:
        def attempt(label, expect_frag, **kw):
            lines = []
            kw.setdefault("env", {})
            code, d = bench.run_benchmark(sb.paths, "dev", "openai", run_id="o-" + label, only=["dev-foto-01"], client_factory=boom, log=lines.append, now=now, **kw)
            text = "\n".join(lines)
            ok(code == 2 and d is None and expect_frag in text and not (sb.paths.out_root / ("o-" + label)).exists(),
               f"openai recusado ({label}): sem criar cliente, sem saída")
            return text

        t = attempt("nada", "--max-calls", env={})
        ok("--i-approve-paid-calls" in t and "OPENAI_API_KEY" in t and "--max-calls" in t, "sem nenhuma exigência: as três faltas são listadas juntas")
        attempt("sem-aprovacao", "--i-approve-paid-calls", max_calls=3, env=key)
        attempt("max-zero", "N >= 1", max_calls=0, approve_paid=True, env=key)
        attempt("max-negativo", "N >= 1", max_calls=-2, approve_paid=True, env=key)
        attempt("sem-max", "N >= 1", approve_paid=True, env=key)
        attempt("sem-chave", "OPENAI_API_KEY", max_calls=3, approve_paid=True, env={})
        attempt("chave-vazia", "OPENAI_API_KEY", max_calls=3, approve_paid=True, env={"OPENAI_API_KEY": ""})
        # a recusa do final vale para openai também
        lines = []
        code, d = bench.run_benchmark(sb.paths, "final", "openai", max_calls=3, approve_paid=True, env=key, client_factory=boom, log=lines.append, now=now)
        ok(code == 2 and d is None and not sb.paths.final_runs.exists(), "openai no final sem --confirm-final: recusa e não registra uso")
        # pela CLI
        code, out, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "run", "--split", "dev", "--generate", "openai", "--only", "dev-foto-01",
                             env={}, factory=boom)
        ok(code == 2 and "RECUSADO" in out, "CLI: openai sem as três exigências sai com 2")
        code, out, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "run", "--split", "dev", "--generate", "openai", "--only", "dev-foto-01",
                             "--max-calls", "0", "--i-approve-paid-calls", env=key, factory=boom)
        ok(code == 2 and "N >= 1" in out, "CLI: --max-calls 0 é recusado")
        ok(not sb.paths.out_root.exists() or not any(sb.paths.out_root.iterdir()), "nenhuma pasta de saída criada pelas recusas")
    # a fábrica padrão nunca roda nas recusas: sem rede e sem socket
    ok(True, "nenhuma recusa tocou a rede (guarda de socket ativa durante toda a suíte)")


def test_openai_injected_transport():
    key = {"OPENAI_API_KEY": "sk-teste"}
    with sandbox() as sb:
        # orçamento esgota: 2 chamadas, 3 casos
        t = Script(lambda n: good_png_response(1536 if n < 3 else 1024, 1024, f"req_{n}"))
        lines = []
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=2, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o1",
                                      only=["dev-foto-01", "dev-ilustracao-01", "dev-cena-01"], log=lines.append, now=now)
        doc = sb.results(d)
        res = by_id(doc["cases"])
        ok(code == 0 and len(t.calls) == 2, "o transporte recebeu exatamente 2 chamadas (o orçamento)")
        ok([res[i]["status"] for i in ("dev-foto-01", "dev-ilustracao-01", "dev-cena-01")] == ["done", "done", "budget_exhausted"], "o 3º caso fica budget_exhausted (não rodou)")
        ok(res["dev-cena-01"]["paid_calls"] == 0 and res["dev-cena-01"]["image"] is None and "esgotado" in res["dev-cena-01"]["reason"], "e registra que nada foi enviado")
        ok(doc["paid_calls_total"] == 2 and doc["max_calls"] == 2 and doc["generate"] == "openai" and doc["quality"] == "medium", "results.json registra orçamento, chamadas pagas e qualidade")
        ok(res["dev-foto-01"]["request_ids"] == ["req_1"] and res["dev-foto-01"]["usage"] == {"total_tokens": 11} and res["dev-foto-01"]["paid_calls"] == 1, "request_id, usage numérico e chamada paga por caso")
        sent = json.loads(t.calls[0]["body"])
        ok(t.calls[0]["url"].endswith("/images/generations") and sent["prompt"] == by_id(sb.load("dev"))["dev-foto-01"]["brief"] and sent["size"] == "1536x1024"
           and sent["model"] == bench.DEFAULT_IMAGE_MODEL and sent["n"] == 1, "foi enviado o brief literal, o tamanho do caso e o modelo padrão")
        ok(not (d / "images" / "dev-cena-01.png").exists(), "sem imagem para o caso que não rodou")

        # retry seguro conta no orçamento
        t = Script(lambda n: (500, {}, b'{"error":{"message":"x"}}') if n == 1 else good_png_response(1536, 1024, "req_ok"))
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=3, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o2",
                                      only=["dev-foto-01"], log=lambda l: None, now=now)
        r = sb.results(d)["cases"][0]
        ok(r["status"] == "done" and r["attempts"] == 2 and r["paid_calls"] == 2 and len(t.calls) == 2, "uma repetição segura vira 2 tentativas e 2 chamadas pagas")

        # falha persistente consome o orçamento e para
        t = Script((500, {"x-request-id": "req_x"}, b'{"error":{"message":"fora do ar"}}'))
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=2, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o3",
                                      only=["dev-foto-01", "dev-foto-02"], log=lambda l: None, now=now)
        res = by_id(sb.results(d)["cases"])
        ok(len(t.calls) == 2 and res["dev-foto-01"]["status"] == "budget_exhausted" and res["dev-foto-01"]["paid_calls"] == 2, "falhas repetidas esgotam o orçamento sem passar dele")
        ok(res["dev-foto-02"]["status"] == "budget_exhausted" and res["dev-foto-02"]["paid_calls"] == 0, "o caso seguinte nem é tentado")
        t = Script((400, {}, b'{"error":{"message":"pedido ruim"}}'))
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=5, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o4",
                                      only=["dev-foto-01"], log=lambda l: None, now=now)
        r = sb.results(d)["cases"][0]
        ok(r["status"] == "failed" and "pedido ruim" in r["error"] and r["paid_calls"] == 1 and len(t.calls) == 1, "erro 400 vira failed com a causa, sem repetir")

        # com referência: usa edit (multipart), a base primeiro
        ref = bench.fake_png("minha-sala", 64, 64)
        sb.ref("dev-edicao-01", "sala-base", ref)
        t = Script(lambda n: good_png_response(1024, 1024, "req_e"))
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=2, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o5",
                                      only=["dev-edicao-01", "dev-fundo-01"], log=lambda l: None, now=now)
        res = by_id(sb.results(d)["cases"])
        ok(len(t.calls) == 1 and t.calls[0]["url"].endswith("/images/edits") and ref in t.calls[0]["body"] and b"Troque apenas a cor" in t.calls[0]["body"],
           "caso com referência vai para /images/edits com a imagem do usuário e o brief")
        ok(res["dev-edicao-01"]["status"] == "done" and res["dev-fundo-01"]["status"] == "skipped", "o caso sem referência continua pulado (não consome orçamento)")
        sb.ref("dev-fundo-01", "retrato-base", b"isto nao e uma imagem")
        t = Script(lambda n: good_png_response(1024, 1024))
        code, d = bench.run_benchmark(sb.paths, "dev", "openai", max_calls=2, approve_paid=True, env=key, client_factory=factory_for(t), run_id="o6",
                                      only=["dev-fundo-01"], log=lambda l: None, now=now)
        r = sb.results(d)["cases"][0]
        ok(r["status"] == "failed" and "não é PNG" in r["error"] and t.calls == [], "referência que não é imagem falha antes de gastar")


# ---------------------------------------------------------------- check


def test_check():
    with sandbox() as sb:
        sb.ref("dev-edicao-01", "sala-base")
        code, d, _ = sb.run("c1", only=["dev-foto-01", "dev-texto-01", "dev-edicao-01", "dev-fundo-01", "dev-diagrama-01", "dev-falha-01"])
        with no_tesseract():
            res = bench.check_run(sb.paths, "c1")
        cases = by_id(res["cases"])
        crit = {c["id"]: {k["id"]: k for k in c["criteria"]} for c in res["cases"]}
        ok((d / "checks.json").exists() and json.loads((d / "checks.json").read_text(encoding="utf-8"))["run_id"] == "c1", "check grava checks.json no run")
        ok(crit["dev-foto-01"]["tamanho"]["status"] == "pass" and "1536x1024" in crit["dev-foto-01"]["tamanho"]["evidence"], "auto:size compara o tamanho real do PNG com o esperado: pass com evidência")
        ok(all(k["status"] == "pending_human" for cid in ("dev-foto-01", "dev-texto-01", "dev-edicao-01") for k in crit[cid].values() if k["check"] == "human"), "critérios human de casos feitos ficam pending_human")
        ok(all(k["status"] == "not_run" for k in crit["dev-fundo-01"].values()) and cases["dev-fundo-01"]["status"] == "skipped", "caso pulado: todos os critérios not_run (nada passa sem imagem)")
        ok(crit["dev-texto-01"]["literais"]["status"] == "not_verified" and crit["dev-texto-01"]["literais"]["ocr_status"] == "unavailable", "auto:ocr sem tesseract: not_verified (nunca aprova)")
        ok(all(v["verdict"] == "not_verified" for v in crit["dev-texto-01"]["literais"]["verdicts"]), "e cada literal fica not_verified")
        ok(crit["dev-edicao-01"]["resto"]["status"] == "not_implemented" and "pixels" in crit["dev-edicao-01"]["resto"]["evidence"], "auto:preservation: not_implemented, dizendo o que falta")
        passed = [(c, k["id"]) for c, ks in crit.items() for k in ks.values() if k["status"] == "pass"]
        ok(passed and all(crit[c][k]["check"] == "auto:size" for c, k in passed), "o único critério que vira pass é auto:size (evidência de arquivo)")
        ok(res["summary"].get("not_verified", 0) >= 3 and "pending_human" in res["summary"], "resumo conta os status")

        # tamanho errado
        bad = d / "images" / "dev-foto-01.png"
        bad.write_bytes(bench.fake_png("x", 1024, 1024))
        with no_tesseract():
            res = bench.check_run(sb.paths, "c1")
        k = {c["id"]: {x["id"]: x for x in c["criteria"]} for c in res["cases"]}["dev-foto-01"]["tamanho"]
        ok(k["status"] == "fail" and "1024x1024" in k["evidence"] and "1536x1024" in k["evidence"], "tamanho diferente do esperado: fail, com os dois tamanhos")
        bad.write_bytes(b"\xff\xd8\xff" + b"\x00" * 30)
        with no_tesseract():
            res = bench.check_run(sb.paths, "c1")
        k = {c["id"]: {x["id"]: x for x in c["criteria"]} for c in res["cases"]}["dev-foto-01"]["tamanho"]
        ok(k["status"] == "not_verified", "arquivo que não é PNG: tamanho não verificável")
        bad.unlink()
        with no_tesseract():
            res = bench.check_run(sb.paths, "c1")
        k = {c["id"]: {x["id"]: x for x in c["criteria"]} for c in res["cases"]}["dev-foto-01"]["tamanho"]
        ok(k["status"] == "not_run", "imagem sumida: not_run")

        # OCR com backend injetado
        lits = by_id(sb.load("dev"))["dev-texto-01"]["text_literals"]

        def status_for(text, words=True):
            ws = [{"text": t, "conf": 95} for t in text.split()] if words else []
            res = bench.check_run(sb.paths, "c1", ocr_backend=lambda b, lang: {"text": text, "words": ws})
            return {c["id"]: {x["id"]: x for x in c["criteria"]} for c in res["cases"]}["dev-texto-01"]["literais"]["status"]

        ok(status_for("\n".join(lits)) == "ocr_match", "OCR leu tudo: ocr_match (não 'pass')")
        ok(status_for("\n".join(lits).replace("Sábado", "Sabado")) == "ocr_mismatch", "acento perdido: ocr_mismatch")
        ok(status_for("nada a ver") == "ocr_mismatch", "OCR leu outra coisa: ocr_mismatch")
        ok(status_for("\n".join(lits), words=False) == "ocr_mismatch", "OCR sem confiança por palavra não vira match")
        # benchmark mudou
        dev = sb.load("dev")
        dev[0]["brief"] += " Com um cachorro."
        sb.save("dev", dev)
        with no_tesseract():
            res = bench.check_run(sb.paths, "c1")
        ok(res["benchmark_changed_since_run"]["dev_sha256"] is True and res["benchmark_changed_since_run"]["final_sha256"] is False, "check avisa quando o benchmark mudou desde o run")
        ok(raises(lambda: bench.check_run(sb.paths, "nao-existe"), "run não encontrado"), "run inexistente: erro claro")
        with no_tesseract():
            code, out, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "check", "--run", "c1")
        ok(code == 0 and "pending_human=" in out, "CLI check imprime o resumo")


# ---------------------------------------------------------------- comparação cega


ONLY6 = ["dev-foto-01", "dev-foto-02", "dev-texto-01", "dev-produto-01", "dev-marketing-01", "dev-falha-01"]


def make_arms(sb, only=ONLY6, a_id="run-alfa", b_id="run-beta"):
    _, da, _ = sb.run(a_id, only=only)
    _, db, _ = sb.run(b_id, only=only)
    for img in (db / "images").glob("*.png"):  # braço B com imagens diferentes das do A
        cid = img.stem
        w, h = bench.png_dims(img.read_bytes())
        img.write_bytes(bench.fake_png(cid + "-braco-b", w, h))
    return da, db


def pack_files(out):
    return sorted(p for p in (out / "avaliador").iterdir())


def test_blind_pack():
    with sandbox() as sb:
        da, db = make_arms(sb)
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 5, out_dir=sb.t / "pack1", label_a="harness-secreto", label_b="outro-braco-secreto", now=now)
        files = pack_files(out)
        names = [p.name for p in files]
        ok((out / "key.json").exists() and "key.json" not in names, "key.json existe fora da pasta do avaliador")
        ok(set(key["assignment"]) == set(ONLY6), "todos os casos concluídos nos dois runs entram")
        ok(all(f"{c}_{pos}.png" in names for c in ONLY6 for pos in "XY") and "ratings_template.csv" in names, "arquivos <caso>_X/Y e ratings_template.csv")
        secrets = ["run-alfa", "run-beta", "harness-secreto", "outro-braco-secreto", "fake", "alfa", "beta", "seed", "key.json", "baseline", "braco-b"]
        leak = [(p.name, s) for p in files for s in secrets if s in p.name.lower() or s.encode() in p.read_bytes().lower()]
        ok(leak == [], f"nenhum arquivo do avaliador (nome ou conteúdo) cita braço, run, rótulo, seed ou chave: {leak[:3]}")
        csv_text = (out / "avaliador" / "ratings_template.csv").read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        ok(list(rows[0].keys()) == ["case_id", "brief", "preferred", "fidelity_x", "fidelity_y", "notes"] and {r["case_id"] for r in rows} == set(ONLY6), "o CSV tem as colunas esperadas e todos os casos")
        ok(all(r[k] == "" for r in rows for k in ("preferred", "fidelity_x", "fidelity_y", "notes")), "o CSV vem em branco (nenhuma coluna carrega o braço)")
        ok({r["case_id"]: r["brief"] for r in rows} == {c: by_id(sb.load("dev"))[c]["brief"] for c in ONLY6}, "e a coluna brief é o pedido do caso")
        kj = json.loads((out / "key.json").read_text(encoding="utf-8"))
        ok(kj["seed"] == 5 and kj["arms"]["A"]["label"] == "harness-secreto" and kj["arms"]["B"]["run_id"] == "run-beta", "key.json guarda seed e quem é cada braço")
        truth = 0
        for cid, asg in kj["assignment"].items():
            for pos in "XY":
                arm_dir = da if asg[pos] == "A" else db
                src = (arm_dir / "images" / f"{cid}.png").read_bytes()
                truth += (out / "avaliador" / f"{cid}_{pos}.png").read_bytes() == src
        ok(truth == 2 * len(ONLY6), "o mapeamento da chave descreve de fato qual imagem está em X e em Y")
        ok({a["X"] for a in kj["assignment"].values()} == {"A", "B"}, "a posição X não é sempre o mesmo braço (ordem sorteada)")
        ok(kj["row_order"] != sorted(kj["row_order"]) and sorted(kj["row_order"]) == sorted(ONLY6) and [r["case_id"] for r in rows] == kj["row_order"], "a ordem das linhas do CSV é embaralhada (e registrada na chave)")
        # seed
        key2, out2 = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 5, out_dir=sb.t / "pack2", now=now)
        ok(key2["assignment"] == key["assignment"] and key2["row_order"] == key["row_order"], "mesma seed, mesma atribuição e mesma ordem")
        ok((out2 / "avaliador" / "ratings_template.csv").read_text(encoding="utf-8") == csv_text, "mesma seed, CSV idêntico")
        key3, out3 = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 6, out_dir=sb.t / "pack3", now=now)
        ok(key3["assignment"] != key["assignment"] or key3["row_order"] != key["row_order"], "outra seed, outra atribuição ou ordem")
        # excluídos
        _, dc, _ = sb.run("run-gama", only=["dev-foto-01", "dev-foto-02", "dev-edicao-01"])
        key4, _ = bench.blind_pack(sb.paths, "run-alfa", "run-gama", 1, out_dir=sb.t / "pack4", now=now)
        ex = {e["id"]: e["reason"] for e in key4["excluded"]}
        ok(set(key4["assignment"]) == {"dev-foto-01", "dev-foto-02"} and "ausente no braço B" in ex["dev-texto-01"] and "sem imagem no braço B" in ex["dev-edicao-01"],
           "só entram casos concluídos nos dois; os demais ficam listados na chave com o motivo")
        # metadados
        meta = bench.fake_png("meta", 1536, 1024)
        i = meta.index(b"IDAT") - 4
        with_meta = meta[:i] + bench._chunk(b"tEXt", b"Software\x00gerador-secreto") + bench._chunk(b"caBX", b"c2pa-secreto") + meta[i:]
        (da / "images" / "dev-foto-01.png").write_bytes(with_meta)
        _, out5 = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 2, out_dir=sb.t / "pack5", now=now)
        blob = b"".join(p.read_bytes() for p in pack_files(out5))
        ok(b"gerador-secreto" not in blob and b"c2pa-secreto" not in blob and b"tEXt" not in blob, "metadados auxiliares do PNG (texto, proveniência) são removidos do pacote")
        ok(bench.png_dims((out5 / "avaliador" / "dev-foto-01_X.png").read_bytes()) == (1536, 1024), "e o PNG continua válido")
        # formato não PNG: aviso
        (db / "images" / "dev-foto-02.png").unlink()
        (db / "images" / "dev-foto-02.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 40)
        r = json.loads((db / "results.json").read_text(encoding="utf-8"))
        by_id(r["cases"])["dev-foto-02"]["image"] = "images/dev-foto-02.jpg"
        (db / "results.json").write_text(json.dumps(r), encoding="utf-8")
        key6, out6 = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 2, out_dir=sb.t / "pack6", now=now)
        ok(any("dev-foto-02" in w and "formatos diferentes" in w for w in key6["warnings"]) and any("não é PNG" in w for w in key6["warnings"]),
           "formatos diferentes ou não PNG geram aviso (a extensão e os metadados podem revelar a origem)")
        ok(all(b"warnings" not in p.read_bytes() for p in pack_files(out6)), "os avisos ficam só na chave")
        # recusas
        ok(raises(lambda: bench.blind_pack(sb.paths, "run-alfa", "run-alfa", 1, out_dir=sb.t / "p7"), "mesmo run"), "os dois braços não podem ser o mesmo run")
        ok(raises(lambda: bench.blind_pack(sb.paths, "run-alfa", "run-beta", 1, out_dir=out), "já existe"), "pasta de saída ocupada é recusada")
        ok(raises(lambda: bench.blind_pack(sb.paths, "run-alfa", "run-beta", "x", out_dir=sb.t / "p8"), "inteiro"), "seed que não é inteiro é recusada")
        ok(raises(lambda: bench.blind_pack(sb.paths, "run-alfa", "run-beta", 1, out_dir=sb.t / "p9", baseline_arm="B"), "--baseline-source"), "baseline sem descrição de como foi obtido é recusado")
        k, _ = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 1, out_dir=sb.t / "p10", baseline_arm="B", baseline_source="geradas manualmente pelo avaliador", now=now)
        ok(k["baseline_arm"] == "B" and "manualmente" in k["baseline_source"], "baseline declarado fica na chave, com a origem")
        _, dd, _ = sb.run("run-delta", only=["dev-ambiguo-01"])
        ok(raises(lambda: bench.blind_pack(sb.paths, "run-alfa", "run-delta", 1, out_dir=sb.t / "p11"), "nada para comparar"), "sem caso em comum: erro claro")
        # CLI
        code, outp, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "blind-pack", "--a", "run-alfa", "--b", "run-beta", "--seed", "9", "--out", str(sb.t / "pack12"))
        ok(code == 0 and "NÃO entregue" in outp and (sb.t / "pack12" / "key.json").exists(), "CLI blind-pack gera o pacote e avisa o que não entregar")


def write_ratings(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "brief", "preferred", "fidelity_x", "fidelity_y", "notes"])
        for r in rows:
            w.writerow([r[0], "pedido", *r[1:], ""])


def manual_key():
    return {"seed": 1, "arms": {"A": {"label": "braço-a", "run_id": "ra"}, "B": {"label": "braço-b", "run_id": "rb"}},
            "assignment": {"c1": {"X": "A", "Y": "B"}, "c2": {"X": "B", "Y": "A"}, "c3": {"X": "A", "Y": "B"}, "c4": {"X": "B", "Y": "A"}, "c5": {"X": "A", "Y": "B"}}}


def test_blind_score():
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        key = manual_key()
        rows = [("c1", "X", "4", "2"), ("c2", "X", "5", "3"), ("c3", "Y", "1", "4"), ("c4", "empate", "3", ""), ("c5", "", "", "")]
        write_ratings(t / "r.csv", rows)
        s = bench.score_ratings(bench.read_ratings(t / "r.csv"), key)
        a, b = s["arms"]["A"], s["arms"]["B"]
        ok((a["wins"], b["wins"], s["ties"], s["n_preference"]) == (1, 2, 1, 4), "preferência agregada por braço certo (X/Y traduzidos pela chave) e empates")
        ok((a["fidelity_n"], a["fidelity_mean"], b["fidelity_n"], b["fidelity_mean"]) == (3, 2.667, 4, 3.5), "fidelidade média e n por braço")
        ok(s["unrated_cases"] == ["c5"] and s["n_graded_cases"] == 4 and s["cases_in_pack"] == 5, "caso sem avaliação é contado à parte")
        text = bench.format_score(s)
        ok("braço A [braço-a]: 1 preferências" in text and "n=3" in text and "n=4" in text and "empates: 1" in text, "o texto mostra n por braço e empates")
        # preferência sem notas / notas sem preferência
        write_ratings(t / "r2.csv", [("c1", "Y", "", ""), ("c2", "", "5", "")])
        s = bench.score_ratings(bench.read_ratings(t / "r2.csv"), key)
        ok(s["arms"]["B"]["wins"] == 1 and s["arms"]["A"]["wins"] == 0 and s["arms"]["B"]["fidelity_n"] == 1 and s["n_preference"] == 1, "preferência sem notas e notas sem preferência são contadas separadamente")
        write_ratings(t / "r3.csv", [("c1", "x", "", "")])
        ok(bench.score_ratings(bench.read_ratings(t / "r3.csv"), key)["arms"]["A"]["wins"] == 1, "preferred aceita minúscula")
        # erros claros
        write_ratings(t / "vazio.csv", [("c1", "", "", ""), ("c2", "", "", "")])
        ok(raises(lambda: bench.score_ratings(bench.read_ratings(t / "vazio.csv"), key), "sem avaliações"), "ratings em branco: erro claro")
        write_ratings(t / "so_cabecalho.csv", [])
        ok(raises(lambda: bench.score_ratings(bench.read_ratings(t / "so_cabecalho.csv"), key), "sem avaliações"), "CSV só com cabeçalho: erro claro")
        write_ratings(t / "ruim.csv", [("c1", "Z", "9", "2"), ("zzz", "X", "", ""), ("c2", "X", "", ""), ("c2", "Y", "", "")])
        try:
            bench.score_ratings(bench.read_ratings(t / "ruim.csv"), key)
            msg = ""
        except bench.BenchError as e:
            msg = str(e)
        ok("preferred 'Z'" in msg and "fidelity_x '9'" in msg and "'zzz'" in msg and "repetido" in msg, "valores inválidos, caso desconhecido e repetido: todos listados, nada é ignorado")
        (t / "semcols.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        ok(raises(lambda: bench.score_ratings(bench.read_ratings(t / "semcols.csv"), key), "colunas"), "CSV sem as colunas do template: erro claro")
        ok(raises(lambda: bench.read_ratings(t / "nao-existe.csv"), "ilegível"), "arquivo inexistente: erro claro")
        (t / "k.json").write_text(json.dumps(key), encoding="utf-8")
        code, out, err = cli("blind-score", "--ratings", str(t / "vazio.csv"), "--key", str(t / "k.json"))
        ok(code == 2 and "sem avaliações" in err, "CLI blind-score sem ratings: código 2 e mensagem clara")
        code, out, err = cli("blind-score", "--ratings", str(t / "r.csv"), "--key", str(t / "k.json"))
        ok(code == 0 and "braço A" in out and "braço B" in out, "CLI blind-score imprime os dois braços")
        (t / "k2.json").write_text("[]", encoding="utf-8")
        code, _, err = cli("blind-score", "--ratings", str(t / "r.csv"), "--key", str(t / "k2.json"))
        ok(code == 2 and "key.json" in err, "chave inválida: erro claro")
    # ponta a ponta: o avaliador sempre prefere o braço A, olhando só X/Y
    with sandbox() as sb:
        make_arms(sb)
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 11, out_dir=sb.t / "pk", now=now)
        rows = [(cid, next(p for p in "XY" if asg[p] == "A"), "5" if asg["X"] == "A" else "2", "2" if asg["X"] == "A" else "5") for cid, asg in key["assignment"].items()]
        write_ratings(sb.t / "pk" / "avaliador" / "ratings.csv", rows)
        s = bench.score_ratings(bench.read_ratings(sb.t / "pk" / "avaliador" / "ratings.csv"), bench.load_key(out / "key.json"))
        ok(s["arms"]["A"]["wins"] == len(rows) and s["arms"]["B"]["wins"] == 0 and s["arms"]["A"]["fidelity_mean"] == 5.0 and s["arms"]["B"]["fidelity_mean"] == 2.0,
           "ponta a ponta: preferências dadas pela posição são atribuídas ao braço certo")


# ---------------------------------------------------------------- relatório


PHRASE = "paridade ainda não demonstrada"


def test_report():
    with sandbox() as sb:
        da, db = make_arms(sb)
        with no_tesseract():
            bench.check_run(sb.paths, "run-alfa")
        md = bench.build_report(sb.paths, "run-alfa", now=now)
        ok(PHRASE in md, "relatório sem baseline contém a frase 'paridade ainda não demonstrada'")
        ok("2026-11-04T12:00:00Z" in md and "run-alfa" in md and "fake-local" in md and "Condições" in md and "Limitações" in md, "traz data, run, modelo, condições e limitações")
        ok("NÃO é automatizado" in md and "ordem aleatória" in md and "obtidas legitimamente" in md, "registra que a comparação com o ChatGPT exige referências legítimas e ordem aleatória, e que a interface não é automatizada")
        ok("gerador **fake**" in md and "não mede qualidade" in md, "run fake é declarado como teste de pipeline")
        ok(all(f"| {c} |" in md for c in ONLY6) and "chamadas pagas" in md and "latência" in md and "tentativas" in md, "tabela de custo, latência e tentativas por caso aceito")
        ok("pending_human" in md and "NÃO são aprovação" in md, "resume as checagens sem chamar nada de aprovado")
        ok("Nenhuma avaliação cega" in md, "sem ratings, diz que não há comparação cega")
        md2 = bench.build_report(sb.paths, "run-beta", now=now)
        ok("ainda não foi executado" in md2 and PHRASE in md2, "sem checks.json, diz que nenhuma checagem foi aplicada")
        for bad in ("superior ao ChatGPT", "igual ao ChatGPT", "supera o ChatGPT", "paridade demonstrada"):
            ok(bad not in md, f"nunca afirma '{bad}'")
        # com ratings, mas arms fake e baseline declarado: continua sem paridade
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 3, out_dir=sb.t / "pk", baseline_arm="B", baseline_source="descrição qualquer", now=now)
        rows = [(cid, "X", "4", "3") for cid in key["assignment"]]
        write_ratings(sb.t / "rt.csv", rows)
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt.csv", key_path=out / "key.json", now=now)
        ok(PHRASE in md and "Comparação cega" in md and "preferências" in md, "baseline declarado mas com braços fake: continua 'paridade ainda não demonstrada'")
        ok(raises(lambda: bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt.csv", now=now), "--key"), "ratings sem chave: erro claro")
        _, dg, _ = sb.run("run-gama", only=ONLY6)
        ok(raises(lambda: bench.build_report(sb.paths, "run-gama", ratings=sb.t / "rt.csv", key_path=out / "key.json", now=now), "não pertence"), "chave de outro par de runs é recusada")

        # baseline externo legítimo: braço A vira 'openai' (simulado no results.json) e B 'external'
        def tag(run_dir, generate, **extra):
            r = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
            r["generate"] = generate
            r.update(extra)
            (run_dir / "results.json").write_text(json.dumps(r), encoding="utf-8")

        tag(db, "external", source="imagens geradas manualmente pelo avaliador, com conta própria")
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 4, out_dir=sb.t / "pk1b", baseline_arm="B", baseline_source="imagens geradas manualmente", now=now)
        write_ratings(sb.t / "rt1b.csv", [(cid, "X", "4", "3") for cid in key["assignment"]])
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt1b.csv", key_path=out / "key.json", now=now)
        ok(PHRASE in md, "baseline externo legítimo contra um braço fake (teste de pipeline): continua 'paridade ainda não demonstrada'")
        tag(da, "openai")
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 4, out_dir=sb.t / "pk2", baseline_arm="B", baseline_source="imagens geradas manualmente pelo avaliador", now=now)
        write_ratings(sb.t / "rt2.csv", [(cid, "X", "4", "3") for cid in key["assignment"]])
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt2.csv", key_path=out / "key.json", now=now)
        ok(PHRASE not in md and "não afirma paridade nem superioridade" in md and "manualmente" in md, "com baseline externo declarado e avaliação cega real: sem a frase, mas sem afirmar paridade nem superioridade")
        write_ratings(sb.t / "rt3.csv", [(cid, "", "4", "3") for cid in key["assignment"]])
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt3.csv", key_path=out / "key.json", now=now)
        ok(PHRASE in md, "só notas de fidelidade, sem preferência cega: ainda sem paridade demonstrada")
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 4, out_dir=sb.t / "pk3", now=now)  # baseline não declarado
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt2.csv", key_path=out / "key.json", now=now)
        ok(PHRASE in md, "braço externo não declarado como baseline: sem paridade demonstrada")
        tag(da, "openai")
        tag(db, "openai")
        key, out = bench.blind_pack(sb.paths, "run-alfa", "run-beta", 4, out_dir=sb.t / "pk4", baseline_arm="B", baseline_source="x", now=now)
        md = bench.build_report(sb.paths, "run-alfa", ratings=sb.t / "rt2.csv", key_path=out / "key.json", now=now)
        ok(PHRASE in md, "baseline declarado, mas que não é um run 'external': não vale")
        # final e CLI
        code, d, _ = sb.run("fin1", split="final", confirm_final=True, only=["final-foto-01"])
        ok("NÃO podem ser usados para ajustar" in bench.build_report(sb.paths, "fin1", now=now) or "não podem ser usados para ajustar" in bench.build_report(sb.paths, "fin1", now=now), "relatório de run do final repete a regra de não ajustar")
        code, outp, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "report", "--run", "run-beta", "--out", str(sb.t / "rel.md"))
        ok(code == 0 and PHRASE in (sb.t / "rel.md").read_text(encoding="utf-8"), "CLI report grava o markdown")
        code, outp, err = cli("--bench-dir", str(sb.t / "bench"), "--out-root", str(sb.t / "out"), "report", "--run", "run-beta")
        ok(code == 0 and PHRASE in outp, "CLI report sem --out imprime")
        # run com pulados e falhas aparece listado
        code, d, _ = sb.run("run-pul", only=["dev-fundo-01", "dev-foto-01"])
        md = bench.build_report(sb.paths, "run-pul", now=now)
        ok("Casos que não rodaram" in md and "dev-fundo-01 (skipped)" in md, "relatório lista os casos pulados com o motivo")


def test_png_utils():
    png = bench.fake_png("a", 40, 20)
    ok(bench.png_dims(png) == (40, 20) and bench.png_dims(b"nao") is None, "png_dims lê o IHDR")
    i = png.index(b"IDAT") - 4
    dirty = png[:i] + bench._chunk(b"eXIf", b"gps") + bench._chunk(b"iTXt", b"x") + png[i:]
    clean, removed = bench.strip_png_metadata(dirty)
    ok(clean == png and sorted(removed) == ["eXIf", "iTXt"], "strip_png_metadata remove só os blocos auxiliares e devolve o PNG original")
    ok(bench.strip_png_metadata(b"\xff\xd8\xffxxxx") == (b"\xff\xd8\xffxxxx", None), "JPEG volta intacto, sinalizado como não limpo")
    ok(bench.strip_png_metadata(png[:-20])[1] is None, "PNG truncado volta intacto")
    ok(bench.fake_png("a", 40, 20) == png and bench.fake_png("b", 40, 20) != png, "fake_png é determinístico e depende do id")


def main():
    socket.socket.connect = no_network  # qualquer tentativa de rede derruba o teste
    socket.create_connection = no_network
    for fn in (test_real_bench_files, test_validate_failures, test_schema_rules, test_run_fake, test_final_gate, test_openai_refusals,
               test_openai_injected_transport, test_check, test_blind_pack, test_blind_score, test_report, test_png_utils):
        print(f"== {fn.__name__}")
        fn()
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
