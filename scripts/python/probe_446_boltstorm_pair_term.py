"""#446 -- MONTAGE NOMME des sorties de `Boltstorm` (1090) sur la face ATTACK, et mesure natif
contre port.

`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("BOLTSTORM_AdjacentEnemies") * Count(BoltstormAbility.GetAllTargets(dsl,
Direct(FindRangedWeapon(caster).Range)))`, ou l'arbre de ciblage vaut

    Target + ( SurroundingEnemies(Owner, range) & Unobscured(Owner, Enemies(Caster,
                                                             AdjacentUnits(Target))) )

-- donc un PRODUIT poids x CARDINAL, et un cardinal qui COMPTE LA CIBLE elle-meme. Un montage nu
serait DEGENERE de deux facons a la fois : toutes les cibles isolees rendent le meme `1 x 10`, et
rien n'exercerait la porte de portee. La geometrie est donc CONSTRUITE (les unites sont DEPLACEES) :

    C  = le caster `templAggressor` (arme `Bolter`, Range = 2 -> `range` = 2)
    T  = T_CROWD    a distance 2 de C, avec DEUX voisins ennemis a portee et UN hors portee
    N1 = NEAR1      voisin de T, distance <= 2 de C   -> COMPTE
    N2 = NEAR2      voisin de T, distance <= 2 de C   -> COMPTE
    F  = FAR        voisin de T, distance 3 de C      -> NE COMPTE PAS (porte `SurroundingEnemies`)
    A  = T_ALONE    a distance 2 de C, a distance >= 2 de T/N1/N2/F -> AUCUN voisin ennemi

d'ou DEUX regimes separes de 20 points, et un troisieme temoin (F) qui n'existe que pour faire
mordre la porte de portee :

    count(T) = 1 (Target) + 2 (N1, N2)  = 3  ->  terme = 30
    count(A) = 1 (Target)               = 1  ->  terme = 10

`EXPECTED_COUNT_*` sont poses ICI, en dur, depuis le decompile -- ils ne sont PAS relus du port,
sinon la mesure ne trancherait plus rien. Le probe ATTESTE que la geometrie installee est bien
celle-la (toutes les distances sont re-mesurees sur les positions LIVE) avant de lire un accord.

⚠ NON COUVERT par ce montage : le gate `Unobscured` (le board `MC1_67` est plat, `IsTargetTileObscured`
y rend toujours faux) et le regime `FindRangedWeapon == null` (le porteur a une arme distance ;
c'est le regime de toute unite melee-only, non atteignable avec `templAggressor`).

Usage :
    python scripts/python/probe_446_boltstorm_pair_term.py --state-file <chemin ABSOLU>

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_446_boltstorm_pair_term_live.py`.
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
from engine.entities.effect_type import EffectType               # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "templAggressor"       # HERO AU POOL ; `Boltstorm` est son SEUL passif
T_CROWD = "astraBullgryn"       # cible entouree  -> count 3
NEAR1 = "astraCreed"            # voisin de T_CROWD, a portee du caster
NEAR2 = "astraDreir"            # voisin de T_CROWD, a portee du caster
FAR = "eldarRanger"             # voisin de T_CROWD, HORS portee du caster (temoin du gate)
T_ALONE = "astraOrdnance"       # cible isolee    -> count 1
FOES = (T_CROWD, NEAR1, NEAR2, FAR, T_ALONE)

ABILITY = int(TriggeredAbilityType.Boltstorm)                # 1090
OVERWATCH = int(EffectType.Overwatch_AutoAttack)             # 1009 -- cf. `_attest_no_overwatch`
WEIGHT_KEY = "BOLTSTORM_AdjacentEnemies"
WEAPON_RANGE = 2                # `Bolter` de `templAggressor` (gameconfig) -- RE-ATTESTE au montage
EXPECTED_COUNT_CROWD = 3        # Target + N1 + N2 (F est hors portee)
EXPECTED_COUNT_ALONE = 1        # Target seul
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 40000                      # personne ne doit mourir : `Health` ET `RemainingHealth` (#438)

BUILD_ARGS = ["--board", BOARD, "--p-units", CASTER, "--a-units", ",".join(FOES),
              "--unit-stat", ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                                      for v in (CASTER,) + FOES)]


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


# --------------------------------------------------------------------------- geometrie

def native_neighbours(t: tuple, cells: set, elev: dict) -> list:
    """Voisins de `t` au sens de `AdjacentUnits` = `Units(AdjacentTiles(t))` ->
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, donc ring-1
    hex AVEC la porte `|delta elevation| < 2`.

    ⚠ MESURE #446 : sur `MC1_67`, prendre `hexgeo.neighbors` NU donne des tuiles que le natif ne
    considere PAS adjacentes -- `(1,3)` (elev 4) et `(2,2)` (elev 2) sont a distance hex 1 et
    `|delta| = 2` les separe. Un montage bati sur le voisinage nu croit exercer la porte de PORTEE
    alors que la porte d'ELEVATION a deja tout tranche : la contre-epreuve du gate de portee ne mord
    plus, et rien ne le signale."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def find_layout(cells: list, elev: dict) -> dict | None:
    """Cherche `(C, T, N1, N2, F, F2, A)` satisfaisant EXACTEMENT le regime decrit en tete.

    Contraintes posees depuis l'arbre natif, pas depuis une intuition : `T` a portee de tir ; DEUX
    voisins NATIFS de `T` a portee et non obscurcis (ils COMPTENT) ; DEUX voisins NATIFS de `T` hors
    portee (ils ne comptent PAS -- l'un porte `F`, l'autre sert de destination au balayage, et c'est
    ce couple qui fait mordre la porte `SurroundingEnemies(Owner, range)`) ; et `A` a portee, sans
    aucun voisin ennemi."""
    d = hexgeo.distance
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for c in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring2 = [q for q in cells if d(c, q) == 2]
        for t in ring2:
            nb = native_neighbours(t, cs, elev)
            near = [q for q in nb if q != c and d(c, q) <= WEAPON_RANGE
                    and not bq.is_target_tile_obscured(c, q, elev)]
            far = [q for q in nb if d(c, q) > WEAPON_RANGE]
            if len(near) < 2 or len(far) < 2:
                continue
            n1, n2, f, f2 = near[0], near[1], far[0], far[1]
            busy = (t, n1, n2, f)
            alone = [q for q in ring2
                     if q not in busy and q != f2 and all(d(q, b) >= 2 for b in busy)
                     and not bq.is_target_tile_obscured(c, q, elev)]
            if not alone:
                continue
            return {"C": c, "T": t, "N1": n1, "N2": n2, "F": f, "F2": f2, "A": alone[0]}
    return None


