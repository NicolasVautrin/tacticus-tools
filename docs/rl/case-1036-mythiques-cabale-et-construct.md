# #1036 — `CabalOfSorcerers` et `GuardianConstruct` : la POSE, puis le BONUS

**Verdict par item** :

| face | `CabalOfSorcerers` (1496) | `GuardianConstruct` (1530) |
|---|---|---|
| ability : pose de l'owner-effect à l'init | **PORTÉE** (`ABILITY_INIT_OWNER_EFFECTS`) | **PORTÉE** (idem) |
| effet : bonus %-dégât sous sélecteur | **PORTÉ + gates CONFRONTÉS LIVE** (`#1036-r2`) | **PORTÉ + gates CONFRONTÉS LIVE** (`#1036-r1`) |
| … sa MAGNITUDE face au natif | **NON CONFRONTÉE** — `#1036-r8`, `BLOCAGE: capteur` | idem |
| … la patte SELF (le porteur bénéficiaire) | **NON PORTÉE** — `#1036-r7` | idem |
| face DÉCISION | playbook natif existe, **NON portée** (`#1036-r3`) | **RIEN À PORTER** — aucun playbook dans le build |

Les deux effets sont entrés dans `EFFECT_CLASSES` (`loki/extra_damage_aura.py`, canal AURA
`create_aura_attack_damage_bonus_for_ally`) le 2026-08-14. Le verrou qui les tenait dehors — le
canal de RARETÉ — est tombé avec `#999-r3` (le capteur) puis `#999-r3-r1-r1` (une MoW entre enfin
dans l'univers des porteurs d'aura). Ce qui restait à faire ici est le mirror des sélecteurs, le
threading de trois clés de contexte neuves sur les DEUX faces, et la confrontation **en régime
séparant** — §7.

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

## 2. Les deux effets — RE complète (portée telle quelle, terme à terme)

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

### Ce que l'inscription au registre exigeait, et que le port fait

Les deux dégradations possibles sont mauvaises, et l'une est piégeuse :

- **omettre le gate** ⇒ terme PERMISSIF silencieux. Et il serait **invisible en test** : `rl_duel
  build` impose `targetRarity = 5` à toute unité normalisée (`rl_collect_batch._TARGET_RARITY`),
  donc `HasRarity(·, Mythic)` est uniformément VRAI et un port qui l'oublie est d'accord avec le
  natif **dans tous les bras par défaut**. C'est un régime DÉGÉNÉRÉ : un accord n'y prouve rien.
  On en sort par `--unit-stat "<vis>:Rarity=N"` — et c'est ce que fait §7 ;
- **fermer le gate sur canal absent** ⇒ effet inerte, qui compterait pourtant comme « porté » dans
  les audits de couverture. Pire que l'absence. D'où le TRI-ÉTAT strict de chaque clé (`None` =
  NON MESURÉ ⇒ le gate se FERME **et le dit**, jamais un booléen deviné).

## 3bis. Les trois clés de contexte neuves, et pourquoi elles vont sur les DEUX faces

| clé | nœud natif | substrat COMBAT | substrat DÉCISION |
|---|---|---|---|
| `att_effect_names` | `EntitiesWithAnyEffect(…, [1545], Both)` | `damage_model._target_effect_names(state, att_id)` | `_shared._effect_names_of(scene, att_id)` |
| `owner_is_machine` | `IsMachine(Owner)` | `components.is_machine_of_war` (le `MachineComponent`) | `Scene.is_machine` (les `casterId` de `decisionView.mows`) |
| `cabal_valid_adjacent_to_attacker` | `AmountIsGreaterThanZero(ValidCharacter(AdjacentFriends(It)))` | `damage_model._cabal_valid_adjacent_to` | `_shared._cabal_valid_adjacent_to` |

