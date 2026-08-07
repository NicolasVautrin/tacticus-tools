#!/usr/bin/env python
"""Probe #498 -- confront LIVE du port de `1152 UnstoppableMomentumReworked` (`orksNob`
« Tanksmasha », Orks), la CHARGE EN LIGNE.

Protocole (replay-diff, meme forme que `probe_116_necrons.py`) : on MONTE la geometrie
(`--place`/`--a-place` : caster et cibles ALIGNES sur un axe hex -- on ne subit pas le spawn), on
capture l'etat AVANT le cast (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng` +
`boardGraph`), on rejoue le cast OFFLINE par le CHEMIN REEL
(`AbilityHandler.visit_ActiveAbilityMessage`), puis le MEME cast LIVE (`applyAction`), et on
confronte etage par etage.

ETAGES (chacun est un observable DISTINCT -- jamais un total qui absorberait les autres) :

  E1 CABLAGE      -- le cast est atteignable (`abilityTargets(...).fromHere` non vide) et le port
                     ne l'ignore plus : `AbilityHandler.last['ported'] is True`.
  E2 TRAJET       -- la position FINALE du caster, offline == live (la ligne de charge, sa
                     troncature sur obstacle, et les `Move` pas a pas).
  E3 DEGAT/CIBLE  -- les degats PAR CIBLE et PAR COUP, offline == live (bit-exact).
  E4 SCALING      -- le terme `extraDmg x traversedSteps` : sur DEUX cibles alignees a des pas
                     differents, l'ecart des BASES doit valoir `extraDmg x (k2 - k1)`. C'est
                     l'etage qui separe le per-hex du degat d'arme -- jamais fitter un scalaire.
  E5 EFFETS       -- `Pinned` (ordinaire) / `Stunned` (BigTarget), offline == live, par cible.
  E6 DEPLACEMENT  -- les positions FINALES des cibles poussees, offline == live.

Les trois faces du kit (`crit`, `block`, `extra_hits`) sont DECOMPOSEES : E3 confronte la SEQUENCE
de coups (donc `extra_hits` change la longueur, `crit`/`block` changent un coup et pas les autres),
et `--regime` monte des temoins qui les separent (`nocrit` = crit force a 0 sur le caster).

ASCII only (cp1252). Usage :
    python probe_498_unstoppable_momentum.py --phase ligne
    python probe_498_unstoppable_momentum.py --phase bigtarget
    python probe_498_unstoppable_momentum.py --phase all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.handler import AbilityHandler               # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402

MOMENTUM = int(ActiveAbilityType.UnstoppableMomentumReworked)   # 1152
PINNED = int(EffectType.Pinned)                                 # 1065
STUNNED = int(EffectType.Stunned)                               # 1162
CASTER_VISUAL = "orksNob"
BOARD = "MC1_67"


# --------------------------------------------------------------------------- helpers RPC / runner

def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_path: Path, args_extra: list, retries: int = 40) -> int:
    """`rl_duel build`. Le plafond MAX_RUNNERS est PARTAGE : un `runner cap reached` est une
    CONTENTION, pas une erreur -- on attend un slot (on ne dispose JAMAIS le runner d'un autre)."""
    for attempt in range(max(1, retries)):
        state_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)] + args_extra,
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if state_path.exists():
            return json.loads(state_path.read_text())["runnerId"]
        out = (proc.stderr or "") + (proc.stdout or "")
        if ("runner cap reached" in out or "runner creation paused" in out) and attempt + 1 < retries:
            print("[498] slot/drain -- attente (%d/%d)" % (attempt + 1, retries), flush=True)
            time.sleep(20)
            continue
        print("[498] build KO:", out[-1200:])
        sys.exit(2)
    sys.exit(2)


