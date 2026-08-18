"""#512-r9 -- CLIQUET : le vecteur `amount` emet `On(0x42 = EventTriggerType.FinalDamage)`.

CE QUI MANQUAIT, ET CE QUE C'ETAIT
-----------------------------------
`IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` vit sur la base COMMUNE et ses xrefs
entrantes sont EXHAUSTIVES : `IdunBattle.Operations.AttackDamageOperation$$Execute` et
`IdunBattle.Operations.AbilityDamageOperation$$Execute`. Le port a TROIS vecteurs d'attaque, dont
DEUX mirroitent la premiere (`damage_ops/normal.py` = l'attaque normale, `damage_ops/normal_like.py`
= le mode `amount`). Les deux premiers emettaient l'evenement ; `normal_like` n'emettait RIEN.

Ce n'etait PAS un ecart d'ORDRE -- celui-la (`8` -> `9`) a ete repare par #512-r7 -- mais un
evenement ENTIER absent. Consommateur porte, et unique (rayon de souffle mesure par
`probe_512r9_final_damage_blast_radius.py` : **1** ecouteur dans tout le registre) :
`RealityUnboundExtraMaxDamageAbility` (`thousTzaangor`), dont le trigger est

    On(0x42, subject=1)
    & HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target@0x178, 0xd = Psychic, times = 1)
    & AreEnemies(target@0x178, self@0x148)

et dont le behaviour pose `AddStaticStatModifierEffect(self, 1207, EXTRA_MAX_DAMAGE, ...)`.

TROIS LECTURES DU DECOMPILE QUI FIXENT LA PLACE ET LE GATE (toutes sur `t6dpr4k06g`) :
  1. l'appel est la DERNIERE instruction d'`AttackDamageOperation$$Execute`, apres la boucle des
     groupes additionnels et apres `attack@+0x28 += hitGroup@+0x4c` -> donc APRES le pipeline de
     degat (le compteur que lit le consommateur est deja incremente) et APRES la facade after-hit ;
  2. il precede `On(9)`/`On(10)`, qui sortent du slot 59 (`FinishAttack`) pousse par le NOEUD ;
  3. l'emission de l'event dans `RegisterFinalDamage` est INCONDITIONNELLE -- elle vit HORS du
     `if (0 < totalDamage)` qui garde la liste `currentAttack@+0x60` et le slot d'itable 0x4b.
     D'ou : aucun gate sur le degat, et aucun gate `is_outside_attack` (qui separe le NOEUD de
     l'OPERATION, et `RegisterFinalDamage` est du cote OPERATION).

ETAGES
------
  E1 LE CONSOMMATEUR   -- de bout en bout : le passif `RealityUnbound` d'un `thousTzaangor` allie
                          gagne son stat-mod quand le vecteur `amount` inflige du Psychic a un
                          ennemi. C'est l'ecart OBSERVABLE que le residu annoncait.
  E2 LE CONTRE-TEMOIN  -- meme montage, profil NON Psychic : rien ne doit etre pose. Sans lui, un
                          trigger devenu inconditionnel passerait pour une reussite.
  E3 PAS DE GATE       -- l'evenement part meme quand la facade est appelee en feuille NUE
                          (`is_outside_attack=False`), parce que le natif l'emet depuis l'OPERATION.
  E4 LE RANG           -- l'event 0x42 tombe APRES la facade after-hit et AVANT la cloture.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.dsl.event_trigger_type import EventTriggerType                     # noqa: E402
from engine.entities.effects_state import EffectsState                         # noqa: E402
from engine.entities.unit_context import UnitContext                           # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,         # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation              # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                         # noqa: E402
from engine.runner.state import State                                          # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE : tout ce que ce fichier lit -- le vecteur `amount`, la facade de dispatch, le registre
    # des triggers, la classe `RealityUnboundExtraMaxDamageAbility` et son effet -- est dans sa
    # propre fermeture d'imports. Recopier des chemins ici serait la faute #531.
    "chemins": (),
    # VRAI : la magnitude du stat-mod vient du gameconfig (`RealityUnbound.variables.extraMaxDmg`)
    # et le profil `Psychic` de la table des profils de degat. Un re-dump qui renommerait l'une de
    # ces cles ferait tomber le montant -- exactement le rouge attendu.
    "build": True,
    "toujours": False,
    "raison": "Quatre etages OFFLINE, montage `State` en memoire : aucun runner, aucune session, "
              "aucun RPC. Le verdict ne depend que de la fermeture d'imports du vecteur `amount` "
              "et du gameconfig du build.",
}

PSYCHIC = "Psychic"
NON_PSYCHIC = "HeavyRound"
TZAANGOR = "thousTzaangor"
#: `EffectType.RealityUnbound_ExtraMaxDamage` -- l'effet que le behaviour du volet B pose.
EFFET_EXTRA_MAX_DAMAGE = 1207
HP = 500000


def _unite(st: State, visual_id: str, team: int, pos, *, passives=None) -> int:
    """Le VRAI `UnitContext` (pas un stub) : le collecteur de triggers, le canal `att_ctx` et le
    substrat de stats en lisent une dizaine de champs, et un stub partiel s'effondre sur le
    premier qu'il n'a pas -- mesure faite (`get_stat` manquant). `passive_abilities` reste le
    canal MESURE (hierarchie 2 = `UnitConfiguration.PassiveAbilities`)."""
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id, True))
    e.add_component(HealthComponent(hp=HP, hp_max=HP))
    e.add_component(OwnerComponent(team=team, player=team))
    e.add_component(PositionComponent(pos[0], pos[1]))
    ctx = UnitContext(entity_id=e.id, visual_id=visual_id)
    if passives is not None:
        ctx.passive_abilities = list(passives)
    e.add_component(StatsComponent(ctx=ctx))
    return e.id


def _montage():
    """Equipe 0 : un attaquant + `thousTzaangor` (porteur de `RealityUnbound`).
    Equipe 1 : la victime -- ENNEMIE de `thousTzaangor`, ce qu'exige `AreEnemies(target, self)`."""
    st = State()
    st.rng = IntBasedMersenneTwister(4463111)
    st.effects = EffectsState()
    att = _unite(st, "thousExalted", 0, (0, 0))
    tza = _unite(st, TZAANGOR, 0, (1, 0), passives=["RealityUnbound"])
    vic = _unite(st, "admecDestroyer", 1, (4, 0))
    return st, att, tza, vic


