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
| `MassDriverAcceleratorPlaybook` | MassDriverAccelerator (1222) | votanChampion `Kimm` [lineup] | oui (DirectDamage) | **PORTE (#27-r1) — NO-OP NATIF** : le selecteur est ancre sur `Owner`, que ce corps-la laisse NULL -> le terme vaut `Fix64(0)` en toute configuration. Cf. §TRANCHE 4g |
| `ResurrectionOrbPlaybook` | ResurrectionOrb (1009) | necroOverlord `Anuphet` [lineup] (+ 5 npc) | **NON** | **PORTE** (#289) — route non-attaque ; `u = 90 x [nResurrect>0 ET nTiles>0] + 10 x numSummons` |

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

### SorcerousFacade (1100) — le SECOND membre de cette route, et le dernier verrou de la famille

| Ability (id) | Symbole | Formule mirroir | Porteur | Validation |
|---|---|---|---|---|
| **SorcerousFacade** (1100) | `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility` (slot **+0x338**, mesure) | `GetUtility(UtilityType.Tile).EvaluateMovement(case(caster, GetMainTile(target)))` **-** `GetUtility(UtilityType.Tile).EvaluateMovement(case(caster, casterPosition))` = `Tile(tuile de la CIBLE) - Tile(tuile candidate)`. Terme POSITION- **et** CIBLE-dependant ; **aucun poids BC** (c'est une difference de composite Tile). Comme la route ajoute `+ Tile(tuile candidate)`, l'utilite d'action porte exactement `Tile(tuile de la CIBLE)` : la tuile que le caster occupera APRES l'echange. Le playbook override AUSSI `ShouldExecute` (+0x328) et `MakeDamagePredictions` (+0x358) — cf. §`SorcerousFacade (1100)`. | thousTzaangor `Yazaghor` + l'allie Psyker thousSorcerer `Thaumachus` [hero, **les deux dans `--list-pool`**, aucun `catalog_inject`] | **A/B causal live** (`probe_27_4e_facade_ab.py`, board MC1_67, 2 configurations, 5 bras) : caster FIGE, cible collee a d=1, et SEUL l'allie bouge sur 4 tuiles d'elevations 1/2/3/4 **toutes a la meme distance 4 du caster**. Natif = moteur dans les 5 bras ; etage prediction **bit-identique** (27.340392069891095 / 41.01058810483664). Detail en §Validation. |

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
   faire varier `U`, sans quoi un « custom constant » resterait indiscernable. C'est ce que fait le
   montage a quatre bras de la section « Le COEFFICIENT est discrimine par la mesure (#286) ».

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

**Masque de ciblage, pour qui portera la face COMBAT** (lu, pas recopie d'une fiche) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility$$.ctor` appelle la surcharge
**a 7 arguments** de `IdunBattle.Core.Services.TargetingOptions$$.ctor`
(`this, isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
getDynamicInvalidTargetReason` — dont l'implementation ecrit `isSelfCasting` en `+0x00`, `range` (24
octets) en `+0x08`, `forceMeleeTarget` en `+0x20`, `rules` en `+0x28`) avec
`isSelfCasting = 0`, `forceMeleeTarget = 2`, **`rules = 0x8402`**, et les deux delegues a `null`.
Le `range` est un bloc de 24 octets **recopie d'un champ statique** (le meme piege de forme que les
presets de `TargetingOptions$$.cctor`) : il n'est PAS un litteral et n'a pas ete resolu ici.
CONSEQUENCE OUVERTE, a mesurer live et non a supposer : le generateur offline filtre les tuiles
candidates a `HEAL_RANGE = 1` (`_heal_candidates`) ; si la portee effective vaut 2, le port perd des
tuiles de cast (degradation RESTRICTIVE, pas permissive). L'enumeration de CIBLES, elle, vient du RPC
natif `abilityTargets` et n'est pas concernee. Test discriminant : poser un allie blesse a distance 2
de Baldr et regarder si `abilityTargets` le rend `fromHere`.

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

### Validation live (#27-4c)

**Etage 1 — MAGNITUDE, canal SCALAIRE `pairUtility`.** Baldr injecte par
`catalog_inject.py --units spaceWolfPriest` (le porteur est `lineup` mais hors catalogue de la seed
BC ; le pool passe de 97 a 98), board MC1_67. Attack 2512, arme 3 coups. Cible `spaceBlackmane` a
5243/20000, soit `missing` = 14757 — **strictement au-dessus des deux magnitudes candidates**, seul
regime qui tranche (en dessous, les deux saturent a `missing` et l'A/B ne mesure rien) :

| hypothese | montant | utilite predite | natif |
|---|---|---|---|
| **ARME** `2512 x 3` | 7536 | 37.6781160942 | **37.67811609432101** |
| config `hpToHeal[50] x 180 %` | 4986 | 24.9287535623 | — |

Reproduit apres reinject (session suivante, meme build) sur un autre montage : 37.67811609432101.
Cible a PV pleins -> `pairUtility` = **0** (`MaxFillUp` nul, `ShouldExecute` refuse), et le port rend
`None` au meme endroit.

**Seconde source, independante du scalaire** : `aiPlaybookPredict.healEvents` rend
`{"targetId": 85, "targetHpBefore": 7599, "healAmount": 7536, "probability": 1}` — ce qui confirme d'un
seul coup (a) la magnitude ARME, (b) la forme `CONCAT44(fill, currentHealth)` de la struct de 8 octets
(`targetHpBefore` = le mot bas, `healAmount` = le mot haut), (c) la probabilite `Fix64(1)` du
`Nullable` vide, et (d) **qu'il n'y a qu'UN SEUL event** — donc que la somme du CustomUtility porte sur
une seule cible, ce que le port supposait et qui est desormais mesure.

> ⚠ **Ce canal-la est SAIN, et il ne faut pas le confondre avec celui du backlog `#276-r1`.** Les deux
> familles ont des decodeurs DISTINCTS dans `frida/hooks/features/ai-step/playbook-predict.ts` :
> - `readHealEvent` lit un `ProbableHealEvent` de stride `0x18` dont le `HealPredictionResult` est
>   INLINE sur **8 octets** a `+0x08..+0x10` (`targetHpBefore@+0x08`, `healAmount@+0x0c`) : il ne lit
>   RIEN hors struct, et c'est exactement la forme que `ProbableHealEvent$$.ctor` +
>   `DamagePrediction$$PredictHeal` imposent.
> - `decodeRepairDict`, lui, suppose un `RepairPrediction` de **16 octets / 4 ints**
>   (`currentHealth`, `currentArmor`, `hpFill`, `armorFill`) alors que `PredictRepair` rend la MEME
>   struct de 8 octets : c'est LUI qui deborde (`hpFill`/`armorFill` sont hors struct, et le champ
>   etiquete `targetArmorBefore` est en realite le `fillUp`). Defaut reel, non corrige a ce jour.
>
> La mesure ci-dessus est en outre corroboree par deux sources qui ne passent par aucun decodeur de
> struct : `targetHpBefore` = 7599 = le `hp` d'`observeBattle`, et `healAmount` = 7536 = le `fill` que
> `pairUtility` = 37.678 implique par `fill/(hpMax+1)x100`. **Le canal de reference reste malgre tout
> le scalaire `pairUtility`** — c'est lui qui porte les conclusions ; `healEvents` ne fait que
> corroborer.

**Etage 2 — le CUSTOM, A/B causal sur le CHOIX natif** (`aiDryRunAllUnits`, read-only). Le terme
n'apparait pas dans `pairUtility` ; on l'exerce donc par le seul levier qui l'annule, l'effet
`HealingBalms_ExtraCritDamage`. Montage FIGE (ennemis relegues hors de portee apres la phase de
blessure, `RitesOfMorkai` passe en cooldown pour que 1212 soit l'ability retenue), `--hp-player 60000` :

| bras | u85 `adeptCanoness` | u87 `spaceStormcaller` | choix natif |
|---|---|---|---|
| **CONTROLE** | `pairUtility` = **12.55979067645967**, non buffe, 16920/60000 | `pairUtility` = **12.55979067645967**, non buffe, **39127/60000** | **u85**, sans deplacement |
| **TEST** | `pairUtility` = **12.55979067645967**, **buffe**, 25379/60000 | `pairUtility` = **12.55979067645967**, non buffe, **39127/60000** | **u87**, move (0,2) |

Les **quatre** utilites de paire sont BIT-IDENTIQUES -> confond de prediction MESURE et NUL. `u87` est
**strictement inchange** entre les deux bras (memes PV, meme tuile, non buffe) : le seul levier qui
bouge est l'effet sur u85. Le natif renonce a sa cible et se DEPLACE pour aller soigner une cible
d'utilite de paire identique mais non buffee.

**Contre-epreuves MOTEUR** sur ce meme etat (generateur `_heal_candidates`, comparaison par
`full = pred + tile_utility`) :

| bras | cible retenue | `pred` |
|---|---|---|
| port tel quel | **u87, to=(0,2)** — cible ET tuile identiques au natif | 18.839686 = `1.5 x 12.559791` |
| `calculate_custom_utility_from_heal` force a 0 | u85, sans move — **DIVERGE** | 12.559791 |
| 1212 retire de `HEAL_PLAYBOOKS` | u85, sans move — **DIVERGE** | 12.559791 |

Le terme de tuile vaut **30.0 pour les deux options** (`42.559791 - 12.559791` et
`48.839686 - 18.839686`) : le deplacement ne coute rien ici, la bascule est donc integralement portee
par le custom.

**Portee du cast — question ouverte de la passe precedente, FERMEE par mesure.** `abilityTargets`
distingue `targets` (superset, deplacement inclus) de `fromHere` (cast immediat). Baldr en (1,0),
allie en (0,1) = distance 2 : present dans `targets`, **absent de `fromHere`**. Le meme allie ramene
en (2,0) = distance 1 y **entre**. Le filtre `HEAL_RANGE = 1` du generateur est donc CORRECT — il n'y
a pas d'ecart de port sur cet axe. (Le `range` du ctor reste un bloc de 24 octets recopie d'un
statique, non resolu offline ; c'est la mesure qui tranche, pas la lecture.)

**Piege de mesure rencontre, et il vaut au-dela de cet item** : un second montage a ete ECARTE parce
que `pairUtility` y rendait **37.678 sur une cible a PV pleins** — valeur incoherente avec l'etat
observe, et qui re-mesuree quelques instants plus tard vaut **0**. C'est une lecture de CACHE perime
(`CachedDamagePredictionQuery`) juste apres une mutation. Regle : **toujours recouper une utilite de
paire avec l'etat de PV du meme instant** ; une valeur qui ne s'explique pas par `min(amount,
missing)/(maxHP+1) x 100` est un artefact, pas une mesure.

### Le COEFFICIENT est discrimine par la mesure (#286) — deux ratios x deux niveaux

L'A/B ci-dessus etablit que le terme EXISTE et que son gate est bien l'effet ; il ne dit rien de sa
FORME, parce que ses deux cibles ont une utilite de soin BIT-IDENTIQUE (12.55979067645967 des deux
cotes) : sur un ecart nul, tout terme strictement positif — y compris une constante — fait basculer
le natif de la meme facon. Le montage suivant (`probe_286_healingbalms_coefficient.py`) leve cela en
opposant deux cibles a utilites DIFFERENTES, sur deux ratios x deux niveaux.

**Le levier, et pourquoi il echappe aux deux pieges de la passe precedente.** `U_heal` vaut
`min(healAmount, missing) / (hpMax + 1) x 100`. En regime NON SATURE (`missing > healAmount`) le
numerateur est CONSTANT : `U` ne depend plus que de **`hpMax`**. On pilote donc niveaux et ratios par
les `Health` du BC, jamais par les degats. Consequences directes :

- piloter `missing` par les degats etait trop grossier a ce regime (fenetres de ~2500 PV, soin par pas
  de 30000, plus le soin RETARDE de 4986 pose par le passif) — ici `missing` n'entre PLUS dans `U` :
  le soin retarde et les coups adverses ne deplacent rien, ils ne consomment que de la marge de
  non-saturation, dimensionnee a plus d'un soin complet apres le cast qui pose le buff ;
- la lecture de CACHE perime de `pairUtility` ne se contourne pas en re-lisant : chaque valeur est
  RECOUPEE avec l'etat de PV du meme instant (`min(amt, missing)/(hpMax+1) x 100`, tolerance `1e-6`
  — le natif calcule en Fix64 et arrondit a ~1e-8, trois ordres sous ce que le cache produit) et toute
  valeur inexplicable est REJETEE au lieu d'etre re-tentee.

**Montage** (board MC1_67, seed 4242, Baldr `spaceWolfPriest` injecte par `catalog_inject`) :

- caster `Damage = 10000`, arme 3 coups -> `healAmount = 30000` (verifie `combatSnapshot`) ;
  `ActiveAbilities = []` (retire `RitesOfMorkai` ; 1212 reste, GRANTED par le passif) ; PV PLEINS,
  donc `pairUtility(caster -> caster) = 0` et le self-cast ne concurrence pas les deux cibles ;
- **caster `Movement = 0`** : `aiMovableTiles` rend **0 tuile** (controle qui LEVE), donc une seule
  tuile candidate et un terme de tuile rigoureusement COMMUN aux deux options — la bascule ne peut
  venir que du terme custom ;
- adversaire `blackAbaddon` **seul**, `Movement = 0`, `Damage = 1`, `Health = 10^8`. Le PV enorme
  rend l'utilite d'attaque (~0.03) negligeable devant les utilites de soin mesurees.
  **`blackTerminator` est EXCLU** : son `TeleportStrike` le ramene au contact quel que soit son
  `Movement`, et le natif proposait alors `Move + NormalAttack(69)` au lieu du soin (mesure) ;
- le buff n'a qu'un seul poseur possible — le cast de 1212 lui-meme. Le bras se joue donc en deux
  tours : cast sur A au tour N, lecture du CHOIX au tour N+1. 1212 n'a pas de cooldown
  (`cooldown: null`) et `HealingBalms_ExtraCritDamage` est toujours porte au tour N+1 ; l'effet
  `HealingBalms`, lui, s'est consomme en soignant 4986 = `hpToHeal[50] = 2770 x 180 %`.

**Les huit bras.** A porte le gate (custom annule -> `u_A = U_A`), B ne le porte pas
(`u_B = (1 + c) U_B`) ; `r = U_A / U_B` ; la derniere colonne est la borne qu'imposerait une
CONSTANTE additive `k` :

| bras | niveau | `hpMax` A / B | `U_A` | `U_B` | `r` mesure | natif | borne sur `c` | borne sur `k` |
|---|---|---|---|---|---|---|---|---|
| 1 | haut | 80 000 / 112 000 | 37.499531265 | 26.785475132 | 1.399995 | **B** | `c > 0.399995` | `k > 10.714056` |
| 2 | haut | 80 000 / 128 000 | 37.499531265 | 23.437316902 | 1.599993 | **A** | `c < 0.599993` | `k < 14.062214` |
| 3 | bas | 320 000 / 448 000 | 9.374970710 | 6.696413620 | 1.399999 | **B** | `c > 0.399999` | `k > 2.678557` |
| 4 | bas | 320 000 / 512 000 | 9.374970710 | 5.859363545 | 1.599998 | **A** | `c < 0.599998` | `k < 3.515607` |
| 5 | haut | 80 000 / 119 200 | 37.499531265 | 25.167574105 | 1.489994 | **B** | `c > 0.489994` | `k > 12.331957` |
| 6 | haut | 80 000 / 120 801 | 37.499531265 | 24.834025931 | 1.510006 | **A** | `c < 0.510006` | `k < 12.665505` |
| 7 | haut | 80 000 / 119 992 | 37.499531265 | 25.001458428 | 1.499894 | **B** | `c > 0.499894` | `k > 12.498073` |
| 8 | haut | 80 000 / 120 008 | 37.499531265 | 24.998125131 | 1.500094 | **A** | `c < 0.500094` | `k < 12.501406` |

Trois conclusions, et elles sont de nature differente :

1. **`0.499894 < c < 0.500094`** (bras 7 et 8, ratios a +-1e-4 de 1.5, marges d'utilite ~0.0025
   point contre un arrondi Fix64 de ~1e-8). Ce n'est plus une exclusion de valeurs rondes, c'est une
   DETERMINATION du coefficient a 1e-4 pres : `Half` est la seule valeur qui survit.
2. **La proportionnalite** : les bras 1+2 (niveau haut) et 3+4 (niveau bas) rendent le MEME
   encadrement `0.400 < c < 0.600` a des utilites separees d'un facteur 4. Un terme qui ne serait pas
   proportionnel a `U` ne pourrait pas rendre les memes bornes aux deux niveaux.
3. **La forme ADDITIVE constante est REFUTEE par contradiction** : le bras 1 exige `k > 10.714056`,
   le bras 4 exige `k < 3.515607`. Aucune constante ne satisfait les deux — et c'est desormais une
   MESURE, plus seulement une lecture de `Fix64$$FastMul`.

**Contre-epreuves MOTEUR** (meme etat, terme custom du port remplace forme par forme) — chaque bras
doit SEPARER, sinon il ne mesure rien :

| bras | natif | `Half` (port) | `0` | `Quarter` | `One` | `k = 12.0` |
|---|---|---|---|---|---|---|
| 1 | B | **B** | A | A | B | B |
| 2 | A | **A** | A | A | B | A |
| 3 | B | **B** | A | A | B | B |
| 4 | A | **A** | A | A | B | **B** |
| 5 | B | **B** | A | A | B | **A** |
| 6 | A | **A** | A | A | B | A |
| 7 | B | **B** | A | A | B | **A** |
| 8 | A | **A** | A | A | B | A |

Le port suit le natif dans les HUIT bras ; `0` et `Quarter` divergent a chaque bras « B », `One` a
chaque bras « A ». La constante `k = 12.0`, calibree pour passer le niveau haut, casse aux bras 4, 5
et 7 : c'est la contradiction ci-dessus, rendue visible cote moteur.

**Generalisation** : les bras 7 et 8 rejoues avec un AUTRE couple de cibles
(`spaceStormcaller` / `spaceBlackmane`), un AUTRE board (MC1_63) et un AUTRE seed (909) rendent le
MEME encadrement (`c > 0.499894` / `c < 0.500094`). Le verdict ne depend ni de la geometrie, ni du
tirage, ni de l'identite des cibles.

**Le controle de montage qui a manque, et ce qu'il a coute** : ce meme bras de generalisation, joue
AVANT que le probe ne verifie l'appartenance des deux cibles a `abilityTargets.fromHere`, rendait
« natif = A » — et TOUTES les formes du port rendaient A, `One` comprise. Cause : sur MC1_63 les
spawns ne mettaient pas `spaceBlackmane` a portee de cast, donc le natif n'avait qu'UNE option et sa
preference ne parlait pas du terme custom. Le probe AMENE desormais les cibles au contact
(`place_targets`, mirror de la doctrine « on pilote les positions ») et LEVE si l'une d'elles reste
hors `fromHere`, a l'entree comme au tour d'observation. **Un bras ou le natif n'a pas le choix rend
un verdict parfaitement lisible et entierement vide.**

**Outil de mesure ajoute pour ce montage** : `rl_duel build --unit-stat "VisualId:Champ=Valeur;…"`.
`--hp-player`/`--dmg-target` ne savent forcer qu'une valeur UNIQUE sur tout un camp, ce qui ne peut
par construction pas produire deux niveaux d'utilite entre deux allies. Le patch s'applique au meme
endroit qu'eux, c'est-a-dire au BC **deja normalise** : `buildNormalizedBC` RECALCULE `Health`/`Damage`
au rank cible, donc patcher le seed BC en amont ne sert a rien (mesure : PV du seed ecrases,
9035/9035 au lieu des 200000 demandes).

Garde live : `scripts/python/tests/engine/test_healing_balms_custom_coefficient_live.py` — quatre
bras, les deux PINCES (7, 8 : la valeur) et les deux NIVEAUX (1, 4 : la refutation de l'additif).

### Non couvert (explicite)

- **Le coefficient est encadre a 1e-4, pas egale.** La mesure borne `0.499894 < c < 0.500094` ; c'est
  le decompile (`Fix64.<statics+0x30>` ecrit par `FixMath.NET.Fix64$$.cctor` =
  `op_Division(One, Fix64(2))`) qui donne la valeur EXACTE. Resserrer encore ne demande que des
  ratios plus proches de 1.5 — le plancher est la granularite ENTIERE des `hpMax` (a `hpA = 80000`,
  un pas de 1 PV sur `hpB` deplace le ratio de ~1.2e-5), pas le bruit de mesure.
- **Un seul porteur exerce.** `spaceWolfPriest` est le seul hero qui porte le passif `HealingBalms`,
  donc la seule voie vers 1212 ; la mesure ne dit rien d'un eventuel second porteur d'un futur build.
- **L'adversaire est neutralise** (`Movement = 0`, `Damage = 1`, `Health = 10^8`) pour que le choix
  du caster se joue entre ses deux seules options de soin. Le montage ne dit donc rien de la
  concurrence entre 1212 et une ATTAQUE a portee — regime ou le terme custom pese aussi, et qui
  reste a exercer si un miss d'agreement l'y fait surface.
- **Les bonus-soin d'effets accumules par `PredictHeal`** avant les caps (boucle sur les effets du
  caster, slot d'interface `0x29`) ne sont pas portes — inertes sur les porteurs exerces.
- **Le cap de groupe** (`GetGroupUnitHealLimit`) reste inerte : `MakeHealPredictions` passe
  `scope = 0`, ce qui est desormais lu au call-site et non suppose.
- **La face COMBAT de 1212** n'est pas portee (l'ability est absente d'`ABILITY_CLASSES`) : cette
  tranche ne couvre que la face DECISION. Son masque de ciblage est consigne ci-dessus pour qui la
  portera.
## TRANCHE 4f (2026-07-30) — Stikkbomb (1051) : le VERROU 3 tombe

Le verrou 3 s'enonçait « `GenerateMultiHitAttackPredictions` sur un SOUS-SET de cibles ». La RE
montre que le sous-set n'est pas le probleme : c'est **QUI recoit la prediction** qui ne se devine
pas.

### Ce que le decompile dit — les DEUX faces sont le meme code, `IsFriend` inverse

`IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility`, relu VERBATIM sur
`rnca9r7q6c` :

```
formula = DSLFormulas.Get(GetVariableForLevel(config, 0xc = minDmg));   // == Direct(minDmg)
hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2);
profile = GetDamageProfile(config);
sel     = StikkbombAbility.GetAdjacentDamageTargets();
preds   = new List<ProbableDamageEvent>();
foreach (u in TargetsSelector.SelectUniqueUnits(sel, AbilityEntities(Target = target), 3))
    if (UnitExtensions.IsFriend(u, caster, state))                      // <-- LE SOUS-SET
        preds.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                            <selecteur Target>, formula, hits2, profile, null, null) );
u = Fix64.Zero;
foreach (p in preds) u = Fix64.op_Addition(u, CalculateUtilityFromDamageEvent(p, caster, casterPosition));
return Fix64.op_UnaryNegation(u);
```

et `...StikkbombPlaybook$$MakeDamagePredictions` est le MEME corps avec `if (!IsFriend(...))` et
`GetNumberConstant(0x2f = nrOfHits)` pour l'event principal. Trois points qui ne se devinent pas :

1. **Le SOUS-SET est declaratif, le TRI est imperatif.** Le selecteur
   `...StikkbombAbility$$GetAdjacentDamageTargets` (corps PARTAGE, seul proprietaire nomme
   `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetAdjacentDamageTargets`,
   8 users) est un arbre `DSLSelectors.AdjacentUnits(Target, unique: 1, sel: 3)` =
   `Units(AdjacentTiles(Target), unique, sel) - Target`, **sans filtre d'equipe**. C'est le MEME
   artefact que la face COMBAT : `...StikkbombAbility$$ExecuteBehaviour` passe ce meme selecteur a
   son 2e `AttackWithAttackDamage`, et il est deja porte
   (`runner/abilities/loki/splash.py::stikkbomb_tree` -> `Alive(AdjacentUnits(TargetTile()))`,
   friendly-fire inclus, #213). Le tri ami/ennemi, lui, n'est PAS un noeud : c'est un `foreach` +
   `UnitExtensions.IsFriend` DANS le playbook. **Classification : MIXTE** — et c'est une TROISIEME
   reponse, differente des deux tranches precedentes (Chronometron : selecteur declaratif partage,
   aucun filtre ; ForwardObservers : 100 % imperatif, aucun artefact partage). Le port evalue donc
   le meme ENSEMBLE que la face combat et n'ecrit a la main que le predicat.
   `IsFriend(u, caster, state)` compare `GetCurrentPlayer(u).<0x20>.<0x24>` a celui du caster :
   le CASTER est son propre ami et compte s'il est lui-meme adjacent a la cible.
2. **Chaque membre du sous-set produit une prediction sur la CIBLE PRINCIPALE, pas sur lui-meme.**
   Le 4e argument de `GenerateMultiHitAttackPredictions` est `target`. Ce n'est pas une lecture
   optimiste du decompile : c'est verifie a l'ASSEMBLEUR. Dans `CalculateCustomUtility` le
   call-site charge `mov r9,[rsp+0x578]` ; le prologue ecrit `mov rax,rsp ; mov [rax+0x20],r9`
   (home slot du 4e parametre) puis `7 x push` + `sub rsp,0x520`, donc
   `rsp_courant + 0x578 == rsp_entree + 0x20` = ce home slot, jamais reecrit. Meme lecture dans
   `MakeDamagePredictions` (`mov r9,[rsp+0x4a8]`, `- 0x38 - 0x450`). Or dans
   `...ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` le `param_4` ne sert qu'a peupler
   le contexte `AbilityEntities` (`Target` + `GetTiles(target)`) : ce sont les entites rendues par
   le SELECTEUR `param_5` qui recoivent les predictions — et `param_5` vaut ici le selecteur
   `Target` (champ `DSLSelectors@0x60`, le meme que `AttackWithAttackDamage` recoit pour l'attaque
   principale dans `ExecuteBehaviour`). La liste vaut donc `[target]` a chaque tour de boucle.
   ⇒ **le membre du sous-set ne determine QUE le NOMBRE d'events** ; leur contenu est invariant.
   C'est un quirk natif (l'intention lisible etait de predire les degats infliges aux amis) — on
   mirroir le code, pas l'intention. **MESURE LIVE** (bras `foe`, ci-dessous) : mettre un ENNEMI au
   contact de la cible fait passer `pairUtility(1051, cible)` de **16.041060** a **24.069251**,
   soit **+8.0282** — a comparer a la moitie de la paire de la CIBLE (**8.0205**, 1 coup au lieu de
   2) et a celle du VOISIN (**0.5504**). L'event porte sur la cible, et l'ecart residuel (0.0077)
   est la non-linearite du composite Damage, pas une autre entite.
3. **Le signe vient du `op_UnaryNegation` FINAL.** L'event porte la CIBLE (un ennemi) ->
   `CalculateUtilityFromDamageEvent` rend une utilite POSITIVE, que le playbook nie. Poser
   `friendly=True` sur l'event ET negger donnerait le signe INVERSE.

Magnitude : le terme vaut `-n x U(nrOfHits_2 coups sur la cible)` la ou l'utilite de paire vaut
`U(nrOfHits coups)`. Config 1051 : `nrOfHits = 2`, `nrOfHits_2 = 1` -> **un seul ami colle a la
cible ampute la moitie de la valeur de l'action**, deux l'annulent. Ce n'est pas un biais de rang.
**AUCUN poids `BC.Utilities` n'intervient** — ce custom-ci n'appelle pas `GetUtilityValue`.

### Ce que le port ajoute, et pourquoi la PREDICTION en fait partie

| Artefact natif | Port |
|---|---|
| `StikkbombPlaybook$$MakeDamagePredictions`, entrees de l'event principal | `prediction/abilities.py::_stikkbomb_inputs` (registre `_MAKE_DMG_INPUT_OVERRIDES[1051]`) : **base = `minDmg` SEUL** (`DSLFormulas.Get(0xc)` a le MEME corps que `DSLFormulas.Direct` — meme mold que #173 HellfireShells / #57e GreatFrostAxe) et **hits = `nrOfHits` LITTERAL** (le chemin generique passait par `get_special_hits`, qui AJOUTE la stat `ExtraHits`) |
| l'appel `GenerateMultiHitAttackPredictions(..., target, <Target>, Get(minDmg), 0x32, ...)`, identique dans les deux faces | `prediction/abilities.py::make_secondary_multihit_event` — **un seul foyer**, consomme par les DEUX faces du playbook 1051 **et par `PlasmaGrenadePlaybook$$CalculateCustomUtility` (1098)**, dont le call-site a les MEMES 4 entrees (renomme en #27-4g : `make_stikkbomb_splash_event` n'etait plus un nom vrai) |
| la boucle `!IsFriend` de `MakeDamagePredictions` | `StikkbombPlaybook.make_damage_predictions` : `events + [ev] * n_ennemis_adjacents` |
| la boucle `IsFriend` + negation de `CalculateCustomUtility` | `StikkbombPlaybook.calculate_custom_utility` : `-n_amis_adjacents * U(ev)` |

La face PREDICTION n'est pas un « pendant que j'y suis » : sans elle l'utilite de paire offline ne
peut pas etre confrontee a la native (base avg au lieu de minDmg), et le bras `foe` de l'A/B ferait
diverger le moteur pour une raison etrangere au custom. C'est le MEME artefact natif, lu au meme
call-site.

### Validation — A/B causal live, 7 bras

`probe_27_4f_stikkbomb_ab.py --build --engine` (board MC1_67, seed 909, `--armor-target 3000`),
garde `tests/engine/test_stikkbomb_decision_live.py`. Caster en (3,4) ; deux cibles a distance 2 et
distantes de 4 : T_high = astraOrdnance (pair 16.041060), T_low = necroWarden (pair 12.262825) ;
les appats AMIS occupent des voisins de la cible visee, tous a distance 3 du caster et 5 de l'autre
cible (ils ne changent l'adjacence d'aucune autre entite).

| bras | montage | natif | moteur | custom moteur (T_high / T_low) |
|---|---|---|---|---|
| n=0 | aucun ami adjacent | 1051 -> T_high | idem | 0 / 0 |
| n=1 | 1 ami sur T_high | 1051 -> **T_low** | idem | **-8.020530** / 0 |
| n=2 | 2 amis sur T_high | 1051 -> T_low | idem | **-16.041060** / 0 |
| bal1 | 1 ami sur CHAQUE cible | 1051 -> T_high | idem | -8.020530 / -6.131413 |
| bal2 | 2 amis sur T_high, 1 sur T_low | 1051 -> **T_low** | idem | -16.041060 / -6.131413 |
| ally-far | les 3 amis repartent loin | 1051 -> T_high | idem | 0 / 0 |
| foe | 1 ENNEMI (pas un ami) adjacent a T_high | 1051 -> T_high | idem | 0 / 0 |

- **EXERCICE PROUVE** : le natif emet `ActiveAbilityMessage(1051)` dans les SEPT bras. Le probe
  echoue explicitement sinon — et c'est arrive : avec le greffon `orksKillaKan` (arme Projectile
  r3) le natif jouait son attaque normale partout (`pair69 = 59.94` contre `pair1051 = 28.88`), les
  sept bras « d'accord » sans rien mesurer. D'ou le greffon MELEE a arme `Physical` (PiercingRatio
  1) + `--armor-target` : la normale tombe a `pair69 = 0` et 1051 (Blast, PiercingRatio 15) reste.
- **Confond de prediction MESURE et NUL** : les six `pairUtility` natives sont BIT-IDENTIQUES sur
  tous les bras ou seuls des AMIS bougent (un ami n'ajoute aucun event ; seul un ENNEMI en ajoute,
  cf. bras `foe`).
- **FORME LINEAIRE prouvee sans recalibrer quoi que ce soit** : ce sont les bras DESEQUILIBRES qui
  tranchent. `bal1` (1 ami de chaque cote) reste sur T_high — les deux modeles le predisent, c'est
  le controle. `bal2` (2 amis sur T_high, 1 sur T_low) bascule sur T_low : un terme BOOLEEN
  (« au moins un ami adjacent ») aurait donne `16.041 - 8.021 = 8.021` contre `12.263 - 6.131 =
  6.131` et serait reste sur T_high. Encadrement sans fitting : `U1(T_high) > 3.7782` (n=1 bascule)
  et `U1(T_high) - U1(T_low) < 3.7782` (bal1 ne bascule pas).
- **Deux contre-epreuves** : custom force a 0 -> le moteur reste sur T_high et DIVERGE du natif ;
  playbook retire du registre -> meme divergence. Le terme ET son enregistrement sont NECESSAIRES.
- Garde offline du SOUS-SET (qui compte, qui ne compte pas, ancrage) : `probe_custom_utility_27.py`.

### Porteur : summon amene par son summoner, mais jamais activable — d'ou la GREFFE

Les deux seuls porteurs de 1051 sont `orksOrkBoys` (SUMMON) et `orksNpc2OrkBoy` (npc). Le summon a
bien un invocateur — `Waaagh` (1058, `constants.unitId = orksOrkBoys`), porte par `orksWarboss`
[lineup, **present dans `--list-pool`**] — et la voie a ete conduite jusqu'au bout (runner 189) :

- `orksWarboss` caste `Waaagh` sur un ennemi a portee 3 (l'ability exige `TargetIsEnemy` **et**
  `CasterHasNotMoved` : deplacer le Warboss avant le cast le refuse) ;
- un `Ork Boy` apparait bien dans MON equipe avec `Stikkbomb(1051) [pret]` ;
- mais il **n'entre jamais dans la liste « A ACTIVER »** du harnais arene, et `aiDryRunAllUnits` ne
  rend pour lui que `FinishUnitTurnMessage` — au tour du spawn comme aux tours suivants ; au
  premier tour adverse joue, l'IA le tue (`u81->u119 KILL`).

Pas de verite de reference par cette voie ⇒ **GREFFE** de l'ability sur `orksRuntherd` (recette
`case-92` §5bis). Le natif PROUVE que le code exerce est bien `StikkbombPlaybook` en emettant
`ActiveAbilityMessage(1051)`.

> **MISE A JOUR #291 — le « verrou » n'en etait pas un : c'est le NATIF**
> (`case-291-summon-activation.md`). `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` appelle
> `FinishUnitTurn(spawned, isTerminated: true)` sur toute unite qui apparait pendant le tour de son
> proprietaire, et `FinishUnitTurnOperation$$Execute` enchaine sur `MarkUnitAsNoActionAvailable` ->
> `HasActionLeft` faux -> exclusion de `toActivate`, qui filtre exactement dessus. Aucune
> « activation a donner » : le debloqueur ci-dessus est CADUC.
> Ce que la mesure (probe_291) montre en revanche : le meme `Ork Boy` **agit** dans le cast meme
> (deplacement de 4 tuiles puis `Stikkbomb`), pousse par le 5e `Group` de
> `WaaaghAbility$$ExecuteBehaviour` = `PerformAIAction(...)` -> `ComputerAction(unit, forced)`. La
> face COMBAT du VRAI porteur est donc confrontable sans greffe, et l'objection « la greffe ne
> couvre ni les stats ni les traits du vrai porteur » (ci-dessous) tombe pour cette face.
> Ce qui reste bloque, plus etroitement, c'est l'oracle de **DECISION** per-unite : `aiDryRunAllUnits`
> interroge la tactique sur une unite a `NoActionAvailable`. **Nouveau debloqueur nomme** : une
> option `resetTurnFlags` sur `aiDryRunAllUnits` qui encadre `sweepAllUnitProposals` du couple
> `RemoveTurnFlags(flags, true, true)` / `SetUnitTurnsFlags` de `ComputerActionOperation`
> (`frida/hooks/features/ai-step/rpc-drive.ts`) — exige une reinjection Frida.

### Non couvert (nomme, pas masque)

- **Ce que la greffe ne couvre pas** : stats, traits et armes du VRAI porteur. Ici la formule custom
  ne lit ni stat ni trait du caster (elle lit la config de l'ability et l'etat du board), mais elle
  passe par une PREDICTION DE DEGAT, qui, elle, lit les stats du caster. L'accord natif<->moteur
  reste valide (les deux voient le MEME greffon), la generalisation aux stats de l'Ork Boy ne l'est
  pas.
- **Regime « caster buffe »** : `Waaagh` accorde `Waaagh_ExtraHits` aux Orks. Le port pose desormais
  le littéral `nrOfHits` (mirror du `GetNumberConstant` natif) au lieu de `get_special_hits` — mais
  le greffon n'a PAS d'ExtraHits, donc la branche ou les deux divergent n'est **pas exercee live**.
- **Unites NEUTRES** (ni `ctrl` ni ennemi du canal `decisionView`) : le natif les compterait comme
  non-amies (donc dans `MakeDamagePredictions`), le port ne les voit ni dans `ctx.fpos` ni dans
  `ctx.epos`. Aucun montage connu n'en produit a portee.
- **La face COMBAT est inchangee** : elle etait deja portee et validee (#213 friendly-fire,
  `stikkbomb_tree`). Cette tranche ne touche que la face DECISION.
- **1142 MalleusRocketLauncher et 1098 PlasmaGrenade restent des residus** : ils partagent le patron
  mais gardent leur verrou PROPRE (MoW non modelisee comme unite de decision pour 1142 ; summon SANS
  invocateur pour 1098). Le patron, lui, est desormais porte et outille.

## TRANCHE 4g (2026-07-30, #27-r1) — MassDriverAccelerator (1222) : le terme est un NO-OP NATIF

La fiche #27-r1 annoncait une formule, HERITEE de la tranche 4 :
`max(0, Count(GetBuffTargets.Evaluate(entities)) - 1) * W(MassDriverAccelerator_AdjacentFriendly = 5)`,
soit « W x nombre d'allies adjacents au caster ». **Elle est FAUSSE**, et le verrou nomme (l'evaluateur
du selecteur) n'etait pas la difficulte : la difficulte etait le CONTENU de l'`AbilityEntities`.

