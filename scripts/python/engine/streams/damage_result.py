"""Les TROIS structs que lit `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` (#477-r34).

Ce module ne porte AUCUNE emission : il porte la FORME des donnees qu'`ApplyDamageOperation`
passe au helper de tags. Les trois sont des `System.ValueType`, et leur LAYOUT est lu -- pas
devine -- dans un `.ctor` ou un accesseur NOMME du build.

    IdunBattle.Core.AbilityOrEffect                taille boxee 40  -> struct 0x18
    IdunBattle.Operations.DamageSource             taille boxee 124 -> struct 0x6c
    IdunBattle.Core.Services.DamageAppliedResult   taille boxee 176 -> struct 0xa0

(`data/symbols/<build>/frida/classes.tsv` publie la taille BOXEE : header 0x10 sur tout
`ValueType` -- cf. `reference_symbol_table_versioned`.)

`IdunBattle.Core.AbilityOrEffect` -- LES TROIS CHAMPS SONT NOMMES PAR LEURS SETTERS
-----------------------------------------------------------------------------------
`data/symbols/<build>/frida/methods.tsv` publie les trois, avec leur type declare :

    AbilityOrEffect.set_ActiveAbility     value: System.Nullable<IdunBattle.Entities.Enum.ActiveAbilityType>
    AbilityOrEffect.set_TriggeredAbility  value: System.Nullable<IdunBattle.Entities.Enum.TriggeredAbilityType>
    AbilityOrEffect.set_Effect            value: System.Nullable<IdunBattle.Entities.Enum.EffectType>

L'ORDRE des trois dans le struct est LU dans
`IdunBattle.Operations.DamageSource$$get_IsFromAnyAbility`, qui deroule `+0x00` (l'ability
active, sur laquelle il teste `StaticBattleRules.ActiveAbility$$IsRegularAttack`) puis `+0x08`
(l'ability declenchee). `GetDamageTags` deroule les trois dans le meme ordre, `+0x10` en
dernier : 3 x 8 octets = les 0x18 de la taille.

⚠ LE TROISIEME NOM NE SUIT PAS LE TAG QU'IL PRODUIT, ET C'EST LA FAUTE NATURELLE ICI. Le champ
s'appelle `TriggeredAbility` et porte un `TriggeredAbilityType` ; le tag que `GetDamageTags` en
tire s'appelle `TagKey.Passive_Ability_Type`. Un port qui apparierait « `Passive_Ability_Type`
-> un type passif » se tromperait de champ ET d'enum -- et le CLAUDE.md chiffre exactement ce
piege : `TriggeredAbilityType` partage **458** ordinaux avec `EffectType`, dont **454** nomment
autre chose. La confusion serait donc SILENCIEUSE sur l'ordinal ; seul le NOM du tag emis la
rend visible, et c'est ce que la contre-epreuve `damage_voie_source` exerce.

`IdunBattle.Operations.DamageSource` -- DEUX `AbilityOrEffect?`, LUS PAR LEUR OFFSET
------------------------------------------------------------------------------------
Le type n'expose que quatre methodes dans `frida/methods.tsv` (`IsFromAbility`, `ToString`,
`get_IsFromAnyAbility`, `get_KillerId`) : ses CHAMPS n'ont aucun accesseur nomme publie, donc
ils sont cites par leur OFFSET RELATIF, comme le CLAUDE.md l'autorise. Deux d'entre eux sont
des `System.Nullable<AbilityOrEffect>` (0x1c octets chacun : 0x18 + le bool + padding) :

    DamageSource+0x18   `AbilityOrEffect?`  -- la source du COUP. C'est celui que
                        `get_IsFromAnyAbility` lit, et celui dont `GetDamageTags` tire
                        `Active_Ability_Type` / `Passive_Ability_Type` / `Effect_Type` ;
    DamageSource+0x50   `AbilityOrEffect?`  -- la source du HIT ADDITIONNEL, dont il tire
                        `Additional_Hit_ActiveAbility_Source` /
                        `Additional_Hit_TriggeredAbility_Source` /
                        `Additional_Hit_Effect_Source`.

`0x50 + 0x1c = 0x6c` : les deux offsets et la taille du type se referment exactement.

`IdunBattle.Core.Services.DamageAppliedResult` -- LAYOUT LU DANS SON `.ctor`
---------------------------------------------------------------------------
`IdunBattle.Core.Services.DamageAppliedResult$$.ctor` ecrit chaque parametre a un offset
explicite ; c'est cette fonction, et elle seule, qui donne le layout :

    +0x00 int   damageProfileType        +0x14 int   hitIndex
    +0x04 int   healthDamage             +0x18 bool  isFirstDamagingHit
    +0x08 int   shieldDamage             +0x20 ref   failedBlockIds
    +0x0c bool  didBlock                 +0x28 ..    source   (DamageSource, 0x6c octets)
    +0x0d bool  didEvade                 +0x94 bool  wasHitTransferred
    +0x0e bool  didCrit                  +0x98 int   initialDamage
    +0x0f bool  didOverkill
    +0x10 bool  isForceOverkill
    +0x11 bool  isPreventLeftoverHits

⚠ `armorDamage` EST UN PARAMETRE DU CTOR QUE LE CTOR N'ECRIT NULLE PART. Le decompile ne lui
donne aucun offset -- il est LU et non porte, plutot que place a un offset invente.

⚠ LES DEUX OFFSETS QUE LIT `GetDamageTags` SE REFERMENT SUR CE LAYOUT : `damageResult+0x40` =
`source+0x18`, et `damageResult+0x78` = `source+0x50`. C'est ce recoupement -- deux fonctions
independantes, un seul layout -- qui attribue les deux `AbilityOrEffect?` a `DamageSource`
plutot qu'a `DamageAppliedResult`.

CE QUE CE MODULE NE PORTE PAS
-----------------------------
Les champs que `GetDamageTags` ne lit pas (`healthDamage`, `shieldDamage`, `isForceOverkill`,
`isPreventLeftoverHits`, `failedBlockIds`, `wasHitTransferred`, `initialDamage`,
`isFirstDamagingHit`, et les champs de `DamageSource` autres que les deux `AbilityOrEffect?`)
sont ABSENTS de ces dataclasses. Les inscrire sans producteur ni lecteur porte en ferait des
champs morts que rien ne confronte ; ils sont NOMMES ci-dessus, ce qui suffit a les retrouver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AbilityOrEffect:
    """`IdunBattle.Core.AbilityOrEffect` -- trois `Nullable<T>` d'enums, dans l'ordre du struct.

    Les trois sont mutuellement exclusifs EN PRATIQUE (les quatre `op_Implicit` du build en
    construisent un depuis UN seul des trois types), mais le struct ne l'impose pas et
    `GetDamageTags` ne le suppose pas non plus : il teste les trois en cascade et s'arrete au
    PREMIER qui a une valeur. Le port fait pareil (`premier_present`), et n'ajoute aucune
    garde d'exclusivite que le natif n'a pas."""

    #: `+0x00` -- `Nullable<IdunBattle.Entities.Enum.ActiveAbilityType>`.
    active_ability: Optional[int] = None
    #: `+0x08` -- `Nullable<IdunBattle.Entities.Enum.TriggeredAbilityType>`.
    #: ⚠ c'est CE champ que `GetDamageTags` ecrit sous `TagKey.Passive_Ability_Type`.
    triggered_ability: Optional[int] = None
    #: `+0x10` -- `Nullable<IdunBattle.Entities.Enum.EffectType>`.
    effect: Optional[int] = None

    @property
    def has_any(self) -> bool:
        """« au moins un des trois a une valeur » -- le cas ou `GetDamageTags` n'ecrit aucun
        tag de source alors que le `AbilityOrEffect?` englobant, lui, EN A une."""
        return (self.active_ability is not None or self.triggered_ability is not None
                or self.effect is not None)


@dataclass(frozen=True)
class DamageSource:
    """`IdunBattle.Operations.DamageSource`, reduit aux DEUX champs que `GetDamageTags` lit.

    Les noms Python viennent des TAGS que chacun produit (`+0x18` -> les trois tags de source,
    `+0x50` -> les trois `Additional_Hit_*_Source`), parce qu'aucun accesseur nomme du build ne
    les nomme -- cf. docstring du module."""

    #: `DamageSource+0x18` -- `Nullable<AbilityOrEffect>`. `None` = le `Nullable` est vide.
    source: Optional[AbilityOrEffect] = None
    #: `DamageSource+0x50` -- `Nullable<AbilityOrEffect>`.
    additional_hit_source: Optional[AbilityOrEffect] = None


@dataclass(frozen=True)
class DamageAppliedResult:
    """`IdunBattle.Core.Services.DamageAppliedResult`, reduit aux champs que `GetDamageTags` lit.

    Les noms Python sont ceux des PARAMETRES du `.ctor` natif, verbatim (`damageProfileType`,
    `hitIndex`, `didBlock`, `didEvade`, `didCrit`, `didOverkill`, `source`)."""

    #: `+0x00` -- `IdunBattle.Entities.Enum.DamageProfileType`.
    damage_profile_type: int = 0
    #: `+0x14` -- `hitIndex`. ⚠ C'est de LUI que sort `TagKey.Attack_Is_First_Hit`, par le test
    #: `hitIndex == 0`, et NON du champ `isFirstDamagingHit` (`+0x18`) que le ctor ecrit juste
    #: a cote. Les deux existent, seul le premier est lu ici.
    hit_index: int = 0
    #: `+0x0c`
    did_block: bool = False
    #: `+0x0d`
    did_evade: bool = False
    #: `+0x0e`
    did_crit: bool = False
    #: `+0x0f`
    did_overkill: bool = False
    #: `+0x28` -- `DamageSource`, dont seuls les deux `AbilityOrEffect?` sont portes.
    source: DamageSource = DamageSource()
