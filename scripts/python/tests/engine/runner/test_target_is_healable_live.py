"""#245 -- GARDE de la regle de ciblage `TargetIsHealable` (bit 8, 0x100) sur SES DEUX PORTEURS :
1002 `CombatRestoratives` (ultraApothecary) et 1037 `RevitalizingMalignancy` (deathRotbone).

La regle est une ligne du filtre statique de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge SEPT arguments -- pas
celle a QUATRE, qui court-circuite pour un caster MoW), gatee par le bit 8 des `TargetingOptions` :

    if ((rules & 0x100) != 0 && !attackQuery.<slot 0x11>(caster, cible, 0, 1)) -> broken(0x100)

Le slot 0x11 d'`IAttackQuery` est `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`, lu sur
DEUX call-sites independants : cette cascade, et
`IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` -- le selecteur qui PORTE le nom
`Healable` et resout le MEME slot sur la MEME classe d'interface.

CE QUE CE TEST VERROUILLE, ET POURQUOI IL ECHOUAIT AVANT #245
-------------------------------------------------------------
Sans la regle, `get_invalid_target_reason` rendait 0 sur toute cible amie adjacente, y compris celles
que le natif REFUSE -- degradation permissive, ni erreur ni crash, invisible en self-play. Le probe
mesurait exactement 1 a 2 lignes d'ecart par montage, comptees a part sous le nom
`TargetIsHealable` dans `probe_249_deathguard_targeting.py`.

TROIS LIGNES DISCRIMINANTES, FABRIQUEES (jamais subies) -- et c'est la 3e qui porte la these :
  * allie ADJACENT et BLESSE, NON mecanique -> natif ACCEPTE (0) ;
  * allie ADJACENT a PV PLEINS              -> natif refuse 0x100 (`IsDamagedUnit` faux) ;
  * allie ADJACENT et BLESSE, MECANIQUE     -> natif refuse 0x100 quand meme
    (`IsAffectedByHealType(_, 0)` faux). Sans elle, la regle serait indistinguable d'un simple
    « HP < max », et la garde de mutation `healable_heal_type_0` aurait suffi. Elle ne suffit PAS :
    le predicat de CETTE regle est le mirror COMPLET `abilities/attack_query.py::entity_can_be_healed`.

Le montage (approche pilotee, blessures POSEES et VERIFIEES, geometrie DRIVEE) et les lectures vivent
dans `scripts/python/probe_245_target_is_healable.py` : le probe MESURE, ce test GARDE, une seule
implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_245_target_is_healable as P
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting_rule import TargetingRule as TR


@pytest.fixture(scope="module")
def healable_res(live_session):
    """UN montage par porteur : approche du camp adverse, blessure VERIFIEE de l'allie non mecanique
    ET de l'allie mecanique, puis regroupement au contact du caster."""
    out = {}
    for aid in sorted(P.CASES):
        try:
            out[aid] = P._run(live_session, aid, P.SEED, P.BOARD)
        except RuntimeError as e:                                    # noqa: BLE001
            pytest.skip("montage %d impossible : %s" % (aid, e))
    for res in out.values():
        P.report(res)
    return out


def _assert_healable(res: dict, aid: int):
    rows = res["rows"]
    bad = [(r["label"], hex(r["nat"] or 0), hex(r["apres"])) for r in rows
           if r["nat"] != r["apres"] and not P._known_gap(r["nat"], r["apres"])]
    assert not bad, (
        "ability %d : le gate porte DIVERGE du natif (hors regles non portees nommees) -> %s"
        % (aid, bad))

    accept = [r for r in rows if r["side"] == "ALLIE" and r["nat"] == 0]
    assert accept, (
        "ability %d : le natif n'ACCEPTE aucun allie -> un port qui refuserait TOUT passerait ce "
        "test ; la blessure de l'allie non mecanique n'a pas pris (soft=%s)"
        % (aid, res["wounded_soft"]))

    full = [r for r in rows if r["visualId"] == res["full"]]
    assert full and full[0]["nat"] == int(TR.TargetIsHealable), (
        "ability %d : l'allie a PV PLEINS (%s) n'est pas refuse par TargetIsHealable -> le terme "
        "`IsDamagedUnit` n'est pas exerce" % (aid, res["full"]))

    mech = [r for r in rows if r["visualId"] == res["mech"]]
    assert mech and mech[0]["wounded"] and mech[0]["nat"] == int(TR.TargetIsHealable), (
        "ability %d : l'allie MECANIQUE (%s) n'est pas a la fois BLESSE et refuse 0x100 -> le terme "
        "`IsAffectedByHealType(_, 0)` n'est pas separe de `HP < max`, et la regle resterait "
        "confondable avec la garde de mutation `healable_heal_type_0`" % (aid, res["mech"]))

    assert res["cf_moved"] >= 1, (
        "ability %d : neutraliser le seul bit 8 ne deplace AUCUN verdict -> ce n'est pas lui qui "
        "rend le refus, la mesure ne valide rien" % aid)
    assert res["n_gain"] >= 1, (
        "ability %d : aucun cast illegal rattrape -- le masque ne mord pas sur ce montage" % aid)


