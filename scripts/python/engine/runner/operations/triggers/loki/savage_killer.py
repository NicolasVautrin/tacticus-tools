"""`SavageKiller` (passif de `spaceWulfen` << Ulf >>, `TriggeredAbilityType` 0x487 = 1159) --
UNE triggered-ability native, DEUX faces de declenchement, UN seul behaviour d'attaque.

i2 (gameconfig, verbatim) : << When a Summon moves to or is summoned adjacent to Ulf, he immediately
deals 5x 1819-2183 Power Damage to it. Ulf will also perform this ability against any enemy that
attempts to use an active ability while in a hex adjacent to him, in which case he deals his Damage
before that unit's ability is activated. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
`classes.tsv` : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility :
IdunBattle.Entities.Abilities.BaseTriggeredAbility`. La classe possede SIX corps, tous contigus dans
`ghidra/functions.tsv`, et **AUCUN autre** (pas de `CreateSimulationBehaviour`, pas de
`GetAttackRangeType` -- la base rend `config@+0x20`, soit `attackRangeType: "Melee"` du gameconfig).

Slots lus (tous sur `DSLSelectors`, l'objet `DSLFactory@+0x90`) -- identifies par les NOMS natifs,
pas par le pseudo-C : `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` construit
`AreEqual(+0x30, +0x60)`, `$$get_OwnerIsCaster` `AreEqual(+0x30, +0x48)` et `$$get_OwnerIsActor`
`AreEqual(+0x30, +0x40)` => **`+0x30 = Owner`, `+0x40 = Actor`, `+0x48 = Caster`, `+0x60 = Target`**
(et `+0x88 = CurrentAbility`, `+0x90 = TriggeringAbility`, lus par `$$CurrentAbilityIs` /
`$$TriggeringAbilityIs`).

## `...SavageKillerAbility$$CreateTrigger`
```
    CreateSummonMoveTrigger() op_BitwiseOr CreateCharacterActiveAbilityTrigger()
```

## `...SavageKillerAbility$$CreateSummonMoveTrigger` -- FACE A (le summon adjacent)
```
    hasSummon = HasTrait(Target@+0x60, UnitTrait.Summon = 2)
    adjacent  = IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType.OnlyAliveAndTargetable = 3)
    enemies   = AreEnemies(Owner@+0x30, Target@+0x60, UnitTeamSelectionType.ByCurrentTeam = 0)
    moved     =   AmountIsGreaterThanZero(PreviousTile(Target@+0x60))
              |   AmountIsGreaterThanZero(TurnStartTile(Target@+0x60))

      ( On(EventTriggerType.UnitAfterMove = 4,  ownerNeedsToBeAlive: 1) & hasSummon & adjacent & enemies )
    | ( On(EventTriggerType.UnitDisplaced = 0x23, 1)                    & hasSummon & adjacent & enemies )
    | ( On(EventTriggerType.UnitAdded = 0x32, 1)                        & hasSummon & adjacent & enemies
        & NOT IsReplacedUnit(Target@+0x60, UnitSelectionType.OnlyAliveAndTargetable = 3) )
    | ( On(EventTriggerType.UnitBecameTargetable = 0x3b, 1)             & hasSummon & adjacent & enemies
        & NOT moved )
```

## `...SavageKillerAbility$$CreateCharacterActiveAbilityTrigger` -- FACE B (l'actif adjacent)
```
      On(EventTriggerType.PreUnitAbility = 0x2a, ownerNeedsToBeAlive: 1)
    & (   IsActiveAbilityCountedAsUsed(isPreAbilityTrigger: **true**)
        & NOT TriggeringAbilityIs(AbilityOrEffect((ActiveAbilityType)0x467 = ArmouredMight_Move)) )
    & NOT IsOverwatchAttack()
    & IsAdjacent(Owner@+0x30, Caster@+0x48, UnitSelectionType.OnlyAliveAndTargetable = 3)
    & AreEnemies(Owner@+0x30, Caster@+0x48, UnitTeamSelectionType.ByCurrentTeam = 0)
```

## `...SavageKillerAbility$$CreateBehaviour(abilityState, triggerType)`
```
    target = (triggerType == EventTriggerType.PreUnitAbility) ? Caster@+0x48 : Target@+0x60
    DSLBehaviors.AttackWithAttackDamage(
        caster:          Owner@+0x30,
        target:          <target>,
        amount:          DSLFormulas.RandomAmount(GetVariableForLevel(AbilityVariableType.minDmg = 0xc),
                                                  GetVariableForLevel(AbilityVariableType.maxDmg = 0xd)),
        damageProfile:   AbilityConfiguration.GetDamageProfile()  -> Nullable(DamageProfileType.Power),
        hits:            AbilityConfiguration.GetNumberConstant(AbilityConstantType.nrOfHits = 0x2f) = 5,
        abilityOrEffect: AbilityOrEffect((TriggeredAbilityType)SavageKiller),
        options:         Nullable VIDE (la struct locale est zeroee),
        selectionType:   UnitSelectionType.OnlyTargetable = 2)
```

## `...SavageKillerAbility$$GetInitialTarget`
```
    ConditionalSelector( On(EventTriggerType.PreUnitAbility = 0x2a, 1), Caster@+0x48, Target@+0x60 )
```
-- soit LITTERALEMENT le meme choix de cible que `CreateBehaviour`, exprime en selecteur. Cette face
est donc SANS contenu propre a porter : le port materialise le choix une fois, dans `_victim_id`.

## `...SavageKillerAbility$$CreateValidActiveAbilityTrigger` -- **DEAD CODE**, verdict MESURE
```
    IsActiveAbilityCountedAsUsed(true)
  & NOT TriggeringAbilityIs(AbilityOrEffect(<ActiveAbilityType>))
```
`mcp__ghidra__list_xrefs` sur `1812b37e0` rend **DEUX** references, toutes deux de type `DATA`
(`1839eb150` = bloc `methodPointers` du PE, `183261c18` = table des methodes de la classe) et
**ZERO** `UNCONDITIONAL_CALL` -- la a ou ses deux soeurs `CreateSummonMoveTrigger` /
`CreateCharacterActiveAbilityTrigger` portent chacune, en plus, l'appel de `CreateTrigger`.
`search_symbols_by_name("CreateValidActiveAbilityTrigger")` sur tout le binaire rend **UN SEUL**
symbole -- celui-ci : il n'existe aucune methode HOMONYME sur une base ou une interface, donc aucun
slot virtuel ne peut l'atteindre. Son corps est un SOUS-ENSEMBLE exact des deux premiers conjoints de
`CreateCharacterActiveAbilityTrigger` : c'est un helper que le compilateur a laisse apres que son
contenu a ete deplie dans l'appelant. **Non porte, et c'est le verdict, pas un oubli** -- grave par
`test_929_savage_killer_offline.py::test_create_valid_active_ability_trigger_est_dead_code`.

================================================================================================
LES SURCHARGES -- tranchees a l'ADRESSE DE LA CIBLE D'APPEL, jamais a l'oeil
================================================================================================
Les octets des trois `Create*` ont ete lus (`read_bytes`) et les `call rel32` resolus EN CODE. Ce
n'est pas un luxe : le pseudo-C ghidra **efface** les immediats passes a `op_Implicit`, et il y en a
deux ici, dans DEUX espaces d'enum DIFFERENTS.

  * `CreateCharacterActiveAbilityTrigger+0x092` -> `0x18166a000` =
    `IdunBattle.Core.AbilityOrEffect$$op_Implicit(activeAbility: ActiveAbilityType)`, immediat
    `mov edx, 0x467` = **1127 = `ActiveAbilityType.ArmouredMight_Move`**.
    ⚠ CE N'EST PAS `this`. Le voisin de forme (`MartialSuperiority`, `CursedPlagueBell`) ecrit un
    `TriggeringAbilityIs`/`CurrentAbilityIs` sur SA PROPRE ability ; ici l'immediat designe une AUTRE
    ability, et dans l'espace `ActiveAbilityType` (ou 1159 vaut `MacroPlasmaIncinerator`, pas
    `SavageKiller`). Recopier le voisin aurait ecrit un id faux ET un enum faux.
  * `CreateBehaviour+0x15e` -> `0x181669f80` =
    `$$op_Implicit(triggeredAbility: TriggeredAbilityType)` -- l'`AbilityOrEffect` du behaviour, lui,
    EST bien `this.Id` en `TriggeredAbilityType`. Les deux call-sites de la MEME classe utilisent donc
    DEUX surcharges differentes.
  * `CreateBehaviour+0x1e2` -> `0x180ea0d70` = la surcharge
    `AttackWithAttackDamage(caster, target, amount: IAmountFormula, damageProfile:
    Nullable<DamageProfileType>, hits: **System.Int32**, abilityOrEffect, options, selectionType)`
    (sur les CINQ homonymes). `hits` est donc la CONSTANTE de config, pas une formule.
  * `CreateSummonMoveTrigger+0x13f` / `+0x190` -> `0x180ed5360` =
    `AmountIsGreaterThanZero(amount: **ITargetsSelector**)` -- pas la surcharge `IAmountFormula`
    (`0x180ed52d0`) : le predicat teste que le SELECTEUR rend au moins une tuile.
  * `CreateCharacterActiveAbilityTrigger+0x10b` -> `0x180ed95a0` = `IsOverwatchAttack()` **sans
    argument** (la surcharge `(ability)` est `0x180ed95f0`).
  * `+0x069` -> `0x180ed76b0` = `IsActiveAbilityCountedAsUsed`, avec `mov dl, 1` : la branche
    `isPreAbilityTrigger = **true**`, seuil `DSLFormulas@+0x18 = Direct(0)` -- l'AUTRE branche de
    celle que porte `FuelledByFury` (`false`, seuil `+0x20 = Direct(1)`).

================================================================================================
CE QUE LE PORT MATERIALISE, ET CE QU'IL NE PEUT PAS
================================================================================================
UNE SEULE classe pour les deux faces, et c'est le natif qui l'impose : il n'y a qu'UNE
`SavageKillerAbility`, donc UN compteur `GetTimesTriggeredThisPhase` (le cap de phase de
`EvaluateTriggerOperation$$EvaluateAbilityTrigger`, porte par `dispatch/core.py` sous la cle
`type(entry).__name__`). Deux classes Python donneraient DEUX compteurs. La repartition des quatre
evenements entre `event_id` et `event_ids` est de la PLOMBERIE du dispatch, pas une donnee native.

RESIDUS EXPLICITES -- chacun est une MESURE, pas une supposition :

 * **`On(UnitBecameTargetable = 0x3b)` : AUCUN EMETTEUR cote port.** Aucun site n'construit ce
   `TriggerEvent` (balayage `EventTriggerType.UnitBecameTargetable` sur `engine/**` : 0 occurrence
   hors mirror d'enum). La 4e disjonction est donc INATTEIGNABLE, et avec elle les deux seuls
   consommateurs de `PreviousTile` / `TurnStartTile` de cette ability. L'evenement n'est PAS dans
   `event_ids` : l'y mettre materialiserait un predicat (`NOT moved`) qu'aucun montage ne peut
   exercer -- port speculatif. Residu **#929-r1**.
 * **`NOT IsReplacedUnit(Target, OnlyAliveAndTargetable)`** (branche `On(UnitAdded)`) =
   `UnitHasSpawnSourceTrigger(unit, SpawnSource.**Replace** = 7, sel)`. Le mirror
   `engine/entities/spawn_source.py` existe, mais **aucune entite du runner ne porte de
   `spawn_source`** : il n'est lu que par l'emetteur de flux (`stream_helper.py`) et par
   `game_setup.py`. Le terme est donc laisse PASSER. La degradation est SURE et mesurable : aucun
   chemin de `operations/spawn.py` ne cree d'unite par remplacement -- tous les spawns portes sont
   des `SpawnSource.Ability`. Residu **#929-r2**.
 * **`NOT IsOverwatchAttack()`** : STRUCTURELLEMENT satisfait cote port. `IsOverwatchAttack()` =
   `TriggeringAbilityIs(AbilityOrEffect{Effect = EffectType.Overwatch_AutoAttack = 0x3f1})`
   (RE relue dans `entities/effects/loki/inescapable_death.py` Sec.3, meme build), et le tir
   d'overwatch du port n'emet PAS `On(PreUnitAbility)` : il appelle `AttackDamageOperation`
   directement sans traverser le niveau MESSAGE (cf. `damage_ops/normal.py`, commentaire du site
   `On(9)`/`On(10)`). Le seul emetteur du vecteur est donc une attaque normale ou un cast -- jamais
   un overwatch. MEME traitement que le `NOT IsDirectTargetAttack(@0x140)` de `MartialSuperiority`.
 * **`NOT TriggeringAbilityIs(ActiveAbilityType.ArmouredMight_Move)`** : materialise ci-dessous sur
   le canal `ev.triggering_effect` (le port n'a qu'UN canal pour le slot `DSLSelectors+0x90`, comme
   le natif), en TRI-ETAT -- `None` = canal vide sur ce vecteur, le terme passe. INERTE aujourd'hui
   pour une raison mesuree et plus forte que le canal : **`ArmouredMight` n'a AUCUN porteur dans le
   gameconfig** (0 unite l'expose en active ou en passive) et `ArmouredMight_Move` n'y a meme pas
   d'entree d'ability. Le terme est ecrit pour que le nœud natif soit CITE et morde le jour ou l'un
   des deux manques est comble.
 * **`IsActiveAbilityCountedAsUsed(true)`** delegue au foyer UNIQUE
   `fuelled_by_fury.is_active_ability_counted_as_used`, etendu ici du parametre
   `is_pre_ability_trigger` (le seuil `Direct(0)` de la branche `true`). Son volet `!IsNormalAttack`
   est ce qui rend le passif AVEUGLE a l'attaque normale -- c'est lui qui porte le << active ability >>
   de l'i2, et c'est la seule des deux faces a l'avoir (cf. le piege des gates asymetriques).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....dsl.effects import ExecutionContext
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.selectors.accessors import Target
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....components import OwnerComponent, UnitComponent, previous_tiles as _previous_tiles
from ....state import State
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.targeting import is_targetable
from ..base import TriggeredAbility, TriggerEvent, _unit_tile, _unit_trait_names
from . import fuelled_by_fury as _fbf      # forme MODULE (#485-r1-r1) : le foyer reste substituable

ABILITY_ID = "SavageKiller"                                  # cle gameconfig (minDmg/maxDmg/nrOfHits)
SAVAGE_KILLER = int(TriggeredAbilityType.SavageKiller)       # 0x487 = 1159
#: `AbilityConfiguration.GetDamageProfile()` -> `constants.damageProfile = "Power"`. RELU au
#: decompile (l'i2 << Power Damage >> n'est qu'une corroboration), comme l'exige la doctrine.
DAMAGE_PROFILE = DamageProfileType.Power.name                # "Power"
#: `HasTrait(Target@+0x60, 2)` -- `UnitTrait.Summon`.
_SUMMON = UnitTrait(int(UnitTrait.Summon)).name              # 2 -> "Summon"
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)  # 0x2a = 42
_ON_AFTER_MOVE = int(EventTriggerType.UnitAfterMove)         # 0x04 = 4
_ON_DISPLACED = int(EventTriggerType.UnitDisplaced)          # 0x23 = 35
_ON_UNIT_ADDED = int(EventTriggerType.UnitAdded)             # 0x32 = 50
#: 4e disjonction de `CreateSummonMoveTrigger`, ABONNEE depuis #981 (residu #929-r1) : son vecteur
#: existe depuis #936 (`move_death.unit_became_targetable_triggers`, emis par
#: `remove_effect_instance` sous le gate de type `UntargetableEffect`).
_ON_UNIT_BECAME_TARGETABLE = int(EventTriggerType.UnitBecameTargetable)   # 0x3b = 59
#: L'immediat `mov edx, 0x467` du `TriggeringAbilityIs` de `CreateCharacterActiveAbilityTrigger`,
#: dans l'espace `ActiveAbilityType` (surcharge `op_Implicit` resolue a l'adresse `0x18166a000`).
_ARMOURED_MIGHT_MOVE = int(ActiveAbilityType.ArmouredMight_Move)          # 0x467 = 1127


def savage_killer_tree():
    """Arbre de `...SavageKillerAbility$$CreateBehaviour` -- MIRROR 1:1 :

        AttackWithAttackDamage(Owner@+0x30, <target>, RandomAmount(minDmg, maxDmg),
                               Nullable(Power), nrOfHits = 5, AbilityOrEffect(1159), null, 2)

    Le selecteur de cibles natif est `Caster@DSLSelectors+0x48` sur la face B et `Target@+0x60` sur
    la face A -- DEUX slots, mais UN SEUL `AttackWithAttackDamage`, et les deux ne rendent qu'UNE
    entite. Le port fait converger les deux dans le slot `target` de l'`AbilityEntities` qu'il batit
    (`entities_from_state(state, owner, victime, victime)`), et lit ce slot par le nœud `Target()`
    (`entities/selectors/accessors.py`, `factory+0x178`). Le CHOIX du slot natif, lui, n'est pas
    dilue : il vit dans `SavageKillerAbility._victim_id`, foyer unique, qui mirroir a la fois le
    `if (triggerType == 0x2a)` de `CreateBehaviour` et le `ConditionalSelector` de
    `$$GetInitialTarget`. MEME collapse, MEME raison et MEME forme que `MartialSuperiority`
    (`Actor()` + `multi=False`), qui porte le patron jumeau.

    `multi=False` = collapse MONO-CIBLE (`Units(Cache(First(Nearest(...))))` du natif) : les deux
    slots ne portent qu'UNE entite.

    `is_melee=True` : `BaseTriggeredAbility$$GetAttackRangeType` rend `config@+0x20`, et le
    gameconfig de `SavageKiller` porte `attackRangeType: "Melee"`. `level_slot="passive"` :
    `SavageKiller` est une passiveAbility, donc `minDmg`/`maxDmg` s'indexent au niveau PASSIF.
    `native_factory` reste le defaut "attack" (la factory native est bien `AttackWithAttackDamage`,
    pas `AttackWithAbilityDamage`)."""
    return AttackWithAttackDamage(Target(), ABILITY_ID, DAMAGE_PROFILE,
                                  is_melee=True, level_slot="passive")


class SavageKillerAbility(TriggeredAbility):
    """`SavageKillerAbility` (triggered 0x487 = 1159, passif `spaceWulfen`) -- cf. l'en-tete.

    UNE classe, QUATRE evenements, DEUX faces :
      * FACE A `On(UnitAfterMove | UnitDisplaced | UnitAdded)` -- un SUMMON ennemi adjacent bouge,
        est pousse, ou apparait -> Ulf le frappe (5 coups Power) ;
      * FACE B `On(PreUnitAbility)` -- un ennemi adjacent tente un ACTIF -> Ulf frappe SON CASTER,
        AVANT que l'ability ne s'execute.

    L'observable de la face B ne tient pas qu'a l'ordre d'emission : si les 5 coups TUENT le caster,
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` re-teste la mort du caster JUSTE
    APRES `On(0x2a)` et `return 0` -- l'ability entrante n'a JAMAIS lieu. Ce gate est deja porte sur
    les deux voies (#133), donc la pre-emption est acquise sans rien ajouter ici.

    ⚠ LES DEUX FACES N'ONT PAS LA MEME GATE, ET C'EST NATIF : la face A gate sur le TRAIT de la
    victime (`Summon`) sans rien exiger de la nature de l'action ; la face B gate sur la NATURE de
    l'ability (`IsActiveAbilityCountedAsUsed`, donc pas une attaque normale) sans rien exiger du
    trait du caster. Recopier la gate d'une face sur l'autre eteindrait exactement une face sur deux.
    """
    #: Le natif n'a qu'UN `CreateTrigger` -- la repartition entre les deux attributs est de la
    #: plomberie du dispatch (`dispatch/core.py` teste `event_id` PUIS `event_ids`). `event_id`
    #: porte `PreUnitAbility` pour que les recenseurs qui lisent ce seul attribut (probe #281) voient
    #: l'abonnement le plus consequent.
    event_id = _ON_PRE_UNIT_ABILITY
    event_ids = (_ON_AFTER_MOVE, _ON_DISPLACED, _ON_UNIT_ADDED, _ON_UNIT_BECAME_TARGETABLE)
    #: `AbilityOrEffect((TriggeredAbilityType)1159)` -- ce que `BaseTriggeredAbility$$Execute` ecrit
    #: dans `CurrentAbility` (`AbilityEntities+0x60`) AVANT le behaviour.
    TRIGGERED_ABILITY_ID = SAVAGE_KILLER

    # -------------------------------------------------------------------------------- la cible
    @staticmethod
    def _victim_id(ev: TriggerEvent):
        """`CreateBehaviour` : `target = (triggerType == 0x2a) ? Caster@+0x48 : Target@+0x60`, et
        `GetInitialTarget` = `ConditionalSelector(On(0x2a), Caster@+0x48, Target@+0x60)` -- le MEME
        choix, ecrit deux fois par le natif. Foyer unique du port.

        Cote port, le vecteur `On(PreUnitAbility)` est construit par
        `dispatch/ability.py::pre_unit_ability_triggers(state, caster_id, target_id, ...)` : son
        `actor_id` EST le caster de l'ability declenchante (= `Caster@+0x48`). Les trois vecteurs de
        la face A posent tous la victime en `target_id` (`after_move_triggers` : `(mover, mover)` ;
        `displace_triggers` : `(pusher, pushed)` ; `on_unit_added` : `(added, added)`)."""
        if int(ev.event_id) == _ON_PRE_UNIT_ABILITY:
            return ev.actor_id
        return ev.target_id

    # -------------------------------------------------------------------------------- le trigger
    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` (doctrine des triggers). Chaque terme cite son nœud natif.

        L'ORDRE des conjoints suit le decompile branche par branche ; les deplacer n'a aucun effet
        observable (tous les predicats sont PURS -- aucun ne consomme de RNG ni ne mute l'etat), et
        les trois conjoints COMMUNS aux quatre disjonctions sont donc factorises en queue."""
        owner = state.get_entity(self.owner_id)
        vid = self._victim_id(ev)
        if owner is None or vid is None or int(vid) == int(self.owner_id):
            return False
        victim = state.get_entity(int(vid))
        if victim is None:
            return False
        if int(ev.event_id) == _ON_PRE_UNIT_ABILITY:
            if not self._active_ability_face(state, ev, int(vid)):
                return False
        elif not self._summon_move_face(state, victim):
            return False
        elif (int(ev.event_id) == _ON_UNIT_BECAME_TARGETABLE
                and self._has_moved(state, victim)):        # `NOT moved`, 4e disjonction SEULE
            return False
        return self._enemy_and_adjacent(state, owner, victim, int(vid))

    # ------------------------------------------------------------------------------- face A / B
    @staticmethod
    def _summon_move_face(state: State, victim) -> bool:
        """Le conjoint PROPRE aux QUATRE branches de `CreateSummonMoveTrigger` :
        `HasTrait(Target@+0x60, UnitTrait.Summon = 2)`.

        Le terme `NOT IsReplacedUnit(Target, 3)` de la branche `On(UnitAdded)` n'est PAS teste :
        `SpawnSource` n'est porte par aucune entite du runner (residu #929-r2, cf. l'en-tete). Il
        n'est pas non plus reecrit ici en gate approximatif -- un `False` invente eteindrait la
        branche spawn, qui est justement celle que l'i2 nomme (<< or is summoned adjacent >>)."""
        return _SUMMON in _unit_trait_names(state, victim.id)

    @staticmethod
    def _has_moved(state: State, victim) -> bool:
        """`moved` = le conjoint PROPRE a la 4e disjonction, et a ELLE SEULE (#981 / residu #929-r1) :

            AmountIsGreaterThanZero( PreviousTile(Target@+0x60) )
          | AmountIsGreaterThanZero( TurnStartTile(Target@+0x60) )

        La branche entiere est `On(0x3b) & hasSummon & adjacent & enemies & NOT moved` : un summon
        qui DEVIENT ciblable **sans avoir bouge** -- typiquement une sortie d'`UntargetableEffect`
        (deep-strike / infiltration) sur place, par opposition a un summon qui s'est deplace jusqu'a
        Ulf (deja couvert par `On(UnitAfterMove)`, d'ou l'exclusion : sans elle, un meme deplacement
        pourrait declencher DEUX fois).

        LES DEUX SUBSTRATS SONT DEJA PORTES, et chacun mirroir le `Select` de SON selecteur :
          * `PreviousTile` -> `runner/components.py::previous_tiles` (mirror de
            `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select` : `PositionComponent+0x88`,
            `Nullable` vide -> liste VIDE) ;
          * `TurnStartTile` -> `UnitComponent.current_turn_start_tile` (mirror du champ
            `UnitComponent+0x18c` qu'ecrit `IdunBattle.Operations.StartTurnOperation$$Execute` ;
            `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select` rend une liste VIDE
            quand il vaut 0).

        `AmountIsGreaterThanZero(<selecteur>)` porte donc sur le CARDINAL de la liste rendue : les
        deux termes sont vrais des que leur selecteur rend au moins une tuile. Le tri-etat de
        `current_turn_start_tile` (`None` = non mesure OU 0, cf. `snapshot.py`) retombe du bon cote :
        liste vide -> terme FAUX -> `NOT moved` vrai, exactement ce que rend le natif sur un champ a
        zero. Degradation PERMISSIVE et NOMMEE : une unite dont le canal n'a pas parle est traitee
        comme n'ayant pas bouge ce tour."""
        if victim is None:
            return False
        if _previous_tiles(victim):                          # AmountIsGreaterThanZero(PreviousTile)
            return True
        uc = victim.get_component(UnitComponent)
        tile = getattr(uc, "current_turn_start_tile", None) if uc is not None else None
        return bool(tile)                                    # AmountIsGreaterThanZero(TurnStartTile)

    def _active_ability_face(self, state: State, ev: TriggerEvent, caster_id: int) -> bool:
        """Les conjoints PROPRES de `CreateCharacterActiveAbilityTrigger`, hors adjacence/equipe."""
        # `IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = true)` -- `mov dl, 1` LU aux octets.
        # Son volet `!IsNormalAttackOrHealOrRepair(CurrentAbility)` est ce qui EXCLUT l'attaque
        # normale : c'est lui, et lui seul, qui porte le << active ability >> du texte i2. Le volet
        # de seuil (`used > 0` sur CETTE branche) reste inerte faute de compteur observable, cf. le
        # foyer.
        if not _fbf.is_active_ability_counted_as_used(state, caster_id, ev.ability_type,
                                                      is_pre_ability_trigger=True):
            return False
        # `NOT TriggeringAbilityIs(AbilityOrEffect((ActiveAbilityType)1127 = ArmouredMight_Move))`.
        # Canal = `ev.triggering_effect`, le SEUL canal du port pour le slot `DSLSelectors+0x90`
        # (`$$TriggeringAbilityIs` / `$$TriggeringEffectIs` / `$$TriggeringAbilityIsNone` le
        # partagent, cf. `triggers/base.py`). TRI-ETAT : `None` = canal VIDE sur ce vecteur -> le
        # terme passe, ce qui est le sens du natif (comparer a un `Nullable` vide rend faux, donc
        # le `NOT` rend vrai).
        # ⚠ Le port collapse les QUATRE champs de l'`AbilityOrEffect` natif en UN entier : un
        # `TriggeredAbilityType 1127` (`SeekerMissileFrequencyLock_Attack`) arrivant par ce canal
        # serait confondu avec l'`ActiveAbilityType 1127` compare ici. Inerte aujourd'hui (le canal
        # n'est pas renseigne sur ce vecteur), nomme pour que ca ne surprenne pas.
        if ev.triggering_effect is not None and int(ev.triggering_effect) == _ARMOURED_MIGHT_MOVE:
            return False
        # `NOT IsOverwatchAttack()` : structurellement satisfait cote port -- le tir d'overwatch
        # n'emet pas `On(PreUnitAbility)` (cf. l'en-tete). Non materialise, documente.
        return True

    # -------------------------------------------------------------- conjoints COMMUNS aux 4 branches
    def _enemy_and_adjacent(self, state: State, owner, victim, victim_id: int) -> bool:
        """`AreEnemies(Owner@+0x30, X, ByCurrentTeam = 0)` puis
        `IsAdjacent(Owner@+0x30, X, OnlyAliveAndTargetable = 3)` -- les DEUX faces posent ces deux
        nœuds, sur leur slot respectif (`Target@+0x60` pour A, `Caster@+0x48` pour B)."""
        ooc = owner.get_component(OwnerComponent)
        voc = victim.get_component(OwnerComponent)
        if ooc is None or voc is None or ooc.team == voc.team:
            return False
        # `OnlyAliveAndTargetable` filtre les DEUX selecteurs. Le gate << owner vivant >> est deja
        # applique par le dispatch (`CanGetAbilityTrigger`) ; restent le volet VIVANT de la victime
        # et le volet CIBLABLE des deux (`UnitExtensions$$IsTargetable` = `!HasFlag(0x11)`), non
        # trivial ici : un summon fraichement pose peut arriver non ciblable.
        vuc = victim.get_component(UnitComponent)
        if vuc is not None and not vuc.alive:
            return False
        if not (is_targetable(state, self.owner_id) and is_targetable(state, victim_id)):
            return False
        board = state.board
        if board is None:
            return False                    # predicat POSITIONNEL : sans plateau, il ne resout rien
        ot = _unit_tile(state, board, self.owner_id)
        vt = _unit_tile(state, board, victim_id)
        return ot is not None and vt is not None and vt in set(board.neighbours(ot))

    # -------------------------------------------------------------------------------- le behaviour
    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        victim_id = int(self._victim_id(ev))
        # `AbilityEntities` du behaviour : caster = `Owner@+0x30` (Ulf porte l'attaque), target = la
        # victime resolue par le `ConditionalSelector`. `actor` la reflete, comme sur l'evenement.
        entities = entities_from_state(state, self.owner_id, victim_id, victim_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        savage_killer_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        return {"ability": ABILITY_ID, "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None),
                "event": int(ev.event_id), "dsl": True}
