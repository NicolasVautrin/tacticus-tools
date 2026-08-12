# case-959 — `GrimEfficiency` et `PredictiveGuidance` : les deux passifs d'AURA du roster Votann

Deux passifs, chacun le DERNIER item manquant de son kit. Même faction, même corps ICF de
`CreateTrigger`, deux canaux de port **différents** — et c'est l'écart qui porte la tranche.

| passif | id | porteur | pool | canal de port |
|---|---|---|---|---|
| `GrimEfficiency` | `TriggeredAbilityType` 1490 | `votanUthar` « Ûthar » | NON | aura **stat-mod projetée** (`runner/operations/aura_stat_mods.py`) |
| `PredictiveGuidance` | `TriggeredAbilityType` 1525 | `votanMemnyr` « Âmmuk » | NON | aura **dégât** (`create_aura_defense_damage_malus_for_ally`) + aura **coups** (`create_aura_hits_malus_for_defense`) |

Hors pool ≠ non confrontable : `catalog_inject` les amène (case-92 §6), et les deux entrent en
bataille avec leur kit complet. Aucun des deux ne figure dans un `data/unspawnable_rank<N>.json` —
il n'en existe aucun dans le dépôt.

## 1. Recensement au bloc `methodPointers` — slots totaux / corps propres

Les `CreateTargetSelector` des deux effets `GrimEfficiency_*` sont **ABSENTS de
`ghidra/functions.tsv`** : leur corps est dédupliqué par l'ICF. Conclure « pas de sélecteur » de
cette absence aurait été le faux négatif classique. Le bloc `methodPointers` du PE, lui, les
montre — les méthodes d'un même type y sont contiguës, dans l'ordre de déclaration.

| classe | base (LUE dans `frida/classes.tsv`) | slots | corps propres | corps FONDUS |
|---|---|---|---|---|
| `GrimEfficiencyAbility` | `BaseTriggeredAbility` | 3 | 1 | `CreateTrigger` → `WayOfTheShortBlade_InitAbility$$CreateTrigger` ; `.ctor` trivial |
| `GrimEfficiency_ExtraArmorEffect` | `DynamicStatModifierEffect` | 3 | 2 | `CreateTargetSelector` → `LionHelm_ExtraBlockDamageEffect$$CreateTargetSelector` |
| `GrimEfficiency_ExtraPierceEffect` | `DynamicStatModifierEffect` | 3 | 2 | idem — **le même corps**, donc la même aura |
| `PredictiveGuidanceAbility` | `BaseTriggeredAbility` | 3 | 1 | `CreateTrigger` → **le même** `WayOfTheShortBlade_InitAbility$$CreateTrigger` ; `.ctor` trivial |
| `PredictiveGuidance_MeleeEffect` | `BaseEffect` | 6 | 4 | `.ctor` (partagé par les trois) ; `CreateActiveCondition` → `WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition` |
| `PredictiveGuidance_RangedEffect` | `BaseEffect` | 4 | 2 | idem |
| `PredictiveGuidance_ExtraHitsEffect` | `BaseEffect` | 4 | 2 | idem |

**Total : `GrimEfficiency` 9 slots / 5 corps propres ; `PredictiveGuidance` 17 slots / 9 corps
propres.** S'y ajoute `GrimEfficiencyPlaybook` (face DÉCISION, hors tranche — cf. §6).

**L'événement du trigger a-t-il un émetteur côté port ?** Oui, et c'est un **registre**, pas un
arbre : `OnOwnerSpecificAbilityInit(this.AbilityType)` est le corps d'INIT que le port rend par
`ABILITY_INIT_OWNER_EFFECTS`. `DSLTriggers.OnOwnerSpecificAbilityInit` n'existe pas comme nœud
Python — aucun passif de ce patron n'en a besoin.

