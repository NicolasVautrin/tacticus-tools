"""#1088 -- `IEffect` slot 4 `get_RemoveOnDeathStep` : le DEFAUT et les QUATRE surcharges.

## Pourquoi ce fichier existe alors que `test_389r2_...` couvre deja `remove_effects_operation`

Parce que ce test-la est AVEUGLE au defaut, et c'est MESURE, pas suppose : le 2026-08-15, en
remettant `BaseEffect.remove_on_kill_step` a l'ancienne valeur FAUSSE (`PreUnitRemove`), ses
**10 tests passent toujours**. Il pose ses steps explicitement sur des stubs, donc il ne peut pas
voir un defaut faux -- et le defaut etait faux depuis #389-r2 sans que rien ne rougisse.

Ce fichier garde donc ce que l'autre ne voit pas, sur trois etages :

  1. **LA VALEUR** du defaut et des surcharges, figee contre ce qui a ete DERIVE du binaire ;
  2. **LA CONSEQUENCE** observable : quel effet part a quel step, et ou tombent les deux events
     `On(UnitDeath)` / `On(UnitDefeated)` de `KillUnitOperation$$Execute` ;
  3. **LA CONCORDANCE** avec l'entree versionnee `metadata/remove_on_death_step.tsv`, quand le
     build est la.

L'etage 1 et l'etage 2 ne dependent PAS du jeu installe : ils tournent partout, donc ce fichier ne
peut jamais rendre `passed == 0 and skipped > 0` (le regime que #455 fait rougir).

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects.base import BaseEffect                        # noqa: E402
from engine.entities.effects.loki.possession import (                      # noqa: E402
    AttemptedPossessionPossessedEffect)
from engine.entities.effects.loki.status import TauntedEffect              # noqa: E402
from engine.entities.kill_unit_step import KillUnitStep                    # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.runner.operations.remove_effects import (                      # noqa: E402
    remove_effects_operation)


# ------------------------------------------------------------------ etage 1 : LA VALEUR

def test_le_defaut_de_base_effect_est_after_unit_remove():
    """`IdunBattle.Entities.Effects.BaseEffect$$get_RemoveOnDeathStep` -> `b8 01 00 00 00 c3`.

    C'etait une HYPOTHESE NOMMEE (#389-r2) posee a `PreUnitRemove`, et elle etait FAUSSE. La valeur
    est desormais LUE : declaration dans le `global-metadata.dat`, corps dans le bloc
    `methodPointers`, 66 controles d'alignement locaux, sur les 465 classes de la fermeture
    transitive -- `probe_1088_remove_on_death_step.py`.

    ⚠ CE TEST EST LE SEUL A MORDRE SUR CETTE LIGNE. Contre-epreuve jouee : remettre `PreUnitRemove`
    laisse `test_389r2_kill_unit_remove_effects_offline.py` INTEGRALEMENT VERT."""
    assert BaseEffect.remove_on_kill_step == KillUnitStep.AfterUnitRemove


def test_les_quatre_surcharges_portees():
    """Les classes qui DECLARENT le getter, avec la valeur lue aux octets.

    Le build en compte QUATRE hors base ; DEUX ont une classe Python (les deux ci-dessous), les
    deux autres n'ont aucun mirror porte -- residu nomme dans le rapport de tranche, pas ici.

    ⚠ `AttemptedPossessionPossessedEffect` vaut `PreUnitRemove`, c'est-a-dire exactement l'ANCIEN
    defaut faux. Si sa ligne explicite disparaissait, la classe se remettrait silencieusement a
    heriter d'`AfterUnitRemove` -- un decalage d'un step qu'aucune autre garde ne verrait."""
    assert TauntedEffect.remove_on_kill_step == KillUnitStep.AfterDeathTrigger
    assert (AttemptedPossessionPossessedEffect.remove_on_kill_step
            == KillUnitStep.PreUnitRemove)
    # NON-DEGENERESCENCE : les trois valeurs figees doivent etre DISTINCTES, sinon l'accord serait
    # compatible avec un port qui rendrait la meme constante partout.
    trois = {int(BaseEffect.remove_on_kill_step),
             int(TauntedEffect.remove_on_kill_step),
             int(AttemptedPossessionPossessedEffect.remove_on_kill_step)}
    assert trois == {0, 1, 2}, trois


# ------------------------------------------------------------------ etage 2 : LA CONSEQUENCE

COLS, ROWS, PORTEUR = 5, 5, 20


