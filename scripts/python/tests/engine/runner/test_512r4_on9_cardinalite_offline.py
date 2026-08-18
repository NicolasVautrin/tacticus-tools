"""#512-r4 / #512-r6 -- CARDINALITE ET ORDRE des DEUX evenements de cloture d'attaque.
Le natif les emet PAR CIBLE au niveau du NOEUD, le port les emettait PAR FEUILLE au niveau de
l'OPERATION.

RE (decompile = verite). `On(9)` sort d'`IdunBattle.Operations.FinishAttackOperation$$Execute`, qui
n'est atteint que par le slot **59** (`FinishAttack`) du processeur. Ce slot est pousse par des
NOEUDS de l'arbre, JAMAIS par une operation de degat -- les cinq emetteurs, relus au build courant :

  * `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : `if (next == null || next != cur)`,
    symetrique du `StartAttack` sous `if (prev == null || prev != cur)` -> UNE fois par cible
    DISTINCTE de la liste (qui est `OrderBy`-ee quand `Count > 1`, donc les repetitions sont
    groupees) ;
  * `IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour$$Execute` : a chaque changement de
    cle du `Dictionary<UnitEntity, List<behaviour>>`, plus une derniere fois a la sortie -- donc
    UNE par cible distincte de la serie, MEME si cette cible porte DEUX behaviours ;
  * `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` : autour de
    CHAQUE maillon ;
  * `IdunBattle.Entities.Behaviours.FinishAttackBehaviour$$Execute` ;
  * la voie MESSAGE.

#512-r6 -- LE SECOND EVENEMENT, `On(AttackDamageAttack = 10)`, SORT DE LA MEME FONCTION. Fin de
`FinishAttackOperation$$Execute`, relue verbatim au build `t6dpr4k06g` :

    FUN_1800280e0(0x50, <IOperationProcessor>, proc, 9, entities)       # On(Attack = 9)  : TOUJOURS
    if (*(char *)(currentAttack + 0x2c) != '\\0')
        FUN_1800280e0(0x50, <IOperationProcessor>, proc, 10, entities)  # On(10)          : GATE

`currentAttack` est le `GetCurrentAttack()` lu en TETE de la fonction ; son octet `+0x2c` est pose
par la SEULE `IdunBattle.Operations.AttackDamageOperation$$Execute`. Cote port c'est exactement
`is_attack_damage_op` -- pas un second canal.

CE QUE CE FICHIER GARDE, ET IL LE FAIT PAR MESURE, PAS PAR LECTURE DE SOURCE :
  (1) un noeud `SortedAttackSeries` portant DEUX feuilles sur la MEME cible emet **UN** `On(9)` --
      et le CONTRE-CAS integre (des feuilles qui emettent elles-memes, c'est-a-dire le port
      d'avant #512-r4) en produit **DEUX**, donc la mesure est discriminante ;
  (2) la facade after-hit d'ability n'emet `On(9)` que si `emit_finish_attack` est vrai, et ses deux
      AUTRES vecteurs (`On(0x3c = UnitBlocked)`, `On(8 = AttackHit)`) partent dans les DEUX regimes
      -- ils viennent d'`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`, donc de
      l'OPERATION, et les confondre aurait eteint le cluster on-block avec la cloture ;
  (3) MEME cardinalite pour `On(10)` : UN par cible distincte du noeud, DEUX dans le contre-cas ;
  (4) l'ORDRE `9` PUIS `10` sur la voie NOEUD -- l'assertion porte sur la SEQUENCE, pas sur des
      comptes (avant #512-r6 le noeud cloturant APRES ses feuilles, `On(10)` partait le PREMIER) ;
  (5) le GATE de famille : un noeud dont TOUTES les feuilles sont de la famille ABILITY
      (`AbilityDamageOperation`, qui ne pose PAS `+0x2c`) emet `On(9)` et **AUCUN** `On(10)` ;
  (6) le gate de FEUILLE, mesure sur l'OPERATION REELLE : `execute_ability_attack` avec
      `is_outside_attack = False` n'emet NI 9 NI 10, et avec `True` emet les deux. Ce cran-la ne
      lit aucune source -- il execute le pipeline de degat complet.

Porteur reel de l'ecart : `1088 HellfyreMissileRack` (`thousTerminator`), dont
`HellfyreMissileRackAbility$$ExecuteBehaviour` monte DEUX `AbilityDamage` sur `ActiveTarget()` via
`SortedAttackSeries` -- la cible du message recoit les deux des qu'elle a deja pris du Psychic ce
tour. Meme forme pour le FOLD de l'attaque normale et pour les N transferts d'`HazeOfCorruption`.

ASCII only. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

# Pose au MERGE de la PR #1155 : le garde `declencheur_guard` (#486-r15) refuse un fichier de test
# NEUF qui ne dit pas ce qui doit changer pour qu'il change de verdict, et il fait rougir la passe
# entiere (`37 passed`, `rc 1`). La proposition a ete DERIVEE, pas ecrite de memoire :
# `probe_486r15_declencheurs_tests.py --proposer <ce fichier>` rend « RIEN A DECLARER hors de la
# cascade » sur une fermeture de 747 modules.
#
# ⚠ CE QUE CETTE DECLARATION NE COUVRE PAS, ET ELLE LE DIT : `--proposer` ne voit que les IMPORTS.
# Les temoins de l'empreinte 457 sont NON MESURES ici, parce que cette mesure est SUSPENDUE par
# decision de l'utilisateur tant que les declencheurs trop larges ne sont pas assainis. Le risque
# qu'elle couvrirait est un `read_text("data/...")` qu'aucun import ne revele -- verifie a la main
# sur ce fichier : il n'ouvre AUCUN chemin (`open`, `read_text`, `Path`, `rglob`, `gameconfig` :
# zero occurrence). La declaration est donc juste pour la raison qu'elle enonce, pas par chance.
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": (
        "Fichier PUREMENT offline et PUREMENT structurel : il monte des behaviours en memoire et "
        "compte les evenements emis. Il ne lit ni le binaire, ni `data/symbols/**`, ni le "
        "gameconfig -- il n'ouvre aucun chemin. Sa fermeture d'imports tient donc entierement dans "
        "la cascade derivee de son foyer (`runner/operations/triggers/dispatch/attack.py`, "
        "`runner/abilities/behaviours/combat.py`, `runner/operations/damage_ops/**`), qu'il ne faut "
        "PAS re-declarer ici (#531). `chemins` vide n'est pas un aveu : c'est le resultat."
    ),
}

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from dataclasses import replace                                            # noqa: E402

from engine.dsl.base import DslContext                                     # noqa: E402
from engine.dsl.effects import ExecutionContext                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.abilities.behaviours.combat import SortedAttackSeries   # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,     # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation          # noqa: E402
from engine.runner.operations.triggers.dispatch import attack as A         # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.state import State                                      # noqa: E402


class _FeuilleMuette:
    """Feuille NUE : elle n'emet RIEN d'elle-meme (c'est ce que fait une
    `IdunBattleLogic.Entities.DSLBehaviors$$AbilityDamage` a `isOutsideAttack = 0`)."""
    is_outside_attack = True          # `SortedAttackSeries.__init__` doit le rabattre a False
    native_factory = "ability"
    profile = "HeavyRound"

    def __init__(self):
        self.appels = []

    def execute(self, entities, ectx):
        self.appels.append((entities.active_target or {}).get("id"))
        return None


class _FeuilleAttaque(_FeuilleMuette):
    """MEME feuille nue, mais de la famille ATTACK : c'est elle qui fait poser
    `currentAttack@+0x2c` par `AttackDamageOperation$$Execute`, donc qui ouvre le gate d'`On(10)`."""
    native_factory = "attack"


