"""Base du namespace `IdunBattle.AI.Playbook` — hiérarchie + registry (RE playbook/architecture.md §2.2).

Hiérarchie native : `BasePlaybook -> {ComparablePlaybook<T>, NonComparablePlaybook<T>}`. Un générateur
d'action fait `LoadPlaybook(abilityType) -> playbook.Evaluate(unit, tile)` ; c'est le playbook qui
énumère ses cibles et les score. Deux régimes :

- **Comparable** (`ComparablePlaybook<T>`, attaques/soins) : `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` boucle les
  cibles éligibles à position caster FIXÉE, `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` par cible
  (`= predictionUtility + Σ CalculateUtilityFromPredictions + [gate ShouldExecute] + Tile(7)`), argmax
  dans un Bucket. `MakeDamagePredictions` (vtable) = le fournisseur de prédiction, OVERRIDÉ par playbook.
- **NonComparable** (`NonComparablePlaybook<T>`) : heuristique entière dans la feuille -> package `noncomparable/`.

PRÉDICTEUR : `ComparablePlaybook.make_damage_predictions` délègue à `engine.playbook.prediction`
(orchestration mince) sur le MODÈLE OBJET — `Scene` (état live) + `AActiveAbility`/`UnitContext`
(entities) + services (`BattleQuery` sélection d'arme, `DamagePrediction`/`DamageCalculations`) — et
produit des `ProbableDamageEvent`. Couvre AoE, multi-hit, split bouclier, modifiers d'effets, self-damage.
"""
from __future__ import annotations

from typing import Callable

from ..weights import Weights
from ..utilities import damage_composite
from ..utilities.tile import tile_composite


class _NoActionUtility:
    """Sentinelle de PORT : « le custom a rendu une valeur que `CalculateActionUtility` traduit en
    `Nullable` VIDE » — c'est-à-dire AUCUNE action générée pour ce (tuile, cible).

    Ce n'est pas une convention inventée, c'est un mirror. `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
    commence par appeler `CalculateCustomUtility` (slot de vtable +0x338) puis compare son résultat à
    TROIS constantes de `IdunBattle.AI.Utilities.BaseUtility`, AVANT toute prédiction :

        u = CalculateCustomUtility(...)
        if (u == BaseUtility.<statics+0x18>) return null;          // Nullable VIDE
        if (u == BaseUtility.<statics+0x20>) return null;          // Nullable VIDE
        if (u == BaseUtility.<statics+0x10>) return Nullable(BaseUtility.<statics+0x10>);
        u += CalculateUtilityFromPredictions(...); ...

    Les trois valeurs, lues dans `IdunBattle.AI.Utilities.BaseUtility$$.cctor` (qui les dérive de
    `FixMath.NET.Fix64$$.cctor` : `Fix64.<statics+0x10>` = `0x7fffffffffffffff` = MaxValue,
    `Fix64.<statics+0x18>` = `0x8000000000000000` = MinValue) :

        BaseUtility.<statics+0x10> = Fix64.MaxValue
        BaseUtility.<statics+0x18> = Fix64.MinValue / Fix64.FromIntFraction(1000001, 1000000)
        BaseUtility.<statics+0x20> = Fix64.MinValue

    Ce sont donc des VETOS : une utilité au voisinage de `MinValue` ne « perd » pas la comparaison,
    elle SUPPRIME l'action. Le port les représente par une IDENTITÉ (`is NO_ACTION`) plutôt que par
    un flottant proche de `-2**31` : la comparaison native est une égalité EXACTE sur un Fix64, qu'un
    port en `float` ne peut pas reproduire de façon fiable, et une valeur très négative laissée dans
    l'arithmétique serait sommée aux termes suivants au lieu d'annuler l'action.

    Porteur actuel : `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility`
    (1098), qui rend `BaseUtility.<statics+0x18>` dès que sa somme vaut `Fix64(0)`."""

    __slots__ = ()

    def __repr__(self) -> str:            # diagnostic lisible en trace de décision
        return "NO_ACTION"


NO_ACTION = _NoActionUtility()


