"""probe #302 -- la route de decision a cibles TUILE : inventaire + etage manquant de 1169.

DEUX volets, independants.

## Volet OFFLINE (`--inventory`) : qui est concerne

Balaye le bit `TargetingRule.TargetIsTile` (bit 6) sur les `TARGETING_OPTIONS` de
`ABILITY_CLASSES`, et croise avec les routes de DECISION reellement portees. Le bit est celui que
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` teste pour aiguiller vers
`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` plutot que
`...$$GetUnitsInRange` -- c'est le SEUL aiguillage tuile du natif (cf. `case-302` §1.1), et il est
deja mirrore par `TargetingOptions.is_tile_targeting`
(= `IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting`, `rules >> 6 & 1`).

Ce volet ne dit RIEN des 162 `ActiveAbilityType` hors registre : le bit ne s'y lit qu'au `.ctor`.
Le compte imprime est donc « sur les abilities PORTEES », et le probe le dit.

## Volet LIVE (`--stage`) : l'etage que `probe_27_4g_plagueburst_route.py` n'avait pas mesure

Ce probe-la concluait « le natif ne genere pas l'action » de `aiDryRunAllUnits` (8/8 sur 69). Mais
son etage 1 (`abilityTargets` a 58 cibles tuile) passe par la branche `manualAbility` du RPC
(`frida/hooks/features/ai-step/rpc-targeting.ts`), qui court-circuite `unitAbilityTypes` : les 58
tuiles prouvent que `GetValidTargets` produit un domaine, PAS que l'ability soit UTILISABLE par le
caster greffe. Tant que cet etage n'est pas mesure, « le natif refuse » et « le harnais n'a pas
rendu l'ability utilisable » sont indiscernables -- et porter une route sur cette base serait
porter contre un oracle qu'on n'a pas lu.

`--stage` lit donc, sur le runner deja monte par `probe_27_4g_plagueburst_route.py --build` :

1. l'entree 1169 de `decisionView(allAbilities: true).units[caster].abilities` -- `usable`,
   `cooldown`, `disabled`, `kind` (c'est la vue de `unitAbilityTypes`, la MEME source que
   `...ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder` consomme) ;
2. le domaine NON force : `abilityTargets` SANS `abilityType`, qui n'enumere que les abilities que
   le caster porte reellement -- 1169 y figure-t-elle ?
3. la correspondance `(col,row) -> tileEntityId` sur les cibles tuile rendues, via `boardGraph`
   (c'est `engine.ai.context._board_tile_ids`, et c'est l'id qu'`applyOneAction` attend).

Usage (depuis scripts/python, ASCII only) :
    python probe_302_tile_target_route.py --inventory
    python probe_27_4g_plagueburst_route.py --build          # monte le runner
    python probe_302_tile_target_route.py --stage
    python rl_duel.py dispose --state-file <LOGS>/rs_pb_route.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
STATE = LOGS / "rs_pb_route.json"

PLAGUEBURST = 1169


# --------------------------------------------------------------------------- inventaire (offline)

def inventory() -> int:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.active_ability_type import ActiveAbilityType

    # Routes de DECISION tuile deja portees (chacune emet un `target` = tileEntityId).
    routed = {}
    try:
        from engine.playbook.noncomparable.dark_talon_strike import DarkTalonStrikePlaybook  # noqa
        routed[1092] = "NC bespoke dark_talon_strike.py"
    except Exception:
        pass
    try:
        from engine.playbook.noncomparable.master_of_the_tutelaries import (  # noqa
            MasterOfTheTutelariesPlaybook)
        routed[1096] = "NC bespoke master_of_the_tutelaries.py"
    except Exception:
        pass
    try:
        from engine.playbook.noncomparable.the_quickening import TheQuickeningPlaybook  # noqa
        routed[1151] = "NC bespoke the_quickening.py"
    except Exception:
        pass
    try:
        from engine.playbook.excruciating_frequencies import (  # noqa
            excruciating_frequencies_candidates)
        routed[1197] = "Comparable bespoke excruciating_frequencies.py"
    except Exception:
        pass

    rows = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None or not opts.is_tile_targeting:
            continue
        try:
            nm = ActiveAbilityType(aid).name
        except Exception:
            nm = cls.__name__
        rows.append((aid, nm, int(opts.rules), routed.get(aid, "")))

    print("=== bit TargetingRule.TargetIsTile (bit 6) sur les abilities PORTEES ===")
    print("ABILITY_CLASSES              : %d" % len(ABILITY_CLASSES))
    print("portant TargetIsTile         : %d" % len(rows))
    print("dont route de DECISION tuile : %d" % sum(1 for r in rows if r[3]))
    print("")
    print("  %-6s %-32s %-18s %s" % ("id", "ability", "rules", "route de decision"))
    for aid, nm, rules, route in rows:
        print("  %-6d %-32s %-18s %s" % (aid, nm, hex(rules), route or "-- AUCUNE --"))
    print("")
    print("NON COUVERT par ce balayage : les ActiveAbilityType hors ABILITY_CLASSES.")
    print("  Le bit ne s'y lit qu'au <X>Ability$$.ctor -- lecture au decompile, hors perimetre #302.")
    return 0


# --------------------------------------------------------------------------------- etage (live)

def stage() -> int:
    import probe_27_3_live as L
    from engine.ai import context as C

    rid = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    caster = None
    for u in (dv.get("units") or []):
        if u.get("visualId") == "deathTyphus":
            caster = u
            break
    if caster is None:
        print("caster deathTyphus absent du runner %d -- monter le montage 4g d'abord" % rid)
        return 2
    cid = caster.get("id")
    print("runner=%d caster=u%s (deathTyphus)" % (rid, cid))

    # (1) etat d'ability tel que `unitAbilityTypes` le voit (source de GetUnitAbilitiesInOrder)
    print("\n[1] decisionView(allAbilities).abilities du caster :")
    seen = False
    for ab in (caster.get("abilities") or []):
        mark = " <== 1169" if ab.get("id") == PLAGUEBURST else ""
        if ab.get("id") == PLAGUEBURST:
            seen = True
        print("    id=%-6s kind=%-10s usable=%-5s cooldown=%-5s disabled=%-5s name=%s%s"
              % (ab.get("id"), ab.get("kind"), ab.get("usable"), ab.get("cooldown"),
                 ab.get("disabled"), ab.get("name"), mark))
    print("    -> 1169 PRESENTE dans le kit vu par le RPC : %s" % ("OUI" if seen else "NON"))

    # (2) domaine NON force : abilityTargets SANS abilityType
    at = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": cid, "allAbilities": True}])
    print("\n[2] abilityTargets SANS abilityType (enumeration du kit REEL) :")
    found = None
    for u in (at.get("units") or []):
        if u.get("unitId") != cid:
            continue
        for a in (u.get("abilities") or []):
            kinds = {}
            for t in (a.get("targets") or []):
                kinds[t.get("kind")] = kinds.get(t.get("kind"), 0) + 1
            print("    ab=%-6s usable=%-5s targetCount=%-4s kinds=%s"
                  % (a.get("abilityId"), a.get("usable"), a.get("targetCount"), kinds))
            if a.get("abilityId") == PLAGUEBURST:
                found = a
    print("    -> 1169 enumeree SANS forcage : %s" % ("OUI" if found else "NON"))

    # (3) correspondance (col,row) -> tileEntityId sur le domaine FORCE
    forced = L._rpc("abilityTargets", [{"runnerId": rid, "casterId": cid,
                                        "abilityType": PLAGUEBURST}])
    tiles = []
    for u in (forced.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != PLAGUEBURST:
                continue
            for t in (a.get("targets") or []):
                if t.get("kind") == "tile":
                    tl = t.get("tile") or {}
                    tiles.append((tl.get("col"), tl.get("row")))
    tid_by_pos = C._board_tile_ids(
        lambda m, b, to=40: L._rpc(m, [dict(b)]), rid)
    resolved = [(p, tid_by_pos.get(p)) for p in tiles]
    miss = [p for p, i in resolved if i is None]
    print("\n[3] correspondance (col,row) -> tileEntityId (boardGraph) :")
    print("    cibles tuile = %d | resolues = %d | NON resolues = %d"
          % (len(tiles), len(tiles) - len(miss), len(miss)))
    print("    echantillon = %s" % resolved[:6])
    if miss:
        print("    MANQUANTES = %s" % miss[:10])
    print("    -> targetId RENDU par abilityTargets sur kind='tile' : %s"
          % ("oui" if any((t.get("targetId") is not None)
                          for u in (forced.get("units") or [])
                          for a in (u.get("abilities") or [])
                          for t in (a.get("targets") or [])
                          if t.get("kind") == "tile") else "NON (contrat : tile{col,row} seul)"))
    return 0


# ------------------------------------------------------------------ confrontation live (decision)

def build_ready(hp_target: int, state_name: str) -> int:
    """Monte le montage 4g (greffe de 1169 sur `deathTyphus`, board MC1_67, positions crafttees) PUIS
    **avance de deux fins de tour**.

    Ces deux `endturn` ne sont PAS cosmetiques : `PlagueburstMortar` arrive avec
    `RemainingCooldownTurns = 1` (mesure `--stage`), donc au tour du build l'ability est INDISPONIBLE
    et le natif ne peut pas la proposer -- c'est ce qui avait fait lire « le natif ne genere pas
    l'action » a `probe_27_4g_plagueburst_route.py`. Le 1er `endturn` rend la main a l'adversaire, le
    2e revient au caster avec `cooldown = None`. Les positions crafttees survivent (aucune unite ne
    joue : on termine les tours a vide)."""
    import probe_27_4g_plagueburst_route as G

    G.STATE = LOGS / state_name
    rid = G.build(hp_target)
    for _ in range(4):
        _duel(["act", "endturn"], G.STATE, rid)
        cid, cd, to_act = _caster_state(rid)
        if cid is not None and cd in (None, 0) and cid in (to_act or []):
            return rid
    raise SystemExit("cooldown de 1169 jamais purge sur le runner %d" % rid)


def _duel(args, state: Path, rid: int) -> None:
    import subprocess
    subprocess.run([sys.executable, "rl_duel.py"] + args
                   + ["--state-file", str(state), "--runner", str(rid)],
                   cwd=str(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _caster_state(rid: int):
    import probe_27_3_live as L
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    c = next((u for u in (dv.get("units") or []) if u.get("visualId") == "deathTyphus"), None)
    if c is None:
        return None, None, None
    ab = next((a for a in (c.get("abilities") or []) if a.get("id") == PLAGUEBURST), None)
    return c.get("id"), (ab or {}).get("cooldown"), dv.get("toActivate")


def native(rid: int, caster: int) -> tuple:
    """Le choix du natif : `(abilityType, targetId)` de l'`ActiveAbilityMessage` propose."""
    import probe_27_3_live as L
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return (m.get("abilityType"), m.get("targetId"))
    return (None, None)


