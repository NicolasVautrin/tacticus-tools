"""#10022-r3 / #10022-r1 -- CONFRONTATION LIVE : la geometrie commande-t-elle l'ORDRE
d'activation de l'IA, et le port de `ShortestPathToEnemyUtility` le predit-il ?

UNE seule experience tranche les DEUX items, et c'est pour ca qu'elle est ecrite ici.

  * si `AiControl.<+0x70>` (`configurationRandomizeAiInput`) valait VRAI, `AiControl$$GetAi`
    rendrait `IdunBattle.AI.WithSomeRandomnessStrategy`, dont
    `RandomGroupOperation.u003CPickNextUnitu003Ed__7$$MoveNext` fait
    `validUnits[random(validUnits.Count)]` -- un tirage uniforme **INDEPENDANT DES POSITIONS**.
    Une prediction geometrique ne pourrait alors pas suivre, sinon par hasard ;
  * s'il vaut FAUX, c'est `DefaultGroupOperator` et ses huit buckets, dont le 6e est
    `UnitWithShortestPathToEnemy` -- l'unite activee est l'argmax de `-minSteps`.

⇒ **faire varier UNIQUEMENT la geometrie, a seed / board / roster CONSTANTS, et regarder si
l'ordre observe suit la prediction.** C'est simultanement la mesure LIVE de #10022-r1 et la
confrontation de #10022-r3.

LE MONTAGE, et pourquoi il est fait comme ca
---------------------------------------------
Roster IA = **N CLONES du meme unitId**. Ce n'est pas une commodite, c'est ce qui NEUTRALISE
mecaniquement les buckets 0 a 5 (cf. `docs/rl/case-10022-unitpicker-inventaire.md` section 8) :

  bucket 0 `PreferSummons`        : aucun clone n'est Summon/Object -> tous VETO_CONDITIONNEL,
                                    donc `best` reste nul et la boucle de veto ne s'execute PAS ;
  bucket 1 `PreferNonBoss`        : aucun n'est boss -> tous `0`, `diff 0 > 1` faux ;
  bucket 2 `PreferFreshlySpawned` : meme provenance -> meme valeur ;
  bucket 3 `UnitOrder`            : meme `unitId`, memes abilities, memes traits -> meme somme.
                                    Son flag de cut n'elimine personne quand tout vaut pareil ;
  bucket 4 `LastAbilities`        : aucun ne porte `RealityUnbound` ;
  bucket 5 `PreferAbilities`      : constante HORS COURSE pour toute unite dans ce build.

Reste le bucket 6. C'est le seul etage qui puisse departager des clones, et il ne lit QUE la
geometrie.

LA GARDE ANTI-COURT-CIRCUIT -- sans elle la mesure ne vaut rien
----------------------------------------------------------------
`decisionView.toActivate` **n'est PAS** l'ordre choisi par le natif : c'est l'ENSEMBLE des unites
activables dans l'ordre d'ITERATION de l'ECS, soit (a un cran pres) l'ENTREE du picker
(`AnAiGroupOperator$$GetValidUnits`). Une prediction qui coinciderait avec `toActivate[0]` ne
prouverait donc RIEN -- ce serait l'accord en regime degenere.

Ce probe **REFUSE** une configuration ou l'argmax predit est deja le premier de `toActivate`, et
il compte separement les configurations DISCRIMINANTES. S'il n'y en a aucune, il rend ROUGE : une
serie entierement degeneree est un echec de montage, pas un succes.

Usage (session Frida deja warmee ; le probe dispose SES runners, jamais ceux des autres) :

    python probe_10022r3_ordre_activation_live.py [--board MC1_67] [--seed 777] [--configs 6]

rc 0 = toutes les configurations discriminantes concordent ; rc 1 = au moins un desaccord, ou
aucune configuration discriminante ; rc 2 = PAS MESURE (session/host indisponible -- jamais
rabattu sur un vert). Sortie ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.pathfinding.ignore_terrain_pathfinder import (        # noqa: E402
    get_path_node_counts)
from engine.utilities.base import OUT_OF_RUNNING                           # noqa: E402
from engine.utilities.unit_picker import ShortestPathToEnemyUtility        # noqa: E402

ROOT = PYDIR.parent.parent
CLONE = "astraBullgryn"          # heros ordinaire : ni boss, ni summon, ni psyker, hors UnitOrder


def _r(sid, method, body, timeout=120):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


# --------------------------------------------------------------------------------------------- #
#  Montage
# --------------------------------------------------------------------------------------------- #

def seed_bc_randomise():
    """Copie de `data/seed-bc.json` avec `RandomizeAiInput = True`, ecrite sous `logs/`.

    C'est le BRAS NEGATIF de l'experience, et le seul qui etablisse la CAUSALITE de #10022-r1 :
    si l'ordre d'activation cesse de suivre la geometrie quand ce SEUL champ passe a `true`,
    alors c'est bien lui qui commande le choix entre `DefaultPlayerStrategy` (les huit buckets)
    et `WithSomeRandomnessStrategy` (tirage uniforme). Sans ce bras, le vert du bras positif
    serait compatible avec « la geometrie commande, mais par un autre chemin »."""
    src = ROOT / "data" / "seed-bc.json"
    dst = ROOT / "logs" / ("_probe10022r3-seedbc-randomize-%d.json" % os.getpid())
    dst.parent.mkdir(parents=True, exist_ok=True)
    bc = json.loads(src.read_text(encoding="utf-8"))
    if bc.get("RandomizeAiInput") is not False:
        raise RuntimeError("seed-bc.json ne porte plus `RandomizeAiInput: false` -- le bras "
                           "negatif n'aurait plus de temoin (valeur lue : %r)"
                           % (bc.get("RandomizeAiInput"),))
    bc["RandomizeAiInput"] = True
    dst.write_text(json.dumps(bc), encoding="utf-8")
    return dst


def build(seed, board, places_ia, place_moi, state_file, seed_bc=None):
    """`rl_duel build` avec placements EXACTS des deux camps. `--a-place` sort l'unite de
    `BC.PredefinedUnits` et la pose par `AddUnitMessage` sur la tuile demandee : c'est ce qui
    permet de faire varier la geometrie SANS consommer l'action d'une unite (un `act move` la
    marquerait comme ayant bouge et changerait ce qu'on mesure)."""
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state_file), "--no-ai",
            "--p-units", CLONE, "--a-units", ",".join([CLONE] * max(1, len(places_ia)))]
    #: `place_moi is None` = build SONDE : on ne veut que le `boardGraph` (pour DERIVER les
    #: geometries), donc aucun placement -- et donc aucun refus possible d'`AddUnitOperation`.
    if place_moi is not None:
        argv += ["--place", "%s:%d,%d" % (CLONE, place_moi[0], place_moi[1])]
    if seed_bc is not None:
        argv += ["--seed-bc", str(seed_bc)]
    for p in places_ia:
        argv += ["--a-place", "%s:%d,%d" % (CLONE, p[0], p[1])]
    Path(state_file).unlink(missing_ok=True)
    res = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True, timeout=420)
    if res.returncode != 0 or not Path(state_file).exists():
        return None, (res.stdout or "")[-1500:] + (res.stderr or "")[-800:]
    return json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"], None


