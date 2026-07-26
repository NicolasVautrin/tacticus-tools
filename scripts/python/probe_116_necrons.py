#!/usr/bin/env python
"""Probe #116 -- confront LIVE des 3 actives Necrons portees (lot 1) : ResurrectionOrb (1009),
Chronometron (1226), MultiThreatEliminator (1006).

Protocole commun (replay-diff) : on capture l'etat AVANT le cast (decisionView + observeBattle +
combatSnapshot + dumpRng), on rejoue le cast OFFLINE via le handler d'ability porte, on rejoue le MEME
cast LIVE (`applyAction`), puis on confronte l'observable.

  * `--phase orb`   : necroOverlord (SELF-cast 1009). Confronte le NOMBRE de summons spawnes
                      (offline `count` de `GetMaxSummonsFormula` == nb d'unites apparues live) et le
                      visualId du summon. Le cast est repete apres N endturns pour exercer le terme
                      `StatAmount(caster, TURNS_STARTED)` (le count DOIT croitre).
  * `--phase chrono`: necroChronomancer (hors seed BC -> `catalog_inject`), cast 1226. Confronte le SET
                      (unite -> effets poses) offline vs live : Pinned/Stunned + Chronometron_ExtraDamage
                      sur TOUS les ennemis du disque rayon `range`, et sur AUCUN autre.
  * `--phase mte`   : necroDestroyer, cast 1006 sur une cible fragile (`--hp-target`) avec un ennemi
                      ADJACENT a elle : confronte la CHAINE (liste des cibles touchees, dans l'ordre)
                      offline vs live (`UnitDamaged` par unite).

Cible du cast prise dans `abilityTargets(...).fromHere` (JAMAIS `targets` : superset move-inclus -> un
cast depuis la position courante y serait ILLEGAL et rendrait `mutated:false` = faux no-op, cf. #111).

ASCII only (cp1252). Usage :
    python probe_116_necrons.py --phase orb
    python probe_116_necrons.py --phase chrono
    python probe_116_necrons.py --phase mte
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
from engine.runner.snapshot import load_state                           # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.handler import AbilityHandler               # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,  # noqa: E402
                                      OwnerComponent, HealthComponent)

ROOT = PYDIR.parents[1]
RESURRECTION_ORB, CHRONOMETRON, MULTI_THREAT = 1009, 1226, 1006


# --------------------------------------------------------------------------- helpers RPC / runner

def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_path: Path, args_extra: list, retries: int = 40) -> int:
    """`rl_duel build`. Le plafond MAX_RUNNERS est PARTAGE entre agents : un `runner cap reached`
    n'est pas une erreur du probe mais une contention -> on ATTEND un slot au lieu d'abandonner (on ne
    dispose JAMAIS le runner d'un autre)."""
    for attempt in range(max(1, retries)):
        state_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)] + args_extra,
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if state_path.exists():
            return json.loads(state_path.read_text())["runnerId"]
        out = (proc.stderr or "") + (proc.stdout or "")
        if "runner cap reached" in out and attempt + 1 < retries:
            print(f"[116] runner cap atteint -- attente d'un slot ({attempt + 1}/{retries})",
                  flush=True)
            time.sleep(20)
            continue
        print("[116] build KO:", out[-800:])
        sys.exit(2)
    sys.exit(2)


