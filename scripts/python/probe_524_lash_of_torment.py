"""#524 -- `LashOfTorment` (ActiveAbilityType 1196, `emperLucius` << Lucius >>).

MESURE, pas garde. Le porteur est un HERO `lineup` HORS du pool spawnable ET hors catalogue -> il
est INJECTE (`catalog_inject.write_augmented_seed_bc`), meme recette que `astarCyrus` (#511).

L'arbre natif (`IdunBattleLogic.Entities.Abilities.Active.Loki.LashOfTormentAbility$$
ExecuteBehaviour`) a TROIS volets, confrontes un par un :

  --step damage : l'ATTAQUE (`nrOfHits` = 6 coups Eviscerate). Sequence COUP PAR COUP (un total
                  juste peut masquer deux erreurs qui se compensent) + nombre de tirages rng.
                  MT offline cale sur `dumpRng` AVANT le cast.
  --step pull   : le `PullUnitOneTile(Caster, Target, elevationKnockback NUL)`. Deux regimes,
                  et ils sont OPPOSES :
                    * cible a distance 2 -> elle AVANCE d'un hex vers Lucius, aucun knockback ;
                    * cible DEJA ADJACENTE -> l'arc AVANT se reduit a la tuile du CASTER,
                      `IsFilled` -> aucun deplacement mais un `ApplyKnockbackTo(caster, target)`.
                  Le second regime n'est PAS dans l'i2 : c'est le quirk lu au decompile.
  --step taunt  : le bond `27 Taunted_OnlySpecificTargets` -- pose SSI la cible est ADJACENTE
                  APRES le pull, bonde au CASTER, `TurnsFromRounds(nrOfRounds)`. L'ABSENCE d'un
                  evenement ne prouve rien : on tranche par la LISTE D'EFFETS des deux cotes, et
                  on exerce les DEUX branches du `If` (adjacente / hors de portee du pull).

Sortie ASCII (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hexgeo                                                          # noqa: E402
import stream_events as SE                                            # noqa: E402

#: Resolu PAR NOM contre `enums.tsv` du build courant, jamais ecrit en ordinal : un membre retire
#: en amont decale tout ce qui suit, et le filtre lit alors le pas VOISIN sans erreur ni trace
#: (cliquet `tests/test_step_ordinal_ratchet_offline.py`).
S_UNIT_DAMAGED = SE.step_id("UnitDamaged")

CASTER = "emperLucius"             # HERO `lineup` HORS seed BC -> catalog_inject
ABILITY = 1196                     # ActiveAbilityType.LashOfTorment
TAUNT = 27                         # EffectType.Taunted_OnlySpecificTargets (COMPOSITE 25/26/1237)
TAUNT_CHILDREN = (25, 26, 1237)
DEFAULT_BOARD = "MC1_67"
RANGE = 2                          # gameconfig `constants.range`


# --------------------------------------------------------------------------- transport live

def _host():
    import rl_collect_batch as R
    return R


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mk_rpc(R, sid):
    def _call(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(board: str, seed: str, allie: str, ennemis: str, hp_target=None, crit=None) -> tuple:
    """`rl_duel build` avec `emperLucius` injecte. Rend `(rid, state_path)`.

    `hp_target` = `--hp-target` : PV des `a-units`, le levier qui rend le kill DETERMINISTE (regime
    << la cible meurt du cast >>, cf. `--step taunt-dead`)."""
    import subprocess
    import catalog_inject
    pyd = Path(__file__).resolve().parent
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    tag = uuid.uuid4().hex[:8]
    bc = tmp / ("lot-bc-%s.json" % tag)
    state = tmp / ("lot-state-%s.json" % tag)
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--seed-bc", str(bc), "--board", board,
            "--rank", "17", "--no-ai",
            "--p-units", "%s,%s" % (CASTER, allie), "--a-units", ennemis]
    if hp_target:
        argv += ["--hp-target", str(hp_target)]
    # `--crit "0,0"` ETEINT le canal crit du caster : c'est la DECOMPOSITION PAR ETAGE du residu
    # #524-r2 -- si le desaccord du 2e cast survit a crit=0, il n'est PAS dans le canal crit.
    if crit:
        argv += ["--crit", str(crit)]
    p = subprocess.run(argv, cwd=str(pyd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-800:]))
    return json.loads(state.read_text())["runnerId"], state


# --------------------------------------------------------------------------- lecture d'etat

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dv, vis):
    return next((u for u in _units(dv) if (u.get("visualId") or "") == vis), None)


def _by_id(dv, uid):
    return next((u for u in _units(dv) if u.get("id") == uid), None)


def _hp(ob, uid):
    """`observeBattle` indexe ses unites par `squadId`, PAS par `id` (cf. probe_511)."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _effects(dv, uid):
    for u in _units(dv):
        if u.get("id") == uid:
            return sorted(e.get("effectType") for e in (u.get("effects") or [])
                          if isinstance(e, dict) and e.get("effectType") is not None)
    return None


