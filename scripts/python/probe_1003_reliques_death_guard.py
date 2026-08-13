"""#1003 -- MONTAGE de confrontation NATIF <-> PORT des deux reliques Death Guard.

L'observable retenu est le volet **INCONDITIONNEL** des deux abilities : la CONTAMINATION de la
tuile de la cible (`AddEffect(0x4dc = 1244 Contaminated, targets = TargetTiles@DSLSelectors+0x78)`).
C'est le seul des deux volets qui ne depend d'aucun etat prealable, donc le seul qui separe
proprement « la relique est montee et son trigger fire » de « rien ne s'est passe ».

  * `Lakrimae` (1541) -- `Lakrimae_AddContamination_Ability`, `On(0x26 = NormalAttack) &
    get_OwnerIsActor & IsMeleeAttack & IsNormalAttack`. Porteur `deathTyphus`.
  * `OrbsOfDecay` (1465) -- `OrbsOfDecayAbility`, `On(0x4a = AttackInAtomicGroup) &
    get_OwnerIsCaster & IsMeleeAttack`. Porteur `deathBlightbringer`.

POURQUOI LE TEMOIN N'EST PAS UN CONFOND. `OnToxicDamageAbility` (1203) pose LE MEME effet 1244 sur
LA MEME tuile quand le coup porte le trait de profil `OnToxic` -- ce serait un confond parfait. Il
est ECARTE par le choix du porteur, pas par un raisonnement : l'arme de melee de `deathTyphus` est
`Power` et celle de `deathBlightbringer` `Plasma` (`gameconfig.units.*.weapons`, LU), donc 1203 ne
peut pas fire. `deathPutrifier`, dont l'arme EST `Toxic`, est ecarte pour cette raison exacte.

TROIS BRAS, et chacun tombe pour une raison DIFFERENTE :
  * POSITIF  : relique equipee -> la tuile de la cible porte `Contaminated` apres l'attaque ;
  * TEMOIN   : MEME montage, MEME attaque, SANS `--equip-relic` -> aucune contamination
               (ce n'est donc pas l'attaque qui contamine, c'est la relique) ;
  * PORT     : la MEME capture pre-attaque, rejouee OFFLINE, contamine la MEME tuile
               (et ne contamine RIEN dans le bras temoin).

Usage : python probe_1003_reliques_death_guard.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

CONTAMINATED = 1244                     # `EffectType.Contaminated` = 0x4dc
SEED = "777"
BOARD = "MC1_67"

#: `(porteur, relique, arme de melee LUE au gameconfig)`. L'arme n'est PAS `Toxic` : c'est ce qui
#: ecarte le confond `OnToxicDamageAbility` (1203), qui poserait le MEME effet sur la MEME tuile.
CAS = {
    "Lakrimae": ("deathTyphus", "Lakrimae", "Power"),
    "OrbsOfDecay": ("deathBlightbringer", "OrbsOfDecay", "Plasma"),
}
#: Cible NON mecanique, sans trait d'immunite, placee ADJACENTE au porteur.
ENNEMI = "orksNob"
#: `MC1_67` : deux tuiles voisines, cote joueur / cote adverse (memes coordonnees que le montage
#: relique deja vert de `test_462_..._post_unit_kill_live.py`).
POSE_PORTEUR = "3,4"
POSE_ENNEMI = "3,5"


def build_args(carrier: str, relic: str | None) -> list:
    a = ["--p-units", carrier, "--a-units", ENNEMI, "--rank", "17", "--board", BOARD,
         "--place", f"{carrier}:{POSE_PORTEUR}", "--a-place", f"{ENNEMI}:{POSE_ENNEMI}"]
    if relic:
        a += ["--equip-relic", f"{carrier}:{relic}:50"]
    return a


def _tiles_contaminees(rpc, rid, board) -> set:
    """`tileMeta.tiles[].effects` -- le canal NATIF des effets de TUILE (`decisionView.units[].
    effects` ne publie que ceux des UNITES)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == CONTAMINATED for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(int(tid))
    return out


