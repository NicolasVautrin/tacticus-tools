"""#889-r6 -- confrontation NATIF/PORT de la PHASE 1 de `1215 InstrumentsOfVengeance`
(`darkaBossLion` « le Lion »).

CE QUE CE PROBE MESURE, ET PAR QUOI
===================================
Le cast NE FRAPPE PAS : aucun total de degat ne le revele. Ses TROIS observables sont des poses
d'effet, et les trois sont lisibles -- le natif les publie dans le `captureEvents` de l'action :

  * `Effect_Refresh e=<entite> <<InstrumentsOfVengeance_LocationTarget>>` -- la MARQUE, posee sur
    des entites TUILE. **C'est l'observable central**, et c'est lui qui confronte tout l'etage de
    selection (bordure, tri, ligne). Le probe releve l'ensemble des entites marquees.
  * `... <<InstrumentsOfVengeance_PendingAttack>>` -- l'ARMEMENT, pose sur le CASTER (unite).
  * `Overwatch_AutoAttack` -- la branche CONDITIONNELLE `If(NOT HasAdjacentEnemies(Owner), ...)`.

DEUX REGIMES, et c'est ce qui rend le troisieme observable NON DEGENERE :

  * **isole**  -- aucun ennemi au contact du Lion  -> le `If` passe.
  * **contact** -- un ennemi colle au Lion         -> le `If` ne passe PAS.

Sans les deux, un accord sur la seule branche << passe >> ne dirait rien du predicat : un port qui
activerait TOUJOURS l'overwatch serait vert.

CE QUE CE PROBE NE PEUT PAS COMPARER, et le DIT
----------------------------------------------
Les ids d'entite du natif (`e=`) sont des ids ECS ; ceux du port sont les ids de tuile du
`boardGraph`. Les deux numerotations ne coincident pas en general, donc **la comparaison porte sur
le CARDINAL et sur la GEOMETRIE** (deux lignes disjointes, chacune ancree sur une bordure opposee),
pas sur l'egalite des ensembles d'ids. La geometrie du port est lue en (col,row) ; celle du natif ne
l'est pas -- ce que le natif publie est un compte et une identite d'effet. Dit, pas tu.

La PHASE 2 (le degat) n'est pas portee -- residu `#889-r6-r1`. Ce probe ne joue donc PAS le tour
suivant : il n'y aurait rien a confronter du cote port.

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

IOV = 1215                      # ActiveAbilityType.InstrumentsOfVengeance
BOARD = "CE6_boss"              # LA carte du boss (gameconfig battles[].BoardId), comme #889-r5
BOSS = "darkaBossLion:4"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py",
                "scripts/python/engine/runner/abilities/loki/__init__.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/effects.py",
                "scripts/python/engine/runner/abilities/behaviours/persistent_data.py",
                "scripts/python/engine/entities/selectors/geometry.py",
                "scripts/python/engine/entities/selectors/tiles.py",
                "scripts/python/engine/entities/selectors/units.py",
                "scripts/python/engine/entities/formulas.py",
                "scripts/python/engine/hex_edge.py"),
    "build": True,
    "toujours": False,
    "raison": "Probe LIVE (un runner par regime, deux regimes). Le perimetre est le port de 1215 et "
              "la cascade de noeuds qu'il consomme. `build: True` : la confrontation lit des "
              "identites d'effet publiees par le binaire (`InstrumentsOfVengeance_LocationTarget` / "
              "`_PendingAttack` / `Overwatch_AutoAttack`) et un board du gameconfig -- les trois se "
              "reindexent au changement de build.",
}


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, sid),
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def live_session() -> int:
    ss = requests.get("%s/api/sessions" % HOST, timeout=10).json()
    live = [s for s in ss if s.get("status") == "running"]
    if not live:
        raise SystemExit("aucune session Frida vivante")
    return int(live[-1]["id"])


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=dict(os.environ))
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind(sid):
    """LIE le transport ambiant que `load_state` utilise pour tirer `unitAbilityStates`."""
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def offline_state(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "rngSnapshot", {"runnerId": rid}, 30)
    abst = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=bg["tiles"], ability_states=abst), dec, board


def _events(act) -> list:
    """Aplatis les `captureEvents` de l'action."""
    out = []
    for a in (act.get("actions") or []):
        out.extend(a.get("events") or [])
    out.extend(act.get("events") or [])
    return out


