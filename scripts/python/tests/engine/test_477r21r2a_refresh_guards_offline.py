"""#477-r21-r2 volet A -- les quatre gardes de `RefreshEffectsOperation`, FIGEES.

Le probe live (`probe_477r21r2a_refresh_guards.py`) confronte ce que les gardes IMPOSENT au flux.
Ce cliquet garde ce que le flux ne peut PAS montrer :

  * `ShouldBeActive` -- le flux porte les CONSEQUENCES d'un verdict, jamais le verdict. Ses
    quatre branches (`ForceActivate`, `ForceDeactivate`, hors domaine, `Automatically`) et ses
    deux regimes (flag courant vs `CreateActiveCondition`) ne sont figes que par ici ;
  * le TRI d'`EffectComponent$$AddTargetId` -- mesure du probe : (I4) n'est exercee que par UN
    sous-arbre sur 289 (0 sur `MC1_67`), parce que les cibles se perdent presque toujours une par
    une. La contre-epreuve `cibles_courantes_inversees` y est meme NON EXERCEE sur un board ;
  * le chemin `DeactivateEffect` (`UpdateEffectTargets` avec `desiredTargets` VIDE) ;
  * `ShouldRefreshForTrigger` sur les 9 declencheurs, dont la SEULE sortie fausse.

ASCII only (console Windows cp1252)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PY = Path(__file__).resolve().parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.runner.operations.refresh_effects import (  # noqa: E402
    ACTION_ACTIVATE, ACTION_APPLY, ACTION_DEACTIVATE, ACTION_LOSE, ACTION_RECEIVE, ACTION_REVERT,
    EffectComponentView, RefreshEffectTrigger, RefreshEffectType, get_targets_to_add,
    get_targets_to_remove, should_be_active, should_refresh_for_trigger, update_effect_targets)
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.streams.step_type import StepType  # noqa: E402
from engine.streams.tag_key import TagKey  # noqa: E402


class _Effet:
    """Le minimum qu'`IEffect` expose aux gardes : `is_active` (slot `<+0xb>`) et
    `REFRESH_TRIGGERS` (slot `<+0x5c8>`, `GetRefreshTriggers`)."""

    def __init__(self, actif=True, triggers=None):
        self._actif = actif
        if triggers is not None:
            self.REFRESH_TRIGGERS = tuple(triggers)

    def is_active(self, unit_state=None) -> bool:
        return self._actif


# --------------------------------------------------------------- `BaseEffect$$ShouldRefreshForTrigger`
def test_should_refresh_for_trigger_defaut_est_vrai_partout():
    """`GetRefreshTriggers()` NULL = rafraichir sur TOUT. C'est le defaut natif (aucun corps sur
    `BaseEffect`), pas une degradation du port -- et c'est ce qui rend le cablage du declencheur
    EXACT et INERTE aujourd'hui."""
    e = _Effet()
    assert not hasattr(e, "REFRESH_TRIGGERS")
    for t in RefreshEffectTrigger:
        assert should_refresh_for_trigger(e, t) is True, t.name


def test_should_refresh_for_trigger_les_trois_premiers_court_circuitent():
    """`Forced` / `Simulation` / `Custom` sortent AVANT toute lecture : meme un tableau qui ne
    les contient pas rend `true` (`if (t != 0 && (uint)(t - 1) > 1)`)."""
    e = _Effet(triggers=(RefreshEffectTrigger.TurnChanged,))
    for t in (RefreshEffectTrigger.Forced, RefreshEffectTrigger.Simulation,
              RefreshEffectTrigger.Custom):
        assert should_refresh_for_trigger(e, t) is True, t.name


def test_should_refresh_for_trigger_seule_sortie_fausse():
    """La SEULE facon de rendre `false` : un tableau NON VIDE qui ne contient pas le declencheur.
    Un tableau VIDE rend `true` -- le `if` interne n'est pas pris et l'on tombe sur le `return
    true` final."""
    restreint = _Effet(triggers=(RefreshEffectTrigger.EffectsChanged,))
    assert should_refresh_for_trigger(restreint, RefreshEffectTrigger.EffectsChanged) is True
    faux = [t for t in RefreshEffectTrigger
            if should_refresh_for_trigger(restreint, t) is False]
    assert sorted(int(t) for t in faux) == [3, 5, 6, 7, 8], faux
    vide = _Effet(triggers=())
    assert all(should_refresh_for_trigger(vide, t) is True for t in RefreshEffectTrigger)