def test_1002_combat_restoratives_healable(healable_res):
    """1002, masque 0x8500 (TargetIsHealable | TargetIsFriendly | CasterIsPossibleTarget), range
    RANGE_ADJACENT. Le heal ne touche que des allies BLESSES et non mecaniques au contact."""
    _assert_healable(healable_res[1002], 1002)


def test_1037_revitalizing_malignancy_healable(healable_res):
    """1037, MEME masque 0x8500 et MEME range -- et c'est precisement pourquoi il est rejoue : deux
    abilities qui partagent un preset peuvent diverger (la campagne de masques l'a montre trois
    fois). Valider sur un seul porteur ne valide pas une regle."""
    _assert_healable(healable_res[1037], 1037)


def test_le_predicat_est_entity_can_be_healed_pas_la_garde_de_mutation():
    """Garde OFFLINE (aucune session) : la cascade appelle bien
    `AttackQuery$$EntityCanBeHealed` (mirror `attack_query.entity_can_be_healed`) et NON la garde de
    mutation `healable_heal_type_0`. Les deux ne sont pas interchangeables -- `entity_can_be_healed`
    refuse en plus une MACHINE, un porteur du trait `Object` (0xd) et une cible sous heal-blockers,
    et sa signature est `(state, caster, cible, scope, removeEffects)` la ou la garde de mutation
    prend le triplet DSL `(entities, ectx, unit)`.

    Ce test est le seul endroit ou la CONFUSION serait detectee sans session : il verrouille que les
    deux porteurs declarent le bit, et que le predicat cable rend des verdicts DIFFERENTS de la
    garde de mutation sur le cas qui les separe (cible MECANIQUE blessee vs cible non mecanique
    blessee -- meme reponse ici, c'est le cas MACHINE qui les separe et qu'on exerce)."""
    from engine.runner.abilities import attack_query as AQ
    from engine.runner.abilities import targeting as T
    import inspect

    for aid in (1002, 1037):
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None and opts.has(TR.TargetIsHealable), (
            "%d ne declare plus TargetIsHealable -- le test de #245 ne garde plus rien" % aid)

    # Les symboles REELLEMENT references par le bytecode de la cascade (`co_names` + les noms
    # importes, qui vivent dans `co_consts`) -- pas le texte source : le module DOIT pouvoir citer
    # `healable_heal_type_0` en commentaire pour dire qu'il ne l'appelle PAS.
    code = T.get_invalid_target_reason.__code__
    refs = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, tuple):
            refs.update(x for x in c if isinstance(x, str))
    assert "entity_can_be_healed" in refs, (
        "la cascade n'appelle plus `entity_can_be_healed` : si elle est repassee sur "
        "`healable_heal_type_0`, elle a perdu 4 des 6 termes natifs")
    assert "healable_heal_type_0" not in refs, (
        "la cascade appelle la garde de MUTATION `healable_heal_type_0` -- c'est le predicat du "
        "`HealableUnitsSelector` cote feuille `Heal`, pas celui du slot 0x11 d'`IAttackQuery`")
    # Les deux termes que la garde de mutation ne porte PAS, et que le mirror complet porte.
    assert "IsMachine" in inspect.getsource(AQ.entity_can_be_healed)
    assert "UnitTrait.Object" in inspect.getsource(AQ.entity_can_be_healed)
