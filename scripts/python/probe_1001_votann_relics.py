#!/usr/bin/env python
"""Probe #1001 -- les DEUX reliques LEAGUES OF VOTANN, confrontees LIVE.

  * `BladeOfTheAncestors`   (`TriggeredAbilityType` 0x5d3 = 1491, `votanUthar` << Uthar >>)
  * `VolummsMasterArtifice` (`TriggeredAbilityType` 0x5d0 = 1488, `votanIronmaster` << Vynn >>)

Les DEUX porteurs sont HORS du pool rank 17 et sont du MEME roster : `write_relic_seed_bc` les
injecte ENSEMBLE (`augment`) et equipe les deux reliques -- UN seul catalogue pour les deux volets.
Le RE des cinq corps natifs vit dans les deux modules de port
(`engine/runner/operations/triggers/loki/{blade_of_the_ancestors,volumms_master_artifice}.py`).

VOLET `blade` -- L'OBSERVABLE EST UNE STAT, PAS UN JET
-----------------------------------------------------
`BladeOfTheAncestorsBuffEffect$$ApplyModification` pose DEUX `ChangeStat` (`CritChance` 9 /
`CritDamage` 10, `StatPart` 5 = MODIFICATION). On ne mesure AUCUN jet de critique : on mesure les
STATS elles-memes, que `combatSnapshot` rend par `IdunBattle.Entities.UnitExtensions$$GetStat`
(valeur EXACTE, deterministe). Le declencheur est la branche 2 du `CreateTrigger` : un HERO ALLIE
(ici `eldarRanger`) TUE une unite NORMALE.

⚠ `--unit-stat votanUthar:CritChance=0` n'est pas un confort : sans lui Uthar peut CRITER pendant
la mesure, et son propre `BladeOfTheAncestors_RemoveEffectAbility` (`On(9) & WasCrit`) enfilerait le
RESET dans le meme message -- le buff serait pose PUIS retire, et le delta lu vaudrait 0 pour une
raison qui n'a rien a voir avec le port.

Le NIVEAU de relique par defaut est **3**, et c'est ce qui separe le champ TERTIAIRE du champ
PASSIF : `extraCritChance[3] = 8` / `extraCritDmg[3] = 654`, la ou une lecture du niveau des PASSIFS
(50 sur tout runner normalise, CLAMPE au dernier palier) rendrait `10` / `877`. Au niveau 10 les
deux lectures coincideraient et la mesure ne separerait RIEN.

VOLET `volumm` -- LE COMPTEUR, PUIS LE SEUIL
-------------------------------------------
`On(0x30 = 48 UnitRepaired)` monte un compteur de persistent-data ; a la `nrOfRepairs`-ieme
reparation (7 aux niveaux 6-10), Vynn se soigne de `hpToHeal` et son ability active est RE-ARMEE.
Le vecteur natif est le MEME que celui d'`EcogSupport` (1487), le passif de kit du meme porteur :
l'apparition d'un E-COG apres une reparation est donc un TEMOIN INDEPENDANT que `UnitRepaired` a
bien ete emis cote natif.

Deux mesures, et la seconde est la seule non degeneree :
  A. UNE reparation  -> compteur = 1 < nrOfRepairs : natif ET port ne soignent RIEN, et l'E-COG
                        apparait (le vecteur a bien fire). Accord, mais en regime NUL.
  B. `--repairs N`   -> N reparations enchainees (une par tour de Vynn, + celle qu'un E-COG joue
                        quand le cap de 3 est atteint) : au franchissement du seuil, le natif
                        SOIGNE Vynn et RE-ARME son active ; le port doit faire les deux au MEME
                        rang. C'est le temoin NON NUL.

Reproduire (depuis scripts/python, session Frida chaude) :

    python probe_1001_votann_relics.py --volet blade
    python probe_1001_votann_relics.py --volet blade --level 10      # bras ou le tertiaire ne separe plus
    python probe_1001_votann_relics.py --volet volumm --repairs 1
    python probe_1001_votann_relics.py --volet volumm --repairs 8

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252). Discipline runner : `--state-file`
absolu, un runner a la fois, dispose en sortie.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]
sys.path.insert(0, str(_PYDIR))

UTHAR = "votanUthar"                 # ETAT 3 : hors catalogue -> `write_relic_seed_bc` l'injecte
VYNN = "votanIronmaster"             # idem
BLADE = "BladeOfTheAncestors"        # 0x5d3 = 1491, `allowedUnits = ['votanUthar']`
BLADE_ID = 1491
BLADE_EFFECT = 1489                  # 0x5d1 `BladeOfTheAncestors_Effect`
VOLUMM = "VolummsMasterArtifice"     # 0x5d0 = 1488, `allowedUnits = ['votanIronmaster']`
VOLUMM_ID = 1488
ECOG_SUPPORT_ID = 1487               # `TriggeredAbilityType.EcogSupport`, le passif de kit de Vynn

KILLER = "eldarRanger"               # HERO du pool -> `HasTrait(Actor@+0x40, 0x10 = Hero)`
VICTIM = "necroWarden"               # unite NORMALE -> `IsNormalUnit(Targets@+0x60)`
SURVIVOR = "orksNob"                 # 2e cible, PV PLEINS : Uthar la frappe SANS la tuer (volet reset)
SURVIVOR_HP = 900000
REPAIR_ALLY = "necroSpyder"          # allie MECANIQUE, cible de la reparation de Vynn
FOE = "necroWarden"

#: Reserve de PV du binome de reparation -- cf. `build_args_volumm` pour ce que chacune achete.
VYNN_MAX_HP = 60000
VYNN_START_HP = 30000
ALLY_MAX_HP = 900000

BOARD = "MC1_67"
SEED = "777"
RANK = 17
TERTIARY_HIERARCHY = 3               # `AddConfiguredAbilities` : `TryAdd(id, tertiaryState, 3)`

MUTATIONS = ("no-rail", "passive-level")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_1001-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def seed_bc_path(blade_level: int, volumm_level: int, no_ecog: bool = False) -> Path:
    """Seed BC augmente des DEUX porteurs Votann, chacun avec SA relique equipee.

    Les trois ecritures du montage (#237) sont faites ENSEMBLE par `equip_relic` (`TertiaryAbility`,
    `BC.Abilities.PassiveAbilities[<nom>]`, `TertiaryAbilityLevel >= 1`) -- les separer est ce qui
    produit un montage muet ou un << system error >> au cast. Le niveau ecrit ICI sera REECRIT a 50
    par `buildNormalizedBC` ; c'est `--equip-relic` qui re-pose le couple APRES la normalisation,
    donc le niveau JOUE est celui de la ligne de commande.

    `no_ecog` -- RETIRE `EcogSupport` (1487) des passifs de Vynn. CE N'EST PAS UN CONFORT : sans
    lui, chaque reparation de Vynn fait apparaitre un E-COG, et ces E-COGs REPARENT tout seuls
    pendant le tour de leur equipe (`PlayAutomaticUnits`). Le compteur de la relique monte alors de
    plusieurs crans par tour, par des evenements que rien de ce que j'observe ne date -- le RANG du
    franchissement devient incomptable, et c'est exactement lui qu'on veut confronter. Le retrait
    est DECLARE (`declare_graft`) : c'est une greffe en sens inverse, comme `restrict_abilities`."""
    import catalog_inject as CI
    seed = CI._load_seed(None)
    bc, _added, _ab, _unres = CI.augment(seed, [UTHAR, VYNN], RANK, 50)
    if no_ecog:
        for u in bc.get("Units") or []:
            if u.get("Id") == VYNN:
                kept = [p for p in (u.get("PassiveAbilities") or []) if int(p) != ECOG_SUPPORT_ID]
                u["PassiveAbilities"] = kept
        CI.declare_graft("restrict", VYNN, "passives sans EcogSupport (%d)" % ECOG_SUPPORT_ID)
    CI.equip_relic(bc, UTHAR, BLADE, blade_level)
    CI.equip_relic(bc, VYNN, VOLUMM, volumm_level)
    import host_inputs
    p = host_inputs.reject_data_output(_out_dir() / "seed-bc-votann.json", "probe_1001")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    return Path(p)


