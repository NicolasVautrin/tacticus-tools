# case-101 — « a bougé ce tour » : UN seul store (le `UnitFlagsComponent`), pas deux

**Verdict : fork de port résolu.** Le fait natif « cette unité a bougé ce tour » vit dans **un seul
endroit** — le flag `UnitFlag.Moved = 0` du `UnitFlagsComponent`. Le port en avait **deux**
représentations parallèles, dont aucune n'était complète : le gate no-move de `HeavyWeapon_ExtraDmg`
lisait un `set` Python que rien n'alimentait sur un état rechargé, et l'`ExecuteBehaviour`
d'HarvesterOfSouls lisait le flag natif que rien ne posait. Résultat : un **+25% fantôme** sur toute
attaque ranged rejouée depuis un état live où le caster avait bougé.

## 1. Artefacts natifs (décompile = vérité)

| Rôle | Symbole |
|---|---|
| Pose du flag | `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` |
| Appelant unique (combat) | `IdunBattle.Operations.MoveUnitOperation$$Execute` |
| Purge | `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` (via `IdunBattle.Operations.StartTurnOperation$$Execute`) |
| Lecteur — bonus dégât | `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` |
| Lecteur — nb de coups | `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` |
| Lecteur — fin de tour | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateTrigger` |

`SetMovedFlag` (mirror 1:1) :

```
added = UnitFlagsComponent.Add(unit, UnitFlag.Moved = 0)          # Add rend « était ABSENT »
if added and ( IsOwnerOfEffect|IsTargetOfEffect (unit, 0x40c | 0x40b | 0x4d9 | 0x4d6) ):
    UnitFlagsComponent.Add(unit, UnitFlag.Teleported = 0xc)
```

Les 4 effets = `TeleportStrike_Moving(1036)` / `TeleportStrike_TeleportingIn(1035)` /
`FearOfTheUnseen_Moving(1241)` / `FearOfTheUnseen_TeleportingIn(1238)` : un déplacement de
téléportation pose AUSSI `Teleported`, ce qui **ré-autorise** le bonus HeavyWeapon (la condition est
`!HasFlag(Moved) | HasFlag(Teleported)`).

Position du `SetMovedFlag` dans `MoveUnitOperation$$Execute` (lue au décompile) :
`AddMoveEvent(s)` -> `KillSteppableUnits` -> `UpdateCharging` -> **`SetMovedFlag`** (gaté par
l'option `MoveUnitOptions` @+0x8, nulle à tous les call-sites du port -> flag toujours posé) ->
`Add(ArrivedAtFinalTile = 1)` -> `RemoveReservation` -> `EvaluateAfterMoveTriggers`.

Gate complet de `HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` :

```
ForPercentIncrease(
    OwnerIsCaster & IsRangedAttack
    & ((F@0xa0 & !HasFlag(TurnFinished=3)) | !F@0xa0)
    & (!HasFlag(Moved=0) | HasFlag(Teleported=0xc)),
    ConditionalAmount(TriggeringAbilityIs(0x3ec=1004 MortisRound) ? base x2 : base))
base = ConfigConst 0xf = traitVariables.heavyWeaponExtraDmg = 25
```

## 2. Le bug (fork de port)

`#60` avait modélisé « a bougé » par un **set d'état** `State.moved_this_turn`, alimenté par
`MoveUnitOperation` et lu par `attacker_modifiers` / `RadSaturation`. En parallèle, le port du
`UnitFlagsComponent` (`#139`) matérialisait le **vrai** flag `Moved`, purgé par `remove_turn_flags`,
lu par `_harvester_hits` — mais **jamais posé** par le move. Deux conséquences :

1. **Aucun des deux stores n'est renseigné par `load_state`** (aucun RPC n'expose les UnitFlags).
   Sur un état rechargé depuis le live, le gate voyait donc toujours « n'a pas bougé » -> **+25%
   appliqué offline alors que le natif ne l'applique pas**.
2. Le reset différait du natif : `state.moved_this_turn.clear()` effaçait **globalement** au
   `StartTurnOperation`, alors que le natif ne purge **que les unités du joueur entrant**.

## 3. Décomposition par étage (mesures, pas d'ajustement de scalaire)

### 3.1 HarvesterOfSouls (eldarMauganRa, ability 1067, seeds 777 **et** 31337)

| | coup 1 | coup 2 | ratio |
|---|---|---|---|
| LIVE | 2155 | 2317 | — |
| OFFLINE (avant fix) | 2694 | 2896 | **1.2500 exact sur les DEUX coups ET les DEUX seeds** |

