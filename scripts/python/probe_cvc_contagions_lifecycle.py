"""Probe case-cvc -- le CYCLE DE VIE du debuff d'armure de l'aura `ContagionsOfNurgle` (1071/1072).

CRITERE (binaire) : quand le nombre d'auras Contagion couvrant une unite CHANGE (l'unite entre ou
sort du disque, l'aura GRANDIT avec `TurnsStarted` du porteur, un SECOND porteur la couvre), le natif
change-t-il l'etat ACTIF des instances 1071/1072 qu'elle porte, et son `FixedArmor` suit-il ?
Le port rend-il le MEME couple `(instance active, FixedArmor)` sur la MEME scene ?

ETAGES MESURES (jamais un scalaire fitte) :

  etape 0  OFFLINE  la fenetre `[min, max]` de `CreateActiveCondition` par instance (`CTOR_ARGS`)
                    et sa DISJONCTION : aucun `amount` n'active les deux a la fois.
  etape A  LIVE     la POSE des DEUX instances par
                    `ContagionsOfNurgle_AddEffectInitially_Ability` : le canal
                    `decisionView { includeInactive: true }` publie 1071 ET 1072 sur CHAQUE ennemi
                    du porteur -- y compris hors du disque, ou les deux sont `active: false`.
                    C'est la refutation directe du collapse « une seule instance, l'active ».
  etape B  LIVE     la GEOMETRIE : on promene une victime a distance 1..4 du porteur et on lit
                    (instances actives, FixedArmor) des deux cotes. Le seuil est
                    `GetCurrentRange(porteur)`, comparateur INCLUSIF (`GetInRangeAuraAmount`).
  etape D  LIVE     la BASCULE 1071 <-> 1072 : un SECOND porteur amene au contact de la meme
                    victime -> `amount` passe a 2, 1071 (-20 %) s'eteint, 1072 (-40 %) s'allume.

L'approche se fait par cycles `move` + `endturn` x2 (les deux camps sont pilotables) -- ce qui fait
AUSSI monter `TurnsStarted` du porteur, donc GRANDIR l'aura : le `TurnsStarted` est imprime a chaque
ligne, et la confrontation se fait toujours live-vs-port SUR LA MEME SCENE (meme snapshot), donc ce
confond ne peut pas maquiller un desaccord.

Usage (depuis scripts/python) :
    python probe_cvc_contagions_lifecycle.py --offline-only
    python probe_cvc_contagions_lifecycle.py --board MC1_67 --seed 4242
    python probe_cvc_contagions_lifecycle.py --board C1_02 --seed 777      # 2e geometrie

ASCII only (cp1252). Discipline runner : state-file ABSOLU unique sous logs/, dispose en fin de passe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
STATE = ROOT / "logs" / "probe_cvc_contagions.json"

RED1 = 1071                 # EffectType.ContagionsOfNurgle_ArmorReduction1 (-20 %, exactement 1 aura)
RED2 = 1072                 # EffectType.ContagionsOfNurgle_ArmorReduction2 (-40 %, 2 auras ou plus)
NAME1 = "ContagionsOfNurgle_ArmorReduction1"
NAME2 = "ContagionsOfNurgle_ArmorReduction2"


# --------------------------------------------------------------------------- plomberie RPC

def _sid() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(method: str, arg=None, timeout: int = 90):
    body = json.dumps({"method": method, "args": [arg] if arg is not None else [],
                       "timeout": timeout * 1000}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{_sid()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def build(p_units: str, a_units: str, board: str, seed: str) -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", p_units, "--a-units", a_units, "--no-ai", "--state-file", str(STATE)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        raise SystemExit("build KO: " + (proc.stderr or proc.stdout)[-1200:])
    return json.loads(STATE.read_text())["runnerId"]


def dispose(rid: int):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
    except Exception as exc:                                     # noqa: BLE001
        print("dispose KO:", exc)


def move(rid, uid, col, row):
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}})
    return (r.get("actions") or [{}])[0].get("error")


def endturn(rid):
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


# --------------------------------------------------------------------------- etape 0 (offline)

def offline_guard() -> int:
    from engine.entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect as E
    bad = 0
    e1 = E(name=NAME1, effect_type=RED1, value=-299, source=7)
    e2 = E(name=NAME2, effect_type=RED2, value=-598, source=7)
    if e1.aura_amount_window() != (1, 1):
        print("KO fenetre 1071", e1.aura_amount_window()); bad += 1
    if e2.aura_amount_window() != (2, 0x7FFFFFFF):
        print("KO fenetre 1072", e2.aura_amount_window()); bad += 1
    for n in range(0, 6):
        us = {"contagions_of_nurgle_amount": (lambda _s, k=n: k)}
        a1, a2 = e1.is_active(us), e2.is_active(us)
        want1, want2 = (n == 1), (n >= 2)
        if (a1, a2) != (want1, want2):
            print(f"KO amount={n} -> ({a1},{a2}) attendu ({want1},{want2})"); bad += 1
        if a1 and a2:
            print("KO les DEUX actives a amount=", n); bad += 1
    # Le stat-mod doit rester DECLARATIF (aucune cle de POSE eager), sinon le driver
    # `refresh_stat_modifier_effects` SKIPPE l'instance et le cycle de vie ne s'applique jamais.
    if e1.stat_mod_source is not None:
        print("KO stat_mod_source non nul -> le driver skipperait l'instance"); bad += 1
    if e1.get_stat_modification_stat() != 16:
        print("KO stat", e1.get_stat_modification_stat()); bad += 1
    # Le GATE `active` d'`applied_stat_mods` : une instance INERTE ne declare AUCUNE modification
    # (le natif l'a reverte) -- sinon la passe 2 du seed attribuerait -20 % ET -40 %.
    e_inert = E(name=NAME1, effect_type=RED1, value=-299, source=7, active=False)
    if e_inert.applied_stat_mods(None):
        print("KO instance INERTE declare une modification ->  double-compte au seed"); bad += 1
    if e1.applied_stat_mods(None) != [(16, -299)]:
        print("KO instance ACTIVE ne declare pas sa modification", e1.applied_stat_mods(None))
        bad += 1
    print("etape 0 fenetres:", e1.aura_amount_window(), e2.aura_amount_window(),
          "| (1071,1072) actives par amount 0..5:",
          [(int(e1.is_active({"contagions_of_nurgle_amount": (lambda _s, k=n: k)})),
            int(e2.is_active({"contagions_of_nurgle_amount": (lambda _s, k=n: k)})))
           for n in range(0, 6)])
    print("etape 0:", "OK" if bad == 0 else f"{bad} ECARTS")
    return bad


# --------------------------------------------------------------------------- lecture de scene

def _load(rid, board_tiles):
    """Charge la scene AVEC le canal LARGE (`includeInactive`) : sans lui les instances INERTES
    n'existent pas cote port et la confrontation comparerait deux canaux differents (#219)."""
    from engine.runner.snapshot import load_state, decision_view_seed_body
    from engine.entities.pathfinding.board import Board
    dec_wide = rpc("decisionView", decision_view_seed_body(rid, allAbilities=True))
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec_wide, ob, snap, board=Board(board_tiles, adjacency="evenq"))
    return dec_wide, ob, snap, state


