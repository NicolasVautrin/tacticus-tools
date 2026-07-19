# Case #34 — angle mort oracle heal/buff (`non-attack-oracle`)

**Statut : RE (decode + plan) FAIT. Implémentation NON commencée — split hook (reinject-gated) + offline (no-reinject).**

## Symptôme (agreement stage `non-attack-oracle`, `engine_agreement_stages.py:314`)

Pour une ability qui n'émet **aucun `ProbableDamageEvent`** (heal / buff / repair), le RPC `aiPlaybookPredict`
(`playbook-predict.ts`) ne décode que les `ProbableDamageEvent` → l'oracle offline reçoit `no-native-events`
→ il **ne peut pas confronter** le choix natif → stage `non-attack-oracle` (miss inclassable, PAS un vrai
désaccord). Le gate `is_noncomp` (stages.py:310) passe AVANT : ces abilities sont donc **Comparable** (scorées
par le générique `CalculateUtilityFromPredictions`, pas un playbook bespoke).

### Les 5 abilities concernées (agrégat 909 + 31337)

| id | nom | famille probable |
|----|-----|------------------|
| 1113 | Stormcaller | effect/buff (ProbableEffectEvent) |
| 1121 | ItItches | effect/buff |
| 1151 | TheQuickening | heal + effect |
| 1163 | BlackRage | effect/buff |
| 1202 | VigilanceEternal | effect/buff (⚠ AUSSI la triggered-ability AdjPref de #36 — ici c'est le CAST actif du buff qui émet un EffectEvent) |

## RE — le scoreur natif (déjà mappé, cf. architecture.md §2.3 / journal.md)

`ComparablePlaybook.CalculateActionUtility @181406ee0` -> `CalculateUtilityFromPredictions @181407890` somme,
par **famille de prédiction** (chacune un générateur `Make*Predictions` + un `CalculateUtilityFrom*Event`) :

- **Dégât** : `Sigma proba x Weight[Damage=34].Eval(UtilityAttackCase.ForDamagePrediction(ev))`  (DEJA porté = `damage_composite`)
- **Heal**  : `Sigma Probability x Weight[Heal=44].Eval(ForHealPrediction(target, healPred))`  (`CalculateUtilityFromHealEvent @1814aac80`)
- **Effet** : `Sigma proba x Weight[AddedTileEffects=45].Eval(ForEffect(effectId))`  (op 0x2d)
- **Repair**: `Sigma Weight[Repair=46].Eval(ForRepairPrediction(...))`  (op 0x2e)

`CalculateUtilityFromHealEvent @1814aac80` (décompilé) : `local_10 = event@0x10` (Probability Fix64) ;
`weight = cfg+0x40 index 0x2c(=44)` ; `case = UtilityAttackCase.ForHealPrediction(param3, param4, target=ev@0x0,
healPred=ev@0x8, abilityOrEffect=op_Implicit(0x12))` ; **résultat = `Probability x Weight[44].Eval(case)`**.

## RE — layout des 3 struct d'événement (décompile des ctors, gqfc5mff6c)

Tous : `@0x0` = target (ptr IEntity -> id via `idByPtr`), `@0x10` = **Probability (Fix64 Q32.32)**. **Diffèrent à `@0x8`** :

| event | ctor VA | sizeof | @0x8 |
|-------|---------|--------|------|
| `ProbableDamageEvent` | `@181135500` | **0xd8** | AttackHitPrediction 0xc0 inline (hp/armor/shield, willKill@0x2c, healthDmg@0x68/6c, totalDmg@0x98/9c, appliedHits@0xc4) ; 2 probs @0xc8/@0xd0 |
| `ProbableHealEvent`   | `@1811359a0` | **0x18** | **HealPrediction ptr** (magnitude du soin) |
| `ProbableEffectEvent` | `@181135820` | **0x18** | **EffectType (int, 4 o)** |

- Le "probability" est calculé pareil dans les 3 ctors : `FromInt(1)` si le nom d'un champ est vide, sinon un
  Fix64 dérivé (division/scale via `FUN_1802a87b0`). Pour heal/effect il vaut typiquement **1** (proba certaine).
- **HealPrediction magnitude** (offset dans la struct pointée @0x8) : RESTE A DECOMPILER (via `DamagePrediction.PredictHeal`
  = `MaxFillUp(target, healAmount)` cappé `maxHP - currentHP`, cf. journal.md:458). Nécessaire pour la sélection
  de cible heal (effective-heal = missing HP départage les cibles, cf. journal.md:459-466).

## Générateurs natifs (résolus par NOM par le hook — pas d'offset vtable)

`ComparablePlaybook` expose les 3 siblings de `MakeDamagePredictions` (slot +0x358) :
- `MakeHealPredictions @18140a970`
- `MakeEffectPredictions @18140a930`
- `MakeRepairPredictions @18140a9b0`

Plus des overrides bespoke (HealPlaybook @181184a70, SpiritLeech @18115d7a0/@18115d690, TwistedScience_Heal
@18116fc60, etc.). Le hook `makeDamagePredictions` résout DEJA `MakeDamagePredictions` par
`findMethodByParamCount(pbCls, "MakeDamagePredictions", 4|3)` -> la même mécanique marche pour les 3 autres noms.

## Plan d'implémentation (2 morceaux)

### A. Hook `frida/hooks/features/ai-step/playbook-predict.ts` — REINJECT-GATED (rebuild + reinject SOLO)

1. `makeHealPredictions` / `makeEffectPredictions` / `makeRepairPredictions` = copies de `makeDamagePredictions`
   (resolve par nom, mêmes args caster/pos/target[/AbilityState]).
2. `readHealEvent(ev)` : `{targetId: idByPtr(ev@0x0), healPred: ev@0x8 -> magnitude (offset TODO), probability: fx(0x10)}`.
   `readEffectEvent(ev)` : `{targetId: idByPtr(ev@0x0), effectType: ev.add(0x8).readS32(), probability: fx(0x10)}`.
   STRIDE = **0x18** (vs 0xd8 damage). Réutiliser `decodeDamageEvents` généralisé (liste/array/yield-machine identiques,
   seul le reader + le stride changent).
3. RPC `aiPlaybookPredict` (rpc-predict.ts) : renvoyer `{damage:[...], heal:[...], effect:[...], repair:[...]}`
   (aujourd'hui liste damage à plat — garder rétro-compat).

### B. Offline `engine/` — NO REINJECT (portable dès que le hook feed des events)

1. Porter les scoreurs `CalculateUtilityFromHealEvent` / `...EffectEvent` / `...RepairEvent` : `U = proba x Weight_k.Eval(For*Prediction(...))`.
   - Nécessite porter les **leaves Weight[Heal=44] / Weight[AddedTileEffects=45] / Weight[Repair=46]** (mirror de
     `damage_composite` = Weight[Damage=34]). RESTE A RE (décompiler les composites 44/45/46).
2. Brancher dans l'oracle `make_predictions` (prediction.py) : sommer damage + heal + effect + repair.
3. Valider : les 5 paires `non-attack-oracle` doivent devenir confrontables (le stage disparaît de l'agrégat 909+31337).

## Ordre / gating

- La partie **A (hook)** exige rebuild `hooks.js` + reinject SOLO -> NE PAS lancer tant qu'un agent tourne
  (règle ⛔ CLAUDE.md ; même si l'agent est offline-only, l'inject casse la session live). Rewarmup après.
- La partie **B (offline)** peut être portée et testée EN LOCAL une fois les events feedés ; sans le hook A elle
  reste dormante (aucun heal/effect event en entrée), comme les feuilles Tile "portées mais dormantes".

## VAs

- `ProbableDamageEvent..ctor @181135500` (0xd8) · `ProbableHealEvent..ctor @1811359a0` (0x18) · `ProbableEffectEvent..ctor @181135820` (0x18)
- `CalculateUtilityFromPredictions @181407890` · `CalculateUtilityFromHealEvent @1814aac80` · `CalculateActionUtility @181406ee0`
- `ComparablePlaybook.MakeHealPredictions @18140a970` · `MakeEffectPredictions @18140a930` · `MakeRepairPredictions @18140a9b0`
- Weights : Damage=34, Heal=44 (op 0x2c), AddedTileEffects=45 (0x2d), Repair=46 (0x2e)
