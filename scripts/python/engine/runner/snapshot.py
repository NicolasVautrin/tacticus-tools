"""État initial (chargé depuis le LIVE) + forme canonique diffable + diff.

Stratégie tranche 0 (cf. docs/rl/runner-engine.md §2.0) : l'état initial du runner
Python est CHARGÉ depuis un snapshot live du runner fraîchement bâti (vérité-terrain) ;
le runner reproduit ensuite l'ÉVOLUTION (operations). Le port complet BC→Initialize
(indépendance totale) est différé.

  • `load_state(decision, observe)` : snapshot live (decisionView + observeBattle) →
    `State` ECS (entités + composants).
  • `snapshot(state)` : `State` → forme canonique comparable (lue depuis les composants).
  • `snapshot_live(decision, observe)` : MÊME forme canonique, calculée DIRECTEMENT
    depuis les RPC (chemin INDÉPENDANT de load_state → cross-check du loader).
  • `diff(a, b)` : liste lisible des divergences entre deux snapshots.

Jointure des ids : `decisionView.units[].id` == `observeBattle.units[].squadId` =
l'**id d'unité** (référencé par les messages/applyAction). ⚠ ≠ `observeBattle.entityId`
(l'id d'entité ECS interne, p.ex. 79 vs squadId 78) : on clé l'ECS Python par l'id
d'UNITÉ (squadId/decisionView.id), pas l'entityId, pour rester aligné aux messages.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .state import State
from .components import (
    UnitComponent, OwnerComponent, PositionComponent, HealthComponent,
    EffectsOwnedComponent, StatsComponent,
)


def _hp_by_id(observe: dict) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
    """hp/hpMax par id d'UNITÉ (squadId == decisionView.id). PAS entityId."""
    out: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for u in (observe.get("units") or []):
        uid = u.get("squadId")
        if uid is not None:
            out[uid] = (u.get("hp"), u.get("hpMax"))
    return out


def _effect_names(u: dict) -> List[str]:
    return sorted(n for n in (e.get("name") for e in (u.get("effects") or [])) if n)


def load_state(decision: dict, observe: dict, snapshot: Optional[dict] = None) -> State:
    """Snapshot live → `State` ECS (entités + composants d'unité).

    `snapshot` (combatSnapshot) optionnel : s'il est fourni, peuple en plus le
    `StatsComponent` (stats RÉSOLUES + arme normale, via `UnitContext`) de chaque unité
    ET `State.effects` (effets STRUCTURÉS matérialisés, `EffectsState`) — le runner peut
    alors calculer la plage de tirage lui-même. Sans `snapshot` : comportement tranche 0
    inchangé (identité/pos/HP/effets-NOMS uniquement)."""
    state = State()
    state.current_player_id = decision.get("currentPlayer")
    hp_by_id = _hp_by_id(observe)
    for u in (decision.get("units") or []):
        uid = u.get("id")
        if uid is None:
            continue
        e = state.add_entity(uid)
        e.add_component(UnitComponent(visual_id=u.get("visualId"), alive=bool(u.get("alive"))))
        e.add_component(OwnerComponent(team=u.get("team")))
        p = u.get("pos") or {}
        if p.get("col") is not None:
            e.add_component(PositionComponent(col=p["col"], row=p["row"]))
        hp, hp_max = hp_by_id.get(uid, (None, None))
        if hp is not None or hp_max is not None:
            e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
        effs = _effect_names(u)
        if effs:
            e.add_component(EffectsOwnedComponent(effects=effs))
    if snapshot is not None:
        _load_stats_and_effects(state, decision, snapshot)
    return state


