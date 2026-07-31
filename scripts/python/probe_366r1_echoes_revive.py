#!/usr/bin/env python
"""#366-r1 -- `1284 EchoesFromTheWarp_Revive` : la SECONDE instanciation de `GhostEffect`.

QUESTION. `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` porte un FORK
d'`amount` resolu A LA CONSTRUCTION de l'arbre :

    if (effet.source == 0x485 = 1157 TriggeredAbilityType.TimeFlux)
         amount = Direct(GetVariableForLevel(config, 0x1d = 'hp', abilityState))   # 1186, porte #213
    else amount = StatAmount(src, 5 = Health, 3 = StatPart.Initial)                # 1284, CE CAS

⚠ `StatPart 3` est **Initial**, pas Maximum (= 2) : `IdunBattle.Entities.Enum.StatPart` =
`0=Current,1=CurrentPct,2=Maximum,3=Initial,4=Missing,...`, et
`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` le confirme au corps
(`case 3: return *(this+0x10)` = le champ base, vs `case 2: get_CurrentMaximumValue()`). La fiche
case-66 §8.4 ecrivait « max = 3 » : mislabel. Le meme `Initial` est relu par le clamp
`IdunBattle.Core.Services.BattleQuery$$GetMaximumReviveHealth` -> le montant final vaut la PV
INITIALE, exactement le « revives with **Full Health** » de l'i2.

CONFRONTABILITE. L'unique porteur, `thousNpc4Terminator`, est un **npc** : `buildNormalizedBC` le
refuse a TOUS les ranks (`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` ->
`KeyNotFoundException` sur un lookup PAR UNITID qui ne couvre que le bucket `lineup`) et aucun
enrichissement du seed BC ne peut lever ce refus (#228). Ce probe passe donc par la **GREFFE**
(`case-92` §5bis, volet PASSIF) : `catalog_inject.write_grafted_seed_bc` pose l'ability 1219 sur
une unite DU POOL. C'est legitime ici -- ni les traits ni l'arme du caster ne sont lus, et la seule
stat lue (`Health` part `Initial`) est celle du GREFFON, ce qui en fait un DISCRIMINANT : deux bras
a `Health` different doivent rendre deux montants differents.

GREFFON : `thousTerminator` (« Toth »), le plus proche du vrai porteur -- MEME faction
(ThousandSons), MEMES traits `WeaverOfFate` + `TerminatorArmour`. La greffe REMPLACE sa liste de
passives, donc `TimeFlux` (et son ghost 1186, et sa regen) DISPARAIT : aucun confond possible entre
les deux instanciations.

USAGE
    python probe_366r1_echoes_revive.py                 # volet A seul (offline, aucun runner)
    python probe_366r1_echoes_revive.py --live          # + volets B et C (2 bras x 2 boards)
Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
import gameconfig as GC                                                  # noqa: E402
import catalog_inject as CI                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ABILITY = "EchoesFromTheWarp"
ECHOES_EFFECT = 1284
TIME_FLUX_EFFECT = 1186
GRAFT = "thousTerminator"          # greffon : meme faction + memes traits que le vrai porteur
FOE = "astraBullgryn"              # porte le coup fatal
FOE_IDLE = "orksNob"               # 2e adverse qui GARDE son action -> pas de bascule de tour
                                   # parasite apres le revive (piege de mesure de #213)
BOARDS = ("MC1_67", "C4_09")
SEED = 31337
DMG_TARGET = 99999                 # le coup adverse est LETAL a coup sur
# Les deux regimes de PV du greffon. `Health` du BC alimente `FillUpStatComponent$$Initialize`
# (initial = max = courant), donc c'est EXACTEMENT le `StatPart.Initial` que lit le fork.
HP_ARMS = (9000, 15000)
STATE = str(ROOT / "logs" / "probe_366r1_echoes.json")
GRAFTED_BC = str(ROOT / "logs" / "probe_366r1_grafted_bc.json")


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


# ============================================================ VOLET A -- offline, re-derive tout

def volet_a() -> dict:
    """Ventilation des porteurs + fermeture du domaine. Ne recopie AUCUN chiffre : tout est
    re-derive du gameconfig et de `classes.tsv`/`enums.tsv` du build courant."""
    idx = GC._index()
    carriers = []
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            names = list(u.get("passiveAbilities") or []) + list(u.get("activeAbilities") or [])
            if any(ABILITY in n for n in names):
                carriers.append({"id": uid, "bucket": bucket,
                                 "faction": u.get("FactionId") or u.get("faction") or "",
                                 "traits": u.get("traits")})
    print("== A1. porteurs gameconfig de %s ==" % ABILITY)
    for c in carriers:
        print("  %-22s bucket=%-8s faction=%-14s traits=%s"
              % (c["id"], c["bucket"], c["faction"], c["traits"]))
    if not carriers:
        print("  (aucun)")

    # Le graphe SUMMON : personne ne spawne le porteur -> la porte SUMMON est fermee elle aussi.
    print("== A2. graphe summon ==")
    for c in carriers:
        s = [aid for aid, a in idx["abilities"].items() if c["id"] in json.dumps(a)]
        print("  %-22s summoners=%s" % (c["id"], s if s else "AUCUN -> porte SUMMON FERMEE"))

    # Fermeture du domaine : sous-classes et effectTypes, lus dans la table de symboles VERSIONNEE.
    build = (ROOT / "data" / "symbols").glob("*/frida/classes.tsv")
    subs_ability, subs_effect = [], []
    for p in build:
        for line in p.read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            if len(f) < 3:
                continue
            if f[2].endswith(".GhostReviveAbility"):
                subs_ability.append(f[0].rsplit(".", 1)[-1])
            if f[2].endswith(".GhostEffect"):
                subs_effect.append(f[0].rsplit(".", 1)[-1])
    print("== A3. fermeture du domaine (classes.tsv, tous builds presents) ==")
    print("  sous-classes de GhostReviveAbility : %s" % sorted(set(subs_ability)))
    print("  sous-classes de GhostEffect        : %s"
          % (sorted(set(subs_effect)) or "AUCUNE (une seule classe)"))

    cfg = GC._index()["abilities"].get(ABILITY) or {}
    print("== A4. config gameconfig de %s ==" % ABILITY)
    print("  variables=%s constants=%s" % (list((cfg.get("variables") or {}).keys()),
                                           list((cfg.get("constants") or {}).keys())))
    print("  -> AUCUNE variable : coherent avec la branche StatAmount (qui ne lit pas la config)")
    return {"carriers": carriers, "subs_ability": sorted(set(subs_ability)),
            "subs_effect": sorted(set(subs_effect))}


# ============================================================ montage LIVE

def build_runner(seed: int, board: str, hp: int, seed_bc: str | None):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--p-units", GRAFT, "--a-units", "%s,%s" % (FOE, FOE_IDLE),
           "--dmg-target", str(DMG_TARGET), "--no-ai", "--board", board,
           "--unit-stat", "%s:Health=%d,RemainingHealth=%d,Armor=0,FixedArmor=0" % (GRAFT, hp, hp),
           "--state-file", STATE]
    if seed_bc:
        cmd += ["--seed-bc", seed_bc]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write((p.stdout or "")[-1200:])
        sys.stdout.write((p.stderr or "")[-1600:])
        raise SystemExit("build KO (board=%s hp=%d)" % (board, hp))
    return json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]


def view(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    out = {}
    for o in (ob.get("units") or []):
        out[o.get("visualId")] = {"id": o.get("id"), "col": o.get("col"), "row": o.get("row"),
                                  "hp": o.get("hp"), "hpMax": o.get("hpMax"),
                                  "isDead": o.get("isDead")}
    for u in (dv.get("units") or []):
        vid = u.get("visualId")
        p = u.get("pos") or {}
        cur = out.setdefault(vid, {})
        cur["id"] = u.get("id", cur.get("id"))
        if p.get("col") is not None:
            cur["col"], cur["row"] = p.get("col"), p.get("row")
        cur["hasAction"] = u.get("hasAction")
    return dv, out


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def ghost_tiles(sid, rid, effect_type):
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    return [(t.get("col"), t.get("row")) for t in (rows or [])
            for e in (t.get("effects") or [])
            if int(e.get("effectType") or -1) == int(effect_type)]


def normal_attack_id(dv, caster_id, target_id):
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == target_id:
                    return ev.get("abilityId")
    return None


def step_towards(sid, rid, uid, goal):
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    tiles.sort(key=lambda t: hexgeo.distance(t, goal))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": tiles[0][0], "row": tiles[0][1]}})
    return tiles[0]


def approach(sid, rid):
    """DRIVE la geometrie : l'ennemi au CONTACT du greffon (les deux camps sont pilotables)."""
    for _ in range(12):
        _, uu = view(sid, rid)
        if GRAFT not in uu or FOE not in uu:
            return uu
        hpos = (uu[GRAFT]["col"], uu[GRAFT]["row"])
        fpos = (uu[FOE]["col"], uu[FOE]["row"])
        if hexgeo.distance(fpos, hpos) <= 1:
            return uu
        step_towards(sid, rid, uu[GRAFT]["id"], fpos)
        act(sid, rid, {"kind": "endturn"})
        _, uu = view(sid, rid)
        step_towards(sid, rid, uu[FOE]["id"], (uu[GRAFT]["col"], uu[GRAFT]["row"]))
        act(sid, rid, {"kind": "endturn"})
    _, uu = view(sid, rid)
    return uu


