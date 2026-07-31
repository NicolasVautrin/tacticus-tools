"""#372 -- `CannotBeGuaranteedKilled@0x89`, le gate de sortie anticipee de `get_WillBeKill`.

ARTEFACT NATIF verrouille ici : `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`,
build `rnca9r7q6c`, VERBATIM :

    if (*(char*)(this + 0x89) != 0) return false;               // CannotBeGuaranteedKilled
    m = (*(long*)(this + 0x38) == 0                             // BlockScenarios == null
         || *(int*)(*(long*)(this + 0x38) + 0x18) < 1)          //   ... ou Count < 1
        ? *(int*)(this + 0x1c)                                  // DefaultScenario.Damage.HealthDamage.Min
        : List.get_Item(BlockScenarios, 0)[+0x0c];              // idem, du scenario de BLOCAGE
    return *(int*)this <= m;                                    // CurrentHealth <= m

et son jumeau `...$$get_MightBeKill`, dont le corps ENTIER tient en
`CurrentHealth <= *(int*)(this + 0x20)` -- aucun gate, aucune liste. L'asymetrie est NATIVE.

CE QUE CES GARDES ETABLISSENT, et pourquoi chacune existe :

1. Le gate MORD, et il mord AVANT le choix de borne (`test_gate_wins_over_...`). Sans lui, la borne
   `will_be_kill` serait PERMISSIVE -- elle rendrait True la ou le natif rend False. C'est la
   classe de degradation qu'un entrainement irait exploiter : ni erreur, ni crash.
2. Le gate ne CONTAMINE pas `might_be_kill` (`test_gate_does_not_touch_might_be_kill`). Poser le
   meme gate des deux cotes serait l'erreur symetrique, tout aussi silencieuse.
3. Le gate est INERTE sur la voie multi-hit, et c'est un FAIT DU NATIF, pas une commodite
   (`test_multi_hit_path_never_arms_the_gate`). `BattleQuery$$GetMultiHitAttackPrediction` --
   dont `get_multi_hit_attack_prediction` est le mirror -- fait `memset(result, 0, 0xa0)` puis
   delegue au slot 0xb (`PredictAttack`). Le SEUL ecrivain du champ dans tout le binaire est
   `DamagePrediction$$PredictNormalAttack` (slot 9), atteint par `GetNormalAttackPrediction`.
   C'est ce qui referme le residu « borne permissive » de #344-r2 : sur
   `sort_attackers_by_damage_prediction_key` la borne etait EXACTE, elle n'avait pas de preuve.
4. `DamagePredictionResult$$Add` ne fusionne AUCUN flag booleen (`test_add_does_not_merge_...`) :
   le cumul multi-coups garde celui du coup 1. Le natif ne somme que les bornes, `AppliedHits@0x98`,
   concatene `IndividualHitDamage@0x80` et fusionne `BlockScenarios@0x38` par index.
5. `composite_fields()["killSure"]` porte le MEME gate (`test_composite_killsure_...`) -- c'est LUI
   que lisent les consommateurs de la face prediction (`_will_normal_attack_kill`,
   `_enemy_killed_by_normal_attack`), pas `will_be_kill()`. Un gate pose d'un seul cote laisserait
   la moitie du port permissive.
6. Le gate reste au niveau NU dans `composite_fields` (`test_composite_killsure_stays_nu_at_zero_hp`) :
   le natif rend `true` a `hp == 0` (`0 <= m`), et `decisionView` conserve les unites mortes. Le
   gate `hp > 0` de `will_be_kill()` est PORT-SIDE et documente comme tel ; l'aligner aurait change
   un verdict sur les cibles a 0 PV.

OFFLINE pur (aucune session Frida). ASCII only (cp1252).
"""
from __future__ import annotations

from engine.playbook.probable_damage_event import ProbableDamageEvent
from engine.services.damage_prediction import (DamagePredictionResult, MinMaxDamage,
                                               get_multi_hit_attack_prediction)


def _pred(hp: int, raw_min: int, raw_max: int, *, block_raw_min=None,
          cannot=False) -> DamagePredictionResult:
    """Un `DamagePredictionResult` reduit aux champs que lisent les deux getters."""
    return DamagePredictionResult(
        current_health=hp,
        raw_health_damage=MinMaxDamage(min=raw_min, max=raw_max),
        accurate_health_damage=MinMaxDamage(min=min(raw_min, hp), max=min(raw_max, hp)),
        block_raw_min=block_raw_min,
        cannot_be_guaranteed_killed=cannot)


# --- 1. le gate mord, et il mord EN TETE -----------------------------------------------------

def test_gate_wins_over_the_default_scenario_bound():
    """Bornes largement letales + gate arme -> `get_WillBeKill` rend FALSE. C'est la ligne
    `if (this[0x89]) return false;`, placee AVANT toute lecture de borne."""
    p = _pred(hp=10, raw_min=999, raw_max=999)
    assert p.will_be_kill(), "sans le gate, cette prediction est un sure-kill"
    p.cannot_be_guaranteed_killed = True
    assert not p.will_be_kill(), (
        "`CannotBeGuaranteedKilled@0x89` doit court-circuiter `get_WillBeKill`")