def positions_et_teams(sid, rid):
    """`{unitId: (pos, team)}` depuis `decisionView`, plus la liste `toActivate` (l'ORDRE
    D'ITERATION ECS -- l'ENTREE du picker, jamais sa sortie)."""
    dv = _r(sid, "decisionView", {"runnerId": rid}, 90) or {}
    par_id = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if p.get("col") is None:
            continue
        par_id[int(u["id"])] = ((int(p["col"]), int(p["row"])), int(u.get("team") or 0))
    return par_id, list(dv.get("toActivate") or []), dv


def predire(board_obj, par_id, ids_ia, team_ia):
    """L'utilite PORTEE, unite par unite. Rend `{unitId: valeur}`.

    `path_node_count` passe par `ignore_terrain_pathfinder.get_path_node_counts`, le mirror
    (deja confronte) de `IPathfinders.GetPath(PathfinderType.IgnoreTerrain, ...)` -- une passe
    INVERSE depuis la tuile de DEPART, dont le module documente l'equivalence."""
    util = ShortestPathToEnemyUtility()
    idof = {(t["col"], t["row"]): t["id"] for t in board_obj.by_id.values()}
    occupants = {idof[p]: uid for uid, (p, _t) in par_id.items() if p in idof}
    cache = {}

    def counts_depuis(pos):
        if pos not in cache:
            tid = idof.get(pos)
            cache[pos] = {} if tid is None else get_path_node_counts(board_obj, tid, occupants)
        return cache[pos]

    def main_tile_of(uid):
        return par_id[uid][0]

    def enemies_of(uid):
        mien = par_id[uid][1]
        return [o for o, (_p, t) in par_id.items() if t != mien]

    def path_node_count(_unit, frm, to):
        tid = idof.get(to)
        return None if tid is None else counts_depuis(frm).get(tid)

    return {uid: util.evaluate_unit(uid, main_tile_of=main_tile_of, enemies_of=enemies_of,
                                    hex_distance=lambda a, b: hexgeo.distance(a, b),
                                    path_node_count=path_node_count)
            for uid in ids_ia}


