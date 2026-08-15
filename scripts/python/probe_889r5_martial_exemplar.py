"""#889-r5 -- confrontation NATIF/PORT de `1216 MartialExemplar` (`darkaBossLion` « le Lion »).

CE QUE CE PROBE DISCRIMINE, et par quoi
=======================================
L'arbre de `1216` a **DEUX branches exclusives**, separees par
`AmountIsGreaterThanZero(<attaquables adjacents>)` -- le compte des ennemis attaquables ENCORE
adjacents APRES la frappe AoE et APRES son `KillDeadUnits`. Un probe qui ne jouerait qu'un seul
regime laisserait la moitie de l'arbre non confrontee, et c'est exactement la faute que #889 avait
evitee en REFUSANT de porter a moitie. Les deux regimes :

  * **THEN** -- la cible SURVIT aux 6 coups -> `UseNormalAttack(Owner, SortUnitsByDamageUtility(...))`
    -> le Lion enchaine une ATTAQUE NORMALE. Monte avec `--hp-target` eleve.
  * **ELSE** -- plus aucun attaquable adjacent -> `MoveUnit(ClosestPositionToTarget(...))` +
    `UseNormalAttackIfAble(Owner, <cible tiree>)`. Monte en laissant les PV nominaux : les 6 coups
    du Lion palier `:4` (dmg 2630) tuent.

TEMOINS, et ce que chacun NE voit PAS
-------------------------------------
  * `footprint` (effets par unite, `decisionView.units[].effects`) -- il VOIT la pose de `1520`
    sur le caster et sa duree. Il ne voit PAS le degat.
  * `hp` (`observeBattle.units[].hp`) -- il VOIT le degat TOTAL par unite. Il ne separe PAS les
    deux volets (AoE + attaque normale), et c'est justement ce que la colonne `DAMAGE(Power)` de
    l'audit ne dit pas non plus. Le `captureEvents` du cast, lui, SEPARE les coups.
  * `move` de la vue -- il VOIT si le porteur peut se deplacer. **MESURE du 2026-08-11 : le Lion
    est `moveNone` sur `CE6_boss`**, donc le `MoveUnit` de la branche ELSE est un NO-OP cote natif
    (`MovementQuery$$FindAnyOrAllMoveableTiles` sort VIDE sur `!CanMove(unit)`), et
    `UseNormalAttackIfAble` part quand meme. Ce probe le VERIFIE au lieu de le supposer : c'est le
    temoin du gate `CanMove` de `ClosestPositionToTarget`.
  * ⚠ CE QU'AUCUN TEMOIN D'ICI NE VOIT : le bonus de crit de `1520` ne mord que sur une cible
    portant `UnitTrait.Summon`, et aucun ennemi du montage n'en est un. L'effet est donc POSE et
    confronte dans sa STRUCTURE, jamais dans sa MAGNITUDE -- dit, pas tu.
  * **`effectsAll` (#231-r) -- LE TEMOIN QUI TRANCHE LE VOLET (b) DE `#889-r5-r3`.** Les deux
    temoins ci-dessus (`footprint`, `live_caster_effects`) partent tous deux de
    `decisionView.units[].effects`, donc d'`EffectsOwnedComponent.ActiveEffectIds` : un `1520`
    absent y est AMBIGU entre « le natif ne le pose pas » et « ce canal ne le publie pas ».
    `effectsAll` enumere les entites-effet du STATE, hors liste possedee, avec `inOwnerList` /
    `removed` / `source` / `targetIds` -- les trois regimes se lisent alors separement. Le residu
    `#889-r5-r3` exigeait « un capteur d'effets INDEPENDANT de `decisionView` » : il EXISTE et il
    est DEPLOYE, ce probe le CONSOMME (`--effects-all`, actif par defaut).
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

MARTIAL_EXEMPLAR = 1216         # ActiveAbilityType.MartialExemplar
ME_EXTRA_CRIT = 1520            # EffectType.MartialExemplar_ExtraCritChance
BOARD = "CE6_boss"              # LA carte du boss (gameconfig battles[].BoardId)
BOSS = "darkaBossLion:4"        # palier HAUT : le seul a porter un CritChance non nul

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/darkangels.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/combat.py",
                "scripts/python/engine/runner/abilities/behaviours/context.py",
                "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
                "scripts/python/engine/runner/abilities/behaviours/movement.py",
                "scripts/python/engine/runner/operations/damage.py",
                "scripts/python/engine/runner/operations/damage_utility.py",
                "scripts/python/engine/entities/selectors/pathing.py",
                "scripts/python/engine/entities/selectors/composites.py",
                "scripts/python/engine/entities/selectors/units.py",
                "scripts/python/engine/entities/effects/loki/martial_exemplar.py",
                "scripts/python/engine/entities/effects/factory.py",
                "scripts/python/engine/entities/distance_type.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF les DEUX branches exclusives de 1216 (attaque normale "
              "enchainee vs deplacement+attaque), les SEULS consommateurs portes des noeuds "
              "`Nearest`/`ClosestPositionToTarget`/`SortUnitsByDamageUtility`/`AttackableEnemies`/"
              "`UseNormalAttack(IfAble)`, et le gate `CanMove` que le porteur `moveNone` exerce.",
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
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind_transport(sid: int):
    """LIE le transport ambiant que `load_state` utilise pour tirer `unitAbilityStates` -- meme
    raison que pour `1217` : sans lui le kit DECLENCHE du caster est ampute."""
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


def pos_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        p = u.get("pos") or {}
        if p:
            out[int(u["id"])] = (p.get("col"), p.get("row"))
    return out


def pos_off(state) -> dict:
    from engine.runner.components import PositionComponent
    out = {}
    for eid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is not None:
            out[int(eid)] = (pc.col, pc.row)
    return out


def rng_dump(sid, rid) -> dict:
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def seed_offline_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def coups_natifs(act: dict) -> dict:
    """Les coups PAR CIBLE que le natif journalise dans les events du cast (`captureEvents`).
    C'est le SEUL temoin qui separe les deux volets de degat (AoE puis attaque normale) : les PV,
    eux, les somment. Cle = `Attacker_Id`/`Target_Id` -- **PAS** `Source_Id`, qui n'existe pas."""
    out: dict = {}
    for ev in (act.get("events") or []):
        tags = ev.get("tags") or {}
        tid = tags.get("Target_Id")
        dmg = tags.get("Damage") or tags.get("Damage_Amount")
        if tid is None or dmg is None:
            continue
        out.setdefault(int(tid), []).append(int(dmg))
    return out


