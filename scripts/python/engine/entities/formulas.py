"""Noeuds VALEUR du DSL = famille `AAmountFormula.Calculate` (kind V) : arithmetique/combinateurs
numeriques + accesseurs config/stat/compteurs runtime.

Mirror du namespace natif `IdunBattle.Entities.Formulas` : les concrets vivent ici, a cote de leurs
freres `entities/{abilities,selectors,triggers,behaviours,effects}` ; la base `AAmountFormula`
(= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory` (`dsl/nodes.py`)."""
from __future__ import annotations

from fractions import Fraction

from ..dsl.base import (AAmountFormula, TargetsSelector, Const, _round_fix64, _effect_field,
                        _default_get_stat, resolve_unit, _units_of)


class Sum(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) + self.b.evaluate(ctx)


class Min(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return min(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Multiply(AAmountFormula):
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) * self.b.evaluate(ctx)


class Difference(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Difference(a,b)` = `Sum(a, Multiply(b, -1))` = a - b."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) - self.b.evaluate(ctx)


class If(AAmountFormula):
    """`DSLFactory.If(cond, a, b)` : `a` si `cond` (bool) sinon `b`. Évalue paresseusement la branche prise."""
    def __init__(self, cond: AAmountFormula, a: AAmountFormula, b: AAmountFormula):
        self.cond, self.a, self.b = cond, a, b

    def calculate(self, ctx):
        return (self.a if self.cond.evaluate(ctx) else self.b).evaluate(ctx)


class ConditionalAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$ConditionalAmount(cond, ifTrue, ifFalse)` (ctor gshared MISLABELE
    « ModuloAbilityTrigger » dans ghidra -- structure lue, jamais le nom) : noeud VALEUR ternaire.
    Factory native DISTINCTE de `IdunBattleLogic.Entities.DSLFactory$$If` (meme semantique cond?a:b, autre singleton) ;
    on la porte sous SON nom pour que les arbres qui la citent restent des homonymes 1:1.
    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateBehaviour` (`ConditionalAmount(HasEffect(Self,
    1098 RammingSpeed_ExtraExplode), ConfigConst(1059 RammingSpeed, extraDmgPct), Get(0))`).
    Evaluation PARESSEUSE de la branche prise (comme `If`)."""
    def __init__(self, cond, a: AAmountFormula, b: AAmountFormula):
        self.cond, self.a, self.b = cond, a, b

    def calculate(self, ctx):
        return (self.a if self.cond.evaluate(ctx) else self.b).evaluate(ctx)


class Max(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Max(a,b)` : `max(a,b)` (singleton DAT_1832457c8, usage prouvé via
    `NonLethalDamage = Min(Max(HP-1, 0), dmg)`)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return max(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Divide(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Divide(a,b,mode)` → `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` :
    `Fix64(a) / Fix64(b)` PUIS `RoundFix64Result(_, mode)` — PAS une division entière. `mode` =
    Ceiling(1)/Floor(2)/Round-half-to-even(0). `b==0` → un arbre valide ne divise jamais par 0
    (laisse remonter l'erreur)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula, mode: int = 0):
        self.a, self.b, self.mode = a, b, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), self.b.evaluate(ctx)), self.mode)


class Half(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Half(a,mode)` = `Divide(a, 2, mode)` — MÊME arrondi Fix64 (pas `a//2`)."""
    def __init__(self, a: AAmountFormula, mode: int = 0):
        self.a, self.mode = a, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), 2), self.mode)


class Double(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Double(a)` = `Multiply(a, 2)` = `a * 2` (entier exact, sans arrondi)."""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return self.a.evaluate(ctx) * 2


class Negative(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Negative(a)` = `Multiply(a, -1)` = `-a`."""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return -self.a.evaluate(ctx)


class PercentageOf(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$PercentageOf(pct, base, mode)` → `PercentageOf.Calculate IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal`
    (Fix64) : `round_mode(pct% * base)` avec arrondis intermédiaires half-to-even à 2 décimales — PAS
    `pct*base//100`. `pct` = pourcentage entier (50 = 50 %). Les arrondis à 2 décimales sont INERTES
    pour des opérandes entières (nos cas) → `round_mode(Fraction(pct*base, 100))` fidèle."""
    def __init__(self, pct: AAmountFormula, base: AAmountFormula, mode: int = 0):
        self.pct, self.base, self.mode = pct, base, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.pct.evaluate(ctx) * self.base.evaluate(ctx), 100), self.mode)


class Count(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Count(selector)` → `IdunBattle.Entities.Formulas.CountFormula$$Calculate` : cardinal du
    sélecteur (nb d'éléments). Retour int >= 0."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        return len(self.selector.evaluate(ctx))


# --- Accesseurs VALEUR (mirror `DSLFactory.X` -> formules natives : config / stat / compteurs). ---

class ConfigConst(AAmountFormula):
    """`DSLFactory.ConfigConst(key)` / `AbilityConfiguration.GetNumberConstant` : constante de config
    d'ability au niveau courant. Ids natifs = enum `AbilityConstantType` (dump.cs TypeDefIndex 24411) :
    0x2f=nrOfHits(47), 0x2b=extraHit(43), 0x48=maxNrOfHits(72), 0x16=range(22). ⚠ `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant`->`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` LÈVE une exception si la clé est ABSENTE (TryGetValue
    échoue -> throw) : une clé référencée par un arbre EST toujours présente dans la config (jamais de
    défaut natif). ⚠ DIVERGENCE assumée : le `default` Python retourne une valeur là où le natif
    THROW — garde-fou offline inerte tant que la clé existe, mais il MASQUERAIT silencieusement une
    clé manquante (verdict validator 2026-07-02 : réserve non bloquante)."""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def calculate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class TotalTimesAttacked(AAmountFormula):
    """`IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate` : compteur runtime d'attaques du caster
    (composant @+0x34). NON capté offline → `ctx.times_attacked` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return ctx.times_attacked or 0


class TimesRepaired(AAmountFormula):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class TotalAttacksMade(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$TotalAttacksMade` = `Entities.Formulas.TotalAttacksMadeFormula` (IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate) :
    nb d'attaques faites par `unit` (compteur runtime). Port on-appearance : la feuille `PerformAIAttack`
    (`runner/abilities/behaviours.py`) pose `_attacks_made` sur le dict de l'enfant (0 si pas d'attaque).
    Unité hors-cast → 0 (compteur général non capté offline, même régime que `TotalTimesAttacked`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("_attacks_made", 0) or 0)


class UnitTurnsStarted(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitTurnsStarted` = `Entities.Formulas.UnitTurnsStartedFormula` (IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate) :
    nb de tours entamés par `unit` (compteur runtime). Le natif compare (via `AmountIsEqual`) le `turnsStarted`
    de l'owner CAPTURÉ au cast (`factory+0xb8`) au `UnitTurnsStarted(child)` → ne retient que les enfants NEUFS
    de CE cast. Le compteur REEL = `GetStat(unit, 0xc=TURNS_STARTED)` (`UnitComponent.turnsStarted@+0x58`,
    incrémenté par `StartTurnOperation`, capté par combatSnapshot #122 et maintenu offline par
    `_bump_turns_started`) → lu via `ctx.get_stat` (le vrai mirror IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate).

    Ordre de résolution : `_turns_started` du dict s'il est PRÉSENT (posé explicitement par `SpawnUnit` sur
    l'enfant frais — le couple `AmountIsEqual(Const(0), UnitTurnsStarted(child))` de GetEmRuntz s'appuie
    dessus), sinon `ctx.get_stat(unit, 0xc)`, sinon 0. Consommateur du compteur RÉEL : la rotation
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` (`Modulo(UnitTurnsStarted(Self), 3, k)`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        from .stats import StatType
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return 0
        if "_turns_started" in u:                    # enfant SPAWNE (SpawnUnit pose 0) — priorite au marqueur
            return int(u.get("_turns_started", 0) or 0)
        gs = getattr(ctx, "get_stat", None)
        if gs is None:
            return 0
        return int(gs(u, int(StatType.TURNS_STARTED), 0) or 0)


class TurnsFromRounds(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$TurnsFromRounds(rounds)` → `IdunBattle.Entities.Formulas.TurnsFromRoundsFormula$$Calculate`
    = `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (interface slot 0x1b) = `count(joueurs du turnOrder,
    PlayerType != 2) * rounds` (RE #174 : PlayerType@+0x20 = config statique, Environment=2 exclu ;
    count = CONSTANTE de bataille). `rounds * ctx.turns_per_round` avec `turns_per_round = count(non-Env)`.
    Defaut 1 = CORRECT pour nos runners 1v1 (count=1 PROUVE par test_effect_stun_live : convert(1)=1) ;
    ne divergerait que dans une bataille count>=2 (non simulee), a capter alors du turnOrder runtime."""
    def __init__(self, rounds: AAmountFormula):
        self.rounds = rounds

    def calculate(self, ctx):
        return self.rounds.evaluate(ctx) * getattr(ctx, "turns_per_round", 1)


class Get(Const):
    """`IdunBattleLogic.Entities.DSLFactory$$Get(value)` = `Const`/`Direct` : enveloppe une valeur littérale int/enum en
    nœud (MÊME singleton DAT_183202d40 + ctor `(value,0)` que `Direct`). Le nom de ctor mislabelé
    `IceTileEffect...d__5` est un trampoline gshared — la classe réelle est le nœud constante, PAS un
    accesseur. (Les overloads IdunBattleLogic.Entities.DSLFactory$$Get/IdunBattleLogic.Entities.DSLFactory$$Get sur arg objet = sélecteurs distincts, hors batch.)"""


class VisualUnitIdFromUnitId(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$VisualUnitIdFromUnitId(unitIdValue)` : noeud VALEUR convertissant un id de
    CONFIG d'unite (ex. `orksOrkBoys`, `GetStringConstant(config, 0)`) en son id VISUEL (ex.
    `orksNpc2OrkBoy`). Le ctor gshared est mislabele `Loki.AutoBot.AutoBotLoopFactory..ctor` par ghidra
    (structure lue : `(factory+0x28 = le service de config d'unites, unitIdValue)`) -- jamais le nom.
    Consommateur lu : `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` / `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour`
    (`UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unitId)), 1)`).

    REDUCTION OFFLINE (documentee, meme classe que celle du noeud `UnitsWithIds`) : le champ `visualId` du
    dict d'unite porte l'id de **CONFIG** pour les unites SPAWNEES par le moteur offline
    (`_spawn_config_grot(visual_id=constants['unitId'])` -> `orksOrkBoys`) et l'id **VISUEL** rendu par
    `decisionView` pour les unites seedees depuis le live (-> `orksNpc2OrkBoy`). Le noeud rend donc les
    **DEUX** formes (`{unitId, gameconfig.unit(unitId).visualId}`), ce qui rend le filtre EXACT dans les
    deux cas -- exactement ce que fait naturellement la constante `affectedUnitIds` de SupremeCommander
    (`"astraSmnGuardsman,astraNpc1Guardsman"`, cf. `UnitsWithIds`). `unit_id` = noeud valeur (`Get`) ou str."""
    def __init__(self, unit_id):
        self.unit_id = unit_id

    def calculate(self, ctx):
        import gameconfig as GC
        uid = self.unit_id.evaluate(ctx) if hasattr(self.unit_id, "evaluate") else self.unit_id
        if not uid:
            return []
        vis = (GC.unit(uid) or {}).get("visualId")
        return [uid, vis] if (vis and vis != uid) else [uid]


class ConfigVar(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$ConfigVar(key)` → `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` :
    `AbilityConfiguration.GetVariableForLevel(key, level)` = valeur du tableau de config SCALÉE par le
    niveau de l'ability. ≠ `ConfigConst` natif (`GetNumberConstant`, valeur fixe hors niveau). Cas
    standard = caster au niveau courant → `ctx.ability_level` ; niveau d'une unité tierce = NON offline.
    ⚠ RÉSERVE (validator) : le `ConfigConst` Python actuel appelle DÉJÀ `get_variable_for_level` — donc
    fait le boulot de ConfigVar, pas de ConfigConst (qui devrait être number-constant fixe). À trancher :
    le wrapper AbilityConfiguration distingue-t-il number-constant (fixe) vs variable-array (par niveau) ?"""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def calculate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


class StatAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$StatAmount(selector, statType, variant, level)` →
    `IdunBattle.Entities.Formulas.StatAmountFormula$$Calculate` : SOMME de `UnitExtensions.GetStat(unit, statType, variant,
    level)` sur toutes les unités du sélecteur (singleton → 1 unité ; multi → somme). `ctx.get_stat`
    fournit les stats réelles ; défaut dégradé = Health via hp (cf. `_default_get_stat`)."""
    def __init__(self, selector: TargetsSelector, stat_type: int, variant: int = 0,
                 level: AAmountFormula | None = None):
        self.selector, self.stat_type, self.variant, self.level = selector, stat_type, variant, level

    def calculate(self, ctx):
        gs = ctx.get_stat or _default_get_stat
        lvl = self.level.evaluate(ctx) if self.level is not None else None
        # `_units_of` normalise le selecteur : un ref-unite SEULE (`Caster()`/`Self@0x148` -> dict) devient
        # `[dict]` (mirror natif = set de 1) ; sans quoi iterer un dict nu rendrait ses CLES (meme piege que
        # `Tiles`/`Sub`). Multi -> SOMME des stats (comme le natif `StatAmountFormula.Calculate`).
        return sum(gs(u, self.stat_type, self.variant, lvl) for u in _units_of(self.selector, ctx))


class UnitNormalAttackType(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitNormalAttackType(entitySelector)` → value-provider lisant le
    `ActiveAbilityComponent.NormalAttackType@0x28` de l'unité = son ActiveAbilityType d'attaque normale
    CONCRET, per-unit (ex. `RighteousRepugnance_NormalAttack`=1182 pour un porteur de RighteousRepugnance).
    Comparé par `AreEqual(..., AbilityOrEffect)` (ActOfFaith accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour : killer == 1182 ?).

    ⚠ Le type CONCRET n'est PAS un champ de l'état runner (state_bridge : id synthétique 17, « non dérivable
    de gameconfig » par le chemin PRÉDICTION). On le RÉSOUT ici depuis le KIT gameconfig de l'unité : une
    ability qui REDÉFINIT l'attaque normale expose un membre d'enum `<ability>_NormalAttack` (14 tels
    membres) — pour chaque ability du kit (`unit_abilities(visualId)` active/passive), si
    `<ability>_NormalAttack` existe dans `ActiveAbilityType`, c'est le normal-attack concret (RighteousRepugnance
    → 1182). Aucune → None (l'unité garde le normal-attack générique, non égal à un `_NormalAttack` nommé →
    `AreEqual` False). None si unité/visualId absent."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        u = resolve_unit(self.selector, ctx)
        vis = (u or {}).get("visualId")
        if vis is None:
            return None
        import gameconfig as GC
        from .active_ability_type import ActiveAbilityType
        names = []
        for _slot, v in (GC.unit_abilities(vis) or {}).items():
            if isinstance(v, str):
                names.append(v)
            elif isinstance(v, dict):
                names.append(v.get("name") or v.get("id"))
            elif isinstance(v, list):
                names += [(x.get("name") if isinstance(x, dict) else x) for x in v]
        for nm in names:
            member = getattr(ActiveAbilityType, f"{nm}_NormalAttack", None) if nm else None
            if member is not None:
                return int(member)
        return None


class ConfigVarForEntity(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$ConfigVar(abilityOrEffect, entity, varKey)` → `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` = `AbilityConfiguration.GetVariableForLevel(varKey, level)` sur la config de l'ability
    `abilityOrEffect`, au NIVEAU de l'`entity` (unité TIERCE, ≠ caster — cf. `ConfigVar` standard qui lit
    `ctx.config`/`ctx.ability_level` du caster). ActOfFaith accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour :
    `ConfigVar(RighteousRepugnance=1107, killer, chance=0x3a=58)` = la chance% du 2e stack, au niveau
    RighteousRepugnance (PASSIVE) du killer. Port : `ability_var(ability_name, var_key, niveau)` avec
    `niveau = ctx.get_ability_level(unit, slot)` (capté offline : `passive_ability_level`/`active_ability_
    level`). `ability_name`/`var_key`/`slot` passés PAR NOM (ids natifs 1107/58 cités par l'appelant) pour
    éviter deux reverse-maps d'enum (AbilityOrEffect/AbilityVariableType) pour un unique usage. None → 0."""
    def __init__(self, ability_name: str, var_key: str, entity_sel: TargetsSelector, slot: str = "passive"):
        self.ability_name, self.var_key = ability_name, var_key
        self.entity_sel, self.slot = entity_sel, slot

    def calculate(self, ctx):
        u = resolve_unit(self.entity_sel, ctx)
        if u is None:
            return 0
        lvl = ctx.get_ability_level(u, self.slot) if ctx.get_ability_level is not None else None
        from .effects.magnitude import ability_var
        return int(ability_var(self.ability_name, self.var_key, lvl) or 0)


class EntityId(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$EntityId(ref)` : id de l'entité résolue (ou None)."""
    def __init__(self, ref):
        self.ref = ref

    def calculate(self, ctx):
        e = self.ref.evaluate(ctx)
        return e.get("id") if isinstance(e, dict) else None


class EffectLevel(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectLevel` : niveau de l'effet COURANT (`ctx.effect`). 0 si absent."""
    def calculate(self, ctx):
        return _effect_field(ctx.effect, "level", 0)
