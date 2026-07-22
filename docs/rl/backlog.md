# Backlog moteur RL — tâches ouvertes

> **Pourquoi ce fichier** : le tracker de tâches (outils `TaskCreate`/`TaskList`/…) vit côté
> compte, pas en local — il a disparu de la session le 2026-07-22 et rien n'en subsistait sur
> disque (aucun serveur MCP « task » déclaré dans les 4 portées de config, aucune base sous
> `~/.claude`). Ce fichier est le remplaçant **versionné** : il ne dépend d'aucune connexion.
> Les tâches TERMINÉES ne sont pas listées ici — elles ont leur `docs/rl/case-<n>-*.md`.

## Convention de tag modèle

Chaque tâche porte le modèle avec lequel la mener :

- **`[fable]`** — le cas a **déjà résisté** (divergence non localisée, verdicts contradictoires,
  flip-flop), le décompilé est **ambigu** (wrappers virtual-only, structure à trancher), ou il faut
  **concevoir des datapoints live discriminants**. En pratique : délégation à `fable-solver`
  (worktree isolé, livraison par PR).
- **`[opus]`** — l'artefact natif est **identifié** et la mécanique comprise (port 1:1, slice DSL,
  câblage d'un canal), **volume mécanique** (N overrides du même patron), ou orchestration /
  validation live / régression / doc / commit.

Tag mixte quand la tâche a deux temps (trancher la structure, puis porter) — l'annoter.

## Tâches ouvertes

| # | Tâche | Modèle | Point d'entrée |
|---|---|---|---|
| **#61bis** | Porter `MV71SniperDroneSquadAttack` (**1076**) — **tranches 1-2 LIVRÉES (2026-07-22), reste la tranche 3** | `[opus]` | Tranches 1 (exécution) + 2 (dispatch mêlée) livrées + validées live (`case-61bis-mv71-sniper-drone.md` §8 : 3 tests replay-diff, dégât bit-exact, tuile PickTile exacte via bucket Tile(7)+utilité 0x37, cap/éviction confirmés). **Reste : (3) prédiction distance** (`PredictAttack @18110a5f0` : config d'arme du drone + `StatAmount(caster, ATTACK)` + coups `1+ExtraHits(caster)` + canal additional-hits déjà porté + % Markerlight côté prédiction) + le dispatch normal-attack→1076 dans `visit_AttackUnitMessage` (`operations/damage.py:850`) pour les tours simulés. Point ouvert : 3ᵉ délégué `m860` (datapoint ExtraHits>0). |
| #35 | LordOfTempests `AddIce` (arbre DSL) | `[opus]` | Patron de slice DSL rodé depuis #149 ; artefact = `CreateBehaviour`. |
| #38 | DoctrinaImperatives `ReachedSummonCap` | `[opus]` | Prédicat/sélecteur scopé. |
| #39 | RE de la porte **per-player 1180** | `[fable]` | Asymétrie par camp constatée sans explication (`case-31`, mémoire `project_per_player_ai_asymmetry`) — profil « a déjà résisté ». |
| #27 | 25 overrides `CalculateCustomUtility` | `[opus]` | Volume mécanique → fan-out `re-expert`, **un item par agent**. |
| #5 | Chantier `DslContext` live-state | `[opus]` | Architecture à poser, pas d'énigme à trancher. |
| #20 | Roadmap AdMec | `[opus]` | Planification + découpage en tranches de port. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Coups post-mortem / dérive du flux MT** (`case-67` §5) : le natif cesse d'émettre les coups
  après la mort de la cible, `_run_hits` continue de tirer → dérive du PRNG après un kill
  mi-attaque en sim multi-actions. `[fable]` si ça remonte (divergence cross-cutting, se localise mal).
- **Bouclier × limites sur la voie ability** (`case-67` §5) : le natif cape le reste POST-part-bouclier,
  le port cape avant le split. Identique tant que `shield = 0`. `[opus]`.
- **`Impervious` (28)` / cap boss `0x5d4`** (`case-67` §5) : no-op documentés, porteurs = boss non
  spawnables en runner → **invalidables**, non portés (doctrine `feedback_no_unvalidatable_ability_ports`).
- **FireOfAbsolution, volet feu-sur-cible** (`case-67` §5) : vecteur after-hit probabiliste non
  modélisé par `execute()`. `[opus]`.
- **Flag=1 des caps heal/repair** (`case-60` §5) : aucun chemin natif identifié à ce jour ; la
  plomberie `group_limit` est en place, gatée OFF. `[opus]` si une ability « ne peut pas réveiller » apparaît.
