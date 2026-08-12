# #951-r2 — les audits de couverture comptaient MANQUANT ce qui est PORTÉ

Deux mécanismes distincts, un seul symptôme : **un agent dispatché sur du travail déjà fait**. Ce
n'est pas un défaut cosmétique du doc — c'est la source depuis laquelle chaque lot est composé.

| mécanisme | ce qui manque à l'audit | cas mesurés |
|---|---|---|
| une **voie de port** qu'il ne lit pas | un registre à lire — ou, pour un appel impératif, **aucun registre n'existe** | `FireOfAbsolution`, `DawnBlade` |
| un **verdict établi** que rien ne mémorise | le natif n'a rien de propre à porter, et c'est écrit dans une case-doc que l'outil ne lit pas | `LeadingTheCharge`, `GalvanicField`, `IndirectFire` |

## 1. L'ampleur — 6 faux manquants sur 130, et le recensement n'a énuméré AUCUNE liste blanche

`probe_951r2_faux_manquants.py`. La question « combien ? » décide de tout : à 2 on ferme deux cas
nommés, à 40 la sélection de lots est structurellement fausse. **La réponse est 6.**

⚠ **La méthode est le point important, pas le chiffre.** Un recenseur qui interroge les registres
qu'il connaît ne peut pas voir la voie qu'il a oubliée — c'est #323 (`unit_map find --ability`
lisait 2 voies d'attribution sur 5 et rendait des zéros qui ont fait classer du vivant en DEAD),
transposé de l'axe ATTRIBUTION à l'axe PORT. Le probe part donc de la **POPULATION** (les 130 items
`nom × catégorie` que les deux audits comptent non portés) et découvre les voies **par leur FORME** :

* import de **tous** les modules `engine.**` (546 importés, 0 échec) ;
* visite de **tout** attribut de module qui est un conteneur (268 conteneurs), aplati
  récursivement — donc tout registre, connu ou non ;
* plus les **symboles définis** dont le nom contient le nom de l'item en snake_case : c'est la voie
  IMPÉRATIVE, qui par construction n'a aucun registre.

Les mirrors d'enum sont exclus (`active_ability_type`, `effect_type`, …) : tout nom d'ability y
figure par construction, les compter rendait **130 candidats sur 130**, soit zéro discrimination.

| population | items | faux manquants |
|---|---:|---:|
| `active-decision` | 55 | **1** |
| `passif` | 22 | **2** |
| `conditionnelle-item` | 23 | **1** |
| `conditionnelle-mythic` | 11 | 0 |
| `combat-no-op` (`combat-ability-coverage.md`) | 16 | **0** |
| `trait` | 2 | **1** (+1 non tranché) |
| `active-combat` | 1 | 0 |

**`combat-ability-coverage.md` rend 0 faux manquant, et c'est structurel** : `ABILITY_CLASSES` est
la seule porte d'exécution d'une active (`AbilityHandler.visit_ActiveAbilityMessage` fait un no-op
silencieux pour toute absente), donc il n'existe pas de « voie alternative » à lui opposer. Les
traces trouvées sur ces 16 sont toutes des registres de **DÉCISION** — face décision portée, face
combat non : l'audit a raison.

### Le contrôle qui a évité de sur-compter

