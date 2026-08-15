"""#1027-r1 -- LE NATIF MELANGE-T-IL VRAIMENT LES EX AEQUO DE `SortByRow(sameColumnIsRandom: 1)` ?

Le decompile dit OUI : `IdunBattle.Entities.Selectors.SortByRowSelector$$Select` ajoute un 3e
`ThenBy(<b__3>)` quand `+0x28` est arme, et
`...SortByRowSelector.u003Cu003Ec__DisplayClass6_0$$u003CSelectu003Eb__3(this, s)` **ignore `s`** :
il rend `pseudoRng.<IPseudoRNG slot 1 = Next(n)>(GetMatchBoard(state).<+0x14 = Width>)`, donc un
tirage FRAIS par element.

Ce probe le CONFRONTE **sans exiger que le flux PRNG du port soit aligne sur celui du natif** : il
ne compare pas port vs natif, il compare le NATIF A LUI-MEME sur des graines differentes.

    meme board, memes rosters et memes PLACEMENTS EXPLICITES (donc geometrie IDENTIQUE),
    seule la GRAINE change  ->  si les tuiles de spawn d'`InvocationOfMachineVengeance` (1172)
    VARIENT, le 3e `ThenBy` est vivant, et un port qui prend toujours les premieres tuiles de
    l'ordre source est FAUX.

⚠ **UN ACCORD NE PROUVERAIT RIEN S'IL EST DEGENERE.** Si `nrOfSummons >= #tuiles candidates`, ou
si une seule tuile porte la row minimale, les tuiles seront identiques quelle que soit la graine.
Le probe MESURE donc aussi le nombre de tuiles retenues et le nombre de tuiles libres de la row
gagnante, et REFUSE de conclure quand le temoin est degenere.

    python probe_1027r1_sort_by_row_pseudo_rng.py --state-file <ABSOLU hors data/> [--seeds a,b,c]

Sortie ASCII. Ce probe MESURE ; le cliquet est l'etage 9 de
`tests/engine/runner/test_1027_belisarius_actives_offline.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from probe_r6_round_materialize import _mkrpc                     # noqa: E402

BOARD = "MC1_67"
IMV = 1172                       # `ActiveAbilityType.InvocationOfMachineVengeance`
SUMMON_VIS = "admecSmnTechpriest"     # `GetStringConstant(config, 0 = unitId)`
BOSS = "admecBossBelisarius:4"
P_UNITS = BOSS
A_UNITS = "admecMarshall"


def _build(sf: str, seed: int) -> tuple:
    """Monte le runner. Rosters MINIMAUX et placement EXPLICITE : la geometrie doit etre
    IDENTIQUE d'une graine a l'autre, sinon la variation mesuree n'accuserait pas le PRNG."""
    env = dict(os.environ)
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    cmd = [sys.executable, "rl_duel.py", "build", "--board", BOARD, "--seed", str(seed),
           "--state-file", sf, "--explicit-stats", BOSS,
           "--p-units", P_UNITS, "--a-units", A_UNITS, "--no-ai"]
    p = subprocess.run(cmd, cwd=_HERE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=420)
    if not os.path.exists(sf):
        return None, (p.stderr or p.stdout or "")[-500:]
    return int(json.loads(open(sf, "r", encoding="utf-8").read())["runnerId"]), None


def _pos(u) -> tuple:
    """`decisionView` publie la position sous `pos: {col, row}` -- pas a plat."""
    p = u.get("pos") or {}
    return (int(p.get("col")), int(p.get("row")))


def _par_id(dv) -> dict:
    """⚠ ON IDENTIFIE LES SUMMONS PAR **DIFFERENCE D'IDS**, PAS PAR `visualId` : sur un montage
    de GUILD BOSS, le canal publie l'id VISUEL du contenu de guilde (`admecBossBelisarius` sort
    en `GuildBoss10Boss1AdmecBelisarius`), donc un filtre sur `admecSmnTechpriest` rendrait
    ZERO -- et ce zero se lirait comme << aucun spawn >>."""
    return {int(u["id"]): (_pos(u), str(u.get("visualId") or "")) for u in (dv.get("units") or [])}


def une_graine(rpc, sf: str, seed: int) -> dict:
    rid, err = _build(sf, seed)
    if rid is None:
        return {"seed": seed, "erreur": "build : %s" % err}
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        boss = next((u for u in (dv.get("units") or [])
                     if "Belisarius" in str(u.get("visualId") or "")), None)
        if boss is None:
            return {"seed": seed, "erreur": "Belisarius absent de la vue"}
        avant = _par_id(dv)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(boss["id"]),
            "targetId": int(boss["id"]), "abilityType": IMV}, "captureEvents": True}, 180)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        apres = _par_id(dv2)
        neufs = sorted(apres[i][0] for i in (set(apres) - set(avant)))
        return {"seed": seed, "caster": boss["id"], "pos": _pos(boss),
                "vis": sorted({apres[i][1] for i in (set(apres) - set(avant))}),
                "nouvelles": neufs, "ok": bool(res.get("ok", True))}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                          # noqa: BLE001
            pass


