"""#433-r4-r1-r4-r2-r1-r1-r1 -- `RammingSpeed` : le SUBSTRAT d'adjacence, confronte au natif.

LE CRITERE, pose AVANT la methode
---------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetDynamicInvalidTargetReason`
lit son `casterTiles` en PARAMETRE (relu au decompile le 2026-08-05) :

    casterTile     = casterTiles[0]
    movedOrOffTile = UnitExtensions.DidMove(caster) || EntityExtensions.GetMainTile(caster) != casterTile
    isAdjacent     = battleQuery.<slot 0x61>(casterTiles, target)   // AreEntitiesAdjacent
    if (movedOrOffTile && !isAdjacent) return 0x10;                 // CasterHasNotMoved
    if (isAdjacent)                    return 0;
    ... branche de CHARGE (0x20 / 0x8000000 / 0)

Donc, evalue depuis une tuile HYPOTHETIQUE `T != mainTile`, `movedOrOffTile` est VRAI par
CONSTRUCTION et la fonction se REDUIT a `isAdjacent([T], GetTiles(target))`. C'est ce qui rend le
predicat d'adjacence natif lisible sur TOUT le set de move, sans deplacer une seule unite :

    castFromTiles(caster, target, 1059).moveTiles
      = { T dans GetMovableTilesFor(caster) : GetInvalidTargetReason(caster, T, target, 1059) == valide }
      = { T : AreTilesAdjacent([T], GetTiles(target)) }        (les autres regles etant satisfaites)

QUESTIONS BINAIRES
  Q1. Le port, place dans le MEME regime (position reecrite a `T`, flag « a bouge » pose), rend-il
      le MEME verdict que le natif sur CHAQUE tuile du set de move ? (attendu : 0 desaccord)
  Q2. Le bras d'AVANT (`hexgeo.distance(mainTile_caster, mainTile_cible) == 1`) en ratait-il ?
      **Un Q2 nul rend Q1 SANS VALEUR** : le montage serait degenere (board plat, aretes completes,
      cibles mono-hex) et l'accord ne prouverait rien. Le probe le dit et sort en ECART.

LES TROIS ECARTS EXERCES (tous PERMISSIFS cote port d'avant, sauf C qui est dans l'autre sens) :
  A. liste STOCKEE  -- `IsNeighbour` lit `ConnectivityComponent+0x10`, pas la couronne hex
                       (terrain `Bridge` -> aretes absentes : 4 sur `C1_74`, 38 sur `C3_14`).
  B. ELEVATION      -- `|dElev| < 2`, terme SEPARE de la primitive.
  C. EMPREINTES     -- deux `IList` : une MoW est adjacente par N'IMPORTE lequel de ses pieds.

Le porteur est GREFFE (`RammingSpeed` a ZERO porteur au gameconfig, mesure #353) :
`build_grafted_seed_bc` de `probe_353_ramming_speed_prediction`.

Usage (session DEJA warmee, depuis scripts/python, ASCII only) :
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --build
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --board C3_14 --build
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py            # re-joue sur le state-file
    python probe_433r4r1r4r2r1r1r1_ramming_speed_adjacence_live.py --dispose
VERDICT : 0 = accord total ET montage discriminant. 1 = desaccord. 2 = montage degenere/indisponible.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from probe_353_ramming_speed_prediction import build_grafted_seed_bc

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_rs_433r4r1r4r2r1r1r1.json"
STATE = LOGS / "rs_adj_433r4r1r4r2r1r1r1.json"

RAMMING_SPEED = 1059
GRAFT = "orksKillaKan"
P_UNITS = "orksKillaKan,astraBullgryn"
A_UNITS = "necroWarden,ultraTitus"
# La MoW ADVERSE ne porte PAS l'axe C par elle-meme (elle a un `MachineComponent`, pas de pieds) :
# elle le porte par son SUMMON. `DutyEternal` (1158) fait naitre `ultraSmnDreadnought` (Galatian),
# la SEULE unite a 3 pieds confrontable de ce build -- le seul autre producteur du noeud
# `IdunBattleLogic.Entities.DSLSelectors$$ThreeTileUnitSpawnShape`, `AetherStride` (1208, `thousDaemonPrince`), est hors seed
# BC et non porte. `ultraDreadnought` est dans les 8 MoW spawnables (`build --list-pool`).
A_MOW = "ultraDreadnought"
SEED = 43341
# `C1_74` et `C3_14` portent des `Bridge` (aretes stockees manquantes) ET des paliers d'elevation.
BOARD_DEFAUT = "C1_74"


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def build(board: str, a_mow: str = A_MOW) -> int:
    """Monte le runner GREFFE. La MoW adverse est OPTIONNELLE au sens du montage (l'axe C tombe
    sans elle), mais son absence est DITE plutot que silencieuse -- cf. `ventiler`."""
    LOGS.mkdir(parents=True, exist_ok=True)
    info = build_grafted_seed_bc(SEED_BC)
    print("[graft] %s -> %s (%s)" % (GRAFT, SEED_BC.name, json.dumps(info)))
    STATE.unlink(missing_ok=True)
    args = ["build", "--seed", str(SEED), "--board", board, "--rank", "17",
            "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
            "--unit-stat", "%s:ActiveAbilityLevel=8,AbilityVariablesMultiplierPercentage=100" % GRAFT,
            "--no-ai", "--state-file", str(STATE)]
    if a_mow:
        args += ["--a-mow", a_mow]
    _run(args)
    if not STATE.exists():
        raise SystemExit("build KO (board=%s) -- rien mesure" % board)
    return _runner_id()


def ensure_my_turn(rid: int) -> bool:
    """Rend la main quand LE CASTER est activable. Sans lui, `GetMovableTilesFor` rend un set VIDE
    et le zero serait un zero de HARNAIS, pas une mesure.

    ⚠ Le critere N'EST PAS `ctrl` : ce champ dit « controle par le joueur COURANT », donc il est
    VRAI pour les unites ADVERSES pendant leur tour -- une garde `toActivate & ctrl` se declare
    satisfaite au mauvais moment (faute mesuree ici meme). On vise l'id du CASTER, nommement.

    On passe le tour par `applyAction endturn`, PAS par `aiturn` : l'IA deplacerait les unites et
    detruirait la geometrie qu'on vient de monter."""
    for _ in range(6):
        dv = _dv(rid)
        cid = _caster_id(dv)
        if cid is not None and cid in set(dv.get("toActivate") or []):
            return True
        L._rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}])
    return False


