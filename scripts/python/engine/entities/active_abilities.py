"""Substrat des abilities ACTIVES d'une unite -- le pendant EXACT, sur l'axe ACTIF, de
`entities.triggered_ability_type.{triggered_ability_ids, entity_triggered_ability_ids}`.

POURQUOI UN MODULE A PART, et pas au bas d'`active_ability_type.py` comme son jumeau declenche :
`active_ability_type.py` est REECRIT EN ENTIER par son generateur
(`regen_active_ability_tables.py` fait `MIRROR.write_text(texte)`, la ou `regen_enum_mirrors.py`
ne remplace que le BLOC de membres et conserve la queue du fichier). Toute fonction posee la-bas
disparaitrait a la prochaine regeneration, SANS ERREUR -- exactement le genre de perte silencieuse
que ce depot chasse. Le mirror reste donc pur ; le lecteur vit ici.

CE QUE LE NATIF INTERROGE. `IdunBattle.Entities.UnitExtensions$$HasActiveAbility(unit, type)` :

    comp = GetComponent<ActiveAbilityComponent>(unit);
    return comp != null && comp.<+0x20 KeyedCollection>.Contains(type);

c.-a-d. l'`ActiveAbilityComponent` REEL de l'entite, pas le kit gameconfig par `visualId`. Le
premier consommateur porte est le predicat de `RadSaturationPlaybook`
(`IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003Cu003Ec$$u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0`
= `HasActiveAbility(f, 0x45e)`), qui l'applique aux AMIS ADJACENTS de la tuile candidate.
"""
from __future__ import annotations

from .active_ability_type import ActiveAbilityType


def kit_active_ability_ids(visual_id: "str | None") -> list[int]:
    """Ids `ActiveAbilityType` du KIT ACTIF gameconfig d'une unite (`activeAbilities` -> enum).

    Borne STATIQUE (le substrat d'avant tout canal live) : elle ignore l'attaque normale posee par
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` et les abilities de
    `AddDerivedAbilities`. `[]` si l'unite est inconnue ou si un nom sort de l'enum."""
    if not visual_id:
        return []
    import gameconfig as GC
    out: list[int] = []
    for name in ((GC.unit(visual_id) or {}).get("activeAbilities") or []):
        m = ActiveAbilityType.__members__.get(name)
        if m is not None:
            out.append(int(m))
    return out


def entity_active_ability_ids(unit_ctx, visual_id: "str | None" = None) -> list[int]:
    """IDS du kit ACTIF d'une ENTITE -- ce que `HasActiveAbility` interroge reellement.

    `unit_ctx` = le `UnitContext` de l'entite (`StatsComponent.ctx` cote runner, `Scene.ctx(uid)`
    cote prediction : le MEME objet, cf. `Scene.from_state`). Son champ `active_abilities` porte
    les NOMS lus dans `unitAbilityStates.actives[].type`, c.-a-d. l'`ActiveAbilityComponent` ;
    il est seede par `snapshot._load_active_abilities` (COMBAT) et
    `playbook.scene._seed_measured_actives` (DECISION).

    TRI-ETAT, meme discipline que `entity_triggered_ability_ids` :
      * `active_abilities is None` -> canal NON MESURE : repli sur le kit gameconfig
        `kit_active_ability_ids(visual_id)` ;
      * une LISTE (fut-elle vide) -> MESURE, et elle FAIT AUTORITE.

    ⚠ CE QUE LA MESURE EST : un SUR-ENSEMBLE du kit de configuration (cf. la docstring de
    `UnitContext.active_abilities`) -- l'`ActiveAbilityComponent` contient AUSSI l'attaque normale
    que la fabrique vient de poser et les abilities de `AddDerivedAbilities`. C'est SANS effet pour
    un predicat qui teste une ability de kit precise (`DoctrinaImperatives` n'est ni une attaque
    normale ni une derivee de trait), et il faut le re-verifier avant d'y tester autre chose.

    ⚠ NON CACHE : le champ est MUTABLE (deux entites de meme `visualId` n'ont pas le meme kit des
    qu'une greffe est en jeu)."""
    if unit_ctx is not None:
        got = getattr(unit_ctx, "active_abilities", None)
        if got is not None:
            out: list[int] = []
            for name in got:
                m = ActiveAbilityType.__members__.get(name)
                if m is not None:
                    out.append(int(m))
            return out
        if visual_id is None:
            visual_id = getattr(unit_ctx, "visual_id", None)
    return kit_active_ability_ids(visual_id)
