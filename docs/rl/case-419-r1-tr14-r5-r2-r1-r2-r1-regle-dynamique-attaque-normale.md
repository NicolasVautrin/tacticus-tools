# `#419-r1-tr14-r5-r2-r1-r2-r1` — la regle dynamique de l'attaque normale

**Critere binaire** : le port offre-t-il, sur le chemin de l'attaque normale, des cibles que le
natif REFUSE ?

**Etat** : RE en cours (notes de travail, a reecrire a l'etat final).

---

## 1. La chaine, LUE — et la surcharge n'est PAS celle annoncee

`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
(5 params : `this, caster, casterTile, target, targetTiles`) :

```
w = <IBattleQuery slot 0xb0>(caster, casterTile, targetTiles)
return (w != null) ? 0 : 2   /* TargetMatchesDynamicRule */
```

`IBattleQuery` porte **TROIS** surcharges de `GetAttackWeaponForDefaultNormalAttack`, et elles ne
font PAS la meme chose. Le slot les separe :

| slot | signature (noms de params, metadata IL2CPP) | corps |
|---|---|---|
| `0xae` | `(attacker, attackerTiles)` | appel d'interface -> chaine de repli melee/ranged |
| `0xaf` | `(attacker, attackerTiles, **target**)` | `GetNormalAttackType` -> `GetAbilityAttackRangeType` -> `HasFlag(0x15)` / `AreEntitiesAdjacent` |
| `0xb0` | `(attacker, attackerTiles, **targetTiles**)` | `AreTilesAdjacent(attackerTiles[0], targetTiles[0])` |

**C'est le slot `0xb0` que la regle dynamique appelle** — donc la surcharge SIMPLE, pas celle a
`GetAbilityAttackRangeType`. Preuves croisees :

1. `ALoki_NormalAttackAbility$$FindAttackWeapon(caster, casterTiles, **targetTiles**)` -> slot `0xb0` ;
   `ALoki_NormalAttackAbility$$FindAttackWeapon(caster, casterTiles, **target**)` -> slot `0xaf`.
   Deux surcharges distinctes de `FindAttackWeapon`, deux slots distincts : la regle dynamique
   n'appelle donc PAS le meme slot que « FindAttackWeapon » au singulier.
2. `IdunBattle.View.FSM.VisualBattleQuery$$GetAttackWeaponForDefaultNormalAttack(unit, unitTile)`
   delegue explicitement au slot **`0xae`** -> le slot `0xae` est la surcharge a 2 arguments.
   Restent `0xaf`/`0xb0` pour les deux surcharges a 3 arguments, que le NOM du 3e parametre
   (`target` vs `targetTiles`) apparie une a une.
3. Les TYPES concordent : la surcharge `targetTiles` deref `targetTiles[0]`
   (`GetNodeByRef(x, 0)`), la surcharge `target` passe `target` tel quel a
   `AreEntitiesAdjacent` / `FindMeleeWeapon`.

## 2. `BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, targetTiles)`

```
t1 = attackerTiles[0]; t2 = targetTiles[0]
if (MovementUtil.AreTilesAdjacent(t1, t2))  return FindMeleeWeapon(attacker, null, null)
else                                        return FindRangedWeapon(attacker)
```

* `IdunBattle.Core.Services.BattleQuery$$FindMeleeWeapon(unit, unitPosition, target)` :
  `EntityExtensions.IsUnit(unit)` faux -> `null` ; sinon collecte les `WeaponProfile` de l'unite
  dont `get_IsMelee` est VRAI dans un `OrderedSet`, puis
  `target != null ? SelectBestDamageWeapon(...) : SelectMaxRangeWeapon(weapons)`.
  Ici `target == null` (le call-site passe `(void*)0x0, (void*)0x0`) -> `SelectMaxRangeWeapon`.
* `IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon(unit)` : symetrique, `get_IsMelee` FAUX.
* `IdunBattle.Core.Services.BattleQuery$$SelectMaxRangeWeapon(weapons)` :
  `Count == 0 -> null` ; `Count == 1 -> weapons[0]` ; sinon max par `Range.GetValueOrDefault()`.

**Ce qui rend `null`, et c'est TOUT ce dont la regle a besoin** : l'ensemble filtre est VIDE
(ou l'entite n'est pas une unite).

* `IdunShared.Battle.WeaponProfile$$get_IsMelee` (champ `this+0x24` = `Nullable<int> Range`) :

```
if (!Range.HasValue) return true;     /* pas de portee -> MELEE */
return Range.Value < 2;
```

## 3. Le discriminant qui en decoule

Cible ADJACENTE + caster sans AUCUNE arme melee -> `FindMeleeWeapon` rend `null` -> le natif REFUSE
(`TargetMatchesDynamicRule`), la ou le port ACCEPTE (distance 1 <= portee).

Cible NON adjacente + caster sans arme ranged -> refus aussi, mais le volet PORTEE le refusait deja
en amont dans la cascade : pas un discriminant.

## 4. Le rayon de souffle est borne par le BIT

La regle n'est consultee que sous `TargetMatchesDynamicRule` (bit 1). Depuis #419-r1-tr14-r5-r2-r1-r2
le port porte la table PAR TYPE : 13 types la posent, 5 ne la posent pas. Le refus ne doit s'armer
que sur les 13.
