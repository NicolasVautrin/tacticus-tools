# `#419-r3` — `isOutsideAttack = false` : la prémisse « tous les call-sites posent 1 » est FAUSSE

**Question binaire posée** : *un seul call-site de `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage`
laisse-t-il l'octet `+0` du `Nullable<AttackDamageBehaviourOptions>` à ZÉRO ?*

**Réponse mesurée : QUINZE sur DIX-HUIT.** Le résidu ne se ferme pas par la mesure — il s'ouvre.

---

## 1. L'identification de #725 est VÉRIFIÉE (pas re-dérivée : confrontée)

Le nom `isOutsideAttack` et le chemin `+0` -> `AttackDamageOptions+0x2e` sont confirmés par **deux**
lectures indépendantes de celle de #725 :

1. **La signature déclarée** de
   `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
   porte `isOutsideAttack:System.Boolean` en **dernier paramètre**
   (`data/symbols/<build>/frida/methods.tsv`) — et `AttackDamageOperation$$Execute` lui passe
   exactement `options+0x2e`. Le nom n'est donc pas seulement attaché au 1ᵉʳ argument de
   `ADamageOperation$$GetCurrentAttackOrDefault` : **deux** consommateurs le nomment identiquement.
2. **Le ré-ordonnancement**, recalculé à partir du décompilé de
   `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` : les sept octets
   `behaviour+0x98..+0x9e` sont recomposés en un qword posé à `AttackDamageOptions+0x28`, et
   `behaviour+0x98` (= l'octet `+0` des options) y occupe l'octet **6** — donc `0x28 + 6 = 0x2e`.
   Ordre complet mesuré : `+0x9b, +0x99, +0x9a, +0x9c, +0x9d, ?, +0x98, +0x9e`.

Le routage, relu :

| `isOutsideAttack` | slot d'`IBattleQuery` | nom / arité | corps |
|---|---|---|---|
| `false` | **200** | `GetCurrentAttackOrDefault` / 0 | `MatchState.GetCurrentAttack()` si le state porte une attaque, sinon `new OngoingAttack()` |
| `true`  | **201** | `GetDefaultAttack` / 0 | `new OngoingAttack()` **inconditionnel** |

(Slots LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`.)

## 2. Le balayage — EXHAUSTIF, 18 call-sites sur 18

`IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` porte **22 xrefs** : **4 DATA** (table de
méthodes / metadata, aucun code) et **18 `UNCONDITIONAL_CALL`**, réparties sur **15 fonctions**.
Les 18 ont été décompilées et lues. Aucune n'est restée non lue.

Deux formes de « zéro » se présentent, et elles sont **équivalentes en aval** — le ctor du behaviour
passe par `Nullable<T>.GetValueOrDefault()`, donc un `Nullable` sans valeur rend la struct `default`,
dont l'octet `+0` vaut `0` :

* **`Nullable` NUL** (`hasValue = 0`, `+0x20` du bloc de 0x28 octets à zéro) — le C# écrit
  `options: null`, c.-à-d. l'argument optionnel omis ;
