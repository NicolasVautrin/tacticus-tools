# case-407 — le canal BLOCK ne se ferme PAS comme le crit, mais son état est per-ATTAQUE

> Piste d'entrée (utilisateur) : « le même mécanisme que #440 existe côté block ».
> **Verdict : à moitié.** Il n'existe **aucun gate booléen** côté block. Ce qui existe, et que le
> port ratait, c'est un **état d'attaque** : la failed-block list, portée par l'`OngoingAttack`.

## 1. Les trois questions, et leurs réponses

| # | Question | Réponse |
|---|---|---|
| 1 | `result[+0x21]`, discriminant du fork d'`ExecuteHits`, est-il `didCrit` ? | **OUI** — et par une chaîne LUE, pas seulement par la mesure (cf. §2) |
| 2 | Existe-t-il un gate qui FERME le canal block (0 tirage aux coups suivants) ? | **NON en booléen ; OUI par SOURCE** — la failed-list, de portée **ATTAQUE** |
| 3 | Le port le manquait-il ? | **OUI** — il repartait d'un set vide à chaque `_run_hits`. Live : **6/6 seeds**, port livré 6/6, ancien port 0/6 |

## 2. `OperationResult+0x21` = `didCrit` — la chaîne, lue

`case-366-r1-crit-multihit` §2.1 l'établissait **par la mesure** (le décompilé « ne le nomme pas »).
La chaîne existe et se lit de bout en bout :

```
AttackDamageOperation$$ExecuteHit : slot 0xb d'IDamagePrediction (CalculateCriticalDamage)
        -> struct {int damage, byte didCrit @+4}          ; local_630
        -> DamageInfo[+0x1C]                              ; packé dans le message de la sub-op 0x42
DealDamageOperation$$Execute      : slot 0xc (CalculateDamageOperation)
        -> DamageAppliedResult[+0x0E] = DamageInfo[+0x1C] ; simple recopie
        -> OperationResult[+0x21]    = DamageAppliedResult[+0x0E]
```

Le jumeau se lit de la même façon : `OperationResult[+0x22]` = `DamageAppliedResult[+0x0C]` = le
`didBlock` d'`ApplyRandomBlockDamage`. Verdict #440 **confirmé**, sur une seconde source.

Bénéfice collatéral — les slots de `IDamageCalculations` sont nommés (arités relues sur les corps) :
`0 = CalculateBlockChances(attacker, defender, failedBlockIds)`, `1 = CalculateEvasionChance`,
`2 = ApplyRandomBlockDamage(blockChances, damage)`,
`3 = ApplyRandomEvasion(evasionChance, damage, attacker, defender)`,
`4 = ApplyBlockDamage(blockChances, damage)` (surcharge « blockChances »),
`0xc = CalculateDamageBlockedByShield`. D'où la forme réelle de
`DamagePrediction$$CalculateDamageOperation` : **évasion d'abord, block seulement si pas d'esquive**,
et un `damageInfo[+0x1D]` (service de garantie) qui donne un block **sans tirage**.

## 3. Pourquoi il n'y a PAS de gate block

`AttackDamageOperation$$Execute`, fin de corps :

```
attack[+0x38] |= hitGroup[+0x3d]      ; « a crité »  (OR collant)
attack[+0x39] |= hitGroup[+0x3e]      ; « a bloqué » (OR collant)
attack[+0x40] &= hitGroup[+0x3c]      ; isCriticalDamageAllowed   <-- LE GATE, crit SEUL
attack[+0x28] += hitGroup[+0x4c]
```

Les deux flags collants sont **symétriques**, le `&=` ne l'est **pas** : aucun analogue block.
Et la polarité est inverse — `ApplyRandomBlockDamage` sort en `return` au 1er **succès**, AVANT
`BlockDamageInfo$$AddFailedBlockId` : une source qui RÉUSSIT reste jouable, seul l'**échec** exclut.

## 4. Le vrai état inter-coups : `OngoingAttack+0x48`