class _FeuilleQuiClot(_FeuilleMuette):
    """CONTRE-CAS : la feuille emet SA propre cloture -- c'est exactement le port d'AVANT #512-r4,
    ou `execute_ability_attack` appelait `after_hit_ability_attack` sans gate."""

    def execute(self, entities, ectx):
        super().execute(entities, ectx)
        A.finish_attack_triggers(ectx.state, (entities.caster or {}).get("id"),
                                 (entities.active_target or {}).get("id"), ranged=False)
        return None


class _FeuilleAttaqueQuiClot(_FeuilleAttaque):
    """CONTRE-CAS de `#512-r6` : la feuille emet SA propre paire de cloture, dans l'ordre ou le port
    la produisait -- `On(10)` etait emis par l'OPERATION, donc AVANT que le noeud n'emette `On(9)`."""

    def execute(self, entities, ectx):
        _FeuilleMuette.execute(self, entities, ectx)
        A.attack_damage_attack_triggers(ectx.state, (entities.caster or {}).get("id"),
                                        (entities.active_target or {}).get("id"), ranged=False)
        return None


def _etat_et_contexte():
    st = State()
    ids = []
    for vis in ("thousTerminator", "cible"):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        ids.append(e.id)
    caster = {"id": ids[0], "team": 1}
    cible = {"id": ids[1], "team": 2}
    ctx = DslContext(units=[caster, cible], caster=caster, target=cible)
    return st, ctx, caster, cible