Un ratio **constant et exact** sur 4 mesures = terme **booléen** manquant, pas un arrondi — et la
valeur 1.25 est exactement `heavyWeaponExtraDmg = 25%`. Le caster avait été DÉPLACÉ par le drive du
test (`UnitFlagsComponent.MOVED` seedé pour `GetHits`, mais invisible du gate no-move).

### 3.2 SentinelDirectives (admecDestroyer « Sy-Gex », ability 1139, seed 777)

Décomposition étage par étage (probe `probe_101_moved_gate.py --case sentdir`) :

| étage | valeur |
|---|---|
| config `[minDmg, maxDmg]` | `[4254, 5318]`, `pierce = 1`, `hits = 1` |
| armure cible (necroOverlord) | `1909` |
| roll brut (rng seedé, **aligné** live/offline) | `4976` |
| perçage/armure `max(0, d - armor, d * pierce/100)` = `max(3067, 49.76)` | **3067** |
| offline AVANT fix : `%-list = [(1.25, None)]` -> `Round(3067 x 1.25)` | **3834** |
| offline APRÈS fix (flag `Moved` posé, `%-list` vide) | **3067** |
| LIVE | **3510** |

Le caster avait émis **4 déplacements** pour s'approcher -> le natif n'applique PAS HeavyWeapon.
L'écart restant `3510 - 3067 = 443` n'est **pas** un résidu de ce gate : c'est le passif
**`HeavyGravCannon` (1291)**, non porté —
`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$CreateEffectDamageBonusForAttack` =
`ForAddition(cond, ConfigVar(8 = extraDmg))` et `...$$CreatePiercingBonusForAttack` =
`ForPiercing(cond, ConfigVar(0x3f = extraPierceRatio))`, avec
`...$$DamageCondition` = `OwnerIsActor & IsRangedAttack & (HasTrait(target, 5 = Mechanical) |
HasTrait(target, 0x3f5 = 1013 MkXGravis) | HasTrait(target, 0x40f = 1039 TerminatorArmour))`.
`necroOverlord` (Anuphet) porte `Mechanical` -> condition VRAIE.

**Vérifié à l'unité** (effet capté live sur le caster : `ability_level = 50`,
`ability_variables_multiplier = 160%`) :

```
extraDmg[50] x 160%        = 443     ==  3510 - 3067   (le flat explique TOUT l'écart)
extraPierceRatio[50]       = 60      ->  pierce_eff = 1 + 60 = 61
pierced = (4976 + 443) x 0.61        = 3305.6  <  after_armor = 4976 + 443 - 1909 = 3510
```

Le `+pierce` est donc **inerte** ici : `GetDamageWithPiercing` prend `max(0, d - armor, d x pierce%)`
(le perçage est un **plancher**) et `d - armor` domine. L'écart résiduel est le **flat seul**, et son
signe est désormais correct (`live >= offline`) — c'est ce que le test asserte.

## 4. Fix

Un seul store, celui du natif.

- `engine/runner/components.py` : `set_moved_flag(state, unit_id)` (mirror 1:1 de
  `UnitExtensions$$SetMovedFlag`, Teleported conditionnel inclus) + `unit_has_moved(state, unit_id)`
  (mirror de `HasFlag(unit, UnitFlag.Moved)`) — **lecteur unique**.
- `engine/runner/operations/movement.py` : `MoveUnitOperation.execute` appelle `set_moved_flag` à la
  position native (après `KillSteppableUnits`).
- `engine/runner/damage_model.py`, `.../triggers/loki/rad_saturation.py`,
  `.../abilities/aeldari.py` : tous lisent `unit_has_moved`.