def _dispose(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


def _capture(sid, rid):
    """(mkstate, dec, board) -- `mkstate()` rebatit un etat OFFLINE neuf depuis les MEMES payloads."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec, board


def _alive(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _unit_of(dec, visual):
    for u in _alive(dec):
        if u.get("visualId") == visual or u.get("unitId") == visual:
            return u
    return None


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _positions(dec):
    return {int(u["id"]): _pos(u) for u in (dec.get("units") or [])}


def _hp(dec):
    return {int(u["id"]): int(u.get("hp") or 0) for u in (dec.get("units") or [])}


def _effects_by_unit(dec):
    out: dict = {}
    for u in (dec.get("units") or []):
        out[int(u.get("id"))] = sorted(int(e.get("effectType") or -1)
                                       for e in (u.get("effects") or []))
    return out


def _from_here(sid, rid, caster, ability):
    at = _r(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 150)
    for u in (at.get("units") or []):
        if int(u.get("unitId") or -1) != int(caster):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) == int(ability):
                return list(ab.get("fromHere") or [])
    return []


def _tid(t):
    if isinstance(t, dict):
        for k in ("unitId", "entityId", "id", "targetId", "tileId"):
            if t.get(k) is not None:
                return int(t[k])
        return None
    return int(t)


def _cast_live(sid, rid, caster, target, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": int(caster), "targetId": int(target),
        "abilityType": int(ability)}}, 180)


def _live_tags(res, ability):
    """Les TAGS BRUTS des events de degat du cast -- sert a montrer que le regime CRIT/BLOCK est
    reellement exerce (temoin NON DEGENERE) et non pas seulement demande a la ligne de commande."""
    out = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability):
                out.append({k: v for k, v in td.items()
                            if k in ("Target_Id", "Amount", "Is_Critical", "Is_Blocked",
                                     "Critical", "Blocked", "Damage_Reason")})
    return out


def _live_per_hit(res, ability):
    """{target_id -> [degat par COUP]} depuis les events d'`applyAction(captureEvents)`. Un event de
    degat portant `Active_Ability_Type == ability` == UN coup APPLIQUE (meme oracle que #61/#116)."""
    out: dict = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability):
                out.setdefault(int(td.get("Target_Id")), []).append(td.get("Amount"))
    return out


def _offline_cast(state, caster, target, ability):
    from engine.runner.messages import ActiveAbilityMessage
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=int(target), ability_type=int(ability)))
    return h


def _offline_per_hit(last: dict) -> dict:
    """{target_id -> [degat par COUP]} depuis le retour du port. Chaque entree d'`attacks` porte
    l'`attack` rendu par `AttackDamageOperation.execute_ability_attack`, dont `per_hit` EST la liste
    des degats appliques coup par coup (`hits` y est le NOMBRE de coups, pas la liste)."""
    out: dict = {}
    for a in (last.get("attacks") or []):
        tid = a.get("target")
        atk = a.get("attack") or {}
        if tid is not None:
            out.setdefault(int(tid), []).extend(list(atk.get("per_hit") or []))
    return out


# --------------------------------------------------------------------------- phases

