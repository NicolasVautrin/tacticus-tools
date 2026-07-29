# La jauge de MUNITIONS d'une Machine of War en runner isole

Question : *pourquoi la jauge de munitions d'une MoW ne monte-t-elle jamais dans un runner isole,
est-ce reparable cote port/harnais ou une propriete du mode de jeu ?*

**Reponse en une ligne** : la jauge n'est pas censee monter — **aucune operation native ne
l'incremente**. Elle est POSEE une fois au setup depuis la `BattleConfiguration` et ne fait que
DESCENDRE. Le seed BC capture une bataille a `MachineOfWarAmmo = 0`, donc le runner reproduit
fidelement une bataille sans munition. Le levier est **la BC, une ligne**, pas le moteur.

Re-derivable : `python scripts/python/probe_mow_ammo_gauge.py` (3 runners, ~3 min).

## 1. Ou vit la jauge

`IdunBattle.Entities.Components.PlayerComponent`, **`+0x6c`** (int) = munitions disponibles ;
**`+0x70`** (int) = munitions deja depensees (compteur cumulatif, remonte au meta).

Elle est **PAR JOUEUR**, pas par machine — piege de lecture :
`IdunBattle.View.FSM.VisualBattleQuery$$GetPlayerAmmoFromMachine` prend une MoW en entree mais
resout `IdunBattle.Entities.EntityExtensions$$GetOriginalPlayer` ->
`IdunBattle.Entities.EntityExtensions$$GetPlayerComponent` -> `return *(int *)(pc + 0x6c)`.
`IdunBattle.Core.Services.BattleQuery$$HasPlayerEnoughAmmo` fait de meme :
`return cost <= *(int *)(pc + 0x6c)`.

## 2. Les DEUX seuls ecrivains de `+0x6c`

| operation | effet sur `+0x6c` |
|---|---|
| `IdunBattle.Operations.AddPlayerOperation$$Execute` | `pc+0x6c = param_8` — **initialisation, une fois** |
| `IdunBattle.Operations.SpendAmmoOperation$$Execute` | `pc+0x6c = System.Math.Max(pc+0x6c - cost, 0)` ; `pc+0x70 += cost` |

**Il n'y a pas de troisieme.** La recherche de symboles sur
`SetAmmoOperation|AddAmmo|GainAmmo|RefillAmmo|IncreaseAmmo|RestoreAmmo|AmmoOperation|AmmoBehaviour`
ne rend que `SpendAmmoOperation$$Execute` et son step-handler de vue
`IdunBattle.View.BattleStream.StepHandlers.SpendAmmoStepHandler$$ExecuteInternal`. La jauge est
donc **monotone decroissante** pour toute la duree d'une bataille. C'est une ressource **META** du
compte joueur (`thor.Menu.ResourcesBar$$OnMachinesOfWarAmmoTapped`,
`idun.ui.InventoryScreen$$UpdateMachinesOfWarAmmoWidget`), consommee en bataille puis reportee au
meta via `+0x70` (`IdunBattle.Core.Services.BattleStatisticQuery$$GetHumanPlayerAmmoUsed`,
`Idun.Source.IdunMeta.Logic.UserProgress.Location.CompleteLocationHandler$$HandleSpendMachineOfWarAmmo`).

## 3. D'ou vient la valeur initiale — le levier

`IdunBattle.Operations.SetupGameOperation$$AddPlayers` boucle sur les `PlayerConfiguration` de la
BC et appelle `AddPlayer` avec, en 7e argument, `*(int *)(playerConfiguration + 0x20)`.
Correspondance etablie champ par champ contre `data/seed-bc.json` (les trois joueurs du seed
portent exactement ces valeurs) :

| `PlayerConfiguration` | champ BC | -> `PlayerComponent` |
|---|---|---|
| `+0x10` | `Name` | `+0x18` |
| `+0x18` | `PlayerType` | `+0x20` |
| `+0x1c` | `TeamId` | `+0x24` |
| **`+0x20`** | **`MachineOfWarAmmo`** | **`+0x6c`** |
| `+0x30` | `StartRarity` (Nullable) | `+0x7c` |
| `+0x38` | `ReinforcementShield` | `+0x84` |

Le seed BC partage porte `MachineOfWarAmmo: 0` sur les **trois** joueurs (`player` PlayerType 0,
`enemy_1` PlayerType 1, `Environment` PlayerType 2). D'ou la jauge a zero.

**Levier** (deja utilise par `probe_r14_mow_decision.py`, `probe_129`, `probe_91`, `probe_123`,
`probe_131`) : patcher le seed BC **hors `data/`** avant `rl_duel build --seed-bc` —

```python
for _pid, p in bc["Player"]["Players"].items():
    if p.get("PlayerType") != 2:          # 2 = Environment
        p["MachineOfWarAmmo"] = 5
```

MESURE (`probe_mow_ammo_gauge.py`, MoW `necroReanimator`, board MC1_67, seed 777) — seule la BC
change entre les deux runners : `1223 ReanimationBeam` passe de `hasAmmo = False` a
`hasAmmo = True`. La jauge est donc bien celle-la, et elle est pilotable.

## 4. Le gate MUNITIONS est cote DECISION, pas cote EXECUTION

Le 4e terme de `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed`
(`!AmmoCost(@0x38).HasValue || HasEnoughAmmo(@0x40)`) est ce que le generateur d'action natif teste
avant de proposer une ability. `applyAction` du harnais, lui, **execute directement**.

MESURE, cooldown purge et action rendue dans les deux cas :

