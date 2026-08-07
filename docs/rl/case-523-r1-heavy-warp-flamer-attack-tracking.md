# case-523-r1 — `1546 HeavyWarpFlamer_AttackTracking` : le COMPTEUR

#523 a porté la face EXECUTION de l'ACTIVE `1227 HeavyWarpFlamer` et a monté son nœud de LECTURE
(`HeavyWarpFlamerAbility$$GetNumExtraHits` interroge le `PersistentDataComponent`) — mais **rien
n'écrivait** : `GetPersistentDataFormula$$Calculate` rendait son `out` par défaut = 0 et
`GetNumTotalHits` valait `nrOfHits`. Cette tranche est l'ÉCRITURE, et elle ne touche **pas une ligne**
du port de 1227.

Build de lecture : `rnca9r7q6c` (= `data/symbols/CURRENT`).

## 0. Gate de confrontabilité — la triggered n'arrive par AUCUNE des voies habituelles

`1546` n'a **aucune entrée de gameconfig** (`GC.ability("HeavyWarpFlamer_AttackTracking")` rend
`None`) et `thousSekhetar` ne la liste **nulle part** — son seul `passiveAbilities` est
`PropheticSentinel`. Elle est montée par
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, qui pour chaque ability ACTIVE de
l'unité fait :

```
if (StaticBattleRules.ActiveAbility$$HasDerivedTriggeredAbilities(t))
    foreach (d in StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities(t))
        TriggeredAbilityComponent$$TryAdd(d, triggeredAbilityState, ...)
```

Le dictionnaire statique est peuplé par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor`, et le
couple y est **LU verbatim** dans le motif d'insertion (valeur écrite en `[rbp+0x18]`, clé en
`[rbp+0x20]`, puis `Dictionary.Add`), encadré par ses deux voisins **déjà portés** :

| valeur (`[rbp+0x18]`) | clé (`[rbp+0x20]`) | statut du port |
|---|---|---|
| `0x5e3` = 1507 `Hailstrike_Attack` | `0x4be` = 1214 `Hailstrike` | porté (#117 ph.2) |
| **`0x60a` = 1546 `HeavyWarpFlamer_AttackTracking`** | **`0x4cb` = 1227 `HeavyWarpFlamer`** | **cette tranche** |
| `0x613` = 1555 `EmpyricAmbush_Reset` | `0x4d0` = 1232 `EmpyricAmbush` | porté (#589-r1-r1-r1-r1) |

⇒ TROISIÈME chemin de registration du port : `ACTIVE_ABILITY_TRIGGERS["HeavyWarpFlamer"]`, celui de
ses deux voisines. Par toute autre voie 1546 serait INTROUVABLE, et l'absence serait **silencieuse**.

Porteur : `thousSekhetar` (HERO `lineup`, hors seed BC) → `catalog_inject.write_augmented_seed_bc` +
`rl_duel build --seed-bc` (`case-92` §6), la MÊME voie que #523 et #27.

## 1. `$$CreateTrigger` — une DISJONCTION, cinq conjoints d'un côté, zéro de l'autre

```
  ( On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive = 1)
    & <DSLTriggers+0x28 = IsTurnOf(Owner)>
    & NOT AreEqual(Attacker, Owner@DSLSelectors+0x30)
    & AreFriends(Attacker, Owner@+0x30, comparisonType = 0, anyEntity = 0)
    & CurrentAttackDamageProfilesContain(DamageProfileType.Psychic = 0xd, includeNotApplied = 0) )
| On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive = 1)
```

Les deux `ownerNeedsToBeAlive` sont LUS à l'assembleur (`mov r8b,1` avant chaque `$$On`), de même
que `includeNotApplied = 0` (`xor r8d,r8d`) et `comparisonType = 0` (`xor r9d,r9d`).
`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` (identification de `case-366-r1-turnof-all.md` §2).

**Le second disjoint est un `On(...)` NU** : ni `get_OwnerIsActor`, ni `<DSLTriggers+0x28>` — le
`op_BitwiseOr` final n'agrège que `On(0x17)`, ce qui se lit dans l'ordre des `op_BitwiseAnd`. La clé
est donc vidée à CHAQUE fin de tour, y compris celle du camp adverse (même forme que
`UntilOfEndTurnEffect$$CreateRemoveEffectTrigger`).

`CurrentAttackDamageProfilesContain` → `IdunBattle.Entities.Triggers.DamageProfilesContainsTrigger$$ShouldTrigger`
= `<liste des profils de l'attaque>.Contains(this+0x10)`, liste nulle ⇒ faux. Le champ
`this+0x14` (`includeNotApplied`) choisit laquelle des deux listes de l'`AbilityEntities` est lue.

## 2. `$$CreateBehaviour` — et LE PIÈGE, qui n'est pas au décompilé

