"""#351 -- SorcerousFacade (1100) : le COMPTE d'events de prediction, confronte au LIVE.

CE QUE CETTE GARDE RETIENT, et pourquoi aucun point ne peut passer par accident
-------------------------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions` construit
`list = [ProbableDamageEvent(sel, <slot 0x22>)]` PUIS `list.AddRange(GenerateMultiHitAttack
Predictions(...))` : DEUX events, tous deux sur `sel` (l'ENNEMI le plus proche), et `AddRange`
AJOUTE -- il ne substitue pas. Le port SUBSTITUAIT sur son chemin generique et rendait UN event.

A. **le COMPTE** (2) et la SEQUENCE (l'attaque normale d'abord, le batch ensuite) egalent le natif.
   Une garde sur la seule valeur du premier event serait passee AVANT le fix : c'est exactement ce
   qui a laisse le residu ouvert.
B. **les DEUX chemins du port coincident** avec le natif -- pas seulement celui qu'emprunte la
   route de decision. Le fork de port (deux implementations du meme artefact natif, dont une
   fausse) est ce que #351 a supprime ; cette assertion est ce qui l'empeche de revenir.
C. **la cible PASSEE est ignoree par la prediction** : interroger l'oracle sur l'ALLIE Psyker ou
   sur l'ENNEMI rend la MEME sequence, parce que le playbook remplace la cible par `sel`.
D. **A/B CAUSAL** : sans le terme en tete, le port retombe a UN event ; sans le profil VIDE, le 2e
   event perce l'armure (`Psychic` 100) au lieu de la subir pleine. Sans ces deux bras, un accord
   ne distinguerait pas « porte » de « juste par ailleurs ».

Porteur `thousTzaangor` (Yazaghor, HERO) ET allie Psyker `thousSorcerer` sont tous deux dans le
pool spawnable : aucun `catalog_inject` requis. Le second ennemi est RELEGUE loin -- a distance
egale, `First(1)` derriere `SortByDistance` ne trancherait plus que par l'ordre d'enumeration
(residu NOMME de `case-287`), et le montage mesurerait ce residu au lieu du compte d'events.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_351_facade_event_count as P                    # noqa: E402


@pytest.fixture(scope="module")
def arms():
    out = P.run(state_file=str(PYDIR.parents[1] / "logs" / "t351.json"), verbose=False)
    return out["arms"]


def test_native_emits_exactly_two_events_on_sel(arms):
    """A : le natif rend DEUX events, tous deux portes par `sel`. C'est le fait que le port
    n'honorait pas."""
    for label, arm in arms.items():
        assert not arm.get("error"), "bras %s : %s" % (label, arm.get("error"))
        assert len(arm["native_from_ally"]) == 2, (
            "bras %s : le natif rend %d event(s) sur `sel` au lieu de 2 -- `list = [normale]` puis "
            "`AddRange(batch)`" % (label, len(arm["native_from_ally"])))
        assert arm["n_events_native_ally"] == 2, (
            "bras %s : %d event(s) au TOTAL -- un event apparu sur une AUTRE cible serait un volet "
            "AoE, que ce playbook n'a pas" % (label, arm["n_events_native_ally"]))
        assert len(set(arm["native_targets_ally"])) == 1, (
            "bras %s : les deux events natifs ne portent plus la MEME cible (%s)"
            % (label, arm["native_targets_ally"]))


def test_both_port_paths_match_the_native_sequence(arms):
    """B : playbook ET chemin generique egalent le natif -- le fork est ferme."""
    for label, arm in arms.items():
        nat = arm["native_from_ally"]
        assert arm["port_playbook"] == nat, (
            "bras %s : PLAYBOOK %r != natif %r" % (label, arm["port_playbook"], nat))
        assert arm["port_generic"] == nat, (
            "bras %s : chemin GENERIQUE %r != natif %r -- le fork de port est revenu (deux "
            "implementations du meme artefact natif)" % (label, arm["port_generic"], nat))


def test_passed_target_does_not_enter_the_prediction(arms):
    """C : l'oracle interroge sur l'ALLIE ou sur l'ENNEMI rend la MEME chose."""
    for label, arm in arms.items():
        assert arm["native_from_foe"] == arm["native_from_ally"], (
            "bras %s : la cible passee change la prediction native (allie %r vs ennemi %r)"
            % (label, arm["native_from_ally"], arm["native_from_foe"]))


def test_head_term_is_necessary(arms):
    """D1 : sans `_PREPEND_NORMAL_ATTACK_EVENT`, le port rend UN event -- l'etat d'avant #351."""
    for label, arm in arms.items():
        assert len(arm["port_without_prepend"]) == 1, (
            "bras %s : sans le terme en tete le port rend %r, attendu le SEUL batch"
            % (label, arm["port_without_prepend"]))
        assert arm["port_without_prepend"] != arm["native_from_ally"], (
            "bras %s : le port egale ENCORE le natif sans le terme en tete -- il n'est pas ce qui "
            "produit l'accord" % label)


def test_empty_profile_is_necessary_on_armoured_target(arms):
    """D2 : sur cible BLINDEE, retirer `_PLAYBOOK_PROFILE_OVERRIDE[1100]` fait percer le 2e event
    (`Psychic` = 100) la ou le natif le laisse au plancher."""
    arm = arms["armor"]
    assert arm["port_without_profile"] != arm["native_from_ally"], (
        "retirer le profil VIDE ne change rien : ce montage n'exerce pas le percage, la garde D2 "
        "ne prouve rien (natif %r)" % (arm["native_from_ally"],))


def test_no_armour_arm_is_insensitive_to_the_profile(arms):
    """Contre-epreuve de D2 : SANS armure, le percage est sans objet -- si le retrait du profil y
    changeait quelque chose, c'est que l'ecart viendrait d'ailleurs que de l'armure."""
    arm = arms["noarmor"]
    assert arm["port_without_profile"] == arm["native_from_ally"], (
        "bras sans armure : le profil ne devrait avoir AUCUN effet, or le port passe de %r a %r"
        % (arm["native_from_ally"], arm["port_without_profile"]))


def test_the_two_arms_measure_different_regimes(arms):
    """Le montage DISCRIMINE : les deux bras ne rendent pas la meme sequence native. Deux bras
    identiques ne prouveraient qu'une chose -- que le levier d'armure n'a pas pris."""
    assert arms["noarmor"]["native_from_ally"] != arms["armor"]["native_from_ally"], (
        "les deux bras rendent la MEME sequence native %r : le levier `--armor-target` n'a pas pris"
        % (arms["armor"]["native_from_ally"],))
