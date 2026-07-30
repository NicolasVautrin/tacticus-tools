# case-266 — `UnitFlag.Moved` sur la face PRÉDICTION : deux termes, pas un

**Verdict : quirk porté et validé live.** La prédiction native voit `HasFlag(Self, UnitFlag.Moved)`
sous **deux** termes — le flag RÉEL de l'ECS *et* la tuile SIMULÉE. Le port n'en avait qu'un (la
tuile). Conséquence mesurée : sur un caster qui a **réellement bougé** puis prédit depuis sa tuile
courante, l'offline accordait un **+25 % ranged fantôme** (`HeavyWeapon_ExtraDmg`, effet 1008) que le
natif refuse — exactement la même signature que le bug COMBAT résolu par `case-101` / `case-o10`,
mais sur l'autre face.

## 1. Artefacts natifs (décompilé = vérité)

| Rôle | Symbole |
|---|---|
| Builder des modifiers de prédiction | `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` |
| Évaluation du gate | `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` → `IdunBattle.Entities.Components.UnitFlagsComponent$$Has` |
| Gate lui-même | `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` |
| **Simulation de la tuile candidate** | `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` |
| Variante SANS pose de flag | `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedOnSameTile` |
| Aiguillage entre les deux | `IdunBattle.Operations.SimulateEffectsOperation.u003Cu003Ec__DisplayClass5_0u003C__Il2CppFullySharedGenericTypeu003E$$u003CExecuteu003Eb__0` |
| Pose du flag | `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` |

### 1.1 Le builder de prédiction ne substitue QUE la position

`CalculateAttackerModifiersForPrediction(retbuf, state, entities, abilityEntities, effets)` reçoit une
struct `AbilityEntities` (0xa8 octets, passée par valeur) et délègue l'évaluation des conditions
d'effet aux membres **0x16 / 0x17 / 0x18** de chaque effet, à qui elle transmet cette même struct.
Elle ne contient **aucun** `UnitFlagsComponent`, `HasFlag`, `Add` ni `Remove` — lecture exhaustive du
corps (1557 lignes de pseudo-C) : zéro occurrence de la sous-chaîne `Flag`.

L'asymétrie décisive est dans le bloc « high ground » : la tuile de l'ATTAQUANT est prise **telle
quelle** du champ `AbilityEntities+0x40`, alors que celle de la CIBLE est re-dérivée par
`IdunBattle.Entities.EntityExtensions$$GetMainTile` sur le monde ECS courant. ⇒ **seule la POSITION
est hypothétique** ; tout le reste (flags, effets) est lu sur l'état réel.

### 1.2 …mais la prédiction d'une tuile candidate tourne DANS une simulation qui pose le flag

`DoActionInSimulatedTile(this, unit, simulatedPosition, action, …)`, dans l'ordre lu au décompilé :

```
wasDead      = UnitExtensions.IsDead(unit)
originTiles  = EntityExtensions.GetTiles(unit)
flags        = GetComponent<UnitFlagsComponent>(unit)
movedAdded   = UnitExtensions.SetMovedFlag(unit)          # <-- LE MEME que MoveUnitOperation
arrivedAdded = UnitFlagsComponent.Add(unit, 1)            # ArrivedAtFinalTile
… sauvegarde de ChargedUnitIds(+0x190) et de deux champs (+0xec/+0xf0) …
… déplacement simulé, SimulateMoveUnitTriggers, RefreshSimulatedEffects …
action()                                                  # <-- LA PRÉDICTION
… ResetAddedEffects, restauration de la position …
if movedAdded:   UnitFlagsComponent.Remove(unit, 0) ; Remove(unit, 0xc)   # Moved / Teleported
if arrivedAdded: UnitFlagsComponent.Remove(unit, 1)
… restauration de ChargedUnitIds et des deux champs …
```

L'aiguillage est **verbatim** (`<Execute>b__0`) :

