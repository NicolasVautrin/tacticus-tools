# Case #32 — les 3 cast-tiles résiduels (pos-downstream-of-ability) → move 100 %

**Contexte** : post case-49 (étage ABILITY fermé 35/35), le batch 777/909/31337 restait à move
48/51 avec 3 misses `pos-downstream-of-ability` : ability + cible matchées, seule la tuile de
cast diverge. Trois causes racines DIFFÉRENTES (une par miss) — diagnostic par la méthode 49f/49g
généralisée (`probe_32_casttile.py` : sweep engine par-tuile + pairUtility natif + L3 par-feuille).

| seed | step | unité | natif | engine (avant) | cause racine | statut |
|---|---|---|---|---|---|---|
| 31337 | 5 | u81 bloodMephiston | (3,5) | (3,6) | feuille move `FuryOfTheAncientsPlaybook` (1247) absente | ✅ portée (spec re-expert, EXACT) |
| 909 | 17 | u95 custoKyrus | (3,4) | (4,2) | ordre d'énumération des positions au tie (NC `_PlanTargetPlaybook`) | ✅ fixé |
| 31337 | 15 | u81 bloodMephiston | (4,5) | (3,6) | éligibilité par position hex-dist ≠ chemin natif (TheQuickening) | ✅ fixé |

**Batch final : prédiction 26/26 · utilité 26/26 · ability 35/35 · MOVE 51/51 — 4 étages à 100 %.**
Zéro régression (BloodyFury/Vexilla/Hammer/BlackRage/VigilanceEternal inchangés ailleurs).

## Miss 1 — 31337 s5 : feuille move FuryOfTheAncients (TriggeredAbilities Tile7)

Preuves (probe_32, s5) :
- La partie DÉGÂT matche à 6 décimales : `pairUtility` natif (69,95)@(3,5)=46.825989545322955 =
  notre `u` ; @(3,6)=38.166535180062056 = notre `u`. → seule la Tile(7) diverge.
- L3 par-feuille : tile (3,5) natif = Elev 20 + **TriggeredAbilitiesUtility 20.52660365588963**
  (nous : 20 + 0) ; tile (3,6) natif = Elev 20 + TileEffects 9 = 29 (nous : 29.0 ✓ exact).
