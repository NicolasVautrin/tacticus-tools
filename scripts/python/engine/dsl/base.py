"""Socle DSL GENERIQUE - les 4 BASES DE FAMILLE lazy, `DslContext` et helpers partages (moteur de
NOEUDS, mirror 1:1 du DSL lazy `DSLFactory`/`TargetsSelector` du jeu).

Le DSL natif = 4 familles, bases abstraites de `IdunBattle.DSL`, une methode d'eval chacune (probe
`dslLazyProbe`) : `AbilityBehaviour.Execute` (EFFETS, kind E, cf. effect_nodes.py), `AbilityTrigger.
ShouldTrigger` (PREDICATS, kind T), `TargetsSelector.Select` (SELECTEURS, kind S), `AAmountFormula.
Calculate` (VALEURS, kind V). Ce module porte les 3 bases LAZY (T/S/V, cf. ci-dessous) mirrorees NOM
POUR NOM ; l'effet (E) vit dans effect_nodes.py. Le natif n'a AUCUNE racine commune au-dessus des 4
(parents `[base, System.Object]`, interfaces `[]`) -> PAS de `Node` fourre-tout : 4 familles SOEURS.

Chaque ability compose un arbre evalue par la methode de sa famille (`should_trigger`/`select`/`calculate`)
contre un `DslContext` (etat de bataille). Types de valeur (comme le DSL natif, type) : NUMERIQUE -> int ;
CONDITION -> bool ; POSITION -> (col,row) ; CIBLAGE -> list[unit]. Unite = dict `{id, team, hp, alive,
pos:{col,row}, visualId}`.

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


# --- Bases DSL par FAMILLE (mirror 1:1 des bases abstraites natives ; une methode d'eval chacune). La
# methode NOMMEE COMME LE NATIF est le VRAI point de surcharge de chaque noeud ; `evaluate` reste un
# ALIAS GENERIQUE qui delegue -> les combinateurs POLY-FAMILLE (`Cache`, `Filter`, arithmetique, `Count`,
# `_units_of`) evaluent un enfant SANS connaitre sa famille (robustesse : pas de dispatch croise fragile).
# C'est une convenance de PORT (le natif dispatch par contrat type) documentee, pas une classe native.
class AAmountFormula:
    """Base des noeuds VALEUR (numerique -> int). Mirror `IdunBattle.DSL.AAmountFormula.Calculate` (kind V)."""
    def calculate(self, ctx: DslContext):
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):    # alias generique (cf. en-tete) -> methode native
        return self.calculate(ctx)


class AbilityTrigger:
    """Base des noeuds PREDICAT (-> bool). Mirror `IdunBattle.DSL.AbilityTrigger.ShouldTrigger` (kind T)."""
    def should_trigger(self, ctx: DslContext) -> bool:
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):
        return self.should_trigger(ctx)


class TargetsSelector:
    """Base des noeuds SELECTEUR (-> list/tuile/entite). Mirror `IdunBattle.DSL.TargetsSelector.Select` (kind S)."""
    def select(self, ctx: DslContext):
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):
        return self.select(ctx)


def resolve_unit(node, ctx):
    """Evalue un noeud (souvent `Subject()`/`Target()`) en UN dict d'unite : dict direct, ou 1er dict d'une
    liste. Helper PARTAGE (selecteurs `Entities.Selectors`, formules `Entities.Formulas`, feuilles
    `Entities.Behaviours` runner) -> vit dans la base commune. None si l'eval ne donne aucun dict."""
    v = node.evaluate(ctx)
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        for x in v:
            if isinstance(x, dict):
                return x
    return None


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
    # Graphe de tuiles (`Board`, entities/pathfinding) — consommé par les SÉLECTEURS DE TUILES
    # (`AdjacentTiles`/`CanAddUnit`, tile_selectors.py) : voisinage natif (`board.neighbours`),
    # walkable, id_at. None → domaine tile dégradé no-op (documenté par nœud).
    board: object | None = None
    # Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    # OriginalTarget) — lu par le nœud `Subject` et les prédicats évalués sous un Filter. None hors Filter.
    subject: dict | None = None
    # ACCUMULATEUR des enfants SPAWNÉS par le behaviour courant (mirror du champ factory natif `+0x148`
    # que `DSLFactory.Spawn` alimente et que `DSLFactory.Children @180debed0` (= `AllAliveMachinesSelector`)
    # relit — cf. GetEmRuntz `Foreach(Children, TauntWithNewChildrenWhoDidDamage)`). Liste PARTAGÉE (le
    # `replace(subject=…)` du `Foreach` la partage par référence) : les feuilles `SpawnUnit` y ajoutent le
    # dict de l'unité spawnée, `Children` la retourne. Défaut [] ; hors behaviour de spawn = vide.
    children: list = field(default_factory=list)
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
    # Accès effets par TUILE (prédicat de `UnitsOnTilesWithEffect @180dffc50` : la tuile porte-t-elle un
    # effet ACTIF du type — ex. Ice 0x11 pour Stormcaller #217). `tile_has_effect(tile_id, effectType)
    # ->bool` ; défaut None → sélecteur dégradé [] (documenté par nœud). Fourni par `entities_from_state`
    # (lit `state.effects` keyé tile-id, même clé que la pose `AddEffectOperation`, cf. case-35).
    tile_has_effect: object | None = None
    # Effet COURANT (EffectSource/EffectLevel) — n'existe qu'en application d'effet ; défaut None.
    effect: object | None = None
    # Faction (`FactionId` gameconfig) PAR UNITÉ (mirror `DSLFactory.UnitsFromFaction`, qui compare vs
    # `Enum.ToString(UnitFaction)` = le NOM de faction) — hors state standard, comme `has_trait`/`get_stat`.
    # `faction_of(unit)->str|None` défaut None → faction inconnue (UnitsFromFaction rend vide). Fourni par la
    # couche runner (`entities_from_state`) via `_faction(visualId)`.
    faction_of: object | None = None
    # Niveau d'ability PAR UNITÉ + slot (`ConfigVar` sur une unité TIERCE, ex. la chance RighteousRepugnance
    # au niveau du killer). `get_ability_level(unit, slot='passive'|'active')->int|None` : lit le
    # `passive_ability_level`/`active_ability_level` capté (StatsComponent.ctx). Défaut None → niveau inconnu
    # (le nœud consommateur dégrade sur le défaut d'`ability_var`). Fourni par `entities_from_state`.
    get_ability_level: object | None = None


class Const(AAmountFormula):
    """`DSLFactory.Direct(value)` : constante littérale (VALEUR)."""
    def __init__(self, value: int):
        self.value = value

    def calculate(self, ctx):
        return self.value


def _pos(u):
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


def _within(units, center, radius, include_center=False):
    """Anneau/disque d'unites autour de `center` — cœur des selecteurs d'OCCUPATION (`Units(
    SurroundingTiles/AdjacentTiles(...))`, tous les call-sites). VIVANTS SEULEMENT (#57m) : le natif
    resout les unites PAR TUILE (`UnitsOnTilesSelector.Select @180f02450` : selecteur de tuiles @+0x18
    + mode d'occupation main/steppable @+0x20 -> resolveur board) et un mort n'est plus sur sa tuile
    (KillUnit retire l'unite du board) — un cadavre de `ctx.units` (state garde alive=False) ne doit
    donc jamais sortir d'un selecteur d'occupation. Les selecteurs d'ENSEMBLE font leur propre choix
    (`AllUnits`=alive #202, `UnitsDefeatedByMeleeAttack`=morts expres) : le filtre vit ICI, pas dans
    ctx.units."""
    out = []
    for u in units:
        if not _is_alive(u):
            continue
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
