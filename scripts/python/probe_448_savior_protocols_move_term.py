#!/usr/bin/env python
"""#448 -- MONTAGE NOMME de la face MOVE de `SaviorProtocols` (1120) et confrontation PAR TUILE
contre le NATIF.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`
verse, PAR unite adjacente a la tuile candidate qui passe
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$TargetIsValidTrigger` :
`SAVIORPROTOCOLS_AdjacentTauFriend` (20), plus `SAVIORPROTOCOLS_AdjacentTauParent` (30) si cette
unite est le SUMMONER du mover. Le predicat a QUATRE noeuds, et ce probe monte un voisin dedie a
chacun -- un montage a un seul regime serait DEGENERE (natif et port d'accord sur 0 tandis que le
port peut etre faux partout ailleurs), et le probe ECHOUE plutot que de rendre un vert vide.

    voisin                      noeud exerce                              terme attendu
    tauAunShi     (ami, T'au, sans 1120)   ---                            +20
    tauDarkstrider(ami, T'au, AVEC 1120)   !ActorHasTriggeredAbility        0
    ultraTitus    (ami, NON-T'au)          HasFaction(Target, 9)            0
    tauShadowsun  (ENNEMI, T'au)           AreFriends(Target, Owner)        0

POURQUOI UNE GREFFE, ET POURQUOI ELLE EST LEGITIME ICI
------------------------------------------------------
1120 n'a AUCUN porteur `lineup` : 3 npc et 3 SUMMONS (`tauSmn*Drone*`). Un summon n'entre JAMAIS
dans `toActivate` (#291), donc `aiStepDryRun` -- la SEULE voie qui donne l'oracle natif du composite
`Tile(7)` par tuile (hook `scorerTileTermTrace`) -- ne peut pas l'activer. La gate `case-92` §5bis
autorise la greffe quand l'utilite ne lit ni stats ni traits du caster : ici le corps ne lit du
mover que son EQUIPE (via `AreFriends`) et son PARENT, jamais une stat ni un trait. Le greffon est
`tauCrisis`, HERO du pool et T'au -- mais sa faction n'entre PAS dans le predicat (qui porte sur le
VOISIN), donc elle n'est pas un confond.

CE QUE LA GREFFE NE COUVRE PAS : le terme PARENT. Un hero n'a pas de summoner, donc
`GetParent(case.Unit)` est nul des DEUX cotes et le noeud est inerte. Le bras `--parent` monte donc
le porteur NATUREL (drone invoque par l'attaque RANGED 1076 de `tauMarksman`, montage #443) pour
exercer ce terme-la ; l'oracle natif y est indisponible pour la meme raison (#291), et c'est dit.

DECOMPOSITION PAR ETAGE (jamais un scalaire fitte), sur les hooks EXISTANTS de
`scorer-damage-trace` (aucune reinjection ; armes pour UN SEUL `aiStepDryRun`, desarmes en
`finally`) -- meme decomposition que #193c, dont ce probe reutilise les primitives :

    X_natif(tuile) = Tile(7)  -  Elevation  -  TileEffects   (scorerTileTermTrace / Elev / Leaf)
    X_port (tuile) = Tile(7) du PORT - ses feuilles Elevation et TileEffects

VERDICTS
  V0 le porteur porte bien 1120 dans le kit LIVE que le dispatcher itere, et les DEUX poids BC
     servis sont non nuls (piege #271 : une cle a 0 ne discrimine rien).
  V1 le terme du port prend AU MOINS DEUX valeurs distinctes sur les tuiles HOOKEES -- sinon la
     mesure ne peut pas contredire le port, et le probe le dit au lieu de verdir.
  V2 X_nat == X_port sur toutes les tuiles hookees (le coeur).
  V3 le terme vaut EXACTEMENT `20 x n` ou `n` = nombre de voisins qualifies calcules depuis le
     `decisionView` -- donc les trois contre-regimes ne comptent pour rien, tuile par tuile.
  V4 SENSIBILITE : le terme RETIRE du registre change X_port sur au moins une tuile hookee.

Usage (ASCII only, depuis scripts/python) :
    python probe_448_savior_protocols_move_term.py --state-file <ABSOLU>
    python probe_448_savior_protocols_move_term.py --state-file <ABSOLU> --board C4_09 --seed 31337
    python probe_448_savior_protocols_move_term.py --state-file <ABSOLU> --parent   # bras SUMMON

Garde jumelle : `scripts/python/tests/engine/test_448_savior_protocols_move_term_live.py`.
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

import catalog_inject as CI                                      # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_193c_move_playbook_terms as P193C                   # noqa: E402
from build_pin import BuildPinRefused, require_pinned            # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.unit_faction import UnitFaction, faction_value       # noqa: E402

BOARD = "MC1_67"
SEED = "777"
ABILITY = int(TriggeredAbilityType.SaviorProtocols)          # 1120 = 0x460
ABILITY_NAME = "SaviorProtocols"
KEY_FRIEND = "SAVIORPROTOCOLS_AdjacentTauFriend"
KEY_PARENT = "SAVIORPROTOCOLS_AdjacentTauParent"
EPS = 1e-6

CARRIER = "tauCrisis"          # greffon : HERO du pool, porteur GREFFE de 1120 -- le MOVER
FRI_TAU = "tauAunShi"          # ami T'au SANS 1120                 -> +20
FRI_1120 = "tauDarkstrider"    # ami T'au AVEC 1120 greffe          ->   0
FRI_OTHER = "ultraTitus"       # ami NON-T'au (Ultramarines)        ->   0
ENE_TAU = "tauShadowsun"       # ENNEMI T'au                        ->   0
ENE_FILL = "astraCreed"        # cible d'attaque : sans elle le tier Comparable n'evalue aucune tuile

P_UNITS = [CARRIER, FRI_TAU, FRI_1120, FRI_OTHER]
A_UNITS = [ENE_TAU, ENE_FILL]
GRAFTS = [f"{CARRIER}:{ABILITY_NAME}", f"{FRI_1120}:{ABILITY_NAME}"]

# Bras `--parent` : le porteur NATUREL, monte par le tir RANGED 1076 (montage #443 reutilise tel
# quel -- une seule action invoque le drone ET marque la cible ; au CONTACT elle bascule en melee et
# ne produit NI drone NI marque, d'ou les cibles a distance 3).
SUMMONER = "tauMarksman"
DRONE = "tauSmnDroneSniper"
SUMMON_ATTACK = 1076


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


def _exiger_build_des_rva() -> None:
    """Les RVA en dur de `scorer-damage-trace` (`installRvaHooks`) valent-elles pour le build
    INSTALLE ? Meme foyer que #193c (#431) : sans ce refus, les hooks se posent sur du code
    aleatoire et le `tileTerm` lu n'est pas celui du natif."""
    require_pinned("rnca9r7q6c",
                   "les RVA en dur de scorer-damage-trace (installRvaHooks)",
                   "rafraichir les RVA_* et LEAF_HOOKS_VA du hook depuis le dump du nouveau "
                   "build, PUIS mettre ce hash a jour")


