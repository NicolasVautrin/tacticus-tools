"""Socle DSL GÉNÉRIQUE — moteur de NŒUDS (mirror 1:1 du DSL lazy du jeu, `DSLFactory`/`TargetsSelector`).

Le jeu définit chaque formule d'ability (`GetHits`, `GetSurroundingUnits`, `GetOtherTargets`, …) comme un
**arbre d'expression lazy** : `Sum(a, b)` est un NŒUD dont les opérandes `a`, `b` sont des sous-arbres
(ex. `Multiply(ConfigConst(extraHit), TotalTimesAttacked())`), évalué contre l'état de bataille au bon
instant. On mirroir cette structure 1:1 (règle projet « le Python reflète la structure du jeu ») : un
`Node` par primitive, un évaluateur unique `Node.evaluate(ctx)`. Chaque ability = l'arbre EXACT du
décompilé, vérifiable nœud-par-nœud (cf. active_ability.py, VA citées).

⚠ **Ghidra MISLABEL les ctors de nœuds gshared** (le ctor de `DSLFactory.Sum @180dfc200` s'affiche
`HasUsedActiveAbilityThisTurnTrigger$$.ctor`) → sémantique lue via la STRUCTURE (pointeur de classe, args
enfants, arithmétique), JAMAIS via les noms. cf. [[feedback_re_ghidra_not_experiment]].

Types de valeur (comme le DSL natif, typé) : les nœuds NUMÉRIQUES → int ; CONDITION → bool ; POSITION →
(col,row) ; CIBLAGE → list[unit]. Unité = dict `{id, team, hp, alive, pos:{col,row}, visualId}` (step_context).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import hexgeo


@dataclass
class DslContext:
    """Contexte d'évaluation d'un arbre DSL (l'« état de bataille » que le nœud interroge).

    `config`/`ability_level` → `ConfigConst` ; `caster`/`target`/`units` → ciblage + positions ;
    `times_attacked` = compteur runtime du caster (`TotalTimesAttackedFormula @180f26620`, composant @+0x34)
    NON capté offline → défaut 0 ; `flags` = ensemble de flags actifs (`HasFlag`). `units`/`caster`/`target`
    ne sont requis que par les nœuds de CIBLAGE (AoE) — un arbre purement numérique (hits) les ignore."""
    units: list = field(default_factory=list)
    caster: dict | None = None
    target: dict | None = None
    config: object | None = None            # AbilityConfiguration
    ability_level: int = 0
    times_attacked: int = 0
    # Compteur runtime de RÉPARATIONS du caster (`DSLFactory.TimesRepaired`, ex. DakkaDakkaDakka
    # GetNumHits @1811d0eb0) NON capté offline → défaut 0.
    times_repaired: int = 0
    flags: frozenset = field(default_factory=frozenset)
    # Position VIRTUELLE du caster pour la décision balayée (= la tuile d'attaque post-move,
    # `casterPosition` passé aux selectors par le generator natif). None → position courante.
    caster_pos: tuple | None = None
    # Élévation par tuile (tileMeta) — consommée par les selectors gated élévation
    # (`TilesOnSameElevationSelector`). None → filtre dégradé no-op (documenté par nœud).
    elev_by_pos: dict | None = None


class Node:
    """Nœud DSL. `evaluate(ctx)` = valeur résolue contre l'état (int/bool/pos/list selon le nœud)."""
    def evaluate(self, ctx: DslContext):
        raise NotImplementedError


# ── Feuilles numériques ───────────────────────────────────────────────────────────────────────
class Const(Node):
    """`DSLFactory.Direct(value)` : constante littérale."""
    def __init__(self, value: int):
        self.value = value

    def evaluate(self, ctx):
        return self.value


class ConfigConst(Node):
    """`DSLFactory.ConfigConst(key)` / `AbilityConfiguration.GetNumberConstant` : constante de config
    d'ability au niveau courant. Ids natifs = enum `AbilityConstantType` (dump.cs TypeDefIndex 24411) :
    0x2f=nrOfHits(47), 0x2b=extraHit(43), 0x48=maxNrOfHits(72), 0x16=range(22). ⚠ `GetNumberConstant
    @181576af0`->`GetStringConstant @181576bb0` LÈVE une exception si la clé est ABSENTE (TryGetValue
    échoue -> throw) : une clé référencée par un arbre EST toujours présente dans la config (jamais de
    défaut natif). ⚠ DIVERGENCE assumée : le `default` Python retourne une valeur là où le natif
    THROW — garde-fou offline inerte tant que la clé existe, mais il MASQUERAIT silencieusement une
    clé manquante (verdict validator 2026-07-02 : réserve non bloquante)."""
    def __init__(self, key: str, default: int = 0):
        self.key, self.default = key, default

    def evaluate(self, ctx):
        if ctx.config is None:
            return self.default
        return ctx.config.get_variable_for_level(self.key, ctx.ability_level, self.default)


# ── Opérateurs numériques (ctors @180dfc200/180df6930/180dedfe0 — arithmétique confirmée) ───────
class Sum(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) + self.b.evaluate(ctx)


class Min(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return min(self.a.evaluate(ctx), self.b.evaluate(ctx))


class Multiply(Node):
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) * self.b.evaluate(ctx)


class Difference(Node):
    """`DSLFactory.Difference(a,b) @180dedfe0` = `Sum(a, Multiply(b, -1))` = a - b."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        return self.a.evaluate(ctx) - self.b.evaluate(ctx)


class If(Node):
    """`DSLFactory.If(cond, a, b)` : `a` si `cond` (bool) sinon `b`. Évalue paresseusement la branche prise."""
    def __init__(self, cond: Node, a: Node, b: Node):
        self.cond, self.a, self.b = cond, a, b

    def evaluate(self, ctx):
        return (self.a if self.cond.evaluate(ctx) else self.b).evaluate(ctx)


# ── Feuilles runtime / condition ─────────────────────────────────────────────────────────────
class TotalTimesAttacked(Node):
    """`TotalTimesAttackedFormula.Calculate @180f26620` : compteur runtime d'attaques du caster
    (composant @+0x34). NON capté offline → `ctx.times_attacked` (défaut 0 = pré-snowball)."""
    def evaluate(self, ctx):
        return ctx.times_attacked or 0


class TimesRepaired(Node):
    """`DSLFactory.TimesRepaired` : compteur runtime de réparations du caster (Mechanical — ex.
    DakkaDakkaDakka `GetNumHits @1811d0eb0` : +extraHits coups par réparation). NON capté offline →
    `ctx.times_repaired` (défaut 0 = pré-snowball)."""
    def evaluate(self, ctx):
        return getattr(ctx, "times_repaired", 0) or 0


class HasFlag(Node):
    """`DSLFactory.HasFlag(flag)` : `flag ∈ ctx.flags`. Le sens exact du flag (ex. HarvesterOfSouls @+0x160)
    reste à RE ; défaut = absent (branche `flag=false`), confirmé par l'agrément."""
    def __init__(self, flag):
        self.flag = flag

    def evaluate(self, ctx):
        return self.flag in ctx.flags


# ── Positions (centres de ciblage) ─────────────────────────────────────────────────────────────
def _pos(u):
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


class CasterTile(Node):
    """Tuile du caster (`UnitPosition.MainTile` du casterPosition passé par le generator) — pour une
    décision balayée c'est la TUILE D'ATTAQUE candidate (`ctx.caster_pos`), pas la position courante."""
    def evaluate(self, ctx):
        return ctx.caster_pos or _pos(ctx.caster)


class TargetTile(Node):
    """Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`."""
    def evaluate(self, ctx):
        return _pos(ctx.target)


class OwnerTile(Node):
    """Tuile COURANTE (réelle) de l'owner/caster — position du composant entité, PAS la tuile d'attaque
    balayée. `HarvesterOfSoulsAbility.GetSurroundingUnits @1811e76a0` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `DakkaDakkaDakka.GetHealthToLose @1811d09a0`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
    La fonction native ne reçoit AUCUN `casterPosition` (elle ne prend que l'ability) -> sel@0x160 résout
    la position LIVE de l'owner (non déplacé pendant la prédiction), != `CasterTile` (= `ctx.caster_pos`,
    la tuile d'attaque post-move). Preuve ground-truth seed777 step-17 : AoE ancré sur (5,6)=owner-réel
    (et non (4,3)=tuile d'attaque) reproduit les 4 sets natifs (cf. active_ability.HarvesterOfSoulsAbility)."""
    def evaluate(self, ctx):
        return _pos(ctx.caster)


# ── Ciblage (évaluent → list[unit]) — géométrie hex `hexgeo.distance` fidèle à la grille ─────────
def _within(units, center, radius, include_center=False):
    out = []
    for u in units:
        p = _pos(u)
        if p is None:
            continue
        d = hexgeo.distance(p, center)
        if d <= radius and (include_center or d > 0):
            out.append(u)
    return out


class SurroundingUnits(Node):
    """`DSLFactory.SurroundingUnits(center, radius) @180dfcb70` = `Units(SurroundingTiles(center, radius))`
    = unités à distance hex <= radius du centre, centre exclu."""
    def __init__(self, center: Node, radius: Node):
        self.center, self.radius = center, radius

    def evaluate(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class AdjacentEnemies(Node):
    """`DSLFactory.AdjacentEnemies(caster) @180de80c0` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: Node, radius: Node | None = None):
        self.center, self.radius = center, radius or Const(1)

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class Enemies(Node):
    """`DSLFactory.Enemies` : filtre → équipe != celle du caster."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") != ct]