Sur la face DÉCISION, la tentation était de décompter tout ce qui n'a pas de playbook natif. Croisé
avec `data/symbols/<build>/metadata/active_playbook_builders.tsv` (le dict `active` de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`, 233 entrées) : **55/55 des faces
comptées manquantes ONT un playbook dédié**. Aucune n'est décomptable par absence — le seul faux
manquant est celui dont le décompilé a été LU (1204), et cela ne se dérive pas, cela s'atteste.

⚠ Et l'inverse est vrai aussi : **la présence dans cette table ne prouve pas un contenu propre**.
IL2CPP réplique le corps de `DefaultActiveAbilityPlaybook` dans chaque spécialisation — compter les
symboles ne dit pas ce qui est surchargé (#945 §7).

## 2. La réparation — deux voies LUES, trois verdicts MÉMORISÉS

### 2.1 Les voies (le mécanisme 1)

* **`IMPERATIVE_ABILITY_VECTORS`** — déclaré à son foyer, `dispatch/ability.py`, parce que c'est là
  qu'il vit. Clé = nom gameconfig du passif, valeur = le callable réellement appelé.
  `FireOfAbsolution` est joué par un **appel en dur** depuis `evaluate_abilities_for_event` : il n'a
  aucune entrée de registre à lire, **quel que soit l'état du port**. La déclaration est le seul
  moyen de rendre cette voie lisible.
* **`RELIC_ABILITY_TRIGGERS`** — un registre qui **existait déjà** et n'était pas lu. Il est séparé
  d'`ABILITY_TRIGGERS` à dessein (montage natif distinct : `TertiaryAbility` / `relicAbilities`), et
  c'est cette séparation même qui le rendait invisible à `_passive_covered`.

⚠ **La double déclaration n'est pas une redondance bénigne, ici : c'est un DOUBLE FIRE.** Inscrire
un nom à la fois dans `IMPERATIVE_ABILITY_VECTORS` et dans un registre de trigger le ferait jouer
deux fois par attaque — exactement ce que le paramètre `fire_of_absolution=False` existe pour
empêcher sur la voie normale. Le test garde la disjonction contre les quatre autres registres.

⚠ **Une déclaration MORTE serait pire que l'absence** : elle atteste une couverture que rien ne
porte. Le contrôle est **structurel** (AST du module qui déclare), pas un grep : le callable doit
apparaître en position d'APPEL dans le fichier même où le registre vit.

### 2.2 Les verdicts (le mécanisme 2)

`scripts/ratchets-951r2-couverture-attestee.json`, foyer unique de validité
`coverage_attestations.py::validite`. Le motif est celui de `ratchets-462`/#465, **avec une
asymétrie INVERSE, et c'est structurel** :

> chez #465 le verdict permissif est `VERT` et il ne périme jamais (un vert périmé est
> CONSERVATEUR). **Ici l'attestation EST le geste permissif** — elle RETIRE du travail du compte.
> Donc une attestation **PÉRIMÉE REMET son item au compte des manquants**.

**Aucun chemin ne peut faire disparaître du travail : la péremption ne sait que EN RAJOUTER.** Un
audit qui sous-compte fait RENONCER, ce qui est pire qu'un audit qui sur-compte et fait perdre du
temps — le sens de la dégradation est choisi, pas subi.

Trois clauses de validité, plus l'exigence d'une raison écrite et d'une source qui existe :

1. **`build`** — le verdict a été lu sur un décompilé ; un build différent (ou non lisible) périme.
2. **`cliquet`** — le fichier de test qui garde le verdict doit exister.
3. **`porteur`** — `module:symbole` du code qui porte réellement le mécanisme, **résolvable**.

Une entrée sans ancrage (`cliquet` ou `porteur`) est refusée : ce serait une liste blanche déguisée.
La formule est **inverse d'une sélection de cas de péremption** (une catégorie oubliée redeviendrait
permissive) : on exige les conditions du **seul cas permissif**, tout le reste périme — y compris
une entrée malformée, un verdict inconnu, une catégorie inconnue.

| item | verdict | pourquoi | ancrage |
|---|---|---|---|
| `1204 LeadingTheCharge` (décision) | `RIEN_A_PORTER` | `MakeDamagePredictions` structurellement identique au générique (#945 §7) | `test_945_…` + `_A_VIA_STAFF_OF_STARS_GET_DAMAGE` |
| `GalvanicField` (passif) | `RIEN_A_PORTER` | 3 feuilles branchées, playbook à `Fix64(0)` sur les deux faces (#952 §3) | `test_952_…` + `galvanic_field_attack_behavior` |
| `IndirectFire` (trait) | `PORTE_HORS_REGISTRE` | lu impérativement aux DEUX volets natifs — élévation (`targeting_query`) et Trench (`damage_modifiers`) | `targeting_query:INDIRECT_FIRE_TRAIT` |

## 3. Effet mesuré

| chiffre | avant | après |
|---|---:|---:|
| items manquants (total `kit-coverage.md`) | 25 | **22** |
| kits lineup COMPLETS | 102 | **105** |
| conditionnelles non portées (hors total) | 34 | **33** |
| faces DÉCISION non portées (hors total) | 55 | **54** |
| `combat-ability-coverage.md` NO-OP | 16 | **16** (inchangé, et c'est le résultat) |

Les faces DÉCISION « dans des kits COMPLETS » restent à **42** : `LeadingTheCharge` en sort, et
`BasiliskBarrage` y entre parce qu'`astraOrdnance` bascule de « avec travail » à « complet ». Le
chiffre est stable par coïncidence, pas par inertie.

**Réparé au passage** : les trois premières lignes de `combat-ability-coverage.md` sur `master`
étaient le **stdout du script** (`ecrit -> …`, `actives=175 …`) et son titre était tronqué
(`nfig.activeAbilities…`) — une redirection de sortie avait écrasé l'en-tête. La régénération le
répare ; le corps du document était intact.

## 4. Contre-épreuves — dans les DEUX sens

L'axe dangereux est le sous-comptage. Trois mutations jouées **pour de vrai** (port retiré, audit
relancé, puis restauration) :

| mutation | effet mesuré | mord ? |
|---|---|---|
| **M1** — entrée retirée d'`IMPERATIVE_ABILITY_VECTORS` | items **22 → 23**, `_passive_covered("FireOfAbsolution")` → `False` | oui |
| **M2** — déclaration gardée, **appel supprimé** | audit **inchangé à 22**, `test_…_REELLEMENT_appele_dans_son_module` **ROUGE** | oui — et **seul le test AST le voit** |
| **M3** — `DawnBlade` retirée de `RELIC_ABILITY_TRIGGERS` | conditionnelles **33 → 34**, portées **10 → 9**, test nommé ROUGE | oui |

**M2 est la mutation qui justifie le dispositif** : sans le contrôle AST, une déclaration devenue
morte ferait sous-compter en silence — le registre continuerait d'affirmer une couverture que plus
rien ne porte.

S'y ajoutent, dans le cliquet : 9 mutations du ledger (une par clause de validité) qui doivent
toutes PÉRIMER, la contre-épreuve de bout en bout « une attestation périmée REMET l'item au compte »
jouée sur le vrai `collect()`, 4 passifs réellement non portés qui doivent **rester** comptés
manquants, un contrôle négatif sur un nom inexistant, et un plancher sur le total.

## 5. Ce qui n'est PAS couvert, avec la raison MESURÉE

* **`Vehicle` (trait, 8 porteurs) — faux manquant PROBABLE, délibérément NON attesté.**
  `port-roadmap.md` §5.1 le déclare « CLOS » (target-trait déjà consommé par `BeastSlayer` /
  `non_owner` / `static_battle_rules` ; exemption de mouvement = « la porter = registered-but-dead »,
  `case-205` §3). Mais ce verdict n'a **ni case-doc de RE dédiée ni cliquet**, et son seul ancrage
  possible (`_BEAST_SLAYER_TARGET_TRAITS`) désigne un consommateur qui n'est **pas** le mécanisme du
  trait — l'attester serait mentir sur l'ancrage. Il reste donc compté manquant : **sur-compter est
  le côté sûr**. Résidu **#951-r5**.
* **La section conditionnelle applique un prédicat COMBAT à des items qui n'ont qu'une face
  DÉCISION.** `Lakrimae` (relique de `deathTyphus`) a sa face décision portée
  (`engine/playbook/lakrimae.py`, face MOVE lue et constante) ; `covered` ne le dit pas, faute de
  ventiler les deux faces comme le fait la section kit. Résidu **#951-r6**.
* **Les 3 marqueurs de verdict du balayage de docs ne sont pas un oracle** : `SternguardFocus`
  (#905, verdict sur `SetsEndTurnFlags`), `ExemplarOfTheKauyon` (#942, cité comme voisin) et
  `EmpyricAmbush` (#589, verdict sur la triggered satellite `_AnyMove`) sont des **faux positifs de
  proximité**, tranchés à la lecture. Le probe TRIE, il ne conclut pas — et c'est écrit dans sa
  docstring.
* **Aucune confrontation LIVE**, et elle n'aurait rien à dire : la tranche ne touche à aucun
  comportement de moteur. Le seul fichier `engine/**` édité ne reçoit qu'une **déclaration**
  (`IMPERATIVE_ABILITY_VECTORS`) — aucun appel, aucun ordre, aucun tirage RNG ne change. Les trois
  mutations ci-dessus l'établissent par construction : M2 montre que retirer l'appel ne change
  **rien** au compte de l'audit, donc que le registre est inerte pour l'exécution.
* **Le ledger ne couvre que ce qui a été LU.** Il n'y a aucun balayage automatique des case-docs
  vers des attestations : chaque entrée est posée par la tranche qui a établi le verdict. C'est
  délibéré — un marqueur textuel n'est pas un verdict (cf. les 3 faux positifs ci-dessus).
