# #478 — `GetAdditionalDamageBehaviour` a **DEUX** consommateurs, et le port n'en jouait aucun

Résidu §7 de `case-446-r3b-fealty-talon-asymetrie.md`. La fiche parente demandait « un câblage
COMBAT, pas une RE de sélecteur ». **La prémisse est fausse sur deux points**, et c'est la mesure
qui les a imposés — pas une relecture de confort.

## 1. Ce qui a été rectifié

| la fiche parente disait | ce que le décompilé + la mesure établissent |
|---|---|
| « `GetAdditionalDamageBehaviour` a un **UNIQUE** consommateur » | il en a **DEUX**. Le second, `$$GetCustomNormalAttackBehaviour`, frappe la cible **PRIMAIRE** |
| « les **quatre** ont la même forme d'exécution » | la gate est **INVERSÉE** pour `Boltstorm` : il cleave sur `IsMelee == 0` |
| « c'est un câblage, pas une RE de sélecteur » | les quatre sélecteurs sont **distincts**, dont deux par la **surcharge** de primitive appelée (xrefs mesurées) |

## 2. L'artefact, relu sur `rnca9r7q6c`

```
<X>_NormalAttackAbility$$ExecuteBehaviour(abilityState, entities):
    weapon = ALoki_NormalAttackAbility$$FindAttackWeapon(entities)
    if (weapon == null) return 0
    <GATE D'ARME>  ->  Execute<X>(abilityState, entities, weapon)
    sinon          ->  la voie SANS cleave

<X>_NormalAttackAbility$$Execute<X>(abilityState, entities, weapon):
    sel = <X>Ability$$GetAdditionalTargets(dsl [, Direct(weapon.Range)])
    ALoki_NormalAttackAbility$$ExecuteInformWeapon(weapon, entities, null)
    ALoki_NormalAttackAbility$$ExecuteNormalAttack(abilityState, entities, weapon)
    b = IdunBattleLogic.Entities.DSLBehaviors$$Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))
    IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic(b, entities, 0x2a)
    return ALoki_NormalAttackAbility$$ExecuteTriggerAbilities(entities, weapon)
```

et, **dans** l'attaque primaire (vslot `0x4a8`, appelé par `ExecuteNormalAttack` et passé en 5ᵉ
argument à `$$GetAttackDamageBehaviour`) :

```
<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour(abilityState):
    return IdunBattleLogic.Entities.DSLBehaviors$$If(
               <cond>, GetAdditionalDamageBehaviour(abilityState, Target@0x60), null)
```

| ability | gate du **CLEAVE** (arme) | `$$GetCustomNormalAttackBehaviour` | gate du **FOLD primaire** (position) |
|---|---|---|---|
| `Fealty` | `IsMelee` | **absent** | — |
| `TalonOfHorus` | `IsMelee` | **absent** | — |
| `RighteousRepugnance` | `IsMelee` | présent | `<DSLTriggers+0x18>` = **IsMeleePosition** |
| `Boltstorm` | **`!IsMelee`** | présent | `DSLTriggers$$IsRangedPosition` = `op_LogicalNot(<+0x18>)` |

`<DSLTriggers+0x18>` est nommé par le corps **trivial** de `IdunBattleLogic.Entities.DSLTriggers$$IsRangedPosition`,
littéralement `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot(this+0x18)` — l'appariement forcé déjà
établi par #389 (`entities/triggers.py`). Son `ShouldTrigger` invoque le slot 9 d'`IBattleQuery`
(`IdunBattle.Core.Services.BattleQuery$$AreUnitsInMelee`), foyer porté
`services.battle_query.are_tiles_adjacent`.

⇒ **L'asymétrie attestée par #446-r3b a maintenant une CAUSE nommée** : ce n'est pas « la prédiction
attribue ce que le combat ne fait pas », c'est qu'un **symbole existe pour deux abilities et pas pour
les deux autres**. Et la prédiction (`$$GetAdditionalDamagePrediction`, portée par
`playbook/prediction/normal_attack.py`) est le mirror **de ce second artefact**, pas du cleave. Le
texte i2 dit la même chose : `RighteousRepugnance` porte « **to the target** and to all enemy units
adjacent to both », `TalonOfHorus` ne porte que le second volet.

