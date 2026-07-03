"""Base du namespace `IdunBattle.AI.Playbook` — hiérarchie + registry (RE playbook/architecture.md §2.2).

Hiérarchie native : `BasePlaybook -> {ComparablePlaybook<T>, NonComparablePlaybook<T>}`. Un générateur
d'action fait `LoadPlaybook(abilityType) -> playbook.Evaluate(unit, tile)` ; c'est le playbook qui
énumère ses cibles et les score. Deux régimes :

- **Comparable** (`ComparablePlaybook<T>`, attaques/soins) : `EvaluateInternal @181408980` boucle les
  cibles éligibles à position caster FIXÉE, `CalculateActionUtility @181406ee0` par cible
  (`= predictionUtility + Σ CalculateUtilityFromPredictions + [gate ShouldExecute] + Tile(7)`), argmax
  dans un Bucket. `MakeDamagePredictions` (vtable) = le fournisseur de prédiction, OVERRIDÉ par playbook.
- **NonComparable** (`NonComparablePlaybook<T>`) : heuristique entière dans la feuille -> `noncomparable.py`.

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
    préférence (`get_Priority`, interface slot 0 ; défaut 0 = tier final). Les sous-classes concrètes
    (Comparable/NonComparable) définissent l'énumération + le scoring."""

    ability_id: int = -1
    priority: int = 0                     # tier de préférence (0 = défaut/final)


# ── Terme de tuile Tile(7) partagé (`CalculateUtilityFromTilePrediction @181408740`) ────────────────
def tile_utility(ctx, pos) -> float:
    """Composite Tile(7) évalué sur la tuile caster `pos`. Sur carte plate ≈ 0 (feuilles situationnelles
    gatées sur métadata absente) -> ne discrimine que sur élévation / tuiles spéciales. Bonus additif."""
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        _elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(_elevs), "elevation_min": min(_elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    if pos in ctx.effects_by_pos:
        meta["effects"] = ctx.effects_by_pos[pos]   # feuille TileEffects (ex. Thorns=-25)
    return tile_composite(pos, meta, {}, ctx.wt)


class ComparablePlaybook(BasePlaybook):
    """`ComparablePlaybook<T>` — régime somme-pondérée sur prédictions (attaques d'abord). Le playbook
    dispatché par le générateur ; `make_damage_predictions` (le fournisseur de prédiction) est OVERRIDÉ
    par sous-classe (NormalAttack -> PV.normal ; Default/spéciales -> PV.special)."""

    is_normal_attack: bool = False        # tie-break natif : à utilité TOTALE égale, la normale gagne

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`Playbook.MakeDamagePredictions` (vtable +0x358) : liste `[(target_id, event_dict), …]` =
        cible principale + AoE, ou None/[] si NON-attaque. Délègue au port PV (complet/validé)."""
        raise NotImplementedError

    def calculate_action_utility(self, ctx, caster_tile, target, ability_id) -> dict | None:
        """`CalculateActionUtility @181406ee0` pour (caster@caster_tile, target) : Σ des events (dégât)
        + Tile(7)@tuile. Gate `ShouldExecute` = pas de prédiction d'attaque -> None (pas d'action émise).
        Renvoie `{u, u_full, pred, aoe, bk}` (u = dégât seul ; u_full = u + tile ; pred = event principal)."""
        events = self.make_damage_predictions(ctx, caster_tile, target, ability_id)  # list[ProbableDamageEvent]
        if not events:
            return None
        from .probable_damage_event import calculate_utility_from_damage_event
        # `CalculateUtilityFromPredictions @181407890` = Σ `CalculateUtilityFromDamageEvent @1814a9f90`
        # (= prob1 × prob2 × composite Damage ; event FRIENDLY -> utilité NÉGÉE).
        u = 0.0
        bk = []
        for ev in events:
            ua = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(ev.target))
            u += ua
            bk.append((ev.target, round(ua, 1)))
        main = events[0]
        return {"u": u, "u_full": u + tile_utility(ctx, caster_tile),
                "pred": main.composite_fields(), "aoe": events[1:], "bk": bk}


# Registry AbilityType id -> instance de playbook (Comparable ; les NonComparable ont leur propre
# registre dans noncomparable.py). Port incrémental : les ids absents -> DefaultActiveAbilityPlaybook.
REGISTRY: dict[int, ComparablePlaybook] = {}


def register(pb: ComparablePlaybook) -> ComparablePlaybook:
    REGISTRY[pb.ability_id] = pb
    return pb


def get_playbook(ability_id: int) -> ComparablePlaybook | None:
    return REGISTRY.get(ability_id)