```
if (UnitPosition.op_Equality(EntityExtensions.GetUnitPosition(state, unit), simulatedPosition))
    DoActionInSimulatedOnSameTile(...)   // AUCUN SetMovedFlag
else
    DoActionInSimulatedTile(...)         // SetMovedFlag
```

⇒ **`has_moved` vu par la prédiction = `HasFlag(u, Moved)` OU `tuile candidate ≠ tuile courante`.**
`SetMovedFlag` n'a que **deux** appelants dans tout le binaire : `MoveUnitOperation$$Execute` et
cette simulation.

## 2. Le bug de port

`engine/playbook/prediction/*` calculait `_hm = (attack_pos != scene.pos(uid))` — le second terme
seul. Sur une prédiction depuis la tuile COURANTE d'un caster ayant déjà bougé, `_hm` valait `False`
et le +25 % était accordé. La face COMBAT, elle, lisait déjà le flag (`case-101`, puis `#235` qui l'a
câblé au canal live `combatSnapshot.units[].unitFlags` → `snapshot._load_unit_flags`) : les deux faces
divergeaient donc sur le MÊME fait.

## 3. Décomposition par étage (mesures)

Probe : `scripts/python/probe_266_moved_prediction.py`. Caster `admecDestroyer` (trait `HeavyWeapon`,
SEUL trait à modifier son dégât en %), cible `orksNob` (ni `Mechanical`, ni `MkXGravis`, ni
`TerminatorArmour` ⇒ `HeavyGravCannonEffect` INERTE), board `MC1_67`, seed 26601.

### 3.1 Balayage de tuiles — ce n'est ni l'élévation ni la distance

Caster non déplacé (tour cyclé ⇒ `RemoveTurnFlags` a purgé `Moved`, `unitFlags = []` vérifié),
utilité native `pairUtility` de l'attaque normale sur la même cible :