## 3. Les quatre sélecteurs — lus un par un, jamais généralisés

Carte `DSLSelectors` (deux voies indépendantes, déjà au port) : `+0x30 Owner · +0x48 Caster ·
+0x50 CasterTile · +0x58 CasterTiles · +0x60 Target · +0x78 TargetTiles`.

```
FealtyAbility$$GetAdditionalTargets      = AdjacentEnemies(Caster@0x48, CasterTiles@0x58)
                                         & AdjacentFriends(Target@0x60,  TargetTiles@0x78)
                                         − Target@0x60                    <-- op_Subtraction EXPLICITE
TalonOfHorusAbility$$GetAdditionalTargets= AdjacentEnemies(Caster@0x48, CasterTile@0x50)
                                         & AdjacentFriends(Target@0x60,  TargetTiles@0x78)
RighteousRepugnanceAbility$$…            = AdjacentEnemies(Caster@0x48, unique, sel 3)   <-- AUTRE surcharge
                                         & AdjacentUnits (Target@0x60,  unique, sel 3)
BoltstormAbility$$…(dsl, range)          = SurroundingEnemies(Owner@0x30, range, unique, 3)
                                         & Unobscured(Owner@0x30, Enemies(Caster@0x48,
                                                      AdjacentUnits(Target@0x60, unique, 3)))
```

Les **deux** surcharges d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies` sont distinctes,
et ce sont les **xrefs entrantes** qui disent laquelle chaque ability appelle (jamais l'œil) :

```
AdjacentEnemies(this, unit, unitTile, unique) = Enemies(unit, Units(AdjacentTiles(unitTile)) − unitTile)   <- Fealty, TalonOfHorus
AdjacentEnemies(this, unit, unique, selType)  = Enemies(unit, Units(AdjacentTiles(unit))     − unit)       <- RighteousRepugnance
```

## 4. Ce que le port livre, et où

* `scripts/python/engine/runner/abilities/loki/additional_targets.py` — les quatre arbres, la table
  `NORMAL_ATTACK_CLEAVES` (clé = le **passif**, même substrat d'ENTITÉ que la cascade
  `custom_normal_attack`), les deux gates, et les deux volets ;
* branchement dans `DamageHandler.visit_AttackUnitMessage`, **au rang du natif** : après
  `AttackDamageOperation.execute` (donc après son `FinishAttack`/`On(9)`) et avant
  `after_hit_normal_attack` (`On(0x26)`).

Feuille commune : `AttackWithAttackDamage` en mode **BORNES** — `amount = RandomAmount(var 0xc, var
0xd)`, `hits = Direct(GetNumberConstant(0x2f))`, `profile = GetDamageProfile()`, `options` **zéroée**
(ni `alwaysOverkilled`, ni `alwaysCrit`, ni le drapeau d'attaque normale). La config lue est celle du
**PASSIF**, au niveau du **PASSIF** (`level_slot="passive"`) : `UnitFactory$$AddNormalAttackAbility`
monte l'attaque substituée avec le `triggeredAbilityState`.

⚠ `Foreach`, jamais `multi=True` : le natif enveloppe **chaque** cible dans son propre
`AttackBehaviour`, donc l'`OrderBy(b__5_0)` d'`AttackBehaviour$$Execute` ne s'applique pas. Un tri
par id déplacerait la consommation RNG dès deux cibles.

## 5. La mesure — quatre étages, et c'est le 4ᵉ qui a trouvé le volet manquant

Replay-diff (même état, même MT via `dumpRng`), lu **delta de PV PAR UNITÉ** puis **par COUP** :

| étage | ce qu'il sépare |
|---|---|
| 0 | l'attaque primaire a eu lieu, et son delta est le même des deux côtés |
| 1 | le **cardinal** des cibles additionnelles == celui qu'un oracle géométrique **écrit à la main depuis la RE** impose |
| 2 | le **montant** par cible additionnelle, unité par unité |
| 3 | la **ventilation par coup** sur la cible primaire : `coups d'arme + coups de fold` du port == la suite des `Amount` natifs, **dans l'ordre** |

