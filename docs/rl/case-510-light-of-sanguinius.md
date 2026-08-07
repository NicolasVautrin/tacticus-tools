# #510 — `1177 LightOfSanguinius` : le vol de Dante, et un doublement qu'on a failli gater à tort

Build `rnca9r7q6c`. Porteur lineup UNIQUE : `bloodDante` (Dante), **dans le pool** rank 17. Face
COMBAT **portée** (`runner/abilities/bloodangels.py`) ; face DÉCISION déjà portée (playbook
`playbook/loki_custom.py`, régle dynamique de ciblage `#287-r5`).

## L'arbre, mirror 1:1

`IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour` — **hors**
namespace `Loki`, et les slots de rôle viennent de `IdunBattleLogic.Entities.DSLSelectors` /
`DSLFormulas` / `DSLTriggers` / `DSLBehaviors` (contexte `this@+0x30` : `+0x78 Behaviors ·
+0x80 Formulas · +0x88 Triggers · +0x90 Selectors`) :

```
infiltrate = AddEffect( 0x416 = Infiltrate_UnitEffect, AbilityStateReference,
                        source = Owner@Selectors+0x30, targets = Owner@+0x30,
                        turns  = <DSLFormulas+0x20> = Direct(1) )
tuiles     = First( SortTilesByUtility(
                      Filter( CanAddUnit(AdjacentTiles(Target@+0x60)),
                              NOT( AmountIsGreater(
                                     MinDistance(ActiveTarget@+0x68, CasterTiles@+0x58),
                                     ConfigConst(0x16 = range) ) ) ),
                      Caster@+0x48, UtilityDefinition(7 = Tile) ), 1 )
vol        = FlyUnit( Caster@+0x48, tuiles )
attaque    = AttackWithAttackDamage( Caster@+0x48, Target@+0x60, MinMaxDamage(abilityState),
                 Nullable(GetDamageProfile()) = Melta, GetHits() = nrOfHits,
                 AbilityOrEffect(this), <options ZERO>, selectionType = 2 )
aura       = AddEffect( 0x560 = LightOfSanguinius, AbilityStateReference,
                 source  = Owner@+0x30,
                 targets = op_Addition( Target@+0x60,
                             NonSteppableOrObjectUnits(
                               Enemies( Owner@+0x30,
                                 SurroundingUnits(Target@+0x60, ConfigConst(0x44 = range_2),
                                                  unique: 1, includeCenter: 0, 3), 3), 3) ),
                 turns   = TurnsFromRounds(ConfigConst(0x45 = nrOfRounds)) )
Execute( op_Addition( op_Addition(infiltrate, vol),
                      IfAlive(Owner@+0x30, op_Addition(attaque, aura)) ) )
```

`DSLBehaviors$$IfAlive(sel, ifB, elseB)` est littéralement `If(DSLTriggers.IsAlive(sel), ifB, elseB)`
— même slot, même place que chez `HammerOfWrathAbility` : **après** le déplacement, **avant**
l'attaque. Un Dante mort au vol (overwatch/piège de la charge) ne pose ni dégât ni debuff.

**Jumeau structurel de `1153 HammerOfWrath`** (même faction, même preset de ciblage, même
`GetDynamicInvalidTargetReason`) : le sélecteur de destination est terme à terme IDENTIQUE, d'où le
foyer partagé `bloodangels.charge_dest_tile(state, caster, target, ability_id)` — seule la config
lue change. Deux écarts LUS, à ne pas lisser : **`FlyUnit`** (et non `MoveUnit` — `Nullable(3)` dans
les options, donc `FlyPathfinder` + `movementSteps` = distance) et la famille **ATTACK**
(`DSLBehaviors$$AttackWithAttackDamage`, crit/block, 2 tirages par coup), là où 1153 est en famille
ABILITY.

## Le masque, et la disjonction

`...LightOfSanguiniusAbility$$.ctor` est en forme **PRESET STATIQUE COPIÉ** : aucun appel à
`TargetingOptions$$.ctor`, il recopie les 0x40 octets de `<TargetingOptions statics>+0x240` puis
`AActiveAbility..ctor(this, &opts, 0)`. Relu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
`+0x240 isSelfCasting = 0` · `+0x248 range <- TargetingRange statics+0x48 = useWholeBoard` ·
`+0x260 forceMeleeTarget = 1` · `+0x268 rules = **0x102004032**`. Décomposition exhaustive, aucun bit
résiduel : `TargetMatchesDynamicRule | CasterHasNotMoved | TargetHasFreeAdjacentTile | TargetIsEnemy
| AllowObscuredTargetByElevation | TargetIsNotAdjacent` (le dernier est le bit **32**).
`AbilityAttackType` = **0 = DirectTargetAttack** (3ᵉ argument, transcrit tel quel).

