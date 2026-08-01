# case-418-r1 — `IsEffectTarget` : la liste de CIBLES d'une aura, et le gate qui ne fermait jamais

**Question, binaire.** Le nœud `IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)`
rend-il, sur chacun de ses call-sites portés, exactement ce que rend le natif ?

**Réponse : NON avant cette tranche, sur le call-site `PsykerExtraAttackAbility`.** Le port y lisait
« l'unité PORTE l'effet », le natif lit « l'unité est CIBLE de l'effet ». Écart mesuré live : le
splash « Smite » du trait Psyker infligeait **1506 de dégât Psychic que le natif n'inflige pas**, dans
tous les cas où il est censé être supprimé. Corrigé, confronté sur 3 régimes géométriques, gardé par
5 tests, éprouvé par 3 mutations adversariales.

## 1. Ce que le nœud lit — la chaîne, relue en entier

`DSLTriggers$$IsEffectTarget(sel, effectType)` construit un
`IdunBattle.Entities.Triggers.IsEffectTargetTrigger`. Son `$$ShouldTrigger` résout le sélecteur
`+0x10` (`SelectSingle`) puis invoque le **slot d'interface** `+0x20` avec
`(entity, effectType@+0x18, onlyActive = 0)`. Ce slot est
`IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget`, dont le corps :

    if (!IsEffectInPlay(effectType)) return false;                 // pre-filtre
    foreach ((type, targets) in GetEffectsWithTargets(unit: null, onlyActive))
        if (type == effectType && targets.Contains(target.Id)) return true;
    return false;

`...$$GetEffectsWithTargets(unit, onlyActive)` balaie **TOUTES** les entités-effet du state (le
paramètre `unit` filtre sur `EffectComponent.OwnerId @+0x14`, et vaut `null` ici), retient celles dont
`EffectComponent.Targets @+0x48` est non vide, et publie `(EffectType @+0x58, Targets @+0x48)`.

⚠ **Ce n'est PAS `EntityExtensions$$IsTargetOfEffectOfType`** (#416/#419) : cette dernière n'itère que
les effets **owned** par l'entité testée, et passe par la `effectsDatabase`. Même aval conceptuel,
deux fonctions distinctes ; ne pas recopier la citation.

### Les deux relations sont DISJOINTES, et une seule est capturée

| relation | écrite par | lue par | publiée par le hook ? |
|---|---|---|---|
| **OWNER** (`EffectsOwnedComponent.ActiveEffectIds`) | `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` (`owner.GetComponent<EffectsOwned>().Add(effect.Id)`) | `HasEffect` / `IsOwnerOfEffectOfType` | **OUI** — `frida/hooks/game/effects.ts::readEffectsByUnit` |
| **TARGET** (`EffectComponent.Targets @+0x48`) | `IdunBattle.Operations.RefreshEffectsOperation$$AddTargetsToEffect` — **unique appelant** d'`IdunBattle.Entities.Components.EffectComponent$$AddTargetId` (xrefs) | `EffectsQuery$$IsEffectTarget` | **NON** (résidu `#366-r1-effect-targets`) |

`AddEffectOperation$$Execute(source, owner, …)` s'exécute **une fois par cible d'`AddEffect`**, avec
`owner` = cette cible : `EffectsState.by_unit` du port est donc bien le mirror de la relation OWNER.
La relation TARGET, elle, n'a qu'un peupleur — `...$$UpdateEffectTargets(desiredTargets, …)`, appelée
par `RefreshEffect` avec le `desiredTargets` rendu par le `<Effect>$$CreateTargetSelector` de
l'effet, évalué avec `Owner = l'owner de l'instance`.

⇒ **la géométrie de la liste vient du sélecteur de l'EFFET, jamais du call-site.** Le sélecteur passé
au nœud (`Owner@DSLSelectors+0x30`, `Caster@+0x48`, `Target@+0x60`) désigne le **SUJET** du test.

## 2. Les 6 fonctions consommatrices, 10 call-sites — verdict par site

Slots `DSLSelectors` lus à la source (`$$InitializeShared` pose `+0x30/+0x38/+0x40/+0x48/+0x50/+0x60/
…`) ; correspondance nommée déjà établie par `case-334` §3.

