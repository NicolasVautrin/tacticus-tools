"""#589-r1 -- L'AVAL de `tilesMovedThisTurn` : les consommateurs, et ce que le passage 4 -> 6
DEPLACE chez chacun.

LE CRITERE, pose AVANT toute methode
------------------------------------
#589 (`#448-r1-r1-r1-r1-r2-r1`) a rebranche `beeline_pathfinder` sur le `ConnectivityComponent` :
le port rendait **4** la ou le natif enregistre **6** pour `tilesMovedThisTurn`. La correction est
validee sur SA face (l'oracle `TeleportStrike`), mais l'AVAL ne l'etait pas. Question binaire, et
elle est **par consommateur** :

    pour CHAQUE lecteur natif de `DSLFormulas$$TilesMovedThisTurn`, un compteur qui passe de
    `n_G` (substrat GEOMETRIE, l'etat d'avant #589) a `n_C` (substrat CANAL) change-t-il son
    RESULTAT ?

Un consommateur dont les deux valeurs donnent le meme resultat est un regime DEGENERE : on ne
conclut RIEN de lui, on NOMME le mecanisme (borne / seuil / saturation).

LE RECENSEMENT NATIF, RE-DERIVE (xrefs de `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn`,
build `rnca9r7q6c`) -- SIX call-sites, QUATRE porteurs
-----------------------------------------------------------------------------------------------
Le nud DSL construit un `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula`, dont
`$$Calculate` rend `ActorStatisticsComponent+0xf0` -- il n'existe aucun autre lecteur de ce champ.

| # | call-site natif | forme lue au decompile | sujet | sensible a n ? |
|---|---|---|---|---|
| 1 | `ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` | `Multiply(ConfigVar(8=extraDmg), TilesMovedThisTurn(sel))` | `DSLSelectors+0x30` = Owner | **LINEAIRE** |
| 2 | `ModifiedExoarmour_ExtraDmgEffect$$GetExtraDamageMultiplier` | `TilesMovedThisTurn(sel)` brut | Owner | **LINEAIRE** |
| 3 | `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` | `AmountIsGreaterThanZero(TilesMovedThisTurn(sel))` | Owner | seuil **> 0** |
| 4 | `EmpyricAmbushEffect$$IsValidAttackForBuff` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Direct(GetNumberConstant(0x51)))` | `DSLSelectors+0x48` = Caster de l'attaque | seuil **= `EmpyricAmbush.constants.movement`** |
| 5 | `MastersOfManoeuvreAbility$$CreateTrigger` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Get(GetNumberConstant(0x88)))` | `DSLSelectors+0x40`, sujet du `On(0x4)` | seuil **= `MastersOfManoeuvre.constants.tilesTraversed`** |
| 6 | `SmashaEadAbility$$CreateTrigger` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Direct(2))` | `DSLSelectors+0x30` = Owner | seuil **= 2**, LITTERAL |

`0x51` / `0x88` sont resolus par `IdunBattle.Configuration.AbilityConstantType` du dump d'enums
(`81 = movement`, `136 = tilesTraversed`) -- ce probe les RE-LIT du gameconfig, il ne les recopie
pas.

LA BORNE QUI DECIDE DES SEUILS, et elle se DERIVE
-------------------------------------------------
`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` ne recoud par une beeline QUE
`if (GetDistance(last, next) > 1)`. Le sous-chemin beeline entre deux nuds distants de `d >= 2`
compte au moins `d >= 2` aretes -- dans **les deux** substrats. Donc :

    des que le rebranchement peut mordre (= une beeline est appelee), `n_G >= 2` ET `n_C >= 2`

et comme `N <= C <= G` (mesure #584) donne `n_G <= n_C`, tout seuil `K <= 2` est **DEJA FRANCHI
par le substrat d'AVANT** : le rebranchement ne peut pas le faire basculer. Ca sature les
call-sites 3, 5 et 6. Le cran `BORNE` MESURE cette derivation au lieu de la supposer.

CE QUE LE PORT CONSOMME, RE-DERIVE DU CODE (cran `INV`)
-------------------------------------------------------
Cote port, le canal `att_ctx["tiles_moved_this_turn"]` a **un seul** lecteur de degat
(`ModifiedExoarmourExtraDmgEffect`, `effects/loki/extra_damage.py`) ; les trois autres porteurs
natifs n'ont **aucun** trigger porte. Le cran `INV` le RE-DERIVE et rougit si ca change -- entrer
un de ces triggers au registre rouvre la question de l'aval.

Usage (session warmee) :
    python probe_589r1_tiles_moved_consumers_live.py --only INV        # offline, aucun runner
    python probe_589r1_tiles_moved_consumers_live.py --only BORNE      # 1 build (C1_74)
    python probe_589r1_tiles_moved_consumers_live.py --only WALK       # contraste Walk / TS
    python probe_589r1_tiles_moved_consumers_live.py --only EXO        # greffe + degat
    python probe_589r1_tiles_moved_consumers_live.py --only FLY        # item 2 : Fly pur
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

# Le board a `Bridge` : le SEUL des trois de #584/#589 ou `G \ C != 0`, donc le seul ou le
# rebranchement peut mordre. `MC1_67` (G\C = 0) et `C6_25` (les trois vues coincident) sont des
# temoins DEGENERES pour cette question -- les jouer seuls ne prouverait rien.
BOARD_BRIDGE = "C1_74"

# Les quatre porteurs natifs, et ce que `unit_map` en dit. Le sujet du selecteur n'est PAS toujours
# le porteur : #4 et #5 lisent le compteur d'une unite TIERCE.
PORTEURS = {
    "ModifiedExoarmour": "votanChampion",
    "EmpyricAmbush": "eldarLhykhis",
    "MastersOfManoeuvre": "darkaStormSpeeder",
    "SmashaEad": "orksNob",
}

# Ce que le cran INV exige du PORT. Cle = ability native ; valeur = ce qui doit exister (ou non)
# cote port. Un changement ici rouvre la question de l'aval, et c'est exactement ce qu'on veut voir.
#
# ⚠ DEUX ENTREES ONT ETE CORRIGEES PARCE QU'ELLES ETAIENT PERIMEES, pas parce qu'elles genaient :
#   * `EmpyricAmbush` -- trigger de RE-ARMEMENT porte depuis #589-r1-r1-r1-r1
#     (`EmpyricAmbushResetAbility`, 1555), et son SEUIL `movement` confronte au natif par
#     #589-r1-r1 ; le rouge qu'il produisait ici etait donc en retard sur sa propre fermeture.
#   * `MastersOfManoeuvre` -- trigger porte depuis #999-r1 (`MastersOfManoeuvrePlaceOnMove`),
#     seuil RECONFRONTE par #589-r2 : 5253 couples divergents sur `C1_74` + `C3_14`, **0 bascule**
#     du gate porte, temoin non-nul a 1328. Cf. `probe_589r2_masters_of_manoeuvre_aval.py`.
# Ce qui reste ACCUSE (le cran plus bas) est le seul porteur a seuil dont le trigger n'existe pas.
PORT_ATTENDU = {
    # ⚠ La colonne mesure « un TRIGGER porte sous `triggers/` », pas « l'ability est portee ».
    # `ModifiedExoarmour` est porte cote EFFET (`effects/loki/extra_damage.py`, le consommateur
    # LINEAIRE) et n'a aucun trigger : `False` est le verdict JUSTE. La regex d'avant rendait
    # `True` sur trois occurrences de PROSE (`maugetar.py:48`, `prophetic_sentinel.py:72`,
    # `wireweave_net.py:36`) -- dont la ligne meme qui avait fait rougir `master`.
    "ModifiedExoarmour": "effet porte (LINEAIRE), pas de trigger",
    "EmpyricAmbush": "porte (trigger de re-armement + seuil confronte, #589-r1-r1)",
    "MastersOfManoeuvre": "porte (trigger #999-r1, seuil SATURE et reconfronte, #589-r2)",
    "SmashaEad": "effet porte, TRIGGER non porte",
}


# --------------------------------------------------------------------------- cran INV (offline)
def _seuils_du_gameconfig() -> dict:
    """Les seuils, RE-LUS du gameconfig courant (jamais recopies du decompile).

    `IdunBattle.Configuration.AbilityConstantType` : `0x51 = 81 = movement`,
    `0x88 = 136 = tilesTraversed`. `SmashaEad` n'en a pas -- son seuil est le litteral `Direct(2)`
    de `SmashaEadAbility$$CreateTrigger`."""
    import gameconfig as GC
    out = {}
    for ab, key in (("EmpyricAmbush", "movement"), ("MastersOfManoeuvre", "tilesTraversed")):
        cfg = GC.ability(ab) or {}
        c = (cfg.get("constants") or {})
        out[ab] = None if key not in c else int(c[key])
    out["SmashaEad"] = 2                 # `DSLFormulas$$Direct(2)`, litteral du decompile
    out["ModifiedExoarmour"] = 0         # `AmountIsGreaterThanZero` -> seuil strict > 0
    return out


def _tokens_executables(source: str) -> set:
    """Les noms en position EXECUTABLE : identifiants, attributs, noms de classe/fonction, et les
    chaines qui ne sont PAS des docstrings. Cf. le bloc de commentaire de `_port_consumers`."""
    import ast

    arbre = ast.parse(source)
    docstrings = set()
    for n in ast.walk(arbre):
        corps = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and corps and isinstance(corps[0], ast.Expr) \
                and isinstance(corps[0].value, ast.Constant) \
                and isinstance(corps[0].value.value, str):
            docstrings.add(id(corps[0].value))
    out = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            out.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", n.value))
    return out


def _port_consumers() -> dict:
    """Ce que le PORT consomme, DERIVE du code source (jamais d'une liste ecrite a la main).

    Deux mesures independantes :
      * les appelants de `engine.entities.effects.base.tiles_moved_this_turn` (le foyer de
        lecture cote COMBAT) ;
      * la presence d'un TRIGGER porte pour chacun des quatre porteurs natifs.
    """
    eng = PYDIR / "engine"
    lecteurs, triggers = set(), {}
    pat_call = re.compile(r"(?<![\w.])tiles_moved_this_turn\s*\(")
    for p in eng.rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(PYDIR).as_posix()
        for i, line in enumerate(txt.splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"') or s.startswith("'"):
                continue
            if pat_call.search(line) and "def tiles_moved_this_turn" not in line:
                lecteurs.add("%s:%d" % (rel, i))
    trig_dir = eng / "runner" / "operations" / "triggers"
    # ⚠ AST, PAS une regex sur le texte brut. Le meme cran ecrit en `re.search` a fait rougir
    # `master` pour UNE occurrence dans un COMMENTAIRE de `triggers/loki/maugetar.py` qui enumere
    # les abilities voisines -- aucun trigger n'etait porte. Un detecteur qui lit la PROSE accuse
    # le progres documentaire et se fait desarmer par le premier qui veut faire taire le rouge.
    # Les COMMENTAIRES n'entrent jamais dans un AST (exclus gratuitement) ; les DOCSTRINGS y sont,
    # on les retire ; les autres chaines RESTENT, parce qu'une cle de registre (`{"X": [...]}`) est
    # precisement ce qu'on veut voir.
    tokens = set()
    for p in trig_dir.rglob("*.py"):
        tokens |= _tokens_executables(p.read_text(encoding="utf-8", errors="replace"))
    if len(tokens) <= 100:
        print("      ECART: detecteur muet (%d token(s)) -- ce cran ne mesure plus rien"
              % len(tokens))
    for ab in PORTEURS:
        triggers[ab] = ab in tokens
    return {"lecteurs": sorted(lecteurs), "triggers": triggers}


def run_inv() -> int:
    print("== INV -- recensement DERIVE des consommateurs (offline)")
    bad = 0
    seuils = _seuils_du_gameconfig()
    print("\n  SEUILS relus du gameconfig courant :")
    for ab, v in sorted(seuils.items()):
        src = ("litteral `Direct(2)`" if ab == "SmashaEad"
               else "`AmountIsGreaterThanZero`" if ab == "ModifiedExoarmour"
               else "constants")
        print("    %-20s seuil=%s   (%s)" % (ab, v, src))
        if v is None:
            print("      ECART: constante ABSENTE du gameconfig -- le seuil n'est pas mesure")
            bad += 1
    # LA BORNE : tout seuil <= 2 est deja franchi par le substrat d'AVANT (cf. en-tete).
    satures = sorted(a for a, v in seuils.items() if v is not None and v <= 2)
    ouverts = sorted(a for a, v in seuils.items() if v is not None and v > 2)
    print("\n  BORNE `n >= 2 des que la beeline mord` :")
    print("    SATURES (seuil <= 2, franchi avant comme apres) : %s" % ", ".join(satures))
    print("    seuil > 2, donc FRANCHISSABLE par le rebranchement : %s"
          % (", ".join(ouverts) or "(aucun)"))
    if not ouverts:
        print("      NB: aucun seuil ouvert -- le cran BORNE devient un TEMOIN, pas une preuve")

    pc = _port_consumers()
    print("\n  PORT -- lecteurs du canal `tiles_moved_this_turn(att_ctx)` :")
    for l in pc["lecteurs"]:
        print("    %s" % l)
    print("  PORT -- trigger porte, par porteur natif :")
    for ab, present in sorted(pc["triggers"].items()):
        print("    %-20s trigger porte=%s   attendu: %s" % (ab, present, PORT_ATTENDU[ab]))
    # Le cran de NON-REGRESSION : le porteur a SEUIL encore non exerce n'a aucun trigger porte.
    # S'il en gagne un, l'aval doit etre reconfronte -- ce probe doit alors rougir pour le dire.
    for ab in ("SmashaEad",):
        if pc["triggers"][ab]:
            print("      ECART: `%s` a maintenant un trigger porte -- l'aval de #589 doit etre "
                  "RECONFRONTE pour ce consommateur" % ab)
            bad += 1
    # ... et la NON-VACUITE du cran : les deux sortis de la liste ci-dessus (#589-r1-r1, #589-r2)
    # en sont sortis PARCE QU'ils sont portes. S'ils cessaient de l'etre, les gardes qui les ont
    # remplaces ne mesureraient plus rien, et ce probe passerait pour vert sans le dire.
    for ab in ("EmpyricAmbush", "MastersOfManoeuvre"):
        if not pc["triggers"][ab]:
            print("      ECART: `%s` n'a PLUS de trigger porte -- sa sortie de la liste accusee "
                  "reposait sur ce fait ; le garde qui l'a remplace est desormais VIDE" % ab)
            bad += 1
    if not pc["lecteurs"]:
        print("      ECART: AUCUN lecteur du canal cote port -- le recensement ne mesure rien")
        bad += 1
    print("\n  VERDICT INV: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return bad


# --------------------------------------------------------------------------- infra live
def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str, units, foes, seed_bc=None):
    import subprocess
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p589r1_state_%s.json" % tag)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", ",".join(units), "--a-units", ",".join(foes or []),
           "--no-ai", "--state-file", str(state_file)]
    if seed_bc:
        cmd += ["--seed-bc", str(seed_bc)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if state_file.exists():
        return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
    sys.stdout.write(((p.stdout or "") + (p.stderr or ""))[-2000:])
    raise SystemExit("build KO (%s)" % tag)


def _turn_counter(ast: dict, uid: int):
    """`tilesMovedThisTurn`, ou `None` = NON MESURE (jamais 0 par defaut)."""
    for u in ((ast or {}).get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(uid):
            v = u.get("tilesMovedThisTurn")
            return None if v is None else int(v)
    return None


def _counters(ast: dict) -> dict:
    return {int(u["entityId"]): u.get("tilesMovedThisTurn")
            for u in ((ast or {}).get("units") or []) if u.get("entityId") is not None}


def _predire(Board, state, uid, src, dst, substrat):
    """`_num_tiles_moved` du port, sous un substrat de voisinage IMPOSE.

    `substrat` in {"C" (canal, l'etat livre), "G" (geometrie, l'etat d'AVANT #589), "N" (le champ
    ampute)}. C'est `Board.base_add_neighbours` que la beeline consomme -- `fly_pathfinder`, lui,
    lit `neighbours_geometric` EN DUR (override natif `FlyPathfinder$$AddNeighbours`), donc il
    n'est PAS pilote par ce levier, et c'est fidele."""
    from engine.runner.operations.movement import _num_tiles_moved
    orig = Board.base_add_neighbours
    try:
        if substrat == "G":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_geometric(tid))
        elif substrat == "N":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_native(tid))
        return _num_tiles_moved(state, int(uid), src, dst)
    finally:
        Board.base_add_neighbours = orig


# --------------------------------------------------------------------------- cran SCAN
def _bg_path(board_id: str) -> pathlib.Path:
    return LOGSDIR / ("p589r1_bg_%s.json" % board_id)


def _get_board_graph(sid, rpc, board_id: str, seed: int, reuse: bool):
    """Le `boardGraph` du board, capte UNE fois puis relu. Le cache vit dans `logs/` (sortie du
    run, jamais `data/`) et n'est PAS une entree : il porte le board ET le build."""
    p = _bg_path(board_id)
    if reuse and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    rid, state_file = _build(board_id, seed, "scan_%s" % board_id,
                             ["blackHaarken", "bloodIntercessor", "necroWarden"], ["necroWarden"])
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
        p.write_text(json.dumps(bg), encoding="utf-8")
        return bg
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)


