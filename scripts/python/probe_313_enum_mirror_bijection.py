#!/usr/bin/env python3
"""#313 -- les mirrors `IntEnum` du moteur sont-ils en BIJECTION avec `enums.tsv` ?

LA QUESTION BINAIRE
-------------------
Pour chaque classe `IntEnum` du port qui recopie un enum natif : l'ensemble de ses membres
coincide-t-il EXACTEMENT avec celui de `data/symbols/<CURRENT>/frida/enums.tsv`, **dans les deux
sens** ? Le second sens est celui qu'on oublie, et c'est celui qui produit du code mort qui a
l'air vivant.

LES TROIS SENS, ET POURQUOI AUCUN CLIQUET NE LES COUVRAIT
----------------------------------------------------------
  MANQUANT   -- valeur du jeu absente du port. Le port ne SAIT PAS nommer ce que le jeu emet.
                C'est le trou de #313 : 8 ids de `TriggeredAbilityType` presents dans le build
                `rnca9r7q6c` et absents du mirror. La degradation est MUETTE tant qu'aucun
                playbook porte ne lit ces ids -- et c'est ce qui la rend durable.
  MORT       -- valeur du port absente du jeu. Aucune erreur, jamais : le jeu ne l'emet pas. Ce
                sont des membres qui ONT L'AIR vivants, qu'un solveur peut citer de bonne foi.
                #270 en avait compte 75 sur `ActiveAbilityType`.
  RENUMEROTE -- meme valeur, autre nom. Le pire : il resout, pointe ailleurs, rien ne proteste.

Le cliquet #283 (`probe_283_enum_ordinal_sweep.step_mirror`) ne verifie QUE le troisieme sens, et
seulement sur ses quatre enums : il compare `ref.get(membre) != valeur` pour les membres PRESENTS
dans le mirror -- un membre que le port n'a pas ne peut pas diverger, il est invisible. Le cliquet
#275 (`probe_275_enum_maps_drift`) fait bien les trois sens, mais sur `enum_maps.py` UNIQUEMENT :
son etape 4 range explicitement les mirrors `engine/entities/*_type.py` en " informatif, hors
perimetre ". Personne ne gardait donc les mirrors du MOTEUR -- ceux que le code executable lit.

CE QUE LA SONDE FAIT
--------------------
  Etape 1  DECOUVERTE : toute classe `IntEnum`/`IntFlag` sous `scripts/python/engine/` est classee
           -- APPARIEE (mapping explicite vers une cle de `enums.tsv`) ou HORS-MIRROR (justifiee).
           Une classe ni l'une ni l'autre est un ECART BLOQUANT : c'est par la que le trou se
           re-creuse. L'appariement est LU, jamais devine -- le nom court ne suffit pas
           (`UtilityType` vit dans `IdunBattle.Configuration`, pas `IdunBattle.Entities.Enum`), et
           un appariement au juge produirait un diff massif et FAUX.
  Etape 2  BIJECTION par mirror apparie : manquants / morts / renumerotes.
  Etape 3  REFERENCES QUALIFIEES : chaque `<Classe>.<membre>` ecrit dans du Python suivi doit
           (a) resoudre dans le mirror -- sinon `AttributeError` a l'execution -- et (b) pour un
           mirror STRICT, designer un membre que le BUILD COURANT connait encore. (b) est le
           garde-fou du piege #270 : c'est lui qui dit si un membre mort peut etre retire sans
           casser du code vivant, et lui qui rattrape une citation devenue fausse.
  Etape 4  PORTEURS (`--porteurs`) : le mirror n'est pas qu'une table, c'est un DICTIONNAIRE
           consomme par nom -- `triggered_ability_ids()` fait
           `TriggeredAbilityType.__members__.get(nom_gameconfig)` et jette silencieusement ce
           qu'il ne connait pas (`if m is not None`). Un membre manquant n'est donc pas inerte :
           il RETIRE des passifs du kit porte. L'etape confronte donc le mirror au gameconfig
           dans les deux sens -- quelles unites portent un membre MANQUANT (la file de portage),
           et quel membre MORT le gameconfig nommerait encore (aucun ne doit l'etre, sinon le
           retirer casserait la conversion).

  Etape 5  CONSOMMATEURS (#270-c) : le cran EN DESSOUS du mirror. Ce que le moteur lit, ce sont
           les DICTS indexes par nom/ordinal (`ABILITY_TRIGGERS`, `EFFECT_CLASSES`, ...). Une cle
           dont le nom a disparu du build ne LEVE pas -- `.get(cle, ())` rend `()`, et le passif
           n'est JAMAIS inscrit : meme degradation muette que le sens MANQUANT, un cran plus bas.
           #318 ne gardait ce cran que pour `EFFECT_CLASSES`. Trois verdicts, dont un NOMME sa
           cause : `EGAREE` = la cle n'est pas dans l'enum de sa voie mais existe dans un AUTRE
           enum natif -- signature du mauvais appariement, et non d'une faute de frappe.
  Etape 6  HOMONYMES (`--homonymes`) : INVENTAIRE, jamais une garde -- un homonyme est un fait du
           BUILD, pas une derive du port. Deux axes de cout inegal : un NOM partage a ordinal
           DIFFERENT rend un ordinal FAUX si on le lit du mauvais mirror (c'est ce que l'etape 5
           garde) ; un ORDINAL partage sous des noms DIFFERENTS rend une cle ENTIERE NON
           VERIFIABLE -- mesure sur `rnca9r7q6c` : `TriggeredAbilityType` partage 233 ordinaux
           avec `ActiveAbilityType`, dont **231 nomment autre chose**, et 458 avec `EffectType`,
           dont **454**. C'est la justification chiffree de « un entier qui DESIGNE passe par un
           enum » : le nom discrimine, l'ordinal non.

Sortie 0 = tous les mirrors SOUS GARDE sont bijectifs, toutes les references resolvent et toutes
les cles des dicts consommateurs sont nommables ; 1 sinon.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"/"python"))

import repo_read  # noqa: E402
import verdict_cache  # noqa: E402
from symbols_layout import build_dir, current_build  # noqa: E402

PY = REPO / "scripts"/"python"
ENGINE = PY / "engine"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 2 105 fichiers -- et le glob n'est PAS `scripts/python/**` : il lit aussi `lib/*.py`
#: A LA RACINE du depot, parce que son etape 3 derive son perimetre de `git ls-files *.py`.
#: Ecrire `scripts/python/**/*.py` aurait donc ete un declencheur trop ETROIT, invisible a
#: toute relecture du source -- c'est la mesure qui l'a montre.
DECLENCHEUR = {
    "chemins": ("**/*.py", "data/seed-bc.json",
                "scripts/cliquets-cache/probe_313_enum_mirror_bijection.tsv"),
    "build": True,
    "toujours": False,
    "raison": "Etapes 1/2 : les mirrors sous `engine/`, confrontes a "
              "`data/symbols/<CURRENT>/frida/enums.tsv` -- donc un changement de build renverse "
              "un verdict sans qu'une ligne du depot bouge (`build: True`, et il lit "
              "`data/symbols/CURRENT` pour savoir lequel). Etape 3 : TOUT le Python suivi du "
              "depot (`git ls-files *.py`), racine comprise. Etape 5 : les dicts consommateurs, "
              "sous `engine/`. Le fichier de cache est declare parce que le cliquet le LIT "
              "reellement ; son CONTEXTE, lui, ne porte pas le build -- les deux balayages "
              "caches sont build-independants (#486-r1) -- ce qui n'affaiblit pas ce "
              "`build: True`, qui vaut pour `enum_natif`, hors cache.",
}


# ------------------------------------------------- le CACHE de verdict par fichier (#486-r1)
#
# LOCALITE ETABLIE, cliquet par cliquet, AVANT de cacher quoi que ce soit.
#
#   CACHABLE   `intenums_du_moteur` et `references_qualifiees` : ce qu'un fichier rend ne depend
#              que de son PROPRE texte et de constantes du cliquet (`BASES_ENUM`, `PAR_CLS`).
#              Aucune variable ne circule d'un fichier a l'autre -- l'agregation (`out[cls] = rel`,
#              la concatenation des references) se rejoue integralement, hors cache.
#   PAS CACHE  `enum_natif`, `bijection`, les etapes 4 a 6. La premiere lit `enums.tsv` du BUILD
#              (une seule lecture, pas un balayage) ; les autres sont des verdicts GLOBAUX --
#              bijection entre deux ensembles, couverture d'un registre, homonymie inter-enums.
#              Aucun n'est local a un fichier et aucun ne coute.
#
# ⚠ CES DEUX BALAYAGES SONT BUILD-INDEPENDANTS, et le contexte ne porte donc PAS le build. Le
# build n'entre dans ce cliquet que par `enum_natif`, qui n'est pas cache : garder ces entrees
# a travers un changement de build n'est pas un raccourci, c'est la mesure de ce dont elles
# dependent reellement. (Les cliquets #477, eux, resolvent leurs citations CONTRE la table de
# slots : leur contexte la porte, et tout y manque au changement de build.)

_CACHE: verdict_cache.CacheCliquet | None = None


def cache() -> verdict_cache.CacheCliquet:
    global _CACHE
    if _CACHE is None:
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_313_enum_mirror_bijection",
            contexte=verdict_cache.sha_fichiers_texte(Path(__file__).resolve()))
    return _CACHE

# Attributs qui ne designent PAS un membre : l'API `Enum` elle-meme.
API_ENUM = {"name", "value", "_value_", "_name_", "_member_map_", "_missing_",
            "__members__", "__name__", "__doc__", "__class__", "mro"}


class Mirror:
    """Une entree du registre. Les champs sont LUS, jamais devines.

    strict  -- les NOMS du port doivent etre ceux du jeu. Faux pour `StatType`, dont le port
               reconventionne (`CRIT_CHANCE` pour `CriticalChance`, UPPER_CASE partout) : sa
               docstring le declare, et la garde y porte sur les VALEURS seules.
    garde   -- la bijection doit etre PARFAITE (le cliquet rougit sinon).
    dette   -- (manquants, morts, renumerotes) EXACTS pour un mirror hors garde. Le compte est
               fige et controle DANS LES DEUX SENS : il rougit si la dette s'aggrave, et il
               rougit aussi si elle est resorbee -- auquel cas la reponse est de passer le
               mirror SOUS GARDE, pas de rafraichir le nombre.
    """

    def __init__(self, cls, rel, cle, strict=True, garde=True, dette=None, raison=""):
        self.cls, self.rel, self.cle = cls, rel, cle
        self.strict, self.garde, self.dette, self.raison = strict, garde, dette, raison


# ---------------------------------------------------------------------------- le registre
REGISTRE: list[Mirror] = [
    # --- SOUS GARDE : bijection parfaite exigee.
    Mirror("ActiveAbilityType", "engine/entities/active_ability_type.py",
           "IdunBattle.Entities.Enum.ActiveAbilityType"),
    Mirror("TriggeredAbilityType", "engine/entities/triggered_ability_type.py",
           "IdunBattle.Entities.Enum.TriggeredAbilityType"),
    Mirror("DamageProfileType", "engine/entities/damage_profile_type.py",
           "IdunBattle.Entities.Enum.DamageProfileType"),
    Mirror("UnitTrait", "engine/entities/traits/unit_trait.py",
           "IdunBattle.Entities.Enum.UnitTrait"),
    Mirror("UnitFaction", "engine/entities/unit_faction.py",
           "IdunBattle.Entities.Enum.UnitFaction"),
    # #477-r35 -- selecteur d'equipe des surcharges a 3 args d'`AreFriends`/`IsFriend`. Inscrit
    # DANS LE MEME COMMIT que le mirror, comme l'exige le cliquet : un mirror neuf non apparie est
    # invisible de la bijection, et c'est par ce trou que quatre mirrors sont deja passes.
    Mirror("UnitTeamSelectionType", "engine/entities/unit_team_selection_type.py",
           "IdunBattle.Entities.Enum.UnitTeamSelectionType"),
    Mirror("DamageTrait", "engine/entities/damage_trait.py",
           "IdunBattle.Entities.Enum.DamageTrait"),
    # #1036 -- rarete d'unite EN BATAILLE. Inscrit DANS LE MEME COMMIT que le mirror.
    # ⚠ CINQ enums du build portent les MEMES six membres aux MEMES ordinaux (`idun.meta.Rarity`,
    # `IdunMetaLogic.UserProgress.Model.{Unit,Item,Upgrade,XpBook}Rarity`) : l'appariement ne peut
    # pas se faire au nom court, et une erreur y serait SILENCIEUSE EN ORDINAL. La cle est celle
    # que le COMBAT declare, LUE dans `frida/methods.tsv` au type du parametre `rarity` de
    # `IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity`, `...DSLTriggers.HasRarity` et
    # `IdunBattle.Entities.UnitExtensions.HasRarity` -- les trois disent `idun.meta.Rarity`.
    Mirror("Rarity", "engine/entities/rarity.py", "idun.meta.Rarity"),
    Mirror("EventTriggerType", "engine/dsl/event_trigger_type.py",
           "IdunBattle.DSL.EventTriggerType"),
    Mirror("StatType", "engine/entities/stats.py",
           "IdunBattle.Entities.Enum.StatType", strict=False,
           raison="port UPPER_CASE + abreviations (CRIT_CHANCE <- CriticalChance) : convention "
                  "declaree dans sa docstring ; la garde porte sur les VALEURS"),
    # #318 : les deux dernieres dettes declarees par #313 sont RESORBEES et passent sous garde.
    # `EffectType` (20 manquants, 73 morts, 2 RENUMEROTES) et `UtilityType` (15 manquants) ont ete
    # regeneres par `regen_enum_mirrors.py`. La forme qui comptait est le RENUMEROTE : 1563/1564
    # rendaient `DA_Hero6_Passive_1`/`_2`, placeholders absents des DEUX builds versionnes, la ou
    # le jeu dit `SpecialIssueCombiMelta_AdditionalHits` / `_ExtraDmg` -- il RESOLVAIT et pointait
    # ailleurs. Memes placeholders que ceux corriges dans `TriggeredAbilityType` par la case-219.
    Mirror("EffectType", "engine/entities/effect_type.py",
           "IdunBattle.Entities.Enum.EffectType"),
    Mirror("UtilityType", "engine/utilities/utility_type.py",
           "IdunBattle.Configuration.UtilityType"),
    # #427 : les deux mirrors que notre PROPRE cadence de portage avait laisses hors registre --
    # `PathfinderType` par #381-r5 (`051219fb`), `KillUnitStep` par #389-r2 (`163f62fb`). Aucun des
    # deux n'etait une categorie NOUVELLE : le registre savait deja les exprimer, personne ne les y
    # avait mis. La cle est LUE dans `enums.tsv`, jamais deduite du nom court (`KillUnitStep` vit
    # dans `IdunBattle.Operations`, pas `IdunBattle.Entities.Enum`).
    # #430 a re-trouve la MEME derive de son cote, en lancant ce cliquet depuis la banque
    # `scripts/ratchets.ps1` -- confirmation INDEPENDANTE que le trou n'etait pas dans la detection
    # mais dans le LANCEMENT. Son correctif prenait `KillUnitStep` en `strict=False` ; c'est celui
    # de #427 qui est retenu (renommer les membres du PORT en verbatim du jeu), parce que
    # `strict=False` relache les NOMS pour TOUT le mirror et rend muet le sens RENUMEROTE.
    Mirror("PathfinderType", "engine/entities/pathfinding/pathfinders.py",
           "IdunBattle.Entities.Pathfinding.PathfinderType"),
    # ⚠ CHEMIN CHANGE PAR #1088 : la feuille a quitte `runner/operations/remove_effects.py` pour
    # `entities/kill_unit_step.py`. Motif MESURE, pas cosmetique -- il lui fallait un second
    # lecteur, `entities/effects/base.py` (`BaseEffect.remove_on_kill_step`), que la cascade de
    # `remove_effects` traverse (177 modules charges, `base` compris) : l'importer de la aurait
    # ferme un cycle. Voie (1) de la doctrine (supprimer l'arete), pas voie (3) (differer).
    Mirror("KillUnitStep", "engine/entities/kill_unit_step.py",
           "IdunBattle.Operations.KillUnitStep"),
    # #270-r1 volet 2 : les 18 cles des trois tables de TRIANGLE (`battle_query._TRIANGLE_EVEN_COL`
    # / `_ODD_COL`, `selectors/geometry._TRIANGLE_SHAPE_DIRECTIONS`) designent le parametre
    # `direction` de `BattleQuery$$GetTilesInTriangleShape`, DECLARE `IdunBattleLogic.Utils.Hex.Corner`
    # dans `frida/methods.tsv`. La cle est LUE la, pas deduite du nom court -- il existe CINQ autres
    # enums nommes `Corner` dans le build (Unity/SimpleUI), tous a 3 ou 4 valeurs.
    Mirror("Corner", "engine/hex_corner.py", "IdunBattleLogic.Utils.Hex.Corner"),
    # `Edge` (#270-r1-r1) -- meme forme, meme piege : le type DECLARE du parametre `direction`
    # d'`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt`, LU dans `frida/methods.tsv`. Le nom
    # court aurait apparie `UnityEngine.RectTransform.Edge` (4 valeurs). Il entre au registre DANS
    # LE COMMIT QUI LUI DONNE UN MIRROR : ce gisement s'est rouvert TROIS fois par notre propre
    # cadence (`PathfinderType` #381-r5, `KillUnitStep` #389-r2, `DamageReason` #651).
    Mirror("Edge", "engine/hex_edge.py", "IdunBattle.Utils.Hex.Edge"),
    # ROUGE de `origin/master`, PAS de la tranche qui l'inscrit (#270-r1 volet 2, au rebase) :
    # `DamageReason` est entre sous `engine/` par `c06a112f` (PR #651) sans passer au registre, et
    # ce cliquet rougissait donc sur `origin/master`. C'est exactement le gisement que l'etape 1
    # existe pour fermer -- et la troisieme fois qu'il se rouvre par notre propre cadence, apres
    # `PathfinderType` (#381-r5) et `KillUnitStep` (#389-r2), tous deux repris par #427. La cle est
    # LUE dans `enums.tsv` : `IdunBattle.Operations`, pas `IdunBattle.Entities.Enum`.
    Mirror("DamageReason", "engine/entities/damage_reason.py",
           "IdunBattle.Operations.DamageReason"),
    # `DistanceType` (#889-r5) -- mirror NEUF, inscrit DANS LE COMMIT QUI LE CREE. Cle LUE dans
    # `enums.tsv`, et c'est aussi le type DECLARE du 4e parametre de
    # `IdunBattleLogic.Entities.DSLSelectors.Nearest(… distanceType : IdunBattle.Entities.Enum.
    # DistanceType …)` dans `frida/methods.tsv`. Deux valeurs seulement, mais elles commandent DEUX
    # metriques sans rapport (hex vs pathfinding) : ecrire `1` au site aurait choisi le pathfinding
    # en silence.
    Mirror("DistanceType", "engine/entities/distance_type.py",
           "IdunBattle.Entities.Enum.DistanceType"),
    # #270-r1-r1-r3 : QUATRE mirrors NEUFS, inscrits DANS LE COMMIT QUI LES CREE. Chacun est le
    # type DECLARE d'un parametre natif, LU dans `frida/methods.tsv` -- jamais deduit du nom
    # court, qui a deja apparie faux deux fois (`Corner`, `Edge`) :
    #   UnitFlag            <- `IdunBattle.Entities.UnitExtensions.HasFlag(flag : ...)`
    #   EntityType          <- `IdunBattle.Core.Entity..ctor(type : ...)`
    #   AbilityConstantType <- `AbilityConfiguration.GetNumberConstant(constantType : ...)`
    #   AbilityVariableType <- `AbilityConfiguration.GetVariableForLevel(variableType : ...)`
    # Les deux derniers partagent 141 ordinaux et nomment autre chose a valeur egale (22 =
    # `range` / `blockDmg_2`) : c'est l'ACCESSEUR appele au site qui tranche, pas l'ordinal.
    Mirror("UnitFlag", "engine/entities/unit_flag.py",
           "IdunBattle.Entities.Enum.UnitFlag"),
    Mirror("EntityType", "engine/entities/entity_type.py",
           "IdunBattle.Entities.Enum.EntityType"),
    # ⚠ Les deux vivent sous `engine/entities/`, PAS sous `engine/entities/abilities/` : y importer
    # quoi que ce soit execute l'`__init__.py` du sous-paquet, qui tire `active_ability` ->
    # `services.damage_prediction` -> `ImportError` sur module partiellement initialise. CYCLE
    # MESURE (meme forme que celui de `services/static_battle_rules.py`, #270-r1-r1). Un mirror
    # d'enum est une FEUILLE : le placer dans un paquet a `__init__` lourd le rend inimportable.
    Mirror("AbilityConstantType", "engine/entities/ability_constant_type.py",
           "IdunBattle.Configuration.AbilityConstantType"),
    Mirror("AbilityVariableType", "engine/entities/ability_variable_type.py",
           "IdunBattle.Configuration.AbilityVariableType"),
    # #477-r21-r2 volet B -- `AbilityPriority`, le critere de tri du cache d'activation
    # (`IdunBattleLogic.Core.Services.Caches.SortedTriggered$$CompareTo`). Il entre au registre DANS
    # LE COMMIT QUI LUI DONNE UN MIRROR. Sa cle est LUE : c'est le TYPE DE RETOUR declare des trois
    # `get_Priority` que `frida/methods.tsv` nomme, et son namespace est `IdunBattle.Entities.
    # Abilities` -- pas `IdunBattle.Entities.Enum`, ou le nom court aurait cherche en vain.
    # ⚠ LE MEME ENUM SERT A DEUX AXES QU'IL NE FAUT PAS CONFONDRE : le tier de PLAYBOOK (`IPlaybook`
    # slot 0, table `engine/playbook/noncomparable/_base.py::NATIVE_PRIORITY`, case-170) et la
    # priorite de CACHE (slot 7 d'une ability, slot 9 d'un effet). Deux slots, deux objets.
    Mirror("AbilityPriority", "engine/entities/ability_priority.py",
           "IdunBattle.Entities.Abilities.AbilityPriority"),
    # #477-r15 tranche A -- le vocabulaire du FLUX DE REPLAY. Les trois enums entrent au registre
    # DANS LE COMMIT QUI LEUR DONNE UN MIRROR, parce que ce gisement s'est deja rouvert QUATRE fois
    # par notre propre cadence (`PathfinderType`, `KillUnitStep`, `DamageReason`, `Edge`). Leur cle
    # est LUE dans `enums.tsv` : le namespace est `IdunBattle.Streams`, pas `IdunBattle.Entities.Enum`.
    # Ils sont le PERIMETRE d'un comparateur de flux : un membre qui glisse rendrait un flux emis
    # faux SANS erreur -- le nom ecrit apres `Group=` / `Action=` / `Tag=` EST le membre.
    # #287-r5 -- `HealType`, mirror NEUF, inscrit DANS LE COMMIT QUI LE CREE (cinquieme fois que ce
    # gisement se rouvre par notre propre cadence). Sa cle est le TYPE DECLARE du parametre
    # `healType` d'`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType`, LU dans
    # `frida/methods.tsv` -- la regle dynamique de 1175 `BloodChalice` appelle cette fonction avec
    # `NonMechanical`, et l'ordinal nu (`0`) est aussi un membre de `DamageReason`/`KillUnitStep`.
    Mirror("HealType", "engine/entities/heal_type.py",
           "IdunBattle.Entities.Enum.HealType"),
    # #524 -- `UnitSelectionType`, mirror NEUF, inscrit DANS LE COMMIT QUI LE CREE (sixieme fois que
    # ce gisement se rouvre par notre propre cadence). Sa cle est le TYPE DECLARE du 3e parametre
    # d'`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` et du 2e d'`IdunBattle.DSL.
    # TargetsSelector$$SelectUnit` -- pas le nom court, et le port en portait TROIS copies a la main
    # (`ONLY_TARGETABLE = 2` dans `runner/operations/behaviour.py`, `.../loki/narthecium.py`,
    # `.../loki/tainted_narthecium.py`), toutes converties par la meme tranche.
    Mirror("UnitSelectionType", "engine/entities/unit_selection_type.py",
           "IdunBattle.Entities.Enum.UnitSelectionType"),
    # #944 (residu #889-r5-r2) -- `InvalidTargetPolicy`, mirror NEUF, inscrit DANS LE COMMIT QUI LE
    # CREE. Sa cle est LUE dans `enums.tsv` et son namespace est `IdunBattle.Operations`, PAS
    # `IdunBattle.Entities.Enum` : le nom court aurait cherche en vain. C'est le type du champ
    # `+0x00` des `UseActiveAbilityBehaviourOptions`, identifie par la signature NOMMEE
    # d'`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` (6e parametre
    # `invalidTargetPolicy`), pas par son ordinal -- `2` est aussi un membre valide
    # d'`ExecutionType`, de `UnitSelectionType` et de six autres enums du build.
    Mirror("InvalidTargetPolicy", "engine/entities/invalid_target_policy.py",
           "IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy"),
    Mirror("GroupType", "engine/streams/group_type.py",
           "IdunBattle.Streams.GroupType"),
    Mirror("StepType", "engine/streams/step_type.py",
           "IdunBattle.Streams.StepType"),
    Mirror("TagKey", "engine/streams/tag_key.py",
           "IdunBattle.Streams.TagKey"),
    # `BEntityId` : un seul membre (`0=NO_ENTITY`), et c'est justement pour ce membre-la qu'il
    # existe -- c'est lui qui fait ecrire `Entity=NO_ENTITY` la ou toute autre valeur s'ecrit en
    # decimal. Sa cle vit dans `IdunBattle.Core`, pas dans `IdunBattle.Streams`.
    Mirror("BEntityId", "engine/streams/entity_id.py",
           "IdunBattle.Core.BEntityId"),
    # `SpawnSource` : le parametre `source` de `StreamHelper$$GetAddUnitTags`, recopie tel quel
    # dans `TagKey.Unit_SpawnSource`. Entre au registre avec son mirror (#477-r15 tranche B).
    Mirror("SpawnSource", "engine/entities/spawn_source.py",
           "IdunBattle.Entities.Enum.SpawnSource"),
    # `MachineOfWarPosition` : le fichier portait TROIS CONSTANTES LIBRES (`MOW_POSITION_*`)
    # depuis #93 -- un entier qui DESIGNE sans enum. Il a fallu le nommer pour emettre
    # `TagKey.MachinePosition` (#477-r15) ; les trois constantes en DERIVENT desormais.
    Mirror("MachineOfWarPosition", "engine/services/machine_of_war_position.py",
           "IdunBattle.Configuration.MachineOfWarPosition"),
    # #270-r4 : le mirror NEUF de la tranche, inscrit DANS LE COMMIT QUI LE CREE (cinquieme fois
    # que ce gisement s'ouvre par notre propre cadence -- `PathfinderType`, `KillUnitStep`,
    # `DamageReason`, `Edge`, puis les quatre de #270-r1-r1-r3). Cle LUE dans `frida/methods.tsv`
    # comme type DECLARE du dernier parametre de `DSLTriggers.HasEffect` -- c'est le seul canal
    # qui tranche, l'ordinal `6` etant un membre valide de dizaines d'autres enums du build.
    Mirror("EffectTargetType", "engine/entities/effect_target_type.py",
           "IdunBattle.Entities.Enum.EffectTargetType"),
    # #477-r24 : le mirror NEUF de la tranche, inscrit DANS LE COMMIT QUI LE CREE. Il n'existe
    # que parce que l'ordinal NU s'etait fait attribuer trois fois de suite au mauvais artefact :
    # `RunPhase(0xd)` -- jamais `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` -- a ete lu comme
    # un `GroupType` a trois crans du deroule #477, puis comme la
    # phase de `Core.Services.OperationProcessor$$ReviveUnit` par `revive.py`/`damage.py`. Cle LUE
    # dans `enums.tsv` -- le namespace est `IdunBattle.Core`, pas `IdunBattle.Streams`, alors meme
    # que le mirror vit sous `engine/streams/` (comme `BEntityId`, meme namespace natif).
    Mirror("PhaseType", "engine/streams/phase_type.py",
           "IdunBattle.Core.PhaseType"),
    # #477-r22 : le mirror NEUF de la tranche, inscrit DANS LE COMMIT QUI LE CREE. `TurnStage` est
    # le 1er argument de `Core.Services.OperationProcessor$$ContinueTurnPhase` et la valeur que
    # `IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage` fait avancer. Sa cle est
    # LUE dans `enums.tsv` (`IdunBattle.Entities.Enum`) ; le nom court seul serait ambigu --
    # l'ordinal `3` que le natif passe en dur est aussi un membre valide de `GroupType` ET de
    # `IdunBattle.Core.PhaseType`, l'enum que l'entree CI-DESSUS (#477-r24) vient precisement de
    # mirrorer apres TROIS attributions fausses du meme ordinal nu. Les deux entrees sont la MEME
    # lecon prise par deux bouts : un ordinal de phase et un ordinal de stage se ressemblent, et
    # seul le NOM les separe.
    Mirror("TurnStage", "engine/entities/turn_stage.py",
           "IdunBattle.Entities.Enum.TurnStage"),
    # #477-r21-r2 volet A : les DEUX mirrors NEUFS de la tranche, inscrits DANS LE COMMIT QUI LES
    # CREE. Ce sont les deux champs d'`IdunBattle.Operations.RefreshEffectOptions`, donc les deux
    # premiers arguments d'`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` -- leurs
    # types sont LUS dans `frida/methods.tsv` (`refreshTrigger:IdunBattle.Operations
    # .RefreshEffectTrigger, refreshType:IdunBattle.Operations.RefreshEffectType`), pas deduits.
    # Le namespace est `IdunBattle.Operations`, comme `KillUnitStep` et `DamageReason`, et les
    # mirrors vivent avec la garde qui les consomme (`engine/runner/operations/refresh_effects.py`,
    # meme convention que `KillUnitStep` dans `remove_effects.py`).
    # ⚠ Le nom court NE TRANCHE PAS : `enums.tsv` porte cinq autres enums dont le nom commence par
    # `Refresh` (`RefreshWithAdsResult`, `RefreshResult`, `RefreshAndLoginResult`,
    # `RefreshMerchantProductsResult`, `ReflectionProbeRefreshMode`), tous a 3 ou 6 valeurs -- dont
    # DEUX a exactement 3 valeurs, la cardinalite de `RefreshEffectType`.
    Mirror("RefreshEffectType", "engine/runner/operations/refresh_effects.py",
           "IdunBattle.Operations.RefreshEffectType"),
    Mirror("RefreshEffectTrigger", "engine/runner/operations/refresh_effects.py",
           "IdunBattle.Operations.RefreshEffectTrigger"),
    # #287-r11-r1-r1 : le mirror NEUF de la tranche, inscrit DANS LE COMMIT QUI LE CREE. C'est la
    # CLE du dictionnaire `BC.Victory.VictoryConditions` qu'interroge
    # `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` (litteral `1` du decompile =
    # `MainPlayerRoundLimitation`), donc le substrat du bit `CasterHas2TurnsLeft`.
    # ⚠ Le NAMESPACE est `idun.Shared.Battle`, pas `IdunBattle.Entities.Enum` : il est LU dans
    # `enums.tsv`, jamais deduit du nom court -- ce mirror vit d'ailleurs sous `engine/entities/`
    # comme les autres FEUILLES d'enum (un paquet a `__init__` lourd les rend inimportables).
    Mirror("VictoryConditionType", "engine/entities/victory_condition_type.py",
           "idun.Shared.Battle.VictoryConditionType"),
]

# HORS-MIRROR : classes `IntEnum`/`IntFlag` du moteur qui ne recopient AUCUN enum natif. Chacune
# porte sa raison -- c'est ce qui interdit d'y ranger un vrai mirror "parce qu'il derive".
HORS_MIRROR: dict[str, str] = {
    "StatPart": "decomposition maison d'un stat (Current/Initial/Modification/Override) -- "
                "l'enum natif homonyme n'existe pas dans enums.tsv",
    "TargetingRule": "IntFlag maison : les BITS du masque `TargetingOptions`, pas un enum natif",
}

PAR_CLS = {m.cls: m for m in REGISTRE}


# ------------------------------------------------------------------------- sources natives

def enum_natif(build: str, cle: str) -> dict[int, set[str]]:
    """{valeur: {noms}} depuis `data/symbols/<build>/frida/enums.tsv`.

    Un ENSEMBLE de noms : plusieurs membres partagent parfois une valeur (mesure sur
    `ActiveAbilityType` : 9999 porte `STRIPPED` ET `testAssetBundles`). Comparer a un nom UNIQUE
    ferait crier le cliquet sur une table pourtant juste."""
    p = build_dir(build) / "frida"/"enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(cle + "\t"):
            out: dict[int, set[str]] = {}
            for paire in ligne.rstrip("\n").split("\t", 1)[1].split(","):
                v, _, n = paire.partition("=")
                if n:
                    try:
                        out.setdefault(int(v), set()).add(n)
                    except ValueError:
                        pass
            return out
    raise SystemExit("cle absente de enums.tsv : %s" % cle)


# --------------------------------------------------------------------------------- le depot

def _echappe(nom: str) -> str:
    """`None_` -> `None` : le mirror echappe le mot-clef Python, le jeu ne l'echappe pas."""
    return nom[:-1] if nom == "None_" else nom