**Rien n'était déjà porté.** Balayage exhaustif de `engine/**` et `tests/**` : cinq sites, tous
DÉCLARATIFS (les membres d'enum), zéro classe, zéro entrée de registre, zéro playbook.

## 2. `GrimEfficiency` — deux auras qui PARTITIONNENT les stances

```
GrimEfficiencyAbility$$CreateBehaviour
  = AddDynamicStatModifierEffectToOwner( 0x5cf = 1487 GrimEfficiency_ExtraArmor,
                                         statType = 0x10 = 16 FixedArmor,  turns = null, isHidden = false )
  & AddDynamicStatModifierEffectToOwner( 0x5d0 = 1488 GrimEfficiency_ExtraPierce,
                                         statType = 0x1a = 26 ExtraPierce, turns = null, isHidden = false )
```

Le **`statType` vient du BEHAVIOUR**, la **magnitude du `.ctor` de l'effet** — deux étages qu'il
ne faut pas confondre : `0x10` n'est pas un `AbilityVariableType`.

Les deux `.ctor` sont relus **à l'assembleur** (le pseudo-C perd le littéral, il part par `edx`) :

```
GrimEfficiency_ExtraArmorEffect$$.ctor  : mov edx,0x5d2 | mov r8d,0x1b | xor r9d,r9d | mov byte [rsp+0x20],0
GrimEfficiency_ExtraPierceEffect$$.ctor : mov edx,0x5d2 | mov r8d,0x3f | xor r9d,r9d | mov byte [rsp+0x20],0
  => DynamicStatModifierEffect( AbilityType.op_Implicit(0x5d2 = 1490), <var>, isNegative = false,
                                canBeImmuneTo = false )
```

La surcharge d'`op_Implicit` est tranchée par l'**adresse réelle du `call`**
(`IdunBattle.Core.AbilityType$$op_Implicit(triggeredAbility: TriggeredAbilityType)`), jamais par le
nom : `AbilityType` en porte deux, et `ActiveAbilityType 1490` nomme autre chose.

Magnitude (corps GÉNÉRIQUE `DynamicStatModifierEffect$$GetDynamicStatModificationAmount`) :
`ConfigVar(<abilityType>, EffectSource(Get(effect)), <variableType>)` — indexée sur l'`AbilityState`
de la **SOURCE**, jamais du buffé. Même structure que `LionHelm_ExtraBlockDamage`.

**Sélecteur** — corps ICF partagé avec `LionHelm_ExtraBlockDamageEffect$$CreateTargetSelector` :
`SurroundingFriends(Owner@+0x30, GetNumberConstant(config, 0x16 = range), true, 3)`. Le porteur est
**exclu** (`SurroundingTiles − Tiles(self)`, aucun `op_Addition Owner`) — l'i2 le corrobore
(« **Other** friendly units within 2 hexes »). Le brief prévenait qu'un `CreateTargetSelector`
fondu peut rendre `Owner` : **ici c'est l'autre cas**, l'aura partagée. Le slot a été LU.

**Condition active** — corps PROPRES et DIFFÉRENTS, c'est tout le passif :

```
_ExtraArmorEffect$$CreateActiveCondition  = HasEffect( EffectSource(Effect@+0x38),
      0x5c7 = 1479 PrioritisedEfficiency_HostileAcquisition_Stance, onlyActive = false, 6 = Both )
_ExtraPierceEffect$$CreateActiveCondition = idem avec 0x5c8 = 1480 ..._FortifyTakeover_Stance
```

### Le piège de cette moitié, et le cran qui le ferme

La pose/bascule des stances vit dans `APrioritisedEfficiencyAbility$$GetSet*StanceBehaviour`, qui
dépend du substrat PERSISTENT-DATA **absent du port** (résidu #121). Les stances sont donc
**seedées depuis l'état live capté**, jamais posées offline.

Conséquence mesurée : le canal `decisionView.effects` est ACTIF-ONLY, donc il publie **une seule**
des deux auras. Le seed `ABILITY_INIT_OWNER_EFFECTS` matérialise l'autre avec `active = True` par
défaut — et sans contre-mesure, **les deux auras s'appliqueraient ensemble**.

Trois pièces ferment ce trou, et la troisième manquait :

1. `is_active` **portée** sur le socle — `has_effect_on(source, <stance>)`, le callable de
   `UnitEffectStateView` qui mirroire exactement `HasEffect(sel, et, onlyActive: null, 6)` ;
2. `active_condition_ported = True` — le flag capté d'une instance SEEDÉE est périmé par
   construction ;
3. `aura_stat_mods._aura_carriers` lit **désormais les deux** : le flag capté **et** la condition
   portée. Le natif ne connaît qu'une activité — il la RECALCULE à chaque refresh ; le port, lui,
   hérite d'un flag figé au seed.

La pièce 3 est un **no-op strict** pour les porteurs préexistants : aucun effet à projection
stat-mod (`LionHelm_ExtraBlock*`, `PathOfCommand_ExtraCrit`, `KustomForceFieldReworked[_Orks]`) ne
surcharge `is_active`.

Le mutant **M1** du probe l'établit : `is_active` neutralisée ⇒ `extraPierce +20` apparaît sur les
deux bénéficiaires que le natif laisse à `0`. Le sur-compte n'est pas redouté, il est **mesuré**.

## 3. `PredictiveGuidance` — trois effets, QUATRE écarts entre eux

```
PredictiveGuidanceAbility$$CreateBehaviour
  = AddEffect( 0x5ff = 1535 _Melee,     AbilityStateReference, source = Owner, targets = Owner, default )
  & AddEffect( 0x600 = 1536 _Ranged,    ... )
  & AddEffect( 0x601 = 1537 _ExtraHits, ... )
```

`targets = Owner` : les trois effets-entités vivent **sur Âmmuk**, pas sur les ennemis. Leur
`CreateTargetSelector` désigne les entités AFFECTÉES, qui ne portent aucune instance — même régime
que `FearedInterrogator_Target`. **Vérifié live : les deux ennemis en portent zéro.**

`.ctor` (UN seul corps ICF pour les trois, relu à l'assembleur : `mov edx,0x5f5` + `mov r8b,1` +
`call AbilityOrEffect$$op_Implicit(triggeredAbility)`) = `BaseEffect(AbilityOrEffect(1525),
hasAutomaticActivation = true)`. `CreateActiveCondition` = `<DSLTriggers+0x40>`, le trigger
constant VRAI que `DSLTriggers$$.ctor` met en cache (son `op_LogicalNot` occupe `+0x48`) → toujours
actifs, donc toujours captés : **aucun `is_active` à porter de ce côté**.

```
<aura> = _MeleeEffect$$AffectUnitsInRange(dsl, config)          -- helper STATIQUE partagé
       = SurroundingEnemies( Owner@+0x30, ConfigConst(0x16 = range, config), true, 3 )

_MeleeEffect$$CreateTargetSelector     = UnitsWithoutFlag( <aura>, 0 = UnitFlag.Moved, 3 )
_RangedEffect$$CreateTargetSelector    = UnitsWithFlag(    <aura>, 0 = UnitFlag.Moved, 3 )
_ExtraHitsEffect$$CreateTargetSelector = <aura>                          -- AUCUN filtre

_MeleeEffect$$BonusCondition(dsl)      -- helper STATIQUE, appelé par les DEUX corps de dégât
  = !AreEqual( EffectSource(Effect@+0x38), Caster@+0x48 )
  & ( IsMechanical( Caster@+0x48, 0 = Any ) | HasFaction( Caster@+0x48, 0x14 = LeaguesOfVotann, 3 ) )

_MeleeEffect$$CreateEffectDamageBonusForAttack
  = ForAddition( get_OwnerIsTarget & IsMeleeAttack  & BonusCondition(dsl), ConfigVar(0x08 = extraDmg) )
_RangedEffect$$CreateEffectDamageBonusForAttack
  = ForAddition( get_OwnerIsTarget & IsRangedAttack & BonusCondition(dsl), ConfigVar(0x09 = extraDmg_2) )
_ExtraHitsEffect$$CreateEffectHitsBonusForAttack
  = ForAddition( get_OwnerIsTarget & HasFaction(Caster, LeaguesOfVotann, 3)
                                   & !AreEqual(EffectSource, Caster),      ConfigConst(0x64 = extraHits) )
```

**Les quatre écarts, tous LUS — une recopie d'une moitié sur l'autre les aurait tous effacés :**

1. le filtre `UnitFlag.Moved` : **absent / présent / inversé** selon l'effet ;
2. `extraDmg` (`0x08`) contre `extraDmg_2` (`0x09`) : deux clés distinctes du gameconfig, qui
   portent aujourd'hui **les mêmes valeurs**. Lire le littéral et non la valeur est ce qui
   survivra à un rééquilibrage ;
3. `ExtraHits` **n'a pas** le membre `IsMechanical` — il est réservé aux Leagues of Votann, ce que
   l'i2 dit explicitement. Un attaquant Mechanical non-LoV reçoit le **dégât** et **pas** le coup ;
4. `ExtraHits` lit une **constante** (`ConfigConst`), les deux autres une **variable de niveau**
   (`ConfigVar`) — accesseurs différents, donc sections différentes du gameconfig.

### Pourquoi le canal du port est celui de la CIBLE

`get_OwnerIsTarget` : le natif boucle « effets actifs du board × CIBLES de l'effet » et écrit
`AbilityEntities+0x18 (Owner) ← la cible de l'effet`
(`EffectsQuery$$GetActiveEffectsWithBonuses`). Le nœud signifie donc « la cible de l'effet EST la
cible du coup ». Côté port, ce sont les deux boucles state-wide où le porteur est une **autre**
unité que la cible : `aura_defense_damage_malus_from_units` (axe DÉGÂT) et
`aura_hits_malus_for_defense` (axe COUPS).

`AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` : le natif n'implémente pas le slot `0x1a` mais le
slot `0x16`, donc sa contribution atterrit dans `attackModifiers` — ce qui décide du nombre
d'arrondis `Fix64.Round` en aval (#437-r1-r1-r1). Même régime que
`DaughterOfTheAbyss_ExtraDamagePct`.

**Deux clés ont été ajoutées au ctx du canal aura-DÉFENSE, sur les DEUX faces** (combat et
prédiction, mêmes noms, mêmes résolveurs — pas de fork) : `att_faction` (le second membre du
`op_BitwiseOr`) et `tgt_has_moved` (le nœud de flag, qui porte sur la CIBLE). Le canal COUPS, lui,
reçoit déjà le `board` complet des deux côtés : aucun élargissement n'y a été nécessaire.

## 4. Ce que la mesure LIVE a établi

Montage sur `MC1_67`, **géométrie calculée puis assertionnée** (`--place` / `--a-place`), régime
fabriqué AU SEED — aucun tour joué :

```
U = votanUthar  (0,0)   source GrimEfficiency ; attaquant Leagues of Votann pour l'autre aura
M = votanMemnyr (0,2)   source PredictiveGuidance                    d(U,M) = 2
C = ultraTitus  (1,2)   d(U,C) = 2 ; NI LoV NI Mechanical  -> témoin de FACTION
D = ultraCalgar (4,0)   d(U,D) = 4                          -> témoin GÉOMÉTRIQUE
E = orksNob     (0,1)   d(M,E) = 1  DANS l'aura d'Âmmuk ;  d(U,E) = 1
F = orksNob     (1,0)   d(M,F) = 3  HORS de l'aura      ;  d(U,F) = 1
```

E et F sont **deux clones du même id, tous deux adjacents à Ûthar** : le seul discriminant entre
les deux bras est l'appartenance à l'aura. C'est ce qui rend l'écart attribuable.

**Étage 2 — le canal.** Ûthar en stance `HostileAcquisition` publie `GrimEfficiency_ExtraArmor` et
**PAS** `_ExtraPierce` : la partition des stances est mesurée, pas supposée. Âmmuk porte les trois
effets ; les ennemis en portent zéro.

**Étage 3 — aura stat-mod, 12 lignes, 0 écart :**

| unité | d(Ûthar) | FixedArmor natif | port |
|---|---|---|---|
| Ûthar (SOURCE) | 0 | **0** — le porteur est exclu | 0 |
| Âmmuk | 2 | **+599** | +599 |
| Titus | 2 | **+599** | +599 |
| Calgar | 4 | **0** | 0 |
| les deux ennemis | — | **0** | 0 |

Décomposition du 599, par étage et sans rien fitter : `extraArmor[50] = 333` ×
`ability_variables_multiplier = 180 %` = 599,4 → **599**. `extraArmor` est la **seule** entrée de
`variablesAffectedByRarityBonus` de cette ability ; `extraPierceRatio` n'y est pas, et vaut donc 20
brut.

**Étage 4 — prédiction, 21 tuiles candidates, 0 écart**, oracle
`decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` :

| attaquant | vs E (dans l'aura) | vs F (hors aura) | verdict |
|---|---|---|---|
| Ûthar (LoV, ≠ source) | **7876 – 10040** | 3720 – 5577 | le bonus MORD, 3/3 paires |
| Âmmuk (la SOURCE) | 25 – 1066 | 25 – 1066 | `!AreEqual(EffectSource, Caster)` mord |
| Titus (ni LoV ni Mechanical) | 1672 – 3888 | 1672 – 3888 | le gate de FACTION mord |
| Calgar (idem) | 1800 – 2698 | 1800 – 2698 | idem |

Les trois assertions de non-dégénérescence sont aussi importantes que l'accord : sans elles, un
port qui n'appliquerait **rien** passerait.

Décomposition du 7876 par les mutants (chacun sur son bras) : sans `_Melee` → 4960 ; sans
`_ExtraHits` → 5907 ; hors aura → 3720 sur 3 coups, soit 1240/coup. `4 × 1240 = 4960` (le coup
supplémentaire seul) et `4 × 1969 = 7876` (avec le bonus par coup). Le port reproduit **les deux
bras** : les étages concordent un par un.

**Étage 5 — les sept mutants sont ROUGES, 7/7.** M1 `is_active` neutralisée · M2 stances échangées
· M3 `StatType` faux · M4 sans `_Melee` · M5 sans `_ExtraHits` · M6 filtre `Moved` inversé · M7
gate de faction neutralisé. Un mutant vert aurait dit que le témoin est aveugle.

## 5. Ce qui N'EST PAS couvert, avec la raison mesurée

* **`PredictiveGuidance_Ranged` n'a pas été exercé LIVE.** Son sélecteur est
  `UnitsWithFlag(Moved)`, et **aucune unité n'a bougé** dans un régime fabriqué au seed — c'est le
  prix, assumé, de « fabriquer le régime au seed plutôt qu'en jouant des tours ». Il est couvert
  OFFLINE (les deux sens du flag, plus le tri-état `None`), et son unique différence structurelle
  avec `_Melee` (déjà confronté live) est la clé de config et le sens du filtre — les deux figés
  par test. Pour le confronter live il faudrait jouer un tour adverse, ce qui déplacerait aussi les
  distances du montage.
* **La face DÉCISION de `GrimEfficiency`** — `GrimEfficiencyPlaybook$$CalculateMovementUtilityInStepsInternal`
  (= `getUtilityVal(<clé>) × Count(SurroundingFriends(GetNumberConstant(0x16))))`, clé
  `"GrimEfficiency_FriendsInRange"` présente dans `metadata/string_literals.tsv`, playbook actif
  dans `metadata/active_playbook_builders.tsv`). **Non portée** — résidu `#959-r1`.
  `PredictiveGuidance` n'a **aucun** playbook, ce qui est un résultat et non un manque.
* **Le cycle de vie des stances** reste le résidu #121 : rien dans cette tranche ne le change, et
  `is_active` le **lit** au lieu de le supposer.
* **`canBeImmuneTo = false`** est lu au `.ctor` des deux `GrimEfficiency_*` mais n'a aucun
  observable dans le montage (aucun porteur `Immune` à portée).

## 6. Résidu ouvert

* `#959-r1` — face DÉCISION de `GrimEfficiency` (`GrimEfficiencyPlaybook`).
