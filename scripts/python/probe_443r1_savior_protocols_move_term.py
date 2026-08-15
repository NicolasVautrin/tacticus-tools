#!/usr/bin/env python
"""#443-r1 -- MONTAGE NOMME de la face MOVE de `SaviorProtocols` (1120).

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`
verse, PAR unite adjacente a la tuile candidate qui passe
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$TargetIsValidTrigger` :
`SAVIORPROTOCOLS_AdjacentTauFriend` (20), plus `SAVIORPROTOCOLS_AdjacentTauParent` (30) si cette
unite est le SUMMONER du mover.

DEUX BRAS, ET ILS NE PROUVENT PAS LA MEME CHOSE
===============================================

`--parent` (DEFAUT DE LA VALIDATION) -- porteur NATUREL, quatre noeuds exerces
-----------------------------------------------------------------------------
Le drone `tauSmnDroneSniper` invoque par l'attaque RANGED 1076 de `tauMarksman` (montage #443
repris tel quel, `--hp-target` COMPRIS : sans lui les cibles meurent et le montage se perd). C'est
le SEUL etat ou `GetParent(case.Unit)` est non nul, donc le seul qui exerce le terme PARENT -- et
le probe REFUSE de mesurer si `unit_parent_id` ne vaut pas le summoner.

Trois voisins sont amenes APRES le tir pour exercer un noeud chacun, et le probe VERIFIE leur
exposition (nombre de tuiles balayees dont ils sont voisins) : un contre-regime qu'aucune tuile ne
voit rendrait « 0 » sans rien prouver.

    voisin                                   noeud exerce                    terme
    tauMarksman  (ami, T'au, sans 1120, PARENT)  ---                          20 + 30
    tauCrisis    (ami, T'au, sans 1120)          ---                          20
    tauDarkstrider(ami, T'au, AVEC 1120 greffe)  !ActorHasTriggeredAbility     0
    ultraTitus   (ami, NON-T'au)                 HasFaction(Target, 9)         0
    tauShadowsun (ENNEMI, T'au)                  AreFriends(Target, Owner)     0

Le terme est confronte a un attendu calcule depuis le `decisionView` + `faction_value` + le kit
LIVE (`unitAbilityStates`) -- donc SANS passer par le playbook teste. Puis CINQ contre-epreuves
mutent le port et re-jouent la MEME mesure : sur une contre-epreuve, VERT est le resultat SUSPECT.

⚠ CE QUE CE BRAS NE FAIT PAS : il ne CONFRONTE PAS au natif. Un summon n'entre jamais dans
`toActivate` (#291), donc aucune voie n'active le drone pour le hook. C'est ecrit tel quel.

Bras par defaut (GREFFE) -- il MESURE que l'oracle natif est indisponible
-------------------------------------------------------------------------
1120 greffe sur `tauCrisis` (HERO du pool ; `case-92` §5bis l'autorise : le corps ne lit du mover
que son EQUIPE et son PARENT, jamais une stat ni un trait), quatre regimes de voisinage, et la
decomposition par etage de #193c :

    X_natif(tuile) = Tile(7) - Elevation - TileEffects   (scorerTileTermTrace / Elev / Leaf)
    X_port (tuile) = Tile(7) du PORT - ses feuilles Elevation et TileEffects

TROIS faits de harnais MESURES sur ce bras, chacun ayant produit une mesure VIDE ou FAUSSE :

  1. `aiStepDryRun` ne fait firer AUCUN hook (0 tileTerm / elev / damage, y compris au dump GLOBAL
     sans filtre d'origine) alors qu'il rend bien Move + ActiveAbility ;
  2. un etat DEJA score n'est pas RE-score : le `decisionView(allAbilities, maxRank=32)` de la mise
     en place score le porteur, et tout ce qui suit ne capte plus que les AUTRES unites ;
  3. l'event du hook ne porte PAS d'unitId. MESURE : sur `MC1_67`/777, les 4 events captes sont
     TOUS sur des tuiles OCCUPEES PAR UN TIERS et AUCUN sur une tuile du porteur -- une version
     anterieure de ce probe, qui ne filtrait pas, a rendu un ACCORD PARFAIT sur le `Tile(7)` d'une
     AUTRE unite. Le filtre « tuiles attribuables au porteur » est donc load-bearing.

Conclusion de ce bras : `scorerTileTermTrace` n'attribue aucune evaluation au porteur sur ce
montage, donc le terme MOVE reste NON CONFRONTE au natif. Le point d'ancrage a hooker pour l'ouvrir
est `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
(la feuille dispatcher elle-meme, PAR TUILE) -- il demande un reinject, hors de portee d'un agent.

Usage (ASCII only, depuis scripts/python) :
    python probe_443r1_savior_protocols_move_term.py --parent --seed 41504 --state-file <ABSOLU>
    python probe_443r1_savior_protocols_move_term.py --state-file <ABSOLU>          # bras GREFFE
    python probe_443r1_savior_protocols_move_term.py --state-file <ABSOLU> --board C4_09 --seed 31337

Garde jumelle : `scripts/python/tests/engine/test_443r1_savior_protocols_move_term_live.py`.
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
from build_pin import BuildPinRefused                            # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.unit_faction import UnitFaction, faction_value       # noqa: E402
from engine.utilities.tile import UtilityType                             # noqa: E402

# Les deux feuilles que les hooks natifs instrumentent, donc les deux a retrancher des DEUX cotes.
_LEAF_ELEV = int(UtilityType.Elevation)
_LEAF_TILE_EFFECTS = int(UtilityType.TileEffects)

BOARD = "MC1_67"
SEED = "777"
ABILITY = int(TriggeredAbilityType.SaviorProtocols)          # 1120 = 0x460
ABILITY_NAME = "SaviorProtocols"
KEY_FRIEND = "SAVIORPROTOCOLS_AdjacentTauFriend"
KEY_PARENT = "SAVIORPROTOCOLS_AdjacentTauParent"
EPS = 1e-6

CARRIER = "tauCrisis"          # greffon : HERO du pool, porteur GREFFE de 1120 -- le MOVER
FRI_TAU = "tauAunShi"          # ami T'au SANS 1120                 -> +20
FRI_TAU2 = "tauMarksman"       # 2e ami T'au SANS 1120 -- exerce la LINEARITE (20 x n, pas forfait)
FRI_1120 = "tauDarkstrider"    # ami T'au AVEC 1120 greffe          ->   0
FRI_OTHER = "ultraTitus"       # ami NON-T'au (Ultramarines)        ->   0
ENE_TAU = "tauShadowsun"       # ENNEMI T'au                        ->   0
ENE_FILL = "astraCreed"        # cible d'attaque : sans elle le tier Comparable n'evalue aucune tuile

P_UNITS = [CARRIER, FRI_TAU, FRI_TAU2, FRI_1120, FRI_OTHER]
A_UNITS = [ENE_TAU, ENE_FILL]
GRAFTS = [f"{CARRIER}:{ABILITY_NAME}", f"{FRI_1120}:{ABILITY_NAME}"]

# Bras `--parent` : le porteur NATUREL, monte par le tir RANGED 1076 (montage #443 reutilise tel
# quel -- une seule action invoque le drone ET marque la cible ; au CONTACT elle bascule en melee et
# ne produit NI drone NI marque, d'ou les cibles a distance 3).
SUMMONER = "tauMarksman"
DRONE = "tauSmnDroneSniper"
SUMMON_ATTACK = 1076
EXTRA_TAU = "tauCrisis"        # ami T'au NON-PARENT du drone -> +20 SEUL : c'est lui qui SEPARE les
EXTRA_OTHER = "ultraTitus"     # deux poids (50 tout seul ne distingue pas 20+30 d'un forfait)
EXTRA_1120 = "tauDarkstrider"  # ami T'au AVEC 1120 GREFFE -> 0 ; sans lui la contre-epreuve du gate
#                                `!ActorHasTriggeredAbility` n'aurait AUCUN voisin a faire compter


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


def _exiger_build_des_rva() -> None:
    """Les RVA en dur de `scorer-damage-trace` (`installRvaHooks`) valent-elles pour le build
    INSTALLE ? Meme foyer que #193c (#431) : sans ce refus, les hooks se posent sur du code
    aleatoire et le `tileTerm` lu n'est pas celui du natif.

    ⚠ DELEGUE, et surtout PAS une copie. Ce corps portait le litteral `rnca9r7q6c` alors que
    `P193C` -- deja importe juste au-dessus -- tenait la declaration unique : la copie a
    survecu a la migration #1129 vers `t6dpr4k06g` et faisait refuser ce probe sur un build ou
    tout etait bon. C'est le meme vice qu'a repare #462-r4c, revenu par imitation.
    """
    P193C._exiger_build_des_rva()


# --------------------------------------------------------------------------- montage

def grafted_seed_bc(tag: str = ""):
    """Ecrit le seed BC GREFFE du montage (1120 sur le porteur ET sur le voisin-contre-regime) et
    rend `(chemin, rapports)`. Sortie dans `logs/` -- JAMAIS dans `data/`, qui ne contient que des
    ENTREES versionnees (garde `host_inputs.reject_data_output` dans `write_grafted_seed_bc`)."""
    out = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "logs",
                       f"seedbc-448-{tag or os.getpid()}.json")
    return CI.write_grafted_seed_bc(out, GRAFTS, replace=True)


def build_extra(seed_bc, board: str = BOARD) -> list[str]:
    """Les args `rl_duel build` du montage -- partages par le probe et sa garde jumelle, pour
    qu'aucun des deux ne monte une variante de l'autre."""
    return ["--board", board, "--p-units", ",".join(P_UNITS), "--a-units", ",".join(A_UNITS),
            "--seed-bc", str(seed_bc)]


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


# Les REGIMES du montage. La non-degenerescence ne peut PAS venir du nombre de tuiles : MESURE --
# le hook `CalculateUtilityFromTilePrediction` ne fire qu'UNE a DEUX fois par unite activee (le
# natif n'evalue le composite `Tile(7)` que sur la meilleure tuile de chaque paire ability/cible),
# et la variante ? plusieurs tuiles candidates ? a rendu 1 seul event sur trois montages differents.
# Elle vient donc des REGIMES : on RE-MESURE la meme scene apres avoir DEPLACE les voisins, et c'est
# le DELTA du natif d'un regime a l'autre qui doit valoir 20 x (nombre de voisins qualifies gagnes).
REGIMES = (
    # nom                        amis T'au sans 1120 adjacents | autres voisins adjacents
    ("R0_aucun_voisin", (), ()),
    ("R1_un_ami_tau", (FRI_TAU,), ()),
    ("R2_deux_amis_tau", (FRI_TAU, FRI_TAU2), ()),
    ("R3_contre_regimes", (FRI_TAU, FRI_TAU2), (FRI_1120, FRI_OTHER, ENE_TAU)),
)


def _geometry(sid, rpc, rid: int) -> dict:
    """Tuile centrale `home`, son anneau 1 (>= 5 tuiles libres exigees), une tuile d'ou la cible de
    tir reste ATTAQUABLE sans bouger, et un parking LOIN (>= 3) pour les voisins ecartes."""
    elev, walk, _tid = P124._board(sid, rid)
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    best, ring1 = None, []
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        r1 = [q for q in cells if hexgeo.distance(p, q) == 1
              and abs((elev.get(q) or 0) - (elev.get(p) or 0)) < 2]
        if len(r1) >= 5:
            best, ring1 = p, r1
            break
    if best is None:
        raise MontageError("montage NON INSTALLE : aucune tuile centrale avec 5 voisins libres")
    near = [p for p in cells if hexgeo.distance(best, p) == 2]
    park = [p for p in cells if hexgeo.distance(best, p) >= 4] \
        or [p for p in cells if hexgeo.distance(best, p) == 3]
    if not near or len(park) < 5:
        raise MontageError(f"montage NON INSTALLE : {best} n'a pas de tuile a distance 2 "
                           f"({len(near)}) ou pas assez de parking lointain ({len(park)})")
    # Parking MUTUELLEMENT espace : deux unites garees cote a cote resteraient adjacentes entre
    # elles, ce qui est sans effet sur le terme (qui porte sur les voisins du MOVER) mais brouille
    # la lecture du montage.
    spaced = []
    for p in park:
        if all(hexgeo.distance(p, q) >= 2 for q in spaced):
            spaced.append(p)
    return {"elev": elev, "walk": walk, "home": best, "ring1": ring1, "near": near[0],
            "park": (spaced or park)}


def _place(sid, rpc, rid: int, regime: int = 0) -> dict:
    """Installe le regime `regime` : porteur au CENTRE, la cible de tir a distance 2 (donc ATTAQUABLE
    SANS BOUGER -- c'est ce qui fait que la tuile evaluee par le natif est celle du porteur), les
    voisins du regime sur l'anneau 1, tous les autres GARES au loin.

    On DEPLACE les unites plutot que d'accuser la geometrie de spawn : au spawn les deux camps sont
    aux extremites et aucun voisin n'est adjacent au porteur."""
    geo = _geometry(sid, rpc, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    by_vis = {}
    for u in (dv.get("units") or []):
        if u.get("alive") and (u.get("pos") or {}).get("col") is not None:
            by_vis.setdefault(u.get("visualId"), u)
    for vis in P_UNITS + A_UNITS:
        if vis not in by_vis:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster "
                               f"-- presents = {sorted(by_vis)}")
    myplayer = by_vis[CARRIER].get("owner")
    name, tau_friends, others = REGIMES[regime]

    adjacent = list(tau_friends) + list(others)
    wanted = {by_vis[CARRIER]["id"]: geo["home"],
              by_vis[ENE_FILL]["id"]: geo["near"]}
    for vis, pos in zip(adjacent, geo["ring1"]):
        wanted[by_vis[vis]["id"]] = pos
    parked = [v for v in (P_UNITS + A_UNITS) if v not in adjacent
              and v not in (CARRIER, ENE_FILL)]
    for vis, pos in zip(parked, geo["park"]):
        wanted[by_vis[vis]["id"]] = pos
    if not P124._drive_to(sid, rid, geo["walk"], geo["elev"], wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"regime {name} NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    # Etat FRAIS : le drive a consomme les actions, et un `aiDryRunAllUnits` sur un etat deja score
    # ne RE-score pas. Deux `endturn` re-arment tout le monde.
    for _ in range(2):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)

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
        raise MontageError(f"regime {name} NON INSTALLE : toActivate={act} -- il faut EXACTEMENT "
                           f"[{cid}] pour attribuer le tileTerm au porteur")
    return {"rid": rid, "carrier": cid, "myplayer": myplayer, "home": geo["home"],
            "regime": name, "adjacent": adjacent,
            "ids": {vis: by_vis[vis]["id"] for vis in P_UNITS + A_UNITS},
            "elev": geo["elev"], "walk": geo["walk"]}


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

    # --- INVALIDER LE CACHE, PUIS armer, PUIS scorer ------------------------
    # TROIS faits de harnais MESURES sur ce montage, et chacun a produit une mesure vide :
    #  (a) `aiStepDryRun` ne fait firer AUCUN hook (0 tileTerm / elev / damage, y compris au dump
    #      GLOBAL sans filtre d'origine) alors qu'il rend bien Move + ActiveAbility ;
    #  (b) un etat DEJA score n'est pas RE-score : le `decisionView(allAbilities, maxRank=32)` de la
    #      mise en place score le porteur, et tout ce qui suit ne capte plus que les AUTRES unites
    #      (mesure : 4 events, tous sur des tuiles OCCUPEES par un tiers, aucun sur le porteur) ;
    #  (c) l'event du hook ne porte PAS d'unitId -- une tuile captee hors des tuiles du porteur
    #      appartient a une autre unite, et la confronter serait un FAUX ACCORD.
    # D'ou cette sequence : deux `endturn` (l'etat change -> le score du porteur est a refaire),
    # re-`finish` des autres SANS passer par `decisionView`, puis armement, puis scoring.
    for _ in range(2):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    for vis, uid in (case.get("ids") or {}).items():
        if vis in P_UNITS and vis != CARRIER:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": uid}}, 60)
    _on = rpc("scorerDamageTraceOn", {"runnerId": rid}, 90)
    rpc("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    try:
        dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 240)
        tterm = rpc("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elevd = rpc("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leafd = rpc("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
    finally:
        rpc("scorerDamageTraceOff", {"runnerId": rid}, 60)

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
    print("  [diag] traceOn=%r | allUnits=%s | tileTerm=%d elev=%d leaf=%d | action_tiles=%d plans=%d"
          % (_on,
             [(u.get("unitId"), len(u.get("proposed") or [])) for u in ((dry or {}).get("units") or [])],
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
    # Les tuiles ATTRIBUABLES au porteur : sa position courante + celles qu'il peut atteindre.
    # `aiDryRunAllUnits` evalue AUSSI les unites dont le tour est fini, et le hook ne porte PAS
    # d'unitId -- une tuile captee hors de cet ensemble appartient a une AUTRE unite, et la
    # confronter reviendrait a comparer le Tile(7) d'un tiers au composite du porteur.
    me = next((u for u in (dv.get("units") or []) if u.get("id") == cid), None)
    mp = (me or {}).get("pos") or {}
    mine = set(ctx.action_tiles or [])
    mine |= {(u.get("col"), u.get("row")) for u in ((mbu.get(cid) or {}).get("tiles") or [])}
    if mp.get("col") is not None:
        mine.add((mp["col"], mp["row"]))
    others = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
              if u.get("alive") and (u.get("pos") or {}).get("col") is not None
              and u.get("id") != cid}
    keep = sorted(t for t in tt if t in mine and t not in others)
    print("  [diag] home=%s tuiles captees=%s | attribuables au porteur=%s | occupees par un tiers=%s"
          % ((mp.get("col"), mp.get("row")), sorted(tt), keep,
             sorted(t for t in tt if t in others)))
    print("  [diag] entrees BRUTES tileTerm = %s"
          % [(e.get("casterCol"), e.get("casterRow"), e.get("tileTerm"))
             for e in (tterm.get("entries") or [])])
    rows = []
    for t in keep:
        vt, ve, vf = P193C._one(tt, t), P193C._one(el, t), P193C._one(te, t, 0.0)
        leaves, leaf_ctx = P193C._port_leaves(ctx, t)
        p_tot = sum(leaves.values())
        # Les deux feuilles INSTRUMENTEES cote natif, retirees des DEUX cotes. Les cles sont des
        # MEMBRES de `UtilityType`, jamais des litteraux (#254) : `probe_193c`, dont ce probe
        # reutilise les primitives, retranche encore `8` et `9` avec le commentaire
        # « 8=Elevation 10=TileEffects » -- une renumerotation (#252, `AttackTile` INSERE en 8) a
        # decale l'enum, si bien qu'il retranche une feuille INEXISTANTE (8) et `Elevation` (9),
        # et JAMAIS `TileEffects` (10). RESIDU `#443-r1c`, hors perimetre de cette tranche.
        p_x = p_tot - leaves.get(_LEAF_ELEV, 0.0) - leaves.get(_LEAF_TILE_EFFECTS, 0.0)
        term = float(pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt))
        saved = TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY, None)
        try:
            muted = sum(P193C._port_leaves(ctx, t)[0].values()) \
                - leaves.get(_LEAF_ELEV, 0.0) - leaves.get(_LEAF_TILE_EFFECTS, 0.0)
        finally:
            TRIGGERED_MOVE_PLAYBOOKS[ABILITY] = saved
        qn = qualified_neighbours(dv, t, cid, elev_by_pos)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        rows.append({"tile": t, "tile7_nat": vt, "elev": ve, "tile_eff": vf, "x_nat": x,
                     "tile7_port": p_tot, "x_port": p_x, "x_port_muted": muted, "term": term,
                     "qualified": [u.get("visualId") for u in qn],
                     "expected": w_friend * len(qn)})
    if not rows:
        raise MontageError("aucune tuile hookee cote natif -- le porteur n'a rien evalue")
    return {"rows": rows, "w_friend": w_friend, "w_parent": w_parent, "ctx": ctx,
            "carrier": cid, "live": live, "regime": case.get("regime"),
            "adjacent": case.get("adjacent")}


def run_regimes(sid, rpc, rid: int, regimes=None) -> list:
    """Installe et mesure CHAQUE regime sur le MEME runner. Rend la liste des resultats.

    Re-mesurer la meme scene apres avoir DEPLACE les voisins est ce qui remplace la variation par
    tuile (impossible ici, cf. `REGIMES`) : le natif doit gagner EXACTEMENT 20 par ami T'au
    qualifie devenu adjacent, et RIEN pour les trois voisins des contre-regimes."""
    out = []
    for i in (regimes if regimes is not None else range(len(REGIMES))):
        case = _place(sid, rpc, rid, i)
        res = measure(sid, rpc, case)
        out.append(res)
    return out


def verdicts(res: dict) -> dict:
    """Verdicts PAR REGIME (V2/V3/V4). La non-degenerescence (V1) est inter-regimes :
    `verdicts_across`."""
    rows = res["rows"]
    return {"V1_valeurs": sorted({round(r["term"], 4) for r in rows}),
            "V2_desaccords": [r for r in rows
                              if r["x_nat"] is None or abs(r["x_nat"] - r["x_port"]) > EPS],
            "V3_non_conformes": [r for r in rows if abs(r["term"] - r["expected"]) > EPS],
            "V4_sensible": any(abs(r["x_port"] - r["x_port_muted"]) > EPS for r in rows)}


def verdicts_across(results: list) -> dict:
    """V1 -- le terme PORTE prend au moins deux valeurs sur l'ensemble des regimes, et le DELTA du
    NATIF d'un regime a l'autre suit celui du port.

    `deltas` = [(regime_i -> regime_j, delta_natif, delta_port, delta_terme)] sur les tuiles
    COMMUNES aux deux regimes (le natif n'evalue pas forcement la meme tuile a chaque fois ; sans
    tuile commune, la paire est declaree NON COMPARABLE plutot que fittee)."""
    terms = sorted({round(r["term"], 4) for res in results for r in res["rows"]})
    deltas, ncomp = [], []
    for a, b in zip(results, results[1:]):
        ta = {r["tile"]: r for r in a["rows"]}
        tb = {r["tile"]: r for r in b["rows"]}
        common = sorted(set(ta) & set(tb))
        if not common:
            ncomp.append((a["regime"], b["regime"], sorted(ta), sorted(tb)))
            continue
        for t in common:
            deltas.append({"from": a["regime"], "to": b["regime"], "tile": t,
                           "d_nat": tb[t]["x_nat"] - ta[t]["x_nat"],
                           "d_port": tb[t]["x_port"] - ta[t]["x_port"],
                           "d_term": tb[t]["term"] - ta[t]["term"]})
    return {"V1_termes": terms, "V1_variable": len(terms) > 1,
            "deltas": deltas, "non_comparables": ncomp,
            "deltas_incoherents": [d for d in deltas
                                   if abs(d["d_nat"] - d["d_port"]) > EPS
                                   or abs(d["d_nat"] - d["d_term"]) > EPS]}


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

    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    case = P443._stage(sid, rpc, rid)
    drone, summoner = case["drone"], case["summoner"]

    # Deux voisins de PLUS, amenes APRES le tir (le montage #443 ne place que le Marksman et ses
    # deux cibles) : un ami T'au NON-PARENT (donc +20 seul, ce qui SEPARE les deux poids) et un ami
    # NON-T'au (contre-regime `HasFaction`, donc 0). Sans eux, le seul regime atteint serait
    # ? adjacent au parent ? = 50, et 50 ne distingue pas 20+30 d'un forfait.
    elev, walk, _tid = P124._board(sid, rid)
    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    by_vis = {u.get("visualId"): u for u in (dv0.get("units") or [])
              if u.get("alive") and (u.get("pos") or {}).get("col") is not None}
    dpos = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dv0.get("units") or [])
                 if u.get("id") == drone), None)
    spos = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dv0.get("units") or [])
                 if u.get("id") == summoner), None)
    if dpos is None or spos is None:
        raise MontageError("montage PERDU : drone ou summoner sans position")
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv0.get("units") or [])
                if u.get("alive") and (u.get("pos") or {}).get("col") is not None}
    free2 = [p for p in cells if p not in occupied and hexgeo.distance(dpos, p) == 2
             and not bq.is_adjacent(p, spos, elev)]
    spaced = []
    for p in free2:
        if all(hexgeo.distance(p, q) >= 2 for q in spaced):
            spaced.append(p)
    wanted = {}
    for vis, pos in zip((EXTRA_TAU, EXTRA_OTHER, EXTRA_1120, ENE_TAU), spaced or free2):
        if vis in by_vis:
            wanted[by_vis[vis]["id"]] = pos
    if wanted:
        P124._drive_to(sid, rid, walk, elev, wanted)
        P124._give_turn_back(sid, rid, by_vis[SUMMONER].get("owner"))

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, drone, wt, _scene.build_predictor(rpc, rid))
    leaf = tile_leaf_ctx(ctx)
    pb = load_playbook(ABILITY)
    w_friend = float(wt.sub("TriggeredAbilities", KEY_FRIEND))
    w_parent = float(wt.sub("TriggeredAbilities", KEY_PARENT))
    if leaf.get("unit_parent_id") != summoner:
        raise MontageError(f"montage NON INSTALLE : le ctx du drone porte unit_parent_id="
                           f"{leaf.get('unit_parent_id')!r}, attendu {summoner} (le summoner) "
                           f"-- le noeud PARENT ne serait pas exerce")
    dpos = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                 if u.get("id") == drone), dpos)

    # Kit 1120 LIVE de chaque unite -- meme substrat que le bras GREFFE.
    for u in (dv.get("units") or []):
        if u.get("id") is not None:
            u["_has_1120"] = ABILITY in _live_triggered(rpc, rid, u["id"])

    tiles = sorted(p for p in cells if hexgeo.distance(dpos, p) <= 2)
    out = []
    for t in tiles:
        qn = qualified_neighbours(dv, t, drone, ctx.elev_by_pos)
        vis = [u.get("visualId") for u in qn]
        par = any(u.get("id") == summoner for u in qn)
        out.append({"tile": t, "term": float(pb.calculate_movement_utility_in_steps(t, leaf, wt)),
                    "qualified": vis, "adj_summoner": par,
                    "expected": w_friend * len(qn) + (w_parent if par else 0.0)})
    # Les voisins des trois CONTRE-REGIMES doivent etre ADJACENTS a au moins une tuile balayee,
    # sinon leur ? 0 ? ne prouve rien (ils ne seraient comptes par personne, gate ou pas).
    exposure = {}
    for vis in (EXTRA_OTHER, EXTRA_1120, ENE_TAU):
        p = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                  if u.get("visualId") == vis and u.get("alive")
                  and (u.get("pos") or {}).get("col") is not None), None)
        exposure[vis] = (0 if p is None
                         else sum(1 for t in tiles if bq.is_adjacent(t, p, ctx.elev_by_pos)))
    return {"drone": drone, "summoner": summoner, "w_friend": w_friend, "w_parent": w_parent,
            "rows": out, "dpos": dpos, "exposure": exposure,
            "_ctx": ctx, "_leaf": leaf, "_wt": wt, "_dv": dv, "_tiles": tiles}