#: Les bases qui font d'une `class` un ENUM aux yeux du detecteur. Elargi par #427 : la version
#: d'origine ne connaissait que `IntEnum`/`IntFlag`, si bien qu'un mirror ecrit `class X(int, Enum)`
#: -- forme strictement equivalente, et idiomatique -- n'etait vu par PERSONNE : ni orpheline, ni
#: apparie, invisible. C'est le mode de defaillance meme que l'etape 1 existe pour fermer (« une
#: absence ne se remarque pas »), reintroduit un cran plus bas. Aujourd'hui aucune classe du depot
#: n'emprunte ces formes (mesure #427 : 13 `IntEnum` + 1 `IntFlag`, rien d'autre) -- l'elargissement
#: ne change donc aucun verdict, il ferme une porte AVANT qu'on la franchisse.
#: RESIDU NOMME, hors de portee d'un AST par fichier : un alias d'import
#: (`from enum import IntEnum as IE` puis `class X(IE)`) reste invisible. Le resoudre demanderait de
#: suivre les imports ; le cas ne s'est jamais produit et le dire vaut mieux que l'inventer.
BASES_ENUM = {"Enum", "IntEnum", "IntFlag", "Flag", "StrEnum", "ReprEnum"}


def classes_intenum(tree: ast.Module) -> dict[str, dict[int, set[str]]]:
    """{classe: {valeur: {noms}}} pour chaque classe d'ENUM d'un arbre (cf. `BASES_ENUM`).

    Lu par AST, pas par regex : un `IntEnum` declare des ALIAS (deux noms, meme valeur), et une
    table `{valeur: nom}` en ecraserait un en silence -- exactement le motif qu'on traque."""
    out: dict[str, dict[int, set[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        bases |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
        if not (bases & BASES_ENUM):
            continue
        membres: dict[int, set[str]] = {}
        for st in node.body:
            if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                    and isinstance(st.targets[0], ast.Name)):
                continue
            v, nom = st.value, _echappe(st.targets[0].id)
            if isinstance(v, ast.Constant) and isinstance(v.value, int) \
                    and not isinstance(v.value, bool):
                membres.setdefault(v.value, set()).add(nom)
            elif isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub) \
                    and isinstance(v.operand, ast.Constant) \
                    and isinstance(v.operand.value, int):
                membres.setdefault(-v.operand.value, set()).add(nom)
        if membres:
            out[node.name] = membres
    return out


def membres_mirror(rel: str, cls: str) -> dict[int, set[str]]:
    p = PY / rel
    if not p.is_file():
        return {}
    return classes_intenum(ast.parse(p.read_text(encoding="utf-8"), filename=rel)).get(cls, {})


def intenums_du_moteur() -> dict[str, str]:
    """{classe: chemin relatif a scripts/python} -- TOUTE classe d'enum sous `engine/`.

    C'est l'etape qui empeche le trou de se re-creuser : un mirror ajoute demain sans entrer au
    registre est signale, au lieu d'echapper silencieusement a la garde. Elle a fait son travail --
    `PathfinderType` (#381-r5) et `KillUnitStep` (#389-r2) rougissaient bien sur `origin/master`
    (#427). Ce qui a manque n'est pas la detection : c'est que personne ne LANCE ce cliquet.

    Le pre-filtre textuel est co-extensif avec le detecteur, pas plus laxe : toute base de
    `BASES_ENUM` contient `Enum` ou `Flag`, et `classes_intenum` ne reconnait une base que par son
    token litteral -- ce que le filtre laisse passer est donc exactement ce que le parse peut
    voir."""
    out: dict[str, str] = {}
    # Lecture PARALLELE (#457-r6) : l'OUVERTURE pese ~7 ms par fichier sous `scripts/`
    # (filtre systeme sur les extensions executables), devant le parse. Ordre inchange.
    fichiers = sorted(ENGINE.rglob("*.py"))
    cch = cache()
    for p, texte in zip(fichiers, repo_read.read_texts(fichiers)):
        rel = p.relative_to(PY).as_posix()
        if texte is None:
            continue
        #: ⚠ LE PRE-FILTRE RESTE JOUE A CHAQUE RUN, hors cache : il coute une recherche de
        #: sous-chaine sur un texte deja lu, et cacher ce qu'il ecarte n'economiserait rien.
        if "Enum" not in texte and "Flag" not in texte:
            continue
        for cls in cch.contribution(rel, "intenums", verdict_cache.sha_texte(texte),
                                    lambda t=texte, r=rel: _classes_du_fichier(t, r)):
            out[cls] = rel
    return out


def _classes_du_fichier(texte: str, rel: str) -> list[str]:
    """Les noms de classes d'enum d'UN fichier -- verdict LOCAL, donc cachable (#486-r1).

    Un fichier au parse impossible ne contribue rien : c'est l'ancien `except SyntaxError:
    continue`, deplace ici sans changer ce qu'il ecarte.
    """
    try:
        tree = ast.parse(texte, filename=rel)
    except SyntaxError:
        return []
    return list(classes_intenum(tree))


# ------------------------------------------------------------------------------ le calcul

def bijection(port: dict[int, set[str]], jeu: dict[int, set[str]],
              strict: bool = True) -> tuple[list, list, list]:
    """(manquants, morts, renumerotes) -- LE calcul du cliquet, isole pour qu'un test puisse le
    nourrir de tables truquees et verifier qu'il MORD.

    manquants   : [(valeur, noms du jeu)]   -- le jeu les emet, le port ne sait pas les nommer
    morts       : [(valeur, noms du port)]  -- le port les cite, le jeu ne les emet plus
    renumerotes : [(valeur, nom du port, noms du jeu)] -- meme valeur, le port nomme AUTRE CHOSE

    Un ALIAS n'est PAS une derive : le port n'a pas besoin de porter tous les noms d'une valeur
    (le jeu donne 9999 = {STRIPPED, testAssetBundles}), il doit seulement n'en porter AUCUN de
    faux -- d'ou l'inclusion `noms_port <= noms_jeu`, jamais l'egalite.

    `strict=False` : la garde porte sur les VALEURS seules (mirror qui reconventionne ses noms).
    """
    manquants = [(v, sorted(jeu[v])) for v in sorted(set(jeu) - set(port))]
    morts = [(v, sorted(port[v])) for v in sorted(set(port) - set(jeu))]
    renum = ([(v, n, sorted(jeu[v])) for v in sorted(set(port) & set(jeu))
              for n in sorted(port[v]) if n not in jeu[v]] if strict else [])
    return manquants, morts, renum


# ---------------------------------------------------------- etape 3 : references qualifiees

def fichiers_python_suivis() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.py"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [x for x in out.splitlines() if x.endswith(".py")]


def references_qualifiees() -> list[tuple[str, int, str, str]]:
    """[(fichier, ligne, classe, membre)] -- chaque `<Classe>.<membre>` ecrit dans du Python suivi.

    AST, pas regex : les exemples de docstring (`TriggeredAbilityType.X` dans
    `audit_passive_ability_coverage.py`) sont du TEXTE, pas du code -- les compter ferait un faux
    positif permanent, et les exclure a la main serait une allowlist de plus a maintenir.

    PRE-FILTRE TEXTUEL, et pourquoi il ne change RIEN au resultat (#427) : le motif cherche est un
    `ast.Attribute` dont la base est un `ast.Name` d'`id` egal a un nom de classe du registre. Un
    `ast.Name` de cet `id` ne peut PAS exister si le token n'apparait pas litteralement dans la
    source -- l'inclusion `nom in texte` est donc une sur-approximation EXACTE du parse, jamais une
    allowlist. Mesure du 2026-08-01, resultat confronte a l'implementation d'avant : 1461 fichiers
    suivis, **712** en citent une (les mirrors les plus larges -- `StatType`, `EffectType`,
    `UnitTrait` -- sont partout), 38,2 s -> 31,5 s, **1795 references identiques des deux cotes**.
    Le gain est donc MODESTE : le poste de cout de cette etape n'est pas le nombre de fichiers
    parses, c'est le parse lui-meme sur la moitie du depot qui cite un enum."""
    out = []
    # Lecture PARALLELE (#457-r6), meme ordre : `read_texts` rend une liste ALIGNEE.
    rels = [r for r in fichiers_python_suivis() if (REPO / r).is_file()]
    cch = cache()
    for rel, texte in zip(rels, repo_read.read_texts([REPO / r for r in rels])):
        if texte is None:
            continue
        #: ⚠ LE PRE-FILTRE RESTE JOUE A CHAQUE RUN, hors cache -- cf. la docstring ci-dessus :
        #: c'est une sur-approximation EXACTE du parse, pas une allowlist, et elle coute une
        #: recherche de sous-chaine sur un texte deja lu.
        if not any(cls in texte for cls in PAR_CLS):
            continue
        out += [tuple(x) for x in
                cch.contribution(rel, "refs", verdict_cache.sha_texte(texte),
                                 lambda t=texte, r=rel: _references_du_fichier(t, r))]
    return out


def _references_du_fichier(texte: str, rel: str) -> list[tuple[str, int, str, str]]:
    """Les `<Classe>.<membre>` d'UN fichier -- verdict LOCAL, donc cachable (#486-r1).

    Un fichier au parse impossible ne contribue rien : c'est l'ancien `except SyntaxError:
    continue`, deplace ici sans changer ce qu'il ecarte.
    """
    try:
        tree = ast.parse(texte, filename=rel)
    except SyntaxError:
        return []
    return [(rel, node.lineno, node.value.id, node.attr) for node in ast.walk(tree)
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in PAR_CLS and node.attr not in API_ENUM
                and not node.attr.startswith("_"))]


