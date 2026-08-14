# #970-r3 — deux faces DÉCISION de kits COMPLETS : `1200 SquigLaunchas` et `1168 EntropyCannons`

Build : `rnca9r7q6c`. Base : `origin/master` `d17bb06d`.

Les deux abilities ont leur face **COMBAT** portée et confrontée. Ce qui manquait est l'utilité de
**DÉCISION** — l'IA les choisissait avec un scoring qui n'est pas celui du natif. Divergence de
**politique**, invisible en replay puisque l'exécution est fidèle ; c'est pourquoi leurs kits
sortaient « COMPLETS » de `audit_kit_coverage.py`, dont `missing` ne compte que la face COMBAT.

| id | ability | porteur | classe de playbook native (source) | verdict |
|---|---|---|---|---|
| 1200 | `SquigLaunchas` | `orksRukkatrukk` (MoW Orks) | `IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook` | **PORTÉE** |
| 1168 | `EntropyCannons` | `deathCrawler` (MoW Death Guard) | `IdunBattle.AI.Playbook.EntropyCannonsPlaybook` | **RIEN_A_PORTER** (attestée) |

L'appariement est **LU**, pas déduit : `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv`,
peuplé par `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders` (dict `+0x68`).

⚠ La même table porte `triggered 1200 → ...ControlEdictPlaybook` et `triggered 1168 →
...ArchContaminatorPlaybook`. Ce sont des `TriggeredAbilityType` à ordinal égal — **un autre enum**.
Qualifier avant de s'en servir.

---

## 1. `1200 SquigLaunchas` — le gate est plus strict que le ciblage

### 1.1 La classe, et sa base

`data/symbols/<build>/frida/classes.tsv` : base = `IdunBattle.AI.Playbook.NonComparablePlaybook`1`.
Le `.ctor`, lui, est étiqueté `ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`
par ghidra (`..ctor(this, 0x4b0 = 1200)`) — corps trivial **dédupliqué**, le piège #487-r1. Lire la
base dans `classes.tsv`, jamais dans le nom du `.ctor`.

`ghidra/functions.tsv`, par préfixe de classe : **trois** corps — `.ctor`, `.cctor`,
`EvaluateNonComparable`. **Pas de `ShouldEvaluate` propre.**

### 1.2 Le corps, terme à terme

`IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook$$EvaluateNonComparable`, lu verbatim :

```
bucket = new Bucket<UnitAction>(0, Nullable(<premier statique de la classe>))   # `.cctor` : Fix64(1)
foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
    crit = <SquigLaunchasAbility>$$FulfillsSummonCriteria(this.ability@+0x68)
    e    = new AbilityEntities(target: entities@+0x10, caster: caster, <tout le reste NUL>)
    if (!crit.<vtable +0x188 = ShouldTrigger>(e, 0x20 = GroupType.Ability_Attack))
        continue
    util = Fix64.op_Implicit( this.rng@+0x30.<IPseudoRNG slot 2 = Next>(1, 10) )
    bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities@+0x10, util))
return bucket
```

`IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook$$.cctor` :
`<statique> = FixMath.NET.Fix64.op_Implicit(1)` → `MIN_UTILITY = 1`.

Le champ `+0x30` de `BasePlaybook` **est** l'`IPseudoRNG` : c'est celui que
`IdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook$$ShouldEvaluate` passe au slot 5
(`NextBool`). `IPseudoRNG` slot **2** = `Next`/2 params, **LU** dans
`data/symbols/<build>/metadata/interface_slots.tsv`. Le `Il2CppClass*` de l'interface a été
identifié par ses trois autres consommateurs — `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`,
`IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$AddListener`,
`Idun.Source.AutomatedTesting.Factories.AutomaticTestingOnslaughtConfigFactory$$GetRandomGrandAlliance`.

`GroupType.Ability_Attack = 32` est lu dans `data/symbols/<build>/frida/enums.tsv`
(`IdunBattle.Streams.GroupType`). Il ne participe pas au verdict du prédicat (dispatch de stream).

### 1.3 Ce qui rend le port OBSERVABLE : deux seuils, un seul couple de prédicats

Les deux gates natifs utilisent les **mêmes** prédicats sur des seuils **différents** :

| gate | symbole | seuils |
|---|---|---|
| CIBLAGE (bit `TargetMatchesDynamicRule`) | `...SquigLaunchasAbility$$GetDynamicInvalidTargetReason` | `>= nrOfUnits (0x78) = 1` Ork **OU** `>= nrOfUnits_2 (0x79) = 2` alliés |
| SUMMON (ce playbook, et l'`ExecuteBehaviour`) | `...SquigLaunchasAbility$$FulfillsSummonCriteria` | `>= nrOfUnits_3 (0x81) = 2` Orks **OU** `>= nrOfUnits_4 (0x82) = 4` alliés |

Les valeurs `1 / 2 / 2 / 4` sont **lues au gameconfig** à l'exécution (`ability_var(..., is_constant=True)`),
jamais écrites en dur.

C'est le CIBLAGE qui filtre déjà `abilityTargets`. **Une cible peut donc être légale sans remplir le
critère de summon** : le natif ne propose alors pas 1200 sur elle, un port sans face DÉCISION la
proposait. C'est le régime séparant, et il est atteignable (§4).

`...SquigLaunchasAbility$$FulfillsSummonCriteria` =
`op_BitwiseOr( HasMinimumAdjacentOrks(Direct(0x81)), HasMinimumAdjacentFriendlyUnits(Direct(0x82)) )`,
avec (relus) :

```
HasMinimumAdjacentFriendlyUnits(n) =
    AmountIsEqualOrGreater(
        Friends( Owner@+0x148,
                 NonSteppableOrObjectUnits( AdjacentUnits(target@+0x178, unique: 1, 3) ) ),
        n )