def test_gate_wins_over_the_block_scenario_bound():
    """MEME verdict quand c'est la branche `BlockScenarios[0]+0x0c` qui fournit la borne : le gate
    est en amont du CHOIX de branche, pas dans l'une des deux."""
    p = _pred(hp=10, raw_min=1, raw_max=1, block_raw_min=500)
    assert p.will_be_kill(), "la borne de block (500) tue a elle seule (hp=10)"
    p.cannot_be_guaranteed_killed = True
    assert not p.will_be_kill(), (
        "le gate doit primer AUSSI sur la branche `BlockScenarios[0]`")


# --- 2. l'asymetrie avec `get_MightBeKill` ---------------------------------------------------

def test_gate_does_not_touch_might_be_kill():
    """`get_MightBeKill` = `CurrentHealth <= DefaultScenario.Damage.HealthDamage.Max@0x20`, corps
    ENTIER. Aucun gate : poser le meme des deux cotes serait l'erreur symetrique."""
    p = _pred(hp=10, raw_min=1, raw_max=999, cannot=True)
    assert not p.will_be_kill(), "gate arme -> pas de sure-kill"
    assert p.might_be_kill(), (
        "`get_MightBeKill` ignore `CannotBeGuaranteedKilled` (asymetrie NATIVE)")


# --- 3. la voie multi-hit n'arme JAMAIS le gate ----------------------------------------------

def test_multi_hit_path_never_arms_the_gate():
    """`get_multi_hit_attack_prediction` mirrore `BattleQuery$$GetMultiHitAttackPrediction`, qui
    `memset(result, 0, 0xa0)` puis delegue a `GetAttackPrediction` (slot 0xb = `PredictAttack`).
    Le seul ecrivain du flag est `PredictNormalAttack` (slot 9). Le resultat sort donc TOUJOURS
    avec le flag a False -- y compris sur plusieurs coups, ou plusieurs groupes heterogenes.

    C'est la garde qui REFERME le residu de #344-r2 : la borne de
    `sort_attackers_by_damage_prediction_key` n'etait pas permissive, elle etait exacte."""
    for hits in (1, 2, 5):
        r = get_multi_hit_attack_prediction(
            target_current_health=500, initial_damage=100, hits=hits, profile_type=0)
        assert r.cannot_be_guaranteed_killed is False, (
            "hits=%d : la voie GetMultiHitAttackPrediction ne doit jamais armer le gate" % hits)
    r = get_multi_hit_attack_prediction(
        target_current_health=500, initial_damage=100, hits=2, profile_type=0,
        extra_groups=[{"count": 2, "amount": 50}])
    assert r.cannot_be_guaranteed_killed is False, (
        "les coups additionnels heterogenes n'arment pas le gate non plus")


# --- 4. `Add` ne fusionne aucun flag ---------------------------------------------------------

def test_add_does_not_merge_the_gate_flag():
    """`DamagePredictionResult$$Add` ne touche a AUCUN des cinq booleens contigus @0x88..0x8c.
    Le cumul garde donc celui de `self` (le coup 1) dans les DEUX sens."""
    base = _pred(hp=100, raw_min=10, raw_max=20)
    other = _pred(hp=100, raw_min=10, raw_max=20, cannot=True)
    base.add(other)
    assert base.cannot_be_guaranteed_killed is False, (
        "`Add` ne doit pas propager le flag de `other` vers `self`")

    base2 = _pred(hp=100, raw_min=10, raw_max=20, cannot=True)
    base2.add(_pred(hp=100, raw_min=10, raw_max=20))
    assert base2.cannot_be_guaranteed_killed is True, (
        "`Add` ne doit pas EFFACER le flag de `self` non plus")


# --- 5/6. la consommation : `composite_fields()['killSure']` ---------------------------------

def test_composite_killsure_carries_the_gate():
    """`killSure` est le verdict `get_WillBeKill` tel que le lisent les consommateurs de la face
    prediction. Le gate doit y etre AUSSI, sinon la moitie du port reste permissive."""
    ev = ProbableDamageEvent(target=1, prediction=_pred(hp=10, raw_min=999, raw_max=999))
    assert ev.composite_fields()["killSure"] is True
    assert ev.composite_fields()["cannotBeGuaranteedKilled"] is False

    ev.prediction.cannot_be_guaranteed_killed = True
    f = ev.composite_fields()
    assert f["killSure"] is False, "`killSure` doit porter le gate `CannotBeGuaranteedKilled`"
    assert f["cannotBeGuaranteedKilled"] is True, (
        "la trace doit dire POURQUOI killSure est faux (gate arme vs bornes insuffisantes)")
    assert f["kill"] is True, "`kill` (= MightBeKill) reste vrai : aucun gate de ce cote"


def test_composite_killsure_stays_nu_at_zero_hp():
    """Le gate `hp > 0` de `will_be_kill()` est PORT-SIDE (harnais/probes sans cible) ; le natif,
    lui, rend `true` a `hp == 0` (`0 <= m`). `composite_fields` doit rester le mirror NU --
    `decisionView` conserve les unites mortes, aligner les deux changerait un verdict."""
    ev = ProbableDamageEvent(target=1, prediction=_pred(hp=0, raw_min=5, raw_max=5))
    assert ev.composite_fields()["killSure"] is True, (
        "mirror NU : `0 <= 5` -> le natif rend true")
    assert ev.prediction.will_be_kill() is False, (
        "`will_be_kill()` garde son gate hp>0 documente")
    ev.prediction.cannot_be_guaranteed_killed = True
    assert ev.composite_fields()["killSure"] is False, (
        "le gate NATIF, lui, s'applique meme a hp == 0")
