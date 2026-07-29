# Case 250 — les cinq masques de ciblage du module `tau`, et le contre-exemple *intra-porteur*

Les cinq abilities `tau` du registre entraient dans `ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`.
`get_invalid_target_reason` / `get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`)
commencent par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement**
quand c'est `None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en
self-play.

## 1. Les cinq ctors, lus un par un

| id | ability | porteur | forme de ctor | `rules` **effectives** | `TargetingRange` | `AbilityAttackType` |
|---|---|---|---|---|---|---|
| 1077 | `EarlyWarningOverride` | `tauCrisis` (HERO) | **3 — preset statique copié** | `0x8004` | `statics+0x60` = `RANGE_SELF` | 2 `Others` |
| 1081 | `FightingRetreat` | `tauDarkstrider` (HERO) | 1 — flags directs | `0x802` | `statics+0x30` = `RANGE_ADJACENT` | 2 `Others` |
| 1082 | `InspiredToGreatness` | `tauAunShi` (HERO) | 1 — flags directs | `0x402` | `statics+0x30` = `RANGE_ADJACENT` | 2 `Others` |
| 1160 | `HeavyRailRifle` | `tauBroadside` (MoW) | 1 — flags directs | `0x10400040004000` | `statics+0x48` = `RANGE_WHOLE_BOARD` | 0 `DirectTargetAttack` |
| 1161 | `TwinSmartMissileSystem` | `tauBroadside` (MoW) | 1 — flags directs | `0x40004000` | `statics+0x48` = `RANGE_WHOLE_BOARD` | 0 `DirectTargetAttack` |

