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
  * `CasterHas2TurnsLeft` (bit 52, 0x10000000000000) refuse quand le slot **0x1b** d'`IBattleQuery`
    (= 27 `HasMinimumRemainingTurns`, arite 2) rend faux sur `(caster, 2)`. **PORTEE depuis
    #287-r11-r1-r1** : le slot etait mal LU (`0x1a` = 26 `ShouldPlayerSkipTurn`, arite 1 -- d'ou
    l'incoherence avec les deux arguments du call-site), pas non resoluble. TROIS porteurs, tous
    MACHINE OF WAR : 1142 `MalleusRocketLauncher` (`astraOrdnanceBattery`), 1160 `HeavyRailRifle`
    (`tauBroadside`), 1188 `DevastatingRefrain` (`adeptExorcist`).
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
`IdunBattle.Entities.UnitExtensions$$IsAbilityBlocked`, cooldown, mode atomique.

`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` (cible = unite
MORTE et l'ability ne l'autorise pas) N'EST PLUS hors perimetre : PORTE par #429-r1 dans
`runner/operations/active_ability.py`, cable en tete du visiteur (`abilities/handler.py`), au rang
natif -- AVANT ce filtre-ci. Son gate est le virtuel slot 0x11 `CanContinueOnDeadTarget`, dont
l'inventaire des overrides a ete releve (aucun) et dont le bit lu -- 38 `AllowDeadTarget` -- n'a
qu'UN porteur dans tout le binaire (`GreatFrostAxeAbility$$GetTargetingOptionsForContinue`). La
crainte « un defaut refuse casserait les abilities de resurrection » est levee par cette mesure : le
NATIF refuse pour toutes les autres, et les resurrections portees ne prennent pas un cadavre en
`target_id`.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Optional

from .targeting_rule import TargetingRule as TR
from ...dsl.base import Const                                       # #287-r11-r1 (hisse, #485)
from ...entities.selectors.accessors import CasterTile, SelectTile, Target, TargetTile
from ...entities.selectors.geometry import SortReverse, TilesBehindInLine
from ...entities.selectors.tiles import Caster, tiles_unit_can_move_to_charge_target
from ...entities.selectors.units import Enemies, Units  # idem
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType   # #270-r1-r1-r3
from ...entities.heal_type import HealType   # #287-r5
from ...entities.unit_flag import UnitFlag   # #270-r1-r1-r3
from ...entities.traits.unit_trait import UnitTrait   # #270-r1-r1-r3
from ...entities.stats import StatType
from ...entities.traits.unit_trait import entity_trait_names
from ...entities.traits import unit_trait as _unit_trait   # forme B (#116-r1) : foyer `is_mechanical`
from ...services import battle_query as _bq
from ...services.custom_normal_attack import custom_normal_attack
from ...services.movement_query import get_distance
from ...services.movement_query import get_tiles_obscuring_terrain_from_tiles
import engine.services.movement_query as _mq   # FORME B (#547-r2), et ABSOLUE : `get_movable_
# tiles_for` / `get_movable_positions_for` sont SUBSTITUABLES par les probes de #590-r6 via le
# chemin PLEIN. Aucune arete neuve -- ce module importe deja `services.movement_query` ci-dessus.
from ..components import ForcedAttackTargetsComponent
from ..components import MachineComponent
from ..components import MachineComponent, UnitComponent
from ..components import OwnerComponent
from ..components import OwnerComponent, PositionComponent, UnitComponent
from ..components import PositionComponent
from ..components import StatsComponent
from ..components import StatsComponent, UnitComponent
from ..components import UnitComponent
from ..components import UnitFlagsComponent
from ..components import get_unit_feet
from ..components import has_effect_of_type
from ..components import is_turn_of_unit   # `BattleQuery$$IsTurnOfUnit` (#287-r11-r1-r1-r2)
from ..components import unit_has_moved
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ..state import State


# `UnitFlag` 0x11 : `IdunBattle.Entities.UnitExtensions$$IsTargetable` = `!HasFlag(unit, 0x11)`.
UNIT_FLAG_NOT_TARGETABLE = UnitFlag.Untargetable

# `IdunBattle.Entities.EffectType.FriendlyFire` = 0x67 : lu par
# `IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` — un porteur peut attaquer ses
# AMIS (et seulement eux).
EFFECT_FRIENDLY_FIRE = EffectType.FriendlyFire

# `IdunBattle.Entities.Enum.EffectType.ForcedInMelee` = 0x529 : lu par
# `IdunBattle.Core.Services.TargetingQuery$$GetRange` — le porteur ne porte plus qu'a 1 (adjacence).
EFFECT_FORCED_IN_MELEE = EffectType.ForcedInMelee

# `IdunBattle.Core.Services.RangedBool` (enum, dump VERBATIM) — un booleen a DEUX valeurs constantes
# et deux valeurs CALCULEES sur le caster ; resolu par
# `IdunBattle.Core.Services.RangedBoolExtensions$$IsTrue`.
RANGED_BOOL_TRUE = 0
RANGED_BOOL_FALSE = 1
RANGED_BOOL_IF_RANGED_CASTER = 2
RANGED_BOOL_IF_NOT_RANGED_CASTER = 3

# `IdunBattle.Entities.Enum.UnitTrait.Ranged` = 0xb ; `.Steppable` = 0x1b — lus respectivement par
# `IdunBattle.Entities.UnitExtensions$$IsRanged` et `IdunBattle.Entities.TileExtensions$$HasSteppableUnit`.
UNIT_TRAIT_RANGED = UnitTrait.Ranged
UNIT_TRAIT_STEPPABLE = UnitTrait.Steppable

# `IdunBattle.Configuration.AbilityConstantType.range` = 0x16 — la constante que
# `IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` recopie dans
# `options.Range.OverrideRange` quand `UseRangeFromConfig` est pose. Cle gameconfig : `constants.range`.
ABILITY_CONSTANT_RANGE = "range"

# `IdunBattle.Configuration.AbilityConstantType.nrOfTiles` = 0x17 — la LONGUEUR de ligne que
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles`
# passe en `Direct(...)` au `maxAmount` de `TilesBehindInLine`. Cle gameconfig : `constants.nrOfTiles`.
ABILITY_CONSTANT_NR_OF_TILES = "nrOfTiles"
EXCRUCIATING_FREQUENCIES_ID = "ExcruciatingFrequencies"


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
    ability qui le pose n'a AUCUNE portee derivable de ses autres champs. `get_range` rend alors un
    `Range` a `value = None` -> aucun gate de DISTANCE (le gate d'adjacence, lui, tient : le delegue
    n'ecrit pas `onlyAdjacent`). C'est different de `range = None` (= `TargetingRange` pas encore
    RE-lu) : ici le `TargetingRange` EST lu, c'est la VALEUR que le delegue produit qui n'est pas
    resolue.

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

    Le delegue n'est pas resolu (cf. `TargetingRange.override_range_func`) -> `get_range` rend un
    `Range` a `value = None`, donc aucun gate de DISTANCE ; le gate d'ADJACENCE tient (le delegue
    n'ecrit pas `onlyAdjacent`, cf. `Range` et #419-r1-tr14-r5-r2-r1-r2-r1-r1). On enregistre le
    FAIT que le ctor le pose, pas une valeur devinee."""
    return TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=None,
                          override_range_func=True)


@dataclass(frozen=True)
class Range:
    """`IdunBattle.Core.Services.TargetingQuery.Range` — la valeur de retour de
    `TargetingQuery$$GetRange`, 8 octets :

        +0x00  int  Value
        +0x04  bool OnlyAdjacent
        +0x05  bool UseWholeBoard

    Le filtre statique lit le champ `@+0x04` pour choisir entre `AreEntitiesAdjacent` et la
    comparaison de distance — c'est ce qui fixe l'ordre des deux premiers. LU aux octets :
    `GetInvalidTargetReason` teste `range._4_1_` puis, dans l'autre branche seulement, `(int)range`.

    Le TROISIEME champ est etabli par `TargetingQuery$$GetTilesInRange`, qui teste les trois
    separement (`(int)range < 0`, `range._5_1_`, `range._4_1_`), et recoupe par le litteral
    `0x10000000001` que `GetRange` rend sous `UseWholeBoard` (= `{1, false, true}`).

    **IL EST DESORMAIS MODELISE, et la RE-lecture a etabli mieux qu'une equivalence de
    comportement : le champ est un ALIAS EXACT d'`options.Range.UseWholeBoard`**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1). `TargetingQuery$$GetRange` n'a que TROIS sorties, et
    chacune l'ecrit depuis la MEME source :

      1. `casterTiles` vide -> `((*(ulonglong *)(options + 8) >> 0x28) & 0xff) << 0x28`, c'est-a-dire
         l'octet `TargetingRange+0x05` RECOPIE tel quel dans le bit 40 du retour ;
      2. court-circuit `!cap.HasValue && options.Range.UseWholeBoard` -> `0x10000000001`, atteint
         SEULEMENT quand ce champ vaut vrai ;
      3. sortie complete -> `(cVar2 != 0) << 0x20` puis `CONCAT44(...)`, donc bits 40..47 a ZERO,
         atteinte SEULEMENT quand il vaut faux (sinon (2) l'a court-circuitee).

    Le modeliser ne cree donc AUCUNE information nouvelle -- et c'est precisement ce qui le rend
    sur : le mirror devient structurel sans qu'aucun consommateur puisse diverger. L'ancienne
    formulation (« le port ne le modelise PAS, meme comportement sur le seul consommateur porte »)
    etait vraie mais reposait sur l'inventaire des consommateurs, donc se serait perimee au premier
    consommateur neuf.

    **`value = None` = la portee NUMERIQUE n'est pas observable, `only_adjacent` l'est quand meme**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1). Les deux champs sont INDEPENDANTS dans le natif : `onlyAdjacent`
    y est calcule AVANT toute resolution d'arme et n'est ensuite que FORCE a vrai par deux conditions
    (`HasEffect(0x529 ForcedInMelee)`, `IsTrue(ForceMeleeTarget) && ShouldApplyRangedInMelee`) qui ne
    lisent pas davantage la valeur. Un tri-etat sur `value` seule est donc le mirror exact — et non un
    `None` global, qui abandonnait AUSSI la branche d'adjacence, laquelle ne lit jamais `Value`."""
    value: Optional[int] = 0
    only_adjacent: bool = False
    #: `Range+0x05`. ALIAS EXACT d'`options.Range.UseWholeBoard` (cf. les trois sorties ci-dessus).
    use_whole_board: bool = False


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


# --- LE SECOND JEU D'OPTIONS : `GetTargetingOptionsForContinue` (#419-r1-tr14-r5-r2-r1-r2-r2) -----
#
# UN RECENSEMENT DES MASQUES QUI S'ARRETE AUX `$$.ctor` EST INCOMPLET, et c'est ce que ce bloc
# repare. Le natif produit un SECOND jeu d'options, loge a `this+0xb0` et consomme par la lambda
# `...ActiveAbilityOperation.u003Cu003Ec__DisplayClass9_0$$u003CIsInvalidTargetu003Eb__1`
# (slot 0xe = `AActiveAbility$$GetInvalidTargetReasonForContinue`) -- le mode « continue » d'une
# ability multi-etapes. Aucun `$$.ctor` ne l'ecrit : il est CALCULE.
#
# LA LOI DE BASE, VERBATIM d'`IdunBattle.Entities.Abilities.AActiveAbility$$
# GetTargetingOptionsForContinue` (les offsets sont ceux de la struct de 0x40 octets) :
#
#     SetConfigValuesInTargetingOptions(this, &this.<TargetingOptions @+0x70>)
#     opts = TargetingOptions..ctor(<copie de this+0x70..0xaf>)     # surcharge COPIE PURE
#     opts.<+0x20 forceMeleeTarget> = 1                             # = RangedBool.False
#     opts.<+0x28 rules> |= 0x10000000000                           # AllowIgnoreForcedAttackTarget
#     return Nullable<TargetingOptions>(opts)
#
# Soit, en clair : le masque du ctor, plus la PERMISSION d'ignorer la cible forcee (le TAUNT ne
# contraint pas la poursuite d'une ability deja engagee), et jamais de rabattement en melee.
#
# ⚠ DEUX SURCHARGES REECRIVENT LE JEU ENTIER -- la fiche du residu n'en nommait qu'UNE. Chacune
# IGNORE `this+0x70` et repart d'un litteral, donc la loi de base ne s'y applique PAS :
#   * `1089 GreatFrostAxe` -- forme PRESET + additionalRules :
#         TargetingOptions..ctor(&opts, &<TargetingOptions statics>+0x40, 0x4000000000)
#     Le preset `statics+0x40` est deja lu ailleurs dans le port (`Rules = 0x4000 TargetIsEnemy`,
#     `isSelfCasting = 0`, range = `TargetingRange statics+0x30` = RANGE_ADJACENT,
#     `forceMeleeTarget = 1`). Masque EFFECTIF = `TargetIsEnemy | AllowDeadTarget`.
#   * `1168 EntropyCannons` -- forme FLAGS DIRECTS (6 parametres) :
#         TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x40004000, 0, 0)
#     Masque EFFECTIF = `TargetIsEnemy | AllowNullCasterTile`, range = RANGE_WHOLE_BOARD.
#     ⚠ IL DESARME `TargetMatchesDynamicRule` : le masque de son `.ctor` vaut `0x40004002`, celui-ci
#     `0x40004000`. La poursuite ne re-consulte donc PAS sa regle dynamique.
#
# ⚠ AUCUN CONSOMMATEUR COTE PORT, ET C'EST DIT PLUTOT QUE TU : le port n'a pas la face
# « continue » (aucune ability multi-etapes n'y passe par `b__1`), donc rien n'appelle ce qui suit.
# C'est un RECENSEMENT, pas un chemin actif -- le residu portait sur l'exhaustivite du recensement,
# pas sur un ecart mesure. Le cast top-level passe par `b__0`, jamais par ici.
#
#: `{ability_id: TargetingOptions}` -- les surcharges qui REECRIVENT le second jeu. L'exhaustivite
#: est gardee par `tests/engine/runner/test_419_options_for_continue_offline.py`, qui balaie les
#: `$$GetTargetingOptionsForContinue` du dump : une surcharge NEUVE au prochain build fait rougir.
TARGETING_OPTIONS_FOR_CONTINUE_OVERRIDES: "dict[int, TargetingOptions]" = {
    # `...GreatFrostAxeAbility$$GetTargetingOptionsForContinue` -- PRESET `<TargetingOptions
    # statics>+0x40` + `additionalRules = 0x4000000000`.
    int(ActiveAbilityType.GreatFrostAxe): TargetingOptions(          # 1089
        rules=TR.TargetIsEnemy | TR.AllowDeadTarget, self_cast=False,
        range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE),
    # `...EntropyCannonsAbility$$GetTargetingOptionsForContinue` -- FLAGS DIRECTS, `0x40004000`.
    int(ActiveAbilityType.EntropyCannons): TargetingOptions(         # 1168
        rules=TR.TargetIsEnemy | TR.AllowNullCasterTile, self_cast=False,
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE),
}


