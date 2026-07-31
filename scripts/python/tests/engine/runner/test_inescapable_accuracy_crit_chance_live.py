"""CLIQUET #366-r1 -- `InescapableAccuracy_extraCritChance` (1115) sur `eldarMauganRa`.

L'effet est pose a l'INIT du passif `InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115) sur
son PORTEUR, avec ses deux jumeaux, par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` :
`AddEffect(0x45b) + AddEffect(0x45c) + AddEffect(0x45d)`, targets = Owner, `turns = NULL`
(PERMANENTS -- ce qui les eteint est la CONDITION, pas une duree).

DEUX ARTEFACTS GARDES, chacun avec sa vue ROUGE mesuree (fiche
`docs/rl/case-366-r1-inescapable-accuracy-crit-chance.md`) :

  * CANAL  -- `...InescapableAccuracy_ExtraCritChanceEffect$$CreateCritChanceBonus` =
              `ForAddition(get_OwnerIsCaster & IsRangedAttack, ConfigVar(0x41 = extraCritChance))`.
              DEUX noeuds seulement : PAS de `IsNormalAttack`, PAS d'`AmountIsGreaterThanZero` --
              contrairement au voisin `1222 WarHowl_ExtraDamage_Unstoppable`, dont ce port
              N'HERITE RIEN (le gate d'attaque y est meme l'INVERSE).
  * GATE   -- `CreateActiveCondition` (corps PARTAGE par les trois classes du passif) =
              `op_LogicalNot(HasFlag(Owner, 0 = UnitFlag.Moved))` : Maugan Ra qui a BOUGE ce tour
              ne beneficie plus du bonus. Meme predicat natif que
              `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` (#98).

Les deux bras sont des SALVES A DISTANCE (arme `weapons[1]`, `Range` 3) : une attaque au CONTACT
basculerait sur l'arme MELEE et fermerait `IsRangedAttack` -- la geometrie du montage impose donc
`2 <= d <= 3` AVANT et APRES le pas.

Probe de mesure : `probe_366_r1_inescapable_accuracy_crit_chance.py` (foyer unique du montage --
`stage`, `strike` et `replay` sont IMPORTES ici plutot que re-transcrits : deux transcriptions du
meme montage finissent par diverger).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import charge_regime                          # noqa: E402,F401  (fixture)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki import InescapableAccuracyExtraCritChanceEffect  # noqa: E402
from probe_366_r1_inescapable_accuracy_crit_chance import (       # noqa: E402
    EFFECT_NAME, EFFECT_TYPE, MAUGAN, replay, stage, strike)

_A_UNITS = "necroWarden,necroOverlord"       # aucun des deux ne porte `Overwatch` (cf. le probe)
#: `CritChance` de base du porteur. **> 0 OBLIGATOIRE** : `DamageCalculations$$CouldCrit` lit
#: `GetStat(9)` BRUTE (le bonus d'effet n'y entre pas), donc a 0 le natif ne tire aucun crit et le
#: bras ne prouverait rien (il mesurerait le residu `could_crit`, cf. la fiche).
_CRIT = "50,700"


def _extra(crit: str = _CRIT):
    """Options de build. `--block-target 0,0` neutralise le canal BLOCK de la cible, celui que porte
    le JUMEAU NON PORTE `1117 InescapableAccuracy_overrideHits`
    (`...InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger` ->
    `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`) : sans elle, un ecart de coups
    imputable a 1117 se lirait comme un ecart de 1115."""
    return ["--crit", crit, "--block-target", "0,0"]


def _measure(charge_regime, do_step, crit=_CRIT, seed="777", board="MC1_67"):
    """Monte, (option) fait UN pas, tire, rejoue offline. ECHEC FORT si le regime n'est pas atteint
    -- un `skip` VERT mentirait sur une garde qui n'a rien garde."""
    h = charge_regime(p_units=MAUGAN, a_units=_A_UNITS, seed=seed, board=board,
                      extra=_extra(crit))
    rec, why = stage(h, do_step)
    assert rec is not None, "regime NON ATTEINT (step=%s) : %s" % (do_step, why)
    live, why = strike(h, rec)
    assert live is not None, "salve non mesurable : %s" % why
    return h, rec, live


