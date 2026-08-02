"""#449 -- LE DISCRIMINANT du << canal predefini >> : le slot de montant applique-t-il le
spread +/-20 % ?

CONTRADICTION TRANCHEE. Deux ports lisaient le MEME slot de facon INCOMPATIBLE :

  * `engine/playbook/psyker.py` et `engine/playbook/avalanche_of_muscle.py` posaient
    `spread_pct=0` sur le slot 0x23 (`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`
    a montant), au motif d'un canal << PREDEFINI, sans spread >> ;
  * la tranche `LightImUp` mesurait au contraire des bornes natives dans un rapport 1,5 sur le
    slot 0x28 (`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction`).

Les deux slots CONVERGENT (RE, cf. la case-doc) :

    BattleQuery$$GetMultiHitAttackPrediction   -- boucle `hits` fois -->
    BattleQuery$$GetAttackPrediction (a montant, surcharge a `UnitPosition` deja construite)
      -- `IDamagePredictionQuery` slot 10, litteral `hits = 1` -->
    DamagePredictionQuery$$GetAttackPrediction (surcharge `initialDamage`/`hits`)
      -- ecrit `request+0x6a = 1` (LITTERAL) -->
    DamagePrediction$$PredictAttackRaw
      `if (request+0x6a == 0)`                    -> MinMaxDamageFix64(damage, damage)  [PLAT]
      `else if (this.<0x10>.<0x31> != 0)`         -> MEME branche PLATE
      `else`  -> `DamagePrediction$$GetBaseDamageFix64` = {slot8(d), slot9(d)} = +/-20 %

`this.<0x10>` est le champ `configuration` de `DamagePrediction$$.ctor` : un fait de la BATAILLE,
identique pour les trois playbooks. AUCUN des trois n'a donc de regime propre : `spread_pct=0` et
le spread par defaut ne peuvent pas etre vrais ensemble.

CE QUE CE PROBE MESURE, et pourquoi c'est DIRECT. L'accord qui << validait >> `spread_pct=0`
portait sur une UTILITE FINALE. Or le composite Damage consomme
`MinMaxDamage$$Avg(AccurateHealthDamage)` : la MOYENNE des deux bornes. Hors cap PV et hors bascule
de kill, `avg(0.8d, 1.2d) == d` -- le canal ne SAIT PAS exprimer la difference, et un accord y est
DEGENERE, pas probant. Ce probe lit donc les BORNES elles-memes, capturees sur le
`IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` que le playbook natif appelle
(`ncPlaybookPredict`, champ `captured`), pour les DEUX porteurs du verdict conteste :

  A_CHARGE  `astraBullgryn` charge `astraCreed`  -> `AvalancheOfMusclePlaybook` (1028), slot 0x23
  P_SPLASH  `spaceStormcaller` tire a 2 hex      -> `PsykerPlaybook` (1013), slot 0x23

Trois hypotheses, separees par la MEME mesure :
  * canal PREDEFINI          -> `min == max`
  * `RandomAmount(min, max)` -> bornes dans le rapport `maxDmg / minDmg` de la config
  * spread +/-20 %           -> bornes dans le rapport `1.2 / 0.8 = 1.5`

Usage :
    python scripts/python/probe_449_spread_slot_predefini.py --state-file <chemin ABSOLU>

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_449_spread_slot_predefini_live.py`.
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
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
BULL = "astraBullgryn"          # HERO au pool ; `AvalancheOfMuscle` (1028) est son passif
NJAL = "spaceStormcaller"       # HERO au pool ; trait `Psyker` -> `PsykerExtraAttack` (1013)
TGT = "astraCreed"              # la cible du case, a 2 hex des DEUX casters
SPLASH = "admecDestroyer"       # ADJACENT a la cible -> pool de splash du Psyker
FOES = (TGT, SPLASH)

AB_AVALANCHE = int(TriggeredAbilityType.AvalancheOfMuscle)       # 1028
AB_PSYKER = int(TriggeredAbilityType.PsykerExtraAttack)          # 1013

EPS = 1e-4


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracle natif

def native_events(rpc, rid: int, cid: int, tgt: int, ability: int, tile, klass: str) -> list:
    """Les `ProbableDamageEvent` que le playbook NATIF construit, captures sur son ctor.

    `attackAbility: "normalAttack"` est OBLIGATOIRE sur les deux playbooks : leurs gates de tete
    (`IsRegularAttack` pour Psyker, `case.AbilityType` transmis a la requete pour les deux) lisent
    l'ability NOMMEE par le case. Un case anonyme fait evaluer FAUX a tous les predicats DSL
    `IsNormalAttack` des effets d'attaquant et repond a une AUTRE question (mesure #419-r1-tr5)."""
    body = {"runnerId": rid, "unitId": cid, "targetId": tgt, "abilityType": ability,
            "abilityKind": "triggered", "via": "attackUtilityInSteps", "hits": 1,
            "col": int(tile[0]), "row": int(tile[1]), "attackAbility": "normalAttack"}
    r = rpc("ncPlaybookPredict", body, 240) or {}
    if "abilityKind" not in r:
        raise MontageError(
            "NON CONFRONTE : le hook deploye ignore `abilityKind` (champ absent de la reponse de "
            "ncPlaybookPredict) -- fenetre de reinject requise. reponse=%r" % (str(r)[:300],))
    if r.get("playbookClass") != klass:
        raise MontageError("KEY-SPACE : l'oracle a charge %r au lieu de %s"
                           % (r.get("playbookClass"), klass))
    if r.get("error"):
        raise MontageError("ncPlaybookPredict a rendu une erreur : %s" % (r["error"],))
    ev = r.get("captured")
    if not isinstance(ev, list) or not ev:
        raise MontageError(
            "REGIME DEGENERE : le playbook natif n'a construit AUCUN `ProbableDamageEvent` "
            "(capturedCount=%r, gates=%r) -- rien a mesurer, ce n'est pas un verdict"
            % (r.get("capturedCount"), r.get("gates")))
    return ev


