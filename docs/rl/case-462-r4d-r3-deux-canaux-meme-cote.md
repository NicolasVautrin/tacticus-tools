# #462-r4d-r3 — deux canaux du MEME cote (`EffectBonus %` + stat-mod DEFENSE), en COMBAT

> ETAT DE TRAVAIL EN COURS — sera reecrit a l'etat FINAL avant la PR.

## 1. RE relue sur le build courant (`rnca9r7q6c`)

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, decompile relu
verbatim. Offsets confirmes sur la copie locale du `Nullable<DamageModifiers>` :

| champ lu | offset | usage |
|---|---|---|
| `Piercing` | `@0x20` | passe SEPAREMENT pour chaque face a `GetBaseDamageWithFixedPiercedArmor` |
| `ArmorPenetration` | `@0x28` | **SOMME** des deux faces (`Fix64.op_Addition`) avant l'appel |
| liste `@0x18` | (struct) | slot `0x11` = `ApplyCappedModifiers`, etapes 1 (att) puis 2 (def) |
| `Multiplier` | `@0x30` | slot `0x10` = `CalculateBaseDamageWithModifiers`, etapes 3 (att) puis 4 (def) |
| `Override` | `@0x00` | `Nullable<Fix64>` du DEFENSEUR seul, court-circuite le retour |

Les quatre etapes sont gatees UNIQUEMENT par le `HasValue` de leur `Nullable` — jamais par la
neutralite du multiplicateur. C'est inchange depuis #462-r4a ; relu ici parce que le regime vise
met les etapes **2 et 4 sur la MEME face**.

## 2. Le regime vise, et ce qu'il separe

Face DEFENSEUR portant SIMULTANEMENT :

* un `EffectBonus %` (effet -> liste `@0x18`, etape 2) ;
* une modification de stat DEFENSE (-> `Multiplier@0x30`, etape 4).

Modeles concurrents :

```
(A) port actuel  : Round( Round(P x pct_def) x mult_def )     # deux canaux, deux etages
(B) canaux fusionnes : Round( P x pct_def x mult_def )        # regression #462-r4a a l'envers
(C) ordre inverse    : Round( Round(P x mult_def) x pct_def )
```

⚠ Ce regime NE discrimine PAS « `attackModifiers` NULL en combat » (residu `#462-r4d-r1`) : apres
l'etape 2 la valeur est deja ENTIERE (`ApplyCappedModifiers` arrondit en fin d'appel quand la liste
est non vide), donc l'etape 3 est un no-op qu'elle existe ou non. A dire comme BORNE, jamais comme
confirmation.

## 3. Blocage herite

`probe_462d_nightshroud_stage_diff.py --thorns` est ECRIT mais ne s'installe pas sur `MC1_67`.
