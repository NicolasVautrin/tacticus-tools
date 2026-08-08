"""CONFRONT LIVE de `1101 AttemptedPossession` (`thousSorcerer` << Thaumachus >>, Thousand Sons).

LE POINT QUE CE PROBE EXISTE POUR TRANCHER, ET COMMENT.

Le decompile dit que `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$
ApplyInternal` appelle `IOperationProcessor slot 127 = ChangeUnitOwner(target, bondedEntity)`.
C'est un OWNER-SWAP -- l'exact contraire de `1164 MindControl`, ou la meme hypothese est REFUTEE.
Mais un swap POSE ET RETIRE DANS LE MEME CAST est invisible d'une simple lecture de `team`
avant/apres : les deux valent la meme chose.

**L'OBSERVABLE EST AILLEURS, ET IL EST BINAIRE : QUI LA CIBLE FRAPPE-T-ELLE ?** L'arbre pose le
bond AVANT le `PerformAIAbility`, donc au moment ou l'unite possedee choisit sa cible, ses
<< ennemis >> sont ceux de son NOUVEAU proprietaire -- c'est-a-dire SES PROPRES ANCIENS ALLIES.

  * owner-swap REEL   -> la cible frappe une unite de SON camp d'origine (l'equipe adverse) ;
  * owner-swap ABSENT -> elle frapperait le camp du CASTER (le notre), ou ne frapperait rien.

Les deux issues sont distinguables sans ambiguite par les PV, et AUCUNE geometrie de spawn ne les
confond. C'est le montage de l'etage [3].

MONTAGE (positions FORCEES par `--place`/`--a-place` -- << bloque par la geometrie >> n'est pas un
resultat) : le sorcier a portee 2 de la cible ; la cible ADJACENTE a un camarade (sa proie apres le
swap) et NON adjacente a nos unites. Sans ce forcage, la cible pourrait n'avoir aucune proie
adjacente et l'etage [3] serait degenere.

Les autres etages :
  [1] REGISTRE + MASQUE -- l'ability est-elle castable, et le gate de cible mord-il des DEUX cotes ?
  [2] EMPREINTE D'EFFETS -- que voit-on APRES le cast ? Le port et le natif doivent s'accorder, et
      l'accord attendu est un ENSEMBLE VIDE : les deux effets sont retires en queue d'arbre. C'est
      un accord en REGIME DEGENERE, donc il ne PROUVE rien seul -- il n'est la que pour interdire
      qu'un effet RESTE colle (un `RemoveEffect` perdu).
  [3] L'OWNER-SWAP PAR SON OBSERVABLE (cf. ci-dessus).
  [4] LE MT19937 -- un cast qui fait FRAPPER consomme des tirages. Contrairement a 1164 (ou le MT
      fige PROUVE que le canal degat est hors du behaviour), ici le MT DOIT bouger : un MT fige
      prouverait que le `PerformAIAbility` n'a rien fait.
  [5] LA REGLE DYNAMIQUE -- `GetDynamicInvalidTargetReason` est NEUVE (1101 n'etait dans aucune des
      deux tables : le port rendait `0` = permissif). Confrontee sur une cible SANS summon et SANS
      proie -- le seul regime ou le natif refuse.
  [6] LA FACE DECISION -- un accord COMBAT ne dit RIEN de la DECISION.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_590_attempted_possession.py [--state-name <nom>]
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

ABILITY = 1101                 # ActiveAbilityType.AttemptedPossession          (0x44d)
POSSESSED = 1209               # EffectType.AttemptedPossession_Possessed       (0x4b9)
DMG_OVERRIDE = 1210            # EffectType.AttemptedPossession_DmgOverride     (0x4ba)
NORMAL_ATTACK = 69             # ActiveAbilityType.Loki_NormalAttack
BOARD = "MC1_67"

CASTER_ID = "thousSorcerer"    # Thaumachus -- le SEUL porteur de 1101 (voie `active` du kit)
ALLY_ID = "thousInfernalMaster"
TARGET_ID = "orksNob"          # la cible du cast
PREY_ID = "orksRuntherd"       # SA proie apres le swap : adjacente a la cible, MEME camp qu'elle
LONE_ID = "orksWarboss"        # temoin de l'etage [5] : sans summon et SANS proie adjacente

#: GEOMETRIE FORCEE. Voisins de la cible `(3,4)` dans l'ordre d'adjacence stocke du board :
#: (2,3) (2,4) (3,3) (3,5) (4,3) (4,4). La proie est en `(4,4)` -- adjacente a la CIBLE et a
#: DISTANCE 2 du caster (donc pas adjacente a nous). Le caster est en `(3,2)` : distance 2 de la
#: cible (a portee de 1101, `range = 2`) mais PAS adjacent -- sinon nos unites seraient elles-memes
#: les << ennemis les plus proches >> de la cible possedee et l'etage [3] ne distinguerait rien.
POS_CASTER = "3,2"
POS_ALLY = "2,2"
POS_TARGET = "3,4"
POS_PREY = "4,4"
#: Temoin ISOLE de l'etage [5] : a portee 2 du caster, mais AUCUN voisin occupe -- ni par les
#: siens (pas de proie) ni par les notres. Le natif doit y refuser le cast (`tous.Count < 1 &&
#: GetPreferredAttackTarget == null`).
POS_LONE = "5,2"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12 / #486-r15).
#: PERIMETRE LARGE, et c'est une MESURE : la fermeture d'import d'un probe d'ability atteint la
#: quasi-totalite de `scripts/python`. Declarer etroit produirait un FAUX VERT.
#: Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py` ne
#: voit PAS `scripts/python/board.py`.
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1101 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + AddBondEffect/AddStatOverrideEffect/RemoveEffect + "
              "PerformAIAbility + les selecteurs ChildrenOf/Alive/UnitsWithoutTrait/SelectIf + les "
              "Operations ChangeUnitOwner/ResetUnitOwner + l'effet 1209 + le registre + le masque "
              "+ la regle dynamique + le playbook) ET du build charge -- l'oracle etant le jeu "
              "lui-meme, pas une constante ecrite ici.",
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
        print((proc.stderr or proc.stdout or "")[-2000:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


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


def find(dec, visual_id):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)


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


def team_live(sid, rid) -> dict:
    """`OwnerComponent.Team` par unite -- lu du natif. C'est la lecture directe du swap ; elle
    vaut la MEME chose avant et apres (le swap est transitoire), et c'est justement pour ca que
    l'etage [3] ne s'y fie pas : elle sert a PROUVER que le net est nul, pas que rien n'a eu lieu."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u.get("teamId", -1)) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def team_off(state) -> dict:
    from engine.runner.components import OwnerComponent
    return {int(eid): int(e.get_component(OwnerComponent).team)
            for eid, e in state.entities.items()
            if e.get_component(OwnerComponent) is not None}


