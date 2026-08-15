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
from ....entities.triggered_ability_type import entity_triggered_ability_ids
from ...components import ForcedAttackTargetsComponent
from ...components import HealthComponent, UnitFlagsComponent
from ...components import StatsComponent
from ...operations.damage import AttackDamageOperation
from ...operations.remove_unit import RemoveUnitOperation
from ...operations.remove_unit_from_tiles import RemoveUnitFromTilesOperation
from ....dsl.event_trigger_type import EventTriggerType


class KillDeadUnits(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$KillDeadUnits` = `IdunBattleLogic.Entities.DSLFactory$$Kill(subject, DownedUnits(units_sel), options)`
    -> `IdunBattle.Entities.Behaviours.KillUnitBehaviour$$Execute` : pour chaque unite DOWNED (flag 0xf, via
    `DownedUnits`=`UnitsWithFlagSelector(units_sel, 0xf, want=1) IdunBattleLogic.Entities.DSLSelectors$$DownedUnits`) NON exemptee (le natif skippe
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
        for u in sorted((x for x in _units_of(self.units_sel, entities)
                         if isinstance(x, dict) and x.get("id") is not None),
                        key=lambda x: x["id"]):              # ordre de lecture = id
            uid = u["id"]
            res = RemoveUnitOperation.execute(state, int(uid), remove_effects=True)
            if res is not None:
                ectx.emit("RemoveUnit", unit=uid, downstream=res["downstream"])
        return OperationResult.ok()


class Resurrect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$Resurrect(targets, targetTiles, hp, healType,
    abilityType, options)` -> `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute` --
    MIRROR du decompile, lu sur `rnca9r7q6c` (les noms de parametres de Ghidra y sont DECALES d'un
    cran par le `sret` de l'`OperationResult` : ce que la signature nomme `entities` est le `this`
    du behaviour, `processor` est l'`AbilityEntities`, et le vrai processor arrive en `r9`) :

        hp      = <+0x60>.Calculate(entities)                         # noeud MONTANT, evalue UNE fois
        targets = <+0x50>.Select(entities)                            # liste d'unites
        ListExtensions.Remove(targets, t => !IsValidTarget(t))        # cf. `u003CExecuteu003Eb__9_0`
        tiles   = <+0x58>.Select(entities)                            # liste de tuiles
        n       = Math.Min(targets.Count, tiles.Count)
        for (i = 0; i < n; i++)
            processor.<slot 100>(targets[i], healType@+0x68, tiles[i], hp,
                                 abilityType@+0x80, options@+0x6c)

    Trois points STRUCTURELS, tous LUS :
      * c'est un **ZIP** borne par `Min(|targets|, |tiles|)` -- la i-eme unite prend la i-eme tuile,
        et le surplus de l'un ou l'autre est simplement ignore. Pas de recherche de tuile, pas de
        re-evaluation entre iterations : les deux listes sont figees AVANT la boucle ;
      * le PRE-FILTRE `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$IsValidTarget` =
        `IsDefeated(t) && battleQuery.CanBeResurrected(t, healType)` retire les cibles invalides
        AVANT le zip -- donc il DECALE l'appariement unite/tuile (une cible ecartee ne consomme pas
        sa tuile). Le porter en aval, dans l'Operation, donnerait le meme ensemble de ressuscites
        mais PAS le meme placement ;
      * `options` (`+0x6c`) est le booleen `takesImmediateTurn`. `1039 RitesOfRestoration` passe
        **false** (i2 : « and are unable to act on this turn »), l'Ambush genestealer passe **true**.

    Frontiere #149 respectee : la feuille est DECLARATIVE (selecteurs + zip), l'Operation en dessous
    est imperative (`runner/operations/resurrect.py`, mirror
    `IdunBattle.Operations.ResurrectUnitOperation$$Execute`) et porte gate, flags, PV et triggers.

    `abilityType` (le `Nullable<AbilityType>` du 6e argument) n'a pas d'observable d'etat porte
    (attribution) -> non modelise, comme le `source` de `Repair`.

    Emet 'Resurrect' (amount + resurrections=[...]). PUR (stop=False)."""
    __slots__ = ("targets_sel", "tiles_sel", "hp_fn", "heal_type", "immediate_turn")

    def __init__(self, targets_sel: TargetsSelector, tiles_sel: TargetsSelector, hp_fn,
                 heal_type: int = 0, immediate_turn: bool = False):
        self.targets_sel, self.tiles_sel, self.hp_fn = targets_sel, tiles_sel, hp_fn
        self.heal_type, self.immediate_turn = int(heal_type), bool(immediate_turn)

    def execute(self, entities, ectx):
        from ...operations.resurrect import ResurrectUnitOperation
        from ..attack_query import can_be_resurrected
        state = ectx.state
        if state is None:
            ectx.emit("Resurrect", hp=None, resurrections=[])
            return OperationResult.ok()
        # `<+0x60>.Calculate(entities)` -- le natif evalue le montant AVANT de resoudre les
        # selecteurs ; scalaire ou callable, MEME convention que `Heal.amount_fn`/`Repair.amount_fn`.
        hp = int((self.hp_fn(entities, ectx) if callable(self.hp_fn) else self.hp_fn) or 0)
        # PRE-FILTRE `IsValidTarget` : `IsDefeated(t) && CanBeResurrected(t, healType)`. Il vit ICI
        # (et pas seulement dans l'Operation) parce qu'il decale l'appariement du zip.
        targets = []
        for u in _units_of(self.targets_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None or uc.alive:                       # `UnitExtensions$$IsDefeated`
                continue
            if not can_be_resurrected(state, int(uid), self.heal_type):
                continue
            targets.append(int(uid))
        tiles = list(self.tiles_sel.evaluate(entities) or [])
        board = state.board
        out: list = []
        for uid, tile in zip(targets, tiles):                # zip borne par Min(|targets|, |tiles|)
            # Domaine du selecteur de tuiles : `CanAddUnit`/`AdjacentTiles` rendent des IDS de tuile ;
            # l'Operation, elle, prend une COORDONNEE. Conversion par le board, jamais devinee.
            coord = tile if isinstance(tile, (tuple, list)) else (
                board.coord(int(tile)) if board is not None else None)
            r = ResurrectUnitOperation.execute(state, uid, coord, hp,
                                               immediate_turn=self.immediate_turn,
                                               heal_type=self.heal_type)
            if r is not None:
                out.append(r)
        ectx.emit("Resurrect", hp=hp, resurrections=out)
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


class ReAddMachine(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ReAddMachine(unit, resetFlags)` ->
    `IdunBattle.Entities.Behaviours.ReAddMachineBehaviour$$Execute` -- MIRROR du decompile, le
    SYMETRIQUE exact de `RemoveMachine` ci-dessus (#1078-r2) :

        unit = <this+0x50>.<slot 9 = SelectSingle>(entities)
        if (unit == null) return default(OperationResult)      // resultat VIDE, aucun appel
        if (<this+0x58> != null) {
            b = <this+0x58>.<slot 0 = ShouldTrigger>(entities)
            processor.<slot 10 = ReAddMachine>(unit, b)
        }
        return default(OperationResult)

    ⚠ **`resetFlags` EST UN PREDICAT (`IAbilityTrigger`), PAS UN BOOLEEN**, et les DEUX call-sites
    du build le prouvent :
      * `...HunterOfSoulsAbility$$CreateBehaviour` passe `<DSLTriggers+0x70>` = le `YesTrigger`
        CONSTANT (toujours VRAI) ;
      * `...HunterOfSouls_KilledAbility$$CreateBehaviour` passe
        `NOT HasFlag(Owner@DSLSelectors+0x30, 0x3 = TurnFinished)`.
    Le figer en `bool` a la construction aurait rendu le second call-site FAUX en silence. Le
    booleen n'apparait qu'a la frontiere de l'Operation, apres `ShouldTrigger`.

    ⚠ **UN SEUL SUJET** : le natif appelle `SelectSingle` (slot 9), pas `Select` -- contraste avec
    `RemoveUnit`/`RemoveMachine`, qui iterent. Une machine, pas une liste.

    DOCTRINE #149 : cette feuille est la FRONTIERE -- au-dessus le selecteur et le predicat
    (declaratifs), en dessous l'Operation imperative (`runner/operations/re_add_machine.py`, qui
    porte les gates, le rattachement et le `RemoveTurnFlags`).

    Emet 'ReAddMachine' seulement si l'Operation a MUTE (un gate qui refuse n'est pas journalise,
    meme convention que `RemoveUnit`). PUR (stop=False)."""
    __slots__ = ("unit_sel", "reset_flags_trigger")

    def __init__(self, unit_sel: TargetsSelector, reset_flags_trigger=None):
        self.unit_sel = unit_sel
        self.reset_flags_trigger = reset_flags_trigger

    def execute(self, entities, ectx):
        from ...operations.re_add_machine import ReAddMachineOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        u = resolve_unit(self.unit_sel, entities)              # `SelectSingle` natif (slot 9)
        uid = u.get("id") if isinstance(u, dict) else None
        if uid is None:
            return OperationResult.ok()                        # `unit == null` -> resultat VIDE
        if self.reset_flags_trigger is None:
            # `if (<this+0x58> != null)` -- selecteur de predicat NUL : le natif n'appelle PAS
            # l'operation du tout. Aucun call-site du build n'est dans ce cas, mais le gate est LU.
            return OperationResult.ok()
        reset = bool(self.reset_flags_trigger.evaluate(entities))
        res = ReAddMachineOperation.execute(state, int(uid), reset_flags=reset)
        if res is not None:
            ectx.emit("ReAddMachine", machine=int(uid), reset_flags=reset,
                      flags_cleared=res["flags_cleared"])
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
        state = ectx.state
        att = resolve_unit(self.attacker_sel, entities)      # `SelectSingle` natif
        aid = att.get("id") if att else None
        if state is None or aid is None:
            return OperationResult.ok()
        e = state.get_entity(int(aid))
        comp = e.get_component(ForcedAttackTargetsComponent) if e is not None else None
        if comp is None or not comp.get():
            return OperationResult.ok()
        # `clear()` VIDE la liste ET DÉLIE l'écrivain-effet : après ce behaviour la restriction ne
        # doit PAS repousser tant que l'effet 27 vit encore (le natif n'a aucune ré-écriture --
        # `TauntedEffect$$ApplyInternal` ne se rejoue pas). Cf. `ForcedAttackTargetsComponent`.
        removed = comp.clear()
        ectx.emit("RemoveAllForcedAttackTargets", attacker=int(aid), removed=removed)
        return OperationResult.ok()


def _unit_has_triggered_ability(state, unit_id, ability_type: int) -> bool:
    """Gate `GetAbilityState` d'`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$
    TriggerAbility` (#448-r1) -- la cible PORTE-t-elle l'ability qu'on lui declenche ?

    Le natif, dans sa boucle par ability du type demande :

        abilityState = ignoreUnitHavingAbility
                     ? new Nullable<AbilityState>(default)              // le bras « on s'en fiche »
                     : UnitExtensions.GetAbilityState(entity);          // l'etat SUR CETTE unite
        if (abilityState.HasValue) { ... Execute(abilityState.Value, entities, 0x20) ... }

    Le nom du parametre le dit : **`ignoreUnitHavingAbility`**. A `false` -- ce que passent les DEUX
    call-sites portes (`HeraldOfTheApocalypse` et `...StormboyzStrike_MissAbility`) -- une unite qui
    ne porte PAS l'ability ne voit RIEN s'executer, et **aucun tirage n'est consomme**.

    MESURE qui l'a rendu visible (#448-r1, `MC1_67`/777, greffe `StormboyzStrike` sur `orksNob`) :
    le `TriggerAbility(Caster, 0x46e = FullThrottle)` du Miss. Le porteur GREFFE n'a que
    `passiveAbilities = [1141]` -- la greffe REMPLACE la liste, elle n'ajoute pas -- donc il ne porte
    PAS `FullThrottle`. Natif : **2** `genrand_int32` consommes sur le pas. Port SANS ce gate : **3**
    (il tirait le `Maybe(chance = 30)` de FullThrottle pour une ability que l'unite ne porte pas).
    L'ecart etait INVISIBLE sur tout observable d'etat -- ni la position, ni la marque, ni les PV --
    et n'apparait QUE sur le flux PRNG, qu'il DECALE pour tout le reste de la bataille.

    Le gate porte sur l'EXECUTION, pas sur la resolution du selecteur : cote natif la liste `targets`
    est deja resolue par `TriggerAbilityBehaviour$$Execute` AVANT l'appel de l'Operation. Le port
    publie donc `targets` inchange et journalise a part les cibles ecartees (`notCarrying`).

    Substrat : `entity_triggered_ability_ids` (l'`AbilitiesComponent` mesure via `unitAbilityStates`,
    repli kit gameconfig quand le canal n'a pas parle) -- le MEME que lit la feuille d'utilite
    `TriggeredAbilities(2)`, jamais un second recensement."""
    if state is None or unit_id is None:
        return False
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    return int(ability_type) in set(entity_triggered_ability_ids(ctx))


class Kill(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$Kill(subject, units, options)` ->
    `IdunBattle.Entities.Behaviours.KillUnitBehaviour$$Execute` (#448-r1) : TUE chaque unite du
    selecteur `units_sel`, `subject_sel` etant le TUEUR impute.

    A NE PAS CONFONDRE avec `KillDeadUnits` ci-dessus : celui-la est
    `Kill(subject, DownedUnits(units), ...)` -- il FINALISE des unites deja a 0 PV et le port en fait
    un no-op structurel (la mort est finalisee inline chez nous). CELUI-CI tue une unite VIVANTE et
    A PLEINS PV : c'est une vraie mutation, et la taire serait un no-op silencieux.

    `...KillUnitBehaviour$$Execute`, remis en C# depuis le decompile :

        mode = entities.<+0x69> ? (entities.<+0x68> ? 1 : 0) : (entities.<+0x68> ? 3 : 2);
        foreach (u in this.<+0x60>.Select(entities, mode)) {
            if (UnitExtensions.HasFlag(u, 9)) continue;      // Fled
            if (UnitExtensions.HasFlag(u, 6)) continue;      // Dead
            if (UnitExtensions.HasFlag(u, 0x1a)) continue;   // Removed
            killer = this.<+0x58>.Select(entities, 8);       // peut etre null
            processor.<vslot 0x60>(killer, u, <options>);    // = KillUnitOperation$$Execute
        }

    Les trois gates sont LUS (`HasFlag(9)`, `HasFlag(6)`, `HasFlag(0x1a)`). Cote port, `HasFlag(6)`
    (`UnitFlag.Dead`) est COLLAPSE en `UnitComponent.alive` -- le moteur ne pose pas ce flag, il
    marque `alive = False` (meme collapse que `remove_unit.py` pour `0x1a`, qui lui EST porte comme
    flag). Les deux autres sont testes tels quels.

    `options = KillUnitBehaviourOptions.ForDirectKill()` = **`0x10001`** (constante LUE :
    `IdunBattle.Entities.Behaviours.KillUnitBehaviourOptions$$ForDirectKill` a pour corps entier
    `return 0x10001;`). Aucun de ses bits n'est consomme par le pipeline de mort PORTE (qui n'a ni
    reservation ni blocage de revive parametrable) -> transcrit pour la tracabilite, non lu.
    RESIDU NOMME.

    FRONTIERE DSL (#149) : la feuille resout ses selecteurs puis DELEGUE, unite par unite, au foyer
    IMPERATIF `AttackDamageOperation._kill_unit_operation` (mirror
    `IdunBattle.Operations.KillUnitOperation$$Execute`, `runner/operations/damage.py`) -- le MEME
    que le pipeline de degat, surtout pas un second port de la meme fonction native. Le natif
    appelle ici le vslot `KillUnit` du processor **DIRECTEMENT**, pas la file `MatchState.AddDeath` :
    il n'y a donc ni enqueue ni drain a mimer, la mort s'applique sur place.

    Call-sites portes : `...StormboyzStrike_FallbackAbility$$CreateBehaviour` (le Stormboy qui finit
    son tour sans avoir pu se poser meurt) et `...FullThrottleAbility$$CreateBehaviour` (le jetpack
    qui explose). Les DEUX passent `Kill(Caster, Caster, ForDirectKill)` -- tueur == victime.

    Emet 'Kill' (`killed` = les ids REELLEMENT tues). PUR (stop=False)."""
    __slots__ = ("subject_sel", "units_sel")

    def __init__(self, subject_sel: TargetsSelector, units_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        killer = resolve_unit(self.subject_sel, entities)          # `Select(entities, 8)`, peut etre None
        killer_id = killer.get("id") if isinstance(killer, dict) else None
        killed: list = []
        out: list = []
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None or not uc.alive:                          # `HasFlag(6 = Dead)` (collapse)
                continue
            fl = e.get_component(UnitFlagsComponent)
            if fl is not None and (fl.has(UnitFlagsComponent.FLED)                 # `HasFlag(9)`
                                   or fl.has(UnitFlagsComponent.REMOVED)):        # `HasFlag(0x1a)`
                continue
            hc = e.get_component(HealthComponent)
            if hc is not None:
                hc.hp = 0                    # `KillUnitOperation$$Execute+0x505` : `health.hp = 0`
            uc.alive = False
            killed.append(int(uid))
            out = out + (AttackDamageOperation._kill_unit_operation(
                state, int(uid), None if killer_id is None else int(killer_id), False) or [])
        ectx.emit("Kill", killer=killer_id, killed=killed, death=out)
        return OperationResult.ok()


# Registre des abilities TRIGGERED declenchables DIRECTEMENT par le noeud `TriggerAbility` :
# `TriggeredAbilityType (int) -> callable(state, owner_id, entities, ectx) -> dict | None`.
# Une entree ici DOIT etre integralement sourcable (config gameconfig ou etat runner), sinon elle
# INVENTE la mutation. Le call-site `HeraldOfTheApocalypse` (1020 -> BattleFatigue 0x401) reste
# DELIBEREMENT absent : son behaviour a un gate central sans AUCUNE source offline (cf. la docstring
# de `TriggerAbility`).
# ⚠ CE DICT N'EST PAS VIDE, et la ligne qui l'affirmait ici a coute un rouge (#513) : il est peuple
# a l'IMPORT par les modules d'abilities -- `loki/full_throttle.py` (1134) depuis #448-r1,
# `abilities/tau.py` (1127) depuis #513. Elargir la signature exige donc de mettre a jour CHAQUE
# entree ; c'est la banque de tests qui l'a dit, pas la lecture du dict au repos.
#
# ⚠ `entities` EST L'`AbilityEntities` DU DECLENCHEUR, ET C'EST LE NATIF QUI LE VEUT (#513) :
# `IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$Execute` resout ses QUATRE selecteurs
# (`+0x60` actor, `+0x68` caster, `+0x70` target, `+0x78` unitFeetTiles) UNE FOIS, puis les passe --
# reconstitues en un `AbilityEntities` -- au slot d'operation 0x56 POUR CHAQUE unite declenchee. La
# signature `(state, owner_id)` d'avant #513 laissait donc tomber `caster` et `target`, ce qui est
# sans consequence tant que les deux valent l'owner mais FAUX des qu'ils divergent : sur
# `APendingAttackEffect` (`triggers/pending_attack.py`), `caster` est l'unite ATTAQUANTE et `target`
# le PORTEUR de l'effet, qui appartiennent a DEUX JOUEURS DIFFERENTS.
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
    `runner/operations/behaviour.py` documente deja pour la voie trigger-sur-mort).

    ⚠ **LE 8e ARGUMENT EST `ignoreUnitHavingAbility`, ET IL ETAIT CODE EN DUR A `false` (#1002-r1).**
    C'est le `flag` `+0x84` que `Execute` passe au slot `0x56`, et
    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` le lit exactement la ou
    `_unit_has_triggered_ability` (ci-dessus) transcrit son corps :

        abilityState = ignoreUnitHavingAbility ? new Nullable<AbilityState>(default)
                                               : UnitExtensions.GetAbilityState(entity);

    Les deux call-sites portes jusqu'ici (`HeraldOfTheApocalypse`, `StormboyzStrike_Miss`) passent
    `false`, donc le gate etait toujours applique et le parametre invisible. Le TROISIEME passe
    `true` -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FinalVengeance_UnitEffect$$
    CreateTargetTriggerBehaviour` = `TriggerAbility(Owner@<DSLSelectors+0x30>,
    0x400 = TriggeredAbilityType.FinalJustice, null, Get(abilityEntities+8),
    Get(abilityEntities+0x10), null, 0, **true**)` -- et c'est litteralement CE bit qui fait
    fonctionner la mecanique : le summon imperial qui recoit l'effet 1454 ne PORTE pas
    `FinalJustice`, l'effet la lui PRETE. Avec le gate applique, `notCarrying` aurait avale 100 %
    des declenchements, sans erreur et sans qu'aucun test ne rougisse.
    Defaut `False` = comportement HISTORIQUE, strict no-op pour les deux call-sites existants.

    Emet 'TriggerAbility'. PUR (stop=False)."""
    __slots__ = ("targets_sel", "ability_type", "ignore_unit_having_ability")

    def __init__(self, targets_sel: TargetsSelector, ability_type: int,
                 ignore_unit_having_ability: bool = False):
        self.targets_sel = targets_sel
        self.ability_type = int(ability_type)
        self.ignore_unit_having_ability = bool(ignore_unit_having_ability)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        fn = TRIGGERED_ABILITY_BEHAVIOURS.get(self.ability_type)
        targets = sorted({u["id"] for u in _units_of(self.targets_sel, entities)
                          if isinstance(u, dict) and u.get("id") is not None})
        results, skipped = [], []
        for uid in targets:                                  # ordre de lecture = id (mirror OrderBy)
            # `ignoreUnitHavingAbility ? Nullable<AbilityState>(default) : GetAbilityState(entity)`
            # -- le bras `true` FABRIQUE un etat par defaut, donc `HasValue` et donc AUCUN filtre.
            if not self.ignore_unit_having_ability \
                    and not _unit_has_triggered_ability(state, uid, self.ability_type):
                skipped.append(int(uid))                     # gate `GetAbilityState` -- cf. ci-dessous
                results.append(None)
                continue
            results.append(None if fn is None else fn(state, uid, entities, ectx))
        ectx.emit("TriggerAbility", ability_type=self.ability_type, targets=targets,
                  dispatched=fn is not None, results=results, notCarrying=skipped,
                  ignoreUnitHavingAbility=self.ignore_unit_having_ability)
        return OperationResult.ok()
