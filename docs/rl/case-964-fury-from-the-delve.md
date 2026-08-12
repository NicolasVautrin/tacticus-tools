# #964 — `FuryFromTheDelve` (1528) porté et confronté, `EcogSupport` (1487) RE complète

Deux passifs du roster **Leagues of Votann**, groupés parce qu'ils partagent le **même roster
injecté** (`catalog_inject.write_augmented_seed_bc`) — le harnais live se paie une fois. Le
premier est **livré et confronté bit-exact** ; le second est **RE complet, port replié sur
`#964-r1`** : son coût réel est d'une tranche entière (deux sélecteurs natifs à porter et un gate
de réparation à câbler), et un port partiel aurait déclaré une couverture inexistante.

---

## 1. `FuryFromTheDelve` — LIVRÉ

`TriggeredAbilityType` **0x5f8 = 1528**, passif de `votanBeserk` (HERO, **hors pool** → injection
catalogue). Classé **GAP-ABSENT** par `docs/rl/passive-ability-coverage.md` : aucune trace nulle
part, pas même en prose.

### 1.1 Trois corps natifs, lus verbatim sur `rnca9r7q6c`

UN nom de kit, **DEUX classes portées** — le `CreateTrigger` est une disjonction
`AbilityTrigger.op_BitwiseOr` et le `CreateBehaviour` se ventile sur son paramètre `triggerType`.
C'est la forme `LetTheGalaxyBurn` / `ThrillSeekers`.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryFromTheDelveAbility$$CreateTrigger` :

```
( On( 0x2a = PreUnitAbility, ownerNeedsToBeAlive: 1 )
    op_BitwiseAnd  IsNormalAttack
    op_BitwiseAnd  get_OwnerIsActor )
op_BitwiseOr
( On( 0x26 = NormalAttack, ownerNeedsToBeAlive: 1 )
    op_BitwiseAnd  get_OwnerIsActor
    op_BitwiseAnd  IsAlive( <DSLSelectors+0x60 = Target> ) )
```

`...FuryFromTheDelveAbility$$GetCheckTargetHealthBehaviour` (bras `PreUnitAbility`) :

```
DSLBehaviors.SetPersistentData(
    AbilityOrEffect(1528),
    unit  = <DSLSelectors+0x30 = Owner>,
    key   = DSLFormulas.Get("TARGET_HEALTH_ABOVE_HALF"),
    value = DSLTriggers.AmountIsGreater(
                DSLFormulas.StatAmount(Target, 0x5 = Health, 0x0 = StatPart.Current, null, 0),
                DSLFormulas.PercentageOf(
                    DSLFormulas.StatAmount(Target, 0x5 = Health, 0x2 = StatPart.Maximum, null, 0),
                    percentage   = GetNumberConstant(0x12 = hpPct),
                    roundingRule = 0 = RoundingRule.Default ) ) )
```

`...FuryFromTheDelveAbility$$CreateBehaviour` (bras `NormalAttack`) :

```
DSLBehaviors.If(
    DSLFormulas.GetPersistentData( AbilityOrEffect(1528), Owner, "TARGET_HEALTH_ABOVE_HALF" ),
    DSLBehaviors.AddEffect( 0x429 = 1065 Pinned, AbilityStateReference,
                            source = Owner, targets = Target,
                            turns  = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)) ),
    DSLBehaviors.AttackWithAttackDamage(
            caster = Owner, target = Target,
            amount = MinMaxDamage(abilityState), damageProfile = GetDamageProfile(),
            hits = GetHits(), abilityOrEffect = AbilityOrEffect(1528),
            options = <struct ZEROEE>, selectionType = 2 ) )
```

Gameconfig `passiveAbilities.FuryFromTheDelve` : `nrOfRounds = 1`, `hpPct = 50`, `nrOfHits = 2`,
`damageProfile = Eviscerate`, `attackRangeType = Melee`, variables `minDmg` / `maxDmg`.

**Lisible** : avant chaque attaque normale on MÉMORISE « la cible était-elle au-dessus de
`hpPct` % de ses PV max ? » ; après le coup on relit ce flag — cible saine → on la `Pinned`, cible
déjà entamée → attaque gratuite de `nrOfHits` coups. Le berserker achève les blessés.

### 1.2 Cinq lectures qui ne se devinent pas

