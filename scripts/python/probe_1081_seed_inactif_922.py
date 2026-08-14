#!/usr/bin/env python
"""#1081 (pour `#922-r1`) -- CONTRE-EPREUVE : l'ecart mesure vient du CANAL DE CAPTURE du harnais,
pas d'un trou de `_seed_ability_owner_effects`.

CE QUE LA FICHE CHERCHAIT, ET OU EST REELLEMENT LA CAUSE
========================================================

`#922-r1` attribue l'ecart `[462, 1600, 988]` a DEUX causes conjointes :
  (1) « `decisionView.effects` est ACTIF-ONLY (GROUND TRUTH #100) » ;
  (2) « `spawn.py::_seed_ability_owner_effects` ne materialise que les abilities du KIT, et une
      relique arrive par `BC.Units[].TertiaryAbility`, donc n'y figure JAMAIS ».

Les DEUX sont perimees, et la seconde l'est depuis #1005 (le seed LIT `ctx.tertiary_ability`).
La premiere l'est depuis #219/#443-r2-b1 : `snapshot.decision_view_seed_body` est la porte NOMMEE
qui passe `includeInactive: true`, et sa docstring dit « LES DEUX FACES PASSENT PAR ICI ».

CE QUI RESTE VRAI -- et c'est ailleurs : le harnais qui produit la capture du probe #922,
`tests/engine/runner/_charge_regime.py::ChargeRegimeHarness`, ne passe PAS par cette porte. Son
`snapshot()` appelle `dview()`, qui envoie `{runnerId, maxRank, allAbilities}` -- le canal
ACTIF-ONLY. L'effet, POSE mais INACTIF a l'instant de la capture, est donc droppe AVANT
`load_state`, et l'etat offline n'a aucune instance a reactiver. Mesure a l'appui : le diagnostic
`instance_dans_by_unit` ajoute au probe #922 rend **0**.

CE QUE CE PROBE FAIT
====================

Il rejoue le MEME montage avec le MEME code moteur, en substituant la SEULE chose en cause : le
corps du RPC de capture, remplace par `decision_view_seed_body`. Rien d'autre ne bouge -- ni le
moteur, ni le harnais sur disque, ni les registres.

  * si l'instance apparait dans `EffectsState.by_unit` -> la cause est ETABLIE, et le correctif de
    `#922-r1` est UNE ligne dans le harnais (pas une extension du seed d'owner-effects) ;
  * si elle n'apparait pas -> la cause est ailleurs, et ce probe le dit.

⚠ POURQUOI LA SUBSTITUTION PLUTOT QUE L'EDITION : `ChargeRegimeHarness` est partage par **53**
fichiers, dont ~25 tests LIVE. Editer son canal de capture change ce que TOUS voient (mesure #219 :
+6 entites-effet au deploiement) -- c'est une tranche a soi seule, avec balayage. Ce probe etablit
la cause SANS payer ce rayon, ce qui est exactement ce qui permet de decider s'il faut le payer.

Usage (depuis scripts/python) :
    python probe_1081_seed_inactif_922.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent

EX_OK = 0
EX_ROUGE = 1
EX_NON_MESURE = 99

#: Le montage est celui du probe #922, joue TEL QUEL dans un sous-processus : on ne re-ecrit pas
#: son protocole (positions drivees, salve, rejeu), on ne substitue que le corps du RPC.
CODE = r"""
import sys
sys.path.insert(0, {pydir!r})
sys.path.insert(0, {tests!r})

import _charge_regime as CR
from engine.runner.snapshot import decision_view_seed_body

# LA SEULE substitution : le canal de capture passe par la porte NOMMEE du seed.
_dview_origine = CR.ChargeRegimeHarness.dview


def _dview_seed(self):
    return self.rpc("decisionView",
                    decision_view_seed_body(self.rid, maxRank=1, allAbilities=True), 90)


CR.ChargeRegimeHarness.dview = _dview_seed

# `probe_922.main()` lit `sys.argv` (aucun parametre) -- on lui pose donc sa ligne de commande.
sys.argv = ["probe_922_intoxicating_elixir_live.py", "--n", "0", "--thrilled"]
import probe_922_intoxicating_elixir_live as P
sys.exit(P.main())
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)

    tests = PYDIR / "tests" / "engine" / "runner"
    code = CODE.format(pydir=str(PYDIR), tests=str(tests))
    print("[1081] BRAS SUBSTITUE -- capture via `decision_view_seed_body` (includeInactive: true)")
    print("       (le harnais sur disque n'est PAS modifie)")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(PYDIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    sortie = (r.stdout or "") + (r.stderr or "")
    print(sortie[-2600:])

    if "instance_dans_by_unit" in sortie or "EffectsState.by_unit" in sortie:
        pass
    if "PRESENTE, le residu porte sur la REACTIVATION" in sortie:
        print("[1081] VERDICT -- CAUSE ETABLIE : avec `includeInactive`, l'instance EST seedee.")
        print("        Le correctif de #922-r1 est le CANAL DE CAPTURE du harnais, pas une")
        print("        extension de `_seed_ability_owner_effects`.")
        return EX_OK
    if "AUCUNE, le residu porte sur le SEED" in sortie:
        print("[1081] VERDICT -- la substitution NE SUFFIT PAS : meme avec `includeInactive`,")
        print("        l'instance n'est pas seedee. La cause est en amont (le capteur ne publie")
        print("        pas cet effet-la) ou en aval (`load_state` le filtre).")
        return EX_OK
    print("[1081] NON MESURE -- le bras n'a pas atteint le diagnostic (rc=%s)." % r.returncode)
    return EX_NON_MESURE


if __name__ == "__main__":
    raise SystemExit(main())