def _beeline_len(bd, neighbours, a, b):
    from engine.entities.pathfinding import base_pathfinder as BP
    from engine.entities.pathfinding import beeline_pathfinder as BL
    p = BP.find_path(bd, a, b, edge=BL.is_valid_path_node, neighbours=neighbours,
                     weight_cost=lambda tid: BL.WEIGHT_BASE,
                     is_valid_final_tile=lambda tid: True)
    return None if p is None else len(p) - 1


def _connected_len(bd, Board, ptype: int, a: int, b: int, substrat: str):
    """`GetNumTilesMoved(GetConnectedPathTo(...))` pour un `ptype` donne, substrat impose.

    C'est l'etage COMPLET -- `pathfinders.find_path` PUIS la re-densification. Le mesurer sur la
    beeline nue suffirait pour `TeleportStrike` (son `FindPath` rend `[from, to]`), PAS pour le
    vol pur, dont `FlyPathfinder$$FindPath` rend des WAYPOINTS."""
    from engine.entities.pathfinding import pathfinders as _pf
    from engine.services.movement_query import get_connected_path_to, get_num_tiles_moved
    orig = Board.base_add_neighbours
    try:
        if substrat == "G":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_geometric(tid))
        elif substrat == "N":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_native(tid))
        path = _pf.find_path(bd, ptype, a, b)
        return get_num_tiles_moved(get_connected_path_to(bd, a, b, path))
    finally:
        Board.base_add_neighbours = orig


