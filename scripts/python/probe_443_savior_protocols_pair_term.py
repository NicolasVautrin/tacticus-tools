"""#443 -- MONTAGE NOMME du poids `SAVIORPROTOCOLS_MarkedTarget` (face ATTACK de `SaviorProtocols`,
1120) et mesure natif contre port.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext`
a UN SEUL `yield`, donc DEUX regimes :

  R1  la CIBLE porte un `Markerlight` (1122) ACTIF   -> `SAVIORPROTOCOLS_MarkedTarget` (60)
  R2  la CIBLE n'en porte pas                        -> 0

Un montage qui n'obtiendrait que R2 serait DEGENERE (natif et port d'accord sur 0, le port pouvant
etre faux sur R1 sans que rien ne rougisse) : le probe ECHOUE -- il ne skippe pas (#268) -- si les
deux regimes ne sont pas reunis SUR LE MEME ETAT.

## Le porteur est NATUREL, pas greffe

`SaviorProtocols` n'a AUCUN porteur `lineup` : 3 npc (`tauNpc{2,3,4}Drone*`) et 3 SUMMONS
(`tauSmnDroneSniper`, `tauSmnDroneShield`, `tauSmnDroneCommandLink`). C'est la voie SUMMON de la gate
de confrontabilite qui l'amene en bataille, et **une seule action monte les DEUX moities du
montage** : l'attaque normale RANGED de `tauMarksman` (ability 1076 `MV71SniperDroneSquadAttack`,
constantes `{unitId: tauSmnDroneSniper, maxSummons: 3}`)

  * invoque `tauSmnDroneSniper` sur une tuile libre ADJACENTE AU CASTER -- le drone nait avec
    `TriggeredAbility_Id 1120` (ground truth #61bis, re-atteste ici par `unitAbilityStates`) ;
  * pose `Markerlight` sur LA CIBLE VISEE, et sur elle seule
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour`
    etape (e)) -- d'ou la seconde cible, TEMOIN, qui ne recoit rien.

⚠ **L'attaque doit etre RANGED.** `MV71SniperDroneSquadAttackAbility$$PredictAttack` bascule sur
`IsMeleeAttack` : au CONTACT elle delegue a `ALoki_NormalAttackAbility` -- ni drone, ni Markerlight
(MESURE : cible adjacente -> `Attack_Weapon_IsMelee: 1`, `spawned: 0`, aucun effet 1122 pose). Les
cibles sont donc placees a distance 3 du Marksman, jamais au contact.

Le poids NE VIENT PAS d'ici : la cle est lue dans `Utilities.Default.TriggeredAbilities` du BC
SERVI, et le probe refuse de conclure si elle est nulle (piege #271). C'est cette mesure qui TRANCHE
l'assignation du litteral a cette face : les trois cles de la classe valent 60 / 20 / 30, donc un
terme mesure a 60 designe `MarkedTarget` sans ambiguite.

Usage :
    python scripts/python/probe_443_savior_protocols_pair_term.py --state-file <chemin ABSOLU>

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_443_savior_protocols_pair_term_live.py`.
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
from engine.entities.effect_type import EffectType               # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
SUMMONER = "tauMarksman"        # HERO au pool ; son attaque normale RANGED est 1076
TGT_MARKED = "astraBullgryn"    # la cible VISEE par 1076 -> recoit le `Markerlight`
TGT_PLAIN = "astraCreed"        # TEMOIN, jamais visee -> aucun `Markerlight`
FOES = (TGT_MARKED, TGT_PLAIN)
DRONE = "tauSmnDroneSniper"     # SUMMON, porteur NATIF de 1120 (arme Piercing portee 4)
SUMMON_ATTACK = 1076            # `MV71SniperDroneSquadAttack`
ABILITY = int(TriggeredAbilityType.SaviorProtocols)          # 1120
MARKERLIGHT = int(EffectType.Markerlight)                    # 1122
KEY_MARKED = "SAVIORPROTOCOLS_MarkedTarget"
EPS = 1e-4                      # Fix64 natif contre float du port
HP_TARGET = "40000"             # les cibles doivent SURVIVRE au tir qui monte le montage
# PV de la cible TEMOIN dans le regime d'INVERSION D'ARGMAX : assez bas pour que son utilite de
# degat de BASE depasse celle de la marquee, assez haut pour rester SOUS le poids 1120 -- la
# fenetre MESUREE a `MC1_67`/41504 est [18.06 ; 78.06[, et 4000 PV y place le temoin a 69.57.
FLIP_HP = 4000

BUILD_ARGS = ["--board", BOARD, "--p-units", SUMMONER, "--a-units", ",".join(FOES),
              "--hp-target", HP_TARGET]


def build_args(board: str = BOARD, flip_hp: int | None = None) -> list[str]:
    """Les args de build pour un board donne -- le montage n'est PAS board-specifique (il exige
    seulement une tuile centrale avec >= 2 tuiles a distance 3), et c'est ce que la generalisation
    sur un second couple (board, seed) verifie.

    `flip_hp` monte le regime d'INVERSION D'ARGMAX : la cible TEMOIN (non marquee) recoit peu de PV,
    donc une utilite de degat de BASE plus haute que celle de la marquee. Le choix de cible bascule
    alors sur le seul terme 1120 -- c'est le scenario ou le comportement porte CHANGE un resultat
    OBSERVABLE, pas seulement un scalaire. Les DEUX champs sont obligatoires (`RemainingHealth` est
    le PV COURANT, celui que lit la prediction ; `Health` seul NE MORD PAS -- mesure #438)."""
    args = ["--board", board, "--p-units", SUMMONER, "--a-units", ",".join(FOES),
            "--hp-target", HP_TARGET]
    if flip_hp:
        args += ["--unit-stat",
                 f"{TGT_PLAIN}:Health={int(flip_hp)},RemainingHealth={int(flip_hp)}"]
    return args


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


# --------------------------------------------------------------------------- montage

def _live_triggered(rpc, rid: int, uid: int) -> list[int]:
    """L'`AbilitiesComponent` REEL de l'unite -- la collection que le dispatcher natif itere."""
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": uid}, 60) or {}
    return sorted({i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                   for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)})


