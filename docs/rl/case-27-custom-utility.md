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

## Ou l'utilite d'ACTION est OBSERVABLE (instrument)

Le terme custom n'apparait ni dans `pairUtility` (etage PAIRE) ni dans le terme Tile. Deux
instruments existants ont ete evalues et **ne marchent pas** sur un runner isole :

- **`bucketAudit*`** (`frida/hooks/features/bucket-audit.ts`) — cense exposer `BucketAction.Utility`
  (= u_full + custom). `bucketAuditStatus` rend `enabled:true, listeners:5` mais **0 fire** (y
  compris `ctorFires`) pendant une evaluation IA de runner : `findBucketMethod` resout les
  MethodInfo du generique OUVERT `Bucket\`1`, dont le body n'est jamais execute (le body reel est
  le gshared). **Instrument mort dans ce build** (correctif = resoudre le gshared, cf. les RVAs
  documentees dans le module ; necessite un rebuild+reinject).
- **`aiUtilityTrace*`** — lit les cles `Utilities` consultees, mais est scope au **mirror**
  (`knownConfigs=0` -> "no mirror UtilitiesDatabase captured yet"), pas au runner isole.
- `--l3` (`playbook_action.utility` = l'utilite d'action exacte) reste l'instrument direct, mais
  il est SESSION-GLOBAL (crash si un autre agent walke l'IA en parallele).

**Voie utilisee a la place (sans hook)** : l'utilite d'action native est *encadree* par le CHOIX
natif (`aiDryRunAllUnits`, read-only, per-unite) une fois les autres etages verifies :
`u_action = tile + pairUtility(natif) + custom`. On mesure `tile` (offline) et `pairUtility`
(RPC, scoreur natif) ; le choix natif borne alors `custom` par une inegalite. Un **A/B causal**
(une seule entree bascule la condition, geometrie et paires FIGEES) donne le signe, la condition
exacte et un encadrement de la magnitude — sans jamais fitter un scalaire.

## PORTES (4) — `engine/playbook/loki_custom.py`

| Ability (id) | VA | Formule mirroir | Poids (seed-bc) | Porteur | Validation |
|---|---|---|---|---|---|
| **ArmoriumCherub** (1014) | @18111c530 | `Fix64(1)` constant (aucune garde) | — | adeptRetributor `Vindicta` [lineup] | Live : runner 132 step 13 natif=1014, moteur=1014 [MATCH] (dispatch + custom appliques). Constante triviale -> RE + garde offline. |
| **LightOfSanguinius** (1177) | @181133d70 | `count(units du joueur-du-caster a PV%==100) * W` (iteration directe des units : `GetOriginalPlayer(caster)` -> `GetStat(Health,part1)==100`) | `LightOfSanguinius_FullHealthFriendlyUnits` = **-10** | bloodDante `Dante` [lineup] | Live : reaches `_best_attack` (Melta 5-hit) ; custom = -40 (4 allies pleins) correctement CALCULE + APPLIQUE (probe `_solver27_dante_probe`), natif=moteur [MATCH] runner 138. Flip-decisif non isole (la normale boostee de Dante domine toutes les geometries d'arene atteignables) -> couverture partielle assumee. |
| **HeraldOfTheApocalypse** (1020) | @1811441b0 | `foreach (e in GetAllNormalAttackTargets(caster).Targets) if (EnemyCouldBeDamagedWithNormalAttack(e)) return 0; return W` — `EnemyCouldBeDamagedWithNormalAttack @18111da80` = `GetAllNormalAttackTargets(e).Targets.Count > 0`. Terme CONSTANT sur (tuile, cible). | `HeraldOfTheApocalypse_CannotKillEnemy` = **50** | blackHaarken `Haarken` [hero, `--list-pool`] | **A/B causal live** (probe `probe_custom_utility_27_live.py`, runners 1276/1299/1304) : geometrie caster/ennemi FIGEE, seul un appat allie bouge -> natif bascule Herald <-> normale ; paires natives BIT-IDENTIQUES dans les 2 bras (8.019551052711904 / 0.018102815374732018) -> zero confond de prediction. Frontiere mesuree = **portee d'ARME de l'ennemi depuis sa tuile** (astraOrdnance r3 -> bascule d=3/4 ; blackTerminator r1 -> d=1) : exclut une feuille d'adjacence. Borne : **C > 34.22**. |
| **Drachnyen** (1029) | @18112dc60 | `count(GetAdjacentEnemies(tuile d'attaque, ownerId)) >= 2 ? W : 0` (BattleQuery slot 0x7d + predicat `<>c` ; l'`ownerEntityId` scope aux ENNEMIS). Terme **POSITION-dependant**. | `Drachnyen_MultipleAdjacentUnits` = **10** | blackAbaddon `Abaddon` [hero, `--list-pool`] | **A/B causal live** apres neutralisation du confond de PAIRE (Drachnyen FIXE les PV du caster a 4729 -> `--hp-player 4729` rend le set-health neutre, paire native = 0 ; sans ca la paire natif=-35.4 vs offline=+2.5 ecrase le +-10). Runner 1373 : caster LOIN (0 ennemi adjacent a sa tuile COURANTE), tuile d'attaque a 1 ennemi -> natif NORMALE (54.139 vs 50.000+C) ; a 2 ennemis -> natif **DRACHNYEN** => le count porte sur la **tuile d'ATTAQUE**. Allie adjacent au lieu d'un ennemi -> natif reste sur la normale => **les allies ne comptent pas**. Encadrement : **5.547 < C < 10.716** (runners 1363 / 1335). |

Les quatre HERITENT la prediction de degat du `DefaultActiveAbilityPlaybook` ; #27 ne porte QUE le
terme custom (la prediction est deja assuree par `prediction.py`, ecarts de degat = hors perimetre).

### Correctif STRUCTUREL induit par Drachnyen (`ai/action_generators.py::_best_attack`)

Le natif somme le custom **dans** `CalculateActionUtility @181406ee0` (vtable +0x348, avant le
terme Tile) — donc **avant** l'argmax par tuile de `EvaluateInternal @181408980`. Le port
l'ajoutait APRES le sweep de tuiles (`u_action = u_full + custom` une fois `pair_best` choisi) :
inoffensif pour un custom CONSTANT (ArmoriumCherub, NormalAttack, Herald, LightOfSanguinius) mais
un custom POSITION-dependant ne pouvait alors JAMAIS changer la tuile choisie. Le sweep compare
desormais `u_full + custom(tuile)`. Neutre par construction sur les customs constants (garde
d'agreement ci-dessous : 0 regression).

## RESIDUS (18) — verdict + VA + blocage

### Dead-code / aucun porteur (2)
- **ProperKilly_NormalAttack** @1811532a0 — **AUCUN porteur** : le scan EXHAUSTIF du gameconfig
  (123 lineup + 481 npc + 65 summons, champs `activeAbilities`/`passiveAbilities` ET dump brut des
  defs d'unite) ne rend AUCUNE unite referencant `ProperKilly` ; la cle n'existe que dans
  `units.abilities` (`damageProfile=Power, nrOfHits=1, dmgPct=60`) et dans un `baseMultiplier`.
  **Absente aussi de l'enum `ActiveAbilityType`** cote moteur (`ProperKilly` -> None) : le moteur ne
  peut meme pas dispatcher. Formule RE'e : `IsMeleeAttack(casterPos, target) @181153980` &&
  `GetStat(target,Health=5) != GetStat(GetHighestHealthMeleeTarget(casterPos, eligibles) @181153430,
  5)` -> constante `Fix64` statique @DAT_183267560+0x18 ; sinon `Fix64.FromInt(GetStat(target,5) + 1)`.
  Verdict **dead-code** : non portable, non validable, non pertinent.
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

### Sous-selecteur = methode `BattleQuery` a token non resolu (3)
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
- **MortisRound** (1004) @18114d190 — `(int) GetTargetUtilityDiffOnDisplace(caster, casterMainTile,
  Func GetDisplaceUtility @18114d2d0, target).Value`. `GetTargetUtilityDiffOnDisplace @1814ab840` =
  `max_{t in tuiles de deplacement candidates} ( Composite(UtilityAttackCase.Base(target, posCourante,
  tuileCourante, ability)) - Composite(UtilityAttackCase.Base(target, t, t, ability)) )`, clampe > 0,
  defaut 0 ; le `Composite` est le service #7 du conteneur, methode d'interface 5 — evaluateur d'un
  `UtilityAttackCase` SANS prediction de degat (`UtilityAttackCase.Base @181104c80/@181104e20` ne
  remplit que Unit/Position/Tile + ability). Puis `(int)` = TRONCATURE (tout diff < 1 -> 0).
  ultraEliminatorSgt `Eliminator Sergeant` [hero, `--list-pool`].
  **Mesure live (#27-1, runner 1386, cible a d=1/2/3, `--hp-target 40000`)** : le natif choisit
  l'attaque NORMALE dans les 3 geometries alors que l'ecart d'action (paires natives verifiees au
  `pairUtility`) n'est que de **0.012** (d=1) / 0.875 (d=2,3) -> **custom mesure < 0.012**, soit
  effectivement **0** (coherent avec la troncature `(int)` et un diff de deplacement nul en terrain
  plat). Aucun port : ajouter le terme exigerait l'evaluateur de composite `UtilityAttackCase.Base`
  (sous-systeme entier) pour un terme mesure NUL — port speculatif interdit.
  Debloque par : port de `UtilityAttackCase.Base` + de l'evaluateur de composite (slot 5 du service
  #7) ; a re-mesurer d'abord sur un board a ELEVATION/couverture (ou pousser la cible change
  reellement son utilite positionnelle).
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

- **Garde d'agreement CIBLEE, zero regression** (`engine_agreement_stages.py --build`) :
  - seed **31337** : prediction 10/10, utilite 10/10, ability **13/13**, move **18/18** (100%) ;
  - seeds **777 + 12345** : prediction 21/21, utilite 21/21, ability **26/26**, move **32/32** (100%).
  Ces seeds exercent le sweep de tuiles de TOUTES les abilities -> ils couvrent le correctif
  structurel `_best_attack` (custom entre dans l'argmax par tuile).
- **ArmoriumCherub** : live-matched (runner 132 step 13). Dispatch + custom appliques.
- **LightOfSanguinius** : reaches `_best_attack`, custom -40 correctement calcule+applique (probe),
  natif=moteur [MATCH] runner 138. Flip-decisif non isole (limite geometrie/kit Dante) — documente.
- **Herald (1020) + Drachnyen (1029)** : `probe_custom_utility_27_live.py` — les DEUX bras de chaque
  A/B causal sont exerces cote NATIF *et* reproduits par le moteur (runners 1413/1414) :
  Herald appat d=3 -> natif 69 / moteur 69 ; appat d=4 -> natif **1020** / moteur **1020** ;
  Drachnyen 1 ennemi adjacent -> natif 69 / moteur 69 ; 2 ennemis -> natif **1029** / moteur **1029**.
  AVANT le port, le moteur repondait `69` dans les deux bras « custom actif » (divergence de choix
  d'action sans divergence de degat, exactement la signature de cet etage).
- **Garde de forme OFFLINE** : `probe_custom_utility_27.py` (dispatch 1014/1177/1020/1029, valeurs des
  4 formules, y compris la POSITION-dependance de Drachnyen).

### Non couvert (explicite)

- Les **18 residus** ci-dessous (chacun avec son debloqueur nomme).
- **MortisRound** : terme mesure < 0.012 en arene plate ; **non re-mesure sur board a elevation /
  couverture** (ou le diff de deplacement pourrait etre non nul). Le port reste bloque par
  l'evaluateur de composite quoi qu'il arrive.
- **Herald** : le mirror de `GetAllNormalAttackTargets` n'applique PAS les regles de ciblage fines
  (LOS/obscurcissement, taunt/`GetOnlyTargets`) — borne SUPERIEURE de l'ensemble, exacte sur terrain
  degage (le cas mesure). Un ennemi qui « voit » une cible a travers un mur serait compte a tort.
- **Drachnyen** : la mesure a ete faite avec le confond de paire NEUTRALISE (`--hp-player 4729`) ;
  en bataille reelle l'ecart de prediction du `set health` (paire natif -35.4 vs offline +2.5 a PV
  pleins, +40.6 vs +3.8 a PV bas) DOMINE le +-10 -> corriger la prediction de Drachnyen (hors #27)
  est prioritaire devant ce terme pour l'agreement reel.
- Les ecarts de PREDICTION de degat de ces units (ex. MortisRound off 3.700 vs natif 4.440 =
  HeavyWeapon x1.5) sont PRE-EXISTANTS et hors perimetre #27 (relevent de `prediction.py`).
- La **magnitude exacte** des termes n'est pas mesuree au scalaire pres mais ENCADREE
  (Herald C > 34.22 ; Drachnyen 5.547 < C < 10.716) : les valeurs portees viennent du decompile
  (`GetUtilityValue(<cle>)`) et sont resolues a l'execution depuis la BC, jamais codees en dur.

## Technique generalisable

**Mesurer un terme d'ACTION sans instrument d'action : A/B causal + verification de l'etage PAIRE.**
Le custom n'est visible ni dans `pairUtility` ni dans le terme Tile, et les deux hooks d'utilite
d'action sont hors service sur un runner isole (cf. « Ou l'utilite d'ACTION est OBSERVABLE »). La
recette qui marche, sans hook :
1. **Fixer** toute la geometrie qui alimente la PAIRE (caster, cible, tuiles d'attaque) et ne faire
   varier QUE l'entree de la condition du terme (un appat allie qui bouge, un 2e ennemi adjacent).
2. **Prouver** que l'etage paire n'a pas bouge : `pairUtility` (scoreur natif) dans les deux bras —
   des valeurs BIT-IDENTIQUES ferment la porte au confond de prediction.
3. **Lire le choix natif** (`aiDryRunAllUnits`, read-only, per-unite) : la bascule d'ability entre
   les deux bras est la preuve causale ; `u_action = tile + pairUtility + custom` transforme chaque
   bras en une INEGALITE sur `custom` -> encadrement de la magnitude sans fitter un scalaire.
4. **Si le natif ne bascule jamais, suspecter un confond de paire AVANT de conclure « pas de terme »** :
   sur Drachnyen, la paire native valait -35.4 la ou l'offline disait +2.5 (prediction du `set health`
   manquante) — un ecart de 38 qui rendait tout +-10 inobservable. Le neutraliser (`--hp-player` =
   valeur du set-health) a fait apparaitre le terme immediatement. Un « aucun effet mesure » sans
   verification de la paire est un FAUX NEGATIF.

**Avant de porter un `CalculateCustomUtility`, trancher la ROUTE DE DISPATCH offline, pas la formule.**
Un override natif ne pese QUE s'il atteint `_best_attack` : verifier `constants.damageProfile` +
`not is_noncomp` (script `_dispatch`), puis le TYPE de porteur (MoW = hors-plateau en arene) et le TYPE
de sous-selecteur du corps (constante / iteration directe d'unites / adjacence deja portee
`count_adjacent` / **arbre DSL** / **BattleQuery a token** / **multi-hit** / **utilite de deplacement**).
Seuls constante + iteration-directe + adjacence-portee se portent sans sous-systeme. Ce triage EN AMONT
evite les ports speculatifs : 18/22 overlays sont bloques par 4 sous-systemes (DSL, BattleQuery-token,
multi-hit, deplacement) ou par une limite de harnais (MoW off-board) / non-modelisation (`dp=False`) /
dead-code — chacun nomme son debloqueur exact ci-dessus (roadmap de reprise).

**Un token `BattleQuery` non resolu n'est pas forcement un blocage** : Herald (0x44) et Drachnyen (0x7d)
etaient classes « token non resolu » et se sont averes portables — la SEMANTIQUE du token se lit sur le
comportement (frontiere de portee mesuree pour 0x44, seuil d'adjacence + exclusion des allies pour 0x7d)
plutot que sur la table d'interface. Re-tester les residus « token » par A/B avant de les laisser dormir.

**Un terme d'action POSITION-dependant impose de verifier OU le port ajoute le custom.** Le natif le somme
dans `CalculateActionUtility` (donc avant l'argmax de tuile) ; tout port qui l'ajoute apres le sweep rend
le terme inerte sans jamais lever d'erreur. Signature du bug : le terme « existe » offline mais ne change
jamais la tuile choisie.