# ------------------------------------------------------- `RefreshEffectsOperation$$ShouldBeActive`
def test_should_be_active_les_deux_forces_ne_lisent_RIEN():
    """`ForceActivate` / `ForceDeactivate` rendent leur verdict AVANT la garde `<+0x5e>`, avant
    `ShouldRefreshForTrigger` et avant la condition : le `switch` est en tete de fonction.

    On le prouve en rendant tout le reste HOSTILE au verdict attendu : composant bloque, flag
    inverse, condition inverse, declencheur non couvert."""
    e = _Effet(actif=False, triggers=())
    comp = EffectComponentView(is_active=False, blocked=True)
    assert should_be_active(RefreshEffectTrigger.TurnChanged, RefreshEffectType.ForceActivate,
                            e, comp) is True
    e2 = _Effet(actif=True)
    comp2 = EffectComponentView(is_active=True)
    assert should_be_active(RefreshEffectTrigger.Forced, RefreshEffectType.ForceDeactivate,
                            e2, comp2) is False


def test_should_be_active_hors_domaine_leve():
    """`default: throw new ArgumentOutOfRangeException(nameof(refreshType), refreshType, null)` --
    le natif LEVE, il ne retombe pas sur un defaut."""
    with pytest.raises(ValueError):
        should_be_active(RefreshEffectTrigger.Forced, 3, _Effet(), EffectComponentView())


def test_should_be_active_garde_5e_precede_tout_le_reste():
    """`if (effectComponent.<+0x5e>) return false;` passe AVANT `ShouldRefreshForTrigger` : meme
    un effet dont la condition est vraie et le flag a 1 rend `false`."""
    e = _Effet(actif=True)
    assert should_be_active(RefreshEffectTrigger.Forced, RefreshEffectType.Automatically, e,
                            EffectComponentView(is_active=True, blocked=True)) is False


def test_should_be_active_les_deux_regimes_divergent():
    """LE COEUR DE LA GARDE : declencheur COUVERT -> on evalue la condition ; declencheur NON
    COUVERT -> on re-emet le flag COURANT, sans rien evaluer.

    Le montage rend les deux DISCERNABLES en les faisant se contredire (condition FAUSSE, flag
    VRAI). Un port qui n'aurait qu'un seul regime rendrait la meme valeur deux fois."""
    e = _Effet(actif=False, triggers=(RefreshEffectTrigger.EffectsChanged,))
    comp = EffectComponentView(is_active=True)
    couvert = should_be_active(RefreshEffectTrigger.EffectsChanged,
                               RefreshEffectType.Automatically, e, comp)
    non_couvert = should_be_active(RefreshEffectTrigger.TurnChanged,
                                   RefreshEffectType.Automatically, e, comp)
    assert couvert is False, "declencheur couvert -> la CONDITION (fausse) doit gagner"
    assert non_couvert is True, "declencheur non couvert -> le FLAG courant (vrai) doit gagner"
    assert couvert != non_couvert, "les deux regimes doivent DIVERGER sur ce montage"


# ------------------------------------- `GetTargetsToAdd` / `GetTargetsToRemove` : deux differences
def test_les_deux_differences_sont_ordonnees_et_de_sens_opposes():
    current, desired = [10, 20, 30], [30, 5, 20]
    assert get_targets_to_add(current, desired) == [5]
    assert get_targets_to_remove(current, desired) == [10]


def test_l_ordre_rendu_est_celui_de_la_liste_PARCOURUE():
    """`GetTargetsToAdd` itere `desiredTargets` (l'ordre du SELECTEUR, non trie) ;
    `GetTargetsToRemove` itere `currentTargets` (l'ordre de `EffectComponent.Targets`, trie).
    C'est ce qui produit, dans le flux, des `ReceiveEffect` non croissants (49, 55, 53) et des
    `LoseEffect` croissants."""
    assert get_targets_to_add([], [49, 55, 53]) == [49, 55, 53]
    assert get_targets_to_remove([49, 53, 55], []) == [49, 53, 55]


