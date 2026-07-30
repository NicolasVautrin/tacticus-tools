# case-278 — les VALEURS du canal `repair_prediction`, confrontées au LIVE

**Verdict : canal CONFORME, #278 FERMÉ.** Le décodage livré par `33292bc4` publie les bons
nombres, et pas seulement la bonne forme. Quatre égalités chiffrées, deux porteurs, deux
régimes de saturation, un cast natif — plus une garde vue **rouge** par mutation adversariale.

---

## 1. Ce qui restait à faire, et pourquoi les deux sources déjà au dossier ne suffisaient pas

Le correctif de décodage était déjà livré. Le hook lit deux `int32` dans RAX, miroir exact de
`PredictHeal` ; il n'y a plus d'offset à maintenir. Sa **forme** était établie par deux sources
indépendantes — le RPC `classFields` (live) et le décompilé du build `rnca9r7q6c`.

Aucune des deux ne peut trancher la question qui restait : **est-ce que les nombres publiés sont
les bons ?** `classFields` dit où sont les champs, le décompilé dit ce que la fonction calcule ;
ni l'un ni l'autre ne dit que le hook lit le bon registre, dans le bon sens, au bon moment. Un
canal peut avoir la forme juste et rendre du faux — c'est exactement ce qui s'était produit avant
`33292bc4`, où tout restait « du bon ordre de grandeur ».

---

## 2. Le natif, relu (décompilé = vérité)

`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` :

```
eff = amount
if EntityExtensions.IsActor(caster):
    eff = (int) Fix64(bonus + amount) * Fix64(multiplier)     # stats du caster
currentHealth = UnitExtensions.GetStat(target, 5 /*Health*/, 0, 0)
if scope == 1:   eff = Min(eff, DamagePrediction.GetGroupUnitHealLimit(this, target, currentHealth))
if UnitExtensions.IsBoss(target):
                 eff = Min(eff, GetStat(target, 5, 3, 0) - currentHealth)
totalHeal = FillUpStatComponent.MaxFillUp(HealthComponent(target), eff)
return CONCAT44(totalHeal, currentHealth)          # lo = currentHealth, hi = totalHeal
```

`IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` :

```
MaxFillUp(amount) = Min(amount, get_CurrentMaximumValue() - <this+0x18 : Remaining>)
```

**C'est ce `Min` qui rend le canal falsifiable**, et c'est tout le montage : il crée **deux
régimes** dont l'un ou l'autre, pris seul, ne discrimine rien.

| régime | condition | `totalHeal` vaut | ce que l'hypothèse concurrente prédirait |
|---|---|---|---|
| **SATURÉ** | `missing < eff` | `hpMax - hp` | un canal qui republierait le MONTANT rendrait `eff` (≫) |
| **PLATEAU** | `missing > eff` | `eff`, **indépendant de `missing`** | un canal qui republierait `hpMax - hp` varierait avec la blessure |

Un montage qui n'exercerait qu'un seul des deux laisserait passer l'autre erreur. **Il faut les
deux, et c'est pour cela que le probe construit trois batailles au lieu d'une.**

---

## 3. Montage

