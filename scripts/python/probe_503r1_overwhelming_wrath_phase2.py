#!/usr/bin/env python3
"""probe_503-r1 -- MESURE de la PHASE 2 de `1141 OverwhelmingWrath` (`worldEightbound` << Azkor >>).

QUESTION BINAIRE, posee AVANT la methode : **au debut de quel tour le `2x Eviscerate` part-il, sur
QUELLES cibles, et pour combien de degat ?** #503 a etabli que le CAST ne frappe pas (il pose
`1301 _RangeDmgReduction`, `27 Taunted_OnlySpecificTargets` et `1300 _PendingAttack`) et laisse le
degat a une TRIGGERED non portee -- residu #503-r1, que cette tranche ferme.

L'ARTEFACT est `...Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour` (1237), arme par
l'effet `1300`, derive d'`IdunBattle.Entities.Effects.APendingAttackEffect` -- le MEME foyer que
`1069` (#513).

⚠ CE PORTEUR NE DISCRIMINE PAS `GetAttackingUnitSelector` : `AddBondEffect(1300, targets =
Caster@DSLSelectors+0x48, bondedEntity = Caster@+0x48)` pose l'effet SUR le caster et le bonde AU
caster. Porteur et bonde coincident, donc -- contrairement a 1069, ou ils appartiennent a deux
JOUEURS -- ce probe ne peut PAS trancher ce selecteur, et il ne pretend pas le faire : cette lecture
reste attestee par la mesure de #513. Ce que ce probe-ci mesure, c'est l'ARBRE DE DEGAT et son RANG.

ETAGES (chaque etage a son oracle natif -- jamais un scalaire fitte) :
  [1] CAST : port == natif, empreinte d'effets (garde de non-regression #503)
  [2] TOUR ENNEMI : RIEN ne part, des DEUX cotes. TEMOIN NEGATIF -- il attribue le degat de [3] au
      bon tour ; sans lui, un port qui frapperait a chaque debut de tour passerait [3] aussi.
  [3] TOUR DU CASTER : les coups partent. CIBLES port == natif, DEGAT port == natif sur un MT CALE.
  [4] EFFETS : `1300` DISPARAIT des deux cotes (le `RemoveEffect` du `Triggered()`).
  [5] TIRAGES : le nombre de `genrand_int32` consommes est le MEME des deux cotes. Un accord sur le
      seul degat ne prouve rien -- deux implementations peuvent tomber juste en decalant le flux.
  [6] CARDINAL : au moins DEUX cibles adjacentes sont frappees. C'est ce qui exerce le `multi=True`
      (UN `AttackBehaviour` portant N cibles -> `OrderBy(b__5_0)`) ; a une seule cible, `multi`
      True et False rendent le MEME resultat et l'accord ne prouverait rien.

Les `endturn` sont NUS : aucune unite n'agit entre les bornes. Le placement est FORCE
(`--place`/`--a-place`) -- << bloque par la geometrie de spawn >> n'est pas un resultat.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_503r1_overwhelming_wrath_phase2.py [--state-file <chemin ABSOLU>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

OVERWHELMING_WRATH = 1141      # ActiveAbilityType.OverwhelmingWrath
OW_RANGE_DMG_REDUCTION = 1301  # EffectType.OverwhelmingWrath_RangeDmgReduction
OW_PENDING_ATTACK = 1300       # EffectType.OverwhelmingWrath_PendingAttack
TAUNTED = 27                   # EffectType.Taunted_OnlySpecificTargets
OW_ATTACK = 1237               # TriggeredAbilityType.OverwhelmingWrath_Attack
BOARD = "MC1_67"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/worldeaters.py",
                "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
                "scripts/python/engine/runner/abilities/behaviours/combat.py",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/runner/operations/damage_ops/ability.py",
                "scripts/python/engine/entities/selectors/units.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la PHASE 2 de 1141 : le foyer APendingAttackEffect (vecteur "
              "On(0x15 = TurnStart_DelayedAttacks) + noeud TriggerAbility) ET l'arbre de degat "
              "MULTI-cibles de la triggered 1237.",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-1500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind_transport(sid: int):
    """LIE le transport ambiant que `load_state` utilise pour tirer `unitAbilityStates` lui-meme.

    ⚠ SANS LUI, LE KIT DECLENCHE DU CASTER EST AMPUTE ET RIEN NE PART -- mesure de #513, qui vaut
    a l'identique ici : `entity_triggered_ability_ids` retomberait sur le kit GAMECONFIG, qui ne
    porte AUCUNE des abilities DERIVEES d'une active
    (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, dictionnaire peuple au
    runtime). `1237` en fait partie -- le gameconfig de `worldEightbound` ne declare que
    `activeAbilities: ["OverwhelmingWrath"]` et `passiveAbilities: ["BeaconOfRage"]`. Le gate
    `GetAbilityState` d'`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`
    refuserait alors l'attaquant (`notCarrying: [<caster>]`, `dispatched: True`, ZERO degat)."""
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def footprint_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(u["id"])] = effs
    return out