def _dispose(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def _capture(sid, rid):
    """(mkstate, dec, board) -- `mkstate()` rebatit un etat OFFLINE neuf depuis les MEMES payloads."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec, board


def _from_here(sid, rid, caster, ability):
    """Cibles LEGALES SANS bouger (`abilityTargets(...).fromHere`) -- JAMAIS `targets` (#111)."""
    at = _r(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 120)
    for u in (at.get("units") or []):
        if int(u.get("unitId") or -1) != int(caster):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) == int(ability):
                return list(ab.get("fromHere") or []), list(ab.get("targets") or [])
    return [], []


def _tid(t):
    """id d'entite d'une entree de `fromHere`/`targets` (dict {unitId|entityId|id} ou int)."""
    if isinstance(t, dict):
        for k in ("unitId", "entityId", "id", "targetId"):
            if t.get(k) is not None:
                return int(t[k])
        return None
    return int(t)


def _aiturn(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def _move_toward_enemy(sid, rid, cid, dec):
    """DRIVE la position (doctrine : on deplace les unites pour realiser la condition testee, on ne
    subit pas la geometrie de spawn) : deplace `cid` sur la tuile LEGALE (`aiMovableTiles`) la plus
    proche de l'ennemi le plus proche."""
    import hexgeo
    me = next((u for u in _alive_units(dec) if int(u["id"]) == int(cid)), None)
    foes = [u for u in _alive_units(dec) if not u.get("ctrl")]
    if me is None or not foes:
        return False
    mp = me.get("pos") or {}
    src = (mp.get("col"), mp.get("row"))
    tgt = min(foes, key=lambda u: hexgeo.distance(
        src, ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))))
    tp = tgt.get("pos") or {}
    dest = (tp.get("col"), tp.get("row"))
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    tiles = []
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId") or -1) == int(cid):
            tiles = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
    if not tiles:
        return False
    best = min(tiles, key=lambda t: hexgeo.distance(t, dest))
    r = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(cid), "to": {"col": best[0], "row": best[1]}}}, 60)
    return bool(r.get("ok"))


def _advance_until_castable(sid, rid, state_path, visual, ability, max_turns=8):
    """Boucle {tenter le cast depuis ici -> sinon AVANCER -> sinon finir le tour + tour IA} jusqu'a
    obtenir une cible LEGALE `fromHere`. Rend (caster_id, fromHere)."""
    cid = None
    for _ in range(max_turns):
        dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u = _unit_of(dec, visual)
        if u is None:
            return None, []
        cid = int(u["id"])
        fh, _tg = _from_here(sid, rid, cid, ability)
        if fh:
            return cid, fh
        _move_toward_enemy(sid, rid, cid, dec)
        fh, _tg = _from_here(sid, rid, cid, ability)
        if fh:
            return cid, fh
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        _aiturn(state_path)
    return cid, []


def _cast_live(sid, rid, caster, target, ability, capture_events: bool = False):
    body = {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(caster), "targetId": int(target),
        "abilityType": int(ability)}}
    if capture_events:
        body["captureEvents"] = True
    return _r(sid, "applyAction", body, 120)


def _live_per_hit(res, ability, dump_zero=False):
    """{target_id -> [degat par COUP]} depuis les events d'`applyAction(captureEvents)`. Un event de
    degat portant `Active_Ability_Type == ability` == UN coup APPLIQUE (meme oracle que #61).
    `dump_zero` imprime les TAGS BRUTS des events a `Amount == 0` : ils sont ambigus (coup tombe sur un
    cadavre ? marqueur de mort ?) et la difference change le nb de coups qu'on prete au natif."""
    out: dict = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability):
                out.setdefault(int(td.get("Target_Id")), []).append(td.get("Amount"))
                if dump_zero and not td.get("Amount"):
                    print(f"[mte] EVENT Amount=0 tags={json.dumps(td, sort_keys=True)}")
    return out


def _alive_units(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _unit_of(dec, visual):
    for u in _alive_units(dec):
        if u.get("visualId") == visual or u.get("unitId") == visual:
            return u
    return None


def _effects_by_unit(dec):
    """{unitId -> [(effectType, remaining)]} depuis `decisionView` (les effets sont NICHES par unite,
    il n'y a PAS de liste `effects` au niveau racine)."""
    out: dict = {}
    for u in (dec.get("units") or []):
        out[int(u.get("id"))] = sorted((int(e.get("effectType") or -1), int(e.get("remaining") or 0))
                                       for e in (u.get("effects") or []))
    return out


def _offline_cast(state, caster, target, ability):
    """Rejoue le cast OFFLINE via le CHEMIN REEL (`AbilityHandler.visit_ActiveAbilityMessage`)."""
    from engine.runner.messages import ActiveAbilityMessage
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=int(target), ability_type=int(ability)))
    return h.last or {}


