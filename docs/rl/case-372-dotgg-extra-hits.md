# #372 (#366-G3a) — `DefenderOfTheGreaterGood` axe COUPS : 1183 + jumeaux drone 1306/1307

**Question binaire** : le bonus de COUPS accorde par `1183` (et ses jumeaux drone) est-il compte
par le port comme par le natif, sur un montage ou il MORD ?

**Reponse** : NON avant ce cas (aucune inscription, aucun canal) — OUI apres.

## 1. UNE classe native, parametree par `isDrone` — les « jumeaux » ne sont pas des classes

`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$.ctor(this, isDrone)`
ecrit `isDrone` a `this+0x480` apres `BaseEffect(AbilityOrEffect(...), hasAutomaticActivation = 1)`.
Meme forme pour l'axe DEGAT :
`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$.ctor(this, isDrone)` =
`DamageModifierAbilityEffect(0x483 = 1155 DefenderOfTheGreaterGood, 0)` + `this+0x480 = isDrone`.

Donc **deux** classes natives seulement pour **quatre** `EffectType` :

| EffectType | classe native | `isDrone` |
|---|---|---|
| `0x49e = 1182` DefenderOfTheGreaterGood_ExtraDmg | `..._ExtraDmgEffect` | 0 |
| `0x49f = 1183` DefenderOfTheGreaterGood_ExtraHits | `..._ExtraHitsEffect` | 0 |
| `0x51a = 1306` DefenderOfTheGreaterGood_ExtraDmgDrone | `..._ExtraDmgEffect` | **1** |
| `0x51b = 1307` DefenderOfTheGreaterGood_ExtraHitsDrone | `..._ExtraHitsEffect` | **1** |

`isDrone` a **deux** effets lisibles, et **aucun** ne touche la magnitude :

* `..._ExtraHitsEffect$$get_Priority` rend `100` si `!isDrone`, `0` sinon ;
* la branche `isDrone` du selecteur ajoute `EntitiesIsNotTargetOfEffect` (cf. 3.).

## 2. Le poseur : `CreateBehaviour` pose les DEUX effets de sa branche

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$CreateBehaviour` :

```
b1182 = AddEffect(0x49e, AbilityStateReference, selectors.Owner, null)
b1183 = AddEffect(0x49f, AbilityStateReference, selectors.Owner, null)
b1306 = AddEffect(0x51a, AbilityStateReference, selectors.Owner, null)
b1307 = AddEffect(0x51b, AbilityStateReference, selectors.Owner, null)
return If( HasTrait(Owner, 0x2 = Summon), b1306 + b1307, b1182 + b1183 )
```

Le 3e argument d'`AddEffect` est `selectors.Owner` : **l'effet est heberge par le PORTEUR**
(Shadowsun, ou le Command-Link Drone), jamais par le beneficiaire. C'est le modele AURA
source-side deja porte pour `1182`.

## 3. Le selecteur — PARTAGE avec l'axe degat, plus un gate anti-double-comptage

`..._ExtraHitsEffect$$CreateTargetSelector` :

```
ownerTiles = DSLSelectors.Tiles(selectors.Owner)
return DefenderOfTheGreaterGoodAbility.GetBaseBuffTargetSelector(dsl, ownerTiles,
                                                                 isDrone@+0x480, 0x49f)
```

`..._ExtraDmgEffect$$CreateTargetSelector` est le MEME appel avec `0x49e`. Le corps de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` :

```
sel = AdjacentFriends(Owner, ownerTiles, includeSelf = 1)
sel = sel - Owner
srf = UnitsFromFaction( SurroundingFriends(Owner, ownerTiles, range = 2, ...), 9 = Tau, 3 )
sel = UnitsWithRangedWeaponsExcludingDamageProfile( Unique(sel + srf), 0xd = Psychic )
if (isDrone == 0) return sel
return EntitiesIsNotTargetOfEffect( sel, Nullable<EffectType>(effectType) )
```

Le tronc commun est celui deja porte pour `1182` : amis ADJACENTS (range 1, toute faction) OU
T'au dans un rayon 2, ayant une arme ranged non-Psychic.

