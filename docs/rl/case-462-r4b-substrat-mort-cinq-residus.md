# `#462-r4b-…` — ce que le port sait d'une unité MORTE : cinq résidus, une seule question

**Livré le 2026-08-08**, build `rnca9r7q6c`.
Probe : `scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_r1_appelants.py`
(`--step {inventaire,ventilation,consommateur,gisement,gates,contrefactuel,registre}`, **100 % offline**).
Garde : `tests/engine/runner/test_462_r4b_substrat_mort_appelants_offline.py` (14) +
`test_ctx_traits_substrat_ventilation_offline.py` (14, **retournée** — cf. §3).

| item | résidu | verdict |
|---|---|---|
| 1 + 5 | `-b-r1-r1-r2` (requalifié) / `-c-r3-r1-r4-r1` | **RE FAITE, PORT NON FAIT** — 3 abilities entières absentes ; §5 |
| 2 | `-b-r1-r1-r3-r1-r1` | **RÉSOLU** — 19 clés énumérées, 1 ATTEIGNABLE, gate posé ; §2 |
| 3 | `-b-r1-r1-r3-r1-r2` | **RÉSOLU** — question native tranchée, port INCHANGÉ (motivé) ; §4 |
| 4 | `-b-r1-r1-r3-r1-r3` | **RÉSOLU AUTREMENT** — la prémisse du résidu était FAUSSE ; §1 |

---

## 1. `IsKilledThisTurn` — le résidu désignait le MAUVAIS CHAMP

Le résidu prescrivait : « le port n'a pas d'horodatage de mort général : `UnitComponent.turn_defeated`
n'est écrit que par `AmbushSummonAbility`. L'écrire à **chaque** mort rendrait les deux sites gatables
par le vrai critère. » **Trois lectures le réfutent.**

**a) `IsKilledThisTurn` ne lit pas `TurnDefeated`.** Le nœud
`IdunBattleLogic.Entities.DSLTriggers$$IsKilledThisTurn(unit)` alloue un
`IdunBattle.Entities.Triggers.KilledThisTurnTrigger`, dont le `ShouldTrigger` tient en trois lignes :

```
unit = SelectSingle(entities);            // slot 7 du sélecteur
if (unit == null) return false;
uc = GetComponent<UnitComponent>(unit);
return uc != null && *(byte *)(uc + 0x17a);      // <- un BOOLEEN
```

`TurnDefeated`, lui, est `+0x17c` — un **entier**, lu par
`IdunBattle.Entities.Formulas.TurnDefeatedFormula$$Calculate` sous un gate
`IdunBattle.Entities.UnitExtensions$$IsDefeated`. Deux champs voisins, deux types, deux lecteurs.
`IdunBattle.Entities.Components.UnitComponent$$Copy` recopie les deux, séparément.

**b) L'écrivain de `+0x17a` est le foyer de mort, et il est déjà porté.**
`IdunBattle.Operations.KillUnitOperation$$Execute+0x828` : `+0x17a = 1`, **dans la branche
non-revive** — juste après la garde `if (!unitComponent.PendingRevive@+0xa8.HasValue)` (`+0x81c`) et
avant le `RegisterDefeatedUnit` (`+0x8be`). C'est exactement le foyer que le port mirrore déjà
(`damage.py::_kill_unit_operation`).

**c) Le RESET explique la sémantique, et elle n'est pas celle du nom.**
`IdunBattle.Operations.StartTurnOperation$$ResetUnit` a pour deuxième instruction
`*(undefined2 *)(uc + 0x179) = 0` — un `short` qui efface `+0x179` **et** `+0x17a` d'un coup. Or
`ResetUnit` court sur `PlayerComponent.CurrentlyOwnedUnitIds`, dont
`PlayerComponent$$get_CurrentlyOwnedUnitIds` retire les défaits. ⇒ **le drapeau d'une unité MORTE
n'est jamais effacé.** `IsKilledThisTurn` veut donc dire « tuée, et n'a pas redémarré de tour
depuis », pas « tuée pendant le tour courant ».

### Le second conjoint était portable aussi, et personne ne l'avait cherché

