#!/usr/bin/env python3
"""#271-r5 -- le regime SPAWN de la feuille `TriggeredAbilitiesNonOwner(4)`, CONFRONTE LIVE.

CE QUI ETAIT PORTE, ET CE QUI N'AVAIT JAMAIS ETE MESURE
--------------------------------------------------------
#271-r3 a etabli au decompile que TROIS corps non-owner yieldent AUSSI en regime SPAWN
(`case.unit == null && case.parent != null`, call-site `SortTilesByUtilityForSummon`) :
`PsychicFortress` (20), `BookOfFate` (5) et la branche SPAWN de `MawClawsOfThyrax` (5). Le port
est mirror-1:1 et garde par 8 tests offline + 5 mutations -- mais l'OBSERVABLE, **quelle tuile
le natif choisit pour faire apparaitre un summon**, n'avait jamais ete mesure. Un port
mirror-1:1 avec des tests offline reste une HYPOTHESE tant que le natif ne l'a pas confirme.

LE MONTAGE, ET POURQUOI CELUI-LA
---------------------------------
`probe_130_placement_sort_rng.py --case controledict` pilote deja un spawn qui passe par
`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon` : `admecMarshall` attaque, son
passif `ControlEdict` fait apparaitre un `admecSmnVanguard` sur l'anneau-1 du CASTER. Il ne
DISCRIMINE pas ce terme parce que son montage est un 1v1 : aucun des trois porteurs n'est sur le
plateau.

On ajoute `ultraTigurius` (`PsychicFortress`, HERO **du pool** -- aucun montage de relique ni
d'injection catalogue) a l'equipe joueur, place ADJACENT au Marshall. Il couvre alors une partie
de l'anneau de spawn, donc `+20` sur ces tuiles-la et 0 sur les autres.

⚠ **Le discriminant est l'ECART DE COMPOSITE, pas le terme seul.** `ElevationUtility` vaut
`10 x elev` (+10 au max du board, -5 au min) : deux tuiles separees de 2 d'elevation annulent
exactement le +20. La geometrie est donc CHERCHEE (etape 1, offline, sur le board dumpe) avant
d'etre montee : on ne monte que si le +20 RENVERSE effectivement l'argmax.

LES TROIS BRAS
---------------
  * **port SANS le terme** (`PsychicFortressNonOwnerPlaybook` neutralise) -> tuile X ;
  * **port AVEC**                                                        -> tuile Y != X ;
  * **NATIF**                                                            -> doit valoir **Y**.

Le bras SANS est obligatoire : sans lui, un accord natif/port ne distingue pas << le terme porte
le resultat >> de << il vient d'ailleurs >>.

    python probe_271r5_spawn_non_owner_live.py --board MC1_67 --seed 777
    python probe_271r5_spawn_non_owner_live.py --geometrie-seule    # etape 1 offline

Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402

#: Ce qui doit changer pour que cette confrontation puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/non_owner.py",
                "scripts/python/engine/utilities/tile.py",
                "scripts/python/engine/runner/operations/spawn.py",
                "scripts/python/probe_130_placement_sort_rng.py"),
    "build": False,
    "toujours": False,
    "raison": "Le terme confronte vit dans `playbook/non_owner.py` ; le composite qui le porte "
              "dans `utilities/tile.py` ; le call-site de spawn dans `operations/spawn.py` ; et "
              "le harnais de montage est celui de `probe_130`.",
}

CASTER = "admecMarshall"        # porte `ControlEdict` -> spawn sur l'anneau-1 du CASTER
PORTEUR = "ultraTigurius"       # porte `PsychicFortress` (1000) -- HERO DU POOL
ENNEMI = "necroDestroyer"
TERME = 20.0                    # `PSYCHICFORTRESS_AdjacentFriendly`, valeur du gameconfig vivant


def _build(seed, board, state_file, extra=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board,
           "--p-units", "%s,%s" % (CASTER, PORTEUR), "--a-units", ENNEMI,
           "--hp-target", "90000", "--hp-player", "90000"] + list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-700:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


# ============================================================ ETAPE 1 : la geometrie, OFFLINE
def cherche_geometrie(board, occupees=frozenset()):
    """(C, P, anneau, sans, avec) tel que le `+20` de `PsychicFortress` RENVERSE l'argmax.

    `C` = tuile du Marshall (origine du pool de spawn), `P` = tuile de Tigurius, ADJACENTE a `C`
    (il doit rester a portee pour couvrir une partie de l'anneau). Le pool est l'anneau-1 libre
    de `C`, moins `P` (occupee par Tigurius) et moins la tuile reservee a l'ennemi.

    Purement OFFLINE : `_tile_utility` de `probe_130` evalue le composite `Tile(7)` sur la seule
    metadata que le board porte (elevation + effets de terrain), et le terme non-owner est un
    `+20` sur les tuiles adjacentes a `P`. On ne monte RIEN tant que ce calcul ne rend pas une
    inversion -- monter d'abord et esperer, c'est exactement ce qui a rendu le contre-controle
    de `probe_130` INERTE.
    """
    from engine.runner.operations import spawn as SP
    import hexgeo
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)

    trouves = []
    for C in sorted(board.by_id):
        if not board.walkable(C) or C in occupees:
            continue
        ring = [n for n in SP._adjacent_tiles(board, C)
                if board.walkable(n) and n not in occupees]
        if len(ring) < 4:                      # P + ennemi + au moins 2 candidats
            continue
        for P in ring:
            # l'ennemi occupe la DERNIERE tuile libre de l'anneau (ordre natif), comme dans
            # `probe_130._discriminating_caster_tile`
            reste = [t for t in ring if t != P]
            if len(reste) < 3:
                continue
            tuile_ennemi = reste[-1]
            pool = [t for t in reste if t != tuile_ennemi]
            if len(pool) < 2:
                continue
            pp = board.coord(P)
            sans = {t: P130._tile_utility(board, t, emax, emin) for t in pool}
            avec = {t: sans[t] + (TERME if hexgeo.distance(board.coord(t), pp) == 1 else 0.0)
                    for t in pool}
            # argmax STABLE : a egalite, l'ordre source (natif) tranche -> on prend le premier
            x = max(pool, key=lambda t: (sans[t], -pool.index(t)))
            y = max(pool, key=lambda t: (avec[t], -pool.index(t)))
            if x == y:
                continue
            # le terme doit REELLEMENT etre ce qui renverse : Y doit etre couvert, X non
            if avec[y] - sans[y] <= 0 or avec[x] - sans[x] > 0:
                continue
            # ⚠ `strict` = de combien X bat Y **SANS** le terme. C'est LE discriminant, et le
            # residu voisin #271-r1 est ouvert pour ne pas l'avoir eu : sur un EX AEQUO
            # (`strict == 0`), un tie-break natif fixe produirait le meme renversement que le
            # terme, et la mesure ne trancherait RIEN. On les garde -- ils restent des montages
            # valables -- mais le tri les met DERNIERS.
            # ⚠ IL FAUT LES DEUX ECARTS, et c'est le coeur de la lecon de #271-r1 :
            #   `strict` = de combien X bat Y **SANS** le terme ;
            #   `marge`  = de combien Y bat X **AVEC**.
            # Si `strict == 0`, un tie-break natif fixe produirait le meme renversement que le
            # terme. Si `marge == 0`, c'est l'argmax stable qui tranche APRES, et le terme n'a
            # fait qu'egaliser -- le natif pourrait rendre X sans que le port ait tort. Seul
            # `min(strict, marge) > 0` fait une confrontation qui TRANCHE.
            trouves.append({"C": C, "P": P, "ennemi": tuile_ennemi, "pool": pool,
                            "sans": sans, "avec": avec, "X": x, "Y": y,
                            "strict": sans[x] - sans[y],
                            "marge": avec[y] - avec[x]})
    trouves.sort(key=lambda d: (-min(d["strict"], d["marge"]), -d["strict"], -d["marge"]))
    return trouves


# ============================================================ ETAPE 2 : le montage LIVE
class _SansPsychicFortress:
    """Neutralise le SEUL terme confronte -- le bras TEMOIN.

    On substitue la methode de la CLASSE (pas le registre) : retirer la classe du registre
    testerait aussi le cablage, alors que la question est << ce terme-la porte-t-il le
    resultat ? >>.
    """

    def __enter__(self):
        from engine.playbook.non_owner import PsychicFortressNonOwnerPlaybook as K
        self.K = K
        self.saved = K.calculate_movement_utility_in_steps
        K.calculate_movement_utility_in_steps = (
            lambda self, tile, owner, is_friend, ctx, wt: 0.0)
        return self

    def __exit__(self, *a):
        self.K.calculate_movement_utility_in_steps = self.saved
        return False


def _tuiles_de(dv, board):
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos")
        if not (u.get("alive") and p):
            continue
        t = board.id_at(p["col"], p["row"])
        if t is not None:
            out[u["id"]] = t
    return out


def confronte(rpc, seed, board_id, geo, verbeux=False) -> dict:
    """Monte la geometrie `geo`, declenche l'attaque, et rend les trois bras."""
    from engine.entities.pathfinding.board import Board

    sf = ROOT / "logs" / "runners" / ("probe271r5-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(seed, board_id, sf)
    if rid is None:
        return {"ok": False, "raison": "build KO"}
    out = {"ok": False, "rid": rid}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"ok": False, "raison": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        dv = dview()
        me = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER and u.get("alive")), None)
        tig = next((u for u in (dv.get("units") or [])
                    if u.get("visualId") == PORTEUR and u.get("alive")), None)
        if me is None or tig is None:
            return {"ok": False, "raison": "caster ou porteur absent du montage"}
        myplayer = me.get("owner")
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myplayer:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = dview()
        if dv.get("currentPlayer") != myplayer:
            return {"ok": False, "raison": "pas notre tour"}
        me = next(u for u in dv["units"] if u.get("visualId") == CASTER and u.get("alive"))
        tig = next(u for u in dv["units"] if u.get("visualId") == PORTEUR and u.get("alive"))
        enemy = next((u for u in (dv.get("units") or [])
                      if u.get("owner") != myplayer and u.get("alive")
                      and u.get("visualId") == ENNEMI), None)
        if enemy is None:
            return {"ok": False, "raison": "ennemi absent"}
        cid, pid, eid = me["id"], tig["id"], enemy["id"]

        # --- poser les trois unites sur la geometrie cherchee
        for uid, cible, quoi in ((cid, geo["C"], "caster"), (pid, geo["P"], "porteur"),
                                 (eid, geo["ennemi"], "ennemi")):
            c = board.coord(cible)
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)
            if not P130._ok(r):
                return {"ok": False, "raison": "move %s -> t%s refuse : %s"
                                               % (quoi, cible, str(r)[:160])}

        dv = dview()
        me = next(u for u in dv["units"] if u["id"] == cid)
        ab = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if ab is None:
            return {"ok": False, "raison": "attaque normale introuvable"}

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
        if not P130._ok(rng_before):
            return {"ok": False, "raison": "dumpRng KO"}
        avant = _tuiles_de(dv, board)

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ab.get("id")},
            "captureEvents": True}, 150)
        if not P130._ok(cast):
            return {"ok": False, "raison": "cast KO : %s" % str(cast)[:200]}
        apres = _tuiles_de(dview(), board)
        natif = sorted(t for uid, t in apres.items() if uid not in avant)

        reg = {"dv": dv, "ob": ob, "snap": snap, "board": board, "cid": cid, "target": eid,
               "rng_before": rng_before, "case": "controledict"}
        avec = _rejoue(reg)
        with _SansPsychicFortress():
            sans = _rejoue(reg)

        out.update({"ok": True, "natif": natif, "port_avec": avec, "port_sans": sans,
                    "geo": {k: geo[k] for k in ("C", "P", "ennemi", "X", "Y", "marge")}})
        return out
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


