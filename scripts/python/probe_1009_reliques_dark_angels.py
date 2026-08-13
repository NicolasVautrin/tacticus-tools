"""#1009 -- MONTAGE de confrontation NATIF <-> PORT des deux reliques DARK ANGELS.

UN SEUL montage pour les deux abilities : `darkaCompanion` << Forcas >> porte
`MonsterSlayerOfCaliban` (1527) et `darkaTerminator` << Baraqiel >> porte `RelicPowerFist` (1466).
Les deux sont Dark Angels (`FactionId` LU au gameconfig) et dans `rl_duel build --list-pool` au
rank 17, donc l'etat 2 des trois etats d'une relique suffit : `--equip-relic` (#237).

  * `MonsterSlayerOfCaliban` -- `OnOwnerSpecificAbilityInit(1527)` -> pose sur le porteur les DEUX
    owner-effects 1539 (`_ExtraDmg`) et 1540 (`_ExtraBlock`). L'observable RETENU est le DEGAT :
    `+extraDmg[niveau]` FLAT contre une cible `Vehicle` / `BigTarget`.
  * `RelicPowerFist` -- `On(9 = Attack) & get_OwnerIsCaster & CurrentAttackDamageProfilesContain(
    Power, includeNotApplied = true)` -> DEUX `Maybe` independants (`Pinned` puis `Stunned`).
    L'observable RETENU est double : les effets poses, ET **l'etat du MT19937 apres l'attaque** --
    deux `next_bool` consomment deux tirages, donc un port qui n'en ferait qu'un (ou aucun)
    DESYNCHRONISE le PRNG meme quand les deux tirages tombent a faux.

TROIS BRAS, chacun tombant pour une raison DIFFERENTE :
  * POSITIF : les deux reliques equipees -> effets 1539/1540 captes sur Forcas, bonus de degat
              engage vs `Vehicle`, et l'attaque de Baraqiel consomme les deux tirages ;
  * TEMOIN  : MEME montage, MEMES attaques, SANS `--equip-relic` -> aucun des deux effets, degat
              per-hit STRICTEMENT plus bas, et deux tirages de MOINS ;
  * PORT    : la MEME capture pre-attaque, rejouee OFFLINE avec le MT19937 du natif, rend les
              MEMES degats per-hit, les MEMES PV et le MEME etat de MT.

⚠ **LE NIVEAU DE RELIQUE EST CHOISI POUR SEPARER** (#1008) : `level = 3` donne
`extraDmg[3] = 543` contre `extraDmg[10] = 728` au palier clampe des passifs (50), et
`chance[3] = 36` contre `chance[10] = 50`. Lire le mauvais couple `(level, mult)` est donc
VISIBLE. La seule variable qui ne separe pas est `blockChance`, CONSTANTE (10) sur les dix paliers
du gameconfig -- c'est un fait de config, dit plutot que masque.

Usage : python probe_1009_reliques_dark_angels.py       (exige la fabrique `build_runner` pytest)

ASCII only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SEED = "777"
BOARD = "MC1_67"

#: Le porteur de chaque relique, sa tuile, et le niveau EQUIPE (cf. l'en-tete : il SEPARE).
FORCAS = "darkaCompanion"
BARAQIEL = "darkaTerminator"
RELIC_LEVEL = 3

#: Cibles. `admecDestroyer` porte `Vehicle` et `tauCrisis` `BigTarget` (LU au gameconfig) : les DEUX
#: traits du `op_BitwiseOr` de `MonsterSlayerofCaliban_ExtraDmgEffect$$CreateDamageModifier`.
#: `eldarRanger` n'en porte AUCUN -> c'est le bras NEGATIF du gate, evalue OFFLINE sur la meme
#: capture (aucune attaque, donc aucun etat consomme).
VEHICLE_TARGET = "admecDestroyer"
BIGTARGET_TARGET = "tauCrisis"
NEUTRAL_TARGET = "eldarRanger"

#: Tuiles de `MC1_67` -- Forcas ADJACENT au `Vehicle`, Baraqiel ADJACENT au `BigTarget`, et le
#: neutre adjacent a Forcas (il n'est jamais attaque : il ne sert qu'au bras NEGATIF offline).
#: odd-q : les voisins de (3,2) sont (3,1) (3,3) (2,2) (2,3) (4,2) (4,3).
POSE = {FORCAS: "3,2", BARAQIEL: "4,3"}
POSE_ENNEMI = {VEHICLE_TARGET: "3,3", BIGTARGET_TARGET: "4,2", NEUTRAL_TARGET: "2,3"}

MSC_EXTRA_DMG = "MonsterSlayerOfCaliban_ExtraDmg"       # EffectType 0x603 = 1539
MSC_EXTRA_BLOCK = "MonsterSlayerOfCaliban_ExtraBlock"   # EffectType 0x604 = 1540
PINNED = 1065                                            # EffectType 0x429
STUNNED = 1162                                           # EffectType 0x48a


def build_args(avec_reliques: bool) -> list:
    a = ["--rank", "17", "--board", BOARD,
         "--p-units", "%s,%s" % (FORCAS, BARAQIEL),
         "--a-units", "%s,%s,%s" % (VEHICLE_TARGET, BIGTARGET_TARGET, NEUTRAL_TARGET)]
    for vid, tile in POSE.items():
        a += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in POSE_ENNEMI.items():
        a += ["--a-place", "%s:%s" % (vid, tile)]
    if avec_reliques:
        a += ["--equip-relic", "%s:MonsterSlayerOfCaliban:%d" % (FORCAS, RELIC_LEVEL),
              "--equip-relic", "%s:RelicPowerFist:%d" % (BARAQIEL, RELIC_LEVEL)]
    return a


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    rng.call_count = 0
    return rng


def _by_vis(state, vis):
    from engine.runner.components import StatsComponent
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _effet(state, uid, name):
    """L'objet effet `name` porte par `uid` dans la capture (None si absent)."""
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    if state.effects is None:
        return None
    actifs = state.effects.active_effects(uid, {"hp": hc.hp if hc is not None else None})
    return next((ef for ef in actifs if getattr(ef, "name", None) == name), None)