def references_cassees(build: str, refs: list | None = None) -> tuple[list, list]:
    """(introuvables, mortes).

    introuvables : la reference ne resout meme pas dans le mirror -> `AttributeError` a
                   l'execution. C'est ce qui arriverait si on retirait un membre encore cite.
    mortes       : elle resout dans le mirror, mais le BUILD COURANT ne connait plus ce nom ->
                   du code qui a l'air vivant et ne peut plus rien matcher. Piege #270.

    `refs` -- le balayage AST de l'etape 3, deja fait. C'est le POSTE DE COUT de la sonde :
    712 des 1461 fichiers Python suivis y sont parses, ~32-52 s selon la charge machine mesurees
    le 2026-08-01 (contre ~6-11 s pour l'etape 1 et 0,5 s pour l'etape 2). Le rapport le calculait
    DEUX fois -- une ici, une pour afficher le total -- ce qui doublait le mur : 159,2 s avant,
    68,9 s apres, sur la meme machine et la meme minute (#427).
    """
    noms_port = {m.cls: {n for ns in membres_mirror(m.rel, m.cls).values() for n in ns}
                 for m in REGISTRE}
    noms_jeu = {m.cls: {n for ns in enum_natif(build, m.cle).values() for n in ns}
                for m in REGISTRE}
    introuvables, mortes = [], []
    for rel, k, cls, membre in (references_qualifiees() if refs is None else refs):
        if _echappe(membre) not in noms_port[cls]:
            introuvables.append((rel, k, cls, membre))
        elif PAR_CLS[cls].strict and _echappe(membre) not in noms_jeu[cls]:
            mortes.append((rel, k, cls, membre))
    return introuvables, mortes


