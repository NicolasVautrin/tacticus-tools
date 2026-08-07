# #508 — `1204 LeadingTheCharge` : la charge, l'attaque et les quatre Death Riders

`astraDreir` « Dreir » (AstraMilitarum / DeathKorpsKrieg, **lineup**, DANS le pool `--list-pool` au
rank 17). Second porteur : `astraNpcDreir` (npc). Avant cette tranche l'ability était un **no-op
silencieux** : absente d'`ABILITY_CLASSES`, le cast partait, `ported` valait `False`, et **rien** ne
se produisait — ni déplacement, ni dégât, ni summon, ni erreur.

## 1. Ce que le natif fait — DEUX phases, pas une boucle

`IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$ExecuteBehaviour` :

```
// PHASE 1 -- AActiveAbility$$Execute
AddEffect(0x416 = Infiltrate_UnitEffect, AbilityStateReference, Owner, Owner, Direct(1))
  & MoveUnit(Caster, GetMoveTile(), <options ZERO>)

// PHASE 2 -- AActiveAbility$$ExecuteAtomic(..., 0x2a)
  ( SetCache(Cache(TimesAttackMadeThisTurn(Caster, null)))
  & IfAlive(Caster, AddStaticStatModifierEffect(Caster, 0x56c TemporaryStatModifier,
                                                0x1a StatType.ExtraPierce, GetExtraPierceRatio(),
                                                Direct(1), isHidden: 1)
                  & AttackWithAttackDamage(Caster, Target, MinMaxDamage, GetDamageProfile(),
                                           GetHits(), AbilityOrEffect(this), <ZERO>, 2) )
  & If(AmountIsGreater(TimesAttackMadeThisTurn(Caster, null), <le cache>),
       Spawn(Caster, GetSummonTiles(), GetStringConstant(0 = unitId),
             WithStatsFromConfig(config, abilityState)
               .onAppearance = AddStaticStatModifierEffect(ActiveTarget, 0x56c, 0x1a, …)
                             & PerformAIAttackFromCurrentPosition(ActiveTarget)) )
  & RemoveEffect(Caster + Children(Caster), Nullable(0x56c))
```

⚠ **`0x2a` est un `GroupType` (`Ability_AtomicGroup`), PAS un compteur d'itérations.**
`AActiveAbility$$ExecuteAtomic` ne fait qu'emballer l'arbre dans un `DSLBehaviors$$AtomicGroup`.
Ce n'est donc **pas** le patron « driver impératif qui exécute un petit arbre à chaque pas » de
`1152 UnstoppableMomentumReworked` (`case-220` §6.13), dont la boucle est bornée par un champ du
ctor. La ressemblance de nom (« charge ») ne dit rien de la forme : c'est un **arbre DSL pur**.

Les trois sous-arbres nommés :

| natif | contenu |
|---|---|
| `$$GetPossibleMoveTiles` | `TilesUnitCanMoveToChargeTarget(Caster, CasterTile, TargetTiles, Get(GetNumberConstant(0x16 = range)), ignoreFlags: 0)` |
| `$$GetMoveTile` | `First(SortTilesByUtility(<ci-dessus>, Caster, UtilityDefinition(UtilityBucket[WeightedUtility(33 MovementSuggestion), WeightedUtility(67 LeadingTheCharge_ChargeTile)])), 1)` |
| `$$GetExtraPierceRatio` | `Multiply(Direct(GetVariableForLevel(0x3f = extraPierceRatio)), Count(Filter(AllUnits(), IsNormalUnit & AreFriends(Owner) & HasBeenDefeated)))` |
| `$$GetSummonTiles` | `First(SortByFormula(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(Caster)), 7 = Tile, Owner), ConditionalAmount(HasAdjacentEnemies(Owner, ActiveTarget, 1, 0), 1, 0), ascending: 0), Get(GetVariableForLevel(0x4f = nrOfSummons)), 0)` |
| `$$GetDynamicInvalidTargetReason` | `Count(GetPossibleMoveTiles()) > 0 ? 0 : 0x8000000 TargetIsInRange` — **déjà porté** avant cette tranche (`_dynamic_rule_leading_the_charge`), il MIGRE seulement de `DYNAMIC_TARGET_RULE_UNPORTED` vers une surcharge de la classe |

## 2. L'utilité **67** `LeadingTheCharge_ChargeTile`, nouvelle feuille

