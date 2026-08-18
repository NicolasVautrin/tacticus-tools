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
                        _default_get_stat, resolve_unit, _units_of, _pos, _feet,
                        invoke_slot, SLOT_CALCULATE, SLOT_CALCULATE_MIN, SLOT_CALCULATE_MAX)
from ..services.min_max_damage import min_max_avg
from ..services.movement_query import get_distance
from .active_ability_type import ActiveAbilityType
from .effects.aura import aura_trait, aura_current_range, aura_next_turn_range
from .effects.magnitude import ability_var
from .selectors._shared import _entity_pos, _tile_positions
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

    def _par_slot(self, ctx, slot):
        """#920-r3 : `IdunBattle.Entities.Formulas.SumAmount$$CalculateMin` / `$$CalculateMax` ont
        un corps STRICTEMENT identique a `$$Calculate` -- seul le SLOT invoque sur les enfants
        change. UNE seule arithmetique, trois points d'entree."""
        total = invoke_slot(self.a, ctx, slot) + invoke_slot(self.b, ctx, slot)
        for branch in (self.c, self.d, self.e):               # `if (this+0x20/0x28/0x30 != 0)`
            if branch is not None:
                total += invoke_slot(branch, ctx, slot)
        return total

    def calculate(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE)   # `a`/`b` : aucun null-check natif

    def calculate_min(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MAX)


class Min(AAmountFormula):
    """`IdunBattle.Entities.Formulas.MinAmount` -- noeud **SIMPLE**
    (`IdunBattle.DSL.ASimpleAmountFormula`), donc `CalculateMin`/`CalculateMax` repli(ent) sur
    `Calculate` et le mode NE DESCEND PAS aux enfants (#920-r3). C'est EXACTEMENT le defaut d'
    `AAmountFormula` : rien a surcharger ici, et c'est un RESULTAT, pas un oubli."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return min(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Multiply(AAmountFormula):
    """`IdunBattle.Entities.Formulas.MultiplyAmount` -- noeud COMPLEXE : il PROPAGE le slot.
    ⚠ **AUCUN CROISEMENT DE BORNES** (LU) : `CalculateMin` = min x min, `CalculateMax` = max x max,
    naivement. Sur un facteur negatif le natif rend donc `min > max` -- a mirrorer tel quel."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def _par_slot(self, ctx, slot):
        return invoke_slot(self.a, ctx, slot) * invoke_slot(self.b, ctx, slot)

    def calculate(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE)

    def calculate_min(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MAX)


