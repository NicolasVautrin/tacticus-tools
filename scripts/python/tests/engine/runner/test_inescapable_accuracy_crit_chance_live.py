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
    EFFECT_NAME, EFFECT_TYPE, MAUGAN, neutralized_seed_bc, replay, stage, strike)

_A_UNITS = "necroWarden,necroOverlord"       # aucun des deux ne porte `Overwatch` (cf. le probe)
#: `CritChance` de BASE du porteur = **0**. Ce n'est pas un confort, c'est le regime le plus
#: DISCRIMINANT : a `GetStat(9) = 0`, le port SANS le canal calcule `could_crit(0, 700)` = faux et
#: ne tire AUCUN crit, tandis que le natif roule a `clamp(0 + extraCritChance[50]) = 15` et tire.
#: Le crit du coup mesure n'existe donc QUE par la contribution de 1115.
_CRIT = "0,700"
#: Le seed BC du module : arme RANGED a UN coup (sort du regime ou mord le residu CRIT
#: pre-existant, cf. la fiche). `extraCritDmg` N'EST PLUS neutralise depuis que `1116` est PORTE
#: (#366-r1/1116) : le patch vivait dans le BC -- donc cote NATIF -- alors que le port lit le
#: gameconfig, si bien qu'il ferait desormais DIVERGER tout coup critique. Ce montage confronte
#: donc les DEUX volets du passif a la fois ; chacun garde son propre cliquet.
_SEED_BC, _SEED_BC_REPORT = neutralized_seed_bc()


def _extra(crit: str = _CRIT):
    """Options de build. `--block-target 0,0` neutralise le canal BLOCK de la cible, celui que porte
    le JUMEAU NON PORTE `1117 InescapableAccuracy_overrideHits`
    (`...InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger` ->
    `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`) : sans elle, un ecart de coups
    imputable a 1117 se lirait comme un ecart de 1115."""
    return ["--crit", crit, "--block-target", "0,0", "--seed-bc", _SEED_BC]


def _measure(charge_regime, do_step, crit=_CRIT, seed="777", board="MC1_67"):
    """Monte, (option) fait UN pas, tire, rejoue offline. ECHEC FORT si le regime n'est pas atteint
    -- un `skip` VERT mentirait sur une garde qui n'a rien garde.

    Rend `(h, rec, live)`. Le natif joue UN coup (seed BC) ; le port en produit six (il derive le
    nombre de coups du GAMECONFIG par visualId, pas du BC -- residu de SOURCE nomme dans la fiche),
    d'ou la confrontation sur le PREFIXE de longueur `len(live)` : les seules cellules ou les deux
    modeles sont sur la MEME case du flux PRNG."""
    h = charge_regime(p_units=MAUGAN, a_units=_A_UNITS, seed=seed, board=board,
                      extra=_extra(crit))
    rec, why = stage(h, do_step)
    assert rec is not None, "regime NON ATTEINT (step=%s) : %s" % (do_step, why)
    live, why = strike(h, rec)
    assert live is not None, "salve non mesurable : %s" % why
    assert len(live) == 1, (
        "le natif a joue %d coups, 1 attendu -- le seed BC 1-coup n'a pas pris, la mesure "
        "retomberait dans le regime du residu CRIT pre-existant" % len(live))
    return h, rec, live


@pytest.fixture(scope="module")
def ia_nomove(charge_regime):
    """BRAS NOMOVE -- Maugan Ra n'a pas bouge : l'`ActiveCondition` est VRAIE, le natif roule a
    `clamp(GetStat(9) + extraCritChance[50]) = 0 + 15 = 15` et TIRE."""
    return _measure(charge_regime, False)


