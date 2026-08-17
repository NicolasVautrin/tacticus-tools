"""#889-r7 -- la PHASE 2 de `1215 InstrumentsOfVengeance` confrontee au NATIF.

CE QUE CE PROBE DISCRIMINE, et ce qu'il ne discrimine pas -- a lire AVANT ses verts :

  * [A] LE CAST (phase 1) sert de PREMISSE, pas d'observable : il est deja confronte par
    `probe_889r6_instruments_of_vengeance.py` (ensembles de tuiles IDENTIQUES sur DEUX regimes). On
    le rejoue ici seulement pour armer la phase 2 des deux cotes.
  * [B] LE COUP DIFFERE. Au DEBUT DU TOUR SUIVANT du Lion, le `Triggered()` d'
    `IdunBattle.Entities.Effects.APendingAttackEffect` fire `TriggerAbility(1519)` et
    `...InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` relit les QUATRE cles persistantes,
    frappe les occupants ENNEMIS des deux lignes, retire les marques `1518` et vide les cles.
    Observables : le DELTA DE PV par unite, et la DISPARITION des marques.
  * [C] LE SPAWN. Le meme arbre pose `nrOfSummons` `darkaSmnTerminator` sur des tuiles libres, avec
    un on-appearance `PerformAIAttackFromCurrentPosition`. Observable : le nombre d'unites de
    l'equipe du Lion, avant et apres.

  NON DISCRIMINE, et il faut le dire :
  * l'ORDRE des trois viviers de tuiles de spawn (`(t2 + t1) + t3`) n'est pas separable ici : les
    trois sont `Randomize`, donc deux implementations qui tirent dans un ordre different peuvent
    rendre le meme ENSEMBLE de tuiles. Le probe compare le CARDINAL et l'appartenance au vivier,
    pas la tuile exacte ;
  * le `Inform(0xc1)` est un hint AI/UI, NO-OP des deux cotes -- rien ne l'observe ;
  * la branche `On(0x25 = UnitRemoved)` n'existe PAS pour cet effet (lecture : la table de symboles
    ne publie aucun `$$CreateHandleTriggerAbilitiesInternal` pour
    `...InstrumentsOfVengeance_PendingAttackEffect`, alors qu'elle publie celui de son homologue
    `TheLionsWrath` -- le temoin est present).

MONTAGE. `--board CE6_boss` (SA carte), boss au palier `:4`, DEUX ennemis places au contact pour que
les lignes portent des occupants. Le Lion est SEUL dans son camp : son cast TERMINE donc le tour,
et UN SEUL `endturn` suffit a rouvrir son tour -- c'est la que la phase 2 part. Les pas sont
APPARIES sur `decisionView.currentPlayer`, jamais sur le NOM qu'on donne au pas (#889-r4), et le
RNG offline est re-seede AVANT chaque bascule (sinon le port tire depuis un etat que le natif a
deja consomme).
⚠ `TACTICUS_ALLOW_ROSTER_DEFICIT=1` est POSE PAR CE PROBE : le jeu publie le boss sous l'id
d'entite REMAPPE `GuildBoss12Boss1DarkaLion`, faux negatif connu du garde de roster.

ASCII only. SORTIES -> logs/, jamais data/ (#349).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

IOV = 1215                      # ActiveAbilityType.InstrumentsOfVengeance
IOV_LOCATION_TARGET = 1518      # EffectType.InstrumentsOfVengeance_LocationTarget
IOV_PENDING_ATTACK = 1519       # EffectType.InstrumentsOfVengeance_PendingAttack
BOARD = "CE6_boss"
BOSS = "darkaBossLion:4"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/operations/triggers/loki/"
                "instruments_of_vengeance_attack.py",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py",
                "scripts/python/engine/runner/abilities/behaviours/summon.py",
                "scripts/python/engine/entities/selectors/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la PHASE 2 de 1215 -- le coup differe des deux lignes, le "
              "retrait des marques 1518 et le volet SPAWN de "
              "`InstrumentsOfVengeance_AttackAbility$$CreateBehaviour`.",
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
    env = dict(os.environ)
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind(sid: int):
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
    abst = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles, ability_states=abst), dec


def seed_offline_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def unites_live(sid, rid) -> dict:
    """`{squadId: (team, visualId)}` -- ce qui rend le SPAWN observable."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): (u.get("team"), u.get("visualId") or u.get("unitId"))
            for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def unites_off(state) -> set:
    return {int(eid) for eid in state.entities}


def marques_off(state) -> dict:
    """`{cle: [effect_type, ...]}` des instances NON consommees -- pour voir le retrait du 1518."""
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        v = sorted(int(e.effect_type) for e in effs if not e.consumed)
        if v:
            out[int(key)] = v
    return out


def _dhp(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


# ---------------------------------------------------------------- LA FIXTURE, nommee et reutilisable

def monter_scenario(sid: int, *, seed: str = "777", board: str = BOARD,
                    hp_target: str | None = "400000", tag: str = "x"):
    """Monte le duel du Lion sur SA carte, DEUX ennemis au contact.

    `hp_target` gonfle les PV de la cible : sans lui les coups de la phase 1 puis de la phase 2
    tuent, et les deltas des DEUX phases se confondent en un seul kill non comparable."""
    state_path = LOGS / ("probe_889r7_%s.json" % tag)
    args = ["--seed", seed, "--board", board,
            "--explicit-stats", BOSS, "--p-units", BOSS,
            "--a-units", "custoVexilusPraetor,orksBigMek",
            "--place", "%s:3,3" % BOSS,
            "--a-place", "custoVexilusPraetor:3,4", "--a-place", "orksBigMek:2,2"]
    if hp_target:
        args += ["--hp-target", str(hp_target)]
    rid = build(state_path, args)

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)   # MES runners, jamais ceux des autres

    return rid, dispose


