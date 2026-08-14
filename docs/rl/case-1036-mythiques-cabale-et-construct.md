# #1036 — `CabalOfSorcerers` et `GuardianConstruct` : la POSE est portée, le BONUS bute sur le même capteur

**Verdict par item** — les deux abilities ont la même ventilation, pour la même cause, mesurée :

| face | `CabalOfSorcerers` (1496) | `GuardianConstruct` (1530) |
|---|---|---|
| ability : pose de l'owner-effect à l'init | **PORTÉE** (`ABILITY_INIT_OWNER_EFFECTS`) | **PORTÉE** (idem) |
| effet : bonus %-dégât sous sélecteur | **INVALIDABLE — BLOCAGE capteur** (`#1036-r2`) | **INVALIDABLE — BLOCAGE capteur** (`#1036-r1`) |
| face DÉCISION | playbook natif existe, **NON portée** (`#1036-r3`) | **RIEN À PORTER** — aucun playbook dans le build |

La cause du blocage est **une seule**, et elle est déjà nommée ailleurs (`#999-r3`, `#1025-r1`,
`#1024-r1/r2`) : **le canal de RARETÉ n'existe pas côté port**. Les deux sélecteurs finissent par
un étage `UnitsWithRarity(…, Rarity.Mythic)`.

---

## 1. Les artefacts natifs, et ce qui les distingue

Les deux sont des `IdunBattleLogic.Entities.Abilities.Triggered.Loki.<X>Ability` — donc des
**passifs déclenchés**, pas des actives : elles n'entrent ni dans `ABILITY_CLASSES`, ni dans
`TARGETING_OPTIONS`, ni dans `ABILITY_ATTACK_TYPE` (confirmé : le cliquet `#1021` porte sur
`ABILITY_CLASSES` et ne les voit donc pas — il a été joué, il est vert).

**`GuardianConstructAbility`** — parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`
(`frida/classes.tsv`), n'override QUE `$$GetEffectType` (corps entier : `return 0x60c`). Tout le
reste est la base, relue :

```
$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType)
$$CreateBehaviour = If( CreateCondition(abilityState),
                        AddEffect(GetEffectType(),
                                  AbilityState(Owner@<DSLSelectors+0x30>, AbilityType(this)),
                                  source = Owner, targets = Owner, options = <Nullable ZERO>) )
```

**`CabalOfSorcerersAbility`** — parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et
elle **DÉCLARE** ses deux méthodes. Même résultat, sans le `If` que la base interpose :

```
$$CreateTrigger   = DSLTriggers.OnOwnerSpecificAbilityInit(0x5d8 = TriggeredAbilityType.CabalOfSorcerers)
$$CreateBehaviour = DSLBehaviors.AddEffect(0x5d6 = EffectType.CabalOfSorcerers_ExtraDamagePct,
                                           AbilityStateReference,
                                           source = Owner@<DSLSelectors+0x30>,
                                           targets = Owner@<DSLSelectors+0x30>,
                                           turns  = <Nullable ZERO-initialisé>)
```

⇒ dans les deux cas : **owner-effect PERMANENT posé à l'init**, patron `Vitarus` / `NornCrown` /
`MoreGitzOverEre`. C'est cette face qui est portée ici.

## 2. Les deux effets — RE complète (c'est ce qui reste à porter le jour où le capteur existe)

### `GuardianConstruct_ExtraDamagePctEffect` (1548)

```
$$CreateEffectDamageBonusForAttack =
    EffectBonus.ForPercentIncrease( get_OwnerIsCaster,
                                    ConfigVar(AbilityVariableType.extraDmgPct = 0xa,
                                              GetAbilityState, <effet+0x60>) )

$$CreateTargetSelector =
    UnitsWithRarity(
        EntitiesWithAnyEffect( Friends(Owner@<DSLSelectors+0x30>, AllUnits, OnlyAliveAndTargetable),
                               effectTypes  = [EffectType.NanoscarabRepairProtocols = 0x609],
                               effectTarget = EffectTargetType.Both = 6 ),
        rarity = Rarity.Mythic = 5, unitSelectionType = OnlyAliveAndTargetable = 3 )

$$GetRefreshTriggers = [RefreshEffectTrigger.EffectsChanged = 4,
                        RefreshEffectTrigger.UnitStateChanged = 3]