# -------------------------------------------------------------------- etape 4 : porteurs

# Quelle liste du gameconfig alimente quel mirror. `TriggeredAbilityType` <- `passiveAbilities`
# (le namespace natif est `Abilities.Triggered.Loki.*Ability`), `ActiveAbilityType` <-
# `activeAbilities`. Les autres mirrors ne sont pas nommes par le gameconfig.
LISTE_GAMECONFIG = {
    "TriggeredAbilityType": "passiveAbilities",
    "ActiveAbilityType": "activeAbilities",
}


def porteurs_par_nom(champ: str) -> dict[str, list[tuple[str, str]]]:
    """{nom d'ability: [(unite, kind)]} depuis le gameconfig du build courant.

    `kind` vient de `gameconfig.unit()` : lineup / npc / summons. Il VENTILE, il ne TRANCHE pas --
    la gate hero/MoW est `rl_duel build --list-pool`, jamais `kind == lineup` (qui ment). Un
    porteur `summons` est confrontable malgre son absence du pool (on spawne son summoner)."""
    import gameconfig as GC
    idx = GC._index()
    out: dict[str, list[tuple[str, str]]] = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(kind) or {}).items():
            for nom in (u.get(champ) or []):
                out.setdefault(nom, []).append((uid, kind))
    return out