def bounds_of(ev: dict) -> tuple:
    """Les bornes BRUTES (non capees par les PV) du degat sante d'un event capture.

    Le decodeur les publie sous `willKillDmg` / `mightKillDmg` : ce sont
    `DamagePredictionResult@+0x24` / `@+0x28`, les DEUX bornes du degat sante NON capees,
    celles-la memes que lisent `get_WillBeKill` et `get_MightBeKill`. On lit les brutes et pas
    `healthDmg*` (capees a `CurrentHealth`) pour qu'un cap PV ne puisse pas ecraser l'ecart et
    faire passer un canal a spread pour un canal predefini."""
    lo, hi = ev.get("willKillDmg"), ev.get("mightKillDmg")
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        raise MontageError("event capture sans bornes brutes : %r" % (str(ev)[:250],))
    return float(lo), float(hi)


# --------------------------------------------------------------------------- oracle port

def _forced_spread(mod, pct):
    """Remplace le foyer `get_attack_prediction` VU PAR LE MODULE par un wrapper qui IMPOSE
    `spread_pct`. C'est ce qui permet de mesurer les DEUX lectures sur le MEME port, sans
    recompiler ni supposer laquelle est en place dans la source.

    `pct is None` = AUCUN forcage : on mesure ce que la SOURCE fait. C'est la colonne qui rend
    ce probe capable de rougir sur une regression -- les deux colonnes forcees, elles, sont
    indifferentes a la valeur ecrite dans le port."""
    real = mod.get_attack_prediction
    if pct is None:
        return real, real

    def wrapper(*a, **kw):
        kw["spread_pct"] = pct
        return real(*a, **kw)
    return real, wrapper


def port_bounds_avalanche(ctx, cid: int, ability_id: int, tgt: int, tile, spread_pct: int):
    """Les bornes que rend `AvalancheOfMusclePlaybook._predict_extra_vs_target` au `spread_pct`
    impose. On appelle le foyer du PORT, pas une reimplementation."""
    import engine.playbook.avalanche_of_muscle as AOM
    from engine.services.battle_query import select_weapon_pierce
    sc = ctx.scene
    pb = AOM.AvalancheOfMusclePlaybook()
    tpos = sc.pos(tgt)
    actx = sc.ctx(cid)
    if tpos is None or actx is None:
        raise MontageError("port : caster ou cible sans position")
    d = hexgeo.distance(tuple(tile), tuple(tpos))
    pierce, is_ranged, _h, prof = select_weapon_pierce(actx, d <= 1, d)
    if prof is None:
        raise MontageError("port : aucune arme selectionnee depuis %r" % (tile,))
    extra = pb._extra_damage(sc, cid)
    if not extra:
        raise MontageError("port : `extraDmg` nul -- le regime ne mesure rien")
    real, wrapper = _forced_spread(AOM, spread_pct)
    AOM.get_attack_prediction = wrapper
    try:
        pred = pb._predict_extra_vs_target(
            sc, cid, tgt, int(extra), tile, prof, is_ranged, pierce,
            ability_id is not None and int(ability_id) in (ctx.normal_ids or ()))
    finally:
        AOM.get_attack_prediction = real
    if pred is None:
        raise MontageError("port : prediction absente")
    return pred, int(extra)