1. **`If` est la surcharge `formula`, pas la surcharge `trigger`.** Tranché par l'ADRESSE du
   `call` (xrefs de `DSLBehaviors$$If` : `FuryFromTheDelveAbility$$CreateBehaviour` pointe la
   variante `formula:IdunBattle.DSL.IAmountFormula`, `ECogSupportAbility$$CreateBehaviour` la
   variante `abilityTrigger:IdunBattle.DSL.IAbilityTrigger`). Son corps enveloppe la formule dans
   **`DSLTriggers.AmountIsGreaterThanZero`** : le test est `> 0`, jamais `!= 0`. Les **trois**
   surcharges sont homonymes (la troisième prend un `ITargetsSelector`).
2. **`SetPersistentData` à valeur-TRIGGER écrit 1 ou 0.** La surcharge
   `value:IdunBattle.DSL.IAbilityTrigger` fabrique
   `DSLFormulas.ConditionalAmount(trigger, <DSLFormulas+0x20>, <DSLFormulas+0x18>)`, et
   `IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose `+0x18 = Direct(0)`, `+0x20 = Direct(1)`
   (`+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`). Le sac ne contient qu'un
   booléen, et le `> 0` du point 1 le relit exactement.
3. **Clé ABSENTE → la formule rend 0 → branche ELSE, donc l'ATTAQUE.**
   `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate` laisse le `out` de
   `TryGetPersistData` à `default(T)` sur clé absente. **Ne porter que le bras `NormalAttack`
   ferait donc partir l'attaque supplémentaire à TOUS les coups** — le bras `PreUnitAbility` est
   ce qui ARME le refus, pas un ornement. C'est la contre-épreuve `sans_bras_pre_attaque`.
4. **Il n'y a AUCUN `ClearPersistentData`** dans ce kit (contraste `LetTheGalaxyBurn_ResetAbility`,
   dont le clear est inconditionnel et vient après la lecture). Le flag est RÉÉCRIT à chaque
   `PreUnitAbility` d'attaque normale. Ajouter un clear « par hygiène » changerait le comportement.
5. **`StatPart` discrimine les deux `StatAmount`** : `0 = Current` contre `2 = Maximum`, même
   sélecteur, même `StatType`. Les confondre rend le prédicat `PV > hpPct % de PV`, donc
   **toujours vrai** pour `hpPct < 100` — l'attaque supplémentaire ne partirait jamais. Le port
   passe par `HealthComponent.get_stat_part`, foyer unique de cette ventilation (#572-r1).

⚠ Offsets `DSLSelectors` de ce build : `Owner` 0x30, `Caster` 0x48, `Target` 0x60, `Current` 0x68.

### 1.3 Face DÉCISION : ABSENTE, et c'est une mesure

`search_symbols_by_name("FuryFromTheDelve")` rend **six** symboles : les trois corps ci-dessus et
trois `IdunBattle.View.AbilityConfigs.Loki.FuryFromTheDelveVisuals*` (couche VUE). **Aucun
`*Playbook`, aucun `*NonOwnerPlaybook`** — ce passif n'a pas de face décision native. Rien à
inscrire dans `NON_OWNER_MOVE_PLAYBOOKS` / `NON_OWNER_ATTACK_PLAYBOOKS` : ce n'est pas un résidu,
c'est un résultat.

### 1.4 Critère de l'ÉMETTEUR : OUI pour les deux faces

| vecteur | émetteur porté | statut |
|---|---|---|
| `On(0x2a = PreUnitAbility)` | `dispatch/ability.py::pre_unit_ability_triggers` — les DEUX voies depuis #120, avec `ability_type` renseigné (c'est ce champ que lit `IsNormalAttack`) | **OUI** |
| `On(0x26 = NormalAttack)` | `dispatch/attack.py` — `ExecuteTriggerAbilities` en clôture d'attaque normale (même vecteur que `SpecialIssueCombiMelta`) | **OUI** |

Aucun *registered-but-dead* de ce côté.

### 1.5 Confrontation LIVE — bit-exact sur les deux bras

`scripts/python/probe_964_fury_from_the_delve.py`, board `MC1_67`, seed 777. Montage **écrit** :
deux cibles au MÊME maximum de PV forcé (4 000 000, pour qu'aucune ne meure du coup — sinon le
gate `IsAlive(Target)` fermerait et le bras 2 mesurerait un silence) et aux ratios opposés. **Le
seul discriminant des deux bras est ce ratio.** L'attendu est DÉRIVÉ du ratio mesuré au snapshot,
jamais supposé.

| régime | ratio PV | NATIF | PORT |
|---|---|---|---|
| blessé | 9,58 % | pas de `Pinned`, **6** coups `[6348, 2077, 1695, 1928, 2328, 2248]` | **identique** |
| sain | 99,86 % | `Pinned` posé, **4** coups `[1246, 1415, 1434, 1394]` | **identique** |

L'écart `6 − 4 = 2` **EST** `nrOfHits`. Les valeurs étant bit-exactes, le profil `Eviscerate`, les
bornes `minDmg`/`maxDmg` et la consommation RNG sont validés en même temps que la structure.

**Quatre contre-épreuves, chacune avec sa RÉCIPROQUE** (un régime où elle est inerte — une
mutation qui mord partout ne discrimine rien) :

| mutant | mord sur | inerte sur |
|---|---|---|
| `sans_bras_pre_attaque` | sain (le flag n'est plus écrit → attaque) | blessé |
| `statpart_confondus` | blessé (`Current`/`Maximum` confondus → jamais d'attaque) | sain |
| `comparaison_inversee` | les deux | — |
| `sans_bras_normal_attack` | les deux | — |

⚠ **DEUX pièges de montage mesurés, tous deux corrigés dans le probe :**

* **L'ORDRE des mesures est load-bearing.** Les mutants tournaient d'abord sur un état re-capturé
  APRÈS le passage du natif ; entre-temps la cible blessée remontait de **20 % à 59 %** de ses PV
  (soin/régénération adverses) et `statpart_confondus` cessait de mordre — plus aucun régime ne
  l'exerçait, et le probe rendait un `inerte` qui accusait le port au lieu du montage. Ils tournent
  désormais sur le **MÊME snapshot** que la mesure, et **la cible blessée passe en premier** (la
  saine, elle, reste au-dessus du seuil quoi qu'il arrive).
* **L'attaque NORMALE emprunte `AttackUnitMessage` → `DamageHandler`**, pas
  `ActiveAbilityMessage` → `AbilityHandler` : le port a DEUX portes pour l'unique site natif
  `InputMessageProcessor$$Visit(ActiveAbilityMessage)` (#120 / #429-r1-r3-r1). Le premier jet
  passait par la seconde et lisait `last = None` — un port **muet** qui se serait lu comme une
  divergence.

Garde offline : `tests/engine/test_964_fury_from_the_delve_offline.py`, **16 tests, 3,5 s** —
ordinaux ÉCRITS AUX SITES figés, les deux bras au registre et sur les bons vecteurs, le passif
ABSENT des registres d'ACTIVES (piège de namespace), les quatre constantes du gameconfig, le
porteur, la **polarité du seuil** (le cas `PV == hpPct % du max` vaut **FAUX** — comparaison
stricte, donc une cible pile à la moitié reçoit l'attaque), les deux `StatPart` réellement lues,
la source `Owner` de la feuille `Pinned`, et la clé persistante composite.

### 1.6 Ce que ce port n'établit PAS

* `selectionType = 2` (`UnitSelectionType.OnlyTargetable`, 9ᵉ argument d'`AttackWithAttackDamage`)
  n'est matérialisé par aucun étage du port — **résidu PARTAGÉ** par tous ses call-sites, ni créé
  ni aggravé ici.
* `options` = struct ZÉRO au call-site (5 qwords à 0, lus à l'assembleur) : ni `isForceOverkill`,
  ni `forceCrit`, ni `skipHitsModifiers`. C'est le défaut de la feuille portée.
* Le gate `!HasFlag(unit, 6 = Dead)` d'`AddEffectBehaviour$$Execute` est porté par le nœud
  `AddEffect` / `AddEffectOperation` partagé, pas ici.

---

## 2. `EcogSupport` — RE COMPLÈTE, port replié sur `#964-r1`

