# #419-r1 tranche 14 — `HeavyBoltPistol` (1083), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Tête des résidus ATTACK de #419-r1 (2 porteurs). Le corps n'avait **pas** été lu.

## 1. L'inventaire du nom — TROIS artefacts sous l'id `1083`, et un piège d'OUTILLAGE

| enum qualifié | valeur `1083` | rapport avec cette tranche |
|---|---|---|
| `PassiveAbilityType` / `TriggeredAbilityType` | **`HeavyBoltPistol`** | **CETTE TRANCHE** |
| `ActiveAbilityType` | `NeedsMoreDakka` | sans rapport |
| `EffectType` | `ChampionOfTheFeast_ReduceArmor` | sans rapport |

Le NOM `HeavyBoltPistol` n'apparaît que dans **un** enum (`frida/enums.tsv`) : il n'y a donc **pas**
de mold d'attaque normale sous un autre id, contrairement à `RighteousRepugnance` 1107 → 1182 ou à
`ElectroShock` 1303 → 1178.

**Piège d'outillage, MESURÉ** : `gameconfig.ability_name(1083)` rend **`"NeedsMoreDakka"`** — son
index est celui d'`ActiveAbilityType`. Toute lecture de config passe donc par le NOM
(`TriggeredAbilityType.HeavyBoltPistol.name`), jamais par l'id. Même forme que le piège de la
tranche 5 (`1103` → `"Supercharge"`).

## 2. Le corps natif, LU

`IdunBattle.AI.Playbook.Loki.HeavyBoltPistolPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__2` — disposition lue **dans le wrapper** : `sm@+0x10 = state`, `sm@+0x18 = current`,
`sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`. Le délégué `getUtilityVal` **n'est pas capturé**
(comme `Neuroparasite`, `LightImUp`, `Shrapnel`) : la sortie n'est **aucune** clé de
`Utilities.Default.TriggeredAbilities`.

`HeavyBoltPistolPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, deux états :

```csharp
if (IsRegularAttack(case)) {                        // TriggeredAbilityPlaybook<T>$$IsRegularAttack
    var trig = DSLTriggers.IsAdjacent(dsl.<DSLTriggers @+0x88>,
                                      dsl.<DSLSelectors @+0x90>.Get(case.Caster),   // case@+0x10
                                      dsl.<DSLSelectors @+0x90>.Get(case.Target),   // case@+0x20
                                      unitSelectionType: 3);
    if (trig.ShouldTrigger(new AbilityEntities(/* memset 0x128 à 0 */))) {
        var cfg = this.<BaseTriggeredAbility @+0x58>.<AbilityConfiguration @+0x20>;
        int dmg = AbilityConfiguration.GetVariableForLevel(cfg, 0xb /* dmg */,
                                                          GetAbilityState(case.Caster), false);
        var pred = this.<IBattleQuery @+0x60>.<slot 0x24>(
                       case.Caster, case.Target, case.CasterPosition,  // case@+0x10/+0x20/+0x18
                       case.AbilityType,                               // case@+0xf0
                       dmg, AbilityConfiguration.GetDamageProfile(cfg), null, null);
        yield return CalculateUtilityFromDamageEvent(
                         new ProbableDamageEvent(case.Target, pred, null, null),
                         case.Caster, case.CasterPosition);            // état 1
    }
}
yield return Fix64.op_Implicit(0);                                     // état 2
```

Six lectures qui ne se devinent pas — les quatre premières sont **confrontées live** (§5) :

1. **La gate d'adjacence porte sur les positions RÉELLES, PAS sur la tuile d'attaque balayée.**
   C'est la lecture centrale, et elle est contre-intuitive. Les deux opérandes du trigger sont des
   **ENTITÉS** : `IdunBattleLogic.Entities.DSLSelectors$$Get(entity)` capture l'entité à la
   CONSTRUCTION du sélecteur — c'est pourquoi l'`AbilityEntities` passée à `ShouldTrigger` peut être
   entièrement memset à 0 sans conséquence. `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$
   ShouldTrigger` fait `a.Any() && b.Any() && a.All(x => b.All(y => query.<slot 0x60>(x, y)))` (lu :
   court-circuit à `false` au premier échec, `false` si l'un des deux ensembles est vide), et le slot
   0x60 est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` →
   `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(GetTiles(x), GetTiles(y))` : les tuiles
   **réellement occupées**. `case.CasterPosition` (`UtilityAttackCase@+0x18`) n'entre pas dans la
   gate. Conséquence mesurable : le terme est **constant sur tout le balayage de tuiles** d'une même
   cible — nul partout si le caster n'est pas déjà au contact, plein partout s'il l'est.
   ⚠ **Tous** les playbooks attack portés qui gatent sur une géométrie le font depuis la TUILE
   (`avalanche_of_muscle` : `<slot 0x60>(casterTile, target)` ; `cosmic_horror` :
   `case.CasterPosition.MainTile` ; `special_issue_combi_melta` : distance cible ↔ tuile d'attaque).
   Un port écrit par analogie se tromperait — et sur les deux diagonales seulement, donc
   silencieusement sur les crans alignés.
2. **La tuile d'attaque entre PAR la prédiction** (`case.CasterPosition` est le 3ᵉ argument du slot
   0x24). Les modifiers positionnels et le prédicat `is_melee` des effets d'attaquant s'évaluent donc
   depuis elle, pendant que la gate reste ancrée sur la tuile réelle. Les deux ancres coexistent dans
   le même corps. **NON EXERCÉ par le montage** — résidu `#419-r1-tr14-r2`.
