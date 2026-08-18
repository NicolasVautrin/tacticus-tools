"""#10023-r1 -- CONFRONTATION LIVE : la tuile CIBLEE de `1201 SquigMine` est-elle dans le POOL ?

QUESTION, une seule, et elle est BINAIRE : `SurroundingTiles(target, includeCenter: 0, range)`
retranche-t-il la tuile CIBLEE quand celle-ci est VIDE ?

    // IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour, relu
    // VERBATIM sur `t6dpr4k06g` -- le 3e argument est le litteral 0 :
    pool = EntitiesWithoutEffects(
               CanAddUnit(SurroundingTiles(dsl+0x60 = Target, includeCenter: 0,
                                           GetNumberConstant(0x16) = range, 0, 0), dsl+0x40),
               [0x5a1 = 1441 SquigMine_Tile])
    picked = PickRandomly(pool, GetVariableForLevel(0x66) = nrOfTiles[level], 0, 0x7fffffff, false)
    Execute( AddEffect(0x5a1, ..., targets = Cache(Target op_Addition picked, unique: 1), turns) )

La RE dit NON (il ne la retranche pas) : `Tiles(origin)` resout d'abord la tuile en son OCCUPANT
(`TargetsSelector$$SelectUnit` -> `UnitExtensions$$GetUnit` -> `TileContentComponent.IsFilled`),
et une tuile VIDE n'y rend AUCUNE entite. Le masque de `SquigMine` porte `TargetTileIsFree`, donc
la tuile ciblee est **TOUJOURS** vide : le regime est systematique, pas accidentel.

CE QUI REND LA MESURE CONCLUANTE -- l'observable n'est pas l'ensemble, c'est le CARDINAL :

    targets = Union(cible, picked), UNIQUE
      * si la cible est DANS le pool, `PickRandomly` peut la tirer -> `Union` la dedoublonne
        -> **nrOfTiles tuiles minees** ;
      * si elle n'y est PAS (ce que faisait le port d'avant), le total est **nrOfTiles + 1**,
        TOUJOURS.

Le probe tranche donc dans les DEUX sens, et les deux verdicts ont des formes differentes :

  * **UN SEUL** cast a `nrOfTiles` tuiles minees PROUVE que la cible est dans le pool (preuve
    d'EXISTENCE) ;
  * N casts a `nrOfTiles + 1` REJETTENT cette hypothese quand
    `prod(1 - nrOfTiles/(|pool|+1)) <= 0,01`. C'est un resultat, pas une absence de resultat --
    et il faut le DIRE, sinon la seule issue possible du probe serait « non concluant ».

Le tirage etant aleatoire, on joue plusieurs seeds et on vise une cible dont le disque est PETIT
(`P(cible tiree) = nrOfTiles / |pool|` monte quand le pool descend).

RESULTAT MESURE le 2026-08-18 sur `t6dpr4k06g`, board `MC1_67`, cible `(6,0)`, `|pool| = 7 + 1`,
`nrOfTiles = 4` : **19 casts sur 19 rendent 5 tuiles minees**, jamais 4. **La tuile ciblee, VIDE,
est RETRANCHEE** -- l'enonce de #10023-r1 annoncait l'inverse ; il etait FAUX.

Invocation CONCLUANTE et reproductible (rc 0, `P = 0,0039`) :

    python probe_10023r1_squig_pool_live.py --seeds 777,31337,4242,11,22,33,44,55 \
        --board MC1_67 --state-file <chemin ABSOLU unique>

⚠ Ce probe ne compare AUCUN ensemble de tuiles : l'ordre d'enumeration natif du pool n'est pas
porte (residu #215), donc les ensembles tires ne sont pas confrontables. Seul le cardinal l'est.

Usage (depuis scripts/python, ASCII only) :

    python probe_10023r1_squig_pool_live.py --seeds 777,31337,4242 --board MC1_67 \
        --state-file <chemin ABSOLU unique>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                              # noqa: E402
from rl_collect_batch import _rpc                          # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.effect_type import EffectType         # noqa: E402

SQUIG_MINE = int(ActiveAbilityType.SquigMine)              # 1201
SQUIG_MINE_TILE = int(EffectType.SquigMine_Tile)           # 1441
MOW = "orksRukkatrukk"


def _r(sid, method, body, timeout=90):
    res = _rpc(sid, method, [body], timeout=timeout)
    return res.get("result") if isinstance(res, dict) and "result" in res else res


def _session_id(sf: dict):
    s = sf.get("session")
    return s.get("id") if isinstance(s, dict) else s


def _build(seed: int, board: str, state_file: str):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
         "--p-mow", MOW, "--p-units", "orksWarboss,orksNob",
         "--a-units", "necroWarden,necroDestroyer", "--state-file", state_file],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    p = Path(state_file)
    if not p.exists():
        print("  [build KO] %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return None, None
    sf = json.loads(p.read_text(encoding="utf-8"))
    return _session_id(sf), sf.get("runnerId")


def _tuiles_minees(tm) -> set:
    """Les (col,row) portant `1441 SquigMine_Tile` -- `tileMeta.tiles[].effects`, le SEUL canal ou
    un marquage de TUILE est visible (`readEffectsByTile`, cf. `probe_90b_mow_effects.py`)."""
    out = set()
    for t in (tm.get("tiles") or []):
        for e in (t.get("effects") or []):
            eid = e.get("effectType", e.get("type", e.get("id")))
            if eid == SQUIG_MINE_TILE:
                out.add((int(t["col"]), int(t["row"])))
    return out


def _libres(tm) -> set:
    """Les (col,row) LIBRES -- approximation PORTEE de `CanAddUnit`, servant UNIQUEMENT a estimer
    |pool| pour choisir une cible et a garder le denominateur du raisonnement. AUCUNE conclusion
    n'en depend : le verdict repose sur le CARDINAL des tuiles minees, mesure live.

    L'occupation est LUE (`tileMeta.tiles[].occupantId`, capteur `readTileOccupant`), pas
    reconstruite depuis les pieds de `decisionView` -- un pied secondaire y serait invisible."""
    out = set()
    for t in (tm.get("tiles") or []):
        if t.get("isWall") or t.get("isInFog"):
            continue
        if t.get("occupantId") is not None:
            continue
        out.add((int(t["col"]), int(t["row"])))
    return out


def _un_cast(sid, rid, cible_min: bool) -> dict:
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == MOW), None)
    if m is None:
        return {"erreur": "MoW %s absent de decisionView.mows" % MOW}
    caster = m["casterId"]
    at = _r(sid, "abilityTargets",
            {"runnerId": rid, "unitId": caster, "abilityType": SQUIG_MINE}) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = [t for t in (((row.get("abilities") or [{}])[0].get("targets") or []) if row else [])
            if t.get("kind") == "tile"]
    if not tgts:
        return {"erreur": "aucune cible TUILE legale"}
    tm_b = _r(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    libres = _libres(tm_b)
    rng = 2                                     # `GetNumberConstant(0x16) = range` (gameconfig)

    def _pool(c):
        return {p for p in hexgeo.disk(c[0], c[1], rng) if p in libres and p != c}

    coords = [(int(t["tile"]["col"]), int(t["tile"]["row"])) for t in tgts]
    #: On vise la cible dont le disque est le PLUS PETIT (mais >= 1) : `P(cible tiree)` monte.
    coords.sort(key=lambda c: len(_pool(c)))
    cible = coords[0] if cible_min else coords[len(coords) // 2]
    pool_sans_cible = _pool(cible)
    avant = _tuiles_minees(tm_b)
    res = _r(sid, "applyAction",
             {"runnerId": rid, "action": {"kind": "ability", "casterId": caster,
                                          "abilityType": SQUIG_MINE,
                                          "to": {"col": cible[0], "row": cible[1]}}}) or {}
    act = (res.get("actions") or [{}])[0]
    tm_a = _r(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    minees = _tuiles_minees(tm_a) - avant
    return {"caster": caster, "cible": cible, "castOk": bool(act.get("ok")) and not act.get("error"),
            "erreur": act.get("error"),
            "poolEstimeSansCible": len(pool_sans_cible), "minees": sorted(minees),
            "nMinees": len(minees), "cibleMinee": cible in minees}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777,31337,4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--nr-of-tiles", type=int, default=4,
                    help="`nrOfTiles[level]` attendu -- LU au tooltip i2 (« 4 random free hexes »)")
    ap.add_argument("--cible-mediane", action="store_true",
                    help="vise une cible de disque MEDIAN au lieu du plus petit")
    a = ap.parse_args()
    n = int(a.nr_of_tiles)
    preuve = False
    lignes = []
    for s in [int(x) for x in a.seeds.split(",") if x.strip()]:
        sid, rid = _build(s, a.board, a.state_file)
        if sid is None:
            lignes.append((s, {"erreur": "build KO"}))
            continue
        try:
            d = _un_cast(sid, rid, not a.cible_mediane)
        finally:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                        # noqa: BLE001
                pass
        lignes.append((s, d))
        print("[seed %d] %s" % (s, json.dumps(d, ensure_ascii=True)))
        if d.get("castOk") and d.get("nMinees") == n and d.get("poolEstimeSansCible", 0) >= n:
            preuve = True
            print("           ^ PREUVE : %d tuiles minees pour nrOfTiles=%d avec un pool de %d "
                  "-- la CIBLE a ete tiree, donc elle EST dans le pool natif."
                  % (d["nMinees"], n, d["poolEstimeSansCible"]))
    print("")
    print("=== VERDICT ===")
    ok = [d for _, d in lignes if d.get("castOk") and d.get("poolEstimeSansCible", 0) >= n]
    if not ok:
        print("NON CONFRONTE : aucun cast exploitable (%s)"
              % [d.get("erreur") or "pool trop petit" for _, d in lignes])
        return 2
    cardinaux = sorted({d["nMinees"] for d in ok})
    print("casts exploitables : %d ; cardinaux observes : %s ; nrOfTiles = %d"
          % (len(ok), cardinaux, n))
    if preuve:
        print("H_GARDE : au moins un cast a rendu nrOfTiles -- la cible EST dans le pool, donc le")
        print("natif la GARDE dans `SurroundingTiles(includeCenter=0)`.")
        return 0
    #: Aucun cast n'a rendu `nrOfTiles`. Sous l'hypothese « la cible est dans le pool », chaque
    #: cast avait `p = n / (|pool| + 1)` de la tirer ; la probabilite de N ratages d'affilee est
    #: le produit des `(1 - p)`. Un produit assez petit REJETTE l'hypothese -- c'est un resultat,
    #: pas une absence de resultat, et c'est ce que la version d'avant se refusait a dire.
    proba = 1.0
    for d in ok:
        proba *= 1.0 - (float(n) / float(d["poolEstimeSansCible"] + 1))
    print("P(ces %d ratages | la cible est DANS le pool) = %.4f" % (len(ok), proba))
    if proba <= 0.01:
        print("H_RETRANCHE : l'hypothese « la cible est dans le pool » est REJETEE a ce seuil.")
        print("Le natif RETRANCHE la tuile ciblee, VIDE -- l'enonce de #10023-r1 disait l'inverse.")
        return 0
    print("NON CONCLUANT : pas assez de casts pour trancher (il en faut jusqu'a P <= 0,01).")
    print("Rejouer avec d'autres seeds, ou viser une cible de disque plus petit.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
