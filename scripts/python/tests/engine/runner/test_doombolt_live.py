"""Doombolt (actif 1102, thousAhriman « Ahriman », Thousand Sons) PORT -> confronte au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1, cf. `engine/runner/abilities/thousandsons.py`) :

    N = Min( Sum(ConfigConst(0x2f = nrOfHits), Count(EntitiesWithAnyEffect(AllTiles, Fire))), Get(9) )
    liste = SortUnitsByDamageUtility( GetTargets() )   puis  Remove(cible); Insert(0, cible)
    C = liste.Count ; r = N % C
    foreach u : k = (r >= 1) ? N/C + 1 : N/C ;  r = (r >= 1) ? r - 1 : r
                behaviour += AttackWithAttackDamage(owner@0x148, Get(u), MinMaxDamage, Psychic, k, …)

CE QUE CE TEST VALIDE (cas DISCRIMINANTS ; montage = la fixture NOMMEE `psychic_aoe_case`,
`tests/engine/runner/conftest.py`, qui delegue au probe `scripts/python/probe_psychic_aoe.py`) :
  (A) `db-2` — 2 ennemis a portee : repartition **[2, 1]**, la CIBLE DU MESSAGE en tete (c'est elle
      qui prend le coup supplementaire du reste `r = 3 % 2 = 1`). Degat bit-exact vs le live.
  (B) `db-4` — 4 ennemis pour N = 3 : repartition **[1, 1, 1, 0]**. Deux proprietes NON triviales y
      sont confrontees d'un coup :
        * la 4e cible ne recoit **AUCUN** coup (base 0). C'est ce cas qui a revele le plancher
          `max(1, ·)` de la formule de coups du port : le natif termine par `System.Math.Max(·, 0)`
          (`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`) et son clamp par-effet est
          borne par la BASE (`Math.Max(hits, Math.Min(base, cap))`) -> base 0 => 0 coup. Le port
          portait un coup fantome (1603 de degat) ; corrige par le plancher `min(1, base)`.
        * l'ORDRE de `SortUnitsByDamageUtility` : sur ce montage il n'est PAS l'ordre par id
          (mesure : u77, u81, u79 — u81 passe devant u79), et le live donne la MEME sequence de
          tirages -> l'ordre porte est confronte, pas seulement le nombre de coups.
  (C) DISCRIMINANCE : un port DELIBEREMENT FAUX (famille ABILITY, 1 tirage/coup au lieu des 2 de la
      famille ATTACK a cc=0) DIVERGE du live sur le meme etat et le meme `state.rng`.

CE QUE `db-4` MESURAIT VRAIMENT, ET POURQUOI IL EST DESORMAIS SCINDE (#494-r1)
-----------------------------------------------------------------------------
`db-4` monte quatre visualId differents a PV NATURELS -- donc a `fixedArmor` naturels et TOUS
DIFFERENTS (mesure 2026-08-07 : 2761 / 2662 / 1806 / 2161). Or l'ARMURE entre dans la prediction
NATIVE et **pas encore** dans la cle du port (`#527-r1`). Ce montage ne mesurait donc pas l'ORDRE :
il mesurait la partie de la cle qui reste non portee, et il passait par COMPENSATION -- deux
absences (armure ET part positionnelle) qui se corrigeaient l'une l'autre sur cette geometrie-la.

La preuve est une mesure a UNE seule variable (`probe_494r1_db4_decompose.py`, MEME roster, MEME
geometrie, MEME seed) :

    | regime      | armures            | NATIF joue      | PORT (cle positionnelle) |
    | db-4        | 2761 2662 1806 2161| [77, 81, 79]    | [77, 83, 81, 79]  DIVERGE |
    | db-4 --egalise |     0 partout   | [77, 83, 79]    | [77, 83, 79, 81]  ACCORD  |

Egalise, le port et le natif sont d'accord sur la MEME geometrie -- `orksNob` (elevation 2, seul
plus BAS que le caster, elevation 3) remonte en 2e position des DEUX cotes. Ce qui restait est donc
bien l'armure, pas l'ordre.

  * `db-4e` (EGALISE) porte la confrontation d'ORDRE et le bit-exact ;
  * `db-4` (HETEROGENE) etait le TEMOIN de `#527-r1`, en `xfail(strict=True)`. **Le cliquet a joue
    (#494-r1-r1)** : la cle de tri passe desormais par la PREDICTION COMPLETE par cible, l'armure y
    entre, le test est passe en `xpass` et le marqueur a ete retire. Il est VERT et le reste.

Detail : `docs/rl/case-494-doombolt-ordre-des-cibles.md`.

Lit l'etat LIVE (aucune tuile/valeur hardcodee), state-file UNIQUE, dispose au teardown (le probe
s'en charge). ASCII only.
"""
from __future__ import annotations

import pytest

import gameconfig as GC


def _cfg_hits() -> int:
    """ORACLE du nb de coups de BASE = la CONSTANTE de config (`GetNumberConstant(0x2f)`), jamais un
    litteral. Aucun hex en feu sur un runner frais -> `Count(EntitiesWithAnyEffect(AllTiles, Fire))`
    vaut 0, donc `N == nrOfHits` (cape a 9, non atteint)."""
    c = (GC.ability("Doombolt") or {}).get("constants") or {}
    assert c.get("nrOfHits") is not None, "oracle introuvable : constants.nrOfHits absent (Doombolt)"
    return int(c["nrOfHits"])


