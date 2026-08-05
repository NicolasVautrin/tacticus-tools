# #270-r4-r2-r2 — trier les imports différés restants d'`engine/`

**Livré le 2026-08-05.** Instruments : `probe_270r4r2r2_tri_differes.py` (ventilation par cause
MESURÉE), `migrate_270r4r2r2_hisser_differes.py` (hissage sous 8 gardes).
Cliquet : `tests/engine/test_270r4r2r2_differes_offline.py`.

#270-r4-r2 avait coupé les deux SCC et laissé les 971 différés **non triés**. Le tri est fait,
et il se lit site par site.

## 1. Ce qui a bougé

| | avant (`3a84b97e`) | après |
|---|---|---|
| instructions d'import différées vers `engine/` | **971** / 194 fichiers | **346** / 126 |
| dont INCONDITIONNELLES (hors `TYPE_CHECKING`, hors `if`/`try`) | 844 | **219** |
| différés **GRATUITS** (cible déjà chargée par le préambule) | **150** | **0** |
| arêtes module-level | 2338 | 2669 |
| SCC > 1 (module-level) | 0 | **0** |
| modules qui s'importent EN PREMIER | 409/409 | **409/409** |

**625 hissages** — 624 par le migrateur (623 + 1 à la seconde passe), 1 à la main.

## 2. La partition, DÉRIVÉE et mesurée (état d'entrée, 971)

La cause n'est pas devinée : chaque instruction est **hissée pour de vrai** puis importée dans un
interpréteur frais, depuis **le module porteur ET chaque cible** en premier (un cycle ne se voit
que dans un sens). Témoin **242/242 verts** sans hissage, avant toute mesure.

| catégorie | n | ce que ça veut dire |
|---|---|---|
| `hissable` | **766** | hissée en TÊTE, l'import reste vert |
| `conditionnel` | **84** | sous `if` (80), `try` (3), `for` (1) **dans** la fonction — hisser change la SÉMANTIQUE. Écarté, et dit. |
| `brise-cycle` | **61** | ni la tête ni la fin de fichier ne passent |
| `TYPE_CHECKING` | **43** | jamais exécuté |
| `placement` | **17** | la TÊTE rougit, la FIN DE FICHIER passe |

Le hissage est **simulé sans écrire aucun fichier** : un `MetaPathFinder` intercepte le module
porteur et `exec`-ute le **segment source exact** dans son namespace, avant son corps. C'est ce
qui permet de mesurer `from .x import Y` **avec** sa résolution de symbole — un `import_module`
seul ne lèverait jamais `cannot import name`.

## 3. Le graphe des sources déclarées dit VERT sur une régression qui casse 405 modules

C'est la mesure de la tranche, et elle est **dirimante**. Le premier lot appliqué — 732 hissages,
filtrés sur l'acyclicité du graphe **déclaré** — a rendu :

- `probe_270r4r2_cycles_imports` : **0 SCC**, 2748 arêtes → **VERT** ;
- `probe_270r4r2_import_en_premier --tous` : **405 des 409** modules ne s'importent plus.

La boucle passe par un paquet **ANCÊTRE**, que Python exécute qu'on l'écrive ou non :

```
engine.battle_query -> engine.entities.effects.aura      (hissé)
                    -> [PARENT] engine.entities (init) -> ... -> engine.entities.triggers
                    -> engine.battle_query                (hissé)   <- casse
```

Aucune de ces deux arêtes n'est un cycle **seule**, et chacune passait sa mesure individuelle.
C'est leur **somme** qui ferme la boucle : une mesure par site ne peut structurellement pas la
voir. Le filtre du migrateur porte donc l'arête `module -> paquet parent`, et le glouton est
**déterministe** (module, ligne) pour que deux exécutions rendent le même lot. Effet : 738
retenus → **627**, et 409/409.

**Ce n'est pas une anecdote de mise au point : c'est REPRODUCTIBLE**, et ça sera re-tenté — filtrer
sur l'acyclicité du graphe déclaré est l'idée la plus naturelle qui soit. La recette, depuis la base
de la tranche :

