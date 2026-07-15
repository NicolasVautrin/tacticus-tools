# Case #160 — Prediction RangedSpecialist (Neurothrope / Darkstrider) : PAS un bug moteur

**Statut** : RE fait (decompile, build `gqfc5mff6c`) + **CONFIRME LIVE** (repro controle isole,
4 regimes bit-exact, re-expert 2026-07-13). **VERDICT : le pipeline de prediction est DEJA CORRECT**
au HEAD 865be1e. Le "x2 manquant" observe dans un predict_sweep anterieur etait un ARTEFACT DE
CAPTURE, pas un trou de port. AUCUN edit moteur requis. #160 CLOS.

## TL;DR

RangedSpecialist (trait, i2 : "If this unit did not start its turn adjacent to an enemy unit, it
deals +33% Damage with ranged attacks") est **materialise comme EffectComponent visible dans
`decisionView.effects`** avec `IsActive` reflant l'etat "did-not-start-adjacent" FIGE au turn-start.
Le moteur seede sa Scene depuis `decisionView.effects` -> il applique/n'applique pas le +33%
exactement comme l'oracle `aiPlaybookPredict`, dans TOUS les regimes. Donc pas de divergence.

C'est le cas **(4a) WIRING-OK** : l'effet APPARAIT bien dans decisionView.effects quand il
doit, et le gate moteur l'applique. Ce n'est PAS le cas (4b) "synthetiser depuis trait+condition".

## Chaine native (VA citees, build gqfc5mff6c)

- **`RangedSpecialistEffect..ctor @180f67930`** = `DamageModifierAbilityEffect..ctor(this, 0x424)`
  (@180f163d0) : stocke l'`AbilityOrEffect` id **0x424=1060** dans un Nullable @+0x30. (Comme
  Neuroparasite, l'EffectType CAPTE live est distinct de l'id ctor : le dict trait->effet donne
  0x424 -> 0x5eb=1515 ; le nom capte = "RangedSpecialist".)

- **`RangedSpecialistEffect.CreateEffectDamageBonusForAttack @180f67520`** = le +33% :
  `EffectBonus.ForPercentIncrease(cond, Get(ConfigConst 0xf))` ou
  `cond = (OwnerIsCaster & IsRangedAttack & !TriggeringAbilityIs(0x434)) | (TriggeringAbilityIs(0x434)
  & IsRangedAttack & Parent==...)` (0x434=1076 = branche overwatch). Magnitude `ConfigConst key 0xf`
  = `traitVariables.rangedSpecialistDmgPct` = **33**. => +33% sur les attaques RANGED (normale ET
  specials ranged ; PAS de gate IsNormalAttack, contrairement a CrushingStrike).

- **`RangedSpecialistEffect.CreateHandleTriggerAbilitiesInternal @180f677d0`** = la CONDITION
  d'(de)activation (le coeur du "did-not-START-adjacent") :
  `On(0x12) & <trigger@+0xa0>` puis
  `If( HasAdjacentEnemies(self),  DeactivateEffect(self@0x150),  ActivateEffect(self@0x150) )`.
  => l'effet EXISTE toujours sur le porteur (owner-effect du trait) ; sa branche IsActive est
  RECALCULEE au trigger **0x12** (= turn-start). Adjacent au start -> Deactivate (IsActive=false) ;
  pas adjacent -> Activate (IsActive=true). **Figee pour tout le tour** (pas re-evaluee mid-turn
  au deplacement).

- **`StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait @18157e800`** = lookup dict
  TraitType -> List<EffectType> (owner-effects ajoutes au porteur a la creation d'unite,
  `InitializeActorAbilitiesOperation.Execute @180e74660`). RangedSpecialist en fait partie ->
  le porteur porte l'effet des le spawn.

- Cote RPC : `readEffectsByUnit` (frida `hooks/game/effects.ts`) lit
  `EffectsOwnedComponent.ActiveEffectIds` -> resout chaque `EffectComponent.EffectType`(@0x58) +
  `IsActive`(@0x5c) et **DROP les effets inactifs** (`if (!info.active || info.removed) continue`).
  => quand RangedSpecialist est OFF (adjacent au start), IsActive=false -> ABSENT de
  decisionView.effects ; quand ON, present.