def test_aucune_deduplication_ni_d_un_cote_ni_de_l_autre():
    """`List<T>.Add` inconditionnel des deux cotes : un doublon a l'entree ressort en doublon."""
    assert get_targets_to_add([], [7, 7]) == [7, 7]
    assert get_targets_to_remove([7, 7], []) == [7, 7]


# ----------------------------------------------- `EffectComponent$$AddTargetId` : le TRI, et son effet
def test_add_target_id_trie_apres_chaque_ajout():
    """`Targets.Add(id); Targets.Sort();` -- et c'est ce tri qui rend les `LoseEffect` croissants.

    ⚠ CE CLIQUET EXISTE PARCE QUE LE LIVE NE LE TIENT PAS : le probe mesure (I4) exercee par UN
    sous-arbre sur 289 (et ZERO sur `MC1_67`), les cibles se perdant presque toujours une par
    une. Un port qui n'appellerait pas `Sort()` resterait vert sur un board entier."""
    comp = EffectComponentView()
    for t in (55, 49, 53):
        comp.add_target_id(t)
    assert comp.targets == [49, 53, 55]


def test_le_tri_ordonne_les_lose_meme_quand_les_cibles_sont_ARRIVEES_en_desordre():
    """Le bout en bout du tri : on POSE les cibles en desordre, on retire tout, et l'ordre des
    `LoseEffect` doit etre croissant -- pas l'ordre d'arrivee."""
    comp = EffectComponentView()
    for t in (55, 49, 53):
        comp.add_target_id(t)
    plan = update_effect_targets([], comp, owner_id=1)
    assert [p.entity for p in plan if p.action == ACTION_LOSE] == [49, 53, 55]


def test_remove_target_id_ne_retrie_pas_et_tait_l_absent():
    """`List<T>.Remove` en ligne : premiere occurrence, silence si absent."""
    comp = EffectComponentView(targets=[1, 2, 3])
    comp.remove_target_id(9)
    assert comp.targets == [1, 2, 3]
    comp.remove_target_id(2)
    assert comp.targets == [1, 3]


# --------------------------------------------------------- `UpdateEffectTargets` : l'ORDRE du plan
def _actions(plan):
    return [p.action for p in plan]


def test_activation_l_ordre_est_activate_puis_receive_puis_apply():
    comp = EffectComponentView()
    plan = update_effect_targets([49, 55, 53], comp, owner_id=7)
    assert _actions(plan) == [ACTION_ACTIVATE, ACTION_RECEIVE, ACTION_RECEIVE, ACTION_RECEIVE,
                              ACTION_APPLY]
    assert [p.entity for p in plan if p.action == ACTION_RECEIVE] == [49, 55, 53]
    assert plan[0].entity == 7 and plan[0].step == int(StepType.ActivateEffect)
    assert comp.targets == [49, 53, 55], "les cibles sont POSEES et TRIEES par le plan"


def test_desactivation_le_deactivate_vient_APRES_les_cibles_pas_avant():
    """⚠ LE POINT CONTRE-INTUITIF, ET LA RAISON D'ETRE DE LA CONTRE-EPREUVE
    `plan_desactivation_en_tete` : `b__1` est ajoutee APRES les deux `AddRange`. Un assembleur
    naif ecrirait `DeactivateEffect` en tete."""
    comp = EffectComponentView(targets=[49, 53])
    plan = update_effect_targets([], comp, owner_id=7)
    assert _actions(plan) == [ACTION_LOSE, ACTION_LOSE, ACTION_DEACTIVATE, ACTION_REVERT]
    assert comp.targets == [], "les cibles sont RETIREES par le plan"


def test_bascule_mixte_ni_activate_ni_deactivate_et_lose_avant_receive():
    """Cibles qui bougent sans que l'effet s'allume ni s'eteigne : aucune des deux lambdas, et
    l'ordre `Lose*` PUIS `Receive*` PUIS `Revert` PUIS `Apply`."""
    comp = EffectComponentView(targets=[10, 20])
    plan = update_effect_targets([20, 30], comp, owner_id=7)
    assert _actions(plan) == [ACTION_LOSE, ACTION_RECEIVE, ACTION_REVERT, ACTION_APPLY]
    assert [p.entity for p in plan if p.action == ACTION_LOSE] == [10]
    assert [p.entity for p in plan if p.action == ACTION_RECEIVE] == [30]
    assert comp.targets == [20, 30]


