"""#511 -- `StrikeFromTheShadows` (ActiveAbilityType 1225, `astarCyrus` << Cyrus >>).

MESURE, pas garde. Le porteur est un HERO `lineup` HORS du pool spawnable -> il est INJECTE au
catalogue (`catalog_inject.write_augmented_seed_bc`), exactement comme pour son passif `HaywireMine`
(#462-r4b-...-r5). Ce probe confronte les TROIS volets de l'arbre natif, un par un :

  --step damage   : l'ATTAQUE. Sequence de degats coup par coup (deltas HP par unite) et NOMBRE DE
                    TIRAGES rng consommes -- un compte de coups juste ne prouve rien, c'est le
                    compteur de tirages qui mord. MT offline cale sur `dumpRng` AVANT le cast.
  --step reset    : le `ResetMovement(Owner)`. Le natif retire {ArrivedAtFinalTile, Moved,
                    TurnTerminated, TurnFinished} du CASTER. Observable : apres un DEPLACEMENT puis
                    le cast, `aiMovableTiles` re-propose des tuiles a Cyrus. Le port doit rendre
                    `UnitFlag.Moved` absent, et `ActiveAbilityUsed` PRESENT (pas de re-cast).
  --step effect   : l'effet 0x60d pose sur la CIBLE, et son INERTIE numerique. Le decompile dit que
                    `StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense` construit un
                    `EffectBonus` a TRIGGER SEUL (les six slots de magnitude a zero) ; la
                    consequence testable est qu'une attaque a distance recue par la cible MARQUEE
                    coute exactement ce qu'elle coutait AVANT la marque.

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

CASTER = "astarCyrus"              # HERO `lineup` HORS seed BC -> catalog_inject
ABILITY = 1225                     # ActiveAbilityType.StrikeFromTheShadows
EFFECT = 1549                      # EffectType.StrikeFromTheShadows (0x60d)
DEFAULT_BOARD = "MC1_67"
RANGE = 3                          # gameconfig `range`


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


def _build(board: str, seed: str, allie: str, ennemis: str) -> tuple:
    """`rl_duel build` avec `astarCyrus` injecte. Rend `(rid, state_path)`."""
    import subprocess
    import catalog_inject
    pyd = Path(__file__).resolve().parent
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    tag = uuid.uuid4().hex[:8]
    bc = tmp / ("sfts-bc-%s.json" % tag)
    state = tmp / ("sfts-state-%s.json" % tag)
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--seed-bc", str(bc), "--board", board,
            "--rank", "17", "--no-ai",
            "--p-units", "%s,%s" % (CASTER, allie), "--a-units", ennemis]
    p = subprocess.run(argv, cwd=str(pyd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-600:]))
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


def _hp(ob, uid):
    """`observeBattle` indexe ses unites par `squadId`, PAS par `id` -- lire `id` rend `None`
    partout, et un dict de deltas VIDE des DEUX cotes est un accord en regime DEGENERE, donc
    zero preuve. Faute commise puis corrigee dans cette tranche."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _effects(dv, uid):
    """La cle est `effectType` (pas `type`) -- lue dans les tests live existants."""
    for u in _units(dv):
        if u.get("id") == uid:
            return sorted(e.get("effectType") for e in (u.get("effects") or [])
                          if isinstance(e, dict) and e.get("effectType") is not None)
    return None


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _coups_natifs(res):
    """La SEQUENCE coup par coup du natif, lue dans les events d'`applyAction`. Un total juste ne
    prouve rien -- c'est la sequence (et le nombre de coups) qui mord."""
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if (e.get("kind") or "") == "damage" or e.get("amount") is not None:
                out.append({k: e.get(k) for k in
                            ("kind", "entity", "target", "amount", "crit", "block", "profile")
                            if e.get(k) is not None})
    return out


def _events_bruts(res, brut=False):
    noms = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            noms.append(e if brut else (e.get("kind") or e.get("type") or "?"))
    return noms


