#!/usr/bin/env python
"""Probe DEATH-NOVA -- traits `Explodes` (1008 -> triggered 1021) et `PutridExplosion` (2028 -> 1074).

Confront LIVE vs PORT de la nova de mort, ETAGE PAR ETAGE, sur un runner isole.

Protocole (cas `--case explodes` / `--case putrid`) :
  1. build (board MC1_67, rosters explicites, `--hp-player` = maxPV CONNU du porteur).
  2. DRIVE des positions (applyAction ne verifie PAS la propriete) : porteur au centre, un ALLIE et
     un/des ENNEMIS adjacents, un ennemi CONTROLE loin (hors ring 1).
  3. pre-damage optionnel pour caler `hp_before` (discrimine overkill vs non-overkill).
  4. capture S = (decisionView, observeBattle, combatSnapshot, boardGraph, dumpRng) JUSTE avant le
     coup letal + HP de toutes les unites.
  5. coup letal LIVE (attaque normale d'un ennemi adjacent) -> HP apres.
     `live_nova[u] = hp_avant[u] - hp_apres[u]` pour toute unite AUTRE que le porteur (la cible du
     coup letal) -> c'est le degat de la NOVA seule.
  6. OFFLINE : `load_state(S)` -> marque le porteur mort -> `pre_unit_death_2_triggers(...)` ->
     `port_nova[u]`. Comparaison EXACTE live vs port, par cible.

Le probe imprime aussi la decomposition d'etage (base = pct% x maxPV, percage du profil, armure de la
cible, net) pour ne JAMAIS fitter un scalaire.

ASCII only (cp1252). Usage:
  python probe_deathnova.py --case explodes [--seed 90210] [--hp 4000] [--predamage 0.6]
  python probe_deathnova.py --case putrid   [--seed 90211] [--hp 4000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.components import UnitComponent, HealthComponent        # noqa: E402
from engine.runner.operations.triggers import pre_unit_death_2_triggers, is_overkill  # noqa: E402

STATE = Path(r"C:\Users\nicolasv\AppData\Local\Temp\claude"
             r"\C--Users-nicolasv-tacticus-tools\b2170732-95be-4660-9594-e3e86a19af08"
             r"\scratchpad\deathnova_a0b6949a.json")

# Rosters CHOISIS (pas subis) : l'allie et le controle eloigne sont SANS `Overwatch` (sinon un tir
# gratuit pendant le placement tue le porteur avant la mesure -- vecu) ; `eldarAutarch` (Aeldari) sert
# d'allie NON-DeathGuard pour le test d'exclusion par faction.
CASES = {
    # carrier, ally (meme team que le carrier), enemies (team adverse ; enemies[0] = tueur)
    # tueur = `ultraInceptorSgt` et NON `ultraTitus` : Titus porte `BeastSlayer` (-> effet
    # `BeastSlayer_ExtraBlock`, une SOURCE DE BLOCK que `--block-target 0,0` ne neutralise pas, et le
    # block est un TIRAGE non comparable dans ce protocole) ET `FinalJustice` (autre death-trigger).
    "explodes": {
        "p": ["necroSpyder", "eldarAutarch"],
        "a": ["ultraInceptorSgt", "ultraTitus", "astraBullgryn"],
        "carrier": "necroSpyder",
        # ultraTitus reste dans le roster mais HORS du ring (sa source de block fausserait la mesure).
        "ring": ["ally", "killer"],
    },
    "putrid": {
        # ally = eldarAutarch (Aeldari, PAS DeathGuard -> DOIT encaisser)
        # enemies : deathBlightbringer = DeathGuard ENNEMI (DOIT etre EPARGNE, exclusion par FACTION)
        #           ultraInceptorSgt = tueur non-DeathGuard (DOIT encaisser)
        "p": ["deathPutrifier", "eldarAutarch"],
        "a": ["ultraInceptorSgt", "deathBlightbringer", "astraBullgryn"],
        "carrier": "deathPutrifier",
    },
    # CHAINAGE : le porteur A (necroSpyder, gros maxPV -> grosse nova) est adjacent a un SECOND porteur
    # Explodes B (orksKillaKan, PV forces bas par `--hp-target`). La nova de A TUE B -> la mort de B
    # re-emet `On(PreUnitDeath_2)` -> la nova de B part a son tour (cascade re-entrante).
    # Tueur = ultraInceptorSgt (PAS ultraTitus : Titus porte le trait `FinalJustice`, un AUTRE
    # death-trigger qui tirerait quand la nova le tue -> confond la mesure).
    "chain": {
        "p": ["necroSpyder", "eldarAutarch"],
        "a": ["ultraInceptorSgt", "orksKillaKan", "astraBullgryn"],
        "carrier": "necroSpyder",
        "a_hp": 500,
    },
}


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(case, seed, hp, extra=()):
    STATE.unlink(missing_ok=True)
    cfg = CASES[case]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67", "--rank", "17",
         "--p-units", ",".join(cfg["p"]), "--a-units", ",".join(cfg["a"]),
         "--hp-player", str(hp)] + list(extra),
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[nova] build KO:", (proc.stderr or proc.stdout or "")[-600:])
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def units_of(sid, rid):
    """Indexe par **squadId** — l'id que consomment `applyAction` (`unitId`/`casterId`/`targetId`),
    `decisionView.units[].id` ET les entites du `State` offline (`load_state`). `entityId` (= squadId+1)
    n'est PAS accepte par `applyAction` (mutated=false silencieux)."""
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    return {int(u["squadId"]): u for u in (ob.get("units") or [])}


