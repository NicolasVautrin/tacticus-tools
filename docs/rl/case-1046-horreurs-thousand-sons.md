# #1046 — la chaîne des Horreurs Thousand Sons : `Split` (1156) → `FlamesOfMutation` (1160)

Deux passifs de **SUMMON**, portés ensemble parce que le natif les **enchaîne** *et* les
**factorise** : une Pink Horror qui meurt se scinde en deux Blue Horrors, dont chacune enflamme sa
tuile en mourant — et leurs deux `CreateTrigger` sont **un seul et même corps**.

| item | ability | porteurs | verdict |
|---|---|---|---|
| 1 | `TriggeredAbilityType.Split` = **1156** | `thousSmnPinkHorror`, `thousSmnPinkHorrorHSE` | **PORTÉ**, confronté live (2 faces) |
| 2 | `TriggeredAbilityType.FlamesOfMutation` = **1160** | `thousSmnBlueHorror`, `thousSmnBlueHorrorHSE` | **PORTÉ**, confronté live (2 faces) |

Foyer : `engine/runner/operations/triggers/loki/horrors.py` · registre :
`ABILITY_TRIGGERS["Split"]` / `["FlamesOfMutation"]` · cliquet :
`tests/engine/test_1046_horrors_chain_offline.py` · mesure : `probe_1046_horrors_chain.py`.

---

## 1. Le fait le plus important : **un seul corps de `CreateTrigger` pour les deux**

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FlamesOfMutationAbility$$CreateTrigger`
**n'existe pas** comme fonction nommée — et ce n'est pas qu'elle manque : elle est **dédupliquée
(ICF)** avec celle de `SplitAbility`. Trois lectures indépendantes le disent :

* `data/symbols/rnca9r7q6c/frida/methods.tsv` porte `SplitAbility.CreateTrigger` (RVA `1035a30`)
  et `FlamesOfMutationAbility.CreateBehaviour` (RVA `10359a0`) — **voisines**, dans la zone de
  `FlamesOfMutationAbility` — mais **aucune** `FlamesOfMutationAbility.CreateTrigger` ;
* le `dump.cs` Il2CppDumper leur donne **littéralement la même RVA** (`0xFAF310` sur une coupe,
  `0xFC2220` sur l'autre), au **même slot de vtable 24** ;
* `ghidra` ne nomme, comme toujours dans ce cas, qu'**un seul** propriétaire.

C'est le cas d'école du garde-fou « **l'ABSENCE d'une méthode dans les tables ne prouve RIEN** » du
`CLAUDE.md` — sauf qu'ici l'absence prouve quelque chose de **positif** : le **partage**. Conclure
« FlamesOfMutation n'a pas de trigger » aurait produit un passif inerte ; conclure « il faut le
deviner » aurait produit un gate inventé.

**Conséquence de port** : une seule base `_HorrorOnDeathAbility` porte le trigger des deux
abilities, et le cliquet joue **chaque gate deux fois** (`@pytest.mark.parametrize`).

## 2. Le trigger (partagé), relu verbatim

```
CreateTrigger() = DSLTriggers$$OnPreDeath2(triggerOnOverkill: false, triggerOnSteppable: false)
                  & DSLTriggers$$get_OwnerIsTarget
```

et `IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2(a, b)` = `OnDeathEvent(2, a, b)` :

```
On(2 = EventTriggerType.PreUnitDeath_2)   &  <YesTrigger @DSLTriggers+0x70>
  & (a == 0 ? NOT TargetIsOverkilled                       : YES)
  & (b == 0 ? NOT HasTrait(Target@+0x60, 0x1b = Steppable) : YES)
```

`IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled` =
`HasFlagAbilityTrigger(Target@<DSLSelectors+0x60>, UnitFlag.Overkilled = 8)`.

⚠ **Les deux littéraux sont `0` ici, donc les DEUX gates sont ARMÉS.** C'est l'écart avec la
famille **death-nova** (`death_nova.py`), qui passe `a = 1` et explose **même en overkill** :
recopier son `_DeathNovaAbility` tel quel aurait été **faux sur ce gate-là**. Le « Does not apply if
Overkilled » des deux textes i2 est exactement ce `a = 0`.

## 3. `Split` — le behaviour

```
SplitAbility$$CreateBehaviour(abilityState, triggerType) =
    DSLBehaviors$$If( <DSLTriggers+0x28>,
                      CreateSpawnBehavior(abilityState, autoAttack: true),
                      CreateSpawnBehavior(abilityState, autoAttack: false) )
```

**`DSLTriggers+0x28` est identifié, pas deviné.**
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` l'écrit
`new <DAT_1833ab568>(<DSLSelectors+0x30>, matchState, 0)`, et
`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` construit **la même classe avec la même
forme d'arguments** : c'est donc `IsTurnOf(Owner)`, mémoïsé une fois pour toutes. L'identité du slot
`+0x30 = Owner` est elle-même lue (`get_OwnerIsActor` = `AreEqual(+0x30, +0x40)`). Et c'est mot pour
mot l'i2 : « can immediately attack an enemy **if summoned during the Pink Horror's turn** ».