def _montants_natifs(res):
    """La SEQUENCE coup par coup du NATIF, lue dans les tags `Amount` des events `action` du pas
    `UnitDamaged`. Un TOTAL juste ne prouve rien : c'est la sequence qui mord (et le compte de
    coups)."""
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


def _changes(res):
    out = []
    for a in ((res or {}).get("actions") or []):
        out.extend(a.get("changes") or [])
    return out


def _capture(rpc, rid, board):
    from engine.runner.snapshot import load_state
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        raise SystemExit("capture live KO -- montage non installe")
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    return dv, ob, st


class _MTCompteur:
    """Le MT du port, avec un COMPTEUR DE TIRAGES. `mti` est un index CYCLIQUE (0..624) : sa
    difference peut etre NEGATIVE et ne compte donc rien. `IntBasedMersenneTwister` porte
    `__slots__`, d'ou la sous-classe (creee a la volee pour garder l'import local)."""

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
    """CALER le MT offline sur le MT LIVE avant toute comparaison de degat -- sans ca,
    `execute_ability_attack` SKIP le degat et on lit un faux 0."""
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s):
        raise SystemExit("dumpRng KO -- MT non calable")
    rng = _MTCompteur()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    st.rng = rng
    return rng


def _drive_a_portee(rpc, rid, cible_vis=None, portee=RANGE, tours=10, exclus=()):
    """DEPLACE Cyrus jusqu'a avoir une cible a portee (doctrine drive-positions : on ne se plaint
    jamais de la geometrie de spawn). Rend `(cyrus, cible)` ou `(None, None)`.

    `exclus` = ids d'unites a NE PAS reprendre (ex. deja marquees par 1549) -- c'est ce qui permet
    d'isoler l'effet du cast N de l'effet POSE par le cast N-1."""
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
        if cible_vis is not None:
            ennemis = [u for u in ennemis if (u.get("visualId") or "") == cible_vis] or ennemis
        if not ennemis:
            return None, None
        tgt = min(ennemis, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= portee:
            return me, tgt
        tiles = _movable(rpc, rid, me["id"])
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if 1 <= hexgeo.distance(p, tp) <= portee else 1,
                                             hexgeo.distance(p, tp)))
            _act(rpc, rid, {"kind": "move", "unitId": me["id"],
                            "to": {"col": best[0], "row": best[1]}}, 60)
        else:
            _act(rpc, rid, {"kind": "endturn"}, 60)
    return None, None


# --------------------------------------------------------------------------- etapes

