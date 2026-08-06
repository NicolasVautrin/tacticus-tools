# `#419-r6-r1` — les 315 « indifférents », la face DÉCISION, et les rouges préexistants

Suite de `case-419-r6-bascule-du-defaut.md`. Trois volets, et le plus gros rend un verdict
**NÉGATIF** : un port a été écrit, puis réfuté par la mesure.

## 1. La face DÉCISION — `MightCrit` dans le SÉLECTEUR de cible : port ÉCRIT, puis RÉFUTÉ

### 1.1 Pourquoi la question se posait, et pourquoi elle ne se posait pas AVANT

`#R34` a porté `MightCrit@+0xB1` (`MightCrit@0x8a` sur le build courant) sur la chaîne PLAYBOOK et
a **nommé en résidu** le seul producteur restant : `runner/operations/damage_utility._target_utility`
fabrique un `pred` synthétique **sans** la clé `mightCrit`, donc `might_be_overkill` y lit `0` en
dur. Le résidu disait « non porté faute de pouvoir le **VALIDER** », et c'était exact : tant que le
canal crit était muet (`CouldCrit` faux sur **106/106** unités normalisées, #419-r5), la clé
**absente** et la clé à **`False`** sont le **même dict** — aucune mesure ne pouvait les séparer.

La bascule du défaut à « équiper » (#419-r6) ouvre `CouldCrit` sur **98/106**. Le port a donc été
écrit, puis confronté.

### 1.2 Ce que le décompilé donne — et ce qu'il ne suffit pas à établir

`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` n'invente aucune
prédiction : il appelle le service (`this+0x50`) avec l'OWNER (`this+0x18`) et recopie la
`DamagePredictionResult` dans son état de boucle (`+0x10..+0xac`), **flags compris**. La chaîne
lue : `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` `memset` une
`AttackPredictionRequest` de `0xb8` octets puis appelle le **slot 4** de `IDamagePrediction`
(`PredictAttack`) ; `IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction` recopie la
struct **entière** (`+0x00..+0x9c`) dans son `Nullable<DamagePredictionResult>` ;
`IdunBattle.AI.Utilities.OverkillUnitUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` appelle
bien `WillBeOverkill` puis, à défaut, `MightBeOverkill`.

**Rien de tout cela n'établit que le flag ENTRE dans le classement** — et c'est précisément le pas
que la première écriture a franchi sans mesure. Il a fallu le live pour trancher.

### 1.3 Le montage, et les TROIS confondants qu'il a fallu retirer un par un

Oracle : Doombolt (`1102`, `thousAhriman`) — `SortUnitsByDamageUtility` gouverne l'ORDRE des cibles,
et `N = 3` coups sur 4 cibles donne `[1, 1, 1, 0]`, donc **la cible à zéro coup dit le dernier du
tri**, sans hook nouveau. Chaque confondant a été trouvé par une mesure fausse, pas par relecture :

| # | confondant | ce que la mesure a montré | parade |
|---|---|---|---|
| 1 | le dégât du nœud de tri était **supposé** (`level = 50, mult = 100` ⇒ 665) | le runner rend **1197** — le régime calculé sur 665 ne discriminait rien, les deux ordres identiques | `_dmg_tri_du_runner` : un runner de RECONNAISSANCE le LIT |
| 2 | l'**armure** de la cible | le port tient la prédiction IA pour pré-armure ; une cible blindée qui cesserait d'être `MightBeKill` ferait basculer le classement **sans rapport avec le flag** | `FixedArmor = Armor = 0` sur les cibles |
| 3 | le **tie-break** | à deux rôles, deux cibles ont la MÊME utilité : le live rendait `[77, 81, 83, 79]`, un ordre qu'**aucune** des deux valeurs du flag ne produit côté port | **TROIS** rôles d'utilité distincts |

Le confondant 3 est le plus instructif : un montage qui crée une égalité **ne mesure pas ce qu'il
croit** — il mesure la stabilité de l'`OrderBy` natif sur l'ordre SOURCE, que le port approxime par
`id` croissant. C'est un **résidu distinct**, nommé au §4.

### 1.4 Le verdict

Régime : `--crit 100,700` sur le caster (le crit **MORD** — le coup sur la cible du message passe de
**1468 à 2168**), armure nulle, trois rôles, marge minimale d'utilité **7,46**.

| | ordre | u79 | u81 | u83 |
|---|---|---|---|---|
| **LIVE** | `[77, 81, 83, 79]` | `[]` | `[399]` | `[399]` |
| port **de production** (sans le flag) | `[77, 81, 83, 79]` | `[]` | `[399]` | `[399]` — **BIT-EXACT** |
| **contrefactuel** (avec le flag) | `[77, 81, 79, 83]` | `[1197]` | `[399]` | `[]` — **DIVERGE** |

Même verdict au régime de crit **NATUREL** (items seuls, `crit_chance = 26`, `crit_damage = 3248`).

⇒ **`SortUnitsByDamageUtilitySelector$$Select` ne fait PAS entrer `MightCrit` dans son classement.**
Le dict de `_target_utility` est **FIDÈLE en l'état**, et le résidu `#R34` n'est pas une dette :
c'est le comportement natif. Le port a été **retiré** ; le paramètre `might_crit` reste, documenté
comme le point d'injection de la contre-épreuve.

### 1.5 Le TÉMOIN, qui établit que la bascule est bien ce qui a rendu la question POSABLE

Le même montage en `--no-bis-items` : `CouldCrit(owner)` **faux** (`crit_chance = 0`,
`crit_damage = 0`), et les **deux ordres deviennent identiques** — le montage cesse de discriminer.
C'est la signature exacte du régime dégénéré : avant #419-r6, la question ne pouvait pas être posée.
Ce n'est pas une formalité : sans ce bras, « le port sans flag colle au live » resterait compatible
avec « le flag n'a jamais été alimenté ».

**Garde** : `tests/engine/test_419r6r1_face_decision_live.py` (**4 passed**) — deux étages offline
(l'écart du flag vaut exactement `PossibleOverkill` **LU du BC** ; les entrées publiques classent
sans le flag, dans un régime où le flag changerait la réponse), deux étages live (le verdict, et le
témoin). Sans ce fichier, la prochaine lecture de `#R34` rouvrirait la même question et récrirait le
même port faux — **un résidu ne dit pas qu'il a été tranché**.

## 2. Les « indifférents » — l'indifférence était SUPPOSÉE, et elle est FAUSSE

`#419-r6` a dérivé son périmètre par trois canaux et joué **(A)** et **(C)** intégralement. Les
**315** restants ont été classés « indifférents » **sans être joués** — une liste blanche par défaut.

Comptes re-dérivés (`probe_419r6_perimetre_bascule.py`, **à re-dériver, jamais citer**) : 705
fichiers visités, 388 live, (B) 45, (A) 28, indifférents **315**, (C) 25. Sur les 315, **21** ont
déjà été joués par le canal (C) — le reste à jouer est donc `indifferent \ dur` = **294**, et le
probe le nomme désormais lui-même.

**Mesure (partielle, en cours au moment de la livraison — le journal porte l'état exact)** : sur les
premiers **154** fichiers joués en régime NOUVEAU, **131 vert, 1 INERTE, 22 ROUGE**. Un taux de
dégradation d'environ **15 %**, très au-dessus des **3,3 %** de l'inventaire #462 : l'extrapolation
« indifférent parce que sans marqueur » ne tenait pas.

⚠ **Un rouge trouvé après la bascule n'est pas un rouge causé par elle**, et c'est la leçon
n°1 de #419-r6. Les 24 dégradés ont donc été **rejoués en `TACTICUS_BIS_ITEMS=0`** ; la ventilation
CAUSÉ/PRÉEXISTANT est au §2.2.

### 2.1 Ce que le balayage a dû corriger pour exister

Quatre shards lancés en tâche de fond ont été **tués au bout de 10 minutes** (le plafond du harnais
qui les portait) et ont rendu **0 octet** après **1 h** de balayage : la sortie n'était produite
qu'à la fin. `probe_419r6_perimetre_bascule` écrit désormais un **journal JSONL incrémental** et
**REPREND** (`--journal`) — un balayage dont le coût se compte en heures doit être **ré-entrant**.

### 2.2 Ventilation des dégradés — VERDICT DU TÉMOIN

<!-- TEMOIN -->

## 3. Les rouges PRÉEXISTANTS — 15 sur 21 n'avaient qu'UNE cause

#419-r6 a mesuré **7** rouges préexistants et les a laissés tels quels, sans diagnostic. Ils ne sont
pas 7 causes.

| fichier | avant | après | cause |
|---|---|---|---|
| `test_additional_hits_after_hit_maybe_live` | 7 failed | **7 passed** | contrat de SORTIE (ci-dessous) |
| `test_additional_hits_roll_order_live` | 5 failed | **5 passed** | idem |
| `test_additional_hits_rounding_live` | 3 failed | **3 passed** | idem |
| `test_psychic_stalk_extra_attack_damage_live` | 2 failed | 2 failed | **étage** : dégâts ÉGAUX (`live == port == [3684]`), mais le `%-list` DÉFENSEUR du port vaut `[]` pour `[1.33]` attendu — le canal n'écrit pas dans le bon slot |
| `test_endturn_order_live` | 1 failed | 1 failed | ORDRE : « l'atterrissage deep-strike n'a pas eu lieu, le tick l'a précédé » |
| `test_429r1r3r1r2_unit_extensions_is_alive_live` | 2 failed | 2 failed | non diagnostiqué |
| `test_harlequins_panoply_live` | 2 failed | 2 failed | non diagnostiqué |

### 3.1 La cause unique des 15

Les trois fichiers levaient tous le **même** `KeyError: 'next_hit_index'` dans
`damage_hits.attack_state_out`. `probe_r6_round_materialize.additional_hits_variant` — le
CONTREFACTUEL substitué à `execute_additional_hits` — ne posait pas les trois clés d'état
d'`OngoingAttack` que le port livré pose depuis `#419-r3` (`next_hit_index` `@+0x30`,
`crit_allowed` `@+0x40`, `failed_block` `@+0x48`). Les deux vecteurs de dégât appellent
`attack_state_out(r, ah)` dès qu'un groupe existe : **la substitution ne remplaçait pas le port,
elle le cassait** — et l'échec accusait le moteur.

Le garde voisin ne pouvait pas le voir : `test_additional_hits_variant_signatures_offline.py`
vérifie la **signature d'ENTRÉE**. Il est **ÉTENDU** (attendus ajoutés, aucune assertion relâchée)
au **contrat de SORTIE**, dérivé à l'AST des clés que `attack_state_out` **lit** — plus un étage de
prémisse qui rougit si la dérivation devient vide. 7 → 8 tests, et la nouvelle assertion a
**effectivement attrapé** la variante avant réparation.

### 3.2 Le rapprochement demandé avec les 4 rouges de `#287-r11` — CONFIRMÉ sur la tuile

`#287-r11` signalait `test_381r4_imperative_collapses_offline` (3) et
`test_heroic_fusillade_migration_live::test_g5_move_splash_crit_wiring` (1), « autour de la tuile de
charge `(1,2)` ». Mesuré ici :

* `test_381r4` (re-joué) : `la tuile d'arret est la MEME avec et sans gate ((1, 2))` et
  `la destination HeroicFusillade est la MEME avec et sans gate ((1, 3))` — **contre-contrôles
  INERTES** (4ᵉ case #462-r6), la mutation ne mord plus ;
* `test_g5_move_splash_crit_wiring` : `Judh pas adjacent a la cible post-move: (1, 2) vs (0, 0)`.

**Même foyer (`_hf_move_dest_tile`), même tuile `(1,2)`.** Le rapprochement est donc empirique, pas
seulement thématique.

**TRANCHÉ AU REBASE : ce sont bien DEUX causes, pas une.** `#484` (PR #741) a été mergée pendant
cette tranche ; re-joué sur l'arbre rebasé, `test_381r4_imperative_collapses_offline` rend
**4 passed** — sa cause était bien le hissage d'imports `492c722f` (le `monkeypatch` posé sur le
module source ne mord plus une fois le nom hissé), et elle est fermée. `test_g5_move_splash_crit_wiring`,
lui, **reste rouge** : la tuile partagée n'était donc pas une cause partagée. Le rapprochement valait
la peine d'être fait — il coûtait un re-jeu et il a évité de traiter `test_381r4` deux fois.

⚠ Corollaire de méthode : « deux rouges pointent le même foyer nommé » justifie de les **grouper
pour les instruire**, jamais de conclure à une cause unique avant réparation. C'est le pendant exact
de l'avertissement de `case-462-tests-live-rouges-invisibles.md` §3, qui portait dans l'autre sens
(deux symptômes sans rapport, une seule cause).

### 3.3 `#419-r6-r3` — le rouge de `norncrown`, tranché sur MESURE

Signalé pendant cette tranche par `#477-r37` : `test_477r33_non_owner_playbooks_live` rend
**6 failed / 35 passed** (« trajectoire native épuisée au pas 17 »), pour **41/41** avant la bascule.
Cause mesurée par son auteur : crit et block non nuls ⇒ la bataille atteint `Finished` avant les pas
discriminants. Témoin sous `TACTICUS_BIS_ITEMS=0` : vert. L'arbitrage était laissé ouvert entre
`--no-bis-items` et une re-mesure des pas.

**Il manquait une troisième voie, et c'est le remède-type de cette famille.** `--no-bis-items`
restituerait le régime **dégénéré global** — crit et block impossibles sur *toute* unité, **plus** la
perte des autres slots d'items (`FixedArmor` sur 49 unités du seed, `Health` sur 4) : payer la
couleur au prix de la mesure. Les quatre drapeaux `--crit` / `--crit-target` / `--block-player` /
`--block-target` épinglent **quatre scalaires sur CE montage**, le reste de l'état équipé demeurant.

Posé au **foyer unique** du montage (`probe_477r33_non_owner_registry_gaps.build_extra`, partagé par
le probe et la fixture — le piège de la duplication de #419-r6 §6.4 ne s'applique donc pas ici), et
motivé par l'**axe** : ce fichier mesure une trajectoire et un accord de **tuiles**, jamais un
montant de dégât. Les **quatre** faces sont nécessaires — le montage a des porteurs des deux côtés.

**6 failed / 35 passed → 41 passed**, soit exactement le compte du témoin. Le critère n'est pas
« c'est vert », c'est « le compte est celui du témoin ».

## 4. Résidus NOMMÉS

* **`#419-r6-r1-r1` — l'étage exact qui neutralise `MightCrit` dans le sélecteur n'est pas isolé.**
  Le comportement est mesuré et gardé ; la RAISON ne l'est pas. Les trois maillons lus
  (`GetAttackPrediction` → slot 4, `ForDamagePrediction` recopie `+0x00..+0x9c`, `MoveNext` appelle
  `MightBeOverkill`) transportent tous le flag. Point d'ancrage à hooker pour trancher : l'utilité
  **par cible** rendue par `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility` dans la
  boucle du sélecteur — aucun hook existant ne la publie, donc c'est une fenêtre de réinjection.
* **Le TIE-BREAK du sélecteur n'est pas fidèle.** Le port trie par `id` croissant à utilité égale ;
  le natif garde la stabilité de l'`OrderBy` sur l'ordre SOURCE. Mesuré : `[77, 81, 83, 79]` (natif)
  vs `[77, 81, 79, 83]` (port) sur un montage à deux cibles d'utilité identique. Dégradation
  **silencieuse** — elle ne se voit que si deux cibles s'égalisent, ce qui n'arrive jamais par
  accident dans les tests existants.
* **`preventOverkill` et `forceOverkill` ne sont pas non plus posés par `_target_utility`.** Ils
  sont dans la même position que `mightCrit` l'était : non alimentés, et **non mesurés**. La mesure
  faite ici ne dit rien d'eux — elle ne porte que sur `MightCrit`.
* **Quatre rouges préexistants restent ouverts** (`psychic_stalk`, `endturn_order`,
  `429r1r3r1r2`, `harlequins_panoply`), les deux premiers avec leur symptôme localisé.

## 5. Ce qui n'est PAS couvert

* **Le balayage des 294 « indifférents » n'est pas terminé** à la livraison. Le journal
  (`--journal`) porte l'état exact et la reprise est mécanique ; les fichiers non joués sont
  **NON MESURÉS**, jamais « verts ».
* **Un seul montage pour la face DÉCISION** : Doombolt / `thousAhriman` / `MC1_67` / seed 31337.
  Les deux autres call-sites du sélecteur (`AncestralFortune` sur `votanUthar`, `FinalJustice`) ne
  sont pas confrontés — ils branchent le même étage de tri, mais avec un autre nœud de dégât.
* **La face DÉCISION hors tests** (`engine_agreement_stages.py`, `predict_sweep.py`) n'a pas été
  rejouée dans les deux régimes. La chaîne PLAYBOOK, elle, pose bien `mightCrit` (#R34), donc le
  régime dégénéré y est levé par la bascule — mais l'agrément n'a pas été re-mesuré.
* **Aucune mesure sur les abilities de relique ni les MoW** dans ce périmètre.
