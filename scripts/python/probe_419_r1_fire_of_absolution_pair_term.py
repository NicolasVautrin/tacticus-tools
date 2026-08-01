"""#419-r1 -- MONTAGE NOMME des sorties de `FireOfAbsolution` (TriggeredAbilityType **1017**) sur la
face ATTACK, et mesure natif contre port.

`IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook.u003CCalculateAttackUtilityInStepsInternalu003E
d__4$$MoveNext` rend

    GetUtilityValue("FIREOFABSOLUTION_AdjacentFriend") * |GetAdjacentFriends(case.Target, playerId)|
  + GetUtilityValue("FIREOFABSOLUTION_AdjacentEnemy")  * |GetAdjacentEnemies(case.Target, playerId,
                                                                             ignoreSteppables: false)|

-- DEUX produits poids x cardinal, de SIGNES OPPOSES (-20 et 20 sur ce BC), ancres sur la CIBLE et
non sur la tuile d'attaque. Trois degenerescences guettent, et le montage les evite toutes :

  * `nFriends == nEnemies` -> terme NUL : la mesure ne trancherait rien ;
  * un montage a `nFriends == 0` ne tranche PAS l'appariement cle <-> slot (les litteraux de chaine
    ne sont pas lisibles au decompile) : il faut au moins un cran ou les deux comptes different ;
  * `hexgeo.distance == 1` != adjacence NATIVE (porte `|delta elevation| < 2` d'`IterateAdjacentTiles`)
    -- toutes les adjacences du montage sont RE-MESUREES avec `battle_query.is_adjacent`.

## Le montage

    C  = `adeptRetributor` (HERO AU POOL), dont `FireOfAbsolution` est le SEUL passif -- aucun autre
         triggered de son kit n'est au registre attack, donc aucun terme ne se mele.
    T  = la cible ennemie, sur une tuile ayant >= 4 voisins NATIFS libres.
    E1, E2 = deux ENNEMIS que l'on amene, un par un, sur un voisin natif de T   -> +20 chacun.
    A1, A2 = deux ALLIES du caster que l'on amene de meme                       -> -20 chacun.

## Etape A -- le BALAYAGE, la mesure qui tranche seule

C reste sur une tuile de tir FIXE, NON adjacente a T. Cinq crans, chacun ne deplacant QU'UNE unite :

    n0 : (0 ami, 0 ennemi) adjacents a T -> terme      0
    e1 : (0, 1)                          -> terme    +20
    e2 : (0, 2)                          -> terme    +40
    f1 : (1, 2)                          -> terme    +20
    f2 : (2, 2)                          -> terme      0

Le critere n'est PAS `port == natif` en niveau : cette paire porte un residu hors-perimetre
(feuilles non portees), et un ecart absolu serait donc VRAI meme pour un port parfait. On mesure
`nat - port_muted` (ce qui MANQUE au port prive de 1017) et on lit ses DELTAS d'un cran a l'autre :
tout le reste est identique entre deux crans consecutifs, donc ce delta EST le terme du playbook,
isole. Il doit valoir exactement +20, +20, -20, -20.

## Etape B -- le CASTER COMPTE-T-IL PARMI LES AMIS ? (double delta)

Le natif n'oppose aucun retrait au resultat de `GetAdjacentFriends` -- ni `op_Subtraction`, ni test
`!= case.Caster` -- la ou la famille MOVE (`AdjacentUnitPreference...d__1`) en a un EXPLICITE. Le
caster adjacent a sa cible devrait donc s'infliger -20. Le confronter en NIVEAU est impossible :
changer la tuile de tir change aussi tout le reste du score. On prend donc un DOUBLE DELTA, qui
annule et le residu constant et la variation due au changement de tuile :

    (nat_adj - muted_adj) - (nat_far - muted_far)  ==  -20   si le caster compte
                                                   ==    0   s'il ne compte pas

ou `far` = C sur une tuile NON adjacente a T et `adj` = C sur un voisin natif de T, dans les DEUX cas
sans aucun autre voisin de T. `muted` = le MEME port prive du playbook 1017 : il porte la variation
de toutes les autres feuilles, qui s'annule donc entre les deux termes.

## Etape C -- les contre-epreuves

Chaque mutant doit DEPLACER le port par rapport au port NON MUTE (jamais « s'ecarter du natif » :
le residu rendrait ce critere vrai pour un mutant inerte -- piege de #441).

    `swap_keys`      les deux cles echangees          -> mord des que nFriends != nEnemies
    `friends_only`   le terme ennemi retire           -> mord des qu'il y a un ennemi adjacent
    `enemies_only`   le terme ami retire              -> mord des qu'il y a un ami adjacent
    `exclude_caster` le caster retire des amis        -> mord SEULEMENT en regime C-adjacent
    `no_elev_gate`   `hexgeo.distance == 1` au lieu de `bq.is_adjacent` -> ne mord que si le montage
                     a une paire separee de >= 2 niveaux ; VERTE = residu NOMME, pas une preuve.

Usage :
    python scripts/python/probe_419_r1_fire_of_absolution_pair_term.py --state-file <ABSOLU>
        [--mutants] [--caster-quirk]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419_r1_fire_of_absolution_pair_term_live.py`.
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
CASTER = "adeptRetributor"      # HERO AU POOL ; `FireOfAbsolution` (1017) est son SEUL passif
ALLY1 = "adeptCanoness"         # A1 -- ami du caster, amene au contact de la CIBLE
ALLY2 = "adeptHospitaller"      # A2 -- idem
TARGET = "astraBullgryn"        # T  -- la cible du case
FOE1 = "astraCreed"             # E1 -- ennemi amene au contact de la CIBLE
FOE2 = "astraDreir"             # E2 -- idem
ALLIES = (CASTER, ALLY1, ALLY2)
FOES = (TARGET, FOE1, FOE2)

ABILITY = int(TriggeredAbilityType.FireOfAbsolution)          # 1017
KEY_FRIEND = "FIREOFABSOLUTION_AdjacentFriend"                # -20 sur ce BC
KEY_ENEMY = "FIREOFABSOLUTION_AdjacentEnemy"                  #  20 sur ce BC
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 40000                      # personne ne doit mourir : `Health` ET `RemainingHealth` (#438)

# Les crans du balayage : (nom, amis adjacents a T, ennemis adjacents a T).
#
# ⚠ `zz` est le cran de la PORTE D'ELEVATION, et il n'existe que si le board offre une tuile `Z` a
# distance hex 1 de `T` que le natif ne considere PAS adjacente (`|delta elev| >= 2`). E2 y monte :
# les comptes NATIFS ne bougent pas (d'ou `(1, 1)`, E1 seul reste), mais une adjacence `hexgeo` nue
# en compterait DEUX. C'est le seul cran ou le mutant `no_elev_gate` peut mordre.
#
# ⚠ Les crans ne sont PAS interchangeables pour les contre-epreuves : `swap_keys` echange deux poids
# et ne peut mordre que la ou `nFriends != nEnemies` -- sur `f2` (2, 2) il est INERTE alors que le
# port est faux nulle part. Les mutants sont donc joues a CHAQUE cran, et le verdict d'un mutant est
# « mord sur AU MOINS un cran », jamais « mord sur le dernier ».
SWEEP = (("n0", 0, 0), ("e1", 0, 1), ("e2", 0, 2), ("f1", 1, 2), ("f2", 2, 2), ("zz", 1, 1))
MUTANTS = ("swap_keys", "friends_only", "enemies_only", "exclude_caster", "no_elev_gate")

BUILD_ARGS = ["--board", BOARD, "--p-units", ",".join(ALLIES), "--a-units", ",".join(FOES),
              "--unit-stat", ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                                      for v in ALLIES + FOES)]


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
    """Le MEME port, prive du playbook 1017 : le denominateur commun des deux etages de mesure."""
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
    """Voisins de `t` au sens de `IterateAdjacentTiles` : ring-1 hex AVEC la porte
    `|delta elevation| < 2`. Prendre `hexgeo.neighbors` NU donnerait des tuiles que le natif ne
    considere PAS adjacentes (mesure #446 sur ce meme board)."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def find_layout(cells: list, elev: dict) -> dict | None:
    """Cherche `(C_far, C_adj, T, S1..S4, P1..P4)` satisfaisant EXACTEMENT le regime de l'en-tete.

    `S1..S4` = quatre voisins NATIFS de T (les postes ou l'on amene E1, E2, A1, A2) ; `C_adj` = un
    CINQUIEME voisin natif de T, reserve au caster pour l'etape B ; `P1..P4` = quatre garages, NON
    adjacents a T et distincts. `C_far` doit voir T (tuile de tir non adjacente)."""
    d = hexgeo.distance
    cs = set(cells)
    cands: list[dict] = []
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = native_neighbours(t, cs, elev)
        if len(nb) < 5:
            continue
        for cfar in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
            if cfar == t or bq.is_adjacent(t, cfar, elev) or d(cfar, t) > 3:
                continue
            if bq.is_target_tile_obscured(cfar, t, elev):
                continue
            posts = [q for q in nb if q != cfar]
            if len(posts) < 5:
                continue
            s1, s2, s3, s4, cadj = posts[0], posts[1], posts[2], posts[3], posts[4]
            if bq.is_target_tile_obscured(cadj, t, elev):
                continue
            busy = {t, cfar, s1, s2, s3, s4, cadj}
            # Garages : hors du voisinage NATIF de T, et a distance hex >= 2 de T pour qu'aucun
            # arrondi d'elevation ne puisse les y ramener.
            parks = [q for q in cells
                     if q not in busy and d(q, t) >= 2 and not bq.is_adjacent(t, q, elev)]
            if len(parks) < 4:
                continue
            # `Z` -- la tuile qui SEPARE l'adjacence native de `hexgeo.distance == 1` : voisine hex
            # de `T`, mais ecartee par la porte `|delta elev| >= 2` d'`IterateAdjacentTiles`. Sans
            # elle, le mutant `no_elev_gate` ne peut pas mordre et le cran `zz` est saute.
            zs = [q for q in cells
                  if q not in busy and d(q, t) == 1 and not bq.is_adjacent(t, q, elev)]
            lay = {"C_far": cfar, "C_adj": cadj, "T": t,
                   "S1": s1, "S2": s2, "S3": s3, "S4": s4,
                   "P1": parks[0], "P2": parks[1], "P3": parks[2], "P4": parks[3]}
            if zs:
                lay["Z"] = zs[0]
            cands.append(lay)
            if zs:
                return lay        # un layout AVEC porte d'elevation exercable prime
    return cands[0] if cands else None


def counts_live(pos: dict, ids: dict, elev: dict) -> tuple:
    """RE-DERIVE `(nFriends, nEnemies)` des positions LIVE avec l'adjacence NATIVE, depuis le
    decompile -- JAMAIS depuis le port. Le caster est compte comme AMI s'il est adjacent (en-tete)."""
    tp = pos.get(ids["T"])
    if tp is None:
        raise MontageError("mesure IMPOSSIBLE : la cible n'a pas de position live")
    friends = [k for k in ("C", "A1", "A2")
               if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev)]
    foes = [k for k in ("E1", "E2")
            if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev)]
    return len(friends), len(foes), friends, foes


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
    for key, vis in (("C", CASTER), ("A1", ALLY1), ("A2", ALLY2)):
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

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1017 dedans, le dispatcher ne l'itere
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
    others = sorted(set(live_ids) & set(PSY.TRIGGERED_ATTACK_PLAYBOOKS) - {ABILITY})
    if others:
        raise MontageError(f"montage AMBIGU : {CASTER} porte aussi les playbooks attack {others} "
                           f"-- leurs termes se meleraient a celui de {ABILITY}")

    # (c) La geometrie, puis le DRIVE (jamais « bloque par le spawn »).
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = find_layout(cells, elev)
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucune configuration (C_far,C_adj,T,S1..S4,"
                           "P1..P4) sur ce board -- les cinq crans ne seraient pas installables")
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
    if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
        raise MontageError(f"cran {label} NON INSTALLE : la tuile de tir {tile} n'est pas dans les "
                           f"tuiles d'action de l'oracle -- natif et port ne compareraient pas la "
                           f"meme chose")
    return {"pos": pos, "tile": tile, "ab": ab, "ctx": ctx}


