"""`CursedOfTheWalkingPox` -- passif du SUMMON `deathPoxwalker` << Poxwalker >> (Death Guard) et du
npc `deathNpc1Poxwalker`. `TriggeredAbilityType` 0x430 = **1072**.

i2 : « Each time this unit kills an enemy non-Mechanical unit, a Poxwalker is summoned in that hex. »

================================================================================================
QUALIFICATION D'ENUM -- ce N'EST PAS une voie inversee, et l'ordinal ne le dirait pas
================================================================================================
Le NOM vit dans `IdunBattle.Entities.Enum.TriggeredAbilityType` (`1072 = CursedOfTheWalkingPox`) et
le gameconfig le porte en `units.summons.deathPoxwalker.passiveAbilities` : **voie et enum
concordent**. Le namespace natif `...Abilities.**Active**.Loki.CursedOfTheWalkingPoxAbility` n'y
change rien -- il est structurellement non fiable (`AdrenalGlands`, `CloseCombatWeakness`,
`InstinctiveBehaviour_InitAbility` vivent aussi sous `Active` en etant des `TriggeredAbilityType`),
et le parent de la classe le confirme : `frida/classes.tsv` donne
`IdunBattle.Entities.Abilities.**BaseTriggeredAbility**`, tout comme la classe de vue
`CursedOfTheWalkingPoxVisuals` derive d'`IdunBattle.View.AbilityConfigs.APassiveAbilityVisualsBase`.

⚠ **L'ORDINAL, LUI, NOMMERAIT AUTRE CHOSE** : `ActiveAbilityType 1072 = MyWillBeDone`. Lire cet id
dans le mauvais enum ne leverait aucune erreur -- il designerait simplement une autre ability.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
Le gameconfig de `CursedOfTheWalkingPox` est **VIDE** (`{"upgrades": null, "variables": {}}`, aucune
constante) : ni `unitId`, ni `summonHp`/`summonDmg`. C'est ce qui impose `CopyOwner` ci-dessous --
aucun `GetStringConstant` / `WithStatsFromConfig` n'aurait quoi lire.

## `CursedOfTheWalkingPoxAbility$$CreateTrigger`

    On(0x35 = EventTriggerType.PostUnitKill, ignoreOverkill = 0)
  & get_OwnerIsActor
  & AreEnemies(Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>, 0)
  & IsDead(Target@<DSLSelectors+0x60>)
  & NOT TriggeringAbilityIs( AbilityOrEffect(<this ability>) )
  & IsCanAddUnit(Target@<DSLSelectors+0x60>)
  & NOT IsObjectOrSteppable(Target@<DSLSelectors+0x60>)
  & NOT HasTrait(Target@<DSLSelectors+0x60>, 0x5 = UnitTrait.Mechanical)

`IsCanAddUnit(sel)` = `AmountIsEqualOrGreater( CanAddUnit(sel), <DSLFormulas+0x20> = Direct(1) )` =
« AU MOINS UNE tuile de `sel` peut accueillir une unite » (foyer porte
`entities/triggers.py::IsCanAddUnit`, qui tient les deux pieges : la classe reellement allouee est
`AmountIsEqualOrGreater`, pas l'`AmountIsGreater` que ghidra affiche, et `DSLFormulas+0x20` vaut
`Direct(1)` et non `Direct(0)`).

## `CursedOfTheWalkingPoxAbility$$CreateBehaviour`

    options = SpawnUnitOptions.CopyOwner(dsl, abilityState)
    options.<+0x48> = Nullable<bool>(true)                       # finishTurnOnSpawn, override
    options.<+0x40> = Nullable<UnitOverrideType>(2 = Summon)     # overrideType
    return Spawn( parent = Owner@<DSLSelectors+0x30>,
                  tiles  = First( CanAddUnit(TargetTiles@<DSLSelectors+0x78>),
                                  amount = 1, ignoreForcedTargets = 0 ),
                  unitId = UnitIdFromUnit(Owner@<DSLSelectors+0x30>),
                  options )

TROIS lectures, aucune devinee :

1. **`UnitIdFromUnit(Owner)`**, pas `GetStringConstant(config, unitId)` : le Poxwalker invoque est un
   clone du PORTEUR, par son `visualId`. C'est ce qui rend le passif RECURSIF -- le Poxwalker pose
   porte le meme kit, donc le meme passif.
2. **`SpawnUnitOptions$$CopyOwner`**, pas `WithStatsFromConfig` : le corps natif empile CINQ
   `StatModifierFormula(StatAmount(Owner@<DSLSelectors+0x30>, <StatType>, StatPart.Current = 3))`
   (`5 = Health`, `0x10 = FixedArmor`, `0 = Attack`, `1 = Movement`, `0x14 = ExtraHits`) puis
   `CreateSpawnOptions(abilityState, null, null, null)`. Le clone herite donc des stats COURANTES du
   parent, jamais d'une table `summon*`. Foyer porte : `operations/spawn.py::
   _spawn_copy_owner_at_tile` (partage avec `execute_self_replica`, l'autre consommateur natif de
   `CopyOwner`).
3. **Les deux champs d'options ecrits APRES `CopyOwner`**, lus a leurs consommateurs :
   * `+0x48` = le `Nullable<bool>` qu'`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$
     TriggerSpawnedUnitBehaviours` OVERRIDE au calcul `HasTrait(Steppable) ? false :
     !HasTrait(Hero)`. Pose a **true** ici -> le tour du Poxwalker est TERMINE des son apparition.
     **NO-OP pour ce porteur** : un Poxwalker n'est ni `Steppable` ni `Hero`, donc le calcul par
     defaut rendait deja `true`. Le port n'expose pas l'override (cf. la note du foyer) et n'en a
     pas besoin -- ecrit ici parce qu'il est LU.
   * `+0x40` = `overrideType`, transporte tel quel dans `AddUnitOptions+0x08` par
     `SpawnUnitBehaviour$$GetAddUnitOptions`. `IdunBattle.Operations.UnitOverrideType` =
     `{0 = Hero, 1 = NPC, 2 = Summon}` -> l'unite posee est forcee en **Summon**. Le port n'a AUCUN
     modele de ce champ (residu nomme en bas de fiche) ; l'unite qu'il cree est de toute facon
     `ai_controlled` et heritee de l'owner du parent, ce que le natif obtient par ce meme champ.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
`CreateTrigger` COLLAPSE dans `matches` (lectures d'etat : `OwnerIsActor`, `AreEnemies`, `IsDead`,
`HasTrait`), sauf DEUX conjoints qui passent par leurs FOYERS DSL PARTAGES --
`entities/triggers.py::is_object_or_steppable` et `::IsCanAddUnit`. `CreateBehaviour` est un ARBRE
DSL (`First(CanAddUnit(TargetTiles))`) dont la feuille appelle l'Operation portee, sans en reecrire
un etage.

1072 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

RESIDUS NOMMES
  * **`NOT TriggeringAbilityIs(<cette ability>)`** -- le canal `TriggerEvent.triggering_ability` est
    INCONDITIONNELLEMENT VIDE sur le vecteur MORT (`triggers/base.py`, mirror du champ natif
    `AbilityEntities.CurrentAbility` que `KillUnitOperation` ne renseigne pas). Le gate est donc
    ECRIT mais ne peut pas mordre tant que ce canal n'est pas seede -- MEME residu, MEME cause et
    MEME sens de degradation (PERMISSIF) que `#955-r1` chez `PossessionSummonOnKillAbility`.
    Effet reel : le natif empeche une CASCADE (un Poxwalker tue par le spawn d'un autre Poxwalker
    ne re-invoque pas) ; le port, lui, n'a pas de vecteur qui produirait ce cas -- le spawn ne tue
    personne.
  * **`overrideType = Summon`** -- non modelise (le port n'a pas de champ `UnitOverrideType`).
  * **`ignoreOverkill`** du `On(0x35)` : le port ne thread pas ce drapeau sur ce vecteur (meme
    statut que chez `CosmicHorrorOnMoveAbility` et `PossessionSummonOnKillAbility`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import Target, TargetTile
from .....entities.selectors.tiles import CanAddUnit
from .....entities.selectors.units import First, Tiles
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsCanAddUnit, is_object_or_steppable
from ....abilities.behaviours.context import entities_from_state
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ...spawn import SpawnUnitOperation
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig du passif
#: (`units.summons.deathPoxwalker.passiveAbilities`).
ABILITY_ID = "CursedOfTheWalkingPox"
#: `On(0x35 = EventTriggerType.PostUnitKill)`.
_ON_POST_UNIT_KILL = int(EventTriggerType.PostUnitKill)
#: `NOT HasTrait(Target@<DSLSelectors+0x60>, 0x5)`. i2 : « an enemy **non-Mechanical** unit ».
MECHANICAL_TRAIT = UnitTrait.Mechanical                       # 0x5
#: `NOT IsObjectOrSteppable(Target@+0x60)` -- foyer DSL partage (8 call-sites natifs).
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())
#: `IsCanAddUnit(Target@+0x60)` -- le noeud natif recoit le selecteur d'UNITE et
#: `CanAddUnitTileSelector` en resout la tuile ; cote port, `Tiles(..., as_ids=True)` est l'ADAPTEUR
#: DE DOMAINE (position -> id d'entite-tuile) que `CanAddUnit` exige, pas un noeud natif de plus.
#: Meme idiome que `possession.py` (`Tiles(Target(), as_ids=True)` pour `Tiles(Target@+0x60)`).
_IS_CAN_ADD_UNIT = IsCanAddUnit(Tiles(Target(), as_ids=True))


def cursed_of_the_walking_pox_spawn_tiles() -> First:
    """`First( CanAddUnit(TargetTiles@<DSLSelectors+0x78>), amount = 1, ignoreForcedTargets = 0 )`
    -- le TILE-SELECTEUR du `Spawn`, mirror 1:1.

    * `TargetTiles@+0x78` = l'EMPREINTE de la cible (`TargetTilesSelector$$Select` =
      `TargetPosition.Tiles ?? [TargetTile] ?? GetTiles(Target)`), c.-a-d. « that hex » de l'i2 ;
      `Tiles(..., as_ids=True)` n'est que l'ADAPTEUR de domaine vers les ids qu'exige `CanAddUnit`.
    * `CanAddUnit` avec `allow_steppable = False` : le call-site natif est la surcharge a DEUX
      arguments `DSLSelectors$$CanAddUnit(this, tiles)`, dont le corps prend son trigger
      `isSteppable` a `<DSLTriggers+0x48>`... **mais** `CanAddUnitTileSelector$$Select` INVERSE ce
      qu'il recoit (`allowSteppable = !ShouldTrigger`), et `+0x48` porte
      `op_LogicalNot(<YesTrigger>)` -> `ShouldTrigger` FAUX -> `allowSteppable` **VRAI**.
      ⚠ Ce parametre est donc `True` ici, et ce n'est PAS le defaut du port : sans lui, une tuile
      occupee par un `Steppable` (decoy, mine, spore) serait tenue pour occupee alors que le natif
      y pose le Poxwalker. Meme lecture que celle etablie par #955-r2 pour la surcharge a 2
      arguments de `FreeTilesOrAdjacentFreeTiles`.
    * `First(..., 1)` = PRISE EN TETE, **zero tirage** (`PickAtIndexSelector$$Select` :
      `idx < list.Count ? [list[idx]] : []`) -- contrairement au `PickRandomly` de
      `Possession`/`Lakrimae`, ce noeud ne consomme AUCUN flux RNG."""
    return First(CanAddUnit(Tiles(TargetTile(), as_ids=True), allow_steppable=True))


def _team_of(state: State, uid) -> Optional[int]:
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _traits_of(state: State, uid) -> list:
    e = state.get_entity(uid) if uid is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return list(getattr(sc.ctx, "traits", None) or []) if sc is not None else []


class CursedOfTheWalkingPoxSummonAbility(TriggeredAbility):
    """`CursedOfTheWalkingPoxAbility` -- le Poxwalker acheve un ennemi non-mecanique, non-objet :
    un NOUVEAU Poxwalker (clone du porteur, stats `CopyOwner`) apparait sur la tuile du mort.

    OBSERVABLE : `+1 deathPoxwalker` dans l'equipe du porteur, sur l'hex de la victime, avec les PV /
    l'attaque / l'armure / le mouvement / les coups supplementaires COURANTS du porteur."""
    event_id = _ON_POST_UNIT_KILL
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.CursedOfTheWalkingPox)     # 0x430 = 1072
    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -- **VRAI**, LU sur
    #: `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedOfTheWalkingPoxAbility` (`OVERRIDE`,
    #: corps `b0 01 c3` ; entree versionnee `data/symbols/<build>/metadata/allow_for_dead_owner.tsv`).
    #: ⚠ CONCORDANT avec le `CreateTrigger`, qui passe `ownerNeedsToBeAlive = **0**` a
    #: `IdunBattleLogic.Entities.DSLTriggers$$On` (donc `& <DSLTriggers+0x70 = YesTrigger>`, aucun
    #: gate d'aval) et dont le `CreateBehaviour` -- `Spawn(Owner, First(CanAddUnit(TargetTiles),1),
    #: UnitIdFromUnit(Owner), CopyOwner)` -- ne porte AUCUN `If(IsAlive(Owner))` non plus.
    #: CONTRE-EPREUVE, sur un arbre presque identique : `...Active.Loki.PossessionAbility$$
    #: CreateTrigger` a la MEME forme (`On(0x35) & OwnerIsActor & AreEnemies & NOT
    #: IsObjectOrSteppable & NOT TriggeringAbilityIs(self)`) mais passe `ownerNeedsToBeAlive = 1`,
    #: et sa classe vaut FAUX. La valeur ne se DEDUIT donc pas de la forme du trigger : elle se LIT.
    #: Le regime que ca ouvre : un Poxwalker qui acheve un ennemi et meurt dans le MEME echange
    #: (riposte, overwatch) engendre quand meme son clone -- ce que le port refusait. #10015
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : l'ACTEUR d'`On(PostUnitKill)` est le TUEUR (le foyer
        # `damage.py::_kill_unit_operation` construit l'event avec `actor = killer ?? killed`).
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or int(victim) == int(self.owner_id):
            return False
        owner, target = state.get_entity(self.owner_id), state.get_entity(victim)
        if owner is None or target is None:
            return False
        # ⚠ **PAS DE GATE `owner alive` ICI, ET C'EST UNE LECTURE (#10015).** Le port en portait un
        # (« Un acteur mort n'agit pas », #70) qui n'a AUCUNE contrepartie native : `CreateTrigger`
        # passe `ownerNeedsToBeAlive = 0` a `IdunBattleLogic.Entities.DSLTriggers$$On` (donc
        # `& <DSLTriggers+0x70 = YesTrigger>`), ses huit conjonctions ne contiennent aucun
        # `IsAlive(Owner)`, `CreateBehaviour` n'en porte pas non plus, et la classe declare
        # `get_AllowForDeadOwner = TRUE`. Le porteur tue dans le MEME echange que sa victime
        # engendre donc bien son clone. Le seul gate d'identite qui reste est `get_OwnerIsActor`
        # ci-dessus, conjugue a `victim != owner` -- ce qui exclut deja le repli `actor = killed`
        # de `damage.py::_kill_unit_operation` quand aucun tueur n'est renseigne.
        # `IsDead(Target@+0x60)` : la victime doit etre morte. Sur ce vecteur elle l'est par
        # construction ; le noeud est ECRIT parce qu'il est LU (et il mord si un revive l'a annulee
        # -- cf. `case-462-...-r4` : `On(0x35)` est le SEUL des cinq events que la garde revive ne
        # supprime pas, donc une victime REVIVEE traverse ce vecteur VIVANTE).
        tuc = target.get_component(UnitComponent)
        if tuc is not None and tuc.alive:
            return False
        # `AreEnemies(Owner@+0x30, Target@+0x60, 0)`
        o_team, t_team = _team_of(state, self.owner_id), _team_of(state, victim)
        if o_team is None or t_team is None or o_team == t_team:
            return False
        # `NOT TriggeringAbilityIs(<cette ability>)` -- canal VIDE sur le vecteur MORT (residu
        # d'en-tete) : le test est ECRIT, il ne mord que si le canal est seede un jour.
        if (ev.triggering_ability is not None
                and int(ev.triggering_ability) == int(self.TRIGGERED_ABILITY_ID)):
            return False
        entities = entities_from_state(state, self.owner_id, victim)
        # `IsCanAddUnit(Target@+0x60)` : la tuile du mort peut-elle accueillir une unite ?
        if not _IS_CAN_ADD_UNIT.should_trigger(entities):
            return False
        # `NOT IsObjectOrSteppable(Target@+0x60)`
        if _IS_OBJECT_OR_STEPPABLE.should_trigger(entities):
            return False
        # `NOT HasTrait(Target@+0x60, 0x5 = Mechanical)`
        return not has_trait(_traits_of(state, victim), MECHANICAL_TRAIT)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        owner = state.get_entity(self.owner_id)
        ouc = owner.get_component(UnitComponent) if owner is not None else None
        # `UnitIdFromUnit(Owner@<DSLSelectors+0x30>)` : le clone porte le `visualId` du PORTEUR.
        visual = getattr(ouc, "visual_id", None) if ouc is not None else None
        if visual is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, victim, actor_id=ev.actor_id)
        tiles = cursed_of_the_walking_pox_spawn_tiles().evaluate(entities) or []
        # `Spawn(Owner, <tiles>, unitId, CopyOwner(abilityState))` -- feuille -> Operation portee.
        spawned = SpawnUnitOperation.execute_copy_owner_on_tiles(
            state, int(self.owner_id), tiles, str(visual))
        for sid in spawned:
            ectx.emit("SpawnUnit", unit=sid)
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "victim": int(victim),
                "tiles": list(tiles), "unit_id": str(visual), "spawned": spawned}
