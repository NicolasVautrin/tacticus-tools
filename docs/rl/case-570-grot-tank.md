# #570 — `1057 GrotTank` : le spawn, et l'étage `StatModifierFormula` qui manquait sous lui

**Verdict : PORTÉ, deux faces, confronté live.** L'ability était un **no-op silencieux** (absente
d'`ABILITY_CLASSES` → `AbilityHandler.visit_ActiveAbilityMessage` l'ignorait : 0 summon, 0 dégât,
aucune erreur), alors que la face DÉCISION pouvait la choisir.

## 1. La catégorie « SUMMON » est JUSTE et n'en dit qu'un cinquième

`IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$ExecuteBehaviour` n'a **qu'un**
`AActiveAbility.Execute` — pas de `Group`, pas d'`ExecuteAtomic` — mais il compose **cinq**
mécaniques dans les options de spawn :

| # | nœud natif | état du port avant #570 |
|---|---|---|
| 1 | `DSLBehaviors.Spawn(Caster@0x48, Target@0x60, GetStringConstant(unitId), opts)` | feuille `Spawn` existante |
| 2 | `SpawnUnitOptions.WithStatsFromConfig(config, abilityState, abilitiesLevel, null)` | porté (`build_summon_context`) |
| 3 | `abilitiesLevel = DSLFormulas.AbilityLevelAmount(Owner@0x30, <ce type>)` | == le niveau déjà lu (cf. §4) |
| 4 | `opts+0x28 = [StatModifierFormula(Health, Initial, TankHealth(), null)]` | **AUCUN mirror** |
| 5 | `opts+0x18 = DSLBehaviors.PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` | feuille `PerformAIAttack` existante |

Le tooltip i2 s'apparie **nœud par nœud** : « Calls in a Grot Tank in an adjacent free hex » = (1) +
le masque `TargetIsTile | TargetTileIsFree` ; « cannot move in its first turn, but can immediately
attack an enemy in range » = (5) puis le `FinishUnitTurn(spawned, isTerminated: true)` de
`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` (#291, déjà porté) ; « 84 Health +12 for each
round that has started 30 Damage 24 Armour » = (4) + (2) **au niveau 2** (`summonHp[1] = 84`,
`extraHp[1] = 12`, `summonDmg[1] = 30`, `summonArmor[1] = 24`).

## 2. `TankHealth` — l'étage neuf

`GrotTankAbility$$TankHealth(abilityState)`, mirror ligne à ligne :

```
extraHp  = config.GetVariableForLevel(AbilityVariableType.extraHp,  abilityState)   // 0x1e
rounds   = DSLFormulas.RoundsStarted(Caster@0x48)
perRound = DSLFormulas.Multiply(rounds, DSLFormulas.Direct(extraHp))
summonHp = config.GetVariableForLevel(AbilityVariableType.summonHp, abilityState)   // 0x29
return     DSLFormulas.Sum(DSLFormulas.Direct(summonHp), perRound)
```

Les **deux variables sont lues à la CONSTRUCTION** de l'arbre (le natif emballe le résultat de
`GetVariableForLevel` dans un `Direct`) ; seul `RoundsStarted` est évalué au spawn. Le sélecteur est
`DSLSelectors+0x48` = **Caster** — la somme porte donc sur UNE unité, le compteur de tours du Big
Mek, pas sur une manche globale.

**Deux mirrors neufs** : `StatModifierFormula` (`behaviours/summon.py`) et le volet FORMULE de
`SpawnUnitBehaviour$$GetStatsToOverride`. La liste native a **deux volets, dans cet ordre** :
`options+0x20` (les `StatModifier` littéraux de `SetStatFromConfig` — déjà portés par
`build_summon_context`) **puis** `options+0x28` (les formules). L'ordre est **load-bearing** :
`FillUpStatComponent$$ApplyModifier` case `StatPart.Initial` **ÉCRASE** (`+0x10`, `+0x14` et `+0x18`
reçoivent tous la valeur), donc sur un même `StatType` la dernière entrée gagne — et GrotTank pose
précisément un 2ᵉ `Health.Initial` par-dessus celui de `summonHp`. `GetStatsToOverride` est appelé
**une fois**, avant l'énumérateur de tuiles.

## 3. Le bug que le premier passage du probe a trouvé

