"""probe #226-r -- le per-hit de `SkyStrike` (1025) est-il PLAT ou porte-t-il le spread +-20 % ?

CE QUE CA TRANCHE (question binaire). Le noeud de degat de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` est
`Sum(NormalAttackDamage(caster), Direct(GetVariableForLevel(8=extraDmg)))`. `NormalAttackDamage`
construit un `IdunBattle.Entities.Formulas.StatAmountFormula` -- LE MEME noeud que celui de
l'ATTAQUE NORMALE (`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$
AttackAmount` appelle `IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage`, xrefs verifiees).
Le port (`engine/runner/abilities/sisterhood.py`) lit ce noeud comme DEGENERE -> `HitDamage(V, V)`
-> coups tous EGAUX. Le cast LIVE, lui, rend des coups INEGAUX.

DECOMPOSITION PAR ETAGE (aucun scalaire fitte) -- meme etat, MEME rng dumpe avant le cast :
  E0  live      : les N coups reellement emis par le natif (tags `Amount`)
  E1  V         : Attack(caster) + extraDmg[level], relu de l'etat offline
  E2  modele A  : port ACTUEL -- `execute_ability_attack(V, V, ...)` bornes DEGENEREES
                  (roll-then-reduce, 2 tirages/coup) -> coups egaux
  E3  modele B  : `execute_normal_like(base=V, spread_pct=20)` -- reduce-then-roll, LE pipeline
                  de l'attaque normale (`IdunBattle.Core.Services.DamagePrediction$$
                  GetBaseDamageFix64` applique le spread aux BORNES, puis 1 tirage/coup)
  E4  modele C  : bornes BRUTES [V-delta, V+delta] en roll-then-reduce (2 tirages/coup)

VERDICT = celui des trois qui est BIT-EXACT sur les N coups. Trois coups tires dans une plage de
~1200 valeurs : une coincidence est a ~1e-9, donc l'egalite bit-exacte IDENTIFIE le pipeline (et
son nombre de tirages), elle ne le « fitte » pas.

Porteur `adeptCelestine` = HERO hors seed BC -> injecte par
`catalog_inject.write_augmented_seed_bc` (bloc `Units` **ET** configs `Abilities`, cf. #226 : un
clone de bloc Unit porterait les stats de l'unite CLONEE et un seed sans `BC.Abilities` leve
`system error`). La cible est COLLEE au caster : le gate `Not(IsAdjacent)` est faux, aucun move,
on isole l'ATTAQUE.

Usage :
  python probe_226r_skystrike_spread.py                 # 1 cast
  python probe_226r_skystrike_spread.py --seeds 777,31337,4242
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import catalog_inject as CI
import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs" / "runners"
BOARD = "MC1_67"
CASTER_VIS = "adeptCelestine"
ABILITY = 1025
A_UNITS = "necroWarden,necroWarden,necroOverlord"


# --------------------------------------------------------------------------- montage

def bind_ambient(sans_canal: bool = False):
    """LIE le canal `unitAbilityStates` en AMBIANT (`snapshot.bind_live_rpc`, #363).

    ⚠ OBLIGATOIRE ICI, et le montage le rend NON EVIDENT (#448-r3-r1-r1). `restrict_abilities`
    RESTREINT le kit du caster dans le BC (`ActiveAbilities=[1025]`, `PassiveAbilities=[]`) : le BC
    porte donc MOINS que le gameconfig -- une greffe en sens INVERSE. Sans le canal, le port derive
    le kit du gameconfig et monte des abilities que la bataille N'A PAS montees (ici
    `GeminaeSuperia`). La divergence est aussi muette qu'une greffe manquante.

    `sans_canal=True` rejoue le regime d'AVANT (canal muet, registre de greffes purge donc pas de
    refus) -- c'est la contre-epreuve, pas un mode d'usage."""
    if sans_canal:
        CI.clear_declared_grafts()
        print("[canal] MUET (--sans-canal) -- regime d'AVANT, kit gameconfig complet cote port")
        return None
    from engine.runner.snapshot import bind_live_rpc
    prev = bind_live_rpc(
        lambda method, body=None, timeout=60:
            L._rpc(method, [body if body is not None else {}], int(timeout * 1000)))
    print("[canal] `unitAbilityStates` LIE en ambiant (bind_live_rpc)")
    return prev


def _write_seed_bc(tag: str):
    if not CI.SEED_BC.exists():
        return None
    path, _u, _a = CI.write_augmented_seed_bc(
        LOGS / ("bc-226r-%s.json" % tag), [CASTER_VIS],
        restrict_abilities={CASTER_VIS: ([ABILITY], [])})
    return path


def _build_runner(bc_file: Path, tag: str, seed: int, armor_target: int = 0):
    state = LOGS / ("rs-226r-%s.json" % tag)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state),
            "--seed-bc", str(bc_file), "--board", BOARD, "--roster", "1",
            "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "300000"]
    if armor_target:
        # regime DISCRIMINANT de l'etage reduction : le plancher `max(0, d - armure, d x pierce%)`
        # bascule sur la branche PERCAGE (bornes fractionnaires -> materialisation visible).
        argv += ["--armor-target", str(int(armor_target))]
    proc = subprocess.run(
        argv,
        cwd=str(HERE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("[226r] build KO: %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return None, state
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"]), state


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _drive_adjacent(rid, charge: bool = False):
    """Amene Celestine a son tour puis place une cible ennemie :
      * `charge=False` (defaut) : COLLEE (voisine libre) -> gate `Not(IsAdjacent)` faux, AUCUN move,
        on isole l'ATTAQUE ;
      * `charge=True`           : a distance 2 -> le gate passe, Celestine CHARGE puis attaque
        (verifie que le MoveUnit ne desynchronise pas la sequence de tirages).
    Renvoie (board, casterId, targetId) ou (None, None, None)."""
    from engine.entities.pathfinding.board import Board
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None, None, None
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = me = None
    for _ in range(14):
        dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
        me = _find(dv, CASTER_VIS)
        if me is not None and dv.get("currentPlayer") == me.get("owner"):
            break
        L._rpc("aiPlayTurn", [{"runnerId": rid}])
    if me is None:
        return None, None, None
    tgt = next((u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != me.get("owner")), None)
    if tgt is None:
        return None, None, None
    mp = me.get("pos") or {}
    cpos = (mp.get("col"), mp.get("row"))
    tid = board.id_at(mp.get("col"), mp.get("row"))
    occ = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or []) if u.get("alive")}
    if charge:
        import hexgeo
        dest = next((t for t in sorted(board.by_id)
                     if board.walkable(t) and board.coord(t) not in occ
                     and hexgeo.distance(board.coord(t), cpos) == 2
                     and any(board.walkable(n) and board.coord(n) not in occ
                             for n in board.neighbours(t))), None)
    else:
        dest = next((n for n in board.neighbours(tid)
                     if board.walkable(n) and board.coord(n) not in occ), None)
    if dest is None:
        return None, None, None
    dc = board.coord(dest)
    L._rpc("applyAction", [{"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt["id"], "to": {"col": dc[0], "row": dc[1]}}}])
    return board, me["id"], tgt["id"]


# --------------------------------------------------------------------------- offline

def _state_builder(rid, board):
    """Capture l'etat AVANT le cast (dv/ob/snap + rng) -> fabrique d'etats rejouables."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    dv = L._rpc("decisionView", [{"runnerId": rid, "maxRank": 1, "allAbilities": True}])
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    snap = L._rpc("combatSnapshot", [{"runnerId": rid}])
    rng0 = L._rpc("dumpRng", [{"runnerId": rid}])

    def build():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"])
            r.mti = rng0["mti"]
            st.rng = r
        return st
    return build


