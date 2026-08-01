"""Feuilles DSL de fin-de-vie d'unite runner-couplees : `KillDeadUnits` (`KillUnitBehaviour`, finalise les
DOWNED), `RemoveUnit` (`RemoveUnitBehaviour`, despawn sans on-death), `RemoveUnitFromItsTiles`
(`RemoveUnitFromItsTilesBehaviour`, l'unite quitte le PLATEAU sans mourir -- #366-r1),
`RemoveAllForcedAttackTargets` (`RemoveForcedAttackTargetBehaviour`) et `TriggerAbility`
(`TriggerAbilityBehaviour`, declenchement DIRECT d'une ability TRIGGERED sur un set d'unites). Namespace
natif `Entities.Behaviours.*`.

C'est ICI qu'atterrira le sous-systeme REVIVE (7 variantes en-place/once/at-position, transverse
case-220)."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import UnitComponent, MachineComponent, is_machine_of_war


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

    DOCTRINE #149 : cette feuille est la FRONTIERE — au-dessus le selecteur (declaratif), en dessous
    l'Operation imperative. Elle resout donc son selecteur puis DELEGUE, unite par unite, a
    `RemoveUnitOperation.execute` (`runner/operations/remove_unit.py`, mirror
    `IdunBattle.Operations.RemoveUnitOperation$$Execute`) avec `removeEffects=1` — le litteral que
    `RemoveUnitBehaviour$$Execute` passe au slot +6 de l'`OperationProcessor`. C'est l'Operation qui
    porte les gates (`Removed`), la pose du flag `0x1a`, la publication d'`On(0x25 = UnitRemoved)` et
    la consommation des effets, dans l'ORDRE natif. SANS death-triggers (difference structurelle avec
    la mort d'`AttackDamageOperation`). Emet 'RemoveUnit' par unite EFFECTIVEMENT retiree (une unite
    qu'un gate refuse n'est pas journalisee). PUR (stop=False)."""
    __slots__ = ("units_sel",)

    def __init__(self, units_sel: TargetsSelector):
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        from ...operations.remove_unit import RemoveUnitOperation
        for u in sorted((x for x in _units_of(self.units_sel, entities)
                         if isinstance(x, dict) and x.get("id") is not None),
                        key=lambda x: x["id"]):              # ordre de lecture = id
            uid = u["id"]
            res = RemoveUnitOperation.execute(state, int(uid), remove_effects=True)
            if res is not None:
                ectx.emit("RemoveUnit", unit=uid, downstream=res["downstream"])
        return OperationResult.ok()


