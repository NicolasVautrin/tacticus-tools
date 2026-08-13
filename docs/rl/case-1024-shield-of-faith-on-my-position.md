# #1024 — `ShieldOfFaith` et `OnMyPosition` : les deux arbres sont LUS et CONFRONTÉS, aucun n'est PORTÉ

**Verdict** : les deux mythiques sont montées en live pour la première fois, leurs arbres DSL sont
mirrorés au décompilé et **exercés étage par étage avec des contre-épreuves qui séparent**. Aucune
des deux n'entre au port : leur gate commun est `HasRarity(·, Mythic)`, et le port n'a **aucun canal
de rareté** — résidus `#1024-r1` / `#1024-r2`, mêmes murs que `#999-r3` et `#477-r43`.

Ce qui change par rapport à ces deux fiches : **le mur n'est plus au montage, il est au capteur, et
c'est mesuré** — `BC.Units[].Rarity` atteint bel et bien `BaseUnitComponent.Rarity` (§4).

---

## 1. `ShieldOfFaith` — `TriggeredAbilityType` 1453, porteur `adeptExorcist` (MoW)

i2 `Abilities/ShieldOfFaith_CurrentLevelDescription` :
> When a friendly **Mythic** character **Crits** or attacks an enemy that is on a hex with **Fire**,
> it gains a **Shield** until the start of its next turn, **unless it already has a shield**. The
> shield's Health is **{shieldPct}%** of the affected character's maximum Health.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ShieldOfFaithAbility` dérive de
`BaseTriggeredAbility` et surcharge `CreateTrigger`, `CreateBehaviour`, `get_AllowInAtomicMode`.

### `...ShieldOfFaithAbility$$CreateTrigger`

```
  ( On(EventTriggerType.PreAttack = 5, true)
    & IsUnitOnTileWithEffect(Target@DSLSelectors+0x60, new EffectType[]{ EffectType.Fire = 5 }) )
| ( On(EventTriggerType.Attack = 9, true) & WasCrit() )
& IsUnit(Attacker)
& AreFriends(Owner@+0x30, Attacker, comparisonType: 0, anyEntity: false)
& HasRarity(Attacker, UnitRarity.Mythic = 5)
```

`Attacker` = `IdunBattleLogic.Entities.DSLSelectors$$Attacker` (sélecteur CONDITIONNEL, cf. `#523-r4`).
Le tableau d'`EffectType` est bâti à l'assembleur (`Array.New(klass, 1)`, borne vérifiée, puis
`elem[0] = 5`) — ce n'est pas un scalaire boxé.

### `...ShieldOfFaithAbility$$CreateBehaviour(abilityState, triggerType)`

```
triggerType != EventTriggerType.Custom (0x20)
    -> TriggerAbilityDelayed(entity: Owner@+0x30,
                             triggeredAbilityType: <this+0x10> = TriggeredAbilityType.ShieldOfFaith,
                             unitSelectionType: UnitSelectionType.OnlyAliveAndTargetable = 3)

triggerType == EventTriggerType.Custom (0x20)
    -> If( IsAlive(Attacker)
           & AmountIsZero(CurrentShieldAmount(Attacker,
                              selectionType: UnitSelectionType.OnlyAliveAndTargetable = 3)),
           CreateShield(Attacker,
                        PercentageOf( StatAmount(Attacker, StatType.Health = 5,
                                                 StatPart.Maximum = 2),
                                      ConfigVar(AbilityVariableType.shieldPct = 0x96,
                                                abilityState, <this+0x20>) ),
                        <AbilityOrEffect source>, TurnsFromRounds(1), null, true) )
```