```powershell
git checkout <base> -- scripts/python/engine
python migrate_270r4r2r2_hisser_differes.py --tri tri.json --sans-ancetres --ecrire
python probe_270r4r2_cycles_imports.py        # 0 SCC, 2748 aretes   -> VERT
python probe_270r4r2_import_en_premier.py --tous   # 405/409 CASSES  -> la verite
git checkout HEAD -- scripts/python/engine    # restaurer
```

**Le fait à retenir** : sur ce lot, `0 SCC` et `405/409 modules cassés` sont **simultanément vrais**.
Un cliquet qui ne regarde que le graphe des sources déclarées est structurellement incapable de voir
cette régression-là.

## 4. Les huit gardes du hissage, et pourquoi trois ont d'abord rendu des refus FAUX

Un hissage n'est pas un déplacement de ligne : il fait passer un nom du scope LOCAL au scope
MODULE. Chaque garde refuse plutôt que de risquer un changement silencieux, et **chaque refus
s'imprime** (la partition `hissés + refus == candidats` est vérifiée à chaque exécution).

Trois gardes ont rendu **151 refus, tous faux**, avant correction — et c'est la partition qui les
a fait voir :

- **`conflit-de-nom` (67 faux)** — comparait les **SEGMENTS**. `from X import a, b` et
  `from X import b` ont des textes différents et la **même source** pour `b`. L'identité d'une
  liaison est `(source, nom d'origine)`, jamais le texte écrit.
- **`ligne-partagée` (78 faux)** — un **commentaire de fin de ligne** n'est pas une instruction
  partagée. Le critère se lit à `end_col_offset`, pas par comparaison de chaînes.
- **`déjà-au-module` (46 faux)** — quand le préambule produit **exactement** la même liaison,
  l'instruction est un **DOUBLON PUR** : on la supprime, sans rien insérer.

⚠ **`str.splitlines()` ne découpe PAS comme le compilateur Python.** Il coupe aussi sur `\x0c`
(form feed), `\x85`, ` `... **Sept** fichiers d'`engine/` portent un form feed ; avec
`splitlines()` la numérotation AST décale d'une ligne et on supprime la **mauvaise** — mesuré, 3
fichiers rendus syntaxiquement invalides. C'est `split("\n")`, toujours.

## 5. Le seul cas traité à la main, et ce qu'il apprend

`engine/playbook/shrapnel.py` liait `_entity_traits` depuis **deux** sources (`.prediction._shared`
et `.prediction`) : conflit **nominal**, pas réel — `playbook/prediction/__init__.py` **réexporte**
le symbole, c'est le **même objet**. Le garde ne peut pas le savoir statiquement ; il refuse, et
c'est le bon défaut. La levée se fait en lisant le `__init__.py`, pas en assouplissant la garde.

## 5bis. La résolution de conflit avec `#27-r8` (PR #692), et ce qui la garde

Le rebase sur `50e6d238` a rendu **un seul** conflit de contenu, dans
`engine/playbook/scene.py` : `#27-r8` ajoute `turns_finished_by_id` sur **la ligne même** dont
cette tranche a retiré l'import hissé (`from engine.entities.stats import StatType as _ST`, désormais
au préambule, ligne 34). Résolution : garder `turns_started_by_id, turns_finished_by_id = {}, {}`
**sans** l'import.

Ce qui la **garde**, et ce n'est pas la relecture : l'empreinte rend **0 nom disparu** — un champ,
un accesseur ou une capture effacés par la résolution s'y verraient immédiatement — et
`test_instruments_of_vengeance_decision_live` (le **seul** test qui lit `turns_finished`) passe.

Les trois autres fichiers arrivés depuis ont été re-passés à l'outil, comme il se doit : `scene.py`
**1** différé (non inconditionnel), `nonattack.py` **1** (idem), `streams/input_messages.py` **0**,
`loki_custom.py` **4** dont 2 mesurés `hissable` — **tous deux refusés** par le filtre
(`fermerait-une-boucle`). Aucun différé neuf n'entre donc dans le lot, et le compte total est
**re-dérivé**, jamais recopié.

## 6. Invariant à ZÉRO : le différé GRATUIT

