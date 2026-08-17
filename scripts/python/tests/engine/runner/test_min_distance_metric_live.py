"""MINDIST -- `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` mesure une distance **HEX**, pas un
chemin, et surement pas un Chebyshev sur coordonnees offset. Garde LIVE discriminante sur CETTE
METRIQUE seule.

RE (decompile = verite, gqfc5mff6c) -- la chaine LUE, appelant par appelant :

  * `IdunBattleLogic.Entities.DSLFormulas$$MinDistance(ctx, selA, selB)` construit une instance de la
    classe `DAT_18324e3c0` en lui passant les DEUX selecteurs. L'ANCRE fiable est le singleton de
    classe, PAS le nom du ctor (ghidra le folde/mislabelle en
    `HasUsedActiveAbilityThisTurnTrigger___ctor` -- meme piege que le comparateur du case #48).
  * `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` :
        best = int.MaxValue
        foreach a in selector@+0x10.Select(ctx):
            foreach b in selector@+0x18.Select(ctx):
                best = Math.Min(best, PositionComponent.Distance(
                                          GetComponent<PositionComponent>(b),
                                          GetComponent<PositionComponent>(a)))
        return best
  * `IdunBattle.Entities.Components.PositionComponent$$Distance` =
    `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` sur chacun des deux (le champ axial vit
    a `PositionComponent+0x10`), puis `IdunBattle.Utils.Hex.CubeCoordinate$$Distance`.
  * `AxialCoordinate$$ToCubeCoordinate` : `off = (flag == 0) ? col + (col & 1) : col & ~1` (le flag
    vit a `axial+0x8` et vaut 0 des `PositionComponent$$.ctor`) ; `x = col ; z = row - off/2 ;
    y = -(x+z)`. `CubeCoordinate$$Distance` = `Max(Max(|dx|,|dy|),|dz|)`.

  => geometrie hexagonale PURE en coordonnees cube, convention offset odd-q. AUCUN graphe, aucune
  file, aucun cout de terrain, aucun obstacle. C'est `hexgeo.distance` (les formes
  `(|dx|+|dy|+|dz|)/2` et `Max(|dx|,|dy|,|dz|)` sont EGALES sur tout cube valide, ou x+y+z=0).

  Le natif HOMONYME qui, LUI, fait du pathfinding est
  `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` : il itere les
  tuiles du `ClosestEnemy` et demande une ROUTE au service de pathfinding dont il lit la longueur
  (`route+0x18`). C'est le natif de `engine/utilities/move.py`, et sa glose « distance de CHEMIN »
  avait ete recopiee A TORT sur le noeud DSL.

CE QUE LA GARDE SURVEILLE. Le gate
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
`On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !AmountIsGreater(MinDistance(owner@0x160,
target@0x178), Direct(2))`. Un Chebyshev SOUS-ESTIME toujours la distance hex (`hex >= cheby`, 0
violation sur un balayage exhaustif 24x24) : il OUVRE donc ce gate la ou le natif le FERME. La
degradation est PERMISSIVE -- ni erreur, ni crash -- et porte sur 5,82 % des paires de tuiles
jouables du board MC1_67.

DEUX MONTAGES, de part et d'autre du DESACCORD DE METRIQUE (c'est ce qui refute « les deux
metriques se valent ») :

  * `split` : `orksKillaKan` (GetStuckIn) caste `DakkaDakkaDakka` (1171, 6 coups, portee 3) sur une
    cible a `hex == 3` mais `cheby <= 2`. Le natif FERME -> le live doit etre bit-exact avec
    `no_maybe`, et le modele `always` (canal branche SANS gate de distance) doit tomber ;
  * `agree` (TEMOIN) : MEME porteur, MEME ability, cible ADJACENTE -- les deux metriques valent 1,
    donc les deux modeles ouvrent le gate. `shipped` doit reproduire le live et `no_maybe` tomber.
    C'est LUI qui prouve qu'un `shipped OK` dans la bande `split` signifie « la metrique est juste »
    et non « le canal entier s'est eteint ».

MESURE DE REFERENCE (seed 777, board MC1_67, `probe_min_distance_metric.py --stage live`) --
AVANT le fix, caster (4,6) cible (6,8), hexgeo=3 cheby=2 :
    live     =[300, 305, 332, 314, 311, 347]
    shipped  =[300, 305, 302, 367, 347, 347]   MISMATCH  <- le proxy ouvrait le gate
    no_maybe =[300, 305, 332, 314, 311, 347]   OK        <- le natif l'avait ferme
APRES le fix, `shipped` rejoint `no_maybe` et le live ; le temoin `agree` reste bit-exact
(`[300, 305, 302, 367, 347, 347]` de part et d'autre).

MONTAGE : regime PERCAGE-DOMINANT (`--armor-target 6000`, fixture `_pierce_floor_regime`), crit et
block neutralises ; bande de position et raison d'etre : `_min_distance_metric_regime`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))                       # helpers siblings
from _pierce_floor_regime import pierce_dominant_regime             # noqa: E402,F401 (fixture)
from _min_distance_metric_regime import (VARIANTS, cheby,           # noqa: E402
                                         measure_metric_split,
                                         want_metrics_agree, want_metrics_split)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import hexgeo                                                        # noqa: E402

# Seeds MESUREES discriminantes (`probe_min_distance_metric.py`, 2026-07-28).
SPLIT_SEEDS = ["777", "31337"]
AGREE_SEEDS = ["777"]


def test_min_distance_is_hex_not_chebyshev_offline():
    """ETAPE 0 (offline, aucune session) : la propriete STRUCTURELLE qui rend la degradation
    PERMISSIVE. Elle ne depend d'aucun montage, donc elle doit tenir inconditionnellement -- et
    c'est elle qui dit dans QUEL SENS un proxy Chebyshev se trompe."""
    worst, patterns = 0, set()
    for c1 in range(16):
        for r1 in range(16):
            for c2 in range(16):
                for r2 in range(16):
                    a, b = (c1, r1), (c2, r2)
                    h, k = hexgeo.distance(a, b), cheby(a, b)
                    assert h >= k, (
                        f"cheby SUR-estime en {a}->{b} : hex={h} cheby={k} -- toute la lecture "
                        "« le proxy est PERMISSIF » repose sur `hex >= cheby`.")
                    worst = max(worst, h - k)
                    if k <= 2 < h:
                        patterns.add((c1 & 1, c2 - c1, r2 - r1))
    assert worst >= 4, (
        f"ecart max hex-cheby = {worst} sur 16x16 : l'ecart devrait CROITRE avec la distance "
        "(il n'est borne par aucune constante) -- `hexgeo.to_cube` a-t-il change de convention ?")
    assert len(patterns) == 12, (
        f"{len(patterns)} patrons discriminants du gate <= 2 au lieu de 12 : la PARITE de la "
        f"colonne de depart ne joue plus comme attendu ({sorted(patterns)}).")