class BasePlaybook:
    """Racine `BasePlaybook`. `ability_id` = l'AbilityType (clé du registry). `priority` = le tier de
    préférence (`get_Priority`, interface slot 0 ; défaut 0 = `AbilityPriority.Normal`, surchargé par
    22 playbooks — cf. `engine.playbook.noncomparable.NATIVE_PRIORITY`). Les sous-classes concrètes
    (Comparable/NonComparable) définissent l'énumération + le scoring."""

    ability_id: int = -1
    priority: int = 0                     # tier de préférence (0 = AbilityPriority.Normal)


# ── Terme de tuile Tile(7) partagé (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction`) ────────────────
def tile_utility(ctx, pos) -> float:
    """Composite Tile(7) évalué sur la tuile caster `pos` — MÊME Composed que le sweep MOVE (case-49 :
    le natif émet `ComposedUtility` identique sous le playbook d'ATTAQUE, L3 s14 31337 — feuille
    TriggeredAbilities(2) incluse : natif (3,4)=25=30elev-25effets+20trig vs (4,3)=40=30+10trig).
    Meta et leaf_ctx MIRROIR de `engine.move` (élévation min/max BOARD, effets dynamiques + covers
    terrain, kit passif + fpos via `tile_leaf_ctx`). Sur carte plate ≈ 0. Bonus additif."""
    from ..utilities.tile import (terrain_tile_effects, tile_leaf_ctx,   # lazy : évite tout cycle
                                  apply_tile_attributes)
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        _elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(_elevs), "elevation_min": min(_elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    _effs = list(ctx.effects_by_pos.get(pos) or [])          # feuille TileEffects (ex. Thorns=-25)
    # ctx POLYMORPHE : NCContext (NovaShield via get_movement_utility) n'a pas `terrain_by_pos`.
    # covers hebergés (case-37) + repli Loop1 non hydraté ; `_effs` = canal dynamique (#155)
    _effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos), _effs)
    if _effs:
        meta["effects"] = _effs
    leaf_ctx = tile_leaf_ctx(ctx)
    apply_tile_attributes(meta, pos, leaf_ctx)   # isTerritory / effects[].effectType (cf. tile.py)
    return tile_composite(pos, meta, leaf_ctx, ctx.wt)


class _UnitView:
    """Vue de l'`AiDecisionContext` recentrée sur une AUTRE unité que le mover — l'`unit` que porte
    le `UtilityAttackCase` quand ce n'est pas le caster.

    Ce n'est pas une commodité : c'est ce que le natif fait. `IdunBattle.AI.Playbook.Playbooku003C
    __Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace` construit
    `UtilityAttackCase$$Base(target, UnitPosition(tile), tile, aoe)` — le `caster` du case (`+0x10`)
    est **la cible**, pas le lanceur —, et les feuilles Tile(7) recopient ce champ dans
    `UtilityMovementCase+0x10` (`IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor(attackCase)`)
    avant de le passer à `HasTrait(case.unit, …)` / `HasFaction(case.unit, …)` et aux comptes
    d'adjacence. Évaluer `Tile(7)` avec le kit du CASTER serait donc un fork de port, pas une
    approximation.

    Trois champs sont redérivés, le reste est délégué tel quel (les cartes par-position
    — élévation, effets, walkable — ne dépendent pas de l'unité) :

    - `me` / `uid` : l'entrée `ctx.units` de l'unité visée ;
    - `units` : la MÊME liste, mais `ctrl` recalculé **du point de vue de cette unité**
      (`ctrl' = (ctrl == ctrl_de_l_unite)`). `_adjacent_units` classe `friends`/`enemies` sur ce
      booléen, et le natif dérive ses deux ensembles de `GetCurrentPlayer(case.unit)` : pour une
      cible ENNEMIE, amis et ennemis sont donc échangés ;
    - `fpos` / `enemies` : les positions des deux camps, réalignées sur ce même point de vue."""

    __slots__ = ("_ctx", "me", "uid", "units", "fpos", "enemies")

    def __init__(self, ctx, unit: dict):
        self._ctx = ctx
        self.me = unit
        self.uid = unit.get("id")
        mine = bool(unit.get("ctrl"))
        self.units = [dict(u, ctrl=(bool(u.get("ctrl")) == mine))
                      for u in (getattr(ctx, "units", None) or [])]
        self.fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in self.units
                     if u.get("ctrl") and u.get("alive") and u.get("pos")]
        self.enemies = [u for u in self.units if not u.get("ctrl") and u.get("alive")]

    def __getattr__(self, name):
        return getattr(self._ctx, name)