def _run_phase(sid, state_path, args_extra, aim_kind: str, label: str) -> dict:
    """Monte le runner, cherche l'aim, rejoue OFFLINE puis LIVE, confronte les 6 etages, DISPOSE
    le runner. Rend le JOURNAL structure de la phase : `{"label", "fails" (liste de messages),
    "ported", "live_ok", "caster_from/off/live", "steps", "line", "off_hits", "live_hits",
    "steps_by_target", "extra_by_target", "off_effects", "live_effects", "off_pos", "live_pos",
    "friends", "crit_flags"}`. C'est LUI la source unique du test de garde (`tests/engine/runner/
    test_unstoppable_momentum_live.py`), qui ne re-derive rien."""
    rid = _build(state_path, args_extra)
    fails: list = []
    J: dict = {"label": label}
    try:
        mkstate, dec0, board = _capture(sid, rid)
        caster = _unit_of(dec0, CASTER_VISUAL)
        if caster is None:
            J["fails"] = ["[498/%s] ECHEC : caster %s absent" % (label, CASTER_VISUAL)]
            print(J["fails"][0])
            return J
        cid = int(caster["id"])
        cpos = _pos(caster)
        print("[498/%s] caster u%d %s @%s" % (label, cid, CASTER_VISUAL, cpos))
        for u in _alive(dec0):
            if int(u["id"]) != cid:
                print("[498/%s]   ennemi u%s %s @%s hp=%s" % (
                    label, u["id"], u.get("visualId"), _pos(u), u.get("hp")))

        # --- l'AIM : une tuile LEGALE `fromHere` (jamais `targets`, superset move-inclus, #111) ---
        fh = _from_here(sid, rid, cid, MOMENTUM)
        if not fh:
            J["fails"] = ["[498/%s] ECHEC E1 : aucune cible legale `fromHere` pour 1152" % label]
            print(J["fails"][0])
            return J
        # On veut l'aim qui pointe VERS la file d'ennemis : la tuile de `fromHere` la plus proche
        # de l'ennemi le plus proche.
        import hexgeo
        # ENNEMIS SEULEMENT (`ctrl` faux) : la tuile d'un AMI n'est de toute facon pas une cible
        # legale (`TargetTileIsFreeOrEnemy`), et la prendre pour reperer la direction ferait viser
        # a cote sur les montages qui posent un ami sur la ligne.
        foes = [u for u in _alive(dec0) if int(u["id"]) != cid and not u.get("ctrl")]
        nearest = min(foes, key=lambda u: hexgeo.distance(cpos, _pos(u))) if foes else None
        def _tile_xy(t):
            if isinstance(t, dict) and t.get("col") is not None:
                return (t["col"], t["row"])
            tid = _tid(t)
            xy = board.coord(int(tid)) if tid is not None else None
            return (int(xy[0]), int(xy[1])) if xy is not None else None
        cands = [(t, _tile_xy(t)) for t in fh]
        cands = [(t, xy) for (t, xy) in cands if xy is not None]
        if nearest is not None:
            cands.sort(key=lambda tx: hexgeo.distance(tx[1], _pos(nearest)))
        aim_t, aim_xy = cands[0]
        aim_id = _tid(aim_t)
        if aim_id is None:
            aim_id = board.id_at(aim_xy[0], aim_xy[1])
        print("[498/%s] aim = tuile %s (entite %s), %d cibles legales" % (
            label, aim_xy, aim_id, len(fh)))

        # ---------------------------------------------------------------- OFFLINE
        st = mkstate()
        h = _offline_cast(st, cid, aim_id, MOMENTUM)
        last = h.last or {}
        off_ported = bool(last.get("ported"))
        off_line = (last.get("res") or last).get("line") if isinstance(last.get("res"), dict) else last.get("line")
        res_off = last.get("res") if isinstance(last.get("res"), dict) else last
        off_pos = {}
        for eid, e in st.entities.items():
            from engine.runner.components import PositionComponent, UnitComponent
            pc = e.get_component(PositionComponent)
            uc = e.get_component(UnitComponent)
            if pc is not None and uc is not None:
                off_pos[int(eid)] = (pc.col, pc.row)
        off_hp = {}
        from engine.runner.components import HealthComponent
        for eid, e in st.entities.items():
            hc = e.get_component(HealthComponent)
            if hc is not None:
                off_hp[int(eid)] = int(hc.hp)
        off_hits = _offline_per_hit(res_off)
        off_effects = {}
        if st.effects is not None:
            for uid, effs in st.effects.by_unit.items():
                off_effects[int(uid)] = sorted(int(x.effect_type) for x in effs if not x.consumed)

        # ---------------------------------------------------------------- LIVE
        live = _cast_live(sid, rid, cid, aim_id, MOMENTUM)
        dec1 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        live_pos = _positions(dec1)
        live_hp = _hp(dec1)
        live_hits = _live_per_hit(live, MOMENTUM)
        live_effects = _effects_by_unit(dec1)

        # ---------------------------------------------------------------- E1 CABLAGE
        print("\n[498/%s] E1 CABLAGE -- ported=%s (offline), live ok=%s mutated=%s" % (
            label, off_ported, live.get("ok"), live.get("mutated")))
        if not off_ported:
            _msg = ("[498/%s] ECHEC E1 : le port declare `ported=False` (no-op silencieux)" % label)
            print(_msg)
            fails.append(_msg)
        if not live.get("ok"):
            _msg = ("[498/%s] ECHEC E1 : le cast LIVE a echoue -- %s" % (label, live))
            print(_msg)
            fails.append(_msg)

        # ---------------------------------------------------------------- E2 TRAJET
        print("[498/%s] E2 TRAJET -- caster : depart %s | offline %s | live %s" % (
            label, cpos, off_pos.get(cid), live_pos.get(cid)))
        print("[498/%s]    ligne de charge portee = %s | pas joues = %s" % (
            label, off_line, res_off.get("steps")))
        if off_pos.get(cid) != live_pos.get(cid):
            _msg = ("[498/%s] ECHEC E2 : position finale du caster DIVERGENTE" % label)
            print(_msg)
            fails.append(_msg)

        # ---------------------------------------------------------------- E3 DEGAT/CIBLE
        print("[498/%s] E3 DEGAT -- offline %s" % (label, off_hits))
        print("[498/%s]            live     %s" % (label, live_hits))
        # NON DEGENERESCENCE du regime : on IMPRIME les drapeaux crit/block, cote port ET cote
        # natif. Un accord sur un regime ou personne ne crit ni ne bloque ne prouverait rien.
        for at in (res_off.get("attacks") or []):
            atk = at.get("attack") or {}
            print("[498/%s]    (off) u%s did_crit=%s did_block=%s crits=%s rolls=%s" % (
                label, at.get("target"), atk.get("did_crit"), atk.get("did_block"),
                atk.get("crits"), atk.get("rolls")))
        for tg in _live_tags(live, MOMENTUM):
            print("[498/%s]    (live tags) %s" % (label, json.dumps(tg, sort_keys=True)))
        if set(off_hits) != set(live_hits):
            _msg = ("[498/%s] ECHEC E3 : ensembles de cibles touchees DIVERGENTS" % label)
            print(_msg)
            fails.append(_msg)
        else:
            for t in sorted(off_hits):
                if list(off_hits[t]) != list(live_hits[t]):
                    _msg = ("[498/%s] ECHEC E3 : cible u%d -- coups offline %s != live %s" % (
                        label, t, off_hits[t], live_hits[t]))
                    print(_msg)
                    fails.append(_msg)

        # ---------------------------------------------------------------- E4 SCALING per-hex
        steps_by_target = {int(a["target"]): int(a.get("steps") or 0)
                           for a in (res_off.get("attacks") or []) if a.get("target") is not None}
        extra_by_target = {int(a["target"]): int(a.get("extra_dmg") or 0)
                           for a in (res_off.get("attacks") or []) if a.get("target") is not None}
        print("[498/%s] E4 SCALING -- pas par cible %s | terme extraDmg %s" % (
            label, steps_by_target, extra_by_target))
        if len(steps_by_target) >= 2:
            ks = sorted(steps_by_target.items(), key=lambda kv: kv[1])
            (t1, k1), (t2, k2) = ks[0], ks[-1]
            if k2 > k1:
                per_hex_1 = extra_by_target[t1] // max(1, k1) if k1 else None
                per_hex_2 = extra_by_target[t2] // k2
                d = extra_by_target[t2] - extra_by_target[t1]
                print("[498/%s]    ecart des termes = %d pour %d hex -> %d/hex "
                      "(temoin per-hex k1=%s)" % (label, d, k2 - k1, d // (k2 - k1), per_hex_1))
                if d <= 0:
                    _msg = ("[498/%s] ECHEC E4 : le terme per-hex ne CROIT pas avec le pas" % label)
                    print(_msg)
                    fails.append(_msg)
                if per_hex_2 is not None and d // (k2 - k1) != per_hex_2:
                    _msg = ("[498/%s] ECHEC E4 : le terme n'est pas LINEAIRE en le pas" % label)
                    print(_msg)
                    fails.append(_msg)
            else:
                print("[498/%s]    (une seule valeur de pas -- scaling non separe ici)" % label)
        else:
            print("[498/%s]    (moins de 2 cibles touchees -- scaling non separe ici)" % label)

        # ---------------------------------------------------------------- E5 EFFETS
        touched = sorted(set(off_hits) | set(live_hits))
        for t in touched:
            o = [e for e in off_effects.get(t, []) if e in (PINNED, STUNNED)]
            l = [e for e in live_effects.get(t, []) if e in (PINNED, STUNNED)]
            print("[498/%s] E5 EFFETS -- u%d : offline %s | live %s" % (label, t, o, l))
            if sorted(o) != sorted(l):
                _msg = ("[498/%s] ECHEC E5 : effets Pinned/Stunned DIVERGENTS sur u%d" % (label, t))
                print(_msg)
                fails.append(_msg)

        # ---------------------------------------------------------------- E6 DEPLACEMENT
        for t in touched:
            print("[498/%s] E6 PUSH -- u%d : offline %s | live %s" % (
                label, t, off_pos.get(t), live_pos.get(t)))
            if off_pos.get(t) != live_pos.get(t):
                _msg = ("[498/%s] ECHEC E6 : position finale de u%d DIVERGENTE" % (label, t))
                print(_msg)
                fails.append(_msg)

        # ---------------------------------------------------------------- E7 AMI EPARGNE
        # i2 : « Friendly units are also displaced, but take no damage or negative effects. » Le
        # natif n'attaque que `Enemies(Caster@0x48, Units(Get(tile)), 3)` -- un AMI traverse par la
        # charge doit donc BOUGER sans prendre ni coup ni `Pinned`/`Stunned`. Cet etage se joue a
        # TOUTES les phases (il est vide quand aucun ami n'est sur la ligne) : c'est ce qui le rend
        # non-degenere quand la phase `allie` en pose un.
        friends = [int(u["id"]) for u in _alive(dec0)
                   if u.get("ctrl") and int(u["id"]) != cid]
        for f in friends:
            hit_off, hit_live = off_hits.get(f), live_hits.get(f)
            eff_off = [e for e in off_effects.get(f, []) if e in (PINNED, STUNNED)]
            eff_live = [e for e in live_effects.get(f, []) if e in (PINNED, STUNNED)]
            moved = (off_pos.get(f) != _positions(dec0).get(f))
            print("[498/%s] E7 AMI -- u%d : coups off=%s live=%s | effets off=%s live=%s | "
                  "pos %s -> %s (live %s)" % (label, f, hit_off, hit_live, eff_off, eff_live,
                                              _positions(dec0).get(f), off_pos.get(f),
                                              live_pos.get(f)))
            if hit_off or hit_live:
                _msg = ("[498/%s] ECHEC E7 : l'ami u%d a pris des DEGATS" % (label, f))
                print(_msg)
                fails.append(_msg)
            if eff_off or eff_live:
                _msg = ("[498/%s] ECHEC E7 : l'ami u%d a recu un effet NEGATIF" % (label, f))
                print(_msg)
                fails.append(_msg)
            if off_pos.get(f) != live_pos.get(f):
                _msg = ("[498/%s] ECHEC E7 : position finale de l'ami u%d DIVERGENTE" % (label, f))
                print(_msg)
                fails.append(_msg)
            if moved:
                print("[498/%s]    (ami DEPLACE par la charge -- temoin non degenere)" % label)

        # diagnostic HP (non bloquant -- E3 est l'etage qui juge ; le HP live d'une cible
        # `LivingMetal` REMONTE apres le cast : le cast TERMINE le tour du caster, donc le tour
        # adverse demarre et le trait regenere 10 % du max. Ce n'est pas un ecart de port.)
        for t in touched:
            print("[498/%s] (hp) u%d : offline %s | live %s" % (
                label, t, off_hp.get(t), live_hp.get(t)))
        J.update({
            "fails": fails, "ported": off_ported, "live_ok": bool(live.get("ok")),
            "caster": cid, "caster_from": cpos, "caster_off": off_pos.get(cid),
            "caster_live": live_pos.get(cid),
            "aim": aim_xy, "line": list(off_line or []), "steps": res_off.get("steps"),
            "off_hits": off_hits, "live_hits": live_hits,
            "steps_by_target": steps_by_target, "extra_by_target": extra_by_target,
            "touched": touched, "friends": friends,
            "off_effects": off_effects, "live_effects": live_effects,
            "off_pos": off_pos, "live_pos": live_pos, "pos_before": _positions(dec0),
            "crit_flags": [{"target": at.get("target"),
                            "did_crit": (at.get("attack") or {}).get("did_crit"),
                            "did_block": (at.get("attack") or {}).get("did_block")}
                           for at in (res_off.get("attacks") or [])],
        })
        return J
    finally:
        _dispose(state_path)


# --------------------------------------------------------------------------- montages (SOURCE UNIQUE)
#
# Chaque entree = les arguments EXACTS de `rl_duel build` d'une phase. C'est la SOURCE UNIQUE des
# montages : `main()` (CLI) ET `tests/engine/runner/test_unstoppable_momentum_live.py` (la garde)
# les lisent d'ici -- aucun des deux ne recopie un argument.
def montages(seed: int = 777) -> dict:
    return {
        # DEUX ennemis ALIGNES avec le caster sur l'axe (col constante, row croissant) : les pas
        # 0 et 1 de la charge sont donc tous deux OCCUPES -> l'etage E4 separe le per-hex.
        # `--hp-target` haut : personne ne meurt, la sequence de coups reste lisible de bout en bout.
        "ligne": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", CASTER_VISUAL,
            "--a-units", "ultraApothecary,necroWarden",
            "--place", "%s:3,2" % CASTER_VISUAL,
            "--a-place", "ultraApothecary:3,3", "--a-place", "necroWarden:3,4",
            "--hp-target", "90000",
        ],
        # UN BigTarget adjacent : `CanBeDisplaced` est FAUX -> branche `Stunned` (et non `Pinned`),
        # `IsDisplaceable` est FAUX -> `Push` rend false -> la charge S'ARRETE (i2 : « until he hits
        # an obstacle or a Big Target »). C'est le temoin qui separe les DEUX branches du `If`.
        "bigtarget": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", CASTER_VISUAL,
            "--a-units", "tyranTyrantGuard,ultraApothecary",
            "--place", "%s:3,2" % CASTER_VISUAL,
            "--a-place", "tyranTyrantGuard:3,3", "--a-place", "ultraApothecary:3,5",
            "--hp-target", "90000",
        ],
        # UN ALLIE au 2e pas, ENCADRE par deux ENNEMIS (pas 0 et pas 2). i2 : « Friendly units are
        # also displaced, but take no damage or negative effects. » -> l'allie DOIT etre pousse,
        # sans coup ni `Pinned` ; c'est le temoin du `Enemies(Caster@0x48, Units(Get(tile)), 3)` de
        # l'attaque. Sans lui, un port qui aurait oublie le `Enemies` passerait toutes les autres
        # phases. L'ami est au pas 2 et non au pas 0 parce que la tuile d'un AMI n'est PAS une cible
        # legale (`TargetTileIsFreeOrEnemy`) : l'aim doit designer un ENNEMI.
        "allie": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", "%s,ultraTitus" % CASTER_VISUAL,
            "--a-units", "ultraApothecary,necroWarden",
            "--place", "%s:3,2" % CASTER_VISUAL, "--place", "ultraTitus:3,4",
            "--a-place", "ultraApothecary:3,3", "--a-place", "necroWarden:3,5",
            "--hp-target", "90000", "--hp-player", "90000",
        ],
        # CRIT force a 100 % sur le caster : chaque coup de la charge DOIT etre critique. Face
        # `crit` du kit, isolee du reste (meme geometrie que `ligne` -- seule la stat change).
        "crit": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", CASTER_VISUAL,
            "--a-units", "ultraApothecary,necroWarden",
            "--place", "%s:3,2" % CASTER_VISUAL,
            "--a-place", "ultraApothecary:3,3", "--a-place", "necroWarden:3,4",
            "--hp-target", "90000", "--crit", "100,700",
        ],
        # BLOCK force a 100 % sur les CIBLES : chaque coup DOIT etre bloque. Face `block` du kit,
        # isolee a son tour -- et c'est le TEMOIN NON DEGENERE du crit (crit 0 / block 100).
        "block": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", CASTER_VISUAL,
            "--a-units", "ultraApothecary,necroWarden",
            "--place", "%s:3,2" % CASTER_VISUAL,
            "--a-place", "ultraApothecary:3,3", "--a-place", "necroWarden:3,4",
            "--hp-target", "90000", "--block-target", "100,500", "--crit", "0,0",
        ],
        # AUCUNE tuile de poussee disponible -> branche `SwitchPosition` de `$$Push` (qui rend
        # `true` : la charge CONTINUE sans `Move`, l'echange ayant deja porte le caster sur la
        # tuile). Montage : la cible est au COIN (0,0) -- ses seules voisines ON-BOARD hors
        # `Backward` sont (0,1) et (1,1), qu'on OCCUPE. Le caster charge depuis (1,0).
        "switch": [
            "--seed", str(seed), "--board", BOARD,
            "--p-units", CASTER_VISUAL,
            "--a-units", "ultraApothecary,necroWarden,ultraTitus",
            "--place", "%s:1,0" % CASTER_VISUAL,
            "--a-place", "ultraApothecary:0,0",
            "--a-place", "necroWarden:0,1", "--a-place", "ultraTitus:1,1",
            "--hp-target", "90000",
        ],
    }


PHASES = ("ligne", "bigtarget", "allie", "crit", "block", "switch")


def run(phase: str, seed: int = 777, state_file=None) -> dict:
    """UNE phase de bout en bout : build isole -> capture -> rejeu OFFLINE -> cast LIVE -> confront
    des 7 etages -> dispose du runner. Rend le JOURNAL structure decrit par `_run_phase`. C'est la
    porte d'entree du test de garde, qui ne re-derive RIEN."""
    sid = _resolve_session()
    root = Path(__file__).resolve().parents[2]
    base = Path(state_file) if state_file else (root / "logs" / "probe_498_state.json")
    base.parent.mkdir(parents=True, exist_ok=True)
    return _run_phase(sid, base.with_name("%s_%s.json" % (base.stem, phase)),
                      montages(seed)[phase], "tile", phase)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="ligne", choices=list(PHASES) + ["all"])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    phases = PHASES if a.phase == "all" else (a.phase,)
    journaux = [run(ph, a.seed, a.state_file) for ph in phases]
    n = sum(len(j.get("fails") or []) for j in journaux)
    print("\n[498] BILAN : %d echec(s) sur %d phase(s)" % (n, len(journaux)))
    return 0 if n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
