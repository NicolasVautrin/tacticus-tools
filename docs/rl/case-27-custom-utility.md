# case-27 — Overrides `CalculateCustomUtility` (terme d'ACTION de l'utilite Comparable)

`ComparablePlaybook<T>.CalculateCustomUtility @181407840` (base = `Fix64(0)`) est un terme AJOUTE
par-dessus `u_full` dans l'assemblage du `BucketAction` :
`u_action = u_full + CalculateCustomUtility` (port : `engine/ai/action_generators.py::_best_attack`).
Il n'apparait PAS dans `pairUtility` (preuve L3 #64) ; il ne pese que dans le CHOIX final d'action
(concurrence serree). Enumeration ghidra exhaustive du 2026-07-23, build `gqfc5mff6c`.

## Deja couverts (hors #27)

- `ComparablePlaybook<T>` @181407840 = `Fix64(0)` (base.py).
- `ALoki_NormalAttackPlaybook<T>` @1813726e0 = `Fix64(1)` constant (common.py `NormalAttackPlaybook`) —
  couvre `Idun.NormalAttackPlaybook<T>` @18149ee60 + `Loki_NormalBossAttackPlaybook` @1811497c0.
- `TwistedScience_HealPlaybook` @18116fb00 (common.py `HealPlaybook.score` : +100 / +100 Genestealers).

## Gate de dispatch dans le moteur (decisif pour le triage)

Le custom n'a d'effet QUE si l'ability atteint `_best_attack`. `state_bridge._plans_for_unit` ne feede
une ability comme attaque que si `_is_attack_ability` : **`constants.damageProfile` present ET
`not is_noncomp(id)`**. Consequences mesurees :

- `damageProfile` absent (`dp=False`) -> l'ability n'est PAS une attaque offline -> le custom n'est
  JAMAIS invoque (Chronometron, DevoutPush, ForwardObservers, HealingBalms_Heal).
- porteur = **MoW** (Machine of War) -> en runner ARENE le MoW est **hors-plateau** (`origin=None`) ->
  son attaque n'est pas feedee a `_best_attack` -> custom jamais invoque (live-confirme, runner 132
  step 15 : `deathCrawler` cast `PlagueburstMortar` natif, moteur = `move`). Invalidable en arene.
- sous-selecteur natif = **arbre DSL** (`DSLFactory` : `TilesInTriangleShape`, `UnitsWithTrait`,
  chain-targets) OU **methode `BattleQuery`** a token (0x44/0x77/0x7c/0x7d/0x7f/0xb1) OU
  **`GenerateMultiHitAttackPredictions`** OU **utilite de deplacement** (`UtilityMovementCase`,
  `GetTargetUtilityDiffOnDisplace`) -> l'ensemble compte depend d'un SOUS-SYSTEME non porte ->
  port speculatif (interdit : mirror 1:1, `no-unvalidatable-ports`).

Poids resolus a l'execution via `ctx.wt.sub("ActiveAbilities", <key>)` (jamais hardcodes) ;
valeurs lues de `data/seed-bc.json` citees pour lecture.

## PORTES (2) — `engine/playbook/loki_custom.py`

| Ability (id) | VA | Formule mirroir | Poids (seed-bc) | Porteur | Validation |
|---|---|---|---|---|---|
| **ArmoriumCherub** (1014) | @18111c530 | `Fix64(1)` constant (aucune garde) | — | adeptRetributor `Vindicta` [lineup] | Live : runner 132 step 13 natif=1014, moteur=1014 [MATCH] (dispatch + custom appliques). Constante triviale -> RE + garde offline. |
| **LightOfSanguinius** (1177) | @181133d70 | `count(units du joueur-du-caster a PV%==100) * W` (iteration directe des units : `GetOriginalPlayer(caster)` -> `GetStat(Health,part1)==100`) | `LightOfSanguinius_FullHealthFriendlyUnits` = **-10** | bloodDante `Dante` [lineup] | Live : reaches `_best_attack` (Melta 5-hit) ; custom = -40 (4 allies pleins) correctement CALCULE + APPLIQUE (probe `_solver27_dante_probe`), natif=moteur [MATCH] runner 138. Flip-decisif non isole (la normale boostee de Dante domine toutes les geometries d'arene atteignables) -> couverture partielle assumee. |

Les deux HERITENT la prediction de degat du `DefaultActiveAbilityPlaybook` ; #27 ne porte QUE le
terme custom (la prediction est deja assuree par `prediction.py`, ecarts de degat = hors perimetre).

## RESIDUS (20) — verdict + VA + blocage

### Dead-code / aucun porteur (2)
- **ProperKilly_NormalAttack** (1086) @1811532a0 — AUCUN porteur (scan gameconfig : nul champ ne
  reference `ProperKilly` ; `orksWarboss`=Gulgortz porte Waaagh/LightImUp). Formule RE'e (melee klaw :
  `IsMeleeAttack` + `GetHighestHealthMeleeTarget` + `GetStat(5)` -> constante @DAT_183267560 ou
  `FromInt(GetStat(target,5)+1)`). Non portable (invalidable, dead).