class Damageable(Node):
    """`DSLFactory.Damageable` : filtre → unités vivantes ciblables (PV > 0)."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        return [u for u in self.inner.evaluate(ctx)
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class And(Node):
    """`TargetsSelector.op_BitwiseAnd` : intersection par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") in bset]


class Sub(Node):
    """`TargetsSelector.op_Subtraction` : a \\ b par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") not in bset]


class UnitSet(Node):
    """Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE)."""
    def __init__(self, units: list):
        self.units = units

    def evaluate(self, ctx):
        return list(self.units)


class UnitsDirectlyBehind(Node):
    """`DSLFactory.UnitsDirectlyBehind @180dff5e0` — cibles secondaires « derrière la cible »
    (PlasmaCannon…). Transcription EXACTE de la construction native :
        ring    = SurroundingTiles(target, 1, 1) − Tiles(target)          # anneau R1 de la CIBLE
        cands   = Enemies(caster, Units(ring))                            # ennemis du caster dessus
        sameElv = TilesOnSameElevationSelector(target, cands, 1)          # même élévation que la cible
        behind  = FromTrigger(cands, dist(caster, cand) >= dist(caster, target))   # côté OPPOSÉ au caster
    (Les ctors de nœuds gshared sont MISLABELÉS par ghidra — sémantique lue par STRUCTURE : la paire
    SortReverse(caster)/SortReverse(x) + AmountIsEqualOrGreater = comparaison de DISTANCES au caster.)
    `dist` = distance hex ; caster = `ctx.caster_pos` (tuile d'attaque balayée). Élévation :
    `TilesOnSameElevationSelector.Select @180efa8a0` garde si `GetElevationDifference(cand, target)
    <= maxDiff` (ctor +0x28 = 1 ici) → TOLÉRANCE ±1, pas une égalité stricte (prouvé step-11 :
    78 elev1 derrière 82 elev2 inclus par le natif). Dégradé no-op sans `ctx.elev_by_pos`."""

    def evaluate(self, ctx):
        tpos = _pos(ctx.target)
        cpos = ctx.caster_pos or _pos(ctx.caster)
        if tpos is None or cpos is None:
            return []
        ct = (ctx.caster or {}).get("team")
        tid = (ctx.target or {}).get("id")
        d_ct = hexgeo.distance(cpos, tpos)
        out = []
        for u in ctx.units:
            p = _pos(u)
            if p is None or u.get("id") == tid or u.get("team") == ct:
                continue
            if hexgeo.distance(p, tpos) != 1:                      # anneau R1 de la cible
                continue
            if ctx.elev_by_pos is not None:                        # TilesOnSameElevationSelector (maxDiff=1)
                et, ec = ctx.elev_by_pos.get(tpos), ctx.elev_by_pos.get(p)
                if et is not None and ec is not None and abs(et - ec) > 1:
                    continue
            if hexgeo.distance(cpos, p) >= d_ct:                   # « derrière » = au moins aussi loin
                out.append(u)
        return out
