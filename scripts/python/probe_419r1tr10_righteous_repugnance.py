"""#419-r1-tr10 -- MONTAGE NOMME des sorties de `RighteousRepugnance` (TriggeredAbilityType **1107**)
sur la face ATTACK, et mesure natif contre port.

`IdunBattle.AI.Playbook.Loki.RighteousRepugnancePlaybook.u003CCalculateAttackUtilityInStepsInternal
u003Ed__3$$MoveNext` rend

    GetUtilityValue("RIGHTEOUSREPUGNANCE_AdjacentEnemy")
      * | RighteousRepugnanceAbility.GetAdditionalTargets(dsl)
            .SelectUniqueUnits({Caster = case.Caster, Target = case.Target}, 3) |

ou l'arbre de ciblage vaut

    AdjacentEnemies(Caster@0x48, unique: 1, sel: 3) & AdjacentUnits(Target@0x60, unique: 1, sel: 3)

-- un PRODUIT poids x CARDINAL dont le cardinal est une DOUBLE ADJACENCE (ennemi du caster, adjacent
au caster ET a la cible), et qui ne compte NI le caster NI la cible.

## Les cinq degenerescences que ce montage evite, chacune par un cran DEDIE

  * **un seul cran a count = 1** ne distinguerait pas `poids x count` d'un poids PLAT -> il faut un
    cran a **2** (`n2`) ;
  * **aucun cran a count = 0** ne dirait rien du plancher : `Boltstorm`, de FORME identique, compte
    la cible elle-meme (`op_Addition` avec `Target@0x60`) et vaut donc deja 10 sur une cible isolee.
    Ici le cran `n0` doit rendre **0** ;
  * **un ennemi adjacent a la CIBLE seulement** (`wt`) doit compter pour **0** -- sinon on aurait
    porte `FireOfAbsolution` (le volet `AdjacentUnits(Target)` seul) ;
  * **un ennemi adjacent au CASTER seulement** (`wc`) doit compter pour **0** -- sinon on aurait
    porte le volet `AdjacentEnemies(Caster)` seul ;
  * **un ALLIE adjacent aux deux** (`n1a`) doit compter pour **0** -- c'est le filtre
    `Enemies(Caster@0x48, ..., 3)`, invisible de tout montage 100 % ennemi.

## Le montage

    C  = `adeptMorvenn` << Morvenn Vahl >> (HERO AU POOL), dont `RighteousRepugnance` est le SEUL
         passif ; le montage ATTESTE qu'aucun autre triggered de son `AbilitiesComponent` LIVE n'est
         au registre attack, sinon deux termes se meleraient.
    T  = la cible ennemie, sur une tuile ADJACENTE (au sens NATIF) a celle du caster : c'est la seule
         configuration ou le voisinage COMMUN a deux tuiles, donc la seule qui offre `count = 2`.
    V1, V2 = les deux tuiles du voisinage COMMUN (adjacentes a C ET a T).
    W_T = un voisin natif de T qui n'est PAS voisin de C   -> temoin, ne compte jamais.
    W_C = un voisin natif de C qui n'est PAS voisin de T   -> temoin, ne compte jamais.

## Le balayage -- le caster NE BOUGE PAS, seules les tierces unites se deplacent

    n0  : E1 -> garage, E2 -> garage, A1 -> garage     count 0    terme   0
    wt  : E1 -> W_T                                    count 0    terme   0
    wc  : E1 -> W_C                                    count 0    terme   0
    n1  : E1 -> V1                                     count 1    terme  10
    n1a : A1 -> V2  (l'ALLIE)                          count 1    terme  10
    n2  : A1 -> garage, E2 -> V2                       count 2    terme  20

Deux criteres, et le second ne remplace pas le premier :

  * **accord ABSOLU** `port == natif` a chaque cran -- c'est le seul qui tranche le PLANCHER (un
    port qui compterait la cible, comme `Boltstorm`, serait +10 partout et les DELTAS ne le
    verraient pas) ;
  * **deltas de `natif - port_muted`** d'un cran a l'autre (`port_muted` = le MEME port prive du
    playbook 1107) : `0, 0, +10, 0, +10`. Il reste valide meme si cette paire portait un residu
    constant hors perimetre, ou le critere absolu ne serait plus lisible. Le probe imprime les DEUX.

Le cardinal est RE-DERIVE des positions LIVE avec l'adjacence NATIVE (`battle_query.is_adjacent`,
porte `|delta elevation| < 2`), jamais lu du port -- sinon la mesure ne trancherait plus rien.

## Les contre-epreuves (`--mutants`)

Critere : DEPLACER le port par rapport au port NON MUTE (jamais << s'ecarter du natif >>, qui serait
vrai meme pour un mutant inerte des qu'un residu existe -- piege de #441).

    `flat`         poids plat au lieu du produit      -> mord au cran `n2`
    `target_only`  gate caster retire                 -> mord au cran `wt`
    `caster_only`  gate cible retire                  -> mord au cran `wc`
    `no_camp`      filtre `Enemies(Caster)` retire    -> mord au cran `n1a`
    `plus_target`  `+ Target` de `Boltstorm` ajoute   -> mord PARTOUT (c'est la recopie par analogie
                                                        du voisin de meme FORME, exactement l'erreur
                                                        que ce module ne devait pas commettre)
    `no_elev_gate` `hexgeo.distance == 1` au lieu de `bq.is_adjacent` -> ne mord que si le layout
                   place un TEMOIN (`W_T` ou `W_C`) a distance hex 1 du sujet dont le natif l'ecarte
                   par elevation (`layout['elev_gated']`). Une tuile voisine-hex des DEUX et ecartee
                   par l'elevation serait STRUCTURELLEMENT impossible ici (deux hexs adjacents n'ont
                   que 2 voisins communs, et le layout exige que ces 2-la soient adjacents au sens
                   NATIF) : le seul ancrage possible est donc le temoin. VERT quand le board n'en
                   offre pas = residu NOMME, jamais une preuve.

## NON COUVERT par ce montage

Le regime `count >= 3` (impossible : deux hexs adjacents n'ont que 2 voisins communs), les unites
MULTI-TUILES (`AdjacentTiles` itere `EntityExtensions.IterateTiles`, le port ne connait que la
MainTile), et la face MOVE (`yield Fix64(0)` constant au natif, rien a confronter).

Usage :
    python scripts/python/probe_419r1tr10_righteous_repugnance.py --state-file <ABSOLU> [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr10_righteous_repugnance_live.py`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "adeptMorvenn"         # HERO AU POOL ; `RighteousRepugnance` (1107) est son SEUL passif
ALLY1 = "adeptCanoness"         # A1 -- ami du caster, amene sur le voisinage COMMUN (cran `n1a`)
TARGET = "astraBullgryn"        # T  -- la cible du case
FOE1 = "astraCreed"             # E1 -- ennemi promene sur W_T, W_C puis V1
FOE2 = "astraDreir"             # E2 -- ennemi amene sur V2 (cran `n2`)
ALLIES = (CASTER, ALLY1)
FOES = (TARGET, FOE1, FOE2)

ABILITY = int(TriggeredAbilityType.RighteousRepugnance)       # 1107
WEIGHT_KEY = "RIGHTEOUSREPUGNANCE_AdjacentEnemy"              # = 10 sur ce BC
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 40000                      # personne ne doit mourir : `Health` ET `RemainingHealth` (#438)

# (nom du cran, cardinal ATTENDU) -- pose ICI, en dur, depuis le decompile. Jamais relu du port.
SWEEP = (("n0", 0), ("wt", 0), ("wc", 0), ("n1", 1), ("n1a", 1), ("n2", 2))
MUTANTS = ("flat", "target_only", "caster_only", "no_camp", "plus_target", "no_elev_gate")

def build_args(board: str = BOARD, armor: int | None = None) -> list:
    """`--board <id>` est OBLIGATOIRE (discipline runner) ; il est parametre pour que la
    GENERALISATION se joue sur un autre board sans dupliquer le montage.

    `armor` (`--armor-target`) est le levier STRUCTUREL de la generalisation : il deplace fortement
    la base de `pairUtility` (la prediction de degat) sans toucher AU TERME, dont le corps natif ne
    lit ni stat ni prediction. Un accord qui survit a ce levier n'est pas un accord de circonstance."""
    args = ["--board", board, "--p-units", ",".join(ALLIES), "--a-units", ",".join(FOES),
            "--unit-stat", ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                                    for v in ALLIES + FOES)]
    if armor is not None:
        args += ["--armor-target", str(armor)]
    return args