`TriggeredAbilityType` **0x5cf = 1487**, passif de `votanIronmaster` « Vynn » (HERO, hors pool).
Classé **ZONE-GRISE [R]** par l'audit, zone `playbook` : sa face DÉCISION **non-owner MOVE** est
déjà portée (#433-r4-r3, `ECogSupportPlaybookNonOwnerPlaybook`, poids
`EcogSupport_EcogAdjacentToParent` = 10). **La face COMBAT ne l'est pas** — c'est elle que ce
paragraphe documente intégralement.

### 2.1 Deux classes natives, lues verbatim

`...ECogSupport_InitAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit(0x5cf = 1487)`
`...ECogSupport_InitAbility$$CreateBehaviour` = `DSLBehaviors.AddFlag(Owner@+0x30, 0x18)`

**`UnitFlag 0x18 = 24 = CanRepairFullHealthUnits`** — résolu au dump (`frida/enums.tsv`), et l'i2
le confirme mot pour mot : « Vynn can repair other friendly units **even if they are at full
Health** ».

`...ECogSupportAbility$$CreateTrigger` = `On(0x30 = 48 UnitRepaired) & get_OwnerIsCaster`

`...ECogSupportAbility$$CreateBehaviour` (les trois helpers sont INLINÉS dans le corps ; ils
existent aussi comme méthodes nommées, dont les corps sont identiques) :