def _effets_de(dv, uid) -> list:
    """Les `effectType` publies par `decisionView.units[].effects` pour l'unite `uid`."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return sorted(int(e.get("effectType")) for e in ((u or {}).get("effects") or [])
                  if e.get("effectType") is not None)


def _mesures_offline(dv, ob, snap, board):
    """Bras OFFLINE PUR : ce que le PORT lit de la capture INITIALE, sans jouer une seule action.

    Prouve (a) que les deux owner-effets de 1527 sont bien montes par le canal `ABILITY_INIT_
    OWNER_EFFECTS`, (b) que la magnitude lue est celle du palier TERTIAIRE et non du palier clampe
    des passifs, (c) que le gate de trait REFUSE une cible sans `Vehicle`/`BigTarget`, et (d) que
    `RelicPowerFist` lit `chance[3]`/`chance_2[3]`."""
    from engine.runner.components import StatsComponent
    from engine.runner.damage_model import target_trait_names
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.loki.relic_power_fist import relic_vars

    state = load_state(dv, ob, snap, board=board)
    forcas, baraqiel = _by_vis(state, FORCAS), _by_vis(state, BARAQIEL)
    veh, big, neutre = (_by_vis(state, VEHICLE_TARGET), _by_vis(state, BIGTARGET_TARGET),
                        _by_vis(state, NEUTRAL_TARGET))
    if None in (forcas, baraqiel, veh, big, neutre):
        return {"error": "unite(s) absente(s) offline : %r"
                         % [forcas, baraqiel, veh, big, neutre]}
    sc = state.get_entity(forcas).get_component(StatsComponent)
    scb = state.get_entity(baraqiel).get_component(StatsComponent)
    dmg = _effet(state, forcas, MSC_EXTRA_DMG)
    blk = _effet(state, forcas, MSC_EXTRA_BLOCK)
    traits = {"vehicle": target_trait_names(state, veh),
              "bigtarget": target_trait_names(state, big),
              "neutre": target_trait_names(state, neutre)}
    bonus = {}
    if dmg is not None:
        for cle, tr in traits.items():
            b = dmg.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=tr)
            bonus[cle] = (None if b is None else {"kind": b.kind, "value": b.value})
        # Les DEUX natures, pour montrer qu'AUCUN gate `IsMeleeAttack`/`IsNormalAttack` n'existe
        # (contraste `BeastSlayer_ExtraDmg`, meme paire de traits, qui en porte un).
        b_r = dmg.create_effect_damage_bonus_for_attack(is_ranged=True,
                                                        target_traits=traits["vehicle"])
        bonus["vehicle_ranged"] = (None if b_r is None else {"kind": b_r.kind, "value": b_r.value})
        b_ab = dmg.create_effect_damage_bonus_for_attack(is_ranged=False, is_normal_attack=False,
                                                         target_traits=traits["vehicle"])
        bonus["vehicle_ability"] = (None if b_ab is None
                                    else {"kind": b_ab.kind, "value": b_ab.value})
    src = blk.create_effect_block_source_for_defense() if blk is not None else None
    return {
        "forcas": forcas, "baraqiel": baraqiel, "veh": veh, "big": big, "neutre": neutre,
        "traits": {k: sorted(v) for k, v in traits.items()},
        "forcas_tertiary": getattr(sc.ctx, "tertiary_ability", None),
        "forcas_tertiary_level": getattr(sc.ctx, "tertiary_ability_level", None),
        "forcas_passive_level": getattr(sc.ctx, "passive_ability_level", None),
        "baraqiel_tertiary": getattr(scb.ctx, "tertiary_ability", None),
        "baraqiel_tertiary_level": getattr(scb.ctx, "tertiary_ability_level", None),
        "has_extra_dmg": dmg is not None, "has_extra_block": blk is not None,
        "bonus": bonus,
        "block_source": (None if src is None
                         else {"chance": src.chance, "amount": src.amount,
                               "block_id": src.block_id}),
        "rpf_vars": list(relic_vars(state, baraqiel)),
    }


def _replay(rpc, rid, attacker_vis, victim_vis, board):
    """REPLAY-DIFF bit-exact d'UNE attaque normale : le natif joue, le port rejoue la MEME attaque
    sur la capture PRE-attaque avec le MT19937 dumpe.

    Rend les per-hit des deux cotes, les PV de la cible, l'etat du MT apres (natif ET port) et les
    `effectType` de la cible avant/apres (natif ET port). C'est ce dernier couple qui porte
    `RelicPowerFist` : ses deux `Maybe` posent `Pinned` / `Stunned` sur la cible."""
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and isinstance(ob, dict) and isinstance(snap, dict)):
        return {"error": "RPC etat pre-attaque KO"}
    att = next((u for u in (dv.get("units") or []) if u.get("visualId") == attacker_vis), None)
    vic = next((u for u in (dv.get("units") or []) if u.get("visualId") == victim_vis), None)
    if att is None or vic is None:
        return {"error": "attaquant/cible absents de decisionView"}
    norm = next((ab for ab in (att.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return {"error": "pas d'attaque normale sur %s" % attacker_vis}
    state = load_state(dv, ob, snap, board=board)
    aid, tid = att["id"], vic["id"]
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        return {"error": "cible introuvable offline"}
    hp_before = hc.hp
    eff_avant_natif = _effets_de(dv, tid)
    eff_avant_port = sorted(int(getattr(e, "effect_type", -1))
                            for e in (state.effects.by_unit.get(tid) or [])
                            if getattr(e, "effect_type", None) is not None)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng0):
        return {"error": "dumpRng KO"}
    state.rng = _seed_rng(rng0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"error": "attaque live REFUSEE : %s" % str(res)[:200]}
    live_ph, did_evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if (td.get("Target_Id") == tid and "Amount" in td
                and td.get("Active_Ability_Type") == norm["id"]):
            live_ph.append(td.get("Amount"))
            did_evade = did_evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid),
                      None)
    rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    eff_apres_natif = _effets_de(dv1, tid) if _ok(dv1) else None

    runner.apply(AttackUnitMessage(aid, tid))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    eff_apres_port = sorted(int(getattr(e, "effect_type", -1))
                            for e in (state.effects.by_unit.get(tid) or [])
                            if getattr(e, "effect_type", None) is not None)
    return {
        "attacker": attacker_vis, "victim": victim_vis, "aid": aid, "tid": tid,
        "hp_before": hp_before, "live_after": live_after, "off_after": off_after,
        "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"), "did_evade": did_evade,
        "eff_avant_natif": eff_avant_natif, "eff_apres_natif": eff_apres_natif,
        "eff_avant_port": eff_avant_port, "eff_apres_port": eff_apres_port,
        # L'OBSERVABLE DE LA TRANCHE, isole des autres effets de la cible : les deux seuls types
        # que `RelicPowerFist` peut poser. Comparer les LISTES ENTIERES serait fragile pour une
        # raison qui ne regarde pas ce port -- mesure #1009 : `1515 RangedSpecialist` DISPARAIT de
        # `decisionView.effects` cote natif quand l'attaquant devient adjacent (sa
        # `CreateActiveCondition` s'eteint) et le port, qui ne la modelise pas, le garde.
        "rpf_natif": sorted(x for x in (eff_apres_natif or ()) if x in (PINNED, STUNNED)),
        "rpf_port": sorted(x for x in eff_apres_port if x in (PINNED, STUNNED)),
        # L'ETAT DU MT19937 apres l'attaque, des DEUX cotes. `mti` seul suffit a voir une
        # consommation qui diverge ; `mt` le confirme quand le buffer a ete regenere.
        "mti_avant": rng0.get("mti"),
        "mti_apres_natif": (rng1 or {}).get("mti"), "mti_apres_port": state.rng.mti,
        "mt_egal": ((rng1 or {}).get("mt") == state.rng.mt),
        "call_count_port": state.rng.call_count,
    }


def run(rpc, avec_reliques: bool, build_runner=None, keep: bool = True,
        seed: str = SEED) -> dict:
    """Monte le regime (avec ou sans reliques), mesure OFFLINE la capture initiale, puis rejoue
    DEUX attaques : Forcas -> `Vehicle` (volet `MonsterSlayerOfCaliban`) et Baraqiel ->
    `BigTarget` (volet `RelicPowerFist`)."""
    from engine.entities.pathfinding.board import Board

    out = {"avec_reliques": bool(avec_reliques), "ok": False, "why": None}
    if build_runner is None:
        out["why"] = "ce probe exige la fabrique `build_runner` du harnais pytest"
        return out
    rid = build_runner(str(seed), extra=build_args(avec_reliques))["rid"]
    out["rid"] = rid
    out["seed"] = str(seed)

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo -- montage a reparer"
        return out
    board = Board(bg["tiles"], adjacency="native_sym")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and isinstance(ob, dict) and isinstance(snap, dict)):
        out["why"] = "RPC etat initial KO"
        return out
    out["offline"] = _mesures_offline(dv, ob, snap, board)
    if "error" in out["offline"]:
        out["why"] = out["offline"]["error"]
        return out
    # Ce que le NATIF publie comme effets du porteur : la preuve que le canal INIT est le bon.
    out["forcas_effects_natif"] = _effets_de(dv, out["offline"]["forcas"])

    out["msc"] = _replay(rpc, rid, FORCAS, VEHICLE_TARGET, board)
    out["rpf"] = _replay(rpc, rid, BARAQIEL, BIGTARGET_TARGET, board)
    for cle in ("msc", "rpf"):
        if "error" in out[cle]:
            out["why"] = "%s : %s" % (cle, out[cle]["error"])
            return out
    out["ok"] = True
    return out


def main():
    print("[1009] ce probe se joue depuis le harnais pytest (fabrique `build_runner`).")
    print("[1009] cf. tests/engine/runner/test_1009_reliques_dark_angels_live.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
