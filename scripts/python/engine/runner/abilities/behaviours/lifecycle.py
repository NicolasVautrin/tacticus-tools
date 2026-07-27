"""Feuilles DSL de fin-de-vie d'unite runner-couplees : `KillDeadUnits` (`KillUnitBehaviour`, finalise les
DOWNED), `RemoveUnit` (`RemoveUnitBehaviour`, despawn sans on-death) et `TriggerAbility`
(`TriggerAbilityBehaviour`, declenchement DIRECT d'une ability TRIGGERED sur un set d'unites). Namespace
natif `Entities.Behaviours.*`.

C'est ICI qu'atterrira le sous-systeme REVIVE (7 variantes en-place/once/at-position, transverse
case-220)."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import UnitComponent


class KillDeadUnits(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$KillDeadUnits` = `IdunBattleLogic.Entities.DSLFactory$$Kill(subject, DownedUnits(units_sel), options)`
    -> `IdunBattle.Entities.Behaviours.KillUnitBehaviour$$Execute` : pour chaque unite DOWNED (flag 0xf, via
    `DownedUnits`=`UnitsWithFlagSelector(units_sel, 0xf, want=1) IdunBattleLogic.Entities.DSLFactory$$DownedUnits`) NON exemptee (le natif skippe
    `HasFlag(9|6|0x1a)`), emet une Operation de KILL (finalise la mort : retrait + on-death). Args natifs
    (ThunderousAssault) : `subject_sel` = Caster() (+0x160), `units_sel` = Target() (+0x178), options =
    `ForClearDeadUnitsBlockReviveOverkill`.

    Role natif : la mort y est DIFFEREE -- l'attaque « DOWN » la cible (PV<=0, flag 0xf) sans la retirer ; ce
    KillDeadUnits POST-push finalise le cadavre pour que `MoveUnit` trouve la tuile libre meme quand l'attaque
    a TUE la cible.

    Chez NOUS : la mort est finalisee INLINE dans l'attaque (`AttackDamageOperation` : `uc.alive=False` +
    death-triggers, cf. damage.py:152) et les morts ne comptent PAS dans l'occupation (`_occupied`/`CanAddUnit`
    excluent `not alive`). Donc a ce point une cible tuee est DEJA finalisee (alive=False, hors-occupation,
    on-death fire) -> ce volet est OBSERVABLEMENT un NO-OP : re-emettre un kill DOUBLE-FIRE les on-death. La
    feuille MIRROR donc la STRUCTURE (filtre DownedUnits LIVE) SANS re-muter -- elle journalise les downed pour
    le replay-diff. (Si notre modele de mort passait un jour en DIFFERE, l'Operation de kill viendrait ICI.)
    `MoveUnit` trouve la tuile libre via l'occupation LIVE (morts exclus) -> l'ordre natif est respecte sans
    mutation redondante. Filtre DOWNED lu en LIVE (`UnitComponent.alive`) et NON sur le dict snapshot (fige a
    l'etat PRE-attaque -> alive=True meme pour une cible tuee par l'attaque). PUR."""
    __slots__ = ("subject_sel", "units_sel")

    def __init__(self, subject_sel: TargetsSelector, units_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        downed: list = []
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None or state is None:
                continue
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None and not uc.alive:          # DOWNED live (flag 0xf) ; mort deja finalisee inline
                downed.append(uid)
        ectx.emit("KillDeadUnits", downed=downed)        # mirror structurel : pas de re-mutation (double-fire)
        return OperationResult.ok()


class RemoveUnit(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$RemoveUnit` -> `IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute` : RETIRE de la
    bataille chaque unite du selecteur — un DESPAWN, PAS une mort (i2 MV71 : « the one with the lowest
    Health is REMOVED ») : AUCUN vecteur on-death (pas de PreUnitDeath/UnitDefeated, pas d'attribution
    de tueur). Call-sites portes (MV71SniperDroneSquadAttack IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour) : eviction (a)
    `RemoveUnit(Units(Get(tile),1,3))` = le drone occupant la tuile choisie (fallback PickTile) ;
    eviction (b) `RemoveUnit(First(AlreadySpawnedSummonsSortedSelector,1,0))` = le drone le plus faible
    au cap maxSummons.

    Port : marque `alive=False` (libere l'occupation — `_occupied`/`CanAddUnit` excluent les morts) et
    consomme les effets portes par l'unite (l'entite-effet native part avec son porteur). SANS
    death-triggers (difference structurelle avec la mort d'`AttackDamageOperation`). Emet 'RemoveUnit'
    par unite. PUR (stop=False)."""
    __slots__ = ("units_sel",)

    def __init__(self, units_sel: TargetsSelector):
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in sorted((x for x in _units_of(self.units_sel, entities)
                         if isinstance(x, dict) and x.get("id") is not None),
                        key=lambda x: x["id"]):              # ordre de lecture = id
            uid = u["id"]
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None or not uc.alive:
                continue
            uc.alive = False                                 # despawn : PAS de vecteur on-death
            if state.effects is not None:                    # les effets portes partent avec l'unite
                for eff in state.effects.by_unit.get(int(uid), []):
                    eff.consumed = True
            ectx.emit("RemoveUnit", unit=uid)
        return OperationResult.ok()


# Registre des abilities TRIGGERED declenchables DIRECTEMENT par le noeud `TriggerAbility` :
# `TriggeredAbilityType (int) -> callable(state, owner_id) -> dict | None`. VIDE par defaut, et c'est un
# CHOIX documente, pas un oubli : le seul call-site porte (HeraldOfTheApocalypse 1020 -> BattleFatigue
# 0x401) declenche un behaviour dont le gate central N'A AUCUNE SOURCE OFFLINE (cf. `TriggerAbility`).
# Une entree ici DOIT etre integralement sourcable (config gameconfig ou etat runner), sinon elle
# INVENTE la mutation.
TRIGGERED_ABILITY_BEHAVIOURS: dict[int, object] = {}


class TriggerAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$TriggerAbility(targets, abilityType, actor, caster, target,
    <sel4>, groupType, flag)` -> `IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$Execute` : pour
    CHAQUE unite du selecteur `targets_sel` (champ `+0x50`), DECLENCHE l'ability TRIGGERED `ability_type`
    (`+0x58`) avec cette unite pour OWNER -- un declenchement DIRECT, qui court-circuite le `CreateTrigger`
    de l'ability declenchee.

    CHAMPS LUS au ctor (`IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$.ctor`, mapping
    factory->ctor verifie) : `+0x50` targets · `+0x58` abilityType (int) · `+0x60`/`+0x68`/`+0x70`/`+0x78`
    = les quatre selecteurs qui RE-CONSTRUISENT l'`AbilityEntities` passe a l'ability declenchee ·
    `+0x80` groupType (3) · `+0x84` flag. `Execute` resout d'abord ces quatre selecteurs, puis itere
    `targets` et appelle, par unite, le slot d'operation 0x56 avec `(unitId, abilityType, entities, flag)`.

    CALL-SITE PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$
    ExecuteBehaviour` -> `TriggerAbility(Enemies(Owner@0x148, SurroundingUnits(Target@0x178, range, 1, 1,
    3)), 0x401 = TriggeredAbilityType.BattleFatigue, actor@0x158, caster@0x160, target@0x178, null, 3,
    false)`.

    CE QUE LE PORT FAIT, ET CE QU'IL NE FAIT PAS. La partie OBSERVABLE et sourcable -- QUELLES unites sont
    declenchees -- est portee (resolution du selecteur, ordre de lecture = id comme partout ailleurs) et
    emise (`TriggerAbility`, champ `targets`). Le DISPATCH passe par `TRIGGERED_ABILITY_BEHAVIOURS` ; une
    ability absente du registre rend `dispatched: False` -- le gap est VISIBLE (meme doctrine que
    `AbilityHandler.unported`), jamais muet.

    ⚠ `BattleFatigue` (0x401) n'y est PAS, et c'est DELIBERE : `IdunBattleLogic.Entities.Abilities.Active.
    Loki.BattleFatigueAbility$$CreateBehaviour` = `Repeat(numTriggers, If(NOT HasFlag(self, 9),
    Maybe(GetFleeChance, self) -> Flee(...)))`, et `...$$GetFleeChance` = `ConditionalAmount(
    TargetIsOverkilled, Direct(GetNumberConstant(0x33)), Direct(GetNumberConstant(0x2a)))` sur une
    `AbilityConfiguration` ABSENTE du gameconfig (`GC.ability("BattleFatigue")` -> None). La chance n'est
    donc pas sourcable offline : dispatcher reviendrait a faire fuir 0 % ou 100 % des cibles la ou le natif
    tire une piece -- une mutation de POSITION massive et fausse a chaque cast (jusqu'a ~19 unites dans le
    disque rayon 2). On resout et on TRACE le set declenche ; la fuite reste un residu nomme (le meme que
    `runner/operations/behaviour.py` documente deja pour la voie trigger-sur-mort). PUR (stop=False)."""
    __slots__ = ("targets_sel", "ability_type")

    def __init__(self, targets_sel: TargetsSelector, ability_type: int):
        self.targets_sel = targets_sel
        self.ability_type = int(ability_type)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        fn = TRIGGERED_ABILITY_BEHAVIOURS.get(self.ability_type)
        targets = sorted({u["id"] for u in _units_of(self.targets_sel, entities)
                          if isinstance(u, dict) and u.get("id") is not None})
        results = []
        for uid in targets:                                  # ordre de lecture = id (mirror OrderBy)
            results.append(None if fn is None else fn(state, uid))
        ectx.emit("TriggerAbility", ability_type=self.ability_type, targets=targets,
                  dispatched=fn is not None, results=results)
        return OperationResult.ok()
