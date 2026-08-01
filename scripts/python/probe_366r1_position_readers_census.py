"""#366-r1 -- RECENSEMENT des lecteurs du foyer POSITION, pour l'etat << unite sans position >>.

POURQUOI CE PROBE EXISTE. Porter `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute`
introduit un etat que le port ne produisait pour AUCUNE unite : une unite VIVANTE, sur le plateau
une frame plus tot, qui n'a plus ni `PositionComponent` ni pied. L'enonce du residu annoncait
<< ~200 sites lisent ce foyer >> et en faisait le vrai cout du portage. Ce probe MESURE ce cout au
lieu de l'estimer -- et c'est ce qui a permis de le REFUTER : le foyer etait deja sain, le trou
etait dans l'ECRIVAIN (`set_unit_feet`, dont la branche << liste vide >> laissait la
`PositionComponent` en place). Sans cette mesure, on aurait durci 291 call-sites au lieu d'un.

CE QU'IL COMPTE. Le foyer n'a pas UNE porte mais CINQ, et n'en balayer qu'une (le grep evident,
`get_component(PositionComponent)`) laisse passer les deux tiers des lecteurs :

    A  e.get_component(PositionComponent)   -> None
    B  get_unit_feet(state, uid)            -> []
    C  get_main_tile(state, uid)            -> None
    D  unit["pos"] / unit.get("pos")        -> None      (dict DSL / `LiveUnit`)
    E  _pos(<unit>)                         -> [] / None (selecteurs)

Pour chacune il marque RISQUE le call-site dont la ligne -- ou les trois suivantes -- DEREFERENCE
le resultat sans garde apparente : `[0]`, `.col` / `.row`, `["col"]`, ou un passage direct a
`hexgeo.distance`. L'heuristique est deliberement PESSIMISTE (elle sur-liste) : un faux positif se
leve en lisant le site, un faux negatif serait un crash offline.

MESURE DU 2026-08-01 (build `rnca9r7q6c`, avant le portage) : A=148 B=12 C=1 D=83 E=47, soit
**291** call-sites, **4** signales par l'heuristique et **0** risque REEL -- les quatre ont ete LUS
un par un et sont gardes (cf. `EXEMPTIONS` ci-dessous, chacune avec la garde qui la couvre).

⚠ Le seuil n'est PAS un nombre. Un `--allow <n>` aurait laisse passer en silence un CINQUIEME site,
et c'est exactement la degradation que ce probe existe pour attraper. On NOMME donc chaque
exemption : le probe rougit des qu'un site sort de la liste, et la liste ne bouge qu'en lisant le
code. Une exemption dont le TEXTE a change rougit aussi (elle est ancree sur le code, pas sur un
numero de ligne, qui bouge a chaque edition du fichier).

Usage (depuis scripts/python) :
    python probe_366r1_position_readers_census.py [--verbose]

rc = 0 si tout site signale est une exemption NOMMEE et si toutes le sont encore, 1 sinon.
Aucun RPC, aucune session live, aucun runner : lecture de sources pure. ASCII only (cp1252).
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` sec.3.
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"

# Marqueurs de garde cherches dans la fenetre : ils couvrent le `if x is None`, le repli
# `x or default`, le ternaire, le `continue`/`return` de boucle et le `getattr` defensif.
GATES = ("is None", "is not None", " or ", " and ", "if not ", "getattr(", " else ",
         "continue", "return")

PORTS = {
    "A get_component(PositionComponent)": re.compile(
        r"\.get_component\s*\(\s*PositionComponent\s*\)"),
    "B get_unit_feet":                    re.compile(r"\bget_unit_feet\s*\("),
    "C get_main_tile":                    re.compile(r"\bget_main_tile\s*\("),
    "D unit-pos-dict":                    re.compile(r"""(\[["']pos["']\]|\.get\(["']pos["']\))"""),
    "E _pos(":                            re.compile(r"(?<![A-Za-z_])_pos\s*\("),
}

DEREF = re.compile(r"""(\[\s*0\s*\]|\.col\b|\.row\b|\[["'](col|row)["']\]|hexgeo\.distance)""")

WINDOW = 4          # la ligne + les 3 suivantes

# EXEMPTIONS NOMMEES -- `(fichier, fragment de code) -> la garde qui le couvre`. Chacune a ete LUE.
# L'ancre est le FRAGMENT DE CODE, jamais le numero de ligne : une edition en amont du fichier ne
# doit pas faire rougir, mais une reecriture du site, si.
EXEMPTIONS = {
    ("ai/context.py",
     'epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]'):
        "`enemies = _enemies(units)` -- `_enemies` filtre deja `u.get('pos')` (2 call-sites)",
    ("ai/state_bridge.py",
     'tgt_epos = [(e["pos"]["col"], e["pos"]["row"]) for e in _tgt]'):
        "`_tgt = [e for e in enemies if e.get('pos') and ...]`, ligne PRECEDENTE",
    ("playbook/scene.py",
     'pos_by_id = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")}'):
        "garde IN-LINE `if u.get('pos')` dans la comprehension elle-meme",
}


def census(root: Path):
    """Rend `(counts, risky)` : `{porte: n}` et `[(porte, chemin, ligne, texte)]`."""
    counts = {k: 0 for k in PORTS}
    risky: list = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            lines = io.open(p, encoding="utf-8").read().splitlines()
            rel = os.path.relpath(p, root).replace("\\", "/")
            in_doc = False
            for i, ln in enumerate(lines):
                # Saut GROSSIER des docstrings : une erreur ici ne peut que SUR-lister (les
                # docstrings de ce depot citent abondamment les noms de composants).
                if ln.count('"""') % 2 == 1:
                    in_doc = not in_doc
                    continue
                if in_doc or ln.lstrip().startswith("#"):
                    continue
                for name, rx in PORTS.items():
                    if not rx.search(ln):
                        continue
                    counts[name] += 1
                    window = "\n".join(lines[i:i + WINDOW])
                    if DEREF.search(window) and not any(g in window for g in GATES):
                        risky.append((name, rel, i + 1, ln.strip()[:110]))
    return counts, risky


def main() -> int:
    verbose = "--verbose" in sys.argv
    if not ENGINE.is_dir():
        print("[366-r1] ECHEC : %s introuvable" % ENGINE)
        return 1
    counts, risky = census(ENGINE)
    total = sum(counts.values())
    print("[366-r1] recensement des lecteurs du foyer POSITION (%s)" % ENGINE.name)
    for name in PORTS:
        print("   %-34s %4d" % (name, counts[name]))
    print("   %-34s %4d" % ("TOTAL", total))

    unknown, seen = [], set()
    for name, rel, ln, txt in risky:
        key = next((k for k in EXEMPTIONS if k[0] == rel and k[1] in txt), None)
        if key is None:
            unknown.append((name, rel, ln, txt))
        else:
            seen.add(key)
            if verbose:
                print("   [exempte] %s:%d  <- %s" % (rel, ln, EXEMPTIONS[key]))
    stale = [k for k in EXEMPTIONS if k not in seen]

    print("[366-r1] signales par l'heuristique : %d | exemptions NOMMEES couvertes : %d/%d | "
          "NON EXPLIQUES : %d" % (len(risky), len(seen), len(EXEMPTIONS), len(unknown)))
    for name, rel, ln, txt in unknown:
        print("   [%s] %s:%d  %s" % (name.split()[0], rel, ln, txt))
    for rel, frag in stale:
        print("   [PERIMEE] %s -- le fragment exempte n'existe plus : %s" % (rel, frag[:80]))

    if unknown:
        print("[366-r1] ECHEC : %d dereferencement(s) de position NON EXPLIQUE(S). LIRE le site : "
              "soit la garde vit en amont (-> l'ajouter aux EXEMPTIONS, en la NOMMANT), soit il "
              "leve sur une unite sans position -- cast de 1011, MoW hors plateau, ou capture ou "
              "`decisionView` rend `pos = null`." % len(unknown))
        return 1
    if stale:
        print("[366-r1] ECHEC : %d exemption(s) PERIMEE(S) -- le code exempte a change, la garde "
              "est a re-verifier avant de mettre a jour la liste." % len(stale))
        return 1
    print("[366-r1] OK -- le foyer supporte l'etat << unite sans position >>.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
