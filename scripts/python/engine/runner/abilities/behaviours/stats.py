"""Feuilles DSL de mutation de STATS/PV runner-couplees : `Heal` (soin), `ChangeStat` (modification de
stat par-source), `SetHealth` (SET du HP courant a un % du max). Wrappers au-dessus de
`runner/operations/heal.py` + `stat_ops.py`. Namespace natif `Entities.Behaviours.*`.

C'est ICI qu'atterrira la feuille `AddStaticStatModifierEffect` (levier transverse #1 de la campagne
case-220 : buffs permanents/durees sur SELECTEUR / ToOwner)."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ....entities.traits.unit_trait import UnitTrait
from ...components import HealthComponent, StatsComponent
from ....dsl.base import _round_fix64
from ....entities.effects.magnitude import ability_var
from ....entities.stats import StatType
from ....entities.stats import StatType, StatPart
from ...operations.effects import AddEffectOperation
from ...operations.heal import HealUnitOperation
from ...operations.repair import RepairUnitOperation
from ...operations.stat_ops import apply_change_stat, revert_change_stat
from ...operations.stat_ops import apply_stat_override


class RefreshDynamicStatModifierValue(AbilityBehaviour):
    """`Idun.Source.IdunBattle.Logic.Entities.Behaviours.RefreshDynamicStatModifierValueBehaviour` — 2e volet
    (`op_BitwiseAnd`) de la factory `IdunBattleLogic.Entities.DSLBehaviors$$AbilityAreaDamage` :
        `AttackWithAbilityDamage(caster, Units(area), amount, profile, src)
         & RefreshDynamicStatModifierValueBehaviour(AllAliveMachinesSelector(area))`
    Le natif RE-EVALUE la valeur des stat-modifiers DYNAMIQUES (aura/adjacence) des unites VIVANTES de la
    zone apres le degat de zone — la nova peut tuer des voisins et donc changer les sources d'aura.

    Le port n'a AUCUNE machinerie de stat-modifier dynamique a rafraichir (les auras sont recalculees a la
    lecture par `defender_fixed_armor`/`attacker_modifiers`, pas mises en cache) -> ce noeud est un
    STRUCTURAL NO-OP, porte pour que l'arbre reste isomorphe au `CreateBehaviour` natif (meme precedent que
    `Inform`/`KillDeadUnits`). Deterministe, aucune mutation, aucun tirage -> n'altere PAS l'ordre
    `state.rng` du volet degat qui le precede dans le `&`. Emet 'RefreshDynamicStatModifierValue'
    (diagnostic). PUR."""
    __slots__ = ("target_sel",)

    def __init__(self, target_sel: TargetsSelector):
        self.target_sel = target_sel

    def execute(self, entities, ectx):
        ectx.emit("RefreshDynamicStatModifierValue",
                  targets=[u.get("id") for u in _units_of(self.target_sel, entities)
                           if isinstance(u, dict)])
        return OperationResult.ok()


def is_mechanical(ht, u) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(Mechanical=5) OU HasTrait(LivingMetal=1000)
    OU HasTrait(Vehicle=0x405=1029)`. Les TROIS sont des traits gameconfig reels (126/51/8 units), donc
    lisibles cote runner via `ctx.has_trait`. Confirme LIVE (case-220 : necroWarden=LivingMetal exclu du
    heal). Helper PARTAGE des feuilles Heal a garde `Healable` (1037 RevitalizingMalignancy, 1002
    CombatRestoratives) -- co-localise avec `Heal` (son unique consommateur)."""
    return bool(ht(u, int(UnitTrait.Mechanical)) or ht(u, int(UnitTrait.LivingMetal))
                or ht(u, int(UnitTrait.Vehicle)))


def healable_heal_type_0(entities, ectx, u) -> bool:
    """Garde `Healable` de la feuille `Heal` (prerequis case-220, `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select`
    + heal type 0) : une unite est soignable par un HEAL de type 0 ssi elle est
      (a) ENDOMMAGEE  : HP < max                                  (IsDamaged du HealableUnitsSelector) ET
      (b) affectee    : `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, 0)`
                        = `HasTrait(AffectedByHealAndRepair=0x421)` OU `NOT IsMechanical`.
    IsMechanical = Mechanical(5) | LivingMetal(1000) | Vehicle(1029) (mirror IdunBattle.Entities.UnitExtensions$$IsMechanical). HP<max est aussi
    garanti aval par `HealUnitOperation` (FillUp rend 0 si plein) ; la garde ICI EXCLUE en plus la cible du
    set (une unite full-HP / mechanical n'apparait pas dans `heals`), fidele au fait que le natif pre-filtre
    via `HealableUnitsSelector` AVANT le split. Confirme LIVE (case-220 1037 : necroWarden mech blesse -> +0 ;
    allie full-HP -> +0). Helper PARTAGE (1037 + 1002) -- co-localise avec `Heal`."""
    state = ectx.state
    uid = u.get("id") if isinstance(u, dict) else None
    e = state.get_entity(uid) if (state is not None and uid is not None) else None
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None or int(hc.hp) >= int(hc.hp_max):
        return False                                          # non endommagee -> non Healable
    ht = entities.has_trait
    if ht is None:
        return True                                           # pas de resolveur trait -> defaut affecte
    # IsAffectedByHealType(unit, 0) : AffectedByHealAndRepair(0x421) OU non-Mechanical.
    return bool(ht(u, int(UnitTrait.AffectedByHealAndRepair)) or not is_mechanical(ht, u))


