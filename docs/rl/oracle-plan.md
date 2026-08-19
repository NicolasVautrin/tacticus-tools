# Plan — Claude-as-oracle (jouer mieux que l'IA du jeu) + distillation IL

Blueprint figé avant build (2026-06-14). Itéré sur plusieurs tours ; ceci consolide
l'archi, ce qui est déjà fait, et les phases. **Rien n'est commité ; on édite ce doc
ensemble avant de coder.**

## Objectif

`Claude + outils read-only + lookahead` comme **policy/oracle** :
1. **Prouver** que je joue mieux que l'IA gloutonne du jeu (qui a des angles morts —
   suicide overwatch [[project_overwatch_blindspot]], pas de coordination, pas de lookahead).
2. **Générer des démonstrations fortes** pour l'**imitation learning** ([[project_rl_objective_il_first]]).
   Recadrage clé : l'IL distille **Claude+outils** (meilleur que l'IA native), pas l'IA native.
   Je suis lent (minutes/battle) → rôle = **oracle/démonstrateur**, pas policy temps-réel.

## Architecture — « decision view » = merge de 4 couches (en Python)

| Couche | Contenu | Source | Nature |
|--------|---------|--------|--------|
| **gameconfig helper** | mécanique : units / abilities (effet+conditions chiffrés) / traits / damageProfiles | lecture directe du `gameconfig` (Python) | statique/version |
| **board helper + géométrie hex** | carte hex logique (col/row/TileId/élévation/jouable/spawns) + distance/voisins/portée hex | BC `Board.Tiles` + math moteur (Python) | statique/board |
| **`decisionView` RPC** | positions, HP, flags, effets de tile dynamiques (EffectType live), rankings d'attaque, danger zone | hooks TS live | dynamique/instant t |
| **wiki** | notes tactiques (persos/abilities/traits) + sémantique terrain | markdown écrit/enrichi par moi | l'irréductible |

Python joint le tout → **tout dans le même repère hex**, je raisonne en **vraie distance hex**.
**Pas de wiki mécanique généré** (ce serait une copie périmable du gameconfig) : helper en
lecture directe ; le wiki ne porte QUE le savoir non dérivable (tactique + sémantique terrain),
créé paresseusement par id.

## Modèle de jeu (acté)

- **1 seul agent suffit** pour self-play : boucle unique, switch par `currentTurnPlayer`.
  Équitable car battle **information parfaite** + **tours séquentiels par équipe** + j'**applique
  au fur et à mesure** → B réagit au board committé de A, aucune intention privée fuitée.
  Mitigation biais : raisonnement frais par tour.
- **2 agents = optionnel** : A/B de policies distinctes (moi vs IA native = duel miroir), ou
  indépendance adversariale stricte (sous-agent par camp via outil Agent), ou parallélisme.

## Déjà fait (NE PAS refaire)

- **Toolkit `frida/hooks/features/ai-step.ts`** (validé) : `aiStepDryRun`, `aiDryRunAllUnits`,
  `aiPlayByUnit`, `aiPlayOrdered`, `aiMovableTiles`, **`aiAttackRank`** (autonome : abilities
  concrètes auto-découvertes + tile courante incluse ; shrink-and-recall ; fidèle à la décision IA).
  Détails : `docs/rl/ai-step-toolkit.md`.
- **RE** : modèle d'abilities ([[project_ability_normal_attack_concrete]] — attaque normale =
  id concret par unité, pas 17) ; `GetBestTileToAttackFrom(unit,set,target,ability)` ; primitives
  AttackQuery ; `ActiveAbilityComponent` (NormalAttackType@0x28, GetActives) ; `GetMainTile(unit,state)`.
- **Spatial** : `hex.js` du front = math moteur (`HexUtils.GetTileWorldPosition`, hex flat-top
  **odd-q**, 6 voisins) ; calibration PNG↔pixel déjà résolue (`hex-calibration.js`).
- **Données** : gameconfig localisé = `AppData/LocalLow/Snowprint/Warhammer 40,000_ Tacticus/
  gameconfig/<hash>.json` (16 MB) → `clientGameConfig.units.{abilities(554),factions,npc,summons,…}`,
  `aiUtilities`, `globalValues.traitVariables`, `damageProfiles`. Terrain : BC `Board.Tiles[c].Tile[r]`
  = {TileId, Elevation, ForceUnplayable, RoomID, Rotation} ; effets dynamiques = `EffectType` live.

## Phases de build (chacune avec un gate de validation)

> **Avancement (2026-06-14)** : Phases 1 (spatial — `hexgeo.py`+`board.py`), 2 (mécanique —
> `gameconfig.py`), 3 (`decisionView` RPC : units/positions/flags/abilities + attackPlans rankés
> + toActivate) et **3.5 (DamagePrediction câblée : chaque tile rankée → dmg+kill)** FAITES &
> validées. Couche dynamique complète, ~240 ms, read-only. Restes : `dangerZone` (enemies
> TurnFinished → à calculer côté Python en Phase 4) ; gap sémantique traits/terrain → wiki.
> **Phase 4 (merge Python — `oracle.py`) FAITE** : carte décision unifiée (board hex +
> overlay units + danger zone géométrique 65/69 tiles + kits gameconfig + plans d'attaque
> avec dmg/kill). Toute la couche OBSERVATION (Phases 1-4) est terminée. Danger zone =
> conservatrice (ignore LoS/obstacles), raffinable. Prochaine : **Phase 5 — `applyAction`**
> (fermer la boucle : je décide → applique MoveUnitMessage/ActiveAbilityMessage → observe).

