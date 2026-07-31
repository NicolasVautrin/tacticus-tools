"""#350-r3a-r3 -- le gate d'ELIGIBILITE per-position ne doit PAS dependre de `maxRank`.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident
------------------------------------------------------------------------------
A. **Le natif evalue l'eligibilite PAR POSITION**, et le port AUSSI. Ce n'est pas une opinion :
   `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` appelle
   `IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit, UnitPosition(P), ability)` une fois
   PAR position candidate, et `_PlanTargetPlaybook.generate_candidates` gate sur un ensemble de
   tuiles PAR PAIRE (ability, cible). L'ecart mesure entre les deux (`e1_predicat`) est **0 a tous
   les rangs** : `castFromTiles` (= `AttackQuery$$GetInvalidTargetReason` tuile par tuile) rend
   exactement l'eligibilite native, position par position. L'enonce « le port gate sur une UNION de
   positions » est donc REFUTE, et cette garde l'empeche de revenir.

B. **Le SEUL ecart est la TRONCATURE, et il DEPLACE la decision.** `computeAttackPlans`
   (`frida/hooks/features/ai-step/projection.ts`) ne garde que les `maxRank` MEILLEURES tuiles par
   paire (`for (let r = 0; r < maxRank; r++)`). Le natif, lui, n'a pas de `maxRank`. Mesure du
   montage `carte` (un seul etat, plusieurs rangs) :

       maxRank=32  positions divergentes  0/33   -> argmax identique
       maxRank=8   positions divergentes 19/33   -> argmax identique (par CHANCE)
       maxRank=6   positions divergentes 21/33   -> ARGMAX DIFFERENT : natif (1,3), port (0,3)

   `6` n'est pas une valeur de laboratoire : c'est le **defaut du RPC `decisionView`**
   (`rpc-decision.ts`), et `8` est celui de `rl_duel._decision`. Le regime fautif est donc celui de
   production. La garde exige l'egalite des argmax AUX TROIS rangs -- c'est la ligne `maxRank=6` qui
   etait ROUGE avant le fix.

C. **L'argmax natif est MESURE, jamais reconstruit.** `ncPlaybookPredict` rend `bucketUtil` /
   `bucketAction` : l'utilite que le natif attribue LUI-MEME a la position sondee. La garde compare
   donc la decision du port au CHOIX du natif, pas a un modele du natif ecrit dans le probe. Et elle
   compare a `generate_candidates` -- le code LIVRE -- pas a une copie du gate.

D. **Une egalite d'ARGMAX a un seul rang ne conclut RIEN.** C'est exactement ce qui a fait classer ce
   residu « non tranche » deux fois : le montage de #356 et le `0/33` du WIP mesuraient un ecart de
   COMPTE d'eligibilite, jamais un ecart de DECISION. D'ou l'exigence multi-rangs.

Lecture du decompile : en-tete de `probe_350r3a_r3_position_gate.py` ;
`docs/rl/case-350r3-oracle-noncomparable.md` sec.9.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_350r3a_r3_position_gate as P                    # noqa: E402

# Les trois rangs qui comptent : 32 = ce que `engine_validate` demande ; 8 = `rl_duel._decision` ;
# 6 = le DEFAUT du RPC `decisionView`, donc ce qu'obtient tout appelant qui ne precise rien.
RANKS = (32, 8, 6)


@pytest.fixture(scope="module")
def measured():
    """UN montage, les trois rangs. Le natif ne depend pas de `maxRank` : sa carte est mesuree une
    seule fois, et seul le port est re-evalue par rang -- la geometrie est donc EXACTEMENT la meme
    d'un rang a l'autre, et un ecart ne peut venir que du rang."""
    return P.run("carte", None, RANKS, verbose=False)["step1"]


def test_montage_atteint(measured):
    """Sans regime, tout le reste serait un zero muet : 1202 n'a de cible eligible que si elle est
    adjacente ou chargeable (`VigilanceEternalAbility$$GetDynamicInvalidTargetReason`)."""
    assert measured.get("ok"), "montage KO : %s" % measured.get("error")
    assert measured["argmaxNative"]["pos"] is not None, (
        "le natif n'a retenu AUCUNE position : regime non atteint, la mesure ne conclut rien")
    assert measured["fromHere"], (
        "`abilityTargets.fromHere` vide a l'origine : `GetValidTargets` ne rend aucune cible")


def test_predicat_identique_par_position(measured):
    """(A) `castFromTiles` == l'eligibilite native, position par position, a TOUS les rangs.

    C'est l'etage qui repond a la question binaire du residu. S'il rougissait, l'ecart serait dans le
    PREDICAT (`GetValidTargets` vs `GetInvalidTargetReason`) et non dans la troncature."""
    bad = [(x["maxRank"], x["e1_predicat"]) for x in measured["byRank"] if x["e1_predicat"]]
    assert not bad, (
        "le PREDICAT diverge (castFromTiles != eligibilite native) sur %s ; "
        "l'ecart n'est alors PAS la troncature et le fix de #350-r3a-r3 vise a cote" % (bad,))


@pytest.mark.parametrize("rank", RANKS)
def test_argmax_port_egale_argmax_natif(measured, rank):
    """(B) La DECISION du port egale celle du natif a chaque rang -- y compris `6`, le defaut du RPC.

    Rouge avant le fix sur `maxRank=6` : le port perdait la position (1,3) (sortie du top-6 de
    `ranked(79)`) et retombait sur (0,3), ex-aequo en utilite mais que le keep-first natif
    (`Bucket$$AddAction`, remplacement STRICT) n'aurait jamais choisie."""
    row = next(x for x in measured["byRank"] if x["maxRank"] == rank)
    nat = measured["argmaxNative"]
    port = row["argmaxPort"]
    assert port["pos"] == nat["pos"], (
        "maxRank=%d : le port caste depuis %s la ou le natif caste depuis %s "
        "(positions divergentes %d/%d, E1=%d E2=%d) -- la troncature de computeAttackPlans a "
        "retire la position gagnante de `ranked(tgt)`"
        % (rank, port["pos"], nat["pos"], row["divergentPositions"], measured["positions"],
           row["e1_predicat"], row["e2_troncature"]))
    assert port["targets"] and port["targets"][0] in (nat["targets"] or []), (
        "maxRank=%d : le port vise %s, le natif %s" % (rank, port["targets"], nat["targets"]))