`forceMeleeTarget` = `1` = `RangedBool.False` **pour les cinq**. `ABILITY_ATTACK_TYPE` était déjà
posé et juste pour les cinq (3ᵉ argument d'`AActiveAbility..ctor`) — aucun changement requis.

### 1077 — la forme **PRESET STATIQUE COPIÉ**, la seule du module

`IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$.ctor` **n'appelle
aucun** `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les **0x40 octets** du champ
statique de `TargetingOptions` à l'offset **`+0x280`** du bloc `<class>+0xb8`, puis
`AActiveAbility..ctor(this, &opts, 2, 0)`. Aucun littéral de masque n'est visible dans le ctor.

Le preset lu **en entier** dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`, bloc
`statics+0x280` :

| champ | offset | valeur | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x280` | `1` | **self-cast** |
| `range` | `<preset>+0x08` | copie de `TargetingRange statics+0x60` | **`RANGE_SELF`** (`overrideRange = Nullable(0)`) |
| `forceMeleeTarget` | `<preset>+0x20` = `statics+0x2a0` | `1` | `RangedBool.False` |
| `rules` | `<preset>+0x28` = `statics+0x2a8` | **`0x8004`** | les deux bits ci-dessous |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

### Décompositions **exhaustives** (aucun bit résiduel)

`TargetingRange$$.cctor` relu à l'occasion, bloc par bloc : `+0x00` adjacent-si-mêlée, `+0x18`
from-config, `+0x30` `onlyAdjacent = RangedBool.True` + `overrideRange = Nullable(1)`, `+0x48`
`useWholeBoard = true` (l'octet `+0x4c` vaut `0x100` : `useRangeFromConfig = false` en `+0x04`,
`useWholeBoard = true` en `+0x05`), `+0x60` `overrideRange = Nullable(0)`. Ligne par ligne conforme
à la table du port.

**`0x8004`** (1077) = `0x4 + 0x8000` :

| bit | masque | nom | volet | porté |
|---|---|---|---|---|
| 2 | `0x4` | `CasterMatchesDynamicRule` | **CASTER** (délégué `options+0x30`, slot vtable `+0x470`) | non |
| 15 | `0x8000` | `CasterIsPossibleTarget` | **déclaratif** — n'apparaît dans aucune des deux cascades | s.o. |

⇒ **aucune règle de refus du filtre CIBLE**. Tout le refus de 1077 vient de son `TargetingRange`.

**`0x802`** (1081) = `0x2 + 0x800` :

| bit | masque | nom | volet | porté |
|---|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | point d'extension → `FightingRetreatAbility$$GetDynamicInvalidTargetReason` | non (§4) |
| 11 | `0x800` | `AddCasterIfAtLeastOneTarget` | lu **uniquement** par `TargetingQuery$$GetCasterNotAddedReason` | non (§4) |

**`0x402`** (1082) = `0x2 + 0x400` :

| bit | masque | nom | volet | porté |
|---|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | → `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` | non (§4) |
| 10 | `0x400` | `TargetIsFriendly` | filtre CIBLE, **règle de CAMP** | **oui** |

**`0x10400040004000`** (1160) = `0x4000 + 0x40000000 + 0x400000000000 + 0x10000000000000` :

| bit | masque | nom | volet | porté |
|---|---|---|---|---|
| 14 | `0x4000` | `TargetIsEnemy` | filtre CIBLE (`UnitsCanAttackEachOther`) | **oui** |
| 30 | `0x40000000` | `AllowNullCasterTile` | CASTER — **assouplissement** (désarme le refus « casterTiles vide ») | non, et sans effet (la clause désarmée n'est pas portée) |
| 46 | `0x400000000000` | `TargetIsActor` | **tête de DOMAINE** — élargit la cible à unité **OU** machine | **oui** (§3) |
| 52 | `0x10000000000000` | `CasterHas2TurnsLeft` | CASTER — `BattleQuery$$HasMinimumRemainingTurns(caster, 2)` | non (§4) |

**`0x40004000`** (1161) = `0x4000 + 0x40000000` : `TargetIsEnemy` + `AllowNullCasterTile`, **rien
d'autre**.

## 2. Le contre-exemple qui interdit de généraliser — et il est *intra-porteur*

`case-245` opposait deux abilities du même **module** ; ici, 1160 et 1161 sont portées par la **même
machine** (`tauBroadside`), sortent de la **même forme de ctor**, partagent le **même
`TargetingRange`** — et ont deux masques distincts. Les deux bits d'écart (46 et 52) ne sont pas
décoratifs :

* **bit 46 `TargetIsActor`** — mesuré : `abilityTargets` liste la MoW **ennemie** dans les cibles
  légales de 1160 (`now[4]: u84, u86, u88, u90`) et **pas** dans celles de 1161 (`now[3]: u84, u86,
  u88`). L'oracle `abilityReason` confirme, sur les deux couples : MoW ennemie → 1160 **`0x0`**,
  1161 **`0x200000000000 TargetIsUnit`** ;
* **bit 52 `CasterHas2TurnsLeft`** — cohérent avec la mécanique **2-phases** de 1160 (le dégât
  arrive au tour suivant, porté par l'effet `HeavyRailRifle_PendingAttack`).

Recopier le masque de la voisine aurait donc été faux **dans les deux sens**.

## 3. Ce que ce cas a dû porter en plus du masque : la **tête de domaine** (bits 44/45/46)

Le bit 46 est dans le masque de 1160 : il n'était pas mesurable tant que le port ignorait la tête de
cascade. Extrait VERBATIM de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
(surcharge 7 arguments), **avant** la branche `TargetIsTile` et avant toute autre règle :

```c
if (!(rules & TargetIsTile)) {
    if (!(rules & TargetIsMachine)) {
        if (!(rules & TargetIsActor)) { t = GetUnit(target); if (t == null) broken(TargetIsUnit); }
        else                          { t = GetUnit(target); if (t == null) goto machine; }
    } else { machine: t = GetMachine(target); if (t == null) broken(TargetIsMachine); }
}
```

`TargetIsUnit` (bit 45) n'est **gaté par aucun flag** : c'est le refus par défaut. `TargetIsActor`
ne rajoute donc pas une règle, il **élargit** le domaine.

Porté dans `get_target_domain_broken_rule` (`engine/runner/abilities/targeting.py`), et **seulement
là où le port sait décider** : une MoW est prouvée machine par son `MachineComponent`
(`snapshot._load_machines`), une unité est prouvée unité par `UnitComponent` **sans**
`MachineComponent` — le port pose un `UnitComponent` sur les deux, d'où l'exclusion explicite. Une
cible que le port ne résout ni en unité ni en machine (id de tuile, entité absente) laisse la règle
**muette** : permissif, comme tout le module.

Avant ce port, les lignes « cible = MoW » divergeaient sur les **quatre** abilities unit-target du
lot (1077, 1081, 1082, 1161) : le natif rendait `TargetIsUnit`, le port rendait `0x0` — ou pire,
refusait pour la **mauvaise raison** (1082 rendait `TargetIsFriendly` sur la MoW ennemie, 1161
`TargetIsEnemy` sur elle-même). Après, accord parfait.

## 4. Les résidus, nommés — et **mesurés** inertes ou actifs

| résidu | symbole | statut mesuré |
|---|---|---|
| règle dynamique de 1081 | `...FightingRetreatAbility$$GetDynamicInvalidTargetReason` | **ouvert**, inerte dans ces deux montages |
| règle dynamique de 1082 | `...InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` | **ouvert et ACTIF** : 2 lignes / 8, sur les deux couples |
| `CasterMatchesDynamicRule` (1077) | `TargetingQuery$$GetInvalidCasterReason`, clause `rules & 4` | **inerte** : `casterReason` natif = 0 sur toutes les lignes |
| `CasterHas2TurnsLeft` (1160) | `BattleQuery$$HasMinimumRemainingTurns` | **inerte** : `casterReason` natif = 0 (le runner n'a pas de plafond de tours ⇒ la fonction rend `true` dès que `maxTurns` n'a pas de valeur) |
| `AddCasterIfAtLeastOneTarget` (1081) | `TargetingQuery$$GetCasterNotAddedReason` | non porté (rend 0) ; natif = 0 sur la ligne self des deux couples |
| `AllowNullCasterTile` (1160/1161) | clause `IsNullOrEmpty(casterTiles)` de `GetInvalidCasterReason` | sans objet : la clause qu'il **désarme** n'est pas portée |
| ligne de vue | `TargetingQuery$$GetTilesObscuringTerrain` | non portée (résidu générique) ; aucune divergence observée ici |

Les deux règles dynamiques, lues au décompilé :

* **1081** ne lit **que le CASTER** (`param_2`) : rend `2` si le caster n'a **ni** ennemi adjacent
  (`battleQuery.<slot 0x7c>`) **ni** allié adjacent portant un `RangedSpecialist` **désactivé**
  (`<slot 0x80>` + `FightingRetreatAbility$$HasDeactivatedRangedSpecialist`), sinon `0` ;
* **1082** rend `1` (le natif **réutilise** le littéral `ValidRequest` comme code de refus) si
  `target == caster` **ou** `UnitExtensions.HasTrait(target, 0x7e7)` **ou** si les trois prédicats
  `<slot 0x11>` (soignable), `<slot 0x12>` (réparable) et `<slot 0x31>`
  (`EntityCanHaveActiveAbilityReset`) sont faux ; sinon `0`.

Les deux dégradent du côté **permissif** (le port accepte un cast que le natif refuse) et sont
signalées comme telles par le probe (`RESIDU`) plutôt que comptées en accord.

## 5. La correction sur les **munitions de MoW** — l'oracle en dépend

`docs/rl/case-mow-ammo-gauge.md` conclut que le terme munitions gate
`AActiveAbility$$get_CanCurrentlyBeUsed` et **pas** `IsInvalidTarget`. C'est exact pour
`ActiveAbilityOperation`, mais **l'oracle `abilityReason` en dépend quand même** : il passe par
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments), dont la
**première** ligne est

```c
ability = ActiveAbilityComponent.GetOrNull(<component du caster>, abilityType);
if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0)
    return GenericBrokenTargetingRule(1);      // ValidRequest, cascade JAMAIS évaluée
