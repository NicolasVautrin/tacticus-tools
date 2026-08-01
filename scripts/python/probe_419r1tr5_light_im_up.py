#!/usr/bin/env python
"""#419-r1 tranche 5 -- MONTAGE NOMME et CONFRONTATION du playbook `LightImUp` (triggered 1103).

CE QUE CE PROBE MESURE, et pourquoi c'est confrontable ETAGE PAR ETAGE
---------------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.LightImUpPlaybook` expose TROIS entrees natives distinctes, et le hook
`ncPlaybookPredict` (#369/#375) sait invoquer les trois par `via` :

    via = attackUtilityForMainTarget       -> `$$CalculateAttackUtilityForMainTarget(case, hits)`
    via = attackUtilityForSecondaryTarget  -> `$$CalculateAttackUtilityForSecondaryTarget(case, hits)`
    via = attackUtilityInSteps             -> la SM `<...InStepsInternal>d__2$$MoveNext` (5 etats)

Le port a exactement les trois pendants (`engine/playbook/light_im_up.py`). On ne compare donc PAS
un scalaire agrege : on confronte chaque etage, ce qui localise une divergence au lieu de la
diluer. `LightImUp` n'appelle JAMAIS `GetUtilityValue` (le delegue n'est meme pas capture par sa
machine a etats -- le wrapper ne stocke que `this` et `case`), donc la minoration que le hook
signale par `utilityWeightsProvided: false` NE LE CONCERNE PAS : les trois utilites rendues sont
FIDELES.

L'ATTESTATION DE REGIME, et pourquoi elle vient du NATIF SEUL
------------------------------------------------------------
La SM a trois sorties non nulles, et savoir laquelle a joue ne doit RIEN devoir au port :

    inSteps == Secondary          -> etat 3 (l'attaque normale tue A COUP SUR)
    inSteps == Main               -> etat 4 (meme normale + passif ne PEUT pas tuer)
    inSteps == (Main + Sec) / 2   -> etat 5 (issue indeterminee)

Les trois valeurs sont mesurees SEPAREMENT chez le natif : l'attestation est donc une identite
entre trois mesures natives. Une ligne dont l'etat n'est pas identifiable (deux candidats egaux,
typiquement `Main == Sec`) est rendue NON DISCRIMINANTE -- jamais lue comme un accord.

LA CONTRE-EPREUVE D'ANCRAGE (lecture 6 de l'en-tete du port)
------------------------------------------------------------
`LightImUpAbility$$GetPossibleSecondaryTargets` appelle la surcharge SIX arguments
`SurroundingEnemies(unit, unitTile, range, unique, unitSelectionType)`, dont TOUTE la geometrie
passe par `unitTile` (`SurroundingTiles(unitTile, ...) - Tiles(unitTile)`). Le playbook alimente
`AbilityEntities.CasterTile` avec `case.CasterPosition.MainTile` -- il est le SEUL des dix playbooks
attack portes a le faire. Le port en conclut que le disque est ancre sur la TUILE D'ATTAQUE, pas sur
la tuile REELLE du caster. Ce n'est PAS deductible du seul nom du champ : on le MESURE, en
interrogeant `attackUtilityForSecondaryTarget` depuis une tuile candidate `(col,row)` choisie pour
que l'ensemble des cibles secondaires y DIFFERE de celui de la tuile courante. Deux variantes du
port sont evaluees (ancrage TUILE D'ATTAQUE vs ancrage TUILE REELLE) : le montage n'a de valeur que
si elles DIVERGENT, et c'est verifie avant toute conclusion.

Usage (depuis scripts/python) :
    python probe_419r1tr5_light_im_up.py --state-file <chemin ABSOLU>   # runner deja monte
    python probe_419r1tr5_light_im_up.py --build --state-file <chemin ABSOLU>

ASCII only (cp1252). Garde jumelle : `tests/engine/test_419r1tr5_light_im_up_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.light_im_up import LightImUpPlaybook        # noqa: E402

BOARD = "MC1_67"
SEED = "419503"
RANK = 17                      # rank auquel `orksWarboss` entre au pool (cf. probe_369)
CASTER = "orksWarboss"         # << Gulgortz >>, HERO, porteur gameconfig de LightImUp
ABILITY = int(TriggeredAbilityType.LightImUp)                    # 1103
EPS = 2e-4                     # Fix64 natif (Q32.32) contre float du port

# Trois cibles ADJACENTES a des PV TRES differents : c'est ce qui separe les etats 3 / 4 / 5 de la
# machine a etats sans toucher a la geometrie. Une quatrieme unite, LOINTAINE (2..3 hex), exerce la
# gate `IsMeleeAttack` (etat 1) et sert de cible SECONDAIRE pour que le disque de rayon 3 ait de
# quoi varier d'une tuile a l'autre.
#
# `RemainingHealth` EST le champ que le natif lit -- patcher `Health` seul ne mord pas.
#
# LES BORNES NE SONT PAS DEVINEES : pour chaque cible, le port rend `raw` de l'attaque normale et
# `raw` du passif ; `etat3 <=> hp <= willBeKill(normale)`, `etat4 <=> hp > max(normale) +
# max(passif)`, `etat5` entre les deux. Mesure du montage (caster rank 17, amount 1940, 3 coups) :
# necroWarden etat3 si hp <= 4696 ; ultraTitus (source de BLOCK -> `willBeKill` faux des hp > 0)
# etat5 tant que hp <= 6268 ; admecDestroyer etat4 des hp > 11235. Le probe RE-VERIFIE l'etat par
# l'oracle natif seul -- ces valeurs ne sont que le calibrage du montage.
TARGETS = ("necroWarden", "ultraTitus", "admecDestroyer", "astraBullgryn")
HP = {"necroWarden": 400,        # etat 3 : l'attaque normale tue A COUP SUR
      "ultraTitus": 3000,        # etat 5 : issue indeterminee -> MOYENNE
      "admecDestroyer": 900000,  # etat 4 : meme normale + passif ne PEUT pas tuer
      "astraBullgryn": 30000}    # LOINTAINE -> etat 1 (gate `IsMeleeAttack` fausse)

BUILD_ARGS = ["--board", BOARD, "--rank", str(RANK), "--p-units", CASTER,
              "--a-units", ",".join(TARGETS),
              "--unit-stat", ";".join("%s:Health=%d,RemainingHealth=%d" % (v, HP[v], HP[v])
                                      for v in TARGETS)]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracle natif

def native_via(rpc, rid, cid, tgt, via, hits, tile=None, attack_ability="normalAttack") -> dict:
    """⚠ `attackAbility` est passe sur LES TROIS voies, pas seulement `attackUtilityInSteps`.

    Le natif n'appelle JAMAIS `...ForMainTarget`/`...ForSecondaryTarget` autrement que depuis sa
    propre machine a etats, dont les deux gates de tete garantissent que le case NOMME une ability.
    Un case anonyme (`Nullable<AbilityOrEffect>` sans valeur) fait evaluer FAUX a tous les predicats
    DSL `IsNormalAttack` / `IsMeleeAttack` des effets d'attaquant, et l'oracle repond alors a une
    AUTRE question. MESURE (`orksWarboss`, `ultraTitus`) : case anonyme -> `healthDmg = [699, 1047]`,
    case nommant l'attaque normale -> `[1047, 1572]`, soit un facteur 1.5 de modifiers perdu. Ne
    jamais confronter le port a la premiere de ces deux valeurs."""
    body = {"runnerId": rid, "unitId": cid, "targetId": tgt, "abilityType": ABILITY,
            "abilityKind": "triggered", "via": via, "hits": int(hits)}
    if tile is not None:
        body["col"], body["row"] = int(tile[0]), int(tile[1])
    if attack_ability is not None:
        body["attackAbility"] = attack_ability
    r = rpc("ncPlaybookPredict", body, 240) or {}
    if "abilityKind" not in r:
        raise MontageError(
            "NON CONFRONTE : le hook deploye ignore `abilityKind` (champ absent de la reponse de "
            "ncPlaybookPredict) -- fenetre de reinject requise. reponse=%r" % (str(r)[:300],))
    if r.get("playbookClass") != "LightImUpPlaybook":
        raise MontageError("KEY-SPACE : l'oracle a charge %r au lieu de LightImUpPlaybook"
                           % (r.get("playbookClass"),))
    if r.get("error"):
        raise MontageError("ncPlaybookPredict(%s) a rendu une erreur : %s" % (via, r["error"]))
    return r


def native_scalar(r: dict) -> float:
    """L'utilite d'une voie a arite 2 (`...ForMainTarget` / `...ForSecondaryTarget`)."""
    v = r.get("triggeredUtilityTotal")
    if not isinstance(v, (int, float)):
        raise MontageError("utilite native absente de la reponse : %r" % (str(r)[:300],))
    return float(v)


def native_in_steps(r: dict) -> float:
    """La SOMME des `Fix64` yieldes -- exactement ce que `TriggeredAbilitiesUtility` accumule.
    La SM de `LightImUp` ne yielde qu'UNE valeur ; on somme quand meme, comme le natif."""
    u = r.get("triggeredUtilities")
    if not isinstance(u, list):
        raise MontageError("triggeredUtilities absent de la reponse : %r" % (str(r)[:300],))
    return float(sum(u))


