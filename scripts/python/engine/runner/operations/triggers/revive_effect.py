"""`IdunBattle.Entities.Effects.ReviveEffect` -- BASE du sous-systeme REVIVE-EN-PLACE (case-66).

C'est une FAMILLE : la base fournit la STRUCTURE (trigger + behaviour DSL + les 3 virtuels), chaque
sous-classe `Loki.*_ReviveEffect` ne surcharge que le FILTRE, les vars et le gate d'overkill. Ce module
mirroir la BASE (ns natif `IdunBattle.Entities.Effects`, hors `Loki`) ; les sous-classes vivent dans
`triggers/loki/*.py` (ns natif `IdunBattle.Entities.Effects.Loki`).

Artefacts natifs (build gqfc5mff6c, VA citees ; RVA = VA - 0x180000000 calculee en code) :

    ReviveEffect..IdunBattle.Entities.Effects.ReviveEffect$$.ctor  0x484=turnsEnabled, 0x480=activationFrequency,
                                                         0x488=removeEffect, source=AbilityOrEffect
    IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger  OnPreDeath(target, get_ReviveOnOverkill)
                                                         & CanBeRevived(target, get_HealType)
                                                         & CreateTargetFilter          (3 virtuels)
    IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour Maybe(GetReviveChance@0x768){
                                                             Revive(self@0x148, target@0x178,
                                                                    Min(GetReviveHP@0x778,
                                                                        StatAmount(target,Health,max)),
                                                                    GetHealType@0x748,
                                                                    AbilityOrEffect(effect.Id)) ;
                                                             DeactivateEffect }
    IdunBattleLogic.Entities.DSLBehaviors$$Revive -> IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute (POSE la `ReviveData`
                               sur `UnitComponent+0xa8` -- AUCUNE mutation) ; le mutateur
                               `IdunBattle.Operations.ReviveUnitOperation$$Execute` la DRAINE plus tard
                               (`Core.Services.OperationProcessor$$ReviveUnit`). Cf. `operations/revive.py`.
    IdunBattleLogic.Entities.DSLBehaviors$$DeactivateEffect -> ActivateEffectBehaviour(effect, active=false)
    IdunBattle.Core.Services.BattleQuery$$CanBeRevived

## Les virtuels de `ReviveEffect` -- LUS, pas deduits (case-89 volet B1)

Le decompile appelle `(**(klass + 0x738))`, `(+0x748)`, `(+0x758)`, `(+0x768)`, `(+0x778)`. La vtable
d'un `Il2CppClass` commence a `+0x138` et chaque entree fait 0x10 (`{methodPtr, MethodInfo*}`) ->
slot = (offset - 0x138) / 0x10 : **0x738 = slot 96**, 0x748 = 97, 0x758 = 98, 0x768 = 99, 0x778 = 100.

DEUX chemins de lecture, croises :
  (a) LIVE `resolveVtableSlot` (`probe_79_revive_vtable.py`) -- ne marche que sur une classe INITIALISEE.
      ⚠ La restriction « RitesOfMorkaiEffect rend des slots NULS : carrier hors pool » N'EST PLUS VRAIE
      depuis le 2026-07-29 : `catalog_inject.write_augmented_seed_bc` fait entrer `spaceWolfPriest` au
      pool, le cast de `RitesOfMorkai` INSTANCIE la classe, et ses slots se lisent alors LIVE. Lecture
      faite, elle CONFIRME le tableau ci-dessous par une seconde source :
        +0x718 IgnoreArmor  +0x728 get_ActivateOnResurrect  +0x738 get_ReviveOnOverkill
        +0x748 get_HealType +0x758 CreateTargetFilter       +0x768 GetReviveChance  +0x778 GetReviveHP
      avec `get_ReviveOnOverkill` = `get_ActivateOnResurrect` = `32 c0 c3` (`xor al,al ; ret`) = FALSE
      et `get_HealType` = `IgnoreArmor` = `33 c0 c3` (`xor eax,eax ; ret`) = 0. Sur la BASE
      `ReviveEffect`, `CreateTargetFilter`/`GetReviveChance`/`GetReviveHP` sont bien les 3 ABSTRAITS.
      ⚠ PIEGE : `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` lit ces
      MEMES slots `+0x728/+0x738/+0x748` avec une tout autre semantique (portee de bond / adjacence /
      rupture) -- sur `ABondEffect` ils sont ABSTRAITS, c'est `ReviveEffect` qui les remplit. Ne pas
      croiser les deux lectures. Ses trois branches produisent des `IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect`, jamais
      un `DeactivateEffect`. cf. `docs/rl/case-229-1502-rites-of-morkai-live-confrontation.md` §5 ;
  (b) OFFLINE la table `methodPointers` d'IL2CPP, presente TELLE QUELLE dans `GameAssembly.dll` (les
      pointeurs sont stockes en VA image-base 0x180000000). Le bloc d'un `*_ReviveEffect` a la forme
      LUE : `[get_ReviveOnOverkill] [get_HealType?] .ctor CreateTargetFilter GetReviveChance GetReviveHP`
      (ordre valide sur la BASE @file 0x30fdb28 : `0 | GameCamera$$ShouldBlurBackground | GameCamera$$GetGuiId | .IdunBattle.Entities.Effects.ReviveEffect$$.ctor |
      IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger | 0 | IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour | 0 | 0` -- les
      TROIS zeros = les 3 ABSTRAITS, ce que la lecture live confirme : slots 0x758/0x768/0x778 de la base
      pointent sur le stub abstrait @1801e6080, `MethodInfo` nul).
      Le TYPE DE RETOUR desambigue les deux entrees triviales : `get_ReviveOnOverkill` renvoie un **bool**
      (corps 1 octet : GameCamera$$ShouldBlurBackground = `return 0`, GameCamera$$get_ShouldDisableRenderingWhenBehindSomething = `return 1`) ; `get_HealType` renvoie un
      **int** (corps 8 octets : GameCamera$$GetGuiId = `return 0`, GameCamera$$get_ScreenStatus = `return 1`).

    classe (bloc methodPointers)        | ReviveOnOverkill | HealType | GetReviveChance | GetReviveHP
    Narthecium_ReviveEffect  @0x30fffc0 | 0 (GameCamera$$ShouldBlurBackground)   | (herite) | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveChance      | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP
    TaintedNarthecium_...    @0x3100e28 | 1 (GameCamera$$get_ShouldDisableRenderingWhenBehindSomething)   | (herite) | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveChance      | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP
    RitesOfMorkaiEffect      @0x3100878 | 0 (GameCamera$$ShouldBlurBackground)   | (herite) | meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70      | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP
    ReanimationBeam_...      @0x3100698 | 0 (GameCamera$$ShouldBlurBackground)   | 1 (GameCamera$$get_ScreenStatus) | meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70 | IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP
    base ReviveEffect        @0x30fdb30 | 0 (GameCamera$$ShouldBlurBackground)   | 0 (GameCamera$$GetGuiId) | ABSTRAIT   | ABSTRAIT

  * `IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveChance` = `GetNumberConstant(config@0x60, 0x2a='chance')` (corps partage par ICF).
  * `meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70` = `b8 64 00 00 00 c3` = **`mov eax,100 ; ret`** -> `GetReviveChance` LITTERAL **= 100**
    pour RitesOfMorkai ET ReanimationBeam (leurs configs n'ont PAS de constante 'chance' et
    `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` LEVE une `System.Exception` sur cle absente : ils DEVAIENT overrider).
    => `default_chance = 100` n'est plus une hypothese, c'est une LECTURE.

`get_ReviveOnOverkill` EST le byte `param_3` de `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` :
  * `param_3 == 0` -> le trigger AJOUTE `NOT(HasFlag(dying, 8=overkill))`  => « unless Overkilled »
  * `param_3 != 0` -> AUCUN gate overkill                                  => « even if Overkilled »
(`param_4 == 0` -> AJOUTE `NOT(CurrentShieldAmountFormula(dying, 0x1b))` = shield==0, present pour TOUS,
implicite a la mort -> non modelise.)
"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import StatsComponent, OwnerComponent, UnitComponent, HealthComponent
# `UnitFlagsComponent` : le 3e etage de `BattleQuery$$CanBeRevived` est `!HasFlag(target, 0xd)`.
from ...components import UnitFlagsComponent
from ...abilities.behaviours.context import entities_from_state
from ...abilities.behaviours.stats import is_mechanical
from ....entities.behaviours import op_add, Maybe
from ....entities.selectors.accessors import Target
from ....entities.selectors.tiles import Caster
from ....entities.traits.unit_trait import UnitTrait
from ....entities.effects.magnitude import ability_var
from ....dsl.base import _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from .base import TriggeredAbility, EffectTrigger, TriggerEvent
from ....entities.selectors._shared import _tile_positions

PERMADEATH = int(UnitTrait.PermaDeath)                     # 0x41a=1050 (NOT HasTrait -> CanBeRevived)
AFFECTED_BY_HEAL = int(UnitTrait.AffectedByHealAndRepair)  # 0x421=1057 (IsAffectedByHealType)


class Revive(AbilityBehaviour):
    """Feuille DSL `Revive` (`IdunBattleLogic.Entities.DSLBehaviors$$Revive` -> `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute`).

    ⚠ CETTE FEUILLE NE MUTE RIEN (RE case-89 volet C) : le natif se contente de POSER une `ReviveData`
    (`amount`, `healType`, `sourceId`, `priority`) sur le `Nullable<ReviveData>` @`UnitComponent+0xa8`
    de CHAQUE cible du selecteur, sous le gate `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive`. Les PV/flags/position ne
    bougent que plus tard, quand `IdunBattle.Operations.ReviveUnitOperation$$Execute` draine ce champ.
    Frontiere #149 : la FEUILLE (declaratif, ICI) POSE ; l'Operation IMPERATIVE (operations/revive.py,
    EN-DESSOUS) APPLIQUE -- on NE fusionne PAS.

    `amount` = `Min(GetReviveHP, StatAmount(target, Health, Initial))` = le noeud `Min(Direct(GetReviveHP),
    StatAmount(target@0x178, Health=5, StatPart=3))` du behaviour natif (`GetReviveHP` =
    `GetVariableForLevel(config, 0x1d='hp', level)`, scalee rarete via `ability_var`). PUR (stop=False).

    ⚠ Le 4e argument de `IdunBattleLogic.Entities.DSLBehaviors$$Revive` est TOUJOURS un NOEUD FORMULE
    cote natif. Le port collapse le cas ARCHI-majoritaire (`Direct(ConfigVar('hp'))`) dans le triplet
    `(ability_id, hp_var, level/mult)` ; `amount_node` est l'echappatoire pour les appelants dont le
    natif passe une AUTRE formule -- a ce jour le SEUL est
    `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` branche
    `EchoesFromTheWarp` (`StatAmount(src, Health = 5, StatPart = 3 = Initial)`, cf. #366-r1 /
    `loki/ghost_revive.py`). Fourni => il REMPLACE `ability_var` (le natif ne calcule qu'UNE branche,
    resolue A LA CONSTRUCTION de l'arbre)."""
    __slots__ = ("target_sel", "ability_id", "hp_var", "level", "mult", "heal_type",
                 "source_id", "priority", "tiles_sel", "amount_node")

    def __init__(self, target_sel, ability_id: str, hp_var: str = "hp",
                 level=None, mult: int = 100, heal_type: int = 0,
                 source_id=None, priority: int = 0, tiles_sel=None, amount_node=None):
        self.target_sel, self.ability_id, self.hp_var = target_sel, ability_id, hp_var
        self.amount_node = amount_node
        # 7e argument de `IdunBattleLogic.Entities.DSLBehaviors$$Revive` (`targetsTile`) -- NUL chez tous
        # les consommateurs SAUF `IdunBattle.Entities.Effects.Loki.GhostEffect$$
        # CreateTargetTriggerBehaviour`, qui y passe `Owner@0x148` = la TUILE porteuse du ghost.
        # `ReviveBehaviour$$Execute` ne renseigne le `Nullable<UnitPosition>` de la `ReviveData` que si
        # ce selecteur est non nul -> c'est LUI qui fait la difference entre un revive in-place et le
        # seul revive DEPLACANT du binaire (#213). None = in-place (comportement de tous les autres).
        self.tiles_sel = tiles_sel
        # `GetReviveHP(abilityState)` = `GetVariableForLevel(config, 0x1d='hp', level)` ou `abilityState`
        # est celui de l'ABILITY SOURCE portee par l'effet. Le niveau/multiplicateur sont donc RESOLUS PAR
        # LE RAIL (cf. `_ReviveEffectCore.revive_level`) : passif du porteur pour un ReviveEffect pose
        # d'office par un passiveAbility ; niveau de l'ACTIVE du POSEUR (transporte par l'effet) pour un
        # ReviveEffect pose par une ability active. La feuille ne devine RIEN.
        self.level, self.mult = level, mult
        # 5e argument de `DSLFactory.Revive` : `GetHealType@0x748` pour un ReviveEffect, litteral pour les
        # TriggeredAbility autonomes (PhoenixGem = 2 IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour, FuelledByFury = 0 IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour).
        self.heal_type = int(heal_type)
        # 6e argument : `Nullable<AbilityOrEffect>` du poseur -- relu par `CurrentAbilityIs` sur On(0x2d = UnitRevived).
        self.source_id = source_id
        # 8e argument : priorite (`IsPreferredRevive`). 0 partout SAUF PhoenixGem = **-1000** (0xfffffc18).
        self.priority = int(priority)

    def execute(self, entities, ectx):
        from ..revive import post_pending_revive
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        # Fork d'`amount` (resolu A LA CONSTRUCTION de l'arbre cote natif, jamais au runtime) :
        # noeud formule explicite si l'appelant en fournit un, sinon `Direct(GetReviveHP)`.
        revive_hp = (int(self.amount_node.evaluate(entities)) if self.amount_node is not None
                     else ability_var(self.ability_id, self.hp_var, self.level,
                                      multiplier_pct=self.mult))      # GetReviveHP
        # `targetsTile` : `ReviveBehaviour$$Execute` evalue le selecteur UNE fois
        # (`FUN_180024d10(10, …, param_2+0x90, entities)`) puis prend l'element d'index de la cible
        # courante -- une liste de tuiles PAR CIBLE. Le port collapse chaque entree en un (col,row)
        # (meme collapse que `PositionComponent`) ; hors selecteur -> liste vide -> revive in-place.
        tiles = ([] if self.tiles_sel is None
                 else _tile_positions(self.tiles_sel, entities, getattr(state, "board", None)))
        for i, u in enumerate(_units_of(self.target_sel, entities)):
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            te = state.get_entity(tid)
            thc = te.get_component(HealthComponent) if te is not None else None
            maxhp = thc.hp_max if thc is not None else None
            hp = revive_hp
            if hp is not None and maxhp is not None:
                hp = min(int(hp), int(maxhp))                # Min(reviveHP, StatAmount(target,Health,max))
            pos = tiles[i] if i < len(tiles) else None       # `IList.get_Item(i)` du decompile
            # ECRITURE de la `ReviveData` @UnitComponent+0xa8 (gate `IsPreferredRevive`) -- PAS de mutation.
            posted = post_pending_revive(state, tid, hp, heal_type=self.heal_type,
                                         source=self.source_id, priority=self.priority,
                                         revive_position=pos)
            ectx.emit("Revive", target=tid, hp=hp, revive_hp=revive_hp, revive_position=pos,
                      revived=posted is not None, posted=posted is not None)
        return OperationResult.ok()


class ConsumeReviveGate(AbilityBehaviour):
    """Feuille `DeactivateEffect` (2e volet de l'`op_add` du `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour`, execute
    APRES le `Revive` sur SUCCES du `Maybe`) : DESACTIVE l'effet revive du porteur -> gate once-per-turn.
    Port : pose `revive_used_this_turn=True` sur le CASTER (`Caster()@0x148`, owner du passif/de l'effet) ;
    reactive au turn-start (`reset_revive_gates`). PUR (stop=False)."""
    __slots__ = ("owner_sel",)

    def __init__(self, owner_sel):
        self.owner_sel = owner_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):
            oid = u.get("id") if isinstance(u, dict) else None
            oe = state.get_entity(oid) if oid is not None else None
            ouc = oe.get_component(UnitComponent) if oe is not None else None
            if ouc is not None:
                ouc.revive_used_this_turn = True
        ectx.emit("DeactivateReviveEffect")
        return OperationResult.ok()


