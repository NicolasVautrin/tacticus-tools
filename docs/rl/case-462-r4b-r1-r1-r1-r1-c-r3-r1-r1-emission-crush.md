# #462-r4b-r1-r1-r1-r1-c-r3-r1-r1 / -r2 / -r3 — le crush d'un `Steppable` publie ses événements de mort

La tranche `-c-r3-r1` avait porté le **retrait** des effets du crushé et laissé l'**émission** dehors,
blast radius mesuré à l'appui (27 classes). Les trois résidus qu'elle a ouverts sont fermés **ensemble**,
parce qu'ils ne se confrontent que l'un par l'autre : `-r2` grave la raison, `-r1` publie l'événement qui
la fait lire, `-r3` fournit le **seul consommateur natif** de ce couple — et donc la confrontation live.

| résidu | verdict |
|---|---|
| `-r1` émission des quatre événements manquants | **PORTÉ** — le crush passe par le MÊME `IdunBattle.Operations.KillUnitOperation$$Execute` que la mort par dégât |
| `-r2` `RecordDeathReason(..., DamageReason.Steppable)` | **PORTÉ** — gate `options+0x44`, mirror lu |
| `-r3` `HaywireMineSteppableAbility` | **PORTÉ** — confronté **live**, natif vs port, bras positif ET négatif |

## 1. Ce que le natif fait, relu sur `rnca9r7q6c`

`IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` construit INLINE la struct que rend
`IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` — deux écritures non nulles, lues au
décompilé : `local_68 = 2` (`+0x00` = `DamageReason.Steppable`) et `local_28 = 0x10100000000` (les
octets `+0x40..+0x47`, donc `+0x44 = +0x45 = 1`, `+0x46 = 0`) — puis appelle le slot `KillUnit`.
**Le reste des 0x48 octets est à ZÉRO**, `+0x04..+0x20` compris : c'est le `TriggeringAbility`.

Les **quatre** tests sur `options` dans `Execute`, et ce qu'ils donnent sous `ForSteppable` :

| octet | ce qu'il gate | valeur | conséquence portée |
|---|---|---|---|
| `+0x45` | court-circuite `UnitExtensions$$IsSteppable(killed)` (flag `0xd`) | 1 | non porté (le port collapse les flags de mort dans `UnitComponent.alive`) |
| `+0x44` | `RecordDeathReason(killer, killed, uc, deathReason = options+0x00)` | 1 | **`-r2`** |
| `+0x46` | le flag `UnitFlag.Overkilled` sous `CanBeOverkilled` | 0 | `overkill=False` sur tout le vecteur |
| `+0x44` | une émission **analytics** (`Dictionary` + slot `0x19`) | 1 | hors moteur |

Aucun autre bloc ne lit `options` ⇒ **les cinq événements, les trois `RemoveEffects` et les deux gardes
sont joués à l'identique pour un crush**. Le seul endroit où `Steppable` change quelque chose est
`ActorStatisticsComponent$$RegisterDefeatedUnit`, sauté sous `IsSteppable(killed)` — non porté.

Le 5e argument de `RecordDeathReason` est bien `*(undefined4 *)options` (= `+0x00`), et la fonction écrit
un `Nullable<DamageSource>` à `UnitComponent+0x108` : `KillerId`, la raison, et un `AbilityOrEffect`
**vide** (aucun `DamageAppliedResult` n'existe pour un crush).

## 2. Ce que le port fait maintenant

`movement.py::_kill_steppable_kill_unit(state, dead_id, killer_id)` — mirror de l'appel
`processor.KillUnit(matchState, killer, entity, ForSteppable)` :

```
hp = 0 ; alive = False                      (posés par `_kill_steppable_units`, mirror de `Execute+0x505`)
RecordDeathReason(killer, killed, uc, DamageReason.Steppable)      <- gate `+0x44`
[canaux d'ability forcés à None]            <- memset 0x128 + `options+0x04` = 0
damage.py::_kill_unit_operation(state, killed, killer, overkill=False)
    On(1) -> garde revive -> On(2) -> RemoveEffects(0) -> RemoveEffects(1)
          -> On(0) -> On(0x36) -> garde HEAL -> RemoveEffects(2)
```

Le corps entier vit dans `_kill_unit_operation`, **foyer partagé avec la mort par dégât** : il n'existe
qu'une implémentation de `KillUnitOperation$$Execute` côté port. `_kill_steppable_remove_effects` (la
sous-séquence isolée de la tranche précédente) **disparaît** — elle en était un sous-ensemble.