def cote_port(seeds: list, largeur: int, candidats: list, combien: int) -> dict:
    """ETAGE PORT (100 % offline) -- le pendant de la mesure live : le noeud `SortByRow` du port
    varie-t-il AUSSI avec la graine ?

    Un port qui rendrait toujours les memes tuiles serait un echec SILENCIEUX : la mesure live
    ci-dessus prouve que le natif melange, mais elle ne dit rien de ce que fait le port. On rejoue
    donc `PickFirstN(SortByRow(<candidats>, sameColumnIsRandom=1, ascending=1), n)` avec le VRAI
    `IntBasedMersenneTwister`, une graine par colonne."""
    from dataclasses import dataclass, field

    from engine.dsl.base import Const
    from engine.entities.selectors._pick import PickFirstN
    from engine.entities.selectors.geometry import SortByRow
    from engine.runner.prng import IntBasedMersenneTwister

    class _B:
        def __init__(self, tuiles):
            self.by_id = {i: {"id": i, "col": c, "row": r} for i, (c, r) in enumerate(tuiles)}

        def coord(self, tid):
            t = self.by_id[tid]
            return (t["col"], t["row"])

    class _Src:
        def __init__(self, ids):
            self.ids = list(ids)

        def evaluate(self, ctx):
            return list(self.ids)

    @dataclass
    class C:
        board: object = None
        subject: object = None
        active_target: object = None
        pseudo_rng_next: object = None

    board = _B(candidats)
    out = {}
    for s in seeds:
        rng = IntBasedMersenneTwister(s)
        ctx = C(board=board, pseudo_rng_next=rng.next)
        sel = PickFirstN(SortByRow(_Src(sorted(board.by_id)), same_column_is_random=True,
                                   ascending=True), Const(combien))
        out[s] = sorted(board.coord(t) for t in sel.evaluate(ctx))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seeds", default="777,31337,4242,90210")
    a = ap.parse_args()
    rpc = _mkrpc()
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]

    res = []
    for s in seeds:
        r = une_graine(rpc, a.state_file, s)
        res.append(r)
        if "erreur" in r:
            print("[seed %-6d] ERREUR : %s" % (s, r["erreur"]))
        else:
            print("[seed %-6d] caster u%s %s -> %d summon(s) %s sur %s"
                  % (s, r["caster"], r["pos"], len(r["nouvelles"]), r["vis"], r["nouvelles"]))

    ok = [r for r in res if "erreur" not in r and r["nouvelles"]]
    print("")
    if len(ok) < 2:
        print("VERDICT : NON CONCLUANT -- moins de deux graines ont produit un spawn (%d/%d)."
              % (len(ok), len(seeds)))
        return 2
    distincts = {tuple(r["nouvelles"]) for r in ok}
    print("graines exploitables : %d ; jeux de tuiles DISTINCTS : %d" % (len(ok), len(distincts)))
    for t in sorted(distincts):
        print("   %s  <- graines %s"
              % (list(t), [r["seed"] for r in ok if tuple(r["nouvelles"]) == t]))
    if len(distincts) > 1:
        print("VERDICT NATIF : le natif MELANGE. Memes rosters, meme board, meme geometrie -- "
              "seules les graines different, et les tuiles de spawn changent. Le 3e "
              "`ThenBy(pseudoRng)` est VIVANT, et un port qui rend toujours l'ordre source est FAUX.")
        # --- ETAGE PORT : la meme question, posee au port ------------------------------------
        vues = sorted({t for r in ok for t in r["nouvelles"]})
        combien = max(len(r["nouvelles"]) for r in ok)
        largeur = max(c for c, _r in vues) + 1
        cand = [(c, vues[0][1]) for c in range(largeur)]      # la row gagnante, pleine
        print("")
        print("[port] candidats reconstruits : %d tuiles de row %d, largeur %d, n = %d"
              % (len(cand), vues[0][1], largeur, combien))
        p = cote_port(seeds, largeur, cand, combien)
        for s in seeds:
            print("   seed %-6d -> %s" % (s, p.get(s)))
        if len({tuple(v) for v in p.values()}) > 1:
            print("VERDICT PORT : le port MELANGE lui aussi (les graines rendent des tuiles "
                  "differentes). NON COUVERT : l'accord TUILE A TUILE avec le natif, qui exigerait "
                  "que le flux PRNG du port soit a la MEME POSITION qu'au cast natif.")
        else:
            print("VERDICT PORT : le port rend LES MEMES tuiles sur toutes les graines -- le "
                  "tirage n'a pas mordu. A INVESTIGUER avant de livrer.")
            return 3
        return 0
    print("VERDICT : ACCORD SUR TOUTES LES GRAINES, ET CET ACCORD NE PROUVE RIEN tant qu'on n'a "
          "pas etabli qu'il y avait des ex aequo a departager (regime DEGENERE : une seule tuile "
          "de row minimale, ou nrOfSummons >= #candidats). A ECARTER, pas a compter.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