def targeting_options_for_continue(options: "TargetingOptions",
                                   ability_id=None) -> "TargetingOptions":
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue` -- MIRROR.

    Rend le SECOND jeu d'options (`this+0xb0`), celui que lit le mode « continue ». `options` = le
    jeu du `$$.ctor` APRES `SetConfigValuesInTargetingOptions` (cf. la loi citee au-dessus).

    `ability_id` aiguille vers une SURCHARGE quand la classe en declare une : celles-ci n'appliquent
    PAS la loi de base, elles repartent d'un litteral."""
    if ability_id is not None:
        sur = TARGETING_OPTIONS_FOR_CONTINUE_OVERRIDES.get(int(ability_id))
        if sur is not None:
            return sur
    return replace(options,
                   rules=int(options.rules) | int(TR.AllowIgnoreForcedAttackTarget),
                   force_melee_target=RANGED_BOOL_FALSE)


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
# ⚠ Une entree PEUT en sortir : depuis #287 le masque de 1100 `SorcerousFacade` a MIGRE sur sa classe
# (et depuis #490 celui de 1027 `PsychicMaelstrom`, meme mouvement)
# du registre COMBAT (`engine/runner/abilities/loki/facade.py::SorcerousFacadeAbility.TARGETING_OPTIONS`),
# parce que sa face COMBAT est desormais portee. Le CONTRAT de disjonction est ce qui rend cette
# migration sure : porter la face COMBAT d'une entree d'ici EXIGE de retirer sa ligne. Le
# MECANISME de la 2e source, lui, reste garde par
# `tests/engine/runner/test_targeting_options_sources.py` (une entree bidon injectee par monkeypatch
# verifie que `targeting_options_for` consulte toujours cette table).
TARGETING_OPTIONS_UNPORTED: "dict[int, TargetingOptions]" = {
    # @FORME PRESET+FLAGS
    # ⚠ 1216 `MartialExemplar` A QUITTE CETTE TABLE (#889-r5), pour la meme raison et par le meme
    # geste que 1217 et 1093 ci-dessous : sa face COMBAT est desormais portee, et le CONTRAT DE
    # DISJONCTION exige alors le retrait de la ligne. Son masque -- les MEMES quatre valeurs,
    # RE-LUES au decompile de `rnca9r7q6c` avant migration (preset `<TargetingOptions statics>+0x280`
    # = `0x8004` OR `additionalRules = 0x10` -> `0x8014`) -- vit sur la classe,
    # `runner/abilities/darkangels.py::MartialExemplarAbility.TARGETING_OPTIONS`, avec la lecture
    # complete du preset. Elle etait la SEULE entree `@FORME PRESET+FLAGS` de cette table ;
    # l'etiquette reste pour le prochain masque de cette forme.
    # @FORME STATIC-COPY   (le ctor recopie les 0x40 octets d'un preset et n'appelle AUCUN
    #                       `TargetingOptions$$.ctor` ; le masque est la constante du `cctor`)
    # ⚠ QUATRE RETRAITS SE SONT CROISES ICI (1217/#889, 1093/#888, 1216/#889-r5, 1215/#889-r6), et
    # la resolution
    # est leur UNION -- pas un arbitrage. Aucun des trois ne contredit les deux autres : chacun
    # constate qu'UNE ability differente a migre son masque sur sa classe.
    # ⚠ 1217 `TheLionsWrath` A QUITTE CETTE TABLE (#889) : sa face COMBAT est desormais portee, et le
    # CONTRAT DE DISJONCTION ci-dessus exige alors le retrait de la ligne. Son masque -- les MEMES
    # quatre valeurs, RE-LUES au decompile avant migration -- vit sur la classe,
    # `runner/abilities/darkangels.py::TheLionsWrathAbility.TARGETING_OPTIONS`, avec la lecture
    # complete du preset `<TargetingOptions statics>+0x40`.
    # ⚠ 1093 `MortarionsPlagueWind` A QUITTE CETTE TABLE (#888), pour la MEME raison : sa face COMBAT
    # est portee (`runner/abilities/deathguard.py::MortarionsPlagueWindAbility`), donc son masque
    # (STATIC-COPY `<TargetingOptions statics>+0x180`, `<preset>+0x28` = 0x4002, le MEME preset que
    # son jumeau 1035) vit desormais sur la classe, avec la lecture complete du preset.
    # ⚠ 1215 `InstrumentsOfVengeance` A QUITTE CETTE TABLE (#889-r6), pour la MEME raison et par le
    # MEME geste que 1217, 1093 et 1216 ci-dessus : sa face COMBAT est desormais portee
    # (`runner/abilities/loki/instruments_of_vengeance.py::InstrumentsOfVengeanceAbility`), et le
    # CONTRAT DE DISJONCTION exige alors le retrait de la ligne. Son masque -- les MEMES quatre
    # valeurs, RE-LUES au decompile de `rnca9r7q6c` avant migration (preset
    # `<TargetingOptions statics>+0x280` recopie TEL QUEL, `<preset>+0x28` = `0x8004`, SANS le
    # `additionalRules = 0x10` de 1216, donc SANS `CasterHasNotMoved` ; `isSelfCasting` = 1 ;
    # `forceMeleeTarget` = 1 = `RangedBool.False` ; `range` = `RANGE_SELF`) -- vit sur la classe.
    # La MESURE qui separe ce masque de celui de 1216 y est reportee : `abilityTargets(1215)` rend
    # UNE cible, le caster lui-meme, et elle SURVIT au deplacement du caster
    # (`probe_27_r6_instruments_of_vengeance.py`).

    # ============================================================================================
    # LES ABILITIES ACTIVES DU POOL SPAWNABLE HORS REGISTRE (#433-r4-r2-r1-r2-r2-r1-r1)
    # ⚠ Le lot etait de **32** a la mesure ; les entrees ECRITES ici, elles, DECROISSENT a chaque
    #   face COMBAT portee, par migration du masque sur la classe (contrat de disjonction ci-dessus).
    #   Re-deriver le compte, ne JAMAIS citer les chiffres ci-dessous comme s'ils etaient courants.
    # ============================================================================================
    # PERIMETRE, re-derive et non herite : les abilities ACTIVES (`gameconfig.activeAbilities`) des
    # 97 unites que rend `rl_duel build --list-pool` au rank courant, MOINS celles d'`ABILITY_CLASSES`
    # -- soit exactement l'ensemble des masques que `BattleQuery$$IsTileInRangeOfAnyAbility` peut
    # avoir a lire sur un ennemi confrontable. Elles etaient **32** a la mesure de #433-r4, et le
    # volet PORTEE de ces memes 32 etait deja lu (il vivait dans
    # `engine.services.ability_range.TARGETING_RANGE_BY_ABILITY`, que cette tranche SUPPRIME : une
    # ability n'a qu'UNE source d'options, jamais deux).
    #
    # ⚠ **32 = le PERIMETRE MESURE de #433-r4, PAS le compte d'entrees ecrites ici.** Les deux
    # nombres bougent independamment, et dans les DEUX sens : des masques ENTRENT dans le bloc (lots
    # ulterieurs, tous appendus en section STATIC-COPY) et il en SORT des qu'une face COMBAT est
    # portee -- le CONTRAT de disjonction de cette table l'exige alors. Sorties a ce jour, dans
    # l'ordre des tranches : 1088 (#487), 1087 (#488), 1048 (#489), 1027 (#490), 1069 (#491),
    # 1068 (#497), 1152 (#498), 1019 (#499), 1038 (#500), 1141 (#503), 1132 (#504),
    # 1204 (#508), 1191 (#509), 1177 (#510), 1197 (#512) -- QUINZE.
    # ⚠ #508, #509, #510 et #512 se sont croisees ICI : chacune n'ajoutait QUE son id a cette liste
    #   et n'annoncait QUE son propre retrait. La resolution est l'UNION des retraits.
    #
    # ⚠ AUCUN COMPTE DE CETTE TABLE NE S'ECRIT PLUS A LA MAIN (#519) -- ils vivent dans le BLOC
    # GENERE ci-dessous, derive du code. Ce n'est pas une precaution de style : SEPT tranches
    # (#498 a #504) ont retire une entree CHACUNE, en parallele et aveugles les unes aux autres,
    # et le compte ecrit ici a ete faux QUATRE fois dans la seule journee du 2026-08-07.
    # QUATRE illustrations, toutes au meme endroit :
    #   * le chiffre d'avant #503 (« 31 entrees ecrites, 10/4/1/16 ») etait deja faux de 2 sur un
    #     arbre qui en portait 29 -- la ventilation « 16 » ne correspondait a aucune section ;
    #   * la version de #503 ecrite AVANT son premier rebase annoncait « 32 dans ce bloc » sur un
    #     arbre qui portait encore 1019, 1038, 1165 et 1064 ;
    #   * celle ecrite APRES ce rebase (« 28 ») s'est perimee quand #504 a retire 1132 pendant la
    #     validation de #503 ; celle de #509 (« 26 ecrites, 30 au total ») etait perimee de DEUX ;
    #   * et la correction FINALE du 2026-08-07 -- celle qui se declarait « RE-COMPTEE PAR LE
    #     CODE » -- annoncait une ventilation par forme de `10 / 4 / 0 / 13` la ou le code en
    #     portait `12 / 6 / 0 / 9`. TROIS nombres faux sur quatre, et leur SOMME juste (27 des
    #     deux cotes) : le seul controle qu'un relecteur pouvait faire de tete PASSAIT. Un accord
    #     peut etre le produit de fautes qui se compensent.
    # Un compteur qu'on ecrit soi-meme n'est pas plus fiable qu'un compteur herite.
    #
    # Les nombres entre parentheses « en #433-r4 » ci-dessous sont, eux, des faits de RE FIGES
    # (la mesure du lot de 32) : ils ne bougent jamais, et le contre-controle de la fin du bloc
    # porte sur CE perimetre-la.
    #
    # COMMENT LA SURCHARGE A ETE TRANCHEE -- par les XREFS ENTRANTES, jamais a l'oeil. Ghidra rend le
    # meme nom decompile (`TargetingOptions___ctor`) pour les trois surcharges de
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` ; ce qui les separe est leur ADRESSE, et donc
    # l'appartenance d'un ctor d'ability a leur liste d'appelants :
    #
    #   surcharge A -- `.ctor(this, isSelfCasting, range, forceMeleeTarget, rules, dynCaster, dynTarget)`
    #                  FLAGS DIRECTS : `this+0x28 = rules`. Le litteral EST le masque.  (14 en #433-r4)
    #   surcharge B -- `.ctor(this, template, additionalRules)`
    #                  PRESET + FLAGS : `this+0x28 = additionalRules | template+0x28`.   (5 en #433-r4)
    #   surcharge C -- `.ctor(this, template)`
    #                  PRESET SEUL (copie PURE, 8 qwords verbatim, AUCUN `|`).           (1 en #433-r4)
    #                  (la SEULE, 1129 `BloodyFury`, est SORTIE en #505 -- la section est VIDE.)
    #   (aucun ctor) -- STATIC-COPY : les 0x40 octets d'un preset sont recopies dans un local passe
    #                  TEL QUEL a `AActiveAbility$$.ctor`. Masque = `<preset>+0x28`.    (12 en #433-r4)
    #                  (MIGRATIONS de cette forme, dans l'ordre : 1204 -- preset `+0x240` -- vers
    #                   `LeadingTheChargeAbility.TARGETING_OPTIONS` (#508) ; 1191 -- preset `+0x40`
    #                   -- (#509) ; 1177 -- MEME preset `+0x240` que 1204 -- vers
    #                   `LightOfSanguiniusAbility.TARGETING_OPTIONS` (#510). Les deux JUMEAUX du
    #                   preset `+0x240` sont donc sortis, chacun par sa tranche.)
    #
    # CHAQUE ENTREE porte sa forme par le marqueur `@FORME <...>` le plus proche AU-DESSUS d'elle :
    # les en-tetes de section en portent un, et les quatre entrees hors-bloc -- qui ne vivent dans
    # aucune section -- en portent un chacune. C'est ce marqueur, et lui seul, qui rend la
    # ventilation ci-dessous DERIVABLE au lieu d'etre recomptee a l'oeil.
    #
    # >>> COMPTES DERIVES (#519) -- BLOC GENERE -- ne pas editer a la main.
    #     Re-generer : `python scripts/python/probe_519_comptes_de_table.py --ecrire`
    #     Garde : `tests/engine/test_519_comptes_derives_offline.py`. Ces nombres ne sont
    #     PAS des faits de RE -- ils bougent a chaque face COMBAT portee, et c'est pour ca
    #     qu'aucun d'eux n'est ecrit a la main.
    #
    #     len(TARGETING_OPTIONS_UNPORTED) ......... 0
    #       dont hors-bloc (tete de table) ..... 0
    #       dont bloc du pool (#433-r4) ........ 0
    #
    #     VENTILATION PAR FORME DE CTOR (dict ENTIER, hors-bloc compris) :
    #       FLAGS-DIRECTS  ..................... 0
    #       PRESET+FLAGS   ..................... 0
    #       PRESET-SEUL    ..................... 0
    #       STATIC-COPY    ..................... 0
    #       (somme = 0)
    # <<< FIN COMPTES DERIVES
    #
    # LES 16 PRESETS, RELUS A LA SOURCE dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`
    # (layout `isSelfCasting@+0x00`, `range@+0x08..0x1f`, `forceMeleeTarget@+0x20`, `rules@+0x28`) --
    # seuls ceux consommes par ce lot sont repris ici :
    #
    #   preset +0x000 : self 0 | TR statics+0x00 ADJ_IF_MELEE | melee 2 IfRangedCaster | rules 0x4002
    #   preset +0x040 : self 0 | TR statics+0x30 ADJACENT     | melee 1 False          | rules 0x4000
    #   preset +0x140 : self 0 | TR statics+0x18 FROM_CONFIG  | melee 0 True           | rules 0x4002
    #   preset +0x180 : self 0 | TR statics+0x18 FROM_CONFIG  | melee 1 False          | rules 0x4002
    #   preset +0x240 : self 0 | TR statics+0x48 WHOLE_BOARD  | melee 1 False          | rules 0x102004032
    #   preset +0x280 : self 1 | TR statics+0x60 SELF         | melee 1 False          | rules 0x8004
    #
    # ⚠ `+0x140` et `+0x180` portent le MEME masque `0x4002` et different par `forceMeleeTarget`
    # (0 contre 1) -- le piege « meme masque, presets differents » : recopier le masque sans le preset
    # entier laisse le volet PORTEE faux. Les deux sont dans ce lot (1088 contre 1027/1069).
    #
    # CONTRE-CONTROLE INDEPENDANT (perimetre #433-r4) : les 32 valeurs d'alors concordent avec
    # l'artefact genere `docs/rl/case-302-4/tile-target-population.json` (champs `form` et `rules`),
    # obtenu par un balayage distinct. 32/32, aucune divergence. Les entrees ajoutees DEPUIS ne sont
    # pas couvertes par cet artefact-la.
    #
    # BIT 43 `AllowUnwalkableTargetTile` : **0 porteur sur les 32 de #433-r4**. Le terme de
    # walkability (`engine.services.targeting_query.tile_removed_by_walkability`) mord donc pour eux.

    # @FORME FLAGS-DIRECTS
    # --- surcharge A, FLAGS DIRECTS (14 LUES en #433-r4) : le litteral du ctor EST le masque -----
    # ⚠ « 14 LUES » est un fait de RE FIGE (le lot de 32 de `#433-r4-r2-r1-r2-r2-r1-r1`) et ne se
    #   decremente JAMAIS. Le compte des entrees REELLEMENT presentes ici, lui, DIMINUE a chaque
    #   face COMBAT portee -- 1087 ExemplarOfTheKauyon (#488), 1152 UnstoppableMomentumReworked
    #   (#498), 1019 StormOfWrath (#499), 1038 FoulInfusion (#500) et 1141 OverwhelmingWrath (#503)
    #   ont MIGRE sur leur classe. Confondre les deux est ce qui a fait ecrire quatre chiffres faux
    #   en un jour : le second N'EST PLUS ECRIT ICI, il vit dans le BLOC GENERE de l'en-tete (#519).
    # 1005 AdaptiveStrategy : MIGRE vers `ABILITY_CLASSES` (#577) -- sa face COMBAT est desormais
    #   portee (`abilities/necrons.py::AdaptiveStrategyAbility.TARGETING_OPTIONS`), donc le CONTRAT
    #   DE DISJONCTION impose de retirer sa ligne d'ici. Le masque a ete RE-LU au decompile avant
    #   migration et est bit-identique a celui qui vivait ici
    #   (`.ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0x402, 0, 0)` -- surcharge a 7 arguments
    #   `(isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
    #   getDynamicInvalidTargetReason)`, tranchee par l'ADRESSE du call ; les DEUX delegues sont NULS,
    #   la regle dynamique vient du slot VIRTUEL de la sous-classe).
    # 1019 StormOfWrath -- MIGRE (#499) sur
    #   `runner/abilities/ultramarines.py::StormOfWrathAbility.TARGETING_OPTIONS` avec sa face
    #   COMBAT (le noeud `ChainAbilityDamage`) ; contrat de disjonction ci-dessus. Valeurs
    #   INCHANGEES, relues au decompile a l'occasion :
    #   `.ctor(&opts, 0, &<TargetingRange statics+0x00>, 1, 0x4000, 0, 0)`.
    # 1038 FoulInfusion -- MIGRE (#500) sur
    #   `runner/abilities/loki/foul_infusion.py::FoulInfusionAbility.TARGETING_OPTIONS` avec sa face
    #   COMBAT ; contrat de disjonction ci-dessus. (Le `range` y reste un DELEGUE
    #   `TargetingRange$$CustomRange(GetRange)` -> `custom_range_func()`, portee non derivable.)
    # 1039 RitesOfRestoration -- MIGRE (#564) sur
    #   `runner/abilities/sisterhood.py::RitesOfRestorationAbility.TARGETING_OPTIONS` avec sa face
    #   COMBAT (`op_BitwiseAnd(Heal, Resurrect)`) ; contrat de disjonction ci-dessus. Le masque a ete
    #   RE-LU au decompile avant migration et est bit-identique a celui qui vivait ici :
    #   `.ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0x8508, 0, 0)`.
    # 1049 CrusadeOfWrath : MIGRE vers `ABILITY_CLASSES` (#893) -- sa face COMBAT est desormais
    #   portee (`runner/abilities/blacktemplars.py::CrusadeOfWrathAbility.TARGETING_OPTIONS`), donc
    #   le CONTRAT DE DISJONCTION ci-dessus lui interdit de rester ici. Le masque a ete RE-LU au
    #   decompile avant migration et est bit-identique a celui qui vivait ici :
    #   `.ctor(&opts, 1, &<TargetingRange statics+0x18>, 1, 0x400, 0, 0)`.
    # 1057 GrotTank : MIGRE vers `ABILITY_CLASSES` (#570) -- sa face COMBAT est desormais portee
    #   (`runner/abilities/orks.py::GrotTankAbility.TARGETING_OPTIONS`), donc le CONTRAT DE
    #   DISJONCTION impose de retirer sa ligne d'ici. Le masque a ete RE-LU au decompile avant
    #   migration et est bit-identique a celui qui vivait ici
    #   (`.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x1040, 0, 0)`).
    # 1061 UnbreakableDuty : MIGRE vers `ABILITY_CLASSES` (#572) -- sa face COMBAT est desormais
    #   portee (`abilities/blacktemplars.py::UnbreakableDutyAbility.TARGETING_OPTIONS`), donc le
    #   CONTRAT DE DISJONCTION impose de retirer sa ligne d'ici. Le ctor a ete RELU au decompile
    #   avant migration et la valeur qui vivait ici est CONFIRMEE champ pour champ :
    #   `.ctor(&opts, 1, &<TargetingRange statics+0x18>, 1, 0x8400, 0, 0)` -- `selfCast = True`,
    #   `range` = FROM_CONFIG (`constants.range` = 2), `forceMeleeTarget = 1` (RangedBool.False),
    #   `rules` = `TargetIsFriendly | CasterIsPossibleTarget`. C'est la SOURCE qui bouge, jamais la
    #   valeur.
    # 1087 ExemplarOfTheKauyon -- MIGRE (#488) sur `runner/abilities/tau.py::ExemplarOfTheKauyonAbility.TARGETING_OPTIONS`
    #   avec sa face COMBAT ; contrat de disjonction ci-dessus.
    # 1121 ItItches : MIGRE vers `ABILITY_CLASSES` (#550) -- sa face COMBAT est desormais portee
    #   (`abilities/tyranids.py::ItItchesAbility.TARGETING_OPTIONS`), donc le CONTRAT DE DISJONCTION
    #   impose de retirer sa ligne d'ici. Le masque a ete RE-LU au decompile avant migration et est
    #   bit-identique a celui qui vivait ici
    #   (`.ctor(&opts, 0, &<TargetingRange statics+0x30>, 0, 0x80040, 0, 0)` -- `forceMeleeTarget = 0`
    #   = `RangedBool.True`, l'enum natif etant INVERSE ; l'une des DEUX du lot hors defaut).
    # 1141 OverwhelmingWrath : MIGRE vers `ABILITY_CLASSES` (#503) -- sa face COMBAT est desormais
    #   portee (`abilities/worldeaters.py::OverwhelmingWrathAbility.TARGETING_OPTIONS`), donc le
    #   CONTRAT DE DISJONCTION impose de retirer sa ligne d'ici. Le masque a ete RE-LU au decompile
    #   avant migration et est bit-identique a celui qui vivait ici
    #   (`.ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0x4000, 0, 0)`).
    # 1152 UnstoppableMomentumReworked : MIGRE vers `ABILITY_CLASSES` (#498) -- sa face COMBAT est
    #   desormais portee (`abilities/loki/momentum.py::UnstoppableMomentumReworkedAbility.
    #   TARGETING_OPTIONS`), donc le CONTRAT DE DISJONCTION impose de retirer sa ligne d'ici. Le
    #   masque a ete RE-LU au decompile avant migration et est bit-identique a celui qui vivait ici
    #   (`.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x10120040, 0, 0)`).
    # 1164 MindControl : SORTIE (#552) -- sa face COMBAT est portee
    #   (`abilities/loki/mind_control.py::MindControlAbility.TARGETING_OPTIONS`), donc le CONTRAT DE
    #   DISJONCTION impose de retirer sa ligne d'ici. Le ctor a ete RELU au decompile avant migration
    #   et la valeur qui vivait ici est CONFIRMEE champ pour champ :
    #   `.ctor(&opts, 0, &<TargetingRange statics+0x18>, 1, 0x4002, 0, 0)` -- `selfCast = False`,
    #   `range` = FROM_CONFIG (= 3), `forceMeleeTarget = 1` (RangedBool.False), `rules` =
    #   `TargetMatchesDynamicRule | TargetIsEnemy`. C'est la SOURCE qui bouge, jamais la valeur.
    #   ⚠ Sa regle dynamique, elle, n'a JAMAIS eu d'entree dans `DYNAMIC_TARGET_RULE_UNPORTED` :
    #   le porteur de repli rendait donc `0` (permissif). Elle est desormais PORTEE sur la classe.
    # 1175 BloodChalice : SORTIE (#576) -- sa face COMBAT est portee
    #   (`abilities/bloodangels.py::BloodChaliceAbility.TARGETING_OPTIONS`), donc le CONTRAT DE
    #   DISJONCTION impose de retirer sa ligne d'ici. Le ctor a ete RELU au decompile avant migration
    #   et la valeur qui vivait ici est CONFIRMEE champ pour champ :
    #   `...Active.BloodChaliceAbility$$.ctor` (hors namespace `Loki`) =
    #   `.ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0xc02, 0, 0)` -- `selfCast = True`,
    #   `range` = ADJACENT, `forceMeleeTarget = 1` (RangedBool.False), `rules` =
    #   `TargetMatchesDynamicRule | TargetIsFriendly | AddCasterIfAtLeastOneTarget`. C'est la SOURCE
    #   qui bouge, jamais la valeur.
    # 1197 ExcruciatingFrequencies : SORTIE (#512) -- sa face COMBAT est portee, donc son masque a
    #   MIGRE sur `emperorschildren.ExcruciatingFrequenciesAbility.TARGETING_OPTIONS`. Le ctor a ete
    #   RELU a cette occasion et la valeur qui vivait ici est CONFIRMEE champ pour champ :
    #   `.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x20000000042, 0, 0)` -- `selfCast =
    #   False`, `range` = ADJACENT, `forceMeleeTarget = 1` (RangedBool.False), `rules` =
    #   `TargetMatchesDynamicRule | TargetIsTile | AllowUntargetableTarget`. C'est la SOURCE qui
    #   bouge, jamais la valeur.

    # @FORME PRESET+FLAGS
    # --- surcharge B, PRESET + FLAGS : `rules = additionalRules | <preset>+0x28` ----------------
    # ⚠ 1048 FragstormGrenadeLauncher (preset `+0x180` + flags `0x2000000` -> `0x2004002`) est
    #   SORTIE d'ici : sa face COMBAT est portee depuis #489, donc son masque vit sur la classe du
    #   registre (`engine/runner/abilities/blacktemplars.py::FragstormGrenadeLauncherAbility`).
    #   Meme migration que 1069 et 1088 -- c'est le CONTRAT DE DISJONCTION, et il avait ete
    #   OUBLIE au merge de #763 : l'entree restait ici pendant que la classe entrait au registre,
    #   ce qui a rendu `master` ROUGE sur `test_targeting_options_sources` (2 failed) pendant
    #   trois commits. `probe_181` restait VERT tout du long -- il verifie qu'un masque EXISTE,
    #   jamais qu'il n'est declare QU'UNE FOIS. Les deux axes sont distincts : jouer le premier
    #   ne dispense pas du second.
    # ⚠ 1050 HolyDuel (preset `+0x40` + flags `0x200000000` -> `0x200004000`) est SORTIE d'ici : sa
    #   face COMBAT est portee, donc son masque vit sur la classe du registre
    #   (`engine/runner/abilities/blacktemplars.py::HolyDuelAbility.TARGETING_OPTIONS`). CONTRAT DE
    #   DISJONCTION, meme migration que 1048 juste au-dessus. Le ctor a ete RELU a cette occasion et
    #   la valeur qui vivait ici est CONFIRMEE champ pour champ.
    # ⚠ 1101 AttemptedPossession (preset `+0x180` = `0x4002` + flags `0x200000002` -> `0x200004002`)
    #   est SORTIE d'ici : sa face COMBAT est portee, donc son masque vit sur la classe du registre
    #   (`engine/runner/abilities/loki/attempted_possession.py::AttemptedPossessionAbility.
    #   TARGETING_OPTIONS`). CONTRAT DE DISJONCTION, meme migration que 1048/1050 ci-dessus. Le ctor
    #   a ete RELU a cette occasion et la valeur qui vivait ici est CONFIRMEE champ pour champ. (#590)
    # 1106 WarHowl : MIGRE vers `ABILITY_CLASSES` -- sa face COMBAT est desormais portee
    #   (`abilities/spacewolves.py::WarHowlAbility.TARGETING_OPTIONS`), donc le CONTRAT DE
    #   DISJONCTION impose de retirer sa ligne d'ici. Le ctor a ete RELU au decompile avant
    #   migration et la valeur qui vivait ici est CONFIRMEE champ pour champ : preset `+0x280`
    #   (`isSelfCasting = 1`, `range` <- `<TargetingRange statics>+0x60` = RANGE_SELF,
    #   `forceMeleeTarget = 1` = `RangedBool.False`, `rules = 0x8004`) puis
    #   `.ctor(&opts, &preset, 0x10)` -> `rules = additionalRules | template.rules` = `0x8014` =
    #   `CasterMatchesDynamicRule | CasterHasNotMoved | CasterIsPossibleTarget`. MEME couple
    #   preset/flags que `1216 MartialExemplar` ci-dessus. C'est la SOURCE qui bouge, jamais la
    #   valeur.
    # 1183 VexillaMagnifica : MIGRE vers `ABILITY_CLASSES` (#566) -- sa face COMBAT est desormais
    #   portee (`abilities/custodes.py::VexillaMagnificaAbility.TARGETING_OPTIONS`), donc le CONTRAT
    #   DE DISJONCTION impose de retirer sa ligne d'ici. Le masque a ete RE-LU au decompile avant
    #   migration et est bit-identique a celui qui vivait ici : preset `+0x40` (`rules = 0x4000` =
    #   `TargetIsEnemy`, `isSelfCasting = 0`, `range` <- `<TargetingRange statics>+0x30` =
    #   RANGE_ADJACENT, `forceMeleeTarget = 1` = `RangedBool.False`) puis
    #   `.ctor(&opts, &preset, 0x200000000)` -> `rules = additionalRules | template.rules` =
    #   `0x200004000` = `TargetIsEnemy | TargetIsNotAnObject`. MEME couple preset/flags que
    #   `1050 HolyDuel` ci-dessus. C'est la SOURCE qui bouge, jamais la valeur.

    # @FORME PRESET-SEUL
    # --- surcharge C, PRESET SEUL : copie PURE, aucun flag ajoute -------------------------------
    # ⚠ 1129 BloodyFury etait la SEULE entree de ce bloc ; elle est SORTIE en #505, sa face COMBAT
    #   etant desormais portee (`engine/runner/abilities/worldeaters.py::BloodyFuryAbility.
    #   TARGETING_OPTIONS`) -- contrat de DISJONCTION, meme mouvement que 1019/1027/1038/1048/1068/
    #   1069/1087/1088/1152. Le ctor a ete RELU a cette occasion et la valeur qui vivait ici est
    #   CONFIRMEE champ pour champ : preset `+0x40` puis `.ctor(&opts, &preset)` a DEUX arguments
    #   (le decompile ressemble a un PRESET+FLAGS dont le litteral aurait disparu -- ce sont les
    #   xrefs entrantes de la surcharge C qui tranchent, meme piege que `1029 Drachnyen` #336),
    #   `rules = 0x4000` = `TargetIsEnemy` SEUL, `isSelfCasting = 0`, `range` = `TargetingRange
    #   statics+0x30` = RANGE_ADJACENT, `forceMeleeTarget = 1` = `RangedBool.False`.
    #   Le bloc reste ECRIT parce qu'il documente la 3e forme de ctor : son compte est 0, pas son
    #   existence. Le compte se RE-COMPTE sur la table, jamais par soustraction du chiffre ecrit.

    # @FORME STATIC-COPY
    # --- STATIC-COPY : aucun ctor appele, masque = `<preset>+0x28` du `.cctor` ------------------
    #   (5 avant #508 : 1204 `LeadingTheCharge` en est SORTIE, sa face COMBAT etant portee ; puis
    #    1191 `MartialInspiration` en #509 et 1177 `LightOfSanguinius` en #510, pour la MEME raison.
    #    Les trois tranches sont passees en parallele : le compte est RE-COMPTE PAR LE CODE APRES
    #    resolution, jamais soustrait ni repris d'un seul cote.)
    # ⚠ Ce compteur annoncait **16** sur `origin/master` pour **7** entrees reelles (mesure #502 au
    #   rebase) : il n'est garde par AUCUN test, donc il derive en silence a chaque migration. Il
    #   compte les entrees EXECUTABLES du bloc -- les lignes `⚠ ... est SORTIE d'ici` sont des
    #   TOMBES, elles ne comptent pas. Re-derive plutot que decremente.
    # ⚠ 1027 PsychicMaelstrom (preset `+0x180`) est SORTIE d'ici en #490 -- comme 1088 en #487,
    #   1069 en #491, 1048 en #489 et 1068 en #497 : sa face COMBAT est desormais portee, donc son
    #   masque vit sur la classe du registre
    #   (`abilities/loki/psychic_maelstrom.py::PsychicMaelstromAbility.TARGETING_OPTIONS`). Le
    #   masque n'a PAS bouge (rules 0x4002, RANGE_FROM_CONFIG, forceMeleeTarget 1) -- c'est la
    #   SOURCE qui change, et le contrat de disjonction impose de retirer la ligne d'ici.
    # ⚠ 1063 FireAndReposition (preset `+0x00`) est SORTIE d'ici en #567, MEME migration que 1064 :
    #   sa face COMBAT est portee (`engine/runner/abilities/aeldari.py::FireAndRepositionAbility`),
    #   donc son masque vit sur la classe du registre. Le ctor a ete RELU a cette occasion et il
    #   CONCORDE champ pour champ avec ce que cette entree portait : preset `<statics>+0x00`,
    #   `+0x28 = 0x4002`, `+0x20 = 2` (`RangedBool.IfRangedCaster` -- elle etait bien la SEULE du
    #   lot dans ce regime), `+0x08` = copie de `TargetingRange statics+0x00` =
    #   `RANGE_ADJACENT_IF_MELEE_CASTER`.
    # ⚠ 1064 Loki_SwoopingHawk (preset `+0x40`) est SORTIE d'ici en #502, MEME migration que 1068 :
    #   sa face COMBAT est portee (`engine/runner/abilities/aeldari.py::SwoopingHawkAbility`), donc
    #   son masque vit sur la classe du registre. Le ctor a ete RELU a cette occasion -- il n'a
    #   aucun corps propre (`return DiveAttackAbilityBase$$.ctor(this);`), c'est la BASE qui recopie
    #   le preset -- et il CONCORDE champ pour champ avec ce que cette entree portait :
    #   `*(statics+0x68) = 0x4000` = `TargetIsEnemy` SEUL, `+0x60 = 1` = `RangedBool.False`,
    #   range = `<TargetingRange statics+0x30>` = RANGE_ADJACENT.
    # ⚠ 1068 SilentDeath (preset `+0x40`) est SORTIE d'ici en #497, MEME migration que 1069 ci-dessous :
    #   sa face COMBAT est portee (`engine/runner/abilities/aeldari.py::SilentDeathAbility`), donc son
    #   masque vit sur la classe du registre. Le ctor a ete RELU a cette occasion et il CONCORDE, champ
    #   pour champ, avec ce que cette entree portait -- `*(statics+0x68) = 0x4000` = `TargetIsEnemy`
    #   SEUL, `+0x60 = 1` = `RangedBool.False`, range = `<TargetingRange statics+0x30>` = RANGE_ADJACENT.
    #   Deux lectures independantes du meme ctor, meme resultat.
    # ⚠ 1069 SeekerMissileFrequencyLock (preset `+0x180`) est SORTIE d'ici en #491 : sa face COMBAT
    #   est desormais portee, donc son masque vit sur la classe du registre
    #   (`engine/runner/abilities/tau.py::SeekerMissileFrequencyLockAbility.TARGETING_OPTIONS`).
    #   Meme migration que 1100 `SorcerousFacade` ci-dessus -- c'est le CONTRAT de disjonction.
    # ⚠ 1088 HellfyreMissileRack (preset `+0x140`) est SORTIE d'ici en #487, pour la MEME raison :
    #   son masque vit desormais sur
    #   `engine/runner/abilities/thousandsons.py::HellfyreMissileRackAbility.TARGETING_OPTIONS`.
    #   Valeurs inchangees par la migration : `0x4002` (`<TargetingOptions statics>+0x140`, lu a
    #   `<preset>+0x28`), `forceMeleeTarget = 0 = RangedBool.True`, `range = RANGE_FROM_CONFIG`.
    #   ⚠ Elle partageait le masque de 1027/1069 mais PAS leur preset : `forceMeleeTarget` vaut 0
    #   ici contre 1 chez eux -- ne jamais generaliser un masque d'une voisine de ce bloc.
    # ⚠ 1132 KillMaimBurn (preset `+0x40`) est SORTIE d'ici en #504, sa face COMBAT etant desormais
    #   portee : son masque vit sur `engine/runner/abilities/worldeaters.py::KillMaimBurnAbility.
    #   TARGETING_OPTIONS`. Valeurs INCHANGEES par la migration : `0x4000` (`TargetIsEnemy`, lu a
    #   `<preset>+0x28`), `self_cast = False`, `range = RANGE_ADJACENT`,
    #   `force_melee_target = RANGED_BOOL_FALSE`. C'est le CONTRAT de disjonction.
    # ⚠ 1165 MightFromBelow (preset `+0x40`) est SORTIE d'ici en #501, pour la MEME raison que 1027,
    #   1048, 1069 et 1088 : sa face COMBAT est desormais portee, donc son masque vit sur la classe
    #   du registre (`abilities/loki/might_from_below.py::MightFromBelowAbility.TARGETING_OPTIONS`).
    #   Valeurs inchangees par la migration : `rules = 0x4000` (`<TargetingOptions statics>+0x40`,
    #   lu a `<preset>+0x28`), `isSelfCasting = 0`, `range = RANGE_ADJACENT`,
    #   `forceMeleeTarget = 1 = RangedBool.False`. C'est le CONTRAT DE DISJONCTION : porter la face
    #   COMBAT d'une entree d'ici EXIGE d'en retirer la ligne, sinon
    #   `test_targeting_options_sources` rougit -- et `probe_181` reste VERT tout du long.
    # ⚠ 1177 LightOfSanguinius (`...Active.LightOfSanguiniusAbility$$.ctor`, hors namespace `Loki`,
    #   preset `+0x240`) est SORTIE d'ici en #510, pour la MEME raison que 1027, 1048, 1069, 1088,
    #   1132, 1141 et 1165 : sa face COMBAT est desormais portee, donc son masque vit sur la classe
    #   du registre (`abilities/bloodangels.py::LightOfSanguiniusAbility.TARGETING_OPTIONS`). Le
    #   `.cctor` a ete RELU a cette occasion et la valeur est CONFIRMEE champ pour champ :
    #   `*(statics + 0x268) = 0x102004032`, `isSelfCasting = 0` (`+0x240`), `range` =
    #   `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD, `forceMeleeTarget = 1` (`+0x260`).
    #   C'est la SOURCE qui bouge, jamais la valeur.
    # ⚠ 1191 MartialInspiration (preset `+0x40`) est SORTIE d'ici en #509, MEME migration que 1132,
    #   1165, 1064 et 1068 : sa face COMBAT est desormais portee, donc son masque vit sur la classe
    #   du registre (`engine/runner/abilities/custodes.py::MartialInspirationAbility.
    #   TARGETING_OPTIONS`). Valeurs INCHANGEES par la migration : `rules = 0x4000` (`TargetIsEnemy`
    #   SEUL, lu a `<preset>+0x28`), `isSelfCasting = 0`, `range = RANGE_ADJACENT`,
    #   `forceMeleeTarget = 1 = RangedBool.False`. Le ctor a ete RELU a cette occasion (forme
    #   STATIC-COPY : aucun `TargetingOptions$$.ctor`, recopie des 0x40 octets du preset puis
    #   `AActiveAbility..ctor(this, &opts, 0)`) et il CONCORDE champ pour champ.
    # ⚠⚠ #509 et #510 se sont croisees SUR CES DEUX LIGNES : chacune ne retirait QUE son id. Un
    #   `--ours`/`--theirs` aurait RESSUSCITE l'entree de l'autre, en laissant le test de disjonction
    #   VERT de chaque cote pris isolement. La resolution est l'UNION des retraits.
    # ⚠ 1195 TalonsOfTheEmperor (preset `+0x40`, le MEME que 1191 ci-dessus) est SORTIE d'ici en
    #   #521, MEME migration : sa face COMBAT est desormais portee, donc son masque vit sur la
    #   classe du registre (`engine/runner/abilities/custodes.py::TalonsOfTheEmperorAbility.
    #   TARGETING_OPTIONS`). Valeurs INCHANGEES par la migration : `rules = 0x4000`
    #   (`TargetIsEnemy` SEUL, lu a `<preset>+0x28`), `isSelfCasting = 0`, `range = RANGE_ADJACENT`,
    #   `forceMeleeTarget = 1 = RangedBool.False`. Le ctor a ete RELU (forme STATIC-COPY, aucun
    #   `TargetingOptions$$.ctor`) et il CONCORDE champ pour champ -- SAUF le 3e argument, qui vaut
    #   `2` ici contre `0` pour 1191 : le preset est partage, le litteral d'`AbilityAttackType` ne
    #   l'est pas.
    # 1204 LeadingTheCharge : RETIREE (#508) -- sa face COMBAT est portee
    #   (`runner/abilities/loki/leading_the_charge.py::LeadingTheChargeAbility`), donc son masque
    #   MIGRE sur la classe, comme l'exige le CONTRAT de disjonction. Le preset reste `+0x240`,
    #   le MEME que 1177 : ce qui separe les deux abilities est leur
    #   `GetDynamicInvalidTargetReason` (cf. `engine.services.ability_range`), pas leurs options.

    # ============================================================================================
    # LE LOT HORS POOL (#433-r4-r2-r1-r2-r2-r1-r1-r1) -- les abilities ACTIVES que le seed BC
    # expose SANS qu'aucune unite du pool `rl_duel build --list-pool` ne les porte. Elles etaient
    # le residu nomme au §8 de `case-433-r4-r2-r1-r2-r2-r1-r1`.
    #
    # ⚠ « HORS POOL » N'EST PAS « NPC-ONLY », et la fiche heritee se trompait sur ce point : la
    # ventilation des porteurs, RE-DERIVEE de `gameconfig`, donne **HUIT** abilities a porteur
    # SUMMON (confrontables en spawnant leur summoner, cf. la gate du `CLAUDE.md`), **une** MoW du
    # pool, et **une seule** reellement npc-only :
    #   1010 -> necroNpc2FlayedOne (npc SEUL)
    #   1015 -> necroNpc3Deathmark (npc) + necroSmnDeathmark (SUMMON)
    #   1044 -> templNpc2Neophyte + templNeophyte (SUMMON)
    #   1053 -> templNpc1Initiate + templInitiate (SUMMON)
    #   1080 -> ultraNpc4HeavyIntercessor + ultraSmnHeavyIntercessor (SUMMON)
    #   1108 -> eldarNpc3Harlequin + eldarSmnHarlequin (SUMMON)
    #   1144 -> tyranBiovore (**MoW du pool**) + tyranNpcMowBiovore
    #   1185 / 1186 -> tauNpc5StealthSuit + tauSmnStealthSuit (SUMMON)
    #
    # HUIT entrees ici, pas dix : `1091` est un NON-LU et `1186` est passee au registre COMBAT
    # entre-temps (voir les deux paragraphes ci-dessous). Le compte de la fiche heritee etait donc
    # PERIME au moment de le reprendre -- il se re-derive, il ne se cite pas.
    #
    # `1091 SlashingDive` N'Y EST TOUJOURS PAS, mais la RAISON A CHANGE (#507) : elle y figurait comme
    # NON-LU (aucun `SlashingDiveAbility` dans `frida/methods.tsv` ni `ghidra/functions.tsv`), et ce
    # non-lu etait le faux negatif que la table elle-meme prescrivait de ne pas croire -- le ctor
    # trivial `return DiveAttackAbilityBase$$.ctor(this);` est FUSIONNE par IL2CPP avec celui de
    # `SwoopingHawkAbility`, et ces tables sont indexees par ADRESSE. Le cran manquant, exactement
    # celui que ce paragraphe reclamait, a ete pris AU RUNTIME (RPC `resolveMethodPtr`, build
    # `rnca9r7q6c`) : `.ctor` a depth=0 a la MEME adresse d'entree que `SwoopingHawkAbility$$.ctor`,
    # et `ExecuteBehaviour` / `GetTargetTilesSelector` / `GetTargetUnitsSelector` /
    # `GetMovementBehavior` tous a depth=1 sur `DiveAttackAbilityBase` -> AUCUNE surcharge.
    # 1091 a donc rejoint le registre COMBAT (`engine/runner/abilities/thousandsons.py::
    # SlashingDiveAbility`) et son masque vit sur SA classe : l'ajouter ici violerait le contrat de
    # disjonction -- MEME raison que `1186 WallOfMirrors` ci-dessous, et non plus l'inverse.
    #
    # @FORME FLAGS-DIRECTS
    # --- FLAGS DIRECTS -- surcharge `TargetingOptions$$.ctor(this, isSelfCasting, range,
    #     forceMeleeTarget, rules, getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`,
    #     la seule des trois a 7 parametres, et la seule dont les XREFS ENTRANTES contiennent ces
    #     quatre ctors (celles des surcharges `(template, additionalRules)` et `(template)` ne les
    #     citent pas). Le litteral EST le masque : ce corps ecrit `this+0x28 <- rules`, sans `|`.
    # --------------------------------------------------------------------------------------------
    # `1010 StormOfFlensingBlades` N'EST PLUS ICI (#996) -- MEME migration que 1144/1204/1195 : sa
    #   face COMBAT est desormais portee (`engine/runner/abilities/necrons.py::
    #   StormOfFlensingBladesAbility`), donc son masque vit sur SA classe et le laisser ici romprait
    #   le contrat de disjonction. Le ctor a ete RELU par la tranche de portage --
    #   `.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x4010, 0, 0)`, forme FLAGS-DIRECTS --
    #   et il CONCORDE champ pour champ avec ce que le registre porte : `rules = 0x4010` =
    #   `CasterHasNotMoved` (0x10) | `TargetIsEnemy` (0x4000), `isSelfCasting = 0`,
    #   `range = <TargetingRange statics+0x30>` = RANGE_ADJACENT, `forceMeleeTarget = 1` =
    #   `RangedBool.False`. Deux lectures independantes, meme resultat.
    # `1144 BioMinefield` N'EST PLUS ICI (#939) -- MEME migration que 1204 et 1195 : sa face COMBAT
    #   est desormais portee (`engine/runner/abilities/loki/bio_minefield.py::BioMinefieldAbility`),
    #   donc son masque vit sur SA classe et le laisser ici romprait le contrat de disjonction.
    #   Le ctor a ete RELU par la tranche de portage -- `.ctor(&opts, 0,
    #   &<TargetingRange statics+0x48>, 1, 0x40004020, 0, 0)`, forme FLAGS-DIRECTS -- et il CONCORDE
    #   champ pour champ avec ce que le registre porte : `rules = 0x40004020` =
    #   `TargetHasFreeAdjacentTile` (0x20) | `TargetIsEnemy` (0x4000) | `AllowNullCasterTile`
    #   (0x40000000), `isSelfCasting = 0`, `range = <statics+0x48>` = RANGE_WHOLE_BOARD,
    #   `forceMeleeTarget = 1` = RangedBool.False. Deux lectures independantes, meme resultat.
    #   Le bit `AllowNullCasterTile` reste la SIGNATURE d'une MoW (une machine n'a aucune tuile, cf.
    #   `get_invalid_caster_reason` clause 4a) -- son porteur `tyranBiovore` EST une MoW du pool.
    #   `targeting_options_for(1144)` continue de rendre ce masque : elle lit les DEUX sources.
    # `1185 ForwardObservers` N'EST PLUS ICI NON PLUS (#996) : sa face COMBAT est portee
    #   (`engine/runner/abilities/tau.py::ForwardObserversAbility`) -- contrat de disjonction.
    #   Ctor RELU par la tranche : `.ctor(&opts, 0, &<TargetingRange statics+0x18>, 0,
    #   0x200004002, 0, 0)`, forme FLAGS-DIRECTS, et il CONCORDE : `TargetMatchesDynamicRule` (0x2)
    #   | `TargetIsEnemy` (0x4000) | `TargetIsNotAnObject` (0x200000000), `isSelfCasting = 0`,
    #   `range = <statics+0x18>` = RANGE_FROM_CONFIG. ⚠ `forceMeleeTarget = 0` = `RangedBool.True`,
    #   le seul du lot dans ce regime -- c'est ce champ-la qu'une recopie de voisin aurait rate.
    # `1186 WallOfMirrors` N'EST PAS ICI NON PLUS, et pour la raison INVERSE de 1091 : sa face
    # COMBAT est portee depuis (`engine.runner.abilities.loki.wall_of_mirrors`), donc son masque
    # vit dans `ABILITY_CLASSES` et l'ajouter ici violerait le contrat de disjonction. Son ctor a
    # tout de meme ete relu par cette tranche -- `.ctor(&opts, 0, &<TargetingRange statics+0x48>,
    # 1, 0x6004012, 0, 0)`, soit `TargetMatchesDynamicRule | CasterHasNotMoved | TargetIsEnemy |
    # AllowObscuredTargetByElevation | AllowObscuredTargetByWalls` sur RANGE_WHOLE_BOARD -- et il
    # CONCORDE, champ pour champ, avec ce que le registre porte. Deux lectures independantes du
    # meme ctor, meme resultat.

    # @FORME PRESET+FLAGS
    # --- PRESET + FLAGS -- surcharge `TargetingOptions$$.ctor(this, template, additionalRules)`,
    #     dont le corps fait `this+0x28 <- additionalRules | template+0x28`. Le litteral visible
    #     n'est PAS le masque. XREF ENTRANTE : `PrecisionShotAbility$$.ctor` figure bien dans la
    #     liste des appelants de CETTE adresse, et d'aucune autre.
    # --------------------------------------------------------------------------------------------
    # `1015 PrecisionShot` N'EST PLUS ICI (#996-r1-r3) -- MEME migration que 1010/1053/1144/1185 :
    #   sa face COMBAT est desormais portee (`engine/runner/abilities/necrons.py::
    #   PrecisionShotAbility`), donc son masque vit sur SA classe et le laisser ici romprait le
    #   contrat de disjonction (`test_targeting_options_sources` ROUGE pendant que `probe_181`
    #   resterait VERT -- garde d'EXISTENCE, aveugle a la DOUBLE declaration).
    #   Le ctor a ete RELU au decompile ET AU `.cctor` par la tranche de portage, et il CONCORDE
    #   champ pour champ avec la valeur qui vivait ici : recopie du preset `+0x280` puis
    #   `.ctor(&opts, &preset, 0x10)` -> `0x10 | *(statics+0x2a8) = 0x10 | 0x8004 = 0x8014` =
    #   `CasterHasNotMoved` | `CasterMatchesDynamicRule` | `CasterIsPossibleTarget` (le MEME masque
    #   effectif que 1216 MartialExemplar) ; `+0x280 isSelfCasting = 1` ; `+0x2a0 forceMeleeTarget
    #   = 1` = RangedBool.False ; `range` <- `<TargetingRange statics+0x60>` = RANGE_SELF (`.cctor`
    #   relu : `+0x60 = 1`, `+0x68 = Nullable(0)`). AUCUN bit de cible : c'est un self-cast.
    #   Sa soeur `1012 PrecisionShot_Aim` porte le MEME masque, sur SA classe elle aussi.

    # @FORME STATIC-COPY
    # --- STATIC-COPY -- aucun ctor appele : le corps recopie les 0x40 octets d'un preset et passe
    #     la struct telle quelle a `AActiveAbility$$.ctor`. Masque = `<preset>+0x28` du `.cctor`.
    # --------------------------------------------------------------------------------------------
    # ⚠ 1044 IncendiaryShells (preset `+0x140`) est SORTIE d'ici en #907, MEME migration que 1080
    #   juste en dessous : sa face COMBAT est desormais portee, donc son masque vit sur la classe du
    #   registre (`engine/runner/abilities/blacktemplars.py::IncendiaryShellsAbility.
    #   TARGETING_OPTIONS`). CONTRAT DE DISJONCTION -- laisser la ligne ici rendrait
    #   `test_targeting_options_sources` ROUGE pendant que `probe_181` reste VERT.
    #   Le ctor a ete RELU au decompile ET AU DESASSEMBLAGE avant migration, et la valeur qui vivait
    #   ici est CONFIRMEE champ pour champ : `*(statics+0x168)` = 0x4002 ; `+0x160` =
    #   `forceMeleeTarget` = **0** = `RangedBool.True` ; range = `<TargetingRange statics+0x18>` =
    #   RANGE_FROM_CONFIG. C'est le preset de 1088 HellfyreMissileRack -- meme masque que 1027/1069
    #   mais `forceMeleeTarget` DIFFERENT. Une 3e source CONCORDE, et elle est LIVE :
    #   `docs/rl/case-302-4/tile-target-population.json` -> `preset=320`, `rules=16386`.
    # 1080 HellfireShells -- MIGRE (#605) sur `runner/abilities/ultramarines.py::
    #   HellfireShellsAbility.TARGETING_OPTIONS` avec sa face COMBAT. Le masque y est RELU au
    #   decompile (meme preset `+0x140`) et il CONCORDE avec celui qui vivait ici.
    # 1053 DevoutPush -- MIGRE (#996-r1) sur `runner/abilities/blacktemplars.py::DevoutPushAbility.
    #   TARGETING_OPTIONS` avec sa face COMBAT. Le ctor a ete RELU au decompile par la tranche de
    #   portage (meme preset STATIC-COPY `+0x40`) et il CONCORDE champ pour champ avec la valeur qui
    #   vivait ici : `*(statics+0x68)` = 0x4000 = `TargetIsEnemy` SEUL ; `+0x60` = 1 =
    #   `RangedBool.False` ; range = `<TargetingRange statics+0x30>` = RANGE_ADJACENT. Meme preset
    #   que 1064/1068/1132/1165/1191/1195 -- et que `DiveAttackAbilityBase$$.ctor`.
    #   CONTRAT DE DISJONCTION -- laisser la ligne ici rendrait `test_targeting_options_sources`
    #   ROUGE pendant que `probe_181` resterait VERT (garde d'EXISTENCE, aveugle a la DOUBLE
    #   declaration -- cf. 1108 juste en dessous, qui a fait exactement cette faute).
    # 1108 KissOfDeath -- MIGRE (#940) sur `runner/abilities/aeldari.py::KissOfDeathAbility.
    #   TARGETING_OPTIONS` avec sa face COMBAT, qui a RELU le meme preset `+0x40`. La valeur qui
    #   vivait ici est CONFIRMEE champ pour champ (comparaison exercee : les deux objets sont
    #   EGAUX). CONTRAT DE DISJONCTION -- la ligne avait ete laissee ici par #940, ce qui rendait
    #   `test_512_excruciating_frequencies_offline` ROUGE sur `master` pendant que `probe_181`
    #   restait VERT : ce dernier est un garde d'EXISTENCE (chaque entree du registre A un masque),
    #   structurellement aveugle a la DOUBLE declaration.
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
    ActiveAbilityType.NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_80,
    ActiveAbilityType.Loki_NormalBossAttack: _NORMAL_ATTACK_OPTIONS_PRESET_80,
    ActiveAbilityType.BlisteringAssault_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_80,
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
    ActiveAbilityType.Loki_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.TemplarInitiateNormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.ProperKilly_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.FeederTendrils_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.OptimizedGait_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.Boltstorm_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.Wraithcannon_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.AncientFury_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.ElectroShock_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.RighteousRepugnance_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.TalonOfHorus_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    ActiveAbilityType.Fealty_NormalAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
    # --- 1076 MV71SniperDroneSquadAttack -- FACTORY NOMMEE, pas une recopie nue -------------------
    # `...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor` appelle
    # `IdunBattle.Core.Services.TargetingOptions$$CustomLokiNormalAttackOptions(&opts, extraRules)`,
    # dont le corps recopie le preset `statics+0x00` champ par champ PUIS fait
    # `opts.rules = preset.rules | extraRules`. Le `extraRules` n'est pas rendu par le decompile
    # (registre RDX perdu) -> LU AUX OCTETS au call-site : `ba 02 00 00 00` = `mov edx, 2`.
    #     0x4002 | 2 = 0x4002  -- l'argument etait deja dans le preset, le calcul le DIT.
    ActiveAbilityType.MV71SniperDroneSquadAttack: _NORMAL_ATTACK_OPTIONS_PRESET_00,
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
    ActiveAbilityType.RogalDorn_NormalAttack: TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
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
    #     portee d'arme non observable fait rendre `value = None` a `get_range`, donc aucun gate de
    #     DISTANCE (le gate d'adjacence, lui, tient -- #419-r1-tr14-r5-r2-r1-r2-r1-r1).
    ActiveAbilityType.FloatingDeath_NormalAttack: TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False, range=RANGE_ADJACENT,
                           force_melee_target=RANGED_BOOL_IF_RANGED_CASTER),
}

