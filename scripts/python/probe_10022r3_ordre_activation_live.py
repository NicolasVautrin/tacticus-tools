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
from rl_collect_batch import _resolve_session, _rpc, PLAYER_ID_HUMAN       # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.pathfinding.ignore_terrain_pathfinder import (        # noqa: E402
    get_path_node_counts)
from engine.utilities.base import OUT_OF_RUNNING                           # noqa: E402
from engine.utilities.unit_picker import ShortestPathToEnemyUtility        # noqa: E402
from engine.entities.traits.unit_trait import (                            # noqa: E402
    UnitTrait, entity_trait_names, has_any_trait)

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


#: MODE MULTI-HEX (#10022-r7) -- le SEUL porteur d'empreinte du jeu est un BOSS, et son empreinte
#: vient du BOARD (`BossPlatforms`), pas de l'unite : `SetupGameOperation$$AddBossUnit` est la seule
#: voie qui pose un porteur sur une LISTE de tuiles, `AddPredefinedUnits` n'en pose qu'UNE (mesure
#: #10018-r1). Le boss entre donc cote JOUEUR, comme CIBLE des clones IA -- le mettre du cote de
#: l'IA casserait la neutralisation des buckets (`bucket 1 = PreferNonBoss` departagerait avant le 6).
#: Deux porteurs mesures, l'un 7-hex l'autre 3-hex. `deathBossMortarion` porte une aura de degats
#: (`ContagionsOfNurgle`) qui TUE au montage tout clone place a portee -- mesure #10022-r7 : le
#: clone A ressortait `alive = false` du `decisionView` INITIAL, avant toute activation, et
#: `--hp-target` ne le sauvait pas. `admecBossBelisarius` (3 hex, board `GB_Belisarius_01`, la voie
#: mesuree par #10018-r1) n'en porte pas.
MULTIHEX_PORTEURS = {
    "belisarius": {"boss": "admecBossBelisarius", "board": "GB_Belisarius_01",
                   "bouche_trou": "admecMarshall"},
    "mortarion": {"boss": "deathBossMortarion", "board": "GB_Mortarion_05",
                  "bouche_trou": "admecMarshall"},
}
MULTIHEX = MULTIHEX_PORTEURS["belisarius"]


def seed_bc_bossunit(dest, unit_id):
    """Copie du seed BC partage avec `BossUnit` renseigne cote HUMAIN. N'ECRIT JAMAIS le partage."""
    import copy
    bc = copy.deepcopy(json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8")))
    bc["BossUnit"] = {"Id": PLAYER_ID_HUMAN, "UnitId": unit_id, "Health": None,
                      "RemainingHealth": None, "Modifiers": []}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(bc), encoding="utf-8")
    return dest


