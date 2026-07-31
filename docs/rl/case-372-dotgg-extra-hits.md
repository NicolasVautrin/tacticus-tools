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

## 4bis. Le collecteur natif : la boucle est GLOBALE, et `Owner` est le BENEFICIAIRE

`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` **n'itere PAS** `attacker.Effects`. Il
appelle, sans argument, le slot 9 de son `effectsQuery` (`this+0x48`, pose par
`IdunBattle.Core.Services.DamagePrediction$$.ctor`) =
`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, qui rend **tous** les effets
actifs du board. Chaque entree est batie par
`IdunBattle.Core.Services.EffectsQuery$$GetEffectWithTargetEntry` et embarque deja la liste des
CIBLES de l'effet ; le consommateur fait une **double boucle effets x cibles** en ecrivant, a chaque
iteration, `AbilityEntities+0x18 (Owner) <- la CIBLE de l'effet` et `+0x08/+0x00 (Caster/Actor) <-
l'ATTAQUANT` (layout donne par `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ; offsets
confirmes par `IdunBattle.Entities.Selectors.OwnerSelector$$Select` = +0x18 et
`...CasterSelector$$Select` = +0x08).

**Donc `get_OwnerIsCaster` signifie « la cible de l'effet EST l'attaquant »** -- le PORTEUR
n'apparait nulle part dans l'`AbilityEntities`, on ne le rejoint que par `EffectSource(Effect)`
(+0x58), ce que fait justement la formule de chance. Cote port, ce gate est rendu PAR LE CANAL
(`aura_hits_bonus_for_attack` n'interroge que des porteurs et evalue leur selecteur sur
l'attaquant), exactement comme les autres auras source-side (#49/#153).

⚠ **Consequence contre-intuitive, lue au decompile** : `!DamageProfileIs(0xd)` du trigger est
**INERTE sur ce canal**. `GetAttackHits` construit son `AbilityEntities` avec
`damageProfile (+0xbc) = null`, et
`IdunBattle.Entities.Triggers.DamageProfileIsTrigger$$IsMatchingDamageProfileInEntities` ouvre sur
`Nullable.get_HasValue(entities+0xbc)` -> rend 0. Le gate Psychic effectivement porte vient donc du
**SELECTEUR** (`UnitsWithRangedWeaponsExcludingDamageProfile` = eligibilite de l'ARME du
beneficiaire), pas du trigger. Le canal `CreateAdditionalHits` (#179), lui, renseigne bien
`damageProfile` -- meme source d'effets, meme boucle, mais slot `0x23` au lieu de `0x1e`.

## 4ter. GROUND TRUTH LIVE

`MC1_67`/777, `tauShadowsun` rank 17, `turnsStarted(Shadowsun) >= 4` donc `chance = 100` (regime
DETERMINISTE des deux cotes). Geometrie pilotee : ennemi ancre sur une tuile a 6 voisins, porteur a
d >= 3 de lui, beneficiaire a la distance voulue du porteur et a portee de tir.

| beneficiaire | faction | d(benef, Shadowsun) | coups LIVE |
|---|---|---|---|
| `darkaHellblaster` | Imperial | **1** | **2** |
| `darkaHellblaster` | Imperial | 2 | 1 |
| `darkaHellblaster` | Imperial | 4 | 1 |
| `tauCrisis` | T'au | **2** | **10** |
| `tauCrisis` | T'au | 4 | 9 |

Le selecteur MORD sur la distance ET la faction : le MEME `darkaHellblaster` perd le coup en passant
de d=1 a d=2, la ou `tauCrisis` le garde a d=2. Mesure `decisionView` : les effets
`DefenderOfTheGreaterGood_ExtraDmg` **et** `_ExtraHits` sont portes par `tauShadowsun`, jamais par
les beneficiaires -- confirmation live du modele AURA source-side.

## 5. Ce que le port faisait AVANT

`1183`/`1306`/`1307` n'etaient inscrits nulle part (`EFFECT_CLASSES`), et le canal AURA de la
formule de coups avait ete **supprime** en #204 (`aura_hits_bonus_for_attack` + le hook
`create_aura_hits_bonus_for_attack`), faute d'alimenteur : son unique implementeur d'alors,
`AstartesBanner`, s'est revele appeler `CreateAdditionalHits`, pas
`CreateEffectHitsBonusForAttack`. La suppression etait juste **a ce moment-la** ;
`DefenderOfTheGreaterGood_ExtraHitsEffect` est l'alimenteur natif qui manquait.

## 6. Le port

| piece | fichier |
|---|---|
| classe COUPS + jumeau drone | `engine/entities/effects/loki/hits.py` |
| `_IS_DRONE` + jumeau drone de l'axe DEGAT (1306) | `engine/entities/effects/loki/extra_damage_aura.py` |
| hook `create_aura_hits_bonus_for_attack` | `engine/entities/effects/base.py` |
| agregateur `aura_hits_bonus_for_attack` (+ `aura_peers` sur le canal degat) | `engine/entities/effects/__init__.py` |
| cablage dans la formule de coups | `engine/services/attack_hits_formula.py` |
| substrat COMBAT (`att_faction`, `turns_started_by_id`, `parent_by_id`, `rng`) | `engine/runner/damage_model.py::build_hits_board` |
| substrat PREDICTION (`att_faction`, `turns_started_by_id`) | `engine/playbook/prediction/normal_attack.py` |
| inscriptions des QUATRE `EffectType` | `engine/entities/effects/factory.py` |
| montage reutilisable | `tests/engine/runner/_dotgg_aura_regime.py` |
| garde | `tests/engine/runner/test_dotgg_extra_hits_live.py` |

Le `Maybe` n'est PAS re-derive : il passe par `entities/triggers.py::MaybeTrigger`, deja mirror 1:1
de `MaybeTrigger$$ShouldTrigger`. Cote COMBAT le PRNG du `State` est threade (le tirage
`NextBool` **consomme un genrand**, le sauter decalerait tout le flux) ; cote PREDICTION la cle est
ABSENTE, ce qui EST le mirror de `CanUseRandom == false` (`99 < chance`).

### 6.1 Vue ROUGE avant le fix -- cinq mutations adversariales

Chaque gate porte est confronte a son propre mutant ; le mutant (e) est le **port d'AVANT**,
reconstitue par RETRAIT de l'inscription.

| mutant | ce qu'on retire | garde qui rougit |
|---|---|---|
| (a) | le gate de FACTION du ring 2 (`d <= 2` pour tous) | `test_selector_tiers_offline` |
| (b) | le plafond `Min(Direct(100), .)` | `test_gates_and_chance_offline` |
| (c) | la branche `isDrone` (`EntitiesIsNotTargetOfEffect`) | `test_drone_does_not_double_count_offline` |
| (d) | le noeud `Parent(EffectSource)` | `test_chance_reads_the_parent_for_the_drone_offline` |
| (e) | l'inscription `DefenderOfTheGreaterGood_ExtraHits` | `test_registry_carries_the_four_effect_types`, puis LIVE `test_adjacent_grants_the_extra_hit` |

## 7. Ce qui n'est PAS couvert

* **Le lien PARENT n'est capte par aucun RPC.** Ni `decisionView` ni `combatSnapshot` n'exposent le
  `ParentComponent` (id @+0x10). Cote COMBAT le port lit `UnitComponent.parent_id`, pose au spawn
  **par la simulation** -- correct quand le drone est invoque DANS le rejeu, absent quand l'etat est
  hydrate depuis un snapshot posterieur au spawn. Cote PREDICTION il n'est pas threade du tout.
  Consequence, limitee au jumeau DRONE : sa chance est lue sur SES tours au lieu de ceux de son
  summoner, donc **SOUS-ESTIMEE** (fidelite-safe : le port sous-tire, il ne sur-tire pas).
  **Point d'ancrage a exposer** : `ParentComponent` id @+0x10, a ajouter a `combatSnapshot.units[]`.
* **Le regime `chance < 100` n'est pas confronte** : le coup y est un TIRAGE, et l'alignement du
  flux PRNG entre natif et port sur ce point precis n'a pas ete mesure. Le port TIRE (mirror), donc
  la consommation de genrand est la ; que le tirage tombe au MEME rang que le natif reste a etablir.
* **`get_Priority`** (`100` si `!isDrone`, `0` sinon) n'est pas porte : le canal SOMME les
  contributions, il ne les trie pas.
* **La pose des effets sur le DRONE n'a pas ete jouee live** : le montage confronte l'aura de
  Shadowsun. La voie est etablie (`tauSmnDroneCommandLink`, `kind: summons`, traits `[Summon,
  Flying, Mechanical]`, passif `DefenderOfTheGreaterGood` -> branche `HasTrait(Owner, 0x2 = Summon)`
  de `CreateBehaviour` -> `1306`+`1307`), et le summon s'obtient en castant `ExemplarOfTheKauyon`.
  Les gates du jumeau sont couverts OFFLINE (mutants (c) et (d)).
