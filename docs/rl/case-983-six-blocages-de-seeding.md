# #983 — six résidus `BLOCAGE: seeding`, et **deux d'entre eux n'étaient pas des bugs**

Les six disaient la même chose : « le port lit le mauvais substrat ». Re-mesurés, **quatre**
énoncés sur six étaient faux ou plus larges que le fait.

| résidu | verdict | ce qui a tranché |
|---|---|---|
| #957-r1 | **RÉFUTÉ** | `GetPool(1)` = `EntityPool.DefeatedUnits`, pas `includeDead: true` |
| #943-r8 | **RÉFUTÉ** | les deux appelants existaient au commit qui a ouvert le résidu |
| #943-r7 | **2 sites câblés** (11 → 9) | aucun des deux n'exigeait le seeding annoncé |
| #945-r2 | **CÂBLÉ** | le canal runtime EXISTAIT, il n'était pas propagé |
| #921-r1 | **PORTÉ** | le substrat manquait vraiment ; la RE était complète |
| #448-r6 | **RÉPARÉ** | `processor[+0x20] = unit` **avant** l'évaluation du nœud `turns` |

---

## 1. #957-r1 — un littéral lu comme un booléen, et l'enum qui le dit

Le port de `FoehammerPlaybook` écrivait, en borne nommée : « les Machines of War sont hors
d'`observeBattle.units` : une MoW détruite ne serait pas comptée. `GetAllDeadUnits` itère, lui,
`slot 0x2f(state, includeDead: 1)` ».

Le `1` n'est pas un booléen. `IdunBattle.Core.Services.BattleQuery$$GetAllDeadUnits` appelle
`IdunBattle.Core.MatchState$$GetPool(<EntityPool>)`, et **trois corps** fixent la lecture :

    GetAllDeadUnits      -> GetPool(EntityPool.DefeatedUnits = 1)
    GetAllUnits          -> GetPool(EntityPool.AllUnits      = 8)
    GetAllAliveMachines  -> GetPool(EntityPool.AliveMachines = 6)

`IdunBattle.Entities.Enum.EntityPool` = `0=AliveUnits, 1=DefeatedUnits, 3=PlayingEffects,
4=EffectsToSimulate, 5=Tiles, 6=AliveMachines, 7=MachinePlatforms, 8=AllUnits, 9=DestroyedMachines`.

Les machines ont **leurs deux pools propres**, disjoints de ceux des unités : une MoW détruite entre
dans `DestroyedMachines`, jamais dans `DefeatedUnits`. Côté entités c'est le même fait —
`EntityType.Machine = 6` n'est pas `EntityType.Unit = 1`.

⇒ le substrat du port (`observeBattle.units[].isDead`, MoW exclues) est **le mirror exact**. La
« borne » qu'il s'écrivait était une fidélité.

C'est très exactement la faute que la règle « un entier qui DÉSIGNE quelque chose passe par un
ENUM » existe pour rendre visible : `1` est un ordinal juste **et** un booléen plausible, et rien
dans le pseudo-C ne les sépare.

## 2. #943-r8 — un résidu ouvert sur un `grep` qui n'a pas trouvé