# --------------------------------------------------------------------------- phase ORB (1009)

def phase_orb(args):
    st_file = Path(args.state_file or (ROOT / "data" / "_116_orb_state.json"))
    sid = _resolve_session()
    rid = _build(st_file, ["--seed", str(args.seed), "--board", "MC1_67", "--rank", "17",
                           "--p-units", "necroOverlord,necroDestroyer",
                           "--a-units", "eldarRanger,astraBullgryn", "--no-ai",
                           "--hp-player", "60000", "--hp-target", "60000"])
    print(f"[orb] runner={rid} session={sid}")
    try:
        for round_idx in range(args.rounds):
            mkstate, dec, board = _capture(sid, rid)
            overlord = _unit_of(dec, "necroOverlord")
            if overlord is None:
                print("[orb] necroOverlord absent"); return 2
            cid = int(overlord["id"])
            fh, tg = _from_here(sid, rid, cid, RESURRECTION_ORB)
            print(f"[orb] round={round_idx} caster=u{cid} fromHere={fh} targets={tg}")
            if not fh:
                print("[orb] AUCUNE cible legale fromHere -> endturn");
            else:
                tid = _tid(fh[0])
                st = mkstate()
                diag = _offline_cast(st, cid, tid, RESURRECTION_ORB)
                off_count = diag.get("count")
                off_spawned = diag.get("spawned") or []
                before = {int(u["id"]) for u in _alive_units(dec)}
                res = _cast_live(sid, rid, cid, tid, RESURRECTION_ORB)
                dec2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
                after = _alive_units(dec2)
                new = [u for u in after if int(u["id"]) not in before]
                print(f"[orb] OFFLINE ported={diag.get('ported')} count={off_count} "
                      f"spawned={len(off_spawned)}")
                print(f"[orb] LIVE     ok={res.get('ok')} mutated={res.get('mutated')} "
                      f"new={[ (u['id'], u.get('visualId')) for u in new ]}")
                # L'OBSERVABLE est le nombre de summons REELLEMENT poses : le `count` de
                # `GetMaxSummonsFormula` est un PLAFOND que le `CanAddUnit(AdjacentTiles(caster))`
                # peut brider (hexes adjacents deja occupes par les Warriors des rounds precedents).
                print(f"[orb] VERDICT spawns offline={len(off_spawned)} live={len(new)} "
                      f"(formule count={off_count}) -> "
                      f"{'OK' if len(off_spawned) == len(new) else 'MISMATCH'}")
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    finally:
        if not args.keep:
            _dispose(st_file)
    return 0


# --------------------------------------------------------------------------- phase CHRONO (1226)