3. **Le canal de prédiction est le slot 0x24, pas le 0x23.** Les slots d'`IBattleQuery` se lisent sur
   les proxys NOMMÉS de `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`, dont chaque
   corps porte son `FUN_1801e7040(inner, <klass IBattleQuery>, <slot>)` — table **re-dérivée** ici,
   et elle corrige au passage une imprécision de la tranche 5 (qui appelait « 0x23 » la surcharge
   `casterPosition`) :

   | slot | méthode | 3ᵉ argument |
   |---|---|---|
   | 0x21 / 0x22 | `GetNormalAttackPrediction` | `casterTile` / `casterPosition` |
   | **0x23** | `GetAttackPrediction(…, ability, amount, profile, hp0, prev)` | `casterTile` |
   | **0x24** | idem | **`casterPosition`** ← CE CALL-SITE |
   | 0x25 / 0x26 / 0x27 | surcharges à délégués `calculateDamageAtTile` | — |
   | 0x28 | `GetMultiHitAttackPrediction(…, hits)` | `casterPosition` |

   `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (surcharge `casterPosition`) écrit le
   LITTÉRAL `1` comme nombre de coups au slot 10 d'`IDamagePredictionQuery` : **hits forcés à 1**,
   exactement comme le 0x23 de `psyker` / `avalanche_of_muscle` / `shrapnel`. La différence 0x23 vs
   0x24 est le TYPE du 3ᵉ argument, sans effet observable ici.
4. **Le montant est la variable `dmg` SEULE** — `GetVariableForLevel(cfg, 0xb, state, false)`, et
   `AbilityVariableType` **11 = `dmg`** (`frida/enums.tsv`), la SEULE variable de la config
   `HeavyBoltPistol`. Ni `minDmg`/`maxDmg` (12/13, la paire de `LightImUp` et de `Shrapnel`), ni
   moyenne, ni tirage : **un seul** appel dans le corps. `dmg` est dans
   `variablesAffectedByRarityBonus` → le multiplicateur de rareté s'applique.
5. **Le profil est celui de l'ABILITY (`Bolter`, `PiercingRatio` 20), jamais l'arme du caster.** Le
   6ᵉ argument est `AbilityConfiguration.GetDamageProfile(cfg)` = `constants.damageProfile`. Le corps
   ne consulte du caster NI arme, NI stat, NI trait — seulement son identité (pipeline modifiers), sa
   position, et le niveau de son propre passif. C'est ce qui rend la greffe légitime (§3).
   `nrOfHits` (= 1) existe au gameconfig mais **le playbook ne le lit pas** : aucun
   `GetNumberConstant` dans le corps, contrairement à `Shrapnel`.
6. **`case.AbilityType` (`@+0xf0`) est à la fois l'argument de la prédiction ET ce que la gate
   `IsRegularAttack` interroge.** `TriggeredAbilityPlaybook<T>$$IsRegularAttack` déroule un
   `Nullable<Nullable<ActiveAbilityType>>` depuis `case+0xf0` puis appelle
   `Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`.
   Conséquence identique à `LightImUp` : les gates `IsNormalAttack` / `IsMeleeAttack` des effets
   d'ATTAQUANT s'évaluent sur l'ATTAQUE NORMALE → `is_normal_attack=True` dans le builder de
   modifiers.

### Le foyer `IsMeleeAttack`, factorisé au 2ᵉ site

`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (slot **2** d'`IBattleQuery`) est consommé par
deux chemins natifs distincts — la gate `TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` et le
prédicat `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` — et le natif n'en
a **qu'une** fonction. Le corps, écrit à la main par la tranche 5 dans `light_im_up.py`, a migré dans
`engine/services/battle_query.py::is_melee_attack` ; `LightImUpPlaybook.is_melee_attack` en reste
l'adaptateur `(ctx, scene, ability_id)` → `(nom d'ability, élévations)`. Deux points au passage :

* la branche `Normal(3)` appelle `AreEntitiesAdjacent(casterPosition, target)` — donc le foyer
  `battle_query.are_entities_adjacent` (court-circuit d'identité #433-r1), et **pas** `is_adjacent`
  (`IterateAdjacentTiles`, qui ne rend jamais la tuile source) que la tranche 5 utilisait. L'écart
  n'est atteignable que si `attack_tile == tgt_pos`, régime impossible (la cible occupe sa tuile) ;
  `test_419r1tr5_light_im_up_live.py` re-joué **7 passed** après la migration ;
* ⚠ homonyme à ne pas confondre : `engine.entities.effects.base.is_melee_attack(is_ranged)` est un
  AUTRE artefact — le gate tri-état que les effets consomment une fois la nature du coup **déjà
  résolue**. Celui-ci la résout.

## 3. Le montage — pourquoi une GREFFE, et sur quel hôte

Les 2 porteurs sont le npc `templNpc1Initiate` et le SUMMON `templInitiate`
(`passiveAbilities: ["HeavyBoltPistol"]`, trait `Summon`, faction BlackTemplars).
La gate de confrontabilité a été jouée **dans l'ordre** :

1. `buildNormalizedBC` refuse tout npc → aucun `--p-units`.
2. **SUMMON sans invocateur — vérifié par balayage, pas supposé** (`case-92` §5bis recours 2) : les
   abilities qui le déclarent (`constants.unitId == "templInitiate"`) sont
   **`EnvFactionSummons:BlackTemplars`** et **`EnvFactionSummons:SpaceWolves`** (`nrOfSummons` 3), et
   **aucune** unité du catalogue ne les porte dans `activeAbilities` / `passiveAbilities` /
   `summonAbilities` / `mythicAbilities` (balayage des sections `summons` / `npc` / `lineup`). C'est
   un summon d'**environnement** : il n'y a pas de summoner à spawner, donc pas de voie « observer le
   summon » (#291). Même configuration qu'`admecSmnElectropriest` (tranche 12) et qu'`astraSmnMortar`
   (tranche 13).
3. **Greffe** (`catalog_inject.write_grafted_seed_bc`, recours 3) sur **`tauMarksman`** — HERO au
   pool, arme distance `Piercing` portée 3, `replace=True`. Elle est **légitime et c'est LU**
   (lecture 5) : le corps ne consulte du caster ni arme, ni stat, ni trait.

**Bras apparié** : deux runners identiques à un passif près (`graft` = `PassiveAbilities=[1083]`,
`base` = le bras greffé **moins** 1083 — surtout pas « les passifs d'origine », `replace=True` les a
déjà retirés ; piège mesuré par la tranche 9). `terme_natif = natif_graft − natif_base`.

Board `MC1_67`, seed `41083`, `Health = RemainingHealth = 10000` pour tout le monde (personne ne
meurt : `dmg` ≈ 1091 × 1.2 ≪ HP, et le composite `DamageDealt` reste dans sa zone **linéaire**).
Roster : `tauMarksman` + `necroWarden` contre `astraBullgryn` (la cible, **fixe**) et `astraCreed`.
Layout mesuré : `T=(0,0) A=(0,1) B=(0,2) K1=(0,4) K2=(0,6)`.

Le probe **refuse** (`MontageError`) si l'attaque normale de l'hôte n'est pas dans
`REGULAR_ATTACK_ABILITY_TYPES` : la gate du corps natif couperait alors le terme à tous les crans, et
un accord `0 == 0` ne prouverait rien. Mesuré : elle y est.

## 4. Les quatre crans — le produit croisé (position réelle) × (tuile d'attaque)

La cible ne bouge jamais. Le caster occupe **deux** emplacements et on évalue depuis **deux** tuiles
d'attaque : c'est le produit croisé qui discrimine, parce que la gate et la prédiction n'ont pas la
même ancre.

| cran | position RÉELLE de C | tuile d'attaque | terme attendu |
|---|---|---|---|
| `far` | `B` (2 hex de T) | `B` | 0 |
| `tileAdj_realFar` | `B` (2 hex de T) | **`A`** (au contact) | **0** ← la gate IGNORE la tuile |
| `adj` | `A` (au contact) | `A` | > 0 |
| `realAdj_tileFar` | `A` (au contact) | **`B`** (2 hex) | **> 0** ← la gate lit le RÉEL |

Les deux **diagonales** sont LES crans de cette tranche. Les deux crans alignés (`far`, `adj`) sont
franchis par un port qui gate sur la tuile **comme** par le port juste.

## 5. La mesure — accord EXACT aux quatre crans

`probe_419r1tr14_heavy_bolt_pistol.py --mutants`, runners `graft`/`base` appariés :

| cran | spot | tuile | natif greffé | natif apparié | **TERME natif** | port | port muté | **TERME porté** | écart |
|---|---|---|---|---|---|---|---|---|---|
| `far` | B | (0,2) | 42.711458 | 42.711458 | **+0.000000** | 48.170366 | 48.170366 | **+0.000000** | 0 |
| `tileAdj_realFar` | B | (0,1) | 9.738052 | 9.738052 | **+0.000000** | 9.738052 | 9.738052 | **+0.000000** | 0 |
| `adj` | A | (0,1) | 12.727454 | 9.738052 | **+2.989402** | 12.727455 | 9.738052 | **+2.989402** | +9e-9 |
| `realAdj_tileFar` | A | (0,2) | 35.102979 | 32.113577 | **+2.989402** | 51.159768 | 48.170366 | **+2.989402** | +9e-9 |

Le terme n'est pas un poids plat mais une **utilité de dégât complète** : l'accord est donc bien plus
contraignant que sur les tranches à poids BC. Et il est **identique aux deux tuiles** — ce que le
NATIF confirme de son côté (2.989402 des deux), ce qui *est* la lecture 1.

### Contre-épreuves (six mutants du port LIVRÉ, joués à chaque cran)

Critère = déplacement par rapport au port **non muté**, jamais l'écart au natif (piège #441/#446).

| mutant | `far` | `tileAdj_realFar` | `adj` | `realAdj_tileFar` |
|---|---|---|---|---|
| `gate_tile` (gate sur la TUILE) | inerte | **+2.989402** | inerte | **−2.989402** |
| `no_gate` (aucune gate) | **+3.979204** | **+2.989402** | inerte | inerte |
| `profile_weapon` (arme du caster) | inerte | inerte | **+8.978204** | **+8.978204** |
| `amount_half` (`dmg` / 2) | inerte | inerte | **−1.489702** | **−1.489702** |
| `melee_from_real` | inerte | inerte | inerte | inerte |
| `spread0` | inerte | inerte | inerte | inerte |

`gate_tile` a la signature exacte attendue : il mord sur **les deux diagonales et elles seules**.
Les deux mutants inertes partout sont des **résidus mesurés** (§7), et le test les garde **à
l'envers** (il exige leur inertie) plutôt que de les taire : s'ils se mettent à mordre, le montage a
changé de régime et le résidu doit être ré-instruit.

## 6. L'ability prise à l'envers — un ÉCART NATIF assumé

`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyBoltPistolAbility$$CreateBehaviour` :

```
If( IsMeleeAttack(dsl.Triggers),                        // <- la gate de la face COMBAT
    InformWeapon(dsl.Behaviors, GetDamageProfile(cfg), true, null)
    & AttackDamage(dsl.Behaviors, Owner@0x30, Target@0x60,
                   Direct(GetVariableForLevel(cfg, 0xb)),      // la MÊME variable `dmg`
                   Direct(GetDamageProfile(cfg)),              // le MÊME profil `Bolter`
                   Direct(GetNumberConstant(cfg, 0x2f)), …),   // nrOfHits = 1
    null )