**`onlyActive = false` est LU, pas supposé** : `EntitiesWithAnyEffectSelector$$Select` appelle
`EntityExtensions$$HasOneOfEffects(entity, query, effectTypes, onlyActive, targetType)` avec un
**zéro** en 4ᵉ argument, et `EffectTargetType.Both = 6 = 2|4` prend les deux branches du corps
(`& 2` = l'entité est CIBLE, `& 4` = elle en est la SOURCE). Le substrat port est donc le store
BRUT `EffectsState.by_unit` filtré sur le seul `consumed` — le même que le `tgt_effect_names` de
`NornCrownEffect` (#1011), interrogé ici sur l'ATTAQUANT.

**`IsMachine` est lu jusqu'au scalaire** : `IsMachineTrigger$$ShouldTrigger` →
`EntityExtensions$$IsMachine`, dont le corps entier est `<EntityType> == 6`. L'ordinal est tranché
par deux témoins indépendants du nom (`$$IsUnit` compare à `1`, `$$IsMachinePlatform` à `7`) et par
l'enum `IdunBattle.Entities.Enum.EntityType`. Attestation DSL : `docs/rl/dsl-port-attestations.tsv`.

⚠ **Réparer une seule face aurait recréé le fork prediction/combat** (#197, #950-r2) : les trois
clés sont posées par les deux foyers, avec les **mêmes noms importés depuis le module d'effet**
(jamais un littéral recopié — un cliquet le vérifie).

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

- **La MAGNITUDE des deux effets face au natif** — `#1036-r8`, `BLOCAGE: capteur`, cause MESURÉE
  au §7.
- **La patte SELF** — `Friends(Owner, AllUnits)` inclut le porteur, et la branche SOURCE d'
  `EffectTargetType.Both` le retient dès qu'il a réparé quelqu'un : le natif accorde donc le bonus
  à la MoW **quand elle attaque elle-même**. Le canal port serait `create_effect_damage_bonus_for_
  attack`, dont l'`att_ctx` ne porte NI `att_rarity` NI `att_effect_names` (~9 sites de
  construction, cf. `#1025-r1`) : en poser un seul créerait un fork silencieux. `#1036-r7`.
- **La face DÉCISION de `CabalOfSorcerers`** (`#1036-r3`) : `CabalOfSorcerersPlaybook`
  (`TriggeredAbilityNonOwnerPlaybook<CabalOfSorcerersAbility>`) surcharge
  `$$CalculateMovementUtilityInSteps`. Son corps a été lu (il rend une utilité pour une tuile
  candidate dont un voisin est Mythic+Hero+Psyker, ou est le porteur). ⚠ Son blocage d'origine
  (la rareté) est LEVÉ : `scene.ctx(uid).rarity` répond, et `Scene.is_machine` existe depuis cette
  tranche. Ce qui reste est le port du playbook lui-même.
- La branche `ifFalse` (`Unique(A + F)`) de `CabalOfSorcerers` n'est atteignable que sur un porteur
  **non-machine** : aucune des deux unités porteuses connues ne l'est. Elle est **portée telle
  quelle** et gardée offline (couple `owner_is_machine` True/False sur le même ctx), jamais
  confrontée live.

## 7. La confrontation LIVE — en régime SÉPARANT, et ce qu'elle a mesuré

Deux probes, deux bras chacun (`probe_1036r1_guardian_construct_live.py`,
`probe_1036r2_cabal_of_sorcerers_live.py`, board `MC1_67`, seed 777, session 89).

**`1548 GuardianConstruct`** — l'aura ne retient un allié que s'il porte un
`NanoscarabRepairProtocols` (1545), l'effet que la MoW pose en **castant** son active 1224. Au
tour 0 personne ne le porte : le probe **fabrique la matière qu'il mesure**.

| discriminant | témoin | mesure |
|---|---|---|
| `EntitiesWithAnyEffect(…, [1545], Both)` | le même allié, avant/après le cast | `None` → `PercentIncrease 20` |
| `Friends` + sélecteur | un allié NON réparé, même bras, même instant | `None` |
| `UnitsWithRarity(…, Mythic)` | bras `--unit-stat "orksKillaKan:Rarity=3"` (rareté mesurée = 3) | `None` |

**`1494 CabalOfSorcerers`** — le probe **DÉPLACE** une unité pour fabriquer puis défaire
l'adjacence, plutôt que de subir la géométrie de spawn.

| discriminant | témoin | mesure |
|---|---|---|
| filtre `F` (`AmountIsGreaterThanZero(ValidCharacter(AdjacentFriends(It)))`) | même attaquant, voisin à d=1 puis d=2 | `PercentIncrease 20` → `None` |
| `CurrentAttackDamageProfileIs(Psychic)` | même instant, profil `Physical` | `None` |
| `UnitsWithTraits([Psyker, Hero])` | attaquant `ultraTitus` (Hero sans Psyker) | `None` |
| `UnitsWithRarity(…, Mythic)` | bras `--unit-stat "eldarFarseer:Rarity=3"` | `None`, `att_rarity = Epic` |

**Face DÉCISION confrontée au MÊME instant** (predicteur complet) : `machine_ids = [87]`,
`Scene.is_machine(MoW) = True`, la MoW dans `effect_carrier_ids`, et le ctx de
`_apply_ally_attack_dmg_bonus` porte les **quatre** clés avec les **mêmes valeurs** que la face
COMBAT (`att_rarity`, `voisins_valides`). Aucun fork.

### Le mur restant, et il n'est PAS la rareté : le NIVEAU d'une mythique de MoW

Mesuré sur `necroReanimator` monté à `--equip-mythic …:4` (donc `TertiaryAbilityLevel = 4` écrit
dans la BC) :

- `combatSnapshot.units[].unitConfig` = `{"error": "visualId introuvable"}` — `readUnitConfig`
  filtre sur la classe `UnitComponent`, la même cécité aux Machines que #1039 a dû contourner pour
  la rareté ;
- `combatSnapshot.units[].abilityStates` et `decisionView.mows[].abilities` ne listent que les
  **ACTIVES** de la MoW (1223 / 1224), jamais sa mythique ;
- donc `UnitContext.tertiary_ability` vaut `None`, `tertiary_ability_level` vaut `0`, et
  `triggered_ability_state` retombe sur la branche PASSIVE en rendant `(0, 160)`.

⇒ **la magnitude est structurellement nulle côté port sur un runner live**, pour 1548, 1494 — et
pour tout jumeau de la famille, `1446 ElectrochaffBackups` compris, dont `#1025-r3` demande
justement une confrontation de magnitude qui butera sur le même mur.
Le port **ne replie pas** sur `effect.level` : le capteur y publie `1`, qui est le niveau de STACK
(`EffectComponent.Level`), pas un niveau d'ability — écrire `extraDmgPct[1]` là où le montage
demande `extraDmgPct[4]` serait inventer une magnitude.

Point d'ancrage NOMMÉ pour lever `#1036-r8` (fenêtre de reinject) : publier l'`AbilityState`
TERTIAIRE d'une Machine — `UnitConfiguration+0xc0` (`TertiaryAbilityLevel`) et `+0x78`
(multiplicateur), atteints par `UnitExtensions$$GetBaseUnitComponent`, exactement la voie que #1039
a prise pour `+0x80` (`Rarity`) — dans `frida/hooks/features/ai-step/rpc-snapshot.ts`.

⚠ **Ce que les deux probes fournissent au lieu de le mesurer** : le niveau d'ability, substitué au
seul canal muet (`tertiary_ability_state_of`). Tous les autres termes restent LIVE. Sans cette
substitution le port rendrait `None` **partout**, et les deux bras du régime séparant seraient
d'accord — un vert vide.

## 8. Résidus

- **`#1036-r3`** — face DÉCISION de `CabalOfSorcerers` (`CabalOfSorcerersPlaybook`). `BLOCAGE:
  aucun` depuis cette tranche (rareté ET nature d'entité disponibles côté `Scene`).
- **`#1036-r7`** — la patte SELF des deux effets (cf. §5).
- **`#1036-r8`** — le niveau d'une ability MYTHIQUE de MoW n'est publié par aucun canal live ;
  aucune magnitude d'aura de MoW n'est donc confrontable. `BLOCAGE: capteur`.
