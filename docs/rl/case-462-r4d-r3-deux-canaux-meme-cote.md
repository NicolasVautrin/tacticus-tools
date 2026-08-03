# #462-r4d-r3 — les DEUX CANAUX du MÊME côté, en COMBAT : **port CONFIRMÉ**

Le régime jamais exercé — face DÉFENSEUR portant SIMULTANÉMENT un `EffectBonus %` (liste `@0x18`)
et une modification de stat DEFENSE (`Multiplier@0x30`) — est **monté, confronté et bit-exact**.
Le port est le **SEUL** des cinq compositions envisageables à reproduire le natif.

Ce que le résidu appelait « montage écrit mais qui ne s'installe pas » n'était pas géométrique :
c'était un **prédicat faux** dans le probe. Détail au §4 — c'est la partie la plus réutilisable.

## 1. La RE, relue sur le build courant

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, décompilé relu
verbatim. Offsets confirmés sur la copie locale de chaque `Nullable<DamageModifiers>` :

| champ | offset | ce que le corps en fait |
|---|---|---|
| `Piercing` | `@0x20` | passé SÉPARÉMENT par face à `GetBaseDamageWithFixedPiercedArmor` |
| `ArmorPenetration` | `@0x28` | **SOMME** des deux faces (`Fix64.op_Addition`) avant l'appel |
| liste | `@0x18` | slot `0x11` = `ApplyCappedModifiers` — étape 1 (att) puis 2 (def) |
| `Multiplier` | `@0x30` | slot `0x10` = `CalculateBaseDamageWithModifiers` — étape 3 (att) puis 4 (def) |
| `Override` | `@0x00` | `Nullable<Fix64>` du DÉFENSEUR seul, court-circuite le retour |

Les quatre étapes sont gatées **uniquement** par le `HasValue` de leur `Nullable`, jamais par la
neutralité du multiplicateur. Rien de neuf par rapport à #462-r4a — relu parce que ce régime met
les étapes **2 et 4 sur la MÊME face**, ce qu'aucune mesure n'avait séparé.

## 2. Le montage, et pourquoi celui-là

`necroDestroyer` (mêlée, 6 coups, perçage 60) contre `custoTrajann` **seul** (armure 2510), conduit
sur une tuile Swamp de `MC1_67`. Les deux canaux du défenseur y sont alors alimentés par des
sources **indépendantes** :

* `MartialKatah` — `IdunBattle.Entities.Effects.Loki.MartialKatah_DmgReductionEffect$$CreateDamageModifier`
  = `ForPercentDecrease(20)` gate `IsNormalAttack` → un EFFET, donc la **liste `@0x18`** ;
* `Thorns_DefenseReduction` — posé sur la tuile par
  `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour`
  (`AddStaticStatModifierEffectToOwner`), `-50` négé par
  `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` → `×1.5`
  dans **`Multiplier@0x30`**.

L'aura `Nightshroud` d'`astraPrimarisPsy` du montage #462-r4d est **écartée à dessein** : sa
`ForSubtraction` plate ajouterait un troisième canal et brouillerait l'attribution.

L'attaquant est placé sur une tuile de **même élévation** que la Swamp — sinon son bonus
positionnel rouvrirait la face attaquant, et le régime ne serait plus « deux canaux du même côté ».

**Le probe REFUSE de mesurer** si le régime n'est pas installé : `pct_list` défenseur non vide,
`multiplicative != 1.0`, **et** stat-mod DEFENSE visible LIVE (`statModSources` → `-50`). Un bras
amputé d'un canal ne prouverait rien.

## 3. La mesure — les bornes NATIVES, inversées, contre cinq modèles écrits

Oracle : les bornes du tirage **inversées à état PRNG connu** (`solve_bounds`, aucune inférence) —
la soustraction `live − off` ne mesure rien ici, le coup étant un modulo. Modèles ÉCRITS, jamais
monkeypatchés :

```
A  liste @0x18 (etapes 1+2, UNE chaine) PUIS Multiplier@0x30 (etapes 3+4)   <- le port
B  les deux canaux FUSIONNES dans la meme liste
C  ordre INVERSE : multiplicateur d'abord, liste ensuite
D  une seule chaine multiplicative, UN SEUL Round final
E  un Round intercale entre les faces de la LISTE (la regression #446-r2)
```

| stat DAMAGE | face ATT | NATIF | OFFLINE | modèles en accord |
|---|---|---|---|---|
| 861 | neutre | **(497, 744)** | (497, 744) | **A seul** |
| 866 | neutre | **(500, 749)** | (500, 749) | **A seul** |
| 876 | neutre | **(504, 756)** | (504, 756) | **A seul** |
| 900 | neutre | **(519, 777)** | (519, 777) | **A seul** |
| 884 | neutre | (509, 764) | (509, 764) | A, B, C, D, E — **témoin** |
| 910 | neutre | (524, 786) | (524, 786) | A, B, C, D, E — **témoin** |
| 906 | neutre | (522, 783) | (522, 783) | A, B, D (C réfuté) |
| 906 | **×1.50** (élévation) | **(783, 1175)** | (783, 1175) | **A seul** (B, D → 1174 ; C → 1174 ; E → **1173**) |

