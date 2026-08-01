"""#441 -- MONTAGE NOMME des DEUX sorties de `Neuroparasite` (1183) sur la face ATTACK, et mesure
natif contre port.

`IdunBattle.AI.Playbook.Loki.NeuroparasitePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
n'a que DEUX sorties -- mais la seule qui vaut quelque chose exige un etat qui n'existe PAS au
deploiement :

  R1  la CIBLE porte l'effet `Neuroparasite` (0x4c2 = 1218)  -> `Fix64.op_Implicit(1)` = 1.0
  R2  elle ne le porte pas                                   -> `Fix64.op_Implicit(0)` = 0.0

Un montage nu tombe ENTIER dans R2 : au deploiement AUCUNE unite n'est parasitee, port et natif y
rendent tous deux 0, ils seraient parfaitement d'accord -- et le port pourrait etre faux sur R1 sans
que rien ne rougisse. **R1 se CONSTRUIT** : le Neurothrope doit d'abord TIRER (l'arme psychique,
range 3 -- `CurrentAttackDamageProfilesContain(0xd)` du trigger natif ; l'arme de melee est
`Physical` et ne pose RIEN), puis on lui rend son action (`endturn` x2, le meme re-armement que
`probe_124._drive_to`) et on mesure.

Les deux cibles doivent etre a **distance >= 4 l'une de l'autre** : MESURE -- avec deux cibles
adjacentes, le tir en a infecte DEUX (l'attaque psychique eclabousse le voisin), et le regime
temoin R2 disparaissait. C'est le meme piege de degenerescence que #438, sur un autre axe.

Le probe mesure DEUX FOIS chaque cible -- AVANT et APRES l'infection -- ce qui donne un
anti-confond temporel : la MEME cible doit passer de « manque 0 » a « manque exactement 1 ».

La valeur NE VIENT PAS d'un poids du BC : ce playbook n'a ni delegue scorer capture, ni `.cctor`, ni
cle `Utilities.Default.TriggeredAbilities`. `EXPECTED_INFECTED` est le LITTERAL du corps natif
(`FixMath.NET.Fix64$$op_Implicit` = `(long)(int)value << 0x20`), pose ici et NON relu du port --
sinon la mesure ne trancherait plus rien.

Usage :
    python scripts/python/probe_441_neuroparasite_pair_term.py --state-file <chemin ABSOLU>

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_441_neuroparasite_pair_term_live.py`.
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
CASTER = "tyranNeurothrope"     # HERO AU POOL ; `Neuroparasite` est dans son kit passif
TGT_INFECT = "astraBullgryn"    # recoit le tir -> porte l'effet 1218  -> R1
TGT_CLEAN = "astraCreed"        # temoin, jamais touche               -> R2
FOES = (TGT_INFECT, TGT_CLEAN)
ABILITY = int(TriggeredAbilityType.Neuroparasite)             # 1183 (l'ABILITY)
EFFECT = int(EffectType.Neuroparasite)                        # 1218 = 0x4c2 (l'EFFET)
# Litteral du corps natif : `Fix64.op_Implicit(1)`. PAS une cle de poids -- cf. l'en-tete.
EXPECTED_INFECTED = 1.0
EPS = 1e-4                      # Fix64 natif contre float du port
# PV releves sur les deux cibles : le tir d'amorcage ne doit TUER personne (un mort ne porte plus
# rien, et le temoin doit survivre au tour adverse) -- `Health` ET `RemainingHealth`, cf. #438.
HP = 40000
# Separation MINIMALE entre les deux cibles (mesure : a distance 1 le tir infecte les deux).
MIN_SEP = 4

BUILD_ARGS = ["--board", BOARD, "--p-units", CASTER, "--a-units", ",".join(FOES),
              "--unit-stat", ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in FOES)]


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


def native_effect_ids(dv, uid) -> set:
    """Les `effectType` que le canal `decisionView` attache a l'unite -- l'oracle du montage
    (`frida/hooks/game/effects.ts::readEffectsByUnit`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return {int(e["effectType"]) for e in ((u or {}).get("effects") or [])
            if isinstance(e, dict) and e.get("effectType") is not None}


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _stage(sid, rpc, rid: int) -> dict:
    """Place le caster et les deux cibles a portee de TIR (2 a 3 tuiles) et SEPAREES d'au moins
    `MIN_SEP` l'une de l'autre, puis rend le contexte de decision.

    Le drive est indispensable : hors portee d'arme, `pairUtility` ne rend que le terme triggered
    tandis que le port produit quand meme sa composante de degat. Et l'ADJACENCE des deux cibles
    ruinerait le montage (le tir eclabousse le voisin -> plus de temoin sain). On DEPLACE donc les
    unites plutot que d'accuser la geometrie de spawn (`probe_124._drive_to`)."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        tgt[vis] = u["id"]

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1183 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    # (b) Une tuile de tir avec deux voisins de rang 2-3 ECARTES l'un de l'autre.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    star = None
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring = [q for q in cells if 2 <= hexgeo.distance(p, q) <= 3]
        pair = next(((a, b) for i, a in enumerate(ring) for b in ring[i + 1:]
                     if hexgeo.distance(a, b) >= MIN_SEP), None)
        if pair:
            star = (p, pair)
            break
    if star is None:
        raise MontageError(f"montage NON INSTALLE : aucune tuile walkable avec deux voisins de "
                           f"rang 2-3 separes de {MIN_SEP} -- le tir infecterait les deux cibles")
    cpos, ring = star
    wanted = {cid: cpos, tgt[TGT_INFECT]: ring[0], tgt[TGT_CLEAN]: ring[1]}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    dv, ctx = _fresh_ctx(rpc, rid, cid)
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    if cpos not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
        raise MontageError(f"montage NON INSTALLE : la tuile de tir {cpos} n'est pas dans les "
                           f"tuiles d'action de l'oracle -- natif et port ne compareraient pas la "
                           f"meme chose")
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "tgt": tgt, "ab": ab, "ctx": ctx,
            "dv": dv, "tile": cpos, "walk": walk, "elev": elev, "wanted": wanted}


def _rows(rpc, st: dict, ctx, dv, phase: str) -> list[dict]:
    """Une ligne par cible : natif, port, port SANS le playbook 1183, et le regime ATTESTE des
    DEUX cotes (canal `decisionView` pour le natif, `battle_query.scene_has_effect` pour le port).

    Un desaccord entre les deux lectures du regime est un MONTAGE non atteste : la mesure
    d'utilite qui suivrait comparerait deux situations differentes -- on refuse."""
    import engine.playbook.psyker as PSY
    out = []
    for vis, uid in st["tgt"].items():
        nat_inf = EFFECT in native_effect_ids(dv, uid)
        port_inf = bq.scene_has_effect(ctx.scene, uid, EFFECT)
        if nat_inf != port_inf:
            raise MontageError(
                f"montage NON ATTESTE ({phase}) : sur {vis}, le canal natif dit "
                f"infecte={nat_inf} et le port dit {port_inf} -- le port est AVEUGLE a l'effet "
                f"{EFFECT}, un accord d'utilite ne prouverait rien")
        nat = pair_native(rpc, st["rid"], st["cid"], uid, st["ab"], st["tile"])
        port = pair_port(ctx, st["ab"], uid, st["tile"])
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(ctx, st["ab"], uid, st["tile"])
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"phase": phase, "target": vis, "uid": uid, "infected": nat_inf,
                    "expected": EXPECTED_INFECTED if nat_inf else 0.0,
                    "native": nat, "port": port, "port_muted": muted})
    return out