def build(seed, board, places_ia, place_moi, state_file, seed_bc=None, p_units=None, extra=None):
    """`rl_duel build` avec placements EXACTS des deux camps. `--a-place` sort l'unite de
    `BC.PredefinedUnits` et la pose par `AddUnitMessage` sur la tuile demandee : c'est ce qui
    permet de faire varier la geometrie SANS consommer l'action d'une unite (un `act move` la
    marquerait comme ayant bouge et changerait ce qu'on mesure)."""
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state_file), "--no-ai",
            "--p-units", p_units or CLONE,
            "--a-units", ",".join([CLONE] * max(1, len(places_ia)))] + list(extra or [])
    #: `place_moi is None` = build SONDE : on ne veut que le `boardGraph` (pour DERIVER les
    #: geometries), donc aucun placement -- et donc aucun refus possible d'`AddUnitOperation`.
    if isinstance(place_moi, list):
        #: plusieurs unites a MOI (volet Steppable) : `[(unitId, (col,row)), ...]`
        for uid, c in place_moi:
            argv += ["--place", "%s:%d,%d" % (uid, c[0], c[1])]
    elif place_moi is not None:
        argv += ["--place", "%s:%d,%d" % (p_units or CLONE, place_moi[0], place_moi[1])]
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
    """`{unitId: (mainTile, team)}` depuis `decisionView`, plus `toActivate` (l'ORDRE D'ITERATION
    ECS -- l'ENTREE du picker, jamais sa sortie) et l'EMPREINTE par unite.

    ⚠ **LA MAIN TILE EST `feet[0]`, PAS `pos`** -- et ce site lisait `pos`. Deux lectures le
    disent, et elles concordent :
      * `IdunBattle.Entities.EntityExtensions$$GetMainTileId`, 2e branche : sur une entite a PIEDS,
        il prend litteralement `set[0]` de l'`OrderedSet` du composant et RECURSE ;
      * `runner/snapshot.py::_load_feet` documente que `decisionView.units[].pos` est le DERNIER
        pied projete. MESURE sur `deathBossMortarion` : `feet = [(4,8), ..., (3,8)]` et
        `pos = (3,8)` -- le dernier, pas le premier.
    Sur une unite MONO-hex les deux coincident (c'est tout ce que le montage historique portait),
    donc la faute etait INVISIBLE tant qu'aucune unite multi-hex n'entrait. Repli sur `pos` quand
    le canal `feet` est muet : c'est une DEGRADATION nommee, exacte en mono-hex."""
    dv = _r(sid, "decisionView", {"runnerId": rid}, 90) or {}
    par_id, empreintes, vivants_dv, owners = {}, {}, set(), {}
    for u in (dv.get("units") or []):
        feet = [(int(f["col"]), int(f["row"])) for f in (u.get("feet") or [])
                if isinstance(f, dict) and f.get("col") is not None]
        p = u.get("pos") or {}
        pos = (int(p["col"]), int(p["row"])) if p.get("col") is not None else None
        main = feet[0] if feet else pos
        if main is None:
            continue
        uid = int(u["id"])
        par_id[uid] = (main, int(u.get("team") or 0))
        empreintes[uid] = feet or [main]
        owners[uid] = u.get("owner")
        if u.get("alive") is not False:
            vivants_dv.add(uid)
    #: ⚠ LES DEUX ROLES N'ONT PAS LE MEME FILTRE, ET C'EST LU. Un CANDIDAT doit etre vivant
    #: (`AnAiGroupOperator$$GetValidUnits`), un ENNEMI n'a pas a l'etre :
    #: `StateExtensions$$GetAllEnemyUnitsOfPlayer` ne retient que DEUX conditions -- team differente
    #: et pas `UnitTrait.Steppable` (0x1b) -- et aucune ne porte sur la vie. `par_id` garde donc les
    #: cadavres (ils comptent comme cibles) et `vivants_dv` restreint les CANDIDATS.
    return par_id, list(dv.get("toActivate") or []), dv, empreintes, vivants_dv, owners


#: `UnitTrait.Steppable` (0x1b = 27) -- LE SEUL filtre de
#: `IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfPlayer`, avec la difference de team.
#: Le `decisionView` ne publie PAS les traits (cles mesurees : `abilities, alive, ctrl,
#: defeatedByMelee, effects, feet, hasAction, hp, id, killerId, owner, parentId, parentMeasured,
#: pos, ranged, team, visualId`) : on les lit au gameconfig par le `visualId`, comme le fait deja
#: la face DECISION (`entity_trait_names`).
_STEPPABLE = UnitTrait.Steppable


def est_steppable(visual_id) -> bool:
    """`BaseUnitComponent$$HasTrait(u, 0x1b)`. Sans `visualId`, on repond NON -- une NON-MESURE ne
    doit jamais RETIRER un ennemi que le natif garde (degradation PERMISSIVE, jamais un filtre
    invente)."""
    if not visual_id:
        return False
    return has_any_trait(entity_trait_names(None, str(visual_id)), (_STEPPABLE.name,))


