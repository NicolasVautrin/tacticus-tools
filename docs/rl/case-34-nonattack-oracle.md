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
  (règle ⛔ CLAUDE.md ; même si l'agent est offline-only, l'inject casse la session live). Reamorce après.
- La partie **B (offline)** peut être portée et testée EN LOCAL une fois les events feedés ; sans le hook A elle
  reste dormante (aucun heal/effect event en entrée), comme les feuilles Tile "portées mais dormantes".

## VAs

- `ProbableDamageEvent..ctor @181135500` (0xd8) · `ProbableHealEvent..ctor @1811359a0` (0x18) · `ProbableEffectEvent..ctor @181135820` (0x18)
- `CalculateUtilityFromPredictions @181407890` · `CalculateUtilityFromHealEvent @1814aac80` · `CalculateActionUtility @181406ee0`
- `ComparablePlaybook.MakeHealPredictions @18140a970` · `MakeEffectPredictions @18140a930` · `MakeRepairPredictions @18140a9b0`
- Weights : Damage=34, Heal=44 (op 0x2c), AddedTileEffects=45 (0x2d), Repair=46 (0x2e)

## MAJ #45 (2026-07-20) — décodage v2 repair + composites 44/45/46 RÉSOLUS + mesure s15

**Le RE demandé ci-dessus est fait ; la mesure 777 s15 a localisé la vraie divergence.**