```
if (triggerType == 0x17)                                    # TurnEnd
    return ClearPersistentData( AbilityOrEffect(0x4cb), Owner@+0x30, "PSYCHIC_ATTACKS_KEY" )
return SetPersistentData( AbilityOrEffect(0x4cb), Owner@+0x30, "PSYCHIC_ATTACKS_KEY",
                          Sum( GetPersistentData(AbilityOrEffect(0x4cb), Owner@+0x30,
                                                 "PSYCHIC_ATTACKS_KEY"),
                               <DSLFormulas+0x20 = Direct(1)> ) )
```

**TROIS lectures qui ne se devinent pas :**

1. **L'`AbilityOrEffect` écrit par la TRIGGERED est le littéral `0x4cb` = 1227 — l'id de l'ACTIVE,
   pas son propre 1546.** Ghidra perd le registre dans les trois `AbilityOrEffect$$op_Implicit` ; le
   littéral est LU à l'assembleur. `...HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour+0x49`
   porte `mov edx, 0x4cb`, et il est posé **AVANT** le `cmp edi, 0x17` (`+0x4e`) — donc **partagé par
   les deux branches** : la branche `TurnEnd`, à `+0x187`, entre directement sur `mov rdi,[rax+0x78]`
   sans recharger `edx`. Le lecteur côté ACTIVE, lui, porte `mov edx,[rbx+0x10]`
   (`...HeavyWarpFlamerAbility$$GetNumExtraHits+0x4a`) = le champ de type de l'active, 1227 aussi.
   Les deux côtés adressent donc la MÊME clé composite (`AbilityOrEffect$$GetPersistentDataId` rend
   l'ordinal du premier de ses trois `Nullable` renseigné). **Écrire `1546` rendrait le mécanisme
   INERTE, sans aucune erreur.**
2. **La `dataKey` est `"PSYCHIC_ATTACKS_KEY"`** — le décompilé n'affiche qu'un `DAT_183370b30`,
   résolu par `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` ligne
   `13388 0x3370b30 "PSYCHIC_ATTACKS_KEY"`. Xrefs du slot : EXHAUSTIVEMENT les deux fonctions de la
   paire ⇒ clé privée.
3. **La feuille est `SetPersistentData`, PAS `AddPersistentData`.** Deux classes natives distinctes,
   dans deux namespaces distincts, à deux adresses distinctes
   (`IdunBattle.Entities.Behaviours.SetPersistentDataBehavior$$Execute` vs
   `IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute`), et la **séquence d'appels** les
   sépare : la seconde appelle `PersistentDataComponent$$TryGetPersistData<T>` **avant** son
   `PersistData<T>` — elle RELIT — là où la première ne l'appelle pas et se contente d'écrire.
   L'incrément vit donc dans le nœud VALEUR `Sum(GetPersistentData(...), Direct(1))`, pas dans la
   feuille ; confondre les deux double-compterait. (Le port n'avait que `AddPersistentData` ; la
   feuille `SetPersistentData` est **neuve**, cf. `abilities/behaviours/persistent_data.py`.)

⇒ Sémantique : **chaque attaque d'un ALLIÉ (jamais du porteur), jouée pendant le tour de l'équipe du
porteur et dont les profils contiennent `Psychic`, ajoute 1 coup au prochain `HeavyWarpFlamer` ;
plafonné en LECTURE à `maxNrOfHits - nrOfHits` ; remis à zéro à la fin du tour.**

## 3. Forme du port (doctrine #149) — et DEUX classes pour UNE classe native

`CreateTrigger` est COLLAPSÉ impérativement dans `matches` (lecture d'état pure : tour courant,
identité de l'attaquant, camp, profils du coup — même choix que `NeuroparasiteAbility`, l'autre
consommateur porté de ce vecteur avec le MÊME conjoint `CurrentAttackDamageProfilesContain(0xd)`).
`CreateBehaviour` est un ARBRE DSL : deux feuilles au-dessus du `PersistentDataComponent`, et le nœud
VALEUR est un vrai arbre — il n'est pas pré-calculé en Python.

Le natif a UNE classe dont le trigger est une disjonction sur deux events et dont le behaviour branche
sur `triggerType` ; le registre du port est indexé PAR `event_id`, d'où **deux** entrées — exactement
le patron `HaywireMinePlaceOnMove` / `HaywireMinePlaceOnTurnEnd`. Les deux portent le même
`TRIGGERED_ABILITY_ID` (1546) et la même clé persistante `(1227, "PSYCHIC_ATTACKS_KEY")`.

`TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` ne s'appliquent pas : ce sont des données d'`ABILITY_CLASSES`
(abilities ACTIVES), et 1546 est une TRIGGERED. `probe_181` reste à **128/128, 0 manquante**.

## 4. Le montage live — la géométrie et les DISTANCES sont FABRIQUÉES

Le compteur n'a **aucun canal de lecture live** (`dumpEntityComponents` rend la mise en page des
composants, pas leurs valeurs) : son seul observable est le NOMBRE DE COUPS de 1227. Le montage est
donc construit pour que ce nombre CHANGE entre deux casts successifs du MÊME porteur. Sur `MC1_67` :

