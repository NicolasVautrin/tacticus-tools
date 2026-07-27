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
   un PATRON a instancier par ability qui pose `TargetMatchesDynamicRule`. 1re instanciation :
   Waaagh (1058), cf.
   `engine/runner/abilities/orks.py`.

------------------------------------------------------------------------------------------------
INVENTAIRE des regles du filtre statique (ordre NATIF de la cascade 7-args) et etat du port.
Une regle NON PORTEE ne refuse JAMAIS (degradation PERMISSIVE — meme convention que « ability non
portee => behaviour no-op ») : le port ne peut pas inventer un refus qu'il ne sait pas decider.

TOUS LES NOMS CI-DESSOUS SONT CEUX DE L'ENUM NATIF, et ce module n'en declare AUCUN : il les lit
dans `engine/runner/abilities/targeting_rule.py`, mirror 1:1 GENERE par
`scripts/python/gen_targeting_rule.py` depuis `data/symbols/<build>/frida/enums.tsv`. C'est la
SEULE source de noms de bits du port -- une deuxieme table, meme juste le jour ou on l'ecrit,
devient fausse au re-dump suivant sans que rien ne le dise. Trois gardes tiennent l'invariant :
`test_ability_registry_ratchet.py` (aucune constante de ciblage declaree ailleurs, aucun bit cite
par sa valeur brute, module genere == dump) et `probe_targeting_rule_bits.py` (qui y ajoute la
table de noms cote hooks, `frida/hooks/data/targeting-rule-names.ts`).

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
  29   0x20000000            TargetIsTargetable (sauf si                        OUI
                             AllowUntargetableTarget est pose)
  51   0x8000000000000       TargetIsNotSteppable                                NON
  47/48/49                   TargetHas1Tiles / TargetHas3Tiles / TargetHas7Tiles NON
   -   (non gate)            portee : `dist(casterTiles, target) > GetRange` ->  OUI (cf. ci-dessous)
                             TargetIsInRange (bit 27, 0x8000000) ; variante
                             EXACTE sous le bit 9 TargetIsAtRange (0x200)
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

BITS QUI NE SONT PAS DES REGLES DE REFUS (verifie exhaustivement sur les DEUX cascades) :
`CasterIsPossibleTarget` (bit 15) n'apparait NI dans le filtre cible NI dans `GetInvalidCasterReason`
— c'est un flag DECLARATIF, lu par `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster`
pour les consommateurs de ciblage (preview / IA). Un port qui en ferait une regle inventerait un
refus. Meme famille : `get_IsTileTargeting` (`TargetIsTile`), `get_IsUnitTargeting`,
`get_IsEnemyTargeting` (`TargetIsEnemy` OU `TargetIsCasterOrEnemy`), `get_IsCasterOrEnemyTargeting`,
`get_IsActorTargeting` (`TargetIsActor`) — des LECTURES du masque, pas des regles supplementaires.

