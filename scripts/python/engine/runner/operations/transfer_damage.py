"""#1020 -- `IdunBattle.Operations.TransferDamageOperation`, l'operation IMPERATIVE qui DEPLACE
un degat en attente de la victime vers un protecteur.

CHAINE NATIVE, lue de bout en bout (build `rnca9r7q6c`) :

    IdunBattleLogic.Entities.DSLBehaviors$$TransferDamage(caster, originalTarget, transferTargets,
                                                          transferAbility, attackAbility)
      -> IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$.ctor
      -> IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$Execute
           (lit `AbilityEntities+0x108` = le `Nullable<HitIndex>` du coup courant)
      -> Core.Services.OperationProcessor$$TransferDamage(..., hitIndex)     // slot 68
      -> IdunBattle.Operations.TransferDamageOperation$$Execute

ET LE POINT QUI TRANCHE TOUT, dans `IdunBattle.Operations.TransferDamageOperation$$GetDamage` :

    d = <healthComponent>+0x64                       // Nullable<DamageAppliedResult>
    if (!d.HasValue) return null;
    dmg = DamageAppliedResult.get_Damage(d.Value);   // = +0x08 shieldDamage + +0x04 healthDamage
    *(qword*)(comp+0x64) = 0;                        // <-- LA VALEUR PENDANTE EST **CONSOMMEE**
    *(qword*)(comp+0x6c) = 0;
    return new Damage(d.Value.<+0x00 damageProfileType>, dmg);

**CE N'EST PAS UN BONUS, C'EST UNE CONSOMMATION.** Le degat en attente sur la victime est mis a
`null`, donc la relecture d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`
(`System.Nullable<T>$$GetValueOrDefault`, qui rend la struct ZERO) fait que
`FillUpStatComponent$$Reduce(hp, 0)` n'enleve plus rien. Confondre les deux DOUBLE le degat au
lieu de le deplacer -- c'est le piege central de cette mecanique.

Puis `Execute` boucle sur les `transferTargets`, emet un pas de flux `0x23`
(`StepType.TransferDamage` = 35) portant `{0xb4: originalTarget, 0xb7: transferTargets,
0xb8: transferTarget}`, et appelle le slot **`0x40`** de l'`OperationProcessor`
(`DirectDamage`, 6 arguments + options) sur le protecteur, avec le montant et le PROFIL du
degat consomme.

⚠ **LE DEGAT TRANSFERE N'EST NI RE-PERCE NI RE-REDUIT PAR L'ARMURE.**
`IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage` est LU en entier et ne fait
qu'UNE chose :

    Fix64 d = (Fix64)damage;
    ApplyGroupUnitDamageLimit(this, &d, null, target, <unitComp+0x18>, hitsMultipleMembers);
    return (int)d;

-- pas de `PiercingRatio`, pas de `FixedArmor`, pas de modificateur. Le montant arrive DEJA
resolu (il sort d'un `DamageAppliedResult`, donc apres crit / block / armure / limites cote
victime) : le re-reduire cote protecteur serait une double application. Seul le **member-cap**
s'applique, exactement comme sur le chemin `execute_direct` du DoT de tuile.
"""
from __future__ import annotations

from typing import Optional

from ...services.damage_combat import calculate_damage_operation
from ...services.trait_damage_limits import apply_group_unit_damage_limit
from ..components import HealthComponent, UnitComponent
from ..state import State
from . import damage as _damage_ops   # FORME B (liaison de MODULE). Le "cycle damage <-> transfert"
#     annonce au site est REFUTE par la mesure : `import engine.runner.operations.damage` en
#     process frais ne charge PAS ce module. Arete GRATUITE (#485).