@pytest.fixture(scope="module")
def ia_moved(charge_regime):
    """BRAS MOVED -- Maugan Ra a fait UN pas (en restant a portee ET hors contact) : `UnitFlag.Moved`
    est pose, l'effet est INACTIF, le natif roule a `GetStat(9)` = 0 et ne tire PAS."""
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
    """Garde STRUCTURELLE (offline, sans jeu) : 1115 a sa PROPRE classe, DISTINCTE de celle de 1116.

    Les fabriques `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffects
    u003Eb__14_141/142/143` allouent depuis TROIS slots `Il2CppClass*` DIFFERENTS puis appellent le
    MEME corps de `$$.ctor` (dedup IL2CPP) : le ctor « fondu » ne fait PAS une classe commune. Les
    volets 1115 et 1116 sont desormais TOUS DEUX portes, mais chacun par SA classe -- les fondre en
    une seule referait l'erreur que le slot refute."""
    from engine.entities.effects.loki import InescapableAccuracyExtraCritDamageEffect
    assert EFFECT_CLASSES.get(EFFECT_NAME) is InescapableAccuracyExtraCritChanceEffect
    assert (EFFECT_CLASSES.get("InescapableAccuracy_extraCritDmg")
            is InescapableAccuracyExtraCritDamageEffect)
    assert InescapableAccuracyExtraCritChanceEffect is not InescapableAccuracyExtraCritDamageEffect
    # `1117` reste NON porte : son canal est un TROISIEME (`BlockHitsReduction`), l'inscrire par
    # analogie serait un port speculatif.
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
    """CAS ROUGE AVANT LE FIX -- le tir d'un Maugan Ra IMMOBILE roule a
    `clamp(GetStat(9) + 15) = 15` cote natif ; un port sans le canal roule a `GetStat(9) = 0`,
    ne tire RIEN, et ne peut donc pas rendre ce coup."""
    h, rec, live = ia_nomove
    off = h.replay_offline(rec)["per_hit"]
    assert _carried(rec, h.replay_offline(rec)["state"]), \
        "1115 n'est pas materialise offline sur l'attaquant -- le test comparerait deux absences"
    assert off[:len(live)] == live, (
        "CANAL : le port ne compte pas la contribution de 1115 -- live=%s offline=%s"
        % (live, off[:len(live)]))


def test_channel_actually_bites(ia_nomove):
    """Le bras NOMOVE EXERCE bien le canal -- sinon `test_crit_chance_matches_native` passerait pour
    une raison TRIVIALE (aucun bonus nulle part, deux zeros qui s'accordent).

    Mutation ADVERSARIALE : l'inscription est retiree d'`EFFECT_CLASSES`, l'effet capte retombe sur
    `BaseEffect` (qui rend None). Le rejeu DOIT alors differer du rejeu de REFERENCE (et pas du
    live : comparer au live serait vide de sens si les deux divergeaient deja)."""
    h, rec, live = ia_nomove
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert mut[:n] != ref[:n], (
        "l'inscription retiree ne change RIEN au rejeu (ref=%s) -- ce tir n'exerce pas le canal ; "
        "varier --crit / --seed / --board" % (ref[:n],))


def test_move_closes_the_gate(ia_moved):
    """BRAS MOVED -- apres UN pas, le natif N'AJOUTE PLUS le bonus (`HasFlag(Owner, Moved)`), et le
    port non plus. Le tir reste un tir A DISTANCE (2 <= d <= 3 impose par le montage)."""
    h, rec, live = ia_moved
    res = h.replay_offline(rec)
    assert _carried(rec, res["state"]), \
        "1115 doit rester MATERIALISE (il est PERMANENT) -- c'est la CONDITION qui l'eteint"
    assert res["per_hit"][:len(live)] == live, (
        "GATE : live=%s offline=%s" % (live, res["per_hit"][:len(live)]))


def test_move_gate_is_load_bearing(ia_moved):
    """Le gate est CHARGE UTILE, pas decoratif -- sinon `test_move_closes_the_gate` serait vrai d'un
    port qui n'applique jamais rien.

    Mutation ADVERSARIALE : les DEUX mirrors de l'`ActiveCondition` sont desarmes (`is_active` force
    a True, cle `has_moved` retiree de l'`att_ctx`). Le port se remet alors a rouler a 15 la ou le
    natif roule a 0 -> il CRITE, et le rejeu DOIT differer de la reference."""
    h, rec, live = ia_moved
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOGATE")
    assert mut[:n] != ref[:n], (
        "gate desarme : le rejeu ne bouge pas (ref=%s) -- ce bras ne prouve pas que la condition "
        "mord ; varier --crit / --seed / --board" % (ref[:n],))


def test_other_board(ia_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`, a ELEVATION -- le crit traverse donc
    aussi l'etage %-list), autre seed (31337)."""
    h, rec, live = ia_alt
    n = len(live)
    ref = h.replay_offline(rec)["per_hit"]
    assert _carried(rec, h.replay_offline(rec)["state"])
    assert ref[:n] == live, "C1_25/31337 : live=%s offline=%s" % (live, ref[:n])
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert mut[:n] != ref[:n], \
        "C1_25/31337 : la mutation ne change rien -- ce bras n'exerce pas le canal"
