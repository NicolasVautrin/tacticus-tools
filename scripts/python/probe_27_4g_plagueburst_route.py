"""probe #27-4g -- PlagueburstMortar (1169) : QUEL est le verrou reel de sa face DECISION ?

CE QUE CE PROBE ETABLIT, et pourquoi il fallait le mesurer
----------------------------------------------------------
`docs/rl/case-27-custom-utility.md` rangeait 1169 derriere le VERROU 1, « MoW non modelisees comme
unites de DECISION ». Ce verrou-la se LEVE par la greffe de l'ability sur une unite du pool
(`case-92` §5bis) : le natif charge le playbook PAR ABILITY, jamais par unite. Une fois greffee, on
voit le verrou SUIVANT -- et ce n'est pas celui qui etait ecrit.

Le custom lui-meme est court et entierement lu
(`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility`) :

    sel = PlagueburstMortarAbility.GetAdjacentEnemies();       // arbre DSL
    n   = TargetsSelector.Count(sel, AbilityEntities(owner: caster, caster: caster, target: target));
    return Fix64.op_Multiply(Fix64(n), GetUtilityValue("PlagueburstMortar_AdjacentEnemy"));

et `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentEnemies` =
`Enemies(<caster>, Units(AdjacentTiles(<target>), unique: 1, sel: 3), sel: 3)` -- c'est-a-dire
EXACTEMENT le second terme de `plagueburst_damage_targets` (face COMBAT, deja portee par #90) SANS
son `Filter(GetIsValidAdjacentEnemyTrigger)`. Rien a inventer : un seul artefact, deja porte.

Ce que le probe MESURE (aucune de ces trois lignes n'est deductible du decompile seul) :

1. le CIBLAGE de 1169 est TILE-BASED (`abilityTargets` -> `kind = "tile"`, 62 tuiles) -- coherent
   avec le bit `TargetIsTile` (0x40) du masque `...PlagueburstMortarAbility$$.ctor` = 0x40000042 ;
2. `decisionView.attackPlans` liste bien 1169, mais avec `rankCount = 0` sur TOUTES les cibles
   UNITE : la route `_best_attack` du port (qui consomme `ranked`) ne peut structurellement rien en
   faire, et la route non-attaque (`playbook/nonattack.py::eligible_targets`) filtre `kind == "unit"` ;
3. `pairUtility(1169)` vaut 0 sur un runner frais -- `...$$MakeDamagePredictions` passe
   `PlagueburstMortarAbility$$GetMainDamageTarget`, qui est `Filter(..., GetIsValidAdjacentEnemyTrigger)`,
   et ce predicat (aura `ContagionsOfNurgle_ArmorReduction1` OU modificateur d'armure NEGATIF) est
   FAUX partout au spawn. L'utilite d'action de 1169 se reduit donc a `custom + Tile`.

Le regime `--hp-target` eleve ecrase l'utilite de l'attaque normale (les utilites sont ~ degat/PVmax)
pour que `custom = n x 10` puisse gagner : c'est le seul regime ou l'on peut voir si le natif GENERE
l'action, et donc si le residu est « route manquante » ou « branche morte ».

Usage (depuis scripts/python, ASCII only) :
    python probe_27_4g_plagueburst_route.py --build [--hp-target=400000] [--tirages=8]
    python rl_duel.py dispose --state-file <LOGS>/rs_pb_route.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_pb_graft.json"
STATE = LOGS / "rs_pb_route.json"
BOARD = "MC1_67"
SEED = 909
RANK = "17"

PLAGUEBURST = int(ActiveAbilityType.PlagueburstMortar)     # 1169
NORMAL = 69

GRAFT_ON = "deathTyphus"                  # Death Guard, present dans --list-pool
P_UNITS = "deathTyphus,deathPutrifier"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = "deathTyphus"
A_VID = "orksWarboss"
B_VID = "necroWarden"
C_VID = "astraCreed"

CASTER_TILE = "2,4"
A_TILE = "4,4"
NB = hexgeo.neighbors(4, 4)
B_NEAR = "%d,%d" % NB[0]
C_NEAR = "%d,%d" % NB[1]

HP_TARGET_DEFAULT = 400000
TIRAGES_DEFAULT = 8


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def write_graft_seed_bc() -> None:
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [PLAGUEBURST]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d] -> %s" % (GRAFT_ON, PLAGUEBURST, SEED_BC))


def build(hp_target: int) -> int:
    write_graft_seed_bc()
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", RANK,
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)] + extra)
    rid = _runner_id()
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    for unit, to in ((ids[A_VID], A_TILE), (ids[B_VID], B_NEAR), (ids[C_VID], C_NEAR),
                     (ids[CASTER_VID], CASTER_TILE)):
        _run(["act", "move", "--unit", str(unit), "--to", to,
              "--state-file", str(STATE), "--runner", str(rid)])
    return rid


def main() -> int:
    argv = sys.argv[1:]
    hp = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--hp-target=")),
                  str(HP_TARGET_DEFAULT)))
    tirages = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--tirages=")),
                       str(TIRAGES_DEFAULT)))
    rid = build(hp) if "--build" in argv else _runner_id()
    u = _units(rid)
    caster = u[CASTER_VID][0]
    print("runner=%d board=%s seed=%d hp-target=%d" % (rid, BOARD, SEED, hp))
    print("positions : caster=%s A=%s B=%s C=%s"
          % (u[CASTER_VID][1], u[A_VID][1], u[B_VID][1], u[C_VID][1]))
    nb_a = set(hexgeo.neighbors(*u[A_VID][1]))
    n_a = sum(1 for v in (B_VID, C_VID) if u[v][1] in nb_a)
    print("n (ennemis adjacents a A, mesure LIVE) = %d -> custom attendu = %d x W" % (n_a, n_a))

    # (1) DOMAINE des cibles legales
    at = L._rpc("abilityTargets", [{"runnerId": rid, "casterId": caster,
                                    "abilityType": PLAGUEBURST}])
    kinds, count = {}, 0
    for x in (at.get("units") or []):
        for a in (x.get("abilities") or []):
            if a.get("abilityId") != PLAGUEBURST:
                continue
            count += int(a.get("targetCount") or 0)
            for t in (a.get("targets") or []):
                kinds[t.get("kind")] = kinds.get(t.get("kind"), 0) + 1
    print("[1] abilityTargets(1169) : %d cibles, domaines = %s" % (count, kinds))

    # (2) ce que la route `_best_attack` du port peut consommer
    ranks = []
    for p in (_dv(rid).get("attackPlans") or []):
        if p.get("unitId") != caster:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("abilityId") == PLAGUEBURST:
                ranks.append((ev.get("targetId"), ev.get("rankCount"), ev.get("err")))
    print("[2] attackPlans evals 1169 (targetId, rankCount, err) = %s" % ranks)

    # (3) l'etage PAIRE
    for vid in (A_VID, B_VID, C_VID):
        tid = u[vid][0]
        for ab in (NORMAL, PLAGUEBURST):
            r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                        "targetId": tid, "abilityType": ab}])
            print("[3] pairUtility(u%d -> u%d[%s], ab=%d) = %s"
                  % (caster, tid, vid, ab, r.get("utility")))

    # (4) le natif GENERE-t-il l'action ?
    hist = {}
    for _ in range(tirages):
        dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
        for x in (dr.get("units") or []):
            if x.get("unitId") != caster:
                continue
            key = tuple(sorted((m.get("cls"), m.get("abilityType"), m.get("targetId"))
                               for m in (x.get("proposed") or [])))
            hist[key] = hist.get(key, 0) + 1
    for k, c in sorted(hist.items(), key=lambda kv: -kv[1]):
        print("[4] natif x%-3d : %s" % (c, list(k)))
    casts = [k for k in hist for (cls, ab, _t) in k
             if cls == "ActiveAbilityMessage" and ab == PLAGUEBURST]
    print("\n=== VERDICT ===")
    print("  le natif propose 1169 : %s" % ("OUI" if casts else "NON (sur %d tirages)" % tirages))
    print("  domaine de ciblage    : %s" % (kinds or "aucune cible"))
    print("  route offline possible: %s" % (
        "OUI (des cibles UNITE rankees)" if any(rc for _t, rc, _e in ranks)
        else "NON -- rankCount=0 partout : ni `_best_attack` (consomme `ranked`) ni "
             "`nonattack.eligible_targets` (filtre kind == 'unit') ne peuvent produire l'action"))
    print("(pense a disposer le runner : rl_duel.py dispose --state-file %s)" % STATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
