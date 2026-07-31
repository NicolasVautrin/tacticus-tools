"""probe #343 -- les deux routes de decision qui LISAIENT le domaine tuile sans EMETTRE de cible.

Residu #336-r1 (`docs/rl/case-302-4-population-cible-tuile.md` §5.2) : sur les 41 abilities qui
portent `TargetingRule.TargetIsTile`, DEUX ont un playbook `NonComparable` porte qui filtre bien
`kind == "tile"` mais rend `{"target": None, ...}` -- `1166 AberrantHypermorph` et `1194 NovaShield`.
La question etait binaire : le natif emet-il lui aussi une cible nulle, ou choisit-il une tuile ?

## Ce que le DECOMPILE tranche (les deux, meme reponse)

`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` construit, PAR entite eligible,
un struct de 0x128 octets dont le champ `+0x10` est l'ENTITE CIBLE (ecrit juste apres
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` ; `+0x08`/`+0x18` = le caster,
`+0x20` = `GetMainTile(entity)`, `+0x30` = la tuile du caster balayee).

Les deux `EvaluateNonComparable` passent CE champ en 3e argument de l'action :

  * `IdunBattle.AI.Playbook.Loki.NovaShieldPlaybook$$EvaluateNonComparable` ->
    `IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(casterPosition, target, utility)` ->
    `IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)` ;
  * `IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$EvaluateNonComparable` inline le meme
    ctor -- et son utilite le NOMME :
    `IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility(caster, summonTile)`.

=> le natif emet TOUJOURS une cible ici ; `target: None` etait un bug de port (l'argmax d'utilite
etait garde, la tuile argmax JETEE).

## Ce que ce probe MESURE (l'oracle = le tour IA observe, pas `aiPredict`)

Par item, deux bras qui different par la SEULE configuration des ennemis, de sorte que la tuile
argmax CHANGE. Pour chaque bras :

  1. `aiDryRunAllUnits` -> `ActiveAbilityMessage(abilityType, targetId)` = le choix du natif ;
  2. la resolution `targetId -> (col,row)` par `boardGraph` : la cible est-elle une TUILE ?
  3. `engine_decide` -> `(ability, target, to)` = le choix du port ;
  4. le bras ROUGE : le meme moteur avec le playbook remis a `target: None` (l'etat d'AVANT ce
     correctif) -- c'est ce qui distingue « le port emet la bonne tuile » de « l'accord vient
     d'ailleurs ».

## Porteurs (gate de confrontabilite)

  * 1166 : `genesBiophagus` (Hollan) -- lineup, DANS `rl_duel build --list-pool`. Porteur NATUREL.
  * 1194 : seul porteur du gameconfig = `tauBossRiptide`, npc -> hors pool, et `buildNormalizedBC`
    refuse les npc (`case-92` §5bis). Le porteur est donc GREFFE sur `tauCrisis` (T'au, pool) :
    le natif charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), et
    l'utilite de NovaShield ne lit ni stats ni traits du caster (seulement `BC.Utilities` + le
    board + les positions ennemies), donc la greffe ne la deforme pas.

Usage (depuis scripts/python, ASCII only) :
    python probe_343_tile_target_emission.py --item 1166 --build
    python probe_343_tile_target_emission.py --item 1194 --build
    python probe_343_tile_target_emission.py --item 1166 --dispose
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

ABERRANT = 1166
NOVASHIELD = 1194

BOARD = "MC1_67"
SEED = 909
RANK = "17"

# --- montages, par item -----------------------------------------------------------------------
CFG = {
    ABERRANT: {
        "state": "rs_343_aberrant.json",
        "caster_vid": "genesBiophagus",     # porteur NATUREL (pool)
        "p_units": "genesBiophagus",
        "a_units": "ultraTitus,orksWarboss",
        "graft_on": None,
    },
    NOVASHIELD: {
        "state": "rs_343_novashield.json",
        "caster_vid": "tauCrisis",          # porteur GREFFE (cf. l'en-tete)
        "p_units": "tauCrisis",
        "a_units": "ultraTitus,orksWarboss",
        "graft_on": "tauCrisis",
    },
}


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _state(item: int) -> Path:
    return LOGS / CFG[item]["state"]


def _rid(item: int) -> int:
    return int(json.loads(_state(item).read_text(encoding="utf-8"))["runnerId"])


def _rpc(method: str, body: dict, timeout=120000):
    import probe_27_3_live as L
    return L._rpc(method, [body], timeout)


def _dv(rid: int) -> dict:
    return _rpc("decisionView", {"runnerId": rid, "allAbilities": True})


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row), ctrl)} -- aucun id hardcode."""
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), u.get("ctrl"))
    return out


def _board(rid: int):
    """({(col,row): tileId}, {(col,row): walkable}) depuis `boardGraph`."""
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000) or {}
    tid, walk = {}, {}
    for t in (bg.get("tiles") or []):
        k = (t.get("col"), t.get("row"))
        tid[k] = t.get("id")
        walk[k] = bool(t.get("walkable", True))
    return tid, walk