def _state_reel():
    """Un `State` COMPLET -- `remove_effects_operation` ne se contente pas de collecter, elle
    RETIRE (revert des modifications, deux events), donc elle a besoin des canaux de `State`. Le
    stub des tests de collecte ci-dessus ne suffit pas ici, et c'est voulu : ce test-la mesure le
    chemin entier."""
    import hexgeo                     # module de `scripts/python`, pas du paquet `engine`
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": PORTEUR, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 2, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": PORTEUR, "hp": 1000, "hpMax": 1000}]}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:
        st.effects = EffectsState()
    return st

class _Eff:
    """Stub minimal d'effet -- il ne DECLARE PAS `remove_on_kill_step`, exprès.

    C'est le regime du `getattr(eff, "remove_on_kill_step", <defaut>)` de
    `remove_effects_operation` : un objet-effet qui n'a pas l'attribut doit se comporter comme
    `BaseEffect`, pas comme `PreUnitRemove`."""

    def __init__(self, effect_type: int) -> None:
        self.effect_type = int(effect_type)
        self.name = "stub%d" % effect_type
        self.consumed = False
        self.target = 1


def _steps_de_retrait(fabrique) -> list:
    """A quels `KillUnitStep` l'effet fabrique par `fabrique()` est-il retire ?

    On rejoue les TROIS steps sur un etat NEUF a chaque fois : c'est le seul moyen de voir a quel
    step l'effet PARTIRAIT, sans que le premier retrait masque les suivants.

    ⚠ IL APPELLE LE VRAI `remove_effects_operation`, ET C'EST LOAD-BEARING. Une premiere version
    de ce helper RE-IMPLEMENTAIT le filtre (`int(getattr(e, "remove_on_kill_step", <defaut>))`)
    pour s'epargner le montage d'un `State` complet. Elle rendait les bons chiffres et elle etait
    INERTE : la mutation du defaut de secours DANS LE CODE DE PRODUCTION laissait les 7 tests
    verts, parce que le test lisait sa propre copie du predicat. Un helper qui re-ecrit ce qu'il
    mesure ne mesure rien."""
    vus = []
    for step in (KillUnitStep.PreUnitRemove, KillUnitStep.AfterUnitRemove,
                 KillUnitStep.AfterDeathTrigger):
        st = _state_reel()
        st.effects.add_effect(PORTEUR, fabrique())
        if remove_effects_operation(st, PORTEUR, step=step):
            vus.append(int(step))
    return vus


def test_un_effet_ordinaire_part_au_step_1_pas_au_step_0():
    """La consequence directe du defaut. Un `BaseEffect` nu doit etre retire par le DEUXIEME appel
    de `KillUnitOperation$$RemoveEffects`, pas le premier."""
    assert _steps_de_retrait(
        lambda: BaseEffect(name="ordinaire", effect_type=1, target=1)) == [
        int(KillUnitStep.AfterUnitRemove)]


def _steps_de_collecte(monkeypatch, eff) -> list:
    """Idem, mais en SUBSTITUANT l'etage AVAL (`remove_effect_instance`).

    Pourquoi : le regime << objet-effet sans l'attribut >> est inatteignable avec une sous-classe
    de `BaseEffect` (l'attribut de classe est toujours trouve par `getattr`), donc il faut un objet
    ETRANGER a la hierarchie -- et un tel objet ne survit pas au RETRAIT reel, qui lit une dizaine
    d'autres champs. On substitue donc ce que l'on ne mesure PAS (le retrait) et on laisse intact ce
    que l'on mesure (la clause de filtrage par step, dans `remove_effects_operation` elle-meme).

    La substitution porte sur le MODULE (`setattr(mod, "remove_effect_instance", ...)`) : c'est la
    forme qui MORD, la fonction y etant resolue par le `globals()` de son module a chaque appel."""
    import engine.runner.operations.remove_effects as mod
    monkeypatch.setattr(mod, "remove_effect_instance", lambda st, uid, e: True)
    vus = []
    for step in (KillUnitStep.PreUnitRemove, KillUnitStep.AfterUnitRemove,
                 KillUnitStep.AfterDeathTrigger):
        st = _state_reel()
        st.effects.add_effect(PORTEUR, eff)
        if mod.remove_effects_operation(st, PORTEUR, step=step):
            vus.append(int(step))
    return vus


def test_un_stub_sans_attribut_suit_le_defaut_natif(monkeypatch):
    """LE DEFAUT DE SECOURS DU `getattr`, qui est un SECOND site et qu'aucune surcharge de classe ne
    corrige. Il valait `0` : un effet hydrate par un chemin qui ne passe pas par `BaseEffect` etait
    donc retire au tout premier step, meme apres correction du foyer."""
    assert _steps_de_collecte(monkeypatch, _Eff(2)) == [int(KillUnitStep.AfterUnitRemove)]