def _port_contamine(dv, ob, snap, board, carrier_vis: str, victim_vis: str, profile: str,
                    relic: str) -> dict:
    """Rejoue OFFLINE le VECTEUR de l'ability sur la capture PRE-attaque, et rend les tuiles que le
    port a contaminees.

    On emet le vecteur NATIF de chaque ability, pas le pipeline de degat complet : c'est ce qui
    ISOLE le trigger (un degat offline deplacerait des tirages `state.rng` et melangerait les
    causes). Les deux vecteurs sont ceux que le port emet deja en bataille :
      * `after_hit_normal_attack` -> `On(0x26 = NormalAttack)`      (Lakrimae) ;
      * `evaluate_abilities_for_event(..., AttackInAtomicGroup)`    (OrbsOfDecay), avec le marqueur
        de kind `NORMAL_ATTACK_KIND` que la voie normale thread."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.dispatch.ability import evaluate_abilities_for_event
    from engine.runner.operations.triggers.dispatch.attack import after_hit_normal_attack
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board)

    def by_vis(vis):
        for uid, e in state.entities.items():
            sc = e.get_component(StatsComponent)
            if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                return uid
        return None

    car, vic = by_vis(carrier_vis), by_vis(victim_vis)
    if car is None or vic is None:
        return {"error": "porteur/cible absents offline (%s/%s)" % (car, vic)}
    sc = state.get_entity(car).get_component(StatsComponent)
    avant = {tid for tid, lst in state.effects.by_unit.items()
             if any(int(getattr(e, "effect_type", -1)) == CONTAMINATED for e in (lst or []))}
    if relic == "Lakrimae":
        out = after_hit_normal_attack(state, car, vic, ranged=False, profile=profile) or []
    else:
        out = evaluate_abilities_for_event(state, car, vic,
                                           int(EventTriggerType.AttackInAtomicGroup),
                                           ranged=False, profile=profile,
                                           ability_type=NORMAL_ATTACK_KIND,
                                           fire_of_absolution=False) or []
    apres = {tid for tid, lst in state.effects.by_unit.items()
             if any(int(getattr(e, "effect_type", -1)) == CONTAMINATED for e in (lst or []))}
    ev = [e for e in out if isinstance(e, dict) and e.get("relic") == relic]
    return {"tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "tertiary_level": getattr(sc.ctx, "tertiary_ability_level", None),
            "events": len(ev), "nouvelles_tuiles": sorted(apres - avant),
            "carrier": car, "victim": vic}


def run(rpc, relic_key: str, avec_relique: bool, build_runner=None, keep: bool = True) -> dict:
    """Monte le regime, mesure le NATIF puis rejoue le PORT sur la MEME capture pre-attaque."""
    from engine.entities.pathfinding.board import Board

    carrier, relic, profile = CAS[relic_key]
    out = {"relic": relic_key, "avec_relique": bool(avec_relique), "ok": False, "why": None}
    extra = build_args(carrier, relic if avec_relique else None)
    if build_runner is None:
        out["why"] = "ce probe exige la fabrique `build_runner` du harnais pytest"
        return out
    rid = build_runner(SEED, extra=extra)["rid"]
    out["rid"] = rid

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo -- montage a reparer"
        return out
    board = Board(bg["tiles"], adjacency="native_sym")

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    vivants = {u.get("visualId"): u for u in (ob.get("units") or []) if not u.get("isDead")}
    if carrier not in vivants or ENNEMI not in vivants:
        out["why"] = "porteur ou cible absents du plateau : %s" % sorted(vivants)
        return out
    sq = {v: u.get("squadId") for v, u in vivants.items()}
    out["squads"] = sq

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tuiles_avant = _tiles_contaminees(rpc, rid, board)
    out["tuiles_avant"] = sorted(tuiles_avant)

    # tuile de la CIBLE = l'ancre de `TargetTiles@DSLSelectors+0x78`.
    tgt = vivants[ENNEMI]
    tid = board.id_at(tgt["col"], tgt["row"]) if "col" in tgt else None
    if tid is None:
        pos = (tgt.get("tiles") or [{}])[0]
        tid = board.id_at(pos.get("col"), pos.get("row")) if pos else None
    out["tuile_cible"] = None if tid is None else int(tid)

    # --- PORT : la capture PRE-attaque, rejouee offline ------------------------------------------
    out["port"] = _port_contamine(dv, ob, snap, board, carrier, ENNEMI, profile, relic)

    # --- NATIF : l'attaque normale REELLE --------------------------------------------------------
    # `applyAction` ne connait PAS de `kind: "attack"` : l'attaque normale est une ABILITY, dont
    # l'`ActiveAbilityType` est CONCRET et PER-UNITE (`ActiveAbilityComponent.NormalAttackType`,
    # expose par `decisionView` en `kind == "normal"`).
    nat = None
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(sq[carrier]):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal" and ab.get("id") is not None:
                    nat = int(ab["id"])
    if nat is None:
        out["why"] = "%s n'expose aucune attaque normale (decisionView kind=normal)" % carrier
        return out
    out["normal_attack_type"] = nat
    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq[carrier], "targetId": sq[ENNEMI],
        "abilityType": nat}}, 120)
    out["attack_ack"] = {k: act.get(k) for k in ("ok", "error")} if isinstance(act, dict) \
        else {"raw": str(act)[:200]}

    tuiles_apres = _tiles_contaminees(rpc, rid, board)
    out["tuiles_apres"] = sorted(tuiles_apres)
    out["natif_nouvelles_tuiles"] = sorted(tuiles_apres - tuiles_avant)
    out["ok"] = True
    return out


def main() -> int:
    print("Ce probe se pilote depuis le harnais pytest (fabrique `build_runner`) :")
    print("  python -m pytest tests/engine/runner/test_1003_reliques_death_guard_live.py -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