# --------------------------------------------------------------------------- montage

def build_case(sid, rpc, rid: int) -> dict:
    """Place le caster au CENTRE d'une etoile : trois cibles adjacentes, une quatrieme a distance.

    On DEPLACE les unites (montage NOMME reutilise : `probe_124_line_elevation_decision._drive_to`)
    plutot que d'accuser la geometrie de spawn."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError("montage NON INSTALLE : %s absent du roster" % CASTER)
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in TARGETS:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError("montage NON INSTALLE : %s absent du roster adverse" % vis)
        tgt[vis] = u["id"]

    # (a) le passif est-il bien dans l'`AbilitiesComponent` que le dispatcher itere ? Sans cette
    #     lecture, un playbook porte pourrait rester INERTE sans que rien ne rougisse (le patron
    #     que #419 recense).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            "montage NON INSTALLE : %d (LightImUp) absent de l'AbilitiesComponent de %s -- "
            "triggered live lus = %r" % (ABILITY, CASTER, sorted(set(live_ids))))

    # (b) une etoile : tuile centrale a >= 3 voisins marchables, plus une tuile a distance 2..3.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    star = None
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in hexgeo.neighbors(p[0], p[1])
              if walk.get(q) and elev.get(q) is not None and abs(elev[q] - elev[p]) < 2]
        if len(nb) < 3:
            continue
        far = [q for q in cells
               if 2 <= hexgeo.distance(p, q) <= 3 and q not in nb and walk.get(q)]
        if far:
            star = (p, nb[0], nb[1], nb[2], far[0])
            break
    if star is None:
        raise MontageError("montage NON INSTALLE : aucune etoile (3 voisins + 1 tuile a 2..3)")
    cpos, p1, p2, p3, pfar = star
    wanted = {cid: cpos, tgt[TARGETS[0]]: p1, tgt[TARGETS[1]]: p2, tgt[TARGETS[2]]: p3,
              tgt[TARGETS[3]]: pfar}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError("montage NON INSTALLE : placement incomplet -- voulu %r, obtenu %r"
                           % (wanted, {u: pos.get(u) for u in wanted}))
    P124._give_turn_back(sid, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    pb = LightImUpPlaybook()
    hits = pb._hits()
    if hits <= 0:
        raise MontageError("montage NON INSTALLE : nrOfHits = %r au gameconfig" % hits)
    return {"rid": rid, "cid": cid, "tgt": tgt, "ab": ab, "ctx": ctx, "pb": pb, "hits": hits,
            "cpos": cpos, "adj": [p1, p2, p3], "far": pfar,
            "hp": {v: ctx.scene.hp(tgt[v]) for v in TARGETS}}


# --------------------------------------------------------------------------- mesures

def measure_faces(rpc, case: dict) -> list:
    """Une ligne par cible : les TROIS voies natives contre les TROIS methodes du port, depuis la
    tuile COURANTE du caster. L'etat de la SM est attribue par les seules mesures NATIVES."""
    pb, ctx, cid, hits = case["pb"], case["ctx"], case["cid"], case["hits"]
    tile = case["cpos"]
    out = []
    for vis, uid in case["tgt"].items():
        n_main = native_scalar(native_via(rpc, case["rid"], cid, uid,
                                          "attackUtilityForMainTarget", hits, tile))
        n_sec = native_scalar(native_via(rpc, case["rid"], cid, uid,
                                         "attackUtilityForSecondaryTarget", hits, tile))
        r_steps = native_via(rpc, case["rid"], cid, uid, "attackUtilityInSteps", hits, tile,
                             attack_ability="normalAttack")
        n_steps = native_in_steps(r_steps)
        p_main = pb.calculate_attack_utility_for_main_target(ctx, cid, case["ab"], uid, tile, hits)
        p_sec = pb.calculate_attack_utility_for_secondary_target(ctx, cid, case["ab"], uid, tile,
                                                                 hits)
        p_steps = pb.calculate_attack_utility_in_steps(ctx, cid, case["ab"], uid, tile)
        out.append({"target": vis, "hp": case["hp"].get(vis),
                    "gates": r_steps.get("gates"), "abilityState": r_steps.get("abilityState"),
                    "attackAbility": r_steps.get("attackAbility"),
                    "n_main": n_main, "n_sec": n_sec, "n_steps": n_steps,
                    "p_main": p_main, "p_sec": p_sec, "p_steps": p_steps,
                    "state": attribute_state(n_main, n_sec, n_steps)})
    return out


