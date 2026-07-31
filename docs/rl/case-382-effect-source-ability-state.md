# case-382 — l'`AbilityState` d'un effet vient de sa SOURCE, jamais de son PORTEUR

> Ferme le residu `#366-r1-src` (`case-366-r1-saga-other-space-wolves.md` §5). Le canal touche est
> **partage par TOUTES les entrees d'`EFFECT_CLASSES`** — d'ou le recensement du §3 et le re-jeu large
> du §6.

## 1. Ce que le natif fait — il *BAKE*, a la POSE

Relu au desassemblage, pas deduit du symptome. La chaine complete, dans l'ordre d'execution :

```
IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute
    evalue le noeud DSL AddEffect(<type>, <abilityStateReference>, source, targets, turns)
    -> IdunBattle.Entities.Behaviours.AddEffectBehaviour$$GetEffectBuilder(entities, processor)
    -> IdunBattle.Operations.AddEffectOperation$$Execute(source, owner, effectBuilder, type, opts)
        -> (*effectBuilder)(nextId, effectType, abilityState)
           = IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)
               -> IdunBattle.Entities.Blueprints$$Effect(id)          # cree l'entite-effet
               -> EffectComponent[+0x18 .. +0x38] = *abilityState     # <<< LE BAKE, 0x24 octets
        -> IdunBattle.Operations.AddEffectOperation$$AddNewEffect(source, owner, effect, type, turns)
               -> EffectComponent+0x10 = SourceUnitId                 # <<< la SOURCE, publiee live
               -> EffectComponent+0x14 = OwnerId (le PORTEUR)
```

`DefaultEffectBuilder` recopie **litteralement** les 0x24 octets de l'`AbilityStateReference` recue
dans `EffectComponent+0x18` (`*(u64*)(comp+0x18) = *(u64*)abilityState`, puis `+0x20`, `+0x28`,
`+0x30`, `+0x38`). `AddNewEffect`, lui, n'ecrit **jamais** `+0x18` : il ne pose que source, owner,
`TimesApplied@+0x6c` et la duree. Le state est donc fige **une fois pour toutes a la pose**.

