"""Nature du canal de COUPS et marqueur de kind << attaque-normale >>, extraits d'
`operations/damage_ops.py` (scission du module >1000 lignes, tache #169 -- deplacement
VERBATIM, zero changement de comportement).

`hits_channel_is_melee` est consommee par le vecteur d'ABILITY (`ability.py`) ;
`_normal_attack_kind` par la voie NORMALE (`normal.py`).

PATCH-POINT (tests/probes) : ces deux noms sont resolus dans les globals du sous-module
qui les CONSOMME -- patcher `damage_ops.<sous-module>.<nom>`, jamais le `__init__`."""
from __future__ import annotations

from ...state import State


def hits_channel_is_melee(state: State, attacker_id: int, target_id: int,
                          is_melee: Optional[bool]) -> Optional[bool]:
    """Mirror de `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` pour le canal de COUPS d'une
    attaque d'ABILITY (#122).

    La facade `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` ne calcule RIEN : elle resout
    le slot d'interface 2 de la `BattleQuery` et lui passe la tranche `+0x10..+0x28` de l'AttackData,
    c'est-a-dire le `Nullable<AbilityOrEffect>` de l'attaque en cours (ecrit la par
    `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits`). `BattleQuery$$IsMeleeAttack` (et son
    jumeau `$$IsRangedAttack`) partent alors de
    `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability)` :

        rangeType 0 (absent) -> IsMeleeAttack FALSE  et  IsRangedAttack FALSE
        rangeType 1 (Melee)  -> IsMeleeAttack TRUE
        rangeType 2 (Ranged) -> IsRangedAttack TRUE
        rangeType 3 (Normal) -> HasFlag(unit, 0x15) ? melee=FALSE/ranged=TRUE
                                                    : AreUnitsInMelee(...)   (POSITIONNEL)
        (>3 -> NotImplementedException : la table est exhaustive)

    -> la nature du coup est **DECLAREE par l'ability**, sauf pour la seule valeur `Normal`. C'est le
    MEME predicat que celui des triggers d'effet (`IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack`/`$$IsRangedAttack`), donc
    le meme resultat alimente le terme `ExtraHitsMelee` de la base ET les gates des effets — un seul
    point de calcul, comme le natif.

    `is_melee` = la nature DECLAREE que la feuille d'attaque a lue dans `attackRangeType` (True=Melee,
    False=Ranged, **None = attackRangeType absent** -> les DEUX predicats faux, gates inertes). Le port
    ne modelise pas `Normal`(3) : aucune des 10 abilities qui le portent n'est une feuille d'attaque
    (residu nomme, case-122 §6). `state`/`attacker_id`/`target_id` sont dans la signature parce que le
    natif les consomme dans cette branche-la ; ils restent inutilises tant qu'elle n'est pas portee.

    AVANT #122 la facade ability recalculait cette nature POSITIONNELLEMENT (`_is_ranged_position`) :
    troisieme fork de `IsMeleeAttack` apres #101 et #106, sur la MEME fonction native. Une ability
    declaree `Ranged` castee au contact passait alors pour de la melee -> `Camouflage_HitReduction` /
    `BigTarget` / `LightCover` tus, `Parry` sur-applique, `ExtraHitsMelee` ajoute a tort."""
    return is_melee


def _normal_attack_kind() -> int:
    """`AbilityOrEffect(0x3f5)` = le marqueur de KIND << attaque-normale >> que la voie NORMALE du port
    thread partout comme `currentAbility` (cf. `abilities/attack_type.NORMAL_ATTACK_KIND`). Import
    PARESSEUX : `abilities/__init__` tire tout le registre d'abilities, qui re-importe `damage` ->
    cycle a l'import module."""
    from ...abilities.attack_type import NORMAL_ATTACK_KIND
    return NORMAL_ATTACK_KIND