```
If( DSLTriggers.AmountIsGreater( DSLFormulas.ConfigConst(0x3c = maxSummons, config),
                                 DSLFormulas.Count( AlreadySummonedUnits() ) ),

    DSLBehaviors.Spawn( Owner@+0x30,
                        SummonTargetTile(),
                        GetStringConstant(0) = "votanSmnEcog",
                        SpawnUnitOptions.WithStatsFromConfig(config, abilityState, null, null) ),

    DSLBehaviors.PerformAIAbility( DSLSelectors.PickRandomly(GetPossibleTriggerRepairSummons(),
                                                             1, 0, int.MaxValue, false),
                                   <Func delegate>, 0, <DSLFormulas+0x18 = Direct(0)>, 0, 0 ) )
```

avec, tous trois lus séparément (`...ECogSupportAbility$$AlreadySummonedUnits`,
`$$GetPossibleTriggerRepairSummons`, `$$SummonTargetTile`) :

```
AlreadySummonedUnits()            = UnitsWithId( Children(Owner@+0x30),
                                                 GetStringConstant(0), 3 = OnlyAliveAndTargetable )

GetPossibleTriggerRepairSummons() = UnitsWithAnyValidTarget(
                                        UnitsWithId(Children(Owner@+0x30), unitId, 3)
                                          op_BitwiseAnd AdjacentFriends(Caster@+0x48, unique: 1, 3),
                                        UnitNormalRepairType( Current@+0x68 ) )

SummonTargetTile()                = PickRandomly( CanAddUnit(AdjacentTiles(Owner@+0x30)),
                                                  1, 0, int.MaxValue, false )
```

Gameconfig `passiveAbilities.EcogSupport` : `maxSummons = 3`, `unitId = "votanSmnEcog"`,
variables `summonHp` / `summonDmg` / `summonArmor`. i2 : « Whenever Vynn repairs a friendly unit,
he summons an E-COG in a free adjacent hex. Cannot have more than 3 E-COGs summoned this way at
the same time. […] if he repairs a friendly unit while 3 summoned E-COGs are already on the
battlefield, one random summoned E-COG adjacent to Vynn also performs a repair, if possible. »

Le texte et le décompilé **concordent branche par branche**, y compris le sens de l'`If` :
`AmountIsGreater(maxSummons, count)` ⇒ `then` = SPAWN, `else` = faire réparer un E-Cog existant.

### 2.2 Critère de l'ÉMETTEUR

| vecteur | émetteur porté | statut |
|---|---|---|
| `On(0x30 = 48 UnitRepaired)` | `runner/operations/repair.py` (`processor.<slot 0x51>`) | **OUI** |
| `OnOwnerSpecificAbilityInit(1487)` | vecteur d'INIT — **à vérifier**, aucun consommateur porté recensé | **à établir** |

### 2.3 Pourquoi le port est une tranche entière — ce qui manque, mesuré

Le vocabulaire DSL requis existe **presque** entièrement côté port : `Spawn`
(`runner/abilities/behaviours/summon.py`), `PerformAIAbility`
(`runner/abilities/behaviours/ai_control.py`), `SpawnUnitOptions.WithStatsFromConfig`,
`Children`, `UnitsWithId`, `AdjacentFriends`, `PickRandomly`, `CanAddUnit`, `AdjacentTiles`,
`AddFlag`. **Deux sélecteurs manquent**, et ils ne sont pas cosmétiques — ce sont eux qui
décident QUEL E-Cog peut réparer :

* **`UnitNormalRepairType(entitySelector)`** — le pendant REPAIR d'`UnitNormalAttackType`
  (`entities/formulas.py`), qui existe déjà et lit `ActiveAbilityComponent.NormalAttackType@0x28` ;
* **`UnitsWithAnyValidTarget(pool, abilitySelector)`** — filtre « cette unité a au moins une cible
  valide pour cette ability », donc un gate de ciblage complet appliqué unité par unité.

S'y ajoute le câblage du flag **`CanRepairFullHealthUnits`** : le poser sans que le gate de
réparation le LISE ne produit rien, et l'inscrire au registre déclarerait une couverture
inexistante — le foyer est `engine/runner/operations/repair.py` / `engine/runner/abilities/repair.py`.

