# #433-r4-r2-r4 — une contre-épreuve peut périmer sans que rien ne régresse

`test_433_r4_r2_adjacency_foyer_live.py` était **rouge sur `master`** (3 failed / 4 passed) et
n'avait rougi dans **aucune PR**. Le verdict : **l'oracle du test avait perdu son régime — aucun
port n'avait régressé.** Le port confronté est même **EXACT**, là où le test lui concédait un
résidu.

## 1. Le fait, daté par bisect

| commit | date | les 3 tests du couple |
|---|---|---|
| `3dbcd330` | 2026-08-04 20:29 | **3 passed** |
| `489bb349` | 2026-08-04 20:58 | **3 failed** |

Mêmes tests, même message (`sans le canal le port doit emettre un cast de 1077 (obtenu [])`).
Le commit responsable est `fix(#433-r4-r1-r4-r2)` — *`is_adjacent` lit la liste STOCKÉE, plus la
couronne hex*. C'est un **fix juste** : il rend le port plus fidèle. Il a cassé le test d'une
**autre tranche**, par un canal que ce test ne connaissait pas.

## 2. Pourquoi la mutation avait cessé de mordre — deux causes indépendantes

Le test neutralisait `elev_by_pos` et appelait cela « l'état d'AVANT `#433-r4-r2` ».