@pytest.fixture(scope="module")
def ia_nomove(charge_regime):
    """BRAS NOMOVE -- Maugan Ra n'a pas bouge : l'`ActiveCondition` est VRAIE, le natif roule a
    `GetStat(9) + extraCritChance[50]` = 50 + 15 = 65."""
    return _measure(charge_regime, False)


@pytest.fixture(scope="module")
def ia_moved(charge_regime):
    """BRAS MOVED -- Maugan Ra a fait UN pas (en restant a portee ET hors contact) : `UnitFlag.Moved`
    est pose, l'effet est INACTIF, le natif roule a `GetStat(9)` = 50."""
    return _measure(charge_regime, True)


@pytest.fixture(scope="module")
def ia_alt(charge_regime):
    """GENERALISATION -- meme invariant, AUTRE board (`C1_25`, a elevation), AUTRE seed (31337)."""
    return _measure(charge_regime, False, seed="31337", board="C1_25")


def _carried(rec, off_state):
    """1115 doit etre MATERIALISE offline sur l'attaquant -- sinon le test compare deux absences."""
    return [e for e in (off_state.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == EFFECT_TYPE or e.name == EFFECT_NAME]


def test_registry_binds_dedicated_class():
    """Garde STRUCTURELLE (offline, sans jeu) : 1115 a sa PROPRE classe.

    Les fabriques `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffects
    u003Eb__14_141/142/143` allouent depuis TROIS slots `Il2CppClass*` DIFFERENTS puis appellent le
    MEME corps de `$$.ctor` (dedup IL2CPP) : le ctor « fondu » ne fait PAS une classe commune, et le
    port ne doit lier que le chemin de 1115."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is InescapableAccuracyExtraCritChanceEffect
    # Les DEUX jumeaux restent NON portes -- les inscrire par analogie serait un port speculatif
    # (leurs canaux sont differents : `CreateCritDamageBonus` / `BlockHitsReduction`).
    assert "InescapableAccuracy_extraCritDmg" not in EFFECT_CLASSES
    assert "InescapableAccuracy_overrideHits" not in EFFECT_CLASSES


def test_gates_are_tristate_offline():
    """Les deux gates se taisent tant que leur contexte ne PROUVE pas le regime.

    Le natif ne se rabat jamais sur `IsRangedAttack` quand `GetAbilityAttackRangeType` ne tranche
    pas (#106) ; et l'`ActiveCondition` FERME des que `HasFlag(Owner, Moved)`. Verrouille aussi
    l'ABSENCE des deux noeuds de `1222` (`IsNormalAttack`, `AmountIsGreaterThanZero`) : les ajouter
    « par analogie avec le voisin » rendrait le port FAUX sur les attaques d'ability et sur un
    porteur a crit-chance nulle."""
    e = InescapableAccuracyExtraCritChanceEffect(
        name=EFFECT_NAME, effect_type=EFFECT_TYPE, level=1, ability_level=50,
        ability_variables_multiplier=180)
    assert e.create_effect_crit_chance_bonus_for_attack(None) is None            # ctx absent
    assert e.create_effect_crit_chance_bonus_for_attack({"is_ranged": None}) is None
    assert e.create_effect_crit_chance_bonus_for_attack({"is_ranged": False}) is None  # melee
    ok = {"is_ranged": True, "has_moved": False}
    assert (e.create_effect_crit_chance_bonus_for_attack(ok) or 0) == 15, \
        "extraCritChance[50] = 15 (gameconfig `InescapableAccuracy`), hors rarity-bonus"
    assert e.create_effect_crit_chance_bonus_for_attack({**ok, "has_moved": True}) is None, \
        "ActiveCondition NOT HasFlag(Owner, Moved) : une unite qui a bouge ne recoit RIEN"
    # AUCUN des deux noeuds de 1222 n'existe ici : ni `IsNormalAttack`, ni le gate sur GetStat(9).
    assert (e.create_effect_crit_chance_bonus_for_attack({**ok, "is_normal_attack": False})
            or 0) == 15, "pas de noeud IsNormalAttack -> le bonus vaut aussi pour une ABILITY"
    assert (e.create_effect_crit_chance_bonus_for_attack({**ok, "caster_crit_chance": 0})
            or 0) == 15, "pas de noeud AmountIsGreaterThanZero -> aucun gate sur GetStat(9)"
    # `is_active` = le MEME predicat, sur l'autre voie (tout consommateur d'`active_effects`).
    assert e.is_active({"has_moved": False}) is True
    assert e.is_active({"has_moved": True}) is False
    assert e.is_active({}) is True, "cle absente = non mesuree -> on ne ferme pas"


def test_crit_chance_matches_native(ia_nomove):
    """CAS ROUGE AVANT LE FIX -- la salve a distance d'un Maugan Ra IMMOBILE roule a `GetStat(9)+15`
    cote natif ; un port sans le canal roulerait a `GetStat(9)`, memes tirages, crits DIFFERENTS."""
    h, rec, live = ia_nomove
    off = h.replay_offline(rec)
    assert _carried(rec, off["state"]), \
        "1115 n'est pas materialise offline sur l'attaquant -- le test comparerait deux absences"
    assert off["per_hit"] == live, (
        "CANAL : le port ne compte pas la contribution de 1115 -- live=%s offline=%s (delta=%s)"
        % (live, off["per_hit"],
           [l - o for l, o in zip(live, off["per_hit"])] if len(live) == len(off["per_hit"])
           else "n different"))


def test_channel_actually_bites(ia_nomove):
    """Le bras NOMOVE EXERCE bien le canal -- sinon `test_crit_chance_matches_native` passerait pour
    une raison TRIVIALE (aucun bonus nulle part, deux zeros qui s'accordent).

    Mutation ADVERSARIALE : l'inscription est retiree d'`EFFECT_CLASSES`, l'effet capte retombe sur
    `BaseEffect` (qui rend None). Le rejeu DOIT diverger du live."""
    h, rec, live = ia_nomove
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert mut != live, (
        "l'inscription retiree ne change RIEN (live=%s) -- le regime de crit n'est pas "
        "discriminant sur cette salve ; varier --crit / --seed / --board" % (live,))


def test_move_closes_the_gate(ia_moved):
    """BRAS MOVED -- apres UN pas, le natif N'AJOUTE PLUS le bonus (`HasFlag(Owner, Moved)`), et le
    port non plus. La salve reste une salve A DISTANCE (2 <= d <= 3 impose par le montage)."""
    h, rec, live = ia_moved
    off = h.replay_offline(rec)
    assert _carried(rec, off["state"]), \
        "1115 doit rester MATERIALISE (il est PERMANENT) -- c'est la CONDITION qui l'eteint"
    assert off["per_hit"] == live, (
        "GATE : live=%s offline=%s" % (live, off["per_hit"]))


def test_move_gate_is_load_bearing(ia_moved):
    """Le gate est CHARGE UTILE, pas decoratif -- sinon `test_move_closes_the_gate` serait vrai d'un
    port qui n'applique jamais rien.

    Mutation ADVERSARIALE : les DEUX mirrors de l'`ActiveCondition` sont desarmes (`is_active` force
    a True, cle `has_moved` retiree de l'`att_ctx`). Le port se remet alors a rouler a
    `GetStat(9)+15` la ou le natif roule a `GetStat(9)` -> le rejeu DOIT diverger du live."""
    h, rec, live = ia_moved
    mut = replay(h, rec, mutate="NOGATE")
    assert mut != live, (
        "gate desarme : le rejeu coincide encore avec le live (live=%s) -- ce bras ne prouve pas "
        "que la condition mord ; varier --crit / --seed / --board" % (live,))


def test_other_board(ia_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`, a ELEVATION -- le crit traverse donc
    aussi l'etage %-list), autre seed (31337)."""
    h, rec, live = ia_alt
    off = h.replay_offline(rec)
    assert _carried(rec, off["state"])
    assert off["per_hit"] == live, (
        "C1_25/31337 : live=%s offline=%s" % (live, off["per_hit"]))