| fonction native | sujet (sélecteur) | `effectType` | géométrie de la liste (`CreateTargetSelector` de l'effet) | verdict |
|---|---|---|---|---|
| `…CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` | paramètre (`Owner`/`Target`) | `0x402` = **1026** `BigTarget_AdjacentEffect` | `AdjacentFriends(Owner, unitTile, unique)` — ring-1, porteur exclu | **PORTÉ** (#418), inchangé ici, non régressé (7/7) |
| `…PsykerExtraAttackAbility$$IsPsykerAttackSuppressed` (inline dans son `$$CreateTrigger`) | `Caster@+0x48` | `0x4a7` = **1191** `HuntersBeyondDeathPsykerSuppression` | `UnitsWithoutTrait(UnitsWithTrait(SurroundingEnemies(Owner, unitTile, range = 2, unique, sel = 3), 0x3ea Psyker, 3), 0x19 Immune, 3)` | **PORTÉ + CONFRONTÉ ici — bug trouvé** (§3) |
| idem | `Target@+0x60` | `0x5fd` = **1533** `WatchedOver_PsykerSuppression` | `WatchedOver_PsykerSuppressionEffect$$CreateTargetSelector` **n'a AUCUN symbole** (corps dédupliqué) | **RÉSIDU** — géométrie non lue, non inscrite, tri-état `None` |
| `…InstinctiveBehaviour_UpdateTargetAbility$$IsNotTaunted` (+ inline dans `$$CreateTrigger`) | `Owner@+0x30` | `0x1b` = **27** `Taunted_OnlySpecificTargets` | `TauntedEffect` n'a pas de `CreateTargetSelector` nommé ; la pose est un `AddBondEffect(0x1b, ref, Caster, Enemies(Caster, AdjacentUnits(CasterTile)), Caster, Direct(2))` | **NON PORTÉ** — l'ability n'existe pas dans `engine/` |
| `…InstinctiveBehaviour_UpdateTargetAbility$$GetUpdatedForcedTarget` | `Owner@+0x30` | `0x41c` = **1052** `Synapse_Effect` | `Unique( UnitsWithTrait(base, 0x3f7 BattleFatigue) + UnitsWithTrait(base, 0x7e5 InstinctiveBehaviour) + UnitsFromFaction(UnitsWithoutTrait(base, 0x7e8 Synapse), 0xc) )` où `base = Friends(Owner, SurroundingUnits(Owner, range = 2, unique, includeCenter = false, 3))` | **NON PORTÉ** — idem |
| `…GuardianOrganismAbility$$CreateTrigger` | `Owner@+0x30` | `0x41c` = **1052** | idem 1052 | **NON PORTÉ** — seuls le playbook (`GuardianOrganismPlaybook`) et l'effet `1217` le sont, pas le trigger de l'ability |
| `…WayOfTheShortBlade_AttackAbility$$CreateTrigger` | `Caster@+0x48` | `0x5dc` = **1500** `WayOfTheShortBlade_AdditionalAttackMarker` | `SurroundingFriends(Owner, range = GetNumberConstant(0x16), unique, 3) → UnitsWithTrait(0x10 Hero) → UnitsFromFaction(0x9)` **+ Owner** | **NON PORTÉ** — l'ability n'existe pas dans `engine/` |

⚠ **Aucune de ces géométries n'est celle du lecteur d'avant** (« amis hex-adjacents, porteur exclu ») :
trois rayons différents, deux polarités d'équipe (`SurroundingEnemies` vs `SurroundingFriends`), deux
filtres de trait, une inclusion explicite du porteur. Un lecteur qui aurait servi ces sites avec le
défaut `1026` aurait été FAUX sur les cinq.

⚠ **Le piège de lecture #419/#429 est confirmé une troisième fois** : `AdjacentFriends(unit, unitTile,
unique)` n'a **ni rayon ni `includeCenter`**, là où `SurroundingEnemies(unit, unitTile, range:Int32,
unique, unitSelectionType)` et `SurroundingUnits(origin, range:Int32, unique, includeCenter, …)` en
ont. Lire la SIGNATURE avant d'interpréter les littéraux.

## 3. Le bug : le gate de suppression ne fermait JAMAIS

`PsykerExtraAttackAbility$$CreateTrigger` =

    On(0x26 NormalAttack) & get_OwnerIsActor & IsRangedAttack & DamageProfileIs(0xd Psychic)
    & op_LogicalNot( IsEffectTarget(Caster@+0x48, 1191) op_BitwiseOr IsEffectTarget(Target@+0x60, 1533) )

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HuntersBeyondDeathAbility$$CreateBehaviour` =
`AddEffect(0x4a6, ref, Owner, Owner, …) + AddEffect(0x494, …) + AddEffect(0x4a7, ref, Owner, Owner, …)`
⇒ **l'instance `1191` est posée SUR SON PORTEUR**. Mesuré, sans rien déduire du port : sur un runner
`astraPrimarisPsy` vs `spaceHound`, `decisionView` publie `HuntersBeyondDeathPsykerSuppression`
(`type = 1191`, `src = spaceHound`) **sur `spaceHound` et sur aucune autre unité**, canal actif comme
`includeInactive: true`.

Le port faisait, aux deux faces :

* COMBAT — `state.effects.has_effect(psyker, 1191)` ;
* DÉCISION — `_unit_has_effect(scene, caster, "HuntersBeyondDeathPsykerSuppression")`.

Les deux lisent la relation **OWNER**, donc **structurellement toujours faux** : le splash n'était
jamais supprimé.

### Mesure live — 3 régimes, mêmes unités, seule la géométrie change

`probe_418_r1_is_effect_target.py`, `MC1_67` + seed `31337`, crit/block neutralisés, PV gonflés (les
trois mesures jouent sur le MÊME runner) :

| régime | d(psyker, porteur) | splash **live** | splash **port AVANT** | splash **port APRÈS** |
|---|---|---|---|---|
| `free` — hors du disque | **3** | `{spaceHound: [1506]}` | idem (bit-exact) | idem |
| `same_turn` — déplacement PUIS tir dans le même tour | **2** | **∅** | `{necroWarden: [1506]}` | **∅** |
| `after_turn` — même position, après un cycle complet | **2** | **∅** | `{necroWarden: [1506]}` | **∅** |
| `ally_carrier` — porteur AMI du psyker | **2** | `{necroSpyder: [1506]}` | idem | idem |

Le volet `ally_carrier` est celui qui **discrimine `SurroundingEnemies` de `SurroundingUnits`** : un
porteur ami à la même distance ne supprime rien, live comme port.

### Le régime discriminant « matérialisé vs re-dérivé » — TRANCHÉ, aucune divergence

L'écart (1) nommé par #419 était : « une lecture faite APRÈS un déplacement et AVANT le refresh qui le
suit ». C'est exactement le régime `same_turn` — le psyker se déplace jusqu'à `d = 2` du porteur puis
tire **sans passer la main**. Résultat : `same_turn` et `after_turn` rendent **le même** verdict
(suppression). La liste native `EffectComponent.Targets` n'est donc **pas en retard d'un refresh** dans
ce régime : re-dériver à la lecture est ici équivalent à lire la liste matérialisée.

⚠ Portée de ce verdict : **ce call-site, ce vecteur (déplacement d'une unité, pas de l'AURA)**. Le
régime symétrique — le PORTEUR de l'aura bouge, puis on lit — n'est pas couvert (§6).

## 4. Le port : une géométrie PAR effectType, jamais un défaut

Foyer unique **`scripts/python/engine/entities/effect_targets.py`** :

* `EFFECT_TARGET_SELECTORS = {1026: AdjacentFriends…, 1191: SurroundingEnemies(range 2) ∧ Psyker ∧ ¬Immune}` —
  chaque entrée cite le `<Effect>$$CreateTargetSelector` dont elle est le mirror ;
* `is_effect_target(world, unit_id, effect_type) -> bool | None` : balaie les **porteurs** du type
  (relation OWNER, la seule capturée), applique le sélecteur de CET effet, teste l'appartenance ;
* **`None` = géométrie non portée / substrat manquant**, jamais un `False` inventé — le natif lit une
  liste matérialisée, affirmer `False` reviendrait à prétendre qu'on l'a mesurée vide.

Deux substrats, comme tout nœud à double face : `runner/components.py::_RunnerEffectTargetWorld`
(ECS) et `playbook/scene.py::_SceneEffectTargetWorld` (tables). `is_target_of_adjacent_friend_aura`
devient un **alias** de `is_effect_target` (son nom encodait une géométrie que le nœud natif ne connaît
pas) ; ses deux appelants sont inchangés.

Les deux consommateurs traitent le tri-état explicitement : `if is_effect_target(…, 1191)` ferme sur
`True` ; `if is_effect_target(…, 1533) is True` ne ferme **pas** sur `None` — comportement strictement
antérieur pour la branche non mesurée.

## 5. Mutations adversariales — les gardes sont ROUGES quand on les casse

| mutation (vérifiée par `git diff --stat`) | ce qui rougit |
|---|---|
| **M1** `is_effect_target` **forcée** à `False` (l'état d'avant, en pire) | 2/5 — `same_turn` + `after_turn` : « le port doit se taire — il a splashé `[{'target': 79, 'per_hit': [1506]}]` » |
| **M2** filtre d'équipe retiré (`SurroundingEnemies` → `SurroundingUnits`) | 1/5 — `ally_carrier` : « le port ne doit pas fermer sur un porteur AMI » |
| **M3** `range = 2` → `3` | 1/5 — `free` : « le port doit firer le splash hors de portée du suppresseur » |

Aucune mutation ne rougit tous les volets : chacun mesure une propriété distincte, et c'est voulu.

## 6. Ce qui n'est PAS couvert

* **`1533 WatchedOver_PsykerSuppression`** — son `CreateTargetSelector` n'a **aucun symbole**
  (corps dédupliqué ; `WatchedOver_DamageReductionPctEffect$$CreateTargetSelector` =
  `AdjacentFriends(Owner, unique, 3)` porte **6 xrefs DATA** contre 2 pour celui de `1191`, ce qui
  *suggère* un partage sans le prouver). Géométrie **non lue** ⇒ **non inscrite** : le foyer rend
  `None` et le gate ne ferme pas dessus. Confrontable en principe (porteurs `darkaSmnWatcher` SUMMON
  + `darkaNpc4Watcher`), non monté ici. Fermer = lire le slot de vtable `CreateTargetSelector` de la
  classe (`reference_il2cpp_methodptr_uninit_class`), **pas** inférer la géométrie par mesure.
* **Les 5 call-sites non portés** (`27`, `1052` ×2, `1500`) : géométries LUES et consignées §2, mais
  aucune des trois abilities porteuses n'existe dans `engine/` — les inscrire serait du port
  spéculatif. Elles deviennent gratuites le jour où l'une d'elles est portée.
* **Le régime « le PORTEUR de l'aura se déplace »** n'est pas mesuré : seul le SUJET bouge dans les
  trois régimes. Si le refresh natif n'était pas déclenché par le mouvement du porteur, la
  re-dérivation serait en AVANCE sur la liste native — non observé, non réfuté.
* **Le volet `adjacent` (d = 1)** a été monté (`--variant adjacent`) mais le tir live n'a produit
  **aucun** événement de dégât dans cette géométrie (`cast_ok = true`, `live_primary = null` — LoS ou
  engagement) : **NON CONFRONTÉ**. Le caractère INCLUSIF du disque `range = 2` reste appuyé sur la
  signature (`range:Int32`) et sur le contraste mesuré d = 3 (ouvert) / d = 2 (fermé).
* **La face DÉCISION** (`PsykerPlaybook`) est corrigée par le **même foyer** que la face COMBAT, mais
  n'est pas confrontée live ici : il faudrait faire jouer l'IA du camp du psyker avec un porteur de
  `HuntersBeyondDeath` en face. Le pendant COMBAT est, lui, confronté sur 4 volets.
* **Écart voisin, hors périmètre, CHIFFRÉ** : dans les régimes où la cible primaire est `spaceHound`,
  le dégât PRIMAIRE diverge d'un **797 constant** (live `2616` / port `3413` ; live `1735` / port
  `2532`). Le canal est `IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathEffect$$
  CreateEffectDamageMalusForDefense` (`1190`), non porté. Rien à voir avec `IsEffectTarget` ; les
  gardes de cette tranche portent donc sur la PRÉSENCE du splash, jamais sur le montant primaire.
* **Cliquet `test_337_dsl_triggers_attestation_offline.py` : ROUGE, et il l'était déjà sur la base**
  (vérifié par `git stash`) — `HasBlockedThisTurn` est `CITE_A_QUALIFIER`, cité par
  `runner/operations/triggers/loki/harlequins_panoply.py`. Sans rapport avec cette tranche.

## 7. Artefacts

| quoi | où |
|---|---|
| foyer du nœud + table des géométries | `scripts/python/engine/entities/effect_targets.py` |
| substrat COMBAT | `scripts/python/engine/runner/components.py` (`is_effect_target`, `_RunnerEffectTargetWorld`, alias `is_target_of_adjacent_friend_aura`) |
| substrat DÉCISION | `scripts/python/engine/playbook/scene.py` (`Scene.is_effect_target`, `_SceneEffectTargetWorld`) |
| consommateur COMBAT | `scripts/python/engine/runner/operations/triggers/loki/psyker.py` |
| consommateur DÉCISION | `scripts/python/engine/playbook/psyker.py` |
| montage live | `scripts/python/probe_418_r1_is_effect_target.py` (`--variant core\|adjacent\|ally`) |
| gardes | `scripts/python/tests/engine/runner/test_psyker_suppression_live.py` (5) |