def _a_le_stat_mod(st: State, uid: int) -> bool:
    for e in (st.effects.by_unit.get(int(uid)) or []):
        if int(getattr(e, "effect_type", 0) or 0) == EFFET_EXTRA_MAX_DAMAGE:
            return True
    return False


def _frappe(profil, *, is_outside_attack=True):
    st, att, tza, vic = _montage()
    assert not _a_le_stat_mod(st, tza), "l'etat de depart porte deja le stat-mod : montage vicie"
    AttackDamageOperation.execute_normal_like(
        st, att, vic, base=3000, profile_pierce=0, hits=1, spread_pct=0,
        damage_profile=profil, is_melee=False, is_outside_attack=is_outside_attack)
    return st, tza, vic


# --------------------------------------------------------------------------------------------- #
# E1 -- LE CONSOMMATEUR : le passif mord sur le vecteur `amount`
# --------------------------------------------------------------------------------------------- #
def test_e1_reality_unbound_gagne_son_stat_mod_sur_le_vecteur_amount():
    """L'ECART QUE #512-r9 FERMAIT. Avant, `execute_normal_like` n'emettait aucun `On(0x42)` :
    `thousTzaangor` ne gagnait RIEN alors que le natif appelle `RegisterFinalDamage` a la sortie de
    la MEME operation (`AttackDamageOperation$$Execute`)."""
    st, tza, vic = _frappe(PSYCHIC)
    assert _a_le_stat_mod(st, tza), (
        "`RealityUnbound` n'a pas pose son `EXTRA_MAX_DAMAGE` (%d) apres un coup Psychic du "
        "vecteur `amount` : l'`On(0x42 = FinalDamage)` n'est pas emis, ou il l'est trop tot "
        "(le gate `HasTakenDamageOfDamageProfileThisTurnAmountOfTimes` exige que le compteur de "
        "la victime soit DEJA incremente)" % EFFET_EXTRA_MAX_DAMAGE)