def write_graft_seed_bc(item: int) -> Path:
    """COPIE du seed BC partage avec `ActiveAbilities` du greffon remplace par `[item]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    graft_on = CFG[item]["graft_on"]
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == graft_on:
            u["ActiveAbilities"] = [item]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, graft_on))
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / ("bc_343_%d.json" % item)
    out.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d] -> %s" % (graft_on, item, out.name))
    return out


def build(item: int) -> int:
    c = CFG[item]
    state = _state(item)
    args = ["build", "--seed", str(SEED), "--board", BOARD, "--rank", RANK,
            "--p-units", c["p_units"], "--a-units", c["a_units"], "--state-file", str(state)]
    if c["graft_on"]:
        args += ["--seed-bc", str(write_graft_seed_bc(item))]
    _run(args)
    return _rid(item)


def _move(item: int, rid: int, unit: int, to: tuple) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", "%d,%d" % to,
          "--state-file", str(_state(item)), "--runner", str(rid)])


# --------------------------------------------------------------------------- oracle + moteur

def native(rid: int, caster: int) -> tuple:
    """Le TOUR IA OBSERVE : `(abilityType, targetId)` de l'`ActiveAbilityMessage` propose par
    `CalculateNextActionForUnit` pour le caster, contre CET etat, sans appliquer."""
    dr = _rpc("aiDryRunAllUnits", {"runnerId": rid})
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        msgs = [m.get("cls") for m in (u.get("proposed") or [])]
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return (m.get("abilityType"), m.get("targetId"), msgs)
        return (None, None, msgs)
    return (None, None, [])


def engine(rid: int, caster: int, item: int) -> dict:
    """Decision MOTEUR sur le MEME etat + bras ROUGE (playbook remis a `target: None`)."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)               # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)

    # BRAS ROUGE : le MEME moteur avec la cible remise a None (l'etat d'AVANT ce correctif).
    pb = PB.REGISTRY.get(item)
    red = None
    if pb is not None:
        orig = type(pb).generate_candidates

        def muted(self, ctx, _orig=orig):
            out = _orig(self, ctx)
            return [dict(c, target=None) for c in out]

        type(pb).generate_candidates = muted
        try:
            red = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
        finally:
            type(pb).generate_candidates = orig
    return {"on": on, "red": red}


def measure(item: int, rid: int, label: str) -> dict:
    c = CFG[item]
    u = _units(rid)
    caster = u[c["caster_vid"]][0]
    tid_by_pos, _walk = _board(rid)
    pos_by_tid = {t: p for p, t in tid_by_pos.items()}
    ab, tgt, msgs = native(rid, caster)
    e = engine(rid, caster, item)
    on, red = e["on"], e["red"]

    print("  --- %s ---" % label)
    print("      positions : %s" % {v: p for v, (_i, p, _c) in u.items()})
    print("      natif  : ability=%s target=%s -> tuile %s (messages=%s)"
          % (ab, tgt, pos_by_tid.get(tgt), msgs))
    print("      moteur : ability=%s target=%s -> tuile %s | to=%s"
          % (on.get("ability"), on.get("target"), pos_by_tid.get(on.get("target")), on.get("to")))
    print("      ROUGE (target=None force) : ability=%s target=%s"
          % ((red or {}).get("ability"), (red or {}).get("target")))
    return {"caster": caster, "native": (ab, tgt), "native_tile": pos_by_tid.get(tgt),
            "engine": (on.get("ability"), on.get("target")), "engine_to": on.get("to"),
            "engine_tile": pos_by_tid.get(on.get("target")),
            "red": ((red or {}).get("ability"), (red or {}).get("target")),
            "pos_by_tid": pos_by_tid, "units": u}


# ------------------------------------------------------------------------------ mise en scene

def _free_neighbours(pos, tid_by_pos, walk, occupied):
    import hexgeo
    return [n for n in hexgeo.neighbors(*pos)
            if n in tid_by_pos and walk.get(n) and n not in occupied]


