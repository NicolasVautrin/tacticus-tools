"""#272 -- pourquoi la feuille `CapturePointTileUtility` rendait 0.0 la ou le montage attend +300.

CRITERE BINAIRE (celui du cas) : la feuille est-elle CENSEE rendre `heroes_on_capture_points` dans
le montage du test #225 (tuile TERRITOIRE, sujet SANS trait 2/0xd, pas de regime spawning) ?

REPONSE, LUE AU DECOMPILE -- OUI, et le port l'implemente fidelement :

    IdunBattle.AI.Utilities.CapturePointTileUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext
        x = Fix64(0)
        if (case.position.MainTile == null) yield break         // rien d'emis
        flag = (case.unit == null) ? (case.parent != null)      // `get_IsSpawning` INLINE (case-205)
                                   : HasTrait(case.unit, 0x2) || HasTrait(case.unit, 0xd)
        if (IdunBattle.Entities.TileExtensions$$IsTerritoryTile(case.position.MainTile))
            x += GetUtilityValue(flag ? <summons_dislike_capture_points>
                                      : <heroes_on_capture_points>)

Le defaut n'etait donc NI dans le gate de trait NI dans la table de poids : le test n'atteignait
JAMAIS cette feuille. Il indexait le registre par l'ORDINAL en dur `TILE_LEAVES[24]`, exact a son
ecriture (`883668e6`, 2026-07-29) et PERIME depuis `fe5b9245` (#252) -- la MAJ de build a insere
`AttackTile` en 8 et decale 59 membres de +1, si bien que `CapturePoint` vaut 25 et que 24 designe
desormais `MoltenForm`. `MoltenForm_TilesUtility` gate sur `unit_triggered_abilities` (1221) : elle
rend 0.0 sur n'importe quel `meta`, sans erreur -- exactement la degradation SILENCIEUSE que le
cliquet de `TILE_LEAVES` (#254) empeche cote REGISTRE mais pas cote CONSOMMATEUR.

Ce probe MESURE les quatre faces et ECHOUE si l'une rote :
  0. l'enum du port == la table VERSIONNEE du build courant (nom par nom) ;
  1. `TILE_LEAVES[UtilityType.CapturePoint]` est bien `CapturePointTileUtility`, et l'ancien
     ordinal 24 ne l'est PLUS (la mesure du piege, pas une supposition) ;
  2. table de verite de la feuille = celle du decompile ci-dessus, poids BC reels ;
  3. plus AUCUN consommateur du depot n'indexe `TILE_LEAVES` par un litteral entier.

ASCII only. Offline (aucun runner, aucun RPC).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_REPO = _HERE.parents[1]

from engine import weights as W                                       # noqa: E402
from engine.utilities.tile import (CapturePointTileUtility, TILE_LEAVES,  # noqa: E402
                                   MoltenForm_TilesUtility)
from engine.utilities.utility_type import UtilityType                 # noqa: E402

_ENUM_NAME = "IdunBattle.Configuration.UtilityType"
_OLD_ORDINAL = 24        # ce que valait `CapturePoint` avant `fe5b9245` (#252)


def _load_native_enum() -> dict[str, int]:
    """{NAME: value} de `UtilityType`, lu dans la table VERSIONNEE du build COURANT."""
    from symbols_layout import current_build
    p = _REPO / "data" / "symbols" / current_build() / "frida" / "enums.tsv"
    with p.open(encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols and cols[0] == _ENUM_NAME:
                out: dict[str, int] = {}
                for pair in cols[1].split(","):
                    v, _, n = pair.partition("=")
                    if n and n not in out:
                        out[n] = int(v)
                return out
    raise SystemExit("enum %s absent de %s" % (_ENUM_NAME, p))


def step0_enum_matches_native() -> list[str]:
    """Le port de l'enum est-il aligne sur le build courant ? (protocole #254b : ordinaux LUS)"""
    native = _load_native_enum()
    bad = [(m.name, int(m), native.get(m.name)) for m in UtilityType
           if native.get(m.name) != int(m)]
    print("[0] UtilityType : %d membres portes, %d natifs -- %d divergence(s)"
          % (len(list(UtilityType)), len(native), len(bad)))
    print("    CapturePoint : port=%d natif=%s | MoltenForm : port=%d natif=%s"
          % (int(UtilityType.CapturePoint), native.get("CapturePoint"),
             int(UtilityType.MoltenForm), native.get("MoltenForm")))
    return ["UtilityType.%s : port=%s natif=%s" % b for b in bad]