def build_args_blade(level: int, seed_bc: Path, reset: bool = False) -> list[str]:
    """`reset = False` -- volet POSE : Uthar a `CritChance = 0`, donc il ne peut PAS criter et son
    `BladeOfTheAncestors_RemoveEffectAbility` reste muet ; le delta de stats ne porte QUE la pose.

    `reset = True` -- volet RESET : Uthar a `CritChance = 100`, il crite a coup sur. La CHANCE de
    crit est alors PLAFONNEE (`GetClampedValue`), donc seul `critDamage` reste lisible -- et c'est
    lui qu'on suit. La 2e cible (`SURVIVOR`, PV PLEINS) existe pour qu'Uthar ait quelqu'un a
    frapper SANS le tuer : un kill par Uthar ajouterait une pile (branche 2 du `CreateTrigger`) en
    plus du reset, et melangerait les deux mesures.

    ⚠ On n'utilise PAS `--hp-target 1` (qui mettrait TOUTES les cibles a 1 PV, `SURVIVOR` compris) :
    la victime est fragilisee PAR UNITE."""
    return ["--board", BOARD, "--seed-bc", str(seed_bc), "--no-ai",
            "--p-units", "%s,%s" % (UTHAR, KILLER), "--a-units", "%s,%s" % (VICTIM, SURVIVOR),
            "--equip-relic", "%s:%s:%d" % (UTHAR, BLADE, level),
            "--dmg-target", "1",
            "--unit-stat", "%s:RemainingHealth=1" % (VICTIM,),
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (SURVIVOR, SURVIVOR_HP, SURVIVOR_HP),
            "--unit-stat", "%s:CritChance=%d" % (UTHAR, 100 if reset else 0)]


