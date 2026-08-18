# #10031 — Un contre-témoin MUET pendant 13 jours, et un plancher qui tombait sur le PROGRÈS

Deux rouges de `master`, deux causes différentes, **aucune des deux n'était une dette de port**.
Les deux vivaient sur la face LIVE, que `probe_457_offline_tests_green.py` exclut par construction
(cf. `case-10033`).

---

## 1. `test_381r4_imperative_collapses_live.py` — le cliquet A RAISON, l'instrument était cassé

### Le symptôme

```
FAILED ::test_l_atterrissage_de_vigilance_eternal_suit_le_gate
  aucune geometrie ou le gate #131 change l'atterrissage sur C2_26 -- le test ne prouverait rien
```

C'est un **auto-contrôle de discriminance** : `_pick_geometry` balaie tous les couples
(caster, cible) et cherche une position où le port **GATE** et le port **NON GATE** désignent deux
tuiles différentes. Il n'en trouvait aucune. Le message accuse le **board**.

### La cause, mesurée

Le contre-témoin `_no_gate()` désarme le gate d'expansion #131 en posant
`tile_blocking.make_can_continue = lambda: None` — c'est-à-dire en substituant l'attribut du module
**SOURCE**. Ça ne mord que si le **consommateur** résout ce nom **à l'appel**.

`git log -S` sur le foyer :

| commit | date | ce qu'il fait |
|---|---|---|
| `7845700b` | 2026-08-01 | ouvre `#381-r4` ; l'import est **fonction-local** (forme C, ligne 316, indentée) → le patch **MORD** |
| `492c722f` | 2026-08-05 | « hisser 624 imports differes d'engine/ au niveau module » → **forme A**, ligne 42, au niveau module → le patch **NE MORD PLUS** |

Mesure directe de la morsure, en trois lignes :

```
avant:       MQ.make_can_continue is TB.make_can_continue -> True
apres patch: MQ.make_can_continue is patched              -> False
MORSURE: NON
```

