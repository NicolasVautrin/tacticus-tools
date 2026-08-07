"""#270-r1-r1-r3 -- GARDE : les litteraux entiers des ROLES DERIVES sont des MEMBRES d'enum.

CE QUI DISTINGUE CETTE TRANCHE DES TROIS VOLETS PRECEDENTS.

Les volets 1 et 2 portaient sur des CLES DE DICT, le volet #270-r1-r1 sur des ELEMENTS DE
CONTENEUR. Tous trois disposaient d'un discriminant STRUCTUREL : la COUVERTURE du groupe (si tous
les entiers d'un dict/tuple appartiennent au meme enum, le groupe EST clee par cet enum). Ici il
n'y a aucun groupe -- ce sont des affectations isolees, des valeurs de retour, des arguments, des
indices. Le seul discriminant disponible est donc, SITE PAR SITE, le NOM deja ecrit au site ou le
TYPE DECLARE lu dans `data/symbols/<build>/frida/methods.tsv`.

QUATRE ATTRIBUTIONS REPOSENT SUR UNE SIGNATURE LUE, PAS SUR UN NOM :
  * `IdunBattle.Configuration.AbilityConstantType` -- le type du parametre `constantType` de
    `IdunBattle.Configuration.AbilityConfiguration.GetNumberConstant` (et de ses trois voisins
    `TryGetNumberConstant` / `GetStringArrayConstant` / `TryGetStringArrayConstant`) ;
  * `IdunBattle.Configuration.AbilityVariableType` -- le type du parametre `variableType` de
    `IdunBattle.Configuration.AbilityConfiguration.GetVariableForLevel` ;
  * `IdunBattle.Entities.Enum.UnitFlag` -- le type du parametre `flag` d'
    `IdunBattle.Entities.UnitExtensions.HasFlag` ;
  * `IdunBattle.Entities.Enum.EntityType` -- le type du parametre `type` d'
    `IdunBattle.Core.Entity..ctor`.
Les deux premiers partagent 141 ordinaux et NOMMENT AUTRE CHOSE a valeur egale (22 = `range` cote
constante, `blockDmg_2` cote variable) : c'est l'ACCESSEUR appele au site qui tranche, jamais
l'ordinal. L'etage 5 mesure cette non-degenerescence -- sans elle, l'etage 1 pourrait tenir sur une
confusion des deux.

L'ORDINAL NE TRANCHE JAMAIS, ET CETTE TRANCHE L'A PAYE DE L'INTERIEUR. La premiere version du
convertisseur portait le membre EN DUR ; elle ecrivait `TriggeredAbilityType.PathOfCommand_ExtraDmg`
pour 1111, qui est `WireweaveNet` cote triggered et `PathOfCommand_ExtraDmg` cote `EffectType`. Le
convertisseur a REFUSE (le mirror ne connait pas ce nom), et sa table ne porte plus depuis que
l'ENUM -- le membre est DERIVE du mirror. Meme lecon que #270-c, re-mesuree.

DEUX ERREURS DE NOM TROUVEES DANS LE PORT, et corrigees ici :
  * `runner/operations/effects.py` nommait `0x472` « `Wraithcannon_NormalAttack` ». C'est
    l'`ActiveAbilityType` 1138 ; le parametre d'
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect.IsUpdatable` est
    DECLARE `IdunBattle.Entities.Enum.EffectType`, ou 1138 est `PowerUp_Armor`.
  * `runner/components.py` declarait le flag 27 « hors enum du dump ». Le build courant le porte :
    `UnitFlag.TurnTerminated`. L'affirmation etait PERIMEE -- exactement la forme de peremption
    silencieuse que la regle vise.

SIX ETAGES.

  * ETAGE 1 -- RENUMEROTAGE : chaque membre ecrit par la tranche vaut TOUJOURS l'ordinal mesure au
    moment de la conversion. C'est le cran qui manque a `probe_313` : lui compare le MIRROR au
    BUILD, donc il redevient VERT des qu'on regenere le mirror -- alors meme que la valeur ecrite
    au site a change. Ici l'ordinal est FIGE : un renumerotage rougit, regeneration ou pas.
  * ETAGE 2 -- CLIQUET DE FORME : chaque fichier porte toujours au moins le nombre d'occurrences
    de chaque membre que la conversion y a mis. Rougit si un ordinal nu revient a la place.
  * ETAGE 3 -- ACCESSEURS PUBLICS : les chemins REELS des appelants (`UnitFlagsComponent.has`,
    `remove_turn_flags`, `BaseTriggeredAbility.VAR_*`), avec l'ordinal ET avec le membre, et avec
    anti-degenerescence -- les reponses doivent DISCRIMINER, sans quoi l'egalite tiendrait aussi
    sur un composant qui repondrait pareil a tout.
  * ETAGE 4 -- LE REGISTRE : les quatre mirrors NEUFS sont inscrits au registre de `probe_313`,
    SOUS GARDE, apparies par leur nom PLEIN. Ce gisement s'est rouvert QUATRE fois par notre propre
    cadence (`PathfinderType` #381-r5, `KillUnitStep` #389-r2, `DamageReason` #651 -- qui rendait
    `master` rouge --, `Edge` #270-r1-r1).
  * ETAGE 5 -- NON-DEGENERESCENCE `AbilityConstantType` / `AbilityVariableType`. Le jour ou les
    deux coincideraient sur les ordinaux utilises, l'etage 1 cesserait de distinguer une confusion
    des deux accesseurs -- et se tairait.
  * ETAGE 6 -- PLACEMENT DES MIRRORS : les deux index vivent sous `engine/entities/`, PAS sous
    `engine/entities/abilities/`. Le second emplacement a ete ESSAYE et rend les modules
    INIMPORTABLES : l'`__init__.py` du sous-paquet tire `active_ability` ->
    `services.damage_prediction` -> `ImportError` sur module partiellement initialise. Le test
    REPRODUIT la contrainte pour que le compromis se retourne tout seul le jour ou elle disparait
    (meme forme que l'etage 4 de `test_270r1r1_container_enum_offline.py`).

CE QUI RESTE DELIBEREMENT EN LITTERAL, et c'est un RESULTAT, pas un oubli (les etages 1/2 ne
portent pas dessus ; le dernier bloc du fichier le rend EXECUTABLE) : tous les `100` de
pourcentage, `INT_MAX` / `DISTANCE_UNREACHABLE` / `MIN_DISTANCE_EMPTY` (0x7FFFFFFF), l'etat interne
du Mersenne Twister, les couts de pathfinding, les poids d'utilite, `MAX_ITERATIONS`, les timeouts
RPC, et les VALEURS de constante gameconfig (`FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30` est la valeur,
pas l'index `42 = chance`). Forcer un nom sur un entier qui ne designe aucun enum est PIRE que
l'ordinal, qui au moins ne ment pas. Liste raisonnee :
`docs/rl/case-270r1r1r3-roles-derives.md`.

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import ast
import importlib
import sys
from enum import Enum
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

ENGINE = PYDIR / "engine"

from engine.entities.ability_constant_type import AbilityConstantType  # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.entity_type import EntityType  # noqa: E402
from engine.entities.stats import StatType  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.entities.unit_faction import UnitFaction  # noqa: E402
from engine.entities.unit_flag import UnitFlag  # noqa: E402
from engine.utilities.utility_type import UtilityType  # noqa: E402

ENUMS = {c.__name__: c for c in (
    AbilityConstantType, AbilityVariableType, UnitFlag, EntityType, StatType, EffectType,
    TriggeredAbilityType, ActiveAbilityType, UnitFaction, UnitTrait, UtilityType)}


def _resoudre(cle: str):
    cls, membre = cle.split(".", 1)
    return getattr(ENUMS[cls], membre)


# ── TABLES -- DERIVEES de l'AST (delta arbre de base -> arbre livre), jamais retranscrites.
#
# `SITES` : (fichier sous `engine/`) -> {"Enum.membre": occurrences INTRODUITES par la tranche}.
# La cle est un COMPTE, pas un numero de ligne : elle survit a un deplacement de code, et un
# compte qui BAISSE signale un retour a l'ordinal nu.
# `ORDINAUX` : l'ordinal MESURE de chaque membre au moment de la conversion -- le cran
# anti-renumerotage. Il ne se regenere pas : c'est ce qui en fait un temoin.

SITES = {
    "ai/action_generators.py": {
        "ActiveAbilityType.Repair_GalvanicField": 1,
        "ActiveAbilityType.SpiritLeech": 1,
    },
    "entities/abilities/triggered_ability.py": {
        "AbilityVariableType.maxDmg": 1,
        "AbilityVariableType.minDmg": 1,
    },
    "entities/effects/loki/ability_modifications.py": {
        "AbilityConstantType.nrOfSummons": 1,
        "AbilityConstantType.range": 1,
    },
    "entities/effects/loki/counter_attack.py": {
        "TriggeredAbilityType.WireweaveNet": 1,
    },
    "entities/effects/loki/crit_aura.py": {
        "EffectType.PathOfCommand_ExtraCrit": 1,
        "EffectType.PathOfCommand_ExtraDmg": 1,
        "StatType.CRIT_CHANCE": 1,
    },
    "entities/effects/loki/cursed_plague_bell.py": {
        "AbilityConstantType.extraMovement": 1,
    },
    "entities/effects/loki/dark_angels_passives.py": {
        "EffectType.FearedInterrogator_Owner": 1,
        "EffectType.FearedInterrogator_Target": 1,
        "EffectType.LionHelm_ExtraBlockChance": 1,
        "EffectType.LionHelm_ExtraBlockDamage": 1,
        "EffectType.LionHelm_ExtraDmg": 1,
        "EffectType.Pinned": 1,
        "EffectType.Stunned": 1,
        "StatType.BLOCK_CHANCE": 1,
        "StatType.BLOCK_DAMAGE": 1,
    },
    "entities/effects/loki/extra_damage_aura.py": {
        "EffectType.DefenderOfTheGreaterGood_ExtraDmg": 1,
    },
    "entities/effects/loki/hits.py": {
        "EffectType.DefenderOfTheGreaterGood_ExtraHits": 1,
        "EffectType.LegendaryCommander_ExtraHits": 1,
        "StatType.BLOCK_CHANCE": 2,
        "StatType.BLOCK_DAMAGE": 1,
        "StatType.EXTRA_HITS": 1,
    },
    "entities/effects/loki/reality_unbound.py": {
        "StatType.EXTRA_MAX_DAMAGE": 1,
        "StatType.EXTRA_RANGE": 1,
    },
    "entities/effects/loki/status.py": {
        "StatType.CRIT_CHANCE": 1,
        "StatType.FIXED_ARMOR": 3,
    },
    "entities/effects/loki/unbreakable_duty.py": {
        "StatType.HEALTH": 1,
    },
    "entities/effects/loki/visions_of_heresy.py": {
        "StatType.EXTRA_PIERCE_MELEE": 1,
        "StatType.EXTRA_PIERCE_RANGED": 1,
    },
    "entities/effects/loki/votann.py": {
        "ActiveAbilityType.GravitonRifle": 1,
    },
    "entities/selectors/tiles.py": {
        "UtilityType.Tile": 1,
    },
    "playbook/excruciating_frequencies.py": {
        "ActiveAbilityType.ExcruciatingFrequencies": 1,
    },
    "playbook/friends_in_range.py": {
        "AbilityConstantType.range": 1,
        "TriggeredAbilityType.AstartesBanner": 1,
        "TriggeredAbilityType.KardiocoreGalvanus": 1,
    },
    "playbook/geminae_superia.py": {
        "TriggeredAbilityType.GeminaeSuperia": 1,
    },
    "playbook/modified_exoarmour.py": {
        "TriggeredAbilityType.ModifiedExoarmour": 1,
    },
    "playbook/noncomparable/the_quickening.py": {
        "TriggeredAbilityType.FuryOfTheAncients": 1,
    },
    "runner/abilities/admec.py": {
        "AbilityVariableType.hpToRepair": 1,
    },
    "runner/abilities/astramilitarum.py": {
        "AbilityConstantType.affectedUnitIds": 1,
        "AbilityConstantType.nrOfHits": 2,
        "AbilityConstantType.nrOfHits_2": 1,
        "AbilityConstantType.nrOfProjectiles": 1,
        "AbilityConstantType.nrOfProjectiles_2": 1,
        "AbilityConstantType.nrOfSummons": 3,
        "AbilityConstantType.range": 1,
        "AbilityVariableType.maxSummons": 1,
    },
    "runner/abilities/attack_query.py": {
        "UnitFlag.CanHealFullHealthUnits": 1,
        "UnitFlag.CanRepairFullHealthUnits": 1,
    },
    "runner/abilities/base.py": {
        "ActiveAbilityType.FightingRetreat": 1,
    },
    "runner/abilities/blacklegion.py": {
        "AbilityConstantType.maxNrOfHits": 1,
        "AbilityConstantType.maxSummons": 1,
        "AbilityConstantType.nrOfHits": 2,
        "AbilityConstantType.range": 3,
        "AbilityVariableType.extraCritDmg": 1,
        "AbilityVariableType.hp": 1,
    },
    "runner/abilities/custodes.py": {
        "AbilityConstantType.nrOfRounds": 1,
        "AbilityVariableType.hpToHeal": 1,
    },
    "runner/abilities/deathguard.py": {
        "AbilityVariableType.chance": 1,
        "AbilityVariableType.chance_2": 1,
    },
    "runner/abilities/emperorschildren.py": {
        "UnitFlag.Overkilled": 1,
    },
    "runner/abilities/loki/mv71.py": {
        "TriggeredAbilityType.DefenderOfTheGreaterGood": 1,
        "TriggeredAbilityType.SaviorProtocols": 1,
        "TriggeredAbilityType.StructuralAnalyser": 1,
    },
    "runner/abilities/necrons.py": {
        "AbilityConstantType.extraHit": 1,
        "AbilityConstantType.maxSummons": 1,
        "AbilityConstantType.nrOfRounds": 1,
        "AbilityConstantType.range": 2,
    },
    "runner/abilities/orks.py": {
        "AbilityConstantType.extraHits": 1,
        "AbilityConstantType.extraMovement": 1,
        "AbilityConstantType.healthPct": 1,
        "AbilityConstantType.maxNrOfHits": 1,
        "AbilityConstantType.nrOfHits": 2,
        "AbilityConstantType.nrOfHits_2": 1,
        "AbilityConstantType.nrOfRounds": 1,
        "AbilityConstantType.nrOfSummons": 1,
        "AbilityConstantType.nrOfUnits": 1,
        "AbilityConstantType.nrOfUnits_2": 1,
        "AbilityConstantType.nrOfUnits_3": 1,
        "AbilityConstantType.nrOfUnits_4": 1,
        "AbilityConstantType.range": 2,
        "AbilityConstantType.range_2": 1,
        "AbilityVariableType.maxDmg": 1,
        "AbilityVariableType.minDmg": 1,
        "AbilityVariableType.nrOfTiles": 1,
    },
    "runner/abilities/targeting.py": {
        "EffectType.ForcedInMelee": 1,
        "EffectType.FriendlyFire": 1,
        "UnitFlag.Untargetable": 1,
        "UnitTrait.Ranged": 1,
        "UnitTrait.Steppable": 1,
    },
    "runner/abilities/tyranids.py": {
        "AbilityConstantType.range": 1,
    },
    "runner/abilities/ultramarines.py": {
        "AbilityVariableType.extraCritDmg": 1,
    },
    "runner/components.py": {
        "EffectType.FuelledByFury_BlockOverkill": 1,
        "UnitFlag.ActiveAbilityUsed": 1,
        "UnitFlag.ArrivedAtFinalTile": 1,
        # `Dead` est arrive par le REBASE : `master` a ajoute `DEAD = 6` pendant la tranche, et
        # cette classe est nommee en entier -- le laisser en ordinal nu aurait rouvert le gisement
        # dans le fichier meme qui le ferme.
        "UnitFlag.Dead": 1,
        "UnitFlag.Fled": 1,
        "UnitFlag.Moved": 1,
        "UnitFlag.NoActionAvailable": 1,
        "UnitFlag.Overkilled": 1,
        "UnitFlag.PreventOverkill": 1,
        "UnitFlag.Removed": 1,
        "UnitFlag.Resurrected": 1,
        "UnitFlag.Teleported": 1,
        "UnitFlag.TurnFinished": 1,
        "UnitFlag.TurnTerminated": 1,
    },
    "runner/operations/effects.py": {
        "EffectType.PowerUp_Armor": 1,
    },
    "runner/operations/triggers/loki/draw_fire.py": {
        "TriggeredAbilityType.DrawFire": 1,
        "TriggeredAbilityType.PrimarchOfTheFirstLegion": 1,
    },
    "runner/operations/triggers/loki/empyric_ambush.py": {
        "UnitFlag.ForceRangedAttack": 1,
    },
    "runner/operations/triggers/loki/final_justice.py": {
        "TriggeredAbilityType.FinalJustice": 1,
    },
    "runner/operations/triggers/loki/fuelled_by_fury.py": {
        "TriggeredAbilityType.FinalJustice": 1,
        "TriggeredAbilityType.FuelledByFury": 1,
    },
    "runner/operations/triggers/loki/harlequins_panoply.py": {
        "TriggeredAbilityType.HarlequinsPanoply": 1,
    },
    "runner/operations/triggers/loki/haywire_mine.py": {
        "UtilityType.Tile": 1,
    },
    "runner/operations/triggers/loki/my_will_be_done_overlord.py": {
        "UnitFaction.Necrons": 1,
    },
    "runner/operations/triggers/loki/phoenix_gem.py": {
        "EffectType.PhoenixGem_CanRevive": 1,
        "TriggeredAbilityType.PhoenixGem": 1,
    },
    "runner/operations/triggers/loki/reanimation_beam.py": {
        "EffectType.NanoscarabRepairProtocols": 1,
        "EffectType.ReanimationBeam_Revive": 1,
    },
    "runner/operations/triggers/loki/rites_of_morkai.py": {
        "EffectType.RitesOfMorkai": 1,
    },
    "runner/operations/triggers/loki/spiritual_leader.py": {
        "UnitFlag.Untargetable": 1,
    },
    "runner/snapshot.py": {
        "EntityType.Machine": 1,
    },
    "services/ability_caster_gates.py": {
        "UnitTrait.Steppable": 1,
    },
    "services/targeting_query.py": {
        "UnitTrait.IndirectFire": 1,
    },
}

ORDINAUX = {
    "AbilityConstantType.affectedUnitIds": 62,
    "AbilityConstantType.extraHit": 43,
    "AbilityConstantType.extraHits": 100,
    "AbilityConstantType.extraMovement": 14,
    "AbilityConstantType.healthPct": 79,
    "AbilityConstantType.maxNrOfHits": 72,
    "AbilityConstantType.maxSummons": 60,
    "AbilityConstantType.nrOfHits": 47,
    "AbilityConstantType.nrOfHits_2": 50,
    "AbilityConstantType.nrOfProjectiles": 31,
    "AbilityConstantType.nrOfProjectiles_2": 56,
    "AbilityConstantType.nrOfRounds": 69,
    "AbilityConstantType.nrOfSummons": 16,
    "AbilityConstantType.nrOfUnits": 120,
    "AbilityConstantType.nrOfUnits_2": 121,
    "AbilityConstantType.nrOfUnits_3": 129,
    "AbilityConstantType.nrOfUnits_4": 130,
    "AbilityConstantType.range": 22,
    "AbilityConstantType.range_2": 68,
    "AbilityVariableType.chance": 58,
    "AbilityVariableType.chance_2": 59,
    "AbilityVariableType.extraCritDmg": 66,
    "AbilityVariableType.hp": 29,
    "AbilityVariableType.hpToHeal": 32,
    "AbilityVariableType.hpToRepair": 36,
    "AbilityVariableType.maxDmg": 13,
    "AbilityVariableType.maxSummons": 49,
    "AbilityVariableType.minDmg": 12,
    "AbilityVariableType.nrOfTiles": 102,
    "ActiveAbilityType.ExcruciatingFrequencies": 1197,
    "ActiveAbilityType.FightingRetreat": 1081,
    "ActiveAbilityType.GravitonRifle": 1206,
    "ActiveAbilityType.Repair_GalvanicField": 1119,
    "ActiveAbilityType.SpiritLeech": 1104,
    "EffectType.DefenderOfTheGreaterGood_ExtraDmg": 1182,
    "EffectType.DefenderOfTheGreaterGood_ExtraHits": 1183,
    "EffectType.FearedInterrogator_Owner": 1294,
    "EffectType.FearedInterrogator_Target": 1295,
    "EffectType.ForcedInMelee": 1321,
    "EffectType.FriendlyFire": 103,
    "EffectType.FuelledByFury_BlockOverkill": 1354,
    "EffectType.LegendaryCommander_ExtraHits": 1395,
    "EffectType.LionHelm_ExtraBlockChance": 1232,
    "EffectType.LionHelm_ExtraBlockDamage": 1214,
    "EffectType.LionHelm_ExtraDmg": 1193,
    "EffectType.NanoscarabRepairProtocols": 1545,
    "EffectType.PathOfCommand_ExtraCrit": 1107,
    "EffectType.PathOfCommand_ExtraDmg": 1112,
    "EffectType.PhoenixGem_CanRevive": 1451,
    "EffectType.Pinned": 1065,
    "EffectType.PowerUp_Armor": 1138,
    "EffectType.ReanimationBeam_Revive": 1547,
    "EffectType.RitesOfMorkai": 1502,
    "EffectType.Stunned": 1162,
    "EntityType.Machine": 6,
    "StatType.BLOCK_CHANCE": 7,
    "StatType.BLOCK_DAMAGE": 8,
    "StatType.CRIT_CHANCE": 9,
    "StatType.EXTRA_HITS": 17,
    "StatType.EXTRA_MAX_DAMAGE": 25,
    "StatType.EXTRA_PIERCE_MELEE": 21,
    "StatType.EXTRA_PIERCE_RANGED": 22,
    "StatType.EXTRA_RANGE": 24,
    "StatType.FIXED_ARMOR": 16,
    "StatType.HEALTH": 5,
    "TriggeredAbilityType.AstartesBanner": 1106,
    "TriggeredAbilityType.DefenderOfTheGreaterGood": 1155,
    "TriggeredAbilityType.DrawFire": 1109,
    "TriggeredAbilityType.FinalJustice": 1024,
    "TriggeredAbilityType.FuelledByFury": 1251,
    "TriggeredAbilityType.FuryOfTheAncients": 1247,
    "TriggeredAbilityType.GeminaeSuperia": 1048,
    "TriggeredAbilityType.HarlequinsPanoply": 1187,
    "TriggeredAbilityType.KardiocoreGalvanus": 1457,
    "TriggeredAbilityType.ModifiedExoarmour": 1529,
    "TriggeredAbilityType.PhoenixGem": 1458,
    "TriggeredAbilityType.PrimarchOfTheFirstLegion": 1511,
    "TriggeredAbilityType.SaviorProtocols": 1120,
    "TriggeredAbilityType.StructuralAnalyser": 1143,
    "TriggeredAbilityType.WireweaveNet": 1111,
    "UnitFaction.Necrons": 7,
    "UnitFlag.ActiveAbilityUsed": 2,
    "UnitFlag.ArrivedAtFinalTile": 1,
    "UnitFlag.CanHealFullHealthUnits": 23,
    "UnitFlag.Dead": 6,
    "UnitFlag.CanRepairFullHealthUnits": 24,
    "UnitFlag.Fled": 9,
    "UnitFlag.ForceRangedAttack": 21,
    "UnitFlag.Moved": 0,
    "UnitFlag.NoActionAvailable": 4,
    "UnitFlag.Overkilled": 8,
    "UnitFlag.PreventOverkill": 19,
    "UnitFlag.Removed": 26,
    "UnitFlag.Resurrected": 14,
    "UnitFlag.Teleported": 12,
    "UnitFlag.TurnFinished": 3,
    "UnitFlag.TurnTerminated": 27,
    "UnitFlag.Untargetable": 17,
    "UnitTrait.IndirectFire": 1005,
    "UnitTrait.Ranged": 11,
    "UnitTrait.Steppable": 27,
    "UtilityType.Tile": 7,
}


# ───────────────────────────────────────────────── ETAGE 1 : RENUMEROTAGE (le cran du dessous)

def test_etage1_aucun_membre_ecrit_n_a_change_d_ordinal():
    """Chaque membre ecrit par la tranche vaut TOUJOURS l'ordinal mesure a la conversion.

    POURQUOI CE N'EST PAS REDONDANT AVEC `probe_313`. Le probe compare le MIRROR au BUILD : si le
    jeu renumerote `AbilityConstantType.range` de 22 a 23 et qu'on regenere le mirror, le probe
    REDEVIENT VERT -- alors que le site, lui, a silencieusement change de valeur. Ici l'ordinal est
    FIGE dans le test, donc il rougit, et il NOMME le membre coupable."""
    ecarts = []
    for cle, attendu in sorted(ORDINAUX.items()):
        try:
            v = int(_resoudre(cle))
        except (AttributeError, KeyError) as e:
            ecarts.append("%s : INTROUVABLE (%s)" % (cle, type(e).__name__))
            continue
        if v != attendu:
            ecarts.append("%s : ordinal %d, la tranche avait mesure %d" % (cle, v, attendu))
    assert not ecarts, ("RENUMEROTAGE (ou membre disparu) sur %d/%d membre(s) :\n  %s"
                        % (len(ecarts), len(ORDINAUX), "\n  ".join(ecarts)))


def test_etage1b_la_table_couvre_bien_la_tranche_livree():
    """Anti-degenerescence de l'etage 1 : une table videe le rendrait VERT sur rien.

    Les trois comptes sont ceux de la tranche livree. Ils ne se re-derivent pas ici -- c'est
    justement ce qui en fait un temoin, et pas un miroir de l'etat courant.

    141 et non 140 : le 141e est `UnitFlag.Dead`, arrive AU REBASE. `master` a ajoute `DEAD = 6` a
    `UnitFlagsComponent` pendant la tranche ; le laisser en ordinal nu aurait rouvert le gisement
    dans le fichier meme qui le ferme. Un conflit de rebase tranche par l'auteur, pas par le
    mergeur -- et celui-ci a AJOUTE une conversion, il n'en a pas repris une."""
    total = sum(sum(m.values()) for m in SITES.values())
    assert total == 141, "la tranche a converti 141 litteraux, la table en declare %d" % total
    assert len(ORDINAUX) == 102, "102 membres distincts attendus, %d declares" % len(ORDINAUX)
    assert len(SITES) == 50, "50 fichiers attendus, %d declares" % len(SITES)


