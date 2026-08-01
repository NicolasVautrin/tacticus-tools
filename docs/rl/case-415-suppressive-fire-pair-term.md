# case-415 — le rouge de #124(b) accusait un terme de PAIRE manquant, pas le gate d'élévation

**Question, binaire.** `test_line_elevation_gate_decision_live::test_excruciating_frequencies_...`
échouait sur `(69, 79) != (69, 77)` — même ability, cible différente. Est-ce le **port** du gate
d'élévation (#124), le **montage** du test, ou le **harnais de collecte** ?

**Réponse : aucun des trois. C'est le PORT, mais sur un tout autre étage** — l'utilité de PAIRE, à
laquelle il manquait `SUPPRESSIVEFIRE_TargetWithOverwatch` (**+35**). Mesuré à l'oracle natif, puis
porté et confronté bit-exact.

## 1. Ce que le rouge n'était pas

Les **trois** assertions qui gardent le gate de #124 passaient déjà (`nat != 1197`,
`cands_gated == []`, `cands_free` non vide) : le gate d'élévation n'a jamais été en cause. Le montage
non plus — il installe exactement le régime qu'il vise (fenêtre aveugle `C3_59`, `P=(3,4)`,
`t2=(1,5)`, `t3=(0,5)`, voisinage 40 tuiles), et il l'installe encore aujourd'hui.

Ce que le test croyait avoir neutralisé, en revanche, était faux : son commentaire « profils
DISTINCTS » visait à briser le tie de cible, mais `--hp-target 600` **égalise** les deux profils
(600 PV, 600 de dégât, kill sûr des deux côtés). Le port voyait donc `pair` STRICTEMENT ÉGAL
(239.6678) sur les deux cibles — et c'est un autre terme qui tranchait.

## 2. La mesure qui tranche : l'oracle `pairUtility`

Le RPC `pairUtility` invoque le NATIF `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
depuis une tuile donnée. Sur l'état du test, aux trois tuiles testées :

| cible | visualId | natif | port (avant) | écart |
|---|---|---|---|---|
| 77 | `eldarRanger` (porte l'overwatch) | **274.6677740942687** | 239.6678 | **-35** |
| 79 | `astraBullgryn` | 239.66777409426868 | 239.6678 | 0 |

Le port sous-estimait la cible 77 de **35 exactement** = le poids
`Utilities.Default.TriggeredAbilities.SUPPRESSIVEFIRE_TargetWithOverwatch`. `emperNoiseMarine`
porte le trait `SuppressiveFire` ; `eldarRanger` porte l'effet `Overwatch_AutoAttack` (1009).

**C'est la seule voie qui pouvait conclure** : `CalculateActionUtility` n'a que trois termes
cible-dépendants — `pair`, `WireweaveNet_FirstAttack`, et le custom — les deux autres ne dépendant
que de la tuile. L'oracle isole donc exactement l'étage divergent, sans hook.

## 3. Le natif, lu

`IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` :

    tile   = case.CasterTile ; target = case@+0x20 ; value = 0
    if (EntityExtensions.HasEffect(target, State, (EffectType?)0x3f1, onlyActive: null))
        if (!query.AreEntitiesAdjacent(tile, target))          // slot IBattleQuery 0x60
            value = GetUtilityValue("SUPPRESSIVEFIRE_TargetWithOverwatch")
    yield return Fix64.FromInt(value)

Trois lectures qui ne se devinent pas :

1. **`0x3f1` = 1009 = `EffectType.Overwatch_AutoAttack`**, et `onlyActive` est le littéral `0` ⇒ le
   natif **ne consulte pas** `EffectComponent.IsActive @+0x5c`. Mirror = `EffectsState.has_effect`,
   surtout pas `active_effects` — l'inverse exact du choix fait pour `WireweaveNet_FirstAttack`,
   dont le call-site teste `Any(e => e.IsActive)`.
2. **Le prédicat est NIÉ** : le bonus n'est versé que si la tuile d'attaque n'est **pas** adjacente
   à la cible. C'est le bonus du **TIR**, et le nom de la clé ne le dit pas. Le slot `0x60` est
   identifié par son autre call-site, qui le NOMME (`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`) :
   `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles, unit)` =
   `MovementUtil$$AreTilesAdjacent(tiles, GetTiles(unit))`, donc la porte habituelle
   (`|Delta elev| < 2` ET `IsNeighbour`).
3. Le poids vient du **BC**, jamais codé en dur (délégué `TriggeredAbilityPlaybook<T>$$GetUtilityValue`).

## 4. Le correctif : deux câblages, aucun code neuf d'infrastructure

L'infrastructure existait (face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`,
`utilities/tile.py::evaluate_attack_in_steps`). Il manquait **les deux bouts de la chaîne** :

| ajout | fichier |
|---|---|
| le playbook (mirror du corps ci-dessus) | `engine/playbook/suppressive_fire.py` |
| son entrée au registre `TRIGGERED_ATTACK_PLAYBOOKS` | `engine/playbook/psyker.py` |
| `"SuppressiveFire": (1044,)` dans `TRAIT_TRIGGERED_ABILITY_IDS` | `engine/entities/triggered_ability_type.py` |