def _infect(sid, rpc, st: dict) -> None:
    """Amorce R1 : le caster TIRE sur `TGT_INFECT` (arme psychique), puis on lui rend son action.

    Le tir est le SEUL chemin qui pose l'effet : `NeuroparasiteAbility$$CreateTrigger` exige
    `CurrentAttackDamageProfilesContain(0xd)` (= `Psychic`), et l'arme de melee du Neurothrope est
    `Physical`. `endturn` x2 re-arme l'action (meme re-armement que `probe_124._drive_to`), puis on
    RE-VERIFIE le placement : le tour adverse a pu deplacer les cibles."""
    uid = st["tgt"][TGT_INFECT]
    r = rpc("applyAction", {"runnerId": st["rid"], "action": {
        "kind": "ability", "casterId": st["cid"], "targetId": uid,
        "abilityType": st["ab"]}}, 90)
    act = ((r or {}).get("actions") or [{}])[0]
    if not act.get("mutated"):
        raise MontageError(f"montage NON INSTALLE : le tir d'amorcage sur {TGT_INFECT} n'a rien "
                           f"mute -- {str(r)[:400]}")
    rpc("applyAction", {"runnerId": st["rid"], "action": {"kind": "endturn"}}, 60)
    rpc("applyAction", {"runnerId": st["rid"], "action": {"kind": "endturn"}}, 60)
    P124._give_turn_back(sid, st["rid"], st["myplayer"])
    if not P124._drive_to(sid, st["rid"], st["walk"], st["elev"], st["wanted"]):
        _dv, pos = P124._positions(sid, st["rid"])
        raise MontageError(f"montage NON INSTALLE : apres le tour adverse le placement n'est plus "
                           f"celui voulu {st['wanted']} -- obtenu "
                           f"{ {u: pos.get(u) for u in st['wanted']} }")
    P124._give_turn_back(sid, st["rid"], st["myplayer"])


