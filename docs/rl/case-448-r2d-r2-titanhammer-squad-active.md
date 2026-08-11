# #448-r2d-r2 — `1231 TitanhammerSquad`, l'ACTIVE de `astarLysander`

Build `rnca9r7q6c`. Porteur `astarLysander` « Lysander » (Adeptus Astartes / Imperial Fists,
HERO **hors pool** → injection catalogue). Port : `engine/runner/abilities/astartes.py`.
Mesure : `scripts/python/probe_448r2dr2_titanhammer_active.py`. Garde :
`tests/engine/runner/test_448r2dr2_titanhammer_active_live.py`.

## 1. Ce n'est pas une ability de soin

L'audit `combat-ability-coverage.md` la classait `HEAL`, et c'était la dernière de cette colonne.
Le décompilé dit autre chose : **le soin est le 2ᵉ des QUATRE volets**. `1231` est une ability de
**téléportation de groupe** — elle marque une tuile d'arrivée, soigne, buffe le *block damage*, et
arme le déplacement des porteurs.

`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour`, LU :

```
groupe = Caster@<Sel+0x48>
         op_Addition
         Filter( SurroundingFriends(Caster@<Sel+0x48>, GetNumberConstant(0x16 range),
                                    unique = true, unitSelectionType = 3),
                 HasTrait(ActiveTarget@<Sel+0x68>, 0x40f = TerminatorArmour) )

b1 = AddEffect(0x623 _TargetTile, stateRef, source = Caster, targets = Target@<Sel+0x60>,
               Sum(TurnsUntilUnitOwnerTurn(groupe), <DSLFormulas+0x20 = Direct(1)>))
b2 = Heal(Caster, groupe, Get(GetVariableForLevel(0x20 hpToHeal)), ForHeal)
b3 = AddDynamicStatModifierEffect(
         Filter(groupe, AmountIsGreaterThanZero(StatAmount(ActiveTarget, 7 BlockChance,
                                                           0 Current, null, 0 Any))),
         Caster, 0x624 _ExtraBlockDamage, stat 8 BlockDamage, stateRef,
         Sum(TurnsUntilUnitOwnerTurn(ActiveTarget), TurnsFromRounds(1)), isHidden = 0)
b4 = AddEffect(0x625 _TeleportingIn, stateRef, source = Caster,
               targets = Filter(groupe, NOT HasFlag(ActiveTarget, 1 ArrivedAtFinalTile)),
               Sum(TurnsUntilUnitOwnerTurn(ActiveTarget), <DSLFormulas+0x20>))

Execute( ((b1 & b2) & b3) & b4 )
```

`$$GetCurrentlyAffectedFriends` **est** le sous-arbre `Filter(SurroundingFriends(…), HasTrait(…))`,
reconstruit à l'identique — c'est ce qui atteste que le groupe est un sous-arbre nommé, pas un
découpage inventé.

**Le second terme des `Sum` de b1 et b4 n'est PAS un `TurnsFromRounds`** : c'est le champ
`<DSLFormulas+0x20>`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor` établit ces cinq champs sans
ambiguïté (`+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`) — donc
`Direct(1)`, déjà en TOURS. Celui de **b3**, lui, est bien un `TurnsFromRounds(1)`, donc il traverse
`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`. Confondre les deux raterait d'un tour
sur b3 dès que le facteur de conversion vaut ≠ 1.

**Les slots de sélecteur sont LUS, pas devinés.** `DSLSelectors+0x48/+0x60/+0x68/+0x78` =
`DSLFactory+0x160/+0x178/+0x180/+0x190` (décalage `0x118`), soit `Caster`, `Target`, `ActiveTarget`,
`TargetTiles`. Cinq points de contact concordants dans le build : `+0x50`/`+0x58` reçoivent la
**même classe** (⇒ `CasterTile`/`CasterTiles`), `EffectSource(<Sel+0x38>)` et
`Contains(<Sel+0x78>, …)` dans
`IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`
(⇒ `Effect`, `TargetTiles`), et l'usage de `+0x48` comme `healer`/`source`.

## 2. Le masque, et le critère qui a tranché la surcharge

`$$.ctor` appelle `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Le build en porte **trois**.
Le critère employé est la **XREF ENTRANTE du call-site** : l'adresse appelée est celle dont la liste
de xrefs contient `TitanhammerSquadAbility$$.ctor`, et c'est la surcharge PLEINE
`(isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
getDynamicInvalidTargetReason)` — les deux autres (`(template)` et `(template, additionalRules)`)
ne le référencent pas.