def test_aucune_action_quand_rien_ne_bouge():
    """`current == desired` non vide : zero action. C'est ce qui fait que
    `GenerateEventGroup` n'ecrit AUCUNE ligne (`if (eventActions.Count > 0)`) -- le pendant du
    « jamais de `Effect_Refresh` vide » mesure par #477-r21."""
    comp = EffectComponentView(targets=[10, 20])
    assert update_effect_targets([20, 10], comp, owner_id=7) == []


def test_les_deux_bascules_sont_exclusives_par_construction():
    """(I3) du probe, figee ici : `currentTargets.Count` ne peut pas etre a la fois nul et
    strictement positif. On BALAIE les quatre regimes plutot que d'affirmer."""
    for cur, des in (([], []), ([], [1]), ([1], []), ([1], [2])):
        plan = update_effect_targets(des, EffectComponentView(targets=list(cur)), owner_id=0)
        noms = _actions(plan)
        assert not (ACTION_ACTIVATE in noms and ACTION_DEACTIVATE in noms), (cur, des)


def test_revert_et_apply_portent_leur_LOT_de_cibles():
    """`b__2` / `b__3` capturent `targetsToRemove` / `targetsToAdd` ENTIERS, pas une cible."""
    comp = EffectComponentView(targets=[10, 20])
    plan = update_effect_targets([30, 40], comp, owner_id=7)
    rev = [p for p in plan if p.action == ACTION_REVERT]
    app = [p for p in plan if p.action == ACTION_APPLY]
    assert len(rev) == 1 and rev[0].targets == (10, 20)
    assert len(app) == 1 and app[0].targets == (30, 40)


# ----------------------------------------------------------- la frontiere DECISION / EMISSION
def test_le_plan_se_lie_a_la_couche_d_emission_sans_import_a_rebours():
    """`bind_refresh_actions` lit les descripteurs EN CANARD. Le test le prouve en lui donnant des
    descripteurs qui ne sont PAS des `RefreshAction` -- s'il les importait, il ne les verrait pas.

    Il verifie aussi le point le plus facile a rater : les tags `ReceiveEffect` sont calcules UNE
    fois et PARTAGES (mirror d'`AddTargetsToEffect`, qui les hisse hors de son `foreach`)."""
    from engine.streams.dispatcher import StreamDispatcher
    from engine.streams.group_type import GroupType
    from engine.streams.stream_cache import StreamCache
    from engine.streams.refresh_effects import (EffectSetup, bind_refresh_actions,
                                                generate_event_group)

    class _Faux:
        def __init__(self, action, entity):
            self.action, self.entity = action, entity

    class _Capture:
        def __init__(self):
            self.racines = []

        def on_root_group_finished(self, group):
            self.racines.append(group)

        def on_log(self, chunk):
            pass

    cache = StreamCache()
    cap = _Capture()
    cache.add_listener(cap)
    events = StreamDispatcher()
    events.subscribe(cache)
    setup = EffectSetup(entity_id=82, effect_type=int(EffectType.Melta_ExtraDmg),
                        current_level=1)
    plan = [_Faux(ACTION_ACTIVATE, 51), _Faux(ACTION_RECEIVE, 49), _Faux(ACTION_RECEIVE, 55),
            _Faux(ACTION_APPLY, None)]
    lies = bind_refresh_actions(events, plan, setup)
    assert len(lies) == 3, "les formes `Revert`/`Apply` n'ecrivent aucune ligne de ce module"
    generate_event_group(events, lies, setup)
    texte = "".join(cap.racines)
    assert "Group=%s" % GroupType.Effect_Refresh.name in texte
    assert texte.count("Action=%s" % StepType.ActivateEffect.name) == 1
    assert texte.count("Action=%s" % StepType.ReceiveEffect.name) == 2
    # les tags `ReceiveEffect` sont PARTAGES : les deux blocs sont identiques, et ils portent le
    # `Tag=Effect_CurrentLevel` que la branche `ReceiveEffect` emet sans garde -- que l'unique
    # `ActivateEffect`, lui, n'a pas.
    assert texte.count("Tag=%s" % TagKey.Effect_CurrentLevel.name) == 2
    assert texte.count("Tag=%s" % TagKey.Effect_Id.name) == 3
