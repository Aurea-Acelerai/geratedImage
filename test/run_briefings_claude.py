#!/usr/bin/env python3
"""Testa o system prompt com o Claude (Sonnet) via CLI `claude -p`, sem chave de API.

Só a etapa do briefing: o Sonnet não gera imagem. Para cada caso do eval_set.json o
prompts/designer-imagegen.system.md vira o system prompt (substitui o padrão, sem ferramentas)
e o modelo devolve o briefing em JSON. Saída: test/out/briefings-<timestamp>.md

  python3 run_briefings_claude.py                 # os 6 casos, em paralelo
  python3 run_briefings_claude.py --case 3
  python3 run_briefings_claude.py --request "banner com modelo ao pôr do sol"
  python3 run_briefings_claude.py --model opus
"""
import argparse, json, pathlib, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run_comparison as rc  # noqa: E402

TAIL = '\n\nResponda SOMENTE JSON: {"use_case":"...","role":"hero|cell","prompt":"<prompt final em inglês no schema>"}'


def briefing(request, client_ctx, model="sonnet", size=None, timeout=240, feedback=None, prev=None):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(rc.load_system_prompt(client_ctx, request=request, size=size))
        sp = f.name
    user = f"Pedido: {request}" + (f"\nTamanho da peça: {size}" if size else "")
    if feedback:
        user += (f"\n\nA versão anterior foi reprovada. Prompt anterior:\n{prev}\n\n"
                 f"Corrija APENAS isto: {feedback}\nRepita as invariantes.")
    user += TAIL
    r = subprocess.run(["claude", "-p", "--model", model, "--system-prompt-file", sp, "--tools", "",
                        "--disable-slash-commands", "--output-format", "text", user],
                       capture_output=True, text=True, timeout=timeout)
    pathlib.Path(sp).unlink(missing_ok=True)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[:400] or f"claude saiu com {r.returncode}")
    txt = r.stdout.strip()
    if txt.startswith("```"):
        txt = txt.strip("`").removeprefix("json").strip()
    return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default=str(ROOT / "client_71.json"))
    ap.add_argument("--cases", default=str(ROOT / "eval_set.json"))
    ap.add_argument("--case", type=int)
    ap.add_argument("--request")
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    ctx = json.loads(pathlib.Path(a.client).read_text(encoding="utf-8"))
    cases = json.loads(pathlib.Path(a.cases).read_text(encoding="utf-8"))
    if a.request:
        cases = [{"id": 0, "request": a.request}]
    elif a.case:
        cases = [c for c in cases if c["id"] == a.case]

    def one(c):
        try:
            return c, briefing(c["request"], ctx, a.model, c.get("size")), None
        except Exception as e:  # noqa: BLE001
            return c, None, f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, cases))

    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    path = out / f"briefings-{time.strftime('%Y%m%d-%H%M%S')}.md"
    md = [f"# Briefings com {a.model}\n\nSystem prompt: `{rc.SYSTEM_PROMPT_PATH.name}` · cliente: {ctx.get('name')}\n"]
    for c, b, err in res:
        md.append(f"\n## Caso {c['id']}: {c['request']}\n" + (f"tags: {', '.join(c.get('tags', []))} · tamanho: {c.get('size')}\n" if c.get("tags") else ""))
        md.append(f"**ERRO:** {err}\n" if err else f"`use_case={b.get('use_case')}` `role={b.get('role')}`\n\n```\n{b.get('prompt')}\n```\n")
    path.write_text("\n".join(md), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
