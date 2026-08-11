#!/usr/bin/env python3
"""#919 -- le passif `IconOfObstinacy` (`TriggeredAbilityType` 0x610 = 1552) d'`astarLysander`.

RE complete : en tete d'`engine/entities/effects/loki/icon_of_obstinacy.py` (les deux effets et le
selecteur partage) et d'`engine/runner/operations/triggers/loki/icon_of_obstinacy.py` (les deux
poseurs). Ce probe MESURE ; les assertions vivent dans
`tests/engine/runner/test_919_icon_of_obstinacy_live.py`.

MONTAGE -- il DISCRIMINE les DEUX gates separement, et c'est le point : un accord obtenu avec un
seul voisin non qualifiant ne prouverait rien.

    u_lysander   astarLysander    (3,3)  PORTEUR                  -> attendu : buff
    u_terminator darkaTerminator  (3,4)  TerminatorArmour, dist 1 -> attendu : buff
    u_plain      ultraTitus       (2,3)  SANS le trait,   dist 1  -> attendu : RIEN  (gate TRAIT)
    u_far        thousTerminator  (0,0)  TerminatorArmour, dist 4 -> attendu : RIEN  (gate DISTANCE)

`astarLysander` est HORS du pool par defaut -> injection catalogue (`catalog_inject.
write_augmented_seed_bc`, cf. `docs/rl/case-270d-trait-hors-enum.md`), et les positions sont
FORCEES (`--place`) : la geometrie de spawn ne decide de rien ici.

ETAGES
  0  registres et litteraux (offline)
  1  la formule, au chiffre (offline, contre le gameconfig vivant)
  2  NATIF : les quatre `FinishUnitTurn` sans attaque, puis `statModSources(FixedArmor)`
  3  PORT  : le MEME etat rejoue offline -> memes porteurs, memes montants
  4  MUTANT : le gate de trait retire -> l'etage 3 DOIT rougir (sinon le temoin est aveugle)

ASCII only dans les sorties (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
#: Les sorties de run vont sous le `logs/` de la RACINE du depot, pas sous `scripts/python/logs/`
#: (#935) : `probe_273` ne reconnait comme SORTIE que les racines de premier niveau
#: (`_OUTPUT_ROOTS = {"logs", "app"}`), donc un `PYDIR / "logs"` y est compte comme une ENTREE
#: gitignoree lue depuis la racine -- etape 1 ROUGE.
LOGS = Path(__file__).resolve().parents[2] / "logs"
sys.path.insert(0, str(PYDIR))

import catalog_inject                                            # noqa: E402
import hexgeo                                                    # noqa: E402
import rl_collect_batch as L                                     # noqa: E402  (foyer `_rpc`)

BOARD = "MC1_67"
SEED = "777"
CARRIER = "astarLysander"
TERMINATOR = "darkaTerminator"          # UnitTrait.TerminatorArmour, sera ADJACENT
PLAIN = "ultraTitus"                    # PAS de TerminatorArmour, sera ADJACENT
FAR = "thousTerminator"                 # UnitTrait.TerminatorArmour, sera LOIN
FOE = "ultraApothecary"

PLACES = {CARRIER: (3, 3), TERMINATOR: (3, 4), PLAIN: (2, 3), FAR: (0, 0)}
ABILITY = "IconOfObstinacy"
EXTRA_ARMOR_NAME = "IconOfObstinacy_ExtraArmor"
EXTRA_DMG_NAME = "IconOfObstinacy_ExtraDmg"


def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result") or {}


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(state: Path) -> int:
    """Montage : seed BC augmente (le porteur est hors pool) + positions FORCEES."""
    state.parent.mkdir(parents=True, exist_ok=True)
    if state.exists():
        state.unlink()
    bc = state.parent / ("seedbc-919-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CARRIER])
    try:
        args = ["build", "--seed", SEED, "--board", BOARD, "--no-ai",
                "--seed-bc", str(bc), "--state-file", str(state),
                "--p-units", ",".join((CARRIER, TERMINATOR, PLAIN, FAR)), "--a-units", FOE]
        for uid, (c, r) in PLACES.items():
            args += ["--place", "%s:%d,%d" % (uid, c, r)]
        p = _duel(args)
        if not state.exists():
            raise SystemExit("build KO (MONTAGE, pas une mesure) : "
                             + (p.stderr or p.stdout or "")[-900:])
    finally:
        bc.unlink(missing_ok=True)
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def capture(rid) -> dict:
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180),
            "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 90),
            "tm": rpc("tileMeta", {"runnerId": rid}, 90),
            "bg": rpc("boardGraph", {"runnerId": rid}, 90)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def ids_by_visual(cap) -> dict:
    return {u.get("visualId"): int(u.get("id")) for u in (cap["dec"].get("units") or [])}


def stats_by_id(cap) -> dict:
    return {int(u["entityId"]): u.get("stats") or {} for u in (cap["snap"].get("units") or [])}


def native_fixed_armor_mod(rid, uid) -> "int | None":
    """`statModSources(unit, StatType.FixedArmor = 16)` -- le canal per-source du natif."""
    sm = rpc("statModSources", {"runnerId": rid, "unitId": int(uid), "statType": 16}, 60)
    for u in (sm.get("units") or []):
        m = (u.get("mods") or {}).get("fixedArmor")
        if m is not None:
            return int(m.get("total") or 0)
    return None


def expected_amount(block_damage: int, level: int, multiplier_pct: int) -> int:
    """`GetCurrentExtraArmour` = `extraArmor[level] + PercentageOf(BlockDamage, chance)`."""
    from engine.entities.effects.loki.icon_of_obstinacy import (ICON_OF_OBSTINACY, CHANCE_VAR,
                                                                EXTRA_ARMOR_VAR, _percentage_of)
    from engine.entities.effects.magnitude import ability_var
    flat = int(ability_var(ICON_OF_OBSTINACY, EXTRA_ARMOR_VAR, level,
                           multiplier_pct=multiplier_pct) or 0)
    pct = int(ability_var(ICON_OF_OBSTINACY, CHANCE_VAR, level, multiplier_pct=multiplier_pct) or 0)
    return flat + _percentage_of(int(block_damage), pct)


# ------------------------------------------------------------------ etage 0 : registres (offline)
def etage0() -> dict:
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.stats import StatType
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.playbook.non_owner import load_playbook_non_owner
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS

    out = {
        "triggers": [c.__name__ for c in (ABILITY_TRIGGERS.get(ABILITY) or [])],
        "init_owner": list(ABILITY_INIT_OWNER_EFFECTS.get(ABILITY) or []),
        "effect_classes": {n: (EFFECT_CLASSES.get(n).__name__ if EFFECT_CLASSES.get(n) else None)
                           for n in (EXTRA_ARMOR_NAME, EXTRA_DMG_NAME)},
        "playbook_owner": type(load_playbook(int(TriggeredAbilityType.IconOfObstinacy))).__name__,
        "playbook_non_owner":
            type(load_playbook_non_owner(int(TriggeredAbilityType.IconOfObstinacy))).__name__,
        "litteraux": {
            "TriggeredAbilityType.IconOfObstinacy": int(TriggeredAbilityType.IconOfObstinacy),
            "EffectType.IconOfObstinacy_ExtraArmor": int(EffectType.IconOfObstinacy_ExtraArmor),
            "EffectType.IconOfObstinacy_ExtraDmg": int(EffectType.IconOfObstinacy_ExtraDmg),
            "UnitTrait.TerminatorArmour": int(UnitTrait.TerminatorArmour),
            "EventTriggerType.UnitFinishedTurn": int(EventTriggerType.UnitFinishedTurn),
            "EventTriggerType.SpecificAbilityInit": int(EventTriggerType.SpecificAbilityInit),
            "StatType.FixedArmor": int(StatType.FIXED_ARMOR),
            "StatType.BlockDamage": int(StatType.BLOCK_DAMAGE),
        },
    }
    print("[0] ABILITY_TRIGGERS[%s]            = %s" % (ABILITY, out["triggers"]))
    print("[0] ABILITY_INIT_OWNER_EFFECTS[%s]  = %s" % (ABILITY, out["init_owner"]))
    print("[0] EFFECT_CLASSES                       = %s" % out["effect_classes"])
    print("[0] playbook OWNER / NON-OWNER           = %s / %s"
          % (out["playbook_owner"], out["playbook_non_owner"]))
    print("[0] litteraux                            = %s" % json.dumps(out["litteraux"]))
    return out


# --------------------------------------------------------------- etage 1 : la formule (offline)
def etage1() -> dict:
    from engine.entities.effects.loki.icon_of_obstinacy import (IconOfObstinacyExtraArmorEffect,
                                                                IconOfObstinacyExtraDmgEffect)
    from engine.entities.stats import StatType

    class _Ctx:
        def __init__(self, bd):
            self.bd = bd

        def get_stat(self, st, part=0, source=None):
            return self.bd if int(st) == int(StatType.BLOCK_DAMAGE) else 0

    rows = []
    for bd in (0, 1000, 2349):
        e = IconOfObstinacyExtraArmorEffect(EXTRA_ARMOR_NAME)
        e.ability_level, e.ability_variables_multiplier = 50, 180
        mods = e.applied_stat_mods(_Ctx(bd))
        d = IconOfObstinacyExtraDmgEffect(EXTRA_DMG_NAME)
        d.ability_level, d.ability_variables_multiplier = 50, 180
        eb = d.create_effect_damage_bonus_for_attack(att_ctx={"owner_block_damage": bd})
        rows.append({"block_damage": bd,
                     "armour": (mods[0][1] if mods else 0),
                     "damage": (int(eb.value) if eb is not None else 0),
                     "attendu": expected_amount(bd, 50, 180)})
        print("[1] BD=%-6d armour=%-6d damage=%-6d attendu(armour)=%d"
              % (bd, rows[-1]["armour"], rows[-1]["damage"], rows[-1]["attendu"]))
    return {"rows": rows}


# ------------------------------------------------------------------ etage 2 : NATIF (live)
def etage2(rid, cap) -> dict:
    """Les quatre unites cloturent leur tour SANS attaquer -> le trigger doit fire pour les seules
    unites du set. `act finish` = `FinishUnitTurnOperation` sans terminaison forcee."""
    by_vis = ids_by_visual(cap)
    for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
        uid = by_vis.get(vis)
        if uid is None:
            raise SystemExit("MONTAGE : %s absent du decisionView" % vis)
        _duel(["act", "finish", "--unit", str(uid), "--state-file", str(STATE)])
    after = capture(rid)
    st = stats_by_id(after)
    eff = {int(u["id"]): [e.get("name") for e in (u.get("effects") or [])]
           for u in (after["dec"].get("units") or [])}
    pos = {int(u["id"]): (u["pos"]["col"], u["pos"]["row"])
           for u in (after["dec"].get("units") or []) if u.get("pos")}
    rows = {}
    for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
        uid = by_vis[vis]
        rows[vis] = {"id": uid, "pos": pos.get(uid),
                     "dist": (hexgeo.distance(pos[by_vis[CARRIER]], pos[uid])
                              if uid in pos and by_vis[CARRIER] in pos else None),
                     "block_damage": int((st.get(uid) or {}).get("blockDamage") or 0),
                     "fixed_armor_mod": native_fixed_armor_mod(rid, uid),
                     "a_effet": EXTRA_ARMOR_NAME in (eff.get(uid) or [])}
        print("[2] %-16s u%-3d pos=%-8s dist=%-4s BD=%-6d fixedArmorMod=%-6s effet=%s"
              % (vis, uid, rows[vis]["pos"], rows[vis]["dist"], rows[vis]["block_damage"],
                 rows[vis]["fixed_armor_mod"], rows[vis]["a_effet"]))
    return {"rows": rows, "cap": after}


# ------------------------------------------------------------------- etage 3 : PORT (offline)
def etage3(cap_avant, by_vis) -> dict:
    """Le MEME etat, AVANT les quatre fins de tour, rejoue par le port : `FinishUnitTurnOperation`
    pour chaque unite, puis lecture des effets et des stat-mods materialises."""
    from engine.runner.components import StatsComponent
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    st, _board = offline_state(cap_avant)
    for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
        FinishUnitTurnOperation.execute(st, by_vis[vis], forced=False)
    rows = {}
    for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
        uid = by_vis[vis]
        effs = [e for e in (st.effects.by_unit.get(uid) or []) if not e.consumed]
        names = [e.name for e in effs]
        ent = st.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        mods = []
        for e in effs:
            if e.name == EXTRA_ARMOR_NAME:
                mods = e.applied_stat_mods(getattr(sc, "ctx", None)) or []
        rows[vis] = {"id": uid, "a_effet": EXTRA_ARMOR_NAME in names,
                     "fixed_armor_mod": (int(mods[0][1]) if mods else None)}
        print("[3] %-16s u%-3d effet=%-6s fixedArmorMod=%s"
              % (vis, uid, rows[vis]["a_effet"], rows[vis]["fixed_armor_mod"]))
    return {"rows": rows}


# ------------------------------------------------ etage 5 : le gate ATTAQUE (live, 2e montage)
def etage5(state: Path) -> dict:
    """`AmountIsZero(TimesAttackMadeThisTurn(Actor@0x40, null))` -- le TROISIEME terme du trigger,
    que le montage principal laisse en regime DEGENERE (personne n'y attaque).

    Montage : le porteur et un ami Terminator sont COLLES a un ennemi ; l'ami ATTAQUE puis clot son
    tour, le porteur clot le sien SANS attaquer. Attendu : buff sur le porteur SEUL."""
    if state.exists():
        state.unlink()
    bc = state.parent / ("seedbc-919atk-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CARRIER])
    try:
        p = _duel(["build", "--seed", SEED, "--board", BOARD, "--no-ai",
                   "--seed-bc", str(bc), "--state-file", str(state),
                   "--p-units", "%s,%s" % (CARRIER, TERMINATOR), "--a-units", FOE,
                   "--place", "%s:3,3" % CARRIER, "--place", "%s:3,4" % TERMINATOR,
                   "--a-place", "%s:2,4" % FOE])
        if not state.exists():
            raise SystemExit("build KO (MONTAGE) : " + (p.stderr or p.stdout or "")[-700:])
    finally:
        bc.unlink(missing_ok=True)
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    cap = capture(rid)
    by_vis = ids_by_visual(cap)
    foe = by_vis[FOE]
    hp_avant = {int(u["entityId"]): int((u.get("stats") or {}).get("health") or 0)
                for u in (cap["snap"].get("units") or [])}
    # L'ami Terminator ATTAQUE (normale) puis clot ; le porteur clot SANS attaquer.
    # `--ability` attend l'ID de l'ability, pas son nom : on le LIT dans le `decisionView` de
    # l'unite (l'attaque normale est une ability CONCRETE, propre a chaque unite).
    atk_id = None
    for u in (cap["dec"].get("units") or []):
        if int(u.get("id")) != by_vis[TERMINATOR]:
            continue
        for ab in (u.get("abilities") or []):
            if str(ab.get("name") or "").endswith("NormalAttack"):
                atk_id = ab.get("id") if isinstance(ab.get("id"), int) else ab.get("abilityId")
    if atk_id is None:
        print("[5] MONTAGE KO -- aucune ability `*NormalAttack` dans le decisionView de %s"
              % TERMINATOR)
        _duel(["dispose", "--state-file", str(state)])
        return {"natif": {}, "port": {}, "ok": None, "montage": "KO"}
    # `act ability` prend le lanceur par `--caster` (`--unit` ne le renseigne PAS : la trace rend
    # `uNone->u<cible>` et le RPC echoue) -- lu au premier montage KO, pas devine.
    p_atk = _duel(["act", "ability", "--caster", str(by_vis[TERMINATOR]),
                   "--ability", str(int(atk_id)), "--target", str(foe),
                   "--state-file", str(state)])
    mid = capture(rid)
    hp_apres = {int(u["entityId"]): int((u.get("stats") or {}).get("health") or 0)
                for u in (mid["snap"].get("units") or [])}
    degat = hp_avant.get(foe, 0) - hp_apres.get(foe, 0)
    print("[5] CONTROLE DE MONTAGE : degat inflige a l'ennemi = %d" % degat)
    if degat <= 0:
        # Un ROUGE sur un montage qui n'a pas mordu ne mesure RIEN. On le DIT et on s'arrete.
        print("[5] MONTAGE KO -- l'attaque n'a pas eu lieu (portee ? action refusee ?). "
              "verbatim : %s" % ((p_atk.stderr or p_atk.stdout or "")[-400:].replace("\n", " | ")))
        _duel(["dispose", "--state-file", str(state)])
        return {"natif": {}, "port": {}, "ok": None, "montage": "KO"}
    _duel(["act", "finish", "--unit", str(by_vis[TERMINATOR]), "--state-file", str(state)])
    _duel(["act", "finish", "--unit", str(by_vis[CARRIER]), "--state-file", str(state)])
    after = capture(rid)
    eff = {int(u["id"]): [e.get("name") for e in (u.get("effects") or [])]
           for u in (after["dec"].get("units") or [])}
    rows = {}
    for vis in (CARRIER, TERMINATOR):
        uid = by_vis[vis]
        rows[vis] = {"id": uid, "a_effet": EXTRA_ARMOR_NAME in (eff.get(uid) or []),
                     "fixed_armor_mod": native_fixed_armor_mod(rid, uid)}
        print("[5] %-16s u%-3d a_attaque=%-6s effet=%-6s fixedArmorMod=%s"
              % (vis, uid, vis == TERMINATOR, rows[vis]["a_effet"], rows[vis]["fixed_armor_mod"]))
    # Le PORT, sur le MEME etat : on rejoue les deux `FinishUnitTurn` depuis la capture d'AVANT,
    # apres avoir enregistre l'attaque de l'ami (le compteur `+0x24` que lit `TimesAttackMadeThisTurn`).
    from engine.runner.components import register_attack_made
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    st, _b = offline_state(cap)
    register_attack_made(st, by_vis[TERMINATOR], foe)      # `ActorStatisticsComponent+0x24 += 1`
    for vis in (TERMINATOR, CARRIER):
        FinishUnitTurnOperation.execute(st, by_vis[vis], forced=False)
    port = {}
    for vis in (CARRIER, TERMINATOR):
        uid = by_vis[vis]
        names = [e.name for e in (st.effects.by_unit.get(uid) or []) if not e.consumed]
        port[vis] = EXTRA_ARMOR_NAME in names
        print("[5] %-16s PORT effet=%s" % (vis, port[vis]))
    ok = all(bool(rows[v]["a_effet"]) == bool(port[v]) for v in (CARRIER, TERMINATOR))
    print("[5] verdict gate ATTAQUE : %s" % ("ACCORD" if ok else "ECART"))
    _duel(["dispose", "--state-file", str(state)])
    return {"natif": rows, "port": port, "ok": ok}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU et UNIQUE du state-file du runner")
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    a = ap.parse_args()

    global STATE
    STATE = Path(a.state_file) if a.state_file else (LOGS / "st-919.json")

    etage0()
    etage1()
    if a.offline_only:
        return 0

    rid = build(STATE)
    print("[montage] runner=%d board=%s seed=%s places=%s" % (rid, BOARD, SEED, PLACES))
    try:
        cap_avant = capture(rid)
        by_vis = ids_by_visual(cap_avant)
        nat = etage2(rid, cap_avant)
        prt = etage3(cap_avant, by_vis)
        ok = True
        for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
            n, p = nat["rows"][vis], prt["rows"][vis]
            same_carrier = bool(n["a_effet"]) == bool(p["a_effet"])
            same_amount = (n["fixed_armor_mod"] or 0) == (p["fixed_armor_mod"] or 0)
            ok = ok and same_carrier and same_amount
            print("[4] %-16s porteur natif=%-6s port=%-6s | montant natif=%-6s port=%-6s | %s"
                  % (vis, n["a_effet"], p["a_effet"], n["fixed_armor_mod"], p["fixed_armor_mod"],
                     "OK" if (same_carrier and same_amount) else "ECART"))
        print("[verdict] %s" % ("ACCORD natif/port sur les quatre" if ok else "ECART -- voir [4]"))
        _duel(["dispose", "--state-file", str(STATE)])
        g = etage5(STATE.with_name(STATE.stem + "-atk.json"))
        if g["ok"] is None:
            print("[verdict] etage 5 NON MESURE (montage KO) -- rien n'en est conclu")
            return 0 if ok else 1
        return 0 if (ok and g["ok"]) else 1
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", str(STATE)])


if __name__ == "__main__":
    raise SystemExit(main())