def rng_dump(sid, rid):
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def rng_key(d):
    return (d.get("callCount"), d.get("mti"), hash(tuple(d.get("mt") or ())))


def seed_offline_rng(state, dump):
    """CALE le MT offline sur le MT LIVE : sans ce calage `state.rng is None` et le port rendrait
    un resultat de REPLI defensif au lieu d'un resultat MESURE."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def reason_live(sid, rid, caster_id, target_id, ability):
    """Le code de refus NATIF pour la paire (caster, cible) -- `IdunBattle.Operations.
    ActiveAbilityOperation$$IsInvalidTarget`, expose par le RPC `abilityReason`. `0` = accepte.

    ⚠ **PAS `abilityTargets`**, et la difference n'est pas cosmetique : cette voie-la rend la LISTE
    des cibles proposees, qui peut etre vide pour une ability dont le gate est dynamique sans que
    le cast soit refuse -- mesure du premier jet de ce probe, ou elle rendait `1` sur une cible que
    le natif ACCEPTAIT (le cast a bien retire 7006 PV). Un oracle qui repond a une AUTRE question
    que celle posee ne mesure pas le gate."""
    r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster_id),
                                   "abilityType": int(ability), "targetId": int(target_id)},
            60) or {}
    return int((r.get("targetReason") or {}).get("hex", "0x0"), 16)


def mesurer(seed: str = "777", board: str = BOARD,
            state_name: str = "probe_590_attempted_possession"):
    """Monte le scenario, joue le cast des DEUX cotes, rend `(mesures, dispose)`.

    Le TEST de garde appelle CETTE fonction : une seule implementation du montage et des lectures,
    donc aucune divergence possible entre ce qui est MESURE ici et ce qui est GARDE la-bas."""
    sid = _session()
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "%s,%s" % (CASTER_ID, ALLY_ID),
        "--a-units", "%s,%s,%s" % (TARGET_ID, PREY_ID, LONE_ID),
        "--place", "%s:%s" % (CASTER_ID, POS_CASTER),
        "--place", "%s:%s" % (ALLY_ID, POS_ALLY),
        "--a-place", "%s:%s" % (TARGET_ID, POS_TARGET),
        "--a-place", "%s:%s" % (PREY_ID, POS_PREY),
        "--a-place", "%s:%s" % (LONE_ID, POS_LONE)])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    dec0 = decision(sid, rid)
    caster = find(dec0, CASTER_ID)
    cible = find(dec0, TARGET_ID)
    proie = find(dec0, PREY_ID)
    seul = find(dec0, LONE_ID)
    manquants = [n for n, u in ((CASTER_ID, caster), (TARGET_ID, cible),
                                (PREY_ID, proie), (LONE_ID, seul)) if u is None]
    if manquants:
        raise SystemExit("montage INCOMPLET, unites absentes : %s" % ",".join(manquants))
    caster_id, cible_id = int(caster["id"]), int(cible["id"])
    proie_id, seul_id = int(proie["id"]), int(seul["id"])

    st0, _ = load(sid, rid)
    rng0 = rng_dump(sid, rid)
    seed_offline_rng(st0, rng0)

    # -- [1] REGISTRE + MASQUE, des DEUX cotes -------------------------------------------------
    porte = ABILITY in ABILITY_CLASSES
    # `get_invalid_target_reason` attend une INSTANCE (il invoque la methode d'instance
    # `get_dynamic_invalid_target_reason`), pas la classe du registre.
    cls = ABILITY_CLASSES.get(ABILITY)
    cls = cls() if cls is not None else None
    masque = int(type(cls).TARGETING_OPTIONS.rules) if cls is not None else None
    # cible LEGALE (ennemie, a portee, avec une proie) vs ALLIE (doit etre refuse par TargetIsEnemy)
    allie = find(dec0, ALLY_ID)
    gate_port_ok = get_invalid_target_reason(st0, caster_id, cible_id, cls) if cls else None
    gate_port_allie = (get_invalid_target_reason(st0, caster_id, int(allie["id"]), cls)
                       if (cls is not None and allie is not None) else None)
    gate_live_ok = reason_live(sid, rid, caster_id, cible_id, ABILITY)
    gate_live_allie = (reason_live(sid, rid, caster_id, int(allie["id"]), ABILITY)
                       if allie is not None else None)

    # -- [5] REGLE DYNAMIQUE sur le temoin ISOLE ------------------------------------------------
    gate_port_seul = get_invalid_target_reason(st0, caster_id, seul_id, cls) if cls else None
    gate_live_seul = reason_live(sid, rid, caster_id, seul_id, ABILITY)

    # -- DIAGNOSTIC PAR ETAGE de `GetPreferredAttackTarget` ------------------------------------
    # On ne fitte JAMAIS un scalaire : quand le gate diverge, on mesure ENTREE/SORTIE de chaque
    # etage du corps natif (`b__0`) jusqu'au PREMIER ou natif != port.
    import engine.runner.abilities.loki.attempted_possession as AP
    from engine.runner.abilities.targeting import valid_normal_attack_targets
    etages = {}
    for nom, uid in (("cible", cible_id), ("seul", seul_id)):
        cands = [int(t) for t in (valid_normal_attack_targets(st0, uid) or [])]
        l1 = [t for t in cands if not AP._has_trait(st0, t, 13)]        # b__5_1 : !Object
        l2 = [t for t in l1 if not AP._has_effect(st0, t, POSSESSED)]   # b__2  : !possede
        etages[nom] = {
            "uid": uid,
            "enfants": AP.AttemptedPossessionAbility._children_of(st0, uid),
            "GetValidTargets": cands, "apres_b__5_1": l1, "apres_b__2": l2,
            "chosen": (l2 if l2 else l1),
            "nearest": AP._nearest_of(st0, uid, (l2 if l2 else l1)),
            "preferred": AP.attempted_possession_preferred_target(st0, caster_id, uid),
        }
        # L'ORACLE de l'etage 1 : ce que le NATIF rend pour la meme question.
        r = rpc(sid, "abilityTargets",
                {"runnerId": rid, "unitId": int(uid), "abilityType": NORMAL_ATTACK}, 60) or {}
        etages[nom]["GetValidTargets_natif"] = sorted(
            {int(t.get("id")) for t in (r.get("targets") or []) if t.get("id") is not None})

    # -- DIAGNOSTIC de l'etage IA (le foyer PARTAGE `perform_ai_ability_unit_behaviour`) --------
    # Quand le port pose bien la contrainte de cible mais ne frappe pas, l'ecart est SOUS l'arbre :
    # on mesure alors les deux entrees de ce foyer, sous simulation du swap comme le natif.
    from engine.runner.operations.change_unit_owner import (ChangeUnitOwnerOperation,
                                                            ResetUnitOwnerOperation)
    from engine.runner.operations.summon_ai import ai_control_execute_ability_action_for
    from engine.runner.operations.triggers.base import _in_attack_range
    import copy
    stx = copy.deepcopy(st0)
    pref = AP.attempted_possession_preferred_target(stx, caster_id, cible_id)
    ChangeUnitOwnerOperation.execute(stx, cible_id, caster_id)
    etage_ia = {
        "preferred": pref,
        "in_attack_range": (_in_attack_range(stx, cible_id, pref) if pref is not None else None),
        "action_ia": ai_control_execute_ability_action_for(
            stx, cible_id, 17, allow_only_move=False, move_amount=0,
            range_gate=lambda t, tile: (t is not None and int(
                t.get("id", -1) if isinstance(t, dict) else t) == int(pref or -1))),
    }
    vus = []
    def _gate_reel(t, tile):
        ok = _in_attack_range(stx, cible_id, t, from_pos=tile)
        vus.append((repr(t)[:40], repr(tile)[:20], bool(ok)))
        return ok and (int(t.get("id", -1) if isinstance(t, dict) else t) == int(pref or -1))
    etage_ia["action_ia_gate_reel"] = ai_control_execute_ability_action_for(
        stx, cible_id, 17, allow_only_move=False, move_amount=0, range_gate=_gate_reel)
    etage_ia["gate_vus"] = vus[:8]
    from engine.runner.abilities.loki.summon import perform_ai_ability_unit_behaviour as _P
    try:
        etage_ia["corps_direct"] = _P(stx, cible_id, False, 0, allowed_targets={int(pref)})
    except Exception as _e:
        etage_ia["corps_direct"] = "EXC:%s:%s" % (type(_e).__name__, _e)
    ResetUnitOwnerOperation.execute(stx, cible_id)

    # -- ETAT AVANT ------------------------------------------------------------------------------
    emp_live_avant = footprint_live(dec0)
    hp_live_avant = hp_live(sid, rid)
    team_live_avant = team_live(sid, rid)
    rng_avant = rng_key(rng0)

    # -- CAST NATIF ------------------------------------------------------------------------------
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": ABILITY,
        "targetId": cible_id}}, 120) or {}
    dec1 = decision(sid, rid)
    emp_live_apres = footprint_live(dec1)
    hp_live_apres = hp_live(sid, rid)
    team_live_apres = team_live(sid, rid)
    rng_apres = rng_key(rng_dump(sid, rid))

    # -- CAST PORT (sur l'etat AVANT, recharge proprement) ---------------------------------------
    st1, _ = load_avant(sid, rid, st0)
    hp_off_avant = hp_off(st1)
    team_off_avant = team_off(st1)
    emp_off_avant = footprint_off(st1)
    # `_apply_active_ability(state, uid, TARGET, ABILITY)` -- l'ordre des deux derniers arguments
    # est (cible, ability). L'inverser rend un `{"routed": "noop"}` SILENCIEUX : le premier jet de
    # ce probe l'a mesure, et un port muet aurait pu passer pour un port faux.
    ret = _apply_active_ability(st1, caster_id, cible_id, ABILITY)
    from engine.runner.components import StatsComponent as _SC
    _e81 = st1.get_entity(cible_id)
    _sc = _e81.get_component(_SC) if _e81 is not None else None
    etage_ia["atk_apres_override"] = (getattr(_sc.ctx, "stats", None).get_stat(0, 0)
                                      if (_sc is not None and getattr(_sc.ctx, "stats", None)) else None)
    emp_off_apres = footprint_off(st1)
    hp_off_apres = hp_off(st1)
    team_off_apres = team_off(st1)

    return {
        "ids": {"caster": caster_id, "cible": cible_id, "proie": proie_id, "seul": seul_id,
                "allie": int(allie["id"]) if allie is not None else None},
        "registre": {"porte": porte, "masque": masque},
        "gate": {"port_ok": gate_port_ok, "port_allie": gate_port_allie,
                 "port_seul": gate_port_seul, "live_ok": gate_live_ok,
                 "live_allie": gate_live_allie, "live_seul": gate_live_seul},
        "effets": {"live": delta(emp_live_avant, emp_live_apres),
                   "port": delta(emp_off_avant, emp_off_apres)},
        "hp": {"live_avant": hp_live_avant, "live_apres": hp_live_apres,
               "port_avant": hp_off_avant, "port_apres": hp_off_apres},
        "team": {"live_avant": team_live_avant, "live_apres": team_live_apres,
                 "port_avant": team_off_avant, "port_apres": team_off_apres},
        "rng": {"avant": rng_avant, "apres": rng_apres, "bouge": rng_avant != rng_apres},
        "retour_port": ret,
        "etages": etages,
        "etage_ia": etage_ia,
        "act": act,
    }


def load_avant(sid, rid, st0):
    """Le port rejoue sur une COPIE de l'etat d'AVANT le cast natif -- le runner, lui, a deja
    avance. On repart du `State` deja charge (`st0`), qui EST cet etat."""
    import copy
    st = copy.deepcopy(st0)
    return st, None


def _pertes(avant: dict, apres: dict) -> dict:
    return {int(k): int(avant[k]) - int(v) for k, v in apres.items()
            if k in avant and int(avant[k]) > int(v)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-name", default="probe_590_attempted_possession")
    a = ap.parse_args()
    m, dispose = mesurer(state_name=a.state_name)
    try:
        ids = m["ids"]
        print("=" * 88)
        print("[590] 1101 AttemptedPossession -- confront LIVE (thousSorcerer)")
        print("=" * 88)
        print("ids : caster=%(caster)s cible=%(cible)s proie=%(proie)s seul=%(seul)s "
              "allie=%(allie)s" % ids)

        print("\n[1] REGISTRE + MASQUE")
        print("  portee au registre : %s ; masque = %s"
              % (m["registre"]["porte"],
                 hex(m["registre"]["masque"]) if m["registre"]["masque"] is not None else None))
        g = m["gate"]
        print("  gate cible LEGALE   port=%s live=%s" % (g["port_ok"], g["live_ok"]))
        print("  gate sur un ALLIE   port=%s live=%s  (TargetIsEnemy doit REFUSER)"
              % (g["port_allie"], g["live_allie"]))

        print("\n[5] REGLE DYNAMIQUE -- cible sans summon ET sans proie adjacente")
        print("  gate temoin ISOLE   port=%s live=%s" % (g["port_seul"], g["live_seul"]))

        print("\n[2] EMPREINTE D'EFFETS (delta du cast) -- accord attendu = VIDE des deux cotes")
        print("  live : %s" % (m["effets"]["live"] or {}))
        print("  port : %s" % (m["effets"]["port"] or {}))

        print("\n[3] L'OWNER-SWAP PAR SON OBSERVABLE -- QUI la cible frappe-t-elle ?")
        pl = _pertes(m["hp"]["live_avant"], m["hp"]["live_apres"])
        po = _pertes(m["hp"]["port_avant"], m["hp"]["port_apres"])
        print("  pertes de PV live : %s" % (pl or {}))
        print("  pertes de PV port : %s" % (po or {}))
        print("  proie (camp de la CIBLE) touchee : live=%s port=%s"
              % (ids["proie"] in pl, ids["proie"] in po))
        print("  NOTRE camp touche                : live=%s port=%s"
              % (bool({ids["caster"], ids["allie"]} & set(pl)),
                 bool({ids["caster"], ids["allie"]} & set(po))))
        tl_a, tl_b = m["team"]["live_avant"], m["team"]["live_apres"]
        print("  team de la cible live : %s -> %s  (NET NUL attendu : le swap est transitoire)"
              % (tl_a.get(ids["cible"]), tl_b.get(ids["cible"])))
        to_a, to_b = m["team"]["port_avant"], m["team"]["port_apres"]
        print("  team de la cible port : %s -> %s" % (to_a.get(ids["cible"]),
                                                      to_b.get(ids["cible"])))

        print("\n[4] MT19937 -- le cast fait FRAPPER, donc il DOIT consommer des tirages")
        print("  MT bouge : %s" % m["rng"]["bouge"])

        print("\n[6] FACE DECISION")
        from engine.playbook.noncomparable import PLAYBOOKS
        print("  playbook 1101 inscrit : %s" % (ABILITY in PLAYBOOKS))
        print("\n[D] DECOMPOSITION PAR ETAGE de GetPreferredAttackTarget")
        for nom, e in m["etages"].items():
            print("  %s (uid=%s) : enfants=%s" % (nom, e["uid"], e["enfants"]))
            print("      GetValidTargets  port=%s  NATIF=%s"
                  % (e["GetValidTargets"], e["GetValidTargets_natif"]))
            print("      apres b__5_1=%s  apres b__2=%s  chosen=%s  nearest=%s  preferred=%s"
                  % (e["apres_b__5_1"], e["apres_b__2"], e["chosen"], e["nearest"],
                     e["preferred"]))
        print("  [IA] %s" % json.dumps({k: v for k, v in m["etage_ia"].items() if k in ("preferred","corps_direct","atk_apres_override")}, default=str)[:900])
        print("\nretour du port : %s" % json.dumps(m["retour_port"], default=str)[:400])
        print("=" * 88)
        return 0
    finally:
        dispose()


if __name__ == "__main__":
    sys.exit(main())












