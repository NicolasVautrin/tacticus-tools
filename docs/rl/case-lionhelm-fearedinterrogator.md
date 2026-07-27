# LionHelm (darkaAzrael) + FearedInterrogator (darkaAsmodai) — RE + port

Deux passifs classes **GAP-ABSENT** par `docs/rl/passive-ability-coverage.md` (items #23 et #10 de la
file dispatchable). **Les deux sont PORTES et VALIDES LIVE** (build `gqfc5mff6c`).

Canal de port : `ABILITY_INIT_OWNER_EFFECTS` (pose) + `EFFECT_CLASSES` (comportement) — **pas**
`ABILITY_TRIGGERS`. Le seul artefact natif de chaque ability est un `CreateBehaviour` DSL qui pose des
effets sur le PORTEUR a l'init ; leur `CreateTrigger` est le corps herite/deduplique
`On(AbilityInit) & OwnerIsActor` (meme famille qu'AnvilShield). Aucune des deux n'est une ability
ACTIVE -> aucune entree `ABILITY_CLASSES`, donc **pas de `TARGETING_OPTIONS` a poser**.

## 0. Piege de RE a retenir — `methods.tsv` est DEDUPE PAR ADRESSE

`data/symbols/<build>/frida/methods.tsv` compte **121 501 lignes pour 121 501 adresses distinctes,
0 doublon**, alors que le binaire fait de l'**identical code folding** : plusieurs methodes au corps
identique partagent une adresse et **une seule survit** dans la table.

- `LionHelm_ExtraDmgEffect.CreateTargetSelector` en est **ABSENT** — et il EXISTE.
- `LionHelm_ExtraBlockDamageEffect.CreateTargetSelector` y figure a la RVA `f4bf30`, que **ghidra
  nomme `PathOfCommandExtraDmgEffect$$CreateTargetSelector`** : les deux tables ne conservent pas le
  meme nom, ce qui PROUVE le partage de corps.

=> **L'absence d'un symbole dans `methods.tsv` n'est PAS une preuve d'absence de la methode.** Le
depart se lit sur la **VTABLE RUNTIME** : RPC `resolveVtableSlot` (read-only, `introspect.ts`), slot
`+0x538` = `CreateTargetSelector` (offset lu dans
`IdunBattle.Entities.Effects.BaseEffect$$CreateTargetSelectorAndCache`, qui fait
`(**(vtable+0x538))(this, *(vtable+0x540))`).

| classe d'effet | slot 0x538 | selecteur effectif |
|---|---|---|
| `LionHelm_ExtraDmgEffect` | `180f4bf30` | `SurroundingFriends(owner, ConfigConst(range))` |
| `LionHelm_ExtraBlockDamageEffect` | `180f4bf30` | idem (MEME corps) |
| `LionHelm_ExtraBlockChanceEffect` | `180f55cf0` | idem + `UnitsFromFaction(DarkAngels)` |
| `FearedInterrogator_OwnerEffect` | `180e03180` | **defaut** (le porteur seul, comme `SmashaEadEffect`) |
| `FearedInterrogator_TargetEffect` | `180f48cb0` | selecteur dedie (cf. §2) |

## 1. LionHelm — `TriggeredAbilityType` **1163** (0x48b), porteur `darkaAzrael` (HERO, dans le pool)

gameconfig : `variables = {extraDmg[65]=437, blockDmg[65]=582, blockChance[65]=20}`,
`constants = {range: 2}`, `variablesAffectedByRarityBonus = [extraDmg, blockDmg]`
(**`blockChance` n'est PAS scale par la rarete** — confirme live : +20 exact la ou `blockDmg` est
scale x1.8 sur le meme porteur).

i2 : « Friendly units within 2 hexes block an additional 582 Damage when they Block and deal +437
Damage with attacks triggered by Overwatch. Other friendly Dark Angels within 2 hexes also have their
Block chance increased by +20% »

### `LionHelmAbility$$CreateBehaviour` (mirror 1:1)

```
  AddEffect( EffectType.LionHelm_ExtraDmg = 1193, AbilityStateReference,
             targets = Owner@0x148, turns = null )
+ AddDynamicStatModifierEffect( Owner@0x148, EffectType.LionHelm_ExtraBlockChance = 1232,
                                StatType.BlockChance = 7, turns = null, isHidden = false )
+ AddDynamicStatModifierEffect( Owner@0x148, EffectType.LionHelm_ExtraBlockDamage = 1214,
                                StatType.BlockDamage = 8, turns = null, isHidden = false )
```

Les trois effets-entites vivent sur **AZRAEL** (verifie live : `decisionView` d'un runner frais liste
les 3 chez lui et RIEN chez ses allies) ; c'est leur `CreateTargetSelector` qui projette.

⚠ Qualification d'enum : `EffectType 1214 = LionHelm_ExtraBlockDamage` mais `ActiveAbilityType 1214 =
Hailstrike` ; `EffectType 1193 = LionHelm_ExtraDmg` mais `TriggeredAbilityType 1193 = SynapticInsight` ;
`EffectType 1232 = LionHelm_ExtraBlockChance` mais `TriggeredAbilityType 1232 = EnvDefenderHealthBuff`.

### Volet 1 — `LionHelm_ExtraDmgEffect` (1193), AURA de DEGAT

`.ctor` = `BaseEffect(AbilityOrEffect(LionHelm 1163), hasAutomaticActivation = true)`.
Selecteur = `SurroundingFriends(Owner, GetNumberConstant(0x16 = range) = 2, unique = true,
OnlyAliveAndTargetable)` — **self EXCLU, aucun filtre de faction**.

```
amount = ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@0x60 )
A      = HasEffect( Caster@0x160, EffectType.Overwatch_AutoAttack = 1009, false, Both )
         & IsOverwatchAttack()
