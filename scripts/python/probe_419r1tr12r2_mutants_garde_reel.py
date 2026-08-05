"""#419-r1-tr12-r2 -- CONTRE-EPREUVE DE LA GARDE du porteur reel : elle rougit-elle vraiment ?

`tests/engine/test_419r1tr12r2_electro_shock_reel_live.py` est VERTE. Un vert ne prouve rien tant
qu'on n'a pas montre que le rouge est ATTEIGNABLE : une garde qui passerait aussi sur un port faux
est un inventaire deguise en garde-fou.

Ce probe MUTE le fichier LIVRE (`engine/playbook/electro_shock.py`) sur disque, rejoue la garde,
puis RESTAURE -- toujours, meme sur exception.

⚠ IL LEVE SI UN MOTIF EST INTROUVABLE OU AMBIGU. C'est le piege exact mesure par la tranche 12 : un
premier essai de contre-epreuve avait rendu « 7 passed » sur du code NON MUTE (le motif n'avait pas
matche), et ce vert-la se serait lu comme « la garde ne detecte pas ». Un remplacement qui ne mord
pas doit ARRETER le probe, jamais produire un resultat.

LES TROIS MUTANTS, et l'axe que chacun coupe :

  `product`  -- `poids x cardinal` au lieu du poids plat. C'est LE modele concurrent : `Boltstorm`
                (1090), `FireOfAbsolution` (1017) et `RighteousRepugnance` (1107) comptent tous des
                voisins de la cible avec le MEME helper `get_Count` et MULTIPLIENT.
  `no_gate`  -- le terme devient inconditionnel (`if (enemies.Count == 0) yield break` supprime).
  `friends`  -- le port lit le volet AMIS de `count_adjacent_by_camp` au lieu du volet ENNEMIS,
                c.-a-d. `GetAdjacentFriends` la ou le natif appelle `GetAdjacentEnemies`.

Usage :
    python scripts/python/probe_419r1tr12r2_mutants_garde_reel.py [--mutant product] [-k <expr>]

ASCII only. Il monte DEUX runners par mutant (la garde est un montage a bras apparie) : le compter
dans le budget partage.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.join(_HERE, "engine", "playbook", "electro_shock.py")
GARDE = os.path.join("tests", "engine", "test_419r1tr12r2_electro_shock_reel_live.py")

#: `{nom: (motif, remplacement)}`. Les motifs sont VERBATIM du fichier livre ; s'ils cessent de
#: matcher, c'est que le port a bouge et que cette contre-epreuve doit etre relue, pas contournee.
MUTANTS: dict[str, tuple] = {
    "product": (
        "        return float(ctx.wt.triggered(_WEIGHT_KEY))",
        "        return float(ctx.wt.triggered(_WEIGHT_KEY)) * n_enemy",
    ),
    "no_gate": (
        "        if n_enemy == 0:\n            return 0.0",
        "        if False and n_enemy == 0:\n            return 0.0",
    ),
    "friends": (
        "        _n_friend, n_enemy = count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)",
        "        n_enemy, _n_friend = count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)",
    ),
}


class MutationInerte(RuntimeError):
    """Le motif n'a pas matche exactement une fois -- la mutation n'a PAS eu lieu."""


def _mute(src: str, motif: str, repl: str) -> str:
    n = src.count(motif)
    if n != 1:
        raise MutationInerte(
            f"motif trouve {n} fois (attendu 1) dans {os.path.basename(PORT)} -- un remplacement "
            f"qui ne mord pas produirait un VERT trompeur. Motif :\n{motif}")
    return src.replace(motif, repl)


def _run_garde(extra: list) -> tuple:
    p = subprocess.run([sys.executable, "-m", "pytest", GARDE, "-q", *extra],
                       cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    tail = [l for l in out.splitlines() if l.strip()][-1:] or [""]
    return p.returncode, tail[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutant", action="append", choices=sorted(MUTANTS), default=None,
                    help="ne jouer que ce(s) mutant(s) (defaut : tous)")
    ap.add_argument("-k", dest="kexpr", default=None,
                    help="restreindre la garde (passe tel quel a pytest)")
    args = ap.parse_args()
    extra = ["-k", args.kexpr] if args.kexpr else []

    original = open(PORT, encoding="utf-8").read()
    verdicts = []
    try:
        for name in (args.mutant or sorted(MUTANTS)):
            motif, repl = MUTANTS[name]
            open(PORT, "w", encoding="utf-8").write(_mute(original, motif, repl))
            rc, tail = _run_garde(extra)
            verdicts.append((name, rc, tail))
            print(f"[mutant {name:<9}] rc={rc} ({'GARDE ROUGE' if rc else 'GARDE VERTE -- TROU'})"
                  f" : {tail}")
    finally:
        open(PORT, "w", encoding="utf-8").write(original)
    # Re-jeu du code RESTAURE : sans lui, on ne sait pas si la restauration a bien eu lieu.
    rc, tail = _run_garde(extra)
    print(f"[restaure ] rc={rc} ({'VERTE' if rc == 0 else 'ROUGE -- restauration SUSPECTE'})"
          f" : {tail}")
    trous = [n for n, r, _t in verdicts if r == 0]
    if trous:
        print(f"TROU DE GARDE : {trous} ne font PAS rougir la garde")
    return 1 if (trous or rc != 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
