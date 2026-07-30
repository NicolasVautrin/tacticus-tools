# case-282 — `PERTES_CONNUES` vide : quatre rouges qui accusaient le MONTAGE, pas le code

Quatre tests de `scripts/python/tests/test_symbols_coverage_guard_offline.py` échouaient sur
`master` (mesure du 2026-07-30 sur `3cd9e63d` : **4 failed, 12 passed**), tous sur la même ligne
et la même exception :

```
(fam, _, _), _ = next(iter(S.PERTES_CONNUES.items()))
E  StopIteration
```

Une seule cause, quatre symptômes : `symbols_sync.PERTES_CONNUES` est **vide**. La question posée
était binaire — **perte ACCIDENTELLE** du registre (à restaurer) ou **état NOMINAL** (les tests
doivent cesser d'en dépendre) ? Réponse mesurée : **état nominal**. Le zéro est le bon état, et
les quatre rouges accusaient le **montage** des tests.

Re-dérivation complète : `python scripts/python/probe_282_registre_pertes.py`.

## 1. Datation — la cause soupçonnée est réfutée par les dates

L'hypothèse d'ouverture était « vidé par la migration de build `gqfc5mff6c → rnca9r7q6c` (#251)
ou par la re-symbolisation gshared (#259/#261) ». **Deux des trois sont impossibles**, et pour une
raison plus forte qu'un simple ordre : le symbole `PERTES_CONNUES` **n'existait pas encore** quand
elles ont été livrées.

Historique du littéral, commit par commit (étape 1 du probe — le compte d'entrées est relu dans le
**texte** de chaque version, pas déduit d'un message) :

| commit | date (2026-07-29) | état de `PERTES_CONNUES` | sujet |
|---|---|---|---|
| `7d630853` | 18:12 | **absent** | #255 axe 4 de la garde |
| `bbe817ad` | **20:33** | **1 entrée** — création, avec `("GSHARED","gqfc5mff6c","rnca9r7q6c")` | #259 axe 5, + les 16 tests |
| `7922c27b` | 20:36 | 1 entrée | #259 correctif de référence |
| `5c72a488` | **22:26** | **VIDE** | **#259-a la couverture gshared est RÉTABLIE — 0 → 4874** |

Confrontation aux causes soupçonnées :

| cause | dernier commit | verdict |
|---|---|---|
| **#251** (migration de build) | `e78acb74`, 17:54 | **lien impossible** — antérieur de 2 h 39 à la naissance du registre |
| **#261** | `e217d1b3`, 18:46 | **lien impossible** — antérieur de 1 h 47 à la naissance du registre |
| **#259** | `9b9be360`, 23:31 | postérieur au vidage — mais c'est bien la **famille** #259 qui a vidé, par `5c72a488` (#259-a) |

Le registre a donc vécu **1 h 53** : créé plein à 20:33 avec les tests qui s'en servaient de
fixture, vidé à 22:26 par un commit qui **n'a pas touché aux tests**.

## 2. Ce n'est pas non plus l'auto-péremption — et la mesure le dit sans lire un seul commit

Le 4ᵉ test s'appelle « le registre s'auto-périme quand la famille est à zéro **des deux côtés** »,
ce qui rendait plausible l'idée que l'état actuel soit ce mécanisme. **Il ne l'est pas.**
L'auto-péremption s'exerce quand l'archive de référence est elle-même dépourvue de la famille
(`0 → 0`, sous le plancher, plus aucune ligne). Or la famille n'a jamais été à zéro côté
référence :

```
reference gqfc5mff6c   GSHARED =   4882
courant   rnca9r7q6c   GSHARED =   4874
ratio = 0.998   (seuil de la garde : 0.60)
```

Le retrait a été **manuel et délibéré** : `GhidraApplyIl2CppDumperNames.java` a reposé 5 899 noms,
la famille est remontée de 0 à 4 874, **l'excuse n'avait plus d'objet**. C'est la doctrine écrite en
tête du registre : *une excuse qui survit à son motif est pire qu'une absence de garde* — retirer
l'entrée **fait partie de la réparation**.

Ce point est vérifiable **indépendamment de tout message de commit** : les deux tables sont
versionnées (`data/symbols/<build>/ghidra/functions.tsv`), et le compte se re-dérive. L'axe 5
rend aujourd'hui `OK couverture par famille vs gqfc5mff6c : 28 familles suivies, aucune chute
inattendue` — **sans excuse**.

## 3. Le vrai défaut : une fixture prélevée sur une donnée d'EXPLOITATION

`PERTES_CONNUES` n'est pas un contrat, c'est un **registre d'exploitation dont l'état nominal est
vide** — par construction, puisque chaque entrée doit disparaître dès que sa cause est réparée. Les
quatre tests y prélevaient leur fixture par `next(iter(...))`, ce qui **couplait la garde du
mécanisme à la présence d'une panne ouverte** :

* registre plein (panne en cours) → les 4 tests passent ;
* registre vide (**état sain**) → les 4 tests **explosent en `StopIteration`**.

Autrement dit, **réparer la panne cassait les tests**. Et la dégradation est doublement mauvaise :
`StopIteration` n'accuse rien de lisible (pas d'assertion parlante, pas de mention du registre dans
le message), et le rouge subsistant invite le lecteur suivant à « restaurer » une entrée dont le
retrait était exactement la bonne action. C'est le motif déjà consigné dans
[`case-254bis`](case-254bis-trois-rouges-de-montage.md) : *le rouge accuse le montage*.

Second défaut, plus discret : `next(iter(...))` ne confronte **qu'une seule** entrée même si le
registre en contient cinq — la couverture y était silencieusement partielle.

## 4. La correction — le montage, jamais l'assertion

**Aucune assertion des quatre tests n'a été affaiblie ni supprimée.** Seule leur **source de
fixture** change : une entrée **synthétique** injectée par `monkeypatch.setitem` dans le registre
réel, et retirée à la sortie.

| test | ce qui change | ce qui ne change pas |
|---|---|---|
| `test_la_perte_connue_est_taue_MAIS_imprimee` | fixture ← entrée synthétique | les 2 assertions (ligne `PERTE CONNUE` + motif imprimé) |
| `test_la_perte_connue_ne_couvre_QUE_sa_transition` | idem | `pytest.raises(Desync)` sur l'autre transition |
| `test_la_perte_connue_ne_couvre_pas_une_autre_famille` | idem | `pytest.raises(Desync)` sur l'autre famille |
| `test_le_registre_s_auto_perime_...` | idem + note : ce filet **n'est pas** ce qui a vidé le registre | `0 → 0` ne produit aucune ligne |

Deux tests **ajoutés**, pour que le trou ne se rouvre pas :

* `test_toute_entree_du_registre_a_la_FORME_que_le_mecanisme_sait_lire` — applique le **même**
  contrôle à l'entrée synthétique (donc **jamais vacuous**, registre vide compris) et à chaque
  entrée réelle. Il exige un triplet `(famille, ref, courant)` — une clé à deux membres produit une
  entrée **inerte** que rien ne signalait — et un motif portant un **numéro de tâche** et un
  **renvoi `.md`** : une excuse sans renvoi est une excuse qu'on ne saura pas retirer.
* `test_un_registre_VIDE_est_l_etat_NOMINAL_et_ne_desamorce_pas_la_garde` — vide ≠ garde éteinte :
  une chute effondrée sur une transition absente du registre doit **toujours** lever.

Une note est posée en tête de `PERTES_CONNUES` (`symbols_sync.py`) : **remplir ou vider ce dict ne
fait plus rougir aucun test**, et une entrée neuve porte son numéro de tâche et son renvoi.

## 5. Validation adversariale — les mutations qui DOIVENT rougir

Chaque test a été confronté à la mutation qui l'invalide (le code muté, la suite rejouée, le
fichier restauré à l'identique et vérifié) :

| mutation appliquée à `symbols_sync.py` | attendu | mesuré |
|---|---|---|
| aucune (baseline) | 18 passed | **18 passed** |
| une entrée **réelle** bien formée revient au registre | 18 passed (la suite ne dépend plus du contenu) | **18 passed** |
| entrée réelle au motif sans `#` ni `.md` | forme refusée | **1 failed** — `..._a_la_FORME_...` |
| entrée réelle à clé de **2** membres (inerte) | forme refusée | **1 failed** — `..._a_la_FORME_...` |
| `motif = None` (le registre n'est plus consulté) | la perte connue n'est plus tue | **1 failed** — `..._est_taue_MAIS_imprimee` |
| le motif n'est plus **imprimé** (tue au lieu de consigner) | idem | **1 failed** — `..._est_taue_MAIS_imprimee` |
| clé sur la **famille seule** (silencieux permanent) | la transition ne borne plus l'excuse | **1 failed** — `..._ne_couvre_QUE_sa_transition` |
| clé sur la **transition seule** | la famille ne borne plus l'excuse | **1 failed** — `..._ne_couvre_pas_une_autre_famille` |
| `SEUIL_COUVERTURE = 0.0` (garde désamorcée) | plus rien ne lève | **6 failed**, dont `..._VIDE_est_l_etat_NOMINAL_...` |
| `PLANCHER_FAMILLE = 0` | le plancher ne protège plus | **2 failed**, dont `..._s_auto_perime_...` |

Contrôle de fuite : après un run complet de la suite, un process neuf relit
`symbols_sync.PERTES_CONNUES` → **`{}`**. La fixture ne survit pas au test qui l'utilise, aucun test
ne peut en désamorcer un autre.

## 6. Ce qui n'est PAS couvert

* **Le contenu du registre n'est plus gardé par aucun test, et c'est délibéré** : il n'existe aucune
  assertion « le registre doit contenir X » ni « le registre doit être vide ». Ce serait recréer le
  couplage qu'on retire — le contenu est piloté par l'état réel de la chaîne de symboles, pas par la
  suite de tests. Ce qui reste gardé : la **forme** de toute entrée et le **mécanisme** qui la lit.
* **La réparation elle-même (#259-a) n'est pas re-vérifiée ici** : ce cas mesure que la famille
  GSHARED est à 4 874 dans la table versionnée, pas que les 5 899 noms reposés sont les bons. Cette
  vérification-là appartient à `probe_259_gshared_coverage.py` et à
  [`case-259`](case-259-couverture-gshared.md).
* **Aucune confrontation live** : le périmètre est offline pur (tables versionnées + historique
  git). Aucune session Frida, aucun runner, aucune (re)injection.
* **Les quatre autres axes de `symbols_sync.py` ne sont pas touchés** — ni leur code, ni leurs
  tests. Le seul fichier de production modifié l'est en **commentaire** uniquement.