@pytest.mark.parametrize("seed", SPLIT_SEEDS)
def test_min_distance_gate_uses_hex_metric_live(live_session, rpc, pierce_dominant_regime, seed):
    """BANDE DISCRIMINANTE : cible a `hex == 3` mais `cheby <= 2`. Le natif FERME le gate
    `!AmountIsGreater(MinDistance, Direct(2))` ; un port qui mesurerait en Chebyshev l'OUVRIRAIT et
    roulerait un `Maybe` par coup d'index impair, decalant le flux RNG. Le modele `always` (canal
    branche sans le gate de distance) doit tomber -- sinon la garde serait AVEUGLE au gate."""
    live, srcs, off, params = measure_metric_split(rpc, pierce_dominant_regime, seed,
                                                   want_metrics_split)
    print(f"\n[MINDIST split] seed={seed} live={live} sources={srcs} params={params}")
    for name, _m in VARIANTS:
        print(f"[MINDIST split] {name:<9}={off[name]}")
    assert len(live) >= 6, f"attaque a {len(live)} coups : montage non conforme (6 attendus)"
    assert not [s for s in srcs if s and s.startswith("trig:")], (
        f"[split seed {seed}] le live porte un coup bonus GetStuckIn alors que MinDistance vaut 3 "
        f"(sources={srcs}) -- le gate de distance natif ne serait donc pas celui qui est porte.")
    assert off["shipped"] == live, (
        f"[split seed {seed}] le port LIVRE ne reproduit pas le live dans la bande ou les deux "
        f"metriques DESACCORDENT : shipped={off['shipped']} live={live} "
        f"(gate ferme={off['no_maybe']}) -- `getstuckin_combat_chance` / "
        "`GetStuckInTrait.as_attacker_bonus_hits` mesurent-ils encore en distance HEX "
        "(`entities.traits.combat.min_distance`), ou un proxy Chebyshev est-il revenu ?")
    assert off["always"] != live, (
        f"[split seed {seed}] le modele `always` (canal FORCE, sans gate de distance) reproduit "
        f"AUSSI le live ({off['always']}) -- montage NON discriminant.")


@pytest.mark.parametrize("seed", AGREE_SEEDS)
def test_min_distance_gate_bit_exact_where_metrics_agree_live(live_session, rpc,
                                                              pierce_dominant_regime, seed):
    """TEMOIN : cible ADJACENTE -- les deux metriques valent 1, donc AUCUNE hypothese de metrique
    ne les separe. Ce montage doit rester BIT-EXACT quel que soit le changement de metrique. Un lot
    ou les deux hypotheses coincident ne conclut rien : c'est ce temoin qui donne son sens au
    `shipped OK` de la bande discriminante, en montrant que le canal n'est pas simplement ETEINT."""
    live, srcs, off, params = measure_metric_split(rpc, pierce_dominant_regime, seed,
                                                   want_metrics_agree)
    print(f"\n[MINDIST agree] seed={seed} live={live} sources={srcs} params={params}")
    for name, _m in VARIANTS:
        print(f"[MINDIST agree] {name:<9}={off[name]}")
    assert off["shipped"] == live, (
        f"[agree seed {seed}] le port LIVRE ne reproduit plus le live sur une cible ADJACENTE : "
        f"shipped={off['shipped']} live={live} -- le canal `Maybe` a-t-il ete ETEINT au lieu "
        "d'etre re-mesure ?")
    assert off["no_maybe"] != live, (
        f"[agree seed {seed}] le modele `no_maybe` (canal eteint) reproduit AUSSI le live "
        f"({off['no_maybe']}) -- ce temoin serait AVEUGLE a une extinction du canal.")