def tile_utility_for_unit(ctx, unit: dict, pos) -> float:
    """`Tile(7)` évalué sur la tuile `pos` POUR l'unité `unit` — `GetUtility(UtilityType.Tile)
    .EvaluateAttack(UtilityAttackCase$$Base(unit, UnitPosition(pos), pos, aoe))`.

    Le mode ATTACK n'est PAS un chemin distinct : chaque feuille de tuile convertit son
    `UtilityAttackCase` en `UtilityMovementCase` et délègue au slot `EvaluateMovementInSteps`
    (corps identiques de `IdunBattle.AI.Utilities.ElevationUtility$$EvaluateAttackInSteps`,
    `…AUnitEffectsUtility$$EvaluateAttackInSteps`, `…CapturePointTileUtility$$EvaluateAttackInSteps`).
    Le facteur de `IdunBattle.AI.Utilities.ComposedUtility$$CalculateAttackModifier` vaut 1 pour ce
    composite : les TROIS seules utilities qui l'overrident (`DislikeBossUtility`,
    `DislikeEnvironmentUnitsUtility`, `DislikeObjectsUtility`) sont des feuilles du composite
    d'ATTAQUE, aucune n'est une feuille de Tile(7). => même somme que `tile_utility`, au point de
    vue d'unité près."""
    return tile_utility(_UnitView(ctx, unit), pos)