| argument | valeur lue | port |
|---|---|---|
| `isSelfCasting` | `0` | `self_cast=False` |
| `range` | `<TargetingRange statics>+0x48` | `RANGE_WHOLE_BOARD` |
| `forceMeleeTarget` | `1` | `RANGED_BOOL_FALSE` |
| `rules` | **`0x6001042`** | `TargetMatchesDynamicRule \| TargetIsTile \| TargetTileIsFree \| AllowObscuredTarget` |
| les deux délégués | `null` | *(cf. ci-dessous)* |

`statics+0x48` est lu dans `IdunBattle.Core.Services.TargetingRange$$.cctor` : `+0x48 = 1`
(`onlyAdjacent = RangedBool.False`) et `+0x4c = 0x100`, dont l'octet [1] est `useWholeBoard = true`.

`AbilityAttackType` = 3ᵉ argument d'`AActiveAbility$$.ctor(this, &opts, 2)` = **`Others`**.

⚠ **Les deux délégués sont NULS au ctor et la règle dynamique est quand même ARMÉE.**
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` reconstruit les deux délégués sur les slots de
vtable `this+0x470`/`this+0x480` et les écrit en `this+0xa0`/`this+0xa8` — inconditionnellement,
après avoir recopié les `TargetingOptions` reçues. Le `null` du ctor d'ability ne dit donc rien ;
c'est le bit `TargetMatchesDynamicRule` qui décide, et il est posé.

## 3. `GetDynamicInvalidTargetReason` — polarité lue au DÉSASSEMBLAGE

```
tile    = CollectionExtensions.IsNullOrEmpty(targetTiles) ? null : targetTiles[0]
enemies = battleQuery.<slot 0x7f>(tile, caster, true)      // GetAdjacentEnemies
return enemies.Count >= 1 ? 0x40000000000 : 0              // TargetIsNotAdjacentToEnemy
```

Le décompilé Ghidra rend `uVar3 = 0x40000000000; if (iVar2 < 1) uVar3 = 0;` — forme qui se lit mal.
Le désassemblage tranche : `test eax,eax ; mov rcx, 0x40000000000 ; cmovle rcx, rdi` avec `rdi = 0`.
Donc **un ennemi adjacent à la tuile visée rend la règle brisée** : on ne se téléporte pas au
contact. `0x40000000000` = 2⁴² = `TargetingRule.TargetIsNotAdjacentToEnemy`.

Le slot est LU (`data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 127
GetAdjacentEnemies`, 3 arguments), et la surcharge est celle dont la signature colle au call-site
(`from:IEntity, unit:IEntity, ignoreSteppables:bool`).
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` se décompose en
`GetUnitsOnTiles( IterateAdjacentTiles(from, null, 1, 1), null, <camp adverse de unit>,
ignoreSteppables )` — centre INCLUS, steppables exclues.

## 4. La découverte qui n'était dans aucune table : 1231 ne termine PAS le tour

`TitanhammerSquadAbility` n'expose que **quatre** méthodes dans `frida/methods.tsv` comme dans
`ghidra/functions.tsv` (`.ctor`, `ExecuteBehaviour`, `GetCurrentlyAffectedFriends`,
`GetDynamicInvalidTargetReason`). C'est précisément le faux négatif documenté au CLAUDE.md : les
corps de `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag` sont des **retours constants**
(`return <DSLTriggers+0x40/+0x48>`), donc **FOLDÉS** par IL2CPP et invisibles sous le nom de leur
classe.

**Établi par MESURE LIVE** (board `MC1_67`, seed 777) :