def port_bounds_psyker(ctx, cid: int, tgt: int, tile, spread_pct: int):
    """Les bornes que rend `PsykerPlaybook._predict_amount_vs_target` au `spread_pct` impose."""
    import engine.playbook.psyker as PSY
    import gameconfig as GC
    from fractions import Fraction
    from engine.entities.formulas import _round_fix64
    sc = ctx.scene
    pb = PSY.PsykerPlaybook()
    pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
    amount = int(_round_fix64(Fraction(pct * int(sc.attack_current(cid)), 100), 0))
    if amount <= 0:
        raise MontageError("port : montant psyker nul -- le regime ne mesure rien")
    real, wrapper = _forced_spread(PSY, spread_pct)
    PSY.get_attack_prediction = wrapper
    try:
        pred = pb._predict_amount_vs_target(sc, cid, tgt, amount, tile)
    finally:
        PSY.get_attack_prediction = real
    if pred is None:
        raise MontageError("port : prediction absente")
    return pred, amount


def bounds_and_utility(ctx, pred, tgt: int) -> tuple:
    """`(min, max, utilite)` d'une prediction du port -- les bornes BRUTES et le terme que la
    feuille en tire (`CalculateUtilityFromDamageEvent` = composite Damage).

    Les DEUX sont rendus parce que c'est leur ECART qui nomme la panne : les bornes SEPARENT les
    hypotheses, l'utilite non (le composite consomme `MinMaxDamage$$Avg`, la MOYENNE)."""
    from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                       calculate_utility_from_damage_event)
    ev = ProbableDamageEvent(target=tgt, prediction=pred)
    u = calculate_utility_from_damage_event(ev, ctx.wt, (ctx.hpmax_by_id or {}).get(tgt))
    return (float(pred.raw_health_damage.min), float(pred.raw_health_damage.max), float(u))


# --------------------------------------------------------------------------- montage

def _pick_geometry(walk, elev):
    """`(t, s, p_bull, c_bull, p_njal)` sur un PALIER UNIQUE :

      `t`       tuile de la CIBLE du case ;
      `s`       un voisin de `t` -- la cible de splash du Psyker ;
      `p_bull`  a distance hex 2 de `t` -- le Bullgryn y demarre (il doit CHARGER) ;
      `c_bull`  voisin de `p_bull` ET adjacent a `t` -- la tuile de charge ;
      `p_njal`  a distance hex 2 de `t` -- Njal y tire (arme a distance, portee 2).

    Palier unique : le gate melee natif et `MovementUtil$$AreTilesAdjacent` portent une porte
    d'elevation `|delta| < 2` ; un montage a relief ne mesurerait plus le canal vise. Le regime
    ELEVATION reste donc NON COUVERT, et c'est dit."""
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))

    def ring(p, iso):
        return [q for q in hexgeo.neighbors(p[0], p[1])
                if walk.get(q) and elev.get(q) == iso]

    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        e0 = elev[t]
        r1 = ring(t, e0)
        if len(r1) < 3:
            continue
        far = [q for q in cells if elev.get(q) == e0 and hexgeo.distance(t, q) == 2]
        for s in r1:
            for p_bull in far:
                if p_bull == s:
                    continue
                cands = [c for c in ring(p_bull, e0)
                         if c != t and c != s and hexgeo.distance(c, t) == 1]
                if not cands:
                    continue
                for p_njal in far:
                    if p_njal in (s, p_bull) or p_njal in cands:
                        continue
                    return t, s, p_bull, sorted(cands)[0], p_njal
    raise MontageError(
        "montage NON INSTALLE : aucune configuration (cible + voisin + deux tuiles a distance 2, "
        "dont une avec tuile de charge, sur un palier unique) sur ce board")


