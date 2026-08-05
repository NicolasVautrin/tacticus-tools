# #433-r4-r2-r4-r1 — quelles contre-épreuves supposent qu'un canal est le SEUL à exclure

Question posée par `#433-r4-r2-r4` : une contre-épreuve « je neutralise le canal X, le port doit
alors diverger » devient **muette** dès qu'un canal Y redondant apparaît — sans erreur, sans que
son code change. Quelles autres l'ont fait, et peut-on rendre l'hypothèse **détectable** ?

## 1. L'inventaire, dérivé (`probe_433_r4_r2_r4_r1_contre_epreuves.py`)

Tous les chiffres viennent d'un balayage AST de `git ls-files scripts/python`, aucun n'est écrit.

| étage | mesure |
|---|---|
| mutations neutralisantes (`replace(o, champ=<neutre>)`) | **31** sur 18 fichiers |
| dont un canal de CONTEXTE | **4** (toutes `elev_by_pos`) — les 27 autres mutent `TargetingOptions` (`range` 17, `rules` 7, `self_cast` 1) et ne sont pas des canaux |
| foyers d'`engine/` à **≥ 2** canaux `*_by_pos` | **23** |
| contre-épreuves **à deux bras** par `replace` | **3** (1 fichier) |
| contre-épreuves **à deux bras** par ARGUMENT omis, callee = foyer réel | **17** (10 fichiers) — 33 avant filtrage du callee, la moitié étaient des `len()`/`sorted()` |
| **total du gisement** | **25 sites** (le compte monte à 25 une fois les positionnels résolus) |

**Le gisement n'est donc ni vide ni réduit au cas parent** — mais il est concentré : deux familles
de canaux seulement, `elev_by_pos`/`neigh_by_pos` (adjacence) et `walkable_by_pos`/`is_in_fog_by_pos`
(walkability, les deux volets de `IdunBattle.Entities.TileExtensions$$IsWalkable`).

## 2. Le régime à risque EXISTE, et il est mesuré à l'exécution

Le probe INTERCEPTE les foyers (patch de `sys.modules`, pas du seul module de définition — les
call-sites importent par `from ... import`), rejoue les tests offline, puis **re-joue chaque appel
capté** avec un canal neutralisé.

Sur **2 800 appels** captés par 7 fichiers offline :

| foyer | appels | exclusion REDONDANTE | porteur unique |
|---|---|---|---|
| `is_adjacent` | 2 079 | **40** | `elev_by_pos` 293, `neigh_by_pos` 35 |
| `are_entities_adjacent` | 642 | **11** | `elev_by_pos` 77, `neigh_by_pos` 6 |
| `_unwalkable` | 23 | **3** | `walkable_by_pos` 7, `is_in_fog_by_pos` 4 |
| `is_tile_in_range_of_any_ability` | 20 | **3** | `elev` 4, `walkable` 4, `is_in_fog` 2 |
| `newly_adjacent_ids` / `is_charging` / `count_adjacent*` / `adjacent_addable_count` / `_ability_covers_tile` | 30 | **10** | — |

**67 appels sur 2 800** (2,4 %) sont dans le régime exact du piège : neutraliser UN canal ne
restitue rien, neutraliser TOUS restitue. Le piège n'était pas un accident de `#433-r4-r2`.

## 3. Y en a-t-il d'autres MUETTES aujourd'hui ? — NON

`--step verdict` : **13 sites mono-canal MESURÉS par rejeu, 0 muet**. Les 7 fichiers offline
portant ces contre-épreuves rendent **126 passed**.

Deux observations non bloquantes en sont sorties :

* **2 tests n'isolent pas l'étage que leur nom promet.**
  `test_newly_adjacent_ids_etage_ENUMERATION` et `..._etage_PORTE_ELEVATION`
  (`test_433r4r1r4r2r1_foyers_voisins_offline.py`) comparent « aucun canal » à « les DEUX
  canaux » : ils prouvent que le couple mord, pas lequel. L'attribution y est réelle mais vit dans
  le **montage** (board `coupe=[...]` contre `elev={...}`), pas dans l'assertion — et la mesure le
  confirme : dans le premier, seul `neigh_by_pos` est porteur unique ; dans le second, seul
  `elev_by_pos`. Une coupure multi-canaux **discrimine sans attribuer** ; c'est hors verdict.
* **7 sites NON MESURÉS** (5 probes live + 2 formes non captées), rendus comme tels, jamais verts.

## 4. Le garde — et pourquoi il n'est PAS un cliquet de couverture

