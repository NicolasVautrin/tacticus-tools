# Case #44 — portage des 5 playbooks NonComparable du « lead 8 »

**Contexte** : suite directe du REFRAME de [`case-34-nonattack-oracle.md`](case-34-nonattack-oracle.md).
Les 5 abilities que l'étage agreement classait « non-attack-oracle » (l'oracle `aiPlaybookPredict` ne
rendait aucun `ProbableDamageEvent`) ne sont **pas** des émetteurs heal/effect : ce sont des
**playbooks NonComparable natifs** (`EvaluateNonComparable`, **aucun** `Make*Predictions`). Le
déblocage n'était donc pas un décodage d'événement mais un **portage de playbook**.

## 1. RE par playbook (décompilé = vérité)

Toutes les `MIN_UTILITY` viennent du `.cctor` du playbook et valent `Fix64.FromInt(1)` ;
`get_Priority` n'est surchargé par aucun playbook (#115) → `PRIORITY = 0` pour les 5.
Éligibilité commune = `BasePlaybook.GetEligibleTargetsSelectable @18111f0d0` =
`IBattleQuery` slot `0x41` `GetValidTargets(unit, UnitPosition(position), abilityType)` puis
`ListExtensions.Remove(<prédicat BasePlaybook>)` → **légalité PAR POSITION**, pas l'union des
tuiles de mouvement.