`Target@0x60` rend **UNE entité**, pas une liste. La feuille `Spawn` faisait
`for t in tiles` sur un dict → elle itérait ses **CLÉS** → zéro tuile, **spawn silencieusement
absent**. Mesure : natif `orksNpc3GrotTank` en (1,1) `hp=7977`, port `spawned=[]`.

S'y ajoute que `SpawnUnitBehaviour$$Execute` ne consomme **jamais** l'élément tel quel : sur chaque
élément il enchaîne `GetMainTile(...)` puis `get_Id` (et sa branche multi-hex passe par
`GetTileIds`, qui fait la même paire d'appels). La feuille normalise donc par `main_tile_id` —
**idempotent** sur les six call-sites antérieurs, qui donnent déjà des ids de tuile.

## 4. Ce qui a été LU et qui contredit l'intuition

- **`ABILITY_ATTACK_TYPE` = `Others` (2)**, littéral relu dans `GrotTankAbility$$.ctor`
  (`AActiveAbility..ctor(this, &opts, 2)`). Les quatre autres SUMMON qui font attaquer leur
  invocation (`ScarabHive` 1007, `SendInTheNextWave` 1016, `Incursion` 1021, `Poxwalkers` 1040)
  valent tous `1 = SummonAndAttackTarget`. La différence lue : ces quatre-là font frapper **la cible
  du cast**, GrotTank cible une **tuile** et laisse l'IA choisir.
- **`abilitiesLevel` (`opts+0x30`) n'exige PAS `Spawn.ability_state`** : `AbilityLevelAmount(Owner,
  <ce type>)` est la même grandeur que l'`abilityState.level` que la feuille lit déjà dans
  l'`active_ability_level` du caster. Le champ du port sert à exprimer un `AbilityState` **étranger**
  (la mine Haywire posée par un passif).
- **`TARGETING_OPTIONS` = `0x1040`** (`TargetIsTile | TargetTileIsFree`, portée adjacente,
  `forceMeleeTarget = 1` = `RangedBool.False`), forme **FLAGS DIRECTS** à 7 arguments. Migré de
  `TARGETING_OPTIONS_UNPORTED` vers la classe (contrat de disjonction), valeurs bit-identiques.

## 5. Face DÉCISION — `GrotTankPlaybook`

`GrotTankPlaybook$$.ctor` = `ComparablePlaybook<T>..ctor(this, 0x421)` ; `.cctor` = `Fix64(1)` →
`MIN_UTILITY = 1` ; `PRIORITY = 0`. `EvaluateNonComparable` énumère
`GetEligibleTargetsSelectable(caster, MainTile(position))` et garde le max **strict**. L'utilité :

```
GetUtility(caster, summonTile) :
    x = 0
    foreach e in IBattleQuery.<slot 118 GetSurroundingUnits>(summonTile, 3, null):
        if (!IBattleQuery.<slot 146 AreFriends>(e, caster, null))  x++
    return x
