"""Scene — l'état de bataille live consommé par la prédiction (la COUTURE oracle/moteur, forme objet).

Consolide en UN objet les deux sacs de dicts de l'ancien PV (`predictor` statique cold + `sctx` par-pas) :
tables par-unité (UnitContext, armure, bouclier, mult de rareté, niveau d'ability, faction) + état courant
(hp, position, équipe, effets matérialisés) + métadonnées de tuile (élévation). Les fonctions de prédiction
lisent la Scene (`scene.hp(id)`, `scene.effects(id)`, …) au lieu de deux dicts non typés — modèle objet propre.

`from_predictor_sctx` BRIDGE les dicts existants (le seam RPC `build_predictor`/`step_context`/`refresh_shields`
reste le fournisseur ; ré-logeable dans Scene.from_live plus tard sans changer le calcul)."""
from __future__ import annotations

from dataclasses import dataclass, field

import gameconfig as GC
from engine.entities import UnitContext, EffectsState


@dataclass
class Scene:
    """État live pour la prédiction. Tables par-id + état courant + élévation. Accès via méthodes."""

    ctx_by_id: dict            # {id: UnitContext} (stats/traits/arme normale, cold)
    armor_by_id: dict          # {id: fixedArmor} — DYNAMIQUE (debuffs), refresh par-pas
    shield_by_id: dict         # {id: totalShield} — DYNAMIQUE (accordé/consommé), refresh par-pas
    mult_by_id: dict           # {id: abilityVariablesMultiplier %} (rareté)
    ablvl_by_id: dict          # {id: passiveAbilityLevel}
    vis_by_id: dict            # {id: visualId}
    units: list                # decisionView.units (courant)
    hp_by_id: dict             # {id: hp courant}
    pos_by_id: dict            # {id: (col,row)}
    team_by_id: dict           # {id: team}
    eff_state: object          # EffectsState (effets matérialisés seed)
    hpmax_by_id: dict = field(default_factory=dict)   # {squadId: hpMax} (observeBattle)
    elev_by_pos: dict | None = None                    # {(col,row): elevation} (tileMeta)
    board: object | None = None                        # Board (voisins natifs, adjacence hex) — cf.
    #                                                    # engine.entities.pathfinding.board ; None → evenq

    @classmethod
    def from_predictor_sctx(cls, predictor: dict, sctx: dict, elev_by_pos: dict | None = None,
                            board: object | None = None) -> "Scene":
        """Bridge des dicts de l'ancien PV vers l'objet Scene (mêmes données, forme objet)."""
        return cls(
            ctx_by_id=predictor.get("ctx_by_id") or {}, armor_by_id=predictor.get("armor_by_id") or {},
            shield_by_id=predictor.get("shield_by_id") or {}, mult_by_id=predictor.get("mult_by_id") or {},
            ablvl_by_id=predictor.get("ablvl_by_id") or {}, vis_by_id=predictor.get("vis_by_id") or {},
            units=sctx.get("units") or [], hp_by_id=sctx.get("hp_by_id") or {},
            pos_by_id=sctx.get("pos_by_id") or {}, team_by_id=sctx.get("team_by_id") or {},
            eff_state=sctx.get("eff_state"), hpmax_by_id=sctx.get("hpmax_by_id") or {},
            elev_by_pos=elev_by_pos if elev_by_pos is not None else predictor.get("elev_by_pos"),
            board=board if board is not None else predictor.get("board"))

    # ── Accesseurs (mirror des lectures dict de PV) ────────────────────────────────────────────────
    def ctx(self, uid):
        return self.ctx_by_id.get(uid)

    def hp(self, uid):
        return self.hp_by_id.get(uid)

    def pos(self, uid):
        return self.pos_by_id.get(uid)

    def team(self, uid):
        return self.team_by_id.get(uid)

    def armor(self, uid) -> int:
        return self.armor_by_id.get(uid, 0)

    def shield(self, uid) -> int:
        return self.shield_by_id.get(uid, 0)

    def mult(self, uid) -> int:
        return self.mult_by_id.get(uid, 100)

    def hpmax(self, uid):
        return self.hpmax_by_id.get(uid)

    def effects(self, uid) -> list:
        """Effets ACTIFS de l'unité (matérialisés, gate HP courant) — `EffectsState.active_effects`."""
        return self.eff_state.active_effects(uid, {"hp": self.hp_by_id.get(uid)})

    def faction(self, uid):
        c = self.ctx_by_id.get(uid)
        return c.faction if c is not None else None