def _attest_ability(rpc, rid: int, cid: int, ability: int, who: str) -> None:
    """Le passif est-il dans l'`AbilitiesComponent` ? Sans lui, le dispatcher ne l'itere pas et la
    mesure ne prouverait rien."""
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live = [i for u in (st.get("units") or []) for tr in (u.get("triggered") or [])
            for i in [((tr.get("raw") or [None])[0])] if isinstance(i, int)]
    if ability not in live:
        raise MontageError(
            "montage NON INSTALLE : %d n'est PAS dans l'AbilitiesComponent de %s -- triggered "
            "live lus = %r" % (ability, who, sorted(set(live))))


def stage(sid, rpc, rid: int) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for vis in (BULL, NJAL):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError("montage NON INSTALLE : %s absent du roster" % vis)
        ids[vis] = u["id"]
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError("montage NON INSTALLE : %s absent du roster adverse" % vis)
        ids[vis] = u["id"]

    _attest_ability(rpc, rid, ids[BULL], AB_AVALANCHE, BULL)
    _attest_ability(rpc, rid, ids[NJAL], AB_PSYKER, NJAL)

    t, s, p_bull, c_bull, p_njal = _pick_geometry(walk, elev)
    wanted = {ids[TGT]: t, ids[SPLASH]: s, ids[BULL]: p_bull, ids[NJAL]: p_njal}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError("montage NON INSTALLE : placement incomplet -- voulu %r, obtenu %r"
                           % (wanted, {u: pos.get(u) for u in wanted}))
    P124._give_turn_back(sid, rid, myplayer)

    _dv2, pos = P124._positions(sid, rid)
    for uid, dest in wanted.items():
        if pos.get(uid) != dest:
            raise MontageError("montage NON ATTESTE : l'unite %d est en %r et non %r"
                               % (uid, pos.get(uid), dest))
    if not bq.is_adjacent(s, t, elev):
        raise MontageError("montage NON ATTESTE : le splash %r n'est pas adjacent a la cible %r"
                           % (s, t))
    if bq.is_adjacent(p_bull, t, elev):
        raise MontageError("montage NON ATTESTE : le Bullgryn est DEJA au contact -- "
                           "`CameIntoContactWithEnemy` serait faux et l'etat 7 inatteignable")
    if not bq.is_adjacent(c_bull, t, elev):
        raise MontageError("montage NON ATTESTE : la tuile de charge %r n'est pas au contact de %r"
                           % (c_bull, t))

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _scene.build_predictor(rpc, rid)
    wt = W.load()
    ctx_bull = _ai_ctx.build(rpc, rid, dv, mbu, ids[BULL], wt, pred)
    ctx_njal = _ai_ctx.build(rpc, rid, dv, mbu, ids[NJAL], wt, pred)
    return {"rid": rid, "ids": ids, "t": t, "s": s, "p_bull": p_bull, "c_bull": c_bull,
            "p_njal": p_njal, "ctx_bull": ctx_bull, "ctx_njal": ctx_njal}


# --------------------------------------------------------------------------- mesure

