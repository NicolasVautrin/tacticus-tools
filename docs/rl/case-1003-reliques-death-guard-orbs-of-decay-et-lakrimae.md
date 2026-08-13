# #1003 — `OrbsOfDecay` (1465) et `Lakrimae` (1541) : deux reliques Death Guard, un seul montage

**Question binaire.** Les deux abilities de relique du roster Death Guard sont-elles portables et
confrontables au natif, et par quel canal ?

**Réponse.** Oui, par `RELIC_ABILITY_TRIGGERS` — et le canal se lit **ability par ability** :
`OrbsOfDecay` porte `CreateTrigger` **et** `CreateBehaviour`, `Lakrimae` en porte **deux jeux**
(deux classes natives pour un seul id). Le volet confronté live des deux est la **contamination de
la tuile de la cible** ; le volet ATTAQUE d'`OrbsOfDecay` est porté et gardé **offline**.

Build de mesure : `rnca9r7q6c`.

---

## 1. Ce que les deux ids portent réellement — **cinq** classes natives, pas deux

| id | classe native | porté | où |
|---|---|---|---|
| **1465** | `…Triggered.Loki.OrbsOfDecayAbility` | **OUI** | `triggers/loki/orbs_of_decay.py` |
| 1465 | `…Triggered.Loki.OrbsOfDecay_AdditionalHitsAbility` (pose l'effet **1463**) | non | résidu `#1003-r1` |
| 1463 | `IdunBattle.Entities.Effects.Loki.OrbsOfDecay_AdditionalHitsEffect` | non | résidu `#1003-r1` (= `#884-r2`) |
| **1541** | `…Triggered.Loki.Lakrimae_AddContamination_Ability` | **OUI** | `triggers/loki/lakrimae.py` |
| 1541 | `…Triggered.Loki.Lakrimae_SummonPoxwalker_Ability` | non | résidu `#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1` |

Les deux ids sont des `TriggeredAbilityType` : **ni `ABILITY_CLASSES`, ni `TARGETING_OPTIONS`, ni
`ABILITY_ATTACK_TYPE`** ne les concernent (bras exécutable :
`test_1003_reliques_death_guard_offline.py::test_1003_ni_active_ni_masque_de_ciblage`).

## 2. `OrbsOfDecay` — l'i2 décrit **deux artefacts**, et n'en nommer qu'un fait écrire un faux port

> « The relic bearer's normal attacks deal an additional 2x 1018-2036 Toxic Damage to enemy units
> that have their Armour reduced by 30% or more and are also **on or** adjacent to the target's hex.
> Additionally, the target's hex is Contaminated. »

* **« adjacent to the target's hex »** = `OrbsOfDecayAbility$$CreateBehaviour`, porté ici ;
* **« on the target's hex »** = `OrbsOfDecay_AdditionalHitsEffect$$CreateAdditionalHits`, qui ajoute
  des COUPS à l'attaque primaire — **non porté** (`#1003-r1`).

Le sélecteur du premier **EXCLUT la cible**, et c'est lu, pas déduit :
`DSLSelectors$$AdjacentEnemies` variante B (`180eac190`, tranchée par XREFS entrantes) =
`Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) − unitTile, 3)`, et
`AdjacentTilesSelector$$Select` teste `Contains(originTiles, adjacentTile)` avant d'ajouter. Aligner
le port sur la lettre de l'i2 (« on or ») serait donc une faute — d'où le bras
`test_1003_la_cible_nest_pas_frappee_par_le_volet_ability`.

**Le prédicat, entièrement qualifié** (`OrbsOfDecayAbility$$GetTriggerForAttack`, statique, partagé
avec l'effet 1463) :

```
  AmountIsGreaterThanZero( StatAmount(Subject@+0x68, 0x10 = FixedArmor, part 3 = INITIAL, null, 0) )
& AmountIsGreater( Divide( Multiply( StatNegativeModification(Subject@+0x68, 0x10),
                                     <DSLFormulas+0x30> = Direct(100) ),
                           StatAmount(...), mode 0 = half-to-even ),
                   ConfigConst(0x83 = armorReductionPct) )
```

Les trois inconnues que `#998-r2` exigeait de qualifier **AVANT** de porter :
`0x10` = `StatType.FIXED_ARMOR`, `<formulas+0x30>` = `Direct(100)`, et le `statPart 3` = **INITIAL**
(le dénominateur est l'armure de BASE — c'est ce qui rend le ratio lisible comme un « % de
réduction »).

⚠ **`AmountIsGreater` est STRICT** là où l'i2 dit « or more ». Ce n'est pas académique :
`ContaminatedStatModifierEffect` pose exactement `−30 %`, donc **`Contaminated` seul ne suffit
JAMAIS** à ouvrir le volet attaque. Il faut une seconde source — typiquement l'aura
`ContagionsOfNurgle_ArmorReduction1` (`−20` **plat** sur `FixedArmor`), que tout porteur Death Guard
projette.

## 3. La formule qui manquait — `StatNegativeModification`

`IdunBattleLogic.Entities.DSLFormulas$$StatNegativeModification` →
`IdunBattle.Entities.Formulas.NegativeStatModificationFormula$$Calculate` : itère le
`Dictionary<source, ValueModification>` de la stat et **n'accumule que les contributions `< 0`**, en
valeur absolue. **Deux call-sites natifs dans tout le binaire, les deux dans `OrbsOfDecay`.**

⚠ **Ce n'est PAS `StatAmount(part 5 = MODIFICATION)`**, qui rend le total SIGNÉ : `−40` compensé par
`+40` rend **40** ici et **0** là. Confondre les deux rend le prédicat muet dès qu'un buff d'armure
coexiste — invisible sur tout cas à une seule source. Substrat :
`UnitStats.negative_stat_modification` (même dictionnaire per-source que `has_negative_modifier`,
qui n'en était que le prédicat existentiel).

## 4. `level_slot="tertiary"` — le slot qui manquait à `ability_attack_params`

`MinMaxDamage` se résout contre l'`abilityState` sous lequel l'ability est **montée**, et
`UnitFactory$$Build` fabrique un `tertiaryAbilityState` **propre** (`TertiaryAbilityLevel`,
`TertiaryAbilityVariablesMultiplierPercentage`). Le registre ne connaissait que `active`/`passive` :
une relique de niveau 3 aurait lu le niveau des PASSIFS (50 sur tout runner normalisé), donc le
**dernier palier** de `minDmg`/`maxDmg`. C'est l'écart silencieux que #357 avait fermé pour
`DawnBlade` sur le canal REPAIR, et qui se rouvrait ici sur le canal DÉGÂT. Foyer unique conservé :
`triggered_ability_state` (import DIFFÉRÉ, classé **PORTEUR** — mesure : charger
`triggers/base` en process frais charge `abilities/base`, l'inverse non).

## 5. Les deux `AddEffect(Contaminated)` n'ont pas la même SOURCE — et c'est une surcharge différente

| ability | surcharge native | source de l'effet | port |
|---|---|---|---|
| `OrbsOfDecay` | `AddEffect(effectType, abilityState, targets, turns)` (`180e9eb30`) — passe `0` en source | **la TUILE elle-même** | `source_from_target=True` |
| `Lakrimae_AddContamination` | `AddEffect(effectType, abilityState, source, targets, options)` (`180e9e8b0`) | **`Owner@DSLSelectors+0x30`** | `source_ref=Owner()` |

Deux abilities Death Guard, même effet, même géométrie, **attribution opposée**. C'est le bras
`test_1003_les_deux_contaminations_nont_pas_la_meme_source`, et le mutant qui les échange est vu
rouge.

## 6. Ce qui a été confronté LIVE, et comment le confond a été écarté

`test_1003_reliques_death_guard_live.py` — **8 bras, 8 verts**, montage
`probe_1003_reliques_death_guard.py` (`--equip-relic <porteur>:<relique>:50`, board `MC1_67`,
porteur en `3,4`, `orksNob` en `3,5`, attaque normale réelle par `applyAction`) :

| bras | `Lakrimae` (`deathTyphus`) | `OrbsOfDecay` (`deathBlightbringer`) |
|---|---|---|
| NATIF, relique équipée | tuile de la cible **contaminée** | idem |
| TÉMOIN, sans relique | **rien** | **rien** |
| PORT, même capture | **même tuile**, ensembles égaux | idem |
| PORT, sans relique | `tertiary_ability = None`, 0 event | idem |

⚠ **Le confond est réel et il a été ÉCARTÉ PAR CONSTRUCTION** : `OnToxicDamageAbility` (1203) pose
LE MÊME effet 1244 sur LA MÊME tuile quand le coup porte le trait de profil `OnToxic`. Les deux
porteurs ont été choisis sur leur arme de mêlée LUE au gameconfig — `Power` pour `deathTyphus`,
`Plasma` pour `deathBlightbringer`. **`deathPutrifier` est écarté pour cette raison exacte** (son
arme EST `Toxic`), alors qu'il est un porteur légitime d'`OrbsOfDecay`. Le bras TÉMOIN le vérifie
au lieu de le supposer.

**Porteurs NON confrontés, et c'est dit** : `deathPutrifier` (confond 1203) et `deathRotbone` —
`OrbsOfDecay` est **UNE** ability, confrontée sur `deathBlightbringer`.

## 7. Ce qui n'est PAS couvert

* **Le volet ATTAQUE d'`OrbsOfDecay` n'est confronté QU'OFFLINE.** Le prédicat (7 cas dont les
  seuils 30 / 30,1 / 30,5 / 31) et le sélecteur sont gardés par le cliquet ; aucune salve n'a été
  mesurée contre le natif. Recette du montage manquant dans `#1003-r2`.
* **Le gate STRICT n'a pas de témoin LIVE** (`#1003-r3`) : il faudrait une cible dont la réduction
  vaut EXACTEMENT 30 % et vérifier que le natif ne frappe pas.
* **`selectionType = 2`** (9ᵉ argument d'`AttackWithAttackDamage`) n'est modélisé sur aucun
  call-site porté de cette feuille — dette préexistante, pas de cette tranche.
* **L'émetteur `On(0x4a)` du port** ne couvre que la voie MESSAGE de l'attaque normale et le nœud
  DSL `EvaluateAbilities` — résidu préexistant `#478-r3`. Mesure faite ici : le rayon
  supplémentaire ouvert par `OrbsOfDecay` sur ce vecteur est **VIDE** (les deux seuls call-sites du
  nœud passent `ranged=True`, que le gate `IsMeleeAttack` refuse ; et `get_OwnerIsCaster`
  exigerait que le porteur soit le caster d'`ArmoriumCherub`).

## 8. Matrice de mutants — **10 sur 10 vus rouges**

`M1` strictesse (`AmountIsGreater` → `AmountIsEqualOrGreater`) · `M2` `StatNegativeModification` →
`StatAmount(MODIFICATION)` · `M3` `StatPart.INITIAL` → `CURRENT` · `M4` ancre `TargetTile` →
`CasterTile` · `M5` source de la contamination · `M6` `level_slot` tertiary → passive · `M7`
`is_melee` → True · `M8` gate `IsNormalAttack` **inventé** sur `OrbsOfDecay` · `M9` source de
`Lakrimae` → `source_from_target` · `M10` gate `IsMeleeAttack` retiré de `Lakrimae`.
