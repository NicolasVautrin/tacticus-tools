# case-366-r1-camo-seed — un effet condition-gated que la SIM fait entrer dans sa condition

**Question, binaire.** Un porteur capté HORS de la condition, puis amené DEDANS par la simulation
offline, reçoit-il ce que le natif lui donne — ou le port reste-t-il muet ?

**Réponse : il restait muet, pour DEUX raisons distinctes, et les deux sont fermées.** Mesuré sur
`1014 CamoCloak_DmgReduction` (`ultraEliminatorSgt` << Certus >>), board `C4_09` / seed 4242,
Certus capté hors couvert puis déplacé sur une `DryBush` : live **31907**, port **32655** avant,
port **31907** après (bit-exact, sur les DEUX canaux de capture), contre-épreuve sans l'effet
**32655** — écart **748/coup** = `dmgReduction[L50] × 1.8 = 499` porté par la chaîne %-dégât.

## 1. La prémisse de la fiche était FAUSSE : INERTE n'est pas ABSENT

`case-366-r1-camo-cloak-dmg-reduction.md` §8 écrivait « un porteur capté HORS couvert n'a **pas
d'instance** 1014 matérialisée ». C'est une lecture du **canal par DÉFAUT**, pas du natif.

`IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour`, relu au
désassemblage, est un `AddEffect(0x3f6, <BaseTriggeredAbility.get_AbilityStateReference>,
Owner@DSLSelectors+0x30, 0)` **NU** — aucun `If(...)`. La pose est **INCONDITIONNELLE**.

Les deux canaux du capteur, lus au MÊME instant sur un Certus hors couvert :

| canal | `1014` | `EffectComponent.IsActive` |
|---|---|---|
| `decisionView` par DÉFAUT | **absent** | — |
| `decisionView { includeInactive: true }` | **présent** | **false** |

⇒ le trou n'est ni dans la pose native ni dans le gate : il est dans **l'INGESTION**.

## 2. Deux trous distincts, que seule une décomposition par étage sépare

| étage | ce qui manquait | correctif |
|---|---|---|
| **SEED** | un état chargé depuis le canal par DÉFAUT n'a AUCUNE instance à rallumer | `factory.ABILITY_INIT_OWNER_EFFECTS["CamoCloak"]` |
| **REFRESH** | même avec l'instance (canal `includeInactive`), le pas offline ne la rallumait pas | `runner/operations/movement.py::refresh_effects_after_move_triggers` |

Le second est un **bug de port**, pas un manque de capteur, et il se lit au désassemblage.
`IdunBattle.Operations.MoveUnitOperation$$Execute` appelle **DEUX FOIS**
`Core.Services.OperationProcessor$$RefreshEffects({trigger = 7 UnitPositionChanged,
effectEntity = null})` — deux `FUN_180028040(0x2f, …, processor, &{7,0})` qui **ENCADRENT**
`MoveUnitOperation$$EvaluateAfterMoveTriggers` :

    … RecordTilesMoved
    RefreshEffects({7, null})          #1  -> porté par `MoveUnitOperation.execute`
    EvaluateAfterMoveTriggers(…)           -> porté par les appelants (`after_move_triggers`)
    [ On(0x1c = ArrivedAtFinalTile) ]
    RefreshEffects({7, null})          #2  -> MANQUAIT

Le second n'est pas redondant : c'est `EvaluateAfterMoveTriggers` qui émet
`On(0x24 = UnitPositionChanged_1)`, donc qui fait poser `1013 LightCover` par
`IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility` — l'entrée même que lit
`IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$CreateActiveCondition`. Au
refresh #1 le couvert n'est pas encore là.

Décomposition mesurée du pas offline, AVANT correctif (seed `includeInactive`) :

| après le pas | valeur |
|---|---|
| `port_has_1013` | **True** (le vecteur after-move a posé le couvert) |
| `cond_is_active` (la `CreateActiveCondition` portée) | **True** |
| `flag_active` (`EffectComponent.IsActive`) | **False** ← le refresh #2 manquant |
| `in_active_effects` | **False** (`active_effects` conjugue les deux, comme le natif) |