class Heal(AbilityBehaviour):
    """`DSLFactory.Heal(source, targets, amount) @...` -> `HealBehaviour.Execute` : soigne CHAQUE unite du
    selecteur `targets_sel` de `amount_fn(entities, ectx)` PV, via l'Operation portee `HealUnitOperation.
    execute` (mutation PV, plafond `hp_max`, gate `Cursed`). Wrapper MINCE au-dessus du mutateur ECS (mirror
    du 3e volet de `SpiritLeech.ExecuteBehaviour` = lifesteal). Le montant est calcule UNE fois par
    `amount_fn` = FOLD du `SetCache(PercentageOf(LastAttackDamageMade, ...))` natif (le Heal natif lit un
    montant CACHE derive de la derniere attaque ; l'`amount_fn` nommee (mirror `GetHealAmountForExecution`)
    le recompute en lisant le total de la derniere `AttackWithAttackDamage` dans `ectx.emitted`). `source`
    de soin = `ctx.caster`. No-op si montant <= 0. Emet 'Heal' (amount + heals=[{target, healed}]). PUR.

    `amount_fn` accepte aussi un SCALAIRE deja resolu (fold d'un `Direct(GetVariableForLevel(...))`).

    `guard` (optionnel, defaut None) = predicat par-unite `(entities, ectx, unit_dict) -> bool` : quand
    fourni, une unite dont la garde est FAUSSE est EXCLUE du set (jamais soignee, absente de `heals`). Sert a
    porter la garde `Healable` du `HealableUnitsSelector` natif COTE MUTATION (case-220 1037
    RevitalizingMalignancy : HP<max ET non-mechanical) sans creer un noeud selecteur dedie. None = comportement
    historique inchange (lifesteal SpiritLeech).

    `options` = les DEUX fabriques du build, transcrites en `scope`/`remove_effects` -- STRICT pendant
    de `Repair`, ajoute par #520 (elles etaient purement et simplement ABSENTES de cette feuille) :
      * `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal`       -> `(0, True)`  (defaut) ;
      * `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate` -> `(1, False)`.

    ⚠ LE DEFAUT `ForHeal` N'EST PAS UNE COMMODITE : c'est la fabrique de 19 des 25 call-sites du
    build (xrefs relues sur `rnca9r7q6c`). Les SIX qui prennent `ForRegenerate` sont NOMMES, et TROIS
    d'entre eux sont portes -- ils DECLARENT donc `scope=1` a leur site :
    `SavageEchoesAbility$$ExecuteBehaviour` (`abilities/bloodangels.py`),
    `TimeFluxAbility$$CreateBehaviour` (`operations/triggers/loki/time_flux.py`) et
    `SanguinaryPriestAbility$$CreateBehaviour` (`operations/triggers/loki/sanguinary_priest.py`,
    #921) ; les trois autres (`MedicusMinistorumAbility`, `LifeStealEffect`,
    `ToughToKill_HealAbility`) ne sont pas portes. Un call-site NEUF lit sa fabrique au decompile ; il
    ne recopie pas ce defaut."""
    __slots__ = ("targets_sel", "amount_fn", "guard", "scope", "remove_effects")

    def __init__(self, targets_sel: TargetsSelector, amount_fn, guard=None,
                 scope: int = 0, remove_effects: bool = True):
        self.targets_sel, self.amount_fn, self.guard = targets_sel, amount_fn, guard
        self.scope, self.remove_effects = int(scope), bool(remove_effects)

    def execute(self, entities, ectx):
        state = ectx.state
        heals: list = []
        amount = 0
        if state is not None:
            src = (entities.caster or {}).get("id")
            # `_units_of` NORMALISE le selecteur en list[dict] : un selecteur MONO-unite (`Caster()` =
            # `Self@0x148` de SavageEchoes, qui rend un dict) -> `[dict]` (sinon `for u in dict` itererait
            # les CLES). Backward-compatible : un selecteur deja liste (SpiritLeech `Union(...)`) reste
            # inchange. Meme idiome que `ChangeStat`/`AddEffect`.
            for u in _units_of(self.targets_sel, entities):
                tid = u.get("id") if isinstance(u, dict) else None
                if tid is None:
                    continue
                if self.guard is not None and not self.guard(entities, ectx, u):
                    continue                              # garde Healable (case-220 1037) : HP<max & non-mechanical
                # `amount_fn` = FOLD du noeud montant natif : CALLABLE (montant derive, ex. le
                # `SetCache(PercentageOf(LastAttackDamageMade))` du lifesteal SpiritLeech) ou SCALAIRE
                # deja resolu (`Direct(GetVariableForLevel(...))` d'InspiredToGreatness) -- meme
                # convention que `ChangeStat.amount` / `Repair.amount_fn`.
                # ⚠ IL EST EVALUE **PAR CIBLE**, DANS LA BOUCLE -- mirror de
                # `IdunBattle.Entities.Behaviours.HealBehaviour$$Execute`, dont le
                # `<+0x60>.Calculate(entities)` tombe ENTRE le `get_Current` de l'enumerateur de
                # cibles et l'appel `processor.<slot 0x57>` (meme structure que
                # `RepairBehaviour$$Execute`, citee par `operations/heal.py` et `operations/repair.py`
                # depuis #299/#520). Sur un `Direct(...)` la difference ne s'observe pas ; sur un
                # `RandomAmount` SI -- `SanguinaryPriestAbility$$CreateBehaviour` (#921) donne DEUX
                # tirages INDEPENDANTS a deux allies adjacents. Le hissage hors boucle qui vivait ici
                # consommait en plus un tirage FANTOME quand le selecteur ne rend AUCUNE cible, ce que
                # le natif ne fait jamais (il n'entre pas dans la boucle).
                amount = int((self.amount_fn(entities, ectx) if callable(self.amount_fn)
                              else self.amount_fn) or 0)
                if amount <= 0:
                    continue                              # no-op a montant <= 0 (comportement conserve)
                # `healer` = `<selecteur@+0x50>` : le SOIGNEUR, `Caster` sur les call-sites lus. Il
                # n'etait PAS transmis a l'Operation avant #520 (`source_id` etait un parametre MORT),
                # alors que le gate natif `EntityCanBeHealed` en depend (`caster != null &&
                # HasFlag(caster, CanHealFullHealthUnits)`).
                healed = HealUnitOperation.execute(state, src, tid, amount,
                                                   scope=self.scope,
                                                   remove_effects=self.remove_effects)
                heals.append({"target": tid, "healed": healed, "amount": amount})
        # `amount` = le montant de la DERNIERE cible evaluee (l'unique quand la formule est
        # deterministe -- le cas de tous les call-sites portes avant #921). Le montant PAR CIBLE, seul
        # exact sous un `RandomAmount`, est dans chaque entree de `heals`.
        ectx.emit("Heal", amount=amount, heals=heals)
        return OperationResult.ok()


