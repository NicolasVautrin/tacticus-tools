"""Passif `KustomForceFieldReworked` (TriggeredAbilityType 0x60b = 1547, `orksBigMek`) -- face COMBAT.

Le SEUL artefact natif de l'ability est un `CreateBehaviour` DSL ; elle ne declare AUCUN
`CreateTrigger` propre (son parent est `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et le
trigger herite est le meme corps deduplique que LionHelm / AnvilShield / PropheticSentinel :
`On(0x21 = AbilityInit) & get_OwnerIsActor`). Canal de port = `ABILITY_INIT_OWNER_EFFECTS` (pose)
+ `EFFECT_CLASSES` (comportement), JAMAIS `ABILITY_TRIGGERS` ni `ABILITY_CLASSES`.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.KustomForceFieldReworkedAbility$$CreateBehaviour`
(MIRROR du decompile) :

    AddDynamicStatModifierEffectToOwner( EffectType.KustomForceFieldReworked      = 0x61e = 1566,
                                        StatType.FixedArmor = 0x10 = 16, turns = null, isHidden = false )
  & AddDynamicStatModifierEffectToOwner( EffectType.KustomForceFieldReworked_Orks = 0x61f = 1567,
                                        StatType.FixedArmor = 0x10 = 16, turns = null, isHidden = false )

⚠ Le joint est `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`, pas `op_Addition` (LionHelm) : DEUX
classes DSL distinctes, meme structure `{+0x50 left, +0x58 right}`. Sans branche conditionnelle
entre les deux, l'observable est le meme -- les DEUX effets sont poses. C'est ecrit ici pour que le
prochain lecteur n'aille pas chercher un `op_Addition` qui n'y est pas.

`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner` pose
`AddStatModifierEffectBehaviour(isDynamic = 1, source = Owner@DSLSelectors+0x30,
targets = Owner@+0x30, ...)` : les DEUX effets-entites vivent sur le PORTEUR ; c'est leur
`CreateTargetSelector` qui projette. VERIFIE LIVE (runner frais, board MC1_67) : le Big Mek liste
`KustomForceFieldReworked` ET `KustomForceFieldReworked_Orks`, ses allies n'en listent AUCUN.

## Les DEUX effets partitionnent les cibles PAR FACTION -- meme selecteur de tete, filtre INVERSE

`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffectReworked$$CreateTargetSelector` :

    Filter( Owner@+0x30 + AdjacentFriends(Owner, unique = 1, unitSelectionType = 3),
            !HasFaction(Subject@DSLSelectors+0x68, UnitFaction.Orks = 5, 3) )

`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffect_Orks$$CreateTargetSelector` : LE MEME
corps, **sans** le `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot`.

  * `DSLSelectors$$Filter(entities, trigger)` delegue litteralement a `FromTrigger(entities,
    trigger, 0)` ; `Subject()` = `ActiveTarget@DSLSelectors+0x68`, l'element courant du filtre (meme slot
    que `entities/effects/loki/daemonic_patrons.py`).
  * `IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` resout son selecteur par UNE
    unite, puis `IdunBattle.Entities.UnitExtensions$$HasFaction(unit, faction)` -- qui compare
    `System.Enum.ToString(UnitFaction)` a une CHAINE. D'ou la comparaison par NOM cote port.
  * Le noeud de tete (`Owner + AdjacentFriends`) est le FOYER PARTAGE
    `effects/aura_selectors.adjacent_friends_including_owner` : le `op_Subtraction` d'`AdjacentFriends`
    exclut le porteur, le `op_Addition` du `CreateTargetSelector` le RE-AJOUTE.

⚠ **Le porteur est DANS sa propre aura**, et c'est le quirk que ni l'i2 ni les voisins de forme ne
donnent : l'i2 de la version NON reworked dit « All friendly **adjacent** units », et
`IconOfObstinacy` -- qui porte le MEME `AdjacentFriends(Owner, unique, OnlyAliveAndTargetable)` --
n'a PAS l'`op_Addition`. Le Big Mek etant lui-meme Ork, c'est l'effet `_Orks` (1567) qu'il porte
sur lui.

## Magnitudes -- DEUX variables distinctes, pas un facteur

`...KustomForceFieldEffectReworked$$GetDynamicStatModificationAmount` :
`ConfigVar( TriggeredAbilityType.KustomForceFieldReworked = 0x60b, unit = EffectSource(Get(effect)),
AbilityVariableType.extraArmor = 0x1b = 27 )`
`...KustomForceFieldEffect_Orks$$GetDynamicStatModificationAmount` : idem avec
`AbilityVariableType.extraArmor_2 = 0x9d = 157`.

`unit = EffectSource(...)` -> la magnitude s'indexe sur l'`AbilityState` de la **SOURCE** (le Big
Mek), jamais sur celle du buffe : `self.ability_level` / `self.ability_variables_multiplier` de
l'instance, qui vit sur le porteur. Les DEUX variables sont dans `variablesAffectedByRarityBonus`
-> scalees par le multiplier du PORTEUR.

⚠ QUALIFICATION D'ENUM : `27` et `157` sont des `AbilityVariableType` -- c'est le type DECLARE du
1er parametre de la surcharge `DSLFormulas$$ConfigVar(abilityType, unit, variableType)` (celle dont
le 3e argument est un selecteur d'unite, LU au call-site). `AbilityConstantType(27)` /
`(157)` nomment autre chose, et l'ability 1547 n'a AUCUNE constante.
Homonymes a ecarter : `TriggeredAbilityType` 1566/1567 et `ActiveAbilityType` 1566/1567 n'ont rien
a voir avec les `EffectType` du meme ordinal.

## GROUND TRUTH LIVE (#930 -- runner MC1_67 / seed 777, `statModSources` statType 16)

`orksBigMek` (rank 17 -> ability level 50, multiplier 180) + 3 allies :

    u81 orksBigMek     Orks           (1,0)                 fixedArmor +1197  source = effet 100
    u83 orksNob        Orks           (0,0) adjacent        fixedArmor +1197  source = effet 100
    u85 ultraApothecary Ultramarines  (1,1) adjacent        fixedArmor  +797  source = effet  99
    u87 astraBullgryn  AstraMilitarum (0,1) NON adjacent    fixedArmor  ABSENT

    extraArmor[50]   = 443 x 1.8 =  797   (effet 99  = 1566, cibles NON-Orks)
    extraArmor_2[50] = 665 x 1.8 = 1197   (effet 100 = 1567, cibles Orks)

Et l'aura est RE-EVALUEE A CHAQUE MOUVEMENT (meme mesure) : `astraBullgryn` deplace en (2,0)
-- adjacent -- GAGNE ses +797 ; `ultraApothecary` deplace en (1,3) les PERD entierement
(`fixedArmor` redevient ABSENT). Le port materialise/reverte au `MoveUnitOperation`, il ne fige
pas le seed.
"""
from __future__ import annotations

