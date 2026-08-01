# case-366-r1-crit-multihit — le crit-roll s'ÉTEINT au premier coup qui ne crite pas

> Résidu ouvert par #411 (`1115`), **borné** par #366-r1/`1117` (« ne touche pas la cardinalité »),
> fermé ici. Il bloquait le plus large : **toute garde multi-coups à crit non nul était non
> confrontable**, et les trois tranches `InescapableAccuracy` ont dû se rabattre sur une salve d'UN
> coup à cause de lui.

## 1. Le critère, et sa réponse

> « Le natif et le port consomment-ils le MÊME NOMBRE de tirages par coup, sur toute la salve ? »

**Non — et l'écart n'est ni au coup 3, ni constant : il dépend du RÉSULTAT des coups précédents.**

`RollCritical` n'est appelé au coup `i` que si le coup `i-1` a **crité**. Au premier non-crit, le
canal se ferme **définitivement** pour l'attaque. Le port roulait un crit-roll à *chaque* coup :
jusqu'à `hits - 1` tirages de trop, et tout le per-coup décalé derrière.

L'hypothèse de départ (« deux tirages sur les deux premiers coups puis un seul ») était la
**projection d'un seul échantillon** : elle décrit le régime `cc = 50` du reproducteur et rien
d'autre. À `cc = 100` le natif consomme 2 tirages sur les **six** coups ; à `cc = 5`, 2 sur le seul
premier.

## 2. Le mécanisme, lu au décompilé

`IdunBattle.Operations.ADamageOperation$$SetupHitGroup` sème l'état (son 5ᵉ paramètre porte ce nom
dans la métadonnée) :

```
hitGroup[+0x3c] = isCriticalDamageAllowed          ; source = OngoingAttack[+0x40]
```

`IdunBattle.Core.OngoingAttack$$.ctor` pose `+0x40 = 1` dans ses **deux** surcharges ⇒ toute
nouvelle attaque rouvre le canal.

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`, boucle `i = 0 .. numHits-1` :

```
options[+0x29] |= (hitGroup[+0x3c] == 0)                  ; flag « never crit », MONOTONE (|=)
result = ExecuteHit(...)
...
if (result[+0x21] == 0)                                   ; le coup n'a PAS crité
    hitGroup[+0x3c] = options[+0x40] != null
                   && options[+0x40].Any(hitIndex => hitIndex == i + 1)
else
    hitGroup[+0x3d] = 1 ; hitGroup[+0x4c] += 1
```

La lambda est `IdunBattle.Operations.AttackDamageOperation.u003Cu003Ec__DisplayClass4_0$$u003CExecuteHitsu003Eb__0`
— corps entier : `return hitIndex == this.i + 1`.

Le gate est lu par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` :

```
if (message[+0x29] == 0) { if (!forceCrit) isCrit = RollCritical(...) }   ; le SEUL chemin qui tire
else                       isCrit = 0                                     ; 0 tirage
```

et `IdunBattle.Operations.AttackDamageOperation$$Execute` propage à l'attaque :
`attack[+0x40] &= hitGroup[+0x3c]` — l'extinction **traverse** les groupes de coups d'une même
attaque (coups bonus, groupes de profils additionnels), d'où le threading côté port.