`IdunBattle.AI.Utilities.LeadingTheCharge_ChargeTileUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

```
free = battleQuery.<slot itf 0x52 = IBattleQuery 82 GetFreeAdjacentTiles>(case.position.MainTile)
if (free.Count > 0)  u += Fix64(free.Count) * GetUtilityValue("PreferAdjacentFreeTiles")
```

* le **slot 82** est LU dans `data/symbols/<build>/metadata/interface_slots.tsv` (arité 1, ce qui
  exclut les surcharges LISTE de `GetAdjacentTiles`, d'arité 4) ;
* la clé BC est RECOUPÉE avec `data/seed-bc.json` → `Utilities.Default.LeadingTheCharge_ChargeTile`
  = `{"PreferAdjacentFreeTiles": 5}` — une **donnée de BC**, jamais une constante de code ;
* l'ancre est la **tuile candidate**, pas le caster : c'est ce qui rend la feuille discriminante.

Sens de jeu : Dreir charge de préférence là où il restera le plus de place libre autour de lui —
parce que c'est là que ses Death Riders se poseront. La feuille vaut jusqu'à `6 × 5 = 30`, donc elle
**domine** le second terme du bucket (`MovementSuggestion` = `[Tile(7), TileDistance(34)]`, dont le
`TileDistance` plafonne à `|0.2|`).

⚠ `self_pos` est compté **OCCUPÉ** (`TileContentComponent$$IsEmpty` rend faux sur la tuile où le
caster se tient encore), et ce corps natif **ne le re-crédite pas** — contrairement à
`GeminaeSuperiaPlaybook`, qui a un `OwnerInAdjacentTile` explicite. Ne pas ajouter la compensation
par analogie.

## 3. Les DEUX fautes que seule la MESURE a trouvées

Les deux étaient **invisibles** de la tuile d'atterrissage ET de la séquence de la charge.

### 3.1 `nrOfSummons` lu sans le niveau — 2 Death Riders au lieu de 4

`ability_var(..., level=None)` retombe sur l'index 0 : `nrOfSummons[1] = 2`, alors que le runner
normalise à 50 → **4**. Le natif posait quatre `AddUnit`, le port deux. Ce qui l'a montré :
les tuiles natives de `AddUnit` (quatre) et **deux tirages manquants** (`PORT=8` contre `NATIF=10`).
Le total de la charge, lui, était déjà bit-exact — un critère sur lui serait resté vert.

### 3.2 Le seuil de `HasAdjacentEnemies` : lu `> 1` au décompilé, **RÉFUTÉ** — c'est `>= 1`

`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies` construit un trigger de classe
`DAT_1833d73e0` avec `(sel, Direct(1))`. Ghidra nomme son ctor
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$.ctor` — mais ce corps est **trivial**
(`+0x10 = selecteur ; +0x20 = minAmount`), donc **dédupliqué** entre `AmountIsGreater` et
`AmountIsEqualOrGreater`, dont `engine/entities/triggers.py` documente déjà le mislabel. Lu
naïvement, `AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend `minAmount < Count(sel)`, soit
« au moins DEUX ennemis adjacents » — ce qui contredit le nom.

**La mesure tranche** (R1, `MC1_67`) : le natif pose ses Death Riders sur
`[(6,7), (4,7), (6,6), (5,6)]`, et les **deux premières sont exactement les deux tuiles adjacentes**
à `necroWarden` (5,8) — alors qu'il n'y a **qu'un seul ennemi** sur le plateau. Avec `> 1` la formule
vaudrait 0 partout, le `SortByFormula` serait inerte, et l'ordre natif serait celui de
`SortTilesByUtilityForSummon` seul. Il ne l'est pas.

C'est `reference_ctor_name_is_not_class_identity` appliqué : **un nom de ctor n'identifie pas une
classe**, et ici le décompilé seul menait au mauvais opérateur.

## 4. Validation live — les quatre étages, deux régimes

`probe_508_leading_the_charge.py` (board `MC1_67`, seed 508, `--crit 0,0`). Positions **drivées** :
`astraDreir` (5,5), figurant `deathRotbone` (1,1) — sans lui le turn-start ennemi rend à la cible
les PV qu'on vient de lui prendre et le delta lu vaut un **faux zéro** (même piège que #504).

| étage | R1 (charge ouverte) | R2 (cible encerclée) |
|---|---|---|
| E0 `ported` | `True` | `True` |
| E1 tuile d'atterrissage | port `(5,7)` == natif `(5,7)` | port `(5,7)` == natif `(5,7)` |
| E2 delta HP | `16818` == `16818` | `{u81: 7345, u83: 4915, u85: 6944}` == natif |
| E2 séquence coup par coup | `[2554, 2376, 2415]` == natif | idem |
| E3 tuiles de summon | `[(6,7),(4,7),(6,6),(5,6)]` == natif, **même ordre** | `[(6,6),(4,6),(5,6)]` == natif, **3 tuiles pour 4 demandées** |
| E4 tirages `genrand_int32` | `10` == `10` | `10` == `10` |

R2 est le régime le plus riche : la cible n'a **qu'un** hex libre adjacent, donc la tuile
d'atterrissage est forcée ; les voisins libres de `(5,7)` ne sont que trois pour `nrOfSummons` = 4
(le `First` mord) ; et `(5,6)` — le seul des trois **sans** ennemi adjacent — sort **en dernier**,
donc le `SortByFormula` mord aussi. Les deux Death Riders y frappent des cibles **différentes**
(`u83` et `u85`), ce qu'un régime mono-cible ne montrerait pas.

Contre-épreuves hors-ligne (`--ab`, même capture, R1, 5 candidats) : `Tile(7)` seule rend `(6,8)`,
**≠** la réponse du bucket `(5,7)` — la définition d'utilité est donc discriminante.

## 5. Ce qui n'est PAS couvert

* ~~**Le terme `extraPierceRatio` n'a jamais été exercé non nul en live**~~ — **FERMÉ par #514.**
  Dans les deux régimes de cette fiche aucun allié de Dreir n'était mort, donc `GetExtraPierceRatio`
  rendait `0` (le natif le confirmait : `UnitStats_ExtraPierce_Modification=0`) : l'accord sur le
  dégât était obtenu dans un régime **dégénéré pour ce terme**. `probe_514_extra_pierce_cadavres.py`
  monte le cadavre (allié fragile + `endturn` + `aiturn`) et confronte : `ExtraPierce` port `10` ==
  natif `10`, séquence `[1212, 1399, 1125]` == natif, 13 tirages == 13 — et la contre-épreuve
  montre que le port d'AVANT #514 rendait `[970, 1119, 900]`, soit **−20 %**.
  Détail : `case-514-allunits-pool8.md`.
* **Les deux termes du bucket ne sont pas séparés** : sur R1, `MovementSuggestion` seule et
  `LeadingTheCharge_ChargeTile` seule rendent toutes deux `(5,7)`. Seule leur SOMME est confrontée.
* **`Fled` (UnitFlag 9)** de `HasBeenDefeated` n'a aucun producteur côté port — le terme est porté
  mais inerte.
* **`isHidden = 1`** (7ᵉ argument des deux `AddStaticStatModifierEffect`) n'est pas modélisé.
* **`ignoreFlags = 0`** de `GetPossibleMoveTiles` reste non exercé (résidu #381 : `unitFlags` n'a pas
  de substrat), mais il est propagé pour que 1204 et 1202 divergent le jour où il en aura un.
* ~~**`Cache(TimesAttackMadeThisTurn)` / `AmountIsGreater` collapsés sur « l'attaque a été
  émise »**~~ — **RÉSOLU par `#508-r1`** : le compteur `ActorStatisticsComponent+0x24` est porté
  (`components.register_attack_made` l'incrémente, `reset_units_attacked_this_turn` le remet à zéro
  — **lu à l'assembleur**, son nom ne le dit pas), et `LeadingTheCharge` compare désormais le
  compteur à lui-même. **Aucun changement observable sur 1204** (le collapse était structurellement
  équivalent sur cet arbre) ; ce qui change est que le nœud
  `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn` devient **réutilisable** par ses
  deux autres consommateurs natifs, `IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` et
  `LegacyOfCombatAbility$$CreateTrigger`, tous deux non portés faute de ce substrat.
  Détail et résidus ouverts (`#508-r2` : les variantes `rangeType` ; `#545-r1` : le seed live) :
  `docs/rl/case-545-composant-de-flags-vide.md` §4-5.

## 6. Le contrat de disjonction — cinq endroits, comptés PAR LE CODE

`TARGETING_OPTIONS_UNPORTED` (masque migré sur la classe, valeur **inchangée** : le snapshot du
volet 2 figeait `0x102004032`, et c'est exactement ce que porte `LeadingTheChargeAbility`) ;
`DYNAMIC_TARGET_RULE_UNPORTED` (la classe surcharge) ; `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` ;
les cardinalités de `test_270r1_volet2_dict_keys_enum_offline` ; et le compteur d'en-tête du bloc.
Ce dernier est **re-compté** par un balayage du littéral (`probe_508 --tables` pour les invariants,
le comptage par section étant fait à la main sur l'arbre résolu) : **26** entrées dans le bloc
(`9 / 4 / 1 / 4` puis `3 / 1 / 4`), **4** hors-bloc, **30** dans le dict entier.