class RemoveReviveEffect(AbilityBehaviour):
    """Feuille `BaseEffect.GetRemoveEffectBehaviour` -- 2e volet du `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour` quand le champ `removeEffect` (0x488, pose au ctor) vaut TRUE. Contrairement a
    `DeactivateEffect` (desactivation reactivee au turn-start = once-per-TURN), `RemoveEffect` RETIRE
    l'effet -> le revive est one-shot DEFINITIF (« the FIRST TIME ... would be defeated »).
    Port : marque l'effet `consumed=True` dans `state.effects` (le collecteur `collect_effect_triggers`
    skippe les effets consommes -> le trigger ne peut plus refirer). PUR (stop=False)."""
    __slots__ = ("owner_sel", "effect_type")

    def __init__(self, owner_sel, effect_type: int):
        self.owner_sel, self.effect_type = owner_sel, effect_type

    def execute(self, entities, ectx):
        state = ectx.state
        eff = getattr(state, "effects", None) if state is not None else None
        if eff is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):
            oid = u.get("id") if isinstance(u, dict) else None
            if oid is None:
                continue
            for e in (eff.by_unit.get(int(oid)) or []):
                if e.effect_type == self.effect_type:
                    e.consumed = True
        ectx.emit("RemoveReviveEffect", effect_type=self.effect_type)
        return OperationResult.ok()