def step_damage(board, seed, allie, ennemis, casts, solo=False):
    """VOLET 1 -- l'attaque : sequence coup par coup ET compteur de tirages."""
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
        marquees: set = set()
        for n in range(casts):
            # `--solo` : la MEME cible peut etre reprise (un seul cast de toute facon) ; sinon on
            # EXCLUT les cibles deja marquees par 1549 -- sans quoi le cast N mesure le cast N-1.
            me, tgt = _drive_a_portee(
                rpc, rid, exclus=(() if (solo or os.environ.get("SFTS_REPRENDRE")) else marquees))
            if me is None or tgt is None:
                print("cast#%d : plus de configuration jouable -- arret" % n)
                break
            cid, tid = me["id"], tgt["id"]
            dv0, ob0, st = _capture(rpc, rid, brd)
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
            atk = diag.get("attack") or {}
            print("cast#%d caster=%s target=%s  effets_cible_AVANT=%s  hp_live_avant=%s"
                  % (n, cid, tid, _effects(dv0, tid), avant.get(tid)))
            print("   effets CASTER AVANT=%s ; bornes port=%s..%s ; armure cible=%s"
                  % (_effects(dv0, cid), atk.get("base_min"), atk.get("base_max"),
                     atk.get("armor")))
            print("   ported=%s  attaque=%s" % (diag.get("ported"), atk))
            print("   deltas HP  live=%s  port=%s  %s"
                  % (live, off, "ACCORD" if live == off else "DESACCORD"))
            print("   coups (port) = %s ; tirages rng consommes = %d"
                  % (atk.get("hits"), rng.tirages - tirages_avant))
            print("   SEQUENCE  port=%s" % (atk.get("per_hit"),))
            print("   SEQUENCE natif=%s" % ([e for e in _montants_natifs(res)],))
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if _ok(s1):
                # COMBIEN LE NATIF A-T-IL TIRE ? On compare l'etat MT d'apres avec celui du port :
                # si les deux MT ne sont pas au MEME point, la comparaison de montants ne veut
                # plus rien dire -- c'est l'etage RNG qui a diverge, pas l'etage degat.
                same_mt = (list(s1.get("mt") or []) == list(rng.mt)) and s1.get("mti") == rng.mti
                print("   MT : mti avant=%s ; apres -> natif=%s (%+d) port=%s (%+d) ; egaux ? %s"
                      % (mti_avant, s1.get("mti"), (s1.get("mti") or 0) - mti_avant,
                         rng.mti, rng.mti - mti_avant, same_mt))
            if os.environ.get("SFTS_DUMP"):
                for e in _events_bruts(res, brut=True):
                    print("      EV %r" % (e,))
                for c in _changes(res):
                    print("      CH %r" % (c,))
            if live != off or diag.get("ported") is not True:
                rc = 1
            if not live:
                # ACCORD EN REGIME DEGENERE = ZERO PREUVE : deux dicts vides ne prouvent rien.
                print("   !! AUCUN delta HP live -- temoin NUL, la comparaison ne prouve rien")
                rc = 1
            mesures += 1
            marquees.add(tid)
            if solo:
                break                # UN cast par runner : la cible reste VIERGE de 1549
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