L'argument `abilityState` vient de l'ability QUI POSE :
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` ->
`IdunBattleLogic.Entities.DSLSelectors$$AbilityState(entities, owner, abilityType)` avec
`owner = AbilityEntities.Owner` — le CASTER.

A la LECTURE, `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` et
`IdunBattle.DSL.AbilityStateFromEffectSelector$$Select` relisent ce **meme** `EffectComponent+0x18`
et rien d'autre. **L'effet ne consulte JAMAIS son porteur.**

Layout de la struct (dump `gqfc5mff6c`, TypeDefIndex 24412) : `Owner(BEntityId)@+0x00` ·
`Ability(AbilityType, 0x10 o)@+0x04` · `Nullable<AbilityState>@+0x14`, ou
`AbilityState = {Level@0, VariableMultiplierPercentage@4, TempData.Counter@8}`. Ce sont **Level** et
**VariableMultiplierPercentage** qui indexent et scalent les `ConfigVar` des formules d'effet.

## 2. Ce que le port faisait, et pourquoi aucun test ne l'avait vu

`EffectsState.seed(effects_by_unit, mult_by_unit, ability_level_by_unit)` etait cle **par
PORTEUR** : chaque instance recevait le `unitConfig` de l'unite qui la porte. Identique tant que
porteur == source (tout owner-effect), **faux** des qu'ils different.

Deux masques, et il faut les deux pour comprendre le silence :

1. **`buildNormalizedBC` ecrit le MEME `targetAbilityLevel` dans `ActiveAbilityLevel` ET
   `PassiveAbilityLevel`** de toutes les unites (`frida/hooks/features/normalize-bc/json-build.ts`
   L204-205). Sur tout montage normalise, niveau porteur == niveau source == 50 : les deux modeles
   coincident **numeriquement**. Une garde montee la-dessus est verte et vide.
2. **Aucun effet porte n'avait porteur != source** avant `1224
   SagaOfTheWarriorBorn_OtherSpaceWolves` (`case-366-r1`), dont le behaviour pose explicitement sur
   AUTRUI : `targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner, 0xd, OnlyAlive)`.

⚠ Le **multiplicateur de rarete**, lui, reste per-unite meme normalise (MESURE : Ragnar 200, Ulf
180) — il touche donc la face CRIT (`extraCritDmg` est la seule variable de `SagaOfTheWarriorBorn`
listee dans `variablesAffectedByRarityBonus`) meme sans dissocier les niveaux.

## 3. Recensement — deux axes, mesures separement

### 3.1 Axe SENSIBILITE au canal (offline, exact sur ce qu'il mesure)

`python probe_382_effect_source_ability_state.py --scan` — pour chaque entree d'`EFFECT_CLASSES`,
la classe (corps propre + bases jusqu'a `BaseEffect` exclu + helpers de MODULE appeles, profondeur
2) mentionne-t-elle `ability_level` / `active_ability_level` / `ability_variables_multiplier` ?

Mesure du 2026-07-31, APRES rebase sur `origin/master` (`d70c60d2` — `visions_of_heresy` puis `ExemplarOfTheKauyon` ont ajoute
trois entrees entre-temps ; ces chiffres se periment, les RE-DERIVER plutot que citer cette ligne) :

| | |
|---|---|
| `EFFECT_CLASSES` | **138** entrees, **135** classes distinctes |
| SENSIBLES au canal | **81** entrees |
| INDIFFERENTES | **57** entrees (le correctif y est un no-op quel que soit l'ecart) |

Ce que ce balayage NE dit PAS, et qui est la limite assumee : il ne suit que les helpers du **MEME
module**, sur 2 niveaux ; une delegation inter-modules rendrait un faux negatif. Il ne dit rien non
plus de l'axe suivant.

### 3.2 Axe « source PEUT differer du porteur » (live, exact sur ce qu'il couvre)

`python probe_382_effect_source_ability_state.py --sweep --advance 6` — sept rosters CHOISIS pour
ramener chacun une famille d'aura, plus le tout-venant, lus apres **6 activations d'equipe jouees
par l'IA** (sans quoi on ne verrait que les owner-effects du deploiement) :

| roster | porteur vise | effets | source == porteur | source != porteur |
|---|---|---|---|---|
| `darkaAzrael,darkaHellblaster,ultraApothecary` | LionHelm (aura block) | 6 | 6 | **0** |
| `eldarAutarch,eldarRanger,eldarFarseer` | PathOfCommand (aura crit) | 5 | 5 | **0** |
| `tauShadowsun,tauCrisis` | DefenderOfTheGreaterGood (aura coups) | 10 | 10 | **0** |
| `ultraTigurius,ultraApothecary` | PsychicFortress (aura reduction) | 6 | 6 | **0** |
| `deathTyphus,necroWarden` + MoW `deathCrawler` | Contagions + source MoW | 11 | 11 | **0** |
| `tyranTyrantGuard,tyranParasite,tyranNeurothrope` | GuardianOrganism + Synapse | 10 | 8 | **2** |
| roster aleatoire 5v5 (seed 777) | tout-venant | 35 | 35 | **0** |

**ANTI-FAUX-NEGATIF, et c'est le point** : sur les **83** instances, `source` est **renseignee 83
fois sur 83** (`source_null = 0`). Les zeros de la derniere colonne sont donc des MESURES, pas une
panne d'instrument — et l'instrument rend bien des lignes des qu'il y en a.

Les deux seules lignes cross-unite du balayage, `IgnoreBattleFatigue` pose sur le TyrantGuard par
ses DEUX porteurs de `Synapse` :

```
u79 <- u81 IgnoreBattleFatigue  porte (180, 50, 50) | source (180, 50, 50) | porteur (180, 50, 50)
u79 <- u83 IgnoreBattleFatigue  porte (180, 50, 50) | source (180, 50, 50) | porteur (180, 50, 50)
```

Etats IDENTIQUES -> le correctif y est numeriquement neutre. C'est le cas general : sur un seed
normalise, deux unites de MEME rarete ont le meme triplet.

Corrobore au rebase sur `d70c60d2` : `1181 ExemplarOfTheKauyon_AdditionalHits` (entree neuve de
#404, MEME fichier `hits.py`) est bien HORS de ce regime. Verifie moi-meme plutot que repris du
rapport — roster `tauShadowsun,tauCrisis` vs `orksNob`, 8 activations IA : **10 effets, cross = 0**,
dont le frere `CyclicIonBlaster_AdditionalHits` (`source == porteur`). L'effet 1181 lui-meme n'a pas
ete materialise dans ce montage (il se pose au CAST) — sa garde `test_exemplar_of_the_kauyon_hits_
live.py` est verte apres le correctif (**7 tests**).

**Lecture** : une AURA n'est PAS un effet pose sur le beneficiaire. L'entite-effet vit sur son
PORTEUR-SOURCE et projette sa modification par selecteur
(`AStatModifierEffect$$ApplyModification`, cf. `runner/operations/aura_stat_mods.py`) — porteur ==
source. Le regime `source != porteur` est donc **etroit** : il faut un behaviour dont le noeud
`AddEffect` a un selecteur `targets` distinct de `source` (`1224`, `Synapse`).

### 3.3 Ce qui n'a PAS ete balaye — a dire, pas a masquer

* **Le decompile des 135 `CreateBehaviour`** qui posent ces effets. C'est la seule facon d'obtenir
  la liste EXHAUSTIVE des entrees ou `targets != source` ; elle n'a pas ete faite (cout). Les
  familles NOMMEES par la RE (effet pose sur autrui par un trigger, jumeaux drone, effet de tuile,
  effet pose par une MoW sur une unite) sont couvertes par le comportement, pas par un inventaire.
* **Les effets absents des six rosters** et des 6 activations jouees. Le balayage est un
  echantillon dirige, pas une enumeration.
* **Les effets POSES OFFLINE** par `runner/operations/effects.py::AddEffectOperation.execute` : ce
  vecteur prend deja `ability_level` / `multiplier_pct` EXPLICITEMENT de son appelant. Verifier que
  chaque appelant passe bien l'etat de la SOURCE (et non de la cible) est un travail distinct, non
  fait ici.
* **La source MoW sur le seam PREDICTION** : `_effect_source_ability_states` exclut volontairement
  les Machines (leur `unitConfig` est en erreur, leur etat vit PAR ABILITY dans `abstate_by_id`, et
  rien ne dit quelle ability a pose l'effet). Elles retombent sur le porteur, a l'identique
  d'avant. Le seam COMBAT, lui, les resout par `_machine_ability_state`.

## 4. Le correctif — un foyer, deux seams

`engine/entities/effects_state.py::baked_ability_state(captured, carrier_id, carrier_state,
ability_state_by_unit)` — mirror de `DefaultEffectBuilder`. Il rend l'etat de la SOURCE
(`captured["source"]` = `EffectComponent.SourceUnitId`) quand elle est RESOLVABLE et DIFFERENTE du
porteur, et le **REPLI est le PORTEUR** dans tous les autres cas (source absente, non entiere, non
chargee, table non fournie) — jamais un neutre, qui ecraserait le multiplicateur de rarete.

Consequence voulue : **le changement ne mord QUE dans le regime dissocie**. Tous les appelants
historiques de `EffectsState.seed` (forme a trois arguments) gardent exactement leur semantique.

Deux seams l'alimentent :

* **COMBAT** — `runner/snapshot.py::_load_stats_and_effects`, PASSE 1 : `abstate_by_id` construit
  AVANT la boucle de materialisation (elle est PURE DONNEE : `unitConfig` pour les unites,
  `_machine_ability_state` pour les MoW ; elle ne depend d'aucun `StatsComponent`). La table sert
  aux DEUX materialisations de la fonction — celle qui nourrit `UnitContext.from_snapshot` et
  `state.effects = EffectsState.seed(...)`.
* **PREDICTION** — `playbook/scene.py::_effect_source_ability_states(predictor)` +
  `step_context`. Le seam `Scene.from_state` en beneficie sans changement (il consomme
  `state.effects`).

Extrait, `runner/snapshot.py::_ability_state_from_config` — le gate est le MULTIPLICATEUR (une
ligne Machine rend `{"error": "visualId introuvable"}`) :

```python
if not isinstance(uc, dict) or uc.get("abilityVariablesMultiplier") is None:
    return (100, None, None)
