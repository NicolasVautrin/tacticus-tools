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

CE QUE CE MODULE PORTE EN PLUS (#1015-r1, trait `Healer`) : la voie par laquelle un TRAIT met une
ability ACTIVE dans ce meme `ActiveAbilityComponent`, et la voie par laquelle un PASSIF l'en retire.
Les deux sont des mirrors de dicts / litteraux LUS, jamais deduits -- cf.
`TRAIT_DERIVED_ACTIVE_ABILITIES` et `PASSIVE_REMOVES_ACTIVE_ABILITY` ci-dessous.
"""
from __future__ import annotations

from .active_ability_type import ActiveAbilityType


# --- LA VOIE TRAIT -> ABILITY ACTIVE (#1015-r1) --------------------------------------------------
#
# Mirror LIGNE A LIGNE du SECOND dict de
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` (celui ecrit a
# `<Trait statics>+0x08`, lu par
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetActiveAbility`).
# Le `.cctor` n'y fait QUE DEUX `Dictionary$$Add`, transcrits ici sans rien ajouter :
#
#     Add(dict, key = 0x0a, value = 0x12)   # UnitTrait.Healer   -> ActiveAbilityType.Heal
#     Add(dict, key = 0x0c, value = 0x1c)   # UnitTrait.Mechanic -> ActiveAbilityType.Repair
#
# (le PREMIER dict, `<Trait statics>+0x00` / `$$GetTriggeredAbility`, est l'autre moitie de la meme
# mecanique et vit deja dans `effects.factory.TRAIT_DERIVED_ABILITIES` -- il porte des TRIGGERED
# abilities et sert le chemin owner-effect. DEUX registres distincts, pas un doublon.)
#
# CE QUI LE MATERIALISE, aux deux moments ou une unite peut recevoir un trait :
#   * a la FABRIQUE -- `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, 3e boucle
#     (sur `config@+0xd0` = `UnitConfiguration.Traits`) : `Trait$$GetActiveAbility(trait)` -> si le
#     `Nullable` a une valeur, `Idun.Shared.Level$$.ctor(1, 0)` puis
#     `IdunBattle.Configuration.AbilityState$$.ctor(level, config@+0x74)` puis
#     `IdunBattle.Entities.Components.ActiveAbilityComponent$$Add(type, state)` ;
#   * EN BATAILLE -- `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (meme lecture,
#     meme `Level..ctor(1, 0)`), et son inverse
#     `IdunBattle.Operations.RemoveTraitOperation$$RemoveDerivedAbilities`.
#
# ⚠ Le NIVEAU de l'ability derivee est le LITTERAL `1`, pas le niveau des abilities de kit. Sans
# effet sur `18 Heal` / `28 Repair`, dont la magnitude vient de l'ARME et non d'une variable de
# config (`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` /
# `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount`) -- mais c'est LU, pas
# suppose : une derivee dont la magnitude viendrait du gameconfig la lirait au niveau 1.
#
# ⚠ SUBSTRAT : le natif lit `UnitConfiguration.Traits` (`BC.Units[].Traits`), PAS le kit gameconfig
# -- meme forme de piege que #264. Les appelants passent donc `entity_trait_names(ctx, vid)`.
TRAIT_DERIVED_ACTIVE_ABILITIES: dict[str, int] = {
    "Healer": int(ActiveAbilityType.Heal),        # UnitTrait.Healer 0x0a -> 0x12 = 18
    "Mechanic": int(ActiveAbilityType.Repair),    # UnitTrait.Mechanic 0x0c -> 0x1c = 28
}

# --- LA VOIE INVERSE : un PASSIF RETIRE l'ability derivee ------------------------------------------
#
# `IdunBattleLogic.Entities.DSLBehaviors$$RemoveActiveAbility` n'a que TROIS appelants de code dans
# le build (xrefs entrantes, exhaustives), et les trois sont des `CreateBehaviour` de passif qui
# SUBSTITUENT une specialisation a l'ability generique derivee du trait. Litteraux transcrits :
#
#   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility$$CreateBehaviour`
#       RemoveActiveAbility(Owner@+0x30, 0x12) & AddActiveAbility(Owner@+0x30, 0x48f, abilityState)
#   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HealingBalmsAbility$$CreateBehaviour`
#       AddFlag(Owner@+0x30, 0x17) + RemoveActiveAbility(Owner@+0x30, 0x12)
#                                  + AddActiveAbility(Owner@+0x30, 0x4bc, abilityState)
#   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility$$CreateBehaviour`
#       AddFlag(Owner@+0x30, 0x18) & RemoveActiveAbility(Owner@+0x30, 0x1c)
#                                  & AddActiveAbility(Owner@+0x30, 0x45f, abilityState)
#
# Sans ce second registre, les DEUX porteurs `Healer` qui SUBSTITUENT (`genesBiophagus` << Hollan >>
# via `TwistedScience`, `spaceWolfPriest` << Baldr >> via `HealingBalms`) et le porteur `Mechanic`
# qui substitue (`admecManipulus` via `GalvanicField`) se retrouveraient avec DEUX abilities de soin
# / reparation la ou le natif n'en laisse qu'UNE. MESURE LIVE deja au depot
# (`tests/engine/test_952_hunters_beyond_death_offline.py`, runner 367 board MC1_67) :
# `admecManipulus` publie `[1117 DefendTheDivineWork, 1119 Repair_GalvanicField]` -- **28 ABSENTE**.
#
# ⚠ La cle est le nom du PASSIF (`passiveAbilities` / `UnitContext.passive_abilities`), pas celui de
# l'ability posee : c'est le passif qui porte le `CreateBehaviour` ou vit le litteral.
PASSIVE_REMOVES_ACTIVE_ABILITY: dict[str, int] = {
    "TwistedScience": int(ActiveAbilityType.Heal),      # 0x12 = 18
    "HealingBalms": int(ActiveAbilityType.Heal),        # 0x12 = 18
    "GalvanicField": int(ActiveAbilityType.Repair),     # 0x1c = 28
}

# --- L'AUTRE MOITIE DE LA SUBSTITUTION : le passif AJOUTE la specialisation ------------------------
#
# `IdunBattleLogic.Entities.DSLBehaviors$$AddActiveAbility` n'a, lui aussi, que TROIS appelants de
# code dans le build (xrefs entrantes, exhaustives -- re-mesurees sur `t6dpr4k06g` par #952-r2), et
# ce sont EXACTEMENT les trois `CreateBehaviour` ci-dessus : chacun fait `Remove` PUIS `Add`, la
# substitution etant un couple, jamais un retrait seul.
#
#   `...TwistedScienceAbility$$CreateBehaviour`
#       RemoveActiveAbility(Owner@+0x30, 0x12) & AddActiveAbility(Owner@+0x30, **0x48f**, abilityState)
#   `...HealingBalmsAbility$$CreateBehaviour`
#       AddFlag(Owner@+0x30, 0x17) + RemoveActiveAbility(Owner@+0x30, 0x12)
#                                  + AddActiveAbility(Owner@+0x30, **0x4bc**, abilityState)
#   `...GalvanicFieldAbility$$CreateBehaviour`
#       AddFlag(Owner@+0x30, 0x18) & RemoveActiveAbility(Owner@+0x30, 0x1c)
#                                  & AddActiveAbility(Owner@+0x30, **0x45f**, abilityState)
#
# ⚠ **CE REGISTRE EXISTE PARCE QU'UNE CONVENTION DE NOMMAGE RATE DEUX CAS SUR TROIS**, et c'est
# MESURE, pas redoute. La face DECISION derive l'ability accordee du NOM du passif
# (`ai/state_bridge.py::_granted_abilities` : `Heal_<Passif>` resolu dans l'enum). Sur les trois
# artefacts natifs :
#     TwistedScience  0x48f = `Heal_TwistedScience`   -> `Heal_TwistedScience`  TROUVE  (1167)
#     HealingBalms    0x4bc = `HealingBalms_Heal`     -> `Heal_HealingBalms`    None
#     GalvanicField   0x45f = `Repair_GalvanicField`  -> `Heal_GalvanicField`   None
# La convention ne marche que pour celui dont l'enum est, par accident, nomme dans ce sens-la. C'est
# le CLAUDE.md mot pour mot : la VOIE ne dit pas l'enum -- seul le NOM ecrit au site, ici le
# LITTERAL du decompile, tranche. Effet mesure du trou : le repli kit d'`admecManipulus` rendait
# `[1117]` la ou le natif rend `[1117, 1119]` (mesure live #952, runner 367 board MC1_67).
#
# ⚠ AUCUNE des trois entrees n'est un mensonge de couverture : les trois ids ont une classe dans
# `runner/abilities/handler.py::ABILITY_CLASSES` (`Repair_GalvanicFieldAbility`,
# `HealingBalms_HealAbility`, `TwistedScience_HealAbility`), donc le runner sait EXECUTER ce que
# cette table fait apparaitre.
#
# ⚠ Meme cle que son jumeau ci-dessus -- le nom du PASSIF, pas celui de l'ability posee : c'est le
# passif qui porte le `CreateBehaviour` ou vit le litteral.
PASSIVE_ADDS_ACTIVE_ABILITY: dict[str, int] = {
    "TwistedScience": int(ActiveAbilityType.Heal_TwistedScience),      # 0x48f = 1167
    "HealingBalms": int(ActiveAbilityType.HealingBalms_Heal),          # 0x4bc = 1212
    "GalvanicField": int(ActiveAbilityType.Repair_GalvanicField),      # 0x45f = 1119
}


def passive_granted_active_ability_ids(passive_names) -> list[int]:
    """Ids `ActiveAbilityType` que les PASSIFS d'une unite ajoutent a son `ActiveAbilityComponent`
    -- l'`AddActiveAbility` de leur `CreateBehaviour`, la moitie AJOUT de la substitution dont
    `derived_active_ability_ids` porte deja la moitie RETRAIT.

    `passive_names` : les passifs de l'ENTITE (`UnitContext.passive_abilities`), ou le kit en repli
    -- MEME substrat et MEME tri-etat que le retrait. `None` = canal MUET -> AUCUN ajout ; c'est une
    BORNE nommee, pas une mesure.

    Ordre STABLE (celui du registre), pour que deux appels rendent la meme liste."""
    have = list(passive_names or ())
    return [aid for name, aid in PASSIVE_ADDS_ACTIVE_ABILITY.items() if name in have]


def trait_derived_active_ability(trait_name: str) -> "int | None":
    """`...StaticBattleRules.Trait$$GetActiveAbility(trait)` -- l'id `ActiveAbilityType` que ce trait
    derive, `None` quand le `TryGetValue` du natif echoue (il rend alors un `Nullable` VIDE)."""
    return TRAIT_DERIVED_ACTIVE_ABILITIES.get(trait_name)


def derived_active_ability_ids(trait_names, passive_names=None) -> list[int]:
    """Ids `ActiveAbilityType` que les TRAITS d'une unite ajoutent a son `ActiveAbilityComponent`,
    MOINS ceux qu'un de ses PASSIFS retire -- l'etat que la fabrique laisse derriere elle.

    `trait_names` : les noms de traits de l'ENTITE (`entity_trait_names(ctx, vid)`), jamais le kit
    gameconfig seul -- cf. le substrat documente sur `TRAIT_DERIVED_ACTIVE_ABILITIES`.
    `passive_names` : les passifs de l'ENTITE (`UnitContext.passive_abilities`, ou le kit en repli).
    `None` = canal MUET -> AUCUN retrait applique ; c'est une BORNE nommee, pas une mesure.

    Ordre STABLE (celui du registre), pour que deux appels rendent la meme liste."""
    removed = set()
    for p in (passive_names or ()):
        aid = PASSIVE_REMOVES_ACTIVE_ABILITY.get(p)
        if aid is not None:
            removed.add(int(aid))
    have = set(trait_names or ())
    return [int(aid) for name, aid in TRAIT_DERIVED_ACTIVE_ABILITIES.items()
            if name in have and int(aid) not in removed]


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
    passives = None
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
        passives = getattr(unit_ctx, "passive_abilities", None)
    # REPLI -- le canal n'est pas mesure, donc on reconstruit ce que la fabrique laisse derriere
    # elle, et pas seulement le kit statique. `AddActiveAbility` (#952-r2) en fait partie : sans lui
    # `admecManipulus` rendait `[1117]` la ou le natif rend `[1117, 1119]`.
    #
    # SUBSTRAT DES PASSIFS -- MEME tri-etat que le champ ci-dessus, et pour la MEME raison (#264 /
    # #931-r2) : la mesure d'entite (`UnitContext.passive_abilities`) prime, le kit gameconfig n'est
    # qu'un repli. Une greffe `catalog_inject.write_grafted_seed_bc(..., replace=True)` REMPLACE la
    # liste, donc lire le kit sur une unite greffee donnerait la mauvaise substitution.
    #
    # ⚠ BORNE NOMMEE, pas un oubli : ce repli ne porte toujours PAS les abilities DERIVEES D'UN
    # TRAIT (`derived_active_ability_ids`, ex. `18 Heal` du trait `Healer`). Elles ont leur propre
    # canal sur la face DECISION (`ai/state_bridge.py::_abilities_of`, 4e source) ; les ajouter ici
    # serait un elargissement que rien n'a mesure.
    if passives is None and visual_id:
        import gameconfig as GC
        passives = (GC.unit(visual_id) or {}).get("passiveAbilities") or ()
    ids = list(kit_active_ability_ids(visual_id))
    for aid in passive_granted_active_ability_ids(passives):
        if aid not in ids:
            ids.append(aid)
    return ids