| | après le cast natif de 1231 | témoin (`finish` d'un allié, MÊME runner) |
|---|---|---|
| flags | `[]` | `ArrivedAtFinalTile, TurnFinished, NoActionAvailable` |
| `toActivate` | contient toujours le caster | l'allié en sort |

Le canal de flags est donc **audible**, et le `[]` du caster est un fait. C'est cohérent avec la
mécanique : l'ability arme une téléportation, l'unité doit encore pouvoir bouger vers la tuile
marquée.

**Conséquence, et c'est ce qui rend l'entrée load-bearing** : sans elle le port publiait
`UnitFinishedTurn`, ce qui déclenchait son propre
`TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn` (#448-r2d) et **retirait aussitôt le `1573`
du caster** — l'ability perdait sa raison d'être, sans erreur, sans crash, et sans qu'aucun test ne
rougisse. D'où les deux entrées dans `NO_END_TURN_ABILITY_TYPES` et
`NO_ABILITY_USED_FLAG_ABILITY_TYPES`.

## 5. La magnitude du `1572`, et ce qui reste ouvert

Aucune classe d'effet native `TitanhammerSquad_ExtraBlockDamageEffect` n'existe : `1572` est une
instance **générique** construite par
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_565` →
`DynamicStatModifierEffect(AbilityType(0x4cf = 1231), variableType = 0x14 = blockDmg,
isNegative = 0, canBeImmuneTo = 0)`. L'`AbilityType` est **lu au désassembleur** (`mov edx, 0x4cf` à
l'entrée de la lambda), Ghidra perdant l'immédiat dans le décompilé. La magnitude sort du corps
générique `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` =
`ConfigVar(AbilityOrEffect(1231), EffectSource(Get(effect)), 20)`, signée par `isNegative`.
Port : `engine/entities/effects/loki/titanhammer_squad.py` (canal eager `applied_stat_mods` /
`reverted_stats`, même *mold* que `MyWillBeDoneOverlord_ExtraDamage`).

**Résidu ouvert `#448-r6` — la durée par cible.**
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` écrit l'entité courante dans
`AbilityEntities+0x20` **avant** d'évaluer son champ `+0x78` (le nœud `turns`) : le
`TurnsUntilUnitOwnerTurn(ActiveTarget)` de b3/b4 y vaut donc la valeur de LA cible en cours. Le port
l'évalue une fois sur le SET des cibles — ce qui est exactement le `Max` que fait
`TurnsUntilUnitOwnerTurnFormula$$Calculate`, donc identique dès que le set est homogène. Il l'est
structurellement dans tout régime constructible (duel à deux joueurs, cibles = alliés du joueur
courant ⇒ 0 partout), et c'est **pour cette raison** que l'écart n'est pas observable aujourd'hui.

## 6. Ce que le témoin discrimine, et ce qu'il ne discriminait pas

Le probe confronte le port au natif **terme à terme** sur le même état de départ : tuiles portant
`1571`, effets `{1571, 1572, 1573}` par unité, PV. Deux couples nominaux (`MC1_67`/777,
`C3_26`/31337) plus un **troisième couple CRAFTÉ**.

Le couple crafté n'est pas un confort : **aucun régime nominal n'exerce les deux gates internes**.
Toutes les unités portent leurs items BiS (donc `BlockChance > 0` ⇒ le gate de b3 ne retire jamais
personne) et personne n'a bougé (donc pas d'`ArrivedAtFinalTile` ⇒ le gate de b4 non plus). Mesuré :
les mutants 2 et 3 étaient **VERTS**. Le craft force la configuration — `BlockChance = 0` sur un
terminator via `--unit-stat`, et l'autre **BOUGE** vers une tuile libre choisie pour qu'il **reste
dans le rayon du caster** (un premier essai l'en avait sorti : c'était alors la PORTÉE qui
l'excluait, pas le gate, et le mutant restait vert). Résultat mesuré sur ce couple : un terminator
porte `1572` seul, l'autre `1573` seul, le caster les deux — les trois volets sont séparés.

Le probe **rougit lui-même** si sa propre discrimination retombe : aucune unité soignée, aucun
membre à `BlockChance = 0`, aucun porteur d'`ArrivedAtFinalTile`, ou porteur du flag hors du rayon.

**Les cinq mutants et leur morsure** (chacun désarme une clause ; tous rougissent) :

| # | clause désarmée | ce qui casse |
|---|---|---|
| 1 | `HasTrait(TerminatorArmour)` sur le groupe | l'alliée sans le trait est soignée et reçoit `1573` |
| 2 | `BlockChance > 0` (b3) | `1572` posé sur le terminator à `BlockChance = 0` |
| 3 | `NOT ArrivedAtFinalTile` (b4) | `1573` posé sur le terminator qui a bougé |
| 4 | `op_Addition` du caster | le caster n'est ni soigné ni affecté |
| 5 | `1571` sur l'unité au lieu de la TUILE | aucune tuile marquée, le caster porte `1571` |

**Non couvert, nommé** : la durée en tours des trois effets (`decisionView` ne publie pas le
`remaining` par instance sur ce canal, et les trois `TurnsUntilUnitOwnerTurn` valent 0 dans tout
régime constructible — un port qui les collapserait à 0 serait vert ici) ; le **régime multi-joueurs**
(cf. `#448-r6`) ; et la face **DÉCISION playbook** (`TitanhammerSquadPlaybook$$GetUtility` /
`$$GetCustomUnitOrderUtility` / `$$IsValidTileForAbility`, non portés — le seed BC porte pourtant
déjà leurs poids `TitanhammerSquad_ChanceToUse`, `_LikesTerminatorFriendsInRange`,
`_LikesToGoFirst`).

Ce qui **est** couvert côté décision : le pool de tuiles du natif (`abilityTargets`) est confronté
au gate du port sur les deux boards — **0 refus** côté port sur 51 et 15 tuiles —, et le gate
dynamique est exercé (il refuse 8 et 14 tuiles hors-pool pour `TargetIsNotAdjacentToEnemy`).