def etape_porteurs(build: str) -> int:
    print("ETAPE 4 -- PORTEURS (gameconfig du build %s)" % build)
    rouge = 0
    for m in REGISTRE:
        champ = LISTE_GAMECONFIG.get(m.cls)
        if champ is None:
            continue
        port = membres_mirror(m.rel, m.cls)
        jeu = enum_natif(build, m.cle)
        manquants, morts, _ = bijection(port, jeu, m.strict)
        pn = porteurs_par_nom(champ)
        print("  %s <- gameconfig.%s" % (m.cls, champ))
        for v, ns in manquants:
            for n in ns:
                ps = pn.get(n) or []
                kinds = sorted({k for _, k in ps})
                print("    MANQUANT %-6d %-44s porteurs=%d %s"
                      % (v, n, len(ps),
                         ("[%s] %s" % (",".join(kinds),
                                       ", ".join(u for u, _ in ps[:6])))
                         if ps else "-- AUCUN porteur au gameconfig"))
        nommes = [(v, n) for v, ns in morts for n in ns if n in pn]
        print("    membres MORTS encore nommes par le gameconfig : %d %s"
              % (len(nommes), nommes[:8] if nommes else ""))
        rouge += len(nommes)
    print("")
    return rouge


# ------------------------------------- etape 5 : les DICTS CONSOMMATEURS indexes par la cle

