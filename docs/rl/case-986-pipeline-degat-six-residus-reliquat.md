# #986 — le reliquat du pipeline de DÉGÂT : six résidus, une seule lecture

Build `rnca9r7q6c`. **Décompilé = vérité, live = confirmation.**

Une passe de RE sur `AttackDamageOperation$$ExecuteHit` → `DamagePrediction$$PredictAttackRaw`
→ `GetBaseDamageFix64` sert **trois** des six résidus. Les lectures sont verbatim.

## 1. L'étage qui les commande : `request+0x58`, le dégât COURANT

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, dans l'ordre du décompilé :

```
D0      = IdunBattle.Core.HitDamage$$GetDamage(options.damage, rng, ignoreSpread)
profil  = BattleQuery.slot 0xad (damageProfileType)
AttackHit..ctor(D0, abilityOrEffect)                     -> Nullable<AttackHit> sur l'attaquant
isCrit  = slot 0xa  RollCritical(...)                    (gate: options[+0x2b] == 0)
AbilityEntities..ctor(...) ; EnqueueOperation(6) ; EnqueueOperation(7)
relecture de l'AttackHit -> `discard` ? -> retour ; isCrit ?
   NON  : D = D0
   OUI  : D = slot 0xb CalculateCriticalDamage(attaquant, defenseur, D0, options)
                        = ApplyCritDamage(critDamage, D0)  =  critDamage + D0   (#954-r2)
request+0x58 = Nullable<int>(D)          <- LE point de composition
request+0x6a = options[+0x2f]            <- le drapeau « appliquer le SPREAD »
slot 4  PredictAttack -> PredictAttackRaw(request)
slot 8  RandomlyResolveMinMaxDamage
sub-op 0x42 ; EvaluateAfterHitTriggers
```

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` lit ce champ, **puis** branche :

```
D = Math.Max(0, Nullable.GetValueOrDefault(request+0x58))
(si le Nullable<Fix64> du slot 0xd de l'interface a une valeur -> D = (int)Fix64(cette valeur))

if (request+0x6a == 0 || request+0x10 -> [+0x31] != 0)
        bornes = MinMaxDamageFix64(D, D)                       # AUCUN spread, bornes dégénérées
else    bornes = GetBaseDamageFix64(D, IsAttackMaxOutDamage(...), GetStat(0x19))
```

et `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`, corps relu **verbatim** :

```
if (!isMaxOut) { min = calc.slot8(D) ;            max = calc.slot9(D) }
else           { min = calc.slot9(D) + Fix64(extraMax) ; max = calc.slot9(D) }
max = max + Fix64(extraMax)
return MinMaxDamageFix64(min, max)
```

**Le spread est appliqué à `D`, un scalaire UNIQUE, et `D` contient DÉJÀ le crit.**

## 2. #954-r3 — NON-BUG : les deux vecteurs sont FIDÈLES, et la divergence est native

Le résidu demandait : « relire où `AttackData` compose `attack + critDamage` pour une attaque
NORMALE — **avant ou après** `GetBaseDamageFix64` ». Réponse LUE : **AVANT**, à `request+0x58`,
et c'est le **même** point de composition pour les deux familles. Ce qui les sépare n'est pas la
place du crit, c'est le **drapeau `options[+0x2f]`** :

| vecteur | `options.damage` (HitDamage) | `D0` | `options[+0x2f]` | bornes |
|---|---|---|---|---|
| NORMALE | dégénérée (`min == max`) | la stat d'attaque, **sans tirage** | ≠ 0 | `GetBaseDamageFix64(attack + cd)` — **spread** |
| ABILITY | plage de config (`min != max`) | **tirée** dans la plage | 0 | `(roll + cd, roll + cd)` — **pas de spread** |

`IdunBattle.Core.HitDamage$$GetDamage`, corps relu verbatim :

```
if (min == max)     return min ;                  # dégénéré -> AUCUN tirage
if (ignoreSpread)   return (max + min) / 2 ;      # division ENTIÈRE C#
return random.Next(min, max + 1) ;
```

Le `min == max -> return min` est ce qui rend l'attaque normale « struct dégénéré, 1 tirage/coup »
et l'ability « struct non dégénéré, 2 tirages/coup » — les deux régimes déjà validés bit-exact.

**Conséquence** : le « shift 974 contre 779 » n'est pas une divergence de fidélité, c'est
l'ombre du spread. Sur le vecteur NORMALE le crit est **dans** la multiplication du spread
(`(3000+974) × 0,80 − 3000 × 0,80 = 779,2`) ; sur le vecteur ABILITY **il n'y a pas de spread du
tout**, donc le shift est plein (`974`). Les deux mirrors du port sont conformes :

* `damage_ops/normal.py` : `eff_attack = stat(ATTACK) + crit_damage` puis `get_base_damage_fix64` ;
* `damage_ops/ability.py` : `hit_cr = bornes brutes + crit_damage` puis `_reduce` (post-roll).

Corroboré, sans être déduit de lui, par le témoin live déjà au dépôt (`necroDestroyer`,
`attack = 906`, `cd = 500`, 6 coups) : les coups critiques mesurés `[932, 882, 967, 867, 961, 955]`
tombent dans `[675, 1012]` = spread sur `906 + 500`. Le modèle « crit ajouté APRÈS le spread »
prédirait `[935, 1152]` — **réfuté par 867** ; le modèle « crit hors spread » prédirait
`[735, 952]` — **réfuté par 967**.

**Verdict : NON-BUG, fermé par la LECTURE.** Aucune correction de code.

### Ce qui reste NON LU, et qui ne change pas le verdict

Le `slot 0xd` de l'interface `DAT_18334a0c8` (celle qui porte aussi `slot 8`/`slot 9` =
min/max du spread, et `slot 0x12` = type de profil) rend un `Nullable<Fix64>` qui **écrase `D`**
quand il a une valeur. Il est **null dans les deux régimes mesurés** (sans quoi le crit
disparaîtrait de l'attaque normale, ce que le live réfute, et les bornes d'ability seraient
fausses, ce que `ThunderousAssault`/`VigilanceEternal` réfutent bit-exact). Il est en amont du
branchement, donc il ne déplace le crit sur aucun des deux vecteurs. Nommé ici plutôt que
supposé nul.