def _caster_params(state, cid):
    """(V = Attack + extraDmg, pierce melee, MeleeWeaponHits, profil melee)."""
    from engine.runner.components import StatsComponent
    from engine.runner.damage_model import select_weapon, select_weapon_pierce
    from engine.entities.stats import StatType
    from engine.entities.effects.magnitude import ability_var
    ctx = state.get_entity(cid).get_component(StatsComponent).ctx
    atk = int(ctx.stats.get_stat(int(StatType.ATTACK), 0))
    pierce, _ranged, whits = select_weapon_pierce(ctx, 1)
    profile = (select_weapon(ctx, 1) or {}).get("DamageProfile") or "Power"
    extra = int(ability_var("SkyStrike", "extraDmg", ctx.active_ability_level,
                            multiplier_pct=ctx.ability_variables_multiplier) or 0)
    return atk + extra, atk, extra, pierce, int(whits), profile


def _model_a(build, cid, tid):
    """Port ACTUEL : arbre SkyStrike -> bornes DEGENEREES (V, V)."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    st = build()
    res = SkyStrikeAbility().execute_behaviour(st, cid, tid)
    inner = ((res or {}).get("attack") or {}).get("attack") or {}
    return list(inner.get("per_hit") or [])


def _model_b(build, cid, tid, V, pierce, hits, profile):
    """Spread +-20 % en reduce-then-roll = pipeline de l'ATTAQUE NORMALE."""
    from engine.runner.operations.damage import AttackDamageOperation
    st = build()
    r = AttackDamageOperation.execute_normal_like(
        st, cid, tid, int(V), int(pierce), hits=int(hits), spread_pct=20,
        damage_profile=profile, is_melee=True, ability_type=ABILITY,
        is_attack_damage_op=True)
    return list((r or {}).get("per_hit") or [])