```

Le `0x609` du call-site est le **scalaire** que la surcharge à 4 arguments emballe elle-même dans un
`int[1]` ; le `6` est l'`effectTarget`, **pas** un second type (même forme que `PsychicStalk`).

### `CabalOfSorcerers_ExtraDamagePctEffect` (1494)

```
$$ValidCharacter(x) =
    UnitsWithTraits( UnitsWithRarity(x, Rarity.Mythic = 5, OnlyAliveAndTargetable),
                     traits = [UnitTrait.Psyker = 0x3ea, UnitTrait.Hero = 0x10],
                     OnlyAliveAndTargetable )

$$CreateTargetSelector =
    A = ValidCharacter( AdjacentFriends(Owner, unique = true, OnlyAliveAndTargetable) )
    B = ValidCharacter( Friends(Owner, <DSLSelectors+0x20>, OnlyAliveAndTargetable) )
    F = Filter( B, AmountIsGreaterThanZero(
                       ValidCharacter( AdjacentFriends(<élément courant @DSLSelectors+0x68>,
                                                       unique = true, OnlyAliveAndTargetable) ) ) )
    return ConditionalSelector( IsMachine(Owner), ifTrue = F, ifFalse = Unique(A + F) )

$$CreateEffectDamageBonusForAttack =
    EffectBonus.ForPercentIncrease(
        get_OwnerIsCaster & CurrentAttackDamageProfileIs(DamageProfileType.Psychic = 0xd),
        ConfigVar(AbilityVariableType.extraDmgPct = 0xa, GetAbilityState, <effet+0x60>) )
