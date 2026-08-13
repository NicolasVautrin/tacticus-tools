# #957 — six faces DÉCISION du 2ᵉ lot `IdunBattle.AI.Playbook.Loki.*`

Les six kits étaient déclarés COMPLETS sur leur face COMBAT. Le lot a mesuré que **trois de ces six
faces DÉCISION existaient déjà** — ce qui n'était pas su au dispatch — et que **l'une des trois
était FAUSSE**.

## 0. Ce que le lot a rendu, en une table

| ability | id | classe native | base LUE (`frida/classes.tsv`) | verdict |
|---|---|---|---|---|
| `FragBomb` | 1017 | `…Loki.FragBombPlaybook` | `ComparablePlaybook\`1` | **volet SPLASH porté** (`get_aoe_targets` + coups), face principale déjà là |
| `Foehammer` | 1097 | `…Loki.FoehammerPlaybook` | `NonComparablePlaybook\`1` | **portée + CONFRONTÉE** (MISS → MATCH, ability ET position) |
| `FearOfTheUnseen` | 1115 | `…Loki.FearOfTheUnseenPlaybook` | `NonComparablePlaybook\`1` | **portée** — NON CONFRONTÉE (§6, résidu `#957-r2`) |
| `ExemplarOfHate` | 1140 | `…Loki.ExemplarOfHatePlaybook` | `NonComparablePlaybook\`1` | **portée + CONFRONTÉE** (bascule de CIBLE, deux montages) |
| `CultDemagogue` | 1179 | `…Loki.CultDemagoguePlaybook` | `ComparablePlaybook\`1` | **DÉJÀ PORTÉE, et FAUSSE — corrigée** (§5) |
| `ExcruciatingFrequencies` | 1197 | `…Loki.ExcruciatingFrequenciesPlaybook` | `ComparablePlaybook\`1` | **DÉJÀ PORTÉE, confirmée FIDÈLE** (§7) |

Les six sont **reachable** : `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` les
liste toutes dans le dict `active` d'`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`.
Aucun code registered-but-dead.

## 1. Le patron ne se factorise pas — CONFIRMÉ, et le coût s'est déplacé

#945 avait mesuré « le patron ne se factorise PAS ». **Confirmé sur six items d'origines
différentes** : aucune ligne de logique n'est partagée entre les six, et le squelette
(`noncomparable/_base.py`) a servi tel quel pour les trois NonComparable — sans une modification.

Mais le coût dominant a CHANGÉ de nature. Sur ce lot, il n'est plus dans la lecture du décompilé
(les trois `EvaluateNonComparable` font 10, 6 et 25 lignes de pseudo-C) : il est dans le
**RECENSEMENT DE L'EXISTANT**. Trois des six faces étaient déjà portées, dans **trois modules
différents** (`playbook/bespoke.py`, `playbook/excruciating_frequencies.py`,
`playbook/prediction/abilities.py`) et par **trois routes différentes** (bespoke `EvaluateInternal`,
générateur bespoke tile-target, registre d'overrides d'entrées). Aucune n'est dans le registre
`noncomparable`, aucune n'est dans `playbook.base.REGISTRY` — donc `aid in PLAYBOOKS` et
`aid in REGISTRY` rendent `False` pour les six, et un dispatch qui s'y fierait re-porterait
trois abilities déjà là.

**Coût mesuré, item par item** :

