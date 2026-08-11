"""#520 -- le PIPELINE de `IdunBattle.Operations.HealUnitOperation$$Execute`, etage par etage.

Cliquet OFFLINE (aucun runner) du foyer que #520 a complete. Il garde ce qu'aucun test live ne
peut garder tout seul : que chaque ETAGE du natif existe cote port, et qu'il est branche DANS LE BON
ORDRE. Un test qui ne verifierait que « le soin rend le bon nombre » resterait vert sur un port ou le
gate et les deux caps auraient disparu -- c'est exactement l'etat dans lequel ce module a vecu.

Les etages, dans l'ordre du decompile :

    HealUnitOperation$$Execute
      0. gate  AttackQuery$$EntityCanBeHealed        -> sortie SANS mutation
      1. cursed EntityExtensions.HasEffect(Cursed)   -> montant force a 0, FillUp appele QUAND MEME
      2. DamagePrediction$$PredictHeal
           2a. bonus des effets       (INERTE sur ce build : 0 implementeur)
           2b. cap GROUPE  scope==1   (GetGroupUnitHealLimit)
           2c. cap BOSS               (is_boss == False cote substrat)
           2d. MaxFillUp / MaxReduce  (branche negative)
      3. FillUpStatComponent$$FillUp                 -> LA mutation

ASCII only (console cp1252).
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LES DEUX OPERATIONS JUMELLES et leur foyer de substrat partage -- c'est ce que ce
        # fichier compare etage par etage, et une divergence de forme entre elles est justement
        # ce qu'il doit rougir.
        "scripts/python/engine/runner/operations/heal.py",
        "scripts/python/engine/runner/operations/repair.py",
        "scripts/python/engine/runner/operations/fill_up_prediction.py",
        # LE GATE : le mirror que l'Operation appelle en tete. Un assouplissement la-bas rendrait
        # l'etage 1 de ce fichier vert a tort.
        "scripts/python/engine/runner/abilities/attack_query.py",
        # LA MUTATION et son accumulateur (`fill_up` / `max_reduce` / `reduce` vivent ensemble).
        "scripts/python/engine/runner/components.py",
        # LES DEUX FEUILLES DSL, dont ce fichier verifie les DEFAUTS d'options.
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        # LES CALL-SITES `ForRegenerate` PORTES -- l'etage 4 les lit par AST, donc tout
        # deplacement de leur `Heal(...)` change son verdict.
        "scripts/python/engine/runner/abilities/bloodangels.py",
        "scripts/python/engine/runner/operations/triggers/loki/time_flux.py",
        # Le cap de groupe, lu par `predict_heal` comme par `predict_repair`.
        "scripts/python/engine/services/trait_damage_limits.py",
        # L'etat minimal que les montages offline construisent.
        "scripts/python/engine/runner/state.py",
        # ⚠ ELARGI (#486-r15) : la liste feuille-a-feuille ci-dessus etait TROP ETROITE de
        # **81 chemins** -- mesure par le cliquet, pas estimee. Importer `heal.py` tire l'`__init__`
        # du paquet `operations`, donc le registre de triggers, le vocabulaire DSL et le
        # pathfinding : une liste choisie ne peut pas montrer le module qu'elle a oublie. Les
        # chemins nommes plus haut restent ECRITS pour la relecture humaine -- ils disent OU
        # regarder ; les deux globs disent ce qui FAIT VRAIMENT changer d'avis.
        # Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
        # ne voit PAS `scripts/python/board.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les deux Operations jumelles, leur gate, leur mutation, leurs feuilles DSL et les "
              "deux call-sites `ForRegenerate` lus par AST. `build: True` parce que la ventilation "
              "des familles `CreateEffect*` -- qui etablit que l'etage BONUS de `PredictHeal` est "
              "INERTE -- est une propriete du BUILD : un `CreateEffectHealBonus` apparaissant a une "
              "mise a jour rendrait le no-op porte FAUX (residu #520-r2).",
}

import ast
import io
import pathlib

import pytest

from engine.runner.state import State
from engine.runner.components import HealthComponent, UnitComponent, UnitFlagsComponent
from engine.runner.operations.heal import HealUnitOperation, predict_heal
from engine.runner.operations.repair import RepairUnitOperation, predict_repair
from engine.runner.abilities.behaviours.stats import Heal, Repair

HP_MAX = 4000


def _unite(hp: int, hp_max: int = HP_MAX, minimal=None, members=None):
    st = State()
    e = st.add_entity()
    e.add_component(HealthComponent(hp, hp_max, minimal_health=minimal))
    e.add_component(UnitComponent("cible", True))
    e.add_component(UnitFlagsComponent())
    uid = next(iter(st.entities))
    return st, uid


# --------------------------------------------------------------------------------------------
# 1. Le GATE est EN TETE -- et il sort SANS MUTATION
# --------------------------------------------------------------------------------------------

def test_le_gate_sort_sans_toucher_aux_PV():
    """`if (!attackQuery.<slot 0x11>(...)) return {};` -- le natif rend un `OperationResult` VIDE.

    Discriminant choisi : une cible a PLEINS PV. `AttackQuery$$IsDamagedUnit` est faux, les trois
    autres disjuncts le sont aussi (aucun effet negatif lisible, aucun flag
    `CanHealFullHealthUnits`), donc le gate REFUSE -- et il refuse AVANT `FillUp`.

    ⚠ CE N'EST PAS LE MEME CHEMIN QUE `filled == 0`, et c'est tout l'interet du test : `FillUp`
    PURGE `over_reduce` en queue, inconditionnellement. Un port qui laisserait passer le gate et se
    contenterait du `Min(amount, max - cur)` rendrait le meme 0 -- et aurait remis l'accumulateur a
    zero. L'etat de `over_reduce` est donc le SEUL observable qui separe « refuse » de « soigne 0 »."""
    st, uid = _unite(HP_MAX)
    hc = st.get_entity(uid).get_component(HealthComponent)
    hc.over_reduce = 777
    assert HealUnitOperation.execute(st, uid, uid, 500) == 0
    assert hc.hp == HP_MAX
    assert hc.over_reduce == 777, "gate en TETE : aucun FillUp, donc aucune purge"


