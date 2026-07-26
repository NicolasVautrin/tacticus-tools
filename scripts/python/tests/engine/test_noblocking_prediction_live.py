"""#69 NoBlocking (profil de degat) cote PREDICTION — le BLOCK DEDUIT (scenario `list[0]@0x50`,
porte `block_raw_min` = base de WillBeKill/killSure) est BYPASSE pour un profil `NoBlocking` (ex.
`Psychic`), mirror de la face COMBAT #65 (`test_noblocking_bypass_live`).

Racine (RE decompile gqfc5mff6c) : `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` fait
`DamageProfile.HasTrait(profile, 0=NoBlocking)` (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2bec) puis SKIP toute la boucle de construction
du scenario block (`param_1[10]` ; `if (blockList != 0 && (char)HasTrait == 0) {...}`). La face
PREDICTION avait le MEME gap que #65 combat : `defender_prediction_block_amount` / `_with_block`
(`services/damage_prediction.py`, `playbook/prediction/_shared.py`) ne gataient PAS NoBlocking -> une
prediction WillBeKill d'attaque Psychic SUR-COMPTAIT le block (kill-prediction IA faussee). Le fix
threade le `damage_profile` jusqu'a `defender_prediction_block_amount` (mirror 1:1 du gate combat
`AttackDamageOperation._block_sources`).

Test LIVE DETERMINISTE (independant version/seed) : astraPrimarisPsy (arme Psychic = NoBlocking, melee
ET range) vs orksNob (trait BeastSlayer -> effet BeastSlayer_ExtraBlock = source de block). On verifie
(1) la source de block EXISTE sans gate profil ET DISPARAIT sous profil Psychic, PERSISTE sous profil
blockable (Bolter) ; (2) la prediction d'attaque normale Psychic reelle -> block_raw_min None (bypass) ;
(3) DISCRIMINATION : la MEME prediction avec le block amount NON-gate deduit bien le block (block_raw_min
!= None) -> le gate est la seule difference. ASCII only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]              # scripts/python
ROOT = Path(__file__).resolve().parents[4]               # racine repo (via junction data/)
# state-file DEDIE #69 (nom UNIQUE absolu — coexistence multi-agents/multi-runner, discipline runner.md).
STATE = ROOT / "logs" / "runners" / "_pytest69_noblock_pred_state.json"

ATTACKER = "astraPrimarisPsy"    # arme normale Psychic (Traits=['NoBlocking']) melee ET range
TARGET = "orksNob"               # BeastSlayer -> effet BeastSlayer_ExtraBlock (source de block)
BLOCKABLE_PROFILE = "Bolter"     # profil de controle SANS NoBlocking (block toujours deduit)


@pytest.fixture(scope="session")
def nb_pred_case(live_session, rpc):
    """Build isole (state-file unique), scene de PREDICTION au START (la source BeastSlayer_ExtraBlock
    est un passif present d'emblee -> pas besoin de driver au contact), gate + E2E + discrimination."""
    import hexgeo
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction
    from engine.playbook.prediction._shared import defender_prediction_block_amount, _weapon_pierce
    from engine.services.damage_prediction import get_attack_prediction
    from engine.services.battle_query import are_tiles_adjacent
    from engine.entities.pathfinding.board import Board

    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(STATE),
         "--board", "MC1_67", "--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build runner KO (rl_duel): {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and "tiles" in bg):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = (dec or {}).get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unite manquante (build 1v1 KO)")
        att_id, tgt_id = champ["id"], tgt["id"]
        predictor = SC.build_predictor(rpc, rid)
        if predictor is None:
            pytest.skip("build_predictor KO")
        sctx = SC.step_context(predictor, dec)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        scene.board = board
        t_pos = scene.pos(tgt_id)

        # (1) GATE : amount de block DU DEFENSEUR, sans gate / sous Psychic / sous profil blockable.
        amt_nogate = defender_prediction_block_amount(scene, tgt_id)
        amt_psychic = defender_prediction_block_amount(scene, tgt_id, "Psychic")
        amt_blockable = defender_prediction_block_amount(scene, tgt_id, BLOCKABLE_PROFILE)
        effs = [getattr(e, "name", None) for e in (scene.effects(tgt_id) or [])]
        has_bs_effect = "BeastSlayer_ExtraBlock" in effs

        # (2) E2E : tuile RANGED (hex-dist 2, non-adjacente) -> arme Psychic garantie -> prediction reelle.
        ranged_pos = None
        for t in bg["tiles"]:
            c, r = t["col"], t["row"]
            if not board.walkable(board.id_at(c, r)):
                continue
            if hexgeo.distance((c, r), t_pos) == 2 and are_tiles_adjacent((c, r), t_pos, board) is not True:
                ranged_pos = (c, r)
                break
        e2e_prof = e2e_block_raw_min = None
        if ranged_pos is not None:
            _, _rng, _, e2e_prof = _weapon_pierce(scene, att_id, False, 2)   # profil REELLEMENT resolu
            _res = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, ranged_pos, meta=True)
            if _res is not None:
                e2e_block_raw_min = _res[0].prediction.block_raw_min

        # (3) DISCRIMINATION : MEME prediction (get_attack_prediction), block amount gate(0) vs nogate.
        hp = scene.hp(tgt_id) or 0
        armor = scene.armor(tgt_id)
        shield = scene.shield(tgt_id)
        d_gated = get_attack_prediction(
            target_current_health=hp, initial_damage=3000, hits=3, profile_type=0, pierce_pct=100,
            armor=armor, target_shield=shield, defender_block_amount=amt_psychic).block_raw_min
        d_ungated = get_attack_prediction(
            target_current_health=hp, initial_damage=3000, hits=3, profile_type=0, pierce_pct=100,
            armor=armor, target_shield=shield, defender_block_amount=amt_nogate).block_raw_min
        return {
            "amt_nogate": amt_nogate, "amt_psychic": amt_psychic, "amt_blockable": amt_blockable,
            "has_bs_effect": has_bs_effect, "effects": effs,
            "e2e_prof": e2e_prof, "e2e_block_raw_min": e2e_block_raw_min, "ranged_pos": ranged_pos,
            "discrim_gated": d_gated, "discrim_ungated": d_ungated,
        }
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def test_pred_source_gated(nb_pred_case):
    """DETERMINISTE : la source de block d'orksNob EXISTE sans gate profil (amt>0), DISPARAIT sous profil
    Psychic (NoBlocking -> 0), PERSISTE sous profil blockable. Sans cette dualite, rien n'est discrimine."""
    c = nb_pred_case
    if not c["has_bs_effect"]:
        pytest.skip(f"BeastSlayer_ExtraBlock non seede sur orksNob (effets={c['effects']})")
    assert c["amt_nogate"] > 0, (
        f"pre-condition : block amount attendu sans gate profil, obtenu {c['amt_nogate']}")
    assert c["amt_psychic"] == 0, (
        f"profil Psychic (NoBlocking) doit BYPASSER le block -> amount 0, obtenu {c['amt_psychic']}")
    assert c["amt_blockable"] == c["amt_nogate"], (
        f"profil blockable ({BLOCKABLE_PROFILE}) doit CONSERVER le block : "
        f"{c['amt_blockable']} != {c['amt_nogate']}")


