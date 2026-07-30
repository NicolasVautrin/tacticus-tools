"""MESURE du DE-FORK du vecteur `On(DamageDealt = 0x10)`.

Le port a DEUX chemins offline pour UN SEUL concept natif :

  * le BUS `On(0x10)` -- `operations/triggers/dispatch/attack.py::damage_dealt_triggers`, emis par le
    chokepoint `AttackDamageOperation._apply_damage_pipeline` en mirror d'
    `IdunBattle.Operations.ApplyDamageOperation$$Execute` (sequence `On(0x3a)` -> `On(0xf)` ->
    `On(0x10)`), sous le gate « reduction de PV REELLEMENT appliquee > 0 » ;
  * les appels IMPERATIFS de `_on_fire_damage_ability` / `_on_toxic_damage_ability`, poses APRES la
    resolution complete de l'attaque (`after_hit_normal_attack` cote NORMALE,
    `damage_ops/ability.py::execute_ability_attack` cote ABILITY), SANS gate.

Or les DEUX abilities natives ecoutent bien `On(0x10)` :
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
        On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
        On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)

Ce probe MESURE les deux moities du critere de de-fork, sans rien changer au moteur :

  (a) DECLENCHEMENT -- le SITE d'appel de chaque pose on-hit (pile d'appel filtree `engine/`), pour
      confronter l'ENSEMBLE des sites du bus a celui des deux appels imperatifs. Un de-fork qui
      elargit ou retrecit cet ensemble ne PRESERVE PAS le declenchement.
  (b) FLUX RNG -- la LISTE ORDONNEE des tirages `IntBasedMersenneTwister` avec leur site, plus le
      `mti` final. C'est le verdict de consommation le moins cher, et le seul qui voie un tirage
      DEPLACE (une valeur de degat identique ne prouve rien : deux tirages permutes peuvent rendre
      le meme total).

Il rend AUSSI l'inventaire STATIQUE des sites d'emission (`_apply_damage_pipeline`) vs des sites
imperatifs, et le recensement des consommateurs de `event_id == 16` dans les 4 registres.

Usage :  python probe_o10_defork.py [--tag before|after]
Sortie : logs/o10-defork/<tag>.json  +  resume ASCII sur stdout.
Pre-requis : session Frida vivante et WARMEE (aucun (re)inject ici). ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import inspect
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
BOARD = "MC1_67"
SEED = "777"
TOXIC_VIS = "genesBiophagus"        # HERO, arme MELEE `Toxic` 1 coup (--list-pool)
FLAME_VIS = "adeptRetributor"       # HERO, arme RANGED `Flame` + passif FireOfAbsolution
FOES = "necroWarden,necroWarden"    # temoin sans Daemon
# DISCRIMINANT du flux RNG : arme `Toxic` (1 coup) + passif `BarbedOvipositor`, dont le behaviour
# consomme un `PickRandomly` sur `On(0 = UnitDeath)` -- vecteur emis ENTRE la position bus et la
# position imperative du canal 1203.
OVIPOSITOR_VIS = "tyranParasite"
# Victime NI `Mechanical` NI `Steppable` -> elle passe les deux exclusions du
# `BarbedOvipositorAbility$$CreateTrigger` (`necroWarden` est Mechanical, donc inutilisable ici).
FRAGILE_FOE = "astraBullgryn"
FIRE_TILE = 5                       # EffectType.Fire
CONTAMINATED_TILE = 1244            # EffectType.Contaminated (0x4dc)
# #283 : etait `DAMAGE_DEALT = 16`. Juste sur les deux builds versionnes (16 < 40), donc
# silencieusement faux au premier build qui touchera aux membres inferieurs -- resolu par MEMBRE.
sys.path.insert(0, str(PYDIR))
from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402

DAMAGE_DEALT = int(EventTriggerType.DamageDealt)


# --------------------------------------------------------------------------- plomberie live

def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, p_units, a_units):
    sf = ROOT / "logs" / "runners" / f"o10defork-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(sf),
         "--board", BOARD, "--roster", "2",
         "--p-units", p_units, "--a-units", a_units],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("[probe] build KO:", (p.stderr or p.stdout)[-500:])
        return None, sf
    return json.loads(sf.read_text())["runnerId"], sf


# --------------------------------------------------------------------------- instrumentation

_ENGINE_MARK = "engine"


def _site(skip=2, depth=14):
    """Signature de pile filtree sur `engine/` : `module:fonction` du plus interne au plus externe.

    C'est ce qui distingue un tirage DEPLACE d'un tirage identique : la valeur seule ne le dirait
    pas (deux tirages permutes rendent le meme total quand les bornes coincident)."""
    out = []
    f = inspect.currentframe()
    for _ in range(skip):
        f = f.f_back if f is not None else None
    n = 0
    while f is not None and n < depth:
        fn = f.f_code.co_filename.replace("\\", "/")
        if f"/{_ENGINE_MARK}/" in fn:
            out.append(f"{Path(fn).stem}:{f.f_code.co_name}")
            n += 1
        f = f.f_back
    return out


class Trace:
    """Journal ORDONNE des tirages RNG et des poses d'effet de tuile, avec leur site d'appel."""

    def __init__(self):
        self.rolls = []      # [{i, kind, args, value, site}]
        self.effects = []    # [{effect_type, target, placed, site}]

    def as_dict(self):
        return {"rolls": self.rolls, "effects": self.effects}


def _install(trace):
    """Patch NON INTRUSIF (probe-only, jamais dans le moteur) de `IntBasedMersenneTwister` et d'
    `AddEffectOperation.execute`. Version-agnostique : marche que le canal soit imperatif (fork) ou
    branche sur le bus (de-fork), donc les deux traces sont directement comparables."""
    from engine.runner.prng import IntBasedMersenneTwister as MT
    from engine.runner.operations.effects import AddEffectOperation

    if getattr(MT, "_probe_patched", False):
        return
    orig_ni, orig_next = MT.next_internal, MT.next

    def next_internal(self, lo, hi):
        v = orig_ni(self, lo, hi)
        trace.rolls.append({"i": len(trace.rolls), "kind": "next_internal",
                            "args": [int(lo), int(hi)], "value": int(v), "site": _site()})
        return v

    def next_(self, bound):
        v = orig_next(self, bound)
        trace.rolls.append({"i": len(trace.rolls), "kind": "next",
                            "args": [int(bound)], "value": int(v), "site": _site()})
        return v

    MT.next_internal, MT.next, MT._probe_patched = next_internal, next_, True

    orig_add = AddEffectOperation.execute

    def execute(state, source, target, effect_type, **kw):
        before = None
        if getattr(state, "effects", None) is not None and target is not None:
            before = state.effects.has_effect(target, effect_type=effect_type)
        r = orig_add(state, source, target, effect_type, **kw)
        if int(effect_type) in (FIRE_TILE, CONTAMINATED_TILE) and target is not None:
            trace.effects.append({"effect_type": int(effect_type), "target": int(target),
                                  "source": (int(source) if source is not None else None),
                                  "was_present": before, "placed": r is not None,
                                  "site": _site()})
        return r

    AddEffectOperation.execute = staticmethod(execute)


# --------------------------------------------------------------------------- inventaires statiques

def _consumers_of_event(event_id):
    """Re-DERIVE (jamais hérité d'une doc) les classes des 4 registres qui ecoutent `event_id`."""
    from engine.runner.operations.triggers.dispatch import registry as R
    out = []
    for name, reg in (("TRAIT", R.TRAIT_TRIGGERS), ("ABILITY", R.ABILITY_TRIGGERS),
                      ("ACTIVE_ABILITY", R.ACTIVE_ABILITY_TRIGGERS), ("EFFECT", R.EFFECT_TRIGGERS)):
        for key, classes in reg.items():
            for c in classes:
                ids = set(getattr(c, "event_ids", ()) or ())
                if getattr(c, "event_id", -1) == event_id or event_id in ids:
                    out.append({"registry": name, "key": str(key), "cls": c.__name__})
    # registre GLOBAL (owner-less) : n'existe qu'apres le de-fork -- absent = fork en place.
    for c in (getattr(R, "GLOBAL_TRIGGERS", None) or ()):
        ids = set(getattr(c, "event_ids", ()) or ())
        if getattr(c, "event_id", -1) == event_id or event_id in ids:
            out.append({"registry": "GLOBAL", "key": "-", "cls": c.__name__})
    return out


def _emission_sites():
    """Sites d'appel STATIQUES du chokepoint d'emission vs des deux appels imperatifs.

    Le grep est fait sur les SOURCES du paquet `engine` (pas d'AST : on veut le compte de sites,
    pas une analyse de flot) -- il sert a montrer que les deux ENSEMBLES ne coincident pas."""
    eng = PYDIR / "engine"
    out = {"pipeline": [], "imperative": []}
    for p in sorted(eng.rglob("*.py")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(txt.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if "_apply_damage_pipeline(" in s and "def " not in s:
                out["pipeline"].append(f"{p.relative_to(eng).as_posix()}:{i}")
            if ("_on_fire_damage_ability(" in s or "_on_toxic_damage_ability(" in s) \
                    and "def " not in s and "import" not in s:
                out["imperative"].append(f"{p.relative_to(eng).as_posix()}:{i}")
    return out


# --------------------------------------------------------------------------- scenarios offline

def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _drive_to_contact(sid, rid, board, carrier_vis):
    """DRIVE les positions (doctrine : jamais « bloque par la geometrie de spawn ») jusqu'a ce que
    `carrier_vis` ait un plan d'attaque LIVE. Rend (uid, target, abilityType normal) ou None."""
    my = None
    for _ in range(14):
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 200)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == carrier_vis and u.get("alive")), None)
        if me is None:
            return None
        if my is None:
            my = me.get("owner")
        if dv.get("currentPlayer") != my or me["id"] not in (dv.get("toActivate") or []):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((p for p in (dv.get("attackPlans") or []) if p.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk = ev["ranked"][0]
            here = me.get("pos") or {}
            if rk.get("col") is None or (rk["col"], rk["row"]) == (here.get("col"), here.get("row")):
                return me["id"], ev["targetId"], norm["id"]
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            continue
        pos = me.get("pos") or {}
        foes = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not foes:
            return None
        tp = min(((u["pos"]["col"], u["pos"]["row"]) for u in foes),
                 key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
        dist = _bfs(board, board.id_at(*tp))
        mt = _rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if pool:
            col, row = reach[min(pool, key=lambda t: dist[t])]
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(s["mt"]), s["mti"]
    return r


def _run_scenario(base_state, mt_seed, attacker, target, trace, mutate=None):
    """Rejoue UNE attaque normale sur une COPIE PROFONDE de l'etat, MT identique.

    `mutate(state)` = crochet de mise en scene (ex. baisser les PV de la cible pour forcer la MORT,
    qui fait passer les vecteurs de mort ENTRE la position bus et la position imperative)."""
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.components import HealthComponent, PositionComponent

    st = copy.deepcopy(base_state)
    st.rng = _seed_rng(mt_seed)
    if mutate is not None:
        mutate(st)
    i0, e0 = len(trace.rolls), len(trace.effects)
    r = Runner(st).install_default_handlers(20)
    r.apply(AttackUnitMessage(attacker, target))
    thc = st.get_entity(target).get_component(HealthComponent)
    pc = st.get_entity(target).get_component(PositionComponent)
    tile = st.board.id_at(pc.col, pc.row) if pc is not None else None
    last = r.damage_handler.last or {}
    return {
        "profile": last.get("profile"), "hits": last.get("hits"), "total": last.get("total"),
        "hp_after": (thc.hp if thc is not None else None), "tile": tile,
        "mti": st.rng.mti, "n_rolls": len(trace.rolls) - i0,
        "rolls": trace.rolls[i0:], "effects": trace.effects[e0:],
        "fire_on_tile": st.effects.has_effect(tile, effect_type=FIRE_TILE) if tile else None,
        "contaminated_on_tile": (st.effects.has_effect(tile, effect_type=CONTAMINATED_TILE)
                                 if tile else None),
    }


def _montage(sid, report, trace, Board, load_state, HealthComponent,
             p_units, a_units, carrier, prefix, live_diff):
    """Monte UN runner, amene `carrier` au contact, et rejoue la MEME attaque offline en deux
    regimes : cible SURVIVANTE et cible LETALE (PV ramenes a 1). Le regime letal fait passer les
    vecteurs de mort ENTRE la position bus et la position imperative."""
    rid, _sf = _build(sid, p_units, a_units)
    if rid is None:
        print(f"[o10] {prefix}: build KO -> SKIP")
        return
    print(f"[o10] {prefix}: runner={rid} p={p_units} a={a_units}")
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        drive = _drive_to_contact(sid, rid, board, carrier)
        if drive is None:
            print(f"[o10] {prefix}: pas de contact -> SKIP")
            return
        me_id, tgt_id, norm_id = drive
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 200)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s1 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        base = load_state(dv, ob, snap, board=board)
        if base.effects is None:
            print(f"[o10] {prefix}: EffectsState absent -> SKIP")
            return

        report["scenarios"][f"{prefix}_survivor"] = _run_scenario(base, s1, me_id, tgt_id, trace)

        def _to_1hp(st):
            st.get_entity(tgt_id).get_component(HealthComponent).hp = 1

        report["scenarios"][f"{prefix}_lethal"] = _run_scenario(base, s1, me_id, tgt_id, trace,
                                                                mutate=_to_1hp)
        if live_diff:
            live_before = s1["mti"]
            res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": me_id, "targetId": tgt_id,
                "abilityType": norm_id}}, 60)
            s2 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
            live_hp = next((u.get("hp") for u in (res.get("units") or [])
                            if u.get("squadId") == tgt_id), None)
            off = report["scenarios"][f"{prefix}_survivor"]
            report["scenarios"][f"{prefix}_live_vs_offline"] = {
                "mti_before": live_before, "mti_live": s2.get("mti"), "mti_offline": off["mti"],
                "delta_live": (s2.get("mti") - live_before) if s2.get("mti") is not None else None,
                "delta_offline": off["mti"] - live_before,
                "hp_live": live_hp, "hp_offline": off["hp_after"], "profile": off["profile"],
            }
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="before", help="before (fork en place) | after (de-forke)")
    args = ap.parse_args()

    sys.path.insert(0, str(PYDIR))
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent

    report = {"tag": args.tag,
              "consumers_on_0x10": _consumers_of_event(DAMAGE_DEALT),
              "emission_sites": _emission_sites(),
              "scenarios": {}}

    print(f"[o10] tag={args.tag}")
    print(f"[o10] consommateurs bus On(0x10) = {len(report['consumers_on_0x10'])}")
    for c in report["consumers_on_0x10"]:
        print(f"[o10]   {c['registry']:<15} key={c['key']:<20} {c['cls']}")
    es = report["emission_sites"]
    print(f"[o10] sites d'emission bus (_apply_damage_pipeline) = {len(es['pipeline'])}")
    for s in es["pipeline"]:
        print(f"[o10]   BUS  {s}")
    print(f"[o10] sites imperatifs (_on_*_damage_ability)       = {len(es['imperative'])}")
    for s in es["imperative"]:
        print(f"[o10]   IMP  {s}")

    trace = Trace()
    _install(trace)
    sid = _sid()

    # --- MONTAGE 1 : porteur Toxic NU (`genesBiophagus`) -> le cas nominal deja live-valide.
    _montage(sid, report, trace, Board, load_state, HealthComponent,
             p_units=f"{TOXIC_VIS},{FLAME_VIS}", a_units=FOES, carrier=TOXIC_VIS,
             prefix="M1", live_diff=True)

    # --- MONTAGE 2 : DISCRIMINANT. `tyranParasite` porte une arme `Toxic` (1 coup) ET le passif
    #     `BarbedOvipositor`, dont le behaviour consomme un `PickRandomly` (tirage) sur l'event
    #     `On(0 = UnitDeath)`. Or ce vecteur de mort est emis par `_fire_death_if_killed`, c.-a-d.
    #     STRICTEMENT ENTRE la position BUS (`damage_dealt_triggers` dans `_apply_damage_pipeline`)
    #     et la position IMPERATIVE (`after_hit_normal_attack`, apres l'attaque complete). La cible
    #     `astraBullgryn` n'est ni `Mechanical` ni `Steppable` -> elle passe les deux exclusions du
    #     `BarbedOvipositorAbility$$CreateTrigger`. C'est le regime ou fork et de-fork PEUVENT
    #     produire un ORDRE de tirages different.
    _montage(sid, report, trace, Board, load_state, HealthComponent,
             p_units=f"{OVIPOSITOR_VIS},{FLAME_VIS}", a_units=f"{FRAGILE_FOE},{FRAGILE_FOE}",
             carrier=OVIPOSITOR_VIS, prefix="M2", live_diff=False)

    for k, v in report["scenarios"].items():
        if k.endswith("_live_vs_offline"):
            print(f"[o10] {k}: mti {v['mti_before']} -> live {v['mti_live']} (d={v['delta_live']}) "
                  f"/ off {v['mti_offline']} (d={v['delta_offline']}) hp live={v['hp_live']} "
                  f"off={v['hp_offline']} profile={v['profile']}")
            continue
        print(f"[o10] {k}: profile={v['profile']} hits={v['hits']} total={v['total']} "
              f"hp={v['hp_after']} rolls={v['n_rolls']} mti={v['mti']} "
              f"fire={v['fire_on_tile']} contaminated={v['contaminated_on_tile']}")
        for r in v["rolls"]:
            print(f"[o10]     roll#{r['i']} {r['kind']}{tuple(r['args'])} = {r['value']}"
                  f"  <- {' <- '.join(r['site'][:5])}")
        for e in v["effects"]:
            print(f"[o10]     effect {e['effect_type']} tile={e['target']} placed={e['placed']} "
                  f"was={e['was_present']}  <- {' <- '.join(e['site'][:5])}")

    _dump(report, args.tag)


def _dump(report, tag):
    out = ROOT / "logs" / "o10-defork"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{tag}.json"
    p.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"[o10] trace -> {p}")


if __name__ == "__main__":
    main()
