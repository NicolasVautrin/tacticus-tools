"""#407 -- la failed-block list a la portee de l'ATTAQUE : garde LIVE discriminante.

RE (decompile = verite, rnca9r7q6c), chaine LUE de bout en bout :
  * `IdunBattle.Core.OngoingAttack$$.ctor` cree `+0x48 = new List<int>()` (`FailedBlockIds`),
    NEUVE par attaque -- exactement comme `+0x40 = 1` (`isCriticalDamageAllowed`) ;
  * `IdunBattle.Operations.ADamageOperation$$GetFailedBlockIds` la rend
    (`HasCurrentAttack() ? GetCurrentAttack().FailedBlockIds : new List<int>()`) ;
  * `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` la seme PAR REFERENCE dans
    `OngoingHitGroup+0x60` ; `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` la passe a
    chaque coup (`options[+0x30] = hitGroup[+0x60]`) ; `ADamageOperation$$RegisterBlocks` y AddRange
    les ids echoues (`hitGroup[+0x60].AddRange(result[+0x28])`) ;
  * `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` EXCLUT toute source dont
    l'id y figure (`Contains(failedBlockIds, id)` -> `continue`) => **0 tirage** pour elle.
`AttackDamageOperation$$Execute` ne construit qu'UN `OngoingHitGroup` (phase d'arme + coups bonus +
`ExecuteAdditionalHitsWithoutDamageProfileType`) et la voie A PROFIL re-lit la MEME liste de
l'`OngoingAttack` => l'exclusion traverse TOUTE l'attaque.

⚠ POLARITE -- ce n'est PAS le gate crit (#440). Le crit a un booleen d'attaque qui TOMBE au premier
coup non-crite (`attack[+0x40] &= hitGroup[+0x3c]`) ; cote block il n'existe AUCUN booleen
equivalent, et l'extinction est PAR SOURCE et seulement sur ECHEC.

L'OBSERVABLE EST LA CONSOMMATION : un roll SAUTE ne consomme pas de tirage. Le port d'AVANT #407
repartait d'un set VIDE a chaque `_run_hits` (donc a chaque groupe) -> 1 `next_bool` de trop, et
tout le flux du groupe decale.

MONTAGE : `orksRuntherd` (passif `SquigHound` -> effet 0x50c, 2 coups PREDEFINED profil `Physical`
pierce 1) attaque au CONTACT `ultraApothecary`, en regime PERCAGE-DOMINANT (`--armor-target 6000`,
fixture `_pierce_floor_regime`), cible porteuse d'une source de block de BASE
`--block-target 10,5` : chance BASSE => le coup d'arme la fait ECHOUER, donc elle DOIT etre exclue
des coups du groupe. `--crit 0,0` (pose par la fixture) => aucun crit-roll : la seule variable du
flux est le block.

MESURE (`probe_407_failed_block_attack_scope.py --seeds 12345,314159,88,777,31337,2026`, 2026-08-01)
6 seeds, TOUS discriminants : port livre **6/6**, contrefactuel sans threading **0/6**. L'ecart
tombe sur le 2e coup du groupe (le tirage de block en trop est consomme APRES le `GetDamage`/
resolve du 1er) -- d'ou la comparaison sur la FENETRE du groupe, jamais sur le seul 1er coup.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, live_amounts,               # noqa: E402
                                  replay_orders, _ok,
                                  pierce_dominant_regime)            # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_407_failed_block_attack_scope import no_thread_variant    # noqa: E402

CARRIER = "orksRuntherd"           # passif SquigHound -> 2 coups Physical (pierce 1)
TARGET = "ultraApothecary"         # ni BigTarget ni Vehicle -> BeastSlayer inerte ; pas de
#                                    SwornProtector (qui devierait l'attaque sur un garde du corps)
BLOCK = "10,5"                     # chance BASSE : le coup d'arme fait ECHOUER la source
SEEDS = ["12345", "88", "2026"]    # tous discriminants (mesure probe_407, 6/6)


@pytest.mark.parametrize("seed", SEEDS)
def test_failed_block_survives_the_weapon_phase_live(live_session, rpc,
                                                     pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, CARRIER, TARGET, armor=6000,
                               extra=["--block-target", BLOCK])   # surcharge le 0,0 de la fixture
    rid, board = r["rid"], r["board"]
    cid, tid, moved = drive(rpc, rid, board, CARRIER, TARGET)
    if cid is None:
        pytest.skip(f"{CARRIER} n'a pas atteint {TARGET} au contact")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        pytest.skip("pas d'attaque normale")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:120]}")
    # `dirty` N'EST PAS un motif d'exclusion ici : le block EST la variable du montage (et le crit
    # est deja neutralise par `--crit 0,0` de la fixture). Skipper dessus rendrait la garde vide.
    live, _dirty = live_amounts(res, tid)

    off = replay_orders(dv, ob, snap, board, rng0, cid, tid, None, moved,
                        {"no_thread": no_thread_variant()})
    nt, ship, arme = off["no_thread"], off["shipped"], off["arme"]
    n = len(arme)
    print(f"\n[#407] seed={seed} live={live} arme_offline={arme}")
    print(f"[#407] groupe livre={ship} sans_threading={nt}")
    assert ship, "aucun coup additionnel rejoue offline (le porteur a-t-il l'effet SquigHound ?)"
    # Les coups d'ARME precedent le groupe dans le flux d'events, et le grot spawne par SquigHound
    # le SUIT -> on ancre sur les coups d'arme (bit-exacts) puis on lit la fenetre du GROUPE.
    assert live[:n] == arme, (
        f"les coups d'ARME divergent (live={live[:n]} off={arme}) : le flux RNG n'est PAS aligne a "
        "l'entree du groupe -- la mesure ne porterait pas sur la portee de la failed-block list.")
    assert n < len(live), f"aucun event live apres les {n} coups d'arme : groupe non emis"
    g_live = live[n:n + len(ship)]
    # (1) RATCHET D'ABORD : le natif GARDE la source exclue, donc le port LIVRE reproduit le live.
    #     Cet ordre est VOULU -- contre-epreuve mesuree (mutation `failed_block = set()` dans
    #     `_run_hits`) : le port devient identique au contrefactuel, et c'est CETTE assertion qui
    #     doit nommer la regression, pas celle du regime discriminant.
    assert ship[:len(g_live)] == g_live, (
        f"le port LIVRE ne reproduit pas le groupe : shipped={ship[:len(g_live)]} live={g_live} "
        "-- `_run_hits`/`execute_additional_hits` threadent-ils encore `failed_block0` "
        "(`OngoingAttack+0x48`) ?")
    # (2) le regime DOIT discriminer les deux modeles, sinon la garde ne prouve rien.
    assert nt[:len(g_live)] != ship[:len(g_live)], (
        f"seed {seed} : groupe NON discriminant (les deux modeles donnent {ship}) -- la source de "
        "block a-t-elle bien ECHOUE pendant la phase d'arme ? rejouer `probe_407_failed_block_"
        "attack_scope.py` pour re-selectionner les seeds.")
    # (3) DISCRIMINATION : le modele SANS threading (le port d'avant #407) doit ECHOUER.
    assert nt[:len(g_live)] != g_live, (
        f"le modele SANS threading reproduit aussi le live ({nt[:len(g_live)]}) : la garde est "
        "AVEUGLE -- le tirage de block en trop ne decale plus le flux.")
