# N8b — `EndTurnOperation.Execute` : le vecteur `On(0x17)` s'exécute **AVANT** `RefreshEffects`

Build `gqfc5mff6c`. Une question binaire, tranchée **au décompilé**, puis gardée par mutation
adversariale et confrontée live.

---

## 1. L'ordre natif

`IdunBattle.Operations.EndTurnOperation$$Execute` — les étapes se lisent dans cet ordre dans le
corps :

| # | Étape | Symbole |
|---|---|---|
| 1 | boucle sur `PlayerComponent.CurrentlyOwnedUnitIds` du joueur **finissant** : `turnsFinished@+0x5c += 1` | `IdunBattle.Operations.EndTurnOperation$$ResetAbilitiesThatResetOnTurnEnd`, `…$$DecreaseAbilityCooldowns` |
| 2 | boucle `GetAllUnits` : décay des boucliers + reset des stats du tour | `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields`, `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn` |
| 3 | même `+0x5c += 1` sur la Machine of War du joueur (`PlayerComponent+0x78`) | `…$$DecreaseAbilityCooldowns` |
| 4 | **si** `HasActivePlayer` : le vecteur de triggers `On(0x17 = TurnEnd)` | `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer`, puis slot 0x51 = `Core.Services.OperationProcessor$$EvaluateAbilities` (littéral `0x17`) |
| 5 | **tick d'un tour des effets à durée** | `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` |
| 6 | events de fin ; si `advance` (param_2) : `SystemActions` (ChangeTurn + StartTurn) | — |

**Deux lectures indépendantes donnent le même verdict**, et c'est ce qui rend la conclusion sûre :

- le bloc qui appelle le slot 0x51 avec `0x17` tombe en **fall-through** sur le bloc qui appelle
  `RefreshEffects` ;
- la branche `HasActivePlayer == 0` **saute directement** à `RefreshEffects`, en enjambant le
  vecteur — ce qui n'a de sens que si le vecteur le précède.

**Verdict : `On(0x17)` PUIS `RefreshEffects`.** Le port faisait l'inverse. L'observation héritée de
la PR #171 était donc **exacte** ; c'est sa justification qui était fausse (§3).

## 2. Ce que `RefreshEffects` fait — et ce qu'il ne fait pas

```
IdunBattle.Operations.EndTurnOperation$$RefreshEffects
  énumère les entités-EFFET du state
  gate : !Removed@+0x5f && HasTurns@+0x5d
    -> IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn
    -> 2 events (0x16 puis 0x15)
  puis, en sortie de boucle, slot 0x2f = Core.Services.OperationProcessor$$RefreshEffects
    -> IdunBattle.Operations.RefreshEffectsOperation$$Execute      (branche de retrait, synchrone)
```

**Aucun dégât n'y est infligé.** Le scénario « un DoT tique en fin de tour et entame les PV du
porteur, ce qui le disqualifie du gate PV-pleins de PileIn » ne correspond à **rien** dans ce corps :
les DoT de tuile passent par les events `0x12`/`0x14` de `IdunBattle.Operations.StartTurnOperation$$Execute`.

## 3. Conséquence réelle de l'écart — et son ampleur MESURÉE

Ce que le déplacement change : **les gates des triggers `On(0x17)` voient l'état PRÉ-tick**. Un effet
à durée qui s'éteint à cette fin de tour est encore actif quand ils s'évaluent ; symétriquement, un
effet posé par un de ces triggers subit le tick du même tour.

**Inventaire des consommateurs du vecteur** — re-dérivé des registres, pas cité d'un commentaire
(`probe_n8b_turnend_consumers.py`, 65 entrées balayées) :

| consommateur | voie | gate | lit un effet ? |
|---|---|---|---|
| `RadSaturationAbility` (branche 3) | dispatch générique `ABILITY_TRIGGERS` | `On(0x17) & OwnerIsActor & NOT HasFlag(owner, Moved)` | **non** |
| `PileIn` | bespoke dans `end_turn_summon_triggers` | `OwnerHasFinishedMinTurns(2) & IsUnitWithStatAmount(Health Cur == Max)` | **non** |

Aucun `EFFECT_TRIGGERS` n'écoute `TurnEnd`. **Donc aucun consommateur porté ne change de verdict
aujourd'hui** : le nombre de répliques PileIn et la consommation PRNG sont **inchangés** par la
correction. L'écart était **latent** — structurellement faux, sans symptôme observable sur le
périmètre porté. Il mord dès qu'un trigger `On(0x17)` lira un effet, ou qu'un effet à durée sera
posé par un tel trigger.

**Un troisième consommateur, lui, changeait bel et bien** : `land_deep_strike`
(`engine/runner/operations/spawn.py`), dont le gate est `has_effect(TeleportStrike_TeleportingIn)` —
et `has_effect` ne voit **pas** une instance `consumed`. Il était placé **après** le tick ; il est
désormais avant (position offline, aucun site natif dans `Execute`). Une instance à durée expirant à
cette fin de tour annulait donc l'atterrissage **silencieusement** : ni erreur, ni test rouge, et les
passives différées (aura `PathOfCommand`) n'étaient jamais initialisées.

## 4. Ce qui a été porté

| fichier | changement |
|---|---|
| `engine/runner/operations/turnflow.py` | `EndTurnOperation.execute` réordonné 1:1 sur les 5 étapes natives : bump → boucliers → (deep-strike, offline) → `On(0x17)` → tick d'effets + revert des stat-mods |

