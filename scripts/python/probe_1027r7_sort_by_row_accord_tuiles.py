"""#1027-r7 -- L'ACCORD **TUILE A TUILE** de `SortByRow(sameColumnIsRandom: 1)`, flux PRNG ALIGNE.

CE QUE #1027-r1 AVAIT LAISSE OUVERT, ET POURQUOI
-----------------------------------------------
`probe_1027r1_sort_by_row_pseudo_rng.py` etablit que les DEUX melangent : quatre graines rendent
quatre jeux de tuiles distincts, cote natif ET cote port, a geometrie identique. Il ne les
COMPARE pas -- il ne le peut pas, parce que son etage port repart d'un twister FRAIS alors que le
natif a deja consomme des tirages au montage de la bataille. Deux flux desalignes ne peuvent pas
rendre les memes tuiles, meme si le port est exact.

CE PROBE FERME CET ECART, par le patron `_replay` de `probe_1073_synaptic_insight.py` :

    1. build du runner, puis CAPTURE de l'etat JUSTE AVANT le cast --
       `decisionView` + `observeBattle` + `combatSnapshot` + **`dumpRng`** (l'etat interne du
       Mersenne Twister : `mt` et `mti`) ;
    2. cast d'`InvocationOfMachineVengeance` (1172) EN LIVE -> les tuiles de spawn NATIVES,
       identifiees par DIFFERENCE D'IDS (jamais par `visualId` : sur un montage de guild boss le
       canal publie l'id visuel du contenu de guilde -- lecon de #1027-r1) ;
    3. rejeu du MEME cast dans le Runner du port, sur l'etat charge, avec le twister REMIS
       EXACTEMENT dans l'etat capture ;
    4. comparaison TUILE A TUILE.

CE QUE CET ACCORD PROUVE, ET QUE LA MESURE DE #1027-r1 NE POUVAIT PAS PROUVER
----------------------------------------------------------------------------
Le **COMPTE** de tirages. `SortByRow` doit tirer exactement `len(items)` fois -- une cle par
element de la source, dans l'ordre SOURCE (`EnumerableSorter.ComputeKeys` descend la chaine par
NIVEAU). Un tirage de TROP ou de MOINS ne casse rien de visible : il decale le flux, et les
tuiles retenues changent. A flux ALIGNE, l'accord tuile a tuile est donc un test du compte autant
que de l'ordre -- c'est la seule mesure qui les atteigne tous les deux.

CONTRE-EPREUVE INTEGREE (`--mutants`). Un accord ne vaut que si le montage sait RENDRE UN
DESACCORD. Trois mutants du seul etage en cause, joues sur la MEME capture :
  * `sansTirage`   : `pseudo_rng_next` non branche -> le port garde l'ordre source ;
  * `tirageEnTrop` : un tirage supplementaire AVANT le tri -> flux decale d'un cran ;
  * `borneHauteur` : borne `height` au lieu de `width` (`BoardComponent+0x10` au lieu de `+0x14`).
Si l'un d'eux rend EGAL, le temoin est degenere et le probe le DIT.

    python probe_1027r7_sort_by_row_accord_tuiles.py --state-file <ABSOLU hors data/> [--seeds ...]

Sortie ASCII. Ce probe MESURE ; le cliquet est
`tests/engine/runner/test_1027r7_sort_by_row_accord_offline.py`.
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
IMV = 1172                            # `ActiveAbilityType.InvocationOfMachineVengeance`
BOSS = "admecBossBelisarius:4"
P_UNITS = BOSS
A_UNITS = "admecMarshall"

#: Ce qui doit changer pour que cette mesure change d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/selectors/geometry.py",
                "scripts/python/engine/runner/abilities/admec.py",
                "scripts/python/engine/runner/prng.py",
                "scripts/python/engine/runner/snapshot.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le noeud `SortByRow` du port au cast natif d'IMV, flux PRNG aligne. "
              "Le noeud, l'arbre de l'ability, le twister et le chargeur d'etat sont les quatre "
              "etages qu'il traverse.",
}


def _build(sf: str, seed: int):
    """Rosters MINIMAUX et placement EXPLICITE -- meme montage que #1027-r1, pour que la seule
    variable soit la graine."""
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


def _pos(u):
    p = u.get("pos") or {}
    return (int(p.get("col")), int(p.get("row")))


def _ids_pos(dv):
    return {int(u["id"]): _pos(u) for u in (dv.get("units") or []) if u.get("pos")}


def _rejouer(cap, board, caster_id: int, mutant=None) -> dict:
    """Rejoue le cast d'IMV dans le Runner du port, twister REMIS dans l'etat capture.

    `mutant` desarme un etage precis du noeud `SortByRow` -- c'est la contre-epreuve : un montage
    qui ne sait pas rendre un DESACCORD ne prouve rien par son accord.
    """
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.entities.selectors import geometry as GEO

    vrai_cles = GEO.SortByRow._pseudo_rng_keys
    vrai_larg = GEO._board_width
    appels = [0]
    try:
        if mutant == "sansTirage":
            def _rien(self, ctx, combien):
                appels[0] += 1
                return None
            GEO.SortByRow._pseudo_rng_keys = _rien
        elif mutant == "tirageEnTrop":
            def _un_de_trop(self, ctx, combien):
                appels[0] += 1
                tirer = getattr(ctx, "pseudo_rng_next", None)
                if tirer is not None:
                    tirer(GEO._board_width(getattr(ctx, "board", None)) or 1)   # LE tirage en trop
                return vrai_cles(self, ctx, combien)
            GEO.SortByRow._pseudo_rng_keys = _un_de_trop
        elif mutant == "borneHauteur":
            def _hauteur(board_):
                appels[0] += 1
                h = getattr(board_, "height", None)
                if h is None and getattr(board_, "by_id", None):
                    h = max(t["row"] for t in board_.by_id.values()) + 1
                return h
            GEO._board_width = _hauteur

        from engine.runner.components import PositionComponent

        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        avant = set(st.entities)
        runner = Runner(st).install_default_handlers(20)
        res = runner.apply(ActiveAbilityMessage(int(caster_id), int(caster_id), IMV))
        neufs = []
        for uid in (set(st.entities) - avant):
            e = st.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            if pc is not None and getattr(pc, "col", None) is not None:
                neufs.append((int(pc.col), int(pc.row)))
        return {"tuiles": sorted(neufs), "mutant_appels": appels[0],
                "neufs": len(set(st.entities) - avant), "res": res}
    finally:
        GEO.SortByRow._pseudo_rng_keys = vrai_cles
        GEO._board_width = vrai_larg


def une_graine(rpc, sf: str, seed: int, mutants: bool) -> dict:
    from engine.entities.pathfinding.board import Board

    rid, err = _build(sf, seed)
    if rid is None:
        return {"seed": seed, "erreur": "build : %s" % err}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        boss = next((u for u in (dv.get("units") or [])
                     if "Belisarius" in str(u.get("visualId") or "")), None)
        if boss is None:
            return {"seed": seed, "erreur": "Belisarius absent de la vue"}
        cid = int(boss["id"])
        avant = _ids_pos(dv)
        # LA CAPTURE, prise AVANT le cast -- `dumpRng` en fait partie : sans lui le rejeu repart
        # d'un twister frais et l'accord est structurellement hors d'atteinte (#1027-r1).
        cap = {"dec": dv, "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": cid,
            "abilityType": IMV}, "captureEvents": True}, 180)
        apres = _ids_pos(rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180))
        natif = sorted(apres[i] for i in (set(apres) - set(avant)))
        if not natif:
            return {"seed": seed, "erreur": "aucun spawn natif (ok=%s)" % res.get("ok")}
        out = {"seed": seed, "caster": cid, "natif": natif}
        port = _rejouer(cap, board, cid)
        out["port"] = port["tuiles"]
        out["port_neufs"] = port.get("neufs")
        out["port_res"] = port.get("res")
        out["verdict"] = "EGAL" if out["port"] == natif else "DIVERGE"
        if mutants:
            out["mutants"] = {}
            for m in ("sansTirage", "tirageEnTrop", "borneHauteur"):
                r = _rejouer(cap, board, cid, mutant=m)
                out["mutants"][m] = {
                    "tuiles": r["tuiles"], "appels": r["mutant_appels"],
                    "verdict": "EGAL" if r["tuiles"] == natif else "DIVERGE"}
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                          # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seeds", default="777,31337,4242")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les trois contre-epreuves sur chaque capture")
    a = ap.parse_args()
    rpc = _mkrpc()
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]

    res = []
    for s in seeds:
        r = une_graine(rpc, a.state_file, s, a.mutants)
        res.append(r)
        if "erreur" in r:
            print("[seed %-6d] ERREUR : %s" % (s, r["erreur"]))
            continue
        print("[seed %-6d] natif=%s" % (s, r["natif"]))
        print("             port =%s  (entites neuves cote port : %s)  -> %s"
              % (r["port"], r.get("port_neufs"), r["verdict"]))
        if not r["port"]:
            print("             [diag] retour du runner : %r" % (r.get("port_res"),))
        for m, d in (r.get("mutants") or {}).items():
            print("             mutant %-13s %s  appels=%d  -> %s"
                  % (m, d["tuiles"], d["appels"], d["verdict"]))

    ok = [r for r in res if "erreur" not in r]
    print("")
    if not ok:
        print("VERDICT : NON MESURE -- aucune graine exploitable.")
        return 2
    # NON-DEGENERESCENCE : si toutes les graines rendent les MEMES tuiles, il n'y avait rien a
    # departager et l'accord ne dit rien du melange.
    jeux = {tuple(r["natif"]) for r in ok}
    if len(ok) > 1 and len(jeux) == 1:
        print("VERDICT : NON CONCLUANT -- les %d graines rendent LES MEMES tuiles natives (%s). "
              "Regime degenere : aucun ex aequo a departager." % (len(ok), sorted(jeux)[0]))
        return 1
    diverge = [r for r in ok if r["verdict"] == "DIVERGE"]
    print("graines mesurees : %d ; jeux de tuiles natifs distincts : %d ; DIVERGE : %d"
          % (len(ok), len(jeux), len(diverge)))
    if a.mutants:
        inertes = sorted({m for r in ok for m, d in (r.get("mutants") or {}).items()
                          if d["verdict"] == "EGAL"})
        jamais = sorted({m for r in ok for m, d in (r.get("mutants") or {}).items()
                         if not d["appels"]})
        if jamais:
            print("MUTANT NON TRAVERSE : %s -- le binding patche n'est pas celui que le port lit. "
                  "Aucun verdict." % jamais)
            return 3
        if inertes:
            print("TEMOIN DEGENERE : le(s) mutant(s) %s rendent EGAL. Ce montage ne sait pas "
                  "distinguer un port juste d'un port faux -- l'accord ne prouve rien." % inertes)
            return 3
        print("contre-epreuves : les 3 mutants DIVERGENT sur toutes les graines.")
    if diverge:
        print("VERDICT : DIVERGE sur %d graine(s). L'accord tuile a tuile n'est PAS etabli."
              % len(diverge))
        return 1
    print("VERDICT : ACCORD TUILE A TUILE sur %d graine(s), flux PRNG ALIGNE. Le COMPTE de tirages "
          "(un par element de la source) est donc exact, pas seulement plausible -- un tirage de "
          "trop decalerait le flux et changerait les tuiles (c'est ce que montre le mutant "
          "`tirageEnTrop`)." % len(ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