def _live_effects(dec, uid):
    """{effectType: active} des instances Contagion publiees pour `uid` (cle `id` du decisionView)."""
    out = {}
    for u in (dec.get("units") or []):
        if u.get("id") != uid:
            continue
        for e in (u.get("effects") or []):
            if e.get("effectType") in (RED1, RED2):
                out[int(e["effectType"])] = bool(e.get("active", True))
    return out


def _live_fixed_armor(snap, uid):
    """`GetStat(unit, 0x10 = FixedArmor)` natif (`combatSnapshot.units[].stats.fixedArmor`)."""
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return int((u.get("stats") or {}).get("fixedArmor", -1))
    return None


def _port_detail(state, uid):
    """Diagnostic par instance : (effectType, flag `active` seede, source, `is_active`)."""
    from engine.runner.components import unit_state_for_effects
    from engine.entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect
    us = unit_state_for_effects(state, int(uid))
    out = []
    for e in (state.effects.by_unit.get(int(uid), []) if state.effects else []):
        if isinstance(e, ContagionsOfNurgleArmorReductionEffect) and not e.consumed:
            out.append((int(e.effect_type), int(bool(e.active)), e.source,
                        int(bool(e.is_active(us))), e.value))
    return out


def _port_state(state, uid):
    """(instances Contagion presentes -> activite selon `is_active`, FixedArmor du port)."""
    from engine.runner.components import StatsComponent, unit_state_for_effects
    from engine.entities.stats import StatType
    from engine.entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect
    us = unit_state_for_effects(state, int(uid))
    acts = {}
    for e in (state.effects.by_unit.get(int(uid), []) if state.effects else []):
        if isinstance(e, ContagionsOfNurgleArmorReductionEffect) and not e.consumed:
            acts[int(e.effect_type)] = bool(e.active and e.is_active(us))
    ent = state.get_entity(int(uid))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    st = getattr(sc.ctx, "stats", None) if sc is not None else None
    armor = int(st.get_stat(int(StatType.FIXED_ARMOR), 0)) if st is not None else None
    return acts, armor