| depuis | utilité |
|---|---|
| **tuile COURANTE** (2,5) | **4.610902587883174** |
| 15 tuiles SIMULÉES en portée, élévations 1/2/3, distances 1/2/3 | **3.772908174432814** (à l'identique) |
| tuile simulée (2,3), élévation 4 > élévation 3 de la cible | 5.4475636733695865 (surplomb, axe séparé) |
| tuiles simulées à distance 4 (hors portée 3) | 0.42359717655926943 |

Une seule valeur pour toutes les tuiles simulées en portée, quelles que soient l'élévation et la
distance : le discriminant est bien **« tuile courante vs tuile simulée »**, pas la géométrie.

### 3.2 Runners JUMEAUX — le flag seul change

Même seed / board / roster / géométrie, caster sur **la même tuile** (2,5), même nombre de tours
écoulés ; seul l'ordre du dernier cycle de tour diffère (donc le flag) :

| | `unitFlags` | utilité NATIVE | port AVANT | port APRÈS |
|---|---|---|---|---|
| A — flag ABSENT | `[]` | **4.6109** | (10052, 15072) | (10052, 15072) |
| B — flag POSÉ | `[0, 1]` | **3.7729** | **(10052, 15072)** | **(8040, 12056)** |
| ratio A/B | | 1.2221 | **1.0** | **1.25025 / 1.25017** |

Deux enseignements :

1. **`3.772908174432814` est BIT-IDENTIQUE** à l'utilité de toutes les tuiles simulées du balayage
   §3.1. Le flag réel et la tuile simulée produisent donc **le même état natif** — c'est la
   confirmation live du mécanisme lu au décompilé.
2. Le port AVANT rendait la MÊME valeur dans les deux régimes (ratio 1.0) : il était **aveugle** au
   flag. Le rouge a été provoqué exprès (`git stash` du câblage, probe re-joué) avant d'être fermé.

Le ratio natif 1.2221 < 1.25 parce que `CalculateUtilityFromPredictions` n'est pas linéaire en dégât ;
la magnitude exacte se lit côté port (×1.25 = `traitVariables.heavyWeaponExtraDmg`) et, sur la face
COMBAT, bit-exact dans `test_heavy_weapon_moved_gate_live`.

## 4. Fix

- `engine/playbook/scene.py` : `Scene.moved_by_id` / `teleported_by_id` + accesseurs `has_moved` /
  `has_teleported` (TRI-ÉTAT : `None` = non mesuré). Remplis par `from_state` depuis l'ECS
  (`unit_has_moved` / `unit_has_teleported`) et côté live par `_unit_flag_from_snapshot` — la
  généralisation du lecteur `_prevent_overkill_from_snapshot` (O5), appelée au `build_predictor` ET
  re-capturée **par pas** dans `refresh_shields` (ce sont les flags les plus volatils du composant).
- `engine/playbook/prediction/_shared.py` : `prediction_has_moved(scene, uid, attack_pos)` (foyer
  UNIQUE : `tuile ≠ courante` OU flag) et `prediction_has_teleported(...)` (mirror de la branche
  `| HasFlag(Teleported)`, y compris l'ajout que `SetMovedFlag` ferait dans la simulation).
- Quatre call-sites basculés sur le foyer : `prediction/normal_attack.py`, `prediction/abilities.py`,
  `playbook/fury_of_the_ancients.py`, `playbook/psyker.py` — plus `att_ctx["has_teleported"]`, que
  seule la face COMBAT threadait. `probe_32d_fury.py` (mirror du chemin fury) suit.

## 5. Validation

### 5.1 Garde dédiée — `test_heavy_weapon_moved_prediction_live.py` (nouveau)

Runners jumeaux (§3.2), trois assertions dont deux adversariales :

- **(a) le natif discrimine** : `utilité(A) > utilité(B)` — sans ça le reste serait de
  l'auto-confirmation ;
- **(b) magnitude** : `port(A)/port(B) == 1 + traitVariables.heavyWeaponExtraDmg/100`, la variable
  étant **lue dans la config**, jamais codée en dur ;
- **(c) contrefactuel DANS LES DEUX SENS** : forcer `Scene.moved_by_id[caster]` à l'hypothèse inverse
  fait basculer la valeur du port sur celle de l'autre runner (mesuré :
  A forcé `moved=True` → `(8040, 12056)` = B ; B forcé `moved=False` → `(10052, 15072)` = A). Un port
  qui aurait simplement *supprimé* HeavyWeapon rendrait deux fois la même valeur et échouerait (b) et
  (c).

Le test **tombe** sans le câblage (vérifié par `git stash`) : `'Scene' object has no attribute
'has_moved'`.

### 5.2 Les quatre évitements retirés

Les quatre montages s'interdisaient de déplacer le caster « parce qu'aucun RPC n'expose les UnitFlags
au port ». La prémisse est morte des deux côtés. État final :

| montage | face | déplacement | résultat |
|---|---|---|---|
| `test_ability_hits_channel_live::test_frenzied_firing_aoe_combat_matches_native` | COMBAT | caster déplacé, en dernier | **passed**, per-coup BIT-EXACT |
| `probe_61d_frenzy_aoe_combat.py` | COMBAT | idem | verdict PER-COUP **BIT-EXACT** (k=0) |
| `test_ability_hits_channel_live::test_frenzied_firing_aoe_batch_matches_native` | PRÉDICTION | caster déplacé au montage | échoue sur la **régression d'oracle** §6, au même point que sur `master` |
| `probe_61c_frenzy_aoe.py` | PRÉDICTION | idem | idem |

⚠ **Contrainte de turn-flow découverte, à ne pas re-découvrir** : sur un roster **1 vs N**, une unité
qui a bougé n'a plus d'action pendante — tout déplacement ADVERSE qui suit fait basculer
`currentPlayer` (mesuré : `currentPlayer=4` alors que `owner=3`, `hasAction=False`) et le cast devient
illégal. Le pas du caster doit donc être joué **en dernier**, après tout le pilotage adverse, et
contraint à rester à distance 2..3 de la cible et hors de l'anneau (sans quoi il changerait le `Count`
de tuiles libres que lit `FrenziedFiringAbility$$GetHitsForOriginalTarget`). Une unité ne dispose que
d'**un** déplacement par tour : la destination ne peut pas être re-choisie après coup.

