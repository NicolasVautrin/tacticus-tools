"""Probe #494 -- `1102 Doombolt` : PAR QUOI le natif ordonne-t-il ses cibles, et a quel etage le
port en diverge ?

Ecart rapporte (case-487 §8, mesure du 2026-08-07, board `MC1_67`, seed 777) :

    LIVE {81: 1, 83: 1, 87: 1}      PORT {81: 1, 83: 1, 85: 1}

Les deux cotes repartissent bien `N = 3` sur `C = 4` (`r = 3` -> `[1, 1, 1, 0]`) : c'est l'ORDRE
rendu par `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` qui diverge, donc
QUI est la 4e (celle a 0 coup).

CE QUE CE PROBE MESURE, ETAGE PAR ETAGE (jamais un scalaire fitte) :
  0. le REGIME du montage -- PV, armure et `maxHp` de chaque cible. `rl_duel --hp-target` force
     `Health = RemainingHealth` ET met `Armor = FixedArmor` a **0** : si tous les etages d'entree de
     l'utilite sont EGAUX, l'utilite l'est aussi et le classement est entierement decide par le
     TIE-BREAK. Cet etage doit etre lu AVANT de conclure quoi que ce soit (c'est exactement ce qui a
     fait survivre le trou d'armure de #527-r1 a sa validation).
  1. l'ORDRE SOURCE du port = ce que rend `DoomboltAbility$$GetTargets` avant tout tri
     (`Damageable(Unobscured(SurroundingEnemies(...)))`), donc l'enumeration des TUILES par
     `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`.
  2. l'UTILITE du port par cible (`engine/runner/operations/damage_utility._target_utility`).
  3. l'ORDRE FINAL du port et sa repartition de coups.
  4. l'ORDRE FINAL du natif, LU dans la sequence d'evenements du cast live (le RNG avance dans
     l'ordre d'iteration, donc la sequence des `Amount` EST la permutation).

A/B DE POSITION -- deux regimes qui ne different QUE par la position d'UNE unite. Si la victime (la
cible a 0 coup) BASCULE cote NATIF, l'ordre natif depend de la GEOMETRIE et non d'une stat de cible.
⚠ Le roster HETEROGENE (`A`/`B`/`C`) ne le permet PAS : `orksBigMek` porte le trait `Mechanic` et
POSE un `statDelta {fixedArmor: +1197}` sur ses voisins -- le DEPLACER change l'armure des autres.
Les regimes `I*`/`J1`/`K1` montent donc N x `orksNob` IDENTIQUES (memes traits, memes stats, meme
`statDelta`) : plus aucune stat de cible ne peut ordonner.

CE QUE LA MESURE A ETABLI (7 geometries, 2026-08-07, `rnca9r7q6c`) -- detail :
`docs/rl/case-494-doombolt-ordre-des-cibles.md`
  * DEUX causes independantes s'additionnent, et le montage heterogene les MELANGE ;
  * l'ordre natif a utilite EGALE n'est ni l'ordre par id (ce que le port impose) ni l'ordre
    d'enumeration des tuiles : c'est cet ordre-la ROTATE d'un cran vers la GAUCHE. La rotation est
    mesuree, y compris en PREDICTION hors echantillon (`J1` a 5 cibles, `K1` a 3), mais elle n'est
    ATTRIBUEE a aucun etage natif : les sept etages de la chaine ont ete lus et preservent tous
    l'ordre. Elle n'est donc PAS portee -- l'ecrire serait un fit.

`rc` : 2 = montage KO ; 1 = la divergence #494 est TOUJOURS presente (etat ATTENDU tant que le
residu est ouvert) ; 0 = victime identique des deux cotes.

Usage : python probe_494_doombolt_sort_order.py [--regime A|B|C|I1..I5|J1|K1] [--seed 777]
                                                [--board MC1_67] [--state-file <abs>]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.battle_query import iterate_surrounding_tiles_order_key   # noqa: E402
from engine.entities.effects.magnitude import ability_var             # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state   # noqa: E402
from engine.runner.abilities.thousandsons import (DOOMBOLT_ID, _ability_state,
                                                  doombolt_targets_selector)   # noqa: E402
from engine.runner.components import StatsComponent                   # noqa: E402
from engine.runner.messages import ActiveAbilityMessage               # noqa: E402
from engine.runner.operations.damage_utility import (_target_utility, damage_utility_weights)  # noqa: E402,E501
from engine.runner.prng import IntBasedMersenneTwister                # noqa: E402
from engine.runner.runner import Runner                               # noqa: E402
from engine.runner.snapshot import load_state                         # noqa: E402

DOOMBOLT = 1102
AHRIMAN = "thousAhriman"

# Les trois regimes ne different QUE par UNE POSITION -- memes unites, memes stats, meme seed, meme
# cible de message (`orksNob`, la seule a d = 1 dans A / a plus petit id a d = 1 dans B).
#   A = la geometrie qui a EXHIBE l'ecart (case-487 §8 : `orksRuntherd` a 3,5).
#   B = A avec `orksBigMek` DEPLACE (2,4) -> (4,3).
#   C = A avec `orksWarboss` DEPLACE (4,4) -> (1,3).
# Aucune stat ne bouge : si la victime BASCULE, c'est la GEOMETRIE qui ordonne, pas la cible.
# Chaque regime = LISTE de (visualId, (col, row)) -- une entree = UNE occurrence, donc les doublons
# sont permis (`rl_duel._parse_place_specs` : « Repeter l'option pour placer deux copies »).
#
#   A / B / C -- roster HETEROGENE (celui de case-487 §8). ⚠ Il n'est PAS un regime propre :
#     `orksBigMek` porte le trait `Mechanic` et POSE un `statDelta {fixedArmor: +1197}` sur ses
#     voisins, donc DEPLACER une unite change l'ARMURE des autres. Utile pour reproduire l'ecart
#     rapporte, inutilisable pour isoler l'ordre.
#   I1 / I2 -- roster IDENTIQUE (4 x `orksNob`) : memes traits, memes stats, meme `statDelta`, donc
#     AUCUNE stat de cible ne peut ordonner. Ce qui reste ne peut etre que la GEOMETRIE. I2 = I1
#     avec UNE SEULE unite deplacee, (2,4) -> (4,3).
REGIMES = {
    "A": [("orksNob", (3, 4)), ("orksWarboss", (4, 4)), ("orksBigMek", (2, 4)),
          ("orksRuntherd", (3, 5))],
    "B": [("orksNob", (3, 4)), ("orksWarboss", (4, 4)), ("orksBigMek", (4, 3)),
          ("orksRuntherd", (3, 5))],
    "C": [("orksNob", (3, 4)), ("orksWarboss", (1, 3)), ("orksBigMek", (2, 4)),
          ("orksRuntherd", (3, 5))],
    "I1": [("orksNob", (3, 4)), ("orksNob", (4, 4)), ("orksNob", (2, 4)), ("orksNob", (3, 5))],
    "I2": [("orksNob", (3, 4)), ("orksNob", (4, 4)), ("orksNob", (4, 3)), ("orksNob", (3, 5))],
    # I3 / I4 -- roster IDENTIQUE, geometries CHOISIES pour que les trois lois candidates rendent
    # TROIS victimes DIFFERENTES (elles se separent en UN seul tir) :
    #   I3 : lex(y,x) -> u81 | lex(x,y) -> u83 | id croissant (port) -> u85
    #   I4 = I3 avec UNE unite deplacee (3,5) -> (2,2) : lex(y,x) -> u85 | lex(x,y) -> u83
    "I3": [("orksNob", (2, 3)), ("orksNob", (1, 4)), ("orksNob", (4, 4)), ("orksNob", (3, 5))],
    "I4": [("orksNob", (2, 3)), ("orksNob", (1, 4)), ("orksNob", (4, 4)), ("orksNob", (2, 2))],
    # I5 -- separe les DEUX lois encore compatibles avec I1 et I3 :
    #   lex(y,x) ASC -> victime u83 | rotation-gauche de lex(x,y) -> victime u81 | id ASC -> u85
    "I5": [("orksNob", (2, 3)), ("orksNob", (1, 4)), ("orksNob", (1, 3)), ("orksNob", (3, 5))],
    # J1 -- CINQ unites identiques : `N = 3` sur `C = 5` -> `[1,1,1,0,0]`, donc on lit les TROIS
    # premieres places de la liste finale. C'est le test de PREDICTION de la loi mesuree sur I1/I3/I5
    # (une rotation-gauche d'UN cran ne se distingue d'une rotation de DEUX qu'a partir de 5).
    "J1": [("orksNob", (2, 3)), ("orksNob", (1, 4)), ("orksNob", (1, 3)), ("orksNob", (3, 5)),
           ("orksNob", (4, 4))],
    # K1 -- TROIS unites identiques, et c'est le seul montage qui separe les deux lectures encore
    # possibles, parce qu'il fait varier `C` (donc la REPARTITION, pas seulement l'ordre) :
    #   * la liste native compte 3 -> `r = 3 % 3 = 0` -> `[1, 1, 1]`, la cible prend UN coup ;
    #   * la liste native compte 2 (une cible ABSENTE) -> `[2, 1]`, la cible en prend DEUX.
    # `orksNob@(2,4)` est le premier dans l'enumeration de tuiles et n'est PAS la cible du message.
    "K1": [("orksNob", (3, 4)), ("orksNob", (2, 4)), ("orksNob", (4, 4))],
    # ---------------------------------------------------------------------------------------------
    # L* (#494-r1) -- les regimes qui font varier l'ELEVATION, et RIEN d'autre. Ils testent
    # l'hypothese que la « rotation d'un cran » n'est pas une loi d'ordre mais l'ombre d'une CLE de
    # tri NON CONSTANTE : `SortUnitsByDamageUtilitySelector$$Select` appelle la prediction d'attaque
    # PAR CIBLE (`IBattleQuery` slot 0x26, args `(caster, unit, casterPosition, ability, dmgMin,
    # dmgMax)`) et `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`
    # est un modifier POSITIONNEL -> deux cibles identiques sur des tuiles d'elevation differente
    # n'ont PAS la meme utilite, meme sans armure et a PV egaux.
    # Elevations du board `MC1_67` autour du caster (3,3) (lues par `tileMeta`, cf. etage 0quinquies) :
    #   elev 3 : (1,4) (2,4) (3,3)=caster (3,4) (4,3) (5,4)   |   elev 2 : (1,2) (4,4) (3,5) ...
    #
    #   L1 PLAT  -- les 4 cibles sur elev 3, comme le caster : AUCUN bonus d'elevation nulle part,
    #     donc la cle EST constante et le tri stable doit rendre l'ordre SOURCE tel quel.
    #       ordre source lex(x,y) = [81, 83, 79, 85] ; cible = u79
    #       cle constante  -> [79, 81, 83, 85]  (victime u85)
    #       rotation-gauche-> [79, 83, 85, 81]  (victime u81)
    "L1": [("orksNob", (3, 4)), ("orksNob", (1, 4)), ("orksNob", (2, 4)), ("orksNob", (5, 4))],
    #   L2 PENTE -- L1 avec la DERNIERE de l'ordre lex descendue d'un cran, (5,4) elev 3 -> (4,4)
    #     elev 2. Les trois lois rendent TROIS victimes differentes :
    #       ordre source lex(x,y) = [81, 83, 79, 85] ; cible = u79
    #       cle constante  -> [79, 81, 83, 85]  (victime u85)
    #       rotation-gauche-> [79, 83, 85, 81]  (victime u81)
    #       elevation      -> [79, 85, 81, 83]  (victime u83 -- u85 seule a beneficier du bonus)
    "L2": [("orksNob", (3, 4)), ("orksNob", (1, 4)), ("orksNob", (2, 4)), ("orksNob", (4, 4))],
    #   L3 PENTE INVERSE -- la cible qui beneficie du bonus est la PREMIERE de l'ordre lex, (1,2)
    #     elev 2 : l'elevation la GARDE en tete, la rotation l'envoie en DERNIER.
    #       ordre source lex(x,y) = [81, 83, 79, 85] ; cible = u79
    #       elevation      -> [79, 81, 83, 85]  (victime u85)
    #       rotation-gauche-> [79, 83, 85, 81]  (victime u81)
    "L3": [("orksNob", (3, 4)), ("orksNob", (1, 2)), ("orksNob", (2, 4)), ("orksNob", (5, 4))],
}
CASTER_POS = (3, 3)


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(sf.read_text())["runnerId"], None


def _live_hits(res, ability):
    """[(target_id, amount)] des coups de `ability` DANS L'ORDRE des evenements du cast."""
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def counts(seq):
    out = {}
    for tid, _a in seq:
        out[tid] = out.get(tid, 0) + 1
    return out


