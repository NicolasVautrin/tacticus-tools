# Case #34 — angle mort oracle heal/buff (`non-attack-oracle`)

**Statut : partie A (hook decode) FAITE + VALIDÉE LIVE (2026-07-20). ⚠ REFRAME MAJEUR (voir §MAJ) :
les 5 abilities bloquées sont des playbooks NON-COMPARABLE natifs — leur déblocage = portage
NC (nouvelle tâche), PAS le decode heal/effect (qui reste utile pour les familles Comparable).**

## MAJ 2026-07-20 — REFRAME : les 5 abilities sont NC NATIVES (le decode ne les débloque pas)

**Vérité native (symbols ghidra, gqfc5mff6c)** — les 5 playbooks exposent `EvaluateNonComparable`
(+ `GetUseProbability`), et **AUCUN `Make*Predictions`** :

| id | playbook | EvaluateNonComparable |
|----|----------|----------------------|
| 1113 | StormcallerPlaybook (+ GetTargetUtility @1811613a0) | @181160ff0 |
| 1121 | ItItchesPlaybook (+ GetAffectedUnitsSelector) | @181146c50 |
| 1151 | TheQuickeningPlaybook (+ GetNumAttackTargetsInPosition) | @18116afb0 |
| 1163 | BlackRagePlaybook | @1811211f0 |
| 1202 | VigilanceEternalPlaybook | @18117fae0 |

(idem `RevitalizingMalignancyPlaybook` @181156790 — le heal actif 1037 de Rotbone est NC aussi.)

