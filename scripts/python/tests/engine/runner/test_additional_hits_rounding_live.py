"""R6 -- MATERIALISATION du canal COUPS ADDITIONNELS HETEROGENES (#179/#202-B), garde LIVE
discriminante sur l'ETAGE materialisation SEUL.

RE (decompile = verite) : les DEUX voies natives de coups additionnels retombent sur le MEME
per-coup que l'attaque d'arme --
  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
    (groupes SANS profil) finit sur `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` ;
  * `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` (groupes
    AVEC profil, dont `SquigHound`) appelle le slot 0x3c de l'interface OperationProcessor =
    `Core.Services.OperationProcessor$$AttackDamage` -> `IdunBattle.Operations.
    AttackDamageOperation$$Execute` -> `ExecuteHits`.
`ExecuteHit` materialise par le slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`
-> `PredictAttackRaw` -> `CalculateBaseDamageWithAllModifiers` -> slot 0x10
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` =
`Fix64.Round(Mul(v, multiplier), AwayFromZero)`. => MEME arrondi que l'attaque normale (#131).

⚠ POURQUOI CETTE GARDE REJOUE UNE VARIANTE D'ORDRE, ET PAS LE PORT TEL QUEL. Le port resout ce
canal en REDUCE-THEN-ROLL (bornes pre-reduites, `post_roll=None`, 1 tirage/coup) alors que le
descripteur natif d'un groupe PREDEFINED porte un `HitDamage` NON DEGENERE : `ExecuteHit` commence
par `IdunBattle.Core.HitDamage$$GetDamage` (1 tirage BRUT) puis resout la cellule degeneree au
slot 8 (1 tirage gaspille) = ROLL-THEN-REDUCE, 2 tirages/coup. MESURE (probe_r6, 11 seeds,
`orksRuntherd`/SquigHound) : le PREMIER coup de chaque groupe est reproduit 11/11 par
roll-then-reduce et 0/11 par reduce-then-roll. Cet ecart d'ORDRE est le residu #202-B (« conso RNG
discriminante, A CONFIRMER LIVE ») -- il est AMONT et ORTHOGONAL a la materialisation. Cette garde
le neutralise (`additional_hits_variant`) pour verrouiller l'etage AVAL, qui est le sujet de R6 ;
le jour ou l'ordre est porte, elle continue de tenir et le port lui-meme deviendra bit-exact.

MONTAGE : `orksRuntherd` (passif `SquigHound` -> effet 0x50c, 2 coups PREDEFINED [minDmg,maxDmg]
profil Physical PiercingRatio 1) attaque au CONTACT une cible forcee en regime PERCAGE-DOMINANT
(`--armor-target 6000`, cf. `_pierce_floor_regime`). Cible sans trait `BigTarget`/`Vehicle` : le
`BeastSlayer_ExtraDmg` du porteur reste INERTE, donc la %-list attaquant reste VIDE (condition (a)).
SEEDS : ceux dont le 1er coup du groupe est DISCRIMINANT (floor != round) -- les autres ne
prouvent rien et sont exclus par construction, pas par un skip.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, live_amounts,               # noqa: E402
                                  replay_materializations, _ok,
                                  pierce_dominant_regime)            # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6_round_materialize import additional_hits_variant       # noqa: E402

CARRIER = "orksRuntherd"           # passif SquigHound -> 2 coups Physical (pierce 1)
TARGET = "ultraApothecary"         # ni BigTarget ni Vehicle -> BeastSlayer inerte ; pas de
#                                    SwornProtector (qui devierait l'attaque sur un garde du corps)
MODULE = "engine.runner.operations.additional_hits"
# Seeds dont le 1er coup du groupe est DISCRIMINANT (mesure probe_r6 --case ah_matrix) :
DISCRIMINANT_SEEDS = ["12345", "314159", "88"]


@pytest.mark.parametrize("seed", DISCRIMINANT_SEEDS)
def test_additional_hits_are_rounded_live(live_session, rpc, pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, CARRIER, TARGET, armor=6000)
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
    live, dirty = live_amounts(res, tid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")

    # ORDRE natif neutralise (cf. en-tete) : SEULE la materialisation varie entre les rejeux.
    off = replay_materializations(
        dv, ob, snap, board, rng0, cid, tid, None, moved, MODULE,
        recorder="additional_hits",
        ah_impl_factory=lambda fr: additional_hits_variant("roll_then_reduce", fr))
    off_f, off_r, off_s, arme = off["floor"], off["round"], off["shipped"], off["arme"]
    # Les coups d'ARME precedent le groupe dans le flux d'events, et le SUMMON de `SquigHound`
    # (grot spawne par l'attaque) le SUIT -> on ne peut pas compter depuis la fin. On ancre sur
    # les coups d'arme, qui sont bit-exacts (verifie ci-dessous), et on lit le 1er coup du GROUPE.
    n_arme = len(arme)
    print(f"\n[R6 additional_hits] seed={seed} live={live} arme_offline={arme}")
    print(f"[R6 additional_hits] groupe troncature={off_f} arrondi={off_r} livre={off_s}")
    assert off_r and off_f, "aucun coup additionnel rejoue offline (le porteur a-t-il l'effet ?)"
    assert live[:n_arme] == arme, (
        f"les coups d'ARME divergent (live={live[:n_arme]} off={arme}) : le flux RNG n'est PAS "
        "aligne a l'entree du groupe -- la mesure ne porterait pas sur la materialisation.")
    assert n_arme < len(live), (
        f"aucun event live apres les {n_arme} coups d'arme : le groupe n'a pas ete emis")
    live_g0 = live[n_arme]
    # (1) le regime DOIT etre discriminant sur CE coup, sinon la garde ne prouve rien.
    assert off_f[0] != off_r[0], (
        f"seed {seed} : 1er coup du groupe NON discriminant (floor==round=={off_r[0]}) -- il ne "
        "fait plus partie des seeds utiles ; rejouer `probe_r6_round_materialize.py "
        "--case ah_matrix` pour en re-selectionner.")
    # (2) le natif ARRONDIT.
    assert off_r[0] == live_g0, (
        f"coup ARRONDI != live : off={off_r[0]} live={live_g0} (groupe offline {off_r}, "
        f"live {live[n_arme:]})")
    # (3) DISCRIMINATION : la troncature (le port d'avant R6) doit ECHOUER.
    assert off_f[0] != live_g0, (
        f"la TRONCATURE reproduit aussi le live ({off_f[0]}) : la garde est AVEUGLE.")
    # (4) RATCHET : `reduce_group_damage` (le FOYER livre) doit materialiser comme le natif.
    assert off_s[0] == live_g0, (
        f"le port LIVRE ne materialise pas comme le natif : shipped={off_s[0]} live={live_g0} "
        f"(arrondi={off_r[0]}, troncature={off_f[0]}) -- `reduce_group_damage` "
        "d'`operations/additional_hits.py` TRONQUE-t-il encore ?")