### Ce que le decompile dit — la chaine lue bout a bout

```
IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility :
    sel      = MassDriverAcceleratorAbility.GetBuffTargets(this.ability)
    entities = new AbilityEntities(caster: caster, actor: caster, target: target,
                                   owner: null, <et TOUS les autres slots a null>)
    n        = sel.Count(entities)                       // slot 2 de l'interface selecteur
    return Fix64.FromInt(Math.Max(0, n - 1)) * GetUtilityValue("MassDriverAccelerator_AdjacentFriendly")

IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$GetBuffTargets :
    Owner + DSLSelectors.AdjacentFriends(Owner, unique: 1, unitSelectionType: 3)
```

1. **`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ecrit `+0x00 = actor`, `+0x08 = caster`,
   `+0x10 = target`, `+0x18 = owner`.** L'ordre des PARAMETRES, lui, est
   `(caster, actor, target, owner, casterTile, activePlayer, casterTiles, effect, targetTile,
   targetTiles, activeTarget, previousActiveTarget, currentAbilityOrEffect, ...)` — signature
   `data/symbols/<build>/frida/methods.tsv`. **Le decalage entre l'ordre des parametres et l'ordre
   des champs est exactement le piege** : lire « les deux premiers arguments sont owner et caster »
   est ce qui a produit la formule fausse.
2. Le call-site du playbook passe `(caster, caster, target, 0, 0, 0, 0, 0, 0, 0, 0, 0, &cur, &parent,
   &trig, ...)` : **9 zeros consecutifs en positions 4..12** -> `owner = null`, et toutes les
   positions/tuiles nulles. Le contraste est dans le meme binaire, a deux fonctions d'ecart :
   `...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason` remplit, LUI, `casterTiles` et
   `targetTiles`.
3. **`IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `entities+0x18`** et, si le champ est
   nul, rend une `List` **VIDE**. Ses deux voisins lisent d'autres champs —
   `IdunBattle.Entities.Selectors.ActorSelector$$Select` lit `+0x00`,
   `IdunBattle.Entities.Selectors.CasterSelector$$Select` lit `+0x08` — c'est ce triplet qui interdit
   de confondre le champ, et il se lit en trois decompilations.
4. `AdjacentFriends(Owner, unique, sel)` = `Friends(Owner, Units(AdjacentTiles(Owner), unique, sel)
   - Owner, sel)` : sur un `Owner` vide, `AdjacentTiles` n'a aucune ancre -> vide aussi.
5. Donc `n = 0`, `Math.Max(0, 0 - 1) = 0`, terme = `Fix64(0) * W = 0` — **quelle que soit
   l'adjacence, sur tout plateau**. Le poids `MassDriverAccelerator_AdjacentFriendly = 5`, pourtant
   AJOUTE par ce build, n'est JAMAIS applique.

**Le selecteur `DSLSelectors+0x30` est bien `OwnerSelector`** — quatre lectures convergentes :
`...DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` appelle `AdjacentFriends(champ+0x30,
ownerTiles, 1)` (surcharge `(unit, unitTile, unique)`, parametre nomme **`ownerTiles`** dans la
metadata) ; `IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateTargetSelector`
a la structure BIT-A-BIT identique a `GetBuffTargets` et le port le documente deja « Self +
AdjacentFriends(range 1) » pour une AURA ; `...ModifiedExoarmourAbility$$CreateBehaviour` (le passif
de Kimm) passe `champ+0x30` a la fois comme cible et comme owner de ses deux `AddEffect`
auto-appliques ; `entities/effects/factory.py` documente deja Defender comme `AdjacentFriends(1) -
owner`. Les deux champs voisins ne sont PAS interchangeables : `+0x48` = CASTER (celui que
`ExecuteBehaviour` passe a `MoveUnit`/`AttackWithAttackDamage`/`IfAlive`) et `+0x60` = TARGET
(`GetAdjacentAttackTargets` = `Enemies(champ+0x48, AdjacentUnits(champ+0x60, 1, 3))`).

**A l'EXECUTION, le meme selecteur MARCHE** : `...MassDriverAcceleratorAbility$$ExecuteBehaviour`
re-inline le meme couple pour son `AddStaticStatModifierEffect(<cible>, 0x606, 1, Get(extraMovement))`
— Kimm et ses amis adjacents gagnent bien le bonus de mouvement. C'est la DECISION, et elle seule,
qui evalue le selecteur contre un `owner` nul. Le bug est natif ; on le mirroir, on ne le corrige pas.

### Confrontation LIVE — `probe_27_r1_massdriver_custom.py`

Fixture `MDA_FIXTURE` (board MC1_67, seed 909, `votanChampion` injecte par `catalog_inject`) :

- **Kimm reste sur sa tuile de SPAWN (1,0)**. Un `act move` consomme son mouvement, et 1222 devient
  alors ILLEGALE (`GetPossibleMoveTiles` vide) — MESURE : `abilityTargets` passe de 1 cible a 0.
  (1,0) est un coin a 3 voisins — (0,0), (1,1), (2,0) — et (2,0) reste LIBRE (chemin de charge).
- **La cible doit etre a distance >= 2** : `abilityReason` refuse 1222 sur une cible ADJACENTE
  (`TargetIsNotAdjacent`). `tauCrisis` en (3,1), sans aucun ennemi adjacent -> le residu
  `MakeDamagePredictions` (splash sur `GetAdjacentAttackTargets`) est inerte.
- **Deux allies porteurs d'aura de degat (`ultraCalgar`, `astraOrdnance`) FIGES loin** dans tous les
  bras : MESURE, rapprocher Calgar de Kimm fait passer `pairUtility(69)` de 22.02 a 37.95.
- **Le passif `ModifiedExoarmour` est retire du seed BC** (`PassiveAbilities: []`) : son playbook
  porte un terme de TUILE (`ModifiedExoarmour_LikesMovingPerTile` = 5 x longueur du chemin) que le
  port n'a pas (residu **N14** de `port-residuals-inventory.md`). Le bras `--passive-on` rejoue le
  scenario avec le kit REEL.
- **Le curseur est `--unit-stat votanChampion:Damage=<D>`** : il met l'attaque NORMALE et 1222 a
  egalite. Il ne touche PAS 1222 (`pairUtility(1222, (1,0))` = **63.846737472340465** sur TOUT le
  balayage, de Damage 900 a 12000 — bit-identique).

Resultat (passif RETIRE ; `n` = allies adjacents a Kimm, 0/1/2) :

| Damage | natif n=0 | natif n=1 | natif n=2 | moteur (terme = 0) | moteur MUTE `W x n` | `pairUtility(69, (3,0))` |
|---|---|---|---|---|---|---|
| 3525 | 1222 | 1222 | 1222 | 1222 x3 | 1222 x3 | 62.68968132790178 |
| 3550 | 69 | 69 | 69 | 69 x3 | **1222 des n=1** | 63.13543247524649 |

- **Le point de bascule natif est le MEME a n=0, n=1 et n=2**, dans une fenetre de 25 points de
  `Damage` = **0.4458 point d'utilite**. Borne : `|C(n=2) - C(n=0)| < 0.4458`, quand la formule
  heritee predisait **10**.
- **Le montage EST sensible** : le moteur PORTANT `W x n` bascule sur 1222 des n=1 la ou le natif ne
  bascule pas. Un terme de +5 aurait donc ete VISIBLE ; son absence est une mesure, pas un angle mort.