def hp_of(sid, rid):
    return {eid: (int(u.get("hp") or 0), int(u.get("hpMax") or 0))
            for eid, u in units_of(sid, rid).items()}


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction",
              {"runnerId": rid, "action": {"kind": "move", "unitId": int(uid),
                                           "to": {"col": int(col), "row": int(row)}}}, 90)


def attack(sid, rid, caster, target, ability):
    return _r(sid, "applyAction",
              {"runnerId": rid, "action": {"kind": "ability", "casterId": int(caster),
                                           "targetId": int(target),
                                           "abilityType": int(ability)}}, 120)


def normal_attack_id(dec, uid):
    """`ActiveAbilityComponent.NormalAttackType@0x28` = l'id CONCRET de l'attaque normale (per-unit,
    ex. 69 `Loki_NormalAttack`) — expose par `decisionView.units[].abilities[kind=='normal'].id`."""
    for u in (dec.get("units") or []):
        if int(u.get("id") or -1) != int(uid):
            continue
        for a in (u.get("abilities") or []):
            if a.get("kind") == "normal":
                return int(a.get("id"))
    return None


def _scan_dmg(node, target_id):
    """Extrait (min,max) de degat SANTE contre `target_id` d'une reponse `aiPredict` — scan RECURSIF
    (la shape exacte varie : dict a plat, `predictions[]`, `events[]`, ...). Retient le 1er dict qui
    porte a la fois une cle min/max de degat sante ET (si presente) la bonne cible."""
    best = [None, None]

    def _walk(n, tgt_ok):
        if isinstance(n, list):
            for x in n:
                _walk(x, tgt_ok)
            return
        if not isinstance(n, dict):
            return
        t = n.get("targetId", n.get("target"))
        ok = tgt_ok if t is None else (int(t) == int(target_id))
        mn = mx = None
        for k, v in n.items():
            kl = k.lower()
            if v is None or isinstance(v, (dict, list)):
                continue
            if "health" in kl and "min" in kl:
                mn = int(v)
            if "health" in kl and "max" in kl and "hp" not in kl:
                mx = int(v)
        if ok and mn is not None and best[0] is None:
            best[0], best[1] = mn, (mx if mx is not None else mn)
        for v in n.values():
            _walk(v, ok)

    _walk(node, True)
    return best[0], best[1]