**`options[+0x40]` est NUL pour tout ce que le port câble.** C'est un champ constant du behaviour
(`AttackDamageBehaviour+0xa0`, recopié dans le message à `+0x40` par
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`), et
`IdunBattle.Operations.AttackDamageOptions$$.ctor` met à zéro tout le reste de la struct. La règle
effective se réduit donc à « le crit-roll suit un crit ».

**Le mécanisme est PROPRE À LA FAMILLE ATTACK** : `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits`
a une boucle **plate** — ni `|=` sur les options, ni recalcul. D'où le gate `is_attack_damage_op`.

### 2.1 `OperationResult+0x21` — comment il est identifié

`ExecuteHit` ne pose jamais `+0x20` (il reste à 0) et recopie `+0x21` / `+0x22` depuis le résultat
de la sous-opération `0x42`. `+0x22` est **`didBlock`**, établi deux fois : c'est l'argument que
`ExecuteHit` passe au paramètre nommé `didBlock` d'`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
et `IdunBattle.Operations.ADamageOperation$$RegisterBlocks` teste ce même octet avant de poser
`hitGroup[+0x3e]`.

Reste `+0x21`, que le décompilé ne nomme pas. Il est identifié **par la mesure**, et de façon
univoque : entre les régimes `cc = 0 / 5 / 35 / 50 / 100` **rien ne change** au montage que la stat
`CritChance` — même board, même seed, mêmes positions, aucun block (`--block-target 0,0`), aucune
esquive. Or le nombre de crit-rolls **suit exactement le nombre de crits**. Un `didBlock` ou un
`didEvade` (nuls partout ici) rendraient les cinq régimes identiques ; ils ne le sont pas.

## 3. Le port

| natif | port |
|---|---|
| `OngoingAttack+0x40` / `hitGroup+0x3c` | `_run_hits(crit_allowed0=…)` → `_crit_allowed`, rendu en `crit_allowed` |
| `options[+0x29] |= …` + gate d'`ExecuteHit` | `damage_hits.crit_gate_open(crit_allowed, is_attack_damage_op)` |
| le recalcul `Any(null) → false` | `if not crit: _crit_allowed[0] = False` |
| `attack[+0x40] &= hitGroup[+0x3c]` | threading `crit_allowed0` → `additional_hits` → `damage_ops/{normal,ability}.py` |

`crit_gate_open` est une fonction de **module** et non une expression inline : c'est le point de
MUTATION du probe et du cliquet (la rendre toujours vraie restaure exactement le port d'avant).
Même pattern qu'`apply_all_modifiers` pour #131.

**Un coup DISCARD éteint aussi le canal** : le natif sort d'`ExecuteHit` sur un `OperationResult`
**memset à 0**, donc `+0x21 = 0` et le recalcul a lieu. Porté (`_discarded` → `_crit_allowed = False`).

## 4. Mesure — l'outil, et pourquoi il tranche

`dumpRng` (RPC existant, aucun hook neuf) rend `mt[624]` + `mti` + `callCount`. Deux modèles qui
consomment le même nombre de `genrand_int32` finissent au **même `mti`** : c'est un oracle EXACT de
l'étage (a), pas une reconstitution. L'étage (b) se lit en régénérant la suite des `genrand>>1`
depuis le `mt` dumpé et en cherchant, pour chaque valeur live, l'index du tirage qui l'explique.

Carte native du reproducteur (`necroDestroyer`, MC1_67/777, `--crit 50,700`) :

```
coup 0 = 928 <- tirage #1 (CRIT)     coup 3 = 600 <- #6
coup 1 = 874 <- tirage #3 (CRIT)     coup 4 = 585 <- #7
coup 2 = 603 <- tirage #5            coup 5 = 544 <- #8
pas entre tirages consommes = [2, 2, 1, 1, 1]
```

## 5. Validation — 11 cellules live, 3 mutations

`probe_366r1_crit_multihit.py` (montage réutilisable) + cliquet
`tests/engine/runner/test_crit_multihit_gate_live.py` — **11 passed**.

| couple | porteur | `--crit` | tirages natif | crits | port |
|---|---|---|---|---|---|
| MC1_67/777 | `necroDestroyer` (6, mêlée) | `0,700` | 6 | 0 | **bit-exact** |
| MC1_67/777 | `necroDestroyer` | `5,700` | 7 | 0 | **bit-exact** |
| MC1_67/777 | `necroDestroyer` | `50,700` | **9** | 2 puis stop | **bit-exact** |
| MC1_67/777 | `necroDestroyer` | `100,700` | 12 | 6 | **bit-exact** |
| MC1_67/777 | `eldarMauganRa` (5, mêlée) | `50,700` | **8** | 2 puis stop | **bit-exact** |
| C1_25/31337 | `necroDestroyer` | `30,700` | 7 | 0 | **bit-exact** |
| C1_25/31337 | `necroDestroyer` | `35,700` | **9** | 2 puis stop | **bit-exact** |
| C1_25/31337 | `necroDestroyer` | `40,700` | 12 | 5 puis stop | **bit-exact** |
| C1_25/31337 | `necroDestroyer` | `50` / `100,700` | 12 | 6 | **bit-exact** |

Avant le fix, les régimes à extinction interne divergeaient : MC1_67/777 `--crit 50,700` rendait
`[928, 874, 603, 917, 1115, 511]` contre un live `[928, 874, 603, 600, 585, 544]` (12 tirages au
lieu de 9). Les trois contre-épreuves `--mutate nogate` (deux couples + 2ᵉ porteur) le
**reproduisent**, donc la garde sait échouer.

Le cliquet contient son propre garde-fou de discrimination (`test_regime_is_discriminant`) : il
exige un CRIT **suivi** d'un non-crit dans la même salve. C'est exactement ce qu'un montage
`--crit 100,x` — le seul régime crit testé jusqu'ici — ne peut pas produire, et c'est par là que le
résidu a survécu.

Tests CIBLÉS rejoués, **83 verts, 0 rouge** : `test_crit_multihit_gate_live` (11),
`test_damage_crit_live` + `test_damage_roll_live` + `test_runner_attack_live` +
`test_case231_charge_forcecrit_live` (12), les trois `test_inescapable_accuracy_*` (31),
`test_getstuckin_{combat,bonus_deferred}_live` + `test_damage_block_live` +
`test_normal_attack_bounds_rounding_live` + `test_additional_hits_scalar_bounds_live` (14),
`test_act_of_faith_*` + `test_ischarging_saga_crit_live` + `test_path_of_command_crit_aura_live` (15).

## 5.1 Le CÂBLAGE — ce que « tests ciblés » ne voit pas

Ce port ajoute un paramètre à **`_run_hits`** et à **`execute_additional_hits`**, et une clé
(`crit_allowed`) à la valeur de retour de `_run_hits`. Une première passe verte sur les tests du
SUJET (crit, dégât, hits) a quand même laissé **16 rouges** dans la famille `additional-hits` : deux
substitutions de harnais (`probe_r6_round_materialize.py::_exec`,
`probe_r6b_additional_hits_order.py::_exec`) étaient restées en arrière, et la `TypeError` remontait
sur trois fichiers live.

**La question à poser n'est pas « quels tests portent sur mon sujet » mais « QUI APPELLE cette
fonction »** — y compris les probes et les stubs de harnais, qui ne ressemblent à aucun test du
domaine. `tests/test_additional_hits_variant_signatures_offline.py` automatise exactement ce
balayage (scan AST : toute fonction dont les six premiers paramètres sont ceux du canal est enrôlée
d'office, et un `**kwargs` fourre-tout est refusé — il rendrait la garde verte en cessant d'exercer
l'étage). **Il est à faire tourner à chaque changement de signature du canal**, et il ne fait partie
d'aucune des deux listes de cliquets habituelles (les six sont des *probes*, celui-ci est un test
pytest).

Balayage symétrique fait ici pour la clé de retour : **sept** harnais substituent `_run_hits` —
`probe_159_ah_bounds`, `probe_277_flail_damage_stages`, `probe_67b_shield_ability_limits`,
`probe_dpw_weapon_cell`, `probe_r6bp2_after_hit_maybe_ability`, `test_shield_ability_limits_live` et
le stub du cliquet ci-dessus. Les six premiers sont des **wrappers** qui délèguent à l'original (le
dict rendu porte donc `crit_allowed`) ; le septième fabrique son dict, mais aucune substitution ne
CHAÎNE le retour — d'où le choix, dans les deux `_exec`, de repasser `crit_allowed0` **verbatim**
plutôt que de chaîner `r["crit_allowed"]` comme le fait le port livré. Ces deux contrefactuels
passent `crit_enabled=False`, donc le canal crit y est structurellement fermé et les deux formes
sont indiscernables ; la limite est **nommée** dans leur commentaire.

## 6. Ce qui n'est PAS couvert

* **`options[+0x40]` (la collection de `hitIndex` autorisés à criter) n'est pas portée.** Elle est
  NULLE pour l'attaque normale et pour tout ce que le port câble — vérifié au décompilé
  (`AttackDamageOptions$$.ctor` zéroïse, seul `AttackDamageBehaviour+0xa0` peut la remplir). Une
  ability qui la poserait **rallumerait** le canal sur des coups précis, ce que le port ne lira pas.
  Résidu NOMMÉ, sans porteur identifié à ce jour.
* **La face PRÉDICTION** : `services/damage_prediction.py` ne modélise aucun crit multi-coups
  (`could_crit` seul) — gap préexistant du canal, pas de ce port.
* **Le vecteur OVERWATCH** et la famille ABILITY à crit ouvert ne sont pas exercés live (la famille
  ABILITY n'a de toute façon pas ce mécanisme, cf. §2).
* **Le cas DISCARD** (Harlequins) est porté par lecture du décompilé (`OperationResult` memset 0),
  **non confronté live** : aucun montage ne combine un discard et un crit ouvert.
* **`hitGroup[+0x4c]`** (incrémenté à chaque coup critique, propagé en `attack[+0x28]`) et
  `options[+0x3c]` (= `hitGroup[+0x4c] > 0`, relu par `ExecuteHit`) ne sont pas portés : aucun
  consommateur identifié côté port. `case-125` §2.1 les lisait comme un compteur de DISCARDS —
  lecture à corriger, l'octet testé y est le crit.
