"""GATE DE CIBLE d'une ability active (#115) — le maillon GENERIQUE + son point d'extension.

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` REFUSE un cast dont la cible est
illegale, AVANT le premier `AActiveAbility.Execute` de la behaviour ET avant
`IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` (d'ou l'observable
mesuree en #111 : `mutated=false`, `actionConsumed=false`, 2 evenements, groupe 12
`User_UseAbility` — ouvert par le handler de message EN AMONT du gate, puis referme aussitot).

CHAINE NATIVE (decompile = verite ; STRUCTURE re-lue sur `rnca9r7q6c` le 2026-08-01, #429) :

⚠ LES INDICES DE SLOT CITES PLUS BAS DATENT DE `gqfc5mff6c` ET TROIS ONT BOUGE DE +1 sur
`rnca9r7q6c` — `IBattleQuery` : `GetFreeAdjacentTiles` 0x51 -> **0x52** (bits 5 et 21),
`AreTilesAdjacent` 0x61 -> **0x62** (bit 32), `GetAdjacentEnemies` 0x7f -> **0x80** (bit 42).
`IAttackQuery` est INCHANGE (0x11 healable, 0x12 repairable) : ce sont deux interfaces
distinctes, une methode inseree dans l'une ne decale pas l'autre. AUCUN degat fonctionnel — le
port n'appelle pas par slot, il appelle des helpers Python nommes — mais les slots cites en
commentaire sont des references de RE, et trois d'entre eux ne resolvent plus. Les indices du
build COURANT sont ceux de `targeting_rule_inventory.py`.

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
EXPOSE DE LA CASCADE CIBLE — l'ORDRE NATIF des regles du filtre statique (surcharge 7 args).
Une regle NON PORTEE ne refuse JAMAIS (degradation PERMISSIVE — meme convention que « ability non
portee => behaviour no-op ») : le port ne peut pas inventer un refus qu'il ne sait pas decider.

⚠ PERIMETRE DE CE TABLEAU, ET IL EST BORNE (#429) : il decrit **l'ORDRE** de la cascade CIBLE,
parce que c'est l'ordre qui fixe la RAISON rendue quand plusieurs regles sont rompues. Ce n'est
PAS le recensement des regles de ciblage, et la colonne « port » ci-dessous n'a valeur
qu'indicative. Le RECENSEMENT — les 60 membres de l'enum, leur role natif, leur lecteur, et
surtout ce qui les ARME — vit dans `targeting_rule_inventory.py`, dont la couverture est prouvee
dans les DEUX directions par `tests/engine/runner/test_targeting_rule_inventory.py`. L'etat de
port, lui, ne s'ecrit nulle part : il se DERIVE de l'AST
(`scripts/python/probe_429_targeting_rule_inventory.py`).

⚠ NE PAS COMPTER LES PORTEURS D'UNE REGLE PAR SON BIT. Mesure du 2026-08-01 : TROIS regles de
cette cascade ne sont pas armees par leur propre bit, et le compte par le bit y donne un zero de
METHODE — `TargetIsAllowedForCaster` (TAUNT) est armee par `TargetIsEnemy|TargetIsCasterOrEnemy`
(**0** par le bit, **59** par l'armement) ; `TargetIsNotSteppable` par `get_IsUnitTargeting`
sans `AllowSteppableUnit` (**1** contre **83**) ; `TargetIsUnit` par l'ABSENCE des trois autres
tetes de domaine. C'est ce qui faisait ecrire « 0 porteur, rien a y porter » pour des regles
armees chez la majorite du registre.

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
  44   0x100000000000        TargetIsMachine  ]  TETE DE DOMAINE (bits 44/45/46) OUI (#250 machine/
  46   0x400000000000        TargetIsActor    ]  : elle RESOUT la cible avant     unite, #253 TUILE ;
  45   0x200000000000        TargetIsUnit     ]    toute autre regle              muette seulement sur
                             (bit 45 : refus par DEFAUT quand `GetUnit(target)`   une cible que le port
                              est nul et qu'aucun des bits 6/44/46 n'est pose --  ne resout PAS ; cf.
                              il n'est GATE par aucun flag)                       get_target_domain_broken_rule)
  39   0x8000000000          TargetIsCaster (`caster != GetUnit(target)` => refus) OUI
  10   0x400                 TargetIsFriendly                                    OUI
  14   0x4000                TargetIsEnemy (`UnitsCanAttackEachOther`)           OUI
  23   0x800000              TargetIsAllowedForCaster (`GetOnlyTargets`, Taunt)  OUI (#436) — ⚠ SON
                             ⚠ ARMEE PAR `TargetIsEnemy | TargetIsCasterOrEnemy`,               BIT N'EST JAMAIS
                             DESARMEE par `AllowIgnoreForcedAttackTarget` :                     TESTE : il
                             son propre bit 23 n'est JAMAIS teste par le natif.                 n'est que le
                             59 abilities du registre l'ont ARMEE (0 posent le bit).            code rendu
  18   0x40000               TargetIsDisplaceable                                NON (0 porteur)
  29   0x20000000            TargetIsTargetable (sauf si                        OUI
                             AllowUntargetableTarget est pose)
  51   0x8000000000000       TargetIsNotSteppable                                OUI (#442) — ⚠ ARMEE
                             ⚠ ARMEE PAR son bit **OU** `get_IsUnitTargeting`                   PAR DEFAUT :
                             (= ABSENCE des bits 6/44/46) SANS `AllowSteppableUnit`.            83 abilities
                             83 abilities du registre l'ont ARMEE ; 1 seule pose le bit.        du registre,
                             DESARMEMENT `AllowSteppableUnit` (bit 20) : il ne vaut QUE          l'ATTAQUE
                             pour la voie unit-targeting -- le bit 51 refuse malgre lui.         NORMALE incluse
  47/48/49                   TargetHas1Tiles / TargetHas3Tiles / TargetHas7Tiles NON (0 porteur)
   -   (non gate)            portee : `dist(casterTiles, target) > GetRange` ->  OUI (cf. ci-dessous)
                             TargetIsInRange (bit 27, 0x8000000) ; variante
                             EXACTE sous le bit 9 TargetIsAtRange (0x200)
  24   0x1000000             `GetTilesObscuringTerrain` (ligne de vue) ->        OUI (#444) — armee
                             TargetIsUnobscured. SEULE regle du filtre dont le    pour les 103
                             refus ne passe PAS par `GenericBrokenTargetingRule`  masques lisibles :
                             mais par `ObscuredTerrainBrokenTargetingRule` (dont  aucun bit ne
                             `get_Type` rend 0x1000000). Les bits 25/26 ne font   l'arme, seuls
                             que la DESARMER, et le trait 1005 `IndirectFire`     25/26 (et le
                             desarme le SEUL volet elevation.                     trait) desarment.
                             Trois DESARMEMENTS de plus, tous ANTERIEURS aux
                             bits : `TargetingConfiguration.EnableObscuringTerrain`
                             a faux, une cible AMIE (ou une tuile portant un
                             allie), et `dist(caster, cible) <= 1` (la ligne fait
                             2 tuiles, `2 < Count` est faux).
  13   0x2000                TargetIsSummon (`HasTrait(2)`)                      OUI (#250)
  50   0x4000000000000       TargetIsHero (`HasTrait(0x10)` requis)              NON (0 porteur)
  33   0x200000000           TargetIsNotAnObject (`HasTrait(0xd)` interdit)      NON (4 porteurs :
                                                                                 1029/1113/1202/1214)
   8   0x100                 TargetIsHealable (slot 0x11 d'`IAttackQuery`      OUI (#245 ; predicat =
                             = `AttackQuery$$EntityCanBeHealed(caster,           `attack_query.
                             cible, scope=0, removeEffects=1)`)                  entity_can_be_healed`,
                                                                                 pas la garde de
                                                                                 mutation
                                                                                 `healable_heal_type_0`)
  16   0x10000               TargetIsRepairable (le JUMEAU du bit 8 :           NON (0 porteur)
                             slot 0x12, meme forme d'appel)
   5   0x20                  TargetHasFreeAdjacentTile (battleQuery slot 0x51)   OUI
  21   0x200000              CasterHasFreeAdjacentTile (jumelle du bit 5, sur    NON (INATTEIGNABLE
                             le CASTER : slot 0x51 applique a `param_2`)         chez ses DEUX
                                                                                 porteurs 1028 et
                                                                                 1047, cf. #249)
  12   0x1000                TargetTileIsFree (`CanAddUnit`)                     OUI (cible TUILE)
  17   0x20000               TargetTileIsFreeOrEnemy                             NON (0 porteur)
  19   0x80000               TargetTileHasEnemyUnit (`IsEmptyOrSteppable` NIE    OUI (#249 ; cible
                             + `UnitsCanAttackEachOther` sur `GetUnit(target)`)   TUILE)
  32   0x100000000           TargetIsNotAdjacent (battleQuery slot 0x61)         OUI
  42   0x40000000000         TargetIsNotAdjacentToEnemy (battleQuery slot 0x7f)  OUI
   1   0x2                   TargetMatchesDynamicRule                            OUI (point d'extension)
  57   0x200000000000000     TargetIsCasterOrEnemy (self OU ennemi attaquable)   OUI

BITS QUI NE SONT PAS DES REGLES DE REFUS **DE CES DEUX CASCADES** :
`CasterIsPossibleTarget` (bit 15) n'apparait NI dans le filtre cible NI dans `GetInvalidCasterReason`.
Il est lu, en DECLARATIF, par `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` pour
les consommateurs de ciblage (preview / IA). ⚠ MAIS il a un TROISIEME lecteur, et celui-la EST un
gate : `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` (`rules >> 0xf & 1`)
RE-APPLIQUE la cascade CIBLE complete au caster pris comme cible. « Deux cascades » n'est donc pas
« exhaustivement » — la troisieme existe (#429), et elle est PARTIELLEMENT PORTEE depuis #447
(branches `AddCaster` et `AddCasterIfMatchesDynamicRule` ; cf. `get_caster_not_added_reason`).
⚠ MAIS PAS la branche du bit 15, et c'est une MESURE, pas un choix : elle exige `isSelfCasting == 0`
alors que l'aiguillage qui mene a cette cascade — l'overload 5 arguments — n'y branche QUE sous
`isSelfCasting != 0`. Les deux conditions sont contradictoires, donc **ses 13 masques armes ne
mordent JAMAIS sur le chemin du CAST** : ils ne comptent que par l'autre appelant,
`TargetingQuery$$GetValidTargets` (l'ENUMERATION preview/IA), non porte. Meme famille de lectures
declaratives : `get_IsTileTargeting` (`TargetIsTile`),
`get_IsUnitTargeting` (= ABSENCE des bits 6/44/46, et pas un bit a lui), `get_IsEnemyTargeting`
(`TargetIsEnemy` OU `TargetIsCasterOrEnemy`), `get_IsCasterOrEnemyTargeting`, `get_IsActorTargeting`
(`TargetIsActor`) — des LECTURES du masque, pas des regles supplementaires.

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

LES DEUX BITS CASTER DES MACHINES OF WAR (#253, les deux abilities d'`astraOrdnanceBattery`) — leur
non-port converge, mais PAS pour la meme raison, et la nuance vaut d'etre ecrite :
  * `AllowNullCasterTile` (bit 30, 0x40000000) n'est PAS une regle, c'est une **PERMISSION** : le
    natif refuse `broken(0x40000000)` quand `casterTiles` est vide et que NI ce bit NI
    `CasterHasNoTile` (bit 55) ne sont poses. Une MoW n'a aucune position -> sans ce bit, aucune de
    ses abilities ne serait castable. ⚠ FICHE CORRIGEE (#366-r1 tranche 1) : ce refus EST desormais
    porte (`get_invalid_caster_reason`, clause 4a) -- il ne pouvait etre laisse de cote que tant que
    la MoW etait le SEUL caster sans tuile ; depuis que `RemoveUnitFromTilesOperation` produit une
    UNITE ordinaire sans tuile, son absence etait une regression PERMISSIVE. La PERMISSION reste ce
    qui protege les MoW : les 17 abilities MoW du registre posent TOUTES le bit 30 (re-mesure).
  * `CasterHas2TurnsLeft` (bit 52, 0x10000000000000, porteur 1142) refuse quand le slot 0x1a
    d'`IBattleQuery` rend faux sur `(caster, 2)` — slot non resolu -> NON portee, degradation
    PERMISSIVE ordinaire.
Le bit 21 `CasterHasFreeAdjacentTile`, lui, EST une regle du filtre statique CIBLE (le natif y
appelle le slot 0x51 sur le **CASTER**, juste apres le meme slot sur la CIBLE pour le bit 5, et
avant `TargetTileIsFree`). Il a **DEUX** porteurs au registre, et pas un — 1028 `SupremeCommander`
et 1047 `ScarabSummon`, masque `0x208000` IDENTIQUE (l'inventaire a longtemps ecrit « son seul
porteur 1028 » : compte FAUX, corrige par #249). L'argument d'inertie a ete REFAIT pour 1047, et il
tient, parce que les deux ctors posent la MEME paire :

    ScarabSummonAbility$$.ctor    : TargetingOptions..ctor(&opts, 1, &<TargetingRange statics+0x60>,
                                                           1, 0x208000, 0,0,0)
    SupremeCommanderAbility$$.ctor: idem, meme preset, meme litteral

`isSelfCasting = 1` + `TargetingRange statics+0x60` = `RANGE_SELF` (`.cctor` : `+0x60 = 1`,
`+0x68 = Nullable(0)`, `+0x70 = null` -> `overrideRange = 0`). Deux chemins, tous deux fermes AVANT
le bit 21 : cible == caster (ou tuile du caster, que `GetUnit` resout en lui) -> l'aiguillage
self-cast branche sur `GetCasterNotAddedReason` et la cascade CIBLE n'est JAMAIS evaluee ; cible
ailleurs -> `d > 0` rompt `TargetIsInRange`, qui PRECEDE le bit 21 dans la cascade. La regle est donc
INERTE chez SES DEUX PORTEURS — la porter serait du code non confrontable. Elle reste atteignable
par un chemin INDIRECT que le port n'a pas : `GetCasterNotAddedReason` finit sur
`TargetingQuery$$GetValidTargets`, qui re-applique la cascade complete a toutes les cibles candidates
— mais `GetValidTargets` n'est pas porte (cf. `get_caster_not_added_reason`), donc rien a y gagner.

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
# TABLE VIDE, et c'est un ETAT, pas un oubli : depuis #287 la seule entree qu'elle portait
# (1100 `SorcerousFacade`) a MIGRE sur sa classe du registre COMBAT
# (`engine/runner/abilities/loki/facade.py::SorcerousFacadeAbility.TARGETING_OPTIONS`), parce que sa
# face COMBAT est desormais portee. Le CONTRAT de disjonction ne change pas d'un iota -- il n'a
# simplement plus rien a arbitrer tant qu'aucune nouvelle ability non portee n'entre ici. Le
# MECANISME de la 2e source, lui, reste garde par
# `tests/engine/runner/test_targeting_options_sources.py` (une entree bidon injectee par monkeypatch
# verifie que `targeting_options_for` consulte toujours cette table).
TARGETING_OPTIONS_UNPORTED: "dict[int, TargetingOptions]" = {
    # 1216 MartialExemplar (#27-r4) -- face DECISION portee (playbook), face COMBAT NON portee :
    # d'ou cette table plutot qu'`ABILITY_CLASSES`. Le masque est EFFECTIF, pas le litteral visible :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$.ctor` recopie le preset
    # `<TargetingOptions statics>+0x280` et appelle la surcharge PRESET+FLAGS
    # `TargetingOptions$$.ctor(this, template, additionalRules)` avec `additionalRules = 0x10` ; ce
    # corps fait `this.rules = additionalRules | template.rules`. Le preset porte `rules = 0x8004`
    # (ecrit par `IdunBattle.Core.Services.TargetingOptions$$.cctor` en `<preset>+0x28`), donc
    #     0x8004 | 0x10 = 0x8014
    #   = CasterIsPossibleTarget(0x8000) | CasterHasNotMoved(0x10) | CasterMatchesDynamicRule(0x4)
    # Recopier `0x10` seul aurait produit un masque FAUX -- pire que l'absence.
    # `isSelfCasting` = `<preset>+0x00` = 1 ; `forceMeleeTarget` = `<preset>+0x20` = 1 = RangedBool.False.
    # `range` = `None` DELIBERE : le bloc de 24 octets `<preset>+0x08..0x1f` est recopie d'un champ
    # statique de `TargetingRange` et n'a PAS ete resolu -> aucun gate de portee invente.
    # MESURE (probe_27_r4_martial_exemplar.py) : les deux bits portants sont observables --
    # `abilityTargets(1216)` rend UNE cible, le caster lui-meme (CasterIsPossibleTarget), et tombe a
    # ZERO cible des que le caster a bouge (CasterHasNotMoved).
    1216: TargetingOptions(rules=TR.CasterIsPossibleTarget | TR.CasterHasNotMoved
                                 | TR.CasterMatchesDynamicRule,
                           self_cast=True, range=None, force_melee_target=RANGED_BOOL_FALSE),
    # 1217 TheLionsWrath (#27-r4) -- meme configuration que 1216 : face DECISION portee (playbook
    # `loki_custom.TheLionsWrathPlaybook`), face COMBAT NON portee -> cette table, pas
    # `ABILITY_CLASSES`. Ici le masque est le LITTERAL, sans piege PRESET+FLAGS :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$.ctor` recopie les 0x40
    # octets du preset `<TargetingOptions statics>+0x40` et appelle
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, abilityAttackType)` -- dont le
    # corps recopie la struct TELLE QUELLE dans `this+0x70..0xac` (aucun `|` de flags additionnels ;
    # le 3e argument est l'`AbilityAttackType`, ici le litteral 0, ecrit a `this+0x68`).
    # Champs du preset, LUS dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #   +0x40 (`isSelfCasting`)     = 0
    #   +0x48..+0x5f (`range`)      = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #   +0x60 (`forceMeleeTarget`)  = 1 = RangedBool.False
    #   +0x68 (`rules`)             = 0x4000 = TargetIsEnemy, et RIEN d'autre
    # C'est ce masque qui met 1217 sur la route d'ATTAQUE (cibles ENNEMIES), la ou 1216 -- self-cast
    # par `CasterIsPossibleTarget` -- passait par la route non-attaque.
    1217: TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False, range=RANGE_ADJACENT,
                           force_melee_target=RANGED_BOOL_FALSE),
    # 1093 MortarionsPlagueWind (#27-r5) -- face DECISION portee (playbook), face COMBAT NON portee.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$.ctor` n'appelle
    # AUCUN `TargetingOptions$$.ctor` : il RECOPIE les 0x40 octets du champ statique
    # `<TargetingOptions statics>+0x180` puis fait `AActiveAbility$$.ctor(this, &opts, 0)`. Le masque
    # EFFECTIF est donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
    # `<preset>+0x28` (= `statics+0x1a8`) : **0x4002** (LU dans le cctor, pas deduit).
    #     0x4000  TargetIsEnemy            -> gate porte (`units_can_attack_each_other`)
    #     0x0002  TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, qu'aucun
    #             symbole `MortarionsPlagueWindAbility$$GetDynamicInvalidTargetReason` ne surcharge.
    # Le PRESET est LE MEME (`statics+0x180`) que celui de son jumeau `PlagueWindAbility$$.ctor`
    # (1035), dont `TARGETING_OPTIONS` porte deja ces valeurs -- les deux ctors sont identiques au
    # nom pres. `isSelfCasting` = `<preset>+0x180` = 0 ; `forceMeleeTarget` = `<preset>+0x1a0` = 1
    # = RANGED_BOOL_FALSE (l'enum natif est INVERSE : True=0, False=1) ; `range` = le bloc
    # `<preset>+0x188..0x19f`, recopie de `TargetingRange statics+0x18` = RANGE_FROM_CONFIG.
    1093: TargetingOptions(rules=TR.TargetIsEnemy | TR.TargetMatchesDynamicRule,
                           range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE),
    # 1215 InstrumentsOfVengeance (#27-r6) -- meme statut que 1216 : face DECISION portee (playbook),
    # face COMBAT NON portee (`...InstrumentsOfVengeanceAbility$$ExecuteBehaviour` est un arbre DSL
    # substantiel : `If(HasTarget)` sur deux paires de `GetEffectBehavior`, `AddBondEffect(0x5ef)`,
    # `If(!HasAdjacentEnemies) ActivateEffect(0x3f1)`, et chaque `GetEffectBehavior` empile
    # `TilesBehindInLine`/`EdgeTilesByDirection`/`SortByFormula`/`SetPersistentData`/`AddEffect(0x5ee)`).
    #
    # Le masque est une STATIC-COPY, pas un litteral de ctor et pas un PRESET+FLAGS :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$.ctor` recopie les
    # 0x40 octets de `<TargetingOptions statics>+0x280` dans une struct locale et la passe TELLE QUELLE
    # a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` -- il n'appelle AUCUNE surcharge de
    # `TargetingOptions$$.ctor`. Le masque effectif est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` en `<preset>+0x28` :
    #     0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)
    # C'est le MEME preset que 1216, SANS le `additionalRules = 0x10` : 1215 n'a donc PAS
    # `CasterHasNotMoved` -- elle reste castable apres deplacement, la ou 1216 ne l'est pas.
    # `isSelfCasting` = `<preset>+0x00` = 1 ; `forceMeleeTarget` = `<preset>+0x20` = 1 = RangedBool.False.
    # `range` = `None` DELIBERE (meme raison que 1216 : le bloc `<preset>+0x08..0x1f` vient d'un champ
    # statique de `TargetingRange` non resolu -> aucun gate de portee invente).
    # MESURE (probe_27_r6_instruments_of_vengeance.py) : `abilityTargets(1215)` rend UNE cible, le
    # caster lui-meme (CasterIsPossibleTarget), et elle SURVIT au deplacement du caster (absence de
    # CasterHasNotMoved) -- c'est la contre-epreuve qui separe ce masque de celui de 1216.
    1215: TargetingOptions(rules=TR.CasterIsPossibleTarget | TR.CasterMatchesDynamicRule,
                           self_cast=True, range=None, force_melee_target=RANGED_BOOL_FALSE),
}


# --- Les `TargetingOptions` de l'ATTAQUE NORMALE -- UNE PAR TYPE (#419-r1-tr14-r5-r2-r1-r2) ------
# Elles ne sont PAS celles d'une entree d'`ABILITY_CLASSES` (aucune classe d'attaque normale n'est au
# registre) : ce sont les options que chaque `<X>NormalAttackAbility$$.ctor` passe a
# `IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor`, et le natif les recupere PAR TYPE
# -- `IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` fait
#     opts = battleQuery.<slot 0x3e>(GetNormalAttackType(unit))
# avant `TargetingQuery.GetValidTargets(unit, tiles, options)`. Il n'y a donc PAS « un masque de
# l'attaque normale » : il y en a un PAR `ActiveAbilityType` d'attaque normale, et ils DIFFERENT.
#
# ⚠ LE PORT N'EN AVAIT QU'UN, celui de `69 Loki_NormalAttack`, applique a toutes les unites. Sur les
# 18 types d'attaque normale du registre natif, SIX ne portent pas ces valeurs -- deux d'entre eux
# sur le champ `range`, qui GATE (le bit, lui, est aujourd'hui inerte cote port, cf. plus bas).
#
# LES DEUX PRESETS STATIQUES, lus dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` (bloc de
# statiques de la classe, 16 presets de 0x40 octets ; le masque est a `<preset>+0x28`) :
#
#   `<TargetingOptions statics>+0x00`            `<TargetingOptions statics>+0x80`
#     +0x00 isSelfCasting    = 0                   +0x80 isSelfCasting    = 0
#     +0x08 range  <- `TargetingRange statics+0x00`  +0x88 range  <- `TargetingRange statics+0x00`
#     +0x20 forceMeleeTarget = 2 IfRangedCaster    +0xa0 forceMeleeTarget = 2 IfRangedCaster
#     +0x28 rules            = 0x4002              +0xa8 rules            = 0x4000
#
# Les deux presets sont IDENTIQUES champ pour champ SAUF UN BIT : `TargetMatchesDynamicRule` (0x2).
# Meme motif que le piege mesure en PR #126 (`0x4002` contre `0x4000` sur un meme lot), sur une AUTRE
# paire de presets.
#
# CE QUE LE BIT 0x2 CABLE, ET POURQUOI SON ABSENCE COMPTE :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$
# GetDynamicInvalidTargetReason` est un VRAI corps, pas un stub --
#     return FindAttackWeapon(caster, casterTiles, targetTiles) != null ? 0 : 2;
# (mirror exact : le meme `IdunBattle.Core.Services.IBattleQuery` slot que
# `ALoki_NormalAttackAbility$$FindAttackWeapon`, dont l'implementation est
# `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`). Un type a `0x4002`
# consulte donc cette regle ; un type a `0x4000` ne la consulte JAMAIS.
# Cette regle EST PORTEE depuis #419-r1-tr14-r5-r2-r1 (`normal_attack_dynamic_invalid_target_reason`),
# et c'est exactement ce qui rend la table ci-dessous LOAD-BEARING : poser le bit partout, comme le
# faisait le port avant #419-r1-tr14-r5-r2-r1-r2, armerait desormais un REFUS sur les 5 types que le
# natif desarme. Les deux tranches se tiennent -- la table sans la regle etait inerte, la regle sans
# la table serait FAUSSE.
# ⚠ Le slot est `0xb0`, PAS la surcharge a `GetAbilityAttackRangeType` (slot `0xaf`) : preuve de
# l'appariement dans `services.battle_query.get_attack_weapon_for_default_normal_attack_from_tiles`.

_NORMAL_ATTACK_OPTIONS_PRESET_00 = TargetingOptions(
    rules=TR.TargetIsEnemy | TR.TargetMatchesDynamicRule,
    self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,
    force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)
"""Recopie de `<TargetingOptions statics>+0x00` (`rules = 0x4002`)."""

_NORMAL_ATTACK_OPTIONS_PRESET_80 = replace(_NORMAL_ATTACK_OPTIONS_PRESET_00, rules=TR.TargetIsEnemy)
"""Recopie de `<TargetingOptions statics>+0x80` (`rules = 0x4000`). Le `replace` EXPRIME la lecture :
les deux presets ne different que par `<preset>+0x28`, tout le reste est le meme octet a octet."""

NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE: "dict[int, TargetingOptions]" = {
    # --- recopie du preset `statics+0x80` -> `rules = 0x4000`, PAS de regle dynamique -------------
    #   17 `IdunBattleLogic.Entities.Abilities.Active.NormalAttackAbility$$.ctor` (lu : `lVar1+0x80`)
    # 1030 `...Active.Loki.Loki_NormalBossAttackAbility$$.ctor`   (lu : `lVar1+0x80`)
    # 1114 `...Active.Loki.BlisteringAssault_NormalAttackAbility$$.ctor` -- son corps ENTIER est
    #      `return Loki_NormalBossAttackAbility$$.ctor(this);`, donc le MEME preset par construction.
    17: _NORMAL_ATTACK_OPTIONS_PRESET_80,
    1030: _NORMAL_ATTACK_OPTIONS_PRESET_80,
    1114: _NORMAL_ATTACK_OPTIONS_PRESET_80,
    # --- recopie du preset `statics+0x00` -> `rules = 0x4002` -------------------------------------
    #   69 `...Active.Loki.Loki_NormalAttackAbility$$.ctor`        (lu : `*puVar1`, offset 0)
    # 1046 `...Active.Loki.TemplarInitiateNormalAttackAbility$$.ctor`   (lu)
    # 1086 `...Active.Loki.ProperKilly_NormalAttackAbility$$.ctor`
    # 1123 `...Active.Loki.OptimizedGait_NormalAttackAbility$$.ctor`    (lu)
    # 1138 `...Active.Loki.Wraithcannon_NormalAttackAbility$$.ctor`     (lu)
    # 1162 `...Active.Loki.AncientFury_NormalAttackAbility$$.ctor`
    # 1178 `...Active.Loki.ElectroShock_NormalAttackAbility$$.ctor`
    # 1120 / 1128 / 1182 / 1205 / 1220 -- leurs `.ctor` sont DEDUPLIQUES par IL2CPP sur
    #      `...Active.Loki.TalonOfHorus_NormalAttackAbility$$.ctor`, dont le corps entier est
    #      `return Loki_NormalAttackAbility$$.ctor(this);` (lu). Leur symbole propre n'existe PAS
    #      dans les tables -- l'absence ne prouve rien, la chaine de ctor si.
    69: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1046: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1086: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1120: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1123: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1128: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1138: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1162: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1178: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1182: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1205: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    1220: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    # --- 1076 MV71SniperDroneSquadAttack -- FACTORY NOMMEE, pas une recopie nue -------------------
    # `...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor` appelle
    # `IdunBattle.Core.Services.TargetingOptions$$CustomLokiNormalAttackOptions(&opts, extraRules)`,
    # dont le corps recopie le preset `statics+0x00` champ par champ PUIS fait
    # `opts.rules = preset.rules | extraRules`. Le `extraRules` n'est pas rendu par le decompile
    # (registre RDX perdu) -> LU AUX OCTETS au call-site : `ba 02 00 00 00` = `mov edx, 2`.
    #     0x4002 | 2 = 0x4002  -- l'argument etait deja dans le preset, le calcul le DIT.
    1076: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    # --- 1126 RogalDorn_NormalAttack -- LITTERAL, et son `forceMeleeTarget` DIFFERE ---------------
    # `...Active.Loki.RogalDorn_NormalAttackAbility$$.ctor` n'utilise AUCUN preset de
    # `TargetingOptions` : il recopie `<TargetingRange statics>+0x00` puis appelle la surcharge
    # « flags directs »
    #     TargetingOptions$$.ctor(&opts, 0, &range, 1, 0x4000, 0, 0)
    #                                    ^        ^  ^
    #                        isSelfCasting        |  forceMeleeTarget = 1 = RangedBool.False
    #                                    TargetingRange statics+0x00
    # `forceMeleeTarget = 1` (et non 2) : le CLAMP de melee de `get_range`
    # (`RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster) && ShouldApplyRangedInMelee`)
    # ne s'applique JAMAIS pour ce type -- la ou le preset `+0x00` l'applique a tout caster distant
    # engage au corps a corps.
    1126: TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                           range=RANGE_ADJACENT_IF_MELEE_CASTER,
                           force_melee_target=RANGED_BOOL_FALSE),
    # --- 1146 FloatingDeath_NormalAttack -- LITTERAL, et son `TargetingRange` DIFFERE -------------
    # `...Active.Loki.FloatingDeath_NormalAttackAbility$$.ctor`, meme forme que 1126 mais il recopie
    # `<TargetingRange statics>+0x30` (`lVar1+0x30/0x38/0x40`) :
    #     TargetingOptions$$.ctor(&opts, 0, &range, 2, 0x4000, 0, 0)
    # `TargetingRange statics+0x30` = RANGE_ADJACENT (`onlyAdjacent = RangedBool.True`,
    # `overrideRange = 1`), PAS RANGE_ADJACENT_IF_MELEE_CASTER. Deux consequences DISTINCTES, et
    # toutes deux mordent dans `get_range` :
    #   * `onlyAdjacent` est vrai INCONDITIONNELLEMENT -- un caster RANGED est ramene a l'adjacence,
    #     la ou `IfNotRangedCaster` le laissait sur le test de DISTANCE ;
    #   * `overrideRange = 1` COURT-CIRCUITE `unit_weapon_range` -- avec le preset generique, une
    #     portee d'arme non observable fait rendre `None` a `get_range`, donc AUCUN gate de portee.
    1146: TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False, range=RANGE_ADJACENT,
                           force_melee_target=RANGED_BOOL_IF_RANGED_CASTER),
}

NORMAL_ATTACK_TARGETING_OPTIONS = NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE[69]
"""Les options de `69 Loki_NormalAttack`, l'attaque normale GENERIQUE -- celle que la fabrique pose
quand aucune des trois voies de substitution ne mord (`UnitFactory$$AddNormalAttackAbility`, repli
`type = this@+0x20`). C'est le DEFAUT du port quand le type n'est pas resoluble, et c'est ce que ce
module appliquait a TOUTES les unites avant #419-r1-tr14-r5-r2-r1-r2."""


