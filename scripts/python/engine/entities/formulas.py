"""Noeuds VALEUR du DSL = famille `AAmountFormula.Calculate` (kind V) : arithmetique/combinateurs
numeriques + accesseurs config/stat/compteurs runtime.

Mirror du namespace natif `IdunBattle.Entities.Formulas` : les concrets vivent ici, a cote de leurs
freres `entities/{abilities,selectors,triggers,behaviours,effects}` ; la base `AAmountFormula`
(= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory` (`dsl/nodes.py`)."""
from __future__ import annotations

from fractions import Fraction

import hexgeo

from .. import battle_query as _bq
from ..dsl.base import (AAmountFormula, TargetsSelector, Const, _round_fix64, _effect_field,
                        _default_get_stat, resolve_unit, _units_of, _pos, _feet)
from ..services.min_max_damage import min_max_avg
from ..services.movement_query import get_distance
from .active_ability_type import ActiveAbilityType
from .effects.aura import aura_trait, aura_current_range, aura_next_turn_range
from .effects.magnitude import ability_var
from .selectors._shared import _tile_positions
from .stats import StatType


class Sum(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Sum` -> `IdunBattle.Entities.Formulas.SumAmount` --
    MIRROR du decompile. La factory a QUATRE surcharges (2, 3, 4 et 5 branches) qui construisent
    TOUTES la meme classe : `SumAmount$$.ctor(a,b,c,d,e)` ecrit `+0x10 a`, `+0x18 b`, `+0x20 c`,
    `+0x28 d`, `+0x30 e` (les surcharges courtes passent `null` pour les champs restants).

    `SumAmount$$Calculate` (LU) additionne DANS L'ORDRE `a, b, c, d, e` : `a` et `b` sont evalues
    INCONDITIONNELLEMENT, `c`/`d`/`e` chacun sous un `if (champ != 0)`. Le port reproduit cet ordre,
    et c'est ce qui compte : une branche peut CONSOMMER DU RNG (un `ConditionalAmount(Maybe(...))`
    tire un `NextBool` a chaque evaluation), donc permuter les branches changerait le flux de tirages.

    Consommateur a 5 branches : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    PsychicMaelstromAbility$$ExecuteBehaviour` (1 + quatre jets de coup supplementaire)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula, c: AAmountFormula = None,
                 d: AAmountFormula = None, e: AAmountFormula = None):
        self.a, self.b, self.c, self.d, self.e = a, b, c, d, e

    def calculate(self, ctx):
        total = self.a.evaluate(ctx) + self.b.evaluate(ctx)   # `a` et `b` : aucun null-check natif
        for branch in (self.c, self.d, self.e):               # `if (this+0x20/0x28/0x30 != 0)`
            if branch is not None:
                total += branch.evaluate(ctx)
        return total


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


class RandomAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$RandomAmount(minFormula, maxFormula)` ->
    `IdunBattle.Entities.Formulas.RandomAmount$$Calculate` — MIRROR 1:1 du decompile :

        min = this@+0x10.Calculate(entities)          # `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin`
        max = this@+0x18.Calculate(entities)          # `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMax`
        return this@+0x20 /* IPseudoRNG, slot 2 */ (min, max + 1)

    Le `+ 1` sur la borne haute est LU dans le decompile (`(*puVar19)(plVar2, uVar15, iVar16 + 1, ...)`) :
    l'intervalle natif est donc **INCLUSIF des deux cotes**. Le slot 2 de l'interface est
    `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(lo, hi)` (hi EXCLU) -> cote port
    `rng.next_internal(min, max + 1)`, MEME consommation de `genrand_int32` que le natif.

    Le RNG est un CHAMP du noeud (`+0x20`, pose par la factory depuis `DSLFactory+0x18`), PAS une entree
    du contexte -> il est pris AU CONSTRUCTEUR, exactement comme `MaybeTrigger` (cf. `entities/triggers.py`).
    `rng=None` -> pas de tirage calable offline : on rend la borne MIN (degradation deterministe et
    documentee, aucun tirage consomme) ; caler `state.rng` pour exercer/valider.

    Consommateur porte : le DoT de tuile DespoiledGround
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateBehaviour` :
    `RandomAmount(PercentageOf(maxHP, EffectConfig(9)), PercentageOf(maxHP, EffectConfig(10)))`)."""
    def __init__(self, min_node: AAmountFormula, max_node: AAmountFormula, rng=None):
        self.min_node, self.max_node, self.rng = min_node, max_node, rng

    def calculate(self, ctx):
        lo = int(self.min_node.evaluate(ctx))
        hi = int(self.max_node.evaluate(ctx))
        if self.rng is None:
            return lo                                # pas de RNG cale -> borne MIN, aucun tirage
        return self.rng.next_internal(lo, hi + 1)    # `NextInternal(min, max + 1)` = [min, max] inclusif

    # --- les slots de PLAGE : c'est par eux que la DECISION lit ce noeud, jamais par `Calculate` ---
    # `Calculate` ci-dessus est un TIRAGE (il consomme le PRNG) ; une prediction ne peut pas s'en
    # servir. `RandomAmount` est le seul noeud de ce port a porter SES PROPRES `CalculateMin`/`Max`
    # (les noeuds simples heritent du defaut `AAmountFormula` = `Calculate`), donc le slot 4
    # (`AAmountFormula$$CalculateAverage`) prend sur lui la branche « plage » = `(max + min) / 2`
    # ENTIERE, TRONQUEE. Etabli LIVE par `probe_32d_fury.py` (#339) : la feuille Fury tombe sur la
    # moyenne EXACTE des deux cibles, ce qu'un tirage ne pourrait pas faire.
    def calculate_min(self, ctx):
        """`IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin` = `this@+0x10.Calculate`."""
        return int(self.min_node.evaluate(ctx))

    def calculate_max(self, ctx):
        """`IdunBattle.Entities.Formulas.RandomAmount$$CalculateMax` = `this@+0x18.Calculate`."""
        return int(self.max_node.evaluate(ctx))


def percentage_of_attack_capped_at_max(unit_sel: TargetsSelector, cap, pct,
                                       stat_part: int = 0, mode: int = 0) -> AAmountFormula:
    """`IdunBattleLogic.Entities.DSLFactory$$PercentageOfAttackCappedAtMax(unit, statPart, cap, pct, mode)`
    — FACTORY COMPOSITE (elle n'alloue AUCUNE formule dediee), mirror 1:1 du decompile :

        statAmount = StatAmountFormula(unit, statType=0 (ATTACK), statPart, 0, 0)
        pctOf      = DSLFactory.PercentageOf(statAmount, pct, mode)
        return       <noeud 2-champs (cap, pctOf)>

    Le noeud englobant est alloue depuis le singleton de classe `DAT_18324e140`, avec un ctor que ghidra
    affiche `HasUsedActiveAbilityThisTurnTrigger..ctor` (fold gshared 2-champs, NOM FAUX -- cf. l'en-tete
    de `dsl/base.py`). **Sa semantique est PROUVEE par IDENTITE DE SINGLETON, pas deduite du nom de la
    factory** : `IdunBattleLogic.Entities.DSLFactory$$Min(a, b)` alloue EXACTEMENT le meme
    `DAT_18324e140` avec le meme ctor 2-champs. Donc `PercentageOfAttackCappedAtMax = Min(cap, pctOf)`.
    CONFIRME LIVE (#112, runner MC1_67 au contact) : `ExemplarOfHate` sur cible Chaos ->
    `UnitStats_Attack_Override = 2008` = `min(maxDmg[50]xmult180 = 5983, round(Attack_CURRENT 2008 x
    dmgPct 100 / 100))` ; idem probe_217 TheQuickening (meph 1204 / ally 4818).

    `stat_part` = le `StatPart` natif passe par l'appelant -- **0 = Current**
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$GetAttackDamage`) vs
    **3 = Initial** (`IdunBattleLogic.Entities.Abilities.Active.Loki.SternguardFocusAbility$$ExecuteBehaviour`
    et `...$$GetOverrideAttackDamageAmount`) : difference LUE au decompile, jamais uniformisee.
    `cap`/`pct` = noeuds VALEUR (`ConfigVar(0xd=maxDmg)` / `ConfigVar(0x4a=dmgPct)` sur les call-sites
    portes) ou scalaires (collapse V quand la config est resolue imperativement)."""
    cap_n = cap if hasattr(cap, "evaluate") else Const(int(cap))
    pct_n = pct if hasattr(pct, "evaluate") else Const(int(pct))
    return Min(cap_n, PercentageOf(pct_n, StatAmount(unit_sel, int(StatType.ATTACK), int(stat_part)),
                                   mode))


class Count(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$Count(selector)` → `IdunBattle.Entities.Formulas.CountFormula$$Calculate` : cardinal du
    sélecteur (nb d'éléments). Retour int >= 0.

    ⚠ `_units_of` NORMALISE l'évaluation : côté natif un sélecteur rend TOUJOURS une collection, mais le
    port laisse les accesseurs mono-entité (`Target()`/`Caster()`/`Subject()`) rendre le dict NU — sans
    normalisation, `len(dict)` compterait ses CLÉS. Une liste reste elle-même, None → 0."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        return len(_units_of(self.selector, ctx))


class GetPersistentData(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$GetPersistentData(abilityOrEffect, unit, dataKey)` ->
    `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate` -- MIRROR du decompile :

        entity = this.<+0x28 unitSelector>.SelectSingle(entities)     # null -> return 0
        key    = this.<+0x30 intFormula>?.Calculate(entities).ToString()
                 ?? this.<+0x38 stringFormula>.Calculate(entities)
        id     = AbilityOrEffect.GetPersistentDataId(this.<+0x10..0x20>)
        comp   = entity.GetComponent<PersistentDataComponent>()
        comp.TryGetPersistData<T>(id, key, out result)                # cle absente -> `default`
        return result

    Trois traits LUS, qui ne se devinent pas :
      * `SelectSingle` (slot 8), pas `Select` : la formule porte sur UNE entite ;
      * la `dataKey` a DEUX sources -- une formule ENTIERE convertie par `Int32.ToString()`, sinon
        une formule de CHAINE. Le port accepte les deux (`.evaluate` ou scalaire) ;
      * `TryGetPersistData` ne signale pas l'absence : son `out` reste au `default` du type, donc
        **cle absente == 0**. C'est ce qui rend `AmountIsZero(GetPersistentData(...))` VRAI la
        premiere fois -- et le port doit rendre 0, jamais None.

    Cle composite portee `(abilityOrEffect, dataKey)`, la MEME que la variante LISTE (c'est le meme
    `Dictionary` @+0x10 cote natif). `ctx.persistent_data` absent -> 0 (meme degradation).

    CONSOMMATEUR PORTE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineAbility$$
    CreateTrigger`, 2e disjonction (`AmountIsZero(GetPersistentData(...))` = « aucune mine posee ce
    tour »)."""
    def __init__(self, ability_or_effect: int, unit: TargetsSelector, data_key):
        self.ability_or_effect = int(ability_or_effect)
        self.unit, self.data_key = unit, data_key

    def calculate(self, ctx):
        fn = getattr(ctx, "persistent_data", None)
        if fn is None:
            return 0
        u = resolve_unit(self.unit, ctx)
        if not u:
            return 0                     # `SelectSingle == null` -> 0
        key = self.data_key.evaluate(ctx) if hasattr(self.data_key, "evaluate") else self.data_key
        v = fn(u, (self.ability_or_effect, key))
        return 0 if v is None else int(v)     # `out` par defaut = 0 sur cle absente


class GetAllPersistentDataCombined(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$GetAllPersistentDataCombined(abilityOrEffect, unit,
    excludedKeys)` -> `IdunBattle.Entities.Triggers.GetAllPersistentDataCombined$$Calculate`, qui
    delegue a `...$$SumAbilityData` -- MIRROR (#965) :

        entity = this.<+0x28 unitSelector>.SelectSingle(entities)   # null -> return 0
        id     = AbilityOrEffect.GetPersistentDataId(this.<+0x10..0x20>)
        return SumAbilityData(entity.GetComponent<...>(), id)       # cf. le mirror du composant

    La SOMMATION elle-meme (somme des valeurs ENTIERES, saut des types non-int, exclusion par
    `String.op_Equality`) vit dans `runner/components.py::PersistentDataComponent.sum_ability_data`,
    ou elle est documentee ligne a ligne -- c'est la frontiere #149 : la formule est le NOEUD, le
    balayage du sac est l'acces au composant.

    ⚠ `excludedKeys` est un `T[]` construit PAR L'APPELANT : `...GetCurrentExtraDmg` alloue un
    tableau a UN element et y ecrit la cle statique posee par `...RefusalToBeOutdoneAbility$$.cctor`.
    Sans cette exclusion, le COMPTEUR d'amis Chaos serait somme dans l'Outrage -- l'argument est
    donc load-bearing, pas decoratif.

    `ctx.persistent_data_all` absent -> 0, meme degradation que `GetPersistentData` (le natif rend
    0 quand son `TryGetValue(abilityId)` echoue, et cela ne se distingue pas d'un sac vide).

    CONSOMMATEUR PORTE : `...RefusalToBeOutdoneAbility$$GetCurrentExtraDmg` (l'*Outrage* de
    Laviscus = la somme des plus gros degats de chaque ami sur le tour)."""
    def __init__(self, ability_or_effect: int, unit: TargetsSelector, excluded_keys=None):
        self.ability_or_effect = int(ability_or_effect)
        self.unit = unit
        self.excluded_keys = tuple(excluded_keys or ())

    def calculate(self, ctx):
        fn = getattr(ctx, "persistent_data_all", None)
        if fn is None:
            return 0
        u = resolve_unit(self.unit, ctx)
        if not u:
            return 0                     # `SelectSingle == null` -> 0
        return int(fn(u, self.ability_or_effect, self.excluded_keys) or 0)


class AngleBetweenLines(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$AngleBetweenLines(a1, b1, a2, b2)` ->
    `IdunBattle.Entities.Formulas.AngleBetweenLinesFormula$$Calculate` (MIRROR 1:1) :

        v1 = BattleQuery.GetVector(a1, b1)          # slot iface 0x70
        v2 = BattleQuery.GetVector(a2, b2)
        return BattleQuery.GetAngleBetweenVectors(v1, v2)    # slot 0x72 = EdgeExtensions.GetAngleTo

    - `IdunBattle.Core.Services.BattleQuery$$GetVector(a, b)` : `MainTile(a)` == `MainTile(b)` -> vecteur
      NUL ; sinon `AxialCoordinate.ConnectingEdge(coordA, coordB)` -> `Position(edge)` si le delta cube est
      une direction UNITAIRE, vecteur NUL sinon (`Position.Zero`, valeur d'arete 0).
    - `IdunBattle.Utils.Hex.EdgeExtensions$$GetAngleTo(e1, e2)` (MIRROR EXACT) :
      `d = |e1 - e2| ; a = d*60 ; if a > 120 : a = (6-d)*60` -> 0/60/120/180/120/60 = l'ecart ANGULAIRE
      MINIMAL entre deux directions hex, en degres.

    Robustesse a la convention de cube : le port et le natif peuvent numeroter les aretes differemment
    (rotation/reflexion de la grille) — `|e1 - e2|` mod 6 est INVARIANT par rotation ET par reflexion,
    donc l'angle rendu est le meme. Delta non unitaire / tuile identique -> arete 0 (mirror du
    `Position.Zero` natif).

    Les deux slots vivent en mirror UNIQUE, en domaine POSITION, dans `engine.battle_query`
    (`get_vector` / `get_angle_between_vectors`) : cette formule DSL (face COMBAT) et la feuille
    `DarkTalonStrikePlaybook` (face DECISION, #126) en sont deux ADAPTATEURS de substrat.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine`
    (`AngleBetweenLines(caster@0x160, <voisine du caster la plus proche de la cible>, target@0x178,
    subject@0x180)` = ecart entre la direction d'APPROCHE du Dark Talon et la direction du rayon)."""
    def __init__(self, a1: TargetsSelector, b1: TargetsSelector,
                 a2: TargetsSelector, b2: TargetsSelector):
        self.a1, self.b1, self.a2, self.b2 = a1, b1, a2, b2

    def calculate(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return 0

        def _vec(na, nb):
            pa = _tile_positions(na, ctx, board)
            pb = _tile_positions(nb, ctx, board)
            if not pa or not pb:
                return 0
            return _bq.get_vector(pa[0], pb[0])            # slot 0x71 = BattleQuery.GetVector
        # slot 0x71 = EdgeExtensions.GetAngleTo -- mirror UNIQUE partage avec la face DECISION
        return _bq.get_angle_between_vectors(_vec(self.a1, self.b1), _vec(self.a2, self.b2))


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
    """`IdunBattleLogic.Entities.DSLFormulas$$TotalTimesAttacked(unit)` ->
    `IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate` : le decompile resout le
    SELECTEUR d'unite, prend son `ActorStatisticsComponent` et rend `*(uint *)(comp + 0x34)` — le
    nombre d'attaques REÇUES depuis le DEBUT DE LA BATAILLE (`RegisterAttackReceived` l'incremente,
    et AUCUN `Reset*` du composant ne l'ecrit ; le champ per-tour est `@+0x38`, cf.
    `runner/components.py`).

    `unit` = le selecteur natif. Le seul call-site porte est
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetNumExtraHits`, qui passe
    `DSLSelectors+0x30` = `Owner()`. Substrat runner : la cle `totalTimesAttacked` du dict d'unite
    (`runner/abilities/behaviours/context.py::_unit_dict`), meme patron que
    `LastHitDamageTakenLastTurn`.

    `unit=None` = la forme DEGRADEE de la face PREDICTION, conservee telle quelle : le contexte
    figé n'a pas de dict d'unite porteur du compteur, il porte `ctx.times_attacked` (defaut 0 =
    pre-snowball). Les deux formes lisent la MEME grandeur, par deux substrats."""
    def __init__(self, unit: TargetsSelector = None):
        self.unit = unit

    def calculate(self, ctx):
        if self.unit is None:
            return ctx.times_attacked or 0
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return ctx.times_attacked or 0
        return int(u.get("totalTimesAttacked", 0) or 0)


class LastHitDamageTakenLastTurn(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$LastHitDamageTakenLastTurn(unit)` ->
    `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate` : resout le selecteur,
    prend l'`ActorStatisticsComponent` de l'unite et rend **`*(int *)(comp + 0x70)`** — le degat du
    DERNIER COUP encaisse pendant le tour PRECEDENT du proprietaire.

    Substrat (cf. `runner/components.py`, champs `last_hit_damage_taken_*`) : `@+0x6c` est ecrit PAR
    COUP par `IdunBattle.Operations.ApplyDamageOperation$$Execute`, puis roule dans `@+0x70` par
    `IdunBattle.Operations.StartTurnOperation$$ResetUnit` au debut du tour du proprietaire. La cle
    `lastHitDamageTakenLastTurn` du dict d'unite DSL est produite par
    `runner/abilities/behaviours/context.py::_unit_dict`. Unite hors-`State` (dict fige de la face
    PREDICTION) -> 0, meme regime que `TotalTimesAttacked`/`TotalAttacksMade`.

    Consommateur porte : la regen `TimeFlux` de `thousTerminator`
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("lastHitDamageTakenLastTurn", 0) or 0)


class TimesRepaired(AAmountFormula):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class RoundsStarted(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$RoundsStarted(selecteur)` ->
    `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` : **SOMME** de `UnitComponent.
    turnsStarted@+0x58` sur les unites du selecteur (le decompile ITERE le selecteur et accumule
    `component+0x58` -- ce n'est pas un `First`, contraste
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` qui resout UNE entite et lit
    `GetStat(unit, 0xc)`). Meme grandeur que le noeud `UnitTurnsStarted` (stat 12 TURNS_STARTED,
    maintenue offline par `StartTurnOperation`), d'ou la meme source de lecture ici.

    Consommateurs portes : `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits`
    (via le collapse `aeldari._rounds_started`, qui AJOUTE un plancher `max(1, .)` propre a ce
    call-site) et `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$AffectedTileAmount`
    (`Sum(Get(1), RoundsStarted(caster@0x160), TotalRepairActionsAmount(...))`). Ce noeud-ci N'A PAS de
    plancher : le natif somme, point."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        gs = ctx.get_stat or _default_get_stat
        return sum(int(gs(u, int(StatType.TURNS_STARTED), 0, None) or 0)
                   for u in _units_of(self.selector, ctx))


class TotalRepairActionsAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$TotalRepairActionsAmount(selecteur)` ->
    `IdunBattle.Entities.Formulas.TotalRepairActionsAmountFormula$$Calculate` : SOMME d'un compteur
    runtime per-unite (`component+0xe8`) sur les unites du selecteur -- « combien de fois cette unite
    a-t-elle REPARE/soigne ». DISTINCT de `TimesRepaired` (`TimesRepairedFormula$$Calculate`, qui lit
    `+0xd0` sur UNE entite = « combien de fois cette unite a ETE reparee »).

    RESIDU DOCUMENTE : ce compteur n'est capte par AUCUN canal offline (ni `combatSnapshot`, ni
    `decisionView`) et le runner porte ne l'incremente nulle part (les feuilles `Repair`/`RepairOrHeal`
    de `behaviours/stats.py` ne tiennent pas de compteur). Le noeud lit donc `u["_repair_actions"]`
    (pose par un futur canal) et rend **0** a defaut -- valeur EXACTE tant qu'aucun allie Mechanic n'a
    soigne, ce qui est le regime de tout runner frais. Consommateur : le 3e terme de
    `RadBombardmentAbility$$AffectedTileAmount` (i2 : « +1 hex chaque fois qu'un Mechanic ami restaure
    la Sante d'une unite »)."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        return sum(int((u or {}).get("_repair_actions", 0) or 0)
                   for u in _units_of(self.selector, ctx))


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


class CurrentStatModifierAmount(AAmountFormula):
    """`IdunBattle.Entities.Formulas.CurrentStatModifierAmountFormula` (allouee par
    `IdunBattleLogic.Entities.DSLFactory$$AddOrUpdateStaticStatModifierEffect` : ctor `(dslFactory+0x38, unit,
    effectType, statType)`) : montant COURANT de la modification de `statType` que l'effet `effectType`
    applique deja a `unit` -- 0 si l'effet n'est pas porte. Sert UNIQUEMENT au gate d'idempotence
    `NOT AmountIsEqual(nouveauMontant, courant)` de la factory composite.

    Port : lit `ctx.stat_modifier_amount(unit, effectType, statType)` (fourni par la couche runner, qui
    connait la `ValueModification` per-source keyee par l'instance d'effet) ; accesseur absent -> 0 (le
    gate devient « toujours re-poser », qui est le comportement du 1er cast et reste correct tant que le
    montant change ; documente)."""
    def __init__(self, unit: TargetsSelector, effect_type: int, stat_type: int):
        self.unit, self.effect_type, self.stat_type = unit, int(effect_type), int(stat_type)

    def calculate(self, ctx):
        fn = getattr(ctx, "stat_modifier_amount", None)
        if fn is None:
            return 0
        u = resolve_unit(self.unit, ctx)
        return int(fn(u, self.effect_type, self.stat_type) or 0) if u is not None else 0


class TotalActiveAbilityUsed(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$TotalActiveAbilityUsed(unit, abilityType)` : le natif alloue un
    noeud (ctor gshared MISLABELE `HasUsedActiveAbilityThisTurnTrigger..ctor` par ghidra -- structure lue :
    `(unit, DirectAbilitySelector(AbilityOrEffect(abilityType)))`) = COMPTEUR runtime du nombre de fois que
    `unit` a utilise l'ability ACTIVE `abilityType` dans la bataille.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour`
    (`Multiply(Sum(TotalActiveAbilityUsed(Owner, 0x47c=1148), Get(1)), Direct(extraCritChance))` = le
    modificateur de CriticalChance cumule d'un cran par usage).

    RESIDU : le compteur n'est PAS capte offline -> `ctx.total_active_ability_used(unit, abilityType)`,
    defaut None -> **0** (meme regime documente que `TotalTimesAttacked`/`TimesRepaired`). Le 1er cast est
    donc exact (`0+1`) ; les suivants sous-estiment tant que le canal n'est pas branche."""
    def __init__(self, unit: TargetsSelector, ability_type):
        self.unit, self.ability_type = unit, int(ability_type)

    def calculate(self, ctx):
        fn = getattr(ctx, "total_active_ability_used", None)
        if fn is None:
            return 0
        u = resolve_unit(self.unit, ctx)
        return int(fn(u, self.ability_type) or 0) if u is not None else 0


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
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return 0
        if "_turns_started" in u:                    # enfant SPAWNE (SpawnUnit pose 0) — priorite au marqueur
            return int(u.get("_turns_started", 0) or 0)
        gs = getattr(ctx, "get_stat", None)
        if gs is None:
            return 0
        return int(gs(u, int(StatType.TURNS_STARTED), 0) or 0)


class PlayerTurnsStarted(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$PlayerTurnsStarted(unit)` ->
    `IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula$$Calculate`, relu VERBATIM
    (`rnca9r7q6c`) :

        unit  = <selecteur>.Select(entities)          # null -> 0
        owner = EntityExtensions.GetOriginalOwnerEntityId(unit)
        turn  = StateExtensions.GetMatchTurn(state)
        return TurnComponent.GetAmountOfTurnsStartedByPlayer(turn, owner)

    C'est donc le compteur PAR JOUEUR `TurnComponent+0x38` (= `State.turn_counts`), incremente par
    `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` -- son ecrivain UNIQUE, donc
    par ChangeTurn et non par StartTurn (#287-r11-r1-r1-r1-r1) -- **PAS** le compteur PER-UNITE
    `UnitComponent+0x58` (stat 0xc) que lit `UnitTurnsStarted` juste au-dessus. Les deux existent et
    les confondre change la phase d'un cycle : `FleshMetalGunsAbility` indexe son cycle a 3 temps sur
    le compteur PER-UNITE, `SereneUnifierAbility` sur celui-ci.

    ⚠ APPROXIMATION NOMMEE -- `GetOriginalOwnerEntityId` lit `OriginalOwnerComponent+0x10`, le
    proprietaire d'ORIGINE (avant tout Mind Control / changement de camp) ; le port n'a pas ce
    composant et lit `OwnerComponent.player`, le proprietaire COURANT. Les deux coincident tant
    qu'aucune unite n'a change de camp. Le canal est fourni par `entities_from_state`
    (`ctx.player_turns_started`) ; absent -> 0, comme le natif sur `unit == null`."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        if u is None:                                # `if (unit == null) return 0`
            return 0
        fn = getattr(ctx, "player_turns_started", None)
        if fn is None:                               # canal absent (arbre purement numerique)
            return 0
        return int(fn(u) or 0)


class TurnsUntilUnitOwnerTurn(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilUnitOwnerTurn(unit)` ->
    `IdunBattle.Entities.Formulas.TurnsUntilUnitOwnerTurnFormula$$Calculate` -- MIRROR du decompile :

        result = 0
        foreach u in selector.Select(entities):
            result = System.Math.Max(result, GetTurnsUntilUnitOwnerTurn(u))
        return result

    L'accumulateur est initialise a ZERO **avant** la boucle et n'est jamais ecrit hors du `Max` :
    un set VIDE rend donc 0, pas une duree inventee. C'est le MAX, pas le premier element -- le
    natif l'applique meme sur un selecteur mono-unite (ou il degenere en la valeur unique).

    `IdunBattle.Entities.Formulas.TurnsUntilUnitOwnerTurnFormula$$GetTurnsUntilUnitOwnerTurn` (LU) :

        cur = StateExtensions.GetCurrentPlayer(state)
        if (cur == null) return 0
        if (GetOriginalPlayerId(cur) == GetOriginalPlayerId(unit)) return 0   # c'est deja son tour
        ... compte les tours de joueur (hors Environment, hors elimine) avant celui du proprietaire

    MEME COLLAPSE ASSUME que le helper imperatif jumeau `runner/abilities/base.py
    :turns_until_unit_owner_turn`, et pour la MEME raison : le port ne detient pas la LISTE
    `TurnOrder`. Sur le seul vecteur constructible -- un duel a deux joueurs non-Environment -- la
    boucle native ne peut compter que le joueur COURANT avant de tomber sur le proprietaire, donc
    **1** ; et **0** des que le proprietaire EST le joueur courant. Avec plus de deux joueurs le
    rang exact n'est pas derivable offline et ce noeud rend 1 (borne INFERIEURE, jamais une duree
    inventee plus longue).

    Canaux : `ctx.current_player_id` (deja porte, lu par `IsTurnOf`) et le champ `player` du dict
    d'unite (`OwnerComponent.player`, cf. `runner/abilities/behaviours/context.py:_unit_dict`) --
    aucun accesseur neuf. `current_player_id is None` -> 0, mirror de la branche `cur == null`."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        cur = getattr(ctx, "current_player_id", None)
        if cur is None:                              # `if (GetCurrentPlayer(state) == null) return 0`
            return 0
        result = 0                                   # accumulateur natif, ZERO avant la boucle
        for u in _units_of(self.selector, ctx):
            owner = u.get("player") if isinstance(u, dict) else None
            turns = 0 if (owner is not None and int(owner) == int(cur)) else 1
            result = max(result, turns)              # `System.Math.Max(result, ...)`
        return result


class TurnsFromRounds(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFactory$$TurnsFromRounds(rounds)` → `IdunBattle.Entities.Formulas.TurnsFromRoundsFormula$$Calculate`
    = `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (interface slot 0x1c) = `count(joueurs du turnOrder,
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


class UnitNormalRepairType(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitNormalRepairType(entitySelector)` ->
    `IdunBattleLogic.Entities.AbilityTypeSelector.UnitNormalRepairAbilitySelector$$Select` : le
    JUMEAU REPAIR d'`UnitNormalAttackType` ci-dessus. Les deux fabriques sont structurellement
    identiques au decompile (meme allocation, meme `.ctor(unit, 0)`), et les deux `Select` ne
    different que par l'accesseur d'`ActiveAbilityComponent` qu'ils appellent :

        UnitExtensions$$GetNormalAttackType(unit)  ->  <ActiveAbilityComponent>+0x28
        UnitExtensions$$GetRepairType(unit)        ->  <ActiveAbilityComponent>+0x2c

    (les deux corps sont identiques par ailleurs, y compris la garde `GetEntityType(unit) == 1
    Unit` et le `return 0` hors-unite.)

    ⚠ **ASYMETRIE LUE, ET ELLE N'EST PAS COSMETIQUE** : `UnitNormalRepairAbilitySelector$$Select`
    GARDE son `SelectSingle` (`if (unit != null) repairType = Nullable(GetRepairType(unit))`) puis
    rend un `Nullable<AbilityOrEffect>` **VIDE** quand le selecteur d'unite ne resout rien, la ou
    `UnitNormalAttackAbilitySelector$$Select` appelle `GetNormalAttackType` SANS garde et rend
    toujours une valeur. C'est ce vide qui fait sauter l'unite dans
    `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select` (son `if
    (ability.HasValue)`), donc le porter comme un `0` filtrerait sur `ActiveAbilityType 0` au lieu
    de ne pas filtrer du tout. `None` cote port = le `Nullable` VIDE.

    SUBSTRAT : meme resolution que `UnitNormalAttackType` -- le type CONCRET n'est pas un champ de
    l'etat runner, on le derive du KIT gameconfig du porteur. Une ability qui REDEFINIT la
    reparation normale expose un membre `<ability>_Repair` d'`ActiveAbilityType` ; a defaut, le
    generique `28 Repair` est rendu des que l'unite porte une ability de reparation dans son kit.
    Aucune -> `None` (l'unite n'a rien a reparer avec, elle sort du filtre)."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        u = resolve_unit(self.selector, ctx)
        # `if (unit != null)` du natif -- le `Nullable` VIDE quand `SelectSingle` ne resout rien.
        if u is None:
            return None
        vis = u.get("visualId")
        if vis is None:
            return None
        import gameconfig as GC
        names = []
        for _slot, v in (GC.unit_abilities(vis) or {}).items():
            if isinstance(v, str):
                names.append(v)
            elif isinstance(v, dict):
                names.append(v.get("name") or v.get("id"))
            elif isinstance(v, list):
                names += [(x.get("name") if isinstance(x, dict) else x) for x in v]
        generic = None
        for nm in names:
            if not nm:
                continue
            member = getattr(ActiveAbilityType, f"{nm}_Repair", None)
            if member is not None:
                return int(member)
            # Le REPAIR generique : l'unite porte une ability de reparation nommee, sans redefinir
            # le type. `Repair` (28) et `Repair_GalvanicField` (1119) sont les deux ids que le port
            # connait de ce cote (`ABILITY_CLASSES`), et un E-Cog porte le premier.
            member = getattr(ActiveAbilityType, str(nm), None)
            if member is not None and str(nm).startswith("Repair"):
                generic = int(member)
        return generic


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


# ---- Le couple de formules du predicat d'AURA (`IsInUnit<X>Aura`), cf. `triggers.IsInUnitAura` ----

# `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` rend `int.MaxValue` quand une des deux
# enumerations est VIDE (l'accumulateur `uVar15` est initialise a 0x7fffffff et aucune iteration ne le
# baisse). Ce n'est PAS un detail : c'est ce qui rend le predicat `AmountIsEqualOrGreater(range,
# dist)` FAUX des qu'un operande ne resout rien -- degradation fidele, jamais un « dans l'aura » par
# defaut.
MIN_DISTANCE_EMPTY = 0x7FFFFFFF


class MinDistance(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$MinDistance(a, b)` ->
    `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` -- MIRROR du decompile :

        min = int.MaxValue                                  # 0x7fffffff
        foreach (ta in <a @+0x10>.SelectTiles(entities))     # slot 10 = TargetsSelector$$SelectTiles
            foreach (tb in <b @+0x18>.SelectTiles(entities))
                min = Math.Min(min, PositionComponent.Distance(tb.Position, ta.Position))
        return min

    EMPREINTES (#433-r3-r1). L'ancienne docstring de ce noeud concluait « le natif lit UNE position
    par ENTITE, donc la MainTile -- PAS l'empreinte » : c'etait FAUX, et c'est la faute que le
    slot 10 rend facile. `GetComponent<PositionComponent>` est bien applique a l'element ENUMERE,
    mais cet element est une TUILE, pas l'entite selectionnee : le slot 10 est
    `IdunBattle.DSL.TargetsSelector$$SelectTiles`, qui materialise `EntityExtensions$$IterateTiles`
    de chaque entite (= l'empreinte COMPLETE) dans une liste plate. Le port lit donc `_feet`.
    Pour une unite mono-tuile `feet == [main tile]` -> resultat inchange.

    Une entite sans position rend une empreinte VIDE et ne contribue a aucune paire (le natif
    deref son `PositionComponent`) ; si aucune paire n'est mesurable on rend `MIN_DISTANCE_EMPTY`,
    exactement le `int.MaxValue` du natif quand la boucle ne tourne pas. ⚠ Ce sentinel est celui
    de CETTE formule ; `IdunBattle.Core.Services.BattleQuery$$GetMinDistance` (le slot 0x6f que lit
    `IsInRangeAbilityTrigger`) rend **-1** dans le meme cas -- deux fonctions, deux sentinels.

    ⚠ **AUCUN offset sur le chemin de distance** -- le chemin est lu de bout en bout :
    `IdunBattle.Entities.Components.PositionComponent$$Distance` =
    `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(this.ToCube(), other.ToCube())`, lui-meme
    `Max(Max(|dx|, |dy|), |dz|)` -- la distance hex NUE, egale a `hexgeo.distance`. C'est ce qui
    REFUTE le modele « `MinDistance` natif = `hexdist - 1` » avance pour expliquer l'ecart d'une
    unite du predicat d'aura par unite : l'ecart etait dans le COMPARATEUR, pas ici (#293, cf.
    `entities/triggers.py::IsInUnitAura`). Garde re-derivable :
    `python scripts/python/probe_293_aura_predicate_comparator.py` (etape 3)."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def calculate(self, ctx):
        # `SelectTiles` = liste PLATE des tuiles de toutes les entites selectionnees.
        ta = [f for u in _units_of(self.a, ctx) if isinstance(u, dict) for f in _feet(u)]
        tb = [f for u in _units_of(self.b, ctx) if isinstance(u, dict) for f in _feet(u)]
        return get_distance(ta, tb)                           # meme seed `int.MaxValue`


class AuraEffectRange(AAmountFormula):
    """`IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate` -- MIRROR du decompile. Construit
    par `IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType,
    isNextTurn)`, qui fige `effectType = 0x42f = 1071 ContagionsOfNurgle_ArmorReduction1` :

        unit = <selecteur @+0x10>.<slot 7>(entities)          ; null -> 0
        aura = <effets @+0x28>.GetEffect(effectType@+0x18) as IAuraEffect
        if (aura == null) return 0                            # cast d'interface ECHOUE
        if (!UnitExtensions.HasTrait(unit, aura.GetTrait())) return 0
        entities.<+0x18 = slot Owner> = unit                  # la formule de portee lira CE porteur
        return (isNextTurn@+0x20 ? aura.GetNextTurnRange() : aura.GetCurrentRange()).Calculate(entities)

    La PORTEE est donc celle d'une DEFINITION d'effet (`EffectsDatabase`), evaluee SUR le porteur --
    aucune instance d'effet posee n'est requise, seul le TRAIT de l'unite compte. Le port n'a pas besoin
    de muter le contexte comme le natif (`entities+0x18 = unit`) : la seule lecture que fait
    `GetCurrentRange` est `StatAmount(Owner, 0xc = TurnsStarted)`, qu'on evalue directement sur l'unite
    resolue -- meme valeur, sans effet de bord sur un contexte partage.

    `unitSelectionType` (`this+0x1c`) est stocke par le ctor mais n'est LU par AUCUN chemin de
    `Calculate` : non porte (les deux call-sites Contagion passent 0, `Lakrimae_SummonPoxwalker` passe 1
    et retombe sur la meme portee). `ctx.has_trait`/`ctx.get_stat` absents -> 0 (degradation fidele :
    « pas d'aura », jamais une portee inventee)."""
    def __init__(self, unit: TargetsSelector, effect_type: int, is_next_turn: bool = False):
        self.unit, self.effect_type, self.is_next_turn = unit, int(effect_type), bool(is_next_turn)

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return 0                                       # `unit == null` -> 0
        trait = aura_trait(self.effect_type)
        if trait is None:
            return 0                                       # `as IAuraEffect` == null -> 0
        ht = getattr(ctx, "has_trait", None)
        if ht is None or not ht(u, trait):
            return 0                                       # `!HasTrait(unit, GetTrait())` -> 0
        gs = ctx.get_stat or _default_get_stat
        turns = int(gs(u, int(StatType.TURNS_STARTED), 0, None) or 0)
        r = (aura_next_turn_range(self.effect_type, turns) if self.is_next_turn
             else aura_current_range(self.effect_type, turns))
        return int(r or 0)


class DamagePredictionFormula(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$DamagePredictionFormula(attacker, attackerPosition,
    defender, ability, damage, hits, damageProfileType, prioritizeKills)` ->
    `IdunBattle.Entities.Formulas.DamagePredictionFormula$$Calculate` -- MIRROR 1:1 du decompile.

    LE CORPS NATIF, transcrit dans son ORDRE (`$$Calculate`) :

        attackerEntity = (+0x20).SelectUnit(entities)             # slot 7
        defenderEntity = (+0x30).SelectUnit(entities)             # slot 7
        damageValue    = (+0x40).Calculate(entities, out MinMaxDamage)   # <-- slot 1
        if (defenderEntity == null || attackerEntity == null
            || UnitExtensions.GetUnit(defenderEntity, state) == null)  return 0
        position = AbilityEntities.get_CasterPosition(entities)
        if ((+0x28) != null) position = (+0x28).SelectTile(entities)     # slot 10
        hits     = (+0x48) != null ? (+0x48).Calculate(entities) : <defaut>
        ability  = AbilityOrEffect(UnitExtensions.GetNormalAttackType(attackerEntity))
        if ((+0x38) != null) ability = (+0x38).Select(entities)          # slot 0
        pred = query.<slot 0x28>(attackerEntity, defenderUnit, position, ability,
                                 damageValue, Nullable(+0x50 = damageProfileType), hits)
        minmax = (+0x54 prioritizeKills) ? <bornes optimistes> : pred.AccurateHealthDamage@+0x40
        avg = MinMaxDamage$$Avg(minmax)
        if (query.<slot 0x92 = AreFriends>(attackerEntity, defenderUnit, 0))  return -avg
        if (!prioritizeKills)                        return avg
        if (pred.WillBeKill)                         return avg * 3
        if (pred.MightBeKill)                        return avg * 2
        return avg

    Les DEUX slots d'interface sont LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`,
    jamais devines : `IBattleQuery 40 GetMultiHitAttackPrediction 7` et `IBattleQuery 146
    AreFriends 3`. Le premier est le MEME foyer que `SortUnitsByDamageUtilitySelector`
    (`runner/operations/attack_prediction.multi_hit_attack_prediction`), le second est le test
    d'equipe -- une prediction sur un ALLIE est comptee NEGATIVEMENT.

    ⚠ **LE TIRAGE EST INCONDITIONNEL, ET IL PRECEDE LES TROIS NULL-GUARDS.** `(+0x40).Calculate`
    est le slot **1** (`IAmountFormula.Calculate`), pas le slot 4 (`CalculateAverage`) : quand la
    formule de degat est un `RandomAmount` -- ce qui est le cas de `BaseTriggeredAbility$$
    MinMaxDamage` -- CHAQUE evaluation CONSOMME le PRNG (`IdunBattle.Entities.Formulas.
    RandomAmount$$Calculate` -> `IntBasedMersenneTwister$$NextInternal(min, max + 1)`). Et le natif
    tire AVANT de tester que le defenseur existe : une formule evaluee sur un candidat dont le
    sous-selecteur ne rend RIEN consomme quand meme son tirage. Rendre 0 sans tirer desalignerait
    tout le flux aval (loi #215). C'est pourquoi ce mirror appelle `damage.evaluate(ctx)` en TETE.

    `prioritize_kills` = le 9e argument de la factory. Les DEUX call-sites portes le passent a
    **faux** (`SpiritLeechAbility$$GetHealAmountForPrediction`, et le `GetDamagePredictionFormula`
    de `FuryOfTheAncientsAbility` -- ou le pseudo-C l'ecrit `(void *)((ulonglong)<pile> << 8)`,
    c.-a-d. octet de poids faible NUL, l'idiome inverse du `CONCAT71(<pile>, 1)` des arguments
    booleens VRAIS). La branche `x3`/`x2` est donc portee mais SANS appelant : elle est ecrite pour
    que le lecteur voie la formule complete, comme la branche `IsAtGroupUnitHealLimit` d'`attack_query`.

    `ctx.attack_prediction` absent (contexte hors runner : prediction, test de noeud) -> 0 APRES le
    tirage. DEGRADATION nommee : sans `State` la prediction native n'est pas evaluable, et rendre
    une valeur inventee ferait un tri FAUX -- un tri sur des cles toutes nulles rend l'ordre SOURCE,
    ce que la stabilite de l'`OrderBy` natif produit aussi a egalite parfaite."""
    __slots__ = ("attacker", "attacker_position", "defender", "ability", "damage", "hits",
                 "damage_profile", "prioritize_kills", "is_melee")

    def __init__(self, attacker: TargetsSelector, attacker_position, defender: TargetsSelector,
                 ability, damage, hits=None, damage_profile: str | None = None,
                 prioritize_kills: bool = False, is_melee: bool = False):
        self.attacker, self.attacker_position = attacker, attacker_position
        self.defender, self.ability = defender, ability
        self.damage, self.hits = damage, hits
        self.damage_profile = damage_profile
        self.prioritize_kills = bool(prioritize_kills)
        # Nature du coup predit -- l'`attackRangeType` de la config d'ability, resolu par l'appelant.
        # Le natif ne la passe pas : elle est deduite de l'`abilityOrEffect` (`+0x38`) par la chaine
        # de prediction elle-meme (`BattleQuery$$GetAttackRangeType`). Cote port, `multi_hit_attack_
        # prediction` la prend en argument -- meme donnee, resolue un etage plus haut.
        self.is_melee = bool(is_melee)

    def calculate(self, ctx):
        att = resolve_unit(self.attacker, ctx)
        dfn = resolve_unit(self.defender, ctx)
        # ORDRE NATIF : le tirage est consomme AVANT les null-guards (cf. la docstring).
        amount = int(self.damage.evaluate(ctx) if hasattr(self.damage, "evaluate")
                     else (self.damage or 0))
        if att is None or dfn is None:
            return 0
        n = 1 if self.hits is None else int(
            self.hits.evaluate(ctx) if hasattr(self.hits, "evaluate") else self.hits)
        fn = getattr(ctx, "attack_prediction", None)
        if fn is None:
            return 0                                   # degradation nommee (cf. docstring)
        pred = fn(att.get("id"), dfn.get("id"), amount, max(1, n), self.damage_profile,
                  self.is_melee)
        if pred is None:
            return 0
        avg = int(min_max_avg(int(pred.get("healthDmgMin") or 0),
                              int(pred.get("healthDmgMax") or 0)))
        # `IBattleQuery` slot 146 `AreFriends(attacker, defender, 0)` -- meme predicat d'equipe que
        # les selecteurs `Friends`/`Enemies` (`u.get("team")`).
        if att.get("team") is not None and att.get("team") == dfn.get("team"):
            return -avg
        if not self.prioritize_kills:
            return avg
        if pred.get("killSure"):                       # `DamagePredictionResult$$get_WillBeKill`
            return avg * 3
        if pred.get("kill"):                           # `...$$get_MightBeKill`
            return avg * 2
        return avg