* **`Nullable` porteur, octet `+0` à zéro** — la struct 0x20 est bien construite, mais son premier
  octet reste `0` (d'autres octets, eux, sont posés).

| # | fonction appelante | forme | octet `+0` |
|---|---|---|---|
| 1 | `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` | porteur | **0** |
| 2 | `IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamageBehaviour` | nul | **0** |
| 3 | `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonOfHorus_NormalAttackAbility$$GetAdditionalDamageBehaviour` | nul | **0** |
| 4 | `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathToTheFalseEmperorAbility$$GetFinalBehaviour` | porteur | `1` |
| 5 | `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility$$CreateBehaviour` | porteur | `1` |
| 6 | `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyBoltPistolAbility$$CreateBehaviour` | porteur | `1` |
| 7 | `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour` | nul | **0** |
| 8 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateBehaviour` (1ᵉʳ) | porteur | **0** |
| 9 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateBehaviour` (2ᵉ) | porteur | **0** |
| 10 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGait_TriggerAttackAbility$$CreateBehaviour` | nul | **0** |
| 11 | `IdunBattleLogic.Entities.Abilities.Active.TestMultipleHitGroupsWithDifferentDamageProfileTypesAttackDamageAbility$$ExecuteBehaviour` (1ᵉʳ) | nul | **0** |
| 12 | idem (2ᵉ) | nul | **0** |
| 13 | `IdunBattleLogic.Entities.Abilities.Active.TestTwoHitGroupsAttackDamageAbility$$ExecuteBehaviour` (1ᵉʳ) | nul | **0** |
| 14 | idem (2ᵉ) | nul | **0** |
| 15 | `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour` | nul | **0** |
| 16 | `IdunBattleLogic.Entities.Abilities.Active.Loki.Fealty_NormalAttackAbility$$GetAdditionalDamageBehaviour` | nul | **0** |
| 17 | `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` (1ᵉʳ) | nul | **0** |
| 18 | idem (2ᵉ) | nul | **0** |

**Bilan : `0` pour 15 sites, `1` pour 3.** Le `true` est l'EXCEPTION, pas la règle — et il désigne
précisément les trois coups tirés *depuis l'intérieur* d'une attaque qu'il faut en SORTIR
(`DeathToTheFalseEmperor`, `HazeCorruption_BonusHit`, `HeavyBoltPistol`).

⚠ **Le site nº1 est l'ATTAQUE NORMALE elle-même** (`ALoki_NormalAttackAbility`), dont dérivent les
huit attaques normales spécialisées. C'est le call-site le plus chaud du jeu, et il pose `false`.
Sa struct d'options n'est pas nulle : elle est construite, l'octet `+6` y est posé par un appel
virtuel (`vtable+0x4b8`), et l'octet `+0` y reste à `0`.

## 3. Où la prémisse s'est cassée

#725 conclut : « *Le port ne modélise AUCUNE `OngoingAttack` partagée, ce qui EST la sémantique
`true`. Poser le drapeau serait un no-op.* » La phrase est fausse **deux fois** :

* **Sur le natif** : `true` n'est pas ce que posent les call-sites — 15/18 posent `false`.
* **Sur le port** : le port modélise DÉJÀ plusieurs champs de l'`OngoingAttack`, threadés
  explicitement au lieu d'être portés par un objet — `hit_index0` (`OngoingAttack+0x30`),
  `crit_allowed0` (`+0x40`, #366-r1-crit-multihit), `failed_block0` (`+0x48`, #407),
  `hit_group_index` (`+0x34`, consommé par `IsFirstHitGroupInAttack`). Ce qui manque n'est donc pas
  « l'objet » mais le **choix de la SOURCE** de ces valeurs au moment où une feuille `AttackDamage`
  démarre : état neuf (`true`) ou état hérité de l'attaque en cours (`false`).

## 4. Ce que `false` change OBSERVABLEMENT — lecture des consommateurs

Champs de l'`OngoingAttack` LUS par `IdunBattle.Operations.AttackDamageOperation$$Execute` après
`GetCurrentAttackOrDefault`, et valeur qu'ils prennent sur un objet NEUF
(`IdunBattle.Core.OngoingAttack$$.ctor`) :

| champ | rôle lu | valeur si `true` (objet neuf) |
|---|---|---|
| `+0x34` | `hitGroupIndex`, 4ᵉ argument de `GetAttackHits` (slot **182** `GetAttackHits` / 5) | `0` |
| `+0x34 == 1` | gate d'entrée d'`ExecuteAdditionalHitsWithoutDamageProfileType` | jamais vraie |
| `+0x40` | `isCriticalDamageAllowed`, passé à `ADamageOperation$$SetupHitGroup` | `1` (crit toujours permis) |
| `+0x28` | accumulateur de dégât refusé (`+= hitGroup+0x4c`) | reparti de `0` |
| `+0x38`/`+0x39` | drapeaux OU-és depuis `hitGroup+0x3d`/`+0x3e` | reparti de `0` |
| `+0x50` | liste lue par `ExecuteAdditionalHitsWithoutDamageProfileType` | liste NEUVE, vide |
| `+0x10`/`+0x18` | `casterId` / `targetIds`, lus par `DealDamageOperation$$HasMatchingOngoingAttack` | `0` / `null` |

⚠ **Une asymétrie qui limite la portée du drapeau, et qu'il faut lire pour ne pas sur-porter** :
`ADamageOperation$$SetupHitGroup` **ne reçoit pas** `isOutsideAttack`. Il relit la liste
`attack+0x48` (`FailedBlockIds`) depuis le **state**, inconditionnellement, pour la poser en
`hitGroup+0x60`. Donc `failed_block0` (#407) **reste partagé même quand `isOutsideAttack == true`** :
ce canal-là n'est PAS gouverné par l'octet. Seul `isCriticalDamageAllowed` (`+0x40`), qui transite
par l'objet rendu, l'est.

## 5. Le régime où l'écart MORD — 2 abilities sur les 15, pas 15

Un `0` ne suffit pas : il ne se voit que si la feuille lit une `OngoingAttack` **déjà mutée**. Or
`IdunBattleLogic.Entities.DSLBehaviors$$Attack` ouvre une attaque neuve
(`StartAttackOperation$$Execute` → `MatchState$$StartAttack`, une pile). Chacun des 18 sites a donc
été reclassé sur sa POSITION dans l'arbre, et non sur la valeur de l'octet :

| position de la feuille | sites | `false` y est-il observable ? |
|---|---|---|
| PREMIÈRE dans son propre `Attack(...)` | 1, 7, 8, 9, 10, 15, 16, 17, 18 | **non** — l'attaque en cours y est neuve, `false` ≡ `true` |
| composée APRÈS une autre feuille du MÊME `Attack(...)` | 2, 3 (voie fold), 11-14 | **oui** |
| `isOutsideAttack = true` | 4, 5, 6 | sans objet |

* **Sites 17/18 (`FragBombAbility`)** : les deux feuilles passent par
  `IdunBattleLogic.Entities.DSLBehaviors$$SortedAttackSeries`, et
  `IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour$$Execute` émet `FinishAttack` puis
  `StartAttack` **à chaque changement de cible** — les deux sélecteurs (`Units(target)` et
  `AdjacentUnits(target) − Caster`) sont disjoints, donc chaque feuille est première de son attaque.
* **Sites 11-14** : `TestTwoHitGroupsAttackDamageAbility` et
  `TestMultipleHitGroupsWithDifferentDamageProfileTypesAttackDamageAbility` — deux feuilles dans un
  seul `Attack(...)`, donc affectées, mais ce sont des abilities de TEST sans porteur.
* **Sites 2/3/15/16** : `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` a **deux** appelants
  structurellement différents, et un seul mord :
  * `$$GetAdditionalTargetsAttackBehavior` (le CLEAVE) enveloppe la feuille dans son propre
    `Attack(...)` → non observable ;
  * `$$GetCustomNormalAttackBehaviour` (le FOLD primaire) rend `If(<cond>, <la feuille>)` **sans
    aucun `Attack`**, et `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` le compose (slot de
    vtable `+0x4e8`) entre l'`AttackDamage` d'ARME et
    `ExecuteAdditionalHitsWithDamageProfileType`, le tout dans **un seul** `Attack(...)`.
  Seules **deux** des quatre attaques normales concrètes ont ce second appelant : `Boltstorm` et
  `RighteousRepugnance`. `Fealty` et `TalonOfHorus` n'ont que le cleave (xrefs, lues).

**Le régime atteignable est donc : le FOLD primaire de `Boltstorm` et de `RighteousRepugnance`.**

## 6. Ce que le port en faisait, et la formulation exacte du défaut

`#419-r1-tr14-r4-r1` écrivait « le port ne modélise AUCUNE `OngoingAttack` partagée ». C'est faux :
il en modélise **trois champs**, threadés de la phase d'arme vers les groupes de coups additionnels
— `hit_index0` (`+0x30`, R6-b'), `crit_allowed0` (`+0x40`, #366-r1-crit-multihit), `failed_block0`
(`+0x48`, #407). Ce qui manquait n'était pas l'objet, c'était **une feuille d'attaque NUE** :

> `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` finit par
> `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor`, donc pousse un `OngoingAttack` neuf par
> cible. Le port n'avait que cette factory-là. Toute feuille montée avec elle est, par
> construction, `isOutsideAttack = true` — d'où le titre du résidu.

Le symptôme avait déjà été VU une fois sans être nommé : le champ `is_first_hit` de
`AttackWithAttackDamage` (case-221) existe précisément parce que « le `hitIndex` court d'une feuille
à l'autre » sur `HazeOfCorruption_DamageTransferEffect`. C'en était la forme booléenne partielle.

**Le port** (`#419-r3`) ajoute `attack_state0` à la feuille et le thread **au seul volet FOLD** :

* `operations/damage_hits.py::attack_state_out(r, ah)` — l'état en sortie d'une opération de dégât ;
* `damage_ops/normal.py` et `damage_ops/ability.py` le rendent sous la clé `attack_state` ;
* `damage_ops/ability.py::execute_ability_attack(hit_index0=, crit_allowed0=, failed_block0=)` ;
* `abilities/behaviours/combat.py::AttackWithAttackDamage(attack_state0=)` — défaut `None` = neuve ;
* `abilities/loki/additional_targets.py::primary_fold_tree(attack_state0=)`, **pas** `cleave_tree` ;
* point de MUTATION : `additional_targets.py::fold_inherits_attack_state()`.

## 7. La mesure — et les DEUX fausses pistes que la garde de montage a nommées

`probe_419r3_fold_attack_state.py`, montage de `probe_478` (`--regime rr`, `adeptMorvenn`, porteur
NATUREL de `RighteousRepugnance`) plus **un seul** degré de liberté : la `CritChance` du porteur.

Le premier passage a rendu un état d'attaque **ARMÉ** (`next_hit_index = 2`, `crit_allowed = False`)
pour un observable **qui ne bougeait pas**. Le probe l'a refusé au lieu de le rendre vert : les trois
canaux y étaient algébriquement inertes — `failed_block` vide (aucune source de block au montage),
`next_hit_index` lu seulement par `getstuckin_combat_chance` (le porteur n'a pas `GetStuckIn`), et
`crit_allowed` invisible tant que `CouldCrit` est faux, car `_roll_crit` sort alors sur `False`
**sans tirage des deux côtés**.

Deux tentatives d'ouvrir le canal ont échoué, chacune pour une raison qui aurait produit une mesure
mensongère si la garde ne l'avait pas nommée :

1. une `CritChance` posée dans une **seconde** occurrence de `--unit-stat` a mordu **côté natif
   seulement** (coups natifs `787, 969, …` → `969, 1073, …`, port strictement inchangé) — une
   mutation à un seul côté fabrique une divergence de MONTAGE qui se lit comme un bug de port ;
2. `CouldCrit` est une **conjonction** (`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` :
   `GetStat(9) > 0 && GetStat(10) > 0`) : avec la seule `CritChance`, le port lisait
   `(cc = 30, cd = 0, could_crit = False)` et le canal restait fermé.

Montage final : `CritChance = 30` **et** `CritDamage = 352`, dans la clause `--unit-stat` existante.
Le probe **REFUSE** de mesurer si `could_crit` est faux côté port.

| | coups sur la cible primaire | PV primaire |
|---|---|---|
| **NATIF** | `1225, 1073` (arme) puis `506, 557, 614` (fold) | 3975 |
| **PORT, héritage ON** (#419-r3) | `1225, 1073` + `506, 557, 614` | **3975** |
| **PORT, héritage OFF** (l'ancien) | `1225, 1073` + `506, 563, 526` | **3893** |

`a_mordu = True`, **rapporté séparément du verdict**. Le canal est le FLUX RNG, pas une valeur : le
gate « never crit » (`AttackDamageOperation$$ExecuteHits` : `options[+0x29] |=
(hitGroup.isCriticalDamageAllowed == 0)`) fait sortir `ExecuteHit` sur `isCrit = 0` **sans appeler
`RollCritical`** — un tirage de moins, et tous les coups suivants se déplacent.

L'inertie est assertionnée **dans les deux sens** : `a_mordu` vrai ⇒ au moins un canal non neutre
(sinon la différence vient d'un canal non modélisé) ; `a_mordu` faux ⇒ les trois canaux neutres
(sinon le canal est inerte et le vert ne prouve rien). Et l'étage 3 exige que le port SANS héritage
**diverge** du natif : sans lui, un étage 2 vert ne distinguerait pas « le port est juste » de « ce
montage ne discrimine pas ».

## 8. Non-régression rejouée

`probe_478_cleave_additional_targets.py --regime rr` VERT (le fold d'`adeptMorvenn` sans crit rend
toujours `502, 506, 557`, identique au natif) · `probe_419r1tr14r3_spread_paliers_kill.py` VERT ·
`probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py` écart port-natif **+0** ·
`probe_477r15a_stream_conformance.py` VERT (204/204 et 316/316) ·
`tests/engine/test_478_cleave_live.py` 13 passed ·
`tests/engine/test_344_ability_damage_average_{live,offline}.py` 15 passed.

## 9. Résidus NOMMÉS

* **`#419-r4` — les AUTRES feuilles nues ne sont pas threadées.** `attack_state0` n'est câblé que
  sur le FOLD. Restent : `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$
  CreateTargetTriggerBehaviour`, qui accumule **N** feuilles nues (une par `LeftOverDamage`) dans un
  seul `Attack(...)` — le port n'y passe que le booléen `is_first_hit` de case-221, jamais l'état
  complet ; et les deux abilities de TEST (sites 11-14), sans porteur. Le canal `hit_group_index`
  (`OngoingAttack+0x34`, lu par `IsFirstHitGroupInAttack`) n'est threadé nulle part : son
  INCRÉMENTEUR n'a pas été localisé — `ADamageOperation$$UpdateCurrentAttackAfterHit` n'écrit que
  `+0x30`. Débloqueur : trouver l'écrivain de `+0x34`.
* **`#419-r5` — le port lit `CritDamage = 0` là où le seed BC porte 352.** Mesuré en marge :
  `adeptMorvenn` porte `CritChance = 20` / `CritDamage = 352` dans `data/seed-bc.json`, et le port
  rendait `(cc = 20, cd = 0, could_crit = False)` sur l'état chargé — il a fallu poser `CritDamage`
  par `--unit-stat` pour ouvrir le canal. Conséquence : **aucun crit n'est possible côté port** sur
  toute unité dont ce canal est muet, donc `crit_allowed`/`RollCritical` y sont structurellement
  inertes. Non instruit ici (hors tranche) : reste à établir si c'est `buildNormalizedBC` qui remet
  le champ à zéro, ou le canal `combatSnapshot` qui ne le publie pas.
* **`#478-r3` (déjà ouvert)** — le câblage du fold vit au niveau MESSAGE
  (`visit_AttackUnitMessage`), donc les portes qui appellent `AttackDamageOperation.execute`
  directement (overwatch, `UseActiveAbility`, summon AI) n'en bénéficient pas. `#419-r3` hérite de
  cette borne sans l'élargir.

## 10. Ce qui n'est PAS couvert

* **Deux des trois canaux ne sont pas exercés** par ce montage : `failed_block` (aucune source de
  block) et `next_hit_index` (le porteur ne porte pas `GetStuckIn`). Ils sont portés par le MÊME
  paramètre et le même appel que `crit_allowed`, mais leur effet propre n'est pas mesuré.
  Débloqueur : un porteur `GetStuckIn` avec un fold, et une cible à `BlockChance > 0`.
* **La branche « `a_mordu` faux ⇒ les trois canaux neutres »** de l'algèbre n'est pas exercée : sur
  ce montage `a_mordu` est vrai. C'est une assertion de sécurité, pas un cran mesuré.
* **`Boltstorm`** n'est pas confronté : seul `RighteousRepugnance` l'est. Les deux partagent le
  foyer porté (`primary_fold_tree`), mais leur gate est INVERSE (`IsRangedPosition` vs
  `IsMeleePosition`) — le layout `boltstorm` de `probe_478` existe et reste à jouer avec le canal
  crit ouvert.
* **L'ORDRE des deux volets à l'intérieur du `Attack(...)`** : le natif joue
  `arme → FOLD → groupes à profil`, le port joue `arme → groupes (les deux voies) → FOLD`. L'état
  transmis au fold inclut donc les groupes à profil, que le natif n'a pas encore joués. Inerte sur
  ce montage (aucun groupe à profil), non couvert ailleurs.