Sa cible est **déjà** importée au niveau module dans le **préambule du même fichier** (avant la
1ʳᵉ `def`/`class` — les imports de PLACEMENT n'y entrent pas, ils ne garantissent rien pour le
corps). Ni cycle possible (l'arête existe déjà), ni coût (le module est déjà chargé) : **aucune**
raison d'être. **150 → 0**.

C'est un **invariant**, pas un seuil : il mord sur **un seul** site. Le seuil (le compte total,
347) est écrit à côté en sachant ce qu'il vaut — il attrape une reprise de MASSE, et il faut le
**baisser** à chaque tranche, sinon il cesse de mordre.

## 7. Le coût d'import : mesuré, et il ne motive aucun différé restant

L'indicateur est le **nombre de modules chargés**, pas le temps : en mesure **appariée** (témoin et
arbre modifié, mêmes conditions machine, min sur 7), le temps varie de **-11 % à +24 % à nombre de
modules IDENTIQUE** — c'est du bruit de machine partagée, et le rapporter serait fabriquer un
résultat.

| entrée | modules `engine` avant | après |
|---|---|---|
| `engine.playbook.scene` | 258 | **356** (+98) |
| `engine.runner.abilities.targeting` | 195 | 212 (+17) |
| `engine.runner.state` | 117 | 118 (+1) |
| `engine.utilities.tile` / `engine.dsl.base` / `engine.entities` | 91 | 91 (**0**) |

Payé **une fois** par processus, là où un différé en fonction chaude coûte un lookup `sys.modules`
**à chaque appel**. Aucun des 347 différés restants n'est justifié par le coût : ils le sont par un
**cycle** (217), par la **sémantique** (84) ou par `TYPE_CHECKING` (43).

## 8. Invariance de comportement

`probe_270r4r2_empreinte_valeurs.py`, contre un arbre témoin extrait par `git archive` **complet**
depuis `origin/master` (`50e6d238`) : **0 divergence de VALEUR sur 197 116 attributs**, **0 nom
disparu**, 8748 noms apparus (l'effet attendu d'un import hissé : le nom devient attribut du module,
et un enum hissé apporte ses ~110 membres).

⚠ **Une empreinte prise contre un ANCÊTRE ne prouve rien de l'arbre fusionné** : celle-ci a été
re-calculée à chaque rebase, contre le `origin/master` du moment. Le **0 nom disparu** est ce qui
garde la résolution de conflit du §5bis — un champ effacé par une résolution maladroite s'y verrait.

## 9. Contre-épreuves

- **du cliquet** — ré-introduire UN différé dont la cible est au préambule
  (`engine/runner/abilities/targeting.py`) : l'invariant passe à **rc 1** en nommant le site ;
  fichier restauré, **rc 0**.
- **du filtre** — `migrate_270r4r2r2_hisser_differes.py --sans-ancetres` sur la base : 732 hissés,
  971 → 239 différés, **0 SCC déclaré**, et **405/409** imports cassés (§3). C'est l'étage 5 du
  cliquet, et lui seul, qui rougit dans ce régime.
- **du détecteur** (dans le cliquet, sur arbre synthétique) : il voit un gratuit évident, et ne le
  déclare PAS quand la cible n'est pas au préambule, quand l'import module-level est en
  **placement** (après une définition), ou quand le différé est **conditionnel**.
  ⚠ Cette contre-épreuve a d'abord **échoué** : le détecteur filtrait en dur sur le préfixe
  `engine`, donc était **intestable** sur un arbre synthétique. Une contre-épreuve qu'on ne peut
  pas écrire est une contre-épreuve qui n'existe pas.

## 10. Ce qui a été rejoué

**Offline** : 6 passed (cliquet neuf, dont l'étage 5 sur les 409 modules), 4 passed (cliquet
#270-r4-r2), 115 passed sur 8 fichiers ciblés (`test_344_ability_damage_average_offline`,
`test_350r3b_triggered_average_forms_offline`, `test_366_effects_registry_partition_offline`,
`test_366_r1_tunneling_horror_pending_summon_offline`, `test_433_r4_r1_filter_tiles_can_attack_offline`,
`test_433_r4_r2_r1_r1_dynamic_target_gate_offline`, `test_433r4r1r4r2r1r1r1_selecteur_spawn_offline`,
`test_443r1a_triggered_move_anchor_offline`).