# --------------------------------------------------------------------------- montage

def _build(state_file: str, board: str, seed: str, seed_bc: str | None,
           p_units, a_units) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file,
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    if seed_bc:
        argv += ["--seed-bc", seed_bc]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not os.path.exists(state_file):
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _live_triggered(rpc, rid: int, uid: int) -> list[int]:
    """L'`AbilitiesComponent` REEL de l'unite -- la collection que le dispatcher natif itere
    (`TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2`), pas le kit gameconfig."""
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": uid}, 60) or {}
    return sorted({i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                   for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)})


def _place(sid, rpc, rid: int) -> dict:
    """Porteur au CENTRE, les quatre voisins-test sur des tuiles DISTINCTES a distance 2, la cible
    de tir plus loin -- de sorte que les tuiles candidates du porteur (anneau 1) soient adjacentes
    a des sous-ensembles DIFFERENTS de voisins, donc que le terme VARIE.

    On DEPLACE les unites plutot que d'accuser la geometrie de spawn : au spawn les deux camps sont
    aux extremites et aucune tuile candidate n'a de voisin qualifie."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    by_vis = {}
    for u in units:
        if u.get("alive") and (u.get("pos") or {}).get("col") is not None:
            by_vis.setdefault(u.get("visualId"), u)
    for vis in P_UNITS + A_UNITS:
        if vis not in by_vis:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster "
                               f"-- presents = {sorted(by_vis)}")
    myplayer = by_vis[CARRIER].get("owner")

    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    home = min(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    ring1 = [p for p in cells if hexgeo.distance(home, p) == 1]
    ring2 = [p for p in cells if hexgeo.distance(home, p) == 2]
    if len(ring1) < 4 or len(ring2) < len(P_UNITS):
        raise MontageError(f"montage NON INSTALLE : {home} n'a que {len(ring1)} tuiles a "
                           f"distance 1 et {len(ring2)} a distance 2")
    # Voisins-test SEPARES : deux voisins sur des tuiles du ring 2 mutuellement non adjacentes
    # partagent au plus une tuile du ring 1, donc les paquets de qualification different.
    chosen: list = []
    for p in ring2:
        if all(hexgeo.distance(p, q) >= 2 for q in chosen):
            chosen.append(p)
        if len(chosen) == 4:
            break
    if len(chosen) < 4:
        chosen = ring2[:4]
    # La CIBLE DE TIR est mise LOIN (anneau 5, a defaut 4) : c'est ce qui force
    # `GetBestTileToAttackFrom` a ranker PLUSIEURS tuiles d'approche -- et le hook
    # `CalculateUtilityFromTilePrediction` ne fire QUE sur les tuiles que le tier Comparable evalue.
    # MESURE : avec toutes les cibles a distance 2, le natif n'evalue qu'UNE tuile (il est deja a
    # portee) et le montage ne peut RIEN contredire. L'ennemi T'au, lui, reste PRES : c'est le
    # contre-regime `AreFriends`, il doit etre adjacent a des tuiles candidates pour valoir 0.
    far = ([p for p in cells if hexgeo.distance(home, p) == 5]
           or [p for p in cells if hexgeo.distance(home, p) == 4])
    far = [p for p in far if all(hexgeo.distance(p, q) >= 2 for q in chosen)] or far
    if not far:
        raise MontageError("montage NON INSTALLE : aucune tuile a distance 4-5 pour la cible de tir")

    wanted = {by_vis[CARRIER]["id"]: home}
    for vis, pos in zip((FRI_TAU, FRI_1120, FRI_OTHER, ENE_TAU), chosen):
        wanted[by_vis[vis]["id"]] = pos
    wanted[by_vis[ENE_FILL]["id"]] = far[0]
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    # Etat FRAIS : le drive a consomme les actions, et un `aiDryRunAllUnits` sur un etat deja score
    # ne RE-score pas -- MESURE : 0 event tileTerm. Deux `endturn` re-arment tout le monde.
    for _ in range(2):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)

    # L'event du hook ne porte PAS d'unitId, seulement la tuile candidate : pour que tout `tileTerm`
    # capte soit ATTRIBUABLE au porteur, on termine le tour de TOUTES mes autres unites.
    for vis in P_UNITS:
        if vis == CARRIER:
            continue
        rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "finish", "unitId": by_vis[vis]["id"]}}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    act = list(dv.get("toActivate") or [])
    cid = by_vis[CARRIER]["id"]
    if act != [cid]:
        raise MontageError(f"montage NON INSTALLE : toActivate={act} -- il faut EXACTEMENT "
                           f"[{cid}] pour attribuer le tileTerm au porteur")
    return {"rid": rid, "carrier": cid, "myplayer": myplayer, "home": home,
            "ids": {vis: by_vis[vis]["id"] for vis in P_UNITS + A_UNITS},
            "elev": elev, "walk": walk}


def qualified_neighbours(dv: dict, tile, carrier_id: int, elev_by_pos: dict) -> list:
    """Les voisins que `TargetIsValidTrigger` RETIENT pour cette tuile candidate, calcules depuis le
    `decisionView` (donc INDEPENDAMMENT du port teste) : allie du mover, faction T'au, sans 1120,
    != mover, et ADJACENT au sens natif (porte d'elevation `|delta| < 2`)."""
    me = next((u for u in (dv.get("units") or []) if u.get("id") == carrier_id), None)
    if me is None:
        return []
    team = me.get("owner")
    out = []
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if not u.get("alive") or p.get("col") is None or u.get("id") == carrier_id:
            continue
        if u.get("owner") != team:                                   # AreFriends(Target, Owner)
            continue
        if faction_value(u.get("visualId")) != int(UnitFaction.Tau):  # HasFaction(Target, 9, 3)
            continue
        out.append(u)
    # Le kit 1120 du voisin se lit en LIVE (une greffe n'est PAS dans le gameconfig) : c'est
    # l'appelant qui fournit `_live_1120`, pose sur les enregistrements ci-dessous.
    return [u for u in out
            if bq.is_adjacent(tile, (u["pos"]["col"], u["pos"]["row"]), elev_by_pos)
            and not u.get("_has_1120")]


# --------------------------------------------------------------------------- mesure

def measure(sid, rpc, case: dict) -> dict:
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS, load_playbook

    rid, cid = case["rid"], case["carrier"]
    live = _live_triggered(rpc, rid, cid)
    if ABILITY not in live:                                              # V0
        raise MontageError(f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent "
                           f"du porteur -- triggered live lus = {live}")
    pb = load_playbook(ABILITY)
    if pb is None:
        raise MontageError(f"l'ability {ABILITY} n'est PAS dans TRIGGERED_MOVE_PLAYBOOKS")

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, wt, _scene.build_predictor(rpc, rid))
    w_friend = float(wt.sub("TriggeredAbilities", KEY_FRIEND))
    w_parent = float(wt.sub("TriggeredAbilities", KEY_PARENT))
    if w_friend == 0 or w_parent == 0:                                   # V0 (piege #271)
        raise MontageError(f"montage NON INSTALLE : le BC servi porte {KEY_FRIEND}={w_friend} "
                           f"et {KEY_PARENT}={w_parent} -- un poids nul ne discrimine rien")

    # Kit 1120 LIVE de chaque unite : une GREFFE n'est pas dans le gameconfig, donc le seul
    # substrat honnete du noeud `!ActorHasTriggeredAbility` cote ORACLE est la lecture live.
    for u in (dv.get("units") or []):
        if u.get("id") is not None:
            u["_has_1120"] = ABILITY in _live_triggered(rpc, rid, u["id"])

    # --- armement des hooks pour UN SEUL aiStepDryRun -----------------------
    _on = rpc("scorerDamageTraceOn", {}, 90)
    _cl = rpc("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    print("  [diag] traceOn=%r clear=%r" % (_on, _cl))
    try:
        # `aiDryRunAllUnits` et NON `aiStepDryRun` : MESURE sur ce montage -- `aiStepDryRun` produit
        # bien une action (Move + ActiveAbility) mais ne fait firer AUCUN hook (0 tileTerm, 0 elev,
        # 0 damage, y compris au dump GLOBAL sans filtre d'origine), alors que `aiDryRunAllUnits`
        # sur le MEME etat en fait firer. Les autres unites ayant fini leur tour, tout event capte
        # appartient au porteur.
        dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 240)
        tterm = rpc("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elevd = rpc("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leafd = rpc("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
    finally:
        rpc("scorerDamageTraceOff", {}, 60)
    print("  [diag] allUnits=%s | tileTerm=%d elev=%d leaf=%d | action_tiles=%d plans=%d"
          % ([(u.get("unitId"), len(u.get("proposed") or [])) for u in ((dry or {}).get("units") or [])],
             len(tterm.get("entries") or []), len(elevd.get("entries") or []),
             len(leafd.get("entries") or []), len(ctx.action_tiles or []),
             len((ctx.plans.get(cid) or {}).get("evals") or [])))

    tt = P193C._by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = P193C._by_tile(elevd.get("entries") or [], "col", "row", "leaf")
    te = P193C._by_tile([e for e in (leafd.get("entries") or []) if e.get("leaf") == "TileEffects"],
                        "col", "row", "value")
    if not tt:
        raise MontageError("AUCUN event tileTerm -- hooks non armes, ou aucun tier Comparable "
                           "evalue a ce pas (le porteur n'a pas de cible a portee ?)")

    elev_by_pos = ctx.elev_by_pos
    rows = []
    for t in [t for t in (ctx.action_tiles or []) if t in tt]:
        vt, ve, vf = P193C._one(tt, t), P193C._one(el, t), P193C._one(te, t, 0.0)
        leaves, leaf_ctx = P193C._port_leaves(ctx, t)
        p_tot = sum(leaves.values())
        p_x = p_tot - leaves.get(8, 0.0) - leaves.get(9, 0.0)   # 8 = Elevation, 9 = TileEffects
        term = float(pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt))
        saved = TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY, None)
        try:
            muted = sum(P193C._port_leaves(ctx, t)[0].values()) \
                - leaves.get(8, 0.0) - leaves.get(9, 0.0)
        finally:
            TRIGGERED_MOVE_PLAYBOOKS[ABILITY] = saved
        qn = qualified_neighbours(dv, t, cid, elev_by_pos)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        rows.append({"tile": t, "tile7_nat": vt, "elev": ve, "tile_eff": vf, "x_nat": x,
                     "tile7_port": p_tot, "x_port": p_x, "x_port_muted": muted, "term": term,
                     "qualified": [u.get("visualId") for u in qn],
                     "expected": w_friend * len(qn)})
    if not rows:
        raise MontageError("aucune tuile a la fois candidate du port et hookee cote natif")
    return {"rows": rows, "w_friend": w_friend, "w_parent": w_parent, "ctx": ctx,
            "carrier": cid, "live": live}


