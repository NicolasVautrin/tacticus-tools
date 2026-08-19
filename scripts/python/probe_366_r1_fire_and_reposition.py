"""case-366-r1 -- MONTAGE LIVE de `1110 FireAndReposition_ReduceDmg` (porteur `eldarRanger`
<<Calandis>>, pose par son active `FireAndReposition` 1063).

CRITERE BINAIRE : << le port retire du degat RECU par Calandis exactement ce que le natif retire,
et se TAIT exactement quand le natif se tait ? >>

Le natif (`...FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense`) est
`EffectBonus.ForSubtraction( OwnerIsTarget & IsRangedAttack & NOT IsTurnOf(Owner),
ConfigVar(0x12 = dmgReduction) )`. Il y a donc TROIS gates, et un montage qui n'en exerce qu'un
ne prouve rien. Ce probe les separe :

  E1 -- POSE + GATE DE TOUR, cote NATIF. Apres le cast, `EffectComponent.IsActive` de l'effet
        (canal `decisionView.effects[].active`, champ ECS relu par le hook) vaut **False** pendant
        le tour de Calandis et **True** au tour ennemi. C'est le gate `NOT IsTurnOf(Owner)` mesure
        SUR LE NATIF, sans rien deduire du port.
  E2 -- DEGAT RANGED, tour ENNEMI (regime NOMINAL). Le meme coup joue LIVE et rejoue OFFLINE sur la
        MEME capture et le MEME flux MT. Trois valeurs :
          * `live`            : ce que le natif a inflige ;
          * `port`            : ce que le port calcule ;
          * `port_sans_effet` : CONTRE-EPREUVE -- l'effet retire du monde offline. Sans elle,
            << port == live >> ne prouverait pas que la reduction y change quoi que ce soit.
  E3 -- CONTREFACTUEL DE TOUR (offline). MEME capture, MEME flux, on force `current_player_id` au
        joueur de Calandis : le port doit alors rendre EXACTEMENT `port_sans_effet`. C'est ce qui
        prouve que le gate `NOT IsTurnOf(Owner)` du port est PORTEUR et pas decoratif.
  E4 -- AXE MELEE (`--axis melee`) : le meme effet present, un coup de MELEE. Le gate
        `IsRangedAttack` doit fermer -- natif ET port -- donc `live == port == port_sans_effet`.

L'armure de Calandis est mise a 0 (`--hp-player`) : la reduction PLATE est PRE-percage, donc a
armure nulle elle se lit 1 pour 1 sur le degat. `--dmg-target` remonte la frappe ennemie au-dessus
de la reduction : sans lui le degat plancherait a 1 dans les deux bras et la mesure serait aveugle
(MESURE : `necroWarden` non dope frappe ~1806, la reduction vaut 2992 -> live = [1, 1]).

Usage :
    python probe_366_r1_fire_and_reposition.py --axis ranged --board MC1_67 --seed 31337
    python probe_366_r1_fire_and_reposition.py --axis melee  --board C4_09  --seed 4242

Consommateur pytest : `tests/engine/runner/test_fire_and_reposition_reduce_dmg_live.py`.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "eldarRanger"        # <<Calandis>> -- HERO, dans le pool spawnable du rank courant
FOE = "necroWarden"            # <<Makhotep>> -- porte UNE arme melee ET une arme ranged r3 :
#                                le MEME ennemi sert les deux axes, une variable de moins
ABILITY = "FireAndReposition"
ABILITY_ID = 1063              # 0x427 -- ActiveAbilityType (le `.ctor` de l'effet l'ecrit en edx)
EFFECT = 1110                  # 0x456 -- EffectType FireAndReposition_ReduceDmg
DMG_TARGET = 20000             # frappe ennemie > reduction (sinon plancher a 1, cf. docstring)
HP_PLAYER = 400000             # Calandis encaisse plusieurs echanges ; met AUSSI son armure a 0
HP_TARGET = 300000             # l'ennemi SURVIT au cast. `FireAndReposition` ENCHAINE une attaque
#                                normale de Calandis (`UseActiveAbility`) et elle le mitraille en
#                                OVERWATCH pendant son approche : sans ce plancher, l'axe MELEE le
#                                tuait AVANT la pose et la bataille se terminait (mesure : hp 5061
#                                -> 1446 a l'approche, puis Match_Winner au cast)
BOARD = "MC1_67"
SEED = "31337"


# --------------------------------------------------------------------------- build
def build_args(board: str, drop_passive: bool = False, active_level: int | None = None) -> list:
    """`--unit-stat` sert DEUX leviers, tous deux appliques au BC DEJA normalise :

      * `PassiveAbilities=[]` -- retire `1111 WireweaveNet` du porteur. Sa contre-attaque
        (<< the first time Calandis is targeted by a normal melee attack during the enemy's turn >>)
        n'est PAS portee (ability de la tache voisine) et CONSOMME du flux MT avant le coup mesure :
        sans ce retrait, le rejeu offline de l'axe MELEE part decale et la comparaison ne mesure
        plus la reduction mais le tirage (MESURE : contre-attaque live [2373, 2664]).
      * `ActiveAbilityLevel=N` -- DISSOCIE le niveau ACTIF du niveau PASSIF, que la normalisation
        met tous deux a 50. C'est le SEUL regime qui discrimine lequel des deux indexe
        `variables["dmgReduction"]`, donc le seul qui puisse REFUTER la lecture
        << `GetAbilityState(effet)` = l'AbilityState de l'ACTIVE >> tiree du `.ctor` (`mov edx,0x427`
        puis la surcharge `op_Implicit` qui appelle `set_ActiveAbility`).
    """
    out = ["--p-units", CARRIER, "--a-units", FOE,
           "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           "--hp-player", str(HP_PLAYER), "--hp-target", str(HP_TARGET),
           "--dmg-target", str(DMG_TARGET),
           "--board", board]
    if drop_passive:
        out += ["--unit-stat", "%s:PassiveAbilities=[]" % CARRIER]
    if active_level is not None:
        out += ["--unit-stat", "%s:ActiveAbilityLevel=%d" % (CARRIER, int(active_level))]
    return out


def _build_subprocess(seed: str, axis: str, board: str, drop_passive: bool = False,
                      active_level: int | None = None) -> int:
    state = _ROOT / "logs" / ("_probe366r1far-%s-%d.json" % (axis, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board, drop_passive, active_level)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- lecture live
def _unit(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _by_vis(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`, dans l'ordre des events + flag de salete (crit /
    block / evade rendraient le coup non comparable a un rejeu deterministe)."""
    out, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and "Amount" in td:
                out.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return out, dirty


# --------------------------------------------------------------------------- pilotage
def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 90)


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _place_at_distance(rpc, rid, mover_vis, anchor_vis, want, tries=25):
    """DEPLACE `mover_vis` jusqu'a la distance hex `want` d'`anchor_vis`. On FABRIQUE la geometrie,
    on ne la subit pas -- le meme ennemi sert l'axe ranged (3) et l'axe melee (1)."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv, an = _by_vis(dv, mover_vis), _by_vis(dv, anchor_vis)
        if mv is None or an is None:
            return None
        mpos = (mv["pos"]["col"], mv["pos"]["row"])
        apos = (an["pos"]["col"], an["pos"]["row"])
        if hexgeo.distance(mpos, apos) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, apos) - want),
                                         hexgeo.distance(t, apos)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
            "captureEvents": False}, 90)
        if hexgeo.distance(best, apos) == want:
            return want
        _endturn(rpc, rid)
    return None


def _ensure_turn(rpc, rid, owner, tries=6):
    """Fait tourner les fins de tour jusqu'a ce que `owner` soit le joueur courant. La CAPTURE doit
    etre prise dans le MEME etat de tour que le coup mesure."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == owner:
            return dv
        _endturn(rpc, rid)
    return None


