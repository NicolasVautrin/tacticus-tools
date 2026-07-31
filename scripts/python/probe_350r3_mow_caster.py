#!/usr/bin/env python
"""Probe #350-r3 (b) -- le gabarit #344 face a un porteur MACHINE OF WAR (`blackForgefiend`).

CE QUE CE PROBE TRANCHE
-----------------------
`probe_344_ability_damage_average.py` passe son caster par `--p-units`, qui REFUSE une MoW.
La question etait : garde EXPLICITE de notre outil, ou chemin de deploiement MoW non cable ?

**Garde EXPLICITE, et le chemin EST cable.** `rl_duel.cmd_build::pick()` teste `u not in pool`, et
`pool` est le COMPLEMENTAIRE de `pool_mow` (`_normalize_and_extract_pool` :
`pool_regular = normalized - mow`). Les deux pools sont disjoints PAR CONSTRUCTION, donc toute MoW
est refusee par `--p-units` -- alors que `--p-mow` / `--a-mow` la poussent par
`BC.PredefinedMachines` (`_patch_predefined_machines`). L'etape 0 le MESURE.

CE QUI COINCE ENSUITE, ET QUI N'EST PAS LE DEPLOIEMENT (etape 1, mesuree)
------------------------------------------------------------------------
La MoW se deploie, `aiPlaybookPredict` resout bien ses playbooks (`HadesAutocannonsPlaybook` /
`DaemonicOrdnancePlaybook`) et le capteur d'`abilityState` PREND (`--unit-stat <mow>:
ActiveAbilityLevel=L` -> `level` capte). Mais avec la MoW COMME CASTER :

  * cote NATIF, `MakeDamagePredictions` rend une liste VIDE si aucun summon n'est en jeu, et
    carrement `null` (`listNull`, `count = -1`) des qu'il y en a un -- une MoW est off-board, et le
    harnais lui substitue la `UnitPosition` de la CIBLE (`rpc-predict.ts`, RE #172) ;
  * cote PORT, `engine.ai.context.build` ne construit AUCUN contexte pour une MoW (`ctx.me is None`) :
    une MoW n'est pas dans `decisionView.units`.

Donc la confrontation d'ARRONDI passe par la GREFFE (`case-92` §5bis) : le natif charge le playbook
PAR ABILITY (`PlaybookDatabase.LoadPlaybook(ActiveAbilityType)`), et la formule de 1147
(`StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)`) ne lit NI stat NI trait du caster --
seulement la config de l'ability et son `AbilityState`. La greffe est donc legitime ICI.

ETAPE 2 -- `1147 HadesAutocannons`, CONFRONTEE
----------------------------------------------
Son selecteur (`HadesAutocannonsAbility$$GetAllTargets`) ne retient que des SUMMONS du camp de la
cible : sans summon en jeu, le natif rend 0 event QUEL QUE SOIT le caster (mesure : 8 cibles x 2
abilities x {MoW, unite greffee} = 16 fois `count = 0`). Le montage en pose donc : `deathBlightbringer`
(pool) auto-cast `1040 SpawnPoxwalkers` -> deux `deathPoxwalker`. Le reste est le gabarit #344 :
deux bras de parite (`minDmg + maxDmg = 3 mod 4` puis `1 mod 4`), quatre variantes d'arrondi, et le
code LIVRE compare au natif.

ETAPE 3 -- `1148 DaemonicOrdnance`, DESACCORD TROUVE PUIS FERME
---------------------------------------------------------------
`DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur
`DaemonicOrdnanceAbility$$GetAllDamageableTargets` = les ennemis debout sur une tuile qui PORTE DEJA
`Fire` (5) -- et c'est ce meme cast qui pose le feu. Sur un board frais le natif rend donc 0. Le port
rendait `(81, 123, 3)` : sur-prediction MUETTE (ni erreur ni crash), qui gonflait l'utilite de 1148.
Ferme par `_MAKE_DMG_TARGET_GATE` (`engine/playbook/prediction/abilities.py`). Cette etape mesure les
DEUX regimes : zone froide (natif 0 == port 0) et zone EN FEU apres un premier cast.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_350r3_mow_caster.py --only-scan        # etape 0, aucun runner
    python probe_350r3_mow_caster.py --step 1           # constat caster MoW
    python probe_350r3_mow_caster.py --step 2           # confrontation 1147 (2 bras)
    python probe_350r3_mow_caster.py --step 3           # 1148 zone froide / zone en feu
    python probe_350r3_mow_caster.py                    # 0 + 1 + 2 + 3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                                  # noqa: E402
from rl_collect_batch import (_resolve_session, _rpc, _load_seed_bc,          # noqa: E402
                              _normalize_and_extract_pool)
from rl_duel import _board_mow_ok, _load_board_dump                           # noqa: E402
import probe_344_ability_damage_average as P344                               # noqa: E402

LOGS = PYDIR.parents[1] / "logs"

MOW = "blackForgefiend"          # porteur natif de 1147 HadesAutocannons et 1148 DaemonicOrdnance
BOARD = "MC1_67"
RANK = 17

# Montage SUMMON : `deathBlightbringer` est au pool et `1040 SpawnPoxwalkers` est SELF-CAST
# (aucune cible requise, aucun cooldown initial) -> deux `deathPoxwalker` en un seul `applyAction`.
SUMMONER = "deathBlightbringer"
SPAWN_POXWALKERS = 1040
P_FILLER = "deathPutrifier"
GRAFT_ON = "necroWarden"         # a-unit qui PORTERA l'ability greffee (equipe adverse)
A_FILLER = "worldKharn"
CENTER = (3, 4)

# `HadesAutocannons` : niveaux dont `minDmg + maxDmg` vaut 3 puis 1 modulo 4 (re-derives du
# gameconfig, jamais supposes -- le probe RELIT la somme effective et echoue si le regime differe).
A1147_LVL_A, A1147_LVL_B = 4, 2          # (58, 77) somme 135 = 3 mod 4 | (43, 58) somme 101 = 1 mod 4


def _r(sid, rid, m, b=None, t=120):
    body = {"runnerId": rid}
    body.update(b or {})
    return (_rpc(sid, m, [body], timeout=t).get("result") or {})


# ------------------------------------------------------------------- etape 0 : pre-conditions MoW

def scan(rank: int = RANK, board: str = BOARD, mow: str = MOW, verbose: bool = True) -> dict:
    """OFFLINE (un seul RPC `buildNormalizedBC`, aucun runner) : les quatre pre-conditions du
    montage MoW, chacune MESUREE."""
    sid = _resolve_session()
    board_dump = _load_board_dump(board)
    template, pool, pool_mow = _normalize_and_extract_pool(
        sid, _load_seed_bc(None), rank, board_dump=board_dump)
    cat = [u for u in (template.get("Units") or []) if u.get("VisualId") == mow]
    out = {
        "mow": mow, "board": board, "rank": rank,
        # (1) la MoW est dans `pool_mow` et ABSENTE du pool regulier -- c'est LA raison du refus de
        #     `--p-units`, et elle est STRUCTURELLE (les deux pools sont disjoints par construction).
        "in_pool_mow": mow in pool_mow, "in_pool_regular": mow in pool, "pool_mow": pool_mow,
        # (2) `--unit-stat` ecrit dans `BC.Units[]` par VisualId : l'entree doit exister.
        "in_bc_units_catalog": bool(cat),
        "active_ability_level": (cat[0].get("ActiveAbilityLevel") if cat else None),
        # (3) board MoW-capable (`MachineOfWarPosition` non nul pour les DEUX camps du SPS actif),
        #     sinon la MoW est DROP en silence au deploiement.
        "board_mow_ok": _board_mow_ok({"Board": board_dump.get("board"),
                                       "SpawnPointSetIndex": board_dump.get("spawnPointsSet")}),
        # (4) le summoner du montage doit etre au pool REGULIER (il se pose par `--p-units`).
        "summoner_in_pool": SUMMONER in pool,
    }
    out["ok"] = bool(out["in_pool_mow"] and not out["in_pool_regular"]
                     and out["in_bc_units_catalog"] and out["board_mow_ok"]
                     and out["summoner_in_pool"])
    if verbose:
        print("[350r3b/0] pre-conditions du montage MoW (%s, board %s, rank %d)" % (mow, board, rank))
        print("  dans pool_mow        : %s  (%d MoW spawnables)" % (out["in_pool_mow"], len(pool_mow)))
        print("  dans pool REGULIER   : %s  <- c'est pourquoi --p-units refuse" % out["in_pool_regular"])
        print("  entree BC.Units      : %s  (ActiveAbilityLevel=%s)"
              % (out["in_bc_units_catalog"], out["active_ability_level"]))
        print("  board MoW-capable    : %s" % out["board_mow_ok"])
        print("  summoner au pool     : %s (%s)" % (out["summoner_in_pool"], SUMMONER))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


# ------------------------------------------------------------------------- montage commun (live)

def _graft_seed_bc(ability_ids, on_unit: str, name: str) -> Path:
    """Greffe `ActiveAbilities = [...]` sur `on_unit` dans une COPIE de la seed BC (voie
    `case-92` §5bis : le natif charge le playbook PAR ABILITY, pas par unite)."""
    bc = _load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == on_unit:
            u["ActiveAbilities"] = list(ability_ids)
            n += 1
    if n != 1:
        raise RuntimeError("greffe impossible : %d entree(s) %r dans BC.Units" % (n, on_unit))
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / ("bc_350r3b_%s.json" % name)
    p.write_text(json.dumps(bc), encoding="utf-8")
    return p


def _build(state_file: Path, seed: int, extra: list, seed_bc: Path | None = None) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", str(RANK),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"] + extra
    if seed_bc is not None:
        cmd += ["--seed-bc", str(seed_bc)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _ids(sid, rid) -> tuple[dict, dict]:
    dv = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 8}, 180)
    return ({u.get("visualId"): u["id"] for u in (dv.get("units") or []) if u.get("alive")}, dv)


def _move(sid, rid, uid, col, row):
    return _r(sid, rid, "applyAction",
              {"action": {"kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}})


# ------------------------------------------------- etape 1 : la MoW REELLE comme caster (constat)

def step1_mow_caster(seed: int = 35030, verbose: bool = True) -> dict:
    """Deploie la MoW pour de vrai (`--a-mow`), pose des summons en face, et MESURE ce que
    l'oracle et le port rendent avec elle comme caster."""
    sid = _resolve_session()
    sf = LOGS / "p350r3b_step1.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = None
    try:
        rid = _build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
                                "--a-mow", MOW,
                                "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                               "AbilityVariablesMultiplierPercentage=100"
                                               % (MOW, A1147_LVL_A)])
        ids, dv = _ids(sid, rid)
        mows = dv.get("mows") or []
        mow_row = next((m for m in mows if m.get("visualId") == MOW), None)
        out = {"deployed": mow_row is not None,
               "caster_id": (mow_row or {}).get("casterId"),
               "abilities": [(a.get("id"), a.get("level"))
                             for a in ((mow_row or {}).get("abilities") or [])]}
        if mow_row is None:
            out["ok"] = False
            return out
        _move(sid, rid, ids[SUMMONER], *CENTER)
        _move(sid, rid, ids[P_FILLER], CENTER[0] - 1, CENTER[1] - 1)
        cid = int(mow_row["casterId"])
        # AVANT tout summon : le selecteur de 1147 ne retient que des summons -> liste VIDE.
        cold = _r(sid, rid, "aiPlaybookPredict",
                  {"unitId": cid, "targetId": ids[SUMMONER], "abilityType": 1147})
        out["cold"] = {"count": cold.get("count"), "listNull": cold.get("listNull"),
                       "abilityState": cold.get("abilityState")}
        # On pose deux summons (self-cast), PUIS on redemande.
        _r(sid, rid, "applyAction",
           {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                       "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
        ids2, _dv2 = _ids(sid, rid)
        smn = sorted(uid for vis, uid in ids2.items() if str(vis).startswith("deathPox"))
        out["summons"] = smn
        if smn:
            hot = _r(sid, rid, "aiPlaybookPredict",
                     {"unitId": cid, "targetId": smn[0], "abilityType": 1147})
            out["hot"] = {"count": hot.get("count"), "listNull": hot.get("listNull")}
        # Cote PORT : aucun contexte AI pour une MoW.
        try:
            ctx, _ = P344._ctx(sid, rid, cid)
            out["port_ctx_me"] = None if ctx.me is None else ctx.me.get("visualId")
        except Exception as e:                                   # noqa: BLE001 -- on RAPPORTE
            out["port_ctx_me"] = "exception: %s" % type(e).__name__
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    # Le CONSTAT attendu : deploiement OK, playbook resolu, niveau capte -- et pourtant l'oracle
    # rend une liste vide puis NULL, et le port n'a pas de contexte. C'est CELA le mur restant.
    out["ok"] = bool(out["deployed"] and out["abilities"]
                     and out["cold"]["count"] == 0
                     and (out.get("hot") or {}).get("listNull") is True
                     and out["port_ctx_me"] is None)
    if verbose:
        print("\n[350r3b/1] la MoW %s COMME CASTER" % MOW)
        print("  deployee               : %s (casterId=%s, abilities=%s)"
              % (out["deployed"], out["caster_id"], out["abilities"]))
        print("  1147 sans summon       : count=%s listNull=%s abilityState=%s"
              % (out["cold"]["count"], out["cold"]["listNull"], out["cold"]["abilityState"]))
        print("  summons poses          : %s" % out.get("summons"))
        print("  1147 avec summon       : %s" % out.get("hot"))
        print("  contexte PORT (ctx.me) : %s" % out["port_ctx_me"])
        print("  -> %s" % ("CONSTAT CONFIRME" if out["ok"] else "CONSTAT NON REPRODUIT"))
    return out


# --------------------------------------------- etape 2 : 1147 confrontee (greffe + summons + 2 bras)

def _arm_1147(sid, sf: Path, seed: int, level: int, label: str, seed_bc: Path) -> dict:
    rid = None
    try:
        rid = _build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
                                "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                               "AbilityVariablesMultiplierPercentage=100"
                                               % (GRAFT_ON, level)], seed_bc=seed_bc)
        ids, _dv = _ids(sid, rid)
        # GEOMETRIE DRIVEE : summoner au centre (ses summons naissent sur son ring), porteur adjacent.
        _move(sid, rid, ids[SUMMONER], *CENTER)
        _move(sid, rid, ids[P_FILLER], CENTER[0] - 1, CENTER[1] - 1)
        _move(sid, rid, ids[GRAFT_ON], CENTER[0] + 1, CENTER[1])
        _move(sid, rid, ids[A_FILLER], CENTER[0] + 1, CENTER[1] - 1)
        _r(sid, rid, "applyAction",
           {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                       "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
        ids2, _dv2 = _ids(sid, rid)
        smn = sorted(uid for vis, uid in ids2.items() if str(vis).startswith("deathPox"))
        if not smn:
            return {"label": label, "error": "aucun summon apres 1040 SpawnPoxwalkers"}
        cid, tid = ids[GRAFT_ON], smn[0]
        ctx, _dv3 = P344._ctx(sid, rid, cid)
        scene = ctx.scene
        mm = P344._minmax_config(scene, cid, 1147, "HadesAutocannons")
        if mm is None:
            return {"label": label, "error": "config d'ability introuvable"}
        mn, mx, lvl_eff, mult_eff = mm
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))
        nat, n_nat = P344._native(sid, rid, cid, tid, 1147)
        ports = {name: P344._offline(scene, cid, tid, 1147, "HadesAutocannons", here, fn)[0]
                 for name, fn in P344.VARIANTS}
        shipped, n_port = P344._offline(scene, cid, tid, 1147, "HadesAutocannons", here, None)
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    s = int(mn) + int(mx)
    return {"label": label, "level_asked": level, "level_eff": lvl_eff, "mult_eff": mult_eff,
            "minDmg": int(mn), "maxDmg": int(mx), "sum": s, "sum_mod4": s % 4, "floor": s // 2,
            "summons": smn, "native": nat, "ports": ports, "shipped": shipped,
            "n_events_native": n_nat, "n_events_port": n_port}


