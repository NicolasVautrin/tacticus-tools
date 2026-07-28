# case R6-c — bornes COMBAT des groupes `amount` du canal de coups additionnels (#179)

**Critère (binaire, deux axes)** : un groupe de coups additionnels en mode `amount` tire-t-il, en
COMBAT, dans les mêmes bornes que le natif — **et** consomme-t-il le même nombre de tirages ?

| axe | réponse |
|---|---|
| **VALEUR** | **NON** avant ce cas. Les trois descripteurs restants ne rendaient que leur nœud DISPLAY ; la face COMBAT étalait donc cette valeur à ±20 % au lieu de lire le nœud ROLL. **PORTÉ**, live **8/8 contre 0/8**. |
| **CONSOMMATION** | **NON** avant ce cas, pour la forme scalaire : le port consommait **1 tirage de trop par coup**. **PORTÉ**, live **8/8 contre 0/8** (natif 3, port 3, contrefactuel 4). |

Les deux axes se répondent séparément : un port qui rend la bonne valeur en consommant un tirage
de trop désynchronise tout l'aval. C'est pour la forme (2) ci-dessous que l'axe consommation est
le seul verdict *bon marché* — la valeur seule n'y discrimine pas de façon fiable (un tirage
±20 % peut tomber sur `v`).

---

## 0. Gate de confrontabilité — les trois porteurs sont atteignables