## Port existant (correct, aucun changement)

- `engine/entities/effects/loki.py::RangedSpecialistEffect.create_effect_damage_bonus_for_attack`
  : `if not is_ranged: return None ; return for_percent_increase(True, trait_var("RangedSpecialist",
  "rangedSpecialistDmgPct"))`. Applique +33% des que `is_ranged` ET que l'effet est present dans la
  liste consommee. Pas de gate adjacency cote effet — CORRECT, car l'adjacency-au-start est portee
  par la PRESENCE/ABSENCE de l'effet dans la capture (IsActive), pas par un gate compute-time.
- `engine/entities/effects/factory.py` : `TRAIT_OWNER_EFFECTS["RangedSpecialist"]=["RangedSpecialist"]`
  (0x424=1060 -> 0x5eb=1515) ; routage `EFFECT_CLASSES["RangedSpecialist"]=RangedSpecialistEffect`.
- Cote prediction : `prediction.make_normal_attack_predictions` -> `att_effects=scene.effects(att_id)`
  -> `calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=...)`. `scene.effects` =
  `EffectsState.active_effects` seede depuis `decisionView.units[].effects` (`scene.step_context`).
  Donc RangedSpecialist est applique ssi il est dans la capture -> mirror exact de l'oracle.

## Repro LIVE controle (runner isole, session 12, build gqfc5mff6c)

Runner : `--p-units tyranNeurothrope,tyranTyrantGuard --a-units orksNob,orksNob --board MC1_67`.
Neurothrope normalAbilityId=69 (Loki_NormalAttack, 1 hit ranged R3 pierce100).
Compare `aiPlaybookPredict(u81,tgt,69)` (oracle DIRECT playbook) vs
`prediction.make_normal_attack_predictions` (moteur) A POSITION COURANTE.

| Regime | Neurothrope | decisionView.effects | ENGINE | ORACLE | mods |
|---|---|---|---|---|---|
| RS-ON (start non-adjacent) | @(4,6) -> u77 | RangedSpecialist present | [2136,3205] | [2136,3205] | [1.33] |
| RS-OFF (start adjacent) | @(5,8) start adj u77 -> u79 | RangedSpecialist ABSENT | [99,903] | [99,903] | - |
| RS-OFF-moved (start adj, bouge loin mid-turn) | @(3,6) -> u77 | RangedSpecialist ABSENT (fige) | [1614,2422] | [1614,2422] | [1.5,0.67] |
| RS-ON + elevation/LightCover | @(3,6) start non-adj -> u77 | RangedSpecialist present | [3204,4808] | [3204,4808] | [1.33, 1.5] |

**TOUS BIT-EXACT.** Points prouves LIVE :
1. RangedSpecialist EST dans decisionView.effects quand ON (start non-adjacent), ABSENT quand OFF.
2. L'(de)activation est FIGEE au turn-start (0x12) : apres un move mid-turn qui eloigne le
   Neurothrope, RangedSpecialist NE reapparait PAS. L'oracle utilise le MEME etat fige.
3. Le "x2" du brief = combinaison **RangedSpecialist x1.33 * elevation x1.5 = 1.995 ~= 2.0**
   (regime 4 : [3204,4808] / [1614,2422] = 1.985). Le moteur applique les DEUX (mods=[1.33, 1.5]).

## Explication du "x2" anterieur (predict_sweep eng=[803,1205] vs live=[1606,2410])

Ratio exact 2.00 = ~1.33 * 1.5. C'etait un etat ou la Scene moteur etait seedee depuis un
`decisionView` NE CONTENANT PAS RangedSpecialist (attaquant ayant demarre adjacent -> RS OFF cote
capture) tout en attaquant depuis une tuile elevee, OU un decalage de capture temporel. Ce n'est
PAS un bug de logique du gate : quand la capture reflete l'etat reel (RS ON present), le moteur
applique le +33% comme l'oracle. Le harnais `predict_sweep.build_rows` cycle deja le tour
(reset HasMoved) et re-lit decisionView APRES cycle -> l'etat fige est correctement capte.

## Hors scope (decouvertes incidentes, PAS #160)