**L'erreur d'inférence originelle** : « le gate `is_noncomp` passe avant, donc ces abilities sont
Comparable » — c'était lire NOTRE registre offline (qui ignore ces 5 ids) comme si c'était la
nature native. Le stage `non-attack-oracle` était donc un DOUBLE mal-classement : (1) offline,
les 5 ids manquent au registre NC ; (2) l'oracle damage-only rendait la paire inconfrontable.
Mesuré live (probe34_decode) : `aiPlaybookPredict` sur 1113/1163 → damage ET heal ET effect
tous `list null` (les 3 `Make*` n'existent pas sur ces classes) — cohérent NC.

**Conséquence** : débloquer ces 5 paires = **porter leurs `EvaluateNonComparable`** (comme
1179/1180 #15 et 1118 #18) + les enregistrer au registre NC offline (le stage devient `nc-pair`
puis `hit` une fois l'évaluateur porté). Tâche dédiée créée. Le décodeur heal/effect (partie A
ci-dessous) reste ACQUIS et nécessaire pour les familles **Comparable** : `HealPlaybook`
(ability 18 « Heal » du trait Healer — validé live), SpiritLeech/DakkaDakkaDakka/TwistedScience
(heal), SpiritLeech (effect), et le modèle repair du lead 2.

## Partie A (hook) — FAITE + VALIDÉE LIVE (2026-07-20, session 42)

- `playbook-predict.ts` : `makeDamagePredictions(..., methodName?)` (résolution par nom, mêmes
  args) + `decodeEventsGeneric(reader, stride)` (List`1 / array / yield-machine partagés) +
  `readHealEvent` / `readEffectEvent` (stride 0x18) ; `rpc-predict.ts` : `aiPlaybookPredict`
  renvoie en plus `healEvents`/`effectEvents` (+ counts/retClass/erreur par famille,
  rétro-compat : `events` = damage inchangé).
- **Correction de layout vs le plan initial** : `ProbableHealEvent@0x8` n'est PAS un ptr —
  c'est le struct **HealPrediction INLINE 8 o** = le retour PAR VALEUR de
  `DamagePrediction.PredictHeal @181037180` (`CONCAT44(amount, currentHealth)`) →
  `targetHpBefore@+0x08`, `healAmount@+0x0c` (amount = MaxFillUp capé maxHP−curHP,
  boss-capé `GetStat(5,3)−cur`, group-capé `GetGroupUnitHealLimit` si flag).
- **Validation live** (31337 + drive 6) :
  - garde régression : ab 69 (Loki_NormalAttackPlaybook) → damage décode inchangé, et les
    siblings rendent `ProbableHealEvent[]`/`ProbableEffectEvent[]` VIDES (base @18140a970/
    @18140a930 = enumerable vide) — familles proprement séparées ;
  - heal réel : u93 deathRotbone **ab 18 « Heal »** (granted, trait Healer) → `HealPlaybook`,
    `List`1`, 1 event/cible : `targetHpBefore` == HP live EXACT sur 5 cibles distinctives
    (9035/9537/8032/12047/8533), `probability` = 1.0 exact, `healAmount` = 0 à HP plein
    (MaxFillUp → 0, loi décompilée). Repro : `probe34_decode.py` / `probe34c_heal18.py`
    (scratchpad session).

## Partie B restante (offline, no-reinject)

1. Scoreur heal : `CalculateUtilityFromHealEvent @1814aac80` = `Probability ×
   Weight[Heal=44].Eval(ForHealPrediction)` — RE des leaves Weight[44] + port (mirror
   `damage_composite`). L'effect (Weight[45] AddedTileEffects) est DÉJÀ porté
   (`ADDED_EFFECT_UTILITY` + `calculate_utility_from_effect_event`).
2. Brancher heal/effect dans la confrontation (`engine_agreement_stages._confront_prediction`
   lit `healEvents`/`effectEvents` pour les paires Comparable heal — ex. ability 18).
3. Repair (lead 2) : `MakeRepairPredictions @18140a9b0` rend un Dictionary (pas d'event) —
   décodage v2 séparé.

## Symptôme (agreement stage `non-attack-oracle`, `engine_agreement_stages.py:314`)

Pour une ability qui n'émet **aucun `ProbableDamageEvent`** (heal / buff / repair), le RPC `aiPlaybookPredict`
(`playbook-predict.ts`) ne décode que les `ProbableDamageEvent` → l'oracle offline reçoit `no-native-events`
→ il **ne peut pas confronter** le choix natif → stage `non-attack-oracle` (miss inclassable, PAS un vrai
désaccord). Le gate `is_noncomp` (stages.py:310) passe AVANT : ces abilities sont donc **Comparable** (scorées
par le générique `CalculateUtilityFromPredictions`, pas un playbook bespoke).

### Les 5 abilities concernées (agrégat 909 + 31337)

⚠ **PÉRIMÉ (cf. §MAJ 2026-07-20)** : la colonne « famille probable » était une CONJECTURE fausse —
les 5 sont des playbooks NC natifs qui n'émettent AUCUN Probable*Event.

| id | nom | famille probable (PÉRIMÉ) |
|----|-----|------------------|
| 1113 | Stormcaller | ~~effect/buff (ProbableEffectEvent)~~ → NC |
| 1121 | ItItches | ~~effect/buff~~ → NC |
| 1151 | TheQuickening | ~~heal + effect~~ → NC |
| 1163 | BlackRage | ~~effect/buff~~ → NC |
| 1202 | VigilanceEternal | ~~effect/buff~~ → NC (⚠ AUSSI la triggered-ability AdjPref de #36) |

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
| `ProbableHealEvent`   | `@1811359a0` | **0x18** | **HealPrediction INLINE 8 o** = `{currentHealth@+0x08, healAmount@+0x0c}` (retour PAR VALEUR de `PredictHeal @181037180` — pas un ptr, corrigé §MAJ) |
| `ProbableEffectEvent` | `@181135820` | **0x18** | **EffectType (int, 4 o)** |

- Le "probability" est calculé pareil dans les 3 ctors : `FromInt(1)` si le nom d'un champ est vide, sinon un
  Fix64 dérivé (division/scale via `FUN_1802a87b0`). Pour heal/effect il vaut typiquement **1** (proba certaine).
- **HealPrediction magnitude** : ✅ DÉCOMPILÉ (§MAJ) — struct 8 o par valeur `{currentHealth,
  healAmount}` = retour de `PredictHeal @181037180` (`amount` = MaxFillUp capé `maxHP−cur`,
  boss-capé, group-capé si flag ; + boucle amont de bonus heal sommés à l'amount d'entrée).

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