Fixture `repair_stage` (`_repair_stage.build_stage`, livrée par #298), `advance=0`, board `MC1_67`,
seed 777 : réparateur trait `Mechanic` + ami **MÉCANIQUE BLESSÉ** (`admecRuststalker`), la blessure
posée par `--unit-stat <cible>:RemainingHealth=N`.

Deux pièges, tous deux déjà payés, tous deux évités ici :

* **`--hp-player N` ne convient pas** : il écrit `Health` **et** `RemainingHealth`, l'unité reste
  à 100 %, `IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit` reste FAUX — le levier annulait
  le scénario qu'il devait créer.
* **Aucun `aiturn` avant la mesure.** `aiDryRunAllUnits` immédiat après build → les
  `repair_prediction` sortent ; le même appel **après un tour IA** → **zéro**, les abilities
  DÉRIVÉES (`RepairType` @0x2c et `NormalAttackType` @0x28) disparaissant **ensemble** de
  l'énumération, sans erreur. C'est ce zéro-là qui avait fait écrire à tort que le rail de
  décision était inatteignable (réfuté par #298).

---

## 4. Mesure — `admecManipulus` → 1119 `Repair_GalvanicField`

`python probe_278_repair_prediction_values.py`. Cible `admecRuststalker`, `hpMax = 8032`.

| scénario | `hp` posé | `missing` | `amount` (arg tracé) | `prediction.currentHealth` | `prediction.totalHeal` |
|---|---|---|---|---|---|
| SATURÉ | 8031 | **1** | 5024 | **8031** | **1** |
| PLATEAU A | 2000 | 6032 | 5024 | **2000** | **5024** |
| PLATEAU B | 1000 | 7032 | 5024 | **1000** | **5024** |

* **C1** — `currentHealth == observeBattle.hp` sur les **trois** valeurs, qui sont CHOISIES par le
  montage, pas constatées. 3/3 events à chaque scénario.
* **C2** — régime saturé : `totalHeal == hpMax - hp == 1`, **alors que le montant vaut 5024**.
  C'est `MaxFillUp` recalculé à la main depuis `observeBattle` seul, et l'écart entre les deux
  hypothèses est maximal — on ne tombe pas sur 1 par hasard quand l'autre candidat est 5024.
* **C3** — plateau : `missing` passe de 6032 à 7032, `totalHeal` ne bouge pas (5024) et reste
  strictement inférieur à `missing`. L'hypothèse « le canal republie `hpMax - hp` » tombe ici.
* **C4** — **exécution native**. `applyAction {kind:"ability", abilityType:1119}` fait caster la
  réparation par le moteur du runner ; `observeBattle` rend **hp 1000 → 6024, delta = 5024**,
  soit **exactement** le `totalHeal` prédit. La face EXÉCUTION n'est pas portée côté Python
  (résidu #299) et n'avait pas à l'être : c'est le natif qui exécute dans le runner.

## 5. Généralisation — `admecDominus` → 28 `Repair`

`StaticBattleRules.ActiveAbility$$IsRegularRepair` = **{0x1c = 28, 0x45f = 1119}**, exactement.
Le lot précédent n'exerce que 1119 (spécialisation par le passif `GalvanicField`) : un canal juste
pour un playbook et faux pour l'autre passerait tout ce qui précède. Second porteur, **autre
playbook** (`RepairPlaybook` au lieu de `Repair_GalvanicFieldPlaybook`), **autre montant** :

| scénario | `hp` posé | `missing` | `amount` | `currentHealth` | `totalHeal` |
|---|---|---|---|---|---|
| SATURÉ | 8031 | 1 | 5022 | **8031** | **1** |
| PLATEAU A | 2000 | 6032 | 5022 | **2000** | **5022** |
| PLATEAU B | 1000 | 7032 | 5022 | **1000** | **5022** |

C4 : **hp 1000 → 6022, delta = 5022** = `totalHeal` prédit. Le montant diffère de 2 points entre
les deux porteurs — donc ce n'est pas une constante du montage qu'on retrouverait par construction.

---

## 6. La garde vue ROUGE — mutation adversariale du décodage

Une garde qu'on n'a jamais vue rouge ne garde rien. La mutation ne touche pas au hook (aucune
réinjection possible) : elle **relit les mêmes octets déjà capturés en échangeant `lo` et `hi`** —
c'est-à-dire qu'elle rejoue exactement la faute de décodage que le correctif a supprimée.

`python probe_278_repair_prediction_values.py --mutate` — sortie VERBATIM :

```
== VERDICT (MUTE lo<->hi) ==
  [ROUGE] C1     0/3 events : currentHealth == observeBattle.hp ; ecarts=admecRuststalker: canal=1 observe_hp=8031; ...
  [ROUGE] C2     0/3 events : totalHeal == hpMax-hp ; ecarts=admecRuststalker: canal=8031 attendu(hpMax-hp)=1; ...
  [ROUGE] C3     missing=6032 -> totalHeal=[2000] ; missing=7032 -> totalHeal=[1000]  <- doit etre EGAL et < missing
  [ROUGE] C1b    0/3 events : currentHealth == observeBattle.hp ; ecarts=admecRuststalker: canal=5024 observe_hp=1000; ...
  [ROUGE] C4     hp 1000 -> 6024 (delta=5024) vs totalHeal predit=1000
  attendu sous mutation : TOUT ROUGE -> garde vue ROUGE, OK
```

**Les cinq contrôles tombent.** Le test `test_swapping_lo_and_hi_breaks_every_check` porte la même
mutation dans pytest et échoue si un seul survit.

---

## 7. Garde supplémentaire — la session live porte-t-elle bien le décodeur corrigé ?

Une confrontation de valeurs contre une session restée sur l'ANCIEN hook ne vaut rien, et
`aiTraceStatus` ne le dirait pas (`PredictRepair: ok` des deux côtés). **Le jeu de clés tranche
tout seul** : l'ancien décodeur publiait QUATRE champs (`currentHealth`, `currentArmor`,
`totalHeal`, `totalArmorRepair`, dont deux hors des bornes du struct), le canal corrigé en publie
DEUX. Tous les events mesurés portent exactement `{currentHealth, totalHeal}` —
`test_the_live_session_carries_the_fixed_decoder` verrouille ce point pour les mesures futures.

---

## 8. Ce qui n'est PAS couvert

* **L'étage Fix64 du caster est resté l'IDENTITÉ** sur les deux porteurs mesurés : `amount` tracé
  = montant effectif (5024 et 5022), donc `bonus = 0` et `multiplier = 1`. La branche
  `if IsActor(caster): eff = (int) Fix64(bonus + amount) * Fix64(multiplier)` est **traversée mais
  neutre** — le montage ne prouve rien sur elle. Il faudrait un caster porteur d'un modificateur
  de puissance de soin pour l'exercer.
* **Branche `scope == 1`** (`GetGroupUnitHealLimit`) : jamais empruntée. Les deux réparations
  régulières mesurées passent avec un `scope` qui n'est pas 1.
* **Branche `IsBoss(target)`** (`Min(eff, GetStat(target,5,3,0) - currentHealth)`) : la cible est
  un héros, pas un boss.
* **`PredictArmorRestore` est MORT dans ce build** — `findMethod` rend « method not found », et
  `ArmorRestorePredictionResult` n'existe plus. Constat, pas correctif : c'est un autre canal, et
  un autre sujet. (Sans effet ici : la réparation régulière restaure la SANTÉ, pas l'armure.)
* **La face EXÉCUTION côté PYTHON** reste non portée (résidu #299) : C4 mesure le **natif**, pas
  le port. Ce case ne dit rien du moteur Python de la réparation.
* Une seule cible (`admecRuststalker`) et un seul board (`MC1_67`) : le canal ne dépend d'aucun
  des deux (il lit un composant de la cible), mais ce n'est pas mesuré.

---

## 9. Reproduire

```
cd scripts/python
python probe_278_repair_prediction_values.py                        # 1119, 4 controles
python probe_278_repair_prediction_values.py --repairer admecDominus # 28
python probe_278_repair_prediction_values.py --mutate               # garde ROUGE
python -m pytest tests/engine/runner/test_repair_prediction_values_live.py -q
```

Le probe MESURE et imprime, les tests GARDENT ; les deux partagent le même code de lecture de
trace et les mêmes prédicats (`probe_278_repair_prediction_values.check_*`) — il n'y a pas deux
définitions du critère.
