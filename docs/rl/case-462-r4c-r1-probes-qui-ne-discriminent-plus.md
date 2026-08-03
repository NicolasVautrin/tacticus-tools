# #462-r4c-r1 — `probe_212` / `probe_241` : ils tournaient, ils ne discriminaient pas

**Statut : LIVRÉ (2026-08-03).** Trois vices distincts, tous mesurés sur `origin/master` avant
correction. Le résidu `#462-r4c-r1` est fermé.

---

## 1. Réponse à la question binaire, probe par probe

### `probe_212_spiritual_leader_tile_term.py` — le CAP de `SpiritualLeaderPlaybook` (1275)

> **A. CAP** — sur les candidates **sans occupant steppable** (là où `X_nat` se réduit au terme de
> 1275), `X_nat` est-il le MÊME pour n = 1, 2, 3 decoys alliés adjacents ?
> **B. ACCORD** — tuile par tuile, `X_nat == X_port` ?

| | |
|---|---|
| **Volet A** | **OUI, le cap mord.** `X_nat` = 30 pour n = 1 **et** n = 2, `0` à n = 0 (21 tuiles hookées, `MC1_67`/777) |
| **Volet B** | **OUI**, `X_nat == X_port` sur les **21** tuiles |
| **Ce que le probe rendait avant** | `rc = 0` **inconditionnellement** — il imprimait `DELTA = -9` sur l'origine de `genesMagus` et passait quand même |

### `probe_241_decoy_tile_leaves.py` — les deux feuilles à occupant steppable

> **A. RÉGIME** — le montage réalise-t-il la condition (≥ 1 candidate à occupant steppable ami,
> ≥ 1 sans) ? **B. ACCORD** — `X_nat == X_port` ? **C. PAS DE FILTRE DE POSITION** — la
> contribution des deux feuilles est-elle constante sur des tuiles à distances DIFFÉRENTES des
> porteurs de 1304 ?

| | |
|---|---|
| **Volet A** | **OUI** — 2 tuiles à occupant steppable ami, 5 sans (7 hookées, `MC1_67`/777) |
| **Volet B** | **OUI**, `X_nat == X_port` sur les 7 |
| **Volet C** | **OUI** — contribution native **constante (25)** sur des tuiles à distance **1 et 3** du porteur |
| **Ce que le probe rendait avant** | `rc = 1` : **3 tuiles / 16 « en désaccord »** — un rouge qui accusait le PORT alors que le port était juste |

---

## 2. Vice n° 1 — la MESURE était fausse (`X_port` retranchait la mauvaise feuille)

`X_nat = Tile(7) − Elevation − TileEffects` : les deux membres de la comparaison doivent porter le
MÊME retranchement. Trois probes portaient encore des **littéraux** :

```python
p_x = sum(leaves.values()) - leaves.get(8, 0.0) - leaves.get(9, 0.0)
```

Depuis #254 (`AttackTile` inséré en 8), `Elevation` vaut **9** et `TileEffects` **10**. Ces probes
retranchaient donc `AttackTile` — **absente de `TILE_UTILITY.children`**, donc `0.0` — puis
`Elevation`, et **jamais `TileEffects`**. `probe_193c` avait reçu ce correctif ; #212, #241 et #242
ne l'avaient pas.

**Mesure du 2026-08-03**, `probe_241` sur `MC1_67`/777, les 3 « désaccords » :

| tuile | DELTA | `TileEffectsUtility` du port |
|---|---|---|
| (3,6) | −9 | +9 |
| (4,6) | +25 | −25 |
| (1,6) | +25 | −25 |

`DELTA == −TileEffects`, exactement. Le foyer est désormais **unique** :
`probe_193c_move_playbook_terms.x_port()` (et `x_excluded()` pour l'affichage — les trois probes
filtraient aussi leurs colonnes sur `(8, 9)`, donc montraient `Elevation` comme une feuille du terme
et cachaient une colonne vide).

⚠ `probe_242` portait le même littéral et est corrigé par la même passe : même faute, même foyer.

## 3. Vice n° 2 — `probe_212` ne pouvait pas RENDRE un rouge

Sa phase finale se terminait par `return 0`, quel que soit le `DELTA` mesuré. Il ne rougissait que
sur « régime non atteint ». C'est ainsi que le `−9` du vice n° 1 est resté invisible.