def run_scan(sid, rpc, board_id: str, seed: int, reuse: bool, verbose: bool) -> int:
    """LE GISEMENT, chiffre AVANT tout montage -- et la BORNE des seuils, MESUREE.

    Trois questions, dans cet ordre :
      S1  la BORNE `n >= 2 des que la beeline mord` tient-elle sur ce board ?
      S2  pour quels REGIMES (`Fly` = 3, `TeleportStrike` = 7, `Walk` = 0) le passage
          GEOMETRIE -> CANAL change-t-il `GetNumTilesMoved` ? et sur combien de couples ?
      S3  un seuil `K` peut-il BASCULER, c'est-a-dire existe-t-il un couple `n_G < K <= n_C` ?
    """
    from engine.entities.pathfinding.board import Board
    bg = _get_board_graph(sid, rpc, board_id, seed, reuse)
    bd = Board(bg["tiles"], adjacency="native_sym")
    if not bd.has_connectivity_channel():
        print("   CANAL ABSENT du boardGraph -- NON MESURE")
        return 1
    ids = sorted(bd.by_id)
    print("== SCAN  board=%s  %d tuiles" % (board_id, len(ids)))
    bad = 0

    # --- S1 : la BORNE. Sur tout couple ou la beeline est APPELEE (d_hex > 1), la longueur du
    #     chemin recousu vaut au moins 2 dans les DEUX substrats. C'est ce qui sature les seuils.
    import hexgeo
    mini_g = mini_c = None
    viol = []
    for a in ids:
        for b in ids:
            if a == b or hexgeo.distance(bd.coord(a), bd.coord(b)) <= 1:
                continue
            lg = _beeline_len(bd, bd.neighbours_geometric, a, b)
            lc = _beeline_len(bd, lambda t: bd.neighbours_connectivity(t) or [], a, b)
            if lg is None or lc is None:
                continue
            mini_g = lg if mini_g is None else min(mini_g, lg)
            mini_c = lc if mini_c is None else min(mini_c, lc)
            if lg < 2 or lc < 2:
                viol.append((bd.coord(a), bd.coord(b), lg, lc))
    print("  [S1] BORNE : min(beeline) sur les couples a d_hex > 1 : G=%s  C=%s  (attendu >= 2)"
          % (mini_g, mini_c))
    if viol:
        print("       ECART: %d couple(s) sous la borne -- la saturation des seuils <= 2 TOMBE"
              % len(viol))
        for v in viol[:6]:
            print("         %s -> %s  G=%d C=%d" % v)
        bad += 1

    # --- S2 / S3 : une seule passe par regime, deux lectures. S2 = ce qui BOUGE ; S3 = ce qui
    #     BASCULE un seuil. Les deux sont differents : un ecart de +2 sur `n = 4 -> 6` bouge la
    #     magnitude LINEAIRE et ne bascule AUCUN seuil <= 4.
    regimes = {0: "Walk", 3: "Fly", 6: "TeleportStrike(Walk)", 7: "TeleportStrike(+Fly)"}
    seuils = _seuils_du_gameconfig()
    bascule_total = 0
    for pt, nom in sorted(regimes.items()):
        chg, tot, ecarts = 0, 0, {}
        exemples = []
        bascule = {a: 0 for a in seuils}
        for a in ids:
            for b in ids:
                if a == b:
                    continue
                ng = _connected_len(bd, Board, pt, a, b, "G")
                nc = _connected_len(bd, Board, pt, a, b, "C")
                tot += 1
                if ng != nc:
                    chg += 1
                    ecarts[nc - ng] = ecarts.get(nc - ng, 0) + 1
                    if len(exemples) < 8:
                        exemples.append((bd.coord(a), bd.coord(b), ng, nc))
                for ab, K in seuils.items():
                    if K is not None and ng < K <= nc:
                        bascule[ab] += 1
        print("  [S2] ptype=%-2d %-22s : %d couple(s) sur %d changent  ecarts %s"
              % (pt, nom, chg, tot, ", ".join("%+d:%d" % kv for kv in sorted(ecarts.items()))
                 or "-"))
        for ex in (exemples if verbose else exemples[:3]):
            print("         %s -> %s : G=%s C=%s" % ex)
        bas = {a: n for a, n in bascule.items() if n}
        bascule_total += sum(bas.values())
        print("  [S3] ptype=%-2d seuils qui BASCULENT (n_G < K <= n_C) : %s"
              % (pt, ", ".join("%s(K=%s):%d" % (a, seuils[a], n) for a, n in sorted(bas.items()))
                 or "AUCUN"))
    if bascule_total == 0:
        print("  [S3] AUCUN seuil ne bascule sur %s, aucun regime -- les consommateurs a SEUIL "
              "sont SATURES par la borne S1, pas par chance" % board_id)
    return bad


