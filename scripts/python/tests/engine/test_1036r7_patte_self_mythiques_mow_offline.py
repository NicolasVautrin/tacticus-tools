"""#1036-r7 -- LA PATTE SELF DES DEUX AURAS MYTHIQUES DE MoW : le VRAI blocage, et il n'est pas
celui que le residu annonçait.

## L'enonce du residu, re-mesure le 2026-08-15
Il dit : << le canal port serait `create_effect_damage_bonus_for_attack`, dont l'`att_ctx` ne porte
NI `att_rarity` NI `att_effect_names` >>. Cette moitie est VRAIE et re-mesurable (etage 1 ci-dessous
la fige). Mais elle n'est PAS le blocage : poser ces cles ne rendrait le regime atteignable NI en
combat NI en confrontation, pour DEUX raisons mesurees ici, chacune suffisante.

## (A) 1494 `CabalOfSorcerers` -- STRUCTURELLEMENT INERTE, cote NATIF
`$$CreateTargetSelector` = `ConditionalSelector(IsMachine(Owner), ifTrue = F, ifFalse = Unique(A + F))`
avec `F = Filter(B, AmountIsGreaterThanZero(ValidCharacter(AdjacentFriends(<element courant
@DSLSelectors+0x68>, unique, OnlyAliveAndTargetable))))`.
Les DEUX porteurs connus (`thousDaemonPrince`, `thousNpcMowDaemonPrince`) sont des MACHINES, donc
`IsMachine(Owner)` tient et SEULE `F` s'applique. Pour que le PORTEUR y entre, l'element courant
serait le porteur lui-meme, et il faudrait `AdjacentFriends(<la MoW>)` non vide -- or
`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit, unique, selType)` =
`Friends(unit, Units(AdjacentTiles(unit), unique, selType) - unit, selType)`, et
`AdjacentTilesSelector$$Select` ENUMERE les tuiles de l'ORIGINE. Une MoW n'en a AUCUNE
(`AddMachineOperation$$Execute` ne lui donne pas de `PositionComponent`, et le port non plus :
`snapshot._load_machines`). L'ensemble est donc VIDE, `AmountIsGreaterThanZero` FAUX, et le porteur
n'entre JAMAIS dans `F`. C'est un DEAD-CODE etabli par la structure, pas par une absence d'outil.

## (B) 1548 `GuardianConstruct` -- BLOCAGE D'ETAGE, mesure du 2026-08-15
Sa patte SELF exige DEUX gestes de la MoW : avoir REPARE quelqu'un (la branche SOURCE d'
`EffectTargetType.Both = 6 = 2|4` -- `EntityExtensions$$HasOneOfEffects` appelle
`EffectsQuery$$IsOwnerOfOneOfEffects` sous `& 4`) et ATTAQUER elle-meme (`get_OwnerIsCaster`).
Or les DEUX actives de `necroReanimator` -- `NanoscarabRepairProtocols` (qui POSE 1545) et
`ReanimationBeam` (la seule offensive : `dmgPct`/`maxDmg`) -- sont HORS `ABILITY_CLASSES`. Le port
ne peut donc ni poser l'effet source ni faire attaquer la MoW : porter la patte SELF ecrirait du
code qu'AUCUN montage ne peut atteindre (<< pas de porteur = speculatif >>).

⚠ CE QUI N'EST **PAS** LE BLOCAGE, ET LA MESURE L'ETABLIT : la RARETE. Mesure LIVE
(`probe_1036r7_patte_self_mow.py`, runner `necroReanimator` + `--equip-mythic
GuardianConstruct:4`) : `_unit_rarity(state, <MoW>) = Rarity.Mythic`, `combatSnapshot` rend
`rarity = 5, entityType = 6`, et le `StatsComponent` de la Machine porte bien `ctx.rarity`. Le
3e etage du selecteur serait donc OUVERT. La rarete a ete le blocage de cette famille pendant
plusieurs tranches ; elle ne l'est plus, et le dire evite de la re-accuser.
⚠ La branche SOURCE non plus n'est pas un blocage de CAPTEUR : elle se derive de `EffectsState`
(`e.source`), sans rien de neuf. C'est une cle a poser, le jour ou l'etage tombera.

## Ce que ce fichier garde
Il fige les DEUX verdicts et, surtout, il ROUGIT le jour ou l'etage tombe -- c'est-a-dire le jour
ou l'une des actives entre au registre : c'est CE jour-la qu'il faut relire ce residu, et personne
ne s'en souviendrait. Les ensembles sont RE-DERIVES (gameconfig + registre), jamais recopies.

ASCII only.
"""
from __future__ import annotations

import gameconfig as GC
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.extra_damage_aura import (
    CabalOfSorcerersExtraDamagePctEffect, GuardianConstructExtraDamagePctEffect)
