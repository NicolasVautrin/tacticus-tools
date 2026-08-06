"""CLIQUET #366-r1 -- `WarHowl_ExtraDamage_Unstoppable` (1222) sur un ALLIE buffe.

L'effet est pose par l'ACTIVE `WarHowl` (`ActiveAbilityType` 0x452 = 1106) de `spaceBlackmane`
<<Ragnar>> sur LUI-MEME et sur tout AMI MELEE non-Summon -- ni faction, ni rayon
(`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour` :
`AddEffect(0x4c6, CreateSnapshot(abilityState), source = Caster,
 targets = Caster + UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(Caster, <pool> - Caster,
 OnlyAliveAndTargetable)), 0x2 = Summon, OnlyAliveAndTargetable), turns = Get(1))`).
`turns = Get(1)` => il ne vaut QUE le tour du cast : le montage caste et frappe DANS LE MEME TOUR.

⚠ Le CASTER ne peut pas mesurer sa propre face (le cast consomme son activation), donc le porteur
mesure est TOUJOURS un ALLIE -> porteur != source, et le residu PARTAGE #382 (niveau/multiplicateur
lus sur le PORTEUR au lieu de l'`AbilityState` de la SOURCE) devient VISIBLE. Il est NEUTRALISE ici
en imposant le MEME `AbilityVariablesMultiplierPercentage` aux deux (`--unit-stat`), et MESURE a
part dans le probe (`--mult SRCMULT` : +177 par coup, cf. la fiche).

DEUX CANAUX GARDES, chacun avec sa vue ROUGE mesuree (fiche
`docs/rl/case-366-r1-war-howl-extra-damage.md` §5) :

  * DEGAT   -- `...WarHowl_ExtraDamage_UnstoppableEffect$$CreateEffectDamageBonusForAttack` =
               `ForAddition(get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack,
                            ConfigVar(0x08 = extraDmg))`.
               ROUGE (inscription retiree d'`EFFECT_CLASSES`) :
                   LIVE    n=3 [5127, 4801, 5049]
                   OFFLINE n=3 [3532, 3206, 3454]
                   DELTA   [1595, 1595, 1595]        (= round(extraDmg[50] 886 x 1.80))
  * CRIT    -- `...$$CreateCritChanceBonus` = les MEMES trois noeuds PLUS
               `AmountIsGreaterThanZero(StatAmount(Caster, 0x9 CriticalChance, StatPart.Current))`.
               ROUGE (gate desarme, bras cc=0) :
                   LIVE    n=3 [5127, 4801, 5049]
                   OFFLINE n=3 [5994, 5892, 4383]    (le port se met a criter, le natif non)
               ROUGE (magnitude retiree, bras cc=40) :
                   LIVE    n=3 [5994, 5892, 5171]
                   OFFLINE n=3 [5994, 5892, 4383]

Probe de mesure : `probe_366_r1_war_howl_extra_damage.py` (foyer unique du montage -- `stage` et
`strike` sont IMPORTES ici plutot que re-transcrits : deux transcriptions du meme montage finissent
par diverger).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import charge_regime                          # noqa: E402,F401  (fixture)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki.war_howl import WarHowlExtraDamageUnstoppableEffect  # noqa: E402
from probe_366_r1_war_howl_extra_damage import (ALIGNED_MULT, EFFECT_NAME, RAGNAR,  # noqa: E402
                                                stage, strike)

_ALLY = "spaceWulfen"               # <<Ulf>>, ami MELEE non-Summon -> RECEVEUR de 1222
_A_UNITS = "necroWarden,necroOverlord"
_EFFECT_TYPE = 1222


def _extra(crit: str):
    """Options de build : regime de crit + ALIGNEMENT des multiplicateurs (neutralise #382)."""
    out = ["--crit", crit]
    for vis in (RAGNAR, _ALLY):
        out += ["--unit-stat", "%s:AbilityVariablesMultiplierPercentage=%d" % (vis, ALIGNED_MULT)]
    return out


def _measure(charge_regime, do_cast, crit, seed="777", board="MC1_67"):
    """Monte, (option) caste, frappe, rejoue offline. ECHEC FORT si le regime n'est pas atteint --
    un `skip` VERT mentirait sur une garde qui n'a rien garde."""
    h = charge_regime(p_units="%s,%s" % (RAGNAR, _ALLY), a_units=_A_UNITS,
                      seed=seed, board=board, extra=_extra(crit))
    rec, why = stage(h, _ALLY, do_cast)
    assert rec is not None, "regime NON ATTEINT (cast=%s) : %s" % (do_cast, why)
    assert rec["mult_source"] == rec["mult_carrier"], (
        "multiplicateurs NON alignes (%d vs %d) -- la garde mesurerait #382 au lieu de ce port"
        % (rec["mult_source"], rec["mult_carrier"]))
    live, why = strike(h, rec)
    assert live is not None, "attaque non mesurable : %s" % why
    return rec, live, h.replay_offline(rec)


@pytest.fixture(scope="module")
def wh_nocrit(charge_regime):
    """BRAS DEGAT -- `CritChance = 0` : le gate `AmountIsGreaterThanZero` est FERME cote natif,
    donc SEULE la face DEGAT peut mordre. Un port sans le gate se mettrait a criter."""
    return _measure(charge_regime, True, "0,700")


@pytest.fixture(scope="module")
def wh_witness(charge_regime):
    """TEMOIN -- aucun cast, 1222 n'existe pas : le port ne doit rien fabriquer."""
    return _measure(charge_regime, False, "0,700")


@pytest.fixture(scope="module")
def wh_crit(charge_regime):
    """BRAS CRIT -- `CritChance = 40` : le gate est OUVERT, le natif roule a 40 + 36 = 76."""
    return _measure(charge_regime, True, "40,700")


@pytest.fixture(scope="module")
def wh_alt(charge_regime):
    """GENERALISATION -- meme invariant, AUTRE board (`C1_25`, a elevation), AUTRE seed (31337)."""
    return _measure(charge_regime, True, "0,700", seed="31337", board="C1_25")


def _carried(rec, off):
    """1222 doit etre MATERIALISE offline sur l'attaquant -- sinon le test compare deux absences."""
    st = off["state"]
    return [e for e in (st.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == _EFFECT_TYPE or e.name == EFFECT_NAME]


def test_registry_binds_dedicated_class():
    """Garde STRUCTURELLE (offline, sans jeu) : 1222 a sa PROPRE classe.

    Le slot `Il2CppClass*` `0x1833908e8` n'est partage par aucun autre des 607 enregistrements
    d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`, et le `$$.ctor` de l'effet n'a
    qu'UN appelant (`...EffectsDatabase.<>c$$<InitializeEffects>b__14_240`) -- une fabrique, un id."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is WarHowlExtraDamageUnstoppableEffect


def test_gates_are_tristate_offline():
    """Les DEUX hooks se taisent tant que leur contexte ne PROUVE pas le regime.

    Le natif ne se rabat jamais sur melee quand `GetAbilityAttackRangeType` ne tranche pas (#106),
    et `AmountIsGreaterThanZero(StatAmount(Caster, CriticalChance))` exige une valeur > 0 : une
    contribution rendue sans preuve serait un bonus inconditionnel."""
    e = WarHowlExtraDamageUnstoppableEffect(name=EFFECT_NAME, effect_type=_EFFECT_TYPE, level=1,
                                            ability_level=50, ability_variables_multiplier=180)
    # -- face DEGAT
    assert e.create_effect_damage_bonus_for_attack(is_ranged=None) is None      # nature inconnue
    assert e.create_effect_damage_bonus_for_attack(is_ranged=True) is None      # distance
    assert e.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                   is_normal_attack=False) is None   # speciale
    got = e.create_effect_damage_bonus_for_attack(is_ranged=False, is_normal_attack=True)
    assert got is not None and got.kind == "Addition" and got.value > 0, \
        "melee + normale PROUVEES -> ForAddition(extraDmg) ; obtenu %r" % (got,)
    # -- face CHANCE DE CRIT
    # #589-r1-r1 : `get_OwnerIsCaster` (le QUATRIEME noeud) a MIGRE du canal vers la classe (le
    # balayage crit est desormais BOARD-WIDE, `board_effect_carriers`). L'identite du porteur fait
    # donc partie du contexte, et un `att_ctx` sans elle ferme ce noeud -- ce n'est pas un
    # assouplissement du test, c'est le noeud lu a sa nouvelle place native.
    ok = {"is_ranged": False, "is_normal_attack": True, "caster_crit_chance": 40,
          "owner_id": 1, "att_id": 1}
    assert e.create_effect_crit_chance_bonus_for_attack(None) is None           # ctx absent
    assert e.create_effect_crit_chance_bonus_for_attack({**ok, "is_ranged": True}) is None
    assert e.create_effect_crit_chance_bonus_for_attack({**ok, "is_normal_attack": False}) is None
    assert e.create_effect_crit_chance_bonus_for_attack({**ok, "caster_crit_chance": 0}) is None, \
        "AmountIsGreaterThanZero(StatAmount(Caster, CriticalChance)) : cc=0 -> AUCUN bonus"
    assert e.create_effect_crit_chance_bonus_for_attack({**ok, "caster_crit_chance": None}) is None
    assert (e.create_effect_crit_chance_bonus_for_attack(ok) or 0) > 0


def test_extra_damage_matches_native(wh_nocrit):
    """CAS ROUGE AVANT LE FIX -- l'allie qui PORTE 1222 frappe plus fort, du montant exact."""
    rec, live, off = wh_nocrit
    assert _carried(rec, off), \
        "1222 n'est pas materialise offline sur l'attaquant -- le test comparerait deux absences"
    assert off["per_hit"] == live, (
        "DEGAT : le port ne compte pas la contribution de 1222 -- live=%s offline=%s (delta=%s)"
        % (live, off["per_hit"],
           [l - o for l, o in zip(live, off["per_hit"])] if len(live) == len(off["per_hit"])
           else "n different"))


def test_witness_without_cast(wh_witness):
    """TEMOIN -- sans cast, 1222 n'existe pas : la salve NUE doit coincider.

    Verrouille que le port ne fabrique pas de degat quand l'effet est absent."""
    rec, live, off = wh_witness
    assert not _carried(rec, off), "1222 ne doit pas exister sans cast"
    assert off["per_hit"] == live, "TEMOIN : live=%s offline=%s" % (live, off["per_hit"])


def test_effect_actually_bites_live(wh_nocrit, wh_witness):
    """Le natif SEPARE bien les deux bras -- sinon les tests ci-dessus passeraient pour une raison
    TRIVIALE (aucun bonus nulle part, deux zeros qui s'accordent). On compare deux mesures LIVE,
    jamais le port : c'est ce qui rend le regime PROBANT."""
    _, live_buffed, _ = wh_nocrit
    _, live_nu, _ = wh_witness
    assert len(live_buffed) == len(live_nu), \
        "1222 ne touche PAS l'axe COUPS : les deux salves doivent avoir le meme n"
    assert sum(live_buffed) > sum(live_nu), (
        "le natif doit frapper PLUS FORT avec 1222 qu'sans -- buffe=%s nu=%s (si egal, le montage "
        "n'exerce pas l'effet et la garde ne garde rien)" % (live_buffed, live_nu))


def test_crit_chance_matches_native(wh_crit):
    """BRAS CRIT -- `CritChance = 40 > 0` ouvre `AmountIsGreaterThanZero`, le natif roule a
    40 + `extraCritChance[50]` = 76. Un port sans la face CRIT roulerait a 40 : memes tirages,
    crits DIFFERENTS (vue rouge mesuree : 3e coup 5171 live vs 4383 offline)."""
    rec, live, off = wh_crit
    assert _carried(rec, off), "1222 doit etre present (sinon la face CRIT n'est pas exercee)"
    assert rec["crit_chance"] > 0, \
        "CritChance=%d : le gate natif serait FERME, ce bras ne prouverait rien" % rec["crit_chance"]
    assert off["per_hit"] == live, (
        "CRIT : live=%s offline=%s" % (live, off["per_hit"]))


def test_extra_damage_other_board(wh_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`, a ELEVATION -- l'additif traverse donc
    aussi l'etage %-list), autre seed (31337)."""
    rec, live, off = wh_alt
    assert _carried(rec, off)
    assert off["per_hit"] == live, (
        "C1_25/31337 : live=%s offline=%s" % (live, off["per_hit"]))