def step_reset(board, seed, allie, ennemis):
    """VOLET 2 -- `ResetMovement(Owner)` : Cyrus BOUGE, caste, et doit pouvoir RE-bouger."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.messages import ActiveAbilityMessage, MoveUnitMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]

        # UN PAS d'abord : c'est ce qui pose `Moved`/`ArrivedAtFinalTile` et rend le reset
        # OBSERVABLE (sans deplacement prealable, retirer `Moved` ne change rien).
        # LE PAS PREALABLE : c'est lui qui pose `Moved`/`ArrivedAtFinalTile` et rend le reset
        # OBSERVABLE. `_drive_a_portee` l'a le plus souvent DEJA consomme (Cyrus a marche jusqu'a
        # sa portee) -- dans ce cas `aiMovableTiles` est deja VIDE, et c'est le regime voulu. Sinon
        # on fait un pas qui garde la cible a portee. On ne se plaint jamais de la geometrie.
        depart, cible_pos = _pos(me), _pos(tgt)
        mov_apres_pas = _movable(rpc, rid, cid)
        if mov_apres_pas:
            pas = [t for t in mov_apres_pas
                   if t != depart and 1 <= hexgeo.distance(t, cible_pos) <= RANGE]
            if pas:
                dest = min(pas, key=lambda t: (hexgeo.distance(t, depart), t))
                _act(rpc, rid, {"kind": "move", "unitId": cid,
                                "to": {"col": dest[0], "row": dest[1]}}, 60)
                mov_apres_pas = _movable(rpc, rid, cid)
        if mov_apres_pas:
            print("Cyrus a ENCORE du mouvement avant le cast (%d tuiles) -- le reset ne serait pas "
                  "observable, montage non conforme" % len(mov_apres_pas))
            return 1

        dv0, ob0, st = _capture(rpc, rid, brd)
        _cale_mt(rpc, rid, st)
        runner = Runner(st).install_default_handlers(20)
        fl = st.get_entity(cid).get_component(UnitFlagsComponent)
        port_avant = sorted(fl.flags)

        _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                        "abilityType": ABILITY})
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        mov_apres_cast = _movable(rpc, rid, cid)
        port_apres = sorted(fl.flags)

        nat_rebouge = len(mov_apres_cast) > 0
        port_rebouge = not fl.has(UnitFlagsComponent.MOVED)
        print("NATIF : tuiles mobiles apres pas = %d ; apres cast = %d -> re-deplacable ? %s"
              % (len(mov_apres_pas), len(mov_apres_cast), nat_rebouge))
        print("PORT  : flags avant=%s apres=%s ; Moved absent ? %s ; ActiveAbilityUsed present ? %s"
              % (port_avant, port_apres, port_rebouge,
                 fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)))
        ok = (nat_rebouge == port_rebouge is True)
        print("VERDICT: %s" % ("ACCORD -- ResetMovement mord des DEUX cotes" if ok
                               else "DESACCORD"))
        # Le natif RE-deplace-t-il vraiment ? on le JOUE, c'est la seule preuve non-derivee.
        if mov_apres_cast:
            d2 = sorted(mov_apres_cast)[0]
            r = _act(rpc, rid, {"kind": "move", "unitId": cid,
                                "to": {"col": d2[0], "row": d2[1]}}, 60)
            a0 = ((r or {}).get("actions") or [{}])[0]
            print("SECOND PAS joue vers %s : ok=%s mutated=%s" % (d2, a0.get("ok"), a0.get("mutated")))
            runner.apply(MoveUnitMessage(int(cid), (int(d2[0]), int(d2[1]))))
            ok = ok and bool(a0.get("mutated"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_effect(board, seed, allie, ennemis):
    """VOLET 3 -- l'effet 0x60d : POSE sur la cible, et INERTIE numerique.

    Deux mesures. (a) la cible porte-t-elle 1549 apres le cast, des deux cotes ? (b) une attaque
    NORMALE A DISTANCE recue par la cible marquee coute-t-elle la meme chose que la MEME attaque
    hors marque ? Le decompile dit OUI (EffectBonus a trigger seul) ; c'est ce qu'on mesure.
    """
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
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        dv0, ob0, st = _capture(rpc, rid, brd)
        _cale_mt(rpc, rid, st)
        runner = Runner(st).install_default_handlers(20)
        eff_avant = _effects(dv0, tid)

        _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                        "abilityType": ABILITY})
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        dv1 = _vue(rpc, rid)
        eff_apres = _effects(dv1, tid)
        from engine.runner.components import has_effect_of_type
        port_porte = has_effect_of_type(st, tid, EFFECT)
        nat_porte = EFFECT in (eff_apres or [])
        print("CIBLE %s : effets avant=%s" % (tid, eff_avant))
        print("             effets apres (natif)=%s -> 1549 present ? %s" % (eff_apres, nat_porte))
        print("             1549 present cote PORT ? %s" % port_porte)
        # duree : le natif doit rendre `TurnsUntilEndOfCurrentPlayersNextTurn`, pas TurnsFromRounds(1)
        rem_nat = None
        for u in _units(dv1):
            if u.get("id") == tid:
                for e in (u.get("effects") or []):
                    if isinstance(e, dict) and e.get("type") == EFFECT:
                        rem_nat = e.get("remaining")
        from engine.runner.abilities.base import (convert_rounds_to_turns,
                                                  turns_until_end_of_current_players_next_turn)
        print("DUREE : natif remaining=%s ; port TurnsUntilEnd...=%s (TurnsFromRounds(1)=%s)"
              % (rem_nat, turns_until_end_of_current_players_next_turn(st),
                 convert_rounds_to_turns(st, 1)))
        ok = (nat_porte == port_porte is True)
        print("VERDICT POSE: %s" % ("ACCORD" if ok else "DESACCORD"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_inertie(board, seed, allie, ennemis):
    """VOLET 3bis -- L'EFFET 1549 MODIFIE-T-IL LES DEGATS RECUS ? La mesure qui tranche.

    Le decompile dit NON (le `EffectBonus` de `CreateEffectDamageMalusForDefense` n'a que son
    trigger ; ses six slots de magnitude sont a ZERO -- verifie AUX OCTETS). On le confronte :
    Cyrus marque la cible A, puis une AUTRE unite l'attaque NORMALEMENT, et on compare natif/port.
    Un ACCORD bit-exact sur une cible MARQUEE etablit l'inertie ; un desaccord la refute.
    """
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner

    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, allie, ennemis)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                        "abilityType": ABILITY})
        dv = _vue(rpc, rid)
        marquee = EFFECT in (_effects(dv, tid) or [])
        print("cible %s marquee par 1549 ? %s (effets=%s)" % (tid, marquee, _effects(dv, tid)))
        if not marquee:
            print("la marque n'est pas posee -- montage non conforme")
            return 1

        # L'ATTAQUANT EST CYRUS LUI-MEME, DANS LA FOULEE DU CAST. Deux raisons : (1) aucune
        # geometrie a re-monter -- la cible est deja a portee, et un `endturn` de repositionnement
        # rendrait le cast suivant `ok:true, mutated:false`, un refus SILENCIEUX qui se lirait
        # comme une mesure (faute commise puis corrigee ici) ; (2) c'est le MEME geste qui exerce
        # le `ResetMovement` -- sans lui, le tour de Cyrus serait clos et l'attaque refusee.
        # `applyAction` N'A PAS de `kind: "attack"` : l'attaque NORMALE est une ABILITY d'id
        # CONCRET par unite (`decisionView.units[].abilities`, entree `kind == "normal"`, cf.
        # `probe_245`).
        att = _by_vis(dv, CASTER)
        if att is None:
            print("Cyrus absent apres son cast -- NON CONFRONTE")
            return 1
        na = next((a["id"] for a in ((att or {}).get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        if na is None:
            print("attaque normale introuvable sur %s -- NON CONFRONTE" % allie)
            return 1
        dv0, ob0, st = _capture(rpc, rid, brd)
        rng = _cale_mt(rpc, rid, st)
        hp0 = _hp(ob0, tid)
        res = _act(rpc, rid, {"kind": "ability", "casterId": int(att["id"]),
                              "targetId": int(tid), "abilityType": int(na)})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("attaque normale (%s) REFUSEE (%r) -- NON CONFRONTE" % (na, a0))
            return 1
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        live = (hp0 or 0) - (_hp(ob2, tid) or 0)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(att["id"]), int(tid)))
        e = st.get_entity(tid)
        hc = e.get_component(HealthComponent) if e is not None else None
        off = (hp0 or 0) - (hc.hp if hc is not None else 0)
        print("ATTAQUE NORMALE sur cible MARQUEE : natif=%s ; port=%s ; sequence natif=%s"
              % (live, off, _montants_natifs(res)))
        ok = (live == off) and live > 0
        print("VERDICT INERTIE: %s"
              % ("ACCORD -- 1549 ne modifie PAS les degats recus (inertie CONFIRMEE)" if ok
                 else "DESACCORD -- 1549 modifie quelque chose, ou temoin nul"))
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
                    choices=["damage", "reset", "effect", "inertie"])
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--allie", default="ultraTitus")
    ap.add_argument("--ennemis", default="orksNob,necroWarden")
    ap.add_argument("--casts", type=int, default=3)
    ap.add_argument("--solo", action="store_true",
                    help="UN seul cast par runner (la cible reste VIERGE de 1549)")
    a = ap.parse_args(argv)
    if a.step == "reset":
        return step_reset(a.board, a.seed, a.allie, a.ennemis)
    if a.step == "effect":
        return step_effect(a.board, a.seed, a.allie, a.ennemis)
    if a.step == "inertie":
        return step_inertie(a.board, a.seed, a.allie, a.ennemis)
    return step_damage(a.board, a.seed, a.allie, a.ennemis, a.casts, a.solo)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