`AreEqual(Killer(it), sel@0x40)` passe par
`IdunBattle.Entities.Selectors.UnitKillerSelector$$Select`, dont le corps est :
`uc = GetComponent<UnitComponent>(unit)` → `Nullable<DamageSource>@+0x108` → si `HasValue` **et**
`IdunBattle.Operations.DamageSource$$get_KillerId() != 0`, résoudre l'entité de cet id et ne la
retenir que si `IdunBattle.Entities.EntityExtensions$$IsActor(entity)`.

Or `UnitComponent.death_source` **existe déjà** côté port (`(killer_id, damage_reason,
ability_or_effect)`), écrit par `damage.py::_record_death_reason` — et le crush le pose avec
`killer_id = mover` (`movement.py::_kill_steppable_kill_unit`). Le conjoint était donc **portable sans
substrat neuf**.

### Ce que le collapse laissait passer (et que `IsKilledThisTurn` seul n'aurait PAS fermé)

Rien ne libère la tuile d'un decoy mort côté port. Un decoy tué au tour N par **une autre unité**
reste donc sur sa tuile ; si un stepper ami y marche au tour N+k, la co-localisation seule le rendait
valide et le port **blastait** pour un kill qui n'était pas le sien. `IsKilledThisTurn` est VRAI dans
ce cas (jamais réinitialisé pour un mort) : **seul `AreEqual(Killer(it), stepper)` le refuse.**

La docstring du port affirmait le contraire (« un decoy mort d'un tour antérieur est sur une AUTRE
tuile »). Elle est corrigée.

### Livré

* `UnitComponent.killed_this_turn`, tri-état (`None` = **non mesuré** — aucun canal ne publie
  `+0x17a` ; `combatSnapshot` ne porte que `unitFlags`, un `OrderedSet<UnitFlag>` distinct) ;
* écriture dans `damage.py::_kill_unit_operation`, branche non-revive, à son rang ;
* reset dans `turnflow.StartTurnOperation.execute`, **gaté `uc.alive`** — le filtre n'est pas une
  prudence, c'est le `RemoveAll(<défait>)` de `CurrentlyOwnedUnitIds` ;
* `genestealer.py::_valid_dead_decoys` porte désormais **les cinq** conjoints natifs.

⚠ **`turn_defeated` reste une COMPENSATION, et c'est un résidu neuf.**
`Ambush_SummonAbility$$GetSummonBehaviour` — l'endroit où le port l'écrit — ne l'écrit **pas** : son
arbre est `If(NOT <trigger>, Spawn(owner@0x30, PickRandomly(FreeTilesOrAdjacentFreeTiles(Tiles(
target))), <stringConst 8>, ForSteppable+AddEffect))`. Et `KillUnitOperation$$Execute` n'écrit que
`+0x178` et `+0x17a`.

⚠ **L'ÉCRIVAIN EST IDENTIFIÉ (2026-08-15) : `IdunBattle.Operations.RemoveUnitOperation$$Execute+0x4f6`.**
Il écrit `uc->[0x17c] = TurnComponent$$GetAmountOfTurnsStartedByPlayer(GetMatchTurn(state),
ownerPlayerId)` puis `uc->[0x180] = 1`, juste après `UnitFlagsComponent$$Add(unit, 0x1a = Removed)`.
`runner/operations/remove_unit.py` le **documentait déjà** en étape 10 : seule sa justification de
non-portage (« aucun consommateur porté ne la lit ») était fausse — `genestealer.py::_eligible_for_resurrect`
la lit. Étape 10 désormais **portée**.

**Ce qui avait fait échouer la recherche, et la parade** : elle interrogeait l'index de code de
ghidra-mcp — partiel, puis **supprimé** (`code_indexed: False` sur `t6dpr4k06g`) — et lisait son
absence comme une absence d'écrivain. Le balayage qui tranche ne cherche pas un TEXTE de pseudo-C
mais l'**encodage x86-64** : un `disp32` littéral `7c 01 00 00` précédé d'un ModRM `mod=10` (SIB géré,
base `rsp`/`r12` écartée = variable locale), dans **les deux sections de code** — `.text` seul rend 0
sur un binaire IL2CPP, le code AOT vit dans `il2cpp`. Résultat : **220 accès, 66 écritures**, dont **3**
sur un `UnitComponent` (`$$.ctor+0x133` init, `$$Copy+0x582` recopie, `RemoveUnitOperation$$Execute+0x4f6`).
Aucun hit n'est tu : les opcodes non classés sortent avec leur propriétaire.

