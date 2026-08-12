# case-961-r1 — l'écart de `LivingLightning` n'est ni dans le vecteur, ni un facteur

Le résidu `#961-r1` était énoncé ainsi : « à distance 1, le port SUR-ESTIME le natif d'un facteur
CONSTANT : le natif rend 87,27 % du port ; à distance 2 c'est bit-exact ; le ratio est identique à
5·10⁻⁵ près sur deux configurations d'élévation ».

**Les trois moitiés de cet énoncé sont fausses.** Ce n'est pas un facteur, ce n'est pas la distance
seule, et les « deux configurations » n'étaient pas deux mesures.

---

## 1. Le « facteur constant » était un artefact de la mesure

Les deux points qui l'établissaient — `3967/4546` et `5951/6819` — sont **la MÊME capture**. Le
second régime (`adjacent_low`) ne diffère du premier que par l'élévation de la cible, qui applique
un `×1.5` **des deux côtés** : `6819 = 4546 × 1.5` et `5951 = 3967 × 1.5` (à l'arrondi). Le ratio
ne pouvait donc pas bouger — il n'y avait **aucun témoin d'invariance**.

Re-mesuré sur des **tirages indépendants** (`probe_961r1_attribution.py --seeds 777,31337,4242`) :

| seed | port | natif | ratio | **delta** |
|---|---|---|---|---|
| 777 | 4546 | 3967 | 0,8726 | **579** |
| 31337 | 4861 | 4282 | 0,8809 | **579** |
| 4242 | 2017 | 1438 | 0,7129 | **579** |
| 12345 | 4645 | 4066 | 0,8753 | **579** |

Le **ratio varie de 0,713 à 0,881** ; le **delta est 579, quatre fois sur quatre**. L'écart est
**ADDITIF**, et chercher un multiplicateur ne pouvait aboutir.

## 2. Ce n'est pas la distance : c'est l'INTERSECTION crit × adjacence

Le montage d'origine confondait DEUX variables — la tuile `near` étant prise comme la première
libre à la distance voulue, `adjacent` tombait sur une élévation ÉGALE (aucun bonus) et `range2`
sur une tuile PLUS BASSE (bonus `×1.5`). Le régime `range2_flat` (distance 2, élévation ÉGALE) a été
ajouté à `probe_961_necron_passives.py::measure_ll` pour compléter le carré, et il rend
**exactement la valeur que le port rend à distance 1** (4546) — donc le port a raison, et c'est le
natif qui retranche.

Carré complet, même roll, même flux MT (`dumpRng` 6/6 partout) :

| distance | coup | delta port − natif |
|---|---|---|
| 2 (élévation égale) | CRIT | **0** |
| 2 (élévation basse) | CRIT | **0** |
| 2 | non-crit | **0** |
| 1 | non-crit (`critChance = 0`) | **0** |
| 1 | **CRIT** | **579** |

Le drapeau natif est lu directement — tag `Attack_DidCrit` de l'event `UnitDamaged` de
`applyAction` — pas déduit : les deux côtés crittent **au même moment**, `Attack_DidBlock = 0`,
`Attack_DidEvade = 0`, `Attack_WasOverkill = 0`, un seul coup.

Le bonus de crit NATIF vaut donc **1503 au contact** contre **2082 à distance**, pour la même stat
`GetStat(10) = 2082` et le même roll de base (2464 et 2779 sur deux seeds → **1503 les deux fois**).

## 3. La réduction est ADDITIVE, et elle appartient au DÉFENSEUR

Contrôles, une entrée d'état à la fois (mutation **vérifiée au `combatSnapshot`**) :

  * `critDamage = 1000` (au lieu de 2082) → delta **toujours 579** (crit effectif 421). La réduction
    n'est donc **pas proportionnelle** au bonus de crit : un facteur aurait donné 278.
  * `fixedArmor = 0` sur la cible (mutation mordue, `stats.fixedArmor: 0` au snapshot) → delta
    **toujours 579**. Rien à voir avec l'armure ni avec le perçage (profil `DirectDamage`,
    perçage 100 % → la branche plancher `d × pierce` gagne de toute façon).
  * **cible `orksWarboss`** → delta **0**. **cible `orksNob`** → delta **0**.