def phase_chrono(args):
    st_file = Path(args.state_file or (ROOT / "data" / "_116_chrono_state.json"))
    bc_file = ROOT / "data" / "_116_chrono_bc.json"
    # Le porteur `necroChronomancer` est HORS du seed BC capture -> injection dans les DEUX catalogues
    # (BC.Units ET BC.Abilities, cf. case-92). Les `--a-units` sont injectees aussi : ca permet de mettre
    # un porteur du trait `Summon` en face (branche `Stunned` du If natif).
    subprocess.run([sys.executable, "catalog_inject.py", "--units",
                    "necroChronomancer," + args.a_units, "--out", str(bc_file)],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not bc_file.exists():
        print("[chrono] catalog_inject KO"); return 2
    sid = _resolve_session()
    rid = _build(st_file, ["--seed", str(args.seed), "--board", "MC1_67", "--rank", "17",
                           "--seed-bc", str(bc_file),
                           "--p-units", "necroChronomancer,necroOverlord",
                           "--a-units", args.a_units,
                           "--hp-player", "90000", "--hp-target", "90000"])
    print(f"[chrono] runner={rid} session={sid}")
    try:
        # `--pre-turns` : laisse tourner N tours AVANT d'approcher -- le temps qu'un SUMMONER adverse
        # (ex. `necroSpyder`) pose ses invoques, pour exercer la branche `Stunned` (trait Summon).
        for _ in range(args.pre_turns):
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            _aiturn(st_file)
        cid, fh = _advance_until_castable(sid, rid, st_file, "necroChronomancer", CHRONOMETRON)
        print(f"[chrono] caster=u{cid} fromHere={fh}")
        if not fh:
            print("[chrono] AUCUNE cible legale fromHere apres avance"); return 3
        mkstate, dec, board = _capture(sid, rid)
        tid = _tid(fh[0])
        st = mkstate()
        diag = _offline_cast(st, cid, tid, CHRONOMETRON)
        off = {}
        for e in (diag.get("effects") or []):
            off.setdefault(int(e["target"]), []).append(int(e["effect_type"]))
        # duree OFFLINE relue de l'etat d'effets (== `remaining` live)
        off_rem = {}
        for uid, effs in (st.effects.by_unit.items() if st.effects is not None else []):
            for ef in effs:
                if ef.consumed:
                    continue
                off_rem.setdefault(int(uid), []).append(
                    (int(ef.effect_type), int(getattr(ef, "remaining_turns", None)
                                              or getattr(ef, "turns_left", None) or 0)))
        eff_before = _effects_by_unit(dec)
        res = _cast_live(sid, rid, cid, tid, CHRONOMETRON)
        dec2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        eff_after = _effects_by_unit(dec2)
        live_new = {}
        for uid, cur in eff_after.items():
            b = list(eff_before.get(uid) or [])
            delta = [x for x in cur if x not in b or cur.count(x) > b.count(x)]
            if delta:
                live_new[uid] = sorted(delta)
        off_new = {k: sorted(v) for k, v in off.items()}
        print(f"[chrono] OFFLINE ported={diag.get('ported')} range={diag.get('range')} "
              f"rounds={diag.get('rounds')} effets={off_new}")
        print(f"[chrono] LIVE ok={res.get('ok')} nouveaux (type,remaining)={live_new}")
        same_units = set(off_new) == set(live_new)
        same_types = all(sorted(off_new.get(u, [])) == sorted(t for t, _r2 in live_new.get(u, []))
                         for u in set(off_new) | set(live_new))
        # duree : compare le `remaining` de CHAQUE type pose, offline vs live
        dur_ok = True
        for uid, pairs in live_new.items():
            for et, rem in pairs:
                orem = [r2 for t2, r2 in (off_rem.get(uid) or []) if t2 == et]
                if not orem or orem[0] != rem:
                    dur_ok = False
                    print(f"[chrono]   duree u{uid} effet {et}: offline={orem} live={rem}")
        print(f"[chrono] VERDICT unites={'OK' if same_units else 'MISMATCH'} "
              f"types={'OK' if same_types else 'MISMATCH'} durees={'OK' if dur_ok else 'MISMATCH'}")
        # BRANCHE `Stunned` (`If(HasTrait(It, Summon), ...)`) : aucun porteur du trait `Summon` ENNEMI
        # n'est spawnable directement (`rl_duel build` refuse les ids `units.summons`) et les summoners
        # adverses n'invoquent pas de facon deterministe -> confront OFFLINE (le trait est la SEULE
        # variable : meme etat, meme cast, on ajoute `Summon` aux ennemis).
        st2 = mkstate()
        for _eid, _e in st2.entities.items():
            from engine.runner.components import StatsComponent as _SC
            _sc = _e.get_component(_SC)
            if _sc is not None and getattr(_sc.ctx, "traits", None) is not None:
                _sc.ctx.traits = set(_sc.ctx.traits) | {"Summon"}
        diag2 = _offline_cast(st2, cid, tid, CHRONOMETRON)
        types2 = sorted({int(e["effect_type"]) for e in (diag2.get("effects") or [])})
        print(f"[chrono] BRANCHE Summon (offline, trait force) -> types poses={types2} "
              f"(attendu [1162, 1550] = Stunned au lieu de Pinned) "
              f"-> {'OK' if types2 == [1162, 1550] else 'MISMATCH'}")
    finally:
        if not args.keep:
            _dispose(st_file)
    return 0


# --------------------------------------------------------------------------- phase MTE (1006)

def phase_mte(args):
    st_file = Path(args.state_file or (ROOT / "data" / "_116_mte_state.json"))
    sid = _resolve_session()
    # `--hp-player` (defaut : celui de `rl_duel build`) : monter les PV du CASTER retire le confond
    # « le caster MEURT de la reaction adverse (Overwatch / WireweaveNet_CounterAttack) pendant la
    # chaine » — un acteur mort rend l'attaque NO-OP (#70) et fausse la lecture des maillons (#122).
    _hp_player = ["--hp-player", str(args.hp_player)] if args.hp_player else []
    rid = _build(st_file, ["--seed", str(args.seed), "--board", "MC1_67", "--rank", "17",
                           "--p-units", "necroDestroyer",
                           "--a-units", args.a_units,
                           "--hp-target", str(args.hp_target), "--crit", "0,0"] + _hp_player)
    print(f"[mte] runner={rid} session={sid}")
    try:
        # rapproche le caster : on le laisse a sa place et on DEPLACE les ennemis a portee 2
        cid, fh = _advance_until_castable(sid, rid, st_file, "necroDestroyer", MULTI_THREAT)
        print(f"[mte] caster=u{cid} fromHere={fh}")
        if not fh:
            print("[mte] pas de cible legale sans bouger apres avance")
            return 3
        mkstate, dec, board = _capture(sid, rid)
        tid = _tid(fh[0])
        st = mkstate()
        hp_before = {eid: (e.get_component(HealthComponent).hp
                           if e.get_component(HealthComponent) else None)
                     for eid, e in st.entities.items()}
        diag = _offline_cast(st, cid, tid, MULTI_THREAT)
        off_chain = diag.get("chain") or []
        off_hp = {eid: (e.get_component(HealthComponent).hp
                        if e.get_component(HealthComponent) else None)
                  for eid, e in st.entities.items()}
        off_delta = {k: (hp_before[k] - off_hp[k]) for k in off_hp
                     if hp_before.get(k) is not None and off_hp[k] != hp_before[k]}
        # #122 CONTRE-CAS : meme etat, meme RNG, SEULE variable = le predicat `IsMeleeAttack` du canal
        # de coups. `legacy` = l'ancien calcul POSITIONNEL (adjacence) ; le port livre la nature
        # DECLAREE (`hits_channel_is_melee`). Si les deux chaines sont identiques, la mesure n'est PAS
        # discriminante et il ne faut rien en conclure.
        legacy_chain = []
        if args.counterfactual:
            import engine.runner.operations.damage_ops as _dops
            from engine.runner.operations.triggers.base import _is_ranged_position
            _keep = _dops.hits_channel_is_melee
            _dops.hits_channel_is_melee = (
                lambda state, a, t, is_melee: not _is_ranged_position(state, a, t))
            try:
                legacy_chain = (_offline_cast(mkstate(), cid, tid, MULTI_THREAT).get("chain") or [])
            finally:
                _dops.hits_channel_is_melee = _keep
        res = _cast_live(sid, rid, cid, tid, MULTI_THREAT, capture_events=True)
        live_ph = _live_per_hit(res, MULTI_THREAT, dump_zero=True)
        dec2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        # PV LIVE : `combatSnapshot` ne rend que les VIVANTS -> une unite du set de depart absente du
        # snapshot est MORTE (PV 0).
        snap2 = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        live_hp = {int(u.get("entityId")): int((u.get("stats") or {}).get("health") or 0)
                   for u in (snap2.get("units") or [])}
        for k in hp_before:
            live_hp.setdefault(int(k), 0)
        live_delta = {k: (hp_before[k] - v) for k, v in live_hp.items()
                      if hp_before.get(k) is not None and v != hp_before[k]}
        live_dead = sorted(k for k, v in live_hp.items() if v <= 0)
        off_dead = sorted(eid for eid, e in st.entities.items()
                          if (e.get_component(UnitComponent) is not None
                              and not e.get_component(UnitComponent).alive))
        print(f"[mte] OFFLINE ported={diag.get('ported')} chain={off_chain}")
        # #122 : decomposition PAR MAILLON. `base_hits` = ce que la chaine passe a l'Operation ;
        # `applied` = ce que la formule de coups partagee a retenu APRES les malus DEFENSEUR
        # (Camouflage/Parry/LightCover) -- les confondre fait lire un ecart de COUPS la ou il n'y a
        # qu'un ecart de DEGAT. `dist` = distance caster/cible (branche -1 vs -2 de Camouflage) ;
        # elle ne pilote PAS le gate melee/ranged, qui est DECLARE (`attackRangeType`).
        import hexgeo as _hg
        _pos = {int(u["id"]): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                for u in (dec.get("units") or []) if (u.get("pos") or {}).get("col") is not None}
        _cp = _pos.get(int(cid))
        _fx = _effects_by_unit(dec)
        _leg = {int(l.get("target")): l for l in legacy_chain}
        for _lnk in off_chain:
            _t = int(_lnk.get("target"))
            _d = _hg.distance(_cp, _pos[_t]) if (_cp and _pos.get(_t)) else None
            _lg = _leg.get(_t) or {}
            print(f"[mte] GEOM maillon u{_t} pos={_pos.get(_t)} dist(caster u{cid} @{_cp})={_d} "
                  f"base_hits={_lnk.get('hits')} OFF applied={_lnk.get('applied_hits')} "
                  f"per_hit={_lnk.get('per_hit')} | LIVE per_hit={live_ph.get(_t)} "
                  f"| LEGACY applied={_lg.get('applied_hits')} per_hit={_lg.get('per_hit')} "
                  f"| effets={_fx.get(_t)}")
        print(f"[mte] OFFLINE deltas PV = {off_delta} morts={off_dead}")
        print(f"[mte] LIVE ok={res.get('ok')} deltas PV = {live_delta} morts={live_dead}")
        print(f"[mte] LIVE hp_before={hp_before} hp_after={live_hp}")
        print(f"[mte] VERDICT set de cibles touchees offline={sorted(off_delta)} "
              f"live={sorted(live_delta)} -> "
              f"{'OK' if sorted(off_delta) == sorted(live_delta) else 'MISMATCH'}")
    finally:
        if not args.keep:
            _dispose(st_file)
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["orb", "chrono", "mte"])
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--hp-target", type=int, default=2000)
    ap.add_argument("--hp-player", type=int, default=0)   # phase mte : PV du caster (0 = defaut build)
    # phase mte : rejoue AUSSI la chaine offline avec l'ancien predicat POSITIONNEL du canal de coups
    # (contre-cas #122). Meme etat, meme RNG -- la seule variable est `IsMeleeAttack`.
    ap.add_argument("--counterfactual", action="store_true")
    # phase `chrono` : mettre un SUMMONER dans le camp adverse (ex. `necroSpyder`) exerce la branche
    # `If(HasTrait(It, Summon), AddEffect(Stunned), AddEffect(Pinned))` du natif.
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn,tauMarksman")
    ap.add_argument("--pre-turns", type=int, default=0)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    return {"orb": phase_orb, "chrono": phase_chrono, "mte": phase_mte}[a.phase](a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