def detour_max(board_obj, par_id, ids_ia) -> int:
    """`max(pathCount - hexDist - 1)` sur les couples (unite IA, ennemi) de la configuration.

    POURQUOI ON LE MESURE : l'elagage 1 du natif (`minSteps <= hexDist(unitTile, targetTile)` ->
    skip) n'est ADMISSIBLE que parce qu'un chemin de `hexDist` aretes compte `hexDist + 1` noeuds.
    Tant que ce detour vaut **0** partout, l'elagage ne peut pas se distinguer de son absence : le
    board ne l'EXERCE pas, et un vert ne dit rien de lui. Une valeur > 0 signifie qu'au moins un
    couple a du CONTOURNER -- c'est l'axe « relief et detour » de #10022-r7, et il est desormais
    RAPPORTE au lieu d'etre suppose."""
    idof = {(t["col"], t["row"]): t["id"] for t in board_obj.by_id.values()}
    occupants = {idof[p]: uid for uid, (p, _t) in par_id.items() if p in idof}
    pire = 0
    for uid in ids_ia:
        p_u, team = par_id[uid]
        tid = idof.get(p_u)
        if tid is None:
            continue
        comptes = get_path_node_counts(board_obj, tid, occupants)
        for o, (p_o, t_o) in par_id.items():
            if t_o == team:
                continue
            n = comptes.get(idof.get(p_o))
            if n is None:
                continue
            pire = max(pire, int(n) - hexgeo.distance(p_u, p_o) - 1)
    return pire


def premiere_activation(sid, rid):
    """Passe la main a l'IA puis joue UNE activation. Rend `(unitId, toActivate_avant, info)`.

    `aiPlayByUnit` peuple `demos` a chaque `MoveUnitMessage` avec `activatedUnitId` ET le
    `toActivate` capture JUSTE AVANT -- les deux dont ce probe a besoin, dans le meme objet."""
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    r = _r(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1,
                                 "maxPump": 30000, "captureEvents": True}, 300) or {}
    demos = r.get("demos") or []
    if demos:
        d = demos[0]
        return d.get("activatedUnitId"), list(d.get("toActivate") or []), r.get("stopReason")
    # Repli : aucune demo (aucune unite n'a BOUGE) -> le premier event annote de la cascade.
    for ev in (r.get("cascade") or []):
        if ev.get("activationUnitId") is not None:
            return ev["activationUnitId"], [], r.get("stopReason")
    return None, [], r.get("stopReason")