def _rejoue(reg) -> list:
    """Tuiles de spawn rendues par le PORT sur l'etat PRE-cast (modele courant, 0 tirage)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import PositionComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    st.rng = P130.CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    avant = set(st.entities.keys())
    Runner(st).install_default_handlers(20).apply(AttackUnitMessage(reg["cid"], reg["target"]))
    tuiles = []
    for eid in st.entities:
        if eid in avant:
            continue
        pc = st.get_entity(eid).get_component(PositionComponent)
        if pc is not None:
            t = reg["board"].id_at(pc.col, pc.row)
            if t is not None:
                tuiles.append(t)
    return sorted(tuiles)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--geometrie-seule", action="store_true",
                    help="etape 1 seule (offline) : cherche une geometrie discriminante")
    ap.add_argument("--essais", type=int, default=3,
                    help="nombre de geometries candidates a MONTER avant d'abandonner")
    ap.add_argument("-v", "--verbeux", action="store_true")
    args = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    rpc = P130.Rpc()

    # Le board sur lequel on CHERCHE doit etre celui sur lequel on MONTERA : le dump versionne
    # (`data/boards/global/<id>.json`) porte la geometrie brute du jeu, pas la forme de
    # `boardGraph` -- et surtout pas la metadata que le runner hydrate. On monte donc un runner
    # SONDE, on lui prend son `boardGraph`, et on le dispose aussitot.
    sonde = ROOT / "logs" / "runners" / ("probe271r5-sonde-%s.json" % uuid.uuid4().hex[:8])
    sonde.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(args.seed, args.board, sonde)
    if rid is None:
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sonde).unlink(missing_ok=True)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("boardGraph indispo -- NON MESURE, pas 'aucune geometrie'")
        return 2
    board = Board(bg["tiles"], adjacency="native_sym")

    print("=== (1) GEOMETRIE DISCRIMINANTE (calculee sur le boardGraph de %s) ===" % args.board)
    cands = cherche_geometrie(board)
    print("geometries ou le +20 de PsychicFortress RENVERSE l'argmax : %d" % len(cands))
    if not cands:
        print("  AUCUNE. Le +20 ne renverse le composite Tile(7) nulle part sur ce board :")
        print("  `ElevationUtility` vaut 10 x elev, donc 2 crans d'elevation l'annulent.")
        print("  Essayer un autre board (--board) avant de conclure.")
        return 1
    stricts = [d for d in cands if min(d["strict"], d["marge"]) > 0]
    print("  dont a DOUBLE ecart strictement positif (X bat Y sans, Y bat X avec) : %d"
          % len(stricts))
    print("  (`strict == 0` : un tie-break natif fixe produirait le meme renversement --")
    print("   c'est ce qui laisse #271-r1 ouvert. `marge == 0` : le terme n'a fait qu'EGALISER,")
    print("   et c'est l'argmax stable qui tranche apres. Seuls les deux ensemble TRANCHENT.)")
    for d in cands[:5]:
        print("  C=t%-4s P=t%-4s ennemi=t%-4s | sans -> t%-4s  avec -> t%-4s  strict=%+.0f marge=%.0f"
              % (d["C"], d["P"], d["ennemi"], d["X"], d["Y"], d["strict"], d["marge"]))
        if args.verbeux:
            for t in d["pool"]:
                print("      t%-4s sans=%7.1f avec=%7.1f" % (t, d["sans"][t], d["avec"][t]))
    print("")
    if args.geometrie_seule:
        return 0

    print("=== (2) CONFRONTATION LIVE (3 bras) ===")
    for i, geo in enumerate(cands[:args.essais]):
        print("-- essai %d : C=t%s P=t%s ennemi=t%s (attendu : sans->t%s, avec->t%s)"
              % (i + 1, geo["C"], geo["P"], geo["ennemi"], geo["X"], geo["Y"]))
        r = confronte(rpc, args.seed, args.board, geo, args.verbeux)
        if not r.get("ok"):
            print("   NON MONTE : %s" % r.get("raison"))
            continue
        print("   port SANS le terme : %s" % r["port_sans"])
        print("   port AVEC le terme : %s" % r["port_avec"])
        print("   NATIF              : %s" % r["natif"])
        if r["port_sans"] == r["port_avec"]:
            print("   NON DISCRIMINANT : les deux bras du PORT coincident -- l'accord avec le")
            print("   natif ne prouverait rien. (Le calcul offline predisait une inversion : le")
            print("   substrat live porte donc une metadata que le dump de board n'a pas.)")
            continue
        verdict = ("NATIF == AVEC (le terme porte le resultat)" if r["natif"] == r["port_avec"]
                   else "NATIF == SANS (le terme est de TROP)" if r["natif"] == r["port_sans"]
                   else "NATIF != les deux bras")
        print("   VERDICT : %s" % verdict)
        return 0 if r["natif"] == r["port_avec"] else 1
    print("")
    print("NON CONFRONTE : aucune des %d geometries essayees n'a pu etre montee ou n'a"
          % min(args.essais, len(cands)))
    print("discrimine. Ce n'est PAS un verdict sur le port.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
