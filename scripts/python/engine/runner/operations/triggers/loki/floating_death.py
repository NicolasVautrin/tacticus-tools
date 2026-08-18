"""Cluster FLOATING-DEATH — le passif `FloatingDeath` (`TriggeredAbilityType` 0x4db = 1243) des deux
Spore Mines tyranides : le summon `tyranSmnSporeMine` (spawne par `BioMinefield`,
`SporeMineLauncher` du MoW `tyranBiovore` et `HyperCorrosiveAcid`) et le npc `tyranNpc6SporeMine`.

UNE entree de `passiveAbilities` au gameconfig, **CINQ classes natives** -- c'est la forme du
cluster, et elle ne se devine pas : elle se lit dans `frida/classes.tsv` (les quatre premieres
derivent de `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, la cinquieme d'
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`).

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_InitAbility
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_AttackAbility
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_ChainAbility
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_ExtraMovementAbility
    IdunBattleLogic.Entities.Abilities.Active.Loki.FloatingDeath_NormalAttackAbility   (1146, ACTIVE)

⚠ L'AUDIT classait ce passif ZONE-GRISE parce que son NOM est reference en code hors de tout
registre de passifs. La mesure tranche : **la 5e face etait portee, les quatre autres non**.
`engine/services/custom_normal_attack.py::CUSTOM_NORMAL_ATTACK_BY_PASSIVE["FloatingDeath"]` est un
CABLAGE reel (la mine attaque avec `1146` et non `69 Loki_NormalAttack`), et `1146` porte son
`TARGETING_OPTIONS` + son appartenance a `REGULAR_ATTACK_ABILITY_TYPES`. Mais `1243` n'etait dans
AUCUN des sept registres de `dispatch/registry.py` : la DETONATION, la CHAINE et le MOUVEMENT
SYNAPSE ne s'executaient pas -- ce que trois docstrings du port disaient deja
(`runner/abilities/tyranids.py` : << le spore mine spawne est INERTE offline >>).

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (decompile = verite, build `rnca9r7q6c` ; symboles verbatim)
--------------------------------------------------------------------------------------------------

1. `...FloatingDeath_InitAbility$$CreateBehaviour` = `DSLBehaviors$$AddTrait(Owner@DSLSelectors+0x30,
   0x41a = 1050 UnitTrait.PermaDeath, isTemporary = 0)`. `CreateTrigger` HERITE de
   `BaseTriggeredAbility` = `<DSLTriggers+0x30>` = `On(0x21 = AbilityInit) & <Yes@+0x70> &
   get_OwnerIsActor` (meme forme que `TerrorsLamentAbility` / `HealingBalms`).
   **NON RECABLEE, ET C'EST MESURE, pas un renoncement** : (a) `PermaDeath` est DEJA dans les traits
   STATIQUES du kit des DEUX porteurs (`gameconfig.units.<id>.traits` =
   `['Summon','InstinctiveBehaviour','Flying','PermaDeath']` pour `tyranSmnSporeMine`,
   `['InstinctiveBehaviour','Flying','PermaDeath']` pour `tyranNpc6SporeMine`), donc l'`AddTrait`
   natif est IDEMPOTENT sur tout porteur reel -- observable NUL ; (b) le runner ne rejoue pas
   `On(AbilityInit)`, il charge un etat ou le natif l'a DEJA joue (meme doctrine que
   `runner/abilities/genestealer.py` et `runner/abilities/loki/healing_balms.py`). Une classe de
   port ici n'ajouterait aucun observable et exigerait un vecteur d'evenement qui n'existe pas.

2. `...FloatingDeath_AttackAbility$$CreateTrigger` =
       `On(0x2 = PreUnitDeath_2, ownerNeedsToBeAlive = 0)`
       op_BitwiseAnd `get_OwnerIsTarget`
       op_BitwiseAnd op_LogicalNot(`TargetIsOverkilled`)
   `...$$CreateBehaviour` =
       `DSLBehaviors$$AttackWithAbilityDamage(
            caster  = Owner@DSLSelectors+0x30,
            target  = DSLSelectors$$AdjacentEnemies(Owner, unique = 1, selectionType = 3),
            amount  = BaseTriggeredAbility$$MinMaxDamage(this, abilityState)
                      = DSLFormulas$$RandomAmount(GetVariableForLevel(0xc = minDmg),
                                                  GetVariableForLevel(0xd = maxDmg)),
            profile = DSLSelectors$$DamageProfileFromConfig(config),
            hits    = DSLFormulas$$Direct(AbilityConfiguration$$GetNumberConstant(config,
                                                                    0x2f = nrOfHits)),
            src     = AbilityOrEffect(this),
            selectionType = 2 )`
   => LA DETONATION. Quand la mine meurt SANS overkill, elle explose sur ses ennemis ADJACENTS
   (`minDmg`-`maxDmg` au profil `Toxic`, `nrOfHits` coups).
   ⚠ CONTRASTE LU avec le cluster DEATH-NOVA (`loki/death_nova.py`), qui ecoute le MEME evenement :
   les deux novas passent par le helper `OnPreDeath2(a = 1, ...)`, donc SANS gate overkill -- elles
   partent MEME EN OVERKILL. FloatingDeath, lui, construit son `On(2)` a la main et ajoute
   explicitement `NOT TargetIsOverkilled` : un overkill ETEINT la detonation. Copier death_nova
   aurait ete faux.
   ⚠ `AdjacentEnemies` ici est la surcharge A (`(this, unit, unique, selectionType)`) -- le 3e
   argument est un `CONCAT71(., 1)`, donc un BOOLEEN, pas une entite : ce n'est PAS la surcharge B
   `(this, unit, unitTile, unique)`. `selectionType = 3 = OnlyAliveAndTargetable`.

3. `...FloatingDeath_ChainAbility$$CreateTrigger` =
       `On(0x0 = UnitDeath, ownerNeedsToBeAlive = 1)`
       op_BitwiseAnd op_LogicalNot(`TargetIsOverkilled`)
       op_BitwiseAnd `AreFriends(Target@DSLSelectors+0x60, Owner@+0x30,
                                 comparisonType = 0 = ByCurrentTeam, anyEntity = 0)`
       op_BitwiseAnd `IsAdjacent(Target@+0x60, Owner@+0x30, selectionType = 0 = Any)`
       op_BitwiseAnd `AreEqual(DSLFormulas$$VisualUnitIdFromUnit(Target@+0x60),
                               DSLFormulas$$VisualUnitIdFromUnit(Owner@+0x30))`
   `...$$CreateBehaviour` = `DSLBehaviors$$Kill(killer = DSLSelectors$$Killer(Target@+0x60),
                                                targets = Owner@+0x30, options = 1)`
   => LA REACTION EN CHAINE. Quand une AUTRE mine du MEME visualId, de la MEME equipe courante et
   ADJACENTE meurt (hors overkill), cette mine-ci meurt aussi, imputee au TUEUR de la premiere --
   ce qui re-declenche sa propre detonation (face 2) par `On(2)`.

4. `...FloatingDeath_ExtraMovementAbility$$CreateTrigger` =
       `On(0x13 = TurnStart_Other, ownerNeedsToBeAlive = 1)`
       op_BitwiseAnd `<DSLTriggers+0x28 = IsTurnOf(Owner)>`
       op_BitwiseAnd `IsInTeamSynapseRange(Owner@+0x30, Owner@+0x30)`
   `...$$CreateBehaviour` = `DSLBehaviors$$AddStaticStatModifierEffectToOwner(
       0x522 = 1314 EffectType.FloatingDeath_ExtraMovement, 0x1 = StatType.Movement,
       DSLFormulas$$Direct(1), turns = 1, isHidden = 0)`
   => +1 MOUVEMENT au debut de son propre tour tant qu'elle est dans la bulle synapse de son equipe.
   ⚠ `IsInTeamSynapseRange` = `IsInAuraRangeTrigger(state, query, effectType = 0x41c, target, team)`
   et `0x41c` est un **`EffectType`** (1052 `Synapse_Effect`), PAS un `UnitTrait` -- l'ordinal 1052
   nomme `Ambush` dans `UnitTrait`. La signature du ctor est LUE (`IsInAuraRangeTrigger.cs`,
   `.ctor(IMatchState, IBattleQuery, EffectType, ITargetsSelector, ITargetsSelector)`).
   ⚠ `<DSLTriggers+0x28>` est identifie `IsTurnOfUnitTrigger(Owner, state)` par
   `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (le champ y est construit avec le couple
   `(Owner@DSLSelectors+0x30, dsl.state@+0x10)`, et `IsTurnOfUnitTrigger` est le SEUL trigger du
   binaire dont le ctor a cette forme). MEME lecture que `SereneUnifier` / `RelentlessMarch`.

5. `...FloatingDeath_NormalAttackAbility` (ACTIVE 1146) -- DEJA PORTEE, hors de ce module :
   substitution d'attaque normale (`services/custom_normal_attack.py`), masque de ciblage
   (`runner/abilities/targeting.py`) et `is_regular_attack` (`runner/abilities/attack_type.py`).

--------------------------------------------------------------------------------------------------
CONFRONTABILITE
--------------------------------------------------------------------------------------------------
`tyranSmnSporeMine` est un SUMMON : hors `--list-pool`, mais atteignable en spawnant son summoner --
`tyranBiovore` est dans le pool des MoW (`SporeMineLauncher` 1145, dont l'ability EST portee,
`runner/abilities/handler.py`). On OBSERVE la mine, on ne la COMMANDE pas (#291).

CONSTANTES -- ZERO HARDCODE : `gameconfig.units.abilities.FloatingDeath`
(`constants.damageProfile = Toxic`, `constants.nrOfHits = 1`, `variables.minDmg`/`maxDmg`, 65
paliers, les deux dans `variablesAffectedByRarityBonus`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.combat import AttackWithAbilityDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect
from ....abilities.behaviours.lifecycle import Kill
from ....components import OwnerComponent, PositionComponent, UnitComponent
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Actor, Owner
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentEnemies
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsInTeamAura
from .....entities.unit_selection_type import UnitSelectionType
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state
from .....services import battle_query as _sbq   # FORME B (liaison de MODULE). Arete GRATUITE
#     (#485) : `import engine.services.battle_query` en process frais ne charge pas ce module.

#: Le NOM gameconfig du passif -- la config que lisent les DEUX faces a magnitude (2 et 4).
FLOATING_DEATH = TriggeredAbilityType.FloatingDeath.name              # "FloatingDeath"
#: `AbilityOrEffect(this)` : les quatre classes natives sont instanciees depuis LA MEME entree de
#: `passiveAbilities`, donc portent le meme `AbilityType` (meme forme que `MyWillBeDoneOverlord`,
#: deux classes de port pour un seul id 1556).
FLOATING_DEATH_ID = int(TriggeredAbilityType.FloatingDeath)           # 0x4db = 1243
#: `AddStaticStatModifierEffectToOwner(0x522, ...)` -- l'effet pose par la face MOUVEMENT.
EXTRA_MOVEMENT_EFFECT = int(EffectType.FloatingDeath_ExtraMovement)   # 0x522 = 1314
#: `IsInTeamSynapseRange` = `IsInAuraRangeTrigger(..., effectType = 0x41c, ...)` -- un `EffectType`.
SYNAPSE_EFFECT = int(EffectType.Synapse_Effect)                       # 0x41c = 1052
#: 4e argument LU d'`DSLSelectors$$AdjacentEnemies(unit, unique, selectionType)`.
_ADJACENT_ENEMIES_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)   # 3
#: 3e argument LU d'`DSLTriggers$$IsAdjacent(a, b, selectionType)` de la face CHAINE.
_CHAIN_ADJACENCY_SELECTION = int(UnitSelectionType.Any)                       # 0


def _floating_death_config() -> tuple:
    """`AbilityConfiguration$$GetDamageProfile(config)` + `GetNumberConstant(config, 0x2f)`.

    Rend `(profile, nrOfHits)` ; `(None, 0)` si la config manque -> l'appelant se tait (aucune
    magnitude inventee, meme degradation que `death_nova._putrid_variables`)."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour ses classes. (Meme raison, meme forme que
    # `the_lantern_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(FLOATING_DEATH) or {}).get("constants") or {}
    profile = str(consts.get("damageProfile") or "")
    hits = int(consts.get("nrOfHits") or 0)
    return (profile or None), hits