def build_args_volumm(level: int, seed_bc: Path) -> list[str]:
    return ["--board", BOARD, "--seed-bc", str(seed_bc), "--no-ai",
            "--p-units", "%s,%s" % (VYNN, REPAIR_ALLY), "--a-units", FOE,
            "--equip-relic", "%s:%s:%d" % (VYNN, VOLUMM, level),
            "--dmg-target", "1",
            # Vynn TRES blesse : le manque doit depasser `hpToHeal`, sinon `MaxFillUp` sature et le
            # delta de PV ne dirait plus rien du montant. Mais PAS a 1000 PV : mesure du
            # 2026-08-13, l'ennemi frappe a 1000 et l'a TUE au 3e tour, avant le seuil.
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (VYNN, VYNN_MAX_HP, VYNN_START_HP),
            # L'allie a une reserve de PV ENORME et n'en porte que 1000 : sans ca, la PREMIERE
            # reparation le remplit, et `RepairUnitOperation$$Execute` sort par son gate
            # `repaired < 1 && cleansed < 1 && !HasFlag(target, 0x18)` AVANT d'emettre
            # `On(0x30 = UnitRepaired)` -- les reparations suivantes ne compteraient plus RIEN.
            "--unit-stat", "%s:Health=%d,RemainingHealth=1000" % (REPAIR_ALLY, ALLY_MAX_HP)]


def _build_subprocess(argv_extra: list[str]) -> tuple[int, Path]:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *argv_extra]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-800:]))
    return json.loads(state.read_text())["runnerId"], state


def _rl_duel(state: Path, *args: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, "rl_duel.py", *args, "--state-file", str(state)]
    return subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _tertiary_rows(rpc, rid: int) -> list:
    """Entrees `TriggeredAbility` de hierarchie 3 (`raw[0]` = `AbilityName`, `raw[10]` = hierarchie ;
    `level`/`mult` viennent de `+0x20`/`+0x24`). Meme lecture que `probe_357_relic_rail`."""
    res = rpc("unitAbilityStates", {"runnerId": rid}, 60) or {}
    out = []
    for u in res.get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == TERTIARY_HIERARCHY:
                out.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                            "level": t.get("level"), "mult": t.get("mult")})
    return out


def _snap_stats(rpc, rid: int) -> dict:
    """`combatSnapshot.units[].stats` indexe par `visualId` -- la lecture EXACTE de `GetStat`."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60) or {}
    out = {}
    for u in snap.get("units") or []:
        vis = ((u.get("unitConfig") or {}).get("visualId")) or u.get("visualId")
        if vis:
            out[vis] = dict(u.get("stats") or {})
    return out


def _live_units(rpc, rid: int) -> dict:
    return {u["squadId"]: u
            for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
            if not u.get("isDead")}


def _move_to(rpc, rid, sq, tile, board):
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)


def _drive_adjacent(rpc, rid, board, sq_mover, anchor_tile) -> bool:
    """DEPLACE `sq_mover` sur une tuile LIBRE adjacente a `anchor_tile`. On CONDUIT les positions --
    la geometrie de spawn n'est jamais une raison de ne pas mesurer."""
    U = _live_units(rpc, rid)
    mt = board.id_at(U[sq_mover]["col"], U[sq_mover]["row"])
    if mt is not None and mt in board.neighbours(anchor_tile):
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    cands = [n for n in board.neighbours(anchor_tile)
             if n in board.by_id and board.walkable(n) and n not in occ]
    cands.sort(key=lambda n: abs(board.coord(n)[0] - U[sq_mover]["col"])
               + abs(board.coord(n)[1] - U[sq_mover]["row"]))
    for n in cands:
        _move_to(rpc, rid, sq_mover, n, board)
        U2 = _live_units(rpc, rid)
        if sq_mover not in U2:
            return False
        m2 = board.id_at(U2[sq_mover]["col"], U2[sq_mover]["row"])
        if m2 is not None and m2 in board.neighbours(anchor_tile):
            return True
    return False


def _normal_attack_type(dv: dict, sq: int):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(sq):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal" and ab.get("id") is not None:
                    return int(ab["id"])
    return None


def _ability_ids(dv: dict, sq: int) -> list:
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(sq):
            return [{"id": ab.get("id"), "kind": ab.get("kind"), "name": ab.get("name")}
                    for ab in (u.get("abilities") or [])]
    return []


