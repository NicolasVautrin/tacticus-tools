# case-27 — Overrides `CalculateCustomUtility` (terme d'ACTION de l'utilite Comparable)

`ComparablePlaybook<T>.CalculateCustomUtility @181407840` (base = `Fix64(0)`) est un terme AJOUTE
par-dessus `u_full` dans l'assemblage du `BucketAction` :
`u_action = u_full + CalculateCustomUtility` (port : `engine/ai/action_generators.py::_best_attack`).
Il n'apparait PAS dans `pairUtility` (preuve L3 #64) ; il ne pese que dans le CHOIX final d'action
(concurrence serree).

## Inventaire — comment il a ete RE-DERIVE (tranche 3, 2026-07-28)

L'enumeration ghidra rendait **27 symboles**. Elle est INCOMPLETE, et la table de symboles ne peut
pas le dire : IL2CPP **deduplique les corps identiques**, et `methods.tsv` est indexee par ADRESSE —
un corps partage par N classes n'y a qu'UN SEUL proprietaire (cf. `docs/rl/case-170-get-priority.md`).

Contre-mesure appliquee : **balayage du SLOT DE VTABLE au runtime**, classe par classe
(`probe_27_custom_utility_inventory.py` : `findClassesNamed("Playbook")` -> `resolveVtableSlot`).