- **Composites 44/45/46 résolus LIVE** (`dumpComposedUtility`, UtilitiesDatabase champ +0x58) :
  `Repair(46) = [47 RepairedAmount, 2 TriggeredAbilities, 4 TriggeredAbilitiesNonOwner]` ;
  `Damage(34) = [40,35,36,38,43,39,37,41, 2,4,3, 59,42]` ; `Tile(7)` et `UnitMovement(6)`
  inchangés vs le port. Heal(44)/AddedTileEffects(45) ne sont PAS des composites (feuilles
  directes, déjà portées : `HealUtility` / `AddedEffectUtility`). Chaque feuille d'un composite
  se dispatch PAR TYPE DE CASE : `Evaluate{Attack,Movement,Repair}InSteps` — pour un case repair,
  les feuilles 2/4 exécutent leur `EvaluateRepairInSteps` (NonOwner d__2 @1810f2ea0, Dispose
  @181102cd0) — **NON PORTÉES** (on n'applique que la feuille 47).
- **Scorer 4-familles** : `CalculateUtilityFromPredictions @181407890` = Σ damage(+0x358, ×prob)
  + heal(+0x368, `@1814aac80` = prob × GetUtility(44).Eval(`ForHealPrediction @181105420`),
  `AbilityOrEffect(18)`) + effect(+0x378, GetUtility(45) × prob) + repair(+0x388,
  GetUtility(46).Eval(`ForRepairPrediction @1811055f0`), `AbilityOrEffect(28)`, **sans** prob).
- **`PredictRepair @181038280`** : `RepairPrediction = {curHealth, curArmor, hpFill, armorFill}`
  (4 ints, 16 o) ; fills = `MaxFillUp(amount)` PAR stat (montant non partagé) ; **bonus ACTEUR
  `(amount + add) × mult`** via query d'effets (slot itf, analogue au bonus-soin) — NON porté ;
  group-limit + boss-cap déjà mirrorés. `RepairPlaybook.MakeRepairPredictions @181187830` =
  `{target: PredictRepair(...)}` (base @18140a9b0 = dict VIDE).
- **Hook décodage v2** : `decodeRepairDict` (playbook-predict.ts — walk du Dictionary, entry
  32 o {hash,next,key ptr,value 16 o}) + champ `repairs` d'`aiPlaybookPredict` (rpc-predict.ts).
  VALIDÉ LIVE (777 s15 : `{targetId:83, hpBefore:6319, hpFill:2716, armorFill:0}`).
- **Harnais** : `_confront_nonattack` (magnitude offline vs fills natifs, familles heal/repair)
  + `_counterfactual_nonattack` (fills natifs × HealUtility/RepairedAmountUtility) dans
  engine_agreement_stages.py ; `non-attack-oracle` ne reste que pour des hooks sans décodeur.
- **MESURE 777 s15 (u83 admecDominus, self-repair 28)** : fills natifs == offline (2716/armor 0)
  → la MAGNITUDE est fidèle ; notre utilité 30.06 (RepairedAmountUtility) bat encore l'attaque
  (~22.4) alors que le natif préfère l'attaque → **la divergence = les feuilles 2/4 du composite
  46 en mode repair** (attendu : contribution négative — famille « AdjacentUnitPreference » déjà
  suspectée par le harnais côté move). NB mesure : les états DIVERGENT entre runners au même pas
  (RNG dégâts per-runner) — le « u=50.1 » historique vs 30.06 = mêmes formules, hp différents ;
  toujours re-mesurer sur SON runner.
- **RESTE** : (a) décompiler + porter les 2 `EvaluateRepairInSteps` (feuilles 2/4) → s15 doit
  flipper ; (b) vérifier la couverture attack de `damage_composite` vs les feuilles 2/4/3 de
  Damage(34) ; (c) ProbableHealEvent offline + branchement heal au total par-paire du moteur ;
  (d) bonus acteur PredictRepair/PredictHeal.

## MAJ #45bis (2026-07-20) — RÉSOLUTION s15 repair-vs-attack : gate STUN, pas l'utilité

La piste « feuilles 2/4 » de la MAJ précédente est CLOSE : mesure directe au scoreur natif.

- **RPC `pairUtility`** (rpc-predict.ts) : invoque `ComparablePlaybook.CalculateUtilityFromPredictions
  @181407890` — signature invocable `(unit, UnitPosition, target, Nullable<AbilityState>*)` + MethodInfo,
  retour Fix64 boxé (+0x10, Q32.32) = la valeur EXACTE de la paire (Σ 4 familles, prob/modifs inclus).
  Mêmes conventions qu'`aiPlaybookPredict` (tuile candidate col/row, AbilityState capteur).
  ⚠ `ncEvaluate` (wrapper `Evaluate` slot 7) **AV @0x46 sur les playbooks COMPARABLES** invoqués hors
  du tour de décision natif (OK sur les NC) → pour une utilité comparable, passer par `pairUtility`.
- **MESURE DÉCISIVE (777 s15, u83 admecDominus hp 6319/9035 @(3,6))** :
  `pairUtility(28→self) = 30.0575` == notre 30.058 → **le scoreur repair offline est exact 1:1**
  (leaf 47 seul ; feuilles 2/4 ≈ 0 sur ce roster). `pairUtility(69→87) = 2.8836` (nous : cf 22.376).
  Le natif classe donc repair ≫ attack au scoreur… et joue l'attaque → le self-repair est éliminé
  AVANT le scoring.
- **LE GATE = STUN.** u83 est stunné au s12 par u87 (custoVexilusPraetor, ability 1183) : effets
  `Stunned 1162` + `Stunned_CantUseAbility 1165` + `Stunned_MovementOverride 1166` + `_DamageModifier
  1167`. 1165 bloque les abilities ACTIVE/GRANTED (Repair 28 = granted, RadBombardment 1116), PAS
  l'attaque normale (wiki §Stunned, validé seed 97000) → le natif n'avait QUE 69→87 (2.88).
  Pièges mesure : le capteur `usable:true` (entrée ActiveAbility) IGNORE les effets ; `abilityTargets`
  liste QUAND MÊME u83 comme cible valide de 28 (le targeting ne porte pas ce gate).
- **MIRROR** : `engine/battle_query.can_use_ability` (= `AttackQuery.CanUseAbility @181054ec0` ;
  maillon slot itf 0x13 = effet famille `CantUseAbilityEffect` : 26 `Taunted_CantUseAbility`,
  1165 `Stunned_CantUseAbility` ; match offline par suffixe de nom `_CantUseAbility`) + filtre au
  point de couture unique `ctx.me["abilities"]` (context.build) — les actives/granted bloquées
  n'atteignent jamais les générateurs ; kind `normal` passe. Côté move : rien à faire (nos candidats
  = movable set NATIF, qui folds déjà MovementOverride).
- **VALIDATION** : match sur le pas exact (runner arrêté à s15 par `probe_45_repair_gate.py` —
  walk-until-condition réutilisable) ; batch frais 777/909/31337 ×20 : **ability 34/35 (97 %)**
  — l'unique miss est le #49 Gauntlets (31337 s14, connu) — **prédiction 26/26 (100 %)**, move 46/51.