- Totaux : natif (3,5) 46.83+40.53=87.35 > (3,6) 67.17 ; nous (3,6) 67.17 > (3,5) 66.83 → flip.
- Le champ `ability:"ForHonor"` des events L3 est un tag GLOBAL du tracer (présent sur toutes les
  feuilles, y compris Elevation) — PAS l'ability déclenchée évaluée. Ne pas s'y fier.
  **Cause tranchée le 2026-07-30 (#270)** : le tracer résolvait l'id **1** via
  `frida/hooks/data/ability-names.ts`, qui portait alors `1: "ForHonor"`. L'id 1 n'est PAS un
  membre d'`ActiveAbilityType` sur les builds mesurés — le champ tracé n'était donc pas un
  `ActiveAbilityType`, et la table lui collait un nom hérité d'un build antérieur. La table a été
  régénérée en #256 (260 entrées, plus de `1`), le tag ne peut donc plus produire ce libellé.

RE (décompilé, VAs) :
- `FuryOfTheAncientsPlaybook..ctor @181166940` : TriggeredAbilityType **0x4df=1247** (kit passif
  gameconfig de bloodMephiston → déjà dans notre enum + `triggered_ability_ids`).
- `CalculateMovementUtilityInStepsInternal @181166000` → iterator `d__1.MoveNext @181176570` :
  ennemis ADJACENTS à la tuile candidate (query slot via `DAT_18327ff80`+0x7d, playerId du
  case.unit) ; vide → yield 0. Sinon N=count, prob=Fix64(1/N), et pour chaque ennemi E :
  `u += GetDamagedEnemyUtility(case, E, 1/N)` puis second target
  (`DSLFactory.Get(E)` → `FuryOfTheAncientsAbility.GetSecondTargetSelector @180f82270` →
  `TargetsSelector.SelectUnit(…, 3)`) : `u += GetDamagedEnemyUtility(case, second, 1/N)`.
- `GetDamagedEnemyUtility @181166680` : `GetDamagePrediction @1811662a0` (level via
  GetAbilityState ; GetDamage 2×437-582 ; profil 0xd ; service DamagePrediction complet) →
  `ProbableDamageEvent(target, pred, prob)` → `TriggeredAbilityPlaybook<T>.
  CalculateUtilityFromDamageEvent` (gshared).
- Face attack déjà OK chez nous (pairUtility matche) — SEULE la face move manque.
- Sous-events L3 (composite Damage imbriqué dans la feuille) : 7.816778682172298
  (bloodDeathCompany) / 6.949208816513419 (thousAhriman) ; 7.82+6.95=14.77 ≠ 20.53 → composition
  exacte (prob/chaîne second) = objet du spec re-expert en cours.
- ⚠ Port : le dispatcher move `TriggeredAbilitiesUtility.evaluate` gate `not friends → 0` et
  `tile_leaf_ctx` ne porte que kit+fpos — Fury a besoin des ennemis + prédiction (scene). Le
  chemin NC (`NCContext` sans `.me`) est aussi muet — mais pour 1151 le +1 Fury est un PALIER
  INTERNE du playbook TheQuickening (pas la Tile7), donc seul le chemin Comparable/move importe.

**PORTÉ** (spec re-expert #32, réconciliation EXACTE 0 résidu) :
- Formule (`MoveNext @181176570`) : ennemis adjacents à la tuile (gate élévation) ; vide → 0 ;
  N=count, prob=1/N ; `total = Σ_E [GDU(E,1/N) + GDU(second(E),1/N)]` ; second(E) =
  `Friends(AdjacentUnits(E,1))` → `SelectUnit(…,3)` = premier ennemi vivant adjacent à E
  (à s5 : {91,95} mutuels → le ×2 annule le 1/N → total = c₉₁+c₉₅).
- Prédiction (`GetDamagePrediction @1811662a0`) = slot 0x23 : **montant PRÉDÉFINI
  avg(minDmg,maxDmg)[lvl PASSIF 50 × mult 180 → (599+797)/2=698], hits FORCÉS 1, spread 0**
  (comme Psyker) — PROUVÉ `probe_32d_fury.py` (matrice hits×canal : delta ~1e-8 sur les 2
  cibles ; hits=2 → ×2, canal plage [min,max] → −0.006). `nrOfHits`=2 = l'EXÉCUTION seulement.
- Implémentation : `engine/playbook/fury_of_the_ancients.py` (module homonyme de la classe
  native) ; registre `TRIGGERED_MOVE_PLAYBOOKS[1247]` ; signature dispatcher généralisée
  `calculate_movement_utility_in_steps(tile, ctx, wt)` (ctx = `tile_leaf_ctx` enrichi :
  uid/enemies/elev_by_pos/neigh_by_pos/scene/hpmax_by_id) ; gate `not friends` retiré de la
  feuille (chaque famille lit ses clés). Vérifié s5 : u_full(3,5)=87.3526 = total natif exact.

## Miss 2 — 909 s17 : ordre d'énumération au tie (`_PlanTargetPlaybook`)

Preuves (probe_32b_nc, s17) :
- u95 = custoKyrus (VigilanceEternal 1202 NC ; passif UnwaveringSentinel = effet counter-attack
  pur, AUCUN playbook IA — vérifié symbols ghidra).
- Notre utilité (1202, tgt 85) est IDENTIQUE **43.86721991701244** sur {(4,2),(3,4),(4,3),(3,3),
  (5,3),(5,5)} → tie pur. Ancien sweep = ordre `ranked` du plan → (4,2). Natif = (3,4).
- L'ordre du movable set natif (rows ncEvaluate = getMovableTiles) place (3,4) EN PREMIER parmi
  le tie set. Pour tgt=77 (max 32.12) l'ordre movable donne aussi (3,4). → keep-first natif dans
  l'ordre POSITIONS, pas l'ordre ranked.

Fix (`engine/playbook/noncomparable/_base.py::_PlanTargetPlaybook.generate_candidates`) :
- sweep POSITION-OUTER dans l'ordre BRUT `ctx.reach_nc` (tuiles de move ordre natif, puis origine
  EN DERNIER — #76/#80), cibles inner dans l'ordre du plan, gate `P ∈ ranked(tgt)`,
  remplacement strict `>` (mirror `<GenerateActions>d__7 @18119a3f0` + `Bucket.AddAction
  @1813fbcc0` keep-first). `SWEEP_ALL_RANKED` supprimé (obsolète : les playbooks
  position-indépendants retombent naturellement sur la 1re position légale de l'ordre movable).

## Miss 3 — 31337 s15 : éligibilité par position = chemin natif, pas hex-dist (TheQuickening)

Preuves (probe_32b_nc + probe_32c_castfrom, s15) :
- Tie util=3.0 chez nous sur positions {(3,6),(4,5),(2,4),(2,5)} → tuile 52=(4,4) (u79
  custoBladeChampion, allié non-BloodAngels : 1 base + 1 friend + 1 fury). L'ordre movable natif a
  (3,6) AVANT (4,5) → l'ordre seul n'explique PAS le choix natif (4,5).
- `castFromTiles(u81, tgt=52, 1151)` natif : `currentValid=True, moveTiles=[(4,5)]` SEULEMENT —
  (3,6)/(2,4)/(2,5) sont des cast ILLÉGAUX natifs (« movement range 2 » = distance de CHEMIN,
  `GetInvalidTargetReason` par tuile). Le natif n'a donc PAS de tie : origine(2) vs (4,5)(3).

Fix (`engine/playbook/noncomparable/the_quickening.py::generate_candidates`) :
- éligibilité par position via la seam native `ctx.cast_from_tiles(uid, tile_id, 1151)`
  (= castFromTiles RPC) : posset = moveTiles ∪ {origine si currentValid} ; fallback hex-dist ≤ 2
  conservé si la seam est absente (comportement pré-#32).

## Probes (scripts/python/)

- `probe_32_casttile.py` — générique (seed/stop/uid/tiles) : chunk natif, sweep engine par-tuile
  (mirror _best_attack sans argmax), pairUtility natif, L3 par-feuille sur tuiles d'intérêt.
- `probe_32b_nc.py` — NC : ncEvaluate natif par position (bucket décodé) + notre
  `generate_candidates` en debug + `evaluate_non_comparable` par tuile rankée.
  NB : bucket `null` partout observé pour 1202/1151 hors décision native (wrapper non amorcé) —
  les utils natifs par position sont alors indisponibles ; passer par castFromTiles/L3.
- `probe_32c_castfrom.py` — éligibilité native par position (castFromTiles) pour 1151 au s15.

## Résiduels ouverts (hors périmètre #32, tâches créées)

- **Fury face ATTACK — RÉSOLU (#51, verdict re-expert)** : c'est le **no-op de base**
  `TriggeredAbilityPlaybook<T>.CalculateAttackUtilityInStepsInternal @18150f4c0` (iterator
  `d__37.MoveNext @18134e990` : yield unique `Fix64(0)`) — Fury n'override QUE la face move
  (~60 autres concrets overrident la face attack, Fury n'y figure pas). Chaîne attack :
  `<EvaluateAttackInSteps>d__0 @1810f6a50` → `<EvaluateAttackInStepsInternal>d__3 @1810f64b0`
  → slot 3 `CalculateAttackUtilityInSteps @18150f530` → vslot 0x1e8 (base). Discriminant live
  31337 s5 tuile (3,5) (2 ennemis adjacents, move-Fury=20.53) : `pairUtility` natif = `u`
  offline SANS terme Fury attack à 9 décimales → terme attack ≡ 0. **L'absence de 1247 dans
  `TRIGGERED_ATTACK_PLAYBOOKS` est le mirror fidèle — ne rien ajouter.** Les sous-valeurs L3
  7.8168/6.9492 = artefact d'attribution du tracer (comme le tag `ability:"ForHonor"`).
- **Second-target multi-adjacent** : le déterminisme de `SelectUnit(…,3)` quand E a ≥ 2 ennemis
  adjacents (ordre d'énumération des tuiles adjacentes de E) — non liant à s5 (1 seul), port =
  ordre `neigh_by_pos` natif, à valider si un cas multi-adjacent apparaît.
- **Gauntlets arc ring-2** (finding validator, case-49 réouvert) : cf. tâche dédiée — le natif
  compte l'arc sur C1_25 (2 ennemis dist-2, floor 2, util native 2) alors que le port ring-1 rend
  0 ; contradictoire avec s14/49c (MC1_67). Hors périmètre #32 (n'affecte pas le batch MC1_67).