def create_target_trigger_behaviour(chance: int, ability_id: str, hp_var: str = "hp",
                                    remove_effect: bool = False, effect_type: int = -1,
                                    owner_sel=None, level=None, mult: int = 100,
                                    heal_type: int = 0):
    """Arbre de `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour` (MIRROR, base -> partage par TOUTES
    les sous-classes) :

        chance   = GetReviveChance                       (virtuel @vtable+0x768)
        reviveHP = GetReviveHP(abilityState)             (virtuel @vtable+0x778)
        amount   = Min(Direct(reviveHP), StatAmount(target@0x178, Health=5, max=3))
        revive   = Revive(self@0x148, target@0x178, amount, GetHealType@0x748, sourceId)
        second   = (removeEffect@0x488 == 0) ? DeactivateEffect(effect)
                                             : BaseEffect.GetRemoveEffectBehaviour(effect)
        Maybe(func{ revive ; second }, target@0x178, chance)

    `IdunBattleLogic.Entities.DSLBehaviors$$Maybe -> IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute` fait UN tirage `next_bool(chance)` ; le func
    ne s'execute QUE sur SUCCES -> un roll RATE ne consomme PAS le gate."""
    owner_sel = Caster() if owner_sel is None else owner_sel
    second = (RemoveReviveEffect(owner_sel, effect_type) if remove_effect
              else ConsumeReviveGate(owner_sel))
    return Maybe(chance, op_add(
        # DSLFactory.Revive : POSE la ReviveData (healType = GetHealType@0x748 ; sourceId =
        # AbilityOrEffect(effect.Id) = `param_1[2]` IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour ; priorite 0).
        Revive(Target(), ability_id, hp_var, level, mult,
               heal_type=heal_type, source_id=effect_type),
        second))                                # DeactivateEffect (once-per-turn) | RemoveEffect (one-shot)