def step1_registry_identity() -> list[str]:
    """La feuille rendue par le registre est-elle CELLE que son nom annonce ?"""
    errs: list[str] = []
    name, leaf = TILE_LEAVES[UtilityType.CapturePoint]
    print("[1] TILE_LEAVES[UtilityType.CapturePoint=%d] -> %r / %s"
          % (int(UtilityType.CapturePoint), name, type(leaf).__name__))
    if not (name == "CapturePoint" and isinstance(leaf, CapturePointTileUtility)):
        errs.append("TILE_LEAVES[CapturePoint] rend %r / %s" % (name, type(leaf).__name__))
    if leaf.UTILITY_TYPE != int(UtilityType.CapturePoint):
        errs.append("leaf.UTILITY_TYPE=%s != %d" % (leaf.UTILITY_TYPE,
                                                    int(UtilityType.CapturePoint)))
    # La MESURE du piege : l'ancien ordinal designe une AUTRE feuille, muette sur ce `meta`.
    old_name, old_leaf = TILE_LEAVES[_OLD_ORDINAL]
    v = old_leaf.evaluate((0, 0), {"is_territory": True}, {"unit_traits": (), "is_spawning": False},
                          W.load())
    print("[1] ancien ordinal %d -> %r / %s ; evaluate(meta.is_territory=True) = %s"
          % (_OLD_ORDINAL, old_name, type(old_leaf).__name__, v))
    if isinstance(old_leaf, CapturePointTileUtility):
        errs.append("l'ordinal %d designe ENCORE CapturePoint -- ce probe est perime" % _OLD_ORDINAL)
    if not isinstance(old_leaf, MoltenForm_TilesUtility) or v != 0.0:
        errs.append("l'ordinal %d ne reproduit plus le faux 0.0 mesure (%s / %s)"
                    % (_OLD_ORDINAL, type(old_leaf).__name__, v))
    return errs


def step2_truth_table() -> list[str]:
    """Table de verite = branches du decompile, poids BC reels."""
    wt = W.load()
    leaf = TILE_LEAVES[UtilityType.CapturePoint][1]
    heroes = wt.sub("CapturePoint", "heroes_on_capture_points")
    summons = wt.sub("CapturePoint", "summons_dislike_capture_points")
    print("[2] poids BC CapturePoint : heroes=%s summons=%s" % (heroes, summons))
    cases = [
        # (libelle, meta, ctx, attendu)
        ("hors territoire, hero", {}, {"unit_traits": (16, 34), "is_spawning": False}, 0.0),
        ("territoire, hero (le montage #225)", {"is_territory": True},
         {"unit_traits": (16, 34, 1001), "is_spawning": False}, heroes),
        ("territoire, trait 2 Summon", {"is_territory": True},
         {"unit_traits": (2, 16), "is_spawning": False}, summons),
        ("territoire, trait 0xd", {"is_territory": True},
         {"unit_traits": (13,), "is_spawning": False}, summons),
        # `get_IsSpawning` INLINE (case-205) : sujet ABSENT + parent present -> traite comme summon.
        ("territoire, IsSpawning", {"is_territory": True}, {"is_spawning": True}, summons),
        ("hors territoire, IsSpawning", {}, {"is_spawning": True}, 0.0),
    ]
    errs: list[str] = []
    for label, meta, ctx, want in cases:
        got = leaf.evaluate((0, 0), meta, ctx, wt)
        ok = "OK" if got == want else "MISMATCH"
        print("    %-38s -> %-8s attendu %-8s [%s]" % (label, got, want, ok))
        if got != want:
            errs.append("%s : %s != %s" % (label, got, want))
    if heroes == summons:
        errs.append("poids BC identiques (%s) : la feuille ne discrimine rien" % heroes)
    if not (heroes > 0 > summons):
        errs.append("le CHANGEMENT DE SIGNE attendu par #225 n'est plus la (%s / %s)"
                    % (heroes, summons))
    return errs


# Les DEUX formes rencontrees du meme defaut : l'index litteral (ce qui a rendu la mauvaise feuille)
# et la constante-ordinal annotee (`CAPTURE_POINT = 24  # UtilityType.CapturePoint`, la ligne source
# du rouge -- elle nomme le membre mais fige sa valeur, donc elle ment des la renumerotation).
_LITERAL_PATTERNS = (
    ("index litteral de TILE_LEAVES", re.compile(r"TILE_LEAVES(?:\.get)?\(?\s*\[?\s*(\d+)\s*[\],]")),
    ("constante-ordinal UtilityType", re.compile(r"=\s*\d+\s*(?:\)\s*)?#\s*UtilityType")),
)


def step3_no_literal_consumer() -> list[str]:
    """Aucun consommateur du depot ne doit figer un ORDINAL `UtilityType` en dur."""
    hits: list[str] = []
    for p in sorted((_REPO / "scripts" / "python").rglob("*.py")):
        if p.name == Path(__file__).name:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for label, rx in _LITERAL_PATTERNS:
                if rx.search(line):
                    hits.append("%s:%d [%s] %s"
                                % (p.relative_to(_REPO).as_posix(), i, label, line.strip()))
    print("[3] ordinaux UtilityType figes en dur chez les consommateurs : %d" % len(hits))
    for h in hits:
        print("    %s" % h)
    return hits


