# #419-r1-tr14-r5 — l'écart du composite d'attaque NORMALE : un DISPATCH lu au mauvais endroit

Le résidu décrivait un écart `port − natif` **chiffré, reproductible et décomposé** sur le composite
d'attaque normale du couple (`tauMarksman` greffé, `astraBullgryn`) : `+5.458908` quand l'attaque
évaluée est un TIR, `+10.597881` de plus quand ce tir suit un DÉPLACEMENT. Deux termes, donc — et la
case-doc de la tranche 14 nommait deux pistes pour le second (une feuille de dégât `has_moved`, une
feuille de position du composite d'action).

**Les deux pistes sont RÉFUTÉES, et les deux termes n'en font qu'un.** Il n'y a aucun gap `has_moved`
ni aucune feuille positionnelle manquante : le port prenait simplement la mauvaise **branche
d'attaque normale**, et l'écart n'est que la différence entre les deux branches — laquelle varie avec
le régime, d'où l'apparence de deux termes.

## 0. Re-mesure préalable — les quatre crans n'ont pas bougé après #544

`probe_419r1tr14_heavy_bolt_pistol.py` rejoué sur `ba74b970` (post-#544), montage identique :

| cran | spot | tuile | natif greffé | port | `port − natif` |
|---|---|---|---|---|---|
| `far` | B | (0,2) | 42.711458 | 48.170366 | **+5.458908** |
| `tileAdj_realFar` | B | (0,1) | 9.738052 | 9.738052 | 0.000000 |
| `adj` | A | (0,1) | 12.727454 | 12.727455 | +0.000001 |
| `realAdj_tileFar` | A | (0,2) | 35.102979 | 51.159768 | **+16.056789** |

Identiques au relevé d'ouverture. Le canal MULTIPLICATEUR de #544 n'y touche pas.

## 1. Ce que dit le décompilé

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, lu verbatim :

```csharp
if (config.Traits.Contains(0x0e) || config.Traits.Contains(0x15)) return;   // pas d'attaque normale
var fromPassive = GetCustomNormalAttackTypeFromPassive(this, config);
if (fromPassive.HasValue) { type = fromPassive.Value; state = triggeredAbilityState; }
else {
    var fromActive = GetCustomNormalAttackTypeFromActive(this, config);
    if (fromActive.HasValue) { type = fromActive.Value; state = activeAbilityState; }
    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }
    else { type = this.<+0x20>; state = new AbilityState(Level(1), config.<+0x74>); }
}
ActiveAbilityComponent.Add(comp, type, state, null);
```

et `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` :

```csharp
foreach (var passive in config.<+0xa8> /* UnitConfiguration.PassiveAbilities */) {
    var custom = StaticBattleRules.TriggeredAbility.GetCustomNormalAttack(passive);
    if (custom.HasValue) return custom;          // le PREMIER passif gagnant s'impose
}
if (config.<+0xb0>.HasValue) { ... }             // branche TERTIAIRE (relique), même règle
return null;
```

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack`
est un `ContainsKey` + `get_Item` sur un `Dictionary<TriggeredAbilityType, ActiveAbilityType>`
**statique**.

**La clé de dispatch est donc `UnitConfiguration.PassiveAbilities` — un fait d'ENTITÉ**, écrit UNE
fois dans `ActiveAbilityComponent.NormalAttackType@0x28`, jamais le catalogue gameconfig.

Trois lectures qui ne se devinent pas :

1. **La substitution vient du PASSIF, et elle a priorité sur la voie ACTIVE.** Un montage qui vide
   `PassiveAbilities` retire donc l'attaque normale custom — ce n'est pas un effet de bord, c'est la
   première branche du `if`.
2. **L'état d'ability suit la voie** : `triggeredAbilityState` pour la voie passive,
   `activeAbilityState` pour la voie active. Les deux ne sont pas interchangeables.
3. **Deux traits (`0x0e`, `0x15`) suppriment purement l'attaque normale**, avant toute substitution.
   Non exercé ici (aucune unité du montage ne les porte) — noté, pas porté.

## 2. Le fork du port

Trois call-sites re-dérivaient cette clé du **KIT gameconfig par `visualId`** :

| call-site | ce qu'il dispatche |
|---|---|
| `engine/playbook/prediction/normal_attack.py` (`is_mv71_normal_attacker`) | chemin drone `1076 MV71SniperDroneSquadAttack` |
| `engine/playbook/prediction/normal_attack.py` (`_normal_attack_followup_prediction`) | folds `1128 Boltstorm_NormalAttack`, `1182 RighteousRepugnance_NormalAttack`, `1086 ProperKilly_NormalAttack` |
| `engine/runner/operations/damage.py` (`visit_AttackUnitMessage`) | face COMBAT du chemin drone |

Le commentaire du second l'écrivait noir sur blanc : « Cle de dispatch = le PASSIF du kit
gameconfig ». Kit et entité coïncident tant que personne ne touche à la liste de passifs — et
divergent **en silence** dès qu'un montage la modifie, ce que fait **tout** bras
`catalog_inject.write_grafted_seed_bc(..., replace=True)`, c'est-à-dire le montage standard de
confrontation d'une ability à porteur npc/summon.

C'est le même vice que **#366-r1** (`collect_triggered_abilities` dérivait les passifs du kit) et que
**#264** sur l'axe TRAITS. Il avait déjà été mesuré une fois sans être reconnu comme tel : le
contrôle apparié de #446-r1 §4 note « `--unit-stat "templAggressor:PassiveAbilities=[]"`, ce qui
ramène l'attaque normale à `69` » — le fait était établi, mais le port du même commit a câblé son
registre de folds sur le kit.

## 3. La mesure — décomposition par étage et SECOND cas discriminant

`probe_419r1tr14r5_normal_attack_stages.py` : deux bras qui ne diffèrent QUE par
`BC.Units[tauMarksman].PassiveAbilities`, les quatre crans de la tranche 14, et **trois étages**
mesurés séparément — dispatch (`decisionView`, `kind == "normal"`), prédiction (`aiPlaybookPredict`
`healthDmgMin/Max`), utilité (`pairUtility`).

**AVANT le fix** (`port` = le port livré, `PORT_ARM` = son dispatch FORCÉ sur le chemin arme) :

| bras | cran | `ab` natif | NAT dmg | PORT dmg | `port − nat` | `arm − nat` |
|---|---|---|---|---|---|---|
| `kit` | `far` | **1076** | 3854..5782 | 3854..5782 | **0.000000** | −5.458908 |
| `kit` | `realAdj_tileFar` | **1076** | 3854..5782 | 3854..5782 | **0.000000** | −16.056789 |
| `strip` | `far` | **69** | 3418..5126 | 3854..5782 | **+5.458908** | **0.000000** |
| `strip` | `realAdj_tileFar` | **69** | 2570..3854 | 3854..5782 | **+16.056789** | **0.000000** |
| les deux | tuile adjacente (×4) | — | 642..1305 | 642..1305 | 0.000000 | 0.000000 |

Trois choses que ce tableau tranche, et qu'aucune mesure isolée n'aurait tranchées :

1. **L'écart naît à l'étage PRÉDICTION, pas dans le composite d'utilité.** Les bornes de dégât
   diffèrent déjà (`3418..5126` contre `3854..5782`). Un correctif cherché dans les feuilles du
   composite Damage(34) aurait été un fit.
2. **La contre-épreuve est RÉCIPROQUE**, et c'est elle qui ferme le dossier : forcer le chemin arme
   ÉCHANGE exactement les deux colonnes. Le chemin arme du port reproduit le natif **bit à bit dans
   les deux régimes de mouvement**, y compris la chute `3418..5126 → 2570..3854`. Il n'y a donc
   **aucun** gap `has_moved` et **aucune** feuille de position manquante : les deux pistes nommées
   par la tranche 14 sont réfutées par mesure.
3. **Les deux « termes » sont un seul.** `+5.458908` = écart des deux branches sans mouvement,
   `+16.056789` = le même écart quand la branche ARME (et elle seule) réagit au déplacement. Le port
   rendait `48.170366` dans les deux cas parce que le chemin drone, lui, n'a pas de terme positionnel
   ici — l'invariance était la SIGNATURE du bug, pas un second bug.

**Le discriminant du montage** est publié, pas supposé : `decisionView` rend
`1076 MV71SniperDroneSquadAttack` sur le bras `kit` et `69 Loki_NormalAttack` sur le bras `strip`.

## 4. Le fix

Un foyer unique, `engine/services/custom_normal_attack.py`, mirror de
`UnitFactory$$GetCustomNormalAttackTypeFromPassive` : la table des entrées PORTÉES du dictionnaire
statique, la boucle « premier passif gagnant », et le prédicat `substitutes_normal_attack` en
**tri-état** — liste mesurée = mirror strict, `None` = canal muet ⇒ repli KIT, strictement le
comportement d'avant.

La SOURCE est la même des deux côtés, et son parsing aussi :

* **COMBAT** : `UnitContext.passive_abilities`, déjà seedé par `snapshot._load_passive_abilities`
  (#366-r1) depuis `unitAbilityStates`, hiérarchie 2 ;
* **DÉCISION** : `scene._seed_measured_passives`, le pendant qui manquait, sur le même capteur et le
  même champ. Le parsing est extrait dans `snapshot.passive_ability_names_by_unit`, appelé par les
  deux — deux parsings distincts auraient recréé le fork « ce que la prédiction annonce ≠ ce que le
  moteur fait ».

**Rang du seed** : les passifs de configuration sont figés au spawn (la fabrique ne tourne qu'une
fois par entité), donc le COLD de `build_predictor` suffit ; `refresh_shields` ne le rejoue que pour
les **arrivants** (`new_units`), sans quoi un summon dont l'attaque normale est substituée
retomberait sur le kit pour toute la bataille. C'est la différence avec les traits (#267), qu'une
opération accorde en cours de bataille et qu'il faut re-capturer par pas.

## 5. Mesure du fix

| | avant | après |
|---|---|---|
| `strip` / `far` (tuile B, sans mouvement) | `+5.458908` | **0.000000** |
| `strip` / `realAdj_tileFar` (tuile B, après mouvement) | `+16.056789` | **0.000000** |
| `kit` (les quatre crans) | 0.000000 | **0.000000** |
| bornes de dégât, bras `strip`, tuile B | `3854..5782` contre `3418..5126` natif | **identiques**, et `2570..3854` après mouvement |
| contre-épreuve `dispatch forcé`, bras `kit` | — | **reste mordante** (−5.458908 / −16.056789) |

### Les deux résidus JUMEAUX tombent avec lui

Le brief demandait de vérifier si les résidus de la tranche 12, de la tranche 13 et de #446
convergeaient vers un seul foyer. Les trois montages sont des greffes `replace=True` sur
`tauMarksman` ; leurs probes, rejoués après le fix :

| résidu | écart de niveau AVANT | APRÈS |
|---|---|---|
| `#419-r1-tr13-r1` (`Shrapnel`) | `+5.458908`, invariant aux 4 crans | **0.000000** aux 4 crans |
| `#419-r1-tr12-r1` (`ElectroShock`) | `+1.364932`, invariant aux 4 crans | **0.000000** aux 4 crans |
| `#419-r1-tr14-r5` (`HeavyBoltPistol`) | `+5.458908` / `+16.056789` | **0.000000** |

Le résidu §5 de #446, lui, avait déjà été fermé par #446-r1 — mais sa fermeture avait **reproduit**
le vice de source sur le second call-site, ce que la généralisation ci-dessous mesure.

### Généralisation — second porteur, second mold, second board

`templAggressor` (passif `Boltstorm`, fold `GetAdditionalDamagePrediction` — **pas** le chemin
drone), board `C2_02`, passif retiré par `--unit-stat` (le levier de #446-r1 §4, pas une greffe) :

| bras | `ab` natif | NAT dmg / coups | PORT | `port − nat` | canal COUPÉ (= avant le fix) |
|---|---|---|---|---|---|
| `kit` | **1128** | 2628..3942 / **6** | idem | 0.000000 | 0.000000 (inerte — kit et entité concordent) |
| `strip` | **69** | 1299..1950 / **3** | idem | 0.000000 | **+16.606679** (le port folderait 6 coups contre 3) |

Le vice était donc **latent et non mesuré** sur ce second mold : le fix l'y ferme aussi, et la
contre-épreuve « canal coupé » y est mordante d'un côté, inerte de l'autre.

## 6. Ce que la garde éprouve — et qu'elle ROUGIT

`tests/engine/test_419r1tr14r5_normal_attack_dispatch_live.py`, 6 crans : discriminant installé
(1076 vs 69), conformité en niveau aux deux bras et aux quatre crans, conformité de l'étage
PRÉDICTION séparément (une compensation à l'étage utilité ne passerait pas), contre-épreuve du
dispatch forcé (mordante à distance, **inerte en mêlée** — la réciproque : un fix qui déborderait sur
la branche mêlée la ferait rougir), puis les deux crans de généralisation.

**Éprouvée par mutation du code LIVRÉ** (`substitutes_normal_attack` renvoyé au repli KIT
inconditionnel, motif vérifié avant écriture) : **3 rouges / 6**, dont la généralisation. Restauration
puis re-jeu : **6 passed**.

## 7. Tests rejoués (69 verts, 0 rouge)

| fichier | verdict |
|---|---|
| `test_419r1tr14r5_normal_attack_dispatch_live.py` (neuf) | 6 passed |
| `runner/test_mv71_sniper_drone_live.py` | 5 passed |
| `test_446_r1_boltstorm_followup_live.py` | 5 passed |
| `test_446_r3_repugnance_followup_live.py` | 5 passed |
| `test_446_boltstorm_pair_term_live.py` | 5 passed |
| `test_419r1tr14_heavy_bolt_pistol_live.py` | 6 passed |
| `test_419r1tr13_shrapnel_live.py` | 7 passed |
| `test_419r1tr12_electro_shock_live.py` | 7 passed |
| `test_419r1tr10_righteous_repugnance_live.py` | 7 passed |
| `test_419r1tr9_r4_boltstorm_pred_live.py` | 6 passed |
| `runner/test_363_ability_states_default_live.py` (le canal consommé) | 10 passed |
| `runner/test_damage_roll_live.py` (garde COMBAT) | 2 passed |

## 8. Résidus NOMMÉS

* **`#419-r1-tr14-r5-r1` — la table statique n'est portée qu'à QUATRE entrées.** L'enum
  `ActiveAbilityType` porte **16** noms en `*NormalAttack*` (`TemplarInitiateNormalAttack`,
  `BlisteringAssault_NormalAttack`, `FeederTendrils_NormalAttack`, `OptimizedGait_NormalAttack`,
  `RogalDorn_NormalAttack`, `Wraithcannon_NormalAttack`, `FloatingDeath_NormalAttack`,
  `AncientFury_NormalAttack`, `ElectroShock_NormalAttack`, `TalonOfHorus_NormalAttack`,
  `Fealty_NormalAttack`, …) ; `CUSTOM_NORMAL_ATTACK_BY_PASSIVE` n'en couvre que les quatre pour
  lesquelles un mold est porté. Pour les douze autres le port reste sur la branche générique, comme
  avant — ce n'est pas une régression, c'est la couverture des molds. **Canal qui les trancherait** :
  lire le `Dictionary` statique de `StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack`
  (statics `+0xb8` → `+0x50`) à l'exécution, ou balayer `decisionView.abilities[kind=="normal"]` sur
  tout le pool. **NON CONFRONTÉ.**
* **`#419-r1-tr14-r5-r2` — la voie ACTIVE reste au kit.**
  `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive` est la SECONDE
  branche du `if`, et son substrat (`UnitConfiguration.ActiveAbilities`) n'a aucun canal de mesure
  dans le port. `substitutes_normal_attack` ne mesure donc que la voie PASSIVE ; le repli lit encore
  `kit["active"]`. Aucun des quatre molds portés n'emprunte cette voie (les quatre clés sont des
  `TriggeredAbilityType`), donc l'axe est **inerte aujourd'hui** — mais il porterait le même fork
  qu'un montage touche à `ActiveAbilities`. Débloqueur : le pendant `ACTIVE_HIERARCHY` du seed.
* **`#419-r1-tr14-r5-r3` — la branche TERTIAIRE (relique) de la fabrique n'est pas portée.**
  `GetCustomNormalAttackTypeFromPassive` consulte AUSSI `config@+0xb0` (le `Nullable`
  `TertiaryAbility`) après avoir épuisé la liste. Le port a le canal (`UnitContext.tertiary_ability`,
  #357) mais ne le verse pas au prédicat : aucune des 32 abilities de relique n'est dans la table
  portée, donc l'axe est inerte — à rouvrir si une relique y entre.
* **`#419-r1-tr14-r5-r4` — les deux traits qui SUPPRIMENT l'attaque normale ne sont pas portés.**
  `AddNormalAttackAbility` rend sans rien ajouter si `config.Traits` contient `0x0e` ou `0x15`. Le
  port ne modélise pas cette absence (une unité qui les porterait se verrait quand même scorer une
  attaque normale). Non exercé par le montage ; les deux valeurs de `UnitTrait` restent à qualifier.
* **Le coût du seed n'est pas mesuré isolément.** `build_predictor` gagne un RPC `unitAbilityStates`
  (walk complet des entités). Le mur de la passe de cliquets est de 397 s et les fichiers live joués
  n'ont pas changé d'ordre de grandeur, mais aucun chiffre avant/après dédié n'a été pris.

## 9. Livré

* `scripts/python/engine/services/custom_normal_attack.py` — le foyer (table, boucle, prédicat).
* `scripts/python/engine/runner/snapshot.py` — `passive_ability_names_by_unit` (parsing partagé).
* `scripts/python/engine/playbook/scene.py` — `_seed_measured_passives` + appel COLD + arrivants.
* `scripts/python/engine/playbook/prediction/normal_attack.py` — les deux call-sites DÉCISION.
* `scripts/python/engine/runner/abilities/loki/mv71.py` — `is_mv71_normal_attacker` en tri-état.
* `scripts/python/engine/runner/operations/damage.py` — le call-site COMBAT.
* `scripts/python/probe_419r1tr14r5_normal_attack_stages.py` — décomposition par étage, deux bras,
  contre-épreuve réciproque, volet `--generalize`.
* `scripts/python/tests/engine/test_419r1tr14r5_normal_attack_dispatch_live.py` — 6 gardes.
