# `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3` — `barbed_ovipositor` : la dernière recopie d'`IsObjectOrSteppable`, et ce qu'elle cachait vraiment

**Livré le 2026-08-05**, build `rnca9r7q6c`.
Probe : `scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py`
(`--step {re,substrat,guard,offline,live}`).
Gardes : `tests/engine/runner/test_barbed_ovipositor_object_or_steppable_offline.py` (30) et
`tests/engine/runner/test_barbed_ovipositor_live.py::test_barbed_ovipositor_corpse_substrate_live`.

## 1. La prémisse du backlog était à moitié fausse — et c'est la moitié qui décidait

La fiche annonçait : « le trigger est `On(UnitDeath)`, donc la cible est un **CADAVRE**, et c'est
exactement le cas où les deux substrats de traits divergent ». La conclusion attendue était donc
« la migration peut changer un verdict sur le chemin nominal, elle exige ses propres bras live ».

**Mesuré, c'est l'inverse qui est vrai sur ce chemin.** Une entité qui meurt *pendant* le run garde
son `StatsComponent` : c'est celle qui était **déjà morte au chargement** qui n'en a pas. La
divergence n'est donc pas indexée par « la victime est morte » mais par « la victime était morte
**avant la capture** ».

Deuxième rectification : **les littéraux de la recopie étaient JUSTES.** `barbed_ovipositor`
gatait `(Steppable, Object)` et `Mechanical` — exactement ce que dit le natif. Contrairement à
`master_of_the_tutelaries` (#462-…-r1, qui nommait `Decoy` = 1053), il n'y avait ici **aucune
erreur de trait**. Le défaut était ailleurs : dans le **substrat**.

## 2. Le décompilé, relu VERBATIM sur `rnca9r7q6c`

```
// IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger
a = AreEnemies(sel@+0x30 owner, sel@+0x60 target, 0)
b = NOT IsObjectOrSteppable(sel@+0x60 target)
c = On(0 = UnitDeath, 1) & get_OwnerIsActor
d = NOT AreEqual(sel@+0x90 triggeringAbility, Direct(AbilityOrEffect(0x438)))
e = NOT HasTrait(sel@+0x60 target, 5 = Mechanical)
=> ((c & (a & b)) & d) & e

// IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(this, selector)
left  = new <ctor>(selector, 0x1b, 0);   // HasTrait(selector, 27 = Steppable)
right = new <ctor>(selector, 0x0d, 0);   // HasTrait(selector, 13 = Object)
return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);
```

**`b` et `e` ont le MÊME sujet (`sel@+0x60`) et sont TOUS DEUX des `HasTrait`** : côté natif ils
lisent forcément le même substrat, `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
(collections `+0x40` base / `+0x48` accordés / `+0x50` retirés). **La mort n'en vide aucune.**

## 3. La mesure — `--step substrat`

| régime | `StatsComponent` | substrat BRUT (recopie) | substrat FOYER (nœuds DSL) |
|---|---|---|---|
| victime **vivante** au chargement | présent | kit **mesuré** | **identique**, bit pour bit sur `{Steppable, Object, Mechanical}` |
| victime **morte** au chargement | **ABSENT** | **`[]`** → gates AVEUGLES | kit gameconfig → gates VOYANTS |

`combatSnapshot.units` **n'inclut pas les morts** — mesuré sur un état live : `decisionView` =
`{77, 79, 81, 83}`, `combatSnapshot` = `{77, 79, 83}`, l'absent `81` étant le `tyranParasite` mort
en cours de bataille. Or `snapshot._load_stats_and_effects` ne pose de `StatsComponent` que pour
les lignes de `combatSnapshot.units`. Le `set()` du port était donc un **artefact de chargement**,
pas une lecture. C'est le vice #226, sur un autre gate.

Le seul écart du régime nominal est le pseudo-trait de **grande-alliance** (`Imperial`/`Xenos`/
`Chaos`) que le foyer ajoute — jamais l'un des trois traits gatés. **Value-preserving prouvé, pas
supposé.**

**Atteignabilité pour CE trigger** : un `On(UnitDeath)` ne vise un cadavre-au-chargement que s'il a
été **ressuscité**. `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (port
`operations/resurrect.py`) cible explicitement une unité `IsDefeated`, et ni lui ni
`operations/revive.py` ne posent de `StatsComponent`. Le régime survit donc à la résurrection.

## 4. Le fix

Les deux conjoints passent par les nœuds DSL du foyer, évalués sur l'`AbilityEntities` que le natif
tient pour tout `CreateTrigger` (`entities_from_state(state, owner, dying)` pose `Target()` sur
`sel@+0x60`) — même forme que `BattleFatigue` et `MasterOfTheTutelaries`, **aucune 3ᵉ recopie** :

```python
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())              # NOT IsObjectOrSteppable
_HAS_TRAIT_MECHANICAL  = HasTrait(Target(), int(UnitTrait.Mechanical))  # NOT HasTrait(..., 5)
```

**Le voisin `Mechanical` est migré AUSSI, et ce n'est pas du « pendant que j'y suis »** : il lisait
la **même variable locale** que le conjoint migré. Ne migrer que l'un aurait laissé le module avec
**deux substrats de traits différents pour deux `HasTrait` du même sujet** — strictement pire que
l'état d'avant. Le mutant B ci-dessous mesure ce que cette moitié-migration coûte.

La garde de port « entité sans `UnitComponent` » est **requalifiée** : elle était présentée comme
une part d'`IsObjectOrSteppable` (« objet = pas de `UnitComponent` »), ce qui est faux — le natif ne
teste que des **traits**. Même correction que celle déjà faite sur MoT.

## 5. Confrontation live — le régime CADAVRE, sur un état réel

`--step live` / `test_barbed_ovipositor_corpse_substrate_live` : le Parasite est placé **au contact**
d'un `necroWarden` à 1 PV (`--place`/`--a-place`, #477-r5), il l'achève par son attaque **normale**,
puis l'état est **rechargé**.

```
runner 538 (MC1_67) | decisionView ids=[77, 79, 81]   combatSnapshot ids=[77, 79]
cadavre eid=81 (necroWarden) : StatsComponent=False
    substrat BRUT  (avant le fix) = []
    substrat FOYER (apres le fix) = ['Hero', 'LivingMetal', 'Mechanical', 'Xenos']
PORT courant  : fire=False  Rippers poses=0
PORT d'AVANT  : fire=True  (2 consultations des noeuds substitues)
```

⚠ **Un SECOND ennemi est indispensable au montage** : sans lui, tuer la victime **termine la
bataille** et `decisionView` rend une liste d'unités **vide** — mesuré (`decisionView ids=[]`), le
bras ne mesurait alors rien. Même piège que celui rencontré sur le crate de #462-…-r1.

## 6. Contre-épreuves — 4 mutants, 4 détectés (et le 4ᵉ a exigé un durcissement)

| mutant | garde offline |
|---|---|
| A — recopie BRUTE restaurée (les deux gates) | **20 rouges** / 30 |
| B — migration PARTIELLE (`Mechanical` reste brut) | **5 rouges** |
| C — sujet `Target()` → `Caster()` sur le foyer | **12 rouges** |
| D — foyer remplacé par une recopie **locale équivalente** | **0 rouge**, puis **1 rouge** après durcissement |

Le mutant D est le même angle mort que celui mesuré sur #462-…-r1 : une recopie locale
strictement équivalente est **comportementalement indistinguable**, donc aucun critère de VALEUR ne
peut la voir. Le risque qu'elle porte est la **divergence future** — exactement le mécanisme qui a
produit le `Decoy` de MoT. D'où un volet de **PROVENANCE** (AST, pas grep : un appel dans un
commentaire ne compte pas) qui exige que le module **appelle** `is_object_or_steppable`.