HasMinimumAdjacentOrks(n) = idem + UnitsFromFaction(., 5 = UnitFaction.Orks, 3)
```

Le référent de `Friends` est l'**OWNER** (le caster MoW) : « friendly » = de MON camp, pas du camp
de la cible. Lecture confirmée live par la face COMBAT (case-mow §5).

### 1.4 L'utilité est un TIRAGE — et le seuil ne filtre RIEN

`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` (relu) : `range = max - min`, retour
`min + (g % range)` → **borne haute EXCLUE** → `Next(1, 10)` ∈ **[1, 9]**, neuf valeurs.

Le gate du bucket est un `>=` :
`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` appelle un
prédicat de seuil dont le retour est `Fix64.op_GreaterThanOrEqual(action.Utility, minUtility)`
(symbole étiqueté `UnityEngine.Timeline.DiscreteTime$$op_GreaterThanOrEqual` — corps dédupliqué).
Avec `MIN_UTILITY = 1`, **tout tirage franchit le seuil**.

Contraste **mesuré** avec `Hailstrike` (#967-r3), où le tirage décide de l'EXISTENCE de l'action et
oblige à porter une borne HAUTE : ici il n'existe aucun tel régime, la borne BASSE suffit.

Ce que le tirage décide en revanche, c'est **quelle** cible — il est refait à chaque itération, donc
c'est un bruit **indépendant** par cible. `AddAction` ne remplace que sur `>` **strict**. D'où :

* le port pose le terme à sa borne BASSE **lue** (`RNG_TERM = 1.0`) — constante sur les N cibles,
  donc **identité sur l'argmax**, donc keep-first sur l'ordre d'énumération natif ; et `>= MIN_UTILITY`,
  ce que `0` ne ferait pas ;
* la cible **effectivement** choisie par le natif est **indéterminable** dans un moteur déterministe
  (le port ne consomme aucun tirage de l'IA, l'état du Mersenne Twister diverge dès le premier).
  Nommée, pas fittée → résidu **#970-r6**.

Restent fidèles et déterministes : **quelles cibles sont proposables** (le gate) et **à quel tier** —
`PRIORITY = 1000` = `AbilityPriority.First` (déjà dans `NATIVE_PRIORITY`, mesure #170), donc 1200
**prime** sur `SquigMine` (1201, tier 0) du même porteur dès qu'une cible passe le gate.

### 1.5 Le port

`scripts/python/engine/playbook/noncomparable/squig_launchas.py`, inscrit dans
`engine.playbook.noncomparable.PLAYBOOKS`.

L'artefact natif du gate est un **arbre DSL**, et il est déjà porté comme tel par la face COMBAT
(`engine.runner.abilities.orks.squig_launchas_fulfills_summon_criteria`). Ce module ne le ré-écrit
pas comme arbre : il en ré-exprime la **sémantique** sur le substrat `NCContext`, comme
`silent_death` pour son `Enemies(AdjacentUnits(...))` et `duty_eternal` pour son
`GetSurroundingUnits`. Raison : la route DÉCISION n'a pas d'exécuteur DSL sur `NCContext` (pas de
`State`) — importer la face COMBAT ferait dépendre un playbook d'un `State` qui n'existe pas là.

Substrat, canal par canal :

| nœud natif | canal `NCContext` |
|---|---|
| `AdjacentUnits(<tuile de la cible>)` | `bq.is_adjacent` (voisinage natif stocké + porte `|dElev| < 2`) |
| `Friends(Owner, .)` | `ctx.fpos` — positions alliées vivantes, **self exclu** |
| `NonSteppableOrObjectUnits(.)` | `_UT.entity_trait_names` (traits d'ENTITÉ, foyer partagé) |
| `UnitsFromFaction(., 5)` | `FactionId` gameconfig ; le **nom** du membre `UnitFaction.Orks` EST cette chaîne |
| énumération des cibles | `_targets.eligible_units` (`abilityTargets(uid, 1200).fromHere`, `kind == "unit"`), ordre natif |

Écart nommé : `ctx.fpos` exclut le caster — **inerte** ici, le porteur est une MoW sans
`PositionComponent`. Idem pour « `fromHere` n'énumère que depuis l'origine » : `ctx.reach_nc` est vide.

Canal `fpos` muet → aucun allié vu → le critère ne peut pas être rempli → l'ability n'est pas
proposée. Dégradation **conservatrice**, dans le même sens que le gate natif (qui REFUSE).

⚠ Le port ne lit **pas** `.traits` en brut : il passe par le foyer `entity_trait_names`. Il n'est donc
pas un site du patron de `probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py` (vérifié :
son inventaire ne compte aucun site sous `playbook/noncomparable/`).

---

## 2. `1168 EntropyCannons` — `RIEN_A_PORTER`, et c'est une mesure POSITIVE

`IdunBattle.AI.Playbook.EntropyCannonsPlaybook` porte **DEUX** corps — `.ctor` et
`MakeDamagePredictions` — et son `MakeDamagePredictions` est la **forme CANONIQUE**, celle que le
chemin générique du port emprunte déjà. Il n'y a donc rien de **propre** à porter.

### 2.1 Le corps, relu verbatim

```
damage  = ability.GetDamage(abilityState)      // corps dédup `VigilanceEternalAbility$$GetDamage`
                                               //   = AActiveAbility$$MinMaxDamage(state, isPrediction: 0)