NORMAL_ATTACK_TARGETING_OPTIONS = NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE[
    ActiveAbilityType.Loki_NormalAttack]     # 69
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


def normal_repair_type_for(state: "State", unit_id) -> Optional[int]:
    """`IdunBattle.Entities.UnitExtensions$$GetRepairType(unit)` cote port -- le pendant REPAIR de
    `normal_attack_type_for` ci-dessus.

    Le natif lit `<ActiveAbilityComponent>+0x2c`, ecrit par la fabrique quand l'unite recoit son
    ability de REPARATION ; les deux accesseurs ne different que par le champ (`+0x28` / `+0x2c`) et
    partagent la meme garde `GetEntityType(unit) == 1 Unit` et le meme `return 0` hors-unite.

    Le champ n'est pas expose par les capteurs -- on le DERIVE des abilities REELLEMENT montees sur
    l'unite, dans cet ordre :

      1. une ability qui REDEFINIT la reparation expose un membre `<nom>_Repair` d'`ActiveAbilityType`
         (aucun sur ce build -- la branche est ecrite parce que la fabrique la prevoit, symetrique de
         `<nom>_NormalAttack`, dont 14 membres existent) ;
      2. sinon, l'ability de reparation GENERIQUE de l'unite, cherchee dans le meme substrat que le
         registre de triggers consomme (`config_active_abilities` MESUREE quand le canal
         `unitAbilityStates` a parle, sinon le kit gameconfig) ;
      3. sinon le TRAIT `Mechanic`, qui est la voie REELLE des porteurs -- et c'est ce qui rend cette
         fonction non triviale : `votanSmnEcog` a `activeAbilities = []` au gameconfig et repare
         quand meme. Une derivation par kit seul rendrait `None` sur le seul porteur qui compte.

    `None` = l'unite n'a pas d'ability de reparation -> le `Nullable` VIDE du natif, qui fait SAUTER
    l'unite dans `UnitsWithAnyValidTargetSelector$$Select`."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return None
    import gameconfig as GC
    vis = _visual_id(state, int(unit_id))
    gu = (GC.unit(vis) or {}) if vis else {}
    measured = getattr(ctx, "config_active_abilities", None)
    actives = list(measured if measured is not None else (gu.get("activeAbilities") or []))
    passives = list(getattr(ctx, "passive_abilities", None) or gu.get("passiveAbilities") or [])
    for nm in list(actives) + list(passives):
        member = getattr(ActiveAbilityType, f"{nm}_Repair", None)          # (1)
        if member is not None:
            return int(member)
    for nm in actives:                                                    # (2)
        member = getattr(ActiveAbilityType, str(nm), None)
        if member is not None and str(nm).startswith("Repair"):
            return int(member)
    # (3) `UnitTrait.Mechanic` -> l'ability generique `28 Repair`. Le trait est LU sur le meme
    # substrat que tous les autres gates de traits du port (`_unit_traits` : mesure live quand elle
    # existe, kit + grande-alliance sinon).
    if UnitTrait.Mechanic.name in (_unit_traits(state, int(unit_id)) or ()):
        return int(ActiveAbilityType.Repair)
    return None


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


def normal_attack_dynamic_invalid_target_reason(state: "State", caster_id: int, target_id,
                                                caster_tiles=None) -> int:
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
    catalogue -- mais un montage qui vide `Weapons` dans le BC seul ferait diverger natif et port.

    ⚠ **`caster_tiles` EST LE 2e ARGUMENT NATIF DU DELEGUE, ET IL EST LOAD-BEARING** (#590-r6). Le
    site d'invocation passe `d.Invoke(caster, casterTiles, cibleResolue, targetTiles)` : c'est donc
    la position INTERROGEE, pas la position reelle, qui decide de l'ADJACENCE -- donc de l'arme
    retenue par `SelectMaxRangeWeapon`, donc du refus. `None` = la position reelle (tous les
    appelants d'avant, octet pour octet). Sans ce parametre le mirror de
    `GetAllValidTargetsFromAllPossibleMovementTiles` serait livre INERTE : mesure faite, il rendait
    `[]` sur les 25 positions candidates d'un summon a 4 de MOVEMENT."""
    import gameconfig as GC
    vid = _visual_id(state, caster_id)
    if GC.unit(vid or "") is None:                 # substrat NON MESURE -> aucun refus invente
        return 0
    board = state.board
    caster_tiles = caster_tiles_of(state, caster_id, caster_tiles)   # `casterTile` du delegue
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

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id,
                                          caster_tiles=None) -> int:
        """La regle-delegue de l'attaque normale (`options+0x38`, bit `TargetMatchesDynamicRule`) --
        PORTEE depuis #419-r1-tr14-r5-r2-r1. Detail et bornes :
        `normal_attack_dynamic_invalid_target_reason`.

        `caster_tiles` (#590-r6) = le 2e argument que le site d'invocation natif passe au delegue
        (`d.Invoke(caster, casterTiles, cibleResolue, targetTiles)`). DECLARE ici -- et nulle part
        ailleurs -- parce que c'est ce porteur-la que `get_valid_targets_in_steps` interroge sur une
        position hypothetique ; les ~35 autres regles dynamiques gardent leur contrat a trois
        arguments et ne recoivent rien (cf. `_invoque_regle_dynamique`).
        ⚠ **LE RELAIS VERS LE TYPE CONCRET NE LE TRANSMET PAS**, et c'est deliberé : aucune des
        surcharges par type (une seule existe, `1076 MV71SniperDroneSquadAttack`) ne le declare
        aujourd'hui. Le transmettre a l'aveugle leverait `TypeError` ; le threading passe donc par
        `_invoque_regle_dynamique`, qui teste la signature -- residu `#590-r6-r3` si une surcharge
        de type doit un jour lire la position interrogee.

        Elle n'est CONSULTEE que si le masque du TYPE porte le bit : la cascade
        (`get_invalid_target_reason`) teste `options.has(TR.TargetMatchesDynamicRule)` avant
        d'appeler cette methode. Les 5 types a `0x4000` ne l'atteignent donc jamais -- c'est la table
        par type (#419-r1-tr14-r5-r2-r1-r2) qui DESARME, pas cette methode.

        ⚠ LE CORPS DEPEND DU **TYPE CONCRET**, PAS DE « l'attaque normale » (#287-r11-r2). Le natif
        lie `options+0x38` au slot vtable `+0x480` de **l'INSTANCE** que la fabrique a posee : un
        type d'attaque normale qui SURCHARGE `GetDynamicInvalidTargetReason` fait donc evaluer SON
        corps, pas celui d'`ALoki_NormalAttackAbility`. Mesure : un seul des 18 types de
        `NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE` est dans ce cas -- `1076
        MV71SniperDroneSquadAttack` (`tauMarksman`), dont
        `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` ne rappelle JAMAIS la
        base. Le port appliquait la regle de la base a tout le monde : sur `tauMarksman` il rendait
        `0` (l'unite a des armes) la ou le natif refuse quand `PickTile` ne trouve aucune tuile de
        spawn -- degradation PERMISSIVE, sans erreur ni crash.

        L'aiguillage est DERIVE (la classe declare-t-elle le corps ?), jamais une table a tenir :
        c'est le mirror exact du « l'instance a-t-elle surcharge le slot ». `klass.__dict__` et non
        `getattr` : `getattr` remonterait la MRO et verrait le defaut d'`ActiveAbility`, donc
        aiguillerait TOUT le monde vers un `return 0` permissif."""
        aid = normal_attack_type_for(state, caster_id)
        if aid is not None:
            # Import DIFFERE **PORTEUR** (mesure : `handler` importe les modules d'abilities, qui
            # importent ce module -- hisser fermerait le cycle). Meme foyer et meme raison que
            # `targeting_options_for` ci-dessous. Forme B : on lie le MODULE, pas le symbole.
            from . import handler                                    # noqa: PLC0415
            klass = handler.ABILITY_CLASSES.get(int(aid))
            if klass is not None and "get_dynamic_invalid_target_reason" in klass.__dict__:
                return int(_invoque_regle_dynamique(klass(), state, caster_id, target_id,
                                                    caster_tiles) or 0)
        return normal_attack_dynamic_invalid_target_reason(state, caster_id, target_id,
                                                           caster_tiles)

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        """Pendant CASTER (`options+0x30`) : le preset de l'attaque normale ne pose PAS
        `CasterMatchesDynamicRule`, donc cette regle n'est de toute facon jamais consultee."""
        return 0


