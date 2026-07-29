# Case 243 — les trois masques `splash` à `0x2004002`, confrontés live : **le clamp de mêlée**

Deux volets, dans cet ordre : **un test rouge sur `master`**, puis les trois masques que
`case-247` avait posés sur RE seule (`1051` `Stikkbomb`, `1078` `Fragstorm`, `1098`
`PlasmaGrenade`). Le premier était **causé** par la doctrine du second, mais pas par une erreur de
masque : par une hypothèse cachée du test.

## 1. Le test rouge — cause réelle, mesurée

`tests/engine/runner/test_summon_ability_ports_live.py::test_plasma_grenade_main_plus_splash`
échouait sur `origin/master` (`hits_main = None`, donc `diag["main_attack"] is None`).

Le montage prenait le **premier** membre de la première équipe comme caster, et une cible choisie
pour avoir un voisin ennemi — **sans jamais regarder la distance**. Mesure sur `--board MC1_67
--seed 777` (`_diag243_test`, reproduction du montage exact) :

| | valeur |
|---|---|
| caster | `u87` @ `(1, 0)` |
| cible | `u77` @ `(6, 8)` |
| **distance hex** | **11** |
| portée de 1098 | `constants.range` = **2** |
| gate PORT | `0x8000000` `TargetIsInRange` |

Tant que `PlasmaGrenadeAbility` n'avait pas de `TARGETING_OPTIONS`, `get_invalid_target_reason`
rendait `0` immédiatement (aucun gate) et la behaviour s'exécutait quand même. Depuis que le masque
est posé, `AbilityHandler.visit_ActiveAbilityMessage` **refuse** le cast — mirror exact de
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, qui sort avant le premier
`AActiveAbility.Execute`. Le diag rendu porte `invalid_target`, donc **pas** de `main_attack`.

⇒ **le masque est juste, l'hypothèse cachée du test était « le gate de cible n'existe pas ».**

### Correction — le montage, pas l'assertion

`_pick_target_with_adjacent_enemy` conduit désormais **aussi le caster** : il est placé sur une
tuile libre **adjacente** à la cible. Adjacent, et non à `d = 2`, parce que le preset de 1098 arme le
clamp de mêlée — or la cible elle-même est au contact : à `d = 1` les deux régimes (clampé ou non)
acceptent, le montage est stable quel que soit le voisinage.

Deux pièges rencontrés en route, tous deux corrigés :

- la sélection s'arrêtait à la **première** cible ayant un voisin ennemi. Sur `MC1_67`/777 c'est
  `u77`, qui n'a que **2 voisins, tous deux occupés** — aucune place pour le caster. La sélection
  balaie maintenant tous les candidats et retient celui qui satisfait **les deux** conditions ;
- l'échec de montage était un `pytest.skip`, donc **vert**. Il est devenu une assertion : le montage
  est conduit, « pas de cible » n'est plus une fatalité de déploiement mais un montage cassé.

Une garde explicite a été ajoutée avant l'assertion de structure : `assert diag["invalid_target"] is
None`, avec le message « corriger le MONTAGE, pas l'assertion ». Sans elle, un refus de gate se
manifestait par « attaque main absente », qui pointe la mauvaise pièce.

Après correction (`hits` lus, pas figés) : `hits_main = 2` (`constants.nrOfHits`),
`splash_hits = [1]` (`nrOfHits_2`), SET splash `[77, 81, 85]` == voisins `boardGraph` ∩ ennemis, et
la dérivation de clé tient (`nrOfHits_2` 1 → 3 ⇒ `splash_hits` [1] → [3], `main` inchangé).

## 2. Le discriminant que la mesure devait exercer

Les trois abilities portent le **même** `rules` effectif (`0x2000000 | 0x4002` = `0x2004002`) et le
**même** `TargetingRange` (`RANGE_FROM_CONFIG` → `constants.range` = 2). Le seul champ qui les
sépare est `<preset>+0x20` `forceMeleeTarget`, lu dans
`IdunBattle.Core.Services.TargetingOptions$$.cctor` :

| id | preset | `forceMeleeTarget` | clamp |
|---|---|---|---|
| 1051 `Stikkbomb` | `TargetingOptions statics+0x140` | `0` = `RangedBool.True` | **armé** |
| 1098 `PlasmaGrenade` | `statics+0x140` | `0` = `RangedBool.True` | **armé** |
| 1078 `Fragstorm` | **`statics+0x180`** | **`1` = `RangedBool.False`** | **désarmé** |

Ce que ce champ décide, dans `IdunBattle.Core.Services.TargetingQuery$$GetRange` :

```
if (RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)
    && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
    { v = Math.Min(1, v); onlyAdjacent = true; }