```
SplitAbility$$CreateSpawnBehavior(abilityState, autoAttack) =
    options = SpawnUnitOptions$$WithStatsFromConfig(config@this+0x20, abilityState, 0, 0)
    if (autoAttack)
        options.<+0x18> = DSLBehaviors$$PerformAIAttackFromCurrentPosition(
                              ActiveTarget@<DSLSelectors+0x68>, null, null, false)
    origin = Owner@<DSLSelectors+0x30>
    tiles  = DSLSelectors$$PickRandomly( CanAddUnit( AdjacentTiles(origin) ),
                                         amount: 2, allowDuplicates: false,
                                         maxDuplicatesAllowed: 0x7fffffff,
                                         ignoreForcedTargets: false )
    return DSLBehaviors$$Spawn(origin, tiles, GetStringConstant(config, 0 = unitId), options)
```

Le **`2` est un littéral du décompilé** : le gameconfig de `Split` ne porte **aucune** variable de
compte — seulement `summonHp` / `summonDmg` (64 paliers, tous deux dans
`variablesAffectedByRarityBonus`) et la constante `unitId = thousSmnBlueHorror`. Le palier 64 donne
1528 / 1310, soit exactement le « Blue Horror's stats: 1528 Health 1310 Damage » de l'i2.

## 4. `FlamesOfMutation` — le behaviour

```
FlamesOfMutationAbility$$CreateBehaviour(abilityState, triggerType) =
    DSLBehaviors$$AddEffect( effectType : 5 = EffectType.Fire,
                             abilityState: BaseTriggeredAbility$$get_AbilityStateReference(this),
                             source      : <ABSENT — le ctor reçoit 0 en param_4>,
                             targets     : DSLSelectors$$Tiles(Owner@<DSLSelectors+0x30>),
                             turns       : null )
```

Trois points, et chacun a un écart possible que le port aurait pu commettre :

* **la cible** — `DSLSelectors$$Tiles` alloue un `IdunBattle.Entities.Selectors.UnitsMainTilesSelector`
  = la **main tile** par entité, pas l'empreinte : « it sets **its hex** on Fire » ;
* **la source** — la surcharge employée est celle à **quatre** arguments, dont le ctor
  `AddEffectBehaviour..ctor(logger, effectType, abilityState, 0, targets, options)` passe **`0` en
  sélecteur source** ⇒ fallback natif « source absente ⇒ **la source EST la cible** », déjà porté et
  documenté sur `BrazierOfHolyFire` (`source_from_target=True`). Confondre avec le caster serait
  **invisible offline** (le caster est mort) et divergerait de la mesure live ;
* **la durée** — `turns = null` ⇒ `DefaultAmountOfRounds(5) = 2` **rounds**, convertis en tours par
  `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (facteur = nombre de joueurs).

## 5. `chance = "50"` est une constante **NON LUE** — et c'est un résultat

`abilities.FlamesOfMutation.constants.chance = "50"` existe en gameconfig. **Aucune** des quatre
méthodes de la classe native ne la lit :

| membre (dump.cs) | corps |
|---|---|
| `get_AllowForDeadOwner` (slot 21) | trivial, partagé |
| `CreateTrigger` (slot 24) | **le corps de `Split`** — qui n'a pas de `chance` en config |
| `CreateBehaviour` (slot 26) | lu ci-dessus : aucun `GetNumberConstant` |
| `.ctor` | trivial, partagé |

et en amont, `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$ShouldTrigger` délègue au trigger
de `this+0x58` tandis que `$$Execute` exécute le behaviour : **aucun gate de chance générique** à cet
étage. Le texte i2 n'en mentionne pas non plus (« When this unit gets defeated it sets its hex on
Fire »).

⇒ **porter un `Maybe(50)` ici serait un gate INVENTÉ** (anti-pattern §2.1 du skill). Le cliquet garde
ce résultat : 200 montages non-overkill posent le feu **200 fois**.
**Reste non éliminé** (résidu `#1046-r1`) : un consommateur **VIEW**
(`IdunBattle.View.AbilityConfigs.Loki.FlamesOfMutationVisuals$$ExecuteInternal`) pourrait la lire —
ce qui serait sans effet sur l'état.

## 6. Confrontabilité — le montage, et pourquoi le premier a échoué

Les quatre porteurs sont des **summons** : absents de `--list-pool`, ils arrivent par leur
**summoner**. Balayage du gameconfig (toutes les abilities, pas seulement celles attribuées) :