- `engine/runner/state.py` : `State.moved_this_turn` **supprimé** (slots + init).
- `engine/runner/operations/turnflow.py` : `clear()` global supprimé — le
  `remove_turn_flags(new_activation=True)` **par joueur entrant** (déjà porté, #139) est le seul
  reset, comme le natif.

Effet de bord positif : `ComputerActionOperation` (qui sauvegarde/restaure les UnitFlags autour
d'une action IA forcée, mirror `SetUnitTurnsFlags`) restaure désormais aussi le fait « a bougé » —
l'ancien set parallèle, lui, n'était pas restauré.

## 5. Validation

### 5.1 Tests ciblés (les 3 en échec sur `master`)

`test_harvester_live` (2 cas + 1 offline) + `test_sentinel_directives_live` (2 cas) :
**3 failed / 2 passed -> 5 passed**.

### 5.2 Généralisation craftée — `test_heavy_weapon_moved_gate_live.py` (nouveau)

Cast LIVE de SentinelDirectives (ranged, mono-coup, famille ATTACK) sur `orksNob` — traits
`['Hero','GetStuckIn','BeastSlayer','Unstoppable']`, donc **ni Mechanical, ni MkXGravis, ni
TerminatorArmour** -> `HeavyGravCannon` INERTE -> bit-exact atteignable.

| scénario | LIVE | offline hypothèse VRAIE | offline hypothèse FAUSSE |
|---|---|---|---|
| (A) caster n'a pas bougé (on déplace la **cible**) | `4167` | flag absent -> **`4167`** | flag posé -> `3334` |
| (B) caster a bougé (1 déplacement, reste à portée) | `3334` | flag posé -> **`3334`** | flag absent -> `4167` |

`4167 / 3334 = 1.24985` -> le bonus est bien `+25%` (trait var), pas un scalaire ajusté. La double
assertion (`== l'hypothèse vraie` **et** `!= l'hypothèse fausse`, dans les DEUX sens) est ce qui
distingue un gate correct d'un bonus purement supprimé : un port qui aurait « enlevé HeavyWeapon »
passerait (B) et échouerait (A).

### 5.3 Garde anti-régression

| lot | fichiers | résultat |
|---|---|---|
| migrés + mouvement | `test_rad_saturation_live`, `test_avalanche_of_muscle_live`, `test_runner_move_live` | 10 passed, 1 xfailed (xfail pré-existant, sans rapport) |
| consommateurs de `HeavyWeapon_ExtraDmg` | `test_mortis_round_live` (branche `x2` MortisRound), `test_plasma_cannon_live` (ability ranged `x1.25`), `test_overwatch_live` (tir d'overwatch) | 4 passed |
| pipeline dégât + turn-flow | `test_damage_roll_live`, `test_runner_attack_live`, `test_skitarii_turn_live` | 6 passed, 1 failed |

L'unique échec — `test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` (`BFS 3->3`) — est
**pré-existant et déjà documenté** dans `backlog.md` sur `origin/master` (« échoue au commit `9cf5e40`
[…] reproduit sur base propre (patch stashé) -> pré-existant, pas une régression »), avec exactement
le même symptôme (le Vanguard bouge sans se rapprocher, attaque ranged 3 hits pour 0 dégât).

### 5.4 Non couvert

- Le gate `Teleported` (`HasFlag(0xc)` qui **ré-autorise** le bonus après un move de téléportation) est
  **porté mais non validé live** : il exige un porteur de `TeleportStrike` / `FearOfTheUnseen` **et**
  du trait `HeavyWeapon` sur la même unité, configuration non montée ici. Mirror 1:1 du décompile.
- La branche `((F@0xa0 & !HasFlag(TurnFinished=3)) | !F@0xa0)` du gate HeavyWeapon n'est toujours pas
  portée (inchangé par ce cas — `F@0xa0` est un sélecteur du contexte d'effet, non décodé).
- Les vecteurs autres qu'`execute_ability_attack` (attaque normale, overwatch) ne sont couverts que
  par leurs tests existants (lot 2), pas par un scénario moved/not-moved craqué exprès.

## 6. Résidus documentés (hors périmètre)

- **`HeavyGravCannon` (1291) non porté** — `case-220 §6.17`. Mesuré ici : `+443` flat sur une cible
  `Mechanical`. C'est le seul confond restant de `test_sentinel_directives_live` (d'où
  `live >= offline` plutôt que le bit-exact).
- **`UnitFlag.ArrivedAtFinalTile = 1` non posé par le port** : `MoveUnitOperation$$Execute` l'ajoute
  juste après `SetMovedFlag` (gaté par l'option `MoveUnitOptions` @+0x0). Aucun consommateur porté
  n'en dépend aujourd'hui (le flag est posé par `FinishUnitTurnOperation` côté port) — à câbler avec
  le reste des `MoveUnitOptions` si un gate le réclame.
- **Aucun RPC n'expose les `UnitFlags`** : un état rechargé par `load_state` ne peut pas savoir
  qu'une unité a bougé. Les fixtures qui *pilotent* le déplacement re-posent le flag
  (`set_moved_flag`) ; un replay non piloté ne le peut pas. Point d'ancrage natif si on veut le
  capter un jour : `IdunBattle.Entities.Components.UnitFlagsComponent` (`OrderedSet<int>` @+0x10) de
  chaque unité, à exposer dans `combatSnapshot`.
