# case-10035 — trois résidus, une cause : la relique arrive APRÈS le seed qui devait la voir

Build `t6dpr4k06g`. Trois résidus décrivaient chacun un owner-effet de relique absent de l'état
offline — `#589-r1-r1-r2-r1-r1` (`AmuletOfTheVoidwyrm_CritDamageReduction`), `#908-r2` (les deux
effets de `NetherRealmCasket`), `#922-r1` (`IntoxicatingElixir`). Ce n'étaient pas trois trous de
registre. C'est **un ordre de passes**, et il vit dans `snapshot.load_state`.

---

## 1. Ce que les trois fiches affirmaient, et ce qui en restait vrai

Les trois portaient la même phrase : « poser l'entrée `ABILITY_INIT_OWNER_EFFECTS` serait **INERTE**,
`_seed_ability_owner_effects` ne connaît ni la relique équipée ni `relicAbilities` ». **Périmée deux
fois** :

* depuis **#1005**, `spawn.py::_seed_ability_owner_effects` lit `ctx.tertiary_ability` et l'ajoute à
  sa liste d'abilities, avec le couple `(mult, level)` TERTIAIRE distinct de celui des passifs ;
* depuis le **2026-08-15**, les **trois** entrées de registre sont posées (`IntoxicatingElixir`,
  `AmuletOfTheVoidwyrm`, `NetherRealmCasket` → 4 owner-effets).

Mesuré : appelé **directement** avec un `ctx` complet, le seed pose bien les quatre effets, au bon
couple. Le mécanisme était donc entier — et pourtant `probe_922_intoxicating_elixir_live.py --n 0
--thrilled` rendait toujours `instance_dans_by_unit = 0`.

## 2. La cause, LUE dans `load_state`

`snapshot.py` appelle, **dans cet ordre** :

1. `_load_stats_and_effects` — qui pose les `StatsComponent.ctx` **et** porte la boucle
   `_seed_ability_owner_effects` ;
2. `_load_tertiary_abilities` — **seul écrivain** de `ctx.tertiary_ability`.

Au moment du seed, toute unité a donc `tertiary_ability = None`. La quatrième source de
`_seed_ability_owner_effects` est **structurellement muette sur ce chemin** — sans erreur, sans
trace. Le seed OFFLINE (`operations/spawn.py`, où le ctx est complet avant l'appel) posait bien
l'effet ; le seed de CAPTURE n'en posait **aucun**.

L'inversion n'est pas un oubli : les seeds *doivent* être en aval, ils écrivent dans les
`StatsComponent.ctx` que `_load_stats_and_effects` crée. **#1009 avait déjà rencontré exactement ce
mur** pour le RE-BAKE du couple, et l'avait résolu de la même façon — une passe placée après
l'écrivain (« Placé dans `_load_stats_and_effects` (donc AVANT), il voyait `None` sur toutes les
unités et ne mordait sur RIEN »). Le cran d'en dessous — l'instance n'existe pas du tout — n'avait
pas été fait.

## 3. Le natif n'a qu'UNE boucle, et elle voit la tertiaire

`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute`, relu en entier :

* il énumère la `Collection` du composant d'abilities (`+0x20`) et, pour CHAQUE entrée, émet le
  trigger `0x31` (`OnOwnerSpecificAbilityInit`) puis consulte
  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` ;
* la boucle TRAITS suit (`…StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait`), puis une
  seconde énumération d'abilities (`+0x18` de l'autre composant) qui ré-émet `0x31`.

L'ability TERTIAIRE est dans cette collection au même titre que les autres —
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` l'y met par
`TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`. **Il n'existe aucun ordre natif où
l'owner-effet d'une relique ne serait pas posé.**

## 4. Le correctif — `snapshot._seed_tertiary_owner_effects`