def floating_death_attack_tree(state: "State", level: Optional[int], multiplier_pct: int,
                               profile: str, hits: int):
    """Arbre de `...FloatingDeath_AttackAbility$$CreateBehaviour` -- MIRROR 1:1 du decompile (SS2).

    `level`/`multiplier_pct` = l'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage(this,
    abilityState)` consomme, resolu par l'appelant sur le PORTEUR via le foyer UNIQUE
    `triggers/base.py::triggered_ability_state` (etat PASSIF pour un kit de summon/npc).

    `AdjacentEnemies(Owner, unique = 1, selectionType = 3)` : le port ancre le disque sur
    `CasterTile()` -- `entities_from_state` pose caster == owner pour une triggered-ability, et
    l'equivalence `Units(AdjacentTiles(x), ., .) - x` == `AdjacentUnits(tuile de x, 1)` est celle
    que `death_nova` a deja LUE au decompile. Le filtre d'equipe (`team != caster`) est dans le
    selecteur porte, comme dans le natif (`Enemies(unit, ...)` interne).

    `is_melee = None` : le natif ne passe AUCUN `attackRangeType` a ce noeud (pas d'`InformWeapon`,
    le profil vient de `DamageProfileFromConfig`), donc la nature du coup n'est pas PROUVEE -- meme
    lecture que `the_lantern_attack_tree`. Les deux gates `IsMeleeAttack` / `IsRangedAttack` rendent
    alors FAUX, ce qui est fidele. (Le `attackRangeType: Melee` de l'entree gameconfig gouverne
    l'attaque NORMALE 1146, pas ce noeud.)

    `multi = True` : le selecteur resout N unites. `native_operation = "ability"` : la detonation
    passe par `AbilityDamageOperation` (percage du profil + mods DEFENSEUR, aucun crit)."""
    mn = ability_var(FLOATING_DEATH, "minDmg", level, multiplier_pct=multiplier_pct) or 0
    mx = ability_var(FLOATING_DEATH, "maxDmg", level, multiplier_pct=multiplier_pct) or 0
    targets = AdjacentEnemies(Caster(), Const(1), selection_type=_ADJACENT_ENEMIES_SELECTION)
    amount = RandomAmount(Const(int(mn)), Const(int(mx)), rng=state.rng)
    return AttackWithAbilityDamage(targets, profile, amount, is_melee=None, hits=int(hits),
                                   source_ref=Owner(),        # `Owner@DSLSelectors+0x30`
                                   multi=True,
                                   native_operation="ability",
                                   ability_type=FLOATING_DEATH_ID)