| item | où était le coût |
|---|---|
| 1140 `ExemplarOfHate` | RE pure (10 lignes) + **deux qualifications d'enum** (`StatPart.CurrentPct`, pseudo-trait d'alliance) |
| 1115 `FearOfTheUnseen` | RE **de la STRUCTURE de retour** (`ValidTargets` : quel champ, `+0x10` ou `+0x18` ?) — le corps du playbook, lui, tient en 6 lignes |
| 1097 `Foehammer` | RE **jusqu'au query** : `AllDeadUnits` → `AllDeadUnitsSelector$$Select` → slot `0x8b` → `BattleQuery$$GetAllDeadUnits`, trois classes dont les `.ctor` sont DÉDUPLIQUÉS |
| 1179 `CultDemagogue` | **relecture d'un port existant** — la faute (§5) n'est visible qu'en relisant le call-site natif du sélecteur |
| 1197 `ExcruciatingFrequencies` | **confrontation** d'un port existant à un décompilé re-lu : 5 termes vérifiés, 0 écart |
| 1017 `FragBomb` | **recensement** (`_PLAYBOOK_PROFILE_OVERRIDE` le portait déjà, `get_aoe_targets` non) + port du 2ᵉ batch |

## 2. Recensement des méthodes : AU BLOC D'ADRESSES, jamais par grep

Le brief l'exigeait, et ça a payé. Trié par adresse, `ghidra/functions.tsv` montre les corps d'une
classe **CONTIGUS** ; ce qui n'y est pas l'est parce qu'il a été FONDU ailleurs.

    ExemplarOfHatePlaybook     18122ecf0..18122f160   EvaluateNonComparable · .cctor · .ctor
    FearOfTheUnseenPlaybook    181238fd0..1812391e0   EvaluateNonComparable · .cctor · .ctor
    FoehammerPlaybook          18123a570..18123ab20   EvaluateNonComparable · .cctor · .ctor
    CultDemagoguePlaybook      181225760..181225f90   EvaluateInternal      · .cctor · .ctor
    ExcruciatingFrequenciesPlaybook  18122e150..18122e3d0  MakeDamagePredictions · ShouldExecute · .ctor
    FragBombPlaybook           18123b990..18123bdf0   MakeDamagePredictions · .ctor

Le contre-exemple est dans le lot : **`FragBombPlaybook$$ShouldExecute` siège à `18121e9e0`**, au
milieu du bloc de `BasiliskBarragePlaybook` — corps FONDU, partagé par les deux classes. Un
recensement par bloc contigu l'aurait manqué ; un recensement par grep de nom l'attribue à
`FragBomb` sans dire qu'il est partagé. **Il faut les DEUX lectures**, et c'est ce que fait ce lot.

Aucun `CreateTrigger` / `CreateActiveCondition` / `CreateTargetSelector` fondu n'a été trouvé pour
les six.

## 3. `1140 ExemplarOfHate` — deux qualifications d'enum, deux silences évités

`IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))        # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        t = entities@+0x10
        if (HasTrait(t, 0xd = UnitTrait.Object)) continue
        u = Fix64(1) + Fix64.FromIntFraction(GetStat(t, 5 = Health, 1 = StatPart.CurrentPct), 100)
        if (!HasTrait(t, 0x3ec = UnitTrait.Infiltrate))  u += Fix64(2)
        if ( HasTrait(t, 0x7ea))                         u += Fix64(1)
        bucket.AddAction(GenerateAction(casterPosition, t, u))

**Piège 1 — `statPart = 1 = CurrentPct`, pas `Current`.** `1164 MindControl` a la MÊME forme
apparente (`GetStat(target, 5, …)`) et lit `Current` : là où 1164 classe par PV BRUTS, 1140 classe
par POURCENTAGE. Confondre les deux ne lève AUCUNE erreur et donne un ordre différent dès que deux
cibles ont des `maxHp` distincts — c'est la forme de faute que le CLAUDE.md décrit sur les enums,
transposée au `StatPart`.

**Piège 2 — `0x7ea` n'est PAS un trait gameconfig.** C'est le pseudo-trait de GRANDE-ALLIANCE
`Chaos` (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait`), posé par le BattleConfiguration. Un
`HasTrait` naïf sur la liste `traits` rendrait TOUJOURS faux et la branche `+1` serait MORTE. La
face COMBAT documentait déjà le piège (`runner/abilities/darkangels.CHAOS_FACTIONS`) — la face
DÉCISION le re-rencontre, et le port dérive du `GrandAllianceId` comme
`playbook/adjacent_unit_preference._has_trait`.

