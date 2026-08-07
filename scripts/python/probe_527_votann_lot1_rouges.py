"""#527 -- MESURE des six rouges de `test_votann_lot1_live.py` sur `master`.

Ce probe ne teste rien : il MESURE, etage par etage, ce que le montage du fichier de test
produit reellement, pour ATTRIBUER chaque rouge a sa cause (montage perime / port faux /
attente perimee) au lieu de le deviner.

Etages mesures, dans l'ordre ou ils se conditionnent :

  1. `stats`   -- les stats de BASE du caster (`combatSnapshot`), en particulier
                  `critChance` / `blockChance` d'un `votanUthar` FRAIS. Le regime
                  `fortune_gated` du test suppose ZERO ; si la base est > 0, le regime
                  qu'il croit exercer n'existe plus et ses trois assertions accusent le
                  MONTAGE, pas le port.
  2. `geom`    -- positions des deux camps apres pilotage, et distance caster<->cible :
                  `AncestralFortuneAbility$$GetAttackTarget` ne frappe QUE des ennemis
                  ADJACENTS (`AdjacentEnemies(caster, 1)`).
  3. `cast`    -- les events NATIFS du cast, non filtres. C'est la seule facon de dire si
                  le natif a ATTAQUE (et qui), pose quels effets, et pourquoi un
                  `_live_total` peut valoir 0 alors que le port rend un total non nul.
  4. `effects` -- les effets portes par la cible AVANT et APRES le cast (`decisionView`),
                  pour le rouge `graviton : cible non Stun ([])`.

ASCII only (cp1252). Aucun `data/` en ecriture : les sorties vont sous `logs/`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

BESERK, IRONMASTER, UTHAR = "votanBeserk", "votanIronmaster", "votanUthar"
SPARE = "spaceHound"
FOE_MECH = "necroWarden"
FOE_PLAIN = "bloodMephiston"

AUGMENTED_ASSAULT, GRAVITON_RIFLE, ANCESTRAL_FORTUNE = 1221, 1206, 1207


def main() -> int:
    print("[527] squelette -- les etages de mesure arrivent dans le meme commit que le fix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