def measure_not_regular(rpc, case: dict) -> dict:
    """ETAT 2 : le case NOMME une ability qui n'est PAS une attaque reguliere.

    On soumet `Waaagh` (l'active du meme caster) comme `attackAbility` : le natif doit rendre
    `isRegularAttack: false` et yielder un seul `Fix64(0)`, et le port doit rendre 0 sur le meme
    id (il n'est pas dans `ctx.normal_ids`). Sans cette ligne, l'etat 2 ne serait couvert par
    AUCUN montage -- et un port qui l'oublierait passerait."""
    from engine.entities.active_ability_type import ActiveAbilityType
    pb, ctx, cid = case["pb"], case["ctx"], case["cid"]
    uid = case["tgt"][TARGETS[0]]
    other = int(ActiveAbilityType.Waaagh)
    r = native_via(rpc, case["rid"], cid, uid, "attackUtilityInSteps", case["hits"], case["cpos"],
                   attack_ability=other)
    port = pb.calculate_attack_utility_in_steps(ctx, cid, other, uid, case["cpos"])
    return {"ability": other, "gates": r.get("gates"), "native": native_in_steps(r), "port": port,
            "regular_refused": (r.get("gates") or {}).get("isRegularAttack") is False}


def measure_no_secondary(case: dict) -> dict:
    """`Count == 0` : un case dont AUCUNE cible secondaire ne survit au selecteur rend `Fix64(0)`
    AVANT tout calcul de montant. On l'exerce en ancrant le disque sur une tuile qui n'a aucun
    ennemi a portee -- le regime NUL de `...ForSecondaryTarget`, distinct d'une erreur."""
    pb, ctx, cid = case["pb"], case["ctx"], case["cid"]
    sc = ctx.scene
    uid = case["tgt"][TARGETS[0]]
    rng = pb._secondary_range()
    far = None
    for p in sorted(sc.pos_by_id.values()):
        pass
    # une tuile suffisamment loin de TOUS les ennemis pour que le disque soit vide
    enemies = [sc.pos(u) for v, u in case["tgt"].items() if sc.pos(u) is not None]
    for col in range(-40, 41):
        for row in range(-40, 41):
            if all(hexgeo.distance((col, row), e) > rng for e in enemies):
                far = (col, row)
                break
        if far:
            break
    if far is None:
        return {"confronted": False, "reason": "aucune tuile hors du disque de toutes les cibles"}
    got = pb.possible_secondary_targets(sc, cid, uid, far)
    return {"confronted": True, "tile": far, "targets": got,
            "utility": pb.calculate_attack_utility_for_secondary_target(
                ctx, cid, case["ab"], uid, far, case["hits"])}