Rien d'autre ne bouge : `revert_stat_mods_of_removed_effects` reste **collé** au tick (mirror du
`RefreshEffectsOperation` que `RefreshEffects` appelle en sortie de boucle), et le bump passe devant
les boucliers pour épouser l'ordre natif (les deux touchent des champs disjoints — sans effet
observable, mais c'est l'ordre du corps).

## 5. Gardes — vues ROUGES avant le fix

`tests/engine/runner/test_endturn_order_live.py`, **10 tests**. Deux sondes symétriques, ni l'une ni
l'autre ne touchant au code de production (même patron que `CountingRng`) :

- `ProbeRng` — au **premier tirage PRNG** (= le `Maybe` du vecteur `On(0x17)`), capture l'état d'un
  effet-témoin à durée 1 ;
- `ProbeEffects` — au **premier `on_turn_end`** (= le tick), capture les tirages déjà consommés et le
  cardinal d'entités du `State`.

Mutation adversariale (tick d'effets replacé en tête d'`execute`) — **4 rouges, messages verbatim** :

```
AssertionError: le vecteur `On(0x17)` a vu l'effet-temoin DEJA consomme -> `RefreshEffects` s'est
                execute AVANT le vecteur ({'consumed': True, 'remaining': 0})
AssertionError: le tick de duree a vu 0 tirage(s) alors que le vecteur `On(0x17)` en consomme 1
                (1 `Maybe` par grot eligible) -> le tick a precede le vecteur
AssertionError: le tick de duree a vu 0 tirage(s) alors que le vecteur `On(0x17)` en consomme 3
                (1 `Maybe` par grot eligible) -> le tick a precede le vecteur
AssertionError: l'atterrissage deep-strike n'a pas eu lieu : le tick l'a precede ([])
```

Les 5 autres tests **restent verts sous la mutation** — c'est voulu : ce sont les gardes de
**non-régression** (verdict de gate PileIn et consommation PRNG identiques dans les deux ordres),
et leur insensibilité est exactement la preuve chiffrée du §3.

**Troisième observable, LIVE** (`test_replica_exists_before_the_tick_live`) : sur un vrai runner
(donc avec board, seul cas où `execute_pilein_replica` spawne), au moment du tick de durée la
réplique PileIn est **déjà** dans le `State` — `entities == before + spawned` — et `rolls >= 1`.

## 6. Mesure de non-régression

| lot | résultat |
|---|---|
| `test_endturn_order_live.py` | **10 passed** |
| `test_pilein_owner_turns_live.py` + `test_maybe_trigger_rng_live.py` | **36 passed** |
| `test_turnflow_live.py` + `test_rad_saturation_live.py` | **7 passed** |
| `test_effect_duration_rounds_live.py` + `test_seeded_eager_statmod_expiry.py` + `test_tile_effect_dynamics_live.py` | **15 passed** |
| `test_summon_trigger_live.py` + `test_effect_stun_live.py` | **2 passed** |

Généralisation, `probe_pilein_owner_turns.py` sur deux configurations **autres** que celle du test :

```
seed 31337 / MC1_67      age 0 : live 0 = port 0      age 1 : live 5 = port 5   (spawn 1/1)
seed  4242 / MC1_44      age 0 : live 0 = port 0      age 1 : live 1 = port 1   (spawn 0/0)
```

Chiffres **identiques** à ceux de la case-doc N8, mesurés avant le réordonnancement ⇒ l'accord live
bit-exact est préservé.

## 7. Ce qui n'est PAS couvert

- **Le DRAIN du pump natif.** `Core.Services.OperationProcessor$$EvaluateAbilities` →
  `IdunBattle.Operations.EvaluateTriggerOperation$$Execute` a deux branches : soit elle enfile un
  `BattleEvent`, soit elle appelle `…$$ExecuteInternal` **synchronement** (branche nominale). Mais
  `ExecuteInternal` **enfile** les triggered-abilities pendantes, drainées par
  `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities`. Ce qui est établi
  ici, c'est que le **DISPATCH** (donc l'évaluation des `ShouldTrigger`) précède `RefreshEffects` ;
  **l'instant exact du drain des BEHAVIOURS** relativement à `RefreshEffects` n'a pas été tranché.
  Le port collapse dispatch et drain (mirror documenté #201) ⇒ il exécute les behaviours avant le
  tick. Aucune garde ne repose sur ce point : le seul observable qui en dépendrait — la durée
  résiduelle d'un effet **posé** par un trigger `On(0x17)`, p. ex. le `Contaminated` de
  RadSaturation — n'est **pas** testé. À rouvrir si une divergence de durée apparaît sur ce chemin.
- **`ActorStatisticsComponent.ResetThisTurn`, `ResetAbilitiesThatResetOnTurnEnd`,
  `DecreaseAbilityCooldowns`** : toujours non suivis offline (déféré hérité, cf. en-tête de
  `turnflow.py`).
- **`HasActivePlayer`** : la garde native de l'étape 4 n'a pas d'équivalent porté (le runner a
  toujours un joueur actif tant que la bataille tourne). Non porté, non mesuré.
- **L'ordre relatif bump ↔ boucliers** est désormais celui du natif, mais **aucun test ne le
  distingue** : les deux étapes écrivent des champs disjoints (`UnitComponent.turns_finished` vs
  `ShieldComponent`).