def consume_pending_damage(state: State, original_target_id: int):
    """`IdunBattle.Operations.TransferDamageOperation$$GetDamage` -- mirror 1:1.

    Rend le `PendingDamage` CONSOMME (et laisse `HealthComponent.pending_damage` a `None`), ou
    `None` si le `Nullable` etait deja vide -- auquel cas `Execute` sort sans rien faire
    (`if (*pcVar7 != '\\0')` garde toute la boucle de transfert).

    Le port ne consomme QUE le champ pendant : c'est la seule ecriture du natif ici, et c'est
    elle qui retire le degat a la victime. Aucune mutation de PV, aucun event."""
    e = state.get_entity(int(original_target_id))
    thc = e.get_component(HealthComponent) if e is not None else None
    if thc is None:
        return None
    pend = getattr(thc, "pending_damage", None)
    if pend is None:
        return None
    thc.pending_damage = None                 # `*(qword*)(comp+0x64) = 0` -- LA CONSOMMATION
    return pend


def _member_capped(state: State, target_id: int, thc, amount: int) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage` = le SEUL etage applique
    au montant transfere : `ApplyGroupUnitDamageLimit(damage, hitsMultipleMembers = null, target,
    <unitComp+0x18>, ...)`. `nrOfMembers <= 1` (tout heros / tout drone) -> no-op strict."""
    e = state.get_entity(int(target_id))
    tuc = e.get_component(UnitComponent) if e is not None else None
    if tuc is None or not thc.hp_max:
        return int(amount)
    import gameconfig as GC
    n = int((GC.unit(tuc.visual_id) or {}).get("nrOfMembers") or 1)
    if n <= 1:
        return int(amount)
    return apply_group_unit_damage_limit(int(amount), False, n, int(thc.hp_max), int(thc.hp))


def transfer_damage_operation(state: State, caster_id: Optional[int], original_target_id: int,
                              transfer_target_id: int,
                              hit_index: Optional[int] = None,
                              attack_ability=None) -> Optional[dict]:
    """`IdunBattle.Operations.TransferDamageOperation$$Execute` -- mirror.

    1. `GetDamage(originalTarget)` : lit ET **CONSOMME** le pending de la victime. `null` -> sortie
       immediate, rien n'est transfere et la victime encaisse normalement.
    2. Pour le `transferTarget` : le pas de flux `0x23` (`StepType.TransferDamage`), puis le slot
       `0x40` = `DirectDamage(caster, originalTarget, transferTarget, damage, profile, ...)`.
       Le port n'emet pas de pas de flux (le runner n'a pas de `BattleStream`) ; le dict rendu
       porte les memes trois champs, sous leurs noms.
    3. Le `DirectDamage` route par le chokepoint partage `_apply_damage_pipeline`, `is_attack=False`
       (un transfert n'est PAS une attaque : ni `RegisterAttackMade`, ni `RegisterAttackReceived`).

    ⚠ **RE-ENTRANCE.** Cette operation est appelee DEPUIS le dispatch d'`On(0x39 = PreDamageTaken)`,
    donc depuis l'interieur de `_apply_damage_pipeline` de la VICTIME -- exactement comme le natif
    (`TransferDamageOperation` -> `DirectDamage` -> `ApplyDamageOperation`). Le protecteur repasse
    donc par le pipeline, y compris par son propre `On(0x39)`. Le natif n'a pas de garde de
    profondeur : la terminaison vient du GATE des abilities de transfert elles-memes --
    `SaviorProtocolsAbility$$TargetIsValidTrigger` exige
    `!ActorHasTriggeredAbility(Target, 0x460 = 1120)`, donc un drone qui encaisse un transfert ne
    peut pas le re-transferer a un autre drone.

    `caster_id` = la SOURCE du degat (l'attaquant), pour l'attribution de mort du protecteur.

    `attack_ability` (#1020-r2) = le 5e parametre `attackAbility` de l'operation. C'est le SEUL des
    deux `AbilityOrEffect` que le corps CONSOMME, et sa destination est LUE : ses 0x18 octets sont
    recopies puis passes en 5e argument `abilityOrEffect` du slot `64 = DirectDamage`
    (`Core.Services.OperationProcessor$$DirectDamage(caster, target, damage, damageProfileType,
    abilityOrEffect, options)` -- slot resolu dans
    `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`, jamais devine). C'est donc lui
    qui NOMME la source du degat inflige au protecteur, et que grave `RecordDeathReason` si le
    protecteur en meurt.

    ⚠ Le 4e, `transferAbility`, n'a AUCUN autre usage dans ce corps que le null-check du pointeur
    (`if (transferAbility == 0) throw`) : il ne ressort ni dans le `DirectDamage`, ni dans le pas de
    flux. Il n'est donc pas porte ICI -- mais il n'est pas inerte pour autant : le BEHAVIOUR au
    dessus exige `HasValue` sur LES DEUX avant d'appeler cette operation, et c'est un vrai GATE
    (cf. `abilities/behaviours/transfer.py`).

    Rend `{original_target, transfer_target, profile, requested, health, shield}` ou `None`."""
    pend = consume_pending_damage(state, original_target_id)
    if pend is None:
        return None
    amount = int(pend.total())                          # `DamageAppliedResult$$get_Damage`
    tgt = state.get_entity(int(transfer_target_id))
    thc = tgt.get_component(HealthComponent) if tgt is not None else None
    if thc is None or thc.hp is None:
        # Le pending reste consomme : le natif ne le remet PAS: `GetDamage` a deja ecrit le zero
        # avant meme d'entrer dans la boucle des `transferTargets`. Le degat est donc PERDU, pas
        # rendu a la victime -- quirk natif porte tel quel.
        return {"original_target": int(original_target_id),
                "transfer_target": int(transfer_target_id),
                "profile": pend.profile, "requested": amount, "health": 0, "shield": 0}
    amount = _member_capped(state, transfer_target_id, thc, amount)
    if amount <= 0:
        return {"original_target": int(original_target_id),
                "transfer_target": int(transfer_target_id),
                "profile": pend.profile, "requested": amount, "health": 0, "shield": 0}
    # Split BOUCLIER d'abord puis PV, sans block ni evasion (0 tirage) -- meme etage que le
    # knockback (`displace.py`), qui route lui aussi un montant deja resolu.
    _shc, shield_total = _damage_ops.AttackDamageOperation._target_shield(tgt)
    dmg = calculate_damage_operation(amount, shield=shield_total)
    # La depletion du bouclier du PROTECTEUR appartient au chokepoint (#1020-r1) : le natif
    # descend `DirectDamage` -> `ApplyDamageOperation$$Execute`, et c'est LA que vit
    # `ApplyDamageOperation$$ReduceShield`, sur le pending RELU. Il y avait ici une depletion
    # MANUELLE et ANTERIEURE (`shc.shield = max(0, (shc.shield or 0) - dmg.shield)`) qui, en plus
    # de doubler celle du chokepoint, visait un attribut INEXISTANT : `ShieldComponent.__slots__`
    # vaut `('shields', 'next_id')`. Tout transfert vers un protecteur PORTANT un bouclier levait
    # donc `AttributeError: 'ShieldComponent' object has no attribute 'shield'` -- crash dur,
    # jamais atteint parce que les six porteurs de `SaviorProtocols` sont des drones T'au sans
    # bouclier, et que rien ne montait ce regime.
    _damage_ops.AttackDamageOperation._apply_damage_pipeline(
        state, int(transfer_target_id), caster_id, tgt, thc, dmg.health, pend.profile,
        dmg.shield, dmg.armor, is_attack=False,
        # #1020-r2 : `attackAbility` -> 5e argument `abilityOrEffect` du slot `64 = DirectDamage`.
        # C'est lui qui nomme la source du degat porte par le protecteur (et donc sa
        # `DamageSource` de mort), la ou le port ne nommait que le `caster`.
        source_ability=attack_ability)
    return {"original_target": int(original_target_id),
            "transfer_target": int(transfer_target_id),
            "profile": pend.profile, "requested": amount,
            "health": int(dmg.health), "shield": int(dmg.shield),
            "hit_index": hit_index}