def sweep(sid, rpc, case: dict, with_mutants: bool = False) -> list[dict]:
    """Etape A -- le balayage, caster sur la tuile de tir FIXE `C_far`.

    Les contre-epreuves sont jouees A CHAQUE CRAN (elles sont purement offline sur le `ctx` deja
    construit -- aucun RPC de plus) : un mutant n'a pas a mordre partout, il doit mordre QUELQUE
    PART, et les crans ou il est inerte sont eux-memes des mesures (cf. `SWEEP`)."""
    lay, ids = case["layout"], case["ids"]
    base = {ids["C"]: lay["C_far"], ids["T"]: lay["T"],
            ids["E1"]: lay["P1"], ids["E2"]: lay["P2"],
            ids["A1"]: lay["P3"], ids["A2"]: lay["P4"]}
    moves = {"n0": {}, "e1": {ids["E1"]: lay["S1"]}, "e2": {ids["E2"]: lay["S2"]},
             "f1": {ids["A1"]: lay["S3"]}, "f2": {ids["A2"]: lay["S4"]},
             # `zz` : E2 quitte son poste adjacent pour `Z` (voisine HEX de T, mais pas au sens
             # natif) et A2 rentre au garage -> comptes natifs (1 ami, 1 ennemi).
             "zz": {ids["E2"]: lay.get("Z"), ids["A2"]: lay["P4"]}}
    wanted = dict(base)
    rows = []
    for name, want_f, want_e in SWEEP:
        if name == "zz" and "Z" not in lay:
            continue                      # board sans marche >= 2 niveaux : cran NON JOUE
        wanted.update(moves[name])
        s = _settle(sid, rpc, case, wanted, name)
        nf, ne, fk, ek = counts_live(s["pos"], ids, case["elev"])
        if (nf, ne) != (want_f, want_e):
            raise MontageError(f"cran {name} NON INSTALLE : comptes live (amis={nf} {fk}, "
                               f"ennemis={ne} {ek}) au lieu de ({want_f}, {want_e}) "
                               f"-- positions { {k: s['pos'].get(v) for k, v in ids.items()} }")
        nat = pair_native(rpc, case["rid"], case["cid"], ids["T"], s["ab"], s["tile"])
        port = pair_port(s["ctx"], s["ab"], ids["T"], s["tile"])
        muted = pair_muted(s["ctx"], s["ab"], ids["T"], s["tile"])
        wt = s["ctx"].wt
        expect = float(wt.triggered(KEY_FRIEND)) * nf + float(wt.triggered(KEY_ENEMY)) * ne
        row = {"step": name, "nf": nf, "ne": ne, "tile": s["tile"], "native": nat,
               "port": port, "muted": muted, "expected": expect,
               "missing": nat - muted, "carried": port - muted}
        if with_mutants:
            row["mutants"] = {m: measure_mutant(rpc, case, m, s["tile"], ids["T"])["shift"]
                              for m in MUTANTS}
        rows.append(row)
    return rows


