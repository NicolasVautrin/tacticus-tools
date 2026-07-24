# case-63 — "divergence armure 0.58" = ELEVATION manquee (state.board non charge dans le replay)

## Symptome rapporte
Attaque NORMALE non-Psychic sensible a l'armure : degat OFFLINE (replay-diff) ~0.58x le LIVE
(offline TROP BAS). Attaques Psychic (pierce 100, armure ignoree) = bit-exact. Mesure fortuite
pendant le port PsychicFortress : necroDestroyer (Gauss) et templHelbrecht (Bolter) contre une
cible sans effet (Apothecary). Hypothese initiale : bug dans l'etage ARMURE/PERCAGE du chemin
attaque.

## Verdict : hypothese armure/percage REFUTEE — c'est l'ELEVATION
La decomposition PAR ETAGE (off vs live) montre que l'etage armure/percage est **fidele**. La
divergence vient du bonus d'ELEVATION (+`ELEVATION_BONUS_PCT` = 50% quand l'attaquant surplombe la
cible), applique par le combat natif AVANT percage/armure, et **omis offline** parce que le harnais
de replay-diff `_combat_replay` ne peuplait pas `state.board`.

### RE (decompile = verite)
- Etage armure natif : `GetBaseDamageWithFixedPiercedArmor @181030d10` lit `GetStat(target, 0x10)` =
  FIXED_ARMOR(16), calcule pierce = clamp(0/1..100, `GetPiercingRatio(profil) @181559a40` + ExtraPierce
  stats), puis `GetDamageWithPiercing(dmg, pierce, armor) @1815598b0` =
  `max( max(0, dmg - armor), dmg * pierce/100 )`. Le port offline (`static_battle_rules.get_damage_with_piercing`,
  `damage_prediction.apply_pierce_and_modifiers`, `damage_model.defender_fixed_armor`,
  `battle_query.select_weapon_pierce`) est un **mirror 1:1** — verifie bit-exact.
- Bonus elevation : `CalculateElevationBonusModifier @181003ea0` = +ElevationBonus si tuile attaquant
  plus haute. C'est une **feuille positionnelle** du builder attaquant partage
  `CalculateAttackerModifiersForPrediction @181000590` que le COMBAT applique aussi (misnomer
  "ForPrediction"). Port : `damage_model.apply_elevation_bonus` -> `calculate_elevation_bonus_modifier`
  (ELEVATION_BONUS_PCT=50, section Damage de la BC). Requiert `state.board` (elevations des tuiles).

### Mesure par etage (positions DRIVEES, ranged, cible ultraApothecary armure 2208, board MC1_67)
| attaquant | arme | pierce | a_elev | t_elev | off_ph (sans board) | live_ph | ratio |
|-----------|------|--------|--------|--------|---------------------|---------|-------|
| necroDestroyer | Gauss | 60 | 4 | 3 | [514,582,514,578,642,603] | [968,902,928,884,658,797] | 0.668 |
| templHelbrecht | Bolter | 20 | 4 | 3 | [263,260,282] | [463,506,422] | 0.579 |

1/1.5 = 0.667 (+50% elevation applique par live, manque offline). L'offline `off_ph` de necroDestroyer
est IDENTIQUE en melee (pathfinding, positions plates) et en ranged drive -> l'offline board-less
n'applique AUCUN bonus positionnel. **Test decisif** : re-mesure avec `state.board` charge ->
off_ph == live_ph BIT-EXACT des deux cotes (ratio 1.0), pour pierce 60 ET pierce 20.

### Le "Psychic bit-exact vs non-Psychic 0.58" etait un CONFOND
La mesure Psychic (test PsychicFortress) utilisait des positions PLATES (POS_RING1/RING2, meme
elevation) -> pas de bonus elevation -> replay board-less bit-exact. La mesure non-Psychic utilisait
des positions a relief (attaquant en surplomb) -> bonus manque. Le discriminant n'etait donc PAS
pierce-100-vs-armure mais **positions-plates-vs-surplomb**. Le pierce 100 masquait juste l'armure,
il n'a jamais ete la cause.

## Cause racine (une ligne)
`_combat_replay._do_replay` construisait deja un `Board` (pour le pathfinding) mais ne l'assignait
JAMAIS a `state.board` -> `load_state` laisse `state.board=None` -> `apply_elevation_bonus` (et
trench/terrain LightCover/GetStuckIn/auras positionnelles) = no-op offline. C'etait le SEUL
consommateur de `load_state` a construire un Board sans l'assigner (les ~40 autres tests posent
explicitement `state.board = board`).

Le runner Python offline n'est utilise QUE par les tests/probes (validation replay-diff) ; aucune
rollout RL production ne passe par lui (la RL pilote le runner LIVE in-game par RPC). La divergence
etait donc confinee au harnais de replay, PAS un bug moteur.

## Fix
- `tests/engine/runner/_combat_replay.py::_do_replay` : `state.board = board` (le Board deja recu).
  Rend le replay fidele aux bonus positionnels. Ajout du helper `replay_attack_driven` (positions
  drivees + surplomb, charge le board) pour exercer l'elevation.
- `tests/engine/runner/test_damage_normal_armored_live.py` : nouveau
  `test_normal_attack_ranged_from_elevation_bitexact` (parametre necroDestroyer Gauss / templHelbrecht
  Bolter) — VERROU : tir armor-sensitive depuis un surplomb, exige off_ph==live_ph + armor>0 +
  a_elev>t_elev.
- `tests/engine/runner/test_psychic_fortress_aura_live.py::_measure` : charge aussi `state.board`
  (meme gap latent ; positions plates => passe deja, mais robustifie).

## Validation
- Probe unique (`probe_63_verify.py`, state-file dedie) : melee necroDestroyer->necroOverlord reste
  bit-exact ; ranged surplomb necroDestroyer (p60) ET templHelbrecht Bolter (p20) -> bit-exact APRES fix.
- pytest cibles (18 tests, tous PASS) : `test_damage_normal_armored_live` (melee + 2 ranged-elev),
  `test_psychic_fortress_aura_live` (2), + zero-regression sur les 3 autres consommateurs de
  `_combat_replay` (mkxgravis/nightshroud/guardian_organism) et les gardes de tranche
  (runner_attack, damage_roll, crit, block).

## Non couvert / residu
- Le fix corrige le HARNAIS de replay-diff (fidelite positionnelle). L'etage armure/percage du moteur
  etait deja correct ; aucune modif de `damage.py`/`damage_model.py`/`damage_prediction.py` requise.
- Autres feuilles positionnelles (trench, terrain LightCover, GetStuckIn) beneficient AUSSI du board
  charge mais ne sont pas re-testees ici (hors perimetre #63 ; elles ont leurs propres tests qui
  posent deja `state.board`).

## Suite
`case-64-load-state-board.md` : le `state.board = board` disperse dans ~40 tests (ligne 51) est
supprime au profit d'un point d'injection UNIQUE `load_state(..., board=board)`, tuant la classe de
bug. Y sont aussi corriges 5 helpers `_replay` copies (crit/block/decomp/guardian/nightshroud) qui
avaient le MEME gap latent que `_do_replay` (board non attache).
