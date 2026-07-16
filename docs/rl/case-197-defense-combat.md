# Case #197 — Axe DEFENSE face COMBAT/runner : le fork prédiction/combat qui laissait le dégât réel ignorer Thorns

**Status : RESOLVED (session 23, suite de #194). Le dégât RÉEL sur un occupant de tuile Thorns prend
bien +50% (mesuré live) — le runner l'ignorait. Cause = un FORK de port (la moitié DEFENSE de la
fonction native était bolted sur le seul caller prédiction). Fix = consolider le fold DANS la fonction
partagée `build_defender_modifiers_from_effects` (mirror 1:1 de `CalculateDefenderModifiersForPrediction
@181002c30`) → prédiction ET combat l'obtiennent PAR CONSTRUCTION. #194 prédiction préservé bit-exact.**

> **Correction terrain (via #198)** : la tuile −50 DEFENSE de C2_19 (2,2) est un tile-def **Swamp**, PAS
> "Thorns" (aucun board n'a de tileDefId "Thorns" ; marche live `{Grass:0, Trench:0, DryBush:0, Swamp:-50}`).
> Le −50 et le fold ci-dessous restent CORRECTS (ils lisent la stat DEFENSE, pas le nom du terrain) ; seul le
> LABEL "Thorns" était faux. Lire « Swamp » partout où ce doc dit « Thorns ». Cf. case-198.

## Le vrai problème n'était pas « un axe à porter » mais un FORK de port
Le natif fait ça à UN seul endroit : `CalculateDefenderModifiersForPrediction @181002c30` remplit UN
accumulateur avec DEUX moitiés (decompile-confirmé) :
1. **fold du stat-mod DEFENSE** : bloc `@181003037` → `CalculateModifiersFromStatModifications @181004380`
   sur le `DefenseComponent` de la CIBLE (negate=1) → `GetMultiplierFromDamageBonus` → `DamageModifiers.Add` ;
2. **boucle des effets** défenseur (param_5) : malus 0x1a/0x1b/0x19 (ADamageDefenseModifierAbilityEffect,
   Terrifying, TerminatorArmour, Neuroparasite…).

Le port avait mirroré @181002c30 par `build_defender_modifiers_from_effects` — mais **seulement la moitié
(2)**. Les DEUX faces (prédiction `prediction.py`, combat/runner `damage_model.defender_modifiers`)
appelaient bien cette fonction partagée → la moitié (2) ÉTAIT partagée. Mais #194, en découvrant l'axe
DEFENSE (scopé « prédiction »), a ajouté la moitié (1) **en dehors** de la fonction partagée, bolted sur le
caller prédiction (`prediction.py`). Le runner, ayant son propre caller, ne l'a jamais vue → gap #197.

**Le gap #197 = le symptôme downstream de ce fork** (mémoire `check_own_port_before_re` : un port qui
fork une fonction native en N crée des divergences en aval). La bonne réponse n'est PAS un 2e fold parallèle
côté runner (ça pérennise le fork) mais de RE-CONSOLIDER la moitié (1) DANS la fonction partagée.

## Mesure live (probe_197, session 23) — le dégât RÉEL prend +50%
Géométrie #194 (C2_19 seed 777, meph→(1,2), jakhal AI→(2,2) [tuile −50 DEFENSE]) puis endturn pour
redonner la main à meph (déjà adjacent), et **replay-diff bit-exact** de la vraie attaque
(`applyAction` LIVE vs runner offline `AttackUnitMessage` sur le MÊME MT via `dumpRng`) :

| | plage propre offline | rolled | après |
|---|---|---|---|
| AVANT fix | [3006, 4515] (×1.0) | 3950 | jakhal survit (2826) |
| oracle prédiction | [4515, 6774] (×1.5) | — | — |
| LIVE réel | — | ≥6774 | jakhal MORT (0) |

Le dégât réel live (≥6774) est **IMPOSSIBLE sous ×1.0** (max 4516) → le combat natif RÉEL applique le +50%
Thorns, le runner le ratait. `CalculateModifiersFromStatModifications @181004380` était noté « xref-prédiction-
only » (#194) : vrai statiquement, MAIS ses 2 xref sont les builders « ForPrediction » **partagés
prédiction+combat** (misnomer, invoqués par delegate via `CalculateAbilityDamage @18102cb50` slot 0xf) →
le combat les atteint. La mesure tranche définitivement.

## Fix (unification, mirror 1:1 de @181002c30)
- **`entities/effects/__init__.py::build_defender_modifiers_from_effects`** : nouveau paramètre
  `defense_stat` ; après la boucle d'effets, folde `calculate_modifiers_from_stat_modifications(defense_stat,
  negate=True)` dans le MÊME accumulateur — les DEUX moitiés du natif, dans l'ordre natif, à UN endroit.
- **`prediction.py::_add_positional_and_defender_mods`** : passe `defense_stat=scene.defense_stat(tgt_id)` ;
  l'ANCIEN fold séparé est RETIRÉ. L'entrée %-list sort désormais via `def_mods.pct_list` (recopié dans
  `mods.pct_list` comme avant) → composition %-list **commutative sans arrondi intermédiaire** (#98, tous
  cap=None) → **#194 bit-exact préservé** (vérifié : engine {4512, **6774**} vs oracle {4515, **6774**},
  max ratio 1.0000, min −3 = résidu par-coup pré-existant #179).
- **`runner/damage_model.py::defender_modifiers`** : passe `defense_stat` = `ctx.stats.components[DEFENSE]`
  de la CIBLE (l'ECS live — l'analogue de la DefenseComponent que le natif relit ; delta cuit au load depuis
  combatSnapshot via `seed_unit_stats`, per-source, PLUS fidèle que le lump snapshot de la prédiction).
- **`playbook/scene.py::Scene.from_state`** : alimente `defstat_by_id` depuis `ctx.stats[DEFENSE]` (même
  source) → la prédiction OFFLINE (décision sur un état runner) folde aussi Thorns, cohérente avec le combat.
- **`services/damage_modifiers.py`** : docstring de `calculate_modifiers_from_stat_modifications` corrigé
  (« PRÉDICTION-ONLY » RÉFUTÉ par la mesure — c'est le fold DÉFENSEUR partagé prédiction+combat).

⚠ La SOURCE de `defense_stat` diffère par nécessité (prédiction live : `scene.defstat_by_id` refreshé par-pas
car ctx COLD ; runner/from_state : `ctx.stats` = ECS live). **Ce n'est PAS un fork** : le fold (la fonction
native) est ICI, unique ; ce sont deux ENTRÉES vers la même DefenseComponent que le natif relit à chaque calcul.

## Validation
- **Prédiction (garde #194)** : engine == oracle ×1.5, max BIT-EXACT (probe_194_stat re-run post-refactor).
- **Combat runner** : plage propre offline **×1.0 [3006,4515] → ×1.5 [4509,6774]** = oracle [4515,6774]
  (−6 min = 3× le résidu par-coup #179). Le runner applique le +50% sur les bornes de dégât.
- **Tests ciblés** : `test_predict_live` (agrément prédiction défenseur) + `test_nightshroud_combat_live`
  (réduction plate défenseur combat) + `test_damage_roll_live` (roll de base) = **6 passed**, 0 régression.
- Le `off_after ≠ live_after` résiduel du probe meph = **désync RNG multi-coups** (meph = 3 coups + crit
  possible ; le live dépasse la borne ×1.5 non-crit de +2, cohérent avec le résidu par-coup #179 ou un crit) —
  PAS une erreur du fold DEFENSE (les BORNES sont ×1.5-exactes). Le test `attack_replay` ne valide bit-exact
  que le mono-coup propre pour cette raison ; une validation combat bit-exact mono-coup sur Thorns = nicety
  optionnelle (le fold est déjà prouvé par la plage + le partage de code avec la prédiction bit-exacte).

## Même famille (couverte par construction, des DEUX faces)
`SpiderWeb_DefenseReduction` (33), `DryBush_DefenseBonus` (35), `ShrubBonusDefense` (@180f46ee0, #126) :
tous stat-mods DEFENSE sur occupants → foldés dès que la modification apparaît (aucun code par-effet).

## Reste ouvert (suivi)
La matérialisation DYNAMIQUE mid-sim (une unité qui ENTRE sur une tuile Thorns PENDANT le runner-sim doit
gagner la modification −50 DEFENSE via `MoveUnitOperation`, symétrique au retrait à la sortie) n'est PAS
portée : le runner source `defense_stat` de l'ECS au LOAD (correct pour une cible DÉJÀ sur Thorns, le cas
mesuré). C'est la complétion #128 (tile-triggers) pour l'axe DEFENSE → tâche de suivi dédiée.

## Anchors
CalculateDefenderModifiersForPrediction @181002c30 (fold DEFENSE @181003037 + boucle effets) ;
CalculateModifiersFromStatModifications @181004380 ; CalculateAbilityDamage @18102cb50 (slot 0xf =
builder défenseur partagé, misnomer) ; ThornsBlockMovementAbility @1811c8d70 (pose −50 DEFENSE, cf. #194).
Port : build_defender_modifiers_from_effects (defense_stat), prediction._add_positional_and_defender_mods,
damage_model.defender_modifiers, scene.from_state. Probe : scratchpad probe_197.py (replay-diff Thorns).
Cf. docs/rl/case-194-defense-axis.md (face prédiction + RE de la pose).