LE VOLET PORTEE (#241) — il n'est GATE PAR AUCUN BIT, donc son armement ne vient pas de `Rules`
mais du champ `TargetingRange` des options (`options+0x08..0x1f`). Extrait VERBATIM du filtre
statique (surcharge 7 arguments, `range` = la valeur rendue par
`IdunBattle.Core.Services.TargetingQuery$$GetRange`) :

    if (!ignoreRangeChecks) {                        # param 6, faux sur le chemin ExecuteInternal
        if (!range.OnlyAdjacent) {                   # Range+0x04
            if (!options.Range.UseWholeBoard) {      # options+0x0d
                d = movementQuery.GetDistance(casterTiles, target);
                if ((rules & 0x200 TargetIsAtRange) == 0) { if (range.Value < d) -> broken(TargetIsInRange) }
                else                                  { if (d != range.Value)   -> broken(TargetIsAtRange) }
            }
        } else if (!battleQuery.AreEntitiesAdjacent(casterTiles, target)) -> broken(TargetIsInRange)
        <ligne de vue : GetTilesObscuringTerrain, NON PORTEE>
    }

TROIS regimes, donc, et il faut les distinguer AVANT tout calcul de distance :
  * `UseWholeBoard`      -> **aucun** test de portee (le plateau entier est a portee) ;
  * `Range.OnlyAdjacent` -> test d'ADJACENCE, pas de distance <= N ;
  * sinon                -> `hexDistance <= Range.Value` (ou `== Range.Value` sous `TargetIsAtRange`).

`GetRange` et sa decomposition : cf. la section dediee plus bas (`get_range`). ARMEMENT : le champ
`TargetingOptions.range` du port vaut `None` tant que le `TargetingRange` de l'ability n'a pas ete
LU au ctor decompile — et `None` = aucun gate de portee, meme convention permissive que le reste du
module. Un `TargetingRange` DEVINE refuserait des casts LEGAUX, c'est-a-dire l'exacte regression que
ce volet doit eviter : on ne renseigne que ce qu'on a lu.

NE PAS DOUBLER WAAAGH : son `TargetingRange` est le preset `UseWholeBoard`
(`IdunBattle.Core.Services.TargetingRange$$.cctor`, statics+0x48) -> le volet generique ne teste
RIEN pour lui. Sa contrainte de distance vit ENTIEREMENT dans son
`WaaaghAbility$$GetDynamicInvalidTargetReason` (qui rend justement `TargetIsInRange`). Meme lecture
pour les 8 autres porteurs `UseWholeBoard` du registre.

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

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Optional

from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ..state import State


# `UnitFlag` 0x11 : `IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(unit, 0x11)`.
UNIT_FLAG_NOT_TARGETABLE = 0x11

# `IdunBattle.Entities.EffectType.FriendlyFire` = 0x67 : lu par
# `IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` — un porteur peut attaquer ses
# AMIS (et seulement eux).
EFFECT_FRIENDLY_FIRE = 0x67

# `IdunBattle.Entities.Enum.EffectType.ForcedInMelee` = 0x529 : lu par
# `IdunBattle.Core.Services.TargetingQuery$$GetRange` — le porteur ne porte plus qu'a 1 (adjacence).
EFFECT_FORCED_IN_MELEE = 0x529

# `IdunBattle.Core.Services.RangedBool` (enum, dump VERBATIM) — un booleen a DEUX valeurs constantes
# et deux valeurs CALCULEES sur le caster ; resolu par
# `IdunBattle.Core.Services.RangedBoolExtensions$$IsTrue`.
RANGED_BOOL_TRUE = 0
RANGED_BOOL_FALSE = 1
RANGED_BOOL_IF_RANGED_CASTER = 2
RANGED_BOOL_IF_NOT_RANGED_CASTER = 3

# `IdunBattle.Entities.Enum.UnitTrait.Ranged` = 0xb ; `.Steppable` = 0x1b — lus respectivement par
# `IdunBattle.Entities.UnitExtensions$$IsRanged` et `IdunBattle.Entities.TileExtensions$$HasSteppableUnit`.
UNIT_TRAIT_RANGED = 0xb
UNIT_TRAIT_STEPPABLE = 0x1b

# `IdunBattle.Configuration.AbilityConstantType.range` = 0x16 — la constante que
# `IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` recopie dans
# `options.Range.OverrideRange` quand `UseRangeFromConfig` est pose. Cle gameconfig : `constants.range`.
ABILITY_CONSTANT_RANGE = "range"


@dataclass(frozen=True)
class TargetingRange:
    """`IdunBattle.Core.Services.TargetingRange` — la struct de 0x18 octets logee a
    `TargetingOptions+0x08`. Champs et offsets lus au ctor
    (`IdunBattle.Core.Services.TargetingRange$$.ctor(onlyAdjacent, useRangeFromConfig,
    useWholeBoard, overrideRange, overrideRangeFunc)`) :

        +0x00  RangedBool onlyAdjacent          (int)
        +0x04  bool       useRangeFromConfig
        +0x05  bool       useWholeBoard          <- le fameux `options+0x0d` du filtre statique
        +0x08  Nullable<int> overrideRange
        +0x10  GetRange   overrideRangeFunc      (delegue ; AUCUN porteur du registre ne le pose)

    `overrideRangeFunc` n'est pas modelise : le seul chemin qui l'alimente est
    `IdunBattle.Core.Services.TargetingRange$$CustomRange(GetRange)`, qu'aucun `<X>Ability$$.ctor`
    du registre n'appelle (les 28 masques ont ete relus un par un). Le jour ou un porteur l'utilise,
    son `TargetingRange` restera `None` (= non RE-lu = pas de gate) tant qu'on ne l'aura pas lu."""
    only_adjacent: int = RANGED_BOOL_FALSE
    use_range_from_config: bool = False
    use_whole_board: bool = False
    override_range: Optional[int] = None


# --- Les 5 `TargetingRange` STATIQUES, ecrits par `IdunBattle.Core.Services.TargetingRange$$.cctor`
#     dans le bloc de statiques de la classe. Le dump il2cpp ne porte pas les NOMS des champs
#     statiques -> on les designe par leur OFFSET dans ce bloc (offset RELATIF, comme les presets
#     `TargetingOptions` deja cites dans `darkangels.py`), et on les NOMME par leur contenu.
RANGE_ADJACENT_IF_MELEE_CASTER = TargetingRange(only_adjacent=RANGED_BOOL_IF_NOT_RANGED_CASTER)
"""statics+0x00 — `onlyAdjacent = IfNotRangedCaster`, rien d'autre : un caster de MELEE ne touche
que l'adjacence, un caster RANGED retombe sur la portee d'arme. Profil de l'attaque normale."""

RANGE_FROM_CONFIG = TargetingRange(use_range_from_config=True)
"""statics+0x18 — `useRangeFromConfig = true` : `AActiveAbility$$SetConfigValuesInTargetingOptions`
pose `overrideRange = AbilityConfiguration.GetNumberConstant(0x16 range)`."""

RANGE_ADJACENT = TargetingRange(only_adjacent=RANGED_BOOL_TRUE, override_range=1)
"""statics+0x30 — `onlyAdjacent = True` + `overrideRange = 1` : cible ADJACENTE, point."""

RANGE_WHOLE_BOARD = TargetingRange(use_whole_board=True)
"""statics+0x48 — `useWholeBoard = true` : le filtre statique NE TESTE PAS la portee."""

RANGE_SELF = TargetingRange(override_range=0)
"""statics+0x60 — `overrideRange = 0` : portee nulle (self / cast sans cible distante)."""


def custom_range(value: int) -> TargetingRange:
    """`IdunBattle.Core.Services.TargetingRange$$CustomRange(int range)` — mirror du decompile :
    `{ onlyAdjacent = False, useRangeFromConfig = false, useWholeBoard = false,
       overrideRange = Nullable(range), overrideRangeFunc = null }`."""
    return TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=int(value))


