# #447 — `AddCasterIfMatchesDynamicRule` : la TROISIÈME cascade entre au port, et le canal de mesure était muet

**Livré le 2026-08-02.** Build de référence : `rnca9r7q6c`. Tranche 4 de `#429-r2`.

## 1. La règle, et pourquoi elle plutôt qu'une autre

Re-dérivation du gisement (`python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps`)
avant la tranche : **22** règles GATE non portées sur 46. Le classement par masques armés donnait
`CasterIsPossibleTarget` (13) en tête, puis `CasterHas2TurnsLeft` (3), `TargetIsNotAnObject` (3),
`AddCaster` (2)… et `AddCasterIfMatchesDynamicRule` (**1**).

**Le premier du classement est mort sur le chemin du CAST, et c'est une mesure.** Sa branche dans
`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` exige `options+0x00 == 0` (ability
NON self-castée), alors que l'aiguillage qui mène à cette cascade — `TargetingQuery$$GetInvalidTargetReason`
surcharge 5 arguments — n'y branche QUE sous `if (*(char *)options != 0)`, c'est-à-dire self-cast
POSÉ. Les deux conditions sont contradictoires : les **13** masques n'arment cette règle que par
l'autre appelant, `TargetingQuery$$GetValidTargets` (l'énumération preview/IA). Le porter, c'est
porter cette énumération — résidu déjà nommé par `case-429` §7, pas une tranche de ciblage.

Les autres candidats, mesurés :

| règle | masques armés | verdict de confrontabilité |
|---|---|---|
| `CasterHas2TurnsLeft` (52) | 3 | `BattleQuery$$HasMinimumRemainingTurns` rend **true** quand le `Dictionary` de limites de tours n'a pas d'entrée — un duel de runner n'en a pas. Inerte au montage. |
| `TargetIsNotAnObject` (33) | 3 | la cible doit porter le trait `Object`. Ses **28** porteurs sont tous des `LootObj_*` **npc** posés par le board : montage par injection catalogue, non tenté. |
| `CasterCanMove` (28) | 1 | déjà tranché dans `abilities/loki/strike.py` (`ThunderousAssaultAbility`) — l'unique poseur de blocage du build est `InstinctiveBehaviourBlockMovementEffect`, et le trait `0x418 Stationary` n'atteint aucun porteur de 1043. Demi-mirror invalidable. |
| **`AddCasterIfMatchesDynamicRule` (3)** | **1** | porteur **HERO au pool** (`tyranDeathleaper`), régime discriminant présent **au déploiement** (trait `TeleportStrike`), dégradation **permissive** déjà nommée dans le code. |

Le rayon est donc de **1 ability** — et c'est un argument, pas un aveu : le risque d'un port de
règle est symétrique (un port trop strict casse des casts légitimes en masse), et ici il est borné
par construction. Le compte se re-dérive : `probe_447_add_caster_dynamic_rule.py --offline`.

## 2. Le natif, verbatim

`TargetingQuery$$GetCasterNotAddedReason` est une chaîne `if / else if / else` — les branches sont
**mutuellement exclusives** et leur ordre tranche :

```
if ((char)rules < 0) return valide;          # bit 7  AddCaster -> court-circuit
if (rules & 0x8) {                           # bit 3  AddCasterIfMatchesDynamicRule
    r = options[+0x30].Invoke(caster, casterTiles); if (r) return broken(r);
} else if (rules & 0x400000) { ... }         # bit 22 (0 porteur au registre)
else if (options+0x00 == 0 && !(rules & 0x800)) { ... }   # bit 15 CasterIsPossibleTarget
else { if (GetValidTargets(...).AllTargets.Count == 0) return broken(0x800); }
```

Unique porteur du bit 3 : **1115 `FearOfTheUnseen`** (masque `0x18`, self-cast), dont
`FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` tient en une ligne —
`return -(uint)(IsTeleporting(caster, state) != 0) & 4;` — soit `CasterMatchesDynamicRule` (0x4).
`IdunBattle.Entities.UnitExtensions$$IsTeleporting` est un OU sur quatre `EffectType`, chacun testé
en OWNER puis en TARGET : `0x40c`/`0x40b` (`TeleportStrike_*`) et `0x4d9`/`0x4d6`
(`FearOfTheUnseen_*`). C'est **exactement** le « and is not in Deep Strike » du texte i2 de
l'ability, dont l'autre moitié — « has not moved this turn » — est le bit `CasterHasNotMoved` du
même masque, déjà porté.