# ── SEAM live-feed (RPC) — tables cold + état par-pas. `rpc(method, body, timeout) -> result dict`. ──
def build_predictor(rpc, rid):
    """Tables STATIQUES (cold, 1×/runner) : `combatSnapshot` (dégât d'arme + stats + unitConfig
    mult/level + boucliers) + `decisionView` (visualId). None si combatSnapshot KO. (Ex-`PV.build_predictor`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return None
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    vis_by_id = {u["id"]: u.get("visualId") for u in (dv0.get("units") or [])}
    ctx_by_id, armor_by_id, mult_by_id, ablvl_by_id, shield_by_id = {}, {}, {}, {}, {}
    for u in (snap.get("units") or []):
        eid = u["entityId"]
        u["visualId"] = vis_by_id.get(eid)
        armor_by_id[eid] = int((u.get("stats") or {}).get("fixedArmor") or 0)
        shield_by_id[eid] = sum(int(s.get("amount") or 0)
                                for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        uc = u.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            mult_by_id[eid] = int(uc["abilityVariablesMultiplier"])
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
        if not (u.get("normalAttack") or {}).get("error"):
            ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_by_id.get(eid) or ""),
                                                       snap.get("statTypes"))
    return {"ctx_by_id": ctx_by_id, "armor_by_id": armor_by_id, "shield_by_id": shield_by_id,
            "mult_by_id": mult_by_id, "ablvl_by_id": ablvl_by_id, "vis_by_id": vis_by_id,
            "elev_by_pos": build_elev_by_pos(rpc, rid)}


def build_elev_by_pos(rpc, rid):
    """`elev_by_pos` {(col,row): elevation} depuis le RPC `boardGraph` (graphe STATIQUE, 1x/runner).
    Alimente la couche ELEVATION de la prediction (`CalculateElevationBonusModifier @181003ea0`, cf.
    `_add_positional_and_defender_mods` : +ElevationBonus si la tuile attaquant > tuile cible). None si
    `boardGraph` KO -> l'elevation redevient no-op (pas de crash ; ancien comportement)."""
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
    except Exception:
        return None
    tiles = (bg or {}).get("tiles") if isinstance(bg, dict) else None
    if not tiles:
        return None
    out = {}
    for t in tiles:
        c, r = t.get("col"), t.get("row")
        if c is not None and r is not None:
            out[(c, r)] = int(t.get("elevation") or 0)
    return out or None


def refresh_shields(predictor, rpc, rid):
    """Rafraîchit l'état DYNAMIQUE (boucliers accordés/consommés + armure débuffée) depuis un
    `combatSnapshot` FRAIS — appeler 1×/pas comparé. (Ex-`PV.refresh_shields`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return
    predictor["shield_by_id"] = {
        u["entityId"]: sum(int(s.get("amount") or 0)
                           for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        for u in (snap.get("units") or [])}
    predictor["armor_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("fixedArmor") or 0)
        for u in (snap.get("units") or [])}


def step_context(predictor, dv):
    """État COURANT du pas (hp/pos/team + effets matérialisés seed) — reconstruit à chaque pas car
    l'état mute. (Ex-`PV.step_context`.)"""
    units = dv.get("units") or []
    return {
        "units": units,
        "hp_by_id": {u["id"]: u.get("hp") for u in units},
        "pos_by_id": {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")},
        "team_by_id": {u["id"]: u.get("team") for u in units},
        "eff_state": EffectsState.seed(
            {u["id"]: (u.get("effects") or []) for u in units},
            predictor["mult_by_id"], predictor["ablvl_by_id"]),
    }
