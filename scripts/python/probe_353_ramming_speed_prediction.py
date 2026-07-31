#!/usr/bin/env python
"""Probe #353 -- la PREDICTION de `RammingSpeed` (ActiveAbilityType 1059), batch par batch.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM)
---------------------------------------------------
`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` emet QUATRE batchs, dont
les deux derniers sont CONDITIONNELS :

    dmg   = AbilityConfiguration$$GetVariableForLevel(config, 0xc = minDmg, abilityState)
    hits1 = AbilityConfiguration$$GetNumberConstant(config, 0x2f = nrOfHits)      // 4
    hits2 = AbilityConfiguration$$GetNumberConstant(config, 0x32 = nrOfHits_2)    // 2
    prof  = AbilityConfiguration$$GetDamageProfile(config)                        // Physical

    list = GenerateMultiHitAttackPredictions(caster, casterPos, TARGET, <Target@0x60>,
                                             Get(dmg), hits1, prof, null, 0)
    self = GenerateMultiHitAttackPredictions(caster, casterPos, CASTER, <Caster@0x48>,
                                             Get(dmg), hits2, prof, null, 0)
    list.AddRange(self)
    if (!self.Any(p => p.Prediction.WillBeKill)) return list;         // <>c$$<MakeDamagePredictions>b__2_0

    amount  = <eval>( ExplodesAbility$$GetDamage(dsl) )               // % du maxPV du caster
    tile    = RammingSpeedAbility$$GetTileToMoveTo(ability)
    friends = Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3)
    enemies = Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3)
    list.AddRange(GenerateAttackPredictions(caster, casterPos, TARGET, friends, Get(amount), null,
                                            Nullable(0xf = DirectDamage), 0))
    list.AddRange(GenerateAttackPredictions(caster, casterPos, TARGET, enemies, Get(amount), null,
                                            Nullable(0xf), 0))

Le port d'AVANT #353 rendait UN SEUL event, base = avg(minDmg, maxDmg) et hits =
`GetDefaultAttackHits(nrOfHits, ExtraHits)`. #353 porte les batchs 1 et 2.

GATE DE CONFRONTABILITE -- comment on amene 1059 en bataille
------------------------------------------------------------
AUCUNE unite du gameconfig ne porte `RammingSpeed` : la chaine complete du JSON ne la cite que
4 fois (`units.abilities`, `units.abilityPowerModifiers`, et 2 fois sous
`aiUtilities.Default.RammingSpeed_MostAdjacentEnemies`). Ni active, ni passive, ni relique, ni
mythic, ni item, ni summon, ni trait. Recours = la GREFFE de case-92 sec.5bis : on pose
`ActiveAbilities = [1059]` sur l'entree `BC.Units` d'un heros DU POOL, dans une COPIE du seed BC,
et on ajoute la config d'ability manquante a `BC.Abilities.ActiveAbilities` (sans quoi la premiere
lecture de variable LEVE -> « system error »).

C'est une MESURE, pas un contournement : `aiPlaybookPredict` charge le playbook PAR ABILITY
(`PlaybookDatabase.LoadPlaybook(1059)`), donc le code exerce est bien `RammingSpeedPlaybook`. Ce que
la greffe ne couvre pas : les stats/traits/armes du VRAI porteur -- il n'y en a AUCUN, donc rien a
couvrir ; natif et port voient la MEME unite greffee, ce qui est exactement ce qu'un test
d'agreement demande.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_353_ramming_speed_prediction.py
    python probe_353_ramming_speed_prediction.py --level 8 --json
    python probe_353_ramming_speed_prediction.py --hp-player 400     # vise le batch EXPLOSION
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc, _load_seed_bc                # noqa: E402
import catalog_inject as CI                                                      # noqa: E402

ABILITY = 1059
ABILITY_NAME = "RammingSpeed"
# Greffon : heros MELEE du pool rank 17 (`rl_duel build --list-pool`). `orksKillaKan` porte en outre
# le trait `Explodes` -- sans effet sur la PREDICTION (le playbook evalue `ExplodesAbility$$GetDamage`
# sans jamais tester le trait), mais coherent avec la mecanique.
GRAFT = "orksKillaKan"
FILLER_P = "astraBullgryn"
VICTIM = "necroWarden"          # cible TEMOIN : aucun trait de reduction de coups (pas de Parry)
FILLER_A = "ultraTitus"
BOARD = "MC1_67"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build_grafted_seed_bc(out_path: Path, graft: str = GRAFT,
                          ability_id: int = ABILITY, ability_name: str = ABILITY_NAME) -> dict:
    """COPIE du seed BC ou `graft` porte l'ability greffee ET ou sa config existe.

    Deux etages, tous deux obligatoires (cf. case-92 sec.2 et sec.5bis) :
      1. `BC.Units[<graft>].ActiveAbilities = [<ability_id>]` -- l'unite EXPOSE l'ability, donc le
         capteur `abilityStates` rend un `AbilityState` reel (level/mult) au lieu du defaut (0,100) ;
      2. `BC.Abilities.ActiveAbilities[<ability_name>]` -- `_load_seed_bc` ne re-synthetise QUE les
         configs deja referencees par le catalogue ; une ability que personne ne porte n'y entre pas
         (MESURE : `RammingSpeed` absente des 131 entrees). Sans elle, `GetVariableForLevel` LEVE.
    """
    bc = _load_seed_bc(None)
    acts = ((bc.get("Abilities") or {}).get("ActiveAbilities") or {})
    if ability_name not in acts:
        acts[ability_name] = CI.synthesize_ability(ability_name)
    bc["Abilities"]["ActiveAbilities"] = acts
    hit = 0
    for u in bc.get("Units") or []:
        if str(u.get("Id") or "").split(":")[0] == graft:
            u["ActiveAbilities"] = [int(ability_id)]
            hit += 1
    if not hit:
        raise RuntimeError("greffon %r absent du seed BC" % graft)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return {"grafted_entries": hit, "ability_config_injected": ability_name in acts}


def _build(state_file: Path, seed_bc: Path, seed: int, board: str, level: int, mult: int,
           armor_target=None, hp_player=None) -> int:
    """`--block-player 0,0` n'est PAS decoratif : la GATE du batch EXPLOSION est
    `Any(selfPreds, p => p.WillBeKill)`, et `DamagePredictionResult$$get_WillBeKill` lit
    `BlockScenarios[0]` (le scenario « TOUS les coups bloques ») des que cette liste est NON VIDE --
    donc la borne d'un caster qui peut bloquer est celle ou il encaisse le MINIMUM, et le kill n'est
    jamais GARANTI. Le defenseur du 2e batch etant le CASTER lui-meme, c'est le block du camp JOUEUR
    qu'il faut retirer, pas celui de la cible."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, FILLER_A),
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                          % (GRAFT, level, mult),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if armor_target is not None:
        cmd += ["--armor-target", str(int(armor_target))]
    if hp_player is not None:
        cmd += ["--hp-player", str(int(hp_player))]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _place(sid, rid, ids) -> dict:
    """GEOMETRIE DRIVEE ET VERIFIEE (runner.md sec.4). La VICTIME occupe une tuile marchable a SIX
    voisins (choisie deterministiquement au milieu de la liste triee), le CASTER un de ses voisins,
    les deux fillers deux AUTRES voisins. On laisse ainsi 3 voisins LIBRES autour de la cible --
    c'est ce dont `RammingSpeedAbility$$GetTileToMoveTo` a besoin pour rendre une tuile
    (`CanAddUnit(AdjacentTiles(target)) & MovableTilesInRange(caster, range)`).

    Le placement est RELU et compare : un `move` refuse ne doit pas se lire comme une geometrie
    choisie. Rend {visualId: (col,row)} ou LEVE."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    six = sorted(t.get("id") for t in bg["tiles"]
                 if len(board.neighbours(t.get("id"))) == 6 and board.walkable(t.get("id"))
                 and all(board.walkable(n) for n in board.neighbours(t.get("id"))))
    if not six:
        raise RuntimeError("aucune tuile marchable a 6 voisins marchables sur ce board")
    tvic = six[len(six) // 2]
    ring = board.neighbours(tvic)
    want = {VICTIM: board.coord(tvic), GRAFT: board.coord(ring[0]),
            FILLER_P: board.coord(ring[1]), FILLER_A: board.coord(ring[2])}
    # DEUX passes : un `move` vers une tuile encore OCCUPEE par une unite qu'on n'a pas encore
    # deplacee est refuse. La 2e passe rejoue les deplacements que la 1re n'a pas obtenus.
    got: dict = {}
    for _ in range(2):
        for v, (col, row) in want.items():
            if got.get(v) != (col, row):
                _move(sid, rid, ids[v], col, row)
        got = {u["visualId"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (_view(sid, rid).get("units") or [])
               if u.get("alive") and u.get("visualId") in want}
        if got == want:
            return want
    raise RuntimeError("placement REFUSE : voulu %s, obtenu %s" % (want, got))


def _sig(events) -> list:
    """Signature COMPARABLE d'une liste d'events natifs : (cible, min, max, coups), triee."""
    return sorted((e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),
                   e.get("appliedHits")) for e in events)


def _sig_port(events) -> list:
    return sorted((e.target, min(e.prediction.accurate_health_damage.min, e.prediction.current_health),
                   min(e.prediction.accurate_health_damage.max, e.prediction.current_health),
                   e.prediction.applied_hits) for e in events)


def _ctx(sid, rid, cid):
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    dv = _view(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid)), dv


def _offline(scene, cid, tid, here, shipped: bool):
    """Prediction OFFLINE. `shipped=True` = le code LIVRE ; `False` = le port d'AVANT #353
    (registres 1059 retires), pour chiffrer le DELTA que ce correctif apporte."""
    from engine.playbook.prediction import abilities as PA
    o_ovr, o_extra = PA._MAKE_DMG_INPUT_OVERRIDES, PA._MAKE_DMG_EXTRA_EVENTS
    if not shipped:
        PA._MAKE_DMG_INPUT_OVERRIDES = {k: v for k, v in o_ovr.items() if k != ABILITY}
        PA._MAKE_DMG_EXTRA_EVENTS = {k: v for k, v in o_extra.items() if k != ABILITY}
    try:
        return PA.make_damage_predictions(scene, int(cid), int(tid), ABILITY, ABILITY_NAME,
                                          attack_pos=here)
    finally:
        PA._MAKE_DMG_INPUT_OVERRIDES, PA._MAKE_DMG_EXTRA_EVENTS = o_ovr, o_extra


def run(seed: int = 35301, state_file=None, level: int = 8, mult: int = 100,
        board: str = BOARD, armor_target=0, hp_player=None,
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = PYDIR.parents[1] / "logs"
    sf = Path(state_file) if state_file else (logs / "p353.json")
    bcf = logs / "p353-seed-bc.json"
    graft_info = build_grafted_seed_bc(bcf)

    rid = None
    out: dict = {"graft": graft_info, "level_asked": level, "mult": mult, "board": board,
                 "armor_target": armor_target, "hp_player": hp_player}
    try:
        rid = _build(sf, bcf, seed, board, level, mult, armor_target, hp_player)
        out["runner"] = rid
        dv = _view(sid, rid)
        ids = {}
        for v in (GRAFT, FILLER_P, VICTIM, FILLER_A):
            u = next((x for x in (dv.get("units") or [])
                      if x.get("visualId") == v and x.get("alive")), None)
            if u is None:
                out["error"] = "unite absente du build : %s" % v
                return out
            ids[v] = int(u["id"])
        out["placement"] = {k: list(v) for k, v in _place(sid, rid, ids).items()}
        cid, tid = ids[GRAFT], ids[VICTIM]
        out["caster_id"], out["target_id"] = cid, tid

        ctx, _dv2 = _ctx(sid, rid, cid)
        scene = ctx.scene
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))

        # Entrees EFFECTIVES du port, re-derivees du live (jamais supposees).
        import gameconfig as GC
        from engine.entities.abilities.ability_configuration import AbilityConfiguration
        from engine.entities.abilities.active_ability import active_ability_for
        cfg = AbilityConfiguration.from_gameconfig(ABILITY_NAME, GC.ability(ABILITY_NAME))
        ab = active_ability_for(ABILITY_NAME, ABILITY, scene.ctx(cid), cfg,
                                ability_state=scene.ability_state(cid, ABILITY))
        lvl, mlt = ab.level, ab.multiplier
        out["level_eff"], out["mult_eff"] = lvl, mlt
        out["minDmg"] = cfg.get_variable_for_level("minDmg", lvl, 0, mlt)
        out["maxDmg"] = cfg.get_variable_for_level("maxDmg", lvl, 0, mlt)
        out["avg_generique"] = ab.get_damage()
        out["nrOfHits"] = int((cfg.constants or {}).get("nrOfHits") or 0)
        out["nrOfHits_2"] = int((cfg.constants or {}).get("nrOfHits_2") or 0)
        out["hits_generiques"] = ab.get_special_hits(True)
        out["caster_hp"] = scene.hp(cid)
        out["caster_hpmax"] = scene.hpmax(cid)

        nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                            "targetId": tid, "abilityType": ABILITY}, 120)
        out["native_ok"] = bool(nat.get("ok", True))
        out["native_error"] = nat.get("error")
        out["native_playbook"] = nat.get("playbookClass")
        out["native_ability_state"] = nat.get("abilityState")
        nev = nat.get("events") or []
        out["native_events"] = [{"targetId": e.get("targetId"), "healthDmgMin": e.get("healthDmgMin"),
                                 "healthDmgMax": e.get("healthDmgMax"),
                                 "appliedHits": e.get("appliedHits"),
                                 "willBeKill": e.get("killSure")} for e in nev]
        out["native_sig"] = _sig(nev)

        shipped = _offline(scene, cid, tid, here, True)
        before = _offline(scene, cid, tid, here, False)
        out["port_sig"] = _sig_port(shipped)
        out["port_before_sig"] = _sig_port(before)
        out["match"] = (out["port_sig"] == out["native_sig"])
        out["before_match"] = (out["port_before_sig"] == out["native_sig"])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    out["ok"] = bool(out.get("match") and not out.get("before_match"))
    if verbose:
        print("[353] greffe : %s <- ability %d (%s) | %s"
              % (GRAFT, ABILITY, ABILITY_NAME, graft_info))
        print("[353] runner=%s board=%s caster=%s cible=%s armure_cible=%s hp_player=%s"
              % (rid, board, out.get("caster_id"), out.get("target_id"), armor_target, hp_player))
        print("[353] niveau demande=%s effectif=%s mult=%s | minDmg=%s maxDmg=%s avg=%s"
              % (level, out.get("level_eff"), out.get("mult_eff"), out.get("minDmg"),
                 out.get("maxDmg"), out.get("avg_generique")))
        print("[353] hits : nrOfHits=%s nrOfHits_2=%s | generiques(port avant)=%s"
              % (out.get("nrOfHits"), out.get("nrOfHits_2"), out.get("hits_generiques")))
        print("[353] caster hp=%s/%s" % (out.get("caster_hp"), out.get("caster_hpmax")))
        print("[353] playbook natif = %s | erreur = %s"
              % (out.get("native_playbook"), out.get("native_error")))
        print("  natif        = %s" % (out.get("native_sig"),))
        print("  port LIVRE   = %s  %s"
              % (out.get("port_sig"), "== NATIF" if out.get("match") else "!= NATIF"))
        print("  port AVANT   = %s  %s"
              % (out.get("port_before_sig"),
                 "== NATIF (bras NON discriminant)" if out.get("before_match") else "!= NATIF"))
        print("  -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=35301)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--armor-target", type=int, default=0)
    ap.add_argument("--hp-player", type=int, default=None,
                    help="PV FORCES du camp joueur -- vise la GATE `Any(selfPreds, WillBeKill)` du "
                         "batch EXPLOSION. MESURE #353 : elle n'a ouvert sur AUCUN des montages "
                         "joues (voir docs/rl/case-353-ramming-speed-prediction.md sec.5)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, state_file=a.state_file, level=a.level, mult=a.mult, board=a.board,
              armor_target=a.armor_target, hp_player=a.hp_player)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
