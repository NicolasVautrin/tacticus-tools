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

## 5. État — ce qui reste à établir

Ce document est à l'état FINAL sur les points 1 à 4 (lecture du décompilé, close). Ce qui reste
ouvert est nommé au §6 de la fiche et dans le rapport de tranche.
