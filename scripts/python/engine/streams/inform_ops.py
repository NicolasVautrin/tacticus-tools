"""La face STREAM d'`IdunBattle.Operations.InformOperation` -- le pas `Action=Info`.

C'est l'aval du noeud DSL `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon` : le noeud
CONSTRUIT un `Dictionary<TagKey,int>`, l'Operation l'EMET. Les deux gestes sont distincts, et
c'est ce qui rendait ces tags invisibles au canal « qui appelle `IStreamListener` » de
`probe_477r18` -- il a fallu un canal separe pour les voir (`docs/rl/case-477r18-perimetre-du-
deroule.md` canal 4).

LA CHAINE, lue de bout en bout et NOMMEE :

    IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour
      weapon = FindAttackWeapon(entities);        // slot 0xaf d'IBattleQuery
      if (weapon == null) return default;
      ExecuteInformWeapon(this, weapon, entities, useSpecial: 0);
    -> IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteInformWeapon
         behaviour = DSLBehaviors.InformWeapon(weapon, useSpecial);   // surcharge a DEUX arguments
         return AActiveAbility.Execute(this, behaviour, entities);
    -> IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(weapon, useSpecial)
         damageProfileType = new Nullable<DamageProfileType>(weapon->{+0x10});
         isMelee           = WeaponProfile.get_IsMelee(weapon);
         return InformWeapon(damageProfileType, isMelee, useSpecial);  // surcharge a TROIS
    -> IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)
         -> `IdunBattle.Entities.Behaviours.InformBehaviour` (le MEME `Il2CppClass*` et le MEME
            ctor a 3 arguments que `DSLBehaviors$$Inform(Dictionary<TagKey,Int32>)`)
    -> IdunBattle.Entities.Behaviours.InformBehaviour$$Execute
         itere le dictionnaire, evalue chaque `IAmountFormula` -- AUCUNE mutation ECS
    -> IdunBattle.Operations.InformOperation$$Execute(tags)
         Events.Action(StepType.Info /*0x1d*/, 0 /*NO_ENTITY*/, tags);

Ce que le flux natif ECRIT, mesure sur MC1_67 (#419-r1-tr14-r4-r2-r1) :

    Group=Ability_Power Entity=83 Source=Loki_NormalAttack InitialTarget=77
        Action=Info Entity=NO_ENTITY
            Tag=Attack_Weapon_IsMelee:1
            Tag=Attack_Weapon_DamageProfile:14
        Group=NormalAttack_AtomicDamage ...

⚠ `Entity=NO_ENTITY` EST LU, pas suppose : `InformOperation$$Execute` passe le litteral `0` en
quatrieme argument du helper d'emission, et `0` est le seul membre d'`IdunBattle.Core.BEntityId`
(cf. `entity_id.py`). L'entite du CASTER est portee par le `Group=` englobant, pas par la ligne.

⚠ L'ORDRE D'INSERTION DU DICTIONNAIRE N'EST PAS OBSERVABLE. Le natif insere `0x93` puis `0x92`
puis (conditionnellement) `0x94` ; le flux les ecrit dans l'ordre des ORDINAUX parce que
`IdunBattle.BattleStream.Loggers.StreamCache$$Action` recopie dans un
`SortedDictionary<TagKey,int>`. L'ordre du mirror est conserve pour la relecture ligne a ligne,
il ne porte aucune information.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional

from ..entities.damage_profile_type import DamageProfileType
from .dispatcher import StreamDispatcher
from .entity_id import NO_ENTITY
from .step_type import StepType
from .tag_key import TagKey


def get_inform_weapon_tags(damage_profile_type: Optional[int], is_melee: bool,
                           use_special: bool) -> Dict[int, int]:
    """Le `Dictionary<TagKey,int>` que construit
    `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)`
    -- FOYER UNIQUE des trois cles, partage par le noeud DSL du runner et la face stream.

        local_res10[0] = damageProfileType.HasValue ? (int)damageProfileType.Value : -1;
        dict.Add(0x93 /*Attack_Weapon_DamageProfile*/, local_res10[0]);   // INCONDITIONNEL
        dict.Add(0x92 /*Attack_Weapon_IsMelee*/,       (uint)isMelee & 0xff);  // INCONDITIONNEL
        if ((char)useSpecial != '\\0')
            dict.Add(0x94 /*Attack_Weapon_Use_Special*/, (uint)useSpecial & 0xff);

    `damage_profile_type` est l'ORDINAL (`DamageProfileType`), `None` = le `Nullable` VIDE -- que
    le natif ecrit `-1`, c'est-a-dire exactement `DamageProfileType.None_`. Ce n'est donc pas une
    sentinelle inventee : le port ECRIT le membre.

    ⚠ LA TROISIEME CLE EST CONDITIONNELLE, et c'est le seul endroit du mirror ou une cle peut
    manquer. La confondre avec « toujours posee, a 0 » ajouterait une ligne au flux."""
    tags: Dict[int, int] = {
        int(TagKey.Attack_Weapon_DamageProfile):
            int(DamageProfileType.None_) if damage_profile_type is None
            else int(damage_profile_type),
        int(TagKey.Attack_Weapon_IsMelee): 1 if is_melee else 0,
    }
    if use_special:
        tags[int(TagKey.Attack_Weapon_Use_Special)] = 1 if use_special else 0
    return tags


def get_inform_tags(tag_key: int, amount: int) -> Dict[int, int]:
    """Le `Dictionary<TagKey, IAmountFormula>` que construit la surcharge A UNE CLE de
    `IdunBattleLogic.Entities.DSLBehaviors$$Inform(TagKey tag, IAmountFormula value)` :

        var dict = new Dictionary<TagKey, IAmountFormula>();
        dict.Add(tag, value);                       // UN SEUL `Add`, INCONDITIONNEL
        return new InformBehaviour(dict, null);

    `IdunBattle.Entities.Behaviours.InformBehaviour$$Execute` evalue ensuite chaque formule et
    passe le `Dictionary<TagKey,int>` resultant a `IdunBattle.Operations.InformOperation$$Execute`
    -- c'est pourquoi le port prend l'ENTIER deja evalue : la formule est un arbre DSL, hors de
    la face stream.

    ⚠ CETTE SURCHARGE N'EST PAS LA SEULE : le build en porte SIX du meme nom. Celle-ci est
    identifiee par ses XREFS ENTRANTES -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    StandVigil_UpdateEffectRangeAbility$$CreateBehaviour` l'appelle avec
    `TagKey.Custom_Data /*0xcc*/`, ce que le flux confirme (`Action=Info Entity=NO_ENTITY` +
    `Tag=Custom_Data:<amount>` dans le `Group=Ability_Power Source=StandVigil`). Les deux autres
    surcharges a trois arguments enveloppent d'abord la valeur (`DSLFormulas$$ConditionalAmount`,
    ou une constante) puis DELEGUENT a celle-ci : le dictionnaire produit est le meme.

    ⚠ UNE SEULE CLE, TOUJOURS. La faute naturelle serait d'y ajouter les tags d'arme de
    `get_inform_weapon_tags` : ce sont DEUX foyers distincts, appeles par deux surcharges
    distinctes, et le natif n'en melange jamais les cles."""
    return {int(tag_key): int(amount)}


def inform(events: StreamDispatcher, tags: Mapping[int, int]) -> None:
    """`IdunBattle.Operations.InformOperation$$Execute(tags)` -- sa seule face, et elle tient en
    une ligne :

        if (this.Events == null) throw;                       // `this+0x10`
        return Events.Action(StepType.Info /*0x1d*/, 0 /*NO_ENTITY*/, tags);

    AUCUNE mutation d'etat, AUCUN tirage : l'Operation ne fait que dispatcher. C'est pour cela
    que le noeud est COMBAT-INERTE tout en etant parfaitement OBSERVABLE."""
    events.action(int(StepType.Info), NO_ENTITY, tags)