# ──────────────────────────────────────────── ETAGE 2 : CLIQUET DE FORME (le gisement se rouvre)

def _occurrences(rel: str) -> dict[str, int]:
    out: dict[str, int] = {}
    arbre = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ENUMS:
            cle = "%s.%s" % (n.value.id, n.attr)
            out[cle] = out.get(cle, 0) + 1
    return out


def test_etage2_aucun_site_n_est_revenu_a_l_ordinal_nu():
    """Chaque fichier porte TOUJOURS au moins les occurrences que la tranche y a mises.

    C'est le cliquet : ce gisement est le seul que notre PROPRE cadence alimente. Un `X = 22`
    reecrit a la place de `X = AbilityConstantType.range` fait baisser le compte, et rougit."""
    manques = []
    for rel, attendus in sorted(SITES.items()):
        if not (ENGINE / rel).is_file():
            manques.append("%s : FICHIER ABSENT" % rel)
            continue
        vus = _occurrences(rel)
        for cle, n in sorted(attendus.items()):
            if vus.get(cle, 0) < n:
                manques.append("%s : %s vu %d fois, la tranche en avait mis %d"
                               % (rel, cle, vus.get(cle, 0), n))
    assert not manques, ("ORDINAL NU REVENU (ou site deplace hors du fichier) :\n  %s"
                         % "\n  ".join(manques))