B      = HasEffect( Caster@0x160, EffectType.GrimRetribution_CounterAttack = 1213, false, Both )
         & CurrentAbilityIs( AbilityOrEffect(TriggeredAbilityType.GrimRetribution = 1177) )
return   EffectBonus.ForAddition( get_OwnerIsCaster & (A | B), amount,
                                  source = AbilityOrEffect(LionHelm 1163) )
```

Canal PORT = `create_aura_attack_damage_bonus_for_ally` (additif PRE-percage PAR COUP, comme
`LordOfTheHost_ExtraDamage`). Le gate `IsOverwatchAttack` est le flag `is_overwatch` deja threade
jusqu'a `Hailstrike_ExtraPierce` ; il descend desormais aussi jusqu'au ctx d'aura
(`damage_ops.execute` -> `damage_model.attacker_modifiers` -> `_apply_ally_attack_damage_auras`).
Le conjoint `HasEffect(Caster, Overwatch_AutoAttack)` est STRUCTURELLEMENT satisfait cote port :
`is_overwatch=True` n'est pose que par le vecteur `Overwatch_AutoAttackEffect`.

**RESIDU FLAGGE — branche B** : elle exige l'effet `GrimRetribution_CounterAttack` (1213) ET
`CurrentAbilityIs(GrimRetribution 1177)`. Le passif `GrimRetribution` de `darkaHellblaster` n'est PAS
porte (GAP-ABSENT, item #13 de la file) -> l'ability 1177 n'existe pas offline : la branche ne peut ni
fire ni etre confrontee. A cabler AVEC GrimRetribution. Consequence = MANQUE possible, jamais un
sur-compte. (NB : l'effet 1213 EST bien present live sur Sarquael — mesure du 2026-07-27 — donc la
branche deviendra active des que GrimRetribution sera porte.)

### Volets 2 et 3 — les DEUX `ADynamicStatModifierEffect`, AURA STAT-MOD PROJETEE

`.ctor` commun : `ADynamicStatModifierEffect( AbilityOrEffect(LionHelm 1163), unitEffectType = null,
canBeImmuneTo = false, keepOnRevive = true, isMultiply = false )`.

| effet | selecteur | `GetDynamicStatModificationAmount` | stat |
|---|---|---|---|
| `_ExtraBlockDamage` (1214) | `SurroundingFriends(Owner, range=2, unique, OnlyAliveAndTargetable)` | `ConfigVar(LionHelm, EffectSource(effect), blockDmg = 20)` | `BlockDamage = 8` |
| `_ExtraBlockChance` (1232) | idem + `UnitsFromFaction(UnitFaction.DarkAngels = 10)` | `ConfigVar(LionHelm, EffectSource(effect), blockChance = 21)` | `BlockChance = 7` |

La magnitude s'indexe sur l'`AbilityState` de la **SOURCE** (`EffectSource`), jamais du buffe.

**Ce que la mesure live a REVELE** (`statModSources`, runner `MC1_67`, Azrael ablvl 50 / mult 180) :

```
darkaHellblaster (Dark Angels, dist 1)        blockChance +20 (source 97) . blockDamage +797 (source 98)
ultraApothecary  (Ultramarines, dist 1)       blockDamage +797 SEUL      -> le gate faction MORD
darkaTerminator  (Deep Strike, TeleportingIn) RIEN                       -> OnlyAliveAndTargetable MORD
darkaAzrael      (le porteur)                 RIEN                       -> SurroundingFriends exclut la source
```
`blockDmg[50] = 443 x 1.8 = 797` exact ; `blockChance[50] = 20` NON scale. Et l'aura est
**RE-EVALUEE A CHAQUE MOUVEMENT** (l'allie eloigne perd les +797, il les retrouve en revenant).

**Consequence de port** — la part est DEJA dans le `combatSnapshot` de la cible (elle est dans
`GetStat`), mais **non attribuee** : `UnitContext.from_snapshot` ne sait attribuer qu'aux effets
PORTES PAR CETTE UNITE, or l'effet vit sur le porteur de l'aura. Elle dormait donc dans
`CAPTURED_SOURCE` et **rien ne pouvait la retirer** quand la cible sortait du rayon. D'ou le module
neuf `engine/runner/operations/aura_stat_mods.py` :

- `attribute_aura_stat_modifiers(state)` — appele en fin de `snapshot.load_state` : deplace la part
  du residu opaque vers la cle de l'effet, **a somme constante** (`GetStat(Current)` inchange au seed,
  zero regression) ;
- `refresh_aura_stat_modifiers(state)` — appele par `MoveUnitOperation.execute` (mirror
  `UpdateEffectTargets`) : re-evalue le selecteur, applique/reverte.

Interface duck-typed (`getattr`, meme regime que `TARGETING_OPTIONS`) : `aura_stat_modification_stat`
/ `_amount` / `_targets`. **Aucun effet preexistant ne la porte -> les deux points de cablage sont des
no-op stricts hors porteur.**

## 2. FearedInterrogator — `TriggeredAbilityType` **1235** (0x4d3), porteur `darkaAsmodai` (HERO, pool)

gameconfig : `variables = {extraDmg[65]=728, extraHits[65]=2}`,
`variablesAffectedByRarityBonus = [extraDmg]` (**`extraHits` non scale**), pas de constants.

i2 : « Deals +728 Damage against enemies that are Suppressed, Stunned, or that are adjacent to another
friendly Dark Angel. Scores 2 additional hits if the enemy is also Chaos. »

### `FearedInterrogatorAbility$$CreateBehaviour` (mirror 1:1)

```
  AddEffect( EffectType.FearedInterrogator_Owner  = 1294, AbilityStateReference,
             source = Owner@0x148, targets = Owner@0x148, options = default )