C'est l'étage 3 qui a rendu le second volet inévitable. Sur `adeptMorvenn`, cardinal 0 (donc rien à
cleaver), le natif émettait `787, 969` (`ActiveAbilityType 1182`) **puis** `502, 506, 557`
(`Active_Ability_Type` nul, la signature d'un `AttackDamageBehaviour`) — **1565 PV** que le port
n'infligeait pas. Un port qui n'aurait comparé que le total aurait cherché un facteur.

Et l'ORDRE est load-bearing : avant que le fold primaire ne soit porté, le cleave d'`adeptMorvenn`
appliquait à sa cible ADDITIONNELLE les rolls `502, 506, 557` que le natif applique à la cible
**PRIMAIRE** — les bons montants sur les mauvaises cibles.

### Chiffres livrés (montage `MC1_67` / seed `4463111`, un état VIERGE par porteur)

| régime | porteur | natif primaire | natif additionnelles | port |
|---|---|---|---|---|
| `one` | `ultraTitus` (`Fealty`) | 2493 | `necroWarden` **3104** | identique |
| `one` | `blackAbaddon` (`TalonOfHorus`) | 3681 | `necroWarden` **4835** | identique |
| `one` | `adeptMorvenn` (`RighteousRepugnance`) | 3321 (dont **1565** de fold) | — (cardinal 0) | identique |
| `two` | `ultraTitus` | 2493 | `necroWarden` 3104 + `astraCreed` **2894** | identique |
| `two` | `blackAbaddon` | 3681 | `necroDestroyer` 3224 + `necroSpyder` **3038** | identique |
| `rr` | `adeptMorvenn` | 3321 | `necroWarden` **1820** | identique |
| `boltstorm` | `templAggressor` | 3249 (dont **1584** de fold, gate RANGED) | — (cf. §7) | identique |

**Un état VIERGE par porteur n'est pas du confort** : joués à la suite sur le même runner, les deux
premiers casts sont bit-exacts et le **troisième** diverge (natif 7830 / port 2081, avec une cible
additionnelle qui *regagne* 6000 PV) — un canal d'état ouvert par les casts précédents, étranger au
cleave. `rl_duel build` sur le même state-file **remplace** le runner : le budget partagé reste à 1.

## 6. Le second cas discriminant, et les contre-épreuves

La géométrie hex **borne** le cardinal : deux tuiles adjacentes ont exactement deux voisins communs,
donc un porteur au contact de sa cible a **au plus 2** cibles additionnelles. Les régimes couvrent
les trois cas — **0** (`ultraTitus` en `rr`, `adeptMorvenn` en `one`), **1** (`one`, `rr`), **2**
(`two`) — et le test le **vérifie** (`test_les_trois_cardinaux_sont_couverts`). Sans cela, « le port
rend le bon total » ne distinguerait pas un sélecteur porté d'une constante calée sur un montage.

`port_only(bundle)` rejoue le port OFFLINE sur l'état **pré-cast** capturé : une contre-épreuve ne
coûte donc **ni runner ni cast live**. Quatre mutations, **toutes mordantes**, plus un bras témoin
(le re-jeu SANS mutation doit reproduire la passe) :

| mutation | mesuré |
|---|---|
| ordre des deux volets **inversé** | `adeptMorvenn` **3576 / 1565** au lieu de 3321 / 1820 — les rolls s'échangent entre primaire et additionnelle |
| registre de dispatch **vidé** | rouge sur les deux porteurs à volet non vide |
| fold primaire **greffé** sur `TalonOfHorus` (le geste « par cohérence ») | rouge |
| gate d'arme **inversée** sur `TalonOfHorus` | rouge (cleave vidé) |

## 7. Résidus NOMMÉS

* **`#478-r4` — le CLEAVE de `Boltstorm` est NON CONFRONTÉ.** Son arbre ancre sur `Owner@0x30`
  (`SurroundingEnemies(Owner, range)` **et** `Unobscured(Owner, …)`), un slot que l'`AbilityEntities`
  d'une attaque **normale** ne renseigne pas. MESURE : dans un montage où les trois gates
  géométriques sont satisfaites (deux ennemis adjacents à la cible, à portée 2, non obscurcis), le
  natif ne frappe **aucune** cible additionnelle — là où le **même** montage fait cleaver `Fealty` et
  `TalonOfHorus`, qui ancrent sur `Caster@0x48`. Le port mirrore le slot **littéralement**
  (`OwnerSlot`, **sans** le repli sur le caster du nœud partagé `Owner()`) : avec le repli, il
  frappait deux cibles — **+2380 PV** de régression qu'aucun test n'aurait vue. La cause du zéro
  natif n'est **pas tranchée** : « `Owner` est nul sur cette voie » est l'hypothèse compatible avec
  les deux mesures, elle n'est pas lue. Le volet FOLD PRIMAIRE de `Boltstorm`, lui, **est** confronté
  (gate `IsRangedPosition`, 1584 PV).
* **`#478-r1` — `CasterTile@0x50` et `CasterTiles@0x58` sont collapsés** sur le même nœud
  `CasterTile()` (= l'empreinte). Le natif choisit `+0x58` pour `Fealty`, `+0x50` pour
  `TalonOfHorus` : deux instances distinctes du même type dans `DSLSelectors$$InitializeShared`.
  Inerte pour toute unité MONO-hex (les deux rendent la même unique tuile) ; aucun porteur confronté
  n'est multi-hex.
* **`#478-r2` — `CalibaniteGreatsword_NormalAttackAdditionalDamageAbility$$GetAdditionalTargetsAttackBehavior`**
  porte le **même** corps, mais c'est une TRIGGERED (`Abilities.Triggered.Loki`), pas une attaque
  normale substituée : elle n'entre pas dans la cascade `UnitFactory$$AddNormalAttackAbility` et
  reste hors de cette tranche.
* **`#478-r3` — le site de branchement ne couvre que la voie MESSAGE.** Les ~11 portes qui appellent
  `AttackDamageOperation.execute` directement (overwatch, `UseActiveAbility`, summon AI,
  `ControlEdict`…) ne déclenchent ni cleave ni fold. **Jumeau exact du résidu de MV71**, non nommé
  jusqu'ici : le natif n'a qu'un site parce que l'ability EST le corps de l'attaque normale.
* **Non couvert** : les unités MULTI-hex (le `− Target` de `Fealty` et le couple
  `CasterTile`/`CasterTiles` n'y sont pas discriminés) ; le régime `weapon == null` ; un montage à
  **trois camps** (qui seul séparerait `AdjacentFriends(Target, reference=Target)` d'un
  `AdjacentEnemies(Target)`) ; l'axe `ExtraPierceMelee`/`ExtraPierceRanged` du fold, threadé depuis
  l'arme choisie mais inerte sur les porteurs confrontés (leurs stats de perçage extra sont nulles).

## 8. Livré

* `scripts/python/engine/runner/abilities/loki/additional_targets.py` — les deux volets, quatre
  sélecteurs, deux gates, table de dispatch par la cascade native.
* `scripts/python/engine/runner/operations/damage.py` — branchement au rang du natif.
* `scripts/python/probe_478_cleave_additional_targets.py` — quatre régimes, oracle géométrique écrit
  à la main, ventilation par coup, `port_only` pour les contre-épreuves.
* `scripts/python/tests/engine/test_478_cleave_live.py` — **10 gardes**, dont les quatre
  contre-épreuves et leur bras témoin.
* `scripts/python/tests/engine/test_446_r3b_fealty_talon_live.py` re-joué **vert** : la face
  DÉCISION reste sans attribution pour `Fealty`/`TalonOfHorus`.
