"""probe #27-4c -- A/B causal LIVE de ForwardObservers (1185), 2e membre de la route non-attaque.

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CalculateCustomUtility` porte DEUX termes de
nature DIFFERENTE, et ce probe les separe :

    custom = [aucun ennemi ne porte Markerlight] * W("ForwardObservers_EnemyHasNoMarkerlight" = 200)
           + RemainingPercentage(CIBLE) * W("ForwardObservers_TargetHealthPercentage" = 40)

* le premier est BOOLEEN et GLOBAL (`...ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` :
  `foreach (e in battleQuery.<slot itf 0x8e = GetAllEnemiesOf>(player)) if HasEffect(e, 0x462) break`) ;
* le second est LINEAIRE dans le RATIO de PV de la cible
  (`IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage` = `max(0, cur/max)`).

1185 n'a PAS de `damageProfile` (`constants` = range/dmgPctReduction/nrOfRounds/nrOfRounds_2) : elle
n'atteint jamais `_best_attack` et passe par `engine/playbook/nonattack.py`. Le bras `route OFF`
(registre `NONATTACK_PLAYBOOKS` vide) rejoue la decision dans l'etat d'AVANT le port -- c'est le
controle qui distingue « le port marche » de « l'accord vient d'ailleurs ».

MONTAGE (board MC1_67), et pourquoi il est fabrique comme ca
------------------------------------------------------------
PORTEUR. Les deux seules unites qui portent 1185 sont `tauSmnStealthSuit` (SUMMON, declare par
`units.abilities.ATemptingTrap.constants.unitId`) et `tauNpc5StealthSuit` (npc). **Aucune unite du
gameconfig ne porte `ATemptingTrap`** : le summon n'a pas d'invocateur, on ne peut pas l'amener par
son summoner. Et `catalog_inject` ne suffit PAS : `buildNormalizedBC` les REFUSE tous les deux
(`v2 patch: system error` -- `IStatsFormula.StatsUsingProgressionIndexFor` n'a pas de table de
progression pour un summon/npc), donc ils restent hors du pool spawnable, stats a 0.

=> Le porteur est GREFFE : on remplace `ActiveAbilities` de `tauCrisis` (T'au, pool, arme ranged
portee 2) par `[1185]` dans une copie du seed BC. C'est licite et non speculatif parce que le
playbook natif est charge PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par
unite : le code exerce est bien `ForwardObserversPlaybook`, et le natif le PROUVE en proposant
`ActiveAbilityMessage(1185)` dans `aiDryRunAllUnits`. La formule custom ne lit aucune variable
d'ability (seulement `BC.Utilities`), donc la greffe ne la deforme pas.

MARKERLIGHT. Il est pose par une voie NATURELLE, pas injecte : `tauDarkstrider` porte le passif
`StructuralAnalyser`, dont
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateTrigger`
= `On(0xa) & IsRangedAttack & OwnerIsCaster` et dont le `CreateBehaviour` fait
`AddEffect(0x462 Markerlight, ...)` sur la cible. Il tire donc sur un ennemi TENU A L'ECART du
caster : la cible marquee sort d'office des cibles de 1185 (
`...ForwardObserversAbility$$GetDynamicInvalidTargetReason` refuse une cible qui porte deja
Markerlight), et ses PV modifies n'entrent dans aucune paire evaluee.

BRAS
----
  B0  : mk=0, les deux cibles a PV PLEINS       -> natif 1185, cible = 1re de l'enumeration
  B1  : mk=0, une cible BLESSEE                 -> natif 1185, cible = la plus SAINE (contre l'ordre
                                                   d'enumeration : exclut booleen ET constante)
  A1  : mk=1 (un ennemi porte Markerlight)      -> le terme 200 s'eteint

Usage (depuis scripts/python, ASCII only) :
    python probe_27_4c_forwardobservers_ab.py --build [--engine] [--hp-target=N]
    python probe_27_4c_forwardobservers_ab.py --engine        # re-joue sur le runner du state-file
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_fo_graft.json"
STATE = LOGS / "rs_fo_ab.json"
BOARD = "MC1_67"
SEED = 909
FORWARD_OBSERVERS = 1185
NORMAL = 69
MARKERLIGHT = 1122                     # EffectType.Markerlight = 0x462

GRAFT_ON = "tauCrisis"                 # porteur GREFFE (cf. l'en-tete)
P_UNITS = "tauCrisis,tauDarkstrider,ultraCalgar"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = "tauCrisis"               # porte 1185 apres greffe
MARKER_VID = "tauDarkstrider"          # StructuralAnalyser -> pose Markerlight en tirant
HURTER_VID = "ultraCalgar"             # blesse une cible (fait varier RemainingPercentage)
TGT_A_VID = "orksWarboss"              # cible 1 de 1185
TGT_B_VID = "necroWarden"              # cible 2 de 1185
FAR_VID = "astraCreed"                 # victime du Markerlight, TENUE A L'ECART du caster

CASTER_TILE = "2,6"
TGT_A_TILE = "2,4"                     # d=2 du caster (<= range 3, et dans la portee d'arme 2)
TGT_A_FAR_TILE = "0,2"                 # bras A2 : hors range 3 -> la cible SAINE sort du jeu
TGT_B_TILE = "2,8"                     # d=2 du caster
FAR_TILE = "6,0"                       # d=8 du caster -> jamais cible de 1185
MARKER_TILE = "5,2"                    # d=2 de FAR_TILE -> tir RANGED (arme Pulse portee 2)
HURTER_TILE = "3,8"                    # adjacent a TGT_B, non adjacent au caster

HP_TARGET_DEFAULT = 0                  # 0 = stats naturelles


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _cast(rid: int, caster: int, ability: int, target: int) -> None:
    _run(["act", "ability", "--caster", str(caster), "--ability", str(ability),
          "--target", str(target), "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row), hp, [effectType...])} -- les ids ne sont PAS hardcodes."""
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        effs = [e.get("effectType") for e in (u.get("effects") or []) if isinstance(e, dict)]
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), u.get("hp"), effs)
    return out