class Consommateur:
    """Un dict du PORT dont les CLES designent des membres d'un enum natif.

    `par` -- "nom" : la cle est le nom du membre (str) ; "valeur" : son ordinal (int).

    L'appariement `cls` est LU dans le code du consommateur (commentaire d'en-tete du registre ET
    site de consommation), jamais deduit du fait qu'une cle "resout". C'est necessaire, et la
    mesure le dit : `TriggeredAbilityType` et `EffectType` partagent 458 ordinaux sur 476, dont
    454 nomment AUTRE CHOSE -- une cle ENTIERE qui resout ne prouve donc a peu pres rien.
    """

    def __init__(self, nom, mod, attr, cls, par="nom", raison="", noms_sup=None):
        self.nom, self.mod, self.attr = nom, mod, attr
        # `noms_sup` : callable -> set de noms LEGITIMES qui ne sont dans aucun enum du build.
        # Un seul cas, MESURE (#270-r2) : les abilities DERIVEES D'UN TRAIT. Le natif les cree par
        # `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` ->
        # `StaticBattleRules.Trait$$GetTriggeredAbility` ; le port les NOMME dans les valeurs de
        # `TRAIT_DERIVED_ABILITIES`, et ce nom n'est pas toujours celui du membre d'enum
        # (`Diminutive` 0x43f est nomme `DiminutiveAbility` cote port, d'apres la CLASSE native
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility` ; `ShadowInTheWarp`
        # 0x424 est nomme comme son TRAIT). Ce sont donc des cles legitimes, mais d'un espace de
        # noms INTERNE au port -- les compter INTROUVABLES aurait accuse deux entrees justes.
        self.noms_sup = noms_sup
        # `cls` peut etre un TUPLE (#270-r2). Deux registres reels sont alimentes par la boucle
        # `abilities = activeAbilities + passiveAbilities` de `spawn.py::_seed_ability_owner_effects`,
        # donc leurs cles vivent dans DEUX enums -- et le CLAUDE.md le dit : la VOIE ne dit pas
        # l'enum (`ShroudPsalm` en `passiveAbilities` est un `ActiveAbilityType` ; `Maugetar` en
        # `activeAbilities` est un `TriggeredAbilityType`). Forcer un enum unique aurait fabrique
        # des EGAREES sur des cles justes.
        self.classes = (cls,) if isinstance(cls, str) else tuple(cls)
        self.cls, self.par, self.raison = cls, par, raison


#: Les dicts que le moteur CONSOMME par cle, et l'enum qui nomme cette cle.
#:
#: POURQUOI CETTE ETAPE (le pendant #270-c de l'etape 4). Un mirror bijectif ne suffit pas : ce que
#: le moteur lit reellement, ce sont ces dicts. Une cle dont le nom a disparu du build ne LEVE pas
#: -- `ABILITY_TRIGGERS.get(pa, ())` rend simplement `()`, et le passif n'est JAMAIS inscrit. C'est
#: la meme degradation muette que le sens MANQUANT du mirror, un cran plus bas, et
#: `test_le_registre_EFFECT_CLASSES_resout_entierement_dans_le_mirror` (#318) ne la gardait que
#: pour `EFFECT_CLASSES`.
#:
#: Les registres de `triggers.dispatch` couvrent les SIX CHEMINS DE REGISTRATION que
#: `collect_triggered_abilities` (`dispatch/core.py`) parcourt : trait, `passiveAbilities`,
#: `activeAbilities` (derivees), `relicAbilities` + `TertiaryAbility`, l'effet, et -- depuis
#: #521-r1 -- la triggered-ability HELPER d'une active (`GetPassiveHelperAbility`).
CONSOMMATEURS: list[Consommateur] = [
    # `dispatch/core.py` : `for pa in passives: ABILITY_TRIGGERS.get(pa, ())`, ou `passives` vient
    # du canal mesure `UnitContext.passive_abilities` ou, a defaut, de `gameconfig.passiveAbilities`.
    Consommateur("ABILITY_TRIGGERS", "engine.runner.operations.triggers.dispatch.registry",
                 "ABILITY_TRIGGERS", "TriggeredAbilityType",
                 raison="voie passiveAbilities -- 210 des 211 noms du gameconfig sont des "
                        "TriggeredAbilityType (l'exception est ShroudPsalm, cf. --homonymes)"),
    # Meme fichier : `for aa in gu['activeAbilities']: ACTIVE_ABILITY_TRIGGERS.get(aa, ())` --
    # mirror de `StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`.
    Consommateur("ACTIVE_ABILITY_TRIGGERS", "engine.runner.operations.triggers.dispatch.registry",
                 "ACTIVE_ABILITY_TRIGGERS", "ActiveAbilityType",
                 raison="voie activeAbilities -- la CLE est l'active, la VALEUR la derivee"),
    # Meme fichier, SIXIEME chemin (#521-r1) : `for aa in config_actives:
    # PASSIVE_HELPER_ABILITY_TRIGGERS.get(aa, ())`. La cle est de la MEME nature que celle du
    # voisin ci-dessus (un nom d'ability ACTIVE), mais le dict natif est AUTRE --
    # `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$
    # GetPassiveHelperAbility` (`<statics>+0x78`), monte par `IdunBattle.Entities.Factories.
    # UnitFactory$$AddActiveAbility`. Meme cran du dessous que ses cinq voisins : un nom disparu
    # rendrait `()` sans erreur, et le trigger ne serait inscrit sur personne.
    Consommateur("PASSIVE_HELPER_ABILITY_TRIGGERS",
                 "engine.runner.operations.triggers.dispatch.registry",
                 "PASSIVE_HELPER_ABILITY_TRIGGERS", "ActiveAbilityType",
                 raison="voie passive-helper -- la CLE est l'active, la VALEUR le helper"),
    # La cle est une relique, mais l'enum reste `TriggeredAbilityType` : le natif la monte par
    # `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)` (branche TERTIAIRE
    # d'`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`), et le registre le dit
    # deja de son cote (`DawnBlade` = `TriggeredAbilityType` 0x5dd = 1501). MESURE : les 25 noms de
    # `relicAbilities` du gameconfig sont 25/25 dans `TriggeredAbilityType`, 0/25 dans `ActiveAbilityType`.
    Consommateur("RELIC_ABILITY_TRIGGERS", "engine.runner.operations.triggers.dispatch.registry",
                 "RELIC_ABILITY_TRIGGERS", "TriggeredAbilityType",
                 raison="voies relicAbilities + UnitConfiguration.TertiaryAbility"),
    Consommateur("TRAIT_TRIGGERS", "engine.runner.operations.triggers.dispatch.registry",
                 "TRAIT_TRIGGERS", "UnitTrait", raison="voie traits"),
    Consommateur("EFFECT_CLASSES", "engine.entities.effects.factory", "EFFECT_CLASSES",
                 "EffectType", raison="EffectFactory, consomme PAR NOM (#318)"),
    # --- indexes par VALEUR. La garde y est BEAUCOUP plus faible, et c'est dit plutot que maquille :
    # cf. `--homonymes`, section ORDINAUX.
    Consommateur("CUSTOM_TRIGGERED_ABILITIES", "engine.runner.operations.triggers.dispatch.registry",
                 "CUSTOM_TRIGGERED_ABILITIES", "TriggeredAbilityType", par="valeur",
                 raison="drain de state.pending_triggered_abilities (noeud TriggerAbilityDelayed)"),
    Consommateur("EFFECT_TRIGGERS", "engine.runner.operations.triggers.dispatch.registry",
                 "EFFECT_TRIGGERS", "EffectType", par="valeur",
                 raison="effectType -> effet-trigger(s)"),
    # --- #270-r2 : les QUATRE registres de `effects/factory.py` que la liste ECRITE avait omis.
    # Ils ne sont pas hypothetiques (<< un huitieme dict ajoute demain >>) : ils EXISTAIENT deja,
    # avec la meme lecture `.get(<nom>, [])`, donc la meme degradation muette. C'est l'etape 7 qui
    # les a trouves, en partitionnant les FOYERS au lieu d'enumerer les dicts connus.
    # `spawn.py::_seed_trait_owner_effects` : `TRAIT_OWNER_EFFECTS.get(trait_name, [])`.
    Consommateur("TRAIT_OWNER_EFFECTS", "engine.entities.effects.factory",
                 "TRAIT_OWNER_EFFECTS", "UnitTrait",
                 raison="voie traits -- owner-effect pose par le trait a l'init"),
    # `spawn.py::_seed_derived_ability_owner_effects` : `TRAIT_DERIVED_ABILITIES.get(trait_name, [])`.
    Consommateur("TRAIT_DERIVED_ABILITIES", "engine.entities.effects.factory",
                 "TRAIT_DERIVED_ABILITIES", "UnitTrait",
                 raison="voie traits -- la CLE est le trait, la VALEUR l'ability derivee"),
    # DEUX enums, et c'est LU : `spawn.py::_seed_ability_owner_effects` boucle sur
    # `activeAbilities + passiveAbilities` -- la voie ne dit donc pas l'enum, et deux inversions
    # connues existent (`ShroudPsalm`, `Maugetar`).
    Consommateur("ABILITY_INIT_OWNER_EFFECTS", "engine.entities.effects.factory",
                 "ABILITY_INIT_OWNER_EFFECTS", ("ActiveAbilityType", "TriggeredAbilityType"),
                 raison="`<Ability>.CreateBehaviour` -> `AddEffect(owner)` a l'init",
                 noms_sup=lambda: abilities_derivees_de_trait()),
    Consommateur("ABILITY_OWNER_EFFECTS", "engine.entities.effects.factory",
                 "ABILITY_OWNER_EFFECTS", ("ActiveAbilityType", "TriggeredAbilityType"),
                 raison="`StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility`",
                 noms_sup=lambda: abilities_derivees_de_trait()),
    # PENDANT EXACT du precedent sur l'autre canal d'init : meme trigger natif
    # (`OnOwnerSpecificAbilityInit(<this.AbilityType>)`), meme boucle consommatrice
    # (`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute`), meme moment -- seule la
    # MUTATION differe (`AddFlag(Owner@+0x30, <UnitFlag>)` au lieu d'`AddEffect`). Donc MEMES deux
    # enums, pour la meme raison : `spawn.py::_seed_ability_owner_effects` boucle sur
    # `activeAbilities + passiveAbilities`, la voie ne dit pas l'enum.
    # PAS de `noms_sup` : `TRAIT_DERIVED_ABILITIES` alimente les deux dicts d'EFFETS ci-dessus
    # (`_seed_derived_ability_owner_effects` -> `get_owner_effects_added_on_ability_init`), pas
    # celui-ci -- l'elargir sans lecteur accepterait des cles que rien ne consomme.
    Consommateur("ABILITY_INIT_OWNER_FLAGS", "engine.entities.effects.factory",
                 "ABILITY_INIT_OWNER_FLAGS", ("ActiveAbilityType", "TriggeredAbilityType"),
                 raison="`<Ability>_InitAbility.CreateBehaviour` -> `AddFlag(owner)` a l'init"),
    # #1038 -- `snapshot._rebake_tertiary_posed_effects` :
    # `get_effects_posed_by_tertiary_ability(str(tert)) or ()`. MEME lecture `.get(<nom>, [])`, donc
    # MEME degradation muette que ses cinq voisins : un nom disparu rend `[]`, la passe ne re-bake
    # rien, et l'effet garde le couple des PASSIFS -- ce qui n'est PAS inerte mais FAUX (mesure
    # #1038 : `dmgReductionPct` lu **32** au lieu de **10**, facteur 3,2, sans la moindre erreur).
    # UN SEUL enum, et c'est le MEME que `RELIC_ABILITY_TRIGGERS` pour la MEME raison : la cle est
    # l'ability TERTIAIRE de la SOURCE, c'est-a-dire ce que le natif monte par
    # `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)` (branche TERTIAIRE
    # d'`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`) -- la voie unique des
    # reliques ET des mythiques de MoW. Cote port la cle est lue dans `UnitContext.tertiary_ability`,
    # seedee par `snapshot._load_tertiary_abilities` depuis le RPC `unitAbilityStates`.
    # MESURE : `MastersOfManoeuvre` = `TriggeredAbilityType` 0x5e4 = 1508, ABSENT d'`ActiveAbilityType`.
    Consommateur("TERTIARY_ABILITY_POSED_EFFECTS", "engine.entities.effects.factory",
                 "TERTIARY_ABILITY_POSED_EFFECTS", "TriggeredAbilityType",
                 raison="voie TERTIAIRE -- effets qu'une relique/mythique pose SUR AUTRUI, dont "
                        "l'AbilityState bake est celui de la tertiaire de la SOURCE"),
]


def abilities_derivees_de_trait() -> set:
    """Les noms d'ability que le PORT produit lui-meme, via `TRAIT_DERIVED_ABILITIES`.

    Ce sont les valeurs du dict, pas ses cles : `{"Diminutive": ["DiminutiveAbility"]}` ->
    `DiminutiveAbility`. `spawn.py::_seed_derived_ability_owner_effects` les passe ensuite a
    `get_owner_effects_added_on_ability_init`, donc elles arrivent bien comme CLES
    d'`ABILITY_INIT_OWNER_EFFECTS` -- un espace de noms interne, legitime et DERIVE."""
    import importlib
    d = getattr(importlib.import_module("engine.entities.effects.factory"),
                "TRAIT_DERIVED_ABILITIES")
    return {n for ns in d.values() for n in ns}


