# `#419-r5` — le canal CRIT/BLOCK était MUET sur toutes les unités de tous les runners

## 1. La question binaire, et le critère énoncé avant la mesure

Deux suspects : `buildNormalizedBC` qui remet le champ à zéro, ou `combatSnapshot` qui ne le
publie pas. **Critère posé avant de mesurer** : lire la valeur de l'unité *en bataille* par un
canal **indépendant de `combatSnapshot`**.

* natif en bataille `> 0` ⇒ le BC transmis est bon, c'est la **publication** qui est muette ;
* natif en bataille `== 0` ⇒ le champ est perdu **en amont**, et alors **le natif lui-même ne
  crite jamais** — un fait observable sans rien devoir à notre port.

Les deux branches ont des conséquences disjointes, donc le critère tranche. Canal indépendant
retenu : le template que `buildNormalizedBC` **renvoie** (`configJson`), en amont du spawn donc
en amont de tout snapshot.

**Verdict : `buildNormalizedBC`.** `combatSnapshot` est hors de cause, et il est *innocenté par
la mesure*, pas par lecture de code : au bout de la chaîne, le template porte `CritDamage = 2727`
et le snapshot republie `2727`.

## 2. La cause

`buildNormalizedBC` écrase les 8 stats numériques du seed BC par la sortie de
`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor`
(`frida/hooks/features/normalize-bc/json-build.ts` : `u.CritDamage = b.add(0x14).readS32()`).

Or les 4 stats crit/block **ne sont pas dans la base d'un héros**. Mesuré sur le gameconfig du
build courant :

```
adeptMorvenn  stats     = {"Health": 95, "Damage": 24, "FixedArmor": 24, "ProgressionIndex": 12}
              itemSlots = ["I_Crit", "I_Block", "I_Booster_Block"]
```

Elles n'arrivent que par les **items équipés**, que `IdunMetaLogic.Formulas.StatsFormula$$StatsFor`
fusionne via `IdunMetaLogic.Formulas.UnitDynamicStats$$Merge`. `buildNormalizedBC` appelle la
formule avec une liste d'items **vide** (`args.itemSpecs?.[unitId] ?? []`), donc elle rend
légitimement `0` — et ce `0` écrase le `352` du seed.

**Le layout n'est pas en cause, et c'est vérifié plutôt que supposé.**
`IdunMetaLogic.Formulas.UnitDynamicStats$$Merge` compose les indices 4, 6, 8, 10 en
**probabilité** (`p += (1 − p/100) · q`) et tous les autres **additivement** — soit exactement
`CritChance`, `BlockChance`, `CritChanceBonus`, `BlockChanceBonus` aux offsets `+0x10`, `+0x18`,
`+0x20`, `+0x28`. Le commentaire de layout de `normalize-bc/formula.ts` est donc confirmé par une
source indépendante de lui-même.

## 3. Pourquoi c'était coûteux

`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` est `GetStat(9) > 0 && GetStat(10) > 0` —
une **conjonction**. Le canal muet la rendait fausse pour **toute** unité, **côté natif comme
côté port**. `RollCritical` et le gate « never crit » étaient donc structurellement inertes, et
tout accord natif-port sur ces chemins était un **accord en régime dégénéré** : les deux côtés
rendaient zéro. Même raisonnement pour `$$CouldBlock`.

## 4. L'ampleur, mesurée

Sur les **106** unités normalisées du seed BC au rank 17 :

| | sans items (l'état livré jusqu'ici) | avec items BiS |
|---|---|---|
| `could_crit` | **0 / 106** | **98 / 106** |
| `could_block` | **0 / 106** | **46 / 106** |

Ce n'est donc pas un cas particulier : c'est **général**. Les 8 unités qui restent fermées sont
les 8 MoW (`pool_mow`). Au **seed**, avant normalisation, 96 des 106 portaient déjà un couple
crit non nul — la normalisation les remettait toutes à zéro.

## 5. Ce n'était pas ignoré — c'était traité comme une fatalité

Le fait est **écrit depuis longtemps**, à quatre endroits au moins, mais toujours comme une
contrainte à contourner, jamais comme un défaut à corriger :

