# #1041 — le recenseur de couverture d'item : deux vices, en sens OPPOSÉS

`audit_kit_coverage.py` listait `PhoenixGem` parmi les voies conditionnelles **non portées**. Elle
est portée en entier. Question posée : **combien d'autres entrées l'audit déclare-t-il non portées
à tort ?** La mesure a répondu — et elle a trouvé un **second** vice, qui tire dans l'autre sens.

Tous les chiffres ci-dessous sont ancrés sur **`b91d1f18`** et **isolés contre un arbre témoin**
régénéré à ce commit exact (§5). Les re-dériver, ne pas les citer.

## 1. Volet SOUS-comptage — une liste blanche ne montre pas le registre qu'elle a oublié

`_passive_covered` testait cinq registres énumérés à la main. `EFFECT_TRIGGERS` n'y était pas, ni
`CUSTOM_TRIGGERED_ABILITIES`. Deux bascules **mesurées** :

| item | voie qui le porte | clé du registre | audit |
|---|---|---|---|
| `PhoenixGem` (relique, `eldarAutarch`) | `EFFECT_TRIGGERS[EffectType.PhoenixGem_CanRevive]` | `EffectType` | `kit-coverage` |
| `HarlequinsPanoply` (passif, `eldarNpc3Harlequin`) | `CUSTOM_TRIGGERED_ABILITIES` **et** `EFFECT_TRIGGERS` | `TriggeredAbilityType` / `EffectType` | `npc-registry` |

⚠ **`WisdomOfTheAncients` n'est PAS une troisième bascule de ce volet — c'est un piège du volet 2.**
Elle est arrivée en cours de tranche, créditée par `ABILITY_INIT_OWNER_EFFECTS` dont la cible
(`WisdomOfTheAncients_DamageReductionEffect`, 1445) n'a **aucune classe** : elle sort donc
`PARTIEL`. Et l'ordinal `1451` la nomme en `TriggeredAbilityType` — c'est exactement le faux
positif que §4(a) écarte. Deux raisons distinctes de ne pas la compter portée, aucune n'est
« elle est absente ».

⚠ La seconde ligne n'attribue pas sa bascule à `CUSTOM_TRIGGERED_ABILITIES` : `HarlequinsPanoply`
est monté par les **deux** voies, donc `EFFECT_TRIGGERS` suffit à expliquer les deux cas.

