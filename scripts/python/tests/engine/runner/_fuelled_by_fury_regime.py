"""MONTAGE REUTILISABLE << regime FuelledByFury >> -- la PAIRE DE REGIMES `fury = 0` / `fury = N`
qui separe les DEUX etages de `FuelledByFury_ExtraDamage` (0x52b = 1323).

Pourquoi une paire et pas un scenario : l'effet est un bonus dont la MAGNITUDE depend d'un COMPTEUR.
Deux defauts distincts, tous deux PERMISSIFS (ni erreur ni crash) :
  * compteur non porte  -> le niveau reste celui du seed (0 sur un runner frais) : l'effet est
    present-mais-INERTE, et un test qui ne regarde qu'un seul regime le lit comme un succes ;
  * magnitude non portee -> le niveau monte mais le degat ne bouge pas.
`fury = 0` seul ne teste PAS la magnitude (l'effet est absent de Titus au deploiement) ; `fury = N`
seul ne prouve PAS que le compteur bouge. C'est le LOT qui conclut.

Ce que le montage garantit, et qui est la raison de son existence :
  * GEOMETRIE DRIVEE, jamais subie -- `applyAction move` ne verifie NI la propriete NI la portee : la
    victime est teleportee sur une tuile centrale, Titus et les deux casters allies sur son ring 1,
    le 2e ennemi tenu a l'ecart (sans lui, tuer la victime terminerait la bataille et `decisionView`
    cesserait de rendre les unites) ;
  * ELEVATION EGALE entre le centre et le ring -- le bonus d'elevation
    (`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, +50 %) MULTIPLIE
    le bonus additif et rendrait le delta A/B illisible comme `nrHits x fury x extraDmg` (confond
    MESURE : +2976 au lieu de +1984 = x1.5) ;
  * PIEGE DE HARNAIS GARDE -- `applyAction` peut rendre `ok=True` SANS RIEN MUTER (unite hors
    `toActivate`, ou pas son tour) : chaque pose est RELUE dans l'etat (position effective, niveau
    d'effet effectif, nombre d'evenements) et le montage ABANDONNE si la mutation n'a pas eu lieu ;
  * chaque attaque de Titus est rejouee OFFLINE depuis le snapshot PRE-attaque avec le MEME etat de
    MT (`dumpRng`) -> comparaison BIT-EXACTE par coup, pas une comparaison de moyennes.

Casters allies : `ultraTigurius` (StormOfWrath 1019) et `astraPrimarisPsy` (PsychicMaelstrom 1027) --
deux HEROS (trait `Hero` = le << Character >> de l'i2) a active ENNEMI-ciblee de portee 2, dont les
passifs sont DEFENSIFS (PsychicFortress / Nightshroud) : ils ne touchent pas le degat SORTANT de
Titus, donc le delta A/B reste imputable au seul FuelledByFury.

Sonde de mesure jumelle (memes etages, sortie lisible) : `scripts/python/probe_1323_fuelled_by_fury.py`.
"""
from __future__ import annotations

import json

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.triggers.dispatch.ability import unit_post_ability_triggers

TITUS = "ultraTitus"              # SEUL porteur de `FuelledByFury` (HERO du pool, rank 17)
CASTERS = ("ultraTigurius", "astraPrimarisPsy")
VICTIM = "genesPrimus"            # cible des attaques de Titus (PV gonfles : elle doit survivre)
FILLER = "astraBullgryn"          # 2e ennemi tenu a l'ecart
FURY = "FuelledByFury_ExtraDamage"
FURY_EFFECT_TYPE = 1323
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _upos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