```

## 5. Mesure — le montage DISSOCIE, et lui seul

`probe_382_effect_source_ability_state.py`. Ragnar (`spaceBlackmane`, SOURCE) execute
`necroOverlord` (Hero) -> le natif pose `1224` sur Ulf (`spaceWulfen`, PORTEUR) ; Ulf charge
`necroWarden`. `--unit-stat spaceBlackmane:PassiveAbilityLevel=1` descend le niveau de la SOURCE.

⚠ **ORDRE** : `--unit-stat` est applique au MEME endroit que `--hp-target`, donc **apres** la
normalisation. L'inverser rendrait la garde verte et vide.

MC1_67 / seed 777 :

```
[p382] source u81 state=(200, 1, 50) | porteur u83 state=(180, 50, 50)
[p382] instance 1224 : ability_level=1 multiplier=200
[p382] LIVE    n=4 [2679, 3724, 2879, 3771]
[p382] OFFLINE n=4 [2679, 3724, 2879, 3771]
[p382] VERDICT OK
[p382] cross-unit u83 <- u81 SagaOfTheWarriorBorn_OtherSpaceWolves : porte (200, 1, 50), source (200, 1, 50)
```

**Vue ROUGE par mutation** (`baked_ability_state` forcee a rendre l'etat du PORTEUR = l'etat
d'avant), verbatim :

```
[p382] source u81 state=(200, 1, 50) | porteur u83 state=(180, 50, 50)
[p382] instance 1224 : ability_level=50 multiplier=180
[p382] LIVE    n=4 [2679, 3724, 2879, 3771]
[p382] OFFLINE n=6 [2679, 3724, 2879, 3771, 3273, 3750]
[p382] VERDICT DIVERGE
[p382] cross-unit u83 <- u81 SagaOfTheWarriorBorn_OtherSpaceWolves : porte (180, 50, None), source (200, 1, 50)
```

Les 4 premiers coups sont DEJA bit-exacts sous la mutation : la divergence est localisee au NOMBRE
de coups, pas a leur valeur. Second couple `C1_25` / seed 31337 : meme carre (live n=4
`[3682, 3969, 3838, 3425]`, offline n=6 sous mutation, n=4 apres correctif).

Sous la meme mutation, `tests/engine/runner/test_effect_source_ability_state_live.py` rend
**6 failed / 2 passed**. Les DEUX verts le doivent : `test_seed_defaults_are_unchanged_offline`
(garde de NON-REGRESSION du canal partage — elle doit passer dans les deux etats) et
`test_regime_is_actually_dissociated` (lu du `combatSnapshot`, independant du port).

## 6. Re-jeu large — le canal est partage

| suite | resultat |
|---|---|
| `test_effect_source_ability_state_live.py` (neuf) | **8 passed** |
| `test_exemplar_of_the_kauyon_hits_live.py` (voisin de `hits.py`, #404) | **7 passed** |
| `test_378_parent_link_offline.py` + `test_366_effects_registry_partition_offline.py` | **verts** |
| `test_saga_other_space_wolves_live.py` + `test_static_statmod_g1_{expiry,live}.py` | **23 passed** |
| `test_dotgg_extra_hits_live.py` + `test_path_of_command_crit_aura_live.py` | **17 passed** |
| `test_ischarging_saga_{hits,crit}_live.py` | **15 passed** |
| `test_my_will_be_done_overlord_live.py` + `test_load_state_inactive_effects_live.py` + `test_seeded_eager_statmod_expiry.py` | **37 passed** |
| `test_lion_helm_block_aura_live.py` + `test_psychic_fortress_aura_live.py` + `test_contagions_aura_range_live.py` | **7 passed** |
| `tests/engine/test_predict_live.py` (seam PREDICTION) | **2 passed** |

**Agreement replay-diff**, roster aleatoire 5v5, seed 777 / MC1_67, 40 pas — joue AVEC le correctif
puis SOUS LA MUTATION, deux runners distincts :

```
[positioning] 34 moves : exact=32 (94%)  <=1hex=32 (94%)
[ability]     32 casts : match=31 (96%)
[stay]        4 sur place : match=4 (100%)
```

**Identique dans les deux etats** — cette bataille ne contient aucun effet cross-unite (cf. §3.2),
donc le correctif y est un no-op strict. C'est la confirmation experimentale du perimetre annonce.

Cliquets : `probe_181_targeting_gaps` (98/98, 0 manquante), `probe_120 --step 0` (0 litteral
manquant), `probe_273 --only-scan` (aucune sortie de run dans `data/`),
`probe_365_versioned_imports_gitignored` (205 fichiers, 858 imports, 0 faute) — **4/4 verts**.

## 7. Ce qui n'est PAS couvert

* Les quatre points du §3.3 (decompile exhaustif des `CreateBehaviour`, effets hors echantillon,
  vecteur de pose OFFLINE, source MoW sur le seam prediction).
* **La face CRIT n'est pas mesuree en degat** : elle est couverte STRUCTURELLEMENT (l'instance porte
  desormais le multiplicateur 200 de la source au lieu de 180, et `extraCritDmg` est la seule
  variable scalee par lui), pas experimentalement. Le montage manquant est `--crit` sur le receveur
  — meme trou que `case-366-r1` §6.
* **`EffectsState.seed` ne propage toujours PAS l'`active_ability_level` du PORTEUR** (il vaut
  `None`, comme avant). Ce n'est reparé que sur la branche SOURCE, ou le triplet complet est
  disponible. Elargir le repli changerait la valeur lue par les ~20 classes a cascade
  `active_ability_level -> ability_level -> level` sur TOUTES les batailles : hors perimetre, a
  traiter comme une tranche propre si un ecart le motive.
* **Un seul effet exerce le regime dissocie** (`1224`). Le balayage a trouve UN second effet
  cross-unite (`IgnoreBattleFatigue`, pose par `Synapse`), mais avec des etats IDENTIQUES : il
  atteste que l'invariant tient, il ne le DISCRIMINE pas. Les autres entrees sont couvertes par
  l'invariant transverse (`test_cross_unit_invariant_holds`), pas par une mesure propre.
* **Trois docstrings mises a jour, pas mesurees** : `damage_reduction.py` (aura GuardianOrganism #89
  et l'aura d'Infiltrate de Sibyll) annonçaient « niveau/mult du porteur = le DEFENSEUR » ; c'est
  desormais la SOURCE, conformement au natif. Aucun montage n'a fait materialiser ces deux effets
  sur un ami ring-1 pendant ce cas (le balayage `guardianorg` ne les a pas produits), donc le
  changement y est correct par construction mais NON CONFRONTE.
