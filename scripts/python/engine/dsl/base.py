"""Socle DSL GENERIQUE - `Node`, `DslContext` et helpers partages (moteur de NOEUDS, mirror 1:1 du
DSL lazy `DSLFactory`/`TargetsSelector` du jeu).

Chaque ability compose un arbre de `Node` evalue par `Node.evaluate(ctx)` contre un `DslContext` (etat de
bataille). Types de valeur (comme le DSL natif, type) : NUMERIQUE -> int ; CONDITION -> bool ; POSITION ->
(col,row) ; CIBLAGE -> list[unit]. Unite = dict `{id, team, hp, alive, pos:{col,row}, visualId}`.

Ghidra MISLABEL les ctors de noeuds gshared (le ctor de `DSLFactory.Sum @180dfc200` s'affiche
`HasUsedActiveAbilityThisTurnTrigger$$.ctor`) -> semantique lue via la STRUCTURE (pointeur de classe, args
enfants, arithmetique), JAMAIS via les noms. cf. [[feedback_re_ghidra_not_experiment]].

Modules soeurs (split ~1000 lignes) : arithmetic / predicates / selectors / accessors. `nodes.py` reste un
shim de compat re-exportant tout. cf. docs/rl/dsl-vocabulary-catalog.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

import hexgeo


class Node:
    """Nœud DSL. `evaluate(ctx)` = valeur résolue contre l'état (int/bool/pos/list selon le nœud)."""
    def evaluate(self, ctx: DslContext):
        raise NotImplementedError


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
    # Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    # OriginalTarget) — lu par le nœud `Subject` et les prédicats évalués sous un Filter. None hors Filter.
    subject: dict | None = None
    # Facteur de conversion rounds→turns (`TurnsFromRounds`, méthode runtime index 0x1b) : dépend du
    # nb d'équipes/joueurs actifs par round, NON capté offline → défaut 1 (identité, cf. times_attacked).
    turns_per_round: int = 1
    # Rôles distincts de l'AbilityEntities (slots factory +0x148/+0x158) pour les prédicats `OwnerIs*`.
    # Défaut None → retombe sur `caster` (hypothèse standard Owner==Caster==Actor, divergence documentée).
    owner: dict | None = None
    actor: dict | None = None
    # Accès trait/stat PAR UNITÉ (mirror `UnitExtensions.HasFlag`/`GetStat`) — hors state standard.
    # `has_trait(unit, traitId)->bool` défaut None → trait absent ; `get_stat(unit, statType, variant,
    # level)->int` défaut None → Health via hp (cf. `_default_get_stat`). Fournis par la couche ability.
    has_trait: object | None = None
    get_stat: object | None = None
    # Contexte d'ATTAQUE courant (Is*Attack) = type de l'ability en cours d'éval. Statique (profil
    # gameconfig), câblé par la couche ability ; défaut None → prédicats d'attaque = False.
    attack_kind: str | None = None           # 'melee' | 'ranged'
    attack_ability_type: int | None = None   # ActiveAbilityType (IsNormalAttack compare vs 1013)
    # Accès effets par unité (HasEffect/HasAnyEffect), mirror `HasOneOfEffects @180eb7640` — hors state
    # standard. `has_effect(unit, effectType, source_flag=6, min_level=0)->bool` défaut None → False.
    has_effect: object | None = None
    # Effet COURANT (EffectSource/EffectLevel) — n'existe qu'en application d'effet ; défaut None.
    effect: object | None = None


class Const(Node):
    """`DSLFactory.Direct(value)` : constante littérale."""
    def __init__(self, value: int):
        self.value = value

    def evaluate(self, ctx):
        return self.value


def _pos(u):
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


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


def _round_fix64(value: Fraction, mode: int) -> int:
    """`RoundFix64Result @180ffa110` : arrondit un quotient Fix64 en int selon `mode` (3ᵉ arg des
    factories Divide/Half/PercentageOf) : `1`=Ceiling, `2`=Floor, sinon (`0`)=Round half-to-even
    (`Fix64.Round`). On modélise le Fix64 par un `Fraction` EXACT (précision ≫ Fix64 pour des entrées
    entières) ; `round(Fraction)` = arrondi banquier (half-to-even), fidèle au mode 0."""
    if mode == 1:
        return math.ceil(value)
    if mode == 2:
        return math.floor(value)
    return round(value)


def _c_mod(a: int, b: int) -> int:
    """Modulo ENTIER signé à la C (`%` tronqué vers zéro, signe du dividende) — ≠ `%` Python (plancher).
    Fidèle à `ModuloAbilityTrigger` (`iVar15 % iVar16`, opérandes signées)."""
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def _same_entity(a, b) -> bool:
    """Égalité d'entité (mirror `AreEqual` sur des références d'entité) : même objet ou même id."""
    if a is None or b is None:
        return a is b
    return a is b or a.get("id") == b.get("id")


def _units_of(node, ctx) -> list:
    """Normalise l'évaluation d'un opérande-sujet en list[unit] : un dict → `[dict]` (cas `Subject` sous
    Filter), une liste → telle quelle, None → `[]`. Les prédicats unité appliquent un `any` dessus."""
    v = node.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)


def _effect_field(e, field, default):
    """Lit un champ de l'effet courant (`ctx.effect`), dict ou objet."""
    if e is None:
        return default
    if isinstance(e, dict):
        return e.get(field, default)
    return getattr(e, field, default)


def _is_alive(u) -> bool:
    return bool(u.get("alive", True)) and (u.get("hp") or 0) > 0


def _default_get_stat(u, stat_type, variant, level):
    """Défaut dégradé de `ctx.get_stat` : seule la santé est captée offline (le vrai accès stats vient
    de `ctx.get_stat` fourni par la couche ability)."""
    # HARDCODE (degrade) : StatType.Health=5 (dump.cs) -- seul stat lisible dans le state offline
    # {id,team,hp,alive,pos,visualId} ; autres StatType -> 0 tant que ctx.get_stat reel absent.
    # TEMP : variant base/current/max non tranche (validator) -- on rend le hp COURANT (natif lit maxHP).
    if stat_type == 5:
        return u.get("hp") or 0
    return 0