⚠ **Le natif rend le code de la DÉLÉGUÉ, jamais le bit 3.** Ce bit n'est qu'un aiguillage.

## 3. Le canal de mesure était MUET, et il l'aurait été en silence

`abilityReason` — le canal réflexe pour ce gisement — publie **`0x1 ValidRequest`** dans le seul
régime discriminant. Il passe par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`,
qui court-circuite sur `ActiveAbility$$get_CanCurrentlyBeUsed` **avant toute cascade** ; or 1115
porte `initialCooldownTurns = 1`, et le Deep Strike du trait `TeleportStrike` expire au bout d'un
round. Les deux fenêtres ne se recouvrent qu'au tour de déploiement, où le cooldown gagne.

Un lecteur naïf y aurait vu « ability indisponible » et conclu **non confrontable**.

**Le canal juste est `abilityTargets.fromHere`** : son chemin natif
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets` ne gate que sur `IsAlreadyUsedThisTurn` —
pas de `get_CanCurrentlyBeUsed` (relu au décompilé). Il est binaire : le caster est dans la liste,
ou il n'y est pas.

**Son attribution a dû être établie, pas supposée.** `TargetingQuery$$GetValidTargets` n'appelle pas
`GetCasterNotAddedReason` : il **ré-implémente** l'ajout du caster dans le même ordre (bit 7, puis
`isSelfCasting || bit 11` **si la liste est déjà non vide**, puis bit 22, puis bit 3). Pour 1115
(`RANGE_SELF`), `GetPossibleTargetsForOptions` rend **zéro** cible, donc l'étage `isSelfCasting` ne
peut rien ajouter et le seul chemin d'ajout restant est la branche du bit 3. Le probe imprime
`targets` à côté de `fromHere`, et la garde échoue si `targets != 0`.

## 4. Ce qui est porté

* `engine/runner/components.py::is_teleporting` — mirror de `UnitExtensions$$IsTeleporting`.
  `set_moved_flag` l'appelle désormais : le natif **inline** la même chaîne (mêmes quatre littéraux,
  même ordre, mêmes deux rôles), donc les deux lecteurs du port partagent UNE source.
* `engine/runner/abilities/targeting.py::get_caster_not_added_reason` — les deux premières branches.
  `AddCaster` rendait déjà `0`, mais **par défaut** ; il est désormais rendu par la BRANCHE (gain de
  fidélité structurelle, pas de comportement).
* `engine/runner/abilities/tyranids.py::FearOfTheUnseenAbility.get_dynamic_invalid_caster_reason`.

Restent non portées, permissives et nommées : bit 22 (`HasFreeTilesInRange`, **0** porteur) et la
branche `else` (`GetValidTargets`, l'énumération — c'est elle qui rend `0x800` chez Chronometron 1226).

## 5. La confrontation — `probe_447_add_caster_dynamic_rule.py`

Trois régimes contre le natif, sur `MC1_67`/777 puis `C3_01`/31337 :

| régime | natif (`targets`/`fromHere`) | port | lecture |
|---|---|---|---|
| **R1** déploiement, Deep Strike actif | 0 / 0 = **REFUS** | `0x4` | **la ligne fermée** : `master` rendait `0x0` = ACCEPTE |
| **R2** un round plus tard, effet expiré | 0 / 1 = VALIDE | `0x0` | face restrictive : rien n'est cassé |
| **R3** après un move | 1 / 0 = REFUS | `0x10` | **ordre** : la cascade CASTER précède, c'est `CasterHasNotMoved` qui doit sortir |