```
OngoingAttack$$.ctor              : +0x48 = new List<int>()      ; NEUVE par attaque (comme +0x40 = 1)
ADamageOperation$$GetFailedBlockIds : HasCurrentAttack() ? GetCurrentAttack().FailedBlockIds
                                                          : new List<int>()
ADamageOperation$$SetupHitGroup   : hitGroup[+0x60] = <cette liste>          ; PAR RÉFÉRENCE
AttackDamageOperation$$ExecuteHits: options[+0x30] = hitGroup[+0x60]         ; à chaque coup
ADamageOperation$$RegisterBlocks  : hitGroup[+0x60].AddRange(result[+0x28])  ; ids échoués du coup
DamageCalculations$$CalculateBlockChances : Contains(failedBlockIds, id) -> continue  ; 0 TIRAGE
```

`Execute` ne construit **qu'un** `OngoingHitGroup` — partagé par la phase d'arme, les coups bonus et
`ExecuteAdditionalHitsWithoutDamageProfileType` — et la voie À PROFIL
(`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → nouvelle `Execute` → nouveau
`SetupHitGroup`) **re-lit la même liste** de l'`OngoingAttack`. ⇒ l'exclusion traverse **toute
l'attaque**, exactement comme `isCriticalDamageAllowed`.

## 5. Le port

| natif | port |
|---|---|
| `OngoingAttack+0x48` / `hitGroup+0x60` | `_run_hits(failed_block0=…)` → `failed_block`, rendu en `failed_block` |
| `RegisterBlocks` → `AddRange` | `failed_block.update(dmg.failed_block_ids)` (inchangé, #72) |
| `CalculateBlockChances` → `Contains` → `continue` | filtre `s.block_id not in failed_block` (inchangé, #72) |
| portée ATTAQUE (traverse les sous-opérations) | threading `failed_block0` → `additional_hits` → `damage_ops/{normal,ability}.py` |

Le port copie (`set(failed_block0 or ())`) là où le natif partage par référence : équivalent, aucun
lecteur du port n'atteint la liste hors du threading.

## 6. Mesure

`probe_407_failed_block_attack_scope.py` — `orksRuntherd` (SquigHound, 2 coups additionnels profil
Physical p1) vs `ultraApothecary`, `--armor-target 6000 --crit 0,0 --block-target 10,5` (chance
BASSE ⇒ la source échoue au coup d'arme). Rejeu double sur le **même** flux RNG : port livré vs
contrefactuel qui avale `failed_block0`.

```
seeds 12345,314159,88,777,31337,2026  ->  discriminants 6/6 | livre 6/6 | sans_threading 0/6
ex. seed 88 : groupe live [37, 37] | livre [37, 37] | sans threading [37, 29]
```

L'écart tombe sur le **2e** coup du groupe (le `next_bool` en trop est consommé APRÈS le
`GetDamage`/resolve du 1er) ⇒ comparer le seul 1er coup rend la garde aveugle (0/5 à l'index 0).

Gardes : `tests/engine/runner/test_failed_block_attack_scope_live.py` (3 seeds) et
`..._offline.py` (5 tests : portée, polarité, chaînage). Contre-épreuve mesurée (mutation
`failed_block = set()` dans `_run_hits`) : **2 rouges offline, 3 rouges live**.

## 7. Ce qui n'est PAS couvert

* **Hors attaque** (`!HasCurrentAttack` ⇒ liste neuve par hitGroup) : non confronté — le port y
  passe `failed_block0=None`, ce qui est le même comportement, mais aucun montage ne l'exerce.
* **`damageInfo[+0x1D]`** (block GARANTI via le service `FUN_180003b70(4, …, 1)`, → `ApplyBlockDamage`
  sans tirage) et **`damageInfo[+0x1E]`** (trait de damage profile qui saute block ET évasion, posé
  par `ExecuteHit` depuis `DamageProfile$$HasTrait(0)`) : le port ne modélise que le second, sous
  le nom `NoBlocking` (#65). Le premier n'a pas de porteur identifié.
* **L'ordre évasion-puis-block** de `CalculateDamageOperation` : le port a les deux branches en
  XOR (`evasion_branch`) et passe toujours `False`. Équivalent tant qu'`evasionChance == 0` (0
  tirage). Résidu nommé, préexistant.
* **`OngoingAttack+0x3c`** (compteur de coups bloqués, incrémenté par `UpdateCurrentAttackAfterHit`,
  lu par `FinishAttackOperation$$Execute`) : aucun consommateur côté port.