def footprint_off(state) -> dict:
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def rng_dump(sid, rid) -> dict:
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def seed_offline_rng(state, dump):
    """CALE le MT offline sur le MT LIVE (`dumpRng`). Sans ce calage `state.rng is None` et le rail
    de degat SKIP par repli defensif : on lirait un `0` FAUX au lieu d'un `0` MESURE."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def find(dec, visual_id):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)


def _player_of(state, uid: int):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return None if oc is None else int(oc.player)


def _hp_delta(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


def measure(sid: int, seed: str = "777", board: str = BOARD,
            state_name: str = "probe_503r1_overwhelming_wrath_phase2",
            hooks: dict | None = None):
    """Monte le scenario, joue le cast PUIS les deux passages de tour des DEUX cotes, rend
    `(mesures, dispose)`. Le TEST de garde appelle CETTE fonction -- une seule implementation du
    montage et des lectures.

    LE PLACEMENT EST CHOISI POUR L'ETAGE [6] : DEUX ennemis colles a Azkor. Le selecteur de la
    phase 2 est `AdjacentEnemies(Caster@+0x48, unique: 1, sel: 3)` -- il ne depend PAS de la cible
    du cast, donc c'est la geometrie AUTOUR DU CASTER qui fixe le cardinal, et c'est elle qu'on
    force.

    `hooks` (#503-r4) : `{"avant_tir": f(sid, rid), "apres_tir": f(sid, rid) -> obj}`. Le SEUL
    point d'extension, et il est place autour du pas natif qui declenche le tir -- c'est ce qui
    permet a `probe_503r4_ventilation_par_coup.py` d'armer `hit-trace` sur CE pas et rien d'autre
    SANS re-ecrire le montage. Dupliquer le montage rendrait les deux mesures incomparables, et
    c'est la comparaison qui est tout l'objet."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "worldEightbound,worldJakhal",
        "--a-units", "orksNob,orksRuntherd",
        "--place", "worldEightbound:2,3", "--place", "worldJakhal:1,1",
        "--a-place", "orksNob:2,4", "--a-place", "orksRuntherd:3,3"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid, hooks=hooks), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int, hooks: dict | None = None) -> dict:
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind_transport(sid)
    dec0 = decision(sid, rid)
    caster = find(dec0, "worldEightbound")
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : worldEightbound absent du decisionView")
    caster_id = int(caster["id"])

    # Cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset move-inclus).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": OVERWHELMING_WRATH}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == OVERWHELMING_WRATH), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1141")
    target_id = int(from_here[0])

    # ---- OFFLINE : le MEME cast, joue par le port -----------------------------------------
    state, _ = load(sid, rid)
    seed_offline_rng(state, rng_dump(sid, rid))
    off_before = footprint_off(state)
    off_hp0 = hp_off(state)
    res = _apply_active_ability(state, caster_id, target_id, OVERWHELMING_WRATH) or {}
    off_cast = delta(off_before, footprint_off(state))
    mon_joueur = _player_of(state, caster_id)
    joueur_adverse = _player_of(state, target_id)

    # ---- LIVE : le MEME cast, joue par le natif -------------------------------------------
    live_before = footprint_live(dec0)
    live_hp0 = hp_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": OVERWHELMING_WRATH,
        "targetId": target_id}}, 90) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = decision(sid, rid)
    live_cast = delta(live_before, footprint_live(dec1))

    # ---- [2] TOUR ENNEMI : le TEMOIN NEGATIF ----------------------------------------------
    # PORT : le vecteur `On(0x15)` avec le joueur ADVERSE. Le gate `IsTurnOf(bonded)` doit refuser.
    off_hp_avant_ennemi = hp_off(state)
    off_ennemi = delayed_attack_triggers(state, joueur_adverse)
    off_hp_apres_ennemi = hp_off(state)
    # NATIF : un `endturn` NU (aucune unite n'agit).
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dec2 = decision(sid, rid)
    live_hp_apres_ennemi = hp_live(sid, rid)
    rng_avant = rng_dump(sid, rid)

    # ---- [3][4][5][6] TOUR DU CASTER ------------------------------------------------------
    # Le MT offline est (re)cale sur le MT LIVE JUSTE AVANT le pas natif : les deux tirent donc a
    # partir du meme etat interne, ce qui rend les deux degats comparables A L'UNITE PRES.
    rng_off = seed_offline_rng(state, rng_avant)
    # ETAGE [3bis] : les stats DEFENSIVES des cibles, lues AVANT le tir. Sans elles, un ecart de
    # total ne se rattache a aucun etage nomme et on en serait reduit a chercher un facteur.
    stats_cibles = {int(u["id"]): _stats_def(state, int(u["id"]))
                    for u in (dec2.get("units") or []) if u.get("id") is not None}
    off_hp_avant = hp_off(state)
    off_foot_avant = footprint_off(state)
    off_tir = delayed_attack_triggers(state, mon_joueur)
    off_hp_apres = hp_off(state)
    off_foot_apres = footprint_off(state)
    off_draws = int(getattr(rng_off, "call_count", 0) or 0)

    # `captureEvents` : le TROISIEME etage de la decomposition. Le delta de PV dit COMBIEN, la
    # ventilation par coup dit COMMENT -- et c'est elle, sur #478, qui a distingue « le port se
    # trompe de montant » de « il manque un volet ». Sans elle une divergence de total ne se
    # decompose pas et on en serait reduit a fitter le scalaire.
    if hooks and hooks.get("avant_tir"):
        hooks["avant_tir"](sid, rid)
    act3 = rpc(sid, "applyAction",
               {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 90) or {}
    extra = hooks["apres_tir"](sid, rid) if (hooks and hooks.get("apres_tir")) else None
    dec3 = decision(sid, rid)
    live_hp_apres = hp_live(sid, rid)
    rng_apres = rng_dump(sid, rid)

    return {
        "extra": extra,
        "rid": rid, "caster": caster_id, "target": target_id, "from_here": from_here,
        "mon_joueur": mon_joueur, "joueur_adverse": joueur_adverse,
        "routed": res.get("routed"), "ported": (res.get("diag") or {}).get("ported"),
        "cast_error": cast_error, "off_cast": off_cast, "live_cast": live_cast,
        "off_hp0": off_hp0, "live_hp0": live_hp0,
        "off_ennemi": off_ennemi,
        "off_hp_ennemi": (off_hp_avant_ennemi, off_hp_apres_ennemi),
        "live_hp_ennemi": (live_hp0, live_hp_apres_ennemi),
        "off_tir": off_tir,
        "off_hp": (off_hp_avant, off_hp_apres),
        "live_hp": (dict(live_hp_apres_ennemi), live_hp_apres),
        "off_foot": (off_foot_avant, off_foot_apres),
        "live_foot": (footprint_live(dec2), footprint_live(dec3)),
        "off_draws": off_draws,
        "stats_cibles": stats_cibles,
        "live_coups": _coups_natifs(act3),
        "rng_avant": (rng_avant.get("callCount"), rng_avant.get("mti")),
        "rng_apres": (rng_apres.get("callCount"), rng_apres.get("mti")),
    }


def _stats_def(state, uid: int) -> dict:
    """Les stats DEFENSIVES d'une unite, telles que le port les lit -- pour rattacher un ecart de
    total a un ETAGE NOMME (armure, block, crit) plutot qu'a un facteur."""
    from engine.runner.components import StatsComponent
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return {}
    return {k: getattr(ctx, k, None) for k in
            ("armor", "block_dmg", "block_chance", "crit_dmg", "crit_chance", "damage")}


def _coups_natifs(act: dict) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS du pas, dans l'ORDRE d'emission.

    Meme lecture que `probe_478_cleave_additional_targets.py` : les evenements portent un `tags`
    JSON, et tout evenement qui porte `Amount` est un coup applique."""
    out = {}
    for a in (act.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU du state-file (defaut : logs/runners/<nom du probe>.json)")
    args = ap.parse_args()

    sid = _session()
    print("[build] board=%s" % BOARD)
    kw = {}
    if args.state_file:
        kw["state_name"] = Path(args.state_file).stem
    m, dispose = measure(sid, **kw)
    rc = 0
    try:
        cid, tid = m["caster"], m["target"]
        print("[scenario] caster=u%d (joueur %s) target=u%d ; fromHere=%s"
              % (cid, m["mon_joueur"], tid, m["from_here"]))

        print("\n[1] CAST -- port == natif (garde de non-regression #503)")
        print("    routed=%s ported=%s cast_error=%s" % (m["routed"], m["ported"], m["cast_error"]))
        print("    port  = %s" % m["off_cast"])
        print("    natif = %s" % m["live_cast"])
        if m["cast_error"]:
            print("    ECHEC : le cast natif a rendu une erreur -- rien n'est mesurable ensuite")
            rc = 1

        print("\n[2] TOUR ENNEMI -- TEMOIN NEGATIF : rien ne part")
        d_off = _hp_delta(*m["off_hp_ennemi"])
        d_live = _hp_delta(*m["live_hp_ennemi"])
        print("    port  : delta HP = %s ; triggers = %s" % (d_off, m["off_ennemi"]))
        print("    natif : delta HP = %s" % d_live)
        if d_off or d_live:
            print("    ECHEC : quelque chose a frappe au tour ENNEMI")
            rc = 1

        print("\n[3] TOUR DU CASTER -- les coups partent")
        d_off = _hp_delta(*m["off_hp"])
        d_live = _hp_delta(*m["live_hp"])
        print("    port  : %s" % d_off)
        print("    natif : %s" % d_live)
        tirs = [t for t in (m["off_tir"] or []) if t]
        print("    port, ventilation par coup :")
        for t in tirs:
            for f in (t.get("fired") or []):
                for r in (f.get("results") or []):
                    for d in ((r or {}).get("damage") or []):
                        # ETAGES au complet, JAMAIS tronques : une divergence se decompose etage
                        # par etage jusqu'au PREMIER ou port != natif, sinon on en est reduit a
                        # fitter le scalaire.
                        print("      u%-4s total=%-7s %s"
                              % (d.get("target"), d.get("total"),
                                 json.dumps(d.get("etages"), ensure_ascii=True)))
        print("    natif, ventilation par coup (events, tag Amount) : %s"
              % json.dumps(m["live_coups"], ensure_ascii=True))
        cibles_off = {k for k in d_off}
        cibles_live = {k for k in d_live}
        if cibles_off != cibles_live:
            print("    ECHEC : ensembles de cibles DIFFERENTS -- port %s vs natif %s"
                  % (sorted(cibles_off), sorted(cibles_live)))
            rc = 1
        elif not cibles_live:
            print("    ECHEC : AUCUN degat des deux cotes -- regime DEGENERE, l'accord ne prouve "
                  "rien (cf. 'Accord en regime DEGENERE = zero preuve')")
            rc = 1
        else:
            for k in sorted(cibles_live):
                po = d_off[k][0] - d_off[k][1]
                na = d_live[k][0] - d_live[k][1]
                verdict = "OK" if po == na else "ECART %d" % (po - na)
                print("      u%-4d port %-7d natif %-7d  %s" % (k, po, na, verdict))
                if po != na:
                    rc = 1
                    st = (m["stats_cibles"] or {}).get(k) or {}
                    print("           stats def. de u%d : %s" % (k, json.dumps(st,
                                                                              ensure_ascii=True)))
                    # RATTACHER L'ECART A UN ETAGE NOMME, jamais chercher un facteur.
                    for nom in ("block_dmg", "crit_dmg", "armor"):
                        v = st.get(nom)
                        if v and int(v) == abs(po - na):
                            print("           L'ECART VAUT EXACTEMENT `%s` = %d" % (nom, int(v)))

        print("\n[4] EFFETS -- le 1300 disparait des deux cotes")
        off_a, off_b = m["off_foot"]
        live_a, live_b = m["live_foot"]
        off_pend = [u for u, e in off_b.items() if OW_PENDING_ATTACK in e]
        live_pend = [u for u, e in live_b.items() if OW_PENDING_ATTACK in e]
        print("    port  : 1300 encore porte par %s (avant : %s)"
              % (off_pend, [u for u, e in off_a.items() if OW_PENDING_ATTACK in e]))
        print("    natif : 1300 encore porte par %s (avant : %s)"
              % (live_pend, [u for u, e in live_a.items() if OW_PENDING_ATTACK in e]))
        if off_pend or live_pend:
            print("    ECHEC : l'effet 1300 survit a son propre RemoveEffect")
            rc = 1

        print("\n[5] TIRAGES -- meme consommation de genrand_int32")
        live_draws = int(m["rng_apres"][0] or 0) - int(m["rng_avant"][0] or 0)
        print("    port %d  natif %d" % (m["off_draws"], live_draws))
        if int(m["off_draws"]) != live_draws:
            print("    ECART : le flux MT diverge -- un accord sur le seul degat ne vaudrait rien")
            rc = 1

        print("\n[6] CARDINAL -- au moins DEUX cibles (c'est ce qui exerce multi=True)")
        print("    natif : %d cible(s) touchee(s)" % len(cibles_live))
        if len(cibles_live) < 2:
            print("    NON EXERCE : a une seule cible, multi=True et multi=False sont "
                  "indistinguables. Le verdict [3] reste valable, l'etage [6] non.")

        print("\nVERDICT : %s" % ("OK" if rc == 0 else "ECHEC"))
    finally:
        dispose()
    return rc


if __name__ == "__main__":
    sys.exit(main())
