# #1011 — `NornCrown` (relique de `tyranNeurothrope`) : l'aura mesurée, et le mot « Other » expliqué

**PORTÉ + CONFRONTÉ LIVE.** Build de mesure : `rnca9r7q6c`.

i2 : « The maximum level of Neuroparasite is increased by 1. **Other** friendly Psykers within
Synapse range and friendly Summons within Synapse range deal +1308 Damage to enemies that are
affected by Neuroparasite. »

## 1. Identité — trois enums, et un ordinal partagé

```
TriggeredAbilityType  0x5d7 = 1495 = NornCrown                  <- l'ABILITY (la relique)
EffectType            0x5d4 = 1492 = NornCrown                  <- l'EFFET posé sur le porteur
EffectType            0x5d7 = 1495 = HunterOfSouls_ExtraDamage  <- rien à voir
```

L'appariement ability → effet est **LU** : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
NornCrownAbility$$GetEffectType` a pour corps ENTIER `return 0x5d4`, et `frida/classes.tsv` donne
son parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`. La classe n'override QUE
`GetEffectType` — tout le reste vient de la base (patron `Vitarus` #1005 / `ToughToKill` #950).

## 2. Les deux faces, et une seule était à porter

* **max de Neuroparasite +1** — DÉJÀ PORTÉE depuis #462-r4b-r1-r1-r1
  (`runner/operations/triggers/loki/neuroparasite.py::neuroparasite_maximum_level`, terme
  `If(ActorHasTriggeredAbility(BondedEntity, 0x5d7), ConfigConst(0x5d7, ·, 0x73 = effectLevel),
  Direct(0))`). Rien à faire.
* **l'AURA de dégât** — c'est le port de cette tranche.

## 3. Le corps natif, verbatim

`AOwnerEffectTriggeredAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit(this.AbilityType)` ;
`…$$CreateBehaviour` = `If(CreateCondition(…), AddEffect(GetEffectType(), AbilityState(Owner),
source = Owner, targets = Owner, options = <Nullable ZÉRO-initialisé>))` → owner-effect
**PERMANENT**.

`IdunBattle.Entities.Effects.Loki.NornCrownEffect$$CreateTargetSelector` :

```
Filter( AllUnits@DSLSelectors+0x20,
          AreFriends( Owner@+0x30, It@+0x68, comparisonType = 0 ByCurrentTeam, anyEntity = false )
        & IsInTeamSynapseRange( It@+0x68, Owner@+0x30 )
        & ( HasTrait(It, 0x3ea = 1002 Psyker) | HasTrait(It, 0x2 = Summon) ) )
```

`…$$CreateEffectDamageBonusForAttack` :

```
EffectBonus.ForAddition(
    get_OwnerIsCaster
      & HasEffect( Target@+0x60, 0x4c2 = 1218 Neuroparasite, onlyActive = false, 6 = Both ),
    ConfigVar( 0x8 = extraDmg, GetAbilityState(effect) ) )
```

Slots `DSLSelectors` (`$$InitializeShared`, carte de `case-489` §4) : `+0x20 AllUnits · +0x30 Owner
· +0x60 Target · +0x68 ActiveTarget`. Signatures et enums lus dans
`data/symbols/<build>/frida/{methods,enums}.tsv`.

## 4. Le mot « Other » n'est PAS dans le sélecteur — il est dans `GetSurroundingUnits`

`AreFriends` descend jusqu'à `IdunBattle.Core.Services.BattleQuery$$AreFriends`, dont le corps
ENTIER est `return UnitExtensions$$IsFriend(unit1, unit2, selectionType, state)` — et `IsFriend`
**n'écarte pas l'égalité**. Le porteur est donc dans son propre `Filter`, et le décompilé ne porte
AUCUNE exclusion du porteur. L'i2 dit pourtant « Other ».

La contradiction se résout un étage plus bas :

```
DSLTriggers$$IsInTeamSynapseRange(target, team)
  -> IsInAuraRangeTrigger(state, query, effectType = 0x41c = 1052 Synapse_Effect, target, team)
  -> IBattleQuery slot 148 = IsInTeamAuraRange -> BattleQuery$$GetInRangeAuraAmount(..., returnFirst: true) > 0
       auraDef = EffectsDatabase[0x41c]                       # IdunBattle.Entities.Effects.Loki.SynapseEffect
       trait   = auraDef.GetTrait()                           # corps ENTIER : return 0x7e8 = 2024 Synapse
       foreach unit in GetSurroundingUnits(target, <range>, friendsOf: null, includeCenter: FALSE):
           HasTrait(unit, trait) && GetCurrentTeamId(unit) == team && <range> >= GetDistance(unit, target)
```

**`includeCenter = FALSE`** (octet bas du 5ᵉ argument mis à zéro au site d'appel) ⇒ **une unité
`Synapse` n'est jamais dans sa PROPRE bulle**. `tyranNeurothrope` étant à la fois `Psyker` et
`Synapse`, il ne s'auto-buffe que si un AUTRE émetteur `Synapse` de son équipe est à ≤ 2 hexes.
C'est exactement le « Other » de l'i2 — obtenu par une mécanique, pas par une exclusion.

Le rayon **2** vient de `SynapseEffect$$GetNextTurnRange` = `Direct(2)`, corroboré par deux sources
indépendantes (`services/movement_query.py::synapse_tiles_for`, i2 du trait).

## 5. Ce qui a été MESURÉ live (`probe_1011_norn_crown.py`, A/B de relique)

Montage : `MC1_67`, seed 777, tuiles EXPLICITES — porteur (3,2), `astraPrimarisPsy` (3,3), cible
`orksNob` (3,4), `orksRuntherd` (0,5) ; parasite posé par l'attaque normale **Psychique** du
Neurothrope ; `--hp-target 200000`. Deux runners identiques **à la relique près**.

| régime | allié AVANT parasite | allié APRÈS | porteur APRÈS |
|---|---|---|---|
| Neurothrope SEUL émetteur `Synapse` | **A−B = 0** | **A−B = +880** | **A−B = 0** |
| + `tyranParasite` à 1 hex | A−B = 0 | A−B = +880 | **A−B = +1170** |

`extraDmg[1] = 880` (le palier CLAMPÉ du niveau 50 vaut 1308). Les deux dernières colonnes
ÉTABLISSENT `includeCenter: false`.

⚠ **`--hp-target` n'est pas un confort** : sans lui `aiPredict` sature ses deux bornes aux PV
restants de la cible (mesuré 3536/3536 des DEUX côtés) et l'écart A−B tombe à 0 pour une raison
étrangère à la relique — un accord en régime DÉGÉNÉRÉ, qui ne prouve rien.

## 6. Le port

`engine/entities/effects/loki/norn_crown.py::NornCrownEffect`, **deux pattes disjointes** (le
porteur est dans son propre sélecteur, cf. §4) :
`create_aura_attack_damage_bonus_for_ally` et `create_effect_damage_bonus_for_attack`. Les
agrégateurs excluent déjà `uid == att_id` : ni trou, ni double-compte.

Registres : `EFFECT_CLASSES["NornCrown"]` et `ABILITY_INIT_OWNER_EFFECTS["NornCrown"]`.

**Trois canaux de contexte**, posés au foyer COMBAT (`damage_model`, un seul site par patte) :

| clé | mirror natif | tri-état |
|---|---|---|
| `tgt_effect_names` | `HasEffect(Target, …, onlyActive: false)` → store BRUT `by_unit` | `None` = non mesuré → gate muet |
| `team_synapse_positions` | positions des `Synapse` VIVANTS par équipe (substrat d'ENTITÉ #264) | idem |
| `tertiary_ability_state_of` | `GetAbilityState(effect)` → `triggered_ability_state` (#357) | absent → repli documenté sur l'instance |

⚠ **Le niveau est le TERTIAIRE, pas le passif.** Contre-épreuve jouée, garde vue ROUGE :
`AssertionError: aura portee = 1308, natif mesure = 880` — le piège +49 % de #357, à l'identique.

## 7. Ce qui n'est PAS couvert

* **La face PRÉDICTION n'est pas câblée** — `playbook/prediction/_shared.py::
  _apply_ally_attack_dmg_bonus` ne reçoit pas les trois canaux. Le `Scene` ne porte AUCUN canal
  tertiaire (aucun `scene.*` ne lit `unitAbilityStates`), donc y verser l'aura lirait le niveau
  PASSIF — exactement la faute que le §6 vient d'éliminer côté combat. Résidu **#1011-r2**.
* **Le PLACEMENT de l'additif ATTAQUANT est NON TRANCHÉ, et il est SYSTÉMIQUE.** Mesuré : le
  porteur (`pct_list = [1.33]`, `RangedSpecialist`) reçoit **+1170 = 880 × 1,33** ; l'allié
  (`pct_list = []`) reçoit **+880**. Le port verse dans `mods.additive`, appliqué APRÈS la %-liste
  (`apply_all_modifiers`, ordre RE'd de `CalculateBaseDamageWithAllModifiers`) — donc **+880 des
  deux côtés**. Le régime ALLIÉ (le seul confronté ici) ne discrimine pas : `M = 1`. La question
  porte sur TOUTE la famille `CreateEffectDamageBonusForAttack` (`BeaconOfRage_Friendly`,
  `DestroyTheWitch_ExtraDamage`, `LordOfTheHost`…), pas sur `NornCrown` — la trancher dans cette
  tranche aurait déplacé un foyer partagé sur une seule mesure. Résidu **#1011-r2**.
* **`Summon` comme bénéficiaire** n'est pas confronté : le gate est porté (`HasTrait(It, 0x2)`) et
  couvert par la contre-épreuve de RETRAIT de trait, mais aucun summon `Psyker`/`Summon` allié n'a
  été amené dans la bulle.
* **Les playbooks** `NornCrownPlaybook` / `NornCrownNonOwnerPlaybook` (face DÉCISION) ne sont pas
  portés.
