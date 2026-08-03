# #462-r4b — un rouge qui n'accusait aucun gate : l'ÉVÉNEMENT d'un côté, l'ÉTAT FINAL de l'autre

`tests/engine/runner/test_chain_after_refused_addeffect_live.py::test_chain_survives_placed_addeffect`
rougissait sur `master`, sur le seul axe PORT :

```
[blackPossession] live={'pinned': True, ...}  port={'pinned': False, 'placed': True, ...}
```

Lecture spontanée : « le natif POSE `Pinned` sur une cible sans `TerminatorArmour`, le port le
REFUSE ». **Fausse.** Le port pose l'effet, et il le pose **ACTIF**.

## 1. Ce que la mesure établit (probe `probe_462r4b_pinned_active_after_chain.py`)

Décomposition par étage, un seul runner (MC1_67, seed du montage N5, caster `darkaAsmodai` au
contact), `ExemplarOfHate` (1140) :

| étage | ce qu'on exécute | `Pinned` sur `blackPossession` |
|---|---|---|
| A | `AddEffect(Pinned)` **seul** | `consumed=False active=True is_active=True` → **actif** |
| B | l'arbre COMPLET, `state.rng = None` (attaque libre no-op) | **actif** |
| C | l'arbre COMPLET, RNG du runner (attaque libre RÉSOLUE) | `consumed=True` → **absent d'`active_effects`** |

L'étage C isole la cause. `traceback` sur l'écriture de `consumed` (mode `--trace` du probe) :

```
AttackDamageOperation.execute -> _apply_damage_pipeline -> _fire_death_if_killed
  -> _verify_deaths -> _kill_unit_operation
  -> _kill_unit_remove_effects(state, target, KillUnitStep.PreUnitRemove)
  -> remove_effects_operation -> remove_effect_instance -> eff.consumed = True
```

**L'attaque libre de la chaîne TUE la cible.** Et elle la tue **des deux côtés** :

```
PORT  hp 8034 -> 0   alive=False
LIVE  hp 8034 -> 0   isDead=True      decisionView.effects POST-cast = []
```

Le natif fait exactement la même chose : `IdunBattle.Operations.KillUnitOperation$$RemoveEffects`
→ `IdunBattle.Operations.RemoveEffectsOperation$$Execute` (décompilé relu sur `rnca9r7q6c` : deux
boucles — collecte des `effectId` de l'`EffectsComponent` du porteur filtrés par `options`, puis
retrait par le slot 0x11) retire **tous** les effets du mort.

⇒ **Aucun gate fautif. Les deux moteurs sont d'accord.** Ce qui divergeait, c'était la LECTURE.

## 2. La faute de mesure, nommée

Le test lisait :

* côté LIVE : `applyAction.events[kind == "group"].source` contient `"Pinned"` — un **événement**,
  émis **pendant le cast**, au moment de la pose (un effet inerte n'applique rien, donc n'émet aucun
  groupe) ;
* côté PORT : `EffectsState.active_effects` sur l'**état final**, après toute la chaîne.

Les deux ne coïncident **que si la cible survit**. `blackPossession` (Uncommon, 8034 PV) ne survit
pas à une attaque sous override d'Attack ; `blackAbaddon` (le bras jumeau) survit, d'où un test 1
vert et un test 2 rouge pour la même raison structurelle. Le canal live le disait déjà : il publie
`Pinned` **deux fois** — la pose, puis le revert de la séquence de mort.

## 3. Le correctif, au foyer du canal

`engine/runner/abilities/behaviours/effects.py` — la feuille `AddEffect` émet désormais, à côté de
`placed`, un champ **`active`** (`_placed_effect_is_active`) : l'instance qui vient d'être posée
contribue-t-elle **à cet instant** ? Prédicat = celui d'`active_effects` (flag
`EffectComponent.IsActive @+0x5c` ET `<Effect>$$CreateActiveCondition` évaluée contre
`unit_state_for_effects`), c'est-à-dire les deux conjoints qu'évalue
`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` avant que `UpdateEffectTargets` →
`ApplyEffectsForTargets` ne joue le `<Effect>.ApplyInternal`.