| `MachineOfWarAmmo` | entites-effet 1547 | `hasAmmo` avant -> apres |
|---|---|---|
| 1 | 0 -> **1** | True -> **False** (munition CONSOMMEE) |
| 0 | 0 -> **1** | False -> False |

Donc : a zero munition le cast **passe quand meme** et pose son effet ; c'est `SpendAmmoOperation`
qui echoue silencieusement (branche `pc+0x6c < cost` : il logue et sort sans decrementer). Le
manque de munitions **n'empeche pas** l'execution par `applyAction` — il empeche l'IA et l'UI de
CHOISIR l'ability. Les docstrings de `engine/battle_query.py:can_currently_be_used` et
`engine/runner/components.py:ActiveAbility.can_currently_be_used` sont donc justes et confirmees.

## 5. `hasAmmo = false` : CONSEQUENCE, jamais cause

`IdunBattle.Operations.AddMachineOperation$$InitializeAbilitiesStatus` ecrit, par ability :

```
ammoCost(@0x38) = (playerComponent+0x20 != 1 && ability.AbilityId == machineComponent+0x30)
                  ? abilityConfig.GetNumberConstant(0x6b)   // 0x6b = munitionsCost
                  : null
hasAmmo(@0x40)  = ammoCost.HasValue ? BattleQuery.HasPlayerEnoughAmmo(playerId, ammoCost) : true
```

Deux consequences lisibles :

* le cout n'existe que sur **l'ability principale de la machine** (`ability.AbilityId ==
  MachineComponent+0x30`) — les autres actives du kit n'ont jamais d'`ammoCost` ;
* il n'existe **pas du tout** quand `PlayerComponent+0x20 == 1`, c'est-a-dire `PlayerType = 1` =
  l'IA. Une MoW ennemie n'est **jamais** bloquee par les munitions, quel que soit son stock.

`SpendAmmoOperation$$Execute` recalcule ensuite ce meme flag sur toutes les abilities de l'entite
apres chaque depense.

## 6. Ce que la mesure de depart imputait a tort a la munition

L'analyse de #237 (« `1223` a `hasAmmo = false`, donc le cast est accepte mais no-ope, donc 1547
n'est pas posable ») est **REFUTEE par mesure** : avec `hasAmmo = true`, le cast no-ope **de la
meme facon**. Les deux vrais obstacles etaient ailleurs, et ils sont cumulatifs :

1. **`initialCooldownTurns = 1`** (gameconfig `ReanimationBeam`) : au tour 1 le 3e terme de
   `get_CanCurrentlyBeUsed` est deja faux. Le champ `usable` publie par `decisionView` ne le
   montre PAS — c'est `CanStillBeUsed@0x28`, le PREMIER terme seul. `abilityReason` le montre
   (`abilityState.cooldown = 1`).
2. **une MoW n'a qu'UNE action par tour** : le cast prerequis de `1224
   NanoscarabRepairProtocols` (exige par
   `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetDynamicInvalidTargetReason`,
   qui refuse toute cible sans l'effet `0x609 = 1545` et non Mechanical) consomme cette action, et
   le beam qui suit dans le MEME tour no-ope.

Recette qui MARCHE : 2 `endturn` (purge du cooldown initial) -> cast `1224` sur un allie
Mechanical -> 2 `endturn` (l'action revient) -> cast `1223`. L'effet 1547 est alors pose.

## 7. Rayon de souffle de 1547 — MESURE (ferme `case-229` section 3)

Une fois 1547 reellement pose, la ventilation demandee par
`docs/rl/case-229-effect-triggers-active-inventory.md` section 3 est **mesurable** :

```
effectAbilityStates(1547)  -> 1 entite : {effectId 103, source 79, active True}
decisionView units[] seul  -> defaut 0 | includeInactive 0
decisionView mows[]        -> defaut 1 | includeInactive 1
   {effectId 103, name 'ReanimationBeam_Revive', remaining 2, level 1, active True}
temoin de canal (entrees `active: false`, tous types) : 3
```

**1547 EST dans le rayon de souffle** d'un `includeInactive` global, mais par le canal
**`mows[]`** : le porteur est la MACHINE (l'effet vit sur le Reanimator, pas sur la cible du
beam). `frida/hooks/features/ai-step/rpc-decision.ts` remplit `units[].effects` ET `mows[].effects`
depuis **la meme** `readEffectsByUnit(statePtr, { includeInactive })` — pour une machine la cle est
`casterId`. Lire `units[]` seul fait donc conclure a tort « effet non publie » : c'est exactement
l'erreur que la premiere passe de mesure avait commise.

Corollaire : le constat « `mows[].effects` est vide dans les DEUX canaux meme apres un cast qui a
mute » n'etait **pas** un trou de capteur. Il etait vide parce qu'**aucun effet n'y etait pose** —
le cast de 1224 pose 1545 sur la CIBLE, pas sur la MoW. Des qu'un effet vit sur la machine, les
deux canaux le publient. Aucun capteur a modifier.

## 8. Ce qui n'est PAS couvert

* Un 1547 **inactif** n'a pas ete produit (rien ne le desactive dans ce scenario) : que
  `mows[].effects` honore `includeInactive` est etabli par LECTURE du hook (meme map, meme option),
  pas par une instance inerte observee.
* `applyAction` rend `mutated: false` / `changes: []` alors que l'effet EST pose sur la machine :
  le champ ne voit pas les poses d'effet sur une entite `Machine`. Non investigue — capteur, hors
  perimetre (aucune reinjection).
* La valeur de `MachineOfWarAmmo` d'une vraie bataille (cote meta) n'a pas ete relevee : le seed BC
  capture une bataille a 0, ce qui ne dit pas ce que le jeu y met en general.
