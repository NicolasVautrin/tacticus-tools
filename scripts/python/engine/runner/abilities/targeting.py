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
   6   0x40                  TargetIsTile -> tuile-cible NON MARCHABLE (rend le  OUI
                             litteral 1 = `ValidRequest`), sauf sous le bit 43
                             AllowUnwalkableTargetTile
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
  13   0x2000                TargetIsSummon (`HasTrait(2)`)                      OUI (#250)
  50   0x4000000000000       TargetIsHero (`HasTrait(0x10)` requis)              NON
  33   0x200000000           TargetIsNotAnObject (`HasTrait(0xd)` interdit)      NON
   8   0x100                 TargetIsHealable                                    NON
  16   0x10000               TargetIsRepairable                                  NON
   5   0x20                  TargetHasFreeAdjacentTile (battleQuery slot 0x51)   OUI
  21   0x200000              CasterHasFreeAdjacentTile                           NON (aucun porteur)
  12   0x1000                TargetTileIsFree (`CanAddUnit`)                     OUI (cible TUILE)
  17   0x20000               TargetTileIsFreeOrEnemy                             NON (domaine TILE)
  19   0x80000               TargetTileHasEnemyUnit                              NON (domaine TILE)
  32   0x100000000           TargetIsNotAdjacent (battleQuery slot 0x61)         OUI
  42   0x40000000000         TargetIsNotAdjacentToEnemy (battleQuery slot 0x7f)  OUI
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
        +0x10  GetRange   overrideRangeFunc      (delegue)

    `override_range_func` = « le ctor natif POSE un delegue a `TargetingRange+0x10` ». On ne modelise
    QUE sa PRESENCE, jamais sa valeur : `TargetingQuery$$GetRange` l'invoque et ECRASE la portee
    calculee juste avant (`if (*(param_4 + 0x18) != 0) v = OverrideRangeFunc(caster);`), donc une
    ability qui le pose n'a AUCUNE portee derivable de ses autres champs. `get_range` rend alors
    `None` -> aucun gate de portee, la degradation permissive de tout ce module. C'est different de
    `range = None` (= `TargetingRange` pas encore RE-lu) : ici le `TargetingRange` EST lu, c'est la
    VALEUR que le delegue produit qui n'est pas resolue.

    Unique porteur du registre : 1040 `SpawnPoxwalkers`, dont le
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$.ctor` construit un
    `IdunBattle.Core.Services.GetRange` (target NUL -> methode STATIQUE) et le passe a la surcharge
    `IdunBattle.Core.Services.TargetingRange$$CustomRange(GetRange)` -- cf. `custom_range_func`."""
    only_adjacent: int = RANGED_BOOL_FALSE
    use_range_from_config: bool = False
    use_whole_board: bool = False
    override_range: Optional[int] = None
    override_range_func: bool = False


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
    """`IdunBattle.Core.Services.TargetingRange$$CustomRange(int range)` — mirror du decompile
    (surcharge INT, celle des 16 call-sites) :
    `{ onlyAdjacent = False, useRangeFromConfig = false, useWholeBoard = false,
       overrideRange = Nullable(range), overrideRangeFunc = null }`."""
    return TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=int(value))


def custom_range_func() -> TargetingRange:
    """`IdunBattle.Core.Services.TargetingRange$$CustomRange(GetRange overrideRangeFunc)` — l'AUTRE
    surcharge (3 call-sites). Mirror du decompile, champ par champ :

        *param_1  = 1        # onlyAdjacent = RangedBool.False, useRangeFromConfig/useWholeBoard = 0
        param_1[1] = 0       # Nullable<int> overrideRange VIDE
        param_1[2] = param_2 # overrideRangeFunc = le delegue

    Le delegue n'est pas resolu (cf. `TargetingRange.override_range_func`) -> `get_range` rend None,
    aucun gate de portee. On enregistre le FAIT que le ctor le pose, pas une valeur devinee."""
    return TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=None,
                          override_range_func=True)


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

    # --- LECTURES DECLARATIVES du masque -- mirror 1:1 des getters natifs de `TargetingOptions`.
    #     Ce ne sont PAS des regles de refus (cf. la note « BITS QUI NE SONT PAS DES REGLES DE
    #     REFUS » en tete de module) : ce sont les lectures que les CONSOMMATEURS de ciblage
    #     (preview, IA) font du masque pour savoir QUEL DOMAINE de cibles enumerer. Le natif les
    #     consomme dans `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions`,
    #     qui choisit entre `GetTilesInRange` / `GetUnitsInRange` / la liste des machines.

    @property
    def is_tile_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting` = `rules >> 6 & 1`."""
        return self.has(TR.TargetIsTile)

    @property
    def is_machine_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsMachineTargeting` = `rules >> 0x2c & 1`."""
        return self.has(TR.TargetIsMachine)

    @property
    def is_actor_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsActorTargeting` = `rules >> 0x2e & 1`."""
        return self.has(TR.TargetIsActor)

    @property
    def is_unit_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsUnitTargeting` — mirror du decompile :
        `!(rules & TargetIsTile) && !(rules & TargetIsMachine) && !(rules & TargetIsActor)`
        (les trois tests en cascade, dans cet ordre)."""
        return not (self.is_tile_targeting or self.is_machine_targeting or self.is_actor_targeting)

    @property
    def is_caster_or_enemy_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsCasterOrEnemyTargeting` = `rules >> 0x39 & 1`."""
        return self.has(TR.TargetIsCasterOrEnemy)

    @property
    def is_enemy_targeting(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_IsEnemyTargeting` — mirror du decompile :
        `(rules >> 0xe & 1) ? true : (rules >> 0x39 & 1)` = `TargetIsEnemy` OU `TargetIsCasterOrEnemy`.

        ⚠ SA NEGATION N'EST PAS UN REFUS. Un masque qui ne porte NI `TargetIsEnemy` NI
        `TargetIsFriendly` n'interdit RIEN par camp : `GetPossibleTargetsForOptions` enumere
        `GetUnitsInRange` (les DEUX camps) et ses deux predicats de purge ne retirent que les morts,
        les tuiles a occupant Steppable et les ennemis OBSCURCIS
        (`...u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__0` / `b__1`).
        Pour « cette ability REFUSE toute cible ennemie », cf. `refuses_all_enemy_targets`."""
        return self.has(TR.TargetIsEnemy) or self.has(TR.TargetIsCasterOrEnemy)

    @property
    def can_target_caster(self) -> bool:
        """`IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` = `rules >> 0xf & 1`
        (`CasterIsPossibleTarget`)."""
        return self.has(TR.CasterIsPossibleTarget)


def refuses_all_enemy_targets(options: "TargetingOptions") -> bool:
    """L'ability REFUSE-t-elle, PAR CONSTRUCTION, toute cible ENNEMIE ? (vrai/faux, jamais « on ne
    sait pas » : appeler avec un masque REELLEMENT lu.)

    Ce predicat n'a que DEUX termes, et ce sont les deux SEULES regles du filtre statique
    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, surcharge 7 arguments) qui
    refusent une cible sur son CAMP / son IDENTITE, donc les deux seules qui rompent pour TOUT
    ennemi sans exception :

      * `TargetIsFriendly` (0x400) -> `if (!UnitsAreFriendly(caster, target)) broken(TargetIsFriendly)` ;
      * `TargetIsCaster`  (bit 39) -> `if (caster != GetUnit(target)) broken(TargetIsCaster)`.

    NE PAS utiliser `not is_enemy_targeting` a la place : ce serait INVENTER un refus. `SilentDeath`
    (0x4000) et `CalibaniteGreatsword` (0x80 `AddCaster` seul) sont toutes deux non-`IsEnemyTargeting`
    au sens du getter pour la seconde, et pourtant la cascade ne rompt sur AUCUN ennemi pour elle :
    un masque sans regle de camp accepte les deux camps (cf. `is_enemy_targeting`).

    Les regles de DOMAINE (`TargetIsTile`, `TargetIsMachine`) ne comptent pas ici : elles changent ce
    que le natif ENUMERE (`GetPossibleTargetsForOptions` rend des TUILES), pas ce que la cascade
    refuse -- `GetInvalidTargetReason(caster, pos, uniteEnnemie, <ability tile>)` resout
    `GetMainTile(target)` et peut parfaitement rendre « valide »."""
    return options.has(TR.TargetIsFriendly) or options.has(TR.TargetIsCaster)


# --- MASQUES RE-LUS D'ABILITES DONT LA FACE COMBAT N'EST PAS PORTEE ------------------------------
# Le masque est une propriete du `<X>Ability$$.ctor`, PAS de la behaviour : il se lit et se porte
# independamment de `ABILITY_CLASSES` (le registre de la face COMBAT). Cette table est l'endroit ou
# vivent les masques des abilities ABSENTES de ce registre -- y ajouter la classe d'ability juste
# pour porter son masque la ferait passer `ported:True` cote `AbilityHandler` alors que sa behaviour
# est un no-op, ce qui eteindrait le diagnostic `unported` (regression silencieuse).
#
# CONTRAT : DISJOINTE d'`ABILITY_CLASSES` (une ability a UNE source de masque, jamais deux) --
# garde-fou `tests/engine/test_targeting_options_sources.py`. Chaque entree cite le ctor natif dont
# le litteral est transcrit ; aucune valeur devinee.
TARGETING_OPTIONS_UNPORTED: "dict[int, TargetingOptions]" = {
    # 1100 SorcerousFacade (thousTzaangor) -- `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$.ctor` :
    #   TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x48 = UseWholeBoard>,
    #                          forceMeleeTarget=1 (RangedBool.False), rules=0x402, 0, 0, 0)
    # 0x402 = TargetIsFriendly | TargetMatchesDynamicRule -> la cible est un ALLIE, et la regle
    # dynamique `SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` la restreint encore
    # (`HasTrait(target, 0x3ea)` + le caster doit pouvoir porter son attaque normale depuis les
    # tuiles de cast). La regle dynamique n'est PAS portee ici (elle vit sur la classe d'ability, qui
    # n'existe pas) -> l'ensemble offline reste un SUR-ENSEMBLE des allies, ce qui est la degradation
    # PERMISSIVE de tout ce module.
    1100: TargetingOptions(rules=TR.TargetIsFriendly | TR.TargetMatchesDynamicRule,
                           self_cast=False, range=RANGE_WHOLE_BOARD,
                           force_melee_target=RANGED_BOOL_FALSE),
}


def targeting_options_for(ability_id) -> Optional["TargetingOptions"]:
    """Les `TargetingOptions` RE-LUES de l'`ActiveAbilityType`, ou `None` si le masque n'a pas ete lu.

    DEUX sources, dans cet ordre, et elles sont disjointes par contrat :
      1. la classe d'ability du registre COMBAT (`ABILITY_CLASSES[aid].TARGETING_OPTIONS`) ;
      2. `TARGETING_OPTIONS_UNPORTED` (masque lu, behaviour non portee).

    `None` = donnee non RE-lue -> les appelants NE POSENT AUCUN GATE (meme convention permissive que
    `get_invalid_target_reason`). Import PARESSEUX du registre : `handler` importe les modules
    d'abilities, qui importent ce module."""
    if ability_id is None:
        return None
    aid = int(ability_id)
    from .handler import ABILITY_CLASSES
    klass = ABILITY_CLASSES.get(aid)
    if klass is not None:
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        if opts is not None:
            return opts
    return TARGETING_OPTIONS_UNPORTED.get(aid)


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

    # `if (options.Range.OverrideRangeFunc != null) v = OverrideRangeFunc(caster);` -- position
    # NATIVE exacte : le delegue ECRASE tout ce qui precede (arme, override, config) et precede les
    # deux clamps de melee. Le port ne resout pas le delegue -> il ne connait PAS `v`, donc il ne
    # peut decider ni la comparaison de distance ni (via `min(1, v)`) les clamps : aucun gate.
    if rng.override_range_func:
        return None

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
# VOLET ADJACENCE — les deux regles `...NotAdjacent...` (bits 32 et 42)
#
# Elles ne sont PAS le meme predicat, et le decompile les separe par deux slots d'interface
# DISTINCTS de `IBattleQuery` (slots LUS sur les lambdas du decorateur
# `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`, qui re-appellent l'inner par le
# MEME index — c'est la seule lecture qui donne l'index sans deviner) :
#
#   slot 0x5f / 0x60 / 0x61 = les trois surcharges de `BattleQuery$$AreEntitiesAdjacent`
#       (`...u003Cu003Ec__DisplayClass116_0/117_0/118_0$$u003CAreEntitiesAdjacentu003Eb__0`)
#   slot 0x7c / 0x7d / 0x7e / 0x7f = les quatre surcharges de `BattleQuery$$GetAdjacentEnemies`
#       (`...u003Cu003Ec__DisplayClass151_0..154_0$$u003CGetAdjacentEnemiesu003Eb__0`)
#
# Le filtre statique appelle le slot 0x60 pour la PORTEE `OnlyAdjacent` (`(casterTiles, target)`),
# le slot 0x61 pour le bit 32 (`(targetTiles, casterTiles)` : deux LISTES) et le slot 0x7f pour le
# bit 42 (`(targetTiles, caster, false)`).
# ------------------------------------------------------------------------------------------------

def entity_tiles(state: "State", entity_id) -> list:
    """`IdunBattle.Entities.EntityExtensions$$GetTiles(entity, state)` = la materialisation en LISTE
    de `IdunBattle.Entities.EntityExtensions$$IterateTiles`, dont le `MoveNext`
    (`...EntityExtensions.u003CIterateTilesu003Ed__17$$MoveNext`) a TROIS branches, dans cet ordre :

        if (entity.Has<UnitFootComponent>()) yield state.GetEntity(foot.TileId);      // UN pied
        else if (entity.Has<TileComponent>()) yield entity;                            // la TUILE
        else if (entity.Has<UnitComponent>())                                          // l'EMPREINTE
            foreach (f in unit._feet) { t = f.Tile; if (t.Id != 0) yield t; }

    C'EST CETTE FONCTION que le filtre statique applique a la CIBLE (`local_a0`) et au CASTER
    (`casterTiles`), donc la seule qui rende `[la tuile]` quand la cible EST une tuile (ability
    tile-target). `components.get_unit_feet` mirror `GetUnitFeetIds`, qui ne couvre QUE la 3e
    branche et rend `[]` sur une tuile : s'en servir ici DESARMERAIT les deux regles d'adjacence
    pour toute ability tile-target (le seul porteur du bit 42, `SporeMineLauncher` 1145, cible une
    TUILE).

    Port : il n'existe pas d'entite-PIED (l'empreinte vit dans `UnitComponent.feet`), donc la 1re
    branche n'a pas d'equivalent ; restent EMPREINTE puis TUILE du board. Les deux espaces d'ids
    sont DISJOINTS — `boardGraph` et `decisionView` projettent le MEME `MatchState` natif, ou une
    tuile et une unite sont deux entites distinctes — l'ordre entre les deux branches est donc sans
    effet. `[]` = le port ne sait pas resoudre -> aucun refus (convention permissive du module)."""
    if entity_id is None:
        return []
    from ..components import get_unit_feet
    feet = get_unit_feet(state, int(entity_id))
    if feet:
        return feet
    board = state.board
    if board is not None and int(entity_id) in board.by_id:
        return [board.coord(int(entity_id))]
    return []


def _current_player_team(state: "State", entity_id):
    """`IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer(entity, state)` puis
    `player.Player.Team` (`+0x20` -> `+0x24`), tels que `UnitExtensions$$IsEnemy` les lit. Le natif
    rabat toute resolution manquante sur `0` ; le port rend `None`, que l'appelant compare comme une
    valeur ordinaire — deux `None` restent EGAUX, donc le verdict est le meme."""
    from ..components import OwnerComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return None if oc is None else oc.team


def units_are_enemies(state: "State", a_id, b_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsEnemy(a, b, state)` — mirror du decompile :

        if (a == null || b == null) return false;
        teamA = (GetCurrentPlayer(a)?.Player is null) ? 0 : GetCurrentPlayer(a).Player.Team;
        teamB = (GetCurrentPlayer(b)?.Player is null) ? 0 : GetCurrentPlayer(b).Player.Team;
        return teamA != teamB;

    ⚠ CE N'EST PAS `not units_are_friendly`. `units_are_friendly` mirror le slot 0x90
    `TargetingQuery$$UnitsAreFriendly` et rend `False` des qu'un `OwnerComponent` manque — le nier
    INVENTERAIT un ennemi la ou le natif, lui, compare deux equipes rabattues a `0` et conclut
    « pas ennemis ». C'est bien `IsEnemy` que consomme `BattleQuery$$CountOrGetUnitsOnTiles`."""
    if a_id is None or b_id is None:
        return False
    return _current_player_team(state, a_id) != _current_player_team(state, b_id)


def tile_can_add_unit(state: "State", coord) -> bool:
    """`IdunBattle.Entities.TileExtensions$$CanAddUnit(tile, state, allowSteppable, ignoreReserved,
    ignoreContent)` pour le triplet `(1, 0, 0)` — le SEUL que le filtre statique utilise (bit 12
    `TargetTileIsFree`) et aussi celui du lambda de filtrage de `BattleQuery$$GetFreeAdjacentTiles`
    (`...BattleQuery$$u003CGetFreeAdjacentTilesu003Eb__96_0` : `CanAddUnit(tile, state, 1, 0, 0)`).
    Mirror du decompile, pour ces arguments :

        if (tile == null || !tile.Has<TileComponent>())      return false;
        if (tile.<+0x40>.Blocker != 0)                       return false;   # folde dans `walkable`
        if (tile.Position.NotWalkable != 0)                  return false;   # folde dans `walkable`
        if (!ignoreContent) {                                                # ici : toujours
            if (content.IsEmpty())                           ok = true;
            else ok = GetUnit(tile).HasTrait(0x1b Steppable);                # allowSteppable = 1
            if (!ok)                                         return false;
        }
        if (ignoreReserved) return true;                                     # ici : non
        return tile.Position.<+0x2c> == 0;                                   # RESERVEE ?

    Offline : `Board.walkable` EST `BattleQuery.IsWalkableTile` = `TileExtensions$$IsWalkable`, qui
    folde deja les deux premiers rejets (cf. `frida/hooks/features/ai-step/rpc-board.ts`) ;
    l'occupation vient de `state.unit_at` (empreinte-aware, morts exclus). Le dernier terme
    (`Position+0x2c`, tuile RESERVEE) n'est capte par aucun RPC -> non modelise, donc PERMISSIF :
    une tuile walkable-vide-mais-reservee est rendue placable ici alors que le natif la refuse.
    C'est la MEME limitation, deja assumee et documentee, que `engine/battle_query.can_add_unit`
    (le pendant DECISION de ce predicat) -- pas un nouveau residu."""
    from ...entities.traits.unit_trait import UnitTrait
    board = state.board
    if board is None or coord is None:
        return False
    tid = board.id_at(int(coord[0]), int(coord[1]))
    if tid is None or not board.walkable(tid):
        return False
    occ = state.unit_at((int(coord[0]), int(coord[1])))
    if occ is not None:
        return UnitTrait.Steppable.name in (_unit_traits(state, occ.id) or ())
    return True


def get_free_adjacent_tiles(state: "State", entity_id) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles(IEntity)` — le slot 0x51 de
    `IBattleQuery` (index LU sur
    `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass101_0$$u003CGetFreeAdjacentTilesu003Eb__0`,
    qui re-appelle l'inner par ce meme index). Mirror du decompile :

        tiles = BattleQuery$$GetAdjacentTiles(entity, requireEmptyOrSteppable: true,
                                              requireWalkable: true[, allowTemporary: true]);
        tiles.FilterInPlace(t => TileExtensions.CanAddUnit(t, state, true, false, false));
        return tiles;

    Les deux pre-filtres de `GetAdjacentTiles` sont SUBSUMES par `CanAddUnit` (vide-ou-steppable +
    walkable), et `allowTemporary` ne filtre rien ; les deux surcharges natives de
    `GetFreeAdjacentTiles` (slots 0x51 et 0x52, qui ne different QUE par ce flag) coincident donc
    offline -- le port ne modelise pas `TileExtensions$$IsTemporary`. Reste la porte d'ELEVATION de
    `TileQuery$$IterateAdjacentTiles` (`|dElev| < 2`), portee ici. Rend des `(col,row)`."""
    board = state.board
    if board is None:
        return []
    out: list = []
    for t in (entity_tiles(state, entity_id) or ()):
        tid = board.id_at(int(t[0]), int(t[1]))
        if tid is None:
            continue
        elev = board.elevation(tid)
        for nid in board.neighbours(tid):
            if abs(elev - board.elevation(nid)) >= 2:
                continue
            coord = board.coord(nid)
            if coord in out or not tile_can_add_unit(state, coord):
                continue
            out.append(coord)
    return out


def get_adjacent_enemies(state: "State", tiles, unit_id,
                         only_non_steppable: bool = False) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IList<Tile> tiles, IEntity unit,
    bool onlyNonSteppable)` — la surcharge du slot 0x7f de `IBattleQuery`. Chaine native, mirror :

        players = state.GetEntity(unit.OwnerComponent.CurrentPlayerEntityId)
        BattleQuery$$GetUnitsOnTiles( BattleQuery$$IterateAdjacentTiles(tiles, false, true, true),
                                      friendOf: null, enemyOf: players, onlyNonSteppable )
          -> `BattleQuery$$CountOrGetUnitsOnTiles` (collecte dans un `OrderedSet`) :
               foreach (tile in tiles) {
                   u = UnitExtensions.GetUnit(tile, state);        if (u == null) continue;
                   if (onlyNonSteppable && IsSteppable(u))         continue;
                   if (friendOf != null && !IsFriend(u, friendOf)) continue;
                   if (enemyOf  != null && !IsEnemy(u, enemyOf))   continue;
                   set.Add(u);
               }

    `IterateAdjacentTiles(tiles, a=false, b=true, c=true)` delegue par tuile a
    `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles(tile, a, b, c)`, dont le `MoveNext`
    (`...TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) lit ses trois flags ainsi (mapping
    des DEUX ctors d'iterateur, `+0x41/+0x43/+0x45` recopies en `+0x40/+0x42/+0x44`) :

        a = requireEmptyOrSteppable = FALSE -> les tuiles OCCUPEES sont incluses (c'est le but ici)
        b = requireWalkable         = TRUE  -> `TileExtensions$$IsWalkable(tile, true)` exige
        c = allowTemporary          = TRUE  -> les tuiles temporaires ne sont PAS filtrees

    puis la porte d'ELEVATION `|tile.Elevation - adj.Elevation| < 2` — la MEME que
    `MovementUtil$$AreTilesAdjacent` (cf. `are_tiles_adjacent`). L'iterateur parcourt la liste
    d'adjacence STOCKEE sur la tuile (`Connectivity`), donc la tuile SOURCE n'est jamais rendue :
    contrairement a `are_tiles_adjacent`, « la meme tuile » ne compte PAS ici.

    Le call-site du filtre statique passe `onlyNonSteppable = 0` : une unite `Steppable` adjacente
    COMPTE. Le parametre est mirrore quand meme (le natif l'expose, d'autres surcharges le posent).

    `state.unit_at` est le mirror etabli d'`UnitExtensions$$GetUnit(tile, state)` (occupant
    empreinte-aware ; il exclut les morts, comme la convention `decisionview_keeps_dead` du port —
    le natif, lui, RETIRE les tuiles d'un cadavre, donc les deux disent la meme chose).

    Sans `state.board` le port ne sait pas enumerer l'adjacence -> liste VIDE : aucun refus invente,
    convention permissive du module."""
    from ...entities.traits.unit_trait import UnitTrait
    board = state.board
    if board is None or not tiles or unit_id is None:
        return []
    out: list = []
    for t in (tiles or ()):
        tid = board.id_at(int(t[0]), int(t[1]))
        if tid is None:
            continue
        elev = board.elevation(tid)
        for nid in board.neighbours(tid):
            if abs(elev - board.elevation(nid)) >= 2:
                continue                                   # porte d'ELEVATION (|dElev| < 2)
            if not board.walkable(nid):
                continue                                   # `requireWalkable = true`
            occ = state.unit_at(board.coord(nid))          # `UnitExtensions$$GetUnit(tile, state)`
            if occ is None:
                continue
            if only_non_steppable and UnitTrait.Steppable.name in (_unit_traits(state, occ.id) or ()):
                continue
            if not units_are_enemies(state, unit_id, occ.id):
                continue                                   # `IsEnemy(u, enemyOf)`
            if occ not in out:
                out.append(occ)                            # `OrderedSet.Add` (dedup)
    return out


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

    NB `unit_has_moved` lit le `UnitFlagsComponent`. ⚠ FICHE CORRIGEE (2026-07-28, #210) : la regle
    n'est PLUS inerte sur un etat CHARGE -- `load_state` seede ce flag depuis
    `combatSnapshot.units[].unitFlags` (`snapshot._load_unit_flags`, introduit par `f02e30f`). MESURE :
    `probe_210_blackrage_targeting.py` cas `S4a` -- Lucien bouge LIVE, on capture, et le port rend
    `CasterHasNotMoved` en accord avec l'oracle `abilityReason`, sans pose manuelle. Elle mord aussi
    sur le chemin replay/self-play OFFLINE, ou c'est `MoveUnitOperation` -> `set_moved_flag`."""
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

    # BRANCHE `TargetIsTile` DU DEBUT DU FILTRE -- la toute PREMIERE regle de refus de la cascade,
    # avant meme `TargetIsCaster`. VERBATIM :
    #     if ((rules & 0x40 TargetIsTile) != 0) {
    #         mainTile = EntityExtensions.GetMainTile(target, state);
    #         if (!TileExtensions.IsWalkable(mainTile, true)
    #             && (rules & AllowUnwalkableTargetTile) == 0)  -> GenericBrokenTargetingRule(1)
    #     }
    # ⚠ LE CODE RENDU EST LE LITTERAL `1`, c'est-a-dire `TargetingRule.ValidRequest` : le natif
    # REUTILISE cette valeur pour « tuile-cible non marchable ». Elle n'a donc PAS toujours le sens
    # « ability indisponible » que lui donne `AttackQuery$$GetInvalidTargetReason` en amont de la
    # cascade -- une lecture d'oracle qui exclurait `0x1` du contrat sans regarder d'ou il vient
    # masquerait un vrai desaccord (MESURE `probe_243_not_adjacent.py --case generalise` : 5 tuiles
    # de C3_30 ou le natif rend `0x1` alors que la cible est parfaitement resolvable).
    if options.has(TR.TargetIsTile) and not options.has(TR.AllowUnwalkableTargetTile):
        board = state.board
        tt = entity_tiles(state, target_id)
        if board is not None and tt:
            tid = board.id_at(int(tt[0][0]), int(tt[0][1]))
            if tid is not None and not board.walkable(tid):
                return int(TR.ValidRequest)

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

    # TargetIsSummon -- « la cible doit etre un SUMMON ». VERBATIM du filtre statique (surcharge 7
    # arguments), juste APRES le bloc portee/ligne de vue :
    #     if ((rules & 0x2000) != 0 && !UnitExtensions.HasTrait(target, 2)) -> broken(0x2000)
    # Position NATIVE : premiere regle du bloc TRAITS (`TargetIsSummon` puis `TargetIsHero` bit 50
    # puis `TargetIsNotAnObject` bit 33 puis `TargetIsHealable`/`TargetIsRepairable`), donc APRES la
    # portee et AVANT `TargetHasFreeAdjacentTile`. L'ordre n'est pas cosmetique : c'est lui qui fixe
    # la RAISON rendue quand plusieurs regles sont rompues.
    # SEUL PORTEUR du bit au registre : `HadesAutocannons` (1147, MoW `blackForgefiend`), dont c'est
    # LA regle -- « a targeted enemy summon ». MESURE (`probe_250_blacklegion_targeting.py`, 1147) :
    # sur un ennemi NON-summon le natif rend bien `0x2000` alors que `TargetIsEnemy` (0x4000, teste
    # AVANT) a deja passe -- ce qui confirme a la fois le predicat et sa place dans la cascade.
    # `UnitTrait.Summon` = 2 ; le substrat de traits est le kit gameconfig, le meme que celui du
    # `UnitsWithTrait(..., 2)` de `HadesAutocannonsAbility$$GetAllTargets`.
    if options.has(TR.TargetIsSummon) and tuid is not None:
        from ...entities.traits.unit_trait import UnitTrait
        if UnitTrait.Summon.name not in (_unit_traits(state, tuid) or ()):
            return int(TR.TargetIsSummon)

    # TargetHasFreeAdjacentTile -- « la cible doit avoir au moins une tuile LIBRE au contact » :
    #     if ((rules & 0x20) && battleQuery.<slot 0x51>(target).Count == 0) -> broken(0x20)
    # Position NATIVE : APRES la portee/ligne de vue et le bloc `TargetIsSummon`/`TargetIsHero`/
    # `TargetIsNotAnObject`/`TargetIsHealable`/`TargetIsRepairable`, AVANT le bloc TUILE puis les deux
    # regles d'adjacence. PORTEE ICI, et pas ailleurs, parce que c'est cet ORDRE qui tranche : sur
    # HammerOfWrath (masque 0x102004032, qui porte les DEUX bits) le natif rend `0x20` et non
    # `0x100000000` pour une cible adjacente ET encerclee -- MESURE par `probe_243_not_adjacent.py`
    # (necroWarden u81, d=1, natif 0x20 ; sans cette regle le port rendait 0x100000000, soit un refus
    # pour la MAUVAISE raison). Le predicat est le meme que celui de la regle DYNAMIQUE de
    # HammerOfWrath, qui rend d'ailleurs le meme code -- ce que le natif fait DEUX fois aussi.
    if options.has(TR.TargetHasFreeAdjacentTile) and state.board is not None:
        if entity_tiles(state, target_id) and not get_free_adjacent_tiles(state, target_id):
            return int(TR.TargetHasFreeAdjacentTile)

    # TargetTileIsFree -- « la TUILE ciblee doit pouvoir accueillir une unite » :
    #     if ((rules & 0x1000) && !TileExtensions.CanAddUnit(mainTile(target), state, 1, 0, 0))
    #        -> broken(0x1000)
    # (`mainTile(target)` = `pcVar12`, que la branche `TargetIsTile` du debut du filtre pose a
    # `GetMainTile(target)`.) Porte UNIQUEMENT quand la cible est une TUILE du board : c'est le seul
    # cas qu'exercent les quatre porteurs du bit (1112, 1145, 1201, 1219), et une cible que le port
    # ne sait pas resoudre en tuile ne doit pas produire de refus invente. Comme le bit 5, il est ici
    # pour l'ORDRE : il precede `TargetIsNotAdjacentToEnemy` (bit 42), donc une tuile OCCUPEE et
    # voisine d'un ennemi doit rendre 0x1000, pas 0x40000000000.
    if options.has(TR.TargetTileIsFree) and state.board is not None and target_id is not None:
        if int(target_id) in state.board.by_id:
            if not tile_can_add_unit(state, state.board.coord(int(target_id))):
                return int(TR.TargetTileIsFree)

    # TargetIsNotAdjacent -- « la cible ne doit PAS etre AU CONTACT du caster ». VERBATIM du filtre
    # statique (surcharge 7 arguments) :
    #     if ((rules >> 0x20) & 1) {
    #         if (battleQuery.<slot 0x61>(targetTiles, casterTiles)) -> broken(0x100000000)
    #     }
    # `targetTiles` = `EntityExtensions.GetTiles(target, state)` (le `local_a0` calcule en TETE de
    # la fonction), `casterTiles` = le 2e argument de l'appelant. Le slot 0x61 est la surcharge
    # LISTE x LISTE d'`AreEntitiesAdjacent` -> `MovementUtil$$AreTilesAdjacent(IList, IList)` =
    # exactement `are_entities_adjacent` (meme tuile incluse + porte d'elevation), deja consomme par
    # le volet `only_adjacent` de la portee. Le sens est INVERSE de celui-la : ici l'adjacence
    # REFUSE. Position NATIVE : apres tout le bloc TUILE (`TargetTileIsFree`/`...FreeOrEnemy`/
    # `...HasEnemyUnit`), AVANT `TargetIsNotAdjacentToEnemy` puis la regle dynamique -- c'est ce qui
    # fixe la RAISON rendue quand la cible est A LA FOIS adjacente et refusee par la regle dynamique
    # de l'ability (mesure #226 sur HammerOfWrath : d=1 refuse, d>=2 accepte).
    if options.has(TR.TargetIsNotAdjacent):
        board = state.board
        src = entity_tiles(state, caster_id)
        dst = entity_tiles(state, target_id)
        if board is not None and src and dst and are_entities_adjacent(board, dst, src):
            return int(TR.TargetIsNotAdjacent)

    # TargetIsNotAdjacentToEnemy -- « la cible ne doit avoir AUCUN ENNEMI DU CASTER au contact ».
    # VERBATIM du filtre statique, juste apres le bloc precedent :
    #     if ((rules >> 0x2a) & 1) {
    #         units = battleQuery.<slot 0x7f>(targetTiles, caster, false);
    #         if (units.Count > 0) -> broken(0x40000000000)
    #     }
    # (le `GetTiles(target)` y transite par un corps IL2CPP DEDUPLIQUE `return param_1;` — une
    # IDENTITE, que ghidra etiquette `idun.tests.TestItemModel$$GetNextLevelItemModel` ; ce n'est PAS
    # une extraction de premiere tuile.) « Ennemi » = `IsEnemy(occupant, joueur du CASTER)`, pas
    # « ennemi de la cible » : sur une ability tile-target (SporeMineLauncher 1145) la tuile n'a pas
    # de camp, c'est le caster qui donne le referentiel. Detail du predicat : `get_adjacent_enemies`.
    if options.has(TR.TargetIsNotAdjacentToEnemy):
        if get_adjacent_enemies(state, entity_tiles(state, target_id), caster_id):
            return int(TR.TargetIsNotAdjacentToEnemy)

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