class _SelFixe:
    """Selecteur qui rend TOUJOURS la meme unite -- la forme `ActiveTarget()` des deux volets de
    `1088`, une fois que les deux selecteurs de la serie ont resolu la MEME cible."""

    def __init__(self, u):
        self.u = u

    def select(self, entities):
        return [self.u]

    def evaluate(self, entities):
        return [self.u]


def _compter(monkeypatch):
    """Compte les `TriggerEvent` par type, en substituant le dispatcher DANS le module qui
    l'appelle (`dispatch/attack.py`) : `from .core import ...` est une liaison de FORME A, donc
    patcher `dispatch.core` NE MORDRAIT PAS."""
    vus = []
    monkeypatch.setattr(A, "evaluate_trigger_operation",
                        lambda state, ev: (vus.append(int(ev.event_id)), [])[1])
    return vus


def _n(vus, ev_type) -> int:
    return sum(1 for e in vus if e == int(ev_type))


def test_le_noeud_emet_UN_On9_pour_DEUX_feuilles_sur_la_MEME_cible(monkeypatch):
    """(1) `SortedAttackSeriesBehaviour$$Execute` : `if (unit != prevUnit)` -> UNE ouverture et UNE
    cloture par cible DISTINCTE, quel que soit le nombre de behaviours de cette cible."""
    st, ctx, caster, cible = _etat_et_contexte()
    f1, f2 = _FeuilleMuette(), _FeuilleMuette()
    noeud = SortedAttackSeries([(_SelFixe(cible), f1), (_SelFixe(cible), f2)], ability_type=1088)
    assert (f1.is_outside_attack, f2.is_outside_attack) == (False, False), \
        "le noeud doit rabattre ses feuilles a `isOutsideAttack = 0`"
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert f1.appels == [cible["id"]] and f2.appels == [cible["id"]], \
        "les DEUX feuilles doivent tourner sur la cible (sinon le test ne mesure rien)"
    assert _n(vus, EventTriggerType.Attack) == 1, vus
    assert _n(vus, EventTriggerType.PreAttack) == 1, vus


def test_CONTRE_CAS_des_feuilles_qui_cloturent_elles_memes_en_emettent_DEUX(monkeypatch):
    """La mesure ci-dessus n'est discriminante que si le regime d'AVANT #512-r4 rend un compte
    DIFFERENT. Il le rend : deux feuilles qui cloturent chacune -> DEUX `On(9)`."""
    st, ctx, _caster, cible = _etat_et_contexte()
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleQuiClot()),
                                (_SelFixe(cible), _FeuilleQuiClot())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _n(vus, EventTriggerType.Attack) == 3, (
        "2 clotures de feuille + 1 du noeud attendues dans le CONTRE-CAS : %r" % (vus,))