def test_sans_gate_le_meme_appel_muterait():
    """CONTRE-EPREUVE du test precedent : la cible blessee, elle, passe le gate et mute.

    Sans ce temoin non-nul, le test ci-dessus serait vert sur un port qui refuserait TOUT."""
    st, uid = _unite(HP_MAX - 300)
    hc = st.get_entity(uid).get_component(HealthComponent)
    hc.over_reduce = 777
    assert HealUnitOperation.execute(st, uid, uid, 500) == 300
    assert hc.hp == HP_MAX
    assert hc.over_reduce == 0, "FillUp atteint -> purge"


# --------------------------------------------------------------------------------------------
# 2. `PredictHeal` -- les quatre etages
# --------------------------------------------------------------------------------------------

def test_predict_heal_MaxFillUp_cape_au_manquant():
    """(2d) `MaxFillUp` = `Min(Max(0, predicted), CurrentMaximumValue - Current)`."""
    st, uid = _unite(HP_MAX - 100)
    assert predict_heal(st, None, uid, 40) == 40          # sous le manquant -> intact
    assert predict_heal(st, None, uid, 9999) == 100       # au-dessus -> cape au manquant
    assert predict_heal(st, None, uid, 0) == 0


def test_predict_heal_branche_NEGATIVE_est_MaxReduce():
    """(2d bis) `if (predicted < 0) return -MaxReduce(fillUp, -predicted, false);`

    `MaxReduce` = `Min(amount, Current)`, puis borne par le plancher `Minimum` quand il est pose."""
    st, uid = _unite(1000)
    assert predict_heal(st, None, uid, -10) == -10
    assert predict_heal(st, None, uid, -5000) == -1000, "Min(5000, current=1000)"
    # plancher `Minimum` : on ne peut pas descendre sous `Min(current, minimal_health)`.
    st2, uid2 = _unite(1000, minimal=600)
    assert predict_heal(st2, None, uid2, -5000) == -400, "current - floor = 1000 - 600"