def is_affected_by_heal_type(has_trait, liveunit, heal_type: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` -- MIRROR 1:1 du decompile (case-89 volet B1) :

        if (HasTrait(unit, 0x421 = AffectedByHealAndRepair)) return true;
        if (healType == 0 && IsMechanical(unit))  return false;     // 0 = Heal   : pas les mecaniques
        if (healType == 1 && !IsMechanical(unit)) return false;     // 1 = Repair : QUE les mecaniques
        return true;                                                // 2 (PhoenixGem) = aucun filtre

    ⚠ Le port precedent HARDCODAIT `healType = 0` pour tous les consommateurs : ReanimationBeam
    (`get_HealType @vtable+0x748` override = **1**, lu dans `methodPointers` @0x31006a0 = GameCamera$$get_ScreenStatus
    `return 1`) exige au contraire une cible MECHANICAL -- or son propre `IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter`
    impose `HasTrait(target, Mechanical)` : avec healType=0 le revive etait un **NO-OP GARANTI** (sauf
    trait AffectedByHealAndRepair). C'est corrige ici."""
    if has_trait is None:
        return True                                          # pas de resolveur trait -> non bloquant
    if has_trait(liveunit, AFFECTED_BY_HEAL):                # HasTrait(0x421) -> toujours affecte
        return True
    mech = is_mechanical(has_trait, liveunit)
    if int(heal_type) == 0 and mech:
        return False
    if int(heal_type) == 1 and not mech:
        return False
    return True


def can_be_revived(entities, target_liveunit, target_id: int, state: State,
                   heal_type: int = 0) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$CanBeRevived` (mirror, appele par le noeud `CanBeRevived` du
    `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger` via `IdunBattleLogic.Entities.DSLTriggers$$CanBeRevived -> CanBeRevivedTrigger
    IdunBattle.Entities.Triggers.CanBeRevivedTrigger$$ShouldTrigger`) : `GetStat(unit,Health,0) < 1` (mort) & `IsAffectedByHealType(healType)` &
    `NOT HasFlag(unit,0xd)` & `NOT HasTrait(PermaDeath=0x41a=1050)` & `NOT HasHealBlockers`.

    `healType` = le virtuel `get_HealType @vtable+0x748` de la sous-classe (0 base/Narthecium/Tainted/
    RitesOfMorkai, **1** ReanimationBeam, **2** PhoenixGem via le litteral de son IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour) -- cf. `is_affected_by_heal_type`.

    ⚠ **LE FLAG `0xd` EST DESORMAIS LU, ET LA JUSTIFICATION QUI VIVAIT ICI ETAIT FAUSSE**
    (#462-r4b-r1-r1-r1-r1-c-r3-r1-r6). Elle disait « flag 0xd (pas encore pose a l'instant de
    l'OnPreDeath) -> non-bloquant » ; le rang natif dit l'inverse. Aux adresses de retour de
    `IdunBattle.Operations.KillUnitOperation$$Execute` :

        RecordDeathReason  ->  Add(0x08 = Overkilled)  ->  **Add(0x0d = PreventRevive)**
        ->  On(1 = PreUnitDeath)  ->  <garde revive, UnitComponent+0xa8>  ->  ...

    le flag tombe AVANT le vecteur qui porte les revives. Et son gate est
    `options.<+0x45> ? true : IsSteppable(killed)`, avec `+0x45 = 1` sous
    `KillUnitOperationOptions$$ForSteppable` : **un CRUSHE le recoit sans condition**. Le port,
    qui ne le lisait pas, ressuscitait donc un crushe que le natif refuse -- degradation
    PERMISSIVE, donc invisible en self-play. Mesure : `probe_462r4br6_revive_apres_crush.py`.

    `HasHealBlockers` reste non modelise -> non-bloquant (residu inchange, direction PERMISSIVE)."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or int(hc.hp) >= 1:        # GetStat(Health,0) < 1 : doit etre mort
        return False
    fl = e.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.PREVENT_REVIVE):
        return False                                         # NOT HasFlag(unit, 0xd) -- cf. docstring
    ht = entities.has_trait
    if ht is None:
        return True                                          # pas de resolveur trait -> defaut revivable
    if ht(target_liveunit, PERMADEATH):                      # NOT HasTrait(PermaDeath=1050)
        return False
    return is_affected_by_heal_type(ht, target_liveunit, heal_type)   # IsAffectedByHealType(healType)


class _ReviveEffectCore:
    """Coeur PARTAGE de la base `ReviveEffect` (trigger IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger + behaviour IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour). Mixe dans
    les DEUX rails du port (`ReviveEffectAbility` pour un effet pose par un PASSIF -> registre
    `ABILITY_TRIGGERS` ; `ReviveEffectTrigger` pour un effet pose par une ACTIVE -> registre
    `EFFECT_TRIGGERS`) : cote natif c'est le MEME `ReviveEffect`, seule change la facon dont l'effet
    arrive sur son porteur.

    Une sous-classe concrete fixe :
      * `ability_id`           -- cle gameconfig des vars ('hp') / constantes ('chance')
      * `revive_on_overkill`   -- virtuel `get_ReviveOnOverkill` @vtable+0x738 (False = « unless Overkilled »)
      * `remove_effect`        -- champ 0x488 du ctor : False = DeactivateEffect (once-per-turn, reactive
                                  au turn-start) ; True = RemoveEffect (one-shot definitif)
      * `create_target_filter` -- virtuel @vtable+0x758 (le SEUL noeud specifique a chaque consommateur)"""
    ability_id: str = ""
    revive_on_overkill: bool = False                # get_ReviveOnOverkill @vtable+0x738 (slot 96)
    heal_type: int = 0                              # get_HealType         @vtable+0x748 (slot 97)
    remove_effect: bool = False                     # champ 0x488 (ctor) : DeactivateEffect vs RemoveEffect
    effect_type: int = -1                           # EffectType du ReviveEffect (pour RemoveEffect)
    hp_var: str = "hp"
    chance_is_constant: bool = True                 # GetReviveChance = GetNumberConstant(config, 0x2a)
    # Valeur du `GetReviveChance` (@vtable+0x768) quand l'ability n'a PAS de constante 'chance' dans le
    # gameconfig. Ce N'EST PAS un defaut de confort : `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant`
    # delegue a `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` qui **LANCE UNE `System.Exception`** si la cle est absente
    # du dictionnaire, et `GetReviveChance` est **ABSTRAIT dans la base** (slot 0x768 de `ReviveEffect` =
    # stub abstrait @1801e6080, lu LIVE) -> toute sous-classe DOIT l'implementer. Celles dont la config
    # n'a pas 'chance' (RitesOfMorkai, ReanimationBeam) l'overrident par un corps LITTERAL, folde par ICF
    # et donc sans symbole propre -- mais la table `methodPointers` du PE le donne quand meme :
    # @0x3100890 (RitesOfMorkai) et @0x31006b8 (ReanimationBeam) valent tous deux **meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70**, dont les
    # octets sont `b8 64 00 00 00 c3` = `mov eax,100 ; ret`. => **100, LU** (plus une hypothese, #89/B2).
    default_chance: Optional[int] = None

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """Virtuel @vtable+0x758 -- le seul noeud specifique. `entities` = ctx DSL (caster=owner du trigger,
        target=le mourant)."""
        raise NotImplementedError

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is None:
            return False
        # DeactivateEffect (once-per-turn) : l'effet est-il encore ACTIF ce tour ? (variante RemoveEffect :
        # le gate est le retrait de l'effet lui-meme, deja filtre par `collect_effect_triggers`.)
        if (not self.remove_effect) and ouc.revive_used_this_turn:
            return False
        dying = ev.dying_id
        if dying is None:
            return False
        if state.get_entity(dying) is None:
            return False
        # IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath(target, ignoreOverkill=get_ReviveOnOverkill) -> IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent :
        # byte==0 -> AJOUTE `NOT(HasFlag(dying, 8=overkill))` ; byte!=0 -> AUCUN gate overkill.
        if (not self.revive_on_overkill) and ev.overkill:
            return False
        # Contexte DSL (caster=owner, target=dying) pour has_trait/positions
        entities = entities_from_state(state, self.owner_id, dying)
        tgt = entities.target
        if tgt is None:
            return False
        # CanBeRevived(target, get_HealType@0x748)  (IdunBattle.Core.Services.BattleQuery$$CanBeRevived)
        if not can_be_revived(entities, tgt, dying, state, heal_type=self.heal_type):
            return False
        # CreateTargetFilter (virtuel @+0x758)
        return bool(self.create_target_filter(state, ev, entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # chance = GetReviveChance = GetNumberConstant(config, 0x2a='chance')
        chance = ability_var(self.ability_id, "chance", is_constant=self.chance_is_constant)
        if chance is None:
            chance = self.default_chance          # cf. `default_chance` (override litteral cote natif)
        if chance is None:
            return None
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        level, mult = self.revive_level(state)
        create_target_trigger_behaviour(int(chance), self.ability_id, self.hp_var,
                                        remove_effect=self.remove_effect,
                                        effect_type=self.effect_type,
                                        level=level, mult=mult,
                                        heal_type=self.heal_type).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        consumed = any(n in ("DeactivateReviveEffect", "RemoveReviveEffect") for n, _ in ectx.emitted)
        return {"ability": self.ability_id, "owner": self.owner_id, "dying": ev.dying_id,
                "chance": int(chance), "revives": revives, "gate_consumed": consumed,
                "rolled": state.rng is not None}


class ReviveEffectAbility(_ReviveEffectCore, TriggeredAbility):
    """Rail PASSIF : le `ReviveEffect` est pose d'office par un passiveAbility du porteur (Narthecium,
    TaintedNarthecium) -> collecte par `ABILITY_TRIGGERS[<passiveAbility>]`."""
    event_id = EventTriggerType.PreUnitDeath        # OnPreDeath -> OnDeathEvent(eventType=1)
    fire_on_death = False                           # owner (porteur) doit etre VIVANT au fire

    def revive_level(self, state: State):
        """`abilityState` du `GetReviveHP` = celui du PASSIF du porteur (l'effet est pose d'office par ce
        passif) -> `passive_ability_level` + `ability_variables_multiplier` du porteur."""
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None, 100
        return (getattr(sc.ctx, "passive_ability_level", None),
                getattr(sc.ctx, "ability_variables_multiplier", 100))


class ReviveEffectTrigger(_ReviveEffectCore, EffectTrigger):
    """Rail EFFET : le `ReviveEffect` est POSE par une ability ACTIVE (RitesOfMorkai, ReanimationBeam)
    -> il apparait dans `state.effects` du porteur et est collecte par `EFFECT_TRIGGERS[effect_type]`."""
    event_id = EventTriggerType.PreUnitDeath        # OnPreDeath -> OnDeathEvent(eventType=1)

    def revive_level(self, state: State):
        """`abilityState` du `GetReviveHP` = celui de l'ABILITY ACTIVE qui a POSE l'effet (portee par
        l'effet, pas par l'unite qui le subit) -> on lit le niveau/multiplicateur SUR L'EFFET
        (`BaseEffect.active_ability_level`/`ability_level`, `ability_variables_multiplier`), jamais sur le
        porteur (un allie inspire peut avoir un tout autre niveau que Baldr)."""
        eff = getattr(state, "effects", None)
        if eff is not None:
            for e in (eff.by_unit.get(int(self.owner_id)) or []):
                if e.effect_type == self.effect_type:
                    lvl = e.active_ability_level if e.active_ability_level is not None else e.ability_level
                    return lvl, (e.ability_variables_multiplier or 100)
        return None, 100


def are_friends(state: State, a_id: int, b_id: int) -> bool:
    """`DSLFactory.AreFriends(self@0x148, target@0x178)` -- meme equipe (`OwnerComponent.team`). Present dans
    le filtre de Narthecium/TaintedNarthecium/ReanimationBeam (PAS de RitesOfMorkai, qui est OwnerIsTarget)."""
    ea, eb = state.get_entity(a_id), state.get_entity(b_id)
    if ea is None or eb is None:
        return False
    oa, ob = ea.get_component(OwnerComponent), eb.get_component(OwnerComponent)
    return oa is not None and ob is not None and oa.team == ob.team
