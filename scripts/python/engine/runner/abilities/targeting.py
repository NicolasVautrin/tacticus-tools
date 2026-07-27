"""GATE DE CIBLE d'une ability active (#115) — le maillon GENERIQUE + son point d'extension.

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` REFUSE un cast dont la cible est
illegale, AVANT le premier `AActiveAbility.Execute` de la behaviour ET avant
`IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` (d'ou l'observable
mesuree en #111 : `mutated=false`, `actionConsumed=false`, 2 evenements, groupe 12
`User_UseAbility` — ouvert par le handler de message EN AMONT du gate, puis referme aussitot).

CHAINE NATIVE (decompile = verite ; build gqfc5mff6c) :

    IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal
      -> IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget
           construit un delegue sur l'ability et teste
           `IdunBattle.Core.Services.IBrokenTargetingRuleExtensions$$IsInvalid` du resultat.
           Le delegue est l'une des deux lambdas de son DisplayClass :
             `...ActiveAbilityOperation.u003Cu003Ec__DisplayClass9_0$$u003CIsInvalidTargetu003Eb__0`
               = slot 7   -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason`
             `...ActiveAbilityOperation.u003Cu003Ec__DisplayClass9_0$$u003CIsInvalidTargetu003Eb__1`
               = slot 0xe -> `AActiveAbility$$GetInvalidTargetReasonForContinue`
           (b__1 = mode « continue » d'une ability multi-etapes, 2e jeu de TargetingOptions @+0xb0 ;
            le cast top-level passe par b__0.)
      -> IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason
           -> `AActiveAbility$$SetConfigValuesInTargetingOptions` :
              `options.Range <- AbilityConfiguration.GetNumberConstant(config, 0x16)` quand
              l'ability lit sa portee de la config et que `options.Range` n'est pas deja pose.
           -> `AActiveAbility$$GetInvalidTargetReasonWithRules` (slot iface +3 de `this+0x58`)
              -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (5 args) :
                   `GetRange` puis `GetInvalidCasterReason` (regles CASTER, hors perimetre #115)
                   puis
                 `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (7 args)
                   = LE FILTRE STATIQUE : une cascade de regles, chacune GATEE PAR UN BIT des
                   `TargetingOptions.Rules` (`IdunBattle.Core.Services.TargetingRule`, flags 64 bits
                   lus a `options+0x28`). La 1re regle rompue rend un `IBrokenTargetingRule`
                   (`IdunBattle.Core.Services.TargetingRuleExtensions$$GenericBrokenTargetingRule`).

OU ENTRE LE `GetDynamicInvalidTargetReason` D'UNE ABILITY — c'est la piece de decoupage :
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` copie les `TargetingOptions` du ctor de la
sous-classe dans `this+0x70..0xaf`, puis **ECRASE** les deux derniers qwords :

    param_1[0x14] (= options+0x30) <- delegue lie au slot vtable `this+0x470`
    param_1[0x15] (= options+0x38) <- `IdunBattle.Core.Services.TargetingOptions.DynamicTargetingTargetRule`
                                      liee au slot vtable `this+0x480` = `GetDynamicInvalidTargetReason`

et le filtre statique invoque cette regle-delegue UNIQUEMENT si le bit `TargetMatchesDynamicRule`
(0x2) est pose :

    if ((options.Rules & 0x2) != 0) {
        long reason = options[0x38].Invoke(caster, casterTiles, target, ...);
        if (reason != 0) return GenericBrokenTargetingRule(reason);
    }

=> **GENERIQUE** = ce module (la cascade + les `TargetingOptions`), consomme par TOUTES les abilities.
   **PROPRE a une ability** = `get_dynamic_invalid_target_reason` (`ActiveAbility`, abilities/base.py),
   un PATRON a instancier par ability qui pose le bit 0x2. 1re instanciation : Waaagh (1058), cf.
   `engine/runner/abilities/orks.py`.

------------------------------------------------------------------------------------------------
INVENTAIRE des regles du filtre statique (ordre NATIF de la cascade 7-args) et etat du port.
Une regle NON PORTEE ne refuse JAMAIS (degradation PERMISSIVE — meme convention que « ability non
portee => behaviour no-op ») : le port ne peut pas inventer un refus qu'il ne sait pas decider.

TOUS LES NOMS CI-DESSOUS SONT CEUX DU DUMP du build courant. Ils l'ont ete tardivement : le
dumper lisait les enums en `readS32()`, donc `TargetingRule` (64 bits) perdait ses 27 membres
au-dessus du bit 31 -- ils tronquaient tous vers 0 et s'ecrasaient dans une map keyee par valeur.
Cette table portait donc des PARAPHRASES entre parentheses (« machine-targeting »,
« HasSteppableUnit »…) la ou le binaire avait un nom. Corrige le 2026-07-27 ;
`scripts/python/probe_targeting_rule_bits.py` confronte desormais les 58 bits au dump du build
courant et ECHOUE si l'un d'eux bouge -- ce qui invaliderait d'un coup tous les masques
`TARGETING_OPTIONS` du registre.

  bit  masque                nom (enum IdunBattle.Core.Services.TargetingRule)   port
  ---  --------------------  -------------------------------------------------  --------------------
   6   0x40                  TargetIsTile                                        NON (domaine TILE)
  44   0x100000000000        TargetIsMachine                                     NON
  46   0x400000000000        TargetIsActor                                       NON
  39   0x8000000000          TargetIsCaster (`caster != GetUnit(target)` => refus) OUI
  10   0x400                 TargetIsFriendly                                    OUI
  14   0x4000                TargetIsEnemy (`UnitsCanAttackEachOther`)           OUI
  23   0x800000              TargetIsAllowedForCaster (`GetOnlyTargets`, Taunt)  NON (forced-targets)
  18   0x40000               TargetIsDisplaceable                                NON
  29   0x20000000            TargetIsTargetable (sauf bit 41                     OUI
                             AllowUntargetableTarget)
  51   0x8000000000000       TargetIsNotSteppable                                NON
  47/48/49                   TargetHas1Tiles / TargetHas3Tiles / TargetHas7Tiles NON
   -   (non gate)            portee : `dist(casterTiles, target) > GetRange` ->  NON (cf. ci-dessous)
                             TargetIsInRange (bit 27, 0x8000000)
   -   (non gate)            `GetTilesObscuringTerrain` (ligne de vue)           NON
  13   0x2000                TargetIsSummon (`HasTrait(2)`)                      NON
  50   0x4000000000000       TargetIsHero (`HasTrait(0x10)` requis)              NON
  33   0x200000000           TargetIsNotAnObject (`HasTrait(0xd)` interdit)      NON
   8   0x100                 TargetIsHealable                                    NON
  16   0x10000               TargetIsRepairable                                  NON
   5   0x20                  TargetHasFreeAdjacentTile                           NON
  21   0x200000              CasterHasFreeAdjacentTile                           NON
  12   0x1000                TargetTileIsFree (`CanAddUnit`)                     NON (domaine TILE)
  17   0x20000               TargetTileIsFreeOrEnemy                             NON (domaine TILE)
  19   0x80000               TargetTileHasEnemyUnit                              NON (domaine TILE)
  32   0x100000000           TargetIsNotAdjacent (battleQuery slot 0x61)         NON
  42   0x40000000000         TargetIsNotAdjacentToEnemy (battleQuery slot 0x7f)  NON
   1   0x2                   TargetMatchesDynamicRule                            OUI (point d'extension)
  57   0x200000000000000     TargetIsCasterOrEnemy (self OU ennemi attaquable)   OUI

BITS QUI NE SONT PAS DES REGLES DE REFUS (verifie exhaustivement sur les DEUX cascades) : le bit 15
`CanTargetCaster` (0x8000) n'apparait NI dans le filtre cible NI dans `GetInvalidCasterReason` — c'est un
flag DECLARATIF, lu par `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` pour les
consommateurs de ciblage (preview / IA). Un port qui en ferait une regle inventerait un refus. Meme
famille : `get_IsTileTargeting` (bit 6), `get_IsUnitTargeting`, `get_IsEnemyTargeting` (bit 14 OU bit 57),
`get_IsCasterOrEnemyTargeting` (bit 57), `get_IsActorTargeting` (bit 46) — des LECTURES du masque, pas des
regles supplementaires.

POURQUOI LA PORTEE N'EST PAS PORTEE ICI : elle n'est PAS gatee par un bit — le natif la teste pour
toute ability dont `options+0x0d` est nul, avec la valeur rendue par
`IdunBattle.Core.Services.TargetingQuery$$GetRange` (config `GetNumberConstant(0x16)` PLUS les
modificateurs de portee de l'unite). Un port approximatif de `GetRange` refuserait des casts
LEGAUX (regression silencieuse en self-play) ; le porter demande sa propre RE. Reste donc
NON PORTE, et explicitement : Waaagh, lui, exprime bien une contrainte de distance — mais par son
`GetDynamicInvalidTargetReason` (qui rend justement `TargetIsInRange`), pas par ce volet.

VOLET CASTER : `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` tourne AVANT le
volet cible (overload 5 args). Une seule de ses regles est portee — `CasterHasNotMoved` (0x10),
parce qu'elle tombe gratuitement et qu'elle est MESUREE ; cf. `get_invalid_caster_reason`.

HORS PERIMETRE (autres rejets d'`ExecuteInternal`, meme observable a 2 evenements, non decomposes) :
`IdunBattle.Operations.ActiveAbilityOperation$$IsValidCaster`,
`IdunBattle.Entities.UnitExtensions$$IsAbilityBlocked`, cooldown, mode atomique, et
`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` (cible = unite
MORTE et l'ability ne l'autorise pas — son gate est le virtuel slot 0x11 de l'ability, dont
l'inventaire des overrides n'a pas ete releve : le porter avec un defaut « refuse » casserait les
abilities de resurrection).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..state import State


# --- `IdunBattle.Core.Services.TargetingRule` (enum FLAGS 64 bits, `options+0x28`) --------------
# Valeurs VERBATIM du dump il2cpp (data/il2cpp_full.json, enums) pour les bits < 32 ; les bits >= 32
# n'y figurent pas (le dump tronque l'enum a 32 bits) -> ceux-la sont nommes par leur ROLE lu au
# decompile de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, prefixe `RULE_BIT`.
RULE_VALID_REQUEST = 0x1                       # ValidRequest
RULE_TARGET_MATCHES_DYNAMIC_RULE = 0x2         # TargetMatchesDynamicRule  <- le point d'extension
RULE_CASTER_MATCHES_DYNAMIC_RULE = 0x4         # CasterMatchesDynamicRule
RULE_CASTER_HAS_NOT_MOVED = 0x10               # CasterHasNotMoved
RULE_TARGET_HAS_FREE_ADJACENT_TILE = 0x20      # TargetHasFreeAdjacentTile
RULE_TARGET_IS_TILE = 0x40                     # TargetIsTile
RULE_TARGET_IS_HEALABLE = 0x100                # TargetIsHealable
RULE_TARGET_IS_AT_RANGE = 0x200                # TargetIsAtRange (portee EXACTE)
RULE_TARGET_IS_FRIENDLY = 0x400                # TargetIsFriendly
RULE_TARGET_TILE_IS_FREE = 0x1000              # TargetTileIsFree
RULE_TARGET_IS_SUMMON = 0x2000                 # TargetIsSummon
RULE_TARGET_IS_ENEMY = 0x4000                  # TargetIsEnemy
RULE_TARGET_IS_REPAIRABLE = 0x10000            # TargetIsRepairable
RULE_TARGET_TILE_IS_FREE_OR_ENEMY = 0x20000    # TargetTileIsFreeOrEnemy
RULE_TARGET_IS_DISPLACEABLE = 0x40000          # TargetIsDisplaceable
RULE_TARGET_TILE_HAS_ENEMY_UNIT = 0x80000      # TargetTileHasEnemyUnit
RULE_ALLOW_STEPPABLE_UNIT = 0x100000           # AllowSteppableUnit
RULE_CASTER_HAS_FREE_ADJACENT_TILE = 0x200000  # CasterHasFreeAdjacentTile
RULE_TARGET_IS_ALLOWED_FOR_CASTER = 0x800000   # TargetIsAllowedForCaster (forced targets / Taunt)
RULE_TARGET_IS_UNOBSCURED = 0x1000000          # TargetIsUnobscured
RULE_ALLOW_OBSCURED_BY_ELEVATION = 0x2000000   # AllowObscuredTargetByElevation
RULE_ALLOW_OBSCURED_BY_WALLS = 0x4000000       # AllowObscuredTargetByWalls
RULE_ALLOW_OBSCURED_TARGET = 0x6000000         # AllowObscuredTarget (= les deux ci-dessus, valeur
                                               #  COMPOSITE presente telle quelle dans l'enum)
RULE_TARGET_IS_IN_RANGE = 0x8000000            # TargetIsInRange
RULE_CASTER_CAN_MOVE = 0x10000000              # CasterCanMove
RULE_TARGET_IS_TARGETABLE = 0x20000000         # TargetIsTargetable
RULE_ALLOW_NULL_CASTER_TILE = 0x40000000       # AllowNullCasterTile
RULE_CASTER_HAS_COMPLETED_ONE_TURN = 0x80000000  # CasterHasCompletedOneTurn
# Bits >= 32 : le dump il2cpp TRONQUE l'enum a 32 bits alors que le champ est un `long` -> ces
# masques sont nommes par le ROLE lu au decompile du filtre statique, prefixe `RULE_BITnn`.
RULE_BIT39_TARGET_IS_CASTER = 0x8000000000         # la cible DOIT etre le caster (self-only)
RULE_BIT41_ALLOW_NON_TARGETABLE = 0x20000000000    # desactive le controle IsTargetable
# bit 57 : nomme par son getter `IdunBattle.Core.Services.TargetingOptions$$get_IsCasterOrEnemyTargeting`
# (= `(rules >> 0x39) & 1`) -> « la cible doit etre le CASTER lui-meme OU un ennemi attaquable ».
RULE_BIT57_CASTER_OR_ENEMY = 0x200000000000000

# `UnitFlag` 0x11 : `IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(unit, 0x11)`.
UNIT_FLAG_NOT_TARGETABLE = 0x11

# `IdunBattle.Entities.EffectType.FriendlyFire` = 0x67 : lu par
# `IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` — un porteur peut attaquer ses
# AMIS (et seulement eux).
EFFECT_FRIENDLY_FIRE = 0x67


@dataclass(frozen=True)
class TargetingOptions:
    """`IdunBattle.Core.Services.TargetingOptions` — la struct de 0x40 octets que chaque
    `<X>Ability$$.ctor` passe a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`.

    Seul le champ REELLEMENT consomme par ce port est modelise : `rules` = le masque de flags
    `TargetingRule` a `options+0x28` (le litteral que le decompile du ctor donne, ex. Waaagh
    `TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x106004012, 0, 0, 0)`).

    ATTENTION AUX SURCHARGES DU CTOR : certaines abilities utilisent l'overload « PRESET + flags »
    (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor` = preset statique
    `+0x200` + `0x806000000`) : le litteral visible n'est PAS le masque effectif. Un port qui
    recopierait le litteral d'une telle ability serait FAUX -> ne poser `TARGETING_OPTIONS` que sur
    les abilities dont le masque EFFECTIF a ete lu.

    `self_cast` = le BYTE a `options+0x00` (2e argument de l'overload « flags directs »). Ce n'est
    PAS un bit de `Rules` : c'est l'AIGUILLAGE de l'overload 5 arguments de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (cf. `_target_is_caster` et
    `get_caster_not_added_reason` plus bas). Nomme d'apres la factory native
    `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`, qui le pose a
    1 en meme temps que `Rules = TargetIsEnemy` et un `Range` : « ability SELF-CASTEE, legale s'il
    existe au moins un ennemi a portee ». Porteurs du registre : ResurrectionOrb (1009),
    Chronometron (1226), AncestralFortune (1207).

    Les autres champs natifs (`Range` Nullable<int> @+0x10 alimente par
    `AActiveAbility$$SetConfigValuesInTargetingOptions`, les deux regles-delegues @+0x30/+0x38, les
    bornes de stats) ne sont pas modelises : les regles qui les consomment ne sont pas portees (cf.
    l'inventaire en tete), sauf la regle dynamique dont le port passe par la METHODE de l'ability
    (`get_dynamic_invalid_target_reason`) plutot que par un champ delegue."""
    rules: int = 0
    self_cast: bool = False

    def has(self, rule: int) -> bool:
        return bool(int(self.rules) & int(rule))


# ------------------------------------------------------------------------------------------------
# Predicats natifs consommes par la cascade
# ------------------------------------------------------------------------------------------------

def _unit_of(state: "State", entity_id):
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state)` — l'UNITE designee par l'entite.
    Offline le message porte un id d'entite : c'est une unite ssi elle porte un `UnitComponent`.
    None (cible-TUILE, entite absente) = « le port ne sait pas resoudre » -> aucune regle du domaine
    UNITE ne s'applique (degradation permissive, cf. l'inventaire en tete)."""
    from ..components import UnitComponent
    if entity_id is None:
        return None
    e = state.get_entity(int(entity_id))
    if e is None or e.get_component(UnitComponent) is None:
        return None
    return e


def is_actor(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$IsActor` — l'entite AGIT (unite ou machine of war),
    par opposition a une tuile / un objet de decor."""
    from ..components import MachineComponent, UnitComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    if e is None:
        return False
    return (e.get_component(UnitComponent) is not None
            or e.get_component(MachineComponent) is not None)


def units_are_friendly(state: "State", a_id, b_id) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$UnitsAreFriendly` = `battleQuery.<slot 0x90>(a, b)`
    — MEME CAMP. Offline : meme `OwnerComponent.team` (la convention d'equipe de tout le port ;
    les summons heritent de l'equipe de leur summoner, cf. project_summon_team_model)."""
    from ..components import OwnerComponent
    ea = state.get_entity(int(a_id)) if a_id is not None else None
    eb = state.get_entity(int(b_id)) if b_id is not None else None
    oa = ea.get_component(OwnerComponent) if ea is not None else None
    ob = eb.get_component(OwnerComponent) if eb is not None else None
    if oa is None or ob is None:
        return False
    return oa.team == ob.team


def units_can_attack_each_other(state: "State", a_id, b_id) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` — MIRROR du decompile :

        if (!IsActor(a) || !IsActor(b)) return false;
        friendly = UnitsAreFriendly(a, b);
        if (battleQuery.<slot 0x91>(a, b)) return true;            // override, cf. ci-dessous
        if (HasEffect(a, state, 0x67 FriendlyFire, activeOnly)) return friendly;
        return !friendly;

    Le porteur de `FriendlyFire` (0x67) inverse la relation : il ne peut attaquer QUE ses amis.
    Le slot 0x91 (override inconditionnel « oui ») n'est pas porte -> il ne peut qu'AJOUTER des
    cibles legales, donc son absence ne peut que refuser un cast que le natif accepterait : c'est le
    seul residu du gate qui va dans le sens strict, il est signale ici et couvert par la validation
    live (aucune divergence observee)."""
    if not (is_actor(state, a_id) and is_actor(state, b_id)):
        return False
    friendly = units_are_friendly(state, a_id, b_id)
    ff = (state.effects is not None and a_id is not None
          and state.effects.has_effect(int(a_id), effect_type=EFFECT_FRIENDLY_FIRE))
    return friendly if ff else (not friendly)


def is_targetable(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(unit, 0x11)`.
    Le flag 0x11 n'est pose par AUCUN chemin du port (aucun `UnitFlagsComponent.add(0x11)`) -> le
    predicat est constamment vrai offline. Mirror ecrit quand meme : le jour ou le flag sera pose,
    la regle s'activera d'elle-meme (et le lecteur voit que ce n'est pas un oubli)."""
    from ..components import UnitFlagsComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return not (fl is not None and fl.has(UNIT_FLAG_NOT_TARGETABLE))


# ------------------------------------------------------------------------------------------------
# La cascade
# ------------------------------------------------------------------------------------------------

def get_invalid_caster_reason(state: "State", caster_id: int, ability) -> int:
    """`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` — volet CASTER du meme
    filtre, evalue AVANT le volet cible par l'overload 5 arguments de
    `TargetingQuery$$GetInvalidTargetReason` (`if (casterReason.IsInvalid()) return casterReason;`).

    UNE SEULE de ses regles est portee — `CasterHasNotMoved` (0x10) — parce qu'elle tombe
    gratuitement : le bit est deja dans les `TARGETING_OPTIONS` de l'ability et le predicat existe
    deja (`unit_has_moved`). Mirror du decompile :

        if (battleQuery.<slot 0x34>(caster) && (rules & 0x10) != 0) {
            if (!UnitExtensions.DidMove(caster)
                && GetTiles(caster).IsEquivalentTo(casterTiles)) -> ok
            return GenericBrokenTargetingRule(0x10);
        }

    `IdunBattle.Entities.UnitExtensions$$DidMove` = `UnitFlagsComponent.Has(unit, UnitFlag.Moved=0)`
    = exactement `unit_has_moved`. La 2e clause (`casterTiles` != les tuiles REELLES du caster)
    couvre une position de cast HYPOTHETIQUE ; sur le chemin `ExecuteInternal` le natif passe
    `EntityExtensions.GetTiles(caster, state)`, donc les deux listes sont toujours equivalentes ->
    la clause se reduit a `DidMove`. Le prefixe `battleQuery.<slot 0x34>` n'est pas resolu : il ne
    peut que DESARMER la regle, et la MESURE live le montre arme pour une unite de roster (probe
    `probe_115_ability_reason.py` : apres un `move`, le natif rend
    `casterReason = {hex: 0x10, reasons: ["CasterHasNotMoved"]}`).

    NON PORTEES (memes motifs qu'en tete de module) : `CasterCanMove` (0x10000000),
    `CasterHasCompletedOneTurn` (0x80000000), `AllowNullCasterTile` (0x40000000),
    `CasterMatchesDynamicRule` (0x4, regle-delegue `options+0x30` = slot vtable +0x470), les filtres
    de `FeetCount` et les bits 52/53.

    NB `unit_has_moved` lit le `UnitFlagsComponent`, que `load_state` ne seede PAS (le RPC n'expose
    pas les UnitFlags) : sur un etat CHARGE la regle est donc inerte. Elle mord sur le chemin
    replay/self-play OFFLINE, ou c'est `MoveUnitOperation` -> `set_moved_flag` qui pose le flag."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None or not options.has(RULE_CASTER_HAS_NOT_MOVED):
        return 0
    from ..components import unit_has_moved
    return RULE_CASTER_HAS_NOT_MOVED if unit_has_moved(state, int(caster_id)) else 0


def _targets_the_caster(state: "State", caster_id: int, target_id: Optional[int],
                        tuid: Optional[int], options: "TargetingOptions") -> bool:
    """AIGUILLAGE SELF-CAST de l'overload 5 arguments de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` — mirror du decompile :

        if (target != caster) {
            if (!(rules & 0x40) || GetMainTile(target) != caster) {
                if ((rules & 0x40) || GetUnit(target) != caster) goto <filtre statique>;
            }
        }
        return GetCasterNotAddedReason(caster, casterTiles, options, range);

    (le terme `GetMainTile(target) != caster` compare une TUILE au CASTER : il est structurellement
    toujours vrai, c'est une ecriture defensive du decompilateur.) Ne reste donc que : la cible EST
    le caster — directement, ou parce qu'elle resout a l'unite du caster et que l'ability n'est pas
    TILE-targeting."""
    if target_id is not None and int(target_id) == int(caster_id):
        return True
    return (not options.has(RULE_TARGET_IS_TILE)) and tuid is not None and tuid == int(caster_id)


def get_caster_not_added_reason(state: "State", caster_id: int, ability) -> int:
    """`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` — la branche que prend le
    natif quand une ability SELF-CASTEE (`options+0x00 != 0`) est castee SUR SON PROPRE CASTER.
    NON PORTEE -> 0 (permissif), pour la meme raison que la portee : sa decision depend d'un etage
    non porte.

    DECOMPILE (rules = `options+0x28`) :

        if ((char)rules < 0) return valide;                       # bit 7 pose -> court-circuit
        if (rules & 0x8) {                                        # bit 3 : regle-delegue caster
            r = options[+0x30].Invoke(caster, casterTiles); if (r) return broken(r);
        } else if (rules & 0x400000) {                            # bit 22 CasterHasFreeAdjacentTile
            if (!HasFreeTilesInRange(1, caster, tiles, options, range)) return broken(0x400000);
        } else if (options+0x00 == 0 && !(rules & 0x800)) {
            if (rules & 0x8000)                                   # bit 15 CanTargetCaster
                { r = <filtre statique>(target = caster); if (r invalide) return r; }
        } else {
            vt = TargetingQuery.GetValidTargets(caster, tiles, options, 1, 1);
            if (vt.AllTargets.Count == 0) return broken(0x800);   # AddCasterIfAtLeastOneTarget
        }
        return valide;

    POURQUOI 0 : sur le chemin qui nous concerne (`options+0x00 != 0`, et aucune des 3 abilities
    self-castees du registre ne pose les bits 3 / 7 / 22), le verdict est
    `GetValidTargets(...).AllTargets.Count == 0`. `GetValidTargets` enumere TOUTES les cibles
    legales, donc consomme `IdunBattle.Core.Services.TargetingQuery$$GetRange` — le volet PORTEE,
    explicitement NON PORTE (cf. l'inventaire en tete : un `GetRange` approximatif refuserait des
    casts LEGAUX). Rendre 0x800 « au juge » inventerait un refus ; rendre 0 degrade du cote
    PERMISSIF, la convention de tout ce module.

    MESURE (probe `probe_targeting_masks_lot4.py`, Chronometron 1226 self-cast, ennemis hors du
    disque range 2) : le natif rend bien `0x800 AddCasterIfAtLeastOneTarget`. C'est le seul ecart
    connu, et il est du BON cote (le port accepte un cast que le natif refuse)."""
    return 0


def get_invalid_target_reason(state: "State", caster_id: int, target_id: Optional[int],
                              ability) -> int:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason` (-> ...WithRules ->
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) : rend le PREMIER
    `TargetingRule` rompu, dans l'ORDRE NATIF de la cascade, ou 0 (cible valide).

    `ability` = l'instance d'`ActiveAbility` portee. Ses `TARGETING_OPTIONS` (litteral du ctor natif)
    sont la SEULE source des bits : options absentes (`None`) = donnee non RE-lue -> AUCUN gate
    (jamais de refus invente).

    Regles portees uniquement — l'inventaire complet et le motif de chaque non-port sont en tete de
    module."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return 0
    target_unit = _unit_of(state, target_id)
    tuid = None if target_unit is None else int(target_id)

    # AIGUILLAGE SELF-CAST -- AVANT le filtre statique, comme le natif : l'overload 5 arguments
    # BRANCHE sur `GetCasterNotAddedReason` (et n'evalue JAMAIS la cascade) des lors que
    # `options+0x00 != 0` ET que la cible est le caster. Sans ce branchement le port appliquerait le
    # filtre statique a un self-cast et refuserait sur `TargetIsEnemy` un cast que le natif JUGE PAR
    # UN AUTRE CHEMIN -- exactement le FAUX REFUS que le gate doit eviter (mesure : Chronometron
    # 1226, natif `0x800`, port `0x4000` avant ce correctif).
    if options.self_cast and _targets_the_caster(state, caster_id, target_id, tuid, options):
        return get_caster_not_added_reason(state, caster_id, ability)

    # bit 39 -- « la cible DOIT etre le caster » : `if (rules & 0x8000000000 && caster != GetUnit(target))`
    if options.has(RULE_BIT39_TARGET_IS_CASTER) and tuid is not None and tuid != int(caster_id):
        return RULE_BIT39_TARGET_IS_CASTER

    # bit 10 TargetIsFriendly -- mirror du decompile :
    #   if (IsMachine(caster))  ok <- battleQuery.<slot 0x90>(caster, target)
    #   else if (IsUnit(caster) && IsUnit(target) && !HasEffect(TARGET, 0x67 FriendlyFire, active))
    #        ok <- UnitsAreFriendly(caster, target)
    #   sinon -> broken(0x400)
    # ATTENTION : c'est l'effet `FriendlyFire` de la **CIBLE** qui est lu ici (contraste avec
    # `UnitsCanAttackEachOther`, qui lit celui de l'ATTAQUANT) -- une cible sous FriendlyFire n'est
    # plus « amie » de personne. La branche MACHINE (slot 0x90 direct) tombe sur le meme predicat
    # d'equipe offline.
    if options.has(RULE_TARGET_IS_FRIENDLY) and tuid is not None:
        ff = (state.effects is not None
              and state.effects.has_effect(tuid, effect_type=EFFECT_FRIENDLY_FIRE))
        if ff or not units_are_friendly(state, caster_id, tuid):
            return RULE_TARGET_IS_FRIENDLY

    # bit 14 TargetIsEnemy -- `if (!UnitsCanAttackEachOther(caster, target)) -> broken(0x4000)`.
    if options.has(RULE_TARGET_IS_ENEMY) and tuid is not None:
        if not units_can_attack_each_other(state, caster_id, tuid):
            return RULE_TARGET_IS_ENEMY

    # bit 29 TargetIsTargetable -- controle INVERSE : il s'applique SAUF si le bit 41 est pose.
    if (not options.has(RULE_BIT41_ALLOW_NON_TARGETABLE)) and tuid is not None:
        if not is_targetable(state, tuid):
            return RULE_TARGET_IS_TARGETABLE

    # bit 1 TargetMatchesDynamicRule -- LE POINT D'EXTENSION : la regle-delegue posee par
    # `AActiveAbility$$.ctor` a `options+0x38` (`TargetingOptions.DynamicTargetingTargetRule` liee au
    # slot vtable +0x480) = le `GetDynamicInvalidTargetReason` de la sous-classe. Place ici comme
    # dans le natif : APRES les regles statiques, avant le retour « valide ».
    if options.has(RULE_TARGET_MATCHES_DYNAMIC_RULE):
        reason = int(ability.get_dynamic_invalid_target_reason(state, caster_id, target_id) or 0)
        if reason:
            return reason

    # bit 57 CasterOrEnemyTargeting -- DERNIERE regle de la cascade native (juste avant le retour
    # « valide »), mirror du decompile :
    #     if ((rules >> 0x39) & 1) && caster != GetUnit(target)
    #        && !UnitsCanAttackEachOther(caster, target)  ->  broken(0x200000000000000)
    # = « la cible doit etre le CASTER LUI-MEME ou un ennemi attaquable ». C'est un TargetIsEnemy
    # ASSOUPLI par la tolerance du self-cast -- a ne pas confondre avec le bit 14 (0x4000), qui refuse
    # le self. Porteur du lot : HarbingerOfDestruction (1008), dont la branche
    # `If(AreEqual(caster, target), ...)` de l'ExecuteBehaviour est exactement la contrepartie de cette
    # tolerance. `tuid is None` (cible non-unite) -> le port ne sait pas decider : permissif, meme
    # convention que les autres regles du domaine UNITE.
    if options.has(RULE_BIT57_CASTER_OR_ENEMY) and tuid is not None:
        if tuid != int(caster_id) and not units_can_attack_each_other(state, caster_id, tuid):
            return RULE_BIT57_CASTER_OR_ENEMY

    return 0


def is_invalid_target(state: "State", caster_id: int, target_id: Optional[int], ability) -> int:
    """`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` — rend le `TargetingRule`
    rompu (non nul = REFUS) ou 0. Le natif enveloppe le resultat dans un `IBrokenTargetingRule` et
    teste `IdunBattle.Core.Services.IBrokenTargetingRuleExtensions$$IsInvalid` ; cote port le code
    de raison EST le verdict (0 = `TargetingRule.None`).

    `ability = None` (ability non portee : `ABILITY_CLASSES` ne la connait pas) -> 0 : ses
    `TargetingOptions` sont inconnues, on ne peut pas decider -> aucun gate.

    ORDRE natif (overload 5 args de `TargetingQuery$$GetInvalidTargetReason`) : volet CASTER
    d'abord (`GetInvalidCasterReason`, dont seul `CasterHasNotMoved` est porte), volet CIBLE
    ensuite. Le natif renvoie la raison CASTER telle quelle si elle est rompue — d'ou le meme code
    dans `casterReason` ET `targetReason` de l'oracle `abilityReason` (mesure du probe #115)."""
    if ability is None:
        return 0
    caster_reason = get_invalid_caster_reason(state, caster_id, ability)
    if caster_reason:
        return caster_reason
    return get_invalid_target_reason(state, caster_id, target_id, ability)