class RemoveMachine(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$RemoveMachine(factory, sel)` ->
    `IdunBattle.Entities.Behaviours.RemoveMachineBehaviour$$Execute` : resout son selecteur `+0x50`
    (= `caster@0x160` au seul call-site porte) et appelle l'operation
    `IdunBattle.Operations.RemoveMachineOperation$$Execute(entity, removeEffects=1, ...)`.

    L'operation native, lue au decompile : gate `IdunBattle.Entities.EntityExtensions$$IsMachine`
    (une entite qui n'est PAS une machine -> log + retour, aucune mutation), puis
    `RemoveMachineFromPlatform`, remise a zero d'un champ de la plateforme, event `0x2e` portant
    `{0x88: HasFlag(entity, 6)}`, enfin `RemoveEffects(entity)`. **Elle ne detruit pas l'entite et
    ne touche NI `ActiveAbilityComponent` NI les PV** : elle la DETACHE de sa plateforme.

    CE QUE LA MESURE AJOUTE AU DECOMPILE (probe_91, anti-confond a runner de CONTROLE) -- le
    decompile ne dit PAS ce que le detachement rend observable, il fallait le mesurer :
      * `decisionView.mows` continue d'exposer la MoW **avec `usable: true`** sur ses DEUX abilities
        (coherent : le projecteur lit `ActiveAbilityComponent`, intact) -> ce canal ne dit RIEN du
        retrait, et un port qui eteindrait `CanStillBeUsed` fabriquerait un etat natif FAUX ;
      * mais le cast est bel et bien REFUSE : `applyAction` rend `actionConsumed = False`
        (signature du refus silencieux, cf. case-111), la ou le meme cast sur un runner de CONTROLE
        (MoW NON retiree, MEME fenetre cooldown/tour ouverte) rend `actionConsumed = True`.
        C'est `actionConsumed` -- PAS `mutated` -- qui discrimine : 1159 est un poseur d'effets de
        tuile, il ne change ni position ni PV meme quand il passe.

    Port : `MachineComponent.removed = True` (le detachement) + consommation des effets portes
    (`RemoveMachineOperation$$RemoveEffects`). RIEN D'AUTRE -- ni `alive = False`, ni extinction des
    abilities : les deux seraient des inventions que la mesure ci-dessus REFUTE. Le refus de cast
    est pose la ou le natif le pose, en tete d'operation d'ability (`AbilityHandler.
    visit_ActiveAbilityMessage`, gate `machine_removed`). Une entite qui n'est PAS une MoW est
    ignoree, comme le gate natif.

    ⚠ Ce que le port ne materialise PAS : l'event `0x2e` et son tag `0x88` (le port n'a pas de bus
    d'events de plateforme MoW) -- residu nomme, cf. docs/rl/case-91-duty-eternal.md §7.

    CALL-SITE PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$
    ExecuteBehaviour` -> `RemoveMachine(caster@0x160) & Spawn(...)`. Emet 'RemoveMachine'. PUR."""
    __slots__ = ("units_sel",)

    def __init__(self, units_sel: TargetsSelector):
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            if not is_machine_of_war(e):          # gate natif `EntityExtensions$$IsMachine`
                continue
            e.get_component(MachineComponent).removed = True     # `RemoveMachineFromPlatform`
            if state.effects is not None:         # `RemoveMachineOperation$$RemoveEffects`
                for eff in state.effects.by_unit.get(int(uid), []):
                    eff.consumed = True
            ectx.emit("RemoveMachine", machine=int(uid))
        return OperationResult.ok()


class RemoveUnitFromItsTiles(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnitFromItsTiles(unit, removeTileFromUnit)` ->
    `IdunBattle.Entities.Behaviours.RemoveUnitFromItsTilesBehaviour$$Execute`. La signature typee vit
    dans la table VERSIONNEE (`frida/methods.tsv`) : `unit : ITargetsSelector, removeTileFromUnit :
    System.Boolean` -- Ghidra, lui, attribue le `.ctor` du behaviour a un corps DEDUPLIQUE
    (`ResetActiveAbilityBehaviour$$.ctor`), donc ne pas lire la classe dans ce nom.

    `Execute`, MIRROR du decompile (le buffer de retour `OperationResult` est le 1er argument sret,
    d'ou les champs du behaviour lus a `+0x50`/`+0x58`) :

        foreach (unit in _unitSelector(+0x50).Select(entities, groupType = 3))
            processor.<slot 7>(unit, _removeTileFromUnit(+0x58));   // = OperationProcessor$$RemoveUnitFromTiles
        return default(OperationResult);                             // jamais de stop

    DOCTRINE #149 : cette feuille est la FRONTIERE -- au-dessus le selecteur (declaratif), en dessous
    l'Operation imperative. Elle resout donc son selecteur puis DELEGUE, unite par unite, a
    `RemoveUnitFromTilesOperation.execute` (`runner/operations/remove_unit_from_tiles.py`). C'est
    l'Operation qui porte le collapse de l'empreinte et les residus nommes.

    Ordre de lecture = id croissant (meme convention que `RemoveUnit`, dont le selecteur natif est
    resolu par le meme `Select(..., 3)`). Emet 'RemoveUnitFromItsTiles' par unite EFFECTIVEMENT
    retiree de ses tuiles. PUR (stop=False).

    CALL-SITES NATIFS -- xrefs EXHAUSTIVES de `IdunBattleLogic.Entities.DSLBehaviors$$
    RemoveUnitFromItsTiles` (build `rnca9r7q6c`), QUATRE, tous avec `removeTileFromUnit: true` :
      * `...Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` (active 1011) -- PORTE ;
      * `...Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` (active 1023) -- PORTE ;
      * `...Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour` (active 1090) -- PORTE
        (`runner/abilities/spacewolves.py`, tranche 2) : SEUL appelant a viser la CIBLE et non le
        caster, et seulement si elle est MORTE sur sa tuile d'origine ;
      * `...Abilities.Triggered.Loki.StormboyzStrike_TeleportAbility$$CreateBehaviour` (triggered
        1141) -- PORTE (`runner/operations/triggers/loki/stormboyz_strike.py`, tranche 3/3) : SEUL
        appelant qui n'est PAS une active, et seul ou cette feuille est la 1re de DEUX (pas de
        trois).
    Chez 1011 et 1023 c'est le 1er des trois behaviours ; LES QUATRE sont desormais portes."""
    __slots__ = ("units_sel", "remove_tile_from_unit")

    def __init__(self, units_sel: TargetsSelector, remove_tile_from_unit: bool = True):
        self.units_sel = units_sel
        self.remove_tile_from_unit = bool(remove_tile_from_unit)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        from ...operations.remove_unit_from_tiles import RemoveUnitFromTilesOperation
        for u in sorted((x for x in _units_of(self.units_sel, entities)
                         if isinstance(x, dict) and x.get("id") is not None),
                        key=lambda x: x["id"]):
            res = RemoveUnitFromTilesOperation.execute(
                state, int(u["id"]), remove_tile_from_unit=self.remove_tile_from_unit)
            if res is not None and res.get("applied"):
                ectx.emit("RemoveUnitFromItsTiles", unit=int(u["id"]), tiles=res["tiles"])
        return OperationResult.ok()


class RemoveAllForcedAttackTargets(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$RemoveAllForcedAttackTargets(attacker)` ->
    `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute`. La factory construit
    ce behaviour avec DEUX selecteurs : l'`attacker` recu, et un second selecteur PRE-CONSTRUIT du
    contexte DSL (`<ctx>+0x90` -> `+0x20`) qui enumere les cibles a retirer -- c'est le « All » du
    nom de la factory.

    `Execute`, MIRROR du decompile :

        attacker = SelectSingle(_attackerSelector(+0x50), entities)
        comp     = attacker.GetComponent<ForcedAttackTargetsComponent>()
        foreach (target in _targetsSelector(+0x58).Select(entities, groupType = 0))
            comp.<liste @+0x50>.Remove(target.Id)

    Le port ne modelise pas le second selecteur : il VIDE la liste de l'attaquant. Les deux
    coincident tant que le selecteur `+0x20` couvre toutes les cibles forcees possibles, ce qui est
    la lecture du nom de la factory (`RemoveALLForcedAttackTargets`) -- ECART NOMME si un jour un
    call-site s'appuyait sur un sous-ensemble. Il y en a exactement DEUX dans ce build (xrefs
    EXHAUSTIVES de `...DSLBehaviors$$RemoveAllForcedAttackTargets`), et les DEUX sont portes :
    `...Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` (1011) et
    `...Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` (1023) -- 2e des trois behaviours
    dans les deux cas, ou l'attaquant est le caster qui vient de quitter le plateau.

    OBSERVABLE MESURE (#366-r1, cast de 1011) : ce behaviour n'a emis AUCUN event -- la liste du
    caster etait VIDE. La feuille est donc portee pour la STRUCTURE de l'arbre ; sa mutation ne
    devient observable que si le caster est sous un Taunt / `InstinctiveBehaviour` au moment du cast
    (ce que porte, lui, le porteur reel de 1023 : `tyranSmnRipperSwarm` a le trait
    `InstinctiveBehaviour`).
    Emet 'RemoveAllForcedAttackTargets' seulement si au moins une cible a ete retiree. PUR."""
    __slots__ = ("attacker_sel",)

    def __init__(self, attacker_sel: TargetsSelector):
        self.attacker_sel = attacker_sel

    def execute(self, entities, ectx):
        from ...components import ForcedAttackTargetsComponent
        state = ectx.state
        att = resolve_unit(self.attacker_sel, entities)      # `SelectSingle` natif
        aid = att.get("id") if att else None
        if state is None or aid is None:
            return OperationResult.ok()
        e = state.get_entity(int(aid))
        comp = e.get_component(ForcedAttackTargetsComponent) if e is not None else None
        if comp is None or not comp.targets:
            return OperationResult.ok()
        removed = comp.get()
        comp.targets = []
        ectx.emit("RemoveAllForcedAttackTargets", attacker=int(aid), removed=removed)
        return OperationResult.ok()


# Registre des abilities TRIGGERED declenchables DIRECTEMENT par le noeud `TriggerAbility` :
# `TriggeredAbilityType (int) -> callable(state, owner_id) -> dict | None`. VIDE par defaut, et c'est un
# CHOIX documente, pas un oubli : le seul call-site porte (HeraldOfTheApocalypse 1020 -> BattleFatigue
# 0x401) declenche un behaviour dont le gate central N'A AUCUNE SOURCE OFFLINE (cf. `TriggerAbility`).
# Une entree ici DOIT etre integralement sourcable (config gameconfig ou etat runner), sinon elle
# INVENTE la mutation.
TRIGGERED_ABILITY_BEHAVIOURS: dict[int, object] = {}


# Registre des TRIGGERED declenchables par le noeud `TriggerAbilityDelayed` : `TriggeredAbilityType
# (int) -> callable(entities, ectx) -> dict | None`. Le callable execute l'ARBRE de `CreateBehaviour`
# de l'ability differee, dans le contexte `entities` du declencheur. Rempli par les modules
# d'abilities (import-time), pas ici : ce module ne connait pas les arbres.
TRIGGERED_ABILITY_DELAYED_BEHAVIOURS: dict[int, object] = {}


class TriggerAbilityDelayed(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$TriggerAbilityDelayed(entity, triggeredAbilityType,
    unitSelectionType)` -> `IdunBattle.Entities.Behaviours.TriggerAbilityDelayedBehaviour`. Champs
    poses par le ctor (relus) : `+0x50` state, `+0x58` entity (selecteur), `+0x60` abilityType (int),
    `+0x64` unitSelectionType (int).

    `...TriggerAbilityDelayedBehaviour$$Execute` resout le selecteur `+0x58` avec le mode `+0x64`,
    puis, POUR CHAQUE entite rendue, appelle le slot 6 du service de triggers DIFFERES avec
    `(entityId, abilityType, entities)` : l'ability n'est PAS executee sur place, elle est PLANIFIEE.

    DEUX CHEMINS, et c'est DELIBERE (#406) :

    1. **LA FILE (fidele)** -- si `ability_type` est inscrite dans `CUSTOM_TRIGGERED_ABILITIES`
       (`operations/triggers/dispatch/registry.py`), le noeud ENFILE, comme le natif, via
       `add_pending_triggered_ability` -> `state.pending_triggered_abilities`. Le drain vit dans
       `Runner.apply`, a la borne du message top-level : c'est la position LUE du premier
       `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` de
       `IdunBattle.Messages.InputMessageProcessor$$RunPhase` (apres `action()`, apres
       `VerifyDeaths`/`ProcessDamageEvents`, avant `EndPhase`). RE complete : le docstring de
       `operations/triggers/dispatch/pending.py`.

    2. **LE COLLAPSE INLINE (herite)** -- sinon, le comportement d'avant : execution immediate du
       callable de `TRIGGERED_ABILITY_DELAYED_BEHAVIOURS`, en fin de behaviour. Il couvre les deux
       call-sites deja portes (`...SorcerousFacadeAbility$$ExecuteBehaviour` et
       `MasterOfTheTutelaries_SummonAbility`), ou le differe est le DERNIER terme de l'arbre et ou
       l'ordre observable ne change donc pas. **DETTE NOMMEE** : ces deux-la n'ont pas ete bascules
       sur la file par #406 (perimetre), et leur bascule demandera de re-jouer leurs tests -- le
       contexte du drain est RECONSTRUIT, pas celui capture a l'enfilement.

    Le chemin 1 est ce qui rend `HarlequinsPanoply` portable : son `TriggerAbilityDelayed` est pose
    PENDANT la resolution d'une attaque (per-coup, via l'intercepteur de `_run_hits`), et son
    behaviour differe DEPLACE le porteur. Inline, ce `MoveUnit` tomberait au milieu des coups.

    `unit_selection_type` = le litteral `+0x64` (3 aux trois call-sites lus) ; il gouverne le MODE de
    resolution du selecteur natif, non porte -> conserve pour la tracabilite, jamais lu.

    Une ability absente des DEUX registres rend `dispatched: False` : le gap est VISIBLE (meme
    doctrine que `AbilityHandler.unported` et que `TriggerAbility`), jamais muet.
    Emet 'TriggerAbilityDelayed'. PUR (stop=False)."""
    __slots__ = ("entity_sel", "ability_type", "unit_selection_type")

    def __init__(self, entity_sel: TargetsSelector, ability_type: int,
                 unit_selection_type: int = 3):
        self.entity_sel = entity_sel
        self.ability_type = int(ability_type)
        self.unit_selection_type = int(unit_selection_type)

    def execute(self, entities, ectx):
        from ...operations.triggers.dispatch.registry import CUSTOM_TRIGGERED_ABILITIES
        targets = sorted({u["id"] for u in _units_of(self.entity_sel, entities)
                          if isinstance(u, dict) and u.get("id") is not None})
        state = ectx.state
        queued = bool(CUSTOM_TRIGGERED_ABILITIES.get(self.ability_type)) and state is not None
        results = []
        if queued:
            from ...operations.triggers.dispatch.pending import add_pending_triggered_ability
            from ...operations.triggers.base import TriggerEvent
            from ....dsl.event_trigger_type import EventTriggerType
            # L'`AbilityEntities` que le natif recopie dans la file est REJOUE tel quel au drain
            # (`TriggerTriggeredAbilityOperation$$Execute` n'y rafraichit que les tuiles, le joueur
            # courant et `+0x18 = entity`). Cote port on memorise le couple (actor, target) du
            # contexte -- de quoi reconstruire a l'identique le meme `entities_from_state`.
            _aid = (entities.actor or {}).get("id") if getattr(entities, "actor", None) else None
            _tid = (entities.target or {}).get("id") if getattr(entities, "target", None) else None
            for _uid in targets:              # ordre de lecture = id (mirror OrderBy natif)
                add_pending_triggered_ability(
                    state, _uid, self.ability_type,
                    # `triggerType = 0x20 = Custom` : le litteral que
                    # `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` passe
                    # au slot 4 de l'ability re-declenchee (dernier argument de l'appel).
                    TriggerEvent(int(EventTriggerType.Custom), _aid, _tid,
                                 ranged=False, profile=None,
                                 triggering_ability=self.ability_type))
                results.append({"queued": True, "unit": int(_uid)})
        else:
            fn = TRIGGERED_ABILITY_DELAYED_BEHAVIOURS.get(self.ability_type)
            if fn is not None:
                for _uid in targets:          # ordre de lecture = id (mirror OrderBy natif)
                    results.append(fn(entities, ectx))
        ectx.emit("TriggerAbilityDelayed", ability_type=self.ability_type, targets=targets,
                  dispatched=queued or TRIGGERED_ABILITY_DELAYED_BEHAVIOURS.get(self.ability_type)
                  is not None, queued=queued, results=results)
        return OperationResult.ok()


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