def _mesure(sid: int, rid: int) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind(sid)
    state, dec0 = load(sid, rid)
    caster = next((u for u in (dec0.get("units") or [])
                   if "DarkaLion" in str(u.get("visualId") or "")), None)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : le Lion est absent du decisionView")
    caster_id = int(caster["id"])
    mon_joueur = dec0.get("currentPlayer")

    # ---- [A] LE CAST, des DEUX cotes (premisse, pas observable) ----------------------------
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    diag_cast = ABILITY_CLASSES[IOV]().execute_behaviour(state, caster_id, caster_id) or {}
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": IOV,
        "targetId": caster_id}}, 120) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours = {"apres_cast": dec1.get("currentPlayer")}

    marques_apres_cast = marques_off(state)
    hp_l0, hp_o0 = hp_live(sid, rid), hp_off(state)
    unites_l0, unites_o0 = unites_live(sid, rid), unites_off(state)

    # ---- [B]/[C] LA BASCULE : le natif rouvre le tour du Lion -------------------------------
    # ⚠ Le RNG se re-seede AVANT la bascule (#889-r4) : sinon le port tire ses rolls depuis un etat
    # que le natif a deja consomme et les deux montants ne sont plus comparables.
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    act2 = rpc(sid, "applyAction",
               {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 120) or {}
    dec2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours["apres_endturn_1"] = dec2.get("currentPlayer")
    # Le port joue la MEME bascule, pour le MEME joueur que celui a qui le natif vient de donner la
    # main -- lu APRES la bascule, jamais devine d'apres le nom du pas.
    off_phase2 = delayed_attack_triggers(state, dec2.get("currentPlayer"))

    hp_l1, hp_o1 = hp_live(sid, rid), hp_off(state)
    unites_l1, unites_o1 = unites_live(sid, rid), unites_off(state)

    return {
        "rid": rid, "caster": caster_id, "mon_joueur": mon_joueur, "tours": tours,
        "cast_error": cast_error,
        "cast_port": {k: diag_cast.get(k) for k in ("marked", "armed", "activated", "persisted")},
        "marques_apres_cast": marques_apres_cast,
        "off_phase2": off_phase2,
        "dhp_natif": _dhp(hp_l0, hp_l1),
        "dhp_port": _dhp(hp_o0, hp_o1),
        "spawn_natif": {str(k): v for k, v in unites_l1.items() if k not in unites_l0},
        "spawn_port": sorted(unites_o1 - unites_o0),
        "marques_apres_phase2": marques_off(state),
        "events_bascule": len(act2.get("actions") or []),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--hp-target", default="400000")
    ap.add_argument("--tag", default=str(os.getpid()))
    a = ap.parse_args()

    sid = _session()
    rid, dispose = monter_scenario(sid, seed=a.seed, board=a.board,
                                   hp_target=a.hp_target, tag=a.tag)
    try:
        m = _mesure(sid, rid)
    finally:
        dispose()

    print("[889r7] runner=%s caster=%s err=%s" % (m["rid"], m["caster"], m["cast_error"]))
    print("[889r7] currentPlayer par pas : %s (mon_joueur=%s)" % (m["tours"], m["mon_joueur"]))
    if m["tours"].get("apres_cast") == m["mon_joueur"]:
        print("        -> ATTENTION : le cast n'a PAS bascule le tour. Un seul endturn ne suffit "
              "alors pas a rouvrir le tour du Lion : la phase 2 n'est PAS exercee.")
    print("[889r7] [A] cast port : marked=%s armed=%s activated=%s persisted=%s"
          % (len(m["cast_port"].get("marked") or []), len(m["cast_port"].get("armed") or []),
             len(m["cast_port"].get("activated") or []),
             [p.get("key") for p in (m["cast_port"].get("persisted") or [])]))
    print("[889r7] [B] COUP DIFFERE")
    print("        natif dhp = %s" % json.dumps(m["dhp_natif"], sort_keys=True))
    print("        port  dhp = %s" % json.dumps(m["dhp_port"], sort_keys=True))
    print("        port  phase2 = %s" % json.dumps(m["off_phase2"], default=str)[:1200])
    print("[889r7] [C] SPAWN")
    print("        natif = %s" % json.dumps(m["spawn_natif"], sort_keys=True))
    print("        port  = %s" % m["spawn_port"])
    print("[889r7] MARQUES 1518 (port) : apres cast = %d cles, apres phase 2 = %d cles"
          % (sum(1 for v in m["marques_apres_cast"].values() if IOV_LOCATION_TARGET in v),
             sum(1 for v in m["marques_apres_phase2"].values() if IOV_LOCATION_TARGET in v)))

    out = LOGS / ("probe_889r7_instruments_phase2_%s.json" % a.tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")
    print("[889r7] -> %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