# --------------------------------------------------------------------------- port (rejeu offline)

def _patch_passive_level(mod):
    """MUTATION `passive-level` : `triggered_ability_state` rend TOUJOURS le couple PASSIF (l'etat
    d'AVANT le rail #357 sur l'axe MAGNITUDE). Le niveau des passifs vaut 50 sur tout runner
    normalise -> la relique rendrait le DERNIER palier quel que soit son niveau reel."""
    saved = mod.triggered_ability_state

    def _passive_only(state, unit_id, ability_name):
        from engine.runner.components import StatsComponent
        e = state.get_entity(unit_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        if ctx is None:
            return (None, 100)
        return (getattr(ctx, "passive_ability_level", None),
                int(getattr(ctx, "ability_variables_multiplier", 100) or 100))
    mod.triggered_ability_state = _passive_only
    return lambda: setattr(mod, "triggered_ability_state", saved)


def _patch_effect_passive_level():
    """MEME mutation, cote EFFET : `_relic_ability_state` rend le couple PASSIF. C'est l'autre
    moitie du meme mode de panne -- la magnitude vit dans la classe d'effet, pas dans l'ability."""
    from engine.entities.effects.loki import votann as V
    saved = V._relic_ability_state

    def _passive_only(stats_ctx, ability_name):
        if stats_ctx is None:
            return (None, 100)
        return (getattr(stats_ctx, "passive_ability_level", None),
                int(getattr(stats_ctx, "ability_variables_multiplier", 100) or 100))
    V._relic_ability_state = _passive_only
    return lambda: setattr(V, "_relic_ability_state", saved)


def _by_vis(state, vis):
    from engine.runner.components import StatsComponent
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _port_blade(dv, ob, snap, board, ability_states, mutate=None, with_reset=False) -> dict:
    """Rejoue `On(0 = UnitDeath)` OFFLINE sur la capture, victime marquee MORTE, `actor` = le tueur.

    `ability_states=False` = le canal #357 REFUSE -> le rail ne voit pas la relique (l'etat d'avant).
    ⚠ `False`, pas `None` : depuis #363, `None` veut dire AUTO et re-tirerait le payload."""
    from engine.entities.stats import StatType
    from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
    from engine.runner.operations.triggers.dispatch.move_death import unit_death_triggers
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    car, kil, vic = _by_vis(state, UTHAR), _by_vis(state, KILLER), _by_vis(state, VICTIM)
    if car is None or kil is None or vic is None:
        return {"error": "unites absentes offline (%s/%s/%s)" % (car, kil, vic)}
    sc = state.get_entity(car).get_component(StatsComponent)
    ve = state.get_entity(vic)
    ve.get_component(UnitComponent).alive = False        # la victime est DEJA morte (patron #317)
    vh = ve.get_component(HealthComponent)
    if vh is not None:
        vh.hp = 0
    cc0 = sc.ctx.stat(int(StatType.CRIT_CHANCE))
    cd0 = sc.ctx.stat(int(StatType.CRIT_DAMAGE))
    undos = []
    if mutate == "passive-level":
        # Cote BLADE la magnitude ne vit PAS dans l'ability (elle n'a aucun `ConfigVar`) : elle vit
        # dans `BladeOfTheAncestorsBuffEffect$$ApplyModification`. Le seul point a muter est donc
        # `_relic_ability_state`, cote EFFET.
        undos = [_patch_effect_passive_level()]
    try:
        out = unit_death_triggers(state, vic, kil) or []
    finally:
        for u in reversed(undos):
            u()
    ev = [e for e in out if isinstance(e, dict) and e.get("relic") == BLADE]
    n_eff = 0
    if state.effects is not None:
        n_eff = sum(1 for e in (state.effects.by_unit.get(int(car)) or [])
                    if not e.consumed and int(e.effect_type) == BLADE_EFFECT)
    cc1 = sc.ctx.stat(int(StatType.CRIT_CHANCE))
    cd1 = sc.ctx.stat(int(StatType.CRIT_DAMAGE))
    reset = None
    if with_reset:
        # LE RESET, bout en bout et par les VECTEURS DU PORT : `On(9 = Attack)` avec `WasCrit`
        # (`finish_attack_triggers`) ENFILE, et c'est le drain de `state.pending_triggered_abilities`
        # -- la borne du message top-level, `process_pending_triggered_abilities` -- qui execute la
        # branche `Custom`. Un `RemoveEffect` immediat serait un COLLAPSE INLINE, pas ce port.
        from engine.runner.operations.triggers.dispatch.attack import finish_attack_triggers
        from engine.runner.operations.triggers.dispatch.pending import (
            process_pending_triggered_abilities)
        tgt = _by_vis(state, SURVIVOR)
        queued = finish_attack_triggers(state, car, tgt if tgt is not None else vic,
                                        ranged=False, is_crit=True) or []
        drained = process_pending_triggered_abilities(state) or []
        left = 0
        if state.effects is not None:
            left = sum(1 for e in (state.effects.by_unit.get(int(car)) or [])
                       if not e.consumed and int(e.effect_type) == BLADE_EFFECT)
        reset = {"queued": [q for q in queued if isinstance(q, dict) and q.get("relic") == BLADE],
                 "drained": [d for d in drained if isinstance(d, dict) and d.get("relic") == BLADE],
                 "stacks_left": left,
                 "cc_delta": sc.ctx.stat(int(StatType.CRIT_CHANCE)) - cc1,
                 "cd_delta": sc.ctx.stat(int(StatType.CRIT_DAMAGE)) - cd1,
                 "cc_back_to_base": sc.ctx.stat(int(StatType.CRIT_CHANCE)) == cc0,
                 "cd_back_to_base": sc.ctx.stat(int(StatType.CRIT_DAMAGE)) == cd0}
    return {"events": len(ev), "stacks": n_eff, "reset": reset,
            "cc_delta": cc1 - cc0,
            "cd_delta": cd1 - cd0,
            "tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "level": getattr(sc.ctx, "tertiary_ability_level", None),
            "mult": getattr(sc.ctx, "tertiary_ability_variables_multiplier", None),
            "passive_level": getattr(sc.ctx, "passive_ability_level", None)}


def _port_volumm(dv, ob, snap, board, ability_states, repairs: int, mutate=None) -> dict:
    """Rejoue `On(0x30 = 48 UnitRepaired)` OFFLINE, `repairs` fois, `caster = Vynn`.

    Le compteur vit dans le `PersistentDataComponent` du port : N drains suffisent a franchir le
    seuil, sans monter N tours de runner. C'est le TEMOIN NON NUL cote port."""
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.triggers.dispatch.repair import unit_repaired_triggers
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    vynn, ally = _by_vis(state, VYNN), _by_vis(state, REPAIR_ALLY)
    if vynn is None or ally is None:
        return {"error": "unites absentes offline (%s/%s)" % (vynn, ally)}
    sc = state.get_entity(vynn).get_component(StatsComponent)
    hc = state.get_entity(vynn).get_component(HealthComponent)
    hp0 = int(hc.hp) if hc is not None else None
    undos = []
    if mutate == "passive-level":
        from engine.runner.operations.triggers.loki import volumms_master_artifice as VA
        undos = [_patch_passive_level(VA)]
    steps = []
    try:
        for _ in range(int(repairs)):
            out = unit_repaired_triggers(state, vynn, ally) or []
            ev = [e for e in out if isinstance(e, dict) and e.get("relic") == VOLUMM]
            steps.append(ev[0] if ev else None)
    finally:
        for u in reversed(undos):
            u()
    healed_at = next((i + 1 for i, s in enumerate(steps) if s and s.get("healed")), None)
    return {"steps": steps, "healed_at": healed_at,
            "hp_delta": (int(hc.hp) - hp0) if hc is not None else None,
            "tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "level": getattr(sc.ctx, "tertiary_ability_level", None),
            "mult": getattr(sc.ctx, "tertiary_ability_variables_multiplier", None)}


# --------------------------------------------------------------------------- volets

def run_blade(rpc, level: int = 3, keep: bool = False, build_runner=None,
              reset: bool = False) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    out: dict = {"volet": "reset" if reset else "blade", "level": level, "reset": bool(reset),
                 "ok": False, "why": None}
    out["expected"] = {
        "cc": int(ability_var(BLADE, "extraCritChance", level, multiplier_pct=100) or 0),
        "cd": int(ability_var(BLADE, "extraCritDmg", level, multiplier_pct=100) or 0)}
    out["expected_clamped"] = {
        "cc": int(ability_var(BLADE, "extraCritChance", 50, multiplier_pct=100) or 0),
        "cd": int(ability_var(BLADE, "extraCritDmg", 50, multiplier_pct=100) or 0)}

    sbc = seed_bc_path(level, 10)
    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args_blade(level, sbc, reset))["rid"]
    else:
        rid, _st = _build_subprocess(build_args_blade(level, sbc, reset))
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")
        U = _live_units(rpc, rid)
        sq = {u.get("visualId"): s for s, u in U.items()}
        for vis in (UTHAR, KILLER, VICTIM):
            if vis not in sq:
                out["why"] = "%s absent du live" % vis
                return out

        rows = _tertiary_rows(rpc, rid)
        out["tertiary_rows"] = rows
        mine = [r for r in rows if r["abilityId"] == BLADE_ID]
        if not mine:
            out["why"] = ("aucune entree de hierarchie 3 pour %s (id %d) : la relique n'est PAS "
                          "montee -- le montage #237 a echoue" % (BLADE, BLADE_ID))
            return out
        out["mounted"] = mine[0]

        vt = board.id_at(U[sq[VICTIM]]["col"], U[sq[VICTIM]]["row"])
        if not _drive_adjacent(rpc, rid, board, sq[KILLER], vt):
            out["why"] = "%s ne peut pas atteindre le contact de %s" % (KILLER, VICTIM)
            return out

        stats0 = _snap_stats(rpc, rid)
        out["stats_before"] = {k: stats0.get(k) for k in (UTHAR,)}
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)

        # --- PORT : trois lectures de la MEME capture, c'est leur CONTRASTE qui prouve -----------
        out["port"] = _port_blade(dv, ob, snap, board, uas, with_reset=reset)
        out["port_no_rail"] = _port_blade(dv, ob, snap, board, False)
        out["port_passive_level"] = _port_blade(dv, ob, snap, board, uas, mutate="passive-level")

        # --- NATIF : le kill REEL par le HERO allie ----------------------------------------------
        nat = _normal_attack_type(dv, sq[KILLER])
        if nat is None:
            out["why"] = "%s n'expose aucune attaque normale" % KILLER
            return out
        act = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sq[KILLER], "targetId": sq[VICTIM],
            "abilityType": nat}}, 120)
        out["attack_ack"] = {k: act.get(k) for k in ("ok", "error", "mutated")} \
            if isinstance(act, dict) else {"raw": str(act)[:200]}
        if isinstance(act, dict) and act.get("ok") is False:
            out["why"] = "attaque REFUSEE par le natif : %s" % (out["attack_ack"],)
            return out
        post = rpc("observeBattle", {"runnerId": rid}, 40).get("units") or []
        by_sq = {u["squadId"]: u for u in post}
        out["victim_dead"] = bool(by_sq.get(sq[VICTIM], {}).get("isDead"))
        stats1 = _snap_stats(rpc, rid)
        out["stats_after"] = {k: stats1.get(k) for k in (UTHAR,)}
        b, a = stats0.get(UTHAR) or {}, stats1.get(UTHAR) or {}
        out["native_delta"] = {
            "cc": int(a.get("critChance", 0)) - int(b.get("critChance", 0)),
            "cd": int(a.get("critDamage", 0)) - int(b.get("critDamage", 0))}
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        out["native_effects"] = [e for u in (dv2.get("units") or [])
                                 if int(u.get("id", -1)) == int(sq[UTHAR])
                                 for e in (u.get("effects") or [])]

        # --- volet RESET : Uthar CRITE sur une cible qui SURVIT -> le buff doit tomber ------------
        if reset:
            if SURVIVOR not in sq:
                out["why"] = "%s absent du live -- pas de cible a criter" % SURVIVOR
                return out
            st = board.id_at(U[sq[SURVIVOR]]["col"], U[sq[SURVIVOR]]["row"])
            if not _drive_adjacent(rpc, rid, board, sq[UTHAR], st):
                out["why"] = "%s ne peut pas atteindre le contact de %s" % (UTHAR, SURVIVOR)
                return out
            dv3 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            nat_u = _normal_attack_type(dv3, sq[UTHAR])
            if nat_u is None:
                out["why"] = "%s n'expose aucune attaque normale" % UTHAR
                return out
            stats_pre = _snap_stats(rpc, rid)
            act2 = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": sq[UTHAR], "targetId": sq[SURVIVOR],
                "abilityType": nat_u}}, 120)
            out["crit_ack"] = {k: act2.get(k) for k in ("ok", "error")} \
                if isinstance(act2, dict) else {"raw": str(act2)[:200]}
            post2 = _live_units(rpc, rid)
            out["survivor_alive"] = sq[SURVIVOR] in post2
            stats_post = _snap_stats(rpc, rid)
            bb, aa = stats_pre.get(UTHAR) or {}, stats_post.get(UTHAR) or {}
            out["reset_delta"] = {
                "cc": int(aa.get("critChance", 0)) - int(bb.get("critChance", 0)),
                "cd": int(aa.get("critDamage", 0)) - int(bb.get("critDamage", 0))}
            out["stats_reset"] = {"before": bb, "after": aa}
            base = _snap_stats(rpc, rid)
            out["cd_back_to_base"] = (int((base.get(UTHAR) or {}).get("critDamage", 0))
                                      == int((stats0.get(UTHAR) or {}).get("critDamage", 0)))
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                    # pragma: no cover - diagnostic
                pass


