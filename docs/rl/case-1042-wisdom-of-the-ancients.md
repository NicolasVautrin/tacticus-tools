# #1042 — `WisdomOfTheAncients` : l'arbre est LU et CONFRONTÉ, la moitié qui compte est INATTEIGNABLE

**Verdict** : la mythique de `ultraDreadnought` (« Galatian ») est mirrorée au décompilé et exercée
étage par étage en live, avec des contre-épreuves qui **séparent**. Elle **n'entre pas au port** :
les **trois** étages de son sélecteur sont `UnitsWithRarity(·, Mythic)` et le port n'a **aucun canal
de rareté** — résidu `#1042-r1`, même mur que `#1024-r1` / `#1025-r1` / `#1035-r2` / `#1036-r1`.

Ce que cette fiche ajoute aux précédentes : **le `ConditionalSelector(IsMachine(Owner))` est INERTE
sur son seul porteur de jeu**, et c'est mesuré des deux côtés — la branche `ifFalse`, celle que l'i2
décrit (« adjacent to Galatian »), ne s'atteint qu'en **greffant** l'ability sur un porteur
ON-BOARD.

---

## 1. Ce que le décompilé écrit

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WisdomOfTheAncientsAbility` — parent LU dans
`data/symbols/rnca9r7q6c/frida/classes.tsv` : `IdunBattle.Entities.Abilities.BaseTriggeredAbility`
(donc PAS `AOwnerEffectTriggeredAbility`), et elle **déclare** ses deux méthodes.

```
$$CreateTrigger   = DSLTriggers.OnOwnerSpecificAbilityInit(0x5ab = 1451
                                                  TriggeredAbilityType.WisdomOfTheAncients)
$$CreateBehaviour = DSLBehaviors.AddEffect(0x5a5 = 1445 EffectType.WisdomOfTheAncients_DamageReduction,
                                           <BaseTriggeredAbility$$get_AbilityStateReference>,
                                           source  = Owner@<DSLSelectors+0x30>,
                                           targets = Owner@<DSLSelectors+0x30>,
                                           options = <Nullable ZERO-initialisé>)
```

Owner-effect **permanent** posé à l'init, par un corps propre et **sans** le `If(CreateCondition)`
que la base interpose — même forme que `CabalOfSorcerers` (#1036). L'appariement `1451 -> 1445` est
**lu au call-site**. Deux surcharges tranchées par la **cible du `call`**, pas par la forme du
pseudo-C : `AddEffect` est celle à `options:Nullable<AddEffectBehaviourOptions>`, et
`AmountIsGreaterThanZero` (plus bas) celle à `amount:IdunBattle.DSL.ITargetsSelector`.

`IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect` — parent `BaseEffect`.
`$$.ctor` = `BaseEffect( AbilityOrEffect(TriggeredAbilityType 1451), hasAutomaticActivation = 1 )` ;
l'overload d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` réellement appelée est celle dont le
**corps** écrit `set_TriggeredAbility`.
`$$CreateActiveCondition` est le corps **dédupliqué** `return <DSLTriggers+0x70>` (le `YesTrigger`
partagé, refcount 182 — le même que `IconOfObstinacy_ExtraArmour`) : l'effet est **toujours actif**.

### Le sélecteur — trois étages de rareté, et un aiguillage

```
ValidCharacter(x) = UnitsWithRarity(x, idun.meta.Rarity.Mythic = 5,
                                    UnitSelectionType.OnlyAliveAndTargetable = 3)

A = ValidCharacter( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique = true, 3) )
B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<DSLSelectors+0x20>, 3) )
F = Filter( B, AmountIsGreaterThanZero(
                   UnitsWithTrait( ValidCharacter( AdjacentFriends(
                                       ActiveTarget@<DSLSelectors+0x68>, unique = true, 3) ),
                                   UnitTrait.Hero = 0x10, 3 ) ) )

return ConditionalSelector( IsMachine(Owner@<+0x30>), ifTrue = F, ifFalse = Unique(A + F) )
```

- `ValidCharacter` est une **méthode déclarée** de l'effet (`$$ValidCharacter`), que
  `$$CreateTargetSelector` **inline trois fois** — d'où les trois `UnitsWithRarity` du pseudo-C.