def attest_layout(pos: dict, ids: dict, elev: dict) -> None:
    """RE-MESURE toutes les distances sur les positions LIVE et refuse si le regime voulu n'est pas
    celui installe. L'adjacence est celle du NATIF (`bq.is_adjacent`, porte d'elevation comprise) --
    c'est precisement ce que la premiere version du montage avait rate."""
    d = hexgeo.distance
    p = {k: pos.get(uid) for k, uid in ids.items()}
    missing = [k for k, v in p.items() if v is None]
    if missing:
        raise MontageError(f"montage NON INSTALLE : position inconnue pour {missing}")
    checks = [
        ("T a portee", d(p["C"], p["T"]) <= WEAPON_RANGE),
        ("A a portee", d(p["C"], p["A"]) <= WEAPON_RANGE),
        ("N1 voisin NATIF de T", bq.is_adjacent(p["T"], p["N1"], elev)),
        ("N2 voisin NATIF de T", bq.is_adjacent(p["T"], p["N2"], elev)),
        ("F voisin NATIF de T", bq.is_adjacent(p["T"], p["F"], elev)),
        ("N1 a portee", d(p["C"], p["N1"]) <= WEAPON_RANGE),
        ("N2 a portee", d(p["C"], p["N2"]) <= WEAPON_RANGE),
        ("N1 non obscurci", not bq.is_target_tile_obscured(p["C"], p["N1"], elev)),
        ("N2 non obscurci", not bq.is_target_tile_obscured(p["C"], p["N2"], elev)),
        ("F HORS portee", d(p["C"], p["F"]) > WEAPON_RANGE),
        ("A sans voisin NATIF ennemi",
         not any(bq.is_adjacent(p["A"], p[k], elev) for k in ("T", "N1", "N2", "F"))),
    ]
    bad = [name for name, ok in checks if not ok]
    if bad:
        raise MontageError(f"montage NON INSTALLE : contraintes violees {bad} -- positions {p}")


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _attest_no_overwatch(dv, ids: dict) -> None:
    """`templAggressor` porte AUSSI le trait `SuppressiveFire` (1010 -> ability 1044), dont le
    playbook EST au registre et verse 35 quand la CIBLE porte l'overwatch (1009). Si une cible le
    portait, le total `pairUtility` melangerait deux termes et l'accord ne dirait plus lequel est
    juste -- on refuse le montage plutot que de lire un chiffre ambigu."""
    for key in ("T", "A"):
        uid = ids[key]
        u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
        types = {int(e["effectType"]) for e in ((u or {}).get("effects") or [])
                 if isinstance(e, dict) and e.get("effectType") is not None}
        if OVERWATCH in types:
            raise MontageError(f"montage AMBIGU : la cible {key} (u{uid}) porte l'overwatch "
                               f"{OVERWATCH} -- le terme SuppressiveFire (1044) se melerait")


