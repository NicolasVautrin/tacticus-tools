"""probe #216 -- SavageEchoes (1230) : la PREDICTION DE DEGAT porte-t-elle le terme
`extraDmg x Count(CanAddUnit(AdjacentTiles(Owner@0x148)))` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` ?

DECOMPOSITION PAR ETAGE (jamais un scalaire fitte) -- pour chaque montage :
  etage 1 DEGAT  : `aiPlaybookPredict` natif (ProbableDamageEvent : healthDmg min/max,
                   appliedHits) vs la prediction OFFLINE (`make_damage_predictions`),
                   AVEC le handler `_savage_echoes_inputs` puis SANS (registre neutralise) ;
  etage 2 UTILITE: `pairUtility` natif vs `calculate_action_utility` offline, AVEC / SANS.

Le compte de tuiles libres est CHOISI par le montage : on deplace des unites autour du
caster pour faire varier `Count(CanAddUnit(AdjacentTiles(caster)))` et voir la prediction
native ET offline bouger DU MEME PAS (generalisation, pas un point unique).

Usage :
  python catalog_inject.py --units bloodTerminator --out <logs>/bc_savage.json
  python probe_216_savage_prediction.py [--keep]
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_savage.json"
STATE = LOGS / "rs_216_savage.json"
BOARD = "MC1_67"
SEED = 909
CASTER, TARGET = 81, 77          # bloodTerminator (team 1) / tauCrisis (team 2)
sys.path.insert(0, str(HERE))
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
#: MEMBRE (#270-r1 volet 2), et LOAD-BEARING : ce probe `pop` puis REINSERE cette cle dans
#: `_MAKE_DMG_INPUT_OVERRIDES` -- un `pop` + reinsertion REMPLACE la cle, donc un ordinal nu
#: laisserait le dict avec une cle non typee.
ABILITY = ActiveAbilityType.SavageEchoes  # 1230
# BOUCHONS : un ALLIE du caster (83 ultraCalgar) et un ENNEMI (79 blackTerminator). Les poser sur des
# tuiles adjacentes au caster fait BAISSER `Count(CanAddUnit(AdjacentTiles(caster)))` -- CanAddUnit ne
# regarde PAS l'equipe (tuile LIBRE), les deux camps bouchent donc pareil : c'est ce que le montage teste.
BLOCKER_ALLY, BLOCKER_FOE = 83, 79
# (2,5) a 6 voisins TOUS marchables sur MC1_67 -> compte pilotable de 5 (cible seule) a 3 (cible + 2
# bouchons). (4,8) du montage historique #27-3 n'a que 3 voisins marchables (compte fige a 2).
HUB = "2,5"
NEIGHBOURS = ["2,6", "3,6", "3,5", "2,4", "1,5", "1,6"]


def _run(args):
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _rid() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _units(rid):
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    return {u.get("id"): u for u in (dv.get("units") or [])}


def _native_pred(rid):
    """ORACLE per-ability : `<Ability>Playbook.MakeDamagePredictions` natif invoque en direct."""
    r = L._rpc("aiPlaybookPredict", [{"runnerId": rid, "unitId": CASTER,
                                      "targetId": TARGET, "abilityType": ABILITY}])
    return [(e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
            for e in (r.get("events") or [])], r


def _native_pair(rid):
    r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER,
                               "targetId": TARGET, "abilityType": ABILITY}])
    return r.get("utility")


def _ctx(rid):
    """`(AiDecisionContext, tuile courante du caster)` -- une passe RPC, comme engine_decide."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, W.load(), _scene.build_predictor(rpc, rid))
    mp = ctx.me.get("pos") or {}
    return ctx, (mp.get("col"), mp.get("row"))


def _offline(ctx, here, with_handler: bool):
    """(events de degat, utilite de paire) OFFLINE pour (CASTER, TARGET, 1230)."""
    from engine.playbook import get_playbook_or_default
    from engine.playbook.prediction import abilities as PA

    saved = PA._MAKE_DMG_INPUT_OVERRIDES.pop(ABILITY, None)
    if with_handler and saved is not None:
        PA._MAKE_DMG_INPUT_OVERRIDES[ABILITY] = saved
    try:
        evs = PA.make_damage_predictions(ctx.scene, CASTER, TARGET, ABILITY, "SavageEchoes",
                                         attack_pos=here)
        pred = [(e.target, e.prediction.accurate_health_damage.min,
                 e.prediction.accurate_health_damage.max, e.prediction.applied_hits)
                for e in evs]
        u = get_playbook_or_default(ABILITY).calculate_action_utility(ctx, here, TARGET, ABILITY)
    finally:
        if saved is not None:
            PA._MAKE_DMG_INPUT_OVERRIDES[ABILITY] = saved
    return pred, (None if u is None else u["u"])