# --------------------------------------------------------------------------------------------- #

def une_config(sid, seed, board_id, places_ia, place_moi, idx, rapport, seed_bc=None):
    state_file = ROOT / "logs" / ("_probe10022r3-%d-%d.json" % (os.getpid(), idx))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid, err = build(seed, board_id, places_ia, place_moi, state_file, seed_bc=seed_bc)
    if rid is None:
        rapport.append("config %d : BUILD ECHOUE -- %s" % (idx, (err or "")[-400:]))
        return None
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
        if not bg.get("tiles"):
            rapport.append("config %d : boardGraph VIDE -- non mesure" % idx)
            return None
        board_obj = Board(bg["tiles"], adjacency="native_sym")
        par_id, to_activate, _dv = positions_et_teams(sid, rid)
        teams = {t for (_p, t) in par_id.values()}
        if len(teams) < 2:
            rapport.append("config %d : une seule team vue (%r) -- non mesure" % (idx, teams))
            return None
        team_moi = par_id[min(par_id)][1] if par_id else 1
        # La team IA est celle des CLONES adverses : celle qui n'est pas la mienne. On la derive
        # du placement (mon roster est d'une seule unite).
        comptes = {}
        for _uid, (_p, t) in par_id.items():
            comptes[t] = comptes.get(t, 0) + 1
        team_ia = max(comptes, key=lambda t: comptes[t])
        ids_ia = sorted([u for u, (_p, t) in par_id.items() if t == team_ia])
        if len(ids_ia) < 2:
            rapport.append("config %d : moins de 2 unites IA (%r) -- rien a departager"
                           % (idx, ids_ia))
            return None

        util_par_id = predire(board_obj, par_id, ids_ia, team_ia)
        vivants = {u: v for u, v in util_par_id.items() if v is not OUT_OF_RUNNING}
        if not vivants:
            rapport.append("config %d : toutes les utilites sont HORS COURSE -- non mesure" % idx)
            return None
        # argmax, ex-aequo tranche par l'ordre d'iteration ECS (comparaison STRICTE `>` du natif
        # dans `CalculateUtilitiesForCasesEnumerated` : le PREMIER a atteindre le max garde `best`).
        ordre_ecs = [u for u in to_activate if u in vivants] or sorted(vivants)
        meilleur = None
        for u in ordre_ecs:
            if meilleur is None or vivants[u] > vivants[meilleur]:
                meilleur = u

        active, to_activate_avant, stop = premiere_activation(sid, rid)
        ecs_avant = [u for u in (to_activate_avant or to_activate) if u in vivants]
        # TROIS etats, pas deux. Un `toActivate` VIDE ne veut pas dire « non degenere » : il veut
        # dire qu'on N'A PAS MESURE l'ordre d'iteration ECS, donc qu'on ne peut RIEN dire de la
        # degenerescence. Le rabattre sur « discriminant » gonflerait le compte du bras positif
        # avec des configurations dont on ignore si elles prouvent quoi que ce soit.
        if not ecs_avant:
            statut = "ECS_INCONNU"
        elif ecs_avant[0] == meilleur:
            statut = "DEGENERE"
        else:
            statut = "DISCRIMINANT"
        ok = (active == meilleur)
        note = {"DEGENERE": " (DEGENERE : predit == ECS[0], ne prouve rien)",
                "ECS_INCONNU": " (ECS NON MESURE : degenerescence indeterminee)"}.get(statut, "")
        detour = detour_max(board_obj, par_id, ids_ia)
        rapport.append(
            "config %d : places=%s | utilites=%s | ECS=%s | predit=%s | active=%s | detour=%d | %s%s"
            % (idx, places_ia,
               {u: (round(float(v), 1) if v is not OUT_OF_RUNNING else "HORS") for u, v in
                sorted(util_par_id.items())},
               ecs_avant, meilleur, active, detour,
               "ACCORD" if ok else "DESACCORD", note))
        return {"ok": ok, "statut": statut, "active": active, "predit": meilleur, "stop": stop,
                "detour": detour}
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception as exc:                                   # noqa: BLE001
            rapport.append("config %d : disposeRunner a leve (%s)" % (idx, exc))