hits    = AActiveAbility$$GetHits()
profile = AActiveAbility$$GetDamageProfile()
sel     = this.dsl@+0x18 ->+0x90 ->+0x60       // DSLSelectors.Target
return ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
           caster, casterPosition, target, sel, damage, hits, Nullable(profile), default, 0)
```

`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDamage` relu :
`return AActiveAbility$$MinMaxDamage(this, state, 0)` — la forme **(b)**. Et `1168` figure **déjà**
dans `engine/entities/abilities/active_ability.py::_PREDICTION_MINMAX_RANDOM_READ` (vérifié), la
famille (b) qui coïncide avec le défaut.

### 2.2 Quatre sources indépendantes — l'absence d'un symbole ne prouve rien (dédup IL2CPP)

1. **Empreinte structurelle** (`data/symbols/<build>/fingerprints/functions.tsv`) —
   `EntropyCannonsPlaybook$$MakeDamagePredictions` partage `taille=381`, `n_ins=82`,
   **`h_body=22f58035eafb`**, `h_mnem=67e23d86827b`, `h_calls=100f3df5c794` avec **exactement deux**
   autres fonctions du build : `...Loki.LashOfTormentPlaybook$$MakeDamagePredictions` — **déjà
   attestée `RIEN_A_PORTER`** au ledger (#974/#979) — et `...Loki.MightFromBelowPlaybook$$MakeDamagePredictions`,
   dont la case-doc du port écrit « la forme CANONIQUE, mot pour mot […] Aucune entrée n'est
   surchargée […] Rien à poser de ce côté ». Corps identiques, **même `h_calls`** : le `GetDamage`
   appelé est le même corps dédupliqué.
   **TÉMOIN QUE L'EMPREINTE DISCRIMINE** : `...Loki.ArmoriumCherubPlaybook$$MakeDamagePredictions` a
   la **même** taille, le **même** `n_ins` et le **même** `h_mnem` — mais `h_body=5aa6395d0578` et
   `h_calls=9758bd6bbf0b`, tous deux **différents**. Un squelette identique ne suffit donc pas à
   faire passer un corps pour un autre : ce sont `h_body` et `h_calls` qui tranchent, et ils
   concordent pour 1168.
2. **Recensement de classe** (`ghidra/functions.tsv`, par préfixe de classe) —
   `EntropyCannonsPlaybook` : **2** corps (`.ctor`, `MakeDamagePredictions`). La mesure SAIT voir une
   surcharge quand il y en a une : `...Loki.MightFromBelowPlaybook` en porte **3**
   (+ `CalculateCasterPositionUtility`, qui EST son seul delta et qui, elle, est portée) et
   `...Loki.ArmoriumCherubPlaybook` en porte **6** (`CalculateCustomUtility`, `CanKillTarget`,
   `GetNumEnemiesInNormalAttackRange`, `ShouldExecute`).
3. **`frida/classes.tsv`**, source distincte du dump — parent =
   `IdunBattle.AI.Playbook.ComparablePlaybook`1`, taille 112, **le même** que `LashOfTorment` et
   `MightFromBelow`. Aucune classe intermédiaire ne s'interpose.