BUILD_ARGS = build_args()


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def pair_muted(ctx, ab, tgt, tile) -> float:
    """Le MEME port, prive du playbook 1107 : le denominateur commun du critere par DELTAS."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
    if saved is None:
        raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
    try:
        return pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- geometrie

def native_neighbours(t: tuple, cells: set, elev: dict) -> list:
    """Voisins de `t` au sens de `AdjacentTiles` -> `IdunBattle.Core.Services.TileQuery.
    u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : ring-1 hex AVEC la porte `|delta elev| < 2`.
    Prendre `hexgeo.neighbors` NU donnerait des tuiles que le natif ne considere PAS adjacentes
    (mesure #446 sur ce meme board)."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def find_layout(cells: list, elev: dict) -> dict | None:
    """Cherche `(C, T, V1, V2, W_T, W_C, P1..P3)` satisfaisant EXACTEMENT le regime de l'en-tete.

    `C` et `T` sont ADJACENTS au sens natif -- c'est la seule configuration dont le voisinage COMMUN
    a DEUX tuiles, donc la seule qui installe `count = 2` et separe le produit du poids plat."""
    d = hexgeo.distance
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    ordered = sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    best = None
    for c in ordered:
        nc = native_neighbours(c, cs, elev)
        for t in nc:
            nt = native_neighbours(t, cs, elev)
            common = [q for q in nt if q in nc and q != c and q != t]
            wt_only = [q for q in nt if q not in nc and q != c and q != t]
            wc_only = [q for q in nc if q not in nt and q != c and q != t]
            if len(common) < 2 or not wt_only or not wc_only:
                continue
            v1, v2 = common[0], common[1]
            # ⚠ Les temoins sont choisis pour exercer AUSSI la porte d'elevation quand le board
            # l'offre : `W_T` voisin HEX de `C` que le natif n'y considere PAS adjacent (et
            # symetriquement `W_C` vis-a-vis de `T`). C'est le SEUL ancrage par lequel le mutant
            # `no_elev_gate` peut mordre ici -- une tuile `Z` voisine-hex des DEUX et ecartee par
            # l'elevation est STRUCTURELLEMENT impossible : deux hexs adjacents n'ont que 2 voisins
            # communs, et le layout exige deja que ces 2-la soient adjacents au sens NATIF.
            w_t = next((q for q in wt_only if d(q, c) == 1), wt_only[0])
            w_c = next((q for q in wc_only if d(q, t) == 1), wc_only[0])
            gated = (d(w_t, c) == 1) or (d(w_c, t) == 1)
            busy = {c, t, v1, v2, w_t, w_c}
            # Garages : hors du voisinage NATIF de T *et* de C, a distance hex >= 2 des deux, pour
            # qu'aucune tolerance d'elevation ne puisse les y ramener.
            parks = [q for q in cells
                     if q not in busy and d(q, t) >= 2 and d(q, c) >= 2
                     and not bq.is_adjacent(t, q, elev) and not bq.is_adjacent(c, q, elev)]
            if len(parks) < 3:
                continue
            lay = {"C": c, "T": t, "V1": v1, "V2": v2, "W_T": w_t, "W_C": w_c,
                   "P1": parks[0], "P2": parks[1], "P3": parks[2], "elev_gated": gated}
            if gated:
                return lay              # un layout AVEC porte d'elevation exercable prime
            if best is None:
                best = lay
    return best


def find_elev_layout(cells: list, elev: dict) -> dict | None:
    """Layout SEPARE de l'etape `--elev-gate` : le SEUL qui exerce la porte d'elevation.

    ⚠ Il ne peut PAS etre le layout principal, et c'est STRUCTUREL, pas contingent. Deux hexs
    adjacents ont exactement DEUX voisins communs ; le montage principal exige que ces deux-la
    soient adjacents au sens NATIF (c'est ce qui installe `count = 2`), donc il ne reste aucune
    tuile commune que l'elevation puisse ecarter. MESURE : le critere << temoin sous porte
    d'elevation dans le layout principal >> rend **0 hit sur les 779 boards** de `data/boards/`.

    Ici on RELACHE `count = 2` : parmi les deux voisins communs HEX de `C` et `T`, `G` est adjacent
    NATIF aux deux et `Z` ne l'est pas (`|delta elev| >= 2` vis-a-vis de `C` ou de `T`). Un ennemi
    sur `G` compte 1 ; le MEME ennemi sur `Z` compte 0 -- et une adjacence `hexgeo` nue en compterait
    1 dans les DEUX cas. C'est exactement ce que le mutant `no_elev_gate` doit faire mordre."""
    d = hexgeo.distance
    cs = set(cells)
    for c in cells:
        for t in [q for q in hexgeo.neighbors(c[0], c[1])
                  if q in cs and bq.is_adjacent(c, q, elev)]:
            hexcom = [q for q in hexgeo.neighbors(t[0], t[1])
                      if q in cs and d(q, c) == 1 and q != c and q != t]
            good = [q for q in hexcom
                    if bq.is_adjacent(c, q, elev) and bq.is_adjacent(t, q, elev)]
            gated = [q for q in hexcom
                     if not (bq.is_adjacent(c, q, elev) and bq.is_adjacent(t, q, elev))]
            if not good or not gated:
                continue
            g, z = good[0], gated[0]
            busy = {c, t, g, z}
            parks = [q for q in cells
                     if q not in busy and d(q, t) >= 2 and d(q, c) >= 2
                     and not bq.is_adjacent(t, q, elev) and not bq.is_adjacent(c, q, elev)]
            if len(parks) >= 3:
                return {"C": c, "T": t, "G": g, "Z": z,
                        "P1": parks[0], "P2": parks[1], "P3": parks[2]}
    return None


def elev_gate_sweep(sid, rpc, case: dict) -> list[dict]:
    """Etape `--elev-gate` : deux crans sur le layout dedie, `G` (compte 1) puis `Z` (compte 0).

    Le mutant `no_elev_gate` est joue a CHAQUE cran : il doit etre inerte sur `g` et MORDRE de +10
    sur `z` -- c'est la seule mesure du montage qui prouve que la porte `|delta elev| < 2` du natif
    est bien celle que le port applique, et non une adjacence hex nue."""
    cells = sorted(p for p, wk in case["walk"].items()
                   if wk and case["elev"].get(p) is not None)
    lay = find_elev_layout(cells, case["elev"])
    if lay is None:
        raise MontageError("etape elev-gate NON INSTALLEE : ce board n'offre aucun couple (G, Z) "
                           "-- choisir un board qui en a un (le scan offline en donne 8)")
    ids = case["ids"]
    case["layout"] = lay              # `_settle` verifie la NON-derive du caster contre `lay['C']`
    base = {ids["C"]: lay["C"], ids["T"]: lay["T"],
            ids["E1"]: lay["P1"], ids["E2"]: lay["P2"], ids["A1"]: lay["P3"]}
    rows = []
    wanted = dict(base)
    for name, dest, want_count in (("g", lay["G"], 1), ("z", lay["Z"], 0)):
        wanted[ids["E1"]] = dest
        s = _settle(sid, rpc, case, wanted, "elev-" + name)
        got, hits = count_live(s["pos"], ids, case["elev"], s["dv"].get("units") or [],
                               case["myplayer"])
        if got != want_count:
            raise MontageError(f"cran elev-{name} NON INSTALLE : cardinal NATIF re-derive = {got} "
                               f"(attendu {want_count}) -- unites comptees {hits}")
        nat = pair_native(rpc, case["rid"], case["cid"], ids["T"], s["ab"], s["tile"])
        port = pair_port(s["ctx"], s["ab"], ids["T"], s["tile"])
        muted = pair_muted(s["ctx"], s["ab"], ids["T"], s["tile"])
        weight = float(s["ctx"].wt.triggered(WEIGHT_KEY))
        rows.append({"step": "elev-" + name, "count": got, "tile": s["tile"], "dest": dest,
                     "native": nat, "port": port, "muted": muted, "missing": nat - muted,
                     "carried": port - muted, "weight": weight, "expected": weight * got,
                     "mut_no_elev": measure_mutant(s["ctx"], case, ids["T"], s["ab"], s["tile"],
                                                   "no_elev_gate")})
    return rows


def count_live(pos: dict, ids: dict, elev: dict, all_units: list, myplayer) -> tuple:
    """RE-DERIVE le cardinal de `GetAdditionalTargets` des positions LIVE, depuis le DECOMPILE --
    jamais depuis le port.

    = |{ u vivante : u ennemie du caster, `is_adjacent(caster, u)` ET `is_adjacent(target, u)` }|.
    Balaye TOUTES les unites live (pas seulement E1/E2/A1) : une tierce unite qui derivrait dans le
    voisinage commun fausserait le cran sans que rien ne le signale."""
    cp, tp = pos.get(ids["C"]), pos.get(ids["T"])
    if cp is None or tp is None:
        raise MontageError("mesure IMPOSSIBLE : caster ou cible sans position live")
    hits = []
    for u in all_units:
        uid = u.get("id")
        if uid is None or not u.get("alive") or uid in (ids["C"], ids["T"]):
            continue
        if u.get("owner") == myplayer:                 # `Enemies(Caster@0x48, ..., 3)`
            continue
        p = pos.get(uid)
        if p is None:
            continue
        if bq.is_adjacent(cp, p, elev) and bq.is_adjacent(tp, p, elev):
            hits.append(uid)
    return len(hits), hits


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _stage(sid, rpc, rid: int) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for key, vis in (("C", CASTER), ("A1", ALLY1)):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster joueur")
        ids[key] = u["id"]
    for key, vis in (("T", TARGET), ("E1", FOE1), ("E2", FOE2)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1107 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": ids["C"]}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")
    # (b) Aucun AUTRE triggered du caster ne doit etre au registre ATTACK, sinon deux termes se
    #     meleraient et l'accord ne dirait plus lequel est juste.
    import engine.playbook.psyker as PSY
    others = sorted((set(live_ids) & set(PSY.TRIGGERED_ATTACK_PLAYBOOKS)) - {ABILITY})
    if others:
        raise MontageError(f"montage AMBIGU : {CASTER} porte aussi les playbooks attack {others} "
                           f"-- leurs termes se meleraient a celui de {ABILITY}")

    # (c) La geometrie, puis le DRIVE (jamais « bloque par le spawn »).
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = find_layout(cells, elev)
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucune configuration (C,T,V1,V2,W_T,W_C,P1..P3) "
                           "sur ce board -- les six crans ne seraient pas installables")
    return {"rid": rid, "cid": ids["C"], "myplayer": myplayer, "ids": ids, "layout": lay,
            "walk": walk, "elev": elev}


def _settle(sid, rpc, case: dict, wanted: dict, label: str) -> dict:
    """Amene les unites, RE-MESURE la geometrie live, et rend le contexte frais + les positions."""
    if not P124._drive_to(sid, case["rid"], case["walk"], case["elev"], wanted):
        _dv, pos = P124._positions(sid, case["rid"])
        raise MontageError(f"cran {label} NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, case["rid"], case["myplayer"])
    _dv2, pos = P124._positions(sid, case["rid"])
    dv, ctx = _fresh_ctx(rpc, case["rid"], case["cid"])
    case["ctx"], case["dv"] = ctx, dv
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError(f"cran {label} NON INSTALLE : aucune attaque normale sur le caster")
    case["ab"] = ab
    tile = pos.get(case["cid"])
    if tile is None:
        raise MontageError(f"cran {label} NON INSTALLE : le caster n'a pas de position live")
    if tile != case["layout"]["C"]:
        raise MontageError(f"cran {label} NON INSTALLE : le caster a DERIVE en {tile} "
                           f"(attendu {case['layout']['C']}) -- les crans ne seraient plus comparables")
    if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
        raise MontageError(f"cran {label} NON INSTALLE : la tuile d'attaque {tile} n'est pas dans "
                           f"les tuiles d'action de l'oracle -- natif et port ne compareraient pas "
                           f"la meme chose")
    return {"pos": pos, "tile": tile, "ab": ab, "ctx": ctx, "dv": dv}


def sweep(sid, rpc, case: dict, with_mutants: bool = False) -> list[dict]:
    """Le balayage : caster FIXE sur `C`, seules les tierces unites bougent."""
    lay, ids = case["layout"], case["ids"]
    base = {ids["C"]: lay["C"], ids["T"]: lay["T"],
            ids["E1"]: lay["P1"], ids["E2"]: lay["P2"], ids["A1"]: lay["P3"]}
    moves = {"n0": {},
             "wt": {ids["E1"]: lay["W_T"]},
             "wc": {ids["E1"]: lay["W_C"]},
             "n1": {ids["E1"]: lay["V1"]},
             "n1a": {ids["A1"]: lay["V2"]},
             "n2": {ids["A1"]: lay["P3"], ids["E2"]: lay["V2"]}}
    wanted = dict(base)
    rows = []
    for name, want_count in SWEEP:
        wanted.update(moves[name])
        s = _settle(sid, rpc, case, wanted, name)
        got, hits = count_live(s["pos"], ids, case["elev"], s["dv"].get("units") or [],
                               case["myplayer"])
        if got != want_count:
            raise MontageError(f"cran {name} NON INSTALLE : cardinal NATIF re-derive = {got} "
                               f"(attendu {want_count}) -- unites comptees {hits}, "
                               f"positions { {k: s['pos'].get(v) for k, v in ids.items()} }")
        nat = pair_native(rpc, case["rid"], case["cid"], ids["T"], s["ab"], s["tile"])
        port = pair_port(s["ctx"], s["ab"], ids["T"], s["tile"])
        muted = pair_muted(s["ctx"], s["ab"], ids["T"], s["tile"])
        weight = float(s["ctx"].wt.triggered(WEIGHT_KEY))
        if weight <= 0:
            raise MontageError(f"montage NON INSTALLE : le poids {WEIGHT_KEY} vaut {weight} dans le "
                               f"BC servi -- le terme serait nul et la mesure ne trancherait rien")
        row = {"step": name, "count": got, "tile": s["tile"], "native": nat, "port": port,
               "muted": muted, "missing": nat - muted, "carried": port - muted,
               "weight": weight, "expected": weight * got}
        if with_mutants:
            row["mutants"] = {m: measure_mutant(s["ctx"], case, ids["T"], s["ab"], s["tile"], m)
                              for m in MUTANTS}
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- contre-epreuves

def measure_mutant(ctx, case: dict, tgt, ab, tile, mutant: str) -> float:
    """Rend le DEPLACEMENT du port (mutant moins port non mute) sur cette cible et cette tuile.

    ⚠ Le critere est le DEPLACEMENT, JAMAIS l'ecart au natif : si cette paire portait un residu
    hors perimetre, `abs(port - native) > EPS` serait vrai meme pour un mutant parfaitement inerte
    (piege de #441)."""
    import engine.playbook.psyker as PSY
    from engine.playbook import righteous_repugnance as R

    ref = pair_port(ctx, ab, tgt, tile)
    elev = getattr(ctx.scene, "elev_by_pos", None)

    class _Mut(R.RighteousRepugnancePlaybook):
        def calculate_attack_utility_in_steps(self, c, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(c, "scene", None)
            if sc is None:
                return 0.0
            n = _mutant_count(sc, attacker_uid, case_tgt_id, mutant, elev)
            if mutant == "flat":
                n = 1 if n > 0 else 0
            elif mutant == "plus_target":
                n = n + 1
            return float(c.wt.triggered(WEIGHT_KEY)) * n

    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _Mut()
    try:
        return pair_port(ctx, ab, tgt, tile) - ref
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


def _mutant_count(scene, caster_uid, target_uid, mutant: str, elev) -> int:
    """Le cardinal MUTE : chaque variante retire exactement UN gate de l'arbre natif."""
    if caster_uid is None or target_uid is None:
        return 0
    cpos, tpos = scene.pos(caster_uid), scene.pos(target_uid)
    cteam = scene.team(caster_uid)
    if cpos is None or tpos is None or cteam is None:
        return 0
    adj = (lambda a, b: hexgeo.distance(a, b) == 1) if mutant == "no_elev_gate" \
        else (lambda a, b: bq.is_adjacent(a, b, elev))
    n = 0
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or not u.get("alive") or uid in (caster_uid, target_uid):
            continue
        if mutant != "no_camp" and u.get("team") == cteam:
            continue
        p = scene.pos(uid)
        if p is None:
            continue
        if mutant != "target_only" and not adj(cpos, p):
            continue
        if mutant != "caster_only" and not adj(tpos, p):
            continue
        n += 1
    return n


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str], seed: str = SEED) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    import json
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def build_case(sid, rpc, rid: int) -> dict:
    return _stage(sid, rpc, rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--mutants", action="store_true",
                    help="joue aussi les six contre-epreuves (elles doivent MORDRE)")
    ap.add_argument("--board", default=BOARD, help="board id (defaut MC1_67)")
    ap.add_argument("--seed", default=SEED, help="seed du build (defaut 41504)")
    ap.add_argument("--armor-target", type=int, default=None,
                    help="levier structurel de generalisation : deplace la base sans toucher au terme")
    ap.add_argument("--elev-gate", action="store_true",
                    help="joue l'etape dediee a la PORTE D'ELEVATION (layout separe ; exige un "
                         "board offrant un couple (G, Z) -- ex. C1_16)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, build_args(args.board, args.armor_target), args.seed)
    case = build_case(sid, rpc, rid)
    if args.elev_gate:
        print(f"runner {rid} | board {args.board} seed {args.seed} | ETAPE PORTE D'ELEVATION")
        for r in elev_gate_sweep(sid, rpc, case):
            print(f"  [{r['step']:<6}] E1@{r['dest']} count={r['count']} nat={r['native']:.6f} "
                  f"port={r['port']:.6f} d={r['port'] - r['native']:+.9f} "
                  f"terme_port={r['carried']:+.6f} manque={r['missing']:+.6f} | "
                  f"mutant no_elev_gate = {r['mut_no_elev']:+.6f} "
                  f"({'MORD' if abs(r['mut_no_elev']) > EPS else 'inerte'})")
        return 0
    lay = case["layout"]
    print(f"runner {rid} | board {args.board} seed {args.seed} | "
          f"caster u{case['cid']} @ {lay['C']} | cible @ {lay['T']}")
    print(f"  layout V1={lay['V1']} V2={lay['V2']} W_T={lay['W_T']} W_C={lay['W_C']} "
          f"porte_elevation_exercee={lay.get('elev_gated')}")
    rows = sweep(sid, rpc, case, with_mutants=args.mutants)
    weight = float(case["ctx"].wt.triggered(WEIGHT_KEY))
    print(f"  poids {WEIGHT_KEY} = {weight}")
    prev = None
    for r in rows:
        dm = "" if prev is None else f" dManque={r['missing'] - prev['missing']:+.6f}"
        print(f"  [{r['step']:<4}] count={r['count']} nat={r['native']:.6f} port={r['port']:.6f} "
              f"d={r['port'] - r['native']:+.9f} | terme_port={r['carried']:+.6f} "
              f"manque={r['missing']:+.6f}{dm} attendu={r['expected']:.6f}")
        prev = r
    if args.mutants:
        for m in MUTANTS:
            worst = max(abs(r["mutants"][m]) for r in rows)
            detail = " ".join(f"{r['step']}:{r['mutants'][m]:+.1f}" for r in rows)
            print(f"  [mutant {m:<13}] deplacement max = {worst:+.6f} [{detail}] "
                  f"({'MORD' if worst > EPS else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