def _amount(state, uid, source_id):
    from engine.runner.components import contagions_of_nurgle_amount
    return contagions_of_nurgle_amount(state, int(uid), int(source_id))


def _turns_started(state, uid):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    st = getattr(sc.ctx, "stats", None) if sc is not None else None
    return int(st.get_stat(int(StatType.TURNS_STARTED), 0)) if st is not None else None


def _pos_of(ob, uid):
    for u in ob["units"]:
        if u["squadId"] == uid:
            return (u["col"], u["row"])
    return None


def _free_at(tiles, ob, anchor, want, exclude_uid=None):
    """Tuiles marchables LIBRES a distance exacte `want` d'`anchor`."""
    import hexgeo
    occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")
           and u["squadId"] != exclude_uid}
    return [(t["col"], t["row"]) for t in tiles if t.get("walkable", True)
            and (t["col"], t["row"]) not in occ
            and hexgeo.distance((t["col"], t["row"]), anchor) == want]


def _step_toward(rid, tiles, ob, uid, anchor, want):
    """UN pas de `uid` vers la distance `want` d'`anchor` (au mieux de sa portee de mouvement).
    Rend la nouvelle distance. `applyAction move` accepte sans erreur une tuile hors portee mais
    l'unite ne bouge pas -> on essaie les tuiles par distance croissante a l'objectif."""
    import hexgeo
    here = _pos_of(ob, uid)
    occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead") and u["squadId"] != uid}
    cand = [(t["col"], t["row"]) for t in tiles if t.get("walkable", True)
            and (t["col"], t["row"]) not in occ]
    # objectif = une tuile a distance `want` de l'ancre ; on vise la plus proche de NOUS.
    goals = [c for c in cand if hexgeo.distance(c, anchor) == want]
    if not goals:
        return hexgeo.distance(here, anchor)
    goals.sort(key=lambda c: hexgeo.distance(c, here))
    for g in goals[:6]:
        if move(rid, uid, g[0], g[1]) is None:
            ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
            if _pos_of(ob2, uid) == g:
                return want
    # pas atteignable d'un pas : on avance vers le meilleur objectif
    g = goals[0]
    cand.sort(key=lambda c: hexgeo.distance(c, g))
    for c in cand[:40]:
        if hexgeo.distance(c, here) == 0:
            continue
        if move(rid, uid, c[0], c[1]) is None:
            ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
            if _pos_of(ob2, uid) == c:
                return hexgeo.distance(c, anchor)
    return hexgeo.distance(here, anchor)