def predire(board_obj, par_id, ids_ia, team_ia, steppables=()):
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
        #: `StateExtensions$$GetAllEnemyUnitsOfPlayer`, LU verbatim : team DIFFERENTE **et** pas
        #: `UnitTrait.Steppable`. Ce second terme manquait -- invisible tant qu'aucun porteur
        #: Steppable n'entrait au montage (aucun des 35 clones des couples historiques).
        mien = par_id[uid][1]
        return [o for o, (_p, t) in par_id.items() if t != mien and o not in steppables]

    def path_node_count(_unit, frm, to):
        tid = idof.get(to)
        return None if tid is None else counts_depuis(frm).get(tid)

    return {uid: util.evaluate_unit(uid, main_tile_of=main_tile_of, enemies_of=enemies_of,
                                    hex_distance=lambda a, b: hexgeo.distance(a, b),
                                    path_node_count=path_node_count)
            for uid in ids_ia}


def ecart_main_vs_empreinte(board_obj, feet, occupants) -> dict:
    """`{pathCount(q -> main) - min_f pathCount(q -> f)}` -> nombre de tuiles, pour l'empreinte
    donnee. **C'est la mesure qui dit si l'axe MAIN TILE / FOOTPRINT est OBSERVABLE.**

    Il ne peut valoir que `0` ou `1` des que la main tile est ADJACENTE a un pied de coût minimal
    -- ce que toute empreinte du jeu garantit (7-hex = centre + ses six voisins ; 3-hex = triangle
    compact). Or un basculement STRICT de l'argmax exigerait deux unites `A`, `B` avec
    `d_main(A) < d_main(B)` ET `d_emp(A) > d_emp(B)`, c'est-a-dire `d_main(B) - 1 < d_main(A) <
    d_main(B)` : IMPOSSIBLE en entiers. L'ordre d'activation ne peut donc PAS distinguer les deux
    lectures -- c'est un resultat, pas un echec de montage, et il est RE-DERIVE ici plutot que
    suppose."""
    idof = {(t["col"], t["row"]): t["id"] for t in board_obj.by_id.values()}
    tid_main = idof.get(feet[0])
    if tid_main is None:
        return {}
    c_main = get_path_node_counts(board_obj, tid_main, occupants)
    c_emp = {}
    for f in feet:
        tf = idof.get(f)
        if tf is None:
            continue
        for t, n in get_path_node_counts(board_obj, tf, occupants).items():
            if t not in c_emp or n < c_emp[t]:
                c_emp[t] = n
    hist = {}
    for t, n in c_main.items():
        if t in c_emp:
            e = int(n) - int(c_emp[t])
            hist[e] = hist.get(e, 0) + 1
    return hist