**L'ability se re-déclenche elle-même** : les vecteurs `PreAttack`/`Attack` ne posent rien, ils
programment un `TriggerAbilityDelayed` qui revient en `EventTriggerType.Custom`, et c'est ce
second passage qui pose le bouclier. Un port qui câblerait le behaviour directement sur `Attack`
aurait le bon effet observable et le mauvais ORDRE (le bouclier arriverait **avant** la résolution
des dégâts au lieu d'après).

`AbilityVariableType 0x96 = shieldPct` n'est pas déduit du nom : il est **recoupé** par
`catalog_inject.synthesize_ability("ShieldOfFaith")`, dont
`VariablesAffectedByUnitRarityMultiplier == [150]`.

---

## 2. `OnMyPosition` — `TriggeredAbilityType` 1452, porteur `astraOrdnanceBattery` (MoW)

i2 `Abilities/OnMyPosition_CurrentLevelDescription` :
> Enemies that are adjacent to a friendly **Cadian Guardsman** or a friendly **Mythic character**
> take **+{extraDmgPct}% Damage** from ranged attacks by mythic characters.

`...Triggered.Loki.OnMyPositionAbility` dérive d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`
et ne surcharge **que** `GetEffectType` → `return 0x5a4` = `EffectType.OnMyPosition_ExtraDamagePct`
(1444). Le trigger et le behaviour sont ceux de la base :

```
CreateTrigger   : OnOwnerSpecificAbilityInit(<this+0x10> = TriggeredAbilityType.OnMyPosition)
CreateBehaviour : If( <slot 0x368 = CreateCondition>(abilityState),
                      AddEffect(<slot 0x378 = GetEffectType>(), AbilityState(Owner, …),
                                Owner@+0x30, Owner@+0x30, <durée par défaut>) )
```

et `AOwnerEffectTriggeredAbility$$CreateCondition` rend `DSLTriggers+0x70` (la condition TOUJOURS
VRAIE partagée). Même patron que `CabalOfSorcerers` (`case-999` §7).

### `...OnMyPosition_ExtraDamagePctEffect$$CreateTargetSelector` — l'AURA

```
Enemies(of: Owner@+0x30,
        AdjacentUnits(
              Friends(of: Owner@+0x30,
                      UnitsWithVisualId(VisualUnitIdFromUnitId(Get(GetStringConstant(
                              AbilityConstantType.unitId = 0) )),
                                        UnitSelectionType.OnlyAlive = 1))
            + UnitsWithRarity(Friends(of: Owner@+0x30,
                                      HeroUnits(<DSLSelectors+0x20 = toutes les unités>, 3)),
                              UnitRarity.Mythic = 5, 3),
            unique: true, 3),
        3)
```

`HeroUnits` n'est pas une primitive : `IdunBattleLogic.Entities.DSLSelectors$$HeroUnits(entities,
selectionType)` est **littéralement** `UnitsWithTrait(entities, UnitTrait.Hero = 0x10, selectionType)`.
La constante `unitId` du gameconfig vaut `astraSmnGuardsman`, dont le `visualId` est
`astraNpc1Guardsman` — c'est le SUMMON de garde impérial, pas une unité de roster.

### `...OnMyPosition_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` — le BONUS

```
EffectBonus.ForPercentIncrease(
    get_OwnerIsTarget
      & AreFriends(Caster@+0x48, EffectSource(Effect@+0x38), comparisonType: 0, anyEntity: false)
      & HasRarity(Caster@+0x48, UnitRarity.Mythic = 5)
      & IsRangedAttack(),
    ConfigVar(AbilityVariableType.extraDmgPct = 0xa, GetAbilityState(), <effect+0x60>))
```

`AbilityVariableType 0xa = extraDmgPct` est recoupé de même
(`synthesize_ability("OnMyPosition").VariablesAffectedByUnitRarityMultiplier == [10]`).

---

## 3. Ce que le live a rendu — sept bras, cinq contre-épreuves

`probe_1024_shield_of_faith_live.py` · `probe_1024_on_my_position_live.py`. Board `MC1_67`
(7×9, tout Grass), seed 777, géométrie **pilotée** par `--place` / `--a-place`, jamais subie.

### `ShieldOfFaith` — attaquant `adeptRetributor` (hpMax **7530**), `--crit 100,700`

| bras | bouclier posé | lecture |
|---|---|---|
| mythique **L4** (`shieldPct` 50) | **3765**, `remaining` 2 | `50 % × 7530 = 3765.0` — écart **0** |
| mythique **L3** (40) | **3012** | `40 % × 7530 = 3012.0` — écart **0** |
| mythique **L1** (25) | **1882** | `25 % × 7530 = 1882.5` → **1882** |
| mythique **L2** (32.5) | **AUCUN** (2 fois) | anomalie de MONTAGE, §5 |
| mythique **L2**, palier tronqué à `"32"` | **2410** | `32 % × 7530 = 2409.6` → **2410** |
| `sans-mythique` | aucun | l'ability est bien la SOURCE du bouclier |
| `sans-crit` (`--crit 0,0`) | aucun | le gate `WasCrit` est EXERCÉ |
| attaquant `Rarity=4` | aucun, et `ShieldOfFaith` **absent des events** | le gate `HasRarity` est EXERCÉ |

**Arrondi** : `2409.6 → 2410` écarte le plancher ; `1882.5 → 1882` écarte l'arrondi-au-loin. C'est
compatible avec `MidpointRounding.ToEven`, mais **un seul cas `.5` a été mesuré** — ce n'est pas une
preuve, c'est une contrainte.

**Durée** : `remaining = 2` pour `TurnsFromRounds(1)` (1 round = 2 tours), cohérent avec « until the
start of its next turn ».

### `OnMyPosition` — `--equip-mythic astraOrdnanceBattery:OnMyPosition:4` (`extraDmgPct` 20)

Montage : attaquant DISTANCE `adeptRetributor` en (3,4), ANCRE `adeptCanoness` en (2,5), TÉMOIN
MÊLÉE `adeptHospitaller` en (4,5) — les trois voisins hex de la cible PROCHE `tyranTyrantGuard`
en (3,5) ; cible LOIN `tyranParasite` en (6,8), à distance ≥ 4 de tous.

| bras | `targetIds` de l'effet 1444 | préd. attaquant DISTANCE | préd. TÉMOIN MÊLÉE |
|---|---|---|---|
| mythique L4 | **[proche]** | **2892 – 4336** | 1446–2169 / 963–1446 |
| `sans-mythique` | **[]** | 2408 – 3616 | **identique** |
| amis `Rarity=4` | **[]** | 2408 – 3616 | **identique** |
| attaquant `Rarity=4` (ancre restée Mythic) | **[proche]** | 2408 – 3616 | **identique** |

Quatre séparations, de natures différentes :

1. **géométrique**, dans le même build — la cible LOIN n'est JAMAIS visée ;
2. **par bras** — sans la mythique, aucun effet et la prédiction retombe ;
3. **`UnitsWithRarity` (le SÉLECTEUR)** — amis en `Rarity=4` ⇒ l'aura ne vise plus personne. Ça
   établit du même coup que la branche `UnitsWithVisualId(astraSmnGuardsman)` ne contribue **rien**
   ici (aucun garde impérial au montage) ;
4. **`HasRarity(Caster)` (le GATE du BONUS)**, isolé du sélecteur — attaquant seul en `Rarity=4`,
   ancre restée Mythic : **l'effet est TOUJOURS sur la cible** et la prédiction est celle de base.
   Sans ce quatrième bras, le troisième éteint les deux d'un coup et ne les distingue pas.

Le **TÉMOIN MÊLÉE** est strictement invariant dans les quatre bras : `IsRangedAttack` est exercé.
(`adeptHospitaller` n'a qu'une arme, `Range = null`, donc mêlée au sens du seuil `Range >= 2`
d'`IdunBattle.Entities.WeaponProfile$$get_IsMelee`.)

**Amplitude** : `2892 / 2408 = 1.2010` et `4336 / 3616 = 1.1991`. Le `+20 %` n'est donc **pas** un
facteur appliqué à la valeur AFFICHÉE — il entre dans le pipeline avant l'arrondi final. L'étage
exact n'est pas décomposé ici : on rapporte la mesure, on ne fitte pas un scalaire.

⚠ **Une AURE NE SE LIT PAS SUR SA CIBLE.** `decisionView` publie l'entité-EFFET **une seule fois**,
portée par sa SOURCE (ici la MoW, qui n'est pas dans `units` mais dans `mows`), et c'est son champ
`targetIds` qui énumère les affectés — l'ennemi ne montre RIEN dans sa propre liste. La première
version du probe concluait « aure muette » alors que la prédiction portait déjà +20 %.

---

## 4. Le mur : `HasRarity` — et il n'est PAS où `#477-r43` le disait

`IdunBattle.Entities.UnitExtensions$$HasRarity(unit, rarity)` =
`GetBaseUnitComponent(unit)->[+0x74] == rarity` ; `UnitsWithRaritySelector$$Select` et
`HasRarityTrigger$$ShouldTrigger` lisent le **même** `+0x74`. Trois corrections mesurées :

- **L'enum EXISTE.** `data/symbols/rnca9r7q6c/frida/enums.tsv` porte
  `IdunMetaLogic.UserProgress.Model.UnitRarity 0=Common,1=Uncommon,2=Rare,3=Epic,4=Legendary,5=Mythic`.
  `#999-r1`/`#999-r3` écrivent « aucun enum `UnitRarity` » : c'est **faux**. Et `5` = **Mythic**,
  pas Legendary — l'i2 le confirme (`<style="Rarity_Mythic">`).
- **`rl_duel build` POSE `targetRarity`.** `rl_collect_batch._TARGET_RARITY = 5`, passé à
  `buildNormalizedBC`. `#477-r43` écrit l'inverse. Conséquence directe : **dans un runner
  standard, toute unité normalisée est Mythic, donc `HasRarity(·, Mythic)` est uniformément VRAI**
  — un port qui OUBLIERAIT le gate serait d'accord avec le natif dans tous les bras par défaut.
  C'est le régime dégénéré, et c'est `--unit-stat "<vis>:Rarity=N"` qui en sort.
- **Le montage n'est pas MUET** — la question que `#477-r43` laissait ouverte. `--unit-stat
  "adeptRetributor:Rarity=4"` (écrit APRÈS la normalisation) **éteint** le bouclier et fait
  disparaître `ShieldOfFaith` des events : `UnitConfiguration.Rarity` atteint bien
  `BaseUnitComponent.Rarity`.

**Ce qui manque est le CAPTEUR, et lui seul.** Mesuré sur un runner vivant : `rarity` n'apparaît
**nulle part** dans `observeBattle`, `combatSnapshot` ni `decisionView`. Point d'ancrage à hooker,
nommé et non écrit (une fenêtre de reinject est nécessaire) :

> `frida/hooks/features/ai-step/rpc-snapshot.ts`, fonction `readUnitConfig` — elle résout déjà
> `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(visualId)` et publie 5 champs sous
> `combatSnapshot.units[].unitConfig`. Il manque `rarity`.
> ⚠ **Deux structures, deux offsets, et `0x74` est dans les DEUX** : `UnitConfiguration+0x74` est
> l'`AbilityVariablesMultiplierPercentage` (déjà lu par ce même code, sous le nom `UCFG.mult`),
> tandis que `BaseUnitComponent+0x74` est la RARETÉ. Lire l'un pour l'autre rendrait `180` ou
> `100` là où on attend `0..5` — donc résoudre l'offset par `getFieldOffset` sur la classe
> `IdunBattle.Entities.Components.BaseUnitComponent`, jamais par recopie.

---

## 5. L'anomalie du palier 2 — un défaut de MONTAGE, pas du jeu

`ShieldOfFaith` niveau 2 ne pose **aucun** bouclier (reproduit deux fois), alors que 1, 3 et 4
fonctionnent. Cause établie par contre-épreuve : avec le palier **tronqué à `"32"`**, le bouclier
revient (2410). C'est donc la **VALEUR ÉCRITE**, pas l'indice de palier.

Deux mesures qui bornent le gisement :

- `abilities.ShieldOfFaith.variables.shieldPct == [25, 32.5, 40, 50]` est le **seul** palier non
  entier des **11** mythiques (les 10 autres sont `[10, 13, 16, 20]`) ;
- `data/seed-bc.json` porte **39 043** valeurs de variable d'ability, dont **0** non entière.

⇒ `catalog_inject.synthesize_ability` recopie la valeur du gameconfig telle quelle
(`"32.5"`), une forme que le BC réel ne porte **jamais**. Quelle valeur le pipeline META écrit à sa
place (32 ? 33 ?) n'est **pas** établi ici — la déterminer demande de lire la fabrique
meta-side, pas de deviner. Résidu `#1024-r3`.

---

## 6. Ce qui N'EST PAS couvert

- **Le PORT** — aucun des deux. `#1024-r1` / `#1024-r2`.
- La branche `UnitsWithVisualId(astraSmnGuardsman)` de l'aura de `OnMyPosition` : **jamais
  satisfaite** au montage (aucun garde impérial en bataille). `#1024-r4`.
- Le vecteur `PreAttack & IsUnitOnTileWithEffect(Target, Fire)` de `ShieldOfFaith` : seul le
  vecteur `Attack & WasCrit` a été exercé. `adeptCanoness` (au roster) porte `BrazierOfHolyFire`,
  qui pose du feu — le montage existe, il n'a pas été joué.
- Le nœud `TriggerAbilityDelayed` : son EFFET est observé (le bouclier arrive), son DÉLAI ne l'est
  pas (aucune mesure de l'ordre relatif bouclier / dégâts).
- L'étage exact où entre le `+20 %` de `OnMyPosition` (§3).
- La valeur que le pipeline META écrit pour un palier fractionnaire (§5).
