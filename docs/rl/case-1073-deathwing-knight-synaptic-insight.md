# case-1073 — `DeathwingKnight` et `SynapticInsight` : deux `GAP-MENTION` `S?`, deux jumeaux npc

Deux passifs `S?` de `passive-ability-coverage.md`. L'audit rendait `S?` parce que son graphe de
summon ne balaie que les abilities **des unités** — pas parce que le porteur serait inatteignable.
Même forme qu'en #1052, et même chemin de sortie : le **jumeau npc**, identifié par le `visualId`
du summon.

## 1. Les porteurs, ventilés (balayage EXHAUSTIF du gameconfig : toute chaîne de l'arbre)

| passif | summon | npc jumeau (`visualId`) | invocateur du summon | chemin retenu |
|---|---|---|---|---|
| `DeathwingKnight` (1510) | `darkaSmnTerminator` | `darkaNpc3Terminator` | **DEUX** : `InstrumentsOfVengeance` — active du **boss npc** `darkaBossLion` (Lion El'Jonson) — et `PowerUp_SummonSpawn_darkaSmnTerminator`, passif d'une pseudo-unité de **survival** (`battles.battleSets.survival_may_2026`) | **npc**, `--explicit-stats darkaNpc3Terminator:45` |
| `SynapticInsight` (1193) | `tyranSmnBarbgaunt` | `tyranNpc5Barbgaunt` (+ `tyranNpc5BarbgauntSurv`) | `EnvFactionSummons:Tyranids` — ability **d'ENVIRONNEMENT** de live-event, portée par **AUCUNE** unité (comme `ThousandSons` en #1052) | **npc**, `--explicit-stats tyranNpc5Barbgaunt:45` |

⚠ Contrairement à #1052, `DeathwingKnight` a bien un invocateur porté par une unité — mais elle est
`npc` (le boss). L'audit ne le voit pas davantage : son graphe part des unités **du pool**.

## 2. Ce qui existait au registre, établi PAR EXÉCUTION

**Rien.** Les deux noms étaient `GAP-MENTION` au sens strict : `ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`,
`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`, `ABILITY_OWNER_EFFECTS`, `ABILITY_CLASSES`,
`TRIGGERED_ABILITY_BEHAVIOURS`, `CUSTOM_NORMAL_ATTACK_BY_PASSIVE` — **8 registres, 0 entrée**. Les
seules occurrences dans `engine/` étaient les **membres de mirror d'enum** et une **prose** de
`playbook/adjacent_unit_preference.py` (« `DeathwingKnightPlaybook` … n'est PAS portée ici »).

## 3. `DeathwingKnight` — un jumeau STRICT, à trois valeurs près

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DeathwingKnightAbility` dérive de
`…DeathwingAbility` (`frida/classes.tsv`) et le `global-metadata.dat` lui déclare **exactement**
`[GetEffectType (slot 35), .ctor]`. `$$GetEffectType` a pour corps ENTIER `return 0x5e8` (= 1512).
Trigger, behaviour et `GetEffect` viennent du parent, **au corps près** — donc
`On(9 = Attack) & get_OwnerIsTarget & WasBlock()` puis
`If(HasEffect, IncreaseEffectLevel(+1, SANS cap), AddEffect(turns = TurnsFromRounds(1)))` (#932).

⚠ **Il n'existe AUCUNE classe native `DeathwingKnightEffect`.** Les deux `EffectType` sont servis
par le MÊME `IdunBattle.Entities.Effects.Loki.DeathwingEffect`, et c'est LU dans les deux fabriques
de l'`EffectsDatabase` :

    …u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_339 -> DeathwingEffect..ctor(this, 0x4dd = 1245)
    …u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_340 -> DeathwingEffect..ctor(this, 0x5e6 = 1510)

Le seul paramètre du `.ctor` est `triggeringAbilityType` (`frida/methods.tsv`) : **seule la config
que `ConfigVar` indexe change**. D'où un port en sous-classe à `ABILITY_ID` près.

⚠ **QUATRE ordinaux, QUATRE enums** : `TriggeredAbilityType 1245`/`EffectType 1318` = `Deathwing`,
`TriggeredAbilityType 1510`/`EffectType 1512` = `DeathwingKnight` — et `EffectType 1510` est
`MastersOfManoeuvre`, sans aucun rapport.

⚠ L'i2 de `DeathwingKnight` dit « the damage he deals is increased » là où celui de `Deathwing` dit
« with melee or *Plasma Cannon* attacks ». **Le corps natif est LE MÊME** (`IsMeleeAttack | NOT
IsNormalAttack`, corps partagé) : la prose diverge, le code non.

## 4. `SynapticInsight` — owner-effect d'INIT + canal COUPS

`$$CreateTrigger` **n'existe pas comme symbole** (ICF). Le bloc `methodPointers` du PE — calage
retenu par **maximisation des concordances**, pas par la première occurrence trouvée — y donne le
corps de `…SummaryExecutionAddBaseEffectAbility$$CreateTrigger` = `return <DSLTriggers+0x30>`, écrit
par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` comme
`EventTrigger(0x21 = AbilityInit) & <+0x70 = YesTrigger> & get_OwnerIsActor`, c.-à-d.
`On(AbilityInit, ownerNeedsToBeAlive: false) & get_OwnerIsActor` → canal **O**.

    CreateBehaviour = AddEffect(0x4cf = 1231, AbilityStateReference, targets = Owner@<Sel+0x30>,
                                turns = null)                                    -> PERMANENT

    …SynapticInsight_ExtraHitsEffect$$CreateEffectHitsBonusForAttack =
        EffectBonus.ForAddition(
            get_OwnerIsCaster & IsRangedAttack()
            & (   Any( AdjacentFriends(unit = Owner@<Sel+0x30>, unitTile = Target@<Sel+0x60>,
                                       unique: true),
                       HasFaction(It@<Sel+0x68>, UnitFaction.Tyranids = 0xc, 3) )
                | IsInTeamSynapseRange( Target@<Sel+0x60>, Owner@<Sel+0x30> ) ),
            ConfigConst(0x2b = extraHit) )                                        # = 2

⚠ **AUCUN nœud `IsNormalAttack`** — ses trois voisins de forme du même canal
(`PowerTrip_FullHealth`, `VoltagheistField_ExtraHit`, `Waaagh_ExtraHits`) en portent un.

⚠ **DEUX surcharges tranchées par la CIBLE DU `call rel32`, pas par l'arité** (les deux candidates
ont la même) : `AddEffect(…, turns: System.Nullable<System.Int32>)` (`+0x56`) et
`AdjacentFriends(unit, unitTile, unique)` = **variante B** (`+0xe2`). Conséquence load-bearing :
**l'ancre géométrique est la CIBLE du coup**, la référence d'équipe est le PORTEUR. Lire la variante
A donnerait `selectionType = 1 = OnlyAlive`, l'inverse exact du filtre natif.

⚠ **Le porteur n'est PAS exclu** de `AdjacentFriends` : le natif ne soustrait que `unitTile`.
Corollaire de montage : un porteur adjacent à sa propre cible arme le disjoint tout seul et détruit
le témoin — d'où un porteur placé à distance 3.

⚠ La classe d'effet déclare AUSSI `CreateActiveCondition` (`<DSLTriggers+0x40>` = constante VRAIE)
et `CreateTargetSelector` (`<DSLSelectors+0x30>` = `Owner`, donc SELF-effet) — **absentes de
`frida/methods.tsv`**, corps fondus par l'ICF. Le seed `ABILITY_INIT_OWNER_EFFECTS` est donc un
**FILET idempotent** : mesuré, le mutant `seed` ne fait rien bouger.

## 5. Confrontation live

`SynapticInsight` — `probe_1073_synaptic_insight.py`, `MC1_67`/4321, porteur
`tyranNpc5Barbgaunt:45` à distance 3 de sa cible `orksNob` :

| régime | montage | natif | port |
|---|---|---|---|
| `temoin` | personne près de la cible | **3** coups, 20341 | idem |
| `adjacent` | 2ᵉ Barbgaunt (Tyranide, **sans** `Synapse`) collé à la cible | **5** coups, 35776 | idem |
| `synapse` | `tyranParasite` (`Synapse`) à distance **2** de la cible | **5** coups, 35776 | idem |

**Le NATIF sépare lui-même les trois régimes** (3 / 5 / 5) : le probe l'exige (`natif_separe`) et
rend `indisponible` sinon — un accord en régime dégénéré ne prouve rien.

Mutants : `effet` → **DIVERGE** sur `adjacent` **et** `synapse` (5 → 3) ; `ctxAdj` → DIVERGE sur
`adjacent` **seul** ; `ctxSynapse` → DIVERGE sur `synapse` **seul** ; `seed` → aucun effet (filet).
Les deux disjoints sont donc câblés chacun sur SON substrat, indépendants — exactement le
`op_BitwiseOr` natif.

⚠ **Les deux mutants `ctx*` ont d'abord rendu un FAUX VERT**, et la cause est celle du CLAUDE.md :
`damage_ops/normal.py` et `…/ability.py` font `from …damage_model import build_hits_board`
(**forme A**), donc substituer `damage_model.build_hits_board` **ne mord pas**. Le probe patche
désormais le binding des **consommateurs** et **publie le compte d'appels** (`mutant_appels`).

`DeathwingKnight` — `probe_932_deathwing.py --variante knight` (un seul corps natif, un seul probe),
face DÉFENSE, porteur `darkaNpc3Terminator:45` :

| bras | natif | port | niveau natif/port | mutants |
|---|---|---|---|---|
| `defense` | 1515 · 9531 | idem | 2 / 2 | `effet` +1168 · `trigger` +1168 (niveau `None`) |
| `chaos` | 7513 · 2908 | idem | 3 / 3 | `double` +584 |
| `amiDA` | 1375 · 12252 | idem | 2 / 2 | `double` +1168 |

## 6. Défaut de HARNAIS réparé — `--crit`/`--block-*`/`--hp-*` étaient INERTES sur `--explicit-stats`

`rl_duel` compare `u["VisualId"]` aux **unitIds** des rosters. Or `catalog_inject.augment` écrit
`Id = 'darkaNpc3Terminator:45'` et **`VisualId = 'darkaNpc3Terminator'`** : la comparaison ne pouvait
jamais tenir. Mesuré — `--block-target 100,50` ne posait AUCUN blocage forcé (niveau **1** au lieu de
**2** après deux attaques, dégât 552/109 au lieu de 1515/9531), et le bras `attaque`, qui dépend de
`--block-player`, rendait `indisponible` pour une cause étrangère à la mécanique. Réparé par
`_visual_set` (réduction au dernier `:`, sur-ensemble, aucun appelant existant ne change).

## 7. Résidus

* **`#1073-r1`** — face **ATTAQUE** de `DeathwingKnight` **NON CONFRONTÉE** : le montage
  `attaqueChaos` diverge, mais **en amont du port**. Décomposé : avec l'effet RETIRÉ (`--mutate
  effet`) l'écart PERSISTE (natif 1245, port 5357), et le per-coup dit tout — `natif_hits = [1245]`,
  `port_hits = [1245, 0]` : **le coup joué des deux côtés est bit-exact**, le port en émet un SECOND
  que le natif n'émet pas. C'est une divergence de **compte de coups** sur porteur
  `--explicit-stats`, pas une divergence de magnitude. La face partage 100 % de son code avec
  `Deathwing` (EGAL live sur `attaque` et `attaqueChaos`, variante `baraqiel`) à `self.ABILITY_ID`
  près — et `ABILITY_ID` est exercé bit-exact par la face DÉFENSE du knight.
* **`#1073-r2`** — face **PRÉDICTION** de `SynapticInsight` câblée (`Scene.synaptic_insight_
  adjacent_tyranid` + le substrat synapse dans le board de coups) mais **non confrontée live**. La
  face COMBAT l'est, bit-exact, sur les trois régimes.