`predict_sweep.py` portait un cinquième évitement de la même famille (cycle de tour pour remettre
`HasMoved` à `False`) : le cycle reste utile pour retrouver des activations disponibles, mais sa
justification `Moved` est caduque et a été réécrite.

### 5.3 Non-régression (tests ciblés)

| lot | résultat |
|---|---|
| `test_sentinel_directives_live`, `test_psyker_splash_live`, `test_ischarging_extra_damage_live` | 10 passed |
| `test_mortis_round_live`, `test_plasma_cannon_live`, `test_charge_tile_utility_live` | 9 passed |
| `test_heavy_weapon_moved_gate_live` (face COMBAT du même gate) | 2 passed |
| agreement `engine_validate --steps 8` (seed 31337, `MC1_67`) | positionnement 8/8 exact, abilities 3/3 match |

Le chemin de DÉCISION en self-play est inchangé : l'IA choisit (tuile, cible) au DÉBUT de
l'activation, quand le flag est absent — le nouveau terme n'y mord pas. Il mord sur les états
RECHARGÉS et sur toute prédiction faite après un déplacement, c'est-à-dire exactement le régime
replay-diff.

## 6. Résidus documentés

- **RÉGRESSION D'OUTILLAGE, pré-existante, hors de portée sans réinjection** : sur le build
  `rnca9r7q6c`, le décodage des prédictions natives est **périmé**. `aiPlaybookPredict` rend des
  `ProbableDamageEvent` avec `targetId = null`, `healthDmg{Min,Max} = 0` et un `appliedHits` qui vaut
  un nombre de PV ; `aiPredict` (`GetAllPredictions`) rend de même `healthDmg{Min,Max} = 0` avec un
  `hpBefore` CORRECT. Seuls `targetId`(+0x00) et `hpBefore`(+0x08) se lisent juste ⇒ la structure
  `AttackHitPrediction` / `DamagePredictionResult` a bougé au-delà de +0x08. Point d'ancrage à
  re-RE : `readDamageEvent` de `frida/hooks/features/ai-step/playbook-predict.ts` (offsets
  `+0x68/+0x6c` healthDmg, `+0xc4` appliedHits, `+0xc8` probability) et le bloc de lecture de
  `aiPredict` dans `rpc-predict.ts` (`+0x60/+0x64`), à confronter à
  `IdunBattle.AI.ProbableDamageEvent$$.ctor`. Rougit déjà sur `master` :
  `test_ability_hits_channel_live::test_frenzied_firing_aoe_batch_matches_native` et
  `test_predict_live::test_normal_attack_prediction_matches_oracle` (11/11 échantillons avec
  `oracle=(0, 0)` — vérifié identique patch stashé). C'est ce qui a imposé `pairUtility` comme oracle
  de substitution ici.
- **Branche `| HasFlag(Teleported)` en prédiction : portée, NON validée live.** Mirror du décompilé
  (`SetMovedFlag` ajoute `Teleported` quand l'`Add(Moved)` a rendu « était absent » et que l'unité
  porte l'un des effets `TeleportStrike_*` / `FearOfTheUnseen_*`). Aucun porteur connu ne cumule
  `HeavyWeapon` et `TeleportStrike` — même limite que la face COMBAT (`case-101` §5.4).
- **Branche `((F@0xa0 & !HasFlag(TurnFinished=3)) | !F@0xa0)`** du gate HeavyWeapon : toujours pas
  portée (inchangé — `F@0xa0` est un sélecteur du contexte d'effet, non décodé).
- `DoActionInSimulatedTile` pose AUSSI `UnitFlag.ArrivedAtFinalTile` (=1) et sauvegarde/restaure
  `ChargedUnitIds@+0x190` autour de l'action. Le premier n'a aucun consommateur de dégât ; le second
  est déjà porté par `_prediction_is_charging` (case-r32), qui reconstruit la liste du pas candidat.
