# #975 — cinq faces DÉCISION de kit (AdeptusMechanicus / Leagues of Votann / T'au)

**Livré** : les cinq playbooks `NonComparable` du lot, portés, câblés et confrontés LIVE.
`PLAYBOOKS` **65 → 70**.

| id | ability | porteur | classe native | verdict |
|---|---|---|---|---|
| 1139 | `SentinelDirectives` | `admecDestroyer` | `IdunBattle.AI.Playbook.SentinelDirectivesPlaybook` | porté ; **écart de valeur hérité de l'étage PRÉDICTION** (#975-r3) |
| 1116 | `RadBombardment` | `admecDominus` | `IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook` | **accord EXACT** (position + utilité) |
| 1206 | `GravitonRifle` | `votanIronmaster` | `IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook` | **accord EXACT** |
| 1221 | `AugmentedAssault` | `votanBeserk` | `IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook` | **accord EXACT**, gate propre prouvé mordant |
| 1087 | `ExemplarOfTheKauyon` | `tauShadowsun` | `IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook` | accord sur utilité + position ; gate en **borne SUP** (#975-r1) |

Reachability LUE dans `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` : cinq
entrées du dict `active` (+0x68), une par ability — aucun code registered-but-dead.
Base `NonComparablePlaybook`1` LUE dans `frida/classes.tsv` pour les **cinq**, alors que ghidra
nomme leur `.ctor` `ComparablePlaybook<...>$$.ctor` pour les cinq (corps gshared dédupliqué —
le piège de #487-r1 / #945 / #957 / #967 / #969, qui se rejoue à chaque lot).

## 1. Ce que les corps disent, et ce qu'ils ne disent pas

Les cinq partagent le squelette `Bucket(0, Nullable(MIN_UTILITY))` + `foreach
GetEligibleTargetsSelectable` + `AddAction(GenerateAction(...))`. Tout le reste les sépare.

* **1221** et **1206** ont le **même corps de boucle, octet pour octet** —
  `Fix64(GetStat(cible, 5 = Health))` — et divergent par ce qui l'entoure :
  * 1221 porte un gate `if (1 < targets.<+0x18>)` (`List._size`) **DANS** `EvaluateNonComparable`,
    donc **PAR POSITION** : le corps de boucle *et* le `SendSumMetric` de fin d'énumération sont
    tous deux à l'intérieur du `if`. Havyr ne dépense son ability que s'il a **au moins DEUX**
    cibles légales depuis la position évaluée ;
  * 1206 n'a aucun gate de boucle, mais surcharge **directement** le slot 4 :
    `!EnemyWillBeKilledWithNormalAttack(unit) && !HasAnyRepairTarget(unit)`. La seconde moitié est
    le corps de `GravitonRiflePlaybook$$HasAnyRepairTarget` **inliné** (les deux fonctions sont
    identiques à la comparaison finale près, `== 0` ici / `!= 0` là-bas). Vynn porte le trait
    `Mechanic` : le natif lui **interdit de tirer tant qu'il reste quoi que ce soit à réparer**.
* **1116** est le seul du lot dont le `.cctor` ne vaut pas 1 : `Fix64.op_Implicit(**2**)`. Son
  utilité est un **compte NU** (`Fix64.op_Implicit(count)`) — ni `op_Multiply` ni `op_Addition`
  dans le corps. ⚠ Le registre `_NONCOMPARABLE_ABILITIES` annonçait
  « (#ennemis dans GetAffectedTiles) **x 2** » : **FAUX**, corrigé par cette tranche. Le `2` réel
  est le plancher du Bucket, pas un facteur.
* **1139** pose un **plancher `Fix64(1)` DANS l'utilité** (`Fix64.op_Implicit(1)` puis
  `op_Addition`), pas seulement dans le gate — donc l'ability est toujours proposable dès qu'une
  cible est éligible. Son dégât est **`minDmg` (var `0xc`) SEUL**, pas la moyenne
  `Half(Sum(minDmg, maxDmg))` du chemin générique — même choix natif que `HammerOfWrath`.
  Son namespace n'a **pas** de `.Loki`, seul du lot.
* **1087** a une utilité **constante 1 = `MIN_UTILITY`** ; tout le discriminant est
  `HasEnemyInRange(entities)`, dont le corps est inliné dans `EvaluateNonComparable` :
  `GetEligibleTargetsForNormalAttack(entities@+0x08 = caster, UnitPosition(entities@+0x10 = la
  TUILE VISÉE)).Count > 0`. Le natif demande donc **« si Shadowsun se tenait là, aurait-elle une
  cible d'attaque normale ? »** — exactement le sens de la face COMBAT, qui la TÉLÉPORTE sur la
  tuile puis y déclenche un `PerformAIAttack`.

⚠ **Le voisin de forme qu'il fallait écarter** :
`TheQuickeningPlaybook$$GetNumAttackTargetsInPosition` ressemble à `HasEnemyInRange` et ne l'est
pas — il appelle `<IBattleQuery slot 0x80 = 128 GetAdjacentEnemies>`, des ennemis **adjacents**,
là où 1087 appelle `<slot 0x42 = 66 GetValidTargets>`, des cibles **légales**. Les deux slots ont
été lus dans `metadata/interface_slots.tsv` **avant** de trancher ; le mirror
`_base._get_num_attack_targets_in_position` porte le second et n'était donc pas réutilisable.

## 2. Ce que la mesure LIVE a trouvé — deux bugs de port, invisibles offline

Banc : `MC1_67` / seed 777, les **cinq porteurs co-injectés dans la même équipe**
(`catalog_inject.write_augmented_seed_bc` pour les deux Votann, absents du seed BC), placement
exact par `--place` / `--a-place`. Oracle : `ncEvaluate` (utilité `best` du Bucket natif, par
position). Probe : `scripts/python/probe_975_kit_decision_faces.py`.

1. **`squadId`, pas `entityId` (1087, et silencieusement 1206).** `observeBattle.units[]` porte les
   DEUX clés, et elles ne désignent pas la même chose. Chercher `entityId` rendait `visualId =
   None` sur les **10** unités du banc ⇒ `has_enemy_in_range` rendait `False` PARTOUT ⇒ le
   playbook était **INSCRIT ET INERTE**, sans la moindre erreur. Le même helper dans
   `graviton_rifle` dégradait, lui, de façon **permissive** (repair-type indéterminable → gate
   inactif) : invisible sans la mesure.

2. **Le sweep de 1116 ne pouvait pas voir le cast que le natif fait.** L'oracle rend
   `bucket: "empty"` à l'origine `(1,3)` et `util = 2` depuis `(1,4)` : **le natif se déplace
   d'une tuile** pour aligner deux ennemis. Un sweep limité à `fromHere` (la borne que porte
   `DarkTalonStrikePlaybook`) ratait donc le **cast entier**, pas seulement sa position. Le
   correctif ne fabrique aucune tuile : il **intersecte** l'union mesurée
   (`abilityTargets(...).targets`) avec une contrainte **LUE** — `TargetingRange.CustomRange(1)`
   du `.ctor`, donc l'aim est toujours adjacent à la position de cast.

## 3. #975-r3 — l'écart de 1139 vit EN AMONT, et deux voies natives le disent

Le port rend le **même argmax de position, la même cible et le même ordre de préférence** que
l'oracle, mais pas la même valeur :

```
pos     (1,5)   (1,6)   (0,4)   (0,5)   autres
natif   54.50   45.59   41.76   34.56   28.17
port    38.99   32.67   32.11   24.83   21.74
```

Décomposition (`probe_975_diag1139{,b,c,d}.py`), étage par étage :

* `GenerateAction` est **neutre** (elle stocke l'utilité telle quelle dans `BucketAction`) ;
* `Playbook<T>$$CalculateUtilityFromDamageEvent` (surcharge finale) est
  `prob1 * prob2 * <UtilityType 0x23 = Damage>(case)` — le port mirrore bien la case **35** ;
* l'écart est donc dans la **PRÉDICTION**, et deux voies natives indépendantes le confirment :
  * `ncPlaybookPredict --via evaluate` capture, à `(1,6)`, **min 2933 / max 4230, hits 1** —
    **IDENTIQUES pour les TROIS cibles**, dont les armures diffèrent. Le port rend 1670/3798 et
    1184/2886 : ses bornes **dépendent** de la cible ;
  * le PLAN natif (`computeAttackPlans`, qui n'emprunte aucun playbook) publie **5984/8436**,
    **8976/10542**, **7480/8536** là où le port rend 1184/2886, 2004/4557, 1480/3608.

Un balayage de `base_override` ne réconcilie pas : la valeur qui reproduit l'utilité native
(**4933**) n'est ni `minDmg` (4254), ni `maxDmg` (5318), ni leur moyenne (4786), et le rapport
max/min diffère structurellement (**1.44** natif contre **2.05–2.27** port). Ce n'est pas un choix
de variable, c'est la **chaîne** de prédiction. `1139` n'est d'ailleurs dans **aucun** des
registres `_PREDICTION_MINMAX_*` : sa prédiction n'avait jamais été confrontée. Le porteur
`admecDestroyer` porte `HeavyWeapon_ExtraDmg` et `HeavyGravCannon`.

**Conséquence, écrite sans la maquiller** : l'argmax est conforme quand l'écart est monotone sur
les cibles (montage A — même position, même cible, y compris le kill-sure) et **peut diverger**
quand il ne l'est pas (montage B — natif `(1,6)`, port `(1,5)`).

## 4. Contre-épreuves — 11 mordantes, 0 muette

`scripts/python/probe_975_mutations.py`, montage B, `--advance-turns 1` :

* **REACHABILITY** (retirer le playbook de `PLAYBOOKS` et rejouer `engine_validate.engine_decide`) :
  **5/5 ATTEINTES**. Sans le playbook, quatre porteurs retombent sur l'attaque normale (ability 69)
  et 1139 sur sa voie Comparable avec une **autre** utilité (38.68 contre 32.11).
* **FIDÉLITÉ**, un terme à la fois : gate `1 < Count` de 1221 neutralisé → le port change de cible
  ET de position ; `MIN_UTILITY` de 1116 porté à 3 → abstention ; `AffectedTileAmount` rabattu à 1
  → abstention ; `HasAnyRepairTarget` forcé à `True` → `should_evaluate = False` ;
  `HasEnemyInRange` forcé à `False` → abstention ; plancher `+1` de 1139 retiré → valeur décalée
  d'exactement 1. **6/6 mordantes.**

⚠ **Le probe s'est d'abord trompé lui-même**, et le noter fait partie du résultat : au premier
passage il rendait **3 INERTE sur 5**, parce qu'il appelait `engine_decide` **sans `predictor`**.
Sans lui `ctx.scene` est `None`, donc `1139._ability_prediction` rend `None` et
`1116.affected_tile_amount` retombe sur son plancher — deux abstentions qui n'ont rien à voir avec
l'inscription au registre. Un banc peut fabriquer le vice qu'il est censé détecter.

Le montage **B** est la contre-épreuve du gate de 1221 : avec **un seul** ennemi adjacent au
Beserk, l'oracle passe de `non-vides = 4` à `non-vides = 1` et le natif **change de position**
(`(4,5)` → `(3,4)`, où deux ennemis sont adjacents). Le port fait exactement le même mouvement.

## 5. Ce qui n'est PAS couvert

* **#975-r1** — le gate de 1087 est une **BORNE SUPÉRIEURE**. `GetValidTargets(caster, <position
  ARBITRAIRE>, naType)` n'est exposé par aucun RPC : `abilityTargets` ne répond que pour la
  position courante et l'union sur les tuiles de **move**, `castFromTiles` balaie
  `GetMovableTilesFor`. Or 1087 est un **téléport** (`RANGE_WHOLE_BOARD`), donc ses destinations
  sont massivement hors de cet univers. Le port mirrore les deux étages dominants (portée d'attaque
  max, `IsTargetTileObscured`) et laisse de côté fog, walkability de la cible et bits du masque —
  trois filtres qui ne peuvent que RETIRER des cibles. Point d'ancrage à hooker :
  `IdunBattle.Core.Services.BattleQuery$$GetValidTargets` (surcharge 3 params), ou un paramètre
  `fromTile` sur `abilityTargets`.
* **#975-r2** — le sweep d'aim de 1087 part de `fromHere` seul (l'utilité étant constante,
  `AddAction` ne remplace jamais : balayer plus de positions ne changerait que la tuile de cast).
* **#975-r3** — l'écart de prédiction de 1139 (§3).
* **#975-r4** — la **tuile visée** de 1087 et de 1116 n'est pas confrontable directement :
  `ncEvaluate` publie `action.targetLow`, le dword bas d'un **pointeur d'entité**, pas un id de
  tuile. Seules l'utilité et la position de cast sont opposables.
* `TotalRepairActionsAmount` (3ᵉ terme d'`AffectedTileAmount`) rend **0** offline — résidu déjà
  documenté sur le nœud ; exact tant qu'aucun Mechanic ami n'a soigné.
* Un seul board (`MC1_67`) et deux seeds de placement : la géométrie de 1116 (ligne) mériterait un
  second board à élévation marquée.
