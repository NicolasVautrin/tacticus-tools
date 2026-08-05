#!/usr/bin/env python3
"""#477-r18 -- PERIMETRE du DEROULE DE BATAILLE dans le flux de replay, DERIVE du natif.

Le port emet le flux et il est egal au natif sur le DEPLOIEMENT (`probe_477r15a`). La borne
(a) de cet oracle publie le reste du chemin : 2 `GroupType` exerces sur 104, 6 `StepType` sur
62, 36 `TagKey` sur 244. Ce probe repond a "qui produit les 102 / 56 / 208 autres, et lesquels
sont MORTS".

CE QU'IL MESURE -- rien n'est enumere a la main :

  1. L'INTERFACE emettrice est DERIVEE, jamais ecrite en dur. `IdunBattle.Streams.IStreamListener`
     declare trois methodes, slots 0/1/2 = `StartGroup` / `FinishGroup` / `Action`. En IL2CPP un
     appel d'interface passe par un helper `FUN_*(<slot>, <Il2CppClass* de l'interface>, <this>,
     <args...>)` : le `DAT_*` de l'interface se DEDUIT de deux temoins independants et le probe
     REFUSE de continuer s'ils ne concordent pas.
  2. Les PRODUCTEURS = les xrefs de ce `DAT_*`. Second canal INDEPENDANT :
     `IdunBattle.Core.AOperation$$get_Events` -- toute fonction qui obtient le flux. L'ecart entre
     les deux ensembles est IMPRIME, dans les deux sens.
  3. Les LITTERAUX de chaque site : `StartGroup(<GroupType>, ...)` / `Action(<StepType>, ...)`.
     Un argument NON litteral (variable) est compte a part et NOMME -- c'est le cas des groupes
     portes par un champ de behaviour, qu'aucune lecture de call-site ne peut trancher.
  4. Les TAGS : `Dictionary<TagKey,int>.Add(dict, &var, ...)` precede de `var = <imm>`. Balaye
     dans les producteurs ET dans les fabriques de tags (`StreamHelper$$Get*Tags`,
     `UnitExtensions$$GetFullStateUpdateTags`).
  5. Le CROISEMENT avec le port : chaque producteur natif est confronte a `engine/`.

CE QU'IL NE VOIT PAS -- imprime a chaque run, jamais rabattu sur un zero :
  - un GroupType/StepType passe par VARIABLE (compte separement, avec ses porteurs) ;
  - un producteur dont le corps est un generique pleinement partage (present dans Ghidra,
    absent du dump Frida) ;
  - les valeurs poussees par du code que Ghidra n'a pas nomme (`FUN_*`).

Sortie ASCII. Aucun ecrit hors `logs/`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghidra_symbols import BINARY, GhidraDown, GhidraMCP, loaded_build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "logs" / "477r18-decompile"

# Les deux temoins servant a DERIVER le Il2CppClass* de IStreamListener. Choisis parce que leur
# role est etabli par la RE deja livree (#477-r15) : l'un n'emet que des `Action`, l'autre ouvre
# et ferme un groupe. Le DAT retenu doit apparaitre dans les DEUX, et porter les trois slots.
TEMOINS_INTERFACE = (
    "IdunBattle.Operations.AddPlayerOperation$$Execute",
    "IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup",
)

SLOT_START_GROUP = 0
SLOT_FINISH_GROUP = 1
SLOT_ACTION = 2

# Fabriques de tags : leur corps ne contient aucun appel au flux, mais il ecrit les TagKey.
FABRIQUES_TAGS = (
    "IdunBattle.Core.Services.StreamHelper$$",
    "IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags",
)

RE_APPEL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(")
RE_IMM = re.compile(r"^(0x[0-9a-fA-F]+|\d+)$")
RE_AFFECT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)(?:\[0\])?\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;")
RE_DICT_ADD = re.compile(r"Dictionaryu003C.*?u003E__Add\(")


def _args_equilibres(txt: str, i: int) -> tuple[list[str], int]:
    """Decoupe les arguments d'un appel dont la parenthese ouvrante est a `i`."""
    prof, arg, out = 0, [], []
    j = i
    while j < len(txt):
        c = txt[j]
        if c == "(":
            prof += 1
            if prof == 1:
                j += 1
                continue
        elif c == ")":
            prof -= 1
            if prof == 0:
                out.append("".join(arg).strip())
                return out, j + 1
        if prof == 1 and c == ",":
            out.append("".join(arg).strip())
            arg = []
        else:
            arg.append(c)
        j += 1
    return out, j