> ⚠ **CORRIGE PAR #218 (2026-07-29).** La tranche 3 balayait `0x108..0x808` SANS BORNE. Comme
> `resolveVtableSlot` lit `klass+off` en aveugle (il n'a pas acces a `vtable_count`), ce balayage
> DEBORDAIT sur l'`Il2CppClass` suivante — contigue en memoire — et rendait des `MethodInfo`
> parfaitement nommes appartenant a une AUTRE classe. Les chiffres ci-dessous sont ceux du sweep
> **BORNE** ; l'ancienne redaction (28 classes overridantes, slots a 0x548/0x5a8/0x668/0x7b8) est
> conservee plus bas a titre de trace corrigee. Detail complet, preuve et technique :
> **`docs/rl/case-218-amulet-voidwyrm-custom-utility.md`**.

Resultat sur le build `gqfc5mff6c` (sweep borne) :

- **377** classes `*Playbook*` vues au runtime, **93** portent un slot `CalculateCustomUtility`
  dans leur PROPRE vtable ; 191 rendent `no-slot` (vtable lue, pas de slot) et **93**
  `vtable-uninit` (vtable NULLE, classe jamais instanciee -> indetermine EXPLICITE, a trancher par
  la chaine d'heritage, pas par le balayage) ;
- **27 corps DISTINCTS** — l'enumeration ghidra etait juste sur les corps — et **27 classes**
  overridantes : il n'y a PAS de 28e. `AmuletOfTheVoidwyrmPlaybook` n'override rien (sa base
  `TriggeredAbilityPlaybook`1` descend directement de `System.Object`, hors de la branche
  `ComparablePlaybook`1` qui DECLARE le virtuel) ; le corps
  `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` n'a qu'**UN** user ;
- **le slot est au MEME offset partout : `+0x338`**, et rien d'autre. Les « 7 playbooks de
  TRIGGERED/passif a 0x548/0x5a8/0x668/0x7b8 » (AmuletOfTheVoidwyrm, ControlEdict,
  OmnissiahsBlessing, FoulInfusion, RedRampage, UnbreakableDuty, PrehensilePincerTail) etaient les
  7 memes lectures hors-vtable : re-balayees bornees, aucune ne porte le slot. Le controle de
  bornes de la tranche 3 (`probe_27_vtable_dump.py`, « coherent jusqu'a 0x5a8 puis du bruit »)
  n'a pas attrape l'erreur parce qu'un debordement ne tombe PAS dans du bruit : il tombe sur la
  vtable de la classe suivante, parfaitement formee.

## RE-DERIVATION SUR LE BUILD `rnca9r7q6c` (tranche 4, 2026-07-30) — 3 overrides NEUFS

L'inventaire ci-dessus a ete etabli sur `gqfc5mff6c`. Le jeu a change de build ; le meme balayage,
**relance contre la table du build COURANT** (`probe_27_custom_utility_inventory.py --build rnca9r7q6c`),
rend :

- **388** classes `*Playbook*` vues au runtime, **96** portent le slot, **tous a `+0x338`**
  (171 `no-slot`, 121 `vtable-uninit`) — la conclusion #218 « un seul offset » tient ;
- **29 corps distincts** : **26 nommes** dans `methods.tsv` + **3 corps PARTAGES** non nommes
  (la base `ComparablePlaybook<T>` a 52 users, `ALoki_NormalAttackPlaybook<T>` a 16, la definition
  generique `NormalAttackPlaybook`1` a 2) ; **0 corps nomme jamais atteint** par le balayage
  (source A incluse dans source B — les deux sources se recoupent exactement).

⚠ **Le defaut `--build gqfc5mff6c` du probe est un PIEGE** : lance sans `--build rnca9r7q6c` il croise
les RVA du runtime contre l'ANCIENNE table et rend « 24 corps nommes, 29 sans proprietaire, 24 nommes
jamais atteints » — un tableau parfaitement coherent et entierement FAUX. Toujours passer le hash du
build courant (`ls -d ~/AppData/Local/tacticus/games/*/`).

**Trois overrides que l'inventaire de la tranche 3 ne pouvait pas connaitre** (leurs porteurs sont des
unites AJOUTEES par ce build) :

| Playbook | Ability (id) | Porteur | `damageProfile` | Verdict |
|---|---|---|---|---|
| `HeavyWarpFlamerPlaybook` | HeavyWarpFlamer (1227) | thousSekhetar `Sekhetar Robot` [lineup] | oui (Flame) | **PORTE** (#27-4) |
| `MassDriverAcceleratorPlaybook` | MassDriverAccelerator (1222) | votanChampion `Kimm` [lineup] | oui (DirectDamage) | **residu** — `MassDriverAcceleratorAbility$$GetBuffTargets` (selecteur DSL) ; formule = `max(0, Count(GetBuffTargets.Evaluate(entities)) - 1) * W(MassDriverAccelerator_AdjacentFriendly = 5)` |
| `ResurrectionOrbPlaybook` | ResurrectionOrb (1009) | necroOverlord `Anuphet` [lineup] (+ 5 npc) | **NON** | **residu** — verrou 2 (route d'ability non-attaque) ; poids `ResurrectionOrb_LikesResurrection = 90`, `_LikesSummoning = 10` |

Par ailleurs `DevoutPushPlaybook` ne possede plus de corps propre sur ce build : il PARTAGE desormais
le corps de `ALoki_NormalAttackPlaybook<T>` (= `Fix64(1)`), ce que la tranche 3 decrivait comme un
corps distinct valant `2`. A re-verifier au decompile si le terme redevient pertinent.

### Prerequis de harnais leve dans le meme commit — `BC.Utilities` PERIMEE (3e catalogue)

Sans lui, **aucun** de ces trois overrides n'etait confrontable, et le diagnostic aurait ete
« le natif n'exerce pas cette branche ». `data/seed-bc.json` est la capture d'UN build ; sa table
`Utilities` (les poids nommes de l'IA) l'est aussi. Le build `rnca9r7q6c` **AJOUTE 16 cles et en
CHANGE 3** — dont `HeavyWarpFlamer_LikesAdjacentEnemies = 10`.

`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue` fait un
`TryGetValue` sur le dict de categorie ; **sur echec il LOGUE un warning et rend `Fix64(0)`**. La
degradation est donc SILENCIEUSE et PERMISSIVE (contrairement a `BC.Abilities`/#254, qui LEVE) : le
terme custom d'une ability neuve vaut 0 cote natif ET cote moteur, les deux bras d'un A/B rendent la
meme chose, et rien ne signale que la mesure ne mesure rien.

Correctif, mirror de `Idun.Source.IdunBattle.View.BattleConfigBuilder$$ParseAIUtilitiesConfiguration`
(appelee par `...$$CreateBattleConfig` : elle parse la cle exterieure en jeu d'utilites, la cle
intermediaire en `UtilityType`, et recopie VERBATIM le dict `{nom: entier}` — la table de la BC EST
`clientGameConfig.aiUtilities`) :

- `catalog_inject.refresh_ai_utilities(bc)` + `ai_utilities_from_gameconfig()` ;
- appelee par `rl_collect_batch._load_seed_bc` (cote NATIF, comme `refresh_ability_configs`) ;
- **et par `engine.weights.load()`** (cote MOTEUR) — sans ce second point, le natif verrait les poids
  neufs et le moteur ceux de la capture, une divergence introduite par le correctif lui-meme.

Delta mesure gqfc5mff6c -> rnca9r7q6c : `Default/ActiveAbilities` +7, `Default/TriggeredAbilities`
+5 et ~2, `Default/TriggeredAbilitiesNonOwner` +4 et ~1 ; **0 cle retiree**, 54 categories inchangees.

## Deja couverts (hors #27)

- `ComparablePlaybook<T>` @181407840 = `Fix64(0)` (base.py).
- `ALoki_NormalAttackPlaybook<T>` @1813726e0 = `Fix64(1)` constant (common.py `NormalAttackPlaybook`) —
  couvre `Idun.NormalAttackPlaybook<T>` @18149ee60 + `Loki_NormalBossAttackPlaybook` @1811497c0.
- `TwistedScience_HealPlaybook` @18116fb00 (common.py `HealPlaybook.score` : +100 / +100 Genestealers).
- `Repair_GalvanicFieldPlaybook` (1119) @181155520 — **DEJA PORTE par #85**, hors `loki_custom.py`
  (`ai/action_generators._repair_galvanic_candidates`). Decompile relu le 2026-07-25 :
  `if (!battleQuery.<0x3f>(target, GetUnitPosition(target), GetNormalAttackType(target))) return 0;`
  puis `M / (GetStat(target, Health=5, part=2) + 1) * 100 / 2` — soit exactement
  `custom = M/(hpMax+1) * 50` gate par `HasValidTargets(cible)`, ce que le port implemente
  (`custom = (M / (hp_max + 1) * 50.0) if _has_valid_targets(ctx, tg) else 0.0`).
  **Correction de la tranche 1**, qui le classait « dead-code / aucun porteur » : le porteur est
  admecManipulus (l'ability est GRANTED par le passif GalvanicField, donc absente des
  `activeAbilities` du gameconfig — d'ou le faux negatif du scan).

## Gate de dispatch dans le moteur (decisif pour le triage)

Le custom n'a d'effet QUE si l'ability atteint `_best_attack`. `state_bridge._plans_for_unit` ne feede
une ability comme attaque que si `_is_attack_ability` : **`constants.damageProfile` present ET
`not is_noncomp(id)`**. Consequences mesurees :

- `damageProfile` absent (`dp=False`) -> l'ability n'est PAS une attaque offline -> le custom n'est
  JAMAIS invoque (Chronometron, DevoutPush, ForwardObservers, HealingBalms_Heal).
- porteur = **MoW** (Machine of War) -> la machine DEPLOIE bien dans le runner arene (`--p-mow` /
  `--a-mow` ; `observeBattle.mows` non vide) mais elle n'a **pas de PositionComponent** et n'apparait
  donc NI dans `decisionView.units` NI dans `attackPlans` : elle n'est jamais une unite de DECISION
  cote moteur -> son attaque n'est pas feedee a `_best_attack` -> custom jamais invoque.
  **Re-confirme live le 2026-07-25 (runner 336, `--p-mow deathCrawler --a-mow blackForgefiend`)** :
  2 machines type-6 presentes, `aiDryRunAllUnits` ne leur propose aucune action. Invalidable en arene.
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

## PORTES (6) — `engine/playbook/loki_custom.py`

| Ability (id) | VA | Formule mirroir | Poids (seed-bc) | Porteur | Validation |
|---|---|---|---|---|---|
| **ArmoriumCherub** (1014) | @18111c530 | `Fix64(1)` constant (aucune garde) | — | adeptRetributor `Vindicta` [lineup] | Live : runner 132 step 13 natif=1014, moteur=1014 [MATCH] (dispatch + custom appliques). Constante triviale -> RE + garde offline. |
| **LightOfSanguinius** (1177) | @181133d70 | `count(units du joueur-du-caster a PV%==100) * W` (iteration directe des units : `GetOriginalPlayer(caster)` -> `GetStat(Health,part1)==100`) | `LightOfSanguinius_FullHealthFriendlyUnits` = **-10** | bloodDante `Dante` [lineup] | Live : reaches `_best_attack` (Melta 5-hit) ; custom = -40 (4 allies pleins) correctement CALCULE + APPLIQUE (probe `_solver27_dante_probe`), natif=moteur [MATCH] runner 138. Flip-decisif non isole (la normale boostee de Dante domine toutes les geometries d'arene atteignables) -> couverture partielle assumee. |
| **HeraldOfTheApocalypse** (1020) | @1811441b0 | `foreach (e in GetAllNormalAttackTargets(caster).Targets) if (EnemyCouldBeDamagedWithNormalAttack(e)) return 0; return W` — `EnemyCouldBeDamagedWithNormalAttack @18111da80` = `GetAllNormalAttackTargets(e).Targets.Count > 0`. Terme CONSTANT sur (tuile, cible). | `HeraldOfTheApocalypse_CannotKillEnemy` = **50** | blackHaarken `Haarken` [hero, `--list-pool`] | **A/B causal live** (probe `probe_custom_utility_27_live.py`, runners 1276/1299/1304) : geometrie caster/ennemi FIGEE, seul un appat allie bouge -> natif bascule Herald <-> normale ; paires natives BIT-IDENTIQUES dans les 2 bras (8.019551052711904 / 0.018102815374732018) -> zero confond de prediction. Frontiere mesuree = **portee d'ARME de l'ennemi depuis sa tuile** (astraOrdnance r3 -> bascule d=3/4 ; blackTerminator r1 -> d=1) : exclut une feuille d'adjacence. Borne : **C > 34.22**. |
| **Drachnyen** (1029) | @18112dc60 | `count(GetAdjacentEnemies(tuile d'attaque, ownerId)) >= 2 ? W : 0` (BattleQuery slot 0x7d + predicat `<>c` ; l'`ownerEntityId` scope aux ENNEMIS). Terme **POSITION-dependant**. | `Drachnyen_MultipleAdjacentUnits` = **10** | blackAbaddon `Abaddon` [hero, `--list-pool`] | **A/B causal live** apres neutralisation du confond de PAIRE (Drachnyen FIXE les PV du caster a 4729 -> `--hp-player 4729` rend le set-health neutre, paire native = 0 ; sans ca la paire natif=-35.4 vs offline=+2.5 ecrase le +-10). Runner 1373 : caster LOIN (0 ennemi adjacent a sa tuile COURANTE), tuile d'attaque a 1 ennemi -> natif NORMALE (54.139 vs 50.000+C) ; a 2 ennemis -> natif **DRACHNYEN** => le count porte sur la **tuile d'ATTAQUE**. Allie adjacent au lieu d'un ennemi -> natif reste sur la normale => **les allies ne comptent pas**. Encadrement : **5.547 < C < 10.716** (runners 1363 / 1335). |

| **DoomSiren** (1199) | @18112cd30 | `W(DefinitelyOverkill) * #(preds WillBeOverkill) + W(TargetHasAdjacentEnemy) * [count(GetAdjacentEnemies(tuile de la CIBLE, caster)) > 0]` | `DoomSiren_DefinitelyOverkill` = **40** ; `DoomSiren_TargetHasAdjacentEnemy` = **50** | emperKakophonist `Adamatar` [hero, `--list-pool`] | **A/B causal live** (probe #27-2, runner 339) : cible + tuile d'attaque FIGEES, seul un 2e ennemi passe loin -> adjacent a la cible ; natif bascule 69 -> **1199**, moteur idem ; contre-epreuve custom=0 -> moteur 69 dans les DEUX bras. Encadrement 100 % natif : **0.624 < C < 1.096** (cf. Validation). |

| **HeavyWarpFlamer** (1227) | `IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$CalculateCustomUtility` | `W * Count(battleQuery.<slot 0x7f>(target, caster, ignoreSteppables:false))` — slot d'interface 0x7f = index de vtable 0x83 (`interfaceOffset` = 4) = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IEntity from, TUnit unit, bool)`. Terme **LINEAIRE** dans le compte (DoomSiren teste `>0`, Drachnyen `>=2`), ancre sur la tuile de la CIBLE. | `HeavyWarpFlamer_LikesAdjacentEnemies` = **10** | thousSekhetar `Sekhetar Robot` [lineup, hors catalogue seed BC -> `catalog_inject.py --units thousSekhetar`] | **A/B causal live** (`probe_27_4_warpflamer_ab.py`, board MC1_67, 2 geometries, 4 bras). Argmax par CIBLE : 2 cibles a distance 2, ecart de paire natif **17.622786**, les 4 `pairUtility` natives BIT-IDENTIQUES dans TOUS les bras. n=0 -> natif T_haut ; **n=1 -> natif ENCORE T_haut** (un terme booleen aurait bascule) ; n=2 -> natif T_bas ; +1 ALLIE au lieu du 2e ennemi -> retour a T_haut. Moteur = natif dans les 4 bras ; custom force a 0 -> moteur reste sur T_haut a n=2 (**terme NECESSAIRE**). Encadrement sans fitting : **8.8114 < W < 17.6228**. |

| **SavageEchoes** (1230) | @1811586d0 | `GetRegenerateCondition(ability).Evaluate(entities) ? 0 : W` — la condition est `DSLFactory.HealthPctIsBelowOrEqual(caster@0x160, ConfigConst(0x4f = healthPct))` = `StatPercentageIsBelowOrEqualAbilityTrigger(caster, Health=5, thr)`, dont `ShouldTrigger` compare le **RATIO** `GetStat(u,stat,0)/GetStat(u,stat,2)` a `thr/100` (PAS un pourcentage arrondi). Terme CONSTANT sur (tuile, cible), variable avec les PV du CASTER. | `SavageEchoes_DislikesAboveHealthPct` = **-10** ; seuil `SavageEchoes.constants.healthPct` = **50** | bloodTerminator `Cezare` [lineup, HORS catalogue seed BC -> amene par `catalog_inject.py --units bloodTerminator`] | **A/B causal live** (`probe_27_3_savage_ab.py`, board MC1_67, caster (4,8) / cible (5,8) FIGES, `--hp-target 60000 --armor-target 4000`) : les DEUX `pairUtility` natifs sont BIT-IDENTIQUES entre les bras (6.3564547803252935 / 12.049598339945078) -> confond de prediction MESURE et NUL ; seul le PV% du caster varie. 100 % -> natif **69**, moteur **69** ; 49.64 % -> natif **1230**, moteur **1230**. Contre-epreuve custom=0 : moteur **1230 dans les DEUX bras** -> terme NECESSAIRE. |

Les sept HERITENT la prediction de degat du `DefaultActiveAbilityPlaybook` ; #27 ne porte QUE le
terme custom (la prediction est deja assuree par `prediction.py`, ecarts de degat = hors perimetre).

### Notes de fidelite du port HeavyWarpFlamer (tranche 4)

- **Le slot d'interface se resout par ANCRAGE, pas par recopie d'une fiche.** Les numeros de slot
  `IBattleQuery` ont BOUGE entre `gqfc5mff6c` et `rnca9r7q6c` : le terme d'adjacence de DoomSiren est
  passe de 0x7f a **0x80**. La conversion slot d'interface -> index de vtable de
  `IdunBattle.Core.Services.BattleQuery` est `+4`, etablie par DEUX ancres independantes :
  `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` appelle le slot
  d'interface **2** et l'index **6** de la vtable est `BattleQuery$$IsMeleeAttack` ; l'index **0x53**
  est `GetAdjacentTiles`, documente slot **0x4f**. Les indices 0x81..0x84 sont les QUATRE surcharges
  de `GetAdjacentEnemies` — recopier « 0x7f = GetAdjacentEnemies » d'une fiche ecrite sur l'ancien
  build aurait donne `GetAdjacentUnits` (index 0x7f), c'est-a-dire **amis compris**. Le bras de
  controle « 1 ennemi + 1 ALLIE » du probe existe pour ca : il echouerait sur ce port-la.
- **La surcharge exacte (index 0x83) accepte une UNITE comme `from`**, la ou DoomSiren (index 0x84)
  recoit une TUILE : `IterateAdjacentTiles` part de
  `IdunBattle.Entities.EntityExtensions$$IterateTiles(from)` puis prend les tuiles adjacentes de
  chacune (`onlyEmptyOrSteppable: false, onlyWalkableTiles: true, allowTemporary: true`). La cible
  ne se compte donc jamais elle-meme, et le mirror est le MEME `battle_query.count_adjacent` (meme
  porte d'elevation) que DoomSiren/Drachnyen.
- **La LINEARITE est ce qui distingue ce port d'une copie de DoomSiren**, et elle ne se voit pas dans
  un A/B a 0 vs 1 voisin. Le montage est calibre pour que l'ecart de paire natif tombe entre `W` et
  `2W` : c'est le passage de 1 a 2 voisins qui bascule le natif, et un terme booleen aurait bascule
  des 1. Le meme controle existe offline (`probe_custom_utility_27.py` : 0/W/2W/3W).
- **Ecart CONNU de prediction, hors #27** :
  `IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$MakeDamagePredictions` passe a
  `GenerateMultiHitAttackPredictions` un nombre de coups DYNAMIQUE —
  `HeavyWarpFlamerAbility$$GetNumTotalHits` = `Sum(Direct(nrOfHits=4), Min(GetPersistentData(...),
  Direct(maxNrOfHits=9) - Direct(nrOfHits=4)))` — la ou le chemin generique lit `nrOfHits` seul. Le
  compteur persistant vaut 0 tant que le stack n'est pas alimente (les deux coincident en debut de
  bataille) et il **ne depend pas de l'adjacence** : pas de confond avec le levier de l'A/B. La
  formule de degat propre est `VigilanceEternalAbility$$GetDamage` (corps PARTAGE, un seul
  proprietaire nomme) et le set de cibles est MONO-CIBLE — d'ou des `pairUtility` natives strictement
  invariantes d'un bras a l'autre, contrairement a DoomSiren (AoE).

### Notes de fidelite du port SavageEchoes (tranche 3)

- **Le seuil est un RATIO, pas un pourcentage arrondi.**
  `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` calcule
  `Fix64(GetStat(u, stat, 0)) / Fix64(GetStat(u, stat, 2)) <= Fix64.Round(thr/100*100)/100` — le seul
  arrondi porte sur le SEUIL (normalise a 2 decimales), jamais sur les PV. Le port n'emprunte donc PAS
  le `round(cur/max*100)` de `GetStat(Health, part=1)` qu'utilisent BloodChalice et LightOfSanguinius
  (un autre appel natif). **Mesure discriminante** : a `1675/3337 = 50.19 %` le natif rend W (condition
  FAUSSE) alors qu'un pourcentage arrondi aurait donne `round(50.19) = 50 <= 50` -> 0. A
  `1638/3300 = 49.64 %` il rend 0. Le port lit `cur` dans `ctx.hp_cur_by_id` (= `part 0`) et `max`
  dans `ctx.hpmax_by_id` (= `part 2`, overlay `combatSnapshot`), exactement les deux `GetStat` natifs.
- **Comment le montage a ete rendu DISCRIMINANT** (le regime se cherche, il ne se suppose pas) : a PV
  et armure par defaut, SavageEchoes ecrase l'attaque normale de +32 d'utilite de paire — un terme de
  -10 n'y change rien, et l'A/B ne peut pas contredire le port. Deux leviers, aucun scalaire fitte :
  `--hp-target 60000` (les utilites sont ~ degat/PVmax : l'ECART absolu se contracte) puis
  `--armor-target 4000` (le plancher percage fait diverger Eviscerate-50 % de Power-40 %, ce qui
  remonte 1230 juste au-dessus de 69). L'ecart offline tombe alors dans la fenetre `(1, 11)` ou le
  poids -10 de la BC decide — et le natif ET le moteur basculent ensemble.
- **Prediction de degat de 1230 : FERMEE (#216).** L'utilite de paire OFFLINE sous-estimait la native
  (7.8931 vs 12.0496 dans le montage a armure ; 15.7828 vs 24.1025 sans armure) parce que le chemin
  generique de `prediction/abilities.py` s'arretait a `MinMaxDamage`. L'artefact natif de la PREDICTION
  est `IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$MakeDamagePredictions`, qui passe en 6e arg de
  `GenerateMultiHitAttackPredictions` la formule PROPRE
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` =
  `Sum(MinMaxDamage, Multiply(Get(ConfigVar 8 = extraDmg), Count(CanAddUnit(AdjacentTiles(Owner@0x148)))))`
  — un bonus `extraDmg x (nb de tuiles adjacentes au CASTER ou une unite peut etre placee)`. Les trois
  AUTRES arguments du call-site sont generiques (profil `GetDamageProfile` -> `Nullable` NON vide, PAS le
  quirk `param_8 = null` de #164/#165 ; hits `ArmoriumCherubAbility$$GetHits` = `GetNumberConstant(0x2f)` ;
  cibles `DSLFactory$$Entity(target)` -> mono-cible). Porte par le handler `_savage_echoes_inputs`
  (`_MAKE_DMG_INPUT_OVERRIDES[1230]`), qui evalue l'arbre PARTAGE `SavageEchoesAbility.get_damage_formula`
  — le MEME que la face COMBAT (`runner/abilities/bloodangels.py`), un seul artefact natif, un seul port.
  VALIDE LIVE bit-exact contre `aiPlaybookPredict` sur 4 montages a compte de tuiles libres PILOTE
  (2 / 5 / 4 / 3 : natif 11572-17352 / 17556-26336 / 15560-23340 / 13564-20344, offline IDENTIQUE ;
  offline SANS le handler reste FIGE a 7576-11364). Paire d'utilite : natif 24.10252990666777 vs offline
  24.102529915669475 (ecart 9e-9, arrondi Fix64) contre 15.7828 avant le fix. `probe_216_savage_prediction.py`
  + garde `tests/engine/test_savage_echoes_prediction_live.py`.
- **Le compte est pris a la POSITION REELLE du caster, PAS a la tuile candidate du balayage IA** —
  RE : `Owner@0x148` est un selecteur d'ENTITE, dont le natif prend la MainTile reelle
  (`EntityExtensions$$GetTiles`) ; la tuile candidate vit dans `CasterTile@0x168`/`CasterTiles@0x170`, que
  cet arbre n'utilise pas (la struct de contexte de `GenerateMultiHitAttackPredictions` porte bien les deux :
  l'entite caster ET `casterPosition` + sa `MainTile`). CONFRONTE LIVE
  (`probe_216_savage_candidate_tile.py`) : caster REEL en (1,0) ou 3 tuiles adjacentes sont libres, tuile
  CANDIDATE (0,0) ou il n'y en a qu'1 -> `pairUtility(col=0,row=0)` natif = **28.25572481378913**, soit la
  valeur du compte **3** (identique au montage a free=3 du probe principal), et non celle du compte 1 ;
  offline 28.255724809173028. Le port lit donc `_pos(caster)` et JAMAIS `ctx.caster_pos` — c'est voulu.
  Consequence de gameplay : le bonus ne recompense pas la tuile ou l'IA va se poser, il photographie le
  degagement AVANT le deplacement.
- **Prerequis de harnais leve dans le meme commit** : `decisionView` nomme les abilities via
  `frida/hooks/data/ability-names.ts` (map GENEREE, figee dans le bundle injecte). 1230 n'y est pas
  -> l'ability sortait en placeholder `"id:1230"`, le predicteur offline cle sa recherche gameconfig
  sur ce NOM, `make_damage_predictions` rendait `[]` et l'ability n'etait **jamais candidate** —
  silencieusement. `engine/ai/context.py::_ability_name` replie sur `ActiveAbilityType(id).name`
  (source independante, meme nom que la cle gameconfig). Portee MESUREE
  (`probe_27_3_ability_names.py`) : **8 ids sur 331** sont absents de la map des hooks — 1215/1216/1217
  (npc-only), 1223/1224 (MoW), 1220 (aucune entree gameconfig), 1228 et 1230 (heros hors catalogue de
  la seed BC). Le repli est donc inerte partout ailleurs, et il rend confrontables exactement les
  porteurs amenes par `catalog_inject.py`.

### Notes de fidelite du port DoomSiren

- Le terme d'overkill mirroir la boucle native `foreach (p in MakeDamagePredictions(...))` en appelant
  **la meme methode** (`self.make_damage_predictions`, = vtable +0x358 cote natif). `WillBeOverkill` est
  extrait en `engine.utilities.damage.will_be_overkill` (meme code que la feuille `OverkillUnitUtility`,
  aucun changement de comportement pour elle).
- **Ecart CONNU** : `IdunBattle.AI.Playbook.Loki.DoomSirenPlaybook$$MakeDamagePredictions` ajoute au set
  de prediction jusqu'a `GetNumberConstant(0x78)` (= `nrOfUnits` = 2) ennemis adjacents a la cible, via
  le MEME slot `battleQuery.<0x7f>` que le terme custom. Le moteur ne modelise PAS cet AoE
  (`get_aoe_targets` non cable pour 1199) -> le compte d'overkills porte, offline, sur la CIBLE
  PRINCIPALE seulement. C'est un ecart de **prediction** (hors #27) : mesure live (runner 323,
  `--hp-target 900000`), la contribution AoE native vaut **+0.4727** sur `pairUtility(1199)` la ou le
  terme d'adjacence vaut 50 -> sans effet sur le CHOIX dans les cas exerces. Debloqueur nomme :
  cabler `DoomSirenAbility.get_aoe_targets = AdjacentEnemies(TargetTile())` cape a `nrOfUnits`, plus la
  formule de degat `BlightGrenadesAbility.GetDamageFormula`.
- Le terme d'adjacence est ancre sur la **tuile de la CIBLE** (pas la tuile d'attaque) : il ne
  participe donc pas a l'argmax par tuile mais bien a l'argmax par CIBLE et par ABILITY.

### Correctif STRUCTUREL induit par Drachnyen (`ai/action_generators.py::_best_attack`)

Le natif somme le custom **dans** `CalculateActionUtility @181406ee0` (vtable +0x348, avant le
terme Tile) — donc **avant** l'argmax par tuile de `EvaluateInternal @181408980`. Le port
l'ajoutait APRES le sweep de tuiles (`u_action = u_full + custom` une fois `pair_best` choisi) :
inoffensif pour un custom CONSTANT (ArmoriumCherub, NormalAttack, Herald, LightOfSanguinius) mais
un custom POSITION-dependant ne pouvait alors JAMAIS changer la tuile choisie. Le sweep compare
desormais `u_full + custom(tuile)`. Neutre par construction sur les customs constants (garde
d'agreement ci-dessous : 0 regression).

## INVENTAIRE EXHAUSTIF des overrides `CalculateCustomUtility` (27 corps / 27 classes, build `gqfc5mff6c`)

**27 corps DISTINCTS** = 1 base + 4 mutualises (attaque normale / heal) + **22 corps par-ability** ;
**27 classes** overridantes — une par corps. (La tranche 3 en annoncait 28, `AmuletOfTheVoidwyrmPlaybook`
etant cense partager le corps de `PlasmaGrenadePlaybook` : **faux positif de lecture hors-vtable,
retire par #218**.)
Ce tableau est le **livrable de decoupe** : il dit, pour chaque override, QUI le porte, si ce porteur
est CONFRONTABLE (gate HERO/MoW via `rl_duel build --list-pool` — un porteur `lineup` ABSENT du
catalogue de la seed BC reste confrontable via `catalog_inject.py`, cf. SavageEchoes / SUMMON via son
invocateur / NPC = non pertinent), et quel VERROU exact reste a lever. Une passe suivante ne doit PAS
re-derouler la recon : elle part d'ici.

### Etat par override

| # | Playbook (VA) | Ability (id) | Porteur(s) | Categorie | Verdict | Verrou / debloqueur |
|---|---|---|---|---|---|---|
| 1 | `ComparablePlaybook<T>` @181407840 | (base) | — | — | **couvert** (base.py) | — |
| 2 | `ALoki_NormalAttackPlaybook<T>` @1813726e0 | attaque normale | toutes | — | **couvert** (`Fix64(1)`) | — |
| 3 | `Idun.NormalAttackPlaybook<T>` @18149ee60 | attaque normale | toutes | — | **couvert** (idem #2) | — |
| 4 | `Loki_NormalBossAttackPlaybook` @1811497c0 | attaque normale boss | npc-boss | npc | **couvert** (idem #2) | — |
| 5 | `TwistedScience_HealPlaybook` @18116fb00 | TwistedScience heal | genesBiophagus | hero | **couvert** (`HealPlaybook.score`) | — |
| 6 | `ArmoriumCherubPlaybook` @18111c530 | ArmoriumCherub (1014) | adeptRetributor | hero (pool) | **PORTE** (#27-0) | — |
| 7 | `LightOfSanguiniusPlaybook` @181133d70 | LightOfSanguinius (1177) | bloodDante | hero (pool) | **PORTE** (#27-0) | — |
| 8 | `HeraldOfTheApocalypsePlaybook` @1811441b0 | HeraldOfTheApocalypse (1020) | blackHaarken | hero (pool) | **PORTE** (#27-1) | — |
| 9 | `DrachnyenPlaybook` @18112dc60 | Drachnyen (1029) | blackAbaddon | hero (pool) | **PORTE** (#27-1) | — |
| 10 | `DoomSirenPlaybook` @18112cd30 | DoomSiren (1199) | emperKakophonist | hero (pool) | **PORTE** (#27-2) | — |
| 11 | `Repair_GalvanicFieldPlaybook` @181155520 | Repair_GalvanicField (1119) | admecManipulus (granted par le passif GalvanicField) | hero | **DEJA PORTE** hors loki_custom (`_repair_galvanic_candidates`, #85) | — (verdict tranche 1 « dead-code » CORRIGE) |
| 12 | `MortisRoundPlaybook` @18114d190 | MortisRound (1004) | ultraEliminatorSgt | hero (pool) | **terme MESURE NUL** (< 0.012), non porte | evaluateur du composite `UtilityAttackCase.Base` (slot 5 du service #0x36) ; re-mesurer sur board a elevation |
| 13 | `SorcerousFacadePlaybook` @18115b9d0 | SorcerousFacade (1100) | thousTzaangor | hero (pool) | **RE RESOLU, NON PORTE — non-conformite MESUREE puis RETIREE (#27-3)** | le moteur route 1100 comme ATTAQUE d'ENNEMI (`damageProfile` present) alors que le natif cible un **allie Psyker** (echange de positions). Debloqueur : route de ciblage ALLIE pour 1100 (`ability_targets` + generateur dedie facon `_bespoke_candidates`) |
| ~~13bis~~ | ~~`AmuletOfTheVoidwyrmPlaybook`~~ | AmuletOfTheVoidwyrm (1464, `TriggeredAbilityType`) | — | passif/triggered | **RETIRE — FAUX POSITIF (#218)** | n'override PAS : sa base `TriggeredAbilityPlaybook`1` descend directement de `System.Object`, hors de la branche `ComparablePlaybook`1` qui declare le virtuel. Le « slot +0x548 » etait le slot +0x338 de `PlasmaGrenadePlaybook`, dont la classe suit a +0x210 en memoire (les 39 slots coincident). Ce qui reste OUVERT sur 1464 est son playbook de **MOUVEMENT** (`AmuletOfTheVoidwyrmPlaybook$$CalculateMovementUtilityInStepsInternal` + face NonOwner `AmuletOfTheVoidwyrmNonOwnerPlaybook$$GetAdjacencyUtility`), inventorie rang B de `case-193` — un AUTRE item. Detail : `docs/rl/case-218-amulet-voidwyrm-custom-utility.md` |
| 14 | `ProperKilly_NormalAttackPlaybook` @1811532a0 | ProperKilly (aucun id) | **aucun** | — | **dead-code** | — (non pertinent) |
| 15 | `PlagueburstMortarPlaybook` @181134e00 | PlagueburstMortar (1169) | deathCrawler | **MoW (pool MoW)** | **invalidable-residu** (face DECISION) | MoW absentes de `decisionView.units` / `attackPlans` (pas de PositionComponent) -> jamais feedees a `_best_attack` — **confirme live runner 336** : `observeBattle.mows` = 2 machines, `aiDryRunAllUnits` ne propose rien pour elles. Debloqueur : modeliser les MoW comme unites de decision (position derivee de `MachineComponent.Position`). NB : la face **COMBAT** de 1169 est portee et validee par **#90** — c'est bien le seul volet DECISION qui manque |
| 16 | `DaemonicOrdnancePlaybook` @1811286c0 | DaemonicOrdnance (1148) | blackForgefiend | MoW (pool MoW) | **invalidable-residu** (face DECISION) | idem #15 (face COMBAT portee par #90) + evaluateur DSL `TilesOnSameElevation(TilesInTriangleShape(...))` pour le terme custom |
| 17 | `StikkbombPlaybook` @18115f7c0 | Stikkbomb (1051) **et** MalleusRocketLauncher (1142) — playbook PARTAGE | orksOrkBoys [summon de `Waaagh`/orksWarboss, **en pool**] ; astraOrdnanceBattery [MoW] | summon + MoW | **residu** | `MalleusRocketLauncherAbility.GetAdditionalTargets` (DSL) + `TargetsSelector.SelectUniqueUnits(3)` + `GenerateMultiHitAttackPredictions` sur les AMIS touches (penalite tir ami, resultat NEGE) |
| 18 | `PlasmaGrenadePlaybook` @181151040 | PlasmaGrenade (1098) | eldarSmnGuardian | summon **sans invocateur** (aucune ability du gameconfig ne le summon) | **residu / non confrontable** | invocateur inexistant -> non amenable en bataille ; + `GenerateMultiHitAttackPredictions` |
| 19 | `ChronometronPlaybook` @181125ab0 | Chronometron (1226) | necroChronomancer | hero **hors pool** | **residu** | (a) porteur non possede au rank courant ; (b) `damageProfile` absent -> n'atteint pas `_best_attack` ; (c) selecteur DSL `ChronometronAbility.GetAffectedEnemies` |
| 20 | `DevoutPushPlaybook` @18112c7b0 | DevoutPush (1053) | templInitiate | summon **d'environnement** (`EnvFactionSummons:BlackTemplars`) | **residu** | formule TRIVIALE (`ALoki_NormalAttack.custom * 2` = **2** constant) mais (a) porteur env-only, (b) `damageProfile` absent -> action « push » non modelisee |
| 21 | `ForwardObserversPlaybook` @18113bb70 | ForwardObservers (1185) | tauSmnStealthSuit | summon de `ATemptingTrap` | **residu** | `damageProfile` absent -> ability non-degat ciblant un ENNEMI, aucune route offline. Formule : `(aucun ennemi n'a de markerlight ? W(=200) : 0) + RemainingPercentage(cible) * W(=40)` |
| 22 | `HealingBalms_HealPlaybook` @181142dc0 | HealingBalms_Heal (1212) | spaceWolfPriest (sous-ability du PASSIF HealingBalms) | hero **hors pool** | **residu** | pas d'entree gameconfig active ; voie « heal declenche par un passif » non modelisee |
| 23 | `SavageEchoesPlaybook` @1811586d0 | SavageEchoes (1230) | bloodTerminator | hero hors catalogue seed BC -> **confrontable via `catalog_inject.py`** | **PORTE** (#27-3) | — (verdicts « porteur hors pool » + « evaluateur de CONDITION manquant » des tranches 1-2 **CORRIGES** : le catalogue se complete, et la condition est un simple ratio de PV lu au decompile) |
| 24 | `MortarionsPlagueWindPlaybook` @18114ca30 | MortarionsPlagueWind (1093) | deathBossMortarion | **npc** | **non pertinent** | — |
| 25 | `InstrumentsOfVengeancePlaybook` @1811460d0 | InstrumentsOfVengeance (1215) | darkaBossLion | **npc** | **non pertinent** | — |
| 26 | `MartialExemplarPlaybook` @18114ae20 | MartialExemplar (1216) | darkaBossLion | **npc** | **non pertinent** | — |
| 27 | `TheLionsWrathPlaybook` @18116aba0 | TheLionsWrath (1217) | darkaBossLion | **npc** | **non pertinent** | — |

### Ventilation (les 22 overrides par-ability, apres correction #218)

- **PORTES / couverts : 7** — 1014, 1177, 1020, 1029, 1199, 1119, **1230**.
- **Traites sans port (verdict ferme) : 2** — MortisRound (terme mesure NUL), ProperKilly (dead-code).
- **Non pertinents (porteurs NPC uniquement) : 4** — 1093, 1215, 1216, 1217.
- **Residus a debloquer : 9** — 1100, 1169, 1148, 1051/1142, 1098, 1226, 1053, 1185, 1212.
  (La tranche 3 en comptait 10 ; **AmuletOfTheVoidwyrm est retire — faux positif, cf. #218**.)

**Triage de dispatch re-derive du code (tranche 3, `probe_27_residual_triage.py`)** — la porte vers
`_best_attack` est `state_bridge._is_attack_ability` (= `constants.damageProfile` present ET non-NC) :

| ability | `damageProfile` | atteint `_best_attack` ? | porteur |
|---|---|---|---|
| 1004 MortisRound | oui | oui | ultraEliminatorSgt [pool] |
| 1169 / 1148 / 1142 | oui | oui | MoW (deathCrawler / blackForgefiend / astraOrdnanceBattery) |
| 1051 Stikkbomb | oui | oui | orksOrkBoys [summon d'orksWarboss, en pool] |
| 1098 PlasmaGrenade | oui | oui | eldarSmnGuardian [summon SANS invocateur] |
| 1230 SavageEchoes | oui | oui | bloodTerminator [catalog_inject] |
| **1226 Chronometron** | **NON** | **non** | necroChronomancer [catalog_inject] |
| **1053 DevoutPush** | **NON** | **non** | templInitiate [summon d'environnement] |
| **1185 ForwardObservers** | **NON** | **non** | tauSmnStealthSuit [summon d'`ATemptingTrap`] |
| **1212 HealingBalms_Heal** | pas d'entree gameconfig | **non** | spaceWolfPriest (sous-ability d'un PASSIF) |

Consequence directe : le verrou « porteur hors `--list-pool` » de la tranche 2 **n'existe plus**
(`catalog_inject.py` complete `BC.Units` ET `BC.Abilities`) ; ce qui reste bloquant pour 1226 / 1053 /
1185 / 1212 est la ROUTE (aucun `damageProfile` -> jamais candidate offline).

### Les VERROUS qui tiennent les 10 residus

1. **MoW non modelisees comme unites de DECISION** (1169, 1148, et la face MoW de 1142) — le blocage
   le plus rentable : 3 overrides d'un coup, et `PlagueburstMortar` est deja un patron PORTE
   (`count(GetAdjacentEnemies) * W`, identique a Drachnyen). Mesure live (runner 336) : les MoW
   DEPLOIENT bien (`observeBattle.mows` = 2) mais n'apparaissent ni dans `decisionView.units`
   ni dans `attackPlans`, et `aiDryRunAllUnits` ne leur propose rien. **La face COMBAT de 1169/1148
   est deja portee et validee live par #90** : c'est donc STRICTEMENT le volet DECISION qui manque
   (les deux faces se valident separement, cf. le protocole `tacticus-re-port`).
2. **Routes d'ability non-attaque** (`damageProfile` absent, ou cible ALLIEE) — 1100, 1226, 1053, 1185,
   1212. Le gate `state_bridge._is_attack_ability` est la seule porte vers `_best_attack` ; toute
   ability qui ne produit pas de degat (ou qui cible un allie) n'a aucune route offline.
3. ~~**Porteur hors `--list-pool` au rank courant**~~ — **VERROU SUPPRIME (tranche 3)**. Le porteur
   `lineup` absent du catalogue de la seed BC se rajoute par `catalog_inject.py --units <id>` (#92,
   `BC.Units` ET `BC.Abilities`), et le runner le deploie normalement — fait pour bloodTerminator
   (1230). Restent 1226 et 1212, bloques par le verrou 2 (route), plus par le catalogue.
4. **`GenerateMultiHitAttackPredictions` sur un sous-set de cibles** — 1051/1142, 1098.
   (AmuletOfTheVoidwyrm y figurait au titre du « corps partage avec 1098 » — **retire par #218**,
   ce partage n'existait pas.)
5. **Evaluateurs manquants** : composite `UtilityAttackCase.Base` (1004), DSL de forme
   `TilesInTriangleShape` (1148), DSL selecteur d'ability (1226).

### `SorcerousFacade` (1100) — RE COMPLETE (verrou identifie, port refuse)

La tranche 1 le classait « bloque par le sous-systeme utilite de deplacement ». **Ce verrou n'existe
pas** : le decompile a ete relu integralement le 2026-07-25.

```
u1 = services[7].EvaluateMovement(new UtilityMovementCase(unit, GetMainTile(target), null, null, null));
u2 = services[7].EvaluateMovement(new UtilityMovementCase(unit, position,            null, null, null));
return u1 - u2;
```

Le `UtilityMovementCase` est construit avec **`ClosestEnemy = null`** (3e argument du ctor
`IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor`, champ @0x20 — meme forme que
`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility`). Or
`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
rend `Fix64(0)` des que `case.ClosestEnemy == null` (3e garde, AVANT tout `GetMinDistanceToEnemy`).
=> la feuille MinDistanceToClosestEnemy(16) est **INERTE** sur ce chemin et le composite de mouvement
se reduit a sa feuille **Tile(7)**. Le mirror exact est donc `base.tile_utility(target_tile) -
base.tile_utility(caster_tile)` — deja disponible dans le moteur, aucun sous-systeme a porter.

**Pourquoi le port est REFUSE** : `SorcerousFacadeAbility` cible un **allie Psyker**
(i2 : « Target a friendly Psyker... then switches positions with the targeted Psyker »), donc le
`target` recu par `CalculateCustomUtility` est un ALLIE. Le moteur, lui, route 1100 vers
`_best_attack` avec des cibles ENNEMIES (`constants.damageProfile = Psychic` present). Le port est
donc conditionne au debloqueur #2 (route de ciblage ALLIE), pas a un sous-systeme d'utilite.

**Ce refus a ete CONTREDIT PAR LE CODE puis RETABLI (tranche 3).** Le commit `8f4295c` (#27-2)
annoncait le refus dans son message ET dans cette fiche, mais **enregistrait quand meme**
`SorcerousFacadePlaybook` dans `loki_custom._register_all()`. Deux mesures live l'ont tranche
(runner arene MC1_67, `thousTzaangor` + `thousSorcerer` [Psyker] + 3 ennemis rapproches) :

1. **Cote natif** — `abilityTargets(unit=thousTzaangor)` rend pour 1100 exactement **UNE** cible
   legale : `targetId` = le **thousSorcerer ALLIE** (`targets` ET `fromHere`), jamais un ennemi. Le
   natif n'evalue donc JAMAIS ce terme sur une cible ennemie. (Le gate suplementaire « il faut un
   ennemi a portee » est visible aussi : sans ennemi proche, 1100 rend 0 cible.)
2. **Cote moteur** — `state_bridge._plans_for_unit` produit bien trois paires `(1100, ennemi)` et les
   dispatche a `SorcerousFacadePlaybook`, dont le terme y valait **-10.0 / -25.0 / +20.0** selon
   l'ennemi (`probe_27_3_facade_route.py`) : NON NUL et NON CONSTANT, un biais de +/-45 sur une
   action que le natif refuse.

`SorcerousFacadePlaybook` est donc **retiree du registre** (le custom de 1100 retombe sur la base
`Fix64(0)`), et `probe_custom_utility_27.py` porte desormais un **cliquet** qui echoue si l'id 1100
y revient. Le RE ci-dessus reste valable et sera re-branche le jour ou la route de ciblage ALLIE
existera.

## Validation

- **Garde d'agreement CIBLEE, zero regression** (`engine_agreement_stages.py --build`) :
  - seed **31337** : prediction 10/10, utilite 10/10, ability **13/13**, move **18/18** (100%) ;
  - seeds **777 + 12345**, re-joues en tranche 3 : prediction **17/21**, utilite 21/21, ability
    **26/26**, move **31/32**. Ces chiffres sont **INFERIEURS a ceux de la tranche 2** (21/21 et
    32/32) — la derive est **PRE-EXISTANTE sur `origin/master`**, pas causee par #27-3 : la MEME passe
    jouee avec les modifications `engine/` mises de cote (`git stash`) rend **exactement les memes
    17/21 - 21/21 - 26/26 - 31/32**. Le delta de #27-3 sur ces seeds est donc STRICTEMENT NUL.
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
- **DoomSiren (1199)** — A/B causal **entierement mesure cote natif** (`probe_custom_utility_27_live.py`
  cas (C), runners 323/339 ; board MC1_67, `--hp-target 900000`). Cible (tauCrisis) et tuile d'attaque
  natives FIGEES a `(1,1)` dans les deux bras -> **le terme Tile s'annule exactement**. Seule variable :
  un 2e ennemi (blackTerminator) passe de « loin » a « adjacent a la cible ».

  | mesure NATIVE @tuile (1,1) | bras A (cible isolee) | bras B (ennemi adjacent a la cible) |
  |---|---|---|
  | `pairUtility(69, cible)` | 0.5689987447112799 | **0.5689987447112799** (bit-identique) |
  | `pairUtility(1199, cible)` | 0.4726656246930361 | 0.9453312493860722 (**+0.4726656** = AoE native) |
  | choix natif (`aiDryRunAllUnits`) | **69** | **1199** |
  | choix moteur | **69** | **1199** |
  | choix moteur, custom force a 0 | 69 | **69** (= divergence -> le terme est NECESSAIRE) |

  Encadrement (aucun scalaire fitte ; `u_action = pair + tile + custom`, tile identique donc annule ;
  la branche 69 est un CONTROLE bit-identique entre les bras, custom(69) = 1 constante deja etablie) :
  - bras A, le natif garde 69 : `1 + 0.56900 > 0.47267 + C_A` => **C_A < 1.09633** ;
  - bras B, le natif bascule sur 1199 : `0.94533 + C_B > 1 + 0.56900` => **C_B > 0.62367**.
  L'AoE native (+0.47267) NE SUFFIT PAS a expliquer la bascule (il faut > 1.09633 - 0.47267 = 0.62367
  de terme supplementaire) -> le confond de prediction est **mesure et ecarte**, pas suppose.
  Valeur portee : `W(DoomSiren_TargetHasAdjacentEnemy)` = 50 (resolu de la BC a l'execution).
- **Generalisation DoomSiren (walk complet)** : board **C4_09**, roster CONTENANT le porteur
  (emperKakophonist, thousTzaangor, ultraCalgar, tauCrisis, orksWarboss vs 5 ennemis), 20 pas natifs.
  Le natif joue DoomSiren spontanement (step 10, `ab=1199 tgt=86`) et le moteur MATCH. A/B avant/apres
  le port **STRICTEMENT identique** (positioning 16/17 exact, 17/17 <=1hex ; ability 11/14) : aucune
  regression, et aucun gain sur ce walk (le cast de step 10 etait deja l'argmax sans le custom).
- **SavageEchoes (1230)** — A/B causal live (`probe_27_3_savage_ab.py`, board MC1_67,
  `--hp-target 60000 --armor-target 4000 --hp-player 3300`, caster (4,8) / cible tauCrisis (5,8)
  FIGES). Seule variable : le PV% du CASTER (une frappe de tauCrisis, `TerminatorArmour` incluse).

  | mesure @tuile (4,8) | bras A (3300/3300 = 100 %) | bras B (1638/3300 = 49.64 %) |
  |---|---|---|
  | `pairUtility(69, cible)` natif | 6.3564547803252935 | **6.3564547803252935** (bit-identique) |
  | `pairUtility(1230, cible)` natif | 12.049598339945078 | **12.049598339945078** (bit-identique) |
  | choix natif (`aiDryRunAllUnits`) | **69** | **1230** |
  | choix moteur | **69** | **1230** |
  | choix moteur, custom force a 0 | **1230** (= divergence -> terme NECESSAIRE) | 1230 |

  Les DEUX paires natives sont bit-identiques entre les bras : le heal `ForRegenerate` n'entre PAS
  dans la prediction du playbook -> **le confond est mesure et NUL** (contrairement a DoomSiren, ou il
  fallait le chiffrer). Encadrement sans fitting (`u_action = pair + tile + custom`, meme tuile donc
  meme terme Tile ; custom(69) = +1 deja etabli) : bras A `6.35645 + 1 > 12.04960 + C_A` =>
  **C_A < -4.69315** ; bras B `12.04960 + C_B > 6.35645 + 1` => **C_B > -4.69315**. Le port rend
  -10 et 0. Sur le montage SANS armure (`--hp-target 60000` seul) les paires natives valent
  15.892803575843573 / 24.10252990666777 et l'encadrement devient **C_A < -7.2097 < C_B**.

  **Seuil borne a 4 points** (meme montage, `--hp-player` varie) : 100 % / 51.12 % / 50.68 % /
  50.19 % -> natif **69** ; 49.64 % -> natif **1230**. Le point 50.19 % EXCLUT un pourcentage arrondi
  (`round(50.19) = 50 <= 50` aurait bascule) : le natif compare bien le RATIO a `healthPct/100`.
- **HeavyWarpFlamer (1227)** — A/B causal live `probe_27_4_warpflamer_ab.py`, board **MC1_67**,
  stats NATURELLES (ni `--hp-target` ni `--armor-target`), porteur `thousSekhetar` amene par
  `catalog_inject.py`. L'observable est l'**argmax par CIBLE** (le terme est per-target) : deux
  cibles legales a distance 2 du caster et a distance 4 l'une de l'autre, les appats ne changent
  l'adjacence d'aucune autre entite.

  | mesure NATIVE | n=0 | n=1 | n=2 | 1 ennemi + 1 ALLIE |
  |---|---|---|---|---|
  | `pairUtility(69, T_bas)` | 29.32473444379866 | idem | idem | idem |
  | `pairUtility(1227, T_bas)` | 35.79286797903478 | idem | idem | idem |
  | `pairUtility(69, T_haut)` | 46.1860187118873 | idem | idem | idem |
  | `pairUtility(1227, T_haut)` | 53.41565425042063 | idem | idem | idem |
  | choix natif (`aiDryRunAllUnits`) | **T_haut** | **T_haut** | **T_bas** | **T_haut** |
  | choix moteur | T_haut | T_haut | T_bas | T_haut |
  | choix moteur, custom force a 0 | T_haut | T_haut | **T_haut** (= divergence -> terme NECESSAIRE) | T_haut |

  Les QUATRE paires natives sont bit-identiques dans les QUATRE bras : le confond de prediction est
  MESURE et NUL (prediction mono-cible). Aucun `MoveUnitMessage` dans les propositions -> meme tuile
  d'attaque, le terme Tile s'annule exactement. Encadrement sans fitting (forme `W*n`, ecart de paire
  17.622786) : `W < 17.6228` (n=1 ne bascule pas) et `2W > 17.6228` (n=2 bascule) ->
  **8.8114 < W < 17.6228** ; le port rend 10. Le bras ALLIE prouve que la requete scope aux ENNEMIS
  (et non `GetAdjacentUnits`, l'index de vtable voisin).
- **Generalisation HeavyWarpFlamer** : le meme protocole rejoue sur une **seconde geometrie a colonne
  IMPAIRE** (caster (3,5), cibles (3,3)/(3,7), appats (3,2)/(4,2) — l'autre table de voisinage hex
  offset) et un **autre seed (31337)** rend EXACTEMENT le meme resultat : 4/4 bras, moteur = natif,
  linearite prouvee, allies ignores, meme encadrement. Le probe VERIFIE desormais le placement et
  REFUSE de mesurer si un `act move` a ete rejete (mesure du 2026-07-30 sur `C2_02` : trois bras
  degeneres en un seul, « 4/4 MATCH » sans aucune valeur).
- **Non-regression du refresh `BC.Utilities`** (`engine_agreement_stages.py --build`), mesuree
  AVANT/APRES le changement, meme session, memes seeds :
  seed **31337** — prediction 0/9, utilite 0/9, ability **12/12**, move **17/17** dans les DEUX etats ;
  seed **777** — prediction 1/10, utilite 1/10, ability **14/14**, move **14/15** dans les DEUX etats.
  **Delta strictement NUL.** (Les etages prediction/utilite s'effondrent sur ce build : c'est
  PRE-EXISTANT sur `origin/master` — le run « avant », changements `git stash`-es, rend les memes
  chiffres.)
- **Garde de forme OFFLINE** : `probe_custom_utility_27.py` (dispatch 1014/1177/1020/1029/1199/**1227**/1230,
  valeurs des 7 formules, POSITION-dependance de Drachnyen, ancrage sur la CIBLE de DoomSiren et de
  HeavyWarpFlamer, **linearite 0/W/2W/3W de HeavyWarpFlamer**, mirror `will_be_overkill`, les 4 bornes
  de ratio mesurees de SavageEchoes, et le **cliquet 1100 absent du registre**). Il ECHOUE aussi si
  `HeavyWarpFlamer_LikesAdjacentEnemies` vaut 0 — c'est-a-dire si la table `Utilities` n'a pas ete
  re-synthetisee depuis le gameconfig courant.
- **Inventaire** : `probe_27_custom_utility_inventory.py` (balayage de vtable, 2 sources croisees),
  `probe_27_slot_offsets.py` (les 7 playbooks hors 0x338), `probe_27_vtable_dump.py` (controle de
  bornes), `probe_27_residual_triage.py` (route de dispatch + porteurs), `probe_27_3_ability_names.py`
  (les 8 ids absents de la map des hooks).

### Non couvert (explicite)

- **Les 2 overrides NEUFS non portes du build `rnca9r7q6c`** : `MassDriverAccelerator` (1222,
  votanChampion — verrou : evaluateur du selecteur DSL `MassDriverAcceleratorAbility$$GetBuffTargets`)
  et `ResurrectionOrb` (1009, necroOverlord — verrou 2 : pas de `damageProfile`, l'ability n'atteint
  jamais `_best_attack`).
- **Le refresh `BC.Utilities` DEMASQUE 2 termes TRIGGERED que le moteur ne porte pas.** Trois valeurs
  passent de 0 a non-nul : `KustomForceFieldReworked_LikesAdjacentFriends` 0->10 et
  `KustomForceFieldReworked_FriendsLikeToBeAdjacent` 0->10 (porteur spawnable : `orksBigMek` [lineup],
  plus 4 npc) et `Lakrimae_LikesNonMechanicalEnemies` 0->5 (porteurs **npc uniquement**, Typhus). Avant
  le refresh, natif et moteur valaient 0 tous les deux — d'accord entre eux, faux tous les deux. Apres,
  le natif applique le poids et le moteur, qui ne porte pas ces termes de playbook TRIGGERED, non : un
  desaccord peut apparaitre sur une bataille contenant `orksBigMek`. **Mesure** : delta NUL sur les
  seeds 777 et 31337 (rosters sans ce porteur) ; le gap existait deja, il etait MASQUE par une capture
  perimee. Inscrit au backlog.
- **`ActiveAbilityType` (engine) n'est PAS re-genere** : seul `HeavyWarpFlamer = 1227` est ajoute. Le
  build `rnca9r7q6c` ajoute 4 membres (1222, 1227, 1231 TitanhammerSquad, 1232 EmpyricAmbush) et en
  RETIRE 75 (les ids Idun historiques 1..85), encore cites par le port : la re-generation complete est
  une action de migration a part entiere.
- Les **10 residus** de l'inventaire ci-dessus (chacun avec son verrou nomme) + les 4 non pertinents (npc).
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
  (Herald C > 34.22 ; Drachnyen 5.547 < C < 10.716 ; DoomSiren 0.624 < C < 1.096 sur la CONFIGURATION
  exercee) : les valeurs portees viennent du decompile (`GetUtilityValue(<cle>)`) et sont resolues a
  l'execution depuis la BC, jamais codees en dur.
- **DoomSiren, terme d'OVERKILL** (`W(DoomSiren_DefinitelyOverkill)` * #preds) : porte et teste
  offline (`will_be_overkill`), mais **jamais exerce live** — l'A/B utilise `--hp-target 900000`
  precisement pour eteindre kill/overkill et isoler le terme d'adjacence. Il reste de plus soumis a
  l'ecart d'AoE documente (le compte offline porte sur la cible principale seulement).
- **SorcerousFacade (1100)** : formule RESOLUE mais NON portee (cible allie vs route ennemie du
  moteur) — cf. l'inventaire. Depuis la tranche 3, plus AUCUN code n'est actif pour 1100 : le custom
  y retombe sur la base `Fix64(0)`. L'ACTION FANTOME, elle, est **FERMEE (#217)** : le masque du
  `SorcerousFacadeAbility$$.ctor` (`0x402` = `TargetIsFriendly | TargetMatchesDynamicRule`) est
  desormais RE-lu et VETO la route ennemie de `_is_attack_ability` — mesure avant/apres dans le meme
  etat de bataille : `plans[1100]` passe de `[(1100,79),(1100,81)]` a `[]`. Detail, balayage de la
  classe et residus : `docs/rl/case-217-phantom-action-routing.md`. A noter que la couture LIVE etait
  deja propre (`attackPlans` porte ces evals avec `rankCount = 0`, que `_best_attack` saute) : les
  termes ±45 de la tranche 3 venaient d'un probe qui evaluait le custom sans filtrer `rankCount`.
- **SavageEchoes, face COMBAT** : portee depuis (case-220 §blood-angels, `ABILITY_CLASSES[1230]`) — #27
  ne couvrait que la face DECISION. La **prediction de degat** de 1230, elle, est FERMEE par #216
  (cf. « Notes de fidelite ») : ce n'est plus un non-couvert.
- ~~**AmuletOfTheVoidwyrm** : override DECOUVERT en tranche 3~~ — **FERME par #218 : il n'y a jamais
  eu d'override.** Faux positif de lecture hors-vtable ; le porteur (relique
  `R_Booster_Crit_AmuletOfTheVoidwyrm`, `allowedUnits` genesBiophagus/genesPrimus/genesKelermorph)
  est neanmoins ventile dans `case-218` §5, avec la localisation du seuil de niveau des reliques
  (`globalValues.tertiaryAbilityUnlockProgressionRequirement` = 16, lu par
  `IdunMetaLogic.UserProgress.UnitProgression$$ProgressionLevelNeededToUnlockTertiaryAbility` — couche
  META, jamais par `IdunBattle.*`).
- **MoW (1169/1148/1142)** : blocage confirme live (runner 336) — les machines deploient mais
  n'existent pas comme unites de decision cote moteur.

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
`not is_noncomp` (script `_dispatch`), puis le TYPE de porteur (MoW = pas d'unite de decision cote
moteur ; porteur hors CATALOGUE = `catalog_inject.py`, PAS « non confrontable ») et le TYPE de
sous-selecteur du corps (constante / iteration directe d'unites / adjacence deja portee
`count_adjacent` / condition de STAT deja lisible du ctx / **arbre DSL** / **BattleQuery a token** /
**multi-hit** / **utilite de deplacement**). Ce triage EN AMONT evite les ports
speculatifs : sur les 23 overrides par-ability, **7 sont portes/couverts, 2 fermes sans port, 4 non
pertinents (npc), 10 residus** tenus par **4 verrous** nommes (MoW non modelisees, routes d'ability
non-attaque, multi-hit, evaluateurs manquants) — cf. l'inventaire (roadmap de reprise).

**L'inventaire d'un override se re-derive au SLOT DE VTABLE — mais un balayage NON BORNE ment.**
Les 27 symboles ghidra decrivent 27 CORPS, et la table ne peut pas dire combien de CLASSES les
utilisent (dedup IL2CPP + indexation par adresse) : le balayage de vtable reste la bonne
contre-mesure. Il doit en revanche etre **borne**, et la premiere redaction de ce paragraphe ne
l'etait pas — elle a produit un faux positif (`AmuletOfTheVoidwyrmPlaybook` cru fondu dans
`PlasmaGrenadePlaybook`, et 7 « offsets de slot alternatifs » 0x548/0x5a8/0x668/0x7b8 qui n'ont
jamais existe). Ce qui tranche vraiment, dans cet ordre (**#218**) :

(a) **La branche d'heritage d'abord** (`data/symbols/<build>/frida/classes.tsv`, indexee par NOM) :
une classe hors de la branche qui DECLARE le virtuel ne peut pas l'overrider, et aucune mesure de
vtable ne peut le contredire. `CalculateCustomUtility` appartient a `ComparablePlaybook`1` ;
`TriggeredAbilityPlaybook`1` descend de `System.Object` — disjoint.
(b) **Borner le balayage** a la vtable PROPRE (premier bloc contigu de slots nommes depuis
`+0x138`). `resolveVtableSlot` lit `klass+off` en aveugle, sans `vtable_count` : c'est a l'appelant
de s'arreter.
(c) **Ne pas prendre « vtable nulle » pour « pas d'override »** — une classe jamais instanciee a des
slots nuls ; c'est un INDETERMINE (statut `vtable-uninit`), a lever par (a) ou par une classe SŒUR
initialisee de la meme base.
(d) **« Regarder ou les noms deviennent du bruit » ne borne rien** : un debordement tombe sur la
vtable de la classe SUIVANTE, parfaitement formee et nommee (`Equals` en tete). L'arithmetique, elle,
tranche : `klass(voisine) - klass(sujet)` donne la taille reelle du sujet.

**Un « porteur hors `--list-pool` » n'est pas un verrou.** Trois abilities dormaient derriere ce
motif ; `catalog_inject.py --units <id>` complete `BC.Units` ET `BC.Abilities` et le runner deploie
l'unite normalement (fait pour bloodTerminator/SavageEchoes). Ne classer « non confrontable » qu'un
porteur NPC, ou un summon sans invocateur.

**Le gate de dispatch peut mentir sur la NATURE de la cible.** `damageProfile` present ne veut pas dire
« ability qui cible un ennemi » : `SorcerousFacade` (1100) porte un `damageProfile=Psychic` mais cible un
**allie** Psyker. Le moteur la route pourtant vers `_best_attack` avec des cibles ENNEMIES. Porter un
terme custom sur un dispatch dont la CIBLE est fausse est pire que ne rien porter (regression garantie,
sans erreur visible). Verifier le kit i2 + le selecteur natif (`<Ability>Ability.GetTarget`) AVANT de
brancher la formule, meme quand celle-ci est parfaitement resolue.

**Un token `BattleQuery` non resolu n'est pas forcement un blocage** : Herald (0x44) et Drachnyen (0x7d)
etaient classes « token non resolu » et se sont averes portables — la SEMANTIQUE du token se lit sur le
comportement (frontiere de portee mesuree pour 0x44, seuil d'adjacence + exclusion des allies pour 0x7d)
plutot que sur la table d'interface. Re-tester les residus « token » par A/B avant de les laisser dormir.

**Un terme d'action POSITION-dependant impose de verifier OU le port ajoute le custom.** Le natif le somme
dans `CalculateActionUtility` (donc avant l'argmax de tuile) ; tout port qui l'ajoute apres le sweep rend
le terme inerte sans jamais lever d'erreur. Signature du bug : le terme « existe » offline mais ne change
jamais la tuile choisie.

**Un `UtilityMovementCase` construit hors du `MovementActionGenerator` a ses champs a NULL — et chaque
feuille se DESARME toute seule dessus.** `MinDistanceToClosestEnemyUtility` rend `Fix64(0)` des que
`case.ClosestEnemy == null` ; ce champ n'est renseigne QUE par le generateur de mouvement
(`FindClosestEnemy`). Consequence : tout appel de `services[7].EvaluateMovement(new UtilityMovementCase(
unit, tile, null, ...))` — c.-a-d. `Playbook<T>.GetMovementUtility` et `SorcerousFacadePlaybook` — se
REDUIT a la feuille Tile(7). Un « sous-systeme utilite de deplacement a porter » peut donc n'etre, au
final, qu'un `tile_utility` deja disponible : LIRE LES GARDES DE LA FEUILLE avant de declarer le verrou.

**Choisir le bras d'A/B pour que le confond soit MESURABLE, pas seulement petit.** Sur DoomSiren, le terme
custom et l'AoE de prediction sont pilotes par LA MEME requete native (`battleQuery.<0x7f>` sur la tuile de
la cible) : impossible de les separer geometriquement. La parade : (a) ecraser les PV (`--hp-target 900000`)
pour rendre la contribution AoE petite DEVANT une constante non-scalable (le +1 de l'attaque normale), puis
(b) MESURER cette contribution au `pairUtility` natif (+0.4727) et montrer qu'elle est strictement
inferieure a l'ecart a franchir (1.0963). Le confond n'est pas suppose negligeable : il est chiffre.

**Le regime discriminant se FABRIQUE : deux leviers qui rapprochent les utilites, aucun qui fitte.**
Un terme de +/-10 est inobservable quand l'ability domine l'attaque normale de +32 d'utilite de paire.
Les deux leviers utilises sur SavageEchoes, dans cet ordre : (1) **`--hp-target` eleve** — l'utilite de
degat est ~ `degat/PVmax`, donc gonfler les PV de la cible contracte l'ECART ABSOLU entre deux abilities
sans toucher a leur ordre ; (2) **`--armor-target` eleve** — le plancher percage
(`max(0, d - armure, d x pierce%)`) fait diverger deux profils de percage differents (Eviscerate 50 %
vs Power 40 %), ce qui **inverse** l'ecart offline et l'amene dans la fenetre ou le poids de la BC
decide. Aucune constante n'est ajustee : on deplace le POINT DE MESURE jusqu'a ce que la sortie
observable (le choix d'ability) devienne sensible au terme, puis on verifie que natif ET moteur y
basculent ensemble, et que forcer le terme a 0 les fait DIVERGER.

**Un catalogue de la BC PERIME peut degrader en SILENCE — et le 3e catalogue (`Utilities`) est le plus
traitre des trois.** `BC.Abilities` (#254) LEVE sur cle absente : la panne est bruyante (« system
error »). `BC.Utilities`, lui, **logue et rend `Fix64(0)`**
(`Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue`) : le terme custom d'une ability
neuve vaut 0 des DEUX cotes, l'A/B ne bascule jamais, et la conclusion naturelle — « le natif n'exerce
pas cette branche » — est fausse. **Reflexe a la migration de build : re-synthetiser TOUS les
catalogues de la BC depuis le gameconfig vivant, et verifier que le poids qu'on s'apprete a mesurer
est NON NUL avant de monter le montage.** Corollaire symetrique : un refresh de config peut
DEMASQUER des gaps de port jusque-la caches par la peremption — les mesurer et les nommer, pas les
re-masquer.

**Un numero de slot d'interface n'est PAS stable entre builds ; l'ANCRE l'est.** `IBattleQuery`+0x7f
designait `GetAdjacentEnemies(tile, unit)` sur `gqfc5mff6c` et designe `GetAdjacentEnemies(entity,
unit)` sur `rnca9r7q6c`, ou c'est 0x80 qui porte la surcharge « tuile ». Pire, l'index de vtable 0x7f
(sans l'`interfaceOffset`) est `GetAdjacentUnits` — **amis compris**. La procedure : dumper la vtable
de la classe CONCRETE (`resolveVtableSlot` borne), etablir l'`interfaceOffset` par une ancre
independante (un call-site nomme dont le slot est lisible au decompile, ici
`IsMeleeAttackAbilityTrigger$$ShouldTrigger` -> slot 2 <-> `IsMeleeAttack` index 6), puis LIRE la
surcharge. Et poser un bras de controle qui casserait si on s'etait trompe d'une case (ici : un ALLIE
adjacent ne doit rien changer).

**Un `act move` REFUSE ne leve rien — et un montage qui se degrade rend « 100 % MATCH ».** Sur un
board ou la tuile visee est injouable ou occupee, l'unite reste ou elle est : les trois bras d'un A/B
deviennent le MEME etat, et l'accord moteur<->natif y est trivialement vrai. Signature : les mesures
sont identiques d'un bras a l'autre ALORS QUE le levier etait cense changer. **Verifier les positions
obtenues contre les positions voulues, et refuser de mesurer sinon** — c'est trois lignes, et sans
elles une generalisation ratee se lit comme une generalisation reussie.

**Une ability que `decisionView` nomme `id:<n>` est INVISIBLE au predicteur offline — et le silence est
total.** La map `frida/hooks/data/ability-names.ts` est GENEREE et figee dans le bundle injecte ; un id
absent sort en placeholder, le predicteur cle sa recherche gameconfig sur ce NOM, `make_damage_predictions`
rend `[]`, et l'ability n'est jamais candidate : ni erreur, ni desaccord de degat, juste une action qui
n'existe pas cote moteur. Signature a reconnaitre : `ctx.ab_name_by_id[id]` commence par `id:`. Le repli
sur `ActiveAbilityType(id).name` (source independante) coute 3 lignes ; sa portee se MESURE (8 ids sur
331 ici) avant de l'introduire, pour ne pas debloquer en masse des abilities jamais validees.