class Difference(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Difference(a,b)` = `Sum(a, Multiply(b, -1))` = a - b.

    ⚠ SON NOEUD REEL N'EST PAS LU (#920-r3 sec.3) : la fabrique n'a **aucun symbole ghidra**, ni
    sur `rnca9r7q6c` ni sur le build charge. La forme ci-dessus vient du mirror, pas du natif --
    donc on NE PROPAGE PAS le mode ici, faute de savoir quel noeud est alloue. Un `SumAmount` le
    propagerait ; un noeud simple non. Residu NOMME plutot que devine."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return self.a.evaluate(ctx) - self.b.evaluate(ctx)


class If(AAmountFormula):
    """`IdunBattle.DSL.IfAmount` : `a` si `cond` (bool) sinon `b`. Evalue paresseusement la branche
    prise -- et PROPAGE le slot A CETTE BRANCHE (#920-r3).

    ⚠ Ce n'est donc PAS `min(then, else)` : c'est le MIN **DE LA BRANCHE PRISE**. La condition,
    elle, passe par un AUTRE dispatcher (retour `char`) : le mode ne la concerne pas."""
    def __init__(self, cond: AAmountFormula, a: AAmountFormula, b: AAmountFormula):
        self.cond, self.a, self.b = cond, a, b

    def _par_slot(self, ctx, slot):
        return invoke_slot(self.a if self.cond.evaluate(ctx) else self.b, ctx, slot)

    def calculate(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE)

    def calculate_min(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MAX)


class ConditionalAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$ConditionalAmount(cond, ifTrue, ifFalse)` (ctor gshared MISLABELE
    « ModuloAbilityTrigger » dans ghidra -- structure lue, jamais le nom) : noeud VALEUR ternaire.
    Factory native DISTINCTE de `IdunBattleLogic.Entities.DSLFormulas$$If` (meme semantique cond?a:b, autre singleton) ;
    on la porte sous SON nom pour que les arbres qui la citent restent des homonymes 1:1.
    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateBehaviour` (`ConditionalAmount(HasEffect(Self,
    1098 RammingSpeed_ExtraExplode), ConfigConst(1059 RammingSpeed, extraDmgPct), Get(0))`).
    Evaluation PARESSEUSE de la branche prise (comme `If`), et PROPAGATION du slot a cette
    branche (#920-r3, meme structure qu'`IfAmount` : seul le traitement du `result` differe cote
    natif -- il est PROPAGE ici et ZEROISE dans `IfAmount`, ce qui n'a pas d'equivalent au port)."""
    def __init__(self, cond, a: AAmountFormula, b: AAmountFormula):
        self.cond, self.a, self.b = cond, a, b

    def _par_slot(self, ctx, slot):
        return invoke_slot(self.a if self.cond.evaluate(ctx) else self.b, ctx, slot)

    def calculate(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE)

    def calculate_min(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MAX)


class Max(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Max(a,b)` : `max(a,b)` (singleton DAT_1832457c8, usage prouvé via
    `NonLethalDamage = Min(Max(HP-1, 0), dmg)`).

    Noeud **SIMPLE** comme `Min` : `CalculateMin`/`CalculateMax` repli(ent) sur `Calculate`, le
    mode ne descend PAS (#920-r3). Defaut d'`AAmountFormula` -- rien a surcharger."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula):
        self.a, self.b = a, b

    def calculate(self, ctx):
        return max(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Divide(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Divide(a,b,mode)` → `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` :
    `Fix64(a) / Fix64(b)` PUIS `RoundFix64Result(_, mode)` — PAS une division entière. `mode` =
    Ceiling(1)/Floor(2)/Round-half-to-even(0). `b==0` → un arbre valide ne divise jamais par 0
    (laisse remonter l'erreur)."""
    def __init__(self, a: AAmountFormula, b: AAmountFormula, mode: int = 0):
        self.a, self.b, self.mode = a, b, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), self.b.evaluate(ctx)), self.mode)


class Half(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Half(a,mode)` = `Divide(a, 2, mode)` — MÊME arrondi Fix64 (pas `a//2`).

    ⚠ ASYMETRIE AVEC `Double`, et elle est LUE, pas supposee (#920-r3 sec.2b) : les deux fabriques
    allouent des classes DIFFERENTES -- `Half` un `DivideAmount` (SIMPLE, le mode NE descend PAS),
    `Double` un `MultiplyAmount` (COMPLEXE, le mode descend). L'identite se lit au POINTEUR DE
    CLASSE alloue, jamais au nom de la fabrique : ghidra mislabelle ces ctors gshared."""
    def __init__(self, a: AAmountFormula, mode: int = 0):
        self.a, self.mode = a, mode

    def calculate(self, ctx):
        return _round_fix64(Fraction(self.a.evaluate(ctx), 2), self.mode)


class Double(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Double(a)` = `Multiply(a, 2)` = `a * 2` (entier exact, sans arrondi).

    La fabrique alloue le MEME singleton de classe que `DSLFormulas$$Multiply` avec `(a, Const(2))`
    -> c'est un `MultiplyAmount`, donc un noeud COMPLEXE : **il PROPAGE le slot** (#920-r3)."""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return self.a.evaluate(ctx) * 2

    def calculate_min(self, ctx):
        return invoke_slot(self.a, ctx, SLOT_CALCULATE_MIN) * 2

    def calculate_max(self, ctx):
        return invoke_slot(self.a, ctx, SLOT_CALCULATE_MAX) * 2


class Negative(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$Negative(a)` = `Multiply(a, -1)` = `-a`.

    ⚠ LE PIEGE LE PLUS COUTEUX DE #920-r3, et il se MIRRORE, il ne se corrige pas. La fabrique
    alloue le MEME singleton que `DSLFormulas$$Multiply`, avec `(a, <factory+0x38>)` -> un
    `MultiplyAmount`, donc patron PROPAGATEUR **sans croisement de bornes**. Consequence :
    `Negative(a).CalculateMin = a.CalculateMin * (-1)`, c'est-a-dire la borne **HAUTE** de `-a`.
    Sur un `a` d'amplitude non nulle le natif rend donc `CalculateMin > CalculateMax` -- ce n'est
    pas un bug, c'est le comportement natif, et le << reparer >> ferait diverger le port.
    (La valeur de `<factory+0x38>` est PRESUMEE `Const(-1)`, non lue -- cf. #920-r3 sec.3.)"""
    def __init__(self, a: AAmountFormula):
        self.a = a

    def calculate(self, ctx):
        return -self.a.evaluate(ctx)

    def calculate_min(self, ctx):
        return -invoke_slot(self.a, ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return -invoke_slot(self.a, ctx, SLOT_CALCULATE_MAX)


class PercentageOf(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$PercentageOf(pct, base, mode)` → `PercentageOf.Calculate IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal`
    (Fix64) : `round_mode(pct% * base)` avec arrondis intermédiaires half-to-even à 2 décimales — PAS
    `pct*base//100`. `pct` = pourcentage entier (50 = 50 %). Les arrondis à 2 décimales sont INERTES
    pour des opérandes entières (nos cas) → `round_mode(Fraction(pct*base, 100))` fidèle.

    #920-r3 : `IdunBattle.Entities.Formulas.PercentageOf$$CalculateMin` et `$$CalculateMax` ont
    des corps STRICTEMENT identiques a `$$Calculate` -- seul le SLOT invoque sur `this+0x10` (le
    POURCENTAGE) et `this+0x18` (le MONTANT) change, `$$CalculateInternal` etant le MEME dans les
    trois. RE-MESURE sur le build charge : `Calculate` -> slot 1 sur les deux enfants,
    `CalculateMin` -> slot 2 sur les deux, `CalculateMax` -> slot 3 sur les deux."""
    def __init__(self, pct: AAmountFormula, base: AAmountFormula, mode: int = 0):
        self.pct, self.base, self.mode = pct, base, mode

    def _par_slot(self, ctx, slot):
        return _round_fix64(Fraction(invoke_slot(self.pct, ctx, slot)
                                     * invoke_slot(self.base, ctx, slot), 100), self.mode)

    def calculate(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE)

    def calculate_min(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MIN)

    def calculate_max(self, ctx):
        return self._par_slot(ctx, SLOT_CALCULATE_MAX)


class RandomAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(minFormula, maxFormula)` ->
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
    """`IdunBattleLogic.Entities.DSLFormulas$$PercentageOfAttackCappedAtMax(unit, statPart, cap, pct, mode)`
    — FACTORY COMPOSITE (elle n'alloue AUCUNE formule dediee), mirror 1:1 du decompile :

        statAmount = StatAmountFormula(unit, statType=0 (ATTACK), statPart, 0, 0)
        pctOf      = DSLFactory.PercentageOf(statAmount, pct, mode)
        return       <noeud 2-champs (cap, pctOf)>

    Le noeud englobant est alloue depuis le singleton de classe `DAT_18324e140`, avec un ctor que ghidra
    affiche `HasUsedActiveAbilityThisTurnTrigger..ctor` (fold gshared 2-champs, NOM FAUX -- cf. l'en-tete
    de `dsl/base.py`). **Sa semantique est PROUVEE par IDENTITE DE SINGLETON, pas deduite du nom de la
    factory** : `IdunBattleLogic.Entities.DSLFormulas$$Min(a, b)` alloue EXACTEMENT le meme
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
    """`IdunBattleLogic.Entities.DSLFormulas$$Count(selector)` → `IdunBattle.Entities.Formulas.CountFormula$$Calculate` : cardinal du
    sélecteur (nb d'éléments). Retour int >= 0.

    ⚠ `_units_of` NORMALISE l'évaluation : côté natif un sélecteur rend TOUJOURS une collection, mais le
    port laisse les accesseurs mono-entité (`Target()`/`Caster()`/`Subject()`) rendre le dict NU — sans
    normalisation, `len(dict)` compterait ses CLÉS. Une liste reste elle-même, None → 0."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        return len(_units_of(self.selector, ctx))


class UnitLevel(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitLevel(unit)` ->
    `IdunBattle.Entities.Formulas.UnitLevelFormula$$Calculate` -- MIRROR du decompile :

        total = 0
        foreach (u in Select(this.unit@+0x10, entities, UnitSelectionType 0))
            total += GetComponent<...>(u).<+0x70>          # le NIVEAU de l'unite
        return total

    C'est une SOMME sur le selecteur (pas un `SelectSingle`), et le `selectionType` est **0**, pas
    `3` -- une unite morte ou non ciblable compte quand meme.

    ⚠ **DEGRADATION NOMMEE : le port n'a PAS de substrat de NIVEAU par unite.** Le dict d'unite que
    `entities_from_state` construit ne porte aucune cle `level` (verifie sur `rnca9r7q6c` : le
    `State` du runner ne seede que rank/stats, jamais le niveau d'unite du profil joueur). La
    formule rend donc **0** pour toute unite sans cette cle -- et le DIT ici plutot que d'inventer
    une derivation.

    Consequence pour l'unique consommateur porte
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BookOfFateAbility$$CreateBehaviour`, qui
    l'utilise en cle de `SortByFormula`) : le tri devient INERTE et l'ordre reste celui du
    `Randomize` amont, parce que `sorted` est STABLE. C'est exactement le comportement natif quand
    tous les niveaux coincident -- ce qui est le regime d'une bataille normalisee au meme rank --
    mais ce n'est PAS une preuve que le natif y soit inerte : si un jour deux summons de niveaux
    differents cohabitent, le port choisira un autre element. Residu explicite `#1008-r1`."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        total = 0
        for u in _units_of(self.unit, ctx):
            if isinstance(u, dict):
                total += int(u.get("level") or 0)
        return total


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
    """`IdunBattleLogic.Entities.DSLFormulas$$AngleBetweenLines(a1, b1, a2, b2)` ->
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
    """`IdunBattleLogic.Entities.DSLFormulas$$LastHitDamageTakenLastTurn(unit)` ->
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


class TimesHealedThisTurn(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$TimesHealedThisTurn(unit)` ->
    `IdunBattle.Entities.Formulas.TimesHealedThisTurnFormula$$Calculate` : resout le selecteur, prend
    l'`ActorStatisticsComponent` de l'entite et rend **`*(uint *)(comp + 0xd4)`** -- combien de fois
    cette unite a ETE SOIGNEE depuis le debut de son tour.

    DISTINCT de ses deux voisins de la meme famille, et le decompile les separe par l'OFFSET :
    `TimesRepairedFormula$$Calculate` lit `+0xd0` (« a ete REPAREE »),
    `TotalRepairActionsAmountFormula$$Calculate` lit `+0xe8` (« a REPARE quelqu'un »).

    Substrat (cf. `runner/components.py`, champ `times_healed_this_turn`) : `+0xd4` est incremente PAR
    SOIN par `IdunBattle.Operations.HealUnitOperation$$Execute` et remis a zero par
    `IdunBattle.Operations.StartTurnOperation$$ResetUnit`. La cle `timesHealedThisTurn` du dict
    d'unite DSL est produite par `runner/abilities/behaviours/context.py::_unit_dict`, et elle est
    LIVE (l'increment natif PRECEDE l'emission du vecteur qui fait relire ce nombre). Unite
    hors-`State` (dict fige de la face PREDICTION) -> 0, meme regime que
    `LastHitDamageTakenLastTurn`.

    Consommateur porte : le gate `AmountIsEqual(TimesHealedThisTurn(Target@DSLSelectors+0x60),
    <DSLFormulas+0x20> = Const(1))` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateTrigger`."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("timesHealedThisTurn", 0) or 0)


class TilesMovedThisTurn(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn(unit)` ->
    `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` : resout le selecteur, prend
    l'`ActorStatisticsComponent` de l'entite et rend **`*(uint *)(comp + 0xf0)`** -- combien de
    TUILES cette unite a parcourues depuis le debut de son tour.

    La fabrique est un simple `new <Formula>(unit)` : le corps ENTIER de
    `DSLFormulas$$TilesMovedThisTurn` alloue la formule et lui passe le selecteur, rien d'autre.

    SUBSTRAT DEJA PORTE, et c'est ce qui fait de ce noeud une ENVELOPPE MINCE : `+0xf0` est le champ
    qu'ecrit `ActorStatisticsComponent$$AddTilesMoved` (`comp[0xec] += tiles ; comp[0xf0] += tiles`,
    garde `< 1`) et que remet a zero `ActorStatisticsComponent$$ResetThisTurn`. Cote port, l'ECRIVAIN
    et le LECTEUR existaient tous deux avant cette classe -- `runner/components.py::
    unit_tiles_moved_this_turn` (lecteur COMBAT, consomme par `damage_model.attacker_modifiers`) et
    `playbook/scene.py::tiles_moved_this_turn` (face DECISION). Ce qui manquait etait le noeud DSL,
    c.-a-d. la voie par laquelle un ARBRE peut lire le compteur.

    LA CLE EST LIVE, et pour la MEME raison mesuree que `timesHealedThisTurn` ci-dessus : l'increment
    natif PRECEDE l'emission du vecteur qui fait relire ce nombre. `MoveUnitOperation$$Execute`
    incremente `+0xf0` puis appelle `EvaluateAfterMoveTriggers`, qui publie `On(4 = UnitAfterMove)`.
    Figee au seed, la valeur serait celle d'AVANT le deplacement -- donc `0` au premier move du tour,
    et le gate `AmountIsEqualOrGreater(TilesMovedThisTurn(Actor), Get(tilesTraversed))` de
    `...MastersOfManoeuvreAbility$$CreateTrigger` ne matcherait JAMAIS.

    Unite hors-`State` (dict fige de la face PREDICTION) -> 0, meme regime que `TimesHealedThisTurn`
    et `LastHitDamageTakenLastTurn`.

    ⚠ NE PAS CONFONDRE avec `MovementSteps()`, le `Nullable<int>` propage par
    `EvaluateAfterMoveTriggers` : celui-la est le nombre de pas DU DEPLACEMENT COURANT, celui-ci le
    CUMUL du tour. Un porteur qui bouge deux fois dans le tour les separe.

    Consommateur porte : la branche `<A>` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility$$CreateTrigger`."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("tilesMovedThisTurn", 0) or 0)


class CriticalHitsThisTurn(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$CriticalHitsThisTurn(unit)` ->
    `IdunBattle.Entities.Formulas.CriticalHitsThisTurnFormula$$Calculate` -- MIRROR du decompile :
    resout le selecteur (`this+0x10`, slot 8 = `SelectActor`), prend l'`ActorStatisticsComponent` de
    l'unite et rend **`*(uint *)(comp + 0x54)`** -- combien de COUPS CRITIQUES cette unite a PORTES
    depuis le debut de son tour.

    La fabrique est un simple `new <Formula>(unit)` : le corps ENTIER de
    `DSLFormulas$$CriticalHitsThisTurn` alloue la formule et lui passe le selecteur, rien d'autre --
    meme forme que `TilesMovedThisTurn` ci-dessus.

    SUBSTRAT PORTE PAR LA MEME TRANCHE (#521-r10), aux DEUX bouts, et les deux sont LUS :
      * ECRITURE `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade`
        (`*(int *)(this + 0x54) += (int)totalCrits`), seul appelant natif
        `IdunBattle.Operations.RegisterAttackOperation$$Execute` -- port
        `runner/components.py::register_attack_made`, appele par le chokepoint de degat ;
      * RESET `...$$ResetUnitsAttackedThisTurn` (`this[0x54] = 0`), appele par
        `IdunBattle.Operations.StartTurnOperation$$Execute` / `$$ResetUnit` / `$$ResetMachine` --
        port `runner/components.py::reset_units_attacked_this_turn`.
    C'est donc bien un compteur PER-TOUR : aucun des deux `ActorStatisticsComponent$$ResetThisTurn`
    ne touche `+0x54`, mais l'entree de tour l'efface.

    LA CLE EST LIVE, pour la MEME raison mesuree que `timesHealedThisTurn` / `tilesMovedThisTurn` :
    l'increment natif PRECEDE l'emission du vecteur qui fait relire le nombre. Le seul consommateur
    lit sur `On(0xe = UnitPostAbility)`, c'est-a-dire APRES l'attaque qui vient de produire les
    crits ; figee au seed, la valeur serait celle d'AVANT et le gate ne matcherait jamais.

    Unite hors-`State` (dict fige de la face PREDICTION) -> 0, meme regime que `TimesHealedThisTurn`
    et `TilesMovedThisTurn`. Le natif, lui, LEVE sur un composant manquant (cf.
    `runner/components.py::unit_critical_hits_this_turn`, qui porte la mesure et dit pourquoi le
    port rabat sur 0).

    Consommateur porte : le gate `AmountIsEqualOrGreater(CriticalHitsThisTurn(Owner@DSLSelectors+0x30),
    Direct(GetHits2()))` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_RemoveCritChance$$CreateBehaviour`
    (#521-r4). C'est aussi le SEUL call-site natif du noeud."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return int((u or {}).get("criticalHitsThisTurn", 0) or 0)


class TimesRepaired(AAmountFormula):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def calculate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class RoundsStarted(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$RoundsStarted(selecteur)` ->
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
    """`IdunBattleLogic.Entities.DSLFormulas$$TotalRepairActionsAmount(selecteur)` ->
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
    """`IdunBattleLogic.Entities.DSLFormulas$$TotalAttacksMade` = `Entities.Formulas.TotalAttacksMadeFormula` (IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate) :
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
    `IdunBattleLogic.Entities.DSLBehaviors$$AddOrUpdateStaticStatModifierEffect` : ctor `(dslFactory+0x38, unit,
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
    """`IdunBattleLogic.Entities.DSLFormulas$$TotalActiveAbilityUsed(unit, abilityType)` : le natif alloue un
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
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitTurnsStarted` = `Entities.Formulas.UnitTurnsStartedFormula` (IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate) :
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
    """`IdunBattleLogic.Entities.DSLFormulas$$TurnsFromRounds(rounds)` → `IdunBattle.Entities.Formulas.TurnsFromRoundsFormula$$Calculate`
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
    """`IdunBattleLogic.Entities.DSLFormulas$$Get(value)` = `Const`/`Direct` : enveloppe une valeur littérale int/enum en
    nœud (MÊME singleton DAT_183202d40 + ctor `(value,0)` que `Direct`). Le nom de ctor mislabelé
    `IceTileEffect...d__5` est un trampoline gshared — la classe réelle est le nœud constante, PAS un
    accesseur. (Les overloads IdunBattleLogic.Entities.DSLSelectors$$Get/IdunBattleLogic.Entities.DSLSelectors$$Get sur arg objet = sélecteurs distincts, hors batch.)"""


class VisualUnitIdFromUnitId(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$VisualUnitIdFromUnitId(unitIdValue)` : noeud VALEUR convertissant un id de
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
    """`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(key)` → `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` :
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
    """`IdunBattleLogic.Entities.DSLFormulas$$StatAmount(selector, statType, variant, level)` →
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


class CurrentShieldAmount(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$CurrentShieldAmount(unit, selectionType)` ->
    `IdunBattle.Entities.Formulas.CurrentShieldAmountFormula$$Calculate` -- MIRROR 1:1 du decompile,
    dont le corps utile tient en quatre lignes :

        total = 0
        list  = this-><+0x10>.Select(entities, this-><+0x18>)     # selecteur, selectionType
        foreach (e in list)
            total += IdunBattle.Entities.UnitExtensions$$GetShield(<e resolue en unite>)
        return total

    C'est donc une **SOMME** sur TOUTES les unites du selecteur, pas la lecture d'une unite unique --
    et le `GetShield` appele est le TOTAL du `ShieldComponent` (toutes instances confondues), pas une
    instance. Sur les trois call-sites natifs recenses le selecteur est un singleton
    (`Target@<DSLSelectors+0x60>`, `Attacker`), donc la somme y vaut la lecture ; l'ecrire en somme
    est ce qui la garde juste si un call-site multi apparait.

    Le ctor natif est `<ctor>(unit, selectionType, 0)` -- il porte le nom ghidra
    `UnityEngine.Timeline.SupportsChildTracksAttribute$$.ctor` (corps DEDUPLIQUE, le MEME que celui
    d'`HasRarity` : la STRUCTURE est lue, jamais le nom).

    `selection_type` est TRANSPORTE et non LU -- meme residu que les quatre call-sites deja portes de
    `TriggerAbilityDelayed` : le port n'a qu'un domaine d'unites deja resolu.

    ⚠ DEGRADATION **PERMISSIVE** (accesseur absent -> 0), nommee au champ `ctx.current_shield_amount`
    : l'unique forme d'emploi native est `AmountIsZero(CurrentShieldAmount(...))`, donc un 0 non
    mesure fait PASSER le gate au lieu de le fermer. Le seul consommateur porte tourne toujours avec
    un `State`."""
    def __init__(self, unit: TargetsSelector, selection_type: int = 0):
        self.unit, self.selection_type = unit, int(selection_type)

    def calculate(self, ctx):
        fn = getattr(ctx, "current_shield_amount", None)
        if fn is None:
            return 0
        return sum(int(fn(u)) for u in _units_of(self.unit, ctx))


class StatNegativeModification(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$StatNegativeModification(unit, statType)` ->
    `IdunBattle.Entities.Formulas.NegativeStatModificationFormula$$Calculate` : SOMME, sur les unites
    du selecteur, des VALEURS ABSOLUES des modifications per-source strictement NEGATIVES de
    `statType`. Toujours >= 0.

    ⚠ CE N'EST PAS `StatAmount(..., StatPart.MODIFICATION)` : ce dernier rend le TOTAL SIGNE (donc
    `-40 + 40 = 0`), la ou cette formule ne retient QUE les contributions negatives et les rend en
    valeur absolue. C'est le meme dictionnaire per-source des DEUX cotes, et c'est ce qui les rend
    confondables au premier coup d'oeil.

    Le 3e argument du ctor natif (`3`) est le `selectionType` du selecteur (comme le `+0x1c` de
    `StatAmountFormula`), pas un `StatPart` : cette formule N'A PAS de `StatPart` -- elle ne lit que
    les modifications.

    Substrat : `ctx.negative_stat_modification(unit, statType)` (pose par `entities_from_state` ->
    `UnitStats.negative_stat_modification`). Accesseur ABSENT -> **0**, degradation fidele : le
    gate consommateur (`AmountIsGreater(ratio, armorReductionPct)`) devient alors FAUX, donc
    RESTRICTIF -- jamais permissif.

    Consommateurs natifs (les DEUX seuls du build `rnca9r7q6c`, mesure `dsl-usage-edges.tsv`) :
    `...OrbsOfDecayAbility$$CreateBehaviour` et `...OrbsOfDecayAbility$$GetTriggerForAttack`."""
    def __init__(self, selector: TargetsSelector, stat_type: int):
        self.selector, self.stat_type = selector, int(stat_type)

    def calculate(self, ctx):
        fn = getattr(ctx, "negative_stat_modification", None)
        if fn is None:
            return 0
        return sum(int(fn(u, self.stat_type)) for u in _units_of(self.selector, ctx))


class UnitNormalAttackType(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitNormalAttackType(entitySelector)` → value-provider lisant le
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

    ⚠ **LE SUBSTRAT N'EST PAS LE KIT GAMECONFIG, ET C'EST MESURE.** Le jumeau `UnitNormalAttackType`
    ci-dessus derive du `visualId` + gameconfig ; ce raccourci NE MARCHE PAS ici. L'ability de
    reparation d'une unite ne vient pas de son `activeAbilities` : `votanSmnEcog` a
    `activeAbilities = []` et repare pourtant -- il la tient de son TRAIT `Mechanic`. Une derivation
    par kit rendrait donc `None` sur le seul porteur qui compte, c'est-a-dire un filtre TOUJOURS
    VIDE et un port MUET (aucune erreur, aucune trace).

    On passe donc par un accesseur de CONTEXTE (`ctx.normal_repair_type`), alimente par
    `entities_from_state` depuis le substrat RUNNER -- meme discipline que
    `ctx.valid_normal_attack_targets` et `ctx.has_any_valid_target`. Accesseur absent (contexte hors
    runner : prediction, test de noeud) -> `None`, degradation NOMMEE."""
    def __init__(self, selector: TargetsSelector):
        self.selector = selector

    def calculate(self, ctx):
        u = resolve_unit(self.selector, ctx)
        # `if (unit != null)` du natif -- le `Nullable` VIDE quand `SelectSingle` ne resout rien.
        if u is None:
            return None
        accessor = getattr(ctx, "normal_repair_type", None)
        if accessor is None:
            return None
        return accessor(u)


class ConfigVarForEntity(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(abilityOrEffect, entity, varKey)` → `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` = `AbilityConfiguration.GetVariableForLevel(varKey, level)` sur la config de l'ability
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
    """`IdunBattleLogic.Entities.DSLFormulas$$EntityId(entity)` : id de l'entité résolue (ou None).

    DOMAINE MIXTE (#889-r6) : le natif lit `IEntity.Id` sur l'entité que rend le sélecteur, et une
    TUILE est une entité comme une autre. Le port représente une unité par un `dict` (clé `id`) et
    une tuile par son `id` de tuile NU (`int`) -- même convention que `Sub._key` et
    `selectors/_shared._entity_pos`, tous deux explicitement en domaine mixte. Un sélecteur
    tile-domain rendait donc `None` ici, en silence.

    Le sélecteur est réduit à SON PREMIER élément : le natif passe par
    `IdunBattle.DSL.TargetsSelector$$SelectSingle`, pas par une somme -- une liste vide rend `None`
    (et non `0`, qui désignerait une entité).

    ⚠ **CE `None` N'EST PAS INTERCHANGEABLE AVEC `0`.** Son seul consommateur porté à ce jour est
    `SetPersistentData` (`...InstrumentsOfVengeanceAbility$$GetEffectBehavior`), dont la feuille
    n'écrit RIEN quand la valeur est `None` -- alors qu'écrire `0` poserait une clé que
    `GetPersistentData` relirait comme une entité. Les deux régimes se distinguent au tour suivant."""
    def __init__(self, ref):
        self.ref = ref

    def calculate(self, ctx):
        e = self.ref.evaluate(ctx)
        if isinstance(e, (list, tuple)):               # `SelectSingle` : le PREMIER, pas la somme
            e = e[0] if e else None
        if isinstance(e, dict):
            return e.get("id")
        if isinstance(e, bool):                        # un bool EST un int en Python -- jamais un id
            return None
        if isinstance(e, int):                         # domaine TUILE : l'id de tuile EST l'entite
            return e
        return None


class EffectLevel(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$EffectLevel` : niveau de l'effet COURANT (`ctx.effect`). 0 si absent."""
    def calculate(self, ctx):
        return _effect_field(ctx.effect, "level", 0)


class EffectLevelOf(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$EffectLevel(effects)` -- l'AUTRE surcharge, celle qui
    prend un SELECTEUR d'entites-effet, mirror de
    `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate` :

        sel = this+0x10;                                   // le selecteur d'effets
        effects = sel.<slot 0xd>(entities);
        total = 0;
        foreach (e in effects)  total += GetComponent<EffectComponent>(e).<+0x68>;   // le NIVEAU
        return total;

    C'est une **SOMME**, pas un premier ni un max -- et c'est ce qui realise le « Transfers ALL
    levels of Machine Vengeance » de `SolarAtomizer` : chaque instance portee par chaque allie
    mecanique ajoute son niveau. Selecteur vide -> `0` (l'accumulateur natif part de 0 et la boucle
    ne tourne pas).

    A NE PAS confondre avec `EffectLevel` ci-dessus (`IdunBattleLogic.Entities.DSLFormulas$$EffectLevel`, SANS argument), qui
    lit le niveau de l'effet COURANT du contexte d'application."""
    def __init__(self, effects: TargetsSelector):
        self.effects = effects

    def calculate(self, ctx):
        v = self.effects.evaluate(ctx)
        if not v:
            return 0
        if isinstance(v, dict):                 # accesseur mono-entite -> sequence d'un element
            v = [v]
        return sum(int(_effect_field(e, "level", 0) or 0) for e in v)


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
        #
        # ⚠ #1050-r1 -- CE FOYER NE VOYAIT QUE LE DOMAINE UNITE, ET SON PROPRE COMMENTAIRE LE DISAIT
        # (<< ne couvre que la branche UNITE, ce qui suffit a ses call-sites >>, cf.
        # `_select_tiles_positions` juste en dessous). Le filtre `isinstance(u, dict)` JETAIT
        # silencieusement tout operande deja en domaine TUILE -- la liste devenait vide des DEUX
        # cotes et la formule rendait `MIN_DISTANCE_EMPTY` (`int.MaxValue`), donc un rayon absurde,
        # sans lever. Or le slot 10 natif (`IdunBattle.DSL.TargetsSelector$$SelectTiles`) est
        # DOMAINE MIXTE par construction : `if (<this est deja un selecteur de TUILES>) return sel`.
        # Le call-site qui l'exige est `AncientFury_NormalAttackAbility$$GetTarget` :
        # `DSLFormulas$$MinDistance(CasterTiles@0x58, TargetTiles@0x78)` -- DEUX selecteurs de
        # tuiles. On delegue donc au helper qui porte deja le slot 10 complet ; il traite un dict
        # d'unite par `_feet`, exactement comme la boucle d'avant -> aucun changement de valeur pour
        # les call-sites en domaine UNITE.
        return get_distance(_select_tiles_positions(self.a, ctx),
                            _select_tiles_positions(self.b, ctx))   # meme seed `int.MaxValue`


# `IdunBattle.Core.Services.BattleQuery$$GetAverageDistance(tilesA, tilesB, defaultValue)` : le
# `defaultValue` que la formule DSL lui passe, LU au decompile d'
# `IdunBattle.Entities.Formulas.AverageDistanceFormula$$Calculate` (l'immediat `10000` du call de
# slot 112). C'est ce que rend la formule quand AUCUNE paire n'est mesurable -- pas 0, pas
# `int.MaxValue` : un « tres loin » fini, qui trie donc APRES toute distance reelle en ordre
# croissant et AVANT en ordre decroissant. Le seed de `MinDistance` ci-dessus est un AUTRE sentinel
# (`int.MaxValue`), et les confondre changerait le classement.
AVERAGE_DISTANCE_EMPTY = 10000


def _select_tiles_positions(sel: TargetsSelector, ctx) -> list:
    """`IdunBattle.DSL.TargetsSelector$$SelectTiles` (slot 10) en domaine POSITION : liste PLATE des
    tuiles de toutes les entites selectionnees. Domaine MIXTE assume -- une UNITE materialise son
    EMPREINTE (`EntityExtensions$$IterateTiles`, `_feet`), une TUILE (id / position) se materialise
    elle-meme (`_entity_pos`). `MinDistance` ci-dessus ne couvre que la branche UNITE, ce qui suffit
    a ses call-sites ; les call-sites de `AverageDistance` melangent les deux (une TUILE candidate
    d'un cote, des UNITES de l'autre)."""
    board = getattr(ctx, "board", None)
    v = sel.evaluate(ctx) if hasattr(sel, "evaluate") else sel
    if v is None:
        return []
    if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v):
        items = [v]
    elif isinstance(v, (dict, int)):
        items = [v]
    else:
        items = list(v)
    out = []
    for it in items:
        if isinstance(it, dict):
            out.extend((int(p[0]), int(p[1])) for p in _feet(it) if p is not None)
            continue
        p = _entity_pos(it, board)
        if p is not None:
            out.append((int(p[0]), int(p[1])))
    return out


class AverageDistance(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$AverageDistance(a, b)` ->
    `IdunBattle.Entities.Formulas.AverageDistanceFormula$$Calculate` -- MIRROR du decompile :

        tilesA = <a @+0x10>.SelectTiles(entities)      # slot 10
        tilesB = <b @+0x18>.SelectTiles(entities)      # slot 10
        return <query @+0x20>.GetAverageDistance(tilesA, tilesB, defaultValue: 10000)   # slot 112

    et `IdunBattle.Core.Services.BattleQuery$$GetAverageDistance` (MIRROR, lu terme a terme) :

        count = 0 ; sum = 0
        foreach (ea in tilesA)
            foreach (eb in tilesB)
                count++ ;  sum += PositionComponent.Distance(eb.Position, ea.Position)
        return count == 0 ? defaultValue : sum / count        # division ENTIERE, troncature

    Trois consequences que le port reproduit telles quelles :
      * la division est ENTIERE (`(longlong)sum / (longlong)count`, troncature vers zero) -- une
        moyenne de 7/2 vaut **3**, pas 3.5 ;
      * `count` s'incremente pour CHAQUE paire, y compris quand la distance est nulle -- c'est un
        produit cartesien `|A| x |B|`, pas une moyenne par entite ;
      * une source VIDE d'UN SEUL cote suffit a rendre `defaultValue` (le `count == 0` couvre les
        deux : boucle externe qui ne tourne pas, ou interne qui ne tourne jamais).

    `PositionComponent$$Distance` = `CubeCoordinate$$Distance` = `Max(|dx|,|dy|,|dz|)`, la distance
    hex NUE -- meme chemin que `MinDistance` ci-dessus, donc `hexgeo.distance` (foyer
    `services.movement_query.get_distance` pour le MIN ; ici la somme est faite sur place, la
    moyenne n'ayant pas de foyer partage).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    CallRipperSwarmsAbility$$ExecuteBehaviour` (`AverageDistance(ActiveTarget@+0x68, enemies)`,
    la cle du `SortByFormula` qui classe les tuiles de spawn)."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def calculate(self, ctx):
        ta = _select_tiles_positions(self.a, ctx)
        tb = _select_tiles_positions(self.b, ctx)
        count = 0
        total = 0
        for pa in ta:
            for pb in tb:
                count += 1
                total += hexgeo.distance(pb, pa)      # `PositionComponent$$Distance(eb, ea)`
        if count == 0:
            return AVERAGE_DISTANCE_EMPTY
        return int(total // count) if total >= 0 else -int((-total) // count)


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


class NormalAttackRange(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$NormalAttackRange(unit, unitTile)` ->
    `IdunBattle.Entities.Formulas.NormalAttackRangeFormula$$Calculate`, MIRROR du decompile :

        entity = <+0x28 : unit>.SelectSingle(entities)
        tiles  = <+0x30 : unitTile>.Select(entities)
        if (tiles == null || tiles.Count == 0) tiles = EntityExtensions.GetTiles(entity, state)
        opts   = <+0x18>.<slot 0x3e>( UnitExtensions.GetNormalAttackType(entity) )
        return   <+0x20>.<slot 0xc>( entity, tiles, opts )

    -- soit la PORTEE des `TargetingOptions` de l'attaque NORMALE de l'unite, mesuree depuis ses
    tuiles. Le port lit cette portee par l'accesseur `ctx.normal_attack_range`, cable sur le foyer
    UNIQUE `runner/abilities/targeting.unit_weapon_range` (les TROIS branches d'arme de
    `IdunBattle.Core.Services.TargetingQuery$$GetRange`, deja portees et confrontees).

    `unit_tile` est accepte pour le MIRROR STRUCTUREL de la signature ; le foyer mesure depuis la
    position REELLE de l'unite, ce qui est exact au seul call-site porte
    (`InstinctiveBehaviour_UpdateTargetAbility$$GetUpdatedForcedTarget` passe `Tiles(Owner)`, donc
    litteralement les tuiles courantes de l'unite).

    **`0` QUAND LE CANAL SE TAIT**, et la direction est NOMMEE : `unit_weapon_range` rend `None`
    pour la seule branche `!HasAnyWeapon` (81 unites du gameconfig -- Machines of War et decor,
    dont AUCUNE ne porte `InstinctiveBehaviour`). Au seul consommateur porte, cette valeur entre
    dans un `Sum(range, movement)` qui borne un `NearestAttackableEnemies` : un `0` RETRECIT le
    rayon, donc rend MOINS de cibles forcees, donc laisse l'unite MOBILE -- degradation permissive,
    jamais un blocage invente. Inventer `1` (melee) serait au contraire une portee affirmee."""
    __slots__ = ("unit", "unit_tile")

    def __init__(self, unit: TargetsSelector, unit_tile: TargetsSelector = None):
        self.unit, self.unit_tile = unit, unit_tile

    def calculate(self, ctx) -> int:
        fn = getattr(ctx, "normal_attack_range", None)
        if fn is None:
            return 0                                   # canal non branche -> cf. docstring
        u = resolve_unit(self.unit, ctx)                # `SelectSingle(unit)`
        if u is None or u.get("id") is None:
            return 0
        return int(fn(int(u["id"])) or 0)