```

La face COMBAT gate sur **`IsMeleeAttack`** (le slot 2, qui traverse `GetAbilityAttackRangeType` et
peut rendre vrai pour une ability typée `Melee` à n'importe quelle distance) ; la face DÉCISION gate
sur **`IsAdjacent(caster, target)`** (géométrie pure). Les deux corps sont lus séparément et ne
partagent aucun prédicat : le playbook **approxime** la gate de l'ability. Même forme d'écart que
`FireOfAbsolution` (le caster compte parmi ses propres amis côté playbook, exclu côté behaviour) et
que `Shrapnel` (pas de cap `nrOfProjectiles` côté playbook).

Le montant, le profil et le nombre de coups, eux, coïncident entre les deux faces.

## 7. Résidus NOMMÉS

* **`#419-r1-tr14-r1` — les porteurs RÉELS ne sont pas confrontés.** La greffe ne couvre ni les
  stats, ni les traits, ni l'arme du summon/npc `Initiate`. Elle est légitime pour ce terme (le corps
  ne lit du caster que son identité, sa position et le niveau de son passif), mais l'`Initiate`
  lui-même n'a jamais été en bataille. Débloqueur nommé, déjà porté par `case-92` §5bis : donner à
  `buildNormalizedBC` un chemin de stats explicite pour summons/npc. **Partagé** avec
  `#419-r1-tr12-r2` et `#419-r1-tr13-r2`.