def measure_pair(rpc, case: dict) -> list:
    """ETAGE INTEGRE : le `pairUtility` natif (`ComparablePlaybook<T>$$CalculateUtilityFromPredictions`,
    qui CONTIENT la feuille `TriggeredAbilities(2)`) contre le port, et contre le port PRIVE du
    playbook 1103.

    C'est la garde de CABLAGE : le manque doit valoir EXACTEMENT le terme mesure a l'etage isole
    (`attackUtilityInSteps`). Un playbook porte mais non cable donnerait `manque = 0` partout."""
    import engine.playbook.psyker as PSY
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    ctx, cid, ab, tile = case["ctx"], case["cid"], case["ab"], case["cpos"]
    out = []
    for vis, uid in case["tgt"].items():
        r = rpc("pairUtility", {"runnerId": case["rid"], "unitId": cid, "targetId": uid,
                                "abilityType": ab, "col": tile[0], "row": tile[1]}, 120)
        nat = (r or {}).get("utility")
        if not isinstance(nat, (int, float)):
            raise MontageError("pairUtility natif indisponible pour %s : %r" % (vis, r))
        cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, uid, ab)
        if cand is None:
            raise MontageError("le port ne produit AUCUNE action sur %s depuis %r" % (vis, tile))
        port = float(cand["u"])
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError("le playbook 1103 n'est PAS au registre -- rien a muter")
        try:
            c2 = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, uid, ab)
            muted = float(c2["u"]) if c2 is not None else None
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"target": vis, "native": float(nat), "port": port, "port_muted": muted,
                    "missing": (None if muted is None else port - muted)})
    return out