def _first_seen(seq):
    """L'ordre des cibles tel que le natif les a JOUEES (premiere apparition)."""
    out = []
    for tid, _a in seq:
        if tid not in out:
            out.append(tid)
    return out


def _stat(state, uid, name):
    """Une stat RESOLUE de l'unite -- elle vit sur le `UnitContext` porte par `StatsComponent.ctx`,
    pas sur le composant lui-meme."""
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None
    return getattr(ctx, name, None)


def _hp(state, uid):
    """(pv courants, pv max) LUS de l'ECS -- `decisionView` ne porte pas toujours `maxHp`."""
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None:
        return (None, None)
    return (hc.hp, hc.hp_max)


def run(regime: str = "A", seed: str = "777", board_id: str = "MC1_67",
        state_file: str | None = None, keep: bool = False, verbose: bool = False) -> dict:
    places = REGIMES[regime]
    sf = state_file or str(Path(__file__).resolve().parents[2] / "logs" / "runners"
                           / ("probe-494-doombolt-%s.json" % regime))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()
    extra = ["--p-units", AHRIMAN, "--a-units", ",".join(v for v, _p in places),
             "--place", "%s:%d,%d" % (AHRIMAN, CASTER_POS[0], CASTER_POS[1])]
    for vid, p in places:
        extra += ["--a-place", "%s:%d,%d" % (vid, p[0], p[1])]
    # `--hp-target/--hp-player` EGALISENT les PV **et mettent Armor/FixedArmor a 0** (cf. rl_duel) :
    # c'est ce qui rend le regime lisible -- aucune stat de cible ne peut alors discriminer.
    extra += ["--hp-target", "400000", "--hp-player", "400000", "--no-ai"]
    rid, err = _build(sf, seed, board_id, extra)
    if rid is None:
        return {"error": "build KO: " + str(err)}
    out: dict = {"rid": rid, "regime": regime, "seed": seed, "board": board_id, "places": places}
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        ahri = next((u for u in units if u.get("visualId") == AHRIMAN), None)
        if ahri is None:
            return {"error": "Ahriman absent du build"}
        ens = [u for u in units if u.get("owner") != ahri.get("owner")]
        if len(ens) < len(places):
            return {"error": "%d ennemis vivants pour %d places" % (len(ens), len(places))}
        ap = (ahri["pos"]["col"], ahri["pos"]["row"])
        for u in ens:
            if hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), ap) > 2:
                return {"error": "ennemi u%s hors portee (d>2) -- geometrie non montee" % u["id"]}
        # cible du message = la plus proche du caster (comme probe_487)
        target = sorted(ens, key=lambda u: (hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), ap),
                                            u["id"]))[0]

        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        # `tileMeta` -- elevation/terrain des tuiles du disque : c'est l'entree de l'obscurcissement
        # (`UnobscuredEntitiesSelector$$Select` interroge le service `+0x18` slot 7 avec
        # (caster, casterMainTile, cible)), donc la seule voie d'EXCLUSION geometrique du candidat.
        tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 40)
        tiles_meta = {}
        for t in ((tm.get("tiles") or []) if isinstance(tm, dict) else []):
            if isinstance(t, dict) and t.get("col") is not None:
                c = (int(t["col"]), int(t["row"]))
                if hexgeo.distance(c, ap) <= 2:
                    tiles_meta[c] = {k: v for k, v in t.items()
                                     if k not in ("col", "row", "neighbours")}
        # ORACLES NATIFS par cible, AVANT tout cast (read-only) : la prediction de degat que le
        # playbook natif fabrique (`MakeDamagePredictions`) et l'utilite de paire au scoreur natif
        # (`ComparablePlaybook$$CalculateUtilityFromPredictions`). Ils DECOMPOSENT l'etage : si les
        # deux sont identiques pour toutes les cibles, aucune stat ne peut ordonner -- seul l'ordre
        # SOURCE reste ; s'ils different, c'est la PREDICTION qui ordonne.
        oracle = {}
        for u in ens:
            pr = _rpc(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": ahri["id"],
                                                 "targetId": u["id"], "abilityType": DOOMBOLT}, 40)
            pu = _rpc(sid, "pairUtility", {"runnerId": rid, "unitId": ahri["id"],
                                           "targetId": u["id"], "abilityType": DOOMBOLT}, 40)
            oracle[int(u["id"])] = {"predict": pr, "pairUtility": pu}
        # `combatSnapshot.units[]` est une LISTE de lignes clees par `squadId` (= l'id d'unite de
        # `decisionView`), PAS par `entityId` (cf. l'en-tete de `engine/runner/snapshot.py`).
        raw_stats = {}
        eids = {int(u["id"]) for u in ens}
        blob = snap.get("units") if isinstance(snap, dict) else None
        rows = (list(blob.values()) if isinstance(blob, dict)
                else list(blob) if isinstance(blob, list) else [])
        for e in rows:
            if not isinstance(e, dict):
                continue
            for cle in ("squadId", "unitId", "id", "entityId"):
                k = e.get(cle)
                if k is not None and int(k) in eids:
                    raw_stats[int(k)] = e
                    break
        if not raw_stats:
            raw_stats["_brut"] = json.loads(json.dumps(snap))
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s0, dict) and s0.get("ok")):
            return {"error": "dumpRng KO: " + str(s0)[:200]}

        # --- LIVE ---------------------------------------------------------------------------------
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ahri["id"], "targetId": target["id"],
            "abilityType": DOOMBOLT}}, 90)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            return {"error": "cast Doombolt KO: " + str(res)[:250]}
        live = _live_hits(res, DOOMBOLT)

        # --- OFFLINE : meme etat, meme MT -----------------------------------------------------------
        st = load_state(dv, ob, snap, board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
        # etage 1 : l'ORDRE SOURCE du selecteur, AVANT tout tri
        ents = entities_from_state(st, ahri["id"], target["id"])
        cand = [u for u in (doombolt_targets_selector().evaluate(ents) or [])
                if isinstance(u, dict) and u.get("id") is not None]
        source_order = [int(u["id"]) for u in cand]
        # etage 0 : le REGIME
        regime_rows = []
        for u in ens:
            p = (u["pos"]["col"], u["pos"]["row"])
            hp, hp_max = _hp(st, u["id"])
            regime_rows.append({
                "id": u["id"], "visualId": u.get("visualId"), "pos": p,
                "d": hexgeo.distance(p, ap), "cube_key": iterate_surrounding_tiles_order_key(p),
                "hp": hp, "maxHp": hp_max,
                # ELEVATION de la tuile de la cible (#494-r1) : c'est une entree de la PREDICTION
                # (`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`),
                # donc de la CLE de tri -- pas seulement du dommage joue.
                "elev": (tiles_meta.get(p) or {}).get("elevation"),
                "armor": _stat(st, u["id"], "armor"),
                "fixed_armor": _stat(st, u["id"], "fixed_armor")})
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=ahri["id"], target_id=target["id"],
                                          ability_type=DOOMBOLT))
        diag = runner.ability_handler.last or {}
        off = []
        for a in (diag.get("attacks") or []):
            off += [(a["target"], h) for h in ((a.get("attack") or {}).get("per_hit") or [])]
        # etage 2 : l'utilite portee par cible, sur un etat NEUF (le cast qui precede a mute `st`)
        # et avec les MEMES arguments que le tri (`dmin == dmax`, cf. `doombolt_ordered_targets`).
        wt = damage_utility_weights()
        st2 = load_state(dv, ob, snap, board=board)
        level, mult = _ability_state(st2, ahri["id"])
        dmin = int(ability_var(DOOMBOLT_ID, "minDmg", level, multiplier_pct=mult) or 0)
        util = {int(u["id"]): _target_utility(st2, int(u["id"]), dmin, dmin, wt) for u in ens}
        # etage 5 : les LOIS CANDIDATES d'ordre SOURCE, chacune passee par le meme
        # `Remove(cible); Insert(0, cible)` que le natif -- pour qu'aucune ne soit avantagee.
        ids = [int(u["id"]) for u in ens]
        key = {int(u["id"]): iterate_surrounding_tiles_order_key(
            (u["pos"]["col"], u["pos"]["row"])) for u in ens}
        tid = int(target["id"])

        def _head(seq):
            return [tid] + [i for i in seq if i != tid]

        cube = {int(u["id"]): hexgeo.to_cube(u["pos"]["col"], u["pos"]["row"]) for u in ens}
        _sxy = [i for i in sorted(ids, key=lambda i: key[i]) if i != tid]
        lois = {
            "cube-lex (x,y) ASC + rot-G": [tid] + _sxy[1:] + _sxy[:1],
            "cube-lex (x,y) ASC": _head(sorted(ids, key=lambda i: key[i])),
            "cube-lex (x,y) DESC": _head(sorted(ids, key=lambda i: key[i], reverse=True)),
            "cube-lex (y,x) ASC": _head(sorted(ids, key=lambda i: (cube[i][1], cube[i][0]))),
            "cube-lex (z,x) ASC": _head(sorted(ids, key=lambda i: (cube[i][2], cube[i][0]))),
            "id ASCENDANT (port)": _head(sorted(ids)),
            "id DESCENDANT": _head(sorted(ids, reverse=True)),
        }
        # ce qui DIFFERE reellement entre les quatre cibles (aucune conclusion sur une stat
        # supposee : on liste toutes celles qui ne sont pas constantes)
        diff_stats = []
        cles = set()
        for e in raw_stats.values():
            if isinstance(e, dict):
                cles |= set(e)
        for c in sorted(cles):
            vals = {k: (json.dumps(v.get(c), sort_keys=True) if isinstance(v, dict) else None)
                    for k, v in raw_stats.items()}
            if len(set(vals.values())) > 1:
                diff_stats.append("%-28s %s" % (c, {k: (vals[k] or "")[:120]
                                                    for k in sorted(vals)}))
        out.update(caster_elev=(tiles_meta.get(ap) or {}).get("elevation"),
                   caster=ahri["id"], caster_pos=ap, target=target["id"], regime_rows=regime_rows,
                   source_order=source_order, util=util, dmin=dmin, lois=lois,
                   oracle=oracle, raw_stats=raw_stats, diff_stats=diff_stats,
                   tiles_meta={"%d,%d" % k: v for k, v in tiles_meta.items()},
                   port_order=diag.get("targets"), port_hits=diag.get("hits"),
                   total_hits=diag.get("total_hits"),
                   live=live, off=off, live_counts=counts(live), off_counts=counts(off),
                   live_order=_first_seen(live), off_order=_first_seen(off))
        if verbose:
            _print(out)
        return out
    finally:
        if not keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", sf],
                           cwd=str(PYDIR), capture_output=True, text=True)