def wait_for_action(sid, rid, who):
    for _ in range(6):
        dv, uu = view(sid, rid)
        if uu.get(who, {}).get("hasAction"):
            return dv, uu
        act(sid, rid, {"kind": "endturn"})
    return view(sid, rid)


# ============================================================ VOLET B -- non-regression du canal

def volet_b(sid, rid) -> dict:
    """Le canal MESURE (`unitAbilityStates`, hierarchie 2) doit rendre, sur un runner NON greffe,
    EXACTEMENT ce que le gameconfig declare. Sans ce controle, substituer la mesure au gameconfig
    dans `collect_triggered_abilities` serait un changement AVEUGLE."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    st = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90)
    # ⚠ `observeBattle.units[]` porte `entityId`/`squadId`, PAS `id` : un mapping sur `id` rend
    # `{None: ...}` et le volet mesure **0 unite**, ce qui se lit a tort comme « 0 ecart ». C'est
    # `decisionView.units[].id` qui est l'id d'entite du port (celui de `state.get_entity`).
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    vis = {u.get("id"): u.get("visualId") for u in (dv.get("units") or [])}
    rows, bad = [], 0
    for su in (st.get("units") or []):
        vid = vis.get(su.get("entityId"))
        if not vid:
            continue
        measured = []
        for t in (su.get("triggered") or []):
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == 2:
                try:
                    measured.append(TriggeredAbilityType(int(raw[0])).name)
                except ValueError:
                    measured.append("id:%s" % raw[0])
        declared = list((GC.unit(vid) or {}).get("passiveAbilities") or [])
        ok = sorted(measured) == sorted(declared)
        bad += 0 if ok else 1
        rows.append((vid, measured, declared, ok))
    print("== B. canal passives MESURE vs gameconfig (runner NON greffe) ==")
    for vid, m, d, ok in rows:
        print("  %-22s mesure=%-30s gameconfig=%-30s %s"
              % (vid, m, d, "OK" if ok else "*** ECART ***"))
    print("  -> %d unite(s), %d ecart(s)" % (len(rows), bad))
    if not rows:
        # Un balayage a ZERO n'est PAS une mesure : sans ce garde-fou, un mapping casse se lit
        # exactement comme « aucun ecart » (c'est arrive ici, cf. le commentaire sur `entityId`).
        print("  *** AUCUNE unite mesuree : le canal ou le mapping est casse, PAS un succes ***")
        return {"rows": 0, "mismatch": 1}
    return {"rows": len(rows), "mismatch": bad}


# ============================================================ VOLET C -- la greffe, live vs port

def run_live(sid, rid, effect_type):
    """Le greffon demarre son tour en A, bouge en B (!= A), y meurt -> il doit revenir en A."""
    _, uu = view(sid, rid)
    for k in (GRAFT, FOE):
        if k not in uu:
            return {"error": "unite %s absente" % k}
    approach(sid, rid)
    dv, uu = wait_for_action(sid, rid, GRAFT)
    if not uu.get(GRAFT, {}).get("hasAction"):
        return {"error": "greffon sans action apres 6 endturn"}
    hid, fid = uu[GRAFT]["id"], uu[FOE]["id"]
    A = (uu[GRAFT]["col"], uu[GRAFT]["row"])
    fpos = (uu[FOE]["col"], uu[FOE]["row"])
    ghosts_before = ghost_tiles(sid, rid, effect_type)
    cand = [t for t in movable(sid, rid, hid) if t != A and hexgeo.distance(t, fpos) <= 1]
    if not cand:
        return {"error": "aucune tuile B (!= A, adjacente a l'ennemi) atteignable"}
    cand.sort(key=lambda t: -hexgeo.distance(t, A))
    B = cand[0]
    act(sid, rid, {"kind": "move", "unitId": hid, "to": {"col": B[0], "row": B[1]}})
    _, uu = view(sid, rid)
    B = (uu[GRAFT]["col"], uu[GRAFT]["row"])
    ghosts_after = ghost_tiles(sid, rid, effect_type)
    act(sid, rid, {"kind": "endturn"})
    dv, uu = view(sid, rid)
    nid = normal_attack_id(dv, fid, hid)
    if nid is None:
        return {"error": "pas de plan d'attaque ennemi vers le greffon"}
    hp0 = int(uu[GRAFT]["hp"])
    act(sid, rid, {"kind": "ability", "casterId": fid, "targetId": hid, "abilityType": nid})
    _, uu2 = view(sid, rid)
    h = uu2[GRAFT]
    return {"A": A, "B": B, "pos_after_death": (h["col"], h["row"]),
            "hp_before": hp0, "hp_after": h.get("hp"), "hp_max": h.get("hpMax"),
            "isDead": h.get("isDead"),
            "ghosts_before_move": ghosts_before, "ghosts_after_move": ghosts_after,
            "ghosts_after_death": ghost_tiles(sid, rid, effect_type)}


def run_port(sid, rid, effect_type):
    """MEME scenario, rejoue par le PORT sur l'etat LIVE-capte AVANT le move."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.components import UnitComponent, HealthComponent, PositionComponent
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.operations.triggers import after_move_triggers
    from engine.runner.events import EventBus
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import OwnerComponent

    def _rpc2(method, body=None, timeout=90):
        return rpc(sid, method, dict(body or {}), timeout)

    prev = bind_live_rpc(_rpc2)
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dec = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
        st = load_state(dec, ob, snap, board=board, tiles=tm)
    finally:
        bind_live_rpc(prev)
    st.rng = IntBasedMersenneTwister(12345)
    td = next((u for u in (dec.get("units") or []) if u.get("visualId") == GRAFT), None)
    if td is None or st.get_entity(td.get("id")) is None:
        return {"error": "greffon absent de l'etat capture"}
    uid = int(td["id"])
    sc = st.get_entity(uid)
    print("  [port] ability_states_seed = %s" % (st.ability_states_seed,))
    from engine.runner.components import StatsComponent
    ctx = sc.get_component(StatsComponent).ctx
    print("  [port] passive_abilities MESUREES = %s" % (ctx.passive_abilities,))
    StartTurnOperation.execute(st, sc.get_component(OwnerComponent).player)
    pc = sc.get_component(PositionComponent)
    A = (pc.col, pc.row)
    occupied = {(e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
                for i, e in st.entities.items()
                if e.get_component(PositionComponent) is not None and i != uid}
    B = None
    for n in board.neighbours(board.id_at(*A)):
        if not board.walkable(n):
            continue
        c = board.coord(n)
        if (int(c[0]), int(c[1])) not in occupied:
            B = (int(c[0]), int(c[1]))
            break
    if B is None:
        return {"error": "aucune tuile voisine libre"}
    MoveUnitOperation(uid, B).execute(st, EventBus())
    after_move_triggers(st, uid)
    ghosts_after = sorted(int(t) for t, effs in st.effects.by_unit.items()
                          if int(t) in board.by_id
                          and any((not e.consumed) and e.effect_type == int(effect_type)
                                  for e in effs))
    foe = next((i for i, e in st.entities.items()
                if e.get_component(OwnerComponent) is not None
                and e.get_component(OwnerComponent).team != sc.get_component(OwnerComponent).team
                and e.get_component(UnitComponent) is not None
                and e.get_component(UnitComponent).alive), None)
    hc = sc.get_component(HealthComponent)
    hp0 = int(hc.hp)
    hc.hp = 0
    out = AttackDamageOperation._fire_death_if_killed(st, uid, foe, hp0, 0, sc, damage=hp0) or []
    pc = sc.get_component(PositionComponent)
    return {"A": A, "B": B, "pos_after_death": (pc.col, pc.row),
            "hp_before": hp0, "hp_after": int(hc.hp), "hp_max": int(hc.hp_max),
            "alive": bool(sc.get_component(UnitComponent).alive),
            "ghost_tile_after_move": ghosts_after,
            "ghost_tile_expected": [board.id_at(*A)],
            "kill_cancelled": any("kill_cancelled_by_revive" in r for r in out)}


def volet_c(sid, grafted_bc) -> int:
    bad = 0
    for board in BOARDS:
        for hp in HP_ARMS:
            print("== C. board=%s  Health(Initial)=%d ==" % (board, hp))
            rid = build_runner(SEED, board, hp, grafted_bc)
            try:
                live = run_live(sid, rid, ECHOES_EFFECT)
                print("  LIVE : %s" % json.dumps(live, sort_keys=True))
                if live.get("error"):
                    bad += 1
                    continue
                if live.get("isDead"):
                    print("  *** le greffon est MORT : aucun revive live ***")
                    bad += 1
                elif int(live.get("hp_after") or 0) != hp:
                    print("  *** hp_after live = %s, attendu %d (= Health Initial) ***"
                          % (live.get("hp_after"), hp))
                    bad += 1
                if tuple(live.get("pos_after_death") or ()) != tuple(live.get("A") or ()):
                    print("  *** revive live hors de la tuile du ghost ***")
                    bad += 1
            finally:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
                print("  runner %s dispose" % rid)
            # le PORT rejoue sur un runner NEUF (meme montage) : on ne peut pas rejouer une capture
            # posterieure a la mort.
            rid2 = build_runner(SEED, board, hp, grafted_bc)
            try:
                port = run_port(sid, rid2, ECHOES_EFFECT)
                print("  PORT : %s" % json.dumps(port, sort_keys=True))
                if port.get("error"):
                    bad += 1
                elif not port.get("alive") or int(port.get("hp_after") or 0) != hp:
                    print("  *** port : alive=%s hp=%s, attendu alive=True hp=%d ***"
                          % (port.get("alive"), port.get("hp_after"), hp))
                    bad += 1
                elif port.get("ghost_tile_after_move") != port.get("ghost_tile_expected"):
                    print("  *** port : ghost pose sur %s, attendu %s ***"
                          % (port.get("ghost_tile_after_move"), port.get("ghost_tile_expected")))
                    bad += 1
            finally:
                rpc(sid, "disposeRunner", {"runnerId": rid2}, 60)
                print("  runner %s dispose" % rid2)
    return bad


def main():
    volet_a()
    if "--live" not in sys.argv:
        print("\n(volets B/C non joues : passer --live)")
        return 0
    sid = _resolve_session()
    Path(STATE).parent.mkdir(parents=True, exist_ok=True)
    # B : non-regression du canal, sur un runner NON greffe -- roster ALEATOIRE 5v5 (bien plus
    # discriminant qu'un duo choisi : on veut savoir si la substitution mesure/gameconfig est un
    # no-op sur des kits QUELCONQUES).
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--rank", "17",
           "--roster", "5", "--board", BOARDS[0], "--no-ai", "--state-file", STATE]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write((p.stdout or "")[-1200:])
        sys.stdout.write((p.stderr or "")[-1600:])
        raise SystemExit("build KO (volet B)")
    rid = json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]
    try:
        b = volet_b(sid, rid)
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
    # C : la greffe.
    p, reports = CI.write_grafted_seed_bc(GRAFTED_BC, ["%s:%s" % (GRAFT, ABILITY)])
    print("\n== greffe ecrite : %s ==" % p)
    for r in reports:
        print("  %s" % json.dumps(r, sort_keys=True))
    bad = volet_c(sid, str(p))
    print("\n== VERDICT ==  canal: %d ecart(s) | greffe: %d ecart(s)" % (b["mismatch"], bad))
    return 0 if (b["mismatch"] == 0 and bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
