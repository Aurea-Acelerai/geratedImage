#!/usr/bin/env python3
"""Versões de imagem: quem é filha de quem, com modelo, parâmetros e versão do prompt. Só stdlib.

Cada imagem gerada vira um registro em `versions/<escopo>/<id>.json` (pela interface Store, então vale no disco, na
memória e no Blob). O registro NÃO guarda bytes de imagem, chave nem o texto do briefing (o briefing já está no turno da
conversa): guarda só o hash dele (`prompt_sha`) e a versão do system prompt do designer (`prompt_version`).

- parent_id: a imagem GERADA que serviu de base (edição ou variação); None se nasceu do zero ou de um anexo.
- base_kind: "generated" (imagem anterior da conversa), "attachment" (imagem anexada usada como alvo) ou None.
- A genealogia (lineage) segue parent_id até a raiz, detecta ciclo e avisa quando falta um registro no caminho.
"Mude só a cor" funciona assim: o chat resolve a base ANTES da chamada (botão Editar, alvo citado ou última imagem), a base
vira entrada marcada com `src_image_id`, e `base_of` extrai daí o pai que fica gravado.
"""
import hashlib, json, re, time

ID = re.compile(r"[a-z0-9]{1,64}")
SCOPE = re.compile(r"[a-z0-9_-]{1,64}")
BASE_KINDS = ("alvo", "variacao")
MAX_DEPTH = 100


def sha12(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]


def base_of(inputs):
    """Descreve a imagem-base de uma lista de entradas: {"kind": generated|attachment|None, "image_id", "asset_id"}.
    Duas bases são ambiguidade (o Runner já recusa antes de gastar); aqui devolve a primeira e marca `ambiguous`."""
    bases = [x for x in (inputs or []) if isinstance(x, dict) and x.get("kind") in BASE_KINDS]
    if not bases:
        return {"kind": None, "image_id": None, "asset_id": None, "ambiguous": False}
    b = bases[0]
    out = {"ambiguous": len(bases) > 1, "image_id": None, "asset_id": None}
    if b.get("src_image_id"):
        out.update(kind="generated", image_id=b["src_image_id"])
    else:
        out.update(kind="attachment", asset_id=b.get("id"))
    return out


class VersionLog:
    def __init__(self, store_fn):
        self._store = store_fn  # callable -> Store (o chat troca o Store nos testes)

    @staticmethod
    def _key(scope, iid):
        if not SCOPE.fullmatch(str(scope)) or not ID.fullmatch(str(iid)):
            raise ValueError(f"escopo ou id de versão inválido: {scope!r}, {iid!r}")
        return f"versions/{scope}/{iid}.json"

    def add(self, scope, rec):
        """Cria o registro. Recusa id repetido, auto-pai e pai inválido (nada de gravar lixo que quebre a genealogia)."""
        iid, pid = rec.get("id"), rec.get("parent_id")
        key = self._key(scope, iid)
        if pid is not None:
            self._key(scope, pid)  # valida o formato
            if pid == iid:
                raise ValueError("uma versão não pode ser pai de si mesma")
        if self._store().exists(key):
            raise ValueError(f"versão {iid} já registrada")
        rec = {**rec, "created": rec.get("created") or time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        self._store().write_text(key, json.dumps(rec, ensure_ascii=False, sort_keys=True), "application/json")
        return rec

    def get(self, scope, iid):
        key = self._key(scope, iid)
        if not self._store().exists(key):
            return None
        return json.loads(self._store().read_text(key))

    def update(self, scope, iid, **fields):
        """Acrescenta campos (nota, aprovação). Não muda id nem parent_id."""
        if "id" in fields or "parent_id" in fields:
            raise ValueError("id e parent_id não mudam depois de gravados")
        rec = self.get(scope, iid)
        if rec is None:
            raise KeyError(iid)
        rec.update(fields)
        self._store().write_text(self._key(scope, iid), json.dumps(rec, ensure_ascii=False, sort_keys=True), "application/json")
        return rec

    def children(self, scope, iid):
        out = []
        for k in self._store().list(f"versions/{scope}/"):
            try:
                r = json.loads(self._store().read_text(k))
            except (ValueError, OSError):
                continue
            if r.get("parent_id") == iid:
                out.append(r["id"])
        return sorted(out)

    def lineage(self, scope, iid):
        """Do ancestral mais antigo até iid: {"chain": [ids], "complete": bool, "reason": str|None}.
        complete=False quando falta o registro de um pai, há ciclo ou a cadeia passa de MAX_DEPTH."""
        chain, seen, cur = [], set(), iid
        while cur is not None:
            if cur in seen:
                return {"chain": list(reversed(chain)), "complete": False, "reason": f"ciclo em {cur}"}
            if len(chain) >= MAX_DEPTH:
                return {"chain": list(reversed(chain)), "complete": False, "reason": "cadeia longa demais"}
            rec = self.get(scope, cur)
            if rec is None:
                return {"chain": list(reversed(chain)), "complete": False, "reason": f"sem registro de {cur}"}
            seen.add(cur)
            chain.append(cur)
            cur = rec.get("parent_id")
        return {"chain": list(reversed(chain)), "complete": True, "reason": None}