def floating_death_chain_tree():
    """Arbre de `...FloatingDeath_ChainAbility$$CreateBehaviour` -- MIRROR 1:1 (SS3) :

        `DSLBehaviors$$Kill(killer = DSLSelectors$$Killer(Target@+0x60), targets = Owner@+0x30, 1)`

    `Killer(Target)` est resolu par l'appelant, qui pose `actor_id = ev.killer_id` dans
    l'`AbilityEntities` -- meme cablage que `death_nova` (`actor_id=ev.killer_id`). Le tueur peut
    etre `None` : le natif l'admet aussi (`<+0x58>.Select(entities, 8)` peut rendre null, cf. la
    docstring de la feuille `Kill`)."""
    return Kill(Actor(), Owner())


def floating_death_extra_movement_tree():
    """Arbre de `...FloatingDeath_ExtraMovementAbility$$CreateBehaviour` -- MIRROR 1:1 (SS4) :

        `AddStaticStatModifierEffectToOwner(0x522, StatType.Movement, Direct(1), turns = 1, 0)`

    La factory `...ToOwner` passe `source = targets = Owner@DSLSelectors+0x30` (les deux memes),
    donc la feuille generique `AddStaticStatModifierEffect` en est le mirror exact (cf. sa
    docstring, #890-r2). Le 4e argument natif est un `int turns` LITTERAL (surcharge
    `(EffectType, StatType, IAmountFormula, int, bool)` lue dans `DSLFactory.cs`), donc
    `duration_turns = 1` -- pas un `TurnsFromRounds`."""
    return AddStaticStatModifierEffect(Owner(), EXTRA_MOVEMENT_EFFECT, int(StatType.MOVEMENT),
                                       Const(1), name=EffectType.FloatingDeath_ExtraMovement.name,
                                       duration_turns=1)