| ability | constante | summon | porteur au pool ? |
|---|---|---|---|
| `MasterOfTheTutelaries` | `unitId` | `thousSmnPinkHorror` | **oui** — `thousInfernalMaster` (Abraxas) |
| `MasterOfTheTutelaries` | `unitId_2` | `thousSmnScreamer` | (l'autre voie, déjà portée #202-C) |
| `Possession` | `unitId_2` | `thousSmnBlueHorror` | **oui** — `blackPossession` (Archimatos) |
| `EnvAllyAndEnemyNpcs:WarpSurge` | `unitId_2/3` | les deux variantes `HSE` | env |

**Montage retenu** : `rl_duel build --board MC1_67 --crit "0,0"` avec Abraxas **côté adverse**
(`--a-units`), un second contrôleur `attach --team 2` pour caster nous-même, et `--place` pour
rapprocher les camps. Abraxas caste `MasterOfTheTutelaries` (tile-target) → Pink Horror ; on la tue
avec un dégât **choisi**.

⚠ **Le premier montage a rendu un faux négatif, et la cause est le seuil d'overkill.**
Laisser l'IA orque tuer la Pink Horror (`u77->u103 3589 KILL`) n'a produit **aucune** Blue Horror —
il aurait été facile d'en conclure « le port ou le natif ne fire pas ». La lecture de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` donne le critère :
`pct = (dmg − PV)/PV × 100` ; overkill si `pct >= overkillDmgPctOfHealth` (= **100**, donc
`dmg >= 2×PV`) **ou** si le coup létal est un **crit**. Le tueur bridé (`--crit "0,0"`) et le choix
de la position d'attaque sont donc les deux leviers qui rendent le montage **déterministe**.

## 7. Ground truth live (runner 446, board MC1_67)

| face | stream natif | port |
|---|---|---|
| `Split`, **non**-overkill | `Attack_WasOverkill=0` → **2** `AddUnit` (e=115, e=118), `Unit_Parent_Id=104`, `Unit_Foot_Tile_Id_1=33`/`34` (adjacentes), `UnitStats_TriggeredAbility_Id=**1160**` | 2 summons `thousSmnBlueHorror`, tuiles adjacentes, `parent_id` du porteur |
| `Split`, **overkill** | `Attack_WasOverkill=1` → `RemoveUnit Unit_WasOverkilled=1`, **0** `AddUnit` | payload vide |
| stats du summon | `UnitStats_MaxHealth=**2093**`, `UnitStats_Attack=**1795**`, sous `VariableMultiplierPercentage=180` | **2093** / **1795** (`summonHp[49]=1163`×180 %, `summonDmg[49]=997`×180 %) |
| `FlamesOfMutation`, **non**-overkill | `ActivateEffect e=**33**` + `ReceiveEffect e=33 Effect_SourceId=**33** Effect_RemainingTurns=**4**` (33 = la tuile du mourant) | effet `5` sur la main tile, **source = la tuile**, **4** tours |
| `FlamesOfMutation`, **overkill** | `Attack_WasOverkill=1` → aucun effet de tuile | payload vide |

⚠ **Le `2` de durée du premier relevé offline était un artefact du MONTAGE, pas du port.** Un `State`
synthétique n'a pas de `turn_order_player_count` ⇒ `ConvertRoundsToTurns` retombe sur le facteur 1 et
rend `2` là où le live rend `4`. La décomposition par étage (`DefaultAmountOfRounds(5) = 2` **rounds**
côté port **et** côté natif, puis conversion) a montré que l'écart était dans le **substrat du
montage**. Poser `turn_order_player_count = 2` (un duel) dissout l'écart : `2 × 2 = 4`.

## 8. Ce qui n'est PAS couvert

* les variantes **`HSE`** (`thousSmnPinkHorrorHSE`, `thousSmnBlueHorrorHSE`) ne sont posées que par
  `EnvAllyAndEnemyNpcs:WarpSurge` (environnement) : **non confrontées**. Elles partagent le même
  passif et le même kit — le port ne les distingue pas, et n'a aucune raison de le faire ;
* la voie **`Possession`** (Archimatos → Blue Horror directement, sans passer par `Split`) n'a pas
  été jouée live : elle mène à la même entité, avec le même passif ;
* l'**ORDRE** relatif du spawn de `Split` vis-à-vis des autres consommateurs d'`On(PreUnitDeath_2)`
  de la même mort (death-novas) n'est pas tranché — même résidu d'ordre intra-vecteur que
  `MasterOfTheTutelaries` ;
* la **chance = 50** : voir §5 (résidu `#1046-r1`).

## 9. Pointeurs

`docs/rl/summons-registry.tsv` (lignes `thousSmn*`) · `docs/rl/passive-ability-coverage.md` (l'audit
qui a nommé les deux GAPS) · `docs/rl/case-291-summon-activation.md` (on OBSERVE un summon, on ne le
COMMANDE pas) · `engine/runner/abilities/behaviours/summon.py` (les feuilles `Spawn` /
`PerformAIAttack`) · `engine/runner/operations/triggers/loki/death_nova.py` (la famille voisine, au
gate overkill **inverse**).
