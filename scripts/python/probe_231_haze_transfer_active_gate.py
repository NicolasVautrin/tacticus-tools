"""#231 -- le gate `EffectComponent.IsActive @+0x5c` du report 1077 mord-il un bond de PRODUCTION ?

QUESTION (binaire) : un bond `HazeOfCorruption_DamageTransfer` (0x435 = 1077) REELLEMENT pose en
bataille est-il publie ACTIF par le canal de seed ? Si le canal le rendait inerte, le gate pose en
#231 dans `HazeOfCorruptionDamageTransferTrigger.matches` eteindrait un report LEGITIME -- une
regression que la garde deterministe (etat monte a la main) ne peut PAS voir.

ARTEFACT NATIF (decompile, build `gqfc5mff6c`) :

    IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets
        ... boucle PAR CIBLE ...
        <component> = GetComponent<EffectComponent>(<entite-effet>)
        if (*(char *)(<component> + 0x5c) != '\\0') {      <-- LE GATE
            if (ShouldTrigger(slot 0x13)) { ... Execute(slot 0x14) ... }
        }

    Le rail JUMEAU `...$$EvaluateEffectTriggerEffectAbilities` n'accede JAMAIS a `+0x5c` : le gate
    ne vaut QUE pour les triggers issus de `<Effect>$$CreateTargetTrigger` -- ce qui est le cas de
    `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`.

MONTAGE : la geometrie k = 1 de `probe_207_haze_pool_ladder.py` avec `--hp-target` HAUT (la cible
SURVIT). Le target-finder tire et POSE le bond a l'entree de l'ability, mais rien ne meurt -> le
bond RESTE en place et devient observable dans `decisionView`. C'est le seul regime ou un 1077 de
production est lisible au repos (a PV bas il est pose ET consomme dans la meme action).

CE QUE LE PROBE MESURE, par etage (jamais un scalaire fitte) :
  1. le canal PUBLIE-t-il le bond ?          -> presence de 1077 dans `decisionView.effects`
  2. avec quel flag ?                        -> la cle `active` de l'entree (les DEUX canaux :
                                                defaut, et `includeInactive: true`)
  3. le port le TRANSPORTE-t-il ?            -> `EffectFactory.create(<entree>).active`
  4. le gate LAISSE-t-il passer ?            -> `HazeOfCorruptionDamageTransferTrigger.matches`
                                                sur un etat portant CETTE instance

CLI (depuis scripts/python) :
  python probe_231_haze_transfer_active_gate.py
  python probe_231_haze_transfer_active_gate.py --seeds 777,88 --hp 90000

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys

from probe_r6_round_materialize import _mkrpc
from probe_159_ah_bounds import _board
from probe_207_haze_pool_ladder import CARRIER, _drive_pool
from probe_209_haze_damage_transfer import _build

HAZE_XFER = 0x435          # 1077 -- `AddBondEffect(0x435, ...)` du target-finder, litteral lu


def _effects_1077(dv):
    """Les (ownerId, entree) de tous les effets 1077 publies par un `decisionView`."""
    out = []
    for u in (dv.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("effectType") == HAZE_XFER:
                out.append((u.get("id"), e))
    return out


def _gate_verdict(entry, owner_id, source_id, bonded_id):
    """Etages 3 et 4 : le port transporte-t-il le flag, et le gate laisse-t-il passer ?
    Renvoie (active_porte, matches). L'etat est monte autour de l'entree REELLEMENT captee."""
    from engine.entities.effects.factory import EffectFactory
    from engine.entities.effects_state import EffectsState
    from engine.runner.components import UnitComponent
    from engine.runner.state import State
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki import haze_of_corruption as H

    eff = EffectFactory.create(dict(entry))
    st = State()
    relay, dying, carrier = st.add_entity(), st.add_entity(), st.add_entity()
    for e in (relay, dying, carrier):
        e.add_component(UnitComponent(visual_id=CARRIER, alive=True))
    eff.source, eff.target, eff.bonded = dying.id, relay.id, carrier.id
    st.effects = EffectsState(by_unit={relay.id: [eff]})
    trg = H.HazeOfCorruptionDamageTransferTrigger(relay.id)
    ev = TriggerEvent(H._ON_UNIT_DEATH, carrier.id, dying.id, ranged=False, profile=None,
                      killer_id=carrier.id, dying_id=dying.id)
    return bool(eff.active), bool(trg.matches(st, ev))


def _run(rpc, seed, hp, args):
    rid, sf = _build(seed, hp, args.armor)
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, 1)
        if cid is None:
            print("[231] seed %s hp=%s : drive KO -- %s" % (seed, hp, err))
            return None
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        # ETAGE 0 -- le bond a-t-il seulement ete POSE ? Sans ce temoin, « 1077 absent du canal »
        # est ambigu : canal muet, ou aucun bond. Le flux natif publie la pose sous
        # `BondEffect_BondedId` (mesure case-207).
        posed = []
        for act in (res.get("actions") or []):
            for ev in (act.get("events") or []):
                td = ev.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "BondEffect_BondedId" in td or td.get("Effect_Type") == HAZE_XFER:
                    posed.append({"name": ev.get("name") or ev.get("type"), "tags": td})
        # Les DEUX canaux : le defaut (actifs SEULS -- « present == actif ») et l'explicite
        # (`includeInactive` publie AUSSI les inertes, avec leur vrai flag). Un bond present dans
        # le premier est necessairement actif ; le second le CONFIRME en lisant le flag.
        dv_def = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        dv_all = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                      "includeInactive": True}, 120)
        alive = None
        for u in (dv_def.get("units") or []):
            if u.get("id") == tid:
                alive = u.get("alive")
        allmap = {}
        for u in (dv_all.get("units") or []):
            if u.get("effects"):
                allmap[u.get("id")] = [(e.get("effectType"), e.get("name"), e.get("active"),
                                        e.get("remaining")) for e in u["effects"]]
        return {"seed": seed, "hp": hp, "cid": cid, "tid": tid, "target_alive": alive,
                "posed": posed,
                "def": _effects_1077(dv_def), "all": _effects_1077(dv_all), "allmap": allmap}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777,88")
    ap.add_argument("--hp", default="90000")       # la cible SURVIT -> le bond reste observable
    ap.add_argument("--armor", type=int, default=0)
    args = ap.parse_args()
    rpc = _mkrpc()
    ok, rows = True, []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for hp in [int(h) for h in str(args.hp).split(",") if h.strip()]:
            r = _run(rpc, seed, hp, args)
            if r is None:
                ok = False
                continue
            rows.append(r)
            print("[231] seed %s hp=%d : caster=%s cible=%s (vivante=%s)"
                  % (seed, hp, r["cid"], r["tid"], r["target_alive"]))
            # ETAGE 0 -- le bond a-t-il ete pose ? (temoin, exige AVANT toute lecture de canal)
            print("      ETAGE 0  bonds POSES dans le flux natif = %d" % len(r["posed"]))
            for p in r["posed"]:
                print("               %-28s %s" % (p["name"], json.dumps(p["tags"])[:260]))
            if not r["posed"]:
                ok = False
                print("      FAIL: aucun bond pose -- montage non concluant (pool vide ?)")
            # ETAGE 1 -- le canal sait-il publier un effet INERTE ? (le vecteur d'exposition du gate)
            inertes = [(u, e) for u, effs in r["allmap"].items() for e in effs if e[2] is False]
            print("      ETAGE 1  effets publies INERTES (includeInactive) = %d %s"
                  % (len(inertes), json.dumps(inertes[:4])))
            if not inertes:
                ok = False
                print("      FAIL: aucun effet inerte publie -- le canal ne prouve pas le vecteur")
            # ETAGE 2 -- le 1077 est-il publie, et avec quel flag ?
            print("      ETAGE 2  1077 publies -- canal DEFAUT = %d, includeInactive = %d"
                  % (len(r["def"]), len(r["all"])))
            for owner, e in r["all"]:
                porte, matched = _gate_verdict(e, owner, e.get("source"), r["cid"])
                print("               owner=%-4s effectId=%-5s active(canal)=%-5s remaining=%-4s "
                      "-> active(port)=%-5s matches=%s"
                      % (owner, e.get("effectId"), e.get("active"), e.get("remaining"),
                         porte, matched))
                if e.get("active") is not True or porte is not True or matched is not True:
                    ok = False
                    print("      FAIL: un bond de PRODUCTION est vu inerte -> le gate #231 mordrait")
            if not r["all"]:
                print("               1077 HORS CANAL de seed : le bond vit sur son entite-effet "
                      "mais n'entre pas dans l'`EffectsOwnedComponent` publie par decisionView. "
                      "=> le gate ne peut PAS mordre un bond seede (il n'y en a pas) ; il garde "
                      "le chemin OFFLINE (pose par le port, active=True par defaut) et tout "
                      "canal futur.")
    print("")
    print("RESULT: %s" % ("OK" if (ok and rows) else "FAIL"))
    return 0 if (ok and rows) else 1


if __name__ == "__main__":
    sys.exit(main())