def _load_stats_and_effects(state: State, decision: dict, snapshot: dict) -> None:
    """Peuple `StatsComponent` (par unité) + `State.effects` (EffectsState matérialisé)
    depuis `combatSnapshot` + `decisionView`. Jointure : `combatSnapshot.entityId` ==
    `decisionView.id` (== id d'unité ECS, cf. en-tête). Mirror de la chaîne validée
    `predict_validate.build_samples` (UnitContext.from_snapshot + EffectsState.seed)."""
    import gameconfig as GC                      # données offline (traits/arme/profil)
    from ..entities import UnitContext, EffectsState

    vis_by_id = {u.get("id"): u.get("visualId") for u in (decision.get("units") or [])}
    mult_by_id: Dict[int, int] = {}
    ablvl_by_id: Dict[int, Optional[int]] = {}
    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        if eid is None:
            continue
        vis = vis_by_id.get(eid)
        su = {**su, "visualId": vis}
        # On construit le ctx MÊME si la prédiction `normalAttack` a erré (cible hors portée au moment
        # de la capture, ex. déploiement) : les STATS (`su["stats"]`) sont valides, et le COMBAT
        # (`AttackDamageOperation.execute`) re-sélectionne arme/hits/perçage depuis **gameconfig** (pas la
        # prédiction snapshot) ⇒ un ctx stat-based suffit. (Avant on SAUTAIT ces unités → un overwatcher
        # ou une cible hors portée à la capture n'avait pas de StatsComponent → vecteur after-move/hit KO.)
        ctx = UnitContext.from_snapshot(su, GC.unit(vis or ""))
        uc = su.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            ctx.ability_variables_multiplier = int(uc["abilityVariablesMultiplier"])
            mult_by_id[eid] = ctx.ability_variables_multiplier
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
            # NIVEAU d'ability ACTIVE = `unitConfig.activeAbilityLevel` (le stat `activeAbilityLevel` du
            # combatSnapshot est None) — indexe minDmg/maxDmg[level] des abilities actives (cf.
            # AActiveAbility.MinMaxDamage / ability_attack_params). Sans ça, niveau=0 → dégât d'ability faux.
            if uc.get("activeAbilityLevel"):
                ctx.active_ability_level = int(uc["activeAbilityLevel"])
        ent = state.get_entity(eid)
        if ent is not None:
            ent.add_component(StatsComponent(ctx=ctx))
    # effets ACTIFS structurés (decisionView.effects), matérialisés + propagés mult/level.
    effects_by_id = {u.get("id"): (u.get("effects") or []) for u in (decision.get("units") or [])}
    state.effects = EffectsState.seed(effects_by_id, mult_by_id, ablvl_by_id)


def snapshot(state: State) -> dict:
    """`State` → forme canonique comparable (lue depuis les composants)."""
    units: Dict[int, dict] = {}
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        ec = e.get_component(EffectsOwnedComponent)
        units[eid] = {
            "visualId": uc.visual_id if uc else None,
            "alive": uc.alive if uc else None,
            "team": oc.team if oc else None,
            "pos": [pc.col, pc.row] if pc else None,
            "hp": hc.hp if hc else None,
            "hpMax": hc.hp_max if hc else None,
            "effects": list(ec.effects) if ec else [],
        }
    return {"currentPlayer": state.current_player_id, "units": units}


def snapshot_live(decision: dict, observe: dict) -> dict:
    """MÊME forme canonique, DIRECTEMENT depuis les RPC (chemin indépendant)."""
    hp_by_id = _hp_by_id(observe)
    units: Dict[int, dict] = {}
    for u in (decision.get("units") or []):
        uid = u.get("id")
        if uid is None:
            continue
        p = u.get("pos") or {}
        hp, hp_max = hp_by_id.get(uid, (None, None))
        units[uid] = {
            "visualId": u.get("visualId"),
            "alive": bool(u.get("alive")),
            "team": u.get("team"),
            "pos": [p["col"], p["row"]] if p.get("col") is not None else None,
            "hp": hp,
            "hpMax": hp_max,
            "effects": _effect_names(u),
        }
    return {"currentPlayer": decision.get("currentPlayer"), "units": units}


def diff(a: dict, b: dict) -> List[str]:
    """Divergences lisibles entre deux snapshots (a = attendu/live, b = obtenu/Python)."""
    out: List[str] = []
    if a.get("currentPlayer") != b.get("currentPlayer"):
        out.append(f"currentPlayer: {a.get('currentPlayer')} != {b.get('currentPlayer')}")
    ua, ub = a.get("units") or {}, b.get("units") or {}
    for uid in sorted(set(ua) | set(ub)):
        ca, cb = ua.get(uid), ub.get(uid)
        if ca is None:
            out.append(f"u{uid}: absente à gauche"); continue
        if cb is None:
            out.append(f"u{uid}: absente à droite"); continue
        for k in ("visualId", "alive", "team", "pos", "hp", "hpMax", "effects"):
            if ca.get(k) != cb.get(k):
                out.append(f"u{uid}.{k}: {ca.get(k)} != {cb.get(k)}")
    return out
