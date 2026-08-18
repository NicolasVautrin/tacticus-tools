"""#512-r7 -- L'ORDRE de la CLOTURE d'attaque sur une feuille AUTONOME.

#512-r4 et #512-r6 avaient ferme la CARDINALITE des deux evenements de cloture (`On(9 = Attack)`,
`On(10 = AttackDamageAttack)`) : une feuille NUE ne clot pas, c'est le noeud parent. Ce qu'ils
n'avaient PAS ferme, c'est leur RANG sur une feuille AUTONOME (`isOutsideAttack = 1`) -- celle que
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` emballe dans son PROPRE
`IdunBattle.Entities.Behaviours.AttackBehaviour`.

RE (decompile = verite, build `t6dpr4k06g`), les TROIS lectures qui fixent l'ordre :

  1. `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` -- la boucle par cible est, verbatim :

         if (prev == null || prev != cur)  <slot 0x3a = 58 StartAttack>     -> On(5)
         <behaviour ENFANT>                                                  # AttackDamage / AbilityDamage
         if (next == null || next != cur)  <slot 0x3b = 59 FinishAttack>    -> On(9), puis On(10)

     La cloture part donc **APRES** le behaviour enfant, c'est-a-dire apres TOUTE l'operation de
     degat.

  2. `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` -- appelee PAR COUP depuis
     les deux `ExecuteHit`, elle n'emet que :

         if ((char)didBlock != '\\0')  FUN_1800280e0(0x50, .., 0x3c, entities)   # On(UnitBlocked)
         FUN_1800280e0(0x50, .., 8, entities)                                    # On(AttackHit)

  3. `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` -- sa DERNIERE instruction est
     `FUN_1800280e0(0x50, .., 0x42, entities)` (`On(FinalDamage = 66)`), et l'appel a
     `RegisterFinalDamage` est lui-meme la DERNIERE instruction d'`IdunBattle.Operations.
     AbilityDamageOperation$$Execute` (`RegisterFinalDamage(...) ; return this ;`) comme de son
     jumeau `AttackDamageOperation$$Execute`.

=> ORDRE NATIF d'une feuille AUTONOME : `... 0x3c?, 8, 0x42, 9, 10`.
=> ORDRE DU PORT AVANT CETTE TRANCHE : `9, 0x3c?, 8, 0x42, 10` -- la cloture ENCADRAIT des
   evenements que le natif emet avant elle. Mesure directe du 2026-08-18 sur
   `execute_ability_attack(is_outside_attack=True)` : `[5, 6, 57, 15, 16, 9, 8, 66, 10]`.

CE QUE CE FICHIER GARDE (par MESURE sur l'operation REELLE, aucune lecture de source) :
  (1) la SEQUENCE `8 -> 66 -> 9 -> 10` sur une feuille AUTONOME de la famille ATTACK ;
  (2) le CONTRE-CAS -- le regime d'avant, rejoue en substituant la facade after-hit par une version
      qui clot elle-meme -- rend `9 -> 8 -> 66 -> 10`, donc la mesure est DISCRIMINANTE ;
  (3) la meme sequence sur la famille ABILITY, ou `On(10)` est absent : `8 -> 66 -> 9` ;
  (4) le vecteur `On(0x3c = UnitBlocked)` reste AVANT `On(8)` et AVANT la cloture (il vient du meme
      `EvaluateAfterHitTriggers`) ;
  (5) le jumeau `execute_normal_like` : `8` AVANT `9` (cette voie n'emet pas `On(0x42)` -- ecart
      distinct, residu **#512-r9**, cf. le commentaire de son call-site).

⚠ RAYON DE SOUFFLE, MESURE AVANT LE DEPLACEMENT (`probe_437_on9_blast_radius.py` etape 1, et le
recensement par event_id du meme jour) : **37** classes-triggers ecoutent `On(9)`, **1** ecoute
`On(8)` (`RefusalToBeOutdoneRecordHitAbility`, porteur `emperExultant`), **1** ecoute `On(66)`
(`RealityUnboundExtraMaxDamageAbility`, porteur `thousTzaangor`), **2** ecoutent `On(0x3c)`
(`AnvilShield*`). La fiche du residu annoncait « les trois familles ont des ecoutants DISJOINTS,
donc aucun consommateur porte ne l'observe » : les ENSEMBLES sont bien disjoints, mais le PORTEUR
ne l'est pas -- `thousTzaangor` porte a la fois `RealityUnboundAbility` (`On(9)`) et
`RealityUnboundExtraMaxDamageAbility` (`On(66)`). Les deux gates ne se lisent pas l'un l'autre
(`has_effect(1205)` contre `received_damage_this_turn`), donc l'ecart reste inerte SUR CE PORTEUR ;
il ne l'est pas par construction, et c'est pour ca qu'on garde la SEQUENCE et pas un compte.

ASCII only. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

# Le garde `declencheur_guard` (#486-r15) refuse un fichier de test NEUF qui ne dit pas ce qui doit
# changer pour qu'il change de verdict. Meme forme -- et meme raison DERIVEE -- que son voisin
# `test_512r4_on9_cardinalite_offline.py` : ce fichier n'ouvre AUCUN chemin (`open`, `read_text`,
# `Path`, `rglob`, `gameconfig` : zero occurrence), donc sa fermeture tient entierement dans la
# cascade d'imports derivee de son foyer.
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": (
        "Fichier PUREMENT offline et PUREMENT structurel : il monte deux unites en memoire, joue "
        "l'operation de degat reelle et compte l'ORDRE des evenements emis. Il ne lit ni le "
        "binaire, ni `data/symbols/**`, ni le gameconfig -- il n'ouvre aucun chemin. Sa fermeture "
        "d'imports tient donc dans la cascade derivee de son foyer "
        "(`runner/operations/damage_ops/{ability,normal_like}.py`, "
        "`runner/operations/triggers/dispatch/attack.py`), qu'il ne faut PAS re-declarer ici "
        "(#531). `chemins` vide n'est pas un aveu : c'est le resultat."
    ),
}

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,     # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation          # noqa: E402
from engine.runner.operations.triggers.dispatch import attack as A         # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.state import State                                      # noqa: E402

_ON_BLOCK = int(EventTriggerType.UnitBlocked)          # 0x3c = 60
_ON_HIT = int(EventTriggerType.AttackHit)              # 8
_ON_FINAL = int(EventTriggerType.FinalDamage)          # 0x42 = 66
_ON_ATTACK = int(EventTriggerType.Attack)              # 9
_ON_ADA = int(EventTriggerType.AttackDamageAttack)     # 10


def _etat_de_degat(hp_cible: int = 1000):
    """Un etat MINIMAL mais REEL : deux unites completes, un PRNG cale. Sans PRNG,
    `execute_ability_attack` rend `None` en silence et le test serait vert sur zero evenement."""
    st = State()
    st.rng = IntBasedMersenneTwister(1234)
    ids = []
    for i in (0, 1):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id="ultraEliminatorSgt", alive=True))
        e.add_component(HealthComponent(hp=hp_cible, hp_max=hp_cible))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(i * 2, 0))
        e.add_component(StatsComponent(
            ctx=UnitContext(entity_id=e.id, visual_id="ultraEliminatorSgt")))
        ids.append(e.id)
    return st, ids[0], ids[1]


def _compter(monkeypatch):
    """Compte les `TriggerEvent` par type, en substituant le dispatcher DANS le module qui l'appelle
    (`dispatch/attack.py`) : `from .core import ...` est une liaison de FORME A, donc patcher
    `dispatch.core` NE MORDRAIT PAS."""
    vus = []
    monkeypatch.setattr(A, "evaluate_trigger_operation",
                        lambda state, ev: (vus.append(int(ev.event_id)), [])[1])
    return vus


def _seq(vus, *ev_ids) -> list:
    vises = set(int(e) for e in ev_ids)
    return [e for e in vus if e in vises]


def test_la_feuille_AUTONOME_clot_APRES_On8_et_APRES_On66(monkeypatch):
    """(1) LA MESURE CENTRALE. `AttackBehaviour$$Execute` pousse `FinishAttack` APRES le behaviour
    enfant, et `RegisterFinalDamage` est la derniere instruction de l'`Execute` de degat -> la paire
    de cloture arrive EN DERNIER."""
    st, att, tgt = _etat_de_degat()
    vus = _compter(monkeypatch)
    r = AttackDamageOperation.execute_ability_attack(
        st, att, tgt, 10, 10, 0, 1, damage_profile="Bolter", is_melee=True,
        is_attack_damage_op=True, is_outside_attack=True)
    assert (r or {}).get("total"), (
        "l'operation doit vraiment s'executer, sinon la mesure est VIDE : %r" % (r,))
    assert _seq(vus, _ON_HIT, _ON_FINAL, _ON_ATTACK, _ON_ADA) == \
        [_ON_HIT, _ON_FINAL, _ON_ATTACK, _ON_ADA], vus


def test_CONTRE_CAS_le_regime_d_avant_rend_l_ordre_INVERSE(monkeypatch):
    """(2) La mesure ci-dessus n'est discriminante que si le regime d'AVANT #512-r7 rend AUTRE
    CHOSE. On le rejoue en substituant la facade after-hit par une version qui clot ELLE-MEME en
    tete -- c'est litteralement ce que faisait `after_hit_ability_attack(emit_finish_attack=True)`.
    Le patch est pose sur le MODULE `dispatch.attack`, que `damage_ops/ability.py` resout en forme
    MODULE : il MORD."""
    st, att, tgt = _etat_de_degat()
    vraie = A.after_hit_ability_attack

    def _facade_d_avant(state, attacker_id, target_id, is_crit, profile=None, did_block=False):
        A.finish_attack_triggers(state, attacker_id, target_id, ranged=False, profile=profile,
                                 is_crit=is_crit, was_block=bool(did_block))
        return vraie(state, attacker_id, target_id, is_crit, profile=profile, did_block=did_block)

    monkeypatch.setattr(A, "after_hit_ability_attack", _facade_d_avant)
    vus = _compter(monkeypatch)
    r = AttackDamageOperation.execute_ability_attack(
        st, att, tgt, 10, 10, 0, 1, damage_profile="Bolter", is_melee=True,
        is_attack_damage_op=True, is_outside_attack=True)
    assert (r or {}).get("total"), (r,)
    ordre = _seq(vus, _ON_HIT, _ON_FINAL, _ON_ATTACK, _ON_ADA)
    assert ordre[0] == _ON_ATTACK, (
        "le CONTRE-CAS doit montrer la cloture EN TETE (l'ordre d'avant) : %r" % (ordre,))
    assert ordre != [_ON_HIT, _ON_FINAL, _ON_ATTACK, _ON_ADA], ordre


def test_famille_ABILITY_meme_ordre_SANS_On10(monkeypatch):
    """(3) `IdunBattle.Operations.AbilityDamageOperation$$Execute` ne pose PAS `currentAttack@+0x2c`
    -> `FinishAttackOperation$$Execute` emet `On(9)` et saute `On(10)`. Le RANG, lui, est le meme :
    la cloture reste apres `On(8)` et `On(0x42)` (que la famille ABILITY emet aussi -- son `Execute`
    appelle le MEME `RegisterFinalDamage`)."""
    st, att, tgt = _etat_de_degat()
    vus = _compter(monkeypatch)
    r = AttackDamageOperation.execute_ability_attack(
        st, att, tgt, 10, 10, 0, 1, damage_profile="Bolter", is_melee=True,
        is_attack_damage_op=False, is_outside_attack=True)
    assert (r or {}).get("total"), (r,)
    assert _seq(vus, _ON_HIT, _ON_FINAL, _ON_ATTACK, _ON_ADA) == \
        [_ON_HIT, _ON_FINAL, _ON_ATTACK], vus


def test_On_block_reste_AVANT_On8_et_avant_la_cloture(monkeypatch):
    """(4) `EvaluateAfterHitTriggers` teste `didBlock` AVANT l'emission inconditionnelle d'`On(8)`.
    Le deplacement de la cloture ne doit pas avoir reordonne ce couple-la.

    On appelle la FACADE directement avec `did_block=True` : passer par l'operation complete ferait
    dependre la mesure d'un tirage de block, donc d'un test intermittent. La facade EST le mirror
    d'`EvaluateAfterHitTriggers`, c'est-a-dire exactement l'etage qui porte cet ordre."""
    st, att, tgt = _etat_de_degat()
    vus = _compter(monkeypatch)
    A.after_hit_ability_attack(st, att, tgt, is_crit=False, profile="Bolter", did_block=True)
    assert _seq(vus, _ON_BLOCK, _ON_HIT, _ON_ATTACK) == [_ON_BLOCK, _ON_HIT], vus


