# #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 — `On(0x35 = PostUnitKill)` entre dans la séquence de mort

Le résidu ouvert par `-r1` : le 5e événement de `IdunBattle.Operations.KillUnitOperation$$Execute`
était publié par `move_death.py::post_unit_kill_triggers_for_move`, en tête d'`after_move_triggers`.
Donc **plus tard** que le natif (après `UpdateCharging` / `SetMovedFlag`) et pour le **seul**
crush-par-move. Double écart, d'**ORDRE** et de **COUVERTURE**.

| volet | verdict |
|---|---|
| rang natif de `On(0x35)` | **PORTÉ** — foyer `damage.py::_kill_unit_operation`, un seul émetteur (cliquet AST) |
| branche REVIVE | **PORTÉ** — le natif publie l'event même quand un revive ANNULE la mort |
| garde HEAL | **PORTÉ** — son `return` saute `On(0x35)` |
| couverture des voies | **PORTÉ** — dégât, crush (4 sites), `KillUnitBehaviour` |
| chemin DÉGÂT confronté LIVE | **MESURÉ sur le NATIF** — `Lakrimae_SummonPoxwalker`, 3 bras |

## 1. Le rang se lit à la PILE d'accolades, jamais à la PROFONDEUR

C'est le cœur de la tranche, et c'est ce qui avait produit une affirmation fausse tenue pendant
deux tranches. Les quatre derniers events sont **tous à la profondeur 9** — d'où la docstring de
`test_revive_cancels_death_events_live.py` : « les quatre autres dispatchs sont TOUS à l'intérieur
de ce bloc (profondeur d'accolades 9 vs 7 pour `On(1)`), **sans `else`** ». Les deux moitiés de
cette phrase sont fausses. Décompilé `rnca9r7q6c`, lignes du décompilé Ghidra :

```
L1111  if (unitComponent != null) {
L1131      if (!PendingRevive.HasValue) {              <- GARDE REVIVE  (+0x81c)
               On(2) ; RemoveEffects(0) ; RemoveEffects(1) ; On(0) ; On(0x36)
L1971          if (health.hp > 0) return;              <- GARDE HEAL    (+0xf35)
               RemoveEffects(2) ; processor.<slot 0x55>
L1997      } else { matchState.<slot 0x63>(killed) }   <- L'ELSE EXISTE (+0xfcc)
           PendingRevive@+0xa8..+0xe8 = 0
L2033      if (dispatcher != null) { On(0x35) ; return }   (+0x10ac)
```

Piles d'ouverture, mesurées :

| event | pile |
|---|---|
| `On(2)`, `On(0)`, `On(0x36)` | … `L1111` → **`L1131`** (la garde revive) |
| `On(0x35)` | … `L1111` → **`L2033`** (le seul null-check du dispatcher) |

⇒ **`On(0x35)` est le SEUL des cinq que la garde revive n'annule pas.** Trois conséquences, toutes
lues, aucune déduite :

1. la branche **REVIVE** le publie aussi (le natif sort du `if/else` avant lui) ;
2. la **GARDE HEAL** le saute (son `return` précède) ;
3. **aucun** octet de `KillUnitOptions` ne le gate — les quatre octets lus (`+0x44`, `+0x45`,
   `+0x46`) le sont ailleurs, cf. `-r1` — donc il part pour **toutes** les voies qui traversent
   `Execute`.

Les cinq events partagent le **même** `AbilityEntities` : `memset(&local_298, 0, 0x128)` puis
`Actor = killer` (`+0x00`), `+0x08 = killer`, `Target = killed` (`+0x10`), les tuiles, et
`KillUnitOptions+0x04..+0x20` recopié dans `TriggeringAbility`. La struct est bâtie **une** fois et
republiée telle quelle — d'où l'ordre d'arguments et le repli `actor = dying` du vecteur porté,
identiques aux quatre autres.

## 2. Ce que le port fait maintenant

`damage.py::_kill_unit_operation` — **UN SEUL émetteur**, gardé par cliquet AST :

```
On(1) -> garde revive --(revive)--> [kill_cancelled_by_revive] + On(0x35)   <- branche `else`
                      --(sinon)---> On(2) -> RemoveEffects(0) -> RemoveEffects(1)
                                    -> On(0) -> On(0x36)
                                    -> garde HEAL (hp > 0 ? RETURN, sans On(0x35))
                                    -> RemoveEffects(2) -> On(0x35)
```

`move_death.py::post_unit_kill_triggers_for_move` **disparaît** — la garder produirait une **double
émission** pour le chemin MOVE. Elle ré-identifiait le crushé par CO-LOCALISATION parce que le port
crushait alors sans émettre ; le foyer connaît désormais `killer` et `killed` directement.

Les **trois** appelants du foyer, donc les trois voies qui gagnent l'event (inventaire dérivé,
`--step voies`) : `damage.py::_verify_deaths` (drain, mort par DÉGÂT),
`movement.py::_kill_steppable_kill_unit` (CRUSH — atteint par les **quatre** sites de
`_kill_steppable_units` : `movement`, `revive`, `resurrect`, `spiritual_leader`) et
`lifecycle.py::Kill.execute` (`KillUnitBehaviour`, feuille DSL).