def normal_attack_type_for(state: "State", caster_id: int) -> Optional[int]:
    """`IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)` cote port -- l'`ActiveAbilityType`
    CONCRET de l'attaque normale de l'entite (jamais l'abstrait 17).

    Delegue au FOYER UNIQUE du dispatch, `engine.services.custom_normal_attack.custom_normal_attack`
    (mirror de la cascade de `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` :
    voie PASSIVE, puis voie ACTIVE, puis branche TRAIT `Boss`), sur les canaux de PRODUCTION du
    `UnitContext`. `None` rendu par le foyer = aucune substitution = le repli generique de la
    fabrique, `69 Loki_NormalAttack`.

    Rend `None` si le nom rendu n'a pas d'entree dans `ActiveAbilityType` -- l'appelant retombe alors
    sur les options generiques, jamais sur un masque devine."""
    from ...entities.active_ability_type import ActiveAbilityType
    from ...services.custom_normal_attack import custom_normal_attack
    from ..components import StatsComponent
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    vis = _visual_id(state, caster_id)
    name = custom_normal_attack(
        passive_abilities=getattr(ctx, "passive_abilities", None),
        active_abilities=getattr(ctx, "active_abilities", None),
        # #419-r1-tr14-r5-r2-r2-r1 : l'etat PRE-fabrique, substrat de la garde du repli generique.
        config_active_abilities=getattr(ctx, "config_active_abilities", None),
        visual_id=vis,
        traits=_unit_traits(state, int(caster_id)))
    if name is None:
        return int(ActiveAbilityType.Loki_NormalAttack)
    got = getattr(ActiveAbilityType, str(name), None)
    return int(got) if got is not None else None