- **Repair_GalvanicField** (1119) @181155520 — AUCUN porteur (scan gameconfig nul). Formule RE'e
  (repair/(GetStat(target,5,2)+1)*100/2, gate `FUN_18000c1b0(0x3f)`). Dormant (confirme #85).

### Non-modele : `dp=False` -> n'atteint pas `_best_attack` (4)
- **Chronometron** (1226) @181125ab0 — `W(Chronometron_AffectedEnemies=10) * count(GetAffectedEnemies)`
  [DSL]. necroChronomancer [lineup]. Debloque par : modeliser l'ability comme action (hors attaque).
- **DevoutPush** (1053) @18112c7b0 — `ALoki_NormalAttack.custom(=1) * 2 = 2` constant. templInitiate
  [summon]. Debloque par : modelisation de l'action push.
- **ForwardObservers** (1185) @18113bb70 — `(pas de markerlight ? W(=200):0) + RemainingPct(target) *
  W(=40)`. tauSmnStealthSuit [summon]. Debloque par : modelisation de l'action.
- **HealingBalms_Heal** (1212) @181142dc0 — `Sigma CalculateUtilityFromHealEvent(MakeHealPredictions) *
  const`, gate `!HasEffect(0x5df=1503)`. Sous-ability de heal declenchee par le PASSIF `HealingBalms`
  de spaceWolfPriest `Baldr` [lineup] ; pas d'entree gameconfig active. Debloque par : voie heal
  passive-declenchee.

### Porteur MoW hors-plateau en arene (invalidable) (3)
- **PlagueburstMortar** (1169) @181134e00 — `count(GetAdjacentEnemies) * W(=10)`. `GetAdjacentEnemies`
  @1811c4330 = DSL `Enemies(Units(AdjacentTiles(caster)))` = PORTABLE fidele via `battle_query.
  count_adjacent(caster_tile, ctx.epos)` (meme `IterateAdjacentTiles`). Porteur deathCrawler MoW ->
  hors-plateau en arene -> custom jamais invoque (live-confirme). Port fidele DISPONIBLE, retenu en
  residu faute de harnais on-board (le seul disponible est l'arene).
- **DaemonicOrdnance** (1148) @1811286c0 — `10 * count(ennemis sur GetTargetAreaTiles)`.
  `GetTargetAreaTiles` @1811cfbf0 = DSL `TilesOnSameElevation(TilesInTriangleShape(...))`. blackForgefiend
  MoW hors-plateau + DSL triangle. Debloque par : MoW on-board + evaluateur DSL de forme.
- **MalleusRocketLauncher** (1142) — voir Stikkbomb (playbook partage). astraOrdnanceBattery MoW.

### Sous-selecteur = arbre DSL a evaluer (chain / UnitsWithTrait) (1, + PlagueburstMortar/DaemonicOrdnance/Chronometron ci-dessus)
- **MortarionsPlagueWind** (1093) @18114ca30 — `count(UnitsWithTrait(chain-targets, 0x3ea=1002))`.
  deathBossMortarion [npc-boss]. Debloque par : evaluateur DSL (chain `GetTargets3` + `UnitsWithTrait`).

### Sous-selecteur = methode `BattleQuery` a token non resolu (5)
- **HeraldOfTheApocalypse** (1020) @1811441b0 — `(aucun ennemi damageable au normal ? W(=50):0)` via
  `GetAllNormalAttackTargets` (BattleQuery 0x44) + `EnemyCouldBeDamagedWithNormalAttack`. blackHaarken
  [lineup]. Debloque par : semantique exacte de `GetAllNormalAttackTargets`/`EnemyCouldBeDamaged`.
- **Drachnyen** (1029) @18112dc60 — `(count(BattleQuery 0x7d, Func) >= 2 ? W(=10):0)`. blackAbaddon
  [lineup]. Debloque par : resolution du token 0x7d + du predicat Func `b__1_0` (`Drachnyen_MultipleAdjacentUnits`).
- **DoomSiren** (1199) @18112cd30 — `W(DefinitelyOverkill=40) * #(preds WillBeOverkill) +
  W(TargetHasAdjacentEnemy=50) * (BattleQuery 0x7f count > 0)`. emperKakophonist [lineup]. Debloque
  par : flag overkill par-prediction + token 0x7f.
- **InstrumentsOfVengeance** (1215) @1811460d0 — `20000 + (Any(0x7f)?0:100) + 20 * count(0x77 echouant
  le predicat)`. darkaBossLion [npc-boss]. Tokens 0x7f/0x77.
- **MartialExemplar** (1216) @18114ae20 — `1000 * count(IsNormalUnit sur BattleQuery 0x7f)`.
  darkaBossLion [npc-boss]. Token 0x7f.
- **TheLionsWrath** (1217) @18116aba0 — `30 * (0xb1).field + 2000 * count(IsNormalUnit & Trait(0x7ea=
  2026) & Trait(0x10=16) sur 0x7f) + (target Trait(0x10)?150:0)`. darkaBossLion [npc-boss]. Tokens 0x7f/0xb1.

### Sous-systeme utilite de deplacement (2)
- **MortisRound** (1004) @18114d190 — `(int) GetTargetUtilityDiffOnDisplace(...).Value`.
  ultraEliminatorSgt [lineup]. Debloque par : port de `GetTargetUtilityDiffOnDisplace`.
- **SorcerousFacade** (1100) @18115b9d0 — `MovementUtility(UtilityMovementCase(caster, targetMainTile))
  - MovementUtility(UtilityMovementCase(caster, casterTile))` (swap). thousTzaangor [lineup]. Debloque
  par : port de `UtilityMovementCase` + son evaluateur.

### Sous-systeme prediction multi-hit (2)
- **PlasmaGrenade** (1098) @181151040 — `Sigma sur units affectees de Sigma utilite
  GenerateMultiHitAttackPredictions` ; ==0 -> constante MaxValue-like. eldarSmnGuardian [summon].
- **Stikkbomb** (1051) @18115f7c0 — `-Sigma CalculateUtilityFromDamageEvent sur les AMIS touches par
  MalleusRocketLauncherAbility.GetAdditionalTargets` (penalite tir ami) via
  `GenerateMultiHitAttackPredictions`. Classe nommee `StikkbombPlaybook` mais corps appellent
  `MalleusRocketLauncherAbility` -> playbook PARTAGE Stikkbomb(1051, orksOrkBoys [summon]) /
  MalleusRocketLauncher(1142, astraOrdnanceBattery [MoW]). Debloque par : reutilisation de
  `GenerateMultiHitAttackPredictions` + resolution du partage d'id.

### Sans id `ActiveAbilityType` cote moteur (1)
- **SavageEchoes** @1811586d0 — `(GetRegenerateCondition non satisfaite ? W(DislikesAboveHealthPct=-10)
  : 0)`. bloodTerminator `Cezare` [lineup]. **Aucun id numerique** dans `ActiveAbilityType`
  (absent de `ability-names.ts` ET `active_ability_type.py`) -> le moteur ne peut pas dispatcher.
  + sous-systeme d'evaluation de condition (`FUN_180026c90`). Debloque par : id d'ability + eval condition.

## Validation

- **Garde 31337 CIBLEE** (`engine_agreement_stages.py --build --seeds 31337`) : 100% tous etages
  (prediction 10/10, utilite 10/10, ability 13/13, move 18/18) — **ZERO regression**. Structurel : les
  ids 1014/1177 n'apparaissent pas dans le roster 31337 ; le port n'ajoute que des dispatch cibles.
- **ArmoriumCherub** : live-matched (runner 132 step 13). Dispatch + custom appliques.
- **LightOfSanguinius** : reaches `_best_attack`, custom -40 correctement calcule+applique (probe),
  natif=moteur [MATCH] runner 138. Flip-decisif non isole (limite geometrie/kit Dante) — documente.
- **Non couvert** : les 20 residus (par blocage ci-dessus) ; le flip-decisif isole de LightOfSanguinius ;
  les ecarts de PREDICTION de degat pour ces units exotiques (ex. +20 pairUtility sur Vindicta au walk
  132) sont PRE-EXISTANTS et hors perimetre #27 (relevent de `prediction.py`).

## Technique generalisable

**Avant de porter un `CalculateCustomUtility`, trancher la ROUTE DE DISPATCH offline, pas la formule.**
Un override natif ne pese QUE s'il atteint `_best_attack` : verifier `constants.damageProfile` +
`not is_noncomp` (script `_dispatch`), puis le TYPE de porteur (MoW = hors-plateau en arene) et le TYPE
de sous-selecteur du corps (constante / iteration directe d'unites / adjacence deja portee
`count_adjacent` / **arbre DSL** / **BattleQuery a token** / **multi-hit** / **utilite de deplacement**).
Seuls constante + iteration-directe + adjacence-portee se portent sans sous-systeme. Ce triage EN AMONT
evite les ports speculatifs : 20/22 overlays sont bloques par 4 sous-systemes (DSL, BattleQuery-token,
multi-hit, deplacement) ou par une limite de harnais (MoW off-board) / non-modelisation (`dp=False`) /
dead-code — chacun nomme son debloqueur exact ci-dessus (roadmap de reprise).