def test_predict_heal_cap_de_GROUPE_est_GATE_par_scope():
    """(2b) `if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))`.

    Le cap ne doit JAMAIS s'appliquer sous `scope == 0` -- c'est ce que les deux call-sites
    `ForRegenerate` portes (SavageEchoes, TimeFlux) mettent en jeu. Sur une unite MONO-MEMBRE (le
    substrat par defaut), `GetGroupUnitHealLimit` rend `int.MaxValue`, donc les deux scopes
    coincident : le test exige donc les DEUX, et le regime mono-membre est declare comme tel."""
    st, uid = _unite(HP_MAX - 500)
    a = predict_heal(st, None, uid, 400, scope=0)
    b = predict_heal(st, None, uid, 400, scope=1)
    assert a == 400
    assert b == 400, ("regime MONO-MEMBRE : les deux scopes coincident par construction "
                      "(GetGroupUnitHealLimit -> int.MaxValue). Ce n'est pas une preuve que le cap "
                      "marche, c'est une preuve qu'il ne MORD PAS la ou il ne doit pas.")


# --------------------------------------------------------------------------------------------
# 3. HEAL et REPAIR sont des JUMEAUX -- meme signature, meme forme
# --------------------------------------------------------------------------------------------

#: Le SEUL parametre sur lequel les deux `Predict*` natifs DIVERGENT (#908, mesure ci-dessous).
_PREDICT_ASYMETRIE = "ability_or_effect"


def test_les_deux_Operations_ont_la_MEME_signature():
    """Le natif a deux Operations symetriques (`<slot 0x57>` / `<slot 0x58>` de
    l'`OperationProcessor`), deux `BehaviourOptions` de meme forme.

    Le port doit l'etre aussi : c'est ce qui a manque pendant toute la vie de `heal.py`, et c'est
    ce qui rendait l'asymetrie INVISIBLE a la relecture -- les deux modules ne se comparaient pas.

    ⚠ LES `Execute` SONT JUMEAUX, LES `Predict*` NE LE SONT PAS -- et cette ligne-ci disait le
    contraire (#908). Ce qui est LU au decompile de `rnca9r7q6c` :

      * `IdunBattle.Operations.HealUnitOperation$$Execute` et `IdunBattle.Operations.
        RepairUnitOperation$$Execute` portent TOUS DEUX un 7e argument `abilityOrEffect`, passe sur
        la PILE (`in_stack_00000040` dans les deux decompiles) -- donc la symetrie des `execute`
        est REELLE, et le port la tient ;
      * `IdunBattle.Core.Services.DamagePrediction$$PredictHeal(this, caster, casterTile, target,
        amount, scope)` **n'a PAS** ce parametre : il batit son `AbilityEntities` INLINE, sans champ
        de cause. `PredictRepair`, lui, le recoit et le relaie a
        `IdunBattle.Core.Services.RepairCalculations$$CalculateRepairModifierForPrediction`
        (5e argument, `source`) -- c'est ce champ que lit le gate `TriggeringAbilityIs` du seul
        descripteur `RepairBonus` qui en porte un (`NetherRealmCasket_LivingMetalBonusEffect`).

    Le test ne s'affaiblit donc pas : il exige la symetrie PARTOUT SAUF sur ce parametre, et il
    ASSERTIONNE l'asymetrie elle-meme (sans quoi un retrait silencieux du canal passerait vert)."""
    import inspect
    sh = inspect.signature(HealUnitOperation.execute)
    sr = inspect.signature(RepairUnitOperation.execute)
    assert list(sh.parameters) == list(sr.parameters), (
        "HealUnitOperation.execute %s != RepairUnitOperation.execute %s" % (sh, sr))
    ph = list(inspect.signature(predict_heal).parameters)
    pr = list(inspect.signature(predict_repair).parameters)
    assert [p for p in pr if p != _PREDICT_ASYMETRIE] == ph, (
        "predict_heal %s != predict_repair %s (hors '%s')" % (ph, pr, _PREDICT_ASYMETRIE))
    # l'ASYMETRIE elle-meme, dans les DEUX sens -- c'est ce que le decompile impose.
    assert _PREDICT_ASYMETRIE in pr, (
        "PredictRepair recoit `source` (5e arg de CalculateRepairModifierForPrediction) : "
        "predict_repair doit le porter, sinon le gate TriggeringAbilityIs est INATTEIGNABLE")
    assert _PREDICT_ASYMETRIE not in ph, (
        "PredictHeal ne recoit AUCUNE cause au decompile : lui en donner une serait une invention")
    # les feuilles DSL portent toutes deux leurs options
    for cls in (Heal, Repair):
        assert "scope" in cls.__slots__ and "remove_effects" in cls.__slots__, cls.__name__