def _marks(evs, nom: str) -> list:
    """Les entites PORTEUSES de l'effet `nom`, dans l'ordre d'emission.

    LA CHAINE, telle que le flux la publie -- et elle a DEUX etages qu'on ne peut pas confondre :

        {"kind":"group",  "group":22, "entity":105, "source":"<nom de l'effet>"}
        {"kind":"action", "step":15,  "entity":75,  "tags":"{... \\"Effect_Id\\":105}"}

    `group.entity` est l'entite-EFFET (105), `action.entity` est l'entite qui le RECOIT (75, ici une
    TUILE). Lire le premier rendrait des ids d'effet CONSECUTIFS -- 14 entiers plausibles et faux,
    qui ne se compareraient a rien. L'appariement passe donc par `Effect_Id`.

    ⚠ Les ids de TUILE du `boardGraph` SONT les ids d'entite ECS (mesure : le board `CE6_boss`
    publie `id` 12..81 pour 7x10 tuiles, et les receveurs de la marque sont dans cet intervalle) --
    c'est ce qui rend la comparaison d'ENSEMBLES possible, et pas seulement celle des cardinaux."""
    eff_ids = {int(e.get("entity")) for e in evs
               if e.get("kind") == "group" and e.get("source") == nom
               and e.get("entity") is not None}
    seen, out = set(), []
    for e in evs:
        if e.get("kind") != "action" or e.get("entity") is None:
            continue
        try:
            tags = json.loads(e.get("tags") or "{}")
        except Exception:
            continue
        if int(tags.get("Effect_Id", -1)) in eff_ids:
            v = int(e["entity"])
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def seed_offline_rng(state, dump):
    """CALE le PRNG offline sur l'etat EXACT du runner (`dumpRng`), comme #889-r5.

    ⚠ **`load_state` ne le fait PAS** : mesure du 2026-08-14, `state.rng` sort a `None` malgre le
    `rngSnapshot` passe en argument. Et un `rng` absent n'est pas neutre ici -- c'est un CHANGEMENT
    DE REGIME : `MaybeTrigger` sans PRNG rend `99 < chance` (le mirror du `!CanUseRandom` natif,
    cote DECISION), donc `99 < 50` = FAUX, donc la branche `b` TOUJOURS. Le natif, lui, tire.
    Comparer sans caler le PRNG mesure deux branches DIFFERENTES et impute a la geometrie ce qui
    n'est qu'un tirage."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def port_cast(state, caster_id: int):
    from engine.runner.abilities.handler import ABILITY_CLASSES
    ability = ABILITY_CLASSES[IOV]()
    return ability.execute_behaviour(state, int(caster_id), int(caster_id)) or {}


def run(regime: str, seed: str, tag: str) -> dict:
    sid = live_session()
    sf = LOGS / ("iov889r6_%s_%s.json" % (regime, tag))
    args = ["--seed", seed, "--board", BOARD, "--explicit-stats", BOSS, "--p-units", BOSS,
            "--a-units", "custoVexilusPraetor,orksBigMek", "--place", "%s:3,3" % BOSS]
    if regime == "contact":
        args += ["--a-place", "custoVexilusPraetor:3,4", "--a-place", "orksBigMek:2,2"]
    else:                                   # `isole` : les deux ennemis au plus loin du Lion
        args += ["--a-place", "custoVexilusPraetor:0,0", "--a-place", "orksBigMek:6,8"]
    rid = build(sf, args)
    bind(sid)
    state, dec, board = offline_state(sid, rid)
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})

    caster = None
    for u in (dec.get("units") or []):
        if int(u.get("team", 0)) == 1 or u.get("isPlayer"):
            caster = int(u["id"])
            break
    if caster is None:
        caster = int((dec.get("toActivate") or [None])[0])

    # ---- PORT : le meme cast, joue hors ligne sur l'etat seede du runner -------------------
    diag = port_cast(state, caster)
    port_marks = [t for t in (diag.get("marked") or []) if t is not None]
    port_pos = []
    for t in port_marks:
        c = board.by_id.get(int(t))
        if c is not None:
            port_pos.append((int(c["col"]), int(c["row"])))

    # ---- LIVE : le MEME cast, joue par le natif -------------------------------------------
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster, "abilityType": IOV, "targetId": caster}}, 120) or {}
    evs = _events(act)
    nat_marks = _marks(evs, "InstrumentsOfVengeance_LocationTarget")
    nat_arm = _marks(evs, "InstrumentsOfVengeance_PendingAttack")
    nat_ow = _marks(evs, "Overwatch_AutoAttack")

    try:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    except Exception:
        pass

    def pos(tid):
        c = board.by_id.get(int(tid))
        return None if c is None else (int(c["col"]), int(c["row"]))

    return {
        "regime": regime, "rid": rid, "caster": caster,
        "cast_error": (act.get("actions") or [{}])[0].get("error"),
        "natif": {"marques": len(nat_marks), "arme": len(nat_arm), "overwatch": len(nat_ow),
                  "tuiles": nat_marks, "positions": [pos(t) for t in nat_marks]},
        "port": {"marques": len(port_marks), "tuiles": port_marks, "positions": port_pos,
                 "arme": len(diag.get("armed") or []),
                 "overwatch": len(diag.get("activated") or []),
                 "persisted": [p["key"] for p in (diag.get("persisted") or [])]},
        "ecart": {"natif_seul": sorted(set(nat_marks) - set(port_marks)),
                  "port_seul": sorted(set(port_marks) - set(nat_marks))},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--tag", default=str(os.getpid()))
    ap.add_argument("--regimes", default="isole,contact")
    a = ap.parse_args()
    res = [run(r, a.seed, a.tag) for r in a.regimes.split(",") if r]
    print(json.dumps(res, indent=2))

    ok = True
    for r in res:
        n, p = r["natif"], r["port"]
        if r["cast_error"]:
            print("[%s] CAST REFUSE : %s" % (r["regime"], r["cast_error"]))
            ok = False
        # A -- les MARQUES : l'ENSEMBLE des tuiles, et sa non-degenerescence.
        # ⚠ **PAS le cardinal brut** : quand les DEUX lignes se croisent, le port emet un `AddEffect`
        # par cible -- donc DEUX fois sur la tuile d'intersection, la seconde avec `placed = False`
        # (`AddEffectOperation` refuse une instance deja presente) -- la ou le flux natif ne publie
        # qu'UN `Effect_Refresh` par tuile. Comparer les cardinaux accuserait alors le port d'un
        # ecart qui n'existe pas : mesure du regime `contact`, 14 emissions pour 13 tuiles, ensembles
        # IDENTIQUES. C'est l'ensemble qui est l'observable.
        nset, pset = set(n["tuiles"]), set(p["tuiles"])
        if not nset or not pset:
            print("[%s] MARQUES VIDES (natif=%d port=%d) -- accord degenere" %
                  (r["regime"], len(nset), len(pset)))
            ok = False
        elif nset != pset:
            print("[%s] ENSEMBLES DIFFERENTS : natif_seul=%s port_seul=%s" %
                  (r["regime"], r["ecart"]["natif_seul"], r["ecart"]["port_seul"]))
            ok = False
        else:
            dup = len(p["tuiles"]) - len(pset)
            print("[%s] marques OK : %d tuiles identiques des deux cotes%s" %
                  (r["regime"], len(nset),
                   "" if not dup else " (%d re-pose(s) sur l'intersection des deux lignes)" % dup))
        # B -- l'ARMEMENT
        if n["arme"] == 0 or p["arme"] == 0:
            print("[%s] ARMEMENT absent (natif=%d port=%d)" % (r["regime"], n["arme"], p["arme"]))
            ok = False
        # C -- les DEUX cles persistantes par passe, soit QUATRE
        if len(p["persisted"]) != 4:
            print("[%s] cles persistantes ecrites : %s (4 attendues)" %
                  (r["regime"], p["persisted"]))
            ok = False
        # D -- la GEOMETRIE portee : deux lignes, chacune ancree sur une bordure opposee
        cols = sorted({c for c, _ in p["positions"]})
        print("[%s] port : %d tuiles marquees, colonnes %s" %
              (r["regime"], p["marques"], cols))
    # E -- le CONTRASTE de la branche conditionnelle, entre les deux regimes
    if len(res) == 2:
        iso = [x for x in res if x["regime"] == "isole"][0]
        con = [x for x in res if x["regime"] == "contact"][0]
        print("overwatch natif : isole=%d contact=%d | port : isole=%d contact=%d" %
              (iso["natif"]["overwatch"], con["natif"]["overwatch"],
               iso["port"]["overwatch"], con["port"]["overwatch"]))
        for cote in ("natif", "port"):
            if iso[cote]["overwatch"] == 0 or con[cote]["overwatch"] != 0:
                print("CONTRASTE ROMPU cote %s : attendu isole>0 et contact==0" % cote.upper())
                ok = False
    print("PROBE OK" if ok else "PROBE KO")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
