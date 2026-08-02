# #419-r1-tr9-r4-r1-r2 — les quatre consommateurs non portés du gate `IsNormalAttack`

**Verdict par item — 2 portés et confrontés, 1 dead, 1 résidu.**

| effet | trigger natif, RELU au décompilé | verdict |
|---|---|---|
| `ShroudPsalm` (1366) | `get_OwnerIsTarget & IsNormalAttack` — **MALUS défenseur**, `ForAdditionWithMinimum(−hitsReduction, min 1)` | **PORTÉ + CONFRONTÉ** |
| `VoltagheistField_ExtraHit` (1381) | `get_OwnerIsCaster & IsNormalAttack`, `ForAddition(+extraHit)` | **PORTÉ + CONFRONTÉ** |
| `Dakka_ExtraHits` (1105) | `AmountIsEqual(MinDistance(Caster,Target), 2) & AmountIsEqualOrGreater(AttackWeaponRange, 3) & get_OwnerIsActor & IsNormalAttack & IsRangedAttack` | **registered-but-DEAD** — aucun porteur du trait |
| `LegendaryCommander_ExtraHits` (1395) | en NÉGATION, + état persistant + `IsFirstHitGroupInAttack` | **résidu `#419-r1-tr9-r4-r1-r2-r1`** |

Le tableau du cas amont (`case-419-r1-tr9-r4-r1-contexte-du-fold.md` §3) est **confirmé sur les
quatre triggers**, avec deux précisions qu'il n'avait pas : les nœuds de `Dakka` et de `1395` sont
lus au complet ci-dessous, et `1105` n'a **aucun porteur**.

## 1. `ShroudPsalm` (1366) — le malus défenseur, celui qui faisait SUR-COMPTER le port

`IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$CreateEffectHitsBonusForAttack` :

```
EffectBonus.ForAdditionWithMinimum(
    trigger  = get_OwnerIsTarget & IsNormalAttack,
    addition = Negative(Get(GetNumberConstant(config, 0x2c = hitsReduction))),   # = -2
    minimum  = Get(1))
```

Aucun nœud mêlée/ranged, aucun gate de profil ni de distance : la réduction porte sur **toute**
attaque NORMALE reçue. `IdunBattleLogic.Entities.DSLFormulas$$Get(int)` a le **même corps** que
`$$Direct(int)` (même classe de formule, même ctor) — c'est une constante directe, pas un accès
indexé ; la distinction `Get`/`Direct` du décompilé n'a donc aucune conséquence.

**Qui pose l'effet** (#436 — un effet au registre sans poseur reste inerte en silence) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ShroudPsalmAbility$$ExecuteBehaviour`, sur le
sélecteur `First(SortByFormula(Randomize(Friends(Caster, AllUnits − Caster, 3))), ·,
ConfigConst(0x11 = nrOfTargets = 2))` — **jusqu'à 2 alliés, caster EXCLU**, pour
`TurnsFromRounds(1)`. Le même corps pose aussi `0x55a = 1370 ShroudPsalm_Armor`
(`AddStaticStatModifierEffect`, stat 0x10, `ConfigVar(0x1b = extraArmor[L])`) et
`0x555 = 1365 MachineVengeance` sur les mêmes cibles. Seul `0x556` porte le canal COUPS.

### Ce que le port n'avait pas : `is_normal_attack` du côté DÉFENSE