def step4_live_territory(board: str, seed: str) -> list[str]:
    """LIVE : le co-gate `meta.is_territory` prend-il jamais une valeur qui MORD en bataille ?

    Le test #225 pose `meta = {"is_territory": True}` en JETON. Cette etape mesure ce que la
    bataille rend vraiment : `tileMeta.isTerritory` = `TileComponent+0x2e`, l'octet EXACT que lit
    `IdunBattle.Entities.TileExtensions$$IsTerritoryTile`. Si une tuile territoire existe, la feuille
    est evaluee DESSUS par le chemin de production (`apply_tile_attributes`) ; sinon le jeton est
    atteste comme la SEULE voie, et la feuille declaree inerte en bataille sur ce board.
    """
    import json
    import subprocess
    import uuid
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    from engine.utilities.tile import apply_tile_attributes, runner_tile_leaf_ctx  # noqa: E402
    from engine.entities.pathfinding.board import Board          # noqa: E402
    from engine.runner.components import StatsComponent, UnitComponent  # noqa: E402
    from engine.runner.snapshot import load_state                # noqa: E402

    sid = _resolve_session()
    state = _REPO / "logs" / "runners" / ("probe272-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed,
                        "--state-file", str(state), "--board", board],
                       cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return ["build runner KO : %s" % ((p.stderr or p.stdout or "")[-400:])]
    rid = json.loads(state.read_text())["runnerId"]

    def _r(m, b, t=90):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    errs: list[str] = []
    try:
        tiles = (_r("tileMeta", {"runnerId": rid}, 60).get("tiles") or [])
        terr = {(int(t["col"]), int(t["row"])): bool(t.get("isTerritory"))
                for t in tiles if t.get("col") is not None}
        n_terr = sum(1 for v in terr.values() if v)
        print("[4] runner %s board %s : %d tuiles, isTerritory=%d" % (rid, board, len(tiles), n_terr))
        wt = W.load()
        leaf = TILE_LEAVES[UtilityType.CapturePoint][1]
        heroes = wt.sub("CapturePoint", "heroes_on_capture_points")
        bg = _r("boardGraph", {"runnerId": rid}, 60)
        dv = _r("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = _r("observeBattle", {"runnerId": rid}, 40)
        cs = _r("combatSnapshot", {"runnerId": rid}, 60)
        st = load_state(dv, ob, cs, board=Board(bg["tiles"], adjacency="native_sym"))
        uid = next((i for i, e in st.entities.items()
                    if e.get_component(StatsComponent) is not None
                    and e.get_component(UnitComponent) is not None), None)
        if uid is None:
            return ["aucune unite a StatsComponent dans l'etat charge"]
        lc = dict(runner_tile_leaf_ctx(st, uid))
        lc["is_territory_by_pos"] = terr
        if n_terr:
            pos = next(p for p, v in terr.items() if v)
            meta = apply_tile_attributes({}, pos, lc)
            got = leaf.evaluate(pos, meta, lc, wt)
            print("[4] tuile territoire %s : meta=%s -> %s (attendu %s)" % (pos, meta, got, heroes))
            if got != heroes:
                errs.append("tuile territoire %s : %s != %s" % (pos, got, heroes))
        else:
            pos = next(iter(terr))
            meta = apply_tile_attributes({}, pos, lc)
            got = leaf.evaluate(pos, meta, lc, wt)
            print("[4] AUCUNE tuile territoire sur ce board -- le co-gate ne mord jamais ici : "
                  "meta.is_territory=%s, feuille=%s. Le jeton du test #225 est donc la SEULE voie "
                  "d'exercice, et la feuille reste INERTE en bataille sur ce board."
                  % (meta.get("is_territory"), got))
            if got != 0.0:
                errs.append("hors territoire, la feuille rend %s au lieu de 0.0" % got)
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            print("[4] runner %s dispose" % rid)
        except Exception as exc:                                   # noqa: BLE001
            print("[4] dispose KO : %s" % exc)
        state.unlink(missing_ok=True)
    return errs


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="ajoute l'etape 4 (monte un runner, mesure tileMeta.isTerritory)")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    errs: list[str] = []
    errs += step0_enum_matches_native()
    errs += step1_registry_identity()
    errs += step2_truth_table()
    errs += step3_no_literal_consumer()
    if a.live:
        errs += step4_live_territory(a.board, a.seed)
    print("")
    if errs:
        print("ECHEC #272 -- %d controle(s) rouge(s) :" % len(errs))
        for e in errs:
            print("  - %s" % e)
        return 1
    print("OK #272 -- feuille CapturePoint atteinte par MEMBRE, table de verite conforme au "
          "decompile, aucun ordinal en dur restant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
