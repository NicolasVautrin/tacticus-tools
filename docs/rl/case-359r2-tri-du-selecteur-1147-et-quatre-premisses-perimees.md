# #359-r2 — le tri du sélecteur de `1147`, et quatre prémisses périmées sur cinq

Tranche de cinq résidus (`#229-r2`, `#116-e`, `#359-r2`, `#264-pv`, `#264-r`). **Un seul décrivait
encore l'arbre** : les quatre autres énonçaient un manque déjà comblé, entre 8 et 12 jours plus tôt.
Le travail utile s'est donc déplacé de « porter ce qui manque » vers « garder ce qui a été porté » —
et dans trois cas sur quatre, **rien ne le gardait**.

---

## 1. Le seul port : le tri de `HadesAutocannonsAbility$$GetAllTargets` (#359-r2)

Le sélecteur finit par trois nœuds que le port n'avait pas. Le décompilé les donne, et **contredit
sur deux points la RE qui vivait dans la docstring du port** :

```
desc = IdunBattleLogic.Entities.DSLSelectors$$SortByRow(Tiles(w), 0, 0, false)
asc  = IdunBattleLogic.Entities.DSLSelectors$$SortReverse(desc)
return IdunBattleLogic.Entities.DSLSelectors$$If(
           IdunBattleLogic.Entities.DSLTriggers$$AreEqual(
               IdunBattleLogic.Entities.DSLSelectors$$CurrentPlayer(),
               IdunBattleLogic.Entities.DSLSelectors$$Player(1)),
           desc, asc)
```

### 1.1 `false` est `ascending`, donc la première branche est DÉCROISSANTE

Le ctor porte la carte des champs, nommée par Ghidra :

```
IdunBattle.Entities.Selectors.SortByRowSelector$$.ctor(
    this, tiles, state, pseudoRng, sameColumnIsRandom, additionalSortingFormula, ascending)
    +0x18 tiles · +0x20 pseudoRng · +0x28 sameColumnIsRandom
    +0x30 additionalSortingFormula · +0x38 ascending
```

et `IdunBattle.Entities.Selectors.SortByRowSelector$$Select` s'y branche :

```
ordered = (+0x38 == 0) ? OrderByDescending(src, key) : OrderBy(src, key)
if (+0x30 != 0) ordered = ThenBy(ordered, <formule>)
if (+0x28 != 0) ordered = ThenBy(ordered, <pseudoRng>)
return ordered.ToList()
```

La docstring nommait ce sélecteur `asc`. Sur un call-site qui passe `false`, c'est l'inverse. La
clé de tri est la ROW de la tuile principale : les deux lambdas
(`...SortByRowSelector.u003Cu003Ec__DisplayClass6_0$$u003CSelectu003Eb__0` et `...b__1`) ont le
**même corps** — elles résolvent `IdunBattle.Entities.EntityExtensions$$GetMainTileId` puis lisent
le champ row ; seul le sens diffère, porté par `ascending`. Côté port, `_entity_pos` **est** le
mirror de `GetMainTile`, d'où la même clé des deux côtés.

### 1.2 `Player(1)` prend une TEAM, pas un numéro de joueur

`IdunBattleLogic.Entities.DSLSelectors$$Player` nomme son paramètre `team` et le transmet à
`IdunBattle.Entities.Selectors.PlayersByTeamSelector$$.ctor(this, state, team)`. Sur un duel 1v1,
les deux lectures coïncident — **l'erreur aurait été invisible ici** et fausse dès qu'un camp compte
plusieurs joueurs. C'est la même forme de piège que l'ordinal juste par accident.

### 1.3 Ce qui est porté

| pièce | où |
|---|---|
| nœud `SortByRow` (4 champs du ctor mirrorés) | `engine/entities/selectors/geometry.py`, à côté de `SortReverse` qui existait déjà |
| prédicat `CurrentPlayerIsOfTeam` | `engine/entities/triggers.py` |
| canal `DslContext.current_player_team` (tri-état) | `engine/dsl/base.py` |
| câblage `_AOE` via `SelectIf` (= `DSLSelectors$$If`, déjà porté) | `engine/entities/abilities/active_ability.py` |
| alimentation du canal côté prédiction | `engine/playbook/prediction/abilities.py` |

**Un nœud composite plutôt que trois nœuds fidèles.** Le port n'a pas d'entité JOUEUR : ni
`CurrentPlayer` ni `Player(team)` n'auraient rien à rendre, et les écrire produirait un `AreEqual`
de deux `None` — **vrai par accident, pour les deux camps**. On mirrore donc la composition en la
nommant.

**Les deux options non exercées LÈVENT.** `sameColumnIsRandom` demande le `pseudoRng` du match,
`additionalSortingFormula` une formule `ThenBy`. Aucun call-site porté ne les pose. Les dégrader en
no-op produirait un ordre **inventé** que rien ne signalerait ; `NotImplementedError` est ce qui
force à lire le décompilé du call-site qui les posera.

### 1.4 Mesure

Rows choisies pour contredire l'ordre d'id ET l'ordre d'insertion :

