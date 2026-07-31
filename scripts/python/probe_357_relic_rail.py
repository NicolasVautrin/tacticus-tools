#!/usr/bin/env python
"""Probe #357 -- LE RAIL DE LA RELIQUE EQUIPEE, confronte LIVE sur `DawnBlade`.

CE QUE #237 A LAISSE OUVERT. Le montage d'une relique est ecrit et mesure
(`docs/rl/case-237-relique-forcee.md`) : `rl_duel build --equip-relic` amene en bataille une unite
avec une relique qu'elle n'equipe pas au seed. Mais RIEN cote Python ne LISAIT ce champ -- le rail
COMBAT (`triggers/dispatch/core.py::collect_triggered_abilities`) derivait le kit declenche du
gameconfig, qui ne connait que les reliques cablees EN DUR sur des npc (`units.<id>.relicAbilities`),
jamais l'item EQUIPE, qui est un etat JOUEUR. Une relique montee etait donc INERTE cote port, sans
erreur ni trace : le trigger n'etait jamais inscrit.

POURQUOI `DawnBlade` (1501) ET PAS UNE AUTRE DES 32
  * son effet est mesurable A L'ETAT -- `Repair(self, self, Get(hpToHeal[lvl]), ForRepair)` sur un
    kill en melee : les PV du porteur montent, on lit un ENTIER, pas un modificateur noye dans une
    plage de degat ;
  * son behaviour est DEJA porte (#317, `triggers/loki/dawn_blade.py`), donc ce probe mesure LE RAIL
    et rien d'autre -- pas un port d'ability neuf qui melangerait deux sources d'ecart ;
  * son porteur legitime (`tauFarsight`, `allowedUnits = ['tauFarsight']`) est en ETAT 3 (hors
    catalogue), donc le montage exerce AUSSI la voie d'injection catalogue -- le cas le plus complet.

LES TROIS MESURES, ET CE QUE CHACUNE SEPARE

  A. RAIL          natif vs port AVEC le canal vs port SANS le canal.
                   Sans le canal, le port repare 0 : c'est l'etat d'avant #357, et c'est ce qui
                   etablit que la mesure A n'est pas un vert par accident.
  B. NIVEAU        deux runners, MEME montage, niveaux de relique DIFFERENTS (8 et 3).
                   Le natif rend `hpToHeal[8]` puis `hpToHeal[3]` ; un port qui lirait le niveau des
                   PASSIFS (50 sur tout runner normalise) rendrait DEUX FOIS `hpToHeal[10]`.
                   C'est la seule mesure qui separe `TertiaryAbilityLevel` de `PassiveAbilityLevel`.
  C. MULTIPLICATEUR  `TertiaryAbilityVariablesMultiplierPercentage` (+0x78) lu de DEUX sources
                   independantes -- l'`AbilityState` MONTE (`unitAbilityStates`, `+0x24`) et la
                   CONFIG (`combatSnapshot.unitConfig.tertiaryAbilityVariablesMultiplier`) -- plus
                   le multiplicateur ACTIF/PASSIF (+0x74), qui est un AUTRE champ et ne vaut pas
                   la meme chose. Tranche l'ecart « 200 au seed contre 100 synthetise » laisse
                   ouvert par #237.

LE VECTEUR. On ne TUE pas la victime cote port : on draine `On(UnitDeath = 0)` sur un etat ou elle
est deja `alive = False` -- meme choix que `probe_301` / `probe_317` (le montage teste le TRIGGER,
pas le pipeline de degat qui l'emet). Cote natif, en revanche, le kill est REEL : `applyAction`
`attack`, et l'observable est le delta de PV du porteur AVANT/APRES ce seul coup.

Reproduire :

    cd scripts/python
    python probe_357_relic_rail.py                     # mesure A + C au niveau 8
    python probe_357_relic_rail.py --level 3           # l'autre bras de la mesure B
    python probe_357_relic_rail.py --mutate passive-level   # contre-epreuve NIVEAU

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

CARRIER = "tauFarsight"          # ETAT 3 : hors catalogue -> `write_augmented_seed_bc`
RELIC = "DawnBlade"              # `TriggeredAbilityType` 0x5dd = 1501, `allowedUnits=[tauFarsight]`
RELIC_ID = 1501
VICTIM = "orksNob"
BOARD = "MC1_67"
SEED = "777"
RANK = 17
CARRIER_HP = 2000                # tres blesse : le manque doit depasser `hpToHeal` (sinon MaxFillUp)
TERTIARY_HIERARCHY = 3           # `AddConfiguredAbilities` : `TryAdd(id, tertiaryState, 3)`

MUTATIONS = ("no-rail", "passive-level")
REGIMES = ("melee", "ranged", "fullhp")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_357-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def seed_bc_path() -> Path:
    """Seed BC augmente de `tauFarsight` (ETAT 3). Ecrit dans `logs/`, jamais `data/`."""
    import catalog_inject as CI
    p, _added, _ab = CI.write_augmented_seed_bc(_out_dir() / "seed-bc-farsight.json",
                                                [CARRIER], rank=RANK)
    return Path(p)


def build_args(level: int, seed_bc: Path, regime: str = "melee") -> list[str]:
    """Arguments `rl_duel build` du montage (hors `--seed`/`--state-file`).

    `--equip-relic` pose les TROIS ecritures APRES la normalisation -> le niveau joue est EXACTEMENT
    celui demande (`buildNormalizedBC` ecraserait a 50 s'il etait pose avant, cf. #237 §4).
    `--hp-target 1` rend le kill CERTAIN d'un seul coup ; `--dmg-target 1` empeche la victime de
    rendre des degats, pour que le delta de PV du porteur ne porte QUE la reparation.

    Regime `fullhp` : le porteur garde ses PV PLEINS -- on ne le blesse PAS. C'est le regime qui
    exerce `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (`IsDamagedUnit`), le gate que
    le `CreateTrigger` de `DawnBlade_HealAbility` ne porte PAS lui-meme."""
    argv = ["--board", BOARD, "--seed-bc", str(seed_bc),
            "--p-units", CARRIER, "--a-units", VICTIM,
            "--equip-relic", "%s:%s:%d" % (CARRIER, RELIC, level),
            "--hp-target", "1", "--dmg-target", "1"]
    if regime != "fullhp":
        argv += ["--unit-stat", "%s:RemainingHealth=%d" % (CARRIER, CARRIER_HP)]
    return argv


def _build_subprocess(level: int, seed_bc: Path, regime: str = "melee") -> int:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(level, seed_bc, regime)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return json.loads(state.read_text())["runnerId"]


def _move_to(rpc, rid, sq, tile, board):
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)


def _drive_adjacent(rpc, rid, board, live, sq_mover, anchor_tile) -> bool:
    """DEPLACE `sq_mover` sur une tuile LIBRE adjacente a `anchor_tile`. On CONDUIT les positions --
    la geometrie de spawn n'est jamais une raison de ne pas mesurer."""
    U = live()
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
        U2 = live()
        if sq_mover not in U2:
            return False
        m2 = board.id_at(U2[sq_mover]["col"], U2[sq_mover]["row"])
        if m2 is not None and m2 in board.neighbours(anchor_tile):
            return True
    return False


def _drive_at_distance(rpc, rid, board, live, sq_mover, anchor_tile, dist: int) -> bool:
    """POSE `sq_mover` a une distance hex EXACTE d'`anchor_tile`. Regime `ranged` : le porteur tire
    a d=2 (sa portee d'arme) -- le kill n'est alors PAS une defaite en MELEE, et
    `IdunBattleLogic.Entities.DSLTriggers$$IsDefeatedByMeleeAttack` doit refuser."""
    import hexgeo
    ap = board.coord(anchor_tile)
    U = live()
    if hexgeo.distance((U[sq_mover]["col"], U[sq_mover]["row"]), ap) == dist:
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    cands = [t for t in board.by_id
             if board.walkable(t) and t not in occ
             and hexgeo.distance(board.coord(t), ap) == dist]
    cands.sort(key=lambda t: abs(board.coord(t)[0] - U[sq_mover]["col"])
               + abs(board.coord(t)[1] - U[sq_mover]["row"]))
    for t in cands[:16]:
        _move_to(rpc, rid, sq_mover, t, board)
        U2 = live()
        if sq_mover not in U2:
            return False
        if hexgeo.distance((U2[sq_mover]["col"], U2[sq_mover]["row"]), ap) == dist:
            return True
    return False


def _tertiary_rows(rpc, rid: int) -> list:
    """Entrees `TriggeredAbility` de hierarchie 3 (`raw` = 12 x int32 depuis `+0x10` :
    `raw[0]` = `AbilityName`, `raw[10]` = hierarchie ; `level`/`mult` viennent de `+0x20`/`+0x24`)."""
    res = rpc("unitAbilityStates", {"runnerId": rid}, 60) or {}
    out = []
    for u in res.get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == TERTIARY_HIERARCHY:
                out.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                            "level": t.get("level"), "mult": t.get("mult")})
    return out


def _patch_passive_level():
    """MUTATION `passive-level` : `triggered_ability_state` rend TOUJOURS le couple PASSIF.

    C'est l'etat du port AVANT #357 sur l'axe MAGNITUDE -- le niveau des passifs vaut 50 sur tout
    runner normalise, donc la relique rendait `hpToHeal[10]` quel que soit son niveau reel."""
    from engine.runner.operations.triggers import base as B
    from engine.runner.operations.triggers.loki import dawn_blade as DB
    saved = DB.triggered_ability_state

    def _passive_only(state, unit_id, ability_name):
        e = state.get_entity(unit_id)
        from engine.runner.components import StatsComponent
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        if ctx is None:
            return (None, 100)
        return (getattr(ctx, "passive_ability_level", None),
                int(getattr(ctx, "ability_variables_multiplier", 100) or 100))
    DB.triggered_ability_state = _passive_only
    assert B.triggered_ability_state is saved, "le helper doit rester intact dans base.py"
    return lambda: setattr(DB, "triggered_ability_state", saved)


def _port_repair(dv, ob, snap, board, ability_states, carrier_vis: str, victim_vis: str) -> dict:
    """Rejoue `On(UnitDeath = 0)` OFFLINE sur la capture, victime marquee MORTE.

    `ability_states=None` = le canal #357 non fourni -> le rail ne voit pas la relique (l'etat
    d'avant). Rend `{repaired, amount, events, level, mult, tertiary}`."""
    from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
    from engine.runner.operations.triggers import unit_death_triggers
    from engine.runner.operations.triggers.loki.dawn_blade import hp_to_heal
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)

    def by_vis(vis):
        for uid, e in state.entities.items():
            sc = e.get_component(StatsComponent)
            if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                return uid
        return None

    car, vic = by_vis(carrier_vis), by_vis(victim_vis)
    if car is None or vic is None:
        return {"error": "porteur/victime absents offline (%s/%s)" % (car, vic)}
    sc = state.get_entity(car).get_component(StatsComponent)
    ve = state.get_entity(vic)
    ve.get_component(UnitComponent).alive = False           # la victime est DEJA morte (probe_317)
    vh = ve.get_component(HealthComponent)
    if vh is not None:
        vh.hp = 0
    hp0 = state.get_entity(car).get_component(HealthComponent).hp
    out = unit_death_triggers(state, vic, car) or []
    ev = [e for e in out if isinstance(e, dict) and e.get("relic") == RELIC]
    hp1 = state.get_entity(car).get_component(HealthComponent).hp
    return {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0),
            "amount": hp_to_heal(state, car), "hp_delta": int(hp1) - int(hp0),
            "tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "level": getattr(sc.ctx, "tertiary_ability_level", None),
            "mult": getattr(sc.ctx, "tertiary_ability_variables_multiplier", None),
            "passive_level": getattr(sc.ctx, "passive_ability_level", None),
            "ability_mult": getattr(sc.ctx, "ability_variables_multiplier", None)}


def run(rpc, level: int = 8, mutate: str | None = None, build_runner=None,
        keep: bool = False, regime: str = "melee") -> dict:
    """Monte le regime, mesure le natif ET le port, rend le releve. Ne LEVE pas -- l'appelant juge.

    Regimes -- les DEUX derniers sont des NEGATIFS, et ils comptent autant que le nominal : un rail
    qui inscrit la relique doit rester REFUSABLE, sinon on a echange une degradation muette (rien ne
    se declenche) contre une degradation permissive (tout se declenche).

      `melee`   NOMINAL : porteur BLESSE, kill au CONTACT      -> natif == port == hpToHeal[lvl]
      `ranged`  meme montage, kill a d=2 (portee d'arme)       -> `IsDefeatedByMeleeAttack` refuse
      `fullhp`  meme montage, porteur a PV PLEINS              -> `EntityCanBeRepaired` refuse
    """
    assert mutate in (None,) + MUTATIONS, "mutation inconnue : %s" % (mutate,)
    assert regime in REGIMES, "regime inconnu : %s (connus : %s)" % (regime, sorted(REGIMES))
    import hexgeo
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    out: dict = {"level": level, "mutate": mutate, "regime": regime, "ok": False, "why": None}
    out["expected"] = int(ability_var(RELIC, "hpToHeal", level, multiplier_pct=100) or 0)
    out["expected_clamped"] = int(ability_var(RELIC, "hpToHeal", 50, multiplier_pct=100) or 0)

    sbc = seed_bc_path()
    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(level, sbc, regime))["rid"]
    else:
        rid = _build_subprocess(level, sbc, regime)
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")

        def live():
            return {u["squadId"]: u
                    for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
                    if not u.get("isDead")}

        U = live()
        sq = {u.get("visualId"): s for s, u in U.items()}
        for vis in (CARRIER, VICTIM):
            if vis not in sq:
                out["why"] = "%s absent du live" % vis
                return out

        # --- MESURE C : le multiplicateur, deux sources independantes ---------------------------
        rows = _tertiary_rows(rpc, rid)
        out["tertiary_rows"] = rows
        mine = [r for r in rows if r["abilityId"] == RELIC_ID]
        if not mine:
            out["why"] = ("aucune entree de hierarchie 3 pour %s (id %d) : la relique n'est PAS "
                          "montee -- le montage #237 a echoue" % (RELIC, RELIC_ID))
            return out
        out["mounted"] = mine[0]
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
        cfg = {}
        for u in (snap0.get("units") or []):
            uc = u.get("unitConfig") or {}
            if uc.get("visualId") == CARRIER:
                cfg = {"tertiaryMult": uc.get("tertiaryAbilityVariablesMultiplier"),
                       "abilityMult": uc.get("abilityVariablesMultiplier"),
                       "passiveLevel": uc.get("passiveAbilityLevel"),
                       "activeLevel": uc.get("activeAbilityLevel")}
        out["unit_config"] = cfg

        # --- conduite des positions : contact (melee/fullhp) ou d=2 exact (ranged) ----------------
        vt = board.id_at(U[sq[VICTIM]]["col"], U[sq[VICTIM]]["row"])
        if regime == "ranged":
            if not _drive_at_distance(rpc, rid, board, live, sq[CARRIER], vt, 2):
                out["why"] = "%s ne peut pas se poser a d=2 exact de %s" % (CARRIER, VICTIM)
                return out
        elif not _drive_adjacent(rpc, rid, board, live, sq[CARRIER], vt):
            out["why"] = "%s ne peut pas atteindre le contact de %s" % (CARRIER, VICTIM)
            return out
        U = live()
        cp = (U[sq[CARRIER]]["col"], U[sq[CARRIER]]["row"])
        vp = (U[sq[VICTIM]]["col"], U[sq[VICTIM]]["row"])
        out["geometry"] = {"carrier": cp, "victim": vp, "dist": hexgeo.distance(cp, vp)}
        out["hp_before"] = {"carrier": U[sq[CARRIER]]["hp"], "carrier_max": U[sq[CARRIER]]["hpMax"],
                            "victim": U[sq[VICTIM]]["hp"]}
        missing = int(U[sq[CARRIER]]["hpMax"]) - int(U[sq[CARRIER]]["hp"])
        out["missing_before"] = missing
        if regime == "fullhp":
            if missing != 0:
                out["why"] = ("regime fullhp : le porteur manque deja %d PV -- le gate "
                              "`IsDamagedUnit` ne mordrait plus" % missing)
                return out
        elif missing <= out["expected"]:
            out["why"] = ("manque de PV %d <= hpToHeal %d : `MaxFillUp` saturerait et la mesure "
                          "ne separerait plus les paliers" % (missing, out["expected"]))
            return out

        # --- capture PRE-kill (positions FINALES) --------------------------------------------------
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)

        # --- PORT : trois lectures de la MEME capture, et c'est leur CONTRASTE qui prouve ----------
        #   `port`               le depot (canal #357 fourni)          -> doit egaler le natif ;
        #   `port_no_rail`       canal NON fourni                      -> l'etat d'AVANT #357 ;
        #   `port_passive_level` canal fourni, niveau lu sur le PASSIF -> l'etat d'AVANT sur l'axe
        #                        MAGNITUDE (le port firait, mais au mauvais palier).
        # Les trois sortent d'UN SEUL runner : le rejeu offline est gratuit, le build ne l'est pas.
        undo = _patch_passive_level() if mutate == "passive-level" else (lambda: None)
        try:
            out["port"] = _port_repair(dv, ob, snap, board,
                                       None if mutate == "no-rail" else uas, CARRIER, VICTIM)
        finally:
            undo()
        out["port_no_rail"] = _port_repair(dv, ob, snap, board, None, CARRIER, VICTIM)
        undo = _patch_passive_level()
        try:
            out["port_passive_level"] = _port_repair(dv, ob, snap, board, uas, CARRIER, VICTIM)
        finally:
            undo()

        # --- NATIF : le kill REEL, delta de PV du porteur sur CE seul coup -------------------------
        # ⚠ `applyAction` ne connait PAS de `kind: "attack"` (il rend `ok:false, unknown kind` en
        # SILENCE si on ignore le retour, cf. `probe_250` §regime BLESSE). L'attaque normale est une
        # ABILITY, et son `ActiveAbilityType` est CONCRET et PER-UNITE
        # (`ActiveAbilityComponent.NormalAttackType`, expose par `decisionView` en `kind == normal`).
        nat = None
        for u in (dv.get("units") or []):
            if int(u.get("id", -1)) == int(sq[CARRIER]):
                for ab in (u.get("abilities") or []):
                    if ab.get("kind") == "normal" and ab.get("id") is not None:
                        nat = int(ab["id"])
        if nat is None:
            out["why"] = "%s n'expose aucune attaque normale (decisionView kind=normal)" % CARRIER
            return out
        out["normal_attack_type"] = nat
        pre = {s: u["hp"] for s, u in live().items()}
        act = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sq[CARRIER], "targetId": sq[VICTIM],
            "abilityType": nat}}, 120)
        out["attack_ack"] = {k: act.get(k) for k in ("ok", "error", "mutated")} \
            if isinstance(act, dict) else {"raw": str(act)[:200]}
        if isinstance(act, dict) and act.get("ok") is False:
            out["why"] = "attaque REFUSEE par le natif : %s" % (out["attack_ack"],)
            return out
        post = rpc("observeBattle", {"runnerId": rid}, 40).get("units") or []
        by_sq = {u["squadId"]: u for u in post}
        out["victim_dead"] = bool(by_sq.get(sq[VICTIM], {}).get("isDead"))
        out["native_delta"] = int(by_sq[sq[CARRIER]]["hp"]) - int(pre[sq[CARRIER]])
        out["hp_after"] = {"carrier": by_sq[sq[CARRIER]]["hp"]}
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                     # pragma: no cover - diagnostic
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="#357 -- rail de la relique EQUIPEE")
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mutate", choices=MUTATIONS)
    ap.add_argument("--regime", choices=REGIMES, default="melee")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, level=a.level, mutate=a.mutate, keep=a.keep, regime=a.regime)
    print("runner=%s level=%s regime=%s mutate=%s ok=%s why=%s"
          % (r.get("rid"), r.get("level"), r.get("regime"), r.get("mutate"),
             r.get("ok"), r.get("why")))
    print("hpToHeal[%s] = %s   (palier 10, ce que le niveau PASSIF rendrait = %s)"
          % (a.level, r.get("expected"), r.get("expected_clamped")))
    if not r.get("ok"):
        return 1
    print("monte  : %s" % (r.get("mounted"),))
    print("config : %s" % (r.get("unit_config"),))
    print("geom   : %s | manque de PV avant = %s | PV = %s"
          % (r.get("geometry"), r.get("missing_before"), r.get("hp_before")))
    print("attaque: normalAttackType=%s ack=%s"
          % (r.get("normal_attack_type"), r.get("attack_ack")))
    print("[PORT avec rail] %s" % (r.get("port"),))
    print("[PORT sans rail] repaired=%s events=%s"
          % (r["port_no_rail"].get("repaired"), r["port_no_rail"].get("events")))
    print("[PORT niveau PASSIF] repaired=%s events=%s"
          % (r["port_passive_level"].get("repaired"), r["port_passive_level"].get("events")))
    print("[NATIF] victime morte=%s | delta PV porteur = %s"
          % (r.get("victim_dead"), r.get("native_delta")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
