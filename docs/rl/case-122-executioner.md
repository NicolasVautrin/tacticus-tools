# Case #122 — Executioner (eldarFarseer) : hits = rounds started (sous-compte port)

Statut : RE + confirmation EMPIRIQUE LIVE faites ; port BLOQUE sur la source OFFLINE du compteur de
rounds (RE en cours, agent re-expert ad53d111 @dd010b6). Ability `Executioner` (id **1066**, porteur
eldarFarseer "Eldryon"), Psychic range 2.

## Symptome (#122)
Oracle prevoit N coups (N = rounds started), port en prevoit 1 -> sous-prediction ~xN.

## Mecanique (i2 + RE)
i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED. If the target is eliminated, an
adjacent enemy also takes 582-2183 for each round started. »
- `ExecutionerAbility$$GetHits @1811da4a0` = `DSLFactory.RoundsStarted(this+0x30, *(this+0x30)+0x160, 0)`.
- `DSLFactory$$RoundsStarted @180dfa6c0` -> `RoundsStartedFormula$$Calculate @180f223e0` (formule ECS
  lourde : itere une collection @param_1+0x10 via query FUN_180025220(4, DAT_1831e7018, ...), composant
  DAT_183200900 par entite, accumule `iVar15 += *(int*)(lVar7 + 0x58)`).
- `ExecutionerPlaybook$$MakeDamagePredictions @1811303b0` / `GeneratePredictions @181130150`.