def _markerlight_holders(rid: int) -> list:
    """Mirror LIVE de `...ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` : QUI, parmi les
    ennemis du caster (`ctrl == False`, le predicat de `BattleQuery$$GetAllEnemiesOf`), porte 0x462.
    Nomme l'unite -- une lecture d'un SEUL id se lit comme « pas de markerlight » alors que le
    predicat est GLOBAL (piege rencontre le 2026-07-30)."""
    out = []
    for u in (_dv(rid).get("units") or []):
        if u.get("ctrl"):
            continue
        for e in (u.get("effects") or []):
            if isinstance(e, dict) and e.get("effectType") == MARKERLIGHT:
                out.append((u.get("id"), u.get("visualId"), e.get("remaining")))
    return out


def _hpmax(rid: int) -> dict:
    obs = L._rpc("observeBattle", [{"runnerId": rid}])
    return {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1185]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [FORWARD_OBSERVERS]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d] -> %s" % (GRAFT_ON, FORWARD_OBSERVERS, SEED_BC))


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : les bras degenerent en UN seul etat, ou l'accord
    moteur<->natif est trivialement vrai (piege mesure le 2026-07-30 sur #27-4)."""
    pos = {i: p for _v, (i, p, _h, _e) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build(hp_target: int) -> int:
    write_graft_seed_bc()
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)] + extra)
    rid = _runner_id()
    ids = {v: i for v, (i, _p, _h, _e) in _units(rid).items()}
    want = ((ids[TGT_A_VID], TGT_A_TILE), (ids[TGT_B_VID], TGT_B_TILE),
            (ids[FAR_VID], FAR_TILE), (ids[CASTER_VID], CASTER_TILE),
            (ids[MARKER_VID], MARKER_TILE), (ids[HURTER_VID], HURTER_TILE))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def _native(rid: int, caster: int, enemies: list) -> tuple[dict, tuple, list]:
    pairs = {}
    for tgt in enemies:
        r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                    "targetId": tgt, "abilityType": NORMAL}])
        pairs[tgt] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen, msgs


