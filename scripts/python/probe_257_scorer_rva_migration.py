#!/usr/bin/env python3
"""#257 -- ou pointent les cibles en dur de `scorer-damage-trace.ts` apres un changement de build ?

POURQUOI
--------
`frida/hooks/features/scorer-damage-trace.ts` hooke ~15 cibles par ADRESSE parce que ce sont des
corps gshared / iterateurs que `findMethod` ne resout pas. Le fichier assume cette dette et la
signale, mais RIEN ne disait ce que chaque adresse devient au build suivant -- il fallait les
re-transcrire une par une, a la main, ce qui a deja produit au moins une faute (voir plus bas).

METHODE : ALLER-RETOUR, pour PROUVER l'identification au lieu de la supposer.
  1. adresse ANCIENNE -> symbole, dans la table du build de reference (reverse : la plus grande
     adresse <= la cible, ce qui capte aussi un point INTERNE a une fonction) ;
  2. symbole -> adresse NEUVE, dans la table du build courant (forward, exact).
Tout ce qui ne fait pas l'aller-retour proprement est SIGNALE -- jamais devine.

CE QUE LA SONDE NE FAIT PAS : elle ne reecrit pas le .ts. Quatre categories de sortie ne se
traitent pas de la meme facon :
  * OK              -> transcription mecanique sure ;
  * OK (+offset)    -> point INTERNE a une fonction : l'offset ne survit que si le corps n'a pas
                       bouge d'un octet. A RELIRE AU DECOMPILE, jamais a recopier ;
  * SYMBOLE DISPARU -> soit la fonction a disparu, soit NOTRE CHAINE ne la nomme plus (cas des
                       generiques pleinement partages : 4015 symboles -> 0 au 2026-07-29 ; cause
                       et voies de retablissement mesurees dans #259 --
                       `docs/rl/case-259-couverture-gshared.md`, sonde
                       `probe_259_gshared_coverage.py`. Deux des cinq « perdu » d'ici en
                       viennent, et ne redeviendront transcriptibles que par la) ;
  * FUN_/DAT_       -> l'adresse EST le seul « nom ». Le CLAUDE.md dit de les LISTER, pas de les
                       maquiller. Prefixees '!' en sortie.

FAUTE DEJA TROUVEE PAR CETTE SONDE : `RVA_VALUE_MOD_MODIFY` valait 0x1fadfc0 alors que son propre
commentaire citait `ValueModification.Modify @180fadfc0` -- dont la RVA est 0xfadfc0. La constante
pointait en plein corps d'une classe sans rapport (`FPSCounterData$$set_Average+0x60`). Latente
parce que c'est un fallback derriere un `findMethod` qui reussit. C'est la faute que decrit
`feedback_rva_transcription_from_va` : stocker la VA COMPLETE, calculer `va - BASE` EN CODE.

Sortie 0 = toutes les cibles font l'aller-retour sans ambiguite ; 1 sinon.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = 0x180000000

# Les cibles telles qu'ecrites dans scorer-damage-trace.ts, avec la valeur du build de REFERENCE.
# (nom de la constante TS, valeur, est-ce une RVA (True) ou une VA complete (False))
CIBLES: list[tuple[str, int, bool]] = [
    ("RVA_COMPOSED_UTILITY",            0x1101600,   True),
    ("RVA_GET_MULT_DMG_BONUS[0]",       0x1005210,   True),
    ("RVA_PROFILE_B0",                  0x11c9d10,   True),
    ("RVA_PROFILE_B1",                  0x11c9e50,   True),
    ("RVA_ATTACK_IFACE",                0x327ff80,   True),
    ("RVA_IFACE_DMG",                   0x3287db8,   True),
    ("RVA_FUN_INVOKE",                  0x31950,     True),
    ("RVA_OVERRIDE_RETADDR",            0x103489e,   True),
    ("RVA_CALC_ACTION_UTILITY",         0x1406ee0,   True),
    ("RVA_ELEVATION_LEAF",              0x11019a0,   True),
    ("RVA_CALC_TILE_PRED",              0x1408740,   True),
    ("RVA_VALUE_MOD_MODIFY",            0x1fadfc0,   True),
    ("RVA_PREDICT_ATTACK_RAW",          0x1032fb0,   True),
    ("LEAF_HOOKS_VA[TileEffects]",      0x1810fbe50, False),
    ("LEAF_HOOKS_VA[CapturePointTile]", 0x1811000a0, False),
]


def charge(build: str) -> tuple[list[int], dict[int, str], dict[str, list[int]]]:
    p = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not p.is_file():
        raise SystemExit("table absente : %s" % p)
    par_addr: dict[int, str] = {}
    par_nom: dict[str, list[int]] = {}
    with p.open(encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            a, _, nom = ligne.rstrip("\n").partition("\t")
            try:
                addr = int(a, 16)
            except ValueError:
                continue
            nom = nom.strip()
            par_addr[addr] = nom
            par_nom.setdefault(nom, []).append(addr)
    return sorted(par_addr), par_addr, par_nom


def reverse(tries: list[int], par_addr: dict[int, str], va: int):
    i = bisect.bisect_right(tries, va) - 1
    if i < 0:
        return None, None
    base = tries[i]
    return par_addr[base], va - base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="gqfc5mff6c",
                    help="build de REFERENCE : celui pour lequel les constantes ont ete ecrites")
    ap.add_argument("--build", default=None, help="build cible ; defaut = data/symbols/CURRENT")
    args = ap.parse_args()

    neuf = args.build or (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    print("reference : %s" % args.ref)
    print("cible     : %s" % neuf)
    if args.ref == neuf:
        print("")
        print("ATTENTION : reference == cible, l'aller-retour est trivialement l'identite.")
    print("")

    tv, av, _ = charge(args.ref)
    _, an, nn = charge(neuf)
    print("%s : %d fonctions | %s : %d fonctions" % (args.ref, len(av), neuf, len(an)))
    print("")

    exact = interne = perdu = ambigu = 0
    for nom_ts, val, est_rva in CIBLES:
        va = (val + BASE) if est_rva else val
        sym, off = reverse(tv, av, va)
        if sym is None:
            print("  %-32s VA %#x -> AUCUN symbole dans %s" % (nom_ts, va, args.ref))
            perdu += 1
            continue

        anonyme = sym.startswith("FUN_") or sym.startswith("DAT_")
        cibles_neuves = nn.get(sym, [])
        if not cibles_neuves:
            etat, neuf_txt = "SYMBOLE DISPARU", "-"
            perdu += 1
        elif len(cibles_neuves) > 1:
            etat = "AMBIGU (%d adresses)" % len(cibles_neuves)
            neuf_txt = ", ".join("%#x" % a for a in cibles_neuves[:4])
            ambigu += 1
        elif off:
            na = cibles_neuves[0]
            etat, neuf_txt = "OK (+%#x) A RELIRE" % off, "%#x -> cible %#x" % (na, na + off)
            interne += 1
        else:
            etat, neuf_txt = "OK", "%#x" % cibles_neuves[0]
            exact += 1

        print("%s%-32s %s" % ("! " if anonyme else "  ", nom_ts, etat))
        print("      symbole : %s%s" % (sym, ("+%#x" % off) if off else ""))
        print("      %s : %#x   |   %s : %s" % (args.ref, va, neuf, neuf_txt))
        if est_rva and len(cibles_neuves) == 1:
            print("      RVA neuve : %#x" % (cibles_neuves[0] + (off or 0) - BASE))
        print("")

    print("---")
    print("exact=%d  point-interne=%d  perdu=%d  ambigu=%d  (total %d)"
          % (exact, interne, perdu, ambigu, len(CIBLES)))
    print("'!' = resout sur un placeholder FUN_/DAT_ : a LISTER, pas a maquiller (CLAUDE.md).")
    print("'A RELIRE' = point interne ; l'offset ne vaut que si le corps n'a pas bouge.")
    if perdu or ambigu:
        print("")
        print("AU MOINS UNE CIBLE N'EST PAS TRANSCRIPTIBLE MECANIQUEMENT -- voir la fiche #257.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
