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
| `orksRuntherd` | `SquigHound` | `BeastSlayer` | **579** |
| `orksNob` | `SmashaEad` | `BeastSlayer`, `Unstoppable` | 0 |
| `orksWarboss` | `LightImUp` | `BigTarget`, `CrushingStrike`, `FinalJustice`, `Mechanical` | 0 |

`GetStuckIn` est porté par les **trois** ⇒ écarté. `BeastSlayer` est porté par `orksNob`, qui est
bit-exact ⇒ écarté.

⚠ **Le discriminant est l'UNITÉ `orksRuntherd`, pas son passif** — et imputer l'écart à `SquigHound`
(le seul passif restant) était une **déduction, pas une lecture**. Elle était FAUSSE. Le décompilé a
tranché : ce qui distingue `orksRuntherd` est sa **RELIQUE**, invisible de la colonne « passifs » —
`data/seed-bc.json` lui donne `TertiaryAbility = 1475` (`SupaCyborkBody`), **équipée au seed**
(l'« état 1 » des trois états d'une relique). C'est le rappel exact du CLAUDE.md : un recensement
qui ne lit pas les cinq voies d'attribution ne prouve rien de ce qu'il ne voit pas.

## 3bis. La cause, LUE au décompilé (build `rnca9r7q6c`)

    IdunBattle.Entities.Effects.Loki.SupaCyborkBody_CritDmgReductionEffect$$CreateCritDamageBonus
        = EffectBonus.ForSubtraction( DSLTriggers.get_OwnerIsTarget,
                                      DSLFormulas.Multiply(ConfigVar(0x97 = critDmgReduction),
                                                           DSLFormulas.EffectLevel) )
    ...$$CreateActiveCondition = HasAdjacentEnemies(Owner, Tiles(Owner))
    ...$$GetCalculateLevel     = Count(AdjacentEnemies(Owner))

`critDmgReduction[49] = critDmgReduction[50] = **579**` au gameconfig — **la valeur mesurée, à
l'unité**. `EffectBonus$$ForSubtraction` remplit `Item2`, et
`DamagePrediction$$GetCritDamageBonusFromEffects` accumule `Item1 - Item2` ⇒ contribution
**négative**. `DamagePrediction$$CalculateCriticalDamage` est bien
`Math.Max(0, GetStat(10) + GetCritDamageBonusFromEffects(...))`, et
`DamageCalculations$$ApplyCritDamage` est une **addition FLAT** sur la valeur roulée brute — le
pipeline est donc hors de cause, exactement comme le mesurait le carré.

Le mécanisme explique les cinq cellules sans rien ajouter : la condition et le niveau se lisent sur
les ennemis **adjacents à la CIBLE**. Au contact, le caster est ce voisin ⇒ `EffectLevel = 1` ⇒
`max(0, 2082 − 579) = 1503`. À distance 2 ⇒ 0 voisin ⇒ condition fausse ⇒ 2082.

⚠ **`EffectLevel` est un COMPTE, pas un booléen** : deux ennemis au contact de la cible
retrancheraient **1158**. Figer 579 passerait le cas mesuré et échouerait au suivant.

⚠ **`RangedInMelee` est RÉFUTÉ, et le commentaire du port n'est pas infirmé** :
`DamageCalculations$$CalculateRangedInMeleeReduction` n'a que des xrefs **DATA**, et aucun des
quatre appelants de `DamageCalculations$$ShouldApplyRangedInMelee` n'est sur le chemin
d'`AttackDamageOperation$$ExecuteHit`.

## 4. ATTRIBUTION — pipeline partagé, PAS le vecteur

C'était la question à trancher, et elle est tranchée :

  * le **vecteur** `LivingLightning` passe au pipeline des bornes JUSTES (`HitDamage(2394, 2992)`,
    tracées) et le bon roll — il est bit-exact dans **quatre** des cinq cellules du carré, y compris
    sur un coup critique ;
  * **le pipeline de dégât partagé est HORS DE CAUSE lui aussi**, et c'est LU, pas supposé : son
    foyer crit (`AttackDamageOperation._crit_params` → `_crit_board` + `_crit_carriers`, balayage
    board-wide cible comprise) est fidèle au natif et les **trois** vecteurs lui passent bien
    `state`/`attacker_id`/`target_id`. La formule native
    (`Math.Max(0, GetStat(10) + GetCritDamageBonusFromEffects(...))`, puis addition FLAT par
    `DamageCalculations$$ApplyCritDamage`) est celle qu'il mirrore ;
  * l'écart est **SOUS** ce foyer : le bonus d'effets rendu vaut **0** (tracé) parce que l'instance
    d'effet qui devrait le porter **n'existe pas dans l'état porté**.

**La cause racine est un trou de MONTAGE D'ÉTAT, pas de calcul.** Mesuré : `decisionView.effects[]`
de la capture ne publie, pour la cible, que
`SquigHound_AdditionalHits (1292)`, `SquigHound_IgnoreBattleFatigue (1078)`,
`BeastSlayer_ExtraDmg (1516)`, `BeastSlayer_ExtraBlock (1517)` —
**`SupaCyborkBody_CritDmgReduction` n'y est PAS**, ni actif ni inactif. Le port ne peut donc pas le
construire, alors que son mirror EXISTE et est enregistré
(`engine/entities/effects/loki/supa_cybork_body.py`, `entities/effects/factory.py`).

⇒ **Aucun correctif n'est livré ici** : établir si l'effet est absent parce qu'il est CONDITIONNEL
et inactif à l'instant de la capture (le caster n'est pas encore adjacent — il l'est après le pas,
qui est justement ce que le vecteur mesure) ou parce que le capteur ne le publie pas, décide de deux
correctifs très différents. Le correctif est ouvert en **`#961-r3`**.

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

  * **`#961-r3`** — le correctif : faire exister l'instance
    `SupaCyborkBody_CritDmgReduction` dans l'état porté. Le premier étage à trancher est
    **pourquoi elle est absente de `decisionView.effects`** — effet conditionnel non encore actif à
    la capture, ou capteur qui ne le publie pas. Si c'est le second, il faut une fenêtre de
    reinject ; si c'est le premier, le correctif est un montage d'état, sans capteur.
  * Les **trois autres reliques équipées au seed** (`necroSpyder` 1462, `admecMarshall` /
    `admecRuststalker` 1457) sont dans le **même angle mort** : si l'instance de 1475 n'est pas
    montée, rien ne dit que les leurs le soient. Non vérifié ici.
  * **Le compte, pas la constante** : aucun test de #961-r3 ne doit figer 579 — `EffectLevel` est
    `Count(AdjacentEnemies(Owner))`, donc deux ennemis au contact de la cible valent **1158**. Le
    régime à deux voisins n'est pas monté ici.
  * Le plancher `Math.Max(0, ...)` de `CalculateCriticalDamage` ne doit pas devenir un **gate du
    tirage** : `RollCritical` ne lit que la CHANCE (gisement #950). Une cible entourée peut pousser
    le crit sous zéro sans qu'aucun tirage disparaisse.
  * Le témoin « coup non critique à distance 1 » n'a été obtenu qu'en **forçant** `critChance = 0` :
    sur cinq seeds, le coup a critté **5/5** à distance 1 alors que la chance est de 41 %. Ce n'est
    pas expliqué ici, et ça mériterait d'être regardé si le flux MT devait être re-confronté.
