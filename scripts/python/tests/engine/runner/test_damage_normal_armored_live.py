"""ATTAQUE NORMALE sur cible ARMURÉE — verrou de l'ORDRE reduce-then-roll (replay-diff LIVE).

Re-vérifie (demande user) que l'attaque NORMALE du runner (`AttackDamageOperation.execute`) est
bit-exact sur une cible à FORTE armure, où l'ordre réduction↔tirage est DISCRIMINANT (≠ cible armure 0).

Confirmé live (necroDestroyer 6 coups mêlée → necroOverlord, armure 1909 pierce 60) :
  • reduce-then-roll (runner) = live À L'UNITÉ : [514,582,514,578,642,603].
  • roll-then-reduce (ordre des ABILITIES) = FAUX ici : [520,519,532,441,493,589].
=> attaque normale = **reduce-then-roll** (bornes pré-réduites puis tirage), GENUINELY DIFFÉRENT du
dégât d'ABILITY = **roll-then-reduce** (`RandomAmount` brut puis réduction ; cf. test_damage_ability_live).
Ce test verrouille la distinction : un futur « unifie les deux ordres » casserait ICI (sur l'armure).

Cible VANILLE tanky `necroOverlord` (hp~8536, armure~1909, effects=[] : survit, 0 reduction/block).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _combat_replay import replay_normal_attack, replay_attack_driven   # noqa: E402

ATTACKER = "necroDestroyer"
TARGET = "necroOverlord"

# Confonds NEUTRALISES AU BUILD (#419-r6). ARBITRAGE : ce fichier mesure l'ORDRE
# reduce-then-roll, et c'est le PER-COUP qui le discrimine (`[514,582,514,578,642,603]` contre
# `[520,519,532,441,493,589]`). Un crit multiplie le coup APRES ce point : il ne testerait pas
# l'ordre, il masquerait le discriminant -- et le fichier ne sait rien en faire, il SKIPPE
# (`did_crit` -> skip). Sur une salve de 6 coups avec `CritChance = 41` cote cible et un
# attaquant equipe, un coup propre devenait improbable : 3 passed -> 3 skipped, soit le fichier
# INERTE que le garde #455 refuse. On neutralise donc sur les QUATRE faces plutot que de viser le
# regime crit, qui a son fichier dedie (`test_damage_crit_live.py`).
_NO_NOISE = ["--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]


def test_normal_attack_armored_reduce_then_roll(live_session, rpc, build_runner):
    """Attaque normale multi-coups sur cible armurée → per-coup bit-exact (reduce-then-roll)."""
    r = replay_normal_attack(rpc, build_runner, ATTACKER, target=TARGET, extra=_NO_NOISE)
    if not r["ok"]:
        pytest.skip(f"{ATTACKER}->{TARGET}: {r['reason']}")
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip(f"coup non propre (crit/block/evade live): {r}")
    # l'armure DOIT être > 0 pour que l'ordre soit discriminant (sinon test non concluant).
    assert r["armor"] and r["armor"] > 0, (
        f"cible non armurée (armor={r['armor']}) — test non discriminant ; choisir une cible armurée")
    print(f"\n[NORMAL armored] {ATTACKER}->{TARGET} hits={r['hits']} armor={r['armor']} pierce={r['pierce']} "
          f"live={r['live_ph']} off={r['off_ph']} (reduce-then-roll)")
    # VERROU : le PER-COUP (= l'ordre réduction↔tirage) doit être bit-exact. On asserte le per-coup
    # directement (PAS `exact` qui inclut aussi les PV-après — désalignables par overwatch/dérive ;
    # necroDestroyer porte Overwatch_AutoAttack). Le per-coup identique prouve reduce-then-roll.
    assert r["off_ph"] == r["live_ph"], (
        f"attaque normale NON bit-exact sur cible armurée : off={r['off_ph']} live={r['live_ph']} "
        f"(armor={r['armor']} pierce={r['pierce']}) — l'ordre reduce-then-roll est-il toujours correct ?")


# #63 : cible armuree SPAWNABLE, sans effet (l'Apothecary survit, 0 reduction/block cote defenseur).
_RANGED_CARRIERS = [
    ("necroDestroyer", "ultraApothecary"),   # Gauss ranged pierce 60
    ("templHelbrecht", "ultraApothecary"),   # Bolter ranged pierce 20
]


@pytest.mark.parametrize("attacker,target", _RANGED_CARRIERS)
def test_normal_attack_ranged_from_elevation_bitexact(live_session, rpc, build_runner, attacker, target):
    """#63 VERROU ELEVATION : attaque normale RANGED armor-sensitive depuis une tuile EN SURPLOMB.

    Le combat natif applique le bonus d'ELEVATION (+ELEVATION_BONUS_PCT=50% quand l'attaquant surplombe
    la cible) AVANT percage/armure. L'ancien replay-diff omettait `state.board` -> `apply_elevation_bonus`
    no-op -> degat OFFLINE TROP BAS (ratio ~0.58-0.67 mesure ; la 'divergence armure' du prompt #63 etait
    en fait l'elevation manquee, le percage/armure etant deja fidele : Psychic pierce-100 masquait l'armure
    ET les positions Psychic etaient plates -> faux discriminant). Avec le board charge (_do_replay #63),
    on exige off_ph == live_ph sur un tir armor-sensitive depuis un surplomb (discriminant : armor>0 ET
    a_elev>t_elev)."""
    r = replay_attack_driven(rpc, build_runner, attacker, target, want_dist=2,
                             require_higher_elev=True, extra=_NO_NOISE)
    if not r["ok"]:
        pytest.skip(f"{attacker}->{target}: {r['reason']}")
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip(f"coup non propre (crit/block/evade live): {r}")
    assert r["armor"] and r["armor"] > 0, f"cible non armuree (armor={r['armor']}) — test non discriminant"
    assert r["a_elev"] > r["t_elev"], (
        f"attaquant PAS en surplomb (a_elev={r['a_elev']} t_elev={r['t_elev']}) — elevation non exercee")
    print(f"\n[RANGED elev] {attacker}->{target} dist={r['dist']} armor={r['armor']} pierce={r['pierce']} "
          f"a_elev={r['a_elev']} t_elev={r['t_elev']} live={r['live_ph']} off={r['off_ph']}")
    assert r["off_ph"] == r["live_ph"], (
        f"attaque RANGED depuis surplomb NON bit-exact : off={r['off_ph']} live={r['live_ph']} "
        f"(armor={r['armor']} pierce={r['pierce']} a_elev={r['a_elev']} t_elev={r['t_elev']}) — "
        "bonus d'ELEVATION manque (state.board non charge dans le replay ?)")