# ──────────────────────────────────────────────────────────── ETAGE 3 : ACCESSEURS PUBLICS

def test_etage3_unit_flags_component_repond_pareil_par_ordinal_et_par_membre():
    """`UnitFlagsComponent` -- le chemin REEL des appelants, avec anti-degenerescence.

    Sans le volet « ces reponses DISCRIMINENT », l'egalite ordinal/membre tiendrait encore sur un
    composant qui repondrait `True` a tout."""
    from engine.runner.components import UnitFlagsComponent as UFC

    c = UFC([UnitFlag.Overkilled, UnitFlag.Fled])
    assert c.has(UnitFlag.Overkilled) and c.has(8)
    assert c.has(UnitFlag.Fled) and c.has(9)
    assert not c.has(UnitFlag.Untargetable) and not c.has(17)   # DISCRIMINE
    assert not c.has(UnitFlag.Teleported)

    assert int(UFC.OVERKILLED) == 8 and int(UFC.FLED) == 9
    assert int(UFC.NO_ACTION_AVAILABLE) == 4 and int(UFC.TURN_FINISHED) == 3
    # Deux noms LOCAUX au port, ordinaux NATIFS : `Resurrected` (14) et `TurnTerminated` (27).
    assert int(UFC.AMBUSH_CONSUMED) == 14
    assert int(UFC.TURN_FINISHED_FORCED) == 27
    noms = ("MOVED", "ARRIVED_AT_FINAL_TILE", "ACTIVE_ABILITY_USED", "TURN_FINISHED",
            "NO_ACTION_AVAILABLE", "FLED", "OVERKILLED", "TELEPORTED", "AMBUSH_CONSUMED",
            "PREVENT_OVERKILL", "REMOVED", "TURN_FINISHED_FORCED")
    assert len({int(getattr(UFC, n)) for n in noms}) == len(noms), \
        "deux constantes de flag se sont mises a designer le meme ordinal"