# Six geometries. Elles ne sont PAS aleatoires : chacune place les trois clones a des distances
# de chemin DIFFERENTES de mon unite, et l'ordre de la LISTE (donc l'ordre d'iteration ECS) est
# volontairement DECORRELE de la proximite -- c'est ce qui rend la configuration discriminante.
#
# ⚠ CES COORDONNEES SONT CELLES DE `MC1_67`, ET RIEN NE LE DISAIT. Les ecrire en dur a fige le
# probe sur UN board, alors que la discipline du depot exige DEUX couples (board, seed) des qu'une
# mecanique touche a la geometrie (#10022-r7). Elles restent ici comme le montage HISTORIQUE --
# celui qui a rendu les 5/5 de la case-doc -- et tout autre board passe par `geometries_derivees`.
GEOMETRIES = [
    ([(6, 8), (6, 7), (2, 6)], (1, 0)),
    ([(2, 6), (6, 8), (6, 7)], (1, 0)),
    ([(6, 8), (2, 5), (5, 8)], (1, 1)),
    ([(5, 8), (6, 7), (3, 5)], (2, 0)),
    ([(6, 6), (4, 5), (6, 8)], (1, 0)),
    ([(6, 7), (3, 6), (6, 8)], (0, 1)),
]

#: Le board dont `GEOMETRIES` porte les coordonnees -- LU nulle part ailleurs, donc ecrit ici.
BOARD_DES_GEOMETRIES_FIGEES = "MC1_67"


