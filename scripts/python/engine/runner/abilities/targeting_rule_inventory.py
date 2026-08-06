"""#429 -- L'INVENTAIRE UNIQUE du role NATIF de chaque membre de `TargetingRule`.

POURQUOI CE FICHIER EXISTE
--------------------------
Le depot portait TROIS recensements concurrents de « quelles regles de ciblage ne sont pas
portees », qui ne couvraient ni les memes membres ni le meme perimetre et se lisaient tous
comme exhaustifs (compte re-derive par `scripts/python/probe_429_targeting_rule_inventory.py`).
Aucun ne couvrait l'enum entier, et aucun ne savait qu'il etait partiel.

Ce module remplace la partie SAISIE de ces trois tables par une seule, dont la couverture est
GARDEE dans les DEUX directions par
`scripts/python/tests/engine/runner/test_targeting_rule_inventory.py` :

  * direction VIVANTE : `enum \\ inventaire` doit etre VIDE -- un membre neuf au re-dump
    (nouveau build) fait ECHOUER la garde tant qu'il n'est pas classe ;
  * direction MORTE   : `inventaire \\ enum` doit etre VIDE -- une entree qui designe un membre
    DISPARU fait echouer aussi. C'est la direction qu'aucun des trois inventaires ne tenait.

CE QUI N'EST PAS ICI, ET C'EST LE POINT
---------------------------------------
**La colonne « portee par le port » n'est PAS saisie ici.** C'est la donnee la plus volatile
(elle bouge a chaque tranche livree), donc c'est exactement celle qui se perime en silence dans
une table ecrite a la main -- les trois tables l'ont toutes fait. Elle est DERIVEE de l'AST du
port (`probe_429_targeting_rule_inventory.py::rules_returned_by_port` : les membres que le port
peut RENDRE comme code de refus), et la garde CONFRONTE cette derivation au role declare ici.

CE QUI EST ICI est le role NATIF, qui ne bouge qu'au changement de build : ce que le bit fait
dans le binaire, et surtout **ce qui l'ARME**. Ce dernier point est la seconde raison d'etre du
fichier : trois regles du filtre statique ne sont PAS armees par leur propre bit, et compter
« les porteurs du bit » y donne un compte structurellement FAUX (cf. `armed_by` ci-dessous).

TOUS LES NOMS SONT CEUX DE L'ENUM NATIF et ce module n'en DECLARE aucun : ce sont des cles de
chaine, confrontees a `targeting_rule.py` (mirror GENERE par `gen_targeting_rule.py` depuis
`data/symbols/<build>/frida/enums.tsv`) par la garde. Il n'y a donc toujours qu'UNE source de
noms de bits.

SOURCE DE CHAQUE LIGNE : lecture du decompile du build courant (`rnca9r7q6c`), fonction par
fonction. Les huit lecteurs relus sont listes dans `READERS`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- Les LECTEURS natifs relus pour construire cet inventaire ------------------------------
# Un `reader` d'entree ci-dessous vaut l'une de ces cles (ou None quand il n'a pas ete localise).
READERS = {
    "TARGET": "IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason",          # surcharge 7 args = LE filtre statique
    "CASTER": "IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason",          # surcharge 4 args
    "ADD_CASTER": "IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason",
    "VALID_TARGETS": "IdunBattle.Core.Services.TargetingQuery$$GetValidTargets",
    "LOS": "IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain",
    "UNITS_IN_RANGE": "IdunBattle.Core.Services.TargetingQuery$$GetUnitsInRange",
    "OBSCURED_RULE": "IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule$$get_Type",
    "ABILITY": "IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidCasterReason",
    "ATTACK_QUERY": "IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason",
    # --- #429-r1 : les deux lecteurs qui vivent HORS du ciblage -------------------------------
    # C'est la raison de fond pour laquelle les huit ci-dessus ne pouvaient pas les trouver : ni
    # l'un ni l'autre n'appartient a une cascade de refus de cible ou de caster.
    "CONTINUE_ON_DEAD": "IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget",
    "DYNAMIC_RULE": ("IdunBattleLogic.Entities.Abilities.Active.Loki.AnnihilatorBeamAbility$$"
                     "GetDynamicInvalidTargetReason"),
}

# --- Les CATEGORIES ------------------------------------------------------------------------
# GATE_TARGET     regle de refus de la cascade CIBLE (filtre statique 7 args)
# GATE_CASTER     regle de refus de la cascade CASTER
# GATE_ADD_CASTER regle de la branche SELF-CAST (`GetCasterNotAddedReason`) / de l'ajout du
#                 caster aux cibles valides (`GetValidTargets`)
# PERMISSION      DESARME une regle -- n'en est pas une ; la porter comme regle inventerait un refus
# REASON          CODE DE RAISON seulement : aucune cascade ne teste ce bit dans un masque
# DECLARATIVE     lu par un getter de domaine, consomme par l'enumeration des cibles
# GATE_OPERATION  regle de refus lue HORS ciblage, par un gate d'OPERATION (#429-r1). Distincte des
#                 GATE_* ci-dessus a deux titres : elle ne rend jamais d'`IBrokenTargetingRule` (le
#                 natif abandonne l'operation, il ne « donne pas de raison »), et son masque n'est
#                 pas forcement le masque principal de l'ability -- d'ou `armed_by`.
# READER_UNKNOWN  aucun lecteur localise -- RESIDU NOMME, pas une preuve de mort (l'absence dans un
#                 balayage ne prouve rien : cf. CLAUDE.md). PLUS AUCUNE entree depuis #429-r1 ; la
#                 categorie RESTE, c'est la case honnete du prochain membre non localise.
KINDS = ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER", "PERMISSION", "REASON",
         "DECLARATIVE", "GATE_OPERATION", "READER_UNKNOWN")

# `armed_by = None` : la regle est armee par SON PROPRE bit (le cas ordinaire).
# `armed_by = "<expression>"` : elle est armee par AUTRE CHOSE, et alors compter « les porteurs
# du bit » donne un compte FAUX -- c'est la faute commune des trois inventaires remplaces.
SELF = None


@dataclass(frozen=True)
class Role:
    kind: str
    reader: Optional[str]
    armed_by: Optional[str] = SELF
    note: str = ""
    # Le code que le NATIF rend quand la regle rompt. `None` = le membre lui-meme (le cas
    # ordinaire). Il n'y a qu'UNE exception dans le build courant, et elle compte : la tete de
    # domaine TUILE rend le litteral `1` = `ValidRequest`, jamais `TargetIsTile`. Un audit qui
    # chercherait « le port rend-il `TargetIsTile` ? » conclurait donc a tort au non-port.
    reason_code: Optional[str] = None
    # (fonction du PORT, jeton a y trouver) -- pour les regles qui ne sont JAMAIS un code de refus.
    #
    # POURQUOI CE CHAMP (#447). Le critere de derivation « le port peut RENDRE `int(TR.<X>)` » est
    # le bon pour l'ecrasante majorite des regles, mais il est STRUCTURELLEMENT aveugle a deux
    # familles -- parce que le NATIF LUI-MEME ne rend jamais leur code :
    #   * les COURT-CIRCUITS (`AddCaster`) : le bit fait rendre VALIDE, jamais un refus ;
    #   * les POINTS D'EXTENSION (`TargetMatchesDynamicRule`, `CasterMatchesDynamicRule`,
    #     `AddCasterIfMatchesDynamicRule`) : le natif rend le code de la DELEGUE tel quel
    #     (`return GenericBrokenTargetingRule(r)`), donc le bit n'est qu'un AIGUILLAGE.
    # Pour ces quatre-la, « portee » se derive autrement : la fonction nommee ici doit contenir le
    # jeton nomme ici -- soit un APPEL (`get_dynamic_invalid_caster_reason(...)`), soit un
    # `TR.<jeton>` (le test du bit). La granularite est la FONCTION PORTEUSE, ce qui est
    # essentiel : `get_dynamic_invalid_caster_reason` est appele par DEUX foyers distincts
    # (`get_invalid_caster_reason` sous le bit 2, `get_caster_not_added_reason` sous le bit 3), et
    # un critere « la methode est appelee quelque part » compterait le second porte alors que seul
    # le premier l'etait. La derivation reste une DERIVATION : rien n'est saisi sur l'etat de port.
    ported_by: Optional[tuple] = None

    def code(self, nom: str) -> str:
        return self.reason_code or nom


RULE_ROLE = {
    # ---------------------------------------------------------------------------------------
    # Valeur neutre
    # ---------------------------------------------------------------------------------------
    "None": Role("REASON", None, SELF,
                 "0 = aucune regle rompue. Le port modelise ce cas par le retour 0."),

    # ---------------------------------------------------------------------------------------
    # CODES DE RAISON -- jamais testes comme bit d'un masque
    # ---------------------------------------------------------------------------------------
    "ValidRequest": Role(
        "REASON", READERS["ABILITY"], SELF,
        "Rendu sur argument NUL par `AActiveAbility$$GetInvalidCasterReason` et "
        "`AActiveAbility$$GetInvalidTargetReasonWithRules` -- ET reutilise par le filtre statique "
        "pour la tuile-cible NON MARCHABLE (litteral 1). Deux sens pour une meme valeur."),
    "AlreadyUseThisTurn": Role(
        "REASON", READERS["ATTACK_QUERY"], "`AttackQuery$$IsAlreadyUsedThisTurn`",
        "Produit par `AttackQuery$$GetInvalidTargetReason`, EN AMONT de la cascade de ciblage."),

    # ---------------------------------------------------------------------------------------
    # CASCADE CIBLE -- `TargetingQuery$$GetInvalidTargetReason` (7 args)
    # ---------------------------------------------------------------------------------------
    "TargetMatchesDynamicRule": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "Point d'extension : invoque la regle-delegue `options+0x38` (slot vtable +0x480 = "
        "`<X>Ability$$GetDynamicInvalidTargetReason`) et rend son code TEL QUEL -- son propre bit "
        "n'est donc JAMAIS le code rendu, d'ou `ported_by`.",
        ported_by=("get_invalid_target_reason", "get_dynamic_invalid_target_reason")),
    "TargetHasFreeAdjacentTile": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "`<IBattleQuery slot 0x52>(target)` -- la cible doit avoir >= 1 tuile adjacente libre."),
    "TargetIsTile": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "TETE DE DOMAINE. Resout la cible en TUILE ; tuile non marchable -> rend le litteral 1 "
        "(`ValidRequest`), sauf `AllowUnwalkableTargetTile`.",
        reason_code="ValidRequest"),
    "TargetIsUnobscured": Role(
        "GATE_TARGET", READERS["OBSCURED_RULE"],
        "la LIGNE DE VUE (`GetTilesObscuringTerrain`) -- AUCUN bit ne l'arme",
        "SEULE regle du filtre dont le refus ne passe pas par `GenericBrokenTargetingRule` : le "
        "natif boxe `ObscuredTerrainBrokenTargetingRule` (dont `get_Type` rend 0x1000000) des que "
        "`GetTilesObscuringTerrain` rend une liste non vide. Elle tourne pour TOUTE ability hors "
        "`ignoreRangeChecks` ; les bits 25/26 ne font que la DESARMER. Trois desarmements de plus, "
        "ANTERIEURS aux bits (#444) : `TargetingConfiguration.EnableObscuringTerrain` a faux, une "
        "cible AMIE (`IsFriendOrHasFriendlyUnitOnIt`), et le trait 1005 `IndirectFire` du caster "
        "(qui ne retire QUE le volet elevation)."),
    "TargetIsHealable": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "`<IAttackQuery slot 0x11>` = `AttackQuery$$EntityCanBeHealed(caster, cible, 0, 1)`."),
    "TargetIsAtRange": Role(
        "GATE_TARGET", READERS["TARGET"], "le champ `TargetingRange` des options, PAS un bit",
        "Variante EXACTE du volet portee : `d != range.Value`. Le volet portee n'est gate par "
        "AUCUN bit -- ce bit ne fait que choisir `==` au lieu de `<=`."),
    "TargetIsFriendly": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "`UnitsAreFriendly`, et l'effet `FriendlyFire` (0x67) de la CIBLE la rend non amie."),
    "TargetTileIsFree": Role("GATE_TARGET", READERS["TARGET"], SELF, "`TileExtensions$$IsFreeTile`."),
    "TargetIsSummon": Role("GATE_TARGET", READERS["TARGET"], SELF, "`HasTrait(target, 2 Summon)`."),
    "TargetIsEnemy": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`TargetingQuery$$UnitsCanAttackEachOther`."),
    "TargetIsRepairable": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "JUMEAU de `TargetIsHealable` : `<IAttackQuery slot 0x12>`, meme forme d'appel."),
    "TargetTileIsFreeOrEnemy": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "`IsFreeTile` OU `UnitsCanAttackEachOther(caster, GetUnit(target))`, et la tuile "
        "principale ne doit pas etre TEMPORAIRE."),
    "TargetIsDisplaceable": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`UnitExtensions$$IsDisplaceable`."),
    "TargetTileHasEnemyUnit": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "`IsEmptyOrSteppable` NIE + `UnitsCanAttackEachOther`. IMBRIQUE dans le `then` du bit "
        "`TargetTileIsFreeOrEnemy` cote natif."),
    "CasterHasFreeAdjacentTile": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "JUMELLE du bit 5 appliquee au CASTER (`<IBattleQuery slot 0x52>` sur `param_2`), et "
        "c'est bien une regle de la cascade CIBLE, pas de la cascade CASTER."),
    "TargetIsAllowedForCaster": Role(
        "GATE_TARGET", READERS["TARGET"],
        "`TargetIsEnemy | TargetIsCasterOrEnemy`, DESARME par `AllowIgnoreForcedAttackTarget`",
        "TAUNT : `UnitExtensions$$GetOnlyTargets(caster)` non vide et la cible n'y figure pas. "
        "**Son propre bit n'est JAMAIS teste** -- il n'est que le code de raison rendu. Compter "
        "« les porteurs du bit 23 » donne donc 0 pour une regle armee chez tout porteur du bit 14."),
    "TargetIsInRange": Role(
        "GATE_TARGET", READERS["TARGET"], "le champ `TargetingRange` des options, PAS un bit",
        "Volet portee : `d > range.Value` (ou `!AreEntitiesAdjacent` sous `OnlyAdjacent`)."),
    "TargetIsTargetable": Role(
        "GATE_TARGET", READERS["TARGET"], "TOUJOURS, DESARME par `AllowUntargetableTarget`",
        "Controle INVERSE : son propre bit n'arme rien, c'est le bit 41 qui le retire."),
    "TargetIsNotAdjacent": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`<IBattleQuery slot 0x62>(targetTiles, casterTiles)`."),
    "TargetIsNotAnObject": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`HasTrait(target, 0xd Object)` INTERDIT."),
    "TargetIsCaster": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`caster != GetUnit(target)` -> refus."),
    "TargetIsNotAdjacentToEnemy": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`<IBattleQuery slot 0x80>` = `GetAdjacentEnemies`."),
    "TargetIsMachine": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "TETE DE DOMAINE : resout la cible en MACHINE."),
    "TargetIsUnit": Role(
        "GATE_TARGET", READERS["TARGET"],
        "l'ABSENCE de `TargetIsTile | TargetIsMachine | TargetIsActor`",
        "TETE DE DOMAINE, refus par DEFAUT : quand `GetUnit(target)` est nul et qu'aucun des "
        "trois autres domaines n'est pose. Son propre bit ne l'arme pas."),
    "TargetIsActor": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "TETE DE DOMAINE : resout la cible en ACTEUR."),
    "TargetHas1Tiles": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`GetFeetCount(target) != 1` -> refus."),
    "TargetHas3Tiles": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`GetFeetCount(target) != 3` -> refus."),
    "TargetHas7Tiles": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`GetFeetCount(target) != 7` -> refus."),
    "TargetIsHero": Role(
        "GATE_TARGET", READERS["TARGET"], SELF, "`HasTrait(target, 0x10 Hero)` requis."),
    "TargetIsNotSteppable": Role(
        "GATE_TARGET", READERS["TARGET"],
        "son bit OU (`get_IsUnitTargeting` ET pas `AllowSteppableUnit`)",
        "`TileExtensions$$HasSteppableUnit`. `get_IsUnitTargeting` = ABSENCE des bits 6/44/46, "
        "donc la regle est armee PAR DEFAUT sur toute ability unit-targeting sans le bit 20 : "
        "compter « les porteurs du bit 51 » sous-estime massivement son armement."),
    "TargetIsCasterOrEnemy": Role(
        "GATE_TARGET", READERS["TARGET"], SELF,
        "self OU ennemi attaquable ; egalement lu par "
        "`TargetingQuery$$IsGuaranteedToHaveNoValidTargetsOnBoard`."),

    # ---------------------------------------------------------------------------------------
    # CASCADE CASTER -- `TargetingQuery$$GetInvalidCasterReason`
    # ---------------------------------------------------------------------------------------
    "CasterMatchesDynamicRule": Role(
        "GATE_CASTER", READERS["CASTER"], SELF,
        "Regle-delegue `options+0x30` (slot vtable +0x470 = `GetDynamicInvalidCasterReason`). "
        "Comme son jumeau CIBLE, le natif rend le code de la DELEGUE, jamais ce bit -> `ported_by`.",
        ported_by=("get_invalid_caster_reason", "get_dynamic_invalid_caster_reason")),
    "CasterHasNotMoved": Role(
        "GATE_CASTER", READERS["CASTER"], SELF,
        "`DidMove(caster)` et tuiles non equivalentes -> refus. Gate `<IBattleQuery slot 0x35>` en tete."),
    "CasterCanMove": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`UnitExtensions$$CanMove(caster)` requis."),
    "AllowNullCasterTile": Role(
        "PERMISSION", READERS["CASTER"], SELF,
        "PERMISSION, et code de raison du refus : `casterTiles` VIDE sans NI ce bit NI "
        "`CasterHasNoTile` -> `broken(AllowNullCasterTile)`. C'est ce qui protege les MoW."),
    "CasterHasCompletedOneTurn": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`GetStat(caster, 0xc) <= 1` -> refus."),
    "CasterHas1Tiles": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`GetFeetCount(caster) != 1` -> refus."),
    "CasterHas3Tiles": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`GetFeetCount(caster) != 3` -> refus."),
    "CasterHas7Tiles": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`GetFeetCount(caster) != 7` -> refus."),
    "CasterHas2TurnsLeft": Role(
        "GATE_CASTER", READERS["CASTER"], SELF,
        "`<IBattleQuery slot 0x1b>(caster, 2)` requis -- le slot 0x1b est 27 "
        "`BattleQuery$$HasMinimumRemainingTurns` (arite 2, table de metadonnee). Ce module ecrivait "
        "DEJA le bon slot quand `targeting.py` et `astramilitarum.py` ecrivaient `0x1a` : c'est "
        "cette CONCORDANCE INTERNE rompue qui signalait le decalage de UN (#287-r11-r1-r1)."),
    "CasterIsMachine": Role(
        "GATE_CASTER", READERS["CASTER"], SELF, "`EntityExtensions$$IsMachine(caster)` requis."),
    "CasterHasNoTile": Role(
        "GATE_CASTER", READERS["CASTER"], SELF,
        "Symetrique de la clause tuile-nulle : tuiles NON vides alors que le bit est pose -> refus."),

    # ---------------------------------------------------------------------------------------
    # BRANCHE SELF-CAST / AJOUT DU CASTER -- `GetCasterNotAddedReason` + `GetValidTargets`
    # ---------------------------------------------------------------------------------------
    "AddCaster": Role(
        "GATE_ADD_CASTER", READERS["ADD_CASTER"], SELF,
        "Teste par le SIGNE de l'octet de poids faible (`-1 < (char)rules`) : s'il est pose, le "
        "caster est ajoute d'office et `GetCasterNotAddedReason` ne refuse RIEN. COURT-CIRCUIT : "
        "il ne peut donc jamais etre un code de refus, d'ou `ported_by` (porte par #447).",
        ported_by=("get_caster_not_added_reason", "AddCaster")),
    "AddCasterIfMatchesDynamicRule": Role(
        "GATE_ADD_CASTER", READERS["ADD_CASTER"], SELF,
        "Invoque la regle-delegue CASTER `options+0x30` et rend SON code, jamais ce bit. Unique "
        "porteur du registre : 1115 `FearOfTheUnseen`, dont la delegue rend "
        "`CasterMatchesDynamicRule` sur `UnitExtensions$$IsTeleporting` (le DEEP STRIKE). "
        "Porte par #447 -- cf. `probe_447_add_caster_dynamic_rule.py`.",
        ported_by=("get_caster_not_added_reason", "get_dynamic_invalid_caster_reason")),
    "AddCasterIfAtLeastOneTarget": Role(
        "GATE_ADD_CASTER", READERS["ADD_CASTER"], SELF,
        "`GetValidTargets(...).AllTargets.Count == 0` -> `broken(AddCasterIfAtLeastOneTarget)`."),
    "AddCasterIfAtLeastOneFreeTileInRange": Role(
        "GATE_ADD_CASTER", READERS["ADD_CASTER"], SELF,
        "`TargetingQuery$$HasFreeTilesInRange` faux -> refus."),
    "CasterIsPossibleTarget": Role(
        "GATE_ADD_CASTER", READERS["ADD_CASTER"], SELF,
        "RE-APPLIQUE la cascade CIBLE complete au caster pris comme cible. Egalement lu, en "
        "DECLARATIF, par `TargetingOptions$$get_CanTargetCaster`. Ni le filtre statique ni "
        "`GetInvalidCasterReason` ne le testent -- mais `GetCasterNotAddedReason`, si."),

    # ---------------------------------------------------------------------------------------
    # PERMISSIONS -- elles DESARMENT, elles ne refusent jamais
    # ---------------------------------------------------------------------------------------
    "AllowSteppableUnit": Role(
        "PERMISSION", READERS["TARGET"], SELF, "Desarme `TargetIsNotSteppable` en mode unit-targeting."),
    "AllowObscuredTargetByElevation": Role(
        "PERMISSION", READERS["LOS"], SELF,
        "Retire le drapeau ELEVATION du masque passe a `<IBattleQuery slot 0xf>`."),
    "AllowObscuredTargetByWalls": Role(
        "PERMISSION", READERS["LOS"], SELF, "Retire le drapeau MURS du meme masque."),
    "AllowObscuredTarget": Role(
        "PERMISSION", READERS["LOS"], SELF,
        "COMPOSITE (elevation | murs) -- le seul membre de l'enum a plusieurs bits. "
        "`TargetingQuery$$GetObscuredTileReasons` l'ECRIT dans les options avant d'enumerer."),
    "AllowIgnoreForcedAttackTarget": Role(
        "PERMISSION", READERS["TARGET"], SELF, "Desarme le TAUNT (`TargetIsAllowedForCaster`)."),
    "AllowUntargetableTarget": Role(
        "PERMISSION", READERS["TARGET"], SELF, "Desarme `TargetIsTargetable`."),
    "AllowUnwalkableTargetTile": Role(
        "PERMISSION", READERS["TARGET"], SELF,
        "Desarme le refus « tuile-cible non marchable » de la tete de domaine TUILE."),
    "AllowTargetWithoutTile": Role(
        "PERMISSION", READERS["UNITS_IN_RANGE"], SELF,
        "Lu par `TargetingQuery$$GetUnitsInRange` : fait entrer dans l'enumeration les unites "
        "sans tuile. Aucune cascade de refus ne le lit -- c'est un elargisseur d'ENUMERATION."),

    # ---------------------------------------------------------------------------------------
    # LUS HORS DU CIBLAGE -- c'est pourquoi les huit lecteurs relus par #429 ne les voyaient pas
    # ---------------------------------------------------------------------------------------
    "AbilityIsNotDisabledByConfigModification": Role(
        "REASON", READERS["DYNAMIC_RULE"], SELF,
        "#429-r1 : CODE DE RAISON PRODUIT par une regle DYNAMIQUE d'ability, jamais un bit teste. "
        "`AnnihilatorBeamAbility$$GetDynamicInvalidTargetReason` rend ce membre quand "
        "`AbilityConfiguration.GetNumberConstant(0x11) <= 0` (la meme constante que "
        "`StaticBattleRules.ActiveAbility$$IsDisabled` teste en premier) -- c'est-a-dire quand une "
        "MODIFICATION DE CONFIG a mis l'ability a zero. Contexte i2 : "
        "`UI/GuildBossSupportingBattle_Modification_Ability_AnnihilatorBeam_nrOfTargets_*` "
        "(« {ABILITY_NAME} targets {N} fewer hexes ») ; le terme d'infobulle "
        "`Tooltips$$BattleHUD_Tooltip_AbilityDisabledByConfigModification_Description` est ce qui "
        "PRESENTE ce code. Il remonte par le point d'extension `TargetMatchesDynamicRule` (bit 1), "
        "qui rend le code de la delegue TEL QUEL. Un SEUL producteur dans tout le binaire (scan "
        "d'instructions, `probe_429r1_bit_readers_scan.py`), et son ability (1071) n'est pas portee."),
    "AllowDeadTarget": Role(
        "GATE_OPERATION", READERS["CONTINUE_ON_DEAD"], "`TargetingOptionsForContinue` (+0xb0), PAS "
        "le masque principal (+0x70)",
        "#429-r1 : LU, mais hors ciblage -- d'ou l'echec des huit lecteurs relus. "
        "`AActiveAbility$$CanContinueOnDeadTarget` (slot 17 d'`IActiveAbility`) rend "
        "`_targetingOptionsForContinue.Rules >> 0x26 & 1`, et "
        "`ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` en fait le gate CIBLE-MORTE, en "
        "TETE d'`ExecuteInternal`. Le masque lu est celui du CONTINUE "
        "(`GetTargetingOptionsForContinue() ?? targetingOptions`) : aucun `TARGETING_OPTIONS` du "
        "registre ne peut donc porter ce bit, et compter ses porteurs sur le masque principal rend "
        "un ZERO DE METHODE. Un seul porteur dans tout le binaire : "
        "`GreatFrostAxeAbility$$GetTargetingOptionsForContinue` (1089).",
        ported_by=("can_continue_on_dead_target", "AllowDeadTarget")),
}