```
team courante = 1     -> [6, 5, 4, 3]     (ascending = false -> OrderByDescending)
team courante = 2     -> [3, 4, 5, 6]     (SortReverse)
team NON MESUREE      -> [3, 4, 5, 6]     (False -> branche fausse, dégradation nommée)
```

Ensemble identique dans les trois cas ; branches exactement inverses. Contre-épreuve : inverser
`ascending` rougit les deux tests de sens ; ancrer sur team 2 rougit aussi.

### 1.5 Ce que ce port NE ferme PAS — `#359-r5`

L'écart d'ordre mesuré par #359 (natif `[113, 110, 116]`, port `[110, 113, 116]`) **ne vient pas du
tri**. `IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions` boucle sur le
sélecteur TEL QUEL, et `SurroundingUnits(..., includeCenter: 1)` y met la cible — d'où `110` en 2ᵉ
position. Le port, lui, **extrait** la cible principale (`aoe = [t for t in ab.get_aoe_targets(dctx)
if t["id"] != main_tgt_id]`) et l'émet en tête, **pour toutes les abilities AoE**. Le tri ne peut
donc réordonner que la queue. L'étage est partagé : le corriger pour 1147 seul le casserait
ailleurs.

Second résidu, `#359-r6` : `_current_player_team` est **dupliqué** de `engine.ai.context`.
`engine.ai.context` importe déjà `engine.playbook.prediction.abilities` (mesuré ; l'inverse est
faux), donc l'importer d'ici fermerait un cycle ; hisser la dérivation — l'option (1) de la
doctrine — exige d'éditer `ai/context.py`, gelé par une tranche en vol.

---

## 2. Les quatre prémisses périmées, et ce qu'il restait à faire