& AddEffect( EffectType.FearedInterrogator_Target = 1295, AbilityStateReference,
             source = Owner@0x148, targets = Owner@0x148, options = default )
```

Verifie live : les DEUX sont chez `darkaAsmodai`, **AUCUN chez les ennemis marques**. Le marqueur
n'est donc PAS un effet a lire cote cible — c'est un SELECTEUR a re-evaluer.
`.ctor` commun (corps partage) = `BaseEffect(AbilityOrEffect(FearedInterrogator 1235), true)`.

### `FearedInterrogator_TargetEffect$$CreateTargetSelector` — le MARQUEUR

```
A       = ValidNormalAttackTargets( unit = Owner@0x148, unitTile = Tiles(Owner@0x148),
                                    range = null, ignoreRule = null, additionalRule = null )
friends = UnitsFromFaction( Friends(Owner, <all>@0x80, OnlyAliveAndTargetable),
                            UnitFaction.DarkAngels = 10, OnlyAliveAndTargetable ) - Owner@0x148
E       = EntitiesWithAnyEffect( A, [ EffectType.Stunned = 1162, EffectType.Pinned = 1065 ] )
B       = AdjacentUnits( friends, unique = true, OnlyAliveAndTargetable )
return    Unique( E + (A & B) )
```

- « Suppressed » de l'i2 = `EffectType.Pinned` (1065), le meme effet que pose SuppressiveFire (#74).
- Le texte i2 **TAIT** le gate `ValidNormalAttackTargets` : le marqueur ne se pose que sur des cibles
  d'attaque normale legales d'Asmodai. C'est un vrai gate du decompile.
- `- Owner` = « **ANOTHER** friendly Dark Angel ».

### `FearedInterrogator_OwnerEffect` — les deux bonus (selecteur DEFAUT = Asmodai seul)

```
CreateEffectDamageBonusForAttack :
    ForAddition( get_OwnerIsCaster & HasEffect(Target@0x178, 1295, false, Both),
                 ConfigVar(extraDmg = 8, GetAbilityState(this), config@0x60) )