- Sur ce runner, `predict_sweep` a flag un MAJOR sur **SpiritLeech** (active 1104) :
  live=[1390,2085] vs eng=[66,605] (facteur ~21x, PAS ~1.33/2.0). Gap de base/formule du SPECIAL
  SpiritLeech (config-based, cf. case-99), independant de RangedSpecialist. A VERIFIER (le fix #99
  a valide SpiritLeech sur un autre roster [1037,1556] vs [2074,3112]) -> tache separee.
- Generalisation multi-hit : rejouer sur **tauDarkstrider** (carrier RangedSpecialist ranged
  multi-hit 4hR2p20) -> verifier que le +33% s'applique par-coup apres le hits-count. Regime
  overwatch (branche TriggeringAbilityIs(0x434)=1076) non teste live.

## #162 — Resolution (2026-07-15) : multi-hit + overwatch = AUCUN gap, aucun edit moteur

Les 2 items "hors scope" ci-dessus resolus (re-expert a007854e, decompile + live).

### Multi-hit (tauDarkstrider) — DEJA CORRECT (bit-exact live)
Runner isole (build gqfc5mff6c, board MC1_67, `tauDarkstrider,tyranTyrantGuard` vs `orksNob,orksNob`),
Darkstrider @(2,3) ranged 4hR2p20 -> u79 @(4,4), RangedSpecialist ACTIF (start non-adjacent) :

| Cote | min | max | hits |
|---|---|---|---|
| ENGINE `make_normal_attack_predictions` | 2680 | 8048 | 4 |
| ORACLE `aiPlaybookPredict(81,79,69)` | 2676 | 8044 | 4 |

BIT-EXACT (<=4, arrondi Fix64 /100). mods = [1.33 RangedSpecialist, 1.5 StructuralAnalyser, 0.67 def], base=2510.
Le +33% scale PAR-COUP (discrimine : 1.33 une-fois-sur-base donnerait [4676,10044], diverge). Structure native
`GetMultiHitAttackPrediction @181066080` boucle `PredictAttackRaw @181032fb0` ; chaque coup applique la %-list
via `ApplyAllModifiers`. Port (`get_multi_hit_attack_prediction` -> `predict_attack_raw(mods)`) correct PAR
CONSTRUCTION (identique au mono-hit #160 ; le hits-count n'intervient pas dans le placement du %-mod).

### Overwatch — condition RE'd @180f67520, fidele des DEUX cotes
```
cond = ((OwnerIsCaster & IsRangedAttack) & !TriggeringAbilityIs(0x434))                            # tir normal
     | ((TriggeringAbilityIs(0x434) & IsRangedAttack) & AreEqual(self@0x148, Parent(self@0x160)))  # OVERWATCH
```
0x434=1076 = id de l'auto-attaque overwatch ; branche 2 = gate d'OWNERSHIP (pas de cible). Net : **+33% sur
TOUTE attaque ranged du porteur, normale OU tir d'overwatch.**
- **Combat (runner) : DEJA CORRECT.** L'overwatch = `OverwatchAutoAttack` (effect_triggers.py:53) ->
  `AttackDamageOperation` (attaque normale) qui collecte les effets actifs -> RangedSpecialist +33% applique au
  tir ranged. Ne PAS gater sur `TriggeringAbilityIs` cote effet est fidele au resultat net.
- **Prediction : l'overwatch n'est PAS predit — FAITHFUL, pas un gap.** Aucune fonction native de prediction
  d'overwatch (`<Ability>Playbook.MakeDamagePredictions` overwatch = 0) ; l'overwatch est un effet-trigger
  COMBAT, jamais un evenement de prediction du playbook. L'IA native ne l'anticipe pas (cf. blind-spot overwatch).
  Le moteur qui ne le predit pas MIRROIRE le natif.

### Couverture manquante (non-bloquante)
Aucun des 16 carriers RangedSpecialist n'a le trait Overwatch -> le +33% sur le tir d'overwatch est prouve par
LECTURE du chemin combat (reutilise l'attaque normale), pas par mesure live directe (verrou = roster contrive,
faible valeur, non fait). Branche 2 `AreEqual` (6 overloads) lue comme ownership par structure, non confirmee au bit.