C'est le pendant **exact** du groupe d'événement live. `placed` seul ne l'est pas : sur une cible
`TerminatorArmour` le natif POSE l'effet et le laisse inerte (#208), donc `placed=True` des deux
côtés alors que le natif n'émet rien.

`ExemplarOfHateAbility.execute_behaviour` remonte la liste sous `effects_active`.

Rayon de souffle : **additif**. 40 consommateurs de `ectx.emitted[n == "AddEffect"]` recensés, tous
lisent des clés nommées (`placed`, `target`, `effect_type`) ; aucune comparaison de payload complet
(`git grep "placed.: True"` sur `tests/` + `probe_*.py` : 0 hors la docstring du probe de ce case).

## 4. Le test, rendu HOMOLOGUE sur trois axes

| axe | LIVE | PORT |
|---|---|---|
| `pinned` | groupe émis par le cast | payload `active` de la feuille `AddEffect` |
| `final` | `decisionView.effects` POST-cast | `EffectsState.active_effects` |
| `dead` | `observeBattle.units[].isDead` | `UnitComponent.alive` |

Les deux axes neufs (`final`, `dead`) sont assertés **dans les deux tests** : c'est ce qui rendrait
visible une divergence de dégât assez grande pour tuer d'un seul côté — exactement le régime qui
avait rendu l'ancien axe non homologue. L'ancienne lecture n'est donc pas supprimée : elle est
**confrontée au bon canal**.

## 5. Contre-épreuves (elles MORDENT — vert aurait été le résultat suspect)

| mutation | attendu | mesuré |
|---|---|---|
| `_placed_effect_is_active` **inversé** | les deux bras rougissent | `test_chain_survives_inert_addeffect` **+** `test_chain_survives_placed_addeffect` rouges (2 failed, 2 passed) |
| gate d'immunité **fantôme** sur `TerminatorArmour` dans `PinnedEffect` (le fork de #224) | `placed=False` sur le bras immune | `test_chain_survives_inert_addeffect` rouge sur `port["placed"]` (1 failed, 3 passed) |

Arbre restauré bit-exact après chaque mutation (`git diff` ne mentionne plus `status.py`).

## 6. Non-régression rejouée

`test_chain_after_refused_addeffect_live.py` **4 passed** (contre 1 failed / 3 passed avant).

Modules qui consomment le même chemin `AddEffect`, joués 4 en parallèle puis 2 :

| module | verdict |
|---|---|
| `test_darkangels_lot1_live.py` | 8 passed |
| `test_effect_immunity_live.py` | 8 passed |
| `test_act_of_faith_second_stack_live.py` | 1 passed |
| `test_anvil_shield_stun_live.py` | 4 passed |
| `test_425_tile_effect_channel_live.py` | 4 passed (chemin **TUILE** — `_placed_effect_is_active` y reçoit un id de tuile) |
| `test_brazier_of_holy_fire_live.py` | 3 passed (chemin `source_from_target`) |

## 7. RÉSIDU NOMMÉ — écart de dégât sur le bras `TerminatorArmour` (item DISTINCT)

Le même probe le rend visible, et **aucun test ne l'assertionne** :

```
blackAbaddon (trait TerminatorArmour)   PORT 10038 -> 2308   (7730 infligés)
                                        LIVE 10038 -> 7442   (2596 infligés)   facteur 2,98
```

Le natif publie **deux** groupes `TerminatorArmour_ReduceDmg` sur ce cast ; le port n'a pas
d'équivalent observable. La réduction est portée
(`entities/effects/loki/damage_reduction.py::TerminatorArmourReduceDmgEffect`, `-75 %` =
`terminatorArmourDmgReduction`), mais elle n'apparaît pas sur l'attaque **commandée** par la feuille
`UseActiveAbility` de la chaîne. Cohérence croisée : sur `blackPossession` (SANS le trait) les deux
côtés infligent le même dégât (les deux amènent exactement à 0) — l'écart est donc bien porté par le
trait, pas par l'override d'Attack.

**Canal qui l'établirait** : décomposition par étage de l'attaque commandée
(`UseActiveAbility` → `AttackDamageOperation`) via le hook `scorerDamageTrace`, en comparant l'étage
« malus de défense » ; et qualification de `terminatorArmourExcludedDmgProfiles` contre le profil
d'arme d'Asmodai. Inscrit au backlog.
