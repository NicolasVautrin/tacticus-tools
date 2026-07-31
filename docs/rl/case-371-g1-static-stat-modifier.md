# case-371 — G1 : les 11 instances génériques `StaticStatModifierEffect`

**Question, binaire.** Une stat-mod posée par un de ces 11 effets DISPARAÎT-elle quand l'effet
expire — côté port comme côté natif ?

Ce n'est pas une question de valeur. Le calcul est bon des deux côtés : `seed_unit_stats` reproduit
toujours le `Current` capté (le résidu opaque compense). **La question est la DURÉE**, et elle ne se
voit qu'APRÈS l'échéance.

## 1. Le mécanisme, en une ligne

`decisionView.effects` n'expose ni le stat ni le montant d'un effet capté. Un stat-mod déjà actif au
chargement d'un `State` arrive donc sans stat-modification déclarée → sa contribution tombe dans
`CAPTURED_SOURCE`, attribuée à AUCUNE source, donc **non retirable** (#118). Déclarer la classe pose
la `ValueModification` **par-source**, et `revert_stat_mods_of_removed_effects` la retire au retrait —
mirror de `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` (`ChangeStat` part 6,
même entité-effet qu'à l'apply).

**Mesuré (`probe_371_static_statmod_g1.py` étage 3, 1171 seedé rem=1, base ATTACK 1200)** :

| monde | AVANT tick | résidu opaque | effet après | APRÈS tick |
|---|---|---|---|---|
| DÉCLARÉ | 1643 | 0 | retiré | **1200** |
| NON DÉCLARÉ | 1643 | 443 | retiré | **1643** |

Avant l'échéance les deux mondes sont **indiscernables** — un montage qui mesure là ne conclut rien.

## 2. La table RE — lue au décompilé (build `rnca9r7q6c`)

Feuille commune : `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
(`(targets, effectType, statType, amount, turns, isHidden)`) et sa variante `...ToOwner`
(`(effectType, statType, amount, turns, isHidden)`).

| id | poseur natif | stat | montant | turns | verdict |
|---|---|---|---|---|---|
| 1171 `SereneUnifierStormOfFire` | `SereneUnifierAbility$$CreateBehaviour` (branche `k = 0`) | 0 ATTACK | `ConfigVar(8 = extraDmg)` | `TurnsFromRounds(1)` | **PORTÉ** |
| 1251 `UnbreakableDuty_Health` | `UnbreakableDutyAbility$$ExecuteBehaviour` | 5 HEALTH | `ConfigVar(0x1e = extraHp)` | **NULL** | **PORTÉ** |
| 1256 `UnbreakableDuty_Damage` | idem | 0 ATTACK | `ConfigVar(8 = extraDmg)` | **NULL** | **PORTÉ** |
| 1004 `MightOfHeroes_ExtraHits` | `MightOfHeroesAbility$$ExecuteBehaviour` | 17 EXTRA_HITS | `GetNumberConstant(0x2b = extraHit)` | `Nullable(2)` | **DEAD** |
| 1005 `MightOfHeroes_ExtraDamage` | idem | 0 ATTACK | `GetVariableForLevel(8)` | `Nullable(2)` | **DEAD** |
| 1006 `MightOfHeroes_ExtraArmor` | idem | 16 FIXED_ARMOR | `GetVariableForLevel(0x1b = extraArmor)` | `Nullable(2)` | **DEAD** |
| 1103 `KanOpener_ReduceArmor` | `KanOpenerEffect$$CreateTargetTriggerBehaviour` | 16 FIXED_ARMOR | **−**`ConfigVar(0x30 = armorReduction)` | NULL | **0 PORTEUR** |
| 1351 `EnvStatBoost_Damage` | `BaseStatBoostAbility$$GetInitBuffBehaviour` (+`GetUpdateBuffBehaviour`) | 0 ATTACK | `PercentageOf(StatAmount(ATTACK, part 3), GetNumberConstant(0x3b))` | NULL | **ENVIRONNEMENT** |
| 1352 `EnvStatBoost_Health` | idem (+ un `ChangeStat` sur la santé COURANTE) | 5 HEALTH | `PercentageOf(StatAmount(HEALTH, part 3), GetNumberConstant(0x4f))` | NULL | **ENVIRONNEMENT** |
| 1507 `EnvStatBoost_Armor` | idem | 16 FIXED_ARMOR | `PercentageOf(StatAmount(FIXED_ARMOR, part 3), GetNumberConstant(0x87))` | NULL | **ENVIRONNEMENT** |
| 31 `StatModifier` | **aucun** | — | — | — | **REGISTERED-BUT-DEAD** (§5) |

**UN SEUL des onze porte un vrai timer** (`1171`) — c'est lui qui porte le bug de durée. Les deux
autres inscrits sont PERMANENTS : ce que leur inscription ferme est l'**ATTRIBUTION**, pas une durée.

### Le cycle de `SereneUnifier`, observé live

`Modulo(PlayerTurnsStarted, Direct(3), Direct(k))` → `If(..., ..., Nothing)`, trois branches. Mesuré
(seed 3711, board MC1_67, `tauAunShi`) :

    SenseOfStone(r2) -> SenseOfStone(r1) -> ZephyrsGrace(r2) -> ZephyrsGrace(r1)
                     -> StormOfFire(r2)  -> StormOfFire(r1)  -> SenseOfStone(r2) -> ...

`StormOfFire` vit deux tours puis part, et la phase suivante ne pose AUCUN stat-mod d'ATTACK : la
fenêtre « effet parti, aucun remplaçant sur la même stat » existe naturellement.

`1170 ZephyrsGrace` (branche `k = 2`, stat 1 MOVEMENT, `ConfigConst(0xe = extraMovement)`, même
durée) est **hors du lot des 11** et reste non inscrit — même patron, résidu nommé.

### Comment les index de variable sont tranchés

`ConfigVar(8) = extraDmg` est établi par une dizaine de ports. Les deux autres le sont **par
élimination stricte, puis confirmés par une source indépendante** :

* `UnbreakableDuty` n'a que trois variables. `dmgReductionPct` = `0x46` (lu sur
  `UnbreakableDuty_DamageReductionEffect$$CreateEffectDamageMalusForDefense`, même index que
  `SereneUnifierSenseOfStoneEffect`), `extraDmg` = 8 ⇒ **`0x1e` = `extraHp`**. Confirmé live : le
  `statDelta[health]` natif tombe **exactement** sur `extraHp[L50] × 180 %` (§3).
* `0x30 = armorReduction` : confirmé par `AdaptiveToxinsAbility$$CreateBehaviour`, qui lit
  `GetVariableForLevel(0x30)` alors que l'ability `AdaptiveToxins` n'a **qu'une seule** variable au
  gameconfig — `armorReduction`. Zéro ambiguïté.
  ⚠ Le port note `GetNumberConstant(0x30 = extraCritChance)` sur `ThrillSeekersEffect` : c'est un
  **trait**, autre table de clés (`trait_var`), et sa valeur lue est validée live — l'index cité en
  commentaire n'est pas confronté ici.

## 3. Mesures live

### 1171 — l'EXPIRATION (`probe_371_serene_unifier_live.py`)

`tauAunShi` (HERO au pool), capture prise AVEC l'effet actif, seed offline, échéance des deux côtés.
Rejoué sur **deux couples (seed, board)** — `(3711, MC1_67)` et `(4242, C4_09)` — résultats identiques :

| | ATTACK avec l'effet | résidu opaque | ATTACK après échéance |
|---|---|---|---|
| LIVE (oracle) | 2101 | — | **1304** |
| MOTEUR, inscrit | 2101 | **0** | **1304** |
| MOTEUR, non inscrit | 2101 | 797 | **2101** |

Delta à l'expiration : **live 797 == moteur 797**. Le bras non inscrit garde le bonus **à vie**
(écart 797). `797 = extraDmg[L50] (443) × 180 %` — magnitude re-dérivée de gameconfig, delta pris au
natif : deux sources indépendantes, résidu 0.

### 1251/1256 — l'ATTRIBUTION (`probe_371_unbreakable_duty_live.py`)

Le behaviour entier est sous `If(AmountIsEqualOrGreater(Count(UnitsWithTraits(Friends(
AllDeadOrResurrectedUnits), [0x1a, 0x10])), Direct(2)), ..., null)` — **>= 2 alliés morts**
(cf. `UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits`). Le montage les fabrique : deux Black
Templars mis à 1 PV (`--unit-stat`) puis tués en pilotant l'unité adverse.

| stat | `statDelta` natif après le cast | magnitude gameconfig × 180 % | attribué (inscrit) | attribué (non inscrit) |
|---|---|---|---|---|
| ATTACK | **1996** | `extraDmg[L50]` 1109 → **1996** | 1996, résidu 0 | 0, résidu 1996 |
| HEALTH | **9970** | `extraHp[L50]` 5539 → **9970** | 9970, résidu 0 | 0, résidu 9970 |

Les stats COURANTES sont identiques dans les deux bras (5309 / 69970) : c'est l'attribution qui
change, pas la valeur — d'où le caractère silencieux du défaut.

## 4. Les verdicts NON PORTÉS, et pourquoi

* **`1004/1005/1006 MightOfHeroes_*` — DEAD.** `MightOfHeroesAbility$$ExecuteBehaviour` existe en
  binaire et pose bien les trois effets, mais l'ability est **absente du gameconfig** (re-mesuré :
  `GC.ability("MightOfHeroes")` → vide). Ses variables ne sont donc pas résolubles : un port serait
  **inerte** (magnitude `None` → aucune contribution). Garde du verdict :
  `test_might_of_heroes_stays_dead` — si l'ability revient au gameconfig, le test rougit et la RE
  ci-dessus suffit à l'inscrire.
* **`1103 KanOpener_ReduceArmor` — 0 porteur.** L'ability est au gameconfig et sa magnitude est
  résoluble, mais aucune unité ne la porte sur les cinq voies (`unit_map find --ability KanOpener` =
  0). L'effet ne peut donc jamais apparaître dans `decisionView.effects` : l'inscrire serait un port
  qu'aucun montage n'exerce. Le résidu nommé de `factory.py` est **fermé** (les deux noms y sont
  écrits, avec la RE et la raison de la non-inscription).
* **`1351/1352/1507 EnvStatBoost_*` — ENVIRONNEMENT, et magnitude CONTEXTUELLE.** Le poseur est une
  ability de board (`BaseStatBoostAbility`), pas une unité : la voie de confrontation est **un board
  qui porte la tuile**, jamais un roster. Et le montant n'est pas une variable lisible : c'est
  `PercentageOf(StatAmount(<stat>, part 3 = INITIAL), GetNumberConstant(<clé>))`, donc une forme
  OVERRIDE (`applied_stat_mods`, magnitude lue sur le ctx du porteur), pas le couple mono-stat de la
  base. Deux travaux distincts, aucun exercé ici.

## 5. `31 StatModifier` — TRANCHÉ : aucun poseur, l'`EffectType` est *registered-but-dead*

Deux balayages indépendants, qui se recoupent.

**(a) Les six chemins de pose, par xrefs.** Les 5 surcharges `AddStaticStatModifierEffect{,ToOwner}`
+ `AddOrUpdateStaticStatModifierEffect` ; tous leurs call-sites énumérés. Deux seulement ne passent
PAS un `EffectType` littéral — ils lisent un champ de record via un getter virtuel :
`APowerUpAbility$$AddAbsoluteBoost` et `$$AddPctBasedBoost`. **Éliminés** : les trois implémentations
concrètes (`PowerUp_DamageAbility$$get_PctBasedStatBoost`, `PowerUp_HealthAbility$$get_PctBasedStatBoost`,
`PowerUp_HitsAbility$$get_AbsoluteStatBoost`) portent `0x473`, `0x477`, `0x475` — pas `0x1f`.

**(b) Le littéral, sur TOUT le binaire.** `(void *)0x1f,` (la forme sous laquelle Ghidra rend un
argument `void*` non final, celle qu'on lit sur `0x493`, `0x3ec`, `0x4e3`…) apparaît dans **5
fonctions sur 65 000**, et **aucune** n'est une pose d'effet :

| fonction | ce que `0x1f` y est |
|---|---|
| `LivingLightningMoveEffectAbility$$CreateTrigger` | `On(0x1f)` — un `TriggerEvent` |
| `RevitalizingMalignancyAbility$$ExecuteBehaviour` | `AtomicGroup(0x1f, …)` — un id de groupe |
| `CombatRestorativesAbility$$ExecuteBehaviour` | idem |
| `LightCoverEffect$$…`, `TrenchEffect$$Create…` | classes d'effet de TUILE (id de tuile) |

`&DAT_0000001f` (l'autre forme que Ghidra emploie pour les petites constantes, cf. `&DAT_00000008`
= `extraDmg`) : **0 occurrence**. Les 244 hits de `0x1f)` sont des `GetNumberConstant(0x1f)` — un
index de constante d'ability (ex. `BasiliskBarrageAbility$$GetNumShellsTotal`), autre enum.

⇒ **Aucun chemin lisible ne pose `31`.** Sa fabrique existe dans `EffectsDatabase$$InitializeEffects`
(c'est ce qui le fait apparaître dans l'inventaire de #366) mais rien ne la référence : c'est du
**registered-but-dead**, et il n'y a rien à porter.

⚠ **Limite de la méthode** : `search_code` porte sur le pseudo-C INDEXÉ ; un corps pleinement
partagé (`__Il2CppFullySharedGeneric`) ou une fonction non indexée y échapperait. La conclusion tient
sur la conjonction (a) ∧ (b), pas sur (b) seul.

## 6. Ce qui n'est PAS couvert

* **Aucun port des 8 non inscrits** — verdicts ci-dessus, RE écrite pour chacun.
* **Le buff cross-unité de 1171 n'est mesuré que sur le porteur-SOURCE.** Aun'Shi arrose aussi ses
  amis adjacents et les amis T'au à <= 2 ; pour eux le seed porte le niveau d'ability du PORTEUR, pas
  du POSEUR (même limite que `RitesOfBattle`), donc la magnitude offline n'y est pas exacte et une
  part reste dans le résidu opaque. **Sous-attribution, jamais sur-attribution** — `seed_unit_stats`
  reproduit toujours le `Current` capté.
* **`1170 SereneUnifierZephyrsGrace`** (même feuille, même durée, stat MOVEMENT) est hors du lot des
  11 et n'est pas inscrit.
* **Le retrait des permanents 1251/1256 n'est exercé par aucun montage** — et c'est structurel :
  `turns` est NULL au décompilé, aucun chemin natif ne les retire. La garde qui les concerne est la
  **contre-épreuve** (`test_unbreakable_duty_permanents_survive_the_expiry_tick`) : ils ne doivent
  RIEN perdre au tick.
* **Aucune mesure sur le canal DÉCISION** : ce cas ne touche que la face COMBAT/stats.

## 7. Artefacts

| quoi | où |
|---|---|
| classes d'effet | `scripts/python/engine/entities/effects/loki/serene_unifier.py`, `.../unbreakable_duty.py` |
| registre | `scripts/python/engine/entities/effects/factory.py` (3 entrées + le résidu KanOpener fermé) |
| mesure offline (table RE + le piège démontré) | `scripts/python/probe_371_static_statmod_g1.py` |
| montages live | `scripts/python/probe_371_serene_unifier_live.py`, `probe_371_unbreakable_duty_live.py` |
| gardes | `scripts/python/tests/engine/runner/test_static_statmod_g1_expiry.py` (9, offline), `test_static_statmod_g1_live.py` (6, live) |