def _markerlight_native(dv: dict, uid: int) -> bool:
    """Ce que le NATIF publie : un effet 1122 ACTIF sur l'unite (`decisionView.units[].effects`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return any(int(e.get("effectType") or -1) == MARKERLIGHT and e.get("active")
               for e in ((u or {}).get("effects") or []))


def _stage(sid, rpc, rid: int) -> dict:
    """Place le Marksman au centre et les deux cibles a DISTANCE 3 (regime RANGED obligatoire),
    tire 1076 sur `TGT_MARKED`, puis rend le contexte de decision du DRONE invoque.

    Le drive est indispensable : au spawn les cibles sont hors de portee, et une cible ADJACENTE
    ferait basculer 1076 sur le chemin melee -- ni drone ni Markerlight. On DEPLACE donc les unites
    plutot que d'accuser la geometrie de spawn (montage NOMME reutilise :
    `probe_124_line_elevation_decision._drive_to`)."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    mk = next((u for u in mine if u.get("visualId") == SUMMONER), None)
    if mk is None:
        raise MontageError(f"montage NON INSTALLE : {SUMMONER} absent du roster")
    myplayer = mk.get("owner")
    tgt = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        tgt[vis] = u["id"]

    # (a) Une tuile centrale + deux tuiles de l'anneau 3 : le tir sera RANGED des deux cotes.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    mpos = min(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    ring3 = [p for p in cells if hexgeo.distance(mpos, p) == 3
             and abs((elev.get(p) or 0) - (elev.get(mpos) or 0)) < 2]
    if len(ring3) < len(FOES):
        raise MontageError(f"montage NON INSTALLE : {mpos} n'a que {len(ring3)} tuiles a distance 3 "
                           f"-- il en faut {len(FOES)} pour un tir RANGED sur chaque cible")
    wanted = {mk["id"]: mpos}
    for vis, pos in zip(FOES, ring3):
        wanted[tgt[vis]] = pos
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    # (b) Le tir qui monte les DEUX moities : invoque le drone ET marque la cible visee.
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": mk["id"], "targetId": tgt[TGT_MARKED],
        "abilityType": SUMMON_ATTACK}}, 120) or {}
    act = (r.get("actions") or [{}])[0]
    if not act.get("ok"):
        raise MontageError(f"montage NON INSTALLE : le tir {SUMMON_ATTACK} a echoue -- {act}")
    melee = [e.get("tags") for e in (act.get("events") or [])
             if '"Attack_Weapon_IsMelee":1' in str(e.get("tags"))]
    if melee:
        raise MontageError("montage NON INSTALLE : le tir est parti en MELEE "
                           f"({melee}) -- ni drone ni Markerlight sur ce chemin")

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    drone = next((u for u in (dv.get("units") or [])
                  if u.get("visualId") == DRONE and u.get("alive")), None)
    if drone is None:
        raise MontageError(f"montage NON INSTALLE : aucun {DRONE} invoque par le tir "
                           f"-- units={[u.get('visualId') for u in (dv.get('units') or [])]}")
    live = _live_triggered(rpc, rid, drone["id"])
    if ABILITY not in live:
        raise MontageError(f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent "
                           f"du {DRONE} -- triggered live lus = {live}")

    # (c) Les DEUX regimes, attestes cote NATIF : marquee / non marquee.
    marks = {vis: _markerlight_native(dv, uid) for vis, uid in tgt.items()}
    if marks != {TGT_MARKED: True, TGT_PLAIN: False}:
        raise MontageError(f"montage DEGENERE : les deux regimes ne sont pas reunis -- {marks}")

    # (d) Rendre la main au joueur du drone : `pairUtility` evalue la paire du POINT DE VUE du
    #     caster, et le contexte de decision se construit sur son tour.
    P124._give_turn_back(sid, rid, myplayer)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    if not _markerlight_native(dv, tgt[TGT_MARKED]):
        raise MontageError("montage PERDU : le `Markerlight` a expire avant la mesure")
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, drone["id"], W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError(f"montage NON INSTALLE : aucune attaque normale sur le {DRONE}")

    # (e) La tuile de mesure : celle du drone, et il faut que les DEUX cibles y soient A PORTEE --
    #     hors portee, le natif ne rend que le terme triggered tandis que le port produit quand
    #     meme sa composante de degat, et les deux cotes ne parlent plus de la meme chose.
    dpos = (drone["pos"]["col"], drone["pos"]["row"])
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": drone["id"], "abilityType": ab}, 60) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == drone["id"]), None)
    here = {t.get("targetId") for a in ((row or {}).get("abilities") or [])
            for t in (a.get("fromHere") or [])}
    missing = [vis for vis, uid in tgt.items() if uid not in here]
    if missing:
        raise MontageError(f"montage NON INSTALLE : {missing} hors de portee du {DRONE} depuis "
                           f"{dpos} -- fromHere={sorted(here)}")

    w = float(ctx.wt.triggered(KEY_MARKED))
    if w == 0:
        raise MontageError(f"montage NON INSTALLE : le BC servi porte {KEY_MARKED}={w} "
                           f"-- un poids nul ne discrimine rien")
    return {"rid": rid, "drone": drone["id"], "summoner": mk["id"], "tgt": tgt, "ab": ab,
            "ctx": ctx, "tile": dpos, "marks": marks, "w": w}


