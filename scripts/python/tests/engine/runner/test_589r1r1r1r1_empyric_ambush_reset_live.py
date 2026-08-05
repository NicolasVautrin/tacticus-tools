"""CLIQUET #589-r1-r1-r1-r1 -- `EmpyricAmbush_Reset` (triggered **1555**), la triggered DERIVEE de
l'actif 1232 (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` : 0x4d0 -> [0x613]).

CRITERE : « quand `eldarLhykhis` ACHEVE un ennemi d'une attaque NORMALE au CONTACT, le natif re-arme
son actif 1232 -- et le PORT rend-il le MEME verdict, a partir du meme etat et du meme flux PRNG ? »

TROIS bras, et les deux derniers sont ce qui interdit l'accord DEGENERE :
  1. `MELEE`       -- le kill au CONTACT : le natif re-arme, le port aussi. La mutation `NOPORT`
     (l'entree `"EmpyricAmbush"` retiree d'`ACTIVE_ABILITY_TRIGGERS` = la vue d'AVANT ce port) doit
     CHANGER l'observable, sinon « ca concorde » ne prouverait rien.
  2. `RANGED`      -- le MEME kill a DISTANCE 2 : le noeud `IsMeleeAttack(<DSLSelectors+0x90>)` doit
     REFUSER le re-armement, des DEUX cotes. Seul bras qui exerce ce noeud.
  3. `PAR-ABILITY` -- la victime meurt du CAST de 1232 : le noeud `IsNormalAttack(<+0x90>)` doit
     refuser. Seul bras qui exerce CELUI-LA.

Le montage est IMPORTE de `probe_589r1r1r1r1_empyric_ambush_reset_live.py` au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

ASCII only.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_589r1r1r1r1_empyric_ambush_reset_live import (  # noqa: E402
    ABILITY_TYPE, CARRIER, cast_kill_live, kill_live, replay, replay_cast,
    seed_bc_avec_lhykhis, stage, stage_par_ability)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

_SEED_BC = seed_bc_avec_lhykhis()
_DMG = 400000        # `--unit-stat` : les 5 coups d'arme de Lhykhis doivent TUER un ennemi tanky


def _monte(charge_regime, board, seed, hp_target=900000, ranged=False):
    """UN runner par bras. Les ennemis sont TANKY pour que le cast de 1232 ne tue PERSONNE : la mort
    doit venir de l'attaque NORMALE (sinon `IsNormalAttack` serait faux et le bras positif ne dirait
    rien). `--crit 0,0` / `--block-target 0,0` : aucun canal aleatoire ne decide de la mort."""
    a = types.SimpleNamespace(ranged=ranged, verbose=False)
    h = charge_regime(p_units="%s,blackHaarken" % CARRIER,
                      a_units="necroWarden,necroOverlord", seed=seed, board=board,
                      extra=["--crit", "0,0", "--block-target", "0,0",
                             "--hp-target", str(hp_target), "--hp-player", "900000",
                             "--unit-stat", "%s:Damage=%d" % (CARRIER, _DMG),
                             "--seed-bc", _SEED_BC])
    return h, a


@pytest.mark.parametrize("board,seed", [("MC1_67", "777"), ("C1_74", "31337")])
def test_le_kill_au_contact_re_arme_l_actif(charge_regime, board, seed):
    """BRAS `MELEE`. `usable` de l'actif 1232 (`decisionView` natif / `ActiveAbilitiesComponent`
    port) -- les deux champs qu'ecrit `ResetActiveAbilityOperation$$Execute`."""
    h, a = _monte(charge_regime, board, seed)
    rec, why = stage(h, a)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = kill_live(h, rec)
    assert live is not None, "kill live NON JOUE (%s)" % why
    off = replay(h, rec)
    mut = replay(h, rec, mutate="NOPORT")

    assert live["mort"] and off["mort"], "la victime doit mourir des DEUX cotes"
    assert (live["apres"] or {}).get("usable") is True, (
        "le natif n'a PAS re-arme l'actif au contact (%s) -- regime non atteint" % (live["apres"],))
    assert (off["apres"] or {}).get("usable") is True, (
        "le port n'a pas re-arme (%s) alors que le natif l'a fait" % (off["apres"],))
    assert (mut["apres"] or {}).get("usable") is False, (
        "NOPORT n'a rien change -- l'accord ne prouve rien")