def _effets_bruts(dv, uid):
    for u in _units(dv):
        if u.get("id") == uid:
            return list(u.get("effects") or [])
    return []


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _montants_natifs(res):
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des events `action` du pas
    `UnitDamaged`)."""
    import json as _j
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != S_UNIT_DAMAGED:
                continue
            try:
                t = _j.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Amount" in t:
                out.append((t.get("Amount"), t.get("Attack_DidCrit"), t.get("Attack_DidBlock")))
    return out


def _events_bruts(res, brut=False):
    noms = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            noms.append(e if brut else (e.get("kind") or e.get("type") or "?"))
    return noms


def _capture(rpc, rid, board):
    from engine.runner.snapshot import load_state
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        raise SystemExit("capture live KO -- montage non installe")
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    return dv, ob, st, snap


def _crit_live(snap, uid):
    """Le CRIT du caster tel que le LIVE le publie (`combatSnapshot`) -- l'etage a decomposer quand
    une SEQUENCE diverge par ses drapeaux de crit et pas par ses montants."""
    for u in ((snap or {}).get("units") or []):
        if u.get("id") == uid or u.get("squadId") == uid:
            return {k: u.get(k) for k in ("critChance", "critDamage", "critChanceReduction",
                                          "blockChance", "blockDamage") if k in u}
    return None


class _MTCompteur:
    """Le MT du port, avec un COMPTEUR DE TIRAGES (cf. probe_511 : `mti` est CYCLIQUE)."""

    _cls = None

    def __new__(cls):
        if cls._cls is None:
            from engine.runner.prng import IntBasedMersenneTwister

            class _MT(IntBasedMersenneTwister):
                __slots__ = ("tirages",)

                def __init__(self):
                    super().__init__()
                    self.tirages = 0

                def genrand_int32(self):
                    self.tirages += 1
                    return super().genrand_int32()

            cls._cls = _MT
        return cls._cls()


def _cale_mt(rpc, rid, st):
    """CALER le MT offline sur le MT LIVE avant toute comparaison de degat."""
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s):
        raise SystemExit("dumpRng KO -- MT non calable")
    rng = _MTCompteur()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    st.rng = rng
    return rng


def _drive_a_distance(rpc, rid, dmin=1, dmax=RANGE, tours=12, exclus=()):
    """DEPLACE Lucius jusqu'a avoir une cible a distance dans `[dmin, dmax]` (doctrine
    drive-positions : on ne se plaint JAMAIS de la geometrie de spawn). Rend `(lucius, cible)`.

    `dmin`/`dmax` sont ce qui separe les DEUX regimes du pull : `2..2` = cible NON adjacente (le
    pull DEPLACE), `1..1` = cible DEJA adjacente (le pull ne deplace pas mais KNOCKBACK)."""
    for _ in range(tours):
        dv = _vue(rpc, rid)
        me = _by_vis(dv, CASTER)
        if me is None:
            return None, None
        if dv.get("currentPlayer") != me.get("owner"):
            _act(rpc, rid, {"kind": "endturn"}, 60)
            continue
        ennemis = [u for u in _units(dv)
                   if u.get("owner") != me.get("owner") and u.get("id") not in exclus]
        if not ennemis:
            return None, None
        tgt = min(ennemis, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if dmin <= hexgeo.distance(_pos(me), _pos(tgt)) <= dmax:
            return me, tgt
        tiles = _movable(rpc, rid, me["id"])
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if dmin <= hexgeo.distance(p, tp) <= dmax else 1,
                                             abs(hexgeo.distance(p, tp) - dmax)))
            _act(rpc, rid, {"kind": "move", "unitId": me["id"],
                            "to": {"col": best[0], "row": best[1]}}, 60)
        else:
            _act(rpc, rid, {"kind": "endturn"}, 60)
    return None, None


def _port_effets(st, uid):
    """Les `effect_type` que le PORT porte sur `uid` -- `EffectsState.by_unit`, la MEME source que
    `runner/components.py::has_effect_of_type` (indexee par ENTITE PORTEUSE)."""
    eff = getattr(st, "effects", None)
    if eff is None:
        return []
    return sorted(int(getattr(x, "effect_type", -1))
                  for x in (eff.by_unit.get(int(uid), []) or []))


# --------------------------------------------------------------------------- etapes

def step_damage(board, seed, allie, ennemis, casts, dmin, dmax):
    """VOLET 1 -- l'attaque : sequence COUP PAR COUP et compteur de tirages."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        mesures = 0
        vues: set = set()
        for n in range(casts):
            me, tgt = _drive_a_distance(rpc, rid, dmin, dmax, exclus=tuple(vues))
            if me is None or tgt is None:
                print("cast#%d : plus de configuration jouable -- arret" % n)
                break
            cid, tid = me["id"], tgt["id"]
            d0 = hexgeo.distance(_pos(me), _pos(tgt))
            dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
            if st.get_entity(cid) is None:
                print("cast#%d : caster absent de l'etat offline -- arret" % n)
                break
            rng = _cale_mt(rpc, rid, st)
            avant = {u["id"]: _hp(ob0, u["id"]) for u in _units(dv0)}
            tirages_avant = rng.tirages
            mti_avant = rng.mti

            res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                                  "abilityType": ABILITY})
            a0 = ((res or {}).get("actions") or [{}])[0]
            if not (a0.get("ok") and a0.get("mutated")):
                print("cast#%d : cast REFUSE par le natif (%r) -- arret" % (n, a0))
                rc = 1
                break
            ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
            live = {u: (avant[u] - _hp(ob2, u)) for u in avant
                    if avant.get(u) is not None and _hp(ob2, u) is not None
                    and avant[u] != _hp(ob2, u)}

            runner = Runner(st).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
            diag = runner.ability_handler.last or {}
            off = {}
            for uid in avant:
                e = st.get_entity(uid)
                hc = e.get_component(HealthComponent) if e is not None else None
                if hc is not None and avant[uid] is not None and avant[uid] != hc.hp:
                    off[uid] = avant[uid] - hc.hp
            res_port = diag   # `AbilityHandler.last` = {ability_type, ported, caster, target, **diag}
            atk = res_port.get("main_attack") or {}
            print("cast#%d caster=%s target=%s dist=%s  hp_live_avant=%s"
                  % (n, cid, tid, d0, avant.get(tid)))
            print("   ported=%s  bornes port=%s..%s  armure=%s  coups=%s  rounds=%s"
                  % (diag.get("ported"), atk.get("base_min"), atk.get("base_max"),
                     atk.get("armor"), atk.get("hits"), res_port.get("nr_of_rounds")))
            print("   deltas HP  live=%s  port=%s  %s"
                  % (live, off, "ACCORD" if live == off else "DESACCORD"))
            print("   SEQUENCE  port=%s" % (atk.get("per_hit"),))
            print("   SEQUENCE natif=%s" % (_montants_natifs(res),))
            print("   crits port=%s ; CRIT live caster=%s cible=%s ; effets caster=%s cible=%s"
                  % (atk.get("crits"), _crit_live(snap0, cid), _crit_live(snap0, tid),
                     _effects(dv0, cid), _effects(dv0, tid)))
            print("   tirages rng consommes (port) = %d" % (rng.tirages - tirages_avant))
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if _ok(s1):
                same_mt = (list(s1.get("mt") or []) == list(rng.mt)) and s1.get("mti") == rng.mti
                print("   MT : mti avant=%s ; apres -> natif=%s (%+d) port=%s (%+d) ; egaux ? %s"
                      % (mti_avant, s1.get("mti"), (s1.get("mti") or 0) - mti_avant,
                         rng.mti, rng.mti - mti_avant, same_mt))
            if os.environ.get("LOT_DUMP"):
                for e in _events_bruts(res, brut=True):
                    print("      EV %r" % (e,))
            if live != off or diag.get("ported") is not True:
                rc = 1
            if not live:
                print("   !! AUCUN delta HP live -- temoin NUL, la comparaison ne prouve rien")
                rc = 1
            mesures += 1
            vues.add(tid)
            _act(rpc, rid, {"kind": "endturn"}, 60)
        print("MESURES: %d" % mesures)
        if mesures == 0:
            rc = 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_pull(board, seed, allie, ennemis, dmin, dmax):
    """VOLET 2 -- le pull, et le COMPTE DES TIRAGES PAR ETAGE (#524-r2).

    `dmin/dmax` choisissent le regime, et les deux regimes sont EXCLUSIFS l'un de l'autre :

        2..2 -> le pull DEPLACE, `ApplyKnockbackTo` n'est PAS atteint
        1..1 -> le pull ne deplace pas (arc AVANT = la tuile du caster, OCCUPEE),
                et la branche `else` de la queue commune appelle `ApplyKnockbackTo`

    C'est le regime DISCRIMINANT de la piste << le natif consomme un tirage de plus des que le
    knockback tire >>. Elle se COMPTE : on decoupe les tirages du port en {attaque, pull} en
    enveloppant `PullUnitOneTileOperation.execute`, et on lit le total natif au delta de `mti`.
    Si `port_attaque == natif_total` sans knockback et `port_attaque == natif_total - 1` avec,
    le tirage manquant est DANS le knockback."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent, PositionComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_distance(rpc, rid, dmin, dmax)
        if me is None or tgt is None:
            print("aucune configuration a distance [%s,%s] -- NON CONFRONTE" % (dmin, dmax))
            return 1
        cid, tid = me["id"], tgt["id"]
        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        rng = _cale_mt(rpc, rid, st)
        mti_avant = rng.mti
        pos_caster = _pos(_by_id(dv0, cid))
        pos_avant = _pos(_by_id(dv0, tid))
        d0 = hexgeo.distance(pos_caster, pos_avant)
        hp_avant = _hp(ob0, tid)

        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("cast REFUSE par le natif (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        # DECOUPE DES TIRAGES DU PORT PAR ETAGE : on enveloppe l'Operation de pull et on lit le
        # compteur du MT autour d'elle. `PullUnitOneTileOperation` couvre TOUTE la queue commune
        # d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute` (choix de tuile, deplacement,
        # `ApplyKnockbackTo`) -- c'est exactement l'etage qu'on suspecte.
        from engine.runner.operations.displace import PullUnitOneTileOperation as _PULL
        _orig_pull = _PULL.execute
        _pull_draws = []

        def _pull_traced(self, state, bus):
            avant = rng.tirages
            out = _orig_pull(self, state, bus)
            _pull_draws.append(rng.tirages - avant)
            return out
        _PULL.execute = _pull_traced
        tirages_avant_cast = rng.tirages
        try:
            runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        finally:
            _PULL.execute = _orig_pull
        diag = runner.ability_handler.last or {}
        res_port = diag   # `AbilityHandler.last` = {ability_type, ported, caster, target, **diag}
        port_total = rng.tirages - tirages_avant_cast
        port_pull = sum(_pull_draws)

        dv1 = _vue(rpc, rid)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
        u1 = _by_id(dv1, tid)
        pos_apres_nat = _pos(u1) if u1 is not None else None
        e = st.get_entity(tid)
        pc = e.get_component(PositionComponent) if e is not None else None
        hc = e.get_component(HealthComponent) if e is not None else None
        pos_apres_port = (pc.col, pc.row) if pc is not None else None
        d_nat = (hexgeo.distance(pos_caster, pos_apres_nat)
                 if pos_apres_nat and pos_apres_nat[0] is not None else None)
        d_port = hexgeo.distance(pos_caster, pos_apres_port) if pos_apres_port else None
        print("REGIME dist AVANT = %s (caster=%s cible=%s)" % (d0, pos_caster, pos_avant))
        print("  position cible APRES : natif=%s (d=%s) ; port=%s (d=%s) ; %s"
              % (pos_apres_nat, d_nat, pos_apres_port, d_port,
                 "ACCORD" if pos_apres_nat == pos_apres_port else "DESACCORD"))
        print("  pull (port) = %s" % (res_port.get("pull"),))
        print("  HP cible : avant=%s ; natif=%s ; port=%s ; deltas natif=%s port=%s"
              % (hp_avant, _hp(ob1, tid), (hc.hp if hc is not None else None),
                 (hp_avant or 0) - (_hp(ob1, tid) or 0),
                 (hp_avant or 0) - (hc.hp if hc is not None else 0)))
        print("  SEQUENCE natif=%s" % (_montants_natifs(res),))
        ok = (pos_apres_nat == pos_apres_port
              and (_hp(ob1, tid) == (hc.hp if hc is not None else None)))
        # TEMOIN NON NUL : un ACCORD en regime degenere ne prouve rien.
        bouge = (pos_apres_nat != pos_avant)
        print("  la cible a-t-elle BOUGE (natif) ? %s" % bouge)

        # --- LE COMPTE, par etage. ------------------------------------------------------------
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        nat_total = None
        if _ok(s1):
            # `mti` est CYCLIQUE (0..624) : une difference brute peut etre NEGATIVE et ne compte
            # rien. On rend le compte SEULEMENT quand les deux restent dans le meme bloc.
            d = (s1.get("mti") or 0) - mti_avant
            nat_total = d if d >= 0 else None
        knock = (res_port.get("pull") or {}).get("knockback")
        print("  TIRAGES  port total=%d  dont pull=%d  -> attaque=%d ; natif total=%s"
              % (port_total, port_pull, port_total - port_pull, nat_total))
        print("  knockback (port) = %s ; MT egaux ? %s"
              % (knock,
                 _ok(s1) and list(s1.get("mt") or []) == list(rng.mt) and s1.get("mti") == rng.mti))
        if nat_total is not None:
            print("  DELTA natif-port = %+d  (regime %s knockback)"
                  % (nat_total - port_total, "AVEC" if knock else "SANS"))
        print("VERDICT PULL: %s" % ("ACCORD" if ok else "DESACCORD"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_taunt(board, seed, allie, ennemis, dmin, dmax):
    """VOLET 3 -- le bond 27. L'ABSENCE d'un evenement ne prouve rien : on lit la LISTE d'effets
    des DEUX cotes, et on exerce les deux branches du `If(IsAdjacent, bond)`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_distance(rpc, rid, dmin, dmax)
        if me is None or tgt is None:
            print("aucune configuration a distance [%s,%s] -- NON CONFRONTE" % (dmin, dmax))
            return 1
        cid, tid = me["id"], tgt["id"]
        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        _cale_mt(rpc, rid, st)
        d0 = hexgeo.distance(_pos(_by_id(dv0, cid)), _pos(_by_id(dv0, tid)))
        eff_avant_nat = _effects(dv0, tid)
        eff_avant_port = _port_effets(st, tid)

        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("cast REFUSE par le natif (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        diag = runner.ability_handler.last or {}
        res_port = diag   # `AbilityHandler.last` = {ability_type, ported, caster, target, **diag}

        dv1 = _vue(rpc, rid)
        eff_apres_nat = _effects(dv1, tid)
        eff_apres_port = _port_effets(st, tid)
        poses_nat = sorted(set(eff_apres_nat or []) - set(eff_avant_nat or []))
        poses_port = sorted(set(eff_apres_port or []) - set(eff_avant_port or []))
        interessants = set([TAUNT]) | set(TAUNT_CHILDREN)
        nat_taunt = sorted(set(poses_nat) & interessants)
        port_taunt = sorted(set(poses_port) & interessants)
        print("dist AVANT=%s  cible=%s" % (d0, tid))
        print("  effets cible : avant natif=%s / port=%s" % (eff_avant_nat, eff_avant_port))
        print("  effets cible : apres natif=%s / port=%s" % (eff_apres_nat, eff_apres_port))
        print("  POSES natif=%s  port=%s" % (poses_nat, poses_port))
        print("  famille TAUNT : natif=%s  port=%s" % (nat_taunt, port_taunt))
        print("  taunt (diag port) = %s ; nr_of_rounds=%s"
              % (res_port.get("taunt"), res_port.get("nr_of_rounds")))
        for e in _effets_bruts(dv1, tid):
            if e.get("effectType") in interessants:
                print("  EFFET NATIF %r" % (e,))
        # ETAGE DUREE, confronte a part : `TurnsFromRounds(nrOfRounds)` -> le natif rend un
        # `remaining` en TOURS. Un accord sur la POSE ne dit rien sur la duree.
        rem_nat = {e.get("effectType"): e.get("remaining") for e in _effets_bruts(dv1, tid)
                   if e.get("effectType") in interessants}
        rem_port = {int(getattr(x, "effect_type", -1)): getattr(x, "remaining_turns", None)
                    for x in ((getattr(st, "effects", None).by_unit.get(int(tid)) or [])
                              if getattr(st, "effects", None) is not None else [])
                    if int(getattr(x, "effect_type", -1)) in interessants}
        # `bondedEntityId` : le 5e argument natif d'`AddBondEffect` = le CASTER.
        bond_nat = {e.get("effectType"): e.get("bondedEntityId") for e in _effets_bruts(dv1, tid)
                    if e.get("effectType") in interessants}
        bond_port = {int(getattr(x, "effect_type", -1)): getattr(x, "bonded", None)
                     for x in ((getattr(st, "effects", None).by_unit.get(int(tid)) or [])
                               if getattr(st, "effects", None) is not None else [])
                     if int(getattr(x, "effect_type", -1)) in interessants}
        print("  DUREE (tours) natif=%s  port=%s  %s"
              % (rem_nat, rem_port, "ACCORD" if rem_nat == rem_port else "DESACCORD"))
        # LE BOND DU PARENT (27) est ce que pose CETTE ability (`bondedEntity` = 5e argument natif
        # d'`AddBondEffect`) : c'est LUI que le verdict garde. Les ENFANTS (25/26/1237) sont spawnes
        # par `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` via
        # `AddSubEffectWithSameTurns` -- le natif leur PROPAGE le bond (mesure : `bondedEntityId`
        # non nul sur les trois, `bondMeasured` vrai), le port non (`SubEffectSpec` n'a pas de champ
        # `bonded`, et ce chemin est PARTAGE par tous les composites : CrushingClaws 1105,
        # GetEmRuntz 1045, OverwhelmingWrath 1141). C'est donc un ecart PREEXISTANT du composite,
        # pas de ce port -- imprime, jamais rabattu sur le verdict de cette tranche.
        print("  BONDED parent natif=%s  port=%s  %s"
              % (bond_nat.get(TAUNT), bond_port.get(TAUNT),
                 "ACCORD" if bond_nat.get(TAUNT) == bond_port.get(TAUNT) else "DESACCORD"))
        # #524-r1 FERME : le bond descend desormais aux ENFANTS, au foyer de creation des
        # sous-effets (mirror du CONTEXTE PARTAGE de `TauntedEffect$$ApplyInternal`). On le
        # CONFRONTE au lieu de le commenter -- et le regime est NON degenere (bond non nul).
        _enf_nat = {k: v for k, v in bond_nat.items() if k != TAUNT}
        _enf_port = {k: v for k, v in bond_port.items() if k != TAUNT}
        print("  BONDED enfants natif=%s  port=%s  %s"
              % (_enf_nat, _enf_port, "ACCORD" if _enf_nat == _enf_port else "DESACCORD"))
        if nat_taunt and _enf_nat != _enf_port:
            print("VERDICT TAUNT: DESACCORD (bond des enfants -- #524-r1)")
            return 1
        if nat_taunt and (rem_nat != rem_port or bond_nat.get(TAUNT) != bond_port.get(TAUNT)):
            print("VERDICT TAUNT: DESACCORD (duree ou bond du parent)")
            return 1
        ok = (bool(nat_taunt) == bool(port_taunt))
        print("VERDICT TAUNT: %s (%s)"
              % ("ACCORD" if ok else "DESACCORD",
                 "pose des DEUX cotes" if nat_taunt and port_taunt
                 else ("absente des DEUX cotes" if not nat_taunt and not port_taunt
                       else "DIVERGENCE")))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_taunt_bloque(board, seed, allie, ennemis):
    """VOLET 3bis -- LA BRANCHE NEGATIVE du `If(IsAdjacent(...), bond)`, CRAFTEE.

    Une garde qui ne voit jamais son `else` ne garde rien. On force le regime : Lucius a distance 2
    d'une cible ALIGNEE (arc AVANT = UNE seule tuile), sur laquelle on POSE l'allie. `FindTileToPullOnce`
    rend alors cette tuile OCCUPEE (`list.Count == 1` -> AUCUN filtre `IsEmptyOrSteppable`), donc
    `IsFilled` -> pas de deplacement -> la cible reste a distance 2 -> `IsAdjacent` FAUX -> PAS de
    taunt. Ce que la mesure doit montrer : la cible NE bouge PAS et NE porte PAS 27, des deux cotes."""
    from engine.battle_query import get_minimum_tiles_180_front
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_distance(rpc, rid, 2, 2)
        if me is None or tgt is None:
            print("aucune configuration a distance 2 -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        dv = _vue(rpc, rid)
        pc, pt = _pos(_by_id(dv, cid)), _pos(_by_id(dv, tid))
        arc = list(get_minimum_tiles_180_front(pc, pt) or [])
        print("arc AVANT (caster=%s cible=%s) = %s" % (pc, pt, arc))
        ally = _by_vis(dv, allie)
        if ally is None:
            print("allie %s absent -- NON CONFRONTE" % allie)
            return 1
        libres = [t for t in arc if all(_pos(u) != t for u in _units(dv))]
        if len(arc) != 1 or not libres:
            print("arc de %d tuile(s), %d libre(s) : le blocage total n'est pas atteignable ici "
                  "-- NON CONFRONTE (relancer avec un autre --seed/--board)" % (len(arc), len(libres)))
            return 2
        dest = libres[0]
        mov = _movable(rpc, rid, ally["id"])
        if dest not in mov:
            print("l'allie ne peut pas atteindre %s (tuiles=%d) -- NON CONFRONTE"
                  % (dest, len(mov)))
            return 2
        _act(rpc, rid, {"kind": "move", "unitId": ally["id"],
                        "to": {"col": dest[0], "row": dest[1]}}, 60)
        dv = _vue(rpc, rid)
        print("allie %s pose sur %s (arc BLOQUE)" % (ally["id"], _pos(_by_id(dv, ally["id"]))))

        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        _cale_mt(rpc, rid, st)
        eff_avant_nat, eff_avant_port = _effects(dv0, tid), _port_effets(st, tid)
        pos_avant = _pos(_by_id(dv0, tid))
        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("cast REFUSE par le natif (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        diag = runner.ability_handler.last or {}
        dv1 = _vue(rpc, rid)
        e = st.get_entity(tid)
        ppc = e.get_component(PositionComponent) if e is not None else None
        pos_port = (ppc.col, ppc.row) if ppc is not None else None
        pos_nat = _pos(_by_id(dv1, tid))
        interessants = set([TAUNT]) | set(TAUNT_CHILDREN)
        nat = sorted(set(_effects(dv1, tid) or []) - set(eff_avant_nat or []))
        port = sorted(set(_port_effets(st, tid)) - set(eff_avant_port or []))
        print("  position cible : avant=%s ; natif=%s ; port=%s" % (pos_avant, pos_nat, pos_port))
        print("  POSES natif=%s  port=%s" % (nat, port))
        print("  pull (port)=%s ; taunt (port)=%s" % (diag.get("pull"), diag.get("taunt")))
        print("  SEQUENCE natif=%s" % (_montants_natifs(res),))
        nat_taunt = sorted(set(nat) & interessants)
        port_taunt = sorted(set(port) & interessants)
        ok = (pos_nat == pos_port == pos_avant and not nat_taunt and not port_taunt)
        print("VERDICT BRANCHE NEGATIVE: %s (taunt natif=%s port=%s)"
              % ("ACCORD -- pull bloque, aucun taunt des deux cotes" if ok else "DESACCORD",
                 nat_taunt, port_taunt))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_taunt_dead(board, seed, allie, ennemis, hp_target, dmin=2, dmax=2):
    """VOLET 3ter -- LE REGIME OU LE PORT EST CENSE DIVERGER (residu NOMME `#433-r3-r2`).

    Les `nrOfHits` coups TUENT la cible. Le natif resout alors `IsAdjacent(caster, target,
    selectionType: 3 = OnlyAliveAndTargetable)` sur un ensemble `B` VIDE -> `!B.Any()` -> FAUX,
    donc PAS de taunt ; et son `PullUnitOneTile` (targetSelectionType 2) ne voit plus la cible non
    plus. Le port, lui, ne consomme pas encore le `UnitSelectionType` : il evalue l'adjacence du
    CADAVRE. MESURE, pas hypothese -- c'est ce pas qui transforme le residu en fait chiffre."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis, hp_target=hp_target)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_distance(rpc, rid, dmin, dmax)
        if me is None or tgt is None:
            print("aucune configuration a distance [%s,%s] -- NON CONFRONTE" % (dmin, dmax))
            return 1
        cid, tid = me["id"], tgt["id"]
        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        _cale_mt(rpc, rid, st)
        hp0 = _hp(ob0, tid)
        eff_avant_port = _port_effets(st, tid)
        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("cast REFUSE par le natif (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        diag = runner.ability_handler.last or {}
        dv1 = _vue(rpc, rid)
        # `decisionView` GARDE les morts (`alive: false`) -> lire la liste COMPLETE, pas `_units`.
        u = next((x for x in ((dv1 or {}).get("units") or []) if x.get("id") == tid), None)
        morte_nat = not bool((u or {}).get("alive"))
        eff_nat = sorted(e.get("effectType") for e in ((u or {}).get("effects") or [])
                         if isinstance(e, dict) and e.get("effectType") is not None)
        from engine.runner.components import UnitComponent
        ent = st.get_entity(tid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        morte_port = not bool(getattr(uc, "alive", True))
        port_poses = sorted(set(_port_effets(st, tid)) - set(eff_avant_port or []))
        interessants = set([TAUNT]) | set(TAUNT_CHILDREN)
        nat_taunt = sorted(set(eff_nat) & interessants)
        port_taunt = sorted(set(port_poses) & interessants)
        print("hp cible avant=%s ; morte ? natif=%s port=%s" % (hp0, morte_nat, morte_port))
        print("  SEQUENCE natif=%s" % (_montants_natifs(res),))
        print("  SEQUENCE port =%s" % ((diag.get("main_attack") or {}).get("per_hit"),))
        print("  effets cible (natif)=%s ; POSES port=%s" % (eff_nat, port_poses))
        print("  pull (port)=%s ; taunt (port)=%s" % (diag.get("pull"), diag.get("taunt")))
        print("  famille TAUNT : natif=%s  port=%s" % (nat_taunt, port_taunt))
        # POURQUOI le port ne taunte-t-il pas ? Le mecanisme n'est PAS celui du natif : le port ne
        # consomme pas le `UnitSelectionType`, il tombe sur l'EMPREINTE VIDE du cadavre (le kill le
        # retire de ses tuiles) -> `are_entities_adjacent([], .)` FAUX. On le MESURE, on ne le
        # suppose pas : sans ce cran, un jour ou le cadavre garderait ses tuiles, l'accord sauterait.
        from engine.entities.triggers import IsAdjacent as _IsAdj
        from engine.entities.selectors.accessors import Target as _T
        from engine.entities.selectors.tiles import Caster as _C
        from engine.runner.abilities.behaviours.context import entities_from_state as _efs
        from engine.runner.components import get_unit_feet as _feet
        ents = _efs(st, cid, tid)
        print("  MECANISME port : feet(cadavre)=%s ; IsAdjacent(Caster,Target)=%s"
              % (_feet(st, tid), _IsAdj(_C(), _T()).should_trigger(ents)))
        if not (morte_nat and morte_port):
            print("TEMOIN NUL : la cible n'est pas morte des deux cotes -- baisser --hp-target")
            return 2
        ok = (bool(nat_taunt) == bool(port_taunt))
        print("VERDICT CIBLE MORTE: %s" % ("ACCORD" if ok else
                                           "DESACCORD -- residu #433-r3-r2 CONFIRME (le port "
                                           "taunte un cadavre que le natif ignore)"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_controle(board, seed, allie, ennemis):
    """VOLET 0 -- LE CONTROLE QUI SEPARE LES ETAGES.

    Le 2e cast d'un enchainement a diverge (`--step damage --casts 3`), et la cible y portait DEUX
    effets qu'elle n'avait pas au 1er : `1516 BeastSlayer_ExtraDmg` / `1517 BeastSlayer_ExtraBlock`
    (son propre trait, pose au debut de SON tour). La question est donc : l'ecart appartient-il a
    `LashOfTorment`, ou a l'etage EN AMONT (le canal de block/crit d'une cible BeastSlayer) ?

    Le montage repond SANS ambiguite : dans la MEME configuration contaminee, on joue D'ABORD
    l'ATTAQUE NORMALE de l'allie sur la MEME cible, PUIS `LashOfTorment`. Si les deux divergent,
    la cause est en amont de 1196 ; si seule la seconde diverge, elle est dans ce port."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_distance(rpc, rid, 1, RANGE)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        # UN tour de passage : c'est lui qui fait apparaitre les effets de trait de la cible.
        _act(rpc, rid, {"kind": "endturn"}, 60)
        me, tgt = _drive_a_distance(rpc, rid, 1, RANGE)
        if me is None or tgt is None:
            print("configuration perdue apres le tour de passage -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        dv = _vue(rpc, rid)
        print("cible %s : effets APRES le tour de passage = %s" % (tid, _effects(dv, tid)))
        ally = _by_vis(dv, allie)
        if ally is None:
            print("allie absent -- NON CONFRONTE")
            return 1

        # (a) ATTAQUE NORMALE de l'allie sur la MEME cible. `applyAction` n'a pas de `kind:"attack"` :
        # l'attaque normale est une ABILITY d'id CONCRET par unite (cf. probe_511 / probe_245).
        na = next((x["id"] for x in ((ally or {}).get("abilities") or [])
                   if x.get("kind") == "normal" and x.get("id") is not None), None)
        if na is not None and hexgeo.distance(_pos(ally), _pos(tgt)) <= 1:
            dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
            rng = _cale_mt(rpc, rid, st)
            hp0 = _hp(ob0, tid)
            res = _act(rpc, rid, {"kind": "ability", "casterId": int(ally["id"]),
                                  "targetId": int(tid), "abilityType": int(na)})
            a0 = ((res or {}).get("actions") or [{}])[0]
            if a0.get("ok") and a0.get("mutated"):
                runner = Runner(st).install_default_handlers(20)
                runner.apply(AttackUnitMessage(int(ally["id"]), int(tid)))
                e = st.get_entity(tid)
                hc = e.get_component(HealthComponent) if e is not None else None
                live = (hp0 or 0) - (_hp(rpc("observeBattle", {"runnerId": rid}, 60), tid) or 0)
                off = (hp0 or 0) - (hc.hp if hc is not None else 0)
                print("(a) ATTAQUE NORMALE (%s) sur cible contaminee : natif=%s port=%s %s"
                      % (allie, live, off, "ACCORD" if live == off else "DESACCORD"))
                print("    SEQUENCE natif=%s" % (_montants_natifs(res),))
                if live != off:
                    rc = 2       # 2 = l'ecart EXISTE DEJA hors de 1196
            else:
                print("(a) attaque normale REFUSEE (%r) -- volet non joue" % (a0,))
        else:
            print("(a) allie hors contact (d=%s) -- volet non joue"
                  % hexgeo.distance(_pos(ally), _pos(tgt)))

        # (b) `LashOfTorment` sur la MEME cible, MEME tour.
        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        rng = _cale_mt(rpc, rid, st)
        hp0 = _hp(ob0, tid)
        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("(b) cast 1196 REFUSE (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        diag = runner.ability_handler.last or {}
        e = st.get_entity(tid)
        hc = e.get_component(HealthComponent) if e is not None else None
        live = (hp0 or 0) - (_hp(rpc("observeBattle", {"runnerId": rid}, 60), tid) or 0)
        off = (hp0 or 0) - (hc.hp if hc is not None else 0)
        print("(b) LashOfTorment sur cible contaminee : natif=%s port=%s %s"
              % (live, off, "ACCORD" if live == off else "DESACCORD"))
        print("    SEQUENCE  port=%s" % ((diag.get("main_attack") or {}).get("per_hit"),))
        print("    SEQUENCE natif=%s" % (_montants_natifs(res),))
        if live != off and rc != 2:
            rc = 1
        print("VERDICT CONTROLE: %s"
              % {0: "les DEUX accordent -- rien a imputer",
                 1: "SEULE 1196 diverge -> l'ecart est DANS ce port",
                 2: "l'attaque NORMALE diverge deja -> l'ecart est EN AMONT de 1196"}[rc])
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_chaine(board, seed, allie, ennemis, vecteur, dmin=1, dmax=RANGE, amorce="ability", crit=None):
    """VOLET 0bis -- LE CONTROLE QUI ISOLE LE VECTEUR, a etat STRICTEMENT identique.

    `--step damage --casts 3` diverge au 2e cast (le port CRITE aux coups 0 et 1, le natif non), et
    la meme configuration confrontee dans un runner FRAIS accorde bit pour bit. L'ecart depend donc
    de l'ETAT accumule, pas de l'arbre. Ce montage rejoue EXACTEMENT la meme sequence -- cast 1196,
    `endturn`, re-approche -- et ne change QU'UNE chose au 2e geste : le VECTEUR.

        --vecteur ability : 2e geste = `LashOfTorment` (reproduit le desaccord)
        --vecteur normal  : 2e geste = l'ATTAQUE NORMALE de Lucius sur la MEME cible

    Meme caster, meme cible, meme position MT, meme etat de charge. Si le vecteur NORMAL diverge
    aussi, la cause est EN AMONT de 1196 (canal crit partage) ; s'il accorde, elle est dans ce port.
    """
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis, crit=crit)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        # --- geste 1 : TOUJOURS 1196, pour reconstruire le MEME etat -------------------------
        me, tgt = _drive_a_distance(rpc, rid, 1, RANGE)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        if amorce == "normal":
            _na0 = next((x["id"] for x in ((me or {}).get("abilities") or [])
                         if x.get("kind") == "normal" and x.get("id") is not None), None)
            _act(rpc, rid, {"kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
                            "abilityType": int(_na0)})
        else:
            _act(rpc, rid, {"kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
                            "abilityType": ABILITY})
        # UN `endturn` ne suffit pas toujours a rendre son ACTIVE a Lucius : selon la geometrie,
        # `_drive_a_distance` peut rendre une configuration AU MEME TOUR, et le 2e geste revient
        # alors `ok: true, mutated: false` -- un refus SILENCIEUX qui se lirait comme une mesure.
        # On BOUCLE jusqu'a ce que le natif re-propose l'ability au caster (`decisionView` la liste
        # dans `units[].abilities`), et on ECHOUE FORT si le tour ne revient pas.
        exclu1 = tgt["id"]
        me = tgt = None
        for _ in range(4):
            _act(rpc, rid, {"kind": "endturn"}, 60)
            m2, t2 = _drive_a_distance(rpc, rid, dmin, dmax, exclus=(exclu1,))
            if m2 is None or t2 is None:
                continue
            dispo = any(int(x.get("id") or -1) == ABILITY for x in (m2.get("abilities") or []))
            if dispo:
                me, tgt = m2, t2
                break
        if me is None or tgt is None:
            print("2e configuration introuvable (ou active non re-proposee) -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        d = hexgeo.distance(_pos(me), _pos(tgt))
        dv0, ob0, st, snap0 = _capture(rpc, rid, brd)
        rng = _cale_mt(rpc, rid, st)
        hp0 = _hp(ob0, tid)
        tirages0, mti0 = rng.tirages, rng.mti
        from engine.runner.components import charged_unit_ids
        print("geste 2 : caster=%s cible=%s dist=%s vecteur=%s" % (cid, tid, d, vecteur))
        print("  etat port : charged(caster)=%s effets caster=%s cible=%s"
              % (sorted(charged_unit_ids(st, cid) or []), _effects(dv0, cid), _effects(dv0, tid)))
        # LE CANAL DU CRIT DE CET ARBRE, ET LE SEUL : `ThrillSeekers` (trait du CASTER
        # `emperLucius`, `UnitTrait` 1056) pose « Thrilled » (`EffectType` 1434), un stat-mod
        # CRIT_CHANCE. Les events du geste 2 montrent qu'il se declenche -- reste a savoir si le
        # PORT sait que le caster le PORTE DEJA au moment de la capture. `decisionView` ne le publie
        # pas toujours (motif de SEEDING #118, nomme par `effects/loki/serene_unifier.py`), et un
        # buff invisible a la capture est un buff que le port RE-AJOUTE au lieu de RAFRAICHIR.
        from engine.entities.effect_type import EffectType as _ET
        _thr = int(_ET.ThrillSeekers)                      # 0x59a = 1434 (« Thrilled »)
        _dv_thr = _thr in (_effects(dv0, cid) or [])
        _st_thr = bool(getattr(st, "effects", None)
                       and st.effects.has_effect(int(cid), _thr))
        print("  THRILLED(1434) sur le caster : decisionView=%s ; etat PORT=%s" % (_dv_thr, _st_thr))
        # LE CRAN QUI TRANCHE : `ThrillSeekersAbility$$CreateBehaviour` teste
        # `HasEffect(Owner, 0x59a, activeOnly = 0, sourceFlags = 6)` -- le natif voit l'effet MEME
        # INACTIF. Or `decisionView` DROPPE les effets dont `IsActive` est faux (`readEffectsByUnit`),
        # sauf si on lui demande `includeInactive`. Si l'effet APPARAIT avec ce drapeau et pas sans,
        # le port prend la branche `AddStaticStatModifierEffect` (+15) la ou le natif prend
        # `ChangeEffectTurns` (Set, aucun nouveau +15) : c'est LA cause du surplus de crit chance.
        _dvi = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                    "includeInactive": True}, 150)
        _inact = [e for e in _effets_bruts(_dvi, cid) if e.get("effectType") == _thr]
        print("  THRILLED(1434) avec includeInactive : %s" % (_inact or "ABSENT",))
        if vecteur == "normal":
            na = next((x["id"] for x in ((me or {}).get("abilities") or [])
                       if x.get("kind") == "normal" and x.get("id") is not None), None)
            if na is None:
                print("attaque normale introuvable -- NON CONFRONTE")
                return 1
            res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                                  "abilityType": int(na)})
        else:
            res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                                  "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("geste 2 REFUSE (%r) -- NON CONFRONTE" % (a0,))
            return 1
        runner = Runner(st).install_default_handlers(20)
        # DECOMPOSITION PAR ETAGE : le canal CRIT est le foyer PARTAGE des trois vecteurs
        # (`AttackDamageOperation._crit_params`). On le TRACE au lieu de deviner -- c'est le seul
        # moyen de dire si l'ecart vient de la CHANCE (etage crit) ou du TIRAGE (etage rng).
        from engine.runner.operations.damage import AttackDamageOperation as _ADO
        _orig = _ADO._crit_params.__func__ if hasattr(_ADO._crit_params, "__func__") \
            else _ADO._crit_params
        _traces = []

        def _traced(*a, **k):
            r = _orig(*a, **k)
            _traces.append((k.get("is_ranged"), k.get("is_normal_attack"), r))
            return r
        _ADO._crit_params = staticmethod(_traced)
        try:
            if vecteur == "normal":
                runner.apply(AttackUnitMessage(int(cid), int(tid)))
                per_hit = None
            else:
                runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
                per_hit = ((runner.ability_handler.last or {}).get("main_attack")
                           or {}).get("per_hit")
        finally:
            _ADO._crit_params = staticmethod(_orig)
        print("  CRIT PARAMS port (is_ranged, is_normal, (chance, dmg, enabled)) = %s" % (_traces,))
        e = st.get_entity(tid)
        hc = e.get_component(HealthComponent) if e is not None else None
        live = (hp0 or 0) - (_hp(rpc("observeBattle", {"runnerId": rid}, 60), tid) or 0)
        off = (hp0 or 0) - (hc.hp if hc is not None else 0)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        print("  degat : natif=%s port=%s %s"
              % (live, off, "ACCORD" if live == off else "DESACCORD"))
        print("  SEQUENCE natif=%s" % (_montants_natifs(res),))
        print("  SEQUENCE  port=%s" % (per_hit,))
        print("  tirages port=%d ; mti avant=%s -> natif=%s port=%s ; MT egaux ? %s"
              % (rng.tirages - tirages0, mti0, (s1 or {}).get("mti"), rng.mti,
                 _ok(s1) and list(s1.get("mt") or []) == list(rng.mt) and s1.get("mti") == rng.mti))
        # QUI PORTE LES +15 ? `ThrillSeekers` pose « Thrilled » PENDANT l'attaque (le trigger
        # `On(PreAttackHit)` precede `_crit_params`). On lit donc l'effet APRES le cast, des deux
        # cotes : si le PORT le pose et que le natif ne l'a pas, le +15 du port est de trop.
        _dv2 = _vue(rpc, rid)
        print("  THRILLED(1434) APRES le cast : natif=%s ; port=%s"
              % (_thr in (_effects(_dv2, cid) or []),
                 bool(getattr(st, "effects", None) and st.effects.has_effect(int(cid), _thr))))
        # LE DECALAGE SE LIT DANS LES OPERATIONS, PAS DANS LE DEGAT. Un tirage de plus cote natif
        # vient d'une OPERATION de plus, et une operation laisse des events. On imprime la SUITE
        # des groupes/steps du geste 2 pour la DIFFER entre les deux amorces : ce qui apparait
        # sous `--amorce ability` et pas sous `--amorce normal` est le suspect.
        print("  EVENTS natif (geste 2), en ordre :")
        for a in ((res or {}).get("actions") or []):
            for e in (a.get("events") or []):
                k = e.get("kind") or "?"
                if k == "group":
                    print("     [group %s] entity=%s source=%s"
                          % (e.get("group"), e.get("entity"), e.get("source")))
                elif e.get("step") is not None:
                    print("     step=%s entity=%s target=%s" % (e.get("step"), e.get("entity"),
                                                                e.get("target")))
                else:
                    print("     %s entity=%s" % (k, e.get("entity")))
        ok = (live == off)
        print("VERDICT CHAINE(%s): %s" % (vecteur, "ACCORD" if ok else "DESACCORD"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="damage",
                    choices=["damage", "pull", "taunt", "taunt-bloque", "taunt-dead", "controle", "chaine"])
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--allie", default="ultraTitus")
    ap.add_argument("--ennemis", default="orksNob,necroWarden")
    ap.add_argument("--casts", type=int, default=2)
    ap.add_argument("--dmin", type=int, default=1)
    ap.add_argument("--dmax", type=int, default=RANGE)
    ap.add_argument("--vecteur", default="ability", choices=["ability", "normal"],
                    help="chaine : vecteur du 2e geste (ability = 1196, normal = attaque normale)")
    ap.add_argument("--crit", default=None,
                    help="chaine : force CritChance,CritDamage des p-units (ex. \"0,0\")")
    ap.add_argument("--amorce", default="ability", choices=["ability", "normal"],
                    help="chaine : vecteur du 1er geste (celui qui avance le MT)")
    ap.add_argument("--hp-target", type=int, default=1200,
                    help="taunt-dead : PV des a-units (kill deterministe en 6 coups)")
    a = ap.parse_args(argv)
    if a.step == "pull":
        return step_pull(a.board, a.seed, a.allie, a.ennemis, a.dmin, a.dmax)
    if a.step == "taunt":
        return step_taunt(a.board, a.seed, a.allie, a.ennemis, a.dmin, a.dmax)
    if a.step == "chaine":
        return step_chaine(a.board, a.seed, a.allie, a.ennemis, a.vecteur, a.dmin, a.dmax, a.amorce, a.crit)
    if a.step == "controle":
        return step_controle(a.board, a.seed, a.allie, a.ennemis)
    if a.step == "taunt-bloque":
        return step_taunt_bloque(a.board, a.seed, a.allie, a.ennemis)
    if a.step == "taunt-dead":
        return step_taunt_dead(a.board, a.seed, a.allie, a.ennemis, a.hp_target, a.dmin, a.dmax)
    return step_damage(a.board, a.seed, a.allie, a.ennemis, a.casts, a.dmin, a.dmax)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