def _place(rid, tiles, uid, anchor, want, max_cycles=8):
    """Amene `uid` a distance EXACTE `want` d'`anchor`, en enchainant pas + `endturn` x2 (chaque
    cycle recharge le mouvement des deux camps ; il fait aussi monter `TurnsStarted`, ce qui est
    MESURE et imprime a chaque ligne)."""
    import hexgeo
    for _ in range(max_cycles):
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        d = hexgeo.distance(_pos_of(ob, uid), anchor)
        if d == want:
            return d, True
        d = _step_toward(rid, tiles, ob, uid, anchor, want)
        if d == want:
            return d, True
        endturn(rid)
        endturn(rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    return hexgeo.distance(_pos_of(ob, uid), anchor), False


# --------------------------------------------------------------------------- etape C (croissance)

def _stage_c(rid, tiles, c0, v0, carriers) -> int:
    """L'AURA QUI GRANDIT, personne ne bouge. On isole UN porteur, on pose la victime a distance 2,
    puis on fait monter `TurnsStarted(porteur)` de 0-2 (rayon 1 -> effet INERTE) a 3+ (rayon 2 ->
    effet ACTIF). Les DEUX faces derivent par LEUR propre vecteur : live par des `endturn`, port par
    `StartTurnOperation.execute` sur l'etat CHARGE AVANT la croissance (aucun re-seed)."""
    import hexgeo
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.components import OwnerComponent
    bad = 0
    # (1) isoler : les autres porteurs TRES loin (>= 9) pour que `amount` ne depende que de c0.
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    vk = _pos_of(ob, v0["squadId"])
    for c in carriers:
        if c["squadId"] == c0["squadId"]:
            continue
        d, _ = _place(rid, tiles, c["squadId"], vk, 9)
        if d < 5:
            print(f"etape C: {c['visualId']} reste a {d} de la victime -- isolation impossible")
            return 0
    # (2) victime a distance 2 du porteur isole
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    ck = _pos_of(ob, c0["squadId"])
    got, _ = _place(rid, tiles, v0["squadId"], ck, 2)
    dec, ob, snap, state = _load(rid, tiles)
    ck = _pos_of(ob, c0["squadId"])
    got = hexgeo.distance(_pos_of(ob, v0["squadId"]), ck)
    ts0 = _turns_started(state, c0["squadId"])
    if got != 2:
        print(f"etape C: victime a d={got} (2 voulu) -- non exercee")
        return 0
    live0 = sorted(t for t, a in _live_effects(dec, v0["squadId"]).items() if a)
    port0, parm0 = _port_state(state, v0["squadId"])
    port0a = sorted(t for t, a in port0.items() if a)
    a0 = _live_fixed_armor(snap, v0["squadId"])
    if ts0 > 2:
        print(f"etape C: TurnsStarted(porteur) vaut deja {ts0} (> 2) -- le palier 1 n'est plus"
              " atteignable sur cette scene, croissance non exercee")
        return 0
    # (3) faire GRANDIR l'aura -- live par `endturn`, port par `StartTurnOperation` sur CE state.
    ent = state.get_entity(int(c0["squadId"]))
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    player = None if oc is None else oc.player
    n_turns = 3 - int(ts0 or 0)
    for _ in range(n_turns):
        endturn(rid)
        endturn(rid)
        if player is not None:
            StartTurnOperation.execute(state, player)
    port1, parm1 = _port_state(state, v0["squadId"])
    port1a = sorted(t for t, a in port1.items() if a)
    ts_port = _turns_started(state, c0["squadId"])
    dec2, ob2, snap2, _st2 = _load(rid, tiles)
    live1 = sorted(t for t, a in _live_effects(dec2, v0["squadId"]).items() if a)
    a1 = _live_fixed_armor(snap2, v0["squadId"])
    d_after = hexgeo.distance(_pos_of(ob2, v0["squadId"]), _pos_of(ob2, c0["squadId"]))
    ok = (live1 == port1a) and (a1 == parm1) and (d_after == 2)
    if not ok:
        bad += 1
    print(f"etape C (AURA QUI GRANDIT, personne ne bouge) : victime a d=2 du seul porteur a portee")
    print(f"   TurnsStarted {ts0} (rayon 1) : live actif={live0} armure={a0}"
          f" | port actif={port0a} armure={parm0}")
    print(f"   TurnsStarted {ts_port} (rayon 2) : live actif={live1} armure={a1}"
          f" | port actif={port1a} armure={parm1}   [{'OK' if ok else 'KO'}]"
          f" (distance inchangee: {d_after == 2})")
    if live0 == live1:
        print("   note: l'etat ACTIF n'a pas change -- etape C non discriminante sur cette scene")
    return bad


# --------------------------------------------------------------------------- etape E (derive)

def _stage_e(rid, tiles, c0, c1, v0, carriers) -> int:
    """Le port EVOLUE-t-il tout seul ? On charge la scene UNE fois, puis on joue le MEME pas des
    deux cotes : offline par `MoveUnitOperation` (qui declenche le driver `RefreshEffectsOperation`
    porte), live par `applyAction`. On compare (instances actives, FixedArmor) APRES le pas, le
    port n'ayant JAMAIS ete re-seede entre les deux lectures."""
    import hexgeo
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    bad = 0
    dec, ob, snap, state = _load(rid, tiles)
    vk = _pos_of(ob, v0["squadId"])
    before_live = sorted(t for t, a in _live_effects(dec, v0["squadId"]).items() if a)
    a_before_live = _live_fixed_armor(snap, v0["squadId"])
    pact0, parm0 = _port_state(state, v0["squadId"])
    before_port = sorted(t for t, a in pact0.items() if a)
    # cible du pas : une tuile LIBRE hors de portee de TOUS les porteurs (rayon max = 3)
    occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")
           and u["squadId"] != v0["squadId"]}
    ck = [_pos_of(ob, c["squadId"]) for c in carriers]
    far = [(t["col"], t["row"]) for t in tiles if t.get("walkable", True)
           and (t["col"], t["row"]) not in occ
           and all(hexgeo.distance((t["col"], t["row"]), k) >= 5 for k in ck)]
    if not far:
        print("etape E: aucune tuile hors de toutes les auras -- non exercee")
        return 0
    far.sort(key=lambda c: hexgeo.distance(c, vk))
    dest = far[0]
    # (1) OFFLINE : le port joue le pas par SA propre operation, sans aucun apport live.
    MoveUnitOperation(v0["squadId"], dest).execute(state, EventBus())
    pact1, parm1 = _port_state(state, v0["squadId"])
    after_port = sorted(t for t, a in pact1.items() if a)
    # (2) LIVE : le MEME pas, puis relecture.
    err = move(rid, v0["squadId"], dest[0], dest[1])
    dec2, ob2, snap2, _st2 = _load(rid, tiles)
    got = _pos_of(ob2, v0["squadId"])
    after_live = sorted(t for t, a in _live_effects(dec2, v0["squadId"]).items() if a)
    a_after_live = _live_fixed_armor(snap2, v0["squadId"])
    if got != dest:
        print(f"etape E: le pas live n'a pas abouti ({err}, arrivee {got} != {dest})"
              " -- confrontation non exercee")
        return 0
    ok_act = (after_live == after_port)
    ok_arm = (a_after_live == parm1)
    if not ok_act:
        bad += 1
    if not ok_arm:
        bad += 1
    # diagnostic d'ATTRIBUTION : sous quelle source la contribution d'armure est-elle rangee ?
    from engine.runner.components import StatsComponent as _SC
    from engine.entities.stats import StatType as _ST, StatPart as _SP, CAPTURED_SOURCE
    from engine.entities.effects import effect_stat_mod_key
    _e = state.get_entity(int(v0["squadId"]))
    _sc = _e.get_component(_SC) if _e is not None else None
    _us = getattr(_sc.ctx, "stats", None) if _sc is not None else None
    if _us is not None:
        comp = _us.components.get(int(_ST.FIXED_ARMOR))
        per = dict(getattr(comp.modification, "per_source", {})) if comp is not None else {}
        keys = [(("CAPTURED" if k is CAPTURED_SOURCE else str(k))[:60], v) for k, v in per.items()]
        print(f"   attribution FixedArmor : initial={_us.get_stat(int(_ST.FIXED_ARMOR), int(_SP.INITIAL))}"
              f" current={_us.get_stat(int(_ST.FIXED_ARMOR), int(_SP.CURRENT))} per_source={keys}")
        for e2 in (state.effects.by_unit.get(int(v0['squadId']), []) if state.effects else []):
            if int(getattr(e2, 'effect_type', 0) or 0) in (RED1, RED2):
                print(f"      cle du driver pour {e2.effect_type} = {str(effect_stat_mod_key(e2))[:70]}")
    print(f"etape E (DERIVE, aucun re-seed) : sortie d'aura {vk} -> {dest}")
    print(f"   AVANT  live actif={before_live} armure={a_before_live}"
          f" | port actif={before_port} armure={parm0}")
    print(f"   APRES  live actif={after_live} armure={a_after_live}"
          f" | port actif={after_port} armure={parm1}"
          f"   [{'OK' if ok_act and ok_arm else 'KO'}]")
    if before_port == after_port and before_live == after_live:
        print("   note: l'etat ACTIF n'a pas change -- etape E non discriminante sur cette scene")
    return bad


