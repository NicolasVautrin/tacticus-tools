# Élévation (surplomb) — 3 axes distincts, ne PAS les confondre

> Finding coûteux (longue investigation live+RE, seed 777 gqfc5mff6c). **GREP ce doc avant de
> re-investiguer** tout écart d'élévation prédiction/combat/IA.

L'élévation intervient sur **trois axes indépendants** du moteur. Le piège (qui a coûté le rouge
`test_predict_live` u90→u86) est de **double-compter** l'élévation en l'ajoutant à la *prédiction de
dégât* alors que le natif ne l'y met pas.

| Axe | Ce que fait le natif | Où c'est porté | Statut |
|---|---|---|---|
| **1. Préférence POSITIONNELLE** (l'IA cherche le haut terrain) | `ElevationUtility` @1810efa20 (`UtilityType.Elevation=8`) : `u = Multiplier×elev (+HighestElevation si elev==max) (+LowestElevation si elev==min)`. BC `Utilities.Default.Elevation = {Multiplier:10, HighestElevation:10, LowestElevation:-5}`. | `engine/utilities/tile.py::ElevationUtility` (UTILITY_TYPE=8) | ✅ porté, fidèle |
| **2. PRÉDICTION de dégât** (preview que l'IA calcule pour classer ses moves) | **N'INCLUT PAS** le bonus d'élévation. `GetAllPredictions` (= oracle `decisionView`) est insensible à l'élévation de la tuile. | `engine/playbook/prediction.py::_add_positional_and_defender_mods` (élévation **retirée**) | ✅ retiré (#50) |
| **3. COMBAT réel** | **+50% appliqué** (surplomb), MÊLÉE **et** RANGED (ground truth jeu). `CalculateElevationBonusModifier @181003ea0` : `+ElevationPercentage` si `elev(tuile attaquant) > elev(GetMainTile(cible))`, gate `HasEffect(0x423)`. | `engine/runner/damage_model.py::apply_elevation_bonus` | ✅ appliqué |

**Conséquence tactique** : l'IA valorise l'altitude via un **proxy positionnel forfaitaire**
(`ElevationUtility`, ~+10/level), PAS via le calcul du dégât réel. Elle « sait » que le haut terrain
est bon sans anticiper le +50% exact. Un oracle qui **compterait** le dégât d'élévation pourrait donc
sur-jouer l'IA native en cherchant le surplomb (exploitable côté doctrine de jeu).

## Case study — le rouge u90→u86 (ce qui a déclenché l'investigation)

- u90 = **orksKillaKan** (MIENNE, team 1), attaque normale **RANGED** (Projectile, pierce 15) sur
  u86 = orksKillaKan (ENNEMIE, team 2) depuis la tuile candidate (5,4) elev **3**, cible (6,6) elev **2**.
- Le port ajoutait un **×1.5 fantôme** (candidate 3 > cible 2) : offline (3072,9037) vs oracle (2048,7592).
  Neutraliser l'élévation → offline (2046,7590) == oracle **exact**.

### Preuves ground-truth (immunisées à toute confusion)
- **`aiPredict`** (RPC = natif `GetAllPredictions` **direct**) : dmg u90→u86 **IDENTIQUE** à la tuile
  candidate élevée (5,4 elev3) ET à la tuile courante (3,2 elev2) = (2048,7592) → la prédiction native
  est **insensible à l'élévation de la tuile**. Idem u88 (tuile courante (4,4) elev2 > cible (6,7) elev1)
  = **aucun** bonus dans `decisionView`. → **axe 2 : pas d'élévation dans la prédiction.**
- **`tileMeta`** : tuiles (3,2)/(5,4)/(6,6) `effects=[]`, AUCUNE tuile "Trench" sur le board, u90/u86
  n'ont PAS d'effet 1059 → le gate `HasEffect(0x423)` n'est pas en cause (0x423 = **TrenchEffect**, effet
  d'**occupation de tuile-tranchée**, cf. `TrenchEffect @180f73fb0` / `TrenchAbility @1811c8e30` — RIEN à
  voir avec l'élévation ; piège d'enum : 1059="RammingSpeed" dans l'enum *ability*, ≠ EffectType Trench).
- **Pas une confusion de Kan** : les deux orksKillaKan sont distincts (id 90 team1 / id 86 team2) ;
  oracle et offline lisent le **même runner** par **entity-ID** (jamais visual_id) → cohérents.
- **BC** : `Utilities.Default.Elevation` existe (axe 1) ; `Utilities.MovementSuggestion` n'a **aucun**
  terme d'élévation.

### Piège de nommage (à retenir)
`CalculateAttackerModifiersForPrediction @181000590` est un **MISNOMER** : c'est le builder des modifiers
de **COMBAT** (inclut la feuille élévation `@181003ea0`), PAS ce que consomme le *preview* de l'IA
(`GetAllPredictions`). Cf. #58 "verdict RE cluster : misnomer ForPrediction". Ne PAS en déduire que la
prédiction IA calcule l'élévation — elle ne le fait pas (ground truth aiPredict ci-dessus).

## Règles réfutées (ne pas y revenir)
Sur des élévations **vérifiées live** :
- « candidate > cible » (ce que faisait le port) : réfuté par u90 (cand 3 > cible 2, oracle 0 bonus).
- « courant > cible » : réfuté par u88 (courant elev2 > cible elev1, oracle 0 bonus) + 5 samples.
- « min(courant, candidate) » : réfuté par le move-test (u90 déplacé RÉELLEMENT en (5,4), oracle inchangé).
- « melee-only / ranged-only » : réfuté — (a) RE : `@181000590` n'a AUCUN gate melee/ranged ; (b) jeu :
  l'élévation combat s'applique **mêlée ET ranged**.
=> aucune règle de tuile ne colle à la prédiction, parce que **la prédiction n'applique PAS l'élévation**.

## Validation du fix (#50)
`test_predict_live` **11/11** (u90 corrigé, 0 régression sur les 10 autres). Combat de garde
`test_runner_attack_live` + `test_damage_roll_live` **4/4** (axe 3 intact). Fix = prediction-only
(`_add_positional_and_defender_mods` ne touche que le preview ; `damage_model` et `ElevationUtility`
inchangés).