```
C  = thousSekhetar (0,0)   ADJACENT A AUCUN ennemi (sinon ForceMeleeTarget rabat la portee a 1)
T  = necroWarden   (0,2)   d(C,T) = 2 = range ; AUCUN autre ennemi a <= 2 de C ET adjacent a T
A1 = thousSorcerer (4,0)   arme RANGED Psychic (portee 2) ; sac de frappe P1 (4,2), d = 2
A2 = thousAhriman  (6,0)   arme RANGED Psychic (portee 2) ; sac de frappe P2 (6,2), d = 2
A3 = astraBullgryn (4,3)   arme MELEE Physical SEULE ; frappe P1 (4,2), d = 1        [TEMOIN]
```

**La distance est le discriminant de PROFIL, pas un détail** : les deux Thousand Sons portent une arme
de mêlée `Flame` et une arme à distance `Psychic` — placés à d = 2, c'est la seconde qui part. Le
témoin `astraBullgryn` n'a QU'UNE arme, `Physical` : son attaque traverse exactement le même vecteur
`On(9)` et doit ne RIEN ajouter. Sans lui, l'accord ne séparerait pas « compte les attaques
PSYCHIQUES » de « compte toutes les attaques alliées ».

Le tour 2 exige de RE-FABRIQUER la géométrie (le tour adverse la défait) : deux `act endturn` ne
rendent PAS la main — mesuré, `act endturn` ne clôt que le tour du camp piloté, et le tour 2 arrivait
avec `legal=[]` alors que la cible était restée à d = 2. Il faut `aiturn`, puis **déplacer le caster**
sur une tuile légale à d = 2 de la cible et à ≥ 2 de tout autre ennemi (« bloqué par la géométrie »
n'est pas un résultat).

## 5. Ce qui a été mesuré

`python scripts/python/probe_523r1_heavy_warp_flamer_tracking.py` — **rc = 0**.

| verdict | mesure |
|---|---|
| 0 — profils RÉELLEMENT émis | `['Psychic', 'Psychic', 'Physical']` |
| 1 — suite du compteur (offline) | `[0, 1, 2, 2]` — +1, +1, **rien** sur le témoin |
| 2 — `GetNumTotalHits` | base `4` → après `6` (`nrOfHits` 4, `maxNrOfHits` 9) |
| 3a — nb de coups tour 1 | offline **6** = live **6** |
| 3b — nb de coups tour 2 | offline **4** = live **4** |
| **4 — DELTA (tour 1 − tour 2)** | offline **2** = live **2** |
| 5 — `On(TurnEnd)` (offline) | compteur `2` → **absent** ; cast suivant = `4` coups |
| 6b — per-coup tour 2 (sans prélude) | offline clampé `[6740, 1877, 0, 0]` = live `[6740, 1877, 0, 0]` |

**Le couple qui MORD est le DELTA** : un accord à valeur constante ne prouverait rien. Les trois modes
de panne sont séparés par le même montage — ne rien compter (delta 0), compter aussi le PHYSIQUE
(delta 3), ne pas VIDER (tour 2 haut, delta 0).

⚠ **La MAGNITUDE du tour 1 n'est PAS confrontée, et c'est MESURÉ, pas supposé.** Le prélude d'attaques
désaligne le PRNG : positions `mti` **live 3 / 5 / 11** contre **offline 2 / 4 / 9**. Comparer les
dégâts imputerait à cette tranche un écart qui appartient au modèle de dégât des attaques du prélude —
et l'attribution est faite : la **3ᵉ** attaque (PHYSIQUE) **ne déclenche pas** 1546 et ajoute pourtant
un tirage d'écart. Le tour 2, sans prélude, est bit-exact. Résidu **#523-r3**.

## 6. Les gardes, et la MUTATION ADVERSARIALE qui les a vues ROUGES

`test_523r1_heavy_warp_flamer_tracking_offline.py` (9) — chaque mutation a été appliquée au port,
jouée, puis **révoquée** :

| mutation | rouges | message verbatim |
|---|---|---|
| clé = `1546` au lieu de `1227` | **6/9** | `FAILED …::test_la_cle_est_celle_de_l_ACTIVE_1227_pas_celle_de_la_triggered_1546` · `assert 4 == 5` |
| `IsTurnOf(Owner)` désarmé | 1/9 | `AssertionError: IsTurnOf(Owner) : une attaque alliee hors de notre tour ne doit RIEN compter` · `assert 1 is None` |
| valeur = `Const(1)` au lieu du nœud `Sum` | 4/9 | `assert 5 == 6` (le compteur reste figé à 1) |
| classe `Reset` retirée du registre | 4/9 | `assert 1 is None` après `end_turn_summon_triggers` |
| conjoint de PROFIL désarmé | 1/9 | `AssertionError: profil non psychique : le compteur a bouge -> le conjoint correspondant ne mord plus` |

`test_523r1_heavy_warp_flamer_tracking_live.py` (8) rejoue `probe.mesure` et assertionne les mêmes
critères sur le même dict (foyer unique).

Non-régression rejouée : `test_523_heavy_warp_flamer_offline.py` (10), `test_523_heavy_warp_flamer_live.py`
(9), `test_ability_registry_ratchet.py` (11), `test_462_r4b_…_haywire_pose_live.py` (5) — le seul
autre consommateur porté de la famille persistent-data. `probe_181` = 128/128, `probe_313` = 35
mirrors en bijection (dont `ACTIVE_ABILITY_TRIGGERS`, 3 clés).

## 7. Résidus

* **#523-r2** — **`AddPersistentDataBehavior$$Execute` RELIT avant d'écrire, et le port le décrit
  comme un écrasement pur.** Mesuré par la séquence d'appels : son corps appelle
  `PersistentDataComponent$$TryGetPersistData<T>` **avant** son `PersistData<T>`, ce que
  `SetPersistentDataBehavior$$Execute` ne fait pas. La docstring de `AddPersistentData`
  (`abilities/behaviours/persistent_data.py`) affirme « `PersistData` **ÉCRASE**, il n'empile pas ».
  Aucun observable ne diverge aujourd'hui : son unique consommateur porté (`HaywireMineAbility`,
  valeur `Direct(1)`) est gaté par `AmountIsZero(GetPersistentData)` et vide la clé à chaque fin de
  tour — accumuler ou écraser y donne le même verdict. À re-RE (l'arithmétique entre les deux appels
  passe par des helpers génériques boxés).
