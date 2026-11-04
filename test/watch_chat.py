#!/usr/bin/env python3
"""Acompanha o chat em tempo real: uma linha por evento. Só stdlib; só lê (nunca altera nada).

  python3 watch_chat.py              # começa do "agora" e fica rodando (Ctrl+C para sair)
  python3 watch_chat.py --from-start # reimprime o registro inteiro antes de seguir

Fontes (na pasta de dados, test/ ou CHAT_DATA_DIR):
- logs/events.jsonl      etapas, erros e avisos de cada mensagem + erros de JavaScript do navegador
- chat_out/<cliente>/    imagens novas (funciona mesmo com um servidor mais antigo, sem registro de eventos)
- conversations/...      o último turno gravado de cada conversa
"""
import json, os, pathlib, sys, time

DATA = pathlib.Path(os.environ.get("CHAT_DATA_DIR") or pathlib.Path(__file__).resolve().parent)
EVENTS = DATA / "logs" / "events.jsonl"


def fmt(ev):
    k, t, job = ev.get("kind"), ev.get("t", ""), (ev.get("job") or "")[:4]
    if k == "start":
        melhorias = ev.get("melhorias") or {}
        off = [n for n, v in melhorias.items() if not v]
        anexos = ", ".join(f"{a['tipo']}:{a['nome']}" for a in ev.get("anexos", [])) or "nenhum"
        return (f"[{t}] ▶ NOVA MENSAGEM {job} (API: {ev.get('provedor')}; conv {str(ev.get('conv'))[:6]}, modo {ev.get('modo')}, {ev.get('tamanho')})\n"
                f"           texto: {ev.get('texto')}\n           anexos: {anexos}" + (f" | melhorias DESLIGADAS: {', '.join(off)}" if off else "")
                + (f" | edit_of: {ev.get('edit_of')}" if ev.get("edit_of") else ""))
    if k == "step":
        extra = f"  [{ev['image_url'].rsplit('/', 1)[-1]}]" if ev.get("image_url") else ""
        if ev.get("prompt"):
            return f"[{t}]   {job} {ev.get('text')}\n           BRIEFING: {' '.join(str(ev['prompt']).split())[:600]}"
        return f"[{t}]   {job} {ev.get('text')}{extra}"
    if k == "done":
        if ev.get("tipo") == "text":
            return f"[{t}] ❓ {job} o designer perguntou: {ev.get('pergunta')}"
        sel = "APROVADA" if ev.get("approved") else "REPROVADA"
        return (f"[{t}] ✔ FIM {job} {sel} nota {ev.get('score')} | intenção {ev.get('intent')} | pacotes {ev.get('packs')} | "
                f"vetos {ev.get('veto')} | {ev.get('segundos')}s" + (f"\n           AVISOS: {ev.get('avisos')}" if ev.get("avisos") else "")
                + (f"\n           resolvido: {ev.get('resolved')}" if ev.get("resolved") else ""))
    if k == "erro":
        return f"[{t}] ✖ ERRO {job}: {ev.get('erro')}"
    if k == "ui":
        return f"[{t}] ⚠ NAVEGADOR ({ev.get('tipo')}): {ev.get('mensagem')}"
    return f"[{t}] {ev}"


def main():
    pos = 0 if "--from-start" in sys.argv else (EVENTS.stat().st_size if EVENTS.exists() else 0)
    seen_img = {str(p) for p in (DATA / "chat_out").glob("*/*")} if "--from-start" not in sys.argv else set()
    conv_m = {str(p): p.stat().st_mtime for p in (DATA / "conversations").glob("*/*.json")} if "--from-start" not in sys.argv else {}
    print(f"acompanhando {DATA} (eventos, imagens e conversas)", flush=True)
    while True:
        try:
            if EVENTS.exists() and EVENTS.stat().st_size > pos:
                with open(EVENTS, "r", encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    try:
                        print(fmt(json.loads(line)), flush=True)
                    except json.JSONDecodeError:
                        pass
            for p in sorted((DATA / "chat_out").glob("*/*")):
                if str(p) not in seen_img:
                    seen_img.add(str(p))
                    print(f"[{time.strftime('%H:%M:%S')}] 🖼 imagem nova: {p.name} ({p.stat().st_size // 1024} KB)", flush=True)
            for p in (DATA / "conversations").glob("*/*.json"):
                m = p.stat().st_mtime
                if conv_m.get(str(p)) != m:
                    conv_m[str(p)] = m
                    try:
                        turns = json.loads(p.read_text(encoding="utf-8")).get("turns", [])
                    except (json.JSONDecodeError, OSError):
                        continue
                    if turns:
                        t = turns[-1]
                        print(f"[{time.strftime('%H:%M:%S')}] 🧠 memória {p.stem[:6]}: turno {t['n']} {t['intent']} → {str(t['resolved'])[:200]}"
                              + (f" | PERGUNTA: {t['question']}" if t.get("question") else f" | nota {t.get('score')}"), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"(observador: {type(e).__name__}: {e})", flush=True)
        time.sleep(0.7)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