def run_volumm(rpc, level: int = 10, repairs: int = 1, keep: bool = False,
               build_runner=None, no_ecog: bool = True) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    out: dict = {"volet": "volumm", "level": level, "repairs": repairs,
                 "no_ecog": bool(no_ecog), "ok": False, "why": None}
    out["expected"] = {
        "nr": int(ability_var(VOLUMM, "nrOfRepairs", level, multiplier_pct=100) or 0),
        "hp": int(ability_var(VOLUMM, "hpToHeal", level, multiplier_pct=100) or 0)}
    out["expected_clamped"] = {
        "nr": int(ability_var(VOLUMM, "nrOfRepairs", 50, multiplier_pct=100) or 0),
        "hp": int(ability_var(VOLUMM, "hpToHeal", 50, multiplier_pct=100) or 0)}

    sbc = seed_bc_path(3, level, no_ecog=no_ecog)
    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args_volumm(level, sbc))["rid"]
        state = None
    else:
        rid, state = _build_subprocess(build_args_volumm(level, sbc))
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")
        U = _live_units(rpc, rid)
        sq = {u.get("visualId"): s for s, u in U.items()}
        for vis in (VYNN, REPAIR_ALLY):
            if vis not in sq:
                out["why"] = "%s absent du live" % vis
                return out

        rows = _tertiary_rows(rpc, rid)
        out["tertiary_rows"] = rows
        mine = [r for r in rows if r["abilityId"] == VOLUMM_ID]
        if not mine:
            out["why"] = ("aucune entree de hierarchie 3 pour %s (id %d) : la relique n'est PAS "
                          "montee" % (VOLUMM, VOLUMM_ID))
            return out
        out["mounted"] = mine[0]

        at = board.id_at(U[sq[REPAIR_ALLY]]["col"], U[sq[REPAIR_ALLY]]["row"])
        if not _drive_adjacent(rpc, rid, board, sq[VYNN], at):
            out["why"] = "%s ne peut pas atteindre le contact de %s" % (VYNN, REPAIR_ALLY)
            return out

        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        out["vynn_abilities"] = _ability_ids(dv, sq[VYNN])
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)

        # --- PORT : N drains sur la MEME capture (le compteur est port-side) ----------------------
        out["port"] = _port_volumm(dv, ob, snap, board, uas, max(int(repairs), out["expected"]["nr"]))
        out["port_no_rail"] = _port_volumm(dv, ob, snap, board, False,
                                           max(int(repairs), out["expected"]["nr"]))
        out["port_passive_level"] = _port_volumm(dv, ob, snap, board, uas,
                                                 max(int(repairs), out["expected"]["nr"]),
                                                 mutate="passive-level")

        # --- NATIF : `repairs` reparations enchainees, une par tour de Vynn ----------------------
        rep_ab = next((a for a in out["vynn_abilities"]
                       if a.get("kind") != "normal" and a.get("id") == 28), None)
        if rep_ab is None:
            rep_ab = next((a for a in out["vynn_abilities"] if a.get("id") == 28), None)
        if rep_ab is None:
            out["why"] = ("Vynn n'expose pas l'ability derivee `Repair` (28) : %s"
                          % (out["vynn_abilities"],))
            return out
        native, seen, _turn_trace = [], 0, []
        for i in range(int(repairs)):
            pre = _live_units(rpc, rid)
            if sq[VYNN] not in pre or sq[REPAIR_ALLY] not in pre:
                native.append({"i": i + 1, "why": "un des deux a disparu du live",
                               "vivants": sorted(u.get("visualId") for u in pre.values()),
                               "tour": _turn_trace[-1] if _turn_trace else None})
                break
            missing = int(pre[sq[VYNN]]["hpMax"]) - int(pre[sq[VYNN]]["hp"])
            act = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": sq[VYNN], "targetId": sq[REPAIR_ALLY],
                "abilityType": 28}}, 120)
            post = _live_units(rpc, rid)
            # COMPTE des reparations REELLEMENT emises par cette action : toute unite AUTRE que Vynn
            # dont les PV MONTENT en est une (celle de Vynn, plus celle qu'un E-COG joue quand le cap
            # de 3 est atteint -- `ECogSupportAbility$$CreateBehaviour`, branche `else`). Vynn est
            # exclu du compte parce que SA montee de PV est justement le SOIN qu'on mesure.
            ups = [s for s, u in post.items()
                   if s != sq[VYNN] and s in pre and int(u["hp"]) > int(pre[s]["hp"])]
            seen += len(ups)
            vd = (int((post.get(sq[VYNN]) or {}).get("hp", 0))
                  - int((pre.get(sq[VYNN]) or {}).get("hp", 0)))
            native.append({
                "i": i + 1,
                "ack": {k: act.get(k) for k in ("ok", "error")} if isinstance(act, dict) else None,
                "repairs_seen": len(ups), "cumul": seen,
                "vynn_missing_before": missing, "vynn_delta": vd,
                "vynn_hp": (post.get(sq[VYNN]) or {}).get("hp"),
                "ally_hp": (post.get(sq[REPAIR_ALLY]) or {}).get("hp"),
                "units": len(post)})
            if state is not None and i + 1 < int(repairs):
                e = _rl_duel(state, "act", "endturn")
                t = _rl_duel(state, "aiturn")
                _turn_trace.append({"i": i + 1,
                                    "endturn": (e.stdout or e.stderr or "")[-200:].strip(),
                                    "aiturn": (t.stdout or t.stderr or "")[-300:].strip()})
        out["native"] = native
        out["turn_trace"] = _turn_trace
        out["native_repairs_seen"] = seen
        heal = next((r for r in native if (r.get("vynn_delta") or 0) > 0), None)
        out["native_heal"] = heal
        out["native_healed_at"] = heal["i"] if heal else None
        out["native_healed_cumul"] = heal["cumul"] if heal else None
        out["native_heal_amount"] = (min(int(heal["vynn_delta"]), out["expected"]["hp"])
                                     if heal else 0)
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                    # pragma: no cover - diagnostic
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="#1001 -- les deux reliques Votann")
    ap.add_argument("--volet", choices=("blade", "reset", "volumm"), default="blade")
    ap.add_argument("--level", type=int, default=None)
    ap.add_argument("--repairs", type=int, default=1)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--with-ecog", action="store_true",
                    help="volumm : GARDE `EcogSupport` -- le rang du seuil devient incomptable")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    if a.volet in ("blade", "reset"):
        r = run_blade(rpc, level=(3 if a.level is None else a.level), keep=a.keep,
                      reset=(a.volet == "reset"))
        print("runner=%s level=%s ok=%s why=%s" % (r.get("rid"), r.get("level"), r.get("ok"),
                                                   r.get("why")))
        print("attendu  = %s   (palier clampe, ce que le niveau PASSIF rendrait = %s)"
              % (r.get("expected"), r.get("expected_clamped")))
        if not r.get("ok"):
            return 1
        print("monte    : %s" % (r.get("mounted"),))
        print("[NATIF]  victime morte=%s | delta stats Uthar = %s"
              % (r.get("victim_dead"), r.get("native_delta")))
        print("[NATIF]  effets sur Uthar = %s" % (r.get("native_effects"),))
        print("[PORT]   %s" % (r.get("port"),))
        print("[PORT sans rail]     stacks=%s cc=%s cd=%s"
              % (r["port_no_rail"].get("stacks"), r["port_no_rail"].get("cc_delta"),
                 r["port_no_rail"].get("cd_delta")))
        print("[PORT niveau PASSIF] cc=%s cd=%s"
              % (r["port_passive_level"].get("cc_delta"),
                 r["port_passive_level"].get("cd_delta")))
        if r.get("reset"):
            print("[NATIF reset] ack=%s survivant=%s delta apres crit = %s | retour a la base = %s"
                  % (r.get("crit_ack"), r.get("survivor_alive"), r.get("reset_delta"),
                     r.get("cd_back_to_base")))
            print("[PORT  reset] %s" % (r["port"].get("reset"),))
        return 0

    r = run_volumm(rpc, level=(10 if a.level is None else a.level), repairs=a.repairs,
                   keep=a.keep, no_ecog=not a.with_ecog)
    print("runner=%s level=%s repairs=%s ok=%s why=%s"
          % (r.get("rid"), r.get("level"), r.get("repairs"), r.get("ok"), r.get("why")))
    print("attendu  = %s   (palier clampe = %s)" % (r.get("expected"), r.get("expected_clamped")))
    if not r.get("ok"):
        return 1
    print("monte    : %s" % (r.get("mounted"),))
    print("abilities Vynn : %s" % (r.get("vynn_abilities"),))
    print("[PORT]   healed_at=%s hp_delta=%s tertiary=%s level=%s"
          % (r["port"].get("healed_at"), r["port"].get("hp_delta"),
             r["port"].get("tertiary"), r["port"].get("level")))
    print("[PORT sans rail]     healed_at=%s" % (r["port_no_rail"].get("healed_at"),))
    print("[PORT niveau PASSIF] healed_at=%s" % (r["port_passive_level"].get("healed_at"),))
    print("[NATIF]  healed_at(action)=%s cumul_reparations=%s delta=%s reparations_vues=%s"
          % (r.get("native_healed_at"), r.get("native_healed_cumul"),
             (r.get("native_heal") or {}).get("vynn_delta"), r.get("native_repairs_seen")))
    for row in (r.get("native") or []):
        print("   %s" % (row,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