```

⇒ le montage discriminant est **un ennemi non-`Steppable` au contact du caster + une cible à
`d = 2`**. Une mesure qui n'exerce pas cette configuration ne valide que `rules`, identique aux
trois — elle ne dit rien du champ qui a motivé la lecture preset-par-preset.

## 3. Confrontabilité — la clé était `CanStillBeUsed`, et elle se lève

Les trois porteurs sont des **summons** (`orksOrkBoys`, `templSmnAggressor`, `eldarSmnGuardian`),
donc hors `--list-pool` par construction. `case-247` avait échoué par la voie « spawner le
summoner » : `Waaagh` (1058) rend 0 cible légale, et `AlphaWarrior` (1112) invoque bien mais aucune
unité ne rendait `abilityState.usable`.

Ce second symptôme n'était pas un mystère : c'est **le résidu déjà mesuré en case-245**.
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments, celle que le
RPC `abilityReason` invoque) commence par

```
ability = ActiveAbilityComponent.GetOrNull(<composant du caster>, abilityType);
if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0)
    return GenericBrokenTargetingRule(1);          // ValidRequest, cascade JAMAIS évaluée
```

et `ActiveAbility.CanStillBeUsed` vaut `false` sur les actives d'un porteur à trait `Summon` (mesuré
case-245 par balayage des 4 variantes de traits, même board/même seed). **Cause établie par
`case-250`** : le trait rend l'unité **automatique**, le moteur la joue et elle consomme sa charge.

La voie qui débloque le lot est donc celle que case-247 avait laissée « non tentée » : **catalogue
injecté** (`catalog_inject.augment` → `Units` **et** `Abilities`) + `initAndStart(playerUnits=[...])`,
avec les **deux mêmes aménagements** que case-245, et pas un de plus :

| champ | origine | montage | pourquoi |
|---|---|---|---|
| `Health` | `0` | `5000` | l'entrée d'un summon porte 0 (ses PV viennent des `summonHp` du summoner au spawn natif) ; spawné à la main il naîtrait à 1 PV. Aucune règle du filtre statique ne lit les PV |
| `Traits` | `…, Summon, …` | trait `Summon` **retiré** | il rend l'unité **automatique** (`case-250`) : le moteur la joue, elle consomme sa charge, `CanStillBeUsed` retombe à `false` et l'oracle court-circuite à `0x1`. Le retirer la rend **contrôlable** |

**Le retrait du trait ne peut pas déplacer un verdict de la cascade pour ces masques**, et ça se lit
au décompilé plutôt qu'à la mesure : les seules règles du filtre statique qui consultent un trait
portent sur la **cible** (`TargetIsSummon` `0x2000`, `TargetIsHero` bit 50, `TargetIsNotAnObject`
bit 33) et aucune n'est dans `0x2004002` ; le trait du **caster** n'entre que par
`RangedBoolExtensions$$IsTrue(IfRangedCaster / IfNotRangedCaster)`, or ces presets posent
`forceMeleeTarget` à une **constante** et `onlyAdjacent` vient de `RANGE_FROM_CONFIG`
(`RangedBool.False`, constante) — aucun des deux ne lit de trait. `ShouldApplyRangedInMelee` lit
`HasTrait(0x1b Steppable)` sur les **voisins de la cible**, pas sur le caster, et son gate
`HasTrait(0xb Ranged)` est court-circuité par `ignoreTrait = 1` au call-site de `GetRange`.

### Le piège du `visualId` — nommé par la fiche, rencontré tel quel

Le `VisualId` de l'entrée de catalogue d'un summon **n'est pas** son `Id` gameconfig :

| `Id` (catalogue, `playerUnits.unitId`) | `VisualId` (ce que `decisionView` expose) |
|---|---|
| `orksOrkBoys` | `orksNpc2OrkBoy` |
| `templSmnAggressor` | `templNpc4Aggressor` |
| `eldarSmnGuardian` | `eldarNpc1Guardian` |

Chercher le porteur par son id gameconfig rend « porteur **ABSENT** » alors que le spawn a bien eu
lieu — c'est ce qu'a produit le premier run du probe. La source est `catalog_inject.synthesize`, qui
mirror `BattleConfigBuilder$$GetUnitConfiguration` : `VisualId <- gameconfig.visualId or Id`. Le
probe résout donc le porteur par ce mapping, avec repli sur le **natif** (qui rend
`abilityState.usable`) si le mapping surprenait.

## 4. Mesure — `probe_243_splash_range_clamp.py`

Oracle = `abilityReason(casterId, abilityType, targetId)` →
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`. Le port est rejoué **sur le même
état figé**, en cinq versions : `APRÈS`, `AVANT` (`TARGETING_OPTIONS = None`, l'état d'avant
case-247), `sansRules`, `sansRange`, `fmtFlip`.