Le mapping trait `1010 -> 1044` est celui du registre runner `BEHAVIOUR_TRAIT_TRIGGERS` (#74) : une
source de vérité, deux faces. **Sans la 3ᵉ ligne le dispatcher n'itère jamais 1044** — c'est ce trou
qui coûtait les 35 points, et il vaut pour les **49** porteurs du trait, pas seulement ce montage.

## 5. Validation

* **Conformité bit-exact** : port `274.66777408637876` contre natif `274.6677740942687` (écart 8e-9,
  Fix64 vs float), et `239.6678` inchangé sur la cible sans overwatch, sur les 3 tuiles.
* **Le test de #124 redevient vert POUR LA BONNE RAISON** : la cible s'accorde désormais **avec ET
  sans** le terme `WireweaveNet_FirstAttack`, alors qu'avant le fix elle basculait selon lui. 2/2.
* **Garde neuve** — `tests/engine/test_415_suppressive_fire_pair_term_live.py`, 2 tests : (1)
  conformité port==natif tuile par tuile sur les DEUX régimes ; (2) **discriminance** — playbook 1044
  retiré du registre, l'écart au natif doit valoir **exactement** le poids sur les tuiles distantes
  **et rester nul au contact** (c'est ce qui garde le prédicat NIÉ). Un montage qui n'atteint pas les
  deux régimes ÉCHOUE, il ne skippe pas.
* **Mutation adversariale** : entrée `"SuppressiveFire"` retirée de `TRAIT_TRIGGERED_ABILITY_IDS`
  ⇒ la garde ROUGIT, écart mesuré `34.99999999554372`. Revert ⇒ verte.
* **Non-régression** (tests CIBLÉS, live) : `test_playbook_live` 3/3, `test_tile_term_triggered_playbooks_live`
  12/12, `runner/test_suppressive_fire_live` 4/4 (face COMBAT du même trait),
  `runner/test_psyker_splash_live` 1/1 (l'autre consommateur du dispatcher), `test_line_elevation_gate_decision_live` 2/2.
* **Cliquets** : la banque, `pwsh -File scripts/ratchets.ps1` — rc=0. La composition n'est PAS
  recopiée ici : ce fichier la définit (#430), et l'énumération qui figurait à cette place en
  citait 8 dont 4 **hors banque**. Ces quatre-là restent des probes hors banque, joués à part
  pour cette tranche et rc=0 : `probe_330`, `probe_321`, `probe_252`, `probe_va_in_code_vs_prose`.

## 6. Ce qui n'est PAS couvert

* **`WireweaveNet_FirstAttack` (-30) est TRANCHÉ par `case-415-r1`** — hors de ce cas, et il fallait
  un autre oracle : le terme n'entre **pas** dans `pairUtility` (il est sommé plus haut, dans
  `CalculateActionUtility`, au littéral `0x37`), donc l'oracle utilisé ici lui est structurellement
  aveugle. Le montage joué là-bas est celui décrit ici — deux cibles au `pairUtility` natif ÉGAL,
  une seule portant un filet armé — avec deux ajouts : le caster est ÉPINGLÉ (`Movement=0`, sinon le
  natif se déplace et la tuile retenue ne porte plus qu'une cible légale) et il n'a PAS
  `SuppressiveFire` (ce qui rend le second porteur d'overwatch inutile). **Verdict : le -30 mord, le
  port est conforme.**
* ~~**La face MOVE de `SuppressiveFirePlaybook`** a son propre corps, non porté et non lu.~~
  **RÉFUTÉ par #419 (PR #465)** : `SuppressiveFirePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
  est un `yield Fix64.FromInt(0)` **CONSTANT**, décompilé lu — il n'y a rien à y porter, et son
  absence du registre `TRIGGERED_MOVE_PLAYBOOKS` EST le comportement natif.
* **La divergence de TUILE**, elle, subsiste et est ANTÉRIEURE : le natif attaque depuis `(3,5)`, le
  port depuis `(4,4)`. C'est l'axe POSITIONNEMENT (proxy à plancher, résidu #124 §7 / #128 §6), hors
  du critère du test (ability + cible).
* **`probe_283_enum_ordinal_sweep.py` est ROUGE, et il l'était déjà** : il accuse
  `tests/test_additional_hits_variant_signatures_offline.py:187` (`On(0x3c)` : `UnitBecameTargetable`
  vaut désormais `UnitBlocked`), fichier **identique à `origin/master`** et étranger à ce cas.

## 7. Artefacts

| quoi | où |
|---|---|
| port | `scripts/python/engine/playbook/suppressive_fire.py` |
| câblages | `engine/playbook/psyker.py` (registre), `engine/entities/triggered_ability_type.py` (trait -> 1044) |
| garde | `scripts/python/tests/engine/test_415_suppressive_fire_pair_term_live.py` |
| probe de mesure | `scripts/python/probe_415_normal_attack_tie_order.py` (grille (tuile, cible), oracle `pairUtility`, A/B armé/désarmé) |