Le point nominal est en outre bit-exact **per-coup** : `[693, 527, 715, 575, 687, 752]` des deux
côtés, **6 tirages PRNG** natif comme port (le flux n'est pas désynchronisé).

Deux choses que ce tableau tranche, et qu'aucun point isolé n'aurait tranchées :

1. **Les deux témoins** sont ce qui donne son sens aux quatre cas. Sur `884` et `910` les CINQ
   compositions rendent la même chose : un vert y est **gratuit**. Ils sont gardés comme tels.
2. **La dernière ligne** est la plus riche du corpus — TROIS entrées sur le même coup (liste
   attaquant `×1.50` **plus** les deux canaux défenseur) — et c'est la seule où la borne HAUTE
   sépare les cinq modèles, `E` compris. Elle vient du montage `--thorns` réparé au §4.

## 4. Pourquoi le montage « ne s'installait pas » — un prédicat faux, pas une géométrie

`probe_462d_nightshroud_stage_diff.py --thorns` sélectionnait ses tuiles ainsi :

```python
want = [... for t in rows if "Thorns_DefenseReduction" in (t.get("effects") or [])]
```

`tileMeta.tiles[].effects` est une liste de **DICTS** (`{name, effectType, source, remaining,
level}`), pas de chaînes. Le test d'appartenance était donc **toujours faux**, `want` restait vide,
et le probe rendait « aucune tuile Thorns marchable atteinte » — ce qui s'est lu comme une
impossibilité **géométrique**, puis a été écrit tel quel dans le résidu.

Mesure : `MC1_67` porte **4 Swamp** — `(1,3)` elev 4, `(1,6)` elev 2, `(4,6)` elev 1, `(5,3)`
elev 4 — chacune avec `BlockEnteringUnits` **et** `Thorns_DefenseReduction`. Le prédicat corrigé,
le placement réussit **du premier coup** (cible en `(1,3)`, attaquant en `(2,3)`, même élévation),
et `--thorns` rend `VERDICT: BIT-EXACT`.

Un zéro d'outil n'est pas une preuve d'absence — c'est la même forme que le `unit_map --ability`
de #323.

Deuxième faux négatif, dans l'ATTESTATION cette fois : interroger `defender_modifiers` **sans**
`is_normal_attack=True` rend une `pct_list` vide, parce que `MartialKatah` est gaté `IsNormalAttack`.
Le vecteur COMBAT (`damage_ops/normal.py`, #112) passe ce flag ; une attestation qui l'oublie
conclut « régime non installé » sur un coup qui porte pourtant le `×0.8`.

## 5. Contre-épreuves du cran — et l'une d'elles est INERTE, ce qui se dit

| mutation de `AttackDamageOperation._apply_defender_flat_reductions` | effet sur le cran |
|---|---|
| le `Multiplier` défenseur reparti dans `pct_list_defender` (= modèle B) | **10 failed / 15 passed** |
| le déplacement du `Multiplier` **supprimé** (`if False`) | **1 failed** — le seul test structurel |

La seconde ne déplace **aucune cellule** : sans déplacement, `apply_all_modifiers(def_mods)` en aval
applique le même `×1.5` au même moment, parce que la `%-list` défenseur a **déjà matérialisé un
entier** à l'étape 2. C'est une **borne du régime**, pas une faiblesse du fix — la nécessité du
déplacement se mesure sur « deux FACES » (#462-r4a), que `test_446_r2_inter_face_rounding_offline`
garde. D'où le test structurel dédié (`test_le_pont_deplace_les_deux_canaux_et_vide_la_source`),
qui garde le **contrat** là où les cellules sont aveugles.

## 6. Ce qui n'est PAS couvert

* **Le résidu `#462-r4d-r1` reste ouvert, et ce régime ne peut pas le fermer.** Il ne sépare pas
  « `attackModifiers` NULL en combat » de « présent à multiplicateur neutre » : après l'étape 2 la
  valeur est déjà ENTIÈRE, donc l'étape 3 est un no-op **qu'elle existe ou non**. À écrire comme
  BORNE, jamais comme confirmation.
* **Le `Multiplier@0x30` de la face ATTAQUANT** reste sans producteur (gate `apply_stat_mod_debuff`
  #49) : l'étape 3 à multiplicateur non neutre est toujours **NON CONFRONTÉE** (résidu #462-r4a).
* **La liste CAPÉE `@0x18`** : aucun `EffectBonus` porté ne pose de `cap`, `Clamp` jamais exercé
  (résidu #446-r2-r1, inchangé).
* **La face PRÉDICTION du même régime** n'a pas été confrontée séparément : elle partage le foyer
  `apply_pierce_and_modifiers`, mais ses étapes 3 et 4 y sont INCONDITIONNELLES, ce qui n'a pas été
  mesuré ici. Canal qui la confronterait : `aiPlaybookPredict` sur la cible posée sur la Swamp.

## 7. Livré

* `scripts/python/probe_462_r4d_r3_two_channels_defender.py` — montage, attestations refusantes,
  inversion des bornes natives, `--sweep` (déplacement de la fraction du perçage), `--models`
  (les cinq compositions, offline, sans runner).
* `scripts/python/probe_462d_nightshroud_stage_diff.py` — prédicat de sélection des tuiles corrigé ;
  `--thorns` fonctionne et rend `BIT-EXACT`.
* `scripts/python/tests/engine/runner/test_462_r4d_r3_two_channels_defender_offline.py` —
  **25 passed, 2 skipped en 1,4 s** ; verrouille les 8 cellules natives, le contrat du pont, la
  fractionnalité du perçage (sans quoi les lignes ne verrouilleraient rien), et **garde les témoins
  comme témoins**.

Aucun fichier d'`engine/` n'est modifié : le port était déjà juste sur ce régime, et c'est ce que
ce dossier établit.