def attribute_state(n_main: float, n_sec: float, n_steps: float) -> dict:
    """Quel etat de la SM le NATIF a joue ? Trois candidats, et l'attribution n'est retenue que si
    elle est UNIQUE -- sinon la ligne est NON DISCRIMINANTE (jamais un accord suppose)."""
    cands = {"etat3-secondaire": n_sec, "etat4-principal": n_main,
             "etat5-moyenne": (n_main + n_sec) / 2.0, "etats1-2-gate": 0.0}
    hit = [k for k, v in cands.items() if abs(v - n_steps) < EPS]
    return {"candidates": cands, "matched": hit,
            "state": hit[0] if len(hit) == 1 else None,
            "discriminating": len(hit) == 1}


def _anchor_variant(pb, ctx, cid, ab, uid, eval_tile, disk_tile, hits):
    """Le port evalue DEPUIS `eval_tile` (predictions, modifiers positionnels, `Unobscured`), mais
    avec le DISQUE des cibles secondaires ancre sur `disk_tile`.

    C'est la SEULE piece que la contre-epreuve fait varier : tout le reste garde la tuile
    d'evaluation. Sans cette separation on comparerait deux montages entiers, pas un ancrage."""
    real = pb.possible_secondary_targets

    def patched(scene, att_id, case_tgt_id, attack_tile):
        return real(scene, att_id, case_tgt_id, disk_tile)

    pb.possible_secondary_targets = patched
    try:
        return pb.calculate_attack_utility_for_secondary_target(ctx, cid, ab, uid, eval_tile, hits)
    finally:
        pb.possible_secondary_targets = real


