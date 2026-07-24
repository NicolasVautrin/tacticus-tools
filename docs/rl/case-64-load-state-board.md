# case-64 — peupler `state.board` A LA SOURCE (`load_state(board=)`) : tuer la classe de bug #63

## Objectif
#63 a corrige PONCTUELLEMENT un seul site (`_combat_replay._do_replay` construisait un `Board`
sans jamais l'assigner a `state.board` -> feuilles positionnelles no-op silencieuses). Mais le
board etait re-pose A LA MAIN dans ~40 tests via un `state.board = board` disperse : un boilerplate
oubliable, exactement le vecteur du faux diagnostic "divergence armure 0.58". #64 supprime la classe :
le board est peuple UNE FOIS, a la source, dans `load_state`.

## Fix (point d'injection unique)
`engine/runner/snapshot.py::load_state` accepte un parametre optionnel `board` :

```python
def load_state(decision, observe, snapshot=None, board=None) -> State:
    state = State()
    ...
    if snapshot is not None:
        _load_stats_and_effects(state, decision, snapshot)
    if board is not None:
        state.board = board          # assigne en DERNIER
    return state
```

Chaque appelant qui posait `X = load_state(A, B, C)` puis `X.board = board` passe desormais
`X = load_state(A, B, C, board=board)` et supprime la ligne d'assignation.

### Pourquoi un OBJET `Board`, pas le boardGraph brut
Le mode d'adjacence du board (`evenq` vs `native_sym`) est CONSOMME par le moteur
(`board.neighbours`, `are_tiles_adjacent`, splash Psyker/plasma, tile-effects) et VARIE selon les
appelants (certains tests construisent `evenq`, d'autres `native_sym`, souvent le MEME objet leur
sert aussi au pathfinding). Construire le board dans `load_state` avec un mode fixe aurait change
le mode vu par le moteur pour une partie des tests -> regression potentielle. Passer l'objet exact
que le test a deja construit = preserver le mode = zero regression.

### Pourquoi c'est BIT-EXACT (equivalence par construction)
L'assignation est faite en TOUTE FIN de `load_state` (apres `_load_stats_and_effects`, qui n'a
jamais lu `state.board`). C'est donc strictement identique a un `state.board = board` que
l'appelant posait apres le retour de `load_state`. La transformation
`X = load_state(A,B,C); X.board = board` -> `X = load_state(A,B,C, board=board)` est semantiquement
neutre a chaque site. `board=None` (guard) == parametre omis == comportement historique (retro-compat :
`State.board` reste inscriptible, donc les probes et `rl_duel` non touches continuent de marcher).

## Bugs LATENTS decouverts (au-dela du boilerplate)
#63 n'avait corrige que `_combat_replay._do_replay`. Cinq tests de la tranche degat ont leur PROPRE
copie du helper `_replay` avec le MEME bug latent (board construit pour le pathfinding, jamais
attache au `state` du replay) :
- `test_damage_crit_live`, `test_damage_block_live`, `test_damage_decomp_live` : `_replay(..., board, ...)`
  recevait deja `board` mais faisait `load_state(...)` sans le threader.
- `test_guardian_organism_combat_live`, `test_nightshroud_combat_live` : `_replay` ne recevait meme
  PAS `board` (ajout du parametre + threading aux 2 call-sites).

Ces tests passaient parce que leurs positions de melee sont plates (elevation nulle -> bonus 0) ;
le bug etait donc invisible mais reel. Threader le board les rend fideles aux bonus positionnels
sans changer leur resultat (neutre si plat, correction sinon — jamais une regression, car le live
inclut deja l'elevation et les tests exigent off==live).

## Perimetre
- Touche : `snapshot.py` (+1 param) + ~58 fichiers de test (`tests/engine/runner/*`) + `_combat_replay.py`.
  ~90 sites `X.board = <board>` supprimes/threades (dont one-liners `; X.board = board; X.rng = ...`,
  closures `build_state`, helpers, inline `X.board = Board(bg["tiles"], ...)`, conditionnels
  `if board is not None`, dict-stored `cap["board"]`).
- 2 lignes redondantes supprimees : `st2 = *_env["build_state"](); st2.board = board` ou `build_state`
  posait deja le board (martial_apotheosis, harbinger_of_destruction).
- Commentaires perimes corriges : the_quickening / thunderous_assault disaient "load_state ne peuple
  PAS le board" (faux desormais).
- NON touche : les probes `probe_*.py` (one-shots non versionnes dans la suite, `state.board = board`
  y reste fonctionnel via l'attribut inscriptible) et le code moteur (aucun read de `state.board` modifie).

## Garde anti-regression
`tests/engine/runner/test_load_state_board_elevation.py` (OFFLINE, synthetique, deterministe) :
- `load_state(..., board=board)` sur un attaquant en surplomb -> `apply_elevation_bonus` arme un
  modificateur %-increase (feuille positionnelle FIRE).
- SANS board -> `state.board is None` -> feuille no-op fidele (mods inchange).
- `board=None` explicite == parametre omis.
C'est le verrou de la classe : si un futur changement re-casse le contrat load_state<->board, ce test
tombe sans dependre du live.

## Validation
- Collect-only sur tout `tests/engine/runner` : 239 tests collectes, ZERO erreur (tous les ~58 fichiers
  parsent/importent).
- Anti-regression offline : 3/3.
- Liste cible LIVE (tranche degat + consommateurs `_combat_replay` + latents) : 14 PASS —
  `test_damage_normal_armored`, `test_mkxgravis_combat`, `test_nightshroud_combat`,
  `test_guardian_organism_combat`, `test_psychic_fortress_aura`, `test_runner_attack`, `test_damage_roll` ;
  + crit/block/decomp : 8 PASS.
- Spot-run LIVE de patterns convertis divers : the_quickening (board->MoveUnit), gauntlets (one-liner+rng
  bit-exact), summon_trait_effects (board=None via guard), env_fire (board=None one-liner) : 7 PASS, 1 SKIP
  (skip pre-existant "aucun caster" = condition de build, en aval de load_state deja execute).

## Non couvert
- La suite complete `tests/engine/` n'est PAS rejouee live (trop lourd, doctrine projet). Les fichiers
  convertis non spot-runnes sont couverts par : (1) equivalence par construction (transformation neutre),
  (2) collect-only (0 erreur d'import/syntaxe), (3) py_compile. Un typo residuel de nom de variable n'est
  pas capte par py_compile/collect ; chaque site a ete lu avant edition ou transforme par regex verifiee
  en dry-run.
- `test_damage_decomp_live` depend d'un helper UNTRACKED (`scripts/python/tools/damage_decomp.py`, present
  seulement dans l'arbre principal) -> non collectable dans un worktree frais. Valide via junction tools/
  temporaire (retiree). Sur l'arbre principal (relecture orchestrateur) il collecte normalement.