def chaine_trait_derivee_cassee() -> list:
    """LE CRAN DU DESSOUS de la chaine trait -> ability derivee -> owner-effect.

    Toute valeur de `TRAIT_DERIVED_ABILITIES` doit etre CONSOMMEE quelque part, sinon le trait
    derive une ability que rien ne materialise -- `.get(nom, [])` rend `[]`, aucun owner-effect
    n'est pose, et le porteur perd silencieusement sa reduction. Trois destinations legitimes :
    une cle d'`ABILITY_INIT_OWNER_EFFECTS`, une cle d'`ABILITY_OWNER_EFFECTS`, ou un membre d'enum
    du build (auquel cas la chaine passe par la voie ordinaire)."""
    import importlib
    F = importlib.import_module("engine.entities.effects.factory")
    cibles = set(F.ABILITY_INIT_OWNER_EFFECTS) | set(F.ABILITY_OWNER_EFFECTS)
    return sorted(n for n in abilities_derivees_de_trait() if n not in cibles)


# ------------------------------- etape 7 : la PARTITION des foyers (#270-r2)
#
# POURQUOI CETTE ETAPE, ET POURQUOI ELLE NE << DECOUVRE >> PAS LES REGISTRES.
# L'etape 1 decouvre toute `IntEnum` sous `engine/`, ce qui empeche le trou de se re-creuser.
# L'etape 5, elle, ne gardait que les dicts INSCRITS A LA MAIN -- exactement le mode de defaillance
# que l'etape 1 existe pour fermer, reintroduit un cran plus bas.
#
# Decouvrir << un dict dont les cles designent un enum >> n'est PAS decidable par AST : une table de
# constantes et un registre d'abilities ont la meme forme. La reponse n'est donc pas la decouverte
# mais la PARTITION : dans les MODULES qui hebergent deja un registre inscrit (les foyers), TOUT
# dict de niveau module est soit INSCRIT, soit ECARTE AVEC SA RAISON. Rien ne peut y etre muet.
# Meme patron que le recenseur de #270-r1, qui a cesse d'enumerer des roles pour les DERIVER et
# faire sortir l'inconnu sous `autre (<Noeud>)`.
#
# Effet MESURE au premier passage : 4 registres reels trouves, tous les quatre absents de la liste
# ecrite -- `TRAIT_OWNER_EFFECTS`, `TRAIT_DERIVED_ABILITIES`, `ABILITY_INIT_OWNER_EFFECTS`,
# `ABILITY_OWNER_EFFECTS`. Ils sont desormais inscrits ci-dessus.

#: Dicts de niveau module d'un foyer qui NE SONT PAS des registres indexes par un membre d'enum.
#: Chacun porte sa RAISON : c'est ce qui distingue un ecart raisonne d'un oubli.
HORS_PERIMETRE: dict[str, str] = {}


def foyers() -> set:
    """Les modules qui hebergent au moins un registre INSCRIT. Derive de `CONSOMMATEURS`, jamais
    ecrit : inscrire un registre dans un module neuf met AUSSITOT tout ce module sous partition."""
    return {c.mod for c in CONSOMMATEURS}


def dicts_de_foyer() -> list:
    """`(module, nom)` de tout dict de niveau module d'un foyer -- par AST, jamais par import (un
    import ferait tourner le moteur, et l'etape doit rester lisible seule)."""
    import ast
    out = []
    for mod in sorted(foyers()):
        p = REPO / "scripts" / "python" / (mod.replace(".", "/") + ".py")
        if not p.exists():
            out.append((mod, "<MODULE INTROUVABLE>"))
            continue
        arbre = ast.parse(p.read_text(encoding="utf-8"))
        for n in arbre.body:
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            valeur = n.value
            if not isinstance(valeur, ast.Dict):
                continue                                  # une List/Set n'est pas lue PAR CLE
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append((mod, t.id))
    return out


def etape_partition() -> int:
    print("ETAPE 7 -- PARTITION des FOYERS de registre (#270-r2)")
    inscrits = {(c.mod, c.attr) for c in CONSOMMATEURS}
    muets = []
    for mod, nom in dicts_de_foyer():
        if (mod, nom) in inscrits or nom in HORS_PERIMETRE:
            continue
        muets.append((mod, nom))
    print("  foyers derives de CONSOMMATEURS : %d" % len(foyers()))
    print("  dicts de niveau module          : %d" % len(dicts_de_foyer()))
    print("  INSCRITS %d | ECARTES AVEC RAISON %d | MUETS %d"
          % (len(inscrits), len(HORS_PERIMETRE), len(muets)))
    for mod, nom in muets:
        print("     MUET   %s.%s -- ni inscrit dans CONSOMMATEURS, ni ecarte avec sa raison"
              % (mod, nom))
    print("")
    return len(muets)


PAR_CONSO = {c.nom: c for c in CONSOMMATEURS}


def table_consommateur(c: Consommateur) -> dict:
    """Le dict lui-meme. Import PARESSEUX : charger `triggers.dispatch.registry` entraine tout le
    moteur, et les etapes 1 a 3 doivent rester lisibles sans lui."""
    import importlib
    return getattr(importlib.import_module(c.mod), c.attr)


def cles_cassees(build: str, c: Consommateur,
                 table: dict | None = None) -> tuple[list, list, list]:
    """(introuvables, mortes, egarees) pour UN consommateur.

    `table` -- les cles a examiner, au lieu du dict reel. C'est ce qui permet a un test de nourrir
    le detecteur de cles TRUQUEES et de verifier qu'il MORD, sans quoi une etape verte sur un
    depot sain ne prouverait rien (meme patron que `references_cassees(build, refs=None)`).

    introuvables : la cle n'est ni dans le mirror ni dans le build -- l'entree est morte, en
                   silence (`.get(cle, ())` rend `()` : le passif n'est jamais inscrit).
    mortes       : elle est dans le mirror mais plus dans le BUILD -- meme effet, et le mirror
                   ment en plus.
    egarees      : (cle PAR NOM seulement) elle n'est pas dans l'enum de sa voie, mais elle EXISTE
                   dans un autre enum natif. C'est la signature du MAUVAIS ENUM, et le seul des
                   trois qui NOMME sa cause -- l'appariement du registre est a relire.
    """
    ms = [PAR_CLS[x] for x in c.classes]
    cles_natives = {m.cle for m in ms}
    cles = list(table_consommateur(c) if table is None else table)
    if c.par == "valeur":
        port = {v for m in ms for v in membres_mirror(m.rel, m.cls)}
        jeu = {v for m in ms for v in enum_natif(build, m.cle)}
        return ([(k, []) for k in cles if k not in port and k not in jeu],
                [k for k in cles if k in port and k not in jeu], [])
    noms_port = {n for m in ms for ns in membres_mirror(m.rel, m.cls).values() for n in ns}
    noms_jeu = {n for m in ms for ns in enum_natif(build, m.cle).values() for n in ns}
    if c.noms_sup is not None:
        noms_jeu = noms_jeu | set(c.noms_sup())
    introuvables, mortes, egarees = [], [], []
    autres = None
    for k in cles:
        if _echappe(k) in noms_jeu:
            continue
        if _echappe(k) in noms_port:
            mortes.append(k)
            continue
        if autres is None:
            autres = tous_les_enums(build)
        ou = sorted(cle.split(".")[-1] for cle, s in autres.items()
                    if cle not in cles_natives and _echappe(k) in s)
        (egarees if ou else introuvables).append((k, ou))
    return introuvables, mortes, egarees


def tous_les_enums(build: str) -> dict[str, set[str]]:
    """{cle de enums.tsv: {noms de membres}} -- TOUS les enums natifs du build.

    Sert a NOMMER la cause d'une cle qui ne resout pas dans l'enum de sa voie : dire « absente »
    envoie chercher une faute de frappe ; dire « ce nom est un `EffectType` » designe le vrai
    defaut, qui est l'appariement."""
    out: dict[str, set[str]] = {}
    for ligne in (build_dir(build) / "frida"/"enums.tsv").open(encoding="utf-8"):
        if ligne.startswith("#!"):
            continue
        cle, _, reste = ligne.rstrip("\n").partition("\t")
        if not reste:
            continue
        noms = {n for _, _, n in (p.partition("=") for p in reste.split(",")) if n}
        if noms:
            out[cle] = noms
    return out


def homonymes(build: str, cle: str) -> tuple[list, list]:
    """(nom_partage_ordinal_DIFFERENT, ordinaux_partages_nom_DIFFERENT) pour UN enum natif.

    LES DEUX AXES DE LA CONFUSION INTER-ENUMS, et ils n'ont pas le meme cout :

      * un NOM present dans deux enums a des ordinaux DIFFERENTS -> lire le nom depuis le mauvais
        mirror rend un ordinal FAUX. C'est ce que l'etape 5 garde (`egarees`).
      * un ORDINAL present dans deux enums sous des noms DIFFERENTS -> une cle ENTIERE resout des
        deux cotes et ne prouve RIEN. C'est la raison mesurable de la regle « un entier qui DESIGNE
        passe par un enum » : le nom discrimine, l'ordinal non.
    """
    tous = tous_les_enums(build)
    ref = enum_natif(build, cle)
    par_nom: dict[str, set[int]] = {}
    for v, ns in ref.items():
        for n in ns:
            par_nom.setdefault(n, set()).add(v)
    noms_diff, ord_diff = [], []
    for autre, _ in tous.items():
        if autre == cle:
            continue
        d = enum_natif(build, autre)
        idx: dict[str, set[int]] = {}
        for v, ns in d.items():
            for n in ns:
                idx.setdefault(n, set()).add(v)
        for n, vs in idx.items():
            if n in par_nom and vs != par_nom[n]:
                noms_diff.append((n, autre, sorted(par_nom[n]), sorted(vs)))
        comm = [v for v in set(ref) & set(d) if not (ref[v] & d[v])]
        if comm:
            ord_diff.append((autre, len(set(ref) & set(d)), len(comm)))
    return noms_diff, sorted(ord_diff, key=lambda x: -x[2])


