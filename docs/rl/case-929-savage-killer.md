# #929 — `SavageKiller` (passif `spaceWulfen` « Ulf », `TriggeredAbilityType` 0x487 = 1159)

UNE triggered-ability native, **DEUX faces** de déclenchement, **UN** behaviour d'attaque.
RE complète (arbres verbatim, surcharges tranchées, résidus) : en-tête de
`scripts/python/engine/runner/operations/triggers/loki/savage_killer.py`. Ce document ne garde que
ce qui ne tient pas dans le module : **la méthode** qui a tranché, et **les mesures**.

## 1. Ce que le natif dit et qu'aucune table ne disait

`ghidra/functions.tsv` donne SIX corps contigus pour cette classe. Deux littéraux load-bearing sont
**effacés par le pseudo-C ghidra** — il n'imprime pas les immédiats passés à `op_Implicit`. Ils ont
été lus aux OCTETS (`read_bytes` + résolution des `call rel32` **en code**) :

| call-site | surcharge résolue | immédiat |
|---|---|---|
| `$$CreateCharacterActiveAbilityTrigger+0x092` | `AbilityOrEffect$$op_Implicit(activeAbility: **ActiveAbilityType**)` | `0x467` = **1127 `ArmouredMight_Move`** |
| `$$CreateBehaviour+0x15e` | `$$op_Implicit(triggeredAbility: **TriggeredAbilityType**)` | `this.Id` = 1159 |

**Deux espaces d'enum DIFFÉRENTS dans la même classe.** Le voisin de forme
(`MartialSuperiority`, `CursedPlagueBell`) écrit un `TriggeringAbilityIs`/`CurrentAbilityIs` **sur sa
propre ability** ; recopier ce patron ici aurait écrit `1159` — un ordinal parfaitement valide dans
`ActiveAbilityType`, où il nomme `MacroPlasmaIncinerator`. **Aucune erreur n'aurait été levée.**
Gardé par `test_929_savage_killer_offline.py::test_les_deux_ids_vivent_dans_DEUX_espaces_d_enum_differents`.