⚠ **Valeur initiale = `-1`** (`c7 87 7c 01 00 00 ff ff ff ff`), une sentinelle : une unité jamais
RETIRÉE ne peut satisfaire aucun `Difference(CurrentPlayerTurnsStarted, TurnDefeated) == 1`. La
prémisse **P2** est donc vraie, et pour une raison **positive**.

⚠ **Et la pose côté port reste une COMPENSATION, désormais chiffrée** : `KillUnitOperation$$Execute`
n'appelle **jamais** `IOperationProcessor` slot 6 = `RemoveUnit` (ses appels sur cette interface sont
les slots 77, 80, 85, 99, 130, 143) — une unité **tuée** n'atteint pas l'écrivain. Résidu ré-ouvert
sur ce point : `#10015-r2`. Détail : `docs/rl/case-10015-allow-for-dead-owner.md`.

---

## 2. L'ÉNUMÉRATION des appelants du substrat `unit_state` — 19 clés, **une** atteignable

`--step ventilation`, AST (jamais grep), sur les **deux** faces : `EffectsState.active_effects`
(COMBAT) et `Scene.unit_state` (DÉCISION).

| verdict | clés | ce qu'il dit |
|---|---|---|
| `INERTE-VIVANT` | 10 | le sujet est un COMBATTANT du coup (attaquant / défenseur / caster / cible) |
| `INERTE-AMONT` | 6 | un gate antérieur refuse le cadavre avant la lecture |
| `NON-VENTILE` | 2 | le portail `Scene.effects` — face DÉCISION, résidu |
| **`ATTEIGNABLE`** | **1** | `damage_model.py::defender_fixed_armor` |