def effects_all(sid, rid, effect_type: int | None = None) -> dict:
    """`effectsAll` (#231-r) -- TOUTES les entites-effet du state, `EffectsOwnedComponent` NON
    consulte. C'est le canal INDEPENDANT de `decisionView` que `#889-r5-r3` (b) reclamait.

    Les trois regimes se lisent au couple (`inOwnerList`, `removed`), cf. la docstring du hook :
      * l'entite n'apparait PAS         -> JAMAIS POSE (gate d'`AddEffectOperation`) ;
      * `inOwnerList=false, removed=1`  -> POSE PUIS RETIRE ;
      * `inOwnerList=false, removed=0`  -> ORPHELIN (vivant hors liste).
    Un `ok:false` est rendu TEL QUEL -- jamais rabattu sur « aucun effet », qui se lirait comme
    une mesure alors que c'est une non-mesure."""
    body = {"runnerId": rid, "includeRemoved": True}
    if effect_type is not None:
        body["effectType"] = int(effect_type)
    return rpc(sid, "effectsAll", body, 60) or {"ok": False, "error": "reponse vide"}


def _dhp(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


def measure(sid: int, regime: str, seed: str = "777", extra: list | None = None) -> tuple:
    """Monte UN regime et joue le MEME cast des deux cotes. `regime` = 'survit' | 'meurt'."""
    state_path = LOGS / ("probe_889r5_%s.json" % regime)
    args = ["--seed", seed, "--board", BOARD,
            "--explicit-stats", BOSS, "--p-units", BOSS,
            "--a-units", "custoVexilusPraetor,orksBigMek",
            # Le Lion est `moveNone` (MESURE, cf. l'en-tete) : on colle la CIBLE, jamais l'inverse.
            "--place", "%s:3,3" % BOSS,
            "--a-place", "custoVexilusPraetor:3,4", "--a-place", "orksBigMek:2,2"]
    if regime == "survit":
        # PV geants -> les 6 coups ne tuent pas -> `AmountIsGreaterThanZero` VRAI -> branche THEN.
        args += ["--hp-target", "400000"]
    elif regime == "vide":
        # PV MINIMAUX -> les 6 coups tuent TOUS les adjacents -> apres le `KillDeadUnits`,
        # `<attaquables adjacents>` est VIDE -> `AmountIsGreaterThanZero` FAUX -> branche ELSE
        # (`MoveUnit(ClosestPositionToTarget)` + `UseNormalAttackIfAble(<cible tiree>)`).
        # C'est le SEUL regime qui exerce `Nearest`/`ClosestPositionToTarget` et le gate `CanMove`.
        args += ["--hp-target", "1"]
    args += list(extra or [])
    rid = build(state_path, args)

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid, regime), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int, regime: str) -> dict:
    from engine.runner.operations.summon_ai import _apply_active_ability

    bind_transport(sid)
    dec0 = decision(sid, rid)
    caster = next((u for u in (dec0.get("units") or [])
                   if "DarkaLion" in str(u.get("visualId") or "")), None)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : le Lion est absent du decisionView")
    caster_id = int(caster["id"])
    # MOUVEMENT DU PORTEUR -- mesure, pas hypothese (le brief generalisait a tort `moveNone` a tous
    # les boss ; un autre montage a mesure `+move[2]` sur `deathBossMortarion`).
    move_live = caster.get("move")
    n_feet = len(caster.get("feet") or [])

    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": MARTIAL_EXEMPLAR}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == MARTIAL_EXEMPLAR), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1216 "
                             "(masque self-cast : la cible attendue est le CASTER lui-meme)")
    target_id = int(from_here[0])

    # ---- OFFLINE : le MEME cast, joue par le port -----------------------------------------
    state, _ = load(sid, rid)
    # SUBSTRAT du caster -- le temoin qui DISCRIMINE un ecart d'ARBRE d'un ecart de SEEDING.
    # `AttackDamageOperation.execute` rend `None` (donc « pas d'attaque normale ») sur DEUX causes
    # seulement : la cible est morte, ou l'attaquant/la cible n'a pas de `StatsComponent`/
    # `HealthComponent`. Sans ce releve, un `skipped=operation_refusee` ne dit pas laquelle.
    from engine.runner.components import StatsComponent as _SC
    _ce = state.get_entity(caster_id)
    _cs = _ce.get_component(_SC) if _ce is not None else None
    _cctx = getattr(_cs, "ctx", None)
    substrat = {"caster_a_stats": _cs is not None,
                "caster_armes": len(getattr(_cctx, "weapons", None) or []) if _cs is not None
                else None,
                "caster_ctx_attrs": sorted(a for a in dir(_cctx or object())
                                           if not a.startswith("_"))[:16]}
    seed_offline_rng(state, rng_dump(sid, rid))
    off_before, off_hp0, off_pos0 = footprint_off(state), hp_off(state), pos_off(state)
    res = _apply_active_ability(state, caster_id, target_id, MARTIAL_EXEMPLAR) or {}
    off_cast = delta(off_before, footprint_off(state))
    off_hp1, off_pos1 = hp_off(state), pos_off(state)
    diag = res.get("diag") or {}

    # ---- LIVE : le MEME cast, joue par le natif -------------------------------------------
    live_before, live_hp0, live_pos0 = footprint_live(dec0), hp_live(sid, rid), pos_live(dec0)
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": MARTIAL_EXEMPLAR,
        "targetId": target_id}}, 90) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = decision(sid, rid)
    live_cast = delta(live_before, footprint_live(dec1))
    live_hp1, live_pos1 = hp_live(sid, rid), pos_live(dec1)
    # VOLET (b) de `#889-r5-r3` : le canal INDEPENDANT de `decisionView`. On tire DEUX vues --
    # la vue FILTREE sur `1520` (la question posee) et la vue TOTALE (le temoin de non-degenerescence :
    # un `count: 0` filtre ne prouve rien si le canal rend 0 effet en tout).
    ea_1520 = effects_all(sid, rid, ME_EXTRA_CRIT)
    ea_tous = effects_all(sid, rid)

    return {
        "regime": regime, "rid": rid, "caster": caster_id, "target": target_id,
        "move_live": move_live, "n_feet": n_feet, "from_here": from_here,
        "routed": res.get("routed"), "ported": diag.get("ported"), "diag": diag,
        "cast_error": cast_error,
        "off_cast": off_cast, "live_cast": live_cast,
        "off_dhp": _dhp(off_hp0, off_hp1), "live_dhp": _dhp(live_hp0, live_hp1),
        "off_dpos": {k: (v, off_pos1.get(k)) for k, v in off_pos0.items()
                     if off_pos1.get(k) != v},
        "live_dpos": {k: (v, live_pos1.get(k)) for k, v in live_pos0.items()
                      if live_pos1.get(k) != v},
        "live_coups": coups_natifs(act), "substrat": substrat,
        # TEMOIN DE CONTROLE : le footprint ne rend qu'un DELTA, donc un effet DEJA present avant
        # le cast y serait invisible. On publie l'etat BRUT du caster apres cast pour distinguer
        # « le natif ne pose pas » de « le temoin ne voit pas ».
        "live_caster_effects": [
            {"t": e.get("effectType"), "rem": e.get("remaining")}
            for u in (dec1.get("units") or []) if int(u["id"]) == caster_id
            for e in (u.get("effects") or [])],
        "live_event_names": sorted({str(e.get("name") or e.get("type") or "?")
                                    for e in (act.get("events") or [])})[:14],
        # VOLET (b) `#889-r5-r3` -- tri-etat STRICT : `ok:false` reste `ok:false`, jamais un zero.
        "effects_all_1520": {
            "ok": ea_1520.get("ok"), "error": ea_1520.get("error"),
            "count": ea_1520.get("count"), "orphanCount": ea_1520.get("orphanCount"),
            "removedCount": ea_1520.get("removedCount"),
            "effects": [{k: e.get(k) for k in
                         ("entityId", "effectType", "inOwnerList", "removed", "active",
                          "ownerId", "sourceId", "targetIds", "remainingTurns")}
                        for e in (ea_1520.get("effects") or [])],
        },
        "effects_all_total": {"ok": ea_tous.get("ok"), "count": ea_tous.get("count"),
                              "types": sorted({int(e["effectType"])
                                               for e in (ea_tous.get("effects") or [])
                                               if e.get("effectType") is not None})},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", choices=("survit", "meurt", "vide", "both"), default="both")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = _session()
    regimes = ("survit", "vide") if a.regime == "both" else (a.regime,)
    for reg in regimes:
        m, dispose = measure(sid, reg, a.seed)
        try:
            print("=" * 92)
            print("REGIME %-7s runner=%s caster=%s target=%s move=%s feet=%s"
                  % (reg, m["rid"], m["caster"], m["target"], m["move_live"], m["n_feet"]))
            print("  routed=%s ported=%s cast_error=%s" % (m["routed"], m["ported"],
                                                           m["cast_error"]))
            print("  [A] EFFETS POSES  natif=%s" % json.dumps(m["live_cast"], sort_keys=True))
            print("                    port =%s" % json.dumps(m["off_cast"], sort_keys=True))
            print("  [B] PV (avant,apres)  natif=%s" % json.dumps(m["live_dhp"], sort_keys=True))
            print("                        port =%s" % json.dumps(m["off_dhp"], sort_keys=True))
            print("  [C] COUPS natifs par cible = %s" % json.dumps(m["live_coups"], sort_keys=True))
            print("      attaques normales du port  = %s"
                  % json.dumps((m["diag"] or {}).get("normal_attacks"), sort_keys=True,
                               default=str))
            print("  [D] POSITIONS changees  natif=%s port=%s"
                  % (json.dumps(m["live_dpos"], default=str),
                     json.dumps(m["off_dpos"], default=str)))
            print("      MoveUnit emis par le port = %s"
                  % json.dumps((m["diag"] or {}).get("moved"), default=str))
            print("  [S] SUBSTRAT caster = %s" % json.dumps(m.get("substrat"), default=str))
            print("  [E] DIAG COMPLET du port = %s"
                  % json.dumps(m["diag"], default=str, sort_keys=True)[:2600])
            print("  [F] EFFETS live du caster APRES = %s"
                  % json.dumps(m.get("live_caster_effects"), default=str))
            ea = m.get("effects_all_1520") or {}
            tot = m.get("effects_all_total") or {}
            print("  [G] effectsAll(1520) = %s" % json.dumps(ea, default=str, sort_keys=True))
            print("      effectsAll(TOUS)  ok=%s count=%s types=%s"
                  % (tot.get("ok"), tot.get("count"),
                     json.dumps(tot.get("types"), default=str)))
            if ea.get("ok") is not True:
                print("      VERDICT (b) : NON MESURE -- le canal a refuse (%s)" % ea.get("error"))
            elif tot.get("ok") is not True or not (tot.get("count") or 0):
                print("      VERDICT (b) : NON MESURE -- canal DEGENERE (0 effet en tout)")
            elif (ea.get("count") or 0) == 0:
                print("      VERDICT (b) : LE NATIF NE POSE PAS 1520 "
                      "(canal non degenere : %s effets au total)" % tot.get("count"))
            else:
                print("      VERDICT (b) : 1520 EST POSE -- c'est `decisionView` qui ne le publie "
                      "pas (count=%s, orphelins=%s, retires=%s)"
                      % (ea.get("count"), ea.get("orphanCount"), ea.get("removedCount")))
        finally:
            dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
