"""case-418-r1 -- MONTAGE LIVE du noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget`,
sur le call-site `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$
IsPsykerAttackSuppressed` (inline dans son `$$CreateTrigger`).

CRITERE BINAIRE : << le splash << Smite >> du trait Psyker se TAIT-il exactement quand le natif le
tait ? >>

Ce que le natif ecrit (decompile) :

    CreateTrigger = On(0x26 NormalAttack) & get_OwnerIsActor & IsRangedAttack
                  & DamageProfileIs(0xd Psychic)
                  & NOT( IsEffectTarget(Caster@DSLSelectors+0x48, 0x4a7 = 1191)
                       | IsEffectTarget(Target@DSLSelectors+0x60, 0x5fd = 1533) )

`IsEffectTarget` resout sur `IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget(target,
effectType, onlyActive)`, qui balaye TOUTES les entites-effet du state
(`...$$GetEffectsWithTargets(unit = null, onlyActive)`) et teste
`EffectComponent.Targets @+0x48 .Contains(target.Id)`.

Or l'instance `1191` n'est PAS portee par le psyker : `IdunBattleLogic.Entities.Abilities.Triggered.
Loki.HuntersBeyondDeathAbility$$CreateBehaviour` = `AddEffect(0x4a7, ref, source = Owner, targets =
Owner, ...)`, donc `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` l'inscrit dans l'
`EffectsOwnedComponent` du PORTEUR du passif (mesure : `decisionView` la publie sur `spaceHound`,
`src = spaceHound`, sur AUCUNE autre unite). La liste de CIBLES, elle, est maintenue par
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` depuis
`...HuntersBeyondDeathPsykerSuppressionEffect$$CreateTargetSelector` =
`UnitsWithoutTrait( UnitsWithTrait( SurroundingEnemies(Owner@+0x30, unitTile@+0x50, range = 2,
unique = 1, sel = 3), 0x3ea Psyker, 3 ), 0x19, 3 )`.

=> C'est une AURA. Le predicat porte est << le psyker est-il ENNEMI, a distance hex <= 2, du porteur
de `HuntersBeyondDeath` >>, PAS << le psyker porte-t-il l'effet 1191 >>.

TROIS mesures, MEME build, MEMES unites -- seule la GEOMETRIE change (on la fabrique, on ne la
subit pas) :

  M1 `free`      -- psyker a d = 2 de la cible primaire ET d >= 3 de `spaceHound`. Le splash DOIT
                    firer (temoin : sans lui, << pas de splash >> ne prouverait rien).
  M2 `same_turn` -- le psyker se DEPLACE a d <= 2 de `spaceHound` puis tire DANS LE MEME TOUR.
                    Discrimine `EffectComponent.Targets` MATERIALISE (mis a jour par le refresh)
                    d'une re-derivation A LA LECTURE : si le natif ne supprime pas ici mais
                    supprime en M3, la liste native est en retard d'un refresh.
  M3 `after_turn`-- meme position qu'en M2, mais apres un cycle complet de tours (aucun
                    deplacement). Le splash doit etre SUPPRIME.

Chaque mesure rend, cote LIVE, la liste des degats par cible de l'attaque normale ; le splash est
present ssi un degat est attribue a une unite AUTRE que la cible primaire. Cote PORT, le meme coup
est rejoue OFFLINE sur la MEME capture et le MEME flux MT.

Usage :
    python probe_418_r1_is_effect_target.py                      # les 3 mesures
    python probe_418_r1_is_effect_target.py --board MC1_67 --seed 31337

Consommateur pytest : `tests/engine/runner/test_psyker_suppression_live.py`.
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

PSYKER = "astraPrimarisPsy"      # <<Sibyll>> -- HERO au pool, trait Psyker, arme RANGED r2 Psychic
SUPPRESSOR = "spaceHound"        # <<Tjark>> -- HERO au pool, SEUL porteur de `HuntersBeyondDeath`
FOE = "necroWarden"              # <<Makhotep>> -- 2e ennemi, sert de cible primaire ou de splash
EFF_SUPPRESS_OWNER = 1191        # 0x4a7 -- EffectType.HuntersBeyondDeathPsykerSuppression
EFF_SUPPRESS_TARGET = 1533       # 0x5fd -- EffectType.WatchedOver_PsykerSuppression
SUPPRESS_RANGE = 2               # `SurroundingEnemies(..., range = 2, ...)` du CreateTargetSelector

HP_TARGET = 400000               # personne ne meurt : les 3 mesures jouent sur le MEME runner
HP_PLAYER = 400000
BOARD = "MC1_67"
SEED = "31337"


# --------------------------------------------------------------------------- build
FOE2 = "necroSpyder"             # 2e ennemi du volet `ally` (fait le voisin de la cible primaire)


def build_args(board: str, variant: str) -> list:
    """`ally` DEPLACE le porteur du passif dans MON camp : `SurroundingEnemies` du
    `CreateTargetSelector` ne doit alors cibler AUCUN de mes psykers -> le splash reste ouvert.
    C'est le volet qui discrimine `SurroundingEnemies` de `SurroundingUnits`."""
    if variant == "ally":
        p_units, a_units = "%s,%s" % (PSYKER, SUPPRESSOR), "%s,%s" % (FOE, FOE2)
    else:
        p_units, a_units = PSYKER, "%s,%s" % (SUPPRESSOR, FOE)
    return ["--p-units", p_units, "--a-units", a_units,
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0",
            "--hp-player", str(HP_PLAYER), "--hp-target", str(HP_TARGET),
            "--board", board]