def test_etage3b_remove_turn_flags_traverse_les_membres_convertis():
    """`RemoveTurnFlags` lit six des constantes converties : le chemin le plus consommateur."""
    from engine.runner.components import UnitFlagsComponent as UFC

    c = UFC([UnitFlag.Moved, UnitFlag.Teleported, UnitFlag.ArrivedAtFinalTile,
             UnitFlag.ActiveAbilityUsed, UnitFlag.TurnFinished, UnitFlag.TurnTerminated,
             UnitFlag.NoActionAvailable, UnitFlag.Overkilled])
    retires = c.remove_turn_flags(include_no_action=True, new_activation=True)
    assert retires == {0, 1, 2, 3, 4, 12, 27}, retires
    # DISCRIMINE : `Overkilled` n'est PAS un flag de tour et doit survivre.
    assert c.has(UnitFlag.Overkilled) and not c.has(UnitFlag.TurnFinished)


def test_etage3c_les_index_de_variable_d_ability_sont_ceux_du_build():
    """`BaseTriggeredAbility.VAR_MIN_DMG` / `VAR_MAX_DMG` -- index de `GetVariableForLevel`."""
    from engine.entities.abilities.triggered_ability import BaseTriggeredAbility as BTA

    assert int(BTA.VAR_MIN_DMG) == 12 and int(BTA.VAR_MAX_DMG) == 13
    assert int(BTA.VAR_MIN_DMG) != int(BTA.VAR_MAX_DMG)          # DISCRIMINE
    # ... et ce sont bien les noms de variable que `ability_var` va chercher au gameconfig.
    assert AbilityVariableType(int(BTA.VAR_MIN_DMG)).name == "minDmg"
    assert AbilityVariableType(int(BTA.VAR_MAX_DMG)).name == "maxDmg"


