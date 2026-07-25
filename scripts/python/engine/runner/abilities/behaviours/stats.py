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


class RefreshDynamicStatModifierValue(AbilityBehaviour):
    """`Idun.Source.IdunBattle.Logic.Entities.Behaviours.RefreshDynamicStatModifierValueBehaviour` — 2e volet
    (`op_BitwiseAnd`) de la factory `IdunBattleLogic.Entities.DSLFactory$$AbilityAreaDamage` :
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

    `guard` (optionnel, defaut None) = predicat par-unite `(entities, ectx, unit_dict) -> bool` : quand
    fourni, une unite dont la garde est FAUSSE est EXCLUE du set (jamais soignee, absente de `heals`). Sert a
    porter la garde `Healable` du `HealableUnitsSelector` natif COTE MUTATION (case-220 1037
    RevitalizingMalignancy : HP<max ET non-mechanical) sans creer un noeud selecteur dedie. None = comportement
    historique inchange (lifesteal SpiritLeech)."""
    __slots__ = ("targets_sel", "amount_fn", "guard")

    def __init__(self, targets_sel: TargetsSelector, amount_fn, guard=None):
        self.targets_sel, self.amount_fn, self.guard = targets_sel, amount_fn, guard

    def execute(self, entities, ectx):
        from ...operations.heal import HealUnitOperation
        state = ectx.state
        amount = int(self.amount_fn(entities, ectx) or 0)
        heals: list = []
        if state is not None and amount > 0:
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
                healed = HealUnitOperation.execute(state, tid, amount, source_id=src)
                heals.append({"target": tid, "healed": healed})
        ectx.emit("Heal", amount=amount, heals=heals)
        return OperationResult.ok()


class ChangeStat(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ChangeStat` -> `IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute` : applique une
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
    Emet 'ChangeStat'. PUR (stop=False)."""
    __slots__ = ("target_sel", "stat_type", "mode", "source", "amount")

    def __init__(self, target_sel: TargetsSelector, stat_type: int, mode: str, source, amount=0):
        self.target_sel, self.stat_type, self.mode = target_sel, int(stat_type), mode
        self.source, self.amount = source, amount

    def execute(self, entities, ectx):
        from ...operations.stat_ops import apply_change_stat, revert_change_stat
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
                val = apply_change_stat(state, uid, self.stat_type, self.source, amt)
                ectx.emit("ChangeStat", unit=uid, stat=self.stat_type, mode="add", amount=amt, value=val)
        return OperationResult.ok()


class SubtractHealthPercent(AbilityBehaviour):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` volet SELF-LOSS -> `ChangeStat(Self@0x160,
    Position(Health=5, current), mode 3 = Subtract, PercentageOf(StatAmount(Self, Health, current),
    ConfigConst(hpPct)))` (`IdunBattleLogic.Entities.DSLFactory$$ChangeStat` -> `IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute`
    case 3 : `new = Max(GetStat(Health) - delta, 0)`). Health = stat FILL-UP (`HealthComponent`, PAS un
    `StatComponent`, cf. `SetHealth` + `ChangeStatBehaviour.Execute` GetStat/StatModifier) -> le modifier
    Subtract sur le fill-up = SET du current HP a `Max(hp - delta, 0)` (`HealthComponent.hp`).

    `delta = PercentageOf(current_hp, pct)` = `round_half_even(hp * pct / 100)` (`PercentageOf` mode 0 : le
    4e arg du `IdunBattleLogic.Entities.DSLFactory$$PercentageOf` est 0 au decompile de `ExecuteBehaviour` -> `_round_fix64`
    mode 0 = arrondi banquier ; MEME primitive/mode que `SetHealth` valide bit-exact BlackRage). `pct` lu via
    `ability_var(is_constant=True)` = `GetNumberConstant`/`ConfigConst` (config 1131 : hpPct=25 constante).

    DETERMINISTE (aucun rng) -> ne decale pas l'ordre `state.rng` de l'attaque qui la precede dans
    `ExecuteBehaviour`. Le natif l'execute APRES l'`ExecuteAtomic` des attaques (`Execute` separe) ; l'appelant
    (`JakhalStimmsAbility.execute_behaviour`) respecte cet ordre en l'executant apres l'`AtomicGroup`. `delta`
    ne peut jamais atteindre `hp` (pct<100) -> le sujet ne meurt PAS de son self-loss (pas de death-trigger).
    Emet 'ChangeStat' (mode="subtract"). PUR (stop=False)."""
    __slots__ = ("target_sel", "ability_id", "pct_var")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, pct_var: str = "hpPct"):
        self.target_sel, self.ability_id, self.pct_var = target_sel, ability_id, pct_var

    def execute(self, entities, ectx):
        from fractions import Fraction
        from ....entities.effects.magnitude import ability_var
        from ....entities.stats import StatType
        from ....dsl.base import _round_fix64
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
            # PercentageOf(current_hp, pct) mode 0 (round half-to-even) = delta ; ChangeStat mode 3 Subtract :
            # HealthComponent.hp = Max(hp - delta, 0). SetAbsolute-like (StatModifier), PAS FillUp.Reduce ->
            # ignore le plancher minimal_health (aligne SetHealth : mutation directe de hc.hp).
            delta = _round_fix64(Fraction(hp * int(pct), 100), 0)
            new_hp = max(hp - delta, 0)
            hc.hp = new_hp
            ectx.emit("ChangeStat", unit=uid, stat=int(StatType.HEALTH), mode="subtract",
                      amount=delta, value=new_hp)
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
    Lucien MaxHealth 15060) : hp 9035 -> 4518 = 15060*30//100 (SetAbsolute a 30%)."""
    __slots__ = ("target_sel", "ability_id", "pct_var")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, pct_var: str = "hpPct"):
        self.target_sel, self.ability_id, self.pct_var = target_sel, ability_id, pct_var

    def execute(self, entities, ectx):
        from fractions import Fraction
        from ....entities.effects.magnitude import ability_var
        from ....dsl.base import _round_fix64
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
            sc = e.get_component(StatsComponent)
            level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
            pct = ability_var(self.ability_id, self.pct_var, level)     # ConfigVar(hpPct) par niveau
            if pct is None:
                continue
            # PercentageOf(MaxHealth, hpPct%) mode 0 = Round half-to-even (`_round_fix64` mode 0), PAS floor
            # (bit-exact vs live 4518 = round(15059*30/100=4517.7) ; floor donnerait 4517). SetAbsolute -> hp.
            new_hp = _round_fix64(Fraction(int(hc.hp_max) * int(pct), 100), 0)
            hc.hp = new_hp
            ectx.emit("SetHealth", unit=uid, hp=new_hp, pct=int(pct))
        return OperationResult.ok()
