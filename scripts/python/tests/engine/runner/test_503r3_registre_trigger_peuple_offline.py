"""GARDE OFFLINE #503-r3 -- la chaine TRIGGER doit peupler elle-meme le registre qu'elle LIT.

CE QUI REGRESSAIT SANS ELLE, et ce n'est pas theorique (mesure du 2026-08-10, process FRAIS,
n'important que `operations/triggers/dispatch/registry.py`) :

    1134 FullThrottle             present   (import pour EFFET DE BORD explicite dans `registry.py`)
    1127 SeekerMissile_Attack     ABSENT    (dependait de `abilities/tau.py`)
    1237 OverwhelmingWrath_Attack ABSENT    (dependait de `abilities/worldeaters.py`)
    total du registre : 1 entree

Le `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`) fait
son lookup dans `TRIGGERED_ABILITY_BEHAVIOURS`. Une phase 2 absente rend `dispatched: False` **et
l'effet est retire quand meme** (le `RemoveEffect` du MEME arbre) -- un marqueur qui disparait sans
que rien ne frappe, exactement le regime que `pending_attack.py` Sec.2 declare PIRE que le statu
quo. En regime reel le runner charge `abilities/handler.py`, donc rien ne se voyait ; le trou
s'ouvre des qu'un probe ou un test entre dans le paquet par la chaine trigger.

PERIMETRE DERIVE, JAMAIS ECRIT A LA MAIN : la liste des abilities exigees est
`PENDING_ATTACK_EFFECTS` elle-meme. Une entree ajoutee a cette table sans que sa phase 2 soit
atteignable depuis la chaine trigger rougit ici -- c'est le cran qui manquait, et c'est le seul
gisement que notre propre cadence de portage alimente.

CE QUE LA MESURE A ETABLI SUR LES DEUX ARETES (protocole du CLAUDE.md : charger la cible SEULE dans
un process frais et regarder si le module de depart y atterrit) :

    `registry -> abilities.worldeaters`  : worldeaters seul NE tire PAS registry -> arete GRATUITE
    `registry -> abilities.tau`          : tau seul TIRE registry                 -> arete PORTEUSE
      chaine mesuree : tau -> attack_query -> revive_effect -> dispatch.ability
                           -> dispatch.core -> dispatch.registry

Hisser l'une et differer l'autre aurait inscrit une asymetrie que rien dans le natif ne justifie.
La reparation est le point (1) de la doctrine -- DEPLACER : les deux phases 2 sont des abilities
TRIGGERED, elles vivent desormais sous `operations/triggers/loki/`, ou `full_throttle.py` (1134)
portait deja le patron. `abilities/tau.py` et `abilities/worldeaters.py` gardent leur ACTIVE.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.operations.triggers.pending_attack import PENDING_ATTACK_EFFECTS

_RACINE = Path(__file__).resolve().parents[3]        # scripts/python

_PROGRAMME = r"""
import json, sys
import engine.runner.operations.triggers.dispatch.registry  # SEULE entree : la chaine trigger
from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from engine.runner.operations.triggers.pending_attack import PENDING_ATTACK_EFFECTS
exiges = sorted(s.triggered_ability for s in PENDING_ATTACK_EFFECTS.values())
print(json.dumps({
    "exiges": exiges,
    "presents": [a for a in exiges if a in TRIGGERED_ABILITY_BEHAVIOURS],
    "absents": [a for a in exiges if a not in TRIGGERED_ABILITY_BEHAVIOURS],
    "total_registre": len(TRIGGERED_ABILITY_BEHAVIOURS),
    "abilities_charges": sorted(m for m in sys.modules
                                if m.startswith("engine.runner.abilities.")
                                and m.count(".") == 4),
}))
"""


def _mesure_process_frais() -> dict:
    """Un process NEUF -- dans le process pytest tout est deja charge, donc la mesure y serait
    structurellement aveugle : c'est exactement pourquoi ce trou a survecu a deux livraisons."""
    p = subprocess.run([sys.executable, "-c", _PROGRAMME], cwd=str(_RACINE),
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, "process frais rc=%d\nSTDERR:\n%s" % (p.returncode, p.stderr[-3000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_la_chaine_trigger_peuple_les_phases_2_quelle_declenche():
    """Toute phase 2 nommee par `PENDING_ATTACK_EFFECTS` est dispatchable des que la chaine trigger
    est chargee -- sans passer par `abilities/handler.py`."""
    m = _mesure_process_frais()
    assert m["exiges"], "table VIDE : le test se serait auto-satisfait (cf. la doctrine du non-vide)"
    assert not m["absents"], (
        "phases 2 ABSENTES du registre en process frais : %s (exigees %s, registre %d entrees). "
        "Le `TriggerAbility` d'`APendingAttackEffect` rendrait `dispatched: False` en RETIRANT "
        "l'effet -- marqueur consomme, rien qui frappe."
        % (m["absents"], m["exiges"], m["total_registre"]))


def test_le_peuplement_ne_traine_pas_les_modules_d_abilities():
    """Le peuplement ne doit PAS etre obtenu en hissant `abilities/tau.py` dans `registry.py` :
    l'arete est PORTEUSE (mesuree), donc la fermer creerait un cycle. La reparation est un
    DEPLACEMENT vers `operations/triggers/loki/`, ce que ce cran fige."""
    m = _mesure_process_frais()
    for interdit in ("engine.runner.abilities.tau", "engine.runner.abilities.worldeaters"):
        assert interdit not in m["abilities_charges"], (
            "%s est charge par la seule chaine trigger : l'arete PORTEUSE a ete fermee au lieu "
            "d'etre supprimee. Modules d'abilities charges : %s"
            % (interdit, m["abilities_charges"]))


def test_les_identifiants_partages_restent_en_phase():
    """`OW_ACTIVE_ID` existe des DEUX cotes -- la phase 1 (`abilities/worldeaters.py`) et la phase 2
    (`triggers/loki/overwhelming_wrath_attack.py`) -- parce que l'arete ne peut aller que dans un
    sens. Ce sont deux fois la meme expression sur le meme enum ; ce cran interdit qu'elles se
    separent en silence. Le kit `SeekerMissileFrequencyLock`, lui, n'a QU'UNE definition : la
    phase 1 l'importe de la phase 2, et ce test le VERIFIE plutot que de le supposer."""
    from engine.runner.abilities import tau, worldeaters
    from engine.runner.operations.triggers.loki import (overwhelming_wrath_attack as owa,
                                                        seeker_missile_attack as sma)
    assert worldeaters.OW_ACTIVE_ID == owa.OW_ACTIVE_ID
    for nom in ("SEEKER_MISSILE_FREQUENCY_LOCK_ID", "SEEKER_LOCK_TARGET", "SEEKER_LOCK_AIMING"):
        assert getattr(tau, nom) is getattr(sma, nom), (
            "%s n'est plus l'objet importe de la phase 2 : une SECONDE definition est apparue "
            "cote phase 1, et les deux peuvent desormais diverger" % nom)


def test_les_phases_2_vivent_sous_operations_triggers():
    """Le FOYER, pas seulement le resultat : chaque callable inscrit pour une phase 2 est defini
    sous `engine.runner.operations.triggers.` -- un retour en arriere (re-definir la phase 2 dans
    le module de l'ACTIVE) rouvrirait le trou meme si un import pour effet de bord le masquait."""
    from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
    import engine.runner.abilities.handler  # noqa: F401  -- peuple TOUT le registre
    for spec in PENDING_ATTACK_EFFECTS.values():
        fn = TRIGGERED_ABILITY_BEHAVIOURS.get(spec.triggered_ability)
        assert fn is not None, "phase 2 de %s (%d) absente du registre" % (spec.native,
                                                                          spec.triggered_ability)
        assert fn.__module__.startswith("engine.runner.operations.triggers."), (
            "la phase 2 de %s (%d) est definie dans %s : elle doit vivre sous "
            "`engine.runner.operations.triggers.`" % (spec.native, spec.triggered_ability,
                                                      fn.__module__))
