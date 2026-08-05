"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EmpyricAmbush_ResetAbility` (TriggeredAbilityType
0x613 = **1555**) — quand `eldarLhykhis` ACHEVE un ennemi d'une attaque NORMALE au CONTACT, son
ability active `EmpyricAmbush` (1232) est **re-armee**. `#589-r1-r1-r1-r1`.

REGISTRE (comment cette triggered arrive sur Lhykhis) — `idun.Idun.Source.Shared.Battle.
StaticBattleRules.StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` : dict statique
`ActiveAbilityType -> List<TriggeredAbilityType>` peuple par `...ActiveAbility$$.cctor`. Entree LUE
au decompile : **`0x4d0 (1232 EmpyricAmbush) -> ToList(0x613 = 1555 EmpyricAmbush_Reset)`** (un seul
element). C'est le MEME chemin que `Hailstrike` (1214 -> 1507) : posseder l'ACTIVE fait porter la
triggered DES L'INIT de l'unite, sans aucun cast prealable. Cote port : registre
`ACTIVE_ABILITY_TRIGGERS` (`dispatch/registry.py`), cle = le NOM gameconfig de l'ability active.
`...StaticBattleRules.TriggeredAbility$$.cctor` ajoute par ailleurs `dict[0x613] = 0x4d0` au dict
`GetActiveAbilityUsedForConfig` (statics+0x48) : 1555 lit la CONFIG de 1232 -- sans consequence ici,
son behaviour ne lit aucune variable.