def _engine(rid: int, caster: int) -> dict:
    """Trois decisions MOTEUR sur le MEME etat : telle quelle / custom force a 0 / route desactivee."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX
    from engine.playbook.base import tile_utility

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    pb = PB.REGISTRY.get(FORWARD_OBSERVERS)
    targets = pb.eligible_targets(ctx, FORWARD_OBSERVERS)
    mk = pb.any_enemy_has_markerlight(ctx)
    per_target = {t: (pb.remaining_health_percentage(ctx, t),
                      pb.calculate_custom_utility(ctx, ctx.origin, t, FORWARD_OBSERVERS))
                  for t in targets}
    tile = tile_utility(ctx, ctx.origin)

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "markerlight": mk, "targets": targets, "per_target": per_target, "tile": tile}


def measure(rid: int, label: str, engine: bool) -> dict:
    u = _units(rid)
    hpmax = _hpmax(rid)
    caster = u[CASTER_VID][0]
    enemies = [u[v][0] for v in (TGT_A_VID, TGT_B_VID, FAR_VID)]
    pairs, chosen, msgs = _native(rid, caster, enemies)
    pct = {}
    for v in (TGT_A_VID, TGT_B_VID, FAR_VID):
        i, _p, hp, _e = u[v]
        mx = hpmax.get(i) or 0
        pct[i] = (float(hp) / float(mx)) if mx else 0.0
    print("  --- %s ---" % label)
    print("      positions : caster=%s A=%s B=%s far=%s"
          % (u[CASTER_VID][1], u[TGT_A_VID][1], u[TGT_B_VID][1], u[FAR_VID][1]))
    print("      PV%% cibles : A(u%d)=%.4f  B(u%d)=%.4f  far(u%d)=%.4f"
          % (u[TGT_A_VID][0], pct[u[TGT_A_VID][0]], u[TGT_B_VID][0], pct[u[TGT_B_VID][0]],
             u[FAR_VID][0], pct[u[FAR_VID][0]]))
    holders = _markerlight_holders(rid)
    print("      porteurs ENNEMIS de Markerlight (predicat GLOBAL du natif) = %s" % (holders,))
    print("      pairUtility(69) natives : %s"
          % {v: pairs[u[v][0]] for v in (TGT_A_VID, TGT_B_VID, FAR_VID)})
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pairs": pairs, "native": chosen, "caster": caster, "pct": pct,
           "ids": {v: u[v][0] for v in (TGT_A_VID, TGT_B_VID, FAR_VID)},
           "mk_native": bool(holders), "holders": holders}
    if engine:
        e = _engine(rid, caster)
        print("      moteur : on=%s | markerlight=%s tile=%.6f" % (e["on"], e["markerlight"], e["tile"]))
        print("      moteur : cibles=%s  (pct, custom) par cible = %s" % (e["targets"], e["per_target"]))
        print("      moteur : custom force a 0 -> %s | route DESACTIVEE -> %s | to=%s"
              % (e["zero"], e["noroute"], e["to"]))
        row["engine"] = e
    return row


def run_ab(rid: int, engine: bool) -> dict:
    ids = {v: i for v, (i, _p, _h, _e) in _units(rid).items()}
    rows = {}
    rows["B0"] = measure(rid, "B0 : mk=0, les deux cibles a PV pleins", engine)
    _cast(rid, ids[HURTER_VID], NORMAL, ids[TGT_B_VID])
    rows["B1"] = measure(rid, "B1 : mk=0, cible B BLESSEE (le natif doit preferer la plus SAINE)",
                         engine)
    _cast(rid, ids[MARKER_VID], NORMAL, ids[FAR_VID])
    rows["A1"] = measure(rid, "A1 : mk=1 (StructuralAnalyser a pose Markerlight sur l'ennemi ecarte)",
                         engine)
    # A2 -- BRAS DISCRIMINANT DE PROPORTIONNALITE. On eloigne la cible SAINE : il ne reste que la
    # cible BLESSEE (pct < 1). A markerlight pose, `u_action(1185) = W_B * pct`. Deux modeles
    # concurrents predisent des choix OPPOSES sur le meme etat des que
    # `W_B * pct < pair_max + 1 < W_B` : le modele PROPORTIONNEL fait rester le natif sur l'attaque
    # normale, un terme CONSTANT (= W_B des que la cible a des PV) le ferait basculer sur 1185.
    _move(rid, ids[TGT_A_VID], TGT_A_FAR_TILE)
    rows["A2"] = measure(rid, "A2 : mk=1, SEULE la cible BLESSEE reste a portee (proportionnalite)",
                         engine)
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    hp = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--hp-target=")),
                  str(HP_TARGET_DEFAULT)))
    rid = build(hp) if "--build" in argv else _runner_id()
    print("runner=%d board=%s seed=%d hp-target=%s" % (rid, BOARD, SEED, hp or "naturel"))
    rows = run_ab(rid, engine)

    print("\n=== SYNTHESE ===")
    ok = True
    for k in ("B0", "B1", "A1", "A2"):
        nat_ab, nat_tgt = rows[k]["native"]
        line = "  %-3s : natif -> ability=%s target=%s (markerlight pose=%s)" % (
            k, nat_ab, nat_tgt, rows[k]["mk_native"])
        if engine:
            e = rows[k]["engine"]
            agree = (e["on"] == (nat_ab, nat_tgt))
            ok = ok and agree
            line += " | moteur -> %s %s" % (e["on"], "MATCH" if agree else "DIVERGE")
        print(line)
    a_id, b_id = rows["B0"]["ids"][TGT_A_VID], rows["B0"]["ids"][TGT_B_VID]
    print("  B0 -> B1 : la cible natif passe de %s a %s (A=u%d sain, B=u%d blesse) : %s"
          % (rows["B0"]["native"][1], rows["B1"]["native"][1], a_id, b_id,
             "TERME PROPORTIONNEL AUX PV DE LA CIBLE"
             if rows["B1"]["native"][1] == a_id and rows["B0"]["native"][1] == b_id
             else "non discriminant sur ce montage"))
    print("  A1 : le natif abandonne 1185 quand un ennemi porte Markerlight : %s"
          % ("OUI" if rows["A1"]["native"][0] != FORWARD_OBSERVERS else "NON"))
    if engine:
        nec = any(rows[k]["engine"]["zero"] != rows[k]["engine"]["on"] for k in rows)
        deb = any(rows[k]["engine"]["noroute"] != rows[k]["engine"]["on"] for k in rows)
        print("  terme NECESSAIRE (custom=0 fait diverger le moteur)          : %s"
              % ("OUI" if nec else "NON"))
        print("  route NECESSAIRE (sans elle le moteur ne peut pas dire 1185) : %s"
              % ("OUI" if deb else "NON"))
        # ENCADREMENT sans fitting. u_action(69) = pair_max + Tile + 1 (custom NormalAttack = +1) ;
        # u_action(1185, c) = A + W_B*pct(c) + Tile a la MEME tuile -> Tile s'annule.
        for k in ("B0", "B1", "A1", "A2"):
            e, r = rows[k]["engine"], rows[k]
            p = max(v for v in r["pairs"].values() if v is not None)
            tgts = e["targets"] or []
            best = max((r["pct"].get(t, 0.0) for t in tgts), default=0.0)
            side = "1185" if r["native"][0] == FORWARD_OBSERVERS else "69"
            # u_action(69) = pair_max + Tile + 1 ; u_action(1185) = A + W_B*pct + Tile (meme tuile).
            # Le natif tranche => une INEGALITE par bras, sans aucun scalaire ajuste.
            floor = p + 1.0
            if r["mk_native"]:
                ineq = ("W_B > %.4f" % (floor / best)) if side == "1185" and best \
                    else ("W_B < %.4f" % (floor / best) if best else "n/a")
            else:
                ineq = ("W_A + W_B*%.4f > %.4f" % (best, floor)) if side == "1185" \
                    else ("W_A + W_B*%.4f < %.4f" % (best, floor))
            print("    %-3s pair_max=%.6f  pct(meilleure cible)=%.4f  natif=%-4s  =>  %s"
                  % (k, p, best, side, ineq))
        # A2 : le meme etat separe les deux modeles du terme de PV.
        r2 = rows["A2"]
        p2 = max(v for v in r2["pairs"].values() if v is not None) + 1.0
        t2 = r2["engine"]["targets"] or []
        pct2 = max((r2["pct"].get(t, 0.0) for t in t2), default=0.0)
        if r2["mk_native"] and t2 and 0.0 < pct2 < 1.0:
            from engine import weights as _W
            wb = _W.load().sub("ActiveAbilities", "ForwardObservers_TargetHealthPercentage")
            print("  A2 DISCRIMINANT : pct=%.4f, pair_max+1=%.4f, W_B(BC)=%s ; proportionnel => %s, "
                  "constant(=W_B) => %s ; natif = %s"
                  % (pct2, p2, wb,
                     "1185" if wb * pct2 > p2 else "69",
                     "1185" if wb > p2 else "69",
                     "1185" if r2["native"][0] == FORWARD_OBSERVERS else "69"))
    print("(pense a disposer le runner : rl_duel.py dispose --state-file %s)" % STATE)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