Le mécanisme qui NOMME un rouge de scénario existait déjà : `counterproof.py` (#462-r6), avec
`InertCounterproof` / `UnconfrontableSample` et le canal type → JUnit → ledger `probe_462`.
Sa docstring déclare qu'on ne peut pas *dériver* qu'une assertion est un contre-contrôle. C'est
vrai en général — **et faux pour la forme qui a coûté** : la neutralisation est explicite, le foyer
est nommé, et ses autres canaux se lisent dans sa signature.

D'où `counterproof.assert_channel_counterproof*`, qui MESURE les trois causes au lieu de les
confondre :

```
seul != base              -> la mutation MORD              -> silence
seul == base != tous      -> un AUTRE canal l'exclut       -> InertCounterproof, canal NOMMÉ
seul == base == tous      -> l'état est hors régime        -> UnconfrontableSample
```

Deux façades, canaux **DÉRIVÉS** — signature du foyer (`assert_channel_counterproof_call`) ou
champs de la dataclass (`..._ctx`) — jamais une liste écrite à la main : `is_adjacent` a gagné
`neigh_by_pos` en 4ᵉ position sans que rien ne le signale, et c'est exactement ce qu'une liste
manuelle rate.

**Pas de cliquet de couverture** (« ce site ne passe pas par le helper ») : les 17 sites restants
sont tous justes aujourd'hui, et un garde qui les ferait rougir en bloc se ferait désarmer. Le
helper, lui, a **zéro faux positif par construction** : il ne parle que quand la mutation a
effectivement cessé de mordre.

## 5. Contre-épreuve du garde — chiffrée

Le montage des trois contre-épreuves de `#433-r4-r2` est rendu **muet artificiellement** (on peuple
`neigh_by_pos` sans l'arête visée, ce que `489bb349` a rendu décisif en live) :

| | verdict | message |
|---|---|---|
| AVANT (état `master`) | 3 × `AssertionError` | *« le port doit retomber sur la distance hex nue »* — **2 sur 3 accusent le PORT** |
| APRÈS | 3 × `InertCounterproof` | *« le canal neutralisé n'est PAS le seul à porter cette exclusion »*, `neigh_by_pos` **nommé**, remède + renvoi à `#433-r4-r2-r4` |

`tests/test_433r4r2r4r1_channel_counterproof_offline.py` (8 tests) fixe les deux directions sur le
foyer RÉEL (`battle_query.is_adjacent`) et la paire de canaux RÉELLE, y compris le **rejeu du
2026-08-04** sur `EarlyWarningOverridePlaybook`. Il est OFFLINE, donc joué par `probe_457` — le
garde est dans une liste qu'on lance, sans ajouter d'entrée à la banque (même canal que #462-r6).

## 6. Trois fautes du probe, trouvées sur son PROPRE premier jet

Elles valent d'être écrites : chacune rendait un chiffre faux **sans erreur**.

1. Un argument **positionnel** résolu par le nom de la VARIABLE et non du PARAMÈTRE
   (`is_adjacent(t, p, elev, neigh)` passe `neigh` à `neigh_by_pos`) : **8 faux positifs sur 9**.
2. `tous les canaux coupés == base` traité comme « aucun canal ne mord » : faux, deux canaux de
   sens **opposés** se compensent (couper l'élévation ÉLARGIT, couper l'équipe RESTREINT dans
   `is_tile_in_range_of_any_ability`). Le `continue` sautait la mesure par canal et déclarait
   MUETTE une contre-épreuve qui mordait.
3. Périmètre entièrement NON MESURÉ rendu **PASS** (20/20 au premier jet, matching de nodeid
   cassé) : c'est le vice « un balayage vide se lit *rien à signaler* ». Rend désormais **99**.

## 7. Résidus

* **`#433-r4-r2-r4-r1-r1`** — *les 17 sites mono-canal restants ne passent pas par le helper*. Ils
  sont justes aujourd'hui (mesuré : 13 mesurés, 0 muet ; 4 hors rejeu), donc rien ne presse ; mais
  chacun rejouera l'incident tel quel s'il devient muet. Migration à faire au fil des tranches qui
  les touchent, pas en bloc. Point d'ancrage :
  `python scripts/python/probe_433_r4_r2_r4_r1_contre_epreuves.py --step verdict`.
* **5 contre-épreuves de PROBES live** (`probe_433_r4_r2_r1_r2_line_of_sight`,
  `probe_433_r4_r2_r1_r2_r2_r1_walkability`, `probe_433r4r1r4_elevation_gate_perimeter` ×2,
  `probe_433r4r1r4r2_is_adjacent_substrat_live`, `probe_433r4r1r4r2r1_solde_par_foyer` ×2) : hors
  rejeu pytest, donc **NON MESURÉES**. Le helper leur est applicable tel quel.

## 8. Non couvert

* **Le LIVE.** Les 2 800 appels viennent de 7 fichiers OFFLINE ; c'est une borne INFÉRIEURE du
  régime, et probablement large — c'est en live que `neigh_by_pos` est réellement peuplé.
* **Les formes de contre-épreuve qui ne passent ni par `replace` ni par un argument** : sous-classe
  « port d'AVANT » (`EarlyWarningOverrideAvant433r4r2`) et `monkeypatch.setattr`. La première est
  précisément le REMÈDE recommandé par `#433-r4-r2-r4` (muter le foyer, pas un substrat) et ne
  souffre pas du vice ; la seconde n'est pas détectable statiquement (le bras muté est temporel).
* **Les canaux qui ne sont ni `*_by_pos` ni l'un des 5 scalaires lus** (`walkable`, `is_in_fog`,
  `elevation`, `neigh`, `is_wall`) : un canal nommé autrement sort du vocabulaire et du balayage.
