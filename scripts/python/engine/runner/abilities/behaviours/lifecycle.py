"""Feuilles DSL de fin-de-vie d'unite runner-couplees : `KillDeadUnits` (`KillUnitBehaviour`, finalise les
DOWNED) et `RemoveUnit` (`RemoveUnitBehaviour`, despawn sans on-death). Namespace natif
`Entities.Behaviours.*`.

C'est ICI qu'atterrira le sous-systeme REVIVE (7 variantes en-place/once/at-position, transverse case-220)
et le noeud `TriggerAbility`."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import UnitComponent


class KillDeadUnits(AbilityBehaviour):
    """`DSLFactory.KillDeadUnits @180df5c60` = `Kill(subject, DownedUnits(units_sel), options) @180df5cb0`
    -> `KillUnitBehaviour.Execute @180fc8b10` : pour chaque unite DOWNED (flag 0xf, via
    `DownedUnits`=`UnitsWithFlagSelector(units_sel, 0xf, want=1) @180dee790`) NON exemptee (le natif skippe
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
    """`DSLFactory.RemoveUnit @180df9fd0` -> `RemoveUnitBehaviour.Execute @180fce1d0` : RETIRE de la
    bataille chaque unite du selecteur — un DESPAWN, PAS une mort (i2 MV71 : « the one with the lowest
    Health is REMOVED ») : AUCUN vecteur on-death (pas de PreUnitDeath/UnitDefeated, pas d'attribution
    de tueur). Call-sites portes (MV71SniperDroneSquadAttack @181108900) : eviction (a)
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