# --------------------------------------------------------------------------------------------- #
# E2 -- LE CONTRE-TEMOIN : un profil non Psychic ne pose rien
# --------------------------------------------------------------------------------------------- #
def test_e2_un_profil_non_psychic_ne_pose_rien():
    """Sans cet etage, un trigger devenu inconditionnel -- ou un event emis avec le mauvais
    payload -- passerait pour une reussite d'E1."""
    st, tza, vic = _frappe(NON_PSYCHIC)
    assert not _a_le_stat_mod(st, tza), (
        "`RealityUnbound` a pose son stat-mod pour un coup `%s` : le gate "
        "`HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(..., Psychic, 1)` ne discrimine plus"
        % NON_PSYCHIC)


# --------------------------------------------------------------------------------------------- #
# E3 -- PAS DE GATE `is_outside_attack` : l'OPERATION emet, pas le NOEUD
# --------------------------------------------------------------------------------------------- #
def test_e3_l_event_part_aussi_sur_une_feuille_nue():
    """`is_outside_attack` separe ce qu'emet le NOEUD (slot 59, `FinishAttack` -> `On(9)`/`On(10)`)
    de ce qu'emet l'OPERATION. `RegisterFinalDamage` est du cote OPERATION : une feuille
    `AttackDamage` NUE monte une operation, donc elle emet `On(0x42)` -- meme si elle n'ouvre ni ne
    ferme d'attaque. Gater cet event comme la cloture serait une faute de LECTURE."""
    st, tza, vic = _frappe(PSYCHIC, is_outside_attack=False)
    assert _a_le_stat_mod(st, tza), (
        "aucun `On(0x42)` sur une feuille NUE : l'emission a ete gatee par `is_outside_attack`, "
        "ce qui la range du cote du NOEUD alors que le natif l'emet depuis l'OPERATION")


# --------------------------------------------------------------------------------------------- #
# E4 -- LE RANG : 0x42 apres l'after-hit, avant la cloture
# --------------------------------------------------------------------------------------------- #
def test_e4_le_rang_de_l_event_dans_la_sequence(monkeypatch):
    """L'ORDRE NATIF d'une feuille AUTONOME est `... 0x3c, 8, 0x42, 9`. On journalise les events
    emis par la facade en substituant les trois vecteurs DANS LE MODULE de dispatch (forme B chez
    l'appelant -- `from ..triggers.dispatch import attack as attack_dispatch`, donc le patch MORD).

    ⚠ Le non-vide est ASSERTIONNE : un journal vide passerait pour un ordre correct."""
    from engine.runner.operations.triggers.dispatch import attack as AD
    journal: list = []
    v_ah, v_fd, v_fa = (AD.after_hit_ability_attack, AD.final_damage_triggers,
                        AD.finish_attack_triggers)

    def _ah(*a, **k):
        journal.append("after_hit")
        return v_ah(*a, **k)

    def _fd(*a, **k):
        journal.append("final_damage")
        return v_fd(*a, **k)

    def _fa(*a, **k):
        journal.append("finish_attack")
        return v_fa(*a, **k)

    monkeypatch.setattr(AD, "after_hit_ability_attack", _ah)
    monkeypatch.setattr(AD, "final_damage_triggers", _fd)
    monkeypatch.setattr(AD, "finish_attack_triggers", _fa)
    _frappe(PSYCHIC)
    assert journal, ("aucun vecteur journalise : la substitution ne MORD pas (l'appelant a-t-il "
                     "ete hisse en forme A ?) -- ce test serait vert sur rien")
    assert journal == ["after_hit", "final_damage", "finish_attack"], (
        "rang natif non respecte (attendu after_hit -> 0x42 -> cloture) : %s" % journal)
    assert int(EventTriggerType.FinalDamage) == 0x42


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