@dataclass(frozen=True)
class Range:
    """`IdunBattle.Core.Services.TargetingQuery.Range` — la valeur de retour de
    `TargetingQuery$$GetRange`, 8 octets : `{ int Value @+0x00 ; bool OnlyAdjacent @+0x04 }`.
    (Le filtre statique lit le champ `@+0x04` pour choisir entre `AreEntitiesAdjacent` et la
    comparaison de distance — c'est ce qui fixe l'ordre des deux champs.)"""
    value: int = 0
    only_adjacent: bool = False


@dataclass(frozen=True)
class TargetingOptions:
    """`IdunBattle.Core.Services.TargetingOptions` — la struct de 0x40 octets que chaque
    `<X>Ability$$.ctor` passe a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`.

    Layout LU sur `IdunBattle.Core.Services.TargetingOptions$$.ctor` (surcharge « flags directs »,
    `.ctor(isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
    getDynamicInvalidTargetReason)`), qui ecrit :

        +0x00 <- isSelfCasting (byte)      +0x20 <- forceMeleeTarget (RangedBool)
        +0x08 <- range (TargetingRange)    +0x28 <- rules (TargetingRule, 64 bits)
                 (3 qwords, 0x08..0x1f)    +0x30/+0x38 <- les deux regles-delegues

    `rules` = le masque de flags `TargetingRule` a `options+0x28` (le litteral que le decompile du
    ctor donne, ex. Waaagh
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

    `range` / `force_melee_target` = les deux entrees du volet PORTEE (cf. `get_range`). `range` a
    `None` pour DEFAUT DELIBERE : « `TargetingRange` non RE-lu » -> aucun gate de portee. Les deux se
    lisent dans le MEME appel de ctor et se posent donc ENSEMBLE, jamais l'un sans l'autre (les
    presets `TargetingOptions` statiques portent les deux aussi : `<preset>+0x08..0x1f` et
    `<preset>+0x20`, ecrits par `IdunBattle.Core.Services.TargetingOptions$$.cctor`).

    Les autres champs natifs (les deux regles-delegues @+0x30/+0x38) ne sont pas modelises : la
    regle dynamique passe par la METHODE de l'ability (`get_dynamic_invalid_target_reason`) plutot
    que par un champ delegue, et la regle-delegue CASTER (@+0x30) n'est pas portee."""
    rules: int = 0
    self_cast: bool = False
    range: Optional[TargetingRange] = None
    force_melee_target: int = RANGED_BOOL_FALSE

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
# VOLET PORTEE — `IdunBattle.Core.Services.TargetingQuery$$GetRange` et ses dependances
# ------------------------------------------------------------------------------------------------

def _visual_id(state: "State", unit_id) -> Optional[str]:
    """`visualId` gameconfig de l'entite (le `StatsComponent.ctx` d'abord, le `UnitComponent`
    ensuite — meme resolution que `_faction_id` cote triggers)."""
    from ..components import StatsComponent, UnitComponent
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return None
    sc = e.get_component(StatsComponent)
    if sc is not None and getattr(sc.ctx, "visual_id", None):
        return sc.ctx.visual_id
    uc = e.get_component(UnitComponent)
    return uc.visual_id if uc is not None else None


def _unit_traits(state: "State", unit_id) -> tuple:
    """Traits gameconfig de l'unite (noms). `BaseUnitComponent$$HasTrait` cote natif ; offline le
    porteur des traits INNES est le kit gameconfig, deja materialise dans `UnitContext.traits`."""
    import gameconfig as GC
    vid = _visual_id(state, unit_id)
    if not vid:
        return ()
    return tuple((GC.unit(vid) or {}).get("traits") or ())