def _build_subprocess(seed: str, board: str, variant: str) -> int:
    state = _ROOT / "logs" / ("_probe418r1-%s-%d.json" % (variant, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board, variant)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- lecture live
def _by_vis(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def damage_by_target(res):
    """Per-coup LIVE, groupes par `Target_Id`, + flag de salete (crit/block/evade)."""
    out, dirty = {}, False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and td.get("Target_Id") is not None:
                out.setdefault(int(td["Target_Id"]), []).append(int(td["Amount"]))
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


def _normal_ability_id(dec, uid):
    u = next((x for x in (dec.get("units") or []) if x.get("id") == uid), None)
    return next((ab.get("id") for ab in ((u or {}).get("abilities") or [])
                 if ab.get("kind") == "normal"), None)


def _drive(rpc, rid, mover_vis, cost, tries=30, move_only=False):
    """Deplace `mover_vis` en MINIMISANT `cost(tile_pos, dec)`. Rend (pos_finale, moved_this_turn).

    `move_only` : ne joue AUCUN `endturn` apres le deplacement -- c'est ce qui permet la mesure
    << deplace PUIS tire dans le MEME tour >> (M2)."""
    import hexgeo                                   # noqa: F401  (garde la dependance explicite)
    moved = False
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        mv = _by_vis(dv, mover_vis)
        if mv is None:
            return None, moved
        here = _pos(mv)
        c_here = cost(here, dv)
        if c_here == 0:
            return here, moved
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: cost(t, dv))
        if cost(best, dv) < c_here:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
                "captureEvents": False}, 90)
            moved = True
            if cost(best, dv) == 0:
                return best, moved
        if move_only:
            return best, moved
        moved = False
        _endturn(rpc, rid)
    return None, moved


def _cost_free(psy_pos, dec):
    """M1 : psyker a d == 2 de FOE (portee de l'arme RANGED) et d >= 3 de SUPPRESSOR."""
    import hexgeo
    foe, sup = _by_vis(dec, FOE), _by_vis(dec, SUPPRESSOR)
    if psy_pos is None or foe is None or sup is None:
        return 999
    d_foe = hexgeo.distance(psy_pos, _pos(foe))
    d_sup = hexgeo.distance(psy_pos, _pos(sup))
    return abs(d_foe - 2) * 10 + max(0, 3 - d_sup) * 10


def _cost_suppressed(psy_pos, dec):
    """M2/M3 : psyker a d == 2 de SUPPRESSOR (cible primaire = SUPPRESSOR, arme RANGED r2)."""
    import hexgeo
    sup = _by_vis(dec, SUPPRESSOR)
    if psy_pos is None or sup is None:
        return 999
    return abs(hexgeo.distance(psy_pos, _pos(sup)) - 2) * 10