TRIGGER — `...EmpyricAmbush_ResetAbility$$CreateTrigger` (MIRROR 1:1 du decompile, dans l'ordre) :

    On(0x36 = UnitDefeated, 1)
  & get_OwnerIsActor                                    # AreEqual(Owner@+0x30, Actor@+0x40)
  & AreEnemies(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60, 0 = ByCurrentTeam)
  & IsNormalAttack(<DSLSelectors+0x90>)
  & IsMeleeAttack(<DSLSelectors+0x90>)

`<DSLSelectors+0x90>` = le slot **`TriggeringAbility`** (`AbilityEntities+0x98`), celui que prennent
`$$TriggeringAbilityIs` / `$$TriggeringEffectIs` / `$$TriggeringAbilityIsNone` (case-292 §1.1) --
PAS `<+0x88>` (`CurrentAbility`), qui est le defaut des surcharges a UN argument
(`DSLTriggers$$IsNormalAttack(this)` -> `<+0x88>`). Les deux noeuds prennent donc, ici, **l'ability du
COUP LETAL**, et pas l'ability courante.

BEHAVIOUR — `...EmpyricAmbush_ResetAbility$$CreateBehaviour(abilityState, triggerType)` :

    ResetActiveAbility( Owner@DSLSelectors+0x30, allowUseless: 1 )

⚠ Ce corps est **DEDUPLIQUE** par IL2CPP : la table de symboles l'attribue a
`...TacticalPrecision_ResetAbility$$CreateBehaviour` (corps identique, aucun litteral distinctif), et
`EmpyricAmbush_ResetAbility$$CreateBehaviour` n'y apparait PAS. Il a ete retrouve par la table de
pointeurs de methodes des deux classes (groupes de 3 : `.ctor` partage, `CreateTrigger`,
`CreateBehaviour`) -- exactement le faux negatif que le `CLAUDE.md` decrit (« l'ABSENCE d'une methode
dans les tables ne prouve RIEN »). `BaseTriggeredAbility$$CreateBehaviour` (le corps de base) n'est
qu'un forward vers le slot de vtable `+0x2f8`, donc une classe SANS override recurserait a l'infini :
l'override existe forcement.

`IdunBattleLogic.Entities.DSLBehaviors$$ResetActiveAbility(units, allowUseless)` alloue un
`IdunBattle.Entities.Behaviours.ResetActiveAbilityBehaviour(units, allowUseless & 0xff)` ->
`IdunBattle.Operations.ResetActiveAbilityOperation$$Execute(unit, flag)`. Le litteral du 2e argument
est **1** (`CONCAT71(..., 1)` du decompile), la ou `InspiredToGreatnessAbility$$ExecuteBehaviour`
passe **0** : il fait sauter le gate de tour de
`IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` (`if (ignoreTurnFlag) return
true` des qu'une ability est en cooldown), ce qui est necessaire ici -- Lhykhis vient d'agir, donc son
`UnitFlag.TurnFinished` peut deja etre pose quand la mort est drainee.

FRONTIERE DSL/IMPERATIF (#149) — le behaviour est un noeud `DSLBehaviors` : il est porte comme un
ARBRE (la feuille `ResetActiveAbility`, `abilities/behaviours/ability_state.py`), qui delegue au
mutateur imperatif `ResetActiveAbilityOperation`. Le predicat du trigger est COLLAPSE dans `matches`,
comme tous les triggers portes (doctrine SuppressiveFire #74).

LES DEUX NOEUDS D'ATTAQUE, ET LEUR CANAL COTE PORT
--------------------------------------------------
`IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack(this, sel)` batit la DISJONCTION
`AbilityIsNormalAttackTrigger(sel) | <noeud kind>(sel, Direct(AbilityOrEffect 0x3f5))`, deja portee
par `abilities/attack_type.py::is_normal_attack`.

`IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack(this, sel)` alloue un
`IsMeleeAttackAbilityTrigger(state, query, logger, sel, 0, 0, 0)` (MEME `.ctor` que son frere
`IsRangedAttackAbilityTrigger` -- corps deduplique ; les deux classes ne different que par le slot
d'`IBattleQuery` invoque a la fin de leur `ShouldTrigger`, 2 = melee / 3 = ranged), et son
`ShouldTrigger` finit par :

    IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)

dont le corps, RELU au decompile, est :

    if (!ability.HasValue)                                    return false
    switch (GetAbilityAttackRangeType(ability)) :             # AttackRangeType (enums.tsv)
        0 None   -> false
        1 Melee  -> true
        2 Ranged -> false
        3 Normal -> !UnitExtensions.HasFlag(caster, 0x15 = ForceRangedAttack)
                    && AreEntitiesAdjacent(casterPosition, target)
        _        -> throw NotImplementedException

CANAL COTE PORT — la valeur comparee est l'`AbilityOrEffect` du COUP LETAL. Sur le vecteur MORT, le
natif la prend dans `AbilityEntities+0x98`, que `KillUnitOperation$$Execute` recopie depuis
`KillUnitOptions+0x04` -- c'est-a-dire le `killTrigger` que `RecordKillOperation$$Execute` a passe a
`MatchState$$AddDeath` (coalesce des deux `Nullable<AbilityOrEffect>` du `KillUnitContext`, lu au
decompile).

Le port a DEUX canaux candidats, et un seul est renseigne sur une attaque NORMALE :

  * `state.trigger_ability_type` (#301) -- alimente par `_add_death` depuis `state.triggering_ability`,
    donc **VIDE** des que la mort ne vient pas du behaviour d'une triggered-ability. Sur une attaque
    normale il vaut `None`, et le gate ne pourrait JAMAIS passer ;
  * `UnitComponent.death_source[2]` -- le `Nullable<AbilityOrEffect>` de la `DamageSource`
    (`UnitComponent+0x108`), ecrit par `_record_death_reason` (mirror de
    `IdunBattle.Operations.KillUnitOperation$$RecordDeathReason`) **AVANT** `On(PreUnitDeath)`, donc
    lisible pendant tout le vecteur mort. Sa valeur est celle qu'a resolue `_damage_source_ability`
    (mirror `GetDamageSourceAbility`), soit `0x3f5 = 1013` sur la voie normale du port.

C'est le SECOND qui est lu ici : les deux natifs derivent de la MEME `DamageSource` du coup letal, et
c'est le seul des deux canaux portes qui soit renseigne sur le regime que cette ability vise. Absent
(`None`) -> gate FAUX, jamais permissif.

RESIDUS NOMMES
--------------
* `GetAbilityAttackRangeType` : le natif le lit dans la base d'abilities (`abilitiesDb[type].<slot
  0xf>`). Cote port l'oracle est le gameconfig (`abilities.<id>.attackRangeType`), et les attaques
  normales n'ONT PAS d'entree gameconfig (`Loki_NormalAttack`, `PrecisionShot_Attack` -> `None`) :
  on retombe alors sur `AttackRangeType.Normal` (3), la seule valeur compatible avec une unite qui
  porte a la fois une arme de melee et une arme a distance. Le gate `IsNormalAttack` etant CONJOINT
  a celui-ci sur le MEME selecteur, la valeur evaluee est toujours une attaque reguliere.
* `AreEntitiesAdjacent(casterPosition, target)` est evalue au moment du DRAIN de la mort, pas au
  moment du coup. Les deux coincident tant que le tueur n'a pas bouge entre les deux (aucun chemin
  porte ne le fait : le drain est non reentrant et suit immediatement l'application du degat).
"""
from __future__ import annotations

from typing import Optional

from .....battle_query import are_entities_adjacent
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors import Owner
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours import ResetActiveAbility, entities_from_state
from ....components import (OwnerComponent, PositionComponent, UnitComponent,
                            UnitFlagsComponent)
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
from .....entities.unit_flag import UnitFlag   # #270-r1-r1-r3

#: Cle du registre `ACTIVE_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability ACTIVE porteuse
#: (`units.activeAbilities`), ici `ActiveAbilityType 0x4d0 = 1232`.
EMPYRIC_AMBUSH_ABILITY = "EmpyricAmbush"
EMPYRIC_AMBUSH_RESET = int(TriggeredAbilityType.EmpyricAmbush_Reset)      # 0x613 = 1555

#: `IdunBattle.Entities.Enum.UnitFlag` 21 = `ForceRangedAttack` (enums.tsv, verbatim) -- le seul flag
#: lu par la branche `Normal` de `BattleQuery$$IsMeleeAttack`. Pas de constante dans
#: `UnitFlagsComponent` : le litteral est cite ici avec son nom d'enum.
_FORCE_RANGED_ATTACK = UnitFlag.ForceRangedAttack


class AttackRangeType:
    """`IdunBattle.Entities.Enum.AttackRangeType` (dump il2cpp, enum VERBATIM) -- la valeur rendue par
    `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType`."""
    NoRange = 0        # `None` dans l'enum natif (mot reserve en Python)
    Melee = 1
    Ranged = 2
    Normal = 3


def _team_of(state: State, uid: Optional[int]):
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _pos_of(state: State, uid: Optional[int]):
    e = state.get_entity(uid) if uid is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _kill_trigger(state: State, dying_id: Optional[int]) -> Optional[int]:
    """L'`AbilityOrEffect` du COUP LETAL, telle que le vecteur mort la porte dans
    `AbilityEntities+0x98` (`TriggeringAbility`, slot `DSLSelectors+0x90`).

    Canal porte = `UnitComponent.death_source[2]` (`Nullable<AbilityOrEffect>` de la `DamageSource`
    @`UnitComponent+0x108`, ecrite par `_record_death_reason` AVANT `On(PreUnitDeath)`). Cf. l'en-tete
    de module pour pourquoi ce n'est PAS `state.trigger_ability_type`. `None` = canal absent -> les
    deux noeuds qui le lisent rendent FAUX."""
    e = state.get_entity(int(dying_id)) if dying_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    ds = getattr(uc, "death_source", None) if uc is not None else None
    if not ds or len(ds) < 3:
        return None
    return None if ds[2] is None else int(ds[2])


def _ability_attack_range_type(ability_or_effect: Optional[int]) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(abilityOrEffect)` -- le natif
    resout l'`AbilityOrEffect` (active / triggered / effet) puis lit `abilitiesDb[type].<slot 0xf>`.

    Oracle porte = la constante `attackRangeType` de la config d'ability (gameconfig). Une attaque
    NORMALE n'a pas d'entree gameconfig -> `AttackRangeType.Normal`, cf. le residu en tete de module.
    """
    if ability_or_effect is None:
        return AttackRangeType.NoRange
    import gameconfig as _GC
    from .....entities.active_ability_type import ActiveAbilityType
    try:
        name = ActiveAbilityType(int(ability_or_effect)).name
    except ValueError:
        name = None
    cfg = (_GC.ability(name) or {}) if name else {}
    v = cfg.get("attackRangeType")
    if v == "Melee":
        return AttackRangeType.Melee
    if v == "Ranged":
        return AttackRangeType.Ranged
    if v == "Normal":
        return AttackRangeType.Normal
    return AttackRangeType.Normal      # pas de config (attaque normale) -> branche `Normal`


def _is_melee_attack(state: State, ability_or_effect: Optional[int],
                     caster_id: Optional[int], target_id: Optional[int]) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)`
    -- MIRROR du decompile (les quatre branches du switch sont dans l'en-tete de module)."""
    if ability_or_effect is None:                       # `if (!ability.HasValue) return false`
        return False
    rt = _ability_attack_range_type(ability_or_effect)
    if rt == AttackRangeType.Melee:
        return True
    if rt in (AttackRangeType.NoRange, AttackRangeType.Ranged):
        return False
    # --- AttackRangeType.Normal : le flag du caster, puis l'adjacence -------------------------
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    if fl is not None and fl.has(_FORCE_RANGED_ATTACK):   # HasFlag(caster, 0x15)
        return False
    cpos, tpos = _pos_of(state, caster_id), _pos_of(state, target_id)
    if cpos is None or tpos is None:
        return False
    board = state.board
    neigh = elev = None
    if board is not None:
        neigh, _walk, elev = board.walk_maps_by_pos()
    return are_entities_adjacent(cpos, tpos, elev, neigh)   # AreEntitiesAdjacent


class EmpyricAmbushResetAbility(TriggeredAbility):
    """`EmpyricAmbush_ResetAbility` (triggered 0x613 = 1555) -- cf. l'en-tete de module pour l'arbre
    natif complet. `owner_id` = l'unite qui POSSEDE l'ability active 1232 (`eldarLhykhis`), instanciee
    par le registre `ACTIVE_ABILITY_TRIGGERS` (mirror `GetDerivedTriggeredAbilities`).

    OBSERVABLE : apres avoir caste `EmpyricAmbush`, Lhykhis a son actif consomme
    (`usable: false` cote `decisionView.units[].abilities`). Des qu'elle ACHEVE un ennemi d'une
    attaque NORMALE au CONTACT, l'actif redevient utilisable (`usable: true`, `cooldown: null`)."""
    event_id = int(EventTriggerType.UnitDefeated)        # On(0x36 = 54, 1)
    TRIGGERED_ABILITY_ID = EMPYRIC_AMBUSH_RESET

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # --- get_OwnerIsActor : AreEqual(Owner@+0x30, Actor@+0x40) ----------------------------
        # Sur `On(UnitDefeated)` l'ACTEUR est le TUEUR (`AbilityEntities+0x00/+0x08 = killer`, ecrit
        # par `KillUnitOperation$$Execute`). Tueur inconnu -> le slot natif est nul -> `AreEqual` est
        # faux : on lit `ev.killer_id`, pas `ev.actor_id` (que le vecteur rabat sur le mourant).
        killer = ev.killer_id
        if killer is None or int(killer) != int(self.owner_id):
            return False
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None:
            return False
        # --- AreEnemies(Owner@+0x30, Target@+0x60, 0 = ByCurrentTeam) --------------------------
        mine, theirs = _team_of(state, self.owner_id), _team_of(state, dying)
        if mine is None or theirs is None or mine == theirs:
            return False
        # --- IsNormalAttack(<DSLSelectors+0x90 = TriggeringAbility>) ---------------------------
        kt = _kill_trigger(state, dying)
        if not is_normal_attack(kt):
            return False
        # --- IsMeleeAttack(<DSLSelectors+0x90>) ------------------------------------------------
        return _is_melee_attack(state, kt, self.owner_id, dying)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`CreateBehaviour` = `ResetActiveAbility(Owner@DSLSelectors+0x30, allowUseless: 1)` --
        ARBRE DSL (feuille `ResetActiveAbility` -> `ResetActiveAbilityOperation`)."""
        ectx = ExecutionContext(state=state, rng=state.rng)
        ResetActiveAbility(Owner(), True).execute(
            entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id), ectx)
        reset = [p for n, p in ectx.emitted if n == "ResetActiveAbility"]
        if not reset:
            return None
        return {"ability": "EmpyricAmbush_Reset", "owner": int(self.owner_id),
                "killed": None if ev.dying_id is None else int(ev.dying_id),
                "reset": reset}
