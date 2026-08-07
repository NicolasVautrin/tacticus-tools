# #287-r11-r2-r1-r2 — le troisième gate de `ShouldApplyRangedInMelee`, et le canal des traits

Deux volets, deux écarts de nature différente. Le second a fait tomber un fork entre les faces ;
le premier a fait remonter un **troisième** écart, dans le behaviour lui-même.

## 1. Le corps natif a TROIS gardes avant sa boucle, pas deux

`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee(attacker, attackerTiles,
state, ignoreTrait)`, relu VERBATIM sur `rnca9r7q6c` :

    if (attackerTiles == null || attackerTiles.Count == 0)          return false;
    if (!UnitExtensions.HasTrait(attacker, 0xb) && !ignoreTrait)    return false;
    if (UnitExtensions.HasFlag(attacker, 0x1c))                     return false;   // <-- CELUI-CI
    foreach (attackerTile in attackerTiles)
      foreach (adj in TileComponent(attackerTile).Neighbours)
        u = UnitExtensions.GetUnit(adj, state);
        if (u != null && IsUnit(u) && !IsFriend(attacker, u, state)
            && !TileExtensions.HasSteppableUnit(adj, state)
            && DamageCalculations.CanMeleeAttackOverElevationDifference(attackerTile, adj)
            && IsTargetable(u) && IsAlive(u, state))                return true;
    return false;

⚠ **`0x1c` se lit dans SON espace de nommage, et l'ordinal ne discrimine PAS** :
`UnitFlag.IngoreRangedInMelee` (**typo native**, `enums.tsv` : `28=IngoreRangedInMelee`), mais
l'ordinal 28 nomme aussi `UnitTrait.Impervious`, et le **bit** 28 de `TargetingRule` est
`CasterCanMove`. Trois noms pour le même nombre — confondre n'aurait levé aucune erreur.

## 2. Le port avait TROIS mirrors, pas deux

| mirror | `attacker` reçu | gate 3 avant | gate 3 après |
|---|---|---|---|
| `runner/abilities/targeting.py::should_apply_ranged_in_melee` | le **caster** | absent | **PORTÉ** |
| `runner/abilities/loki/mv71.py::_should_apply_ranged_in_melee_from_tile` | le **`parent`** | absent | **PORTÉ** (tri-état) |
| `playbook/prediction/_shared.py::_should_apply_ranged_in_melee` | le caster | absent | **NOMMÉ**, non porté |

Le troisième n'était pas recensé par le résidu. Il omet en outre `!HasSteppableUnit(adj)` et
`IsTargetable(u)` ; ces écarts sont nommés dans sa docstring et restent inertes tant que son gate
`HasTrait(0xb Ranged)` l'est.

## 3. Ce qui a rendu le gate exerçable — son POSEUR UNIQUE

Balayage **exhaustif** des deux seules voies d'écriture d'un flag (`UnitFlagsComponent` n'expose ni
`AddRange` ni setter de masque) : **25** appelants de `IdunBattle.Entities.Components.UnitFlagsComponent$$Add`,
**10** appelants de `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag`, plus les xrefs entrantes de
`UnitFlagsComponent$$Remove`. Un seul site pose `0x1c` :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour

par la chaîne DSL, composée par `AbilityBehaviour$$op_BitwiseAnd` :

    AddEffect(0x46c) & AddEffect(0x46d) & AddFlag(sel@0x68, 0x1c)
                     & UseActiveAbility(caster = Alive(sel@0x68), …) & RemoveFlag(sel@0x68, 0x1c)

Trois lectures qui ne se devinent pas :

* **le porteur est le DRONE**, pas le héros — le sélecteur `+0x68` est celui-là même qui reçoit les
  deux `AddEffect` de stats initiales et le `Alive()` ;
* **le flag est TRANSITOIRE** : posé puis retiré autour d'un seul `UseActiveAbility`. Il n'existe
  jamais entre deux actions, donc aucun état capturé hors du behaviour ne le porte ;
* **sémantique** : l'attaque d'OUVERTURE du drone fraîchement invoqué est dispensée de la pénalité
  ranged-in-melee.

⇒ **Sur `BattleQuery$$IsTargetInAttackRangeForSummon`, le gate reçoit le `parent` : il y est
INERTE PAR CONSTRUCTION.** Ce n'est pas un manque de canal, c'est une mesure — et c'est aussi ce qui
rend sans conséquence le `None` de la face prédiction (la valeur mesurée serait `False` de toute
façon). Il MORD sur l'autre chemin, `AttackQuery$$ShouldApplyRangedInMelee(caster = LE DRONE)`.

⚠ **La citation du décompilé en tête de `mv71.py` OMETTAIT le couple `AddFlag`/`RemoveFlag`**, et
le port l'omettait donc aussi. Les deux sont réparés : le behaviour pose le flag sur le drone avant
`AttackDamageOperation` et le retire après, exactement comme la chaîne DSL — l'état final est
inchangé. **Inerte par ce chemin**, et la cause est nommée : le seul consommateur porté du gate est
`targeting.get_range` (sous `options.force_melee_target`), que le raccourci `AttackDamageOperation`
ne traverse pas — le port appelle l'opération de dégât DIRECTEMENT là où le natif passe par la
cascade `ActiveAbilityOperation`.