def _stage(sid, rpc, rid: int) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    vis_uid = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1090 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    # (b) L'arme distance du caster : le `range` de l'arbre natif. Re-atteste plutot que suppose.
    from engine.services.battle_query import find_ranged_weapon
    w = find_ranged_weapon(CASTER)
    if w is None or int(w.get("Range") or 0) != WEAPON_RANGE:
        raise MontageError(f"montage NON INSTALLE : l'arme distance de {CASTER} vaut {w}, "
                           f"portee attendue {WEAPON_RANGE} -- la geometrie serait fausse")

    # (c) La geometrie, puis le DRIVE (jamais « bloque par le spawn »).
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = find_layout(cells, elev)
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucune configuration (C,T,N1,N2,F,F2,A) sur ce "
                           "board -- le regime a trois niveaux ne serait pas installe")
    ids = {"C": cid, "T": vis_uid[T_CROWD], "N1": vis_uid[NEAR1], "N2": vis_uid[NEAR2],
           "F": vis_uid[FAR], "A": vis_uid[T_ALONE]}
    wanted = {ids[k]: lay[k] for k in ids}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    _dv2, pos = P124._positions(sid, rid)
    attest_layout(pos, ids, elev)

    dv, ctx = _fresh_ctx(rpc, rid, cid)
    _attest_no_overwatch(dv, ids)
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    if lay["C"] not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
        raise MontageError(f"montage NON INSTALLE : la tuile de tir {lay['C']} n'est pas dans les "
                           f"tuiles d'action de l'oracle -- natif et port ne compareraient pas la "
                           f"meme chose")
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "ids": ids, "ab": ab, "ctx": ctx,
            "dv": dv, "tile": lay["C"], "layout": lay, "walk": walk, "elev": elev,
            "wanted": wanted}


def _rows(rpc, st: dict) -> list[dict]:
    """Une ligne par cible mesurable (T = entouree, A = isolee) : natif, port, et port SANS le
    playbook 1090. `expected` est le PRODUIT pose en dur (`poids x EXPECTED_COUNT_*`), lu du BC
    servi pour le poids et du decompile pour le cardinal."""
    import engine.playbook.psyker as PSY
    wt = st["ctx"].wt
    weight = float(wt.triggered(WEIGHT_KEY))
    if weight <= 0:
        raise MontageError(f"montage NON INSTALLE : le poids {WEIGHT_KEY} vaut {weight} dans le BC "
                           f"servi -- le terme serait nul et la mesure ne trancherait rien")
    out = []
    for key, count in (("T", EXPECTED_COUNT_CROWD), ("A", EXPECTED_COUNT_ALONE)):
        uid = st["ids"][key]
        nat = pair_native(rpc, st["rid"], st["cid"], uid, st["ab"], st["tile"])
        port = pair_port(st["ctx"], st["ab"], uid, st["tile"])
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(st["ctx"], st["ab"], uid, st["tile"])
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"target": key, "uid": uid, "count": count, "weight": weight,
                    "expected": weight * count, "native": nat, "port": port,
                    "port_muted": muted})
    return out


def build_case(sid, rpc, rid: int) -> dict:
    return _stage(sid, rpc, rid)


def measure(rpc, case: dict) -> list[dict]:
    return _rows(rpc, case)


# --------------------------------------------------------------------------- contre-epreuves