4. **`mcp__ghidra__search_symbols_by_name`** sur `EntropyCannonsPlaybook` → **2** symboles, les mêmes
   deux.

### 2.3 Pas de `.cctor` — et le seuil statique ne la concerne pas

`EntropyCannonsPlaybook` n'a **aucun** `.cctor`, donc aucun seuil propre. Elle n'a pas non plus de
`ShouldExecute` : elle **n'est pas** l'une des douze classes de
`engine/playbook/static_threshold_gate.py` (dont le gate est précisément un `<X>Playbook$$ShouldExecute`
qui lit le premier static de sa classe). Son absence des deux tuples `DERIVED_CCTOR_IDS` /
`NO_DERIVED_CCTOR_IDS` est donc **correcte**, et vérifiée.

### 2.4 Verdict

`RIEN_A_PORTER`, inscrit au ledger `scripts/ratchets-951r2-couverture-attestee.json` sous
`active-decision:EntropyCannons`, ancré sur
`scripts/python/tests/engine/test_1021_face_decision_au_registre_offline.py`. La ligne `1168` de
`probe_1021.DETTE` est **retirée dans le même commit** : c'est le retrait qui la fait tomber sous le
CRAN A, donc ce qui la protège désormais — si l'attestation périme (build changé, cliquet disparu),
l'item **rougit** au lieu d'être couvert par une vieille ligne de dette.

---

## 3. La confrontation LIVE de 1200 — et le faux oracle qu'il a fallu écarter

`scripts/python/probe_970r3_squig_launchas_live.py` (garde :
`tests/engine/playbook/test_970r3_squig_launchas_decision_live.py`). **Un** runner, **un** build,
et l'on passe du régime séparant au régime passant en **déplaçant** un Ork au contact de la cible
— la tuile est choisie dans `ring1(cible) ∩ atteignables ∩ libres`, jamais écrite en dur, et
l'arrivée est **vérifiée**.

Mesure (board `MC1_67`, seed 777, `orksRukkatrukk` MoW, cible `necroWarden`) :

| régime | Orks adjacents | cible dans `fromHere` | NATIF | PORT |
|---|---:|---:|---|---:|
| A — **séparant** | 1 | **1** (donc LÉGALE) | `bucket: empty`, **0** action | **0** candidat |
| B | 2 | 1 | **1** action, 8 tirages `[1, 3, 3, 4, 5, 6, 8, 9]` | **1** candidat |

`playbookClass` échoué par le capteur = `SquigLaunchasPlaybook` dans les deux régimes.

Les **deux bornes** sont atteintes (1 et 9) et `10` n'apparaît jamais : `Next(1, 10)` = `[1, 9]`,
borne haute **exclue** — la lecture de `IntBasedMersenneTwister$$NextInternal` est confirmée
**live**. Et 7 valeurs distinctes sur 8 établissent que c'est bien un **tirage**, pas une
constante : c'est ce qui justifie #970-r6 (le port ne fitte pas la valeur).

### ⚠ `ncEvaluate` est structurellement AVEUGLE aux MACHINES OF WAR

C'est le point le plus important de cette passe, et il a failli produire une validation fausse.

Le hook d'`ncEvaluate` (`frida/hooks/features/ai-step/rpc-predict.ts`) cherche le caster par
`forEachEntity(state, ...)` filtré sur `ty === EntityType.Unit`. Une MoW est une
`EntityType.Machine` : il rend donc `{ok: false, error: "unit 77 not found"}` — **pour 1200 comme
pour `1201 SquigMine`**, dont le playbook NonComparable est pourtant porté *et* validé.