class FuryStage:
    """Le montage vivant + ses deux regimes. `measure()` rend UN dict de mesures (aucun assert)."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board

    # -------------------------------------------------------------- lecture d'etat live
    def dview(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "allAbilities": True}, 180)

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, vis, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == vis), None)

    def fury_level(self, unit_id, dv=None) -> int:
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if int(u.get("id") or -1) != int(unit_id):
                continue
            for e in (u.get("effects") or []):
                if e.get("name") == FURY and not e.get("removed"):
                    return int(e.get("level") or 0)
        return 0

    # -------------------------------------------------------------- pilotage
    def move(self, uid, coord) -> bool:
        """Teleporte et RELIT la position -- `applyAction` peut rendre ok=True sans muter."""
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": int(uid),
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 60)
        u = next((x for x in self.alive() if int(x["id"]) == int(uid)), None)
        return _upos(u) == (int(coord[0]), int(coord[1]))

    def reach_my_turn(self, my_player, max_end=14):
        dv = self.dview()
        for _ in range(max_end):
            if dv.get("currentPlayer") == my_player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 60)
            dv = self.dview()
        return dv if dv.get("currentPlayer") == my_player else None

    # -------------------------------------------------------------- pont live <-> offline
    def capture(self):
        return {"dv": self.dview(),
                "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 60),
                "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 90),
                "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 40)}

    def offline_state(self, cap):
        st = load_state(cap["dv"], cap["ob"], cap["snap"], board=self.board)
        if isinstance(cap["rng"], dict) and cap["rng"].get("mt"):
            st.rng = _seed_rng(cap["rng"])
        return st

    def cast(self, caster_id, target_id, ability_type):
        act = {"kind": "ability", "casterId": int(caster_id), "abilityType": int(ability_type)}
        if target_id is not None:
            act["targetId"] = int(target_id)
        res = self.rpc("applyAction", {"runnerId": self.rid, "action": act}, 120)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        per = {}
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability_type):
                per.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        return {"ok": bool(res.get("ok") and a0.get("ok")), "per": per,
                "n_events": len(a0.get("events") or []), "raw": str(res)[:220]}

    def predicted(self, attacker_id, target_id):
        p = (self.rpc("aiPredict", {"runnerId": self.rid, "unitId": int(attacker_id),
                                    "targetId": int(target_id),
                                    "abilityType": NORMAL_ATTACK}, 90) or {}).get("pred") or {}
        if p.get("totalDmgMin") is None:
            return None
        return (int(p["totalDmgMin"]), int(p["totalDmgMax"]))


def _fury_offline(st, unit_id) -> int:
    eff = getattr(st, "effects", None)
    if eff is None:
        return 0
    lv = 0
    for e in eff.by_unit.get(int(unit_id), []):
        if (not e.consumed) and int(e.effect_type) == FURY_EFFECT_TYPE:
            lv = max(lv, int(e.level or 0))
    return lv


def _fury_params(st, unit_id):
    """DECOMPOSITION PAR ETAGE : `(level, ability_level, multiplier_pct, extraDmg_base, par_stack)`
    lus sur l'effet MATERIALISE offline. None si l'effet est absent (regime fury=0)."""
    from engine.entities.effects.magnitude import ability_var
    eff = getattr(st, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(unit_id), []):
        if e.consumed or int(e.effect_type) != FURY_EFFECT_TYPE:
            continue
        return (int(e.level or 0), e.ability_level, e.ability_variables_multiplier,
                ability_var("FuelledByFury", "extraDmg", e.ability_level, multiplier_pct=100),
                ability_var("FuelledByFury", "extraDmg", e.ability_level,
                            multiplier_pct=e.ability_variables_multiplier))
    return None


def _replay_normal_attack(stage, attacker_id, target_id):
    """Rejoue LA MEME attaque normale live puis OFFLINE (MT cale) -- profils de coups comparables."""
    cap = stage.capture()
    fury_before = stage.fury_level(attacker_id, cap["dv"])
    st = stage.offline_state(cap)
    params = _fury_params(st, attacker_id)
    live = stage.cast(attacker_id, target_id, NORMAL_ATTACK)
    if not live["ok"]:
        return {"ok": False, "reason": "attaque live refusee: %s" % live["raw"]}
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(int(attacker_id), int(target_id)))
    rr = runner.damage_handler.last or {}
    return {"ok": True, "fury": fury_before, "params": params,
            "live_ph": live["per"].get(int(target_id)) or [],
            "off_ph": rr.get("per_hit"),
            # `On(0xe)` est emis AUSSI par l'attaque normale (`ability_type = 1013`) :
            # `IsActiveAbilityCountedAsUsed` DOIT la refuser -> le compteur ne bouge pas.
            "fury_after_live": stage.fury_level(attacker_id),
            "fury_after_off": _fury_offline(st, attacker_id)}


def _accumulate_step(stage, titus_id, caster_id, ability_type, target_id):
    """UN cast allie : niveau LIVE avant/apres + le MEME vecteur `On(0xe)` rejoue OFFLINE."""
    cap = stage.capture()
    before = stage.fury_level(titus_id, cap["dv"])
    st = stage.offline_state(cap)
    live = stage.cast(caster_id, target_id, ability_type)
    after_live = stage.fury_level(titus_id)
    unit_post_ability_triggers(st, int(caster_id), (int(target_id) if target_id else None),
                               ranged=False, profile=None, ability_type=int(ability_type))
    return {"ok": live["ok"], "caster": caster_id, "ability": ability_type,
            "before": before, "after_live": after_live, "after_off": _fury_offline(st, titus_id),
            "n_events": live["n_events"], "raw": live["raw"]}


def build_stage(build_runner, rpc, seed="777", board_name="MC1_67"):
    """Monte la bataille, DRIVE la geometrie, joue les deux regimes et rend le dict de mesures."""
    rid = build_runner(seed, board=board_name, extra=[
        "--rank", "17",
        "--p-units", "%s,%s,%s" % (TITUS, CASTERS[0], CASTERS[1]),
        "--a-units", "%s,%s" % (VICTIM, FILLER),
        "--hp-target", "60000", "--crit", "0,0", "--block-target", "0,0"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    stage = FuryStage(rpc, rid, board)

    dv = stage.dview()
    titus = stage.by_visual(TITUS, dv)
    victim = stage.by_visual(VICTIM, dv)
    filler = stage.by_visual(FILLER, dv)
    casters = [stage.by_visual(c, dv) for c in CASTERS]
    if not (titus and victim and filler and all(casters)):
        pytest.skip("roster incomplet dans le runner")
    my_player = titus.get("owner")

    import hexgeo

    def _flat_ring(t):
        e = board.elevation(t)
        return [n for n in board.neighbours(t) if board.walkable(n) and board.elevation(n) == e]

    cands = [t for t in sorted(board.by_id) if board.walkable(t) and len(_flat_ring(t)) >= 4]
    if not cands:
        pytest.skip("aucune tuile centrale a >=4 voisins marchables de MEME elevation")
    center_tile = cands[len(cands) // 2]
    center = board.coord(center_tile)
    ring = [board.coord(n) for n in _flat_ring(center_tile)]
    far = next((board.coord(t) for t in cands if hexgeo.distance(board.coord(t), center) >= 4), None)
    if far is None or len(ring) < 3:
        pytest.skip("geometrie insuffisante (ring plat < 3 ou pas d'ecart >= 4)")

    todo = [(filler["id"], far), (victim["id"], center), (titus["id"], ring[0]),
            (casters[0]["id"], ring[1]), (casters[1]["id"], ring[2])]
    for _ in range(3):                       # les 5 unites echangent leurs tuiles -> repasses
        todo = [(uid, co) for uid, co in todo if not stage.move(uid, co)]
        if not todo:
            break
    if todo:
        pytest.skip("placements refuses (no-op silencieux) : %s" % todo)
    if stage.reach_my_turn(my_player) is None:
        pytest.skip("mon tour jamais atteint")

    pred0 = stage.predicted(titus["id"], victim["id"])
    regime_a = _replay_normal_attack(stage, titus["id"], victim["id"])

    steps = []
    for cu in casters:
        act = next((ab for ab in (cu.get("abilities") or []) if ab.get("kind") == "active"), None)
        if act is None:
            continue
        steps.append(_accumulate_step(stage, titus["id"], cu["id"], act["id"], victim["id"]))

    if stage.reach_my_turn(my_player) is None:
        pytest.skip("mon tour (2) jamais atteint")
    predN = stage.predicted(titus["id"], victim["id"])
    regime_b = _replay_normal_attack(stage, titus["id"], victim["id"])

    # --- gate `AreFriends(Owner@0x148, caster@0x160)` : ENNEMI, volet PORT seul ------------------
    # MESURE : le harnais ne sait PAS faire caster une unite ADVERSE -- deux tentatives (cast pilote
    # pendant le tour adverse, avec et sans geometrie drivee) sont revenues `ok=True, events=2, 0
    # degat` = le no-op silencieux d'`applyAction`. Le CONTROLE POSITIF de la meme passe (cast ALLIE,
    # 21 evenements, fury 0 -> 1) prouve que c'est bien le cast ADVERSE qui ne part pas, pas le
    # harnais. Faute de contrepartie live, on garde le volet PORT : le MEME vecteur `On(0xe)` emis
    # avec un caster ENNEMI ne doit RIEN incrementer. C'est une garde de non-regression du gate, pas
    # une confrontation live -- dit tel quel.
    cap_foe = stage.capture()
    lvl_before = stage.fury_level(titus["id"], cap_foe["dv"])
    st_foe = stage.offline_state(cap_foe)
    foe = next((u for u in stage.alive(cap_foe["dv"])
                if u.get("owner") != my_player and u.get("id") != victim["id"]), None)
    foe_act = next((a for a in ((foe or {}).get("abilities") or [])
                    if a.get("kind") == "active"), None)
    foe_off = None
    if foe is not None and foe_act is not None:
        unit_post_ability_triggers(st_foe, int(foe["id"]), int(titus["id"]),
                                   ranged=True, profile=None, ability_type=int(foe_act["id"]))
        foe_off = _fury_offline(st_foe, titus["id"])

    return {"rid": rid, "titus": titus["id"], "victim": victim["id"],
            "pred0": pred0, "predN": predN, "a": regime_a, "b": regime_b, "steps": steps,
            "foe": (None if foe is None else foe["id"]),
            "foe_ability": (None if foe_act is None else foe_act["id"]),
            "foe_level_before": lvl_before, "foe_level_after_off": foe_off,
            "fury_final": stage.fury_level(titus["id"])}
