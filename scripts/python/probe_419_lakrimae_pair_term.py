"""#419 -- MONTAGE NOMME du terme `Lakrimae_LikesNonMechanicalEnemies` (5) sur la face ATTACK, et
mesure natif contre port.

L'objet est DOUBLE, et c'est le patron que #419 recense :

  1. le PLAYBOOK -- `IdunBattle.AI.Playbook.Loki.LakrimaePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
     verse le poids quand la CIBLE n'a PAS le trait `Mechanical` (`UnitTrait` 5), 0 sinon ;
  2. le CABLAGE -- l'ability 1541 arrive par une RELIQUE (`items.R_Crit_Lakrimae.abilityId`,
     `allowedUnits = [deathTyphus]`), donc par `UnitConfiguration.TertiaryAbility` : le kit
     gameconfig ne la contient PAS. Sans la lecture du canal live dans
     `engine/utilities/tile.py::TriggeredAbilitiesUtility.evaluate_attack_in_steps`, le dispatcher
     n'itere JAMAIS 1541 et le playbook est INERTE -- porte + non cable, sans erreur ni test rouge.

Le montage exige donc les deux, et il ECHOUE (il ne skippe pas, #268) si l'un manque : la relique
absente de l'`AbilitiesComponent` live, ou les DEUX regimes de cible (mecanique / non mecanique) non
reunis, invalident la mesure.

Le poids vient du BC RAFRAICHI : la capture `data/seed-bc.json` porte
`Lakrimae_LikesNonMechanicalEnemies` a **0**, le gameconfig vivant a **5**, et c'est
`catalog_inject.refresh_ai_utilities` qui sert le vivant aux DEUX cotes. C'est exactement le piege
#271 : sans ce refresh, natif et port liraient tous deux 0, seraient parfaitement d'accord, et
FAUX -- le probe verifie donc que le poids lu n'est pas nul avant de conclure quoi que ce soit.

Usage :
    python scripts/python/probe_419_lakrimae_pair_term.py [--state-file <chemin ABSOLU>]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_419_lakrimae_pair_term_live.py`.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.traits.unit_trait import (UnitTrait,        # noqa: E402
                                               entity_trait_ids)
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "deathTyphus"          # SEUL `allowedUnits` de l'item relique `R_Crit_Lakrimae`
TGT_MECH = "admecDestroyer"     # trait `Mechanical` -> le predicat coupe, terme = 0
TGT_SOFT = "astraBullgryn"      # pas `Mechanical` -> le poids tombe
ABILITY = int(TriggeredAbilityType.Lakrimae)                 # 1541
WEIGHT_KEY = "Lakrimae_LikesNonMechanicalEnemies"
MECHANICAL = int(UnitTrait.Mechanical)                      # 5
EPS = 1e-4                      # Fix64 natif contre float du port

BUILD_ARGS = ["--board", BOARD, "--p-units", CASTER,
              "--a-units", f"{TGT_MECH},{TGT_SOFT}",
              "--equip-relic", f"{CASTER}:Lakrimae"]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


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


def build_case(sid, rpc, rid: int) -> dict:
    """Place le caster AU CONTACT des deux cibles et rend tout ce qu'il faut pour mesurer.

    Le drive est indispensable : hors portee d'arme, `pairUtility` rend le seul terme triggered
    tandis que le port produit quand meme sa composante de degat -- les deux cotes ne parlent alors
    pas de la meme chose. On DEPLACE donc les unites plutot que d'accuser la geometrie de spawn
    (montage NOMME reutilise : `probe_124_line_elevation_decision._drive_to`)."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in (TGT_MECH, TGT_SOFT):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        tgt[vis] = u["id"]

    # (a) LA RELIQUE EST-ELLE MONTEE ? C'est la moitie CABLAGE du cas : sans 1541 dans
    #     l'AbilitiesComponent, le dispatcher ne l'itere pas et la mesure ne prouverait rien.
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : la relique Lakrimae ({ABILITY}) n'est PAS dans "
            f"l'AbilitiesComponent de {CASTER} -- triggered live lus = {sorted(set(live_ids))}")

    # (b) Trois tuiles mutuellement adjacentes : le caster au centre, une cible de chaque cote.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    trio = None
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in hexgeo.neighbors(p[0], p[1])
              if walk.get(q) and elev.get(q) is not None and abs(elev[q] - elev[p]) < 2]
        if len(nb) >= 2:
            trio = (p, nb[0], nb[1])            # (caster, cible mech, cible soft)
            break
    if trio is None:
        raise MontageError("montage NON INSTALLE : aucune tuile walkable a 2 voisins walkables")
    cpos, mpos, spos = trio
    wanted = {cid: cpos, tgt[TGT_MECH]: mpos, tgt[TGT_SOFT]: spos}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")

    # (c) LES DEUX REGIMES DE CIBLE. Le trait est relu au foyer d'ENTITE (#225) : c'est ce que
    #     lit le port, donc c'est lui qui doit attester du regime -- pas le kit gameconfig.
    sc = ctx.scene
    vis_by_id = getattr(sc, "vis_by_id", None) or {}
    regimes = {}
    for vis, uid in tgt.items():
        tr = entity_trait_ids(sc.ctx(uid) if hasattr(sc, "ctx") else None, vis_by_id.get(uid))
        regimes[vis] = MECHANICAL in tr
    if not (regimes.get(TGT_MECH) and not regimes.get(TGT_SOFT)):
        raise MontageError(f"montage NON INSTALLE : les deux regimes de cible ne sont pas reunis "
                           f"-- Mechanical par cible = {regimes}")

    weight = float(ctx.wt.triggered(WEIGHT_KEY))
    if weight == 0:
        raise MontageError(f"montage NON INSTALLE : le BC servi porte {WEIGHT_KEY} = 0 "
                           f"(refresh_ai_utilities inoperant ?) -- rien ne discriminerait")

    # Tuiles ACCEPTEES par l'oracle = tuile courante + movable set = exactement `ctx.action_tiles`,
    # restreintes au CONTACT des deux cibles. Le contact est le seul critere de portee qui vaille
    # sans lire l'arme : `decisionView` ne publie PAS la portee (cf. ses cles), et hors portee le
    # natif ne rend que le terme triggered la ou le port produit AUSSI sa composante de degat --
    # deux mesures qui ne parlent pas de la meme chose (ecart constate : ~11.36).
    tiles = [t for t in (ctx.action_tiles or [])
             if t and t[0] is not None and all(hexgeo.distance(t, p) <= 1 for p in (mpos, spos))]
    if not tiles:
        raise MontageError("montage NON INSTALLE : aucune tuile au contact des DEUX cibles -- la "
                           "mesure ne comparerait pas la meme chose")
    return {"rid": rid, "cid": cid, "tgt": tgt, "ab": ab, "ctx": ctx, "wt": ctx.wt,
            "weight": weight, "tiles": tiles[:3], "regimes": regimes}


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par (cible, tuile) : natif, port, port SANS le playbook 1541."""
    import engine.playbook.psyker as PSY
    out = []
    for vis, uid in case["tgt"].items():
        for tile in case["tiles"]:
            nat = pair_native(rpc, case["rid"], case["cid"], uid, case["ab"], tile)
            port = pair_port(case["ctx"], case["ab"], uid, tile)
            saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
            if saved is None:
                raise MontageError("le playbook 1541 n'est PAS au registre -- rien a muter")
            try:
                muted = pair_port(case["ctx"], case["ab"], uid, tile)
            finally:
                PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
            out.append({"target": vis, "mechanical": case["regimes"][vis], "tile": tile,
                        "native": nat, "port": port, "port_muted": muted})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du runner (rl_duel build --state-file)")
    args = ap.parse_args()

    import json
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()
    rid = int(json.load(open(args.state_file, encoding="utf-8"))["runnerId"])

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    case = build_case(sid, rpc, rid)
    print(f"runner {rid} | caster u{case['cid']} | cibles {case['tgt']} | "
          f"poids {WEIGHT_KEY} = {case['weight']}")
    for row in measure(rpc, case):
        d = row["port"] - row["native"]
        dm = row["native"] - row["port_muted"]
        print(f"  {row['target']:<16} mech={str(row['mechanical']):<5} @{row['tile']} "
              f"nat={row['native']:.6f} port={row['port']:.6f} d={d:+.6f} | "
              f"mute={row['port_muted']:.6f} manque={dm:+.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