Une première passe du probe lisait `positions` d'une réponse `ok: false` et en concluait
« 0 action ». L'accord obtenu en régime séparant était alors **dégénéré** : il ne prouvait rien.
Deux crans ferment la porte — `_oracle_natif` **lève** sur `ok: false` (un échec rendu n'est pas
une mesure), et le verdict exige un **témoin non nul** (au moins une action émise quelque part).

Le capteur juste est **`ncPlaybookPredict(via="evaluate")`** (`rpc-nc-predict.ts`), dont le hook
accepte `EntityType.Unit` **ou** `EntityType.Machine`.

**Rien à reinjecter** : le capteur correct existe déjà dans le bundle. Étendre `ncEvaluate` aux
`EntityType.Machine` serait cohérent mais n'est **pas nécessaire** ici — résidu non ouvert, la
limitation est nommée dans les deux probes.

## 4. Ce qui a été rejoué

* `probe_1021_face_decision_au_registre.py` — `rc 0` (CRAN A/B/C).
* `probe_547_ledger_sans_verdict_non_vert.py` — `rc 0`.
* `tests/engine/runner/test_ctx_traits_substrat_ventilation_offline.py` — 14 passed.
* `tests/engine/test_1021_face_decision_au_registre_offline.py`.
* `tests/engine/playbook/test_970r3_squig_launchas_decision_offline.py` — 13 passed.
* `tests/engine/playbook/test_970r3_squig_launchas_decision_live.py` — 8 passed.
* `probe_462_..._substrat_traits.py --step inventaire` — 76 sites, **aucun** sous
  `playbook/noncomparable/` (le port passe par le foyer `entity_trait_names`).

### Les gardes ont été MESURÉES, pas supposées

**Contre-épreuve du ledger** (3 mutations, process séparés) : retirer l'attestation d'EntropyCannons,
la périmer (build faux), ou sortir 1200 de `PLAYBOOKS` — les trois font passer `probe_1021` de
`rc 0` à `rc 1`, et c'est **le CRAN A** qui tombe à chaque fois (jamais B ni C).

**Contre-épreuve du port** (6 mutations) : gate neutralisé, filtre de trait retiré, faction ignorée,
borne du tirage à 0, ordre des cibles trié, adjacence élargie → **0 mutation muette**, chacune
identifiant l'assertion qui tombe.

⚠ **Deux fautes trouvées par la mesure elle-même**, toutes deux réparées :

1. **Le montage était CREUX.** `orksBoy` / `ultraIntercessor` ne sont pas des `visualId` du
   gameconfig → `_unit_cfg` vide → `FactionId is None` → tous les régimes « N Orks » étaient en
   fait « N non-Orks ». La décomposition par étage a montré que `_adjacent_friends` rendait bien
   2 unités : c'était le **montage**, pas le port. Le probe **assertionne** désormais que ses trois
   `visualId` résolvent.
2. **La garde était MUETTE sur l'étage géométrique.** Tant que le montage ne portait que des
   voisins immédiats, neutraliser `bq.is_adjacent` ne faisait rougir **aucune** assertion. Deux
   régimes à distance ≥ 2 (mêmes unités, autre distance) la rendent mordante.

## 5. Ce qui n'est PAS couvert

* **Quelle cible** le natif retient quand plusieurs passent le gate : indéterminable (tirage par
  cible). Résidu **#970-r6**.
* La **décision finale de l'IA** : `Evaluate/3` donne l'utilité et la cible, pas ce que le tactic
  retient après les tiers de priorité et son propre `Bucket`. L'accord établi ici est nécessaire,
  pas suffisant.
* `1168` n'a **pas** été re-confronté live par cette tranche : sa confrontation vit dans
  `test_977_faces_decision_kit_live.py` (`aiPlaybookPredict`, 4 cibles, bit-exact), non modifié.

## 6. Résidus

* **#970-r6** — la cible effectivement choisie par le natif est un tirage `Next(1, 10)` refait par
  cible, donc indéterminable hors mirror du flux `IPseudoRNG` de l'IA. Le port rend le gate et le
  tier ; il ne rend pas *quelle* cible. Même famille que #967-r3 (`Hailstrike`), **sans** son volet
  SEUIL — ici le seuil est structurellement non filtrant (borne basse du tirage = `MIN_UTILITY`),
  ce qui est **mesuré live** (les 8 tirages sont tous ≥ 1).
