# Case #30 — Bornes RAW du DamagePredictionResult (raw @0x24/0x28 vs accurate @0x58)

Statut : RE structurel PROUVÉ (décompile + live event-dumps). Fix candidat identifié, **validation
live requise** (session Frida tombée en cours d'investigation — voir §Validation).

Build : gqfc5mff6c. VAs absolues (RVA = VA − 0x180000000).

## Symptômes (agreement-stages.md leads 4-5, seed 31337, event-dumps capturés live)

Champs natifs de l'event `aiPlaybookPredict` (= `MakeDamagePredictions`) :
`willKillDmg`=raw min @0x24, `mightKillDmg`=raw max @0x28, `healthDmgMin/Max`=accurate (capé HP),
`totalDmgMin/Max`=total, `appliedHits`=nb coups.

Observation clé (5 event-dumps, seed 31337) : **`willKillDmg == totalDmgMin` ET `mightKillDmg ==
totalDmgMax`** dans TOUS les cas → le raw @0x24/0x28 EST le `totalDmg` (dégât total NON capé HP).

| step | u→tgt | ab | hpBefore | appliedHits | willKill/mightKill (raw) | healthMin/Max (accurate) |
|------|-------|----|----------|-------------|--------------------------|--------------------------|
| 8    | 83→91 | 69 | 1499     | 3           | 1498 / **1949**          | 1498 / 1499 (capé HP)    |
| 13   | 93→83 | 69 | 2783     | 4           | 2704 / **4056**          | 2704 / 2783 (capé HP)    |
| 6    | 85→95 | 1027| 2708    | 1           | 2792 / 4188              | 2708 / 2708              |
| 17   | 77→87 | 69 | 322      | 1           | 1378 / 2067              | 322 / 322                |
| 18   | 89→81 | 69 | 5274     | 2           | 5526 / 6492              | 5274 / 5274              |

Notre port (offline) à ces steps :
- s08 : raw off=(1498, **1498**) vs nat (1498, 1949) → `kill` off=False nat=True (raw max écrasé).
- s13 : raw off=(**4428**, **6640**) vs nat (2704, 4056) → `killSure` off=True nat=False (raw sur-évalué).

## Structure native (décompile)

### DamagePredictionResult (offsets via getters)
- `get_HealthDamage @18102be20` : renvoie `{@0x1c(min), @0x24}` (MinMax bytes).
- `get_WillBeKill @18102bef0` : `HP@0x00 <= raw@0x24(min)` → raw min sert le kill-sûr.
- `get_MightBeKill @18102be30` : `HP@0x00 <= raw@0x28(max)` → raw max sert le kill-possible.
- **@0x24 = raw MIN, @0x28 = raw MAX, @0x00 = HP cible. accurate = @0x58 (get_HealthDamageWithBlock lit
  0x1c..0x28 pour le split block ; l'accurate capé HP vit à @0x58).**

### `PredictAttackRaw @181032fb0` (par coup)
Ordre des écritures relativement à `ApplyTraitDamageLimitsToDamage @18102c650` :
1. `local_8b8`/`uStack_8b0` = bornes lo/hi (Fix64) posées BRUTES (@0x1810355a8, avant cap).
2. `ApplyTraitDamageLimitsToDamage(param_2, 1, &local_8b8, &uStack_8b0)` (@0x1810359c7) — **cape lo/hi
   EN PLACE** (member-cap, Resilient hp-1, Impervious, boss). AUCUNE sauvegarde des bornes brutes n'est
   lue entre la pose (2157) et ce call (2295) : tout l'aval consomme les bornes capées-trait.
3. `CalculateDamagePredictionScenario @18102ed00` reçoit ces bornes (via `param_6`).

### `CalculateDamagePredictionScenario @18102ed00` (struct de sortie)
Produit une struct où :
- champ **accurate** (0x04/0x08/0x0c/0x10) = `Max(0, eff − shieldAbs)` PUIS
  `FillUpStatComponent.MaxReduceByMinimum @180f9b800/900` appliqué à min ET max ;
- champ **raw** (0x24/0x2c) = `{op_Explicit(param_6+0x10), op_Explicit(param_6+0x18)}` = **les bornes
  ENTRANTES `param_6`**, SANS le cap FillUpStat, SANS re-soustraction shieldAbs.

`MaxReduceByMinimum` (les 2 surcharges) : `cap = CurrentValue(+0x18) − Min(CurrentValue, reservedMin
(+0x1c Nullable))` ; **NO-OP** si pas de Nullable minimum (héros normal → accurate = raw par coup). La
surcharge @180f9b800 écrit aussi le flag `limitedByMinHp` (`résultat != entrée`).

### `Add @18102a710` (agrégation multi-coups)
Somme SÉPARÉMENT chaque MinMaxDamage du résultat, chacun suivi d'`ApplyCap` (normalisation min≤max,
PAS un cap HP) :
- raw @0x24/0x28 : `param_1+0x24 += param_2[4].hi ; param_1+0x28 += param_2[5].lo ; ApplyCap(+0x1c)`.
- accurate @0x58 : `param_1+0x60 += param_2[0xc] ; ApplyCap(+0x58)` (chaîne santé).

→ **raw agrégé = Σ des raw par coup ; accurate agrégé = Σ des accurate par coup.** Aucun re-cap HP
sur le total raw. C'est pourquoi `mightKillDmg` (1949, 4056) dépasse `hpBefore` alors que
`healthDmgMax` est plafonné à HP.

## Porte overkill (Resilient hp-1) — RE confirmé fidèle

- `IsOverkill @181032bc0` (entrée service) : `CanBeOverkilled(tgt)` → `maxHP=GetStat(tgt,5,0)` →
  délègue `IsOverkill @181032db0(maxHP, dmg, …, allow=*(cfg+0x30), threshold=*(cfg+0x34))`.
- `ApplyTraitDamageLimitsToDamage` calcule le flag UNE fois depuis la borne MIN
  (`accum = (param_11−param_9) + param_12 + minDmg`, base pct = param_11=maxHP), l'applique aux 2
  bornes via `ApplyResilientTraitDamageLimit @18102c3a0` (cap `current_health−1` ssi trait Resilient
  0x3f1 && maxHealth>1 && current_health>0 && !overkill).
- **Le port `compute_prediction_overkill`/`is_overkill`/`apply_resilient_trait_damage_limit`
  (trait_damage_limits.py) est FIDÈLE en structure.** Le seul paramètre NON PROUVÉ = le threshold
  `*(cfg+0x34)` (config DI, asset-driven) ; le port suppose `overkillDmgPctOfHealth`=100 (HYPOTHÈSE).

## Diagnostic du bug (port) — CAUSE RACINE = la porte OVERKILL sur cible Resilient

Faits vérifiés :
- `DamagePredictionResult.add` (damage_prediction.py L71-93) est CORRECT et fidèle à `Add @18102a710`
  (raw sommé séparément de l'accurate, chacun `apply_cap` = normalisation min≤max). **Le bug n'est PAS
  dans l'agrégation.**
- **tgt=91 (bloodDeathCompany, lead 4) A le trait Resilient** (gameconfig : `['Hero','RapidAssault',
  'Resilient','Unstoppable']`). Donc `target_has_resilient=True` est CORRECT. tgt=83 (eldarAutarch,
  lead 5) ne l'a PAS.
- Lead 4 natif : raw=(1498, **1949**) ; accurate=(1498, **1499**=HP exact, PAS hp-1=1498). ⇒ **le natif
  n'applique PAS le cap Resilient hp-1** (ni au raw ni à l'accurate) : l'accurate est simplement capé à
  HP. La seule lecture cohérente : **côté natif overkill=TRUE** (le coup tue la cible Resilient → le cap
  hp-1 est BYPASSÉ, cf. `ApplyResilientTraitDamageLimit @18102c3a0` : cap ssi `!overkill`).
- Notre port : `compute_prediction_overkill` retourne **False** (threshold=100 + évalué par coup sur
  `dmg_min` d'un coup ~500 < curHP) → on applique le cap Resilient hp-1 → raw écrasé à (1498,1498).

**CAUSE RACINE : notre porte overkill diverge du natif → cap Resilient appliqué à tort.** Trois
paramètres config-DI NON PROUVÉS entrent en jeu (à valider live) :
1. **threshold** `*(cfg+0x34)` — port suppose 100. S'il est bas, `IsOverkill @181032db0` renvoie 1 dès
   `curHP ≤ dmg` via la branche ratio.
2. **allow_flag** `*(cfg+0x30)` (param_4 d'IsOverkill) — port suppose 0. **Si =1**, `IsOverkill` renvoie
   1 dès `param_1 ≤ param_2` (curHP ≤ dmg) SANS condition de ratio → overkill dès que le coup tue.
3. **granularité** : le port évalue l'overkill par coup sur `dmg_min` d'UN coup ; il se peut que le
   natif l'évalue sur le dégât CUMULÉ/total (1949 ≥ curHP 1499). À vérifier : le `accum` d'ATL utilise
   `(param_11−param_9)+param_12+minDmg` par coup, mais `param_9`/`param_11` (curHP/maxHP) sont peut-être
   les valeurs INITIALES (non déplétées) → un coup unique suffit si base non déplétée.

- **Lead 5 (s13, tgt=83 NON Resilient) = problème SÉPARÉ** : `accurate min` diverge déjà (2704 nat vs
  2783 off) ⇒ écart de CALCUL du dégât brut (defender-modifier sur eldarAutarch non modélisé) propagé au
  raw ; le `killSure` fantôme en est la conséquence, pas un défaut de la logique raw. Ne PAS le confondre
  avec le lead 4.

## Fix candidat (à valider live)

Le raw et l'accurate sont déjà séparés correctement (add + predict_attack_raw). Le fix porte sur la
PORTE OVERKILL de `predict_attack_raw`/`compute_prediction_overkill` :
- déterminer les vraies valeurs `allow_flag` (cfg+0x30) et `threshold` (cfg+0x34) via un probe live
  (hook `IsOverkill @181032db0` args, OU tracer `apply_trait_damage_limits_to_damage` sur une cible
  Resilient et observer la bascule cap/no-cap) ;
- l'hypothèse la plus probable : `allow_flag=1` (overkill dès `dmg ≥ curHP`) — ce qui, pour lead 4,
  déclencherait overkill sur le coup qui tue → bypass du cap Resilient → raw (et accurate) non plafonnés
  à hp-1 → raw=(1498,1949), accurate capé HP=1499, kill=True. À CONFIRMER LIVE.

## Ce que le validator doit attaquer en priorité
1. La granularité + les 2 flags config-DI de la porte overkill (le point faible : 3 hypothèses non
   prouvées se combinent). Un hook `IsOverkill @181032db0` capturant `param_4`(allow)/`param_7`(threshold)
   sur une cible Resilient tranche net.
2. Ne PAS régler lead 5 par le même fix (defender-mod distinct) — vérifier qu'il ne régresse pas.

## Validation

Session Frida tombée pendant l'investigation (jeu fermé → `session:null`). Les event-dumps ci-dessus
ont été capturés AVANT la chute (seed 31337, 20 pas). Re-tester le fix : re-inject + warmup, puis
`walk_dump_raw` (mon dumper scratchpad) sur seeds 31337 + 777, cible s08 (raw doit passer à
(1498,1949), kill→True) et s13 (traiter séparément le defender-mod).