**Live** : **30 passed** — `test_344_ability_damage_average_live` et
`test_movement_scoring_origin_live`, choisis sur les chemins les plus réécrits
(`runner/damage_model.py`, `runner/operations/movement.py`, `services/movement_query.py`), PLUS
`test_instruments_of_vengeance_decision_live` — le seul test qui lit `turns_finished`, donc celui
qui éprouve la **résolution de conflit** du §5bis.

**Exigence de la tranche** : `probe_477r15a_stream_conformance.py` reste **rc 0** (204/204 et
316/316). `engine/streams/` n'est **pas touché** — 0 fichier au diff.

**Non couvert** : les tests des 141 fichiers réécrits n'ont pas tous été joués. Le filet réel
n'est pas le volume de tests mais l'empreinte du §8, qui porte sur **tout** `engine/`, et les
409/409 imports du §1.

## 11. Un tri se PÉRIME sous l'effet de son PROPRE lot

La ventilation du §2 décrit l'arbre **d'entrée**. Elle ne décrit **pas** l'arbre livré, et la
recopier l'aurait fait croire. Re-mesurée **sur l'arbre livré**, elle bouge franchement :

| catégorie | sur l'arbre d'entrée (971) | sur l'arbre livré (346) |
|---|---|---|
| `hissable` | 766 | **107** (dont **105** que le filtre refuse) |
| `brise-cycle` | 61 | **90** |
| `placement` | 17 | **22** |
| `conditionnel` | 84 | 84 |
| `TYPE_CHECKING` | 43 | 43 |

Un site le montre à lui seul : `engine/playbook/loki_custom.py:124` était `hissable` à l'entrée et
est **`brise-cycle`** à l'arrivée — ce sont les hissages faits **dans `engine.ai.*`** qui ont fermé
sa boucle. Le tri d'un lot est donc valable **pour l'arbre sur lequel il a été pris**, et pour lui
seul.

Conséquence pratique : **il faut re-mesurer après avoir appliqué**, et itérer jusqu'au point fixe.
La re-mesure a rendu **1 hissage de plus** (`playbook/shrapnel.py`, débloqué par la correction
manuelle du §5) ; la mesure suivante en rend **0** — point fixe atteint, et c'est ce qui est livré.

## 12. Ce qui reste — résidu **#270-r4-r2-r2-r1**

Les **346** différés restants se ventilent **exhaustivement** ainsi. Ces chiffres sont mesurés
**sur l'arbre livré**, pas hérités du tri d'entrée (§11) :

| reste | n | pourquoi |
|---|---|---|
| `hissable` mais REFUSÉ par le filtre | **107** | 105 `fermerait-une-boucle` + 2 `conflit-de-nom`. Le refus est une **sur-approximation** : le filtre modélise `module -> parent`, donc il refuse aussi des arêtes qui ne fermeraient rien en pratique. À départager par mesure matérielle itérative (appliquer, mesurer 409/409, désarmer le coupable que la trace NOMME). |
| `brise-cycle` | **90** | ni la tête ni la fin de fichier ne passent. La parade n'est pas le hissage mais la **coupe** (cf. #270-r4-r2-r1 : 41 fichiers lisent 9 symboles d'`engine.entities`). |
| `conditionnel` | **84** | ⚠ **JAMAIS MESURÉS** — leur catégorie est **syntaxique** (sous `if`/`try`/`for` dans la fonction), pas éprouvée : aucun n'a jamais été hissé, même en simulation. Certains sont peut-être des brise-cycles, d'autres de purs gratuits ; **on ne le sait pas**. Ne pas lire cette ligne comme une catégorie triée. Les traiter demande de décider un par un (un `if` de garde n'est pas un `try` d'import optionnel), jamais en masse. |
| `TYPE_CHECKING` | **43** | inoffensifs, jamais exécutés. Rien à faire. |
| `placement` | **22** | **mesurés** hissables en FIN DE FICHIER. Non traités : le placement exact (après la définition consommée) se décide fichier par fichier, et chaque arête rendrait le graphe déclaré cyclique — le cliquet `0 SCC` tomberait. Le trancher demande de décider ce que ce cliquet garde vraiment. |