def test_doombolt_two_targets_live(psychic_aoe_case):
    """(A) 2 ennemis a portee -> [2, 1], la cible du message d'abord ; degat bit-exact."""
    r = psychic_aoe_case("db-2")
    diag = r["diag"]
    assert diag["total_hits"] == _cfg_hits(), (
        f"N={diag['total_hits']} != oracle constants.nrOfHits={_cfg_hits()} "
        f"(aucun hex en feu attendu sur un runner frais)")
    assert len(diag["targets"]) == 2, f"2 cibles attendues : {diag['targets']}"
    assert diag["targets"][0] == r["target"], (
        f"la CIBLE DU MESSAGE doit etre en tete (Remove+Insert(0)) : {diag['targets']}")
    assert diag["hits"] == [2, 1], f"repartition attendue [2,1], obtenu {diag['hits']}"
    # `exact` = comparaison PAR CIBLE des sequences de coups (une cible a 0 coup vaut liste vide des
    # deux cotes ; le port emet quand meme le behaviour, comme le natif -> cle presente, valeur []).
    assert r["exact"], f"degat non bit-exact : live={r['live']} off={r['off']}"
    assert len(r["live"][diag["targets"][0]]) == 2 and len(r["live"][diag["targets"][1]]) == 1, \
        f"repartition LIVE != [2,1] : {r['live']}"
    assert r["discriminant"], (
        f"cas NON discriminant (le port-FAUX famille ABILITY rend le meme resultat) : "
        f"control={r['control']} live={r['live']}")


def _assert_db4(r):
    """Le corps commun aux deux regimes de `db-4` : repartition, plancher de coups, bit-exact,
    ordre. Ecrit UNE fois pour que le regime EGALISE et le TEMOIN heterogene soient juges par le
    MEME critere -- un temoin juge plus mollement ne temoignerait de rien."""
    diag = r["diag"]
    assert len(diag["targets"]) == 4, f"4 cibles attendues a portee : {diag['targets']}"
    assert diag["hits"] == [1, 1, 1, 0], f"repartition attendue [1,1,1,0], obtenu {diag['hits']}"
    last = diag["targets"][-1]
    assert r["live"].get(last, []) == [], (
        f"la 4e cible (base 0 coup) NE DOIT recevoir AUCUN coup live, obtenu {r['live'].get(last)}")
    assert r["off"].get(last, []) == [], (
        f"port : coup FANTOME sur la cible a 0 coup ({r['off'].get(last)}) -- le plancher de coups "
        f"doit etre borne par la BASE (`Math.Max(·, 0)` natif), cf. l'en-tete du module")
    # `exact` = comparaison PAR CIBLE des sequences de coups (une cible a 0 coup vaut liste vide des
    # deux cotes ; le port emet quand meme le behaviour, comme le natif -> cle presente, valeur []).
    assert r["exact"], f"degat non bit-exact : live={r['live']} off={r['off']}"
    # ORDRE : les 3 premieres cibles prennent 1 coup chacune ; comme le RNG avance dans l'ordre
    # d'iteration, l'egalite bit-exacte ci-dessus VALIDE aussi la permutation rendue par le tri.
    assert diag["targets"][0] == r["target"], (
        f"la CIBLE DU MESSAGE doit rester en tete : {diag['targets']}")
    assert r["discriminant"], (
        f"cas NON discriminant : control={r['control']} live={r['live']}")


def test_doombolt_zero_hit_target_and_sort_order_live(psychic_aoe_case):
    """(B)+(C) 4 ennemis pour N=3 -> [1,1,1,0], PV et armures EGALISES : la DERNIERE cible ne recoit
    AUCUN coup (plancher de coups borne par la base) et l'ORDRE du tri par utilite est confronte au
    live sur une geometrie ou seule l'ELEVATION discrimine (#494-r1)."""
    _assert_db4(psychic_aoe_case("db-4e"))


def test_doombolt_ordre_heterogene_bloque_par_l_armure_live(psychic_aoe_case):
    """TEMOIN de `#527-r1`, desormais VERT : le MEME critere que `db-4e`, sur le montage a armures
    HETEROGENES.

    ⚠ Ce test a porte un `xfail(strict=True)` du 2026-08-07 au 2026-08-07 (#494-r1-r1). Le marqueur
    etait un CLIQUET : « quand l'armure entrera dans la cle, ce test passera au vert et rougira en
    xpass ». Il a fait exactement cela. La cause a ete fermee en faisant passer la cle de tri par la
    PREDICTION COMPLETE par cible (`IBattleQuery` slot `0x26`, `damageProfile: null` donc percage 0
    et armure SOUSTRAITE EN ENTIER) -- mesure : `[77, 81, 79]` des deux cotes, bit-exact.
    Le NOM du test est conserve tel quel : c'est lui que la case-doc et le backlog citent."""
    _assert_db4(psychic_aoe_case("db-4"))