**(a) `elev_by_pos` n'est plus le seul canal du foyer d'adjacence.** Depuis `489bb349`,
`battle_query.is_adjacent` énumère d'abord `neigh_by_pos` — la liste stockée que
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` rend, donc **déjà traversée**
par la porte d'élévation de
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. La porte
re-jouée par le port est **idempotente** sur ce substrat — c'est écrit dans la docstring
d'`is_adjacent`, et c'est exactement ce qui vide la contre-épreuve.

MESURE (`probe_433_r4_r2_r4_canaux_adjacence.py`, les quatre combinaisons) :

| canaux passés au foyer | `adjacent_at_origin` |
|---|---|
| `elev` + `neigh` | `∅` |
| `neigh` seul (`elev_by_pos = None`) | `∅` |
| `elev` seul (`neigh_by_pos = None`) | `∅` |
| aucun | `{Y}` |

**Neutraliser un seul canal ne restitue rien.** Les deux disent la même chose sur cette arête.

**(b) `elev_by_pos` a un SECOND rôle depuis `feat(#433-r4-r2-r1-r2)`** : il est le substrat de la
ligne de vue d'`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (branche A). Le
neutraliser **élargit** la zone d'ability de l'ennemi. Le bras `off` ne mesurait donc plus une
cause : il bougeait deux mécanismes à la fois, et le cast disparaissait pour la **troisième**
raison — plus rien n'atteignait `MIN_UTILITY`.

## 3. Deuxième défaut, indépendant : la mesure confrontait un port AMPUTÉ

`rows` appelait `utility_at(P, enemies, adj)` **sans les canaux** que `generate_candidates` lui
passe (élévation, murs, équipes, walkability, brouillard). La divergence qui en sortait était
imputée au résidu LoS de la ZONE, et le test lui réservait la borne `<= 1`.

Canaux réellement passés, sur **quatre montages** de deux boards :

| montage | positions | port LIVRÉ ≠ natif | port CANAUX VIDES ≠ natif | port d'AVANT ≠ natif |
|---|---|---|---|---|
| `MC1_67` paire 0 (celui du test) | 34 | **0** | 1 | 6 |
| `MC1_67` paire 3 | 48 | **0** | 17 | 16 |
| `MC1_67` paire 9 | 30 | **0** | 1 | 10 |
| `MC1_61` paire 0 | 35 | **0** | 12 | 13 |

**147 positions, 0 divergence.** Le « résidu LoS 1/34 » était un artefact de mesure : le port
accorde le bonus de couverture dès qu'on lui donne la ligne de vue à lire. Sur la paire 3, le port
amputé divergeait sur **17/48** — la borne `<= 1` n'était donc pas une marge tolérante, c'était
une propriété d'un seul relief.

## 4. La contre-épreuve qui la remplace

Non plus une neutralisation de canal, mais **le port d'AVANT `#433-r4-r2`** : le partage A/B
tranché par `hexgeo.distance(origine, E) == 1`, **tous les autres canaux intacts**
(`EarlyWarningOverrideAvant433r4r2`, mixin d'une seule méthode). La mutation ne touche que le foyer
d'adjacence — condition pour qu'un écart lui soit imputable.

Ce qu'elle mesure, sur le montage figé du test :

* `adj_origin` : `∅` (livré) contre `{Y}` (avant) ;
* **6/34** positions divergentes pour le port d'avant, chacune valant exactement **un** bonus de
  couverture (50) ;
* l'action émise **change de tuile** : le port livré choisit `(5,2)`, que le natif évalue au
  **maximum de son sweep** (`10`) ; le port d'avant choisit `(3,0)`, que le natif évalue **`-40`**.

⚠ **Le SENS de l'écart n'est pas une propriété générale.** Sur la paire 3, la branche B est au
contraire MUETTE (`threshold = 3` non dépassé à `d <= 3`) là où la branche A verse : le port d'avant
y **sous-évalue** de 50 sur 16/48 positions. Seule la *quantité* (un bonus de couverture) est
invariante — d'où la valeur absolue dans l'assertion.

## 5. Ce qui aurait dû l'attraper, et ne l'a pas fait

* **Rien ne relie un canal à ses consommateurs de TEST.** `489bb349` a branché `neigh_by_pos` sur
  **62 call-sites** et posé un cliquet (`probe_433r4r1r4r2_neigh_channel_wired`) qui vérifie que
  les call-sites *lisent* le canal. Aucun garde ne demandait l'inverse : *quels oracles supposent
  qu'un canal est le SEUL à porter une exclusion ?* Une contre-épreuve bâtie sur « je coupe le
  canal X » devient muette dès qu'un canal Y redondant apparaît — **sans erreur, sans changement
  de code chez elle**.
* **Le test n'était joué par personne.** Il ne figure pas dans les 49 empreintes de
  `scripts/ratchets-457-footprints.json`, et « tests ciblés uniquement » veut dire que la PR qui
  branche `is_adjacent` joue les tests d'adjacence, pas ceux d'`EarlyWarningOverride`. Le rouge a
  survécu à **trois merges**.
* **La mutation n'était pas vérifiée.** Le test assertionnait le RÉSULTAT de la mutation
  (`adj_off == [Y]`), donc il *aurait dû* attraper (a)… et il l'a fait — mais seulement une fois
  quelqu'un l'a joué. Le verrou ajouté
  (`test_neutralising_one_channel_alone_no_longer_restores_adjacency`) fixe désormais la
  **redondance elle-même**, en quatre lectures : si un jour un seul canal suffit à restituer
  l'adjacence, c'est la nature de la mesure qui a changé, et toute contre-épreuve bâtie dessus est
  à relire.

## 6. Résidus

* **`#433-r4-r2-r4-r1`** — *aucun garde ne relie un canal partagé aux ORACLES qui le supposent
  exclusif*. Le cliquet de `489bb349` vérifie que les call-sites de production lisent le canal ;
  il ne voit pas les probes/tests qui **coupent** un canal pour fabriquer une contre-épreuve. Point
  d'ancrage : recenser les `dataclasses.replace(ctx, <canal>=None)` des probes et tests, et
  confronter chacun à la liste des canaux que son foyer consulte.
* Le volet ZONE de `#433-r4-r2-r1` reste **nommé** (une divergence LoS peut exister sur un autre
  relief) mais **n'est pas observable** sur les 4 montages mesurés ici. Le test ne lui réserve plus
  de marge : une divergence y serait un fait à expliquer, plus un résidu admis.

## 7. Non couvert

* **`MC2_60`** (le board au plus fort relief, 124 paires `|dElev| >= 2` hors-ligne) : **aucune**
  paire installable en live — toutes portent au moins une tuile non marchable. Régime absent, pas
  d'échec de port.
* Le montage reste **un caster / un ennemi** (`tauCrisis` / `tauMarksman`). Le terme
  `Sum_E` de la boucle native n'est donc pas confronté à plusieurs ennemis simultanés.
* **`#433-r4-r2-r3`** (le `MIN_UTILITY = 1` contesté) n'est pas touché : il gouverne l'existence du
  cast, et les deux bras de la nouvelle contre-épreuve émettent tous les deux.