## Confirmation EMPIRIQUE LIVE (2026-07-12, runner 47, probe_122_rounds.py)
Farseer u82 drive a portee 2 de custoTrajann u78 ; aiPlaybookPredict(1066) predict-only (jamais CAST ->
cible survit) balaye plusieurs cycles de round :
```
cycle 0 | ORACLE n=1 per={78:1} appliedHits=3 | PORT n=1 hits=1
cycle 1 | ORACLE n=1 per={78:1} appliedHits=4 | PORT n=1 hits=1
cycle 2 | ORACLE n=1 per={78:1} appliedHits=5 | PORT n=1 hits=1
cycle 3 | ORACLE n=1 per={78:1} appliedHits=6 | PORT n=1 hits=1
cycle 4 | ORACLE n=1 per={78:1} appliedHits=7 | PORT n=1 hits=1
cycle 5 | ORACLE n=1 per={78:1} appliedHits=8 | PORT n=1 hits=1
```
=> **UN SEUL event** (pas N events : != MurderousSwing #108), `appliedHits` = **rounds started**, +1 par
round-cycle (endturn mine+enemy). Le degat total = base x appliedHits. Le port emet appliedHits=1 (config
nrOfHits) -> sous-compte xN.

## Plan de port
1. Ajouter `ExecutionerAbility(AActiveAbility)` dans active_ability.py + registrer `"Executioner"` dans
   `_SPECIAL_ABILITY_CLASSES` (mirror pattern BloodyFuryAbility/HarvesterOfSoulsAbility/MurderousSwingAbility).
2. Override `get_special_hits(is_melee) -> rounds_started` (mirror ExecutionerAbility.GetHits =
   DSLFactory.RoundsStarted). Le pipeline existant get_multi_hit_attack_prediction boucle `hits` fois ->
   1 event, appliedHits=N, degat = N x per-coup. AUCUN changement d'events (single-target).
3. **BLOQUEUR** : la Scene/ctx n'expose AUCUN compteur de round offline (scene.py : 0 match `round`).
   decisionView.roundCap = clock BOMBARDMENT (EnvEndBombardment), PAS rounds-started. -> il faut un
   CAPTEUR : exposer le compteur de rounds dans decisionView/snapshot (source runtime = verdict agent
   re-expert ad53d111 : ou vit le compteur dans l'etat + offset). Puis scene lit le round, get_special_hits
   le retourne. Capteur = hooks change -> rebuild + REINJECT (a faire APRES la fin de l'agent).
4. Valider live : oracle appliedHits == port appliedHits (== rounds started) sur plusieurs rounds.

## PORT IMPLÉMENTÉ + VALIDÉ LIVE (2026-07-12)

Verdict re-expert (agent ad53d111) : `RoundsStartedFormula.Calculate @180f223e0` = Σ `UnitComponent.
turnsStarted@+0x58` sur units-in-scope (= CASTER) ; exposé stat 12 (`GetStat(unit,0xc)` =
`UnitTurnsStartedFormula.Calculate @180f2d6c0`). Incrémenté LIVE par `StartTurnOperation.Execute
@180ea3fb0` (+0x58 += 1 / unité du joueur courant, au début de tour). Off-by-one : incr AVANT que
l'ability agisse -> round 1 = 1 coup. Scope caster-only (lire le compteur du CASTER, pas un round global).

Port (3 fichiers) :
1. `frida/hooks/features/ai-step/rpc-snapshot.ts` : `COMBAT_STAT_IDS += turnsStarted: 12` (capteur ;
   `seed_unit_stats` crée auto le StatComponent[12] -> `ctx.stat(12)`). REBUILD + REINJECT + amorce.
2. `engine/entities/stats.py` : `StatType.TURNS_STARTED = 12`.
3. `engine/entities/abilities/active_ability.py` : `ExecutionerAbility.get_special_hits ->
   max(1, caster.stat(TURNS_STARTED))` + registre `_SPECIAL_ABILITY_CLASSES["Executioner"]`.

VALIDÉ LIVE (probe_122_rounds.py, runner FRAIS, prédicteur RE-CAPTURÉ chaque cycle) :
```
cycle 0..5 | ORACLE appliedHits 3->8 (n=1) | PORT appliedHits 3->8 (n=1) turnsStarted 3->8 | OK x6
```
Port == oracle BIT-EXACT sur le compte de coups à chaque round (avant : appliedHits=1 fixe). Single event
(appliedHits=N, PAS N events).

## Qui met à jour turnsStarted offline ?
- PRÉDICTION : PERSONNE (le port ne le maintient pas). Lu LIVE via `combatSnapshot` (capteur stat 12),
  figé par scène -> re-capturer (nouveau `build_predictor`) = valeur fraîche. La staleness du 1er run
  (probe réutilisant 1 snapshot figé round 9) = artefact de probe, PAS un bug port.
- RUNNER offline : **RÉSOLU #123** (2026-07-12). Le `StartTurnOperation` porté bumpe MAINTENANT le stat-12
  PER-UNIT (`UnitComponent+0x58`) de chaque unité VIVANTE du joueur courant, en plus du compteur GLOBAL
  `state.turn_counts` (`TurnComponent+0x38`). Mirror fidèle de la boucle interne de `StartTurnOperation.
  Execute @180ea3fb0` (`*(int*)(unitComp+0x58) += 1` sur `PlayerComponent.GetCurrentlyOwnedUnitIds`,
  décompilé relu). Détail #123 ci-dessous.

## #123 — Runner offline : bump per-unit turnsStarted (RÉSOLU 2026-07-12)
GAP découvert au port #122 : le runner offline avançait `state.turn_counts` (global) mais pas le stat-12
per-unit -> tout consommateur de `GetStat(unit, 0xc)` en sim multi-round (Executioner) lisait la valeur
seedée (périmée). Décompilé `StartTurnOperation.Execute @180ea3fb0` relu (re-dérivation post-compact) :
dans la boucle sur `PlayerComponent.GetCurrentlyOwnedUnitIds(joueurCourant)`, `*(int*)(unitComp+0x58) += 1`
par unité. Port (2 fichiers, mirror 1:1) :
- `engine/entities/stats.py` : `UnitStats.increment_base(stat_type, by=1)` — bump l'`initial` du
  `StatComponent` (compteur BRUT, PAS une ValueModification ; seede à 0 si absent).
- `engine/runner/operations/turnflow.py` : `_bump_turns_started(state, player)` (boucle unités vivantes
  du joueur courant -> `ctx.stats.increment_base(TURNS_STARTED, 1)`), appelé par `StartTurnOperation.execute`
  juste après le bump global.

VALIDÉ LIVE (`tests/engine/runner/test_turnflow_live.py::test_turnflow_turnsstarted_live`, 3/3 vert avec le
guard `test_getstat_live`) : stat-12 OFFLINE (runner Python après `EndTurnMessage`) == stat-12 LIVE d'un
`combatSnapshot` FRAIS pris après le MÊME endturn, sur toutes les unités communes (agreement non-circulaire) ;
le bump `+1` sur les unités du joueur entrant est exercé et confirmé (`ts1 == ts0 + 1`).

## Fichiers
- `scripts/python/engine/entities/abilities/active_ability.py` (ExecutionerAbility + registre).
- `scripts/python/engine/entities/stats.py` (StatType.TURNS_STARTED = 12).
- `frida/hooks/features/ai-step/rpc-snapshot.ts` (capteur `turnsStarted: 12`).
- probe : `scripts/python/probe_122_rounds.py` (scratch, non commité).
