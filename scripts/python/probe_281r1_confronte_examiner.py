"""probe_281r1 -- CONFRONTER les montages `A EXAMINER` de `case-281`, au lieu de les LIRE.

`case-281` §7 laisse ouvert exactement ceci : les dix call-sites classes `A EXAMINER` sont declares
INERTES **par lecture du gate** -- `AbilityHasAttackType(0|1)` faux sur un buff (SwornProtector),
`IsNormalAttack` faux sur un cast (AnvilShield, FuryFromTheDelve). Le raisonnement est solide sur
le decompile, mais aucun de ces montages n'a jamais ete REJOUE dans les deux voies pour le
constater. Un gate lu correctement mais jamais exerce reste une hypothese.

CE QUE CE PROBE MESURE, et pourquoi c'est le bon observable
-----------------------------------------------------------
Le raccourci `<X>Ability().execute_behaviour(state, caster, target)` court-circuite
`AbilityHandler.visit_ActiveAbilityMessage`, donc l'emission du vecteur
`On(PreUnitAbility = 0x2a)` que
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` place tout en haut. Le port emet
ce vecteur par `engine/runner/operations/triggers/dispatch/ability.py::pre_unit_ability_triggers`,
qui rend la LISTE des triggers ayant effectivement fire.

On instrumente donc CE foyer, et on regarde ce qu'il rend sur le montage REEL, route par la voie
de PRODUCTION (`Runner.apply(ActiveAbilityMessage(...))`) :

    liste VIDE   -> le vecteur n'a rien declenche -> le raccourci est EQUIVALENT, mesure a l'appui
    liste NON VIDE -> le raccourci saute quelque chose -> le montage est FAUX

⚠ ET C'EST POURQUOI IL Y A UN TEMOIN. Une liste vide partout serait aussi ce que rendrait une
instrumentation qui NE MORD PAS -- l'accord en regime degenere ne prouve rien. Le cas `temoin`
monte donc `deathBlightlord` (porteur `HazeOfCorruption`, la seule famille INCONDITIONNELLE) dans
la geometrie `near` de `probe_281 --step mesure`, ou le pool
`Damageable(AdjacentEnemies(Self) & AdjacentFriends(Target))` n'est PAS vide. Il DOIT rendre une
liste non vide ; s'il rend vide, le probe echoue AVANT de conclure quoi que ce soit sur les
autres cas.

SECOND OBSERVABLE, independant du premier : l'etat resultant et le COMPTEUR DE TIRAGES des deux
voies, joues sur deux copies FRAICHES du meme etat-avant et le meme flux PRNG. Deux voies qui
rendent le meme etat ET le meme nombre de tirages ne peuvent pas differer par un trigger amont.

CE QUE CE PROBE NE FAIT PAS : corriger. `case-281` le dit explicitement -- router ces montages par
`Runner.apply` << pour etre sur >> leur ajouterait des vecteurs after-hit / turn-flow qu'ils n'ont
pas. Le geste juste est la MESURE.

    python probe_281r1_confronte_examiner.py                  # les 4 cas
    python probe_281r1_confronte_examiner.py --cas sworn      # un seul

ASCII only. rc 0 = tous les cas confrontes et conformes ; rc 1 = un cas diverge ou le temoin est muet.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

BOARD = "MC1_67"

#: Un cas = un montage REEL cite par `case-281`, avec l'ability qu'il caste et le porteur de la
#: famille abonnee. `attendu_fires` = ce que la LECTURE du gate predit ; le probe le CONFRONTE.
CAS = {
    # ---- TEMOIN : la famille INCONDITIONNELLE, dans la geometrie ou elle fire pour de bon -------
    "temoin": {
        "quoi": "HazeOfCorruption (aucun gate d'attaque, porteur en position de CASTER)",
        "p_units": "deathBlightlord",
        "a_units": "necroWarden,necroWarden,necroWarden,necroOverlord",
        "caster_vis": "deathBlightlord",
        "target_vis": "necroWarden",
        "ability": 1042,                       # FlailSwing
        "near": True,                          # place un 2e ennemi ADJACENT -> pool Haze non vide
        "attendu_fires": "NON_VIDE",
        "site": "temoin de non-degenerescence -- PAS un call-site `A EXAMINER`",
    },
    # ---- Les trois familles des dix `A EXAMINER` -----------------------------------------------
    "sworn": {
        "quoi": "SwornProtector -- gate lu `AbilityHasAttackType(0|1)`, faux sur un buff",
        "p_units": "astraCreed",
        "a_units": "necroDestroyer",
        "caster_vis": "astraCreed",
        "target_vis": "astraCreed",            # SupremeCommander est un SELF-cast
        "ability": 1028,                       # SupremeCommander
        "near": False,
        "attendu_fires": "VIDE",
        "site": "test_supreme_commander_live.py:141/275/382/422 + probe_95r2:106 (5 sites)",
    },
    "anvil": {
        "quoi": "AnvilShield -- gate lu `IsNormalAttack`, faux sur tout cast",
        "p_units": "spaceRockfist",
        "a_units": "necroOverlord,necroWarden,orksNob,adeptCanoness",
        "caster_vis": "spaceRockfist",
        "target_vis": "necroOverlord",
        "ability": 1097,                       # Foehammer
        "near": False,
        "attendu_fires": "VIDE",
        "site": "test_foehammer_live.py:50 (1 site)",
    },
    "fury": {
        "quoi": "FuryFromTheDelve -- gate lu `IsNormalAttack`, et famille NON PORTEE cote port",
        "p_units": "votanBeserk",
        "a_units": "necroWarden",
        "caster_vis": "votanBeserk",
        "target_vis": "necroWarden",
        "ability": 1221,                       # AugmentedAssault (lot votann #113)
        # `votanBeserk` est HORS du seed BC capture (`build --list-pool` le refuse au rank 17) : il
        # entre par injection catalogue (#92), exactement comme la fixture `votann_bc` de
        # `test_votann_lot1_live.py`. Un << hors pool >> n'est PAS un << non confrontable >>.
        "inject": "votanBeserk",
        "near": False,
        "attendu_fires": "VIDE",
        "site": "probe_121:243/246, test_prioritised_efficiency_live.py:234, "
                "test_votann_lot1_live.py:287 (4 sites)",
    },
}


def _counting_rng(s):
    """PRNG cale sur l'etat live + COMPTEUR de tirages -- l'observable de l'etage AMONT (#281)."""
    from engine.runner.prng import IntBasedMersenneTwister
    box = [0]

    class _Counting(IntBasedMersenneTwister):
        __slots__ = ()

        def genrand_int32(self):
            box[0] += 1
            return IntBasedMersenneTwister.genrand_int32(self)

    r = _Counting()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r, box