def geometries_multihex(board_obj, feet, pos_dv, occupants, n=4):
    """Placements qui DISCRIMINENT `GetMainTile` (= `feet[0]`) de `pos` (= le DERNIER pied projete).

    C'est l'axe multi-hex REELLEMENT observable par l'ordre d'activation : la lecture
    MAIN-TILE / FOOTPRINT ne l'est pas (`ecart_main_vs_empreinte` le demontre), mais `pos` peut
    etre a distance 2 de `feet[0]` sur une empreinte 7-hex -- deux pieds opposes -- donc un
    basculement STRICT y est possible.

    On cherche deux clones `A`, `B` tels que `cA_main < cB_main` ET `cA_pos > cB_pos`, plus un
    troisieme strictement plus LOIN dans les DEUX lectures (il ne doit jamais gagner). Le
    `pathCount` vient du meme mirror que celui qu'on teste ; aucune distance n'est devinee."""
    idof = {(t["col"], t["row"]): t["id"] for t in board_obj.by_id.values()}
    if feet[0] not in idof or pos_dv not in idof:
        return []
    c_main = get_path_node_counts(board_obj, idof[feet[0]], occupants)
    c_pos = get_path_node_counts(board_obj, idof[pos_dv], occupants)
    libres = [t for t in sorted(board_obj.by_id)
              if board_obj.walkable(t) and board_obj.coord(t) not in set(feet)
              and t in c_main and t in c_pos]
    out = []
    #: Les DEUX sens de la paire. Ne balayer que `libres[i+1:]` testait `c_main[ta] < c_main[tb]`
    #: pour le seul ordre des IDS de tuile, donc ratait tout couple dont le discriminant vit dans
    #: l'autre sens -- un montage muet qui se serait lu « ce board ne discrimine pas ».
    for ta in libres:
        if len(out) >= n:
            break
        for tb in libres:
            if tb == ta:
                continue
            if not (c_main[ta] < c_main[tb] and c_pos[ta] > c_pos[tb]):
                continue
            loin = [t for t in libres
                    if c_main[t] > max(c_main[ta], c_main[tb])
                    and c_pos[t] > max(c_pos[ta], c_pos[tb])]
            if not loin:
                continue
            tc = loin[len(loin) // 2]
            places = [board_obj.coord(tb), board_obj.coord(tc), board_obj.coord(ta)]
            out.append((places, None,
                        {"A": (board_obj.coord(ta), c_main[ta], c_pos[ta]),
                         "B": (board_obj.coord(tb), c_main[tb], c_pos[tb]),
                         "C": (board_obj.coord(tc), c_main[tc], c_pos[tc])}))
            break
    return out


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

def une_config(sid, seed, board_id, places_ia, place_moi, idx, rapport, seed_bc=None,
               p_units=None, extra=None):
    state_file = ROOT / "logs" / ("_probe10022r3-%d-%d.json" % (os.getpid(), idx))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid, err = build(seed, board_id, places_ia, place_moi, state_file, seed_bc=seed_bc,
                     p_units=p_units, extra=extra)
    if rid is None:
        rapport.append("config %d : BUILD ECHOUE -- %s" % (idx, (err or "")[-400:]))
        return None
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
        if not bg.get("tiles"):
            rapport.append("config %d : boardGraph VIDE -- non mesure" % idx)
            return None
        board_obj = Board(bg["tiles"], adjacency="native_sym")
        par_id, to_activate, _dv, empreintes, vivants_dv, owners = positions_et_teams(sid, rid)
        teams = {t for (_p, t) in par_id.values()}
        if len(teams) < 2:
            rapport.append("config %d : une seule team vue (%r) -- non mesure" % (idx, teams))
            return None
        # ⚠ LA TEAM IA SE DERIVE DU JOUEUR COURANT, PAS DE LA MAJORITE. Le critere d'avant
        # (`max(comptes)`) supposait que mon roster tienne en UNE unite ; il devient INDETERMINE
        # des que les deux camps ont le meme effectif -- exactement le montage du volet Steppable
        # (2 contre 2), ou il a designe MA team et fait predire sur les mauvaises unites (mesure
        # #10022-r7). Le `decisionView` est lu AVANT le `endturn`, donc `currentPlayer` est MOI.
        moi = _dv.get("currentPlayer")
        ia = {owners[u] for u in par_id if owners.get(u) is not None and owners[u] != moi}
        if len(ia) == 1:
            proprio_ia = next(iter(ia))
            team_ia = next(t for u, (_p, t) in par_id.items() if owners.get(u) == proprio_ia)
        else:
            comptes = {}
            for _uid, (_p, t) in par_id.items():
                comptes[t] = comptes.get(t, 0) + 1
            team_ia = max(comptes, key=lambda t: comptes[t])
            rapport.append("config %d : `currentPlayer` ne separe pas les camps (%r) -- repli sur "
                           "la MAJORITE, qui est indetermine a effectifs egaux" % (idx, ia))
        #: CANDIDATS = les unites de la team IA qui sont VIVANTES (cf. positions_et_teams).
        ids_ia = sorted([u for u, (_p, t) in par_id.items() if t == team_ia and u in vivants_dv])
        if len(ids_ia) < 2:
            rapport.append("config %d : moins de 2 unites IA (%r) -- rien a departager"
                           % (idx, ids_ia))
            return None

        steppables = {int(u["id"]) for u in (_dv.get("units") or [])
                      if est_steppable(u.get("visualId"))}
        util_par_id = predire(board_obj, par_id, ids_ia, team_ia, steppables)
        vivants = {u: v for u, v in util_par_id.items() if v is not OUT_OF_RUNNING}
        if not vivants:
            rapport.append("config %d : toutes les utilites sont HORS COURSE -- non mesure" % idx)
            return None

        active, to_activate_avant, stop = premiere_activation(sid, rid)
        ecs_avant = [u for u in (to_activate_avant or to_activate) if u in vivants]
        # ⚠ L'ARGMAX SE PREND SUR L'ENTREE DU PICKER, PAS SUR TOUTE LA TEAM. Le natif choisit dans
        # `AnAiGroupOperator$$GetValidUnits` ; une unite hors de cet ensemble ne peut PAS etre
        # activee, donc la predire est une faute de HARNAIS et le desaccord qui en sort n'accuse
        # rien du port. MESURE qui l'a montre (#10022-r7) : sur le montage multi-hex, un clone
        # place a portee de l'aura `ContagionsOfNurgle` de Mortarion arrivait MORT (`alive=false`)
        # -- il gardait une utilite (sa position est publiee) et sortait argmax, pendant que le
        # picker ne voyait que les deux autres. Trois DESACCORDS, zero faute du port.
        # Ex-aequo tranche par l'ordre d'iteration ECS (comparaison STRICTE `>` du natif dans
        # `CalculateUtilitiesForCasesEnumerated` : le PREMIER a atteindre le max garde `best`).
        ordre_ecs = ecs_avant or [u for u in to_activate if u in vivants] or sorted(vivants)
        meilleur = None
        for u in ordre_ecs:
            if meilleur is None or vivants[u] > vivants[meilleur]:
                meilleur = u
        hors_picker = sorted(u for u in vivants if ecs_avant and u not in ecs_avant)
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
            "config %d : places=%s | utilites=%s | ECS=%s | hors_picker=%s | predit=%s | "
            "active=%s | detour=%d | %s%s"
            % (idx, places_ia,
               {u: (round(float(v), 1) if v is not OUT_OF_RUNNING else "HORS") for u, v in
                sorted(util_par_id.items())},
               ecs_avant, hors_picker, meilleur, active, detour,
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


#: Porteur `UnitTrait.Steppable` MONTABLE (`kind = npc`, entre par `--explicit-stats`). Les cinq
#: familles porteuses du gameconfig sont `powup*`, `LootObj_*` (npc) et deux summons
#: (`genesSmnDecoy`, `astarSmnHaywireMine`) -- les summons exigeraient leur summoner, les npc non.
STEPPABLE_UNIT = "powupArmor"


def volet_steppable(sid, a) -> int:
    """AXE (c) de #10022-r7 : `GetAllEnemyUnitsOfPlayer` n'ecarte QUE `UnitTrait.Steppable`.

    Le filtre est LU (`StateExtensions$$GetAllEnemyUnitsOfPlayer` : team differente **et**
    `!HasTrait(0x1b)`), jamais mesure -- aucun porteur Steppable n'entrait dans les montages
    historiques, qui n'alignaient que des clones. On en pose un DANS MON CAMP, pres d'un clone IA,
    et on regarde laquelle des DEUX predictions le natif suit :

      * FILTREE (la lecture native) : le powup ne compte pas, l'argmax ne depend que du vrai
        ennemi ;
      * NAIVE (sans le filtre) : le clone le plus proche du powup gagne.

    Le probe REFUSE de conclure si les deux predictions coincident -- ce serait un vert vide."""
    board_id, seed = a.board, a.seed
    extra = ["--explicit-stats", STEPPABLE_UNIT]
    sonde = ROOT / "logs" / ("_probe10022r7-stsonde-%d.json" % os.getpid())
    rid, err = build(seed, board_id, [], None, sonde, p_units=CLONE + "," + STEPPABLE_UNIT,
                     extra=extra)
    if rid is None:
        print("[10022-r7-steppable] NON MESURE : build SONDE KO (%s) -- rc 2" % (err or "")[-500:])
        return 2
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    if not bg.get("tiles"):
        print("[10022-r7-steppable] NON MESURE : boardGraph SONDE vide -- rc 2")
        return 2
    b = Board(bg["tiles"], adjacency="native_sym")
    if not est_steppable(STEPPABLE_UNIT):
        print("[10022-r7-steppable] NON MESURE : `%s` ne porte plus `Steppable` au gameconfig -- "
              "le montage n'a plus de porteur. -- rc 2" % STEPPABLE_UNIT)
        return 2

    marchables = [t for t in sorted(b.by_id) if b.walkable(t)]
    if len(marchables) < 10:
        print("[10022-r7-steppable] NON MESURE : board trop petit -- rc 2")
        return 2
    #: Le VRAI ennemi loin, le powup pres d'un clone : `t_vrai` a un bout, `t_pow` a l'autre.
    t_vrai, t_pow = marchables[0], marchables[-1]
    c_vrai = get_path_node_counts(b, t_vrai, {})
    c_pow = get_path_node_counts(b, t_pow, {})
    cands = [t for t in marchables if t in c_vrai and t in c_pow and t not in (t_vrai, t_pow)]
    #: On veut trois clones tels que l'argmax FILTRE (min sur `c_vrai`) et l'argmax NAIF
    #: (min sur `min(c_vrai, c_pow)`) DESIGNENT DES UNITES DIFFERENTES.
    #: DEUX clones suffisent -- le picker n'a besoin que de deux candidats pour departager, et
    #: exiger un troisieme « strictement plus loin dans les DEUX lectures » vidait la recherche
    #: (mesure : 0 triplet sur `MC1_67`). Moins de contraintes, meme pouvoir discriminant.
    trouve = None
    for ta in cands:
        for tb in cands:
            if tb == ta:
                continue
            # A gagne sous FILTRE (plus pres du VRAI ennemi), B gagne sous NAIF (colle au powup).
            if (c_vrai[ta] < c_vrai[tb]
                    and min(c_vrai[tb], c_pow[tb]) < min(c_vrai[ta], c_pow[ta])):
                trouve = (ta, tb)
                break
        if trouve:
            break
    if not trouve:
        print("[10022-r7-steppable] NON MESURE : aucun couple ne separe la prediction FILTREE de "
              "la NAIVE sur %s -- le montage ne discriminerait rien. -- rc 2" % board_id)
        return 2
    ta, tb = trouve
    #: B EN TETE de la liste : l'ordre des `--a-place` commande l'ordre d'iteration ECS, et le
    #: probe ECARTE toute configuration ou le predit est deja `ECS[0]` (regime degenere).
    places = [b.coord(tb), b.coord(ta)]
    print("[10022-r7-steppable] board=%s seed=%d | vrai ennemi @%s | %s (Steppable) @%s"
          % (board_id, seed, b.coord(t_vrai), STEPPABLE_UNIT, b.coord(t_pow)))
    print("[10022-r7-steppable] clones : A=%s(vrai=%d,pow=%d) B=%s(vrai=%d,pow=%d) "
          "-- FILTRE predit A, NAIF predirait B"
          % (b.coord(ta), c_vrai[ta], c_pow[ta], b.coord(tb), c_vrai[tb], c_pow[tb]))

    rapport, resultats = [], []
    r = une_config(sid, seed, board_id, places,
                   [(CLONE, b.coord(t_vrai)), (STEPPABLE_UNIT, b.coord(t_pow))], 1, rapport,
                   p_units=CLONE + "," + STEPPABLE_UNIT, extra=extra)
    for l in rapport:
        print("[10022-r7-steppable] " + l)
    if r is None:
        print("[10022-r7-steppable] NON MESURE : la configuration n'a pas ete mesuree -- rc 2")
        return 2
    resultats.append(r)
    if r["statut"] != "DISCRIMINANT":
        print("[10022-r7-steppable] NON MESURE : configuration %s -- rc 2" % r["statut"])
        return 2
    if not r["ok"]:
        print("[10022-r7-steppable] ROUGE : le natif n'a pas suivi la prediction FILTREE. Soit il "
              "COMPTE le porteur `Steppable` (le filtre lu serait faux), soit un autre etage "
              "intervient -- ne rien conclure sans decomposer.")
        return 1
    print("[10022-r7-steppable] VERT : le natif a suivi la prediction qui ECARTE le porteur "
          "`Steppable`, alors que la prediction NAIVE designait une autre unite. Le filtre "
          "`!HasTrait(UnitTrait.Steppable)` de `GetAllEnemyUnitsOfPlayer` est CONFRONTE.")
    return 0


def volet_multihex(sid, a, porteur=None) -> int:
    """AXE (a) de #10022-r7 : une unite MULTI-HEX au bout de la mesure.

    DEUX questions distinctes, et une seule est observable par l'ordre d'activation :

      1. **MAIN TILE vs FOOTPRINT** -- ce qui separe cette utilite de
         `MinDistanceToClosestEnemyUtility` (17). `ecart_main_vs_empreinte` le RE-DERIVE sur
         l'empreinte reellement montee : l'ecart ne prend que les valeurs `0` et `1`, donc aucun
         basculement STRICT de l'argmax n'est possible (il exigerait `d(B)-1 < d(A) < d(B)`).
         **NON OBSERVABLE par cet oracle** -- imprime, jamais rabattu sur un vert.
      2. **MAIN TILE vs `decisionView.pos`** -- observable, elle : `pos` est le DERNIER pied
         projete, a distance 2 de `feet[0]` sur une 7-hex, donc l'argmax peut basculer. C'est la
         lecture que ce probe faisait AVANT (`positions_et_teams`), et c'est elle qu'on confronte.
    """
    P = porteur or MULTIHEX
    sf = ROOT / "logs" / ("_probe10022r7-bc-%d.json" % os.getpid())
    seed_bc = seed_bc_bossunit(sf, P["boss"])
    #: `--hp-target` eleve : MESURE (#10022-r7) -- sans lui, l'aura `ContagionsOfNurgle` de
    #: Mortarion tue les clones places a portee AVANT la premiere activation (`alive = false` des
    #: le `decisionView` initial). Un clone mort garde une position, donc une utilite, mais sort de
    #: `GetValidUnits` : la prediction designe alors une unite que le picker ne voit pas.
    extra = ["--explicit-stats", P["boss"] + ":4", "--hp-target", "500000"]
    os.environ.setdefault("TACTICUS_ALLOW_ROSTER_DEFICIT", "1")
    board_id = P["board"]

    sonde = ROOT / "logs" / ("_probe10022r7-sonde-%d.json" % os.getpid())
    rid, err = build(a.seed, board_id, [], None, sonde, seed_bc=seed_bc,
                     p_units=P["bouche_trou"], extra=extra)
    if rid is None:
        print("[10022-r7-multihex] NON MESURE : build SONDE KO (%s) -- rc 2" % (err or "")[-400:])
        return 2
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
        par_id, _ta, dv, empreintes, _viv, _own = positions_et_teams(sid, rid)
        boss = next((u for u in (dv.get("units") or [])
                     if len(u.get("feet") or []) > 1 and u.get("alive")), None)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    if not bg.get("tiles") or boss is None:
        print("[10022-r7-multihex] NON MESURE : aucune unite MULTI-HEX au montage "
              "(BC.BossUnit non consomme ?) -- rc 2")
        return 2
    board_obj = Board(bg["tiles"], adjacency="native_sym")
    feet = empreintes[int(boss["id"])]
    p = boss.get("pos") or {}
    pos_dv = (int(p["col"]), int(p["row"]))
    #: Les OCCUPANTS reels : `IgnoreTerrainPathfinder$$WeightCost` = `10 + IsFilled(to)`, donc une
    #: tuile occupee COUTE plus cher sans jamais bloquer (`IsValidPathNode` n'a aucun test
    #: d'occupant -- sa signature native n'a meme pas de parametre `unit`). Les passer ici met la
    #: DERIVATION dans le meme regime que la PREDICTION, qui les passe deja.
    idof0 = {(t["col"], t["row"]): t["id"] for t in board_obj.by_id.values()}
    occ = {idof0[f]: int(boss["id"]) for f in feet if f in idof0}
    print("[10022-r7-multihex] boss u%s feet=%d %s | main(feet[0])=%s | pos(dv)=%s"
          % (boss["id"], len(feet), feet, feet[0], pos_dv))

    hist = ecart_main_vs_empreinte(board_obj, feet, occ)
    print("[10022-r7-multihex] AXE 1 -- ecart `pathCount(main) - min pathCount(empreinte)` : %s"
          % sorted(hist.items()))
    if hist and max(hist) <= 1:
        print("[10022-r7-multihex] AXE 1 = NON OBSERVABLE par l'ordre d'activation : l'ecart vaut "
              "0 ou 1 partout, et un basculement STRICT exigerait `d(B)-1 < d(A) < d(B)`. La "
              "distinction MAIN TILE / FOOTPRINT est donc indiscriminable par CET oracle -- pas "
              "par manque de montage, par ARITHMETIQUE.")
    elif hist:
        print("[10022-r7-multihex] AXE 1 : ecart max = %d > 1 -- un basculement EST possible, la "
              "conclusion ci-dessus ne tient pas sur cette empreinte." % max(hist))

    geoms = geometries_multihex(board_obj, feet, pos_dv, occ, a.configs)
    if not geoms:
        print("[10022-r7-multihex] AXE 2 NON MESURE : aucun couple de tuiles ne discrimine "
              "`feet[0]` de `pos` sur ce board -- rc 2")
        return 2
    print("[10022-r7-multihex] AXE 2 -- %d configuration(s) discriminant `feet[0]` de `pos`"
          % len(geoms))

    rapport, resultats = [], []
    for i, (places, _moi, detail) in enumerate(geoms, 1):
        print("  config %d : A=%s(main=%d,pos=%d) B=%s(main=%d,pos=%d) C=%s(main=%d,pos=%d)"
              % (i, detail["A"][0], detail["A"][1], detail["A"][2],
                 detail["B"][0], detail["B"][1], detail["B"][2],
                 detail["C"][0], detail["C"][1], detail["C"][2]))
        r = une_config(sid, a.seed, board_id, places, None, i, rapport, seed_bc=seed_bc,
                       p_units=P["bouche_trou"], extra=extra)
        if r is not None:
            resultats.append(r)
    print("")
    for l in rapport:
        print("[10022-r7-multihex] " + l)
    disc = [r for r in resultats if r["statut"] == "DISCRIMINANT"]
    acc = [r for r in disc if r["ok"]]
    print("")
    print("[10022-r7-multihex] BILAN AXE 2 : %d mesuree(s), %d discriminante(s), %d accord(s)"
          % (len(resultats), len(disc), len(acc)))
    if not disc:
        print("[10022-r7-multihex] ROUGE : aucune configuration discriminante -- echec de montage.")
        return 1
    if len(acc) != len(disc):
        print("[10022-r7-multihex] ROUGE : %d desaccord(s) -- le natif ne lit pas `feet[0]`, ou "
              "un autre etage intervient." % (len(disc) - len(acc)))
        return 1
    print("[10022-r7-multihex] VERT : sur une unite MULTI-HEX, le natif lit bien la MAIN TILE "
          "(`feet[0]`), pas `decisionView.pos` (le DERNIER pied projete).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--configs", type=int, default=len(GEOMETRIES))
    ap.add_argument("--steppable", action="store_true",
                    help="AXE (c) de #10022-r7 : pose un porteur UnitTrait.Steppable dans le "
                         "camp ennemi et confronte le filtre de GetAllEnemyUnitsOfPlayer.")
    ap.add_argument("--multihex", nargs="?", const="belisarius", default=None,
                    choices=sorted(MULTIHEX_PORTEURS),
                    help="AXE (a) de #10022-r7 : monte une unite MULTI-HEX (boss, via "
                         "`BC.BossUnit`) comme CIBLE et confronte la lecture de sa MAIN TILE.")
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
    # ---------------------------------------------------------------- axe MULTI-HEX (#10022-r7)
    if a.steppable:
        return volet_steppable(sid, a)
    if a.multihex:
        return volet_multihex(sid, a, MULTIHEX_PORTEURS[a.multihex])

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
