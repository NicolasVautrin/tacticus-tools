# Case #44 — portage des 5 playbooks NonComparable du « lead 8 »

**Contexte** : suite directe du REFRAME de [`case-34-nonattack-oracle.md`](case-34-nonattack-oracle.md).
Les 5 abilities que l'étage agreement classait « non-attack-oracle » (l'oracle `aiPlaybookPredict` ne
rendait aucun `ProbableDamageEvent`) ne sont **pas** des émetteurs heal/effect : ce sont des
**playbooks NonComparable natifs** (`EvaluateNonComparable`, **aucun** `Make*Predictions`). Le
déblocage n'était donc pas un décodage d'événement mais un **portage de playbook**.

## 1. RE par playbook (décompilé = vérité)

Toutes les `MIN_UTILITY` viennent du `.cctor` du playbook et valent `Fix64.FromInt(1)` ;
aucune des 5 abilities (1113, 1121, 1151, 1163, 1202) ne figure dans la table
`engine.playbook.noncomparable.NATIVE_PRIORITY` → `PRIORITY = 0` (`AbilityPriority.Normal`) pour
les 5. ⚠ La justification originelle (« `get_Priority` n'est surchargé par aucun playbook », #115)
est FAUSSE et a été corrigée par **#170** : 22 playbooks le surchargent. La valeur 0 de ces cinq-là
reste juste, mais elle vient désormais d'une **mesure exhaustive** (invocation du slot 0 de la
vtable d'interface sur les 257 `ActiveAbilityType`), pas d'une généralité.
Éligibilité commune = `BasePlaybook.GetEligibleTargetsSelectable @18111f0d0` =
`IBattleQuery` slot `0x41` `GetValidTargets(unit, UnitPosition(position), abilityType)` puis
`ListExtensions.Remove(<prédicat BasePlaybook>)` → **légalité PAR POSITION**, pas l'union des
tuiles de mouvement.

| id | playbook | `EvaluateNonComparable` | utilité |
|---|---|---|---|
| 1113 | `StormcallerPlaybook` | @181160ff0 | `GetTargetUtility @1811613a0` : `Fix64.Zero` puis **+1 par tuile de la zone de glace portant une unité** (`GetUnit(tile) != null`, **aucun** filtre d'équipe). Zone = `StormcallerAbility.GetAddIceTiles @18120cf70` = `AdjacentTiles(Target) + Target`. Gate par cible : `WillNormalAttackKill(target, position) → continue`. |
| 1121 | `ItItchesPlaybook` | @181146c50 | `Fix64.FromInt(Count(GetTargetUnits))` où `ItItchesAbility.GetTargetUnits @1811ec5e0` = `Enemies(Target + AdjacentTilesIntersection(caster, target))` = la cible + les ennemis adjacents **à la fois** à la cible et au caster. Gates : `IsDisplaceable(target) @180ed8140` puis `CanBePushed` (@181146aa0, slot `0x4d` + `FilterInPlace`, `Count > 0`). |
| 1151 | `TheQuickeningPlaybook` | @18116afb0 | paliers `+1` cumulatifs — base 1 ; gate `GetNumAttackTargetsInPosition(caster, targetTile) == 0 → continue` ; `+1` si un **ami** est sur la tuile ; `+1` de plus si `HasFaction(ami, faction(caster))` ; `+1` de plus si l'ami échangé peut attaquer depuis la position du caster ; `+1` si `HasTriggeredAbility(caster, 0x4df = FuryOfTheAncients)` **et** que la position évaluée ≠ la tuile courante. **Cible = entité TUILE.** |
| 1163 | `BlackRagePlaybook` | @1811211f0 | `PredictAttack` (slot `0x21`, attaque **NORMALE** du caster depuis la tuile de charge) → `ProbableDamageEvent` → `CalculateUtilityFromDamageEvent @1814a9f90`. Le coût en PV (50 %) n'entre **pas** dans l'utilité. |
| 1202 | `VigilanceEternalPlaybook` | @18117fae0 | `GetDamageFormula(position)` + `GetDamageProfile` + `GetHits` → `CalculateUtilityFromDamageEvent` (surcharge @1814aa3d0). |

`WillNormalAttackKill @18111fff0` = `PredictAttack` (slot `0x20`) →
`DamagePredictionResult.get_WillBeKill` = **sure-kill** (borne MIN ≥ PV) = `killSure` du composite.
À ne pas confondre avec `EnemyCouldBeKilledWithNormalAttack` (existe-t-il *un* ennemi sure-kill),
déjà porté pour HammerOfWrath.

## 2. Port

Un fichier par playbook dans `scripts/python/engine/playbook/noncomparable/` (`stormcaller.py`,
`it_itches.py`, `the_quickening.py`, `black_rage.py`, `vigilance_eternal.py`), fondations partagées
ajoutées dans `_base.py` :

- `_will_normal_attack_kill` / `_get_num_attack_targets_in_position` / `_normal_attack_ids` (mirrors
  homonymes des fonctions natives) ;
- `NCContext.plans` = plans de **toutes** les unités (le terme « l'ami échangé peut attaquer » de 1151
  interroge le plan d'un allié, pas seulement celui du caster) ;
- `_PlanTargetPlaybook.SWEEP_ALL_RANKED` : les playbooks à utilité **position-dépendante** (1163, 1202)
  balaient **toutes** les tuiles rankées de la paire (mirror du balayage de positions du generator
  natif restreint aux positions légales) au lieu de `ranked[0]`.

Les 5 noms sont ajoutés à `_NONCOMPARABLE_ABILITIES` (`entities/abilities/active_ability.py`) : la
mesure live (#34) montre que `MakeDamagePredictions`/`MakeHealPredictions`/`MakeEffectPredictions`
rendent **tous `null`** → aucun `ProbableDamageEvent` **affiché** (même loi que Gauntlets/Hammer,
#109). Conséquence : `make_damage_predictions` rend `[]` pour eux ; l'utilité de décision de 1202
appelle donc `generate_multi_hit_attack_prediction` **directement** (même contournement que
`make_hammer_wrath_events`), et celle de 1163 passe par l'attaque normale.

## 3. Mesure (agreement `--build --seeds 777,31337 --steps 20`, board MC1_67)

| | ability | move | prédiction |
|---|---|---|---|
| baseline #43 | 24/29 (3 « non-attack-oracle ») | 31/35 | 21/21 |
| 1113/1121/1163/1202 enregistrés, 1151 **hors registre** | **25/29** | **31/35** | 21/21 |
| + fix cible 1163 au contact (#47) | **26/29 (89 %)** | **31/35** | 21/21 |

- **1113 Stormcaller** (31337 s11, u89 → cible 81) : **hit** — le miss est fermé.
- **1163 BlackRage** (31337 s12, u91) : **RÉSOLU (#47)** — la bonne ability ET la bonne cible (85).
  La divergence était la **position de prédiction** : la charge ferme au contact avant l'attaque
  (`ExecuteBehaviour @1811b9c20` : `MoveUnit(First(SortTilesByUtility(TilesUnitCanMoveToChargeTarget)))`
  puis `UseActiveAbility(attaque normale)`), donc la prédiction de décision est celle de l'attaque
  **de MÊLÉE au contact**, indépendante de la position d'évaluation du générateur (mesure s12 : le
  natif émet (1163, 85) **sans pré-move**). Le port scorait la paire depuis la tuile de cast rankée
  (= l'origine) → sélection d'arme **ranged** (dist 2) → 85 = 1 hit u=40,3 vs 77 = 4 hits u=50,2 →
  mauvais argmax. Au contact : 85 = mêlée 4 hits 3008-3788 `kill` → **u=132,8** ≫ 77 (jamais kill,
  hp 8533) — argmax natif reproduit. Fix : `evaluate_non_comparable` évalue chaque hex **adjacent à
  la cible** libre+walkable (mirror `TilesUnitCanMoveToChargeTarget`) et garde le max ; la tuile de
  cast ne sert que d'ancre `to` (`ranked[0]`=origine → `to=None`, cast en place comme le natif) ;
  `SWEEP_ALL_RANKED` retiré (prédiction indépendante de la tuile de cast).
  **Hypothèse « bonus +728 » RÉFUTÉE au décompilé** : le bonus est l'effet `BlackRage_ExtraDamage`
  (1343 = `0x53f`, trigger DSL `OwnerIsCaster & IsCharging & IsNormalAttack`,
  `CreateEffectDamageBonusForAttack @180f340e0`, magnitude `ConfigVar 8`) posé par `AddEffect(0x53f)`
  dans l'`ExecuteAtomic` d'`ExecuteBehaviour` — donc **à l'exécution seulement**, absent de l'unité à
  l'instant de la décision → la prédiction native ne peut pas le voir ; ne PAS l'ajouter au port
  (ce serait un fit).
- **1121 ItItches** : **CONFRONTÉ + RÉSOLU (#48, 2026-07-20, seed 909 s14, u93 tyranParasite)** —
  le natif émet (1121 → tuile 63) là où le port n'émettait JAMAIS. Deux fixes (it_itches.py) :
  1. **Les cibles éligibles sont des TUILES, pas des unités** : `abilityTargets` 1121 rend
     `kind=tile` (mesure s14 : 5 tuiles = les 5 positions ennemies) → l'ancien parse `kind=="unit"`
     rendait une liste vide → aucun candidat. Décompilé @181146c50 : l'élément éligible est passé
     **tel quel** à `GenerateAction` (→ le natif émet un **id de tuile**, 63=(5,6)=u81) et l'unité
     des gates (`IsDisplaceable`) est résolue depuis l'élément via `UnitExtensions.GetUnit`.
  2. **Ordre par-position = ordre `GetAdjacentTiles` natif** (`neigh_by_pos`), décisif au keep-first
     du Bucket à util égal : à P=(4,5), (5,5) et (5,6) rendent toutes deux util=2, mais les voisins
     natifs de (4,5) = `[54, 63, 62, …]` → 63=(5,6) énuméré AVANT 62=(5,5) → le natif garde 63 ;
     l'union RPC (ordre trans-positions) listait (5,5) d'abord → mauvaise cible à util égal.
  Résultat 909 : **ability 6/6 (100 %)**, move 15/16 (résidu unique = s17 cast-tile, cf. #32),
  prédiction 4/4 ; **777+31337 inchangés** (27/29, 31/35, 21/21 — pas d'overfire induit).
- **1202 VigilanceEternal** : confronté sur 909 s17 (u95 Tyrith) → **hit ability+cible** (1202→85
  des deux côtés) ; seul le **cast-tile** diverge (natif (3,4) vs moteur (4,2)) = résidu
  move-with-ability fiché #32.

## 4. Le point dur : 1151 TheQuickening — porte RÉSOLUE (#46) : `turnsStarted > 1`

**RÉSOLUTION (2026-07-20)** — le mécanisme complet, en 3 pièces :

1. **La porte = slot 4 `ShouldEvaluate(unit)` de la vtable, corps FOLDÉ @18111af90** (symbole
   `AlphaWarriorPlaybook$$ShouldEvaluate`, COMDAT, refcount 7) = **`GetStat(unit, 0xc=TurnsStarted) > 1`**
   — l'ability n'est JAMAIS évaluée pendant le **premier tour** de l'unité (`turnsStarted` = compteur
   per-unit incrémenté au StartTurn, `UnitComponent.turnsStarted@+0x58`, stat 12 déjà portée #122).
   Résolu LIVE par `resolveVtableSlot` (introspect.ts) sur la classe : entrée vtable @0x298
   (= itf IPlaybook offset 18 + slot 4) → code @18111af90. Vtables partageant ce corps parmi les
   NC portés : **TheQuickening(1151), HeroicFusillade(1180), VigilanceEternal(1202)**, AlphaWarrior
   (non porté) — le gate a été ajouté aux trois (`should_evaluate` → `_turns_started_gate`, `_base.py`).
   Mesures concordantes (seed 31337, MC1_67) : pas 5 (1er tour u81, ts=1) → slot4=0 (8/8), le natif
   attaque normal ; pas 15 (2e tour, ts=2) → slot4=1, le natif émet 1151 ; step 0 frais (ts=0) →
   slot4=0 + `GetUseProbability`=1.0. La corrélation RapidAssault (n=2) était un **proxy du 1er tour**
   (ces effets tombent après le 1er tour), pas le mécanisme — l'anti-fit a payé.
   **Correction du §4.1 initial** : la voie `prob := vtable[0x1f8]` de `BasePlaybook.ShouldEvaluate
   @18111fb70` n'est PAS l'implémentation de ce playbook — le slot 0x1f8 pointe
   `BasePlaybook.GetUseProbability @18111fa00` = `Fix64(1)` constant (vérifié live = 1.0) ; la
   déduction « branche prob<=0 » raisonnait sur la MAUVAISE implémentation du slot 4.

2. **Le miss de CIBLE résiduel (52 vs 35) n'était PAS un tie d'ordre** : la cible native 52=(4,4),
   **occupée par l'allié u79** (l'échange = la raison d'être de l'ability), était jetée par le mirror
   plan-based de `GetNumAttackTargetsInPosition` — les tuiles rankées des attackPlans sortent de
   `GetPossibleMovementTiles`, donc une tuile OCCUPÉE n'y figure jamais, alors que le slot natif 0x7f
   prend la position en ARGUMENT (hypothétique, non contrainte par l'occupation). Fix : fallback
   géométrique MELEE hors univers movable (`count_adjacent` + porte élévation) dans
   `_get_num_attack_targets_in_position` (`_base.py`) ; borne inf résiduelle = arme RANGED (LoS non
   portée). NB : l'union `abilityTargets` inclut BIEN les tuiles allié-occupées (mesure pas 15 :
   25 tuiles dont (4,4)) — l'énumération n'était pas le problème.

3. **Ciblage natif de 1151** (`GetDynamicInvalidTargetReason @181212560`) : sélecteur =
   `MovableTilesInRange(caster, Direct(range=cfg 0x16=2), 1, 1)` **moins** `Enemies(...)`
   (op_Subtraction) ; tuile vide OK, tuile occupée OK **ssi** `GetFeetCount(occupant) ==
   GetFeetCount(caster)` (même empreinte → échange légal). Les tuiles ennemies sont exclues.

**Verdict mesuré** (agreement `--build --seeds 777,31337 --steps 20`, MC1_67) : 31337 pas 5 = MATCH
(gate ferme le 1er tour), pas 15 = **MATCH ability+cible** (1151→52) — position ~1hex ((3,6) vs
(4,5), tie util=3, ordre de sweep → `pos-downstream-of-ability`). **Ability 26/29 → 27/29 (93 %)**,
`nc-pair` disparu ; move 31/35 et prédiction 21/21 inchangés. 1151 **ENREGISTRÉ** dans `PLAYBOOKS`.

Historique de la localisation (mesures live pré-résolution) :

Mesure seed 31337 :

- **pas 5** — u81 à l'origine (5,8), 21 tuiles de move, `abilityTargets(81, 1151)` = **36 tuiles
  valides**, ability `usable = true`. Le **natif joue l'attaque NORMALE** (ab 69 → u95) et n'émet
  **pas** 1151. Or le gate `GetNumAttackTargetsInPosition > 0` de `EvaluateNonComparable` passe pour de
  nombreuses tuiles, **dont (3,5)** — précisément la tuile d'où le natif attaque.
- **pas 15** — origine (3,5), 4 tuiles de move : le natif **émet** 1151 → tuile 52 = (4,4).

Comme toute NonComparable qui « sort » prime sur toute Comparable **par l'ordre des générateurs**
(`InitAbilityTypeLists @1810ed540` + `<CalculateNextActionForUnit>d__5 @1810f54e0` = first-generateur-
non-vide), le natif n'aurait **pas pu** attaquer au pas 5 si le playbook 1151 avait produit une action.

### 4.1 (historique) Localisation live de la porte = `IPlaybook` **slot 4 `ShouldEvaluate(unit)`**

Le générateur `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` gate CHAQUE ability, AVANT
tout sweep de position, par DEUX prédicats d'interface : `slot 4 ShouldEvaluate(unit)` (`FUN_180003bd0(4,
…)`) **puis** `slot 5 ShouldEvaluate(unit, tiles)` (`FUN_1800051a0(5, …)`). Si slot 4 rend 0, l'ability
est **sautée entièrement** (jamais évaluée) → le fallback Comparable (attaque normale) prend la main.

**Mesure live décisive** (RPC `pbSlots` = mapping vtable de la classe du playbook ; RPC `pbGate` =
invocation d'un slot d'interface avec args résolus ; RPC `ncEvaluate` = la voie `Evaluate(unit, position,
tiles)` par position). Sur seed 31337, board MC1_67 :
- `pbSlots(1151)` : IPlaybook (offset 18) slots 0..13 = get_Priority / get_IsComparable /
  get_CanHandleNullCasterTile / Init / **ShouldEvaluate(1)** / **ShouldEvaluate(2)** / ShouldEvaluate(3) /
  Evaluate(3) / GetCustomUnitOrderUtility(1) / ResetCaches / … / EvaluateNonComparable(3).
- **pas 5** : `slot 4 ShouldEvaluate(unit) = 0` (8/8 invocations → **DÉTERMINISTE**) ; `slot 5 = 1` ;
  `ncEvaluate` rend des actions util=2 à ~13 positions (la leaf « voudrait » tirer).
- **pas 15** : `slot 4 = 1` (8/8) ; `ncEvaluate` rend util=**3** sur exactement (4,5)→tuile (4,4) =
  l'action native (u79 y est allié → 3e palier +1). L'utilité N'est PAS plate ; le miss de cible
  s'explique sans invoquer l'ordre d'énumération.

Donc : **le natif décline 1151 au pas 5 parce que `ShouldEvaluate(unit)` rend 0**, indépendamment de la
leaf. Le wrapper de base `BasePlaybook.ShouldEvaluate(unit) @18111fb70` calcule
`prob := vtable[0x1f8](this, unit)` (VirtualInvokeData {code, MethodInfo} au champ classe 0x1f8) puis :
`prob >= Fix64(1) → true` ; `0 < prob < 1 → tirage RNG autobot (this+0x30)` ; **`prob <= 0 → false`**.
Le résultat étant **stable à 0** (8/8), la branche est `prob <= 0` — un déclin FERME, PAS le tirage
aléatoire (contrairement aux GAP `GetUseProbability` de 1121/1163). `GetUseProbability` de base
(`@18111f9b0` = `Fix64(1)`) donnerait toujours `true` ; **le slot vtable `0x1f8` n'est donc PAS la
`GetUseProbability` de base** — c'est un virtuel per-playbook (ou hérité `NonComparablePlaybook`) qui
rend 0 pour u81 au pas 5. **Reste à nommer `0x1f8`** (résolution de la vtable non faite offline).

### 4.2 (historique) Corrélation RapidAssault — réfutée (proxy du 1er tour)

Le seul état **par-unité** (pas de position) qui bascule entre les deux pas : les effets **RapidAssault**
(`RapidAssault_Movement` 1228 + `RapidAssault_ExtraDamage` 1229) sont **présents sur u81 au pas 5**,
**absents au pas 15** (mesuré via `decisionView.effects`). Hypothèse : `ShouldEvaluate(unit)` de 1151
décline tant qu'un effet de mouvement (RapidAssault / « a déjà bougé/assailli ce tour ») est actif. C'est
une corrélation sur **n=2** → NE PAS porter dessus (anti-fit) ; il faut le mécanisme natif de `0x1f8`.

→ 1151 reste **porté mais PAS enregistré**. Prochaine étape #46 : nommer le virtuel `0x1f8` (résoudre la
vtable de `TheQuickeningPlaybook` : soit statiquement via le layout `Il2CppClass.vtable`, soit live en
lisant `klass+0x1f8` → `MethodInfo.name`), lire son corps, et si le déclin est bien un état lisible
offline (effet RapidAssault / flag « moved this turn »), porter le gate + enregistrer 1151.

Outils réutilisables livrés pour ça (RPCs `frida/hooks/features/ai-step/rpc-predict.ts`, non commités) :
`ncEvaluate` (leaf par position), `pbSlots` (mapping itf→méthode d'un playbook), `pbGate` (invocation
d'un slot d'interface avec args `unit`/`pos`/`tiles`).

## 5. Écarts assumés (flaggés dans le code)

- **`ShouldEvaluate(unit)` slot 4** — **PORTÉ** (#46) : `NonComparablePlaybook.should_evaluate(ctx)`
  (base True = mirror `BasePlaybook.ShouldEvaluate @18111fb70` avec `GetUseProbability` de base
  `Fix64(1)`), testé par `choose_action` AVANT `generate_candidates` (mirror du gate
  `FUN_180003bd0(4,…)` du générateur). Overrides portés d'après la RÉSOLUTION LIVE des vtables
  (`resolveVtableSlot` @0x298) : 1151/1180/1202 = corps foldé @18111af90 (`turnsStarted > 1`,
  `_turns_started_gate`) ; 1153 Hammer = `!EnemyWillBeKilledWithNormalAttack @181142320` (relogé de
  `generate_candidates` vers `should_evaluate`) ; **1183 Vexilla = MÊME corps foldé @181142320 que
  Hammer** (gate ajouté). NovaBoost/NovaShield gardent leurs overrides propres (écart usable-proxy
  documenté dans nova_boost.py).
- **`GetUseProbability` (porte ALÉATOIRE)** non modélisée — le moteur offline est déterministe :
  1163 `@181121740` = `0.4` si les PV après usage (`GetHealthPercentageAfterUse @1811ba570`, ConfigVar
  0x26 = 50 %) < PV courants, sinon `1.0` ; 1121 `@1811477b0` = `Fix64.FromIntFraction(GetMaxNumUnitsAffected, 3)`.
  Même statut que ScarabSummon. (NB : pour 1151 le gate slot 4 est DÉTERMINISTE `prob<=0`, PAS ce tirage.)
- **Slot `0x4d`** de `CanBePushed` (1121) non identifié (ce n'est ni `GetAdjacentTiles` = `0x4e`, ni
  `GetTilesBehind` = `0x53` — arités différentes) → porté par la **géométrie réellement exécutée**
  (`DisplaceUnitOperation` / `FindTileToPush @180e695e0` : un pas dans la direction caster→cible, tuile
  walkable et libre).
- **`IsDisplaceable`** : le FLAG runtime `HasFlag(unit, 0x19)` n'est pas lisible offline (énum de flags
  d'entité, distincte des traits gameconfig) → seuls les traits `Immovable(17)` / `Hulking(3)` /
  `BigTarget(1017)` sont testés.
- **`GetNumAttackTargetsInPosition`** porté via le plan natif (`attackPlans`) → vaut 0 pour un **allié**
  quand le contexte ne fournit pas son plan (bridge offline `state_bridge` ne peuple que l'unité
  active) : le 3ᵉ palier de 1151 dégrade à la baisse.