# --------------------------------------------------------------------------- offline
def _capture(rpc, rid):
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                            "includeInactive": True}, 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board):
    from engine.runner.snapshot import load_state
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board)


def _strip_effect(st, carrier_id):
    """CONTRE-EPREUVE : retire 1110 du monde offline (instance consommee). Sert a montrer que le
    regime MORD -- sans ce controle, << le port reproduit le live >> ne prouverait rien."""
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type == EFFECT:
            e.consumed = True


def offline_hits(cap, board, caster_id, target_id, strip=False, force_player=None):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT -> per-coup du port.
      * `strip`        : sans l'effet 1110 (contre-epreuve de discriminance) ;
      * `force_player` : ecrase `State.current_player_id` -- CONTREFACTUEL du gate
        `NOT IsTurnOf(Owner)` (mirror `TurnComponent.CurrentPlayerId`)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    st = _load(cap, board)
    if strip:
        _strip_effect(st, target_id)
    if force_player is not None:
        st.current_player_id = int(force_player)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return list((last or {}).get("per_hit") or [])


def offline_effect_view(cap, board, carrier_id):
    """Ce que le PORT materialise pour 1110 sur cette capture : (present, classe, bonus rendu dans
    les 4 regimes de gate). Etage SEPARE du degat -- un port qui n'aurait PAS l'effet et un port
    dont le gate ferme rendent le meme degat."""
    st = _load(cap, board)
    inst = next((e for e in (st.effects.by_unit.get(carrier_id) or [])
                 if e.effect_type == EFFECT), None)
    if inst is None:
        return {"present": False}
    def _b(is_melee, turn_of_owner):
        eb = inst.create_effect_damage_malus_for_defense(
            is_melee, None, {"is_turn_of_owner": turn_of_owner})
        return None if eb is None else [eb.kind, eb.value]
    return {"present": True, "cls": type(inst).__name__,
            "active_ability_level": inst.active_ability_level,
            "multiplier": inst.ability_variables_multiplier,
            "ranged_enemy_turn": _b(False, False),   # le seul regime ou le natif soustrait
            "ranged_own_turn": _b(False, True),
            "melee_enemy_turn": _b(True, False),
            "unknown_ctx": None if inst.create_effect_damage_malus_for_defense(False, None, None)
            is None else "NON-NUL"}


