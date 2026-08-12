# #926 — `FirstAmongTraitors` (`blackAbaddon`) : trois faces, pas une

**Verdict : les TROIS faces sont portées et confrontées à leur oracle natif.** `kit-coverage`
annonçait `manque 1` ; le décompilé en porte **trois** — face DÉCISION owner, face DÉCISION
non-owner (déjà portée par #477-r37), face COMBAT. Aucune n'est du code mort.

Build de la RE : `rnca9r7q6c`. Port : `engine/entities/effects/loki/first_among_traitors.py`,
`engine/playbook/friends_in_range.py::FirstAmongTraitorsPlaybook`. Mesure :
`probe_926_first_among_traitors.py`. Gardes : `tests/engine/test_926_*_offline.py` (24),
`tests/engine/runner/test_926_*_live.py` (7).

## 1. Ce que le natif dit, et qu'aucune table ne disait

`IdunBattleLogic.Entities.Abilities.Active.Loki.FirstAmongTraitorsAbility` ne DÉCLARE que deux
corps (`GetEffectType` = `return 0x427`, `GetRange` = `GetNumberConstant(cfg, 0x16)`). Son parent,
lu dans `classes.tsv`, est `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` : ni
`CreateTrigger` ni `CreateBehaviour` propres — ce sont les corps de BASE. D'où le canal de port
`ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_CLASSES`, jamais `ABILITY_TRIGGERS`.

⚠ Le namespace `...Abilities.**Active**.Loki` du symbole ne dit RIEN de la voie : la classe dérive
d'un `...TriggeredAbility` et le gameconfig la range en `passiveAbilities`.

**`FirstAmongTraitors_ExtraDmgEffect$$CreateTargetSelector`**

    UnitsWithTrait( SurroundingFriends(Owner@DSLSelectors+0x30, ConfigConst(0x16 = range),
                                       unique = true, unitSelectionType = 3),
                    0x7ea = UnitTrait.Chaos, 3 )

`DSLSelectors$$SurroundingFriends` (surcharge à 5 args) = `Friends(unit, Units(SurroundingTiles(unit,
range) − Tiles(unit), …))` : **le porteur est RETIRÉ, et rien ne le ré-ajoute**. Pas de
`op_Addition Owner`, contrairement à `DestroyTheWitch_ExtraDamage` et `IconOfObstinacy_ExtraDmg`.
⇒ **UNE seule patte de port** (`create_aura_attack_damage_bonus_for_ally`) ; déclarer
`create_effect_damage_bonus_for_attack` donnerait à Abaddon un bonus que le natif ne lui donne pas.

**`…$$CurrentDamageBonus(effect)`**

    Min( Sum( ConfigVar(0x428, EffectSource(effect), 0x08 = extraDmg),
              Multiply( TotalAttacksMade(EffectSource(effect)),
                        ConfigVar(0x428, EffectSource(effect), 0x09 = extraDmg_2) ) ),
         ConfigVar(0x428, EffectSource(effect), 0x0d = maxDmg) )

Les quatre nœuds lisent l'`EffectSource` = **Abaddon**, jamais le bénéficiaire : la magnitude est
identique pour tous, calculable depuis le seul porteur. `@50 / mult 100` : `277 + 55 n`, cap `992`.
Le cap tombe **exactement** à `n = 13`, ce que corrobore la constante `buffMaxLevel = 13` — que le
port NE LIT PAS (témoin indépendant, sous test).

**`…$$CreateEffectDamageBonusForAttack`** = `ForAddition(get_OwnerIsCaster, CurrentDamageBonus)` —
**UN SEUL** nœud de trigger. Ni `IsMeleeAttack`, ni `IsNormalAttack`, ni `HasTrait(Target, …)` : le
bonus vaut pour TOUTES les attaques du bénéficiaire. `GetRefreshTriggers` = `{UnitsChanged = 5,
UnitPositionChanged = 7}`.

**Face DÉCISION owner** (`FirstAmongTraitorsPlaybook.<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext`) :

    units = IBattleQuery.<slot 0x75 = GetSurroundingUnits>(tile, GetRange(), case.unit, true)
    foreach u : if (u != case.unit && HasTrait(u, 0x7ea)) value += w["FIRSTAMONGTRAITORS_SurroundingChaosFriend"]

Même slot et même `includeCenter = true` qu'`AstartesBanner`, mais **deux filtres que son voisin
n'a pas** : l'exclusion explicite du mover et le trait `Chaos`. Les deux faces DÉCISION lisent des
clés BC **différentes**, dans des **sections** différentes (`TriggeredAbilities` = 10 /
`TriggeredAbilitiesNonOwner` = 20).

⚠ **Le slot cité par `friends_in_range.py` était FAUX** (`0x74`) et il est corrigé : `0x74` = 116 =
`GetUnitsAtDistance` (arité 2), incompatible avec les 4 arguments du call-site ;
`interface_slots.tsv` donne `IBattleQuery 117 GetSurroundingUnits` (arité 4). La sémantique décrite,
elle, était juste.

## 2. Le compteur `ActorStatisticsComponent+0x20`, qui n'était pas porté côté COMBAT

`TotalAttacksMade` est un **cumul de bataille** que rien ne remet à zéro (`reset_units_attacked_this_turn`
écrit `*(u64*)(this+0x24) = 0`, donc +0x24/+0x28 — pas +0x20). Il n'est NI `+0x30`
(`TotalTurnsWithAttacksMade`, ce que lit `MartialInspiration`) NI `+0x24`
(`AmountOfAttacksMadeThisTurn`). La face PRÉDICTION le lisait déjà (capteur `actorStats`) ; la face
COMBAT ne l'avait pas — le terme croissant y serait resté figé à 0, soit un **fork
prédiction/combat** silencieux. #926 l'ajoute : `components.register_attack_made` (`+= 1`),
`components.unit_total_attacks_made` (lecteur), `snapshot._apply_actor_stats` (seed — le hook
publiait déjà `totalAttacksMade`, **aucun capteur neuf**).

Publié aux DEUX agrégateurs d'aura sous la même clé `owner_total_attacks_made` (map par porteur),
même forme qu'`owner_stat_block_damage` de #919.

## 3. Ce que la mesure a tranché — deux régimes non déductibles du décompilé

**(a) Un ami NON CIBLABLE reçoit quand même le bonus.** Le sélecteur porte
`unitSelectionType = 3 = OnlyAliveAndTargetable` sur ses deux nœuds, et ce volet est **réel** sur un
autre canal du binaire (`LionHelm`, stat-mod : `darkaTerminator` en `TeleportStrike_TeleportingIn` ne
reçoit RIEN). Montage `blackTerminator` (Chaos + `TeleportStrike`) à distance 1 : le port lui accorde
499 et l'oracle NATIF est en **accord sur les 25 tuiles**. Ajouter un gate `is_targetable` ici serait
un écart **restrictif**. Cran : `test_un_ami_NON_CIBLABLE_recoit_quand_meme_le_bonus`.

> **#926-r1 — ce que la relecture a établi, et ce qui reste.** L'asymétrie **n'est PAS dans le
> sélecteur** : les deux `CreateTargetSelector` décompilés côte à côte ouvrent sur le MÊME
> `SurroundingFriends(Owner@+0x30, <range>, unique = 1, unitSelectionType = 3)` — ce fichier-ci
> n'ajoute qu'un `UnitsWithTrait(_, 0x7ea, 3)`. Fait NEUF, lu :
> `...FirstAmongTraitors_ExtraDmgEffect$$GetRefreshTriggers` rend `{UnitsChanged = 5,
> UnitPositionChanged = 7}` — écrit **INLINE** (`arr[0] = 5 ; arr[1] = 7`), donc entièrement
> lisible, contrairement aux surcharges qui passent par `RuntimeHelpers$$InitializeArray` — et
> `EffectsChanged = 4` **n'y est pas** ; les deux `LionHelm_*` ne déclarent **aucune** surcharge,
> donc `null`, que `BaseEffect$$ShouldRefreshForTrigger` traite comme « tout trigger ».
> **Sur-ensemble strict.** S'y ajoute que `RefreshEffectsOperation$$RefreshEffect` **sort en amont**
> en SIMULATION quand `StaticBattleRules.Effect$$ShouldRefreshDuringSimulation` est faux : pendant
> toute la face DÉCISION, `Targets@+0x48` est **figé**.
> La seconde cause candidate (« le flag `UnitFlag 0x11` n'est pas encore visible ») est **réfutée
> par structure** : ce flag est un état PARTAGÉ posé sur la CIBLE ; il ne peut pas rendre deux
> réponses à deux prédicats identiques **au même instant**, seulement à des instants différents.
> ⇒ **ce qui diffère est la FENÊTRE de ré-évaluation, jamais le prédicat.** Ne pas harmoniser, dans
> aucun sens ; le verdict est inscrit dans `aura_selectors.py::is_targetable` et dans
> `create_aura_attack_damage_bonus_for_ally`.
> **Reste ouvert** : quel `RefreshEffectTrigger` la pose d'un `UntargetableEffect` émet, et
> l'appartenance de `1063`/`1214` au `HashSet` de simulation. Les deux butent sur le même obstacle
> d'outillage — le `.cctor` de `StaticBattleRules.Effect` dépasse le budget du décompilateur, et les
> appels au slot 0x2f de `Core.Services.OperationProcessor` n'ont aucune xref.

**(b) L'attaque d'Abaddon pollue sa cible — et ce n'est PAS ce cas.** Son autre passif
`LetTheGalaxyBurn` pose l'effet de TUILE `DespoiledGround` (1476) sous la cible ; le volet
`DespoiledGround_ExtraDamagePct` (1478) n'est **pas porté** (résidu antérieur,
`case-159-rng-canal179-et-maybe-ltgb.md`). Écarts mesurés exactement proportionnels — ×4/3 et ×5/4,
selon l'attaquant. Le probe mesure donc le terme croissant sur l'ennemi **non frappé**.

## 4. Validation

| étage | oracle | résultat |
|---|---|---|
| 3 PRÉDICTION | `decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` par tuile | **33 tuiles, 0 écart** ; distances porteur 0/1/2/3 → gate géométrique EXERCÉ |
| 4 DÉCISION | `triggeredMoveTrace` (armement **nominatif** par `runnerId`) + `check_value` (#443-r1a) | **162 lignes, accord partout**, 45 non nulles, **3 valeurs natives distinctes** `[0, 10, 20]` |
| 5 TERME CROISSANT | prédiction native avant/après une attaque d'Abaddon, sur l'ennemi non frappé | natif `4422 → 4872` ; port suit, **9 tuiles, 0 écart** |
| 6 COMBAT | `attacker_modifiers().additive`, delta imputé en retirant la classe du registre | **499** sur le seul bénéficiaire, **0** sur le porteur / l'Imperial / le lointain |
| 7 MUTANTS | gate de trait, rayon, patte SELF, magnitude | **4/4 ROUGES** |
| 8 NON CIBLABLE | prédiction native, montage deep-strike | accord, cf. §3(a) |

⚠ **Deux mutants ont d'abord été VERTS**, et les deux pour la même famille de vice :
- `magnitude +1` — l'attendu était **recalculé par la fonction mutée**, donc il se déplaçait avec
  elle. Corrigé en FIGEANT `bonus` avant toute mutation.
- `porteur RE-AJOUTÉ` — simulé depuis le canal aura, il ne pouvait **pas** mordre : l'agrégateur
  exclut déjà le porteur de ses propres carriers (`uid == att_id: continue`). Le seul chemin par
  lequel le porteur toucherait le bonus est `create_effect_damage_bonus_for_attack` : le mutant
  DÉCLARE désormais cette patte.

## Ce qui n'est PAS couvert

- `GetLocalizationDataInternal` (`{AbilityParam(0x15): CurrentDamageBonus}`) — pur affichage, non
  porté, sans conséquence de simulation.
- Les variantes `rangeType` de `RegisterAttackMade` (`+0x28`/`+0x2c`) restent non portées — résidu
  antérieur nommé dans `components.register_attack_made`, hors de ce cas.
- `TalonOfHorus` (ability d'**item** d'Abaddon) — voie conditionnelle, hors du kit ; recensée
  hors-total par `kit-coverage`.
- Le cap `maxDmg` n'a pas été atteint EN BATAILLE (il faudrait 13 attaques d'Abaddon) : il est
  confronté à la formule et au témoin `buffMaxLevel`, pas à un état live.