@pytest.mark.parametrize("board,seed", [("MC1_67", "777"), ("C1_74", "31337")])
def test_le_kill_a_distance_ne_re_arme_pas(charge_regime, board, seed):
    """BRAS `RANGED` -- le noeud `IsMeleeAttack`. MEME attaque normale, MEME victime, distance 2 :
    le natif ne re-arme PAS, et le port non plus. Sans ce bras, un port qui re-armerait sur TOUT
    kill concorderait quand meme sur le bras positif."""
    h, a = _monte(charge_regime, board, seed, ranged=True)
    rec, why = stage(h, a)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = kill_live(h, rec)
    assert live is not None, "kill live NON JOUE (%s)" % why
    off = replay(h, rec)

    assert live["mort"] and off["mort"], "la victime doit mourir des DEUX cotes"
    assert (live["apres"] or {}).get("usable") is False, (
        "le natif a re-arme sur un kill A DISTANCE (%s) -- la RE du noeud IsMeleeAttack est a "
        "reprendre" % (live["apres"],))
    assert (off["apres"] or {}).get("usable") is False, (
        "le port a re-arme a distance (%s) -- le gate IsMeleeAttack ne mord pas" % (off["apres"],))


def test_le_kill_par_l_ability_ne_re_arme_pas(charge_regime):
    """BRAS `PAR-ABILITY` -- le noeud `IsNormalAttack`. La victime (FRAGILE) meurt des 8 coups du
    CAST de 1232 : le `killTrigger` du vecteur mort vaut 1232, pas une attaque normale.

    ⚠ L'observable `usable` cote PORT est SATUREE ici (le port ne modelise pas la consommation de
    l'actif au cast offline -> `ActiveAbilitiesComponent` reste a `usable=True`, et le gate
    `EntityCanHaveActiveAbilityReset` rend alors le re-armement no-op quoi qu'il arrive). Le noeud
    est donc confronte au niveau du PREDICAT, sur le MEME etat post-cast -- c'est dit, pas maquille
    en accord."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.abilities.attack_type import is_normal_attack
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.empyric_ambush import (
        EmpyricAmbushResetAbility, _kill_trigger)

    h, a = _monte(charge_regime, "MC1_67", "777", hp_target=500)
    rec, why = stage_par_ability(h, a)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = cast_kill_live(h, rec)
    assert live is not None, "cast live NON JOUE (%s)" % why
    off = replay_cast(h, rec)

    assert live["mort"] and off["mort"], "la victime doit mourir du CAST des DEUX cotes"
    assert (live["apres"] or {}).get("usable") is False, (
        "le NATIF a re-arme sur un kill d'ABILITY (%s) -- la RE du noeud IsNormalAttack est a "
        "reprendre" % (live["apres"],))
    kt = _kill_trigger(off["state"], rec["target"])
    assert kt == ABILITY_TYPE, "killTrigger attendu %d, lu %s" % (ABILITY_TYPE, kt)
    assert not is_normal_attack(kt), "regime non atteint : %s vu comme attaque normale" % kt
    ev = TriggerEvent(int(EventTriggerType.UnitDefeated), rec["caster"], rec["target"],
                      ranged=False, profile=None,
                      killer_id=rec["caster"], dying_id=rec["target"])
    assert not EmpyricAmbushResetAbility(rec["caster"]).matches(off["state"], ev), (
        "le port declenche EmpyricAmbush_Reset sur un kill d'ABILITY -- IsNormalAttack ne mord pas")