def _cost_adjacent(psy_pos, dec):
    """Volet `adjacent` : psyker a d == 1 du SUPPRESSOR (ennemi) et d == 2 de FOE (cible primaire,
    arme RANGED). Discrimine le disque INCLUSIF `Surrounding*(range = 2)` d'un anneau `d == 2`."""
    import hexgeo
    foe, sup = _by_vis(dec, FOE), _by_vis(dec, SUPPRESSOR)
    if psy_pos is None or foe is None or sup is None:
        return 999
    return (abs(hexgeo.distance(psy_pos, _pos(sup)) - 1)
            + abs(hexgeo.distance(psy_pos, _pos(foe)) - 2)) * 10


def _cost_ally(psy_pos, dec):
    """Volet `ally` : psyker a d <= 2 du SUPPRESSOR (qui est ICI un AMI) et d == 2 de FOE."""
    import hexgeo
    foe, sup = _by_vis(dec, FOE), _by_vis(dec, SUPPRESSOR)
    if psy_pos is None or foe is None or sup is None:
        return 999
    return (max(0, hexgeo.distance(psy_pos, _pos(sup)) - 2)
            + abs(hexgeo.distance(psy_pos, _pos(foe)) - 2)) * 10


def _cluster(rpc, rid, mover_vis, anchor_vis, want=1):
    """AMENE `mover_vis` a distance `want` d'`anchor_vis` : la cible primaire doit avoir EXACTEMENT
    un ennemi adjacent, sinon le tirage `PickRandomly(1)` du splash n'est pas deterministe."""
    import hexgeo

    def cost(p, dec):
        a = _by_vis(dec, anchor_vis)
        if p is None or a is None:
            return 999
        return abs(hexgeo.distance(p, _pos(a)) - want) * 10

    return _drive(rpc, rid, mover_vis, cost, tries=20)[0]


# --------------------------------------------------------------------------- une mesure
def _fire(rpc, rid, caster_id, target_id, ability_id):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": ability_id}}, 120)


