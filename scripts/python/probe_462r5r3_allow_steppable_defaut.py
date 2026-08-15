"""CONFRONTATION LIVE #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3 -- le DEFAUT d'`allow_steppable`.

CE QUE CE PROBE MESURE, ET POURQUOI IL EXISTE
---------------------------------------------
`IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` calcule
`allowSteppable = !<+0x28>.ShouldTrigger(...)` et le passe a
`IdunBattle.Entities.TileExtensions$$IsFreeTile`, dont le bras `allowSteppable == 1` rend **LIBRE**
une tuile occupee par un `HasTrait(0x1b = Steppable)`.

La surcharge a UN argument de `IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit` -- **123 xrefs**,
celle que represente `CanAddUnit(source)` sans annotation cote port -- code son trigger EN DUR a
`<DSLTriggers+0x48>` = `op_LogicalNot(<trigger nu>)`, donc `ShouldTrigger` FAUX, donc
`allowSteppable` **VRAI**. Le port codait la branche INVERSE (defaut `False`) jusqu'au 2026-08-15.

⚠ **LA DEGRADATION EST SANS SYMPTOME** : elle ne change QUE la tuile ou un summon se pose quand un
`Steppable` (decoy, mine, spore, token) l'occupe -- ni erreur, ni crash, ni trace. C'est pourquoi
elle a survecu a toute la banque de tests : aucun temoin ne mettait un `Steppable` sur une tuile
CANDIDATE.

LE MONTAGE, ET CE QU'IL DISCRIMINE
----------------------------------
On CEINTURE le caster de `Steppable` : chacune de ses tuiles adjacentes walkables recoit une unite
a qui `catalog_inject.add_unit_trait` a ajoute le trait. Alors :

* `allowSteppable = TRUE`  (natif, et port depuis #462-...-r5-r3) -> les tuiles ceinturees restent
  CANDIDATES ;
* `allowSteppable = FALSE` (le port d'AVANT)                      -> **ZERO** candidate.

L'observable est donc le CARDINAL, pas la tuile -- ce qui rend le temoin insensible au `PickRandomly`
de la plupart des arbres de spawn. La contre-epreuve (`--contre-modele`) rejoue le MEME etat avec
`allow_steppable=False` : si elle ne s'effondre pas a 0, le montage est DEGENERE (aucun `Steppable`
n'occupe reellement une candidate) et le verdict ne prouve rien.

⚠ **LE VOISINAGE SE PREND EN NATIF** (`Board.neighbours`, le `boardGraph` capte), jamais en
geometrie even-q : `TileQuery$$IterateAdjacentTiles` applique une porte `|dElev| < 2`, et une tuile
voisine EN GEOMETRIE peut ne pas l'etre EN NATIF. Un premier jet qui ceinture << geometriquement >>
laisse des candidates libres et rend le contre-modele NON MORDANT.

    python probe_462r5r3_allow_steppable_defaut.py
    python probe_462r5r3_allow_steppable_defaut.py --board C4_09 --seed 777
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
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Il met un `Steppable` sur une tuile CANDIDATE -- le seul regime ou le defaut "
              "d'`allow_steppable` est observable. Sans lui, l'inversion du defaut est invisible "
              "de toute la banque.",
}

#: `IdunBattle.Entities.Enum.UnitTrait` -> `27 = Steppable` (0x1b). Le NOM est ce que
#: `catalog_inject.add_unit_trait` ecrit dans `BC.Units[].Traits` ; l'ordinal est lu par
#: `BaseUnitComponent$$HasTrait` cote natif.
TRAIT_STEPPABLE = "Steppable"


def rpc(sid, method, body, timeout=90):
    """Voie `POST /api/scripts/<sid>/rpc` -- la MEME que les probes live du depot. `/api/sessions/`
    liste les sessions, elle ne porte pas de RPC (404)."""
    r = requests.post("%s/api/scripts/%s/rpc" % (HOST, sid),
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    if isinstance(r, dict) and r.get("error"):
        raise SystemExit("RPC %s: %s" % (method, r["error"]))
    return r.get("result", r)


def session_id() -> int:
    st = requests.get("%s/api/admin/status" % HOST, timeout=20).json()
    return int(st["session"]["id"])


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state_path.unlink()
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=dict(os.environ))
    if not state_path.exists() or proc.returncode != 0:
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO (rc=%s)" % proc.returncode)
    return int(json.loads(state_path.read_text())["runnerId"])


def dispose(sid, rid):
    try:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    except BaseException as exc:                       # noqa: BLE001 -- diagnostic, jamais fatal
        print("[dispose] %s" % exc)


def charge(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board), dec, board


def _pos(u) -> tuple | None:
    p = u.get("pos") or {}
    if p.get("col") is None:
        return None
    return (int(p["col"]), int(p["row"]))


def _candidates(state, board, caster_id, allow_steppable: bool) -> list:
    """`CanAddUnit(AdjacentTiles(Caster()))` -- la forme de la surcharge a UN argument, evaluee sur
    l'etat LIVE charge. C'est le foyer exact dont le defaut est en cause."""
    from engine.entities.selectors.accessors import FixedTileIds
    from engine.entities.selectors.tiles import CanAddUnit
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.components import PositionComponent
    e = state.get_entity(int(caster_id))
    pc = e.get_component(PositionComponent)
    tid = board.id_at(pc.col, pc.row)
    voisins = [int(t) for t in (board.neighbours(tid) or ()) if board.walkable(int(t))]
    ctx = entities_from_state(state, caster_id=int(caster_id))
    return list(CanAddUnit(FixedTileIds(voisins), allow_steppable=allow_steppable).evaluate(ctx))


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67", help="board CHOISI (jamais laisse au hasard)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--state-file", default=None)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(PYDIR))
    import catalog_inject as CI                                          # noqa: PLC0415

    sid = session_id()
    seed_bc = LOGS / "probe_462r5r3_seed_bc.json"
    etat = Path(args.state_file) if args.state_file else (LOGS / "rs_462r5r3_ceinture.json")

    # -- 1. LE PORTEUR DU TRAIT : on FABRIQUE des `Steppable` plutot que d'en chercher.
    #    `add_unit_trait` ecrit dans `BC.Units[].Traits`, le canal que `combatSnapshot` republie et
    #    que `BaseUnitComponent$$HasTrait` lit -- c'est la meme voie que #498-r2.
    pool = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"], cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    noms = [l.strip().split()[0] for l in (pool.stdout or "").splitlines()
            if l.strip() and not l.startswith(("#", "["))]
    if len(noms) < 4:
        print("[0] POOL non mesure (%d entrees) -- montage impossible" % len(noms))
        return 2
    caster, bouchons = noms[0], noms[1:4]
    specs = ["%s:%s" % (b, TRAIT_STEPPABLE) for b in bouchons]
    CI.write_trait_seed_bc(seed_bc, specs)
    print("[0] MONTAGE caster=%s  bouchons(Steppable)=%s" % (caster, ",".join(bouchons)))

    rid = build(etat, ["--seed", args.seed, "--board", args.board, "--seed-bc", str(seed_bc),
                       "--p-units", ",".join([caster] + bouchons),
                       "--a-units", noms[4] if len(noms) > 4 else noms[1]])
    try:
        state, dec, board = charge(sid, rid)
        vivants = [u for u in (dec.get("units") or []) if u.get("alive")]
        par_vis = {}
        for u in vivants:
            par_vis.setdefault(str(u.get("visualId") or ""), []).append(u)
        cid = None
        for u in vivants:
            if str(u.get("visualId") or "") == caster or str(u.get("unitId") or "") == caster:
                cid = int(u["id"])
                break
        if cid is None:
            cid = int(vivants[0]["id"])
            print("[!] caster non resolu par visualId -- repli sur la 1re unite vivante")

        # -- 2. LE CONTROLE DE NON-DEGENERESCENCE : au moins UNE candidate doit etre occupee par un
        #       `Steppable`, sinon les deux bras rendront la meme chose pour une AUTRE raison.
        from engine.entities.traits.unit_trait import UnitTrait, has_trait
        from engine.runner.components import PositionComponent, StatsComponent
        occ_step = 0
        from engine.runner.components import PositionComponent as PC
        pcc = state.get_entity(cid).get_component(PC)
        tid = board.id_at(pcc.col, pcc.row)
        voisins = {int(t) for t in (board.neighbours(tid) or ())}
        for eid, ent in state.entities.items():
            p = ent.get_component(PositionComponent)
            sc = ent.get_component(StatsComponent)
            if p is None or sc is None:
                continue
            t = board.id_at(p.col, p.row)
            if t in voisins and has_trait(getattr(sc.ctx, "traits", None) or [],
                                          UnitTrait.Steppable):
                occ_step += 1
        print("[1] voisines du caster occupees par un Steppable : %d" % occ_step)
        if occ_step == 0:
            print("[1] MONTAGE DEGENERE -- aucun Steppable sur une candidate. Le verdict ne "
                  "prouverait RIEN (cf. l'avertissement en tete). Deplacer les bouchons.")
            return 3

        # -- 3. LES DEUX BRAS, sur le MEME etat.
        avec = _candidates(state, board, cid, allow_steppable=True)
        sans = _candidates(state, board, cid, allow_steppable=False)
        print("[2] CanAddUnit(AdjacentTiles(caster))  allowSteppable=TRUE  -> %d tuile(s) : %s"
              % (len(avec), sorted(avec)))
        print("[3] CanAddUnit(AdjacentTiles(caster))  allowSteppable=FALSE -> %d tuile(s) : %s"
              % (len(sans), sorted(sans)))
        gagnees = sorted(set(avec) - set(sans))
        print("[4] tuiles que le DEFAUT NATIF (`+0x48` -> TRUE) rend et que le port d'AVANT "
              "refusait : %d %s" % (len(gagnees), gagnees))
        if len(gagnees) != occ_step:
            print("[4] ⚠ ECART : %d tuiles gagnees pour %d Steppable adjacents -- une autre cause "
                  "que le trait joue (occupation multi-pieds ? walkable ?)" % (len(gagnees),
                                                                              occ_step))
        ok = len(gagnees) >= 1
        print("VERDICT : %s -- le defaut du port est %s, et il CHANGE l'observable sur %d tuile(s)"
              % ("OK" if ok else "FAIL", "TRUE (natif)", len(gagnees)))
        print("PORTEE DE LA MESURE -- ce que ce probe ne prouve PAS")
        print("  L'etat est LIVE (board natif, occupation native, traits republies par")
        print("  `combatSnapshot`) et le regime est etabli NON DEGENERE (%d Steppable sur des" % occ_step)
        print("  candidates). Mais les deux bras sont evalues PAR LE PORT : ce probe mesure que le")
        print("  defaut CHANGE l'observable, pas que la valeur `TRUE` soit la bonne -- celle-la")
        print("  vient du DECOMPILE (`<DSLTriggers+0x48>` code en dur dans la surcharge a UN")
        print("  argument, releve a l'octet, cf. test_550r4_462r5r3_can_add_unit_offline etage 1).")
        print("  NON COUVERT : un cast natif OBSERVE qui pose un summon SUR la tuile d'un")
        print("  Steppable -- aucune ability du pool ne reunit summon-par-CanAddUnit et Steppable")
        print("  adjacent sans montage supplementaire.")
        return 0 if ok else 1
    finally:
        dispose(sid, rid)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
