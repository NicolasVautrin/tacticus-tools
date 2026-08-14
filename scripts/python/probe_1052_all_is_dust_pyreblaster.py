"""#1052 -- MESURE live des deux passifs portes : `AllIsDust` (effet 1189) et `Pyreblaster` (1098).

CE QU'IL MESURE, ET POURQUOI CES DEUX MONTAGES-LA
================================================================================================
Les DEUX porteurs sont des **npc** (`thousNpc3RubricMarine`, `templNpc3InitiatePyreblaster`) : ils
arrivent en bataille par le CHEMIN DE STATS EXPLICITE (`--explicit-stats <id>:<palier>`, case-92
Sec.5bis recours 4), donc avec LEURS stats, LEURS traits et LEURS armes -- c'est le mirror du
porteur, pas une greffe. Leurs jumeaux SUMMON portent le meme `visualId` et le meme kit.

* **AllIsDust** -- volet DEGAT PUR. On attaque le Rubric Marine avec une arme dont le percage de
  profil est <= `pierceRatio` (35) et on compare le degat PAR COUP live vs port. La CONTRE-EPREUVE
  est une MUTATION du port : on retire `AllIsDustEffect` du registre `EFFECT_CLASSES` et on rejoue
  le MEME etat -- si le degat ne bouge pas, l'effet ne mordait pas et le vert ne prouvait rien.

* **Pyreblaster** -- volet TRIGGER. On place le porteur, sa cible et une TROISIEME unite ALIGNEE
  derriere la cible, on fait tirer le porteur, et on compare (a) l'attaque `Flame` supplementaire
  sur l'unite de derriere, (b) les tuiles passees en `Fire`. Le port est rejoue sur la capture
  PRE-attaque par le VECTEUR NATIF (`evaluate_abilities_for_event(AttackInAtomicGroup)`), pas par
  un appel direct a `execute_behaviour` -- meme discipline que `probe_1003_reliques_death_guard`.

GEOMETRIE : la tuile « derriere » vient de `battle_query.get_tiles_behind_filled`, jamais d'une
constante. Le montage la CALCULE depuis le `boardGraph` LIVE et place la 3e unite dessus.

USAGE
    python probe_1052_all_is_dust_pyreblaster.py --volet allisdust
    python probe_1052_all_is_dust_pyreblaster.py --volet pyreblaster
Sorties ASCII (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rl_collect_batch import _rpc, _resolve_session          # noqa: E402

SEED = "777"
BOARD = "MC1_67"
#: PALIER 45 = `units.npc[].stats[44]` = le DERNIER (`FixedArmor` 5740, `Health` 12988).
#: ⚠ CE CHOIX EST LA CONDITION D'OBSERVABILITE D'`AllIsDust`, pas une preference : le percage est un
#: PLANCHER (`GetDamageWithPiercing` = `max(base - armure, base x percage%)`), donc il ne DECIDE du
#: degat que si `armure >= base`. Au palier 3 l'armure vaut **37** face a une base de ~1600 : les
#: deux regimes (percage 20 et percage 1) rendent alors le MEME degat, et le vert obtenu ne dit
#: rien -- mesure faite, `port_avec == port_sans` avec pourtant `extra = -19` applique.
RUBRIC = "thousNpc3RubricMarine:45"
RUBRIC_VIS = "thousNpc3RubricMarine"
PYRE = "templNpc3InitiatePyreblaster:45"
PYRE_VIS = "templNpc3InitiatePyreblaster"
FIRE = 5                                   # `EffectType.Fire`

#: Attaquants du volet AllIsDust -- TROIS regimes, choisis sur le PERCAGE DE PROFIL de leur arme
#: (LU au gameconfig, `damageProfiles[<profil>].PiercingRatio`), et tous les trois a UNE SEULE arme
#: pour que le profil de l'attaque normale soit sans ambiguite :
#:   * `adeptHospitaller` Bolter **20** -- SOUS le seuil : l'effet MORD, et le montant est non nul ;
#:   * `necroSpyder`      Particle **35** -- EXACTEMENT le seuil : `NOT AmountIsGreater(35, 35)` est
#:     VRAI (comparateur STRICT), donc l'effet mord ENCORE -- le cas discriminant du `<=` ;
#:   * `orksNob`          Physical **1** -- SOUS le seuil mais montant `-(1-1) = 0` : regime
#:     DEGENERE, l'effet est un no-op EXACT. Il ne prouve rien seul, et c'est pour ca qu'il est
#:     nomme : un vert obtenu la-dessus serait un accord en regime degenere.
ATT_MELEE = "adeptHospitaller"
#: Temoin du volet Pyreblaster : deux unites, la CIBLE du tir et celle de DERRIERE.
#: L'unite de derriere ne doit porter AUCUNE aura qui change le nombre de coups RECUS par sa
#: voisine. MESURE : `astraBullgryn` porte le trait `BigTarget` (i2 : « Adjacent friendly units
#: receive -1 hit from ranged attacks »), et le PORT l'appliquait (3 coups -> 2) la ou le NATIF en
#: faisait 3 -- le flux `state.rng` divergeait donc AVANT le passif, et l'ecart mesure ensuite sur
#: Pyreblaster n'accusait pas Pyreblaster. C'est un ecart PRE-EXISTANT du canal COUPS, hors de
#: cette tranche ; il est nomme ici pour qu'on ne le re-decouvre pas comme un bug de #1052.
PYRE_CIBLE = "orksNob"
PYRE_DERRIERE = "darkaAsmodai"


def _build(state_file: str, extra: list, build_runner=None) -> dict:
    """`rl_duel build` en sous-processus, `--state-file` ABSOLU et unique (discipline runner.md)."""
    if build_runner is not None:
        # PORTE PYTEST : la fabrique du conftest gere le cap `MAX_RUNNERS` ET la LIBERATION
        # (un runner construit par un test meurt avec lui). Hors pytest on retombe sur le
        # sous-processus `rl_duel build`, qui a la meme discipline `--state-file`.
        return {"rc": 0, "rid": build_runner(SEED, extra=list(extra), board=BOARD)["rid"],
                "stdout": "", "stderr": ""}
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
           "--state-file", state_file, *extra]
    r = subprocess.run(cmd, cwd=str(_HERE), capture_output=True, text=True, timeout=600)
    out = {"rc": r.returncode, "stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:]}
    try:
        out["rid"] = json.loads(Path(state_file).read_text(encoding="utf-8")).get("runnerId")
    except Exception as exc:                                  # noqa: BLE001
        out["rid"] = None
        out["why"] = "state-file illisible : %s" % exc
    return out


def _dispose(sid, rid, build_runner=None):
    if build_runner is not None:
        return          # la fabrique du conftest libere elle-meme (portee du test)
    if rid is not None:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:                                     # noqa: BLE001
            pass


def _board_of(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = (_rpc(sid, "boardGraph", [{"runnerId": rid}], timeout=60) or {}).get("result") or {}
    if not bg.get("tiles"):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _res(sid, method, args, timeout=60):
    return (_rpc(sid, method, [args], timeout=timeout) or {}).get("result") or {}


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return next((u for u in _alive(dv) if u.get("visualId") == vis), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _normal_attack_type(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal" and ab.get("id") is not None:
                    return int(ab["id"])
    return None


def _reach_turn(sid, rid, player, max_end=12):
    dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    for _ in range(max_end):
        if dv.get("currentPlayer") == player:
            return dv
        _res(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    return dv


def _place(sid, rid, uid, coord):
    _res(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid),
        "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)


def _snapshot(sid, rid):
    return {
        "dv": _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120),
        "ob": _res(sid, "observeBattle", {"runnerId": rid}, 60),
        "snap": _res(sid, "combatSnapshot", {"runnerId": rid}, 90),
        "rng": _res(sid, "dumpRng", {"runnerId": rid}, 30),
    }


def _offline_state(s, board):
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    r = s.get("rng") or {}
    if r.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(r["mt"])
        rng.mti = r["mti"]
        st.rng = rng
    return st


def _fire_tiles(sid, rid, board):
    tm = _res(sid, "tileMeta", {"runnerId": rid}, 60)
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == FIRE for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(int(tid))
    return out


def _live_attack(sid, rid, caster_id, target_id, nat):
    act = _res(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(caster_id), "targetId": int(target_id),
        "abilityType": int(nat)}}, 120)
    a0 = (act.get("actions") or [{}])[0]
    per_target = {}
    detail = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Target_Id") is not None:
            per_target.setdefault(int(td["Target_Id"]), []).append(td["Amount"])
            # ATTRIBUTION : sans elle, deux `Amount` sur la meme cible ne disent pas QUI frappe --
            # l'attaque normale, le passif, ou la brulure du trait `OnFire` de l'arme.
            detail.append({k: td.get(k) for k in
                           ("Target_Id", "Amount", "Active_Ability_Type", "Triggered_Ability_Type",
                            "Effect_Type", "Damage_Profile", "Source_Id", "Attacker_Id")
                           if td.get(k) is not None})
    return {"ok": bool(a0.get("ok")), "per_target": per_target, "detail": detail,
            "events": a0.get("events") or []}


# ================================================================================ volet AllIsDust

def volet_all_is_dust(sid, state_file, attaquant: str = ATT_MELEE,
                      build_runner=None) -> dict:
    """Le Rubric Marine encaisse une attaque normale ; on compare le degat PAR COUP live vs port,
    avec et SANS `AllIsDustEffect` au registre (contre-epreuve par MUTATION)."""
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner

    out = {"volet": "allisdust", "attaquant": attaquant, "ok": False}
    # `--a-units` porte le MEME spec a palier que `--explicit-stats` : sans le suffixe `:<n>`, la
    # gate de pool refuse (`hors pool / non spawnables`) AVANT que le chemin de stats explicite
    # entre en jeu -- meme forme que `test_888_mortarion_boss_abilities_live.py`.
    b = _build(state_file, ["--p-units", attaquant, "--a-units", RUBRIC,
                            "--explicit-stats", RUBRIC, "--roster", "1",
                            "--crit", "0,0", "--block-target", "0,0"], build_runner)
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-600:]
        return out
    board = _board_of(sid, rid)
    if board is None:
        out["why"] = "boardGraph indispo"
        _dispose(sid, rid, build_runner)
        return out

    dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    att = _by_vis(dv, attaquant)
    vic = _by_vis(dv, RUBRIC_VIS)
    if att is None or vic is None:
        out["why"] = "unites absentes : %s" % sorted({u.get("visualId") for u in _alive(dv)})
        _dispose(sid, rid, build_runner)
        return out
    out["effets_victime"] = [e.get("name") for e in (vic.get("effects") or [])]

    # DRIVE des positions : l'attaquant au contact de la victime (les deux camps sont pilotables).
    vpos = _pos(vic)
    voisines = [board.coord(t) for t in board.neighbours(board.id_at(*vpos))
                if board.walkable(t) and board.coord(t) != _pos(att)]
    occupees = {_pos(u) for u in _alive(dv)}
    libres = [c for c in voisines if c not in occupees]
    if libres:
        _place(sid, rid, att["id"], libres[0])
    dv = _reach_turn(sid, rid, att.get("owner"))
    att = _by_vis(dv, attaquant)
    vic = _by_vis(dv, RUBRIC_VIS)
    if att is None or vic is None:
        out["why"] = "unite perdue apres placement"
        _dispose(sid, rid, build_runner)
        return out
    out["pos"] = {"att": _pos(att), "vic": _pos(vic)}

    nat = _normal_attack_type(dv, att["id"])
    if nat is None:
        out["why"] = "pas d'attaque normale exposee"
        _dispose(sid, rid, build_runner)
        return out

    s = _snapshot(sid, rid)
    live = _live_attack(sid, rid, att["id"], vic["id"], nat)
    out["live_ok"] = live["ok"]
    out["live_per_hit"] = live["per_target"].get(int(vic["id"]))

    def _port(avec_effet: bool):
        """Rejoue l'attaque OFFLINE sur la capture PRE-coup, avec ou SANS `AllIsDustEffect` au
        registre. Le canal INTERNE (`pierce_pct` et `mods.extra_pierce` reellement passes a
        `apply_pierce_and_modifiers`) est CAPTE : sans lui, deux verts identiques ne diraient pas
        SI l'effet a mordu -- c'est exactement le piege du regime degenere."""
        from engine.entities.effects import factory as F
        from engine.runner.operations import damage_ops
        import engine.services.damage_prediction as DP
        sauve = F.EFFECT_CLASSES.get("AllIsDust")
        vu = []
        orig = DP.apply_pierce_and_modifiers

        def _spy(value, pierce_pct=100, armor=0, mods=None, **kw):
            vu.append({"pierce": int(pierce_pct), "armor": int(armor),
                       "extra": None if mods is None else int(mods.extra_pierce),
                       "value": value})
            return orig(value, pierce_pct, armor, mods, **kw)

        try:
            if not avec_effet:
                F.EFFECT_CLASSES.pop("AllIsDust", None)
            st2 = _offline_state(s, board)          # (re-)seed APRES la mutation du registre
            DP.apply_pierce_and_modifiers = _spy
            for m in (damage_ops.normal, damage_ops.normal_like, damage_ops.ability):
                if hasattr(m, "apply_pierce_and_modifiers"):
                    m.apply_pierce_and_modifiers = _spy
            r = Runner(st2).install_default_handlers(20)
            r.apply(AttackUnitMessage(attacker_id=int(att["id"]), target_id=int(vic["id"])))
            last = r.damage_handler.last or {}
            hc = st2.get_entity(int(vic["id"])).get_component(HealthComponent)
            return {"per_hit": (last.get("attack") or last).get("per_hit") or last.get("per_hit"),
                    "last_cles": sorted(last.keys()), "damage": last.get("damage"),
                    "hp": None if hc is None else hc.hp, "pierce_vu": vu[:4]}
        finally:
            DP.apply_pierce_and_modifiers = orig
            for m in (damage_ops.normal, damage_ops.normal_like, damage_ops.ability):
                if hasattr(m, "apply_pierce_and_modifiers"):
                    m.apply_pierce_and_modifiers = orig
            if sauve is not None:
                F.EFFECT_CLASSES["AllIsDust"] = sauve

    out["port_avec"] = _port(True)
    out["port_sans"] = _port(False)
    out["ok"] = True
    _dispose(sid, rid, build_runner)
    return out


# =============================================================================== volet Pyreblaster

def volet_pyreblaster(sid, state_file, derriere: str = PYRE_DERRIERE,
                      build_runner=None) -> dict:
    """Le porteur tire sur une cible ALIGNEE ; une 3e unite est placee sur la tuile DERRIERE."""
    import engine.battle_query as BQ
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.dispatch.ability import evaluate_abilities_for_event

    out = {"volet": "pyreblaster", "ok": False}
    b = _build(state_file, ["--p-units", PYRE, "--a-units",
                            "%s,%s" % (PYRE_CIBLE, derriere),
                            "--explicit-stats", PYRE, "--roster", "1",
                            "--crit", "0,0", "--block-target", "0,0"], build_runner)
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-600:]
        return out
    board = _board_of(sid, rid)
    if board is None:
        out["why"] = "boardGraph indispo"
        _dispose(sid, rid, build_runner)
        return out

    dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    car = _by_vis(dv, PYRE_VIS)
    cib = _by_vis(dv, PYRE_CIBLE)
    der = _by_vis(dv, derriere)
    if not (car and cib and der):
        out["why"] = "unites absentes : %s" % sorted({u.get("visualId") for u in _alive(dv)})
        _dispose(sid, rid, build_runner)
        return out

    # GEOMETRIE : on choisit une tuile de CASTER, une tuile de CIBLE a distance 2 ALIGNEE, et on
    # DERIVE la tuile derriere par le mirror -- jamais une constante.
    cpos = _pos(car)
    cand = None
    for tid in sorted(board.by_id):
        p = board.coord(tid)
        if not board.walkable(tid) or p == cpos:
            continue
        import hexgeo
        if hexgeo.distance(cpos, p) != 2 or not BQ.is_on_straight_line(cpos, p):
            continue
        behind = BQ.get_tiles_behind_filled(
            cpos, p, tile_exists=lambda q: board.id_at(q[0], q[1]) is not None,
            elevation_at=lambda q: (None if board.id_at(q[0], q[1]) is None
                                    else board.elevation(board.id_at(q[0], q[1]))))
        if len(behind) == 1 and board.walkable(board.id_at(*behind[0])):
            cand = (p, behind[0])
            break
    if cand is None:
        out["why"] = "aucune geometrie alignee distance 2 avec tuile derriere marchable"
        _dispose(sid, rid, build_runner)
        return out
    tpos, bpos = cand
    out["geometrie"] = {"caster": cpos, "cible": tpos, "derriere": bpos}

    _place(sid, rid, cib["id"], tpos)
    _place(sid, rid, der["id"], bpos)
    dv = _reach_turn(sid, rid, car.get("owner"))
    car = _by_vis(dv, PYRE_VIS)
    cib = _by_vis(dv, PYRE_CIBLE)
    der = _by_vis(dv, derriere)
    if not (car and cib and der):
        out["why"] = "unite perdue apres placement"
        _dispose(sid, rid, build_runner)
        return out
    out["pos_reelles"] = {"caster": _pos(car), "cible": _pos(cib), "derriere": _pos(der)}
    if _pos(cib) != tpos or _pos(der) != bpos or _pos(car) != cpos:
        out["why"] = "le placement n'a pas mordu : %s" % out["pos_reelles"]
        _dispose(sid, rid, build_runner)
        return out

    nat = _normal_attack_type(dv, car["id"])
    if nat is None:
        out["why"] = "pas d'attaque normale exposee"
        _dispose(sid, rid, build_runner)
        return out
    out["normal_attack_type"] = nat

    feu_avant = _fire_tiles(sid, rid, board)
    hp_avant = {u["id"]: u.get("hp") for u in _alive(dv)}
    s = _snapshot(sid, rid)

    # --- PORT : L'ATTAQUE NORMALE ENTIERE, rejouee sur la capture PRE-attaque ---------------------
    # On passe par le VRAI point d'entree (`Runner.apply(AttackUnitMessage)`) et NON par un appel
    # direct au vecteur : c'est le seul chemin ou `EvaluateAbilities(0x4a = AttackInAtomicGroup)`
    # est emis AU RANG natif, donc ou les tirages `state.rng` du passif tombent dans la MEME fenetre
    # du flux que live. Un rejeu du seul vecteur part du MT PRE-attaque et ne peut pas etre
    # bit-exact -- il ne prouverait que la topologie.
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.operations.triggers.dispatch import registry as REG

    def _port(avec_passif: bool):
        sauve = REG.ABILITY_TRIGGERS.get("Pyreblaster")
        try:
            if not avec_passif:
                REG.ABILITY_TRIGGERS.pop("Pyreblaster", None)
            st = _offline_state(s, board)

            def _uid(vis):
                for uid, e in st.entities.items():
                    sc = e.get_component(StatsComponent)
                    if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                        return uid
                return None

            u_car, u_cib, u_der = _uid(PYRE_VIS), _uid(PYRE_CIBLE), _uid(derriere)
            _cctx = st.get_entity(u_car).get_component(StatsComponent).ctx
            out.setdefault("caster_ctx", {k: getattr(_cctx, k, None) for k in (
                "normal_profile", "normal_profile_pierce", "normal_hits", "normal_ranged",
                "weapons", "extra_hits", "attack", "passive_ability_level",
                "ability_variables_multiplier")})
            feu0 = {tid for tid, lst in st.effects.by_unit.items()
                    if any(int(getattr(e, "effect_type", -1)) == FIRE for e in (lst or []))}
            hp0 = {}
            for uid in (u_cib, u_der):
                hc = st.get_entity(uid).get_component(HealthComponent) if uid else None
                hp0[uid] = None if hc is None else hc.hp
            r = Runner(st).install_default_handlers(20)
            r.apply(AttackUnitMessage(attacker_id=int(u_car), target_id=int(u_cib)))
            normale = r.damage_handler.last or {}
            trig = [e for e in (r.damage_handler.after_hit or [])
                    if isinstance(e, dict) and e.get("passive") == "Pyreblaster"]
            hp1 = {}
            for uid in (u_cib, u_der):
                hc = st.get_entity(uid).get_component(HealthComponent) if uid else None
                hp1[uid] = None if hc is None else hc.hp
            feu1 = {tid for tid, lst in st.effects.by_unit.items()
                    if any(int(getattr(e, "effect_type", -1)) == FIRE for e in (lst or []))}
            return {"uids": {"caster": u_car, "cible": u_cib, "derriere": u_der},
                    "degat_cible": (None if hp0.get(u_cib) is None
                                    else hp0[u_cib] - hp1[u_cib]),
                    "degat_derriere": (None if hp0.get(u_der) is None
                                       else hp0[u_der] - hp1[u_der]),
                    "normale": {k: normale.get(k) for k in
                                ("per_hit", "base", "clean_min", "clean_max", "pierce", "armor",
                                 "hits", "profile", "rolls", "armor_dmg")},
                    "passif": [{k: (p.get("attack") or {}).get(k) for k in
                                ("per_hit", "base_min", "base_max", "clean_min", "clean_max",
                                 "pierce", "armor", "hits", "rolls")}
                               for e in trig for p in (e.get("behind") or [])],
                    "nouvelles_tuiles_feu": sorted(feu1 - feu0)}
        finally:
            if sauve is not None:
                REG.ABILITY_TRIGGERS["Pyreblaster"] = sauve

    out["port_avec"] = _port(True)
    out["port_sans"] = _port(False)

    # --- NATIF : le tir REEL ---------------------------------------------------------------------
    live = _live_attack(sid, rid, car["id"], cib["id"], nat)
    out["live_ok"] = live["ok"]
    out["live_par_cible"] = {str(k): v for k, v in live["per_target"].items()}
    out["live_detail"] = live.get("detail")
    out["live_ids"] = {"caster": car["id"], "cible": cib["id"], "derriere": der["id"]}
    dv2 = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    hp_apres = {u["id"]: u.get("hp") for u in (dv2.get("units") or [])}
    out["live_degat"] = {
        "cible": (None if hp_avant.get(cib["id"]) is None
                  else hp_avant[cib["id"]] - (hp_apres.get(cib["id"]) or 0)),
        "derriere": (None if hp_avant.get(der["id"]) is None
                     else hp_avant[der["id"]] - (hp_apres.get(der["id"]) or 0))}
    feu_apres = _fire_tiles(sid, rid, board)
    out["natif_nouvelles_tuiles_feu"] = sorted(feu_apres - feu_avant)
    out["tuiles_attendues"] = sorted({board.id_at(*bpos), board.id_at(*tpos)})
    out["ok"] = True
    _dispose(sid, rid, build_runner)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=("allisdust", "pyreblaster", "tous"), default="tous")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--attaquant", default=ATT_MELEE)
    ap.add_argument("--derriere", default=PYRE_DERRIERE)
    a = ap.parse_args()
    sid = _resolve_session()
    base = a.state_file or str(_HERE.parent.parent / "logs" / ("rs_1052_%d.json" % os.getpid()))
    Path(base).parent.mkdir(parents=True, exist_ok=True)
    volets = (["allisdust", "pyreblaster"] if a.volet == "tous" else [a.volet])
    for v in volets:
        sf = base.replace(".json", "_%s.json" % v)
        t0 = time.time()
        r = (volet_all_is_dust(sid, sf, a.attaquant) if v == "allisdust"
             else volet_pyreblaster(sid, sf, a.derriere))
        r["duree_s"] = round(time.time() - t0, 1)
        print(json.dumps(r, ensure_ascii=True, default=str)[:6000])
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