def caster_quirk(sid, rpc, case: dict) -> dict:
    """Etape B -- DOUBLE DELTA : le caster compte-t-il parmi les amis adjacents ?

    Les deux crans n'ont AUCUN autre voisin de T ; seule la tuile du caster change. Le terme
    `nat - muted` porte le terme du playbook PLUS le residu de la tuile ; la difference des deux
    ANNULE ce residu, a condition que le port muted suive correctement la variation des autres
    feuilles (ce qui est justement ce que le sweep de l'etape A a etabli)."""
    lay, ids = case["layout"], case["ids"]
    park = {ids["E1"]: lay["P1"], ids["E2"]: lay["P2"],
            ids["A1"]: lay["P3"], ids["A2"]: lay["P4"], ids["T"]: lay["T"]}
    out = {}
    for name, ctile in (("far", lay["C_far"]), ("adj", lay["C_adj"])):
        wanted = dict(park)
        wanted[ids["C"]] = ctile
        s = _settle(sid, rpc, case, wanted, f"quirk/{name}")
        nf, ne, fk, ek = counts_live(s["pos"], ids, case["elev"])
        want_f = 1 if name == "adj" else 0
        if (nf, ne) != (want_f, 0):
            raise MontageError(f"cran quirk/{name} NON INSTALLE : comptes live (amis={nf} {fk}, "
                               f"ennemis={ne} {ek}) au lieu de ({want_f}, 0)")
        nat = pair_native(rpc, case["rid"], case["cid"], ids["T"], s["ab"], s["tile"])
        muted = pair_muted(s["ctx"], s["ab"], ids["T"], s["tile"])
        port = pair_port(s["ctx"], s["ab"], ids["T"], s["tile"])
        out[name] = {"tile": s["tile"], "nf": nf, "ne": ne, "native": nat, "muted": muted,
                     "port": port, "missing": nat - muted, "carried": port - muted}
    wt = case["ctx"].wt
    out["expected"] = float(wt.triggered(KEY_FRIEND))          # -20 : le caster, seul ami adjacent
    out["double_delta_native"] = out["adj"]["missing"] - out["far"]["missing"]
    out["double_delta_port"] = out["adj"]["carried"] - out["far"]["carried"]
    return out