```

Lecture : les bénéficiaires sont les alliés **Mythic + Psyker + Hero** du porteur qui ont
eux-mêmes un tel allié **adjacent** (la « cabale ») ; si le porteur est une **machine**
(`IsMachine`), c'est cette seule liste, sinon on y ajoute ses propres voisins qualifiés.
`thousDaemonPrince` étant une MoW, c'est la branche `F` qui s'applique — mais `IsMachine` est un
trigger évalué à la sélection, pas une constante, donc les deux branches sont portées telles quelles
le jour venu.

**Quatre lectures qui ne se devinent pas**, et comment chacune a été tranchée :

- **le canal est POURCENT, pas ADDITIF.** Le corps de `CabalOfSorcerers` est **inline** (aucun
  `call`) : on le lit à la disposition des champs. `EffectBonus$$ForAddition` écrit son montant à
  `+0x10`, `EffectBonus$$ForPercentIncrease` à `+0x08` — les deux corps ont été décompilés pour
  l'établir. Ce corps-ci écrit le trigger à `+0x00` et le montant à `+0x08` ⇒ pourcentage.
  `GuardianConstruct`, lui, **appelle** `ForPercentIncrease` explicitement : deuxième source,
  concordante.
- **l'ordre des branches de `ConditionalSelector`.** `ConditionalSelector$$Select` évalue `this+0x18`
  (le trigger) et prend `this+0x20` s'il déclenche, `this+0x28` sinon — soit `selectorTrue` /
  `selectorFalse` dans l'ordre du ctor. Lu, pas supposé.
- **la surcharge d'`AdjacentFriends`.** Deux corps homonymes existent, `(this, unit, unique,
  selectionType)` et `(this, unit, unitTile, unique)`. Tranché par les **XREFS ENTRANTES** : les
  deux appels de `$$CreateTargetSelector` visent le premier.
- **`Friends` ne retire PAS le porteur.** `UnitsByTeamSelector$$CountOrAdd` garde toute entité dont
  `UnitExtensions$$IsFriend(unit, other)` égale son flag, et `IsFriend(u, u)` est **vrai** (il
  compare deux ids d'équipe). Le porteur n'est donc exclu que là où l'adjacence l'exclut.

## 3. Le mur : la RARETÉ — et l'enum que le combat lit n'est PAS celui qui était nommé

`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` lit
`UnitExtensions$$GetBaseUnitComponent(e)` puis compare son champ `+0x74` à la rareté attendue.
Ce champ n'est publié par **aucun** RPC — re-vérifié pour cette tranche sur `observeBattle`,
`combatSnapshot`, `decisionView` et tout `frida/host/**`. Point d'ancrage nommé (fenêtre de
reinject nécessaire) : `frida/hooks/features/ai-step/rpc-snapshot.ts`, fonction `readUnitConfig`.

**Correction mesurée apportée ici.** `case-1024` §4 (et `#999-r1`/`#999-r3` avant lui) désignent
l'enum `IdunMetaLogic.UserProgress.Model.UnitRarity`. Cet enum existe, mais **ce n'est pas celui du
combat** : le **type déclaré** du paramètre `rarity`, lu dans `frida/methods.tsv`, est
`idun.meta.Rarity` aux **trois** foyers —
`IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity`, `IdunBattleLogic.Entities.DSLTriggers.HasRarity`
et `IdunBattle.Entities.UnitExtensions.HasRarity`.

Cela n'a **aucun effet sur l'ordinal** — et c'est précisément ce qui rend la faute dangereuse :
**cinq** enums du build portent les six mêmes membres aux mêmes ordinaux (`idun.meta.Rarity`,
`...Model.{Unit,Item,Upgrade,XpBook}Rarity`). Le mirror livré ici s'apparie donc au nom **plein**
mesuré, et `probe_313` le garde (`engine/entities/rarity.py`).

### Pourquoi on n'inscrit PAS les deux effets à `EFFECT_CLASSES`

Les deux dégradations possibles sont mauvaises, et l'une est piégeuse :

- **omettre le gate** ⇒ terme PERMISSIF silencieux. Et il serait **invisible en test** : `rl_duel
  build` impose `targetRarity = 5` à toute unité normalisée (`rl_collect_batch._TARGET_RARITY`),
  donc `HasRarity(·, Mythic)` est uniformément VRAI et un port qui l'oublie est d'accord avec le
  natif **dans tous les bras par défaut**. C'est un régime DÉGÉNÉRÉ : un accord n'y prouve rien.
  On en sort par `--unit-stat "<vis>:Rarity=N"`, dont `case-1024` a mesuré qu'il n'est pas muet ;
- **fermer le gate sur canal absent** ⇒ effet inerte, qui compterait pourtant comme « porté » dans
  les audits de couverture. Pire que l'absence.

C'est le précédent déjà pris pour `MoreGitzOverEre` (1449) et `ElectrochaffBackups` (1446).
La RE ci-dessus est écrite **au site** (`effects/factory.py`) pour que le port se réduise, le jour
où le capteur existe, à écrire deux classes d'effet.

## 4. Confrontation

Porteurs (`catalog_inject.py --list-mythics`) : `thousDaemonPrince` / `thousNpcMowDaemonPrince`
pour `CabalOfSorcerers`, `necroReanimator` / `necroNpcMoWReanimator` pour `GuardianConstruct`.
Les deux `lineup` sont **hors seed** ⇒ `augment` requis, intégré à `--equip-mythic` (#999).
Aucun des deux n'est dans `data/unspawnable_rank<N>.json`.

Montage (fixture `mythic_owner_effect_runner`,
`tests/engine/runner/test_1036_mythiques_owner_effect_live.py`) :

```powershell
python rl_duel.py build --seed 777 --board MC1_67 `
  --p-units necroDestroyer,necroWarden --a-units tyranParasite,tyranTyrantGuard `
  --p-mow necroReanimator --equip-mythic "necroReanimator:GuardianConstruct:1" `
  --state-file <ABSOLU>
```

## 5. Ce qui N'EST PAS couvert

- **Le BONUS de dégât des deux effets** — jamais évalué, ni offline ni live. C'est l'objet de
  `#1036-r1` / `#1036-r2`, tous deux `BLOCAGE: capteur`.
- **La magnitude** `extraDmgPct` n'est pas confrontée à une valeur live (elle n'a pas de
  consommateur tant que l'effet n'est pas au registre).
- **La face DÉCISION de `CabalOfSorcerers`** (`#1036-r3`) : `CabalOfSorcerersPlaybook`
  (`TriggeredAbilityNonOwnerPlaybook<CabalOfSorcerersAbility>`) surcharge
  `$$CalculateMovementUtilityInSteps`. Son corps a été lu (il rend une utilité pour une tuile
  candidate dont un voisin est Mythic+Hero+Psyker, ou est le porteur) — il porte **lui aussi** un
  test de rareté (`BaseUnitComponent+0x74 == 5`), donc le même blocage.
- La branche `ifFalse` (`Unique(A + F)`) de `CabalOfSorcerers` n'est atteignable que sur un porteur
  **non-machine** : aucune des deux unités porteuses connues ne l'est.

## 6. Résidus

- **`#1036-r1`** — porter `GuardianConstruct_ExtraDamagePctEffect` (1548) dans `EFFECT_CLASSES`.
  RE complète ci-dessus et au site. `BLOCAGE: capteur` (rareté).
- **`#1036-r2`** — idem pour `CabalOfSorcerers_ExtraDamagePctEffect` (1494). `BLOCAGE: capteur`.
- **`#1036-r3`** — face DÉCISION de `CabalOfSorcerers` (`CabalOfSorcerersPlaybook`).
  `BLOCAGE: capteur` (même canal de rareté).