```

**Mesuré** (C4_09/777, seed BC partagé, `MachineOfWarAmmo = 0`) : 1160 (`ammoCost = 1`,
`hasAmmo = false`) rend **`0x1` sur les 8 lignes, `casterReason` compris** — aucune mesure de masque
possible. 1161 (`ammoCost = null`) n'est pas concernée et mesure normalement. Le probe patche donc
`Player.Players[*].MachineOfWarAmmo = 9` dans un seed BC écrit **hors `data/`**, et la cascade
s'évalue (§6).

⚠ Corollaire général : **`hasAmmo` doit être vérifié avant d'invoquer `abilityReason` sur une ability
de MoW à coût de munitions**, sinon on mesure le court-circuit et pas le masque.

### Le discriminant, parce qu'il existe une autre cause du même `0x1`

L'agent du module `deathguard` (#249) a mesuré le même `0x1` sur un caster MoW et l'a attribué à
l'autre clause du **même** court-circuit — `ActiveAbilityComponent.GetOrNull(...) == null` — après
avoir écarté cooldown et munitions sur son cas. Les deux lectures sont compatibles : c'est **une
seule ligne de code à trois clauses**, et il faut dire **laquelle** a mordu.

Pour ce cas-ci, la mesure tranche sans ambiguïté, et il n'a pas fallu changer d'oracle :

* **même runner, même caster** (`u91 tauBroadside`), **même RPC**, deux abilities : 1161
  (`ammoCost = null`) a rendu une cascade réelle (`0x0` / `0x4000` / `0x200000000000`) pendant que
  1160 (`ammoCost = 1`, `hasAmmo = false`) rendait `0x1` partout. Si `GetOrNull` avait rendu `null`
  pour un caster machine, **les deux** auraient rendu `0x1` ;
* **patcher `MachineOfWarAmmo` a suffi** à faire apparaître la cascade de 1160. Un patch de munitions
  ne peut pas peupler `ActiveAbilityComponent`.

⇒ pour 1160, la clause mordante est bien `!ability.CanCurrentlyBeUsed` **via les munitions**, et
l'oracle par CODE reste utilisable une fois le stock posé. Le repli sur l'oracle **ensembliste**
(`abilityTargets`) reste la bonne réponse quand c'est la clause `GetOrNull` qui mord — ce n'était
simplement pas le cas ici. Le recoupement a d'ailleurs été fait dans les deux sens :
`abilityTargets` (`now[4]` contre `now[3]`) et `abilityReason` (`0x0` contre `0x200000000000`)
disent **la même chose** sur le discriminant 1160/1161.

## 6. Validation live — `scripts/python/probe_250_tau_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)`. Le probe rejoue le gate
**offline sur le même état figé**, en cinq versions : `APRÈS` (registre), `AVANT`
(`TARGETING_OPTIONS = None`, l'état de `master`), `sansRules` (masque à 0, portée conservée),
`sansRange` (`range = None`), `melee1` (`force_melee_target = RangedBool.True`).

Montage : `--p-units tauCrisis,tauDarkstrider,tauAunShi --p-mow tauBroadside --a-mow
ultraDreadnought --a-units necroWarden×3`, board **MoW-capable** (`MachineOfWarPosition` posé pour
les deux camps), `--no-ai`, `MachineOfWarAmmo` patché. La géométrie est **conduite**, pas subie :
Darkstrider amené au contact d'Aun'Shi, un ennemi amené au contact, Re'vas et un second ennemi
écartés — d'où, dans la même table figée, les quatre régimes (allié au contact / allié loin / ennemi
au contact / ennemi loin) plus les deux machines hors-plateau.

**Deux couples (board, seed) distincts**, 40 lignes chacun :

| | `C4_09` / 777 | `C3_26` / 31337 |
|---|---|---|
| 1077 accord | **8/8** — 7 gains | **8/8** — 7 gains |
| 1081 accord | **8/8** — 4 gains | **8/8** — 5 gains |
| 1082 accord | **6/8** + 2 résidus dynamiques — 6 gains | **6/8** + 2 résidus — 6 gains |
| 1160 accord | **8/8** — 4 gains | **8/8** — 4 gains |
| 1161 accord | **8/8** — 5 gains | **8/8** — 5 gains |
| **total** | 38/40 + 2 résidus, **0 mismatch** | 38/40 + 2 résidus, **0 mismatch** |
| **casts illégaux que `master` acceptait** | **26** | **27** |

Table `C4_09/777` de 1160 et 1161, côte à côte (les deux abilities de la même machine) :

| cible | 1160 natif / port | 1161 natif / port |
|---|---|---|
| ennemi `necroWarden` ×3 | `0x0` / `0x0` | `0x0` / `0x0` |
| allié `tauCrisis`/`tauDarkstrider`/`tauAunShi` | `0x4000 TargetIsEnemy` / idem | `0x4000` / idem |
| **la MoW elle-même** (`tauBroadside`) | `0x4000 TargetIsEnemy` / idem | **`0x200000000000 TargetIsUnit`** / idem |
| **la MoW ENNEMIE** (`ultraDreadnought`) | **`0x0` (acceptée)** / `0x0` | **`0x200000000000`** / idem |

### Contrefactuels, par champ (sur les lignes GAIN, `C4_09`/777)

| ability | `rules` neutralisées | `range` neutralisé | `force_melee_target` flippé |
|---|---|---|---|
| 1077 | 0/7 faux-accepts | **5/7** | **2 lignes changent** |
| 1081 | 0/4 | **2/4** | 0 |
| 1082 | **1/6** | **1/6** | 0 |
| 1160 | **3/4** | 0/4 | 0 |
| 1161 | **3/5** | 0/5 | 0 |

Lecture, et elle est **dissymétrique à dessein** :

* 1077 : `rules` à 0 ne change **rien** — c'est le **verdict attendu**, ses deux bits ne sont pas des
  règles du filtre cible. Le test l'assère en positif (`cf_rules == 0`) plutôt que de laisser passer
  un masque mal lu ;
* 1160/1161 : `range` neutralisé ne change **rien** — `useWholeBoard` fait sauter le volet portée,
  donc ce champ **n'est pas validé par la mesure** pour ces deux-là (il est lu au décompilé, pas
  confronté) ;
* `force_melee_target` : sa valeur est `RangedBool.False` pour les cinq, c'est-à-dire la valeur
  **neutre** — le neutraliser ne peut rien changer. On mesure donc l'inverse (le **flip** vers
  `RangedBool.True`), et il ne déplace un verdict que pour **1077** (dont `RANGE_SELF` porte
  `overrideRange = 0` : le clamp mêlée met `onlyAdjacent = true` et fait accepter la distance 1).
  Pour **1081, 1082, 1160, 1161 le champ n'est pas validé par la mesure** — `RANGE_ADJACENT` est
  déjà `onlyAdjacent` avec `overrideRange = 1` (clamp no-op) et `RANGE_WHOLE_BOARD` sort de
  `get_range` avant de le lire.

## 7. Compteurs

| | avant | après |
|---|---|---|
| `ABILITY_CLASSES` | 94 | 94 |
| avec `TARGETING_OPTIONS` | 58 | **63** |
| sans | 36 | **31** |
| module `tau` sans masque | 5 | **0** |

Modules restants (`probe_181_targeting_gaps.py`) : `splash` 6, `blacklegion` 5, `deathguard` 5,
`summon` 5, `astramilitarum` 4, `strike` 2, `imperative`/`mv71`/`quickening`/`stormcaller` 1 chacun.

## 8. Artefacts

* port : `scripts/python/engine/runner/abilities/tau.py` (les cinq `TARGETING_OPTIONS`)
* tête de domaine : `scripts/python/engine/runner/abilities/targeting.py`
  (`get_target_domain_broken_rule`, `_is_machine`, `_resolves_to_unit`)
* probe (MESURE) : `scripts/python/probe_250_tau_targeting.py`
* test (GARDE) : `scripts/python/tests/engine/runner/test_tau_targeting_live.py`
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py`
  (1077/1081/1082/1160/1161 retirés de `SANS_TARGETING_OPTIONS`)