from engine.runner.abilities.handler import ABILITY_CLASSES

#: Ce que ce fichier LIT -- pris LARGE (un declencheur trop etroit est un faux vert).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/damage_model.py",
        "data/gameconfig.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "les deux classes d'aura mythique, le registre d'abilities dont l'entree ROUVRE ce "
              "residu, et le gameconfig d'ou sortent les actives des deux porteurs.",
}

#: Les DEUX porteurs, et l'effet que chacun porte. Re-derives ci-dessous, jamais crus sur parole.
_PORTEURS = {"necroReanimator": ("GuardianConstruct", "GuardianConstruct_ExtraDamagePct"),
             "thousDaemonPrince": ("CabalOfSorcerers", "CabalOfSorcerers_ExtraDamagePct")}


def test_le_canal_SELF_n_est_surcharge_par_AUCUNE_des_deux_classes():
    """ETAT FIGE, avec sa raison : la patte SELF n'est PAS portee, et ce n'est pas un oubli.

    Le jour ou l'une des deux surcharge `create_effect_damage_bonus_for_attack`, ce test rougit et
    impose de relire les deux blocages ci-dessus -- notamment de verifier que le ctx SELF porte
    alors REELLEMENT la rarete et la branche SOURCE, sur les DEUX faces."""
    for cls in (GuardianConstructExtraDamagePctEffect, CabalOfSorcerersExtraDamagePctEffect):
        assert (cls.create_effect_damage_bonus_for_attack
                is BaseEffect.create_effect_damage_bonus_for_attack), (
            "%s surcharge le canal SELF : relire #1036-r7 (les deux blocages) avant de garder"
            % cls.__name__)


def test_les_deux_effets_SONT_bien_au_registre_par_leur_canal_AURA():
    """TEMOIN DE NON-VACUITE : sans lui, le test precedent serait vert sur un registre VIDE."""
    for _uid, (_ability, effet) in _PORTEURS.items():
        cls = EFFECT_CLASSES.get(effet)
        assert cls is not None, "%s absent d'EFFECT_CLASSES -- perimetre casse" % effet
        assert (cls.create_aura_attack_damage_bonus_for_ally
                is not BaseEffect.create_aura_attack_damage_bonus_for_ally), effet


def test_le_BLOCAGE_est_un_ETAGE_aucune_active_des_porteurs_n_est_portee():
    """LA MESURE QUI DEPLACE LE BLOCAGE, re-derivee du gameconfig et du registre.

    Tant qu'elle tient, porter la patte SELF de 1548 serait un port SPECULATIF : le port ne peut ni
    poser `NanoscarabRepairProtocols` (la branche SOURCE) ni faire attaquer la MoW."""
    actives = {}
    for uid in _PORTEURS:
        u = GC.unit(uid) or {}
        act = list(u.get("activeAbilities") or ())
        assert act, "%s n'a AUCUNE active en gameconfig -- perimetre casse" % uid
        actives[uid] = act
    portees = {uid: [a for a in act if ABILITY_CLASSES.get(a) is not None]
               for uid, act in actives.items()}
    assert all(not p for p in portees.values()), (
        "UNE ACTIVE D'UN PORTEUR EST ENTREE AU REGISTRE -- l'etage qui bloquait #1036-r7 vient de "
        "tomber, RELIS le residu : %r" % portees)


def test_la_patte_SELF_de_1494_est_INERTE_par_STRUCTURE_pas_par_outillage():
    """(A) ci-dessus, rendu EXECUTABLE : le filtre `F` compte les allies qualifies ADJACENTS a
    l'element courant. Pour la patte SELF cet element est le PORTEUR, une MoW SANS tuile -- le
    compteur ne peut donc rien rendre de positif, et le foyer le dit deja par son tri-etat.

    On vise le CALCULATEUR reel (`damage_model._cabal_valid_adjacent_to`), pas une re-ecriture :
    mesurer une copie ne prouverait rien sur le port."""
    from engine.runner.components import OwnerComponent, UnitComponent
    from engine.runner.damage_model import _cabal_valid_adjacent_to
    from engine.runner.state import State
    st = State()
    mow = st.add_entity(87)                       # la MoW : PAS de `PositionComponent`, comme le natif
    mow.add_component(UnitComponent(visual_id="necroReanimator", alive=True))
    mow.add_component(OwnerComponent(team=1, player=1))
    assert _cabal_valid_adjacent_to(st, 87, 1) in (None, 0), (
        "un porteur SANS tuile ne peut avoir aucun voisin qualifie : la branche F ne peut pas le "
        "retenir, et c'est ce qui rend la patte SELF de 1494 DEAD sur ses deux porteurs")