**Les deux canaux d'ability sont VIDES sur tout le vecteur, et c'est lu deux fois** : `Execute` fait
`memset(&entities, 0, 0x128)` (donc `CurrentAbility` `+0x60` reste nul) puis recopie
`KillUnitOptions+0x04..+0x20` dans `TriggeringAbility` `+0x98` — or `ForSteppable` laisse ces octets à
zéro. Le port sauve/force/restaure les deux, même geste que `_verify_deaths` pour le drain (#301). Sans
ça, un crush déclenché DANS un behaviour de triggered-ability (feuille DSL `MoveUnit`,
`spiritual_leader`) ferait fuiter l'ambiant de l'appelant dans les gates `CurrentAbilityIs` /
`TriggeringAbilityIs` du vecteur mort.

`DamageReason` entre au port comme **enum** (`engine/entities/damage_reason.py`, mirror 1:1 de
`IdunBattle.Operations.DamageReason` lu dans `data/symbols/<build>/frida/enums.tsv`) — règle ENUM du
CLAUDE.md ; `reactivate_overwatch.DAMAGE_REASON_ABILITY` en dérive au lieu de porter l'ordinal nu.

## 3. `-r3` — la mine Haywire, et pourquoi elle est la PREUVE

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineSteppableAbility$$CreateTrigger`, nœud
par nœud (`sel+0x30 = Owner`, `sel+0x40 = Actor`) :

```
OnPreDeath(<null>, ignoreOverkill = 1) & OwnerIsTarget
  & HasDeathReason(Owner, 2 = DamageReason.Steppable, <Nullable VIDE>)
  & NOT HasTrait(Actor, 0x1b = Steppable) & IsAlive(Actor)
  & AreEnemies(Owner, Actor, 0 = ByCurrentTeam)
```

`...$$CreateBehaviour` :

```
atk1 = AttackWithAbilityDamage(Owner, Actor, RandomAmount(ConfigVar(0xc), ConfigVar(0xd)),
                               DamageProfileFromConfig(0x2e), ConfigConst(0x2f), AbilityOrEffect(0x606), 1)
atk2 = <idem avec 0x36 / 0x37 / 0x3f / 0x32>
If( HasTrait(Actor, 5 = Mechanical), op_Addition(atk1, atk2), atk1 )
```

Config gameconfig (zéro hardcode) : `minDmg`/`maxDmg`/`minDmg_2`/`maxDmg_2` (per-niveau, **toutes** dans
`variablesAffectedByRarityBonus`), `nrOfHits = 1`, `damageProfile = Blast`, `nrOfHits_2 = 2`,
`damageProfile_2 = Energy`, `attackRangeType = Melee`. Le 8e argument natif (`selectionType = 1` =
`UnitSelectionType.OnlyAlive`) est **redondant** avec le `IsAlive(Actor)` du trigger — résidu nommé.

**C'est l'ability qui n'existe QUE pour ce régime** : `HasDeathReason(Owner, Steppable)` ne peut être vrai
que si un crush a gravé la raison. Elle referme donc `-r1` et `-r2` en même temps qu'elle-même, et elle
**ouvre la voie « owner = le MOURANT »** que la tranche précédente avait mesurée fermée (0 kit `Steppable`
inscrit → **2** aujourd'hui, les deux mines).

## 4. La confrontation LIVE — natif vs port, sur un porteur RÉEL

Montage (`astarCyrus` injecté au catalogue, board `MC1_67`, `--no-ai`) : Cyrus sème une mine sur sa tuile
**précédente** à chaque déplacement (`HaywireMineAbility$$CreateTrigger` = `(On(4 = UnitAfterMove) &
OwnerIsActor & TriggeringAbilityIsNone) | (On(0x29) & OwnerIsActor & AmountIsZero(GetPersistentData(…)))`),
puis on fait marcher dessus l'unité voulue.

| bras | natif | port |
|---|---|---|
| ennemi **MECHANICAL** (`necroWarden`) | 3 coups, profils `[18 Blast, 16 Energy, 16 Energy]`, total **4641** | fourchette **[3576, 4873]** (`RandomAmount` forcé sur `CalculateMin` / `CalculateMax`) — **contient 4641** |
| ennemi non-mécanique (`orksNob`) | 1 coup, profil `18`, `Amount = 1403` | 1 attaque (branche `else` du `If`) |
| **ALLIÉ** (`ultraTitus`) | **0 événement de dégât**, PV inchangés | PV inchangés (gate `AreEnemies`) |

Le tirage ne peut pas coïncider (le PRNG natif porte l'état de toute la bataille), donc on confronte ce qui
est confrontable : la **structure** (nombre de coups, profils) et l'**encadrement**. L'encadrement
**discrimine** — cf. §5.

Ordre observé dans la cascade native, et il compte : `[Ability_Power «HaywireMineSteppable»]` puis
`DirectlyKillUnit` / `RemoveUnitFromTiles` / `RemoveUnit` ⇒ l'explosion **précède** le retrait du plateau,
exactement comme `On(1 = PreUnitDeath)` précède `processor.<slot 6>` au décompilé.

## 5. Le trou de HARNAIS qu'il a fallu boucher pour que la mesure ait un sens

Une unité **INVOQUÉE** n'a **aucune** `UnitConfiguration` native (`SpawnUnitOperation` la fabrique par
`SpawnUnitOptions$$WithStatsFromConfig`), donc le capteur `combatSnapshot.unitConfig` rend littéralement
`{"error": "config null"}` — **mesuré** sur `astarSmnHaywireMine`. `_load_unit_stats` laissait alors
`passive_ability_level = 0` et le multiplicateur à `100` : **toute** variable per-niveau d'un passif de
summon était lue à l'index 0. Mesure : `minDmg[0] = 50` au lieu de `minDmg[49] × 180 % = 4986`, facteur
**~55** — le mode de panne de #174 sur les Machines of War, transposé aux summons.

`snapshot._load_passive_abilities` seede désormais l'`AbilityState` depuis `unitAbilityStates` (canal qui
dumpe `level` `+0x20` et `mult` `+0x24` **par instance d'ability montée** — c'est d'ailleurs celui que
`AbilityConfiguration$$GetVariableForLevel` consomme réellement), **et seulement quand le trou existe** :
la garde n'écrit que si `passive_ability_level` est absent/0. Sur une unité configurée les deux canaux
coïncident (vérifié : `necroWarden` → `unitConfig.passiveAbilityLevel = 50` / `mult = 180`, et
l'`AbilityState` de hiérarchie 2 porte `level = 50` / `mult = 180`).

Sans ce correctif, la fourchette du port valait ~[40, 60] pour un natif à ~4500 : le bras d'encadrement
**rougissait**. C'est ce qui prouve qu'il discrimine.

## 6. Le blast radius, JOUÉ et non plus inventorié

L'inventaire dérivé des registres est ré-mesuré : **28** classes écoutent les cinq événements de mort,
dont **27** les quatre que le port n'émettait pas (chiffre du résidu **confirmé**, et il passe à 28 après
l'entrée de `HaywireMineSteppableAbility`).

Deux voies « owner = le MOVER » sont désormais **exercées**, chacune avec son TÉMOIN (même montage, aucun
crush) — `probe_… --step consommateurs` :

| classe | témoin (sans crush) | avec crush |
|---|---|---|
| `ActOfFaithAccumulateAbility` | 0 | **1** |
| `TheBetrayerAddEffectAbility` | 0 | **1** |

Verdict **analytique** (lecture du `matches` porté + du `CreateTrigger` natif) pour les autres, par
événement — c'est ce qui borne le risque réel :

* `On(1)` — `HazeCorruptionBonusHitAbility` et `EarlyWarningOverrideReactivateOverwatch` exigent
  `killer == owner` : **atteignables** par le MOVER. EWO ajoute `LegitDeathReasons`, qui n'accepte que
  `DamageReason.Ability` ⇒ **refuse un crush** (et c'est le natif qui refuse, pas le port).
  Les quatre revives (`Narthecium`, `TaintedNarthecium`, `ReanimationBeam`, `RitesOfMorkai`,
  `PhoenixGem`) visent le **mourant** : `CanBeRevived` passe sur un decoy (ni `PermaDeath` ni
  `Mechanical`), donc un apothicaire adjacent **peut** annuler un crush — comportement natif, garde revive
  incluse. Les deux `GhostEffectRevive` exigent `EffectSource == dying` : hors régime.
* `On(2)` — `Explodes` / `PutridExplosion` ont pour owner le mourant et portent un `NOT HasTrait(Steppable)`
  explicite ⇒ **refusent**. `BondRemoveOnBondedEntityDeath` fire si le crushé est le bondé d'un effet.
* `On(0)` — `BarbedOvipositorSummonAbility` porte `NOT IsObjectOrSteppable(target)` ⇒ **refuse**.
  `TerrifyingCrescendoOverkillAbility` exige `overkill` ⇒ **refuse** (`+0x46 = 0`).
  `DawnBladeHealAbility` (relique, owner = le tueur) **fire**. `EarlyWarningOverrideHitReductionPurge`
  n'a **aucun gate d'acteur** et purge son propre effet — il fire pour tout porteur, régime inchangé par
  le crush lui-même.
* `On(0x36)` — `CosmicHorrorOnKillAbility` porte `NOT HasTrait(Steppable)` ⇒ **refuse** (et c'est
  exactement ce que sa fiche annonçait). `AmbushSummonAbility` vise le mourant (aucun kit `Steppable` n'a
  `Ambush`). `EmpyricAmbushResetAbility` exige `IsNormalAttack(killTrigger)`, or le `killTrigger` d'un
  crush est **vide** ⇒ **refuse**.

⇒ le rayon RÉEL est **quatre** classes (`ActOfFaith`, `TheBetrayer`, `HazeCorruption`, `DawnBlade`) plus la
famille revive et les bonds ; les gates natifs éliminent le reste. **Deux** sont exercées, les autres sont
laissées en verdict analytique — résidu nommé.

## 7. Validation

* **`test_462_r4b_r1_r1_r1_r1_c_r3_r1_r1_crush_death_events_live.py` — 7 verts.** Trois bras LIVE
  (encadrement natif/port sur la mine, raison de mort, bras négatif ALLIÉ), trois bras STRUCTURE
  (les quatre événements, les deux consommateurs du mover avec témoin, la branche `Mechanical`), un bras
  HARNAIS (le seed d'`AbilityState` d'un summon).
* **`test_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable_live.py` — 6 verts, après INVERSION de ses deux bras
  de garde.** Ils annonçaient qu'ils rougiraient « le jour où l'émission serait portée / où un porteur
  naturel apparaîtrait » : les deux sont arrivés ensemble, et ils gardent maintenant l'état inverse.
* **Matrice de mutants — 6 sur 6 rouges** (bras ciblés, arbre restauré après chacune) :

| mutant | ce qu'il casse | rouges |
|---|---|---|
| M1 — `_kill_steppable_kill_unit` = les trois retraits seuls (état pré-tranche) | l'émission + la raison | **5** |
| M2 — `damage_reason` = `Ability` | le gate `+0x44` lu à l'envers | **2** |
| M3 — `HaywireMineSteppable` hors registre | `-r3` | **2** |
| M4 — l'arbre rend toujours `atk1` | le volet anti-`Mechanical` | **2** |
| M5 — `AreEnemies` supprimé | la mine explose sous un allié | **2** |
| M6 — seed d'`AbilityState` supprimé | le niveau d'un passif de summon | **2** |

* **Non-régression : 181 verts sur 26 fichiers**, en six passes de 4 en parallèle —
  `462_…_bond_removal_offline` (16), `389r2_kill_unit_remove_effects_offline` (10),
  `kill_unit_trigger_channels` (12), `act_of_faith_crit_resets_both_paths` (1), `dawn_blade_repair` (7),
  `decoy_foundation_live` (3), `cosmic_horror_live` (6), `462_…_c_r3_owner_gates_effet_live` (8),
  `spiritual_leader_live` (5), `death_queue_ordering_live` (22), `kill_unit_trigger_channels_live` (3),
  `revive_cancels_death_events_live` (3), `ambush_migration_live` (5),
  `decoys_misdirection_migration_live` (3), `hypersensory_moveandspawndecoy_live` (5),
  `tile_effect_dynamics_live` (5), `462_…_c_r1_tile_owner_gate_live` (7), `act_of_faith_live` (1),
  `thebetrayer_rage_duration_live` (1), `narthecium_revive_live` (9),
  `589r1r1r1r1_empyric_ambush_reset_live` (5), `357_relic_rail_live` (12),
  `363_ability_states_default_live` (10), `366r1_carrier_active_level_offline` (4),
  `steppable_decoy_tile_leaves_live` (14), `462_…_bond_removal_live` (4).
  Les familles réveillées par l'émission (`act_of_faith`, `thebetrayer`, `narthecium`,
  `empyric_ambush`) et les canaux d'`AbilityState` touchés par le correctif de harnais (`357`, `363`,
  `366r1`) sont dans le lot **parce que** cette tranche les atteint, pas par confort.

## 8. Non couvert, et nommé

* **Le tirage n'est pas confronté à l'unité près.** Le PRNG natif porte l'état de toute la bataille ; on
  confronte la structure et l'encadrement. Un port qui se tromperait **à l'intérieur** de la fourchette
  (mauvais profil sur un seul coup, mauvais nombre de coups compensé) ne serait pas vu par ce bras seul —
  c'est pourquoi les profils et le compte de coups sont assertés **séparément**.
* **Le crush d'un `Steppable` par `AddUnitOperation`** (le 4e site natif, qui passe par un
  `DamageAppliedResult` et le pipeline de mort complet) n'a **aucun** équivalent porté : le port ne
  modélise pas ce chemin. Écart préexistant, inchangé.
* **La garde HEAL n'est plus inerte** (`+0xf35`) : un consommateur des événements de mort peut désormais
  soigner le mourant entre le 2e et le 3e `RemoveEffects`. Elle est portée depuis la tranche précédente
  et son bras de test l'exerce — sur un montage **synthétique** assumé, faute de poseur naturel.
* **`UnitFlag` de mort** (`0xd` posé sous `+0x45`, `Remove(0xf)` / `Add(6)`) : toujours non portés, le
  port collapse l'état « mort » dans `UnitComponent.alive`. Écart préexistant.

## 9. Résidus ouverts

* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4`**~~ — **FERMÉ**, cf.
  `case-462-r4b-r1-r1-r1-r1-c-r3-r1-r4-post-unit-kill.md`. L'event vit désormais dans le foyer
  `damage.py::_kill_unit_operation`, à son rang natif, et `post_unit_kill_triggers_for_move` a
  disparu. ⚠ **Deux affirmations de cette fiche étaient FAUSSES**, et la seconde vaut aussi pour
  la docstring de `test_revive_cancels_death_events_live.py` : (a) l'event n'est pas seulement
  « après le `if/else` », il part **dans les DEUX branches** — la branche REVIVE le publie aussi,
  c'est le seul des cinq à survivre à l'annulation de la mort ; (b) le rang se lit à la **PILE**
  d'accolades, jamais à la **profondeur** (les quatre derniers events valent tous 9, ce qui avait
  fait écrire « TOUS à l'intérieur de ce bloc, sans `else` » — l'`else` existe, `+0xfcc`).
  L'effet de bord redouté — « un decoy allié tué par une AoE soignerait le Patermine » — est bien
  le comportement **NATIF** (le trigger `CosmicHorror_OnMoveAbility` ne porte AUCUNE gate de
  mouvement, relu nœud par nœud) mais n'a **aucun porteur atteignable** : le Patermine n'a pas
  d'AoE friendly-fire. La voie DÉGÂT a été confrontée **live** par un autre consommateur natif,
  `Lakrimae_SummonPoxwalker` (dont le `NOT IsObjectOrSteppable` exclut justement le crush).
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5`** — **la POSE de la mine n'est pas portée.**
  `HaywireMineAbility` (1531) exige `Spawn` + `GetPersistentData`/`AddPersistentData` +
  `TriggerAbilityDelayed`, et `HaywireMine_ResetAbility` le ré-armement. Conséquence : le port ne **crée**
  jamais de mine — il ne sait que la faire exploser quand la capture live en pose une. Toute simulation
  offline partant d'un état sans mine n'en verra jamais apparaître.
* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r1-r6`**~~ — **FERMÉ**, cf.
  `case-462-r4b-r1-r1-r1-r1-c-r3-r1-r6-prevent-revive.md` §1.
  ⚠ **SA PRÉMISSE ÉTAIT FAUSSE, ET ELLE VENAIT DU §6 CI-DESSUS.** La famille revive n'est pas « la
  seule capable d'annuler un crush » : elle en est **structurellement incapable**.
  `IdunBattle.Core.Services.BattleQuery$$CanBeRevived` a **CINQ** étages, et le §6 n'en énumère que
  quatre — il saute `!HasFlag(target, 0xd = UnitFlag.PreventRevive)`. Or
  `IdunBattle.Operations.KillUnitOperation$$Execute` pose ce flag sous
  `options.<+0x45> ? true : IsSteppable(killed)`, et
  `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` écrit
  `*(undefined2 *)(opts + 0x44) = 0x101` ⇒ `+0x45 = 1` : **tout crushé le reçoit sans condition**, et
  le rang le place **AVANT** `On(1 = PreUnitDeath)`, donc avant le vecteur qui porte les revives.
  ⇒ la phrase du §6 « un apothicaire adjacent **peut** annuler un crush » est à lire comme **FAUSSE**.
  Le port, lui, avait le bug **INVERSE** : ne lisant pas le flag, il ressuscitait un crushé que le
  natif refuse (dégradation PERMISSIVE). **CORRIGÉ** — mesuré `can_be_revived(crushé)` `True` →
  `False`, témoin mort ordinaire `True` → `True`.
  Ce qui reste ouvert de ce résidu part sous **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2`** :
  `HazeCorruptionBonusHitAbility` et `DawnBladeHealAbility`, toujours en verdict analytique.