def unit_weapon_range(visual_id: Optional[str], stats) -> Optional[int]:
    """LES TROIS BRANCHES D'ARME de `IdunBattle.Core.Services.TargetingQuery$$GetRange` — la portee
    « naturelle » d'une unite, AVANT tout override des `TargetingOptions`. Mirror du decompile :

        if (!UnitExtensions.HasAnyWeapon(caster))    range = GetStat(caster, StatType.Range = 2)
        else if (!UnitExtensions.HasRangedWeapon(c)) range = 1
        else {
            w     = TargetingQuery.FindLongestRangedWeapon(caster)   # max Range parmi les NON-melee
            bonus = w.Select(_ => _.Range.Value) ?? 1
            range = GetStat(caster, StatType.ExtraRange = 0x18) + bonus
        }

    `stats` = un porteur de `get_stat(StatType)` (`UnitContext` ou `UnitStats`) ; None -> extra 0.

    **`None` = NON OBSERVABLE**, et c'est la 1re branche : `StatType.Range` (2, marque
    `[Obsolete] Idun Concept`) n'est PAS dans le catalogue de `combatSnapshot` -> `get_stat(2)`
    rendrait 0, ce qui n'est pas la valeur native mais l'absence de mesure. Or 81 unites du
    gameconfig n'ont AUCUNE arme (les Machines of War et les objets de decor) : rendre 0 pour elles
    ferait refuser TOUTES leurs cibles. On rend donc None, que l'appelant traduit en « pas de gate ».

    Source d'arme = gameconfig (`weapons[].Range`, absent = arme de MELEE) : c'est le meme substrat
    que `WeaponsComponent`, dont le natif tire `HasAnyWeapon` / `HasRangedWeapon` /
    `FindLongestRangedWeapon`."""
    import gameconfig as GC
    from ...entities.stats import StatType
    weapons = ((GC.unit(visual_id or "") or {}).get("weapons")) or []
    if not weapons:
        return None                                   # branche `!HasAnyWeapon` : non observable
    ranged = [int(w.get("Range") or 0) for w in weapons if w.get("Range")]
    if not ranged:
        return 1                                      # branche `!HasRangedWeapon` -> melee
    extra = int(stats.get_stat(int(StatType.EXTRA_RANGE)) or 0) if stats is not None else 0
    return max(ranged) + extra


