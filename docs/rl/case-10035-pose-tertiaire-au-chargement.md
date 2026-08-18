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
* **Les 23 reliques sans entrée `ABILITY_INIT_OWNER_EFFECTS`** ne sont pas visitées. Deux d'entre
  elles sont équipées au seed BC (`SupaCyborkBody` sur `orksRuntherd`, `KardiocoreGalvanus` sur
  `admecMarshall`/`admecRuststalker`) ; `KardiocoreGalvanus` est toujours actif (donc toujours capté),
  `SupaCyborkBody` a une condition — c'est le régime de `#961-r3`. Établir si leur `CreateBehaviour`
  pose un owner-effet à l'init exige de le LIRE, ability par ability. Résidu **#10035-r3**.