def verdicts(res: dict) -> dict:
    rows = res["rows"]
    vals = sorted({round(r["term"], 4) for r in rows})
    v1 = len(vals) > 1
    v2 = [r for r in rows if r["x_nat"] is None or abs(r["x_nat"] - r["x_port"]) > EPS]
    v3 = [r for r in rows if abs(r["term"] - r["expected"]) > EPS]
    v4 = any(abs(r["x_port"] - r["x_port_muted"]) > EPS for r in rows)
    return {"V1_terme_variable": v1, "V1_valeurs": vals,
            "V2_desaccords": v2, "V3_non_conformes": v3, "V4_sensible": v4}


# --------------------------------------------------------------------------- bras PARENT

def parent_arm(sid, rpc, rid: int) -> dict:
    """Bras `--parent` : porteur NATUREL (`tauSmnDroneSniper`) invoque par le tir RANGED 1076 de
    `tauMarksman` -- le SEUL montage ou `GetParent(case.Unit)` est non nul, donc le seul qui exerce
    `SAVIORPROTOCOLS_AdjacentTauParent`.

    L'oracle NATIF y est indisponible : un summon n'entre jamais dans `toActivate` (#291), donc
    `aiStepDryRun` ne l'active pas et le hook `scorerTileTermTrace` n'a pas d'evaluation a capter
    qui lui soit attribuable. Ce bras mesure donc le PORT et atteste que le montage exerce bien le
    noeud -- il ne CONFRONTE pas. C'est ecrit tel quel dans le rapport, pas maquille en accord."""
    import probe_443_savior_protocols_pair_term as P443
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.utilities.tile import tile_leaf_ctx

    case = P443._stage(sid, rpc, rid)
    ctx = case["ctx"]
    leaf = tile_leaf_ctx(ctx)
    pb = load_playbook(ABILITY)
    wt = ctx.wt
    w_friend = float(wt.sub("TriggeredAbilities", KEY_FRIEND))
    w_parent = float(wt.sub("TriggeredAbilities", KEY_PARENT))
    drone, summoner = case["drone"], case["summoner"]
    if leaf.get("unit_parent_id") != summoner:
        raise MontageError(f"montage NON INSTALLE : le ctx du drone porte unit_parent_id="
                           f"{leaf.get('unit_parent_id')!r}, attendu {summoner} (le summoner) "
                           f"-- le noeud PARENT ne serait pas exerce")
    tiles = sorted({(u["pos"]["col"], u["pos"]["row"])
                    for u in (ctx.units or []) if (u.get("pos") or {}).get("col") is not None})
    out = []
    for t in [case["tile"]] + [p for p in (ctx.action_tiles or []) if p != case["tile"]]:
        out.append({"tile": t, "term": float(pb.calculate_movement_utility_in_steps(t, leaf, wt)),
                    "adj_summoner": bq.is_adjacent(
                        t, next((u["pos"]["col"], u["pos"]["row"]) for u in (ctx.units or [])
                                if u.get("id") == summoner), ctx.elev_by_pos)})
    return {"drone": drone, "summoner": summoner, "w_friend": w_friend, "w_parent": w_parent,
            "rows": out, "n_units": len(tiles)}


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--parent", action="store_true",
                    help="bras SUMMON : exerce SAVIORPROTOCOLS_AdjacentTauParent (port seul)")
    args = ap.parse_args()

    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    if args.parent:
        import probe_443_savior_protocols_pair_term as P443
        rid = _build(args.state_file, args.board, args.seed, None,
                     [SUMMONER], list(P443.FOES))
        try:
            res = parent_arm(sid, rpc, rid)
            print(f"runner {rid} | bras PARENT | drone u{res['drone']} invoque par u{res['summoner']}"
                  f" | poids {KEY_FRIEND}={res['w_friend']} {KEY_PARENT}={res['w_parent']}")
            for r in res["rows"]:
                print(f"  {str(r['tile']):<10} adj_summoner={str(r['adj_summoner']):<5} "
                      f"terme_port={r['term']:.4f}")
            hit = [r for r in res["rows"] if r["adj_summoner"]]
            exp = res["w_friend"] + res["w_parent"]
            bad = [r for r in hit if abs(r["term"] - exp) > EPS]
            print(f"  tuiles adjacentes au SUMMONER : {len(hit)} ; attendu {exp} "
                  f"(={res['w_friend']}+{res['w_parent']}) ; non conformes : {len(bad)}")
            print("  NOTE : oracle natif INDISPONIBLE sur ce bras (#291) -- port seul.")
            return 0 if hit and not bad else 1
        finally:
            if not args.keep:
                rpc("disposeRunner", {"runnerId": rid}, 30)

    seed_bc, reports = CI.write_grafted_seed_bc(
        os.path.join(os.path.dirname(os.path.dirname(_HERE)), "logs",
                     f"seedbc-448-{os.getpid()}.json"), GRAFTS, replace=True)
    rid = _build(args.state_file, args.board, args.seed, str(seed_bc), P_UNITS, A_UNITS)
    print(f"  [diag] runner {rid} construit (seed-bc greffe {seed_bc})")
    try:
        case = _place(sid, rpc, rid)
        res = measure(sid, rpc, case)
        v = verdicts(res)
        print(f"runner {rid} | board {args.board} seed {args.seed} | porteur GREFFE {CARRIER} "
              f"u{res['carrier']} @{case['home']} | kit live = {res['live']}")
        print(f"  greffes : {[(r['unitId'], r['abilityId'], r['passiveAbilitiesAfter']) for r in reports]}")
        print(f"  poids servis : {KEY_FRIEND}={res['w_friend']} {KEY_PARENT}={res['w_parent']}")
        print("\n  tuile      Tile7nat  Elev   TileEff  X_nat    | X_port   X_mute   terme  attendu  voisins")
        for r in res["rows"]:
            print("  %-10s %-9s %-6s %-8s %-8s | %-8.4g %-8.4g %-6.4g %-8.4g %s"
                  % (r["tile"], r["tile7_nat"], r["elev"], r["tile_eff"], r["x_nat"],
                     r["x_port"], r["x_port_muted"], r["term"], r["expected"], r["qualified"]))
        print(f"\n  V1 terme variable  : {v['V1_terme_variable']}  valeurs={v['V1_valeurs']}")
        print(f"  V2 desaccords nat/port : {len(v['V2_desaccords'])} / {len(res['rows'])}")
        print(f"  V3 terme != 20 x n     : {len(v['V3_non_conformes'])} / {len(res['rows'])}")
        print(f"  V4 sensible au registre: {v['V4_sensible']}")
        ok = (v["V1_terme_variable"] and not v["V2_desaccords"]
              and not v["V3_non_conformes"] and v["V4_sensible"])
        print("VERDICT: %s" % ("OK" if ok else "KO"))
        return 0 if ok else 1
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)


if __name__ == "__main__":
    raise SystemExit(main())