⚠ **La branche `isDrone` n'est PAS decorative** : `EntitiesIsNotTargetOfEffect(sel, <effectType
non-drone>)` retire du selecteur du DRONE toute unite deja ciblee par l'effet de SHADOWSUN
(`0x49e` pour l'axe degat, `0x49f` pour l'axe coups). C'est l'anti-double-comptage natif quand
une unite est a la fois dans l'aura de Shadowsun et dans celle du drone.

## 4. La contribution COUPS — un `EffectBonus`, PAS un groupe #179

`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`,
lu verbatim (ordre des `DSLFactory` du corps natif) :

```
srcSel = EffectSource(selectors, <selectors+0x38 = le selecteur Effect>)
turnSel = If( AmountIsGreaterThanZero(Parent(srcSel)), Parent(srcSel), srcSel )
chance = Min( Direct(100), Multiply( ConfigConst(0x2a = chance), UnitTurnsStarted(turnSel) ) )

trigger = get_OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd = Psychic) & Maybe(chance)
return EffectBonus.ForAddition( trigger,
                                ConfigConst(0x2b = extraHit),
                                <AbilityOrEffect recopie> )
```

Le marqueur natif est `CreateEffectHitsBonusForAttack` (**terme de la FORMULE de coups**,
`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`), et **non**
`CreateAdditionalHits` (canal #179, groupe a degat propre). Le coup gagne est donc un coup
d'ARME de plus, avec le degat et les %-mods de l'arme — pas un coup a profil separe. C'est la
distinction tranchee en #204/#227, dans l'autre sens.

`Direct(100)` = le champ `DSLFormulas+0x30`, dont `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
montre qu'il est construit `DirectAmount(100)` (les voisins : `+0x18`=0, `+0x20`=1, `+0x28`=2,
`+0x38`=-1).

`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$GetCurrentExtraHitChance`
reconstruit **exactement** le meme nœud `chance` (c'est la donnee `{[chanceCurrent]}` de l'i2).

### 4.1 Les constantes

`gameconfig` de l'ability `DefenderOfTheGreaterGood` : `constants = {chance: 25, extraHit: 1}`,
`variables = {extraDmg: [5 .. 364]}`, `variablesAffectedByRarityBonus = [extraDmg]`.
`0x2a = chance` et `0x2b = extraHit` sont les deux SEULES constantes de l'ability — la lecture
croise le mapping deja etabli du depot (`AbilityConstantType` 0x2a = `chance`, 0x2b = `extraHit`).
**Aucune des deux n'est rarity-scalee** (seul `extraDmg` l'est) : le multiplier est passe au
`ConfigConst` par calque, il est inerte.

### 4.2 Le tour compte est celui de SHADOWSUN, drone compris

`turnSel = If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )` :
pour Shadowsun, `Parent` est vide -> on lit Shadowsun ; pour le Command-Link Drone (un summon),
`Parent` est son summoner -> on lit **encore Shadowsun**. L'i2 le dit :
« This chance is 25% for each round in which **Shadowsun** has been on the battlefield. »

`IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = `GetStat(unit, 0xc)` =
`StatType.TURNS_STARTED` (deja porte).

### 4.3 `Maybe(chance)` — le regime DETERMINISTE, et c'est lui qui rend le cas validable

`IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` :

```
chance = <noeud V>.Calculate(entities)
if (!ANonDeterministicAbilityTrigger.CanUseRandom(this)) return 99 < chance;
return DisallowablePseudoRNG.NextBool(rng@+0x18, chance);
```

Deja porte 1:1 (`engine/entities/triggers.py::MaybeTrigger`). Consequence pour CE cas :

* `chance = min(100, 25 x turnsStarted(Shadowsun))` atteint **100 des le 4e tour commence** ;
* a 100, les DEUX faces concordent sans aleatoire : `99 < 100` est vrai, et `NextBool(100)` aussi.

C'est le regime a viser en validation : le coup supplementaire y est **certain**, donc
observable sans statistiques.

## 5. Ce que le port faisait AVANT

`1183`/`1306`/`1307` n'etaient inscrits nulle part (`EFFECT_CLASSES`), et le canal AURA de la
formule de coups avait ete **supprime** en #204 (`aura_hits_bonus_for_attack` + le hook
`create_aura_hits_bonus_for_attack`), faute d'alimenteur : son unique implementeur d'alors,
`AstartesBanner`, s'est revele appeler `CreateAdditionalHits`, pas
`CreateEffectHitsBonusForAttack`. La suppression etait juste **a ce moment-la** ;
`DefenderOfTheGreaterGood_ExtraHitsEffect` est l'alimenteur natif qui manquait.
