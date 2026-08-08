# `#419-r1-tr14-r5-r2-r1-r1-r1-r3` — les derniers `ShouldExecute` à corps propre, le foyer d'adjacence partagé, et le rang du lifesteal

**Critère binaire** : reste-t-il, sur la route Comparable, un `ShouldExecute` natif à corps propre
que le port ignore et qui soit portable **sans** approximation de domaine ? **Non pour 4 des 10
restants**, portés ici ; **3 sont documentés non portables en l'état** et **3 sont attestés « leur
gate vit ailleurs »**. S'y ajoutent deux corrections structurelles : le comptage d'adjacence a
désormais un foyer partagé qui lit le bon `UnitSelectionType`, et le terme lifesteal de
`1104 SpiritLeech` est revenu à son rang natif.

---

## 1. L'inventaire, RE-DÉRIVÉ — et il corrige le brief

Le brief de cette tranche annonçait « 43 classes non portées, la tranche précédente n'en a porté
qu'un ». **C'est périmé de deux tranches.** Le recensement a été refait depuis les symboles du build
(`search_symbols_by_name(query = "Playbook.*\$\$ShouldExecute")` → **31** symboles, dont deux
définitions génériques), puis chaque corps décompilé et classé par FORME :

| corps natif | classes | état à l'ouverture |
|---|---|---|
| `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute` | 14 | porté (`normal_attack_kill_gate`, `-r1`) |
| `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute` | 2 | LU, non porté (cible = TUILE, `-r1-r1`) |
| `IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute` | 1 | porté (`-r1`) |
| famille « seuil statique de la classe » | 12 | portée (`static_threshold_gate`, `-r2`) |
| `IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute` | 1 | porté (#573) |
| `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$ShouldExecute` | 1 | porté (`loki_custom`) |
| **les 10 restants** | 10 | **cette tranche** |

29 corps concrets + 2 génériques = les 31 symboles. Le gisement réel à l'ouverture était donc de
**10**, pas de 43.

### Les dix, corps LU verbatim et `ability_id` LU dans le `.ctor`

| classe | id (`.ctor`) | corps | verdict |
|---|---|---|---|
| `Loki.StranglethornCannonPlaybook` | `0x420` = 1056 | `utility > Fix64(0)` littéral | **porté** |
| `Loki.ReapingScythePlaybook` | `0x447` = 1095 | `utility > 0` **&&** `GetStat(caster, TurnsStarted) > 2` | **porté** |
| `Loki.StormOfFlensingBladesPlaybook` | `0x3f2` = 1010 | `casterTile == GetMainTile(caster)` | **porté** |
| `Loki.HadesAutocannonsPlaybook` | `0x47b` = 1147 | un allié porte `UnitTrait.Summon` | **porté** |
| `Common.HealPlaybook` | `0x12` = 18 | `utility > 0` **&&** `(!IsBoss(caster) \|\| caster != target)` | **porté** (2ᵉ moitié) |
| `Common.RepairPlaybook` | `0x1c` = 28 | `utility > Fix64(0)` littéral | attesté ailleurs |
| `Loki.Repair_GalvanicFieldPlaybook` | `0x45f` = 1119 | idem | attesté ailleurs |
| `Loki.TwistedScience_HealPlaybook` | `0x48f` = **1167** | idem, **sans** la clause boss | **porté** (classe dédiée) |
| `Loki.HealingBalms_HealPlaybook` | `0x4bc` = 1212 | idem | attesté ailleurs |
| `Loki.ArmoriumCherubPlaybook` | `0x3f6` = 1014 | requête de zone → `!CanKillTarget` | résidu |
| `BloodChalicePlaybook` | `0x497` = 1175 | `Σ (GetNumberConstant(0x4f) − Health(allié)) > 0` | résidu |
| `Loki.TacticalPrecisionPlaybook` | `0x482` = 1154 | requête `0xcd` → `true`, sinon `Count(cibles) > 1` | résidu |

⚠ **Le nom du playbook peut MENTIR sur l'ability, et seul l'id du `.ctor` les apparie** :
`TwistedScience_HealPlaybook` porte `ActiveAbilityType.Heal_TwistedScience` — les deux moitiés du
nom sont inversées dans le build. Un port qui aurait cherché `TwistedScience_Heal` dans l'enum aurait
levé un `AttributeError` (c'est ce qui est arrivé, et c'est ce qui a fait relire l'enum).

---

## 2. Trois lectures qui ne se devinent pas

1. **`ReapingScythe` lit `StatType.TurnsStarted` (12), pas un compteur de charges.** Le littéral
   `0xc` est qualifié dans `data/symbols/<build>/frida/enums.tsv` (`12=TurnsStarted`) et c'est le
   même accesseur que `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`, déjà porté
   (`Scene.turns_started`, **tri-état**). La comparaison est `> 2` STRICT : l'ability n'est proposée
   qu'à partir du QUATRIÈME tour démarré.
2. **`StormOfFlensingBlades` compare la TUILE DE CAST à la MainTile courante** — un gate « je ne me
   déplace pas pour lancer ». Il ne lit ni utilité ni cible. Le sweep de tuiles du générateur d'action
   propose des positions de déplacement ; le natif les refuse **toutes** sauf l'origine. C'est le plus
   permissif des quatre trous fermés ici : le port acceptait le cast depuis n'importe quelle tuile
   atteignable.
3. **`Common.HealPlaybook` interdit à un BOSS de se soigner lui-même**, et `1167` **n'a pas** cette
   clause. Les laisser partager un playbook aurait fait hériter à `1167` un gate que son corps natif
   n'a pas — d'où la classe `TwistedScience_HealPlaybook`, qui existe pour cette seule différence.

### La borne du `IsBoss`, dite exactement

`IdunBattle.Entities.UnitExtensions$$IsBoss` ne lit **pas** un trait : il résout un composant et rend
l'octet `<composant>+0x88`. **Aucun canal du port ne publie ce champ** (ni `combatSnapshot`, ni le
gameconfig, qui n'a aucune clé `isBoss` — vérifié). Le port emploie donc le PROXY déjà acté ailleurs,
le trait `Boss` (`UnitTrait` `0x7e7` = 2023), celui que
`services/custom_normal_attack.NORMAL_BOSS_ATTACK_TRAIT` consomme pour dispatcher l'attaque normale
boss et celui que le montage de #573 greffe pour faire basculer le natif sur `1030`. **Mesuré : 0
unité sur 175 du seed BC le porte** — la clause est donc INERTE hors greffe, et c'est par greffe
qu'elle se confronterait.

---

## 3. Le foyer d'adjacence PARTAGÉ (`#419-r1-tr10-r2` et `-r4`)

Trois comptages portés écrivaient chacun leur boucle « pour chaque unité vivante, si
`is_adjacent(pos(sujet), pos(u))` » : `righteous_repugnance.count_additional_targets`,
`boltstorm.count_all_targets`, `fire_of_absolution.count_adjacent_by_camp`. Les trois portaient donc
la même approximation sur **deux** axes. `engine/playbook/adjacency.py` est leur foyer commun.

### 3.1 L'axe `UnitSelectionType` — le littéral `3` n'est pas « vivante »

`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`, décompilé relu en entier :

```csharp
if (unit == null)                               return false;
if (!<IsUnit>(unit))                            return false;
if (selectionType == OnlyAlive)                 return IsAlive(unit, state);
if (selectionType == OnlyTargetable)            return !HasFlag(unit, UnitFlag.Untargetable);
if (selectionType == OnlyAliveAndTargetable)    return IsAlive(unit, state)
                                                       && !HasFlag(unit, Untargetable);
return true;                                    // Any -- ET toute valeur hors enum
```

`3` = `IdunBattle.Entities.Enum.UnitSelectionType.OnlyAliveAndTargetable` = **deux** clauses. Le port
n'en portait qu'une (`alive`), donc il comptait une unité en cours de deep-strike que le natif écarte
— dégradation **PERMISSIVE**. La seconde est portée par le domaine `UNTARGETABLE_EFFECT_TYPES` (le
flag `0x11` est posé par `UntargetableEffect$$ApplyInternal`, donc il se lit par ses effets — même
lecture que `engine.ai.state_bridge._is_untargetable`, dont c'est le pendant DÉCISION).

⚠ **La branche par défaut du natif est `true`, pas `false`.** Les trois tests sont des comparaisons
successives et le chemin qui n'en satisfait aucune saute au `return true`. Un mirror qui aurait
« durci » ce défaut aurait écarté des unités que le natif compte.

⚠ **`fire_of_absolution` n'est PAS concerné par cet axe, et c'est LU** : sa primitive est
`IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles`, dont la signature est
`(tiles, friendsOf, enemiesOf, ignoreSteppables, get, result)` — **aucun `UnitSelectionType`**. Y
appliquer le filtre aurait été ajouter une règle que le natif n'a pas.

### 3.2 L'axe MULTI-TUILES — le mirror est posé, l'ENTRÉE manque

`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`, lu verbatim :

```csharp
result = new OrderedSet<ITile>();
inner  = this.<+0x20 = origin>.Select(entities);          // TOUTES les tuiles du sujet
foreach (t in inner)
    foreach (n in battleQuery.<+0x50 IterateAdjacentTiles>(t, false, true, true))
        if (!inner.Contains(n)) result.Add(n);            // ring-1 de CHAQUE pied, MOINS l'empreinte
```

et `inner` remonte, pour une entité, à `IdunBattle.Entities.EntityExtensions$$IterateTiles(entity,
state)`. Le voisinage natif d'une unité à 3 ou 7 pieds est donc l'union des ring-1 de **chaque** pied.
`adjacency.unit_in_adjacent_tiles` le porte **des deux côtés** (le sujet ET l'autre unité : `Units(tiles)`
résout l'OCCUPANT de chaque tuile, donc un seul pied suffit).

**Le port reste néanmoins sur la MainTile, et c'est un trou de SEEDING localisé.** Mesuré :

* côté COMBAT le substrat EXISTE (`runner.components.get_unit_feet`, mirror de
  `UnitExtensions$$GetUnitFeet`, qui lit `UnitComponent._feet`) ;
* côté DÉCISION **aucun RPC ne publie la liste des tuiles** — balayage de `frida/hooks/**` :
  **0** occurrence de `GetUnitFeet`, `GetFeetCount` ou `IterateTiles` dans un émetteur, et
  `state.ts` ne projette explicitement que **la première** tuile d'une `UnitPosition`.
  `engine/runner/ability_range.py` portait déjà le même constat pour `GetFeetCount`.

`adjacency.iterate_tiles` lit donc la clé `feet` **si l'appelant la porte** et retombe sur
`[MainTile]` sinon : le comportement d'avant, **exactement**, quand le canal est muet. Le mirror est
en place et value-preserving sur toute unité à un pied (le cas nominal) ; il s'armera seul le jour où
le capteur existera.

**Point d'ancrage à hooker** (fenêtre de reinject nécessaire, donc hors de cette tranche) :
`IdunBattle.Entities.UnitExtensions$$GetUnitFeet` — ou plus simplement publier
`UnitPosition.Tiles` en entier, par unité, dans `combatSnapshot`.

---

## 4. Le RANG du lifesteal (`#419-r1-tr14-r5-r2-r1-r1-r3`)

`ComparableAbilityGenerator._action_utility` ajoutait `ls` au **RETOUR** de
`calculate_action_utility`, donc **après** le gate. Le natif ne somme rien après : le terme entre par
une **troisième branche de prédiction**, et il est foldé avant.

```
IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeHealPredictions(caster, casterTile, target, abilityState)
  -> amount  = SpiritLeechAbility$$GetHealAmountForPrediction(target, abilityState)
     targets = SpiritLeechAbility$$GetHealTargets()
     return ComparablePlaybook<T>$$GenerateHealPredictions(caster, casterTile, caster, targets, amount, 0, <vide>)

ComparablePlaybook<T>$$CalculateUtilityFromPredictions
  = Σ CalculateUtilityFromDamageEvent                     (1re boucle)
  + Σ CalculateUtilityFromHealEvent   (slot +0x368)       (2e boucle)   <- ICI

ComparablePlaybook<T>$$CalculateActionUtility
  u = CalculateCustomUtility + CalculateUtilityFromPredictions
  if (!ShouldExecute(caster, casterPosition.MainTile, target, u)) return Nullable_vide
```

Le port pose donc `ComparablePlaybook.make_heal_predictions` (base VIDE, comme
`MakeEffectPredictions`) et le folde dans `calculate_utility_from_predictions` ;
`playbook/spirit_leech.py` l'override pour `1104` **seul** — le symbole `$$MakeHealPredictions` n'a
qu'**UN** propriétaire de vtable, donc les treize autres identités du même `ShouldExecute` gardent
bien la base vide.

**Ce que le déplacement change, et ce qu'il ne change pas.** L'utilité d'action FINALE est identique
(l'addition commute) ; ce qui change, c'est **l'étage `u`** — celui que les probes confrontent au
canal natif `pairUtility`, qui **est** `CalculateUtilityFromPredictions` — et **l'argument du gate**.

⚠ **Ce résidu ne devient pas mordant pour autant, et la fiche de `-r1` avait raison contre celle de
#573** : `SpiritLeechPlaybook$$ShouldExecute` = `!WillNormalAttackKill(...)`, qui **ne lit pas**
`attackHealUtility`. Le rang était faux ; il n'était pas observable par ce gate-là.

Le calcul lui-même est **inchangé** (corps de `_spiritleech_lifesteal_util`, #84 corrigé par #339 —
bornes CAPÉES `healthDmg*`, un seul arrondi demi-vers-le-pair, aucun bouclier). Cette tranche déplace
un terme, elle ne le recalcule pas.

---

## 5. La face COMBAT de `RighteousRepugnance` (`#419-r1-tr10-r3`) — LUE, NON PORTÉE

`IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$ExecuteRighteousRepugnance`,
décompilé lu en entier, dans l'ordre du flux :

```csharp
sel = RighteousRepugnanceAbility.GetAdditionalTargets(this.<+0x30 = DSL>);
ALoki_NormalAttackAbility.ExecuteInformWeapon(this, attackWeapon, entities, null);
ALoki_NormalAttackAbility.ExecuteNormalAttack(this, abilityState, entities, attackWeapon);   // cible PRINCIPALE
b = DSLBehaviors.Foreach(dsl.<+0x78>, sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState));
AActiveAbility.ExecuteAtomic(this, b, entities, 0x2a);
return ALoki_NormalAttackAbility.ExecuteTriggerAbilities(this, entities, attackWeapon);
```

et la feuille :

```csharp
// RighteousRepugnance_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior(target, abilityState)
caster    = dsl.<+0x90>.<+0x48>;                                  // entities.Caster
behaviour = GetAdditionalDamageBehaviour(this, abilityState, target);
return DSLBehaviors.Attack(dsl.<+0x78>, caster, target, behaviour, AbilityOrEffect.op_Implicit(...));
```

**Elle est structurellement identique à celle de `Boltstorm`** (`Boltstorm_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior`
a le MÊME corps au symbole de `GetAdditionalDamageBehaviour` près) — donc les deux faces COMBAT se
portent ensemble ou pas du tout. **Non portée ici** : elle exige un mirror de `DSLBehaviors.Foreach`
+ `ExecuteAtomic` dans `engine/runner`, foyer disjoint de tout ce que cette tranche touche, et le
groupage était justifié par « même foyer `righteous_repugnance.py` » — ce qui est vrai de la face
DÉCISION, pas de la face COMBAT. Le résidu `#419-r1-tr10-r3` reste OUVERT, avec son RE désormais
complet (ci-dessus) : il ne reste que le port.

---

## 6. Ce qui est livré

* `engine/playbook/should_execute_gates.py` — les 4 gates portés + l'attestation des 5 ids dont le
  gate vit ailleurs (`LITERAL_ZERO_ELSEWHERE`).
* `engine/playbook/adjacency.py` — le foyer partagé (multi-tuiles + `UnitSelectionType`), consommé
  par `righteous_repugnance` et `boltstorm`.
* `engine/entities/unit_selection_type.py` — `matches_unit_selection_type`, mirror du foyer natif
  (tri-état sur les deux prédicats).
* `engine/playbook/spirit_leech.py` — `1104`, lifesteal à son rang ; `engine/playbook/base.py` — le
  crochet `make_heal_predictions` + son fold.
* `engine/playbook/common.py` — la clause BOSS du soin générique, et `TwistedScience_HealPlaybook`.
* `engine/ai/action_generators.py` — le terme lifesteal RETIRÉ d'après le gate ; le gate de soin
  consulté par playbook.
* `scripts/python/probe_419r1tr10r2_multi_tuiles_canal.py` — le probe qui MESURE le canal `feet`
  côté décision (il refuse de mesurer si le montage n'est pas installé).
* `scripts/python/tests/engine/test_419r1tr14r5r2r1r1r1r3_should_execute_gates_offline.py` —
  17 crans.

---

## 7. Ce qui n'est PAS couvert

* **Les 4 gates neufs ne sont PAS confrontés LIVE.** Leurs porteurs, mesurés par
  `unit_map.py find --ability` : `1010` → 3 npc, `1095` → 1 npc (`deathBossMortarion`), `1056` →
  1 npc, `1147` → `blackForgefiend`, **MoW du pool**. Aucun n'est donc « non confrontable » — les
  trois premiers sont GREFFABLES (leurs `ShouldExecute` ne lisent ni stats ni traits de la cible), et
  `1147` demande le déploiement de sa MoW. Le montage n'a pas été joué : **NON CONFRONTÉ**, pas
  « non confrontable ».
* **La clause BOSS est inerte sur le seed** (0 unité sur 175 porte le trait) : elle se confronte par
  greffe, non jouée.
* **Le volet `Untargetable` n'a pas de bras dédié.** Il est porté et lu au décompilé, mais aucun
  montage ne le rend discriminant : il faudrait une unité en deep-strike (`1035
  TeleportStrike_TeleportingIn` / `1140 StormboyzStrike_TeleportingIn`) adjacente au caster ET à sa
  cible au même pas.
* **Le canal multi-tuiles est ABSENT côté décision** (§3.2) : le mirror est donc inerte, et le probe
  qui le mesure n'a pas pu aller jusqu'à l'étape 2 — `adeptExorcist` est **hors plateau au pas 0**
  (une MoW se déploie, elle n'apparaît pas dans `decisionView.units` avant), donc le montage exige
  en plus de jouer le déploiement.
* **Trois corps restent non portés** : `1014 ArmoriumCherub` (requête de zone + `CanKillTarget`),
  `1175 BloodChalice` (somme de déficits de PV sur les unités d'une requête, en sautant les
  mécaniques), `1154 TacticalPrecision` (requête `0xcd` puis `Count(GetNonChargingAttackTargets) > 1`).
  Les trois exigent un mirror de requête de zone que le port n'a pas sur cette route.
* **`1017`/`1026` restent hors registre** (`-r1-r1`, cible native = TUILE) — inchangé par cette tranche.

---

## 8. Résidus NOMMÉS

* **`#419-r1-tr10-r2` reste OUVERT, et son blocage est requalifié** : ce n'est plus « le port ne
  connaît que la MainTile » (le mirror est posé) mais « aucun RPC ne publie les pieds côté
  décision ». `BLOCAGE: capteur`, point d'ancrage `UnitExtensions$$GetUnitFeet`.
* **`#419-r1-tr10-r3` reste OUVERT**, RE complet livré en §5 : il ne reste que le port
  (`DSLBehaviors.Foreach` + `ExecuteAtomic` dans `engine/runner`), à faire **avec** la face COMBAT de
  `Boltstorm`, dont le corps est identique.
* **`#419-r1-tr10-r4` est FERMÉ** : le type est énuméré, le littéral qualifié, la seconde clause
  (`!Untargetable`) portée. Ce qui reste est son bras de confrontation, nommé en §7.
* **`#419-r1-tr14-r5-r2-r1-r1-r3` est FERMÉ** : le terme est à son rang. Son observabilité, elle,
  reste nulle par ce gate (§4).
* **Les trois corps non portés** (`1014`, `1175`, `1154`) et **la non-confrontation live des quatre
  gates** ouvrent le résidu `#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1`.