def measure(rpc, case: dict) -> list:
    rows = []
    ids = case["ids"]

    ev = native_events(rpc, case["rid"], ids[BULL], ids[TGT], AB_AVALANCHE, case["c_bull"],
                       "AvalancheOfMusclePlaybook")
    n_lo, n_hi = bounds_of(ev[0])
    ab = next(iter(case["ctx_bull"].normal_ids or ()), None)
    pf, amt = port_bounds_avalanche(case["ctx_bull"], ids[BULL], ab, ids[TGT], case["c_bull"], 0)
    ps, _ = port_bounds_avalanche(case["ctx_bull"], ids[BULL], ab, ids[TGT], case["c_bull"], 20)
    pc, _ = port_bounds_avalanche(case["ctx_bull"], ids[BULL], ab, ids[TGT], case["c_bull"], None)
    f_lo, f_hi, f_u = bounds_and_utility(case["ctx_bull"], pf, ids[TGT])
    s_lo, s_hi, s_u = bounds_and_utility(case["ctx_bull"], ps, ids[TGT])
    c_lo, c_hi, _cu = bounds_and_utility(case["ctx_bull"], pc, ids[TGT])
    rows.append({"regime": "A_CHARGE", "playbook": "AvalancheOfMuscle(1028)", "amount": amt,
                 "events": len(ev), "native": [n_lo, n_hi], "target": ev[0].get("targetId"),
                 "hpBefore": ev[0].get("hpBefore"), "nativeUtility": None,
                 "port_flat": [f_lo, f_hi], "port_spread": [s_lo, s_hi],
                 "port_src": [c_lo, c_hi], "u_flat": f_u, "u_spread": s_u})

    ev = native_events(rpc, case["rid"], ids[NJAL], ids[TGT], AB_PSYKER, case["p_njal"],
                       "PsykerPlaybook")
    n_lo, n_hi = bounds_of(ev[0])
    tgt_id = ev[0].get("targetId")
    if not isinstance(tgt_id, int):
        raise MontageError("event psyker sans cible resolue : %r" % (str(ev[0])[:250],))
    pf, amt = port_bounds_psyker(case["ctx_njal"], ids[NJAL], tgt_id, case["p_njal"], 0)
    ps, _ = port_bounds_psyker(case["ctx_njal"], ids[NJAL], tgt_id, case["p_njal"], 20)
    pc, _ = port_bounds_psyker(case["ctx_njal"], ids[NJAL], tgt_id, case["p_njal"], None)
    f_lo, f_hi, f_u = bounds_and_utility(case["ctx_njal"], pf, tgt_id)
    s_lo, s_hi, s_u = bounds_and_utility(case["ctx_njal"], ps, tgt_id)
    c_lo, c_hi, _cu = bounds_and_utility(case["ctx_njal"], pc, tgt_id)
    rows.append({"regime": "P_SPLASH", "playbook": "PsykerExtraAttack(1013)", "amount": amt,
                 "events": len(ev), "native": [n_lo, n_hi], "target": tgt_id,
                 "hpBefore": ev[0].get("hpBefore"),
                 "nativeKill": [ev[0].get("willBeKill"), ev[0].get("mightBeKill")],
                 "port_flat": [f_lo, f_hi], "port_spread": [s_lo, s_hi],
                 "port_src": [c_lo, c_hi], "u_flat": f_u, "u_spread": s_u})
    return rows


def verdict(rows: list) -> tuple:
    """PASS ssi, sur CHAQUE regime :

      (a) les bornes NATIVES sont DISTINCTES -- le canal N'EST PAS << predefini >>. C'est le
          discriminant NU : `min == max` est la signature EXCLUSIVE d'un montant predefini
          (`spread_to_min_max(base, 0)`), et aucun autre etage du pipeline ne peut ecarter les
          deux bornes -- armure, percage et caps sont appliques aux DEUX ;
      (b) la lecture `spread_pct=0` du port rend bien `min == max` -- la contre-epreuve MORD
          (sans ca, la comparaison serait aveugle au bouton mesure) ;
      (c) la lecture du port au spread PAR DEFAUT reproduit les DEUX bornes natives.

    Le RAPPORT `1.2/0.8` n'est PAS un critere : l'armure est SOUSTRACTIVE, elle deplace les deux
    bornes de la meme quantite et ne conserve donc pas leur rapport. Ce qu'elle conserve, c'est
    leur ECART -- d'ou le critere (a) sur la difference, et (c) sur les valeurs."""
    errs = []
    for r in rows:
        lo, hi = r["native"]
        if hi <= 0:
            errs.append("%s: bornes natives nulles (%r) -- regime degenere, la mesure ne separe "
                        "rien" % (r["regime"], r["native"]))
            continue
        if abs(hi - lo) <= EPS:
            errs.append("%s: le natif rend min == max (%r) -- le canal EST predefini, la lecture "
                        "`spread_pct=0` serait la bonne" % (r["regime"], r["native"]))
            continue
        if abs(r["port_flat"][1] - r["port_flat"][0]) > EPS:
            errs.append("%s: la lecture `spread_pct=0` ne rend PAS min == max (%r) -- la "
                        "contre-epreuve ne mord pas" % (r["regime"], r["port_flat"]))
        if abs(r["port_spread"][0] - lo) > EPS or abs(r["port_spread"][1] - hi) > EPS:
            errs.append("%s: le port au spread par defaut rend %r contre %r au natif"
                        % (r["regime"], r["port_spread"], r["native"]))
        # (d) LE CLIQUET : ce que la SOURCE fait, sans forcage. Sans cette ligne, le probe
        #     resterait VERT si `spread_pct=0` revenait dans le port -- les deux colonnes
        #     precedentes sont forcees, donc indifferentes a la source.
        if abs(r["port_src"][0] - lo) > EPS or abs(r["port_src"][1] - hi) > EPS:
            errs.append("%s: le port TEL QU'ECRIT rend %r contre %r au natif -- le `spread_pct` "
                        "de la source n'est pas celui du natif (#449)"
                        % (r["regime"], r["port_src"], r["native"]))
    return (not errs), errs