Il rend maintenant `rc != 0` sur chacun des deux volets, et `rc = 2` quand l'échantillon ne les
exerce pas. Le volet A est une mesure **native** du cap, indépendante du port : on restreint aux
tuiles **sans occupant steppable** (celles où les feuilles 19/64 de #241 sont muettes) et on vérifie
que `X_nat` y est PLAT pour tout n ≥ 1 et différent de sa valeur à n = 0.

## 4. Vice n° 3 — l'échantillon était SUBI

Le régime s'obtenait en marchant la trajectoire native jusqu'à ce que la géométrie de spawn veuille
bien le produire — pas **47** pour #212, pas **21** pour #241, en dur dans les tests live. Rien ne
fige ces numéros : c'est ce qui a fait rendre à un autre lecteur « trajectoire épuisée au pas 38,
aucune activation qualifiée ».

**On pilote désormais les positions** (patron `_drive_cluster` de #242) :

* `walk_driven(call, rid, carrier_id, wants, goals_of, ...)` — marche la trajectoire native et
  **yield** les états de décision où `wants` est vrai ; sinon elle DÉPLACE le carrier vers
  `goals_of(...)` et termine le tour des alliés. Foyer partagé par les deux probes **et** par les
  deux tests live.
* `_drive_carrier_toward` — se pose sur la tuile visée si elle est atteignable (elle devient
  l'**origine** du carrier, donc une candidate garantie du tour suivant), sinon au plus près ;
  `goals` vide ⇒ régime de **SEMIS** (on s'éloigne des decoys déjà adjacents, pour que le second
  volet de `SpiritualLeaderAbility$$CreateBehaviour` — `AmountIsEqualOrGreater(GetAdjacentDecoys(),
  Direct(2))` — n'invoque pas un Neophyte qui **écrase** le decoy qu'on vient de poser).

**Le drive s'auto-alimente** : le `move` du carrier déclenche `On(0x1c = ArrivedAtFinalTile)`, donc
la face COMBAT de `SpiritualLeader` pose un decoy de plus. Rapprocher le carrier et enrichir le
plateau sont le même geste.

Les cibles diffèrent, et c'est le cœur du montage :

| probe | `goals_of` | pourquoi |
|---|---|---|
| #212 | les tuiles à **≥ 2 decoys alliés adjacents** (`_rich_tiles`) | s'y poser fait de la tuile riche l'origine du carrier ; le bord de son rayon reste à n = 0 |
| #241 | les tuiles d'où les decoys se voient à des **distances VARIÉES** (`goals_241`) | viser « adjacent à un decoy » ne suffit pas — mesuré : le carrier se posait au contact d'un cluster serré, les deux candidates à occupant tombaient à la MÊME distance, et le volet C rendait `NON EXERCÉ` |

Dans les deux cas, `avoid` = les positions des decoys : **fouler un decoy le CRUSHE**
(`AddUnitOperation$$KillSteppableUnits`).

### 4.1 `decisionView` ne publie PAS `traits`

Première version du drive : `0 decoy(s) allié(s)` à chaque activation, alors que trois candidates
portaient un `genesSmnDecoy`. Les traits **runtime** passent par `combatSnapshot`
(`frida/hooks/features/ai-step/rpc-snapshot.ts`, #233), pas par `decisionView` — un filtre
`DECOY_TRAIT in u["traits"]` sur `decisionView` rend donc **toujours** la liste vide, sans erreur.
Le drive restait en mode SEMIS en permanence. `_ally_decoys` lit le `leaf_ctx` du port, la même
source que `_decoys_adjacent`.

---

## 5. Validation

### 5.1 Avant / après, mesuré

| | avant | après |
|---|---|---|
| `probe_212` — pas où le régime est réalisé | **47** (subi) | **23** (2 drives) |
| `probe_212` — tuiles hookées | 15 | **21** |
| `probe_212` — verdict | `rc=0` **malgré** `DELTA=-9` | `rc=0`, volets A et B explicites, 0 désaccord |
| `probe_241` — pas | **22** (subi) | **34** (2 drives) |
| `probe_241` — désaccords | **3 / 16** (faux : `−TileEffects`) | **0 / 7** |
| `probe_241` — volet C | `NON EXERCÉ` (toutes à d = 2) | **prouvé** : d = 1 et 3, contribution constante 25 |

### 5.2 Contre-épreuves — le verdict CHANGE quand on casse ce qu'il garde

| mutation | attendu | **mesuré** |
|---|---|---|
| `SpiritualLeaderPlaybook.MAX_ADJACENT_FRIENDS = None` (cap retiré) | #212 volet B rouge : le port somme `30 × n` | **rc=1**, `4/21` tuiles à `DELTA = −30`, **toutes à n = 2**. Le volet A reste **OK** — il mesure le NATIF, pas le port |
| retranchement remis aux littéraux `(8, 9)` | volet B rouge, `DELTA = −TileEffects` | **c'est l'état d'avant ce commit** : `probe_241` rc=1, **3/16** |
| pose de `meta["steppable"]` retirée (`apply_tile_attributes`) | #241 volet B rouge sur les tuiles à occupant | **rc=1**, `2/7` tuiles à `DELTA = +25`, colonne `f19+f64` à **0**. Volets A et C restent verts |
| profondeur ramenée à 4 pas (`--max-steps 4`) | `ECHANTILLON NON CONFRONTABLE`, rc=2 | **rc=2**, message conforme, aucun armement |

La première ligne est la plus instructive : elle **sépare** les deux volets. Le cap disparu, le
natif continue de rendre 30 (volet A vert) et c'est le PORT qui diverge (volet B rouge, `−30` par
decoy surnuméraire). Un probe qui n'aurait qu'un scalaire aurait rendu « désaccord » sans dire de
quel côté.

Le montage piloté est **reproductible** : les deux passes de `probe_241` (saine et mutée) s'arrêtent
au **même pas 34**, sur les mêmes 7 tuiles hookées — seul le verdict change.

### 5.3 Gardes live

Les deux tests live passent au montage **piloté** (plus de numéro de pas en dur) et leurs gardes de
RÉGIME passent sous `counterproof.assert_sample_confrontable` (#462-r6) — un montage qui ne réalise
plus son régime n'accuse ni le port ni le harnais, et le nom du type traverse jusqu'au ledger de
`probe_462` :

* `test_spiritual_leader_tile_term_live.py` : `test_case_still_activates_the_carrier`,
  `test_montage_exercises_more_than_one_adjacent_decoy`, et l'échec de montage de la fixture ;
* `test_steppable_decoy_tile_leaves_live.py` : idem + l'assertion « au moins un ami porteur de
  1304 » **au sein** de `test_leaves_fire_exactly_on_tiles_with_a_friendly_steppable_occupant` — la
  granularité est l'ASSERTION, pas le test (cette fonction mêle échantillon et fond).

Attestation `probe_462 --run --since origin/master` (mur 335,2 s, 2 workers) :
**2 fichiers, VERT 2 / ROUGE 0** — `test_spiritual_leader_tile_term_live.py` **10 passed**,
`test_steppable_decoy_tile_leaves_live.py` **14 passed**, 0 skipped des deux côtés (mêmes comptes
qu'avant le changement de montage : le pilotage n'a **rien retiré** de la couverture).

---

## 6. Ce qui n'est PAS couvert

* **Le volet A de #212 ne mesure le cap que jusqu'à n = 2** sur le montage piloté (le montage subi
  atteignait n = 3). `Min(count, 1)` ne se distingue de `Min(count, 2)` qu'à partir de n = 2 : le
  cap est donc bien tranché, mais une valeur de cap **> 2** ne serait pas séparée de `None` par ce
  seul montage. `MIN_RICH` est la poignée.
* **Un occupant steppable ENNEMI** n'apparaît sur aucun de ces montages (les decoys sont du côté du
  mover) : la branche `EnemyDecoy` / `EnemySteppableUnit` de la feuille 19 reste couverte par les
  seuls tests de table de branchement (offline), comme le disait déjà `case-241` §4.4.
* **Les deux branches court-circuit** (`SpikySting` 77, `LandMine` 114) restent sans porteur.
* **Le second board** (`C4_09`/31337) est exercé par les tests live, pas par les passes de probe
  rapportées ici.

## 7. Résidus

* **`#462-r4c-r1-r1`** — `probe_242_fabricator_claw_cap.py` a reçu le correctif de retranchement
  (§2) mais **n'a pas été re-joué** dans cette passe : son montage `--min-rep 2` exige des alliés
  Mechanical BLESSÉS, donc une bataille longue. Le correctif est value-preserving tant qu'aucune
  candidate ne porte d'effet de terrain — ce qui n'est pas garanti. À re-jouer tel quel.
* **`#462-r4c-r1-r2`** — `walk_driven` termine le tour des alliés à chaque drive. C'est ce qui rend
  la convergence rapide, mais cela **écarte la trajectoire native** : les états mesurés ne sont pas
  ceux qu'une partie non pilotée produirait. Sans effet sur ce qui est mesuré ici (l'utilité d'une
  tuile ne dépend que de l'état, pas de son histoire), mais à ne pas réutiliser tel quel pour une
  mesure sensible à la trajectoire.

## 8. Reproduire

```bash
cd scripts/python
python probe_212_spiritual_leader_tile_term.py --board MC1_67 --seed 777 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python probe_241_decoy_tile_leaves.py --board MC1_67 --seed 777 --carrier genesPrimus --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python -m pytest tests/engine/test_spiritual_leader_tile_term_live.py
python -m pytest tests/engine/test_steppable_decoy_tile_leaves_live.py
```

`--no-drive` rejoue le régime SUBI sur les deux probes (contre-épreuve du montage).