def test_pred_e2e_bypass_and_discrimination(nb_pred_case):
    """COEUR #69 : (a) la prediction d'attaque normale Psychic REELLE bypasse le block (block_raw_min None) ;
    (b) DISCRIMINATION : la MEME prediction avec le block amount NON-gate deduit bien le block (!= None) ->
    le gate NoBlocking est la SEULE difference (pas un no-op fortuit)."""
    c = nb_pred_case
    if not c["has_bs_effect"]:
        pytest.skip(f"BeastSlayer_ExtraBlock non seede sur orksNob (effets={c['effects']})")
    # (b) discrimination d'abord : sans le gate, le block SERAIT deduit (sinon le test (a) ne prouve rien).
    assert c["discrim_ungated"] is not None, (
        f"pre-condition : block amount non-gate ({c['amt_nogate']}) doit DEDUIRE le block "
        f"(block_raw_min != None), obtenu {c['discrim_ungated']}")
    assert c["discrim_gated"] is None, (
        f"block amount gate (0, Psychic) ne doit PAS deduire de block -> block_raw_min None, "
        f"obtenu {c['discrim_gated']}")
    # (a) end-to-end via le VRAI point d'entree make_normal_attack_predictions.
    if c["ranged_pos"] is None:
        pytest.skip("aucune tuile ranged (hex-dist 2) trouvee autour de la cible")
    assert c["e2e_prof"] == "Psychic", (
        f"le profil d'arme resolu doit etre Psychic (NoBlocking), obtenu {c['e2e_prof']!r}")
    assert c["e2e_block_raw_min"] is None, (
        f"attaque normale Psychic reelle : block bypasse -> block_raw_min None, obtenu {c['e2e_block_raw_min']}")