# --------------------------------------------------------------------------- entree

def build_args(hp_splash: int | None = None) -> list:
    """Les arguments `rl_duel build` du montage. `hp_splash` cale les PV de la cible de splash
    (phase FLIP). Partages avec la garde jumelle, qui passe par la fixture `build_runner`."""
    a = ["--board", BOARD, "--p-units", ",".join((BULL, NJAL)), "--a-units", ",".join(FOES)]
    if hp_splash is not None:
        a += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (SPLASH, hp_splash, hp_splash)]
    return a


def _build(state_file: str, hp_splash: int | None = None) -> int:
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", state_file,
            *build_args(hp_splash)]
    proc = subprocess.run(args, cwd=_HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not os.path.exists(state_file):
        raise MontageError("build KO: %s" % ((proc.stderr or proc.stdout or "")[-400:],))
    with open(state_file, encoding="utf-8") as fh:
        return int(json.load(fh)["runnerId"])


def measure_flip(rpc, case: dict, hp: int) -> dict:
    """GENERALISATION -- un regime ou la lecture du spread CHANGE le resultat observable.

    Les PV de la cible de splash sont cales STRICTEMENT ENTRE la borne basse a spread et le
    montant plat : le natif ne peut alors PAS garantir le kill (`WillBeKill` faux, borne min
    `0.8 x d` sous les PV) mais il le juge POSSIBLE (`MightBeKill` vrai, borne max `1.2 x d`
    au-dessus). La lecture `spread_pct=0`, elle, a `min == max == d >= PV` : elle rend
    `killSure` VRAI. C'est la bascule `DefinitelyKill` -> `PossibleKill` de
    `IdunBattle.AI.Utilities.KillUnitUtility`, soit un ECART D'UTILITE FRANC, la ou le regime
    de la phase 1 rendait le MEME chiffre des deux cotes."""
    ids = case["ids"]
    ev = native_events(rpc, case["rid"], ids[NJAL], ids[TGT], AB_PSYKER, case["p_njal"],
                       "PsykerPlaybook")
    e0 = next((e for e in ev if e.get("targetId") == ids[SPLASH]), None)
    if e0 is None:
        raise MontageError("FLIP : aucun event capture sur la cible de splash %d -- le regime "
                           "n'est pas celui qu'on croit (cibles vues : %r)"
                           % (ids[SPLASH], [e.get("targetId") for e in ev]))
    n_lo, n_hi = bounds_of(e0)
    pf, _amt = port_bounds_psyker(case["ctx_njal"], ids[NJAL], ids[SPLASH], case["p_njal"], 0)
    ps, _ = port_bounds_psyker(case["ctx_njal"], ids[NJAL], ids[SPLASH], case["p_njal"], 20)
    f_lo, f_hi, f_u = bounds_and_utility(case["ctx_njal"], pf, ids[SPLASH])
    s_lo, s_hi, s_u = bounds_and_utility(case["ctx_njal"], ps, ids[SPLASH])
    return {"regime": "P_KILLFLIP", "hp": hp, "hpBefore": e0.get("hpBefore"),
            "native": [n_lo, n_hi],
            "nativeWillBeKill": e0.get("willBeKill"), "nativeMightBeKill": e0.get("mightBeKill"),
            "port_flat": [f_lo, f_hi], "port_spread": [s_lo, s_hi],
            "u_flat": f_u, "u_spread": s_u,
            "killSure_flat": pf.will_be_kill(), "killSure_spread": ps.will_be_kill()}


def verdict_flip(fl: dict) -> tuple:
    """PASS ssi le natif REFUSE le kill garanti et l'ADMET comme possible, la ou la lecture
    `spread_pct=0` le GARANTIT -- et que l'utilite en differe franchement."""
    errs = []
    if fl["nativeWillBeKill"] is not False:
        errs.append("FLIP : le natif rend willBeKill=%r (attendu False) -- les PV %d ne sont pas "
                    "entre les bornes %r" % (fl["nativeWillBeKill"], fl["hp"], fl["native"]))
    if fl["nativeMightBeKill"] is not True:
        errs.append("FLIP : le natif rend mightBeKill=%r (attendu True) -- les PV %d sont "
                    "au-dessus de la borne haute %r" % (fl["nativeMightBeKill"], fl["hp"],
                                                        fl["native"]))
    if fl["killSure_flat"] is not True:
        errs.append("FLIP : la lecture `spread_pct=0` ne garantit PAS le kill (%r) -- le regime "
                    "ne separe pas les deux lectures" % (fl["killSure_flat"],))
    if fl["killSure_spread"] is not False:
        errs.append("FLIP : la lecture au spread garantit le kill (%r) alors que le natif ne le "
                    "garantit pas" % (fl["killSure_spread"],))
    if abs(fl["u_flat"] - fl["u_spread"]) < 1.0:
        errs.append("FLIP : les deux lectures rendent la MEME utilite (%.6f vs %.6f) -- le canal "
                    "reste degenere, la generalisation ne prouve rien"
                    % (fl["u_flat"], fl["u_spread"]))
    return (not errs), errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du runner (hors data/)")
    ap.add_argument("--no-flip", action="store_true",
                    help="ne joue que la phase BORNES (pas la generalisation kill-flip)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r.get("result") or {}

    rid = _build(args.state_file)
    try:
        case = stage(sid, rpc, rid)
        rows = measure(rpc, case)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    ok, errs = verdict(rows)

    fl, fok, ferrs = None, True, []
    if not args.no_flip:
        psy = next(r for r in rows if r["regime"] == "P_SPLASH")
        lo = psy["native"][0]
        flat = psy["port_flat"][0]
        if flat <= lo + 1:
            raise MontageError("FLIP impossible : la borne plate %.2f n'est pas strictement "
                               "au-dessus de la borne basse %.2f" % (flat, lo))
        hp = int((lo + flat) // 2) + 1                 # lo < hp <= flat  -> la bascule
        rid2 = _build(args.state_file, hp_splash=hp)
        try:
            case2 = stage(sid, rpc, rid2)
            fl = measure_flip(rpc, case2, hp)
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid2}, 60)
            except Exception:
                pass
        fok, ferrs = verdict_flip(fl)

    ok = ok and fok
    errs = errs + ferrs
    if args.json:
        print(json.dumps({"rows": rows, "flip": fl, "ok": ok, "errors": errs}, indent=1))
    else:
        print("== #449 -- spread du slot de montant (board %s, seed %s) ==" % (BOARD, SEED))
        for r in rows:
            lo, hi = r["native"]
            print("  %-10s %-24s amount=%-6d events=%d target=%r hp=%r"
                  % (r["regime"], r["playbook"], r["amount"], r["events"], r["target"],
                     r["hpBefore"]))
            print("      natif       [%10.2f, %10.2f]  ecart=%.2f" % (lo, hi, hi - lo))
            print("      port sp=0   [%10.2f, %10.2f]  u=%.9f" % (r["port_flat"][0],
                                                                  r["port_flat"][1], r["u_flat"]))
            print("      port sp=20  [%10.2f, %10.2f]  u=%.9f" % (r["port_spread"][0],
                                                                  r["port_spread"][1],
                                                                  r["u_spread"]))
            print("      port SOURCE [%10.2f, %10.2f]  <- sans forcage (le cliquet)"
                  % tuple(r["port_src"]))
            print("      delta u (sp=20 - sp=0) = %+.9f   <- le canal UTILITE" % (
                r["u_spread"] - r["u_flat"]))
        if fl is not None:
            print("  %-10s PV cales a %d (entre la borne basse et le montant plat)"
                  % (fl["regime"], fl["hp"]))
            print("      natif       [%10.2f, %10.2f]  willBeKill=%r mightBeKill=%r"
                  % (fl["native"][0], fl["native"][1], fl["nativeWillBeKill"],
                     fl["nativeMightBeKill"]))
            print("      port sp=0   [%10.2f, %10.2f]  killSure=%r u=%.9f"
                  % (fl["port_flat"][0], fl["port_flat"][1], fl["killSure_flat"], fl["u_flat"]))
            print("      port sp=20  [%10.2f, %10.2f]  killSure=%r u=%.9f"
                  % (fl["port_spread"][0], fl["port_spread"][1], fl["killSure_spread"],
                     fl["u_spread"]))
            print("      delta u (sp=20 - sp=0) = %+.9f   <- le canal MORD ici"
                  % (fl["u_spread"] - fl["u_flat"]))
        for e in errs:
            print("  KO: %s" % e)
        print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as exc:
        print("MONTAGE: %s" % exc)
        sys.exit(2)