```

⇒ **#unités non amies dans le DISQUE de rayon 3** autour de la tuile de spawn. Slots lus dans
`data/symbols/<build>/metadata/interface_slots.tsv` (arité 3 pour les deux ; 117/119 sont d'autres
surcharges de `GetSurroundingUnits`). Le **rayon 3 est un littéral du playbook** : il coïncide avec
`orksGrotTank.weapons[1].Range` mais rien ne l'y lie. `includeCenter` est **inerte** (la tuile de
spawn est libre par le masque).

## 6. Ce qui est CONFRONTÉ, et ce qui ne l'est pas

Board `MC1_67`, seed 777, `orksBigMek` rank 17 → niveau 50, multiplicateur 180 % ⇒
`summonHp = 6980`, `extraHp = 997`, `summonDmg = 2493`, `summonArmor = 1996`.

| étage | natif | port |
|---|---|---|
| spawn, tuile | 1 unité sur la tuile ciblée | idem |
| **PV, `turnsStarted = 1`** | **7977** | **7977** (= 6980 + 1 × 997) |
| **PV, `turnsStarted = 4`** | **10968** | **10968** (= 6980 + 4 × 997) |
| on-appearance, dégât par cible | `{u83: 1522}` | `{u83: 1522}` |
| `decisionView.toActivate` | `[77, 79, 83]` — le tank (105) **absent** | (#291, non porté côté port) |
| DÉCISION, utilité par position | **30/30** identiques, valeurs {1, 2, 3} | idem, argmax 3.0 des deux côtés |

Deux **montages** rendent ces mesures non vides, et sans eux la passe serait verte sans rien
mesurer : `--caster-pos`/`--enemy-pos` (aux spawn points de `MC1_67` le tank apparaît à 7 hex de la
mêlée, hors de sa portée 3 → on-appearance inerte des deux côtés) et `--wait-turns` (à
`turnsStarted = 1`, `summonHp + 1 × extraHp` et `summonHp + turnsStarted × extraHp` coïncident).

**NON confronté** :
- `E3` (Attack / FixedArmor du tank) — `combatSnapshot` **ne publie pas** l'entité NPC fraîchement
  spawnée. Le probe rend `NON MESURE` (tri-état) et compare le port à la **config**, pas au natif.
- Le passif du summon (§7).
- L'écart `AreFriends` tri-état côté décision : le natif compterait un objet **neutre** dans le
  disque, le port compte `ctx.epos` (ennemis seuls). Aucun régime porté ne l'expose — les runners
  n'ont que deux camps.

## 7. Le summon et ses items

`orksGrotTank` (`kind: summons`, `visualId: orksNpc3GrotTank`) : Movement 2, deux armes (`Physical`
1 coup en mêlée ; `Blast` 3 coups, **Range 3**), traits `Summon` / `Mechanical` / `BattleFatigue` /
`Vehicle`, `activeAbilities: []`, **`passiveAbilities: ["Ramshackle"]`**.

**`Ramshackle_DmgReduction` (`EffectType` 1090) est PORTÉ depuis #570-r1 (2026-08-10)** —
`engine/entities/effects/loki/ramshackle.py`, inscrit à `EFFECT_CLASSES` et à
`ABILITY_INIT_OWNER_EFFECTS["Ramshackle"]`. i2 : « Takes -`dmgReduction` damage from attacks with
damage types that have `pierceRatio` % pierce ratio or lower ».

    $$CreateDamageModifier = ForAddition(
        get_OwnerIsTarget & AmountIsEqualOrGreater(ConfigConst(0x49 = pierceRatio),
                                                   AttackPiercingRatio()),
        Multiply(ConfigVar(0x12 = dmgReduction), Direct(-1)@DSLFormulas+0x38) )

Trois lectures qui ne se devinent pas : le **sens** du gate (`AmountIsEqualOrGreaterAbilityTrigger$$
ShouldTrigger` finit par `return <+0x20> <= <+0x18>` ⇒ `pierceRatio >= perçage du profil`, donc
« les profils à perçage FAIBLE ») ; `AttackPiercingRatioFormula$$Calculate` rend **0** sur un
`Nullable<DamageProfileType>` vide, sinon le `PiercingRatio` **nominal** du profil ; et le littéral
du `.ctor` (`ba 45 04 00 00` = `0x445` = `TriggeredAbilityType.Ramshackle` — **`EffectType` 1093
est `HolyDuel_DmgReduction`**, autre chose).

**La POSE au spawn manquait aussi** : `spawn_unit` n'appelait pas la 3ᵉ source de la boucle
ABILITIES d'`InitializeActorAbilitiesOperation$$Execute` (les owner-effects des abilities de
l'unité), donc une invocation était privée des passifs de son **propre** kit. Rayon de souffle
mesuré avant l'ajout : **0** unité non-`lineup` du gameconfig y était touchée.

**CONFRONTÉ** (`probe_570r1_ramshackle.py`, `MC1_67`/777, trois profils autour des 30 %) : le natif
publie 1090 sur le tank ; le tank du **port** le porte aussi ; et le **témoin négatif** (profil à
perçage 60 > 30) rend **6862 == 6862**.

**NON CONFRONTÉ — la MAGNITUDE, et le PLACEMENT avec elle.** Le port lit `dmgReduction[**1**] = 5`
au lieu du palier réel. Tant que ce niveau est faux, aucune comparaison de magnitude n'est
concluante : les écarts mesurés (5 sur `Physical`, 487 sur `Energy`) sont inexploitables, et le
placement pré- vs post-perçage reste **présumé** par la famille Nightshroud/`PsychicFortress`.

### #570-r3 (2026-08-10) — le blocage était en DEUX étages, le premier est levé

⚠ **La cause écrite ici était FAUSSE sur un point** : `combatSnapshot` **publie bien** l'entité NPC
fraîchement spawnée (le probe la lit et en imprime les stats). Ce qui manque n'est pas l'entité,
c'est sa **configuration** — et le blocage se ventile en deux étages **distincts** :

* **ÉTAGE 1 — L'UNITÉ. LEVÉ, mesuré.** Une unité INVOQUÉE n'a aucune `UnitConfiguration` (le natif
  la fabrique par `SpawnUnitOptions$$WithStatsFromConfig`, pas depuis une config), donc
  `combatSnapshot.unitConfig` rend `{"error": "config null"}` et le port gardait
  `passive_ability_level = 0` / `mult = 100`. Le canal qui porte l'information est
  **`unitAbilityStates`**, que `snapshot._load_passive_abilities` sait consommer **depuis
  #462-r4b-…-r3** — mais que le harnais des probes (`probe_503r1_overwhelming_wrath_phase2.load`,
  5 consommateurs) **ne collectait pas**. Après correction : le CTX du tank passe de
  `(passive_ability_level 0, mult 100)` à **`(50, 180)`**.
  S'y ajoute, côté spawn **PORTÉ**, un défaut faux : `build_summon_context` laissait
  `passive_ability_level` à `0` quand l'appelant ne le précisait pas, alors que
  `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig` écrit
  `if (abilitiesLevel == null) abilitiesLevel = abilityState.level` (et de même pour le
  multiplicateur) — **aucune branche native ne laisse ce niveau à zéro**, et le natif n'a qu'UN
  niveau pour toutes les abilities de l'unité posée. Seconde voie qui le confirme :
  `IdunBattle.Operations.AddUnitOperation$$InherentAbilitiesLevelFromParent` prend le MAX des
  `AbilityState` du parent et le pose sur celles de l'unité.
* **ÉTAGE 2 — L'INSTANCE D'EFFET. NON LEVÉ.** L'effet porte toujours `ability_level = None` /
  `mult = 100`, donc `lvl` retombe sur `self.level` (= `1`, le niveau de l'EFFET publié par
  `decisionView.effects`) et la magnitude reste `dmgReduction[1] = 5`. Cause **déjà nommée dans le
  code** (`engine/entities/effects/factory.py`) : `load_state` matérialise les effets **AVANT**
  `_load_passive_abilities`, donc à la naissance de l'effet le CTX de son owner porte encore
  `0`/`100`. Le remède y est écrit — déplacer le seed d'owner-effects après
  `_load_passive_abilities` — mais c'est un changement d'**ORDRE** dans `load_state` dont le rayon
  de souffle n'est pas mesuré.

⇒ **magnitude et placement restent NON CONFRONTÉS**, et le blocage change de nature : il n'est plus
`seeding` (l'unité a son niveau) mais `etage` (l'instance d'effet ne le lit pas). Résidu **#570-r5**
(`--suggere 570` : `r1..r4` sont pris).

## Artefacts

- Port : `scripts/python/engine/runner/abilities/orks.py` (`grot_tank_tree`,
  `grot_tank_health_formula`, `GrotTankAbility`), `engine/runner/abilities/behaviours/summon.py`
  (`StatModifierFormula`, `get_stats_to_override`, `Spawn.stat_modifier_formulas`),
  `engine/runner/operations/spawn.py` (`apply_spawn_stat_overrides`),
  `engine/playbook/noncomparable/grot_tank.py`.
- Sondes : `scripts/python/probe_570_grot_tank.py` (COMBAT, 5 étages),
  `scripts/python/probe_570_grot_tank_nc.py` (DÉCISION, `ncEvaluate --sweep`).
- Gardes : `scripts/python/tests/engine/runner/test_grot_tank_live.py` (5 tests, chacun vu ROUGE
  par mutation adversariale).
- #570-r1 : `scripts/python/engine/entities/effects/loki/ramshackle.py`,
  `engine/entities/effects/factory.py` (`EFFECT_CLASSES` + `ABILITY_INIT_OWNER_EFFECTS`),
  `engine/runner/operations/spawn.py` (`_seed_ability_owner_effects` au spawn),
  sonde `scripts/python/probe_570r1_ramshackle.py`.