**Un port partiel a donc été refusé délibérément.** Le volet `_InitAbility` seul (20 lignes) aurait
posé un flag que rien ne lit, et l'entrée `ABILITY_TRIGGERS["EcogSupport"]` aurait fait passer
l'audit de GAP à PORTÉ sans qu'aucun comportement ne change — exactement le « mensonge de
couverture » que `special_issue_combi_melta.py` refuse pour sa sœur `_InitAbility`.

### 2.4 Le montage live est écrit et rejouable

`probe_959_grim_efficiency_predictive_guidance.py` (#959) monte déjà le roster Votann par
`catalog_inject.write_augmented_seed_bc`. `votanIronmaster` y entre par la même voie ; le régime
déclenchant est une RÉPARATION par Vynn d'un allié `Mechanical` — `#433-r4-r3` l'a déjà observé
live (l'E-Cog apparaît, `squadId 112` en (2,0), `visualId` `votanNpc1Ecog`).

---

## 3. Ce qui a été établi sur les quatre passifs retirés du périmètre en cours de tranche

Le périmètre est passé de six à deux items par correction de l'orchestrateur. Ce qui avait été lu
avant, pour le successeur de chacun — **aucun décompilé de fond n'a été lu sur ces quatre-là**, ce
sont des lectures de recensement :

| passif | id | état mesuré |
|---|---|---|
| `RefusalToBeOutdone` | `TriggeredAbilityType` 1441 | GAP-MENTION. **Résidu `#522-r2` DÉJÀ OUVERT** et précis : après un cast de 1198 le caster porte côté natif `[1226, 1430, 1434, 1511]` et côté port `[1226, 1434]` — `RefusalToBeOutdone_ExtraDamage` (1430) et `_ExtraCritDamage` (1511) manquent. Symboles natifs : `...RefusalToBeOutdoneAbility$$CreateBehaviour` et `$$RecordHitBehaviour` (les deux appellent la surcharge `If(abilityTrigger)`). Point d'entrée : `docs/rl/case-522-euphoric-strikes.md` §6 |
| `WhisperingWeb` | `TriggeredAbilityType` 1554 (effet `EffectType.WhisperingWeb` = **1579**, ids DISJOINTS) | GAP-MENTION. ⚠ **Piège majeur** : `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector` est un corps DÉDUPLIQUÉ (`return Selectors@+0x30`) que ghidra étiquette sur **au moins six** effets d'autres factions (`deathwing`, `hunters_beyond_death`, `icon_of_obstinacy`, `martial_superiority`, `reinforced_hive_node`, `skullsmasher` le citent tous). Ne jamais conclure de ce nom que le sélecteur appartient à `WhisperingWeb` |
| `HealingBalms` | `TriggeredAbilityType` 1502 | ZONE-GRISE `ai, playbook, runner`. L'**ACTIVE** `1212 HealingBalms_Heal` est portée et confrontée (`engine/playbook/common.py::HealingBalms_HealPlaybook`, `case-27` tranche 4d) ; c'est le **PASSIF** qui ne l'est pas — `...HealingBalmsAbility$$CreateBehaviour` = `AddActiveAbility(0x4bc = 1212)`. ⚠ `TriggeredAbilityType 1502` et `EffectType 1502 = RitesOfMorkai` sont **deux objets différents** (le second est porté, `runner/operations/triggers/loki/rites_of_morkai.py`) — homonymie d'ordinal à trois faces, exactement le piège `HeavyGravCannon`. Porteur `spaceWolfPriest`, entré au pool par injection catalogue le 2026-07-29 |
| `WayOfTheShortBlade` | `TriggeredAbilityType` 1500 (effets `WayOfTheShortBlade_DamageBuff` 1499, `_AdditionalAttackMarker` 1500 — **même ordinal, autre enum**) | ZONE-GRISE `playbook`. Face DÉCISION **non-owner ATTACK portée** (`engine/playbook/non_owner_attack.py::WayOfTheShortBladeNonOwnerPlaybook`, clé `WayOfTheShortBlade_TauAdjacentToEnemy`). Face COMBAT non portée. Géométrie de l'effet **déjà LUE et consignée** par #418-r1 §2 mais NON INSCRITE : `SurroundingFriends(range = GetNumberConstant(0x16))` + `Owner`. Deux résidus adjacents la citent déjà : `#433-r4-r3-r1-r2` (sa face ATTACK non-owner, slot 1 de l'interface) et `#271-r8` (argmax natif non confronté) |