def test_le_jumeau_normal_like_clot_APRES_On8(monkeypatch):
    """(5) `execute_normal_like` porte le MEME couple facade/cloture. Il n'emet pas `On(0x42)` (ecart
    distinct de celui-ci -- residu ouvert), mais le rang `8` -> `9` doit etre celui du natif."""
    st, att, tgt = _etat_de_degat()
    vus = _compter(monkeypatch)
    r = AttackDamageOperation.execute_normal_like(
        st, att, tgt, 50, 0, hits=1, spread_pct=0, damage_profile="Bolter", is_melee=True,
        is_attack_damage_op=True, is_outside_attack=True)
    assert (r or {}).get("total"), (
        "l'operation doit vraiment s'executer, sinon la mesure est VIDE : %r" % (r,))
    assert _seq(vus, _ON_HIT, _ON_ATTACK) == [_ON_HIT, _ON_ATTACK], vus


def test_le_jumeau_normal_like_NE_clot_PAS_sur_feuille_NUE(monkeypatch):
    """(5 bis) TEMOIN du gate : `is_outside_attack=False` -> aucune cloture, mais `On(8)` reste. La
    cardinalite de #512-r4 n'a pas ete perdue en deplacant l'emission."""
    st, att, tgt = _etat_de_degat()
    vus = _compter(monkeypatch)
    r = AttackDamageOperation.execute_normal_like(
        st, att, tgt, 50, 0, hits=1, spread_pct=0, damage_profile="Bolter", is_melee=True,
        is_attack_damage_op=True, is_outside_attack=False)
    assert (r or {}).get("total"), (r,)
    assert _seq(vus, _ON_HIT, _ON_ATTACK) == [_ON_HIT], vus
