# case-419-r1 tranche 9 — `RapidFire` (1135), la face ATTACK du second tir

**Verdict : PORTÉ + CONFRONTÉ LIVE.** Neuvième des résidus ATTACK de `#419-r1`, tête de liste par
nombre de porteurs (4). Le port vit dans `scripts/python/engine/playbook/rapid_fire.py` (l'en-tête
du module porte la RE complète, lecture par lecture) ; il entre au registre
`psyker.TRIGGERED_ATTACK_PLAYBOOKS` dans le même commit.

Ce que le passif fait, côté joueur (i2, qui recoupe le décompilé) :

> The Heavy Intercessor attacks twice if he did not move this turn, with each of the two attacks
> dealing Damage as normal.

## 1. Le corps, en cinq états

`IdunBattle.AI.Playbook.Loki.RapidFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` —
SM montée par le wrapper (`sm@+0x20 = case`, `sm@+0x28 = this`, le délégué `getUtilityVal` **n'est
pas capturé** : la sortie n'est aucune clé de `Utilities.Default.TriggeredAbilities`) :

```
if (case.MovementTile != EntityExtensions.GetMainTile(case.Caster, <IBattleState @+0x40>))
    yield Fix64(0);                                                           // état 1
else if (!IsRegularAttack(case))              yield Fix64(0);                 // état 2
else if (UnitExtensions.HasFlag(case.Caster, (UnitFlag)0 /* Moved */))
    yield Fix64(0);                                                           // état 3
else {
    var vt = <IBattleQuery @+0x60>.<slot 0x42>(case.Caster, case.CasterPosition,
                                               (ActiveAbilityType)0x45);      // GetValidTargets
    if (case.DamagePrediction.Value.WillBeKill) ValidTargets.Remove(vt, case.Target);
    if (vt.AllTargets.Count == 0)             yield Fix64(0);                 // état 4
    Fix64 best = Fix64(0);
    foreach (IEntity t in vt.AllTargets) {
        Fix64 p = (t == case.Target && case.DamagePrediction.Value.MightBeKill)
                    ? Fix64.Half : Fix64.One;
        var pred = <IBattleQuery @+0x60>.<slot 0x22>(case.Caster, case.Target,
                                                     case.CasterPosition);
        best = Fix64.Max(best, CalculateUtilityFromDamageEvent(
                   new ProbableDamageEvent(t, pred, p, null),
                   case.Caster, case.CasterPosition));
    }
    yield best;                                                               // état 5
}
```

Les lectures qui ne se devinent pas sont détaillées dans l'en-tête du module (huit points). Les
trois qui ont coûté le plus :

* **La prédiction est calculée UNE FOIS contre `case.Target` et RÉUTILISÉE pour chaque cible.** Ce
  n'est pas une lecture de décompilé mais de **désassemblage** : au call-site du slot `0x22` les
  trois arguments sont `mov rcx,[rax+0x10]` / `mov r8,[rax+0x20]` / `mov rax,[rax+0x18]` avec
  `rax = sm.case`, soit `(case.Caster, case.Target, case.CasterPosition)` — l'élément courant de
  l'énumérateur (`r15`) n'y entre pas, il n'apparaît que comme `target` de l'event. Le port hisse
  l'appel hors de la boucle (fonction pure des mêmes trois arguments) et le dit.
* **L'ensemble de cibles est demandé par le LITTÉRAL `0x45`** (= `ActiveAbilityType.Loki_NormalAttack`),
  jamais par `UnitExtensions.GetNormalAttackType(caster)` ni par `case.AbilityType`. C'est
  **observable** : `IdunBattle.Core.Services.AttackQuery$$GetValidTargets` fait
  `unit.GetComponent<ActiveAbilityComponent>().GetOrNull(0x45)` et, si l'unité n'a pas cette
  ability, **LogError puis `ValidTargets.Empty`** — le playbook tombe à l'état 4. Le
  `StaticBattleRules.ActiveAbility` cctor recense **17** autres attaques normales concrètes ; un
  porteur qui en a une rend donc **0** quelle que soit la géométrie (§4, régime `foreign`).
* **La sortie est un `Fix64.Max` borné en bas par zéro** — ni somme (`fire_of_absolution`), ni
  moyenne (`psyker`, `light_im_up`), ni produit (`boltstorm`). Deux conséquences : l'ordre
  d'énumération de l'`OrderedSet` est indifférent, et une utilité négative est écrasée à 0.

Face MOVE : `RapidFirePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` est
un `yield Fix64(0)` unique — décompilé LU. Son absence de `TRIGGERED_MOVE_PLAYBOOKS` **est** le
comportement natif.

## 2. Ce que ce port a corrigé au FOYER PARTAGÉ — `DamageUtility` lit l'ENTITÉ, pas la prédiction

`IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` prend
`actor = case.Target` (`case@+0x20`) puis lit :

* `UnitExtensions.GetStat(actor, 5 /*Health*/, 2 /*Max*/) + 1` → le `combinedMax` ;
* `IdunBattle.AI.Utilities.DamageUtility$$GetShield(actor)` → le bouclier ;
* `IdunBattle.AI.Utilities.DamageUtility$$GetRemainingHealth(this, actor)` =
  `GetStat(actor, 5, 0 /*Current*/) + 1 + GetShield(actor) + 1` → le restant.

**Seul le DÉGÂT** (et le repli `LimitedByMinHp → CurrentHealth`) sort du `DamagePredictionResult`.
Le port lisait `hpBefore`/`shieldBefore` de la prédiction : un **PROXY**, exact tant que l'event et
la prédiction portent la même cible. `RapidFire` est le premier producteur où elles diffèrent.

Corrigé par deux clés OPTIONNELLES (`targetHp`, `targetShield`) que `DamageUtility.evaluate` lit
quand elles sont là ; absentes, comportement antérieur **à l'identique** — aucun autre producteur ne
les pose. Les deux autres feuilles du composite ne sont **pas** concernées : `KillUnitUtility` et
`OverkillUnitUtility` lisent `WillBeKill`/`MightBeKill`/`WillBeOverkill`/`MightBeOverkill`, qui sont
des propriétés du `DamagePredictionResult` et comparent à son `CurrentHealth@+0x00`.

Mesure qui a nommé la cause (avant correction, montage à trois cibles de PV distincts) : pour
`case.Target = u77`, le natif rendait `4.591239` là où le port rendait `4.108584` — et
`4.108584 × (9539+2)/(8536+2) = 4.591239` **exactement**, c'est-à-dire le même dégât noté avec les
PV de l'autre cible. Les trois lignes retombent au bit près après correction.

## 3. Le montage — greffe, et pourquoi elle est LÉGITIME ici

Les 4 porteurs sont 3 npc `ultra*Intercessor*` + le SUMMON `ultraSmnHeavyIntercessor` : **aucun
HERO**, donc aucun `--p-units` possible, et un summon s'observe mais ne se commande pas (#291). La
greffe (`catalog_inject.graft_passive_ability`) est légitime parce que le corps ne consulte du
caster que sa **position**, son **flag `Moved`** et son **ensemble de cibles d'attaque normale** —
ni stat, ni trait, ni variable d'ability (le délégué scorer n'est même pas capturé par la SM).

