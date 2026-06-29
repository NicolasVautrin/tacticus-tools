"""COUVERTURE CATALOGUE — axe DÉGÂT : valide l'attaque normale de CHAQUE unité (data-driven
`unit_map`) par replay-diff bit-exact vs live. 1ʳᵉ brique du programme « valider chaque
playbook/ability/effet/trait via test ».

Périmètre v1 = unités **vanilla melee-multihit** (arme mêlée ≥2 coups, AUCUN modificateur de
dégât d'ability/trait : `unit_map._has_dmg_mod` faux) → l'attaque normale doit être reproduite
À L'UNITÉ par le moteur de dégât porté (spread→perçage/armure→multi-coups). Un MISMATCH ici =
vrai trou du moteur sur ce profil d'arme/trait (le but : le SURFACER).

Échelle : le catalogue entier = des centaines de batailles live (lent). Par défaut on teste un
ÉCHANTILLON (cap `DAMAGE_CATALOG_N`, défaut 4) ; `DAMAGE_CATALOG_UNITS="a,b,c"` force une liste ;
`DAMAGE_CATALOG_N=0` = tout (run à la demande / workflow). Cible vanille = eldarFarseer.

Les axes crit/block/effet-crit ont leurs tests dédiés (test_damage_{crit,block}_live) ; les unités
NON-vanilla (ability/effet/trait sur l'attaque) = modes de couverture séparés à venir (résolution
d'ability, mécaniques effet/trait), souvent xfail tant que non portés.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner → import du helper sibling

from _combat_replay import replay_normal_attack  # noqa: E402

TARGET = "eldarFarseer"          # cible vanille (aucune reduction de degat)


def _catalog_units():
    """Unités vanilla melee-multihit (data-driven), échantillonnées. Liste calculée à la collecte."""
    env = os.environ.get("DAMAGE_CATALOG_UNITS")
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    try:
        import unit_map as UM
    except Exception:
        return []
    cands = []
    for k in UM.all_kits():
        if k["id"] == TARGET:
            continue
        if any(w["melee"] and w["hits"] >= 2 for w in k["weapons"]) and not UM._has_dmg_mod(k):
            cands.append(k["id"])
    cands.sort()
    n = int(os.environ.get("DAMAGE_CATALOG_N", "4"))
    return cands if n <= 0 else cands[:n]


_UNITS = _catalog_units()


@pytest.mark.skipif(not _UNITS, reason="unit_map indisponible / aucune unite vanilla melee-multihit")
@pytest.mark.parametrize("attacker", _UNITS)
def test_normal_attack_bit_exact(attacker, live_session, rpc, build_runner):
    """L'attaque normale de `attacker` (vanilla melee-multihit) est reproduite bit-exact offline."""
    r = replay_normal_attack(rpc, build_runner, attacker, target=TARGET)
    if not r["ok"]:
        pytest.skip(f"{attacker}: {r['reason']}")
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip(f"{attacker}: coup non propre (crit/block/evade live) — hors axe vanilla")
    print(f"\n[CATALOG dmg] {attacker}: hits={r['hits']} live={r['live_ph']} off={r['off_ph']} "
          f"live_after={r['live_after']} off_after={r['off_after']} eff={r['effects']}")
    assert r["exact"], (f"{attacker}: dégât offline != live — per-hit off={r['off_ph']} "
                        f"live={r['live_ph']} (off_after={r['off_after']} live_after={r['live_after']})")