def engine(rid: int, caster: int) -> dict:
    """Decision MOTEUR sur le MEME etat + les deux bras de necessite + la decomposition par etage."""
    import engine_validate as EV
    import probe_27_3_live as L
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)              # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    pb = PB.REGISTRY[PLAGUEBURST]

    targets = pb.eligible_targets(ctx, PLAGUEBURST)
    per_target = [(t, pb.calculate_custom_utility(ctx, ctx.origin, t, PLAGUEBURST)) for t in targets]
    # VUE ROUGE : ce que `eligible_targets` rendait AVANT la tranche (domaine UNITE force). C'est la
    # mesure de l'etat d'avant le correctif, pas une hypothese sur lui.
    orig_dom = type(pb).targets_tiles
    type(pb).targets_tiles = lambda self, aid: False
    try:
        targets_unit_domain = pb.eligible_targets(ctx, PLAGUEBURST)
    finally:
        type(pb).targets_tiles = orig_dom

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, tile, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    # VERROU : `_best_attack` ne peut structurellement PAS rendre 1169 (rankCount = 0 partout).
    from engine.ai.action_generators import ComparableAbilityGenerator
    best = ComparableAbilityGenerator()._best_attack(ctx)
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "targets": targets, "per_target": per_target,
            "targets_unit_domain": targets_unit_domain,
            "best_attack_ability": (best[3] if best else None)}


