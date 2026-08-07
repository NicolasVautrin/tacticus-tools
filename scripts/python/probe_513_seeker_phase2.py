"""probe_513 -- MESURE de la PHASE 2 de `1069 SeekerMissileFrequencyLock` (`tauMarksman` Sho'syl).

QUESTION BINAIRE, posee AVANT la methode : **au debut de quel tour le missile part-il, et pour
combien de degat ?** #491 avait etabli que le CAST ne frappe pas (il pose `1122 Markerlight`, `1123
_Target` et `1136 _Aiming`) et laisse le degat a une TRIGGERED non portee -- residu #491-r1. Le foyer
de ce declenchement est `IdunBattle.Entities.Effects.APendingAttackEffect$$
CreateHandleTriggerAbilitiesInternal`, commun aux 20 derivees de la famille (recensement :
`probe_513_pending_attack_family.py`).

LE DISCRIMINANT EST LE TOUR, ET IL EST STRUCTUREL. `1123` est pose SUR LA CIBLE et bonde AU CASTER :
les deux candidats de `GetAttackingUnitSelector` -- `Owner@DSLSelectors+0x30` (le porteur) et
`BondedEntityFromEffect(Effect@+0x38)` (le bonde) -- appartiennent a des JOUEURS DIFFERENTS. Le gate
`IsTurnOf` les separe donc d'un tour entier, et il suffit de regarder QUAND les PV tombent. Aucune
lecture de decompile n'etait necessaire pour trancher ; le decompile dit la meme chose, et les deux
concordent.

ETAGES (chaque etage a son oracle natif -- jamais un scalaire fitte) :
  [1] CAST : port == natif, empreinte d'effets `{caster:{1136}, cible:{1122,1123}}` (garde #491)
  [2] TOUR ENNEMI : RIEN ne part -- ni cote natif, ni cote port. C'est le TEMOIN NEGATIF qui
      attribue le degat de [3] au bon selecteur ; sans lui, un port qui tirerait sur le porteur
      passerait [3] aussi.
  [3] TOUR DU CASTER : le missile part. DEGAT port == natif, a l'unite pres, sur un MT CALE.
  [4] EFFETS : `1123` (sur la cible) et `1136` (sur le caster) DISPARAISSENT des deux cotes.
  [5] TIRAGES : le nombre de `genrand_int32` consommes est le MEME des deux cotes. Un accord sur le
      seul degat ne prouve rien -- deux implementations peuvent tomber juste en decalant le flux.

Les deux `endturn` sont NUS : aucune unite n'agit entre les bornes (pas d'`aiPlayByUnit`). Le 1er
jet laissait l'IA jouer le tour ennemi et le delta de PV n'etait attribuable a RIEN -- l'IA tuait
meme le caster.

Le placement est FORCE (`--place`/`--a-place`) : la geometrie de spawn de MC1_67 met Sho'syl hors de
sa portee 5. « Bloque par la geometrie de spawn » n'est pas un resultat.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_513_seeker_phase2.py [--state-file <chemin ABSOLU>]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

SEEKER = 1069                  # ActiveAbilityType.SeekerMissileFrequencyLock
MARKERLIGHT = 1122             # EffectType.Markerlight
SEEKER_TARGET = 1123           # EffectType.SeekerMissileFrequencyLock_Target
SEEKER_AIMING = 1136           # EffectType.SeekerMissileFrequencyLock_Aiming
SEEKER_ATTACK = 1127           # TriggeredAbilityType.SeekerMissileFrequencyLock_Attack
BOARD = "MC1_67"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/tau.py",
                "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
                "scripts/python/engine/runner/abilities/behaviours/combat.py",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/runner/operations/turnflow.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la PHASE 2 de 1069 : le foyer APendingAttackEffect (vecteur "
              "On(0x15) + trigger + noeud TriggerAbility) ET l'arbre de degat de la triggered 1127.",
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

    ⚠ SANS LUI, LE KIT DECLENCHE DU CASTER EST AMPUTE, ET LE MISSILE NE PART PAS -- mesure de cette
    tranche. `entity_triggered_ability_ids` retombe alors sur le kit GAMECONFIG
    (`triggered_ability_ids(visualId)`), qui rend `[1119]` pour `tauMarksman` la ou le
    `TriggeredAbilityComponent` NATIF porte `[1119, 1127, 1131]` -- les deux abilities DERIVEES de
    ses actives (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, un dictionnaire
    peuple au runtime, donc invisible du gameconfig). Le gate `GetAbilityState` de
    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` refusait donc
    l'attaquant : `notCarrying: [<caster>]`, `dispatched: True`, ZERO degat, et rien n'aurait dit
    pourquoi si le noeud ne publiait pas ce champ."""
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