def test_deux_cibles_distinctes_donnent_DEUX_On9(monkeypatch):
    """Le pendant : ce qui est plafonne, c'est le nombre de feuilles PAR CIBLE, pas le nombre de
    cibles. Une serie a deux cibles distinctes ouvre et clot DEUX attaques."""
    st, ctx, _caster, cible = _etat_et_contexte()
    autre = {"id": cible["id"] + 100, "team": 2}
    ctx = replace(ctx, units=list(ctx.units) + [autre])
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleMuette()),
                                (_SelFixe(autre), _FeuilleMuette())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _n(vus, EventTriggerType.Attack) == 2, vus
    assert _n(vus, EventTriggerType.PreAttack) == 2, vus


def _seq(vus, *ev_types) -> list:
    """La SOUS-SEQUENCE des evenements demandes, dans l'ordre d'emission. C'est ce qui distingue un
    ORDRE d'un COMPTE -- et l'ordre est precisement ce que `#512-r6` corrigeait."""
    vises = {int(e) for e in ev_types}
    return [e for e in vus if e in vises]


# ==================================================================================================
# #512-r6 -- `On(AttackDamageAttack = 10)`, meme foyer natif : cardinalite, ORDRE et gate de famille
# ==================================================================================================

def test_le_noeud_emet_UN_On10_pour_DEUX_feuilles_ATTACK_sur_la_MEME_cible(monkeypatch):
    """(3) MEME `if (unit != prevUnit)` que pour `On(9)` : une cloture par cible DISTINCTE. Le gate
    `currentAttack@+0x2c` est ouvert des qu'UNE feuille de la cible est de la famille ATTACK."""
    st, ctx, _caster, cible = _etat_et_contexte()
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleAttaque()),
                                (_SelFixe(cible), _FeuilleAttaque())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _n(vus, EventTriggerType.AttackDamageAttack) == 1, vus
    assert _n(vus, EventTriggerType.Attack) == 1, vus


def test_l_ORDRE_sur_la_voie_NOEUD_est_9_PUIS_10(monkeypatch):
    """(4) LE SECOND VOLET DU RESIDU, et il ne se mesure pas sur des comptes. `FinishAttackOperation
    $$Execute` emet `9` puis, sous le gate, `10`."""
    st, ctx, _caster, cible = _etat_et_contexte()
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleAttaque())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _seq(vus, EventTriggerType.Attack, EventTriggerType.AttackDamageAttack) == \
        [int(EventTriggerType.Attack), int(EventTriggerType.AttackDamageAttack)], vus


def test_CONTRE_CAS_le_regime_d_avant_rend_DEUX_On10_ET_l_ordre_INVERSE(monkeypatch):
    """La mesure ci-dessus n'est discriminante que si le regime d'AVANT #512-r6 rend AUTRE CHOSE.
    Il rend les deux ecarts a la fois : DEUX `On(10)` (le port l'emettait par FEUILLE, depuis
    l'OPERATION) et l'ordre INVERSE (`10` avant `9`, le noeud cloturant apres ses feuilles)."""
    st, ctx, _caster, cible = _etat_et_contexte()
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleAttaqueQuiClot()),
                                (_SelFixe(cible), _FeuilleAttaqueQuiClot())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _n(vus, EventTriggerType.AttackDamageAttack) == 3, (
        "2 clotures de feuille + 1 du noeud attendues dans le CONTRE-CAS : %r" % (vus,))
    ordre = _seq(vus, EventTriggerType.Attack, EventTriggerType.AttackDamageAttack)
    assert ordre[0] == int(EventTriggerType.AttackDamageAttack), (
        "le CONTRE-CAS doit montrer l'ordre INVERSE (10 avant 9) : %r" % (ordre,))


def test_un_noeud_de_famille_ABILITY_emet_On9_mais_AUCUN_On10(monkeypatch):
    """(5) LE GATE. `IdunBattle.Operations.AbilityDamageOperation$$Execute` ne pose PAS
    `currentAttack@+0x2c` -- seule `AttackDamageOperation$$Execute` le fait. Un noeud dont toutes
    les feuilles sont de la famille ABILITY clot donc l'attaque SANS le second evenement."""
    st, ctx, _caster, cible = _etat_et_contexte()
    noeud = SortedAttackSeries([(_SelFixe(cible), _FeuilleMuette()),
                                (_SelFixe(cible), _FeuilleMuette())], ability_type=1088)
    vus = _compter(monkeypatch)
    noeud.execute(ctx, ExecutionContext(state=st, rng=st.rng))
    assert _n(vus, EventTriggerType.Attack) == 1, vus
    assert _n(vus, EventTriggerType.AttackDamageAttack) == 0, vus