# --------------------------------------------------------------------------- contre-epreuves

def _mutant_class(mutant: str, wt):
    from engine.playbook import fire_of_absolution as F

    class _Mut(F.FireOfAbsolutionPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None:
                return 0.0
            if mutant == "no_elev_gate":
                nf, ne = _counts_hexgeo_only(sc, attacker_uid, case_tgt_id)
            elif mutant == "exclude_caster":
                nf, ne = F.count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)
                tp, cp = sc.pos(case_tgt_id), sc.pos(attacker_uid)
                if tp is not None and cp is not None and bq.is_adjacent(
                        tp, cp, getattr(sc, "elev_by_pos", None)):
                    nf -= 1
            else:
                nf, ne = F.count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)
            wf, we = float(ctx.wt.triggered(F._WEIGHT_FRIEND)), float(ctx.wt.triggered(F._WEIGHT_ENEMY))
            if mutant == "swap_keys":
                wf, we = we, wf
            if mutant == "friends_only":
                we = 0.0
            if mutant == "enemies_only":
                wf = 0.0
            return wf * nf + we * ne
    return _Mut


def _counts_hexgeo_only(scene, caster_uid, target_uid) -> tuple:
    """Variante MUTEE : adjacence `hexgeo.distance == 1` NUE, sans la porte d'elevation native."""
    tp = scene.pos(target_uid)
    cteam = scene.team(caster_uid)
    if tp is None or cteam is None:
        return (0, 0)
    nf = ne = 0
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or not u.get("alive"):
            continue
        p = scene.pos(uid)
        if p is None or hexgeo.distance(tp, p) != 1:
            continue
        if u.get("team") == cteam:
            nf += 1
        else:
            ne += 1
    return (nf, ne)