Autres surcharges tranchées **à l'adresse de la cible d'appel** (jamais à l'œil) :
`AttackWithAttackDamage` = la forme `hits: System.Int32` + `damageProfile: Nullable<DamageProfileType>`
(sur CINQ homonymes) ; `AmountIsGreaterThanZero` = la forme `ITargetsSelector` (pas `IAmountFormula`) ;
`IsOverwatchAttack` = la forme **sans argument** ; `IsActiveAbilityCountedAsUsed` avec `mov dl, 1`,
donc la branche `isPreAbilityTrigger = **true**` — l'AUTRE que celle que portait `FuelledByFury`.

## 2. Les DEUX faces ont des gates DIFFÉRENTES, et c'est natif

|  | déclencheur | ce qu'elle gate | ce qu'elle NE gate PAS |
|---|---|---|---|
| **A** | `On(UnitAfterMove \| UnitDisplaced \| UnitAdded)` | le **TRAIT** de la victime (`Summon`) | rien sur la nature de l'action |
| **B** | `On(PreUnitAbility)` | la **NATURE de l'ability** (`IsActiveAbilityCountedAsUsed`, donc jamais une attaque normale) | rien sur le trait du caster |

Et elles ne lisent pas le même slot : **A** vise `Target@DSLSelectors+0x60`, **B** vise
`Caster@+0x48`. `$$CreateBehaviour` re-exprime ce choix (`triggerType == 0x2a ? Caster : Target`) et
`$$GetInitialTarget` une troisième fois, en `ConditionalSelector` — trois écritures du même fait.

**Mesure live** (probe_929, duel `spaceWulfen` vs `orksRuntherd`, board MC1_67, seed 777) :

| régime | dist | action | face B (le caster est frappé ?) | face A (le grot est frappé ?) |
|---|---|---|---|---|
| `actif`   | 1 | caste `GetEmRuntz` | **OUI** — 5 coups 1159 : `5529+2832+2556+2984+2988` = 16889 | **OUI** — 5 coups, grot mort |
| `normale` | 1 | attaque NORMALE | **NON** — 0 coup 1159, PV inchangés | oui (grot de `SquigHound`) |
| `summon`  | 2 | caste `GetEmRuntz` | **NON** — gate d'adjacence | **OUI** — `6108+1204`, grot mort |

Le régime `normale` est le **loophole** déjà observé en self-play (« frapper Ulf en NORMALE depuis un
corps déjà-adjacent ne le réveille pas ») : il est ici **mesuré au décompilé ET au live**, et c'est
lui qui interdit de recopier la gate d'une face sur l'autre — ça aurait éteint exactement une face
sur deux.

Le montage `GetEmRuntz` n'est pas un choix de commodité : ses grots naissent sur les tuiles libres
**adjacentes au caster ET adjacentes à un ennemi**
(`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector`), donc un
summon naît adjacent à Ulf **sans qu'on ait à piloter un summon** — ce qui est autrement coûteux
(un summon a son tour terminé à l'apparition, cf. #291).

## 3. Verdict DEAD CODE — `$$CreateValidActiveAbilityTrigger`

`list_xrefs` rend **2** références, toutes **DATA** (bloc `methodPointers` + table des méthodes),
**0** `UNCONDITIONAL_CALL` — là où ses deux sœurs portent en plus l'appel de `$$CreateTrigger`.
`search_symbols_by_name` sur ce nom rend **UN SEUL** symbole dans tout le binaire : aucune méthode
homonyme d'une base ou d'une interface, donc aucun slot virtuel ne peut l'atteindre. Son corps est
un **sous-ensemble exact** des deux premiers conjoints de `$$CreateCharacterActiveAbilityTrigger` :
un helper laissé après dépliage.

Le verdict est **gravé aux octets**, sans ghidra
(`test_929_savage_killer_offline.py::test_create_valid_active_ability_trigger_est_dead_code`) :
`$$CreateTrigger` fait exactement **2 `call`** (les deux helpers vivants) et **1 `jmp`** (le tail call
`op_BitwiseOr`), aucun vers lui. ⚠ Le test **assertionne son propre non-vide** avant de conclure de
l'absence : la première rédaction bornait sa fenêtre de lecture par une soustraction qui pouvait
devenir négative, et rendait alors `cibles == []` — l'assertion « `va_dead` absent » serait passée
pour une raison **vacue**. C'est la contre-épreuve qui l'a montré, pas la relecture.

## 4. Ce que le LIVE ne peut PAS garder — et pourquoi il faut le savoir

Le mutant `DAMAGE_PROFILE : Power -> Physical` **ne fait pas rougir la passe live**. Cause mesurée,
deux étages qui s'additionnent :

* `--hp-target 999999` met `Armor`/`FixedArmor` à **0** (`runner.md` §3) → l'étage PERCE-ARMURE du
  profil n'a rien à percer, `Power` (pierce 40) et `Physical` (pierce 0) rendent le même dégât ;
* sur le grot de la face A, les deux profils **tuent** → PV clampés à `0` des deux côtés.

Le profil est donc gardé **contre sa source** (`constants.damageProfile` du gameconfig), pas contre
un delta de PV. Même traitement pour `nrOfHits` et `attackRangeType`. C'est le cran juste : c'est
cette lecture-là que le port doit reproduire.

## 5. Mutants joués

| # | mutation | verdict |
|---|---|---|
| M1 | entrée retirée d'`ABILITY_TRIGGERS` | **mord** — 3 tests live rouges |
| M2 | gate `IsActiveAbilityCountedAsUsed` retiré | **mord** — réaction fantôme de 16889 sur une attaque normale |
| M3 | gate d'adjacence retiré | **mord** — réaction fantôme sur un caster à 2 hexes |
| M4 | slot inversé sur la face B (`Target` au lieu de `Caster`) | **mord** — 0 réaction offline vs 5 coups live |
| M5 | gate de la face A recopiée sur la face B (`HasTrait(Summon)`) | **mord** — le piège du voisin |
| M6 | `DAMAGE_PROFILE : Power -> Physical` | **INERTE live** (cf. §4) — **mord offline** |

## 6. Résidus

* **#929-r1** — `On(UnitBecameTargetable = 0x3b)`, la 4ᵉ disjonction, **n'a aucun émetteur côté
  port** : l'évènement n'est construit nulle part dans `engine/**`. Non abonnée (un port spéculatif
  y matérialiserait le prédicat `NOT (PreviousTile | TurnStartTile)` que rien ne peut exercer).
* **#929-r2** — `NOT IsReplacedUnit(Target, 3)` = `UnitHasSpawnSourceTrigger(unit, SpawnSource.Replace = 7, …)`.
  Le mirror `engine/entities/spawn_source.py` existe, mais **aucune entité du runner ne porte de
  `spawn_source`**. Terme laissé PASSER ; dégradation sûre et mesurable (aucun chemin de
  `operations/spawn.py` ne crée d'unité par remplacement).
* **#929-r3** — bug DORMANT **de `master`**, découvert par cette tranche et **non causé par elle** :
  `hateful_assault_tree(...).execute(...)` lève `AttributeError: 'int' object has no attribute 'get'`
  (`UnitSet([<id int>])` + `multi=True`, alors que la branche multi de `AttackWithAttackDamage` filtre
  par `(u or {}).get("id")`). Reproduit en 12 lignes offline. Ses 10 tests sont verts parce
  qu'**aucun** n'exécute son `execute_behaviour`.
* **#929-r4** — `NOT TriggeringAbilityIs((ActiveAbilityType)1127 ArmouredMight_Move)` est porté mais
  **inerte** : le canal `ev.triggering_effect` (le slot `DSLSelectors+0x90`) n'est pas threadé sur le
  vecteur `On(PreUnitAbility)`. Doublement inerte, en fait — `ArmouredMight` n'a **aucun porteur**
  dans le gameconfig (mesure gardée par un test).

Le conjoint `NOT IsOverwatchAttack()` n'est PAS un résidu : il est **structurellement satisfait** —
le tir d'overwatch du port n'émet pas `On(PreUnitAbility)` (il appelle `AttackDamageOperation` sans
traverser le niveau MESSAGE). Même traitement que le `NOT IsDirectTargetAttack(@0x140)` de
`MartialSuperiority`.