| résidu | ce qu'il affirmait | mesure | fermé par |
|---|---|---|---|
| `#229-r2` | `test_refresh_active_flag_discriminant_offline` **n'existe pas** | il existe, sous `scripts/python/tests/` | `de7da919` |
| `#264-pv` | la Scene LIVE **reconstruit** les traits | elle lit la mesure | `9f782d36` (#267) |
| `#264-r` | 2 fichiers live rouges par le montage | **8 passed / 4 passed**, 0 skip | `29db0029` (#268) |
| `#116-e` | l'effet 1550 est posé mais **INERTE** | vivant, 4/4 canaux aux deux seams | `8fe05a62` |

**Le vice commun des quatre n'est pas d'avoir été résolus sans qu'on le note** — c'est que trois
d'entre eux n'étaient **tenus par rien**, donc réversibles en silence.

### 2.1 `#229-r2` — un plancher littéral n'est pas un cliquet

La prémisse était fausse (`#427-r2` le disait déjà : la recherche avait porté sur `tests/` à la
racine, répertoire qui n'existe pas). Le vice réel était dans le fichier :

```python
assert len(overrides) >= 20      # plancher LITTÉRAL
```

Un seuil est **unidirectionnel** : il rougit quand une surcharge de `is_active` DISPARAÎT, jamais
quand une ARRIVE. Le fichier le constatait **deux fois** (« une classe entrée sans que le plancher
bouge ») sans pouvoir l'empêcher, et quatre commits l'ont remonté à la main (16, 17, 18, 20).
**Mesure à la reprise : plancher écrit 20, classes surchargeantes 21** — le cliquet était en retard
d'une, et VERT.

Remplacé par `CONDITIONS_PORTEES_ATTESTEES`, ensemble nommé, confronté dans les deux sens.
Contre-épreuve : un port neuf non attesté ROUGIT (l'ancien seuil : VERT) ; une surcharge disparue
ROUGIT.

**Effet de bord voulu : deux branches parallèles fusionnent par UNION.** C'est la réponse à
l'avertissement que le fichier portait (« ce plancher ne se choisit pas entre deux branches en
conflit ») : sur un NOMBRE, prendre 18 ou 17 est faux des deux côtés puisque les deux s'ajoutent ;
sur un ENSEMBLE, garder les deux lignes est la résolution évidente.

### 2.2 `#264-pv` — mesuré sur le porteur que la fiche nommait

`necroOverlord` porte `Resilient` au gameconfig et pas en bataille.

```
_hydrate_static_unit seul   -> ['Hero', 'LivingMetal', 'Mechanical', 'Resilient']   (kit)
+ _seed_measured_traits     -> ['LivingMetal']                                      (MESURE)
```

Les deux sites d'hydratation sont chacun suivis de leur seed. La ligne du backlog citait le code
d'avant #267.

### 2.3 `#264-r` — le diagnostic pressenti était le bon

La fiche disait « ça sent la migration de build, bornes de dégât dégénérées ». #268 a trouvé
exactement cela : **décodeur de prédiction périmé**. Les fixtures ÉCHOUENT désormais au lieu de
skipper — plus aucun skip dans les deux fichiers, ce qui est la doctrine #455 appliquée.

### 2.4 `#116-e` — un test qui ne vérifie que l'OUVERTURE ne voit pas un gate qui s'ouvre TOUJOURS

L'effet est vivant. Mais son seul garde
(`test_462_r4b_r1_r1_defender_additive_carriers_offline`) ne mesure que le gate **ouvert**
(magnitude non nulle et intégrale). **Neutraliser `AreFriends` le laisse VERT** — et l'effet majore
alors le dégât infligé par les ENNEMIS du Chronomancer, l'inverse exact de son sens.

L'arbre natif
(`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) :

```
trigger = get_OwnerIsTarget & IsUnit(caster@0x160)
                            & AreFriends(caster@0x160, EffectSource(Effect@0x150))
montant = Multiply( If( IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                    ConfigVar(8 = extraDmg) ),
                    TimesEffectApplied(Effect@0x150) )
kind    = ForAddition
```

Le membre DROIT d'`AreFriends` est le **POSEUR**, pas l'attaquant : c'est la raison d'être de la clé
`team_by_id`, et le seul point où une lecture distraite ferait comparer l'attaquant à lui-même — un
gate alors **toujours vrai**.

Sept régimes figés, magnitudes **re-dérivées du gameconfig** (seuls les rapports, les fermetures et
la linéarité sont assertés — un rebalancement ne doit pas rougir ici, un gate perdu si). Le fichier
ouvre par un test d'**anti-vacuité** : sans lui, un effet redevenu mort ferait passer les six gardes
de fermeture pour de bonnes raisons.

Contre-épreuve, attribution exacte :

| mutation | rougit |
|---|---|
| `AreFriends` compare l'attaquant à lui-même | `enemy` + `source_team`, rien d'autre |
| `IsMechanical` neutralisé | `mechanical`, rien d'autre |
| `Multiply(TimesEffectApplied)` neutralisé | `linear` + `zero`, rien d'autre |

### 2.5 Et une RE adversariale a trouvé un BUG que la re-mesure n'avait pas vu

La re-mesure du §2.4 dit « l'effet est vivant » — et elle a raison. Une **relecture indépendante du
décompilé**, lancée pour *confronter* le port et non pour l'écrire, dit autre chose :

```
IdunBattle.Entities.UnitExtensions$$IsMechanical(unit) =
    HasTrait(unit, 0x5) || HasTrait(unit, 0x3e8) || HasTrait(unit, 0x405)
    //     Mechanical=5      LivingMetal=1000        Vehicle=1029
```

Le site testait `"Mechanical" in (ac.get("traits") or ())`. **Trois traits, pas un.** Le raccourci
ne lève pas : il lit l'autre branche du `If` et rend `extraDmg` au lieu d'`extraDmg_2`.

**Et il rate précisément le régime le plus fréquent de cet effet** : `Chronometron` est une ability
NECRON (`necroChronomancer`), dont les alliés portent `LivingMetal` — pas `Mechanical`.

Le prédicat existait déjà en **trois exemplaires corrects**, chacun sur un substrat différent
(`behaviours/stats.py` sur le callable `has_trait` du DSL, `abilities/targeting.py` sur un `State` +
un id, le sélecteur `MechanicalUnits` qui délègue au premier). **Manquait celui du substrat le plus
simple** — un ensemble de NOMS déjà résolu, ce que porte `attacker_ctx["traits"]`. C'est cette
absence qui a fait recopier un raccourci à un trait plutôt qu'appeler un foyer. Ajouté dans
`entities/traits/unit_trait.py`, frère exact d'`is_normal_unit`.

Contre-épreuve, les trois traits testés **séparément** (un helper qui n'en couvrirait que deux
passerait un test qui les poserait ensemble) :

```
code AVANT le fix : Mechanical VERT · LivingMetal ROUGE · Vehicle ROUGE
code APRES le fix : Mechanical VERT · LivingMetal VERT  · Vehicle VERT
```

**La leçon** : la re-mesure « l'effet rend-il une magnitude ? » ne pouvait pas voir ce bug — elle
mesurait la **présence** d'une valeur, pas sa **justesse**. Il a fallu une lecture du natif *faite
pour contredire*. Une prémisse périmée ne veut pas dire qu'il n'y a rien à trouver.

Le balayage des autres sites testant le trait `5` rend **un candidat, pas zéro** :
`engine/ai/state_bridge.py::_is_machine` (résidu `#116-r1`) ; tous les autres sont corrects, le
natif y écrivant `HasTrait(unit, 5)` **nu** et le port documentant la distinction.

---

## 3. Ce que cette tranche enseigne sur le backlog

Quatre lignes sur cinq décrivaient un état de l'arbre vieux de 8 à 12 jours, et **trois d'entre
elles nommaient un porteur précis** (`necroOverlord`, les deux fichiers de test, l'`attacker_ctx`) —
ce qui les rendait vérifiables en quelques minutes. Le coût n'est pas la lecture périmée : c'est
qu'une ligne périmée **occupe un créneau de dispatch** et se lit comme du travail restant.

Le contrôle qui les a toutes tranchées est le même : **rejouer la mesure que la fiche décrit, sur le
porteur qu'elle nomme**, avant de lire une ligne de code. Deux minutes par résidu.

Et le corollaire, moins confortable : un résidu fermé sans cliquet **n'est pas fermé**. Trois des
quatre l'étaient de cette façon — le travail livré ici est très majoritairement de la garde, pas du
port.