def measure_mutant(rpc, case: dict, mutant: str, tile, tgt) -> dict:
    """Re-mesure le port avec 1017 REMPLACE par un mutant, sur la geometrie DEJA installee.

    ⚠ Le critere est le DEPLACEMENT du port par rapport au port NON MUTE, JAMAIS l'ecart au natif :
    cette paire porte un residu hors-perimetre, et `abs(port - native) > EPS` serait donc VRAI meme
    pour un mutant parfaitement inerte (piege de #441)."""
    import engine.playbook.psyker as PSY
    ctx, ab = case["ctx"], case["ab"]
    ref = pair_port(ctx, ab, tgt, tile)
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _mutant_class(mutant, ctx.wt)()
    try:
        got = pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
    return {"mutant": mutant, "port": got, "port_ref": ref, "shift": got - ref}


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str]) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
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
                    help="joue les contre-epreuves sur le dernier cran du balayage")
    ap.add_argument("--caster-quirk", action="store_true",
                    help="joue le double delta de l'etape B (le caster compte-t-il ?)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, BUILD_ARGS)
    case = build_case(sid, rpc, rid)
    lay = case["layout"]
    print(f"runner {rid} | caster u{case['cid']} ({CASTER}) | ability 1017 | board {BOARD}")
    print(f"  layout T={lay['T']} C_far={lay['C_far']} C_adj={lay['C_adj']} "
          f"posts S1..S4={lay['S1']},{lay['S2']},{lay['S3']},{lay['S4']}")

    if "Z" not in lay:
        print("  [!] board SANS marche >= 2 niveaux voisine de la cible : le cran `zz` est SAUTE et "
              "le mutant `no_elev_gate` ne peut PAS mordre (residu a nommer, pas une preuve).")
    prev = None
    rows = sweep(sid, rpc, case, with_mutants=args.mutants)
    for r in rows:
        dn = "" if prev is None else f" dMANQUE={r['missing'] - prev['missing']:+.6f}"
        de = "" if prev is None else f" dATTENDU={r['expected'] - prev['expected']:+.1f}"
        print(f"  [{r['step']}] amis={r['nf']} ennemis={r['ne']} tile={r['tile']} "
              f"nat={r['native']:.6f} port={r['port']:.6f} mute={r['muted']:.6f} | "
              f"manque={r['missing']:+.6f} porte={r['carried']:+.6f} "
              f"attendu={r['expected']:+.1f}{dn}{de}")
        prev = r
    ok = all(abs((b["missing"] - a["missing"]) - (b["expected"] - a["expected"])) <= EPS
             for a, b in zip(rows, rows[1:]))
    lvl = max(abs(r["missing"] - r["expected"]) for r in rows)
    print(f"  => deltas du balayage : {'ACCORD' if ok else 'DESACCORD'} (tolerance {EPS}) | "
          f"ecart NIVEAU max |manque - attendu| = {lvl:.9f}")

    if args.mutants:
        for m in MUTANTS:
            shifts = {r["step"]: r["mutants"][m] for r in rows}
            worst = max(abs(v) for v in shifts.values())
            detail = " ".join(f"{k}:{v:+.1f}" for k, v in shifts.items())
            print(f"  [mutant {m:<15}] deplacement max = {worst:+.9f} [{detail}] "
                  f"({'MORD' if worst > EPS else 'NE MORD PAS'})")

    if args.caster_quirk:
        q = caster_quirk(sid, rpc, case)
        for k in ("far", "adj"):
            print(f"  [quirk/{k}] tile={q[k]['tile']} amis={q[k]['nf']} ennemis={q[k]['ne']} "
                  f"nat={q[k]['native']:.6f} mute={q[k]['muted']:.6f} "
                  f"manque={q[k]['missing']:+.6f} porte={q[k]['carried']:+.6f}")
        print(f"  => double delta NATIF={q['double_delta_native']:+.6f} "
              f"PORT={q['double_delta_port']:+.6f} attendu={q['expected']:+.1f} "
              f"({'ACCORD' if abs(q['double_delta_native'] - q['expected']) <= EPS else 'DESACCORD'})")
        r = measure_mutant(rpc, case, "exclude_caster", q["adj"]["tile"], case["ids"]["T"])
        print(f"  [mutant exclude_caster @adj] deplacement du port = {r['shift']:+.9f} "
              f"({'MORD' if abs(r['shift']) > EPS else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