| id | playbook | `EvaluateNonComparable` | utilité |
|---|---|---|---|
| 1113 | `StormcallerPlaybook` | @181160ff0 | `GetTargetUtility @1811613a0` : `Fix64.Zero` puis **+1 par tuile de la zone de glace portant une unité** (`GetUnit(tile) != null`, **aucun** filtre d'équipe). Zone = `StormcallerAbility.GetAddIceTiles @18120cf70` = `AdjacentTiles(Target) + Target`. Gate par cible : `WillNormalAttackKill(target, position) → continue`. |
| 1121 | `ItItchesPlaybook` | @181146c50 | `Fix64.FromInt(Count(GetTargetUnits))` où `ItItchesAbility.GetTargetUnits @1811ec5e0` = `Enemies(Target + AdjacentTilesIntersection(caster, target))` = la cible + les ennemis adjacents **à la fois** à la cible et au caster. Gates : `IsDisplaceable(target) @180ed8140` puis `CanBePushed` (@181146aa0, slot `0x4d` + `FilterInPlace`, `Count > 0`). |
| 1151 | `TheQuickeningPlaybook` | @18116afb0 | paliers `+1` cumulatifs — base 1 ; gate `GetNumAttackTargetsInPosition(caster, targetTile) == 0 → continue` ; `+1` si un **ami** est sur la tuile ; `+1` de plus si `HasFaction(ami, faction(caster))` ; `+1` de plus si l'ami échangé peut attaquer depuis la position du caster ; `+1` si `HasTriggeredAbility(caster, 0x4df = FuryOfTheAncients)` **et** que la position évaluée ≠ la tuile courante. **Cible = entité TUILE.** |
| 1163 | `BlackRagePlaybook` | @1811211f0 | `PredictAttack` (slot `0x21`, attaque **NORMALE** du caster depuis la tuile de charge) → `ProbableDamageEvent` → `CalculateUtilityFromDamageEvent @1814a9f90`. Le coût en PV (50 %) n'entre **pas** dans l'utilité. |
| 1202 | `VigilanceEternalPlaybook` | @18117fae0 | `GetDamageFormula(position)` + `GetDamageProfile` + `GetHits` → `CalculateUtilityFromDamageEvent` (surcharge @1814aa3d0). |

`WillNormalAttackKill @18111fff0` = `PredictAttack` (slot `0x20`) →
`DamagePredictionResult.get_WillBeKill` = **sure-kill** (borne MIN ≥ PV) = `killSure` du composite.
À ne pas confondre avec `EnemyCouldBeKilledWithNormalAttack` (existe-t-il *un* ennemi sure-kill),
déjà porté pour HammerOfWrath.

## 2. Port

Un fichier par playbook dans `scripts/python/engine/playbook/noncomparable/` (`stormcaller.py`,
`it_itches.py`, `the_quickening.py`, `black_rage.py`, `vigilance_eternal.py`), fondations partagées
ajoutées dans `_base.py` :

- `_will_normal_attack_kill` / `_get_num_attack_targets_in_position` / `_normal_attack_ids` (mirrors
  homonymes des fonctions natives) ;
- `NCContext.plans` = plans de **toutes** les unités (le terme « l'ami échangé peut attaquer » de 1151
  interroge le plan d'un allié, pas seulement celui du caster) ;
- `_PlanTargetPlaybook.SWEEP_ALL_RANKED` : les playbooks à utilité **position-dépendante** (1163, 1202)
  balaient **toutes** les tuiles rankées de la paire (mirror du balayage de positions du generator
  natif restreint aux positions légales) au lieu de `ranked[0]`.

Les 5 noms sont ajoutés à `_NONCOMPARABLE_ABILITIES` (`entities/abilities/active_ability.py`) : la
mesure live (#34) montre que `MakeDamagePredictions`/`MakeHealPredictions`/`MakeEffectPredictions`
rendent **tous `null`** → aucun `ProbableDamageEvent` **affiché** (même loi que Gauntlets/Hammer,
#109). Conséquence : `make_damage_predictions` rend `[]` pour eux ; l'utilité de décision de 1202
appelle donc `generate_multi_hit_attack_prediction` **directement** (même contournement que
`make_hammer_wrath_events`), et celle de 1163 passe par l'attaque normale.

## 3. Mesure (agreement `--build --seeds 777,31337 --steps 20`, board MC1_67)

| | ability | move | prédiction |
|---|---|---|---|
| baseline #43 | 24/29 (3 « non-attack-oracle ») | 31/35 | 21/21 |
| 1113/1121/1163/1202 enregistrés, 1151 **hors registre** | **25/29** | **31/35** | 21/21 |

- **1113 Stormcaller** (31337 s11, u89 → cible 81) : **hit** — le miss est fermé.
- **1163 BlackRage** (31337 s12, u91) : la bonne ability est désormais émise, mais la **cible** reste
  fausse (natif 85, port 77 : utilités 40,3 vs 50,2) → miss `nc-pair`, à traiter comme un problème de
  **fidélité de prédiction par cible** (même famille que #40/#41), pas comme un gate manquant.
  `SWEEP_ALL_RANKED` (balayage de toutes les tuiles rankées au lieu de `ranked[0]`) **ne renverse pas**
  l'argmax → la divergence n'est pas positionnelle. **Hypothèse à vérifier** (non prouvée) : le natif
  prédit la charge **avec** le bonus de BlackRage (`+728 Damage when charging`, gameconfig), qui peut
  faire basculer u85 en `kill`/`killSure` (saut d'utilité) là où un flat +728 seul ne renverserait
  rien. Le port score l'attaque normale **sans** ce bonus.
- **1121 / 1202** : aucun porteur sur ces deux seeds → portés sur preuve décompilée, **non confrontés
  live** (à confronter sur un seed portant tyranParasiteOfMortrex / Tyrith).

## 4. Le point dur : 1151 TheQuickening — porte native NON RÉSOLUE

Mesure seed 31337 :

- **pas 5** — u81 à l'origine (5,8), 21 tuiles de move, `abilityTargets(81, 1151)` = **36 tuiles
  valides**, ability `usable = true`. Le **natif joue l'attaque NORMALE** (ab 69 → u95) et n'émet
  **pas** 1151. Or l'unique gate du décompilé (`GetNumAttackTargetsInPosition > 0`) passe pour de
  nombreuses tuiles, **dont (3,5)** — précisément la tuile d'où le natif attaque.
- **pas 15** — origine (3,5), 4 tuiles de move : le natif **émet** 1151 → tuile 52 = (4,4).

Comme toute NonComparable qui « sort » prime sur toute Comparable **par l'ordre des générateurs**
(`InitAbilityTypeLists @1810ed540`), le natif n'aurait **pas pu** attaquer au pas 5 si le playbook
avait produit une action. Il manque donc une porte (ShouldEvaluate ? usabilité runtime ? condition de
round / mouvement déjà consommé ?) **invisible** dans `EvaluateNonComparable @18116afb0` — la table des
symboles ne montre aucun `ShouldEvaluate`/`ShouldExecute` sur ce playbook.

Second point ouvert : l'utilité est **plate** (tous les candidats à 2.0 = base 1 + palier
FuryOfTheAncients) dès qu'aucune tuile cible ne porte d'ami → l'accord de **cible** se joue sur
l'**ordre d'énumération** (keep-first du Bucket), pas sur l'utilité.

→ Le playbook est **porté et documenté mais volontairement pas enregistré** dans `PLAYBOOKS` :
l'enregistrer produit un **sur-tir mesuré** au pas 5 (anti-pattern #31) et un miss d'ordre au pas 15.
Tâche dédiée ouverte pour le RE de la porte + de l'ordre d'énumération.

## 5. Écarts assumés (flaggés dans le code)

- **`GetUseProbability` (porte ALÉATOIRE)** non modélisée — le moteur offline est déterministe :
  1163 `@181121740` = `0.4` si les PV après usage (`GetHealthPercentageAfterUse @1811ba570`, ConfigVar
  0x26 = 50 %) < PV courants, sinon `1.0` ; 1121 `@1811477b0` = `Fix64.FromIntFraction(GetMaxNumUnitsAffected, 3)`.
  Même statut que ScarabSummon.
- **Slot `0x4d`** de `CanBePushed` (1121) non identifié (ce n'est ni `GetAdjacentTiles` = `0x4e`, ni
  `GetTilesBehind` = `0x53` — arités différentes) → porté par la **géométrie réellement exécutée**
  (`DisplaceUnitOperation` / `FindTileToPush @180e695e0` : un pas dans la direction caster→cible, tuile
  walkable et libre).
- **`IsDisplaceable`** : le FLAG runtime `HasFlag(unit, 0x19)` n'est pas lisible offline (énum de flags
  d'entité, distincte des traits gameconfig) → seuls les traits `Immovable(17)` / `Hulking(3)` /
  `BigTarget(1017)` sont testés.
- **`GetNumAttackTargetsInPosition`** porté via le plan natif (`attackPlans`) → vaut 0 pour un **allié**
  quand le contexte ne fournit pas son plan (bridge offline `state_bridge` ne peuple que l'unité
  active) : le 3ᵉ palier de 1151 dégrade à la baisse.