Le canal `create_effect_hits_malus_for_defense` ne recevait **pas** la nature du vecteur — ses
quatre porteurs d'alors (LightCover, Parry, Camouflage, Diminutive) n'ont pas ce nœud. `ShroudPsalm`
est le **premier** effet du côté défense à le porter : le paramètre est ajouté à la base, aux quatre
overrides (qui documentent explicitement l'ABSENCE du nœud chez eux), à l'agrégateur
`hits_malus_from_defender_effects` et au call-site de `AttackHitsWithModifiersFormula`.

### Le `minimum = Get(1)`, et pourquoi le port reste juste sans le modéliser

`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` consomme le minimum **juste après**
l'addition du bonus concerné : `hits = Math.Max(hits, Math.Min(base, minimum))`, dans deux boucles
successives (additions d'abord, réductions ensuite, ces dernières sautées si un effet actif a rendu
`BaseEffect$$BlockHitsReduction == true`). Le port l'approxime par son plancher **global**
`max(min(1, base), ·)`. Identique tant que tous les minimums valent 1 — c'est le cas des **sept**
porteurs du canal (Parry, LightCover, Camouflage, Diminutive, BigTarget, FightingRetreat,
ShroudPsalm). Le port intégral du clamp par-effet reste le chantier séparé déjà nommé dans l'entête
de `services/attack_hits_formula.py`.

## 2. `VoltagheistField_ExtraHit` (1381) — jumeau structurel de `PowerTrip_FullHealth`

`IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$CreateEffectHitsBonusForAttack` :

```
EffectBonus.ForAddition(
    trigger  = get_OwnerIsCaster & IsNormalAttack,
    addition = Get(GetNumberConstant(config, 0x2b = extraHit)))   # = 1
```

Mêmes deux nœuds que `PowerTrip_FullHealthEffect` (ordre inverse), même clé de constante, pas de
`minimum`.

**Qui pose l'effet** : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VoltagheistField_OnRepairAbility`
— `CreateTrigger` = `On(0x30 = 48 UnitRepaired) & get_OwnerIsTarget`, `CreateBehaviour` =
`AddEffect(0x565, <abilityStateRef>, Target, Owner, <durée>)`. L'effet n'existe donc **que** dans la
fenêtre qui suit un **repair** reçu (pas un heal : le porteur doit être `Mechanical`). La seconde
moitié du passif (`−50 %` sur le montant réparé) est l'effet séparé `0x566 = 1382
VoltagheistField_RepairReduction` (`$$CreateEffectRepairBonus`), canal REPAIR — hors périmètre.

## 3. `Dakka_ExtraHits` (1105) — RE complète, verdict **registered-but-DEAD**

`IdunBattle.Entities.Effects.Loki.Dakka_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` construit
son `EffectBonus` **inline** (pas d'appel à `EffectBonus$$ForAddition` : mêmes slots écrits à la
main, `minimum` laissé à zéro — sémantiquement un `ForAddition`) :

```
trigger  = ((get_OwnerIsActor & IsNormalAttack) & IsRangedAttack)
           & AmountIsEqualOrGreater(AttackWeaponRange(), Direct(statics[0]))
           & AmountIsEqual(MinDistance(Caster, Target), Direct(statics[1]))
addition = Direct(GetNumberConstant(config, 0x2b = extraHit))
```

`Dakka_ExtraHitsEffect$$.cctor` écrit `statics[0] = 3` et `statics[1] = 2` — soit exactement l'i2
« For attacks with range 3 or more, has +extraHit hits if the target is at range 2 ».
`IdunBattle.Entities.Formulas.AttackWeaponRangeFormula$$Calculate` rend **1** quand
`WeaponProfile.get_IsMelee()` est vrai, sinon le `Nullable<int>` de portée de l'arme ;
`MinDistance` est la distance hex nue (cf. `entities/formulas.py::MinDistance`).

**Pourquoi DEAD.** Sa seule voie d'attribution est le **trait `Dakka`** :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DakkaAbility` est un
`AOwnerEffectSpecificTriggeredAbility` et **l'unique appelant de son ctor** est le registre
`IdunBattle.Core.Services.AbilitiesDatabase.<InitializeTriggeredAbilities>b__28_107`. Or **aucune
unité** du gameconfig `rnca9r7q6c` ne porte ce trait. Recoupé par trois lectures indépendantes :
balayage des `traits` des trois groupes (`lineup` / `npc` / `summons`) → 0 ;
`unit_map.py find --trait Dakka` → 0 ; balayage **brut** du JSON complet du gameconfig → 30
occurrences de la chaîne « Dakka », **aucune dans un tableau `traits`** (elles sont dans
`DakkaDakkaDakka`, `NeedsMoreDakka`, un `traitPowerModifiers` `"Dakka": 125`, un nom d'upgrade
« Snazzy Dakka » et des `BoardId`).

⇒ **Aucun porteur spawnable, donc aucun port** (règle « pas de port spéculatif »). Le jour où une
unité reçoit ce trait, la RE ci-dessus suffit à l'écrire ; il faudra alors ajouter au board de la
formule la portée de l'arme de l'attaque (`AttackWeaponRange`), qui n'y est pas.

## 4. `LegendaryCommander_ExtraHits` (1395) — résidu `#419-r1-tr9-r4-r1-r2-r1`, RE consignée

Porteur : `custoTrajann` (**lineup**, donc confrontable — ce n'est pas un problème d'accès).
i2 : « … If the affected enemies are also adjacent to Trajann, friendly Characters score 2
additional hits against them with **their first attack that is not a normal attack**. »

`$$IsValidAttack(<sélecteur>)` :

```
  get_OwnerIsTarget
& AreFriends(<sel +0x48 = Caster>, EffectSource(<sélecteur passé>))
& !IsNormalAttack(<sel +0x88>)
& !(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility(<sel +0x88>))
```

`$$CreateEffectHitsBonusForAttack` :

```
EffectBonus.ForAddition(
    trigger  = (IsValidAttack(<sel +0x38>) & !IsInPersistentDataList(<AbilityOrEffect de l'effet>,
                    EffectSource(<sel +0x38>), EntityId(<sel +0x30 = Owner>), EntityId(<sel +0x48 = Caster>)))
               & IsFirstHitGroupInAttack(),
    addition = ConfigVar(0x2f = nrOfHits, <abilityState>, config))
```

Trois choses manquent au port pour l'écrire, et c'est ce qui en fait un résidu et non un oubli :

1. **La négation.** Le bonus ne s'applique **jamais** à une attaque normale. C'est le seul des six
   consommateurs dans ce sens — le porter à l'envers serait pire que l'absence.
2. **L'état persistant.** `IsInPersistentDataList` + le couple
   `$$GetMarkCasterBehaviour` / `$$GetClearAllMarkedAttackersBehaviour` / `$$IsCasterMarked`
   implémentent le « **first** attack » : une liste d'attaquants déjà servis, portée par
   l'entité-effet, remise à zéro par un trigger. Le port n'a pas ce substrat sur ce canal.
3. **`IsFirstHitGroupInAttack`.** Tranché par le cas amont (`case-419-…-contexte-du-fold` §5) : ce
   nœud a `1395` pour **unique** lecteur, et la clé `is_first_hit_group` n'existe pas dans le board
   de la formule de coups. C'est précisément la dépendance que le cas amont annonçait.

**Montage nommé** pour qui reprendra : `custoTrajann` est au pool ; il faut une cible ennemie
adjacente à Trajann **et** adjacente à un allié de Trajann ayant utilisé une active dans le tour
(condition de l'effet `LegendaryCommander_ExtraDamage` 1394 qui pose le marquage), puis une attaque
**d'ability** (famille ATTACK, pour traverser `AttackDamageOperation$$GetAttackHits`) portée par un
`Character` allié — mesurée deux fois pour voir le « first ».

## 5. La confrontation — deux montages, deux probes, six tests

### `ShroudPsalm` — `probe_419r1tr9_r4_r1_r2_shroud_psalm.py`

Le porteur natif de l'ability (`admecBossBelisarius`) est **npc** → greffe de l'**active**
(`catalog_inject.write_grafted_seed_bc(..., kind="active")`, `case-92` §5bis) sur `templAggressor`.
Board `MC1_67`, seed `41366`, un seul runner, mesure **avant/après le cast**.

> **Le bras qui compte** : on mesure les coups **REÇUS** par le porteur de l'effet. L'attaquant est
> donc une TIERCE unité, et le porteur est sa CIBLE.
>
> ⚠ Le caster greffé et son allié sont dans l'équipe **ADVERSE**, l'attaquant dans la mienne :
> `abilityTargets` — d'où sort l'`ActiveAbilityType` concret de l'attaque normale — ne renseigne que
> les unités du **joueur courant** (mesuré : un `unitId` adverse y rend zéro ability). Le cast se
> fait donc pendant le tour adverse (`endturn`, cast, `_give_turn_back`).

Positions : `tauCrisis` (attaquant, 12 coups d'arme) en `(0,2)` ; `templAggressor` (caster) en
`(0,0)` ; `astraBullgryn` (allié affecté) en `(0,4)` — les deux cibles à distance 2 de l'attaquant,
même élévation, non adjacentes entre elles.

```
  phase     cible    natif                    port
  before    ally     (1569, 2355, h9)         (1569, 2355, h9)
  before    caster   ( 414,  621, h9)         ( 414,  621, h9)
  after     ally     (1269, 1905, h7)         (1269, 1905, h7)
  after     caster   ( 414,  621, h9)         ( 414,  621, h9)

  [1] montage (NATIF seul) : d(ally) = -2 (attendu -2), d(caster temoin) = 0 (attendu 0)
  [2] accord port/natif 4/4
  [3] contre-epreuve : deplacement ally = +2, caster = 0
```

Le cran [1] est **entièrement natif** : le port n'entre pas dans la définition du verdict. Le
**témoin interne** est le caster lui-même, que le sélecteur natif EXCLUT — même runner, mêmes
positions, même tour.
Effets lus après le cast : allié = `[…, 'ShroudPsalm', 'ShroudPsalm_Armor', 'MachineVengeance']`,
caster = `['CrushingStrike']`.

### `VoltagheistField_ExtraHit` — `probe_419r1tr9_r4_r1_r2_voltagheist.py`

Porteurs natifs : deux npc + un summon d'**environnement** (`admecSmnElectropriest`, dont l'unique
invocateur est `EnvFactionSummons:AdeptusMechanicus`, portée par **aucune unité** — ce n'est donc
pas un summon atteignable par son summoner) → **greffe du passif**
(`TriggeredAbilityType.VoltagheistField = 1302`) sur `necroWarden`, choisi parce que son trait
`LivingMetal` (« Regenerates X % … at the start of the players' turn. This unit is also
Mechanical ») fournit le **repair** tout seul, sans seconde unité ni cast à piloter. Il suffit de le
blesser (`--unit-stat RemainingHealth=300000` pour `Health=900000`).

⚠ **Le protocole « avant/après un tour » NE MARCHE PAS ici** : le repair a déjà eu lieu quand la
première mesure est prise (le placement traverse des tours), donc l'effet est présent aux **deux**
mesures et le delta est nul. Mesuré, puis remplacé par **deux bras** (`graft` / `none`) partageant
le même catalogue, la même seed, la même géométrie (le layout du premier bras est rejoué dans le
second) et ne différant que par `BC.Units[necroWarden].PassiveAbilities`.

```
[graft] carrier  nat=(2601, 3900, h3)  port=(2601, 3900, h3)   effets: [..., 'VoltagheistField_ExtraHit']
[graft] witness  nat=(1752, 2628, h6)  port=(1752, 2628, h6)
[none ] carrier  nat=(1734, 2600, h2)  port=(1734, 2600, h2)   effets: ['RelentlessMarch_DangerZone']
[none ] witness  nat=(1752, 2628, h6)  port=(1752, 2628, h6)

  [1] montage (NATIF seul) : d(porteur) = +1 (attendu +1), d(temoin) = 0 (attendu 0)
  [2] accord port/natif 4/4
  [3] contre-epreuve : graft/porteur = -1, graft/temoin = 0, none/porteur = 0
```

### Le mutant qui rend VERT sans avoir mordu

Première écriture de la contre-épreuve : retirer la clé du registre `EFFECT_CLASSES`. **Déplacement
mesuré : 0** — la scène est déjà hydratée quand le mutant tourne, les instances construites restent
des `ShroudPsalmEffect`, et le test aurait été vert **sans jamais tester quoi que ce soit**.
Corrigé en patchant la **méthode** de la classe, qui agit sur les instances existantes. C'est
exactement `feedback_verify_the_mutation_applied` : sur une contre-épreuve, **vert est le résultat
suspect**.

### Garde : `tests/engine/test_419r1tr9_r4_r1_r2_normal_attack_gate_live.py`

**6 tests, 0 skip, 234 s** — trois crans par effet (montage natif + témoin / accord port-natif /
contre-épreuve discriminante).

## 6. Non-régression rejouée

| fichier | résultat |
|---|---|
| `tests/engine/entities/test_attack_nature_gates_offline.py` | 17 passed, 1,6 s |
| `test_lightcover_gate_live.py` + `test_ability_hits_attack_nature_live.py` | 3 passed, 125 s |
| `test_ability_hits_channel_live.py` + `test_purge_response_blockhits_live.py` | 15 passed, 362 s |
| `test_inescapable_accuracy_override_hits_live.py` + `test_419r1tr9_r4_boltstorm_pred_live.py` | 19 passed, 271 s |
| `test_419r1tr9_r4_r1_fold_context_live.py` + `test_summon_trait_effects_live.py` | 13 passed, 117 s |
| `test_419r1tr9_r4_r1_r2_normal_attack_gate_live.py` (neuf) | 6 passed, 234 s |

**73 tests, 0 skip.** Banque de cliquets : `pwsh -File scripts/ratchets.ps1` → **30 verts, mur
154,2 s** (relevé de ce cas ; la composition fait foi dans `scripts/ratchets.ps1`, pas ici).

## 7. Résidus NOMMÉS

* **`#419-r1-tr9-r4-r1-r2-r1`** — `LegendaryCommander_ExtraHits` (1395) non porté. RE complète en
  §4 ; il lui manque trois pièces (négation, liste persistante d'attaquants déjà servis, clé
  `is_first_hit_group` au board de la formule) et son porteur `custoTrajann` est au pool, donc
  confrontable. Candidat naturel pour une tranche dédiée.
* **`#419-r1-tr9-r4-r1-r2-r2`** — `Dakka_ExtraHits` (1105) : DEAD **aujourd'hui**, pas pour
  toujours. Le verdict tient au gameconfig courant ; il est à re-dériver au changement de build (le
  balayage tient en une ligne : porteurs du trait `Dakka` dans `units.{lineup,npc,summons}`).
* **`#419-r1-tr9-r4-r1-r3` (hérité, partiellement fermé)** — les citations
  `IdunBattleLogic.Entities.DSLFactory$$Is*`, qui n'existent dans aucun des deux dumps. Corrigées
  dans les fichiers du périmètre (`effects/loki/hits.py` : 4 ; `effects/base.py` : 2 — vérifié
  contre `data/symbols/rnca9r7q6c/ghidra/functions.tsv` : `IsCharging`, `IsMeleeAttack`,
  `IsPersistentData` existent en `DSLTriggers$$` et **pas** en `DSLFactory$$`). Il en reste ~74
  dans ~38 autres fichiers, hors périmètre de ce cas. Aucun cliquet ne voit cette faute.

## 8. Ce que ce cas n'établit PAS

* **La face COMBAT.** Les deux confrontations passent par `aiPlaybookPredict` (façade PRÉDICTION,
  `DamagePrediction$$GetAttackHits`). La formule est **partagée** avec le combat
  (`AttackDamageOperation$$GetAttackHits` → `AttackHitsWithModifiersFormula$$Calculate`) et le port
  l'appelle au même endroit depuis les deux faces, mais aucun coup n'a été **exécuté** ici.
* **Le régime `is_normal_attack = False`.** Le gate est vérifié par construction (le port rend
  `None`) et par le test offline `test_attack_nature_gates_offline.py`, pas par une mesure live
  d'attaque d'ABILITY contre un porteur de `ShroudPsalm`.
* **Les magnitudes autres que celles du gameconfig courant** : `hitsReduction = 2` et
  `extraHit = 1` sont lus, jamais codés en dur — mais une seule valeur de chacun a été confrontée.
* **`ShroudPsalm_Armor` (1370) et `MachineVengeance` (1365)**, posés par le même cast : les bornes
  de dégât du port les suivent exactement dans la mesure ci-dessus, mais ce cas ne les asserte pas
  (seul `appliedHits` est confronté).
