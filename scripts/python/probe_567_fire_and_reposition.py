"""#567 -- `FireAndReposition` (ActiveAbilityType 1063, `eldarRanger` << Calandis >>).

MESURE, pas garde. Le porteur est un HERO du pool spawnable (`rl_duel build --list-pool`, rank 17)
-> aucune injection catalogue, aucun montage de relique.

L'arbre natif
(`IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`) porte
TROIS feuilles, et ce probe les confronte UNE PAR UNE -- un volet qui passe ne dit rien des deux
autres, et c'est exactement le mode de panne qu'un port composite installe :

  --step damage : [1] `UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster))`. La config
                  1063 n'a NI `minDmg`/`maxDmg`, NI `nrOfHits`, NI `damageProfile` -> le cast
                  DISPATCHE l'attaque NORMALE de Calandis. Observable : la sequence de degats coup
                  par coup (deltas HP par unite) ET le nombre de tirages rng consommes -- un total
                  juste ne prouve rien, c'est la SEQUENCE et l'etat MT final qui mordent.
  --step reset  : [2] `ResetMovement(Owner)`. Le natif retire {ArrivedAtFinalTile, Moved,
                  TurnTerminated, TurnFinished} du caster. Observable : apres un DEPLACEMENT puis le
                  cast, `aiMovableTiles` re-propose des tuiles a Calandis, et le second pas est
                  JOUE (seule preuve non derivee). Cote port : `UnitFlag.Moved` absent et
                  `ActiveAbilityUsed` PRESENT (elle re-bouge, elle ne re-caste pas).
  --step effect : [3] `AddEffect(0x456 = 1110 FireAndReposition_ReduceDmg, source = Caster,
                  targets = Caster, TurnsFromRounds(1))` -- SUR ELLE-MEME. Observable : la pose des
                  deux cotes, le `remaining` natif contre `TurnsFromRounds(1)` (et contre
                  `TurnsUntilEndOfCurrentPlayersNextTurn`, la duree VOISINE que porte
                  `StrikeFromTheShadows` et qui depasserait d'un tour), et le NIVEAU d'ability bake
                  sur l'instance du port (`scale_from_source` : la magnitude de 1110 s'indexe sur
                  l'ACTIVE, cf. #366-r1).
  --step gate   : le MASQUE. `<TargetingOptions statics>+0x00` = rules 0x4002 +
                  `RANGE_ADJACENT_IF_MELEE_CASTER` + `forceMeleeTarget = IfRangedCaster`. Confronte
                  l'ACCEPTATION du natif a celle du port, cible par cible, sur TOUTES les unites
                  vivantes du plateau (ennemies ET amies) -- c'est le seul volet ou l'ecart se lit
                  en REFUS, pas en degat.

L'effet 1110 lui-meme (ses trois gates, sa magnitude) est deja mesure et garde par
`probe_366_r1_fire_and_reposition.py` / `test_fire_and_reposition_reduce_dmg_live.py` : ce probe-ci
ne le redouble pas, il mesure sa POSE -- ce qui manquait, la face COMBAT de 1063 etant un NO-OP.

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

#: Resolu PAR NOM contre `enums.tsv` du build courant, jamais ecrit en ordinal (meme cliquet que
#: `probe_511` : un membre retire en amont decale tout ce qui suit, en silence).
S_UNIT_DAMAGED = SE.step_id("UnitDamaged")

CASTER = "eldarRanger"             # << Calandis >> -- HERO du pool spawnable, rank 17
ABILITY = 1063                     # ActiveAbilityType.FireAndReposition (0x427)
EFFECT = 1110                      # EffectType.FireAndReposition_ReduceDmg (0x456)
DEFAULT_BOARD = "MC1_67"
#: Portee de l'arme RANGED de Calandis (`unit_map` : `1hR3p30`). Le masque n'a AUCUNE constante
#: `range` a lire (la config 1063 n'en porte pas) : la portee effective est celle de l'ARME, et
#: c'est ce que dit l'i2 (<< if Calandis has a target in range >>).
RANGE = 3


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


def _build(board: str, seed: str, allie: str, ennemis: str, drop_passive: bool = False) -> tuple:
    """`rl_duel build`. Rend `(rid, state_path)`.

    `drop_passive` retire `1111 WireweaveNet` du porteur. Il n'est PAS le defaut : ce passif est une
    CONTRE-ATTAQUE declenchee quand Calandis est ciblee par une attaque de MELEE, donc il ne mord sur
    aucun des quatre volets (c'est elle qui attaque). L'option existe pour isoler le flux MT si un
    jour un volet diverge -- on ne degrade pas le regime << au cas ou >>.
    """
    import subprocess
    pyd = Path(__file__).resolve().parent
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    tag = uuid.uuid4().hex[:8]
    state = tmp / ("far567-state-%s.json" % tag)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--board", board, "--rank", "17", "--no-ai",
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-player", "0,0", "--block-target", "0,0",
            "--p-units", "%s,%s" % (CASTER, allie), "--a-units", ennemis]
    if drop_passive:
        argv += ["--unit-stat", "%s:PassiveAbilities=[]" % CASTER]
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
    """`observeBattle` indexe ses unites par `squadId`, PAS par `id` (piege releve par #511 : lire
    `id` rend `None` partout et un dict de deltas VIDE des DEUX cotes est un accord DEGENERE)."""
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


def _effect_row(dv, uid, etype):
    for u in _units(dv):
        if u.get("id") == uid:
            for e in (u.get("effects") or []):
                if isinstance(e, dict) and e.get("effectType") == etype:
                    return e
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


def _montants_natifs(res):
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des events du pas `UnitDamaged`)."""
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != S_UNIT_DAMAGED:
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Amount" in t:
                out.append((t.get("Target_Id"), t.get("Amount"),
                            t.get("Attack_DidCrit"), t.get("Attack_DidBlock")))
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
    """MT du port avec COMPTEUR DE TIRAGES. `mti` est CYCLIQUE (0..624) : sa difference ne compte
    rien. `IntBasedMersenneTwister` porte `__slots__`, d'ou la sous-classe a la volee."""

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


def _drive_a_portee(rpc, rid, portee=RANGE, tours=12, exclus=()):
    """DEPLACE Calandis jusqu'a avoir un ennemi a portee (doctrine drive-positions : on ne se plaint
    JAMAIS de la geometrie de spawn). Rend `(calandis, cible)` ou `(None, None)`."""
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

def step_damage(board, seed, allie, ennemis, drop_passive=False):
    """VOLET 1 -- l'attaque NORMALE dispatchee : sequence coup par coup, tirages, etat MT."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    rpc = _mk_rpc(R, R._resolve_session())
    rid, state = _build(board, seed, allie, ennemis, drop_passive)
    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]
        dv0, ob0, st = _capture(rpc, rid, brd)
        if st.get_entity(cid) is None:
            print("caster absent de l'etat offline -- NON CONFRONTE")
            return 1
        rng = _cale_mt(rpc, rid, st)
        avant = {u["id"]: _hp(ob0, u["id"]) for u in _units(dv0)}
        tirages_avant, mti_avant = rng.tirages, rng.mti

        res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                              "abilityType": ABILITY})
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print("cast REFUSE par le natif (%r) -- NON CONFRONTE" % (a0,))
            return 1
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
        atk = (diag.get("attack") or {})
        print("caster=%s target=%s  distance=%s  hp_live_avant=%s"
              % (cid, tid, hexgeo.distance(_pos(me), _pos(tgt)), avant.get(tid)))
        print("   ported=%s  diag=%s"
              % (diag.get("ported"), {k: diag.get(k) for k in
                                      ("ability", "reset", "reset_reopened", "effect_placed")}))
        print("   attaque(port) = %s" % (atk,))
        print("   deltas HP  live=%s  port=%s  %s"
              % (live, off, "ACCORD" if live == off else "DESACCORD"))
        print("   tirages rng consommes (port) = %d" % (rng.tirages - tirages_avant))
        print("   SEQUENCE natif = %s" % (_montants_natifs(res),))
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        same_mt = None
        if _ok(s1):
            same_mt = (list(s1.get("mt") or []) == list(rng.mt)) and s1.get("mti") == rng.mti
            print("   MT : mti avant=%s ; apres -> natif=%s port=%s ; etats EGAUX ? %s"
                  % (mti_avant, s1.get("mti"), rng.mti, same_mt))
        if live != off or diag.get("ported") is not True:
            rc = 1
        if not live:
            # ACCORD EN REGIME DEGENERE = ZERO PREUVE.
            print("   !! AUCUN delta HP live -- temoin NUL, la comparaison ne prouve rien")
            rc = 1
        if same_mt is False:
            print("   !! MT DESYNCHRONISE apres le cast -- l'etage RNG a diverge, pas l'etage degat")
            rc = 1
        print("VERDICT DAMAGE: %s" % ("ACCORD" if rc == 0 else "DESACCORD"))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_reset(board, seed, allie, ennemis, drop_passive=False):
    """VOLET 2 -- `ResetMovement(Owner)` : Calandis BOUGE, caste, et doit pouvoir RE-bouger."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.messages import ActiveAbilityMessage, MoveUnitMessage
    from engine.runner.runner import Runner

    R = _host()
    rpc = _mk_rpc(R, R._resolve_session())
    rid, state = _build(board, seed, allie, ennemis, drop_passive)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid, tid = me["id"], tgt["id"]

        # LE PAS PREALABLE : c'est lui qui pose `Moved`/`ArrivedAtFinalTile` et rend le reset
        # OBSERVABLE. `_drive_a_portee` l'a le plus souvent DEJA consomme -- dans ce cas
        # `aiMovableTiles` est deja VIDE, et c'est le regime voulu.
        depart, cible_pos = _pos(me), _pos(tgt)
        mov_avant_cast = _movable(rpc, rid, cid)
        if mov_avant_cast:
            pas = [t for t in mov_avant_cast
                   if t != depart and 1 <= hexgeo.distance(t, cible_pos) <= RANGE]
            if pas:
                dest = min(pas, key=lambda t: (hexgeo.distance(t, depart), t))
                _act(rpc, rid, {"kind": "move", "unitId": cid,
                                "to": {"col": dest[0], "row": dest[1]}}, 60)
                mov_avant_cast = _movable(rpc, rid, cid)
        if mov_avant_cast:
            print("Calandis a ENCORE du mouvement avant le cast (%d tuiles) -- le reset ne serait "
                  "pas observable, montage NON CONFORME" % len(mov_avant_cast))
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
        port_pas_de_recast = fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)
        print("NATIF : tuiles mobiles avant cast = %d ; apres cast = %d -> re-deplacable ? %s"
              % (len(mov_avant_cast), len(mov_apres_cast), nat_rebouge))
        print("PORT  : flags avant=%s apres=%s ; Moved absent ? %s ; ActiveAbilityUsed present ? %s"
              % (port_avant, port_apres, port_rebouge, port_pas_de_recast))
        ok = (nat_rebouge is True and port_rebouge is True and port_pas_de_recast is True)
        # Le natif RE-deplace-t-il vraiment ? on le JOUE -- seule preuve non derivee.
        if mov_apres_cast:
            d2 = sorted(mov_apres_cast)[0]
            r = _act(rpc, rid, {"kind": "move", "unitId": cid,
                                "to": {"col": d2[0], "row": d2[1]}}, 60)
            a0 = ((r or {}).get("actions") or [{}])[0]
            print("SECOND PAS joue vers %s : ok=%s mutated=%s"
                  % (d2, a0.get("ok"), a0.get("mutated")))
            runner.apply(MoveUnitMessage(int(cid), (int(d2[0]), int(d2[1]))))
            ok = ok and bool(a0.get("mutated"))
        print("VERDICT RESET: %s"
              % ("ACCORD -- ResetMovement mord des DEUX cotes" if ok else "DESACCORD"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_effect(board, seed, allie, ennemis, drop_passive=False):
    """VOLET 3 -- l'effet 1110 : POSE SUR LE CASTER, duree, niveau d'ability bake."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import has_effect_of_type
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    R = _host()
    rpc = _mk_rpc(R, R._resolve_session())
    rid, state = _build(board, seed, allie, ennemis, drop_passive)
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
        eff_caster_avant = _effects(dv0, cid)
        eff_cible_avant = _effects(dv0, tid)

        _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                        "abilityType": ABILITY})
        runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
        dv1i = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                    "includeInactive": True}, 150)
        eff_caster_apres = _effects(dv1i, cid)
        eff_cible_apres = _effects(dv1i, tid)
        nat_porte = EFFECT in (eff_caster_apres or [])
        nat_sur_cible = EFFECT in (eff_cible_apres or [])
        port_porte = has_effect_of_type(st, cid, EFFECT)
        port_sur_cible = has_effect_of_type(st, tid, EFFECT)
        row = _effect_row(dv1i, cid, EFFECT)

        print("CASTER %s : effets avant=%s ; apres (natif, inactifs inclus)=%s"
              % (cid, eff_caster_avant, eff_caster_apres))
        print("   1110 sur le CASTER  -> natif=%s  port=%s" % (nat_porte, port_porte))
        print("   1110 sur la CIBLE   -> natif=%s  port=%s  (doit etre False des deux cotes : "
              "`targets` = Caster@+0x48)" % (nat_sur_cible, port_sur_cible))
        print("CIBLE  %s : effets avant=%s ; apres=%s" % (tid, eff_cible_avant, eff_cible_apres))

        from engine.runner.abilities.base import (convert_rounds_to_turns,
                                                  turns_until_end_of_current_players_next_turn)
        print("DUREE : natif remaining=%s ; TurnsFromRounds(1)=%s ; "
              "TurnsUntilEndOfCurrentPlayersNextTurn=%s (la duree VOISINE, +1 tour)"
              % (None if row is None else row.get("remaining"),
                 convert_rounds_to_turns(st, 1),
                 turns_until_end_of_current_players_next_turn(st)))

        inst = next((e for e in (st.effects.by_unit.get(cid) or [])
                     if e.effect_type == EFFECT), None)
        if inst is not None:
            print("SCALE : classe=%s active_ability_level=%s multiplier=%s"
                  % (type(inst).__name__, inst.active_ability_level,
                     inst.ability_variables_multiplier))
            # Le bonus dans le SEUL regime ou le natif soustrait (ranged, tour ennemi).
            eb = inst.create_effect_damage_malus_for_defense(False, None,
                                                             {"is_turn_of_owner": False})
            print("        bonus ranged/tour-ennemi = %s"
                  % (None if eb is None else [eb.kind, eb.value],))

        ok = (nat_porte is True and port_porte is True
              and nat_sur_cible is False and port_sur_cible is False
              and inst is not None and inst.active_ability_level is not None)
        print("VERDICT EFFECT: %s" % ("ACCORD" if ok else "DESACCORD"))
        return 0 if ok else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_gate(board, seed, allie, ennemis, drop_passive=False):
    """VOLET 4 -- le MASQUE `TARGETING_OPTIONS`, confronte cible par cible.

    Le natif est interroge par `applyAction` (un cast REFUSE rend `mutated=False` + une `reason`),
    le port par `get_invalid_target_reason`. On balaye TOUTES les unites vivantes -- amies comprises,
    puisque c'est `TargetIsEnemy` (0x4000) qui doit les refuser -- et le CASTER lui-meme.

    ⚠ Le natif est interroge sans MUTER : on utilise l'endpoint `abilityTargets`, qui expose
    l'ensemble des cibles legales SANS jouer le cast (le seul canal qui permette de balayer plus
    d'une cible par runner). On lit **`fromHere`**, PAS `targets` : `targets` inclut le deplacement
    (superset << ce tour >>), alors que le port evalue depuis la TUILE COURANTE -- comparer au
    superset ferait passer pour un desaccord tout ce qui n'est atteignable qu'apres un pas."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason

    R = _host()
    rpc = _mk_rpc(R, R._resolve_session())
    rid, state = _build(board, seed, allie, ennemis, drop_passive)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        me, tgt = _drive_a_portee(rpc, rid)
        if me is None or tgt is None:
            print("aucune configuration a portee -- NON CONFRONTE")
            return 1
        cid = me["id"]
        dv0, ob0, st = _capture(rpc, rid, brd)
        nat = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        if not _ok(nat):
            print("abilityTargets KO (%r) -- NON CONFRONTE" % (str(nat)[:200],))
            return 1
        legales, vus = set(), 0
        for urow in (nat.get("units") or []):
            if urow.get("unitId") != cid:
                continue
            for arow in (urow.get("abilities") or []):
                if arow.get("abilityId") != ABILITY:
                    continue
                vus += 1
                for t in (arow.get("fromHere") or []):
                    if isinstance(t, dict) and t.get("targetId") is not None:
                        legales.add(int(t["targetId"]))
        if vus == 0:
            print("abilityTargets ne publie AUCUNE ligne pour (unit=%s, ability=%s) -- "
                  "NON CONFRONTE" % (cid, ABILITY))
            return 1
        cls = ABILITY_CLASSES.get(ABILITY)
        ability = cls()
        lignes, ecarts = [], []
        for u in _units(dv0):
            uid = u["id"]
            d = hexgeo.distance(_pos(me), _pos(u))
            nat_ok = uid in legales
            port_reason = get_invalid_target_reason(st, cid, uid, ability)
            port_ok = (port_reason == 0)
            lignes.append((uid, u.get("visualId"), u.get("owner") == me.get("owner"), d,
                           nat_ok, port_ok, hex(port_reason)))
            if nat_ok != port_ok:
                ecarts.append(lignes[-1])
        print("CASTER %s (%s) -- masque 0x%x ; %d cible(s) legale(s) cote natif (fromHere)"
              % (cid, CASTER, cls.TARGETING_OPTIONS.rules, len(legales)))
        for l in lignes:
            print("   uid=%-4s %-22s ami=%-5s d=%-3s natif=%-5s port=%-5s reason=%s" % l)
        if not legales:
            # Un balayage ou le natif n'accepte RIEN est un accord DEGENERE : le port pourrait tout
            # refuser pour la mauvaise raison et personne ne le verrait.
            print("!! le natif n'accepte AUCUNE cible -- temoin NUL, le balayage ne prouve rien")
            return 1
        print("VERDICT GATE: %s" % ("ACCORD (%d cibles balayees)" % len(lignes) if not ecarts
                                    else "DESACCORD sur %d cible(s) : %r" % (len(ecarts), ecarts)))
        return 0 if not ecarts else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


STEPS = {"damage": step_damage, "reset": step_reset, "effect": step_effect, "gate": step_gate}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="damage", choices=sorted(STEPS) + ["all"])
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--allie", default="eldarFarseer")
    ap.add_argument("--ennemis", default="necroWarden,necroDestroyer")
    ap.add_argument("--drop-passive", action="store_true",
                    help="retire 1111 WireweaveNet du porteur (isolement du flux MT)")
    a = ap.parse_args()
    steps = sorted(STEPS) if a.step == "all" else [a.step]
    rc = 0
    for s in steps:
        print("\n===== STEP %s (board=%s seed=%s) =====" % (s, a.board, a.seed))
        rc |= STEPS[s](a.board, a.seed, a.allie, a.ennemis, a.drop_passive)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