* `rl_duel.py` (aide de `--crit`) : « *restaure des stats de combat […] (**la normalisation les
  remet à 0**) […] le crit d'un héros vient des items I_Crit (cf. `itemSlots`), absent d'un build
  frais* » ;
* `rl_duel.py` (aide de `--block-*`) : « *un héros frais a BlockChance/BlockDamage = 0 (le block
  vient des items)* » ;
* `tests/engine/runner/test_damage_block_live.py` : « *aucune unité n'a de block de base : il
  vient uniquement des items équipés* » ;
* `probe_113_votann.py` : « *un héros frais a critChance/blockChance de base = 0* ».

Le contournement standard (`--crit`, `--crit-target`, `--block-target`, `--block-player`,
`--unit-stat`) **réécrit le scalaire après la normalisation**. Il ouvre le canal, mais il ne
rétablit pas la voie native. `--bis-items` équipe, ce que le jeu fait.

## 6. Le correctif

Tout l'outillage existait déjà côté hooks et **n'avait aucun appelant Python** :
`buildBisItemSpecs` (`frida/hooks/features/normalize-bc/items-catalog.ts`), exposé par le RPC
`previewBis`, et le paramètre `itemSpecs` de `buildNormalizedBC`. **Aucune modification de
`frida/hooks/*` n'a donc été nécessaire — le correctif est purement Python, et n'attend aucune
fenêtre de réinjection.**

* `rl_collect_batch._bis_item_specs` — appelle `previewBis` (faction lue au gameconfig), cache
  par `(sid, unités, cap, relics)` ;
* `rl_collect_batch._normalize_and_extract_pool(equip_items=…, item_specs=…)` — le foyer partagé
  (~30 lecteurs) ;
* `rl_duel build --bis-items` ;
* `TACTICUS_BIS_ITEMS=0|1` — bascule globale dans les deux sens, sans toucher au code, pour
  établir un témoin ou mesurer une bascule du défaut d'un coup.

Le cap de rareté des items est **la constante qui sert déjà de `targetRarity`** : il n'y a qu'un
régime cible, pas deux.

### Deux gardes, chacun pour une panne mesurée

* **La mutation doit mordre.** La première écriture posait `equip_items` mais **jamais**
  `args["itemSpecs"]` — le canal restait à `0/106`. C'est le probe qui l'a attrapé, pas la
  relecture.
* **`ok: true` ne suffit pas.** `previewBis` rend `ok: true` avec des `itemSpecs` **vides** quand
  aucun slot n'est pourvu. Accepter ce vide restituerait le régime dégénéré **sans aucune
  trace** : un zéro se lirait comme une mesure. `_bis_item_specs` **refuse** si aucune unité ne
  repart équipée, et cite les raisons rendues par le picker.

## 7. Le défaut reste « ne pas équiper » — arbitrage MESURÉ

Équiper est le régime **fidèle** : un héros rank 17 / level 50 / 5 étoiles sans aucun item
n'existe pas dans le jeu. Mais basculer le défaut change l'état de **tous** les runners. Rayon de
souffle, mesuré en jouant 8 fichiers de dégât **dans les deux régimes** :