Utilité dans `[1.0, 4.0]`. **Le tri qui en résulte est le seul observable du playbook**, et c'est
exactement lui que le live a fait basculer (§8).

## 4. `1097 Foehammer` — le playbook ne compte PAS ce que son ability utilise

`…FoehammerPlaybook$$EvaluateNonComparable` évalue `DSLFormulas.Count(DSLSelectors.AllDeadUnits())`
sur un `AbilityEntities` **MEMSET à zéro** (le décompilé fait le `memset(.., 0, 0x128)` juste avant
la copie) : l'utilité ne dépend NI de la cible NI de la position — elle est **CONSTANTE sur tout le
bucket**.

Résolution du sélecteur, jusqu'au query :

    DSLSelectors$$AllDeadUnits()  ->  AllDeadUnitsSelector
    AllDeadUnitsSelector$$Select  ->  IBattleQuery slot 0x8b (= 139) GetAllDeadUnits(playerEntityId: null)
    BattleQuery$$GetAllDeadUnits  ->  filtre par propriétaire SEULEMENT si le Nullable a une valeur

⇒ **toutes les unités mortes du plateau, les deux camps confondus, sans filtre de trait.**

**Le QUIRK** : `…FoehammerAbility$$ExecuteBehaviour` construit son bonus de dégât avec
`UnitsWithTrait(AllDeadOrResurrectedUnits(), 0x10 = Hero, 0)` — les HÉROS morts ou ressuscités. Les
deux corps sont dans le même binaire à quelques fonctions d'écart et n'interrogent pas le même
ensemble. Même forme de quirk qu'`AdaptiveStrategy` (#945 §2) et `MassDriverAccelerator` (#27-r1).
Observable : une bataille où seuls des SUMMONS sont tombés fait monter l'utilité de DÉCISION de 1097
alors que son dégât, lui, n'a pas bougé.

⚠ **Trois classes, un seul `.ctor`.** `AllDeadUnitsSelector`, `AllDeadOrResurrectedUnitsSelector` et
`AllDefeatedUnitsSelector` partagent le corps que Ghidra nomme `AllDefeatedUnitsSelector$$.ctor` :
le nom du ctor ne dit PAS la classe. Ce sont leurs `Select` (corps propres, slots `0x8b` / `0x8b`+
boucle / `0x8c`) qui les séparent.

## 5. `1179 CultDemagogue` — déjà portée, et l'ANCRE était fausse

Le port (`playbook/bespoke.CultDemagoguePlaybook`) écrivait :

> `PossibleTilesForDecoys` = `CanAddUnit(SurroundingTiles(caster, range=2))` → tuiles LIBRES
> placeables ≤2 hex du **CASTER**. […] Terme 1 = CONSTANT sur les cibles → n'affecte PAS l'argmax.

Le call-site natif dit autre chose :

    …CultDemagogueAbility$$PossibleTilesForDecoys =
        CanAddUnit( SurroundingTiles(<DSLSelectors+0x60>, includeCenter: 0,
                                     range = GetNumberConstant(0x44), onlyMovable: 0,
                                     includeNonWalkable: 0),
                    isSteppable: <DSLTriggers+0x40> )

`<DSLSelectors+0x60>` est **`Target`**. La carte de champs est celle que le reste du port cite
partout (`+0x30 = Owner`, `+0x48 = Caster`, `+0x60 = Target` — `HadesAutocannonsAbility`,
`MassDriverAcceleratorAbility`, et `FragBombAbility$$GetAdjacentTargets`, qui SOUSTRAIT `+0x48` pour
retirer le caster). **La face COMBAT du même jeu le disait déjà** : `genestealer.SpawnDecoys` fait
`_surrounding_free_tiles(state, _pos_of(state, target_id), radius)` et sa docstring écrit « tuiles
libres aléatoires ≤`range` hex de la **CIBLE** ».

