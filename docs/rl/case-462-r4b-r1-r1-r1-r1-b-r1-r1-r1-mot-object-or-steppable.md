# #462-r4b-r1-r1-r1-r1-b-r1-r1-r1 — MoT : `{Steppable, Decoy}` était `Steppable | Object`

**Livré le 2026-08-05.** Résidu ouvert par `case-462-r4b-r1-r1-r1-r1-b-r1-r1-object-or-steppable.md`
§5 (PR #635), qui a créé le foyer `entities/triggers.py::is_object_or_steppable` et **mesuré** que
`master_of_the_tutelaries.py` en faisait une recopie manuelle infidèle — sans la corriger, faute de
savoir si l'écart était exerçable.

**Il l'est.** La question que la fiche parente laissait ouverte — « ces `LootObj_*` peuvent-ils être
`AreEnemies` du porteur *et* recevoir une attaque `Psychic` ? » — se répond **OUI**, et pas par
raisonnement : par un montage joué. Le natif refuse le Screamer sur une cible `Object`, le port
d'avant l'accordait.

## 1. Le conjoint, relu verbatim

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger`
compose, `op_BitwiseAnd` par `op_BitwiseAnd` (build `rnca9r7q6c`) :

| # | conjoint | sujet |
|---|---|---|
| 1 | `On(9 = Attack, 1)` | — |
| 2 | `HasEffect(sel@+0x30 owner, 0x4ad = 1197, onlyActive = 0, relation = 6 = Both)` | `+0x30` |
| 3 | `AreEnemies(sel@+0x30 owner, sel@+0x60 target, 0)` | `+0x30`, `+0x60` |
| **4** | **`NOT IsObjectOrSteppable(sel@+0x60 target)`** | **`+0x60`** |
| 5 | `CurrentAttackDamageProfilesContain(0xd = 13 Psychic, 0)` | — |

Le sujet du 4ᵉ est `+0x60`, **la CIBLE** — le même sélecteur que le 2ᵉ argument d'`AreEnemies`.
Même couple `+0x30` = self / `+0x60` = l'autre que sur `BattleFatigueAbility$$CreateTrigger`.

Et la factory, `IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable`, est triviale :

```
left  = new <ctor>(selector, 0x1b, 0);      // HasTrait(selector, 27 = Steppable)
right = new <ctor>(selector, 0x0d, 0);      // HasTrait(selector, 13 = Object)
return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);
```

⚠ `Object` = **13**, `Decoy` = **1053**. Le port nommait le second. Le natif ne nomme que 27 et 13.

## 2. Ce que la migration change — et rien d'autre

Mesure re-dérivée du gameconfig (`--step census`, 683 unités : 127 lineup / 491 npc / 65 summons) :

| volet | porteurs | effet |
|---|---|---|
| **retiré** — `Decoy` sans `Steppable` | **0** | aucune unité ne perd le gate : le retrait est *value-preserving* |
| **ajouté** — `Object` sans `Steppable` | **28** (tous npc `LootObj_*`) | 28 cibles que le natif écarte et que le port laissait passer |

Les deux ensembles sont **disjoints** dans le catalogue : les 28 porteurs `Object` n'ont jamais
`Steppable`, et les 27 porteurs `Steppable` n'ont jamais `Object`. Les 2 porteurs `Decoy`
(`genesDecoy`, `genesSmnDecoy`) portent tous deux `Steppable`, d'où le zéro de la première ligne.

## 3. Le recensement seul aurait conclu FAUX

Aucun des 28 porteurs `Object` n'est dans `data/seed-bc.json` (histogramme des traits des 175 unités
du seed : `Object` = 0), et tous sont `kind == npc`, donc hors `rl_duel build --list-pool`. La
lecture naturelle est « régime inatteignable, correctif cosmétique ». **Elle est fausse**, et c'est
le point de méthode de cette tranche : *un zéro de recensement mesure ce que le seed contient, pas
ce qu'un montage peut produire.*

Le montage tient en trois écritures, et la **deuxième** est celle qui n'était pas évidente :

1. `catalog_inject.write_augmented_seed_bc` ajoute le `LootObj_*` au bloc `Units` du seed ;
2. on lui **force ses stats** (`Health`) : `buildNormalizedBC` ne le **normalise pas** — il n'a
   aucune progression, d'où son absence du pool (97 unités avec ou sans lui) — mais il **garde son
   entrée dans le template**. Ce sont donc les valeurs qu'on écrit qui arrivent en bataille.
   Le catalogue ne lui donne **aucune** stat (`health` nul), donc sans ce forçage il arrive mort ;
3. on le pose **à la tuile voulue** via `initAndStart.playerUnits` avec `playerId = PLAYER_ID_AI`
   (la voie `--a-place`, #477-r5). C'est **ça** qui contourne le refus de pool : `_build_custom` et
   `rl_duel --a-units` exigent l'appartenance au pool, `playerUnits` non.

⚠ Un piège mesuré : avec le crate pour **unique** ennemi, `decisionView` rend **0 unité** (la
bataille ne tient pas). Il faut une vraie unité adverse en plus — et l'exiler au coin opposé, sinon
le Horror peut la choisir et le bras ne discrimine plus rien.

## 4. La confrontation native — deux bras appariés

Même roster, même tuile de cast `(5,8)`, même seed, même board `MC1_67`, même position d'Abraxas
`(4,7)`. **Seule change l'unité au contact** du Pink Horror invoqué par 1096 — donc la cible de son
attaque Psychic d'apparition (`PerformAIAttackFromCurrentPosition`).

| bras | cible du Horror | traits vus par le port | PV cible | **Screamers** |
|---|---|---|---|---|
| `crate` | `LootObj_Crate_Imp` | `NPC, Object` | 5000 → **2705** | **0** |
| `warden` | `necroWarden` | `Hero, LivingMetal, Mechanical, Xenos` | 8536 → **8026** | **1** |

Les deux préconditions que le recensement ne pouvait pas trancher sont **satisfaites et mesurées** :

* **`AreEnemies`** — le crate arrive **team 2** face à un Abraxas **team 1**, vivant (5000 PV) ;
* **cible d'attaque légale** — `abilityTargets` rend `(abilityId 69, targetId <crate>)` : l'attaque
  normale concrète d'Abraxas peut le viser. C'est le natif qui le dit (l'endpoint interroge son
  ciblage), pas une déduction.
* **le profil Psychic** ne dépend pas de la cible :
  `IdunBattleLogic.Entities.DSLTriggers$$CurrentAttackDamageProfilesContain` alloue un
  `DamageProfilesContainsTrigger$$.ctor(profileType, includeNotApplied)` — **aucun sélecteur**, il
  lit les profils de l'attaque courante. Rien de la cible ne peut faire échouer ce conjoint.

**La chute** : sur ce même état live, le port d'AVANT le fix (recopie `{Steppable, Decoy}` rejouée
par substitution) rend `matches(crate) = True`. Il aurait spawné un Screamer que le natif ne produit
pas. Le port d'après rend `False`, et `True` sur le warden — accord sur les deux bras.

**Non-vacuité du zéro** : un zéro est le résultat le plus facile à obtenir pour de mauvaises
raisons. Deux gardes le rendent attribuable, et elles sont assertionnées **avant** lui — le Horror
doit être APPARU (`dHorror = 1` dans les deux bras) et la cible doit avoir PERDU des PV (l'attaque a
bien eu lieu : 5000 → 2705).

## 5. La forme du port — pourquoi ce n'était pas un remplacement d'appel

Le foyer est un **nœud DSL** (`TriggerOr(HasTrait(…, 27), HasTrait(…, 13))`) ; `MasterOfTheTutelaries
SummonAbility.matches` évalue **impérativement**, sans `DslContext` sous la main. Le port matérialise
donc l'`AbilityEntities` que le natif tient pour tout l'arbre :

```python
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())   # sel@+0x60
...
entities = entities_from_state(state, self.owner_id, tgt)    # Target() -> la cible de l'attaque
if _IS_OBJECT_OR_STEPPABLE.should_trigger(entities):
    return False