# ------------------------------------------------------------------------------------------------
# REGLES DYNAMIQUES DE CIBLE des abilities dont la BEHAVIOUR n'est pas portee (#287-r4-r1)
# ------------------------------------------------------------------------------------------------
# OU VIT LA REGLE, COTE NATIF. Le corps est le slot de vtable `+0x480` de la SOUS-CLASSE d'ability
# (`<X>Ability$$GetDynamicInvalidTargetReason`), qu'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`
# publie en delegue a `options+0x38` et que la surcharge 7 arguments de
# `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` invoque SANS GARDE sous le bit
# `TargetingRule.TargetMatchesDynamicRule`.
#
# OU ELLE VIT COTE PORT. Une ability dont la behaviour EST portee ecrit sa regle en SURCHARGE dans sa
# classe (`WaaaghAbility`, `SquigMineAbility`, ...) : c'est le mirror 1:1 naturel. Une ability SANS
# classe n'a pas de sous-classe ou l'ecrire -- sa regle vit donc ICI, indexee par `ActiveAbilityType`,
# exactement comme son MASQUE vit dans `TARGETING_OPTIONS_UNPORTED`. Les deux tables sont le meme
# objet natif vu par ses deux champs (`options+0x28` = les regles, `options+0x38` = le delegue).
#
# ⚠ UNE ABSENCE N'EST PAS UN « LE NATIF NE REFUSE RIEN ». C'est « le port n'a pas porte CE corps ».
# La degradation reste `0` (permissive -- cf. le bloc DEGRADATION de `UnportedAbilityTargeting`), et
# chaque corps natif NON porte est RECENSE avec son symbole dans
# `docs/rl/case-287r4r1-regles-dynamiques-de-ciblage.md` (residu ouvert #287-r5). Une entree de cette
# table est un mirror 1:1 d'UN corps natif NOMME, jamais une regle deduite d'un nom d'ability.
#
# ⚠ ELLE EST VIDE AUJOURD'HUI, ET CE N'EST PAS DU DEAD CODE (#1015). Les huit regles qui y ont vecu
# ont toutes MIGRE en surcharge a mesure que leur behaviour etait portee (#488/#500/#508/#510/#512/
# #576/#577, puis 1185 par #996). Le canal reste le POINT D'ACCUEIL de la voie NON portee : les 33
# ids qui posent le bit sans regle evaluable (residu #287-r5) y entreront des que leur corps sera
# mirrore sans que leur classe le soit. Ce que les gardes exigent n'est donc PAS que cette table
# soit PEUPLEE -- un tel critere expire par le travail accompli, et c'est exactement ce qui a rendu
# `master` rouge -- mais que le cablage soit ARME : `UnportedAbilityTargeting` lit ce qu'on y met, et
# un porteur construit pour un AUTRE id n'en herite pas. Cela se garde a table vide, par une entree
# TEMOIN injectee le temps du test (`test_287r4r1_dynamic_target_rules_offline`).