# --------------------------------------------------------------------------- cran TILES
def run_tiles(sid, rpc, unit: str, fillers, foes, board_id: str, seed: int, max_turns: int,
              verbose: bool, inject: bool = False) -> int:
    """Le compteur natif, confronte au port sous les TROIS substrats, pour UN porteur donne.

    Le porteur est le parametre : c'est ce qui rend le cran utilisable pour les trois REGIMES de
    `MovementQuery$$GetPathfinderTypeForUnit` -- `Walk` (0), `Fly` (3) et un type DECORE
    (`TeleportStrike` -> 7). Le regime n'est PAS suppose : il est RE-DERIVE de l'etat porte et
    imprime, parce que c'est lui qui decide si la beeline est seulement APPELEE."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent
    from engine.services.movement_query import get_pathfinder_type_for_unit, unit_has_effect_fn
    from engine.runner.components import StatsComponent
    import probe_448_r1_r1_r1_flying_movement_steps as P

    bcp = None
    if inject:
        import catalog_inject as CI
        bcp = CI.write_augmented_seed_bc(LOGSDIR / ("bc_589r1_%s.json" % unit), [unit])
        bcp = bcp[0] if isinstance(bcp, tuple) else bcp
        print("   catalogue augmente : %s" % bcp)
    rid, state_file = _build(board_id, seed, "tiles_%s" % unit, [unit] + list(fillers), foes,
                             seed_bc=bcp)
    print("== TILES  unit=%s board=%s seed=%d runner=%s" % (unit, board_id, seed, rid))
    accord_c = accord_g = joues = disc_tot = approches = 0
    vus: set = set()
    regimes: set = set()
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 120)
        bd = Board(bg["tiles"], adjacency="native_sym")
        if not bd.has_connectivity_channel():
            print("   CANAL ABSENT du boardGraph -- NON MESURE (rien n'est interpretable)")
            return 1
        for turn in range(max_turns):
            state, dv, _ob = P._port_state(sid, rpc, rid, bd)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            carriers = P._carriers(dv, [unit])
            cand = [u for u in to_act if u in carriers]
            if not cand:
                if not to_act:
                    print("   t%d : toActivate vide -> fin" % turn)
                    break
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            uid = cand[0]
            e = state.get_entity(int(uid))
            pc = e.get_component(PositionComponent)
            src = (pc.col, pc.row)
            sc = e.get_component(StatsComponent)
            traits = getattr(sc.ctx, "traits", None) if sc is not None else None
            ptype = get_pathfinder_type_for_unit(unit_has_effect_fn(state, int(uid)), traits or [])
            regimes.add(ptype)
            legal = P._legal_moves(sid, rpc, rid, uid)
            disc, plats = [], []
            for d in legal:
                dst = (int(d[0]), int(d[1]))
                if dst == src:
                    continue
                # `GetConnectedPathTo` ne recoud QUE `if (GetDistance(last, next) > 1)`. Un couple
                # a distance 1 n'appelle JAMAIS la beeline : il ne discrimine RIEN du substrat.
                if hexgeo.distance(src, dst) <= 1:
                    continue
                nc = _predire(Board, state, uid, src, dst, "C")
                ng = _predire(Board, state, uid, src, dst, "G")
                nn = _predire(Board, state, uid, src, dst, "N")
                if (src, dst) in vus:
                    continue
                # ⚠ LE DISCRIMINANT EST `nc != ng`, PAS `len({nc,ng,nn}) > 1`. Le gisement de ce
                # cran est le REBRANCHEMENT (G -> C) ; un couple ou seul `N` differe ne tranche
                # que le vieux champ ampute, deja ferme par #584. Mesure vecue : sur `C1_74` les
                # couples `N != C` sont bien plus nombreux (58 aretes contre 16), donc un tri qui
                # les melange NOIE le cas utile -- 5 mesures, 0 couple `G != C`, et une conclusion
                # « route Fly inerte » qui aurait ete FAUSSE (le SCAN en compte 106 sur 3906).
                (disc if nc != ng else plats).append(
                    ((abs(nc - ng), abs(nc - nn)), dst, ng, nc, nn))
            disc.sort(reverse=True)
            plats = [x for x in plats if x[3] >= 2]
            plats.sort(reverse=True)
            disc_tot += len(disc)
            print("   t%d u%s src=%s ptype=%d : %d legale(s), %d DISCRIMINANTE(s) (G!=C) inedite(s)"
                  % (turn, uid, src, ptype, len(legal), len(disc)))
            # Un TEMOIN une mesure sur deux : sans lui on ne mesure que le regime qui CHANGE, et
            # un port casse hors de ce regime passerait inapercu.
            if disc and plats and joues and joues % 2 == 0:
                disc, temoin = plats, True
            else:
                temoin = False
            # Un porteur en regime `Walk` n'a JAMAIS de couple `G != C` (mesure SCAN : 0/3906) --
            # sans cette porte, le cran rendrait `joues == 0` et se lirait « NON CONFRONTE » alors
            # que l'inertie est justement ce qu'il doit ETABLIR. Apres deux approches steriles, on
            # joue un TEMOIN : le natif doit y coller aux trois substrats.
            if not disc and plats and approches >= 2:
                disc, temoin = plats, True
            if not disc:
                approches += 1
                br = [t["id"] for t in bg["tiles"] if t.get("tileDefId") == "Bridge"]
                if br and legal:
                    tgt = bd.coord(br[0])
                    step = min(legal, key=lambda d: hexgeo.distance((d[0], d[1]), tgt))
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": int(uid),
                        "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                    print("      APPROCHE -> %s (Bridge en %s)" % (step, tgt))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            _gap, dst, ng, nc, nn = disc[0]
            vus.add((src, dst))
            b_all = _counters(rpc(sid, "actorStats", {"runnerId": rid}, 60))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(uid),
                "to": {"col": dst[0], "row": dst[1]}}}, 120)
            a_all = _counters(rpc(sid, "actorStats", {"runnerId": rid}, 60))
            before, after = b_all.get(int(uid)), a_all.get(int(uid))
            reset = any(k != int(uid) and a_all.get(k) is not None and b_all.get(k) is not None
                        and a_all[k] < b_all[k] for k in b_all)
            nat = None if (before is None or after is None) else after - before
            if nat == 0 and dst != src:
                reset = True                       # `ResetThisTurn` sous nos pieds, pas une mesure
            if reset or nat is None:
                print("      %s -> %s : NON MESURE (ResetThisTurn=%s, capteur=%s/%s)"
                      % (src, dst, reset, before, after))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            joues += 1
            accord_c += 1 if nat == nc else 0
            accord_g += 1 if nat == ng else 0
            colle = [n for n, v in (("G", ng), ("C", nc), ("N", nn)) if nat == v]
            verdict = ("TEMOIN (G==C==N)" if len({ng, nc, nn}) == 1 else
                       "NI L'UNE NI L'AUTRE" if not colle else
                       {"G": "GEOMETRIE", "C": "CANAL", "N": "CHAMP AMPUTE"}[colle[0]]
                       if len(colle) == 1 else "AMBIGU (%s)" % "+".join(colle))
            print("      %s -> %s : NATIF=%d  port G=%d C=%d N=%d  -> %s%s"
                  % (src, dst, nat, ng, nc, nn, verdict, "  [temoin]" if temoin else ""))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)
    print("   -> TILES %s : %d mesure(s) ; accord CANAL %d, accord GEOMETRIE %d ; "
          "regimes ptype vus %s" % (unit, joues, accord_c, accord_g, sorted(regimes)))
    if joues == 0:
        print("   AUCUNE mesure -- NON CONFRONTE")
        return 1
    if disc_tot == 0:
        print("   REGIME DEGENERE : aucun couple ou les substrats divergent. Ca NE DIT PAS que "
              "le port est juste -- ca dit que ce porteur ne peut pas discriminer ici.")
    return 0 if accord_c == joues else (joues - accord_c)


# --------------------------------------------------------------------------- cran EXO
def run_exo(sid, rpc, board_id: str, seed: int, max_turns: int, graft: bool, verbose: bool) -> int:
    """L'AVAL, MESURE : le degat natif depend-il de `tilesMovedThisTurn`, et de combien ?

    Le seul consommateur LINEAIRE (`ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` =
    `Multiply(ConfigVar(extraDmg), TilesMovedThisTurn(Owner))`) a pour sujet le PORTEUR, et son
    unique porteur `votanChampion` est un MARCHEUR : son compteur ne bouge donc jamais avec #589
    (cran SCAN : `Walk` = 0 couple sur 3906). Pour MESURER l'aval au lieu de le supposer, on
    GREFFE le passif sur un porteur qui, lui, EST dans le regime -- `blackHaarken` (trait
    `Flying`, arme MELEE portee 0, 4 coups), recette `case-92` SS5bis.

    ⚠ CE QUE LA GREFFE NE COUVRE PAS : les stats/traits/armes du VRAI porteur. Elle est legitime
    ICI parce que le natif est l'ORACLE et voit exactement la meme unite que le port -- on ne
    transpose aucun chiffre vers `votanChampion`, on etablit la SENSIBILITE de la chaine.

    Le contre-bras `--no-graft` est OBLIGATOIRE : sans lui, une variation de degat imputable a
    autre chose (charge, %-list de tuile, trait) s'attribuerait au compteur."""
    import hexgeo
    import catalog_inject as CI
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent, StatsComponent
    from engine.services.movement_query import get_pathfinder_type_for_unit, unit_has_effect_fn
    import probe_448_r1_r1_r1_flying_movement_steps as P

    unit, foe = "blackHaarken", "necroWarden"
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    bcp = None
    if graft:
        bcp, reports = CI.write_grafted_seed_bc(
            LOGSDIR / "bc_589r1_exo.json", ["%s:ModifiedExoarmour" % unit], kind="passive")
        print("   greffe : %s" % json.dumps(reports))
    rid, state_file = _build(board_id, seed, "exo_%s" % ("g" if graft else "n"),
                             [unit, foe], [foe], seed_bc=bcp)
    print("== EXO  unit=%s greffe=%s board=%s seed=%d runner=%s"
          % (unit, graft, board_id, seed, rid))
    par_n = {}            # n natif -> (min, max) de `aiPredict` APRES le move
    disc_vus = []
    vues_dist: set = set()
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 120)
        bd = Board(bg["tiles"], adjacency="native_sym")
        if not bd.has_connectivity_channel():
            print("   CANAL ABSENT -- NON MESURE")
            return 1
        approches = 0
        # L'ANCRE : un voisin d'un `Bridge`. C'est la seule zone du board ou `G \ C != 0` (mesure
        # #584 : les 16 aretes dirigees de `C1_74` sont TOUTES incidentes aux deux ponts), donc la
        # seule ou le rebranchement peut deplacer `n` -- et donc le degat.
        # L'ancre est un voisin GEOMETRIQUE du pont qui n'est PAS un voisin de CONNECTIVITE :
        # c'est de l'autre cote du raccourci. Poser la cible SUR le pont ne sert a rien -- ses
        # seuls voisins de connectivite sont ses deux voisins d'axe, donc tout strike y arrive
        # par le chemin que les deux substrats partagent (mesure vecue : 4 valeurs de `n`, zero
        # couple discriminant).
        ponts = [t["id"] for t in bg["tiles"] if t.get("tileDefId") == "Bridge"]
        ancre = None
        for p_id in ponts:
            conn = set(bd.neighbours_connectivity(p_id) or [])
            derriere = [v for v in bd.neighbours_geometric(p_id) if v not in conn]
            if derriere:
                ancre = bd.coord(derriere[0])
                break
        place_fait = False
        for turn in range(max_turns):
            state, dv, ob = P._port_state(sid, rpc, rid, bd)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            carriers = P._carriers(dv, [unit])
            cand = [u for u in to_act if u in carriers]
            if not cand:
                if not to_act:
                    print("   t%d : toActivate vide -> fin" % turn)
                    break
                # TOUR ADVERSE (`--no-ai` : il ne se joue pas tout seul). On s'en sert pour
                # AMENER LA CIBLE au bord du pont : sans ca le porteur ne peut jamais finir
                # ADJACENT sur un couple discriminant, et on mesurerait la pente sans jamais
                # mesurer l'ECART qu'elle chiffre. DEPLACER pour construire la configuration,
                # jamais « bloque par la geometrie de spawn ».
                if not place_fait and ancre is not None:
                    mv = P._legal_moves(sid, rpc, rid, to_act[0])
                    if mv:
                        step = min(mv, key=lambda d: hexgeo.distance((d[0], d[1]), ancre))
                        rpc(sid, "applyAction", {"runnerId": rid, "action": {
                            "kind": "move", "unitId": int(to_act[0]),
                            "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                        print("   t%d : CIBLE u%s -> %s (ancre %s)" % (turn, to_act[0], step,
                                                                       ancre))
                        if tuple(step) == tuple(ancre):
                            place_fait = True
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            uid = cand[0]
            # La CIBLE : un ennemi VIVANT, fixe d'un tour a l'autre (sinon la comparaison des
            # degats melangerait deux armures).
            foes = [int(u["id"]) for u in (dv.get("units") or [])
                    if u.get("id") is not None and u.get("team") != dv.get("team")
                    and u.get("alive")]
            if not foes:
                print("   t%d : aucune cible vivante -> fin" % turn)
                break
            tgt = min(foes)
            e = state.get_entity(int(uid))
            pc = e.get_component(PositionComponent)
            src = (pc.col, pc.row)
            sc = e.get_component(StatsComponent)
            traits = getattr(sc.ctx, "traits", None) if sc is not None else None
            ptype = get_pathfinder_type_for_unit(unit_has_effect_fn(state, int(uid)), traits or [])
            te = state.get_entity(int(tgt))
            tpc = te.get_component(PositionComponent) if te is not None else None
            tpos = (tpc.col, tpc.row) if tpc is not None else None
            legal = P._legal_moves(sid, rpc, rid, uid)
            tid_cible = bd.id_at(*tpos) if tpos else None
            vois_cible = ([bd.coord(v) for v in bd.neighbours_native(tid_cible)]
                          if tid_cible is not None else [])
            # DEUX PHASES, alternees, et c'est le montage qui les impose :
            #  * STRIKE  -- finir ADJACENT a la cible, sinon `aiPredict` rend `pred: null`
            #               (`dictCount = 0` : le natif ne prevoit rien hors de portee). C'est LA
            #               phase qui mesure.
            #  * REPOSER -- s'eloigner, pour que le STRIKE suivant parte d'une distance DIFFERENTE
            #               et rende une valeur de `n` INEDITE. Sans elle le porteur fait un
            #               aller-retour entre deux tuiles et rend N fois le meme `n` : mesure
            #               vecue, 6 tours, une seule valeur (n = 4) et aucune pente.
            strike = []
            repos = []
            for d in legal:
                dst = (int(d[0]), int(d[1]))
                if dst == src or hexgeo.distance(src, dst) <= 1:
                    continue
                nc = _predire(Board, state, uid, src, dst, "C")
                ng = _predire(Board, state, uid, src, dst, "G")
                # ⚠ L'ADJACENCE DE JEU N'EST PAS `hexgeo.distance <= 1`. `MovementUtil$$AreTilesAdjacent`
                # vaut `(|dElev| < 2) & IsNeighbour(a, b)`, c'est-a-dire exactement le champ
                # `neighbours_native` (connectivite INTERSECTE la porte d'elevation, #589 SS14.2).
                # Mesure vecue : depuis `(2,4)`, `hexgeo` donne `d = 1` vers `(1,5)` et le natif
                # rend `pred: null` -- la tuile n'est PAS adjacente pour lui.
                tid_t = bd.id_at(*tpos) if tpos else None
                tid_d = bd.id_at(*dst)
                adj = (tid_t is not None and tid_d is not None
                       and tid_d in set(bd.neighbours_native(tid_t)))
                if adj:
                    # PRIORITE, et elle decoule du PIEGE documente plus bas (le %-list de tuile) :
                    #   3  le couple DISCRIMINANT (`n_G != n_C`) dont l'AUTRE valeur est deja
                    #      mesuree SUR CETTE TUILE -> l'ecart d'aval devient une difference de
                    #      DEUX MESURES, sans aucun modele ;
                    #   2  un `n` inedit sur une tuile deja mesuree (isole la pente du %-list) ;
                    #   1  un `n` inedit ;
                    #   0  redondant.
                    connue = any(t == dst for (t, _n) in par_n)
                    inedit = (dst, nc) not in par_n
                    if nc != ng and (dst, ng) in par_n:
                        prio = 3
                    elif connue and inedit:
                        prio = 2
                    elif inedit:
                        prio = 1
                    else:
                        prio = 0
                    strike.append(((prio, 1 if nc != ng else 0, nc), dst, ng, nc))
                else:
                    # ON DEPLACE POUR CONSTRUIRE LA CONFIGURATION, jamais « bloque par la
                    # geometrie de spawn » : une position de repli vaut par le STRIKE qu'elle
                    # rend possible ensuite. Priorite 1 -- de la, il existe un strike ou les deux
                    # substrats DIVERGENT (c'est le seul montage qui chiffre l'aval sans modele).
                    prep = 0
                    for v in (vois_cible or []):
                        vg = _predire(Board, state, uid, dst, v, "G")
                        vc = _predire(Board, state, uid, dst, v, "C")
                        if vg != vc:
                            prep = 1
                            break
                    dd = hexgeo.distance(dst, tpos) if tpos else 0
                    repos.append(((prep, 1 if dd not in vues_dist else 0, dd), dst, ng, nc))
            strike.sort(reverse=True)
            repos.sort(reverse=True)
            # STRIKE seulement s'il APPORTE quelque chose ; sinon on s'ecarte pour le preparer.
            if strike and strike[0][0][0] >= 1:
                cands = strike
            elif repos:
                cands = repos
            else:
                cands = strike
            if not cands:
                approches += 1
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            _k, dst, ng, nc = cands[0]
            if tpos is not None:
                vues_dist.add(hexgeo.distance(dst, tpos))
            b_all = _counters(rpc(sid, "actorStats", {"runnerId": rid}, 60))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(uid), "to": {"col": dst[0], "row": dst[1]}}}, 120)
            a_all = _counters(rpc(sid, "actorStats", {"runnerId": rid}, 60))
            before, after = b_all.get(int(uid)), a_all.get(int(uid))
            reset = any(k != int(uid) and a_all.get(k) is not None and b_all.get(k) is not None
                        and a_all[k] < b_all[k] for k in b_all)
            nat = None if (before is None or after is None) else after - before
            if nat == 0 and dst != src:
                reset = True
            if reset or nat is None:
                print("      %s -> %s : NON MESURE (ResetThisTurn=%s)" % (src, dst, reset))
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            pr = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": int(uid),
                                        "targetId": int(tgt), "col": dst[0], "row": dst[1],
                                        "fresh": True}, 90)
            lo, hi = _predict_bounds(pr)
            print("   t%d u%s ptype=%d %s -> %s : NATIF n=%d (port G=%d C=%d)  cible=u%s@%s d=%s  "
                  "aiPredict=%s/%s"
                  % (turn, uid, ptype, src, dst, nat, ng, nc, tgt, tpos,
                     hexgeo.distance(dst, tpos) if tpos else "?", lo, hi))
            if verbose:
                print("        aiPredict brut: %s" % json.dumps(pr)[:400])
            if lo is None:
                print("        aiPredict SANS borne -- NON MESURE pour ce tour")
            else:
                # ⚠ INDEXE PAR (TUILE, n), ET C'EST UNE MESURE QUI L'IMPOSE. Le degat depend AUSSI
                # du %-list de la tuile d'attaque (surplomb) : la MEME valeur `n = 2` rend
                # 6024 depuis `(1,4)` et 9040 depuis `(0,3)`. Une pente calculee sur des tuiles
                # differentes melange les deux effets et n'attribue plus rien.
                par_n.setdefault((dst, nat), (lo, hi))
                if ng != nc:
                    disc_vus.append((src, dst, ng, nc, nat, lo, hi))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)

    print("\n   -> EXO (greffe=%s) : `aiPredict` APRES le move, par (tuile d'attaque, n)" % graft)
    for (t, n) in sorted(par_n, key=lambda k: (k[0], k[1])):
        print("        tuile %-8s n=%-3d  willKill=%-8s mightKill=%-8s"
              % (str(t), n, par_n[(t, n)][0], par_n[(t, n)][1]))
    # LA PENTE, calculee A TUILE CONSTANTE -- seule facon d'attribuer l'ecart au compteur.
    par_tuile = {}
    for (t, n) in par_n:
        par_tuile.setdefault(t, {})[n] = par_n[(t, n)]
    pentes = []
    for t, m in sorted(par_tuile.items()):
        ns = sorted(m)
        for a, b in zip(ns, ns[1:]):
            pentes.append((t, a, b, (m[b][0] - m[a][0]) / (b - a), (m[b][1] - m[a][1]) / (b - a)))
    if not pentes:
        print("      AUCUNE tuile avec DEUX valeurs de n -- la SENSIBILITE n'est pas mesuree "
              "a %-list constant (NON CONCLU)")
        return 1
    for (t, a, b, plo, phi) in pentes:
        print("      pente a tuile CONSTANTE %-8s n=%d->%d : willKill %+.1f/tuile   "
              "mightKill %+.1f/tuile" % (str(t), a, b, plo, phi))
    non_nulles = [p for p in pentes if p[3] != 0]
    if graft and not non_nulles:
        print("      ECART: le passif est GREFFE et le degat NE DEPEND PAS de n a tuile "
              "constante -- la greffe est inerte, ou la chaine ne remonte pas jusqu'au degat")
        return 1
    if (not graft) and non_nulles:
        print("      ECART: SANS greffe le degat depend deja de n -- une autre mecanique varie "
              "avec le deplacement, l'attribution a ModifiedExoarmour serait FAUSSE")
        return 1
    # L'ECART D'AVAL, ENTIEREMENT MESURE quand les DEUX valeurs `n_G` et `n_C` ont ete lues sur
    # LA MEME tuile : `D(n_C) - D(n_G)` est alors une difference de deux mesures, sans modele.
    for (s, d, ng, nc, nat, lo, hi) in disc_vus:
        m = par_tuile.get(d) or {}
        if ng in m and nat in m:
            print("      AVAL MESURE  %s -> %s : port AVANT #589 aurait lu n=%d (degat %s/%s), "
                  "le natif enregistre n=%d (degat %s/%s) -> ecart %+d/%+d"
                  % (s, d, ng, m[ng][0], m[ng][1], nat, m[nat][0], m[nat][1],
                     m[nat][0] - m[ng][0], m[nat][1] - m[ng][1]))
        else:
            print("      DISCRIMINANT %s -> %s : natif n=%d, geometrie n=%d -- l'autre valeur "
                  "n'a PAS ete mesuree sur cette tuile (ecart NON chiffre directement)"
                  % (s, d, nat, ng))
    return 0