Le natif, lui, republie `1014` dans son canal ACTIF avec `active: true` après le même pas.

## 3. L'inventaire du gisement — 20 classes, **12 encore EXPOSÉES**

`python scripts/python/probe_366_camo_seed_inventory.py` (100 % offline). Il RE-DÉRIVE la partie
mécanique depuis le code et la croise avec un verdict de RE **par classe**. Deux conjoints, et il
faut les DEUX :

* **POSE** — le natif matérialise-t-il l'instance quand la condition est fausse ? Tranché au
  `<X>Ability$$CreateBehaviour` (`AddEffect` nu sur le trigger d'init = oui), jamais au
  comportement observé. Pose RUNTIME ⇒ l'absence offline est **fidèle**.
* **BASCULE** — la condition peut-elle passer de FAUSSE à VRAIE en cours de sim ? Un trait ne
  bascule pas ; la position, les PV, le tour, un effet voisin, si.

| verdict | n | qui |
|---|---|---|
| `COUVERT-SEED` | **6** | `AnvilShield_BlockChanceBelowHealthCap`, `HammerOfWrath_ConditionalDamage`, `ModifiedExoarmour_ExtraDmg`, `VisionsOfHeresy_ExtraPierce{Melee,Ranged}`, **`CamoCloak_DmgReduction`** |
| `NON-EXPOSE` | **2** | `Pinned` (pose runtime + condition de TRAIT, qui ne bascule pas), `PsychicStalk_VisualEffect` (`NOT IsDead(Owner)` : vraie pour tout porteur vivant) |
| `EXPOSE` | **12** | `ContagionsOfNurgle_ArmorReduction1/2`, `DestroyTheWitch_ExtraDamage/_ExtraMove`, `InescapableAccuracy_extraCritChance/_extraCritDmg/_overrideHits`, `MartialSuperiority_Visual`, `PowerTrip_FullHealth`, `ReinforcedHiveNode_ExtraArmor/_ExtraBlock`, `StructuralAnalyser_Visual` |

⚠ **Ne pas recopier ces nombres** : ils se périment à chaque port qui entre une classe
surchargeant `is_active`. Les re-dériver (`probe_366_camo_seed_inventory.py`).
**Mesuré sur ce cas même** : le cliquet a ROUGI au rebase, sur
`ReinforcedHiveNode_ExtraBlock` (`1109`, mergé pendant ce run) — une classe entrée sans verdict de
pose, exactement ce qu'il existe pour attraper. Résolu en lisant son `CreateBehaviour` (le MÊME que
`1108` : `AddStaticStatModifierEffectToOwner(0x454)` **et** `AddStatOverrideEffectToOwner(0x455)`
d'un bloc, sans `If`).

**EXPOSÉ ne veut pas dire FAUX partout** : le port matérialise l'instance dès que le SITE DE
CAPTURE demande `includeInactive` (`snapshot.decision_view_seed_body`). Mesuré : **14 fichiers**
l'utilisent, contre ~200 sites de `load_state` qui capturent par le canal par défaut. C'est ce
déséquilibre qui est le résidu, pas une erreur de moteur.

## 4. Le montage live

`probe_366_r1_camo_seed.py` — Certus **SEUL** de son camp (aucun ami `BigTarget` ⇒ le seul membre
atteignable du `op_BitwiseOr` est `1013`), `necroWarden` amené à 2..3 hex de la tuile de
DESTINATION (l'ancre est la destination, pas la position de départ), cycle de tour complet pour
rendre au tireur une activation FRAÎCHE, capture dans le tour de l'ennemi, puis le pas du porteur
joué HORS de son tour (`applyAction` ne vérifie pas la propriété, `MoveUnitMessage` non plus : les
deux côtés voient le MÊME pas). `--crit 0,0 --crit-target 0,0 --block-target 0,0 --block-player 0,0`,
`--hp-player` (armure du porteur à 0). Le probe VÉRIFIE que le pas live n'a consommé aucun tirage
(`dumpRng` avant/après identique) — sans quoi l'égalité bit-à-bit ne voudrait rien dire.

## 5. Mutations adversariales

| mutation | ce qui rougit |
|---|---|
| **M1** 2ᵉ `RefreshEffects` retiré | **4/7** de `test_camo_cloak_seed_move_live` (S3 et S4, les DEUX canaux) |
| **M2** entrée `ABILITY_INIT_OWNER_EFFECTS["CamoCloak"]` retirée | **4** (les 3 bras `default` + la garde `none` de #418) |
| **M3** ancienne attente `present is False` restaurée | `test_camo_cloak_no_cover_native_off_live` |
| **M4** refresh #2 appelé AVANT `after_move_triggers` | le cliquet structurel offline |

M2 et M3 sont les deux qui comptent : ils prouvent que la garde `none` de #418 n'a pas été
**assouplie** mais **corrigée** — elle codait la lecture fausse « pas dans le canal actif ⇒ pas
d'instance », et cette attente-là interdisait au port de rallumer quoi que ce soit.

## 6. Ce qui n'est PAS couvert

* **Les 12 classes `EXPOSE`** ne sont pas seedées. Chacune demande la même paire (verdict de pose
  déjà établi + entrée `ABILITY_INIT_OWNER_EFFECTS`), MAIS `spawn._seed_ability_owner_effects` lit
  les passives du **KIT gameconfig**, pas de la MESURE (`UnitContext.passive_abilities`, seedé par
  `snapshot._load_passive_abilities` — donc APRÈS lui). C'est le piège #312 : un montage qui prive
  une unité de son passif verrait le port matérialiser l'effet quand même. **Le préalable à un
  seed en masse est de déplacer ce seed après `_load_passive_abilities` et de lui faire lire le
  substrat mesuré** (résidu déjà nommé par #366-r1b).
* **Aucune mesure sur un porteur SUMMON** (`ultraSmnEliminator` porte le même passif).
* **Le refresh #2 est porté aux DEUX sites qui composent move + after-move** (`MovementHandler`,
  `summon_ai`). Les sites qui appellent `MoveUnitOperation.execute` SANS vecteur after-move
  (`DisplaceUnitOperation`, `TheQuickening`, genestealer) restent inchangés : rien n'y change entre
  les deux refreshes, donc le second y serait un no-op exact — non mesuré, raisonné.
* **La face DÉCISION** (`playbook/scene.py::_seed_condition_gated_owner_effects`) reste gouvernée
  par le couple `active_condition_ported` + `seed_witness_effect`, et `CamoCloak` n'a **pas** d'effet
  frère utilisable comme témoin. Le seed COMBAT (`load_state`) ne l'alimente pas.
* **Le régime « la sim fait SORTIR de la condition »** (quitter le couvert) n'est confronté
  qu'offline (contrefactuel de #418), jamais par un pas live.

## 7. Artefacts

| quoi | où |
|---|---|
| 2ᵉ `RefreshEffects` du move | `scripts/python/engine/runner/operations/movement.py` (`refresh_effects_after_move_triggers`), appelé par `MovementHandler.visit_MoveUnitMessage` et `operations/summon_ai.py` |
| seed de l'owner-effect | `scripts/python/engine/entities/effects/factory.py` (`ABILITY_INIT_OWNER_EFFECTS["CamoCloak"]`) |
| montage live | `scripts/python/probe_366_r1_camo_seed.py` |
| inventaire + cliquet de pose | `scripts/python/probe_366_camo_seed_inventory.py` |
| gardes live (7) | `scripts/python/tests/engine/runner/test_camo_cloak_seed_move_live.py` |
| cliquets offline (3) | `scripts/python/tests/engine/runner/test_camo_seed_inventory_offline.py` |