CreateEffectHitsBonusForAttack :
    ForAddition( get_OwnerIsCaster & HasEffect(Target@0x178, 1295, false, Both)
                 & HasTrait(Target@0x178, UnitTrait 0x7ea = 2026 = grande-alliance Chaos),
                 ConfigVar(extraHits = 19, GetAbilityState(this), config@0x60) )
```

`get_OwnerIsCaster` est satisfait STRUCTURELLEMENT (ces hooks ne sont appeles que sur les effets de
l'ATTAQUANT). `HasEffect(Target, 1295, Both)` est re-evalue par
`damage_model.marked_effect_types_for_target` (interface duck-typed `marks_target`) et threade dans
les DEUX canaux (degat via `att_ctx`, coups via le `board` de `build_hits_board`), avec
`tgt_grand_alliance` pour le gate Chaos (derive de `GrandAllianceId`, comme RitesOfBattle/BeaconOfRage).

## 3. Validation live — 2 discriminants minimum par passif, dont un NEGATIF

| test | cas | resultat |
|---|---|---|
| `test_lion_helm_block_aura_live.py` | ami DA <=2 / ami non-DA <=2 / ami hors rayon / porteur | offline == live **a chaque etape** (seed, sortie de rayon, retour) ; gates faction + rayon + self prouves discriminants |
| `test_lion_helm_overwatch_aura_live.py` | Azrael dist 1 vs dist 11 de l'overwatcher | replay-diff **bit-exact des deux cotes** ; ecart in/out live == ecart offline == **749** (= extraDmg[50] x 1.8 x 1.25 HeavyWeapon) |
| `test_feared_interrogator_live.py` | NEG / POS_DMG (non-Chaos) / POS_HITS (Chaos) | replay-diff **bit-exact sur les 3** ; marqueur absent/present ; 4 coups sans Chaos vs 6 avec ; degat par coup strictement superieur quand marque |

Probes de mesure (versionnes) : `scripts/python/probe_lionhelm_block_aura.py`,
`probe_lionhelm_overwatch.py`, `probe_feared_interrogator.py`.

### Piege de mesure rencontre — un replay-diff RNG-DESALIGNE ment

Une premiere recette (teleports directs + `--hp-player` + `--no-ai`, overwatcher `darkaHellblaster`)
donnait un ecart in/out **live de 599** contre **749 offline**, ce qui suggerait que le natif
n'appliquerait PAS les %-modifiers a l'additif. C'etait **FAUX** : dans cette recette le replay
offline consommait un tirage MT different du live (fractions 0.899 vs 0.040 dans les DEUX
geometries), donc les valeurs absolues n'etaient pas comparables. Rejoue avec la recette
**prouvee alignee** de `test_overwatch_live.py` (approche pas-a-pas, `dumpRng` juste avant le pas
declencheur), le replay-diff est **bit-exact** et l'ecart vaut **749 des deux cotes** : le natif
multiplie bien l'additif par les %-modifiers, comme `LordOfTheHost`.
**Regle** : ne jamais conclure d'un ECART entre deux runs si le replay-diff de chaque run n'est pas
d'abord bit-exact.

## 4. Ce qui n'est PAS couvert

- **Branche B de `LionHelm_ExtraDmg`** (contre-attaque `GrimRetribution`) : residu flagge, non cablable
  tant que GrimRetribution n'est pas porte (cf. §1).
- **Face PREDICTION** : les gates cible (`marked_effect_types`, `tgt_grand_alliance`) et le flag
  `is_overwatch` sont threades sur la face COMBAT (runner). La face prediction/playbook ne les porte
  pas encore -> l'IA SOUS-ESTIME ces bonus (manque conservateur, jamais un sur-compte).
- **Aura stat-mod hors mouvement** : `refresh_aura_stat_modifiers` est cable au `MoveUnitOperation`
  (le selecteur est purement geometrique) et au seed. Un changement de cible du selecteur sans move
  (mort d'un allie, atterrissage d'un deep-strike) n'est pas re-evalue.