* **`#419-r1-tr14-r2` — l'ancrage de la PRÉDICTION sur `case.CasterPosition` est LU mais NON
  EXERCÉ.** Le terme natif vaut `+2.989402` **à l'identique** depuis la tuile au contact et depuis
  celle à 2 hex : aucun canal positionnel n'est actif sur ce montage. Trois causes, toutes mesurées —
  (a) **aucun** board de `data/boards/` n'a d'élévation variée (balayage : 0 fichier sur l'ensemble
  des trois pools), donc pas de bonus d'élévation ; (b) `tauMarksman` ne porte aucun modifier gaté
  `IsMeleeAttack`/`IsRangedAttack` ; (c) `extra_pierce_melee == extra_pierce_ranged == 0`. Le mutant
  `melee_from_real` est donc inerte aux quatre crans. Un port qui ancrerait la prédiction sur la
  position réelle passerait ce montage. Débloqueur : un hôte porteur d'un effet gaté melee/ranged
  (ou d'un `ExtraPierceMelee ≠ ExtraPierceRanged`).
* **`#419-r1-tr14-r3` — le spread ±20 % n'est pas discriminé.** Le mutant `spread0` est inerte aux
  quatre crans : `HP = 10000`, aucun kill possible, et le composite ne consomme alors que la moyenne
  des bornes — identique à spread 0 et à spread 20. Cette tranche ne tranche donc **ni dans un sens
  ni dans l'autre** le résidu `#419-r1-tr5-r2` (`psyker`/`avalanche_of_muscle` posent `spread_pct=0`
  sur un slot qui converge vers le même slot 10 ; `light_im_up` et ce module gardent le défaut).
  Débloqueur : un montage où la cible peut mourir — `kill`/`overkill` sont des paliers sur les bornes,
  donc le spread y devient observable.