def repairable_heal_type_1(entities, ectx, u) -> bool:
    """Garde de la feuille `Repair` -- symetrique EXACT de `healable_heal_type_0`, pour le heal type 1
    (REPARATION) : l'unite est reparable ssi
      (a) ENDOMMAGEE (HP < max) -- meme pre-filtre `HealableUnitsSelector` ;
      (b) `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, 1)`
          = `HasTrait(AffectedByHealAndRepair=0x421)` OU **IsMechanical** (le complementaire du
          type 0, qui exige NON-mechanical) -- i2 : « Cannot be healed, but can be repaired instead ».
    IsMechanical = Mechanical(5) | LivingMetal(1000) | Vehicle(1029) (helper partage `is_mechanical`).
    Sans resolveur de trait -> False (conservateur : c'est la branche `Heal` qui prend le relais dans le
    `If(IsRepairable, Repair, Heal)` natif)."""
    state = ectx.state
    uid = u.get("id") if isinstance(u, dict) else None
    e = state.get_entity(uid) if (state is not None and uid is not None) else None
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None or int(hc.hp) >= int(hc.hp_max):
        return False
    ht = entities.has_trait
    if ht is None:
        return False
    return bool(ht(u, int(UnitTrait.AffectedByHealAndRepair)) or is_mechanical(ht, u))