## 4. Second volet — la face PRÉDICTION lisait le mauvais canal, et c'était un FORK

`mv71.pick_tile_scene` hydratait son `occupant_by_tile` par
`entity_trait_names(None, visualId)` — la **borne STATIQUE** (kit gameconfig + alliance). Or
`entity_trait_names` documente lui-même que `Scene.ctx(uid)` **est le même objet** que le
`StatsComponent.ctx` que lit la face RUNNER (`targeting._unit_traits`). Passer `None` réduisait donc
volontairement le substrat : aveugle à tout trait **accordé en bataille** (`AddTraitOperation`) ET à
la mesure live `combatSnapshot.units[].traits`, qui diffère du kit **dans les deux sens** (#264 :
5 unités du seed ont MOINS de traits que leur kit, 48 en ont PLUS).

Ce n'était pas une borne assumée mais un **fork entre les deux faces**, et il est OBSERVABLE : avec
un `Steppable` accordé en bataille sur l'ennemi adjacent à la candidate, la face runner rend la
tuile `(3,0)` et la face prédiction rendait `None`. Après : les deux rendent `(3,0)`.

`ctx` absent ⇒ `entity_trait_names` retombe de lui-même sur la borne statique, donc la dégradation
d'une unité hors tables est celle d'avant.

## 5. La garde

`tests/engine/test_287r11r2r1_los_summon_offline.py`, **étage 9** (7 tests neufs, fichier à 25) :

1. l'ordinal 28 nomme TROIS choses différentes — le piège, gravé ;
2. l'ordinal confronté à `data/symbols/<build>/frida/enums.tsv` (le mirror ne dérive pas) ;
3. le gate de `targeting.should_apply_ranged_in_melee` : MÊME substrat, le flag SEUL bascule le
   verdict (avec l'assertion que le montage arme VRAIMENT le clamp, sinon le bras serait vrai par
   vacuité) ;
4. le tri-état du gate de `mv71` (`True` court-circuite, `False` et `None` laissent la boucle) ;
5. le couple `AddFlag`/`RemoveFlag` du behaviour — l'état PENDANT l'attaque (témoin substitué à
   `AttackDamageOperation.execute`) et l'état FINAL, qui doit être inchangé ;
6. le câblage runner qui lit le flag du **PARENT**, avec compteur d'appels (sans lui le test
   passerait par coïncidence, les deux verdicts valant 0) ;
7. le fork de canal, confronté **AU SITE** (`pick_tile_scene`), pas à la valeur d'un helper.

Vue rouge sur l'arbre témoin : **5 failed / 20 passed** ; **25 passed** après. Les 2 tests d'ordinal
sont verts des deux côtés — ce sont des crans de CITATION, pas de port.

## 6. Régression trouvée par la passe de non-régression

`test_433_r4_r1_filter_tiles_can_attack_offline.py::_StubScene` n'expose pas `ctx` — le changement
de canal le faisait lever `AttributeError`. Le stub est complété (`ctx -> None`, donc repli sur la
borne statique : son montage est inchangé) plutôt que le site rendu défensif : le contrat de
`pick_tile_scene` est une `Scene`, et un `getattr` défensif y masquerait le prochain appelant
incomplet. Recensement : `pick_tile_scene` a **un** appelant moteur
(`playbook/prediction/normal_attack.py`, vraie `Scene`) et **deux** en test.

## 7. Ce qui n'est PAS couvert

* **Aucune confrontation LIVE de ce volet.** Le seul régime où le flag existe est *à l'intérieur*
  du behaviour natif, entre `AddFlag` et `RemoveFlag` : aucun état capturable par
  `combatSnapshot` ne le porte, et aucun RPC n'observe un instant intra-behaviour. La garde est
  donc OFFLINE, et le port du couple `AddFlag`/`RemoveFlag` est ce qui rend le régime reproductible
  côté port. Le canal, lui, est vérifié : `unitFlags` publie **toutes** les valeurs de l'enum.
* **Le gate 3 du troisième mirror** (`playbook/prediction/_shared.py`) reste non porté — raison
  mesurée en §2 et nommée dans sa docstring, avec ses deux conjonctions manquantes.
* **Le consommateur du gate n'est pas traversé** par le raccourci `AttackDamageOperation` du port
  (§3). Rendre l'exécution du drone passante par la cascade `ActiveAbilityOperation` est une
  tranche à part.
* **La `Scene` n'a pas de table pour ce flag** — sans conséquence tant que le poseur est unique et
  vise le drone (§3). Point d'ancrage nommé si un second poseur apparaît.

## 8. Résidus

Aucun ouvert par cette tranche.