⇒ Le terme dominant de l'utilité (`min(|tuiles libres|, nrOfSummons) × 20`) **n'est pas constant :
il DÉPARTAGE l'argmax**, et il le domine (le second terme dépasse rarement 1 ou 2). Le port le
calculait une fois, hors boucle, depuis l'origine du caster.

Deux crans posés dans la foulée :

* **le caster est ajouté EXPLICITEMENT à l'occupation** — `ctx.fpos` exclut le mover, et `center`
  ne vaut plus l'origine ;
* **l'ordre des cibles est PRÉSERVÉ** : `tgt_ids` était un `set`, or `Bucket$$AddAction` ne remplace
  que sur amélioration STRICTE — à utilité égale, c'est la PREMIÈRE cible du sélecteur qui gagne.
  Avec un `set`, l'argmax d'un tie dépendait du hachage.

⚠ **Les deux `AbilityEntities` du corps ne sont pas le même**, et c'est LU : `PossibleTilesForDecoys`
est évalué sur l'`AbilityEntities` COURANTE du `foreach`, tandis que les deux `SelectUniqueUnits`
reçoivent un `AbilityEntities` NEUF dont SEUL `+0x10 = target` est renseigné. Aucun des trois
sélecteurs ne lit `caster` (`+0x08`) : les trois ancrent sur `+0x60`, donc le buffer nul suffit.

## 6. `1115 FearOfTheUnseen` — un VETO sur l'UNION, et NON CONFRONTÉ

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    vt = BasePlaybook.GetAllNormalAttackTargets(caster)              # ValidTargets
    if (vt != null && vt.<+0x10> != null && vt.<+0x10>.<+0x18> == 0)
        bucket.AddAction(GenerateAction(casterPosition, caster, Fix64.op_Implicit(10)))

Il n'y a **AUCUN appel à `GetEligibleTargetsSelectable`** : la cible est le CASTER (2ᵉ argument de
`GenerateAction`), l'utilité est la constante `10`, et tout le discriminant est dans la condition.

`GetAllNormalAttackTargets(unit)` = `IBattleQuery` slot `0x45` =
`GetAllValidTargetsFromAllPossibleMovementTiles(unit, GetNormalAttackType(unit), false)` — le MÊME
appel que `ExemplarOfTheMontkaPlaybook$$HasNormalAttackTarget`. Les DEUX champs de `ValidTargets`
(taille `0x20`) sont lus dans `…ValidTargets$$Merge` / `…$$GetTargetsByPosition` :

    +0x10 = OrderedSet<IEntity>                        <- l'UNION de toutes les cibles
    +0x18 = Dictionary<UnitPosition, OrderedSet<…>>    <- la carte position -> cibles

Le playbook lit `+0x10` puis SON `Count` : la condition est « l'UNION, sur TOUTES les tuiles de
move, est VIDE ». Le mirror offline est donc `abilityTargets(uid, <naId>).targets`, **jamais**
`fromHere` — qui rendrait le veto beaucoup trop permissif.