def _empreinte(state):
    """Etat OBSERVABLE d'apres-cast : PV, vie, position et effets de CHAQUE entite.

    Volontairement LARGE -- une liste de champs choisis ne peut pas montrer la difference qu'elle a
    oubliee. Trie pour etre comparable d'une voie a l'autre."""
    from engine.runner.components import (HealthComponent, PositionComponent, UnitComponent)
    out = []
    for eid, e in sorted(state.entities.items()):
        hc = e.get_component(HealthComponent)
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        eff = []
        if state.effects is not None:
            eff = sorted((getattr(x, "name", "") or "")
                         for x in (state.effects.by_unit.get(eid) or [])
                         if not getattr(x, "consumed", False))
        out.append((int(eid),
                    None if hc is None else hc.hp,
                    None if uc is None else bool(uc.alive),
                    None if pc is None else (pc.col, pc.row),
                    tuple(eff)))
    return out


def confronte(nom: str, spec: dict) -> dict:
    """Monte le montage, capture l'etat-avant, joue les DEUX voies, rend le verdict du cas."""
    import hexgeo
    from rl_collect_batch import _resolve_session, _rpc
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.abilities.handler import ABILITY_CLASSES
    import engine.runner.operations.triggers.dispatch.ability as DISPATCH

    pydir = REPO / "scripts" / "python"
    sid = _resolve_session()

    def r(m, b, t=90):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    sf = REPO / "logs" / "runners" / ("p281r1-%s-%s.json" % (nom, uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
            "--board", BOARD, "--roster", "1",
            "--p-units", spec["p_units"], "--a-units", spec["a_units"],
            "--hp-target", "90000", "--crit", "0,0", "--block-target", "0,0"]
    if spec.get("inject"):
        bc = REPO / "logs" / "runners" / ("p281r1-bc-%s.json" % spec["inject"])
        if not bc.exists():
            ci = subprocess.run([sys.executable, "catalog_inject.py", "--units", spec["inject"],
                                 "--out", str(bc)], cwd=str(pydir), capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
            if not bc.exists():
                return {"nom": nom, "erreur": "catalog_inject KO : %s"
                        % (ci.stderr or ci.stdout or "")[-300:]}
        argv += ["--seed-bc", str(bc)]
    proc = subprocess.run(argv, cwd=str(pydir), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return {"nom": nom, "erreur": "build KO : %s"
                % (proc.stderr or proc.stdout or "")[-300:]}
    rid = int(json.loads(sf.read_text())["runnerId"])
    try:
        bg = r("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return r("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        def find(dv, vis):
            return next((u for u in (dv.get("units") or [])
                         if u.get("visualId") == vis and u.get("alive")), None)

        myp = None
        for _ in range(20):
            dv = dview()
            c = find(dv, spec["caster_vis"])
            if c is None:
                return {"nom": nom, "erreur": "caster %s absent du build" % spec["caster_vis"]}
            myp = c.get("owner")
            if dv.get("currentPlayer") == myp:
                break
            r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        dv = dview()
        c = find(dv, spec["caster_vis"])
        cid = c["id"]
        cpos = (c["pos"]["col"], c["pos"]["row"])
        ctile = board.id_at(*cpos)

        # --- GEOMETRIE : on DEPLACE les unites, on ne subit pas le spawn (doctrine) --------------
        if spec["caster_vis"] == spec["target_vis"]:
            tid = cid                                  # self-cast
        else:
            tgt = find(dv, spec["target_vis"])
            if tgt is None:
                return {"nom": nom, "erreur": "cible %s absente" % spec["target_vis"]}
            nbrs = [n for n in board.neighbours(ctile) if board.walkable(n)]
            if not nbrs:
                return {"nom": nom, "erreur": "aucune tuile libre adjacente au caster"}
            tc = board.coord(nbrs[0])
            r("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": tgt["id"], "to": {"col": tc[0], "row": tc[1]}}}, 60)
            tid = tgt["id"]
            if spec.get("near"):
                # le SEUL parametre du regime `near` de #281 : un 2e ennemi ADJACENT au caster ET
                # a la cible -> le pool `AdjacentEnemies(Self) & AdjacentFriends(Target)` est plein
                sec = next((u for u in (dv.get("units") or [])
                            if u.get("owner") != myp and u.get("alive")
                            and u["id"] != tid), None)
                cand = [n for n in board.neighbours(board.id_at(*tc))
                        if board.walkable(n) and board.coord(n) != cpos
                        and hexgeo.distance(board.coord(n), cpos) == 1]
                if sec is None or not cand:
                    return {"nom": nom, "erreur": "regime near : pas de 2e ennemi placable"}
                s2 = board.coord(cand[0])
                r("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": sec["id"],
                    "to": {"col": s2[0], "row": s2[1]}}}, 60)

        # --- le cast doit etre LEGAL : sinon le montage ne mesure rien ---------------------------
        at = r("abilityTargets", {"runnerId": rid, "unitId": cid,
                                  "abilityType": spec["ability"]}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == spec["ability"]), {})
        fh = [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]
        if tid not in fh:
            return {"nom": nom, "erreur": "cast illegal (cibles legales : %r)" % (fh[:8],)}

        dv0 = dview()
        ob0 = r("observeBattle", {"runnerId": rid}, 60)
        snap0 = r("combatSnapshot", {"runnerId": rid}, 90)
        s0 = r("dumpRng", {"runnerId": rid}, 30)

        # --- VOIE PRODUCTION : `Runner.apply`, avec le vecteur INSTRUMENTE -----------------------
        fires = []
        vrai = DISPATCH.pre_unit_ability_triggers

        def _espion(state, caster_id, target_id, ranged, profile=None, ability_type=None):
            out = vrai(state, caster_id, target_id, ranged, profile=profile,
                       ability_type=ability_type)
            fires.append({"caster": caster_id, "target": target_id,
                          "ability_type": ability_type, "n": len(out or []),
                          "quoi": [str(x)[:120] for x in (out or [])]})
            return out

        DISPATCH.pre_unit_ability_triggers = _espion
        try:
            st_p = load_state(dv0, ob0, snap0, board=board)
            st_p.rng, box_p = _counting_rng(s0)
            Runner(st_p).install_default_handlers(20).apply(
                ActiveAbilityMessage(cid, tid, spec["ability"]))
        finally:
            DISPATCH.pre_unit_ability_triggers = vrai

        # --- VOIE RACCOURCI : `execute_behaviour` sur un etat FRAIS et le MEME flux --------------
        st_d = load_state(dv0, ob0, snap0, board=board)
        st_d.rng, box_d = _counting_rng(s0)
        cls = ABILITY_CLASSES.get(spec["ability"])
        if cls is None:
            return {"nom": nom, "erreur": "ability %d hors ABILITY_CLASSES : le raccourci que "
                                          "`case-281` decrit n'existe pas pour elle"
                                          % spec["ability"]}
        cls().execute_behaviour(st_d, cid, tid)

        n_fires = sum(f["n"] for f in fires)
        return {"nom": nom, "rid": rid, "caster": cid, "target": tid,
                "ability": spec["ability"], "fires": fires, "n_fires": n_fires,
                "tirages_production": box_p[0], "tirages_raccourci": box_d[0],
                "empreinte_egale": _empreinte(st_p) == _empreinte(st_d),
                "delta_empreinte": [(a, b) for a, b in zip(_empreinte(st_p), _empreinte(st_d))
                                    if a != b][:6]}
    finally:
        try:
            r("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cas", default="all", choices=["all"] + sorted(CAS))
    a = ap.parse_args(argv)
    noms = sorted(CAS) if a.cas == "all" else [a.cas]
    # le temoin d'abord : s'il est muet, aucun VIDE d'apres ne prouve quoi que ce soit
    noms.sort(key=lambda n: 0 if n == "temoin" else 1)

    rc = 0
    resultats = {}
    for n in noms:
        spec = CAS[n]
        print("\n=== %s : %s" % (n, spec["quoi"]))
        print("    sites : %s" % spec["site"])
        res = confronte(n, spec)
        resultats[n] = res
        if res.get("erreur"):
            print("    ERREUR : %s" % res["erreur"])
            rc = 1
            continue
        print("    cast %d : caster=%s target=%s" % (res["ability"], res["caster"], res["target"]))
        print("    On(PreUnitAbility) emis %d fois, triggers fires : %d"
              % (len(res["fires"]), res["n_fires"]))
        for f in res["fires"]:
            print("       vecteur(ability_type=%r) -> %d trigger(s) %s"
                  % (f["ability_type"], f["n"], f["quoi"] if f["n"] else ""))
        print("    tirages : production=%d raccourci=%d ; empreinte d'etat egale : %s"
              % (res["tirages_production"], res["tirages_raccourci"], res["empreinte_egale"]))
        if res["delta_empreinte"]:
            print("    premieres divergences d'etat : %r" % (res["delta_empreinte"],))

        attendu = spec["attendu_fires"]
        if attendu == "NON_VIDE":
            if res["n_fires"] <= 0:
                print("    TEMOIN MUET -- l'instrumentation ne mord pas, ou la geometrie `near` n'a "
                      "pas rempli le pool Haze. AUCUN `VIDE` mesure ensuite ne prouve quoi que ce "
                      "soit (accord en regime degenere).")
                rc = 1
            else:
                print("    TEMOIN OK : le vecteur fait fire %d trigger(s) -- l'instrument mord."
                      % res["n_fires"])
        else:
            conforme = (res["n_fires"] == 0
                        and res["empreinte_egale"]
                        and res["tirages_production"] == res["tirages_raccourci"])
            if conforme:
                print("    CONFRONTE : inertie MESUREE (0 trigger, meme etat, memes tirages) -- la "
                      "lecture du gate de `case-281` est confirmee par l'experience.")
            else:
                print("    DIVERGENCE : le raccourci n'est PAS equivalent sur ce montage.")
                rc = 1

    print("\n[281-r1] rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