def step2_confront_1147(seed: int = 35040, verbose: bool = True) -> dict:
    """Gabarit #344 applique a 1147 : deux bras de parite, quatre variantes, code LIVRE vs natif."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = _graft_seed_bc([1147], GRAFT_ON, "1147")
    sf = LOGS / "p350r3b_step2.json"
    arms = {}
    for key, label, lvl, sd in (("a", "A (3 mod 4 -- le natif MONTE)", A1147_LVL_A, seed),
                                ("b", "B (1 mod 4 -- le natif DESCEND)", A1147_LVL_B, seed + 1)):
        arm = _arm_1147(sid, sf, sd, lvl, label, seed_bc)
        if not arm.get("error"):
            P344._grade(arm)
        arms[key] = arm
    regimes_ok = (arms["a"].get("sum_mod4") == 3 and arms["b"].get("sum_mod4") == 1)
    nul_on_both = [n for n, _fn in P344.VARIANTS
                   if all((arms[k].get("match") or {}).get(n) for k in ("a", "b"))]
    import engine.entities.abilities.active_ability as AA
    expected = "to_even" if 1147 in AA._PREDICTION_MINMAX_AVERAGE else "trunc"
    ok = bool(regimes_ok and all(arms[k].get("ok") for k in ("a", "b"))
              and nul_on_both == [expected])
    if verbose:
        print("\n[350r3b/2] 1147 HadesAutocannons -- greffee sur %s, summons de %s"
              % (GRAFT_ON, SUMMONER))
        print("  variante attendue par le registre : %s (voie a2 -- "
              "StaffOfStarsAbility$$GetDamage, isPrediction = 1)" % expected)
        for key in ("a", "b"):
            arm = arms[key]
            if arm.get("error"):
                print("\n  === bras %s === ERREUR : %s" % (key, arm["error"]))
                continue
            print("\n  === bras %s === %s" % (key, arm["label"]))
            print("    niveau demande=%d effectif=%d | minDmg=%d maxDmg=%d somme=%d (mod4=%d) floor=%d"
                  % (arm["level_asked"], arm["level_eff"], arm["minDmg"], arm["maxDmg"],
                     arm["sum"], arm["sum_mod4"], arm["floor"]))
            print("    natif   = %-24s (events natif=%d port=%d)"
                  % (str(arm["native"]), arm["n_events_native"], arm["n_events_port"]))
            print("    LIVRE   = %-24s %s"
                  % (str(arm["shipped"]), "== NATIF" if arm["shipped_ok"] else "!= NATIF"))
            for name, _fn in P344.VARIANTS:
                print("      %-9s port=%-24s %s"
                      % (name, str(arm["ports"][name]), "== NATIF" if arm["match"][name] else "!="))
            print("    bras discriminant : %s" % arm["discriminates"])
        print("\n  regimes pilotes comme annonces : %s" % regimes_ok)
        print("  variantes nulles sur les DEUX bras : %s" % (nul_on_both or "aucune"))
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "arms": arms, "regimes_ok": regimes_ok,
            "nul_on_both_arms": nul_on_both, "expected_variant": expected}


# ------------------------------------ etape 3 : 1148, zone FROIDE puis zone EN FEU (natif vs port)

def step3_daemonic_ordnance(seed: int = 35050, verbose: bool = True) -> dict:
    """`DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur les ennemis debout sur une tuile
    qui PORTE DEJA `Fire` (5). Deux regimes, mesures sur le MEME runner : avant le premier cast (zone
    froide) et apres (la zone brule). C'est le gate `_MAKE_DMG_TARGET_GATE` qui est en jeu."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = _graft_seed_bc([1148], SUMMONER, "1148")
    sf = LOGS / "p350r3b_step3.json"
    rid = None
    out: dict = {}
    try:
        rid = _build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
                                "--unit-stat", "%s:ActiveAbilityLevel=2,"
                                               "AbilityVariablesMultiplierPercentage=100"
                                               % SUMMONER], seed_bc=seed_bc)
        ids, _dv = _ids(sid, rid)
        cid = ids[SUMMONER]
        _move(sid, rid, cid, *CENTER)
        _move(sid, rid, ids[P_FILLER], CENTER[0] - 1, CENTER[1] - 1)
        tgt_pos = (CENTER[0] + 1, CENTER[1])
        _move(sid, rid, ids[GRAFT_ON], *tgt_pos)
        _move(sid, rid, ids[A_FILLER], CENTER[0] + 1, CENTER[1] - 1)
        tid = ids[GRAFT_ON]

        def _both(tag):
            nat, n_nat = P344._native(sid, rid, cid, tid, 1148)
            ctx, _d = P344._ctx(sid, rid, cid)
            mp = ctx.me.get("pos") or {}
            port, n_port = P344._offline(ctx.scene, cid, tid, 1148, "DaemonicOrdnance",
                                         (mp.get("col"), mp.get("row")), None)
            fx = (ctx.scene.tile_effects_by_pos or {}).get(tuple(tgt_pos)) or []
            return {"tag": tag, "native": nat, "n_native": n_nat, "port": port,
                    "n_port": n_port, "tile_effects_on_target": fx}

        out["cold"] = _both("zone FROIDE (aucune tuile en feu)")
        # Le cast POSE le feu sur la zone (etage [5] `AddEffect(Fire -> zone)`). Cible = l'hex du
        # porteur greffe, pour que la zone triangulaire contienne sa tuile.
        cast = _r(sid, rid, "applyAction",
                  {"action": {"kind": "ability", "casterId": cid,
                              "to": {"col": tgt_pos[0], "row": tgt_pos[1]},
                              "abilityType": 1148}}, 180)
        out["cast_ok"] = bool((cast.get("actions") or [{}])[0].get("ok"))
        out["cast_error"] = (cast.get("actions") or [{}])[0].get("error")
        out["hot"] = _both("zone EN FEU (apres un premier cast)")
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    # Le seul verdict que ce probe VERROUILLE est le regime FROID : natif et port doivent y rendre
    # ZERO event. Le regime CHAUD est mesure et IMPRIME (il depend du cast, qui peut echouer sur un
    # gate de ciblage), jamais force.
    cold_ok = (out["cold"]["n_native"] == 0 and out["cold"]["n_port"] == 0)
    out["ok"] = bool(cold_ok)
    if verbose:
        print("\n[350r3b/3] 1148 DaemonicOrdnance -- greffee sur %s" % SUMMONER)
        for k in ("cold", "hot"):
            r = out.get(k) or {}
            print("  %-44s natif=%s (%d ev) | port=%s (%d ev) | effets de tuile cible=%s"
                  % (r.get("tag"), r.get("native"), r.get("n_native"),
                     r.get("port"), r.get("n_port"), r.get("tile_effects_on_target")))
        print("  cast intermediaire : ok=%s err=%s" % (out.get("cast_ok"), out.get("cast_error")))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only-scan", action="store_true")
    ap.add_argument("--step", type=int, default=None, choices=[0, 1, 2, 3])
    ap.add_argument("--seed", type=int, default=35030)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    steps = [a.step] if a.step is not None else ([0] if a.only_scan else [0, 1, 2, 3])
    out = {}
    if 0 in steps:
        out["scan"] = scan()
    if 1 in steps:
        out["step1"] = step1_mow_caster(seed=a.seed)
    if 2 in steps:
        out["step2"] = step2_confront_1147(seed=a.seed + 10)
    if 3 in steps:
        out["step3"] = step3_daemonic_ordnance(seed=a.seed + 20)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if all(v.get("ok") for v in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