1. **Spatial** — `scripts/python/hexgeo.py` (offset↔cube, distance, neighbors, range/disk ;
   plus tard LoS) + `scripts/python/board.py` (BC → carte hex logique).
   *Gate* : distance/voisins == moteur ; carte == un board réel (recoupé avec le front).
2. **Mécanique** — `scripts/python/gameconfig.py` (localise par hash, load+index+cache ;
   `ability/unit/trait/damageProfile(...)` + cross-refs + carte compacte). *Gate* : cartes
   correctes sur un échantillon ; **localiser où sont définies les units individuelles**.
3. **`decisionView` (RPC TS)** — agrège le dynamique (units/abilities/attack-rankings/danger)
   en coords hex, intègre aiAttackRank. *Gate* : read-only, **un appel**, < budget freeze.
4. **Merge + oracle read-only** — Python compose la carte unifiée (4 couches) ; je raisonne
   et propose un plan de tour SANS appliquer. *Gate* : plan cohérent depuis une seule vue.
5. **`applyAction` (RPC TS) + boucle d'apprentissage** — je décide depuis (prédictions + kits +
   notes) → applique (`ApplyAiMessage`) sur le **runner réel** → **observe la conséquence réelle**
   → si surprise, j'**écris/maj une note tactique** (capture d'expérience). *Gate* : le coup
   atterrit ; la boucle observe-et-note tourne.
6. **Expérience A — duel miroir** : moi vs IA native, même seed. *Gate* : winrate + cas montré
   (éviter l'overwatch que l'IA mange). Si je bats l'IA → dataset « Claude+outils » prouvé supérieur.
7. **Self-play → dataset IL** (si A positif) : moi les deux camps, capture (état→action). Dataset
   = battles à **notes mûres** (les premières sont des battles d'apprentissage), ou décisions filtrées.

**PAS de clone/lookahead** (décision 2026-06-14 : trop lourd, inutile ici). On s'appuie sur :
conséquences **lues** (`DamagePrediction`, **danger zone** = reachability adverse read-only) +
**apprises** (notes). Le runner réel donne la conséquence gratuitement ; les notes accumulent
l'expérience qu'un lookahead aurait simulée.
**Optionnel/plus tard** : 2 sous-agents (indépendance stricte) ; effets de tile dynamiques
(decisionView v2) ; sémantique terrain dans le wiki.

## Décisions actées

- Logique lourde **batchée dans les RPC** (anti-freeze + moins de round-trips) ; Python = chef d'orchestre.
- **Merge en Python** (a déjà la BC + le gameconfig) ; RPC = uniquement ce que seul le live sait.
- **Helper, pas wiki généré** pour le mécanique ; wiki = notes tactiques + terrain, paresseux.
- Mécanique = **gameconfig** comme colonne vertébrale (effet + conditions chiffrées ; ciblage/déclencheur
  fin = enrichi depuis TargetingOptions/triggered + notes).
- **Hex, pas Chebyshev.** **Screenshot uniquement sur demande** de l'utilisateur.

## Questions ouvertes — statut

- **Q1 RÉSOLU** : units dans **`clientGameConfig.units.npc`** (480 défs complètes : name/FactionId/
  Movement/weapons/traits/activeAbilities/passiveAbilities/stats par rank) + **`units.lineup`**
  (héros jouables, ex. `custoVexilusPraetor`) + `summons`. Le helper `unit(id)` cherche les 3.
- **Q2 OUVERT** (→ Phase 2 / wiki) : sémantique terrain (Swamp/Water/glace/feu → effet gameplay).
  TileId statique connu (`Block/Bridge/DryBush/Grass/Swamp/Water`…) ; le « que fait chaque terrain »
  à sourcer (`globalValues`/configs d'effet/notes).
- **Q3 RÉSOLU** : **pas de clone/lookahead** (trop lourd, inutile ici — cf. décisions).
- **Q4 RÉSOLU (pour l'instant)** : **contraintes de temps abandonnées, priorité QUALITÉ.** Pas de
  pression de débit. Sync PvP ≈ 40 s/tour ([Goonhammer](https://www.goonhammer.com/drive-me-closer-i-want-to-hit-them-with-my-phone-pvp-in-warhammer-40k-tacticus)) → de toute façon c'est le **net IL distillé** qui jouera en temps réel, pas moi.
  Leviers de débit si besoin plus tard : sous-agents parallèles + démos correctives ciblées.

## Contraintes

- Build **kqkbjqfb6c** (RVA/dumps spécifiques). Anti-freeze : chunker / batcher (≤ budget main-thread).
- Cycle dev hooks : rebuild + `POST /api/admin/inject` + `autoBootExtraire({force:true})` (autonome).
- **Ne jamais commit de sa propre initiative.**
