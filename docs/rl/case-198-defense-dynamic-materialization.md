# Case #198 — Axe DEFENSE : matérialisation DYNAMIQUE du stat-mod de tuile (enter/leave mid-sim) — SWAMP

**Status : PORTÉ + VALIDÉ LIVE (session 23, suite de #197). Le runner matérialise dynamiquement la
réduction DEFENSE de tuile en ENTRANT/SORTANT d'une tuile porteuse pendant le sim. Correction majeure de
RE : le terrain porteur est **Swamp** (−50 DEFENSE), PAS "Thorns" (premisse #194/#197 réfutée live). Marche
multi-terrain offline-vs-live : PORT == LIVE à chaque transition (Grass/Trench/DryBush = 0, Swamp = −50).**

## La correction RE : le terrain est SWAMP, pas "Thorns"
#194/#197 nommaient la tuile −50 DEFENSE "Thorns" (hypothèse : nom de l'ability `ThornsBlockMovementAbility`
-> terrain "Thorns"). **Réfuté live** : aucun board (779 scannés) n'a de tileDefId "Thorns" ; la tuile −50
DEFENSE de C2_19 (2,2) a `tileDefId == "Swamp"`. Marche multi-terrain (probe_198_map, jakhal traversant le
board) :

    terrain -> DEFENSE delta (live) : { Grass: 0, Trench: 0, DryBush: 0, Swamp: -50 }

⇒ Seule **Swamp** porte le stat-mod DEFENSE (−50, générique au tile-def). L'ability interne
`ThornsBlockMovementAbility` est assignée par la tile-config Unity au tile-def **Swamp** (description
localisée = `SwampBlockMovement @1809cdf10`) : elle fait block-entering (#131) + −50 DEFENSE. Le −50 et le
fold #194/#197 restent CORRECTS (ils lisent la stat DEFENSE, pas le nom du terrain) — seul le LABEL était faux.

## RE native (decompile-citée, build gqfc5mff6c) — inchangée
- `ThornsBlockMovementAbility.CreateBehaviour @1811c8d70` = `AddBlockEnteringUnitsEffect(0,0)` (block, #131)
  `&` `AddStaticStatModifierEffectToOwner(0xb, stat 3=DEFENSE, Direct(GetNumberConstant(config, 0x14)))`.
  `AddStaticStatModifierEffectToOwner @180de7860/@180de7750` -> `AddStatModifierEffectBehaviour`.
- `GetNumberConstant @181576af0` = `Int32.Parse(GetStringConstant(config, 0x14))` — Unity asset config
  (`IdunUniverse.GetTileConfigurations @1807a7d60`), ABSENTE du gameconfig (vérifié).
- `ThornsDefenseReductionEffect.CreateTargetSelector @180f47ea0` = `UnitsWithoutTrait(Units(tile,1,3),
  Immune=25)` -> réduction sur l'occupant NON-Immune de la tuile.
- LIVE `statModSources(occupant Swamp, defense)` : `total −50, bySource=[{source: 85, amount: −50,
  sourceIsUnit: false}]` — le jeu attribue le −50 à une ENTITÉ EFFET de tuile distincte (pas un lump).

## Design du port (on-move, `captured`-adjustment — sans build-time pass, sans toucher le seed partagé)
Découverte structurante : `seed_unit_stats` cuit le −50 d'une unité DÉJÀ sur Swamp au LOAD dans le lump
`CAPTURED_SOURCE` de sa `ValueModification` DEFENSE (le résidu inexpliqué par les effets nommés ; la face
prédiction #197 le lit tel quel, correct pour la position chargée). Le seeding `from_snapshot` est PARTAGÉ
prédiction+runner → on NE le touche PAS.

À la transition `from -> to` (`MoveUnitOperation.execute`), on ajoute au TOTAL DEFENSE la **différence**
`tile_defense_mod(to) − tile_defense_mod(from)` (0 hors Swamp). Comme la contribution de la tuile de départ
vit déjà dans `captured` (unité déjà-posée) ET que les unités entrantes n'y ont rien, ajuster `captured` de
cette différence maintient l'invariant UNIFORMÉMENT (déjà-posée comme entrante), sans re-keying ni pass au
build :
- ENTER (Grass->Swamp) : delta = −50 − 0 = −50 → `captured += −50` → DEFENSE −50.
- LEAVE (Swamp->Grass) : delta = 0 − (−50) = +50 → `captured += +50` → si résultat 0, `reverse_modification`
  (le gate `Current==Initial` du fold #197 rend alors ×1.0).
- Gate **Immune** (mirror `UnitsWithoutTrait`) : Immune -> aucune contribution (jamais appliqué, jamais retiré).
Le fold #197 (`calculate_modifiers_from_stat_modifications`) somme les sources ⇒ un `captured` ajusté reste
UN `EffectBonus` → composition inchangée, #194/#197 intacts (aucun MoveUnitOperation en prédiction).

## Fichiers
- `runner/operations/triggers/tiles.py` : `TILE_DEFENSE_STAT_MODS = {"Swamp": -50}` (HARDCODE Unity-asset,
  capté live, à re-capturer par-build — flaggé), `TILE_DEFENSE_EXCLUDE_TRAIT = Immune`, `tile_defense_mod`,
  `apply_tile_defense_on_move` (mirror apply-on-enter/revert-on-leave de `ThornsDefenseReductionEffect`).
- `runner/operations/movement.py` : `MoveUnitOperation.execute` capture `old_pos` avant l'écrasement et
  appelle `apply_tile_defense_on_move` (lazy import ; no-op si spawn/pc None / hors Swamp / Immune).

## Validation (probe_198_map, C2_19 seed 777, jakhal marchant — NE fait que bouger, survit)
À chaque tour de jakhal : move vers une tuile reachable, LIVE `combatSnapshot` DEFENSE vs OFFLINE
`MoveUnitOperation` depuis le MÊME snapshot pré-move. **PORT == LIVE à toutes les étapes** :

    Grass def=100 (OK) · Trench def=100 (OK) · Swamp def=50 delta=-50 (OK, ENTER)
    · DryBush def=100 (OK, LEAVE) · Trench def=100 (OK) · Trench def=100 (OK)

⇒ ENTER (Trench->Swamp 100->50), LEAVE (Swamp->DryBush 50->100) et les transitions hors-Swamp (no-op,
off==live) toutes fidèles. La conséquence combat (DEFENSE 50 -> ×1.5) est déjà #197 (le fold lit la stat
mise à jour). Offline logic test (probe_198_offline) : enter/leave/Immune/résidu-autre-source/no-op = 19/19.

## Famille (hors table = no-op fidèle tant qu'un board ne la mesure pas)
DryBush mesuré à **0** DEFENSE delta ici → le "DryBush_DefenseBonus"/"ShrubBonusDefense" (#126) n'est PAS un
stat-mod DEFENSE actif sur ce build (ou pas sur DryBush). SpiderWeb non rencontré. Ne JAMAIS deviner un
signe/constante : ajouter une entrée à `TILE_DEFENSE_STAT_MODS` dès qu'une valeur est CAPTÉE live.

## Anchors
ThornsBlockMovementAbility.CreateBehaviour @1811c8d70 (assignée au tile-def **Swamp**) ;
AddStaticStatModifierEffectToOwner @180de7860/@180de7750 ; GetNumberConstant @181576af0 ;
ThornsDefenseReductionEffect.CreateTargetSelector @180f47ea0 ; SwampBlockMovement desc @1809cdf10 ;
IdunUniverse.GetTileConfigurations @1807a7d60. Port : tiles.apply_tile_defense_on_move, MoveUnitOperation.
Probes : scratchpad probe_198_map.py (marche+diff), probe_198_diag.py (source/terrain), probe_198_offline.py.
Cf. case-197-defense-combat.md (consommation combat), case-194-defense-axis.md (fold prédiction),
terrain-effects.md §2.