* **`#419-r1-tr14-r4` — la face COMBAT n'est pas portée.** `HeavyBoltPistolAbility$$CreateBehaviour`
  n'a **aucun** mirror dans `engine/runner` : une attaque de mêlée d'un `Initiate` ne fait donc pas
  partir le coup de pistolet côté exécution. Même forme que `#419-r1-tr9-r4-r3`, `#419-r1-tr10-r3`,
  `#419-r1-tr12-r3` et `#419-r1-tr13-r3`. La face DÉCISION livrée ne dit rien de l'exécution.
* **`#419-r1-tr14-r5` — l'écart de NIVEAU hors périmètre VARIE, et il se décompose.** `port −
  natif_graft` vaut `+0.000001` (tuile A, sans mouvement), `0.000000` (tuile A, après mouvement),
  `+5.458908` (tuile B, sans mouvement) et `+16.056789` (tuile B, après mouvement). Deux composantes,
  exactes à 1e-6 : **+5.458908** dès que l'attaque évaluée est un TIR — c'est *exactement* le résidu
  `#419-r1-tr13-r1`, mesuré sur le MÊME couple (`tauMarksman`, `astraBullgryn`), confirmation
  indépendante — et **+10.597881** de plus quand ce tir suit un DÉPLACEMENT. Sur la tuile B, le natif
  descend de `42.711458` (le caster y est déjà) à `32.113577` (il doit s'y rendre) ; le port rend
  `48.170366` dans les deux cas. La cause n'est **pas** instruite ici (feuille de dégât `has_moved`
  ou feuille de position du composite d'action) — le terme du passif, lui, s'accorde exactement dans
  les deux régimes, donc c'est hors périmètre de cette tranche. Mais c'est un gap chiffré et
  reproductible du composite d'attaque normale.

## 8. Face MOVE : `yield Fix64(0)` CONSTANT — ce n'est PAS un résidu

`HeavyBoltPistolPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` a été
**lu** : un unique état, `Fix64.op_Implicit(0)`, aucun champ de la SM consulté. Elle n'entre donc pas
dans `TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (même forme que
`Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution`, `CosmicHorror`,
`ElectroShock` et `Shrapnel`).

## 9. Registre `ABILITY_CLASSES` : sans objet

`HeavyBoltPistol` est un TRIGGERED (`PassiveAbilityType` 1083), pas une ACTIVE : il n'entre pas dans
`ABILITY_CLASSES` et ne porte donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (ces deux données
sont celles du registre des abilities ACTIVES, et `HeavyBoltPistolAbility` est déclenchée par
`CreateBehaviour`/`If(IsMeleeAttack …)`, jamais castée). Le seul registre concerné est
`TRIGGERED_ATTACK_PLAYBOOKS` (`playbook/psyker.py`), posé dans le même commit.

## 10. Artefacts

| rôle | chemin |
|---|---|
| port | `scripts/python/engine/playbook/heavy_bolt_pistol.py` |
| foyer factorisé | `scripts/python/engine/services/battle_query.py::is_melee_attack` |
| registre | `scripts/python/engine/playbook/psyker.py` (`TRIGGERED_ATTACK_PLAYBOOKS`) |
| probe (MESURE) | `scripts/python/probe_419r1tr14_heavy_bolt_pistol.py` |
| garde (TEST) | `scripts/python/tests/engine/test_419r1tr14_heavy_bolt_pistol_live.py` |