| porteur | catégorie | présence `rl_duel.py build --list-pool` | rôle |
|---|---|---|---|
| `tauCrisis` | HERO | **oui**, direct | forme (1), nœuds distincts |
| `deathPutrifier` | HERO | **oui**, direct | forme (2), nœud scalaire — **deux** descripteurs |
| `blackObliterator` | HERO | **oui**, direct | témoin (corrigé en #159) |

Aucun n'est NPC ni summon : les trois se spawnent directement. Le blocage invoqué en #159
(« pas de montage live sur leur porteur ») n'était donc pas une impossibilité — il n'avait pas
été monté.

---

## 1. La RE — deux nœuds, et la face lue dépend d'un booléen

### 1.1 Le conteneur — `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`

Lu verbatim (`gqfc5mff6c`), c'est l'instruction qui fixe tout :

```
param_1[0] = param_2                       # condition
param_1[1] = param_3                       # +0x08  noeud ROLL
param_1[3] = param_6                       # +0x18  count
if (param_8 != 0) param_3 = param_8;
param_1[2] = param_3                       # +0x10  noeud DISPLAY  <- repli sur ROLL
```

⇒ **`param_8 == 0` ne veut pas dire « pas de display » : il veut dire « display == roll ».**

### 1.2 L'évaluateur — `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits`

Signature `(out, this, entities, useDisplay)` :

```
if (!condition.ShouldTrigger(entities))  return default        # slot 5
count  = countNode != null ? countNode.<slot 1>(entities) : 1  # +0x18
amount = displayNode.<slot 4>(entities)                        # +0x10   TOUJOURS
min = max = amount
if (!useDisplay) {                                             # <- FACE COMBAT
    min = rollNode.<slot 2>(entities)                          # +0x08
    max = rollNode.<slot 3>(entities)
}
-> AdditionalHitsInfo{ MinMax = MinMaxDamage(min, max), amount, count, profile }
```

`IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` passe
l'octet **explicitement mis à zéro** ⇒ la face COMBAT lit **toujours** le nœud ROLL ;
`IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction` prend
l'autre branche ⇒ cellule dégénérée `(amount, amount)` que le pipeline de prédiction étale ensuite
(`IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread`).

### 1.3 Sémantique des nœuds, lue et non supposée

- `IdunBattleLogic.Entities.DSLFactory$$ConfigVar` construit un
  `IdunBattle.Entities.Formulas.ConfigAmount` — une **feuille scalaire**.
- `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin` lit `this+0x10` et appelle **slot 1
  (`Calculate`)** ; `CalculateMax` fait de même sur `this+0x18`. Les bornes d'un `RandomAmount`
  sont donc les valeurs de ses deux sous-nœuds.
- `IdunBattle.Entities.Formulas.ConditionalAmount$$CalculateMin` évalue la condition (`this+0x10`)
  puis **délègue `CalculateMin`** à `this+0x18` (branche vraie) ou `this+0x20` (branche fausse) —
  ce n'est donc pas la condition qui est figée, mais bien la borne de la branche retenue.

### 1.4 Les trois descripteurs, verbatim

| descripteur | nœud ROLL (`param_3`) | nœud DISPLAY (`param_8`) | bornes COMBAT |
|---|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` | `ConditionalAmount(cond, RandomAmount(Sum(minDmg,extraDmg), Sum(maxDmg,extraDmg)), RandomAmount(minDmg,maxDmg))` | `ConditionalAmount(cond, Sum(minDmg,extraDmg), minDmg)` | `[minDmg, maxDmg]`, **+`extraDmg` sur les DEUX bornes** si `cond` |
| `IdunBattle.Entities.Effects.Loki.FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` | `ConfigVar(0xb)` — scalaire | **0** ⇒ repli sur ROLL | `[v, v]` **dégénéré** |
| `IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits` | `ConfigVar(8)` — scalaire | même nœud (`Create` **inliné** : `param_1[1] == param_1[2]`) | `[v, v]` **dégénéré** |

`cond` = `HasEffect(target@0x178, 0x462 Markerlight, 1, 6) | HasTrait(target@0x178, 5 Mechanical)`.

Sur `ExplosiveMaladies` le compilateur a inliné `Create` et **résolu le repli à la compilation** —
les deux champs reçoivent littéralement le même objet. Ce descripteur pose aussi `+0x30 = 1`
(`forceOverkill`), qui reste non transporté par le canal (résidu antérieur, inchangé ici).

### 1.5 Pourquoi la consommation change, et pas seulement la valeur

`IdunBattle.Core.HitDamage$$GetDamage`, verbatim :

```
if (*param_1 == param_1[1])  return *param_1;              # min == max -> 0 TIRAGE
if (param_3 /*useAverage*/)  return (max + min) / 2;
return rng.Range(min, max + 1);
```

Une cellule dégénérée **court-circuite avant tout tirage**. Le port, lui, fabriquait
`[0.8v, 1.2v]` puis tirait dedans : **un `genrand_int32` de trop par coup**. Le resolve slot 8
(`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`), qui n'a *pas* de gate
`min == max`, reste consommé des deux côtés — c'est ce qui fait que le budget total diffère
d'exactement 1.

---

## 2. Le port

`BaseEffect.additional_hit_groups` documentait déjà le contrat bi-canal (`min`/`max` = ROLL lu par
le COMBAT ; `amount` = DISPLAY lu par la PRÉDICTION, les deux **coexistant**), et
`execute_additional_hits` en mirrorait déjà la précédence. Il ne manquait que les trois
descripteurs :

- `CyclicIonBlasterAdditionalHitsEffect` rend désormais `min`/`max` **en plus** d'`amount`, avec
  `extraDmg` ajouté aux **deux** bornes sur la branche vraie. Que `amount == min` y est une
  propriété du descripteur (branche fausse du DISPLAY = `minDmg` nu), **pas** une règle du canal.
- `FoulInfusionExtraHitsEffect` et `_ExplosiveMaladiesAuraHitsBase` rendent `min == max == v`.

**Face PRÉDICTION strictement inchangée** : les deux sites de
`playbook/prediction/normal_attack.py` testent `"amount" in _g` **en premier** et ne regardent
`min`/`max` que dans la branche `else`. Le seul consommateur de `min`/`max` est
`execute_additional_hits`.

---

## 3. La mesure

Protocole : flux RNG calé par `dumpRng` avant le cast, rejeu offline de la **même** attaque sur le
**même** flux, sous le port livré et sous un contrefactuel. Le contrefactuel se fabrique en
**retirant `min`/`max` du groupe livré** — on ne re-dérive rien, donc on ne peut pas se tromper en
construisant l'adversaire. Budget de tirages natif = re-simulation du Mersenne Twister entre deux
`dumpRng` (le nombre de pas EST le nombre de tirages).

Montages : board `MC1_67`, `--crit 0,0 --block-target 0,0 --hp-target 90000 --armor-target 6000`.

### 3.a Forme (1) — nœuds distincts, axe VALEUR

Deux montages qui **inversent** la signature, donc un facteur calé sur l'un se trahit sur l'autre :

| montage | cible | `cond` | bornes ROLL | contrefactuel `amount ±20 %` | largeur ROLL / contrefactuel |
|---|---|---|---|---|---|
| A | `astraCreed` (aucun trait hors Hero) | faux | `[599, 898]` | `[479, 719]` | 299 / 240 — ROLL **plus large** |
| B | `admecMarshall` (`Mechanical` seul) | vrai | `[1198, 1497]` | `[958, 1437]` | 299 / 479 — ROLL **plus étroit** |

| seed | A live = port | A contrefactuel | B live = port | B contrefactuel |
|---|---|---|---|---|
| 777 | `[355, 368, 323]` | `[333, 280, 290]` | `[634, 647, 602]` | `[455, 548, 513]` |
| 12345 | `[351, 283, 283]` | `[277, 228, 269]` | `[630, 562, 562]` | `[563, 489, 571]` |
| 314159 | `[389, 369, 396]` | `[279, 248, 283]` | `[668, 648, 675]` | `[648, 638, 581]` |
| 88 | `[330, 294, 393]` | `[327, 319, 318]` | `[609, 573, 672]` | `[555, 612, 501]` |

⇒ **port 8/8, contrefactuel 0/8, 8/8 montages discriminants.** Les coups d'arme sont bit-exacts
**8/8** (`[221, 185, 187, 221, 189, 206]` sur 777, …) : le flux est aligné à l'entrée du groupe,
donc la mesure porte bien sur les **bornes** et pas sur un décalage de tirages. Le montage B
vérifie en propre que `extraDmg` alimente les **deux** bornes — un port qui ne l'ajouterait qu'au
minimum rendrait `[1198, 898]`.

### 3.b Forme (2) — nœud scalaire, axe CONSOMMATION

Deux descripteurs, deux **chemins de code distincts** (aura vs porteur) et deux formes natives
distinctes (`Create` inliné vs `param_8 = 0` explicite) :

| montage | attaquant | groupe live = port | contrefactuel | genrand natif | port | contrefactuel |
|---|---|---|---|---|---|---|
| `ExplosiveMaladies` (aura) | `admecMarshall` adjacent à `deathPutrifier`, ranged | `[1496]` × 4 seeds | `[1275]`, `[1346]`, `[1258]`, `[1989]` | 3 | **3** | **4** |
| `FoulInfusion` (porteur) | `deathPutrifier` en mêlée après cast 1038 | `[1954]` × 4 seeds | `[1764]`, `[1717]`, `[1886]`, `[1850]` | 3 | **3** | **4** |

⇒ **port 8/8 sur les deux axes, contrefactuel 0/8 sur les deux axes.**

Le résultat le plus probant n'est pas une égalité mais une **invariance** : le coup du groupe vaut
`1496` (resp. `1954`) sur **quatre flux RNG différents**, alors que les coups d'arme du même
montage varient (`2793 / 2833 / 2725 / 2160`). Une cellule qui ne bouge pas quand le flux bouge
**est** une cellule dégénérée — et le contrefactuel, lui, varie bien, ce qui prouve que le montage
n'est pas simplement insensible.

---

## 4. Ce qui n'est PAS couvert

- ~~**Résidu NEUF, orthogonal — la cellule d'ARME de `deathPutrifier` en mêlée.**~~ **RÉSOLU**
  (`docs/rl/case-dpw-deathputrifier-weapon-cell.md`, port live 4/4, contrefactuel 0/4). Le
  montage `foul` donnait, sur le coup d'arme, live `3219/3529/2923/2750` contre offline
  `2333/2649/2505/3170` — écart de **signe variable** (seed 88), donc bien une divergence de
  **BORNES** : cellule native `[2248, 3621]` (résolue, unique, sur 4 flux) contre `[2248, 3373]`
  au port. ⚠ **L'argument « le groupe est bit-exact donc l'armure est juste » écrit ici était
  FAUX** : la valeur du groupe (2792 brut, profil Toxic p70) tombe des DEUX côtés sur la branche
  PERÇAGE de `max(0, d − armure, d × 70 %)`, donc elle est **armure-indépendante** — ce montage
  n'était pas discriminant sur l'armure. Le terme réel : l'attaque est re-résolue sur
  `astraSmnKell` (invoqué par `SwornProtector`, #120bis), qui APPARAÎT dans l'aura Contagion de
  `deathPutrifier` et y prend `ContagionsOfNurgle_ArmorReduction1` (−20 % ⇒ armure 1496 → **1197**).
- **La branche `Markerlight`** de `cond` (effet `0x462`) n'est pas exercée : les deux montages
  passent par `HasTrait(target, 5 Mechanical)`. Les deux disjoints alimentent le **même**
  `ConditionalAmount`, donc la branche testée est la même — mais le gate `HasEffect(..., 1, 6)`
  lui-même (ses deux derniers arguments) n'est pas confronté.
- **`ExplosiveMaladies_ExtraMeleeAttackEffect`** partage le mold corrigé
  (`_ExplosiveMaladiesAuraHitsBase`) mais n'a pas de montage propre : son gate supplémentaire
  (alliance Chaos) reste non confronté, comme avant ce cas.
- **`forceOverkill = 1`** d'`ExplosiveMaladies` (`+0x30`) n'est toujours pas transporté par le
  canal `additional_hit_groups` — résidu antérieur, inchangé.
- **Les groupes `predefined`** (SquigHound, CordClaw, FearOfTheUnseen, InfernalPacts,
  MasterAnnihilator) : leur face PRÉDICTION reste sur `predefined MinMaxDamage(min, max)` alors
  que le natif y rendrait `(slot4(displayNode), slot4(displayNode))` étalé à ±20 %. Numériquement
  indistinguable tant que leurs paires sont des paires ±20 % exactes autour de leur moyenne.
  Inchangé — le corriger sans montage discriminant serait spéculatif.

---

## 5. Reproduire

```
python probe_r6c_ah_bounds.py --case cyclic   --target astraCreed    --seeds 777,12345,314159,88
python probe_r6c_ah_bounds.py --case cyclic   --target admecMarshall --seeds 777,12345,314159,88
python probe_r6c_ah_bounds.py --case maladies --target astraCreed    --seeds 777,12345,314159,88
python probe_r6c_ah_bounds.py --case foul     --target astraCreed    --seeds 777,12345,314159,88

python -m pytest tests/engine/runner/test_additional_hits_scalar_bounds_live.py -q
```

Non-régression rejouée : `test_additional_hits_amount_bounds_live.py` +
`test_additional_hits_roll_order_live.py` + `test_additional_hits_rounding_live.py` +
`test_additional_hits_after_hit_maybe_live.py` (**20 passed**).

---

## 6. Interaction avec le vecteur `On(DamageDealt = 0x10)` de #85 — vérifiée, nulle

#85 a introduit l'émission d'un vecteur **neuf** sur le chemin de dégât
(`AttackDamageOperation._apply_damage_pipeline`, gate `applied > 0`), **par groupe de dégât
résolu**. C'est exactement le terrain de l'axe CONSOMMATION : si un consommateur de ce vecteur
tirait du RNG, le budget mesuré ici bougerait.

**Constat re-dérivé des registres** (et non repris de la docstring de `damage_dealt_triggers`) :
un balayage de `ABILITY_TRIGGERS` / `ACTIVE_ABILITY_TRIGGERS` / `EFFECT_TRIGGERS` /
`TRAIT_TRIGGERS` sur `event_id == 16` rend **exactement une** entrée — la clé `FleshmetalGuns`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger`
= `On(0x10) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5 = WarpHail)`), dont le behaviour
pose un tile-effect — **aucun tirage**. `OnFireDamageAbility` / `OnToxicDamageAbility`, qui
écoutent nativement le même vecteur, restent appelés impérativement depuis
`after_hit_normal_attack` : le `next_bool` du Toxic n'a donc pas été déplacé.

⇒ Aucun porteur des montages de ce cas (`tauCrisis`, `deathPutrifier`, `admecMarshall`,
`astraCreed`) ne porte `FleshmetalGuns` : le vecteur neuf y est un **no-op strict**. **Mesuré**,
pas seulement déduit — après rebase sur `13b2bac`, l'axe consommation est **bit-identique** :
natif 3 = port 3 ≠ contrefactuel 4 (4/4), et les valeurs de groupe sont inchangées (`[1496]`,
`[1954]`, contrefactuels `1275`/`1346`/`1764`/`1717`).

Le seul montage où ce vecteur **fire réellement** est celui de la non-régression #159
(`blackObliterator` en variante **WarpHail**, le porteur gaté) : il reste vert. C'est aussi ce
qui ferme, côté #85, le « +1 tirage constant » que `case-159` §2.c imputait au volet
`DespoiledGround` alors non porté.

Re-jeu complet après rebase : les 26 ci-dessus **plus** `test_despoiled_ground_live.py`
(la garde du vecteur neuf) — **31 passed**.