## 3. Le blast radius NATIF, mesuré — pas inventorié

Balayage des **226** `<X>$$CreateTrigger` qui appellent `IdunBattleLogic.Entities.DSLTriggers$$On`
(xrefs des trois surcharges), décompilés et lus : **226/226 lus**, **4** écoutent `0x35`, **6**
rendent un argument non littéral.

| classe | portée ? |
|---|---|
| `Triggered.Loki.CosmicHorror_OnMoveAbility` | **OUI** (seul consommateur porté) |
| `Triggered.Loki.Lakrimae_SummonPoxwalker_Ability` | non |
| `Active.Loki.CursedOfTheWalkingPoxAbility` | non |
| `Active.Loki.PossessionAbility` | non |

⚠ Le premier jet de ce balayage a rendu **« 0 »** — parce que `GhidraMCP.call` ne lit que
`content[0]`, donc un batch de 20 ne rendait qu'**une** fonction (12 lues sur 226). Un capteur qui
rend zéro n'est pas une mesure ; le compteur `items lus` du second jet est ce qui le rend
vérifiable.

`CosmicHorror_OnMoveAbility$$CreateTrigger`, relu nœud par nœud :

```
On(0x35, ignoreOverkill = 1) & get_OwnerIsActor
  & ( AreFriends(sel+0x30, sel+0x60) & HasTrait(sel+0x60, 0x41d = Decoy) )
```

**Aucune gate de mouvement**, malgré le nom de la classe — ni `NOT HasTrait(Steppable)`, ni
`TriggeringAbilityIsNone`. Le crush n'est donc que la voie la plus *fréquente*, pas la condition :
le Patermine se soigne dès qu'il est le **tueur** d'un allié `Decoy`, quelle que soit la voie.

## 4. Le chemin DÉGÂT, confronté LIVE — en changeant de CONSOMMATEUR

Le consommateur **porté** n'est atteignable que par le CRUSH : le kit du Patermine (`Eviscerate`,
5 coups mêlée) n'a **aucune AoE friendly-fire**, donc rien ne le rend tueur d'un allié `Decoy`
autrement qu'en marchant dessus. Le régime DÉGÂT serait donc **dégénéré** côté port — et un accord
en régime dégénéré ne prouve rien. On en sort en changeant de consommateur.

`Lakrimae_SummonPoxwalker_Ability$$CreateTrigger` (relique `Lakrimae`, porteur `deathTyphus`,
**dans le pool**) :

```
On(0x35, ignoreOverkill = 1) & AreEnemies(Owner@0x30, Target@0x60) & IsDead(Target@0x60)
  & <owner-is-actor> & NOT TriggeringAbilityIs(<implicit>)
  & IsCanAddUnit(FreeTilesOrAdjacentFreeTiles(Target@0x60))
  & NOT IsObjectOrSteppable(Target@0x60) & NOT HasTrait(Target@0x60, 5 = Mechanical)
  & NOT AmountIsEqualOrGreater( Filter(AllUnits@0x20,
                                       AreFriends(Owner, it@0x68) & IsUnitWithVisualId(it@0x68,
                                                                    GetStringConstant(0))),
                                Get(formulas, GetNumberConstant(0x78)) )
  & IsInRange(Owner@0x30, Target@0x60, ContagionsOfNurgleRange(Owner@0x30, 1, 0))
```

Son `NOT IsObjectOrSteppable(Target)` **exclut structurellement le crush** : ce consommateur ne
peut fire que sur une mort par DÉGÂT. Un Poxwalker qui apparaît est donc la preuve **directe** que
le natif publie `On(0x35)` pour cette voie.

Montage (`--equip-relic deathTyphus:Lakrimae:50`, board `MC1_67`, ennemi à 1 PV / armure 0 placé
**adjacent** à Typhus — il meurt du dégât d'aura de Nurgle à l'ouverture, sans aucun mouvement) :

| bras | relique | ennemi adjacent | `deathPoxwalker` |
|---|---|---|---|
| POSITIF | `Lakrimae` | `orksNob` (non-mécanique) | **1**, sur la tuile du mort |
| TÉMOIN | aucune | `orksNob` | **0** (même mort) |
| CONTRE-ÉPREUVE | `Lakrimae` | `necroWarden` (**Mechanical**) | **0** (gate `NOT HasTrait(5)`) |