# --------------------------------------------------------------------------- scenario live

def scenario(args) -> int:
    rid = build(args.p_units, args.a_units, args.board, args.seed)
    print("runner", rid, "| board", args.board, "| seed", args.seed)
    bad = 0
    try:
        import hexgeo
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = bg["tiles"]
        dec, ob, snap, state = _load(rid, tiles)
        alive = [u for u in ob["units"] if not u.get("isDead")]
        carriers = [u for u in alive if u["visualId"].startswith("death")]
        victims = [u for u in alive if u not in carriers]
        if len(carriers) < 2 or not victims:
            print("KO montage: porteurs", [u["visualId"] for u in carriers],
                  "victimes", [u["visualId"] for u in victims])
            return 1
        c0, c1 = carriers[0], carriers[1]
        v0 = victims[0]
        print("porteur#1", c0["visualId"], c0["squadId"], "| porteur#2", c1["visualId"],
              c1["squadId"], "| victime", v0["visualId"], v0["squadId"])

        # ---- etape A : la POSE des DEUX instances (AddEffectInitially) ----------------------
        n_ok = 0
        for v in victims:
            wide = _live_effects(dec, v["squadId"])
            pa, _arm = _port_state(state, v["squadId"])
            same = set(wide) == set(pa)
            if set(wide) == {RED1, RED2} and same:
                n_ok += 1
            print(f"etape A | {v['visualId']:<14} live(large)={ {k: int(a) for k, a in sorted(wide.items())} }"
                  f" port={ {k: int(a) for k, a in sorted(pa.items())} }"
                  f" {'OK' if same else 'KO'}")
            if not same:
                bad += 1
        print(f"etape A: {n_ok}/{len(victims)} victimes portent les DEUX instances des deux cotes")

        # ---- ecarter le 2e/3e porteur pour isoler l'etage GEOMETRIE de l'etape B -----------
        vk = _pos_of(ob, v0["squadId"])
        for c in carriers[1:]:
            d, ok = _place(rid, tiles, c["squadId"], vk, 8)
            print(f"ecarte {c['visualId']} -> dist {d} de la victime", "" if ok else "(au mieux)")

        # ---- etape B : la GEOMETRIE (distance 4 -> 1 du porteur #1) ------------------------
        rows = []
        for want in (4, 3, 2, 1):
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            ck = _pos_of(ob, c0["squadId"])
            got, ok = _place(rid, tiles, v0["squadId"], ck, want)
            dec, ob, snap, state = _load(rid, tiles)
            ck = _pos_of(ob, c0["squadId"])
            got = hexgeo.distance(_pos_of(ob, v0["squadId"]), ck)
            live_all = _live_effects(dec, v0["squadId"])
            larm = _live_fixed_armor(snap, v0["squadId"])
            pact, parm = _port_state(state, v0["squadId"])
            n = _amount(state, v0["squadId"], c0["squadId"])
            ts = _turns_started(state, c0["squadId"])
            live_active = sorted(t for t, a in live_all.items() if a)
            port_active = sorted(t for t, a in pact.items() if a)
            agree = (live_active == port_active)
            if not agree:
                bad += 1
            rows.append((got, ts, live_active, port_active, larm, parm))
            geo = [(c["visualId"][5:12], hexgeo.distance(_pos_of(ob, c["squadId"]), _pos_of(ob, v0["squadId"])),
                    _turns_started(state, c["squadId"])) for c in carriers]
            print(f"{'OK ' if agree else 'KO '}d={got} TurnsStarted(porteur)={ts} amount(port)={n}"
                  f" | live actif={live_active} port actif={port_active}"
                  f" | FixedArmor live={larm} port={parm}")
            print(f"      porteurs (nom, dist, TurnsStarted) = {geo}"
                  f" | port detail (type, activeFlag, source, isActive, value) ="
                  f" {_port_detail(state, v0['squadId'])}")
        print("etape B:", "OK" if bad == 0 else f"{bad} DESACCORDS", "| lignes", len(rows))
        if len({tuple(r[2]) for r in rows}) < 2:
            print("   note: l'etat ACTIF n'a pas VARIE sur les 4 distances -- etape B non"
                  " discriminante sur cette scene (rayon deja >= 4 ?)")

        # ---- etape C : l'AURA QUI GRANDIT (personne ne bouge) ------------------------------
        bad += _stage_c(rid, tiles, c0, v0, carriers)

        # ---- etape D : le SECOND porteur -> bascule 1071 -> 1072 ---------------------------
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        vk = _pos_of(ob, v0["squadId"])
        d1, _ = _place(rid, tiles, c1["squadId"], vk, 1)
        dec, ob, snap, state = _load(rid, tiles)
        vk = _pos_of(ob, v0["squadId"])
        d0 = hexgeo.distance(_pos_of(ob, c0["squadId"]), vk)
        d1 = hexgeo.distance(_pos_of(ob, c1["squadId"]), vk)
        live_all = _live_effects(dec, v0["squadId"])
        larm = _live_fixed_armor(snap, v0["squadId"])
        pact, parm = _port_state(state, v0["squadId"])
        n = _amount(state, v0["squadId"], c0["squadId"])
        live_active = sorted(t for t, a in live_all.items() if a)
        port_active = sorted(t for t, a in pact.items() if a)
        agree = (live_active == port_active)
        if not agree:
            bad += 1
        print(f"{'OK ' if agree else 'KO '}etape D | porteurs a d={d0} et d={d1} | amount(port)={n}"
              f" | live actif={live_active} port actif={port_active}"
              f" | FixedArmor live={larm} port={parm}")
        if live_active != [RED2]:
            print("   note: 1072 n'est PAS l'instance active live -> la variante -40 % n'est pas"
                  " exercee par cette scene (les deux porteurs ne couvrent pas la victime)")

        # ---- etape E : le port DERIVE tout seul (aucun re-seed) -----------------------------
        # Les etapes A..D confrontent deux etats SEEDES : elles prouvent que le port LIT juste,
        # pas qu'il EVOLUE juste. Ici on charge UNE fois, puis on joue le MEME pas des DEUX cotes
        # (offline `MoveUnitOperation` / live `applyAction`) et on compare ce que CHACUN produit.
        bad += _stage_e(rid, tiles, c0, c1, v0, carriers)
        print("VERDICT:", "OK" if bad == 0 else f"{bad} DESACCORDS")
    finally:
        if not args.keep:
            dispose(rid)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--p-units", default="ultraTitus,necroWarden,adeptMorvenn")
    ap.add_argument("--a-units", default="deathTyphus,deathBlightlord,deathPutrifier")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    bad = offline_guard()
    if not args.offline_only:
        bad += scenario(args)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