Quatre contre-épreuves, chacune vérifiant d'abord que sa mutation a mordu : masque privé du bit 3
(= l'état de `master`) → `0x0` ; masque + `AddCaster` → `0x0` (le court-circuit **antérieur** gagne) ;
déléguée neutralisée → `0x0` (c'est la déléguée qui décide, pas le bit) ; flag `Moved` posé offline
dans le régime R1 → `0x10` (régime que le live ne peut pas produire — **mesuré : un move fait expirer
le Deep Strike**, l'unité ayant « agi »).

**Généralisation** : second couple (board, seed) ci-dessus, plus `darkaCompanion` (Dark Angels) et
son `CalibaniteGreatsword` (1189, masque `0x80` = `AddCaster` seul) sur `C4_09`/999 — l'autre branche
portée, une autre faction. Ce bloc est une **non-régression**, pas une discrimination : le port
rendait déjà `0`. Dit dans le probe.

**Contre-épreuve du fix lui-même** : branche du bit 3 neutralisée → `probe_447` rend `FAIL` sur R1
(`port=0x0`) et `probe_429` reclasse la règle en non portée (26 → 25 portées). Arbre restauré.

## 6. Trouvé en chemin : le compteur de #429 ne pouvait pas voir ces deux règles

Le critère de dérivation de `probe_429` est « le port peut RENDRE `int(TR.<X>)` ». Il est
**structurellement aveugle** à deux familles, parce que **le natif lui-même ne rend jamais leur
code** : les court-circuits (`AddCaster`) et les points d'extension (`TargetMatchesDynamicRule`,
`CasterMatchesDynamicRule`, `AddCasterIfMatchesDynamicRule`, dont le natif rend le code de la
déléguée). Les deux premiers étaient comptés portés **par accident** — parce qu'une ability
(`SorcerousFacade`) rend le bit du point d'extension comme code, ce qui est une propriété de
l'ability, pas du port de la règle.

D'où `Role.ported_by = (fonction du port, jeton)` et `rules_ported_by_delegation()` — **toujours une
dérivation** (AST), avec la **fonction porteuse** comme granularité : `get_dynamic_invalid_caster_reason`
a DEUX foyers d'appel (`get_invalid_caster_reason` sous le bit 2, `get_caster_not_added_reason` sous
le bit 3), et un critère « la méthode est appelée quelque part » aurait compté le second porté alors
que seul le premier l'était.

Trois gardes dans `test_targeting_rule_inventory.py`, contre-épreuves jouées : fonction porteuse
inexistante → ROUGE ; `ported_by` posé sur une règle qui EST un code de refus → ROUGE ; jeton absent
de la fonction → la dérivation reclasse en non portée.

**Compteur** : `regles GATE 46 ; PORTEES 24 -> 26 (dont 4 par délégation/court-circuit) ; NON PORTEES
22 -> 20`. Abilities touchées par ≥ 1 règle non portée : **26 → 23** / 103. ⚠ Chiffres à re-dériver.

## 7. Résidus nommés

* **`#447-r1` — la branche `CasterIsPossibleTarget` est morte sur le chemin du CAST** (§1). Ses 13
  masques ne mordent que par `TargetingQuery$$GetValidTargets`. Fermer le résidu = porter cette
  énumération, pas la branche.
* **`#447-r2` — `abilityReason` ne peut pas exprimer un refus d'une ability en cooldown.** Le gate
  `get_CanCurrentlyBeUsed` d'`AttackQuery` précède la cascade et rend `0x1 ValidRequest`, valeur qui
  signifie AUSSI « tuile-cible non marchable » ailleurs. Tout lecteur de ce canal doit croiser
  `abilityState.cooldown` avant de conclure. Aucun capteur neuf n'est requis pour #447 —
  `abilityTargets` suffit — mais le piège vaut pour les tranches suivantes.
* **`#447-r3` — le régime « Deep Strike ET caster ayant bougé » n'est pas atteignable en live** : un
  move fait expirer `TeleportStrike_TeleportingIn` (l'unité a agi). L'ordre y est prouvé OFFLINE
  (CE4) et, en live, par le régime R3 (hors Deep Strike, après move).
* **`#447-r4` — `get_invalid_target_reason` seul saute le volet CASTER.** L'ordre natif complet
  (`GetInvalidCasterReason` puis l'aiguillage self-cast) n'est réalisé que par `is_invalid_target`.
  Les appelants qui prennent `get_invalid_target_reason` directement (`valid_normal_attack_targets`,
  et le premier jet de ce probe) mesurent une cascade amputée. Non corrigé ici : c'est la structure
  existante du module, et la changer touche tous ses appelants.

## 8. Re-dériver

```
python scripts/python/probe_447_add_caster_dynamic_rule.py --offline          # rayon, sans session
python scripts/python/probe_447_add_caster_dynamic_rule.py --generalize
python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps
python -m pytest tests/engine/runner/test_add_caster_dynamic_rule_live.py tests/engine/runner/test_targeting_rule_inventory.py -q
```