- **RE annexe (pour le port futur des feuilles 2/4, roadmap AdMech #20)** :
  `ComposedUtility.EvaluateRepairInSteps` d__7 @181102db0 = (Σ enfants) × (`CalculateAttackModifier
  @1810cd930` = Π des Nullable<Fix64> des enfants ; seuls overrides : Dislike{Boss,EnvironmentUnits,
  Objects}Utility → =1 pour Repair(46)=[47,2,4]). Leaf 47 natif (d__2 @1810e45b0) =
  `hpFill/(maxHp+1)×W_HP + armorFill/(maxArmor+1)×W_ARMOR`, ×2 si `IsBoss(ACTEUR)` (case+0x10),
  boss-cap santé via config si CIBLE boss. Feuilles 2/4 = `CalculateRepairUtilityInSteps(case, x)`
  des playbooks triggered (protocole : steps yield 0, DERNIER yield = valeur ; base Internal yield 0
  @18134f520) — owner d__1 @1811022c0 : LoadPlaybook par ability du porteur ; NonOwner d__2 @181102860
  + `IterateAbilities` d__3 @181103860 (skip owner, `LoadPlaybookNonOwner(unit.Type)`, gate
  `flag || IsFriend(owner, unit)`). Concrets : OmnissiahsBlessing @181197aa0 (+config si la CIBLE
  réparée porte l'ability ; valeur alternative si 1293), RepairEnthusiast @181197930 (+config si
  actor≠target et cible sans 1514), VoltagheistField, Repair_GalvanicField.
  Case `UtilityAttackCase` : +0x10=ACTEUR, +0x18=UnitPosition, +0x20=CIBLE,
  +0xfc=Nullable<RepairPrediction> (`ForRepairPrediction @1811055f0` ; `AbilityOrEffect(28)` hardcodé
  par le scorer pour la famille repair, (45)/ForEffect pour la famille effect ×prob).
- **RESTE (#45)** : (b') **échelle famille damage** : notre cf 22.376 (damage_composite + Tile7) vs
  `pairUtility` natif 2.8836 pour 69→87 — u87 est SHIELDED (hp 13368 > max 11044), suspect n°1 =
  traitement du shield dans la famille damage ; levier propre = brancher `pairUtility` comme ORACLE
  d'un étage UTILITÉ du harnais (confrontation par-paire systématique, comme `aiPlaybookPredict`
  l'est pour la prédiction) ; (c) heal formule (u91 biophagus 1167 self-heal : off 5066 vs natif
  3614, feed=false) ; (d) bonus acteur PredictRepair/PredictHeal (inchangés).

## MAJ #45ter (2026-07-20) — ÉTAGE UTILITÉ branché + s15 damage RÉSOLU (MaxHealth part-2)

**(b') est branché et le « gap 22.38 vs 2.88 » est mort : c'était le terme Tile(7) qui polluait
la comparaison** (le scoreur natif ne le contient pas — il vit dans le sweep de position).

- **ÉTAGE UTILITÉ** (`engine_agreement_stages.py`) : confrontation par-paire SYSTÉMATIQUE (hits
  inclus) `_formula_pair_utility` (mirror 4-familles de `CalculateUtilityFromPredictions
  @181407890`, nourri des prédictions NATIVES = formule isolée, SANS Tile(7)) vs RPC `pairUtility`
  (même tuile). Les contrefactuels délèguent au MÊME mirror (source unique, `_counterfactual_
  nonattack` fusionné). Sous-produit : classification `native-gate` sur un miss quand le scoreur
  natif préfère LUI-MÊME la paire du moteur (signature s15 stun) — au lieu de «utility-logic».
- **BATCH 777/909/31337 ×20 : 26 confrontations, 24 match (92 %), 2 mismatches famille damage**
  (offline SOUS-estime) : 777 s15 u83 69→87 (off 2.3755 / nat 2.8836) et 31337 s18 u89
  spaceStormcaller 69→u81 bloodMephiston (off 164.2269 / nat 182.0807).
- **s15 RÉSOLU EXACT — MaxHealth = StatPart 2, pas le champ struct.** Décompilé @1810e2280 :
  `combinedMax = GetStat(target, Health=5, **StatPart=2**, null) + 1 + GetShield+1` — l'agrégat
  base+modifications (clamp cape). `observeBattle.hpMax` lit MaximumValue@0x14 = la BASE. Vécu :
  u87 custoVexilusPraetor base 11044, **bump TwistedScience +2992** (u91 caste 1167 sur 87 au
  pas 1 ; `statModSources(u87, health) = {total: 2992, source: effet 145}`) → max effectif 14036
  → 328/14038×80 + (1−13326/14038)×20 = **2.8836 exact**. FIX (4 étages) : capteur
  `combatSnapshot.healthMax` = GetStat(e,5,part=2) (rpc-snapshot.ts) → `hpmax_eff_by_id`
  (build_predictor + refresh_shields par-pas, scene.py) → overlay `hpmax_by_id` (context.build).
  Hooks reinjectés (session 57) ; **VALIDÉ live** : re-batch 777/909/31337 → étage UTILITÉ
  **25/26 (96 %)**, le mismatch s15 a DISPARU (seul restant : s18 splash Psyker, cf. MAJ
  #45quater) ; prédiction 26/26 (dont heal 1167 → match 3614, port heal_amount_weapon
  validé), ability 34/35, move 46/51 — aucune régression de l'overlay hpmax_eff.
- **s18 OUVERT : +17.854 ADDITIF** (aucun mod health sur Mephiston — statModSources vide → pas
  un problème de CM ; kill garanti 100 + DamageDealt 64.23 corrects). Feuille additive à NOMMER
  au breakdown natif par-feuille (**L3 utility_score, exige SOLO** — après le validator).
- **RE composite Damage(34) = [40,35,36,38,43,39,37,41,2,4,3,59,42]** (13 feuilles, on porte
  35/36/37) : **42 AttackTargetWithEffect** @1810e0f00 = Σ effets ACTIFS de la CIBLE →
  +poids BC keyé par le NOM du type d'effet (`Enum.ToString`, catégorie `AttackTargetWithEffect` ;
  ce build : seul `ArmourOfShriekingSouls: 20`) ; **59 OptimizedGait_AdjacentFriends** @1810f73c0 =
  si ACTEUR mécanique, +poids par unité ADJACENTE à la tuile candidate portant la triggered 0x4b5
  =1205 (poids BC = 0 ce build → inerte) ; **2/4 TriggeredAbilities(NonOwner)** mode attack
  (@1810f64b0 / @1810f7ea0) = protocole triggered standard (owner : LoadPlaybook par ability du
  porteur, vslot 3 `CalculateAttackUtilityInSteps` ; NonOwner : IterateAbilities + vslot 1) ;
  `OptimizedGaitPlaybook` attack @18118a050 **yield 0**. Modificateur Π : SEULS overrides =
  `Dislike{Boss @1810cf5d0, EnvironmentUnits @1810cf720, Objects @1810cf870}` (=1 sur unité
  normale). ~60 playbooks triggered ont un corps attack non-trivial (liste symbols
  `CalculateAttackUtilityInStepsInternal`) — porter à la demande (agreement-driven).
- **(c) heal Heal_TwistedScience — RÉSOLU + PORTÉ** : la magnitude native 3614 ==
  **la stat Damage du caster** (BC genesBiophagus `Damage: 3614`). Décompilé relu :
  `HealAmount @180e345b0` = arbre DSL `Multiply(StatAmount(this.weapon@0x160),
  Max(WeaponHighestHits(weapon), 1))` ; `TwistedScience_HealPlaybook.MakeHealPredictions
  @18116fc60` = `GenerateHealPredictions(target@ability+0x178, HealAmount)`. Le bump max-HP
  est un canal SÉPARÉ : `ExecuteBehaviour @181217ad0` = AddDynamicStatModifierEffect(stat 5,
  ConfigVar(TwistedScience=1278, `hp`)) — le +2992 vu au statModSources. PORT :
  `engine/predict.heal_amount_weapon(attack_stat)` (stat Damage résolue = `ctx.attack`) +
  fallback branché aux DEUX call-sites (générateur heal action_generators + confrontation
  stages) quand `hpToHeal` absent ; saturation missing = dernier filet (Scene absente).

## MAJ #45quater (2026-07-20) — s18 NOMMÉ : splash Psyker (leaf 2 → PsykerPlaybook)

**Le +17.854 de 31337 s18 est NOMMÉ par le breakdown natif par-feuille** (hooks L3 étendus
aux SM `EvaluateAttackInSteps(Internal)` des feuilles Damage(34), ai-trace/utilities.ts,
events `mode:"attack"` avec acteur/cible projetés du `UtilityAttackCase` +0x10/+0x20) :
`TriggeredAbilitiesUtility#0 score=17.85381752299145` — la feuille 2 (triggered de l'ACTEUR).

- **Chaîne** : u89 spaceStormcaller (Njal) porte les triggered `1194 LordOfTempests, 1013
  PsykerExtraAttack, 1142 TerminatorArmour` (capteur unitAbilityStates). La feuille 2 charge
  leurs playbooks ; le contributeur = **`PsykerPlaybook.CalculateAttackUtilityInStepsInternal
  d__2 @18118a0d0`** (le SPLASH PSYCHIQUE, trait Psyker) :
  1. Gates : `IsRegularAttack(case)` ; arme du case **ranged** (`IsMelee` → 0) ; profil
     **Psychic** (`profile+0x10 == 0xd=13`) ; non supprimé (`IsPsykerAttackSuppressed
     @181224610` = IsEffectTarget(CASTER, 1191 HuntersBeyondDeathPsykerSuppression) ||
     IsEffectTarget(CIBLE, 1533 WatchedOver_PsykerSuppression)).
  2. `PossibleTargets @181224690` = `Damageable(Enemies(caster, AdjacentUnits(CIBLE, 1, 3)))`
     — les ennemis damageables ADJACENTS À LA CIBLE (ring 1) ; vide → 0.
  3. `GetAttackDamage @181224550` = `PercentageOf(StatAmount(weapon@0x148),
     Direct(GetNumberConstant(config, 0xf)))` — stat Damage du caster × constante config #15
     (le % de splash ; à localiser dans le gameconfig au port — PsykerExtraAttack n'est pas
     une entrée `ability()` directe).
  4. Pour chaque target U : prédiction du MONTANT brut vs U (query slot 0x23, profil 13,
     AbilityOrEffect(1013)) → `ProbableDamageEvent` → `TriggeredAbilityPlaybook.
     CalculateUtilityFromDamageEvent` (composite Damage par event) ; **u = Σ / Count(targets)
     (MOYENNE, pas somme)** — d'où le 17.85 non-rond, position-dépendant (2 cases sur 6).
- **Port (à faire, #45-s18)** : registre `TRIGGERED_ATTACK_PLAYBOOKS = {1013: psyker}` +
  fonction leaf-2 attack appelée PAR EVENT depuis les deux scoreurs de paire
  (`calculate_action_utility` + `_formula_pair_utility` stages — le natif évalue les 13
  feuilles DANS ForDamagePrediction, par DamageEvent). Gates ranged/Psychic via la
  résolution d'arme existante (select_weapon), suppression via effets 1191/1533,
  magnitude = ctx.attack × pct15, prédiction montant-vs-U via le chemin amount existant.

## MAJ #45quinquies (2026-07-20) — s18 PORTÉ + VALIDÉ EXACT : la chaîne slot-0x23 élucidée

**Feuille portée = 17.853817519579994 vs L3 natif 17.85381752299145 (delta 3.4e-9), probe
`probe_45_psyker.py` (rebuild 31337, walk s18, feuille offline vs capture L3 + splash exécuté).**
Fichiers : `engine/playbook/psyker.py` (NOUVEAU — `PsykerPlaybook` + `TRIGGERED_ATTACK_PLAYBOOKS`),
`engine/utilities/tile.py` (`TriggeredAbilitiesUtility.evaluate_attack_in_steps` face attack
@1810f64b0 + `triggered_abilities_attack_utility`), `engine/entities/triggered_ability_type.py`
(`kit_triggered_ability_ids` = passifs + `TRAIT_TRIGGERED_ABILITY_IDS` {Psyker→1013} — 1013 vient
du TRAIT, pas des `passiveAbilities`), câblé dans `playbook/base.calculate_action_utility` +
stages `_formula_pair_utility` (par event, DANS le composite → suit prob × signe).

Précisions RE gagnées au port (chaîne du « montant brut » slot 0x23) :

1. **slot 0x23 = `BattleQuery.GetAttackPrediction @18105e090`** (overload amount+Nullable<profil>) :
   profil résolu via `GetDamageProfile`, **hits forcés 1**, délègue à `DamagePredictionQuery.
   GetAttackPrediction @181091c90` qui boxe l'amount en **Nullable<int> = canal PREDEFINED**
   (même famille que les additional-hits `RandomAmount` : **SANS spread ±20%**) et dispatche la
   requête (struct 0xC8, flag byte=1) au service interne (iface `DAT_183287ef8` slot+4).
2. **Le pipeline predefined applique la COUCHE MODIFIERS COMPLÈTE** (le « montant brut » n'est brut
   qu'à l'entrée) — prouvé au chiffre près (31337 s18, u89 Njal → u81, splash {u77, u79}) :
   base 402 (= 50% × GetStat(Attack, Current)=803, `statModSources` mods={} — AUCUN stat-mod)
   **+ 1200 additif `LordOfTempests_ExtraDamage`** (= `round(extraDmg[50]=222 × 180%) = 400` par
   hex glacé × **3 hexes ring-1 de la TUILE DU CASE (2,4)**, centre exclu — l'effet était DÉJÀ
   porté/validé, `effects/loki/extra_damage.py`) = **1602** (u77 admecMarshall, sans réduction) ;
   u79 custoBladeChampion **−20% `MartialKatah_DmgReduction` → 1282 == le splash EXÉCUTÉ sur u79**
   (hp-diff exact après applyAction). Solve exact : mean(u77(1602)=21.3896, u79(1282)=14.3181)
   = 35.707635/2 == natif à 1e-7.
3. **Le splash est traité `is_normal_attack=True` par la couche modifiers** (LordOfTempests ET
   Katah sont IsNormalAttack-gatés côté port, et les DEUX s'appliquent au splash, prédiction ET
   exécution — mesuré). Le flag byte=1 de la requête @181091c90 en est la trace plausible.
4. **Pièges évités** : `ctx.attack` du snapshot EST le bon StatAmount (Current, sans mods ici) —
   le ×3.6 apparent venait du bonus ADDITIF positionnel, pas d'un stat caché ; premier essai
   `mods=None` donnait 6.21 vs 17.85 (ratio non-entier → refus de fitter, recon de l'effet).
**BATCH FINAL (777/909/31337, post-fix staleness)** : prédiction **26/26**, **UTILITÉ 26/26
(100 % — étage FERMÉ)**, ability **34/35** (seul reste = #49 Gauntlets ring-2), move **47/51**
(+1 : la position u89 s18 « ~1hex » était DOWNSTREAM de l'utilité d'attaque — feuille alignée
⇒ sweep de position aligné ; restent 3 pos-downstream + 1 move-formula AdjacentUnitPreference).

5. **Piège STALENESS (2e bug, trouvé au batch)** : dans le harnais stages le prédicteur est COLD
   (build 1×/runner) → `ctx_by_id[u89].attack` = **2101 au déploiement** (= 803 + **1298 aura
   RitesOfBattle** : Njal adjacent à Calgar au spawn) vs **803 au s18** (éloigné) → feuille 24.37,
   off 188.59 (+6.51). L'aura par-ADJACENCE va et vient → tout nœud `StatAmount(Attack, Current)`
   doit lire le stat DU PAS. Fix : canal `attack_cur_by_id` (capture `combatSnapshot.stats.attack`,
   refresh par-pas dans `refresh_shields`), accessor `Scene.attack_current(uid)` (fallback
   `ctx.attack` pour from_state/vieux hooks), consommé par la feuille. Re-validé 17.8538 exact
   DANS le ctx stages (repro dédié).

### (d) bonus acteur PredictHeal/PredictRepair — RE COMPLET (port = tâche dédiée)

- **`PredictHeal @181037180`** : si caster IsUnit, boucle sur ses EFFETS → virtuel slot 0x1c =
  `BaseEffect.HealBonus @180f12540` (lit le CACHE de bonus `InitializeBonusCacheIfNeeded`
  @+0x250.. : descripteur {condition, nodes} ; condition.Test(entities) → évalue les nœuds
  Amount) → **Σ des `add` AJOUTÉE à l'amount d'entrée** (flat, pas de mult côté heal). Puis
  caps existants (group-limit flag, boss `GetStat(5,3)−cur`) ; amount<0 → `MaxReduce` négé,
  sinon `MaxFillUp(max(0,amount))`. **AUCUN effet du build ne peuple le cache heal-bonus**
  (0 override `Create*HealBonus`) → boucle structurellement présente, TOUJOURS 0 : le port
  actuel (sans la boucle) est fidèle par vacuité sur ce build.
- **`PredictRepair @181038280`** : gate `IsActor(caster)` → service slot-0 =
  `RepairCalculations.CalculateRepairModifierForPrediction @181052890` : énumération ECS de
  **TOUS les EffectComponents du combat** (pas « les effets du caster » — correction RE 2ᵉ passe),
  filtrée par la condition **`OwnerIsTarget`** → seuls les effets **portés par la CIBLE** de la
  réparation contribuent (bonus sur réparations REÇUES, pas faites). Par effet : virtuel slot
  **0x1d** = `BaseEffect.RepairBonus @180f15370` (lit le CACHE `EffectBonus` {condition@+0x00,
  pctNode@+0x08, addNode@+0x10} ; builders `ForAddition @180f406e0` / `ForPercentIncrease
  @180f40850` / `ForPercentDecrease @180f40760` — Decrease enveloppe le pctNode ×−1) → fold
  `RepairModifier.Add @1810535a0` : add **sommés** (op_Addition), mult **multipliés**
  (op_Multiply, `mult = 1 + pct/100` via `GetFloatMultiplierFromPercentage @180ffd270`),
  commutatif, SANS arrondi intermédiaire → **`amount' = trunc((amount + Σadd) × Πmult)`**
  (troncature vers zéro unique, `Fix64.op_Explicit`), puis caps + `MaxFillUp` par stat
  (hp@stat5, armor@stat4) — le modifier s'applique AVANT MaxFillUp.
- **Les 3 implémenteurs du build (RE 2026-07-20, re-expert #9)** :

  | Effet (CreateEffectRepairBonus) | EffectType | Type | Valeur + source | Gate |
  |---|---|---|---|---|
  | `NanoscarabRepairProtocolsEffect @180f5ab60` | 1545 | add | `hpToRepair[lvl]` (ConfigVar 0x24, rarity-scaled multiplier poseur) | OwnerIsTarget |
  | `NetherRealmCasket_LivingMetalBonusEffect @180f5b650` | 1456 | add | `hpToHeal[lvl]` (ConfigVar 0x20, max 1456) | OwnerIsTarget **ET `TriggeringAbilityIs(LivingMetalRepair=0x3f2)`** → INERTE sur le chemin décision (Repair 28 / Galvanic 1119) |
  | `VoltagheistField_RepairReductionEffect @180f76b10` | 1382 | mult | pct = −`healthPct` (constante 50, non scalée) → ×0.5 | OwnerIsTarget |

  Enums : `AbilityVariableType{hpToHeal=0x20, hpToRepair=0x24}`, `AbilityConstantType{healthPct=0x4f}`,
  `TriggeredAbilityType{LivingMetalRepair=0x3f2, NetherRealmCasket=0x5b6}`. Porteurs (gameconfig) :
  Nanoscarab = `necroReanimator`/`necroNpcMoWReanimator` ; Voltagheist = `admecNpc3Electropriest*`/
  `admecSmnElectropriest` ; NetherRealmCasket = NPC Necron (Warden/Destroyer/Spyder + bosses, avec
  trait Living Metal).
- **PORTÉ (2026-07-20)** : `engine/predict.py` `calculate_repair_modifier_for_prediction` (fold
  homonyme, lit dv `effects[].{name,level,source}` de la CIBLE ; multiplier poseur via
  `heal_config(source)`) + `repair_amount` (docstring corrigée : trunc unique). Câblé dans
  `action_generators._repair_candidates` (avant `predict_repair_effective`) et
  `_repair_galvanic_candidates` (sur le FILL seulement — le terme custom @181155520 consomme le
  M brut de `GetOverrideAttackDamageAmount`, hors PredictRepair). Smoke : volt ×0.5 (constante
  lue gameconfig), nano-l3 +11, nether no-op. **Validation live à faire** (scénario proposé par
  le RE : `necroReanimator` répare `admecSmnElectropriest` blessé même camp → predicted =
  trunc(base×0.5) ; puis buff Nanoscarab actif sur cible → +hpToRepair[lvl]).