```

Exactement la forme déjà retenue par `BattleFatigueAbility` (#635). **Aucune troisième recopie.**

Deux effets de bord de ce passage, tous deux dans le sens de la fidélité :

* **le substrat de traits change de source**. Le port lisait `StatsComponent.ctx.traits` brut ; le
  contexte DSL passe par `entity_trait_names`, qui ajoute le trait de grande-alliance **et** retombe
  sur le gameconfig quand l'entité n'a pas de `StatsComponent` (le cas d'un CADAVRE, #226). Sans
  effet mesurable ici (une cible d'attaque est vivante), mais c'est le bon substrat.
* **la garde `UnitComponent is None`** reste, **relabellée**. Elle se présentait comme une part
  d'`IsObjectOrSteppable` (« objet = pas de `UnitComponent` ») : c'est faux, le natif ne teste que
  des traits. Elle est INERTE — les six sites qui créent une entité (`snapshot.load_state` ×2,
  `operations/spawn.py` ×4, `components.py`) posent tous un `UnitComponent`.

## 6. Validation

* **Garde OFFLINE — `tests/engine/runner/test_master_tutelaries_object_or_steppable_offline.py`
  (18 tests).** État synthétique minimal (deux unités d'équipes opposées, marqueur 1197 actif,
  événement `On(9)` porteur du profil Psychic) : **seuls les traits de la cible changent**.

  | bras | verdict | port d'AVANT | contre-épreuve `neutralisé` |
  |---|---|---|---|
  | cible normale (contrôle) | `True` | `True` | `True` — identique, correct |
  | `Steppable` (27) | `False` | `False` | `True` — diffère |
  | **`Object` (13)** | `False` | **`True`** | `True` — diffère |
  | `Steppable`+`Object` | `False` | `False` | `True` — diffère |
  | `Decoy` seul (1053) | `True` | **`False`** | `True` — identique |

  **Deux** contre-épreuves, et la seconde est celle qui compte : `neutralisé` (nœud toujours faux)
  prouve que le conjoint *existe et mord* ; **`recopie`** (nœud rejouant `{Steppable, Decoy}`)
  reconstitue le port d'AVANT et prouve que le fix **change** quelque chose. Sans elle, un fix qui
  aurait « oublié » `Object` resterait invisible — les trois autres bras coïncident dans les deux
  mondes.

  ⚠ **Les deux substitutions COMPTENT leurs consultations, et le compteur est lu AVANT le verdict.**
  Une mutation jamais consultée rendrait « verdict identique », qu'un lecteur pressé lirait comme
  « le fix ne change rien ». Ici le VERT est le résultat suspect.

  Le bras `Decoy` seul est un **TÉMOIN, pas une garde de régression** : aucune unité réelle ne porte
  `Decoy` sans `Steppable`, donc il n'existe que dans l'état synthétique. Ce qu'il fige est le
  **littéral du natif**.

* **Garde LIVE — `tests/engine/runner/test_master_tutelaries_object_target_live.py` (7 tests).**
  Les deux bras appariés du §4, 2 runners, disposés. Elle assertionne dans cet ordre : les conjoints
  amont (team adverse, trait `Object` vu, `Steppable` **absent** — sinon le bras ne discriminerait
  rien), la non-vacuité (Horror apparu, PV en baisse), le contrôle (≥ 1 Screamer sur une vraie
  unité), **puis** le critère (0 Screamer sur `Object`), l'accord du port, et le désaccord de la
  recopie. Un montage qui ne s'installe pas **échoue** (`pytest.fail`), il ne skippe pas (#268).

* **Éprouvées par MUTANTS — 4 posées offline, 4 détectées ; 1 posée live, détectée.**

  | mutant | effet | rouges |
  |---|---|---|
  | sujet `Target()` → le porteur (arguments de `entities_from_state` inversés) | le conjoint porte sur Abraxas | **10 / 18** |
  | foyer `Object` → `Decoy` | exactement l'infidélité qu'on ferme | **6 / 18** (+ 5 / 11 sur BattleFatigue) |
  | conjoint retiré (`if False and …`) | le port d'avant #635 | **13 / 18** |
  | recopie `{Steppable, Decoy}` restaurée | le port d'avant CE fix | **12 / 18** |
  | foyer `Object` → `Decoy` (sur le fichier **LIVE**) | idem, confronté au natif | **2 / 7** |

  Le mutant « recopie restaurée » n'a **pas** fait rougir `test_le_module_ne_porte_plus_de_recopie_
  de_traits` : le set y était une variable **locale**, pas un attribut de module. Les tests
  comportementaux l'ont attrapé quand même — la garde structurelle est un filet, pas le critère.

* **Non-régression** : `test_master_tutelaries_active_gate_live.py` **5 verts**,
  `test_barbed_ovipositor_live.py` **10 verts**, `test_battle_fatigue_object_or_steppable_offline.py`
  **11 verts**. 0 skipped.

## Résidus

* ~~**`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3`**~~ — **LIVRÉ (2026-08-05)**,
  `case-462-r4b-r1-r1-r1-r1-b-r1-r1-r3-barbed-substrat-traits.md`. La recopie de
  `barbed_ovipositor` était **fidèle sur les littéraux** — le défaut était le **substrat**.
  ⚠ **La formulation ci-dessus (« la cible est un CADAVRE, donc les substrats divergent ») était à
  moitié fausse** : une unité qui meurt *pendant* le run **garde** son `StatsComponent`, donc les
  deux substrats y coïncident bit pour bit. La divergence est indexée par « morte **avant la
  capture** », régime atteignable via `ResurrectUnitOperation$$Execute`. Migration donc
  **value-preserving mesurée** sur le nominal, **correctrice** sur le cadavre — et le voisin
  `NOT HasTrait(target, 5)`, qui lisait la même variable locale, est migré avec.
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r2`** (inchangé) — les 5 call-sites natifs non portés
  d'`IsObjectOrSteppable`.
* **NON MESURÉ, et nommé** : on ne sait pas si un `LootObj_*` arrive sur une **team adverse** dans
  une vraie bataille de campagne. Le montage du §3 le pose lui-même. `IsFriend` compare
  `GetCurrentPlayer(x).<+0x20>.<+0x24>` (0 quand l'entité n'a pas de joueur), et le site qui donne
  son `OwnerComponent` à un `LootObj_*` n'a pas été localisé dans le binaire (aucun symbole
  `LootObject`/`SpawnLoot`). Ce que la confrontation établit, c'est le **verdict du conjoint sur une
  cible `Object` ennemie** — pas la fréquence de cette configuration en jeu.
  Deux lectures indépendantes disent quand même qu'un objet est une cible d'attaque **ordinaire**
  côté natif : `KillMaimBurnAbility$$GetNextTarget` filtre `validNextTargets` par
  `NOT IsObjectOrSteppable` puis `.Otherwise(validNextTargets)` — ce repli n'a de sens que si
  l'ensemble des cibles valides peut être **intégralement** composé d'Object/Steppable ; et
  `BounceAbility$$Prioritization` les **déprioris**e (`ConditionalAmount(IsObjectOrSteppable(It),
  Negative(...), ...)`) au lieu de les filtrer.