def expected_term(case: dict, vis: str) -> float:
    """Ce que la face ATTACK DOIT verser sur cette cible, selon les deux sorties natives."""
    return case["w"] if case["marks"][vis] else 0.0


def leaf_terms(case: dict) -> dict:
    """La face ATTACK ISOLEE (foyer `engine.utilities.tile.triggered_abilities_attack_utility`),
    pour chaque (attaquant, cible) -- la mesure qui prouve que le terme est attache au PORTEUR.

    Le SUMMONER est l'anti-cas : il attaque LA MEME cible marquee depuis LA MEME tuile, et ne porte
    PAS 1120 (son passif est `MV71SniperDroneSquad` 1119, sans face ATTACK). Un port qui aurait mis
    la condition dans le composite -- ou qui la lirait sur la cible sans consulter le kit de
    l'attaquant -- verserait le poids ici aussi."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    out = {}
    for who, uid in (("drone", case["drone"]), ("summoner", case["summoner"])):
        for vis, tid in case["tgt"].items():
            out[(who, vis)] = float(triggered_abilities_attack_utility(
                case["ctx"], uid, case["ab"], tid, case["tile"]))
    return out


def argmax_of(rows: list[dict], field: str) -> str:
    """La cible que ce classement retient -- l'argmax d'utilite de paire, c.-a-d. le CHOIX DE CIBLE
    (meme foyer que le trou mesure par #415 : « c'est ce trou qui faisait diverger le choix de
    CIBLE de l'attaque normale »)."""
    return max(rows, key=lambda r: r[field])["target"]


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par cible : natif, port, et port SANS le playbook 1120 au registre."""
    import engine.playbook.psyker as PSY
    out = []
    for vis, uid in case["tgt"].items():
        nat = pair_native(rpc, case["rid"], case["drone"], uid, case["ab"], case["tile"])
        port = pair_port(case["ctx"], case["ab"], uid, case["tile"])
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(case["ctx"], case["ab"], uid, case["tile"])
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"target": vis, "marked": case["marks"][vis], "tile": case["tile"],
                    "expected": expected_term(case, vis),
                    "native": nat, "port": port, "port_muted": muted})
    return out


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str], seed: str = SEED) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    ap.add_argument("--board", default=BOARD, help="board de mesure (generalisation)")
    ap.add_argument("--seed", default=SEED, help="seed de build (generalisation)")
    ap.add_argument("--flip-hp", type=int, default=None,
                    help=f"PV de {TGT_PLAIN} -- regime d'INVERSION D'ARGMAX (cf. build_args)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, build_args(args.board, args.flip_hp), args.seed)
    try:
        case = _stage(sid, rpc, rid)
        print(f"runner {rid} | board {args.board} seed {args.seed} flip_hp={args.flip_hp} | "
              f"{DRONE} u{case['drone']} @{case['tile']} (invoque par {SUMMONER} "
              f"u{case['summoner']}) | poids {KEY_MARKED}={case['w']}")
        rows = measure(rpc, case)
        for row in rows:
            d = row["port"] - row["native"]
            dm = row["native"] - row["port_muted"]
            print(f"  {row['target']:<16} marked={str(row['marked']):<5} @{row['tile']} "
                  f"nat={row['native']:.6f} port={row['port']:.6f} d={d:+.6f} | "
                  f"mute={row['port_muted']:.6f} manque={dm:+.6f} attendu={row['expected']}")
        print("  face ATTACK ISOLEE (foyer triggered_abilities_attack_utility) :")
        for (who, vis), v in sorted(leaf_terms(case).items()):
            print(f"    {who:<10} -> {vis:<16} {v:.6f}")
        print("  CHOIX DE CIBLE (argmax d'utilite de paire) : natif=%s port=%s port_mute=%s%s" % (
            argmax_of(rows, "native"), argmax_of(rows, "port"), argmax_of(rows, "port_muted"),
            "   <-- INVERSION : le terme 1120 change le resultat OBSERVABLE"
            if argmax_of(rows, "port") != argmax_of(rows, "port_muted") else ""))
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