Le masque **MIGRE** de `TARGETING_OPTIONS_UNPORTED` vers la classe, et sa règle dynamique de
`DYNAMIC_TARGET_RULE_UNPORTED` vers une surcharge qui appelle le corps déjà porté
(`targeting._dynamic_rule_light_of_sanguinius`, #287-r5). Comptes **RE-DÉRIVÉS** après retrait, pas
soustraits : `len(TARGETING_OPTIONS_UNPORTED)` **31 → 30** (bloc `9/4/1/4` + `3/1/4` + 4 hors-bloc),
snapshot `test_270r1_volet2` `31 → 30` / total `115 → 114`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`
`19 → 18`. `1204 LeadingTheCharge` partage le MÊME preset et le MÊME masque et **reste** dans la
table : ce qui les sépare est leur règle dynamique, pas leurs options.

## L'effet 1376, et le piège de mesure qui a failli le fausser

`IdunBattle.Entities.Effects.Loki.LightOfSanguinius_DamageReductionEffect$$.ctor` =
`DamageModifierAbilityEffect..ctor(this, 0x499 = 1177, Nullable(1))` ; `$$CreateDamageModifier` :

```
pct    = ConfigVar( 0x46 = dmgReductionPct, GetAbilityState(effet), config@effet+0x60 )
seuil  = ConfigConst( 0x4f = healthPct, config@effet+0x60 )
amount = DSLFormulas.If( NOT( HealthPctIsBelowOrEqual(Target@DSLSelectors+0x60, seuil) ),
                         pct, Multiply(pct, <DSLFormulas+0x28> = Direct(2)) )
return   EffectBonus.ForPercentDecrease( DSLTriggers.get_OwnerIsCaster, amount )
```

Aucun autre gate — ni mêlée/ranged, ni profil, ni `IsNormalAttack`, ni `ActiveCondition`. L'effet vit
sur l'ATTAQUANT (`get_OwnerIsCaster`) et sort par le forwarder
`DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack` (slot `+0x728`), donc dans
l'accumulateur ATTAQUANT. Le substrat du gate (`tgt_hp`/`tgt_hp_max`) est threadé dans `att_ctx` par
les **trois** faces — le natif n'a qu'UN `AbilityEntities`, la scission est un artefact du port.

### ⚠ LE PIÈGE : `aiPlaybookPredict` HORS-TOUR rend un contexte DÉGRADÉ

Interrogé sur un ennemi **pendant le tour du joueur**, l'oracle natif rend un facteur **0,70
CONSTANT** dans TROIS régimes — porteur de l'effet à 18,8 % PV, défenseur à 40 % PV, et les deux à
100 % PV. Aucun doublement, quelle que soit l'entité sous le seuil. Un premier port a donc conclu à
un « fork prédiction/combat » et **gaté le doublement sur `is_prediction`**.

**L'anti-confond l'a REFUTÉ.** Re-mesuré sur le MÊME couple, avec le MÊME effet actif, au MÊME
instant, **après `endturn`** (donc quand l'unité affectée appartient à l'équipe ACTIVE) :

| canal | attaquant | défenseur | mesure | facteur |
|---|---|---|---|---|
| prédiction HORS-TOUR | u85 (affecté, 100 % PV) | u81 (40 % PV) | `(1820, 2730)` | 0,70 |
| prédiction EN-TOUR | u85 | u81 | `(1040, 1560)` | **0,40** |
| combat EN-TOUR | u85 | u81 | live **2778** — port doublement ARMÉ **2778**, DÉSARMÉ 5091 | **0,40** |

Le canal n'a pas changé ; le **tour**, si. Le gate `is_prediction` a été retiré le même jour, et un
test verrouille sa non-réintroduction.

La lecture qui explique la dégradation :
`IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` résout
d'abord son SÉLECTEUR (`this+0x10`, slot 7 `SelectSingle`) et **rend `0` = FAUX dès qu'il ne résout
AUCUNE entité**. Un `Target@+0x60` non renseigné suffit donc à effacer la branche, sans erreur.
**Ce qui reste NON LU** — pourquoi ce slot est vide hors-tour, c'est-à-dire la construction de
l'`AbilityEntities` dans
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` — est le
résidu **`#510-r1`**.

## Ce qui est confronté

`probe_510_light_of_sanguinius_live.py` (montage `MC1_67`, positions DRIVÉES ; deux punching-bags
alliés de même `Health` dont un à 40 % PV — l'unique curseur ; un ennemi HORS du ring = témoin).
Six étages, tous verts, gardés par `tests/engine/runner/test_510_light_of_sanguinius_live.py` :

- **E1** la SÉQUENCE des 5 coups Melta, port == live, depuis la même capture et le même MT
  (`[1634, 1426, 1378, 1482, 1422]`) ;
- **E2** la tuile d'arrivée du vol, `(4, 2)` des deux côtés ;
- **E3** les porteurs de l'effet 1376 : `[83, 85]` des deux côtés, l'ennemi hors ring EXCLU ;
- **E4** 4 couples (ennemi, allié), port == oracle natif, avec les DEUX magnitudes (0,70 et 0,40)
  et DEUX témoins plats à 1,00 ;
- **E5** l'attaque réelle rejouée hors-ligne : bras ARMÉ bit-exact, bras DÉSARMÉ non — c'est le
  second point qui interdit un vert par coïncidence ;
- **E6** l'anti-confond ci-dessus.

⚠ Fait de mesure incident, utile ailleurs : après `endturn`, `applyAction` accepte les actions pour
les unités de l'équipe adverse (`decisionView.ctrl` bascule) — c'est ce qui rend E5 possible sans
passer par `aiturn`.
