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

CE QUI COINCAIT ENSUITE -- ET QUI ETAIT LE HARNAIS, PAS LE JEU (tranche par #360)
--------------------------------------------------------------------------------
La MoW se deploie, `aiPlaybookPredict` resout bien ses playbooks (`HadesAutocannonsPlaybook` /
`DaemonicOrdnancePlaybook`) et le capteur d'`abilityState` PREND (`--unit-stat <mow>:
ActiveAbilityLevel=L` -> `level` capte). Avec la MoW COMME CASTER, cette etape constatait pourtant
un oracle `null` et un port sans contexte. Les deux constats etaient des artefacts DE MESURE :

  * `aiPlaybookPredict` SUBSTITUAIT la `UnitPosition` de la CIBLE au caster off-board. Le natif ne
    fait jamais cela : `DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
    passe `UnitPosition$$NullPosition()` (= une liste de tuiles VIDE). Invoque avec la position du
    CASTER, le MEME `MakeDamagePredictions` REND l'event -- `(324, 492, 6)` au niveau 4, identique
    a la voie greffee. `ncPlaybookPredict(via = "makeDamagePredictions")` le fait deja ;
  * `engine.ai.context.build` rend `me = None` sur une Machine parce que c'est la fonction des
    UNITES ; `build_machine` est celle des MACHINES, elle existe, et `engine_validate.py` route deja
    dessus via `machine_row`. Le probe appelait simplement la mauvaise.

La GREFFE (`case-92` §5bis) reste legitime -- le natif charge le playbook PAR ABILITY, et la formule
de 1147 (`StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)`) ne lit NI stat NI trait du
caster -- et elle est desormais VALIDEE : `probe_360_mow_caster_oracle.py` rejoue les deux bras avec
le porteur MoW REEL et retrouve les memes couples, au chiffre pres.

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

ETAPE 4 -- LE VOLET AoE DE `1147` (#359)
----------------------------------------
`HadesAutocannonsPlaybook$$MakeDamagePredictions` ne prend PAS `<Target>` : il boucle sur les entites
de `GetEntitiesFromSelector(HadesAutocannonsAbility$$GetAllTargets, ...)` et `AddRange` un
`GenerateMultiHitAttackPredictions` par entite. Le port n'avait aucun mirror de ce selecteur -> UN
event la ou le natif en emet un par summon retenu. Quatre regimes (aucun summon / cible summon /
porteur ennemi au contact / cible NON-summon), chacun mesure natif vs port AVANT vs port APRES -- le
port d'AVANT etant reconstitue par RETRAIT des entrees de registre, jamais reimplemente.

ETAPE 5 -- GENERALISATION DU MEME VOLET
---------------------------------------
Board DIFFERENT (`MC1_15`) et caster ALLIE des summons : le selecteur ne lit RIEN du caster. L'etape
4 borne un cote (caster ENNEMI -- un port qui referencerait le caster rendrait 0), celle-ci l'autre
(caster ALLIE -- un port qui filtrerait les cibles ennemies rendrait 0 alors que le natif emet).

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_350r3_mow_caster.py --only-scan        # etape 0, aucun runner
    python probe_350r3_mow_caster.py --step 1           # constat caster MoW
    python probe_350r3_mow_caster.py --step 2           # confrontation 1147 (2 bras)
    python probe_350r3_mow_caster.py --step 3           # 1148 zone froide / zone en feu
    python probe_350r3_mow_caster.py --step 4           # 1147 volet AoE, 4 regimes
    python probe_350r3_mow_caster.py --step 5           # 1147 volet AoE, generalisation
    python probe_350r3_mow_caster.py --step 6           # 1148 volet AoE (#359-r1), 3 regimes
    python probe_350r3_mow_caster.py --step 7           # idem sur un board ou `dir` BASCULE
    python probe_350r3_mow_caster.py                    # 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7

ETAPE 6 -- LE PENDANT AoE DE `1148` (#359-r1)
---------------------------------------------
`DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle lui aussi sur un selecteur
(`GetAllDamageableTargets` = les ennemis debout sur une tuile EN FEU de la zone-triangle ancree sur
la CIBLE). #350-r3 n'avait porte que le gate de la cible PRINCIPALE ; le SET restait vide. Des que la
cible demandee est HORS de la zone de feu alors qu'un AUTRE ennemi y est debout, le natif emet et le
port rendait `[]`. Trois regimes, positions DRIVEES (`dir` calcule par le mirror de
`BattleQuery$$GetPositionMachineForPlayer`, puis RE-VERIFIE contre les tuiles reellement en feu).
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


def _build(state_file: Path, seed: int, extra: list, seed_bc: Path | None = None,
           board: str = BOARD) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", str(RANK),
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


def ctx_machine(sid, rid, cid):
    """`AiDecisionContext` d'un caster MACHINE -- `engine.ai.context.build_machine`, le mirror de
    `IdunBattle.AI.Tactics.DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`.

    C'est la fonction que le spine appelle DEJA pour une MoW (`engine_validate.py` :
    `if machine_row(dv, uid) is not None: build_machine(...)`). `build`, elle, est celle des UNITES
    et rend `me = None` sur une Machine -- ce qui est CORRECT (le natif expose les MoW dans un canal
    `.mows` separe de `.units`), et n'a jamais voulu dire que le port ignorait les MoW."""
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, rid, m, b, t)                              # noqa: E731
    dv = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 8}, 180)
    return AICTX.build_machine(rpc, rid, dv, int(cid), W.load(),
                               _scene.build_predictor(rpc, rid)), dv


def _move(sid, rid, uid, col, row):
    return _r(sid, rid, "applyAction",
              {"action": {"kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}})


# ------------------------------------------------- etape 1 : la MoW REELLE comme caster (constat)

def step1_mow_caster(seed: int = 35030, verbose: bool = True) -> dict:
    """Deploie la MoW pour de vrai (`--a-mow`), pose des summons en face, et MESURE ce que
    l'oracle et le port rendent avec elle comme caster.

    ⚠ RE-MESURE #360 -- ce que cette etape croyait constater a ete tranche, et dans l'autre sens :

      * l'oracle n'etait pas ferme par le caster Machine mais par la SUBSTITUTION de la
        `UnitPosition` de la CIBLE que faisait `rpc-predict.ts`. Le natif, lui, passe
        `UnitPosition$$NullPosition()` (`DefaultMachineTactic`). Le MEME
        `<X>Playbook$$MakeDamagePredictions` invoque avec la position du CASTER
        (`ncPlaybookPredict(via = "makeDamagePredictions")`) REND l'event -- mesure : `(324, 492, 6)`,
        exactement ce que rendait la voie GREFFE ;
      * le port a un contexte pour une MoW depuis `engine.ai.context.build_machine`. C'est `build`
        (la fonction des UNITES) qui rend `me = None`, et c'est correct : `decisionView.units` ne
        contient jamais de Machine.

    L'etape mesure donc les DEUX oracles et les DEUX constructeurs de contexte, et son verdict est
    l'ACCORD des oracles -- pas le silence de l'un d'eux. Elle reste valide AVANT comme APRES la
    fenetre de reinject qui portera le correctif : `aiPlaybookPredict` publie `posSrc`, et
    `machine:*` signe le bundle corrige."""
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
        # On pose deux summons (self-cast), PUIS on redemande -- aux DEUX oracles.
        _r(sid, rid, "applyAction",
           {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                       "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
        ids2, _dv2 = _ids(sid, rid)
        smn = sorted(uid for vis, uid in ids2.items() if str(vis).startswith("deathPox"))
        out["summons"] = smn
        if smn:
            hot = _r(sid, rid, "aiPlaybookPredict",
                     {"unitId": cid, "targetId": smn[0], "abilityType": 1147})
            out["hot"] = {"count": hot.get("count"), "listNull": hot.get("listNull"),
                          "posSrc": hot.get("posSrc"),
                          "events": [(e.get("healthDmgMin"), e.get("healthDmgMax"),
                                      e.get("appliedHits")) for e in (hot.get("events") or [])]}
            # L'oracle qui passe la position du CASTER (= `NullPosition` pour une MoW). Il ne
            # depend PAS du correctif de `rpc-predict.ts` : il est deja dans le bundle.
            nc = _r(sid, rid, "ncPlaybookPredict",
                    {"unitId": cid, "targetId": smn[0], "abilityType": 1147,
                     "via": "makeDamagePredictions"}, 240)
            out["hot_nc"] = {"returnedCount": nc.get("returnedCount"), "posSrc": nc.get("posSrc"),
                             "error": nc.get("error"),
                             "events": [(e.get("healthDmgMin"), e.get("healthDmgMax"),
                                         e.get("appliedHits"))
                                        for e in (nc.get("returned") or [])]}
        # Cote PORT : `build` (unites) rend None -- correct, une Machine n'est pas dans `.units` ;
        # `build_machine` (machines) rend le contexte REEL.
        try:
            ctx, _ = P344._ctx(sid, rid, cid)
            out["port_ctx_me"] = None if ctx.me is None else ctx.me.get("visualId")
        except Exception as e:                                   # noqa: BLE001 -- on RAPPORTE
            out["port_ctx_me"] = "exception: %s" % type(e).__name__
        try:
            ctxm, _ = ctx_machine(sid, rid, cid)
            out["port_machine_ctx_me"] = None if ctxm.me is None else ctxm.me.get("visualId")
            out["port_machine_abilities"] = [a.get("id") for a in (ctxm.me or {}).get("abilities", [])]
            out["port_machine_scene_ctx"] = (ctxm.scene is not None
                                             and ctxm.scene.ctx(cid) is not None)
        except Exception as e:                                   # noqa: BLE001
            out["port_machine_ctx_me"] = "exception: %s" % type(e).__name__
            out["port_machine_scene_ctx"] = None
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    hot, hot_nc = (out.get("hot") or {}), (out.get("hot_nc") or {})
    # Le bundle Frida injecte porte-t-il le correctif #360 ? `posSrc` le SIGNE (`machine:*`).
    out["bundle_has_360_fix"] = str(hot.get("posSrc") or "").startswith("machine:")
    # VERDICT. L'oracle par la position du CASTER doit repondre -- il ne depend d'aucune fenetre.
    # `aiPlaybookPredict` n'est exige d'ACCORDER que si le bundle porte le correctif ; sinon on
    # constate (et on IMPRIME) qu'il rend `null`, sans en faire un echec ni une verite durable.
    oracle_ok = (not hot_nc.get("error")) and bool(hot_nc.get("events"))
    ai_ok = (hot.get("events") == hot_nc.get("events")) if out["bundle_has_360_fix"] else True
    out["oracles_agree"] = bool(oracle_ok and ai_ok)
    out["ok"] = bool(out["deployed"] and out["abilities"]
                     and out["cold"]["count"] == 0
                     and out["oracles_agree"]
                     and out.get("port_machine_ctx_me") == MOW)
    if verbose:
        print("\n[350r3b/1] la MoW %s COMME CASTER" % MOW)
        print("  deployee               : %s (casterId=%s, abilities=%s)"
              % (out["deployed"], out["caster_id"], out["abilities"]))
        print("  1147 sans summon       : count=%s listNull=%s abilityState=%s"
              % (out["cold"]["count"], out["cold"]["listNull"], out["cold"]["abilityState"]))
        print("  summons poses          : %s" % out.get("summons"))
        print("  1147 aiPlaybookPredict : count=%s listNull=%s posSrc=%s events=%s"
              % (hot.get("count"), hot.get("listNull"), hot.get("posSrc"), hot.get("events")))
        print("  1147 ncPlaybookPredict : returned=%s posSrc=%s err=%s events=%s"
              % (hot_nc.get("returnedCount"), hot_nc.get("posSrc"), hot_nc.get("error"),
                 hot_nc.get("events")))
        print("  bundle porte le fix #360 : %s" % out["bundle_has_360_fix"])
        print("  contexte PORT build()         : ctx.me = %s (None ATTENDU : canal .units)"
              % out["port_ctx_me"])
        print("  contexte PORT build_machine() : ctx.me = %s | abilities=%s | scene.ctx=%s"
              % (out.get("port_machine_ctx_me"), out.get("port_machine_abilities"),
                 out.get("port_machine_scene_ctx")))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
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


# ------------------------------------ etape 4 : le volet AoE de 1147 (natif N events, port N ?)

class _MontageError(RuntimeError):
    """Le MONTAGE n'a pas atteint son regime (pas assez de summons) -- distinct d'un desaccord de
    port : on le RAPPORTE tel quel, on ne le maquille pas en mesure."""


def _port_events(scene, cid, tid, here, shipped: bool):
    """Events du PORT pour 1147. `shipped = False` = le port d'AVANT #359 (aucun set AoE pour 1147,
    aucun gate de selecteur) -- reconstitue en RETIRANT les deux entrees de registre, jamais en
    re-implementant quoi que ce soit."""
    from engine.playbook.prediction import abilities as PA
    import engine.entities.abilities.active_ability as AA
    gate, klass = PA._MAKE_DMG_TARGET_GATE, AA._SPECIAL_ABILITY_CLASSES
    if not shipped:
        PA._MAKE_DMG_TARGET_GATE = {k: v for k, v in gate.items() if k != 1147}
        AA._SPECIAL_ABILITY_CLASSES = {k: v for k, v in klass.items() if k != "HadesAutocannons"}
    try:
        evs = PA.make_damage_predictions(scene, int(cid), int(tid), 1147, "HadesAutocannons",
                                         attack_pos=here)
    finally:
        PA._MAKE_DMG_TARGET_GATE, AA._SPECIAL_ABILITY_CLASSES = gate, klass
    return [{"target": e.target,
             "dmg": (e.prediction.accurate_health_damage.min,
                     e.prediction.accurate_health_damage.max, e.prediction.applied_hits)}
            for e in evs]


def _native_events(sid, rid, cid, tid):
    r = _r(sid, rid, "aiPlaybookPredict",
           {"unitId": int(cid), "targetId": int(tid), "abilityType": 1147}, 120)
    return [{"target": e.get("targetId"),
             "dmg": (e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))}
            for e in ((r or {}).get("events") or [])]


SUMMON_LEVEL = 50        # `Poxwalkers` : chance/chance_2 = 20/45 des le niveau 40 (gameconfig, relu)


def step4_aoe_1147(seed: int = 35060, verbose: bool = True) -> dict:
    """#359 -- le natif emet UN event PAR ENTITE du selecteur `HadesAutocannonsAbility$$GetAllTargets`
    (les summons du camp de la CIBLE, dans son disque `range`, cible INCLUSE) ; le port n'en emettait
    qu'UN. Quatre regimes, sur le MEME runner, chacun mesure natif / port AVANT / port APRES :

      R0  AUCUN summon en jeu (avant le cast du summoner) -> selecteur VIDE, natif 0 event. C'est le
          regime que #350-r3 a mesure 16 fois, et celui ou le port d'AVANT inventait un event.
      R1  cible = un summon, les AUTRES summons dans son disque -> natif = |selecteur| >= 2. C'est le
          volet manquant, et son compte est le verdict.
      R2  le PORTEUR (camp du caster) amene AU CONTACT des summons -> le compte ne bouge PAS :
          `Friends(of: Target)` reference la CIBLE, donc une unite du camp du CASTER n'entre jamais
          dans l'ensemble. Discrimine le REFERENT d'equipe, que le montage R1 laisse ambigu (le
          summoner et les summons y sont du meme camp).
      R3  cible = une unite NON-summon (le summoner, qui est POURTANT au centre du nuage de summons)
          -> `UnitsWithTrait(2 = Summon)` la refuse. Ce que le natif rend ICI dit s'il boucle sur SON
          selecteur meme quand la cible n'y est pas.

    MONTAGE. Le nombre de poxwalkers est un TIRAGE natif : `SpawnPoxwalkersAbility$$ExecuteBehaviour`
    = `Divide(RandomAmount(cnt x chance, cnt x chance_2), 100, Ceiling)` ou `cnt` = le nombre de
    tuiles LIBRES du disque `CalculateRange(TurnsStarted)` (= 1 aux tours 1-2). A niveau >= 40,
    chance/chance_2 = 20/45 : il faut donc `cnt = 6` (anneau ENTIEREMENT libre) pour que la borne
    BASSE elle-meme, `ceil(6 x 20 / 100) = 2`, garantisse deux summons. D'ou le montage : le summoner
    seul au centre, tout le monde d'abord ECARTE -- le porteur n'est ramene au contact qu'en R2, une
    fois les summons poses."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = _graft_seed_bc([1147], GRAFT_ON, "1147")
    sf = LOGS / "p350r3b_step4.json"
    rid = None
    out: dict = {}
    try:
        rid = _build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
                                "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                               "AbilityVariablesMultiplierPercentage=100"
                                               % (GRAFT_ON, A1147_LVL_A),
                                "--unit-stat", "%s:ActiveAbilityLevel=%d"
                                               % (SUMMONER, SUMMON_LEVEL)], seed_bc=seed_bc)
        ids, _dv = _ids(sid, rid)
        # GEOMETRIE DRIVEE : le summoner SEUL au centre. Personne d'autre ne bouge -- leurs spawns
        # sont hors de son anneau, ce que la mesure de `ring_occupied` ci-dessous VERIFIE.
        _move(sid, rid, ids[SUMMONER], *CENTER)
        ob0 = _r(sid, rid, "observeBattle", {}, 120)
        pos0 = {int(u["squadId"]): (u["col"], u["row"])
                for u in (ob0.get("units") or []) if not u.get("isDead")}
        import hexgeo
        out["ring_occupied"] = sorted(uid for uid, p in pos0.items()
                                      if uid != ids[SUMMONER]
                                      and hexgeo.distance(p, CENTER) <= 1)

        def _regime(tag, tid):
            ctx, _d = P344._ctx(sid, rid, int(ids[GRAFT_ON]))
            mp = ctx.me.get("pos") or {}
            here = (mp.get("col"), mp.get("row"))
            ob = _r(sid, rid, "observeBattle", {}, 120)
            pos = {int(u["squadId"]): (u["col"], u["row"])
                   for u in (ob.get("units") or []) if not u.get("isDead")}
            return {"tag": tag, "target": tid, "positions": pos,
                    "native": _native_events(sid, rid, ids[GRAFT_ON], tid),
                    "port_before": _port_events(ctx.scene, ids[GRAFT_ON], tid, here, shipped=False),
                    "port_after": _port_events(ctx.scene, ids[GRAFT_ON], tid, here, shipped=True)}

        # R0 -- AUCUN summon en jeu : le selecteur est VIDE quelle que soit la cible, et le natif
        # n'emet RIEN (le regime mesure 16 fois par #350-r3). C'est le cas ou le port d'AVANT
        # inventait un event, et celui ou un port TROP permissif se verrait tout de suite.
        out["r0"] = _regime("R0 aucun summon en jeu", ids[SUMMONER])
        _r(sid, rid, "applyAction",
           {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                       "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
        _ids2, dv2 = _ids(sid, rid)
        # ⚠ `_ids` indexe par `visualId` : les DEUX poxwalkers y ecrasent la meme cle. Le compte de
        # summons se lit donc sur la LISTE `decisionView.units`, jamais sur ce dict.
        smn = sorted(int(u["id"]) for u in (dv2.get("units") or [])
                     if u.get("alive") and str(u.get("visualId") or "").startswith("deathPox"))
        out["summons"] = smn
        out["all_units"] = sorted((u.get("visualId"), u.get("id"))
                                  for u in (dv2.get("units") or []) if u.get("alive"))
        cid = ids[GRAFT_ON]
        if len(smn) < 2:
            out["error"] = ("montage : %d summon(s), il en faut 2 (anneau du summoner occupe par %s)"
                            % (len(smn), out["ring_occupied"]))
            raise _MontageError(out["error"])
        out["r1"] = _regime("R1 cible = summon, les autres summons dans son disque", smn[0])
        out["r3"] = _regime("R3 cible NON-summon (le summoner, au centre du nuage)", ids[SUMMONER])
        # R2 : le porteur (camp ADVERSE des summons) amene AU CONTACT. `Friends(of: Target)` doit
        # l'exclure -> meme compte qu'en R1.
        tgt_pos = next((p for uid, p in
                        {int(u["squadId"]): (u["col"], u["row"])
                         for u in ((_r(sid, rid, "observeBattle", {}, 120)).get("units") or [])
                         if not u.get("isDead")}.items() if uid == smn[0]), None)
        out["r2_target_pos"] = tgt_pos
        if tgt_pos is not None:
            import hexgeo as _hg
            for cand in _hg.disk(tgt_pos[0], tgt_pos[1], 1):
                if tuple(cand) == tuple(tgt_pos):
                    continue
                mv = _move(sid, rid, cid, cand[0], cand[1])
                if bool((mv.get("actions") or [{}])[0].get("ok")):
                    out["r2_caster_pos"] = tuple(cand)
                    break
        out["r2"] = _regime("R2 porteur (camp du caster) AU CONTACT des summons", smn[0])
    except _MontageError:
        pass                                   # le montage a echoue : on RAPPORTE, on n'invente pas
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    # Le verdict est DERIVE de la mesure : natif == port APRES sur les trois regimes, et le port
    # AVANT differe sur au moins un (sinon la garde ne verrouille rien).
    regs = [out[k] for k in ("r0", "r1", "r2", "r3") if k in out]
    out["after_matches_native"] = bool(regs) and all(r["port_after"] == r["native"] for r in regs)
    out["before_differed"] = any(r["port_before"] != r["native"] for r in regs)
    out["ok"] = bool(out["after_matches_native"] and out["before_differed"])
    if verbose:
        print("\n[350r3b/4] volet AoE de 1147 -- selecteur GetAllTargets (summons du camp de la CIBLE)")
        print("  summons : %s  | erreur: %s" % (out.get("summons"), out.get("error")))
        print("  unites  : %s" % out.get("all_units"))
        print("  anneau du summoner occupe par : %s" % out.get("ring_occupied"))
        print("  R2 : porteur deplace en %s (cible en %s)"
              % (out.get("r2_caster_pos"), out.get("r2_target_pos")))
        for k in ("r0", "r1", "r2", "r3"):
            r = out.get(k)
            if not r:
                continue
            print("\n  === %s ===  cible=%s" % (r["tag"], r["target"]))
            print("    positions : %s" % r["positions"])
            print("    natif       (%d ev) : %s" % (len(r["native"]), r["native"]))
            print("    port AVANT  (%d ev) : %s" % (len(r["port_before"]), r["port_before"]))
            print("    port APRES  (%d ev) : %s" % (len(r["port_after"]), r["port_after"]))
        print("\n  port APRES == natif sur les %d regimes : %s" % (len(regs),
                                                                  out["after_matches_native"]))
        print("  port AVANT differait                  : %s" % out["before_differed"])
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


# --------------- etape 5 : GENERALISATION -- autre board, caster ALLIE des summons

GEN_BOARD = "MC1_15"     # board DIFFERENT de celui des etapes 0-4 (geometrie et spawns distincts)
GEN_GRAFT_ON = P_FILLER  # `deathPutrifier` : meme camp que le summoner, donc ALLIE des summons


def step5_generalize_1147(seed: int = 35090, verbose: bool = True) -> dict:
    """#359, generalisation. Le selecteur de 1147 ne lit RIEN du caster -- `Friends(of: Target)` et
    `SurroundingUnits(Target, range)` referencent tous deux la CIBLE. Un caster ALLIE des summons
    doit donc rendre le MEME ensemble qu'un caster ennemi.

    Ce n'est pas une redite de l'etape 4 : la-bas le caster est du camp OPPOSE aux summons, si bien
    qu'un port qui aurait (a tort) reference le CASTER aurait rendu ZERO -- l'ecart etait visible.
    Ici c'est l'inverse : un port qui filtrerait les cibles ENNEMIES du caster (le reflexe naturel
    pour une ability offensive, et ce que disent ses `TargetingOptions`) rendrait zero ALORS QUE LE
    NATIF EMET. Les deux montages ensemble bornent le referent des deux cotes.

    Board DIFFERENT (`MC1_15`) : la geometrie de spawn, le nombre de tuiles libres autour du
    summoner -- donc le NOMBRE de summons -- et les distances changent. Un accord qui ne tiendrait
    que sur `MC1_67` serait un sur-ajustement au montage."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = _graft_seed_bc([1147], GEN_GRAFT_ON, "1147gen")
    sf = LOGS / "p350r3b_step5.json"
    rid = None
    out: dict = {"board": GEN_BOARD, "caster_visual": GEN_GRAFT_ON}
    try:
        sfp = sf
        sfp.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
               "--state-file", str(sfp), "--board", GEN_BOARD, "--rank", str(RANK),
               "--crit", "0,0", "--block-target", "0,0", "--no-ai",
               "--p-units", "%s,%s" % (SUMMONER, GEN_GRAFT_ON),
               "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
               "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=100"
                              % (GEN_GRAFT_ON, A1147_LVL_A),
               "--unit-stat", "%s:ActiveAbilityLevel=%d" % (SUMMONER, SUMMON_LEVEL),
               "--seed-bc", str(seed_bc)]
        proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if not sfp.exists():
            raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        rid = int(json.loads(sfp.read_text())["runnerId"])
        ids, _dv = _ids(sid, rid)
        # Le summoner s'isole : c'est le nombre de tuiles LIBRES de son anneau qui fixe le compte de
        # summons (`ceil(cnt x chance / 100)`). On prend la tuile la plus degagee qu'il peut atteindre.
        import hexgeo
        ob0 = _r(sid, rid, "observeBattle", {}, 120)
        pos0 = {int(u["squadId"]): (u["col"], u["row"])
                for u in (ob0.get("units") or []) if not u.get("isDead")}
        mov = _r(sid, rid, "aiMovableTiles", {}, 90)
        cand = []
        for u in (mov.get("units") or []):
            if int(u.get("unitId") or -1) != int(ids[SUMMONER]):
                continue
            for t in (u.get("tiles") or []):
                p = (t.get("col"), t.get("row"))
                if None in p:
                    continue
                busy = sum(1 for uid, q in pos0.items()
                           if uid != ids[SUMMONER] and hexgeo.distance(q, p) <= 1)
                cand.append((busy, p))
        cand.sort()
        out["summoner_tile"] = cand[0][1] if cand else pos0.get(int(ids[SUMMONER]))
        out["neighbours_busy"] = cand[0][0] if cand else None
        if cand:
            _move(sid, rid, ids[SUMMONER], *cand[0][1])
        _r(sid, rid, "applyAction",
           {"action": {"kind": "ability", "casterId": ids[SUMMONER],
                       "targetId": ids[SUMMONER], "abilityType": SPAWN_POXWALKERS}}, 180)
        _ids2, dv2 = _ids(sid, rid)
        smn = sorted(int(u["id"]) for u in (dv2.get("units") or [])
                     if u.get("alive") and str(u.get("visualId") or "").startswith("deathPox"))
        out["summons"] = smn
        if not smn:
            out["error"] = "montage : aucun summon pose sur %s" % GEN_BOARD
            raise _MontageError(out["error"])
        cid = ids[GEN_GRAFT_ON]
        ctx, _d = P344._ctx(sid, rid, cid)
        mp = ctx.me.get("pos") or {}
        here = (mp.get("col"), mp.get("row"))
        out["native"] = _native_events(sid, rid, cid, smn[0])
        out["port_after"] = _port_events(ctx.scene, cid, smn[0], here, shipped=True)
        out["port_before"] = _port_events(ctx.scene, cid, smn[0], here, shipped=False)
        out["caster_team_is_target_team"] = (ctx.scene.team(cid) == ctx.scene.team(smn[0]))
        ob = _r(sid, rid, "observeBattle", {}, 120)
        out["summon_positions"] = {int(u["squadId"]): (u["col"], u["row"])
                                   for u in (ob.get("units") or [])
                                   if not u.get("isDead") and int(u["squadId"]) in smn}
    except _MontageError:
        pass
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    # L'ENSEMBLE et les valeurs -- pas la sequence : le port ne mirrore PAS les noeuds de tri du
    # selecteur (`SortByRow` / `SortReverse` sous `If(IsTopPlayer)`), et l'utilite les ignore
    # (`CalculateUtilityFromPredictions` SOMME). Ce montage-ci le MESURE : le natif ordonne autrement.
    _bag = (lambda evs: sorted((e["target"], tuple(e["dmg"])) for e in (evs or [])))
    out["order_native"] = [e["target"] for e in (out.get("native") or [])]
    out["order_port"] = [e["target"] for e in (out.get("port_after") or [])]
    out["same_bag"] = bool(out.get("native")) and _bag(out.get("port_after")) == _bag(out.get("native"))
    out["same_order"] = out["order_native"] == out["order_port"]
    out["ok"] = bool(out["same_bag"] and out.get("caster_team_is_target_team") is True
                     and _bag(out.get("port_before")) != _bag(out.get("native")))
    if verbose:
        print("\n[350r3b/5] GENERALISATION -- board %s, caster %s (ALLIE des summons)"
              % (GEN_BOARD, GEN_GRAFT_ON))
        print("  tuile du summoner : %s (voisins occupes : %s) | summons : %s @ %s"
              % (out.get("summoner_tile"), out.get("neighbours_busy"), out.get("summons"),
                 out.get("summon_positions")))
        print("  caster allie de la cible : %s" % out.get("caster_team_is_target_team"))
        print("  natif      (%s ev) : %s" % (len(out.get("native") or []), out.get("native")))
        print("  port APRES (%s ev) : %s" % (len(out.get("port_after") or []), out.get("port_after")))
        print("  port AVANT (%s ev) : %s" % (len(out.get("port_before") or []),
                                             out.get("port_before")))
        print("  meme ENSEMBLE : %s | meme SEQUENCE : %s (le tri du selecteur n'est pas porte)"
              % (out["same_bag"], out["same_order"]))
        print("  erreur : %s" % out.get("error"))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


# ------------- etape 6 : le pendant AoE de 1148 (#359-r1) -- cible HORS zone de feu

def _fire_positions(scene) -> set:
    """Positions portant `Fire` -- `Scene.tile_effects_by_pos` est indexee par NOM d'effet (tileMeta
    `effects[].name`), jamais par id : meme cle que `_daemonic_ordnance_target_gate`."""
    from engine.entities.effect_type import EffectType
    fx = scene.tile_effects_by_pos or {}
    return {tuple(p) for p, names in fx.items() if EffectType.Fire.name in (names or [])}


def _triangle_dir(groups, team) -> int:
    """`dir` de `DaemonicOrdnanceAbility$$GetTargetAreaTiles` =
    `If(IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4))`, calcule PAR LE MIRROR de la
    cascade native (`BattleQuery$$GetPositionMachineForPlayer`), jamais suppose. Le probe le
    RE-VERIFIE ensuite contre les tuiles REELLEMENT en feu apres le cast."""
    from engine.services.machine_of_war_position import machine_of_war_position_for_player
    if groups is None or team is None:
        return None
    return 1 if int(machine_of_war_position_for_player(groups, int(team))) == 2 else 4


def _port_events_1148(scene, cid, tid, here, shipped: bool):
    """Events du PORT pour 1148. `shipped = False` = le port d'AVANT #359-r1 -- reconstitue en
    RETIRANT l'entree `DaemonicOrdnance` de `_SPECIAL_ABILITY_CLASSES` (donc `get_aoe_targets` rend
    `[]`, l'etat exact d'avant cette tranche), jamais re-implemente. Le gate de selecteur
    `_MAKE_DMG_TARGET_GATE[1148]`, lui, est ANTERIEUR (#350-r3) : il reste arme des deux cotes."""
    from engine.playbook.prediction import abilities as PA
    import engine.entities.abilities.active_ability as AA
    klass = AA._SPECIAL_ABILITY_CLASSES
    if not shipped:
        AA._SPECIAL_ABILITY_CLASSES = {k: v for k, v in klass.items() if k != "DaemonicOrdnance"}
    try:
        evs = PA.make_damage_predictions(scene, int(cid), int(tid), 1148, "DaemonicOrdnance",
                                         attack_pos=here)
    finally:
        AA._SPECIAL_ABILITY_CLASSES = klass
    return [{"target": e.target,
             "dmg": (e.prediction.accurate_health_damage.min,
                     e.prediction.accurate_health_damage.max, e.prediction.applied_hits)}
            for e in evs]


def _ctx_with_groups(sid, rid, cid, groups):
    """`AiDecisionContext` du caster AVEC ses `SpawnPointGroups`.

    `probe_344._ctx` ne les passe pas -- il n'en a pas besoin pour l'arrondi. Ici c'est CENTRAL : sans
    eux, `AiDecisionContext.machine_of_war_position` retombe sur le slot d'une MoW DEPLOYEE
    (`decisionView.mows`), et le montage GREFFE n'en a aucune -> `None` -> le predicat
    `IsPositionMachineForCurrentPlayer` rend False -> `dir = 4` au lieu de 1, donc la MAUVAISE
    zone-triangle. C'est le residu d'outillage nomme par `case-302` : aucun RPC n'expose les groupes
    par runner, l'appelant qui monte le runner les LIT dans le state-file."""
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, rid, m, b, t)                              # noqa: E731
    dv = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 8}, 180)
    mov = _r(sid, rid, "aiMovableTiles", {}, 90)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid), spawn_groups=groups), dv


def _aoe_stages_1148(scene, cid, tid) -> dict:
    """DECOMPOSITION PAR ETAGE du set AoE de 1148 -- pour qu'un desaccord designe l'etage FAUTIF au
    lieu d'un `[]` muet. Chaque ligne est un noeud de l'arbre natif, evalue sur le MEME contexte que
    `make_damage_predictions`."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.active_ability import (active_ability_for,
                                                          DaemonicOrdnanceAbility)
    from engine.playbook.prediction import abilities as PA
    from engine import dsl
    by_id = {u.get("id"): u for u in scene.units}
    cfg = AbilityConfiguration.from_gameconfig("DaemonicOrdnance", GC.ability("DaemonicOrdnance"))
    ctx0 = scene.ctx(int(cid))
    ab = active_ability_for("DaemonicOrdnance", 1148, ctx0, cfg,
                            ability_state=scene.ability_state(int(cid), 1148))
    the = PA._tile_has_effect_from_scene(scene)
    dctx = dsl.DslContext(units=scene.units, caster=by_id.get(int(cid)), target=by_id.get(int(tid)),
                          config=cfg, ability_level=(ab.level if ab else 0),
                          board=scene.board, elev_by_pos=scene.elev_by_pos,
                          tile_has_effect=the,
                          current_player_machine_position=getattr(
                              scene, "machine_of_war_position", None))
    area = DaemonicOrdnanceAbility._AREA.evaluate(dctx)
    coord = (lambda t: tuple(scene.board.coord(t)) if scene.board is not None else t)
    burning = [t for t in area if the is not None and the(t, 5)]
    # Le TRIANGLE BRUT (avant `TilesOnSameElevation`) + l'elevation de chaque tuile : c'est ce qui
    # permet de dire, quand le natif allume MOINS de tuiles que le port n'en met dans `area`, si
    # l'ecart vient du filtre d'elevation ou d'une tuile hors plateau.
    raw = DaemonicOrdnanceAbility._AREA.tiles.evaluate(dctx)
    return {"class_routed": type(ab).__name__ if ab is not None else None,
            "board": scene.board is not None,
            "mow_position": getattr(scene, "machine_of_war_position", None),
            "tile_has_effect_wired": the is not None,
            "triangle_raw": [coord(t) for t in raw],
            "elev": {str(coord(t)): scene.board.elevation(t) for t in raw} if scene.board else {},
            # La tuile est-elle PROJETEE par `tileMeta` ? Une tuile absente de la carte n'est pas
            # « sans feu » : elle est NON OBSERVEE -- distinction indispensable pour ne pas lire un
            # trou de canal comme un verdict du natif.
            "in_tilemeta": {str(coord(t)): (coord(t) in (scene.tile_effects_by_pos or {}))
                            for t in raw},
            "walkable": ({str(coord(t)): bool(scene.board.walkable(t)) for t in raw}
                         if scene.board is not None else {}),
            "area": [coord(t) for t in area],
            "burning": [coord(t) for t in burning],
            "aoe": [u.get("id") for u in (ab.get_aoe_targets(dctx) if ab is not None else [])]}


def _native_events_1148(sid, rid, cid, tid):
    r = _r(sid, rid, "aiPlaybookPredict",
           {"unitId": int(cid), "targetId": int(tid), "abilityType": 1148}, 120)
    return [{"target": e.get("targetId"),
             "dmg": (e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))}
            for e in ((r or {}).get("events") or [])]


GEN_BOARD_DIR4 = "C1_15"   # `MachineOfWarPosition(team 1) = 0` -> l'AUTRE branche du `If` (dir = 4)


def step6_aoe_1148(seed: int = 35100, board: str = BOARD, verbose: bool = True,
                   tag: str = "6") -> dict:
    """#359-r1 -- `DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur
    `GetEntitiesFromSelector(DaemonicOrdnanceAbility$$GetAllDamageableTargets, ...)` =

        Enemies( Caster,
                 Units( Filter( GetTargetAreaTiles(), HasEffect(Subject, 5 = Fire) ), unique ) )

    L'ensemble est ancre sur la CIBLE (`GetTargetAreaTiles` = `TilesOnSameElevation(Target,
    TilesInTriangleShape(Target, dir), 1)`), donc il peut contenir des ennemis que la cible demandee
    n'est PAS. #350-r3 n'avait porte que le gate de la cible PRINCIPALE ; le SET, lui, restait vide
    (`AActiveAbility.get_aoe_targets` -> `[]`).

    MONTAGE PILOTE (positions DRIVEES, jamais subies) :
      * `dir` est calcule par le mirror de `BattleQuery$$GetPositionMachineForPlayer` sur les
        `SpawnPointGroups` de la BC REELLEMENT executee, puis RE-VERIFIE contre les tuiles en feu ;
      * A (`necroWarden`) est pose sur l'ancre `PA`, B (`worldKharn`) sur `PB` = la voisine de `PA`
        dans la direction OPPOSEE a un cote du triangle -> `PA` appartient au triangle de `PB`, et
        `PB` n'appartient PAS a celui de `PA` (donc elle ne prend pas feu) ;
      * un premier cast sur `PA` allume `{PA, n1, n2}` -- c'est l'etage [5] `AddEffect(Fire -> zone)`
        du behaviour, la seule voie qui pose ce feu.

    TROIS REGIMES, sur le MEME runner :
      RA  cible = A, qui brule -> 1 event (regime deja couvert par l'etape 3, re-mesure ici) ;
      RB  cible = B, tuile FROIDE, A brulant DANS son triangle -> le natif emet pour A, la cible
          demandee n'y figurant pas. C'est LE regime du pendant AoE ;
      RC  B ramene sur une tuile EN FEU du triangle de A, cible = A -> DEUX events, un par ennemi.
          Verrouille l'ENSEMBLE et les VALEURS (chaque event est predit contre SON ennemi)."""
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = _graft_seed_bc([1148], SUMMONER, "1148")
    sf = LOGS / ("p350r3b_step%s.json" % tag)
    rid = None
    out: dict = {"board": board}
    try:
        # DEUX leviers de PILOTAGE, tous deux requis pour que l'accord dise autre chose que « meme
        # ensemble » :
        #  * niveau 50 (minDmg/maxDmg = 997/1330, relus du gameconfig) -- au niveau 2 les bornes
        #    saturent au PLANCHER sur les DEUX ennemis (`(3, 3, 3)`), parce que `param_8 = null`
        #    donne pierce 0 (armure PLEINE) et que l'armure du rank 17 depasse le degat ;
        #  * armures DIFFERENTES par ennemi (`--unit-stat` ecrit `Armor`/`FixedArmor` dans le BC
        #    normalise) : c'est ce qui SEPARE les bornes des deux events de RC. Sans cela, un port
        #    qui recopierait la prediction de la cible principale sur chaque membre du set passerait.
        rid = _build(sf, seed, ["--p-units", "%s,%s" % (SUMMONER, P_FILLER),
                                "--a-units", "%s,%s" % (GRAFT_ON, A_FILLER),
                                "--unit-stat", "%s:ActiveAbilityLevel=50,"
                                               "AbilityVariablesMultiplierPercentage=100"
                                               % SUMMONER,
                                "--unit-stat", "%s:Armor=0,FixedArmor=0" % GRAFT_ON,
                                "--unit-stat", "%s:Armor=500,FixedArmor=500" % A_FILLER],
                     seed_bc=seed_bc, board=board)
        from engine.services.machine_of_war_position import spawn_groups_from_battle_config
        from engine.ai.context import _current_player_team
        from engine.entities.selectors.geometry import (neighbour_at,
                                                        _TRIANGLE_SHAPE_DIRECTIONS)
        bc = json.loads(sf.read_text(encoding="utf-8")).get("bc") or {}
        groups = spawn_groups_from_battle_config(bc)
        ids, dv = _ids(sid, rid)
        team = _current_player_team(dv)
        d = _triangle_dir(groups, team)
        out["spawn_groups"] = groups
        out["current_player_team"] = team
        out["dir_expected"] = d
        if d is None:
            out["error"] = "SpawnPointGroups non lus -> `dir` indecidable, montage abandonne"
            raise _MontageError(out["error"])
        dirs = _TRIANGLE_SHAPE_DIRECTIONS[d]
        pa = CENTER                                       # ancre : la tuile que le cast allume
        pb = neighbour_at(pa[0], pa[1], (dirs[0] + 3) % 6)  # PA est dans le triangle de PB
        fire_expected = {tuple(pa)} | {tuple(neighbour_at(pa[0], pa[1], k)) for k in dirs}
        # Le caster se pose sur une voisine de PA qui n'est NI dans la zone de feu NI la tuile de B.
        cpos = next((tuple(neighbour_at(pa[0], pa[1], k)) for k in range(6)
                     if tuple(neighbour_at(pa[0], pa[1], k)) not in fire_expected
                     and tuple(neighbour_at(pa[0], pa[1], k)) != tuple(pb)), None)
        out["pa"], out["pb"], out["caster_pos"] = tuple(pa), tuple(pb), cpos
        out["fire_expected"] = sorted(fire_expected)
        cid, a_id, b_id = ids[SUMMONER], ids[GRAFT_ON], ids[A_FILLER]
        out["moves"] = {}
        for who, uid, to in (("A", a_id, pa), ("caster", cid, cpos),
                             ("B", b_id, tuple(pb)),
                             ("filler", ids[P_FILLER], (pa[0] - 2, pa[1] - 2))):
            mv = _move(sid, rid, uid, to[0], to[1])
            out["moves"][who] = {"to": tuple(to),
                                 "ok": bool((mv.get("actions") or [{}])[0].get("ok")),
                                 "error": (mv.get("actions") or [{}])[0].get("error")}
        if not all(out["moves"][t]["ok"] for t in ("A", "caster", "B")):
            out["error"] = "placement KO : %s" % out["moves"]
            raise _MontageError(out["error"])

        def _regime(tag, tid):
            ctx, _d = _ctx_with_groups(sid, rid, int(cid), groups)
            mp = ctx.me.get("pos") or {}
            here = (mp.get("col"), mp.get("row"))
            ob = _r(sid, rid, "observeBattle", {}, 120)
            pos = {int(u["squadId"]): (u["col"], u["row"])
                   for u in (ob.get("units") or []) if not u.get("isDead")}
            return {"tag": tag, "target": tid, "positions": pos,
                    "fire": sorted(_fire_positions(ctx.scene)),
                    "stages": _aoe_stages_1148(ctx.scene, cid, tid),
                    "native": _native_events_1148(sid, rid, cid, tid),
                    "port_before": _port_events_1148(ctx.scene, cid, tid, here, shipped=False),
                    "port_after": _port_events_1148(ctx.scene, cid, tid, here, shipped=True)}

        # Le cast POSE le feu (etage [5] du behaviour). Zone froide -> aucun degat : les deux
        # ennemis survivent, ce que la mesure des positions confirme.
        cast = _r(sid, rid, "applyAction",
                  {"action": {"kind": "ability", "casterId": cid,
                              "to": {"col": pa[0], "row": pa[1]}, "abilityType": 1148}}, 180)
        out["cast_ok"] = bool((cast.get("actions") or [{}])[0].get("ok"))
        out["cast_error"] = (cast.get("actions") or [{}])[0].get("error")
        if not out["cast_ok"]:
            out["error"] = "cast 1148 refuse : %s" % out["cast_error"]
            raise _MontageError(out["error"])
        out["ra"] = _regime("RA cible = A, sa tuile BRULE", a_id)
        # VERIFICATION du `dir` calcule : les tuiles reellement allumees doivent etre INCLUSES dans
        # le triangle attendu, et la tuile-centre en faire partie. L'inclusion (et non l'egalite) est
        # ce que le natif garantit : une voisine du triangle peut manquer -- hors plateau, ou ecartee
        # par `TilesOnSameElevation` -- et c'est OBSERVE sur `C1_15` (2 tuiles allumees sur 3). Le
        # `dir` reste tranche : les tuiles allumees d'une AUTRE direction ne s'y trouveraient pas.
        out["fire_measured"] = out["ra"]["fire"]
        _fire_meas = set(map(tuple, out["ra"]["fire"]))
        out["dir_confirmed"] = bool(_fire_meas) and _fire_meas <= fire_expected \
            and tuple(pa) in _fire_meas
        out["area_extra_vs_native"] = sorted(fire_expected - _fire_meas)
        out["rb"] = _regime("RB cible = B (tuile FROIDE), A brule dans SON triangle", b_id)
        # RC : B ramene sur une tuile REELLEMENT EN FEU du triangle de A (mesuree, pas attendue) ->
        # deux ennemis dans l'ensemble.
        b_hot = next((p for p in sorted(_fire_meas) if tuple(p) != tuple(pa)), None)
        out["b_hot_pos"] = tuple(b_hot) if b_hot else None
        out["b_hot_ok"] = False
        if b_hot is not None:
            mvb = _move(sid, rid, b_id, b_hot[0], b_hot[1])
            out["b_hot_ok"] = bool((mvb.get("actions") or [{}])[0].get("ok"))
            out["b_hot_error"] = (mvb.get("actions") or [{}])[0].get("error")
        if out["b_hot_ok"]:
            out["rc"] = _regime("RC deux ennemis sur tuiles EN FEU, cible = A", a_id)
    except _MontageError:
        pass
    finally:
        if rid is not None:
            _r(sid, rid, "disposeRunner", {}, 30)
    regs = [out[k] for k in ("ra", "rb", "rc") if k in out]
    _bag = (lambda evs: sorted((e["target"], tuple(e["dmg"])) for e in (evs or [])))
    out["after_matches_native"] = bool(regs) and all(_bag(r["port_after"]) == _bag(r["native"])
                                                     for r in regs)
    out["before_differed"] = any(_bag(r["port_before"]) != _bag(r["native"]) for r in regs)
    # L'accord doit porter sur les VALEURS, pas seulement sur l'ENSEMBLE : si les deux events de RC
    # rendaient les MEMES bornes, un port qui recopierait la prediction de la cible principale sur
    # chaque membre du set passerait. On EXIGE donc que RC les separe (armures distinctes).
    _rc = [tuple(e["dmg"]) for e in ((out.get("rc") or {}).get("native") or [])]
    out["values_discriminate"] = len(_rc) >= 2 and len(set(_rc)) >= 2
    out["ok"] = bool(out["after_matches_native"] and out["before_differed"]
                     and out.get("dir_confirmed") is True and out["values_discriminate"])
    if verbose:
        print("\n[350r3b/%s] pendant AoE de 1148 -- selecteur GetAllDamageableTargets (board %s)"
              % (tag, board))
        print("  SpawnPointGroups : %s | team courante : %s"
              % ([(g.get("TeamWithPlayerIndex"), g.get("MachineOfWarPosition"))
                  for g in (out.get("spawn_groups") or [])] or "NON LUS",
                 out.get("current_player_team")))
        print("  dir attendu=%s | zone attendue=%s | ALLUMEE=%s | confirme=%s | non allumee=%s"
              % (out.get("dir_expected"), out.get("fire_expected"), out.get("fire_measured"),
                 out.get("dir_confirmed"), out.get("area_extra_vs_native")))
        print("  B sur tuile en feu : %s (ok=%s err=%s)"
              % (out.get("b_hot_pos"), out.get("b_hot_ok"), out.get("b_hot_error")))
        print("  PA=%s PB=%s caster=%s | cast ok=%s err=%s"
              % (out.get("pa"), out.get("pb"), out.get("caster_pos"),
                 out.get("cast_ok"), out.get("cast_error")))
        print("  placements : %s" % out.get("moves"))
        for k in ("ra", "rb", "rc"):
            r = out.get(k)
            if not r:
                continue
            print("\n  === %s ===  cible=%s" % (r["tag"], r["target"]))
            print("    positions : %s" % r["positions"])
            print("    feu       : %s" % r["fire"])
            print("    etages    : %s" % r["stages"])
            print("    natif       (%d ev) : %s" % (len(r["native"]), r["native"]))
            print("    port AVANT  (%d ev) : %s" % (len(r["port_before"]), r["port_before"]))
            print("    port APRES  (%d ev) : %s" % (len(r["port_after"]), r["port_after"]))
        print("\n  port APRES == natif sur les %d regimes : %s"
              % (len(regs), out["after_matches_native"]))
        print("  port AVANT differait                  : %s" % out["before_differed"])
        print("  RC separe les VALEURS par cible       : %s" % out.get("values_discriminate"))
        print("  erreur : %s" % out.get("error"))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


def step7_generalize_1148(seed: int = 35110, verbose: bool = True) -> dict:
    """#359-r1, GENERALISATION -- le MEME montage sur un board dont le predicat de plateau BASCULE.

    `MC1_67` (etape 6) declare `MachineOfWarPosition(team 1) = 2`, donc
    `IsPositionMachineForCurrentPlayer(2)` VRAI, donc `dir = 1` = triangle `{S, SE}`. `C1_15`
    declare `0` : le predicat est FAUX et le natif prend `Direct(4)` = triangle `{NW, N}`. Un port
    qui aurait code `dir` en dur -- ou qui aurait laisse le canal `machine_of_war_position` non
    branche -- passe l'etape 6 et ECHOUE ici : les deux etapes ensemble bornent les DEUX branches
    du `If`. Mesure du depot au moment de l'ecriture : **502** boards resolvent sur `0` et **173**
    sur `2` (re-derivable par un balayage de `data/boards/`, jamais recopie)."""
    return step6_aoe_1148(seed=seed, board=GEN_BOARD_DIR4, verbose=verbose, tag="7")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only-scan", action="store_true")
    ap.add_argument("--step", type=int, default=None, choices=[0, 1, 2, 3, 4, 5, 6, 7])
    ap.add_argument("--seed", type=int, default=35030)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    steps = [a.step] if a.step is not None else ([0] if a.only_scan else [0, 1, 2, 3, 4, 5, 6, 7])
    out = {}
    if 0 in steps:
        out["scan"] = scan()
    if 1 in steps:
        out["step1"] = step1_mow_caster(seed=a.seed)
    if 2 in steps:
        out["step2"] = step2_confront_1147(seed=a.seed + 10)
    if 3 in steps:
        out["step3"] = step3_daemonic_ordnance(seed=a.seed + 20)
    if 4 in steps:
        out["step4"] = step4_aoe_1147(seed=a.seed + 30)
    if 5 in steps:
        out["step5"] = step5_generalize_1147(seed=a.seed + 40)
    if 6 in steps:
        out["step6"] = step6_aoe_1148(seed=a.seed + 50)
    if 7 in steps:
        out["step7"] = step7_generalize_1148(seed=a.seed + 60)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if all(v.get("ok") for v in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