class FloatingDeathAttackAbility(TriggeredAbility):
    """`FloatingDeath_AttackAbility` -- LA DETONATION (SS2 de l'en-tete).

    Trigger = `On(2 = PreUnitDeath_2, ownerNeedsToBeAlive = 0) & get_OwnerIsTarget &
    NOT TargetIsOverkilled`. `fire_on_death = True` : l'owner EST le mourant, deja `alive = False`
    au dispatch -> bypass du gate << owner vivant >> de `CanGetAbilityTrigger`.

    ⚠ Le gate overkill est ICI, dans le TRIGGER, et il est EXPLICITE (`op_LogicalNot(
    TargetIsOverkilled)`) -- a la difference des deux novas de `death_nova.py`, qui passent
    `a = 1` a `OnDeathEvent` et partent donc MEME en overkill."""
    event_id = EventTriggerType.PreUnitDeath_2                # 0x2
    fire_on_death = True
    TRIGGERED_ABILITY_ID = FLOATING_DEATH_ID                  # 0x4db = 1243

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:       # `get_OwnerIsTarget` (Target@+0x60 = le mourant)
            return False
        return not ev.overkill                 # `op_LogicalNot(TargetIsOverkilled)`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        profile, hits = _floating_death_config()
        if not profile or hits <= 0:
            return None                        # config absente -> aucune magnitude inventee
        level, mult = triggered_ability_state(state, int(self.owner_id), FLOATING_DEATH)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `caster = Owner@+0x30`, `target = le mourant` (== l'owner ici), `actor = le tueur`.
        entities = entities_from_state(state, self.owner_id, self.owner_id,
                                       actor_id=ev.killer_id)
        floating_death_attack_tree(state, level, mult, profile, hits).execute(entities, ectx)
        # LES ETAGES du coup, pas seulement son total (meme diag que `the_lantern_attack`).
        dmg = [{"target": p.get("target"), "total": p.get("total"),
                "etages": {k: (a or {}).get(k) for k in
                           ("base_min", "base_max", "pierce", "armor", "did_block", "rolls",
                            "per_hit", "hp_before", "hp_after")}}
               for n, p in ectx.emitted if n == "AttackWithAbilityDamage"
               for a in [p.get("attack")]]
        if not dmg:
            return None                        # aucun ennemi adjacent -> no-op, rien a rapporter
        return {"ability": FLOATING_DEATH, "face": "detonation", "owner": int(self.owner_id),
                "level": level, "multiplier": mult, "profile": profile, "hits": int(hits),
                "damage": dmg, "on_event": ev.event_id}


class FloatingDeathChainAbility(TriggeredAbility):
    """`FloatingDeath_ChainAbility` -- LA REACTION EN CHAINE (SS3 de l'en-tete).

    Trigger = `On(0 = UnitDeath, ownerNeedsToBeAlive = 1) & NOT TargetIsOverkilled &
    AreFriends(Target, Owner, ByCurrentTeam, anyEntity = 0) & IsAdjacent(Target, Owner, Any) &
    AreEqual(VisualUnitIdFromUnit(Target), VisualUnitIdFromUnit(Owner))`.

    Les cinq conjoints sont collapses IMPERATIVEMENT dans `matches` -- c'est la forme du port pour
    un `CreateTrigger` (le registre est indexe par `event_id`, cf. `dispatch/registry.py`), la meme
    que `Hailstrike` / `SereneUnifier` / `death_nova`. Les DEUX predicats geometriques passent par
    des foyers deja portes : `IsAdjacent` par le noeud DSL homonyme (`entities/triggers.py`, qui
    delegue a `battle_query.are_tiles_adjacent` -- porte d'elevation comprise), `AreFriends` par
    l'egalite d'equipe COURANTE (`OwnerComponent.team`, mirror de `GetCurrentTeamId`).

    `fire_on_death = False` : `ownerNeedsToBeAlive = 1` -- la mine qui reagit doit etre VIVANTE."""
    event_id = EventTriggerType.UnitDeath                     # 0x0
    TRIGGERED_ABILITY_ID = FLOATING_DEATH_ID                  # 0x4db = 1243

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dying = ev.dying_id
        if dying is None or int(dying) == int(self.owner_id):
            return False                       # `Target@+0x60` = une AUTRE unite (le mourant)
        if ev.overkill:                        # `op_LogicalNot(TargetIsOverkilled)`
            return False
        me = state.get_entity(int(self.owner_id))
        other = state.get_entity(int(dying))
        if me is None or other is None:
            return False
        muc = me.get_component(UnitComponent)
        ouc = other.get_component(UnitComponent)
        if muc is None or ouc is None or not muc.alive:
            return False                       # `On(0, ownerNeedsToBeAlive = 1)`
        moc, ooc = me.get_component(OwnerComponent), other.get_component(OwnerComponent)
        if moc is None or ooc is None or int(moc.team) != int(ooc.team):
            return False                       # `AreFriends(., ., ByCurrentTeam, anyEntity = 0)`
        if muc.visual_id is None or muc.visual_id != ouc.visual_id:
            return False                       # `AreEqual(VisualUnitIdFromUnit x2)`
        mp, op_ = me.get_component(PositionComponent), other.get_component(PositionComponent)
        if mp is None or op_ is None:
            return False
        # `IsAdjacent(Target@+0x60, Owner@+0x30, selectionType = 0 = Any)` -- le 3e argument va au
        # SELECTEUR, pas au predicat, et les deux selecteurs rendent ici UNE unite chacun : le
        # `forall` du noeud se reduit donc a l'unique paire. Foyer : `battle_query.are_tiles_adjacent`
        # via le meme service que le noeud DSL homonyme (porte d'elevation + court-circuit d'identite).
        _ = _CHAIN_ADJACENCY_SELECTION         # 0 = Any -- litteral natif, QUALIFIE
        return bool(_sbq.are_tiles_adjacent((op_.col, op_.row), (mp.col, mp.row),
                                            board=getattr(state, "board", None)))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `Killer(Target@+0x60)` -> `actor_id` ; `targets = Owner@+0x30` -> caster == owner.
        entities = entities_from_state(state, self.owner_id, ev.dying_id, actor_id=ev.killer_id)
        floating_death_chain_tree().execute(entities, ectx)
        killed = [p.get("killed") for n, p in ectx.emitted if n == "Kill"]
        if not any(killed):
            return None
        return {"ability": FLOATING_DEATH, "face": "chain", "owner": int(self.owner_id),
                "triggered_by": int(ev.dying_id), "killer": ev.killer_id, "killed": killed,
                "on_event": ev.event_id}


class FloatingDeathExtraMovementAbility(TriggeredAbility):
    """`FloatingDeath_ExtraMovementAbility` -- +1 MOUVEMENT SOUS SYNAPSE (SS4 de l'en-tete).

    Trigger = `On(0x13 = TurnStart_Other, ownerNeedsToBeAlive = 1) &
    <DSLTriggers+0x28 = IsTurnOf(Owner)> & IsInTeamSynapseRange(Owner, Owner)`.
    Vecteur porte : `turn_start_other_triggers` (`dispatch/turn.py`), emis par
    `StartTurnOperation.execute` -- MEME patron que `SereneUnifier` / `RelentlessMarch` /
    `CursedPlagueBell`, et `IsTurnOf(Owner)` s'y lit `ev.player_id == OwnerComponent.player`.

    Le troisieme conjoint passe par le noeud DSL `IsInTeamAura` (`entities/triggers.py`), qui
    delegue a `battle_query.is_in_team_aura_range` -- le FOYER, avec son etage de portee dans
    `entities/effects/aura.py` (`SynapseEffect$$GetTrait` = `UnitTrait.Synapse`,
    `$$GetCurrentRange` = `Direct(2)`). Aucun predicat n'est re-derive ici."""
    event_id = EventTriggerType.TurnStart_Other               # 0x13 = 19
    TRIGGERED_ABILITY_ID = FLOATING_DEATH_ID                  # 0x4db = 1243

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        e = state.get_entity(int(self.owner_id))
        if e is None:
            return False
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:    # `On(0x13, ownerNeedsToBeAlive = 1)`
            return False
        oc = e.get_component(OwnerComponent)
        if oc is None or ev.player_id is None or int(oc.player) != int(ev.player_id):
            return False                       # `<DSLTriggers+0x28> = IsTurnOf(Owner)`
        # `IsInTeamSynapseRange(target = Owner@+0x30, team = Owner@+0x30)` -- les DEUX selecteurs
        # sont l'owner (lu au decompile : le meme `*(dsl.Selectors + 0x30)` passe deux fois).
        entities = entities_from_state(state, self.owner_id, None)
        return bool(IsInTeamAura(Caster(), SYNAPSE_EFFECT, Caster()).should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                        # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None)
        floating_death_extra_movement_tree().execute(entities, ectx)
        posed = [(p.get("effect_type"), p.get("unit"), p.get("amount"))
                 for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not posed:
            return None                        # deja porte (gate d'idempotence de l'Operation)
        return {"ability": FLOATING_DEATH, "face": "extra_movement", "owner": int(self.owner_id),
                "stat_mods": posed, "on_event": ev.event_id}
