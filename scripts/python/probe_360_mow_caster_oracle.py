#!/usr/bin/env python
"""Probe #360 -- confronter une ability de MACHINE OF WAR avec son PORTEUR REEL.

CE QUE CE PROBE TRANCHE (etape A, le DISCRIMINANT)
-------------------------------------------------
`#350-r3` a laisse DEUX verrous nommes, et la tache #360 demandait lequel est le VRAI :

  (a) cote CAPTEUR : `aiPlaybookPredict` rend `count = -1 / listNull = true` des qu'un summon est
      en jeu, avec une MoW pour caster ;
  (b) cote PORT : `engine.ai.context.build` rend `ctx.me is None` pour une entite `Machine`.

Les deux se mesurent SANS reinject, avec des RPC DEJA deployes, et c'est ce que fait l'etape A :

  * `aiPlaybookPredict(caster = MoW)` SUBSTITUE la `UnitPosition` de la CIBLE au caster off-board
    (`rpc-predict.ts`, commentaire RE #172). Ce n'est PAS ce que fait le natif : le tactic reel,
    `IdunBattle.AI.Tactics.DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`,
    appelle `GenerateActions(machine, UnitPosition$$NullPosition(), new OrderedSet(), 0)` --
    `UnitPosition$$NullPosition` = `new List<ITile>()`, donc une position VIDE, jamais celle d'une
    autre entite. Et `UnitPosition$$get_MainTile` sur une liste vide rend `null` SANS lever (le
    corps teste `Count` avant d'indexer), donc la position vide est un argument LEGAL.
  * `ncPlaybookPredict` (`rpc-nc-predict.ts`), lui, prend `unitPositionCurrent(caster)` -- pour une
    MoW off-board, `EntityExtensions$$GetUnitPosition` = `GetTiles` = une liste VIDE, c'est-a-dire
    EXACTEMENT la `NullPosition` du natif. Sa voie `via = "makeDamagePredictions"` invoque le MEME
    `makeDamagePredictions(playbook, caster, pos, target, level, mult)` que `aiPlaybookPredict`, et
    rend en plus le MESSAGE de l'exception si le natif leve.

  => les deux RPC ne different, sur ce montage, QUE par la `UnitPosition` passee. Si le second rend
  des events la ou le premier rend `null`, le verrou (a) est la SUBSTITUTION, pas le caster Machine.

  * cote (b) : `engine.ai.context.build_machine` EXISTE DEJA (mirror de `DefaultMachineTactic` :
    `origin = None`, `action_tiles = []`, `plans = {}`, `me` lu dans `decisionView.mows`). La mesure
    « `ctx.me is None` » de #350-r3 vient de `probe_344._ctx`, qui appelle `build` -- la fonction
    des UNITES. L'etape A appelle les DEUX et publie les deux reponses.

ETAPE B -- la CONFRONTATION avec le porteur reel
------------------------------------------------
Une fois l'oracle ouvert, on rejoue le gabarit #344 (deux bras de parite, quatre variantes
d'arrondi) sur `1147 HadesAutocannons` avec `blackForgefiend` POUR CASTER, et on compare au tableau
obtenu par GREFFE (`docs/rl/case-350r3-porteur-mow-et-formule-triggered.md`) :

    bras A (niveau 4, minDmg+maxDmg = 135 = 3 mod 4) : natif greffe = (324, 492, 6)
    bras B (niveau 2, minDmg+maxDmg = 101 = 1 mod 4) : natif greffe = (240, 360, 6)

Les bornes AVAL (profil d'arme, percage) sont celles du CASTER : elles n'ont aucune raison de
coincider entre un `necroWarden` greffe et la MoW. Ce qui doit coincider, c'est le VERDICT
d'arrondi -- quelle variante egale le natif sur les DEUX bras.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_360_mow_caster_oracle.py --step a      # discriminant (a) vs (b)
    python probe_360_mow_caster_oracle.py --step b      # confrontation 1147, caster MoW reel
    python probe_360_mow_caster_oracle.py               # a + b
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                            # noqa: E402
import probe_344_ability_damage_average as P344                                # noqa: E402
import probe_350r3_mow_caster as P350                                          # noqa: E402

LOGS = PYDIR.parents[1] / "logs"

MOW = P350.MOW                       # blackForgefiend -- porteur natif de 1147 et 1148
BOARD = P350.BOARD
RANK = P350.RANK
SUMMONER = P350.SUMMONER             # deathBlightbringer (pool) -- 1040 SpawnPoxwalkers self-cast
SPAWN_POXWALKERS = P350.SPAWN_POXWALKERS
P_FILLER = P350.P_FILLER
A_UNIT = P350.GRAFT_ON               # necroWarden, cote de la MoW (equipe adverse)
A_FILLER = P350.A_FILLER
CENTER = P350.CENTER
ABILITY = 1147
ABILITY_NAME = "HadesAutocannons"
LVL_A, LVL_B = P350.A1147_LVL_A, P350.A1147_LVL_B     # 4 (3 mod 4) puis 2 (1 mod 4)


def _r(sid, rid, m, b=None, t=120):
    body = {"runnerId": rid}
    body.update(b or {})
    return (_rpc(sid, m, [body], timeout=t).get("result") or {})


def _mow_montage(sid, sf: Path, seed: int, level: int) -> tuple[int, int, int, dict]:
    """Monte le runner MoW + summons et rend `(rid, casterId de la MoW, id d'un summon, dv)`.

    GEOMETRIE DRIVEE : le summoner au centre (ses summons naissent sur son ring), les autres
    autour. La MoW est off-board (elle n'a pas de tuile) -- rien a deplacer pour elle."""
    rid = P350._build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                 "--a-units", "%s,%s" % (A_UNIT, A_FILLER),
                                 "--a-mow", MOW,
                                 "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                                "AbilityVariablesMultiplierPercentage=100"
                                                % (MOW, level)])
    ids, dv = P350._ids(sid, rid)
    mow_row = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
    if mow_row is None:
        raise RuntimeError("MoW %s non deployee (mows=%s)"
                           % (MOW, [m.get("visualId") for m in (dv.get("mows") or [])]))
    P350._move(sid, rid, ids[SUMMONER], *CENTER)
    P350._move(sid, rid, ids[P_FILLER], CENTER[0] - 1, CENTER[1] - 1)
    P350._move(sid, rid, ids[A_UNIT], CENTER[0] + 1, CENTER[1])
    P350._move(sid, rid, ids[A_FILLER], CENTER[0] + 1, CENTER[1] - 1)
    _r(sid, rid, "applyAction",
       {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                   "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
    ids2, dv2 = P350._ids(sid, rid)
    smn = sorted(uid for vis, uid in ids2.items() if str(vis).startswith("deathPox"))
    if not smn:
        raise RuntimeError("aucun summon apres 1040 SpawnPoxwalkers")
    return rid, int(mow_row["casterId"]), int(smn[0]), dv2


# `AiDecisionContext` d'un caster MACHINE -- `build_machine`, le mirror de `DefaultMachineTactic`
# (et non `build`, qui est celui des UNITES). Foyer UNIQUE : `probe_350r3_mow_caster.ctx_machine`.
_ctx_machine = P350.ctx_machine


# ------------------------------------------------------- etape A : (a) capteur ou (b) port ?

def step_a(seed: int = 36010, verbose: bool = True) -> dict:
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    sf = LOGS / "p360_stepA.json"
    rid = None
    out: dict = {}
    try:
        rid, cid, tid, _dv = _mow_montage(sid, sf, seed, LVL_A)
        out["casterId"], out["targetId"] = cid, tid
        # --- (a1) la voie ACTUELLE : `aiPlaybookPredict`, qui SUBSTITUE la position de la cible.
        a1 = _r(sid, rid, "aiPlaybookPredict",
                {"unitId": cid, "targetId": tid, "abilityType": ABILITY}, 180)
        out["aiPlaybookPredict"] = {
            "ok": a1.get("ok"), "count": a1.get("count"), "listNull": a1.get("listNull"),
            "posSrc": a1.get("posSrc"), "playbookClass": a1.get("playbookClass"),
            "makeArity": a1.get("makeArity"), "error": a1.get("error"),
            "events": a1.get("events"), "abilityState": a1.get("abilityState")}
        # --- (a2) la MEME invocation avec la position du CASTER (= NullPosition pour une MoW).
        a2 = _r(sid, rid, "ncPlaybookPredict",
                {"unitId": cid, "targetId": tid, "abilityType": ABILITY,
                 "via": "makeDamagePredictions"}, 180)
        out["ncPlaybookPredict"] = {
            "ok": a2.get("ok"), "returnedCount": a2.get("returnedCount"),
            "capturedCount": a2.get("capturedCount"), "listNull": a2.get("listNull"),
            "posSrc": a2.get("posSrc"), "playbookClass": a2.get("playbookClass"),
            "error": a2.get("error"), "returnedError": a2.get("returnedError"),
            "returned": a2.get("returned"), "captured": a2.get("captured"),
            "abilityState": a2.get("abilityState")}
        # --- (a3) le SCOREUR complet (4 familles) -- publie le message d'exception s'il leve.
        a3 = _r(sid, rid, "pairUtility",
                {"unitId": cid, "targetId": tid, "abilityType": ABILITY}, 180)
        out["pairUtility"] = {"ok": a3.get("ok"), "utility": a3.get("utility"),
                              "posSrc": a3.get("posSrc"), "error": a3.get("error")}
        # --- (b) cote PORT : `build` (unites) contre `build_machine` (machines).
        try:
            ctx_u, _ = P344._ctx(sid, rid, cid)
            out["port_build_me"] = None if ctx_u.me is None else ctx_u.me.get("visualId")
        except Exception as e:                                    # noqa: BLE001 -- on RAPPORTE
            out["port_build_me"] = "exception: %s: %s" % (type(e).__name__, e)
        try:
            ctx_m, _ = _ctx_machine(sid, rid, cid)
            out["port_build_machine_me"] = (None if ctx_m.me is None
                                            else ctx_m.me.get("visualId"))
            out["port_build_machine_abilities"] = [a.get("id")
                                                   for a in (ctx_m.me or {}).get("abilities", [])]
            out["port_scene_ctx"] = (ctx_m.scene is not None
                                     and ctx_m.scene.ctx(cid) is not None)
            out["port_origin"] = ctx_m.origin
        except Exception as e:                                    # noqa: BLE001
            out["port_build_machine_me"] = "exception: %s: %s" % (type(e).__name__, e)
            out["port_scene_ctx"] = None
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    nc = out.get("ncPlaybookPredict") or {}
    ai = out.get("aiPlaybookPredict") or {}
    # VERDICT. ⚠ CE DRAPEAU EST ECRIT POUR VALOIR `True` AVANT LE CORRECTIF : il constate que
    # `aiPlaybookPredict` TOMBE (`listNull` / `count < 0`) tandis que la voie « position du
    # caster » repond. Une fois le correctif de `rpc-predict.ts` DEPLOYE, il vaut donc `False`
    # -- et ce `False` est le SUCCES, pas un echec. D'ou le second drapeau ci-dessous, qui dit
    # l'etat POST-correctif ; les deux ensemble couvrent les deux regimes sans ambiguite.
    out["oracle_ouvert_par_position_caster"] = bool(
        (nc.get("returnedCount") or 0) >= 0 and not nc.get("error")
        and (ai.get("listNull") is True or (ai.get("count") or 0) < 0))
    out["oracle_direct_repare"] = bool(
        ai.get("ok") and ai.get("listNull") is False and (ai.get("count") or 0) >= 0
        and (nc.get("returnedCount") or 0) == (ai.get("count") or -1))
    out["port_ouvert_par_build_machine"] = bool(
        out.get("port_build_machine_me") == MOW and out.get("port_build_me") is None)
    out["ok"] = bool(out["oracle_ouvert_par_position_caster"]
                     or out["oracle_direct_repare"]
                     or out["port_ouvert_par_build_machine"])
    if verbose:
        print("\n[360/A] DISCRIMINANT -- caster MoW %s (id=%s), cible summon id=%s"
              % (MOW, out.get("casterId"), out.get("targetId")))
        # `posSrc` est RENDU par le RPC : on l'imprime au lieu de le decrire. Un libelle fige
        # ("pos = CIBLE substituee") survivrait au correctif et decrirait un etat revolu.
        print("  (a1) aiPlaybookPredict  [posSrc=%s] : ok=%s count=%s listNull=%s err=%s"
              % (ai.get("posSrc"), ai.get("ok"), ai.get("count"), ai.get("listNull"),
                 ai.get("error")))
        print("  (a2) ncPlaybookPredict  [posSrc=%s] : ok=%s returned=%s "
              "captured=%s err=%s"
              % (nc.get("posSrc"), nc.get("ok"), nc.get("returnedCount"),
                 nc.get("capturedCount"), nc.get("error")))
        print("       events rendus : %s" % json.dumps(nc.get("returned"), default=str)[:400])
        pu = out.get("pairUtility") or {}
        print("  (a3) pairUtility        [posSrc=%s] : ok=%s utility=%s err=%s"
              % (pu.get("posSrc"), pu.get("ok"), pu.get("utility"), pu.get("error")))
        print("  (b)  port build()        -> ctx.me = %s" % out.get("port_build_me"))
        print("       port build_machine() -> ctx.me = %s | abilities=%s | scene.ctx=%s | origin=%s"
              % (out.get("port_build_machine_me"), out.get("port_build_machine_abilities"),
                 out.get("port_scene_ctx"), out.get("port_origin")))
        print("  -> [PRE-correctif] oracle ouvert par la position du caster : %s"
              % out["oracle_ouvert_par_position_caster"])
        print("  -> [POST-correctif] aiPlaybookPredict repare, et D'ACCORD avec nc : %s"
              % out["oracle_direct_repare"])
        print("  -> port ouvert par build_machine                           : %s"
              % out["port_ouvert_par_build_machine"])
    return out


# --------------------------------- etape B : 1147 confrontee AVEC SON PORTEUR MoW (gabarit #344)

# Ce que la voie GREFFE (`case-350r3`, 1147 posee sur `necroWarden`) avait mesure -- on le compare
# terme a terme au porteur REEL. Ces valeurs sont un POINT DE COMPARAISON, jamais une attente
# imposee : un ecart serait un resultat, pas un echec du montage.
GRAFT_NATIVE = {"a": (324, 492, 6), "b": (240, 360, 6)}


def _native_mow(sid, rid, cid, tid, ability):
    """Oracle NATIF pour un caster MACHINE : `ncPlaybookPredict(via = "makeDamagePredictions")`.

    C'est le MEME `<X>Playbook$$MakeDamagePredictions` qu'invoque `aiPlaybookPredict` ; seule la
    `UnitPosition` differe -- celle du CASTER (vide pour une MoW off-board, donc la `NullPosition`
    du tactic natif) au lieu de celle de la CIBLE. Meme regle de selection que `probe_344._native` :
    la SEQUENCE des events de la cible principale, plus le compte total."""
    r = _r(sid, rid, "ncPlaybookPredict",
           {"unitId": int(cid), "targetId": int(tid), "abilityType": int(ability),
            "via": "makeDamagePredictions"}, 240)
    if r.get("error"):
        return None, 0, r.get("error")
    evs = (r or {}).get("returned") or []
    mains = [e for e in evs if e.get("targetId") == int(tid)] or (evs[:1] if evs else [])
    if not mains:
        return None, len(evs), None
    return (tuple((e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                  for e in mains), len(evs), None)


def _arm_b(sid, sf: Path, seed: int, level: int, label: str) -> dict:
    rid = None
    try:
        rid, cid, tid, _dv = _mow_montage(sid, sf, seed, level)
        ctx, _dv2 = _ctx_machine(sid, rid, cid)
        scene = ctx.scene
        mm = P344._minmax_config(scene, cid, ABILITY, ABILITY_NAME)
        if mm is None:
            return {"label": label, "error": "config d'ability introuvable pour la MoW"}
        mn, mx, lvl_eff, mult_eff = mm
        # `origin` d'une MoW = None (mirror `NullPosition` : elle n'a pas de PositionComponent).
        here = ctx.origin
        nat, n_nat, nat_err = _native_mow(sid, rid, cid, tid, ABILITY)
        if nat_err:
            return {"label": label, "error": "oracle natif : %s" % nat_err}
        ports = {name: P344._offline(scene, cid, tid, ABILITY, ABILITY_NAME, here, fn)[0]
                 for name, fn in P344.VARIANTS}
        shipped, n_port = P344._offline(scene, cid, tid, ABILITY, ABILITY_NAME, here, None)
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    s = int(mn) + int(mx)
    return {"label": label, "level_asked": level, "level_eff": lvl_eff, "mult_eff": mult_eff,
            "minDmg": int(mn), "maxDmg": int(mx), "sum": s, "sum_mod4": s % 4, "floor": s // 2,
            "casterId": cid, "targetId": tid, "here": here,
            "native": nat, "ports": ports, "shipped": shipped,
            "n_events_native": n_nat, "n_events_port": n_port}


def step_b(seed: int = 36030, verbose: bool = True) -> dict:
    """Gabarit #344 (deux bras de parite, quatre variantes) avec `blackForgefiend` POUR CASTER."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    sf = LOGS / "p360_stepB.json"
    arms = {}
    for key, label, lvl, sd in (("a", "A (3 mod 4 -- le natif MONTE)", LVL_A, seed),
                                ("b", "B (1 mod 4 -- le natif DESCEND)", LVL_B, seed + 1)):
        arm = _arm_b(sid, sf, sd, lvl, label)
        if not arm.get("error"):
            P344._grade(arm)
            arm["graft_native"] = GRAFT_NATIVE[key]
            arm["agrees_with_graft"] = (arm.get("native") == (GRAFT_NATIVE[key],))
        arms[key] = arm
    regimes_ok = (arms["a"].get("sum_mod4") == 3 and arms["b"].get("sum_mod4") == 1)
    nul_on_both = [n for n, _fn in P344.VARIANTS
                   if all((arms[k].get("match") or {}).get(n) for k in ("a", "b"))]
    import engine.entities.abilities.active_ability as AA
    expected = "to_even" if ABILITY in AA._PREDICTION_MINMAX_AVERAGE else "trunc"
    ok = bool(regimes_ok and all(arms[k].get("ok") for k in ("a", "b"))
              and nul_on_both == [expected])
    if verbose:
        print("\n[360/B] %s (%d) CONFRONTEE AVEC SON PORTEUR REEL %s"
              % (ABILITY_NAME, ABILITY, MOW))
        print("  oracle natif : ncPlaybookPredict(via=makeDamagePredictions), position = CASTER")
        print("  variante attendue par le registre : %s" % expected)
        for key in ("a", "b"):
            arm = arms[key]
            if arm.get("error"):
                print("\n  === bras %s === ERREUR : %s" % (key, arm["error"]))
                continue
            print("\n  === bras %s === %s" % (key, arm["label"]))
            print("    niveau demande=%d effectif=%d | minDmg=%d maxDmg=%d somme=%d (mod4=%d) floor=%d"
                  % (arm["level_asked"], arm["level_eff"], arm["minDmg"], arm["maxDmg"],
                     arm["sum"], arm["sum_mod4"], arm["floor"]))
            print("    natif MoW  = %-24s (events natif=%d port=%d)"
                  % (str(arm["native"]), arm["n_events_native"], arm["n_events_port"]))
            print("    natif GREFFE (case-350r3) = %s -> meme mesure : %s"
                  % (str(arm["graft_native"]), arm["agrees_with_graft"]))
            print("    LIVRE      = %-24s %s"
                  % (str(arm["shipped"]), "== NATIF" if arm["shipped_ok"] else "!= NATIF"))
            for name, _fn in P344.VARIANTS:
                print("      %-9s port=%-24s %s"
                      % (name, str(arm["ports"][name]), "== NATIF" if arm["match"][name] else "!="))
            print("    bras discriminant : %s" % arm["discriminates"])
        print("\n  regimes pilotes comme annonces : %s" % regimes_ok)
        print("  variantes nulles sur les DEUX bras : %s" % (nul_on_both or "aucune"))
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "arms": arms, "regimes_ok": regimes_ok,
            "nul_on_both_arms": nul_on_both, "expected_variant": expected}


# --------------------------- etape C : 1148 DaemonicOrdnance, MEME porteur MoW, DEUX regimes de feu

ORDNANCE = 1148
ORDNANCE_NAME = "DaemonicOrdnance"
ORDNANCE_LVL = 2
# Nom de l'effet de TUILE que lit le gate de selecteur de 1148 (`EffectType.Fire`, 5) -- re-derive
# de l'enum du moteur, jamais ecrit en dur.
_EFFECT_FIRE = __import__("engine.entities.effect_type", fromlist=["EffectType"]).EffectType.Fire.name


def step_c(seed: int = 36070, verbose: bool = True) -> dict:
    """`1148` avec `blackForgefiend` POUR CASTER -- l'ability dont le porteur natif EST cette MoW.

    `DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur
    `DaemonicOrdnanceAbility$$GetAllDamageableTargets` = les ennemis debout sur une tuile qui PORTE
    DEJA `Fire` (5) -- que ce meme cast pose en dernier etage de son behaviour. Deux regimes sur le
    MEME runner : zone froide (avant tout cast) et zone en feu (apres). C'est le gate
    `_MAKE_DMG_TARGET_GATE` qui est en jeu, cette fois avec le VRAI caster."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    sf = LOGS / "p360_stepC.json"
    rid = None
    out: dict = {}
    try:
        rid = P350._build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                     "--a-units", "%s,%s" % (A_UNIT, A_FILLER),
                                     "--a-mow", MOW,
                                     "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                                    "AbilityVariablesMultiplierPercentage=100"
                                                    % (MOW, ORDNANCE_LVL)])
        ids, dv = P350._ids(sid, rid)
        mow_row = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
        if mow_row is None:
            raise RuntimeError("MoW %s non deployee" % MOW)
        cid = int(mow_row["casterId"])
        out["casterId"] = cid
        out["mow_abilities"] = [(a.get("id"), a.get("level"))
                                for a in (mow_row.get("abilities") or [])]
        # GEOMETRIE DRIVEE : la cible (une unite du camp OPPOSE a la MoW) au centre.
        tgt_pos = CENTER
        P350._move(sid, rid, ids[SUMMONER], *tgt_pos)
        P350._move(sid, rid, ids[P_FILLER], tgt_pos[0] - 1, tgt_pos[1] - 1)
        tid = ids[SUMMONER]

        def _both(tag):
            from engine.playbook.prediction import abilities as PA
            nat, n_nat, err = _native_mow_ability(sid, rid, cid, tid, ORDNANCE)
            ctxm, _d = _ctx_machine(sid, rid, cid)
            port, n_port = P344._offline(ctxm.scene, cid, tid, ORDNANCE, ORDNANCE_NAME,
                                         ctxm.origin, None)
            sc = ctxm.scene
            fx = (sc.tile_effects_by_pos or {}).get(tuple(tgt_pos)) or []
            # DECOMPOSITION PAR ETAGE : un desaccord doit designer SON etage, pas rester un
            # « le port rend 0 ». Le gate de selecteur de 1148 lit trois choses -- les equipes des
            # deux entites et la tuile de la cible : on les publie toutes.
            return {"tag": tag, "native": nat, "n_native": n_nat, "native_error": err,
                    "port": port, "n_port": n_port, "tile_effects_on_target": fx,
                    "scene_team_caster": sc.team(cid), "scene_team_target": sc.team(tid),
                    "scene_pos_target": sc.pos(tid), "scene_ctx_caster": sc.ctx(cid) is not None,
                    "gate": PA._MAKE_DMG_TARGET_GATE[ORDNANCE](sc, cid, tid)}

        out["cold"] = _both("zone FROIDE (aucune tuile en feu)")
        cast = _r(sid, rid, "applyAction",
                  {"action": {"kind": "ability", "casterId": cid,
                              "to": {"col": tgt_pos[0], "row": tgt_pos[1]},
                              "abilityType": ORDNANCE}}, 180)
        out["cast_ok"] = bool((cast.get("actions") or [{}])[0].get("ok"))
        out["cast_error"] = (cast.get("actions") or [{}])[0].get("error")
        out["hot"] = _both("zone EN FEU (apres un premier cast de la MoW)")
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    cold, hot = out["cold"], out["hot"]
    # Les DEUX regimes sont verrouilles, et c'est ce qui a change avec #360. Avant, seul le regime
    # FROID etait exigible : le port y rendait ZERO pour la MAUVAISE raison (`scene.team(<MoW>)`
    # valait None, donc le gate se degradait en NEGATIF), et le regime CHAUD passait inapercu --
    # natif `(3, 3, 3)`, port RIEN. Un accord obtenu par une donnee manquante n'est pas un accord.
    out["ok"] = bool(cold["n_native"] == 0 and cold["n_port"] == 0 and not cold["native_error"]
                     and cold["scene_team_caster"] is not None
                     and out.get("cast_ok")
                     and _EFFECT_FIRE in (hot["tile_effects_on_target"] or [])
                     and hot["n_native"] > 0 and hot["port"] == hot["native"])
    if verbose:
        print("\n[360/C] %s (%d) -- caster = la MoW REELLE %s" % (ORDNANCE_NAME, ORDNANCE, MOW))
        print("  abilities portees par la MoW : %s" % out.get("mow_abilities"))
        for k in ("cold", "hot"):
            r = out.get(k) or {}
            print("  %-46s natif=%s (%s ev, err=%s) | port=%s (%s ev) | effets de tuile=%s"
                  % (r.get("tag"), r.get("native"), r.get("n_native"), r.get("native_error"),
                     r.get("port"), r.get("n_port"), r.get("tile_effects_on_target")))
            print("      etages du gate : team(caster)=%s team(cible)=%s pos(cible)=%s "
                  "ctx(caster)=%s -> gate=%s"
                  % (r.get("scene_team_caster"), r.get("scene_team_target"),
                     r.get("scene_pos_target"), r.get("scene_ctx_caster"), r.get("gate")))
        print("  cast intermediaire par la MoW : ok=%s err=%s"
              % (out.get("cast_ok"), out.get("cast_error")))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


def _native_mow_ability(sid, rid, cid, tid, ability):
    """`_native_mow` avec le message d'erreur RENDU (utilise par l'etape C, ou le zero est
    justement le verdict attendu : un zero DOIT etre distingue d'une levee)."""
    return _native_mow(sid, rid, cid, tid, ability)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=("a", "b", "c"), default=None)
    ap.add_argument("--seed", type=int, default=36010)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    steps = [a.step] if a.step else ["a", "b", "c"]
    out = {}
    if "a" in steps:
        out["stepA"] = step_a(seed=a.seed)
    if "b" in steps:
        out["stepB"] = step_b(seed=a.seed + 20)
    if "c" in steps:
        out["stepC"] = step_c(seed=a.seed + 60)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if all(v.get("ok") for v in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