- **Bras de controle `--passive-on`** (kit REEL de Kimm, point d'equilibre a Damage 900/1000) : le
  natif y est **invariant en n lui aussi** (1222/1222/1222 puis 69/69/69), fenetre = 1.7830 point
  d'utilite. Le retrait du passif n'est donc pas ce qui annule le terme.
- Accord moteur <-> natif : **6/6 cellules** (2 Damage x 3 configurations d'adjacence).

### Generalisation — un SECOND plateau, geometrie et point d'equilibre RE-DERIVES

`--auto --board <id>` ne rejoue pas le scenario : il le RECONSTRUIT. `derive_geometry` repart de la
tuile de spawn de Kimm sur le plateau demande, prend ses voisins WALKABLE via `boardGraph`
(adjacence NATIVE, pas `hexgeo`), choisit une tuile ennemie a distance 2, et `bisect_flip` retrouve
le `Damage` d'equilibre par bissection. Les ids d'entite sont resolus par `visualId` (sur `C1_02`
ils valent 49..59 la ou `MC1_67` rend 77..87) — les figer aurait fait echouer tous les `act move`
en silence.

Resultat sur **`C1_02`** (Kimm en (0,0), ennemi en (0,2), appats en (1,1)/(1,0), equilibre trouve a
`Damage` 1198/1222) : natif `[1222, 1222, 1222]` puis `[69, 69, 69]` — **invariant en n la aussi** ;
moteur = natif **6/6** ; moteur MUTE `W x n` DIVERGE a n=1 et n=2. Fenetre de bascule : 24 points de
`Damage`.

**Un piege de montage a ete pris par cette generalisation, et il est desormais garde (verdict V0).**
La premiere derivation posait un appat sur `(0,1)` — precisement la tuile ou le natif allait frapper
a l'attaque normale. Le bras n>=1 privait donc le duel de son concurrent, et le natif basculait sur
1222 pour une raison **purement geometrique** : `[69, 1222, 1222]`, qu'on aurait lu « le terme n'est
pas nul ». La derivation choisit maintenant la tuile ennemie de facon a RESERVER au moins un voisin
de Kimm adjacent a l'ennemi, et le verdict **V0** refuse de conclure si la tuile d'attaque du natif
tombe sur un emplacement d'appat.

### Le port, et pourquoi il existe alors qu'il rend 0

`engine/playbook/loki_custom.py::MassDriverAcceleratorPlaybook` rend `0.0`. C'est identique au
comportement de la base `ComparablePlaybook<T>` — la classe n'ajoute donc AUCUN comportement. Elle
existe pour **verrouiller ce zero** : sans elle, la formule de la fiche resterait la seule trace
ecrite de 1222 dans le depot, et le prochain lecteur la re-porterait. Deux cliquets l'accompagnent :
`probe_custom_utility_27.py` (offline, 0 allie a 3 allies adjacents -> 0.0) et
`tests/engine/test_mass_driver_custom_utility_live.py` (live, 6 cellules + la mutation adversariale).

### Ce que cette tranche NE couvre PAS

- **N14** — le terme de tuile `ModifiedExoarmourPlaybook` (5 x longueur du chemin), non porte :
  il RETOURNE la decision de Kimm des que son passif est actif (mesure ci-dessus).
- ~~**N15**~~ — `MassDriverAcceleratorPlaybook$$MakeDamagePredictions` (splash par ennemi adjacent a
  la cible, `GetHits2`/`DamageProfile2`) : **FERME le 2026-07-31 par #305**,
  `case-305-massdriver-splash-prediction.md`. L'ecart etait nul dans CE montage par construction (la
  cible n'y a aucun ennemi adjacent) ; chiffre ailleurs, il vaut un event de degat entier par ennemi
  adjacent, avec le profil `Physical` (pierce 1) au lieu de `DirectDamage` (pierce 100).
- La face COMBAT de 1222 (`ExecuteBehaviour` : buff de mouvement + `MoveUnit` + double attaque) n'est
  pas dans le perimetre de #27 et n'a pas ete confrontee ici.

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

## PORTES (10) — `engine/playbook/loki_custom.py`

| Ability (id) | VA | Formule mirroir | Poids (seed-bc) | Porteur | Validation |
|---|---|---|---|---|---|
| **ArmoriumCherub** (1014) | @18111c530 | `Fix64(1)` constant (aucune garde) | — | adeptRetributor `Vindicta` [lineup] | Live : runner 132 step 13 natif=1014, moteur=1014 [MATCH] (dispatch + custom appliques). Constante triviale -> RE + garde offline. |
| **LightOfSanguinius** (1177) | @181133d70 | `count(units du joueur-du-caster a PV%==100) * W` (iteration directe des units : `GetOriginalPlayer(caster)` -> `GetStat(Health,part1)==100`) | `LightOfSanguinius_FullHealthFriendlyUnits` = **-10** | bloodDante `Dante` [lineup] | Live : reaches `_best_attack` (Melta 5-hit) ; custom = -40 (4 allies pleins) correctement CALCULE + APPLIQUE (probe `_solver27_dante_probe`), natif=moteur [MATCH] runner 138. Flip-decisif non isole (la normale boostee de Dante domine toutes les geometries d'arene atteignables) -> couverture partielle assumee. |
| **HeraldOfTheApocalypse** (1020) | @1811441b0 | `foreach (e in GetAllNormalAttackTargets(caster).Targets) if (EnemyCouldBeDamagedWithNormalAttack(e)) return 0; return W` — `EnemyCouldBeDamagedWithNormalAttack @18111da80` = `GetAllNormalAttackTargets(e).Targets.Count > 0`. Terme CONSTANT sur (tuile, cible). | `HeraldOfTheApocalypse_CannotKillEnemy` = **50** | blackHaarken `Haarken` [hero, `--list-pool`] | **A/B causal live** (probe `probe_custom_utility_27_live.py`, runners 1276/1299/1304) : geometrie caster/ennemi FIGEE, seul un appat allie bouge -> natif bascule Herald <-> normale ; paires natives BIT-IDENTIQUES dans les 2 bras (8.019551052711904 / 0.018102815374732018) -> zero confond de prediction. Frontiere mesuree = **portee d'ARME de l'ennemi depuis sa tuile** (astraOrdnance r3 -> bascule d=3/4 ; blackTerminator r1 -> d=1) : exclut une feuille d'adjacence. Borne : **C > 34.22**. |
| **Drachnyen** (1029) | @18112dc60 | `count(GetAdjacentEnemies(tuile d'attaque, ownerId)) >= 2 ? W : 0` (BattleQuery slot 0x7d + predicat `<>c` ; l'`ownerEntityId` scope aux ENNEMIS). Terme **POSITION-dependant**. | `Drachnyen_MultipleAdjacentUnits` = **10** | blackAbaddon `Abaddon` [hero, `--list-pool`] | **A/B causal live** apres neutralisation du confond de PAIRE (Drachnyen FIXE les PV du caster a 4729 -> `--hp-player 4729` rend le set-health neutre, paire native = 0 ; sans ca la paire natif=-35.4 vs offline=+2.5 ecrase le +-10). Runner 1373 : caster LOIN (0 ennemi adjacent a sa tuile COURANTE), tuile d'attaque a 1 ennemi -> natif NORMALE (54.139 vs 50.000+C) ; a 2 ennemis -> natif **DRACHNYEN** => le count porte sur la **tuile d'ATTAQUE**. Allie adjacent au lieu d'un ennemi -> natif reste sur la normale => **les allies ne comptent pas**. Encadrement : **5.547 < C < 10.716** (runners 1363 / 1335). |

| **DoomSiren** (1199) | @18112cd30 | `W(DefinitelyOverkill) * #(preds WillBeOverkill) + W(TargetHasAdjacentEnemy) * [count(GetAdjacentEnemies(tuile de la CIBLE, caster)) > 0]` | `DoomSiren_DefinitelyOverkill` = **40** ; `DoomSiren_TargetHasAdjacentEnemy` = **50** | emperKakophonist `Adamatar` [hero, `--list-pool`] | **A/B causal live** (probe #27-2, runner 339) : cible + tuile d'attaque FIGEES, seul un 2e ennemi passe loin -> adjacent a la cible ; natif bascule 69 -> **1199**, moteur idem ; contre-epreuve custom=0 -> moteur 69 dans les DEUX bras. Encadrement 100 % natif : **0.624 < C < 1.096** (cf. Validation). |

| **HeavyWarpFlamer** (1227) | `IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$CalculateCustomUtility` | `W * Count(battleQuery.<slot 0x7f>(target, caster, ignoreSteppables:false))` — slot d'interface 0x7f = index de vtable 0x83 (`interfaceOffset` = 4) = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IEntity from, TUnit unit, bool)`. Terme **LINEAIRE** dans le compte (DoomSiren teste `>0`, Drachnyen `>=2`), ancre sur la tuile de la CIBLE. | `HeavyWarpFlamer_LikesAdjacentEnemies` = **10** | thousSekhetar `Sekhetar Robot` [lineup, hors catalogue seed BC -> `catalog_inject.py --units thousSekhetar`] | **A/B causal live** (`probe_27_4_warpflamer_ab.py`, board MC1_67, 2 geometries, 4 bras). Argmax par CIBLE : 2 cibles a distance 2, ecart de paire natif **17.622786**, les 4 `pairUtility` natives BIT-IDENTIQUES dans TOUS les bras. n=0 -> natif T_haut ; **n=1 -> natif ENCORE T_haut** (un terme booleen aurait bascule) ; n=2 -> natif T_bas ; +1 ALLIE au lieu du 2e ennemi -> retour a T_haut. Moteur = natif dans les 4 bras ; custom force a 0 -> moteur reste sur T_haut a n=2 (**terme NECESSAIRE**). Encadrement sans fitting : **8.8114 < W < 17.6228**. |

| **SavageEchoes** (1230) | @1811586d0 | `GetRegenerateCondition(ability).Evaluate(entities) ? 0 : W` — la condition est `DSLFactory.HealthPctIsBelowOrEqual(caster@0x160, ConfigConst(0x4f = healthPct))` = `StatPercentageIsBelowOrEqualAbilityTrigger(caster, Health=5, thr)`, dont `ShouldTrigger` compare le **RATIO** `GetStat(u,stat,0)/GetStat(u,stat,2)` a `thr/100` (PAS un pourcentage arrondi). Terme CONSTANT sur (tuile, cible), variable avec les PV du CASTER. | `SavageEchoes_DislikesAboveHealthPct` = **-10** ; seuil `SavageEchoes.constants.healthPct` = **50** | bloodTerminator `Cezare` [lineup, HORS catalogue seed BC -> amene par `catalog_inject.py --units bloodTerminator`] | **A/B causal live** (`probe_27_3_savage_ab.py`, board MC1_67, caster (4,8) / cible (5,8) FIGES, `--hp-target 60000 --armor-target 4000`) : les DEUX `pairUtility` natifs sont BIT-IDENTIQUES entre les bras (6.3564547803252935 / 12.049598339945078) -> confond de prediction MESURE et NUL ; seul le PV% du caster varie. 100 % -> natif **69**, moteur **69** ; 49.64 % -> natif **1230**, moteur **1230**. Contre-epreuve custom=0 : moteur **1230 dans les DEUX bras** -> terme NECESSAIRE. |

| **Stikkbomb** (1051) | `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility` | `-n x U(pred(CIBLE, base = Get(minDmg), hits = GetNumberConstant(0x32 = nrOfHits_2), profil config))` ou `n` = nb d'AMIS du caster (caster INCLUS) adjacents a la CIBLE. Sous-set = arbre DSL `AdjacentUnits(Target, unique:1, sel:3)` **partage avec la face COMBAT**, filtre par un `IsFriend` IMPERATIF. Chaque membre produit une prediction sur la **CIBLE PRINCIPALE**, pas sur lui-meme (4e arg du `GenerateMultiHitAttackPredictions` = `target`, lu a l'assembleur). Terme INDEPENDANT de la tuile d'attaque. | **aucun poids BC** (ce custom n'appelle pas `GetUtilityValue`) ; `nrOfHits_2` = 1, `nrOfHits` = 2 | orksOrkBoys [SUMMON de `Waaagh`/orksWarboss ; amene mais **jamais activable en arene** -> GREFFE sur `orksRuntherd`, `case-92` §5bis] | **A/B causal live** (`probe_27_4f_stikkbomb_ab.py`, board MC1_67, seed 909, `--armor-target 3000`), **7 bras**, moteur = natif dans les 7 ; 6 `pairUtility` natives BIT-IDENTIQUES sur tous les bras amis ; linearite prouvee par bras DESEQUILIBRES ; deux contre-epreuves DIVERGENTES. Detail en §TRANCHE 4d. |

| **PlasmaGrenade** (1098) | `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` | `n x U(pred(CIBLE, base = Get(minDmg), hits = GetNumberConstant(0x32 = nrOfHits_2), profil config))` ou `n` = nb d'**ENNEMIS** du caster adjacents a la CIBLE (`battleQuery.<slot itf 0x7d>` = `GetAdjacentEnemies(IEntity, BEntityId, bool)`, index de vtable 0x81 — RE-DERIVE au runtime). Signe **POSITIF** (Stikkbomb, meme mold, NIE sa somme parce qu'il compte des amis). **Somme nulle -> `BaseUtility.<statics+0x18>` = VETO**, pas utilite nulle. Terme INDEPENDANT de la tuile d'attaque, DEPENDANT de la cible. | **aucun poids BC** ; `nrOfHits_2` = 1, `nrOfHits` = 2 | eldarSmnGuardian [summon SANS invocateur] + eldarNpc1Guardian [npc] -> porteur **GREFFE** sur `eldarAutarch` (`case-92` §5bis) | **A/B causal live** (`probe_27_4g_plasma_grenade_ab.py`, board MC1_67, seed 909), **3 bras a issues DIFFERENTES**, moteur = natif dans les 3 ; VETO prouve avec cible LEGALE et `pairUtility` = 13.553 ; RENVERSEMENT de l'argmax par cible en C2 ; **2 mutations adversariales ROUGES**. Detail en §TRANCHE 4g |
| **MassDriverAccelerator** (1222) | `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility` | **`Fix64(0)` — NO-OP NATIF.** `Max(0, Count(GetBuffTargets) - 1) * W` avec `GetBuffTargets` = `Owner + AdjacentFriends(Owner, 1, 3)`, evalue contre un `AbilityEntities` dont `owner` est NULL (`AbilityEntities$$.ctor` ecrit `+0x18 = owner` ; le call-site passe 9 zeros en positions 4..12 ; `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `+0x18` et rend une liste VIDE) -> `Count = 0`, `Max(0, -1) = 0`. | `MassDriverAccelerator_AdjacentFriendly` = **5**, JAMAIS applique | votanChampion `Kimm` [hero, hors pool -> `catalog_inject.py --units votanChampion`] | **A/B causal live** (`probe_27_r1_massdriver_custom.py`, board MC1_67, seed 909, curseur `--unit-stat votanChampion:Damage`) : le point de bascule natif 1222 <-> attaque normale est le MEME a n=0, n=1 et n=2 allies adjacents, dans une fenetre de **0.4458 point d'utilite** (la formule heritee predisait 10). SENSIBILITE prouvee : le moteur PORTANT `W x n` bascule des n=1 la ou le natif ne bascule pas. Bras de controle `--passive-on` (kit REEL) : invariance en n confirmee, fenetre 1.7830. Accord moteur/natif **6/6 cellules**. Detail en §TRANCHE 4g. |

Les dix HERITENT la prediction de degat du `DefaultActiveAbilityPlaybook` ; #27 ne porte QUE le
terme custom (la prediction est deja assuree par `prediction.py`, ecarts de degat = hors perimetre).
**Exception assumee : Stikkbomb (1051)**, dont la prediction est portee DANS la meme tranche —
`MakeDamagePredictions` et `CalculateCustomUtility` y sont litteralement le meme corps avec
`IsFriend` inverse, et sans la face prediction l'A/B ne serait pas interpretable (cf. §TRANCHE 4f).

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

> ⚠ **Ce tableau est celui de `gqfc5mff6c`.** Le compte du build COURANT (`rnca9r7q6c`) est **29 corps
> distincts = 26 nommes + 3 partages**, re-derive en §TRANCHE 4g ; les verdicts par ligne ci-dessous
> sont tenus a jour, mais les VA et le compte d'en-tete ne le sont pas. Re-deriver plutot que citer :
> `python probe_27_custom_utility_inventory.py --build rnca9r7q6c`.
>
> ⚠ **RE-DERIVE OFFLINE le 2026-08-05 (#27-r8), et l'INVENTAIRE DES CORPS EST CLOS.** Sans runner :
> `data/symbols/rnca9r7q6c/ghidra/functions.tsv` rend **29 corps** `$$CalculateCustomUtility`
> (+ 1 lambda `DrachnyenPlaybook.<>c$$<CalculateCustomUtility>b__3_0`),
> `frida/methods.tsv` en rend **26** — l'ecart de 3 EST la liste des gshared
> (`ComparablePlaybook<T>`, `ALoki_NormalAttackPlaybook<T>`, `Idun.NormalAttackPlaybook<T>`),
> structurellement absents du dump Frida. Les deux sources concordent avec le balayage vtable de la
> §TRANCHE 4g. **Les 29 sont tranches : 0 corps non porte a porteur confrontable.** Ce qui reste
> ouvert dans cette case-doc n'est donc plus un CORPS mais un ETAGE — les gates `ShouldEvaluate` /
> `GetUseProbability` (cf. §TRANCHE r8) — et un porteur (le tacticien MoW).

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
| 12 | `MortisRoundPlaybook` | MortisRound (1004) | ultraEliminatorSgt | hero (pool) | **PORTE** (#27-r3) | — (les deux verdicts precedents sont CORRIGES : le « terme mesure NUL » etait la TRONCATURE vers `int` sur un board PLAT, et l'« evaluateur manquant » n'existait pas — la voie `EvaluateAttack` des feuilles `Tile(7)` DELEGUE a `EvaluateMovementInSteps`, donc `tile_utility` suffisait. Re-mesure sur MC1_67 : custom = 20 et 10 selon la geometrie. Cf. §TRANCHE 4h) |
| 13 | `SorcerousFacadePlaybook` | SorcerousFacade (1100) | thousTzaangor | hero (pool) | **PORTE** (#27-4e) | — (le verrou « route de ciblage ALLIE » est TOMBE : 1100 passe par `playbook/nonattack.py`, dont l'enumeration vient de `ctx.ability_targets` ; le VETO #217 sur la route ENNEMIE est INTACT et re-mesure dans le meme montage) |
| ~~13bis~~ | ~~`AmuletOfTheVoidwyrmPlaybook`~~ | AmuletOfTheVoidwyrm (1464, `TriggeredAbilityType`) | — | passif/triggered | **RETIRE — FAUX POSITIF (#218)** | n'override PAS : sa base `TriggeredAbilityPlaybook`1` descend directement de `System.Object`, hors de la branche `ComparablePlaybook`1` qui declare le virtuel. Le « slot +0x548 » etait le slot +0x338 de `PlasmaGrenadePlaybook`, dont la classe suit a +0x210 en memoire (les 39 slots coincident). Ce qui reste OUVERT sur 1464 est son playbook de **MOUVEMENT** (`AmuletOfTheVoidwyrmPlaybook$$CalculateMovementUtilityInStepsInternal` + face NonOwner `AmuletOfTheVoidwyrmNonOwnerPlaybook$$GetAdjacencyUtility`), inventorie rang B de `case-193` — un AUTRE item. Detail : `docs/rl/case-218-amulet-voidwyrm-custom-utility.md` |
| 14 | `ProperKilly_NormalAttackPlaybook` @1811532a0 | ProperKilly (aucun id) | **aucun** | — | **dead-code** | — (non pertinent) |
| 15 | `PlagueburstMortarPlaybook` @181134e00 | PlagueburstMortar (1169) | deathCrawler | **MoW (pool MoW)** | **PORTE** (#302 tranche 1) | — (**cette cellule disait encore « invalidable-residu » APRES la livraison de #302 — corrige #27-r8** : le port vit dans `engine/playbook/plagueburst_mortar.py`, il est enregistre par `engine/playbook/__init__.py`, et `tests/engine/test_plagueburst_mortar_decision_live.py` le confronte (10 tests verts au 2026-08-05). La ventilation ci-dessous le classait deja parmi les PORTES : la fiche se CONTREDISAIT, et le tableau — la cellule qu'un dispatch lit en premier — portait la version perimee. Le verrou historique (« ciblage TILE-TARGET, `abilityTargets` -> 58 cibles `kind = "tile"`, `attackPlans` `rankCount = 0` partout ») a ete leve par la ROUTE A CIBLES TUILE : `docs/rl/case-302-route-cible-tuile.md` §6) |
| 16 | `DaemonicOrdnancePlaybook` @1811286c0 | DaemonicOrdnance (1148) | blackForgefiend | MoW (pool MoW) | **PORTE** (#302 tranche 3) | — (route de decision a cibles TUILE + `10 x |ennemis sur GetTargetAreaTiles|`, `10` = CONSTANTE `Fix64(0xa)` EN DUR ; l'evaluateur DSL `TilesOnSameElevation(TilesInTriangleShape(...))` etait DEJA porte par la face COMBAT #90. La tranche a en outre corrige `IsPositionMachineForCurrentPlayer`, qui lisait le slot d'une MoW DEPLOYEE au lieu du groupe de spawn du PLATEAU — cf. `docs/rl/case-302-route-cible-tuile.md` §8) |
| 17 | `StikkbombPlaybook` @18115f7c0 | Stikkbomb (1051) **SEULE** | orksOrkBoys [summon de `Waaagh`/orksWarboss, **en pool**] | summon | **PORTE** (#27-4f) | — (le sous-set = `AdjacentUnits(Target)` filtre par `IsFriend`, et chaque membre produit une prediction sur la CIBLE PRINCIPALE : lu au decompile puis a l'assembleur, confirme live). Porteur summon amene par `Waaagh` mais jamais activable en arene -> GREFFE (`case-92` §5bis). ⚠ **Le « playbook PARTAGE 1051/1142 » est RETIRE (#27-4g)** : `...StikkbombPlaybook$$.ctor` appelle `ComparablePlaybook<T>..ctor(this, 0x41b)` — 1051 seule — et aucune classe `Malleus*Playbook` ne porte le slot au balayage runtime. 1142 n'a AUCUN corps propre |
| 18 | `PlasmaGrenadePlaybook` @181151040 | PlasmaGrenade (1098) | eldarSmnGuardian [summon **sans invocateur**] + eldarNpc1Guardian [npc] | summon + npc | **PORTE** (#27-4g) | — (les deux verrous sont TOMBES : (a) le mold `GenerateMultiHitAttackPredictions` a ete ouvert par 1051 et le foyer est PARTAGE — `prediction.make_secondary_multihit_event`, memes 4 entrees ; (b) le porteur, refuse par `buildNormalizedBC`, est GREFFE sur `eldarAutarch`). S'y ajoute le VETO : somme nulle -> `BaseUtility.<statics+0x18>` -> aucune action |
| 19 | `ChronometronPlaybook` | Chronometron (1226) | necroChronomancer | hero (catalog_inject) | **PORTE** (#27-4b) | — (les trois verrous annonces sont TOMBES : (a) `catalog_inject.py` amene le porteur ; (b) la route non-attaque `playbook/nonattack.py` remplace `_best_attack` ; (c) le selecteur DSL etait DEJA porte par la face COMBAT — `chronometron_affected_enemies`, meme artefact natif) |
| 20 | `DevoutPushPlaybook` @18112c7b0 | DevoutPush (1053) | templInitiate | summon **d'environnement** (`EnvFactionSummons:BlackTemplars`) | **residu** | formule TRIVIALE (`ALoki_NormalAttack.custom * 2` = **2** constant) mais (a) porteur env-only, (b) `damageProfile` absent -> action « push » non modelisee |
| 21 | `ForwardObserversPlaybook` @18113bb70 | ForwardObservers (1185) | tauSmnStealthSuit [summon SANS invocateur] + tauNpc5StealthSuit [npc] | summon + npc | **PORTE** (#27-4e) | — (les deux verrous sont TOMBES : (a) la route non-attaque `playbook/nonattack.py` remplace `_best_attack` ; (b) le predicat Markerlight est un mirror IMPERATIF de `CheckIfAnyEnemyHasMarkerLight` (slot itf 0x8e `GetAllEnemiesOf` + `EntityExtensions.HasEffect`), sans arbre DSL a evaluer. Porteur GREFFE — `ATemptingTrap` n'appartient a AUCUNE unite ET `buildNormalizedBC` refuse summon/npc) |
| 22 | `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility` | HealingBalms_Heal (1212) | spaceWolfPriest `Baldr` [lineup, hors catalogue seed BC -> `catalog_inject.py --units spaceWolfPriest`] | hero | **PORTE** (#27-4d) | — (les verrous annonces sont TOMBES : l'ability n'a pas besoin d'entree gameconfig — sa magnitude vient de l'ARME —, elle est GRANTED des le spawn par `HealingBalmsAbility$$CreateBehaviour` (`RemoveActiveAbility(0x12)` + `AddActiveAbility(0x4bc)`), et elle atteignait deja `_heal_candidates`) |
| 23 | `SavageEchoesPlaybook` @1811586d0 | SavageEchoes (1230) | bloodTerminator | hero hors catalogue seed BC -> **confrontable via `catalog_inject.py`** | **PORTE** (#27-3) | — (verdicts « porteur hors pool » + « evaluateur de CONDITION manquant » des tranches 1-2 **CORRIGES** : le catalogue se complete, et la condition est un simple ratio de PV lu au decompile) |
| 24 | `IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$CalculateCustomUtility` | MortarionsPlagueWind (1093) | deathBossMortarion | npc **-> GREFFE sur `tauCrisis`** | **PORTE (#27-r5)** | — (`Count(UnitsWithTrait(t1+t2+t3, Psyker))` ; le « verrou restant » annonce ici etait PERIME : les 4 primitives et 2 combinateurs etaient deja portes, et la chaine a 3 vagues EST l'artefact natif de `PlagueWind` (1035), porte depuis #220 — c'est la deduplication IL2CPP qui la nommait d'apres un proprietaire arbitraire. Residu `#27-r5-r1` : prediction AoE) |
| 25 | `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$CalculateCustomUtility` | InstrumentsOfVengeance (1215) | darkaBossLion | npc **-> GREFFE sur `darkaAsmodai`** | **PORTE (#27-r6)** | — (`20000 + 100*[aucun ennemi adjacent] + 20*|surrounding(2) \ adj|` ; route NON-ATTAQUE, masque STATIC-COPY `0x8004` SANS `CasterHasNotMoved` -> le terme est POSITION-DEPENDANT et ses constantes sont discriminables par le CHOIX DE TUILE. ⚠ `adj` et `surrounding` n'ont PAS la meme geometrie — la fiche r4 disait « ennemis a d=2 », c'est `surrounding \ adj`, et l'ecart est MESURE. Residu : le gate `GetUseProbability` reste non porte, cf. §TRANCHE r6) |
| 26 | `IdunBattle.AI.Playbook.Loki.MartialExemplarPlaybook$$CalculateCustomUtility` | MartialExemplar (1216) | darkaBossLion | npc **-> GREFFE sur `darkaAsmodai`** | **PORTE (#27-r4)** | — (`1000 x` le compte d'ennemis adjacents `IsNormalUnit` ; ne lit ni stat ni trait du caster. Le natif emet `ActiveAbilityMessage(1216)` sous greffe. Route NON-ATTAQUE malgre un `damageProfile`, parce que le masque effectif `0x8014` est SELF-CAST) |
| 27 | `IdunBattle.AI.Playbook.Loki.TheLionsWrathPlaybook$$CalculateCustomUtility` | TheLionsWrath (1217) | darkaBossLion | npc **-> GREFFE sur `darkaAsmodai`** | **PORTE (#27-r7)** | — (`30*FindMeleeWeapon(CIBLE).Hits + 2000*|adjacents Chaos+Hero| + 150*[CIBLE est Hero]` ; le verrou n'etait pas la formule mais la ROUTE : `MakeDamagePredictions` est ABSENT des tables et pourtant OBLIGATOIRE — la base `ComparablePlaybook<T>` est ABSTRAITE — et son override rend `[]`, donc seule la route NON-ATTAQUE produit l'ability) |

### Ventilation (les 22 overrides par-ability, apres correction #218)

*(Re-derive du BINAIRE le 2026-07-30 sur `rnca9r7q6c` — `probe_27_custom_utility_inventory.py
--build rnca9r7q6c`. Ces chiffres se PERIMENT : les re-deriver plutot que citer cette ligne.)*

*(Etat au 2026-08-01, apres #27-r3.)*

- **PORTES / couverts : 19** — 1014, 1177, 1020, 1029, 1199, 1119, 1230, 1227, 1226, 1185, 1212,
  1100, 1051, **1098**, 1009, **1169** (#302 tranche 1), **1148** (#302 tranche 3), 1222 (NO-OP
  natif, #27-r1), **1004** (#27-r3) (+ les corps mutualises `Loki_NormalBossAttack` et
  `TwistedScience_Heal`, et les 3 corps PARTAGES : base, attaque normale, heal generique).
- **Traites sans port (verdict ferme) : 1** — ProperKilly (dead-code, aucun porteur).
- **Porteurs NPC : 4 — et l'angle « npc-only » est TRANCHE (#27-r4).** Les quatre formules ont ete
  relues au decompile sous le seul angle qui compte (« lit-elle une stat ou un trait du CASTER ? ») :
  **aucune ne le fait**, donc les quatre sont **GREFFABLES** (`case-92` §5bis). **1216
  `MartialExemplar` est PORTEE et CONFRONTEE** — le natif emet `ActiveAbilityMessage(1216)` une fois
  l'ability greffee sur `darkaAsmodai`. **Les trois autres le sont aussi, par la meme greffe** :
  1093 `MortarionsPlagueWind` (#27-r5), 1215 `InstrumentsOfVengeance` (#27-r6) et 1217
  `TheLionsWrath` (#27-r7). **Aucun des quatre n'est plus un residu de PORT** ; ce qui reste ouvert
  est nomme par tranche (`#27-r5-r1` la prediction AoE de 1093, `#27-r6-r1` le gate de 1215).
  Detail et verdicts : §TRANCHE r4, r5, r6 et r7.
- **Residus a debloquer : 0 a porteur HERO/pool.** (1169 et 1148 sont SORTIS : le verrou etait le
  DOMAINE DE CIBLE, leve par la route a cibles TUILE — `docs/rl/case-302-route-cible-tuile.md` §6
  et §8. **1004 est SORTI par #27-r3** : le verrou ecrit — « evaluateur du composite
  `UtilityAttackCase.Base` manquant » — **n'existait pas**, la voie ATTACK des feuilles `Tile(7)`
  deleguant a `EvaluateMovementInSteps`.)
- **DEUX entrees SORTENT de la liste sans qu'aucun port ne les ferme (#27-4g, correction
  d'inventaire)** : **1142 MalleusRocketLauncher** n'a AUCUN corps propre — le « playbook PARTAGE
  1051/1142 » est FAUX sur ce build (`...StikkbombPlaybook$$.ctor` -> `0x41b` = 1051 seule) — et
  **1053 DevoutPush** partage le corps de l'attaque normale (`Fix64(1)`), deja couvert.
  (Tranche 3 : 10 ; **AmuletOfTheVoidwyrm retire — faux positif, #218** ; **1226 porte — #27-4b** ;
  **1185 porte — #27-4c** ; **1212 porte — #27-4d** ; **1100 porte — #27-4e** ;
  **1051 porte — #27-4f** ; **1098 porte + 1142/1053 retires — #27-4g**.)

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

1. ~~**Cible TUILE non modelisee dans la route de DECISION** (1169, 1148)~~ — **VERROU LEVE (#302),
   et cette entree etait PERIMEE depuis (corrige #27-r8).** La route de decision a cibles TUILE
   existe (`engine/playbook/tile_targets.py` + `nonattack.eligible_targets`, qui choisit un DOMAINE
   au lieu de filtrer `kind == "unit"`), et les DEUX membres sont portes et confrontes :
   `engine/playbook/plagueburst_mortar.py` (1169) et `engine/playbook/daemonic_ordnance.py` (1148).
   Detail : `docs/rl/case-302-route-cible-tuile.md` §6 et §8.
   ⚠ Ce qui reste ouvert n'est PAS le domaine de cible mais **le tacticien MoW** — les MoW
   n'apparaissent ni dans `decisionView.units` ni dans `attackPlans` (mesure runner 336) — et il ne
   bloque que le porteur REEL (`deathCrawler`) ; la GREFFE sur une unite du pool suffit a confronter
   le playbook, puisque le natif le charge PAR ABILITY.
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
   - ~~**1100 SorcerousFacade**~~ — **PORTE (#27-4e)**. Le diagnostic « la route non-attaque ne le
     debloque pas » etait faux d'un cran : le critere reel de cette route n'est pas « pas de
     `damageProfile` », c'est « ABSENTE de `ctx.plans` ». Le VETO #217 met precisement 1100 dans ce
     cas, et son enumeration de cibles (`ctx.ability_targets`) rend deja les ALLIES. Il n'a donc
     fallu creer AUCUNE route neuve — seulement rendre celle-ci structurellement fidele en y sommant
     `CalculateUtilityFromPredictions` (no-op exact pour Chronometron, dont les predictions sont
     vides). Detail : §`SorcerousFacade (1100)` ci-dessous.
3. ~~**Porteur hors `--list-pool` au rank courant**~~ — **VERROU SUPPRIME (tranche 3)**. Le porteur
   `lineup` absent du catalogue de la seed BC se rajoute par `catalog_inject.py --units <id>` (#92,
   `BC.Units` ET `BC.Abilities`), et le runner le deploie normalement — fait pour bloodTerminator
   (1230), necroChronomancer (1226) et spaceWolfPriest (1212).
4. ~~**`GenerateMultiHitAttackPredictions` sur un sous-set de cibles**~~ — **VERROU LEVE (tranche
   4f)**, cf. §TRANCHE 4f. Le sous-set est un arbre DSL **deja porte par la face COMBAT**
   (`AdjacentUnits(Target)`) filtre par un `IsFriend` IMPERATIF, et chaque membre produit une
   prediction sur la **CIBLE PRINCIPALE** (lu a l'assembleur, confirme live : +8.0282 sur la paire
   de la cible, contre 0.5504 attendus si l'event portait sur le voisin). **1051 est PORTE et
   valide live** (7 bras, linearite prouvee par bras desequilibres, deux contre-epreuves).
   **Ce verrou est desormais CLOS des deux cotes (#27-4g)** :
   - **1098 PlasmaGrenade** — **PORTE**. Playbook DISTINCT (`PlasmaGrenadePlaybook`) mais MEMES 4
     entrees de prediction : un seul foyer, `prediction.make_secondary_multihit_event` (renomme de
     `make_stikkbomb_splash_event`). Porteur summon SANS invocateur -> GREFFE sur `eldarAutarch`.
   - **1142 MalleusRocketLauncher** — **RETIRE de l'inventaire** : il n'a AUCUN corps propre (le
     partage de playbook avec 1051 etait un faux positif de la tranche 3, refute au `.ctor`).
   (AmuletOfTheVoidwyrm y figurait au titre du « corps partage avec 1098 » — **retire par #218**,
   ce partage n'existait pas.)
5. **Evaluateurs manquants** : composite `UtilityAttackCase.Base` (1004), DSL de forme
   `TilesInTriangleShape` (1148), DSL selecteur d'ability (1226).

### `SorcerousFacade` (1100) — PORTE (#27-4e, tranche 4e)

C'etait le dernier verrou de la famille, et il etait DISTINCT des autres : la cible native est un
**ALLIE Psyker** (i2 : « Target a friendly Psyker... then switches positions with the targeted
Psyker »), la ou tous les autres membres scorent des ennemis.

#### Les quatre pieces du natif (relues sur `rnca9r7q6c`)

**1. Le masque.** `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$.ctor`
prend la surcharge **FLAGS DIRECTS** de `IdunBattle.Core.Services.TargetingOptions$$.ctor`
(`(this, isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
getDynamicInvalidTargetReason)`) : `isSelfCasting = 0`, `range` = le champ statique `TargetingRange`
+0x48 (whole board), `forceMeleeTarget = 1`, et **`rules = 0x402` en LITTERAL**. Ce n'est ni un
preset statique recopie, ni la surcharge PRESET+flags — le piege de masque ne s'applique pas ici, et
`TARGETING_OPTIONS_UNPORTED[1100]` (pose par #217) est confirme sur le build courant. La portee
« whole board » est visible live : `abilityTargets(1100)` rend l'allie a **distance 6** du caster.

**2. Le terme custom.** `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility`
(slot de vtable **+0x338**, MESURE par `probe_27_4e_facade_vtable.py`) :

```
u1 = IUtilitiesDatabase.GetUtility(7 = UtilityType.Tile)
        .EvaluateMovement(new UtilityMovementCase(caster, EntityExtensions.GetMainTile(target)));
u2 = IUtilitiesDatabase.GetUtility(7)
        .EvaluateMovement(new UtilityMovementCase(caster, casterPosition));
return Fix64.op_Subtraction(u1, u2);
```

C'est **le MEME artefact natif** que
`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility` :
memes deux appels (slot 0 d'`IUtilitiesDatabase` avec l'argument `7`, puis slot 8 d'`IUtility`), au
seul champ `AbilityType` pres (rempli la, NUL ici — il n'entre pas dans le composite Tile). Le port
n'ecrit donc AUCUN evaluateur neuf : il APPELLE `engine.ai.utilities.get_movement_utility(ctx, pos,
UtilityType.Tile)`. Les deux `UtilityMovementCase` sont construits par des surcharges DIFFERENTES,
tranchees par XREF et non par lecture d'une signature ambigue (le 1er appel prend la surcharge
`movementTile`, qui fait `new UnitPosition(tile)` ; le 2e la surcharge `movementPosition`).

La reduction « le composite se reduit a Tile(7) » de la tranche 2 reste vraie mais devient
SURNUMERAIRE : l'argument passe a `GetUtility` est **litteralement `7`**, il n'y a jamais eu de
composite de mouvement a reduire.

**Consequence structurelle** : la route ajoute ensuite `u_full = u + Tile(tuile candidate)`, donc le
terme de la tuile candidate **s'annule exactement** et l'utilite d'action porte
`Tile(tuile de la CIBLE) + <predictions>`. C'est la tuile que le caster occupera APRES l'echange de
positions — la formule dit exactement ce que l'ability fait.

**3. Le gate.** `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$ShouldExecute` (slot **+0x328**,
mesure) est un OVERRIDE non trivial, a deux branches :

```
sel = TargetsSelector.SelectFirst(SorcerousFacadeAbility.GetTarget(ability),
                                  entities{Caster=caster, CasterTile=casterTile,
                                           CasterTiles=[casterTile]});
if (sel == null) {
    uTarget = GetUtility(7).EvaluateMovement(case(caster, GetMainTile(target)));
    foreach (t in battleQuery.<slot d'interface 0xa>(caster, false, null))
        if (GetUtility(7).EvaluateMovement(case(caster, t)) > uTarget) return false;
}
return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);
```

- le **slot d'interface `0xa`** est `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovableTilesOf`.
  Il avait d'abord ete identifie PAR ELIMINATION (collection de TUILES, 3 arguments, 3e argument nul
  tolere — `GetMovableTilesFor` dereference le sien, `GetCurrentAndMovablePositionsFor` est un AUTRE
  slot) ; il est desormais **MESURE** (`probe_27_4e_facade_vtable.py` : `interfaceOffset` = 4
  revalide par les deux ancres `IsMeleeAttack`@6 et `GetAdjacentTiles`@0x53, puis lecture de l'index
  0xe). Mirror : `ctx.reach_nc` (origine + tuiles de move).
- `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` (surcharge 4-args) =
  `new ProbableDamageEvent(target, battleQuery.<slot 0x21>(caster, target, casterTile))
  .Prediction.WillBeKill`, avec `target == null -> false`. Le `target` est ici la cible de
  l'ABILITY, donc l'**ALLIE** : le natif refuse le cast quand l'attaque normale du caster tuerait
  l'allie vise. Ce n'est pas une paraphrase — c'est le 3e argument du call natif.

**4. La prediction.** `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions`
(slot **+0x358**, mesure) est aussi un override, et c'est le fait qui change tout :

```
sel = SelectFirst(GetTarget(ability), entities{Caster, CasterTile=casterPosition.MainTile, ...});
if (sel == null) return <liste VIDE statique>;
list = [ new ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel, casterPosition)) ];
list.AddRange(GenerateMultiHitAttackPredictions(
                  caster, casterPosition, sel,
                  targets = DSLSelectors.Get(sel),                        // mono-cible
                  damage  = Half(Sum(GetVariableForLevel(0xc = minDmg),
                                     GetVariableForLevel(0xd = maxDmg))),
                  hits    = GetNumberConstant(0x2f = nrOfHits),
                  profil  = <vide>));
return list;
```

**La prediction ne porte PAS sur la cible de l'ability** (l'allie) mais sur `sel`, l'ennemi le plus
proche attaquable a l'attaque normale. L'utilite d'action de 1100 contient donc l'attaque normale
COMPLETE plus le coup psychique : c'est ce qui la rend competitive, et c'est pourquoi la traiter
comme un membre « sans prediction » (le regime de Chronometron) divergerait systematiquement.

Le selecteur `SorcerousFacadeAbility$$GetTarget` est **le MEME arbre que la face COMBAT** —
`...SorcerousFacadeAbility$$ExecuteBehaviour` le re-inline mot pour mot pour alimenter son
`UseActiveAbility(caster, sel, UnitNormalAttackType(caster))` :

```
Cache(First(SortByDistance(ValidNormalAttackTargets(Caster, CasterTiles, range: null,
                                                    ignoreRule, additionalRule),
                           Caster),
            1),
      true)
```

`IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` se resout en
`TargetingQuery.GetValidTargets(caster, casterTiles, <options de l'attaque normale>)` — le mirror
OFFLINE/LIVE est `ctx.plans` (les `attackPlans` de l'attaque normale portent deja la cascade de
ciblage native), FILTRE sur la tuile candidate.
`IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select` trie par
`PositionComponent.Distance(<reference>, GetMainTileId(s))` ou la reference est le selecteur
`Caster` : la distance est prise a la **position REELLE** du caster, pas a la tuile candidate (meme
quirk d'ancrage que Chronometron/SavageEchoes). `OrderBy` LINQ etant stable, l'ordre d'enumeration
tranche a distance egale.

#### La route — ouverte SANS toucher au VETO #217

Le diagnostic des tranches precedentes (« il faut une route de ciblage ALLIE, `_bespoke_candidates`
facon #82 ») etait faux d'un cran. Le critere de la route non-attaque (#27-4b) n'est pas « l'ability
n'a pas de `damageProfile` » — c'est « l'ability est ABSENTE de `ctx.plans` », donc invisible de
`_best_attack`. Le VETO #217 met 1100 exactement dans ce cas, et l'enumeration de cette route passe
par `ctx.ability_targets` (RPC natif `abilityTargets` en live, `ability_targets_offline` sinon), qui
rend deja les ALLIES depuis #217.

Il n'a donc fallu creer AUCUNE route neuve. La seule modification structurelle est de rendre la
route existante **fidele a `CalculateActionUtility`** : elle somme desormais
`custom + CalculateUtilityFromPredictions(MakeDamagePredictions(...))`, alors qu'elle ne portait que
`custom`. C'est un **no-op exact pour Chronometron** (sa liste de predictions est vide) — re-mesure,
cf. §Validation.

`ComparablePlaybook.calculate_utility_from_predictions` est EXTRAIT de `calculate_action_utility`
(meme code, meme ordre) pour que les deux routes consomment le MEME terme.

#### Le piege qui a coute une passe : `_PREDICT_VIA_NORMAL_ATTACK` n'est PAS vide

Le premier port deleguait le 2e event a `prediction.make_damage_predictions(..., 1100, ...)`. Or
`SorcerousFacade` est dans `_PREDICT_VIA_NORMAL_ATTACK` (pose par #171, parce que l'oracle
`aiPlaybookPredict` ne remonte que l'attaque normale pour 1100), donc ce chemin rend l'attaque
NORMALE et rien d'autre. Resultat : **deux events identiques**, `u_pred` moteur = **54.660** contre
`pairUtility(1100)` natif = **27.340** — le double EXACT, signature limpide une fois l'etage mesure.

Le commentaire de `prediction/abilities.py` affirmait noir sur blanc « `_PREDICT_VIA_NORMAL_ATTACK`
est VIDE (via_normal toujours False) ; la branche est conservee morte » — **faux depuis #171**.
Il est corrige dans ce commit. Le port construit desormais ses deux events lui-meme :
`make_normal_attack_predictions` pour le premier, `generate_multi_hit_attack_prediction(...,
profile_override="None")` pour le second. Le profil VIDE (`param_8` nul, meme quirk que
1020/1062/1147/1148) laisse l'armure PLEINE et le percage a 0 : sur `ultraTitus` (armure 2312) le
batch psychique vaut **1 point de degat**, d'ou les **+0.0105** d'utilite que le natif ajoute a
l'attaque normale — et cette valeur minuscule est elle-meme une CORROBORATION du profil vide.

Aucune entree n'est posee dans `_PLAYBOOK_PROFILE_OVERRIDE` pour 1100 : elle serait INERTE (le
court-circuit `via_normal` intervient avant la consommation des overrides). Un commentaire l'y
remplace, pour que la prochaine lecture ne la re-pose pas.

#### Ce que le port NE fait pas

La regle dynamique (`...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` : `HasTrait(target,
0x3ea = Psyker)` ET le caster doit pouvoir porter son attaque normale depuis les tuiles de cast)
n'est pas portee — elle vit sur la classe d'ability, hors registre COMBAT. En LIVE c'est sans effet
(le RPC rend l'ensemble natif EXACT) ; en OFFLINE PUR (`ability_targets_offline`) l'ensemble reste
un SUR-ENSEMBLE des allies, degradation permissive deja documentee par #217. S'y ajoute un second
ecart offline-pur : `_ability_reach` derive la portee du gameconfig (`attackRangeType: Normal` ->
portee d'arme = 2) alors que le masque dit **whole board** — l'ensemble offline est donc, sur cet
axe, un SOUS-ensemble. Les deux ecarts sont hors du chemin LIVE valide ici.

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
- **SorcerousFacade (1100)** — A/B causal live `probe_27_4e_facade_ab.py`, board **MC1_67** (elevation
  1..4, ou le composite Tile vaut 5 / 20 / 30 / 50), seed 1100, stats NATURELLES (aucun `--hp-target`,
  donc l'armure de la cible est INTACTE — c'est elle qui rend le profil vide observable). Caster
  `thousTzaangor` FIGE (un `act move` consomme son mouvement -> `aiMovableTiles` rend 0 tuile, le sweep
  est reduit a sa tuile courante), `ultraTitus` colle a **d=1** (la regle dynamique de 1100 exige que le
  caster puisse porter son attaque normale), `ultraCalgar` relegue en (6,0). **SEUL l'allie Psyker
  `thousSorcerer` bouge**, sur quatre tuiles d'elevations 1/2/3/4 **toutes a la MEME distance 4 du
  caster** — aucune feuille d'adjacence ne les distingue.

  | configuration | caster | Tile(caster) | allie | Tile(allie) | custom | natif | moteur | custom=0 | route OFF |
  |---|---|---|---|---|---|---|---|---|---|
  | `caster_bas` e1 | (2,7) elev 1 | 5 | (6,8) elev 1 | 5 | **0** | **69** | 69 | 69 | 69 |
  | `caster_bas` e2 | (2,7) elev 1 | 5 | (5,5) elev 2 | 20 | **+15** | **1100** | 1100 | **69** | **69** |
  | `caster_bas` e3 | (2,7) elev 1 | 5 | (1,4) elev 3 | 30 | **+25** | **1100** | 1100 | **69** | **69** |
  | `caster_bas` e4 | (2,7) elev 1 | 5 | (2,3) elev 4 | 50 | **+45** | **1100** | 1100 | **69** | **69** |
  | `caster_haut` e4 | (2,3) elev 4 | 50 | (6,3) elev 4 | 50 | **0** | **69** | 69 | 69 | 69 |

  - **ETAGE PREDICTION confronte, et il est BIT-IDENTIQUE** : `pairUtility(1100, allie)` natif
    **27.340392069891095** vs `CalculateUtilityFromPredictions` du port **27.340392** (config basse) ;
    **41.01058810483664** vs **41.010588** (config haute). C'est cette mesure — et pas la bascule — qui a
    attrape le piege `_PREDICT_VIA_NORMAL_ATTACK` : avant correction, le port rendait **54.660**, le
    double EXACT (deux fois l'attaque normale). Decomposition : event #1 = attaque normale
    `[1623,3591]` -> 27.33 ; event #2 = batch psychique a profil VIDE -> `[1,1]` de degat sur une
    armure de 2312 -> **+0.0105**. Le natif ajoute exactement 0.0105.
  - **Les `pairUtility(69)` natives sont bit-identiques entre les quatre bras** d'une meme
    configuration (27.329908800311387 en basse, 41.000104835256934 en haute) -> le confond de
    prediction est MESURE et NUL : deplacer l'allie ne touche ni l'etage paire, ni le terme Tile de la
    tuile du caster.
  - **CONTROLE CROISE — le terme est une DIFFERENCE, pas un bonus sur la tuile de la cible.** La MEME
    tuile d'allie (elevation 4, Tile = 50) donne **1100** avec un caster en elevation 1 et **69** avec
    un caster en elevation 4. Un terme qui ne lirait que la tuile de la CIBLE rendrait le meme choix
    dans les deux cas. C'est l'equivalent, pour un terme en difference, du test de linearite de
    HeavyWarpFlamer.
  - **Encadrement sans fitting.** Le caster ne bougeant pas, `u_action(69) = pair(69) + Tile(caster) + 1`
    et `u_action(1100) = Tile(allie) + P` avec `P` = l'etage prediction mesure ci-dessus. La frontiere
    theorique du custom est donc `1 + pair(69) - P` = **0.98952** en configuration basse
    (`1 + 27.329909 - 27.340392`) et **0.98952** en configuration haute (`1 + 41.000105 - 41.010588`) —
    la MEME valeur, ce qui est attendu puisque `P - pair(69)` est le batch psychique, invariant.
    L'observation encadre cette frontiere dans **(0, 15]** : le natif refuse 1100 a custom = 0 (deux
    fois, dans deux configurations independantes) et l'accepte des custom = +15. Aucune constante n'est
    ajustee — les valeurs de `Tile` viennent du composite deja porte, `P` et `pair(69)` du scoreur natif.
  - **Les deux contre-epreuves** : `custom` force a 0 -> le moteur revient sur 69 dans les trois bras ou
    1100 gagnait (**terme NECESSAIRE**) ; `NONATTACK_PLAYBOOKS` vide -> le moteur rend 69 partout
    (**la route est bien le deblocage** ; sans elle, 1100 ne passe par aucune autre voie).
  - **NON-REGRESSION #217, dans le MEME montage** : cote natif, les evals `(1100, ennemi)` de
    `decisionView.attackPlans` sont presentes mais toutes a `rankCount = 0` dans les 5 bras (le gate
    `IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` fait son travail, et `_best_attack`
    les saute) ; cote port, `_is_attack_ability(1100)` reste **False**, `_ability_kind` reste **`ally`**,
    1100 n'entre pas dans `_attack_abilities('thousTzaangor')`, et `ctx.plans` ne porte aucune eval
    rankable. Le veto est INTACT — le port l'a contourne par la route alliee, il ne l'a pas affaibli.
- **SorcerousFacade, non-regression de Chronometron** (la route `nonattack_candidates` a change : elle
  somme desormais les predictions). `probe_27_4b_chronometron_ab.py --build --engine` rejoue APRES le
  changement : **4/4 bras MATCH**, linearite PROUVEE (n=1 -> 10, n=2 -> 20), terme NECESSAIRE, route
  NECESSAIRE, encadrement inchange **6.8781 < W < 13.7562**. Le no-op est donc mesure, pas seulement
  argumente (les predictions de 1226 sont vides -> le terme ajoute vaut 0).
- **SorcerousFacade, non-regression du refactor `ComparablePlaybook.calculate_utility_from_predictions`**
  (extraction pure de `calculate_action_utility`, consommee par les DEUX routes) —
  `engine_agreement_stages.py --build` : seed **31337** prediction **4/4**, utilite **4/4**, ability
  **4/4**, move **10/10** (100 % partout) ; seed **777** ability **8/8**, utilite **6/6**, move 10/11,
  prediction 3/6 (les etages prediction/move de 777 sont une derive PRE-EXISTANTE de `origin/master`,
  cf. les mesures des tranches precedentes).
- **Vtables MESUREES** : `probe_27_4e_facade_vtable.py` — les trois slots du playbook
  (`+0x328` ShouldExecute, `+0x338` CalculateCustomUtility, `+0x358` MakeDamagePredictions) pointent
  bien sur des corps `SorcerousFacadePlaybook` ; les deux ancres d'`interfaceOffset` d'`IBattleQuery`
  sont revalidees dans le meme dump (`IsMeleeAttack`@6, `GetAdjacentTiles`@0x53) ; et le slot
  d'interface `0xa` de `ShouldExecute` est **`GetCurrentAndMovableTilesOf`** (index de vtable 0xe),
  ce qui CONFIRME l'identification faite par elimination au decompile.
- **Garde LIVE 1100** : `tests/engine/test_sorcerous_facade_decision_live.py` — 8 tests, **8 PASS**
  (108 s) : accord moteur/natif sur les 5 bras, egalite de l'etage prediction a 1e-6, bascule du natif
  avec la difference de tuiles, controle croise (difference vs bonus de cible), necessite du terme,
  necessite de la route, fermeture de la route ennemie (#217), selecteur + gate exerces.
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
- **La route non-attaque a QUATRE membres** (1226, 1185, 1100, 1009). Le residu restant du groupe
  (1053) garde son verrou PROPRE, nomme ci-dessus. (1212, qu'on y rangeait, n'en relevait pas : c'est
  un soin, il entre par `_heal_candidates` — cf. TRANCHE 4d.)

- **Le critere de la route, RECTIFIE par la mesure de #289.** On lisait « Comparable ABSENTE de
  `ctx.plans` ». C'est exact du cote OFFLINE (`state_bridge._is_attack_ability` rend False), mais
  **FAUX en LIVE** : `decisionView.attackPlans` LISTE bien 1009 — a `rankCount = 0`, et sur des
  ENNEMIS uniquement, alors que la cible que le natif retient est le CASTER. Le critere OPERANT, vrai
  dans les DEUX regimes, est : **`_best_attack` ne peut pas la rendre**, parce que
  `make_damage_predictions` rend `[]` et que `calculate_action_utility` rend donc `None`. Garde :
  `test_resurrection_orb_decision_live.py::test_best_attack_can_never_yield_the_orb`.

- **L'override NEUF encore non porte du build `rnca9r7q6c`** : `MassDriverAccelerator` (1222,
  votanChampion — verrou : evaluateur du selecteur DSL `MassDriverAcceleratorAbility$$GetBuffTargets`).
  `ResurrectionOrb` (1009) est PORTE par #289 — voir la tranche dediee ci-dessous.
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
- **SorcerousFacade (1100)** : **PORTE (#27-4e)** — le custom, le gate `ShouldExecute` et les deux
  events de `MakeDamagePredictions`. Ce qui reste NON couvert sur cet item :
  - ~~la **regle dynamique** `...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason`~~ — **PORTEE
    par #287** (`SorcerousFacadeAbility.get_dynamic_invalid_target_reason`), et ce n'etait pas
    cosmetique : le bras `--far-foes` du probe #287 mesure le natif REFUSER EN SILENCE un cast que le
    port executait entierement. Detail : `case-287-sorcerous-facade-combat.md` §2 ;
  - la **portee du masque** (`TargetingRange` whole board) n'est pas consommee par `_ability_reach`,
    qui derive de `attackRangeType: Normal` -> portee d'ARME (2). Ecart OFFLINE PUR seulement. Il se
    fermera le jour ou `ability_targets_offline` lira le masque plutot que le gameconfig ;
  - ~~la **face COMBAT**~~ — **PORTEE par #287** : 1100 entre dans `ABILITY_CLASSES`, son masque
    MIGRE de `TARGETING_OPTIONS_UNPORTED` vers la classe (contrat de disjonction respecte) et
    `ABILITY_ATTACK_TYPE[1100] = Others` est pose dans le meme commit. La face DECISION est
    INCHANGEE (meme valeur de masque, seule la SOURCE change) — re-jeu
    `test_sorcerous_facade_decision_live.py` 8/8. Detail : `case-287-sorcerous-facade-combat.md` ;
  - `CalculateCasterPositionUtility` (+0x348) et `CalculateUtilityFromTilePrediction` restent hors port
    pour 1100 comme pour Chronometron (corps de base partages, non nommes, non overrides ici).
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

**Un commentaire qui dit « cette branche est morte » est une AFFIRMATION, pas une mesure — et il
peut avoir peri.** `prediction/abilities.py` portait, en toutes lettres, « `_PREDICT_VIA_NORMAL_ATTACK`
est VIDE (via_normal toujours False) ; la branche est conservee morte ». L'ensemble contenait
`SorcerousFacade` depuis #171. Un port qui delegue la prediction de 1100 a cette fonction recoit donc
l'attaque NORMALE au lieu du batch propre de l'ability — et le symptome est *silencieux* : deux events
plausibles, aucune exception, un choix d'action qui a l'air simplement « un peu trop favorable ».
Ce qui l'attrape en une mesure : **confronter l'ETAGE prediction, pas la bascule**. `pairUtility(<id de
l'ability>, cible)` est le scoreur natif de cet etage exactement ; le port doit l'egaler a 1e-6. Ici le
port rendait **54.660** contre **27.340** — un facteur 2 EXACT, qui nomme le bug tout seul. Sans cette
confrontation, la seule chose visible aurait ete « le moteur choisit 1100 partout », qu'on aurait pu
attribuer au custom, au terme Tile, au gate... Regle : **avant de suspecter le terme qu'on vient de
porter, mesurer l'etage qu'on a REUTILISE.**

**Une route de dispatch se caracterise par ce qu'elle CONSOMME, pas par le motif de l'item qui l'a fait
naitre.** La route non-attaque (#27-4b) est nee pour les abilities SANS `damageProfile`, et la fiche
l'avait ecrite comme ca — d'ou trois tranches a repeter « la route non-attaque ne debloque pas 1100,
il lui faut une route ALLIEE dediee facon `_bespoke_candidates` ». Faux d'un cran : son critere reel
est « ABSENTE de `ctx.plans` », et le VETO #217 y met precisement 1100. Le port a donc coute *zero*
route neuve — seulement de rendre la route existante fidele a `CalculateActionUtility` (y sommer
`CalculateUtilityFromPredictions`, no-op mesure pour l'item deja porte). **Avant de construire une
seconde route, verifier si l'existante ne discrimine pas deja sur le bon critere** : le cout d'une
route en trop, ce n'est pas la duplication, c'est deux endroits ou l'ordre des termes peut diverger.

**Un terme en DIFFERENCE se refute par un CONTROLE CROISE, comme un terme lineaire se refute par
n=1/n=2.** `custom = Tile(cible) - Tile(candidate)` et « custom = bonus si la cible est sur une tuile
haute » font la MEME prediction tant qu'on ne bouge que l'allie. Le bras qui separe : rejouer la MEME
tuile de cible avec le caster sur une tuile de MEME elevation — le terme en difference tombe a 0 et le
natif change d'avis, le terme-bonus ne bougerait pas. C'est trois lignes de montage, et c'est la
seule chose qui distingue « la formule est juste » de « la formule est compatible avec ce que j'ai
mesure ».

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

## TRANCHE 289 — `ResurrectionOrb` (1009, `necroOverlord` « Anuphet ») : PORTE

`IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$.ctor` =
`ComparablePlaybook<...>$$.ctor(this, 0x3f1, ...)` -> **COMPARABLE** (0x3f1 = 1009). Le playbook
n'override que `CalculateCustomUtility` ; l'`EvaluateNonComparable`/`GetUseProbability` de
`gqfc5mff6c` a disparu **avec le changement de famille NonComparable -> Comparable**.

### La formule, mirror 1:1 du decompile

    u   = Fix64.Zero
    ctx = zeroed(0x128) ; ctx.caster = caster ; ctx.casterPosition = casterPosition
    if Count(ability.GetPossibleResurrectTargets(), ctx) > 0:
        if Count(ability.GetPossibleSpawnOrResurrectTiles(), ctx) > 0:
            u += GetUtilityValue("ResurrectionOrb_LikesResurrection")           # 90
    u += Fix64(ability.GetNumSummonsFormula().Calculate(ctx))
         * GetUtilityValue("ResurrectionOrb_LikesSummoning")                    # x 10

Trois faits que le corps etablit :

1. **`target` et `possibleTargets` ne sont PAS lus** — l'utilite est CONSTANTE sur les cibles et
   VARIE sur la tuile balayee. C'est la TUILE que l'argmax discrimine, pas la cible.
2. **Le terme summoning est inconditionnel et MULTIPLICATIF** ; le terme resurrection est un forfait
   BOOLEEN sous une CONJONCTION (>=1 cible resurrectable ET >=1 tuile posable).
3. Les selecteurs/formules ne sont PAS redefinis cote playbook : ce sont les arbres DSL de
   l'ABILITY. Un seul artefact natif, un seul port (`runner/abilities/necrons.py`), deux
   consommateurs — meme doctrine que `SavageEchoesAbility.get_damage_formula`.

### Les arbres, relus sur `rnca9r7q6c` — et TROIS corrections du port `gqfc5mff6c`

| Artefact natif | Arbre |
|---|---|
| `$$GetPossibleResurrectTargets` | `Filter(Friends(AllDeadUnits, caster@0x48), HasTrait(It@0x68, 0x10=Hero) & IsMechanical(It@0x68))` |
| `$$GetPossibleSpawnOrResurrectTiles` | `CanAddUnit(AdjacentTiles(casterTile@0x58))` |
| `$$GetMaxSummonsFormula` | `Min(Sum(Count(Filter(Friends(AllDeadUnits, caster), IsMechanical(It))), StatAmount(caster, 0xc=TURNS_STARTED)), Direct(GetNumberConstant(0x3c)=maxSummons))` |
| `$$GetNumSummonsFormula` | `Min(GetMaxSummonsFormula, If(AmountIsGreaterThanZero(GetPossibleResurrectTargets), Count(tiles) - Direct(1), Count(tiles)))` |

Le port ecrit sur `gqfc5mff6c` divergeait sur trois points, **tous relus au decompile du build
courant** (c'est le natif qui a change, pas la lecture) :

1. `AllDeadUnits` (`AllDefeatedUnitsSelector`) et non `AllDeadOrResurrectedUnits` — deux factories
   natives distinctes ; la seconde ajoute les ressuscites (flag `0xe`), qui sont VIVANTS.
2. `Filter(..., IsMechanical)` et non `UnitsWithTrait(LivingMetal)` — `UnitExtensions$$IsMechanical`
   = `HasTrait(5) || HasTrait(0x3e8=1000 LivingMetal) || HasTrait(0x405=1029 Vehicle)`. Un allie
   mort `Mechanical` non-`LivingMetal` (9 tels heros dans le pool rank 17, ex. `admecMarshall`)
   comptait a tort pour zero.
3. cap = `ConfigConst(maxSummons)` = **5** et non `Direct(6)` : le cap est passe LITTERAL -> CONFIG
   entre les deux builds. La constante figee etait devenue fausse en silence.

⚠ **`GetNumSummonsFormula` est PUREMENT AI** : son unique xref native est
`ResurrectionOrbPlaybook$$CalculateCustomUtility`. `$$ExecuteBehaviour` cape, lui, par
`GetMaxSummonsFormula` DIRECTEMENT (`First(tiles, GetMaxSummonsFormula(), 0)`) — les deux faces
n'utilisent PAS le meme compte, et c'est le natif qui le veut. Ne pas « harmoniser ».

`maxSummons` = i2 mot a mot : « summons 1 Necron Warrior **for each round that has started** » (le
compteur per-unite `UnitComponent.turnsStarted@+0x58`) « + 1 more for each friendly unit with the
trait Living Metal **that was defeated** in this battle ». La lecture `StatAmount(caster, 0xc)` etait
la plus surprenante du RE : c'est le TEXTE DU JEU qui l'a confirmee, pas une intuition.

### Ce que la confrontation LIVE a mesure (`probe_289_resurrection_orb.py`)

Deux bras RIGOUREUSEMENT identiques (meme seed, meme board `MC1_67`, meme tour adverse joue, donc
meme `TURNS_STARTED`), a UNE chose pres : l'allie `necroWarden` (Hero + LivingMetal) est mort ou non.

| bras | natif | moteur | `nResurrect` | `maxSummons` | `numSummons` | custom |
|---|---|---|---|---|---|---|
| VIVANT | `69@81` (attaque) | `69@81` MATCH | 0 | 2 | 2 | 20 |
| MORT | `1009@83` (self) | `1009@83` MATCH | 1 | 3 | 1 | 100 |

- **BASCULE native causee par le seul forfait resurrection** : `pairUtility(69)` BIT-IDENTIQUE d'un
  bras a l'autre (45.632215263321996) — le confond de prediction est MESURE et NUL.
- **Terme NECESSAIRE** (custom force a 0 -> le moteur retombe sur `69@81` alors que le natif dit
  1009) et **route NECESSAIRE** (`NONATTACK_PLAYBOOKS` vide -> idem).
- **LINEARITE** : le custom releve tuile par tuile prend 3 valeurs (100/110/120) — un terme constant
  ou purement booleen est exclu.
- **Une tuile est RESERVEE** : a `nTiles` egal, le bras MORT summon UN de moins (`numSummons` 2 -> 1).
  C'est le `Count(tiles) - 1` du `If`, observe et non suppose.
- Encadrement : `pair + 1 = 46.63` tombe entre 20 (VIVANT) et 100 (MORT) — coherent avec 90 / 10.

Garde : `tests/engine/test_resurrection_orb_decision_live.py` (11 tests).

### Residus nommes

- **La face COMBAT de 1009 a DRIFTE et n'est pas re-portee** (hors perimetre #289, qui traite la
  DECISION). `$$ExecuteBehaviour` du build courant fait
  `SortByFormula(tiles, MinDistance(It, NormalUnits(Enemies(caster))))` puis
  `SortTilesByUtilityForSummon(., 7, caster)` puis `First(., GetMaxSummonsFormula(), 0)` — un TRI
  deterministe la ou le port a garde le `PickRandomly` de `gqfc5mff6c` — et il PRECEDE le spawn d'un
  `GetResurrectBehaviour(...)` (resurrection d'un heros mecanique allie mort, `PickRandomly(1)`, PV =
  `PercentageOf(StatAmount(cible, Health, max), variable 0x26)`), entierement absent du port. Le
  verdict « SUMMON PUR — aucune resurrection » de `necrons.py` etait juste sur `gqfc5mff6c` et est
  desormais FAUX ; il est corrige sur place.
- **Le 4e argument d'`UnobscuredEntitiesSelector`** (le `caster` que `DSLSelectors$$CanAddUnit` lui
  passe) n'est pas RE : le port compte comme occupee la tuile de toute unite vivante. Le playbook
  contourne en DEPLACANT le caster sur la tuile candidate dans son `DslContext` (mirror du
  `casterPosition`), ce qui rend le compte juste des deux cotes ; mais la semantique exacte du
  parametre reste a lire.
- **Le terme resurrection sur un allie `Mechanical` NON-`LivingMetal`** (correction 2 ci-dessus) n'est
  pas confronte LIVE : le montage utilise `necroWarden`, qui porte les deux traits. Les 9 heros
  `Mechanical` sans `LivingMetal` du pool rank 17 rendraient ce bras discriminant.
- **Le cap `maxSummons = 5` vs l'ancien `6`** n'est pas confronte LIVE non plus : il faudrait
  `Count(morts mecaniques) + TURNS_STARTED >= 6`, hors de portee du montage a deux tours.

## TRANCHE 4g (2026-07-30) — `PlasmaGrenade` (1098) PORTE, et le VERROU 4 tombe pour de bon

### L'inventaire, RE-DERIVE du binaire (et deux entrees qui en SORTENT)

`probe_27_custom_utility_inventory.py --build rnca9r7q6c` : **388** classes `*Playbook*`, **96**
portent le slot, **toutes a `+0x338`**, **29 corps distincts** = **26 nommes** + 3 partages (base,
attaque normale, heal generique). Ventilation des 26 nommes : **17 portes/couverts**, **4** npc-only,
**1** dead-code, **3 residus** (1148, 1169, 1004), **1** en cours (1222).

**Deux entrees quittent la liste des residus sans qu'aucun port ne les ait fermees** — c'est une
correction d'inventaire, et elle se lit au `.ctor` :

- **1142 `MalleusRocketLauncher` n'a AUCUN corps propre.**
  `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$.ctor` appelle
  `ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this, 0x41b, klass)` — **1051
  SEULE** — et aucune classe `Malleus*Playbook` ne porte le slot dans le balayage runtime. Le
  « playbook PARTAGE 1051/1142 » ecrit en tranche 3 est **FAUX sur ce build** : il n'y a rien a
  porter pour 1142 cote `CalculateCustomUtility`. (Le meme controle vaut l'inverse :
  `PlasmaGrenadePlaybook$$.ctor` -> `0x44a` = 1098, un seul id.)
- **1053 `DevoutPush`** partage le corps de `ALoki_NormalAttackPlaybook<T>` (= `Fix64(1)`), deja
  couvert par `common.NormalAttackPlaybook`.

⚠ **Le `--build` par defaut du probe reste le PIEGE nomme en tranche 4** : lance sans
`--build rnca9r7q6c`, il croise les RVA du runtime contre l'ANCIENNE table et rend un tableau
coherent et entierement faux.

### `PlasmaGrenade` (1098) — la formule, relue VERBATIM

`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` :

```
formula = DSLFormulas.Get(GetVariableForLevel(config, 0xc = minDmg));   // == Direct(minDmg)
hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2);
profile = GetDamageProfile(config);
ownerId = OwnerComponent.get_CurrentPlayerEntityId(caster);
u = Fix64.Zero;
foreach (e in battleQuery.<slot itf 0x7d>(target, ownerId, ignoreSteppables: false))
    foreach (p in GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                      <selecteur Target>, formula, hits2, profile, null, null))
        u = Fix64.op_Addition(u, CalculateUtilityFromDamageEvent(p, caster, casterPosition));
if (u == Fix64(0)) u = BaseUtility.<statics+0x18>;
return u;
```

soit **`u = n x U(1 coup sur la CIBLE)`**, `n` = nombre d'ENNEMIS DU CASTER adjacents a la CIBLE.
C'est le MOLD de Stikkbomb (1051) avec **trois differences qui changent tout** :

| | Stikkbomb (1051) | PlasmaGrenade (1098) |
|---|---|---|
| sous-set | arbre DSL `AdjacentUnits(Target)` **partage avec la face COMBAT**, filtre par un `IsFriend` imperatif | appel `battleQuery` DIRECT `GetAdjacentEnemies` — **aucun arbre DSL**, donc rien a partager |
| qui est compte | les **AMIS** (caster inclus) | les **ENNEMIS** |
| signe | `op_UnaryNegation` FINAL (penalite de tir ami) | **positif** (bonus de groupement) |
| somme nulle | rend `Fix64(0)` (utilite nulle) | rend une **SENTINELLE** -> aucune action |

Les entrees de prediction, elles, sont IDENTIQUES (`minDmg` seul, `nrOfHits_2` coups, selecteur
`Target` -> mono-cible, profil de config) : un seul foyer de port,
`prediction/abilities.py::make_secondary_multihit_event` (renomme de `make_stikkbomb_splash_event`,
qui n'etait plus un nom vrai).

### Le VETO — trois constantes de `BaseUtility` qu'il fallait lire, pas deviner

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
teste le custom contre TROIS valeurs **avant toute prediction** :

```
u = CalculateCustomUtility(vtable +0x338)(...)
if (u == BaseUtility.<statics+0x18>) return null;      // Nullable VIDE
if (u == BaseUtility.<statics+0x20>) return null;      // Nullable VIDE
if (u == BaseUtility.<statics+0x10>) return Nullable(BaseUtility.<statics+0x10>);
```

et `IdunBattle.AI.Utilities.BaseUtility$$.cctor` les derive de `FixMath.NET.Fix64$$.cctor`
(`Fix64.<statics+0x10>` = `0x7fffffffffffffff` = MaxValue, `Fix64.<statics+0x18>` =
`0x8000000000000000` = MinValue) :

    BaseUtility.<statics+0x10> = Fix64.MaxValue
    BaseUtility.<statics+0x18> = Fix64.MinValue / Fix64.FromIntFraction(1000001, 1000000)
    BaseUtility.<statics+0x20> = Fix64.MinValue

Ce ne sont donc pas des utilites tres basses **qui perdraient la comparaison** : ce sont des VETOS
qui SUPPRIMENT l'action. 1098 rend `<statics+0x18>` des que sa somme vaut `Fix64(0)`.

Port : `playbook/base.py::NO_ACTION`, une IDENTITE (`is NO_ACTION`) et non un flottant proche de
`-2**31` — la comparaison native est une egalite EXACTE sur un Fix64, qu'un port `float` ne peut pas
reproduire, et une valeur tres negative laissee dans l'arithmetique serait SOMMEE aux termes suivants
au lieu d'annuler l'action. Consomme par `ai/action_generators._action_utility` (qui calcule desormais
le custom **AVANT** `calculate_action_utility`, comme le natif) et par `playbook/nonattack.py`.

**Classification DSL/imperatif** (tranchee AVANT de coder) : `CalculateCustomUtility`,
`GetAdjacentEnemies` (methode de `BattleQuery`) et la chaine de prediction sont des METHODES, pas des
arbres `DSLFactory` -> **imperatif**, mirror 1:1. Aucun noeud declaratif sur ce chemin — contrairement
a Stikkbomb, dont le sous-set EST un arbre et devait donc etre partage avec la face COMBAT.

### Le slot d'interface se RE-DERIVE, il ne se recopie pas

`probe_27_4g_battlequery_slots.py` (neuf) balaie la vtable PROPRE de
`IdunBattle.Core.Services.BattleQuery` au runtime et rend, sur `rnca9r7q6c` :

| slot d'interface | index de vtable | methode |
|---|---|---|
| 0x7a / 0x7b / 0x7c | 0x7e / 0x7f / 0x80 | `GetAdjacentUnits` (**AMIS COMPRIS**) |
| **0x7d** | **0x81** | **`GetAdjacentEnemies(IEntity from, BEntityId playerEntityId, bool)`** |
| 0x7e / 0x7f / 0x80 | 0x82 / 0x83 / 0x84 | `GetAdjacentEnemies` (autres surcharges) |
| 0x81 | 0x85 | `GetAdjacentFriends` |
| 0x8e | 0x92 | `GetAllEnemiesOf` |

La conversion `+4` est CONFIRMEE par les deux ancres independantes du probe (slot 0x02 -> index 0x06
`IsMeleeAttack` ; slot 0x4f -> index 0x53 `GetAdjacentTiles`). **Un decalage d'UN slot inverserait la
semantique en silence** (`GetAdjacentUnits` compte les amis) : c'est exactement le piege que la note
de fidelite HeavyWarpFlamer decrivait, et il est desormais outille.

### Porteur GREFFE, et pourquoi ca reste une mesure

Les deux seules unites qui portent 1098 sont `eldarSmnGuardian` (SUMMON) et `eldarNpc1Guardian`
(npc) ; le summon n'a pas d'invocateur et `buildNormalizedBC` refuse les deux. Porteur GREFFE sur
`eldarAutarch` (Aeldari, pool) — `case-92` §5bis. Le natif charge le playbook PAR ABILITY et il le
PROUVE en emettant `ActiveAbilityMessage(1098)`. La formule ne lit **ni stat ni trait du caster**
(uniquement le board et la config d'ability), donc la greffe ne la deforme pas.

### Validation — A/B causal live, 3 bras, 3 issues DIFFERENTES

`probe_27_4g_plasma_grenade_ab.py --build --engine --tirages=18` (board MC1_67, seed 909, runner 201).
CASTER et CIBLE PRINCIPALE **FIGES** en (2,4) et (4,4) ; seuls les deux autres ennemis bougent.

| bras | n(A) | cibles LEGALES (natif) | natif (18 tirages) | moteur | verdict |
|---|---|---|---|---|---|
| **C0** | 0 | **{A}** — A est legale | `FinishUnitTurn` **18/18**, 1098 **JAMAIS** | `(None, None)` | **MATCH** |
| **C1** | 1 | {A, B} | `1098 -> B` (9/18) | `(1098, B)` | **MATCH** |
| **C2** | 2 | {A, B, C} | `1098 -> A` (8/18) | `(1098, A)` | **MATCH** |

Ce que chaque bras etablit, et pourquoi il ne peut pas passer par accident :

- **C0 prouve le VETO dans le regime le plus exigeant** : la cible EST legale (`abilityTargets` la
  rend) et `pairUtility(1098, A)` = **13.553077075630426** — une utilite qui aurait largement gagne
  contre une attaque normale a `pairUtility` **0**. Le natif ne propose pourtant JAMAIS 1098.
  A `p = 1/3`, `0/18` a une probabilite `(2/3)^18 ~ 7e-4`.
- **C2 prouve la LINEARITE par RENVERSEMENT** : `pair(1098, A) = 13.553077 < pair(1098, B) =
  15.940501`, et le natif prend pourtant **A** — la cible dont la `pairUtility` est la plus FAIBLE,
  parce qu'elle a DEUX voisins ennemis au lieu d'un. `u(A) = 13.553 + 2 x 6.777 = 27.106` contre
  `u(B) = 15.941 + 1 x 7.970 = 23.911`.
- **Confond de prediction MESURE et NUL** sur les deux cibles de l'arbitrage : `pairUtility(1098, A)`
  et `pairUtility(1098, B)` sont **BIT-IDENTIQUES** dans les trois bras. *(La 3e cible, elle, est
  DEPLACEE entre C1 et C2 : sa paire bouge, 15.056975 -> 10.045359. Le test le dit explicitement au
  lieu d'exiger une invariance fausse.)*
- **Recoupement quantitatif independant** : le port calcule `U(1 coup) = 6.776538538139812` (C1,
  n=1 sur A) la ou `pairUtility(1098, A) / 2 = 6.776538537815213` — l'ability a `nrOfHits = 2` et
  `nrOfHits_2 = 1`, donc l'event secondaire vaut exactement la moitie de la paire. Ecart **3.2e-10**
  (arrondi Fix64). Ce n'est pas un scalaire ajuste : c'est une consequence de la config, verifiee.

**Deux MUTATIONS ADVERSARIALES, vues ROUGES avant le fix** (le probe les rejoue a chaque run) :

1. **VETO DESARME** (le custom rend `0.0` — c'est-a-dire l'etat du port AVANT ce commit) : le moteur
   propose `(1098, A)` en **C0**, la ou le natif ne le fait JAMAIS. Degradation PERMISSIVE.
2. **TERME RENDU BOOLEEN** (`n` remplace par `min(n, 1)`) : le moteur bascule sur **B** en C2 alors
   que le natif dit **A**. Le montage separe donc bien lineaire et booleen — sans cette mutation,
   « lineaire » resterait une hypothese.

Garde : `tests/engine/test_plasma_grenade_decision_live.py` (8 tests).

### `PlagueburstMortar` (1169) — le verrou est RE-QUALIFIE, et il n'est pas celui qui etait ecrit

La fiche rangeait 1169 derriere le VERROU 1 (« MoW non modelisees comme unites de DECISION »). Ce
verrou-la se LEVE par la greffe — le natif charge le playbook par ABILITY. Une fois 1169 greffee sur
`deathTyphus` (Death Guard, pool), on voit le verrou SUIVANT, et il est ailleurs.

**Le custom, entierement lu** (`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility`) :

```
sel = PlagueburstMortarAbility.GetAdjacentEnemies();       // arbre DSL
n   = TargetsSelector.Count(sel, AbilityEntities(owner: caster, caster: caster, target: target));
return Fix64.op_Multiply(Fix64(n), GetUtilityValue("PlagueburstMortar_AdjacentEnemy"));
```

avec `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentEnemies` =
`Enemies(<caster>, Units(AdjacentTiles(<target>), unique: 1, sel: 3), sel: 3)` — c'est-a-dire
EXACTEMENT le second terme de `plagueburst_damage_targets` (face COMBAT, portee par #90) **sans** son
`Filter(GetIsValidAdjacentEnemyTrigger)`. Un seul artefact, deja porte : le jour ou le verrou tombe,
il n'y a rien a inventer. Poids : `PlagueburstMortar_AdjacentEnemy` = **10**.

> **Ancrage du slot 2** (`FUN_180025bf0(2, <klass>, selector, entities)` -> `uint`) :
> `IdunBattle.DSL.TargetsSelector$$Count`. Etabli par ANCRAGE et non par recopie —
> `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility` emet le MEME
> appel avec la MEME classe, et sa formule (`max(0, Count(GetBuffTargets) - 1) * W`) est deja RE.

**Ce que la mesure dit** (`probe_27_4g_plagueburst_route.py --build --hp-target=400000`, runner 260,
n(A) = 2 donc `custom` attendu = 20) :

| mesure | valeur |
|---|---|
| `abilityTargets(1169)` | **58 cibles, domaine `tile` a 100 %** (bit `TargetIsTile` du masque `0x40000042`) |
| `attackPlans` evals 1169 | `rankCount = 0` sur les **trois** cibles UNITE |
| `pairUtility(1169, *)` | **0** partout — `$$MakeDamagePredictions` passe `GetMainDamageTarget` = `Filter(..., GetIsValidAdjacentEnemyTrigger)`, predicat FAUX au spawn (ni aura `ContagionsOfNurgle_ArmorReduction1`, ni modificateur d'armure negatif) |
| `pairUtility(69, *)` | 0.79 a 1.02 (ecrasees par `--hp-target 400000`) |
| `aiDryRunAllUnits` x8 | **`ActiveAbilityMessage(69)` 8/8 — 1169 JAMAIS proposee** |

Le regime est pourtant maximalement favorable : `custom = 20` ecraserait `pair(69) + 1 ~ 2.02`. **Le
natif ne genere donc simplement pas d'action pour 1169 depuis une unite de decision normale** — et le
port ne le peut pas davantage (`_best_attack` consomme `ranked`, vide ; `nonattack.eligible_targets`
filtre `kind == "unit"`).

> **MISE A JOUR #302 — les deux lignes ci-dessus sont PERIMEES, et la seconde etait un artefact.**
> **(a)** `1169 est desormais PORTEE` (route de decision a cibles TUILE, tranche 1 de
> `docs/rl/case-302-route-cible-tuile.md`) : natif `(1169, tuile 43)` == moteur `(1169, tuile 43)`,
> garde `tests/engine/test_plagueburst_mortar_decision_live.py` (10 tests).
> **(b)** « le natif ne genere pas l'action » etait un **COOLDOWN non purge** : 1169 arrive avec
> `RemainingCooldownTurns = 1`, donc au tour du build elle est INDISPONIBLE. Deux fins de tour plus
> tard, le natif la propose **6/6**. Toute mesure « le natif ne propose jamais X » doit asserter le
> cooldown purge AVANT de conclure.

**VERDICT (perime, cf. l'encadre ci-dessus) : invalidable-residu, verrou re-qualifie.** Ce n'est pas « les MoW ne sont pas modelisees »
mais **le domaine de cible** : 1169 est TILE-TARGET, et la greffe — qui a leve le verrou porteur pour
1185 et 1051 — **ne le leve pas ici**. Debloqueur nomme, en DEUX pieces :

1. une route de decision a cibles **TUILE** (enumeration + format d'action + correspondance
   `id d'entite-tuile` <-> `(col, row)` pour confronter le choix natif) ;
2. le tacticien MoW (les MoW n'apparaissent ni dans `decisionView.units` ni dans `attackPlans`, et
   `aiDryRunAllUnits` ne leur propose rien — mesure #27 tranche 1, runner 336).

La piece (1) est un prerequis de la piece (2) et non l'inverse : c'est ce que cette mesure retourne
par rapport a la redaction precedente. **1148 `DaemonicOrdnance` est dans le meme cas** (porteur MoW ;
son custom, lu au passage, est `10 x |ennemis sur GetTargetAreaTiles|` — une CONSTANTE `Fix64(0xa)`
en dur, sans `GetUtilityValue` —, et sa zone est un `TilesInTriangleShape` non porte).

### Non couvert (explicite)

- **Le tirage `GetUseProbability` de 1098 n'est pas modelise.**
  `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$GetUseProbability` = `Fix64(1)/Fix64(3)`, et
  `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` en fait un TIRAGE (`p >= 1 -> true` ;
  `p <= 0 -> false` ; sinon `random(p)`). Le moteur offline est deterministe : il emet 1098 la ou le
  natif la saute ~2 fois sur 3. Meme statut que `...BlackRagePlaybook$$GetUseProbability` et
  `...ScarabSummonPlaybook$$GetUseProbability`. **Consequence sur la mesure** : l'accord se lit sur
  l'ENSEMBLE des cibles proposees au moins une fois sur K tirages, jamais sur un tirage isole.
- **La 3e sentinelle (`BaseUtility.<statics+0x10>` = `Fix64.MaxValue` -> `Nullable(MaxValue)`) n'est
  portee par AUCUN membre du registre** : elle est lue et documentee, pas implementee. Le jour ou un
  playbook la rend, il faudra un second cas dans `_action_utility`.
- **La greffe ne couvre pas** les stats, traits et armes du VRAI porteur d'1098 (`eldarSmnGuardian`).
  Elle est legitime ici parce que le terme ne lit ni stat ni trait du caster ; elle ne le serait pas
  pour une prediction de degat.
- ~~**`MakeDamagePredictions` de 1098 n'est pas re-porte**~~ — **FERME (#352, `case-352`)** : le
  playbook l'override bien, et l'ecart est desormais MESURE. Base = `Get(minDmg)` SEUL et hits =
  `GetNumberConstant(0x2f)` LITTERAL (porte par
  `prediction.abilities._plasma_grenade_inputs`) : natif `(402, 606, 2)` contre `(490, 734, 2)`
  pour le chemin generique. Son volet SECONDAIRE, lui, est **structurellement mort** (sélecteur
  `Enemies(caster@0x30, ...)` evalue sur un `AbilityEntities` au caster NUL) — 1 seul event, la ou
  1051 en rend 3 sur la MEME geometrie. Cette classe n'a donc PAS de `make_damage_predictions`,
  contrairement a `StikkbombPlaybook`, et c'est VOULU.
- ~~**1004 `MortisRound`** reste un residu~~ — **PORTE (#27-r3)**, cf. §TRANCHE 4h.

## TRANCHE 4h (2026-08-01, #27-r3) — `MortisRound` (1004) PORTE : le dernier residu a porteur HERO

### L'inventaire, RE-DERIVE du binaire sur `rnca9r7q6c`

`probe_27_custom_utility_inventory.py --build rnca9r7q6c`, relance le 2026-08-01 :
**388** classes `*Playbook*` vues au runtime, **96** portent le slot — **toutes a `+0x338`** (171
`no-slot`, 121 `vtable-uninit`) ; **29 corps distincts** = **26 nommes** dans `methods.tsv` + **3
corps PARTAGES** non nommes (base `ComparablePlaybook<T>` a 52 users, `ALoki_NormalAttackPlaybook<T>`
a 16, la definition generique `NormalAttackPlaybook`1` a 2) ; **0 corps nomme jamais atteint** par le
balayage. **Le compte « 28 classes / 27 corps » de la fiche de tache etait celui de `gqfc5mff6c` et
est PERIME.**

Etat des **26 corps nommes** apres cette tranche : **21 portes ou couverts**, **1 dead-code**
(`ProperKilly_NormalAttackPlaybook`, aucun porteur), **4 a porteur NPC-seul** (1093, 1215, 1216,
1217) — **relus depuis, et les 4 sont GREFFABLES ; les 4 sont desormais PORTEES et CONFRONTEES**
(1216 #27-r4, 1093 #27-r5, 1215 #27-r6, 1217 #27-r7 — §TRANCHE r4 a r7). **Plus aucun override
a porteur HERO/pool n'est en residu.**

### Ce que le decompile dit — la chaine, lue bout a bout

`IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` :

```
casterTile = UnitPosition$$get_MainTile(casterPosition)
best = Playbook<T>$$GetTargetUtilityDiffOnDisplace(this, caster, casterTile,
                                                  <delegue>, target)
if (best == null) throw;
return Fix64.op_Implicit( Fix64.op_Explicit(best.<+0x18>) )      // Fix64 -> int -> Fix64
```

`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace`
(`this, caster, casterTile, tilesFunc, target`) :

```
best = new <paire>(target, Fix64(0))
if (!UnitExtensions$$IsDisplaceable(target)) return best;          // -> 0
util = <service @this+0x40>.GetUtility(UtilityType.Tile = 7)
t0   = EntityExtensions$$GetMainTile(target, this.<state @+0x20>)
u0   = util.<slot itf 5>( UtilityAttackCase$$Base(target, UnitPosition(t0), t0, aoe) )
foreach (tile in tilesFunc(casterTile, target)) {
    uN   = util.<slot itf 5>( UtilityAttackCase$$Base(target, UnitPosition(tile), tile, aoe) )
    diff = Fix64.op_Subtraction(u0, uN)
    if (diff > Fix64(0) && diff > best.<+0x18>) best = new <paire>(target, diff)
}
return best
```

et `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetPushableTiles` :

```
if (!UnitExtensions$$IsDisplaceable(target)) return new List<ITile>();
tiles = this.<battleQuery @+0x28>.<slot itf 0x4e>(casterTile, target)
return TargetsSelector$$SelectTiles( DSLSelectors$$EmptyOrHasSteppableUnit(
                                       DSLSelectors$$Entities(tiles) ) )
```

**Six points de RE, dont quatre ne se devinent pas :**

1. **L'unite du `UtilityAttackCase` est la CIBLE**, pas le caster.
   `IdunBattle.AI.Utilities.UtilityAttackCase$$Base(caster, casterPosition, target, abilityType)`
   ecrit `+0x10 = caster` — et l'appel passe `target` a cette place. Les feuilles de tuile recopient
   ce champ dans `UtilityMovementCase+0x10` (`IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor
   (attackCase)` : `+0x10 <- +0x10`, `+0x18 <- +0x18`, `+0x28 <- +0xf0.GetValueOrDefault()`,
   `+0x38 <- +0x20`, le reste NUL) puis le passent a `HasTrait(case.unit, …)` /
   `HasFaction(case.unit, …)`. Evaluer `Tile(7)` avec le kit du CASTER serait un fork de port.
   D'ou `engine/playbook/base.py::tile_utility_for_unit` et sa vue `_UnitView`, qui recentre
   `me`/`uid`/`units.ctrl`/`fpos`/`enemies` sur l'unite evaluee.
2. **`EvaluateAttack` sur le composite `Tile(7)` EST `EvaluateMovement`.** Chaque feuille de tuile
   convertit son `UtilityAttackCase` en `UtilityMovementCase` et saute au slot
   `EvaluateMovementInSteps` — corps IDENTIQUES de
   `IdunBattle.AI.Utilities.ElevationUtility$$EvaluateAttackInSteps`,
   `...AUnitEffectsUtility$$EvaluateAttackInSteps`,
   `...CapturePointTileUtility$$EvaluateAttackInSteps`. Sans cette lecture on aurait conclu que la
   voie ATTACK des feuilles Tile est le stub vide de
   `IdunBattle.AI.Utilities.BaseUtility.u003CEvaluateAttackInStepsu003Ed__53$$MoveNext`
   (`yield Fix64(0)`) — et donc, a tort, que le terme est un NO-OP natif comme 1222.
3. **Le facteur multiplicatif du composite vaut 1.**
   `IdunBattle.AI.Utilities.ComposedUtility.u003CEvaluateAttackInStepsu003Ed__6$$MoveNext` fait
   `(Sigma enfants) x CalculateAttackModifier(case)`, produit des `Nullable<Fix64>` non vides des
   enfants. Or les **TROIS SEULES** utilities qui overrident `CalculateAttackModifier`
   (`DislikeBossUtility`, `DislikeEnvironmentUnitsUtility`, `DislikeObjectsUtility`) sont des
   feuilles du composite d'ATTAQUE — **aucune n'appartient a `Tile(7)`**.
4. **La TRONCATURE vers `int`** (`Fix64$$op_Explicit` puis `op_Implicit`) est ce qui explique le
   « terme mesure NUL (< 0.012) » des tranches 1-3 : elle ecrase a 0 tout gain de module `< 1`, et
   sur un plateau PLAT le composite `Tile(7)` est constant, donc `diff == 0` PARTOUT. Le terme n'a
   d'existence que sur un board a feuille de tuile discriminante — l'elevation en tete.
5. **La liste de tuiles est l'arc ARRIERE, pas la destination reelle du push.** Le slot d'interface
   `0x4e` est `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile` — RE-DERIVE
   au runtime (index de vtable **0x52**, `interfaceOffset` = 4, ancres `IsMeleeAttack`/
   `GetAdjacentTiles` de `probe_27_4g_battlequery_slots.py`), **jamais recopie d'une fiche**. La
   DECISION ne rejoue donc pas `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` : elle
   score l'arc ENTIER et en prend le MAX. Sur un push melee axis-aligne l'arc est degenere en UNE
   tuile et les deux coincident ; hors alignement il peut en porter DEUX.
6. **C'est un MAX gate a `> 0`** : une tuile de push qui AMELIORERAIT la position de la cible
   n'apporte aucun malus, et deux tuiles ne s'additionnent pas.

**Contre-epreuve de l'orientation des vecteurs, sans live** : `battle_query.
get_minimum_tiles_180_behind_from_tile` (nouvelle, face DECISION) et le couple `_dir_index`/`_step`
de `runner/operations/displace.py` (face COMBAT, porte et valide live par #68) sont deux ports
ECRITS SEPAREMENT depuis deux artefacts natifs DISTINCTS. Ils rendent la MEME tuile sur les 6
geometries adjacentes testees (deux parites de colonne, plusieurs directions).

**Classification DSL/imperatif** (tranchee AVANT de coder) : `CalculateCustomUtility`,
`GetTargetUtilityDiffOnDisplace` et `GetPushableTiles` sont des METHODES (boucles, appels de
service, slot de `BattleQuery`), pas des arbres `DSLFactory` -> **imperatif, mirror 1:1**. Les deux
seuls noeuds declaratifs du chemin sont `DSLSelectors$$Entities` et
`DSLSelectors$$EmptyOrHasSteppableUnit`, et ils ne sont pas recables : le port applique le predicat
d'occupation (`tuile vide OU occupant a trait Steppable`) la ou le natif l'applique.

### L'override porte

| Ability (id) | Symbole | Formule mirroir | Poids | Porteur | Validation |
|---|---|---|---|---|---|
| **MortisRound** (1004) | `IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` (slot **+0x338**) | `trunc( max(0, max_{t in arc} [ Tile7(cible@sa tuile) - Tile7(cible@t) ]) )` ; `arc` = `EmptyOrHasSteppableUnit(GetMinimumTiles180BehindFromTile(casterTile, cible))` ; gate `IsDisplaceable(cible)`. Terme POSITION- **et** CIBLE-dependant. | **aucun poids BC** — la magnitude sort entierement du composite `Tile(7)` (sur MC1_67 : `Elevation.Multiplier` = 10/niveau, `HighestElevation` = +10, `LowestElevation` = -5) | `ultraEliminatorSgt` `Certus` [**HERO du pool**, ni `catalog_inject` ni greffe] | **A/B causal live** (`probe_27_r3_mortis_round_ab.py`, board MC1_67, seed 909, `--hp-target 1800`), **5 bras a 2 issues**, moteur = natif dans les 5 ; **3 mutations adversariales**. Detail ci-dessous. |

### Validation — A/B causal live, 7 bras, magnitude ENCADREE

Le terme n'apparait pas dans `pairUtility` : on l'exerce par le CHOIX natif (`aiDryRunAllUnits`,
read-only). `u(1004) = pair1004 + custom` contre `u(69) = pair69 + 1` (le custom de l'attaque
normale vaut `Fix64(1)`), le terme `Tile(7)` de la tuile de tir etant commun aux deux.

DEUX geometries dont seule l'ELEVATION de la tuile d'arrivee change — memes distances (2), memes
elevations de tuile de tir (3), donc **memes predictions et meme terme de tuile** :

| geom | caster | cible | arc | `u0 - uN` | custom |
|---|---|---|---|---|---|
| **A** | (0,1) elev 3 | (0,3) elev **4** (= max board) | [(0,4)] elev 3 | `(40+10) - 30` | **20** |
| **B** | (0,2) elev 3 | (0,4) elev 3 | [(0,5)] elev 2 | `30 - 20` | **10** |
| **C** | (3,3) elev 3 | (4,4) elev 2 | [(5,5) elev 2, (4,5) elev **1** (= min board)] | `max(20 - 20, 20 - (10-5))` | **15** |

La geom **C** est la seule dont l'arc n'est pas degenere (caster non aligne en cube avec la cible) :
sa PREMIERE tuile donne un diff NUL et la seconde 15. Elle teste donc le `max` — et bloquer la
SEULE seconde tuile suffit a annuler le terme, l'arc restant non vide.

> ⚠ **Le terrain DOMINE l'elevation, et la premiere version de ce bras s'y est fait prendre.** Posee
> sur (1,3), une tuile `Swamp`, la geom C rendait `u0 = 25` au lieu de 50 (`TileEffectsUtility` =
> **-25**) et les DEUX diffs etaient negatifs -> custom 0, natif ET moteur d'accord sur `69`, bras
> muet. Toute geometrie de ce probe se re-derive avec le **TileId**, jamais avec la seule elevation.

`--hp-target 1800` place `ecart = pair69 + 1 - pair1004` a **11.932297**, DANS `(10, 20)` — la seule
fenetre ou 20 bascule le natif et 10 ne le bascule pas. (Calibrage mesure : PV naturels 11046 ->
2.774 ; 2200 -> 9.946 ; **1800 -> 11.932** ; 1500 -> 58.856, la normale TUE et le bonus Kill fait
exploser l'ecart.)

| bras | levier | custom porte | natif | moteur |
|---|---|---|---|---|
| **A libre** | — | **20** | **1004** | **1004** [MATCH] |
| **A bloque** | appat ALLIE sur (0,4) | 0 | 69 | 69 [MATCH] |
| **B libre** | — | **10** | **69** | 69 [MATCH] |
| **B bloque** | appat ALLIE sur (0,5) | 0 | 69 | 69 [MATCH] |
| **C libre** | — (arc DOUBLE, max sur la 2e tuile) | **15** | **1004** | **1004** [MATCH] |
| **C bloque** | appat ALLIE sur (4,5), l'arc reste NON VIDE | 0 | 69 | 69 [MATCH] |
| **BigTarget** | `tauCrisis` prend (0,3), arc LIBRE | 0 | 69 | 69 [MATCH] |

- **Confond de prediction MESURE ET NUL** : `pair69` = 76.6370699275285 et `pair1004` =
  65.70477248169482 sont **bit-identiques sur les quatre bras A/B**. La geom C, dont l'elevation de
  cible differe, a ses paires propres (145.89345171116292 / 139.345172024332, `gap` = 7.548280) —
  c'est SON gap qui borne SA bascule.
- **Encadrement 100 % natif, sans fitting** : `custom(geom A) > 11.9323` **et**
  `custom(geom B) < 11.9323`. Un terme CONSTANT — quelle que soit sa valeur — ne peut pas produire
  ces deux resultats opposes a paires identiques : la MAGNITUDE est discriminee, pas seulement le
  signe.
- **Le bras BigTarget est un encadrement bien plus serre** : `tauCrisis` a 1800 PV est tuee par les
  deux abilities, donc `pair69 == pair1004 == 239.88901221659034` et il suffirait de `custom > 1`
  pour basculer. Le natif ne bascule pas => `custom < 1`, donc 0. Le gate `IsDisplaceable` est
  mesure, pas suppose.
- **Necessite** : moteur avec le custom force a 0 -> `69` dans le bras A libre, la ou le natif dit
  `1004`. Le terme est NECESSAIRE a l'accord.
- **QUATRE mutations adversariales** (`probe.MUTANTS`, rejouees sur la MEME decision), et chacune
  diverge sur un bras DIFFERENT — aucune n'est couverte par les autres :

  | mutation | piece du port retiree | diverge sur |
  |---|---|---|
  | `zero` | le terme entier | `a-libre`, `c-libre` |
  | `no_occupancy` | `DSLSelectors$$EmptyOrHasSteppableUnit` | `a-bloque`, `b-bloque`, `c-bloque` |
  | `no_displaceable` | `UnitExtensions$$IsDisplaceable` | `bigtarget` |
  | `first_not_max` | le `max` (prend la 1re tuile de l'arc) | `c-libre` |

  C'est ce que garde `tests/engine/test_mortis_round_decision_live.py::test_each_mutation_is_visible`
  (9 tests au total).

### Non couvert (explicite)

- **`IsDisplaceable` teste aussi `HasFlag(unit, 0x19)`**, un `UnitFlag` que le substrat de DECISION
  (`decisionView`) n'expose pas. Gate INERTE cote port -> borne SUPERIEURE (jamais une tuile retiree
  a tort). Les quatre autres refus sont portes : mort, `Hulking` (3), `Immovable` (17),
  `BigTarget` (1017).
- **`MortisRoundPlaybook$$MakeDamagePredictions` n'est pas re-porte.** Il appelle
  `GenerateAttackPredictions(…, StranglethornCannonAbility$$GetDamageAmountMain(ability), …)` sur le
  selecteur `Entity(target)`. Le chemin generique du port lit le `damageProfile` de la config ; les
  `pairUtility` natives et le port n'ont pas ete decomposees etage par etage sur ce point. **Hors
  perimetre #27** (qui ne porte que le terme custom), mais a verifier avant de conclure quoi que ce
  soit sur la MAGNITUDE de 1004.
- **`GetDisplaceUtility`** (meme corps que le custom, SANS la troncature — il rend l'`int` brut) n'a
  aucun call-site dans le binaire : ses 2 xrefs sont des DATA (table de methodes). Non porte.
- **Le composite `Tile(7)` evalue pour la CIBLE** herite des limites connues de `tile_utility` : les
  feuilles non portees ou dormantes le restent. La contre-mesure est que le montage LIVE mesure le
  resultat NET, pas feuille par feuille.
- **La TRONCATURE vers `int` n'est PAS discriminee par ce montage.** Les trois geometries donnent
  des diffs ENTIERS (20, 10, 15) : un port sans `int()` rendrait exactement les memes valeurs et
  aucun bras ne bougerait. C'est pourquoi elle n'a pas de mutant. Elle est LUE au decompile
  (`Fix64$$op_Explicit` -> `op_Implicit`), pas mesuree. La discriminer demanderait une feuille de
  `Tile(7)` a valeur FRACTIONNAIRE sur la tuile de la cible ou de son arc — aucune des feuilles
  actives sur MC1_67 n'en produit.
- **Le reclassement ami/ennemi de `_UnitView` n'est pas exerce.** Les feuilles de `Tile(7)` qui
  distinguent amis et ennemis (famille `AUnitEffectsUtility`, `SaviorProtocols`,
  `DefenderOfTheGreaterGood`) sont inertes dans ce montage : aucun voisin porteur. Le recentrage est
  donc porte par LECTURE du natif (`UtilityAttackCase+0x10` = la cible), pas confirme par la mesure.
- **Le delegue passe a `GetTargetUtilityDiffOnDisplace` n'est pas lu directement** : `DAT_183334188`
  est un `MethodInfo*` rempli a l'init IL2CPP, donc illisible statiquement. `GetPushableTiles` est
  la SEULE methode de `Playbook<T>` dont la signature `(ITile, TUnit) -> IEnumerable<ITile>`
  corresponde a l'invocation, et le comportement mesure live (arc arriere + filtre d'occupation) le
  confirme des deux cotes. Attribution par ANCRAGE, pas par lecture directe.

## TRANCHE r4 (2026-08-01) — les 4 overrides « npc-only » : l'INVENTAIRE tranche, et il tranche a 4/4

Les tranches precedentes rangeaient 1093 / 1215 / 1216 / 1217 en « non pertinent — porteur npc ».
**Ce n'est pas un verdict, c'est une question non posee.** Le critere de la gate de confrontabilite
est : *l'utilite lit-elle une stat ou un trait du CASTER ?* Si non, l'ability se GREFFE sur une unite
du pool (`case-92` §5bis), parce que le natif charge le playbook **par ABILITY**
(`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite.

Les quatre `.ctor` le confirment — ce sont bien quatre `ComparablePlaybook<T>` distincts :
`...MortarionsPlagueWindPlaybook$$.ctor` -> `0x445` (1093),
`...InstrumentsOfVengeancePlaybook$$.ctor` -> `0x4bf` (1215),
`...MartialExemplarPlaybook$$.ctor` -> `0x4c0` (1216),
`...TheLionsWrathPlaybook$$.ctor` -> `0x4c1` (1217). Les quatre ont un `constants.damageProfile`
(Psychic / HeavyRound / Power / Power) : elles passent donc par la route d'ATTAQUE (`_best_attack`),
pas par la route non-attaque de la tranche 4b.

### Le PIVOT de l'inventaire : le slot d'interface 0x80 du `battleQuery`

Trois des quatre customs (1215, 1216, 1217) reposent sur le meme appel
`this.<battleQuery @+0x28>.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false)`.

**Ancrage du slot, par le decorateur enregistreur** (jamais par recopie de fiche) — les
`RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClassNNN_0$$u003C<Nom>u003Eb__0`
emettent chacun leur slot :

| slot | methode |
|---|---|
| 0x77 | `GetSurroundingUnits` (DisplayClass146) |
| **0x78** | **`GetSurroundingEnemies`** (DisplayClass147) |
| 0x79 | `GetSurroundingFriends` (DisplayClass148) |
| 0x7a / 0x7b / 0x7c | `GetAdjacentUnits` (DisplayClass149/150/151) |
| 0x7d / 0x7e / 0x7f / **0x80** | **`GetAdjacentEnemies`** (DisplayClass152/153/154/155) |
| 0x1b | `HasMinimumRemainingTurns` (DisplayClass68) |
| 0xb2 | `FindMeleeWeapon` (DisplayClass212) |

⚠ **Le numero de DisplayClass n'est PAS un index de slot** : localement (144..155) la suite est
monotone, mais `DisplayClass38` -> slot 6 et `DisplayClass41/42/43` -> slots 1/2/3. Chaque slot cite
ici a ete lu dans le corps de SON display class, pas extrapole.

**Et c'est ce corps-la qui rend le verdict** :
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit, ignoreSteppables)` ne lit du
`unit` que son `OwnerComponent.CurrentPlayerEntityId` — **le CAMP**, rien d'autre — avant
`IterateAdjacentTiles(from)` / `GetUnitsOnTiles(...)`. Idem pour
`...$$GetSurroundingEnemies(actor, from, range, includeCenter)` = `GetSurroundingUnits(from, range,
includeCenter)` filtre par un predicat d'inimitie capturant `actor`. **Ni stat, ni trait, ni arme,
ni portee du caster.** Une greffe ne les deforme donc pas.

Meme conclusion pour les GATES, qu'il fallait lire avant de conclure a l'atteignabilite :

- `...MartialExemplarPlaybook$$ShouldEvaluate` = `GetAdjacentEnemies(position, unit, false).Count > 0`.
- `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate` = `BasePlaybook$$ShouldEvaluate &&
  HasMinimumRemainingTurns(unit, 2)`. Le corps de
  `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` **n'utilise PAS son parametre
  `unit`** : il lit la limite de tours du match (dict de config, cle 1) moins
  `TurnComponent$$GetAmountOfTurnsEndedByPlayer`, et **rend `true` quand la limite est absente**.
  C'est un gate GLOBAL, neutre au porteur — et en arene il passe.
- `...TheLionsWrathPlaybook$$ShouldEvaluate` combine les deux (`HasMinimumRemainingTurns(unit, 2)` et
  le compte d'adjacents).

### Les 4 verdicts

| id | symbole | formule lue | lit une stat/trait du CASTER ? | verdict |
|---|---|---|---|---|
| **1093** | `IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$CalculateCustomUtility` | `Fix64( Count( DSLSelectors.UnitsWithTrait(t1+t2+t3, Psyker(0x3ea), sel 3), AbilityEntities(owner: caster, caster: caster, target: target) ) )` — les trois vagues sont `t1 = <cfg dsl>+0x60` (selecteur de cible principale), `t2 = Enemies(of, AdjacentUnits(t1, includeCenter:1, sel:3), sel:3)`, `t3 = Unique(Enemies(of, AdjacentUnits(t2, includeCenter:1, sel:3), sel:3)) - t1 - t2`. **Aucun `GetUtilityValue`** : le compte EST l'utilite | **NON** — le seul trait lu (`Psyker`) est celui des unites SELECTIONNEES ; le caster n'entre que comme `owner`/`caster` de l'`AbilityEntities` (inimitie = camp) | **PORTE + CONFRONTE** (#27-r5) |
| **1215** | `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$CalculateCustomUtility` | `adj = GetAdjacentEnemies(casterPosition, caster, false)` ; `u = 20000 + (adj.Any() ? 0 : 100) + 20 x \|{ e in GetSurroundingEnemies(caster, casterPosition, 2, false) : !adj.Contains(e) }\|`. **Aucun `GetUtilityValue`** : les trois constantes sont EN DUR | **NON** — camp seulement | **PORTE + CONFRONTE** (§TRANCHE r6). ⚠ Reserve de MESURE : `...InstrumentsOfVengeancePlaybook$$GetUseProbability` = `Fix64.Zero` si `GetTurnsFinished(unit) == 0`, `Fix64.Half` si `== 1`, `Fix64.One` sinon (`Fix64.<statics>` : +0x20 One, +0x28 Zero, +0x30 Half) -> l'ability est INDISPONIBLE au tour du build et TIREE a 1/2 au suivant ; seule la fenetre `GetTurnsFinished >= 2` est deterministe. ⚠⚠ Et la formule ci-contre se lit `surrounding \ adj`, PAS « ennemis a d=2 » : les deux ensembles n'ont pas la meme geometrie (§TRANCHE r6) |
| **1216** | `IdunBattle.AI.Playbook.Loki.MartialExemplarPlaybook$$CalculateCustomUtility` | `1000 x \|{ e in GetAdjacentEnemies(casterPosition, caster, false) : UnitExtensions$$IsNormalUnit(e) }\|` ; `IsNormalUnit(e)` = `!HasTrait(e, Object(0xd)) && !HasTrait(e, Steppable(0x1b))`. **Aucun `GetUtilityValue`** : `1000` est EN DUR | **NON** — camp seulement ; le filtre porte sur les ENNEMIS | **PORTE + CONFRONTE** (ci-dessous) |
| **1217** | `IdunBattle.AI.Playbook.Loki.TheLionsWrathPlaybook$$CalculateCustomUtility` | `30 x FindMeleeWeapon(TARGET).<+0x20 = Hits> + 2000 x \|{ e in GetAdjacentEnemies(casterPosition, caster, false) : IsNormalUnit(e) && HasTrait(e, Chaos(0x7ea)) && HasTrait(e, Hero(0x10)) }\| + 150 x [HasTrait(TARGET, Hero)]`. **Aucun `GetUtilityValue`** | **NON** — l'arme et le trait `Hero` lus sont ceux de la **CIBLE** ; les traits `Chaos`/`Hero` filtres sont ceux des ADJACENTS | **PORTE + CONFRONTE** (#27-r7) |

Traits qualifies contre `data/symbols/rnca9r7q6c/frida/enums.tsv`, enum `IdunBattle.Entities.Enum.UnitTrait` :
`0xd = 13 = Object`, `0x10 = 16 = Hero`, `0x1b = 27 = Steppable`, `0x3ea = 1002 = Psyker`,
`0x7ea = 2026 = Chaos`.

`WeaponProfile+0x20 = Hits` etabli par DEUX lectures concordantes :
`IdunBattle.Core.Services.BattleQuery$$u003CGetBestWeaponu003Eb__316_0` calcule
`GetDamageProfile(w.<+0x10>).<+0x14> x w.<+0x20>` (degat par coup x nombre de coups), et
`...$$SelectMaxRangeWeapon` / `IdunShared.Battle.WeaponProfile$$get_IsMelee` lisent tous deux
`+0x24` comme le `Nullable<int> Range` (`IsMelee` = `range < 2`) — donc `+0x20` n'est pas la portee.

### L'override PORTE : 1216 `MartialExemplar`

#### Le masque EFFECTIF, et ce qu'il retourne du dossier

`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$.ctor` n'appelle PAS la
surcharge explicite : il recopie le preset `<TargetingOptions statics>+0x280` et passe
`additionalRules = 0x10` a `IdunBattle.Core.Services.TargetingOptions$$.ctor(this, template,
additionalRules)`, dont le corps fait `this.rules(+0x28) = additionalRules | template.rules(+0x28)`.
Le preset porte `rules = 0x8004` (ecrit par `...TargetingOptions$$.cctor`), donc :

    0x8004 | 0x10 = 0x8014
      = CasterIsPossibleTarget(0x8000) | CasterHasNotMoved(0x10) | CasterMatchesDynamicRule(0x4)

**Recopier `0x10` seul aurait donne un masque FAUX** — c'est exactement le piege « PRESET + flags ».
Les deux bits portants sont MESURES, pas deduits (`probe_27_r4_martial_exemplar.py`) :

| bit | consequence | mesure live |
|---|---|---|
| `CasterIsPossibleTarget` | 1216 est **SELF-CAST** | `abilityTargets(1216)` rend UNE cible : le caster. Les `attackPlans.evals` de 1216 sur les ENNEMIS rendent tous `rankCount = 0` |
| `CasterHasNotMoved` | cast interdit apres deplacement | un `act move` du caster fait tomber `abilityTargets(1216)` de 1 cible a **0** |

C'est le premier bit qui dicte la ROUTE : `_best_attack` consomme des evals a `rankCount > 0` sur des
ennemis, elle ne peut donc RIEN produire pour 1216. Le port passe par la **route non-attaque**
(`playbook/nonattack.py`), 3e motif d'entree apres « pas de `damageProfile` » (1226, 1185) et « masque
refusant toute cible ennemie » (1100) — et ce alors meme que 1216 A un `damageProfile` (`Power`).
`make_damage_predictions` rend `[]` : la cible etant le caster, le natif ne predit aucun degat sur
elle (**mesure** : `pairUtility(1216, SELF) = 0` sur les trois tuiles testees).

#### Ce qui est porte

- `engine/playbook/loki_custom.py::MartialExemplarPlaybook` (`NonAttackComparablePlaybook`, registre
  `NONATTACK_PLAYBOOKS` par `register_nonattack`) :
  `calculate_custom_utility` = `1000 x |adjacents IsNormalUnit|`, `should_evaluate` = le gate,
  `is_caster_added` = mirror de `CasterHasNotMoved` (seule l'origine passe).
- `engine/playbook/nonattack.py` : hook **`should_evaluate(ctx, tile, ability_id)`** dans
  `nonattack_candidates`, defaut `True`. C'est le slot de vtable **6**, et il est appele **PAR TUILE
  CANDIDATE** — etabli sur la machine a etats de
  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`,
  qui appelle `playbook.<slot 6>(unit, position, positions)` a chaque `MoveNext` de l'enumerateur de
  positions. ⚠ **Trois surcharges distinctes coexistent** — slot 4 `(unit)`, slot 5
  `(unit, possiblePositions)`, slot 6 `(unit, position, possiblePositions)` — et les deux premieres
  sont appelees UNE fois, AVANT la boucle. `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate`
  override la 2-args, 1216 et 1217 la 4-args : les confondre inverse la semantique du gate.
- `engine/battle_query.py::count_adjacent_matching` — meme `is_adjacent` que `count_adjacent` (donc
  la meme porte d'elevation `|delta| < 2` d'`IterateAdjacentTiles`), avec un predicat par unite.
  Aucun fork d'adjacence.
- `engine/entities/traits/unit_trait.py::is_normal_unit` — ecrit la ou vit son homonyme natif.
- `engine/runner/abilities/targeting.py::TARGETING_OPTIONS_UNPORTED[1216] = 0x8014`. C'est la table
  « masque lu, behaviour NON portee » : la face COMBAT de 1216 n'est pas portee, elle n'entre donc
  pas dans `ABILITY_CLASSES` (et `probe_181` reste a 102/102, `probe_120` etape 0 a « aucun »).

⚠ **Le gate et l'utilite ne comptent PAS le meme ensemble.** `ShouldEvaluate` compte TOUS les ennemis
adjacents ; `CalculateCustomUtility` seulement les `IsNormalUnit`. Les deux divergent des qu'un ennemi
`Object`/`Steppable` est adjacent — l'action est alors generee avec `custom = 0`. Les confondre serait
un port faux dans exactement ce regime.

#### Validation live (4 bras, `probe_27_r4_martial_exemplar.py`, board MC1_67, seed 909)

Porteur GREFFE sur **`darkaAsmodai`** (Dark Angels comme `darkaBossLion`, arme de melee, present dans
`rl_duel build --list-pool`). **Le caster n'est JAMAIS deplace** — c'est une assertion du probe, pas
une precaution : un `act move` du caster arme `CasterHasNotMoved` et desarme l'ability, et les bras
degenereraient en « le natif ne propose jamais 1216 », un faux negatif parfaitement coherent. Ce sont
les ENNEMIS qu'on deplace.

| bras | n | natif | moteur | custom | contre-epreuve `custom = 0` |
|---|---|---|---|---|---|
| A | 0 | `MoveUnitMessage` + `ActiveAbilityMessage(69)` | `(69, 77)` | 0.0 | `(69, 77)` |
| B | 1 | **`ActiveAbilityMessage(1216, self)`**, sans deplacement | `(1216, 83)`, `to=None` | 1000.0 | **`(69, 77)`** |
| C | 2 | `ActiveAbilityMessage(1216, self)` | `(1216, 83)`, `to=None` | 2000.0 | **`(69, 79)`** |
| D | — | `abilityTargets(1216)` : 1 cible avant le move du caster, **0 apres** | 12 tuiles hors origine, **0** acceptees par `is_caster_added` | — | — |

Le natif emet `ActiveAbilityMessage(1216)` : **c'est la preuve directe que « npc-only » n'etait pas
« non confrontable »**. Les deux contre-epreuves (custom force a 0, registre `NONATTACK_PLAYBOOKS`
vide) font DIVERGER le moteur du natif sur B et C — le terme et la route sont donc necessaires, pas
decoratifs. Garde : `tests/engine/test_martial_exemplar_decision_live.py` (9 tests).

#### Ce qui n'est PAS couvert, et pourquoi

- **La MAGNITUDE `1000` n'est pas discriminable par le choix natif.** `CasterHasNotMoved` fige la
  tuile et `CasterIsPossibleTarget` fige la cible : il n'existe qu'**UNE** action 1216 par tour, donc
  le terme ne departage jamais deux actions de 1216 entre elles ; face aux autres abilities il gagne
  des `n >= 1`. Toute constante `>= ~10` produirait les memes decisions dans tous les regimes
  atteignables. Le `1000` est LU (constante en dur, aucun `GetUtilityValue`), il n'est pas mesure —
  et les assertions du test gardent le PORT contre une derive de code, pas contre le natif.
- **Le filtre `IsNormalUnit` n'est pas exerce en LIVE** : il faudrait un ennemi `Object` ou
  `Steppable` adjacent au caster **au spawn** (le caster ne peut pas aller le chercher). Garde
  OFFLINE uniquement (`test_is_normal_unit_mirrors_the_native_predicate`).
- **La face COMBAT de 1216 n'est pas portee.**
  `...MartialExemplarAbility$$ExecuteBehaviour` est un arbre DSL substantiel (`AddEffect(0x5f0)`,
  `AttackWithAttackDamage(AdjacentEnemies)`, puis `MoveUnit(ClosestPositionToTarget(Nearest(...)))`,
  `UseNormalAttackIfAble`, `SortUnitsByDamageUtility`, `KillDeadUnits`) — une charge suivie d'une
  attaque. Hors perimetre de cette tranche, qui ne couvre que la DECISION.
- La greffe ne couvre pas les stats, traits et armes de `darkaBossLion` — legitime ICI puisque la
  formule n'en lit aucun, et ce serait illegitime pour une prediction de degat.

- **1004 `MortisRound`** reste un residu d'une nature encore differente :
  `IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` =
  `(Fix64)(int)(Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace(caster, casterPosition.MainTile, <liste>, target).<+0x18>)`
  — une TRONCATURE vers `int` d'un differentiel d'utilite de DEPLACEMENT. La troncature explique le
  « terme mesure NUL (< 0.012) » des tranches precedentes : tout differentiel de module < 1 rend 0.
  Debloqueur : porter `GetTargetUtilityDiffOnDisplace` (evaluateur `UtilityMovementCase`), pas un
  scalaire.

## TRANCHE r5 (2026-08-03, #27-r5) — `MortarionsPlagueWind` (1093) PORTE : le verrou annonce etait PERIME

La fiche #27-r5 annoncait un verrou « REEL » : « l'evaluateur DSL `UnitsWithTrait` + la chaine
`AdjacentUnits` a 3 vagues n'est pas portee cote decision ». **Re-derive du code du commit courant,
il n'existait plus** — et le critere de decision se tranche avant toute edition, en trois greps :

| primitive du decompile | port | ou |
|---|---|---|
| `DSLSelectors$$AdjacentUnits` (source = ENSEMBLE) | `adjacent_units` | `entities/selectors/composites.py` |
| `DSLSelectors$$Enemies` | `Enemies` | `entities/selectors/units.py` |
| `DSLSelectors$$Unique` | `Unique` | idem |
| `DSLSelectors$$UnitsWithTrait` | `UnitsWithTrait` | idem |
| `TargetsSelector$$op_Addition` / `$$op_Subtraction` | `Union` / `Sub` | idem |

Et la VOIE « playbook -> `DslContext` -> arbre de l'ability » avait deja **deux** precedents
(`playbook/resurrection_orb.py`, `playbook/tile_targets.py`). Il n'y avait donc **aucune primitive
DSL a porter** : seulement un contexte a monter. Le port tient en une classe + deux fonctions.

**Ce que la fiche ne disait pas, et qui est le vrai fait du dossier** : la chaine des trois vagues
de 1093 est **le meme artefact natif** que la face COMBAT de son jumeau `PlagueWind` (1035,
`deathTyphus`), **portee et validee depuis #220** (`runner/abilities/deathguard.py::
plague_wind_target_selectors`). Les trois corps sont DEDUPLIQUES par IL2CPP — ghidra les nomme
d'apres un proprietaire arbitraire (`StrikeFromTheShadowsAbility$$GetTarget`,
`StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0`, `PlagueWindAbility$$GetTargets3`), ce qui
masque completement la parente si on lit les NOMS.

### La formule, relue VERBATIM

    t1  = <ability>.GetTarget()          = <DSLSelectors+0x60> = Target
    t2  = <ability>.b__1_0(t1)           = Enemies(<+0x48> = Caster, AdjacentUnits(t1, 1, 3), 3)
    t3  = <ability>.GetTargets3(t1, t2)  = Unique(Enemies(Caster, AdjacentUnits(t2, 1, 3), 3)) - t1 - t2
    sel = DSLSelectors$$UnitsWithTrait(t1 + t2 + t3, 0x3ea = Psyker, 3)
    return Fix64.op_Implicit( sel.<vslot 0x18 = Count>(AbilityEntities(caster, caster, target)) )

**Aucun `GetUtilityValue`, aucune constante multiplicative : le COMPTE DE PSYKERS *EST* l'utilite.**
Slots partages etablis par plusieurs lectures independantes du depot (`case-411-r3`, `case-418-r1`,
`case-459`) : `<DSLSelectors+0x30>` = Owner, `<+0x48>` = Caster, `<+0x60>` = Target.
`0x3ea = 1002 = Psyker` (enum `IdunBattle.Entities.Enum.UnitTrait`).

**Trois points de RE qui ne se devinent pas :**

1. **Le 3e argument d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(this, origin, unique,
   selectionType)` est `unique`, PAS `includeCenter`** — piege #419, deja paye sur #420-r1. Son
   corps est `op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)` : le
   centre est TOUJOURS retire, et le `1` du call-site ne le reintroduit pas. La fiche heritee
   l'ecrivait « `includeCenter:1` » — lecture FAUSSE, sans consequence ici seulement parce que le
   port passe par `adjacent_units`, qui mirroir la COMPOSITION native et non l'argument.
2. **`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(this, caster, actor, target, owner,
   casterTile, ...)` n'est appele qu'avec `(caster, caster, target, 0, 0, ...)`**, apres un memset a
   ZERO de ses 0x128 octets : `owner` ET `casterTile` sont NULS. **Le terme est donc INDEPENDANT de
   la tuile d'attaque** — il departage les CIBLES, jamais deux tuiles pour une meme cible. C'est ce
   qui interdit de recopier le `_dsl_context` de 1009 (qui, lui, DEPLACE le caster sur la tuile
   candidate parce que ses arbres lisent `CasterTile`).
3. **`Count` est le slot VIRTUEL 0x18**, pas la methode non-virtuelle `TargetsSelector$$Count` — mais
   celle-ci en est l'implementation de base et vaut `Enumerable.Count(this.<vslot 0x17 = Select>(
   entities))`. Aucun `Unique` par-dessus l'union : les trois vagues sont deja disjointes par
   construction (`t3` retranche `t1` et `t2` ; `t2` exclut `t1` via le `- origin` d'`AdjacentUnits`).

### Ce qui est porte

- `engine/runner/abilities/deathguard.py` : `plague_wind_wave_selectors()` (RENOMMEE par
  `#27-r5-r1` : les memes trois corps natifs sont appeles par le `MakeDamagePredictions` de 1035
  AUTANT que par celui de 1093 — le nom d'une des deux abilities mentait) (les trois
  vagues) et `mortarions_plague_wind_psyker_selector()` (l'union + le filtre `Psyker`). Ecrites **a
  cote** de `plague_wind_target_selectors` et non fusionnees avec elle : l'artefact DIFFERE d'un
  `DSLSelectors$$Cache` par vague, que les deux `ExecuteBehaviour` posent et que le playbook n'a pas
  (memoisation qui fige un ensemble entre deux bandes de degat — sans objet quand rien ne mute).
- `engine/playbook/loki_custom.py` : `MortarionsPlagueWindPlaybook` (`_CustomOnlyPlaybook`, registre
  `REGISTRY`) + `_mortarions_plague_wind_dsl_context` (mirror de l'`AbilityEntities` a trois champs).
- `engine/runner/abilities/targeting.py` : `TARGETING_OPTIONS_UNPORTED[1093] = 0x4002`
  (`TargetIsEnemy | TargetMatchesDynamicRule`, `range = RANGE_FROM_CONFIG`, `force_melee_target =
  RANGED_BOOL_FALSE`). LU, pas deduit : `...MortarionsPlagueWindAbility$$.ctor` n'appelle aucun
  `TargetingOptions$$.ctor`, il recopie les 0x40 octets de `<TargetingOptions statics>+0x180` — **le
  MEME preset que `PlagueWindAbility$$.ctor`** — et le masque effectif est la constante que
  `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit en `<preset>+0x28` = `statics+0x1a8`.
  La face COMBAT n'etant pas portee, 1093 n'entre pas dans `ABILITY_CLASSES`.

**ROUTE : `_best_attack`** (route d'ATTAQUE standard, comme 1051/1098) — 1093 a un
`constants.damageProfile` (`Psychic`) et un masque a cibles ENNEMIES. Rien a voir avec la seconde
route Comparable de 1216/1226/1185/1100.

### Validation live — `probe_27_r5_mortarions_plague_wind.py`, board MC1_67, seed 909

Porteur GREFFE sur **`deathBlightlord`** (Death Guard comme `deathBossMortarion`, dans
`rl_duel build --list-pool`). **La greffe demande DEUX ecritures, et l'oubli de la seconde est
SILENCIEUX au build** : `MortarionsPlagueWind` est absente des 131 entrees
`BC.Abilities.ActiveAbilities` du seed, et `refresh_ability_configs` ne RATTRAPE que les configs
deja presentes. Poser `BC.Units[].ActiveAbilities` seul deploie une unite qui porte l'ability... et
`abilityTargets` rend `err = "system error"` (meme verrou que #226). `catalog_inject.
write_grafted_seed_bc(..., kind="active")` fait les deux — c'est la voie.

Montage (les leviers repondent chacun a une mesure, pas a une precaution) :

| levier | pourquoi, et ce qui a ete mesure sans lui |
|---|---|
| `--unit-stat deathBlightlord:Movement=0` | une seule tuile de cast -> `tile_utility` IDENTIQUE pour les deux cibles, l'argmax natif ne compare plus que `u_full + custom`. `abilityTargets(1093).fromHere` vaut 2 : les deux cibles restent castables sans bouger |
| `--unit-stat deathBlightlord:Damage=1` | sans lui le natif prefere l'attaque NORMALE (`aiDryRunAllUnits` rend `ActiveAbilityMessage(69)`) et **aucun bras ne mesure rien**. Le degat de 1093 n'en depend pas (`AttackWithAbilityDamage`, base `minDmg`/`maxDmg` de la config) |
| `--hp-target 40000` + `--unit-stat orksWarboss:Health=...` | a PV nominaux egaux, `orksWarboss` encaisse **1.5x** le Psychic de `necroWarden` (`aiPlaybookPredict` : 2693-4040 vs 1795-2693) -> ecart de `pairUtility` de **6.9**, soit 7x le terme. Les PV de T1 sont le seul levier qui bouge `u_full` **sans toucher ni la geometrie ni les traits** |

Geometrie SYMETRIQUE, lue au `boardGraph` (porte d'elevation comprise) : `T1 = (3,1)` et
`T2 = (0,1)` a distance 2 du caster **toutes les deux** (= sa portee), distance 3 l'une de l'autre,
voisinages DISJOINTS ; `V1 = (3,2)` et `V2 = (0,2)` a distance 3 du caster **tous les deux** (donc
ni l'un ni l'autre n'est ciblable), et a distance >= 2 l'un de l'autre (aucune vague 3 parasite).

| bras | montage | `u_full` natif (T1 / T2) | choix natif | custom PORT |
|---|---|---|---|---|
| **A** | Psyker en `V1` | 13.2764 / 13.7118 (**Δ = −0.4354**) | **`1093` sur T1** | `{T1: 1.0, T2: 0.0}` |
| **B** | Psyker en `V2` (permutation) | 13.2764 / 13.7118 (**Δ = −0.4354**, IDENTIQUE) | **`1093` sur T2** | `{T1: 0.0, T2: 1.0}` |
| **C** | Psyker en `W1 = (3,3)` — voisin de `V1`, **pas** de `T1` | 28.2331 / 5.6097 | `1093` sur T1 | `{T1: 1.0, T2: 0.0}` |

**Le bras A est la mesure** : le natif retient `T1` alors que son PROPRE `u_full` favorise `T2` — il
va CONTRE sa preference de degat, et aucun autre terme ne distingue ces deux actions (meme caster,
meme tuile, meme ability). **Le bras B est la contre-epreuve**, et elle est propre : `u_full` natif
est **strictement identique** dans les deux bras (la permutation ne change rien au degat, les deux
unites echangees ayant les memes PV forces), et pourtant le choix BASCULE. Seul le trait a bouge.
**Le bras C** exerce la VAGUE 3 : le Psyker n'entre dans le compte que par
`t3 = Unique(Enemies(AdjacentUnits(t2))) - t1 - t2` ; un port a deux vagues rendrait 0.

**La MAGNITUDE `1` est MESUREE, pas seulement lue.** On fait varier `u_full(T1)` par les PV de T1 et
on lit ou le natif bascule :

| PV de T1 | Δ `u_full` (T1 − T2) | choix natif |
|---|---|---|
| 512 000 | **−0.9000** | T1 — il tient |
| 736 000 | **−1.1001** | T2 — il lache |

=> le terme natif d'UN Psyker est **encadre dans (0.90, 1.10)**, et le port rend `1.0`. La constante
cesse d'etre une lecture : c'est un encadrement experimental a 10 %.

Gardes : `tests/engine/test_mortarions_plague_wind_decision_live.py` — **15 tests**, 9 offline
(structure des trois vagues, filtre `Enemies`, linearite du compte, disjonction, borne de la chaine)
et 6 live (les trois bras, la bascule, la vague 3, l'encadrement de magnitude).

### Ce qui n'est PAS couvert, et pourquoi

- ~~**L'ACCORD DE DECISION de bout en bout moteur<->natif**~~ — **FERME le 2026-08-03 par
  `#27-r5-r1`** (§TRANCHE r5-r1 ci-dessous). Le residu etait :
  `IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions` fait **TROIS**
  batchs `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` — un par vague (`t1`/`t2`/`t3`
  en `param_5`) avec sa propre formule (`GetDamage1`/`2`/`3`) et le MEME `GetHits()` — puis
  `AddRange` des trois ; le port heritait du chemin generique mono-cible et n'en rendait qu'**UN**.
  MESURE d'alors (bras A) : `u_full` port **1.1220 / 5.6097** contre natif **13.2764 / 13.7118**, et
  le moteur choisissait `T2` dans les trois bras. Depuis le port des trois batchs, `u_full` port et
  natif coincident a **1e-8** et `engine_decide` rend la cible du natif dans les TROIS bras — bras A
  compris, celui ou le natif va CONTRE son propre `u_full`. Les deux gardes correspondantes sont
  entrees dans `test_mortarions_plague_wind_decision_live.py` (point G), qui portait jusque-la la
  clause « l'accord de decision ne peut PAS etre garde ».
- ~~**La branche `Summon x2`**~~ — **PORTEE ET EXERCEE** par la meme tranche (`<DSLFormulas+0x28>` =
  `Direct(2)`, LU au ctor).
- **La face COMBAT de 1093** (`...MortarionsPlagueWindAbility$$ExecuteBehaviour`) n'est pas portee.
  Sa structure est integralement RE ci-dessus : c'est le jumeau exact de `plague_wind_tree` (memes
  trois vagues sous `Cache`, memes trois `AttackWithAbilityDamage`, `AtomicGroup(0x5c)`), a la
  formule `If(Summon)` pres. D'ou `TARGETING_OPTIONS_UNPORTED` plutot qu'`ABILITY_CLASSES`.
- **Le filtre `Enemies` n'est pas exerce en LIVE avec un allie POSITIONNE dans l'anneau** (le caster
  est seul de son camp) : garde OFFLINE
  (`test_the_caster_is_never_in_a_wave_even_when_adjacent`).
- La greffe ne couvre pas les stats, traits et armes de `deathBossMortarion` — legitime ICI puisque
  la formule n'en lit AUCUN (le trait `Psyker` teste est celui des unites SELECTIONNEES, le caster
  n'entrant que comme referent d'inimitie, donc par son CAMP).

## TRANCHE r5-r1 (2026-08-03, #27-r5-r1) — les TROIS batchs de 1035 ET 1093, et le quirk `Summon`

### Ce que le decompile impose, et qui ne se devine pas

`IdunBattle.AI.Playbook.Loki.PlagueWindPlaybook$$MakeDamagePredictions` (1035) et
`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions` (1093) ont le
MEME squelette :

    t1 = StrikeFromTheShadowsAbility$$GetTarget(ability)              # <DSLSelectors+0x60> = Target
    t2 = StormOfWrathAbility$$<ExecuteBehaviour>b__1_0(ability, t1)   # Enemies(Caster, AdjacentUnits(t1,1,3), 3)
    t3 = PlagueWindAbility$$GetTargets3(ability, t1, t2)              # Unique(Enemies(Caster,
                                                                     #   AdjacentUnits(t2,1,3),3)) - t1 - t2
    hits = AActiveAbility$$GetHits = GetNumberConstant(0x2f)          # LITTERAL, la MEME pour les trois
    list = []
    list.AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, target, t_i, d_i, hits, prof, null, 0))  # x3
    return list

**Les trois corps de selecteur sont les MEMES FONCTIONS pour les deux playbooks** — pas des
homonymes, pas des jumeaux : les deux decompiles appellent litteralement les memes adresses. C'est
le point que la deduplication IL2CPP masque, et il est PLUS FORT qu'une ressemblance de structure.
D'ou le RENOMMAGE du port : `mortarions_plague_wind_target_selectors` -> `plague_wind_wave_selectors`
(`runner/abilities/deathguard.py`). Un nom d'ability sur un artefact partage est un nom qui ment.

**Les deux differences, lues :**

| | 1035 | 1093 |
|---|---|---|
| `d1` | `StranglethornCannonAbility$$GetDamageAmountMain` -> `MinMaxDamageAverage` | `MortarionsPlagueWindAbility$$GetDamage1` |
| `d2` | `StranglethornCannonAbility$$GetDamageAmountAdjacent` -> `MinMaxDamage2Average` | `...$$GetDamage2` |
| `d3` | `PlagueWindAbility$$GetDamage3` -> `MinMaxDamage3Average` | `...$$GetDamage3` |
| forme | l'avg NUE | `If( HasTrait(<+0x60> = Target, 2 = Summon), Multiply(<avg>, <DSLFormulas+0x28>), <avg> )` |
| `param_8` | `AbilityConfiguration$$GetDamageProfile` (Nullable BRUT, via `BaseFleshmetalGunsEffect$$GetDamageProfileType`) | `Nullable(AActiveAbility$$GetDamageProfile)` (= `GetValueOrDefault(-1)`) |

`AActiveAbility$$MinMaxDamage{,2,3}Average` = `Half(Sum(Direct(<min>), Direct(<max>)), 0)` avec
`(0xc,0xd)`, `(0x36,0x37)`, `(0x38,0x39)` = `(minDmg,maxDmg)`, `(minDmg_2,maxDmg_2)`,
`(minDmg_3,maxDmg_3)`.

**`<DSLFormulas+0x28>` : LU, pas suppose.** `IdunBattleLogic.Entities.DSLFormulas$$.ctor` alloue
cinq constantes partagees et les ecrit a `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
**`+0x28 = Direct(2)`**, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)` — meme classe allouee et meme
ctor que `IdunBattleLogic.Entities.DSLFormulas$$Direct(amount)`. L'i2 (« Summons take double
damage ») ne PROUVAIT rien ; la brief demandait de ne pas coder `2` sur cette attente, et c'est le
ctor qui tranche. (La meme table est deja citee ailleurs dans le depot : `entities/triggers.
is_mechanical` lit `+0x20 = Direct(1)`.)

**LE QUIRK, et il est structurel.**
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` construit **UN SEUL** `AbilityEntities`
AVANT sa boucle (`target = param_4`), puis (a) evalue la FORMULE `param_6` **une fois, hors
boucle**, (b) evalue le SELECTEUR `param_5` sur le meme objet, (c) boucle en ne changeant QUE la
cible passee au slot `0xb` (`DamagePredictionQuery$$GetAttackPrediction`) et au
`ProbableDamageEvent`. Donc le `Target` du `HasTrait` est **la cible principale**, jamais l'unite
frappee : si la cible est un `Summon`, **les trois vagues entieres** doublent, y compris sur des
unites qui n'en sont pas ; si elle ne l'est pas, aucune ne double, meme sur un summon frappe.

### Ce qui est porte

- `engine/playbook/prediction/plague_wind.py` (NEUF) : `min_max_damage_average`,
  `wave_damage_formula` (l'arbre, avec le `If(Summon)` pour 1093 seul), `dsl_context`,
  `main_batch_inputs` (batch 1) et `wave_events` (batchs 2 et 3).
- `engine/playbook/prediction/abilities.py` : `_MAKE_DMG_INPUT_OVERRIDES[1035] = [1093] =
  _plague_wind_inputs` et `_MAKE_DMG_EXTRA_EVENTS[1035] = [1093] = _plague_wind_wave_events`.
  Decoupage MIRROR : le batch 1 EST le chemin generique (son selecteur est `Target`), il ne lui
  manque que ses ENTREES ; les batchs 2 et 3 ont chacun SON selecteur et SA base, donc ils ne sont
  ni l'AoE de l'ability (une seule base) ni la cible.
- **`hits` LITTERAL** pour le batch principal : le chemin generique passe par
  `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits[, ExtraHitsMelee])`, qui AJOUTE
  la stat `ExtraHits` du caster — que ce playbook n'ajoute pas. Meme ecart, meme correctif que
  `_stikkbomb_inputs` / `_mass_driver_accelerator_inputs` / `_ramming_speed_inputs`.
- **Aucun `profile_override`** : les deux chemins natifs rendent la `damageProfile` de la config
  (`Psychic` pour les deux abilities). La distinction `Nullable` brut vs `GetValueOrDefault(-1)` est
  structurellement INOBSERVABLE ici — elle ne le deviendrait que sur une config SANS
  `damageProfile`, regime qu'aucune des deux n'a.

### Confrontation live — `probe_27_r5_r1_plague_wind_prediction.py`, board MC1_67, seed 909

UN build par bras, **DEUX abilities mesurees dessus** : `deathTyphus` porte 1035 NATIVEMENT (pool),
`deathBlightlord` porte 1093 par GREFFE (`write_grafted_seed_bc(kind="active")` — 1093 est absente
des `BC.Abilities.ActiveAbilities` du seed, cf. TRANCHE r5). Mesurer les deux sur le MEME etat fait
de 1035 le **temoin** de 1093 : si le port appliquait le facteur aux deux, 1035 rougirait.

Grappe a TROIS anneaux, lue au `boardGraph` : `T = (3,1)` (cible), `V = (3,2)` (voisin de T),
`W = (3,3)` (voisin de V, PAS de T), `F = (0,1)` (temoin, hors de toute vague). Les trois plages de
degat de la config DIFFERENT (1093 : 1109-1385 / 1662-1939 / 2770-3878), donc un port qui raterait
une vague ou melangerait deux bases se voit sur les VALEURS, pas seulement sur le compte.

Oracle = `aiPlaybookPredict` (le `MakeDamagePredictions` NATIF), compare **event par event, cible
par cible, champ par champ** (`appliedHits`, `healthDmgMin/Max`, `rawHealthDmgMin/Max`).

| bras | max \|dElev\| | 1035 (`deathTyphus`) | 1093 (`deathBlightlord`) |
|---|---|---|---|
| **plain** | 1 | `[4845,7269]` / `[3651,5475]` / `[1795,2693]` | `[2693,4040]` / `[3890,5834]` / `[4786,7180]` |
| **summon_T** (T porte `Summon`) | 1 | IDENTIQUE au bras plain | `[5385,8079]` / `[7779,11667]` / `[9573,14359]` |
| **summon_V** (V porte `Summon`, T non) | 1 | IDENTIQUE | IDENTIQUE au bras plain |
| **wide** (2 unites en vague 2) | 1 | `[4845,7269]` / `[3651,5475]` **x2** / `[1795,2693]` | `[2693,4040]` / `[3890,5834]` **x2** / `[4786,7180]` |
| **relief** (voisin GATE a `\|dElev\| = 2`) | **2** | `[4845,7269]` / `[2434,3650]` — **2 events** | `[2693,4040]` / `[2593,3889]` — **2 events** |

**MATCH bit-a-bit natif<->port sur les 32 events.** Le bras `summon_T` prouve le quirk dans un sens
(V et W ne sont PAS des summons et doublent quand meme) ; `summon_V` le prouve dans l'autre (le
summon FRAPPE ne double rien, pas meme son propre event).

**Le bras `wide` est la GENERALISATION du SET**, et sa geometrie est DERIVEE du `boardGraph` vivant :
`T` + **DEUX** voisins libres de `T` + un voisin de l'un d'eux hors de l'anneau 1. Les trois bras
`line` ne peuplent JAMAIS une vague de plus d'une unite : un port qui emettrait un event par VAGUE
au lieu d'un par UNITE y serait indiscernable. Ici les deux unites de la vague 2 recoivent la MEME
base et une valeur DISTINCTE de celles des vagues 1 et 3 (4 events = 3 valeurs, dont une en double).

### La PORTE D'ELEVATION — par ou elle entre, et le bras qui la fait mordre

`#433-r4-r1-r4` (PR #535) a branche `DslContext.elev_by_pos` sur le board. Ces vagues **SONT** de
l'adjacence, donc la question se pose : ce port a-t-il ete mesure porte INERTE ? **NON, et la voie
n'est pas celle qu'on croit.**

`adjacent_units` -> `AdjacentTiles` -> **`Board.neighbours_native`**, qui rend le champ **BRUT**
`boardGraph.neighbours`. `AdjacentTiles` **ne consulte JAMAIS `ctx.elev_by_pos`** (les deux seuls
lecteurs de ce canal sont `FilterTilesIfCanAttackTargetTileFrom` et `TilesOnSameElevationSelector`).
Or le capteur du `boardGraph` passe par `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`,
qui applique `|dElev| < 2` **INCONDITIONNELLEMENT** : **la porte est CUITE dans le canal**. Elle
etait donc deja active dans ces vagues, avant comme apres #535 — qui leur est INERTE.

**MESURE, pas deduction** (`gated_edges`, board vivant MC1_67) : **316** paires hex-voisines
orientees, **18 ABSENTES** du champ brut, **toutes a `|dElev| = 2`**, et **ZERO** absente sous 2.
Le refus du canal est donc exactement la porte d'elevation, et rien d'autre.

**Le bras `relief`** derive du `boardGraph` un triplet `(T, G, K)` ou `G` est hex-voisine de `T`
mais **GATEE**, `K` est un voisin **NATIF**, et `G` n'est voisin natif NI de `T` NI de `K` (sans
quoi elle rentrerait par la vague 3 et le bras cesserait de discriminer). Mesure : `T = (1,2)`
elev **2**, `G = (1,3)` elev **4**, `K = (0,1)` elev 3 -> le natif rend **2 events** (T et K),
`G` n'entre dans AUCUNE vague, et le port rend la meme chose.

⚠ **Sans ce bras, le vert des quatre autres ne prouvait RIEN sur cet axe** : leur `max |dElev|`
mesure vaut **1** (profil imprime par chaque bras). C'est exactement pour ca qu'il est la.

**Quatre mutations adversariales, chacune DEBORDANT ZERO** :

| mutation | plain | summon_T | summon_V | wide | relief |
|---|---|---|---|---|---|
| `waves` — `_MAKE_DMG_EXTRA_EVENTS` vide (retour a UN event) | ROUGE | ROUGE | ROUGE | ROUGE | ROUGE |
| `summon` — `wave_damage_formula` rend toujours l'avg nue | vert | **ROUGE** | vert | vert | vert |
| `quirk` — formule re-evaluee PAR UNITE FRAPPEE | vert | **ROUGE** | **ROUGE** | vert | vert |
| `hexgeo` — `neighbours_native` rendu en geometrie hex NUE | vert | vert | vert | vert | **ROUGE** |

⚠ La premiere version de la mutation `quirk` etait **INERTE** et rendait vert la ou elle devait
rougir : elle changeait l'ARBRE (`HasTrait(Subject())`), or `ctx.subject` est `None` hors `Filter`,
donc le predicat retombait sur `False`. La lecture naive ne s'exprime PAS dans l'arbre — le sujet du
`HasTrait` natif EST `Target` — mais dans le **moment de l'evaluation**. Corrigee, elle deplace
l'evaluation DANS la boucle avec l'unite frappee comme cible du contexte, et elle mord.

### Effet sur la DECISION — le residu de la TRANCHE r5 est ferme

Re-jeu de `probe_27_r5_mortarions_plague_wind.py --all` apres le port :

| bras | `u_full` port AVANT | `u_full` port APRES | `u_full` NATIF | `engine_decide` | natif |
|---|---|---|---|---|---|
| A | 1.1220 / 5.6097 | **13.276385 / 13.711814** | 13.276385 / 13.711814 | `(1093, T1)` | `(1093, T1)` |
| B | idem | **13.276385 / 13.711814** | idem | `(1093, T2)` | `(1093, T2)` |
| C | — | **28.2331 / 5.6097** | 28.2331 / 5.6097 | `(1093, T1)` | `(1093, T1)` |

Ecart residuel mesure sur `u_full` : **6.3e-09 / -1.0e-08** (`Fix64` cote natif, `double` cote
port). Le bras A est le plus fort des trois : le natif y va CONTRE son propre `u_full` (`T2` vaut
0.435 de plus), donc le moteur ne peut le suivre qu'en portant A LA FOIS les trois batchs de degat
ET le terme custom — et la contre-epreuve tient dans le meme run (`zero`, custom desarme, retombe
sur `T2`). Les 15 tests de la TRANCHE r5 restent verts ; deux gardes NEUVES les rejoignent.

### Ce qui n'est PAS couvert, et pourquoi

- **Le `hits_override` n'est pas discrimine LIVE.** `ExtraHits` (StatType 17) n'a AUCUN champ dans
  `BC.Units` — il ne vient que d'un effet, donc `--unit-stat` ne l'atteint pas. L'axe est garde
  OFFLINE (`test_the_hits_are_the_literal_constant_not_the_default_attack_hits`, qui verifie AUSSI
  que le chemin generique DIFFERE bien du litteral a `ExtraHits = 2` — sinon la garde ne garderait
  rien). Le correctif est du meme mold que trois autres deja confrontes live sur leur tranche.
- **Le `param_8` de 1035 vs 1093** (Nullable brut vs `GetValueOrDefault(-1)`) : inobservable sur ces
  deux configs, qui portent toutes deux `damageProfile`.
- **Le masque `3` de `SelectUniqueUnits`** (vivante ET sans le flag `0x11 NotTargetable`) : residu
  commun a tous les sets AoE portes, aucun substrat sur la face prediction.
- **La face COMBAT de 1093** (`...MortarionsPlagueWindAbility$$ExecuteBehaviour`) reste non portee
  — inchange par cette tranche, cf. TRANCHE r5.

## TRANCHE r6 (2026-08-03) — 1215 `InstrumentsOfVengeance` : le terme se mesure par le CHOIX DE TUILE

L'un des trois residus de la tranche r4 (les deux autres ont ete livres en parallele : 1093
§TRANCHE r5, 1217 §TRANCHE r7). Le corps, relu VERBATIM sur `rnca9r7q6c` :

    adj = battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false);
    u   = adj.Any() ? 0 : 100;
    foreach (e in battleQuery.<slot itf 0x78>(caster, casterPosition, range: 2,
                                              includeCenter: false))
        if (!adj.Contains(e)) u += 20;
    return Fix64.op_Implicit(u + 20000);

Les deux slots sont ancres par leurs decorateurs enregistreurs — `...DisplayClass155_0$$
u003CGetAdjacentEnemiesu003Eb__0` emet **0x80** (3 arguments), `...DisplayClass147_0$$
u003CGetSurroundingEnemiesu003Eb__0` emet **0x78** (4 arguments) — et ni l'un ni l'autre ne lit du
caster autre chose que son CAMP (`OwnerComponent$$get_CurrentPlayerEntityId` ; `UnitExtensions$$
IsEnemy` capture dans le predicat de `ListExtensions$$FilterInPlace`). Greffe legitime.

### Ce que la fiche r4 disait, et qui etait INSUFFISANT

Elle resumait le 3e terme par « `20 x |ennemis a d=2 non adjacents|` ». **`adj` et `surrounding`
n'ont pas la meme geometrie**, et ce resume perd exactement leur difference :

| ensemble | itereur natif | porte d'elevation |
|---|---|---|
| `GetAdjacentEnemies` | `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` | **OUI**, `\|dElev\| < 2` |
| `GetSurroundingEnemies` -> `GetSurroundingUnits` | `...$$IterateSurroundingTiles` (`TileUtil$$IsTileValidForList(..., checkElevation: 0)`) | **NON** — disque hex pur |

Un ennemi a distance hex **1** dont l'ecart d'elevation vaut `>= 2` est donc HORS `adj` et DANS
`surrounding` : il compte `+20` **et** laisse le `+100` arme. Le port compose donc
`is_surrounding(...) AND NOT is_adjacent(...)` au lieu de tester une distance.
**Ce n'est pas une precaution : le bras F ci-dessous MESURE que le modele resume choisit une autre
tuile que le natif.**

### Le masque : STATIC-COPY, et c'est ce qui separe 1215 de 1216

`...InstrumentsOfVengeanceAbility$$.ctor` recopie les 0x40 octets de
`<TargetingOptions statics>+0x280` dans une struct locale et la passe TELLE QUELLE a
`AActiveAbility$$.ctor` — **aucun appel a `TargetingOptions$$.ctor`**, ni la surcharge « flags
directs », ni la surcharge PRESET+FLAGS. Le masque effectif est la constante ecrite par
`...TargetingOptions$$.cctor` en `<preset>+0x28` :

    0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)

C'est le **meme preset** que 1216 `MartialExemplar`, qui lui ajoute `additionalRules = 0x10`. Les
deux consequences se separent donc net :

| | 1216 | 1215 |
|---|---|---|
| `CasterIsPossibleTarget` | oui -> SELF-CAST | oui -> SELF-CAST |
| `CasterHasNotMoved` | **oui** -> une SEULE action par tour | **non** -> une action PAR TUILE |
| magnitude discriminable ? | **non** (r4 le dit) | **oui**, par le CHOIX DE TUILE |

C'est le fait central de cette tranche : ce que r4 ne pouvait pas mesurer sur 1216, le meme montage
le mesure sur 1215, parce que le sweep de tuiles existe.

### Ce qui est porte

- `engine/playbook/loki_custom.py::InstrumentsOfVengeancePlaybook` (`NonAttackComparablePlaybook`,
  registre `NONATTACK_PLAYBOOKS`) : `calculate_custom_utility` + les deux ensembles, chacun avec sa
  geometrie. Constantes nommees (`BASE_UTILITY`, `NO_ADJACENT_ENEMY_UTILITY`,
  `NON_ADJACENT_SURROUNDING_UTILITY`) — aucune n'est un poids `BC.Utilities`.
- `engine/runner/abilities/targeting.py::TARGETING_OPTIONS_UNPORTED[1215] = 0x8004` (face COMBAT non
  portee : `...InstrumentsOfVengeanceAbility$$ExecuteBehaviour` est un arbre DSL substantiel).
- **Aucune primitive neuve** : `battle_query.is_adjacent` et `battle_query.is_surrounding` existaient
  deja et portent deja la distinction. C'est leur COMPOSITION qui est le port.

ROUTE NON-ATTAQUE bien que `constants.damageProfile = HeavyRound` : `abilityTargets(1215)` rend UNE
cible (le caster), et les `attackPlans.evals` de 1215 sur les ENNEMIS rendent tous `rankCount = 0`
-> `_best_attack` ne peut rien produire. `pairUtility(1215, SELF) = 0` -> `make_damage_predictions`
rend `[]` (herite), exactement comme le natif.

### Validation live (`probe_27_r6_instruments_of_vengeance.py`, board MC1_67, seed 909, rank 17)

Porteur GREFFE sur **`darkaAsmodai`** (`ActiveAbilities = [1215]` dans une COPIE du seed BC). Le
caster n'est deplace qu'au dernier bras : c'est le SWEEP DE TUILES qui est le levier, le supprimer
degenererait tous les autres. La fenetre deterministe `GetTurnsFinished >= 2` est atteinte par
**quatre `act endturn`** (l'IA ne joue pas -> la geometrie du montage est intacte), et le probe
VERIFIE `turnsFinished == 2` au `combatSnapshot` avant de mesurer.

| bras | geometrie | natif | moteur | contre-epreuves (custom=0 / route OFF / modele FAUX) |
|---|---|---|---|---|
| E | `turnsFinished = 0` | `MoveUnitMessage` **SEUL** | `1215` | — (ECART NOMME, cf. plus bas) |
| A | tous a d >= 3 | `1215`, **sans move** (custom CONSTANT 20100) | idem, `to=None` | `1215` / **move nu** / `1215` |
| B | un ennemi en (2,0), ADJACENT a l'origine | move **(0,0)** + `1215` | idem | **`69`** / **`69`** / `1215` (0,0) |
| C | un ennemi en (5,1), adjacent a AUCUNE tuile | move **(3,0)** + `1215` | idem | **`69`** / **`69`** / `1215` (3,0) |
| F | (1,3) et (2,3) a elevation **4**, (1,2) a **2** ; (3,2) occupee | move **(1,2)** + `1215` | idem | **`69`** / **`69`** / **`1215` (1,1)** |
| D | le caster BOUGE | `abilityTargets(1215)` inchange (1 cible), le natif propose toujours `1215` | — | — |

Lectures :

* **A** est le temoin : custom constant -> le natif ne bouge pas. Si ce bras faisait bouger le natif,
  les trois suivants ne prouveraient plus rien.
* **B** mesure le `+100` : l'origine passe de 20100 a 20000 parce qu'un ennemi y devient adjacent, et
  le natif DEPLACE le caster pour caster depuis une tuile qui garde son `+100`.
* **C** mesure le `+20` seul : aucune tuile n'a d'ennemi adjacent, le `+100` est donc constant, et
  seule la presence d'un ennemi a distance 2 departage (3,0) (20120) de l'origine (20100).
* **F** mesure le QUIRK, et c'est la seule mesure qui separe le port de son resume : la tuile
  gagnante (1,2) tire son avantage d'un ennemi a **distance 1** (en (1,3)) que la porte d'elevation
  exclut d'`adj`. Le modele `20 x |dist == 2|` monte a la place en **(1,1)** — **DIVERGENCE du natif**.
* **D** est la contre-epreuve du masque : si `CasterHasNotMoved` y etait, `abilityTargets(1215)`
  tomberait a 0 apres le move (c'est ce que 1216 fait, mesure en r4). Il ne tombe pas.
* Le RPC `pairUtility` rend `playbookClass = InstrumentsOfVengeancePlaybook` **sur l'unite greffee** :
  seconde preuve, independante du choix, que le natif charge le playbook PAR ABILITY.

Garde : `tests/engine/test_instruments_of_vengeance_decision_live.py` (14 tests — 10 live, 4 offline).

### Ce qui n'est PAS couvert, et pourquoi

- ~~**Le gate `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate` (surcharge 2-args, slot 4) n'est
  PAS porte**~~ — **PORTE (#27-r8)**, et le debloqueur annonce ici (« un CAPTEUR, donc une fenetre
  de reinject ») etait **FAUX**. Cf. §TRANCHE r8. Reste PERMISSIF, et c'est declare : le volet
  `GetTurnsFinished == 1` -> `Fix64.Half` est un TIRAGE (meme statut que le 1/3 de 1098).
  * `BattleQuery$$HasMinimumRemainingTurns(unit, 2)` **n'utilise pas son parametre `unit`** : il lit
    la limite de tours du match (`<config>+0x18`, cle 1) moins
    `TurnComponent$$GetAmountOfTurnsEndedByPlayer`, et **rend `true` quand la limite est absente** —
    le regime du runner. Le defaut permissif de la route y est donc EXACT ; aucun canal offline
    n'expose cette limite.
- **La face COMBAT** (`...InstrumentsOfVengeanceAbility$$ExecuteBehaviour` : `If` sur deux paires de
  `GetEffectBehavior`, `AddBondEffect(0x5ef)`, `If(!HasAdjacentEnemies) ActivateEffect(0x3f1)`, et
  par direction `TilesBehindInLine` / `EdgeTilesByDirection` / `SortByFormula` /
  `SetPersistentData` / `AddEffect(0x5ee)`) n'est pas portee — hors perimetre de cette tranche.
  L'invocation annoncee par la fiche (`constants.unitId = darkaSmnTerminator`, `nrOfSummons`) en
  fait partie.
- **La base `20000` n'est pas discriminee**, et elle ne peut pas l'etre par ce montage : elle place
  1215 au-dessus de toute autre action des qu'elle est legale, donc toute valeur assez grande
  produirait les memes choix. Ce sont les deux AUTRES constantes que le sweep de tuiles mesure. Le
  `20000` est LU (constante en dur, aucun `GetUtilityValue`).
- La greffe ne couvre pas les stats/traits/armes de `darkaBossLion` — legitime ICI puisque la
  formule n'en lit aucun.


## TRANCHE r7 (2026-08-03) — 1217 `TheLionsWrath` : le piege n'etait PAS ou la fiche l'annoncait

La fiche #27-r7 nommait UN piege (le `ShouldEvaluate` mal reconstruit par Ghidra) et il etait reel,
mais mineur. **Le verrou du port etait ailleurs, et il ne se voit qu'en decomposant par etage** :
`...TheLionsWrathPlaybook$$MakeDamagePredictions` rend une liste **VIDE**.

### 1. La formule custom, CONFIRMEE au decompile

`IdunBattle.AI.Playbook.Loki.TheLionsWrathPlaybook$$CalculateCustomUtility` :

    n = 0; hits = 0;
    foreach (e in battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false))
        if (IsNormalUnit(e) && HasTrait(e, 0x7ea Chaos) && HasTrait(e, 0x10 Hero))  n++;
    var w = battleQuery.<slot itf 0xb2>(target);            // FindMeleeWeapon(TARGET), surcharge 1-arg
    if (w != null) hits = w.<+0x20>;                        // Hits
    return Fix64.op_Implicit(hits * 0x1e + n * 2000 + (HasTrait(target, 0x10) ? 0x96 : 0));

Aucun `GetUtilityValue` : `30`, `2000` et `150` sont EN DUR. Les deux premiers facteurs sont lus sur
la **CIBLE** — c'est ce qui rend le terme discriminant par cible, et l'ability greffable malgre un
porteur `darkaBossLion` [npc].

`FindMeleeWeapon(unit)` (slot `0xb2`) = `FindMeleeWeapon(unit, null, null)` : le `target` nul rend la
branche `SelectBestDamageWeapon` MORTE, c'est toujours `SelectMaxRangeWeapon({w : w.IsMelee})` qui
tranche. Port : `engine/services/battle_query.py::find_melee_weapon` (symetrique exact de
`find_ranged_weapon`, deja la) + `weapon_hits` (defaut **0**, pas 1).

### 2. Le gate, relu A L'ASSEMBLEUR — et sa jumelle qui prouve le decodage

Ghidra rend `(extraout_var >> 7 ^ 1) & bVar1`, un decalage de 7 sur un OCTET. Les octets disent
autre chose :

    call  <slot 0x1b>(unit, 2)   ; HasMinimumRemainingTurns  -> movzx ebp, al
    call  <slot 0x80>(position, unit, false)                 ; GetAdjacentEnemies
    call  <Count>                                            ; -> eax
    c1 e8 1f    shr   eax, 0x1f      ; bit de SIGNE du compte (32 bits, pas 8)
    34 01       xor   al, 1          ; -> (count >= 0)
    40 22 c5    and   al, bpl        ; & HasMinimumRemainingTurns

soit `HasMinimumRemainingTurns(unit, 2) && (Count() >= 0)` — le second terme est **TOUJOURS VRAI**.

**La contre-epreuve qui ancre ce decodage** : `...MartialExemplarPlaybook$$ShouldEvaluate` est
structurellement IDENTIQUE (memes DAT, meme slot 0x80, meme `Count`) et finit par
`83 f8 01 / 0f 9d c0` = `cmp eax,1 ; setge al` = `Count() > 0`. Les deux fonctions different
EXACTEMENT a cet endroit. Recopier `> 0` par analogie — la pente naturelle — aurait pose un gate que
le natif n'a pas.

Le terme restant, `HasMinimumRemainingTurns`, **n'utilise pas son parametre `unit`** :
`IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` lit `limit = <config dict>[1]`,
rend `true` si `!limit.HasValue`, sinon `turns <= limit - TurnComponent$$GetAmountOfTurnsEndedByPlayer`.
Gate GLOBAL au match. Le plafond de tours n'a **aucun substrat cote port** — meme constat, et meme
mot, que le bit `CasterHas2TurnsLeft` de 1160 (`runner/abilities/tau.py`), qui appelle le MEME natif.
Le gate se reduit donc a `True`, c.-a-d. au defaut de `NonAttackComparablePlaybook.should_evaluate` :
l'overrider serait du code mort. **Residu nomme `#27-r4-g`** — il ne peut mordre que dans un match A
PLAFOND DE TOURS, qu'aucun runner d'arene ne monte.

### 3. LE VERROU : `MakeDamagePredictions` rend `[]`, et c'est la route qui change

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`
est **ABSTRAITE** — son corps entier est `FUN_1801f4390(<classe>, 0)`, la levee
`NotImplementedException`. Un override existe donc forcement pour 1217, et il est ABSENT de la table
de symboles (corps DEDUPLIQUE — exactement le faux negatif que le `CLAUDE.md` decrit).

**TROIS canaux independants** disent qu'il rend une liste vide NON NULLE :

| canal | mesure |
|---|---|
| `aiPlaybookPredict(1217)` (= `MakeDamagePredictions` natif) | `retClass = ProbableDamageEvent[]`, `listNull = false`, `count = 0` — l'appel REUSSIT, il ne leve pas |
| `pairUtility(1217)` (= `CalculateUtilityFromPredictions` natif) | `utility = 0`, `utilRaw = "0"`, sur les DEUX cibles |
| COMPORTEMENTAL (le decisif) | dans le bras `--hp-ahriman 100`, la PREVIEW d'attaque vaut **238,04** sur `thousAhriman` contre **8,01** sur `blackAbaddon`, et le natif choisit `blackAbaddon` — il n'ajoute donc AUCUNE utilite de degat |

Coherent avec le kit : `...TheLionsWrathAbility$$ExecuteBehaviour` DIFFERE l'attaque dans
`IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect` ; il n'y a pas de degat a
predire au moment du cast.

**Consequence de ROUTE, et c'est tout le fix.** `ComparablePlaybook<T>$$CalculateActionUtility`, relu
verbatim, enchaine `u = 0 + custom` PUIS `u += CalculateUtilityFromPredictions(...)` PUIS
`if (!ShouldExecute(caster, tile, target, u)) return Nullable.Empty`. Le gate recoit donc
`custom + predictions`, jamais les predictions seules. Cote port :

- `base.ComparablePlaybook.calculate_action_utility` rend `None` sur `events == []`, et
  `ComparableAbilityGenerator.generate` gate sur `best[0] > 0` (l'utilite de DEGAT). **`_best_attack`
  ne peut donc structurellement pas produire 1217** — c'est le motif de **1009 ResurrectionOrb**.
- `nonattack_candidates` mirroir `CalculateActionUtility` A LA LETTRE (`u = custom`, `u += preds`,
  `should_execute(u)`, `full = u + tile`). C'est la bonne route.

⇒ 1217 entre dans `NONATTACK_PLAYBOOKS`, **4e motif** d'entree apres « pas de `damageProfile` »
(1226, 1185), « masque refusant toute cible ennemie » (1100) et « masque SELF-CAST » (1216) — et ce
alors meme que 1217 A un `damageProfile` (`Power`) ET des `attackPlans` a `rankCount > 0`.

**MESURE de la divergence, avant/apres** (bras `--hp-ahriman 100`, natif = `(1217, blackAbaddon)`) :

| etat du port | decision moteur |
|---|---|
| prediction generique (heritee), route attaque | `(1217, thousAhriman)` — la PREVIEW fantome de `attackPlans` (identique a celle de l'attaque normale) ecrase l'ecart de custom de 120 |
| `MakeDamagePredictions -> []`, route attaque | `(None, None)` — le gate `best[0] > 0` supprime l'action |
| `MakeDamagePredictions -> []`, route NON-ATTAQUE | `(1217, blackAbaddon)` = **natif** |

### 4. Le masque, et pourquoi il n'y a PAS de piege PRESET+FLAGS ici

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$.ctor` recopie les 0x40 octets
du preset `<TargetingOptions statics>+0x40` et les passe TELS QUELS a
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, abilityAttackType)`, dont le corps
recopie la struct dans `this+0x70..0xac` **sans OU-er le moindre flag** (le 3e argument est
l'`AbilityAttackType`, ici le litteral `0`, ecrit a `this+0x68`). Champs du preset, lus dans
`IdunBattle.Core.Services.TargetingOptions$$.cctor` :

    +0x40  isSelfCasting    = 0
    +0x48  range            = recopie de <TargetingRange statics>+0x30 = RANGE_ADJACENT
    +0x60  forceMeleeTarget = 1 = RangedBool.False
    +0x68  rules            = 0x4000 = TargetIsEnemy, et RIEN d'autre

`TARGETING_OPTIONS_UNPORTED[1217]` (face COMBAT non portee ⇒ cette table, pas `ABILITY_CLASSES`).

### 5. Confrontation LIVE — greffe `darkaAsmodai`, board MC1_67, seed 909, rank 17

Caster en `(1, 0)` ; les deux cibles sur deux voisins ; `thousAhriman` a `Health = 100`
(`--unit-stat`) pour que sa PREVIEW ecrase celle de `blackAbaddon`. Le CASTER n'est jamais deplace.

| | `blackAbaddon` (Hits 5) | `thousAhriman` (Hits 1) |
|---|---|---|
| `u_full` NATIF de 1217 (`pairUtility`) | **0** | **0** |
| `MakeDamagePredictions` natif | **0 event** | **0 event** |
| custom PORTE | **4300** = 30x5 + 2000x2 + 150 | **4180** = 30x1 + 2000x2 + 150 |
| PREVIEW (`pairUtility(69)`) | 8,01 | **238,04** |

Les deux argmax DIVERGENT (custom -> `blackAbaddon`, preview -> `thousAhriman`) : le bras est
discriminant. Natif = `ActiveAbilityMessage(1217, blackAbaddon)`, moteur = idem.

**Bras SWAP** : les deux cibles ECHANGENT leurs tuiles (via une 3e tuile — un `act move` croise est
REFUSE en silence, et `_assert_placed` le voit). Le natif choisit **toujours** `blackAbaddon` : son
choix ne vient donc pas de l'ordre d'enumeration des cibles (rang cube croissant, keep-first STRICT).

**Trois contre-epreuves, toutes MORDENT** :

| contre-epreuve | decision moteur | ce qu'elle exclut |
|---|---|---|
| `custom` force a 0 | `(69, thousAhriman)` | le terme n'est pas decoratif |
| registre `NONATTACK_PLAYBOOKS` VIDE | `(69, thousAhriman)` | la route n'est pas inerte |
| terme `30 x Hits` NIE (`-30`) | `(1217, thousAhriman)` | **ce terme-la** est bien ce qui departage les cibles |

Gardes : `probe_27_r4_lions_wrath.py` (2 bras x 3 contre-epreuves, `VERDICT: PASS`),
`tests/engine/test_lions_wrath_decision_live.py` (11), `tests/engine/test_lions_wrath_custom_utility.py`
(11, offline).

### 6. Ce qui n'est PAS couvert, et pourquoi

- **Le terme `2000 x n` n'est pas DISCRIMINE**, seulement porte et verifie offline. Il ne depend que
  de `casterPosition`, donc il ne departage jamais deux cibles ; et comme 1217 est ADJACENT-only,
  changer de tuile change AUSSI l'ensemble des cibles legales — un bras « tuile a n=1 contre tuile a
  n=0 » ne serait pas un comparatif toutes choses egales par ailleurs.
- **Le terme `150 x [cible Hero]` est CONSTANT dans tout montage de heros** : les **97** unites du
  pool rank 17 portent TOUTES le trait `Hero` (compte re-derive, pas herite). Le discriminer exige
  une cible sans `Hero` : un SUMMON adverse (les 65 summons en sont depourvus) — la MoW, elle, est
  hors d'atteinte, le masque `0x4000` n'ayant pas le bit de domaine `TargetIsActor`, si bien que
  `TargetIsUnit` la refuse.
- **Le filtre `IsNormalUnit && Chaos && Hero` sur les adjacents** n'est pas exerce en LIVE (il
  faudrait un ennemi `Object`/`Steppable` adjacent au caster au spawn) : garde OFFLINE.
- **La face COMBAT de 1217 n'est pas portee** — `...TheLionsWrathAbility$$ExecuteBehaviour` est un
  arbre DSL (`AddBondEffect`, `AddEffect`, `IfAlive`, `AttackWithAttackDamage`) dont le degat passe
  par `TheLionsWrath_PendingAttackEffect`. Hors perimetre de cette tranche (DECISION seule).
- **Le gate `should_execute` de la BASE** reste le defaut `True` du port. Le corps natif de
  `ComparablePlaybook<T>$$ShouldExecute` n'est pas nomme (dedupli), et 1217 ne l'override pas ; la
  MESURE (le natif emet bien l'ability, avec `u = custom = 4300`) est compatible aussi bien avec
  `true` qu'avec `utility > 0` — le montage ne les separe pas. Sans consequence ici : `custom >= 30`
  des qu'une cible existe.

## TRANCHE r8 (2026-08-05, #27-r8) -- l'inventaire des CORPS est CLOS ; le gate slot-4 de 1215 est PORTE

### 1. Ce que la tranche devait faire, et ce que la mesure a rendu

La tranche etait dispatchee comme << les overrides `CalculateCustomUtility` restants >>, avec pour
consigne de re-deriver l'inventaire (<< 28 classes / 27 corps >> etant un chiffre a re-mesurer).
**Re-derive, il n'en reste AUCUN.**

Mesure OFFLINE, sans runner ni ghidra-mcp (`data/symbols/rnca9r7q6c/`) :

| source | corps `$$CalculateCustomUtility` | note |
|---|---|---|
| `ghidra/functions.tsv` | **29** (+1 lambda `DrachnyenPlaybook.<>c$$<CalculateCustomUtility>b__3_0`) | inclut les gshared |
| `frida/methods.tsv` | **26** (+1 lambda) | les gshared y sont structurellement absents |
| ecart | **3** | `ComparablePlaybook<T>`, `ALoki_NormalAttackPlaybook<T>`, `Idun.NormalAttackPlaybook<T>` |

Les deux sources concordent entre elles et avec le balayage de vtable de la §TRANCHE 4g (29 corps
distincts = 26 nommes + 3 partages). **Les 29 sont tranches**, et la partition est EXHAUSTIVE
(23 + 5 + 1 = 29) :

- **23 PORTES** : 1014, 1177, 1020, 1029, 1199, 1119, 1230, 1227, 1226, 1185, 1212, 1100, 1051,
  1098, 1009, 1169, 1148, 1222, 1004, 1093, 1215, 1216, 1217 ;
- **5 COUVERTS sans port dedie** : les 3 gshared (`ComparablePlaybook<T>` = `Fix64(0)`,
  `ALoki_NormalAttackPlaybook<T>` et `Idun.NormalAttackPlaybook<T>` = `Fix64(1)`) plus
  `TwistedScience_HealPlaybook` (`HealPlaybook.score`) et `Loki_NormalBossAttackPlaybook` ;
- **1 DEAD-CODE** : `ProperKilly_NormalAttackPlaybook` (aucun porteur).

⚠ `DevoutPush` (1053) et `MalleusRocketLauncher` (1142) ne figurent PAS dans ces 29 : ils n'ont
**aucun corps propre** sur ce build (cf. §TRANCHE 4g) -- les compter serait un doublon.

Le compte d'items PORTABLES restants est donc **zero**.

### 2. Deux affirmations de la fiche etaient FAUSSES, et la plus couteuse est une CONTRADICTION INTERNE

- **1169 `PlagueburstMortar` etait porte depuis #302, et le TABLEAU disait encore
  << invalidable-residu >>** (VERROU 1 idem). La *Ventilation*, six lignes plus bas, le classait
  pourtant parmi les PORTES. Le port existe (`engine/playbook/plagueburst_mortar.py`, enregistre
  par `engine/playbook/__init__.py`) et il est confronte
  (`tests/engine/test_plagueburst_mortar_decision_live.py`, **10 verts** re-joues le 2026-08-05).
  La cellule perimee etait celle qu'un dispatch lit EN PREMIER. Les deux entrees sont corrigees.
- **Le debloqueur annonce pour `#27-r6-r1` -- << `turnsFinished` absent de `decisionView`, donc un
  CAPTEUR a ecrire, donc une fenetre de reinject >> -- etait faux sur DEUX crans** (cf. §3).

Le backlog portait en outre deux entrees OUVERTES pour des tranches deja LIVREES (`#27-r2`
`ResurrectionOrb`, livree par #289 ; `#27-r4`, dont la version barree << LIVRE >> coexistait avec
une version ouverte). Corrigees.

### 3. Le verrou de `#27-r6-r1`, et pourquoi il n'existait pas

Le gate, relu VERBATIM :

```
IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$ShouldEvaluate(unit)   // slot 4
    return BasePlaybook.ShouldEvaluate(unit) && battleQuery.<slot itf 0x1b>(unit, 2);

IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability(unit)
    t = UnitExtensions.GetTurnsFinished(unit);
    if (t != 0) { if (t != 1) return Fix64.<statics+0x20>;   // One
                  return Fix64.<statics+0x30>; }             // Half
    return Fix64.<statics+0x28>;                             // Zero

IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)
    p = <vtable +0x1f8> GetUseProbability(unit);
    if (p >= Fix64(1)) return true;
    if (p <= Fix64(0)) return false;
    return random.<slot 4>(p);                               // TIRAGE
```

Les trois statiques sont LUS au `FixMath.NET.Fix64$$.cctor`, pas deduits du nom :
`+0x20 = 0x100000000` (One), `+0x28 = 0` (Zero), `+0x30 = op_Division(1, 2)` (Half).

### Le TIREUR est nomme (#27-r9, 2026-08-07) — et le blocage change de nature

Le `random` de la derniere ligne est le champ **`BasePlaybook+0x30`**, invoque par
`FUN_180005000(4, <klass>, this+0x30, p)` — donc le slot 4 d'une **interface**, et **uniquement**
dans la branche `0 < p < 1`. Ce n'est ni un statique `UnityEngine.Random` ni un `System.Random`
local : c'est un champ d'INSTANCE, injecte a la construction du playbook.

La classe de ce slot est celle qu'initialise `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$AddListener` —
autrement dit **le PRNG DE BATAILLE**. La meme classe apparait chez
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`,
`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` / `$$FindTileToPullOnce` et
`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetUnitToSpawn` — trois consommateurs **deja
portes** cote runner sur `state.rng`. Le tirage est donc **rejouable depuis un etat**, et la
question ouverte n'est plus « quel generateur » mais **a quel RANG dans le flux**.

⚠ **Et c'est pour ca que rien n'est inscrit.** Le port ne reproduit pas la sequence d'evaluation
des playbooks tuile par tuile ; poser le tirage au mauvais rang **decalerait tout le flux PRNG** en
aval et casserait des accords aujourd'hui verts (degats, spawns, displacements). Le correctif
serait donc RESTRICTIF *et* perturbateur — deux fois pire que l'ecart permissif qu'il ferme.
Restent a etablir : le NOM du slot 4 sur `DisallowablePseudoRNG`, et si l'evaluation IA consomme ce
flux **dans la bataille** ou dans une copie isolee (l'existence d'un `AddListener` suggere un flux
ENREGISTRE, donc bien celui de la bataille — indice, pas preuve).

**Le blocage tombe sur deux crans :**

1. **Le capteur EXISTE deja**, livre par #N11 : `getTurnsFinishedMi`
   (`frida/hooks/features/ai-step/internals.ts`) et le champ `turnsFinished` de
   `frida/hooks/features/ai-step/rpc-snapshot.ts`. Il alimente `UnitComponent.turns_finished`, que
   `engine/runner/turnflow.py::_bump_turns_finished` tient AUSSI offline (mirror
   d'`IdunBattle.Operations.EndTurnOperation$$Execute`). Rien n'etait a instrumenter, donc aucune
   fenetre de reinject n'etait requise.
2. **Surtout, la premisse portait sur le mauvais canal.** La `Scene` de DECISION ne se construit pas
   depuis `decisionView` pour ces tables : `scene.build_predictor` les lit dans **`combatSnapshot`**
   -- c'est deja de la que vient `turnsStarted` (#46), a trois lignes du champ manquant. Et
   `combatSnapshot` renvoie `turnsFinished` par defaut (`wants(part)` ne filtre que si `debugOnly`
   est passe, ce qu'aucun appelant ne fait). Il n'y avait qu'un FIL a brancher.

⚠ La lecon est celle d'un canal nomme par le MAUVAIS bout : << absent de `decisionView` >> etait
vrai, et sans consequence -- le consommateur ne lisait pas `decisionView`. Un verrou doit nommer le
canal que le CONSOMMATEUR lit, pas celui auquel on pense en premier.

### 4. Ce qui est porte

- **`Scene.turns_finished_by_id` + `Scene.turns_finished(uid)`** (`engine/playbook/scene.py`),
  alimente par les TROIS voies, exactement comme `turns_started_by_id` : `from_state` (ECS, via
  `UnitComponent.turns_finished`), `build_predictor` (cold) et `refresh_shields` (par-pas -- le
  compteur est DYNAMIQUE, un cold fige au pas 0 refuserait 1215 pour toute la bataille).
  Accesseur **tri-etat** : `None` = non capte -> l'appelant ne gate pas a l'aveugle. Un `0` de repli
  signifierait `Fix64.Zero`, donc un REFUS que le natif n'a pas prononce.
- **Le gate AMONT slot-4 de la route non-attaque** (`engine/playbook/nonattack.py` :
  `should_evaluate_unit`, appele PAR ABILITY avant l'enumeration des tuiles). Sa POSITION est LUE
  dans `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :
  la machine a etats enchaine, par ability, `AActionGenerator$$CanAbilityBeUsed` ->
  `PlaybookDatabase$$LoadPlaybook` -> **slot 4 `(unit)`** -> **slot 5 `(unit, actionTiles)`** ->
  `GetEnumerator()` sur les tuiles -> et seulement la, par position, slot 6 puis
  `battleQuery.<slot 0x40>` puis slot 7 `Evaluate`. Les slots 4 et 5 court-circuitent donc
  l'ability ENTIERE, pas une tuile. **Defaut `True` = le corps natif EXACT** (les deux surcharges de
  `IdunBattle.AI.Playbook.BasePlaybook$$GetUseProbability` rendent `Fix64.op_Implicit(1)`), pas une
  convention permissive de notre cote.
- **L'override de 1215** (`engine/playbook/loki_custom.py::InstrumentsOfVengeancePlaybook`) :
  `t == 0 -> False` (deterministe) ; `t == 1 -> Half -> TIRAGE, laisse PERMISSIF` ;
  `t >= 2 -> True`. `HasMinimumRemainingTurns(unit, 2)` vaut `True` dans le regime du runner (le
  natif rend `true` des que la limite de tours est absente) -- deja etabli en §TRANCHE r6.

**FACE DECISION UNIQUEMENT.** Un gate n'a pas de face EXECUTION ; celle de 1215
(`...InstrumentsOfVengeanceAbility$$ExecuteBehaviour`) reste non portee, comme en §TRANCHE r6.

### 5. Validation -- l'accord est ATTRIBUE, pas constate

Montage inchange (`probe_27_r6_instruments_of_vengeance.py`, board **MC1_67**, seed **909**, rank
17, greffe `[1215]` sur `darkaAsmodai`). Le bras E CHANGE DE NATURE : il mesurait un ECART NOMME, il
mesure desormais un ACCORD -- et parce qu'un accord seul ne prouverait rien, il vaut TROIS
assertions :

| cran | mesure (2026-08-05) | pourquoi il existe |
|---|---|---|
| substrat | `Scene.turns_finished(caster) = 0`, `gate = False` | un canal MUET rendrait le gate permissif : l'accord serait celui d'un regime DEGENERE |
| accord | natif `['MoveUnitMessage']` ; moteur `on = (None, None)`, `to = (3,2)` | ni l'un ni l'autre ne propose 1215 |
| contre-epreuve | gate NEUTRALISE -> moteur `(1215, 83, None)` | attribue l'accord AU GATE, et pas a autre chose |

⚠ **Ces trois valeurs ont ete mesurees DEUX FOIS, sur DEUX sessions Frida distinctes**, et la
seconde n'est pas une precaution de forme : le jeu a ete relance en cours de tranche et une premiere
serie de runners est passee dans la fenetre ou le drain etait retombe **avant** que l'amorce ne
soit joue. Un runner monte sur session NON WARMEE rend `started: true` et ne prouve rien. La serie
retenue ici est integralement celle d'apres amorce ; elle reproduit la premiere **a l'identique**
(memes tuiles, memes triplets), et le seul artefact de la fenetre a ete un `rc = 2` transitoire de
`probe_477r15a_stream_conformance.py`, revenu a `rc = 0` sans qu'aucune ligne de code ne bouge.

Les cinq autres bras (A/B/C/F/D, mesures a `turnsFinished == 2`) restent **inchanges et verts** : le
gate ne mord pas dans la fenetre deterministe, donc le port de la formule n'est pas touche.

**Contre-epreuve du TEST lui-meme** (ecrite sur disque, pas simulee) : `return t != 0` remplace par
`return True` dans `loki_custom.py` rend `test_slot4_gate_truth_table_offline` **ROUGE**
(`assert True is False`) ; restauration verifiee par `git checkout` + re-jeu **VERT**.

**Non-regression re-jouee APRES rebase sur `origin/master` ET apres amorce** (tous verts,
2026-08-05, **70 tests**) : `test_instruments_of_vengeance_decision_live` **16** (14 + 2 gardes
offline neuves), et les six autres membres de la route non-attaque --
`test_chronometron_decision_live` 7, `test_martial_exemplar_decision_live` 9,
`test_lions_wrath_decision_live` 11, `test_plagueburst_mortar_decision_live` 10,
`test_forward_observers_decision_live` 6, `test_sorcerous_facade_decision_live` 8 -- plus
`test_playbook_live` 3. `probe_477r15a_stream_conformance.py` **rc 0** (204/204 et 316/316) et
`probe_468_collision_numeros.py` **PASS**.

Le re-jeu post-rebase n'etait pas une formalite : la PR fusionnee entre-temps touchait
`scripts/python/catalog_inject.py` et `scripts/python/rl_duel.py`, c'est-a-dire exactement les deux
outils dont depend la GREFFE qui rend 1215 confrontable.

### 6. Ce qui n'est PAS couvert, et pourquoi

- **Le volet `GetTurnsFinished == 1` -> `Fix64.Half`** reste PERMISSIF : le natif y TIRE a pile ou
  face (`random.<slot 4>(p)`) et le moteur n'a pas son PRNG a ce point. Meme statut que le `1/3` de
  `...PlasmaGrenadePlaybook$$GetUseProbability`. Rendre `False` y serait aussi faux que `True`, mais
  RESTRICTIF -- on garde le sens qui ne retire jamais une action que le natif peut jouer.
  **Residu `#27-r9`** : porter le PRNG de decision (`random.<slot 4>`) rendrait ce volet mesurable,
  et fermerait du meme coup les deux gates a tirage du dossier (1215 et 1098).
- **Le slot 5** `ShouldEvaluate(unit, actionTiles)` n'est PAS cable : AUCUN membre du registre
  non-attaque ne l'override sur ce build. Son seul overrideur mesure est
  `...DutyEternalPlaybook$$GetUseProbability` (= `Fix64.FromIntFraction((GetTurnsFinished(unit) -
  GetNumberConstant(config, 0x68) + 1) * 33, 100)`), dont le porteur `ultraDreadnought` est une
  Machine of War -- hors face DECISION tant que le tacticien MoW n'existe pas. Un crochet sans
  porteur serait du code speculatif.
- **La route ATTAQUE (`_best_attack`) n'a pas ce gate amont.** Le cran natif y est le MEME (c'est le
  meme generateur), mais aucun de ses membres n'override le slot 4 par un corps modelisable : le
  seul qui l'override est 1098 `PlasmaGrenade`, dont `GetUseProbability` rend `1/3` -- un TIRAGE,
  donc le meme mur que ci-dessus. Poser un gate `True` inconditionnel de ce cote n'ajouterait aucune
  fidelite. Nomme, pas masque.
- **`HasMinimumRemainingTurns`** : aucun canal offline n'expose la limite de tours du match ; le
  defaut permissif est EXACT dans le regime du runner (residu deja nomme en §TRANCHE r6).
- **Le volet `IsTemporary` du slot 6** (`BasePlaybook$$ShouldEvaluate(unit, position,
  possiblePositions)` refuse une position posee sur une tuile temporaire, sauf si le predicat de
  vtable `+0x1d8` l'autorise) reste non porte. `ctx.is_temporary_by_pos` existe en LIVE
  (`tileMeta.isTemporary`) mais vaut `{}` en offline pur, et le predicat `+0x1d8` n'est nomme dans
  AUCUNE des deux tables -- le resoudre exige un balayage de vtable au runtime. Residu deja nomme
  dans `engine/playbook/nonattack.py`.