Les **trois** porteurs sont spawnés dans **un seul runner** (`MC1_67`, seed 777, 4 `necroWarden`) et
mesurés à tour de rôle, chacun avec **deux** géométries conduites (les ennemis sont déplacés vers le
caster courant, `applyAction` ne vérifiant pas la propriété du `unitId`) :

- **LIBRE** — ennemis à `d = 2, 3, 5, 6`, **aucun** au contact : le clamp ne mord pour personne, le
  seuil de portée est encadré des deux côtés ;
- **MÊLÉE** — un ennemi amené à `d = 1`, le premier restant à `d = 2` : c'est la ligne qui sépare les
  presets.

### Résultat — 84/84 sur **deux** couples, et le discriminant tombe

| couple | id | accord natif/port | casts illégaux fermés | seuil `d≤2` accepté / `d≥3` refusé | **cible `d=2`, ennemi au contact** |
|---|---|---|---|---|---|
| `MC1_67` / 777 | 1051 | **14/14** | 12 | 1 / 3 | `0x8000000` **REFUS** (clamp armé) |
| `MC1_67` / 777 | 1078 | **14/14** | 11 | 1 / 3 | `0x0` **ACCEPT** (clamp désarmé) |
| `MC1_67` / 777 | 1098 | **14/14** | 12 | 1 / 3 | `0x8000000` **REFUS** (clamp armé) |
| `C4_09` / 31337 | 1051 | **14/14** | 12 | 1 / 3 | `0x8000000` **REFUS** |
| `C4_09` / 31337 | 1078 | **14/14** | 11 | 1 / 3 | `0x0` **ACCEPT** |
| `C4_09` / 31337 | 1098 | **14/14** | 12 | 1 / 3 | `0x8000000` **REFUS** |

Même runner, même géométrie, même tour : **le seul champ qui varie entre 1078 et ses deux voisines
est `forceMeleeTarget`**, et le natif bascule exactement là où le décompilé le place. Les
contrefactuels sont identiques sur les deux couples, `fmtFlip` compris (1/14 chacun).

Lignes-clés (`MC1_67`/777) :

| ability | montage | cible | `d` | natif | port `APRÈS` | port `AVANT` | `fmtFlip` |
|---|---|---|---|---|---|---|---|
| 1051 | libre | ennemi | 2 | `0x0` | `0x0` | `0x0` | `0x0` |
| 1051 | libre | ennemi | 3 | `0x8000000` `TargetIsInRange` | idem | **`0x0`** | `0x8000000` |
| 1051 | **mêlée** | ennemi | **2** | **`0x8000000`** | idem | **`0x0`** | **`0x0`** |
| 1051 | mêlée | ennemi | 1 | `0x0` | `0x0` | `0x0` | `0x0` |
| 1078 | **mêlée** | ennemi | **2** | **`0x0`** | `0x0` | `0x0` | **`0x8000000`** |
| 1098 | **mêlée** | ennemi | **2** | **`0x8000000`** | idem | **`0x0`** | **`0x0`** |
| ×3 | les deux | allié / le caster | 0–1 | `0x4000` `TargetIsEnemy` | idem | **`0x0`** | `0x4000` |

### Contrefactuels — chaque champ est démontré porteur

Comptés comme **lignes divergentes dans les deux sens** (neutraliser un champ peut faux-accepter
comme faux-refuser) :

| champ neutralisé | 1051 | 1078 | 1098 | ce que ça prouve |
|---|---|---|---|---|
| `rules = 0` | 6/14 | 6/14 | 6/14 | `TargetIsEnemy` porte le refus des cibles amies et du self-cast |
| `range = None` | 6/14 | 5/14 | 6/14 | le volet portée porte les `TargetIsInRange` |
| `force_melee_target` basculé | **1/14** | **1/14** | **1/14** | **exactement** la ligne « cible `d=2`, ennemi au contact » — dans un sens pour 1051/1098 (faux-accept), dans l'autre pour 1078 (faux-refus) |
| `TARGETING_OPTIONS = None` | 12/14 | 11/14 | 12/14 | la dégradation permissive fermée par le masque |

**Aucun champ inerte** sur les trois. C'est le point qui manquait à case-247, où
`force_melee_target` de 1105/1065 restait explicitement « non validé par la mesure ».

**Volet CASTER** : `casterReason` natif = `0` sur toutes les lignes, port `0x0` — aucun de ces
masques ne pose `CasterHasNotMoved`.

### Contre-épreuve — la garde mord

Le masque de **1078** a été temporairement remplacé par celui de sa voisine
(`force_melee_target = RangedBool.True`, c'est-à-dire *exactement* l'erreur que la lecture
preset-par-preset avait évitée), et `test_splash_range_clamp_live.py` a été rejoué :