**Le terme natif est une différence de DEUX mesures NATIVES** : `pairUtility(hôte greffé)` moins
`pairUtility(hôte privé du seul 1135)`, même seed, même board, même roster, même placement (apparié
par `visualId`). Le port n'entre pas dans sa définition, donc les résidus hors-périmètre du couple
(caster, cible) sont mesurés **à part** (colonne `socle`) au lieu d'être imputés au playbook.

⚠ Le bras apparié est le bras greffé **moins 1135**, surtout pas « les passifs d'origine » : avec
`replace=True` la greffe a déjà retiré `LightImUp` de `orksWarboss`, et le remettre ferait différer
les deux bras de DEUX abilities. Mesuré : `LightImUp` valait **+16.75** sur une tuile de mêlée du
montage, entièrement imputé au socle par un bras mal apparié.

## 4. Les quatre régimes, et ce que chacun est SEUL à trancher

`python scripts/python/probe_419r1tr9_rapid_fire.py --state-file <abs> --regime <r> --mutants`

| régime | hôte | ce qu'il installe | ce qu'il tranche |
|---|---|---|---|
| `home` | `orksWarboss`, passifs **remplacés** par 1135 | 3 cibles à distance 2 | le terme non nul, la gate 1 (`MOVE`), la gate 3 (`MOVED`) |
| `kill` | idem + `RemainingHealth` calibrés | une cible à kill POSSIBLE non garanti | `Fix64.Half` |
| `remove` | idem, géométrie `solo` | **une seule** cible légale, à kill GARANTI | `ValidTargets.Remove` (l'ensemble se vide → 0) |
| `foreign` | `templAggressor` (greffe **additive**) | attaque normale concrète `1128` | le LITTÉRAL `0x45` |

**Le couple `MOVE` / `MOVED` épingle les deux gates sans circularité** : sur la MÊME tuile, le natif
rend la MÊME valeur avant et après que le caster s'y soit réellement déplacé (mesuré : `30.569220`
des deux côtés, au bit près). Si seule la gate 1 existait, la seconde mesure porterait le terme (la
tuile est devenue la tuile courante) ; si seule la gate 3 existait, la première le porterait.

