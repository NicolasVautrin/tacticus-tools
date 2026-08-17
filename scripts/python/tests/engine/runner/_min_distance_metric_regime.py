"""FIXTURE NOMMEE ET REUTILISABLE — le montage « les deux metriques de distance DESACCORDENT »,
seul montage ou la METRIQUE du gate `MinDistance` est observable.

POURQUOI cette fixture existe (et pourquoi elle doit resservir) : tout gate de distance porte
(`GetStuckIn`, les regles d'adjacence, `IsCharging`) se lit dans un montage ordinaire de la MEME
facon, que le port mesure une distance HEX ou un Chebyshev sur coordonnees offset — parce que les
deux metriques COINCIDENT sur la majorite des paires, et notamment sur les deux configurations que
l'on monte spontanement (cible adjacente, cible loin en ligne droite). Un lot ou les deux
hypotheses donnent le meme resultat ne conclut RIEN : c'est exactement pour cela que le gap avait
survecu a plusieurs campagnes, et que la PR #177 a pu le contourner (`_want_far` exige `cheby >= 3`
PRECISEMENT pour neutraliser l'ecart).

Ce module fabrique le complement : la BANDE ETROITE ou les deux modeles se separent.

    `hex >= cheby` TOUJOURS (0 violation sur un balayage exhaustif 24x24, ecart jusqu'a 12) — le
    Chebyshev SOUS-ESTIME, donc sur `!(MinDistance > 2)` il OUVRE ce que le natif FERME. Les paires
    discriminantes du gate `<= 2` valent toutes `hex == 3, cheby == 2`, et leur patron depend de la
    PARITE de la colonne de depart (asymetrie odd-q) : 12 patrons (dcol, drow) au total.
    Sur le board MC1_67 : 46,6 % des paires de tuiles jouables ont une distance differente et
    **5,82 % font diverger le gate `<= 2`** (`probe_min_distance_metric.py --stage offline`).

RE (decompile = verite, gqfc5mff6c) — `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` construit
`IdunBattle.Entities.Formulas.MinDistanceFormula`, dont le `Calculate` prend le `Min` sur les paires
de `IdunBattle.Entities.Components.PositionComponent$$Distance` =
`IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` x2 puis
`IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = `Max(|dx|,|dy|,|dz|)`. **Zero pathfinding.**
Le natif HOMONYME qui, LUI, fait du pathfinding est
`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` (utilite IA de
MOUVEMENT) — c'est la confusion des deux qui avait produit le proxy.

LE LEVIER : le porteur est DEPLACE jusqu'a la bande discriminante (`_drive_ability` du probe R6-b'',
qui balaie `aiMovableTiles` et repositionne ; jamais « bloque par la geometrie de spawn »).
`DakkaDakkaDakka` portant a 3 hex, la configuration `hex == 3` reste CASTABLE — sans quoi la bande
serait inobservable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))                       # helpers siblings
from _ability_after_hit_regime import (DAKKA_ABILITY, DAKKA_CARRIER,  # noqa: E402,F401
                                       DAKKA_TARGET, VARIANTS,
                                       measure_ability_vector)

__all__ = ["DAKKA_ABILITY", "DAKKA_CARRIER", "DAKKA_TARGET", "VARIANTS",
           "want_metrics_split", "want_metrics_agree", "measure_metric_split", "cheby"]


def cheby(a, b) -> int:
    """Le PROXY incrimine, garde ICI en toutes lettres pour que la garde puisse encore le
    CONSTRUIRE apres sa disparition du moteur (une garde qui importerait la fonction fixee ne
    pourrait plus fabriquer la configuration qu'elle doit surveiller)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def want_metrics_split(hexdist, cheb):
    """CONFIGURATION DISCRIMINANTE : `MinDistance` natif == 3 (gate `<= 2` FERME) alors que le proxy
    Chebyshev vaut <= 2 (gate OUVERT). Les deux modeles predisent des flux RNG DIFFERENTS, donc des
    per-coup differents — c'est la seule bande ou la METRIQUE elle-meme est observable."""
    return hexdist == 3 and cheb <= 2


def want_metrics_agree(hexdist, cheb):
    """TEMOIN : cible ADJACENTE — les DEUX metriques valent 1, les deux modeles ouvrent le gate.
    Doit rester BIT-EXACT de part et d'autre de tout changement de metrique. Sans lui, un `shipped
    OK` dans la bande discriminante ne distinguerait pas « la metrique est juste » de « le canal
    entier s'est eteint »."""
    return hexdist == 1 and cheb == 1


def measure_metric_split(rpc, regime, seed, want, target=DAKKA_TARGET, armor=6000):
    """Monte le regime percage-dominant, AMENE `orksKillaKan` dans la bande `want`, caste
    `DakkaDakkaDakka` LIVE et rejoue le MEME cast offline sous les quatre modeles de `VARIANTS`.
    Rend `(live, sources, off, params)` ou `pytest.skip`. Delegue a `measure_ability_vector` :
    le montage est le MEME que R6-b'', seul le predicat de position change."""
    return measure_ability_vector(rpc, regime, seed, want, target=target, armor=armor)
