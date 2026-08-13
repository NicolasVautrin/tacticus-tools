# #914-r2 — la prémisse du résidu était **PÉRIMÉE** : le cran exécutable existait déjà (#933)

Énoncé du résidu : « Toute prémisse de montage de la forme *la normalisation met X à 0*, écrite
avant la bascule #419-r5, est suspecte — et **aucune n'est exécutable** […] le réflexe existe déjà
pour les COUPS sales et **nulle part** pour les STATS de base. »

**Les deux affirmations sont fausses depuis #933**, qui cite explicitement #914 §4.1 :
« #914 §4.1 l'avait nommé sans l'outiller […] Ce fichier est cette chose exécutable. »
`probe_933_premisses_regime.py` + `tests/engine/test_933_premisse_regime_offline.py` posent
exactement le cran demandé, sur exactement les quatre stats visées
(`_STATS_ZERO_OUVERT = CritChance, CritDamage, BlockChance, BlockDamage`), avec une dette
inventoriée et l'invariant « la liste ne grandit pas ».

## Ce qui restait vraiment ouvert : le COMPLÉMENT que #933 déclare ne pas visiter

`probe_933` l'écrit dans sa propre docstring : « Il ne visite PAS les probes
`scripts/python/probe_*.py`, ni la face DÉCISION hors tests, ni ce qu'un test atteint via la
fixture d'un autre paquet. » C'est le seul périmètre que #914-r2 ajoutait.

**Mesuré** (`probe_914r2_premisses_de_montage.py`, 2 056 fichiers, 157 342 fragments non
exécutables — commentaires + docstrings ; les messages d'assertion sont exclus **parce qu'ils sont
exécutables**, donc ils *sont* le cran, pas le vice) :

| étage | ce qui est compté | fichiers | fragments |
|---|---|---|---|
| (a) | mentionnent une des 4 stats | 179 | 1 503 |
| (a+b) | + affirment une absence / nullité | 179 | 420 |
| (a+b+c) | + parlent de MONTAGE | **26** | **33** |
| dont couverts par #933 (`tests/**/test_*.py`) | | 18 | |
| dont **complément** (probes, helpers) | | **8** | |

Sur ces 8, **3 sont les probes du sujet lui-même** (`probe_419r5_canal_crit_block`,
`probe_912_crit_zero_porteur`, ce recenseur), et sur les 5 restants le tri site par site donne :

* `probe_123_hailstrike_phase2.py` et `probe_373_path_of_command_extra_crit.py` — **déjà réparés**
  par #914/#912, leurs fragments *documentent* la péremption ;
* `probe_366_r1_inescapable_accuracy_override_hits.py` — la base est **forcée au montage**
  (`--crit 0,700`), la prémisse est donc établie, pas supposée ;
* `probe_505_bloody_fury.py` — **faux positif** : son `Block` est un nœud DSL, pas `BlockChance` ;
* `probe_113_votann.py::phase_fortune` — **le seul vice réel**, corrigé ici.

## Le seul site fautif, et sa réparation

`phase_fortune` prétendait exercer les deux sens des gates natifs `CanAddCritChance` /
`CanAddBlockChance` (`StatAmount(self, 9|7, INITIAL) > 0`) en s'appuyant sur une prémisse écrite :
« un héros FRAIS a critChance/blockChance de BASE = 0, ces stats viennent des ITEMS que la
normalisation strippe ». Depuis #419-r5/-r6 la normalisation **équipe** les items Best-In-Slot par
défaut : sans drapeau, la base n'est plus nulle, le gate est VRAI des deux côtés, et la phase
mesurait **deux fois le même sens en croyant les opposer**.

Le sens négatif se **construit** désormais (`--unit-stat <u>:CritChance=0,CritDamage=0` et
`BlockChance=0,BlockDamage=0` quand `--crit` / `--block` ne sont pas passés), jamais
`TACTICUS_BIS_ITEMS=0`, qui déshabille tout le roster (#914 §3.3).

## Le vice de RECENSEUR trouvé en chemin

Le premier balayage cherchait ses tokens en **sous-chaîne** : `crit` matche `critere`, `critique
de`, `description`. Mesure de l'écart, une fois passé en **frontières de mot** :
facteur (a) **5 853 → 1 503** fragments (**4 716 faux positifs, 81 %**), et le complément de #933
**49 → 8** fichiers. Un recenseur qui sur-compte d'un facteur 6 fait renoncer au tri site par site
qu'il est censé rendre possible — c'est le même mode de défaillance que le sous-comptage, dans
l'autre sens.

## Non couvert

Les deux autres angles morts que `probe_933` déclare — la face DÉCISION hors tests
(`engine_validate.py`, `predict_sweep.py`) et ce qu'un test atteint via la fixture d'un autre
paquet — ne sont pas balayés ici : le recenseur ne visite que commentaires et docstrings, il ne
suit aucune fixture.
