"""#512-r4 -- CARDINALITE d'`On(Attack = 9)` : le natif l'emet PAR CIBLE au niveau du NOEUD, le port
l'emettait PAR FEUILLE au niveau de l'OPERATION.

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

CE QUE CE FICHIER GARDE, ET IL LE FAIT PAR MESURE, PAS PAR LECTURE DE SOURCE :
  (1) un noeud `SortedAttackSeries` portant DEUX feuilles sur la MEME cible emet **UN** `On(9)` --
      et le CONTRE-CAS integre (des feuilles qui emettent elles-memes, c'est-a-dire le port
      d'avant #512-r4) en produit **DEUX**, donc la mesure est discriminante ;
  (2) la facade after-hit d'ability n'emet `On(9)` que si `emit_finish_attack` est vrai, et ses deux
      AUTRES vecteurs (`On(0x3c = UnitBlocked)`, `On(8 = AttackHit)`) partent dans les DEUX regimes
      -- ils viennent d'`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`, donc de
      l'OPERATION, et les confondre aurait eteint le cluster on-block avec la cloture.

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
from engine.runner.abilities.behaviours.combat import SortedAttackSeries   # noqa: E402
from engine.runner.components import UnitComponent                         # noqa: E402
from engine.runner.operations.triggers.dispatch import attack as A         # noqa: E402
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


class _FeuilleQuiClot(_FeuilleMuette):
    """CONTRE-CAS : la feuille emet SA propre cloture -- c'est exactement le port d'AVANT #512-r4,
    ou `execute_ability_attack` appelait `after_hit_ability_attack` sans gate."""

    def execute(self, entities, ectx):
        super().execute(entities, ectx)
        A.finish_attack_triggers(ectx.state, (entities.caster or {}).get("id"),
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