def test_le_defaut_de_remove_effects_DIFFERE_entre_les_deux_feuilles_et_c_est_LU():
    """`HealBehaviourOptions$$ForHeal` = `(scope 0, removeEffects 1)` ;
    `RepairBehaviourOptions$$ForRepair` = `(scope 0, removeEffects 1)`.

    Les deux feuilles doivent donc defaulter a `remove_effects=True`. Ce test existe parce que le
    defaut est le SEUL endroit ou une faute de transcription des fabriques serait silencieuse :
    `remove_effects` n'a aucun observable d'etat PV cote port (la purge n'est pas modelisee), donc
    aucun test de montant ne le verrait."""
    import inspect
    for cls in (Heal, Repair):
        d = inspect.signature(cls.__init__).parameters
        assert d["scope"].default == 0, cls.__name__
        assert d["remove_effects"].default is True, cls.__name__


# --------------------------------------------------------------------------------------------
# 4. Les DEUX call-sites `ForRegenerate` portes DECLARENT leur scope
# --------------------------------------------------------------------------------------------

RACINE = pathlib.Path(__file__).resolve().parents[2] / "engine"

# `HealBehaviourOptions$$ForRegenerate` -- les SIX call-sites natifs (xrefs relues sur `rnca9r7q6c`).
# Les DEUX portes, et le fichier ou vit leur feuille `Heal(...)`.
FOR_REGENERATE_PORTES = {
    "runner/abilities/bloodangels.py":
        "IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour",
    "runner/operations/triggers/loki/time_flux.py":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour",
}


def _heal_calls(rel: str):
    """Les appels `Heal(...)` d'un module, par AST -- une mention en docstring ne compte pas."""
    src = io.open(RACINE / rel, encoding="utf-8").read()
    return [n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Heal"]


@pytest.mark.parametrize("rel,symbole", sorted(FOR_REGENERATE_PORTES.items()))
def test_les_call_sites_ForRegenerate_declarent_scope_1(rel, symbole):
    """Un call-site dont le natif passe `ForRegenerate` DOIT ecrire `scope=1`.

    Sans ce cliquet, l'omission est invisible : sur un porteur MONO-MEMBRE (les deux le sont), le
    cap de groupe ne mord pas, donc aucun test de montant ne rougirait. C'est exactement pourquoi
    l'omission a survecu -- et pourquoi `bloodangels.py` portait DEJA le mot `ForRegenerate` dans un
    commentaire pendant que le port tournait en `scope 0`."""
    appels = _heal_calls(rel)
    assert appels, "aucun appel `Heal(...)` dans %s -- le call-site a bouge ?" % rel
    for appel in appels:
        kw = {k.arg: k.value for k in appel.keywords}
        assert "scope" in kw, ("%s : `Heal(...)` sans `scope` alors que %s passe ForRegenerate"
                               % (rel, symbole))
        assert isinstance(kw["scope"], ast.Constant) and kw["scope"].value == 1, \
            "%s : scope attendu 1 (ForRegenerate), lu %r" % (rel, ast.dump(kw["scope"]))
        assert isinstance(kw.get("remove_effects"), ast.Constant) and \
            kw["remove_effects"].value is False, \
            "%s : ForRegenerate ecrit removeEffects = 0" % rel