def _etat_de_degat():
    """Un etat MINIMAL mais REEL : deux unites completes, un PRNG cale. C'est ce qu'il faut pour
    qu'`execute_ability_attack` aille jusqu'au bout (sans PRNG elle rend `None` en silence, et le
    test serait vert sur zero evenement)."""
    st = State()
    st.rng = IntBasedMersenneTwister(1234)
    ids = []
    for i in (0, 1):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id="ultraEliminatorSgt", alive=True))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(i * 2, 0))
        e.add_component(StatsComponent(
            ctx=UnitContext(entity_id=e.id, visual_id="ultraEliminatorSgt")))
        ids.append(e.id)
    return st, ids[0], ids[1]


def test_la_FEUILLE_ne_clot_NI_9_NI_10_quand_isOutsideAttack_est_faux(monkeypatch):
    """(6) LE GATE DE FEUILLE, MESURE SUR L'OPERATION REELLE -- aucun AST, aucune source lue.

    Une `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` NUE (`isOutsideAttack = 0`) ne pousse
    NI `StartAttack` NI `FinishAttack` : c'est le noeud parent qui ouvre et ferme. Les DEUX
    evenements de cloture doivent donc disparaitre ENSEMBLE, et les vecteurs de l'OPERATION
    (`On(8 = AttackHit)`, `On(0x42 = FinalDamage)`) doivent RESTER dans les deux regimes -- sinon le
    gate aurait eteint autre chose que la cloture."""
    st, att, tgt = _etat_de_degat()
    resultats = {}
    for outside in (True, False):
        vus = _compter(monkeypatch)
        r = AttackDamageOperation.execute_ability_attack(
            st, att, tgt, 10, 10, 0, 1, damage_profile="Bolter", is_melee=True,
            is_attack_damage_op=True, is_outside_attack=outside)
        assert (r or {}).get("total"), (
            "l'operation doit vraiment s'executer, sinon la mesure est VIDE : %r" % (r,))
        resultats[outside] = list(vus)
    assert _n(resultats[True], EventTriggerType.Attack) == 1, resultats[True]
    assert _n(resultats[True], EventTriggerType.AttackDamageAttack) == 1, resultats[True]
    assert _n(resultats[False], EventTriggerType.Attack) == 0, resultats[False]
    assert _n(resultats[False], EventTriggerType.AttackDamageAttack) == 0, resultats[False]
    # TEMOIN : les vecteurs de l'OPERATION survivent des deux cotes.
    for regime, vus in resultats.items():
        assert _n(vus, EventTriggerType.AttackHit) == 1, (regime, vus)
        assert _n(vus, EventTriggerType.FinalDamage) == 1, (regime, vus)


def test_la_facade_after_hit_gate_On9_mais_JAMAIS_On8_ni_On_block(monkeypatch):
    """(2) Les TROIS evenements de `after_hit_ability_attack` n'ont pas la meme granularite native :
    `On(0x3c)` et `On(8)` viennent d'`ADamageOperation$$EvaluateAfterHitTriggers` (par COUP, donc
    portes par l'OPERATION) et doivent partir dans les DEUX regimes ; seul `On(9)` est gate."""
    st, _ctx, caster, cible = _etat_et_contexte()
    for regime, attendu in ((True, 1), (False, 0)):
        vus = _compter(monkeypatch)
        A.after_hit_ability_attack(st, caster["id"], cible["id"], is_crit=False,
                                   did_block=True, emit_finish_attack=regime)
        assert _n(vus, EventTriggerType.Attack) == attendu, (regime, vus)
        assert _n(vus, EventTriggerType.AttackHit) == 1, (regime, vus)
        assert _n(vus, EventTriggerType.UnitBlocked) == 1, (regime, vus)