- Les **deux** `AdjacentFriends` visent la surcharge `(unit, unique, selectionType)` — tranchée par
  les **xrefs entrantes** des deux corps homonymes, pas par la forme du call-site.
- `Filter(entities, filter)` = `DSLSelectors$$FromTrigger(entities, filter, 0)` : il lie chaque
  élément de `B` à `ActiveTarget@<DSLSelectors+0x68>`, que le prédicat relit.
- L'**ordre** des deux branches est lu : `DSLSelectors$$ConditionalSelector(abilityTrigger,
  selectorTrue, selectorFalse)` transmet ses arguments dans cet ordre au ctor du sélecteur.
- `IsMachineTrigger$$ShouldTrigger` prend la **première** entité du sélecteur et rend
  `IdunBattle.Entities.EntityExtensions$$IsMachine(entity)` =
  `entity.GetEntityType() == IdunBattle.Entities.Enum.EntityType.Machine = 6` (enum **qualifié**).
- `UnitsWithRaritySelector$$Select` compare `GetBaseUnitComponent(e)->[+0x74]` au littéral par
  **égalité** (jamais `>=`), et `Friends` ne retire **pas** le sujet
  (`UnitsByTeamSelector$$CountOrAdd` garde toute entité dont `UnitExtensions$$IsFriend(unit, other)`
  égale son flag, et `IsFriend(u, u)` est vrai).

En clair : **F** = « amis Mythiques du porteur ayant au moins un ami Mythique portant le trait
`Hero` en adjacence » ; **A** = « amis Mythiques adjacents au PORTEUR ».

### Le malus

```
$$CreateEffectDamageMalusForDefense
  = Nullable<EffectBonus>( EffectBonus.ForPercentDecrease(
        get_OwnerIsTarget,
        ConfigVar(AbilityVariableType.dmgReductionPct = 0x46, GetAbilityState(effet), <effet+0x60>) ) )
```

Corps **inline** (aucun `call` vers `ForPercentDecrease`) : le canal se lit à la **disposition des
champs** — montant écrit à `+0x08`, le slot de `EffectBonus$$ForPercentIncrease`/`ForPercentDecrease`,
distinct de `ForAddition` (`+0x10`) et `ForSubtraction` (`+0x18`). **Aucun gate de rareté ici** :
tout le ciblage vit dans le sélecteur.

`dmgReductionPct` = `[10, 13, 16, 20]` (4 paliers, `variablesAffectedByRarityBonus` = `[dmgReductionPct]`).

i2 `Abilities/WisdomOfTheAncients_CurrentLevelDescription` :
> Friendly **Mythic characters** take **-{dmgReductionPct}% Damage** if they are adjacent to
> **Galatian** or a friendly Mythic character.

Les deux membres de la phrase sont **A** et **F**. Or **A n'est dans que la branche `ifFalse`**.

---

## 2. Ce que le live a rendu

`probe_1042_wisdom_of_the_ancients_live.py`. Board `MC1_67` (7×9, tout Grass), seed 777, géométrie
**pilotée** par `--place` / `--a-place` et assertionnée avant tout build.

L'aura est montée du côté **ADVERSE** : `decisionView.attackPlans` ne publie que MES unités, donc la
prédiction native **contre** un défenseur affecté ne s'obtient qu'en plaçant le porteur en face.

```
team 2 (l'aura)   P1 adeptRetributor (1,1) - P2 adeptCanoness (2,1) - P3 adeptHospitaller (3,1)
                  H  astraCreed (5,7) - X astraBullgryn (6,7)      d(P·, H/X) >= 7 ; d(P1,P3) = 2
team 1 (moi)      A1 blackTerminator (2,2) adjacent a P2 ; A2 bloodDeathCompany (6,6) adjacent a X
```

`H` est forcé à `Rarity = 4` dans **tous** les bras (`--unit-stat`, écrit APRÈS la normalisation).
C'est ce qui fait de `X` un discriminant : `X` n'a qu'un voisin ami, `H`, non-Mythique — donc `X`
n'est **jamais** dans `F`, et n'entre dans le set que par `A`.

<!-- MESURES -->

---

## 3. Le mur — et il n'est pas où on l'attendrait

<!-- MESURES -->

---

## 4. Ce qui N'EST PAS couvert

<!-- MESURES -->