Une passe qui rejoue la MÊME boucle une fois son entrée connue, **entre** `_load_tertiary_abilities`
et `_rebake_tertiary_owner_effects` (qui reste l'écrivain unique du couple). Elle réutilise
`_seed_ability_owner_effects` — foyer unique des **cinq** sources de la boucle native — au lieu d'en
dupliquer une partie.

Trois bornes, toutes reprises de la boucle qu'elle rejoue :

* **porteur** : seules les unités à tertiaire **débloquée** (`tertiary_ability_level > 0` ; `0` =
  verrouillé, `Idun.Shared.Level$$CreateValidOrLockedLevel`) ;
* **deep-strike** : gate `TeleportStrike_TeleportingIn` (1035) — les passives d'une unité qui descend
  du ciel sont DIFFÉRÉES à l'atterrissage (`spawn.initialize_deferred_actor_abilities`) ;
* **idempotence** : `_materialize_owner_effect` a son gate `has_effect`, donc ce que
  `decisionView.effects` a capté et ce que la première passe a posé restent intacts. La passe ne peut
  qu'**ajouter ce qui manquait**.

Elle est tracée dans `State.ability_states_seed["seededTertiaryOwnerEffects"]`.

## 5. Mesure — avant / après

`probe_922_intoxicating_elixir_live.py --n 0 --thrilled` (`emperKakophonist` + `IntoxicatingElixir`,
la condition géométrique est FAUSSE à la capture et devient VRAIE pendant la salve) :

| | avant | après |
|---|---|---|
| `instance_dans_by_unit` | **0** | **1** |
| LIVE | `[6996, 6221, 5998]` | `[6996, 6221, 5998]` |
| OFFLINE | `[6534, 4621, 5010]` | **`[6996, 6221, 5998]`**, `accord=True` |
| écart par coup | `[462, 1600, 988]` | **`[0, 0, 0]`** |
| témoin `NOCHANNEL` | `[6534, 4621, 5010]` | `[6534, 4621, 5010]` (ROUGE) |
| témoin `CRITDMG_AVANT` | `[6534, 4621, 5010]` | `[6534, 4621, 5010]` (ROUGE) |

Les deux témoins du probe restent rouges : l'accord n'est pas dégénéré.

⚠ **Le drapeau `--inactifs` donnait déjà `1`, mais par l'autre bout.** Le volet (c) de `#922-r1`
proposait de basculer le canal `includeInactive` du harnais par défaut : cela **élargit la capture**
au lieu de réparer la pose, et son rayon est `ChargeRegimeHarness` entier (53 fichiers lecteurs,
+6 entités-effet au déploiement d'un 5v5 mesurées par #219). Ici rien n'est élargi. Le volet (c)
reste ouvert **pour d'autres motifs** (un effet posé en COMBAT et devenu inactif n'est rattrapé par
aucun seed d'init), mais il n'est plus ce qui ferme ces trois résidus.

## 6. Rayon, mesuré

Sur les **32** items relique du build, **9** ont une entrée `ABILITY_INIT_OWNER_EFFECTS` :
`AmuletOfTheVoidwyrm`, `HeadwoppasKillchoppa`, `IntoxicatingElixir`, `MonsterSlayerOfCaliban`,
`NetherRealmCasket`, `NornCrown`, `OrbsOfDecay`, `TheArdentBlade`, `Vitarus`. Une seule est équipée
dans le seed BC (**état 1**) : `NetherRealmCasket` sur `necroSpyder`. Les huit autres n'arrivent que
par un montage `--equip-relic` explicite.

Le rayon effectif est donc : *toute unité portant une de ces 9 reliques, dont l'owner-effet est
INACTIF à l'instant de la capture*. Partout ailleurs la passe est un no-op exact.

## 7. Gardes

* `tests/engine/runner/test_10035_pose_tertiaire_au_chargement_offline.py` — **25 passed**, cinq
  étages : ordinaux des deux enums figés (avec témoin de non-dégénérescence : les ordinaux d'effet
  nomment **autre chose** dans `TriggeredAbilityType`) ; entrées de registre ; **le RANG de la passe**
  (`_load_stats_and_effects` < `_load_tertiary_abilities` < seed < re-bake) ; la pose de bout en bout
  par `load_state` ; le couple TERTIAIRE contre celui des passifs ; les deux gates (niveau
  verrouillé, deep-strike) ; l'idempotence sur un effet déjà capté.
* **Témoin de non-dégénérescence joué AVANT les assertions de pose** : le montage vérifie qu'il ne
  publie PAS les owner-effets dans `decisionView.effects`. Sans lui, le seed serait un no-op et
  l'étage 2 serait vert sans rien mesurer.
* **Contre-épreuve, jouée** : `snapshot.py` restauré à sa version d'avant → **11 des 25 rougissent**,
  dont les trois bras de pose et les trois bras de couple.

## 8. Rejeu

    python probe_922_intoxicating_elixir_live.py --n 0 --thrilled
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 0,1,2 --level 3
    python -m pytest tests/engine/runner/test_10035_pose_tertiaire_au_chargement_offline.py

## 9. Ce qui n'est PAS couvert

* **`NetherRealmCasket` n'a pas de bras LIVE discriminant pour la POSE.** À `n = 0` l'effet ne verse
  rien (le compteur est nul), à `n > 0` il est ACTIF donc déjà capté par le canal : le dégât est
  identique dans les deux régimes, avant et après. Le gain y est structurel — l'instance existe
  désormais dès le déploiement, ce qui compte pour toute condition qui deviendrait vraie EN COURS de
  simulation. Résidu **#10035-r1**.
* **`probe_908_nether_realm_casket_crit_live.py --n 0,1 --level 1` est ROUGE, et il l'était
  DÉJÀ.** Vérifié en restaurant `snapshot.py` à sa version d'avant : sortie **strictement
  identique**, même `FAIL`. Son bras mutant `PASSIF` retire `tertiary_ability_state_of` du
  **contexte** `_crit_board`, mais depuis #1009 `_rebake_tertiary_owner_effects` bake le couple
  TERTIAIRE **dans l'instance** — l'effet lit son propre couple et le mutant ne mord plus. Le témoin
  est devenu structurellement aveugle : pour mordre, il doit viser le RE-BAKE, pas le callable de
  contexte. Résidu **#10035-r2**.
* **Le volet (c) de `#922-r1`** (basculer `includeInactive` par défaut dans `ChargeRegimeHarness`)
  reste ouvert, avec son rayon de 53 fichiers.
* ~~**Les 23 reliques sans entrée `ABILITY_INIT_OWNER_EFFECTS`** ne sont pas visitées.~~ **LUES
  (2026-08-18, `#10035-r3`) — SEPT posent, SEIZE non.** Cf. §10.

## 10. `#10035-r3` — les 23 reliques, LUES une par une (2026-08-18)

Le résidu disait « le zéro n'est pas une mesure, c'est une absence de lecture ». Les 23
`CreateBehaviour`/`CreateTrigger` ont été lus sur `t6dpr4k06g` : **7 posent** un owner-effet à
l'init, **16 non**. Le résultat NÉGATIF compte autant — c'est lui qui interdit de croire qu'on
aurait pu tout inscrire, et il est figé test par test.

| relique | forme | effet posé sur `Owner` (ordinal LU) |
|---|---|---|
| `KardiocoreGalvanus` | (a) | `KardiocoreGalvanus_ExtraCritDmg` `0x5aa` |
| `MawClawsOfThyrax` | (a) | `MawClawsOfThyrax_ExtraCritDmg` `0x5b5` |
| `SupaCyborkBody` | (a) | `SupaCyborkBody_CritDmgReduction` `0x5bc` |
| `TalismanOfRage` | (a) SPECIFIC, `.ctor(this, 0x5b4)` LU | `TalismanOfRage_CritDamageReduction` `0x5ad` |
| `PhoenixGem` | (a), via `PhoenixGem_InitAbility` | `PhoenixGem_CanRevive` `0x5ab` |
| `DawnBlade` | (b), via `DawnBlade_InitAbility` | `DawnBlade_ExtraDmg` `0x5dd` |
| `RelicBoltPistol` | (b) | `RelicBoltPistol_ExtraPierce` `0x5b1` **et** `..._ExtraCritDamage` `0x5b2` |

* **(a)** base `AOwnerEffect[Specific]TriggeredAbility` : la classe ne déclare que `GetEffectType`
  (corps ENTIER `return <ordinal>`), tout le reste vient de la base —
  `$$CreateTrigger` = `OnOwnerSpecificAbilityInit(this.AbilityType@+0x10)` (resp. `<this+0x60>`
  pour la variante SPECIFIC) et `$$CreateBehaviour` = `If(<ce trigger>, AddEffect(GetEffectType(),
  AbilityState(Owner, AbilityType), targets = `Owner@<DSLSelectors+0x30>`, turns ZÉROÉ), null)`.
* **(b)** `BaseTriggeredAbility` + `CreateBehaviour` propre, `CreateTrigger` = corps ICF partagé de
  corps ENTIER `OnOwnerSpecificAbilityInit(this.get_AbilityType())`, sans conjoint.

**Le partage ICF de (b) est MESURÉ, pas déduit.** Le RPC `resolveMethodPtr` (lecture pure, aucun
runner) rend le MÊME `methodPointer` pour les `CreateTrigger` de `RelicBoltPistolAbility`,
`SupaCyborkBodyAbility_AddTrait`, `DawnBlade_InitAbility` et `WayOfTheShortBlade_InitAbility` — et
c'est cette dernière qui porte le symbole, donc le corps lisible. Sans cette mesure, (b) restait un
appariement de bloc `methodPointers`.

⚠ **Le piège d'ordinal est réel dans ce lot même** : `EffectType` 1457/1458 sont les deux effets de
`RelicBoltPistol`, alors que `TriggeredAbilityType` 1457/1458 sont `KardiocoreGalvanus` et
`PhoenixGem`. Les quatre entrent dans le même bloc de registre ; un appariement par l'ordinal y
écrivait deux entrées fausses **sans lever d'erreur**.

⚠ **`PhoenixGem` n'est pas cosmétique** : 1451 est l'effet-MARQUEUR sur lequel tout le self-revive
de `#79` est branché (`EFFECT_TRIGGERS[PhoenixGem_CanRevive]`, trois classes). Sans la pose à
l'init, le rail existait mais n'était **jamais armé** hors capture live.

**Trouvé en passant, même registre, même lecture** : le passif `WayOfTheShortBlade` n'avait pas non
plus son entrée. C'est SA `CreateTrigger` qui porte le corps ICF de la forme (b) — la lire, c'est
lire son `CreateBehaviour` = `AddEffect(0x5db) & AddEffect(0x5dc)` sur `Owner`. Le canal AURA de
1499 (`#1019-r1`, confronté bit-exact) était donc INERTE hors capture live.

**Les seize non-poseuses**, avec la raison lue, sont figées dans
`tests/engine/runner/test_10035r3_reliques_non_visitees_offline.py` (65 tests). Cinq mutants joués,
cinq mordent : entrée retirée, effet manquant d'une paire, non-poseuse inscrite, ordinal dérivé,
4ᵉ source du seed débranchée.

**Reste ouvert** : `SupaCyborkBodyAbility_AddTrait$$CreateBehaviour` =
`AddTrait(Owner, 0x421 = UnitTrait.AffectedByHealAndRepair, isTemporary: false)` sous le même
trigger d'init — un TRAIT, qu'aucun des trois registres du port ne sait écrire. Résidu
**#10035-r5**.