def test_troncature_ne_mutile_plus_l_eligibilite(measured):
    """(B bis) Le gate EFFECTIF du port ne doit plus DEPENDRE du rang.

    `rows[].port` est la carte que `_PlanTargetPlaybook.eligible_positions` produit reellement (pas
    `ranked`, qui reste tronque : le fix ne DETRONQUE pas `attackPlans`, il cesse de s'en servir
    comme gate). Avant le fix ces cartes differaient de 19 puis 21 positions sur 33 selon le rang --
    le port voyait un jeu different a chaque appelant, sans erreur ni trace."""
    sets = {x["maxRank"]: [(tuple(r["pos"]), tuple(r["port"])) for r in x["rows"]]
            for x in measured["byRank"]}
    ref_rank = max(sets)
    ref = sets[ref_rank]
    bad = {mr: sum(1 for a, b in zip(v, ref) if a != b) for mr, v in sets.items() if v != ref}
    assert not bad, (
        "la carte d'eligibilite du port DEPEND de maxRank (positions differentes de maxRank=%d : "
        "%s) -- le gate n'est pas un mirror de GetValidTargets mais une vue tronquee du plan"
        % (ref_rank, bad))


@pytest.mark.parametrize("rank", RANKS)
def test_gate_effectif_egale_eligibilite_native(measured, rank):
    """(A bis) LE VERROU CENTRAL : position par position, l'ensemble de cibles que le gate LIVRE
    retient egale celui que le natif retient (`ncPlaybookPredict`, un event par cible eligible).

    C'est plus fort que l'egalite des argmax : deux gates differents peuvent rendre le meme argmax
    par coincidence de geometrie -- c'est arrive DEUX FOIS sur ce residu. Ici on exige l'egalite des
    ENSEMBLES aux 33 positions."""
    row = next(x for x in measured["byRank"] if x["maxRank"] == rank)
    bad = [(tuple(r["pos"]), r["natif"], r["port"]) for r in row["rows"]
           if set(r["natif"]) != set(r["port"])]
    assert not bad, (
        "maxRank=%d : le gate du port differe de l'eligibilite native sur %d/%d positions "
        "(pos, natif, port) = %s" % (rank, len(bad), measured["positions"], bad[:6]))