* **#523-r3** — **le PRNG diverge d'un tirage par attaque normale sur le montage de ce probe.**
  Mesuré : `mti` live 3 / 5 / 11 contre offline 2 / 4 / 9 après les attaques de `thousSorcerer`
  (RANGED `Psychic`, 1 coup), `thousAhriman` (idem) et `astraBullgryn` (MÊLÉE `Physical`, 4 coups) —
  soit +1 sur la 1ʳᵉ et +1 de plus sur la 3ᵉ. **Hors périmètre de cette tranche** : le trigger 1546
  ne consomme aucun tirage, et la 3ᵉ attaque ne le déclenche pas. Conséquence directe : toute
  confrontation de MAGNITUDE derrière un prélude d'attaques est structurellement impossible sur ce
  roster tant que ce n'est pas fermé.
* **#523-r4** — **la branche MV71 de `IdunBattleLogic.Entities.DSLSelectors$$Attacker` n'est pas
  modélisée.** Le sélecteur n'est PAS le slot `Actor@+0x40` : c'est un composite, lu en entier —
  `If( AreEqual(<DSLSelectors+0x98>, DirectAbilitySelector(AbilityOrEffect(0x434 =
  ActiveAbilityType.MV71SniperDroneSquadAttack))), ParentSelector(Caster@+0x48), Caster@+0x48 )`. Le
  littéral `0x434` est LU à l'assembleur (`...DSLSelectors$$Attacker+0x38` : `mov edx,0x434`), et la
  nature CONDITIONNELLE du nœud est établie par les XREFS de son `.ctor` — corps DÉDUPLIQUÉ que
  `DSLSelectors$$If` et `DSLSelectors$$ConditionalSelector` partagent, donc le nom ghidra
  `UnobscuredEntitiesSelector$$.ctor` est celui d'un propriétaire ARBITRAIRE. Hors du cas MV71 (un
  drone T'au, dont l'attaque est créditée à son PARENT), `Attacker` EST le caster de l'attaque, que
  le port lit dans `ev.actor_id`. Le sélecteur est partagé : ce résidu dépasse 1546.

## Fichiers

* port : `scripts/python/engine/runner/operations/triggers/loki/heavy_warp_flamer.py`
* feuille neuve : `scripts/python/engine/runner/abilities/behaviours/persistent_data.py`
  (`SetPersistentData`)
* câblage : `scripts/python/engine/runner/operations/triggers/dispatch/registry.py`
  (`ACTIVE_ABILITY_TRIGGERS["HeavyWarpFlamer"]`)
* mesure : `scripts/python/probe_523r1_heavy_warp_flamer_tracking.py`
* gardes : `scripts/python/tests/engine/runner/test_523r1_heavy_warp_flamer_tracking_offline.py` (9),
  `.../test_523r1_heavy_warp_flamer_tracking_live.py` (8)