| fichier | sans items | avec items |
|---|---|---|
| `test_damage_roll_live` | 2 passed | 2 skipped → **réparé ici**, 2 passed |
| `test_damage_normal_armored_live` | 3 passed | **3 skipped** (fichier inerte, garde #455) |
| `test_damage_ability_live` | 1 passed | **1 failed** (écart natif-port de 904 PV) |
| `test_damage_catalog_live` | 5 passed | 1 passed + 4 skipped |
| `test_damage_crit_live` | 1 passed / 1 skipped | **identique** |
| `test_damage_block_live` | 2 passed | **identique** |
| `test_damage_decomp_live` | 1 passed | **identique** |
| `test_runner_attack_live` | 2 passed | **identique** |

Les fichiers qui se dégradent sont **tous** de la même famille : ils ne retiennent qu'un coup
« propre » (sans crit ni block) et le trouvaient **sans rien demander** tant que le canal était
muet. Leur verdict reposait donc sur un **accident global**. Les réparer un par un excède cette
tranche et demande un arbitrage par fichier (viser le régime crit, ou le neutraliser
explicitement).

**On livre donc l'outil et la mesure, défaut inchangé** : aucun verdict existant ne bouge, et le
canal s'ouvre pour qui le demande. Le jour de la bascule, c'est `_EQUIP_ITEMS_PAR_DEFAUT` qui
passe à `True` — résidu `#419-r6`.

⚠ **Le rayon de souffle ne se limite pas au canal crit/block**, et la première écriture du probe
portait la prémisse inverse (« équiper ne touche que crit/block ⇒ 0 divergence attendue »). **La
mesure l'a réfutée** : équiper fait aussi entrer l'unité dans ses **autres** slots — **49** unités
sur 106 changent de `FixedArmor` (+654 par slot `I_Defensive` mythique) et **4** de `Health`. Les
57 stables sont exactement celles dont les slots sont `I_Crit`/`I_Block`/`I_Booster_*`. Le probe
**ventile** désormais par stat et par jeu de slots au lieu de compter un écart à zéro.

## 8. Ce qui a été rejoué

* `probe_419r5_canal_crit_block.py` — étages 1-3 (RPC seul) + étage 4 **live** : runner monté,
  `combatSnapshot` relu, `could_crit 2/2` au natif, template `2727` → snapshot `2727`.
* `tests/engine/test_419r5_canal_crit_ouvert_live.py` — **3 passed**. Volet 1 : `--bis-items`
  ouvre crit **et** block. Volet 2 **anti-tautologie** : le même montage **sans** le drapeau doit
  avoir le canal **fermé**, sinon le fichier ne garde plus rien.
* Les 8 fichiers du tableau §7, joués **deux fois** (avec et sans items) — c'est ce double jeu
  qui a établi que les 3 dégradations sont **causées** par l'ouverture, et non préexistantes.

## 9. Résidus NOMMÉS

* **`#419-r6` — basculer le défaut à « équiper », et réparer les fichiers de la §7.** Le geste
  est d'une ligne (`_EQUIP_ITEMS_PAR_DEFAUT = True`) ; le travail est de réparer les fichiers qui
  reposaient sur l'accident global. Le remède-type est établi et appliqué une fois
  (`test_damage_roll_live` : `NO_NOISE` sur les **quatre** faces — `--crit`/`--block-player`
  n'épinglent que les p-units, `--crit-target`/`--block-target` que les a-units).
* **L'écart natif-port de 904 PV de `test_damage_ability_live` n'est pas diagnostiqué.** Les
  dégâts par coup sont **identiques** des deux côtés (`live_ph == off_ph == [5543]`) : l'écart
  porte sur l'**état de départ**, pas sur le calcul. C'est le premier écart réel que l'ouverture
  du canal fait apparaître, et il mérite son propre découpage.
* **Le choix BiS n'est pas confronté au choix du jeu.** `pickBisForSlot` prend la rareté la plus
  haute ≤ cap, puis `starLvl`, puis le nombre de niveaux, au niveau **max**. C'est cohérent avec
  le reste de la normalisation (tout au max), mais ce n'est pas un mirror de
  `UnitProgression$$GetCappedItemModelsOfUnit`, qui dépend de l'inventaire réel du joueur.
* **Les 4 unités sans `FactionId`** (`necroNpc*`) sont omises du picker. Sans effet mesurable —
  elles n'ont aucune entrée `lineup`, donc aucun slot — mais c'est une omission, pas une preuve.

## 10. Ce qui n'est PAS couvert

* **Les ~20 fichiers de la catégorie « indirectement exposés »** (recensement §2) n'ont pas tous
  été joués : 8 l'ont été. L'extrapolation n'est pas une mesure.
* **La face DÉCISION** : `MightCrit@+0xB1` = `CouldCrit(attaquant)` valait `False` sur *toutes*
  les prédictions, donc `engine_agreement_stages` et les tests d'overkill concluaient eux aussi en
  régime dégénéré. Non rejoués ici.
* **Le block n'a pas d'étage live dédié** : le garde vérifie que `CouldBlock` est vrai, pas qu'un
  block **se produit** et que le port le reproduit.
* **Un seul rank (17) et un seul board (`MC1_67`)** pour l'étage live.