def measure_mutant(rpc, case: dict, mutant: str) -> list[dict]:
    """Re-mesure le port avec le playbook 1090 REMPLACE par un mutant. La contre-epreuve doit
    MORDRE : chaque mutant doit ECARTER le port du natif sur au moins une cible.

      `no_range`   -- la porte `SurroundingEnemies(Owner, range)` retiree (range infinie) : `F`
                      entre dans le compte de `T` -> +1 x poids.
      `no_target`  -- le volet `Target` de l'`op_Addition` retire (`count - 1`) : -1 x poids sur
                      les deux cibles.
      `not_adjacent` -- `AdjacentUnits(Target)` remplace par « tous les ennemis a portee » : le
                      compte de `A` gonfle des unites non adjacentes.
    """
    import engine.playbook.psyker as PSY
    from engine.playbook import boltstorm as B

    class _Mut(B.BoltstormPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None:
                return 0.0
            n = B.count_all_targets(sc, attacker_uid, case_tgt_id,
                                    99 if mutant == "no_range" else WEAPON_RANGE)
            if mutant == "no_target":
                n = max(0, n - 1)
            if mutant == "not_adjacent":
                n = _count_no_adjacency(sc, attacker_uid, case_tgt_id, WEAPON_RANGE)
            return float(ctx.wt.triggered(WEIGHT_KEY)) * n

    tile = case["tile"]
    ids = case["ids"]
    ref = {k: pair_port(case["ctx"], case["ab"], ids[k], tile) for k in ("T", "A")}
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _Mut()
    try:
        out = []
        for key in ("T", "A"):
            uid = ids[key]
            out.append({"mutant": mutant, "target": key, "uid": uid,
                        "native": pair_native(rpc, case["rid"], case["cid"], uid, case["ab"], tile),
                        "port": pair_port(case["ctx"], case["ab"], uid, tile),
                        "port_ref": ref[key]})
        return out
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


def sweep_count(sid, rpc, case: dict) -> list[dict]:
    """BALAYAGE DU CARDINAL sur la MEME paire (C, T) -- la mesure qui tranche seule, ET la seule
    qui exerce la porte de PORTEE.

    Une comparaison natif/port en NIVEAU melange le terme du playbook et tout ce que le port peut
    devoir par ailleurs sur cette paire (residu constant, cf. la case-doc). Ici on ne bouge QU'UNE
    chose : la DISTANCE AU CASTER d'un voisin de `T` qui reste voisin de `T` dans tous les crans.
    Tout le reste (armure, defense, arme, distance C->T, effets, adjacence a la cible) est identique
    d'un cran a l'autre, donc le DELTA natif EST le terme du playbook, isole -- et il doit valoir
    exactement le poids `BOLTSTORM_AdjacentEnemies` par cran.

    Crans, dans cet ordre :
      `count1` -- N1 ET N2 sur les deux tuiles voisines-NATIVES de `T` mais HORS portee : ils sont
                  toujours adjacents a la cible, seule la porte `SurroundingEnemies(Owner, range)`
                  les exclut.
      `count2` -- N1 revient a portee.
      `count3` -- N2 revient a portee.

    A chaque cran, la geometrie est RE-MESUREE et le cardinal RE-DERIVE des positions live avec
    l'adjacence NATIVE -- jamais suppose."""
    d = hexgeo.distance
    lay, ids = case["layout"], case["ids"]
    elev = case["elev"]
    # `F` cede sa tuile hors-portee a `N1` et va se garer loin de tout (il ne doit plus etre voisin
    # de `T`, sinon le cardinal du cran `count1` ne serait plus 1).
    park = _park_tile(case, lay)
    steps = [
        ("count1", {ids["F"]: park, ids["N1"]: lay["F"], ids["N2"]: lay["F2"]}),
        ("count2", {ids["N1"]: lay["N1"]}),
        ("count3", {ids["N2"]: lay["N2"]}),
    ]
    rows = []
    wanted = dict(case["wanted"])
    for name, move in steps:
        wanted.update(move)
        if not P124._drive_to(sid, case["rid"], case["walk"], case["elev"], wanted):
            _dv, pos = P124._positions(sid, case["rid"])
            raise MontageError(f"balayage NON INSTALLE ({name}) : placement incomplet -- voulu "
                               f"{wanted}, obtenu { {u: pos.get(u) for u in wanted} }")
        P124._give_turn_back(sid, case["rid"], case["myplayer"])
        _dv2, pos = P124._positions(sid, case["rid"])
        tp, cp = pos[ids["T"]], pos[ids["C"]]
        # Cardinal RE-DERIVE des positions live, depuis l'arbre natif (adjacence NATIVE incluse) --
        # jamais depuis le port.
        adj = [k for k in ("N1", "N2", "F", "A")
               if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev)]
        got = 1 + sum(1 for k in adj
                      if d(cp, pos[ids[k]]) <= WEAPON_RANGE
                      and not bq.is_target_tile_obscured(cp, pos[ids[k]], elev))
        gated = [k for k in adj if d(cp, pos[ids[k]]) > WEAPON_RANGE]
        dv, ctx = _fresh_ctx(rpc, case["rid"], case["cid"])
        case["ctx"], case["dv"] = ctx, dv
        nat = pair_native(rpc, case["rid"], case["cid"], ids["T"], case["ab"], cp)
        port = pair_port(ctx, case["ab"], ids["T"], cp)
        rows.append({"step": name, "count": got, "tile": cp, "native": nat, "port": port,
                     "adjacent": adj, "gated_by_range": gated})
    if not any(r["gated_by_range"] for r in rows):
        raise MontageError("balayage NON DISCRIMINANT : aucun cran n'a de voisin de la cible EXCLU "
                           "PAR LA PORTEE -- la porte `SurroundingEnemies(Owner, range)` n'est pas "
                           "exercee et le mutant `no_range` ne pourrait pas mordre")
    return rows


