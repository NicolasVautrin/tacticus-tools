# case-254-bc — le bloc `Units` du seed BC est périmé, et son SILENCE valait un rouge mal attribué

Dispatché comme « #449 — rouge pré-existant sur `master` » : `test_catalog_inject_live.py::
test_synthese_reproduit_le_catalogue_capture` échouait.
**Accusé : ni la synthèse, ni le test — la DONNÉE.** Mesure :
`scripts/python/probe_254bc_seed_bc_units_perime.py` (4 étapes, 100 % offline).

## 1. Le rouge, et son vrai accusé

```
divergences UNITS: {'PassiveAbilities': [('necroOverlord', [1556], [1045])],
                    'Traits':           [('necroOverlord', [... 'Resilient'], [...])]}
```

`catalog_inject.validate` re-synthétise les 175 entrées `Units` capturées et les diffe. Résultat
re-dérivé : **174 fidèles au bit près, 1 divergente**, et **277/277 configs d'ability** fidèles à la
capture BRUTE hors les 3 dérives que le rattrapage #254 répare déjà. La synthèse est donc juste.

Ce qui a cédé n'est pas du code, c'est la **prémisse** de la confrontation : elle ne vaut que si les
deux côtés viennent du **même build**. La capture est figée (`data/seed-bc.json`, **un seul commit**,
`f467e649`) ; `gameconfig.py` lit le fichier **vivant**, donc celui du build courant.

## 2. Datation — aucun commit n'est en cause

| artefact | commits | dernier |
|---|---|---|
| `scripts/python/tests/engine/runner/test_catalog_inject_live.py` | 1 | `ab981298`, 2026-07-25 |
| `data/seed-bc.json` | 1 | `f467e649` |
| `data/symbols/CURRENT` (bascule `rnca9r7q6c`) | 1 | `8db3bd16`, **2026-07-29** |

Le test est né vert le 2026-07-25 et n'a jamais été retouché. Il a basculé à la **mise à jour du
jeu**, quand le gameconfig sur disque a été remplacé — pas à un commit. C'est pourquoi ni `git
log -S` ni un bisect ne désignent quoi que ce soit : le fichier qui a changé n'est pas versionné.

## 3. Attribution — pourquoi c'est la capture qui est en arrière

Lue dans les **deux tables d'enum versionnées** (`data/symbols/<build>/frida/enums.tsv`) :

| | `gqfc5mff6c` | `rnca9r7q6c` |
|---|---|---|
| `TriggeredAbilityType` | 468 membres | 477 |
| `MyWillBeDoneOverlord` | **absent** | **1556** |
| `MartialApotheosis` | 1045 | 1045 |
| `UnitTrait.Resilient` | 1009 | 1009 |

Le gameconfig de `gqfc5mff6c` **ne pouvait pas** attribuer une ability absente de son propre enum :
c'est donc la capture qui date d'avant. `Resilient` existe dans les deux enums ⇒ le trait gagné est
un pur changement de gameconfig, même migration. Le gameconfig **vivant** confirme le sens :
`necroOverlord.passiveAbilities = ['MyWillBeDoneOverlord']`, `Resilient` dans ses traits, et
**0 porteur** de `MartialApotheosis` sur les 669 unités (sa config d'ability, elle, existe encore).

## 4. La seconde moitié du même test ne pouvait PAS rougir

L'ancien test lisait le seed par `rl_collect_batch._load_seed_bc`, **qui vient d'appeler
`refresh_ability_configs`**. Il comparait donc `synthesize_ability(x)` à une valeur que le
rattrapage venait d'écrire *depuis* `synthesize_ability(x)`. Mesure (étape 3 du probe) :

| oracle | dérives `validate_abilities` |
|---|---|
| capture **BRUTE** | **4** (`ResurrectionOrb` ×2, `FearOfTheUnseen`, `ShockAssault`) |
| seed **RECHARGÉ** | **0** |

`assert not adiffs` sur le seed rechargé était une **tautologie**. Le même chargement laisse
`BC.Units` intact — d'où un fichier dont une moitié rougissait à tort et l'autre verdissait à vide.

## 5. Pourquoi personne ne l'a vu pendant quatre jours

Le test était **100 % offline** mais logeait dans un fichier `_live.py` — donc **hors du périmètre
de `probe_457`** (`not name.endswith("_live.py")`), le seul cliquet qui voie un test offline rouge
en permanence. S'y ajoutent les deux autres facteurs de #457 : la suite complète est proscrite, et
ce fichier n'était la tranche de personne.

## 6. Ce que la péremption fait EN BATAILLE — re-mesuré live le 2026-08-02

Voie de production, `rl_duel build --seed 777 --board MC1_67 --p-units necroOverlord,necroWarden
--a-units ultraTitus` (runner 738, disposé) :

| canal | mesure live | gameconfig vivant |
|---|---|---|
| `unitAbilityStates`, hiérarchie triggered de l'entité 79 | **`1045`** (+ `1010`) | `MyWillBeDoneOverlord` = `1556` |
| `combatSnapshot.units[].traits` | `[Mechanical, Hero, LivingMetal, Xenos]` | + **`Resilient`** (1009) |

Le runner déploie donc le kit de `gqfc5mff6c`, et le rapport de chargement le dit désormais avant
même le build. (L'identité de l'entité est établie par son active `1009`, celle que la capture porte.)
Ce n'est pas une citation de `case-392` : c'est la même mesure rejouée sur le build courant.

## 7. Ce qui est livré

* **`test_catalog_inject_offline.py`** (fichier neuf, non-`_live` ⇒ entre au cliquet `probe_457`
  tout seul). Cinq gardes, toutes confrontées à la capture **BRUTE** : fidélité stricte hors épingle ;
  épingle gardée **dans les deux sens** ; attribution inter-build ; **asymétrie** des trois
  catalogues ; et le rattrapage #254 gardé par l'**égalité de deux ensembles calculés
  indépendamment** (la dérive mesurée d'un côté, ce que `refresh_ability_configs` déclare réparer de
  l'autre) — c'est ce qui remplace la tautologie.
* **`catalog_inject.STALE_UNIT_ENTRIES` / `stale_unit_entries()` / `stale_unit_report()`** : la
  péremption devient un objet mesurable, avec sa liste épinglée.
* **`_load_seed_bc` le DIT** à chaque chargement, à côté des deux catalogues qu'il rattrape :
  `[seed-bc] bloc Units NON rattrape (#254-bc) : 1 entree(s) perimee(s) ... necroOverlord{...}`.
  Coût mesuré : 2,6 ms. Une entrée hors épingle est marquée `INATTENDUE`.
* **`catalog_inject.py --validate`** sépare les deux verdicts : `rc=1` sur une **infidélité**,
  `rc=0` sur une péremption épinglée ou une dérive de config **rattrapée au chargement**. Il rendait
  `rc=1` depuis le 2026-07-29, pour la même confusion.

**Ce qui n'est PAS fait, et c'est délibéré : le bloc `Units` n'est toujours pas rafraîchi.** Un
re-dump change le pool spawnable et les stats de référence de tous les tests live, retire
`MartialApotheosis` du montage (`test_martial_apotheosis_live.py` rougira sur sa garde T0, qui dit
quoi faire) et rend `MyWillBeDoneOverlord` dispatchable (#392-r1). C'est un **arbitrage**, pas un
geste de passage. La ligne #254-bc du backlog reste ouverte ; ce qui change, c'est qu'elle n'est
plus **muette**.

## 8. Contre-épreuves (étape 4 du probe) — 8 mutations, 8 rouges

| mutation | garde qui doit rougir |
|---|---|
| épingle **vide** | fidélité / épingle / asymétrie (rapport `INATTENDUE`) |
| épingle **orpheline** (`ultraTitus`) | épingle |
| `_traits` amputé d'un trait | fidélité |
| attribution visant le build **courant** | attribution |
| `refresh_ability_configs` rendu **inerte** | abilities |
| capture corrigée d'un seul côté | asymétrie |

La mutation « attribution visant le build courant » a d'abord rendu **vert** : le repli
« archive absente → on le dit et on sort » rendait la branche infalsifiable. Remplacé par une
assertion — les builds archivés sont conservés exprès, leur diff *est* le rapport de changement du
jeu. C'est la quatrième victime du patron #516, trouvée dans mon propre correctif.

Discriminance des autres tests du fichier live, vérifiée : `test_controle_entree_synthetisee_
indiscernable` compare deux BC qui diffèrent sur **12 champs** (placeholders recalculés par
`buildNormalizedBC`) et rougit sous mutation (`ActiveAbilities` vidée → `1 failed`), le rapport de
chargement nommant au passage `genesBiophagus{ActiveAbilities} INATTENDUE`.

## 9. Trouvé en marge — `probe_431` balaie moins de la moitié de ce qu'il déclare (`#431-r1`)

Le cliquet a rougi sur mon propre littéral `"gqfc5mff6c"` — à raison, et le foyer sanctionné
existait : `build_pin.archived_build(name, what)`, qui **lève** si l'archive a disparu. Les deux
sites y sont passés (il rend `0 RESOLUTION`), et l'assertion « le build de référence n'est pas le
build courant » reste à côté — sans elle, la mutation M4 redevenait verte.

Mais il n'avait vu **qu'un** des deux littéraux ajoutés le même jour. Cause :
`is_exec` teste `Path(rel).match("scripts/**/*.py")`, et `PurePath.match` ne traite pas `**`
récursivement — un seul niveau intermédiaire. **904 fichiers balayés sur 1 814** `.py` versionnés
sous `scripts/`, **910 invisibles**, dont **tout `engine/**`**. Avec un périmètre récursif :
1 872 fichiers, **17 RESOLUTIONs**, toutes dans `tests/**` et toutes synthétiques (hashes bidon des
tests de `build_pin`, chemin écrit dans un tmpdir) — **0 dans `engine/**`**. Le trou ne cache donc
aucun défaut vivant, mais le fermer demande une règle pour le hash synthétique de test, axe que
#431 n'a pas tranché. **Non corrigé ici** (hors périmètre) → backlog `#431-r1`.

## 10. Résidus

* **`#254-bc`** — le re-dump lui-même, inchangé, toujours `[opus]`+arbitrage.
* **`#392-r1`** — `MyWillBeDoneOverlord` reste inerte dans tout runner bâti sur ce seed ; se ferme
  avec le re-dump.
* **`#254-bc-r1`** — l'épingle couvre l'axe `Units` **capturé**. Une unité que le gameconfig a
  ajoutée depuis la capture n'y est pas du tout : elle relève de `missing_from_seed_bc`, qui ne
  compare rien — aucun garde ne dit si le catalogue a *perdu* des entrées face au gameconfig vivant.
* **`#431-r1`** — §8, le périmètre de `probe_431` (non corrigé, hors périmètre).