L'énoncé : « `Scene.enmity_adjacent_units` / `..._dark_angels_friends` ne sont appelés NULLE PART ».
Mesuré à trois commits (`git grep -c` sur `engine/playbook/`) :

    f296bfa6 (#947+#948, le commit qui CRÉE les accesseurs)  -> abilities.py 1 · normal_attack.py 1
    32605db4 (#943-r7, celui qui OUVRE le résidu)            -> idem
    origin/master d'aujourd'hui                              -> idem

Les deux appelants posent `_ENMITY_CTX_UNITS` / `_ENMITY_CTX_DA` dans le ctx d'attaquant de la face
PRÉDICTION, et les deux classes d'effet les consomment (`_CTX_KEY`). La chaîne est complète depuis
l'origine.

## 3. #943-r7 — le blocage écrit était plus large que le fait

Le résidu classait les onze sites restants en « neuf ctx d'AURA — des dicts que l'agrégateur
remplit, sans board : les câbler exige de PUBLIER les deux cartes en amont, dans
`damage_model.attacker_modifiers` **et** dans la face PRÉDICTION ». C'est vrai pour sept d'entre
eux. Pour **deux**, non :

* `dark_angels_passives.py::marks_target` **n'est pas un ctx d'aura** : sa signature est
  `marks_target(state, owner_id, target_id)` et `state` **est** l'ECS du runner. Les deux canaux se
  dérivent de `state.board`, comme `damage_model.battle_query_is_charging` le fait déjà six cents
  lignes plus haut dans son unique appelant. Et c'est une face **MONO** —
  `marked_effect_types_for_target` n'a qu'un appelant (`damage_model`), donc aucune jumelle DÉCISION
  ne peut diverger.
* `extra_damage_aura.py::create_aura_attack_bonus` est bien un ctx d'aura, mais **son ctx portait
  déjà `board`** : `aura_attack_bonus_from_allies` reçoit `{..., "board": scene.board, ...}` de
  `playbook/prediction/normal_attack.py`, son unique appelant. Zéro seeding.

**La DIRECTION, que la couronne hex ne pouvait pas porter.**
`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin, unique, selType)` =
`op_Subtraction(Units(AdjacentTiles(origin), …), origin)`, et
`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` énumère `GetAdjacentTiles(t)` pour
chaque tuile de **l'origine**. La source de l'énumération est donc le PORTEUR (RitesOfBattle) ou
l'ami Dark Angel (FearedInterrogator) — jamais la cible. `hexgeo.distance`, symétrique par
construction, ne pouvait pas exprimer cet axe ; il a son test dédié, sur une carte asymétrique.

### Ce que le cliquet a rendu, et les DEUX natifs qu'il taisait

`probe_433r4r1r4r2_neigh_channel_wired`, avant → après :

    etape 5 : natifs a l'armement suspendu     1 -> 1   (mais PAS le meme)
    etape 6 : geometries nues sans canal      19 -> 17
              ventilation      GEOMETRIQUE=5, LISTE_STOCKEE=11 -> 9

L'étape 5 a demandé l'armement d'`AdjacentUnits` dès le second site câblé — son dernier foyer. En
l'armant, le registre suspendu s'est **vidé**, et `test_les_natifs_SUSPENDUS_le_sont_pour_une_raison
_qui_se_MESURE` a rougi sur son propre garde-vide (« registre vide : ce test ne garde plus rien »).
C'est ce rouge qui a fait chercher **ce que le registre ne portait pas** :

* `AdjacentFriends` et `AdjacentEnemies` figurent dans `SUBSTRATS_LUS[LISTE_STOCKEE]` **et** dans
  les valeurs de `GEOMETRIE_NUE_CLASSEE` — ils sont donc LUS — et pourtant ils n'étaient **ni armés
  ni suspendus** : en silence total, exactement ce que la suspension existe pour interdire.
* Inscrits, l'étape 5 les a départagés elle-même : `AdjacentEnemies` **périmé d'emblée** (ses trois
  foyers sont déjà dans `GEOMETRIE_NUE_TOLEREE`) → **armé** ; `AdjacentFriends` justifié par **trois**
  foyers hors tolérance (`imperative.py` ×2, `triggers/loki/icon_of_obstinacy.py`) → **suspendu**,
  foyers nommés.

⚠ Le garde-vide du test avait raison de rougir, et la bonne réponse n'était pas de l'assouplir.

## 4. #945-r2 — le canal existait, il n'était pas propagé

L'énoncé : « aucune source de `NCContext` ne publie les triggered abilities RUNTIME d'une unité ».
Faux : `AiDecisionContext.live_triggered_kits()` lit le `TriggeredAbilityComponent` de **toutes** les
unités en un seul RPC (`unitAbilityStates`), et `utilities/tile.py::_adjacent_units` le consomme
déjà pour ses voisins. Ce qui manquait, c'est l'arête `AiDecisionContext -> NCContext`.

`NCContext` gagne `triggered_kits` (callable lazy, même patron qu'`active_levels` /
`ability_config`), alimenté au **seul** call-site (`ai/action_generators.py`). Le gate de
`CalibaniteGreatsword` lit les deux substrats en **UNION** — règle N13 : une lecture live partielle
ne doit jamais RETIRER un id que le kit connaît. Canal absent ou RPC muet → kit gameconfig seul,
la dégradation d'avant, **jamais une affirmation**.

⚠ Côté OFFLINE le canal reste `None` (le bridge n'a pas de `rid`) : la borne se déplace, elle ne
disparaît pas. Résidu **#983-r1**.

## 5. #921-r1 — le seul dont le substrat manquait vraiment

`IdunBattle.AI.Playbook.SanguinaryPriestPlaybook` a un corps **propre**, et
`<CalculateMovementUtilityInStepsInternal>d__3$$MoveNext` porte trois choses qu'un port « par
ressemblance » aurait toutes ratées :

1. **le second `+=` est IMBRIQUÉ dans le premier `if`** — un ami Mechanical ne rapporte RIEN, même
   blessé. Appliquer le gate au seul terme de base laisserait 6, et le test du terme de base
   resterait vert : c'est pourquoi il a sa contre-épreuve ;
2. **aucun `RemoveAll(u.Id == case.Unit.Id)`**, et `UnitExtensions$$IsFriend` n'écarte pas
   l'égalité — le mover se compte **lui-même** dès que son origine tombe en ring-1 de la tuile
   candidate. L'inverse exact de `SereneUnifierPlaybook` (#456-r1) ;
3. **l'ORDRE du court-circuit** : `HasTrait(0x421 AffectedByHealAndRepair)` précède le test
   mécanique et le rend inopérant.

`IsMechanical` porte **trois** traits (`Mechanical 0x5`, `LivingMetal 0x3e8`, `Vehicle 0x405`) ;
`IsDamagedUnit(u)` = `GetStat(u, StatType.Health = 5, StatPart.Missing = 4) > 0`. Poids lus du seed :
**5** et **6**, qui se cumulent (11 sur un ami blessé).

Le substrat manquant était `hp`/`hp_max` par voisin. Les **trois** producteurs de contexte des
feuilles `Tile(7)` les publient désormais (runner ECS via `HealthComponent`, `Scene` via
`hp`/`hpmax`, `AiDecisionContext` via `units[].hp` + `hpmax_by_id`), plus `self_hp`/`self_hp_max`
pour le mover — sans quoi le point 2 serait muet. **TRI-ÉTAT strict** : un `0` de maximum ferait
passer toute unité pour intacte, en se présentant comme une mesure.

Sa face ATTACK est un `yield Fix64.op_Implicit(0)` **propre** (pas hérité) : elle n'a rien à
enregistrer, l'absence d'entrée EST le mirror.

## 6. #448-r6 — l'ordre des deux écritures

`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute`, relu verbatim :

    foreach (unit in <cibles>) {
        if (UnitExtensions.HasFlag(unit, UnitFlag.Dead = 6)) continue;
        processor[+0x20] = unit;                                   // <-- AVANT
        turns  = (entities+0x78 != null) ? Nullable(<+0x78>.Calculate(processor)) : null;
        rounds = (entities+0x80 != null) ? <+0x80>.Calculate(processor) : 1;
        ...
    }

Le nœud `turns` voit donc **la cible en cours**. Le port l'évaluait une fois sur le SET, ce qui est
le `Max` de `TurnsUntilUnitOwnerTurnFormula$$Calculate` : identique sur un set homogène, faux sinon.

`_resolve_duration` accepte désormais un NŒUD et **exige** alors le contexte par-cible ; sans
contexte il rend `None` — il ne devine pas. Les deux behaviours l'évaluent dans leur boucle sous
`replace(entities, active_target=elem)`. `TitanhammerSquad` b3/b4 passent les nœuds ; le
`TurnsFromRounds(1)` de b3 reste résolu au montage (`ConvertRoundsToTurns` ne lit que le `state`,
invariant sur la boucle).

## 7. Validation

**Offline** — `tests/engine/test_983_sanguinary_priest_et_adjacence_offline.py`, **25 tests, 0 skip**.
Chaque particularité a sa contre-épreuve : le gate mécanique est exercé sur les **trois** traits, la
direction d'`AdjacentUnits` sur une carte **asymétrique**, le tri-état des PV dans ses trois formes,
le canal runtime dans ses **quatre** régimes (absent / porteur / autre id / RPC muet), et la durée
par-cible avec son **témoin non nul** (1 vs 2 par cible, 2 pour les deux sur le set).

**Cliquets** — `probe_433r4r1r4r2_neigh_channel_wired` PASS ; `test_433r4r1r4r2r1r1_derivation_morte
_offline` + `test_943r7_faces_jumelles_adjacence_offline` + `test_433r4r1r4r2_is_adjacent_substrat
_offline` : **89 passed**.

**Live** — 4 fichiers des feuilles `Tile(7)` (le foyer que `hp`/`hp_max` traverse) : **30 passed,
1 failed**. Le rouge (`test_spiritual_leader_tile_term_live::test_term_is_capped_at_one_adjacent_
decoy[MC1_67-777]`) est **PRÉEXISTANT** — rejoué sur un arbre témoin détaché à `origin/master`, il
tombe à l'identique (même tuile `(1,3)`, mêmes valeurs `(0.0, 2)`). Autre tranche.

### Ce qui n'est PAS couvert

* **La confrontation live de `SanguinaryPriestPlaybook`.** `probe_193c_move_playbook_terms` sur
  `bloodSanguinary`/1296 (`MC1_67`, deux seeds) montre le port qui FIRE — `[0.0, 5.0, 10.0]`, des
  multiples du poids 5 — mais rend « **aucun pas DISCRIMINANT côté HOOKS** » : les tuiles où le
  terme varie ne sont pas celles que `scorerTileTermTrace` capte sur ce montage. La ventilation
  native par tuile n'est donc **pas** confrontée. Résidu **#983-r2**.
* **Le terme DAMAGED en live** : il exige un ami *blessé* au moment de la décision, que le seed ne
  produit pas au tour 0.
* **Les sept sites d'adjacence restants** (`hits.py` ×4, `imperative.py` ×2, `traits/combat.py`),
  plus `momentum.py` (`BLOCAGE: capteur`) et `triggers/loki/icon_of_obstinacy.py` (couple non
  fermable) — cf. #943-r7, dont l'étape 5 nomme désormais les trois foyers d'`AdjacentFriends`.
* **Le canal `triggered_kits` côté OFFLINE** (#983-r1).

## 8. Une note d'outillage, pour la prochaine tranche

Le capteur du `ConnectivityComponent` **brut** que #943-r7 réclame (`BLOCAGE: capteur` sur
`momentum.py`) **existe déjà** : `frida/hooks/features/ai-step/rpc-board.ts` publie `connectivity`
par tuile en tri-état, plus `connectivityLayout` / `connectivityTiles` / `connectivityEdges` /
`connectivityOversize` (livré par #448-r1-r1-r1-r1-r2), et `Board.neighbours_connectivity` le lit.
Ce qui manque n'est pas un hook : c'est que ce champ **n'existe qu'en live** — le
`ConnectivityComponent` est construit en bataille par
`IdunBattle.Operations.InitializeConnectivityOperation$$Execute`, alors que `data/boards/*.json`
sont des **assets** sérialisés par `IdunAssetsUtil.LoadBoard`, qui ne peuvent structurellement pas
le porter. L'étiquette `BLOCAGE: capteur` de ce site est donc trompeuse ; c'est
`BLOCAGE: aucun` + confrontation **live**.

## 9. Résidus ouverts

* **#983-r1** — `NCContext.triggered_kits` reste `None` sur le chemin OFFLINE (`state_bridge` n'a
  pas de `rid`) : le gate de `CalibaniteGreatsword` y retombe sur le kit gameconfig seul.
* **#983-r2** — la face DÉCISION de `SanguinaryPriest` n'est pas confrontée par tuile : le montage
  qui recouvre les tuiles hookées reste à construire.
* **#943-r7** reste ouvert sur **neuf** sites (11 → 9).
