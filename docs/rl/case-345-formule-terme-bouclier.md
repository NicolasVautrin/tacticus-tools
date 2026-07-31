# case-345 — la formule du terme BOUCLIER de la prédiction, DÉRIVÉE puis confrontée

Résidu #342-r1 fermé. Trois faits, tous mesurés :

1. **La formule est lue au décompilé** (ci-dessous), pas ajustée sur les bornes.
2. **Le port avait un rem UNIQUE là où le natif a un rem PER-PISTE.** Invisible sur
   `AccurateShieldDamage` (indiscernabilité **algébrique**), visible sur son complément :
   `healthDmgMin` natif **1897** vs port **2528** (= exactement un coup), `totalDmgMin` **7380** vs
   **6186**.
3. **`TotalDamage` n'est PAS `AccurateHealthDamage + AccurateShieldDamage`.** C'est ce qui rendait
   `shieldDmgMin != min(shield, totalDmgMin)` — le point que #342 avait constaté sans l'expliquer.

## 1. La formule (`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, par COUP)

```
shield        = IdunBattle.Entities.UnitExtensions$$GetShield(defender)
remShieldMin  = Math.Max(0, shield - prev.Damage.ShieldDamage.Min)
remShieldMax  = Math.Max(0, shield - prev.Damage.ShieldDamage.Max)      # = CurrentShield@+0x04
base          = IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64(...)   # MinMaxDamageFix64
blockedMin    = IdunBattle.Core.Services.DamageCalculations$$CalculateDamageBlockedByShield(
                    remShieldMin, base.Min, attacker, defender)         # = Math.Min(rem, (int)dmg)
blockedMax    = ...                       (remShieldMax, base.Max)

DefaultScenario.Damage.ShieldDamage = new MinMaxDamage(blockedMin, blockedMax)        # cap VIDE
AccurateShieldDamage@+0x50          = new MinMaxDamage(DefaultScenario.Damage.ShieldDamage.Min,
                                                       .Max, cap: CurrentShield@+0x04)
TotalDamage@+0x60                   = new MinMaxDamage(healthFix64).Add(shieldFix64)
```