def _predict_bounds(pr):
    """Les bornes de degat de `aiPredict` = `pred.willKillDmg` / `pred.mightKillDmg`.

    Ce sont les DEUX bornes du preview natif `GetAllPredictions` (`ProbableDamageEvent`), celles
    que #312/#322 nomment « natif min/max ». `None` = NON MESURE -- jamais un 0 par defaut, qui se
    lirait comme « aucun degat »."""
    pred = (pr or {}).get("pred")
    if not isinstance(pred, dict):
        return (None, None)
    lo = pred.get("willKillDmg", pred.get("healthDamageMin"))
    hi = pred.get("mightKillDmg", pred.get("healthDamageMax"))
    if lo is None or hi is None:
        return (None, None)
    return int(lo), int(hi)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("INV", "SCAN", "TILES", "EXO"), default="INV")
    ap.add_argument("--inject", action="store_true",
                    help="TILES : injecte le porteur au catalogue (`write_augmented_seed_bc`)")
    ap.add_argument("--no-graft", action="store_true",
                    help="EXO : CONTRE-BRAS sans le passif greffe (le degat ne doit PAS suivre n)")
    ap.add_argument("--reuse-bg", action="store_true",
                    help="relit le boardGraph deja capte dans logs/ (aucun runner monte)")
    ap.add_argument("--unit", default="blackHaarken")
    ap.add_argument("--fillers", default="bloodIntercessor,necroWarden")
    ap.add_argument("--foes", default="necroWarden")
    ap.add_argument("--board", default=BOARD_BRIDGE)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.only == "INV":
        return 0 if run_inv() == 0 else 1
    sid, rpc = _rpc_factory()
    # #448-r3-r1-r1 : les bras TILES et EXO GREFFENT (`write_augmented_seed_bc`,
    # `write_grafted_seed_bc`). Sans le canal `unitAbilityStates`, `load_state` ne seede pas les
    # kits REELLEMENT montes et le port derive du gameconfig, qui ignore la greffe -- port AMPUTE,
    # assertions negatives a vide. Le foyer (`snapshot._refuse_if_grafted`) LEVE sans cette ligne.
    from rl_collect_batch import bind_ambient_rpc
    bind_ambient_rpc(sid)
    print("== #589-r1 -- l'AVAL de tilesMovedThisTurn   session=%s   canal unitAbilityStates LIE"
          % sid)
    if a.only == "SCAN":
        n = run_scan(sid, rpc, a.board, a.seed, a.reuse_bg, a.verbose)
        print("VERDICT: %s (%d ecart(s))" % ("PASS" if n == 0 else "FAIL", n))
        return 0 if n == 0 else 1
    if a.only == "EXO":
        n = run_exo(sid, rpc, a.board, a.seed, a.turns, not a.no_graft, a.verbose)
        print("VERDICT: %s (%d ecart(s))" % ("PASS" if n == 0 else "FAIL", n))
        return 0 if n == 0 else 1
    n = run_tiles(sid, rpc, a.unit, [x for x in a.fillers.split(",") if x],
                  [x for x in a.foes.split(",") if x], a.board, a.seed, a.turns, a.verbose,
                  a.inject)
    print("VERDICT: %s (%d ecart(s))" % ("PASS" if n == 0 else "FAIL", n))
    return 0 if n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