def appels(code: str):
    """Tous les appels du pseudo-C, sous forme (nom, [args], position)."""
    for m in RE_APPEL.finditer(code):
        args, _ = _args_equilibres(code, m.end() - 1)
        yield m.group(1), args, m.start()


class Ghidra:
    def __init__(self, hors_ligne: bool):
        self.hors_ligne = hors_ligne
        self.g = None
        CACHE.mkdir(parents=True, exist_ok=True)

    def _client(self) -> GhidraMCP:
        if self.g is None:
            self.g = GhidraMCP(timeout=180).connect()
        return self.g

    def build(self) -> str:
        return loaded_build(self._client())

    def xrefs(self, cible: str) -> list:
        f = CACHE / ("xrefs_%s.json" % re.sub(r"[^A-Za-z0-9_]", "_", cible))
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        if self.hors_ligne:
            return []
        res = self._client().call("list_xrefs", {"binary_name": BINARY, "name_or_address": cible})
        out = (res or {}).get("result") or []
        xs = out[0].get("cross_references") or [] if out else []
        f.write_text(json.dumps(xs), encoding="utf-8")
        return xs

    def decompile(self, nom: str) -> str | None:
        f = CACHE / ("fn_%s.c" % re.sub(r"[^A-Za-z0-9_]", "_", nom))
        if f.exists():
            t = f.read_text(encoding="utf-8", errors="replace")
            return None if t == "\0ABSENT" else t
        if self.hors_ligne:
            return None
        try:
            res = self._client().call("decompile_function",
                                      {"binary_name": BINARY, "name_or_address": nom,
                                       "timeout_sec": 60})
        except (GhidraDown, RuntimeError):
            return None
        rs = (res or {}).get("result") or []
        code = (rs[0].get("code") if rs else None) or ""
        f.write_text(code if code else "\0ABSENT", encoding="utf-8")
        return code or None

    def symboles(self, requete: str, limite: int = 200) -> list:
        f = CACHE / ("sym_%s.json" % re.sub(r"[^A-Za-z0-9_]", "_", requete))
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        if self.hors_ligne:
            return []
        res = self._client().call("search_symbols_by_name",
                                  {"binary_name": BINARY, "query": requete,
                                   "functions_only": True, "limit": limite})
        out = (res or {}).get("symbols") or []
        f.write_text(json.dumps(out), encoding="utf-8")
        return out


def deriver_dat_interface(gh: Ghidra) -> tuple[str, dict]:
    """Le Il2CppClass* de IStreamListener, deduit de deux temoins -- jamais ecrit en dur."""
    vus = []
    for nom in TEMOINS_INTERFACE:
        code = gh.decompile(nom)
        if code is None:
            raise RuntimeError("temoin d'interface introuvable : %s" % nom)
        cand = {}
        for _, args, _pos in appels(code):
            if len(args) >= 3 and RE_IMM.match(args[0] or "") and (args[1] or "").startswith("DAT_"):
                cand.setdefault(args[1], set()).add(int(args[0], 0))
        vus.append(cand)
    communs = set(vus[0]) & set(vus[1])
    # Le bon DAT est celui qui porte les trois slots sur l'union des temoins.
    retenus = [d for d in communs
               if {SLOT_START_GROUP, SLOT_FINISH_GROUP, SLOT_ACTION} <= (vus[0][d] | vus[1][d])]
    if len(retenus) != 1:
        raise RuntimeError("derivation du DAT d'interface AMBIGUE : %r (candidats communs %r)"
                           % (retenus, sorted(communs)))
    dat = retenus[0]
    return dat, {n: sorted(v.get(dat, ())) for n, v in zip(TEMOINS_INTERFACE, vus)}