def geometries_derivees(board_obj, n=6):
    """`n` configurations DERIVEES du board, au lieu de coordonnees ecrites a la main.

    Le critere est le meme que celui des geometries figees, mais il est desormais EXECUTABLE :
    trois clones a des `pathCount` DEUX A DEUX DISTINCTS depuis ma tuile (sinon l'argmax est
    ex-aequo et la configuration ne departage rien), et l'ordre de la LISTE decorrele de la
    proximite (sinon la configuration est DEGENEREE et le probe l'ecarte de lui-meme).

    Le `pathCount` vient de `ignore_terrain_pathfinder.get_path_node_counts` -- le mirror deja
    confronte de `IPathfinders.GetPath(PathfinderType.IgnoreTerrain, ...)`, donc la MEME grandeur
    que celle dont on teste la prediction. On ne devine aucune distance.

    Rend `[(places_ia, place_moi), ...]`, ou `[]` si le board ne porte pas la configuration (ce qui
    est un resultat, pas une panne : l'appelant le DIT)."""
    tuiles = sorted(board_obj.by_id)
    marchables = [t for t in tuiles if board_obj.walkable(t)]
    if len(marchables) < 8:
        return []
    out, vus = [], set()
    #: On balaie des ANCRES espacees plutot que la premiere tuile venue : deux ancres voisines
    #: donneraient deux configurations quasi identiques, donc six mesures pour une seule geometrie.
    pas = max(1, len(marchables) // (n + 2))
    for k in range(0, len(marchables), pas):
        if len(out) >= n:
            break
        t_moi = marchables[k]
        moi = board_obj.coord(t_moi)
        comptes = get_path_node_counts(board_obj, t_moi, {})
        #: `count` DISTINCTS deux a deux, et assez loin pour que l'ordre puisse etre decorrele.
        par_compte = {}
        for t, c in comptes.items():
            if t != t_moi and board_obj.walkable(t) and c >= 2:
                par_compte.setdefault(int(c), t)
        if len(par_compte) < 3:
            continue
        cs = sorted(par_compte)
        choix = [par_compte[cs[len(cs) // 6]], par_compte[cs[len(cs) // 2]],
                 par_compte[cs[-1 - len(cs) // 6]]]
        if len(set(choix)) < 3:
            continue
        places = [board_obj.coord(t) for t in choix]
        #: DECORRELATION : le plus PROCHE ne doit pas etre en tete de liste (l'ordre de la liste
        #: commande l'ordre d'iteration ECS, et une tete deja optimale rend la config degeneree).
        places = [places[1], places[2], places[0]] if (len(out) % 2 == 0) else \
                 [places[2], places[0], places[1]]
        cle = (tuple(places), moi)
        if cle in vus or moi in places:
            continue
        vus.add(cle)
        out.append((places, moi))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--configs", type=int, default=len(GEOMETRIES))
    ap.add_argument("--deriver", action="store_true",
                    help="DERIVER les geometries du boardGraph meme sur le board historique "
                         "(controle : les deux modes doivent conclure pareil).")
    ap.add_argument("--randomize", action="store_true",
                    help="BRAS NEGATIF : monte les runners depuis un seed BC a "
                         "`RandomizeAiInput = True`. On ATTEND alors des DESACCORDS -- l'ordre "
                         "ne doit plus suivre la geometrie (tirage uniforme de "
                         "`RandomGroupOperation`). Un VERT ici REFUTERAIT #10022-r1.")
    a = ap.parse_args(argv)

    try:
        sid = _resolve_session()
    except Exception as exc:                                       # noqa: BLE001
        print("[10022-r3-live] NON MESURE : session Frida introuvable (%s) -- rc 2" % exc)
        return 2
    if sid is None:
        print("[10022-r3-live] NON MESURE : aucune session running -- rc 2")
        return 2
    # ---------------------------------------------------------------- quelles geometries ?
    #: Les coordonnees figees sont celles de `MC1_67` : sur tout autre board elles designeraient des
    #: tuiles quelconques (voire hors plateau), et le probe mesurerait une geometrie qu'il n'a pas
    #: choisie. On DERIVE alors, depuis le `boardGraph` d'un build SONDE.
    geoms, origine_geoms = GEOMETRIES[:a.configs], "FIGEES (montage historique de %s)" % (
        BOARD_DES_GEOMETRIES_FIGEES,)
    if a.board != BOARD_DES_GEOMETRIES_FIGEES or a.deriver:
        sf = ROOT / "logs" / ("_probe10022r3-sonde-%d.json" % os.getpid())
        rid, err = build(a.seed, a.board, [], None, sf)
        if rid is None:
            print("[10022-r3-live] NON MESURE : build SONDE KO sur %s (%s) -- rc 2"
                  % (a.board, (err or "")[-400:]))
            return 2
        try:
            bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
        finally:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        if not bg.get("tiles"):
            print("[10022-r3-live] NON MESURE : boardGraph SONDE vide sur %s -- rc 2" % a.board)
            return 2
        geoms = geometries_derivees(Board(bg["tiles"], adjacency="native_sym"), a.configs)
        origine_geoms = "DERIVEES du boardGraph de %s" % a.board
        if not geoms:
            print("[10022-r3-live] NON MESURE : %s ne porte aucune configuration a trois "
                  "`pathCount` distincts -- ce board ne peut rien departager. -- rc 2" % a.board)
            return 2
    print("[10022-r3-live] geometries : %s -- %d configuration(s)" % (origine_geoms, len(geoms)))

    seed_bc = None
    if a.randomize:
        try:
            seed_bc = seed_bc_randomise()
        except Exception as exc:                                   # noqa: BLE001
            print("[10022-r3-live] NON MESURE : bras negatif impossible (%s) -- rc 2" % exc)
            return 2
        print("[10022-r3-live] BRAS NEGATIF : seed BC a RandomizeAiInput=True (%s)" % seed_bc.name)
    print("[10022-r3-live] session=%s board=%s seed=%d" % (sid, a.board, a.seed))

    rapport, resultats = [], []
    for i, (places, moi) in enumerate(geoms, 1):
        t0 = time.time()
        r = une_config(sid, a.seed, a.board, places, moi, i, rapport, seed_bc=seed_bc)
        if r is not None:
            resultats.append(r)
        print("  ... config %d en %.0f s" % (i, time.time() - t0))

    print("")
    for l in rapport:
        print("[10022-r3-live] " + l)
    print("")

    # Bras POSITIF : seules les configurations dont on a MESURE l'ordre ECS et qui en different
    # comptent. Bras NEGATIF : le critere porte sur le DESACCORD, que l'ECS soit mesure ou non --
    # une geometrie qui ne commande plus se voit sans lui.
    if a.randomize:
        discriminantes = [r for r in resultats if r["statut"] != "DEGENERE"]
    else:
        discriminantes = [r for r in resultats if r["statut"] == "DISCRIMINANT"]
    accords = [r for r in discriminantes if r["ok"]]
    inconnues = len([r for r in resultats if r["statut"] == "ECS_INCONNU"])
    detours = [r.get("detour", 0) for r in resultats]
    print("[10022-r3-live] BILAN : %d config(s) mesuree(s), %d retenue(s), %d accord(s), "
          "%d a ECS non mesure" % (len(resultats), len(discriminantes), len(accords), inconnues))
    print("[10022-r3-live] DETOUR exerce (max `pathCount - hexDist - 1`) : %s ; sur %d config(s) "
          "a detour > 0. %s"
          % (max(detours) if detours else "n/a", len([d for d in detours if d > 0]),
             "L'elagage 1 est EXERCE." if any(d > 0 for d in detours) else
             "L'elagage 1 n'est PAS exerce ici : sur ce board tout chemin vaut la distance hex, "
             "donc ce couple ne dit RIEN de cette branche."))

    if a.randomize:
        # BRAS NEGATIF : le critere s'INVERSE. Un accord parfait ici refuterait #10022-r1.
        if not discriminantes:
            print("[10022-r3-live] ROUGE : bras negatif sans configuration discriminante -- il ne "
                  "peut RIEN refuter, donc il n'atteste rien non plus.")
            return 1
        if len(accords) == len(discriminantes):
            print("[10022-r3-live] ROUGE : bras negatif en ACCORD PARFAIT (%d/%d). Avec "
                  "`RandomizeAiInput = True`, `AiControl$$GetAi` devrait rendre "
                  "`WithSomeRandomnessStrategy` (tirage uniforme, INDEPENDANT des positions). Que "
                  "la geometrie commande quand meme REFUTE que ce champ pilote l'etage -- "
                  "re-examiner #10022-r1." % (len(accords), len(discriminantes)))
            return 1
        print("[10022-r3-live] VERT (bras negatif) : %d desaccord(s) sur %d discriminante(s) -- "
              "avec `RandomizeAiInput = True` la geometrie ne commande PLUS. Le champ pilote donc "
              "bien le choix de strategie : la CAUSALITE de #10022-r1 est etablie, pas seulement "
              "sa correlation." % (len(discriminantes) - len(accords), len(discriminantes)))
        return 0

    if not discriminantes:
        print("[10022-r3-live] ROUGE : AUCUNE configuration discriminante. Une serie entierement "
              "degeneree (predit == premier de l'ordre d'iteration ECS) ne prouve RIEN -- c'est un "
              "echec de MONTAGE, pas un succes. Deplacer les unites.")
        return 1
    if len(accords) != len(discriminantes):
        print("[10022-r3-live] ROUGE : %d desaccord(s) sur %d configuration(s) discriminante(s)."
              % (len(discriminantes) - len(accords), len(discriminantes)))
        return 1
    print("[10022-r3-live] VERT : l'ordre d'activation suit la GEOMETRIE et le port le predit sur "
          "%d configuration(s) discriminante(s) -> (a) `AiControl.<+0x70>` est FAUX en live "
          "(c'est `DefaultPlayerStrategy`, pas le tirage uniforme), (b) le bucket 6 est bien ce "
          "qui departage." % len(discriminantes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