def _print(r):
    print("runner %s | regime %s | board %s | seed %s" % (r["rid"], r["regime"], r["board"],
                                                          r["seed"]))
    print("caster u%s @%s | cible du message u%s" % (r["caster"], r["caster_pos"], r["target"]))
    print("\n--- etage 0 : REGIME (ce que l'utilite peut voir) ---")
    print("caster elevation = %s" % r.get("caster_elev"))
    print("%-6s %-16s %-8s %-3s %-10s %-8s %-8s %-7s %-7s %-5s"
          % ("id", "visualId", "pos", "d", "cube_key", "hp", "maxHp", "armor", "fixArm", "elev"))
    for w in r["regime_rows"]:
        print("%-6s %-16s %-8s %-3s %-10s %-8s %-8s %-7s %-7s %-5s"
              % (w["id"], w["visualId"], "%d,%d" % w["pos"], w["d"], "%d,%d" % w["cube_key"],
                 w["hp"], w["maxHp"], w["armor"], w["fixed_armor"], w.get("elev")))
    vals = {w["id"]: (w["hp"], w["maxHp"], w["armor"], w["fixed_armor"]) for w in r["regime_rows"]}
    print("REGIME EGALISE (hp/maxHp/armor/fixedArmor identiques) : %s"
          % ("OUI" if len(set(vals.values())) == 1 else "NON -- %s" % sorted(set(vals.values()))))
    # ⚠ L'EGALISATION CI-DESSUS NE COUVRE PAS L'ELEVATION, et c'est exactement le trou de #494 :
    # une cible plus BASSE que le caster recoit le bonus d'elevation, donc une PREDICTION plus
    # haute, donc une utilite plus haute -- sans qu'aucune de ses stats n'ait bouge.
    elevs = {w["id"]: w.get("elev") for w in r["regime_rows"]}
    print("ELEVATION DES CIBLES : %s -- %s"
          % (elevs, "PLATE" if len(set(elevs.values())) == 1 else "VARIABLE"))
    print("\n--- etage 0bis : ORACLES NATIFS par cible (read-only, AVANT le cast) ---")
    for k in sorted(r["oracle"]):
        o = r["oracle"][k]
        print("  u%-4s pairUtility = %s" % (k, json.dumps(o["pairUtility"])[:260]))
        print("        predict     = %s" % json.dumps(o["predict"])[:420])
    print("--- etage 0ter : stats RESOLUES brutes (combatSnapshot) + traits ---")
    for k in sorted(r["raw_stats"], key=str):
        print("  u%-4s %s" % (k, json.dumps(r["raw_stats"][k])[:900]))
    print("--- etage 0quater : ce qui DIFFERE entre les cibles (stat par stat) ---")
    for lig in r.get("diff_stats") or ["(rien)"]:
        print("  %s" % lig)
    print("--- etage 0quinquies : tuiles du disque (entree de l'obscurcissement) ---")
    for k in sorted(r.get("tiles_meta") or {}):
        print("  %-8s %s" % (k, json.dumps(r["tiles_meta"][k])[:240]))
    print("\n--- etage 1 : ORDRE SOURCE du port (GetTargets, avant tri) ---")
    print("  %s" % r["source_order"])
    print("--- etage 2 : UTILITE portee par cible (dmin=dmax=%s) ---" % r["dmin"])
    if isinstance(r["util"], dict) and "error" not in r["util"]:
        for k in sorted(r["util"]):
            print("  u%-4s %.10f" % (k, r["util"][k]))
        print("  TOUTES EGALES : %s" % ("OUI" if len(set("%.12f" % v for v in r["util"].values()))
                                        == 1 else "NON"))
    else:
        print("  %s" % r["util"])
    print("--- etage 3 : ORDRE FINAL du PORT ---")
    print("  ordre  = %s" % r["port_order"])
    print("  coups  = %s (N=%s)" % (r["port_hits"], r["total_hits"]))
    print("  frappe = %s" % r["off_counts"])
    print("--- etage 4 : ORDRE FINAL du NATIF (sequence d'evenements live) ---")
    print("  ordre joue = %s" % r["live_order"])
    print("  frappe     = %s" % r["live_counts"])
    print("  per-coup   = %s" % r["live"])
    print("--- etage 5 : LOIS CANDIDATES (ordre SOURCE, puis Remove(cible)+Insert(0,cible)) ---")
    for nom, pred in sorted(r["lois"].items()):
        print("  %-28s %s%s" % (nom, pred, "   <== CONCORDE" if pred[:len(r["live_order"])]
                                == r["live_order"] else ""))
    # ⚠ LE VERDICT PORTE SUR L'ORDRE, PAS SEULEMENT SUR LA VICTIME. Un regime ou `N % C == 0`
    # (K1 : 3 coups sur 3 cibles) n'a AUCUNE victime des deux cotes -- un critere « meme victime »
    # y rendrait ACCORD alors que la sequence jouee diverge. C'est le meme vice que le montage
    # `db-4` de `test_doombolt_live.py` : mesurer un observable que la geometrie a rendu muet.
    live_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["live_counts"]]
    off_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["off_counts"]]
    ordre_ok = r["live_order"] == r["off_order"]
    print("\nVICTIME (0 coup) : NATIF %s | PORT %s -- %s"
          % (live_zero, off_zero, "meme" if live_zero == off_zero else "DIFFERENTE"))
    print("ORDRE JOUE       : NATIF %s | PORT %s -- %s"
          % (r["live_order"], r["off_order"], "identique" if ordre_ok else "DIVERGENT"))
    print("VERDICT          : %s" % ("ACCORD" if (ordre_ok and live_zero == off_zero)
                                     else "DIVERGENCE (#494-r1)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="A", choices=sorted(REGIMES))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    r = run(regime=a.regime, seed=a.seed, board_id=a.board, state_file=a.state_file,
            keep=a.keep, verbose=True)
    if "error" in r:
        print("ERREUR:", r["error"])
        raise SystemExit(2)
    live_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["live_counts"]]
    off_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["off_counts"]]
    raise SystemExit(0 if (live_zero == off_zero and r["live_order"] == r["off_order"]) else 1)


if __name__ == "__main__":
    main()