def _model_c(build, cid, tid, V, pierce, hits, profile):
    """Bornes BRUTES [V-delta, V+delta] en roll-then-reduce (mode bornes du port)."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.services.damage_calculations import spread_to_min_max
    mm = spread_to_min_max(int(V), 20)
    st = build()
    r = AttackDamageOperation.execute_ability_attack(
        st, cid, tid, int(mm.min), int(mm.max), int(pierce), int(hits),
        damage_profile=profile, is_melee=True, is_attack_damage_op=True)
    return list((r or {}).get("per_hit") or [])


# --------------------------------------------------------------------------- run

def run_once(seed: int, charge: bool = False, armor_target: int = 0,
             sans_canal: bool = False) -> dict:
    tag = "%s-%s" % (seed, uuid.uuid4().hex[:6])
    out = {"seed": seed, "live": None, "A": None, "B": None, "C": None,
           "charge": charge, "armor_target": armor_target}
    bc_file = _write_seed_bc(tag)
    if sans_canal:
        CI.clear_declared_grafts()      # neutralise le refus : on veut le VERDICT d'avant
    if bc_file is None:
        print("[226r] seed BC de reference absent (data/seed-bc.json)")
        return out
    rid, state = _build_runner(bc_file, tag, seed, armor_target)
    try:
        if rid is None:
            return out
        board, cid, tid = _drive_adjacent(rid, charge=charge)
        if cid is None:
            print("[226r] drive KO (geometrie / Celestine absente)")
            return out
        build = _state_builder(rid, board)
        st0 = build()
        V, atk, extra, pierce, whits, profile = _caster_params(st0, cid)
        from engine.runner.damage_model import defender_fixed_armor
        armor = defender_fixed_armor(st0, tid)
        out.update({"V": V, "attack": atk, "extraDmg": extra, "pierce": pierce,
                    "hits": whits, "profile": profile, "armor": armor})
        print("[226r seed=%s charge=%s] caster attack=%s extraDmg=%s -> V=%s ; pierce=%s hits=%s "
              "profil=%s ; armure cible=%s"
              % (seed, charge, atk, extra, V, pierce, whits, profile, armor))

        cast = L._rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}])
        errs = [a.get("error") for a in (cast.get("actions") or []) if a.get("error")]
        live = []
        for a in (cast.get("actions") or []):
            for ev in (a.get("events") or []):
                td = ev.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY \
                        and td.get("Target_Id") == tid:
                    live.append(td.get("Amount"))
        out["live"] = live
        out["errors"] = errs
        print("[226r seed=%s] LIVE ok=%s errors=%s hits=%s" % (seed, cast.get("ok"), errs, live))

        out["A"] = _model_a(build, cid, tid)
        out["B"] = _model_b(build, cid, tid, V, pierce, whits, profile)
        out["C"] = _model_c(build, cid, tid, V, pierce, whits, profile)
        for k in ("A", "B", "C"):
            print("  modele %s = %s   %s" % (k, out[k], "BIT-EXACT" if out[k] == live else "!="))
    finally:
        if rid is not None:
            try:
                L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:
                pass
        for p in (bc_file, state):
            try:
                p.unlink()
            except Exception:
                pass
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="probe #226-r : per-hit SkyStrike plat ou spread ?")
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--charge", action="store_true",
                    help="cible a distance 2 -> Celestine CHARGE avant d'attaquer (le modele A seul "
                         "est alors comparable : B/C sont calcules SANS le move)")
    ap.add_argument("--armor-target", type=int, default=0,
                    help="force l'armure des a-units (regime discriminant de l'etage reduction)")
    ap.add_argument("--sans-canal", action="store_true",
                    help="CONTRE-EPREUVE : rejoue le regime d'AVANT #448-r3-r1-r1 (canal "
                         "`unitAbilityStates` muet, kit derive du gameconfig)")
    a = ap.parse_args(argv)
    bind_ambient(a.sans_canal)
    rows = [run_once(int(s.strip()), charge=a.charge, armor_target=a.armor_target,
                     sans_canal=a.sans_canal)
            for s in a.seeds.split(",") if s.strip()]
    print("=== SYNTHESE #226-r ===")
    for r in rows:
        live = r.get("live")
        print("  seed=%-6s V=%-6s armure=%-6s charge=%-5s live=%s"
              % (r["seed"], r.get("V"), r.get("armor"), r.get("charge"), live))
        for k in ("A", "B", "C"):
            print("      %s %-40s %s" % (k, str(r.get(k)), "== live" if r.get(k) == live else "!= live"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
