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

## TRANCHE 4b (2026-07-30) — le VERROU 2 est leve : une route pour les Comparable SANS prediction

### Ce que le decompile dit vraiment de `CalculateActionUtility`

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
relue integralement sur `rnca9r7q6c` :

```
u = CalculateCustomUtility(vtable +0x338)(caster, casterPosition, target, abilityOrEffect, possibleTargets)
if (u == <sentinelle A> || u == <sentinelle B>) return null;          // Fix64? VIDE
if (u == <sentinelle C>) return Nullable(<sentinelle C>);
u += CalculateUtilityFromPredictions(caster, casterPosition, target, abilityOrEffect)
if ( ShouldExecute(vtable +0x328)(caster, casterPosition.MainTile, target, u) ) {
    u += CalculateCasterPositionUtility(vtable +0x348)(caster, casterPosition, abilityOrEffect)
    u += <service #0x37>.slot5( IdunBattle.AI.Utilities.UtilityAttackCase$$Base(caster, casterPosition,
                                                                               target, abilityOrEffect) )
    u += CalculateUtilityFromTilePrediction(caster, casterPosition, target, ...)
    return Nullable(u)
}
return null;
```

Deux faits, et ils corrigent la redaction des tranches precedentes :

1. **Le custom est calcule EN PREMIER** et entre dans l'ARGUMENT de `ShouldExecute` — ce n'est pas un
   terme ajoute apres coup a une utilite de degat. (Les offsets de vtable cites en tranche 3
   — « custom = +0x348 » — etaient decales d'un slot : `+0x338` = `CalculateCustomUtility`,
   `+0x348` = `CalculateCasterPositionUtility`. Le port, lui, etait juste : il sommait bien le custom
   AVANT l'argmax de tuile.)
2. **`ShouldExecute` par DEFAUT rend `true`.** MESURE au slot de vtable, pas deduite
   (`probe_27_4b_chronometron_vtable.py`) : le slot `+0x328` de `ChronometronPlaybook`,
   `DrachnyenPlaybook`, `DoomSirenPlaybook` et `ForwardObserversPlaybook` pointe sur le MEME corps
   trivial `return 1`, dont l'unique proprietaire nomme dans `methods.tsv` est
   `UnityEngine.U2D.IK.Solver2D$$DoValidate` (dedup IL2CPP). Les `<X>Playbook$$ShouldExecute` NOMMES
   (`...HealingBalms_HealPlaybook$$ShouldExecute` = `utility > Fix64(0)`,
   `...ArmoriumCherubPlaybook$$ShouldExecute`, `...SorcerousFacadePlaybook$$ShouldExecute`) sont des
   OVERRIDES. Chercher « le ShouldExecute de la base » dans la table aurait donne la reponse INVERSE.

**Consequence** : le natif n'exige NULLE PART une prediction de degat pour generer une action. Ce qui
borne l'ensemble, c'est le CIBLAGE (`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities`,
recalcule PAR TUILE candidate), pas un `damageProfile`. Le gate `if not events: return None` du port
(`ComparablePlaybook.calculate_action_utility`) n'a donc **aucun equivalent natif** : c'est LUI le
verrou 2.

### La route portee — `engine/playbook/nonattack.py`

Route Comparable SECONDE, strictement ADDITIVE (ni `_best_attack` ni le gate `if not events` ne sont
touches — le regime ATTAQUE reste inchange, delta d'agreement nul par construction) :

- `NonAttackComparablePlaybook` : `make_damage_predictions -> []`, `u = custom`,
  `should_execute` (defaut `True`, mirror du slot `+0x328`), `u_full = u + tile_utility(tuile)`,
  `eligible_targets` (mirror de `GetEligibleTargetsEntities` via le seam `ctx.ability_targets`),
  `is_caster_added` (mirror de `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`,
  branche self-cast : `GetValidTargets` vide -> `GenericBrokenTargetingRule(0x800)`, le caster n'entre
  pas dans les cibles depuis cette tuile).
- `nonattack_candidates(ctx)` : mirror des deux boucles natives —
  `...ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` (ability x tuile, ordre
  `ctx.reach_nc` = origine en tete) et `...ComparablePlaybook...$$EvaluateInternal` (cibles,
  keep-first STRICT). Appelee par `ComparableAbilityGenerator.generate`, a cote de `_heal_candidates` /
  `_repair_candidates` / `_bespoke_candidates`.
- Registre **EXPLICITE** `NONATTACK_PLAYBOOKS` : seule une ability dont le playbook est PORTE y entre.
  Une route generique (« toute non-attaque devient candidate ») serait une degradation permissive —
  exactement le trou qu'un entrainement irait exploiter.

**Classification DSL/imperatif** (tranchee AVANT de coder) : la route (`CalculateActionUtility`,
`ShouldExecute`, `EvaluateInternal`, l'`ActionGenerator`) est **imperative** — ce sont des methodes,
pas des arbres `DSLFactory`. Le SELECTEUR `GetAffectedEnemies` est **declaratif** : c'est le MEME arbre
que la face COMBAT, et le port l'EVALUE au lieu de recabler l'adjacence a la main.

### Chronometron (1226) — l'override porte derriere ce verrou

| Ability (id) | Symbole | Formule mirroir | Poids | Porteur | Validation |
|---|---|---|---|---|---|
| **Chronometron** (1226) | `IdunBattle.AI.Playbook.Loki.ChronometronPlaybook$$CalculateCustomUtility` | `W * Count(ChronometronAbility$$GetAffectedEnemies)` ; `GetAffectedEnemies` = `DSLSelectors.SurroundingEnemies(<unite>, GetNumberConstant(0x16 = range), unique:1, sel:3)` — surcharge **5-args** (2e parametre `unit`, pas `unitTile`) = `Enemies(unit, Units(SurroundingTiles(unit, includeCenter:1, range) - Tiles(unit), unique, sel), sel)`. Terme **LINEAIRE**, ancre sur la MainTile **REELLE** du caster, centre exclu, **sans** `Unobscured`. | `Chronometron_AffectedEnemies` = **10** ; `range` = `Chronometron.constants.range` = 2 | necroChronomancer `Thothmek` [lineup, hors seed BC -> `catalog_inject.py --units necroChronomancer`] | **A/B causal live** (`probe_27_4b_chronometron_ab.py`, board MC1_67, seed 909, `--hp-target 85000`), 4 bras, moteur = natif dans les 4. Detail en §Validation. |

**Le meme artefact natif que la face COMBAT** : `...ChronometronAbility$$ExecuteBehaviour` re-inline
exactement le meme appel a `SurroundingEnemies` (memes 5 arguments) pour alimenter son `Foreach`. Un
seul artefact, un seul port — le mirror decision `battle_query.surrounding_enemies_in_range` et le
mirror combat `necrons.chronometron_affected_enemies` decrivent le meme ensemble. La face COMBAT etait
deja portee et validee (#116) : cette tranche ne couvre que la face DECISION.

**Piege evite** : `battle_query.surrounding_enemies` existait deja, mais il mirroir le
`Unobscured(SurroundingEnemies(...))` de `...GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector`
et fige `r = 2`. Le reutiliser aurait retire des ennemis a distance 2 obscurcis que CE selecteur-ci
compte, et fige un rayon qui vient d'un `GetNumberConstant`. D'ou une fonction distincte.

## TRANCHE 4c (2026-07-30) — ForwardObservers (1185), 2e membre de la route non-attaque

### Ce que le decompile dit

`IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CalculateCustomUtility`, relu VERBATIM sur
`rnca9r7q6c` :

```
CheckIfAnyEnemyHasMarkerLight(caster);              // remplit le cache (this+0x70 = calcule, +0x71 = flag)
u = Fix64.Zero;                                     // <Fix64 statics>+0x28, ecrit a 0 par `FixMath.NET.Fix64$$.cctor`
if (!this.<anyEnemyHasMarkerLight @+0x71>)
    u = Fix64.op_Addition(u, GetUtilityValue("ForwardObservers_EnemyHasNoMarkerlight"));
if (target == null) throw;
comp = <FillUpStatComponent de la CIBLE, StatType 5 = Health>;
if (comp == null) throw;
return Fix64.op_Addition(u, Fix64.op_Multiply(comp.RemainingPercentage(),
                                              GetUtilityValue("ForwardObservers_TargetHealthPercentage")));
```

et `IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` :

```
if (this.<calcule @+0x70>) return;                  // remis a 0 par `...ForwardObserversPlaybook$$ResetCaches`
this.<calcule @+0x70> = true;
player = EntityExtensions.GetCurrentPlayer(caster, this.<state @+0x20>);
foreach (e in this.<battleQuery @+0x28>.<slot itf 0x8e>(player))
    if (EntityExtensions.HasEffect(e, this.<state @+0x20>, 0x462, null)) {
        this.<anyEnemyHasMarkerLight @+0x71> = true; break;
    }
```

Trois points de RE qui ne se devinent pas :

1. **Le slot d'interface `0x8e` est `GetAllEnemiesOf`**, etabli par ANCRAGE et non par recopie de fiche :
   `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass169_0$$u003CGetAllEnemiesOfu003Eb__0`
   (le decorateur enregistreur) appelle ce meme slot avec `(battleQuery, playerEntityId)`, et
   `IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$ShouldExecute` l'appelle avec
   `GetCurrentOwnerEntityId(caster)`. Le corps de `IdunBattle.Core.Services.BattleQuery$$GetAllEnemiesOf`
   ne filtre NI la mort NI la position : c'est « toutes les unites dont le proprietaire courant n'est
   pas ce joueur ».
2. **`RemainingPercentage` est un RATIO, pas un pourcentage.**
   `IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage` =
   `Fix64.Max(Fix64(0), Fix64(<valeur courante @+0x18>) / Fix64(get_CurrentMaximumValue()))` : aucun
   arrondi, aucun x100. Le port ne passe donc PAS par le `round(cur/max*100)` de
   `GetStat(Health, part=1)` (celui de BloodChalice / LightOfSanguinius). Et le composant lu est bien
   celui de la SANTE : le call-site est l'inline exact de la branche `statType == 5` de
   `IdunBattle.Entities.UnitExtensions$$GetFillUpStatComponent` (memes deux classes, meme champ
   statique d'id de composant).
3. **Le terme de Markerlight est BOOLEEN et GLOBAL**, jamais un compte : le natif `break` au premier
   ennemi marque. Il ne depend NI de la tuile candidate NI de la cible — c'est un bonus d'AMORCAGE
   (tant que personne n'est marque, poser la premiere marque vaut 200 ; des qu'un seul ennemi l'a, il
   disparait).

**Classification DSL/imperatif** (tranchee AVANT de coder, et elle DIFFERE de celle de 1226) :
`CheckIfAnyEnemyHasMarkerLight` est une **methode imperative du playbook** — une boucle `foreach` +
`HasEffect`, pas un arbre `DSLFactory`. Le partage decision/COMBAT de Chronometron **ne se reproduit
pas ici** : la face COMBAT
(`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$ExecuteBehaviour`) est
`AddEffect(0x462 Markerlight, TurnsFromRounds(GetNumberConstant(0x45))) +
AddEffect(0x575 ForwardObservers_DamageReduction, TurnsFromRounds(GetNumberConstant(0x77)))` et
**n'evalue AUCUN selecteur d'ennemis**. Il n'y a donc aucun artefact commun a reutiliser, et aucun
risque de fork. Les deux primitives sont ecrites la ou vivent leurs homonymes natifs
(`battle_query.all_enemies_of` = slot 0x8e, `battle_query.entity_has_effect` =
`EntityExtensions.HasEffect`) plutot que recablees dans le playbook.

**Ciblage lu au ctor** (non porte au registre COMBAT — cette tranche ne couvre que la DECISION) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$.ctor` appelle la surcharge
7-args EXPLICITE `TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics>+0x18
= RANGE_FROM_CONFIG, forceMeleeTarget=0 = RangedBool.True, rules=0x200004002, 0, 0)`. Ce n'est **pas**
la forme preset+flags : le litteral EST le masque effectif (`TargetMatchesDynamicRule | TargetIsEnemy |
TargetIsNotAnObject`). `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`. La regle
DYNAMIQUE est portante : `...ForwardObserversAbility$$GetDynamicInvalidTargetReason` refuse (raison 2)
toute cible qui porte DEJA le Markerlight — cote decision, cette cascade est appliquee par le NATIF
(`ctx.ability_targets` = RPC `abilityTargets`), le port en herite sans la rejouer.

### L'override porte

| Ability (id) | Symbole | Formule mirroir | Poids | Porteur | Validation |
|---|---|---|---|---|---|
| **ForwardObservers** (1185) | `IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CalculateCustomUtility` | `[aucun ENNEMI ne porte Markerlight(0x462)] * W_A + RemainingPercentage(CIBLE) * W_B` ; predicat = `foreach (e in GetAllEnemiesOf(GetCurrentPlayer(caster))) if HasEffect(e, 0x462) break` ; ratio = `max(0, GetStat(cible, Health, part 0) / GetStat(cible, Health, part 2))` | `ForwardObservers_EnemyHasNoMarkerlight` = **200** ; `ForwardObservers_TargetHealthPercentage` = **40** | tauSmnStealthSuit (SUMMON **sans invocateur**) + tauNpc5StealthSuit (npc) -> porteur **GREFFE** (cf. ci-dessous) | **A/B causal live** (`probe_27_4c_forwardobservers_ab.py`, board MC1_67, seed 909), 4 bras, moteur = natif dans les 4 ; encadrement **36.5359 < W_B < 41.4060**. Detail en §Validation. |

### Pourquoi le porteur est GREFFE, et pourquoi ca reste une mesure

> **Recette reutilisable — un porteur non spawnable NE ferme PAS le dossier.** L'enchainement
> complet (les deux etages `catalog_inject` / `buildNormalizedBC`, le diagnostic en une commande,
> les trois recours dans l'ordre, et ce que la greffe ne couvre pas) est ecrit une seule fois, en
> **`docs/rl/case-92-catalog-injection.md` §5bis**. Ce qui suit n'en est que l'instance 1185.

Les deux SEULES unites qui portent 1185 sont `tauSmnStealthSuit` et `tauNpc5StealthSuit` (memes actives
`[ForwardObservers, WallOfMirrors]`). Le summon est declare par
`units.abilities.ATemptingTrap.constants.unitId` — mais **aucune unite du gameconfig ne porte
`ATemptingTrap`** (balayage exhaustif du fichier : l'ability n'apparait que comme cle de
`units.abilities` et de `units.abilityPowerModifiers`). Le chemin « SUMMON amene par son summoner »
n'existe donc pas. Et `catalog_inject` ne suffit pas : les deux ids entrent bien dans `BC.Units`, mais
`buildNormalizedBC` les REFUSE (`v2 patch: system error` —
`IStatsFormula.StatsUsingProgressionIndexFor` n'a pas de table de progression pour un summon/npc, comme
pour les 70 entrees `*Npc*` deja skippees), donc ils restent hors du pool spawnable, stats a 0.

Le montage remplace donc `ActiveAbilities` de `tauCrisis` (T'au, pool, arme ranged portee 2) par
`[1185]` dans une COPIE du seed BC. **Ce n'est pas un contournement de la mesure** : le natif charge le
playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite — le code exerce
est bien `ForwardObserversPlaybook`, et le natif le PROUVE en emettant `ActiveAbilityMessage(1185)`
dans `aiDryRunAllUnits` puis en changeant de decision quand on change le SEUL etat que ce playbook lit.
La formule custom ne lit aucune variable d'ability (uniquement `BC.Utilities`), donc la greffe ne la
deforme pas. Le residu que cela laisse est nomme en §Non couvert.

**Le Markerlight est pose par une voie NATURELLE**, pas injecte : `tauDarkstrider` porte le passif
`StructuralAnalyser`, dont
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateTrigger`
= `On(0xa) & IsRangedAttack & OwnerIsCaster` et dont le `CreateBehaviour` fait `AddEffect(0x462, ...)`
sur la cible touchee.

## TRANCHE 4d (2026-07-30) — 1212 `HealingBalms_Heal` : la branche HEAL n'en etait pas une

### Ce que la prémisse annoncait, et ce que le decompile dit

La fiche de tranche 4b rangeait 1212 a part : « `HealingBalms_HealPlaybook` surcharge DEUX choses,
`ShouldExecute` **et** `MakeHealPredictions` : ce n'est pas une ability sans prediction, c'est la
branche HEAL avec sa propre chaine de prediction ». **Le decompile courant refute la seconde moitie.**

`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$MakeHealPredictions` a un corps
**structurellement identique** a `IdunBattle.AI.Playbook.Common.HealPlaybook$$MakeHealPredictions` et a
`IdunBattle.AI.Playbook.Loki.TwistedScience_HealPlaybook$$MakeHealPredictions` : memes appels, memes
arguments —

```
ability = this+0x18
if (ability == null || ability.<+0x90> == null) throw;
targets    = ability.<+0x90>+0x60                       // le MEME selecteur de cibles DSL
healAmount = IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount(ability)
return ComparablePlaybook<T>$$GenerateHealPredictions(this, caster, casterTile, target,
                                                      targets, healAmount, /*scope*/0,
                                                      /*Nullable<Fix64> proba*/ VIDE, klass)
```

— seul le type gshared (`klass`) differe. C'est la **recopie imposee par la hierarchie** : le `.ctor`
de `HealingBalms_HealPlaybook` appelle `ComparablePlaybook<T>..ctor(this, 0x4bc, klass)`, donc la
classe descend DIRECTEMENT de `ComparablePlaybook<T>` et n'herite pas de `HealPlaybook`. Il n'y a
aucune chaine de prediction propre a porter : c'est la chaine de soin STANDARD, deja portee.

⚠ **Generalisation** : « la methode est overridee » ne dit rien du comportement tant qu'on n'a pas
compare les CORPS. Ici trois overrides nommes partagent la meme semantique ; conclure de la seule
presence du symbole aurait fait forker un second predicteur de soin — exactement la divergence
structurelle que le protocole interdit.

### Le seul delta : `CalculateCustomUtility`, et il est MULTIPLICATIF

`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility` :

```
x = Fix64(0)
if (!EntityExtensions$$HasEffect(target, state, 0x5df, onlyActive:0)) {
    foreach (ev in <vtable +0x368 = MakeHealPredictions>(caster, casterPosition.MainTile,
                                                        target, abilityState))
        x += Playbook<T>$$CalculateUtilityFromHealEvent(ev, caster, casterPosition)
}
return Fix64.FastMul(x, Fix64.<statics+0x30>)
```

Deux faits qu'il faut LIRE, pas deduire :

1. **`Fix64.<statics+0x30>` = `Half`.** `FixMath.NET.Fix64$$.cctor` ecrit ce slot avec
   `op_Division(0x100000000, 0x200000000)` = `One / 2`. (Reperes du meme cctor, qui datent la lecture :
   `+0x20` = `One` = `0x100000000`, `+0x28` = `Zero`, `+0x38` = `Pi` = `0x3243f6a88`.)
2. **La somme sommee par le custom est EXACTEMENT celle de la prediction.**
   `ComparablePlaybook<T>$$CalculateUtilityFromPredictions` a **quatre** boucles — degat (slot +0x358,
   `CalculateUtilityFromDamageEvent`), **soin (slot +0x368, `CalculateUtilityFromHealEvent`)**, effet
   (slot +0x378, `UtilityAttackCase$$ForEffect`, utility `0x2e`), reparation (slot +0x388,
   `ForRepairPrediction`, utility `0x2f`) — et le custom re-invoque le MEME slot +0x368 avec les memes
   arguments. Comme `CalculateActionUtility` fait `u = custom + CalculateUtilityFromPredictions` :

   | cible | `custom` | `CalculateUtilityFromPredictions` | `u` |
   |---|---|---|---|
   | sans `HealingBalms_ExtraCritDamage` | `0.5 x U_heal` | `U_heal` | **`1.5 x U_heal`** |
   | avec l'effet | `0` | `U_heal` | **`1.0 x U_heal`** |

   Le terme n'est donc ni un poids de `BC.Utilities` ni un compte : c'est un **facteur** sur l'utilite
   de soin. Corollaire de mesure : il ne peut pas etre encadre par un montage a `U` fixe — il faut
   faire varier `U`, sans quoi un « custom constant » resterait indiscernable.

`0x5df` = `EffectType.HealingBalms_ExtraCritDamage`, l'un des deux stat-modifiers que
`IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility$$ExecuteBehaviour` pose sur
**le meme selecteur de cibles** (`ability.<+0x90>+0x60`) que la prediction, avec `0x5e0`
(`HealingBalms_ExtraCritChance`) — le gate lit donc « cette cible porte deja mon buff ». Un seul
artefact natif pour les deux faces : la face COMBAT et la face DECISION consomment le meme selecteur
et le meme `HealAbility$$HealAmount` ; le port ne fabrique aucun second evaluateur (l'enumeration de
cibles passe par le seam `ctx.ability_targets` = `TargetingQuery` natif).

`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$ShouldExecute` = `utility > Fix64(0)` **seul**.
Le generique `IdunBattle.AI.Playbook.Common.HealPlaybook$$ShouldExecute` y ajoute
`(!IsBoss(caster) || caster != target)` — clause absente ici, et de toute facon inerte en arene.
Effet observable du gate : une cible a PV pleins reste **ciblable** (le ciblage ne teste que
`UnitExtensions$$IsAffectedByHealType`, cf. `...HealingBalms_HealAbility$$GetDynamicInvalidTargetReason`
et l'i2 « Baldr can heal friendly units even if they are at full Health ») mais `MaxFillUp` rend 0,
donc `u = 0` et **aucune action n'est emise**. Mesure : `pairUtility(81 -> 83, 1212)` = `0` sur une
cible a 20000/20000.

**Classification DSL/imperatif** (tranchee AVANT de coder) : `CalculateCustomUtility`, `ShouldExecute`
et la chaine `HealAmount -> PredictHeal -> MaxFillUp -> HealUtility` sont des METHODES, pas des arbres
`DSLFactory` -> **imperatif**, mirror 1:1. Le seul noeud declaratif du chemin est le selecteur de
cibles, et il n'est pas re-cable : il est consomme par le seam de ciblage natif.

### L'ecart de port qu'il a fallu corriger : la MAGNITUDE

1212 atteignait deja le generateur de soin (`_heal_candidates` filtre `"Heal" in name`, et 1212 est
present dans la map `frida/hooks/data/ability-names.ts`) — mais avec **la mauvaise magnitude**.

Le natif dispatche par **CLASSE d'ability**, et il n'existe que deux implementations
(`search_symbols_by_name "HealAmount"`) :

| implementation | formule | qui l'appelle |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Active.MassHealAbility$$HealAmount` | `Direct(AbilityConfiguration$$GetVariableForLevel(cfg, 0x20, abilityState))` = la VARIABLE | MassHeal (8) |
| `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` | `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), Get(1)))` = l'ARME | 18, 1167, **1212** — leurs `MakeHealPredictions` l'appellent NOMMEMENT, sans dispatch virtuel |

Le port choisissait par la **presence** de la variable `hpToHeal`, un proxy. Il est faux pour 1212 :
`_heal_config_key("HealingBalms_Heal")` derive la cle `"HealingBalms"`, c'est-a-dire la config du
**PASSIF**, dont le `hpToHeal` alimente le soin **RETARDE** de l'effet (i2 `UnitEffects/HealingBalms` :
« Is healed for {[hpToHeal]} Health at the start of their next turn »), pas l'action.

Mesure discriminante, canal **scalaire** `pairUtility` (runner 523, board MC1_67, seed 4242, Baldr
`spaceWolfPriest` injecte par `catalog_inject.py --units spaceWolfPriest`) — Baldr attack **2512**,
arme 3 coups, cible `spaceBlackmane` a **5243/20000** (donc `missing` = 14757 > les deux candidats :
regime NON sature, le seul qui tranche) :

| hypothese de magnitude | montant | utilite predite | natif |
|---|---|---|---|
| **ARME** `2512 x 3` | 7536 | **37.6781160942** | **37.67811609432101** |
| config `hpToHeal[50] x 180 %` | 4986 | 24.9287535623 | — |
| config `hpToHeal[50]` non scale | 2770 | 13.8493075346 | — |

Ecart de **12.75 points d'utilite** entre les deux hypotheses : la branche `hpToHeal` est REFUTEE.

**Non-regression, re-derivee du code** : les quatre seuls `ActiveAbilityType` dont le nom contient
« Heal » sont 8 / 18 / 1167 / 1212. 18 (`Heal`) et 1167 (`Heal_TwistedScience`) n'ont pas de `hpToHeal`
sous leur cle derivee — ils retombaient DEJA sur l'arme, valeurs inchangees (6024 pour l'Hospitaller
3-coups, 3614 pour le biophagus 1-coup). 8 (`MassHeal`) passe desormais par la branche config (None
faute d'entree gameconfig -> saturation) au lieu du repli arme, ce que le natif ne fait jamais pour
cette classe ; **inerte** : `unit_map.py find --ability MassHeal` rend **0 unite** sur ce build.

### Deux corrections de la fiche `docs/rl/playbook/prediction.md` §9

Elles ne changent aucun chiffre mesure ici, mais la fiche etait a re-lire (elle l'annoncait elle-meme
sur la chaine repair voisine) :

- **`UtilityType.Heal` = 45 (`0x2d`)**, pas 44. Litteral lu dans
  `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromHealEvent`
  et recoupe par `data/symbols/rnca9r7q6c/frida/enums.tsv`.
- **`bossMod` teste `IsBoss(CASTER)`**, pas la cible.
  `IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext` appelle
  `UnitExtensions$$IsBoss(case+0x10)`, et `IdunBattle.AI.Utilities.UtilityAttackCase$$ForHealPrediction`
  ecrit `caster` en `+0x10` / `target` en `+0x20` — c'est `+0x20` que lit le `GetStat(Health, Maximum)`
  du denominateur. Inerte en arene (`BossUnit` nul).

Confirme par ailleurs, contre le meme decompile : `W_heal = 100` (`HealUtility$$.cctor` =
`op_Implicit(0x64)`), denominateur `maxHP + 1`, `friendSign = -1` si la cible n'est pas amie,
probabilite = `Fix64(1)` quand le `Nullable` est vide (`IdunBattle.AI.Playbook.ProbableHealEvent$$.ctor`),
et `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` = accumulation des bonus-soin d'effets du
caster (non portee), puis `Min(., GetGroupUnitHealLimit)` **si `scope == 1` seulement** — or
`MakeHealPredictions` passe `scope = 0`, ce qui reconfirme le flag OFF de #60 —, puis cap boss sur la
CIBLE, puis `FillUpStatComponent$$MaxFillUp`.

### Le port

- `engine/playbook/common.py::HealingBalms_HealPlaybook` (registre `HEAL_PLAYBOOKS`, dispatch par id
  dans `_heal_candidates`) : `calculate_custom_utility_from_heal` = `Half x heal_term` gate par
  `HasEffect(target, HealingBalms_ExtraCritDamage)`, `score` = `custom + heal_term` avec le gate
  `> 0`.
- `engine/predict.py::heal_amount_for_ability` : mirror du dispatch natif par classe
  (`CONFIG_HEAL_ABILITY_IDS = {8}`).
- Le gate d'effet passe par le MEME canal que le gate TwistedScience deja en place
  (`ctx.scene.eff_state.has_effect`, c'est-a-dire les `EffectComponent`, pas la liste serialisee
  `unit["effects"]` de `decisionView`). Difference de nature a noter : le gate TwistedScience EXCLUT
  la cible de l'enumeration, celui-ci **annule le terme** sans retirer la cible.

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
| 19 | `ChronometronPlaybook` | Chronometron (1226) | necroChronomancer | hero (catalog_inject) | **PORTE** (#27-4b) | — (les trois verrous annonces sont TOMBES : (a) `catalog_inject.py` amene le porteur ; (b) la route non-attaque `playbook/nonattack.py` remplace `_best_attack` ; (c) le selecteur DSL etait DEJA porte par la face COMBAT — `chronometron_affected_enemies`, meme artefact natif) |
| 20 | `DevoutPushPlaybook` @18112c7b0 | DevoutPush (1053) | templInitiate | summon **d'environnement** (`EnvFactionSummons:BlackTemplars`) | **residu** | formule TRIVIALE (`ALoki_NormalAttack.custom * 2` = **2** constant) mais (a) porteur env-only, (b) `damageProfile` absent -> action « push » non modelisee |
| 21 | `ForwardObserversPlaybook` @18113bb70 | ForwardObservers (1185) | tauSmnStealthSuit [summon SANS invocateur] + tauNpc5StealthSuit [npc] | summon + npc | **PORTE** (#27-4c) | — (les deux verrous sont TOMBES : (a) la route non-attaque `playbook/nonattack.py` remplace `_best_attack` ; (b) le predicat Markerlight est un mirror IMPERATIF de `CheckIfAnyEnemyHasMarkerLight` (slot itf 0x8e `GetAllEnemiesOf` + `EntityExtensions.HasEffect`), sans arbre DSL a evaluer. Porteur GREFFE — `ATemptingTrap` n'appartient a AUCUNE unite ET `buildNormalizedBC` refuse summon/npc) |
| 22 | `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility` | HealingBalms_Heal (1212) | spaceWolfPriest `Baldr` [lineup, hors catalogue seed BC -> `catalog_inject.py --units spaceWolfPriest`] | hero | **PORTE** (#27-4d) | — (les verrous annonces sont TOMBES : l'ability n'a pas besoin d'entree gameconfig — sa magnitude vient de l'ARME —, elle est GRANTED des le spawn par `HealingBalmsAbility$$CreateBehaviour` (`RemoveActiveAbility(0x12)` + `AddActiveAbility(0x4bc)`), et elle atteignait deja `_heal_candidates`) |
| 23 | `SavageEchoesPlaybook` @1811586d0 | SavageEchoes (1230) | bloodTerminator | hero hors catalogue seed BC -> **confrontable via `catalog_inject.py`** | **PORTE** (#27-3) | — (verdicts « porteur hors pool » + « evaluateur de CONDITION manquant » des tranches 1-2 **CORRIGES** : le catalogue se complete, et la condition est un simple ratio de PV lu au decompile) |
| 24 | `MortarionsPlagueWindPlaybook` @18114ca30 | MortarionsPlagueWind (1093) | deathBossMortarion | **npc** | **non pertinent** | — |
| 25 | `InstrumentsOfVengeancePlaybook` @1811460d0 | InstrumentsOfVengeance (1215) | darkaBossLion | **npc** | **non pertinent** | — |
| 26 | `MartialExemplarPlaybook` @18114ae20 | MartialExemplar (1216) | darkaBossLion | **npc** | **non pertinent** | — |
| 27 | `TheLionsWrathPlaybook` @18116aba0 | TheLionsWrath (1217) | darkaBossLion | **npc** | **non pertinent** | — |

### Ventilation (les 22 overrides par-ability, apres correction #218)

- **PORTES / couverts : 11** — 1014, 1177, 1020, 1029, 1199, 1119, 1230, 1227, 1226, **1185**, **1212**.
- **Traites sans port (verdict ferme) : 2** — MortisRound (terme mesure NUL), ProperKilly (dead-code).
- **Non pertinents (porteurs NPC uniquement) : 4** — 1093, 1215, 1216, 1217.
- **Residus a debloquer : 6** — 1100, 1169, 1148, 1051/1142, 1098, 1053.
  (Tranche 3 : 10 ; **AmuletOfTheVoidwyrm retire — faux positif, #218** ; **1226 porte — #27-4b** ;
  **1185 porte — #27-4c** ; **1212 porte — #27-4d**.)
>>>>>>> b59bd79f (docs(rl): #27-4c 1212 HealingBalms_Heal - fiche a l etat final + garde live)

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
| **1185 ForwardObservers** | **NON** | **non** | tauSmnStealthSuit [summon SANS invocateur] + tauNpc5StealthSuit [npc] |
| ~~**1212 HealingBalms_Heal**~~ | ~~pas d'entree gameconfig~~ | **sans objet** | spaceWolfPriest [catalog_inject] |

⚠ **La ligne 1212 de ce triage etait un FAUX NEGATIF (corrige #27-4d).** `_is_attack_ability` n'est pas
sa porte : 1212 est un SOIN, il entre par `_heal_candidates` (filtre `"Heal" in name`), route qui ne
demande ni `damageProfile` ni entree gameconfig — sa magnitude vient de l'ARME du caster. L'ability
etait donc DEJA candidate offline, avec la mauvaise magnitude ; le probe de triage, cale sur la seule
porte d'ATTAQUE, ne pouvait pas le voir.

Consequence directe : le verrou « porteur hors `--list-pool` » de la tranche 2 **n'existe plus**
(`catalog_inject.py` complete `BC.Units` ET `BC.Abilities`) ; ce qui restait bloquant pour 1226 / 1053 /
1185 etait la ROUTE (aucun `damageProfile` -> jamais candidate offline), levee en 4b. **Nuance
mesuree en 4c** : `catalog_inject` ne rend pas TOUT confrontable — il complete le CATALOGUE, mais
`buildNormalizedBC` filtre ensuite sur `IStatsFormula.StatsUsingProgressionIndexFor`, qui **refuse les
summons et les npc** (`v2 patch: system error`). Un porteur summon/npc reste donc hors du pool meme
injecte ; le chemin restant est (a) son SUMMONER s'il en a un, (b) sinon la GREFFE de l'ability sur une
unite du pool (le playbook se charge par ABILITY, pas par unite).

### Les VERROUS qui tiennent les residus

1. **MoW non modelisees comme unites de DECISION** (1169, 1148, et la face MoW de 1142) — le blocage
   le plus rentable : 3 overrides d'un coup, et `PlagueburstMortar` est deja un patron PORTE
   (`count(GetAdjacentEnemies) * W`, identique a Drachnyen). Mesure live (runner 336) : les MoW
   DEPLOIENT bien (`observeBattle.mows` = 2) mais n'apparaissent ni dans `decisionView.units`
   ni dans `attackPlans`, et `aiDryRunAllUnits` ne leur propose rien. **La face COMBAT de 1169/1148
   est deja portee et validee live par #90** : c'est donc STRICTEMENT le volet DECISION qui manque
   (les deux faces se valident separement, cf. le protocole `tacticus-re-port`).
2. ~~**Routes d'ability non-attaque**~~ — **VERROU LEVE (tranche 4b)**. La route existe
   (`engine/playbook/nonattack.py`) et est validee live sur son premier membre, Chronometron (1226).
   `state_bridge._is_attack_ability` n'est plus la SEULE porte : une ability Comparable sans
   `damageProfile` entre par `NONATTACK_PLAYBOOKS`. Ce qui reste sur les autres items n'est plus la
   route mais leur verrou PROPRE :
   - ~~**1185 ForwardObservers**~~ — **PORTE (#27-4c)**. Le predicat Markerlight est un mirror
     IMPERATIF de `...ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` (slot d'interface 0x8e
     = `GetAllEnemiesOf` + `EntityExtensions.HasEffect(0x462)`) : ce N'EST PAS un arbre DSL, et la face
     COMBAT ne partage aucun artefact avec lui. Le ciblage ENNEMI n'a rien demande de special —
     `eligible_targets` de la route lit le RPC natif `abilityTargets`, qui rend deja des ennemis. Le
     verrou REEL etait ailleurs : **le porteur** (summon SANS invocateur + npc, tous deux refuses par
     `buildNormalizedBC`), leve par GREFFE de l'ability sur une unite du pool.
   - ~~**1212 HealingBalms_Heal**~~ — **PORTE (#27-4d)**, et il ne relevait pas de cette route : c'est un
     SOIN, il passe par `_heal_candidates`. Les deux overrides annonces ne se valent pas —
     `$$MakeHealPredictions` a un corps IDENTIQUE au generique (recopie de hierarchie, aucune chaine
     propre) ; seul `$$CalculateCustomUtility` porte du comportement (`Half x U_heal` gate par
     `HasEffect(HealingBalms_ExtraCritDamage)`). Detail : section TRANCHE 4d.
   - **1053 DevoutPush** — sur ce build le playbook ne possede PLUS de corps propre (il PARTAGE
     `ALoki_NormalAttackPlaybook<T>` = `Fix64(1)`) : l'item #27 est vide de substance ; reste l'action
     « push » non modelisee, hors #27.
   - **1100 SorcerousFacade** — verrou distinct et toujours entier : cible ALLIEE. La route
     non-attaque ne le debloque pas (l'ability a un `damageProfile` et son masque `0x402` la fait
     VETO-er par `_is_attack_ability` depuis #217) ; il lui faut une route de ciblage ALLIE.
3. ~~**Porteur hors `--list-pool` au rank courant**~~ — **VERROU SUPPRIME (tranche 3)**. Le porteur
   `lineup` absent du catalogue de la seed BC se rajoute par `catalog_inject.py --units <id>` (#92,
   `BC.Units` ET `BC.Abilities`), et le runner le deploie normalement — fait pour bloodTerminator
   (1230), necroChronomancer (1226) et spaceWolfPriest (1212).
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
- **Chronometron (1226)** — A/B causal live `probe_27_4b_chronometron_ab.py`, board **MC1_67**, seed
  909, `--hp-target 85000`, porteur `necroChronomancer` amene par `catalog_inject.py`. Caster FIGE en
  (2,6) (il ne bouge dans aucun bras : `aiMovableTiles` rend 0 tuile apres son placement, donc le terme
  Tile est IDENTIQUE partout — mesure = 20.0). Seule variable : le nombre d'ennemis a `d <= 2`.
  L'ordre des appats est CALIBRE (le premier arrive sur la tuile a `pairUtility` FORTE) pour que le
  maximum des paires soit atteint des n=1 et ne bouge plus.

  | mesure | n=0 | n=1 | n=2 | 1 ennemi + 1 ALLIE |
  |---|---|---|---|---|
  | `pairUtility(69, orksWarboss)` natif | 0 | 12.756170448847115 | **12.756170448847115** | **12.756170448847115** |
  | cibles eligibles (RPC `abilityTargets`) | `[]` | `[79, 83]` | `[79, 81, 83]` | `[79, 83]` |
  | choix natif (`aiDryRunAllUnits`) | **rien** (FinishUnitTurn) | **69** | **1226** | **69** |
  | choix moteur | rien | 69 | **1226** | 69 |
  | moteur, custom force a 0 | rien | 69 | **69** (= divergence -> terme NECESSAIRE) | 69 |
  | moteur, ROUTE desactivee | rien | 69 | **69** (= divergence -> route NECESSAIRE) | 69 |
  | custom porte | 0 | 10 | 20 | 10 |

  - Les `pairUtility` natives sont **bit-identiques** de n=1 a `ally` -> confond de prediction MESURE
    et NUL (l'ability ne produit aucune prediction, et deplacer un appat ne change ni stats ni profil).
  - **LINEARITE PROUVEE** : n=1 ne bascule PAS, n=2 bascule. Un terme booleen (copie du 2e terme de
    DoomSiren) aurait bascule des n=1. Encadrement sans fitting (`u_action(69) = pair_max + Tile + 1`,
    `u_action(1226) = n*W + Tile`, meme tuile donc Tile s'annule) : `W < 13.7562` (n=1) et
    `2W > 13.7562` (n=2) => **6.8781 < W < 13.7562** ; le port rend 10.
  - **ALLIES IGNORES** : le bras de controle remplace le 2e ennemi par un ALLIE sur la MEME tuile — le
    natif REVIENT sur l'attaque normale. C'est ce qui separe `Enemies(...)` d'un compte d'unites.
  - **n=0** : `abilityTargets` natif rend `[]` -> le gate self-cast
    (`GetCasterNotAddedReason` -> `0x800`) est exerce, et le port le mirroir (`is_caster_added=False`).
  - **ROUTE NECESSAIRE** : le bras « route desactivee » (registre `NONATTACK_PLAYBOOKS` vide) rejoue la
    decision dans l'etat d'AVANT le port et rend 69 — c'est la preuve que 1226 ne passe par aucune
    autre voie, et donc que le deblocage du verrou 2 est bien ce qui produit l'accord.
- **Chronometron, ANCRAGE du compte** (`probe_27_4b_chronometron_ab.py --anchor --build --engine`,
  runner DEDIE ou le caster n'a pas encore bouge — un `act move` consomme son mouvement et rend le test
  impossible). Caster REEL en (1,0), appats en (0,2)/(1,3) : `d=3` de la position reelle, `d=2` de la
  tuile de MOVE (1,1). Les cibles eligibles sont NON VIDES (`[79, 83, 81, 77]`) : l'action 1226 est bien
  generable. Resultat : natif **69** (avec `MoveUnitMessage`), moteur **69** [MATCH] ; la variante
  concurrente « custom ancre sur la TUILE CANDIDATE », rejouee sur le MEME etat, rend **1226** ->
  l'hypothese est **REFUTEE PAR LE NATIF**. Le centre du selecteur est donc bien l'ENTITE (surcharge
  5-args), comme le decompile l'annonce.
- **Non-regression (garde d'agreement `engine_agreement_stages.py --build`, board MC1_67)** :
  seed **31337** — prediction **10/10**, utilite **10/10**, ability **13/13**, move **18/18** (100 %) ;
  seed **777** — prediction 9/12, utilite 12/12, ability **16/16**, move 16/17. Le delta du port est
  **NUL par construction** et pas seulement par mesure : `nonattack_candidates` boucle sur
  `NONATTACK_PLAYBOOKS` = {1226}, et les SEULS porteurs de Chronometron sont `necroChronomancer`
  [lineup] + 4 npc (`unit_map find --ability Chronometron`) — aucun n'est dans le roster de ces seeds.
- **Garde de forme OFFLINE** : `probe_custom_utility_27.py` couvre desormais 1226 — dispatch, presence
  dans `NONATTACK_PLAYBOOKS` (sans quoi le terme serait INERTE), linearite 0/W/2W/3W, exclusion du
  centre, exclusion de `d = range+1`, **invariance a la tuile candidate**, gate `is_caster_added` dans
  les deux sens, et `should_execute(0) == True`.
- **Garde LIVE** : `tests/engine/test_chronometron_decision_live.py` — 7 tests, **7 PASS** (163 s) :
  accord moteur/natif sur les 4 bras, linearite, bit-identite des paires, necessite du terme, necessite
  de la route, allies ignores, gate sans ennemi a portee.
- **Inventaire** : `probe_27_custom_utility_inventory.py` (balayage de vtable, 2 sources croisees),
  `probe_27_4b_chronometron_vtable.py` (slots `+0x318`/`+0x328`/`+0x338`/`+0x348` de 4 playbooks : c'est
  lui qui etablit que `ShouldExecute` par defaut rend `true`),
  `probe_27_slot_offsets.py` (les 7 playbooks hors 0x338), `probe_27_vtable_dump.py` (controle de
  bornes), `probe_27_residual_triage.py` (route de dispatch + porteurs), `probe_27_3_ability_names.py`
  (les 8 ids absents de la map des hooks).
- **ForwardObservers (1185)** — A/B causal live `probe_27_4c_forwardobservers_ab.py`, board **MC1_67**,
  seed 909, porteur GREFFE `tauCrisis.ActiveAbilities = [1185]`. Caster FIGE en (2,6) (son `act move`
  consomme son mouvement -> terme Tile IDENTIQUE partout, mesure = 20.0). Cibles a d=2 : `orksWarboss`
  (2,4) et `necroWarden` (2,8) ; l'ennemi tenu a l'ecart est en (6,0).

  | bras | etat | `pair_max` natif | pct(meilleure cible) | choix natif | choix moteur |
  |---|---|---|---|---|---|
  | B0 | mk=0, deux cibles pleines | 33.183694 | 1.0000 | **1185** @necroWarden | idem [MATCH] |
  | B1 | mk=0, necroWarden blessee | 35.535935 | 1.0000 | **1185** @**orksWarboss** | idem [MATCH] |
  | A1 | mk=1 | 35.535935 | 1.0000 | **1185** @orksWarboss | idem [MATCH] |
  | A2 | mk=1, SEULE la cible blessee reste a portee | 35.535935 | 0.8824 | **69** | idem [MATCH] |

  - **B0 -> B1 : le terme suit le RATIO de PV de la CIBLE.** Blesser la cible que le natif avait
    choisie le fait passer sur l'autre — et ce changement va **CONTRE l'ordre d'enumeration**
    (`abilityTargets` rend `[necroWarden, orksWarboss]`, keep-first STRICT), que suivrait tout terme
    CONSTANT ou BOOLEEN. C'est ce qui separe `RemainingPercentage * W` d'un `W` plat.
  - **A2 : bras DISCRIMINANT, les deux modeles predisent des choix OPPOSES sur le MEME etat.** Avec
    `pct = 0.8824`, `pair_max + 1 = 36.5359` et `W_B = 40` : le modele PROPORTIONNEL donne
    `40 x 0.8824 = 35.30 < 36.54` -> attaque normale ; un terme CONSTANT donnerait `40 > 36.54` ->
    1185. **Le natif rend 69** -> le modele constant est REFUTE PAR LE NATIF, pas ecarte par argument.
  - **Le terme Markerlight est GLOBAL** : dans A1/A2 l'ennemi marque est `astraSmnKell` — le summon
    intercepteur (`SwornProtector`) qui a pris le tir a la place de la cible visee. Il n'est NI la
    cible du tir, NI une cible eligible de 1185, NI a portee du caster, et il eteint quand meme le
    bonus de 200. Un port qui aurait teste « la cible porte-t-elle Markerlight » ne bascule pas ici.
  - **ENCADREMENT sans fitting** (`u_action(69) = pair_max + Tile + 1`, custom NormalAttack = +1 ;
    `u_action(1185, c) = A + W_B*pct(c) + Tile`, meme tuile donc Tile s'annule), balayage de 5 runners
    a `--hp-target` different :

    | runner | `--hp-target` | bras | mesure | inegalite |
    |---|---|---|---|---|
    | naturel | — | A1 | pair 54.652143, pct 1.0, natif **69** | `W_B < 55.6521` |
    | 12000 | 12000 | B0 | pair 199.983336, pct 1.0, natif **1185** | `W_A + W_B > 200.9833` |
    | 120000 | 120000 | A1 | pair 13.918601, pct 1.0, natif **1185** | `W_B > 14.9186` |
    | 47000 | 47000 | A1 | pair 35.535935, pct 1.0, natif **1185** | **`W_B > 36.5359`** |
    | 47000 | 47000 | A2 | pair 35.535935, pct 0.8824, natif **69** | **`W_B < 41.4060`** |
    | 41000 | 41000 | A1 | pair 40.736062, pct 1.0, natif **69** | `W_B < 41.7361` |

    => **36.5359 < W_B < 41.4060** ; le port rend **40**. Pour W_A, la ligne 12000 combinee a la borne
    sup de W_B donne **W_A > 159.577** ; le port rend **200** (borne SUPERIEURE non mesuree, cf. §Non
    couvert).
  - **Contre-epreuves** : custom force a 0 -> le moteur DIVERGE (il retombe sur `(69, necroWarden)`
    dans les bras ou le natif dit 1185) ; registre `NONATTACK_PLAYBOOKS` VIDE -> le moteur DIVERGE
    aussi (1185 n'entre par aucune autre voie : pas de `damageProfile`).
- **Garde de forme OFFLINE (1185)** : `probe_custom_utility_27.py` couvre le dispatch, la presence
  dans `NONATTACK_PLAYBOOKS` (sans quoi le terme serait INERTE), le scope ENNEMIS-ONLY du predicat (un
  ALLIE marque ne doit RIEN declencher), la separation des deux termes (mk=0 vs mk=1), la LINEARITE
  stricte sur 4 ratios (0 / 25 / 60 / 100 %), l'extinction propre quand les PV sont illisibles, et
  `should_execute(0) == True`.
- **Garde LIVE (1185)** : `tests/engine/test_forward_observers_decision_live.py` — 6 tests,
  **6 PASS** (37 s, session 28) : accord sur les 4 bras, booleen global du Markerlight, cible qui
  suit le ratio, bras A2 discriminant AVEC verification prealable que le montage SEPARE bien les
  deux modeles (`W_B * pct < pair_max + 1 < W_B` — sinon le test ECHOUE au lieu de passer a vide),
  necessite du terme, necessite de la route.
- **La correction #292 de `UTILITY_TYPE_NAMES` (37 entrees fausses) est SANS EFFET sur cette mesure
  — verifie, pas suppose.** Aucun chemin de #27-4c ne resout un nom d'utilite par RPC : les poids
  viennent de `engine.weights.load()` (seed BC sur disque + re-synthese depuis le gameconfig
  VIVANT), et cote natif de `BC.Utilities` re-synthetisee par `_load_seed_bc` — dans les deux cas
  des cles TEXTUELLES, jamais un ordinal `UtilityType`. Les seuls RPC du probe sont `decisionView`,
  `observeBattle`, `pairUtility`, `aiDryRunAllUnits`, `aiMovableTiles`, `abilityTargets` et
  `combatSnapshot` ; `aiUtilityTrace` (le consommateur de cette table) n'est pas utilise — il est
  d'ailleurs inoperant sur runner isole (cf. §« Ou l'utilite d'ACTION est OBSERVABLE »). Les enums
  renumerotes par #283 sont `EventTriggerType`, `UtilityType`, `StepType` et `DisplaceDirection` :
  **ni `EffectType` ni `ActiveAbilityType`**, les deux seuls dont ce port lit un ordinal (1122 et
  1185), et il les derive des tables versionnees.

### Non couvert (explicite)

- **Chronometron, la CIBLE choisie a custom egal.** Le terme est constant sur les cibles : a
  `custom` egal, c'est l'ORDRE d'enumeration qui tranche (keep-first STRICT). Le port consomme l'ordre
  du RPC `abilityTargets` ; le natif herite de celui de
  `IdunBattle.Core.Services.TileQuery$$IterateSurroundingTiles`. Les deux **coincident sur les montages
  mesures** (`[79, 81, 83]` -> 79 des deux cotes) mais l'identite des deux ordres n'est PAS etablie.
- **Chronometron, les deux termes positionnels non portes** : `CalculateCasterPositionUtility`
  (vtable `+0x348`) et `CalculateUtilityFromTilePrediction`. Leurs corps de BASE sont partages et non
  nommes ; aucun membre actuel de `NONATTACK_PLAYBOOKS` ne les override, donc ils sont hors du chemin
  exerce — mais ils ne sont pas mirrores.
- **Chronometron, le composite `UtilityAttackCase.Base`** n'est porte que par sa feuille Tile(7)
  (`tile_utility`), exactement comme la route d'attaque. C'est le meme residu que celui qui bloque
  MortisRound (1004), et il est PARTAGE par les deux routes — donc neutre dans une comparaison entre
  elles.
- **Chronometron, la cascade fine de ciblage** : `is_caster_added` mirroir la branche self-cast de
  `GetCasterNotAddedReason` (« au moins un ennemi a `range` »), pas la cascade
  `GetInvalidTargetReason` complete. Le masque de 1226 est permissif (`AllowObscuredTargetBy*`), donc
  le port reste un SUR-ENSEMBLE — degradation assumee et bornee a cette ability. En LIVE le point est
  sans objet : `ctx.ability_targets` est le RPC natif (mesure : `[]` au bras n=0).
<<<<<<< HEAD
- **La route non-attaque a DEUX membres** (1226, 1185). Les autres residus du groupe (1212, 1053)
  gardent chacun un verrou PROPRE, nomme ci-dessus ; ils n'ont pas ete enchaines.
- **ForwardObservers : le porteur REEL n'est pas confronte.** La mesure passe par une GREFFE de
  l'ability sur `tauCrisis`. Ce que la greffe NE couvre PAS : les stats, traits et l'arme du vrai
  porteur (`tauSmnStealthSuit` : `Camouflage`, `Infiltrate`, `Summon`, arme Pulse 4 coups) — donc
  l'INTERACTION du terme custom avec la prediction de degat de CE porteur precis. Le terme custom
  lui-meme n'en depend pas (il ne lit que `BC.Utilities`, l'etat Markerlight des ennemis et les PV de
  la cible). Debloqueur nomme : faire accepter les summons/npc par `buildNormalizedBC` (leur donner un
  chemin de stats explicite dans le RPC, au lieu de `IStatsFormula.StatsUsingProgressionIndexFor`).
- **ForwardObservers, borne SUPERIEURE de `W_A` (Markerlight) non mesuree.** Elle exigerait un bras
  mk=0 ou le natif RESTE sur l'attaque normale, donc `pair_max + 1 > W_A + W_B ~ 240` : le run le plus
  agressif teste (`--hp-target 12000`) plafonne a `pair_max = 199.98`. On a donc `W_A > 159.577`
  seulement — meme statut que Herald (`C > 34.22`).
- **ForwardObservers, le gate de PORTEE par TUILE.** `GetEligibleTargetsEntities` est recalcule PAR
  tuile candidate ; `eligible_targets` de la route consomme l'UNION rendue par `abilityTargets` (un
  SUR-ENSEMBLE). Sur un caster qui peut encore bouger, le port peut donc retenir une tuile d'ou le
  natif ne generait pas l'action pour cette cible. Le montage FIGE le caster (0 tuile de move), donc le
  point est hors du chemin mesure. `isSelfCasting = 0` -> aucun gate `GetCasterNotAddedReason` n'est
  invente (contrairement a 1226).
- **ForwardObservers, `EntityExtensions.HasEffect` n'est mirrore que sur son role CIBLE.** Le natif
  fait `IsOwnerOfEffect || IsTargetOfEffect` ; le canal `decisionView` attache a chaque unite son
  `EffectsOwnedComponent.ActiveEffectIds` (les effets qui S'APPLIQUENT a elle), pas ceux dont elle est
  la SOURCE. Degradation PERMISSIVE-EN-MOINS (le port peut rendre False la ou le natif rend True) : un
  ennemi qui aurait POSE un Markerlight sur un tiers sans en porter lui-meme ne serait pas compte.
  Idem pour `onlyActive` (le hook laisse tomber les effets `removed` / `!active`, le natif recoit un
  `Nullable<bool>` VIDE).
- **ForwardObservers, face COMBAT non portee.** `...ForwardObserversAbility$$ExecuteBehaviour`
  (`AddEffect(0x462) + AddEffect(0x575)`) n'entre PAS dans `ABILITY_CLASSES` — cette tranche ne couvre
  que la DECISION. Le masque (`0x200004002`, RANGE_FROM_CONFIG, `forceMeleeTarget = RangedBool.True`)
  et l'`AbilityAttackType` (`2 = Others`) sont RE-lus et consignes dans la docstring du playbook pour
  que ce port-la parte d'une lecture, pas d'une devinette.
- **La route non-attaque a DEUX membres** (1226, 1185). Le residu restant du groupe (1053) garde son
  verrou PROPRE, nomme ci-dessus. (1212, qu'on y rangeait, n'en relevait pas : c'est un soin, il entre
  par `_heal_candidates` — cf. TRANCHE 4d.)

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

**Le corps par DEFAUT d'un virtuel ne se lit pas dans la table — et l'intuition est souvent INVERSEE.**
`ShouldExecute` a trois proprietaires nommes dans `methods.tsv`, tous des comparaisons `utility > 0` ou
des predicats metier ; on en conclut naturellement que « le defaut, c'est `> 0` ». **FAUX** : le defaut
est `return true`, et ces trois-la sont les OVERRIDES. La raison est structurelle — un `return true`
est un corps trivial (`mov al,1 ; ret`), donc DEDUPLIQUE par IL2CPP et nomme sur UN SEUL proprietaire
arbitraire (ici `UnityEngine.U2D.IK.Solver2D$$DoValidate`). Les corps NON triviaux, eux, sont tous
nommes. **La table sur-represente donc systematiquement les overrides « riches » et cache le defaut
« pauvre ».** Ce qui tranche : le SLOT DE VTABLE sur plusieurs classes SŒURS (si quatre playbooks sans
rapport pointent sur le meme corps, c'est le defaut) ; et l'identification du corps trivial se fait en
le decompilant (`return 1` / `return 0`), pas en lisant son nom. Cout : un probe de 100 lignes
(`probe_27_4b_chronometron_vtable.py`). Sans lui, le port aurait recopie un gate `u > 0` — et
Chronometron, dont l'utilite de prediction est nulle par nature, n'aurait JAMAIS ete jouee.

**Un bras d'A/B qui « ne bascule pas » ne prouve rien tant qu'on n'a pas montre que l'hypothese
CONCURRENTE, elle, aurait bascule.** Sur l'ancrage de Chronometron (position reelle du caster vs tuile
candidate), le natif a joue l'attaque normale. C'est compatible avec « le custom vaut 0 » — mais aussi
avec « le custom vaut 20 et perd quand meme ». La parade coute trois lignes : rejouer la MEME decision
moteur avec la variante concurrente branchee (ici un `calculate_custom_utility` ancre sur
`caster_tile`). Elle rend **1226** ; le natif rend 69 ; l'hypothese est REFUTEE PAR LE NATIF, et le
bras devient une mesure. Sans ce controle, le probe affichait deja « ancrage CONFIRME » — sur rien.

**Un `act move` consomme le MOUVEMENT de l'unite : deplacer le caster detruit son sweep de tuiles.**
Apres placement, `aiMovableTiles` rend **0 tuile** pour lui — pratique pour isoler un terme (le terme
Tile devient constant et s'annule dans toutes les inegalites), FATAL pour tester quoi que ce soit qui
depende de la tuile candidate. Les deux besoins exigent donc DEUX runners : l'un ou le caster est place
a la main (A/B du terme), l'autre ou il reste a son spawn avec son mouvement intact (test d'ancrage).
Un test d'ancrage joue sur le premier rend « aucune cible eligible » et se lit comme une confirmation.

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
