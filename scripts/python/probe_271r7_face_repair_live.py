#!/usr/bin/env python
"""#271-r7 -- CONFRONTATION LIVE de la face REPAIR du dispatcher non-owner.

    python probe_271r7_face_repair_live.py                 # montage NOMINAL
    python probe_271r7_face_repair_live.py --montage gate   # le CONTROLE

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
--------------------------------------------------
La face REPAIR (`IUtility <slot 2> = EvaluateRepairInSteps`) est la TROISIEME et derniere face du
dispatcher `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility`, membre du composite
`Repair(47)`. Son unique corps concret est
`IdunBattle.AI.Playbook.Loki.VoltagheistFieldPlaybook.u003CCalculateRepairUtilityInStepsu003Ed__1$$MoveNext`.

Ce probe mesure, sur un ETAT LIVE REEL, les trois memes choses que son jumeau de la face ATTACK
(`probe_271r4_face_attack_live.py`) :

  1. **ATTEIGNABILITE** -- le dispatcher yielde-t-il la paire `(playbook, owner)` ? C'est le
     pre-gate `<slot 4> || IsFriend` qui en decide, et `<slot 4>` vaut FALSE pour ce playbook
     (entree versionnee `metadata/non_owner_slot4.tsv`), donc tout tient a `IsFriend` ;
  2. **VALEUR** -- le terme est-il bien le DOUBLEMENT de `RepairedAmount(48)` ? Le corps ne lit
     AUCUNE cle BC : il RE-EMET la feuille. On exige donc `terme == repair_utility(...)` a
     l'identique, pas un poids ;
  3. **A/B OFF-vs-ON** -- l'utilite de reparation CHANGE-t-elle quand le registre REPAIR est
     desarme ? Sans ecart, le terme ne pese rien d'observable.

⚠ **CE QU'IL NE MESURE PAS** : l'ARGMAX NATIF. Meme limite que la face ATTACK -- aucun canal ne
publie le terme natif de cette feuille (les hooks par-feuille de `scorer-damage-trace` ne portent
que `TileEffects` et `CapturePointTile`). Ce qui est rendu ici est « le terme MORD, il vaut
EXACTEMENT le doublement attendu, et le gate l'ETEINT », pas « le natif suit ».

LE MONTAGE -- GREFFE, et pourquoi elle est LICITE
--------------------------------------------------
Les trois porteurs de `VoltagheistField` sont `admecSmnElectropriest` (SUMMON) et deux npc
`admecNpc3Electropriest*`. Recours 3 de `case-92` Sec.5bis : GREFFE du passif sur une unite DU
POOL. La condition est VERIFIEE au decompile, pas supposee : le corps ne lit du PORTEUR que son
IDENTITE (`case.Target != owner` -> break), aucune stat, aucun trait ; et le natif charge le
playbook PAR ABILITY (`LoadPlaybookNonOwner(ta.Type)`), jamais par unite.

On greffe donc sur `admecRuststalker`, la CIBLE REPAREE du montage de reparation deja etabli
(`tests/engine/runner/_repair_stage.py`) : c'est exactement ce que le corps exige, puisqu'il ne
rend une valeur que quand `case.Target == owner`.

DEUX CONTROLES, et ils ne gardent PAS le meme gate
---------------------------------------------------
* `--montage gate` greffe le passif sur le REPAREUR lui-meme. Le terme tombe a 0, mais **par
  l'exclusion de SELF** d'`IterateAbilities` (inconditionnelle) : le porteur n'est meme pas
  ITERE. Ce bras garde l'exclusion de self, PAS le corps.
* `--montage tiers` greffe sur une TROISIEME unite amie, ni repareur ni cible. Le porteur EST
  itere (ami, non-self, donc le pre-gate `<slot 4> || IsFriend` passe), et c'est le CORPS qui
  doit rendre 0 sur `if (case.Target != owner) yield break`. **C'est le seul bras qui garde le
  gate du corps** -- et le distinguer du precedent est ce qui evite de croire tester un gate
  qu'on ne touche pas.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                                 # noqa: E402

#: Le montage de reparation DEJA ETABLI (`tests/engine/runner/_repair_stage.py`) : les deux sont
#: HERO et dans `rl_duel.py build --list-pool` au rank 17.
REPAIRER_VIS = "admecManipulus"      # trait Mechanic -> reparation derivee
REPAIREE_VIS = "admecRuststalker"    # trait Mechanical -> reparable ; c'est LUI l'owner greffe
TIERS_VIS = "admecDominus"           # 3e ami : porteur du CONTROLE `tiers` (ni sujet, ni cible)
ENEMY_VIS = "orksNob"
ABILITY_NAME = "VoltagheistField"
BOARD = "MC1_67"


def _seed_bc(out: Path, montage: str) -> Path:
    import catalog_inject as CI
    bc = CI._load_seed(None)                                                 # noqa: SLF001
    owner = {"nominal": REPAIREE_VIS,     # la CIBLE reparee -> `case.Target == owner` -> valeur
             "gate": REPAIRER_VIS,        # le SUJET -> exclu par `IterateAbilities` (self)
             "tiers": TIERS_VIS}[montage]  # un TIERS ami -> itere, mais `case.Target != owner`
    rep = CI.graft_passive_ability(bc, owner, ABILITY_NAME)
    print("  greffe : %s -> %s (id %s), %s entree(s), avant=%s"
          % (owner, ABILITY_NAME, rep.get("abilityId"), rep.get("unitsPatched"),
             rep.get("passiveAbilitiesBefore")))
    if not rep.get("unitsPatched"):
        print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _build(seed: str, seed_bc: Path, state: Path, hp: int, montage: str) -> int:
    roster = "%s,%s" % (REPAIRER_VIS, REPAIREE_VIS)
    if montage == "tiers":
        roster += "," + TIERS_VIS
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", BOARD,
            "--state-file", str(state), "--seed-bc", str(seed_bc),
            "--p-units", roster,
            "--a-units", ENEMY_VIS,
            # blesse la cible SANS toucher sa sante MAX (`--hp-player` ecrirait les deux).
            "--unit-stat", "%s:RemainingHealth=%d" % (REPAIREE_VIS, hp)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit("BUILD KO rc=%d\n%s" % (p.returncode, (p.stderr or "")[-1500:]))
    return json.loads(state.read_text(encoding="utf-8"))["runnerId"]


def mesurer(rpc, rid: int, gate: bool, max_steps: int = 14) -> dict:
    """Cherche un pas ou le REPAREUR est active, et evalue la face REPAIR sur son etat."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.utilities.tile import triggered_abilities_non_owner_repair_utility as F
    from engine.utilities.repair import REPAIR_UTILITY
    import engine.playbook.non_owner_repair as NR
    sys.path.insert(0, str(PYDIR / "tests" / "engine"))
    from _move_tile_sweep_order import _apply_native                          # noqa: E402

    from engine.entities.triggered_ability_type import TriggeredAbilityType
    ABILITY = int(TriggeredAbilityType.VoltagheistField)
    wt = W.load()
    for step in range(max_steps):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"ok": False, "raison": "trajectoire finie au pas %d (%s)"
                    % (step, dry.get("error"))}
        uid = dry.get("activatedUnitId")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if me is None or me.get("visualId") != REPAIRER_VIS:
            _apply_native(rpc, rid, dry)
            continue
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
        ctx = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv, mov_by_unit, uid, wt, predictor)
        sc = ctx.scene
        porteurs = []
        for u in (sc.units or []):
            oid = u.get("id")
            if oid is None or int(oid) == int(uid):
                continue
            if ABILITY in list(ctx.live_triggered_ability_ids(oid) or ()):
                porteurs.append({"id": int(oid), "vis": sc.vis_by_id.get(int(oid)),
                                 "ami": sc.team(int(oid)) == sc.team(uid)})
        # la CIBLE reparee : l'unite MECHANICAL amie et blessee. `hpMax` n'est PAS dans
        # `decisionView.units[]` -- il vient d'`observeBattle`, exactement comme le fait
        # `_repair_candidates` (`obs_by_sq[tg]["hpMax"]`). Le lire ailleurs inventerait un maximum.
        cible = next((u for u in (dv.get("units") or [])
                      if u.get("visualId") == REPAIREE_VIS), None)
        if cible is None:
            return {"ok": False, "raison": "cible %s absente de decisionView" % REPAIREE_VIS}
        tg = int(cible["id"])
        ob = rpc("observeBattle", {"runnerId": rid}, 90) or {}
        # ⚠ la cle d'appariement est `squadId`, PAS `entityId` -- c'est celle que
        # `_repair_candidates` utilise (`obs_by_sq`), et `decisionView.units[].id` est un squadId.
        row = next((u for u in (ob.get("units") or []) if u.get("squadId") == tg), {})
        hp, hp_max = row.get("hp"), row.get("hpMax")
        if hp is None or hp_max is None:
            return {"ok": False, "raison": "observeBattle ne publie ni hp ni hpMax pour u%d" % tg}
        fill = max(0, int(hp_max) - int(hp))
        base = REPAIR_UTILITY.evaluate(fill, hp_max, False)
        on = F(ctx, uid, tg, fill, hp_max, False)
        anc = dict(NR.NON_OWNER_REPAIR_PLAYBOOKS)
        try:
            NR.NON_OWNER_REPAIR_PLAYBOOKS.clear()          # A/B : registre DESARME
            off = F(ctx, uid, tg, fill, hp_max, False)
        finally:
            NR.NON_OWNER_REPAIR_PLAYBOOKS.update(anc)
        return {"ok": True, "step": step, "repairer": uid, "cible": tg,
                "hp": hp, "hp_max": hp_max, "fill": fill,
                "porteurs": porteurs, "on": on, "off": off,
                "repaired_amount": base, "gate": gate}
    return {"ok": False, "raison": "le repareur %s n'a pas ete active en %d pas"
            % (REPAIRER_VIS, max_steps)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--montage", default="nominal", choices=["nominal", "gate", "tiers"])
    ap.add_argument("--seed", default="777")
    ap.add_argument("--hp", type=int, default=30, help="RemainingHealth de la cible reparee")
    a = ap.parse_args()
    gate = (a.montage != "nominal")
    sid = R._resolve_session()                                               # noqa: SLF001
    if not sid:
        print("PAS MESURE : aucune session Frida")
        return 99
    tag = uuid.uuid4().hex[:8]
    tmp = PYDIR.parents[1] / "logs"
    tmp.mkdir(parents=True, exist_ok=True)
    bcp = _seed_bc(tmp / ("bc_271r7_%s.json" % tag), a.montage)
    stf = tmp / ("st_271r7_%s.json" % tag)
    rid = _build(a.seed, bcp, stf, a.hp, a.montage)
    print("=== #271-r7 face REPAIR non-owner -- montage %s, runner %d ===" % (a.montage, rid))
    rpc = lambda m, b, t: (lambda d: d.get("result", d))(R._rpc(sid, m, b, t))   # noqa: E731,SLF001
    try:
        res = mesurer(rpc, rid, gate)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                        # noqa: BLE001
            print("  (disposeRunner a echoue -- runner %d a nettoyer)" % rid)
    if not res.get("ok"):
        print("PAS MESURE : %s" % res.get("raison"))
        return 99
    print("pas %d : repareur u%s, cible u%s  hp=%s/%s  fill=%s"
          % (res["step"], res["repairer"], res["cible"], res["hp"], res["hp_max"], res["fill"]))
    print("porteurs de %s VUS par le dispatcher : %s"
          % (ABILITY_NAME, res["porteurs"] or "AUCUN"))
    print("RepairedAmount(48) seul            : %s" % res["repaired_amount"])
    print("face REPAIR non-owner  registre ON : %s" % res["on"])
    print("face REPAIR non-owner  registre OFF: %s" % res["off"])
    ecart = (res["on"] - res["off"]) if (res["on"] is not None and res["off"] is not None) else None
    print("ECART A/B (ON - OFF)               : %s" % ecart)
    if gate:
        quoi = ("l'exclusion de SELF d'`IterateAbilities`" if a.montage == "gate"
                else "le gate `case.Target != owner` DU CORPS")
        vus = bool(res["porteurs"])
        print("\nVERDICT (CONTROLE %s) : le terme doit valoir 0, par %s -- %s"
              % (a.montage, quoi, "OK" if not res["on"] else "ROUGE"))
        if a.montage == "tiers" and not vus:
            print("   DEGENERE : aucun porteur ITERE -- ce bras n'a pas garde le corps.")
        elif a.montage == "tiers":
            print("   porteur ITERE et terme NUL : c'est bien le CORPS qui a rendu 0.")
    else:
        att = res["repaired_amount"]
        ok = (att is not None and res["on"] is not None and abs(res["on"] - att) < 1e-9)
        print("\nVERDICT : le terme doit DOUBLER `RepairedAmount(48)` (aucune cle BC lue).")
        print("   attendu = %s   mesure = %s   %s" % (att, res["on"], "OK" if ok else "ECART"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
