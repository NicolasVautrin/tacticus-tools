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
    from ..utilities.tile import terrain_tile_effects, tile_leaf_ctx   # lazy : évite tout cycle
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        _elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(_elevs), "elevation_min": min(_elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    _effs = list(ctx.effects_by_pos.get(pos) or [])          # feuille TileEffects (ex. Thorns=-25)
    # ctx POLYMORPHE : NCContext (NovaShield via get_movement_utility) n'a pas `terrain_by_pos`.
    _effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos))  # covers (case-37)
    if _effs:
        meta["effects"] = _effs
    return tile_composite(pos, meta, tile_leaf_ctx(ctx), ctx.wt)


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

    def calculate_action_utility(self, ctx, caster_tile, target, ability_id) -> dict | None:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` pour (caster@caster_tile, target) : Σ des events (dégât)
        + Σ effet + Tile(7)@tuile. Gate `ShouldExecute` = pas de prédiction d'attaque -> None (pas d'action).
        Renvoie `{u, u_full, pred, aoe, bk}` (u = dégât+effet ; u_full = u + tile ; pred = event principal)."""
        events = self.make_damage_predictions(ctx, caster_tile, target, ability_id)  # list[ProbableDamageEvent]
        if not events:
            return None
        from .probable_damage_event import (calculate_utility_from_damage_event,
                                            calculate_utility_from_effect_event)
        # `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` = Σ `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
        # (= prob1 × prob2 × composite Damage ; event FRIENDLY -> utilité NÉGÉE) + Σ des events d'EFFET.
        from ..utilities.tile import triggered_abilities_attack_utility
        u = 0.0
        bk = []
        for ev in events:
            ua = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(ev.target))
            # Feuille TriggeredAbilities(2) face ATTACK (#45-s18, splash Psyker) : évaluée DANS le
            # composite par event (`ForDamagePrediction`) -> même prob × signe que le composite.
            trig = triggered_abilities_attack_utility(ctx, ctx.uid, ability_id, ev.target, caster_tile)
            if trig:
                ua += (-1.0 if ev.friendly else 1.0) * ev.probability * trig
            u += ua
            bk.append((ev.target, round(ua, 1)))
        # Fold EFFET (branche +0x388) : base vide -> no-op pour toute ability sans override (additif).
        for ee in self.make_effect_predictions(ctx, caster_tile, target, ability_id) or []:
            u += calculate_utility_from_effect_event(ee, ctx.wt)
        main = events[0]
        return {"u": u, "u_full": u + tile_utility(ctx, caster_tile),
                "pred": main.composite_fields(), "aoe": events[1:], "bk": bk}


# Registry AbilityType id -> instance de playbook (Comparable ; les NonComparable ont leur propre
# registre dans le package noncomparable/). Port incrémental : les ids absents -> DefaultActiveAbilityPlaybook.
REGISTRY: dict[int, ComparablePlaybook] = {}


def register(pb: ComparablePlaybook) -> ComparablePlaybook:
    REGISTRY[pb.ability_id] = pb
    return pb


def get_playbook(ability_id: int) -> ComparablePlaybook | None:
    return REGISTRY.get(ability_id)