La garde porte aussi l'invariant en formulation positive : **`matches` rend le même verdict pour un
même `visualId`, que la victime ait été chargée vivante ou déjà morte.**

## 7. Non-régression — rayon de souffle du foyer (3 consommateurs)

| fichier | résultat |
|---|---|
| `test_barbed_ovipositor_object_or_steppable_offline.py` (neuf) | **30 verts** |
| `test_battle_fatigue_object_or_steppable_offline.py` | **verts** (lot de 58 avec les deux autres offline) |
| `test_master_tutelaries_object_or_steppable_offline.py` | idem |
| `test_barbed_ovipositor_live.py` | **11 verts** (10 + le bras neuf), 0 skipped |
| `test_438_barbed_ovipositor_pair_term_live.py` | **4 verts** |
| `test_master_tutelaries_active_gate_live.py` | **5 verts** |
| `test_master_tutelaries_object_target_live.py` | **7 verts** |

## 8. Ce qui n'est PAS couvert

* **Le régime CADAVRE × `Steppable`/`Object` n'est pas confronté LIVE** — seul `Mechanical` l'est.
  Il faudrait un cadavre dont le **kit** porte l'un des deux, or **aucune unité du pool n'en porte**
  (recensement : 28 porteurs `Object` et 27 `Steppable`, tous `npc` sauf deux summons —
  `genesSmnDecoy`, `astarSmnHaywireMine`). Le montage existe (injection catalogue + `--a-place`,
  recette de #462-…-r1) mais n'a pas été rejoué ici. Les trois traits sont couverts **offline**, sur
  des `visualId` RÉELS, dans les deux régimes.
* **Le conjoint `d`** (`NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)`) reste
  **non porté et inerte** — inchangé par cette tranche, cf. l'en-tête du module.
* **Le natif n'a pas été confronté sur le refus lui-même** pour `IsObjectOrSteppable` sur
  `barbed_ovipositor` : le seul bras `IsObjectOrSteppable` du fichier live reste **offline** (decoy
  `genesSmnDecoy`). Le sens du conjoint est établi par le décompilé et par la confrontation native
  faite sur MoT (#462-…-r1 : crate `Object` → 0 Screamer, vraie unité → 1).

## 9. Résidu

* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1`** — **la lecture BRUTE de `ctx.traits` est un patron, pas
  un accident** : un balayage **approché** (la prose des docstrings n'est pas entièrement écartée)
  compte **54 sites sur 29 fichiers** dans `engine/`, dont **10 fichiers portent aussi un marqueur
  de mort** (`runner/operations/movement.py` 4, `triggers/genestealer.py` 5,
  `triggers/dispatch/{core,move_death}.py`, `triggers/loki/{cosmic_horror,spiritual_leader}.py`,
  `runner/components.py` 6, `entities/effects/base.py`, `runner/operations/triggers/base.py`).
  Chacun porte **potentiellement** le même vice : gate aveugle dès que le sujet est une entité
  chargée morte. ⚠ Le chiffre est à **re-dériver** par un probe dédié (le balayage ci-dessus compte
  encore des lignes de prose — `barbed_ovipositor` y figure par sa propre docstring). La question
  par site est la même que pour cette tranche : **le sujet peut-il être une entité morte au
  chargement ?** Le foyer de la réponse existe déjà (`entity_trait_names`), donc le coût par site
  est faible ; c'est le **tri** qui est le travail.