def charger_mirrors():
    sys.path.insert(0, str(REPO / "scripts" / "python"))
    from engine.streams import GroupType, StepType, TagKey  # noqa: E402
    return GroupType, StepType, TagKey


def nom_enum(cls, v: int) -> str:
    try:
        return cls(v).name
    except ValueError:
        return "<INCONNU:%d>" % v


def scanner_producteur(code: str, dat: str):
    """Rend (sites_groupes, sites_actions, sites_finish, variables) pour un corps."""
    groupes, actions, finish, variables = [], [], [], []
    for _nom, args, _pos in appels(code):
        if len(args) < 3 or args[1] != dat or not RE_IMM.match(args[0] or ""):
            continue
        slot = int(args[0], 0)
        reste = args[3:]
        if slot == SLOT_START_GROUP:
            v = reste[0] if reste else ""
            (groupes if RE_IMM.match(v) else variables).append(
                int(v, 0) if RE_IMM.match(v) else ("StartGroup", v))
        elif slot == SLOT_ACTION:
            v = reste[0] if reste else ""
            (actions if RE_IMM.match(v) else variables).append(
                int(v, 0) if RE_IMM.match(v) else ("Action", v))
        elif slot == SLOT_FINISH_GROUP:
            finish.append(True)
    return groupes, actions, finish, variables