def _free_tiles(ctx):
    """`Count(CanAddUnit(AdjacentTiles(caster)))` recalcule OFFLINE (diag du montage)."""
    from engine.dsl import nodes as dsl
    sc = ctx.scene
    by_id = {u.get("id"): u for u in (sc.units or [])}
    dctx = dsl.DslContext(units=sc.units, caster=by_id.get(CASTER), board=getattr(sc, "board", None))
    return dsl.Count(dsl.CanAddUnit(dsl.AdjacentTiles(dsl.Caster()))).evaluate(dctx)


def _move(rid, uid, to):
    _run(["act", "move", "--unit", str(uid), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _report(rid, label):
    ctx, here = _ctx(rid)
    free = _free_tiles(ctx)
    nat_pred, _ = _native_pred(rid)
    nat_u = _native_pair(rid)
    on_pred, on_u = _offline(ctx, here, True)
    off_pred, off_u = _offline(ctx, here, False)
    print("--- %s (free_tiles offline = %s) ---" % (label, free))
    print("  degat  natif        : %s" % (nat_pred,))
    print("  degat  offline AVEC : %s" % (on_pred,))
    print("  degat  offline SANS : %s" % (off_pred,))
    print("  util   natif=%r  offline AVEC=%r  offline SANS=%r" % (nat_u, on_u, off_u))
    ok = (nat_pred and on_pred
          and [tuple(x[1:]) for x in nat_pred] == [tuple(x[1:]) for x in on_pred])
    print("  VERDICT degat AVEC handler : %s" % ("EXACT" if ok else "ECART"))
    dmg = lambda p: (None if not p else (p[0][1], p[0][2]))          # noqa: E731
    return label, free, dmg(nat_pred), dmg(on_pred), dmg(off_pred)


def main() -> int:
    if not SEED_BC.exists():
        print("seed BC augmentee absente : lancer d'abord")
        print("  python catalog_inject.py --units bloodTerminator --out %s" % SEED_BC)
        return 2
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", str(SEED_BC),
          "--p-units", "bloodTerminator,ultraCalgar", "--a-units", "tauCrisis,blackTerminator",
          "--hp-player", "100000", "--hp-target", "60000", "--state-file", str(STATE)])
    rid = _rid()
    print("runner=%d board=%s" % (rid, BOARD))
    rows = []
    # Montage 0 -- REPRODUCTION du montage historique #27-3 (caster (4,8) / cible (5,8), 3 voisins
    # marchables dont 1 pris par la cible -> compte FIGE a 2). C'est la mesure de reference du cas.
    _move(rid, CASTER, "4,8")
    _move(rid, TARGET, "5,8")
    _move(rid, BLOCKER_ALLY, "0,0")
    rows.append(_report(rid, "montage 0 : reference #27-3 (4,8)/(5,8)"))
    # Montages 1..3 -- le caster passe sur un HUB a 6 voisins TOUS marchables, puis on BOUCHE les
    # tuiles une a une : le compte descend 5 -> 4 -> 3 et le degat doit suivre DU MEME PAS.
    _move(rid, CASTER, HUB)
    _move(rid, TARGET, NEIGHBOURS[0])
    rows.append(_report(rid, "montage 1 : hub degage (cible seule adjacente)"))
    _move(rid, BLOCKER_ALLY, NEIGHBOURS[1])            # ALLIE du caster sur un voisin
    rows.append(_report(rid, "montage 2 : + 1 ALLIE adjacent au caster"))
    _move(rid, BLOCKER_FOE, NEIGHBOURS[2])             # ENNEMI sur un autre voisin
    rows.append(_report(rid, "montage 3 : + 1 ENNEMI adjacent au caster"))
    print("=== SYNTHESE ===")
    for lbl, free, nat, on, off in rows:
        print("  %-46s free=%s natif=%s offlineAVEC=%s offlineSANS=%s"
              % (lbl, free, nat, on, off))
    if "--keep" not in sys.argv[1:]:
        L._rpc("disposeRunner", [{"runnerId": rid}])
        print("runner %d dispose" % rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