def measure(hp_target: int, state_name: str) -> dict:
    rid = build_ready(hp_target, state_name)
    caster, cd, _ = _caster_state(rid)
    return {"rid": rid, "caster": caster, "cooldown": cd,
            "native": native(rid, caster), "engine": engine(rid, caster)}


def dispose(rid: int) -> None:
    import probe_27_3_live as L
    try:
        L._rpc("disposeRunner", [{"runnerId": rid}])
    except Exception:                                       # noqa: BLE001
        pass


def decision(hp_target: int) -> int:
    r = measure(hp_target, "rs_302_a.json")
    try:
        print("runner=%d caster=u%s cooldown=%s" % (r["rid"], r["caster"], r["cooldown"]))
        print("natif   = %s" % (r["native"],))
        e = r["engine"]
        print("moteur  = %s (to=%s)" % (e["on"], e["to"]))
        print("zero    = %s   (custom force a 0)" % (e["zero"],))
        print("noroute = %s   (registre non-attaque vide)" % (e["noroute"],))
        print("best_attack rend = %s" % e["best_attack_ability"])
        print("cibles eligibles = %d tuiles" % len(e["targets"]))
        vals = sorted({c for _t, c in e["per_target"]})
        print("custom distinct  = %s" % vals)
        print("ACCORD = %s" % ("OUI" if e["on"] == r["native"] else "NON"))
    finally:
        dispose(r["rid"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--decision", action="store_true")
    ap.add_argument("--hp-target", type=int, default=400000)
    a = ap.parse_args()
    if a.inventory:
        return inventory()
    if a.stage:
        return stage()
    if a.decision:
        return decision(a.hp_target)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