Ne pas recopier ces comptes : `--step ventilation` les rejoue et **rougit** dès qu'une clé apparaît
ou disparaît (cliquet d'exhaustivité, pas un seuil).

### Le rayon de souffle se MESURE, il ne se suppose pas

Le résidu dit « clé `traits` absente ⇒ une condition de TRAIT rend VRAI (#208) ». Exact — mais
`--step consommateur` mesure que **UNE SEULE** `is_active` de tout `engine/` lit cette clé :
`PinnedEffect.is_active` (`IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition` =
`Not(HasTrait(Self, 0x40f = TerminatorArmour))`). Un site n'est donc un gisement que si son sujet
peut être un cadavre **ET** que le consommateur aval lit cet effet-là. Sans cette borne, les 18 autres
sites se lisent tous comme portant le même risque.

### Le seul ATTEIGNABLE, et les DEUX écarts qui s'y superposent

`defender_fixed_armor` retenait un porteur d'aura sur trois critères — `OwnerComponent`,
`PositionComponent`, même équipe — et **aucun gate de vivacité**, là où ses **cinq** frères en portent
un (`build_hits_board` et `_crit_carriers` par `#57m`, `collect_additional_hit_groups` par
`uc.alive`, `_apply_ally_attack_damage_auras` et la boucle porteurs de `defender_modifiers` par
`hp <= 0`).

* **A — la clé `traits`** : **sans conséquence ici.** `defender_fixed_armor` ne lit que l'aura
  `FixedArmor` de `ProtectorImperative` ; le `Pinned` d'un cadavre y est invisible, actif ou non.
* **B — le gate absent** : c'est LUI l'écart, et il est plus large. Un cadavre-au-chargement
  projetait son aura. ⚠ **Il était INERTE EN FAIT, par une propriété du CAPTEUR, pas par un gate du
  port** : `KillUnitOperation$$Execute` appelle **trois** fois `RemoveEffects(killed, <step>)`, donc
  `decisionView.units[].effects` est vide pour un mort et le `if not effs: continue` l'écartait.
  **Aucun critère de VALEUR ne pouvait voir ce trou** — seul un état construit hors capture (greffe,
  seed synthétique) le révèle. C'est pourquoi la garde est un critère de **SOURCE** (AST).

Gate `uc.alive` posé ; les six balayages sont sous cliquet (`--step gates`).

---

## 3. La garde de la tranche précédente s'est RETOURNÉE, et ses deux bras n'isolaient RIEN

`test_ctx_traits_substrat_ventilation_offline.py` figeait le collapse. Ses deux bras (« mort du run »
vs « cadavre au chargement ») faisaient varier **trois** choses à la fois — `StatsComponent`,
`killed_this_turn`, `death_source` : un vert n'y était attribuable à **aucun** conjoint. C'est
exactement ce qui laissait le collapse passer pour un port.

`etat_crush` pose désormais les deux champs que le **vrai** crush grave, et **deux bras neufs isolent
chaque conjoint** en ne bougeant qu'un champ à partir du contrôle positif :

| bras | `_valid_dead_decoys` | ce qu'il isole |
|---|---|---|
| mort du run, crushé PAR le stepper | `[2]` | contrôle positif |
| cadavre AU CHARGEMENT | `[]` | rien de mesuré (`None` / `None`) |
| `killed_this_turn = False` | `[]` | **`IsKilledThisTurn` seul** |
| `Killer != stepper` | `[]` | **`AreEqual(Killer, stepper)` seul** |

Le critère de provenance change aussi : il cherchait un test `sc is None` — un **artefact** du port,
qui tenait par coïncidence et serait tombé en silence le jour où un `StatsComponent` sera posé sur les
cadavres. Il cherche désormais le **nom du champ natif**.

### Et le cliquet d'exhaustivité a mordu AU REBASE — 4ᵉ récidive du gisement

`#271-r4` (PR #831, mergée pendant cette tranche) a introduit
`playbook/non_owner_attack.py::_has_trait`, une lecture BRUTE de `c.traits` **non ventilée**.
Trouvé **au troisième rebase**, pas à l'écriture : ni la PR qui l'a créée, ni la relecture, ne
l'avaient vu. Ventilé `INERTE-VIVANT` (le sujet est `caster` = `UtilityAttackCase+0x10`, vivant par
construction du cas d'utilité ; et `Scene.ctx_by_id` vient de `combatSnapshot`, donc des vivants
seuls — `c is None` sur un cadavre rend FAUX, jamais un trait deviné).

C'est la **quatrième** fois que ce gisement se rouvre par notre propre cadence de portage (après
`_can_move` #a1e372d3, puis les trois de `#508`/`#498`). Le cliquet est ce qui le rend visible ; le
**rebase avant PR** est ce qui le rend visible **à temps**.

---

## 4. Le REGISTRE (`-r2`) — la question ne se tranchait pas où le résidu la posait

Le résidu demandait : « `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache` retire-t-il
l'entité à la mort ? ». La réponse se lit **un cran plus bas**, et elle est **structurelle**.

`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` :

```
if (!ability.get_AllowForDeadOwner()) {                          // ITriggeredAbility slot 8
    if (IsUnit(owner) && !IsAlive(owner))                        return 0; }
if (IsUnit(owner) && IsTriggersDisabled(owner))                  return 0;
```

⚠ **Cette fiche écrivait `IsAtomic(ability)` — FAUX NOM (#10015).** La dispense est
`ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` ; `IsAtomic` désigne une AUTRE propriété
(`ITriggerable` slot 0 = `get_AllowInAtomicMode`), lue par la MÊME fonction quelques instructions
plus bas. Le raisonnement structurel ci-dessous **tient mot pour mot** avec le bon nom — mais le
recensement qui en découle, lui, a été révisé (cf. `#462-…-r3-r1-r2-r1` §9).

Si le cache retirait les morts, **ce gate ET son exemption seraient tous deux inatteignables** — la
branche atomique n'existe QUE pour laisser passer un owner MORT. ⇒ le cache **conserve** les entités
mortes, et c'est `CanGetAbilityTrigger` qui trie.

**Conséquence pour le port** : `collect_triggered_abilities`'s `if sc is None: continue` et le gate
natif rendent le **même** verdict pour toute ability NON atomique (le port a déjà le gate `uc.alive`
dans `evaluate_trigger_operation`). Ils ne peuvent diverger que sur les **atomiques** — que le port
nomme `fire_on_death`. Recensement (`--step registre`, 9 porteurs) :

| état | porteurs | pourquoi |
|---|---|---|
| `INERTE-FACE` | 3 | `EffectTrigger` : `_owner_gate_applies` est FAUX, aucun gate d'owner |
| `INERTE-EVENT` | 5 | l'événement **EST** sa propre mort : il a eu lieu avant la capture |
| `DIVERGENT-DOUBLE-GATE` | 1 | `EnvAmbushResurrectAbility`, `On(TurnStart_Actions = 22)` |

⚠ **La face se résout par la MRO, pas par le nom de la base.**
`RitesOfMorkaiReviveTrigger(ReviveEffectTrigger)` dérive d'`EffectTrigger` par un **intermédiaire** :
un test de nom de base le rendait « NON TRIÉ », un faux rouge. Le probe charge la classe.

**Le port n'est PAS modifié**, et c'est motivé : le seul divergent est doublement gaté — (1) le
behaviour d'`EnvAmbushResurrect` est GLOBAL (toute autre instance inscrite produit le même effet) ;
(2) `_eligible_for_resurrect` exige `turn_defeated is not None`, que rien ne seede au chargement.
Inscrire les cadavres au registre serait un changement spéculatif au rayon non chiffré.
Reste OUVERT : le cas où le **seul** porteur Ambush du plateau est un cadavre-au-chargement.
Résidu `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1`.

---

## 5. Items 1 + 5 — RE faite, PORT non fait, et l'énoncé était déjà requalifié

Les deux résidus **convergent** : les trois abilities que `-b-r1-r1-r2` laisse ouvertes
(`CursedOfTheWalkingPox`, `Possession`, plus `Lakrimae_SummonPoxwalker` tranché à la main) sont
**exactement** les trois consommateurs natifs d'`On(0x35)` de `-c-r3-r1-r4-r1`. Et l'énoncé
« 5 call-sites d'`IsObjectOrSteppable` non portés » était **déjà requalifié le 2026-08-07** : ce qui
reste ouvert est le **portage de trois abilities entières**, pas des gates oubliés — aucune n'est dans
`ABILITY_TRIGGERS`, il n'y a donc **aucun arbre où greffer le conjoint**.

Les quatre `CreateTrigger` relus **verbatim** sur `rnca9r7q6c` :

| ability | conjonction | porté |
|---|---|---|
| `Triggered.Loki.CosmicHorror_OnMoveAbility` | `On(0x35, 1) & OwnerIsActor & (AreFriends(0x30,0x60) & HasTrait(0x60, 0x41d = Decoy))` | **OUI** |
| `Triggered.Loki.Lakrimae_SummonPoxwalker_Ability` | `On(0x35, 1) & AreEnemies(0x30,0x60) & IsDead(0x60) & <owner-is-actor> & NOT TriggeringAbilityIs & IsCanAddUnit(FreeTilesOrAdjacentFreeTiles(0x60)) & NOT IsObjectOrSteppable(0x60) & NOT HasTrait(0x60, 5 = Mechanical) & NOT AmountIsEqualOrGreater(Filter(AllUnits@0x20, AreFriends(Owner,it@0x68) & IsUnitWithVisualId(it, GetStringConstant(0))), Get(formulas, GetNumberConstant(0x78))) & IsInRange(0x30, 0x60, ContagionsOfNurgleRange(0x30,1,0))` | non |
| `Active.Loki.CursedOfTheWalkingPoxAbility` | `On(0x35, **0**) & OwnerIsActor & AreEnemies(0x30,0x60) & IsDead(0x60) & NOT TriggeringAbilityIs & IsCanAddUnit(0x60) & NOT IsObjectOrSteppable(0x60) & NOT HasTrait(0x60, 5 = Mechanical)` | non |
| `Active.Loki.PossessionAbility` | `On(0x35, 1) & OwnerIsActor & (AreEnemies(0x30,0x60) & NOT IsObjectOrSteppable(0x60)) & NOT TriggeringAbilityIs` | non |

⚠ **MESURE NEUVE, et la table de `-r4` ne la portait pas** : le **2ᵉ argument** d'`On` diffère.
`CursedOfTheWalkingPox` passe **`ignoreOverkill = 0`**, les trois autres `1`. Le balayage de `-r4`
comptait « qui écoute `0x35` » sans lire cet argument.

**Le 8ᵉ call-site d'`IsObjectOrSteppable` est d'une autre NATURE.**
`BounceAbility$$Prioritization(surrounding)` n'est pas un gate : c'est un
`SortByFormula(surrounding, <formule>, 0)`, et `IsObjectOrSteppable(it@0x68)` y sert de **condition
d'une `ConditionalAmount`**, c'est-à-dire de **clé de tri** :

```
ConditionalAmount(
    HasTrait(it@0x68, 3) & AreEnemies(it@0x68, Owner@0x30)
        & NOT AmountIsGreater(EmptyOrHasSteppableUnit(…), <const@0x20>),
    ConditionalAmount(AmountIsGreater(CanAddUnit(AdjacentTiles(Tiles(it))), Direct(1)),
                      <const@0x28>, <const@0x20>),
    ConditionalAmount(IsObjectOrSteppable(it@0x68), Negative(<const@0x20>), <const@0x18>))
```

Traiter ce site comme « un conjoint manquant » serait donc une faute de catégorie.

**Pourquoi le port n'est pas fait ici** : chacune de ces trois abilities est une tranche à part
entière (entrée au registre + `TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE` + behaviour + ses propres
tests), et le brief en groupait cinq. La RE ci-dessus est le travail amont ; le portage reste ouvert.
`Lakrimae_SummonPoxwalker` est le plus atteignable — porteur `deathTyphus` **dans le pool**, montage
`--equip-relic deathTyphus:Lakrimae:50` **déjà écrit et vert** dans
`test_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill_live.py` — et le seul dont le gate
`NOT IsObjectOrSteppable` sélectionne exactement la voie DÉGÂT que `-r4` a ouverte.

---

## 6. Contre-épreuves — 6 mutants, **4 détectés au premier passage**, 6/6 après réparation

| mutant | ce qu'il casse | rouges |
|---|---|---|
| M1 — gate `alive` de `defender_fixed_armor` retiré | le seul ATTEIGNABLE | **1** |
| M2 — `killed_this_turn` jamais posé au kill | l'ÉCRIVAIN | **0** → **1** |
| M3 — conjoint `IsKilledThisTurn` retiré | le lecteur | **2** |
| M4 — conjoint `AreEqual(Killer, stepper)` retiré | le lecteur | **1** |
| M5 — `PinnedEffect` ignore la clé `traits` | le contrefactuel | **2** |
| M6 — reset au turn-start retiré | le RESET | **0** → **1** |

⚠ **M2 et M6 ne mordaient PAS, et c'est la trouvaille de la matrice.** Tous les bras partaient d'un
état **synthétique** qui pose les champs à la main : ils gardaient le **LECTEUR**
(`_valid_dead_decoys`) et rien d'autre. **Un champ qu'aucun test n'écrit par le vrai chemin est un
champ que personne ne garde.** L'étage 5 les exerce sur le chemin réel (crush pour l'écrivain,
`StartTurnOperation.execute` pour le reset) — et son bras MORT est ce qui interdit un reset GLOBAL,
qui désarmerait le conjoint en silence.

Chaque mutation vérifiée mordante avant exécution ; arbre restauré et `git diff` vide ensuite.

## 7. Non-régression

| fichiers | résultat |
|---|---|
| `test_462_r4b_substrat_mort_appelants_offline.py` (neuf) | **14 verts** |
| `test_ctx_traits_substrat_ventilation_offline.py` (retourné) | **14 verts** |
| `test_462_…_c_r3_r1_r4_post_unit_kill_live.py` + `…_c_r3_r1_crush_steppable_live.py` | **17 verts** |
| `test_ambush_migration_live.py` + `test_decoy_foundation_live.py` | **8 verts** |
| `test_decoys_misdirection_migration_live.py` | **3 verts** |
| `test_steppable_decoy_tile_leaves_live.py` | **14 verts** |
| `test_doctrina_imperatives_live.py` + `test_contagions_aura_range_live.py` | **9 verts** |
| `test_beast_slayer_block_live.py` + `test_daemon_extra_block_live.py` | **4 verts** |

Les deux derniers lots sont là **parce que** le gate d'`defender_fixed_armor` touche la résolution
d'armure du défenseur, pas par confort.

## 8. Ce qui n'est PAS couvert

* **Aucun bras LIVE neuf.** Les deux conjoints portés sont des prédicats **purs** sur des champs
  ECS ; le régime qui les sépare (un decoy tué par un TIERS, puis un stepper ami qui marche sur sa
  tuile) exige deux tours et deux tueurs distincts — montage écrit mais non joué. Budget live partagé
  (`liveRunners 10` au moment de la tranche).
* **`killed_this_turn` n'a AUCUN canal de mesure.** Point d'ancrage natif à hooker si on le veut :
  `UnitComponent + 0x17a`, à publier dans `combatSnapshot.units[]` à côté d'`unitFlags` (qui est un
  `OrderedSet<UnitFlag>` et ne le porte pas). Exige une fenêtre de reinject — **non fait, et dit**.
* **La face DÉCISION n'est pas ventilée** : `Scene.effects` a ~30 appelants sous `playbook/`, et la
  `Scene` porte bien des morts (`build_scene_ctx` construit `pos_by_id`/`team_by_id`/`hp_by_id` et le
  `EffectsState` depuis TOUT `dv.units`, alors que `ctx_by_id` vient du `predictor` donc des vivants
  seuls). Même degradation, même consommateur unique.
* **Les trois abilities de §5 ne sont pas portées.**

## 9. Résidus ouverts

* ~~**`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1`**~~ — **RÉSOLU (2026-08-15)** : l'écrivain est
  `IdunBattle.Operations.RemoveUnitOperation$$Execute+0x4f6`, étape 10 désormais **portée** (cf. §1).
  La prémisse **P2** est confirmée VRAIE, et positivement : `TurnDefeated` naît à `-1`. Ce qui reste
  ouvert est la chaîne native qui retire une unité **tuée** — `#10015-r2`.
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1-r1`** — **la face DÉCISION du substrat `unit_state` n'est
  pas ventilée** (~30 appelants de `Scene.effects` sous `playbook/`).
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1`** — **le seul porteur Ambush du plateau peut être un
  cadavre-au-chargement**, et le port ne l'inscrit alors à aucun registre.
  ⚠ **RÉ-ÉNONCÉ (2026-08-15) : « là où le natif l'évalue (atomique) » est FAUX.**
  `EnvAmbushResurrectAbility` ne déclare **pas** `get_AllowForDeadOwner` (sa table de méthodes ne
  porte que `CreateTrigger`, `CreateBehaviour`, `GetValidDecoys`, `GetUnitsEligibleForResurrect`,
  `GetIsAlliedWithCurrentPlayerUnitTrigger`, `GetIsCurrentPlayerUnitTrigger`, `.ctor`) : elle
  **hérite** celle de `BaseTriggeredAbility`, dont le corps rend **FAUX** (`32 c0 c3`). Si son owner
  natif était une unité, le natif gaterait le cadavre dehors **comme le port** — et c'est le port qui
  serait trop permissif (il déclare `fire_on_death = True`). La question devient donc **l'identité de
  l'owner** : `Env*Ability` est une famille de **25** classes d'environnement, `EnvAmbushResurrect`
  n'apparaît **nulle part** dans le gameconfig (0 occurrence), et son `CreateTrigger` ne porte
  **aucun** prédicat d'owner. `BLOCAGE: etage`. Détail : `docs/rl/case-10015-allow-for-dead-owner.md` §5.