def etape_consommateurs(build: str) -> int:
    print("ETAPE 5 -- DICTS CONSOMMATEURS (les cles que le moteur lit REELLEMENT)")
    rouge = 0
    for c in CONSOMMATEURS:
        try:
            n = len(table_consommateur(c))
        except Exception as exc:                                   # noqa: BLE001
            print("  ROUGE  %-28s import impossible : %s" % (c.nom, exc))
            rouge += 1
            continue
        introuvables, mortes, egarees = cles_cassees(build, c)
        etat = "OK"if not (introuvables or mortes or egarees) else"ROUGE"
        print("  %-6s %-28s %3d cles par %-7s -> %-22s INTROUVABLES=%d MORTES=%d EGAREES=%d"
              % (etat, c.nom, n, c.par, c.cls, len(introuvables), len(mortes), len(egarees)))
        for k, ou in egarees:
            print("           EGAREE      %-34s ce nom vit dans : %s" % (k, ", ".join(ou[:5])))
        for k, _ in introuvables:
            print("           INTROUVABLE %-34s dans AUCUN enum du build" % (k,))
        for k in mortes:
            print("           MORTE       %-34s le build ne la connait plus" % (k,))
        rouge += len(introuvables) + len(mortes) + len(egarees)
    # Le cran du dessous : une ability DERIVEE d'un trait que rien ne materialise (#270-r2).
    orphelines = chaine_trait_derivee_cassee()
    print("  %-6s %-28s %3d abilities derivees d'un trait, %d sans consommateur"
          % ("OK" if not orphelines else "ROUGE", "chaine TRAIT_DERIVED",
             len(abilities_derivees_de_trait()), len(orphelines)))
    for n in orphelines:
        print("           ORPHELINE   %-34s derivee d'un trait, aucun owner-effect a poser" % n)
    rouge += len(orphelines)
    print("")
    return rouge


def etape_homonymes(build: str) -> None:
    """INVENTAIRE, pas garde -- un homonyme est un FAIT du build, pas une derive du port.

    Il est imprime parce que c'est lui qui explique les `egarees` de l'etape 5, et parce que le
    chiffre de la section ORDINAUX est ce qui justifie de convertir une cle entiere en membre
    d'enum."""
    for cls in ("TriggeredAbilityType", "ActiveAbilityType"):
        m = PAR_CLS[cls]
        noms_diff, ord_diff = homonymes(build, m.cle)
        print("ETAPE 6 -- HOMONYMES de %s" % cls)
        print("  NOMS partages avec un autre enum a ordinal DIFFERENT : %d paire(s)"
              % len(noms_diff))
        for n, autre, a, b in sorted(noms_diff)[:20]:
            print("    %-42s ici=%-10s %s=%s" % (n, a, autre.split(".")[-1], b))
        if len(noms_diff) > 20:
            print("    ... %d de plus" % (len(noms_diff) - 20))
        print("  ORDINAUX partages, NOM different (une cle entiere n'y prouve rien) :")
        for autre, comm, diff in ord_diff[:6]:
            print("    %-46s %4d partages, %4d nomment AUTRE CHOSE"
                  % (autre.split(".")[-1], comm, diff))
        print("")


# ------------------------------------------------------------------------------ la sortie

def rapport(verbose: bool, porteurs: bool = False, consommateurs: bool = True,
            homo: bool = False) -> int:
    build = current_build()
    print("build : %s" % build)
    print("")
    rouge = 0

    # ---- Etape 1 : decouverte
    trouves = intenums_du_moteur()
    orphelins = sorted(c for c in trouves if c not in PAR_CLS and c not in HORS_MIRROR)
    absents = sorted(m.cls for m in REGISTRE if m.cls not in trouves)
    print("ETAPE 1 -- DECOUVERTE : %d classe(s) IntEnum/IntFlag sous engine/" % len(trouves))
    print("  APPARIEES=%d  HORS-MIRROR=%d  ORPHELINES=%d"
          % (sum(1 for c in trouves if c in PAR_CLS),
             sum(1 for c in trouves if c in HORS_MIRROR), len(orphelins)))
    for c in orphelins:
        print("  ORPHELINE %-24s %s -- ni apparie, ni justifie HORS-MIRROR" % (c, trouves[c]))
    for c in absents:
        print("  AU REGISTRE MAIS INTROUVABLE : %s (%s)" % (c, PAR_CLS[c].rel))
    rouge += len(orphelins) + len(absents)
    print("")

    # ---- Etape 2 : bijection
    print("ETAPE 2 -- BIJECTION mirror <-> enums.tsv (les DEUX sens)")
    for m in sorted(REGISTRE, key=lambda x: (not x.garde, x.cls)):
        port = membres_mirror(m.rel, m.cls)
        if not port:
            print("  ROUGE  %-22s classe introuvable dans %s" % (m.cls, m.rel))
            rouge += 1
            continue
        jeu = enum_natif(build, m.cle)
        manquants, morts, renum = bijection(port, jeu, m.strict)
        compte = (len(manquants), len(morts), len(renum))
        if m.garde:
            etat = "OK"if compte == (0, 0, 0) else"ROUGE"
            tag = "[SOUS GARDE]" + (""if m.strict else" valeurs seules")
            rouge += 0 if compte == (0, 0, 0) else 1
        else:
            etat = "dette"if compte == m.dette else"ROUGE"
            tag = "[dette declaree %s]" % (m.dette,)
            rouge += 0 if compte == m.dette else 1
        print("  %-6s %-22s port=%-4d jeu=%-4d  MANQUANTS=%-4d MORTS=%-4d RENUMEROTES=%-3d %s"
              % (etat, m.cls, len(port), len(jeu), *compte, tag))
        if verbose or (m.garde and compte != (0, 0, 0)):
            for v, ns in manquants[:12]:
                print("           MANQUANT   %-6d le jeu dit %s"% (v,",".join(ns)))
            if len(manquants) > 12:
                print("           ... %d manquant(s) de plus" % (len(manquants) - 12))
            for v, ns in morts[:12]:
                print("           MORT       %-6d le port dit %s"% (v,",".join(ns)))
            if len(morts) > 12:
                print("           ... %d mort(s) de plus" % (len(morts) - 12))
            for v, n, ns in renum[:8]:
                print("           RENUMEROTE %-6d le port dit %-32s le jeu dit %s"
                      % (v, n, ",".join(ns)))
    print("")

    # ---- Etape 3 : references qualifiees
    refs = references_qualifiees()
    introuvables, mortes = references_cassees(build, refs)
    print("ETAPE 3 -- REFERENCES QUALIFIEES `<Classe>.<membre>` dans du Python suivi")
    print("  total=%d  INTROUVABLES=%d (AttributeError)  MORTES=%d (le build ne connait plus)"
          % (len(refs), len(introuvables), len(mortes)))
    for rel, k, cls, membre in introuvables[:20]:
        print("  INTROUVABLE %s:%d  %s.%s" % (rel, k, cls, membre))
    for rel, k, cls, membre in mortes[:20]:
        print("  MORTE       %s:%d  %s.%s" % (rel, k, cls, membre))
    rouge += len(introuvables) + len(mortes)
    print("")

    # ---- Etape 4 : porteurs (optionnelle : elle charge le gameconfig)
    if porteurs:
        rouge += etape_porteurs(build)

    # ---- Etape 5 : dicts consommateurs (par defaut : elle importe le moteur, ~1 s)
    if consommateurs:
        rouge += etape_consommateurs(build)

    # ---- Etape 6 : homonymes (inventaire pur, jamais bloquant)
    if homo:
        etape_homonymes(build)

    # ---- Etape 7 : partition des foyers (#270-r2) -- PUREMENT AST, aucun import du moteur, donc
    # elle tourne meme sous `--sans-consommateurs` : c'est justement quand on saute l'etape 5 qu'un
    # registre muet passerait le plus facilement.
    rouge += etape_partition()

    if rouge:
        print("%d ecart(s) BLOQUANT(s) -- voir ci-dessus" % rouge)
    else:
        dettes = sum(1 for m in REGISTRE if not m.garde)
        print("les %d mirror(s) SOUS GARDE sont en bijection avec le build %s ; %s"
              % (sum(1 for m in REGISTRE if m.garde), build,
                 ("%d dette(s) declaree(s) au compte attendu" % dettes) if dettes else
                 "AUCUNE dette declaree ne subsiste (les 2 dernieres resorbees par #318)"))
    return 1 if rouge else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="detailler manquants/morts/renumerotes de TOUS les mirrors")
    ap.add_argument("--porteurs", action="store_true",
                    help="etape 4 : confronter le mirror au gameconfig (file de portage)")
    ap.add_argument("--sans-consommateurs", action="store_true",
                    help="sauter l'etape 5 (elle importe le moteur)")
    ap.add_argument("--homonymes", action="store_true",
                    help="etape 6 : inventorier les homonymes inter-enums (jamais bloquant)")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant le cache versionne et le confronte entree "
                         "par entree (#486-r1) -- le seul controle qui voie une entree falsifiee "
                         "de facon coherente")
    a = ap.parse_args()

    global _CACHE
    if a.verifier_cache:
        #: MODE ESPION : le fichier est charge, jamais servi -- le rapport recalcule donc TOUT.
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_313_enum_mirror_bijection",
            contexte=verdict_cache.sha_fichiers_texte(Path(__file__).resolve()), relire=False)

    rc = rapport(a.verbose, a.porteurs, not a.sans_consommateurs, a.homonymes)

    #: LE CACHE (#486-r1) -- muet dans le regime normal : la sortie avec cache chaud doit etre
    #: BIT POUR BIT celle d'un run a froid. Les modes `--porteurs` / `--homonymes` n'ajoutent
    #: aucun appel cache, `--sans-consommateurs` non plus : tous les regimes visitent les memes
    #: entrees, donc tous peuvent ecrire sans chasser celles de la boucle de merge.
    if a.verifier_cache:
        divergences = verdict_cache.verifier(cache())
        print("")
        print("=== VERIFICATION DU CACHE VERSIONNE (#486-r1) ===")
        print("  entrees sur disque : %d   recalculees : %d"
              % (len(cache()._sur_disque), len(cache()._vues)))
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            #: rc DEDIE : ce n'est pas le verdict du cliquet sur le depot, c'est le CACHE qui ment.
            print("  rc=3 -- le cache versionne n'atteste PAS ce que le calcul rend. Le")
            print("  REGENERER : python scripts/python/probe_313_enum_mirror_bijection.py")
            return 3
        print("  OK -- chaque entree du cache vaut ce que le recalcul integral produit.")
    else:
        c = cache()
        c.enregistrer()
        # #486-r22 : si cette reecriture a CHANGE le fichier versionne, du code est entre depuis
        # la derniere regeneration commitee. Le verdict ci-dessus reste juste ; c'est l'artefact
        # qui est en retard, et sans ce cran il le resterait indefiniment.
        return verdict_cache.rendre_compte_du_cache(c, rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