def _caster_id(dv: dict):
    for u in (dv.get("units") or []):
        if u.get("visualId") == GRAFT and u.get("alive"):
            return u.get("id")
    return None


def _cibles(dv: dict, caster_id: int) -> list:
    """Les ennemis VIVANTS du caster : unites + MoW. La MoW n'est PAS dans `units` -- sa cle
    d'acteur est `mows[].casterId` (piege #115)."""
    mine = {u.get("id") for u in (dv.get("units") or []) if u.get("ctrl")}
    out = []
    for u in (dv.get("units") or []):
        if u.get("alive") and u.get("id") not in mine and u.get("id") != caster_id:
            out.append((u.get("id"), u.get("visualId"), False))
    for m in (dv.get("mows") or []):
        mid = m.get("casterId") if m.get("casterId") is not None else m.get("id")
        if mid is not None and mid not in mine and m.get("alive", True):
            out.append((mid, m.get("visualId"), True))
    return out


def _movable(rid: int, caster_id: int) -> list:
    """`GetMovableTilesFor(caster, false, {})` -- LE MEME set que balaye `castFromTiles`."""
    mov = L._rpc("aiMovableTiles", [{"runnerId": rid}])
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == caster_id:
            return [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def natif_valides(rid: int, caster_id: int, target_id: int) -> tuple:
    """`castFromTiles` = `GetInvalidTargetReason(caster, <tuile>, target, 1059)` par tuile de move.
    Rend `(currentValid, {(col,row) valides})`."""
    r = L._rpc("castFromTiles", [{"runnerId": rid, "casterId": caster_id,
                                 "targetId": target_id, "abilityType": RAMMING_SPEED}])
    if not r.get("ok"):
        raise SystemExit("castFromTiles KO : %s" % r.get("error"))
    return bool(r.get("currentValid")), {(t["col"], t["row"]) for t in (r.get("moveTiles") or [])}


# ------------------------------------------------------------------ cote PORT

def _port_valides(dv, ob, snap, bg, caster_id: int, target_id: int, tuiles, bras_avant: bool):
    """Le verdict du PORT depuis chaque tuile de `tuiles`, dans le REGIME du natif hypothetique.

    Deux ecritures OFFLINE sur un `State` recharge par tuile -- la position du caster, et le flag
    « a bouge ». La seconde n'est PAS un artifice : depuis une tuile `T != mainTile` le natif a
    `movedOrOffTile` VRAI par construction (`GetMainTile(caster) != casterTiles[0]`), et le port ne
    modelise cette 2e clause nulle part (residu assume, docstring d'`orks.py`). La poser, c'est
    mettre les deux moteurs dans le MEME regime -- sans elle on comparerait la branche de CHARGE
    du port a la branche d'ADJACENCE du natif.

    `bras_avant` substitue le foyer tel qu'`orks.py` le voit par le predicat d'AVANT le correctif
    (`hexgeo.distance` sur les deux MAIN TILES) : c'est la CONTRE-EPREUVE, et c'est elle qui dit si
    le montage discrimine.
    """
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities import orks as ORKS
    from engine.runner.abilities.targeting import is_invalid_target
    from engine.runner.components import PositionComponent, set_moved_flag
    from engine.runner.snapshot import load_state

    board = Board(bg.get("tiles") or [], adjacency="native_sym")
    ability = ORKS.RammingSpeedAbility()
    ancien = ORKS.are_entities_adjacent

    def _main_tile_hex(feet_a, feet_b, _board=None):
        if not feet_a or not feet_b:
            return False
        return hexgeo.distance(tuple(feet_a[0]), tuple(feet_b[0])) == 1

    valides = set()
    try:
        if bras_avant:
            ORKS.are_entities_adjacent = _main_tile_hex
        for (c, r) in tuiles:
            st = load_state(dv, ob, snap, board=board)
            e = st.get_entity(int(caster_id))
            pc = e.get_component(PositionComponent) if e is not None else None
            if pc is None:
                continue
            pc.col, pc.row = int(c), int(r)
            set_moved_flag(st, int(caster_id))
            if int(is_invalid_target(st, int(caster_id), int(target_id), ability)) == 0:
                valides.add((c, r))
    finally:
        ORKS.are_entities_adjacent = ancien
    return valides


# ------------------------------------------------------------------ montage DERIVE du board

def choisir_poste(bg: dict, movable) -> tuple:
    """La tuile `P` ou POSTER la cible, DERIVEE du board -- rien de code en dur.

    On cherche `P` dont les voisins HEX walkables tombant dans le set de move se ventilent en DEUX
    groupes NON VIDES : ceux que le natif tient pour adjacents (arete presente dans la liste
    STOCKEE) et ceux qu'il refuse. Le second groupe est exactement ce que la couronne hex du bras
    d'avant sur-atteignait. Les deux doivent etre non vides -- sans le premier on ne verifierait
    que des refus, sans le second le montage serait DEGENERE.

    Rend `(P, refuses, tenus, axes)` ou `axes` ventile chaque tuile refusee :
      'elevation' = arete PRESENTE dans le `ConnectivityComponent` brut mais |dElev| >= 2 ;
      'arete'     = arete ABSENTE du `ConnectivityComponent` (terrain `Bridge`, `HasEdge` refuse) ;
      'inconnu'   = canal `connectivity` non capte (bundle anterieur) -- on ne DEVINE pas.
    `None` si le board n'en porte pas dans la portee courante."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    tiles = bg.get("tiles") or []
    board = Board(tiles, adjacency="native_sym")
    par_pos = {(t["col"], t["row"]): t for t in tiles}
    M = set(movable)
    best = None
    for t in tiles:
        if not t.get("walkable"):
            continue
        P = (t["col"], t["row"])
        # `P` PEUT etre dans le set de move : une fois la cible postee dessus la tuile est occupee
        # et sort du set. On la retire donc ici aussi, sinon on compterait `P` parmi ses voisins.
        tenus, refuses, axes = [], [], {}
        stockes = board.neighbours(t["id"])
        conn = board.neighbours_connectivity(t["id"])
        for q in hexgeo.neighbors(*P):
            u = par_pos.get(q)
            if u is None or not u.get("walkable") or q not in M or q == P:
                continue
            if u["id"] in stockes:
                tenus.append(q)
            else:
                refuses.append(q)
                if conn is None:
                    axes[q] = "inconnu"
                elif u["id"] in conn:
                    axes[q] = "elevation"
                else:
                    axes[q] = "arete"
        if tenus and refuses:
            # L'axe `arete` PASSE D'ABORD : c'est le seul ou l'elevation n'explique rien, donc le
            # seul qui exerce la liste STOCKEE toute seule. A defaut on retombe sur `elevation`.
            cle = (1 if "arete" in axes.values() else 0, len(refuses), len(tenus))
            if best is None or cle > best[0]:
                best = (cle, P, sorted(refuses), sorted(tenus), axes)
    return None if best is None else (best[1], best[2], best[3], best[4])


# ------------------------------------------------------------------ axe C : l'EMPREINTE (Galatian)

def _ammo_graft_seed_bc(out_path: Path, ammo: int = 9) -> None:
    """Seed BC portant LES DEUX patches : la greffe de `RammingSpeed` sur `orksKillaKan` ET les
    munitions de MoW. Le seed partage part a `MachineOfWarAmmo = 0`, donc AUCUNE MoW ne caste --
    sans ce second patch `DutyEternal` (1158, cout 3) ne part jamais et l'axe C reste vide."""
    build_grafted_seed_bc(out_path)
    bc = json.loads(out_path.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:          # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    out_path.write_text(json.dumps(bc), encoding="utf-8")


def _occupants(rid: int) -> set:
    g = L._rpc("boardGraph", [{"runnerId": rid}])
    return {(t["col"], t["row"]) for t in (g.get("tiles") or [])
            if t.get("occupantUnitId") is not None}


def faire_naitre_galatian(rid: int, caster_pos) -> bool:
    """Fait caster `DutyEternal` (1158) a la MoW ADVERSE -> `ultraSmnDreadnought` (Galatian), la
    SEULE unite a 3 pieds confrontable de ce build (l'autre producteur de
    `IdunBattleLogic.Entities.DSLSelectors$$ThreeTileUnitSpawnShape`, `AetherStride` 1208, est hors seed BC et non porte).

    L'ancre est choisie pour que l'empreinte tombe PRES du caster : sans ca les tuiles
    discriminantes -- adjacentes a un pied SECONDAIRE et a distance >= 2 du pied 0 -- sortent du
    set de move et le montage ne mesure rien.

    DEUX refus SILENCIEUX a eviter (`applyAction` rend alors `ok:true, mutated:false`) : le
    cooldown initial (2 tours) et le fait que ce doit etre le TOUR DU PROPRIETAIRE de la MoW."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.services import spawn_tile_shape as STS

    dv = _dv(rid)
    cid = _caster_id(dv)
    deja = [uid for uid, f in _pieds(rid).items() if len(f) > 1 and uid != cid]
    if deja:
        print("[axeC] empreinte multi-hex DEJA presente (u%s) -- pas de nouveau cast" % deja[0])
        return True
    mows = [m for m in (dv.get("mows") or []) if m.get("visualId") == A_MOW]
    if not mows:
        print("[axeC] %s absente de decisionView.mows -- pas de MoW, axe C NON couvert" % A_MOW)
        return False
    mow, owner = mows[0], mows[0].get("owner")
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    board = Board(bg.get("tiles") or [], adjacency="native_sym")
    occ = _occupants(rid)
    best = None
    for t in (bg.get("tiles") or []):
        A = (t["col"], t["row"])
        aire = STS.get_area(board, occ, A)
        if len(aire) != 3:
            continue
        d0 = hexgeo.distance(caster_pos, aire[0])
        # Les tuiles DISCRIMINANTES : adjacentes (hex) a un pied SECONDAIRE, mais a >= 2 du pied 0.
        disc = [q for f in aire[1:] for q in hexgeo.neighbors(*f)
                if hexgeo.distance(q, aire[0]) >= 2 and q not in occ
                and board.id_at(*q) is not None and board.walkable(board.id_at(*q))]
        if not disc:
            continue
        if best is None or (len(set(disc)), -d0) > (len(set(best[2])), -best[3]):
            best = (A, aire, disc, d0)
    if best is None:
        print("[axeC] aucune ancre a aire valide ET discriminante sur ce board")
        return False
    A, aire, disc, d0 = best
    print("[axeC] ancre=%s aire=%s (dist caster->pied0 = %d) tuiles discriminantes=%d"
          % (A, aire, d0, len(set(disc))))
    for _ in range(12):
        v = _dv(rid)
        m = next((x for x in (v.get("mows") or []) if x.get("visualId") == A_MOW), None)
        ab = next((a for a in ((m or {}).get("abilities") or []) if a.get("id") == 1158), None)
        if ab is None:
            print("[axeC] 1158 absente des abilities de la MoW")
            return False
        pret = ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0)
        if pret and (owner is None or v.get("currentPlayer") == owner):
            break
        L._rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}])
    else:
        print("[axeC] 1158 jamais castable -- axe C NON couvert")
        return False
    tid = board.id_at(A[0], A[1])
    L._rpc("applyAction", [{"runnerId": rid, "action": {
        "kind": "ability", "casterId": mow.get("casterId"), "abilityType": 1158,
        "targetId": tid}}])
    pieds = _pieds(rid)
    ok = any(len(f) == 3 for f in pieds.values())
    print("[axeC] apres cast : empreintes multi-pieds = %s"
          % {k: v for k, v in pieds.items() if len(v) > 1})
    return ok


def _pieds(rid: int) -> dict:
    """`{squadId: [(col,row) par pied, ordonne par entityId]}` -- l'empreinte NATIVE."""
    out = {}
    for u in (L._rpc("observeBattle", [{"runnerId": rid}]).get("units") or []):
        if u.get("col") is None or u.get("isDead"):
            continue
        out.setdefault(u.get("squadId"), []).append((u.get("entityId") or 0,
                                                     (u["col"], u["row"])))
    return {k: [p for _e, p in sorted(v)] for k, v in out.items()}


def poster(rid: int, unit_id: int, P) -> bool:
    """`applyAction move` NE VERIFIE PAS la propriete de `unitId` (runner.md sec.4) : on poste donc
    la CIBLE sans depenser le mouvement du caster. Un move refuse ne leve rien -> on RELIT."""
    _run(["act", "move", "--unit", str(unit_id), "--to", "%d,%d" % (P[0], P[1]),
          "--state-file", str(STATE), "--runner", str(rid)])
    for u in (_dv(rid).get("units") or []):
        if u.get("id") == unit_id:
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row")) == tuple(P)
    return False


# ------------------------------------------------------------------ ventilation

def ventiler(rid: int) -> int:
    dv = _dv(rid)
    caster_id = _caster_id(dv)
    if caster_id is None:
        print("VERDICT: 2 -- caster %s absent/mort, rien mesure" % GRAFT)
        return 2
    tuiles = _movable(rid, caster_id)
    if not tuiles:
        print("VERDICT: 2 -- set de move VIDE (hors tour ? deja agi ?), rien mesure")
        return 2
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    poste = choisir_poste(bg, tuiles)
    if poste is None:
        print("VERDICT: 2 -- ce board ne porte AUCUNE paire discriminante dans la portee courante"
              " ; rien mesure (essayer --board C3_14)")
        return 2
    P, refuses, tenus, axes = poste
    cibles0 = _cibles(dv, caster_id)
    if not cibles0:
        print("VERDICT: 2 -- aucune cible ennemie vivante, rien mesure")
        return 2
    print("[montage] poste DERIVE du board : P=%s  refuses par le natif=%s (%s)  tenus=%s"
          % (P, refuses, ",".join(sorted(set(axes.values()))), tenus))
    if not poster(rid, cibles0[0][0], P):
        print("VERDICT: 2 -- placement de la cible u%s en %s REFUSE, montage invalide"
              % (cibles0[0][0], P))
        return 2
    dv = _dv(rid)
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    snap = L._rpc("combatSnapshot", [{"runnerId": rid}])
    tuiles = _movable(rid, caster_id)
    cibles = _cibles(dv, caster_id)
    print("caster u%s [%s]  tuiles de move=%d  cibles=%d"
          % (caster_id, GRAFT, len(tuiles), len(cibles)))
    n_desaccord = 0
    n_discriminants = 0
    n_paires = 0
    for (tid, vid, is_mow) in cibles:
        nat_cur, nat = natif_valides(rid, caster_id, tid)
        apres = _port_valides(dv, ob, snap, bg, caster_id, tid, tuiles, bras_avant=False)
        avant = _port_valides(dv, ob, snap, bg, caster_id, tid, tuiles, bras_avant=True)
        nat = nat & set(tuiles)
        d_apres = (nat ^ apres)
        d_avant = (nat ^ avant)
        n_paires += len(tuiles)
        n_desaccord += len(d_apres)
        n_discriminants += len(d_avant)
        print("  cible u%-4s [%-28s]%s natif=%-3d port_APRES=%-3d port_AVANT=%-3d"
              " | desaccord APRES=%d AVANT=%d%s"
              % (tid, vid, " MoW" if is_mow else "    ", len(nat), len(apres), len(avant),
                 len(d_apres), len(d_avant),
                 ("  currentValid=%s" % nat_cur)))
        for t in sorted(d_apres)[:6]:
            print("      DESACCORD %s : natif=%s port=%s"
                  % (t, t in nat, t in apres))
        for t in sorted(d_avant)[:6]:
            print("      (avant) %s [axe %s] : natif=%s port_AVANT=%s"
                  " -- l'ecart que le correctif ferme"
                  % (t, axes.get(t, "?"), t in nat, t in avant))
    print("-- paires (tuile, cible) evaluees : %d" % n_paires)
    print("-- Q1 desaccords natif/port APRES le correctif : %d (attendu 0)" % n_desaccord)
    print("-- Q2 tuiles ou le bras d'AVANT divergeait      : %d (0 = montage DEGENERE)"
          % n_discriminants)
    if n_desaccord:
        print("VERDICT: 1 -- le port ne suit pas le natif")
        return 1
    if not n_discriminants:
        print("VERDICT: 2 -- MONTAGE DEGENERE : le bras d'avant donne le meme resultat,"
              " l'accord ne prouve rien (changer de board / de cible)")
        return 2
    print("VERDICT: 0 -- accord total sur un montage DISCRIMINANT")
    return 0


def ventiler_empreintes(rid: int) -> int:
    """AXE C -- la cible est MULTI-HEX. Le montage n'a plus besoin d'une paire de tuiles : c'est
    l'EMPREINTE qui discrimine, et dans l'AUTRE SENS des axes A/B (le bras d'avant INVENTAIT un
    refus la ou le natif tient l'unite pour adjacente par un pied secondaire)."""
    import hexgeo

    dv = _dv(rid)
    caster_id = _caster_id(dv)
    if caster_id is None:
        print("VERDICT: 2 -- caster absent, rien mesure")
        return 2
    pieds = _pieds(rid)
    multi = [(uid, f) for uid, f in pieds.items() if len(f) > 1 and uid != caster_id]
    if not multi:
        print("VERDICT: 2 -- aucune cible MULTI-HEX vivante, axe C NON couvert")
        return 2
    tuiles = _movable(rid, caster_id)
    if not tuiles:
        print("VERDICT: 2 -- set de move VIDE, rien mesure")
        return 2
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    snap = L._rpc("combatSnapshot", [{"runnerId": rid}])
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    n_desaccord = n_disc = 0
    for (tid, feet) in multi:
        nat_cur, nat = natif_valides(rid, caster_id, tid)
        nat &= set(tuiles)
        apres = _port_valides(dv, ob, snap, bg, caster_id, tid, tuiles, bras_avant=False)
        avant = _port_valides(dv, ob, snap, bg, caster_id, tid, tuiles, bras_avant=True)
        d_apres, d_avant = nat ^ apres, nat ^ avant
        n_desaccord += len(d_apres)
        n_disc += len(d_avant)
        print("  cible MULTI-HEX u%-4s pieds=%s  natif=%d port_APRES=%d port_AVANT=%d"
              " | desaccord APRES=%d AVANT=%d  currentValid=%s"
              % (tid, feet, len(nat), len(apres), len(avant), len(d_apres), len(d_avant), nat_cur))
        for t in sorted(d_apres)[:6]:
            print("      DESACCORD %s : natif=%s port=%s" % (t, t in nat, t in apres))
        for t in sorted(d_avant)[:6]:
            print("      (avant) %s : natif=%s port_AVANT=%s -- d(pied0)=%d d(empreinte)=%d"
                  % (t, t in nat, t in avant, hexgeo.distance(t, feet[0]),
                     min(hexgeo.distance(t, f) for f in feet)))
    print("-- Q1 desaccords natif/port APRES le correctif : %d (attendu 0)" % n_desaccord)
    print("-- Q2 tuiles ou le bras d'AVANT divergeait      : %d (0 = montage DEGENERE)" % n_disc)
    if n_desaccord:
        print("VERDICT: 1 -- le port ne suit pas le natif sur l'empreinte")
        return 1
    if not n_disc:
        print("VERDICT: 2 -- MONTAGE DEGENERE (aucune tuile n'atteint un pied SECONDAIRE seul)")
        return 2
    print("VERDICT: 0 -- accord total sur un montage DISCRIMINANT (axe EMPREINTES)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--board", default=BOARD_DEFAUT)
    ap.add_argument("--no-mow", action="store_true", help="monte SANS MoW adverse (axe C absent)")
    ap.add_argument("--axe-c", action="store_true",
                    help="axe EMPREINTES : fait naitre le Galatian (3 pieds) et confronte dessus")
    ap.add_argument("--dispose", action="store_true")
    a = ap.parse_args()
    if a.dispose:
        if STATE.exists():
            _run(["dispose", "--state-file", str(STATE), "--runner", str(_runner_id())])
            print("[dispose] runner du state-file")
        return 0
    if a.build or not STATE.exists():
        if a.axe_c:
            LOGS.mkdir(parents=True, exist_ok=True)
            _ammo_graft_seed_bc(SEED_BC)
            print("[graft+ammo] %s" % SEED_BC.name)
            STATE.unlink(missing_ok=True)
            _run(["build", "--seed", str(SEED), "--board", a.board, "--rank", "17",
                  "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
                  "--a-mow", A_MOW, "--no-ai", "--state-file", str(STATE)])
            if not STATE.exists():
                raise SystemExit("build KO (board=%s) -- rien mesure" % a.board)
            rid = _runner_id()
        else:
            rid = build(a.board, a_mow="" if a.no_mow else A_MOW)
    else:
        rid = _runner_id()
    if a.axe_c:
        dv = _dv(rid)
        cid = _caster_id(dv)
        cpos = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                     if u.get("id") == cid and u.get("pos")), None)
        if cpos is None:
            print("VERDICT: 2 -- caster sans position, rien mesure")
            return 2
        if not faire_naitre_galatian(rid, cpos):
            print("VERDICT: 2 -- Galatian non ne, axe C NON CONFRONTE")
            return 2
        if not ensure_my_turn(rid):
            print("VERDICT: 2 -- le caster n'a jamais repris la main, rien mesure")
            return 2
        return ventiler_empreintes(rid)
    if not ensure_my_turn(rid):
        print("VERDICT: 2 -- le caster n'a jamais repris la main, rien mesure")
        return 2
    return ventiler(rid)


if __name__ == "__main__":
    raise SystemExit(main())
