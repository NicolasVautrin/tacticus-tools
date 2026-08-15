# #425-r1 — le témoin cherché n'était pas sur la feuille qu'on regardait

**Mesuré le 2026-08-15, build `t6dpr4k06g`.** Le port est LIVRÉ depuis le 2026-08-14/15 ; ce qui
restait ouvert était le **témoin non dégénéré** — un effet de tuile POSÉ mais INACTIF. Deux
montages l'avaient cherché en vain. Ils cherchaient sur la mauvaise feuille.

## 1. La prémisse est CONFIRMÉE, re-lue sur le build courant

`IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`,
Loop 1 : `get_MainTile` → `GetComponent<EffectsOwnedComponent>` → liste `@+0x10` →
`<IMatchState slot 0x29 GetEntity>(id)` → `GetComponent<EffectComponent>` → `Enum.ToString(+0x58)`
→ `HasUtilityValue` → `GetUtilityValue`. **Aucun test de `IsActive` (`+0x5c`) ni de `Removed`
(`+0x5f`)** entre le `GetEntity` et la lecture du type. Idem pour
`ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext`, relue ici même.

⚠ Étage vu au passage et **NON porté** : la Loop 1 multiplie le poids par
`TileEffectsUtility$$GetStatusEffectMultiplier` **si et seulement si**
`StaticBattleRules.Effect$$IsTileStatusEffect(type)`. Le port note « non porté → poids brut ».

## 2. Le mécanisme qui FABRIQUE un effet possédé-mais-inactif, LU

`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive(refreshTrigger, refreshType, …)` :

```c
case 1: return true;   case 2: return false;
case 0:
    if (effectComponent.BeingRemoved /* +0x5e */) return false;
    if (!effect.<vslot 0xc>(refreshTrigger)) return effectComponent.IsActive;  // inchangé
    return effect.<vslot 0xb>(<contexte 0x128 : owner, activePlayer, effectEntity>);
```

puis `$$DeactivateEffect` écrit `0` à `+0x5c`. **Il ne retire rien de `EffectsOwnedComponent`** —
seul `IdunBattle.Operations.RemoveEffectOperation$$Execute` le fait. L'état « possédé + inactif »
est donc **structurel**, pas hypothétique.

Balayage binaire exhaustif (`probe_425r3_removed_writers.py --offset 0x5c`, 44 605 916 o de code) :
**275 sites** d'écriture d'un octet à `+0x5c` dans **215 fonctions**, dont **4** portant `Effect` —
`RefreshEffectsOperation$${Activate,Deactivate,Refresh}Effect` et `RemoveEffectOperation$$Execute`.
Seuls les deux derniers écrivent `0`.

## 3. Pourquoi les deux montages précédents ont rendu un gisement VIDE

Un seul effet de tuile porte un `CreateActiveCondition` propre. Croisement des **15** noms de
`BC.Utilities.Default.TileEffects` contre `data/symbols/t6dpr4k06g/ghidra/functions.tsv` :

| effet | `CreateActiveCondition` | poids `Default.TileEffects` |
|---|---|---|
| `Contaminated` | **OUI** — `IsWalkable(tile) \|\| IsSpawnTile(tile)` | **0** |
| les 14 autres (`Fire`, `Ice`, `SpiderWeb`, `Thorns_…`, `FirstAidHeal`, les 9 marqueurs `…_Pending*`/`…Tile`) | aucun | −25 … −100 |

Le seul effet **désactivable** est aussi celui dont le poids est **nul**. Sur la feuille
`TileEffects(10)`, le témoin est donc **structurellement dégénéré** : même compté, il vaut 0.
C'est la cause exacte du « gisement nul » mesuré la veille sur `1148 DaemonicOrdnance`.

(Contrôle : `IsWalkable` n'est pas un test d'occupant —
`IdunBattleLogic.Entities.DSLTriggers$$IsWalkable` = `AmountIsGreaterAbilityTrigger(DSLSelectors.Walkable(sel), minAmount)`.)

## 4. Le témoin EXISTE — sur `Contaminated(26)`, pas sur `TileEffects(10)`

`Contaminated` a **sa propre feuille**, et son poids y est **non nul** :

```
BC.Utilities.Default.Contaminated = { "AffectedUnit": -25 }
```

`ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext` itère la **même** liste
possédée et compare `EffectComponent+0x58` à `0x4dc`, **sans gate d'activité**, puis ajoute
`GetUtilityValue("Contaminated.AffectedUnit")` et **sort** (pas d'accumulation). Côté port, ce
canal est `tile_effect_type_ids`, que `_tile_attribute_maps` (`engine/ai/context.py`) construit
**sans filtrer `active`** depuis le fix. Avant le fix, il était filtré ⇒ **−25 perdus**.

**Le témoin mordant est donc : `Contaminated` sur une tuile qui n'est ni marchable ni tuile de
spawn.** Poseurs (`AddEffect(0x4dc, …)`) :

- `CloudOfFlies_ContaminationAbility$$CreateBehaviour` → `DSLSelectors.Tiles(state, caster)` (la
  tuile du caster — marchable à la pose, donc il faut qu'elle **le devienne** non marchable) ;
- `Lakrimae_AddContamination_Ability$$CreateBehaviour` → cibles de l'ability (`ctx+0x78`) ;
- `ArchContaminatorAbility` → `AdjacentEnemies`, dégât : pas un effet de tuile.

**NON CONFRONTÉ** : le montage n'a pas été joué. Il demande de rendre non marchable une tuile
déjà contaminée (candidat conservé : la zone non marchable de `1148 DaemonicOrdnance`, #368).

## 5. Ce qui change pour la suite

Le résidu ne cherche plus « un effet de tuile inactif » en général : il cherche **`Contaminated`
sur une tuile devenue non marchable**, et l'observable est la feuille **26** (−25), pas la 10 (0).
Si `Default.TileEffects.Contaminated` cessait de valoir 0, la feuille 10 redeviendrait elle aussi
un témoin — c'est une valeur de gameconfig, à re-dériver, jamais à citer d'ici.