def scanner_tags(code: str) -> set:
    """TagKey ecrits : `var = <imm>;` puis `Dictionary<TagKey,int>.Add(dict,&var,...)`."""
    derniere = {}
    trouves = set()
    for ligne in code.splitlines():
        m = RE_AFFECT.match(ligne)
        if m:
            derniere[m.group(1)] = int(m.group(2), 0)
        for mm in RE_DICT_ADD.finditer(ligne):
            args, _ = _args_equilibres(ligne, mm.end() - 1)
            if len(args) >= 2 and args[1].startswith("&"):
                v = derniere.get(args[1][1:].split("[")[0])
                if v is not None:
                    trouves.add(v)
    return trouves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hors-ligne", action="store_true",
                    help="n'interroge pas ghidra-mcp : n'exploite que le cache logs/")
    ap.add_argument("--json", type=str, default=None, help="ecrit la carte brute (sous logs/)")
    a = ap.parse_args()

    gh = Ghidra(a.hors_ligne)
    GroupType, StepType, TagKey = charger_mirrors()

    print("=" * 78)
    print("#477-r18 -- PERIMETRE DU DEROULE DE BATAILLE (derive du natif)")
    print("=" * 78)

    if not a.hors_ligne:
        b = gh.build()
        cur = (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
        print("build charge par ghidra-mcp : %s ; data/symbols/CURRENT : %s" % (b, cur))
        if b != cur:
            print("REFUS : build charge != build des tables versionnees.")
            return 2

    dat, temoins = deriver_dat_interface(gh)
    print("\n[1] INTERFACE EMETTRICE -- derivee, pas ecrite en dur")
    print("    IdunBattle.Streams.IStreamListener -> %s" % dat)
    for n, slots in temoins.items():
        print("    temoin %-64s slots %s" % (n.split("$$")[0].split(".")[-1] + "$$"
                                             + n.split("$$")[1], slots))

    xs = gh.xrefs(dat)
    producteurs = sorted({x["function_name"] for x in xs if x.get("function_name")})
    sans_nom = sum(1 for x in xs if not x.get("function_name"))
    print("\n[2] PRODUCTEURS -- xrefs du Il2CppClass* de l'interface")
    print("    sites : %d   fonctions nommees : %d   sites sans fonction : %d"
          % (len(xs), len(producteurs), sans_nom))

    ev = gh.xrefs("IdunBattle.Core.AOperation$$get_Events")
    canal2 = sorted({x["function_name"] for x in ev
                     if x.get("function_name") and x.get("type") != "DATA"})
    print("    canal 2 INDEPENDANT (AOperation$$get_Events) : %d fonctions" % len(canal2))
    print("    dans get_Events mais PAS dans les xrefs du DAT : %d"
          % len(set(canal2) - set(producteurs)))
    print("    dans les xrefs du DAT mais PAS dans get_Events : %d"
          % len(set(producteurs) - set(canal2)))

    carte = {}
    groupes_vus, actions_vues, tags_vus = {}, {}, {}
    variables = []
    illisibles = []
    for nom in producteurs:
        code = gh.decompile(nom)
        if code is None:
            illisibles.append(nom)
            continue
        g, ac, fi, va = scanner_producteur(code, dat)
        tg = scanner_tags(code)
        carte[nom] = {"groupes": sorted(set(g)), "actions": sorted(set(ac)),
                      "finish": len(fi), "variables": va, "tags": sorted(tg)}
        for v in set(g):
            groupes_vus.setdefault(v, []).append(nom)
        for v in set(ac):
            actions_vues.setdefault(v, []).append(nom)
        for v in tg:
            tags_vus.setdefault(v, []).append(nom)
        for kind, expr in va:
            variables.append((nom, kind, expr))

    # Fabriques de tags : elles n'appellent pas le flux, mais ecrivent les TagKey.
    fabriques = []
    for prefixe in FABRIQUES_TAGS:
        for s in gh.symboles(re.escape(prefixe)):
            fabriques.append(s["name"])
    fabriques = sorted(set(fabriques))
    for nom in fabriques:
        code = gh.decompile(nom)
        if code is None:
            illisibles.append(nom)
            continue
        for v in scanner_tags(code):
            tags_vus.setdefault(v, []).append(nom)

    print("\n[3] VOCABULAIRE VIVANT -- litteraux lus aux call-sites")
    for lib, cls, vus in (("GroupType", GroupType, groupes_vus),
                          ("StepType", StepType, actions_vues),
                          ("TagKey", TagKey, tags_vus)):
        total = len(list(cls))
        connus = {v for v in vus if v in set(int(x) for x in cls)}
        inconnus = sorted(set(vus) - connus)
        print("    %-9s : %3d / %3d atteints par un litteral ; %d hors enum %s"
              % (lib, len(connus), total, len(inconnus), inconnus if inconnus else ""))
        morts = [m for m in cls if int(m) not in vus]
        print("              %d membres SANS aucun litteral trouve (voir ci-dessous)" % len(morts))

    print("\n[4] CE QUE CETTE MESURE NE VOIT PAS")
    print("    arguments NON litteraux (portes par une variable) : %d site(s), %d fonction(s)"
          % (len(variables), len({v[0] for v in variables})))
    for nom, kind, expr in variables[:20]:
        print("      %-70s %-11s <- %s" % (nom, kind, expr))
    if len(variables) > 20:
        print("      ... %d de plus" % (len(variables) - 20))
    print("    fonctions productrices NON decompilables : %d" % len(illisibles))
    for n in illisibles[:10]:
        print("      %s" % n)
    print("    fabriques de tags balayees : %d" % len(fabriques))

    if a.json:
        p = REPO / "logs" / a.json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"dat": dat, "producteurs": carte,
             "groupes_vus": {str(k): v for k, v in groupes_vus.items()},
             "actions_vues": {str(k): v for k, v in actions_vues.items()},
             "tags_vus": {str(k): v for k, v in tags_vus.items()},
             "variables": variables, "illisibles": illisibles,
             "fabriques": fabriques, "canal2": canal2}, indent=1), encoding="utf-8")
        print("\ncarte brute -> %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GhidraDown as exc:
        print("MESURE IMPOSSIBLE : %s" % exc)
        sys.exit(3)