# --------------------------------------------------------------------------- montage
def run(rpc, axis: str = "ranged", seed: str = SEED, board_id: str = BOARD,
        keep: bool = False, drop_passive: bool = True,
        active_level: "int | None" = None) -> dict:
    r = {"axis": axis, "seed": seed, "board": board_id, "rid": None,
         "drop_passive": drop_passive, "active_level_forced": active_level}
    try:
        _run(rpc, r, axis, seed, board_id, drop_passive, active_level)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:                             # nettoyage best-effort
                pass
    return r


def _run(rpc, r: dict, axis: str, seed: str, board_id: str, drop_passive: bool = True,
         active_level: "int | None" = None) -> None:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    want_dist = 1 if axis == "melee" else 3
    r["want_dist"] = want_dist

    rid = _build_subprocess(seed, axis, board_id, drop_passive, active_level)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, FOE)
    if car is None or foe is None:
        raise RuntimeError("porteur/cible absents du deploiement")
    r["carrier_id"], r["foe_id"] = car["id"], foe["id"]
    r["carrier_owner"], r["foe_owner"] = car.get("owner"), foe.get("owner")

    # -- niveau/mult de l'ACTIVE (c'est l'AbilityState que `GetAbilityState(effet)` resout)
    ab = next((a for a in (car.get("abilities") or []) if a.get("id") == ABILITY_ID), None)
    if ab is None:
        raise RuntimeError("l'active FireAndReposition n'est pas exposee sur le porteur")
    r["active_level"], r["multiplier"] = ab.get("level"), ab.get("multiplier")
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 120)
    _uc0 = next((u.get("unitConfig") or {} for u in (snap0.get("units") or [])
                 if u.get("entityId") == car["id"]), {})
    r["passive_level"] = _uc0.get("passiveAbilityLevel")
    r["dmg_reduction_config"] = ability_var(ABILITY, "dmgReduction", r["active_level"],
                                            multiplier_pct=r["multiplier"] or 100)
    # Ce que la MEME formule donnerait si le niveau lu etait le PASSIF : c'est la valeur que le
    # port rend aujourd'hui (le seed d'effets ne propage QUE le niveau passif, cf. case-doc §5).
    r["dmg_reduction_if_passive"] = ability_var(ABILITY, "dmgReduction", r["passive_level"],
                                                multiplier_pct=r["multiplier"] or 100)

    # -- geometrie FABRIQUEE (3 = arme ranged de Makhotep, 1 = son arme melee)
    if _place_at_distance(rpc, rid, FOE, CARRIER, want_dist) != want_dist:
        raise RuntimeError("distance %s non atteinte (axe %s)" % (want_dist, axis))

    # -- E1 : POSE + gate de tour, cote NATIF ------------------------------------------------
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du porteur non atteint (pose)")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": car["id"], "targetId": foe["id"],
        "abilityType": ABILITY_ID}}, 150)
    if not (isinstance(res, dict) and res.get("ok")):
        raise RuntimeError("cast FireAndReposition KO: %s" % (str(res)[:200],))
    r["cast_actions"] = [{k: v for k, v in (a or {}).items() if k in ("kind", "ok", "error",
                                                                     "mutated")}
                         for a in (res.get("actions") or [])]

    dvo = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dvoi = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 150)
    eo, eoi = _eff(_unit(dvo, car["id"]), EFFECT), _eff(_unit(dvoi, car["id"]), EFFECT)
    r["own_turn_in_active_channel"] = eo is not None
    r["own_turn_active_flag"] = None if eoi is None else eoi.get("active")
    r["own_turn_remaining"] = None if eoi is None else eoi.get("remaining")
    if eoi is None:
        r["effects_after_cast"] = [(e.get("effectType"), e.get("name"), e.get("active"))
                                   for e in ((_unit(dvoi, car["id"]) or {}).get("effects") or [])]
        raise RuntimeError("l'effet 1110 n'a pas ete pose par le cast (effets: %s ; cast: %s)"
                           % (r["effects_after_cast"], r.get("cast_actions")))

    # -- tour ENNEMI : l'effet doit s'ALLUMER
    if _ensure_turn(rpc, rid, foe["owner"]) is None:
        raise RuntimeError("tour ennemi non atteint")
    dve = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ee = _eff(_unit(dve, car["id"]), EFFECT)
    r["enemy_turn_in_active_channel"] = ee is not None
    r["enemy_turn_active_flag"] = None if ee is None else ee.get("active")
    r["enemy_turn_remaining"] = None if ee is None else ee.get("remaining")

    # la geometrie a pu bouger pendant les fins de tour -> on la REFABRIQUE
    if _place_at_distance(rpc, rid, FOE, CARRIER, want_dist) != want_dist:
        raise RuntimeError("distance %s non retablie avant le coup" % want_dist)
    if _ensure_turn(rpc, rid, foe["owner"]) is None:
        raise RuntimeError("tour ennemi non retabli")

    # -- COUP D'ECHAUFFEMENT (axe MELEE seulement) : `1111 WireweaveNet_CounterAttack` est
    #    << the FIRST time Calandis is targeted by a normal melee attack during the enemy's turn >>.
    #    Cette contre-attaque N'EST PAS PORTEE (ability de la tache voisine) et, surtout, elle
    #    CONSOMME du flux MT avant le coup mesure -> le rejeu offline part decale. On la brule donc
    #    AVANT la capture : le coup MESURE est alors le SECOND, et le flux redevient comparable.
    if axis == "melee" and not drop_passive:
        pre = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        pfoe = _unit(pre, foe["id"])
        pnorm = next((a for a in ((pfoe or {}).get("abilities") or [])
                      if a.get("kind") == "normal"), None)
        if pnorm is not None:
            w = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": foe["id"], "targetId": car["id"],
                "abilityType": pnorm["id"]}}, 150)
            wh, _ = live_amounts(w, car["id"])
            wc, _ = live_amounts(w, foe["id"])
            r["amorce_hits_on_carrier"], r["amorce_counter_on_foe"] = wh, wc
        if _place_at_distance(rpc, rid, FOE, CARRIER, want_dist) != want_dist:
            raise RuntimeError("distance %s non retablie apres echauffement" % want_dist)
        if _ensure_turn(rpc, rid, foe["owner"]) is None:
            raise RuntimeError("tour ennemi non retabli apres echauffement")

    # -- E2/E3/E4 : le COUP -------------------------------------------------------------------
    cap = _capture(rpc, rid)
    r["capture_current_player"] = cap["dv"].get("currentPlayer")
    r["port_effect_view"] = offline_effect_view(cap, board, car["id"])

    dvc = cap["dv"]
    foe_row = _unit(dvc, foe["id"])
    norm = next((a for a in ((foe_row or {}).get("abilities") or [])
                 if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune attaque normale exposee sur l'ennemi")
    resA = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": foe["id"], "targetId": car["id"],
        "abilityType": norm["id"]}}, 150)
    if not (isinstance(resA, dict) and resA.get("ok")):
        raise RuntimeError("coup live KO: %s" % (str(resA)[:200],))
    hits, dirty = live_amounts(resA, car["id"])
    if not hits:
        raise RuntimeError("coup joue mais aucun degat attribue au porteur")
    r["live_hits"], r["dirty"] = hits, dirty
    # Degats infliges a l'ENNEMI pendant le MEME echange = la contre-attaque `1111` (non portee) :
    # non vide -> du flux MT a ete consomme hors du port, et le rejeu offline n'est plus bit-exact.
    r["live_counter_on_foe"], _ = live_amounts(resA, foe["id"])

    r["port_hits"] = offline_hits(cap, board, foe["id"], car["id"])
    r["port_hits_without_effect"] = offline_hits(cap, board, foe["id"], car["id"], strip=True)
    # CONTREFACTUEL : meme capture, meme flux, mais c'est le tour de CALANDIS -> le gate
    # `NOT IsTurnOf(Owner)` doit fermer et rendre exactement `port_hits_without_effect`.
    r["port_hits_owner_turn"] = offline_hits(cap, board, foe["id"], car["id"],
                                             force_player=car["owner"])
    r["ok"] = True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=("ranged", "melee"), default="ranged")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--keep-passive", action="store_true",
                    help="NE PAS retirer 1111 WireweaveNet (sa contre-attaque decale le flux MT)")
    ap.add_argument("--active-level", type=int, default=None,
                    help="force BC.Units.ActiveAbilityLevel du porteur -- DISSOCIE actif/passif")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, axis=a.axis, seed=a.seed, board_id=a.board, keep=a.keep,
            drop_passive=not a.keep_passive, active_level=a.active_level)
    print(json.dumps(r, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1/1110/%s] runner=%s board=%s seed=%s dist=%s"
          % (a.axis, r["rid"], a.board, a.seed, r["want_dist"]))
    print("  config   : dmgReduction[ACTIF L%s] x mult %s = %s | si PASSIF L%s -> %s"
          % (r["active_level"], r["multiplier"], r["dmg_reduction_config"],
             r["passive_level"], r["dmg_reduction_if_passive"]))
    print("  E1 GATE NATIF : tour du PORTEUR  canal actif=%s  IsActive=%s (rem=%s)"
          % (r["own_turn_in_active_channel"], r["own_turn_active_flag"], r["own_turn_remaining"]))
    print("                  tour ENNEMI      canal actif=%s  IsActive=%s (rem=%s)"
          % (r["enemy_turn_in_active_channel"], r["enemy_turn_active_flag"],
             r["enemy_turn_remaining"]))
    print("  PORT effet    : %s" % (json.dumps(r["port_effect_view"], default=str),))
    print("  E2 DEGAT      : live=%s  port=%s" % (r["live_hits"], r["port_hits"]))
    print("     CONTRE-EPREUVE (sans l'effet, meme flux MT) : %s"
          % (r["port_hits_without_effect"],))
    print("  E3 CONTREFACTUEL de tour (current_player = porteur) : %s"
          % (r["port_hits_owner_turn"],))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