class Repair(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$Repair(mechanic, selector, amount, source, options)` ->
    `IdunBattle.Entities.Behaviours.RepairBehaviour$$Execute` -- MIRROR du decompile :

        mechanic = SelectSingle(+0x50)                 # le REPARATEUR (`Caster` sur les 3 call-sites)
        foreach target in Select(+0x58) :              # les cibles
            amount = (+0x60).Calculate(entities)
            processor.<slot 0x58>(mechanic, target, amount,
                                  options.scope@+0x10, options.removeEffects@+0x14, source@+0x68)

    Le slot 0x58 est `Core.Services.OperationProcessor$$RepairUnit` ->
    `IdunBattle.Operations.RepairUnitOperation$$Execute`, PORTE depuis #299
    (`runner/operations/repair.py`). AVANT #299 cette feuille appelait `HealUnitOperation` : le
    raccourci mutait bien les PV mais COURT-CIRCUITAIT les trois etages propres a la reparation --
    le gate `AttackQuery$$EntityCanBeRepaired`, le `RepairModifier` de la CIBLE et les caps de
    `PredictRepair`. Frontiere #149 respectee : la feuille reste DECLARATIVE, l'Operation en dessous
    est imperative.

    `options` = les DEUX fabriques du build, transcrites en `scope`/`remove_effects` :
      * `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair`     -> `(0, True)`  (defaut) ;
      * `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRegenerate` -> `(1, False)`.

    `guard` (optionnel) = predicat par-unite `(entities, ectx, unit_dict) -> bool`, pendant EXACT du
    `guard` de `Heal` : il porte le pre-filtre `HealableUnitsSelector` d'un call-site qui en a un.
    ⚠ Les call-sites n'en ont PAS tous : `RepairAbility$$CreateBehaviour` (28/1119) passe le
    selecteur NU (`ActiveTarget`), et c'est le gate de l'Operation qui tranche -- d'ou `None`.

    Call-sites portes : `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour`
    (28 `Repair` et, par heritage, 1119 `Repair_GalvanicField`) et
    `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal`
    (1082 : `If(IsRepairable(sel), Repair(caster, sel, Direct(amt), AbilityOrEffect(0x43a)),
    Heal(caster, sel, Direct(amt)))`, garde `repairable_heal_type_1`).
    `source`/`abilityOrEffect` (attribution) n'a pas d'observable d'etat porte -> non modelise.
    Emet 'Repair'. PUR."""
    __slots__ = ("targets_sel", "amount_fn", "guard", "scope", "remove_effects")

    def __init__(self, targets_sel: TargetsSelector, amount_fn, guard=None,
                 scope: int = 0, remove_effects: bool = True):
        self.targets_sel, self.amount_fn, self.guard = targets_sel, amount_fn, guard
        self.scope, self.remove_effects = int(scope), bool(remove_effects)

    def execute(self, entities, ectx):
        state = ectx.state
        amount = int(self.amount_fn(entities, ectx) if callable(self.amount_fn) else self.amount_fn)
        repairs: list = []
        if state is not None and amount > 0:
            # `mechanic` = `SelectSingle(+0x50)` : le REPARATEUR, `Caster` sur les 3 call-sites lus.
            src = (entities.caster or {}).get("id")
            for u in _units_of(self.targets_sel, entities):
                tid = u.get("id") if isinstance(u, dict) else None
                if tid is None:
                    continue
                if self.guard is not None and not self.guard(entities, ectx, u):
                    continue
                repairs.append({"target": tid,
                                "repaired": RepairUnitOperation.execute(
                                    state, src, tid, amount,
                                    scope=self.scope, remove_effects=self.remove_effects)})
        ectx.emit("Repair", amount=amount, repairs=repairs)
        return OperationResult.ok()


class ChangeStat(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat` -> `IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute` : applique une
    MODIFICATION DE STAT (`ModifyStatMessage` -> `UnitStats.Transform`) sur le(s) sujet(s) de `target_sel`,
    stat `stat_type` (natif `Position(statType,0,0)`), selon `mode` (lu au decompile IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute, champ
    +0x68) :
        0 = SetAbsolute (new = delta - GetStat)           2 = Add       (new = GetStat + delta)
        1 = Clamp/Min-Max (Min(Max(GetStat+delta,0),max)) 3 = Subtract  (new = Max(GetStat - delta, 0))
        4 = source-scaled (StatModifier depuis une source)   -- seuls 2/3 sont portes (usage actuel).
    Porte via `apply_change_stat`/`revert_change_stat` (`operations.stat_ops` = `ModifyStatMessage` apply
    part5 / revert part6, PAR-SOURCE) : `mode="add"` -> `apply_change_stat(+delta)` attribue a `source` ;
    `mode="revert"` -> `revert_change_stat(source)`. Le revert par-source == le natif mode3 `Max(GetStat -
    delta, 0)` TANT QU'aucun autre modifier ne touche la stat entre l'add et le revert -- cas du buff
    NET-NUL scope-attaque (HeroicFusillade encadre son attaque de `ChangeStat(CRIT_DAMAGE, Add, mag)` /
    `ChangeStat(CRIT_DAMAGE, Sub, mag)`). Le combat relit `ctx.stat(stat_type)` AU ROLL (cf.
    `damage._crit_params`) -> un buff pose AVANT l'attaque est OBSERVABLE (crit +mag), retire apres.

    `amount` = int OU callable `(entities, ectx) -> int` (mag calculee LIVE, ex. `extraCritDmg x nbFree`
    lu POST-move). `source` = cle de source PARTAGEE entre l'add et le revert (revert exact par-source).
    Emet 'ChangeStat'. PUR (stop=False).

    HEALTH (5) est une stat FILL-UP (`HealthComponent`, PAS un `StatComponent`) -- meme fait, meme
    foyer que les deux feuilles voisines `SetHealth` (mode 0 SetAbsolute) et `SubtractHealthPercent`
    (mode 3 Subtract), qui mutent toutes deux `hc.hp` DIRECTEMENT. Le mode 2 la traverse donc par la
    MEME porte : le natif construit `StatModifier(Position(Health, Current), GetStat(Health) +
    delta)` (branche `iVar1 == 2` de `IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute`
    -- une valeur ABSOLUE, pas un delta) puis `DSLBehaviors$$Transform` => `hc.hp = hp + delta`.
    Router HEALTH vers `apply_change_stat` ecrirait dans `ctx.stats[5]`, que RIEN ne relit pour les
    PV : le soin serait SILENCIEUSEMENT perdu. Unique porteur a ce jour : `1061 UnbreakableDuty`
    (#572, le « +extraHp de PV COURANTS » qui accompagne le +extraHp de PV MAX).
    AUCUN clamp sur `hp_max`, et c'est DELIBERE : le natif clampe contre un maximum qui vient d'etre
    RELEVE du meme montant par l'`AddStaticStatModifierEffectToOwner(HEALTH)` qui le PRECEDE dans la
    meme sequence -- le clamp natif est donc INERTE sur ce call-site. Cote port,
    `HealthComponent.hp_max` est un CHAMP FIGE que les stat-mods HEALTH (qui vivent dans `ctx.stats`)
    ne relevent PAS : clamper ici introduirait un ecart que le natif n'a pas. Le residu est l'absence
    de propagation stat-mod HEALTH -> `hp_max` (#572-r1), pas ce non-clamp."""
    __slots__ = ("target_sel", "stat_type", "mode", "source", "amount")

    def __init__(self, target_sel: TargetsSelector, stat_type: int, mode: str, source, amount=0):
        self.target_sel, self.stat_type, self.mode = target_sel, int(stat_type), mode
        self.source, self.amount = source, amount

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.target_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            if self.mode == "revert":                     # ChangeStat mode 3 (Subtract) = undo net-nul
                val = revert_change_stat(state, uid, self.stat_type, self.source)
                ectx.emit("ChangeStat", unit=uid, stat=self.stat_type, mode="revert", value=val)
            else:                                         # ChangeStat mode 2 (Add)
                amt = int(self.amount(entities, ectx) if callable(self.amount) else self.amount)
                if self.stat_type == int(StatType.HEALTH):    # stat FILL-UP -> HealthComponent (cf. docstring)
                    e = state.get_entity(uid)
                    hc = e.get_component(HealthComponent) if e is not None else None
                    if hc is None or hc.hp is None:
                        continue
                    val = int(hc.hp) + amt                    # `GetStat(Health) + delta`, valeur ABSOLUE
                    hc.hp = val
                else:
                    val = apply_change_stat(state, uid, self.stat_type, self.source, amt)
                ectx.emit("ChangeStat", unit=uid, stat=self.stat_type, mode="add", amount=amt, value=val)
        return OperationResult.ok()


class SubtractHealthPercent(AbilityBehaviour):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` volet SELF-LOSS -> `ChangeStat(Self@0x160,
    Position(Health=5, current), mode 3 = Subtract, PercentageOf(StatAmount(Self, Health, current),
    ConfigConst(hpPct)))` (`IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat` -> `IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute`
    case 3 : `new = Max(GetStat(Health) - delta, 0)`). Health = stat FILL-UP (`HealthComponent`, PAS un
    `StatComponent`, cf. `SetHealth` + `ChangeStatBehaviour.Execute` GetStat/StatModifier) -> le modifier
    Subtract sur le fill-up = SET du current HP a `Max(hp - delta, 0)` (`HealthComponent.hp`).

    `delta = PercentageOf(current_hp, pct)` = `round_half_even(hp * pct / 100)` (`PercentageOf` mode 0 : le
    4e arg du `IdunBattleLogic.Entities.DSLFormulas$$PercentageOf` est 0 au decompile de `ExecuteBehaviour` -> `_round_fix64`
    mode 0 = arrondi banquier ; MEME primitive/mode que `SetHealth` valide bit-exact BlackRage). `pct` lu via
    `ability_var(is_constant=True)` = `GetNumberConstant`/`ConfigConst` (config 1131 : hpPct=25 constante).

    DETERMINISTE (aucun rng) -> ne decale pas l'ordre `state.rng` de l'attaque qui la precede dans
    `ExecuteBehaviour`. Le natif l'execute APRES l'`ExecuteAtomic` des attaques (`Execute` separe) ; l'appelant
    (`JakhalStimmsAbility.execute_behaviour`) respecte cet ordre en l'executant apres l'`AtomicGroup`. `delta`
    ne peut jamais atteindre `hp` (pct<100) -> le sujet ne meurt PAS de son self-loss (pas de death-trigger).
    Emet 'ChangeStat' (mode="subtract"). PUR (stop=False).

    `stat_part` = le 3e argument du `IdunBattleLogic.Entities.DSLFormulas$$StatAmount` NATIF, c.-a-d. la
    PART de la stat Health dont le pourcentage est pris — `StatPart.CURRENT` (0) ou `StatPart.MAXIMUM`
    (2). Il est LU ability par ability, jamais uniformise :
      * JakhalStimms (1131) : `StatAmount(Self@0x160, 5=Health, 0)` -> CURRENT (i2 « 25% of his
        current Health ») — DEFAUT, comportement historique inchange ;
      * DakkaDakkaDakka (1171) :
        `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose` =
        `PercentageOf(StatAmount(Self@0x160, 5=Health, **2**), ConfigConst(0x4f healthPct))` -> MAXIMUM
        (i2 « loses 15% of his maximum Health »).
    La SOUSTRACTION porte dans les deux cas sur le PV COURANT (`ChangeStat(..., Position(Health), 3 =
    Subtract, ...)`) : seule la BASE du pourcentage change."""
    __slots__ = ("target_sel", "ability_id", "pct_var", "stat_part")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, pct_var: str = "hpPct",
                 stat_part: int = 0):
        self.target_sel, self.ability_id, self.pct_var = target_sel, ability_id, pct_var
        self.stat_part = int(stat_part)

    def execute(self, entities, ectx):
        from fractions import Fraction
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        pct = ability_var(self.ability_id, self.pct_var, is_constant=True)   # ConfigConst(hpPct)
        if pct is None:
            return OperationResult.ok()
        for u in _units_of(self.target_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None:
                continue
            hp = int(hc.hp)
            # BASE du pourcentage = la part LUE au `StatAmount` natif (CURRENT par defaut ; MAXIMUM
            # pour DakkaDakkaDakka). `hp_max` non capte -> retombe sur le courant (degradation fidele
            # au seul etat disponible, jamais un plafond invente).
            base = hp
            if self.stat_part == int(StatPart.MAXIMUM) and hc.hp_max is not None:
                base = int(hc.hp_max)
            # PercentageOf(base, pct) mode 0 (round half-to-even) = delta ; ChangeStat mode 3 Subtract :
            # HealthComponent.hp = Max(hp - delta, 0). SetAbsolute-like (StatModifier), PAS FillUp.Reduce ->
            # ignore le plancher minimal_health (aligne SetHealth : mutation directe de hc.hp).
            delta = _round_fix64(Fraction(base * int(pct), 100), 0)
            new_hp = max(hp - delta, 0)
            hc.hp = new_hp
            ectx.emit("ChangeStat", unit=uid, stat=int(StatType.HEALTH), mode="subtract",
                      amount=delta, value=new_hp)
        return OperationResult.ok()


class AddStatOverrideEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddStatOverrideEffect(unitSel, effectType, statType,
    amountNode, duration, flag)` -> `IdunBattle.Entities.Behaviours.AddStatOverrideEffectBehaviour$$Execute`
    — MIRROR du DECOMPILE.

    Champs du ctor (`IdunBattle.Entities.Behaviours.AddStatOverrideEffectBehaviour$$.ctor`, LUS) :
    `+0x58` = selecteur d'unites (param_2) · `+0x60` = effectType (param_3) · `+0x64` = statType (param_4)
    · `+0x68` = noeud MONTANT (param_5) · `+0x70` = duree (param_6) · `+0x78` = flag (param_7) ·
    `+0x50` = NULL (selecteur SOURCE optionnel ; les 3 call-sites portes le laissent nul -> source = la
    cible elle-meme, `lVar25 = lVar17` du decompile).

    `Execute` (mirror) :
        foreach unit in (+0x58).Select(entities) :
            entities.subject = unit                       # `param_3[4] = lVar17` = slot SUJET @0x20
            amount = (+0x68).Calculate(entities)          # formule V evaluee AVEC le sujet LIE
            builder = StatOverrideBuilder(effectType, statType, amount, flag)
            AddEffect(target=unit, source=unit, builder, effectType, options{duree=+0x70})

    Le binding du SUJET est ce qui rend `PercentageOfAttackCappedAtMax(Subject@0x180, ...)` correct :
    le montant est calcule sur l'ATTACK de l'unite qui RECOIT l'override, pas sur celle du caster.
    Frontiere #149 respectee : la feuille est DECLARATIVE ; les deux Operations en dessous sont deja
    portees (`AddEffectOperation` = materialisation ECS de l'entite-effet ; `apply_stat_override` =
    `ChangeStat` mode 4 / `Position(statType, part 7 SetOverride)`).

    `stat_override_stats` est pose sur l'instance -> la feuille `RemoveEffect` (qui appelle
    `AddEffectOperation.revert_stat_overrides`) ANNULE exactement cet override, mirror du
    `<Effect>.RevertInternal` -> `ResetStat` (part 8 `RemoveOverride`). C'est le couple
    `AddStatOverrideEffect(0x510) ... RemoveEffect(0x510)` qu'ExemplarOfHate et SternguardFocus
    encadrent autour de leur attaque libre -> NET-ZERO apres le cast (mesure live #112 : l'effet
    `TemporaryStatOverride` n'apparait PAS dans `decisionView.effects` apres le cast).

    `is_modifiable` = le flag natif `+0x78` (=1 sur les call-sites portes) -> `SetOverride(value,
    modifiable)`. Emet 'AddStatOverrideEffect' par unite. PUR (stop=False)."""
    __slots__ = ("unit_sel", "effect_type", "stat_type", "amount", "name", "duration_rounds",
                 "duration_turns", "is_modifiable")

    def __init__(self, unit_sel: TargetsSelector, effect_type: int, stat_type: int, amount,
                 name=None, duration_rounds=None, duration_turns=None,
                 is_modifiable: bool = True):
        self.unit_sel, self.effect_type = unit_sel, int(effect_type)
        self.stat_type, self.amount, self.name = int(stat_type), amount, name
        self.duration_rounds, self.duration_turns = duration_rounds, duration_turns
        self.is_modifiable = bool(is_modifiable)

    def execute(self, entities, ectx):
        from dataclasses import replace
        from .effects import _resolve_duration
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        dur = _resolve_duration(state, self.duration_rounds, self.duration_turns)
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            # `param_3[4] = current` : le natif LIE l'unite courante au slot SUJET (@0x20 = `Subject`
            # / `ActiveTarget@0x180`) AVANT d'evaluer le noeud montant.
            sub = replace(entities, subject=u)
            amt = int(self.amount.evaluate(sub) if hasattr(self.amount, "evaluate") else self.amount)
            # source = la cible elle-meme (`+0x50` NUL sur les call-sites portes -> `lVar25 = lVar17`).
            eff = AddEffectOperation.execute(state, source=uid, target=uid,
                                             effect_type=self.effect_type, name=self.name,
                                             duration_override=dur, value=amt)
            if eff is None:                     # gate « deja present » de l'Operation -> pas de re-pose
                continue
            apply_stat_override(state, uid, self.stat_type, amt, is_modifiable=self.is_modifiable)
            eff.stat_override_stats = [int(self.stat_type)]   # lu par RemoveEffect -> revert (part 8)
            # STAT 18 `ACTIVE_ABILITY_LEVEL` -- cote port, le niveau qui INDEXE les variables d'ability
            # n'est PAS lu via `UnitStats.get_stat(18)` (aucun consommateur) mais via
            # `UnitContext.active_ability_level` (`ability_var` / `ability_attack_params`). L'override
            # doit donc AUSSI etre ecrit la : c'est le seul mirror OBSERVABLE de
            # `GetStat(unit, ACTIVE_ABILITY_LEVEL)`. Consommateur : `InspiredToGreatnessAbility$$
            # ExecuteBehaviour` (1082, magnitude +1496 validee live, #114).
            # `overridden_prev` conserve la valeur precedente sur l'instance d'effet pour un revert exact.
            # RESIDU FLAGGE (#114) : le retrait natif (`InspiredToGreatness_OverrideLevelEffect$$
            # CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster`, au PROCHAIN cast du porteur) n'est
            # pas branche offline -> l'override PERSISTE apres la 2e utilisation. Sans consequence
            # pratique (le porteur n'a droit qu'a UNE utilisation supplementaire).
            applied_ctx = False
            if int(self.stat_type) == int(StatType.ACTIVE_ABILITY_LEVEL):
                e = state.get_entity(int(uid))
                sc = e.get_component(StatsComponent) if e is not None else None
                if sc is not None and sc.ctx is not None:
                    eff.overridden_prev = getattr(sc.ctx, "active_ability_level", None)
                    sc.ctx.active_ability_level = amt
                    applied_ctx = True
            ectx.emit("AddStatOverrideEffect", unit=uid, effect_type=self.effect_type,
                      stat=int(self.stat_type), amount=amt, applied=applied_ctx)
        return OperationResult.ok()


class SetHealth(AbilityBehaviour):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetSetHealthBehaviour` -> `ChangeStat(Health(5), mode 0=SetAbsolute,
    PercentageOf(StatAmount(Health, MAXIMUM=2), ConfigVar(hpPct)))` : SET le HP courant du sujet a
    `hpPct%` de son MaxHealth. Mode 0 SetAbsolute (`IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute` case 0 : la
    modification impose `GetStat(stat) == amount`) ; Health = stat FILL-UP (`HealthComponent`, PAS un
    `StatComponent`) -> le SetAbsolute sur le fill-up = SET du current HP (`HealthComponent.hp = amount`).
    Amount = `hp_max * hpPct // 100` (`PercentageOf(MaxHealth, hpPct%)`). `hpPct` = ability var per-level
    (BlackRage: [30,30,...] = 30%, HORS variablesAffectedByRarityBonus -> multiplier 100).

    DETERMINISTE (aucun rng). C'est le COUT self de BlackRage : Lucien tombe a 30% MaxHealth (HEAL s'il est
    DEJA sous 30%, cf. walk garde 31337 hp=1 -> 30%). Emet 'SetHealth'. PUR (stop=False). MESURE live (31337,
    Lucien MaxHealth 15060) : hp 9035 -> 4518 = 15060*30//100 (SetAbsolute a 30%).

    `amount` (case BL-1029) = le NOEUD MONTANT natif, quand il n'est PAS le `PercentageOf(MaxHealth,
    ConfigVar(hpPct))` de BlackRage. Le vrai invariant partage est le `ChangeStat(sel, Position(Health=5,0),
    mode 0 = SetAbsolute, <noeud montant>)` : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    DrachnyenAbility$$GetSetHealthBehaviour` a EXACTEMENT la meme forme d'appel que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetSetHealthBehaviour` (meme overload
    `DSLBehaviors$$ChangeStat`, meme `Position(5,0,0)`, meme mode 0), seul le noeud montant differe :
    `Min(StatAmount(Owner@0x148, Health=5, MAXIMUM=2), Direct(ConfigVar(0x1d = hp)))`. Fourni ->
    `new_hp = int(amount.evaluate(entities))` (clampe >= 0) et `ability_id`/`pct_var` ne sont pas lus.

    ⚠ `pct_rounding` et `pct_is_constant` sont LUS au call-site natif, jamais supposes -- les deux
    porteurs du chemin POURCENTAGE divergent sur les DEUX axes (#573) :
      * `...BlackRageAbility$$GetSetHealthBehaviour` : `PercentageOf(., ConfigVar(hpPct), **0**)`
        -> `AAmountFormula$$RoundFix64Result` mode 0 = Round half-to-even, et `hpPct` est une
        VARIABLE per-niveau (`AbilityConfiguration$$GetVariableForLevel`) ;
      * `IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetSetHealthBehaviour` :
        `PercentageOf(StatAmount(It@DSLSelectors+0x68, HEALTH=5, MAXIMUM=2),
        ConfigConst(0x4f = healthPct), **2**)` -> mode 2 = **Floor**, et `healthPct` est une
        CONSTANTE (`AbilityConfiguration$$GetNumberConstant`, `constants.healthPct = 50`).
    L'ecart n'est PAS cosmetique : sur un `hp_max` IMPAIR a 50 %, `hp_max/2` tombe pile sur un demi
    -- `floor(15059*50/100) = 7529` la ou le half-to-even rend `7530`. Defauts = les valeurs de
    BlackRage, donc aucun porteur existant ne bouge.

    ⚠ La BOUCLE de cet `execute` EST l'iteration `It` du natif : `StatAmount(It, HEALTH, MAXIMUM)`
    se lit `hc.hp_max` de la cible COURANTE, pas une valeur globale evaluee une fois. C'est ce qui
    permet a BloodChalice de poser 50 % du max de CHAQUE allie, jamais 50 % du max du caster."""
    __slots__ = ("target_sel", "ability_id", "pct_var", "amount", "pct_rounding", "pct_is_constant")

    def __init__(self, target_sel: TargetsSelector, ability_id: str | None = None,
                 pct_var: str = "hpPct", amount=None, pct_rounding: int = 0,
                 pct_is_constant: bool = False):
        self.target_sel, self.ability_id, self.pct_var = target_sel, ability_id, pct_var
        self.amount = amount
        self.pct_rounding, self.pct_is_constant = int(pct_rounding), bool(pct_is_constant)

    def execute(self, entities, ectx):
        from fractions import Fraction
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.target_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp_max is None:
                continue
            if self.amount is not None:                # noeud montant natif explicite (Drachnyen)
                new_hp = max(0, int(self.amount.evaluate(entities)))
                hc.hp = new_hp
                ectx.emit("SetHealth", unit=uid, hp=new_hp, pct=None)
                continue
            sc = e.get_component(StatsComponent)
            level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
            # `ConfigVar(hpPct)` per-niveau (BlackRage) OU `ConfigConst(healthPct)` (BloodChalice) --
            # `GetVariableForLevel` vs `GetNumberConstant`, LU au call-site, jamais deduit du nom.
            pct = (ability_var(self.ability_id, self.pct_var, is_constant=True)
                   if self.pct_is_constant else ability_var(self.ability_id, self.pct_var, level))
            if pct is None:
                continue
            # PercentageOf(MaxHealth, pct%) -> `AAmountFormula$$RoundFix64Result` selon le 3e arg NATIF :
            # mode 0 = Round half-to-even (BlackRage ; bit-exact vs live 4518 = round(15059*30/100),
            # floor donnerait 4517), mode 2 = Floor (BloodChalice). SetAbsolute -> hp.
            new_hp = _round_fix64(Fraction(int(hc.hp_max) * int(pct), 100), self.pct_rounding)
            hc.hp = new_hp
            ectx.emit("SetHealth", unit=uid, hp=new_hp, pct=int(pct))
        return OperationResult.ok()
