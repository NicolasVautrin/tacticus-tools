# #908 — `NetherRealmCasket` (relique, `TriggeredAbilityType` 0x5b6 = 1462)

Build `rnca9r7q6c`. Une ability, **deux** effets, **deux** canaux de port distincts.
Les deux sont **portés et confrontés live**.

---

## 1. Identité

| Objet | Enum | Ordinal |
|---|---|---|
| l'ability (et la CONFIG des deux effets) | `TriggeredAbilityType.NetherRealmCasket` | `0x5b6` = 1462 |
| effet crit | `EffectType.NetherRealmCasket_CritDamageReduction` | `0x5af` = 1455 |
| effet repair | `EffectType.NetherRealmCasket_LivingMetalBonus` | `0x5b0` = 1456 |
| la variable crit | `AbilityVariableType.critDmgReduction` | `0x97` = 151 |
| la variable repair | `AbilityVariableType.hpToHeal` | `0x20` = 32 |
| la cause qui ouvre le gate | `TriggeredAbilityType.LivingMetalRepair` | `0x3f2` = 1010 |

**Pas d'ambiguïté d'enum ici** (contrairement à 1460/1464 d'`AmuletOfTheVoidwyrm`) : le `.ctor` de
l'effet 1456, relu octet à octet, porte `ba b6 05 00 00` = 1462, et le gameconfig n'a qu'**une**
entrée `NetherRealmCasket`, portant les **deux** variables (`critDmgReduction` `[390 … 579]`,
`hpToHeal` `[980 … 1456]`, 10 paliers chacune).

⚠ **La collision est juste à côté** : `EffectType.RelicBoltPistol_ExtraPierce` **et**
`TriggeredAbilityType.KardiocoreGalvanus` valent tous deux **1457**. D'où l'écriture systématique
par membre nommé — un test fige la collision et **assertionne sa propre prémisse**.

---

## 2. La RE — trois artefacts natifs

### 2.1 L'ability : DEUX `AddEffect`, et c'est ce qui la distingue de ses sœurs

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NetherRealmCasketAbility$$CreateBehaviour` :

```
AddEffect(0x5af, AbilityStateReference, source = Owner@<DSLSelectors+0x30>,
                                        targets = Owner, options = <32 octets ZÉROÉS>)
  op_BitwiseAnd
AddEffect(0x5b0, <mêmes arguments>)
```

La surcharge d'`AddEffect` est tranchée par la **cible du `call`** (`0x180e9e8b0` =
`(this, effectType, abilityState, source, targets, options)`), pas par le pseudo-C — les quatre
surcharges homonymes sont indiscernables autrement. Options **zéroées** ⇒ effets **permanents** ;
ce qui les éteint est leur `CreateActiveCondition`, pas une durée.

Les autres reliques à owner-effect dérivent d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`,
dont le `CreateBehaviour` de base pose **un** effet enveloppé dans un `If(<trigger>, …)`. Celle-ci
en pose **deux**, donc elle ne peut pas emprunter cette base : `classes.tsv` la donne fille
directe de `BaseTriggeredAbility` et elle écrit son propre `CreateBehaviour`.

⚠ **Son `CreateTrigger` n'est pas lisible — résidu `#908-r1`.** La classe ne porte que
`CreateBehaviour` et `GetLocalizationData` (vérifié sur `frida/methods.tsv` **et** sur le
voisinage d'adresses de `ghidra/functions.tsv`). `BaseTriggeredAbility$$GetTrigger` appelle le slot
`+0x2d8`, et aucun `BaseTriggeredAbility$$CreateTrigger` n'existe dans les tables — ce qui **ne
prouve rien** (dédup IL2CPP). **150 des 452** filles directes sont dans ce cas, et aucun des **20**
appelants d'`OnOwnerSpecificAbilityInit` n'est cette classe. Ce qui est **établi** : les deux effets
sont posés sur l'**Owner**, sans durée, et le natif les a bien posés **au déploiement** (mesuré).

### 2.2 L'effet 1455 — axe RÉDUCTION du canal crit-DÉGÂT

```
CreateCritDamageBonus = ForSubtraction( get_OwnerIsTarget,                    <- trigger NU
                                        Multiply( ConfigVar(0x97),
                                                  AdjacentMechanicalUnits() ) )
CreateActiveCondition = AmountIsGreaterThanZero( <le MÊME compteur> )
GetCalculateLevel     = <le MÊME compteur>          (affichage, non porté)
```

Le 2ᵉ facteur est un appel **virtuel** au slot `+0x5f8` (`mov r8,[rdx+0x5f8] ; call r8`), soit
`$$AdjacentMechanicalUnits`. Troisième implémenteur de l'axe RÉDUCTION, après `AmuletOfTheVoidwyrm`
(1460) et `SupaCyborkBody` (1468) — même `ForSubtraction`, même `get_OwnerIsTarget` **nu**, même
`ConfigVar(0x97)`. **Seul le compteur change.**

### 2.3 Le compteur — trois étages, et les deux sont load-bearing

```
Count( MechanicalUnits( NormalUnits( AdjacentFriends(Owner, unique: 1, selectionType: 3), 3 ), 3 ) )
```

* **La surcharge d'`AdjacentFriends` est tranchée par la cible de son `call`** (`0x180eac2a0` =
  variante `(this, unit, unique, selectionType)`), jamais par le pseudo-C : l'autre surcharge lit
  son 3ᵉ argument comme une **ancre géométrique**. Le littéral `3` est donc un `selectionType`, et
  la variante A le propage aux deux étages internes.
* **`MechanicalUnits` n'est PAS `HasTrait(Mechanical)`** : `UnitExtensions$$IsMechanical` =
  `Mechanical 5 | LivingMetal 1000 | Vehicle 0x405`. C'est load-bearing **ici plus qu'ailleurs** —
  la relique est NECRON, tout le roster necron porte `LivingMetal`, plusieurs **sans** `Mechanical`
  (`necroWarden`, mesure #220). Un port par trait unique compterait systématiquement trop peu, sur
  le camp même où la relique s'équipe.
* **`NormalUnits` est un étage RÉEL** : `IsNormalUnit` = `!HasTrait(Object) && !HasTrait(Steppable)`.

### 2.4 L'effet 1456 — un `RepairBonus` GATÉ par sa cause

```
CreateEffectRepairBonus = ForAddition( get_OwnerIsTarget
                                       op_BitwiseAnd
                                       TriggeringAbilityIs( AbilityOrEffect(LivingMetalRepair 0x3f2) ),
                                       ConfigVar(0x20 = hpToHeal) )
```

Les deux `AbilityOrEffect` relus octet à octet (`ba f2 03 00 00` pour le gate ; `ba b6 05 00 00`
= 1462 pour le `source` du descripteur). Troisième et dernier implémenteur du canal
`BaseEffect$$RepairBonus`, et **le seul dont le gate porte un `TriggeringAbilityIs`**.

La face DÉCISION ne peut **jamais** le satisfaire (elle prédit `Repair` 28 / `Repair_GalvanicField`
1119, jamais `LivingMetalRepair`) : la face COMBAT est le seul chemin où ce bonus vaut autre chose
que 0. La RE déjà écrite dans `engine/predict.py` (#45d) est **confirmée sans correction**.

---

## 3. Confrontabilité — état 1 **et** état 2

`allowedUnits` = `necroWarden`, `necroSpyder`, `necroDestroyer` — **les trois au pool**.
`necroSpyder` porte la relique **dès le seed** (`BC.Units[].TertiaryAbility = 1462`,
`TertiaryAbilityLevel = 1`) : état 1, confrontable sans montage. Les deux autres sont en état 2
(`rl_duel build --equip-relic`), qui permet en plus de **choisir le niveau** — indispensable, car
un runner normalisé réécrit le niveau à 50 et `ability_var` clamperait au dernier palier.

⚠ **Le choix du porteur de mesure est une contrainte, pas une préférence** : sur les trois
autorisés, **deux réparent par ailleurs** (`necroSpyder` → `FabricatorClawArray` ;
`necroWarden` → `RelentlessMarch`, « repairs affected Mechanical units for 1455 Health »), ce qui
pollue tout delta de PV. `necroDestroyer` est le seul propre.

---

## 4. Le port — deux canaux, un seul effet a une classe

| effet | canal | où vit la règle |
|---|---|---|
| 1455 | `create_effect_crit_damage_bonus_for_attack` | `entities/effects/loki/nether_realm_casket.py` + `EFFECT_CLASSES` |
| 1456 | `BaseEffect$$RepairBonus` | foyer **unique** `engine.predict.calculate_repair_modifier_for_prediction` |

1456 **n'a délibérément pas de classe** : ses deux co-implémenteurs (`NanoscarabRepairProtocols`
1545, `VoltagheistField_RepairReduction` 1382) n'en ont pas non plus, et en créer une dupliquerait
la règle. Un test fige **les deux moitiés** de ce choix, sans quoi l'absence se lirait comme un oubli.

**Le canal de cause, ouvert par cette tranche** — il était nommé comme manquant par
`runner/operations/repair.py` :

```
RepairBehaviour+0x68  ->  RepairUnitOperation$$Execute  ->  PredictRepair
                      ->  CalculateRepairModifierForPrediction (5ᵉ arg `source`)
```

⚠ **Les deux `Execute` portent `abilityOrEffect`, les deux `Predict*` NON.** Mesuré : le 7ᵉ argument
arrive **sur la pile** (`in_stack_00000040`) dans `HealUnitOperation$$Execute` **comme** dans
`RepairUnitOperation$$Execute` — Ghidra décale leur signature d'un cran et nomme `abilityOrEffect`
ce qui est en réalité `removeEffects`. En revanche `DamagePrediction$$PredictHeal(this, caster,
casterTile, target, amount, scope)` **n'a pas** ce paramètre (il bâtit son `AbilityEntities` inline,
sans champ de cause) là où `PredictRepair` le relaie. `test_520_heal_pipeline_offline.py` affirmait
la symétrie des deux `Predict*` : il exige désormais la symétrie **partout sauf** ce paramètre, et
**assertionne l'asymétrie dans les deux sens**.

---

## 5. Ce qui est mesuré LIVE

### Volet REPAIR — `probe_908_nether_realm_casket_repair_live.py`

Porteur `necroDestroyer` (relique niv 3) et témoin `necroOverlord` (LivingMetal, sans relique)
régénèrent dans le **même** `endturn`, sur le **même** état : seule la relique les sépare.

| | LIVE | PORT | attendu |
|---|---|---|---|
| porteur | **+5086** | 5086 | `round(10 % × 40000) = 4000` + `hpToHeal[3] = 1086` |
| témoin | **+4000** | 4000 | `4000` |

* mutant **NOCAUSE** (cause jetée avant le modifier — la vue d'avant #908) : **4000**, écart
  exactement `1086` ; le témoin, lui, ne bouge pas ⇒ pas d'effet de bord ;
* mutant **PASSIF** (canal #357 neutralisé) : **4980** — le foyer indexe alors `hpToHeal` par le
  `level` de l'**effet capté** (1), pas par celui de la relique.

### Volet CRIT — `probe_908_nether_realm_casket_crit_live.py`

`n` n'est jamais déclaré : il est **dérivé** de l'inventaire natif (`combatSnapshot.units[].traits`),
leçon de #589-r1-r1-r2-r1-r8/r9.

| bras | `n` natif | actif natif | bonus port | LIVE (= PORT) |
|---|---|---|---|---|
| `n=0` | 0 | `False` | — | `[5434, 5811, 5674, 4085]` |
| `n=1` | 1 | `True` | `-432` | `[5051, 4130, 4902, 4181]` |
| `n=2` | 2 | `True` | `-864` | `[4338, 4763, 4441, 3899]` |
| `LivingMetal+Steppable` | **0** | `False` | — | `[5434, 5811, 5674, 4085]` |

* **le PRODUIT est confronté** : `n=1` → `-432`, `n=2` → `-864`, salves différentes ;
* **`IsMechanical` est confronté** : les compagnons portent `LivingMetal` **sans** `Mechanical`, et
  le natif les compte — un port par trait unique aurait rendu 0 ;
* **`NormalUnits` est confronté** : le même compagnon rendu `Steppable` n'est compté **ni** par le
  natif **ni** par le port ;
* **recoupement non cherché** : la salve du bras `n=0` **égale** le mutant `NOCHANNEL` des bras
  `n=1` et `n=2` — le canal ne verse rien à `n=0`, et les rolls sont bien identiques ;
* mutants `NOCHANNEL` et `PASSIF` mordent tous deux dès `n > 0` ;
* **généralisation** : niveau 7 (`critDmgReduction[7] = 516`), trait `Mechanical`, board `C1_74`,
  seed 31337 — accord également.

### ⚠ Le probe s'est d'abord accusé lui-même, et c'est le port qui avait raison

Sur `C1_74`, le premier jet du volet CRIT a rendu **`n_natif = 2`** contre `compteur = 1` au port
— un **FAUX ROUGE**. Le discriminant était sous les yeux : **LIVE et PORT étaient IDENTIQUES**
(`[5851, 5927, 5861, 6225]`). Si le natif avait compté 2 et le port 1, l'écart de `516` par coup
serait apparu dans la salve.

Cause : l'inventaire filtrait par `hexgeo.distance == 1`, alors que le natif suit la liste
d'adjacence **STOCKÉE** — `AdjacentFriends` → `AdjacentTiles` → `AdjacentTilesSelector$$Select` →
`IBattleQuery` slot 80 = `IterateAdjacentTiles`, dont
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` énumère
`tile.<+0x30>.<+0x10>`, **sans aucune géométrie**. Deux tuiles à hex 1 peuvent donc ne pas être
voisines. C'est exactement la mesure de #589-r1-r1-r2-r1-r8, **ici re-observée sur un canal
indépendant** (l'activité d'un effet + le dégât, plutôt que le compteur d'un autre effet).

Le probe dérive désormais `n_natif` de `board.neighbours(<tuile de l'ancre>)` et **DIT** quand le
`n` posé diffère du `n` compté — il ne corrige pas le montage en silence. `MC1_67` ne montrait pas
l'écart (les deux critères y coïncident) : un seul board n'aurait jamais fait apparaître le vice.

---

## 6. Résidus ouverts

* **`#908-r1`** — le `CreateTrigger` de `NetherRealmCasketAbility` n'est pas lisible (dédup IL2CPP
  probable). Sans conséquence sur le port actuel : les effets entrent dans l'état par la **capture**.
  Il le deviendrait si l'on voulait porter la **POSE** offline.
* ~~**`#908-r2`**~~ — **FERMÉ (#10035, 2026-08-18).** La fiche avait raison de dire « même cause que
  `#589-r1-r1-r2-r1-r1` », elle se trompait sur **laquelle**. Ce n'était ni le registre (les deux
  entrées sont posées depuis le 2026-08-15) ni la lecture de la relique (acquise depuis #1005), mais
  un **ordre de passes** dans `snapshot.load_state` : `_load_stats_and_effects`, qui porte la boucle
  `_seed_ability_owner_effects`, tourne **avant** `_load_tertiary_abilities`, seul écrivain de
  `ctx.tertiary_ability`. Corrigé par `snapshot._seed_tertiary_owner_effects`, placée entre
  l'écrivain et le re-bake. `necroSpyder` porte cette relique **dans le seed BC** — c'est le seul des
  9 registres relique dans ce cas, donc le seul rayon immédiat de la passe. Détail :
  `docs/rl/case-10035-pose-tertiaire-au-chargement.md`.
  ⚠ **NON CONFRONTÉ LIVE sur le dégât, et c'est structurel** : à `n = 0` l'effet ne verse rien, à
  `n > 0` il est ACTIF donc déjà capté — le dégât est identique avant/après, sur les deux bras.
  Résidu **`#10035-r1`**.
* **`#10035-r2`** — `probe_908_nether_realm_casket_crit_live.py --n 0,1 --level 1` est **ROUGE**, et
  il l'était **déjà** avant #10035 (vérifié en restaurant `snapshot.py` : sortie strictement
  identique). Son bras mutant `PASSIF` retire `tertiary_ability_state_of` du **contexte**
  `_crit_board`, mais depuis #1009 le couple TERTIAIRE est baké **dans l'instance** : l'effet lit son
  propre couple et le mutant ne mord plus. Pour redevenir discriminant, il doit viser le **re-bake**.
* **`#589-r1-r1-r2-r1-r3`** (préexistant) — la face PRÉDICTION ignore les canaux CRIT :
  `services/damage_prediction.py` n'appelle pas `crit_damage_bonus_from_effects`, donc la réduction
  de 1455 n'entre pas dans la prédiction. Les deux faces divergent sur tout porteur.
* **Non couvert** : l'axe `Vehicle` du prédicat `IsMechanical` (les bras joués couvrent
  `Mechanical` et `LivingMetal`) ; `GetCalculateLevel` (niveau d'affichage, aucun observable de
  combat) ; le `source = AbilityOrEffect(1462)` des deux descripteurs (attribution, pas d'observable
  d'état porté).