# ────────────────────────────────────────────────────────────────────── ETAGE 4 : LE REGISTRE

MIRRORS_NEUFS = {
    "UnitFlag": ("engine/entities/unit_flag.py", "IdunBattle.Entities.Enum.UnitFlag"),
    "EntityType": ("engine/entities/entity_type.py", "IdunBattle.Entities.Enum.EntityType"),
    "AbilityConstantType": ("engine/entities/ability_constant_type.py",
                            "IdunBattle.Configuration.AbilityConstantType"),
    "AbilityVariableType": ("engine/entities/ability_variable_type.py",
                            "IdunBattle.Configuration.AbilityVariableType"),
}


def test_etage4_les_quatre_mirrors_neufs_sont_au_registre_de_probe_313():
    """Un mirror neuf hors registre en sort ORPHELIN -- quatre precedents, dont un `master` rouge.

    La cle d'appariement est le nom PLEIN : le build porte des homonymes courts (cinq `Corner`,
    deux `Edge`), et un appariement par nom court a deja rendu un mirror faux."""
    import probe_313_enum_mirror_bijection as P

    par_cls = {m.cls: m for m in P.REGISTRE}
    for cls, (rel, cle) in sorted(MIRRORS_NEUFS.items()):
        assert cls in par_cls, "%s n'est PAS au registre de probe_313" % cls
        m = par_cls[cls]
        assert m.rel == rel, "%s : registre dit %s, la tranche a ecrit %s" % (cls, m.rel, rel)
        assert m.cle == cle, "%s : cle %s, attendu le nom PLEIN %s" % (cls, m.cle, cle)
        assert m.garde, "%s doit etre SOUS GARDE (bijection exigee), pas en dette" % cls
        assert m.strict, "%s recopie les noms du jeu VERBATIM : strict attendu" % cls


