# case-392 — `MartialApotheosis` est MONTÉE par le BC : #354 avait le mauvais référentiel

**Le tripwire d'inertie `test_ma_inertia_tripwire_no_carrier` rougissait sur `master`** en accusant
l'étage ATTRIBUTION du port. Verdict : **c'est le tripwire qui lisait une voie périmée** — et sa
prémisse, héritée de #354, est réfutée par la mesure.

Mesure : `scripts/python/probe_392_martial_apotheosis_bc_carrier.py` (5 étages, dont 3 LIVE).

## 1. Le natif ne monte PAS le kit gameconfig

`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` énumère
`UnitConfiguration.PassiveAbilities` (`config+0xa8`) et appelle
`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)`.
La source du montage est donc **`BattleConfiguration.Units[].PassiveAbilities`**. Le kit
gameconfig et `decisionView.units[].abilities` (qui n'expose pas les passifs) ne disent rien de ce
montage — or ce sont les deux seules choses que `probe_354` balayait.

| étage | mesure | résultat |
|---|---|---|
| seed BC | `data/seed-bc.json`, 175 unités | `necroOverlord.PassiveAbilities = [1045]` — **1 porteur** |
| kit gameconfig | 4 voies chez `necroOverlord` | **AUCUNE** (le kit dit `MyWillBeDoneOverlord`) |
| composant RÉEL | RPC `unitAbilityStates`, hiérarchie 2 du `TriggeredAbilityComponent` | **`['1045=MartialApotheosis']`** |
| LIVE, d=1 | ennemi drivé en anneau-1, `endturn` vers le turn-start | **3702** |
| LIVE, d=2 | même montage, ennemi à distance 2 | **0** |

Le couple d=1 / d=2 **attribue** le dégât à une source de portée anneau-1, et lève l'objection de
`case-354` §3 (« un `delta > 0` n'attribue rien »), qui était juste. Le replay-diff offline rend en
plus **3702** — le dégât est **bit-exact**, ce que #354 déclarait « plus confrontable ».

## 2. Le silence de #354 était un BUG DU PORT, pas un retrait du jeu

`collect_triggered_abilities` dérivait les passives du **gameconfig par `visualId`**. Le natif, lui,
monte le BC. Tant que les deux coïncident, la reconstruction passe inaperçue — mais elle rend
INERTE, sans erreur ni trace, tout passif que le BC porte et que le kit ignore. C'est exactement ce
qui s'est produit, et #354 a lu l'inertie du port comme un fait du jeu, puis **supprimé trois
vecteurs de test valides** (#354-r2).

Le bug a été fermé indépendamment par **#366-r1** (`21a38550`, 2026-08-01 00:25, canal MESURÉ
`UnitContext.passive_abilities`). Le tripwire, resté en place, s'est alors mis à accuser le
correctif.

## 3. Cause racine amont : le seed BC est périmé (#254-bc, déjà au backlog)

Le bloc `Units` de `data/seed-bc.json` est resté celui de `gqfc5mff6c`. `necroOverlord` y porte
encore `[1045]` là où le gameconfig vivant dit `MyWillBeDoneOverlord` (1556). **Ce n'est pas un
accord sur une entrée morte** : le natif monte réellement l'ability et la joue, le port fait de
même, et les deux sont confrontés bit-exact. Ce qui est validé est donc « le moteur reproduit le
natif **pour cette configuration** » — pas « c'est ce qui se passe en bataille in-game avec un BC
frais ». Le jour où #254-bc est arbitré et le seed re-dumpé, l'ability sortira du BC et la garde T0
rougira **sur le bon canal**, avec la marche à suivre dans son message.

Balayage (probe_392 étage 0) — les écarts kit/BC du seed sont au nombre de **trois**, et c'est tout :

| ability | sens de l'écart | portée au registre |
|---|---|---|
| `MartialApotheosis` | BC seul (montée, hors kit) — `necroOverlord` | oui |
| `MyWillBeDoneOverlord` | kit seul (**non montée**) — `necroOverlord` | oui → **résidu : inerte dans tout runner bâti sur ce seed** |
| `Bounce` | kit seul (non montée) — `orksNpc7Squig` | non |

## 4. Ce qui change dans le fichier de test

| | avant (#354-r2) | après (#392) |
|---|---|---|
| tests | 4 passed, **1 failed** | **7 passed** |
| garde d'inertie | kit gameconfig + `decisionView` | canal MESURÉ (tri-état du seed + hiérarchie 2) + écart kit/BC constaté |
| vecteur turn-start (A) | supprimé | restauré |
| ciblage anneau-1 (C) | construction directe | **via le dispatch** |
| replay-diff LIVE (E) | supprimé | restauré + **durci** : attribution géométrique *et* dégât bit-exact |

La leçon transférable est celle du couple : **un vecteur par le dispatch ET un vecteur par
construction directe**. C'est lui qui localise un décrochage à l'étage ATTRIBUTION sans avoir à
deviner ; son absence a coûté le faux verdict.

## 5. `IsEffectTarget` — la seconde primitive, apparue PENDANT le run

Le cliquet #337 a rougi une seconde fois, sur `IsEffectTarget`, pendant que cette tâche tournait :
la PR **#418** (`1014 CamoCloak_DmgReduction`), mergée entre-temps, installe
`engine/runner/components.py::is_target_of_adjacent_friend_aura`, dont la docstring cite la
primitive. Elle bascule donc de `NON_PORTE` à `CITE_A_QUALIFIER`. Chacune des deux PR est juste à
SA base — c'est la forme « état dérivé + deux PR parallèles » qui se referme après merge.

**Verdict : `PORTE_HORS_FACADE`, avec deux écarts nommés (résidu `#418-r1`, non corrigés — cette
tranche est une ATTESTATION).**

### L'aval nommé par #418 n'est pas celui qu'emprunte le trigger

`IsEffectTargetTrigger$$ShouldTrigger` résout le sélecteur `+0x10`, puis **invoque le slot
d'interface** de `+0x20` avec `(entity, effectType@+0x18, 0)`. Ce `+0x20` vient de
`<ctx DSLTriggers>+0x38` — exactement le champ que ghidra nomme `effectsQuery` dans
`IdunBattleLogic.Entities.DSLTriggers$$HasEffect`. La cible est donc
`IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget` (signature `(target, effectType,
onlyActive)`, aucune xref d'appel direct — uniquement DATA, comme toute méthode d'interface).

`IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType`, que la docstring de #418 nomme, a
au contraire **un appelant direct mesuré** : `IdunBattle.Entities.EntityExtensions$$HasEffectOfType`.
C'est l'aval d'un AUTRE prédicat. Erreur de citation, sans conséquence sur le comportement — les
deux finissent par lire `EffectComponent+0x48`.

### Ce que #418 fait JUSTE, et c'est vérifié

* la **géométrie** : `IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateTargetSelector`
  = `Friends(AdjacentUnits(Owner))`, et `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` =
  `AdjacentTiles(origin)` — **anneau‑1 FIXE, aucun paramètre de rayon** — puis
  `TargetsSelector$$op_Subtraction(origin)`, soit le **porteur EXCLU**. Le port dit exactement ça.
  (Les littéraux `1` et `3` de l'appel sont `unique` et `selectionType`, pas un rayon.)
* `onlyActive = 0` : le trigger passe `false`, et `EffectsState.has_effect` filtre `consumed`, pas
  `active`. Fidèle.

### Les deux écarts (`#418-r1`)

1. **Matérialisé vs re-dérivé.** `EffectsQuery$$GetEffectsWithTargets` **copie**
   `EffectComponent+0x48` — elle ne ré-évalue aucun sélecteur. La liste native est tenue à jour par
   `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` (calcul de `GetTargetsToRemove`
   / `GetTargetsToAdd` contre `desiredTargets`, appelée par `RefreshEffect` et `DeactivateEffect`).
   Le port, lui, re-dérive **à la lecture**. Régime discriminant : une lecture faite APRÈS un
   déplacement et AVANT le refresh qui le suit.
2. **Générique vs spécialisé.** La primitive ne connaît aucune géométrie ; le lecteur encode celle
   de l'effet `1026`. Sur les **6** fonctions natives qui construisent le nœud (10 call-sites),
   **5 restent découvertes** : `InstinctiveBehaviour_UpdateTargetAbility` (×3),
   `PsykerExtraAttackAbility` (×4), `GuardianOrganismAbility`,
   `WayOfTheShortBlade_AttackAbility` — chacune avec SON sélecteur.