class ComparablePlaybook(BasePlaybook):
    """`ComparablePlaybook<T>` — régime somme-pondérée sur prédictions (attaques d'abord). Le playbook
    dispatché par le générateur ; `make_damage_predictions` (le fournisseur de prédiction) est OVERRIDÉ
    par sous-classe (NormalAttack -> PV.normal ; Default/spéciales -> PV.special)."""

    is_normal_attack: bool = False        # tie-break natif : à utilité TOTALE égale, la normale gagne

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`Playbook.MakeDamagePredictions` (vtable +0x358) : liste `[(target_id, event_dict), …]` =
        cible principale + AoE, ou None/[] si NON-attaque. Délègue au port PV (complet/validé)."""
        raise NotImplementedError

    def make_effect_predictions(self, ctx, caster_tile, target, ability_id):
        """`ComparablePlaybook.MakeEffectPredictions` (vtable +0x388) : liste de `ProbableEffectEvent`
        (pose d'effet probable). BASE = VIDE (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeEffectPredictions` = `new List()`) — l'immense majorité des
        abilities n'ajoute PAS d'effet-prédiction. SEUL `SpiritLeechPlaybook IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeEffectPredictions` l'override dans
        ce build (effet Pinned=0x429, poids 0 -> inerte). Override par sous-classe au besoin."""
        return []

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` = `Fix64.FromInt(0)`. Terme d'ACTION
        ajouté PAR-DESSUS `u_full` (pair + Tile) dans l'assemblage du BucketAction — il n'apparaît PAS
        dans le pairUtility (le scorer natif confronté à l'étage UTILITÉ ne le contient pas ; preuve
        L3 #64 : playbook_action u = pair + tile + custom exacts). Overrides natifs : NormalAttack +1
        (common.py) ; quirks per-ability NON portés à ce jour (MortisRound IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility displacement,
        Drachnyen IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility count>=2, HeraldOfTheApocalypse IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility, ProperKilly IdunBattle.AI.Playbook.Loki.ProperKilly_NormalAttackPlaybook$$CalculateCustomUtility...)."""
        return 0.0

    def calculate_utility_from_predictions(self, ctx, caster_tile, target, ability_id,
                                           events) -> tuple:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
        = Σ `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
        (= prob1 × prob2 × composite Damage ; event FRIENDLY -> utilité NÉGÉE) + Σ des events d'EFFET
        (branche +0x388, base vide). Renvoie `(u, bk)`.

        EXTRAIT de `calculate_action_utility` (aucun changement de comportement pour elle) pour être
        consommable par la SECONDE route Comparable (`playbook/nonattack.py`), dont le natif somme
        exactement le même terme : `CalculateActionUtility` fait `u = custom` PUIS
        `u += CalculateUtilityFromPredictions(...)` — le régime « sans prédiction » n'est que le cas
        où `MakeDamagePredictions` rend une liste vide, pas une route où le terme n'existe pas."""
        from .probable_damage_event import (calculate_utility_from_damage_event,
                                            calculate_utility_from_effect_event)
        from ..utilities.tile import triggered_abilities_attack_utility
        u = 0.0
        bk = []
        for ev in (events or []):
            ua = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(ev.target))
            # Feuille TriggeredAbilities(2) face ATTACK (#45-s18, splash Psyker) : évaluée DANS le
            # composite par event (`ForDamagePrediction`) -> même prob × signe que le composite.
            # #438 : le case natif de CET event porte sa `DamagePrediction` (`ForDamagePrediction`,
            # 4e argument) -> on la passe. Sans elle, `BarbedOvipositorPlaybook` lirait un case
            # `HasValue == false` et rendrait 0 en silence.
            trig = triggered_abilities_attack_utility(ctx, ctx.uid, ability_id, ev.target, caster_tile,
                                                      prediction=ev.prediction)
            if trig:
                ua += (-1.0 if ev.friendly else 1.0) * ev.probability * trig
            u += ua
            bk.append((ev.target, round(ua, 1)))
        # Fold EFFET (branche +0x388) : base vide -> no-op pour toute ability sans override (additif).
        for ee in self.make_effect_predictions(ctx, caster_tile, target, ability_id) or []:
            u += calculate_utility_from_effect_event(ee, ctx.wt)
        return u, bk

    def calculate_action_utility(self, ctx, caster_tile, target, ability_id) -> dict | None:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` pour (caster@caster_tile, target) : Σ des events (dégât)
        + Σ effet + `key-0x36(UtilityAttackCase)` + Tile(7)@tuile. Gate `ShouldExecute` = pas de prédiction
        d'attaque -> None (pas d'action). Renvoie `{u, u_full, wwn, pred, aoe, bk}` (u = dégât+effet ;
        u_full = u + key-0x36 + tile ; pred = event principal).

        `key-0x36` = `UtilityType.WireweaveNet_FirstAttack` (**55** sur ce build ; 54 sur `gqfc5mff6c`,
        d'où l'écriture `key-0x36` des docs). Terme PAR (tuile, cible), au même rang que `Tile(7)` — il ne
        figure donc PAS dans le `pairUtility` que l'étage UTILITÉ confronte (preuve L3 #64), d'où sa place
        dans `u_full` et pas dans `u`. Identiquement **0** partout où la cible ne porte pas de filet
        `1111` ARMÉ, donc dans toute bataille sans `eldarRanger`. RE : `engine/utilities/wireweave_net.py`
        (⚠ le conjoint d'adjacence natif est DÉGÉNÉRÉ — il compare la tuile du caster à elle-même)."""
        from ..utilities.wireweave_net import wireweave_net_first_attack_utility
        events = self.make_damage_predictions(ctx, caster_tile, target, ability_id)  # list[ProbableDamageEvent]
        if not events:
            return None
        u, bk = self.calculate_utility_from_predictions(ctx, caster_tile, target, ability_id, events)
        main = events[0]
        wwn = wireweave_net_first_attack_utility(ctx, caster_tile, target)
        return {"u": u, "u_full": u + wwn + tile_utility(ctx, caster_tile), "wwn": wwn,
                "pred": main.composite_fields(), "aoe": events[1:], "bk": bk}


# Registry AbilityType id -> instance de playbook (Comparable ; les NonComparable ont leur propre
# registre dans le package noncomparable/). Port incrémental : les ids absents -> DefaultActiveAbilityPlaybook.
REGISTRY: dict[int, ComparablePlaybook] = {}


def register(pb: ComparablePlaybook) -> ComparablePlaybook:
    REGISTRY[pb.ability_id] = pb
    return pb


def get_playbook(ability_id: int) -> ComparablePlaybook | None:
    return REGISTRY.get(ability_id)
