# case-445 — `AvalancheOfMuscle` (1028), et le premier playbook ATTACK qui FABRIQUE sa prédiction

Quatrième des 20 résidus ATTACK de `case-419` §7 (5 porteurs dispatchés). Le corps n'avait pas été
lu ; il ne ressemble à aucun de ses trois prédécesseurs.

**Résultat** : le playbook est porté et confronté live sur **trois montages**. Contrairement à
`BarbedOvipositor` (#438), qui **lit** `case.DamagePrediction`, celui-ci en **fabrique une neuve** —
celle du bonus de charge — et la fait scorer par le composite `Damage`. Aucun canal nouveau n'a été
nécessaire : le chemin « montant prédéfini, hits forcés 1 » existait déjà (`psyker.py`,
`fury_of_the_ancients.py`).

## 0. Le piège du nom, levé — `1028` désigne TROIS artefacts

Enums **qualifiés**, tous relus dans le port :

| enum | membre à 1028 |
|---|---|
| `TriggeredAbilityType` | **`AvalancheOfMuscle`** ← ce playbook |
| `ActiveAbilityType` | `SupremeCommander` |
| `EffectType` | `HeadClaimer_ExtraDmg` |

L'entrée déjà portée côté EFFET est **`EffectType.AvalancheOfMuscle_ExtraDamage = 1025`**
(`AvalancheOfMuscleExtraDamageEffect`, jumeau de `FeederTendrils` sans le nœud `IsNormalAttack`) :
c'est la face **COMBAT** du même passif, pas cette face-ci. Les deux se rejoignent sur **un seul**
point, et c'est un recoupement, pas une déduction : la magnitude (`extraDmg`, var index 8).

## 1. Le corps natif — SEPT états de yield

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook$$CalculateAttackUtilityInStepsInternal` monte
la SM `d__2` (case @+0x20, playbook @+0x28) ; corps =
`AvalancheOfMusclePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`.

```
mainTile   = EntityExtensions.GetMainTile(case.Caster)      // case@+0x10
casterTile = case.CasterPosition.MainTile                   // case@+0x18

if (case.AbilityType.HasValue                               // case@+0xf0
    && case.AbilityType.Value == (AbilityOrEffect)(TriggeredAbilityType)1028)
    yield Fix64(0)                                          // état 1  ANTI-RÉCURSION
if (!EntityExtensions.IsUnit(case.Target))       yield Fix64(0)     // état 2
else if (casterTile == mainTile)                 yield Fix64(0)     // état 3  il ne bouge pas
else if (!battleQuery.<slot 0x60>(casterTile, case.Target))
                                                 yield Fix64(0)     // état 4  pas au contact
else {
    w = battleQuery.<slot 0xaf>(case.Caster, [casterTile], case.Target)
    if (w == null)                               yield Fix64(0)     // état 5  aucune arme
    else if (!CameIntoContactWithEnemy(case))    yield Fix64(0)     // état 6  déjà au contact
    else {
        extra = ability.GetExtraDamage(UnitExtensions.GetAbilityState(case.Caster, 1028).Value)
        pred  = battleQuery.<slot 0x23>(case.Caster, case.Target, casterTile,
                                        case.AbilityType, extra,
                                        (DamageProfileType?)w.<+0x10>, false, null)
        yield CalculateUtilityFromDamageEvent(new ProbableDamageEvent(case.Target, pred),
                                              case.Caster, case.CasterPosition)   // état 7
    }
}
```

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook$$CameIntoContactWithEnemy` (méthode **propre**
au playbook, décompilée séparément — et le corps de `d__2` la **ré-inline** à l'identique) :

```
return  <slot 0x62>( [casterTile],           GetTiles(case.Target) )
     && !<slot 0x62>( GetTiles(case.Caster), GetTiles(case.Target) )
```

### Sept lectures qui ne se devinent pas

1. **Ce playbook ne lit PAS `case.DamagePrediction`.** Le paramètre `prediction` ajouté par #438 est
   accepté et **ignoré**, exactement comme le corps natif ignore `case@+0x28`.

2. **L'état 1 est un anti-récursion, pas un gate métier — et il n'est portable par AUCUN chemin du
   port.** `TriggeredAbilityPlaybook<T>$$CalculateUtilityFromDamageEvent` (l'état 7) reconstruit un
   `UtilityAttackCase` par `IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction` en y
   posant `abilityType = (AbilityOrEffect)T`, soit **triggered 1028**, puis évalue le composite
   `UtilityType.Damage` (**0x23 = 35**, littéral lu dans le corps), qui contient la feuille
   `TriggeredAbilities(2)`, qui re-dispatche ce même playbook. L'état 1 coupe la boucle.
   Côté port, `calculate_utility_from_damage_event` n'évalue que les **trois feuilles dominantes**
   (`engine/utilities/damage.py::DAMAGE_UTILITY`) ; la feuille triggered est ajoutée **hors
   composite** par `playbook/base.py`. La ré-entrée n'existe donc pas, et l'écrire en
   `ability_id == 1028` serait **FAUX** — `ability_id` porte un `ActiveAbilityType`, dont 1028 est
   `SupremeCommander`. **Résidu nommé** (§5).

3. **L'état 3 exige un MOUVEMENT RÉEL**, pas seulement l'adjacence finale. `get_MovementTile` est un
   corps **dédupliqué** (`IdunBattle.Core.UnitPosition$$get_MainTile(this+0x18)`) : appliqué à un
   `UtilityAttackCase`, `+0x18` est `casterPosition` (offsets relus dans
   `IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` : caster@+0x10, casterPosition@+0x18,
   target@+0x20, damagePrediction@+0x28, heal@+0xd0, repair@+0xdc, effectType@+0xe8,
   abilityType@+0xf0). Le nom `UtilityMovementCase` de la table est un mislabel de déduplication.

4. **Le prédicat n'est PAS `IsCharging`**, même s'il en est le jumeau sémantique. Le natif ne route
   pas vers `IdunBattle.Core.Services.BattleQuery$$IsCharging` (qui lit
   `UnitComponent.ChargedUnitIds@+0x190`) : il compare les tuiles avant/après. Différence
   observable — `CameIntoContactWithEnemy` **ignore les charges déjà acquises ce tour**. On mirrore
   le décompilé, pas le foyer `battle_query.is_charging`.

5. **L'adjacence est celle de `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(Tile, Tile)`**
   (décompilé lu) = `|elev1 − elev2| < 2 && (tile1 == tile2 || ConnectivityComponent.IsNeighbour)`.
   Porte d'élévation **inconditionnelle** ⇒ foyer `battle_query.is_adjacent`, jamais une adjacence
   hex nue. Les slots `0x60` / `0x61` / `0x62` sont les trois surcharges d'
   `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` (Tile×entité, liste×liste,
   entité×entité), toutes résolues sur `AreTilesAdjacent`.

6. **La magnitude est `extraDmg`, la MÊME variable que la face COMBAT.**
   `IdunBattleLogic.Entities.Abilities.Active.Loki.AvalancheOfMuscleAbility$$GetExtraDamage` =
   `AbilityConfiguration.GetVariableForLevel(config, 8, abilityState, fallbackToDefault: false)`, et
   `IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack`
   appelle `ConfigVar(config, 8, GetAbilityState, …)` sur la MÊME config. `AvalancheOfMuscle` n'a
   qu'**une** variable au gameconfig et `fallbackToDefault` vaut `false` (le natif **lève** si la
   variable manque) ⇒ l'index 8 ne peut désigner qu'elle. `extraDmg` est dans
   `variablesAffectedByRarityBonus` ⇒ multiplicateur de rareté appliqué. **Mesuré** : `extraDmg[L50]
   × 180 % = 599`, exactement le `+599`/coup de `test_ischarging_extra_damage_live.py` — recoupement
   indépendant de la face COMBAT.

7. **La prédiction est celle du slot `0x23`**,
   `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction(caster, target, casterTile, ability,
   amount, Nullable<DamageProfileType>, …)` : montant **prédéfini**, **hits forcés à 1** (littéral
   `1` passé au slot 10 d'`IDamagePredictionQuery`), spread 0 — même canal que `psyker.py` et
   `fury_of_the_ancients.py`. Le profil n'est PAS une constante d'ability : c'est `w.<+0x10>`, le
   `DamageProfile` de l'arme rendue par le slot `0xaf` =
   `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(caster,
   attackerTiles, target)` (foyer porté : `services/battle_query.py::select_weapon_pierce`, `case-184`).

**Face MOVE** : `AvalancheOfMusclePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext`
est un `yield Fix64.op_Implicit(0)` **constant** (décompilé lu). Rien à porter ; son absence de
`TRIGGERED_MOVE_PLAYBOOKS` **est** le comportement natif.

## 2. Porteurs — 5, dont un HERO au pool, aucun montage nécessaire

`unit_map find --ability AvalancheOfMuscle` : `astraBullgryn` « Kut » (**lineup / HERO**, présent
dans `rl_duel build --list-pool` au rank 17) + `astraBossBullgryn`, `astraBossBullgrynLEG`,
`astraBossBullgrynLHE`, `astraNpcBullgryn` (npc). Voie d'attribution : **passive** — le passif est
donc dans l'`AbilitiesComponent` sans aucune écriture, et le montage l'**atteste**
(`unitAbilityStates` doit contenir 1028, sinon il échoue).

## 3. Mesure — quatre régimes, trois montages

Les régimes se distinguent par la **tuile d'attaque** et la **position du caster**, jamais par un
poids constant :

| régime | configuration | attendu |
|---|---|---|
| `R_CHARGE` | caster à distance 2, tuile au contact | terme > 0 |
| `R_KILL` | idem, cible à 1 PV | terme **autre** (KillUnit/Overkill) |
| `R_ALREADY` | caster **déjà** au contact, change de tuile | 0 (état 6) |
| `R_STAY` | tuile d'attaque == tuile courante | 0 (état 3) |

`R_CHARGE` et `R_KILL` sont **deux points de la même chaîne** (`extraDmg` → prédiction slot 0x23 →
composite Damage) : un seul point se fitterait, deux ne se fittent pas.

```
A  MC1_67 / 41504 / astraCreed,astraDreir,admecDestroyer   caster (3,4)   extraDmg porté = 599
   R_CHARGE  @(2,4)  nat=66.644540   port=66.644540   d=-0.000000 | terme=+0.132758
   R_KILL    @(2,4)  nat=346.666667  port=346.666667  d=+0.000000 | terme=+173.333333
   R_ALREADY @(4,3)  nat=54.680784   port=54.680784   d=+0.000000 | terme=+0.000000
   R_STAY    @(3,4)  nat=54.680784   port=54.680784   d=+0.000000 | terme=+0.000000

B  MC1_67 / 777 / orksNob,tauCrisis,admecDestroyer
   R_CHARGE  @(2,4)  nat=130.003983  port=130.003983  d=-0.000000 | terme=+0.119498
   R_KILL    @(2,4)  nat=346.666667  port=346.666667  d=+0.000000 | terme=+173.333333
   (R_ALREADY / R_STAY : 54.680784 des deux côtés, terme 0)

C  C3_22 (palier UNIQUE) / 31337 / astraCreed,astraDreir,admecDestroyer   caster (4,3)
   R_CHARGE  @(5,3)  nat=66.644540   port=66.644540   d=-0.000000 | terme=+0.132758
   R_KILL    @(5,4)  nat=346.666667  port=346.666667  d=+0.000000 | terme=+173.333333
   (R_ALREADY / R_STAY : 54.680784 des deux côtés, terme 0)
```

Conformité **exacte** sur les quatre régimes des trois montages ; playbook retiré du registre ⇒ le
port perd exactement le terme sur les deux régimes de charge et **rien** sur les deux gates.

### Deux pièges de montage, mesurés

* **Sur un board à relief, `hexgeo.distance == 1` ne suffit pas.** Premier essai `C3_26` : la cible
  « adjacente » l'était géométriquement mais **pas pour le moteur** (`pairUtility` natif = `0`
  depuis la tuile courante). Le montage attestait donc un régime qu'il ne mesurait pas. Deux gardes
  posées : l'attestation d'adjacence passe par `battle_query.is_adjacent` (porte d'élévation), et
  **l'oracle atteste son propre montage** (`pairUtility` non nul depuis la tuile courante, sinon le
  montage est REFUSÉ). Le montage se tient désormais sur un **palier unique**.
* **Un écart port/natif n'est pas forcément de la tranche.** Sur `orksNob` (C3_26) et
  `eldarJainZar` (MC1_67/777) l'écart valait 43 à 70 points **alors que le playbook versait 0** sur
  la ligne : résidu **préexistant**, étranger. Le probe le DIT désormais dans son verdict au lieu de
  laisser l'imputer à la tranche.

## 4. Contre-épreuves — cinq jouées, et DEUX N'ONT PAS MORDU

Sur une contre-épreuve, **VERT est le résultat suspect**. Les mutations ont été appliquées après
vérification de leur ancre, et la restauration vérifiée identique au commit (`git diff` vide).

| mutation | effet attendu | verdict |
|---|---|---|
| registre vidé de 1028 | tout rougit | **MORD** (3 erreurs + 1 échec) |
| conjonct `not before` retiré | `R_ALREADY` rougit | **MORD** (`+0.062900`) |
| gate « le caster bouge » retiré | `R_STAY` rougit | **MORD** (`+0.188699`) |
| `extraDmg × 2` | `R_CHARGE` rougit | **MORD** (`+0.099569`) |
| `extraDmg` littéral **faux** (600) | l'étage rougit | **MORD** (garde d'étage seule) |
| état 4 désactivé | « hors contact → 0 » rougit | **NE MORD PAS** |
| `after` forcé à `True` | idem | **NE MORD PAS** |
| **les deux ensemble** | idem | **NE MORD PAS** |

**Ce que ces trois verts établissent** : les états **2 / 4 / 5** et le conjonct `after` de l'état 6
sont **mutuellement redondants sur la VALEUR** — ils rendent tous `0` sur les mêmes entrées, et seul
le *numéro d'état du yield* les distingue, invisible de l'extérieur. Le port est fidèle (les quatre
gates y sont, dans l'ordre natif), mais **aucune assertion prise sur la feuille ne peut les garder
isolément**. Le troisième vert le prouve : même les deux gates d'adjacence cassés ENSEMBLE, l'état 5
(`select_weapon_pierce` ne rend aucune arme à distance ≥ 2 pour un porteur mêlée) rend `0`.
La garde correspondante a donc été **remplacée** par une garde d'**étage** — les quatre combinaisons
de `_came_into_contact_with_enemy` hors runner — qui, elle, mord.

**Pouvoir de résolution de la garde live sur la magnitude, mesuré** : `extraDmg` 599 → 600 (1 point)
ne franchit pas `EPS = 1e-4` sur `R_CHARGE` (le terme vaut `0.199` pour 599, soit `3.3e-4` par
point) ; `× 2` le franchit largement. C'est la garde d'étage (§5 du test) qui tient l'unité — d'où
la décomposition en deux niveaux plutôt qu'une seule assertion de bout en bout.

## 5. Ce que ce cas ne couvre PAS

* **L'état 1 (anti-récursion)** — structurellement inatteignable côté port (§1 lecture 2). Il ne
  devient pertinent que si `calculate_utility_from_damage_event` se met à ré-entrer dans la feuille
  `TriggeredAbilities(2)`. **Effet mesuré aujourd'hui : nul** — le kit des 5 porteurs se réduit à
  `AvalancheOfMuscle` + les traits `Hero`/`BigTarget`, dont aucun n'a de playbook ATTACK au
  registre ; la ré-entrée native ne fait donc rien pour eux non plus. Le porter en `ability_id ==
  1028` serait un BUG (`ActiveAbilityType.SupremeCommander`) : il faudrait le **kind** de
  l'`AbilityOrEffect`, que le port ne transporte pas.
* **Les états 2 / 4 / 5 isolément** — redondants sur la valeur (§4). Portés, non gardables seuls.
* **Le régime RANGED** — les 5 porteurs sont mêlée-only (`4hmp1`, aucune arme à distance) : le
  `is_ranged` de `select_weapon_pierce` n'est jamais vrai. NON CONFRONTÉ, pas « non pertinent ».
* **Le régime ÉLÉVATION** — le montage se tient sur un palier unique, précisément parce qu'un
  relief fait diverger le gate mêlée natif du seul `is_adjacent` (§3). La porte `|Δelev| < 2` est
  lue au décompilé et portée, mais **non exercée** par la mesure.
* **`is_normal_attack = False`** — le natif transmet `ability = case.AbilityType` à la prédiction ;
  le port en dérive `ability_id in ctx.normal_ids`. Les trois montages n'exercent que l'attaque
  normale : la branche « ability active » (ex. `FragBomb` du même porteur) n'est pas confrontée.
* **Le régime MULTI-EVENTS (AoE)** — même angle mort que `#438-r1` : `astraBullgryn` n'a pas
  d'attaque AoE.

## 6. Fichiers

* Port : `scripts/python/engine/playbook/avalanche_of_muscle.py` ; registre :
  `scripts/python/engine/playbook/psyker.py`.
* Mesure : `scripts/python/probe_445_avalanche_of_muscle_pair_term.py`
  (`--board` / `--seed` / `--foes` paramétrables ; `--mutate-before` / `--mutate-move` /
  `--mutate-extra` = les trois contre-épreuves qui mordent).
* Garde : `scripts/python/tests/engine/test_445_avalanche_of_muscle_pair_term_live.py` (5 tests).