## 9. Ce qui n'est PAS couvert

* **Les deux `GetDynamicInvalidTargetReason`** (1081, 1082) — lus au décompilé (§4), **non portés**.
  Celui de 1082 refuse mesurablement 2 lignes sur 8 ; celui de 1081 est resté inerte dans ces
  montages parce que Darkstrider avait un ennemi adjacent. C'est le résidu principal du cas.
* **`CasterHas2TurnsLeft`** (1160) : mesuré inerte parce que le runner n'a pas de plafond de tours.
  Une bataille **plafonnée** ferait mordre la règle, et le port ne modélise pas le plafond.
* **`force_melee_target`** pour 1081/1082/1160/1161, et **`range`** pour 1160/1161 : lus au
  décompilé, **non confrontés** par cette mesure (cf. §6).
* **La ligne de vue** : non portée dans le gate générique, et 1160/1161 (portée plateau entier, sans
  bit `AllowObscured*`) sont justement des candidates à un refus natif par ce chemin — aucune
  divergence observée sur ces deux boards, mais rien ne le garantit ailleurs.
* **La tête de domaine sur une cible NON résolue** (id de tuile, entité absente) : le natif rompt
  sur `TargetIsUnit`, le port reste muet.
* **Les faces COMBAT** des cinq abilities (behaviours) : hors périmètre, déjà portées et gardées par
  `test_tau_lot1_live.py` / `test_mow_effect_posers_live.py`, rejouées vertes après ce changement.