⚠ Deux contrôles ont été ÉCARTÉS parce que la mutation **n'a pas mordu** (`defense = 0` et
`attack = 1000` : le snapshot rend les valeurs d'origine). Ils ne concluent rien, et c'est dit —
un `--unit-stat` qui ne s'applique pas rend un résultat identique au témoin, donc rassurant à tort.

Le porteur se lit dans ce qui **distingue** les trois cibles, toutes trois `Hero` + `GetStuckIn` :

| cible | passif | autres traits | delta |
|---|---|---|---|
| `orksRuntherd` | **`SquigHound`** | `BeastSlayer` | **579** |
| `orksNob` | `SmashaEad` | `BeastSlayer`, `Unstoppable` | 0 |
| `orksWarboss` | `LightImUp` | `BigTarget`, `CrushingStrike`, `FinalJustice`, `Mechanical` | 0 |

`GetStuckIn` est porté par les **trois** ⇒ écarté. `BeastSlayer` est porté par `orksNob`, qui est
bit-exact ⇒ écarté. **Reste `SquigHound`**, le passif du seul porteur divergent.

## 4. ATTRIBUTION — pipeline partagé, PAS le vecteur

C'était la question à trancher, et elle est tranchée :

  * le **vecteur** `LivingLightning` passe au pipeline des bornes JUSTES (`HitDamage(2394, 2992)`,
    tracées) et le bon roll — il est bit-exact dans **quatre** des cinq cellules du carré, y compris
    sur un coup critique ;
  * l'écart vit dans le **canal CRIT du pipeline de dégât partagé** — `AttackDamageOperation
    $$ExecuteHit` → `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` =
    `Math.Max(0, GetStat(10) + GetCritDamageBonusFromEffects(...))` — dont le port rend un bonus
    d'effets de **0** (tracé) là où le natif applique **−579** ;
  * le porteur de ce bonus est un effet du **DÉFENSEUR** (`SquigHound`), gaté sur l'**adjacence**.

⇒ **Aucun correctif n'est livré ici** : le foyer (`engine/runner/operations/damage.py`,
`damage_ops/*`) est celui d'une autre tranche en vol, et le porteur d'effet reste à identifier au
décompilé. Le correctif est ouvert en **`#961-r3`**.

## 5. Outillage livré

  * `scripts/python/probe_961r1_attribution.py` — décompose le coup PAR ÉTAGE côté port (bornes
    `HitDamage`, sources de blocage, `_crit_params` + sa stat brute, `GetCritDamageBonusFromEffects`
    et ses porteurs, élévation, trench, perçage/armure, face défenseur) en substituant les foyers
    que `damage_ops/ability.py` résout dans SES globals — aucun fichier du pipeline n'est édité.
    Il lit AUSSI les tags natifs (`Attack_DidCrit`, `Attack_DidBlock`, `Amount`) des events de
    `applyAction`, et il expose `--unit-stat` / `--enemy-near` pour faire varier **une** entrée
    d'état à la fois.
  * `probe_961_necron_passives.py::measure_ll` — régime **`range2_flat`** (distance 2, élévation
    ÉGALE), qui rend les deux axes séparables. Sans lui, distance et élévation restaient confondues
    et l'écart paraissait multiplicatif.

## 6. Ce qui n'est PAS couvert

  * **`#961-r3`** — le correctif lui-même : nommer l'`EffectBonus` natif de `SquigHound` sur le slot
    `IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus`, sa magnitude (−579 au rank du
    montage) et son gate d'adjacence, puis le porter. Foyer probable : un module d'effet sous
    `engine/entities/effects/`, **pas** le pipeline — mais la lecture du décompilé doit le
    confirmer avant toute écriture.
  * La valeur **579** n'est pas rattachée à une variable de gameconfig : le balayage des kits des
    trois unités du montage n'en trouve aucune qui l'égale (à `×1`, `×1,6`, `×1,8`, `×2`). Elle est
    donc soit calculée, soit portée par un effet de TRAIT (les traits ne sont pas des entrées
    `GC.ability`).
  * Le témoin « coup non critique à distance 1 » n'a été obtenu qu'en **forçant** `critChance = 0` :
    sur cinq seeds, le coup a critté **5/5** à distance 1 alors que la chance est de 41 %. Ce n'est
    pas expliqué ici, et ça mériterait d'être regardé si le flux MT devait être re-confronté.