def normal_attack_targeting_options(state: "State", caster_id: int) -> "TargetingOptions":
    """`battleQuery.<slot 0x3e>(GetNormalAttackType(unit))` -- les `TargetingOptions` de l'attaque
    normale DE CETTE UNITE, pas celles d'une constante de module.

    Type non resoluble, ou type absent de la table (attaque normale dont le ctor n'a pas ete LU) ->
    les options du GENERIQUE `69`. C'est le meme arbitrage que partout ici : on ne renseigne que ce
    qu'on a lu, et le defaut est celui qui etait deja applique."""
    aid = normal_attack_type_for(state, caster_id)
    if aid is None:
        return NORMAL_ATTACK_TARGETING_OPTIONS
    return NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.get(int(aid), NORMAL_ATTACK_TARGETING_OPTIONS)


def normal_attack_dynamic_invalid_target_reason(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
    -- la regle-delegue que `AActiveAbility$$.ctor` pose a `options+0x38` pour TOUTE attaque normale.
    Corps natif, LU (5 parametres : `caster, casterTile, target, targetTiles`) :

        w = <IBattleQuery slot 0xb0>(caster, casterTile, targetTiles)
        return (w != null) ? 0 : 2 /* TargetMatchesDynamicRule */

    Le slot `0xb0` est
    `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
    attackerTiles, targetTiles)` -- l'appariement slot<->surcharge, et le fait que ce ne soit PAS la
    surcharge a `GetAbilityAttackRangeType` (slot `0xaf`), sont etablis dans
    `services.battle_query.get_attack_weapon_for_default_normal_attack_from_tiles`.

    CE QUI MORD, ET C'EST LE SEUL REGIME : `SelectMaxRangeWeapon` rend `null` sur un ENSEMBLE VIDE,
    donc le refus tombe exactement quand le caster n'a AUCUNE arme du type que l'adjacence reclame.
    Ventile sur le catalogue (683 unites, re-derive) :

      * cible NON adjacente + caster sans arme a distance (271 unites `melee_only`) -> le natif
        refuse ici AUSSI, mais le volet PORTEE l'a deja refuse EN AMONT de la cascade
        (`onlyAdjacent = IfNotRangedCaster` vrai pour un caster non-ranged -> `TargetIsInRange`).
        Aucun verdict deplace : meme refus, autre raison.
      * cible ADJACENTE + caster sans arme de melee -> **0 unite du catalogue** : aucune n'a une arme
        a distance sans arme de melee. Regime VIDE, dit plutot que compte comme une victoire.
      * caster sans AUCUNE arme -> les DEUX branches rendent `null` : le natif refuse TOUTE cible.
        C'est le seul regime ou ce port DEPLACE un verdict, et il vaut pour 81 unites du catalogue --
        dont 79 portent le bit (le type generique `69`). Les 2 autres sont les Spore Mines
        (`tyranNpc6SporeMine`, `tyranSmnSporeMine`), dont le type `1146 FloatingDeath_NormalAttack`
        NE POSE PAS le bit : le natif DESARME lui-meme la regle sur elles.

    ⚠ Les 11 MACHINES OF WAR de ce lot n'ont AUCUNE attaque normale, et c'est STRUCTUREL --
    `IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle jamais
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` (unique xref de code :
    `UnitFactory$$Build`). Ce port ne peut donc pas leur fabriquer un refus d'attaque normale : elles
    n'en ont pas. Cf. `ai/context.py` (`normal_ids = set()` pour une Machine).

    SUBSTRAT ET SON TRI-ETAT. Le natif itere le `WeaponsComponent` de l'ECS (peuple depuis
    `BC.Units[].Weapons`) ; la face DECISION n'a que le kit gameconfig -- meme borne, et meme
    citation, que `find_melee_weapon` / `find_ranged_weapon`, dont ce port se contente de composer
    les deux branches. D'ou :

      * `GC.unit(visualId)` ABSENT (unite inconnue du catalogue, `visual_id` non resolu) = substrat
        NON MESURE -> `0`, aucun refus. C'est la convention permissive du module : on n'invente pas
        un refus faute de mesure. A NE PAS confondre avec `weapons == []`, qui est une mesure et
        REFUSE.
      * tuiles non resolues (`entity_tiles` vide, board absent) -> `0`, meme raison.

    RESIDU NOMME : les deux substrats peuvent DIVERGER (`BC.Units[].Weapons` patche a la main ne
    change pas le gameconfig). En bataille standard ils concordent, `buildNormalizedBC` derivant du
    catalogue -- mais un montage qui vide `Weapons` dans le BC seul ferait diverger natif et port."""
    from ...services import battle_query as _bq
    import gameconfig as GC
    vid = _visual_id(state, caster_id)
    if GC.unit(vid or "") is None:                 # substrat NON MESURE -> aucun refus invente
        return 0
    board = state.board
    caster_tiles = entity_tiles(state, caster_id)
    target_tiles = entity_tiles(state, target_id)
    if board is None or not caster_tiles or not target_tiles:
        return 0                                   # tuiles non resolues -> permissif
    adjacent = are_entities_adjacent(board, caster_tiles, target_tiles)
    weapon = _bq.get_attack_weapon_for_default_normal_attack_from_tiles(vid, adjacent)
    return 0 if weapon is not None else int(TR.TargetMatchesDynamicRule)


class _NormalAttackTargeting:
    """Porteur MINIMAL des `TargetingOptions` de l'attaque normale, pour reutiliser TELLE QUELLE la
    cascade `get_invalid_target_reason` (qui lit `TARGETING_OPTIONS` sur son argument `ability`).
    Ce n'est PAS une entree d'`ABILITY_CLASSES` -- il n'a ni behaviour ni `ABILITY_TYPE`, il ne
    transporte que le masque. `ABILITY_ID = None` -> `SetConfigValuesInTargetingOptions` est inerte
    (aucun des `TargetingRange` d'attaque normale ne pose `UseRangeFromConfig`).

    `options=None` garde l'attribut de CLASSE -- c'est ce qui laisse les sous-classes de probe
    (`probe_436` / `probe_442` / `probe_444`, qui surchargent `TARGETING_OPTIONS` pour desarmer une
    regle) fonctionner sans changement."""
    TARGETING_OPTIONS = NORMAL_ATTACK_TARGETING_OPTIONS
    ABILITY_ID = None

    def __init__(self, options: Optional["TargetingOptions"] = None):
        if options is not None:
            self.TARGETING_OPTIONS = options

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        """La regle-delegue de l'attaque normale (`options+0x38`, bit `TargetMatchesDynamicRule`) --
        PORTEE depuis #419-r1-tr14-r5-r2-r1. Detail et bornes :
        `normal_attack_dynamic_invalid_target_reason`.

        Elle n'est CONSULTEE que si le masque du TYPE porte le bit : la cascade
        (`get_invalid_target_reason`) teste `options.has(TR.TargetMatchesDynamicRule)` avant
        d'appeler cette methode. Les 5 types a `0x4000` ne l'atteignent donc jamais -- c'est la table
        par type (#419-r1-tr14-r5-r2-r1-r2) qui DESARME, pas cette methode."""
        return normal_attack_dynamic_invalid_target_reason(state, caster_id, target_id)

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        """Pendant CASTER (`options+0x30`) : le preset de l'attaque normale ne pose PAS
        `CasterMatchesDynamicRule`, donc cette regle n'est de toute facon jamais consultee."""
        return 0


def valid_normal_attack_targets(state: "State", caster_id: int) -> list:
    """`IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` (MIRROR du decompile) :

        unit  = SelectSingle(unitSel@+0x18)                 # le caster
        tiles = Select(unitTileSel@+0x20)                   # ses tuiles de cast
        opts  = battleQuery.<slot 0x3e>(GetNormalAttackType(unit))
        if (rangeSel@+0x28 != null) { opts.rules &= ~TargetMatchesDynamicRule ;
                                      opts.range  = CustomRange(<formule>) }
        if (ignoreRule@+0x30.HasValue)     opts.rules &= ~ignoreRule
        if (additionalRule@+0x40.HasValue) opts.rules |= additionalRule
        return targetingQuery.<slot 2>(unit, tiles, opts, false).Targets

    Cette fonction porte le cas des call-sites SANS override (`range = null`, les deux `Nullable`
    VIDES) -- le seul lu a ce jour (`SorcerousFacadeAbility$$GetTarget` / `$$ExecuteBehaviour`,
    `FearedInterrogator_TargetEffect$$CreateTargetSelector`). Les trois overrides sont donc
    volontairement ABSENTS de la signature : les ajouter sans call-site serait du code speculatif.

    `GetValidTargets` = enumeration du domaine puis filtre par la MEME cascade que le gate de cible
    (`get_invalid_target_reason`) -> on la reutilise TELLE QUELLE avec le masque de l'attaque
    normale, plutot que d'ecrire un 2e filtre. Les tuiles de cast sont celles du caster : le port
    n'a pas de variante « depuis une tuile hypothetique » (`get_invalid_target_reason` mesure la
    portee depuis la position REELLE) -- exact au call-site COMBAT, ou le cast part de la position
    courante du caster.

    ORDRE D'ENUMERATION = celui de `state.entities` (ordre d'insertion). RESIDU NOMME : le natif
    enumere `GetPossibleTargetsForOptions` -> `GetUnitsInRange`, dont l'ordre n'est pas porte ; il
    ne tranche QU'A DISTANCE EGALE sous le `SortByDistance` + `First(1)` du seul consommateur.

    #419-r1-tr14-r5-r2-r1-r2 : les options sont celles du TYPE d'attaque normale DE CE CASTER
    (`normal_attack_targeting_options`), mirror du `battleQuery.<slot 0x3e>(GetNormalAttackType(unit))`
    que le selecteur natif fait a cette place exacte -- et non plus une constante de module."""
    probe = _NormalAttackTargeting(normal_attack_targeting_options(state, int(caster_id)))
    out = []
    for uid in list(state.entities.keys()):
        if int(uid) == int(caster_id):
            continue
        if get_invalid_target_reason(state, int(caster_id), int(uid), probe) == 0:
            out.append(int(uid))
    return out


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


def _is_machine(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$GetMachine(entity, state) != null` — l'entite EST une
    MACHINE OF WAR. Offline le marqueur est le `MachineComponent` pose par
    `engine/runner/snapshot.py` `_load_machines` (`decisionView.mows`, cle = `casterId`)."""
    from ..components import MachineComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    return e is not None and e.get_component(MachineComponent) is not None


def _resolves_to_unit(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state) != null`. ⚠ Une MoW n'est PAS une
    unite pour le natif -- mais le port lui pose un `UnitComponent` (porteur d'identite, cf.
    `_load_machines`), d'ou l'exclusion EXPLICITE du `MachineComponent` ici."""
    from ..components import MachineComponent, UnitComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    if e is None or e.get_component(UnitComponent) is None:
        return False
    return e.get_component(MachineComponent) is None


def get_target_domain_broken_rule(state: "State", target_id, options: "TargetingOptions") -> int:
    """TETE DE DOMAINE de la cascade 7-args (`TargetingQuery$$GetInvalidTargetReason`), la TOUTE
    PREMIERE decision, avant meme la branche `TargetIsTile`. VERBATIM du decompile :

        if (!(rules & TargetIsTile)) {
            if (!(rules & TargetIsMachine)) {
                if (!(rules & TargetIsActor)) { t = GetUnit(target); if (t == null) broken(TargetIsUnit); }
                else                          { t = GetUnit(target); if (t == null) goto machine; }
            } else { machine: t = GetMachine(target); if (t == null) broken(TargetIsMachine); }
        } else { t = GetMainTile(target); ... }
        <t = la cible RESOLUE que consomment TOUTES les regles suivantes>

    Autrement dit `TargetIsActor` (bit 46) n'est pas une regle de refus de plus : il ELARGIT le
    domaine (unite OU machine), la ou son absence rend une cible MACHINE illegale sur `TargetIsUnit`
    (bit 45, qui n'est gate par AUCUN flag). MESURE (#250) : la MoW `tauBroadside` porte 1160 AVEC le
    bit 46 et 1161 SANS -- et `abilityTargets` liste la MoW ennemie pour 1160, pas pour 1161.

    PORTE LA OU LE PORT SAIT DECIDER : cible PROUVEE machine (`MachineComponent`), PROUVEE unite,
    ou TUILE du board -- ce dernier cas ELARGI par #253, parce que `GetUnit` resout une tuile en son
    OCCUPANT (cf. `unit_of_entity`). MESURE (#253, ForwardSpotter 1143, masque SANS bit de domaine) :
    caste sur une tuile VIDE le natif rompt `TargetIsUnit`, caste sur la tuile d'un ALLIE il rend
    `0` = VALIDE. Les deux verdicts sont desormais rendus. Ne reste MUETTE que sur une cible que le
    port ne resout NI en unite, NI en machine, NI en tuile (entite absente) : le natif rompt, le port
    ne rompt pas -- degradation PERMISSIVE, meme convention que tout ce module."""
    if options.has(TR.TargetIsTile) or target_id is None:
        return 0
    machine = _is_machine(state, target_id)
    unit = _resolves_to_unit(state, target_id)
    if options.has(TR.TargetIsMachine):
        return 0 if machine else (int(TR.TargetIsMachine) if unit else 0)
    if options.has(TR.TargetIsActor):
        return 0                       # unite OU machine : les deux passent ; le reste indecidable
    if machine:
        return int(TR.TargetIsUnit)    # `GetUnit(MoW)` est nul cote natif
    if unit:
        return 0
    # ELARGISSEMENT #253 -- la cible est une TUILE du board : le natif la resout en son OCCUPANT.
    board = state.board
    if board is not None and int(target_id) in board.by_id:
        return 0 if unit_of_entity(state, target_id) is not None else int(TR.TargetIsUnit)
    return 0                           # ni unite, ni machine, ni tuile -> le port ne sait pas


def unit_of_entity(state: "State", entity_id):
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state)` — L'UNITE QUE DESIGNE l'entite,
    et non « l'entite si c'est une unite » : sur une TUILE le natif rend son OCCUPANT. C'est le
    `local_c8` que le filtre statique calcule UNE FOIS en tete de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) et
    propage en `pcVar12` des qu'aucun bit de DOMAINE n'est pose.

    Rend l'ID d'unite, ou None (« aucune unite designee » — le natif rend null, et c'est ce null que
    teste le preambule `TargetIsUnit`). MESURE (#253, probe `probe_253_astramilitarum_targeting.py`,
    ForwardSpotter 1143 caste sur la TUILE d'un allie) : le natif rend `0` = VALIDE, parce qu'il
    resout la tuile en son occupant. Un port qui rendrait « pas une unite » y poserait un FAUX
    REFUS.

    `_unit_of` reste DISTINCTE et n'est PAS remplacee : elle repond a « la cible EST-ELLE une unite »
    (elle alimente `tuid`, donc les regles du domaine UNITE, qui restent permissives sur une tuile)."""
    from ..components import UnitComponent
    if entity_id is None:
        return None
    e = state.get_entity(int(entity_id))
    if e is not None and e.get_component(UnitComponent) is not None:
        return int(entity_id)
    board = state.board
    if board is not None and int(entity_id) in board.by_id:
        occ = state.unit_at(board.coord(int(entity_id)))
        return None if occ is None else int(occ.id)
    return None


def _resolved_target_id(state: "State", target_id, options: "TargetingOptions"):
    """`puVar12` — la cible RESOLUE par la tete de domaine du filtre statique
    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, surcharge 7 arguments), celle
    que consomment TOUTES les regles qui suivent. MIRROR de l'aiguillage lu en tete de la fonction :

        TargetIsTile     -> EntityExtensions.GetMainTile(target)      (une ENTITE TUILE)
        TargetIsMachine  -> UnitExtensions.GetMachine(target)
        TargetIsActor    -> GetUnit(target), et a defaut GetMachine(target)
        (aucun des trois) -> UnitExtensions.GetUnit(target)           (= `local_c8`)

    Rend l'ID d'entite, ou None quand le port ne resout pas (degradation PERMISSIVE de tout ce
    module : aucune regle ne refuse sur une cible non identifiee).

    `get_target_domain_broken_rule` porte le volet REFUS de cette meme tete ; ici on porte son volet
    RESOLUTION, qui lui n'a pas de code de retour."""
    if target_id is None:
        return None
    if options.has(TR.TargetIsTile):
        board = state.board
        tt = entity_tiles(state, target_id)
        if board is None or not tt:
            return None
        return board.id_at(int(tt[0][0]), int(tt[0][1]))
    if options.has(TR.TargetIsMachine):
        return int(target_id) if _is_machine(state, target_id) else None
    if options.has(TR.TargetIsActor):
        u = unit_of_entity(state, target_id)
        if u is not None:
            return int(u)
        return int(target_id) if _is_machine(state, target_id) else None
    return unit_of_entity(state, target_id)


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


def get_only_targets(state: "State", unit_id) -> list:
    """`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets(unit)` — les SEULES entites que `unit` a le
    droit d'attaquer (le TAUNT). MIRROR du decompile, branche par branche :

        if (!unit.TryGetComponent<ForcedAttackTargetsComponent>(out comp)) return new List<int>();
        owner = unit.GetComponent<OwnerComponent>();          // NRE si absent
        if (OwnerComponent.IsOverridden(owner)) return new List<int>();
        return comp.<+0x50>;                                   // la List<int> d'entity-ids

    Liste VIDE = AUCUNE restriction (c'est le cas de la quasi-totalite des unites) — le gate de la
    regle est `Count > 0`, pas la presence du composant.

    QUI L'ECRIT : `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` la pose a
    `[BondedEntityId]` et `$$RevertInternal` la vide ; `AddForcedAttackTargetBehaviour` /
    `RemoveForcedAttackTargetBehaviour` l'editent par element. Detail + le lien effet->ecriture que
    le port materialise : `engine/runner/components.py::ForcedAttackTargetsComponent`.

    NON PORTE — le gate `IdunBattle.Entities.Components.OwnerComponent$$IsOverridden`
    (`= *(int*)(owner+0x14) != 0`, le champ `OverriddenPlayerEntityId` du MIND CONTROL ; le port ne
    porte que le CURRENT owner, `OwnerComponent.player`, sans distinguer l'original de l'override,
    cf. `OwnerComponent$$get_CurrentPlayerEntityId` = `+0x14 != 0 ? +0x14 : +0x10`). Une unite a la
    fois MIND-CONTROLEE et TAUNTEE verrait donc le port maintenir une restriction que le natif leve
    -> degradation RESTRICTIVE, du MAUVAIS cote. Elle n'a aucun porteur offline (le port ne
    materialise aucun override d'owner : aucun ecrivain de `OwnerComponent.player` hors capture) ;
    a fermer le jour ou la capture publiera les deux champs."""
    from ..components import ForcedAttackTargetsComponent
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return []
    comp = e.get_component(ForcedAttackTargetsComponent)
    if comp is None:
        return []                          # `TryGetComponent` faux -> `new List<int>()`
    return comp.get()


def is_targetable(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(unit, 0x11)`.
    Le flag 0x11 n'est pose par AUCUN chemin du port (aucun `UnitFlagsComponent.add(0x11)`) -> le
    predicat est constamment vrai offline. Mirror ecrit quand meme : le jour ou le flag sera pose,
    la regle s'activera d'elle-meme (et le lecteur voit que ce n'est pas un oubli)."""
    from ..components import UnitFlagsComponent
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return not (fl is not None and fl.has(UNIT_FLAG_NOT_TARGETABLE))


def has_steppable_unit(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.TileExtensions$$HasSteppableUnit(tile, matchState)` — MIRROR du decompile,
    ligne par ligne :

        u = UnitExtensions.GetUnit(tile, matchState);
        if (u == null) return false;
        b = UnitExtensions.GetBaseUnitComponent(u);
        if (b == null) return false;
        return BaseUnitComponent.HasTrait(b, 0x1b);          // UnitTrait.Steppable

    ⚠ SON NOM DIT « tile » MAIS SON ARGUMENT EST `GetUnit`-e : la cascade lui passe `puVar12`, la
    cible RESOLUE, qui est une UNITE sur une ability unit-targeting et une TUILE sous
    `TargetIsTile`. `GetUnit` couvre les deux (sur une tuile il rend son OCCUPANT, sur une unite
    l'unite elle-meme) -- d'ou `unit_of_entity`, exactement le meme mirror, et surtout PAS `_unit_of`
    (qui repondrait « la cible EST-elle une unite » et raterait le cas TUILE).

    Le substrat de traits est le meme que tous les `HasTrait(...)` portes (`_unit_traits` ->
    `entity_trait_names`) : kit gameconfig + traits accordes en bataille + mesure live
    `combatSnapshot.units[].traits`. Aucun etat supplementaire n'est a ECRIRE pour cette regle --
    `Steppable` est un TRAIT, pas un effet : il arrive avec l'unite (BC/snapshot) ou avec le summon
    (`build_decoy_context` / `build_summon_context`, tous deux seedes du `traits` gameconfig)."""
    from ...entities.traits.unit_trait import UnitTrait
    u = unit_of_entity(state, entity_id)
    if u is None:
        return False
    return UnitTrait.Steppable.name in (_unit_traits(state, int(u)) or ())


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
    """Traits de l'unite (NOMS) — le substrat que lit `IdunBattle.Entities.UnitExtensions$$HasTrait`.

    #264 : ce lecteur RELISAIT le gameconfig par visualId alors que son propre docstring annoncait
    `UnitContext.traits`. Il etait donc AVEUGLE aux deux choses que le substrat d'ENTITE porte : le
    pseudo-trait de GRANDE-ALLIANCE (`Imperial`/`Chaos`/`Xenos`, jamais dans un `traits` gameconfig)
    et tout trait ACCORDE EN BATAILLE (`AddTrait`) — plus, depuis #264, la MESURE live
    (`combatSnapshot.units[].traits`), qui differe du kit DANS LES DEUX SENS (`necroOverlord` porte
    `Resilient` au gameconfig et PAS en bataille). Deux ensembles de traits contradictoires
    cohabitaient donc dans le meme port ; il n'y en a plus qu'UN, `entity_trait_names`.

    Entite sans `StatsComponent` (cadavre : `combatSnapshot` filtre les morts) -> borne STATIQUE
    `entity_trait_names(None, vid)` = kit gameconfig + alliance, meme repli que `_unit_dict`."""
    from ...entities.traits.unit_trait import entity_trait_names
    from ..components import StatsComponent
    e = state.get_entity(unit_id)
    if e is None:
        return ()
    sc = e.get_component(StatsComponent)
    return tuple(sorted(entity_trait_names(sc.ctx if sc is not None else None,
                                           _visual_id(state, unit_id))))


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
    resultat est bit-a-bit celui d'avant.

    #250 : c'est bien `entity_tiles` (= `IdunBattle.Entities.EntityExtensions$$GetTiles`) qu'il faut
    ici, PAS `components.get_unit_feet` (= `GetUnitFeetIds`, 3e branche seule). Le natif passe
    l'ENTITE-cible au slot 0x60 / a `GetDistance`, qui resolvent ses tuiles par `GetTiles` — c'est la
    variable `pcVar12` du decompile de la surcharge 7 arguments, « la cible RESOLUE » :
    `EntityExtensions$$GetMainTile(target)` sous `TargetIsTile`, `UnitExtensions$$GetUnit(target)`
    sinon. Pour une ability TILE-TARGET la cible EST une tuile et `GetTiles(tile)` rend `[tile]`.
    `get_unit_feet`, lui, rend `[]` sur une tuile -> le volet portee retombait sur `return 0` et se
    DESARMAIT entierement pour toute ability tile-target (exactement l'avertissement porte par la
    docstring d'`entity_tiles`, qui n'avait pas ete applique ici).

    DEUX MESURES INDEPENDANTES, arrivees au meme diagnostic par des porteurs disjoints :
      * #250-summon -- `MasterOfTheTutelaries` (1096) et `AberrantHypermorph` (1166), masque
        `TargetIsTile | TargetTileIsFree` + `RANGE_ADJACENT` : le natif rend `TargetIsInRange` sur
        toute tuile non adjacente au caster, le port rendait 0 (branche `only_adjacent`) ;
      * #254 -- `TheQuickening` (1151), `RANGE_FROM_CONFIG` = 2
        (`probe_250_loki_solo_targeting.py`) : le natif rend `TargetIsInRange` sur les tuiles a d=3
        et d=4, le port rendait 0 (branche DISTANCE, l'autre du couple).
    Les CINQ abilities tile-target du registre a gate de portee reel etaient concernees : 1017
    FragBomb, 1092 DarkTalonStrike, 1116 RadBombardment, 1151 TheQuickening, 1219 IronkinSteeljack.
    Pour une cible UNITE le resultat est INCHANGE (`entity_tiles` commence par `get_unit_feet` et le
    rend tel quel)."""
    from ...services.movement_query import get_distance
    rr = get_range(state, caster_id, options)
    if rr is None:
        return 0
    src_feet = entity_tiles(state, caster_id)
    dst_feet = entity_tiles(state, target_id)
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


def is_friend_or_has_friendly_unit_on_it(state: "State", entity_id, unit_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(entity, unit, state)` --
    mirror du decompile :

        if (entity == null || unit == null) return false;
        if (unit.EntityType != Unit(1))     return false;      // slot 1 de `IEntity`
        u = UnitExtensions.GetUnit(entity, state);              // une TUILE resout en son OCCUPANT
        if (u == null)                      return false;
        return GetCurrentPlayer(u)?.Player?.Team@+0x24 == GetCurrentPlayer(unit)?.Player?.Team;

    C'est le DESARMEMENT de la ligne de vue : le terrain n'obscurcit JAMAIS une cible amie (ni une
    tuile portant un allie). Meme predicat d'equipe que `units_are_friends` (`UnitExtensions$$IsFriend`),
    rabats a `0` compris -- d'ou sa reutilisation ici plutot qu'une 3e ecriture du meme test.

    Le gate `EntityType == Unit` sur le CASTER est porte par `_resolves_to_unit` (qui exclut
    justement la MoW, a laquelle le port pose un `UnitComponent` d'identite) : pour une MACHINE le
    natif sort sur `false`, donc la ligne de vue reste ARMEE. Sans consequence -- une MoW n'a aucune
    tuile, donc `casterTiles` est vide et la surcharge LISTE rend un set vide."""
    if entity_id is None or unit_id is None:
        return False
    if not _resolves_to_unit(state, unit_id):
        return False
    occupant = unit_of_entity(state, entity_id)
    if occupant is None:
        return False
    return units_are_friends(state, occupant, unit_id)


def get_tiles_obscuring_terrain(state: "State", caster_id: int, target_id,
                                options: "TargetingOptions") -> set:
    """`IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain(caster, casterTiles,
    target, options)` (surcharge LISTE) -- LA LIGNE DE VUE, et le SEUL endroit ou les bits 24/25/26
    sont lus. VERBATIM :

        if (config == null) throw;                                     // `this+0x30`
        if (config.EnableObscuringTerrain (+0x10)
            && !UnitExtensions.IsFriendOrHasFriendlyUnitOnIt(target, caster, state)) {
            type = 0;
            if (!UnitExtensions.HasTrait(caster, 0x3ed IndirectFire)
                && (rules & 0x2000000 AllowObscuredTargetByElevation) == 0)  type = Elevation(2);
            t2 = type | Wall(4);
            if ((rules & 0x4000000 AllowObscuredTargetByWalls) != 0)          t2 = type;
            if (t2 != 0) return movementQuery.<slot 0xf>(casterTiles, target, t2, 2);
        }
        return new DisposableHashSet();                                 // VIDE

    QUATRE observations qui font la difference entre porter la regle et porter une caricature :

      * **`TargetIsUnobscured` (bit 24) N'ARME RIEN** -- il n'est meme pas lu ici. Ce bloc tourne
        pour TOUTE ability qui atteint le volet portee (mesure #429 : les **103** masques lisibles).
        Les bits 25 et 26 ne font que le DESARMER, chacun sur un volet.
      * **`IndirectFire` (trait 1005) ne desarme QUE l'elevation**, pas les murs -- exactement ce
        que dit le tooltip i2 `Traits/IndirectFire_Description` (« can fire over obscuring hexes »).
      * **le masque des murs est pose PAR DEFAUT** : sans `AllowObscuredTargetByWalls`, `t2` vaut au
        moins `4`, donc le bloc n'est jamais court-circuite par `t2 == 0` -- ce dernier cas exige
        les DEUX desarmements (ou IndirectFire + le bit 26).
      * **le gate AMI precede tout** : une cible alliee (ou une tuile portant un allie) n'est jamais
        obscurcie. C'est ce qui met hors de portee de cette regle toutes les abilities de soin/buff.

    LA CIBLE EST `pcVar12`, la cible RESOLUE par la tete de domaine (`_resolved_target_id`) -- la
    meme variable que consomment `TargetIsAllowedForCaster` et le volet portee, PAS la cible
    d'origine. Sur une ability tile-target c'est la tuile ; sinon c'est `GetUnit(target)`, qui resout
    une tuile en son OCCUPANT (dont la main tile peut differer de la tuile visee si elle est
    multi-hex). Non resolue -> `GetMainTile(null)` est nul cote natif aussi, et le set est vide.

    Rend le SET des positions obscurcissantes (cardinal seul lu par la cascade)."""
    from ...entities.traits.unit_trait import UnitTrait
    if not getattr(state, "enable_obscuring_terrain", True):
        return set()
    resolved = _resolved_target_id(state, target_id, options)
    if resolved is None:
        return set()
    if is_friend_or_has_friendly_unit_on_it(state, resolved, caster_id):
        return set()
    obscuring = 0
    indirect = UnitTrait.IndirectFire.name in (_unit_traits(state, caster_id) or ())
    if not indirect and not options.has(TR.AllowObscuredTargetByElevation):
        obscuring = 2                                  # ObscuringType.Elevation
    t2 = obscuring | 4                                 # | ObscuringType.Wall
    if options.has(TR.AllowObscuredTargetByWalls):
        t2 = obscuring
    if t2 == 0:
        return set()
    from ...services.movement_query import get_tiles_obscuring_terrain_from_tiles
    return get_tiles_obscuring_terrain_from_tiles(
        state.board, entity_tiles(state, caster_id), _obscuring_target_tile(state, resolved),
        t2, 2)


def _obscuring_target_tile(state: "State", target_id):
    """La tuile que `MovementQuery$$GetTilesObscuringTerrain` retient de la CIBLE :
    `IdunBattle.Entities.EntityExtensions$$GetMainTile(to, state)` -- la MAIN TILE, pas l'empreinte.
    Une unite multi-hex n'est donc jugee que sur la tuile de son PREMIER pied.

    `entity_tiles(...)[0]` EST `GetMainTileId` (cf. sa docstring : premier pied pour une unite, la
    tuile elle-meme pour une tuile). `None` quand le port ne resout pas -> aucun refus."""
    tt = entity_tiles(state, target_id)
    return None if not tt else (int(tt[0][0]), int(tt[0][1]))


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


def units_are_friends(state: "State", a_id, b_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsFriend(a, b, state)` — le JUMEAU EXACT d'`IsEnemy`,
    lu au decompile : memes deux `GetCurrentPlayer(...).Player.Team@+0x24`, memes rabats a `0`, seul
    le comparateur change (`==` au lieu de `!=`). C'est ce predicat-la (et pas le slot 0x90
    `UnitsAreFriendly`) que consomme la branche `friendOf` de
    `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles`, donc `GetAdjacentFriends`.

    ⚠ Ce n'est PAS `not units_are_enemies` en general (deux entites dont l'une est `None` sont ni
    amies ni ennemies), mais ca l'est des que les deux ids sont resolus."""
    if a_id is None or b_id is None:
        return False
    return _current_player_team(state, a_id) == _current_player_team(state, b_id)


def tile_is_empty_or_steppable(state: "State", coord) -> bool:
    """`IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable(tile, state)` — mirror du decompile
    (les DEUX surcharges ont le meme corps, seule differe la facon d'atteindre le
    `TileContentComponent` : lookup de composant ou champ `tile+0x38`) :

        if (tile.TileContentComponent.IsEmpty())                       return true;
        u = UnitExtensions.GetUnit(tile, state);
        if (u != null && GetBaseUnitComponent(u) != null
            && BaseUnitComponent.HasTrait(u, 0x1b Steppable))          return true;
        return false;

    C'est le PREMIER terme de la regle `TargetTileHasEnemyUnit` (bit 19), dont il est la NEGATION
    utile : « la tuile ne porte AUCUNE unite, ou n'en porte qu'une STEPPABLE ».

    ⚠ FONCTION NATIVE DISTINCTE de `TileExtensions$$CanAddUnit` — ne PAS les fusionner. `CanAddUnit`
    n'appelle pas celle-ci : il RE-ECRIT le meme test (`IsEmpty()` puis `HasTrait(0x1b)`) et
    l'encadre de trois autres rejets (blocker, `NotWalkable`, tuile RESERVEE) que `IsEmptyOrSteppable`
    n'a PAS. Une tuile non marchable et vide est `IsEmptyOrSteppable` = VRAI et `CanAddUnit` = FAUX.
    La duplication du corps est celle du natif ; la structure offline suit la structure native.

    `state.unit_at` est le mirror etabli d'`UnitExtensions$$GetUnit(tile, state)` (occupant
    empreinte-aware, morts exclus) : il folde les deux etages `IsEmpty()` / `GetUnit`. Sans board ni
    coordonnee le port ne sait pas resoudre -> `True` (aucun refus invente : c'est la valeur qui
    DESARME la regle du bit 19, convention permissive de tout ce module)."""
    from ...entities.traits.unit_trait import UnitTrait
    if coord is None:
        return True
    occ = state.unit_at((int(coord[0]), int(coord[1])))
    if occ is None:
        return True
    return UnitTrait.Steppable.name in (_unit_traits(state, occ.id) or ())


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


def get_adjacent_friends(state: "State", tiles, unit_id) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentFriends(from, playerEntityId)` — le SYMETRIQUE
    de `get_adjacent_enemies`, lu au decompile (surcharge `(IEntity, BEntityId)`, slot 0x80) :

        players = state.GetEntity(playerEntityId)
        BattleQuery$$GetUnitsOnTiles( BattleQuery$$IterateAdjacentTiles(from, false, true, true),
                                      friendOf: players, enemyOf: null, onlyNonSteppable: false )

    C'est le MEME `IterateAdjacentTiles(_, a=false, b=true, c=true)` que le jumeau ennemi — donc les
    memes trois flags (tuiles occupees INCLUSES, `IsWalkable` exige, temporaires non filtrees) et la
    meme porte d'ELEVATION `|dElev| < 2`. Comme lui, l'iterateur parcourt l'adjacence STOCKEE sur la
    tuile : **la tuile source n'est jamais rendue**, donc l'unite elle-meme n'est JAMAIS dans le
    resultat (c'est pour ca que `FightingRetreatAbility$$ExecuteBehaviour` re-ajoute explicitement le
    caster par `op_Addition(adjFriends, caster@0x160)`).

    Contrairement au jumeau ennemi, cette surcharge ne prend PAS de `onlyNonSteppable` : une unite
    `Steppable` amie adjacente COMPTE. Consommateur porte : la regle dynamique de `FightingRetreat`
    (1081, #247). Sans `state.board` -> liste VIDE (aucun refus invente)."""
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
            if not units_are_friends(state, unit_id, occ.id):
                continue                                   # `IsFriend(u, friendOf)`
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

    DEUX de ses regles sont portees — `CasterHasNotMoved` (0x10) et, depuis #250,
    `CasterMatchesDynamicRule` (0x4, le POINT D'EXTENSION du volet caster). La 1re tombe
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

    ORDRE NATIF de la cascade CASTER, relu en entier (#250) -- il fixe la RAISON rendue quand
    plusieurs regles sont rompues :
        1. `CasterHasNotMoved` (0x10)                    PORTEE
        2. `CasterCanMove` (0x10000000)                  non portee
        3. `CasterHasCompletedOneTurn` (0x80000000)      non portee (`GetStat(caster, 0xc) <= 1`)
        4a. **la clause TUILE-NULLE**                    PORTEE depuis #366-r1 tranche 1 (cf. plus bas)
        4b. `CasterHasNoTile` (bit 55) + tuiles NON vides -> refus (bit 55) : non portee, **0 porteur
            au registre** (compte re-derive, cf. `probe_249_unported_rule_carriers.py`) -- rien a y
            porter, ce serait du code mort.
        5. **`CasterMatchesDynamicRule` (0x4)**          PORTEE depuis #250 (regle-delegue
           `options+0x30` = slot vtable `+0x470` = `<X>Ability$$GetDynamicInvalidCasterReason`)
        6. `CasterHas1/3/7Tiles` (bits 35/36/37), `CasterHas2TurnsLeft` (52), `CasterIsMachine` (53)

    NON PORTEES (memes motifs qu'en tete de module) : les points 2, 3, 4b et 6.

    LA CLAUSE TUILE-NULLE (4a) -- PORTEE PAR #366-r1 tranche 1, et c'est un REVIREMENT MESURE.
    VERBATIM du decompile (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`,
    surcharge `IList<IEntity> casterTiles`) :

        if ( (rules & AllowNullCasterTile) == 0 && (rules & CasterHasNoTile) == 0
             && CollectionExtensions.IsNullOrEmpty(casterTiles) )
            return GenericBrokenTargetingRule(AllowNullCasterTile);   // 0x40000000

    Elle etait NON PORTEE tant qu'AUCUN caster porte ne pouvait etre sans tuile : le seul cas etait
    la MACHINE OF WAR, et le port n'aurait fait qu'inventer un refus (« sans ce bit, aucune de ses
    abilities ne serait castable »). Ce raisonnement etait JUSTE mais il est PERIME depuis #366-r1 :
    `RemoveUnitFromTilesOperation` cree desormais, offline comme en live, une UNITE ORDINAIRE sans
    aucune tuile (`feet = []`). Sans cette clause, le port ACCEPTAIT un second cast de 1011/1023
    depuis une unite sous terre, que le natif REFUSE -- une regression PERMISSIVE, silencieuse, dans
    le sens exact que ce module cherche a eviter.

    L'ARGUMENT MoW EST RE-MESURE, il ne casse rien : sur les 17 abilities du registre portees par une
    MoW, les **17** posent `AllowNullCasterTile` (bit 30) -- elles sortent donc par le 1er terme,
    exactement comme le natif. Les 84 autres masques n'ont ni bit 30 ni bit 55, mais leurs casters
    sont sur le plateau : la clause y est INERTE. Compte re-derivable :
    `ABILITY_CLASSES` x `TARGETING_OPTIONS.rules`, ne pas le citer de memoire.
    Le port lit `get_unit_feet` = l'equivalent 1:1 d'`IdunBattle.Entities.EntityExtensions$$GetTiles`
    que le natif passe en `casterTiles` sur le chemin `ActiveAbilityOperation$$ExecuteInternal`.

    NB `unit_has_moved` lit le `UnitFlagsComponent`. ⚠ FICHE CORRIGEE (2026-07-28, #210) : la regle
    n'est PLUS inerte sur un etat CHARGE -- `load_state` seede ce flag depuis
    `combatSnapshot.units[].unitFlags` (`snapshot._load_unit_flags`, introduit par `f02e30f`). MESURE :
    `probe_210_blackrage_targeting.py` cas `S4a` -- Lucien bouge LIVE, on capture, et le port rend
    `CasterHasNotMoved` en accord avec l'oracle `abilityReason`, sans pose manuelle. Elle mord aussi
    sur le chemin replay/self-play OFFLINE, ou c'est `MoveUnitOperation` -> `set_moved_flag`."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return 0
    if options.has(TR.CasterHasNotMoved):
        from ..components import unit_has_moved
        if unit_has_moved(state, int(caster_id)):
            return int(TR.CasterHasNotMoved)
    # CLAUSE TUILE-NULLE (4a) -- placee ici, au rang NATIF : APRES `CasterHasNotMoved`, AVANT
    # `CasterMatchesDynamicRule`. L'ordre n'est pas cosmetique, c'est lui qui fixe la RAISON rendue :
    # une unite sous terre rompt CETTE regle et non la regle-delegue de son ability (cf. la section
    # dediee dans la docstring).
    if not (options.has(TR.AllowNullCasterTile) or options.has(TR.CasterHasNoTile)):
        from ..components import get_unit_feet
        if not get_unit_feet(state, int(caster_id)):
            return int(TR.AllowNullCasterTile)
    # `CasterMatchesDynamicRule` -- LE POINT D'EXTENSION du volet caster (#250), place ici comme dans
    # le natif (apres la paire tuile-nulle, avant les filtres de `FeetCount`). Le natif rend le code
    # que la regle-delegue lui donne, tel quel : `if (r != 0) return GenericBrokenTargetingRule(r)`.
    if options.has(TR.CasterMatchesDynamicRule):
        reason = int(ability.get_dynamic_invalid_caster_reason(state, caster_id) or 0)
        if reason:
            return reason
    return 0


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

    DECOMPILE (rules = `options+0x28`), relu VERBATIM sur `rnca9r7q6c` (#447) -- c'est une chaine
    `if / else if / else`, donc les branches sont MUTUELLEMENT EXCLUSIVES et leur ORDRE fixe qui
    tranche :

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

    ⚠ LA BRANCHE `CasterIsPossibleTarget` EST INATTEIGNABLE PAR CE CHEMIN, et c'est une mesure, pas
    une opinion : elle exige `options+0x00 == 0` (ability NON self-castee), alors que l'AIGUILLAGE
    qui mene ici -- `TargetingQuery$$GetInvalidTargetReason` surcharge 5 arguments -- ne branche sur
    `GetCasterNotAddedReason` QUE sous `if (*(char *)options != 0)`, c'est-a-dire self-cast POSE.
    Les deux conditions sont contradictoires. Ses **13** masques armes au registre (compte
    `probe_429_targeting_rule_inventory.py`) ne mordent donc QUE par l'autre appelant,
    `TargetingQuery$$GetValidTargets` (l'ENUMERATION : preview / IA), et le porter exigerait de
    porter cette enumeration -- residu nomme, cf. #429 §7.

    CE QUI EST PORTE (#447) : les deux premieres branches.

      * `AddCaster` (bit 7) -- le court-circuit. `(char)rules < 0` teste le SIGNE de l'octet de poids
        faible, donc exactement le bit 7. Deja le verdict rendu avant #447 (0), mais il l'etait par
        DEFAUT ; il est desormais rendu par la BRANCHE. Porteurs : 1118 `DoctrinaImperatives`,
        1189 `CalibaniteGreatsword`.
      * `AddCasterIfMatchesDynamicRule` (bit 3) -- la regle-delegue CASTER `options+0x30`
        (= slot vtable `+0x470` = `<X>Ability$$GetDynamicInvalidCasterReason`, cf.
        `ActiveAbility.get_dynamic_invalid_caster_reason`). Le natif rend le code de la DELEGUE
        TEL QUEL (`broken(r)`), jamais le bit 3 -- ce bit n'est qu'un AIGUILLAGE. Unique porteur du
        registre : 1115 `FearOfTheUnseen` (`tyranDeathleaper`), dont la delegue rend
        `CasterMatchesDynamicRule` (0x4) quand `UnitExtensions$$IsTeleporting(caster)` -- le
        DEEP STRIKE. C'est le « and is not in Deep Strike » du texte i2 de l'ability.

    CE QUI RESTE NON PORTE, et pourquoi (degradation PERMISSIVE, la convention de tout ce module) :
      * `AddCasterIfAtLeastOneFreeTileInRange` (bit 22) -> `TargetingQuery$$HasFreeTilesInRange`
        non porte. **0 porteur au registre** (compte re-derive) : rien a y gagner aujourd'hui.
      * la branche `else` -> `TargetingQuery$$GetValidTargets` non porte (il ENUMERE toutes les
        cibles legales du plateau). Rendre `0x800` « au juge » inventerait un refus.
        MESURE (probe `probe_targeting_masks_lot4.py`, Chronometron 1226 self-cast, ennemis hors du
        disque range 2) : le natif rend bien `0x800 AddCasterIfAtLeastOneTarget` la ou le port rend
        `0` -- ecart connu, du cote permissif, et c'est CETTE branche.

    ⚠ LE CANAL DE MESURE DE CETTE FONCTION N'EST PAS `abilityReason` (#447, mesure) : ce RPC passe
    par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui court-circuite sur
    `ActiveAbility$$get_CanCurrentlyBeUsed` AVANT toute cascade et rend alors le litteral `1`
    (`ValidRequest`). 1115 porte `initialCooldownTurns = 1` -> au tour 1, `abilityReason` publie
    `0x1` quel que soit le verdict de ciblage. Le canal qui EXPRIME ce refus est
    `abilityTargets.fromHere`, dont le chemin natif (`AttackQuery$$GetValidTargets`) ne gate que sur
    `IsAlreadyUsedThisTurn`."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return 0
    # `if ((char)rules < 0) return valide;` -- le SIGNE de l'octet bas = le bit 7 `AddCaster`.
    if options.has(TR.AddCaster):
        return 0
    # `if (rules & 0x8) { r = options[+0x30].Invoke(...); if (r) return broken(r); }`
    # Le code rendu est celui de la DELEGUE, pas le bit 3.
    if options.has(TR.AddCasterIfMatchesDynamicRule):
        reason = int(ability.get_dynamic_invalid_caster_reason(state, caster_id) or 0)
        if reason:
            return reason
        return 0                       # branche EXCLUSIVE : la suite de la chaine est un `else if`
    # `else if (rules & 0x400000)` / `else` : les deux etages non portes (cf. la docstring).
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

    # TETE DE DOMAINE (bits 44/45/46) -- elle precede TOUT le reste, y compris la branche
    # `TargetIsTile` ci-dessous : c'est elle qui RESOUT la cible que les regles suivantes consomment.
    # Detail + motif du non-port partiel : `get_target_domain_broken_rule`.
    reason = get_target_domain_broken_rule(state, target_id, options)
    if reason:
        return reason

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

    # TargetIsAllowedForCaster (bit 23) -- LE TAUNT / la CIBLE FORCEE (#436). VERBATIM du filtre
    # statique (surcharge 7 arguments), juste APRES `TargetIsEnemy` et AVANT `TargetIsDisplaceable` :
    #
    #     if ((rules >> 0xe & 1) != 0 || (rules >> 0x39 & 1) != 0) {        // TargetIsEnemy | TargetIsCasterOrEnemy
    #         if ((rules >> 0x28 & 1) == 0) {                               // !AllowIgnoreForcedAttackTarget
    #             list = UnitExtensions.GetOnlyTargets(caster);             // null -> NRE
    #             if (0 < list.Count) {
    #                 found = false;
    #                 foreach (id in list) { if (puVar12 == null) NRE;
    #                                        if (id == EntityId(puVar12)) found = true; }
    #                 if (!found) -> broken(0x800000);
    #             }
    #         }
    #     }
    #
    # ⚠ SON PROPRE BIT N'EST JAMAIS TESTE (mesure #429 : **0** ability du registre pose le bit 23,
    # **59** ARMENT la regle par `TargetIsEnemy|TargetIsCasterOrEnemy`). Le bit 23 n'est QUE le code
    # rendu. C'est pour ca qu'un recensement par le bit donnait « 0 porteur, rien a y porter » --
    # un zero de METHODE. L'ARMEMENT est le meme predicat que
    # `IdunBattle.Core.Services.TargetingOptions$$get_IsEnemyTargeting`, que le natif REECRIT inline
    # ici (il n'appelle pas le getter) ; le port reutilise le getter, c'est le meme prédicat bit pour
    # bit. Il vaut aussi pour l'ATTAQUE NORMALE (preset `0x4002` -> `TargetIsEnemy`), donc pour
    # `valid_normal_attack_targets`.
    #
    # LE DESARMEMENT est `AllowIgnoreForcedAttackTarget` (bit 40) : une ability qui le pose ignore le
    # taunt. TROIS GATES successifs, dans cet ordre -- armement, desarmement, puis `Count > 0` : une
    # liste VIDE (le cas de toute unite non tauntee) ne refuse RIEN.
    #
    # LA CIBLE COMPAREE est `puVar12`, la cible RESOLUE par la tete de domaine (`_resolved_target_id`),
    # PAS la cible d'origine : sur une ability TILE-targeting c'est la tuile, sur une ability
    # machine-targeting la machine, sinon `GetUnit(target)` (qui resout une TUILE en son OCCUPANT).
    if options.is_enemy_targeting and not options.has(TR.AllowIgnoreForcedAttackTarget):
        only = get_only_targets(state, caster_id)
        if only:
            rtid = _resolved_target_id(state, target_id, options)
            # `rtid is None` : le natif JETTE (`if (puVar12 == null) throw`) -- inatteignable chez lui,
            # la tete de domaine ayant deja rompu `TargetIsUnit`. Le port, lui, est PERMISSIF partout
            # ou il ne resout pas la cible (cf. `get_target_domain_broken_rule`) : on ne refuse pas
            # sur une cible qu'on ne sait pas identifier, meme convention que tout ce module.
            if rtid is not None and int(rtid) not in {int(x) for x in only}:
                return int(TR.TargetIsAllowedForCaster)

    # TargetIsTargetable -- controle INVERSE : il s'applique SAUF si `AllowUntargetableTarget` est pose.
    if (not options.has(TR.AllowUntargetableTarget)) and tuid is not None:
        if not is_targetable(state, tuid):
            return int(TR.TargetIsTargetable)

    # TargetIsNotSteppable (bit 51) -- LE DECOY / LA MINE (#442). VERBATIM du filtre statique
    # (surcharge 7 arguments), juste APRES `TargetIsTargetable` et AVANT les regles `TargetHasNTiles`
    # (donc AVANT le volet PORTEE) :
    #
    #     if ((rules >> 0x33 & 1) == 0) {                      // bit 51 NON pose
    #         if (TargetingOptions.get_IsUnitTargeting(options)) {
    #             if ((rules & 0x100000) == 0) goto TEST;      // !AllowSteppableUnit (bit 20)
    #         }
    #     } else {
    #     TEST:
    #         if (TileExtensions.HasSteppableUnit(puVar12, state)) -> broken(0x8000000000000);
    #     }
    #
    # ⚠ DEUX ARMEMENTS, ET LE SECOND EST LE VRAI GISEMENT (mesure #429) : son bit 51 n'a **1** seul
    # porteur au registre (1011 `TunnelingHorror`, TILE-targeting), tandis que **83** abilities
    # l'ARMENT par `get_IsUnitTargeting` -- qui n'est PAS un bit a lui mais l'ABSENCE des bits
    # 6/44/46 (`TargetIsTile|TargetIsMachine|TargetIsActor`), donc VRAI PAR DEFAUT. L'ATTAQUE NORMALE
    # est dans ce cas (preset `0x4002`, aucun bit de domaine) : on ne peut PAS attaquer normalement
    # une unite `Steppable`. Un recensement par le bit donnait ici un zero de METHODE.
    #
    # LE DESARMEMENT est `AllowSteppableUnit` (bit 20), et il ne desarme QUE la voie
    # unit-targeting : une ability qui pose le bit 51 refuse meme avec le bit 20 (la branche `else`
    # du natif court-circuite le test du bit 20). L'ORDRE des trois gates est donc : bit 51 d'abord,
    # puis `IsUnitTargeting`, puis `!AllowSteppableUnit`.
    #
    # LA CIBLE TESTEE est `puVar12`, la cible RESOLUE par la tete de domaine (`_resolved_target_id`),
    # pas la cible d'origine -- cf. `has_steppable_unit` pour le detail du `GetUnit` que le predicat
    # applique par-dessus (tuile -> occupant).
    #
    # ⚠ CETTE REGLE PRECEDE `TargetTileIsFree` (bit 12) DANS LA CASCADE, et ce n'est pas cosmetique :
    # le natif appelle `IsFreeTile(tile, state, allowSteppable: 1, ...)` -- une tuile portee par une
    # unite `Steppable` est donc « libre » pour le bit 12. Chez 1011, qui porte les DEUX bits, c'est
    # bien 51 qui refuse la tuile d'un decoy, jamais 12.
    if (options.has(TR.TargetIsNotSteppable)
            or (options.is_unit_targeting and not options.has(TR.AllowSteppableUnit))):
        rtid = _resolved_target_id(state, target_id, options)
        if rtid is not None and has_steppable_unit(state, rtid):
            return int(TR.TargetIsNotSteppable)

    # PORTEE -- SANS BIT DE GATE (cf. l'extrait du filtre en tete de module). Position NATIVE dans la
    # cascade : apres `TargetIsTargetable`/`TargetIsNotSteppable`/les regles `TargetHasNTiles`, AVANT
    # la ligne de vue puis tout le bloc `TargetIsSummon`/`TargetIsHero`/... et la regle dynamique.
    # L'ordre n'est pas cosmetique : c'est lui qui fixe la RAISON rendue quand plusieurs regles sont
    # rompues (le natif s'arrete a la premiere). `get_range_broken_rule` rend 0 des que le port ne
    # sait pas mesurer.
    reason = get_range_broken_rule(state, caster_id, target_id, options)
    if reason:
        return reason

    # LIGNE DE VUE (#444) -- la regle `TargetIsUnobscured` (bit 24). Elle vit DANS le meme bloc
    # `if (!ignoreRangeChecks)` que la portee, JUSTE APRES lui et AVANT `TargetIsSummon`. VERBATIM :
    #
    #     if (!ignoreRangeChecks) {
    #         <les trois regimes de PORTEE>
    #         tiles = this.GetTilesObscuringTerrain(caster, casterTiles, pcVar12, options);
    #         if (tiles == null) throw;
    #         if (0 < tiles.Count) return <box ObscuredTerrainBrokenTargetingRule(tiles)>;
    #     }
    #
    # TROIS choses que la place dans la cascade rend NON COSMETIQUES :
    #
    #   * elle est **INCONDITIONNELLE dans ce bloc** -- pas gatee par le bit 24 (qui n'est QUE le
    #     code rendu), et pas gatee non plus par la branche de portee : un `UseWholeBoard` saute le
    #     calcul de distance mais PAS la ligne de vue ;
    #   * elle **suit** la portee, donc une cible a la fois hors de portee et masquee rend
    #     `TargetIsInRange`, pas `TargetIsUnobscured` ;
    #   * elle **precede** tout le bloc TRAITS (`TargetIsSummon`/`TargetIsHero`/...), la regle
    #     dynamique et `TargetIsCasterOrEnemy`.
    #
    # SEULE REGLE DU FILTRE dont le refus ne passe pas par
    # `IdunBattle.Core.Services.TargetingRuleExtensions$$GenericBrokenTargetingRule` : le natif boxe
    # un `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule` (qui transporte les tuiles
    # fautives), dont le `get_Type` rend le litteral `0x1000000` -- soit exactement
    # `TargetingRule.TargetIsUnobscured`. Le code rendu est donc le meme des deux cotes.
    #
    # DEGRADATION : le port rend `0` partout ou il ne sait pas MESURER (pas de board, tuiles non
    # resolues) -- meme convention permissive que le reste du module. La regle ne peut rendre un
    # refus que sur des positions et des elevations REELLES.
    if state.board is not None:
        if get_tiles_obscuring_terrain(state, caster_id, target_id, options):
            return int(TR.TargetIsUnobscured)

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

    # TargetIsHealable -- « la cible doit etre SOIGNABLE par le caster ». VERBATIM du filtre statique
    # (surcharge 7 arguments), dans le bloc TRAITS, apres `TargetIsSummon`/`TargetIsHero`/
    # `TargetIsNotAnObject` et AVANT son jumeau `TargetIsRepairable` (bit 16) puis
    # `TargetHasFreeAdjacentTile` :
    #     if ((rules & 0x100) != 0) {
    #         aq = this.<+0x10>;                                  // le champ `attackQuery`
    #         if (!aq.<slot 0x11>(caster, pcVar12, 0, 1)) -> broken(0x100)
    #     }
    # `this+0x10` EST l'`attackQuery` : `IdunBattle.Core.Services.TargetingQuery$$Init(this,
    # attackQuery, battleQuery, movementQuery, state, config)` ecrit `*(this+0x10) = attackQuery`.
    # Les deux derniers arguments sont des LITTERAUX du site d'appel : `scope = 0` (ghidra :
    # `in_stack_... & 0xffffffff00000000`, les 32 bits bas mis a zero) et `removeEffects = 1`.
    #
    # LE SLOT 0x11 DE L'INTERFACE `IAttackQuery` = `AttackQuery$$EntityCanBeHealed`, et ce n'est pas
    # herite d'une lecture voisine : `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` --
    # le selecteur qui PORTE le nom `Healable` -- resout `FUN_1801e7040(<query>, <la MEME classe
    # d'interface que la cascade>, 0x11)` et l'invoque avec `(caster, entity, scope, 1)`. Deux
    # call-sites independants, meme interface, meme slot.
    #
    # ⚠ CE N'EST PAS `healable_heal_type_0` (`abilities/behaviours/stats.py`). Celle-la est la garde
    # COTE MUTATION des feuilles `Heal`, et elle ne couvre que DEUX des six termes natifs (HP<max +
    # `IsAffectedByHealType(target, 0)`). Le predicat de CETTE regle est le mirror COMPLET
    # `attack_query.entity_can_be_healed` (`AttackQuery$$EntityCanBeHealed`, surcharge 4 arguments),
    # qui y ajoute `!IsMachine`, le disjunct `HasNegativeUnitEffect` (arme par `removeEffects = 1`),
    # le flag caster `CanHealFullHealthUnits` (0x17), `!HasHealBlockers` et `!HasTrait(0xd Object)`.
    # Les trois non-ports de ce mirror (`HasNegativeUnitEffect`, `HasHealBlockers`, flag 0x17) sont
    # nommes dans son module et degradent tous du meme cote : ils ne peuvent qu'ELARGIR le refus.
    #
    # CIBLE = `pcVar12`, la cible RESOLUE par la tete de domaine -> `unit_of_entity` (`GetUnit`, qui
    # resout une TUILE en son occupant), le meme helper que le bit 19 emploie pour `local_c8`. Les
    # DEUX porteurs du registre (1002 `CombatRestoratives`, 1037 `RevitalizingMalignancy`) ne posent
    # aucun bit de domaine, donc `pcVar12 == local_c8 == GetUnit(target)`.
    #
    # GARDE D'HONNETETE (`health_is_readable`) : le refus natif tient a la conjonction de DISJUNCTS
    # dont deux ne sont pas portes ; si le port ne sait meme pas LIRE les PV de la cible, refuser
    # serait FABRIQUER un verdict. PV illisibles -> aucun gate, la degradation permissive de tout ce
    # module.
    if options.has(TR.TargetIsHealable):
        from .attack_query import entity_can_be_healed, health_is_readable
        htid = unit_of_entity(state, target_id)
        if htid is not None and health_is_readable(state, htid):
            if not entity_can_be_healed(state, caster_id, htid, scope=0, remove_effects=True):
                return int(TR.TargetIsHealable)

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
    # `GetMainTile(target)`.) Comme le bit 5, il est ici pour l'ORDRE : il precede
    # `TargetIsNotAdjacentToEnemy` (bit 42), donc une tuile OCCUPEE et voisine d'un ennemi doit rendre
    # 0x1000, pas 0x40000000000.
    # #250 : la cible est resolue par `entity_tiles(...)[0]` = `EntityExtensions$$GetMainTileId`
    # (feet[0] pour une UNITE, la tuile elle-meme pour une TUILE) -- PAS par « target_id est un id du
    # board ». Le natif applique la regle a `GetMainTile(target)` quelle que soit la nature de la
    # cible : interroge avec une UNITE, une ability tile-target rend `TargetTileIsFree` parce que la
    # tuile de cette unite est occupee PAR elle. MESURE #250 sur `MasterOfTheTutelaries` (1096) :
    # 3 lignes (le caster, un allie au contact, un ennemi au contact) ou le natif rend 0x1000 et ou
    # le port rendait 0.
    if options.has(TR.TargetTileIsFree) and state.board is not None:
        tt = entity_tiles(state, target_id)
        if tt and not tile_can_add_unit(state, tt[0]):
            return int(TR.TargetTileIsFree)

    # TargetTileHasEnemyUnit -- « la TUILE ciblee doit porter une unite ENNEMIE DU CASTER ». VERBATIM
    # du filtre statique (surcharge 7 arguments), IMBRIQUE dans la clause du bit 17 et juste avant
    # `TargetIsNotAdjacent` :
    #     if ((rules & 0x80000) != 0
    #         && (TileExtensions.IsEmptyOrSteppable(pcVar12, state)
    #             || !TargetingQuery.UnitsCanAttackEachOther(caster, pcVar9)))
    #        -> broken(0x80000)
    # DEUX TERMES, et ils ne resolvent PAS la tuile de la meme facon -- c'est le point que le module
    # a deja paye deux fois (#251/#254 sur `GetUnitFeetIds`, #250 sur `TargetTileIsFree`) :
    #   * `pcVar12` = la cible RESOLUE par la tete de domaine, donc `GetMainTile(target)` pour les
    #     QUATRE porteurs (tous `TargetIsTile`) = `entity_tiles(...)[0]`, exactement comme le bit 12 ;
    #   * `pcVar9` = `local_c8` = `UnitExtensions$$GetUnit(target, state)` calcule UNE FOIS en tete de
    #     la cascade sur la cible D'ORIGINE (ghidra le reassigne `pcVar9 = local_c8` juste avant le
    #     bloc `TargetIsTargetable`, donc ce n'est PAS `GetMachine`) -> `unit_of_entity`, qui resout
    #     une TUILE en son OCCUPANT (`GetUnit` @ le corps generique : UnitComponent -> l'entite ;
    #     TileComponent -> `TileContentComponent.IsFilled` puis `state.GetEntity(content.UnitId)`).
    # Aucune 3e variante n'est introduite : les deux helpers existaient deja.
    # SEMANTIQUE : la tuile doit etre OCCUPEE par une unite NON-Steppable (1er terme) qui soit
    # ATTAQUABLE par le caster (2e terme). Tuile vide -> le 1er terme rompt ; tuile d'un ALLIE -> le
    # 2e (`UnitsCanAttackEachOther` faux) ; tuile d'un ENNEMI -> aucun des deux, cast valide.
    # `unit_of_entity` nul (tuile vide) fait rendre `False` a `units_can_attack_each_other` via
    # `is_actor(None)` -- meme verdict que le natif, dont `UnitsCanAttackEachOther(caster, null)`
    # sort sur `!IsActor(null)`.
    # PERMISSIF quand le port ne resout pas la tuile (`entity_tiles` vide) : aucun refus invente.
    # IMBRICATION : le natif n'evalue le bit 19 QUE si la clause du bit 17 `TargetTileIsFreeOrEnemy`
    # n'a pas deja rompu (le bit 19 est dans son `then`). Le port teste le bit 19 directement, et ce
    # n'est PAS un raccourci : le bit 17 a **ZERO porteur** au registre
    # (`probe_249_unported_rule_carriers.py`), donc la garde ne peut pas se declencher. Si une
    # ability posant le bit 17 entre un jour, il faudra porter le bit 17 AVANT celui-ci, dans cet
    # ordre d'imbrication.
    if options.has(TR.TargetTileHasEnemyUnit):
        tt = entity_tiles(state, target_id)
        if tt:
            occupant = unit_of_entity(state, target_id)
            if (tile_is_empty_or_steppable(state, tt[0])
                    or not units_can_attack_each_other(state, caster_id, occupant)):
                return int(TR.TargetTileHasEnemyUnit)

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