`IdunBattle.Core.Services.MinMaxDamage$$.ctor` appelle `MinMaxDamage$$ApplyCap` : les **deux**
bornes d'`AccurateShieldDamage` sont rabattues à `CurrentShield`.
`IdunBattle.Core.Services.DamagePredictionResult$$Add` cumule per-piste (`+0x2c`/`+0x30` pour le
scénario, `+0x58`/`+0x5c` pour l'accurate) avec `ApplyCap` à chaque fois.

`TotalDamage` somme le dégât santé **tel qu'il entre** dans
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario` — donc avant le
`blockDamage` et avant `IdunBattle.Entities.Components.FillUpStatComponent$$MaxReduceByMinimum` —
et le bloqué **non capé**.

Layout confirmé par la résolution PAR NOM (#279) : `CurrentShield@0x04`,
`DefaultScenario.Damage.ShieldDamage.{Min@0x2c, Max@0x30}`, `AccurateShieldDamage@0x50`,
`TotalDamage@0x60`.

## 2. Pourquoi #42 ne pouvait PAS trancher

`AccurateShieldDamage.Min = min(min(base.Min, remShieldMin), remShieldMax)`, et
`remShieldMax <= remShieldMin` **toujours** (le cumul MAX absorbé est >= le cumul MIN). Donc
`= min(base.Min, remShieldMax)` : **rem unique et rem per-piste y sont algébriquement
indiscernables**. #42 mesurait ce seul champ — son verdict « rem UNIQUE » n'était pas réfutable
par sa propre mesure. Les deux modèles se séparent sur le **complément** (dégât santé), qu'il
n'avait pas regardé.

Corollaire : le « rem 478 > 0 » de #42 (777 s11 u81), qui servait à gater le plancher #170 sur
`target_shield <= 0`, était un artefact du modèle rem-unique — avec le rem per-piste, ce coup a un
résidu MIN de **0**. La gate est donc retirée : le plancher `MinMaxDamageFix64$$MathMax(dmg, 1)`
est gaté par « il RESTE du dégât après le bouclier », **par borne**.

## 3. La mesure (`probe_345_shield_prediction_formula.py`)

`ultraInceptorSgt -> genesPrimus`, board `MC1_67`, bouclier **5483** posé par `thousSorcerer`
(`ArcaneShield`), 6 coups :

| `Damage` | régime | shieldDmg natif = port | healthDmg | totalDmg | `min(shield,totalDmg)` |
|---|---|---|---|---|---|
| 381  | SOUS-CAP    | `[1830, 2742]` | `[0, 0]`       | `[1830, 2742]`  | `[1830, 2742]` (coïncide) |
| 762  | CAP-PARTIEL | `[3660, 5483]` | `[0, 1]`       | `[3660, 5484]`  | `[3660, 5483]` (coïncide) |
| 2286 | CAP-PARTIEL | `[3658, 5483]` | `[1897, 7026]` | `[7380, 13496]` | `[5483, 5483]` **RÉFUTÉ** |

Généralisation (`emperNoiseMarine -> necroWarden`, 3 coups, même board) : 3 tirs, 2 régimes,
accord complet.

`Damage` 762 est le régime où le résidu de la borne MAX vaut **1** et le facteur de réduction
~0,30 : sans plancher le port rendait 0, le natif rend 1. Balayage 763..766 (résidus 13/19/25/31
-> 4/6/7/9) : plancher inerte, port == natif — il ne peut donc pas masquer une erreur de facteur.

**Mutation jouée** (`--` le port d'avant #345, rem unique) : `AccurateShieldDamage` **inchangé sur
les 3 tirs** (indiscernable, comme prévu) ; complément **cassé** à `Damage` 2286.

## 4. Gardes

`tests/engine/test_345_shield_prediction_formula_live.py` (8 tests) : terme réellement exercé,
>= 2 régimes, deux modèles rivaux réfutés par la mesure, port == natif sur le bouclier ET sur le
complément, mutation aveugle sur le bouclier et rouge sur le complément.

Non régressé : `test_342_shield_term_rounding_live.py` (8), `test_noblocking_prediction_live.py` +
`test_prediction_trait_gates_live.py` (8). Sans bouclier (`target_shield <= 0`) le chemin est
**strictement inchangé** — c'est ce qui borne le risque du retrait de gate.

## 5. Ce qui n'est PAS couvert

- **Le régime SUR-CAP** (les deux bornes rabattues) n'est pas atteint par ces montages : la piste
  MIN sature le bouclier au même coup que la piste MAX ou jamais.
- **`DefaultScenario.Damage.ShieldDamage` n'est pas exposé par le décodeur** : il est déduit, pas
  lu. Le vérifier directement demanderait d'ajouter `scenarioShieldDamage` aux champs rendus par
  `readDamagePredictionResult` (le chemin nommé existe déjà dans `DPR_PATHS`) — **reinject requis**.
- **La face COMBAT** : `engine/runner/operations/damage_utility.py` rend toujours `shieldBefore = 0`
  (résidu pré-existant, hors périmètre).
- **Les 8 autres porteurs de `DSLBehaviors$$CreateShield`** ne sont pas exercés.
- La gate du plancher est établie **par la mesure**, pas par le décompilé : la zone ghidra
  correspondante (`PredictAttackRaw`, second `MinMaxDamageFix64$$MathMax`) a ses locales de pile
  fusionnées et son `op_Equality` résolu sur un corps dédupliqué (`XNamespace`) — elle se lit
  « plancher si `blockedMax == 0` », ce que la mesure contredit. Point d'ancrage à hooker pour
  trancher au natif : l'entrée de ce `MathMax`.
