"""#407-r1 -- le block est ATTEINT apres l'etage esquive : garde LIVE discriminante.

RE (decompile = verite, rnca9r7q6c), corps d'`IdunBattle.Core.Services.DamagePrediction$$
CalculateDamageOperation` -- slots d'`IDamageCalculations` (§2 de
`docs/rl/case-407-failed-block-attack-scope.md`) :

    evasionChance = slot 1   CalculateEvasionChance(attacker, defender) = GetStat(def, 0xf)
    rest          = Math.Max(0, damage - slot 0xc CalculateDamageBlockedByShield(...))
    ev            = slot 3   ApplyRandomEvasion(evasionChance, rest, attacker, defender)
    if !ev.didEvade:  bd = slot 2 ApplyRandomBlockDamage(blockChances, rest)

=> une SEQUENCE, pas une alternative : l'esquive n'ecarte le block que si elle REUSSIT. Le port
portait un XOR (`evasion_branch`) dont le mapping natif etait FAUX -- l'octet cite
(`uStack_5b0>>0x28`) est `damageInfo[+0x1D]`, le block GARANTI, pas un selecteur.

CE QUE CETTE GARDE PEUT ET NE PEUT PAS PROUVER. La face « l'esquive est evaluee AVANT le block »
est **NON CONFRONTABLE** : aucune unite n'arrive en bataille avec `StatType 15` non nul (5 voies,
`probe_407r1_evasion_carriers.py`), et a chance nulle `ApplyRandomEvasion` ne consomme AUCUN
tirage -- les deux ordres sont bit-a-bit identiques. Ce qui EST confrontable, et ce que cette
garde verrouille, c'est que le natif **DESCEND** bien au block : le contrefactuel `xor`
(`block_runs_after_evasion` rendu toujours `False`) supprime tout block, consomme moins de
tirages et decale tout le flux.

La garde MESURE aussi son propre regime au lieu de le supposer : `Attack_DidEvade`
(`IdunBattle.Streams.TagKey` 140) doit rester FAUX -- c'est la constatation live que
`evasionChance == 0`, et c'est ce qui rend legitime le fait de n'avoir pas confronte l'ordre.

MONTAGE (celui de #407, regime deja mesure) : `orksRuntherd` (passif `SquigHound` -> 2 coups
PREDEFINED profil `Physical`) attaque au CONTACT `ultraApothecary`, en regime PERCAGE-DOMINANT
(`--armor-target 6000`), cible porteuse d'une source de block de BASE `--block-target 25,40`
(chance assez haute pour que le block MORDE dans la fenetre). `--crit 0,0` (fixture) : aucun
crit-roll, la seule variable du flux est le block.

MESURE (`probe_407r1_evasion_order_live.py --seeds 12345,314159,88,777,31337,2026`, 2026-08-01)
6 seeds, TOUS discriminants : port livre **6/6**, contrefactuel `xor` **0/6**, et **0 esquive**
observee. La comparaison porte sur la FENETRE (coups d'arme + groupe), jamais sur un point : le
tirage de block manquant est consomme APRES le resolve du coup courant, donc c'est le coup
SUIVANT qui bouge (piege mesure de #407).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, live_amounts, _ok,               # noqa: E402
                                  pierce_dominant_regime)                # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                       # scripts/python
from probe_407r1_evasion_order_live import (replay_evasion_gate,         # noqa: E402
                                            _any_evade)

CARRIER = "orksRuntherd"           # passif SquigHound -> 2 coups Physical additionnels
TARGET = "ultraApothecary"         # ni BigTarget ni Vehicle -> BeastSlayer inerte ; pas de
#                                    SwornProtector (qui devierait l'attaque sur un garde du corps)
BLOCK = "25,40"                    # chance assez HAUTE pour que le block morde dans la fenetre
SEEDS = ["12345", "88", "2026"]    # tous discriminants (mesure probe_407r1, 6/6)


@pytest.mark.parametrize("seed", SEEDS)
def test_le_block_est_atteint_apres_l_etage_esquive_live(live_session, rpc,
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
    # `dirty` N'EST PAS un motif d'exclusion : le block EST la variable du montage (le crit est
    # deja neutralise par `--crit 0,0`). Skipper dessus rendrait la garde vide.
    live, _dirty = live_amounts(res, tid)
    evaded = _any_evade(res, tid)

    off = replay_evasion_gate(dv, ob, snap, board, rng0, cid, tid, moved)
    win_ship = off["arme_shipped"] + off["shipped"]
    win_xor = off["arme_xor"] + off["xor"]
    w = len(win_ship)
    print(f"\n[#407-r1] seed={seed} live={live} evade_live={evaded}")
    print(f"[#407-r1] fenetre livre={win_ship} xor={win_xor}")
    assert win_ship, "aucun coup rejoue offline (le montage a-t-il produit une attaque ?)"
    assert w <= len(live), (
        f"le live n'a que {len(live)} events pour une fenetre offline de {w} coups : "
        "l'attaque n'a pas produit ce qui est attendu du montage.")

    # (0) LE REGIME EST BIEN CELUI QU'ON CROIT : aucune esquive live. C'est la MESURE qui autorise
    #     a ne pas avoir confronte l'ORDRE (a chance nulle, les deux ordres coincident). Si elle
    #     tombe, un porteur de `StatType 15` est apparu -> le regime devient confrontable et
    #     `docs/rl/case-407-r1-evasion-order.md` doit etre rouvert.
    assert not evaded, (
        f"seed {seed} : `Attack_DidEvade` est VRAI en live -- une unite porte donc `StatType 15` "
        "(EvasionChance) alors que le recensement `probe_407r1_evasion_carriers.py` n'en trouvait "
        "AUCUNE. L'ordre esquive->block devient CONFRONTABLE : le chiffrer, ne pas se contenter "
        "de cette garde.")
    # (1) RATCHET D'ABORD : le port LIVRE reproduit le live sur toute la fenetre.
    assert win_ship == live[:w], (
        f"le port LIVRE ne reproduit pas le live : livre={win_ship} live={live[:w]} -- "
        "`calculate_damage_operation` descend-il encore au slot 2 `ApplyRandomBlockDamage` apres "
        "l'etage esquive (`block_runs_after_evasion`) ?")
    # (2) le regime DOIT discriminer les deux modeles, sinon la garde ne prouve rien.
    assert win_ship != win_xor, (
        f"seed {seed} : fenetre NON discriminante (les deux modeles donnent {win_ship}) -- la "
        "cible porte-t-elle encore une source de block ? (`--block-target 25,40`). Rejouer "
        "`probe_407r1_evasion_order_live.py` pour re-selectionner les seeds.")
    # (3) DISCRIMINATION : le contrefactuel `xor` (block plus jamais atteint) doit ECHOUER.
    assert win_xor != live[:w], (
        f"le contrefactuel XOR reproduit aussi le live ({win_xor}) : la garde est AVEUGLE -- le "
        "block ne consomme plus de tirage dans ce montage.")