Les deux bras négatifs mordent, et chacun pour une raison différente : sans la relique le mort est
le **même** (ce n'est donc pas la mort qui invoque, c'est le trigger) ; avec un mécanique, relique
et mort sont là (c'est donc bien **ce** trigger, avec **ses** gates). `worldJakhal` — 1 PV lui
aussi, mais **loin** — reste vivant dans les trois bras : témoin gratuit du gate `IsInRange`.

⚠ `Lakrimae` **n'est pas portée**. Ce bras mesure le **natif** ; il ne confronte pas un port.

## 5. Le crush, confronté LIVE côté PORT

Le seul consommateur porté, sur le seul régime où il soit atteignable en bataille. Trois choses à
la fois, et la troisième est neuve :

* le heal a lieu (non-régression — il avait déjà lieu, par un autre émetteur) ;
* il part **dans** `MoveUnitOperation.execute`, donc avant tout le pipeline after-move : c'est
  l'écart d'ORDRE, rendu observable par un compteur pris **entre** les deux appels ;
* il ne part **qu'une fois**. Déplacer une émission sans retirer l'ancienne est le mode de panne
  exact de cette tranche, et l'ancien émetteur (`after_move_triggers`) est toujours appelé là.

Le point d'observation de `test_cosmic_horror_live.py` a dû **déménager** : il lisait le *retour*
d'`after_move_triggers`, qui ne porte plus la trace. Il observe désormais l'ability **à la source**
— invariant au rang de l'émission, même geste que `--step consommateurs` pour `ActOfFaith` /
`TheBetrayer`. Les quatre garanties (le trigger fire, sur quel decoy, pour quel montant, les PV
bougent) sont conservées ; deux s'y ajoutent (fire **pendant** le move, **une seule** fois).

## 6. Validation

* **Probe `probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill.py`** — 6 steps, 2 contre-épreuves
  intégrées (`--mutate rang-move` fait tomber la 5e valeur sur les trois voies ;
  `--mutate revive-sec` ramène la branche revive à `[On(1)]`).
* **`test_462_…_c_r3_r1_r4_post_unit_kill_live.py` — 11 verts** : 5 bras STRUCTURE (les cinq events
  ×3 voies, la branche revive, la garde HEAL, le cliquet AST, les deux voies du consommateur),
  1 bras LIVE crush, 3 bras LIVE Lakrimae.
* **Matrice de mutants — 6 sur 6 rouges** (arbre restauré après chacun) :

| mutant | ce qu'il casse | rouges |
|---|---|---|
| M1 — émission finale retirée (état d'AVANT) | l'émission | **6** |
| M2 — la garde HEAL ne saute plus `On(0x35)` | la garde HEAL | **1** |
| M3 — branche revive : `return` sec | la branche revive | **1** |
| M4 — un SECOND émetteur republie depuis le move | le rang **et** le doublon | **2** (AST + live) |
| M5 — `_kill_steppable_units` perd son gate `uc.alive` | la sélection du crush | **1** |
| M6 — `On(0x35)` publié avant `On(0x36)` | l'ordre | **4** |

  ⚠ **M5 ne mordait PAS au premier passage** — et c'est la trouvaille de la matrice. Le
  cadavre-au-chargement est écarté **plus bas**, par un substrat de traits vide
  (`sc is None` → `has_trait([], Steppable)` faux) : **deux** gates protégeaient, le test n'en
  isolait **aucun**. Un 3e régime a été ajouté — le cadavre **DU RUN** (mort, mais avec son ctx et
  ses traits `Steppable`), que seul `uc.alive` peut refuser. C'est aussi le régime **réel** du 2e
  pas d'un chemin : un steppable crushé au pas N est encore sur sa tuile au pas N+1.

* **Gardes RETOURNÉES** — trois annonçaient leur condition de retournement, elle est arrivée :
  `test_…_c_r3_r1_r1_crush_death_events_live` (QUATRE → **CINQ** events),
  `test_…_c_r3_r1_crush_steppable_live` (+ assertion de **non-doublon** : son assertion d'ENSEMBLE
  y était structurellement aveugle), et le site converti de
  `test_ctx_traits_substrat_ventilation_offline`, qui a **disparu** — d'où un bras `DISPARUS` neuf
  (le site n'est pas revenu / le porteur existe / il porte son gate) plus la garantie ré-assertée
  sur le **chemin réel**.
* **Docstrings corrigées, parce que RÉFUTÉES** : `test_revive_cancels_death_events_live` et
  `test_tainted_narthecium_revive_live` (« TOUS dans ce bloc, sans `else` » — faux deux fois) ;
  `cosmic_horror.py` (`0x37=55` / `0x36=54` décalés d'un cran — les valeurs justes sont
  `0x36=54 UnitDefeated` et `0x35=53 PostUnitKill` ; les **littéraux**, eux, n'avaient jamais été
  écrits : le port lit l'enum).
* **Non-régression : 163 verts sur 19 fichiers**, en cinq passes de 4 en parallèle —
  `462_…_c_r3_r1_r4_post_unit_kill_live` (11), `cosmic_horror_live` (6),
  `462_…_c_r3_r1_crush_steppable_live` (6), `462_…_c_r3_r1_r1_crush_death_events_live` (7),
  `revive_cancels_death_events_live` (3), `tainted_narthecium_revive_live` (12),
  `death_queue_ordering_live` (22), `kill_unit_trigger_channels_live` (3),
  `spiritual_leader_live` (5), `ambush_migration_live` (5), `narthecium_revive_live` (9),
  `decoys_misdirection_migration_live` (3), `389r2_kill_unit_remove_effects_offline` (10),
  `kill_unit_trigger_channels` (12), `462_…_bond_removal_live` (4), `death_nova_live` (5),
  `ctx_traits_substrat_ventilation_offline` (12), `steppable_decoy_tile_leaves_live` (14),
  `hypersensory_moveandspawndecoy_live` (5).
  Les quatre voies de crush (`movement`, `revive`, `resurrect`, `spiritual_leader`) sont dans le
  lot **parce que** cette tranche leur ajoute un événement, pas par confort.

## 7. Non couvert, et nommé

* **Les trois autres consommateurs natifs ne sont pas portés** (§3) — donc les voies revive /
  resurrect / `KillUnitBehaviour` gagnent l'événement sans qu'aucun consommateur porté ne le lise.
  Le port est fidèle au décompilé sur ces voies ; il n'y est pas *confronté*. Résidu `-r4-r1`.
* **Le régime « decoy allié tué par une AoE »**, que la tranche redoutait comme effet de bord, est
  le comportement **NATIF** (§3, aucune gate de mouvement) — mais il n'a **aucun porteur
  atteignable** : le Patermine n'a pas d'AoE friendly-fire. Le bras `--step consommateur` du probe
  **monte** ce régime, il ne le **rencontre** pas.
* **Six `CreateTrigger` dont l'argument d'event n'est pas un littéral lisible** au décompilé
  (`OiWatchItAbility`, `EnvArmourSupplies`, `EnvDefenderHealthBuff`, `EnvFortified`,
  `EnvStrategicBuff`, `GetStuckIn`) : ils ne sont ni comptés dans les 4, ni écartés. Résidu
  `-r4-r2`.
* **`AddUnitOperation$$KillSteppableUnits`** (le 4e site natif, via un `DamageAppliedResult`) n'a
  toujours aucun équivalent porté. Écart préexistant, inchangé.
* **`UnitFlag` de mort** (`0xd` sous `+0x45`, `Remove(0xf)` / `Add(6)`) : toujours non portés, le
  port collapse l'état « mort » dans `UnitComponent.alive`. Écart préexistant.

## 8. Résidus ouverts

* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1`** — **les trois autres consommateurs natifs d'`On(0x35)`
  ne sont pas portés.** `Lakrimae_SummonPoxwalker_Ability` (relique `Lakrimae` / `deathTyphus`,
  porteur DANS le pool, montage `--equip-relic` **déjà écrit et vert** dans le test de cette
  tranche), `CursedOfTheWalkingPoxAbility` et `PossessionAbility` (deux `Active.Loki`, dont le
  `CreateTrigger` n'a pas été lu ici). Le premier est le plus atteignable **et** le seul dont le
  gate `NOT IsObjectOrSteppable` sélectionne exactement la voie que cette tranche ouvre : le
  porter donnerait au chemin DÉGÂT un consommateur **porté**, donc une confrontation natif↔port
  au lieu d'une mesure du natif seul.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2`** — **six `CreateTrigger` dont l'événement écouté n'est
  pas lisible** comme littéral dans le décompilé (§7). Le balayage les **compte** plutôt que de
  les rabattre sur « n'écoute pas `0x35` » ; il faut les lire un par un pour clore l'inventaire
  du blast radius.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r3`** — **la trace du crush est JETÉE par
  `MoveUnitOperation.execute`.** `_kill_steppable_units` rend les ids crushés, pas la trace des
  vecteurs joués, et son retour est jeté par l'Operation. Conséquence mesurée ici : le test du
  consommateur a dû changer de point d'observation (§5). Aucun écart de comportement — un écart
  d'**observabilité**, qui rendra tout futur bras sur les events d'un crush plus coûteux à écrire.