def unit_is_ranged(state: "State", unit_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsRanged` = `HasTrait(unit, 0xb Ranged)
    || WeaponsComponent.HasRangedWeapon(unit)`. Le trait 0xb n'est porte par AUCUNE unite du
    gameconfig (constat #161) -> en pratique le predicat se reduit a « possede une arme a Range »,
    mais les deux termes sont ecrits."""
    import gameconfig as GC
    from ...entities.traits.unit_trait import UnitTrait
    traits = _unit_traits(state, unit_id)
    if UnitTrait.Ranged.name in traits:
        return True
    vid = _visual_id(state, unit_id)
    weapons = ((GC.unit(vid or "") or {}).get("weapons")) or []
    return any(w.get("Range") for w in weapons)


def ranged_bool_is_true(value: int, state: "State", unit_id) -> bool:
    """`IdunBattle.Core.Services.RangedBoolExtensions$$IsTrue(RangedBool, unit)` — mirror exact :
    `True -> true`, `False -> false`, `IfRangedCaster -> IsRanged(unit)`,
    `IfNotRangedCaster -> !IsRanged(unit)` (le natif leve `ArgumentOutOfRangeException` au-dela)."""
    v = int(value)
    if v == RANGED_BOOL_TRUE:
        return True
    if v == RANGED_BOOL_FALSE:
        return False
    if v == RANGED_BOOL_IF_RANGED_CASTER:
        return unit_is_ranged(state, unit_id)
    return not unit_is_ranged(state, unit_id)         # IfNotRangedCaster


def _tile_of(state: "State", entity_id):
    """La MAIN TILE `(col, row)` de l'entite, ou None (== `EntityExtensions$$GetMainTileId`, cf.
    `components.get_main_tile`). Les consommateurs qui doivent voir l'EMPREINTE COMPLETE (portee,
    adjacence : le natif y passe des LISTES de tuiles) utilisent `components.get_unit_feet` —
    cf. `get_range_broken_rule` / `are_entities_adjacent` (#R30)."""
    from ..components import PositionComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


def _has_forced_in_melee(state: "State", unit_id) -> bool:
    """`EntityExtensions.HasEffect(caster, state, 0x529 ForcedInMelee, activeOnly = false)` lu par
    `GetRange` juste avant le cap final. Poseur porte : le trigger de free-attack de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility` (pose puis retire dans le
    meme cast)."""
    if state.effects is None or unit_id is None:
        return False
    return bool(state.effects.has_effect(int(unit_id), effect_type=EFFECT_FORCED_IN_MELEE))


def should_apply_ranged_in_melee(state: "State", caster_id: int) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$ShouldApplyRangedInMelee(caster, casterTiles,
    ignoreTrait)` -> `IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee`.

    `GetRange` l'appelle avec **`ignoreTrait = 1`** (litteral du call-site ; le thunk d'`AttackQuery`
    se contente de forwarder R9 et d'injecter `this.state` en 3e argument — VERIFIE a l'octet, la
    lecture Ghidra `uStack…28 = 0` designe le slot `MethodInfo*`, pas `ignoreTrait`). Le gate
    `HasTrait(0xb Ranged)` est donc COURT-CIRCUITE ici : contrairement au chemin PREDICTION
    (`CalculateRangedInMeleeReduction`, `ignoreTrait = 0`, inerte faute de porteur du trait #161),
    ce chemin-ci MORD pour tout caster. Mirror du decompile :

        if (casterTiles == null || casterTiles.Count == 0) return false;
        if (!HasTrait(caster, 0xb) && !ignoreTrait) return false;
        foreach (tile in casterTiles)
          foreach (adj in <tuiles adjacentes de tile>)
            u = GetUnit(adj, state);
            if (u != null && IsUnit(u) && !IsFriend(caster, u, state)
                && !TileExtensions.HasSteppableUnit(adj, state)
                && DamageCalculations.CanMeleeAttackOverElevationDifference(tile, adj)
                && IsTargetable(u) && IsAlive(u, state))  return true;
        return false;

    Offline : adjacence = `board.neighbours` (graphe evenq, la meme adjacence que tout le port),
    `HasSteppableUnit` = l'occupant porte `UnitTrait.Steppable` (0x1b),
    `CanMeleeAttackOverElevationDifference` = `|dElevation| < 2` (litteral `iVar1 < 2`).
    Sans `state.board` on ne sait pas decider -> False (aucun clamp invente)."""
    from ...entities.traits.unit_trait import UnitTrait
    from ..components import OwnerComponent, PositionComponent, UnitComponent
    board = state.board
    if board is None:
        return False
    src = _tile_of(state, caster_id)
    if src is None:
        return False
    src_tid = board.id_at(src[0], src[1])
    if src_tid is None:
        return False
    caster = state.get_entity(int(caster_id))
    c_owner = caster.get_component(OwnerComponent) if caster is not None else None
    if c_owner is None:
        return False
    src_elev = board.elevation(src_tid)
    neigh = set(board.neighbours(src_tid))
    for uid, ent in state.entities.items():
        if int(uid) == int(caster_id):
            continue
        uc = ent.get_component(UnitComponent)
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if uc is None or oc is None or pc is None:
            continue                                   # `IsUnit(u)`
        if oc.team == c_owner.team:
            continue                                   # `!IsFriend(caster, u)`
        if not uc.alive:
            continue                                   # `IsAlive(u, state)`
        tid = board.id_at(pc.col, pc.row)
        if tid is None or tid not in neigh:
            continue
        if UnitTrait.Steppable.name in (_unit_traits(state, uid) or ()):
            continue                                   # `!HasSteppableUnit(adj, state)`
        if abs(src_elev - board.elevation(tid)) >= 2:
            continue                                   # `CanMeleeAttackOverElevationDifference`
        if not is_targetable(state, uid):
            continue
        return True
    return False


def _ability_config_range(ability) -> Optional[int]:
    """`AbilityConfiguration.GetNumberConstant(0x16)` = `int.Parse(GetStringConstant(range))`.
    `AbilityConstantType` 0x16 = `range` -> cle `constants.range` de gameconfig-abilities."""
    import gameconfig as GC
    aid = getattr(ability, "ABILITY_ID", None)
    if not aid:
        return None
    raw = ((GC.ability(aid) or {}).get("constants") or {}).get(ABILITY_CONSTANT_RANGE)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def set_config_values_in_targeting_options(options: "TargetingOptions",
                                           ability) -> "TargetingOptions":
    """`IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` — appele par
    `AActiveAbility$$GetInvalidTargetReason` AVANT la query, sur la copie locale des options :

        if (this.Configuration != null && options.Range.UseRangeFromConfig
            && !options.Range.OverrideRange.HasValue)
            options.Range.OverrideRange = Configuration.GetNumberConstant(0x16 range);

    Note l'ordre : l'`OverrideRange` deja pose par le ctor GAGNE sur la config (aucune ability du
    registre ne pose les deux, mais le mirror garde la garde)."""
    rng = options.range
    if rng is None or not rng.use_range_from_config or rng.override_range is not None:
        return options
    cfg = _ability_config_range(ability)
    if cfg is None:
        return options
    return replace(options, range=replace(rng, override_range=cfg))


def get_range(state: "State", caster_id: int, options: "TargetingOptions") -> Optional[Range]:
    """`IdunBattle.Core.Services.TargetingQuery$$GetRange(caster, casterTiles, options)` — mirror :

        if (casterTiles == null || casterTiles.Count == 0)   return default(Range);
        if (options.Range.UseWholeBoard)                     return <Range sans OnlyAdjacent>;
        onlyAdjacent = RangedBoolExtensions.IsTrue(options.Range.OnlyAdjacent, caster);
        if      (!HasAnyWeapon(caster))    v = GetStat(caster, Range);
        else if (!HasRangedWeapon(caster)) v = 1;
        else                               v = GetStat(caster, ExtraRange) + longestRangedWeapon.Range;
        v = options.Range.OverrideRange.GetValueOrDefault(v);
        if (options.Range.OverrideRangeFunc != null) v = OverrideRangeFunc(caster);
        if (HasEffect(caster, 0x529 ForcedInMelee)) { v = Math.Min(1, v); onlyAdjacent = true; }
        if (RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)
            && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
            { v = Math.Min(1, v); onlyAdjacent = true; }
        return new Range(Math.Min(v, <cap>), onlyAdjacent);

    (Le `<cap>` final est un `Nullable<int>` local que le decompile n'ecrit JAMAIS -> `int.MaxValue`,
    donc `Math.Min` neutre. Idem pour la garde `!<cap>.HasValue` du court-circuit `UseWholeBoard`,
    toujours vraie.)

    Rend **None quand le port ne sait pas decider** — `TargetingRange` non RE-lu, caster sans tuile,
    portee d'arme non observable (cf. `unit_weapon_range`), ou `UseWholeBoard` (le filtre statique ne
    teste alors RIEN). Dans tous ces cas l'appelant NE POSE AUCUN REFUS : c'est la seule degradation
    admissible ici, un `Range` devine refuserait des casts LEGAUX.

    L'ORDRE compte et il est respecte : la valeur d'abord (arme -> override -> config), les deux
    CLAMPS de melee ensuite. Un clamp applique avant l'override serait ecrase par lui."""
    from ..components import StatsComponent
    rng = options.range
    if rng is None:
        return None                                   # `TargetingRange` non RE-lu -> pas de gate
    if _tile_of(state, caster_id) is None:
        return None                                   # `casterTiles` vide / caster hors plateau
    if rng.use_whole_board:
        return None                                   # le filtre saute le test de portee

    only_adjacent = ranged_bool_is_true(rng.only_adjacent, state, caster_id)

    if rng.override_range is not None:
        value = int(rng.override_range)
    else:
        e = state.get_entity(int(caster_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        value = unit_weapon_range(_visual_id(state, caster_id),
                                  sc.ctx if sc is not None else None)
        if value is None:
            return None                               # portee d'arme NON OBSERVABLE -> pas de gate

    if _has_forced_in_melee(state, caster_id):
        value = min(1, value)
        only_adjacent = True
    if ranged_bool_is_true(options.force_melee_target, state, caster_id):
        if should_apply_ranged_in_melee(state, caster_id):
            value = min(1, value)
            only_adjacent = True
    return Range(value=value, only_adjacent=only_adjacent)


def are_tiles_adjacent(board, src_tid, dst_tid) -> bool:
    """`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tileA, tileB)` — mirror EXACT du
    decompile, et il ne dit PAS « distance hex == 1 » :

        dElev    = |tileB.Position.Elevation - tileA.Position.Elevation|;
        adjacent = (tileA == tileB) ? true : tileA.Connectivity.IsNeighbour(tileB);
        return dElev < 2 && adjacent;

    DEUX quirks que la paraphrase « dist == 1 » manque, et les deux ont ete MESURES :
      * **la MEME tuile compte comme adjacente** (`tileA == tileB` court-circuite le test de
        voisinage). C'est ce qui fait que le natif, pour `IronkinSteeljack` casse SUR SA PROPRE
        TUILE, passe la portee et rend `TargetTileIsFree` (0x1000) — la ou un port en `dist == 1`
        rendait `TargetIsInRange` (BIT-DIFF mesure par `probe_targeting_masks_lot4.py --groups
        steeljack, u81 caster) ;
      * **l'adjacence est GATEE EN ELEVATION** (`|dElev| < 2`) : deux tuiles voisines separees par
        2 niveaux ne sont PAS adjacentes.

    La surcharge LISTE (`AreTilesAdjacent(IList, IList)`, celle qu'appelle
    `BattleQuery$$AreEntitiesAdjacent`) rend vrai des qu'UNE paire l'est — c'est
    `are_entities_adjacent` ci-dessous, qui boucle sur les EMPREINTES (#R30)."""
    if src_tid is None or dst_tid is None:
        return False
    if abs(board.elevation(src_tid) - board.elevation(dst_tid)) >= 2:
        return False
    if int(src_tid) == int(dst_tid):
        return True
    return int(dst_tid) in board.neighbours(int(src_tid))


def get_range_broken_rule(state: "State", caster_id: int, target_id: Optional[int],
                          options: "TargetingOptions") -> int:
    """LE VOLET PORTEE du filtre statique (surcharge 7 arguments de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`), sur le chemin
    `ignoreRangeChecks = false` — le seul emprunte par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. Rend le `TargetingRule` rompu
    ou 0 :

      * `range.OnlyAdjacent` -> `battleQuery.AreEntitiesAdjacent(casterTiles, target)` (lui-meme
        `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, cf. `are_tiles_adjacent` : MEME
        TUILE incluse + gate d'elevation) ; faux -> `TargetIsInRange` ;
      * sinon `d = movementQuery.GetDistance(casterTiles, target)` = MIN des
        `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` entre tuiles source et tuiles cible
        (`hexgeo.distance` offline, meme convention evenq que `Board`) ;
        `rules & TargetIsAtRange` -> refus si `d != range.Value` (portee EXACTE) ;
        sinon                     -> refus si `d > range.Value`.

    Cible sans position (tuile non modelisee, entite absente) -> 0 : on ne sait pas mesurer, donc on
    n'invente pas de refus.

    #R30 : les DEUX branches raisonnent desormais sur les EMPREINTES completes (`GetTiles`), pas sur
    la seule main tile — c'est litteralement ce que font les deux fonctions natives citees
    (`AreEntitiesAdjacent` prend deux LISTES de tuiles, `GetDistance` prend deux LISTES et rend le
    MINIMUM sur toutes les paires). Pour une unite a 1 pied l'empreinte vaut `[main tile]`, donc le
    resultat est bit-a-bit celui d'avant."""
    from ...services.movement_query import get_distance
    from ..components import get_unit_feet
    rr = get_range(state, caster_id, options)
    if rr is None:
        return 0
    src_feet = get_unit_feet(state, int(caster_id)) if caster_id is not None else []
    dst_feet = get_unit_feet(state, int(target_id)) if target_id is not None else []
    if not src_feet or not dst_feet:
        return 0
    if rr.only_adjacent:
        board = state.board
        if board is None:
            return 0                                  # adjacence NATIVE non calculable -> pas de gate
        ok = are_entities_adjacent(board, src_feet, dst_feet)
        return 0 if ok else int(TR.TargetIsInRange)
    d = get_distance(src_feet, dst_feet)               # MIN sur toutes les paires de pieds
    if options.has(TR.TargetIsAtRange):
        return 0 if d == rr.value else int(TR.TargetIsAtRange)
    return 0 if d <= rr.value else int(TR.TargetIsInRange)


def are_entities_adjacent(board, src_feet, dst_feet) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` -> la surcharge LISTE de
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` : vrai des qu'UNE paire
    (tuile source, tuile cible) est adjacente au sens `are_tiles_adjacent` (meme tuile incluse +
    gate d'elevation). Empreintes a 1 pied -> une seule paire = comportement inchange."""
    for s in (src_feet or ()):
        sid = board.id_at(s[0], s[1])
        for d in (dst_feet or ()):
            if are_tiles_adjacent(board, sid, board.id_at(d[0], d[1])):
                return True
    return False


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
    if options is None or not options.has(TR.CasterHasNotMoved):
        return 0
    from ..components import unit_has_moved
    return int(TR.CasterHasNotMoved) if unit_has_moved(state, int(caster_id)) else 0


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
    return (not options.has(TR.TargetIsTile)) and tuid is not None and tuid == int(caster_id)


def get_caster_not_added_reason(state: "State", caster_id: int, ability) -> int:
    """`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` — la branche que prend le
    natif quand une ability SELF-CASTEE (`options+0x00 != 0`) est castee SUR SON PROPRE CASTER.
    NON PORTEE -> 0 (permissif), pour la meme raison que la portee : sa decision depend d'un etage
    non porte.

    DECOMPILE (rules = `options+0x28`) :

        if ((char)rules < 0) return valide;                    # AddCaster pose -> court-circuit
        if (rules & 0x8) {                                     # AddCasterIfMatchesDynamicRule
            r = options[+0x30].Invoke(caster, casterTiles); if (r) return broken(r);
        } else if (rules & 0x400000) {                         # AddCasterIfAtLeastOneFreeTileInRange
            if (!HasFreeTilesInRange(1, caster, tiles, options, range)) return broken(0x400000);
        } else if (options+0x00 == 0 && !(rules & 0x800)) {    # AddCasterIfAtLeastOneTarget
            if (rules & 0x8000)                                # CasterIsPossibleTarget
                { r = <filtre statique>(target = caster); if (r invalide) return r; }
        } else {
            vt = TargetingQuery.GetValidTargets(caster, tiles, options, 1, 1);
            if (vt.AllTargets.Count == 0) return broken(0x800);   # AddCasterIfAtLeastOneTarget
        }
        return valide;

    POURQUOI 0 : sur le chemin qui nous concerne (`options+0x00 != 0`), le verdict est
    `GetValidTargets(...).AllTargets.Count == 0`, et
    `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` n'est PAS porte : il ENUMERE toutes
    les cibles legales du plateau (`GetPossibleTargetsForOptions` + la cascade complete, y compris
    les regles que ce module ne porte pas). Ce n'est plus la portee qui bloque — `GetRange` est
    porte depuis #241 — c'est l'enumeration. Rendre 0x800 « au juge » inventerait un refus ; rendre
    0 degrade du cote PERMISSIF, la convention de tout ce module.

    EXCEPTION deja lue au decompile : `CalibaniteGreatsword` (`AddCaster`) prend le tout premier
    court-circuit `if ((char)rules < 0) return valide;` — pour elle, 0 EST le verdict natif.

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
    # `AActiveAbility$$GetInvalidTargetReason` commence par ca, sur SA copie des options : la portee
    # de config est resolue AVANT que la query ne calcule `GetRange`.
    options = set_config_values_in_targeting_options(options, ability)
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

    # TargetIsCaster -- « la cible DOIT etre le caster » :
    #   `if ((rules & TargetIsCaster) && caster != GetUnit(target)) -> broken(TargetIsCaster)`
    if options.has(TR.TargetIsCaster) and tuid is not None and tuid != int(caster_id):
        return int(TR.TargetIsCaster)

    # TargetIsFriendly -- mirror du decompile :
    #   if (IsMachine(caster))  ok <- battleQuery.<slot 0x90>(caster, target)
    #   else if (IsUnit(caster) && IsUnit(target) && !HasEffect(TARGET, 0x67 FriendlyFire, active))
    #        ok <- UnitsAreFriendly(caster, target)
    #   sinon -> broken(0x400)
    # ATTENTION : c'est l'effet `FriendlyFire` de la **CIBLE** qui est lu ici (contraste avec
    # `UnitsCanAttackEachOther`, qui lit celui de l'ATTAQUANT) -- une cible sous FriendlyFire n'est
    # plus « amie » de personne. La branche MACHINE (slot 0x90 direct) tombe sur le meme predicat
    # d'equipe offline.
    if options.has(TR.TargetIsFriendly) and tuid is not None:
        ff = (state.effects is not None
              and state.effects.has_effect(tuid, effect_type=EFFECT_FRIENDLY_FIRE))
        if ff or not units_are_friendly(state, caster_id, tuid):
            return int(TR.TargetIsFriendly)

    # TargetIsEnemy -- `if (!UnitsCanAttackEachOther(caster, target)) -> broken(TargetIsEnemy)`.
    if options.has(TR.TargetIsEnemy) and tuid is not None:
        if not units_can_attack_each_other(state, caster_id, tuid):
            return int(TR.TargetIsEnemy)

    # TargetIsTargetable -- controle INVERSE : il s'applique SAUF si `AllowUntargetableTarget` est pose.
    if (not options.has(TR.AllowUntargetableTarget)) and tuid is not None:
        if not is_targetable(state, tuid):
            return int(TR.TargetIsTargetable)

    # PORTEE -- SANS BIT DE GATE (cf. l'extrait du filtre en tete de module). Position NATIVE dans la
    # cascade : apres `TargetIsTargetable`/`TargetIsNotSteppable`/les regles `TargetHasNTiles`, AVANT
    # la ligne de vue puis tout le bloc `TargetIsSummon`/`TargetIsHero`/... et la regle dynamique.
    # L'ordre n'est pas cosmetique : c'est lui qui fixe la RAISON rendue quand plusieurs regles sont
    # rompues (le natif s'arrete a la premiere). `get_range_broken_rule` rend 0 des que le port ne
    # sait pas mesurer.
    reason = get_range_broken_rule(state, caster_id, target_id, options)
    if reason:
        return reason

    # TargetMatchesDynamicRule -- LE POINT D'EXTENSION : la regle-delegue posee par
    # `AActiveAbility$$.ctor` a `options+0x38` (`TargetingOptions.DynamicTargetingTargetRule` liee au
    # slot vtable +0x480) = le `GetDynamicInvalidTargetReason` de la sous-classe. Place ici comme
    # dans le natif : APRES les regles statiques, avant le retour « valide ».
    if options.has(TR.TargetMatchesDynamicRule):
        reason = int(ability.get_dynamic_invalid_target_reason(state, caster_id, target_id) or 0)
        if reason:
            return reason

    # TargetIsCasterOrEnemy -- DERNIERE regle de la cascade native (juste avant le retour
    # « valide »), mirror du decompile :
    #     if ((rules >> 0x39) & 1) && caster != GetUnit(target)
    #        && !UnitsCanAttackEachOther(caster, target)  ->  broken(TargetIsCasterOrEnemy)
    # = « la cible doit etre le CASTER LUI-MEME ou un ennemi attaquable ». C'est un `TargetIsEnemy`
    # ASSOUPLI par la tolerance du self-cast -- a ne pas confondre avec `TargetIsEnemy`, qui refuse
    # le self. Porteur du lot : HarbingerOfDestruction (1008), dont la branche
    # `If(AreEqual(caster, target), ...)` de l'ExecuteBehaviour est exactement la contrepartie de cette
    # tolerance. `tuid is None` (cible non-unite) -> le port ne sait pas decider : permissif, meme
    # convention que les autres regles du domaine UNITE.
    if options.has(TR.TargetIsCasterOrEnemy) and tuid is not None:
        if tuid != int(caster_id) and not units_can_attack_each_other(state, caster_id, tuid):
            return int(TR.TargetIsCasterOrEnemy)

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