def seed_rng(state, rng0):
    if isinstance(rng0, dict) and rng0.get("ok"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        state.rng = rng
    return state


def capture(sid, rid):
    return {
        "dec": _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180),
        "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
        "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "bg": _r(sid, "boardGraph", {"runnerId": rid}, 60),
        "rng": _r(sid, "dumpRng", {"runnerId": rid}, 30),
    }


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
    return seed_rng(st, cap["rng"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), required=True)
    ap.add_argument("--seed", type=int, default=90210)
    ap.add_argument("--hp", type=int, default=4000)
    ap.add_argument("--predamage", type=int, default=0,
                    help="nb d'attaques non letales AVANT le coup letal (cale hp_before/overkill)")
    ap.add_argument("--center", default="3,4")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en fin de passe")
    ap.add_argument("--with-block", action="store_true",
                    help="NE PAS neutraliser le block des a-units (mesure du tirage de block ; "
                         "l'issue peut differer live/port par desync de POSITION RNG)")
    ap.add_argument("--dump-cap", default=None,
                    help="ecrit la capture S + les deltas LIVE en JSON (rejeu offline sans live)")
    args = ap.parse_args()

    sid = _resolve_session()
    # `--block-target 0,0` : ANNULE le block des a-units. Le block est un TIRAGE (`CalculateBlockChances
    # IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` -> sub-op 0x42) qui A LIEU dans la famille ABILITY (PROUVE live : Titus a encaisse 0
    # d'une nova de 75). Or le port rejoue la nova depuis la capture S avec un RNG cale AVANT le coup
    # letal : le natif, lui, a deja consomme des tirages pour l'attaque letale -> desync de POSITION RNG
    # -> l'issue du tirage de block peut differer des deux cotes SANS que le modele soit faux. On
    # NEUTRALISE donc le block pour mesurer l'etage DEGAT, et on mesure le block a part (--with-block).
    extra = [] if args.with_block else ["--block-target", "0,0"]
    if CASES[args.case].get("a_hp"):
        extra += ["--hp-target", str(CASES[args.case]["a_hp"])]
    rid = build(args.case, args.seed, args.hp, extra)
    print("[nova] case=%s runnerId=%s hp-player=%d" % (args.case, rid, args.hp))

    cfg = CASES[args.case]
    ob = units_of(sid, rid)
    by_vis = {}
    for eid, u in ob.items():
        by_vis.setdefault(u.get("visualId"), []).append(eid)
    carrier = by_vis[cfg["carrier"]][0]
    ally = by_vis[cfg["p"][1]][0]
    killer = by_vis[cfg["a"][0]][0]
    adj_enemy = by_vis[cfg["a"][1]][0]
    far_enemy = by_vis[cfg["a"][2]][0]
    print("[nova] carrier=u%d ally=u%d killer=u%d adjEnemy=u%d farEnemy=u%d"
          % (carrier, ally, killer, adj_enemy, far_enemy))

    # --- geometrie DRIVEE : ring 1 autour du porteur ---------------------------------------------
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = [int(x) for x in args.center.split(",")]
    ctile = board.id_at(ccol, crow)
    ring = [board.coord(t) for t in board.neighbours(ctile)]
    print("[nova] centre=(%d,%d) ring1=%s" % (ccol, crow, ring))
    if len(ring) < 3:
        print("[nova] centre trop pauvre en voisins"); sys.exit(2)

    # eloigner d'abord TOUT ce qui n'est pas sur le ring (controles du gate de zone), puis placer
    roles = {"ally": ally, "killer": killer, "adj": adj_enemy, "far": far_enemy}
    ring_roles = cfg.get("ring") or ["ally", "killer", "adj"]
    for uid, (c, r) in zip([roles[k] for k in ("far", "adj", "ally", "killer") if k not in ring_roles],
                           [(6, 0), (6, 8), (0, 8)]):
        move(sid, rid, uid, c, r)
    move(sid, rid, carrier, ccol, crow)
    for role, (c, r) in zip(ring_roles, ring):
        move(sid, rid, roles[role], c, r)

    ob = units_of(sid, rid)
    dirty = []
    for uid in (carrier, ally, killer, adj_enemy, far_enemy):
        u = ob[uid]
        print("   u%-3d %-20s pos=(%s,%s) hp=%s/%s team=%s"
              % (uid, u.get("visualId"), u.get("col"), u.get("row"), u.get("hp"),
                 u.get("hpMax"), u.get("teamId")))
        if int(u.get("hp") or 0) != int(u.get("hpMax") or 0):
            dirty.append(uid)
    if dirty:
        # GARDE anti-pollution : un tir d'overwatch (ou tout degat) pendant le PLACEMENT fausserait la
        # mesure. On refuse au lieu de mesurer un etat sale.
        print("[nova] SETUP POLLUE (PV entames pendant le placement) sur %s -> abandon" % dirty)
        if not args.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sys.exit(4)

    dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    na = normal_attack_id(dec, killer)
    print("[nova] normal-attack id du tueur u%d = %s" % (killer, na))
    if na is None:
        print("[nova] id d'attaque normale introuvable"); sys.exit(2)

    # --- pre-damage optionnel (cale hp_before pour discriminer overkill) --------------------------
    for i in range(args.predamage):
        r = attack(sid, rid, adj_enemy, carrier, normal_attack_id(dec, adj_enemy) or na)
        hp = hp_of(sid, rid)
        print("[nova] pre-damage #%d -> carrier hp=%d/%d (ok=%s)"
              % (i + 1, hp[carrier][0], hp[carrier][1], r.get("ok")))
        if hp[carrier][0] <= 0:
            print("[nova] pre-damage a TUE le porteur -> baisse --predamage"); sys.exit(2)

    # --- capture S (juste avant le coup letal) ----------------------------------------------------
    cap = capture(sid, rid)
    hp_before = hp_of(sid, rid)
    print("[nova] HP avant coup letal : %s"
          % {("u%d" % k): v[0] for k, v in sorted(hp_before.items())})

    # --- CLASSIFICATION OVERKILL (observable, PAS devinee) ----------------------------------------
    # `is_overkill IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : overkill ssi `dmg - PV >= overkillDmgPctOfHealth%(=100) * PV`, i.e.
    # `dmg >= 2*PV_courant`. Le degat REEL du coup letal n'est pas lisible (HP clampe a 0) -> on borne
    # via la PREDICTION native (`aiPredict` = `GetAllPredictions`, preview de l'attaque normale) :
    #   dmg_min >= 2*hp   -> OVERKILL CERTAIN
    #   dmg_max <  2*hp   -> NON-OVERKILL CERTAIN (si le coup tue, i.e. dmg >= hp)
    pred = _r(sid, "aiPredict", {"runnerId": rid, "unitId": killer, "targetId": carrier,
                                 "abilityType": na}, 90)
    print("[nova] aiPredict brut : %s" % json.dumps(pred, default=str)[:700])
    p = (pred or {}).get("pred") or {}
    # `healthDmg*` est CAPE a `hpBefore` (inutilisable pour l'overkill) ; `totalDmg*` est le degat
    # BRUT (sante+armure+bouclier) -> il EGALE le degat sante brut quand la cible n'a ni armure-pool
    # ni bouclier (`armorBefore == 0 and shieldBefore == 0`), ce qui est le cas de nos porteurs.
    if int(p.get("armorBefore") or 0) == 0 and int(p.get("shieldBefore") or 0) == 0 \
            and p.get("totalDmgMin") is not None:
        dmin, dmax = int(p["totalDmgMin"]), int(p["totalDmgMax"])
        print("[nova] degat BRUT du coup letal (armure/bouclier nuls) = [%d,%d]" % (dmin, dmax))
    else:
        dmin, dmax = _scan_dmg(pred, carrier)
    hpc = hp_before[carrier][0]
    if dmin is None:
        ovk_class = "INDETERMINE (prediction illisible : %s)" % json.dumps(pred, default=str)[:900]
    elif dmin >= 2 * hpc:
        ovk_class = "OVERKILL CERTAIN (dmg_min=%d >= 2*PV=%d)" % (dmin, 2 * hpc)
    elif dmax is not None and dmax < 2 * hpc:
        ovk_class = "NON-OVERKILL CERTAIN (dmg_max=%d < 2*PV=%d)" % (dmax, 2 * hpc)
    else:
        ovk_class = "INDETERMINE (plage [%s,%s] chevauche 2*PV=%d)" % (dmin, dmax, 2 * hpc)
    print("[nova] prediction du coup letal = [%s,%s] vs PV=%d -> %s" % (dmin, dmax, hpc, ovk_class))
    # PREUVE STRUCTURELLE COMPLEMENTAIRE : un porteur `Resilient` ne peut PAS mourir d'un coup
    # NON-overkill (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` : `if not overkill: cap = curHP-1`).
    # S'il meurt, le coup ETAIT un overkill — independamment de toute prediction.
    import gameconfig as _GC
    _tr = (_GC.unit(CASES[args.case]["carrier"]) or {}).get("traits") or []
    print("[nova] porteur `Resilient` ? %s  (si OUI : mort d'un coup => OVERKILL structurellement certain)"
          % ("OUI" if "Resilient" in _tr else "non"))

    # --- coup letal LIVE --------------------------------------------------------------------------
    res = attack(sid, rid, killer, carrier, na)
    hp_after = hp_of(sid, rid)
    print("[nova] applyAction ok=%s mutated=%s" % (res.get("ok"), res.get("mutated")))
    print("[nova] HP apres coup letal : %s"
          % {("u%d" % k): v[0] for k, v in sorted(hp_after.items())})
    if hp_after[carrier][0] > 0:
        print("[nova] LE PORTEUR N'EST PAS MORT (hp=%d) -> augmente --predamage" % hp_after[carrier][0])
        if not args.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sys.exit(3)

    live_nova = {uid: hp_before[uid][0] - hp_after[uid][0]
                 for uid in hp_before if uid != carrier}
    # flag overkill THREADE au vecteur offline : borne basse observable de la prediction (aucun
    # consommateur de `On(2)` ne le lit -- les DEUX novas passent `a=1` = pas de gate -- mais on le
    # thread quand meme pour que le probe teste bien la MEME valeur des deux cotes).
    ovk = is_overkill(hpc, dmin if dmin is not None else hpc)
    print("[nova] coup letal : classification=%s -> overkill threade au port=%s" % (ovk_class, ovk))
    print("[nova] LIVE nova par cible : %s" % {("u%d" % k): v for k, v in sorted(live_nova.items())})

    if args.dump_cap:
        Path(args.dump_cap).write_text(json.dumps(
            {"cap": cap, "carrier": carrier, "killer": killer, "ally": ally,
             "adj_enemy": adj_enemy, "far_enemy": far_enemy, "live_nova": live_nova,
             "hp_before": {str(k): v for k, v in hp_before.items()},
             "hp_after": {str(k): v for k, v in hp_after.items()},
             "overkill": ovk, "ovk_class": ovk_class}, default=str), encoding="utf-8")
        print("[nova] capture ecrite -> %s" % args.dump_cap)

    # --- PORT (offline, depuis S) -----------------------------------------------------------------
    st = offline_state(cap)
    ce = st.get_entity(carrier)
    if ce is None:
        print("[nova] porteur absent de l'etat offline"); sys.exit(2)
    hc = ce.get_component(HealthComponent)
    maxhp = int(hc.hp_max or 0)
    uc = ce.get_component(UnitComponent)
    if uc is not None:
        uc.alive = False
    hp_off_before = {eid: int((e.get_component(HealthComponent) or HealthComponent()).hp or 0)
                     for eid, e in st.entities.items()
                     if e.get_component(HealthComponent) is not None}
    out = pre_unit_death_2_triggers(st, carrier, killer, overkill=ovk)
    hp_off_after = {eid: int((e.get_component(HealthComponent) or HealthComponent()).hp or 0)
                    for eid, e in st.entities.items()
                    if e.get_component(HealthComponent) is not None}
    port_nova = {eid: hp_off_before[eid] - hp_off_after[eid]
                 for eid in hp_off_before if eid != carrier}
    print("[nova] PORT resultats bruts : %s" % json.dumps(out, default=str)[:900])
    print("[nova] PORT nova par cible : %s" % {("u%d" % k): v for k, v in sorted(port_nova.items())})
    print("[nova] maxPV(carrier) offline = %d" % maxhp)

    # --- verdict ----------------------------------------------------------------------------------
    keys = sorted(set(live_nova) | set(port_nova))
    bad = []
    for k in keys:
        lv, pv = live_nova.get(k, 0), port_nova.get(k, 0)
        flag = "OK " if lv == pv else "MISMATCH"
        print("   u%-3d live=%-8d port=%-8d %s" % (k, lv, pv, flag))
        if lv != pv:
            bad.append(k)
    print("[nova] VERDICT : %s" % ("PASS (live == port sur toutes les cibles)" if not bad
                                   else "FAIL sur %s" % bad))

    if not args.keep:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        print("[nova] runner %s dispose" % rid)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