def _dynamic_rule_adaptive_strategy(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason`
    (1005, `necroWarden`) -- MIRROR du decompile, qui tient en une ligne :

        return UnitExtensions.HasTrait(target, 0x10) ? 2 : 0;   // 0x10 = UnitTrait.Hero
                                                               // 2    = TargetMatchesDynamicRule

    SEMANTIQUE, avec le masque `0x402` (`TargetMatchesDynamicRule | TargetIsFriendly`) : la cible doit
    etre un ALLIE **qui n'est pas un heros**. En bataille de lineup -- ou toute unite deployee porte
    `Hero` -- la regle refuse donc TOUTES les cibles, et l'unite se retrouve sans action : c'est
    exactement la divergence mesuree (`C1_02`/seed 28704, `necroWarden` : natif `targetReason =
    TargetMatchesDynamicRule` + `UnitFlag.NoActionAvailable` POSE ; port `0`, flag absent).

    ⚠ `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)` =
    `GetBaseUnitComponent(unit)?.HasTrait(trait) ?? false` : il lit le composant de l'entite CIBLE
    ELLE-MEME et ne resout PAS une tuile en son occupant. Le mirror est donc `_unit_traits(state,
    target)` -- surtout PAS `unit_of_entity`, qui est le mirror de `GetUnit` et que
    `has_steppable_unit` consomme, lui, precisement parce que SON argument natif y transite.

    Cible non resolue (`None`) -> `0` : le natif appelle `HasTrait(null)`, dont
    `GetBaseUnitComponent(null)` rend null, donc `false`. Ce n'est pas une degradation permissive du
    port, c'est le verdict du natif."""
    if target_id is None:
        return 0
    if state.get_entity(int(target_id)) is None:
        return 0
    return (int(TR.TargetMatchesDynamicRule)
            if UnitTrait.Hero.name in (_unit_traits(state, int(target_id)) or ()) else 0)


def _dynamic_rule_foul_infusion(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$GetDynamicInvalidTargetReason`
    (1038, `deathPutrifier`) -- MIRROR du decompile. Le natif est le MIROIR EXACT d'AdaptiveStrategy
    ci-dessus, trait et sens de test changes :

        return UnitExtensions.HasTrait(target, 0x7ea) ? 0 : 2;  // 0x7ea = UnitTrait.Chaos
                                                               // 2     = TargetMatchesDynamicRule

    SEMANTIQUE, avec le masque `0x482` (`TargetMatchesDynamicRule | AddCaster | TargetIsFriendly`) :
    la cible doit etre un allie **de la grande alliance Chaos**. `Chaos` (2026) est un pseudo-trait
    d'ALLIANCE, absent des `traits` gameconfig d'une unite -- il n'existe que dans le substrat
    d'entite (`entity_trait_names`), que `_unit_traits` lit deja (#264). Le lire par le kit seul
    rendrait la regle constamment refusante.

    Cible non resolue -> `0` (`HasTrait(null)` = `false` ferait rendre `2` au natif, MAIS la cascade
    n'atteint cette regle que sur une cible enumeree, donc resolue ; on ne fabrique pas un refus sur
    un substrat que le port n'a pas mesure -- convention permissive du module)."""
    if target_id is None:
        return 0
    if state.get_entity(int(target_id)) is None:
        return 0
    return (0 if UnitTrait.Chaos.name in (_unit_traits(state, int(target_id)) or ())
            else int(TR.TargetMatchesDynamicRule))


def _dynamic_rule_forward_observers(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$GetDynamicInvalidTargetReason`
    (1185, `tauNpc5StealthSuit` / `tauSmnStealthSuit`) -- MIRROR du decompile, qui tient en deux
    lignes :

        if (target != null && EntityExtensions.HasEffect(target, state, 0x462, onlyActive: false))
            return 2;                            // 0x462 = EffectType.Markerlight
        return <corps de base>;                  // 2     = TargetingRule.TargetMatchesDynamicRule

    ⚠ LE `return` DE QUEUE EST LE CORPS DE BASE, ET C'EST LA QU'ON LE LIT. Le natif appelle
    explicitement `AActiveAbility$$GetDynamicInvalidTargetReason` -- que Ghidra mislabelle
    `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` (IL2CPP deduplique les corps triviaux
    et n'attribue qu'UN proprietaire). Ce corps decompile en `return 0`. C'est le SEUL call-site qui
    NOMME ce corps, et il vaut bien au-dela de 1185 : il etablit ce que rend le delegue des ids dont
    la classe ne surcharge pas -- cf. `probe_287r5_etages_bloquants.py`.

    SEMANTIQUE, avec le masque `0x200004002`
    (`TargetMatchesDynamicRule | TargetIsEnemy | TargetIsNotAnObject`) : on ne re-marque pas une
    cible qui porte DEJA `Markerlight`. Une seconde pose serait sans effet -- le natif l'interdit au
    CIBLAGE, pas a l'execution.

    `onlyActive` vaut `0` a ce call-site, exactement comme celui de `SquigMineAbility` : le mirror
    est donc `has_effect_of_type` (`EffectsState.has_effect`, qui ne filtre que `consumed`), et
    surtout pas `active_effects`.

    Cible non resolue -> `0` : le natif teste `target != null` AVANT le `HasEffect`, donc c'est son
    propre verdict, pas une degradation du port."""
    if target_id is None:
        return 0
    if state.get_entity(int(target_id)) is None:
        return 0
    return (int(TR.TargetMatchesDynamicRule)
            if has_effect_of_type(state, int(target_id), int(EffectType.Markerlight)) else 0)


def _dynamic_rule_light_of_sanguinius(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$GetDynamicInvalidTargetReason`
    (1177, `bloodDante`) -- MIRROR du decompile, avec son lambda
    (`...LightOfSanguiniusAbility.u003Cu003Ec__DisplayClass2_0$$u003CGetDynamicInvalidTargetReasonu003Eb__0`) :

        range = Configuration.GetNumberConstant(0x16 range);
        tiles = battleQuery.GetFreeAdjacentTiles(targetTiles);       // this+0x20, slot 0x53
        if (tiles.Count == 0) return 0x20;                           // TargetHasFreeAdjacentTile
        return tiles.Any(t => battleQuery.GetDistance(t, casterTile) <= range) ? 0 : 0x20;

    ⚠ LE CODE RENDU N'EST PAS `TargetMatchesDynamicRule`. Cette regle refuse par `0x20`
    (`TargetHasFreeAdjacentTile`) -- un bit que le masque de 1177 (`0x102004032`) porte DEJA au volet
    STATIQUE. Ce n'est pas une redite : le volet statique demande « la cible a-t-elle une tuile
    adjacente libre ? », la regle dynamique ajoute « ET l'une d'elles est-elle a `range` du
    CASTER ? ». Un port qui n'aurait retenu que le bit 0x2 aurait donc rate cette regle entierement
    -- c'est pourquoi le recensement se fait sur le BIT POSE AU MASQUE, jamais sur le code rendu.

    SEMANTIQUE (`range` = 5 au gameconfig) : Dante saute sur une tuile libre a cote de sa cible ; il
    faut donc qu'une telle tuile existe ET qu'elle soit a portee de son point de depart.

    `get_free_adjacent_tiles` est le mirror deja porte de
    `IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles`, et `get_distance` celui de
    `...$$GetDistance` (minimum sur toutes les paires de pieds -- ce qui compte pour un caster
    multi-hex). Le natif appelle la surcharge `(IEntity tuile, IList casterTiles)` : cote port,
    `[t]` contre l'empreinte COMPLETE du caster, pas sa seule MainTile.

    Cible non resolue -> `0`, et `range` absent du gameconfig -> `0` : on ne fabrique pas un refus
    sur un substrat que le port n'a pas mesure (convention permissive du module)."""
    if target_id is None or state.get_entity(int(target_id)) is None:
        return 0
    import gameconfig as GC
    raw = ((GC.ability("LightOfSanguinius") or {}).get("constants") or {}).get(
        ABILITY_CONSTANT_RANGE)
    if raw is None:
        return 0
    try:
        rng = int(raw)
    except (TypeError, ValueError):
        return 0
    tiles = get_free_adjacent_tiles(state, int(target_id))
    if not tiles:
        return int(TR.TargetHasFreeAdjacentTile)
    caster_tiles = entity_tiles(state, int(caster_id))
    for t in tiles:
        if get_distance([t], caster_tiles) <= rng:
            return 0
    return int(TR.TargetHasFreeAdjacentTile)


def is_mechanical(state: "State", unit_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsMechanical` -- MIRROR :

        return HasTrait(unit, 0x5)   || HasTrait(unit, 0x3e8) || HasTrait(unit, 0x405);
               // Mechanical=5         LivingMetal=1000         Vehicle=0x405=1029

    Les trois `GetBaseUnitComponent(unit)?.HasTrait(...)` du natif lisent l'entite ELLE-MEME (pas
    son occupant si c'est une tuile) : le mirror est `_unit_traits`, comme
    `_dynamic_rule_adaptive_strategy`. Pendant `runner/abilities/behaviours/stats.py::is_mechanical`,
    qui porte le MEME natif sur le substrat DSL (`entities.has_trait`) -- un noeud natif, deux
    substrats.

    #116-r1 -- CE SITE NE RE-ECRIT PLUS LA DISJONCTION. Il RESOUT le substrat (`State` + id -> NOMS)
    puis DELEGUE au foyer NOMS `entities/traits/unit_trait.py::is_mechanical`. Recopier les trois
    traits ici etait exactement le geste qui a produit le bug de `ChronometronExtraDamageEffect`
    (#116-e) : un seul trait teste, silencieux, ratant le camp necron. Un exemplaire de moins a
    tenir a jour si le natif ajoute un quatrieme trait.
    L'appel passe par le MODULE (`_unit_trait.is_mechanical`), pas par un nom importe : c'est la
    forme qui MORD au `monkeypatch` du foyer (cf. la doctrine des trois formes, `CLAUDE.md`), et
    elle evite en prime la collision avec l'homonyme local."""
    return _unit_trait.is_mechanical(_unit_traits(state, int(unit_id)))


def is_affected_by_heal_type(state: "State", unit_id, heal_type: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` -- MIRROR du decompile :

        if (GetBaseUnitComponent(unit)?.HasTrait(0x421) == true) return true;  // AffectedByHealAndRepair
        if (healType == 0 &&  IsMechanical(unit)) return false;                // HealType.NonMechanical
        if (healType == 1 && !IsMechanical(unit)) return false;                // HealType.Mechanical
        return true;                                                          // HealType.Any

    Le trait `AffectedByHealAndRepair` COURT-CIRCUITE le discriminant : une unite qui le porte est
    soignable ET reparable. C'est ce court-circuit que le nom de l'enum rend lisible -- lu comme un
    ordinal, `0` se lirait « pas de type » alors qu'il DESIGNE le heal biologique.

    Entite non resolue -> aucun trait -> `not is_mechanical` = `True` pour `NonMechanical` : c'est le
    verdict du natif (`GetBaseUnitComponent(null)` rend null, donc `HasTrait` faux partout), pas une
    degradation du port."""
    if UnitTrait.AffectedByHealAndRepair.name in (_unit_traits(state, int(unit_id)) or ()):
        return True
    if int(heal_type) == int(HealType.NonMechanical):
        return not is_mechanical(state, int(unit_id))
    if int(heal_type) == int(HealType.Mechanical):
        return is_mechanical(state, int(unit_id))
    return True


def _dynamic_rule_blood_chalice(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetDynamicInvalidTargetReason`
    (1175, `bloodSanguinary`) -- MIRROR du decompile :

        tiles = EntityExtensions.GetTiles(target, state);
        if (battleQuery.AreEntitiesAdjacent(tiles, casterTiles)          // this+0x20, slot 0x62
            && UnitExtensions.IsAffectedByHealType(target, 0))           // HealType.NonMechanical
            return 0;
        return (caster != target) ? 2 : 0;   // 2 = TargetingRule.TargetMatchesDynamicRule

    SEMANTIQUE, avec le masque `0xc02`
    (`TargetMatchesDynamicRule | TargetIsFriendly | AddCasterIfAtLeastOneTarget`) : le calice soigne
    un allie ADJACENT et NON MECANIQUE. Le `caster != target` de la queue est ce qui laisse le
    CASTER lui-meme passer sans condition -- exactement ce que `AddCasterIfAtLeastOneTarget` ajoute
    au masque : le caster est adjoint a l'ensemble des cibles, et cette regle ne doit pas l'en
    sortir.

    ⚠ LA SURCHARGE D'ADJACENCE COMPTE. Le natif prend `AreEntitiesAdjacent(IList, IList)` -- deux
    EMPREINTES, pas deux MainTiles -- dont le port a deja le mirror `are_entities_adjacent`, qui
    delegue a `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` : vrai des
    qu'UNE paire de pieds est adjacente (meme tuile incluse + gate d'elevation). Sur une unite
    multi-hex, la MainTile seule rendrait un verdict FAUX.

    Cible non resolue -> `0` : le natif y rendrait `2` (`caster != null`), mais la cascade n'atteint
    cette regle que sur une cible enumeree, donc resolue -- meme convention que `_dynamic_rule_foul_infusion`.
    Board absent -> `0` : on ne fabrique pas un refus sur un substrat non mesure."""
    if target_id is None or state.get_entity(int(target_id)) is None:
        return 0
    if state.board is None:
        return 0
    adjacent = are_entities_adjacent(state.board, entity_tiles(state, int(target_id)),
                                     entity_tiles(state, int(caster_id)))
    if adjacent and is_affected_by_heal_type(state, int(target_id),
                                             int(HealType.NonMechanical)):
        return 0
    return 0 if int(caster_id) == int(target_id) else int(TR.TargetMatchesDynamicRule)


def _dynamic_rule_exemplar_of_the_kauyon(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`
    (1087, `tauShadowsun`) -- MIRROR du decompile, avec son lambda
    (`...ExemplarOfTheKauyonAbility.u003Cu003Ec__DisplayClass2_0$$u003CGetDynamicInvalidTargetReasonu003Eb__0`
    = `UnitExtensions.IsEnemy(unit, closure.caster, ability.state)`) :

        if (!TileExtensions.IsFreeTile(target, state, allowSteppable: true,
                                       allowTemporaryTile: false, allowAnyUnit: false))
            return 2;                                          // TargetMatchesDynamicRule
        units = battleQuery.GetAdjacentUnits(target, friendsOf: null, enemiesOf: null,
                                             ignoreSteppables: false);      // slot 122
        units.Remove(caster);                                  // ICollection<T> slot 6
        units.RemoveAll(u => UnitExtensions.IsEnemy(u, caster, state));
        return units.Count() == 0 ? 2 : 0;                     // ICollection<T> slot 0

    SEMANTIQUE, avec le masque `0x6001042`
    (`TargetMatchesDynamicRule | TargetIsTile | TargetTileIsFree | AllowObscuredTargetByElevation
    | AllowObscuredTargetByWalls`) : Shadowsun disparait et REAPPARAIT sur une tuile libre
    « adjacent to an allied unit ». Le `RemoveAll` retire les ENNEMIS -- ce qui reste, et qu'on
    exige non vide, ce sont les unites NON ennemies adjacentes. Le sens du filtre est donc INVERSE
    de sa lecture naive (« il faut un ennemi adjacent ») : c'est `RemoveAll`, pas un `Where`.

    ⚠ LE `Remove(caster)` EST UN TERME A PART ENTIERE, ET IL A ETE TROUVE PAR LA MESURE LIVE.
    `IsEnemy(caster, caster)` est FAUX, donc le `RemoveAll` ne retire PAS le caster : sans ce
    premier retrait, une tuile dont le SEUL voisin est Shadowsun elle-meme passerait. C'est
    exactement le SOUS-REFUS mesure sur `MC1_67` (natif `0x2`, port `0` ; le diagnostic par etage
    imprimait `GetAdjacentUnits=[u<caster>(ami)]`). Il est logique : l'ability TELEPORTE Shadowsun,
    donc elle ne peut pas etre son propre voisin a l'arrivee.
    ⚠ ET IL N'ETAIT PAS LISIBLE AU PREMIER PASSAGE : Ghidra rend l'appel `FUN_180003c00(6, <MI>,
    liste, caster)`, un invoke d'interface generique sans nom. Le `6` est le slot `Remove` d'
    `ICollection<T>` (`get_Count` 0, `get_IsReadOnly` 1, `Add` 2, `Clear` 3, `Contains` 4, `CopyTo`
    5, `Remove` 6), et ce qui l'ETABLIT sans le deviner est un second call-site du MEME motif dont
    le nom dit ce qu'il fait :
    `idun.Idun.Source.IdunMeta.View.Hud.Screens.GuildProjects.GuildProjectWidget$$HandleCheatRemoveTapped`,
    dont le corps ENTIER est ce seul appel. Le `Count` de queue est le slot 0 de la meme interface.

    ⚠ LE PREMIER TERME EST UNE REDITE DU VOLET STATIQUE, ET IL EST INERTE ICI.
    `TileExtensions$$IsFreeTile(tile, state, allowSteppable, allowTemporaryTile, allowAnyUnit)` a
    le MEME CORPS que `TileExtensions$$CanAddUnit(tile, state, allowSteppable, ignoreReserved,
    ignoreContent)` -- lu, pas suppose : memes quatre rejets dans le meme ordre (composant tuile,
    Blocker `+0x40/+0x10`, `Position.NotWalkable +0x40`, contenu vide-ou-`Steppable` 0x1b), meme
    sortie de queue `Position+0x2c == 0` sous le flag. Les deux triplets coincident ici
    (`allowSteppable=1, allowTemporaryTile=0, allowAnyUnit=0` == `(1, 0, 0)`), donc ce terme
    demande EXACTEMENT ce que le bit `TargetTileIsFree` du masque a deja demande en amont dans la
    cascade : une tuile qui le romprait n'atteint jamais la regle dynamique. Il est porte quand
    meme (le natif l'ecrit) mais ne peut pas mordre -- le seul terme DISCRIMINANT de 1087 est
    l'ALLIE ADJACENT.

    `tile_can_add_unit` est le mirror deja porte de ce corps pour ce triplet ; on ne re-ecrit pas
    un second exemplaire sous l'autre nom.

    Cible non resolue -> `0` : le natif y rendrait `2` (`IsFreeTile(null)` est faux), mais la
    cascade n'atteint cette regle que sur une cible enumeree, donc resolue -- meme convention que
    `_dynamic_rule_blood_chalice`. Board absent -> `0` : on ne fabrique pas un refus sur un substrat
    non mesure."""
    if target_id is None:
        return 0
    board = state.board
    if board is None:
        return 0
    tiles = entity_tiles(state, int(target_id))
    if not tiles:
        return 0
    if not tile_can_add_unit(state, tiles[0]):
        return int(TR.TargetMatchesDynamicRule)
    units = get_adjacent_units(state, int(target_id))
    # `units.Remove(caster)` puis `RemoveAll(u => IsEnemy(u, caster, state))` -- ce qui RESTE est
    # un allie adjacent AUTRE que le caster.
    restants = [u for u in units
                if u.id != int(caster_id) and not units_are_enemies(state, int(caster_id), u.id)]
    return 0 if len(restants) > 0 else int(TR.TargetMatchesDynamicRule)


def charge_tiles_count(state: "State", caster_id: int, target_id, ability_id: str,
                       ignore_flags: bool) -> Optional[int]:
    """`<X>Ability$$GetPossibleMove[ment]Tiles` -> `ITargetsSelector` slot 2 `Count`/1, le corps
    PARTAGE par les regles dynamiques « tuiles de mouvement du caster » (#287-r5-r1).

    L'ARBRE natif, identique aux deux call-sites qui l'empruntent :

        DSLSelectors$$TilesUnitCanMoveToChargeTarget( caster@0x48, casterTiles@0x50, target@0x78,
                                                      <formule>(GetNumberConstant(0x16 range)),
                                                      ignoreFlags )
        = CanAddUnit(AdjacentTiles(target))  op_BitwiseAnd  MovableTilesInRange(caster, casterTile,
                                                                                range, ignoreFlags,
                                                                                ignoreUnitsOnTiles=0)

    `IdunBattleLogic.Entities.DSLFormulas$$Direct` (VigilanceEternal) et `$$Get` (LeadingTheCharge)
    ont le MEME corps -- les deux allouent la meme classe de formule et l'initialisent par
    `(amount, 0)`. La difference de nom ne porte donc AUCUNE difference de valeur ; c'est LU, pas
    suppose.

    ⚠ CE N'EST PAS UN COLLAPSE IMPERATIF : on evalue l'ARBRE DSL
    (`tiles_unit_can_move_to_charge_target`, mirror 1:1 deja porte), exactement comme
    `WaaaghAbility.get_dynamic_invalid_target_reason`. `Count(entities)` = `Select(entities).Count`
    (`IdunBattle.DSL.TargetsSelector$$Count`, qui appelle le vslot `Select` puis
    `ICollection.get_Count`) et, le selecteur etant `ReturnsOnlyTiles`, il coincide avec le
    `SelectTiles(entities).Count` qu'emprunte VigilanceEternal.

    `None` = SUBSTRAT ABSENT (cible non resolue, `constants.range` illisible) -- l'appelant rend
    alors `0`, la degradation permissive du module ; jamais un refus fabrique."""
    from .behaviours.context import entities_from_state
    import gameconfig as GC
    if target_id is None or state.get_entity(int(target_id)) is None:
        return None
    raw = ((GC.ability(ability_id) or {}).get("constants") or {}).get(ABILITY_CONSTANT_RANGE)
    if raw is None:
        return None
    try:
        rng = int(raw)                                  # GetNumberConstant(0x16 = range)
    except (TypeError, ValueError):
        return None
    # `MovableTilesInRangeSelector$$Select` resout son `unitTileSelector` (+0x28) par
    # `TargetsSelector$$SelectTile` -- UNE tuile de depart, pas l'empreinte (#459).
    sel = tiles_unit_can_move_to_charge_target(Caster(), SelectTile(CasterTile()), Target(),
                                               Const(rng), ignore_flags=ignore_flags)
    return len(sel.evaluate(entities_from_state(state, int(caster_id), int(target_id))))


def _dynamic_rule_leading_the_charge(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$GetDynamicInvalidTargetReason`
    (1204, `bloodDante` MoW `mowDreadnought`) -- MIRROR du decompile, qui tient en deux lignes :

        ents = AbilityEntities(caster, caster, target, caster, ..., casterTiles, ..., targetTiles, ...)
        return LeadingTheChargeAbility$$GetPossibleMoveTiles().<slot 2 Count/1>(ents) > 0
               ? 0 : 0x8000000;                          // TargetingRule.TargetIsInRange

    `GetPossibleMoveTiles` = `TilesUnitCanMoveToChargeTarget(caster@0x48, casterTiles@0x50,
    target@0x78, Get(GetNumberConstant(0x16 range)), ignoreFlags = 0)` -- l'octet `ignoreFlags` est
    NUL au call-site (`in_stack << 8`), CONTRASTE avec VigilanceEternal qui passe 1.

    SEMANTIQUE, avec le masque `0x102004032` : Dante charge sa cible, donc il faut qu'une tuile
    LIBRE adjacente a la cible soit atteignable en <= `range` pas. `TargetIsNotAdjacent` (0x100000000)
    du volet STATIQUE ecarte deja la cible au contact ; cette regle-ci exige la CHARGEABILITE.

    ⚠ AUCUN court-circuit d'adjacence, a la difference de VigilanceEternal : le natif appelle le
    selecteur inconditionnellement. Les deux regles ne sont donc PAS interchangeables, alors qu'elles
    partagent le meme etage.

    Cible non resolue / `range` illisible -> `0` : on ne fabrique pas un refus sur un substrat que le
    port n'a pas mesure (convention permissive du module)."""
    n = charge_tiles_count(state, caster_id, target_id, "LeadingTheCharge", ignore_flags=False)
    if n is None:
        return 0
    return 0 if n > 0 else int(TR.TargetIsInRange)


def excruciating_frequencies_affected_tiles(n_tiles) -> SortReverse:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles`
    -- LE foyer, MIRROR 1:1 du decompile :

        SortReverse( TilesBehindInLine( from      = CasterTile@0x50,
                                        direction = TargetTile@0x78,
                                        settings{+0x10 = 1, +0x11 = 1},
                                        maxAmount = Direct(GetNumberConstant(0x17 nrOfTiles)) ) )

    UN SEUL exemplaire pour les DEUX faces de 1197 : la regle dynamique de ciblage ci-dessous
    (`Enemies(Units(GetAffectedTiles()))`, le `GetAttackTargets` natif) et l'`ExecuteBehaviour`
    (`emperorschildren.excruciating_frequencies_tree`), qui l'appelle DEUX fois -- une pour le
    `Count` de toutes les unites de la ligne, une pour les ennemis attaques. Les dupliquer en ferait
    deux geometries a maintenir.

    `settings +0x10 = 1` active `IsWalkable` **ET** le gate d'ELEVATION `|Delta elev| < 2` de
    `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` ; `+0x11 = 1` fait SUIVRE la reference le
    long de la ligne (marche pas-a-pas). La ligne S'ARRETE a la 1re tuile invalide -- c'est un
    PREFIXE, pas un filtre (#124).

    `SelectTile(...)` = le `TargetsSelector$$SelectTile` (vslot 0xc) par lequel
    `TilesBehindInLineSelector$$Select` resout ses deux extremites."""
    return SortReverse(TilesBehindInLine(SelectTile(CasterTile()), SelectTile(TargetTile()),
                                         max_count=Const(int(n_tiles)),
                                         check_walkable=True,        # settings +0x10 = 1
                                         update_reference=True))     # settings +0x11 = 1


def _dynamic_rule_excruciating_frequencies(state: "State", caster_id: int, target_id) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetDynamicInvalidTargetReason`
    (1197, `emperNoiseMarine` « Shiron ») -- MIRROR du decompile (#287-r11-r1) :

        selector = GetAttackTargets();
        entities = default(AbilityEntities);          // memset 0x128 octets
        entities.caster      = caster;                // +0x08
        entities.target      = target;                // +0x10
        entities.targetTiles = targetTiles;           // +0x38
        return selector.<slot 2 = ITargetsSelector.Count>(entities) > 0 ? 0 : 2;
        //                    ^ le SLOT D'INTERFACE, lu dans `interface_slots.tsv`. Le decompile,
        //                      lui, montre l'index 24 de la VTABLE de la classe -- une position
        //                      dans la CLASSE n'indexe RIEN (#477-r24-r1), et les melanger sur
        //                      une meme ligne est ce qui rendait le cliquet ROUGE (#477-r42).

    et les DEUX etages du selecteur, tous deux DEJA PORTES -- seul le call-site manquait :

        GetAttackTargets  = Enemies( of = Caster@0x48,
                                     Units(GetAffectedTiles(), unique: 1, selectionType: 3),
                                     selectionType: 3 )
        GetAffectedTiles  = SortReverse( TilesBehindInLine(origin    = CasterTile@0x50,
                                                           direction = TargetTile@0x78,
                                                           settings{+0x10 = 1, +0x11 = 1},
                                                           Direct(GetNumberConstant(0x17 nrOfTiles))) )

    SEMANTIQUE : Shiron vise une TUILE (masque `0x20000000042` = `TargetMatchesDynamicRule |
    TargetIsTile | AllowUntargetableTarget`) et son rayon part de lui A TRAVERS cette tuile. La
    regle exige simplement que le rayon TOUCHE au moins un ennemi -- sinon le cast serait un no-op.

    ⚠ LES TROIS SLOTS DE `DSLSelectors` SONT LUS, PAS DEDUITS.
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` alloue les selecteurs partages ; le
    couple `+0x48` / `+0x50` est identifie sans ambiguite par
    `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`, donc
    `+0x48` = **Caster** (l'ENTITE) et `+0x50` = **CasterTile** ; `+0x78` = **TargetTile**, identifie
    de meme par `DSLTriggers$$get_OwnerIsTargetTile` = `AreEqual(+0x78, +0x30)`. Les prendre pour
    des offsets de `DSLFactory` (`0x160 Caster`, `0x178 Target`) aurait interverti deux roles.

    ⚠ LE VSLOT 24 EST `Count`, ET C'EST SA SIGNATURE QUI LE DIT. Ghidra rend l'appel comme un
    dispatch virtuel anonyme sur `klass->vtable[0x18]` ; ce qui l'etablit, c'est que les SIX
    call-sites de ce meme slot dans le binaire passent tous un `AbilityEntities` par valeur et
    comparent le retour a `0`/`1` -- dont
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$GetDynamicInvalidCasterReason`,
    dont le corps entier est `Count(GetTargets(), entities) < 1 ? TargetIsInRange : 0`. Et
    `ITargetsSelector` n'expose qu'UNE methode a 1 parametre rendant un `int` : `Count` (slot 2 de
    l'interface, cf. `data/symbols/<build>/metadata/interface_slots.tsv`).

    ⚠ LA CIBLE EST UNE TUILE, ET LE ROLE `target` LA MATERIALISE -- depuis #287-r12, dans le FOYER
    `entities_from_state` lui-meme. La parade a vecu LOCALE ici (#287-r11-r1), puis dans une fonction
    specialisee `entities_with_tile_target` (#512) ; le rayon de souffle de l'elargissement a ete
    MESURE (`probe_287r12_role_target_tuile.py --rayon`) a **2** abilities -- `1017 FragBomb` et
    `1018 ValkyrieStrike`, toutes deux en NO-OP silencieux sur ce role -- et les deux ont ete
    confrontees. Il n'y a donc plus de forme specialisee, ni ici ni ailleurs.

    ⚠ ET LE CONTEXTE NATIF EST VOLONTAIREMENT PAUVRE : `casterTiles` (+0x48) reste NUL, donc
    `CasterTileSelector$$Select` retombe sur `GetTiles(entities.Caster)` -- l'empreinte COURANTE du
    caster, ce que `CasterTile()` rend deja cote port hors balayage IA. Aucun ecart.

    `nrOfTiles` illisible / cible non resolue / board absent -> `0`, la convention permissive du
    module (on ne fabrique pas un refus sur un substrat non mesure)."""
    # `entities_from_state` reste DIFFERE : `behaviours` re-importe `targeting` (cycle reel, meme
    # raison que `charge_tiles_count`). Les noeuds DSL, eux, sont HISSES au niveau module -- le
    # cliquet `probe_485_imports_differes.py` a MESURE qu'aucun cycle ne les justifie.
    from .behaviours.context import entities_from_state  # noqa: PLC0415
    import gameconfig as GC                                             # noqa: PLC0415
    if target_id is None:
        return 0
    raw = ((GC.ability(EXCRUCIATING_FREQUENCIES_ID) or {}).get("constants")
           or {}).get(ABILITY_CONSTANT_NR_OF_TILES)
    if raw is None:
        return 0                                    # `GetNumberConstant(0x17)` non mesure
    ents = entities_from_state(state, int(caster_id), int(target_id))
    if ents.target is None:
        return 0                                    # ni unite ni tuile du board -> non mesure
    # #585-r1 : les litteraux ne sont PAS dans `$$GetDynamicInvalidTargetReason` -- celui-ci ne fait
    # que DELEGUER a `...ExcruciatingFrequenciesAbility$$GetAttackTargets`, qui ecrit
    # `Units(gs, GetAffectedTiles(), unique: 1, 3)` puis `Enemies(gs, gs@0x48, ., 3)`. LUS la-bas.
    sel = Enemies(Units(excruciating_frequencies_affected_tiles(int(raw)), selection_type=SELECTION),
                  selection_type=SELECTION)
    return 0 if len(sel.evaluate(ents)) > 0 else int(TR.TargetMatchesDynamicRule)


DYNAMIC_TARGET_RULE_UNPORTED: "dict[int, object]" = {
    # 1005 AdaptiveStrategy : RETIREE (#577) -- meme forme que les cinq ci-dessous,
    # `necrons.AdaptiveStrategyAbility` SURCHARGE desormais `get_dynamic_invalid_target_reason` et
    # APPELLE `_dynamic_rule_adaptive_strategy` ci-dessus, qui reste l'UNIQUE mirror du corps natif.
    # 1185 ForwardObservers : RETIREE (#1015) -- #996 (`b061a916`) a porte sa face COMBAT et retire
    # son masque de `TARGETING_OPTIONS_UNPORTED`, mais a OUBLIE cette entree-ci : l'id se retrouvait
    # dans les DEUX canaux a la fois. L'entree etait INATTEIGNABLE et c'est MESURE -- `_porteur(1185)`
    # rend `ForwardObserversAbility` (elle a son `TARGETING_OPTIONS`), jamais `UnportedAbilityTargeting`
    # qui est le SEUL lecteur de cette table ; verdicts identiques avec et sans elle (`refuse=2`,
    # `passe=0`). `tau.ForwardObserversAbility` SURCHARGE et appelle `_dynamic_rule_forward_observers`
    # ci-dessus, qui reste l'UNIQUE mirror du corps natif.
    # 1175 BloodChalice : RETIREE (#576) -- meme forme que 1177/1087/1038, `BloodChaliceAbility`
    # SURCHARGE `get_dynamic_invalid_target_reason` et appelle `_dynamic_rule_blood_chalice`
    # ci-dessus, qui reste l'UNIQUE mirror du corps natif.
    # 1204 LeadingTheCharge : RETIREE (#508) -- meme forme, `LeadingTheChargeAbility` SURCHARGE
    # `get_dynamic_invalid_target_reason` et appelle `_dynamic_rule_leading_the_charge` ci-dessus,
    # qui reste l'UNIQUE mirror du corps natif.
    # 1087 ExemplarOfTheKauyon : RETIREE (#488) -- `ExemplarOfTheKauyonAbility` SURCHARGE
    # desormais `get_dynamic_invalid_target_reason` et appelle le corps ci-dessus.
    # 1038 FoulInfusion : RETIREE (#500) -- meme forme, `FoulInfusionAbility` SURCHARGE et appelle
    # `_dynamic_rule_foul_infusion`.
    # 1177 LightOfSanguinius : RETIREE (#510) -- meme forme, `LightOfSanguiniusAbility`
    # (`abilities/bloodangels.py`) SURCHARGE et appelle `_dynamic_rule_light_of_sanguinius`.
    # 1197 ExcruciatingFrequencies : RETIREE (#512) -- meme forme,
    # `emperorschildren.ExcruciatingFrequenciesAbility` SURCHARGE `get_dynamic_invalid_target_reason`
    # et appelle `_dynamic_rule_excruciating_frequencies` ci-dessus, qui reste l'UNIQUE mirror du
    # corps natif.
}


class UnportedAbilityTargeting:
    """Porteur MINIMAL des `TargetingOptions` d'une ability dont la BEHAVIOUR n'est pas portee
    (masque lu -> `TARGETING_OPTIONS_UNPORTED`), pour reutiliser TELLE QUELLE la cascade
    `get_invalid_target_reason`. Pendant exact de `_NormalAttackTargeting` ci-dessus, du meme
    procede, mais pour un `ActiveAbilityType` du catalogue.

    POURQUOI UNE CLASSE NOMMEE, ET PAS UN `type(...)` FABRIQUE AU SITE (#287-r4). La cascade
    consomme DEUX membres sur son argument `ability` : le masque `TARGETING_OPTIONS`, et -- sous le
    bit `TargetMatchesDynamicRule` -- la METHODE `get_dynamic_invalid_target_reason`. Un porteur qui
    n'apporte que le premier fait lever la cascade (`AttributeError`) des que le masque porte le
    bit ; c'etait le cas du type anonyme `_UnportedTargeting` fabrique par
    `operations/turnflow._has_valid_targets`, sur 18 des 65 ids qui posent ce bit.

    DEGRADATION -- NOMMEE, jamais un `getattr` defensif. Le natif a TOUJOURS un delegue quand le bit
    est pose : `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` l'ecrit a `options+0x38` (lie au
    slot vtable `+0x480`), et la surcharge 7 arguments de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` le lit sans garde -- un delegue
    NUL y fait LEVER (l'appel s'y termine par le stub de NullReferenceException), il ne degrade pas.
    Le port, lui, ne peut evaluer ce delegue que s'il en a porte le CORPS : depuis #287-r4-r1, ceux
    qui le sont vivent dans `DYNAMIC_TARGET_RULE_UNPORTED` ci-dessus (mirror 1:1 par
    `ActiveAbilityType`, pendant exact de `TARGETING_OPTIONS_UNPORTED` pour le MASQUE), et la methode
    ci-dessous les CONSULTE. A defaut d'entree, elle rend `0` = « pas de refus dynamique », la
    degradation PERMISSIVE de tout ce module (aucun refus invente) -- du meme cote que le defaut de
    `ActiveAbility.get_dynamic_invalid_target_reason` (base), qu'une sous-classe portee posant le bit
    sans surcharger recevrait aussi. Ce `0`-la reste une DETTE NOMMEE, pas une mesure : les corps
    natifs qu'il couvre sont recenses dans `docs/rl/case-287r4r1-regles-dynamiques-de-ciblage.md`
    (residu #287-r5).

    `ABILITY_ID` est la cle GAMECONFIG (une chaine, ex. `"Executioner"`), pas l'ordinal : c'est ce
    que `_ability_config_range` passe a `GC.ability(...)` pour resoudre
    `AbilityConfiguration.GetNumberConstant(range)`. `None` quand elle n'est pas resolue -> le
    volet `UseRangeFromConfig` de `set_config_values_in_targeting_options` reste inerte, ce qui est
    le comportement DEJA en place (l'ancien site posait un `int`, que `GC.ability` ne peut pas
    resoudre non plus)."""

    __slots__ = ("TARGETING_OPTIONS", "ABILITY_ID", "ABILITY_TYPE")

    def __init__(self, ability_type: int, options: "TargetingOptions",
                 ability_id: Optional[str] = None):
        self.TARGETING_OPTIONS = options
        self.ABILITY_TYPE = int(ability_type)
        self.ABILITY_ID = ability_id

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        """Regle-delegue CIBLE (`options+0x38`) -- le corps du slot vtable `+0x480` de la sous-classe
        native, quand le port l'a mirrore. Cf. le bloc DEGRADATION de la docstring de classe pour le
        `0` rendu a defaut d'entree."""
        regle = DYNAMIC_TARGET_RULE_UNPORTED.get(int(self.ABILITY_TYPE))
        if regle is None:
            return 0
        return int(regle(state, caster_id, target_id) or 0)

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        """Regle-delegue CASTER (`options+0x30`, bit `CasterMatchesDynamicRule`) : meme motif de
        non-evaluabilite que son pendant CIBLE ci-dessus."""
        return 0


def valid_normal_attack_targets(state: "State", caster_id: int, range_override=None,
                                caster_tiles=None) -> list:
    """`IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` (MIRROR du decompile) :

        unit  = SelectSingle(unitSel@+0x18)                 # le caster
        tiles = Select(unitTileSel@+0x20)                   # ses tuiles de cast
        opts  = battleQuery.<slot 0x3e>(GetNormalAttackType(unit))
        if (rangeSel@+0x28 != null) { opts.rules &= ~TargetMatchesDynamicRule ;
                                      opts.range  = CustomRange(<formule>) }
        if (ignoreRule@+0x30.HasValue)     opts.rules &= ~ignoreRule
        if (additionalRule@+0x40.HasValue) opts.rules |= additionalRule
        return targetingQuery.<slot 2>(unit, tiles, opts, false).Targets

    Les DEUX `Nullable<TargetingRule>` (`ignoreRule` / `additionalRule`) restent volontairement
    ABSENTS de la signature : aucun call-site LU ne les pose (ils sont VIDES sur les quatre lus).

    `range_override` PORTE le premier bloc, et il l'est parce qu'un call-site le POSE (#946) :
    `IdunBattle.Entities.Effects.Loki.UnwaveringSentinel_CounterAttackEffect$$GetCounterAttackCondition`
    passe `range = DSLFormulas$$Direct(AbilityConfiguration$$GetNumberConstant(cfg,
    AbilityConstantType.range))`. Le bloc natif fait DEUX choses, et le port fait les deux :

      * `opts.range = CustomRange(range)` -- `TargetingRange{only_adjacent = RangedBool.False,
        override_range = range}`, donc la portee de l'ARME est REMPLACEE. ⚠ `RangedBool.False` n'est
        PAS `IfNotRangedCaster` : l'override efface aussi le « un caster de melee ne touche que
        l'adjacence » du preset d'attaque normale. Le clamp melee subsiste par l'AUTRE voie, celle
        qui ne depend pas du preset (`get_range` force `only_adjacent` sur
        `HasEffect(ForcedInMelee)` et sur `IsTrue(ForceMeleeTarget) && ShouldApplyRangedInMelee`) --
        c'est CE second forcage qui porte le « If there is an enemy adjacent to Tyrith, the range of
        this ability is reduced to 1 » de l'i2.
      * `opts.rules &= ~TargetMatchesDynamicRule` -- la regle-delegue est DESARMEE. Cote port cela
        se lit `_NormalAttackTargeting.get_dynamic_invalid_target_reason` jamais consultee, la
        cascade testant `options.has(TR.TargetMatchesDynamicRule)` avant de l'appeler.

    `None` = pas d'override -> le comportement d'avant #946, octet pour octet (les call-sites sans
    range continuent d'appeler la meme cascade avec les memes options).

    `GetValidTargets` = enumeration du domaine puis filtre par la MEME cascade que le gate de cible
    (`get_invalid_target_reason`) -> on la reutilise TELLE QUELLE avec le masque de l'attaque
    normale, plutot que d'ecrire un 2e filtre.

    `caster_tiles` (#590-r6) -- LES TUILES DE CAST, `None` = celles du caster sur le plateau. Le
    selecteur natif passe `Select(unitTileSel@+0x20)`, donc les tuiles du caster ; mais la fonction
    qu'il appelle en dessous (`TargetingQuery$$GetValidTargets(caster, casterTiles, options,
    skipAddCasterChecks, onlySendFirst)`) prend la liste en PARAMETRE, et c'est cette voie-la qu'emprunte
    `AttackQuery$$GetValidTargetsInSteps(unit, possibleUnitTiles, abilityType)` pour interroger une
    position HYPOTHETIQUE. Le port suit : la valeur par defaut rend le comportement d'avant, octet
    pour octet, et le parametre ouvre le mirror de la branche MOBILE (`get_valid_targets_in_steps`).

    ORDRE D'ENUMERATION = celui de `state.entities` (ordre d'insertion). RESIDU NOMME : le natif
    enumere `GetPossibleTargetsForOptions` -> `GetUnitsInRange`, dont l'ordre n'est pas porte ; il
    ne tranche QU'A DISTANCE EGALE sous le `SortByDistance` + `First(1)` du seul consommateur.

    #419-r1-tr14-r5-r2-r1-r2 : les options sont celles du TYPE d'attaque normale DE CE CASTER
    (`normal_attack_targeting_options`), mirror du `battleQuery.<slot 0x3e>(GetNormalAttackType(unit))`
    que le selecteur natif fait a cette place exacte -- et non plus une constante de module."""
    opts = normal_attack_targeting_options(state, int(caster_id))
    if range_override is not None:
        # `opts.rules &= ~TargetMatchesDynamicRule ; opts.range = CustomRange(range)` -- les DEUX
        # ecritures du bloc natif, dans le meme ordre. `dataclasses.replace` parce que
        # `TargetingOptions` est `frozen` : on ne MUTE pas le preset partage du module.
        opts = replace(opts,
                       rules=int(opts.rules) & ~int(TR.TargetMatchesDynamicRule),
                       range=custom_range(int(range_override)))
    probe = _NormalAttackTargeting(opts)
    # LE VOLET CASTER, EN TETE (#447-r4). `TargetingQuery$$GetValidTargets` -- la fonction dont
    # cette boucle est le mirror -- COMMENCE par lui et sort AVANT toute enumeration :
    #     reason = GetInvalidCasterReason(caster, casterTiles, options);
    #     if (reason.IsInvalid())  return ValidTargets.Empty;      // AUCUNE cible, pas « toutes »
    # Meme etage que `runner/operations/turnflow.py` (#287-r4), qui le portait deja SEUL : trois
    # mirrors de la MEME fonction native, dont deux sautaient le volet -- c'est ce que #447-r4
    # nommait. Ici il est presque toujours INERTE (aucun masque d'attaque normale ne pose de bit
    # `Caster*`) SAUF par la clause TUILE-NULLE, qui n'est gatee par aucun bit : une unite SANS
    # tuile (`Burrowers` sous terre) n'a aucune cible d'attaque normale, et c'est le natif.
    if get_invalid_caster_reason(state, int(caster_id), probe, caster_tiles):
        return []
    out = []
    for uid in list(state.entities.keys()):
        if int(uid) == int(caster_id):
            continue
        # `apply_self_cast_switch=False` : la boucle native appelle la surcharge **7 arguments**
        # (`GetInvalidTargetReason(caster, casterTiles, t, options, onlyTiles: true, range)`), qui
        # n'a NI aiguillage self-cast NI volet caster -- c'est son APPELANTE qui porte le volet,
        # ci-dessus. Meme couple que `turnflow.py`.
        if get_invalid_target_reason(state, int(caster_id), int(uid), probe,
                                     apply_self_cast_switch=False,
                                     caster_tiles=caster_tiles) == 0:
            out.append(int(uid))
    return out


def get_valid_targets_in_steps(state: "State", caster_id: int, positions) -> list:
    """`IdunBattle.Core.Services.AttackQuery$$GetValidTargetsInSteps(unit, possibleUnitTiles,
    abilityType)` -- MIRROR du corps de son iterateur
    `AttackQuery.u003CGetValidTargetsInStepsu003Ed__18$$MoveNext`, LU terme a terme :

        result = new ValidTargets();                                  # etat +0x40
        foreach (from in possibleUnitTiles) {                          # +0x48 = l'enumerateur
            yield return null;                                         # etat 1 -- le << InSteps >>
            other = this.GetValidTargets(unit, from, abilityType);     # la surcharge 1-POSITION
            result.Merge(other);
        }
        yield return result;                                           # etat 2

    C'est donc l'UNION, position par position, de la MEME cascade que `valid_normal_attack_targets`
    -- rien d'autre. Le `yield return null` intermediaire est le decoupage en pas de temps du
    natif (il laisse la frame respirer) : il n'a aucune contrepartie offline et n'entre dans AUCUN
    resultat, l'appelant non-`InSteps`
    (`AttackQuery$$GetValidTargets(unit, possibleUnitTiles, abilityType)`) bouclant sur `MoveNext`
    jusqu'a epuisement avant de lire l'accumulateur.

    ⚠ **CABLE SUR L'ATTAQUE NORMALE**, comme son unique consommateur porte. Le natif prend un
    `abilityType` quelconque ; le seul call-site porte
    (`AttemptedPossessionAbility$$GetPreferredAttackTarget`) y passe
    `UnitExtensions$$GetNormalAttackType(unit)`, ce que `valid_normal_attack_targets` resout deja
    par caster. La generalisation a une ability quelconque demanderait de propager `caster_tiles`
    dans `valid_targets_for` : residu, pas un port speculatif.

    ORDRE : `ValidTargets$$Merge` accumule dans un `OrderedSet`, donc premiere apparition d'abord et
    doublons ignores -- ce que la deduplication ci-dessous reproduit. L'ordre des POSITIONS est celui
    que l'appelant fournit.

    ⚠ NON PORTE, et c'est BORNE : `ValidTargets` transporte AUSSI une `MainTile` (le natif construit
    `new ValidTargets(mainTile, targets)` par position, et `Merge` ne garde que les cibles). Le seul
    consommateur porte ne lit que `res.<+0x10>`, la liste -- le champ `MainTile` n'entre dans aucun
    verdict de cette tranche."""
    out: list = []
    vus: set = set()
    for pos in (positions or ()):
        for t in valid_normal_attack_targets(state, int(caster_id), caster_tiles=pos):
            if int(t) in vus:
                continue                       # `OrderedSet.Add` -- doublon ignore
            vus.add(int(t))
            out.append(int(t))
    return out


def all_valid_targets_from_all_possible_movement_tiles(state: "State", unit_id: int) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAllValidTargetsFromAllPossibleMovementTiles(unit,
    abilityType, ignoreMovementFlag)` (slot `IBattleQuery 69`) -- MIRROR.

    Le `BattleQuery` DELEGUE au slot 5 d'`IDamagePredictionQuery`
    (`DamagePredictionQuery$$GetAllValidTargetsFromAllPossibleMovementTiles`), dont le corps est
    l'iterateur `DamagePredictionQuery.u003CGetAllValidTargetsFromAllPossibleMovementTilesInStepsu003E
    d__29$$MoveNext`, LU etat par etat :

        // etat 0
        tiles = <IMovementQuery 2 GetMovablePositionsFor>(attacker, ignoreMovementFlag, out default);
        tiles.Add(EntityExtensions.GetUnitPosition(attacker, state));      // la position COURANTE
        // etat 1
        result = <IAttackQuery 4 GetValidTargetsInSteps>(attacker, tiles, abilityType);

    Les DEUX slots sont LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`
    (`IMovementQuery 2 GetMovablePositionsFor 3` et `IAttackQuery 4 GetValidTargetsInSteps 3`),
    jamais devines : c'est l'ARITE qui les confirme (3 arguments chacun, comme les call-sites).

    L'`Add` de la position courante n'est PAS redondant avec l'union interne de
    `MovementQuery$$GetMovablePositionsFor` (`movable.AddRange(IterateTiles(unit, state))`) : sur
    une unite MULTI-HEX le regroupement en positions a N pieds peut ne pas reproduire l'empreinte
    exacte. La cible etant un `OrderedSet`, l'ajout est un no-op quand elle y est deja.

    `ignoreMovementFlag` est INERTE cote port : il desarme la garde d'entree
    `UnitFlagsComponent$$Has(unitFlags, 1)` de `MovementQuery$$FindAnyOrAllMoveableTiles`, garde qui
    n'a aucun substrat dans `services/movement_query.get_movable_tiles_for` (residu partage, deja
    nomme par `MovableTilesInRange` et par `genestealer.py`). Il n'est donc pas un parametre ici.

    PORTEE DU PATHFINDING : `options = default` cote natif, donc `overrideRange = null`, donc
    `StatComponent(Movement).CurrentValue` -- le MOVEMENT courant de l'unite, la meme grandeur que
    l'`overrideMovement` de `1101 AttemptedPossession`.

    Rend la liste des ids de cible, ou `[]` quand le substrat manque (pas de board, pas de position)
    -- aucun refus ni aucune cible inventes."""
    board = state.board
    if board is None:
        return []
    feet = entity_tiles(state, int(unit_id))
    if not feet:
        return []
    tid = board.id_at(int(feet[0][0]), int(feet[0][1]))
    if tid is None:
        return []
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return []
    move = int(sc.ctx.get_stat(int(StatType.MOVEMENT)) or 0)
    # OCCUPATION PAR EMPREINTE VIVANTE -- meme convention que les trois collapses de `genestealer.py`
    # (`_living_occupants_map`) : la valeur est l'EQUIPE de l'occupant, ce a quoi
    # `WalkPathfinder$$UnitIsBlockedByEnemyUnit` compare `moving_team`.
    occupants = {}
    for eid, ent in state.entities.items():
        uc = ent.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        team = ent.get_component(OwnerComponent)
        for t in get_unit_feet(state, int(eid)) or ():
            t_id = board.id_at(int(t[0]), int(t[1]))
            if t_id is not None:
                occupants[t_id] = None if team is None else team.team
    stop = _mq.get_movable_tiles_for(board, state, int(unit_id), int(tid), move, occupants,
                                     None if oc is None else oc.team)
    # `GetMovablePositionsFor` = le regroupement en positions a N pieds AU-DESSUS du stop-set.
    positions = _mq.get_movable_positions_for(board, state, int(unit_id),
                                              [board.coord(int(t)) for t in sorted(stop)])
    positions = [list(p) for p in positions]
    # `tiles.Add(GetUnitPosition(attacker, state))` -- la position COURANTE, en QUEUE comme le natif.
    if sorted(feet) not in [sorted(p) for p in positions]:
        positions.append(list(feet))
    return get_valid_targets_in_steps(state, int(unit_id), positions)


def has_valid_targets(state: "State", unit_id, ability_type) -> Optional[bool]:
    """`IBattleQuery.<slot 64 = 0x40> HasValidTargets(unit, position, abilityType)` -- le predicat
    « cette unite a-t-elle au moins une cible legale pour CETTE ability, depuis sa tuile ».

    Slot LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
    (`IBattleQuery 64 HasValidTargets 3`), et recoupe par ses DEUX consommateurs natifs, qui
    l'appellent par le meme `<slot 0x40>` :

      * `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector$$Select`, qui passe
        `(unit, GetUnitPosition(unit), UnitExtensions$$GetNormalAttackType(unit))` -- c'est la
        surcharge a DEUX arguments de `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithAnyValidTarget`,
        deja portee ici par `valid_normal_attack_targets` (attaque normale CABLEE) ;
      * `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select`, qui passe
        `(unit, GetUnitPosition(unit), <ability calculee par un selecteur>.Value)` -- la surcharge a
        TROIS arguments, ou l'ability est un PARAMETRE. C'est celle qu'appelle
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ECogSupportAbility$$CreateBehaviour`.

    Cette fonction est donc `valid_normal_attack_targets` GENERALISEE a une ability quelconque :
    meme cascade (`get_invalid_target_reason`), meme domaine d'enumeration, seul le masque change.
    Elle rend un BOOLEEN (le natif rend `bool`), pas la liste -- les deux appelants natifs ne
    testent que l'existence.

    TRI-ETAT, et il est LOAD-BEARING : `None` = **le masque de cette ability n'a pas ete RE-lu**
    (`targeting_options_for` rend `None`, meme convention permissive que partout dans ce module).
    Un appelant qui rabattrait ce `None` sur `False` FILTRERAIT une unite que le natif garde ; sur
    `True`, il en garderait une que le natif ecarte. Les deux sont des inventions : le consommateur
    doit DIRE qu'il ne sait pas."""
    targets = valid_targets_for(state, unit_id, ability_type)
    return None if targets is None else bool(targets)


def valid_targets_for(state: "State", unit_id, ability_type) -> Optional[list]:
    """Les cibles LEGALES de `ability_type` pour `unit_id`, depuis sa tuile courante.

    Generalisation EXACTE de `valid_normal_attack_targets` ci-dessus (dont le corps est ce meme
    balayage avec le masque de l'attaque normale du caster) : c'est le domaine que le natif enumere
    derriere `IdunBattle.Core.Services.BattleQuery$$GetValidTargets(unit, from, abilityType)` ->
    slot 6 d'`ITargetingQuery`, la MEME cascade que `get_invalid_target_reason`.

    `None` = masque non RE-lu (tri-etat, cf. `has_valid_targets`). Liste VIDE = mesure reelle
    « aucune cible »."""
    if unit_id is None or ability_type is None:
        return None
    opts = targeting_options_for(ability_type)
    if opts is None:
        return None                       # masque non RE-lu -> le port ne SAIT pas (jamais [])
    from .handler import ABILITY_CLASSES
    klass = ABILITY_CLASSES.get(int(ability_type))
    # Le porteur de masque : la classe d'ability REELLE quand elle est portee (elle apporte sa
    # `get_dynamic_invalid_target_reason`, que le bit `TargetMatchesDynamicRule` consulte), sinon le
    # porteur minimal, comme pour l'attaque normale.
    probe = klass() if klass is not None else _NormalAttackTargeting(opts)
    uid, out = int(unit_id), []
    # LE VOLET CASTER, EN TETE (#447-r4) -- cf. `valid_normal_attack_targets` ci-dessus pour le
    # VERBATIM. Ici il MORD pour de bon : ce mirror sert des abilities QUELCONQUES, dont celles qui
    # posent `CasterHasNotMoved`, `CasterMatchesDynamicRule` ou un `CasterHasNTiles`. Un caster
    # refuse rend `[]` -- une MESURE (`ValidTargets.Empty`), jamais `None` (qui veut dire
    # « masque non RE-lu », deja rendu plus haut).
    if get_invalid_caster_reason(state, uid, probe):
        return []
    for tid in list(state.entities.keys()):
        if int(tid) == uid:
            continue
        # `apply_self_cast_switch=False` : la boucle native emprunte la surcharge 7 arguments.
        if get_invalid_target_reason(state, uid, int(tid), probe,
                                     apply_self_cast_switch=False) == 0:
            out.append(int(tid))
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
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    return e is not None and e.get_component(MachineComponent) is not None


def _resolves_to_unit(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state) != null`. ⚠ Une MoW n'est PAS une
    unite pour le natif -- mais le port lui pose un `UnitComponent` (porteur d'identite, cf.
    `_load_machines`), d'ou l'exclusion EXPLICITE du `MachineComponent` ici."""
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
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    if e is None:
        return False
    return (e.get_component(UnitComponent) is not None
            or e.get_component(MachineComponent) is not None)


def units_are_friendly(state: "State", a_id, b_id) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$UnitsAreFriendly` = `battleQuery.<slot 0x90>(a, b)`
    — MEME CAMP. Offline : meme `OwnerComponent.team` (la convention d'equipe de tout le port ;
    les summons heritent de l'equipe de leur summoner, cf. project_summon_team_model)."""
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

    **`None` = branche 1 NON RESOLUE ICI, et l'appelant qui a le canal la resout**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1). Cette fonction ne recoit qu'un porteur de stats
    OPTIONNEL, donc elle ne peut pas promettre `GetStat` ; ses deux appelants tranchent
    differemment, et c'est VOULU :

      * `get_range` -- le foyer natif ou `GetStat(caster, StatType.Range = 2)` est LU -- le resout
        des que le `StatsComponent` est la. ⚠ La phrase qui vivait ici (« `StatType.Range` n'est PAS
        dans le catalogue de `combatSnapshot` ») etait **PERIMEE** : le RPC publie `stats.range` et
        son catalogue `statTypes` l'apparie a l'index **2**. MESURE : `0` sur toutes les unites
        observees, arme ou non, `statDelta` vide ;
      * `engine.runner.operations.triggers.base._max_attack_range` substitue **1** (comportement
        historique d'`IsInAttackRange`) : un `0` y fermerait l'overwatch d'une MoW. Cet arbitrage
        n'est PAS touche -- le mirror est pose chez `get_range`, pas ici, precisement pour ne pas
        le deplacer sous les pieds d'un consommateur hors perimetre.

    81 unites du gameconfig n'ont AUCUNE arme (les 22 Machines of War et les objets de decor).

    Source d'arme = gameconfig (`weapons[].Range`, absent = arme de MELEE) : c'est le meme substrat
    que `WeaponsComponent`, dont le natif tire `HasAnyWeapon` / `HasRangedWeapon` /
    `FindLongestRangedWeapon`."""
    import gameconfig as GC
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
    e = state.get_entity(int(entity_id)) if entity_id is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


def _first_tile(tiles):
    """`IdunBattle.Core.UnitPosition$$get_MainTile(casterTiles)` -- la PREMIERE tuile d'une position
    interrogee, ou `None` si la liste est vide. Meme convention que `entity_tiles(...)[0]`, qui EST
    `EntityExtensions$$GetMainTileId` (cf. `_obscuring_target_tile`)."""
    for t in (tiles or ()):
        if t is None:
            continue
        return (int(t[0]), int(t[1]))
    return None


def caster_tiles_of(state: "State", caster_id: int, caster_tiles=None) -> list:
    """`EntityExtensions$$GetTiles(caster, state)` OU la position INTERROGEE (#590-r6).

    LE FOYER UNIQUE du repli : partout ou le natif prend un parametre `casterTiles`, le port accepte
    desormais `caster_tiles=None` (« la position REELLE », le comportement de tous les appelants
    historiques, octet pour octet) ou une LISTE de tuiles `(col, row)` -- la position hypothetique
    que `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets(caster, casterTiles, options,
    skipAddCasterChecks, onlySendFirst)` recoit de son appelant.

    Ce n'est PAS une commodite : le natif ne DEPLACE jamais l'unite pour interroger une position
    candidate, il passe la liste. Simuler par un `MoveUnitOperation` reversible aurait libere la
    tuile d'origine et change l'occupation du plateau -- une divergence que le paramètre supprime
    par construction."""
    if caster_tiles is not None:
        return [(int(t[0]), int(t[1])) for t in caster_tiles if t is not None]
    return entity_tiles(state, caster_id)


def _has_forced_in_melee(state: "State", unit_id) -> bool:
    """`EntityExtensions.HasEffect(caster, state, 0x529 ForcedInMelee, activeOnly = false)` lu par
    `GetRange` juste avant le cap final. Poseur porte : le trigger de free-attack de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility` (pose puis retire dans le
    meme cast)."""
    if state.effects is None or unit_id is None:
        return False
    return bool(state.effects.has_effect(int(unit_id), effect_type=EFFECT_FORCED_IN_MELEE))


def should_apply_ranged_in_melee(state: "State", caster_id: int, caster_tiles=None) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$ShouldApplyRangedInMelee(caster, casterTiles,
    ignoreTrait)` -> `IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee`.

    `caster_tiles` (#590-r6) -- LA POSITION INTERROGEE, `None` = celle du caster sur le plateau.
    Le slot est `IAttackQuery 21 ShouldApplyRangedInMelee` (arite 3,
    `data/symbols/<build>/metadata/interface_slots.tsv`) et son 2e argument est bien `casterTiles` :
    `IdunBattle.Core.Services.TargetingQuery$$GetRange` le lui transmet VERBATIM
    (`(*puVar10)(plVar1, caster, casterTiles, 1, method)`). Le clamp melee se mesure donc depuis la
    position CANDIDATE quand on interroge une position hypothetique -- c'est ce que le mirror de
    `GetAllValidTargetsFromAllPossibleMovementTiles` exige (un summon qui s'approche entre en melee).

    `GetRange` l'appelle avec **`ignoreTrait = 1`** (litteral du call-site ; le thunk d'`AttackQuery`
    se contente de forwarder R9 et d'injecter `this.state` en 3e argument — VERIFIE a l'octet, la
    lecture Ghidra `uStack…28 = 0` designe le slot `MethodInfo*`, pas `ignoreTrait`). Le gate
    `HasTrait(0xb Ranged)` est donc COURT-CIRCUITE ici : contrairement au chemin PREDICTION
    (`CalculateRangedInMeleeReduction`, `ignoreTrait = 0`, inerte faute de porteur du trait #161),
    ce chemin-ci MORD pour tout caster. Mirror du decompile :

        if (casterTiles == null || casterTiles.Count == 0) return false;
        if (!HasTrait(caster, 0xb) && !ignoreTrait) return false;
        if (UnitExtensions.HasFlag(caster, 0x1c))          return false;
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
    Sans `state.board` on ne sait pas decider -> False (aucun clamp invente).

    LE TROISIEME GATE EST PORTE DEPUIS #287-r11-r2-r1-r2, et il etait ABSENT des DEUX mirrors.
    `HasFlag(attacker, 0x1c)` est `UnitFlag.IngoreRangedInMelee` (**typo native**, `enums.tsv` :
    `28=IngoreRangedInMelee`) -- l'ordinal ne se lit QUE dans cet espace de nommage : `0x1c` vaut
    aussi `UnitTrait.Impervious` et le bit 28 de `TargetingRule` (`CasterCanMove`), qui nomment
    autre chose. Le drapeau DISPENSE son porteur du clamp melee : sans lui le port rabattait a 1
    une portee que le natif laisse entiere -- ecart RESTRICTIF, meme direction que celui de
    #287-r11-r1-r1-r2.

    SON UNIQUE POSEUR EST CONNU, et c'est ce qui rend CE mirror-ci le seul des deux a etre
    exercable : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour`
    pose le flag SUR LE DRONE juste avant son `UseActiveAbility` et le retire juste apres
    (balayage exhaustif des deux voies d'ecriture de flag -- 25 appelants de
    `UnitFlagsComponent$$Add`, 10 de `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag`). Cette
    fonction-ci recoit le CASTER, donc elle voit le flag quand le caster EST le drone -- ce qui est
    exactement le regime de son attaque d'ouverture. (Le mirror jumeau de `mv71.py` recoit le
    `parent` : le gate y est inerte par construction.)
    Le canal existe et il est COMPLET : `combatSnapshot.units[].unitFlags` publie le resultat de
    `IdunBattle.Entities.UnitExtensions$$HasFlag` pour **chaque valeur** de l'enum lue au runtime
    (`internals.ts::unitFlagValues`), et `snapshot._load_unit_flags` seede tout ce qu'il recoit --
    donc ce gate MORD des qu'un etat charge porte le drapeau, sans capteur neuf.

    ⚠ RESIDU NOMME (#590-r6-r1, INCHANGE PAR CETTE TRANCHE) : le natif fait
    `foreach (tile in casterTiles) foreach (adj in <voisins de tile>)`, le port ne regarde que la
    MAIN TILE. Les deux coincident sur toute unite a 1 pied ; sur une multi-hex le port sous-estime
    le clamp (ecart PERMISSIF sur la portee). Le parametre `caster_tiles` ci-dessus reprend la MEME
    convention -- sa premiere tuile -- pour rester value-preservant : le corriger est une reparation
    a part entiere, pas un effet de bord de ce port-ci."""
    board = state.board
    if board is None:
        return False
    src = _tile_of(state, caster_id) if caster_tiles is None else _first_tile(caster_tiles)
    if src is None:
        return False
    src_tid = board.id_at(src[0], src[1])
    if src_tid is None:
        return False
    caster = state.get_entity(int(caster_id))
    c_owner = caster.get_component(OwnerComponent) if caster is not None else None
    if c_owner is None:
        return False
    # `if (UnitExtensions.HasFlag(attacker, 0x1c)) return false;` -- AVANT la boucle, comme le
    # natif : le drapeau court-circuite, il ne filtre pas les voisins.
    c_flags = caster.get_component(UnitFlagsComponent) if caster is not None else None
    if c_flags is not None and c_flags.has(UnitFlag.IngoreRangedInMelee):
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


def get_range(state: "State", caster_id: int, options: "TargetingOptions",
              caster_tiles=None) -> Optional[Range]:
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

    Rend **None dans un SEUL cas** : `TargetingRange` non RE-lu (l'ability n'est dans aucune des deux
    sources de masque) — la seule situation ou le port ne sait rien. Rend un `Range` a
    **`value = None`** quand seule la portee NUMERIQUE echappe au port — portee d'arme non observable
    (cf. `unit_weapon_range`) ou `OverrideRangeFunc` non resolu. Dans les deux cas l'appelant ne pose
    aucun refus DE DISTANCE, mais il garde le gate d'adjacence, qui ne lit pas la valeur
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1).

    ⚠ **LES DEUX COURT-CIRCUITS NATIFS SONT DESORMAIS MIRRORES, ils ne sont plus rabattus sur un
    `None`** (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1 et -r2). Ils rendent chacun un `Range` PARFAITEMENT
    DEFINI, et les confondre avec « non RE-lu » perdait de l'information :

      * `casterTiles` vide -> `Range(0, false, options.Range.UseWholeBoard)`. `(int)range == 0` est
        une VALEUR, pas une absence : `GetTilesInRange` y branche sur `casterTiles` (donc l'ensemble
        VIDE, puisque c'est justement lui qui l'est) et `GetInvalidTargetReason` y compare
        `GetDistance(casterTiles, target)` -- qui rend `int.MaxValue` sur une liste vide (boucle
        externe non entree, `IdunBattle.Core.Services.MovementQuery$$GetDistance` initialise a
        `0x7fffffff`) -- donc un refus `TargetIsInRange` SYSTEMATIQUE hors `UseWholeBoard` ;
      * `UseWholeBoard` -> `Range(1, false, true)` (le litteral `0x10000000001`), sans evaluer ni
        `only_adjacent` ni la portee d'arme, et AVANT les deux clamps de melee -- qui ne peuvent donc
        pas armer l'adjacence dans ce regime.

    PORTEUR du premier, RE-ETABLI et non suppose : la **MACHINE OF WAR**. `MachineFactory$$Build`
    ne lui pose aucune tuile, d'ou le bit `AllowNullCasterTile` sur ses masques. Le regime d'ECART
    (`casterTiles` vide ET `UseWholeBoard` faux) est neanmoins **VIDE, et c'est MESURE** : les
    **22/22** masques portant `AllowNullCasterTile` portent aussi `use_whole_board`, et les **22**
    unites `MachineOfWar` du gameconfig (11 hero + 11 npc) n'ont QUE ces deux actives-la -- plus
    aucune attaque normale (`MachineFactory$$Build` n'appelle jamais
    `UnitFactory$$AddNormalAttackAbility`). Le mirror est donc exact ET sans effet observable
    aujourd'hui : c'est ce qui le rend sur a poser.

    L'ORDRE compte et il est respecte : la valeur d'abord (arme -> override -> config), le delegue
    ensuite, les deux CLAMPS de melee en dernier. Un clamp applique avant l'override serait ecrase
    par lui. Et **tout chemin qui clampe force `only_adjacent`** (les deux `Math.Min(1, v)` du
    decompile sont dans le MEME bloc que `onlyAdjacent = true`) : la valeur clampee n'est donc jamais
    lue par le consommateur, ce qui rend le clamp d'un `None` sans consequence.

    `caster_tiles` (#590-r6) : la position INTERROGEE, `None` = celle du caster. Elle entre dans les
    DEUX endroits ou le natif lit `casterTiles` -- le court-circuit « liste vide » de tete et le
    `ShouldApplyRangedInMelee` de queue. Rien d'autre du corps n'en depend (la portee d'arme, les
    stats et les deux `RangedBool` lisent le CASTER, pas sa position)."""
    rng = options.range
    if rng is None:
        return None                                   # `TargetingRange` non RE-lu -> pas de gate
    uwb = bool(rng.use_whole_board)
    if (_tile_of(state, caster_id) if caster_tiles is None
            else _first_tile(caster_tiles)) is None:
        # `if (casterTiles == null || casterTiles.Count == 0)` -- le PREMIER test du corps natif,
        # AVANT le court-circuit `UseWholeBoard`. Il rend `{0, false, options.Range.UseWholeBoard}`.
        return Range(value=0, only_adjacent=False, use_whole_board=uwb)
    if uwb:
        # `if (!cap.HasValue && options.Range.UseWholeBoard) return 0x10000000001;` -- `cap` est un
        # `Nullable<int>` local que le decompile n'ECRIT jamais, donc `!HasValue` est toujours vrai.
        return Range(value=1, only_adjacent=False, use_whole_board=True)

    # `onlyAdjacent = RangedBoolExtensions.IsTrue(options.Range.OnlyAdjacent, caster);` -- position
    # NATIVE exacte : AVANT toute resolution d'arme, et il n'en depend jamais. C'est ce qui autorise
    # le tri-etat ci-dessous.
    only_adjacent = ranged_bool_is_true(rng.only_adjacent, state, caster_id)

    if rng.override_range is not None:
        value = int(rng.override_range)
    else:
        e = state.get_entity(int(caster_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        value = unit_weapon_range(_visual_id(state, caster_id), ctx)
        if value is None and ctx is not None:
            # `if (!HasAnyWeapon(caster)) v = GetStat(caster, StatType.Range = 2);` -- la PREMIERE
            # branche d'arme du natif, celle que `unit_weapon_range` laisse a `None` faute de canal.
            # ⚠ **LE CANAL EXISTE, et la docstring qui disait le contraire etait PERIMEE**
            # (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1) : `combatSnapshot` publie `stats.range`, et son
            # catalogue `statTypes` l'apparie explicitement a l'index **2** -- soit `StatType.RANGE`.
            # `UnitStats.get_stat` rend `0` quand le composant est absent, ce qui est le mirror du
            # `default -> return 0` de `IdunBattle.Entities.UnitExtensions$$GetStat` : les deux
            # coincident donc, la ou un `None` inventait une indecision que le natif n'a pas.
            # Ce que ca FERME : hors `only_adjacent`, une portee `None` desarmait le gate de distance
            # -- le natif refusait TOUTE cible (`d > 0`), le port les acceptait toutes. Ecart
            # PERMISSIF, le seul type qu'un entrainement puisse exploiter.
            value = int(ctx.get_stat(int(StatType.RANGE)))
        # `value is None` (canal ABSENT, face DECISION) -> portee NON OBSERVABLE. On NE SORT PAS :
        # seule la branche DISTANCE en depend, `only_adjacent` reste exact.

    # `if (options.Range.OverrideRangeFunc != null) v = OverrideRangeFunc(caster);` -- le delegue
    # ECRASE tout ce qui precede (arme, override, config) et precede les deux clamps de melee. Le port
    # ne le resout pas : la VALEUR devient inconnue, `only_adjacent` non.
    if rng.override_range_func:
        value = None

    if _has_forced_in_melee(state, caster_id):
        value = None if value is None else min(1, value)
        only_adjacent = True
    if ranged_bool_is_true(options.force_melee_target, state, caster_id):
        if should_apply_ranged_in_melee(state, caster_id, caster_tiles):
            value = None if value is None else min(1, value)
            only_adjacent = True
    # Sortie COMPLETE : bits 40..47 du retour natif restent a zero (`(cVar2 != 0) << 0x20` puis
    # `CONCAT44`), et on ne l'atteint que si `options.Range.UseWholeBoard` est faux.
    return Range(value=value, only_adjacent=only_adjacent, use_whole_board=False)


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
                          options: "TargetingOptions", caster_tiles=None) -> int:
    """LE VOLET PORTEE du filtre statique (surcharge 7 arguments de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`), sur le chemin
    `ignoreRangeChecks = false` — le seul emprunte par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. Rend le `TargetingRule` rompu
    ou 0 :

      * `range.OnlyAdjacent` -> `battleQuery.AreEntitiesAdjacent(casterTiles, target)` (lui-meme
        `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, cf. `are_tiles_adjacent` : MEME
        TUILE incluse + gate d'elevation) ; faux -> `TargetIsInRange` ;
      * sinon, et SEULEMENT si `!options.Range.UseWholeBoard` (le gate vit DANS cette branche-ci, et
        il lit les OPTIONS, pas le champ homonyme du `Range` rendu) :
        `d = movementQuery.GetDistance(casterTiles, target)` = MIN des
        `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` entre tuiles source et tuiles cible
        (`hexgeo.distance` offline, meme convention evenq que `Board`) ;
        `rules & TargetIsAtRange` -> refus si `d != range.Value` (portee EXACTE) ;
        sinon                     -> refus si `d > range.Value`.

    Cible sans position (tuile non modelisee, entite absente) -> 0 : on ne sait pas mesurer, donc on
    n'invente pas de refus.

    #419-r1-tr14-r5-r2-r1-r2-r1-r1 : le desarmement pour cause de PORTEE NON OBSERVABLE vit ICI, dans
    la seule branche qui lit la valeur. Il vivait dans `get_range` (un `return None` global), ce qui
    abandonnait AUSSI la branche `only_adjacent` -- alors que ni elle ni le calcul natif d'
    `onlyAdjacent` ne lisent la portee. Gisement : les unites SANS ARME du gameconfig, pour qui
    `unit_weapon_range` rend `None` ET `only_adjacent` vaut vrai (l'attaque normale porte
    `RANGE_ADJACENT_IF_MELEE_CASTER`, et `IsRanged` est faux faute d'arme a `Range`).

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
    rend tel quel).

    #590-r6 : `caster_tiles` est le `casterTiles` natif -- le 2e argument de la surcharge 7
    arguments, que `TargetingQuery$$GetValidTargets` lui transmet depuis SON propre 2e argument.
    `None` = la position REELLE, le seul regime d'avant cette tranche. Les DEUX branches (adjacence
    et distance) le consomment, comme le natif, et `get_range` le recoit lui aussi."""
    rr = get_range(state, caster_id, options, caster_tiles)
    if rr is None:
        return 0
    src_feet = caster_tiles_of(state, caster_id, caster_tiles)
    dst_feet = entity_tiles(state, target_id)
    if not src_feet or not dst_feet:
        # DIVERGENCE DE SUBSTRAT, NOMMEE (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r2). Le natif ne teste rien
        # ici : il appelle `MovementQuery$$GetDistance`, qui rend `int.MaxValue` sur une liste vide
        # (son minimum est initialise a `0x7fffffff` et la boucle externe n'est pas entree), donc il
        # REFUSE `TargetIsInRange`. Le port ne peut pas le suivre : `entity_tiles` rend `[]` aussi
        # bien pour « cette entite n'a pas de tuile » que pour « le port ne sait pas la resoudre »,
        # et refuser sur le second inventerait une mesure. Le mirror EXACT du court-circuit vit donc
        # un etage plus haut, dans `get_range` (`Range(0, false, UseWholeBoard)`), la ou il est
        # DECIDABLE. Gisement de l'ecart, MESURE et vide : le seul porteur de « caster sans tuile »
        # est la MACHINE OF WAR, et ses 22/22 masques portent `use_whole_board`, donc le gate de
        # distance ne s'evalue jamais pour elle (test ci-dessous).
        return 0
    if rr.only_adjacent:
        board = state.board
        if board is None:
            return 0                                  # adjacence NATIVE non calculable -> pas de gate
        ok = are_entities_adjacent(board, src_feet, dst_feet)
        return 0 if ok else int(TR.TargetIsInRange)
    if options.range is not None and options.range.use_whole_board:
        # `else if (!options.Range.UseWholeBoard)` -- SECOND test du volet portee, et il porte sur les
        # OPTIONS, pas sur le champ homonyme du `Range` rendu (qui en est pourtant l'alias exact, cf.
        # `Range`). Il vit DANS la branche `!OnlyAdjacent` : l'ordre est donc adjacence PUIS plateau
        # entier, jamais l'inverse. Avant #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1 ce gate etait porte par
        # le `return None` de `get_range` ; le mirror du court-circuit l'a rendu explicite ICI.
        return 0
    if rr.value is None:
        # SEULE la branche DISTANCE a besoin de la valeur : `only_adjacent` a deja ete tranche
        # ci-dessus, exactement comme le natif (`if (range._4_1_ == 0) { ...(int)range... }`).
        # #419-r1-tr14-r5-r2-r1-r2-r1-r1 : c'est ici, et NON dans `get_range`, que l'indisponibilite
        # de la portee numerique doit desarmer -- l'y remonter desarmait aussi l'adjacence.
        return 0
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
                                options: "TargetingOptions", caster_tiles=None) -> set:
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

    Rend le SET des positions obscurcissantes (cardinal seul lu par la cascade).

    #590-r6 : le premier argument du slot `IMovementQuery 15 GetTilesObscuringTerrain` EST
    `casterTiles` -- la ligne de vue part donc de la position INTERROGEE, pas de la position reelle.
    `caster_tiles=None` rend exactement le comportement d'avant."""
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
    return get_tiles_obscuring_terrain_from_tiles(
        state.board, caster_tiles_of(state, caster_id, caster_tiles),
        _obscuring_target_tile(state, resolved), t2, 2)


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
#   slot 0x60 / 0x61 / 0x62 = les trois surcharges de `BattleQuery$$AreEntitiesAdjacent`
#       (`...u003Cu003Ec__DisplayClass117_0/118_0/119_0$$u003CAreEntitiesAdjacentu003Eb__0`)
#   slot 0x7d / 0x7e / 0x7f / 0x80 = les quatre surcharges de `BattleQuery$$GetAdjacentEnemies`
#       (`...u003Cu003Ec__DisplayClass152_0..155_0$$u003CGetAdjacentEnemiesu003Eb__0`)
#
# Le filtre statique appelle le slot **0x61** pour la PORTEE `OnlyAdjacent` (`(casterTiles, target)`
# = `(IList, IEntity)`), le slot **0x62** pour le bit 32 (`(targetTiles, casterTiles)` : deux
# LISTES) et le slot **0x80** pour le bit 42 (`(targetTiles, caster, false)`).
#
# ⚠ LES DEUX GROUPES ONT ETE RE-MESURES le 2026-08-05 (#433-r4-r1-r4-r2-r1-r1-r1) et TOUS DEUX
# etaient DECALES D'UN CRAN (`0x5f/0x60/0x61` sur `DisplayClass116_0..118_0`, `0x7c..0x7f` sur
# `DisplayClass151_0..154_0`) -- c'est le gisement annonce par `#433-r3-r3`, ici solde pour ces deux
# groupes SEULEMENT. Sur `rnca9r7q6c` il n'existe AUCUN `DisplayClass116_0`/`151_0` portant ces
# lambdas ; les classes reelles sont `117..119` et `152..155`, et les slots qu'elles re-appellent
# sont `0x60/0x61/0x62` et `0x7d/0x7e/0x7f/0x80`.
# L'index seul ne suffirait pas a designer une SURCHARGE : ce qui l'identifie ici, c'est le TYPE des
# arguments a deux call-sites INDEPENDANTS qui melangent une LISTE et une ENTITE --
# `TargetingQuery$$GetInvalidTargetReason` (branche `OnlyAdjacent`) et
# `RammingSpeedAbility$$GetDynamicInvalidTargetReason` passent tous deux `(casterTiles, target)` au
# MEME `0x61`. Le bit 42 est confirme par le meme decompile, qui y appelle `0x80`.
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
    """`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles(IEntity)` — le slot 0x52 de
    `IBattleQuery`, LU dans le champ `slot` d'`Il2CppMethodDefinition`
    (`data/symbols/<build>/metadata/interface_slots.tsv`).
    ⚠ Ce slot etait ecrit `0x51`, et la cause est NOMMEE : l'index avait ete pris sur
    `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass101_0$$u003CGetFreeAdjacentTilesu003Eb__0`,
    c'est-a-dire par une lecture INDIRECTE — exactement la grandeur intermediaire que
    `#477-r24-r1` a montree n'indexer RIEN. `0x51` est `GetAdjacentTiles`, que le corps ci-dessous
    appelle : le decalage de 1 se lit comme une chaine d'appel prise pour une identite.
    Mirror du decompile :

        tiles = BattleQuery$$GetAdjacentTiles(entity, requireEmptyOrSteppable: true,
                                              requireWalkable: true[, allowTemporary: true]);
        tiles.FilterInPlace(t => TileExtensions.CanAddUnit(t, state, true, false, false));
        return tiles;

    Les deux pre-filtres de `GetAdjacentTiles` sont SUBSUMES par `CanAddUnit` (vide-ou-steppable +
    walkable), et `allowTemporary` ne filtre rien ; les deux surcharges natives de
    `GetFreeAdjacentTiles` (slots 0x52 et 0x53, qui ne different QUE par ce flag) coincident donc
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


def get_adjacent_tiles(state: "State", entity_id, only_empty_or_steppable: bool,
                       only_walkable_tiles: bool, allow_temporary: bool) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(IList from, bool onlyEmptyOrSteppable,
    bool onlyWalkableTiles, bool allowTemporary)` — la surcharge LISTE, slot 81 d'`IBattleQuery`
    (arite 4, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`). Mirror du decompile :

        set = new OrderedSet<IEntity>();
        foreach (tile in from)                                   # UNION des ring-1 de l'empreinte
            set.AddRange(BattleQuery$$IterateAdjacentTiles(tile, onlyEmptyOrSteppable,
                                                           onlyWalkableTiles, allowTemporary));
        return set;                                              # DEDUPLIQUE, ordre d'insertion

    `IterateAdjacentTiles` delegue par tuile a `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
    dont la boucle est deja lue mot pour mot dans `engine/battle_query.get_adjacent_tiles` :

        foreach (neighbour in tile.Neighbours)
            if (tile == null)                                              continue
            if (!allowTemporary   && TileExtensions.IsTemporary(tile))     continue
            if (onlyWalkableTiles && !TileExtensions.IsWalkable(tile, 1))  continue
            if (onlyEmptyOrSteppable && !IsEmptyOrSteppable(tile, state))  continue
            if (|elev(src) - elev(tile)| < 2) yield tile                   # porte INCONDITIONNELLE

    ⚠ CE N'EST PAS `get_free_adjacent_tiles`, bien que les deux COINCIDENT offline pour
    `(onlyEmptyOrSteppable=1, onlyWalkableTiles=1)`. `GetFreeAdjacentTiles` est un natif DISTINCT
    (slots 82/83, arite 1) qui appelle celui-ci puis lui applique en plus
    `ListExtensions$$FilterInPlace(t => TileExtensions.CanAddUnit(t, state, 1, 0, 0))` — un filtre
    qui, offline, ne retire rien de plus (`CanAddUnit` re-teste vide-ou-steppable + walkable, et son
    seul terme supplementaire, la tuile RESERVEE `Position+0x2c`, n'est capte par aucun RPC). La
    coincidence est donc MESUREE sur ce que le port modelise, pas supposee — et les deux fonctions
    restent separees parce que les deux natifs le sont.

    `allow_temporary` est PROPAGE mais INERTE : `TileExtensions$$IsTemporary` n'a aucun substrat
    offline (meme limitation, deja nommee, que `get_free_adjacent_tiles`). Le declarer plutot que le
    taire fait diverger le jour ou le substrat existera.

    `only_empty_or_steppable=False` EST DESORMAIS MIRRORE (#287-r11, le gate de `1094 TheLantern`
    passe `(0, 1, 1)`) : le flag GATE le filtre, il ne le conditionne plus a l'entree. C'est
    litteralement le `if (onlyEmptyOrSteppable && !IsEmptyOrSteppable(tile, state)) continue` du
    decompile ci-dessus -- a `false`, le terme disparait, il ne s'inverse pas.
    `only_walkable_tiles=False` LEVE toujours : AUCUN call-site porte ne le passe, et il ferait
    entrer des tuiles que le port ne sait pas qualifier. Mentir sur un flag non mirrore serait pire
    que refuser.

    Rend des `(col,row)`, dedupliques, dans l'ordre d'insertion."""
    if not only_walkable_tiles:
        raise NotImplementedError(
            "get_adjacent_tiles: `only_walkable_tiles=False` n'a aucun call-site porte "
            "-- il n'est donc pas mirrore")
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
                continue                       # porte d'ELEVATION de `TileQuery$$IterateAdjacentTiles`
            coord = board.coord(nid)
            if coord in out:
                continue                       # `OrderedSet` : deduplication
            if not board.walkable(nid):
                continue                       # `onlyWalkableTiles` -> `TileExtensions$$IsWalkable`
            if only_empty_or_steppable and not tile_is_empty_or_steppable(state, coord):
                continue                       # `onlyEmptyOrSteppable` -> `IsEmptyOrSteppable`
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


def get_adjacent_units(state: "State", entity_id, friends_of=None, enemies_of=None,
                       ignore_steppables: bool = False) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(IEntity from, IEntity friendsOf,
    IEntity enemiesOf, bool ignoreSteppables)` — slot 122 d'`IBattleQuery` (arite 4, LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv`). Mirror du decompile, qui tient en une
    ligne :

        return GetUnitsOnTiles( IterateAdjacentTiles(from, requireEmptyOrSteppable: false,
                                                           requireWalkable: true,
                                                           allowTemporary: true),
                                friendsOf, enemiesOf, ignoreSteppables );

    C'est le MEME etage que `get_adjacent_enemies` / `get_adjacent_friends` ci-dessus — memes trois
    flags d'iterateur, meme `CountOrGetUnitsOnTiles` en aval :

        foreach (tile in tiles) {
            u = UnitExtensions.GetUnit(tile, state);        if (u == null) continue;
            if (onlyNonSteppable && IsSteppable(u))         continue;
            if (friendOf != null && !IsFriend(u, friendOf)) continue;
            if (enemyOf  != null && !IsEnemy(u, enemyOf))   continue;
            set.Add(u);
        }

    La difference avec ses deux voisins est qu'ici les DEUX filtres sont des PARAMETRES : le
    call-site porte (`ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`) les passe NULS
    tous les deux, donc TOUTE unite adjacente est rendue, amie comme ennemie, steppable comprise
    (`ignoreSteppables = false`). C'est le seul des trois natifs qui sache rendre cet ensemble-la.

    Comme ses voisins : la tuile SOURCE n'est jamais rendue (l'iterateur parcourt l'adjacence
    STOCKEE), la porte d'ELEVATION `|dElev| < 2` s'applique, `state.unit_at` mirror
    `UnitExtensions$$GetUnit(tile, state)`, et l'absence de board rend `[]` (aucun refus invente).

    ⚠ `from` est une ENTITE, pas une liste : le port passe par `entity_tiles`, qui rend `[la tuile]`
    quand l'entite EST une tuile — le regime exact du call-site porte (1087 cible une TUILE)."""
    board = state.board
    if board is None or entity_id is None:
        return []
    out: list = []
    for t in (entity_tiles(state, int(entity_id)) or ()):
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
            if ignore_steppables and UnitTrait.Steppable.name in (_unit_traits(state, occ.id) or ()):
                continue
            if friends_of is not None and not units_are_friends(state, friends_of, occ.id):
                continue                                   # `IsFriend(u, friendOf)`
            if enemies_of is not None and not units_are_enemies(state, enemies_of, occ.id):
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

#: Le 2e argument que `TargetingQuery$$GetInvalidCasterReason` passe au slot `0x1b`
#: (`HasMinimumRemainingTurns`) sous le bit `CasterHas2TurnsLeft` : le litteral **2** du decompile
#: (`<slot 0x1b>(this.<+0x18>, caster, 2)`). C'est un NOMBRE DE TOURS, pas un id -- il ne designe
#: aucune entite du jeu et n'a donc pas d'enum ; c'est ce `2` qui donne son NOM au bit.
CASTER_HAS_2_TURNS_LEFT_ARG = 2


def get_invalid_caster_reason(state: "State", caster_id: int, ability, caster_tiles=None) -> int:
    """`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` — volet CASTER du meme
    filtre, evalue AVANT le volet cible par l'overload 5 arguments de
    `TargetingQuery$$GetInvalidTargetReason` (`if (casterReason.IsInvalid()) return casterReason;`).

    TROIS de ses regles sont portees — `CasterHasNotMoved` (0x10), `CasterMatchesDynamicRule`
    (0x4, le POINT D'EXTENSION du volet caster, depuis #250) et `CasterHas2TurnsLeft` (bit 52,
    depuis #287-r11-r1-r1). La 1re tombe gratuitement : le bit est deja dans les
    `TARGETING_OPTIONS` de l'ability et le predicat existe deja (`unit_has_moved`). Mirror du
    decompile :

        if (battleQuery.<slot 0x35>(caster) && (rules & 0x10) != 0) {
            if (!UnitExtensions.DidMove(caster)
                && GetTiles(caster).IsEquivalentTo(casterTiles)) -> ok
            return GenericBrokenTargetingRule(0x10);
        }

    `IdunBattle.Entities.UnitExtensions$$DidMove` = `UnitFlagsComponent.Has(unit, UnitFlag.Moved=0)`
    = exactement `unit_has_moved`. La 2e clause (`casterTiles` != les tuiles REELLES du caster)
    couvre une position de cast HYPOTHETIQUE ; sur le chemin `ExecuteInternal` le natif passe
    `EntityExtensions.GetTiles(caster, state)`, donc les deux listes sont toujours equivalentes ->
    la clause se reduit a `DidMove`.

    ⚠ LE PREFIXE EST `<slot 0x35>`, ET IL EST RESOLU (#287-r11-r1-r1) -- cette note ecrivait
    `<slot 0x34>` « non resolu », soit un DECALAGE DE UN qui apparie `52 IsInMovementRange`
    (arite 2) la ou le call-site ne passe qu'UN argument. Le slot `0x35` = 53 =
    `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit` (arite 1,
    `data/symbols/<build>/metadata/interface_slots.tsv`), confirme par la lambda
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass86_0$$
    u003CIsTurnOfUnitu003Eb__0`, qui relaie le MEME couple (slot, classe d'interface) et dont le NOM
    donne la methode :

        GetOriginalOwnerEntity(GetUnit(caster)).Id == StateExtensions.GetMatchTurn(state).CurrentPlayerId

    Il est PORTE cote DECISION (`engine.services.ability_caster_gates`, champ
    `CasterSubstrate.is_turn_of_unit`, mesure #433-r4-r2-r1-r2-r2-r1-r1-r1-r4 : 11 paires sur 42
    ou le natif ACCEPTE une unite qui a bouge parce que ce n'est pas son tour), ET **ICI DEPUIS
    #287-r11-r1-r1-r2** -- foyer `engine.runner.components.is_turn_of_unit`, qui lit
    `OwnerComponent.<PlayerEntityId @+0x10>` (le proprietaire d'ORIGINE, celui que
    `EntityExtensions$$GetOriginalOwnerEntity` resout) contre `State.current_player_id`.

    ⚠ L'OMISSION ETAIT RESTRICTIVE, ET SON REGIME D'INERTIE EST NOMME. Sur le chemin du CAST
    (`ActiveAbilityOperation$$ExecuteInternal` -> `handler.py`) le caster est le joueur courant,
    donc le prefixe y est vrai par construction et le prefixe est INERTE. Il MORD des que le port
    interroge une unite dont ce n'est pas le tour : c'est le regime de l'ORACLE `abilityReason`,
    que `AttackQuery$$GetInvalidCasterReason` evalue pour n'importe quelle unite des deux camps --
    et le flag `UnitFlag.Moved` SURVIT a la fin du tour (`RemoveTurnFlags` est purge par le
    `StartTurnOperation` du JOUEUR ENTRANT, pas globalement), donc une unite qui a bouge puis passe
    la main porte encore le flag pendant tout le tour adverse. Sans le prefixe, le port rendait
    `CasterHasNotMoved` la ou le natif rend `0`. MESURE (#287-r11-r1-r1-r2, probe
    `probe_287r11r1r1r2_is_turn_of_unit.py`, board `MC1_67`) : ventilation non degeneree, natif
    `0x0` / port AVANT `0x10` / port APRES `0x0` sur le bras hors-tour, les deux d'accord a `0x10`
    sur le bras EN-TOUR.

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
        6. **`CasterHas1/3/7Tiles` (bits 35/36/37) PORTEES depuis #895-r2**,
           **`CasterHas2TurnsLeft` (52) PORTEE depuis #287-r11-r1-r1**, `CasterIsMachine` (53)

    NON PORTEES (memes motifs qu'en tete de module) : les points 2, 3, 4b, et `CasterIsMachine`
    (bit 53) du point 6.

    `CasterHas2TurnsLeft` (bit 52) -- PORTEE PAR #287-r11-r1-r1. VERBATIM du decompile :

        if ((rules >> 0x34 & 1) && !<IBattleQuery slot 0x1b>(this.<+0x18>, caster, 2))
            return GenericBrokenTargetingRule(0x10000000000000);

    Le slot `0x1b` = 27 = `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` (arite 2,
    table de metadonnee + lambda `...u003Cu003Ec__DisplayClass68_0$$u003CHasMinimumRemainingTurns
    u003Eb__0`). La note precedente ecrivait `0x1a` -- un DECALAGE DE UN, qui apparie
    `26 ShouldPlayerSkipTurn` (arite **1**) alors que le call-site passe DEUX arguments : c'est
    cette contradiction d'arite qui a rendu le slot « non resolu ». Mirror :
    `engine.services.battle_query.has_minimum_remaining_turns`, dont le premier bras (**pas de
    plafond de rounds -> `true`**) est LU dans `BC.Victory.VictoryConditions`, jamais suppose.
    TROIS porteurs, tous MACHINE OF WAR : 1142 (`astraOrdnanceBattery`), 1160 (`tauBroadside`),
    1188 (`adeptExorcist`).

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
    sur le chemin replay/self-play OFFLINE, ou c'est `MoveUnitOperation` -> `set_moved_flag`.

    #590-r6 -- `caster_tiles` : la position INTERROGEE (`None` = la position REELLE). DEUX clauses
    la lisent, et une SEULE change de verdict quand elle differe des tuiles reelles :
      * `CasterHasNotMoved` -- la 2e clause native est `GetTiles(caster).IsEquivalentTo(casterTiles)`,
        donc une position HYPOTHETIQUE fait rendre `0x10` meme si l'unite n'a pas bouge. Elle est
        desormais ECRITE, et elle est INERTE sur le seul consommateur porte de la position
        hypothetique (l'attaque normale, preset `0x4002`, ne pose pas le bit `0x10`) ;
      * la clause TUILE-NULLE (4a) teste `IsNullOrEmpty(casterTiles)`, donc bien la position
        interrogee -- une position candidate non vide ne la rompt jamais.
    Les trois filtres `CasterHasNTiles` lisent `GetFeetCount(caster, state)`, c'est-a-dire le CASTER
    et non `casterTiles` : ils restent sur les pieds REELS, comme le natif."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return 0
    if options.has(TR.CasterHasNotMoved):
        # LE PREFIXE `<slot 0x35>` = `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit(caster)`,
        # PORTE PAR #287-r11-r1-r1-r2 (foyer `runner.components.is_turn_of_unit`). Ce n'est pas le
        # tour du proprietaire d'ORIGINE -> le natif SAUTE la clause entiere, flag `Moved` compris.
        # Seul un `False` MESURE allege : `None` = substrat non capte, et sauter sur une non-mesure
        # fabriquerait une acceptation (cf. le tri-etat du foyer).
        if is_turn_of_unit(state, int(caster_id)) is not False:
            # `if (!DidMove(caster) && GetTiles(caster).IsEquivalentTo(casterTiles)) -> ok`
            # -- la 2e clause REFUSE une position de cast hypothetique (#590-r6). `IsEquivalentTo`
            # est ensembliste : on compare les MULTI-ENSEMBLES de tuiles, pas leur ordre. Le
            # court-circuit `caster_tiles is None` la rend litteralement inexistante dans le regime
            # d'avant cette tranche (la position interrogee EST celle du caster).
            deplacee = (caster_tiles is not None
                        and sorted(caster_tiles_of(state, int(caster_id), caster_tiles))
                        != sorted(entity_tiles(state, int(caster_id))))
            if deplacee or unit_has_moved(state, int(caster_id)):
                return int(TR.CasterHasNotMoved)
    # CLAUSE TUILE-NULLE (4a) -- placee ici, au rang NATIF : APRES `CasterHasNotMoved`, AVANT
    # `CasterMatchesDynamicRule`. L'ordre n'est pas cosmetique, c'est lui qui fixe la RAISON rendue :
    # une unite sous terre rompt CETTE regle et non la regle-delegue de son ability (cf. la section
    # dediee dans la docstring).
    # `IsNullOrEmpty(casterTiles)` porte sur la position INTERROGEE (#590-r6). Le repli reste
    # `get_unit_feet` -- PAS `caster_tiles_of` -- pour etre value-preservant a l'octet : `entity_tiles`
    # a un 2e bras (une TUILE se rend elle-meme) que `get_unit_feet` n'a pas, et cette clause-ci
    # lisait `get_unit_feet` avant cette tranche.
    if not (options.has(TR.AllowNullCasterTile) or options.has(TR.CasterHasNoTile)):
        interrogee = (get_unit_feet(state, int(caster_id)) if caster_tiles is None
                      else caster_tiles_of(state, int(caster_id), caster_tiles))
        if not interrogee:
            return int(TR.AllowNullCasterTile)
    # `CasterMatchesDynamicRule` -- LE POINT D'EXTENSION du volet caster (#250), place ici comme dans
    # le natif (apres la paire tuile-nulle, avant les filtres de `FeetCount`). Le natif rend le code
    # que la regle-delegue lui donne, tel quel : `if (r != 0) return GenericBrokenTargetingRule(r)`.
    if options.has(TR.CasterMatchesDynamicRule):
        reason = int(ability.get_dynamic_invalid_caster_reason(state, caster_id) or 0)
        if reason:
            return reason
    # 6. LES TROIS FILTRES DE `GetFeetCount` -- `CasterHas1Tiles` / `CasterHas3Tiles` /
    #    `CasterHas7Tiles` (bits 35/36/37), PORTES PAR #895-r2. VERBATIM du decompile
    #    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, surcharge
    #    `IList<IEntity> casterTiles`), juste APRES la regle-delegue et AVANT le bit 52 :
    #
    #        feet = UnitExtensions.GetFeetCount(caster, state);
    #        if ((rules >> 0x23 & 1) && feet != 1) return broken(0x800000000);
    #        if ((rules >> 0x24 & 1) && feet != 3) return broken(0x1000000000);
    #        if ((rules >> 0x25 & 1) && feet != 7) return broken(0x2000000000);
    #
    #    `IdunBattle.Entities.UnitExtensions$$GetFeetCount` = `GetUnitFeetIds(unit, state).Count`,
    #    dont `runner.components.get_unit_feet` est le mirror (meme parcours de
    #    `UnitComponent._feet @+0x78`, repli sur le `PositionComponent` pour l'unite mono-hex).
    #    ⚠ NUANCE LUE, PAS SUPPOSEE : le natif compte les PIEDS (`GetUnitFeetIds`), pas les tuiles
    #    (`IterateTiles`, qui SAUTE un pied sans tuile). Les deux coincident cote port, ou aucun
    #    pied n'existe sans tuile.
    #    L'ORDRE N'EST PAS COSMETIQUE : place ici, un refus de cardinal PRECEDE `CasterHas2TurnsLeft`
    #    et SUIT la regle-delegue -- c'est lui qui fixe la raison rendue quand deux regles sont
    #    rompues.
    #    AUCUN REFUS INVENTE SUR UN SUBSTRAT ABSENT : `feet` vide sort deja par la clause 4a
    #    ci-dessus chez les QUATRE porteurs du registre (aucun ne pose `AllowNullCasterTile` ni
    #    `CasterHasNoTile` -- compte re-derivable `ABILITY_CLASSES` x `TARGETING_OPTIONS.rules`,
    #    ne pas le citer de memoire).
    #    Le pendant DECISION de ces trois clauses vit dans
    #    `engine.services.ability_caster_gates.invalid_caster_reason` (etage 6) ; les deux lisent le
    #    MEME decompile, et c'est la face RUNNER qui manquait.
    feet_count = len(get_unit_feet(state, int(caster_id)))
    if options.has(TR.CasterHas1Tiles) and feet_count != 1:
        return int(TR.CasterHas1Tiles)
    if options.has(TR.CasterHas3Tiles) and feet_count != 3:
        return int(TR.CasterHas3Tiles)
    if options.has(TR.CasterHas7Tiles) and feet_count != 7:
        return int(TR.CasterHas7Tiles)
    # 7. `CasterHas2TurnsLeft` (bit 52) -- APRES la regle-delegue et APRES les trois filtres de
    #    `GetFeetCount`, comme dans le natif. Aucun porteur du bit 52 ne pose AUSSI un
    #    `CasterHasNTiles` (les trois sont des MoW), donc l'ordre relatif des deux blocs est
    #    aujourd'hui INERTE -- il est ecrit fidele parce que c'est le natif, pas parce qu'un cas
    #    l'exerce.
    #    `has_minimum_remaining_turns` rend desormais une VALEUR dans les DEUX bras
    #    (#287-r11-r1-r1-r1) : le second lit `State.turns_ended`, le mirror de
    #    `TurnComponent.<Dictionary @+0x40>` que pose `turnflow.set_current_player` (ecrivain natif
    #    UNIQUE) et que seede `snapshot._load_turns_ended`. Il LEVAIT, faute de ce substrat.
    if options.has(TR.CasterHas2TurnsLeft):
        if not _bq.has_minimum_remaining_turns(caster_id, CASTER_HAS_2_TURNS_LEFT_ARG, state=state):
            return int(TR.CasterHas2TurnsLeft)
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


def _invoque_regle_dynamique(ability, state: "State", caster_id: int, target_id, caster_tiles):
    """LE DELEGUE `options+0x38` -- et il recoit `casterTiles`, ce que le port ne lui donnait PAS.

    VERBATIM du site d'invocation dans la surcharge 7 arguments
    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) :

        if ((rules & 2) != 0) {                                  // TargetMatchesDynamicRule
            d = options.<+0x38>;
            rule = d.Invoke(caster, casterTiles, <cible RESOLUE>, targetTiles);
            if (rule != 0) return GenericBrokenTargetingRule(rule);
        }

    QUATRE arguments, dont `casterTiles` en DEUXIEME. Ce n'est pas un detail de fidelite : la regle
    de l'ATTAQUE NORMALE (`ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`) mesure
    l'ADJACENCE `casterTile x targetTiles` pour choisir l'arme, donc une position hypothetique en
    change le verdict. MESURE (#590-r6, `MC1_67`, summon a 4 de MOVEMENT) : sans ce threading, la
    branche mobile de `1101 AttemptedPossession` rendait `[]` sur TOUTES les positions candidates --
    la portee passait, la ligne de vue passait, et le delegue refusait quand meme parce qu'il
    mesurait l'adjacence depuis la tuile REELLE. Le mirror aurait ete livre INERTE.

    THREADING PAR SIGNATURE, meme patron que `PerformAIAbility._accepte_utility_entity` (#590-r4) :
    un porteur qui veut la donnee la DECLARE (`caster_tiles=` en mot-cle), les ~35 autres gardent
    leur contrat `(state, caster_id, target_id)` et ne voient AUCUN changement. Un appel a l'aveugle
    aurait leve `TypeError` sur chacun d'eux ; une signature illisible est traitee comme un refus."""
    fn = ability.get_dynamic_invalid_target_reason
    if caster_tiles is None or not _accepte_caster_tiles(fn):
        return fn(state, caster_id, target_id)
    return fn(state, caster_id, target_id, caster_tiles=caster_tiles)


def _accepte_caster_tiles(fn) -> bool:
    """Le porteur declare-t-il un parametre `caster_tiles` ? (cf. `_invoque_regle_dynamique`)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
        return True
    return "caster_tiles" in sig.parameters


def get_invalid_target_reason(state: "State", caster_id: int, target_id: Optional[int],
                              ability, *, apply_self_cast_switch: bool = True,
                              caster_tiles=None) -> int:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason` (-> ...WithRules ->
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) : rend le PREMIER
    `TargetingRule` rompu, dans l'ORDRE NATIF de la cascade, ou 0 (cible valide).

    `ability` = l'instance d'`ActiveAbility` portee. Ses `TARGETING_OPTIONS` (litteral du ctor natif)
    sont la SEULE source des bits : options absentes (`None`) = donnee non RE-lue -> AUCUN gate
    (jamais de refus invente).

    `apply_self_cast_switch` (#447-r1) -- LAQUELLE DES DEUX SURCHARGES NATIVES. Le natif en a deux,
    et elles ne font PAS la meme chose :

      * la surcharge **5 arguments** (`TargetingQuery$$GetInvalidTargetReason`, celle du CAST)
        commence par l'aiguillage self-cast et BRANCHE sur `GetCasterNotAddedReason` -- c'est le
        defaut ici, et le comportement de tous les appelants historiques ;
      * la surcharge **7 arguments** (celle que `TargetingQuery$$GetValidTargets` appelle dans sa
        boucle d'enumeration, avec `range` deja calcule) est la CASCADE SEULE : aucun aiguillage,
        aucun volet caster, la cible est jugee par la cascade meme quand elle EST le caster.

    ⚠ « CASCADE SEULE » N'EST PAS « SANS REGLE DYNAMIQUE » (#287-r4). Relue a l'octet sur le build
    courant, la surcharge 7 arguments INVOQUE le delegue `options+0x38` sous le bit
    `TargetMatchesDynamicRule`, entre `TargetIsNotAdjacentToEnemy` et `TargetIsCasterOrEnemy` --
    exactement la place ou ce port la met. Ce que les 5 arguments ajoutent, et qu'elle n'a pas,
    c'est l'aiguillage self-cast et l'appel prealable a `GetInvalidCasterReason` ; rien de plus.
    Donc TOUT appelant de cette fonction, `apply_self_cast_switch` a `False` compris, doit fournir
    une INSTANCE portant `get_dynamic_invalid_target_reason` -- une classe rendrait la methode NON
    LIEE (`TypeError`), un porteur minimal sans la methode ferait `AttributeError`.

    Le port n'a qu'un corps ; ce drapeau NOMME la surcharge. `False` = la 7 arguments -- reserve aux
    mirrors d'ENUMERATION (`caster_is_valid_target`), jamais au chemin du cast.

    `caster_tiles` (#590-r6) -- LE `casterTiles` NATIF, 2e argument des DEUX surcharges. `None` = la
    position REELLE du caster, c'est-a-dire ce que `ActiveAbilityOperation$$ExecuteInternal` passe
    (`EntityExtensions.GetTiles(caster, state)`) et le seul regime d'avant cette tranche. **QUATRE**
    etages de la cascade le consomment, et ce sont exactement les quatre que le natif alimente avec,
    releves un par un sur la surcharge 7 arguments :
      * le volet PORTEE -- `<IMovementQuery 10 GetDistance>(casterTiles, cible)` et
        `<IBattleQuery 0x61 AreEntitiesAdjacent>(casterTiles, cible)`, plus `GetRange(caster,
        casterTiles, options)` qui le repasse a `ShouldApplyRangedInMelee` ;
      * la LIGNE DE VUE -- `GetTilesObscuringTerrain(caster, casterTiles, cible, options)` ;
      * `TargetIsNotAdjacent` -- `<IBattleQuery 0x62>(targetTiles, casterTiles)` ;
      * **LA REGLE DYNAMIQUE** -- `options.<+0x38>.Invoke(caster, casterTiles, cibleResolue,
        targetTiles)`. C'est le quatrieme, et c'est celui qu'une lecture rapide rate : le delegue
        n'est pas un predicat sur la CIBLE seule. Cf. `_invoque_regle_dynamique`.
    Aucune autre regle du filtre ne lit la position du caster -- `TargetIsNotAdjacentToEnemy`, en
    particulier, ne recoit que `targetTiles` et le CASTER (pas ses tuiles).

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
    if (apply_self_cast_switch and options.self_cast
            and _targets_the_caster(state, caster_id, target_id, tuid, options)):
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
    reason = get_range_broken_rule(state, caster_id, target_id, options, caster_tiles)
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
        if get_tiles_obscuring_terrain(state, caster_id, target_id, options, caster_tiles):
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
        src = caster_tiles_of(state, caster_id, caster_tiles)     # `casterTiles` (#590-r6)
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
        reason = int(_invoque_regle_dynamique(ability, state, caster_id, target_id,
                                              caster_tiles) or 0)
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

    ⚠ CETTE FONCTION N'EST PAS CELLE QUE L'ORACLE `abilityReason` APPELLE (#287-r6). Le RPC passe
    par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui place DEUX etages EN
    AMONT de la cascade : disponibilite de l'ability (`ActiveAbilityComponent.GetOrNull` /
    `ActiveAbility.CanCurrentlyBeUsed` / `ability+0x44`) puis `IsDamagedMachine`, tous deux rendant
    `GenericBrokenTargetingRule(1)` = `TargetingRule.ValidRequest`. `ActiveAbilityOperation$$IsInvalidTarget`
    n'a AUCUN de ces etages -- il resout la config d'ability et appelle DIRECTEMENT le meme slot
    d'`ITargetingQuery`. Confronter les deux quand l'etage amont mord compare deux fonctions natives
    differentes : le natif rend `1` pour TOUTE cible, et le desaccord se lit a tort comme un bug de
    ce module (mesure : 4 couples `SquigMine`, natif `0x1` / port `0x1000`, alors que la cascade
    traversee rend `0x1000` DES DEUX COTES). Le cran est `oracle_targeting.oracle_court_circuite`,
    qui lit `casterReason` -- meme etage amont, sans dependre de la cible.

    ORDRE natif (overload 5 args de `TargetingQuery$$GetInvalidTargetReason`), RELU EN ENTIER :
    `GetRange`, puis `GetFirstOrNull(casterTiles)`, puis **`GetInvalidCasterReason`**, puis
    seulement l'aiguillage self-cast et le filtre statique. Le natif renvoie la raison CASTER telle
    quelle si elle est rompue -- d'ou le meme code dans `casterReason` ET `targetReason` de l'oracle
    `abilityReason` (mesure du probe #115). ⚠ Cette note disait « dont seul `CasterHasNotMoved` est
    porte » : PERIME. Le volet caster porte aujourd'hui `CasterHasNotMoved` (sous son prefixe
    `IsTurnOfUnit`), la clause TUILE-NULLE, `CasterMatchesDynamicRule`, les trois filtres de
    `GetFeetCount` et `CasterHas2TurnsLeft` -- l'etat exact se LIT dans
    `get_invalid_caster_reason`, il ne se cite pas d'ici."""
    if ability is None:
        return 0
    caster_reason = get_invalid_caster_reason(state, caster_id, ability)
    if caster_reason:
        return caster_reason
    return get_invalid_target_reason(state, caster_id, target_id, ability)


# ================================================================================================
# `CasterIsPossibleTarget` (bit 15) -- LE CASTER COMME CIBLE DE SA PROPRE ABILITY (#447-r1)
#
# LES QUATRE LECTEURS NATIFS DU BIT, relus a l'octet sur `rnca9r7q6c`. Trois seulement MORDENT,
# et le quatrieme est du CODE MORT -- ce qui n'est pas une opinion mais une lecture de ses
# appelants :
#
#   1. `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions`
#          if ((rules >> 0xf & 1) != 0)
#              <ensemble>.<IOrderedSet slot 0>(bVar12 ? casterTiles : caster);
#          if ((rules & 0x200000000000000) != 0)                        // TargetIsCasterOrEnemy
#              <ensemble>.<IOrderedSet slot 0>(bVar12 ? casterTiles : caster);
#      -- `bVar12 = onlyTiles || (rules >> 6 & 1)` (`TargetIsTile`) : domaine TUILE -> ce sont les
#      TUILES du caster qui entrent, domaine UNITE -> l'ENTITE caster. C'est le lecteur qui compte :
#      il AJOUTE le caster aux cibles POSSIBLES, en AMONT des trois `RemoveAll` et de la boucle de
#      filtrage de `GetValidTargets`.
#
#   2. `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` -- deux fois :
#          (int)range == 0 -> `(rules >> 0xf & 1)` ? new OrderedSet(casterTiles) : OrderedSet VIDE
#          branche disque  -> <IBattleQuery slot 0x67> `GetSurroundingTiles(..., includeCenter:
#                             (byte)(rules >> 0xf) & 1)`
#      Porte cote DECISION par `engine/services/ability_range.py` (#433-r4-r2-r1-r2-r2-r1-r1-r1),
#      qui est LE foyer de la zone -- ce module lui DELEGUE plutot que d'en ecrire un second corps.
#
#   3. `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` = `rules >> 0xf & 1`,
#      lecteur DECLARATIF (deux appelants, tous deux UI : `IdunBattle.View.FSM.Actions.UnitSelection$$QueueShowAsSelected`
#      et `idun.Ui.IdunAbilitySelectionHud$$SelectIfPossible`). Porte : `TargetingOptions.can_target_caster`.
#
#   4. `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`, branche
#      `else if (options+0x00 == 0 && !(rules & 0x800)) { if (rules & 0x8000) ... }` -- **MORTE sur
#      le chemin du CAST**, et c'est une mesure : cette fonction n'a que DEUX appelants de CODE
#      (les deux surcharges 5 arguments de `TargetingQuery$$GetInvalidTargetReason`), et toutes
#      deux n'y branchent que sous `if (*(char *)options != 0)`, c'est-a-dire self-cast POSE --
#      contradictoire avec le `options+0x00 == 0` que la branche exige. Non portee, et ne doit pas
#      l'etre : la porter INVENTERAIT un refus que le natif ne rend jamais.
#
# ⚠ CE QUE #447-r1 DISAIT, ET QUI EST FAUX : « elle vit par `TargetingQuery$$GetValidTargets`, qui
# RE-APPLIQUE la cascade CIBLE complete au caster ». `GetValidTargets` NE TESTE JAMAIS le bit 15 --
# relu en entier : il teste le bit 7 (`AddCaster`), `isSelfCasting || bit 11`, le bit 22 et le
# bit 3. Le bit 15 vit UN CRAN PLUS HAUT, dans `GetPossibleTargetsForOptions`.
# ================================================================================================


def caster_is_possible_target(state: "State", caster_id: int, ability) -> bool:
    """Le CASTER (domaine unite) ou SA TUILE (domaine tuile) entre-t-il dans l'ensemble rendu par
    `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` ?

    C'est la question que le bit 15 decide, et elle a exactement TROIS termes -- la zone de
    `GetTilesInRange` evaluee a la distance 0, puis les DEUX `AddRange(casterTiles)` de l'appelant :

        UseWholeBoard | CasterIsPossibleTarget | TargetIsCasterOrEnemy

    (les branches `(int)range == 0` et `GetSurroundingTiles` de `GetTilesInRange` lisent le MEME
    bit 15 que le premier ajout, donc elles n'ajoutent aucun terme ; `OnlyAdjacent` et
    `TargetIsAtRange` ne rendent JAMAIS la source d'eux-memes.)

    UN SEUL FOYER : la cascade est portee par `engine.services.ability_range`, et cette fonction lui
    DELEGUE (`zone_contains_for_options(..., distance=0)`) au lieu d'en ecrire un second corps.

    ⚠ LA DELEGATION PASSE LE MASQUE, PAS SEULEMENT L'ID -- et c'est un DEFAUT MESURE, pas un detail
    de style : `tiles_in_range_zone_contains(ability_id, ...)` RECHARGE le masque du registre depuis
    l'id, donc un masque MUTE par l'appelant (contre-epreuve qui desarme le bit 15, override
    runtime) etait silencieusement ignore -- la contre-epreuve rendait alors un VERT qui n'exercait
    rien. L'`ability_id` n'est passe que pour resoudre le `TargetingRange` (`UseRangeFromConfig` lit
    la config de l'ability) ; `None` est admis et laisse `_range_terms` decider.

    `False` quand le masque n'est pas RE-lu (`TARGETING_OPTIONS is None`) -- meme convention
    permissive que le reste du module : on n'invente ni un ajout ni un refus."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return False
    options = set_config_values_in_targeting_options(options, ability)
    # Les DEUX `AddRange` de `GetPossibleTargetsForOptions` -- inconditionnels, en aval de la zone.
    if options.has(TR.CasterIsPossibleTarget) or options.has(TR.TargetIsCasterOrEnemy):
        return True
    aid = getattr(ability, "ABILITY_ID", None)
    from engine.services.ability_range import zone_contains_for_options
    return bool(zone_contains_for_options(options, None if aid is None else int(aid),
                                          _visual_id(state, caster_id), 0))


def caster_is_valid_target(state: "State", caster_id: int, ability,
                           *, other_valid_targets: Optional[int] = None) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` RESTREINT a une seule question :
    **le CASTER figure-t-il dans l'ensemble rendu ?** -- c'est-a-dire ce que le canal
    `abilityTargets.fromHere` publie (`IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit,
    UnitPosition{GetTiles(unit)}, abilityType)` -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetValidTargets`
    -> la surcharge 6 arguments avec `skipAddCasterChecks = false`, lu au call-site).

    Le natif, dans l'ordre :

        if (IsInvalid(GetInvalidCasterReason(caster, casterTiles, options))) return Empty;
        possible = GetPossibleTargetsForOptions(...);          // le bit 15 AJOUTE le caster ICI
        foreach (t in possible)
            if (!IsInvalid(GetInvalidTargetReason(caster, casterTiles, t, options, true, range)))
                targets.Add(t);                                // surcharge 7 args = filtre STATIQUE
        if ((char)rules < 0)                     { if (!targets.Contains(caster)) targets.Add(caster); }
        if (isSelfCasting || (rules & 0x800))    { if (targets.Count > 0 && !Contains) Add(caster); }
        if (rules & 0x400000)                    { if (HasFreeTilesInRange || Count > 0) Add(caster); }
        if (rules & 8)                           { if (delegate(caster) == 0) Add(caster); }

    ⚠ **L'ETAGE D'AJOUT PEUT MASQUER LE BIT 15**, et c'est ce qui rend le regime de mesure delicat :
    une ability SELF-CAST voit son caster ajoute des qu'il existe au moins UNE autre cible valide,
    quel que soit le bit 15. Le seul regime ou le bit 15 DECIDE seul est donc « aucune autre cible
    valide » (`other_valid_targets == 0`), ou une ability NON self-castee sans le bit 11.

    `other_valid_targets` = le CARDINAL des autres cibles valides, que ce mirror n'enumere pas (il
    ne porte pas `GetPossibleTargetsForOptions` en entier -- residu nomme). `None` = non fourni :
    l'etage `Count > 0` est alors NON DECIDABLE et le mirror le traite en PERMISSIF (il n'ajoute
    pas), ce qui peut rendre `False` la ou le natif rend `True`. Un appelant qui veut la reponse
    EXACTE doit le fournir."""
    options = getattr(ability, "TARGETING_OPTIONS", None)
    if options is None:
        return False
    options = set_config_values_in_targeting_options(options, ability)
    # `if (IsInvalid(GetInvalidCasterReason(...))) return ValidTargets.Empty;`
    if get_invalid_caster_reason(state, caster_id, ability):
        return False
    # La boucle de filtrage, restreinte au caster : il n'y entre que s'il est POSSIBLE, et il n'y
    # survit que si le FILTRE STATIQUE (surcharge 7 arguments, donc sans l'aiguillage self-cast)
    # ne rompt aucune regle.
    if caster_is_possible_target(state, caster_id, ability):
        if not get_invalid_target_reason(state, caster_id, caster_id, ability,
                                         apply_self_cast_switch=False):
            return True
    # L'ETAGE D'AJOUT, dans l'ordre natif. Chaque bras AJOUTE le caster SANS le filtrer.
    if options.has(TR.AddCaster):
        return True
    if options.self_cast or options.has(TR.AddCasterIfAtLeastOneTarget):
        if other_valid_targets is not None and int(other_valid_targets) > 0:
            return True
    # `AddCasterIfAtLeastOneFreeTileInRange` (bit 22) -> `TargetingQuery$$HasFreeTilesInRange`, NON
    # PORTE (meme motif que dans `get_caster_not_added_reason`). Son bras `Count > 0` l'est, lui.
    if options.has(TR.AddCasterIfAtLeastOneFreeTileInRange):
        if other_valid_targets is not None and int(other_valid_targets) > 0:
            return True
    # `AddCasterIfMatchesDynamicRule` (bit 3) -- la regle-delegue CASTER `options+0x30`, deja portee
    # par #447 dans `get_caster_not_added_reason`. Ici le natif AJOUTE quand elle rend 0.
    if options.has(TR.AddCasterIfMatchesDynamicRule):
        if not int(ability.get_dynamic_invalid_caster_reason(state, caster_id) or 0):
            return True
    return False