def stage_arms(item: int, rid: int) -> dict:
    """Deux bras qui different par la SEULE position des ennemis, choisis pour que la tuile argmax
    CHANGE d'un bras a l'autre. Les positions sont DERIVEES du board (aucune coordonnee figee)."""
    import hexgeo
    c = CFG[item]
    tid_by_pos, walk = _board(rid)
    u = _units(rid)
    caster_pos = u[c["caster_vid"]][1]
    enemies = [(v, i) for v, (i, _p, ctrl) in u.items() if ctrl is False]
    if len(enemies) < 2:
        raise SystemExit("montage : %d ennemi(s), 2 requis" % len(enemies))
    occ = {p for _v, (_i, p, _c) in u.items()}

    # Deux tuiles de spawn candidates ST1/ST2 : libres, adjacentes au caster, DISTINCTES.
    cands = _free_neighbours(caster_pos, tid_by_pos, walk, occ)
    if len(cands) < 2:
        raise SystemExit("montage : %d tuile(s) libre(s) adjacente(s) au caster" % len(cands))
    # ST1 et ST2 NON adjacentes entre elles quand c'est possible : un ennemi pose autour de l'une
    # ne doit pas compter pour l'autre.
    pair = next(((a, b) for a in cands for b in cands
                 if a != b and hexgeo.distance(a, b) > 1), (cands[0], cands[1]))
    st1, st2 = pair

    def slot(st, taken):
        return next((n for n in _free_neighbours(st, tid_by_pos, walk, occ | taken)
                     if n != caster_pos and hexgeo.distance(n, st) == 1), None)

    e1_pos = slot(st1, set())
    e2_pos = slot(st2, {e1_pos} if e1_pos else set())
    if e1_pos is None or e2_pos is None:
        raise SystemExit("montage : pas de logement libre autour de ST1/ST2 (%s / %s)" % (st1, st2))
    return {"caster_pos": caster_pos, "st1": st1, "st2": st2,
            "e1": (enemies[0][1], e1_pos), "e2": (enemies[1][1], e2_pos),
            "tid": tid_by_pos}


def run(item: int, do_build: bool) -> int:
    rid = build(item) if do_build else _rid(item)
    c = CFG[item]
    print("item=%d runner=%d board=%s seed=%d caster=%s%s"
          % (item, rid, BOARD, SEED, c["caster_vid"],
             " (GREFFE)" if c["graft_on"] else " (porteur naturel)"))
    st = stage_arms(item, rid)
    print("  ST1=%s ST2=%s caster=%s" % (st["st1"], st["st2"], st["caster_pos"]))

    rows = {}
    # BRAS A : UN ennemi, adjacent a ST1 seulement -> l'argmax doit etre ST1.
    _move(item, rid, st["e1"][0], st["e1"][1])
    _move(item, rid, st["e2"][0], _far_slot(rid, st))
    rows["A"] = measure(item, rid, "A : 1 ennemi adjacent a ST1 (%s)" % (st["st1"],))
    # BRAS B : le 2e ennemi rejoint ST2, le 1er s'eloigne -> l'argmax doit basculer sur ST2.
    _move(item, rid, st["e2"][0], st["e2"][1])
    _move(item, rid, st["e1"][0], _far_slot(rid, st))
    rows["B"] = measure(item, rid, "B : 1 ennemi adjacent a ST2 (%s)" % (st["st2"],))

    print("\n=== SYNTHESE item %d ===" % item)
    ok = True
    for k in ("A", "B"):
        r = rows[k]
        agree = r["native"] == r["engine"]
        emits = r["native"][1] is not None
        is_tile = r["native_tile"] is not None
        ok = ok and agree
        print("  %-2s natif=(%s, %s) tuile=%s | moteur=(%s, %s) tuile=%s | %s"
              % (k, r["native"][0], r["native"][1], r["native_tile"],
                 r["engine"][0], r["engine"][1], r["engine_tile"],
                 "MATCH" if agree else "DIVERGE"))
        print("     natif emet une CIBLE : %s | cette cible est une TUILE du board : %s"
              % ("OUI" if emits else "NON (target=None)", "OUI" if is_tile else "NON"))
        print("     bras ROUGE (target=None) : %s -> %s"
              % (r["red"], "aurait DIVERGE" if r["red"] != r["native"] else "indiscernable ici"))
    changed = rows["A"]["native_tile"] != rows["B"]["native_tile"]
    print("  la tuile cible du NATIF change entre A et B : %s (%s -> %s)"
          % ("OUI" if changed else "NON", rows["A"]["native_tile"], rows["B"]["native_tile"]))
    print("(pense a disposer : python probe_343_tile_target_emission.py --item %d --dispose)" % item)
    return 0 if ok else 1


def _far_slot(rid: int, st: dict):
    """Une tuile libre LOIN des deux tuiles de spawn (parking du 2e ennemi)."""
    import hexgeo
    tid_by_pos, walk = _board(rid)
    u = _units(rid)
    occ = {p for _v, (_i, p, _c) in u.items()}
    cand = [p for p in tid_by_pos
            if walk.get(p) and p not in occ
            and min(hexgeo.distance(p, st["st1"]), hexgeo.distance(p, st["st2"])) >= 3]
    if not cand:
        raise SystemExit("montage : pas de parking a distance >= 3 des tuiles de spawn")
    return max(cand, key=lambda p: hexgeo.distance(p, st["caster_pos"]))


def dispose(item: int) -> int:
    _run(["dispose", "--state-file", str(_state(item))])
    print("runner de l'item %d dispose" % item)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", type=int, required=True, choices=sorted(CFG))
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    a = ap.parse_args()
    if a.dispose:
        return dispose(a.item)
    return run(a.item, a.build)


if __name__ == "__main__":
    sys.exit(main())