def measure_anchor(rpc, case: dict) -> dict:
    """CONTRE-EPREUVE D'ANCRAGE : `attackUtilityForSecondaryTarget` depuis une tuile CANDIDATE dont
    le disque de rayon 3 ne contient PAS les memes ennemis que celui de la tuile courante.

    Deux variantes du port sont evaluees sur la MEME tuile candidate : ancrage TUILE D'ATTAQUE
    (le port livre) et ancrage TUILE REELLE. La mesure ne conclut que si les deux DIVERGENT."""
    pb, ctx, cid, hits = case["pb"], case["ctx"], case["cid"], case["hits"]
    cpos = case["cpos"]
    uid = case["tgt"][TARGETS[0]]
    rng = pb._secondary_range()
    here = set(pb.possible_secondary_targets(ctx.scene, cid, uid, cpos))
    cand = None
    for t in (ctx.action_tiles or []):
        if not t or t[0] is None or tuple(t) == tuple(cpos):
            continue
        there = set(pb.possible_secondary_targets(ctx.scene, cid, uid, t))
        if there != here:
            cand = (tuple(t), there)
            break
    if cand is None:
        return {"confronted": False,
                "reason": "aucune tuile candidate ne change l'ensemble des cibles secondaires "
                          "(rayon %d, tuiles balayees %d) -- l'ancrage n'est PAS observable ici"
                          % (rng, len(ctx.action_tiles or []))}
    tile, there = cand
    nat = native_scalar(native_via(rpc, case["rid"], cid, uid,
                                   "attackUtilityForSecondaryTarget", hits, tile))
    ab = case["ab"]
    port_attack_tile = pb.calculate_attack_utility_for_secondary_target(ctx, cid, ab, uid, tile,
                                                                        hits)
    port_real_tile = _anchor_variant(pb, ctx, cid, ab, uid, tile, cpos, hits)
    return {"confronted": True, "tile": tile, "targets_here": sorted(here),
            "targets_there": sorted(there), "native": nat,
            "port_anchor_attack_tile": port_attack_tile,
            "port_anchor_real_tile": port_real_tile,
            "discriminating": abs(port_attack_tile - port_real_tile) >= EPS}


# --------------------------------------------------------------------------- CLI

def _build(state_file: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
           "--state-file", state_file, "--no-ai"] + BUILD_ARGS
    proc = subprocess.run(cmd, cwd=_HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not os.path.exists(state_file):
        raise MontageError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file du runner")
    ap.add_argument("--build", action="store_true", help="monte le runner avant de mesurer")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()
    rid = _build(args.state_file) if args.build \
        else int(json.load(open(args.state_file, encoding="utf-8"))["runnerId"])

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    case = build_case(sid, rpc, rid)
    print("runner %d | caster u%d @%r | hits=%d | cibles %r"
          % (rid, case["cid"], case["cpos"], case["hits"], case["tgt"]))
    rows = measure_faces(rpc, case)
    bad = 0
    for r in rows:
        st = r["state"]
        print("  %-16s hp=%-8s gates=%r" % (r["target"], r["hp"], r["gates"]))
        for k in ("main", "sec", "steps"):
            n, p = r["n_" + k], r["p_" + k]
            flag = "OK " if abs(n - p) < EPS else "DIFF"
            if flag == "DIFF":
                bad += 1
            print("      %-6s natif=%12.6f port=%12.6f  d=%+.6f  %s" % (k, n, p, p - n, flag))
        print("      etat natif = %s (candidats %r)"
              % (st["state"], {k: round(v, 4) for k, v in st["candidates"].items()}))
    states = {r["state"]["state"] for r in rows}
    print("  ETATS couverts : %r" % sorted(s for s in states if s))
    nr = measure_not_regular(rpc, case)
    if abs(nr["native"] - nr["port"]) >= EPS or not nr["regular_refused"]:
        bad += 1
    print("  ETAT2 (ability non reguliere) : %s" % json.dumps(nr, default=str)[:400])
    ns = measure_no_secondary(case)
    print("  COUNT==0 : %s" % json.dumps(ns, default=str)[:300])
    anc = measure_anchor(rpc, case)
    print("  ANCRAGE : %s" % json.dumps(anc, default=str)[:600])
    steps_by_target = {r["target"]: r["n_steps"] for r in rows}
    for pr in measure_pair(rpc, case):
        d = pr["port"] - pr["native"]
        want = steps_by_target.get(pr["target"])
        okp = abs(d) < EPS and (want is None or abs((pr["missing"] or 0.0) - want) < EPS)
        if not okp:
            bad += 1
        print("  PAIRE %-16s nat=%12.6f port=%12.6f d=%+.6f | mute=%12.6f manque=%+.6f "
              "(terme isole %+.6f) %s"
              % (pr["target"], pr["native"], pr["port"], d, pr["port_muted"] or 0.0,
                 pr["missing"] or 0.0, want or 0.0, "OK" if okp else "DIFF"))
    print("  -> %s" % ("OK" if bad == 0 else "%d ecart(s)" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