Ce n'était pas le premier trou de cette liste : **chacune** de ses cinq entrées avait été payée par
un faux manquant du même genre — `DawnBlade` (`RELIC_ABILITY_TRIGGERS`, #951-r2), `FireOfAbsolution`
(`IMPERATIVE_ABILITY_VECTORS`, #951-r2), `Boltstorm` et voisins (`CUSTOM_NORMAL_ATTACK_BY_PASSIVE`,
#925), `MartialKatah` (`TRAIT_OWNER_EFFECTS`). Le gisement se rouvrait **à chaque registre neuf**.

## 2. Volet SUR-comptage — un montage DÉCLARÉ qui n'exécute RIEN

Symétrique, et un correctif du seul volet 1 l'aurait **aggravé**. Une entrée
d'`ABILITY_INIT_OWNER_EFFECTS` créditait l'item **même quand l'effet posé n'a aucune classe** dans
`EFFECT_CLASSES` : le port déclare une pose, et rien ne s'exécute.

**6 mythiques** dans ce cas — `BlightedLand`, `CabalOfSorcerers`, `ContemptuousDisregard`,
`GuardianConstruct`, `MoreGitzOverEre`, `WisdomOfTheAncients`. Ce sont **exactement** les entrées
d'`ABILITY_INIT_OWNER_EFFECTS` dont aucune cible n'a de classe : le critère ne désigne rien d'autre.

⚠ **Le gisement s'ALIMENTE, et le rebase l'a montré en direct.** Au premier passage la mesure en
donnait **4** ; `ContemptuousDisregard` puis `WisdomOfTheAncients` s'y sont ajoutées pendant que
cette tranche tournait, livrées par deux autres agents qui ont porté la **pose** et laissé la face
dégât bloquée sur le mur `rareté` (#1042-r1). C'est donc le **régime courant** de l'axe mythique,
pas un reliquat — et c'est précisément pour ça que le compte doit les NOMMER au lieu de les fondre.

Le critère n'est pas inventé ici — `audit_passive_ability_coverage` l'applique **déjà** à son canal
`[O]` (« avec AU MOINS un effet cible present dans `EFFECT_CLASSES` »). Les deux audits
divergeaient sur la même question.

## 3. La réponse : un TRI-ÉTAT, pas un booléen

`PORTE` / `PARTIEL` / `ABSENT`. `PARTIEL` = une voie désigne l'item et son **gate** tombe. Il reste
compté comme du travail — c'en est — mais il est **nommé** : il demande *la face qui manque*, pas un
port entier. Le rabattre sur `PORTE` fait renoncer ; sur `ABSENT`, re-dispatcher un port à moitié
fait. Le doc généré **annonce** le changement de sens au lieu de le glisser.

## 4. Le foyer — `scripts/python/kit_item_voies.py`

Même patron que `decision_face_voies` (#979) sur la face DÉCISION et `trait_channels` (#1015) sur
l'axe TRAIT : **partitionner un périmètre**, pas énumérer des registres.

`PERIMETRE` = `engine/runner` + `engine/entities/effects/factory.py` + `engine/services`.
**1515** conteneurs visités → **20** VOIES, **27** ÉCARTÉS avec raison, **0** MUET, **40** écartés
par le filtre, **1428** inertes. Un registre neuf y sort MUET, et le cliquet rougit.

Deux crans au-delà du patron :

**(a) L'ENUM DE LA CLÉ SE LIT AU SITE.** Résoudre un ordinal dans les trois enums faisait basculer
**5** items — dont **4 FAUX** :

```
ordinal   EffectType                              TriggeredAbilityType
1451      PhoenixGem_CanRevive   <- la VRAIE      WisdomOfTheAncients    <- faux positif
1508      HealingBalms                            MastersOfManoeuvre     <- faux positif
1462      TheArdentBlade         <- faux positif  NetherRealmCasket
1443      ContemptuousDisregard_DamageReduction   ObsessiveAnnunciation  (faux positif à gauche)
```

Le balayage naïf est **doublement** faux : il crédite `WisdomOfTheAncients` **et** perd
`PhoenixGem` (1451 résout en `TriggeredAbilityType` avant `EffectType`). C'est le partage
d'ordinaux du CLAUDE.md, appliqué à un recensement.

**(b) Chaque ÉCARTÉ imprime ce qu'il COÛTERAIT s'il était inscrit** (`--tout`, colonne `bascules`).
Un écart qui ferait basculer un item devient **visible** — la partition est falsifiable, pas
seulement exhaustive. C'est ce qui a tranché `_TRAITS_WITH_DERIVED_ABILITIES` : l'inscrire ferait
basculer `Healer` (6 porteurs, le total ENTIER de l'audit) sur un étage que le module lui-même
déclare **non porté** (« ce jeu sert à REFUSER en silence-zéro »). `Healer` reste donc un vrai
manquant — et le seul.

## 5. Mesure AVANT / APRÈS, isolée

Contrôle d'isolement : arbre témoin extrait de **`b91d1f18`** (`git archive`, arbre **complet**) et
audits régénérés dedans. `kit-coverage.md` versionné y était **à jour** (0 divergence) ⇒ tout son
delta est l'effet de cette tranche.

| compte | avant | après |
|---|---:|---:|
| voies conditionnelles **non portées** | 5 (2 mythic / 3 item) | **10** (8 mythic / 2 item), dont **6 PARTIELLES** |
| voies conditionnelles **portées** | 38 | **33** |
| passifs npc portés (`npc-registry`) | 110 | **111** |
| total kit intrinsèque (`missing`) | 6 | **6** (inchangé — les 6 porteurs de `Healer`) |
| actives no-op (lineup) | 0 | **0** |

**Les deux listes nominatives, qui sont le livrable** :

* **SOUS-comptage → +1 portée** : `PhoenixGem`.
* **SUR-comptage → 6 dé-créditées** (portées ⇒ `PARTIEL`) : `BlightedLand`, `CabalOfSorcerers`,
  `ContemptuousDisregard`, `GuardianConstruct`, `MoreGitzOverEre`, `WisdomOfTheAncients`.
* **npc** : `HarlequinsPanoply` (portée).

`5 − 1 + 6 = 10` et `38 + 1 − 6 = 33`. **Le second volet pèse six fois le premier** : un correctif
du seul sous-comptage aurait fait passer le compte de 5 à 4 et **aggravé** l'écart au réel.

⚠ Sur `npc-registry.tsv`, **8 lignes** divergeaient déjà entre le fichier versionné et sa
régénération à `origin/master` (4 actives portées sans régénération du doc). **Ce n'est pas l'effet
de cette tranche** — c'est une péremption antérieure, que la régénération corrige mécaniquement.
Mon effet seul sur cet audit est **une ligne** (`HarlequinsPanoply`).

## 6. Les autres axes — lesquels sont aveugles, avec leur compte

| axe | mécanisme | verdict |
|---|---|---|
| passifs / traits / conditionnelles | était une liste blanche de 5 registres | **c'était le vice** — corrigé |
| traits | `trait_channels.canaux()` (#1015), balayage AST de tout `engine/**` | **non aveugle** — pas de liste blanche |
| actives (combat) | `aid in ABILITY_CLASSES` | **non aveugle** : c'est LE registre du dispatch d'exécution. Contributif nul aujourd'hui (0 no-op lineup) |
| face DÉCISION | `decision_face_voies` (#979), partition | **non aveugle** |

## 7. Les audits voisins — même vice, foyer DIFFÉRENT, impact NUL aujourd'hui

`audit_combat_ability_coverage._triggered_portee` porte le même vice **sous deux formes** :

* son balayage `d.get(nm)` avec `nm` **chaîne** est structurellement aveugle à **3 des 8**
  conteneurs de `registry` — `EFFECT_TRIGGERS` (50 entrées), `CUSTOM_TRIGGERED_ABILITIES` (4),
  `GLOBAL_TRIGGERS` (liste, 2). Il ne voit que les 5 dicts à clés `str` ;
* son périmètre est le **seul** module `registry` (import en dur dans la fonction), donc il est
  aveugle aux **13** voies que le foyer inscrit hors de ce module.

**Impact mesuré : 0.** La fonction n'est appelée que sur les lignes `HORS-ACTIVE`/`INCONNU`, et il
n'y en a **qu'une** (`Maugetar`), vue portée par `RELIC_ABILITY_TRIGGERS` — donc en accord avec le
foyer. Ce n'est **pas le même foyer de code** et la question posée diffère (« par quel registre ce
NOM est-il monté », pour afficher une inversion de voie) : non corrigé ici, résidu `#1041-r1`.
Le premier nom `HORS-ACTIVE` dont la triggered vivrait dans `EFFECT_TRIGGERS` sortirait
« NON PORTEE » à tort.

`audit_passive_ability_coverage` énumère lui aussi ses canaux (7), mais son filet `[B]`/`[R]`
(balayage AST de tout `engine/`) rattrape beaucoup, et son canal `[O]` appliquait **déjà** le gate
du volet 2. Divergence mesurée contre le foyer : cf. `#1041-r2`.

## 8. Ce qui n'est PAS couvert

* **La fidélité.** Le tri-état mesure la présence d'un câblage et la vivacité de sa cible, jamais la
  justesse du corps. Un item `PORTE` peut l'être faussement.
* **Les 4 PARTIELLES ne sont pas portées ici.** Cette tranche les rend visibles et nommées ; leur
  face dégât reste à porter (régime courant de l'axe mythique).
* **Le gate est unique** (`GATE_EFFET_CLASSE`). Une voie de pose de **flag**
  (`ABILITY_INIT_OWNER_FLAGS`) n'a pas d'équivalent dérivable — son en-tête exige que chaque entrée
  **nomme son lecteur**, c'est une déclaration, pas une vérification.
* **`PhasalSubjugator`, `TheArdentBlade`, `OnMyPosition`, `ShieldOfFaith`** restent `ABSENT` —
  vérifié : aucun conteneur d'`engine/**` ne les désigne sous une résolution correcte.
* **Les 6 `PARTIEL` ne sont pas portées ici**, et leur face manquante est bloquée en amont : les
  deux dernières arrivées butent sur le mur `rareté` (`#1042-r1`), pas sur cet audit.

## Résidus

* `#1041-r1` — `audit_combat_ability_coverage._triggered_portee` est aveugle à 3 des 8 conteneurs de
  `registry` (clés entières, liste) et à 13 voies hors de ce module. Impact **0** aujourd'hui (1
  seule ligne `HORS-ACTIVE`, en accord), donc non corrigé — mais structurel.
* `#1041-r2` — divergence résiduelle entre `audit_passive_ability_coverage.channels()` et le foyer :
  les deux répondent à la même question avec deux jeux de canaux distincts, et rien ne les
  confronte. Un croisement exécutable manque.