def measure(sid: int, seed: str = "777", board: str = BOARD,
            state_name: str = "probe_513_seeker_phase2"):
    """Monte le scenario, joue le cast PUIS le passage de tour des DEUX cotes, rend
    `(mesures, dispose)`. Le TEST de garde appelle CETTE fonction -- une seule implementation du
    montage et des lectures."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "tauMarksman,tauShadowsun",
        "--a-units", "orksNob,orksRuntherd",
        "--place", "tauMarksman:2,2", "--place", "tauShadowsun:1,2",
        "--a-place", "orksNob:2,5", "--a-place", "orksRuntherd:4,4"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int) -> dict:
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind_transport(sid)
    dec0 = decision(sid, rid)
    caster = find(dec0, "tauMarksman")
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : tauMarksman absent du decisionView")
    caster_id = int(caster["id"])

    # Cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset move-inclus).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": SEEKER}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SEEKER), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1069")
    target_id = int(from_here[0])

    # ---- OFFLINE : le MEME cast, joue par le port -----------------------------------------
    state, _ = load(sid, rid)
    seed_offline_rng(state, rng_dump(sid, rid))
    off_before = footprint_off(state)
    off_hp0 = hp_off(state)
    res = _apply_active_ability(state, caster_id, target_id, SEEKER) or {}
    off_cast = delta(off_before, footprint_off(state))
    mon_joueur, joueur_cible = _player_of(state, caster_id), _player_of(state, target_id)

    # ---- LIVE : le MEME cast, joue par le natif -------------------------------------------
    live_before = footprint_live(dec0)
    live_hp0 = hp_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SEEKER,
        "targetId": target_id}}, 90) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = decision(sid, rid)
    live_cast = delta(live_before, footprint_live(dec1))

    # ---- [2] TOUR ENNEMI : le TEMOIN NEGATIF ----------------------------------------------
    # PORT : le vecteur `On(0x15)` avec le joueur ADVERSE. Le gate `IsTurnOf(bonded)` doit refuser.
    off_hp_avant_ennemi = hp_off(state)
    off_ennemi = delayed_attack_triggers(state, joueur_cible)
    off_hp_apres_ennemi = hp_off(state)
    # NATIF : un `endturn` NU (aucune unite n'agit).
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dec2 = decision(sid, rid)
    live_hp_apres_ennemi = hp_live(sid, rid)
    rng_avant = rng_dump(sid, rid)

    # ---- [3][4][5] TOUR DU CASTER ---------------------------------------------------------
    # Le MT offline est (re)cale sur le MT LIVE JUSTE AVANT le pas natif : les deux tirent donc a
    # partir du meme etat interne, ce qui rend les deux degats comparables A L'UNITE PRES.
    rng_off = seed_offline_rng(state, rng_avant)
    off_hp_avant = hp_off(state)
    off_foot_avant = footprint_off(state)
    off_tir = delayed_attack_triggers(state, mon_joueur)
    off_hp_apres = hp_off(state)
    off_foot_apres = footprint_off(state)
    off_draws = int(getattr(rng_off, "call_count", 0) or 0)

    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dec3 = decision(sid, rid)
    live_hp_apres = hp_live(sid, rid)
    rng_apres = rng_dump(sid, rid)

    return {
        "rid": rid, "caster": caster_id, "target": target_id, "from_here": from_here,
        "mon_joueur": mon_joueur, "joueur_cible": joueur_cible,
        "routed": res.get("routed"), "ported": (res.get("diag") or {}).get("ported"),
        "cast_error": cast_error, "off_cast": off_cast, "live_cast": live_cast,
        "off_hp0": off_hp0, "live_hp0": live_hp0,
        "off_ennemi": off_ennemi,
        "off_hp_ennemi": (off_hp_avant_ennemi, off_hp_apres_ennemi),
        "live_hp_ennemi": (live_hp0, live_hp_apres_ennemi),
        "live_foot_ennemi": footprint_live(dec2),
        "off_tir": off_tir,
        "off_hp": (off_hp_avant, off_hp_apres),
        "live_hp": (dict(live_hp_apres_ennemi), live_hp_apres),
        "off_foot": (off_foot_avant, off_foot_apres),
        "live_foot": (footprint_live(dec2), footprint_live(dec3)),
        "off_draws": off_draws,
        "live_draws": (int(rng_avant.get("callCount") or 0), int(rng_apres.get("callCount") or 0)),
        "rng_avant": (rng_avant.get("callCount"), rng_avant.get("mti")),
        "rng_apres": (rng_apres.get("callCount"), rng_apres.get("mti")),
    }


def _hp_delta(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


def main() -> int:
    sid = _session()
    print("[build] board=%s" % BOARD)
    m, dispose = measure(sid)
    rc = 0
    try:
        cid, tid = m["caster"], m["target"]
        print("[scenario] caster=u%d (joueur %s) target=u%d (joueur %s) ; fromHere=%s"
              % (cid, m["mon_joueur"], tid, m["joueur_cible"], m["from_here"]))

        print("\n[1] CAST -- port == natif (garde de non-regression #491)")
        print("    routed=%s ported=%s cast_error=%s" % (m["routed"], m["ported"], m["cast_error"]))
        print("    port  = %s" % m["off_cast"])
        print("    natif = %s" % m["live_cast"])
        attendu = {cid: {SEEKER_AIMING}, tid: {MARKERLIGHT, SEEKER_TARGET}}
        ok1 = (m["off_cast"] == m["live_cast"]
               and {k: set(v) for k, v in m["off_cast"].items()} == attendu
               and m["ported"] is True and not m["cast_error"])
        print("    -> %s" % ("OK" if ok1 else "ECHEC"))
        rc |= 0 if ok1 else 1

        print("\n[2] TOUR ENNEMI -- TEMOIN NEGATIF (le missile NE part PAS)")
        d_off = _hp_delta(*m["off_hp_ennemi"])
        d_live = _hp_delta(*m["live_hp_ennemi"])
        print("    port  : declenches=%s  HP changes=%s" % (m["off_ennemi"] or "AUCUN",
                                                            d_off or "AUCUN"))
        print("    natif : HP changes=%s" % (d_live or "AUCUN"))
        print("    natif : 1123 encore sur la cible ? %s"
              % (SEEKER_TARGET in (m["live_foot_ennemi"].get(tid) or {})))
        ok2 = (not m["off_ennemi"] and not d_off and not d_live
               and SEEKER_TARGET in (m["live_foot_ennemi"].get(tid) or {}))
        print("    -> %s" % ("OK" if ok2 else "ECHEC"))
        rc |= 0 if ok2 else 1

        print("\n[3] TOUR DU CASTER -- LE MISSILE PART")
        d_off = _hp_delta(*m["off_hp"])
        d_live = _hp_delta(*m["live_hp"])
        print("    port  : declenches=%s" % json.dumps(m["off_tir"])[:600])
        print("    port  : HP %s" % (d_off or "AUCUN"))
        print("    natif : HP %s" % (d_live or "AUCUN"))
        dmg_off = {k: v[0] - v[1] for k, v in d_off.items()}
        dmg_live = {k: v[0] - v[1] for k, v in d_live.items()}
        ok3 = bool(dmg_live) and dmg_off == dmg_live
        print("    degat port=%s  natif=%s  -> %s"
              % (dmg_off, dmg_live, "ACCORD" if ok3 else "DIVERGENCE"))
        if not dmg_live:
            print("    (REGIME DEGENERE : le natif n'a rien inflige -- un accord ne prouverait rien)")
        rc |= 0 if ok3 else 1

        print("\n[4] EFFETS RETIRES")
        off_a, off_b = m["off_foot"]
        live_a, live_b = m["live_foot"]
        off_perdus = {SEEKER_TARGET: (SEEKER_TARGET in (off_a.get(tid) or {})
                                      and SEEKER_TARGET not in (off_b.get(tid) or {})),
                      SEEKER_AIMING: (SEEKER_AIMING in (off_a.get(cid) or {})
                                      and SEEKER_AIMING not in (off_b.get(cid) or {}))}
        live_perdus = {SEEKER_TARGET: (SEEKER_TARGET in (live_a.get(tid) or {})
                                       and SEEKER_TARGET not in (live_b.get(tid) or {})),
                       SEEKER_AIMING: (SEEKER_AIMING in (live_a.get(cid) or {})
                                       and SEEKER_AIMING not in (live_b.get(cid) or {}))}
        print("    port  : %s" % off_perdus)
        print("    natif : %s" % live_perdus)
        ok4 = off_perdus == live_perdus == {SEEKER_TARGET: True, SEEKER_AIMING: True}
        print("    -> %s" % ("OK" if ok4 else "ECHEC"))
        rc |= 0 if ok4 else 1

        print("\n[5] TIRAGES CONSOMMES (MT cale sur le live avant le pas)")
        live_draws = m["live_draws"][1] - m["live_draws"][0]
        print("    port=%d  natif=%d   (rng live %s -> %s)"
              % (m["off_draws"], live_draws, m["rng_avant"], m["rng_apres"]))
        ok5 = m["off_draws"] == live_draws and live_draws > 0
        print("    -> %s" % ("ACCORD" if ok5 else "DIVERGENCE"))
        rc |= 0 if ok5 else 1

        print("\nPROBE %s" % ("OK" if rc == 0 else "ECHEC"))
        return rc
    finally:
        dispose()


if __name__ == "__main__":
    sys.exit(main())