**NON CONFRONTÉE, cause MESURÉE.** Trois montages joués (§8) ; dans aucun le natif ne propose 1115.
Le porteur unique `tyranDeathleaper` porte `TeleportStrike_TeleportingIn` : il se **pose au contact**
au déploiement, et c'est le seul tour où l'union de ses cibles d'attaque normale est vide — or 1115
y est en `[cd1]`. Dès le tour 2, l'union est non vide. `--unit-stat "tyranDeathleaper:Movement=0"`
ne mord pas sur cette apparition (le deep-strike n'est pas un move). Résidu `#957-r2`, avec les
deux pistes de montage.

## 7. `1197 ExcruciatingFrequencies` — déjà portée, confrontée au décompilé, FIDÈLE

`…ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` (un SEUL appel à
`GenerateMultiHitAttackPredictions`, dont le sélecteur porte tout) :

| terme natif | port (`playbook/excruciating_frequencies.py`) | verdict |
|---|---|---|
| `GetAttackTargets()` = `Enemies(Caster@+0x48, Units(GetAffectedTiles(), unique: 1, sel: 3), 3)` | ennemis sur les tuiles de la ligne | ✔ |
| `GetAffectedTiles()` = `SortReverse(TilesBehindInLine(CasterTile@+0x50, Direction@+0x78, settings, Direct(GetNumberConstant(0x17))))` | `_line_tiles` → `battle_query.get_tiles_behind` | ✔ |
| `damage` = `<X>Ability$$GetDamage` (corps dédup, `MinMaxDamage`) | chemin générique `ab.get_damage()` | ✔ |
| `Nullable(GetDamageProfile())` NON vide | profil `Blast` de la config, aucun override | ✔ |
| `ShouldExecute` = `attackHealUtility > <1er static>` | `STATIC_UTILITY_THRESHOLD = 10.0` | ✔ |

Un seul écart : `hits` = `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f)` **LITTÉRAL**, là où
le chemin générique passe par `GetDefaultAttackHits(nrOfHits + ExtraHits)`. Inerte tant que
`ExtraHits = 0`. Résidu `#957-r3` — **RÉSOLU et CONFRONTÉ LIVE (2026-08-13)**.

### `#957-r3` — le régime discriminant EXISTE, et le levier proposé n'était pas le bon

Le résidu proposait « `--unit-stat` sur la stat 17 ». **Faux** : l'entrée BC d'une unité porte
**38** champs et **aucun** ne s'appelle `ExtraHits` (`probe_957r3_excruciating_hits.py
--montrer-bc`). `ExtraHits` est une stat de BATAILLE, à 0 par défaut, et le build `rnca9r7q6c` n'a
que **deux** producteurs :

| producteur | signe | voie d'attribution | atteint le caster de 1197 ? |
|---|---|---|---|
| `IdunBattle.Entities.Effects.Loki.Swarm_HitReductionEffect` (1021) | **négatif** (`-min(nrOfMembers - 1, membres morts)`) | trait `Swarm` | **OUI**, par montage |
| `DoomSiren_ExtraHit` (1431, `AddStaticStatModifierEffect`) | +1, permanent | branche OVERKILL de `1199` | non (`emperKakophonist` porte 1199, pas 1197) |

Le premier est atteignable parce que ses **trois** entrées sont des champs BC — `Traits`,
`NumberOfMembers` et `RemainingHealth` (qui fait les membres morts) — donc `--unit-stat` sur
chacune. Montage mesuré :

```
--unit-stat emperNoiseMarine:NumberOfMembers=5
--unit-stat emperNoiseMarine:Traits=[...,"Swarm"]
--unit-stat emperNoiseMarine:RemainingHealth=800     (Health = 8533 -> 4 membres morts)
    statModSources : extraHits = -4
    litteral  = nrOfHits                              = 1
    generique = GetDefaultAttackHits(1, -4, 0, False) = max(1 - 4, 0) = 0
    aiPlaybookPredict -> appliedHits = 1 sur 4 evenements
```

⇒ **le natif prédit le LITTÉRAL** : l'override est CONFIRMÉ live, dans un régime où les deux
candidats sont séparés de façon maximale (1 contre 0).

⚠ Deux pièges de montage, tous deux mesurés : **`--hp-player` ne marche pas** (il aligne `Health`
sur `RemainingHealth`, donc 0 membre mort, donc `ExtraHits = 0` — accord dégénéré) ; et
**`aiPlaybookPredict`/`statModSources` veulent le `squadId`** d'`observeBattle`, pas son
`entityId` (sinon `unit 82 not found (unit/machine)`) — même piège que celui déjà nommé sur
`combatSnapshot.units[].entityId` par #982-r5. S'y ajoute la **géométrie** : 1197 est une ability
de LIGNE, et au placement de spawn le caster n'est aligné avec personne — le playbook rend alors
zéro événement, ce qui se lirait à tort comme « pas de prédiction ». Le probe aligne
explicitement (`--place emperNoiseMarine:6,6`).

Garde : `tests/engine/runner/test_957r3_excruciating_hits_live.py` (3 tests, dont un **témoin de
régime armé joué AVANT le verdict**). Vue ROUGE par mutation (l'override rend le générique) :
`le port surcharge None coups la ou le natif en applique [1]` côté live, et
`hits_override = None, attendu le litteral de config 1` côté offline.

## 8. `1017 FragBomb` — le volet SPLASH manquait

`…FragBombPlaybook$$MakeDamagePredictions` émet **deux** batchs, forme identique à
`MassDriverAcceleratorPlaybook` : la cible principale (sélecteur `Target`, `GetHits`), puis, pour
chaque entité de `…FragBombAbility$$GetAdjacentTargets`, un batch `Entity(e)` avec le **MÊME
`damage`** (évalué une fois, hors boucle) et `GetHits2`.

Deux écarts avec 1222, LUS :

* le SET est **`AdjacentUnits` NU moins le caster** — aucun wrapper `Enemies` (contraste
  `MassDriverAccelerator`, qui en a un) ⇒ **friendly-fire**, les alliés adjacents à la tuile ciblée
  sont prédits et leur event est `friendly` (utilité NÉGÉE). Même artefact que la face COMBAT, où le
  friendly-fire est mesuré live (`astraCreed` adjacent encaisse 3 coups) ;
* `param_8` (le `Nullable<DamageProfile>`) est **0 sur les DEUX batchs** — donc pas de
  `profile_override` propre au splash ; l'entrée `_PLAYBOOK_PROFILE_OVERRIDE[FragBomb] = "None"`
  (#168, validée live) couvre les deux.

Ce qui reste ouvert et n'est PAS de ce lot : le **domaine de ciblage TUILE** de 1017 côté générateur
Comparable (le port énumère des UNITÉS), déjà nommé par `#419-r1-tr14-r5-r2-r1-r1-r1-r1` — c'est lui
qui bloque aussi le port de son `ShouldExecute`.

## 9. Validation

**Oracle = un TOUR D'IA OBSERVÉ** (`engine_validate.py`), jamais `aiPredict`. Contre-épreuve : le
MÊME montage rejoué depuis un **arbre témoin détaché sur `origin/master`** portant le SEUL correctif
`scene.py` (§10), c'est-à-dire le port de ce lot DÉSARMÉ.

| montage (board MC1_67) | avec #957 | sans #957 |
|---|---|---|
| A — `darkaAsmodai,spaceRockfist,tyranDeathleaper` vs `spaceHound,blackAbaddon,adeptCanoness`, seed 777, 24 pas | ability **22/24 (91 %)**, position **18/18 (100 %)**, sur-place **6/6 (100 %)** | 15/19 (78 %), 15/17 (88 %), 3/5 (60 %) |
| B — mêmes rosters `--place`és, `tyranDeathleaper@(0,0)` isolé, seed 2468 | ability **15/15 (100 %)**, sur-place **6/6** | (non rejoué : A suffit à la contre-épreuve) |
| C — B + `--unit-stat "tyranDeathleaper:Movement=0"` | ability **9/9 (100 %)** | idem |

Les casts qui basculent, nommément :

* **`u83` [darkaAsmodai], `ab=1140`** : natif `tgt=79` (`blackAbaddon`, Chaos NON-Infiltrate,
  utilité 5). Sans la tranche le port visait `tgt=77` (`spaceHound`, **Infiltrate**, utilité 2)
  **et bougeait** — deux MISS ; avec, MATCH sur la cible ET sur la position. Le montage B rejoue le
  discriminant à deux cibles (`adeptCanoness` 4 vs `spaceHound` 2) : MATCH.
* **`u85` [spaceRockfist], `ab=1097`** : natif `tgt=81`. Sans, le port proposait `ab=69` (attaque
  normale) **et bougeait** — deux MISS ; avec, MATCH sur les deux.

**Corroboration indépendante du dispatch NonComparable** : `decisionView.attackPlans` rend
`[0-0]` pour 1140 comme pour 1097 dans les trois montages — le natif ne prédit AUCUN dégât pour ces
deux abilities, ce qui confirme au live la lecture « pas de `Make*Predictions` » faite au décompilé.

**Offline** : `tests/engine/test_957_decision_faces_offline.py` — 30 tests, 9 étages.
Contre-épreuve de mutation : **23 mutants du code de production, 23 mordent** (filtre `Object`
retiré, PV bruts au lieu du pourcentage, ligne obs absente → 0 %, branche `Infiltrate` inversée,
branche `Chaos` retirée, grande-alliance non dérivée, argmax non strict, veto lu sur `fromHere`,
NON-MESURE traitée comme veto, utilité 10 → 1, comptage filtré sur les héros, seuil abaissé, terme 1
ancré sur le caster, caster absent de l'occupation, ordre des cibles perdu, splash filtré ennemi,
classe de prédiction retirée, coups du splash non surchargés, les trois retirées de
`_NONCOMPARABLE_ABILITIES`, chacune des trois retirée du registre, `scene` revenu au `self.traits`).

Deux mutants étaient MUETS au premier passage (`argmax non strict`, `terme 1 ancré sur le caster`) :
les deux témoins étaient DÉGÉNÉRÉS — trois utilités distinctes dans le premier cas, plafond
`nrOfSummons` atteint des deux côtés dans le second. Les deux tests portent désormais leur propre
assertion de non-dégénérescence.

## 10. Un rouge de `master` révélé, et réparé

`Scene._enmity_adjacent` (`playbook/scene.py`) appelait `self.traits(oid)` — méthode qui n'existe
QUE sur `_SceneEffectTargetWorld`, pas sur `Scene`. Le corps levait donc `AttributeError` **dès
qu'une unité vivante était hex-adjacente au porteur**, et il est sur le chemin INCONDITIONNEL de
`make_normal_attack_predictions`. Le rouge est latent parce que la boucle sort AVANT sur un board où
personne n'est au contact — c'est-à-dire au premier tour de la plupart des montages.

Introduit par `f296bfa6` (#947 + #948) ; `scene.py` était identique à `origin/master` au moment de
la mesure. Il a bloqué la première passe de validation de ce lot au pas 5. Corrigé par le canal
correct (`ctx_by_id[<uid>].traits`, déjà publié en NOMS), avec un cliquet exécutable (étage 8 du
fichier de test).

## 11. Ce qui n'est PAS couvert

* la confrontation native de `1115` (résidu `#957-r2`) — cause mesurée au §6 ;
* les MoW dans le comptage de morts de `1097` (`observeBattle.units` ne les porte pas) — `#957-r1` ;
* ~~le `hits` littéral de `1197`~~ — `#957-r3` **RÉSOLU** (§7) ; reste hors couverture : le
  producteur **POSITIF** d'`ExtraHits` (`DoomSiren_ExtraHit`, +1 par overkill), qui exigerait de
  greffer 1197 sur `emperKakophonist` **et** de lui faire jouer un overkill — le montage `Swarm`
  couvre le signe négatif, pas le positif ;
* le splash de `1017` et le fix d'ancre de `1179` **NON CONFRONTÉS LIVE** — `#957-r4`. Les deux
  portent leur cliquet offline avec mutation, mais aucun montage n'a été joué : `astraBullgryn` et
  `genesPrimus` n'étaient dans aucun des trois runners ;
* le domaine de ciblage TUILE de `1017`/`1026` côté générateur Comparable — résidu PRÉEXISTANT
  `#419-r1-tr14-r5-r2-r1-r1-r1-r1`, non rouvert ici ;
* le tirage aléatoire de `GetUseProbability` (écart assumé du moteur déterministe) — aucune des six
  ne le surcharge, donc sans effet sur ce lot.