def test_etage4b_les_mirrors_neufs_sont_en_bijection_avec_le_build():
    """La bijection elle-meme, rejouee ici pour que le test soit autoportant."""
    import probe_313_enum_mirror_bijection as P

    build = (P.REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    for cls, (_rel, cle) in sorted(MIRRORS_NEUFS.items()):
        natif = P.enum_natif(build, cle)
        assert natif, "%s : `enums.tsv` du build %s ne porte pas la cle %s" % (cls, build, cle)
        port = {int(m): m.name for m in ENUMS[cls]}
        assert set(natif) == set(port), (
            "%s : MANQUANTS=%s MORTS=%s"
            % (cls, sorted(set(natif) - set(port))[:8], sorted(set(port) - set(natif))[:8]))
        for v, noms in natif.items():
            assert port[v] in noms, ("%s : le port dit %d=%s, le build dit %s"
                                     % (cls, v, port[v], sorted(noms)))


# ───────────────────── ETAGE 5 : NON-DEGENERESCENCE AbilityConstantType / AbilityVariableType

def test_etage5_une_confusion_des_deux_index_serait_silencieuse_en_ORDINAL():
    """Le danger que la tranche eteint, MESURE -- et il n'est PAS celui qu'on croit.

    Premiere formulation, FAUSSE : « les ordinaux utilises des deux cotes doivent nommer autre
    chose ». Elle rendait un ensemble VIDE -- les 19 ordinaux `AbilityConstantType` et les 10
    `AbilityVariableType` de la tranche sont DISJOINTS. Un test vide serait passe pour vert.

    Le vrai danger est ailleurs, et il est pire : les **19/19** ordinaux `AbilityConstantType`
    utilises sont AUSSI des membres valides d'`AbilityVariableType` (et **10/10** dans l'autre
    sens). Une confusion `GetNumberConstant` / `GetVariableForLevel` n'aurait donc leve AUCUNE
    erreur -- elle aurait lu la mauvaise cle du gameconfig, en silence. C'est exactement ce que
    l'ecriture par NOM rend visible."""
    utilises_c = sorted({v for k, v in ORDINAUX.items() if k.startswith("AbilityConstantType.")})
    utilises_v = sorted({v for k, v in ORDINAUX.items() if k.startswith("AbilityVariableType.")})
    assert utilises_c and utilises_v, "la tranche utilise les deux enums"

    vac = {int(m) for m in AbilityConstantType}
    vav = {int(m) for m in AbilityVariableType}
    # (a) La confusion serait SILENCIEUSE : c'est ce qui justifie d'ecrire le NOM.
    assert all(v in vav for v in utilises_c), (
        "des ordinaux `AbilityConstantType` de la tranche ne sont plus valides cote "
        "`AbilityVariableType` : le risque a change de forme, relire l'attribution")
    assert all(v in vac for v in utilises_v)

    # (b) ... et le NOM, lui, DISCRIMINE. L'exception est NOMMEE, pas absorbee : `47` s'appelle
    # `nrOfHits` des DEUX cotes -- c'est la meme cle gameconfig, donc la confusion y serait sans
    # effet observable. Si d'autres apparaissent, la liste doit etre relue, pas elargie.
    HOMONYMES_CONNUS = {47}
    homonymes = {v for v in utilises_c + utilises_v
                 if AbilityConstantType(v).name == AbilityVariableType(v).name}
    assert homonymes == HOMONYMES_CONNUS, (
        "les ordinaux nommes PAREIL des deux cotes ont change : %s (connus : %s). Sur ceux-la le "
        "nom ne discrimine plus -- verifier au gameconfig que la cle est bien la meme."
        % (sorted(homonymes), sorted(HOMONYMES_CONNUS)))


# ─────────────────────────────────────────────────────────── ETAGE 6 : PLACEMENT DES MIRRORS

def _paquet_du_module(chemin: Path, racine: Path) -> str:
    """Le paquet PLEIN d'un fichier de l'arbre temoin (`engine.entities.effects.loki`).

    C'est ce qui permet de resoudre un import RELATIF : sans lui, `from ...X import` n'est
    qu'une chaine, et une mutation textuelle passe a cote."""
    parties = chemin.relative_to(racine).with_suffix("").as_posix().split("/")
    return ".".join(parties[:-1])


def _cible_pleine(noeud: "ast.ImportFrom", paquet: str) -> str:
    """Le module PLEIN designe par un `ImportFrom`, absolu ou relatif.

    `level = 0` : `noeud.module` est deja plein. `level = N` : on remonte de `N - 1` crans
    depuis `paquet` (regle Python : un point = le paquet courant), puis on colle `noeud.module`.
    Rend `""` si la remontee sort de l'arbre -- un import qu'on ne sait pas resoudre n'est jamais
    reecrit."""
    if not noeud.level:
        return noeud.module or ""
    parties = paquet.split(".") if paquet else []
    if noeud.level - 1 > len(parties):
        return ""
    base = parties[:len(parties) - (noeud.level - 1)]
    return ".".join(base + ([noeud.module] if noeud.module else []))


def _reecrire_vers_abilities(noeud: "ast.ImportFrom", paquet: str, nom: str) -> str:
    """Le `from <...>` d'apres-deplacement, en CONSERVANT la forme (relative ou absolue).

    Conserver la forme n'est pas cosmetique : reecrire un relatif en absolu changerait AUSSI
    l'ordre de resolution, donc la mutation ne mesurerait plus le seul deplacement. Si la
    nouvelle cible n'est pas atteignable au meme niveau relatif, on retombe sur l'absolu --
    toujours correct, et c'est alors DIT par la forme produite."""
    cible = "engine.entities.abilities." + nom
    if not noeud.level:
        return "from " + cible
    parties = paquet.split(".") if paquet else []
    base = ".".join(parties[:len(parties) - (noeud.level - 1)])
    if base and cible.startswith(base + "."):
        return "from " + "." * noeud.level + cible[len(base) + 1:]
    return "from " + cible


def test_etage6_les_deux_index_vivent_hors_du_paquet_abilities():
    """ETAGE 6 -- l'emplacement des deux mirrors : la CONTRAINTE A DISPARU, et cet etage l'ACTE.

    CE QU'IL GARDAIT. `entities/abilities/__init__.py` re-exportait `active_ability`, donc
    importer QUOI QUE CE SOIT de ce paquet executait cet `__init__`, qui tirait
    `services.damage_prediction` -> `ImportError` sur un module partiellement initialise
    (`cannot import name 'get_default_attack_hits'`). Les deux mirrors devaient donc vivre sous
    `entities/`, et cet etage refusait qu'on les range sous `entities/abilities/`. Il etait
    ecrit pour SE RETOURNER le jour ou le cycle disparaitrait. Ce jour est arrive.

    CE QUI L'A RETOURNE (#485-r1-r1) : la vidange des barils a vide cet `__init__.py`. Mesure,
    et non supposition -- l'etage DEPLACE reellement les deux mirrors dans une copie de l'arbre,
    reecrit leurs deux consommateurs `entities/effects/loki/*`, et importe : ca PASSE.

    ⚠ CE QU'IL GARDE MAINTENANT, ET POURQUOI CE N'EST PAS RIEN. L'emplacement sous `entities/`
    n'est plus IMPOSE, il est CHOISI -- on ne deplace pas 2 modules et leurs importeurs pour du
    rangement. Ce qui reste exigible est le FAIT qui l'a libere : ces mirrors sont des FEUILLES,
    et le paquet `entities.abilities` ne doit plus tirer la couche `services`. Si un
    re-export y revenait, l'import de la copie deplacee re-echouerait et cet etage rougirait --
    il faudrait alors retablir la prescription d'emplacement, pas le desarmer.
    """
    for cls in ("AbilityConstantType", "AbilityVariableType"):
        mod = ENUMS[cls].__module__
        assert mod.startswith("engine.entities."), mod

    init = ENGINE / "entities" / "abilities" / "__init__.py"
    assert init.is_file()
    tire = [n for n in ast.walk(ast.parse(init.read_text(encoding="utf-8")))
            if isinstance(n, ast.ImportFrom) and "active_ability" in (n.module or "")]
    assert not tire, (
        "`entities/abilities/__init__.py` re-importe `active_ability` : la contrainte "
        "d'emplacement de #270-r1-r1-r3 est de retour. Retablir le refus (les deux mirrors "
        "HORS de `entities/abilities/`) plutot que de desarmer cet etage.")

    # ── LA MESURE : le deplacement PASSE-T-IL vraiment ? On le fait, on ne le suppose pas. ────
    import os
    import shutil
    import subprocess
    import tempfile
    #: ⚠ ON REECRIT **TOUS** LES IMPORTEURS, pas une liste choisie. Une liste ecrite a la main
    #: rate celui qu'on n'a pas vu -- mesure : `entities/abilities/triggered_ability.py` importe
    #: `ability_variable_type`, et l'oublier faisait echouer la mutation par un
    #: `ModuleNotFoundError` de MONTAGE, que l'assertion aurait impute au cycle.
    #:
    #: ⚠⚠ ET LE MEME VICE EXISTE SUR L'AXE **FORME**, pas seulement sur l'axe FICHIER -- mesure
    #: du 2026-08-07, `master` ROUGE. La mutation ne connaissait QUE la forme ABSOLUE
    #: (`entities.<nom> import`), remplacee a la chaine. `entities/effects/loki/
    #: martial_inspiration.py` (arrive avec #509) ecrit `from ...ability_variable_type import` --
    #: forme RELATIVE, conforme a son voisinage (**34 des 35** fichiers de ce dossier importent
    #: en relatif). La mutation la laissait intacte, le module deplace n'existait plus a
    #: `engine/entities/`, et l'etage accusait « la contrainte de #270-r1-r1-r3 est revenue »
    #: alors que le cycle, lui, n'etait jamais revenu : un cliquet qui montre un ROUGE DE SON
    #: PROPRE OUTIL sous le libelle d'un fait de RE. Un `str.replace` sur une seule ecriture EST
    #: une liste choisie, deguisee.
    #:
    #: La reecriture passe donc par l'AST : on RESOUT chaque `ImportFrom` (niveau relatif
    #: compris) vers son module PLEIN, et on ne reecrit que ceux qui designent reellement
    #: `engine.entities.<nom>`. L'invariant qui remplace le seuil : REECRITS == RECENSES.
    with tempfile.TemporaryDirectory() as tmp:
        arbre = Path(tmp) / "arbre"
        shutil.copytree(ENGINE, arbre / "engine", ignore=shutil.ignore_patterns("__pycache__"))
        for f in ("gameconfig.py", "hexgeo.py"):
            if (PYDIR / f).exists():
                shutil.copy2(PYDIR / f, arbre / f)
        for nom in ("ability_constant_type", "ability_variable_type"):
            src = arbre / "engine" / "entities" / (nom + ".py")
            assert src.is_file(), src
            shutil.move(str(src), str(arbre / "engine" / "entities" / "abilities" / (nom + ".py")))
        recenses, reecrits, touches = [], [], []
        for p in sorted((arbre / "engine").rglob("*.py")):
            avant = p.read_text(encoding="utf-8")
            lignes = avant.splitlines(keepends=True)
            paquet = _paquet_du_module(p, arbre)
            change = False
            for noeud in ast.walk(ast.parse(avant)):
                if not isinstance(noeud, ast.ImportFrom):
                    continue
                cible = _cible_pleine(noeud, paquet)
                nom = cible.rpartition(".")[2]
                if cible not in ("engine.entities.ability_constant_type",
                                 "engine.entities.ability_variable_type"):
                    continue
                site = "%s:%d" % (p.relative_to(arbre).as_posix(), noeud.lineno)
                recenses.append(site)
                i = noeud.lineno - 1
                ecrit_avant = "from %s%s" % ("." * noeud.level, noeud.module or "")
                ecrit_apres = _reecrire_vers_abilities(noeud, paquet, nom)
                if ecrit_avant in lignes[i]:
                    lignes[i] = lignes[i].replace(ecrit_avant, ecrit_apres, 1)
                    reecrits.append(site)
                    change = True
            if change:
                p.write_text("".join(lignes), encoding="utf-8")
                touches.append(p.relative_to(arbre).as_posix())
        #: INVARIANT, pas seuil : tout site RECENSE a ete REECRIT. Une garde en seuil se degrade
        #: en silence -- c'est le `>= 10` qui laissait passer la forme relative.
        assert recenses and reecrits == recenses, (
            "la mutation n'a pas reecrit tous les importeurs recenses -- elle ne mesure donc PAS "
            "le deplacement reel. Non reecrits : %r"
            % [s for s in recenses if s not in reecrits])
        assert len(touches) >= 10, (
            "moins d'importeurs reecrits qu'attendu (%d) -- la mutation ne mesure peut-etre "
            "plus le deplacement reel : %r" % (len(touches), touches))
        env = dict(os.environ, PYTHONPATH=str(arbre) + os.pathsep + str(PYDIR))
        rendus = {}
        for m in ("engine.entities.abilities.ability_constant_type",
                  "engine.entities.abilities.ability_variable_type",
                  "engine.entities.effects.loki.ability_modifications",
                  "engine.entities.effects.loki.cursed_plague_bell",
                  "engine.entities.abilities.triggered_ability"):
            rendus[m] = subprocess.run([sys.executable, "-c", "import " + m],
                                       capture_output=True, text=True, cwd=str(arbre), env=env)
    casses = {m: r.stderr[-300:] for m, r in rendus.items() if r.returncode != 0}
    assert not casses, (
        "LE DEPLACEMENT SOUS `entities/abilities/` NE PASSE PLUS : la contrainte de "
        "#270-r1-r1-r3 est revenue. Retablir le refus d'emplacement dans cet etage ET dans le "
        "`CLAUDE.md`. %r" % casses)


# ────────────────────────── CE QUI RESTE EN LITTERAL, ET QUI A ETE VU (pas un oubli)

SCALAIRES_ASSUMES = (
    # (module, attribut, valeur) -- des QUANTITES, pas des designateurs. Le test verifie qu'ils
    # sont restes des `int` PURS : si l'un devenait un membre d'enum, c'est que quelqu'un a force
    # un nom sur un entier qui n'en designe aucun, et la case-doc doit etre relue.
    ("engine.battle_query", "DISTANCE_UNREACHABLE", 0x7FFFFFFF),
    ("engine.entities.formulas", "MIN_DISTANCE_EMPTY", 0x7FFFFFFF),
    ("engine.services.movement_query", "INT_MAX", 0x7FFFFFFF),
    ("engine.runner.prng", "_N", 624),
    ("engine.runner.prng", "_M", 397),
    ("engine.runner.prng", "_MATRIX_A", 0x9908B0DF),
    ("engine.entities.pathfinding.walk_pathfinder", "WEIGHT_BASE", 10),
    ("engine.entities.pathfinding.walk_pathfinder", "WEIGHT_BLOCKED", 10000),
    ("engine.utilities.heal", "W_HEAL", 100),
    ("engine.utilities.repair", "W_HP", 100),
    ("engine.services.static_battle_rules", "W_LASCANNON_PIERCE_BONUS", 50),
    ("engine.runner.abilities.behaviours.combat", "ChainLeftOverHitsAttackDamage.MAX_ITERATIONS",
     100),
    ("engine.services.ability_range", "WHOLE_BOARD_REACH", 1_000_000),
    # La VALEUR d'une constante gameconfig (30 %), PAS son index -- l'index est 42 (`chance`).
    ("engine.runner.operations.triggers.loki.fire", "FIRE_OF_ABSOLUTION_IGNITE_CHANCE", 30),
    # Deux constantes MORTES (aucun lecteur) dont les NOMS CONTREDISENT `StatType` (4 = ARMOR,
    # 5 = HEALTH). La tranche ne les convertit pas : figer l'un des deux sens serait choisir au
    # jugement. Residu #270-r1-r1-r3-r1.
    ("engine.services.damage_combat", "STAT_HEALTH", 4),
    ("engine.services.damage_combat", "STAT_ARMOR", 5),
)


def test_les_scalaires_assumes_sont_restes_des_entiers_purs():
    """« Hors regle, c'est un scalaire » est un RESULTAT -- ce test l'ecrit de facon EXECUTABLE."""
    fautes = []
    for mod, attr, attendu in sorted(SCALAIRES_ASSUMES):
        v = importlib.import_module(mod)
        for p in attr.split("."):          # `Classe.ATTRIBUT` accepte -- certains sont des
            v = getattr(v, p)              # attributs de CLASSE (`ChainLeftOverHits...`).
        if isinstance(v, Enum):
            fautes.append("%s.%s est devenu %r : un nom a ete force sur une QUANTITE"
                          % (mod, attr, v))
        elif int(v) != attendu:
            fautes.append("%s.%s vaut %d, la tranche avait mesure %d"
                          % (mod, attr, int(v), attendu))
    assert not fautes, "\n  ".join(fautes)


def test_les_deux_constantes_mortes_de_damage_combat_restent_sans_lecteur():
    """Le residu #270-r1-r1-r3-r1, sous cliquet : si un lecteur apparait, il faut TRANCHER.

    `STAT_HEALTH = 4` / `STAT_ARMOR = 5` contredisent `StatType` (4 = ARMOR, 5 = HEALTH). Tant que
    RIEN ne les lit, la contradiction est inerte et les laisser est le geste sur -- en figer un
    sens serait choisir au jugement. Le jour ou un site les lit, elle devient un BUG de valeur, et
    ce test le dit AVANT."""
    lecteurs = []
    for f in sorted(ENGINE.rglob("*.py")):
        if f.name == "damage_combat.py":
            continue
        texte = f.read_text(encoding="utf-8")
        for nom in ("STAT_HEALTH", "STAT_ARMOR"):
            if nom in texte:
                lecteurs.append("%s cite %s" % (f.relative_to(ENGINE).as_posix(), nom))
    assert not lecteurs, (
        "les constantes MORTES de `services/damage_combat.py` ont trouve un lecteur -- leur "
        "contradiction avec `StatType` (4 = ARMOR, 5 = HEALTH) n'est plus inerte, il faut la "
        "trancher au decompile (#270-r1-r1-r3-r1) :\n  " + "\n  ".join(lecteurs))