from ..aura_selectors import adjacent_friends_including_owner, faction_of
from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.stats import StatType
from ....entities.unit_faction import UnitFaction

#: cle gameconfig de l'ability qui pose les deux effets -- c'est SON `AbilityState` que
#: `ConfigVar(0x60b, EffectSource(...), <var>)` resout.
_KUSTOM_FORCE_FIELD_REWORKED = "KustomForceFieldReworked"   # TriggeredAbilityType 0x60b = 1547

#: `HasFaction(Subject, 0x5)` -- compare par NOM (`System.Enum.ToString(UnitFaction)` vs
#: `FactionComponent+0x30`), donc c'est le `.name` du membre qu'on confronte au `FactionId`
#: gameconfig, jamais l'ordinal.
_FACTION_ORKS = UnitFaction.Orks.name                        # UnitFaction.Orks = 5


class _KustomForceFieldReworkedAuraEffect(BaseEffect):
    """Socle des DEUX `ADynamicStatModifierEffect` de `KustomForceFieldReworked` -- `.ctor`
    identique (`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffectReworked$$.ctor` et
    `...KustomForceFieldEffect_Orks$$.ctor` ont MEME empreinte de corps) :
    `AStatModifierEffect( sourceAbility = AbilityOrEffect(...), unitEffectType = null,
    canBeImmuneTo = false, keepOnRevive = true, isMultiply = false )`.

    INTERFACE PORT (duck-typed, consommee par `runner/operations/aura_stat_mods.py` -- les deux
    points de cablage, `snapshot.load_state` au SEED et `MoveUnitOperation.execute` au MOUVEMENT,
    sont deja generiques : ce module n'a rien a cabler).

    Les deux sous-classes ne different QUE par `_VAR` et `_ORKS_ONLY` : c'est exactement la seule
    difference du binaire (meme selecteur de tete, filtre `HasFaction` inverse, variable distincte).
    """

    _VAR = ""                    # `AbilityVariableType` lu par `ConfigVar`
    _VAR_TYPE = None             # le membre d'enum correspondant (qualification, cf. en-tete)
    _ORKS_ONLY = False           # `HasFaction(Subject, Orks)` vs son `op_LogicalNot`

    def aura_stat_modification_stat(self) -> int:
        """`statType` du helper `AddDynamicStatModifierEffectToOwner` = `0x10` = 16."""
        return int(StatType.FIXED_ARMOR)

    def aura_stat_modification_amount(self) -> "int | None":
        """`ConfigVar( 0x60b, EffectSource(Get(effect)), <_VAR> )` -- indexe sur la SOURCE."""
        if self.ability_level is None:
            return None
        return ability_var(_KUSTOM_FORCE_FIELD_REWORKED, self._VAR, self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        """`Filter( Owner + AdjacentFriends(Owner, unique, OnlyAliveAndTargetable),
        [!]HasFaction(Subject, UnitFaction.Orks) )` evalue contre l'ECS.

        Le noeud de tete est le FOYER PARTAGE
        `effects/aura_selectors.adjacent_friends_including_owner` ; ne reste ici que le filtre
        PROPRE a la classe.

        ⚠ Une faction INCONNUE (`faction_of` rend `None` : pas de `visual_id`, unite hors
        gameconfig) n'est PAS assimilee a « non-Ork » : elle est ECARTEE des deux effets. Le natif
        lit un `FactionComponent` toujours renseigne ; cote port l'absence est un DEFAUT DE MESURE,
        et le rabattre sur une valeur ferait poser un buff que le natif ne pose peut-etre pas."""
        out: list = []
        for uid in adjacent_friends_including_owner(state, owner_id):
            fac = faction_of(state, uid)
            if fac is None:
                continue
            if (fac == _FACTION_ORKS) != self._ORKS_ONLY:
                continue                       # `HasFaction(Subject, Orks)` / `op_LogicalNot`
            out.append(uid)
        return out


class KustomForceFieldReworkedEffect(_KustomForceFieldReworkedAuraEffect):
    """`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffectReworked` (EffectType 0x61e = 1566).

    `$$CreateTargetSelector` : le filtre porte `op_LogicalNot(HasFaction(Subject, Orks))` -> les
    cibles NON-Orks (le porteur, Ork, en est donc EXCLU).
    `$$GetDynamicStatModificationAmount` : `AbilityVariableType.extraArmor` (0x1b = 27) ;
    stat ecrit = `StatType.FixedArmor` = 16. Mesure live : +797 (443 x 1.8)."""

    _VAR = "extraArmor"
    _VAR_TYPE = AbilityVariableType.extraArmor          # 0x1b = 27
    _ORKS_ONLY = False


class KustomForceFieldReworkedOrksEffect(_KustomForceFieldReworkedAuraEffect):
    """`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffect_Orks` (EffectType 0x61f = 1567).

    ⚠ Le NOM de la classe native ne porte PAS « Reworked » -- mais son
    `$$GetDynamicStatModificationAmount` lit `ConfigVar( 0x60b = KustomForceFieldReworked, ...)`,
    et c'est bien elle que `KustomForceFieldReworkedAbility$$CreateBehaviour` pose. La version NON
    reworked (`KustomForceFieldAbility`, ability 0x44e = 1102) pose, elle, l'unique
    `KustomForceFieldEffect` (0x448 = 1096) qui lit `ConfigVar( 0x44e, ..., extraArmor )`.
    L'appartenance se lit au DECOMPILE, pas au nom.

    `$$CreateTargetSelector` : MEME corps que sa soeur **sans** l'`op_LogicalNot` -> les cibles
    Orks, PORTEUR COMPRIS.
    `$$GetDynamicStatModificationAmount` : `AbilityVariableType.extraArmor_2` (0x9d = 157) ;
    stat ecrit = `StatType.FixedArmor` = 16. Mesure live : +1197 (665 x 1.8)."""

    _VAR = "extraArmor_2"
    _VAR_TYPE = AbilityVariableType.extraArmor_2        # 0x9d = 157
    _ORKS_ONLY = True
