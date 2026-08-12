# case-919 — `IconOfObstinacy` : UNE entree de gameconfig, DEUX abilities natives, DEUX registres

Passif de kit d'`astarLysander` (`TriggeredAbilityType` `0x610` = 1552). Build `rnca9r7q6c`.

## 1. L'etat REEL au recon — l'audit sous-creditait, et il le disait

`audit_kit_coverage.py` le comptait `missing = 1`. Le recon a trouve la moitie DECISION deja
portee : `IconOfObstinacyNonOwnerPlaybook` (#433-r4-r3-r1) etait au registre depuis une autre
tranche, et `audit_passive_ability_coverage.py` classait bien le passif en `ZONE-GRISE [R]`
(« reference en code hors registre »). Restaient : la face DECISION **OWNER** et **toute** la face
COMBAT.

## 2. Le fait de structure — deux classes natives, deux chemins de port

`data/symbols/<build>/frida/classes.tsv` :

| classe native | parent | ce qu'elle fait |
|---|---|---|
| `AIconOfObstinacyAbility` | `BaseTriggeredAbility` | base abstraite ; porte le SELECTEUR partage |
| `IconOfObstinacy_AddArmourBuffAbility` | la base | trigger de COMBAT |
| `IconOfObstinacy_AddDamageBuffAbility` | la base | owner-effect pose a l'INIT |
| `IconOfObstinacy_ExtraArmourEffect` | `ADynamicStatModifierEffect` | stat-mod local, 1 round |
| `IconOfObstinacy_ExtraDamageEffect` | `BaseEffect` | AURA de degat |
| `IconOfObstinacyPlaybook` | `AdjacentUnitPreferenceTriggeredAbilityPlaybook<AddDamageBuff>` | face DECISION owner |
| `IconOfObstinacyNonOwnerPlaybook` | `AdjacentToOwnerNonOwnerPlaybook<AddArmourBuff>` | face DECISION non-owner |

**Les deux abilities n'empruntent PAS le meme registre**, et c'est le decompile qui tranche :

```
IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger
    On(0x28 = UnitFinishedTurn, ownerNeedsToBeAlive = 1)
  & DSLTriggers.Contains( GetAffectedUnits(), Actor@DSLSelectors+0x40 )
  & DSLTriggers.AmountIsZero( DSLFormulas.TimesAttackMadeThisTurn(Actor@0x40, rangeType = null) )
        -> `triggers.dispatch.ABILITY_TRIGGERS`

IconOfObstinacy_AddDamageBuffAbility$$CreateTrigger        (corps FONDU par l'ICF)
    DSLTriggers.OnOwnerSpecificAbilityInit(this.AbilityType@BaseTriggeredAbility+0x10)
  = On(0x31 = SpecificAbilityInit) & get_OwnerIsActor & TriggeringAbilityIs(<type>)
        -> `effects.factory.ABILITY_INIT_OWNER_EFFECTS`
```

### 2bis. Ce `CreateTrigger`-la n'a AUCUN symbole, et l'absence ne prouvait rien

`IconOfObstinacy_AddDamageBuffAbility$$CreateTrigger` n'apparait ni dans `ghidra/functions.tsv` ni
dans `frida/methods.tsv` : son corps est **DEDUPLIQUE par l'ICF** avec
`WayOfTheShortBlade_InitAbility$$CreateTrigger`, qui en est le seul proprietaire dans les tables.
Conclure « elle n'a pas de trigger » aurait fait poser l'aura de degat au mauvais endroit.

La lecture qui tranche est en DEUX temps, et aucun des deux ne suffit seul :

1. `global-metadata.dat` (`il2cpp_metadata.type_methods`) **DECLARE** ce que porte le type —
   `[CreateTrigger (slot 26), CreateBehaviour (slot 28), .ctor]` ;
2. le bloc `methodPointers` du PE, **ancre sur le `.ctor`** et indexe par l'ordre du metadata,
   donne l'**ADRESSE** de chaque entree — y compris des corps fondus.

Meme voie pour les deux corps fondus de `IconOfObstinacy_ExtraArmourEffect` :
`CreateActiveCondition` (partage avec `WisdomOfTheAncients_DamageReductionEffect`) = le trigger
CONSTANT `<DSLTriggers+0x70>`, et `CreateTargetSelector` (partage avec `WhisperingWebEffect`) =
`<DSLSelectors+0x30>` = **`Owner`** — donc l'effet d'armure n'est PAS une aura : il modifie la stat
de l'unite qui le porte.

## 3. Le selecteur partage, et le detail qui commande le port

```
AIconOfObstinacyAbility$$GetAffectedUnits(dsl)
    left = Owner@DSLSelectors+0x30
    return left + UnitsWithTrait( AdjacentFriends(left, unique = 1, selectionType = 3),
                                  0x40f = UnitTrait.TerminatorArmour, selectionType = 3 )
```

**`Owner` entre par `op_Addition`, donc SANS passer par le filtre de trait.** Les agregateurs
d'aura du port, eux, EXCLUENT le beneficiaire (`uid == att_id`) — fidelement a
`AdjacentFriends`/`SurroundingFriends`, qui retirent la source. L'effet de degat porte donc
**DEUX pattes disjointes** : `create_effect_damage_bonus_for_attack` (le porteur attaque) et
`create_aura_attack_damage_bonus_for_ally` (un ami Terminator adjacent attaque). Ni trou, ni
double-compte — c'est le mutant exerce par `test_les_deux_pattes_du_bonus_de_degat_sont_DISJOINTES`.

## 4. Les magnitudes — meme forme, deux porteurs differents

```
IconOfObstinacy_ExtraArmourEffect$$GetCurrentExtraArmour(target, effect)
    = GetVariableForLevel(0x1b = extraArmor)
    + PercentageOf( GetStat(TARGET, 0x8 = BlockDamage, 0x0 = Current),
                    GetVariableForLevel(0x3a = chance), roundingRule = 0 )

IconOfObstinacy_ExtraDamageEffect$$GetCurrentExtraDamage()
    = Sum( ConfigVar(0x8 = extraDmg),
           PercentageOf( StatAmount(OWNER@0x30, BlockDamage, Current), ConfigVar(chance), 0 ) )
```

Le `%` de l'armure se prend sur le **BENEFICIAIRE** ; celui du degat sur le **PORTEUR** — la
magnitude de degat est donc la MEME pour tous les beneficiaires. `chance` n'est pas dans
`variablesAffectedByRarityBonus` (`["extraDmg", "extraArmor"]`) : le multiplicateur de rarete ne
l'atteint pas.

### Le canal qui manquait : `BlockDamage du PORTEUR`

C'est la premiere aura de degat dont la magnitude lit une **stat du porteur** et non une seule
variable de config. Le ctx d'aura ne publiait que `owner_{id,pos,team}`. Trois sites, **tous
additifs** : `damage_model._apply_ally_attack_damage_auras` (map `owner_stat_block_damage` par
porteur), `damage_model.attacker_modifiers` (`att_ctx["owner_block_damage"]`, meme convention que
`tiles_moved_this_turn`) et `_shared.prediction_block_damage` (foyer unique cote prediction,
consomme par le ctx d'aura ET par les deux `att_ctx` self) — donc **pas de fork
prediction/combat**. Tri-etat partout : `None` = non mesure -> le terme `%` est OMIS et le dit.

## 5. La mesure LIVE (session 68, board `MC1_67`, seed 777, positions FORCEES)

`astarLysander` est HORS du pool par defaut -> `catalog_inject.write_augmented_seed_bc` (#270-d).

| unite | pos | dist(porteur) | `TerminatorArmour` | BlockDamage | FixedArmor natif | port |
|---|---|---|---|---|---|---|
| `astarLysander` | (3,3) | — porteur | oui | 2349 | **+1105** | **+1105** |
| `darkaTerminator` | (3,4) | **1** | **oui** | 2349 | **+1105** | **+1105** |
| `ultraTitus` | (2,3) | **1** | **non** | 0 | aucun | aucun |
| `thousTerminator` | (0,0) | **4** | oui | 2349 | aucun | aucun |

Les deux gates sont **attribues separement** : un voisin adjacent sans le trait, et un porteur du
trait hors du ring-1. `1105 = 400 (extraArmor lvl 50 x mult 180) + 705 (= round(2349 x 30 %))` —
decomposition par etage, aucun scalaire fitte.

**Troisieme gate, montage DEDIE** (le principal le laissait en regime degenere : personne n'y
attaque) : l'ami Terminator ATTAQUE (7822 degats infliges, controle de montage) puis clot son tour
-> **pas de buff**, des deux cotes ; le porteur, qui n'a pas attaque, garde le sien.

⚠ **Ce troisieme etage a d'abord rendu un ROUGE, et c'etait un FAUX ROUGE DE MONTAGE** : `--ability`
attend un ID (pas un nom) et `act ability` prend son lanceur par `--caster` (pas `--unit`) —
l'attaque n'avait jamais eu lieu. Le probe porte desormais un **controle de montage** explicite
(degat inflige > 0) et rend `NON MESURE` plutot qu'un rouge.

## 6. Les mutants — cinq, cinq rouges

| mutant | temoin qui mord |
|---|---|
| `StatPart.INITIAL` au lieu de `Current` | 3 x `test_la_magnitude_est_flat_plus_pourcentage_du_blockdamage` |
| gate TRAIT retire du selecteur (LIVE) | `test_le_port_rend_les_MEMES_porteurs_et_les_MEMES_montants` |
| `On(0x29)` au lieu de `On(0x28)` | `test_le_trigger_ecoute_UnitFinishedTurn_et_PAS_sa_variante_normale` |
| adjacence `> 1` (le porteur entre dans sa propre aura) | `test_les_deux_pattes_du_bonus_de_degat_sont_DISJOINTES` |
| — | aucun mutant vert |

⚠ **Un mutant NON discriminant, nomme** : filtrer aussi `Owner` par le trait ne changerait RIEN sur
ce porteur (`astarLysander` porte `TerminatorArmour`). C'est le decompile — `op_Addition` — qui
etablit l'inconditionnalite, pas la mesure.

## 7. Ce qui n'est PAS couvert

- **`CreateRefreshValueTrigger`** de l'effet d'armure (`On(0x38 = BlockDamageChanged) &
  get_OwnerIsActor`) : `On(0x38)` n'est emis par AUCUN site du port -> la magnitude est **figee a la
  pose**. Le natif la recalcule quand le `BlockDamage` de la cible bouge. Residu `#919-r1`.

  ⚠ **L'EMETTEUR NATIF EST IDENTIFIE (#981), et l'obstacle suivant AUSSI.** Le residu demandait
  « emettre `On(0x38)` au chokepoint qui ecrit la stat 8 » : ce chokepoint est
  `IdunBattle.Operations.TransformUnitOperation$$Execute`, et **tout** stat-mod y aboutit ::

      IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification
        (ou IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$RefreshValueInternal)
        -> IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat(targets, statType, mode 4, Direct(amount), Entity(effect))
           -> IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute      // batit List<StatModifier>
              -> IdunBattleLogic.Entities.DSLBehaviors$$Transform(unitSelector, statModifiers, ...)
                 -> <slot 102 = TransformUnit>
                    -> IdunBattle.Operations.TransformUnitOperation$$Execute
                       -> UnitExtensions.ApplyStatModifiers(unit, statModifiers)
                       -> pour chaque StatType touche, SI la table lui associe un event :
                          <slot 81 = EvaluateAbilities>(unit, unit, unit, <event>, <AbilityOrEffect vide>)
                       -> <slot 47 = RefreshEffects>

  La table est le `.cctor` (`StatType -> ModStatTransformConfig`, dernier champ =
  `Nullable<EventTriggerType>`) : **seuls deux StatTypes portent un event** — `0 (ATTACK) -> 0x37
  AttackChanged` et `8 (BLOCK_DAMAGE) -> 0x38 BlockDamageChanged`. La table d'INSTANCE du `.ctor`
  (`FillStatTransformConfig`) en ajoute un troisieme, `StatType 5 (HEALTH) -> 0x1e`, sur la branche
  `statPart not in (5, 6)`. Les DEUX slots sont `actor = caster = target = l'unite dont la stat a
  change`, ce qui satisfait exactement le `get_OwnerIsActor` du trigger de refresh.

  **CE QUI RESTE BLOQUANT, et ce n'est plus l'emetteur** : le driver de refresh du port
  (`runner/operations/refresh_effects.py::refresh_stat_modifier_effects`) **SKIPPE par construction**
  tout effet portant une cle de POSE (`stat_mod_source is not None`) — et `1576` est justement pose
  par le canal EAGER `AddEffectOperation._apply_stat_mods`. Le brancher sans lever cette garde ne
  ferait rien ; la lever naivement rouvre le double-compte que la garde documente et qui a deja ete
  MESURE (`ThrillSeekers` 1434 : +30 CritChance au lieu de +15). La tranche qui fermera `#919-r1`
  doit donc traiter les DEUX etages, et se confronter avec un poseur de `BlockDamage`
  (`TitanhammerSquad_ExtraBlockDamage`, qui buffe les MEMES unites Terminator).
- **`selectionType = 3` = `OnlyAliveAndTargetable`** : le port n'honore que le volet ALIVE. Un
  voisin en Deep Strike (`TeleportStrike_TeleportingIn`) reste selectionne offline alors que le
  natif l'ecarte. Meme limite que toute la famille des selecteurs d'effet.
- **L'adjacence** est `hexgeo.distance == 1`, sans le gate d'elevation `|delta| < 2` de
  `TileQuery$$IterateAdjacentTiles` (#271) — foyer partage avec `entities/effect_targets.py` et
  `effects/aura_selectors.py` ; permissif au bord d'une marche >= 2. A corriger au FOYER.
- **La face DECISION n'est confrontee par AUCUNE mesure de ce cas.** Les deux playbooks sont au
  registre et leurs cles sont LUES au litteral natif, mais aucun A/B d'utilite `Tile(7)` n'a ete
  monte : `test_433_r4_r3_r1_adjacent_to_owner_live.py` (38 passed, rejoue) garde la face
  NON-OWNER par sa forme, pas par un ecart d'utilite mesure sur ce porteur. Residu `#919-r2`.
- **Le volet DEGAT n'est pas confronte non plus par un ecart de degat mesure** : l'effet 1575 est
  bien pose LIVE au spawn (`decisionView.effects` du porteur), et la magnitude partage sa formule
  avec l'armure (verifiee au chiffre), mais aucun coup n'a ete compare natif/port. Residu `#919-r3`.