def _park_tile(case: dict, lay: dict) -> tuple:
    """Une tuile de garage pour `F` pendant le balayage : walkable, loin de `T` et de `C`, libre."""
    d = hexgeo.distance
    busy = {lay[k] for k in lay}
    cells = sorted(p for p, wk in case["walk"].items() if wk and case["elev"].get(p) is not None)
    for q in cells:
        if q not in busy and d(q, lay["T"]) >= 3 and d(q, lay["C"]) >= 3:
            return q
    raise MontageError("balayage NON INSTALLE : aucune tuile de garage pour F")


def _count_no_adjacency(scene, caster_uid, target_uid, rng) -> int:
    """Variante MUTEE (contre-epreuve `not_adjacent`) : le gate `AdjacentUnits(Target)` retire."""
    if target_uid is None:
        return 0
    n = 1
    cpos = scene.pos(caster_uid)
    cteam = scene.team(caster_uid)
    if cpos is None or cteam is None:
        return n
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or uid in (caster_uid, target_uid) or not u.get("alive"):
            continue
        if u.get("team") == cteam:
            continue
        p = scene.pos(uid)
        if p is not None and hexgeo.distance(cpos, p) <= rng:
            n += 1
    return n


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--mutants", action="store_true",
                    help="joue aussi les trois contre-epreuves (elles doivent MORDRE)")
    ap.add_argument("--sweep", action="store_true",
                    help="balaie le CARDINAL sur la meme paire (2, 3, 4) -- la mesure isolante")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, BUILD_ARGS)
    case = build_case(sid, rpc, rid)
    lay = case["layout"]
    print(f"runner {rid} | caster u{case['cid']} @ {lay['C']} | ability normale {case['ab']} | "
          f"range={WEAPON_RANGE}")
    print(f"  layout T={lay['T']} N1={lay['N1']} N2={lay['N2']} F={lay['F']} A={lay['A']}")
    for row in measure(rpc, case):
        d = row["port"] - row["native"]
        dm = row["native"] - row["port_muted"]
        print(f"  [{row['target']}] u{row['uid']} count={row['count']} "
              f"nat={row['native']:.6f} port={row['port']:.6f} d={d:+.9f} | "
              f"mute={row['port_muted']:.6f} manque={dm:+.9f} attendu={row['expected']:.6f}")
    # ⚠ ORDRE : les mutants d'ABORD (ils s'appuient sur le layout de montage, ou `F` est voisin
    # NATIF de la cible mais HORS portee -- c'est ce qui rend `no_range` discriminant), le balayage
    # ENSUITE (il DEPLACE les unites et laisse la geometrie ailleurs).
    if args.mutants:
        for m in ("no_range", "no_target", "not_adjacent"):
            rows = measure_mutant(rpc, case, m)
            # ⚠ Le critere est le DEPLACEMENT du port par rapport au port NON MUTE, JAMAIS l'ecart
            # au natif : cette paire porte un residu constant hors-perimetre, et un `abs(port -
            # native) > EPS` serait donc VRAI meme pour un mutant parfaitement inerte. C'est
            # exactement le piege de #441 (un bras vert sous mutation).
            worst = max(abs(r["port"] - r["port_ref"]) for r in rows)
            detail = " ".join(f"{r['target']}:{r['port'] - r['port_ref']:+.4f}" for r in rows)
            print(f"  [mutant {m:<13}] deplacement max du port = {worst:+.9f} [{detail}] "
                  f"({'MORD' if worst > EPS else 'NE MORD PAS'})")
    if args.sweep:
        prev = None
        for row in sweep_count(sid, rpc, case):
            dn = "" if prev is None else f" dNat={row['native'] - prev['native']:+.6f}"
            dp = "" if prev is None else f" dPort={row['port'] - prev['port']:+.6f}"
            print(f"  [{row['step']}] count={row['count']} adj={row['adjacent']} "
                  f"gate_portee={row['gated_by_range']} nat={row['native']:.6f} "
                  f"port={row['port']:.6f} d={row['port'] - row['native']:+.9f}{dn}{dp}")
            prev = row
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