Et l'effet, sur le probe compagnon (`probe_381r4_imperative_collapses.py --board C2_26 --mutate
no-gate`) :

| régime | sorties de site changées | `rc` |
|---|---|---|
| forme A (état de `master`) | **0** — « le bras NE DISCRIMINE PAS » | 1 |
| forme B (après correctif) | **483** (charge 92+83+151, betrayer 157, hypersensory 0) | 0 |

### Ce que la mesure a montré en plus, et que l'inventaire n'avait pas vu

Rejoué en régime `master` (forme A **et** fichier de test d'origine), **les DEUX tests du fichier
échouent**, pas un seul — le premier sur son propre auto-contrôle (`assert gate_bit`, « le gate
#131 ne change le pool d'AUCUNE des N unités confrontées »). L'inventaire d'entrée n'en citait
qu'un.

### Trois instruments visaient ces deux noms. Un seul était joué.

| instrument | joué par un cliquet ? | ce qu'il est devenu |
|---|---|---|
| `test_381r4_imperative_collapses_offline.py` | **oui** (`probe_457`) | a rougi tout de suite, **réparé AU SITE DE MESURE** : il patchait aussi `MQ.make_can_continue` |
| `test_381r4_imperative_collapses_live.py` | non | **rouge 13 jours**, message accusant la géométrie |
| `probe_381r4_imperative_collapses.py` | non (aucun cliquet ne joue les probes) | **`rc 1` 13 jours**, même fausse accusation |

Le contournement au site de mesure est le point important : il a **reverdi le seul témoin visible**
et laissé la cause en place. C'est ce qui a rendu le désarmement durable.

### Le correctif

`engine/services/movement_query.py` repasse `make_can_continue` **et** `is_like_flying` en
**FORME B** (liaison de module, résolue à l'appel) — la seule des trois formes qui garde la
morsure. Le même fichier portait déjà, huit lignes plus bas, trois imports en forme B avec le
commentaire qui l'explique : la règle était écrite au-dessus du site qui la violait.

### Le cran anti-récidive

`tests/engine/services/test_10031_morsure_des_mutations_offline.py`, **deux étages qui ne tombent
pas pour la même raison** :

* **E1 — l'EFFET** : la mutation `no-gate` doit changer au moins une sortie de site. Invariant de
  bout en bout, indifférent au mécanisme du désarmement. Ne dit pas **où** c'est cassé.
* **E2 — la CAUSE** : aucune liaison **figée** (forme A) neuve sur un nom substitué. Dérivé de bout
  en bout — les couples viennent de l'**AST des instruments eux-mêmes**
  (`morsure_substitution.cibles_substituees`), les liaisons d'un balayage AST de tout `engine/**`.

**Contre-épreuve jouée** : re-hissé en forme A, `3 failed` — E1 et E2 rougissent tous les deux, et
E2 **nomme le fichier fautif**. Restauré : `4 passed`.

`morsure_substitution.py` porte deux lectures, et elles ne voient pas la même chose :
`liaisons_figees` (RUNTIME, ne voit que les modules chargés — la bonne pour une garde locale, qui ne
doit pas rougir sur un chemin non exercé) et `liaisons_figees_statiques` (AST, voit ce qu'aucune
passe ne charge — la bonne pour un cliquet). Ni l'une ni l'autre ne remonte un simple **ré-export** :
le critère « appelle le nom » est dérivé de l'AST.

### L'outil qui aurait dû le voir, et pourquoi il ne l'a pas vu

`migrate_485r1_barils_reexport.py morsure` **connaît** ce gisement : il a une catégorie
`HISSAGE_DESARMERAIT`. Mais son périmètre est l'ensemble des imports **DIFFÉRÉS** — donc il est
**préventif**. Une fois le hissage consommé, le couple sort de son écran et retombe dans
`DEJA_INERTE`, un **inventaire non bloquant de 66 lignes** où `make_can_continue` et
`is_like_flying` figuraient tous les deux, noyés. L'outil disait vrai et personne ne le jouait :
ce n'est pas un test.

### Résidu

**#10031-r1** — deux liaisons figées **réelles** subsistent, hors du chemin de `#381-r4` :
`engine/ai/state_bridge.py` (`make_can_continue`) et `engine/runner/operations/movement.py`
(`is_like_flying`). Elles sont **attestées et nommées** dans
`scripts/ratchets-10031-liaisons-figees.json`, qui ne doit que **décroître**. Les réparer ferait
**mordre** des mutations là où elles ne mordent pas aujourd'hui, donc changerait le verdict de
mesures appartenant à `#448` et `#381-r1` — à faire par une tranche qui pourra les re-jouer.

---

## 2. `test_510_light_of_sanguinius_live.py` — PRÉMISSE EXPIRÉE

### Le symptôme

```
FAILED ::test_le_cablage_du_registre_est_complet
  assert len(TARGETING_OPTIONS_UNPORTED) > 10
  assert 0 > 10  +  where 0 = len({})
```

Le témoin était écrit « … et la table n'est PAS vide : le retrait de 1177 est CIBLE, pas un
effacement ».

### La cause

La table est **vide**, et elle l'est **légitimement**. Ses entrées en sont sorties **une à une**,
par MIGRATION de leur masque sur leur classe (contrat de disjonction), chaque sortie étant nommée au
site dans `targeting.py`. Le dernier retrait est `c3eb44a2` (#996-r1-r3, 2026-08-14,
`1015 PrecisionShot`), dont le message porte l'audit régénéré : `actives=175 ported=174 no-op=0`.

Mesuré : `TARGETING_OPTIONS_UNPORTED` = **0**, `DYNAMIC_TARGET_RULE_UNPORTED` = **0**,
`ABILITY_CLASSES` = **182**, `probe_181_targeting_gaps` = **182/182, 0 manquante**.

C'est un **plancher de population qui rougit sur le PROGRÈS** — le cas exact décrit par
`feedback_floor_replacement_is_usually_dominated`.

### Le geste : retirer le plancher, et RIEN d'autre — parce que c'est mesuré

Sept mutations jouées à l'ablation ; pour chacune, l'assertion qui tombe **en tête** :

| mutation | assertion qui tombe |
|---|---|
| 1177 sort du registre | l.135 `cls is not None` |
| 1177 revient dans la table | l.136 disjonction |
| masque effacé de la classe | l.142 `opts is not None` |
| masque FAUX (`0x4002`) | l.145 la somme de bits |
| `AbilityAttackType` absent | l.153 |
| le témoin 1204 sort du registre | l.164 |
| **table RE-PEUPLÉE à 12 entrées BIDON** | **AUCUNE** |

Le plancher n'arrive en tête d'**aucune** des six mutations réelles — il est **dominé** — et la
septième montre qu'il était **satisfiable par du bruit**. Une assertion « plus riche » posée à sa
place serait le vice symétrique (une remplaçante qui ne rougit jamais).

### Ce qui garde déjà ce qu'il prétendait garder, en INVARIANT

* `tests/engine/runner/test_targeting_options_sources.py::test_la_deuxieme_source_reste_CONSULTEE_meme_table_vide`
  — injecte une entrée **bidon** par monkeypatch : le **mécanisme** de la 2ᵉ source est gardé
  indépendamment du contenu de la table. Et `test_les_deux_sources_de_masque_sont_disjointes` garde
  le contrat. **5 passed.**
* `probe_181_targeting_gaps.py` — « masques manquants == 0 », l'invariant que le CLAUDE.md oppose
  déjà explicitement aux seuils.

La mesure et l'interdiction d'en reposer un sont écrites **au site**.

### Validation

`test_510_light_of_sanguinius_live.py` **entier**, live compris : **10 passed** (les six étages du
cast natif inclus).
