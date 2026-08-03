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

* ~~**`#419-r1-tr14-r5-r1`**~~ — **FERMÉ**, cf. §10. La table est portée à ses **14** entrées,
  transcrites du `.cctor` et confrontées au natif **une par une**. (Le « 16 noms `*NormalAttack*` »
  de cette ligne était un compte approché ET un mauvais critère : l'enum en porte **17**, et le
  nombre de noms n'est pas le nombre d'entrées — cf. §10.2.)
* **`#419-r1-tr14-r5-r2` — la voie ACTIVE reste au kit.**
  `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive` est la SECONDE
  branche du `if`, et son substrat (`UnitConfiguration.ActiveAbilities`) n'a aucun canal de mesure
  dans le port. `substitutes_normal_attack` ne mesure donc que la voie PASSIVE ; le repli lit encore
  `kit["active"]`. Débloqueur : le pendant `ACTIVE_HIERARCHY` du seed.
  **Ce que la RE de #419-r1-tr14-r5-r1 y ajoute** (lu, non porté — hors périmètre de cette tranche) :
  sa table statique est celle de `StaticBattleRules.ActiveAbility$$GetCustomNormalAttack`
  (statics `+0xb8` → **`+0x28`**, une AUTRE table que la passive), écrite par
  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor`, et
  elle contient **exactement UNE entrée** : `1124 PoundThemToDust` → `1126 RogalDorn_NormalAttack`.
  C'est ce qui **ferme la ventilation** des 17 `*NormalAttack*` de l'enum (§10.2) : `1126` est le
  seul qui ne soit ni générique ni valeur de la table passive. Son porteur est une **MACHINE OF
  WAR** (Rogal Dorn Battle Tank), absente de `gameconfig.all_unit_ids()` — donc invisible au
  recensement `lineup`/`npc`/`summons`. À noter pour qui rouvrira `-r2` : `ai/context.py` pose
  `normal_ids = set()` pour les MoW au motif que leurs `weapons` gameconfig sont vides ; si une MoW
  porte `PoundThemToDust`, le natif lui pose bel et bien une attaque normale — c'est le même
  « dérivé du kit » qu'ici, sur l'autre voie. **NON CONFRONTÉ.**
* **`#419-r1-tr14-r5-r3` — la branche TERTIAIRE (relique) de la fabrique n'est pas portée.**
  `GetCustomNormalAttackTypeFromPassive` consulte AUSSI `config@+0xb0` (le `Nullable`
  `TertiaryAbility`) après avoir épuisé la liste. Le port a le canal (`UnitContext.tertiary_ability`,
  #357) mais ne le verse pas au prédicat : aucune des 32 abilities de relique n'est dans la table
  portée, donc l'axe est inerte — à rouvrir si une relique y entre.
* ~~**`#419-r1-tr14-r5-r4`**~~ — **FERMÉ**, cf. §11. `0x0e` = `Erratic`, `0x15` = `Harmless` ; la
  garde est portée sur la voie OFFLINE et confrontée par montage écrit.
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

---

# `-r1` et `-r4` — la TABLE, et les DEUX TRAITS qui la court-circuitent

Les deux résidus vivent dans la **même fonction**, `UnitFactory$$AddNormalAttackAbility` : `-r4` est
sa première ligne, `-r1` la table que sa deuxième ligne consulte. D'où une seule tranche.

## 10. `-r1` — la table statique, lue au `.cctor` puis confrontée entrée par entrée

### 10.1 Le canal : le `.cctor`, pas un capteur neuf

Le résidu nommait deux canaux possibles : lire le `Dictionary` statique **à l'exécution**
(`statics +0xb8` → `+0x50`), ou balayer `decisionView`. Le premier aurait demandé un capteur neuf,
donc une fenêtre de reinject. **Ni l'un ni l'autre n'était nécessaire** : ce champ statique est
écrit **une seule fois**, par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor`, qui
construit le `Dictionary` puis empile **14 `Add(key, value)` à littéraux constants** avant de
l'assigner à `+0x50`. La table est donc **lisible au décompilé, en clair**.

Le second canal, lui, sert de **confrontation** (§10.3) — et il ne demande rien non plus :
`decisionView.units[].abilities` publie `kind == "normal"` pour **toutes** les unités du board.

### 10.2 Les 14 paires, et trois contrôles de lecture

| # | clé `TriggeredAbilityType` | → valeur `ActiveAbilityType` |
|---|---|---|
| 1 | `1083 HeavyBoltPistol` | `1046 TemplarInitiateNormalAttack` |
| 2 | `1119 MV71SniperDroneSquad` | `1076 MV71SniperDroneSquadAttack` |
| 3 | `1147 ProperKilly` | `1086 ProperKilly_NormalAttack` |
| 4 | `1190 BlisteringAssault` | `1114 BlisteringAssault_NormalAttack` |
| 5 | `1197 FeederTendrils` | `1120 FeederTendrils_NormalAttack` |
| 6 | `1090 Boltstorm` | `1128 Boltstorm_NormalAttack` |
| 7 | `1205 OptimizedGait` | `1123 OptimizedGait_NormalAttack` |
| 8 | `1243 FloatingDeath` | `1146 FloatingDeath_NormalAttack` |
| 9 | `1256 AncientFury` | `1162 AncientFury_NormalAttack` |
| 10 | `1220 Wraithcannon` | `1138 Wraithcannon_NormalAttack` |
| 11 | `1303 ElectroShock` | `1178 ElectroShock_NormalAttack` |
| 12 | `1107 RighteousRepugnance` | `1182 RighteousRepugnance_NormalAttack` |
| 13 | `1484 TalonOfHorus` | `1205 TalonOfHorus_NormalAttack` |
| 14 | `1512 Fealty` | `1220 Fealty_NormalAttack` |

Trois contrôles **indépendants** avant toute mesure live :

1. **Les 4 entrées déjà portées y sont, à l'identique et dans la même orientation** — 4/4. Elles
   avaient été établies une par une par mesure live (#446-r1, #446-r3, #419-r1-tr14-r5) ; les
   retrouver dans le `.cctor` valide la **lecture**, pas seulement la table.
2. **L'orientation clé/valeur est prouvée par un SECOND corps.**
   `StaticBattleRules.TriggeredAbility$$IsCustomNormalAttackDerivedFromTriggeredAbility` fait
   `dict.Values.Contains(<ActiveAbilityType>)` sur ce même champ `+0x50` : les valeurs sont donc des
   `ActiveAbilityType`, les clés des `TriggeredAbilityType`. On ne le déduit pas de l'ordre des
   arguments d'un `Add` gshared.
3. **La ventilation des `*NormalAttack*` de l'enum est CLOSE.** `ActiveAbilityType` en porte **17**
   (pas 16) : `17 NormalAttack` et `69 Loki_NormalAttack` (les génériques), les **14** valeurs
   ci-dessus, et `1126 RogalDorn_NormalAttack` — seule valeur de la table de la voie **ACTIVE**
   (§8, `-r2`). **Aucune orpheline.**

⚠ **Deux entrées interdisent de dresser cette table « par les noms »**, et c'est le cœur du résidu :
`HeavyBoltPistol` rend `TemplarInitiateNormalAttack` (**aucune** parenté lexicale), tandis que
`RogalDorn_NormalAttack` — qui, lui, *porte* le suffixe — n'est la valeur d'**aucune** clé passive.
Un inventaire par grep aurait donc raté la première et inventé la seconde.

### 10.3 Confrontation live — 14/14, par DEUX chemins, avec contrôles

Canal : `decisionView.units[].abilities` `kind == "normal"`, c.-à-d.
`ActiveAbilityComponent.NormalAttackType@0x28`, le champ que la fabrique écrit.

**Chemin A — porteurs naturels, AUCUN montage.** Cinq passifs ont un porteur `lineup` **au pool**
(`rl_duel build --list-pool`, rank 17) et le seed BC les porte déjà en `BC.Units[].PassiveAbilities` :

| unité | passif d'entité | attaque normale NATIVE |
|---|---|---|
| `tauMarksman` | `MV71SniperDroneSquad` | `1076` ✅ |
| `templAggressor` | `Boltstorm` | `1128` ✅ |
| `adeptMorvenn` | `RighteousRepugnance` | `1182` ✅ |
| `tyranDeathleaper` | `FeederTendrils` | **`1120`** ✅ (entrée NEUVE) |
| `admecRuststalker` | `OptimizedGait` | **`1123`** ✅ (entrée NEUVE) |
| `astraBullgryn`, `necroWarden` (témoins) | — | `69 Loki_NormalAttack` |

**Chemin B — greffe écrite**, une unité neutre par passif (`BC.Units[].PassiveAbilities = [<id>]`,
le levier du contrôle apparié de #446-r1 §4), plus un **témoin** à `PassiveAbilities = []` :

| porteuse | passif greffé | attaque normale NATIVE |
|---|---|---|
| `astraBullgryn` | `HeavyBoltPistol` | **`1046 TemplarInitiateNormalAttack`** ✅ |
| `necroWarden` | `ProperKilly` | `1086` ✅ |
| `orksNob` | `BlisteringAssault` | `1114` ✅ |
| `spaceHound` | `FloatingDeath` | `1146` ✅ |
| `eldarRanger` | `AncientFury` | `1162` ✅ |
| `bloodIntercessor` | `Wraithcannon` | `1138` ✅ |
| `darkaTerminator` | `ElectroShock` | `1178` ✅ |
| `tauCrisis` | `TalonOfHorus` | `1205` ✅ |
| `ultraTitus` | `Fealty` | `1220` ✅ |
| `worldJakhal` (témoin) | *(aucun)* | `69 Loki_NormalAttack` |

**14 / 14, 3 témoins conformes.** Le chemin B tranche aussi la confrontabilité que le recensement
laissait ouverte : `BlisteringAssault`, `ProperKilly` et `TalonOfHorus` n'ont **zéro** porteur dans
le gameconfig, `Wraithcannon` et `Fealty` n'en ont que des **npc** — et les cinq sont pourtant
confrontées, parce que la fabrique ne lit **que** la liste de passifs de la configuration. Le
témoin n'est pas décoratif : sans lui, un montage qui n'aurait rien installé rendrait des `69`
partout et se lirait comme « aucune substitution » au lieu de « montage mort ».

### 10.4 Pourquoi la table DOIT être complète — la boucle, pas la table

Une table partielle ne fait pas « moins de dispatch ». `GetCustomNormalAttackTypeFromPassive` rend
au **PREMIER** passif substituant de la liste ; quand une entrée manque, la boucle du port la
**saute** et donne la main à la suivante — ce que le natif ne fait jamais. Le montage l'exerce :

| `BC.Units[].PassiveAbilities` | natif | port, table à 14 | port, table à 4 (avant `-r1`) |
|---|---|---|---|
| `templAggressor` = `[HeavyBoltPistol, Boltstorm]` | `1046` | `1046` — pas de fold | `1128` — **folde `Boltstorm` à tort** |
| `astraBullgryn` = `[Boltstorm, HeavyBoltPistol]` | `1128` | `1128` | `1128` (coïncide) |

Le second bras est la **réciproque** : même paire, ordre inverse, réponse native différente — ce
qui interdit de lire le premier comme un artefact du montage. Et le bras réciproque est le régime où
les deux tables **coïncident** : il ne prouve donc rien à lui seul, il **borne** (le fix ne déborde
pas). C'est le premier bras qui porte la preuve, et la contre-épreuve « table d'avant » y **mord**
sur la prédiction de dégât (le fold `Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction`
s'ajoute à tort).

**Chiffres, bras `[HeavyBoltPistol, Boltstorm]`** (board `C2_02`, `templAggressor` → `astraBullgryn`,
tuile `(0,2)` à distance, ability native `1046`) :

| | bornes de dégât |
|---|---|
| natif | `1299..1950` |
| port, table à 14 | **`1299..1950`** — exact |
| port, table à 4 (avant `-r1`) | **`2628..3942`** — **+102 % / +102 %** |

`2628..3942` est exactement la valeur `kit` de la généralisation de #551 (6 coups au lieu de 3) : la
table partielle faisait folder le porteur comme si `Boltstorm` avait gagné la boucle. L'écart de
`-r1` n'est donc **pas** un raffinement de couverture — c'est un **facteur 2 sur les deux bornes**,
dans un régime qu'un montage de confrontation atteint.

## 11. `-r4` — `Erratic` et `Harmless`

### 11.1 Ce que le décompilé dit, verbatim

```csharp
// UnitFactory$$AddNormalAttackAbility, premières lignes
if (config.Traits.Contains(0x0e)) return;     // config@+0xd0 = UnitConfiguration.Traits
if (config.Traits.Contains(0x15)) return;
```

Deux `List<UnitTrait>.Contains` et un `return` **sec** : ni la voie passive, ni la voie active, ni
le repli générique ne sont atteints, et `ActiveAbilityComponent$$Add` n'est jamais appelé. L'unité
n'a **aucune** attaque normale ; `NormalAttackType@0x28` reste à `0`.

`IdunBattle.Entities.Enum.UnitTrait` : **`0x0e` = `Erratic`, `0x15` = `Harmless`**. ⚠ Ce n'est pas
`NonAttacking` (1033) — un trait voisin par le sens, absent de cette garde. Les valeurs se lisent,
elles ne s'infèrent pas d'une affinité de nom.

Le substrat est `UnitConfiguration.Traits`, donc `BC.Units[].Traits` : un fait d'**ENTITÉ**, comme
les passifs. C'est exactement l'axe de #264.

### 11.2 Où le port divergeait — et où il ne divergeait PAS

Le port a **deux** faces, et une seule était touchée :

* **face LIVE** (`ai/context.py`) — `normal_ids` se lit dans `decisionView` (`kind == "normal"`).
  C'est la **mesure** du champ que la fabrique écrit : conforme par construction, rien à faire.
* **face OFFLINE** (`ai/state_bridge.py`) — celle qui joue les summons et les unités `ai_controlled`
  sans RPC. Elle **dérivait** l'existence de l'attaque normale du KIT : `_abilities_of` posait
  `NormalAttack` dès que `gameconfig[vid].weapons` était non vide, et `_attack_abilities` la posait
  **inconditionnellement**. Une unité `Erratic`/`Harmless` s'y voyait donc générer, scorer, et
  potentiellement **choisir** une attaque que le natif ne propose pas — dégradation **permissive**,
  ni erreur ni crash.

Le fix pose `has_normal_attack(entity_trait_names(ctx, vid))` sur les **trois** sorties de la face
offline (`abilities`, `ab_name_by_id`, `normal_ids`) **et** sur `_attack_abilities` (les plans) —
laisser les plans seuls aurait produit un `normal_ids` vide mais des `evals` d'attaque normale,
c.-à-d. un état incohérent plutôt qu'un fix.

### 11.3 La confrontabilité : ZÉRO porteur ≠ non confrontable

Recensement : **683** kits gameconfig (`lineup` 127, `npc` 491, `summons` 65) et les **175** unités
du seed BC — **aucune** ne porte `Erratic` ni `Harmless`. La garde est donc, *sur les données de ce
build*, du code que rien n'atteint.

Ce n'est pas un verdict de non-confrontabilité : `BC.Units[].Traits` est **écrivable**, exactement
comme `PassiveAbilities` (c'est le levier de #264 et de #446-r1 §4). Le montage écrit ajoute le
trait à la liste **existante** de l'unité (la remplacer retirerait `Hero`/l'alliance et ferait
varier autre chose que la seule variable étudiée), sur un **bras apparié** dont l'autre côté ne
diffère que par ce trait, avec un **témoin sans trait dans chaque bras** :

| bras | `necroWarden` (+`Harmless`) | `orksNob` (+`Erratic`) | témoin `astraBullgryn` |
|---|---|---|---|
| `ctrl` | `69` | `69` | `69` |
| `trait` | **aucune** | **aucune** | `69` |

et côté port, `state_bridge.build_from_state(...).normal_ids` :

| bras | garde armée | garde COUPÉE (= avant `-r4`) |
|---|---|---|
| `ctrl` (`necroWarden`, `orksNob`) | `[17]` | `[17]` — **inerte**, la réciproque |
| `trait` (`necroWarden`, `orksNob`) | **`[]`** | **`[17]`** — **MORD** |

La contre-épreuve est ce qui interdit de lire le `[]` comme un artefact (unité sans arme, montage
mort) : couper la garde le fait **redevenir** `[17]`, et seulement sur le bras qui porte le trait.

## 11.4 Où la garde est posée — et où elle ne l'est PAS

Sur les **trois** sorties de `build_from_state` (`abilities`, `ab_name_by_id`, `normal_ids`) **et**
sur `_attack_abilities`, qui alimente les `plans`. Ne garder que `normal_ids` aurait produit un
`normal_ids` vide avec des `evals` d'attaque normale dans le plan — un état **incohérent**, pire
qu'un port permissif : `_best_attack` itère les `evals` et prend `NORMAL_ATTACK_PLAYBOOK` pour
`ab in ctx.normal_ids`, sinon `get_playbook_or_default(ab)`. Une attaque normale restée dans les
plans mais absente de `normal_ids` serait donc scorée par le playbook **par défaut**.

Rien n'est posé côté LIVE ni côté COMBAT — par lecture, pas par omission : cf. §11.2 et §12.

## 12. Ce qui n'est PAS couvert

* **`-r2` et `-r3` ne sont pas portés** (hors périmètre de la tranche). §8 dit ce que cette RE y
  ajoute : la table de la voie ACTIVE est lue et tient en une entrée.
* **La face COMBAT de `-r4`.** Le runner exécute l'attaque normale par `AttackUnitMessage`, sans id
  d'ability : il n'y a pas de point où le port « donne » une attaque normale en combat, seulement le
  générateur d'action qui la propose — et c'est lui qui est gardé. Aucune mesure n'a été prise du
  côté `visit_AttackUnitMessage` pour une unité `Harmless`, parce qu'aucun chemin porté ne produit
  ce message pour elle une fois la face décision gardée. **Non couvert, non nécessaire aujourd'hui.**
* **Les molds de PRÉDICTION restent quatre.** La table dit quelle attaque normale l'entité porte ;
  elle ne dit rien du mold. Pour les dix attaques normales concrètes sans mold porté, la prédiction
  reste sur la branche générique — c'est la couverture des molds, un axe **distinct** du dispatch, et
  il n'a pas bougé.
* **Les porteurs SUMMON de la table** (`ultraSmnDreadnought`/`AncientFury`,
  `tyranSmnSporeMine`/`FloatingDeath`, `templInitiate`/`HeavyBoltPistol`,
  `admecSmnElectropriest`/`ElectroShock`) n'ont pas été confrontés **par leur summoner** : les quatre
  entrées le sont par greffe (§10.3, chemin B), ce qui teste la fabrique, pas la chaîne de spawn.
* **Aucun chiffre de coût** n'a été pris pour le RPC supplémentaire — la gate `-r4` n'en ajoute
  aucun (elle lit un `UnitContext` déjà chargé).

## 13. Ce que les gardes éprouvent — et qu'elles ROUGISSENT

`tests/engine/test_419r1tr14r5_r1r4_normal_attack_table_live.py`, **9 crans** : la taille de la
table (cran OFFLINE), les 14 entrées contre le natif, les 3 témoins, les deux ordres de la même
paire, la conformité de la prédiction sur le bras discriminant, la contre-épreuve « table d'avant »,
la garde des traits côté natif, côté port, et sa contre-épreuve avec réciproque.

**Éprouvées par MUTATION DU CODE LIVRÉ**, motif vérifié avant écriture à chaque fois :

| mutation | rouges |
|---|---|
| `CUSTOM_NORMAL_ATTACK_BY_PASSIVE` réduit à ses 4 entrées d'avant | **4 failed** / 5 passed |
| `has_normal_attack` → `True` inconditionnel | **2 failed** / 7 passed |
| restauration | **9 passed** |

⚠ La première mutation rendait d'abord **5 ERROR de fixture** (`KeyError` sur la table réduite) au
lieu d'un rouge assertionnel. Un rouge de fixture *est* un rouge, mais il ne dit pas **ce qui** a
bougé — le probe lit désormais la table par `.get`, et une entrée retirée produit un `MISMATCH`
nommé. C'est la différence entre « le test casse » et « le test accuse ».

## 14. Tests rejoués (37 verts, 0 rouge)

| fichier | verdict |
|---|---|
| `test_419r1tr14r5_r1r4_normal_attack_table_live.py` (neuf) | 9 passed |
| `test_419r1tr14r5_normal_attack_dispatch_live.py` (le foyer touché) | 6 passed |
| `runner/test_mv71_sniper_drone_live.py` | 5 passed |
| `test_446_r1_boltstorm_followup_live.py` | 5 passed |
| `runner/test_skitarii_turn_live.py` (le bridge OFFLINE, consommateur de `-r4`) | 16 passed (avec le suivant) |
| `test_min_distance_move_leaf_live.py` | ↑ |
| `runner/test_381r1_movable_tiles_pool_live.py` | 5 passed (avec le suivant) |
| `runner/test_deep_strike_live.py` | ↑ |

## 15. Livré (`-r1` / `-r4`)

* `scripts/python/engine/services/custom_normal_attack.py` — la table à 14 entrées,
  `NORMAL_ATTACK_SUPPRESSING_TRAITS` + `has_normal_attack`, et le `None == None` de
  `substitutes_normal_attack` fermé.
* `scripts/python/engine/ai/state_bridge.py` — la garde des traits sur les trois sorties et sur
  `_attack_abilities`.
* `scripts/python/probe_419r1tr14r5_r1r4_normal_attack_table.py` — trois volets (table / ordre /
  traits), greffe écrite, deux contre-épreuves.
* `scripts/python/tests/engine/test_419r1tr14r5_r1r4_normal_attack_table_live.py` — 9 gardes.
