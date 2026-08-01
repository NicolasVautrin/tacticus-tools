#!/usr/bin/env python
"""Probe #415-r1 -- la face DECISION de `1111 WireweaveNet_CounterAttack` (`-30`), CONFRONTEE au natif.

QUESTION, BINAIRE. Le terme `IdunBattle.AI.Utilities.WireweaveNet_FirstAttack` (`UtilityType` 55,
poids BC `Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect` = -30) MORD-il
sur la decision NATIVE, et le port lui repond-il exactement ?

POURQUOI IL FALLAIT UN MONTAGE DEDIE. Le terme n'entre PAS dans `pairUtility` : le natif le somme un
etage PLUS HAUT, dans
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
(= `custom + CalculateUtilityFromPredictions + key-0x36(UtilityAttackCase) + Tile(7)`). L'oracle
`pairUtility` (= `...$$CalculateUtilityFromPredictions`) lui est donc STRUCTURELLEMENT AVEUGLE, et
c'est ce qui a laisse `#366-r1b` §8 ecrire « la face DECISION n'est pas confrontee live ». Le seul
oracle qui le VOIT est la DECISION elle-meme (`aiDryRunAllUnits` ->
`IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateNextActionForUnit`).

LE MONTAGE, et pourquoi il DISCRIMINE. Deux cibles ennemies dont l'utilite de PAIRE native est
EXACTEMENT EGALE (verifiee a l'oracle, `utilRaw` identique), dont UNE SEULE porte un filet 1111 ARME :

  * `CalculateActionUtility` n'a que TROIS termes cible-dependants : `pair`, `key-0x36`
    (= WireweaveNet_FirstAttack) et le custom. Le custom de l'attaque normale
    (`ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` = +1)
    ne depend pas de la cible, et `Tile(7)` ne depend que de la TUILE. A `pair` EGAL et tuile FIXE, le
    SEUL discriminant natif qui reste EST donc le terme mesure.
  * La cible qui porte le filet est ENUMEREE LA PREMIERE (rang cube `bq.iterate_surrounding_tiles_order_key`
    strictement plus petit). Comme `...$$EvaluateInternal` remplace son meilleur candidat sur
    `op_GreaterThan` STRICT, elle GAGNERAIT le tie sans le terme. Le natif qui retient l'AUTRE cible
    ne peut donc s'expliquer QUE par le -30.

Deux bras, MEME geometrie, MEME roster, un seul octet de difference :

  ARME    : `eldarRanger` garde son passif 1111 -> filet ARME (tour de l'adversaire de Calandis).
  DESARME : `--unit-stat "eldarRanger:PassiveAbilities=[]"` (montage anti-bruit de case-366-r1) ->
            aucune entite-effet 1111, terme NUL des deux cotes -> le tie revient, et la cible
            PREMIERE ENUMEREE doit gagner. C'est le REGIME OU LE TERME NE S'APPLIQUE PAS, donc le
            controle qui interdit d'attribuer au -30 un ecart qui viendrait d'ailleurs.

CASTER `tauMarksman` -- choisi, pas subi : sans `SuppressiveFire` (sinon le terme +35 de #415 casse
l'egalite de paire des que UNE seule cible porte l'overwatch) et sans `Overwatch` (sinon son tir
automatique TUE une cible a 600 PV pendant le drive de placement). Ses abilities sont RETIREES
(`ActiveAbilities=[]`, `PassiveAbilities=[]`) pour que la seule action comparable soit l'attaque
NORMALE, et celles des deux cibles aussi -- sauf le 1111 du bras ARME.

ASCII only. Usage : python probe_415_r1_wireweave_decision.py     (exit 0 = les deux bras conformes)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo  # noqa: E402
import probe_124_line_elevation_decision as P124  # noqa: E402  (montage NOMME : board/drive/natif)
from engine import battle_query as bq  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai.action_generators import ComparableAbilityGenerator  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402
from engine.utilities import wireweave_net as wwn_mod  # noqa: E402
from engine_validate import engine_decide  # noqa: E402
from rl_collect_batch import _resolve_session  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BOARD = "MC1_67"
SEED = "41171"
CASTER = "tauMarksman"          # ni SuppressiveFire ni Overwatch (cf. en-tete) ; portee 3
NET = "eldarRanger"             # Calandis -- le passif 1111 WireweaveNet
OTHER = "astraCreed"            # traits = ["Hero"] seul : aucun effet porte, aucun terme parasite
HP_TARGET = "600"               # kill deterministe des deux cotes -> `pair` sature et s'EGALISE
EPS = 1e-4                      # Fix64 natif vs float du port


# --------------------------------------------------------------------------- build


def _build(state: Path, disarm: bool, cap_wait_s: float = 900.0, poll_s: float = 20.0):
    """`rl_duel build` du montage. Le bras DESARME ne differe que par `PassiveAbilities=[]` sur
    `eldarRanger`. Attente du cap MAX_RUNNERS (session partagee -- un refus de cap n'est pas un echec
    du scenario, cf. runner.md §3)."""
    net_stat = (NET + ":ActiveAbilities=[],PassiveAbilities=[]") if disarm \
        else (NET + ":ActiveAbilities=[]")
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), "--board", BOARD,
            "--p-units", CASTER, "--a-units", f"{NET},{OTHER}",
            "--hp-target", HP_TARGET, "--hp-player", "90000",
            "--unit-stat", CASTER + ":ActiveAbilities=[],PassiveAbilities=[],Movement=0",
            "--unit-stat", net_stat,
            "--unit-stat", OTHER + ":ActiveAbilities=[],PassiveAbilities=[]"]
    waited = 0.0
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return json.loads(state.read_text())["runnerId"]
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or waited >= cap_wait_s:
            print("BUILD KO:", out[-600:])
            return None
        print(f"  cap sature, attente {poll_s:.0f}s ({waited:.0f}/{cap_wait_s:.0f})")
        time.sleep(poll_s)
        waited += poll_s


# --------------------------------------------------------------------------- geometrie


def find_pair(P: tuple, elev: dict, walk: dict, meta: dict):
    """(TA, TB) : les DEUX tuiles de cible autour de la tuile FIXE `P` du caster, choisies pour
    qu'AUCUN etage autre que le terme mesure ne puisse les separer.

      * `d(P,TA) == d(P,TB)`, entre 2 et 3 : meme portee d'arme, et jamais au CONTACT (le regime
        `RangedInMelee` de `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
        ne doit pas s'inviter d'un cote seulement) ;
      * MEME elevation (elle entre dans le modificateur d'attaquant) et MEMES flags de tuile ;
      * AUCUN effet de tuile sur les deux (le board en porte -- ex. `Melta_ExtraDmg` 1297) ;
      * `rang_cube(TA) < rang_cube(TB)` : la porteuse du filet est ENUMEREE LA PREMIERE
        (`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`), donc
        elle GAGNE le tie quand le terme ne s'applique pas -- c'est ce qui rend le bras DESARME
        discriminant ;
      * `d(TA,TB) >= 2` : les deux cibles ne sont pas adjacentes (pas de recouvrement d'AoE).

    `P` est la tuile de SPAWN du caster, qu'on ne choisit pas : le caster est EPINGLE par
    `--unit-stat Movement=0`, ce qui reduit `BattleQuery$$GetCurrentAndMovablePositionsFor` a la
    seule tuile courante. C'est ce qui SUPPRIME l'axe POSITIONNEMENT du montage : la boucle MEDIANE
    (tuiles) du natif n'a qu'un tour, donc la decision se reduit EXACTEMENT a la boucle MINEURE
    (cibles) -- celle que le terme mesure arbitre. Sans cet epinglage, le natif se DEPLACE vers la
    cible qu'il retient et la tuile qu'il choisit ne porte plus qu'UNE cible legale : l'egalite de
    paire n'y est plus verifiable et le montage cesse de discriminer (mesure du 2026-08-01).

    Deterministe (balayage trie), donc IDENTIQUE dans les deux bras -- verifie par le main."""
    neff = {p: len(m.get("effects") or []) for p, m in meta.items()}
    flags = {p: (m.get("isTerritory"), m.get("isTemporary"), m.get("isWall"))
             for p, m in meta.items()}
    cells = [p for p, w in walk.items() if w and elev.get(p) is not None]
    if not cells or P not in elev:
        return None
    cand = sorted(q for q in cells
                  if 2 <= hexgeo.distance(P, q) <= 3 and neff.get(q, 1) == 0)
    for a in cand:
        for b in cand:
            if a == b or hexgeo.distance(P, a) != hexgeo.distance(P, b):
                continue
            if elev[a] != elev[b] or flags.get(a) != flags.get(b):
                continue
            if bq.iterate_surrounding_tiles_order_key(a) >= \
                    bq.iterate_surrounding_tiles_order_key(b):
                continue
            if hexgeo.distance(a, b) < 2:
                continue
            return a, b
    return None


# --------------------------------------------------------------------------- mesure


def _pair_native(rpc, rid, cid, tgt, ab, tile):
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    return r if isinstance(r, dict) else {}


def _legal_tiles(ctx, cid, ab):
    """Tuiles d'ou l'attaque `ab` est LEGALE, par cible (`ev["ranked"]` des attackPlans natifs)."""
    plan = ctx.plans.get(cid) or {}
    out = {}
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") != ab or not ev.get("rankCount"):
            continue
        out[ev.get("targetId")] = {(r.get("col"), r.get("row")) for r in (ev.get("ranked") or [])}
    return out


def run(disarm: bool = False, verbose: bool = True) -> dict:
    """Monte UN runner, place les trois unites, et rend la mesure complete d'UN bras."""
    sid = _resolve_session()
    state = ROOT / "logs" / "runners" / f"probe415r1-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(state, disarm)
    if rid is None:
        return {"error": "build KO"}
    try:
        r = _measure(sid, rid, disarm, verbose)
        r["disarm"] = disarm
        r["rid"] = rid
        if verbose:
            _report(r)
        return r
    finally:
        P124._r(sid, "disposeRunner", {"runnerId": rid}, 30)
        state.unlink(missing_ok=True)


def _measure(sid: int, rid: int, disarm: bool, verbose: bool) -> dict:
    rpc = lambda m, b, t=90: P124._r(sid, m, b, t)          # noqa: E731
    elev, walk, _tid = P124._board(sid, rid)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    meta = {(t.get("col"), t.get("row")): t for t in (tm.get("tiles") or [])}

    dv, pos0 = P124._positions(sid, rid)
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    myplayer = next((u.get("owner") for u in mine), None)
    ea = next((u["id"] for u in (dv.get("units") or [])
               if u.get("owner") != myplayer and u.get("visualId") == NET), None)
    eb = next((u["id"] for u in (dv.get("units") or [])
               if u.get("owner") != myplayer and u.get("visualId") == OTHER), None)
    if cid is None or ea is None or eb is None:
        return {"error": f"roster incomplet (caster={cid} {NET}={ea} {OTHER}={eb})"}
    P = pos0.get(cid)                       # tuile de SPAWN -- le caster est EPINGLE (Movement=0)
    if P is None:
        return {"error": "caster sans position"}
    pr = find_pair(P, elev, walk, meta)
    if pr is None:
        return {"error": f"board {BOARD}, tuile caster {P} : aucun couple (TA, TB) conforme"}
    TA, TB = pr
    if not P124._drive_to(sid, rid, walk, elev, {ea: TA, eb: TB}):
        _d, pos = P124._positions(sid, rid)
        return {"error": f"placement incomplet : voulu {{{ea}: {TA}, {eb}: {TB}}}, "
                         f"obtenu {{{ea}: {pos.get(ea)}, {eb}: {pos.get(eb)}}}"}
    P124._give_turn_back(sid, rid, myplayer)
    _d, pos1 = P124._positions(sid, rid)
    if pos1.get(cid) != P:
        return {"error": f"le caster a BOUGE ({P} -> {pos1.get(cid)}) : l'epinglage Movement=0 "
                         f"n'a pas pris"}

    dvv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = _ai_ctx.build(rpc, rid, dvv, mbu, cid, wt, predictor)
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        return {"error": "aucune attaque normale sur le caster"}

    def _eff(uid):
        u = next((x for x in (dvv.get("units") or []) if x.get("id") == uid), {})
        return [(e.get("effectType"), e.get("active")) for e in (u.get("effects") or [])]

    # NATIF : la decision, seul oracle qui VOIT le terme.
    nat = P124._native(sid, rid, cid)
    nat_to = nat.get("to") or P

    legal = _legal_tiles(ctx, cid, ab)
    tiles = [P] + ([nat_to] if nat_to != P else [])
    action_tiles = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
    oracle = []
    for tile in tiles:
        for name, tgt in ((NET, ea), (OTHER, eb)):
            pu = _pair_native(rpc, rid, cid, tgt, ab, tile)
            cand = ComparableAbilityGenerator()._action_utility(ctx, NORMAL_ATTACK_PLAYBOOK,
                                                                ab, tgt, tile)
            oracle.append({
                "tile": tile, "who": name, "target": tgt,
                "native_pair": pu.get("utility"), "native_raw": pu.get("utilRaw"),
                "port_pair": None if cand is None else cand[2],
                "port_u_action": None if cand is None else cand[0],
                "legal": tile in legal.get(tgt, set()),
                "wwn": round(wwn_mod.wireweave_net_first_attack_utility(ctx, tile, tgt), 6),
                "armed": wwn_mod.target_has_active_wireweave_net(ctx, tgt)})

    # PORT : avec le terme, puis terme NEUTRALISE (mutation ciblee du SEUL etage suspect).
    port = _engine(sid, rid, cid, wt, predictor, dvv, mbu)
    saved = wwn_mod.wireweave_net_first_attack_utility
    wwn_mod.wireweave_net_first_attack_utility = lambda c, t, u: 0.0
    try:
        port_off = _engine(sid, rid, cid, wt, predictor, dvv, mbu)
        off = []
        for tile in tiles:
            for name, tgt in ((NET, ea), (OTHER, eb)):
                cand = ComparableAbilityGenerator()._action_utility(ctx, NORMAL_ATTACK_PLAYBOOK,
                                                                    ab, tgt, tile)
                off.append({"tile": tile, "who": name, "target": tgt,
                            "port_u_action": None if cand is None else cand[0]})
    finally:
        wwn_mod.wireweave_net_first_attack_utility = saved

    return {"board": BOARD, "P": P, "TA": TA, "TB": TB, "elev": (elev[P], elev[TA], elev[TB]),
            "dist": hexgeo.distance(P, TA),
            "caster": cid, "net_id": ea, "other_id": eb, "ability": ab,
            "action_tiles": action_tiles,
            "cube": {NET: bq.iterate_surrounding_tiles_order_key(TA),
                     OTHER: bq.iterate_surrounding_tiles_order_key(TB)},
            "effects": {NET: _eff(ea), OTHER: _eff(eb)},
            "scene_effects": {NET: sorted({e.effect_type for e in ctx.scene.effects(int(ea))})
                              if ctx.scene else None,
                              OTHER: sorted({e.effect_type for e in ctx.scene.effects(int(eb))})
                              if ctx.scene else None},
            "native": {"ability": nat.get("ability"), "target": nat.get("target"), "to": nat_to},
            "port": port, "port_without_wwn": port_off,
            "oracle": oracle, "oracle_without_wwn": off}


def _engine(sid, rid, cid, wt, predictor, dvv, mbu):
    if predictor is not None:
        _scene.refresh_shields(predictor, lambda m, b, t: P124._r(sid, m, b, t), rid)
    e = engine_decide(sid, rid, dvv, mbu, cid, wt, predictor)
    return {"ability": e.get("ability") if e.get("kind") == "ability" else None,
            "target": e.get("target"), "to": e.get("to"), "kind": e.get("kind")}


# --------------------------------------------------------------------------- rapport


def _report(r: dict) -> None:
    if "error" in r:
        print("ERREUR:", r["error"])
        return
    bras = "DESARME" if r["disarm"] else "ARME"
    print(f"runner {r['rid']} board {r['board']} bras {bras}")
    print(f"  P={r['P']} TA({NET})={r['TA']} TB({OTHER})={r['TB']} elevations={r['elev']} "
          f"d(P,cible)={r['dist']} action_tiles={r['action_tiles']}")
    print(f"  rangs cube (ordre d'enumeration natif, croissant) : {r['cube']}")
    print(f"  caster={r['caster']} {NET}={r['net_id']} {OTHER}={r['other_id']} ability={r['ability']}")
    for who in (NET, OTHER):
        print(f"  effets {who}: dv={r['effects'][who]} scene_port={r['scene_effects'][who]}")
    print("  ORACLE par (tuile, cible) -- pair NATIF, pair PORT, u_action PORT, terme wwn :")
    for e in r["oracle"]:
        print(f"    {e['tile']} {e['who']:<12} legal={str(e['legal']):<5} "
              f"pair_natif={e['native_pair']} raw={e['native_raw']} "
              f"pair_port={None if e['port_pair'] is None else round(e['port_pair'], 6)} "
              f"u_action={None if e['port_u_action'] is None else round(e['port_u_action'], 4)} "
              f"wwn={e['wwn']} arme={e['armed']}")
    print("  u_action PORT avec le terme NEUTRALISE :")
    for e in r["oracle_without_wwn"]:
        print(f"    {e['tile']} {e['who']:<12} "
              f"u_action={None if e['port_u_action'] is None else round(e['port_u_action'], 4)}")
    print(f"  NATIF                      : {r['native']}")
    print(f"  PORT  (terme ACTIF)        : {r['port']}")
    print(f"  PORT  (terme NEUTRALISE)   : {r['port_without_wwn']}")


# --------------------------------------------------------------------------- verdict


def verdict(arme: dict, desarme: dict) -> list:
    """Les DEUX volets, sur les DEUX bras. Rend la liste des echecs (vide = tout vert)."""
    fails: list = []
    wt = W.load()
    weight = float(wt.category("WireweaveNet_FirstAttack")
                   .get(wwn_mod.WIREWEAVENET_ADJACENT_ACTIVE_EFFECT, 0.0))
    if weight == 0:
        fails.append("le BC courant ne porte pas WIREWEAVENET_AdjacentActiveEffect : "
                     "le montage ne discrimine rien")
    for bras, r in (("arme", arme), ("desarme", desarme)):
        if "error" in r:
            fails.append(f"[{bras}] {r['error']}")
            continue
        P = r["P"]
        # (0) LE REGIME DISTANT. Le conjoint `IsAdjacentTo` du corps natif compare
        # `case.CasterPosition.MainTile` A LUI-MEME (les deux operandes sortent du MEME `case+0x18`,
        # lu au decompile) : ce n'est PAS un gate d'adjacence caster/cible, donc le malus doit tomber
        # AUSSI a distance. Mesurer a distance >= 2 est ce qui FALSIFIE la lecture « adjacence » que
        # le nom de la cle (`..._AdjacentActiveEffect`) suggere -- au CONTACT les deux lectures
        # predisent la meme chose et le montage ne trancherait rien.
        if r["dist"] < 2:
            fails.append(f"[{bras}] cibles au CONTACT (d={r['dist']}) : le montage ne falsifie pas "
                         f"la lecture « gate d'adjacence » du conjoint")
        # (0bis) L'EPINGLAGE : une seule tuile d'action, et le natif ne bouge pas. Sans lui la boucle
        # MEDIANE (tuiles) se re-invite et la tuile retenue ne porte plus qu'UNE cible legale.
        if r["action_tiles"] != [P]:
            fails.append(f"[{bras}] le caster n'est PAS epingle : action_tiles={r['action_tiles']} "
                         f"(attendu [{P}]) -- l'axe POSITIONNEMENT rentrerait dans la mesure")
        if r["native"]["to"] != P:
            fails.append(f"[{bras}] le natif se DEPLACE ({P} -> {r['native']['to']}) alors que le "
                         f"caster est epingle")
        rows = [e for e in r["oracle"] if e["tile"] == P]
        if len(rows) != 2:
            fails.append(f"[{bras}] pas de mesure d'oracle sur la tuile epinglee {P}")
            continue
        # (1) EGALITE DE PAIRE -- sans elle l'ecart pourrait venir de n'importe quel autre terme.
        pa, pb = rows[0]["native_pair"], rows[1]["native_pair"]
        if pa is None or pb is None or abs(float(pa) - float(pb)) > EPS:
            fails.append(f"[{bras}] pairUtility NATIF INEGAL sur {P} : {pa} vs {pb} -- "
                         f"le montage ne discrimine RIEN")
        if rows[0]["native_raw"] != rows[1]["native_raw"]:
            fails.append(f"[{bras}] pairUtility NATIF (Fix64 brut) inegal sur {P} : "
                         f"{rows[0]['native_raw']} vs {rows[1]['native_raw']}")
        # (2) MON PROPRE PORT d'abord : un fork en amont donnerait un faux ecart.
        for e in rows:
            if e["port_pair"] is None or abs(float(e["port_pair"]) - float(e["native_pair"])) > EPS:
                fails.append(f"[{bras}] le PORT diverge du natif DES l'etage `pair` sur "
                             f"{e['tile']}/{e['who']} : natif={e['native_pair']} "
                             f"port={e['port_pair']} -- l'ecart de decision ne serait pas "
                             f"attribuable au terme mesure")
            if not e["legal"]:
                fails.append(f"[{bras}] la cible {e['who']} n'est PAS legale depuis la tuile "
                             f"epinglee {P} : l'ecart s'expliquerait par la LEGALITE")
        # (3) CONFORMITE
        if r["port"]["target"] != r["native"]["target"] \
                or r["port"]["ability"] != r["native"]["ability"] \
                or r["port"]["to"] not in (None, r["native"]["to"]):
            fails.append(f"[{bras}] port {r['port']} != natif {r['native']}")
        # (4) le regime attendu de CHAQUE bras
        if not r["disarm"]:
            if r["native"]["target"] != r["other_id"]:
                fails.append(f"[bras arme] le natif retient {r['native']['target']}, pas la cible "
                             f"SANS filet ({r['other_id']}) : le terme ne mord pas")
            if r["port_without_wwn"]["target"] != r["net_id"]:
                fails.append(f"[bras arme] terme NEUTRALISE, le port retient "
                             f"{r['port_without_wwn']['target']} et non la porteuse du filet "
                             f"({r['net_id']}) : le montage n'est PAS discriminant")
        else:
            if r["native"]["target"] != r["net_id"]:
                fails.append(f"[bras desarme] le natif retient {r['native']['target']} et non la "
                             f"PREMIERE ENUMEREE ({r['net_id']}) : le tie ne se lit pas")
            if r["port_without_wwn"]["target"] != r["port"]["target"]:
                fails.append(f"[bras desarme] neutraliser le terme CHANGE la decision du port "
                             f"({r['port']['target']} -> {r['port_without_wwn']['target']}) : "
                             f"il n'est pas inerte dans le regime ou il ne s'applique pas")
        # (5) DISCRIMINANCE NUMERIQUE : l'ecart au terme neutralise vaut EXACTEMENT le poids.
        off = {(e["tile"], e["who"]): e["port_u_action"] for e in r["oracle_without_wwn"]}
        for e in r["oracle"]:
            o = off.get((e["tile"], e["who"]))
            if e["port_u_action"] is None or o is None:
                continue
            d = float(e["port_u_action"]) - float(o)
            want = weight if (e["who"] == NET and not r["disarm"]) else 0.0
            if abs(d - want) > EPS:
                fails.append(f"[{bras}] {e['tile']}/{e['who']} : le terme pese {d} au lieu de "
                             f"{want} (poids BC = {weight})")
    return fails


def main() -> int:
    import os
    only = os.environ.get("BRAS", "")            # "arme" / "desarme" / vide = les deux
    out = {}
    for bras, disarm in (("arme", False), ("desarme", True)):
        if only and only != bras:
            continue
        print(f"===== BRAS {bras.upper()} =====")
        out[bras] = run(disarm=disarm)
        print()
    if len(out) < 2:
        return 0 if "error" not in next(iter(out.values())) else 1
    arme, desarme = out["arme"], out["desarme"]
    if "error" not in arme and "error" not in desarme:
        if (arme["P"], arme["TA"], arme["TB"]) != (desarme["P"], desarme["TA"], desarme["TB"]):
            print("ATTENTION : geometries DIFFERENTES entre les deux bras -- "
                  f"{(arme['P'], arme['TA'], arme['TB'])} vs "
                  f"{(desarme['P'], desarme['TA'], desarme['TB'])}")
        print("===== A/B =====")
        print(f"  natif ARME    : cible={arme['native']['target']} (sans filet = "
              f"{arme['other_id']}, avec filet = {arme['net_id']})")
        print(f"  natif DESARME : cible={desarme['native']['target']}")
        print("  VERDICT : le natif " + ("CHANGE" if arme["native"]["target"]
                                         != desarme["native"]["target"] else "NE CHANGE PAS")
              + " de cible quand le filet disparait -> le terme "
              + ("MORD" if arme["native"]["target"] != desarme["native"]["target"]
                 else "NE MORD PAS") + " sur la face DECISION.")
    fails = verdict(arme, desarme)
    print()
    if fails:
        print("FAILS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK -- les deux bras sont CONFORMES et le montage est DISCRIMINANT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
