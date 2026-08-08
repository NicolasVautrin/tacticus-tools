#!/usr/bin/env python3
"""#594 -- MESURE : par ou arrivent le MASQUE et le TYPE D'ATTAQUE d'une ability ?

CE QU'IL MESURE, ET POURQUOI CETTE QUESTION
-------------------------------------------
`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` sont les deux donnees OBLIGATOIRES du registre
`ABILITY_CLASSES` (cf. CLAUDE.md). Ce sont aussi les deux ou l'on a MESURE des ports faux :
le masque recopie d'un preset statique au lieu du litteral visible, et trois abilities
entrees au registre sans leur `AbilityAttackType`, decouvertes seulement au re-jeu apres
rebase d'un autre agent. Les deux fautes ont la meme forme : un LITTERAL au site d'appel que
rien n'extrait, et qu'il faut donc lire a l'oeil dans du decompile.

Ce probe MESURE la structure de ce gisement. Il ne GARDE rien -- le cliquet qui garde le
zero de couverture est `probe_181_targeting_gaps.py`, et il porte sur le PORT, pas sur le
natif.

CE QUE LA MESURE A ETABLI (2026-08-08, build rnca9r7q6c) -- a RE-DERIVER, pas a citer
--------------------------------------------------------------------------------------
IL N'Y A PAS D'ARBRE D'APPEL A COUVRIR. Il y a UNE fonction :

    IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(
        targetingOptions : IdunBattle.Core.Services.TargetingOptions,
        abilityAttackType: IdunBattle.Entities.Abilities.AbilityAttackType)

135 des 139 `.ctor` d'ability l'appellent, TOUS avec exactement 3 arguments. Les deux
donnees convergent donc sur les arguments 2 et 3 d'UN SEUL site. L'extracteur n'a pas a
parcourir un graphe : il lit une liste d'arguments.

DEUX HYPOTHESES REFUTEES EN COURS DE MESURE, toutes deux miennes :

  1. << la forme preset est l'exception >>. FAUX : 53 des 139 (38 %) ne touchent AUCUN
     symbole `TargetingOptions` au premier saut.
  2. << ces 53 recopient un preset statique, et l'adresse `DAT_` porte le masque >>.
     REFUTE par la mesure suivante : `DAT_1833ffc10` est partage par 50 d'entre eux et
     porte 12 masques DIFFERENTS. Une adresse unique ne peut pas etre 12 masques. Ils
     construisent ailleurs et passent a la base, comme les 84 autres.

Ce qui tient : 145/145 adresses `FUN_` resolues contre la table offline (100 %), et deux
formes que la doctrine ne nommait pas -- des fabriques STATIQUES nommees
(`TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`, `$$CustomLokiNormalAttackOptions`).

TRI-ETAT. Sans ghidra-mcp, le probe rend rc=2 et le DIT. Il ne rend jamais un zero.
Le corpus decompile est cache sous `logs/` (ce qu'on ECRIT), jamais sous `data/`.

Usage:
    python probe_594_ctor_litteraux.py            # cache si present, sinon rapatrie
    python probe_594_ctor_litteraux.py --refaire  # ignore le cache

ASCII strict (console cp1252).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mcp_ghidra  # noqa: E402
from symbols_layout import build_dir, current_build  # noqa: E402

CACHE = RACINE / "logs" / "probe_594_ctor_corpus.jsonl"
BINAIRE = "GameAssembly.dll"
LOT = 8

RE_FUN = re.compile(r"\bFUN_([0-9a-f]{6,})\b")
RE_NOMME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{6,})\s*\(")
RE_TO = re.compile(r"TargetingOptions", re.I)
RE_TO_CTOR = re.compile(r"TargetingOptions_+ctor", re.I)
RE_BASE = re.compile(r"AActiveAbility_+ctor\s*\(")

#: Ce qui doit changer pour que cette mesure change d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py",),
    "build": True,
    "toujours": False,
    "raison": "Il croise le registre `ABILITY_CLASSES` (donc la fermeture d'import de "
              "`engine.runner.abilities.handler`) avec le DECOMPILE du build courant. Les "
              "deux bougent : une ability entrant au registre change le corpus, un "
              "changement de build change les adresses et les corps.",
}


def build_courant() -> str:
    return (RACINE / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def table_adresses(build: str) -> dict[str, str]:
    """adresse -> symbole, depuis `ghidra/functions.tsv` (indexee par ADRESSE)."""
    out: dict[str, str] = {}
    p = RACINE / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            c = ligne.rstrip("\n").split("\t")
            if len(c) >= 2:
                out[c[0].lower().lstrip("0")] = c[1]
    return out


def temoins(adresses: dict[str, str]) -> tuple[list[dict], list[tuple]]:
    """Les entrees du registre, appariees a leur `.ctor` natif par le nom COURT de classe."""
    from engine.runner.abilities.handler import ABILITY_CLASSES

    ctors: dict[str, list[str]] = defaultdict(list)
    for sym in adresses.values():
        if sym.endswith("$$.ctor"):
            ctors[sym[: -len("$$.ctor")].rsplit(".", 1)[-1]].append(sym[: -len("$$.ctor")])

    trouves, sans = [], []
    for atype, cls in sorted(ABILITY_CLASSES.items()):
        cands = ctors.get(cls.__name__, [])
        if not cands:
            sans.append((atype, cls.__name__, cls.__module__.rsplit(".", 1)[-1]))
            continue
        trouves.append({
            "atype": atype, "classe": cls.__name__, "symbole": cands[0],
            "n_candidats": len(cands),
            "masque": repr(getattr(cls, "TARGETING_OPTIONS", None)),
            "attack": repr(getattr(cls, "ABILITY_ATTACK_TYPE", None)),
        })
    return trouves, sans


def rapatrier(cibles: list[dict]) -> list[dict] | None:
    """Decompile en LOT et ECRIT SUR DISQUE. Rend `None` si le serveur est injoignable."""
    if mcp_ghidra.disponible() is None:
        return None
    m = mcp_ghidra.Mcp()
    m.ouvrir()
    noms = [t["symbole"] + "$$.ctor" for t in cibles]
    out, t0 = [], time.time()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with io.open(CACHE, "w", encoding="utf-8", newline="\n") as fh:
        for i in range(0, len(noms), LOT):
            paquet = noms[i:i + LOT]
            try:
                res = m.decompiler(BINAIRE, paquet)
            except Exception as ex:                                  # noqa: BLE001
                print("   lot %2d : ECHEC -- %s" % (i // LOT + 1, str(ex)[:90]))
                continue
            for j, e in enumerate(res):
                if j >= len(paquet) or e.get("error"):
                    continue
                # On se rattache par la POSITION dans le lot : le `name` rendu par le
                # serveur est TRONQUE (<classe abregee>-<adresse>) et n'est pas une cle.
                d = dict(cibles[i + j])
                d["code"] = e.get("code") or ""
                d["signature"] = e.get("signature")
                out.append(d)
                fh.write(json.dumps(d, ensure_ascii=True) + "\n")
            print("   lot %2d/%d : cumul %d" % (i // LOT + 1,
                                                (len(noms) + LOT - 1) // LOT, len(out)))
    print("   %d corps rapatries en %.0f s, %d caracteres SUR DISQUE (0 en contexte)"
          % (len(out), time.time() - t0, sum(len(x["code"]) for x in out)))
    return out


def sortants(code: str, adresses: dict[str, str]) -> set[str]:
    """Les symboles appeles : les `FUN_<hex>` RESOLUS, plus les appels deja nommes."""
    out = set()
    for h in RE_FUN.findall(code):
        s = adresses.get(h.lower().lstrip("0"))
        if s:
            out.add(s)
    for n in RE_NOMME.findall(code):
        if not n.startswith("FUN_"):
            out.add(n)
    return out


def arite_base(code: str) -> int | None:
    """Nombre d'arguments passes a `AActiveAbility$$.ctor`, ou None s'il n'est pas appele."""
    m = RE_BASE.search(code)
    if not m:
        return None
    i, prof, n = m.end(), 1, 1
    while i < len(code) and prof > 0:
        c = code[i]
        if c in "([":
            prof += 1
        elif c in ")]":
            prof -= 1
            if prof == 0:
                break
        elif c == "," and prof == 1:
            n += 1
        i += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refaire", action="store_true", help="ignorer le cache de corpus")
    args = ap.parse_args()

    build = build_courant()
    adresses = table_adresses(build)
    cibles, sans = temoins(adresses)
    print("[594] build %s -- table de %d adresses" % (build, len(adresses)))
    print("[594] registre : %d appariee(s) a un `.ctor` natif, %d SANS"
          % (len(cibles), len(sans)))
    for atype, nom, mod in sans:
        print("        SANS `.ctor` : %5s %s (%s)" % (atype, nom, mod))
    print("        ^ l'ABSENCE d'un symbole ne prouve rien : IL2CPP deduplique les corps")
    print("          triviaux, un corps partage n'a qu'UN proprietaire dans la table.")

    corpus = None
    if CACHE.exists() and not args.refaire:
        corpus = [json.loads(l) for l in io.open(CACHE, encoding="utf-8")]
        print("[594] corpus relu du cache : %d corps (%s)" % (len(corpus), CACHE))
    if corpus is None:
        print("[594] rapatriement par ghidra-mcp, en lots de %d ..." % LOT)
        corpus = rapatrier(cibles)
    if corpus is None:
        print("")
        print("[594] ghidra-mcp INJOIGNABLE -- PAS MESURE. Aucun verdict rendu.")
        print("[594] Demarrer : pwsh -File C:\\Users\\nicolasv\\ghidra-mcp\\start-ghidra-mcp.ps1")
        return 2

    # ---------------------------------------------------------------- ventilation
    direct, via_fabrique, ni = [], [], []
    for x in corpus:
        s = sortants(x["code"], adresses)
        if any(RE_TO_CTOR.search(n) for n in s):
            direct.append(x)
        elif any(RE_TO.search(n) for n in s):
            via_fabrique.append(x)
        else:
            ni.append(x)

    print("")
    print("[594] PAR OU ARRIVE LE MASQUE, AU PREMIER SAUT")
    print("        ctor `TargetingOptions` appele directement : %3d" % len(direct))
    print("        fabrique STATIQUE nommee                   : %3d" % len(via_fabrique))
    for x in via_fabrique:
        for n in sortants(x["code"], adresses):
            if RE_TO.search(n):
                print("           %s -> %s" % (x["classe"], n))
    print("        aucun symbole `TargetingOptions`           : %3d" % len(ni))

    arites = Counter()
    for x in corpus:
        arites[arite_base(x["code"])] += 1
    print("")
    print("[594] L'ARETE UNIQUE -- appel a `AActiveAbility$$.ctor`")
    for n, k in sorted(arites.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        libelle = "PAS D'APPEL" if n is None else "%d argument(s)" % n
        print("        %-16s : %3d site(s)" % (libelle, k))
    print("        signature declaree (frida/methods.tsv) : (targetingOptions, "
          "abilityAttackType)")
    print("        => les DEUX donnees obligatoires du registre convergent sur UN site.")

    # les `FUN_` se resolvent-ils tous ?
    vus = sum(len(RE_FUN.findall(x["code"])) for x in corpus)
    perdus = sum(1 for x in corpus for h in RE_FUN.findall(x["code"])
                 if h.lower().lstrip("0") not in adresses)
    print("")
    print("[594] RESOLUTION : %d appel(s) `FUN_`, %d non resolu(s) (%.1f %%)"
          % (vus, perdus, 100.0 * perdus / max(1, vus)))

    print("")
    print("[594] MESURE, pas un cliquet -- rc 0 quelle que soit la ventilation.")
    print("[594] NON VU : une ability dont le `.ctor` est un corps DEDUPLIQUE (absente de")
    print("      la table, cf. ci-dessus), et tout site qui construirait le masque hors du")
    print("      `.ctor` -- la mesure porte sur le `.ctor`, elle ne prouve rien au-dela.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