def test_taunted_survit_aux_deux_premiers_steps():
    """C'est LA propriete qui rend possible la face SUCCESS de #911-r1.

    `KillUnitOperation$$Execute` ordonne : step 0 -> step 1 -> `On(UnitDeath)` -> `On(UnitDefeated)`
    -> step 2. Un effet a `AfterDeathTrigger` est donc encore PORTE quand les deux events partent,
    et c'est ce que le natif exige pour que `DaemonicPatrons` se re-arme sur un kill de cible
    TAUNTEE (`HasEffect(Target, 27)` vrai a `On(UnitDefeated)`)."""
    vus = _steps_de_retrait(lambda: TauntedEffect(name="Taunted_OnlySpecificTargets",
                                                  effect_type=27, target=1))
    assert vus == [int(KillUnitStep.AfterDeathTrigger)]
    assert int(KillUnitStep.AfterDeathTrigger) > int(KillUnitStep.AfterUnitRemove), \
        "l'ordre des steps est ce qui place le taunt APRES les events de mort"



def test_le_regime_sans_step_retire_tout_quel_que_soit_le_slot():
    """`options.step.HasValue` est FAUX -> AUCUN filtre. C'est une clause du natif que le resume
    << compare le slot 4 a options.step >> ne montre pas, et l'oublier ferait survivre le taunt a
    un retrait qui doit tout emporter (ex. le despawn).

    ⚠ TEMOIN NON DEGENERE : les deux effets poses ont des steps DIFFERENTS (1 et 2). Si les deux
    partageaient le meme, le test passerait aussi avec un filtre reste arme."""
    st = _state_reel()
    ordinaire = BaseEffect(name="ordinaire", effect_type=1, target=PORTEUR)
    taunt = TauntedEffect(name="Taunted_OnlySpecificTargets", effect_type=27, target=PORTEUR)
    assert int(ordinaire.remove_on_kill_step) != int(taunt.remove_on_kill_step)
    st.effects.add_effect(PORTEUR, ordinaire)
    st.effects.add_effect(PORTEUR, taunt)
    retires = remove_effects_operation(st, PORTEUR, step=None)
    assert sorted(int(x) for x in retires) == [1, 27], retires


# ------------------------------------------------------------------ etage 3 : LA CONCORDANCE

def test_le_port_concorde_avec_l_entree_versionnee():
    """Le port dit-il la meme chose que ce qui a ete DERIVE du binaire ?

    Le TSV est l'artefact de `probe_1088 --regenerer`. S'il manque (depot sans le build courant),
    on SKIPPE en le disant -- les deux etages precedents, eux, ont deja tourne, donc ce fichier ne
    tombe jamais dans le regime `passed == 0 and skipped > 0`."""
    sys.path.insert(0, str(PYDIR))
    import probe_1088_remove_on_death_step as P1088                        # noqa: E402
    try:
        table = P1088.lire_tsv()
    except SystemExit as exc:
        pytest.skip("entree versionnee absente pour le build courant : %s" % exc)
    assert table, "l'entree versionnee est VIDE -- un accord sur rien ne prouve rien"

    attendu = {
        "IdunBattle.Entities.Effects.BaseEffect": BaseEffect,
        "IdunBattle.Entities.Effects.TauntedEffect": TauntedEffect,
        "IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect":
            AttemptedPossessionPossessedEffect,
    }
    vus = 0
    for natif, cls in attendu.items():
        assert natif in table, (
            "%s ne DECLARE plus le getter dans l'entree versionnee -- le port porte une surcharge "
            "que le binaire n'a plus" % natif)
        assert int(cls.remove_on_kill_step) == table[natif], (
            "%s : port=%d, binaire=%d" % (natif, int(cls.remove_on_kill_step), table[natif]))
        vus += 1
    assert vus == 3, vus
    # Les DEUX classes natives qui declarent SANS mirror Python porte : on garde leur existence,
    # pour qu'un port futur ne les redecouvre pas -- et pour que leur DISPARITION se voie.
    for natif in ("IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect",
                  "IdunBattleLogic.Entities.Abilities.Active.Loki."
                  "RammingSpeed_ExtraExplodeEffect"):
        assert natif in table, natif
        assert table[natif] == int(KillUnitStep.AfterDeathTrigger), (natif, table[natif])