def build_case(sid, rpc, rid: int) -> dict:
    """Monte les DEUX regimes et ATTESTE qu'ils sont bien installes, dans l'ordre temporel :
    phase `before` (les deux cibles SAINES), amorcage, phase `after` (une infectee, une saine)."""
    st = _stage(sid, rpc, rid)

    rows_before = _rows(rpc, st, st["ctx"], st["dv"], "before")
    if any(r["infected"] for r in rows_before):
        raise MontageError(
            f"montage NON INSTALLE : une cible porte DEJA l'effet {EFFECT} avant l'amorcage "
            f"-- l'anti-confond temporel serait perdu : "
            f"{[(r['target'], r['infected']) for r in rows_before]}")

    _infect(sid, rpc, st)
    dv, ctx = _fresh_ctx(rpc, st["rid"], st["cid"])
    st["ctx"], st["dv"] = ctx, dv
    for vis, uid in st["tgt"].items():
        u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
        if not (u or {}).get("alive"):
            raise MontageError(f"montage NON INSTALLE : {vis} est MORTE apres l'amorcage -- "
                               f"une morte ne porte plus rien")
    got = {vis: EFFECT in native_effect_ids(dv, uid) for vis, uid in st["tgt"].items()}
    if got != {TGT_INFECT: True, TGT_CLEAN: False}:
        raise MontageError(
            f"montage DEGENERE : apres l'amorcage l'infection devait etre "
            f"{{{TGT_INFECT}: True, {TGT_CLEAN}: False}} et vaut {got} -- sans les DEUX regimes, "
            f"port et natif seraient d'accord pour rien")
    st["rows_before"] = rows_before
    return st


def measure(rpc, case: dict) -> list[dict]:
    """Les lignes des DEUX phases. `before` est FIGE (son etat n'existe plus) ; `after` est
    re-jouable a volonte -- l'etat du runner ne bouge plus."""
    return list(case["rows_before"]) + _rows(rpc, case, case["ctx"], case["dv"], "after")


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
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, BUILD_ARGS)
    case = build_case(sid, rpc, rid)
    print(f"runner {rid} | caster u{case['cid']} @ {case['tile']} | ability normale "
          f"{case['ab']} | valeur attendue quand infecte = {EXPECTED_INFECTED}")
    for row in measure(rpc, case):
        d = row["port"] - row["native"]
        dm = row["native"] - row["port_muted"]
        print(f"  [{row['phase']:<6}] {row['target']:<16} u{row['uid']} "
              f"infecte={str(row['infected']):<5} nat={row['native']:.6f} "
              f"port={row['port']:.6f} d={d:+.9f} | mute={row['port_muted']:.6f} "
              f"manque={dm:+.9f} attendu={row['expected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