```
FAILED test_accord_natif_port[1078]
    desaccord natif/port sur 1078 : [('melee', 'ENNEMI necroWarden', 2, '0x0', '0x8000000')]
FAILED test_clamp_de_melee_le_champ_qui_separe_les_trois[1078]
```

Une seule ligne des 14 diverge — et c'est celle du discriminant. La garde échoue sur son
**assertion de fond** (accord natif/port), pas seulement sur le contrôle de forme du champ. Masque
restauré, 18/18 de nouveau au vert.

## 5. Artefacts

- port (marqueurs `NON CONFRONTE LIVE` **levés**) :
  `scripts/python/engine/runner/abilities/loki/splash.py`
- probe (MESURE) : `scripts/python/probe_243_splash_range_clamp.py`
  (`--only Stikkbomb|Fragstorm|PlasmaGrenade`, `--seed`, `--board`)
- test (GARDE) : `scripts/python/tests/engine/runner/test_splash_range_clamp_live.py` (18 tests)
- test corrigé (volet 1) : `scripts/python/tests/engine/runner/test_summon_ability_ports_live.py`
- cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py`
  (les trois notes « posé sur RE seule » remplacées par le verdict mesuré)

## 6. Ce qui n'est PAS couvert

- ~~**1065 `ScythingTalons`**~~ — **RÉSORBÉ par `case-250`** : confronté live sur son porteur réel
  `tyranSmnWarrior` (déjà au catalogue, donc sans injection), 6/6 d'accord natif/port, seuil encadré
  des deux côtés, trois contrefactuels portants. Le module `splash` est intégralement mesuré.
- ~~**`AActiveAbility$$CanStillBeUsed`**~~ — **EXPLIQUÉ par `case-250`**, et la chaîne candidate
  citée ici était fausse : le slot virtuel `+0x3d8` est `GetCooldownAfterUse`, il ne lit aucun
  trait. La cause réelle est que le trait `Summon` (`UnitTrait` 2) rend l'unité **automatique**
  (`IdunBattle.Entities.UnitExtensions$$IsAutomatic`) : le moteur la joue lui-même
  (`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`), elle consomme sa charge, et
  `CanStillBeUsed` retombe à `false` par l'**usage**
  (`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`). Le retrait du trait ne lève
  donc pas un gate : il rend l'unité **contrôlable**, donc interrogeable avant qu'elle ait casté.
- **La règle dynamique** (`TargetMatchesDynamicRule`, bit 1) des trois masques : le port rend `0`
  (défaut permissif). Si l'une surchargeait `GetDynamicInvalidTargetReason`, le port accepterait des
  cibles que le natif refuse. La mesure ne peut pas trancher ici — aucune des 42 lignes n'exhibe de
  refus imputable au bit 1 — mais elle borne l'écart : sur cet état, **zéro** divergence.
- **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portée ; sans conséquence *dans ce
  sens*, le bit `AllowObscuredTargetByElevation` la désarmant côté natif.
- **Deux couples (board, seed) mesurés** — `MC1_67`/777 et `C4_09`/31337 — mais le test de garde
  n'en rejoue **qu'un** (`MC1_67`/777, `P.SEED`/`P.BOARD`) : le montage coûte un build à catalogue
  injecté plus deux géométries conduites par ability. Le second couple est reproductible d'une
  ligne (`probe_243_splash_range_clamp.py --board C4_09 --seed 31337`), il n'est pas automatisé.
- **Les 42 lignes par couple sont toutes des cibles UNITÉ.** Aucune cible TUILE n'est exercée : ces
  masques ne posent pas `TargetIsTile`, donc la tête de domaine de la cascade
  (`get_target_domain_broken_rule`) reste sur la branche `TargetIsUnit`, non discriminée ici.
- **La face COMBAT** (behaviours splash) est hors périmètre : ce cas ne traite que le gate de cible.
  Le seul point de contact est le test du volet 1, dont le montage devait devenir légal.

## 7. La leçon transférable

Un masque « posé sur RE seule » n'est pas seulement non gardé : il est **indistinguable d'un masque
faux tant qu'un montage n'exerce pas le champ qui le distingue de ses voisins**. Ici, `rules` et
`range` étaient identiques aux trois — n'importe quelle mesure les aurait validés ensemble, et aurait
laissé passer une erreur sur `forceMeleeTarget`, c'est-à-dire précisément l'erreur que la lecture
preset-par-preset avait servi à éviter. **Le montage doit être choisi pour séparer les items, pas
pour les confirmer.**

Corollaire opérationnel : quand un lot bute sur « le porteur n'est pas confrontable », relire les
**résidus déjà mesurés** avant de conclure. Ici la clé (`CanStillBeUsed` éteint chez un porteur à
trait `Summon`) était écrite dans case-245 depuis le début, avec sa parade — mais sa **cause** ne
l'était pas, et l'explication héritée était fausse : `case-250` a dû la reprendre au décompilé.