# --------------------------------------------------------------------------- contre-epreuves

def counter_proofs(res: dict) -> list:
    """MUTATIONS du port re-jouees sur la MESURE LIVE deja faite. Sur une contre-epreuve, VERT est
    le resultat SUSPECT : chaque bras doit rendre `mord = True`, et celui qui ne mord pas est
    DECLARE (jamais retire).

    Chaque mutation est appliquee, la mesure REFAITE sur les memes tuiles, puis l'etat RESTAURE et
    verifie identique (`restored`) -- une contre-epreuve dont la restauration derive contaminerait
    les suivantes."""
    from engine.playbook import savior_protocols as SP
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS

    ctx, leaf, wt, tiles = res["_ctx"], res["_leaf"], res["_wt"], res["_tiles"]
    base = {r["tile"]: r["term"] for r in res["rows"]}

    def _terms():
        pb = TRIGGERED_MOVE_PLAYBOOKS.get(ABILITY)
        if pb is None:
            return {t: 0.0 for t in tiles}
        return {t: float(pb.calculate_movement_utility_in_steps(t, leaf, wt)) for t in tiles}

    out = []

    def _run(name, apply_fn, undo_fn, why):
        apply_fn()
        try:
            got = _terms()
        finally:
            undo_fn()
        restored = _terms() == base
        out.append({"name": name, "mord": got != base, "restored": restored, "why": why,
                    "changed": sum(1 for t in tiles if abs(got[t] - base[t]) > EPS),
                    "sample": [(t, base[t], got[t]) for t in tiles
                               if abs(got[t] - base[t]) > EPS][:3]})

    # CE1 -- la CLE du terme FRIEND. Si le port lisait l'autre cle, 20 deviendrait 30.
    _run("CE1_cle_friend_vers_parent",
         lambda: setattr(SP, "_WEIGHT_ADJACENT_TAU_FRIEND", KEY_PARENT),
         lambda: setattr(SP, "_WEIGHT_ADJACENT_TAU_FRIEND", KEY_FRIEND),
         "l'assignation du litteral 20 a la face FRIEND")
    # CE2 / CE3 -- les deux gates du predicat, RETIRES un a un. On remplace le foyer
    # `_target_is_valid_trigger` par une variante amputee : muter la constante ne suffirait pas
    # (poser `_TAU = None` FERME le gate pour tout le monde au lieu de l'ouvrir, ce qui ferait
    # mordre la contre-epreuve pour la MAUVAISE raison).
    orig = SP._target_is_valid_trigger

    def _no_faction(neighbour, is_friend, mover_uid):
        if not is_friend:
            return False
        if SP._SAVIOR_PROTOCOLS in set(neighbour.get("triggered") or ()):
            return False
        nid, mid = neighbour.get("id"), mover_uid
        return not (nid is not None and mid is not None and int(nid) == int(mid))

    def _no_carrier_gate(neighbour, is_friend, mover_uid):
        if not is_friend:
            return False
        if faction_value(neighbour.get("vis")) != SP._TAU:
            return False
        nid, mid = neighbour.get("id"), mover_uid
        return not (nid is not None and mid is not None and int(nid) == int(mid))

    _run("CE2_gate_faction",
         lambda: setattr(SP, "_target_is_valid_trigger", _no_faction),
         lambda: setattr(SP, "_target_is_valid_trigger", orig),
         "HasFaction(Target, 9) -- exige un ami NON-T'au adjacent a une tuile balayee")
    _run("CE3_gate_porteur_1120",
         lambda: setattr(SP, "_target_is_valid_trigger", _no_carrier_gate),
         lambda: setattr(SP, "_target_is_valid_trigger", orig),
         "!ActorHasTriggeredAbility(Target, 0x460) -- exige un ami T'au PORTEUR de 1120 adjacent")

    def _no_friend_gate(neighbour, is_friend, mover_uid):
        if faction_value(neighbour.get("vis")) != SP._TAU:
            return False
        if SP._SAVIOR_PROTOCOLS in set(neighbour.get("triggered") or ()):
            return False
        nid, mid = neighbour.get("id"), mover_uid
        return not (nid is not None and mid is not None and int(nid) == int(mid))

    _run("CE5_gate_areFriends",
         lambda: setattr(SP, "_target_is_valid_trigger", _no_friend_gate),
         lambda: setattr(SP, "_target_is_valid_trigger", orig),
         "AreFriends(Target, Owner) -- exige un ENNEMI T'au adjacent a une tuile balayee")
    # CE4 -- l'entree au registre. C'est le cablage lui-meme.
    saved = [None]

    def _pop():
        saved[0] = TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY, None)

    def _push():
        if saved[0] is not None:
            TRIGGERED_MOVE_PLAYBOOKS[ABILITY] = saved[0]
    _run("CE4_registre_move", _pop, _push, "l'entree 1120 dans TRIGGERED_MOVE_PLAYBOOKS")
    return out


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
        # Le montage #443 est repris TEL QUEL, `--hp-target` COMPRIS : sans lui les cibles meurent
        # au tir qui monte le montage et le `Markerlight` expire avant la mesure (mesure).
        # Le seed BC greffe ne porte QUE `EXTRA_1120` : c'est l'ami T'au PORTEUR de 1120 sans lequel
        # la contre-epreuve du gate `!ActorHasTriggeredAbility` n'aurait aucun voisin a faire
        # compter. Le porteur MESURE, lui, reste NATUREL (le drone invoque).
        gseed, _greps = CI.write_grafted_seed_bc(
            os.path.join(os.path.dirname(os.path.dirname(_HERE)), "logs",
                         f"seedbc-448p-{os.getpid()}.json"),
            [f"{EXTRA_1120}:{ABILITY_NAME}"], replace=True)
        base = [a for a in P443.build_args(args.board)]
        base[base.index("--p-units") + 1] = ",".join(
            [SUMMONER, EXTRA_TAU, EXTRA_OTHER, EXTRA_1120])
        # `ENE_TAU` en 3e adversaire : les deux `FOES` du montage #443 sont Astra Militarum, donc
        # AUCUN ennemi T'au -- sans lui, la contre-epreuve du gate `AreFriends` n'aurait aucun
        # voisin a faire compter et resterait verte pour la mauvaise raison.
        base[base.index("--a-units") + 1] = ",".join(list(P443.FOES) + [ENE_TAU])
        argv = [sys.executable, "rl_duel.py", "build", "--seed", args.seed,
                "--state-file", args.state_file, *base, "--seed-bc", str(gseed)]
        p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0 or not os.path.exists(args.state_file):
            raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                               f"{(p.stderr or p.stdout or '')[-800:]}")
        rid = int(json.load(open(args.state_file, encoding="utf-8"))["runnerId"])
        try:
            res = parent_arm(sid, rpc, rid)
            print(f"runner {rid} | bras PARENT | drone u{res['drone']} @{res['dpos']} invoque par "
                  f"u{res['summoner']} | poids {KEY_FRIEND}={res['w_friend']} "
                  f"{KEY_PARENT}={res['w_parent']}")
            print("  tuile      terme  attendu  adj_parent  voisins qualifies")
            for r in res["rows"]:
                print("  %-10s %-6.4g %-8.4g %-11s %s"
                      % (r["tile"], r["term"], r["expected"], r["adj_summoner"], r["qualified"]))
            vals = sorted({round(r["term"], 4) for r in res["rows"]})
            bad = [r for r in res["rows"] if abs(r["term"] - r["expected"]) > EPS]
            hit = [r for r in res["rows"] if r["adj_summoner"]]
            only20 = [r for r in res["rows"] if not r["adj_summoner"] and r["qualified"]]
            print(f"  regimes atteints : termes distincts = {vals} ; tuiles adj. au PARENT = "
                  f"{len(hit)} ; tuiles a ami T'au NON-parent = {len(only20)} ; non conformes = "
                  f"{len(bad)}")
            print(f"  exposition des contre-regimes (tuiles balayees adjacentes) : {res['exposure']}")
            print("\n  CONTRE-EPREUVES (sur une contre-epreuve, VERT est le resultat SUSPECT) :")
            ces = counter_proofs(res)
            for c in ces:
                print("    %-26s mord=%-5s restaure=%-5s tuiles changees=%-3d %s"
                      % (c["name"], c["mord"], c["restored"], c["changed"],
                         "" if c["mord"] else "<-- NE MORD PAS : " + c["why"]))
            print("  NOTE : oracle natif INDISPONIBLE sur ce bras (#291) -- port seul.")
            ok = (bool(hit) and bool(only20) and not bad and len(vals) > 1
                  and all(c["restored"] for c in ces) and all(c["mord"] for c in ces))
            print("VERDICT: %s" % ("OK" if ok else "KO"))
            return 0 if ok else 1
        finally:
            if not args.keep:
                rpc("disposeRunner", {"runnerId": rid}, 30)

    seed_bc, reports = grafted_seed_bc()
    rid = _build(args.state_file, args.board, args.seed, str(seed_bc), P_UNITS, A_UNITS)
    print(f"runner {rid} | board {args.board} seed {args.seed} | porteur GREFFE {CARRIER} "
          f"| seed-bc {seed_bc}")
    print(f"  greffes : {[(r['unitId'], r['abilityId'], r['passiveAbilitiesAfter']) for r in reports]}")
    try:
        results = run_regimes(sid, rpc, rid)
        print(f"  poids servis : {KEY_FRIEND}={results[0]['w_friend']} "
              f"{KEY_PARENT}={results[0]['w_parent']} | kit live du porteur = {results[0]['live']}")
        ko = 0
        for res in results:
            v = verdicts(res)
            print("\n  == %-20s adjacents=%s" % (res["regime"], res["adjacent"]))
            print("     tuile      Tile7nat  Elev   TileEff  X_nat    | X_port   X_mute   terme"
                  "  attendu  voisins qualifies")
            for r in res["rows"]:
                print("     %-10s %-9s %-6s %-8s %-8s | %-8.4g %-8.4g %-6.4g %-8.4g %s"
                      % (r["tile"], r["tile7_nat"], r["elev"], r["tile_eff"], r["x_nat"],
                         r["x_port"], r["x_port_muted"], r["term"], r["expected"], r["qualified"]))
            print("     V2 desaccords nat/port : %d / %d | V3 terme != %s x n : %d | V4 sensible : %s"
                  % (len(v["V2_desaccords"]), len(res["rows"]), res["w_friend"],
                     len(v["V3_non_conformes"]), v["V4_sensible"]))
            ko += len(v["V2_desaccords"]) + len(v["V3_non_conformes"])
        va = verdicts_across(results)
        print("\n  V1 termes vus sur les regimes : %s (variable=%s)"
              % (va["V1_termes"], va["V1_variable"]))
        for d in va["deltas"]:
            print("     %-18s -> %-18s @%-9s d_nat=%+.4f d_port=%+.4f d_terme=%+.4f"
                  % (d["from"], d["to"], d["tile"], d["d_nat"], d["d_port"], d["d_term"]))
        if va["non_comparables"]:
            print("     NON COMPARABLES (aucune tuile commune) : %s"
                  % [(a, b) for a, b, _x, _y in va["non_comparables"]])
        ok = (ko == 0 and va["V1_variable"] and not va["deltas_incoherents"]
              and any(verdicts(r)["V4_sensible"] for r in results))
        print("VERDICT: %s" % ("OK" if ok else "KO"))
        return 0 if ok else 1
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)


if __name__ == "__main__":
    raise SystemExit(main())