def _measure(rpc, rid, label, target_vis, board):
    """Capture -> tir LIVE -> rejeu OFFLINE sur la MEME capture / le MEME flux MT."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    psy, tgt = _by_vis(dv, PSYKER), _by_vis(dv, target_vis)
    if psy is None or tgt is None:
        return {"label": label, "error": "unite absente"}
    import hexgeo
    sup = _by_vis(dv, SUPPRESSOR)
    d_sup = hexgeo.distance(_pos(psy), _pos(sup)) if sup else None
    d_tgt = hexgeo.distance(_pos(psy), _pos(tgt))
    if dv.get("currentPlayer") != psy.get("owner"):
        _endturn(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        psy, tgt = _by_vis(dv, PSYKER), _by_vis(dv, target_vis)
    ab = _normal_ability_id(dv, psy["id"])
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    ae = state.get_entity(psy["id"])
    traits = ((ae.get_component(StatsComponent).ctx.traits or [])
              if ae is not None and ae.get_component(StatsComponent) is not None else [])
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng

    res = _fire(rpc, rid, psy["id"], tgt["id"], ab)
    a0 = (res.get("actions") or [{}])[0]
    ok = bool(res.get("ok")) and bool(a0.get("ok"))
    by_tid, dirty = damage_by_target(res)
    live_splash = {k: v for k, v in by_tid.items() if k != tgt["id"]}

    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(psy["id"], tgt["id"]))
    dh = runner.damage_handler
    port_splash = [a for a in (dh.after_hit or []) if a.get("trait") == "Psyker"]

    return {
        "label": label, "cast_ok": ok, "dirty": dirty,
        "psyker_id": psy["id"], "target_id": tgt["id"], "target_vis": target_vis,
        "dist_target": d_tgt, "dist_suppressor": d_sup,
        "psyker_traits": sorted(traits),
        "psyker_carries_1191": bool(state.effects.has_effect(psy["id"], EFF_SUPPRESS_OWNER))
        if state.effects is not None else None,
        "suppressor_carries_1191": bool(state.effects.has_effect(sup["id"], EFF_SUPPRESS_OWNER))
        if (state.effects is not None and sup is not None) else None,
        "live_primary": by_tid.get(tgt["id"]),
        "live_splash": live_splash,
        "live_splash_fired": bool(live_splash),
        "port_ranged": dh.last.get("ranged") if dh.last else None,
        "port_profile": dh.last.get("profile") if dh.last else None,
        "port_primary": (dh.last or {}).get("per_hit"),
        "port_splash": [{"target": s.get("target"), "per_hit": (s.get("result") or {}).get("per_hit")}
                        for s in port_splash],
        "port_splash_fired": bool(port_splash),
    }


# --------------------------------------------------------------------------- scenario
def _hand_back_to_psyker(rpc, rid, tries=6):
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        psy = _by_vis(dv, PSYKER)
        if psy is not None and dv.get("currentPlayer") == psy.get("owner") \
                and not psy.get("turnFinished"):
            return True
        _endturn(rpc, rid)
    return False


def run(rpc, seed: str, board: str, keep: bool = False, variant: str = "core") -> dict:
    from engine.entities.pathfinding.board import Board
    rid = _build_subprocess(seed, board, variant)
    out = {"rid": rid, "board": board, "seed": seed, "variant": variant, "measures": []}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 120)
        b = Board(bg["tiles"], adjacency="evenq")

        if variant == "ally":
            # Le porteur du passif est un AMI : la cible primaire est FOE, son voisin FOE2. On
            # AMENE le psyker a portee de tir, PUIS le porteur ami a d <= 2 du psyker (deux
            # deplacements distincts : la contrainte double n'est pas satisfiable d'un seul cote).
            _cluster(rpc, rid, FOE2, FOE, want=1)
            out["pos"] = _cluster(rpc, rid, PSYKER, FOE, want=2)
            out["carrier_pos"] = _cluster(rpc, rid, SUPPRESSOR, PSYKER, want=2)
            _hand_back_to_psyker(rpc, rid)
            out["measures"].append(_measure(rpc, rid, "ally_carrier", FOE, b))
            return out

        _cluster(rpc, rid, FOE, SUPPRESSOR, want=1)   # FOE en ring-1 de SUPPRESSOR

        if variant == "adjacent":
            # d(psyker, FOE) == 2 (arme RANGED) et d(psyker, SUPPRESSOR ennemi) == 1 : le disque
            # `Surrounding*(range = 2)` doit mordre a d = 1 comme a d = 2 (INCLUSIF).
            out["pos"] = _cluster(rpc, rid, PSYKER, FOE, want=2)
            out["carrier_pos"] = _cluster(rpc, rid, SUPPRESSOR, PSYKER, want=1)
            _hand_back_to_psyker(rpc, rid)
            out["measures"].append(_measure(rpc, rid, "adjacent", FOE, b))
            return out

        # M1 -- TEMOIN : loin du suppresseur, le splash doit firer.
        p, _ = _drive(rpc, rid, PSYKER, _cost_free, tries=30)
        out["m1_pos"] = p
        out["measures"].append(_measure(rpc, rid, "free", FOE, b))

        # M2 -- deplacement JUSQU'A d = 2 du suppresseur PUIS tir dans le MEME tour.
        _hand_back_to_psyker(rpc, rid)
        p2, moved = _drive(rpc, rid, PSYKER, _cost_suppressed, tries=30, move_only=True)
        out["m2_pos"], out["m2_moved_same_turn"] = p2, moved
        m2 = _measure(rpc, rid, "same_turn", SUPPRESSOR, b)
        m2["moved_same_turn"] = moved
        out["measures"].append(m2)

        # M3 -- MEME position, apres un cycle complet de tours (aucun deplacement).
        for _ in range(4):
            _endturn(rpc, rid)
        out["measures"].append(_measure(rpc, rid, "after_turn", SUPPRESSOR, b))
    finally:
        if not keep:
            rpc("disposeRunner", {"runnerId": rid}, 60)
    return out


# --------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="case-418-r1 : IsEffectTarget (suppression du smite)")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--variant", choices=("core", "adjacent", "ally"), default="core")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, a.seed, a.board, a.keep, a.variant)
    print(json.dumps(r, indent=1, default=str))
    print("")
    for m in r["measures"]:
        print("[418-r1/%-10s] d(cible)=%s d(suppresseur)=%s | LIVE primary=%s splash=%s | "
              "PORT primary=%s splash=%s"
              % (m.get("label"), m.get("dist_target"), m.get("dist_suppressor"),
                 m.get("live_primary"), m.get("live_splash"),
                 m.get("port_primary"), m.get("port_splash")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