### Mesures (board `MC1_67`, seed 41135)

`home` — trois cibles, `hpmax` {u77: 9539, u79: 8536, u81: 8536} :

```
[HOME ] (3,4) u77 nat=13.049735 port=13.027541 | base= 6.162876 socle=+0.010481 terme_nat=+6.886859 terme_port=+6.875146
[HOME ] (3,4) u79 nat=23.448114 port=23.448114 | base=11.724057 socle=+0.000000 terme_nat=+11.724057 terme_port=+11.724057
[HOME ] (3,4) u81 nat=25.251815 port=25.251815 | base=12.625908 socle=+0.000000 terme_nat=+12.625908 terme_port=+12.625908
[MOVE ] (0,4) u79 nat=30.569220 port=30.569220 | base=30.569220 socle=+0.000000 terme_nat=+0.000000  terme_port=+0.000000
[MOVED] (0,4) u79 nat=30.569220 port=30.569220 | base=30.569220 socle=+0.000000 terme_nat=+0.000000  terme_port=+0.000000
```

L'écart de `-0.011712` sur u77 est **attribué, pas toléré** : le montage publie les bornes de dégât
natives (`decisionView.attackPlans`) contre celles du port — `natif=[470, 705] port=[470, 704]`,
soit **un point** de moyenne. Ce point se propage à `1 × 100/(8538) = 0.011712` (la cible notée par
l'argmax) et au socle `1 × 100/(9541) = 0.010481`. Les deux tombent exactement. La tolérance du test
est DÉRIVÉE de ce résidu mesuré (`P.term_tolerance`), pas posée au confort.

`kill` — accord à `1e-9` sur les cinq lignes, aucun résidu de dégât. `remove` — une seule cible
légale, kill garanti, terme natif **`+0.000000`** (nat == base au bit près). `foreign` — attaque
normale `1128`, `fromHere(0x45) = []` alors que `fromHere(1128) = [79, 77, 81]`, terme natif
**`+0.000000`** sur les trois cibles.

### Contre-épreuves — critère = DÉPLACEMENT par rapport au port NON MUTÉ

Jamais l'écart au natif : la paire porte des résidus hors-périmètre, donc `abs(port − natif) > EPS`
serait vrai même pour un mutant inerte.

| mutant | régime | déplacement max |
|---|---|---|
| `no_home_gate` (gate 1 retirée) | `home` | **+30.569** |
| `no_moved_gate` (gate 3 retirée) | `home` | **+30.569** |
| `sum_not_max` (somme au lieu de `Fix64.Max`) | `home` / `kill` | **+23.925** / **+118.514** |
| `pred_target_hp` (PV de la prédiction) | `home` / `kill` | **+0.870** / **+16.700** |
| `always_one` (`Fix64.Half` retiré) | `kill` | **+0.115** |
| `no_remove` (`ValidTargets.Remove` sauté) | `remove` | **+68.756** |
| `case_ability` (id concret au lieu de `0x45`) | `foreign` | **+38.475** |

Les sept mordent, chacun dans le régime où sa lecture est exercée — et la garde exige que **chaque**
mutant ait un tel régime (`test_every_reading_has_a_regime_where_its_mutant_bites`).

## 5. Ce qui a été rejoué

Garde jumelle `scripts/python/tests/engine/test_419r1tr9_rapid_fire_live.py` : **7 tests, 0 skip**
(268 s, 4 régimes, 8 runners construits et libérés au fil de l'eau).

Non-régression du foyer `DamageUtility` (chiffres du 2026-08-02, 0 skip) : offline `test_333`,
`test_344`, `test_353`, `test_383` → **50 passés** ; live `test_333`, `test_342`, `test_449`,
`test_419r1tr5` → **26 passés** ; voisins `test_419_lakrimae`, `test_419_r1_fire_of_absolution`,
`test_419_t6_cosmic_horror`, `test_plagueburst_mortar` → **28 passés** ; cliquet
`tests/test_419_playbook_wiring_ratchet_offline.py` → **3 passés**.

## 6. Résidus NOMMÉS

* **`#419-r1-tr9-r1`** — le canal `fromHere` est **live seulement**. `engine.ai.state_bridge` route
  `abilityTargets` vers `ability_targets_offline`, qui ne publie que `targets` (union sur les tuiles
  de déplacement). Le port lit donc un canal MUET hors-ligne et rend 0 — dégradation RESTRICTIVE,
  nommée. On ne se rabat **pas** sur `ctx.plans` (dont l'`abilityId` est l'attaque normale CONCRÈTE)
  : ce repli serait faux exactement dans le régime `foreign`. Fermeture : ajouter à
  `ability_targets_offline` une énumération ancrée sur la tuile COURANTE pour l'id demandé.
* **`#419-r1-tr9-r2`** — `IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn` non porté.
  Le natif l'évalue entre `GetOrNull` et le ciblage, et rend `ValidTargets.Empty` s'il est vrai.
  INERTE dans le régime de décision (l'IA évalue une unité qui n'a pas encore agi), et le canal
  `fromHere` le traverse de toute façon puisqu'il appelle le MÊME `AttackQuery.GetValidTargets`.
  NON CONFRONTÉ.
* **`#419-r1-tr9-r3`** — **résidu de PRÉDICTION hors périmètre** : contre `astraBullgryn`, la borne
  MAX du port vaut `704` quand le natif rend `705` (montage `home`, `orksWarboss` à distance 2). Un
  point. Il se propage à tout consommateur de cette prédiction, dont ce playbook.
* **`#419-r1-tr9-r4`** — **second résidu de prédiction, plus gros** : dans le régime `foreign`, le
  port rend `[1762, 2642]` contre `[876, 1314]` au natif pour `templAggressor` → `necroWarden`
  (facteur ~2), et `[2628, 3942]` contre `[2631, 3945]` pour `astraBullgryn` (3 points). Sans effet
  ici (le terme est nul des deux côtés dans ce régime) mais **ouvert** : `Boltstorm_NormalAttack`
  (1128) est une attaque normale CONCRÈTE dont le port ne dispatche aucun `PredictAttack` dédié.
* **`#419-r1-tr9-r5`** — `--unit-stat necroWarden:RemainingHealth=300` ressort à **2008** après le
  placement, alors que le même patch mord sur `astraBullgryn` et `tauAunShi`. Cause non établie
  (seule Necron du roster). Contourné en écartant cette unité du patch ; le levier n'est donc pas
  universel, et un montage qui compterait dessus mesurerait autre chose que ce qu'il croit.

## 7. Ce que ce cas n'établit PAS

* Les branches `Melee(1)` / `Ranged(2)` d'aucune gate de portée : ce playbook n'en a pas.
* Le comportement sur un porteur **réel** (npc / summon) : le montage est une GREFFE, il ne couvre
  ni les stats, ni les traits, ni les armes des quatre porteurs. Ce qui est confronté, c'est le
  CORPS du playbook, dont la RE établit qu'il ne les lit pas.
* Le cas `event.target` **allié** : `GetValidTargets` d'une attaque normale ne rend que des ennemis,
  donc la négation friendly-fire de `DamageUtility` n'est pas exercée par ce chemin.
