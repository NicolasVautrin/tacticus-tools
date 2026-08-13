"""Socle du contexte DSL runner-couple : `entities_from_state` (construit le `DslContext` natif
`AbilityEntities` depuis le `State` runner) + `LiveUnit` (vue live-by-ref d'une unite). Consomme par
TOUTES les feuilles du package `behaviours`. cf. docs/rl/dsl-effect-nodes.md,
docs/rl/dsl-live-context-substrate.md."""
from __future__ import annotations

from .... import battle_query as _bq
# Forme B : foyer UNIQUE du predicat `WeaponsComponent$$HasRangedWeapon` (accesseur
# `ctx.has_ranged_weapon`, lu par le selecteur `UnitsWithoutRangedWeapons`).
from ....services import battle_query as _sbq
from ....dsl.base import DslContext
from ...components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent, get_unit_feet)
from ....entities.traits.unit_trait import (UnitTrait, has_trait, grand_alliance_trait_name,
                                            entity_trait_names)
from ....entities.effects import effect_stat_mod_key
# #577 : substrat de `ctx.has_triggered_ability` -- foyer UNIQUE du kit declenche d'une ENTITE
# (tri-etat mesure/repli documente sur la fonction). Feuille enum, aucun cycle.
from ....entities.triggered_ability_type import entity_triggered_ability_ids
# #270-r1-r1-r3-r1 : la ligne d'import qui vivait ici (`StatPart as _SP, StatType as _ST`) est
# retiree -- #873 a DELEGUE la ventilation des parts a `HealthComponent.get_stat_part`, donc `_SP`
# n'a plus aucun lecteur dans ce module, et l'import de `_ST` etait DOUBLE (deux lignes
# consecutives, la seconde re-liant le meme nom).
from ....entities.stats import StatType as _ST
# #572-r3 : le composant fill-up des MEMBRES (`IdunBattle.Entities.Components.
# NumberOfMembersComponent`) et l'enum des parts, LUS ici pour separer `Maximum` et `Initial`.
from ....entities.stats import FillUpStatComponent as _FillUp
from ....entities.stats import StatPart
from ....utilities.tile import sort_tiles_by_utility as _stbu, runner_tile_leaf_ctx
from ...components import UnitComponent as _UC
from ...components import UnitFlagsComponent
from ...components import charged_unit_ids
from ...components import PersistentDataComponent      # #965 : `ctx.persistent_data_all`
from ...components import persistent_data as _pd
from ...components import persistent_data_list as _pdl
from ...components import previous_tiles as _pt
from ...operations.ability_reset import entity_can_have_active_ability_reset
from ....services.trait_damage_limits import group_unit_stat_part
from ...components import MachineComponent
# `unit_extensions_is_alive` (`IdunBattle.Entities.UnitExtensions$$IsAlive` : flag `Dead`, pool
# `AliveUnits`, PV) : le predicat « cette unite est-elle SUR LE BOARD », lu par `main_tile_id`.
# Choisi plutot que `unit_is_alive` (PV seuls, celui de `get_tiles`) parce que le natif teste la
# PRESENCE DU PIED, que perd aussi une unite RETIREE a PV pleins (`RemoveUnitOperation`) -- et
# parce que c'est EXACTEMENT le predicat du gate cible-morte
# (`is_dead_unit_and_not_allowed_by_ability`), donc la resolution et le gate ne peuvent pas
# diverger sur le meme cadavre.
from ...components import unit_extensions_is_alive
# Import de MODULE (forme B) : `unit_id` delegue sa branche TUILE au mirror deja porte
# `operations/active_ability.py::get_unit`. Arete classee GRATUITE par la mesure -- charger
# `engine.runner.operations.active_ability` seul dans un process FRAIS ne fait PAS atterrir ce
# module-ci dans `sys.modules`, donc hisser ne ferme aucun cycle (cf. la regle « un import DIFFERE
# est un outil a CYCLE »). Forme B et non A : une liaison de module n'est jamais gelee, donc un
# `monkeypatch.setattr` sur le foyer MORD toujours.
from ...operations import active_ability as _aa
from ...operations.damage_utility import sort_units_by_damage_utility as _subdu
from ....utilities.damage import composite_fields_from_prediction
from ...operations.attack_prediction import multi_hit_attack_prediction as _mhap


# Trait d'ALLIANCE derive de la GrandAlliance : la resolution CANONIQUE vit desormais dans
# `entities/traits/unit_trait.py` (le module d'autorite du mapping id <-> nom), parce qu'elle est
# consommee par DEUX substrats — le contexte DSL runner (ici) et le `ctx` des feuilles Tile(7)
# (`utilities/tile.py::tile_leaf_ctx`). Un 2e mapping "Imperial/Xenos/Chaos -> 26/1006/2026" aurait
# ete un fork de port. Alias conserve : il NOMME la source (cite par `abilities/ultramarines.py` et
# par les fiches de test RevitalizingMalignancy / CombatRestoratives) ; depuis #264 le substrat de
# traits de ce module passe par `entity_trait_names`, qui l'applique lui-meme.
_grand_alliance_trait = grand_alliance_trait_name


def _unit_dict(state, eid: int, entity=None) -> dict | None:
    """Dict d'unite {id, team, player, pos, alive, hp, visualId, _traits} lu du `State` runner — la forme
    `unit` que consomment les selecteurs DSL. `entity` optionnel (evite un `get_entity` redondant)."""
    e = entity if entity is not None else state.get_entity(eid)
    if e is None:
        return None
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    uc = e.get_component(UnitComponent)
    sc = e.get_component(StatsComponent)
    hc = e.get_component(HealthComponent)
    # REPLI GAMECONFIG quand l'unite n'a pas de `StatsComponent` — cas d'un CADAVRE : `_load_stats_and_
    # effects` ne pose le composant que pour les entrees de `combatSnapshot.units`, et une unite MORTE en
    # est absente ; son dict sortait donc SANS trait, alors que `decisionView` la garde et que le natif,
    # lui, teste les flags d'une entite morte (`UnitsWithFlagSelector` sur `AllDeadUnitsSelector`).
    # MESURE (#226, Foehammer) : `Count(UnitsWithTrait(AllDeadOrResurrectedUnits, Hero))` rendait 0 avec
    # un heros mort au sol -> bonus `extraDmg x deadHeroes` PERDU (live 2142 vs port 343). La source du
    # repli est EXACTEMENT celle du chemin vivant (`UnitContext.traits = gameconfig.unit(vis).traits`).
    # Le trait d'ALLIANCE (Imperial/Chaos/Xenos) fait partie du substrat : requis par le split
    # RevitalizingMalignancy (WithoutTrait Imperial / WithTrait Chaos) + l'exclusion Imperial de
    # CombatRestoratives. CONFIRME LIVE (case-220 : deathBlightbringer Chaos +6980, eldarRanger Xenos
    # +3490, adeptHospitaller Imperial +0). #264 : il vient desormais de `entity_trait_names` -- soit
    # de la MESURE live (`BC.Units[].Traits` la porte explicitement), soit, a defaut de mesure, de la
    # derivation `GrandAlliance$$GetTrait`. Ce site ne l'ajoute donc plus lui-meme : un DEUXIEME
    # ajout par-dessus une mesure re-introduirait exactement la reconstruction que #264 retire.
    # A defaut de mesure, `entity_trait_names(ctx, vis)` == l'ancien `set(ctx.traits) | {_ga}` et
    # `entity_trait_names(None, vis)` == l'ancien repli `_config_traits(vis) | {_ga}` -- bit pour bit.
    traits = set(entity_trait_names(sc.ctx if sc is not None else None,
                                    uc.visual_id if uc is not None else None))
    alive = uc.alive if uc is not None else True
    return {
        "id": eid,
        "team": oc.team if oc is not None else None,
        # EQUIPE D'ORIGINE (#963-r1) -- ce que rend `IdunBattle.Entities.EntityExtensions$$
        # GetOriginalPlayer` la ou `team` rend `GetCurrentPlayer`. Les deux ne different que sous
        # OWNER-SWAP (`IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute`, effet `1209
        # AttemptedPossession_Possessed`) : `OwnerComponent.overridden_from` porte alors le couple
        # `(team, player)` D'ORIGINE, `None` sinon (cf. `runner/components.py`).
        # LU par `entities/unit_team_selection_type.py::team_for_selection`, donc par les noeuds
        # `AreEnemies`/`AreFriends` quand leur call-site passe `UnitTeamSelectionType.ByOriginalTeam`
        # -- le seul du build etant `RedRampage_BuffAbility$$CreateTrigger`.
        "originalTeam": ((oc.overridden_from[0] if oc.overridden_from is not None else oc.team)
                         if oc is not None else None),
        "player": oc.player if oc is not None else None,
        "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
        # EMPREINTE (#R30/#91) — `IdunBattle.Entities.EntityExtensions$$GetTiles` = les tuiles des
        # PIEDS, dans l'ordre des pieds. Toujours une LISTE (jamais None) : une unite mono-tuile
        # rend `[(col,row)]`, exactement ce que le natif rend pour un seul `UnitFoot`. C'est la
        # SEULE porte d'entree des selecteurs DSL sur « quelles tuiles cette unite occupe » ; sans
        # elle un `CanAddUnit` ne voyait qu'un tiers de l'empreinte d'un Galatian pose au sol.
        "feet": get_unit_feet(state, eid),
        "alive": alive,
        "hp": hc.hp if hc is not None else (1 if alive else 0),
        # MAXIMUM de PV -- publie parce que `HealthComponent$$IsAlive` le LIT
        # (`get_CurrentMaximumValue() > 0` decide entre CADAVRE et unite SANS SANTE), et que
        # `dsl/base.py::_is_alive` ne voit que ce dict. Sans lui, un DECOY a `0/0` (mesure
        # #589-r1-r1-r2-r1-r8 : `genesSmnDecoy`) sortait de tout selecteur d'occupation alors que
        # le natif le compte. `None` = non capte -> `_is_alive` garde son verdict d'avant.
        "hpMax": hc.hp_max if hc is not None else None,
        "visualId": uc.visual_id if uc is not None else None,
        # Lien PARENT (`ParentComponent` id @+0x10, live `Unit_Parent_Id`) : lu par le selecteur
        # `Parent` (`IdunBattle.Entities.Selectors.ParentSelector$$Select` ->
        # `IdunBattle.Entities.UnitExtensions$$GetParent`). None pour toute unite du roster initial.
        "parentId": getattr(uc, "parent_id", None) if uc is not None else None,
        # `ActorStatisticsComponent @+0x70` — lu par le noeud formule `LastHitDamageTakenLastTurn`
        # (`IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate`). 0 par defaut.
        "lastHitDamageTakenLastTurn": (int(getattr(uc, "last_hit_damage_taken_last_turn", 0) or 0)
                                       if uc is not None else 0),
        # `ActorStatisticsComponent @+0x34` — lu par le noeud formule `TotalTimesAttacked`
        # (`IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate`, qui rend ce champ
        # tel quel). TOTAL de la bataille (aucun `Reset*` natif ne l'ecrit), a distinguer du
        # per-tour `@+0x38`. 0 par defaut. Consommateur porte : `BloodyFuryAbility$$GetNumExtraHits`.
        "totalTimesAttacked": (int(getattr(uc, "total_times_attacked", 0) or 0)
                               if uc is not None else 0),
        # `ActorStatisticsComponent @+0x40` (`unitsAttackedThisTurn`) -- l'`OrderedSet` d'IDS des
        # unites que CETTE unite a frappees depuis le debut de son tour, DANS L'ORDRE des coups.
        # Lu par le selecteur `IdunBattle.Entities.Selectors.UnitsAttackedThisTurnSelector$$Select`
        # (qui resout chaque id en entite et ne garde que les UNITES, `EntityExtensions$$IsUnit`).
        # ⚠ Ce champ MUTE PENDANT l'arbre (chaque maillon d'une chaine d'attaque l'allonge) -> il est
        # dans `_LIVE_KEYS`, faute de quoi `KissOfDeath` lirait la liste d'AVANT sa propre chaine,
        # donc une liste VIDE, donc aucune tuile d'atterrissage (#940). Liste, jamais un set : c'est
        # l'ORDRE que `Last(...)`/`AtIndex(..., 1)` consomment.
        "unitsAttackedThisTurn": ([int(i) for i in uc.units_attacked_this_turn]
                                  if uc is not None else []),
        # #951 -- `ActorStatisticsComponent @+0xa8` UNION `@+0xb0` : les ids que CETTE unite a
        # vaincus depuis le debut de la bataille, dans l'ordre d'inscription. Lu par le selecteur
        # `IdunBattle.Entities.Selectors.UnitsDefeatedBySelector$$Select`. MEME raison d'etre dans
        # `_LIVE_KEYS` que `unitsAttackedThisTurn` : le compteur est allonge par
        # `KillUnitOperation$$Execute+0x8b9`, donc AVANT `On(UnitDefeated)` -- et c'est justement
        # cet evenement qui fait relire la liste (TrophyTaker). Fige au seed, il rendrait `n-1`.
        "defeatedUnits": ([int(i) for i in uc.defeated_units] if uc is not None else []),
        "_traits": traits,
    }


# Champs MUTABLES d'une unite (re-lus du state a chaque acces par LiveUnit). Les autres (id/team/player/
# visualId/_traits) sont quasi-statiques -> servis depuis le snapshot seed.
#: `hpMax` en est parce qu'il MUTE (bumps de maximum, cf. `healthMax` du capteur) et qu'il decide
#: desormais d'une LIVENESS (`_is_alive`) : le figer au seed rejouerait le vice que `LiveUnit` existe
#: pour eteindre -- un predicat re-evalue apres mutation lirait un maximum perime.
#: `unitsAttackedThisTurn` en est pour la MEME raison, et c'est la plus aigue : il est allonge par
#: CHAQUE maillon de la chaine d'attaque du MEME arbre qui le relit ensuite (`KissOfDeath` #940).
#: Fige au seed, il rendrait toujours la liste d'AVANT le premier coup.
_LIVE_KEYS = frozenset({"pos", "hp", "hpMax", "alive", "feet", "unitsAttackedThisTurn",
                        "defeatedUnits"})


class LiveUnit(dict):
    """Vue LIVE d'une unite pour le contexte RUNNER (mirror natif : `AbilityEntities` tient une REF
    d'entite @+0x40, position/PV re-derives A LA LECTURE -- jamais un snapshot ; cf.
    docs/rl/dsl-live-context-substrate.md, `IdunBattle.Entities.Abilities.AbilityEntities$$get_CasterPosition` / `UnitPosition..IdunBattle.Core.UnitPosition$$.ctor`).

    Sous-classe `dict` pour rester reconnue par les `isinstance(v, dict)` du DSL (`resolve_unit`/`_units_of`/
    helpers de `dsl/base.py`) et exposer les champs STATIQUES (id/team/player/visualId/_traits) via le
    snapshot seed (compat `**`/`.items()`/iteration). Les champs MUTABLES (`_LIVE_KEYS` = pos/hp/alive) sont
    RE-LUS du `state` a chaque `get`/`[]` -> une re-eval de predicat (ex. `IsAdjacent`) APRES une mutation
    (Move/degat/mort) voit l'etat COURANT. C'est CE qui permet a UN arbre DSL de rester correct a travers une
    mutation intra-arbre (Voie A, S-chantier).

    L'override `caster_pos` (mode `AbilityEntities+0x48`, decision balayee AI) reste applique par les
    SELECTEURS (`ctx.caster_pos or _pos(...)`), PAS ici : LiveUnit rend la position BRUTE live du `state`.
    Le chemin PREDICTION (`playbook/prediction.py`) construit toujours des dicts FIGES depuis sa scene
    hypothetique -> il n'utilise PAS LiveUnit (frozen-by-design)."""

    def __init__(self, state, eid: int, entity=None):
        self._state = state
        self._eid = eid
        # Ref d'entite STABLE (les composants mutent en place) = l'homologue de AbilityEntities+0x40.
        self._entity = entity if entity is not None else state.get_entity(eid)
        super().__init__(_unit_dict(state, eid, self._entity) or {"id": eid})

    def _live(self, key):
        d = _unit_dict(self._state, self._eid, self._entity)
        return (d or {}).get(key)

    def get(self, key, default=None):
        if key in _LIVE_KEYS:
            v = self._live(key)
            return v if v is not None else default
        return super().get(key, default)

    def __getitem__(self, key):
        if key in _LIVE_KEYS:
            v = self._live(key)
            if v is None:
                raise KeyError(key)
            return v
        return super().__getitem__(key)


def _tile_entity(state, eid) -> dict | None:
    """Entite-TUILE MINIMALE : la forme sous laquelle une tuile du `boardGraph` entre dans un role de
    l'`AbilityEntities` (`caster` ou `target`). `None` si `eid` ne designe pas une tuile du board.

    UNE seule forme, parce qu'il n'y a qu'UNE forme cote natif : `AbilityEntities` porte des ENTITES,
    et une entite-tuile en est une (`IdunBattle.Entities.EntityExtensions$$GetMainTile` rend une
    entite-tuile ELLE-MEME -- domaine mixte). Cote port une tuile ne vit que dans `state.board` /
    `EffectsState` (`state.entities` ne contient que des unites/MoW), d'ou ce dict : `pos` est ce que
    lit `dsl.base._pos`, `id` ce que lisent les feuilles d'effet et `Units`/`AdjacentTiles`
    (qui acceptent tous le domaine mixte, cf. `selectors/units.Units.select`).

    `_traits` VIDE et `team`/`player`/`visualId` a `None` : une tuile n'a ni camp ni trait, et une
    valeur inventee ferait passer des gates de camp que le natif n'evalue pas. `alive: True` /
    `hp: None` : la tuile n'est ni morte ni blessee, et `hp=None` est ce que lit `_unit_dict` pour une
    entite sans `HealthComponent`."""
    board = getattr(state, "board", None)
    if eid is None or board is None:
        return None
    try:
        tid = int(eid)
    except (TypeError, ValueError):
        return None
    if tid not in getattr(board, "by_id", {}):
        return None
    c = board.coord(tid)
    return {"id": tid, "team": None, "player": None,
            "pos": {"col": int(c[0]), "row": int(c[1])},      # forme lue par `dsl.base._pos`
            "alive": True, "hp": None, "visualId": None, "_traits": set()}


def entities_from_state(state, caster_id: int, target_id: int | None = None,
                        actor_id: int | None = None, owner_id: int | None = None) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = `LiveUnit` (vues live-by-ref, pos/hp/alive re-lus du `state` a chaque acces
    -> mirror `AbilityEntities+0x40` ; permet la re-eval de predicat post-mutation, Voie A), `caster`
    (`factory+0x160`, aussi `Self@0x148`
    pour un triggered Owner==Caster), `target` (cible principale = `factory+0x178`, lu par `Target()` —
    l'entite-TUILE quand `target_id` en designe une (#287-r12, cf. le bloc de commentaire plus bas),
    None quand l'ability est sans cible ; sur un OnPreDeath = l'unite MOURANTE @0x178), `actor` (`factory+
    0x158` = ACTEUR/TUEUR de l'evenement, lu par `Actor()` — threade sur les behaviours de trigger type
    ActOfFaith accumulate ; None sinon), `board` (= `state.board`), `has_trait(unit, traitId)` (mirror
    `UnitExtensions.HasFlag`, via l'enum `UnitTrait` + le set de noms `ctx.traits`). `children=[]` =
    accumulateur de spawn FRAIS pour CE cast (mirror factory+0x148)."""
    units: list = []
    caster = None
    target = None
    actor = None
    owner = None
    for eid, e in state.entities.items():
        u = LiveUnit(state, eid, e)                   # vue LIVE (pos/hp/alive re-lus a chaque acces)
        units.append(u)
        if eid == caster_id:
            caster = u
        if target_id is not None and eid == target_id:
            target = u
        if actor_id is not None and eid == actor_id:
            actor = u
        # `owner_id` (#1002) : le slot **Owner** (`DSLSelectors+0x30` = `factory+0x148`), DISTINCT
        # du caster. Il ne se thread que quand le natif les separe reellement -- ce qui est rare :
        # pour la quasi-totalite des triggered-abilities, `BaseTriggeredAbility$$Execute` s'execute
        # sur son propre porteur, donc `Owner == Caster` et le repli documente de
        # `entities/selectors/accessors.Owner` (`ctx.owner or ctx.caster`) est EXACT.
        # Le premier call-site qui les separe est
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateBehaviour` :
        # la relique de `astraDreir` se declenche AUSSI quand un Death Rider SUMMON charge -- le
        # CASTER est alors le Death Rider et l'OWNER reste Dreir. Sans ce slot, la source de
        # l'effet `Pinned` et le referent d'`AreFriends(Owner, ...)` designeraient le mauvais
        # porteur, SILENCIEUSEMENT.
        # `None` (defaut) = comportement d'avant, INCHANGE pour les ~459 autres appelants.
        if owner_id is not None and eid == owner_id:
            owner = u

    # CASTER NON-UNITE (entite TUILE). `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    # resout son champ +0x50 (le caster) en UNE **entite**, pas forcement une unite : le DoT de tuile
    # (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour`) y passe
    # `Tiles(<occupant>)`, donc l'entite-TUILE. Cote port, une tuile ne vit que dans `EffectsState`
    # (`state.entities` ne contient que des unites/MoW) -> la boucle ci-dessus laissait `caster=None`,
    # et toute feuille qui lit `entities.caster` (ex. `AttackWithAbilityDamage`) devenait un NO-OP
    # SILENCIEUX des que le porteur etait une tuile. On materialise donc un caster MINIMAL porteur du
    # seul `id` — exactement ce dont la feuille a besoin (source du degat / attribution de mort).
    # Il n'entre PAS dans `units` : le natif non plus ne met pas la tuile dans la liste d'unites de
    # l'`AbilityEntities`, donc aucun selecteur ne peut la ramasser. INERTE quand `caster_id` designe
    # une unite (cas de tous les autres appelants).
    # `pos` : la TUILE porteuse a une position, et `IdunBattle.Entities.EntityExtensions$$GetMainTile`
    # rend une entite-tuile ELLE-MEME (domaine mixte) -> on la renseigne quand `caster_id` est un id
    # du `boardGraph`. Sans elle, tout selecteur de TUILE ancre sur ce caster (#213 : le `tiles =
    # Owner@0x148` du `Revive` de `GhostEffect`) resolvait une liste VIDE = no-op silencieux. Reste
    # `None` pour un caster non resolvable (ni unite, ni tuile du board).
    if caster is None and caster_id is not None:
        _tile = _tile_entity(state, caster_id)
        caster = ({"id": caster_id, "team": None, "player": None, "pos": None,
                   "alive": True, "hp": None, "visualId": None, "_traits": set()}
                  if _tile is None else _tile)
        caster["id"] = caster_id                 # id BRUT (un caster non-tuile garde le sien)

    # TARGET NON-UNITE (entite TUILE) -- le PENDANT du caster minimal ci-dessus, et la meme
    # DEGRADATION SILENCIEUSE quand il manque (#287-r12). Le natif ne connait qu'un role `target`, et
    # c'est une ENTITE : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` resout
    # `finalTarget = IActiveAbility.GetActualTarget(ability, caster, target)` (slot 16 ->
    # `IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` -> slot `ITargetingQuery` 6 =
    # `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`), dont la branche
    # `rules & TargetIsTile` rend `IdunBattle.Entities.EntityExtensions$$GetMainTile(target, state)` ;
    # ce `finalTarget` part en 5e argument de
    # `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`, qui ecrit
    # `AbilityEntities+0x10 = finalTarget` (offset LU dans
    # `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`, 32 arguments : `+0x00 actor ·
    # +0x08 caster · +0x10 target · +0x18 owner · +0x30 targetTile · +0x40 casterTile ·
    # +0x48 casterTiles`). Le role `target` d'une ability TILE-TARGET est donc TOUJOURS l'ENTITE-TUILE
    # -- jamais nul.
    # MESURE (`probe_287r12_role_target_tuile.py`, 100 % offline) de ce que rendait le `None` :
    #   * `1017 FragBomb`      -> `Target()` evalue 3x, **3 NULS** -> aucune attaque, aucune erreur ;
    #   * `1018 ValkyrieStrike`-> `Target()` evalue 1x, **1 NUL**  -> l'effet 1022 n'est PAS pose ;
    #   * `1026 BasiliskBarrage`, `1148 DaemonicOrdnance`, `1169 PlagueburstMortar` : 0 evaluation
    #     nulle -- les deux dernieres portent leur propre normalisation tuile (`FixedTileIds`), et
    #     1026 collapse ses tirages en Python AVANT l'arbre.
    # Il N'ENTRE PAS dans `units` (le natif non plus ne met pas la tuile dans la liste d'unites de
    # l'`AbilityEntities`) et reste `None` pour un `target_id` qui n'est ni une unite ni une tuile du
    # board : substrat non mesure, aucune tuile inventee. INERTE des que `target_id` designe une unite
    # (cas de tous les casts unit-target).
    if target is None and target_id is not None:
        target = _tile_entity(state, target_id)

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait((unit or {}).get("_traits") or set(), enum)

    # `ctx.faction_of` (mirror `UnitsFromFaction`) — FactionId gameconfig par visualId (`_faction` cache).
    # Lazy import (garde anti-circulaire, comme les Operations importees dans les feuilles).
    from ....ai.action_generators import _faction

    def _faction_of(unit):
        return _faction((unit or {}).get("visualId"))

    # `ctx.has_ranged_weapon` (mirror `IdunBattle.Entities.Components.WeaponsComponent$$
    # HasRangedWeapon(minRange = null)`) : le selecteur `UnitsWithoutRangedWeapons`
    # (`IdunBattle.Entities.Selectors.UnitsWithoutWeaponsSelector$$Select`) inline cette boucle
    # sur le `WeaponsComponent` de chaque entite. Le port passe par le kit de la BC via
    # `visualId` -- foyer UNIQUE `engine.services.battle_query.has_ranged_weapon`, partage avec la
    # face DECISION (`playbook/adjacent_unit_preference`).
    # ⚠ `visualId` ABSENT (entite-TUILE, MoW sans kit) -> `False`, ce qui GARDE l'element : c'est
    # exactement la branche `GetUnit(entity) == null` du natif, qui saute le bloc d'armes et
    # tombe sur le `Add`. Rendre `True` y jetterait des entites que le natif conserve.
    def _has_ranged_weapon(unit):
        vis = (unit or {}).get("visualId")
        return bool(_sbq.has_ranged_weapon(vis)) if vis else False

    # `ctx.get_stat` (mirror `IdunBattle.Entities.UnitExtensions$$GetStat`) : le noeud `StatAmount(sel, statType,
    # variant)` lit la VRAIE stat de l'unite (Attack/Health/…) via son `StatsComponent.ctx.stats` — sans
    # ce wiring il degraderait vers Health (hp) via `_default_get_stat`. `variant` = `StatPart` natif
    # (0=Current, 2=Maximum, 3=Initial) ; `level` ignore offline (stats non scalees par niveau tierce).
    # id de l'unite DSL -> entite ECS -> `UnitStats.get_stat(statType, part)`.
    def _get_stat(unit, stat_type, variant=0, level=None):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        # #60 : stat 20 (NUMBER_OF_MEMBERS) = branche DEDIEE du GetStat natif (handler jumptable 0x14
        # IdunBattle.Entities.UnitExtensions$$GetStat+0x859 : NumberOfMembersComponent fill-up {+0x10=nrOfMembers, +0x18=restants}, PAS un
        # StatComponent — `IdunBattle.Entities.UnitExtensions$$GetStatComponent` n'a pas de case 0x14). Offline : parts derivees
        # de l'etat PV via `group_unit_stat_part` (lu par `SwarmAbility` StatAmount(Self,20,3/4)).
        # HEALTH = l'AUTRE stat « fill-up » du natif (comme NUMBER_OF_MEMBERS ci-dessous) :
        # `IdunBattle.Entities.UnitExtensions$$GetStat` route la PV sur un `FillUpStatComponent`
        # (+0x10 = maximum courant, +0x18 = valeur courante) et delegue a
        # `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`, PAS sur le `StatComponent`
        # generique. Cote port la PV vit dans le `HealthComponent` (hp / hp_max) ; passer par
        # `UnitStats.get_stat` rendait le composant HEALTH generique, dont l'`initial` est la PV
        # COURANTE captee -> `Maximum` valait la PV COURANTE des que l'unite etait blessee.
        # MESURE : DoT de tuile sur darkaTerminator a 473240/500000 PV -> base offline 94648
        # (= 20 % de 473240) contre 100000 attendu (= 20 % de 500000), tick natif 25000.
        # Parts (mirror `FillUpStatComponent$$GetStatPart`) : 0=Current, 1=CurrentPct, 2=Maximum,
        # 3=Initial, 4=Missing.
        #
        # #572-r1 -- LA VENTILATION DES PARTS EST DELEGUEE, ELLE N'EST PLUS REECRITE ICI.
        # `HealthComponent.get_stat_part` EST le mirror de `FillUpStatComponent$$GetStatPart`, et
        # depuis que le composant porte sa `ValueModification` de maximum (+0x28), les parts
        # `Maximum` (2) et `Initial` (3) **ne coincident plus** : le natif rend
        # `get_CurrentMaximumValue()` pour la premiere et le champ brut `+0x10` pour la seconde.
        # Les confondre -- ce que faisait le `if p in (2, 3): return mx` d'ici -- rendait donc
        # FAUSSE l'une des deux des qu'un stat-mod HEALTH est pose, et LAQUELLE dependait de ce que
        # `hp_max` designait. Une seule ventilation, dans le composant.
        if int(stat_type) == int(_ST.HEALTH):
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is not None and hc.hp is not None and hc.hp_max is not None:
                return hc.get_stat_part(int(variant))
            return us.get_stat(int(stat_type), int(variant)) if us is not None else 0
        if int(stat_type) == int(_ST.NUMBER_OF_MEMBERS):
            n = int(getattr(sc.ctx, "number_of_members", 1)) if sc is not None else 1
            # #572-r3 : le MAXIMUM (part 2) est `get_CurrentMaximumValue()` du
            # `IdunBattle.Entities.Components.NumberOfMembersComponent`, PAS le champ `+0x10`.
            # Depuis #572-r3 ce composant existe cote port (`UnitStats.components[20]` seede en
            # `FillUpStatComponent`) : on le LIT au lieu de re-deriver, sinon une modification de
            # maximum posee par `stat_ops` resterait invisible de ce chemin-ci -- exactement le
            # « deux reservoirs, un seul bouge » que #572-r1 a corrige pour la sante.
            _c = us.components.get(int(_ST.NUMBER_OF_MEMBERS)) if us is not None else None
            mx = _c.get_current_maximum_value() if isinstance(_c, _FillUp) else None
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None or hc.hp_max is None:
                if int(variant) == int(StatPart.MAXIMUM) and mx is not None:
                    return int(mx)
                return n if int(variant) in (0, 2, 3) else 0
            return group_unit_stat_part(int(variant), int(hc.hp_max), n, int(hc.hp),
                                        member_maximum=mx)
        return us.get_stat(int(stat_type), int(variant)) if us is not None else 0

    # `ctx.player_turns_started` (mirror `IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula
    # $$Calculate`) : `TurnComponent.GetAmountOfTurnsStartedByPlayer(turn, GetOriginalOwnerEntityId(
    # unit))` = le dict PAR JOUEUR `TurnComponent+0x38`, cote port `State.turn_counts`. Lu par le
    # noeud `PlayerTurnsStarted` (cycle a 3 temps de `SereneUnifierAbility`). L'owner ORIGINAL du
    # natif est approxime par l'owner COURANT (`OwnerComponent.player`) -- approximation nommee dans
    # la docstring du noeud. Unite sans `OwnerComponent` -> 0.
    def _player_turns_started(unit):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        if oc is None or oc.player is None:
            return 0
        return int(state.turn_counts.get(int(oc.player), 0) or 0)

    # `ctx.get_ability_level` (mirror du niveau d'ability lu par `ConfigVar` sur une unite TIERCE) : le noeud
    # `ConfigVarForEntity(RighteousRepugnance, chance, killer)` lit le niveau PASSIF/ACTIF capte de l'unite
    # (`StatsComponent.ctx.passive_ability_level`/`active_ability_level`, seede depuis unitConfig).
    def _get_ability_level(unit, slot="passive"):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None
        return getattr(sc.ctx, "active_ability_level" if slot == "active" else "passive_ability_level", None)

    # `ctx.tile_has_effect` (predicat tuile de `IdunBattleLogic.Entities.DSLSelectors$$UnitsOnTilesWithEffect`, #217) : la TUILE
    # (entite ECS tile-id) porte-t-elle un effet ACTIF (non consomme) du type ? Meme cle tile-id de
    # `state.effects` que la pose `AddEffectOperation` (case-35 : la glace vit dans by_unit[tile_id]).
    def _tile_has_effect(tile_id, effect_type):
        return (state.effects is not None
                and state.effects.has_effect(int(tile_id), effect_type=int(effect_type)))

    # `ctx.has_effect` (`IdunBattleLogic.Entities.DSLFactory$$HasEffect(unit, effectType, activeOnly,
    # sourceFlags)` -> `IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` ->
    # `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`) : l'unite porte-t-elle un effet du type ?
    # (source-flag 6 = owned|incoming -> offline on ne distingue pas la source, toutes les instances
    # portees comptent). Meme cle `by_unit` que la pose `AddEffectOperation`. Sans `state.effects` ->
    # False (degradation fidele).
    # `active_only` (#100) = le 4e argument NATIF : `IsOwnerOfEffect` skippe toute entree dont
    # `EffectComponent+0x5c` (= IsActive) est nul. Cote port, l'equivalent est l'`ActiveCondition`
    # (`BaseEffect.is_active(unit_state)`) — indispensable pour
    # `AnvilShield_BlockChanceBelowHealthCap` (1200), PRESENT en permanence sur Arjac mais ACTIF
    # seulement sous 35 % PV. `unit_state` = `{hp, max_hp}` lu du `HealthComponent` du porteur.
    def _has_effect(unit, effect_type, source_flag=6, min_level=0, active_only=True):
        if state.effects is None:
            return False
        uid = (unit or {}).get("id")
        if uid is None:
            return False
        ustate = None
        for e in state.effects.by_unit.get(int(uid), []):
            if e.consumed or e.expired or e.effect_type != int(effect_type):
                continue
            if int(min_level or 0) > 0 and int(e.level or 0) < int(min_level):
                continue
            if active_only:
                if ustate is None:
                    _ent = state.get_entity(int(uid))
                    _hc = _ent.get_component(HealthComponent) if _ent is not None else None
                    ustate = ({"hp": _hc.hp, "max_hp": _hc.hp_max} if _hc is not None else {})
                if not e.is_active(ustate):
                    continue
            return True
        return False

    # `ctx.effects_from_source` (`IdunBattleLogic.Entities.DSLSelectors$$EffectsFromUnitSource`, #MasterAnnihilator) : les INSTANCES
    # d'effet du type dont le `EffectComponent.SourceUnit` == `source_unit`. Balaye `state.effects.by_unit`
    # (cle = le PORTEUR) et ne garde que les instances ACTIVES (non consommees) de la bonne source.
    def _effects_from_source(source_unit, effect_type):
        if state.effects is None:
            return []
        sid = (source_unit or {}).get("id")
        if sid is None:
            return []
        out = []
        for uid, effs in state.effects.by_unit.items():
            for e in effs:
                if e.consumed or e.effect_type != int(effect_type) or e.source is None:
                    continue
                if int(e.source) == int(sid):
                    out.append({"effect_type": int(effect_type), "source": int(sid), "owner_id": int(uid)})
        return out

    # `ctx.effects_of_units` -- l'AUTRE surcharge de la meme famille de selecteurs d'effet :
    # `IdunBattleLogic.Entities.DSLSelectors$$EffectFromOwner(effectTarget, effectType)`, celle a DEUX
    # arguments, dont `effectTarget` est un SELECTEUR D'UNITES (et non l'owner implicite). Rend les
    # INSTANCES portees, avec leur `level` -- c'est ce champ (`EffectComponent+0x68`) que somme
    # `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate`.
    # MEME cle `by_unit` et MEME filtre `consumed` que `_effects_from_source` juste au-dessus ; PAS de
    # filtre `is_active` : le natif de `EffectLevelFormula` enumere le selecteur SANS gate d'activite
    # (contraste `HasEffect`, dont le 4e argument `activeOnly` est explicite au call-site).
    def _effects_of_units(unit, effect_type):
        if state.effects is None:
            return []
        uid = (unit or {}).get("id")
        if uid is None:
            return []
        out = []
        for e in state.effects.by_unit.get(int(uid), []):
            if e.consumed or e.expired or e.effect_type != int(effect_type):
                continue
            out.append({"effect_type": int(effect_type), "owner_id": int(uid),
                        "level": int(getattr(e, "level", 0) or 0)})
        return out

    # `ctx.current_player_machine_position` (predicat `IsPositionMachineForCurrentPlayer`, mirror
    # `IsPositionMachineForPlayerTrigger IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger`).
    # ⚠ RESIDU NOMME (#302 tranche 3) : le natif ne lit PAS une machine deployee, il lit
    # `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer` = la
    # `MachineOfWarPosition` du GROUPE DE SPAWN du joueur (`SpawnPointSetConfiguration.
    # GroupForPlayer(teamIndex, playerNr).<+0x14>`), une propriete du PLATEAU disponible qu'une MoW
    # soit la ou non -- cf. `engine.services.machine_of_war_position`, ou la cascade est portee, et
    # `AiDecisionContext.machine_of_war_position`, qui la cable cote DECISION.
    # Ce qui suit est donc un PROXY : le slot (`MachineComponent.Position` @0x78) de la MoW dont
    # l'owner-PLAYER est le joueur courant. Il est EXACT quand une MoW est deployee (elle l'a ete
    # sur le slot de son groupe) et rend None sinon, la ou le natif repond toujours. Le combler
    # demande de porter les `SpawnPointGroups` de la BC jusqu'au `State` -- hors perimetre #302-3,
    # qui n'a valide que la face DECISION.
    mow_pos = None
    if state.current_player_id is not None:
        for _e, _mc in state.with_component(MachineComponent):
            _oc = _e.get_component(OwnerComponent)
            if _oc is not None and _oc.player == state.current_player_id:
                mow_pos = _mc.slot
                break

    # `ctx.has_negative_modifier` (`IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`) :
    # l'unite porte-t-elle >=1 modification per-source NEGATIVE sur l'un des StatTypes du filtre ? Mirror
    # deja en place cote stats (`UnitStats.has_negative_modifier`, foyer du gate ConquerorImperative) —
    # ici on l'expose au DSL (predicat de ciblage PlagueburstMortar). Stats absentes -> False.
    def _has_negative_modifier(unit, stat_types):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        return bool(us.has_negative_modifier(stat_types)) if us is not None else False

    # `ctx.negative_stat_modification` (`IdunBattle.Entities.Formulas.
    # NegativeStatModificationFormula$$Calculate`) : le PENDANT QUANTITATIF du precedent -- somme des
    # valeurs ABSOLUES des modifications per-source < 0 de CETTE stat. Meme substrat
    # (`UnitStats`, dictionnaire per-source), donc meme resolution d'unite ; stats absentes -> 0.
    def _negative_stat_modification(unit, stat_type):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        return int(us.negative_stat_modification(stat_type)) if us is not None else 0

    # `ctx.is_in_team_aura` (`IdunBattle.Entities.Triggers.IsInAuraRangeTrigger$$ShouldTrigger` ->
    # slot `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange`) : `unit` est-elle dans la portee
    # d'une aura `effect_type` portee par une unite de l'EQUIPE de `team_reference` ?
    # Le canal etait un RESIDU ASSUME (accesseur jamais fourni -> le noeud `IsInTeamAura` rendait
    # toujours False, donc la branche AURA de `PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`
    # etait morte). Il est desormais MATERIALISE : `BattleQuery$$GetInRangeAuraAmount` est entierement
    # lisible au decompile (aucun slot opaque) et son etage de portee vit dans
    # `entities/effects/aura.py`, partage avec la formule `AuraEffectRange`. La correction est
    # strictement dans le sens de la FIDELITE (le port refusait des cibles que le natif accepte).
    def _is_in_team_aura(unit, effect_type, team_reference):
        team = (team_reference or {}).get("team")
        if team is None:
            return False                       # `GetCurrentTeamId(ref)` indisponible -> pas d'aura
        return _bq.is_in_team_aura_range(int(effect_type), int(team), unit, units,
                                         _has_trait, _turns_started)

    def _turns_started(unit):
        """`StatAmount(Owner, 0xc = TurnsStarted)` -- l'entree de `GetCurrentRange` d'un `IAuraEffect`."""
        return int(_get_stat(unit, int(_ST.TURNS_STARTED), 0, None) or 0)

    # `ctx.stat_modifier_amount` (`CurrentStatModifierAmountFormula`, gate d'idempotence de
    # `AddOrUpdateStaticStatModifierEffect`) : contribution COURANTE, sur `stat_type`, de l'effet
    # `effect_type` porte par l'unite = la `ValueModification` keyee par SA cle d'instance
    # (`effect_stat_mod_key` : cle de pose, sinon cle DERIVEE du seed — meme invariant « une seule
    # entree per_source par entite-effet » que le natif, #118). 0 si l'effet n'est pas porte ou n'a
    # pose aucune stat-modification.
    def _stat_modifier_amount(unit, effect_type, stat_type):
        uid = (unit or {}).get("id")
        if uid is None or state.effects is None:
            return 0
        e = state.get_entity(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        comp = us.components.get(int(stat_type)) if us is not None else None
        if comp is None:
            return 0
        total = 0
        for eff in state.effects.by_unit.get(int(uid), []):
            if eff.consumed or eff.effect_type != int(effect_type):
                continue
            key = effect_stat_mod_key(eff)
            if key is None:
                continue
            total += int(comp.modification.get_modification_from_entity(key) or 0)
        return total

    # `ctx.has_unit_flag` (`IdunBattle.Entities.Components.UnitFlagsComponent$$Has`) : l'unite porte-t-elle
    # le drapeau ? Lu par `AllDeadOrResurrectedUnits` (flag 0xe = RESSUSCITE, pose par
    # `ResurrectUnitOperation` cote port `UnitFlagsComponent.AMBUSH_CONSUMED`). Unite sans composant de
    # flags -> False.
    # `ctx.has_taken_damage_of_profile_this_turn` (`IdunBattle.Entities.UnitExtensions$$
    # HasTakenDamageOfDamageProfileThisTurn`, dont le corps relu est un `ContainsKey` sur le dict
    # `ActorStatisticsComponent+0x80` = `receivedDamageThisTurn`) : PRESENCE de la cle, pas un compte.
    # C'est le MEME dict que lisent `units_that_taken_damage_this_turn` (weaver_of_fate) et
    # `has_taken_damage_of_damage_profile_this_turn_amount_of_times` (reality_unbound) -- une seule
    # source cote port (`UnitComponent.received_damage_this_turn`, alimente par `damage.py`).
    # Composant absent -> False (degradation fidele).
    def _has_taken_damage_of_profile_this_turn(unit, profile_id):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        uc = e.get_component(_UC) if e is not None else None
        if uc is None:
            return False
        return int(profile_id) in (uc.received_damage_this_turn or {})

    def _has_unit_flag(unit, flag):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        return bool(fl.has(int(flag))) if fl is not None else False

    # `ctx.can_have_active_ability_reset` (`IdunBattle.Core.Services.BattleQuery$$
    # EntityCanHaveActiveAbilityReset(unit, false)`) : l'unite a-t-elle une ability active RESETTABLE
    # (charge consommee hors cooldown, ou en cooldown sous conditions de tour) ? C'est le predicat du
    # selecteur `UnitsThatCanHaveActiveAbilityReset` (InspiredToGreatness). None = INCONNU (canal
    # `ActiveAbilitiesComponent` absent) -> propage, jamais rabattu sur False.
    # `ctx.has_triggered_ability` (`IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(unit,
    # type)`, dont le corps relu est `GetComponent<TriggeredAbilityComponent>()?.TryGetAbility(type)`)
    # : l'unite PORTE-t-elle cette triggered-ability ? Lu par le predicat
    # `IdunBattle.Entities.Triggers.ActortHasTriggeredAbilityTrigger$$ShouldTrigger` (#577).
    # Substrat = `entity_triggered_ability_ids` -- le FOYER UNIQUE du kit declenche, le MEME que lit
    # le gate `GetAbilityState` de `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$
    # TriggerAbility` (`behaviours/lifecycle.py::_unit_has_triggered_ability`). Composant absent ->
    # repli kit gameconfig, deja porte par le foyer (tri-etat documente la-bas).
    def _has_triggered_ability(unit, triggered_ability_type):
        uid = (unit or {}).get("id")
        e = state.get_entity(int(uid)) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        return int(triggered_ability_type) in set(entity_triggered_ability_ids(ctx))

    def _can_have_active_ability_reset(unit):
        uid = (unit or {}).get("id")
        if uid is None:
            return None
        return entity_can_have_active_ability_reset(state, int(uid), False)

    # `ctx.units_damaged_this_phase` : mirror de la `List<BEntityId>` @`ActorStatisticsComponent + 0x48`
    # de l'ATTAQUANT (`IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select` prend ce
    # composant sur chaque attaquant selectionne et resout les ENTITES). Cote port la liste vit sur le
    # `UnitComponent` de l'attaquant (`damaged_units_this_phase`) ; on rend les vues `LiveUnit` deja
    # construites (meme identite d'objet que `ctx.units`, donc les predicats aval lisent le state LIVE).
    _by_id = {u.get("id"): u for u in units}

    def _units_damaged_this_phase(unit):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        uc = e.get_component(_UC) if e is not None else None
        if uc is None:
            return []
        return [_by_id[t] for t in uc.damaged_units_this_phase if t in _by_id]

    # `ctx.valid_normal_attack_targets` (`IdunBattle.Entities.Selectors.
    # ValidNormalAttackTargetsSelector$$Select`) : les cibles LEGALES de l'attaque NORMALE de
    # `caster_unit` depuis ses tuiles. DELEGUE a `runner/abilities/targeting.py` -- la cascade de
    # ciblage n'a QU'UN port, et c'est celui-la (surtout pas un 2e filtre ici). Rend les vues
    # `LiveUnit` deja construites (meme identite d'objet que `ctx.units`), dans l'ordre
    # d'enumeration de `state.entities`.
    def _valid_normal_attack_targets(caster_unit, range_override=None):
        """`range_override` = le bloc `if (rangeSel@+0x28 != null)` du selecteur natif, arme par le
        seul call-site qui le pose (`UnwaveringSentinel_CounterAttackEffect$$
        GetCounterAttackCondition`, #946). `None` = comportement d'avant, inchange."""
        from ..targeting import valid_normal_attack_targets as _vnat
        cid = (caster_unit or {}).get("id")
        if cid is None:
            return []
        return [_by_id[t] for t in _vnat(state, int(cid), range_override=range_override)
                if t in _by_id]

    # `ctx.has_any_valid_target` (slot `IBattleQuery.<64 = 0x40> HasValidTargets(unit, position,
    # abilityType)`, lu PAR UNITE par `IdunBattle.Entities.Selectors.
    # UnitsWithAnyValidTargetSelector$$Select`) : DELEGUE au mirror generique de la cascade
    # (`abilities/targeting.has_valid_targets`), dont `valid_normal_attack_targets` ci-dessus est le
    # cas particulier « ability = l'attaque normale du caster ». TRI-ETAT conserve TEL QUEL : `None`
    # = masque non RE-lu, et le noeud DOIT le voir pour ecarter en le disant plutot que d'inventer.
    def _has_any_valid_target(unit, ability_type):
        from ..targeting import has_valid_targets as _hvt
        uid = (unit or {}).get("id")
        if uid is None or ability_type is None:
            return None
        return _hvt(state, int(uid), int(ability_type))

    # `ctx.normal_repair_type` (`IdunBattle.Entities.UnitExtensions$$GetRepairType`, lu par le noeud
    # VALEUR `UnitNormalRepairType`) : DELEGUE a l'unique derivation portee.
    def _normal_repair_type(unit):
        from ..targeting import normal_repair_type_for as _nrt
        uid = (unit or {}).get("id")
        return None if uid is None else _nrt(state, int(uid))

    # `ctx.normal_attack_type` (`IdunBattle.Entities.UnitExtensions$$GetNormalAttackType`, lu PAR
    # UNITE par `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector$$Select`) : DELEGUE a
    # l'unique derivation portee, exactement comme `_normal_repair_type` ci-dessus.
    def _normal_attack_type(unit):
        from ..targeting import normal_attack_type_for as _nat
        uid = (unit or {}).get("id")
        return None if uid is None else _nat(state, int(uid))

    # `ctx.entity_can_be_repaired` (slot 0x13 d'`IAttackQuery`, lu par
    # `IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select`) : DELEGUE a l'unique mirror du
    # predicat (`abilities/attack_query.entity_can_be_repaired`) avec `caster_id = None` -- la
    # surcharge a TROIS arguments EST la 4-args a caster nul (relue au decompile : le seul disjunct
    # qui disparait est `caster != null && HasFlag(caster, 0x18)`). Surtout pas un 2e port du gate.
    def _entity_can_be_repaired(unit, scope=0, remove_effects=True):
        from ..attack_query import entity_can_be_repaired as _ecbr
        uid = (unit or {}).get("id")
        if uid is None:
            return False
        return bool(_ecbr(state, None, int(uid), scope=int(scope),
                          remove_effects=bool(remove_effects)))

    # `ctx.entity_can_be_healed` (slot 0x11 d'`IAttackQuery`, lu par
    # `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select`) : DELEGUE a l'unique mirror du
    # predicat (`abilities/attack_query.entity_can_be_healed`). Contrairement au jumeau REPAIRABLE
    # ci-dessus, le selecteur HEALABLE appelle la surcharge a QUATRE arguments -- il resout d'abord son
    # PROPRE selecteur de caster (`HealableUnitsSelector+0x18`, `Caster` sur le call-site lu
    # `RitesOfRestorationAbility$$GetHealTargets`) et le passe en tete. Le caster est donc un ARGUMENT,
    # pas un `None` code en dur : `HasFlag(caster, CanHealFullHealthUnits)` est le disjunct qui
    # depend de lui.
    def _entity_can_be_healed(caster_unit, target_unit, scope=0, remove_effects=True):
        from ..attack_query import entity_can_be_healed as _ecbh
        tid = (target_unit or {}).get("id")
        if tid is None:
            return False
        cid = (caster_unit or {}).get("id") if isinstance(caster_unit, dict) else None
        return bool(_ecbh(state, None if cid is None else int(cid), int(tid),
                          scope=int(scope), remove_effects=bool(remove_effects)))

    # `ctx.pick_randomly` (`IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select`) : le noeud
    # DSL `PickRandomly` n'a pas acces au PRNG de bataille -> il passe par cet accesseur, qui delegue
    # au foyer UNIQUE de la boucle native (`abilities/loki/splash._pick_randomly_n`, loi #130/#215 :
    # `min(len(pool), amount)` tirages, y compris sur un pool de 1). L'ORDRE de `items` est celui du
    # selecteur source -- on ne le retrie pas ici (R28-1).
    def _pick_randomly(items, amount, allow_repeat=False, max_repeats=0x7FFFFFFF):
        from ..loki.splash import _pick_randomly_n
        return _pick_randomly_n(state, list(items), int(amount),
                                allow_repeat=bool(allow_repeat), max_repeats=int(max_repeats))

    # `ctx.sort_tiles_by_utility` (`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select`)
    # : le noeud DSL `SortTilesByUtility` n'a pas acces au `State` (les feuilles d'utilite lisent
    # l'ECS entier) -> il passe par cet accesseur, qui delegue au foyer UNIQUE
    # `engine/utilities/tile.py::sort_tiles_by_utility` -- le MEME que consomment les call-sites qui
    # collapsent `First(SortTilesByUtility(...), 1)` (`first_tile_by_utility`). ZERO tirage.
    # `leaf_ctx` = `runner_tile_leaf_ctx(state, unit_id, parent_id)`, le port de `dc.units`/`dc.owner`
    # que le natif met dans le `UtilityMovementCase` de chaque feuille (#165).
    # `utility_definition` (#120bis-spawn) = la definition BATIE A LA MAIN par le call-site quand il
    # n'emprunte PAS la surcharge int de `SortTilesByUtility` -- le foyer l'accepte deja (#353-r1,
    # `RammingSpeedAbility$$GetTileToMoveTo`), mais cet accesseur ne savait pas la transporter, donc
    # aucun noeud DSL ne pouvait l'exprimer. `None` (defaut) = comportement INCHANGE : la definition
    # est derivee du scalaire `utility_type`, comme pour tous les appelants existants.
    def _sort_tiles_by_utility(tiles, unit_id, utility_type, parent_id=None,
                               utility_definition=None):
        uid = None if unit_id is None else int(unit_id)
        pid = None if parent_id is None else int(parent_id)
        return _stbu(state, list(tiles), None, uid, int(utility_type), pid, utility_definition,
                     runner_tile_leaf_ctx(state, uid, pid))

    def _sort_units_by_damage_utility(candidate_ids, dmin, dmax, owner_id=None, hits=1,
                                      ability_type=None):
        """`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` -- l'accesseur
        que lit le noeud DSL `selectors.units.SortUnitsByDamageUtility`. DELEGUE au foyer deja
        porte (`runner/operations/damage_utility.sort_units_by_damage_utility`), jamais une seconde
        implementation. `is_melee=None` : le foyer le derive lui-meme du couple (attaquant, cible)
        par `GetAttackWeaponForDefaultNormalAttack`, comme le natif. #889-r5."""
        return _subdu(state, [int(c) for c in candidate_ids], int(dmin), int(dmax),
                      owner_id=None if owner_id is None else int(owner_id), hits=int(hits or 1),
                      ability_type=None if ability_type is None else int(ability_type))

    def _attack_prediction(attacker_id, defender_id, amount, hits, damage_profile=None,
                           is_melee=False):
        """`IBattleQuery` slot **40** `GetMultiHitAttackPrediction(attacker, defender,
        attackerPosition, ability, damage, damageProfile, hits)` -- l'accesseur que lit le noeud
        VALEUR `entities.formulas.DamagePredictionFormula`. DELEGUE au foyer deja porte
        (`runner/operations/attack_prediction.multi_hit_attack_prediction`), jamais une seconde
        implementation : c'est le MEME que consomme `SortUnitsByDamageUtilitySelector` (#927).

        ⚠ Ici `damageProfile` n'est PAS nul (contraste `SortUnitsByDamageUtility`, dont TOUS les
        call-sites passent `null`) : `DamagePredictionFormula$$Calculate` transmet
        `Nullable<DamageProfileType>(this+0x50)`, que ses appelants remplissent avec
        `GetDamageProfileOrDefault(...)`. Le PERCAGE suit donc le profil, au lieu d'etre force a 0
        (`DamagePrediction$$GetAttackPiercingDamageRatio` : `if (damageProfile == null) return 0`).

        `is_melee` est derive de l'`attackRangeType` de la config d'ability par l'APPELANT du noeud ;
        `is_normal_attack = False` (le noeud `+0x38 ability` est non nul sur les deux call-sites
        portes, donc le natif ne retombe PAS sur `GetNormalAttackType`).
        Rend le dict de composite (`healthDmgMin/Max`, `kill`, `killSure`) ou `None`."""
        if attacker_id is None or defender_id is None:
            return None
        prof = None if damage_profile is None else str(damage_profile)
        pierce = 0
        if prof is not None:
            import gameconfig as _GC
            pierce = int(((_GC.damage_profile(prof) or {}).get("PiercingRatio")) or 0)
        dp = _mhap(state, int(attacker_id), int(defender_id), int(amount), max(1, int(hits)),
                   prof, pierce, is_melee=bool(is_melee), ability_type=None,
                   is_normal_attack=False)
        if dp is None:
            return None
        return composite_fields_from_prediction(dp)

    # `ctx.charged_units` (`UnitComponent + 0x190`, cf. `update_charging`) : ids que l'unite a CHARGES
    # pendant son activation courante. Moitie runtime du predicat
    # `IdunBattle.Core.Services.BattleQuery$$IsCharging` (l'autre moitie = l'adjacence). Vide si le
    # composant manque (degradation fidele : personne n'a charge).
    def _charged_units(unit):
        uid = (unit or {}).get("id")
        return charged_unit_ids(state, int(uid)) if uid is not None else set()

    # `ctx.persistent_data_list` (`IdunBattle.Entities.Components.PersistentDataComponent$$
    # TryGetPersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`) : le `List<T>` range sous
    # la cle composite `(GetPersistentDataId(abilityOrEffect), dataKey)` du sac persistant de l'unite.
    # Cle absente / composant absent -> `[]`, exactement ce que fait le natif (les trois consommateurs
    # -- `AddToPersistentDataListBehaviour$$Execute`, `IsInPersistentDataListTrigger$$ShouldTrigger`,
    # `EntitiesFromPersistentDataListSelector$$Select` -- font tous `?? new List<T>()`).
    def _persistent_data_list(unit, key):
        uid = (unit or {}).get("id")
        return _pdl(state.get_entity(int(uid)) if uid is not None else None, key)

    def _persistent_data(unit, key):
        """`ctx.persistent_data` -- le pendant SCALAIRE de `_persistent_data_list`, sur le MEME
        `Dictionary` @+0x10 et la MEME cle composite. `None` = cle absente (la formule
        `GetPersistentData` le rend en 0, comme l'`out` par defaut du natif)."""
        uid = (unit or {}).get("id")
        return _pd(state.get_entity(int(uid)) if uid is not None else None, key)

    def _persistent_data_all(unit, ability_or_effect, excluded_keys=None):
        """`ctx.persistent_data_all` -- `GetAllPersistentDataCombined$$SumAbilityData` sur le MEME
        `Dictionary` @+0x10. Composant absent -> 0 (le natif rend 0 quand son `TryGetValue` echoue)."""
        uid = (unit or {}).get("id")
        e = state.get_entity(int(uid)) if uid is not None else None
        c = e.get_component(PersistentDataComponent) if e is not None else None
        if c is None:
            return 0
        return c.sum_ability_data(ability_or_effect, excluded_keys)

    def _previous_tiles(unit):
        """`ctx.previous_tiles` -- `PositionComponent+0x88` deplie en coordonnees, ce que rend
        `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select`. `[]` = `Nullable` VIDE."""
        uid = (unit or {}).get("id")
        return _pt(state.get_entity(int(uid)) if uid is not None else None)

    # `ctx.entity_by_id` (`IBattleState.GetEntity(id)`, slot 0x29) : la resolution id -> unite que
    # fait `EntitiesFromPersistentDataListSelector$$Select`. On la sert depuis `units` (deja
    # materialise ci-dessus), donc dans la MEME representation que tous les autres selecteurs.
    # Un id absent rend None -> le selecteur le jette, comme le natif.
    _by_id = {int(u["id"]): u for u in units if (u or {}).get("id") is not None}

    def _entity_by_id(eid):
        try:
            return _by_id.get(int(eid))
        except (TypeError, ValueError):
            return None

    return DslContext(units=units, caster=caster, target=target, actor=actor, owner=owner,
                      board=state.board,
                      # `TurnComponent.CurrentPlayer` -> noeud `IsTurnOf` (#85). Le runner le tient
                      # dans `state.current_player_id` (pose par `ChangeTurnOperation.execute`).
                      current_player_id=getattr(state, "current_player_id", None),
                      player_turns_started=_player_turns_started,
                      units_damaged_this_phase=_units_damaged_this_phase,
                      charged_units=_charged_units,
                      valid_normal_attack_targets=_valid_normal_attack_targets,
                      has_any_valid_target=_has_any_valid_target,
                      normal_repair_type=_normal_repair_type,
                      normal_attack_type=_normal_attack_type,
                      unknown_ability_types=set(),
                      persistent_data_list=_persistent_data_list,
                      persistent_data=_persistent_data,
                      persistent_data_all=_persistent_data_all,
                      previous_tiles=_previous_tiles,
                      entity_by_id=_entity_by_id,
                      has_trait=_has_trait, faction_of=_faction_of, get_stat=_get_stat,
                      has_ranged_weapon=_has_ranged_weapon,
                      has_unit_flag=_has_unit_flag,
                      has_taken_damage_of_profile_this_turn=_has_taken_damage_of_profile_this_turn,
                      get_ability_level=_get_ability_level, tile_has_effect=_tile_has_effect,
                      has_effect=_has_effect, effects_from_source=_effects_from_source,
        effects_of_units=_effects_of_units, children=[],
                      has_negative_modifier=_has_negative_modifier,
                      negative_stat_modification=_negative_stat_modification,
                      is_in_team_aura=_is_in_team_aura,
                      has_triggered_ability=_has_triggered_ability,
                      can_have_active_ability_reset=_can_have_active_ability_reset,
                      entity_can_be_repaired=_entity_can_be_repaired,
                      entity_can_be_healed=_entity_can_be_healed,
                      pick_randomly=_pick_randomly,
                      sort_tiles_by_utility=_sort_tiles_by_utility,
                      sort_units_by_damage_utility=_sort_units_by_damage_utility,
                      attack_prediction=_attack_prediction,
                      # `has_effect_of_type` reste NON BRANCHE : la CATEGORIE d'un effet
                      # (`EffectsDatabase` def+0x58) n'est pas dans le canal de seed. Cf. le noeud
                      # `UnitsWithEffectsOfType` -- residu NOMME, pas un oubli.
                      current_player_machine_position=mow_pos)


def main_tile_id(state, entity_id) -> int | None:
    """`IdunBattle.Entities.EntityExtensions$$GetMainTile(entity, state)` en DOMAINE ID DE TUILE : la
    tuile d'une UNITE comme d'une TUILE (le natif rend une entite-tuile ELLE-MEME -- domaine mixte).
    `None` si `entity_id` n'est ni une tuile du board ni une unite POSITIONNEE.

    Foyer PARTAGE des collapses imperatifs qui ont besoin de la tuile visee AVANT de construire leur
    arbre (`astramilitarum.basilisk_shell_tiles`, `deathguard.plagueburst_target_tile`) -- le seul
    endroit du port ou `target_id` est normalise en TUILE. Les DEUX l'ecrivaient chacun de leur cote,
    et l'un des deux (1026) ne traitait QUE le cas UNITE : un `target_id` de tuile lui rendait `[]`,
    donc **zero obus**, sans erreur (#287-r12).

    ⚠ L'ORDRE DES DEUX BRANCHES EST LU, PAS CHOISI, et il n'est pas celui qu'on ecrit d'instinct :
    `IdunBattle.Entities.EntityExtensions$$GetMainTileId` essaie D'ABORD le composant de PIED
    (`TryGetComponent` -> `return *(uint*)(comp + 0x14)`), PUIS l'unite multi-pieds (l'`OrderedSet`
    @+0x78, dont il prend l'element 0 et RECURSE), et ne teste `EntityExtensions$$IsTile` qu'EN
    DERNIER, en repli. Une entite-TUILE est donc le cas de FALLBACK, jamais le cas prioritaire.
    Ce n'est pas academique cote port : les deux espaces d'ids (unites de `state.entities`, tuiles de
    `state.board`) se CHEVAUCHENT (residu nomme dans `operations/active_ability.py`), donc l'ordre
    DECIDE ce que rend un id ambigu. `deathguard.plagueburst_target_tile` testait la tuile d'abord --
    l'ordre inverse du natif ; il delegue desormais ici.

    ⚠ Pendant ID de `_entity_pos` (`entities/selectors/_shared.py`), qui rend une POSITION : les deux
    mirrorent la meme fonction native sous les deux formes dont le port a besoin ; celle-ci ne vaut
    que la ou un ID de tuile est attendu (pools de `PickRandomly`, `FixedTileIds`)."""
    board = getattr(state, "board", None)
    if board is None or entity_id is None:
        return None
    try:
        eid = int(entity_id)
    except (TypeError, ValueError):
        return None
    e = state.get_entity(eid)
    pc = e.get_component(PositionComponent) if e is not None else None
    # ⚠ UNE UNITE MORTE N'A PLUS DE TUILE, et c'est LU : `GetMainTileId` cherche le composant de
    # PIED, puis l'`OrderedSet` de pieds @+0x78 -- dont il sort par `return 0` quand il est VIDE
    # (`*(lVar1 + 0x18) == 0`). Le natif RETIRE du board l'unite tuee, donc son `GetMainTile` rend
    # `state.GetEntity(0)` = **null**. Cote port, `PositionComponent` SURVIT a la mort : sans ce
    # filtre, `main_tile_id(<cadavre>)` rendait sa derniere tuile.
    # MESURE (#287-r14, `test_429r1r3_dead_target_message_gate_live`) : la resolution de cible
    # branchee en amont du gate cible-morte transformait alors `IsUnit(<cadavre>)` en
    # `IsUnit(<tuile>)` = faux -- le gate ne mordait plus et le cast s'executait sur un cadavre.
    # C'est une regression PERMISSIVE, et c'est le harnais qui l'a vue, pas la lecture.
    # MEME NOTION D'OCCUPATION que `operations/active_ability.py::get_tiles` (« unite MORTE ->
    # liste VIDE, mirror du board natif d'ou une unite tuee est RETIREE »), que le selecteur
    # `Units(tiles)` (#57m), `CanAddUnit` et `walk_pathfinder` -- mais par le predicat LARGE
    # `UnitExtensions$$IsAlive` (cf. l'import), pas par les seuls PV : une unite RETIREE a PV
    # pleins n'a pas de pied non plus.
    if pc is not None and (e.get_component(UnitComponent) is None or unit_extensions_is_alive(e)):
        return board.id_at(pc.col, pc.row)
    return eid if eid in getattr(board, "by_id", {}) else None


def unit_id(state, entity_id) -> int | None:
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state)` en DOMAINE ID -- la surcharge
    DOMAINE MIXTE, celle que les DEUX call-sites de `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
    visent (etabli par les XREFS de la fonction, pas par son nom : le binaire en porte TROIS, dont
    une tuile->unite et une pied->unite). Son corps, relu :

        if (entity == null)      return null;
        if (IsType(entity, Unit))     return entity;                    // l'entite ELLE-MEME
        if (IsType(entity, Tile)) { c = entity.TileContentComponent@+0x38;
                                    if (!c.IsFilled())  return null;
                                    entity = state.GetEntity(c@+0x10);  // RECURSION
                                    continue; }
        if (IsType(entity, UnitFoot)) return GetUnit(<surcharge pied>, state);
        return null;

    Cote port : `state.entities` ne contient que des unites et des MoW, `state.board` les tuiles, et
    les PIEDS n'ont pas d'entite propre (`get_unit_feet` rend des POSITIONS) -- la 3e branche n'a
    donc pas de contrepartie, et son absence ne perd rien (aucun appelant du port ne tient d'id de
    pied).

    ⚠ UNE MoW N'EST PAS UNE `Unit` COTE NATIF (elle est du type `Machine` -- lu dans
    `IdunBattle.Entities.UnitExtensions$$GetMachine`, qui rend l'entite elle-meme sur ce type), alors
    que le port lui pose un `UnitComponent` pour la rendre exercable (`snapshot._load_machines`).
    Le discriminant retenu est donc le `MachineComponent`, present sur elle SEULE : sans lui,
    `GetUnit(<MoW>)` rendrait la MoW la ou le natif rend `null`.

    La branche TUILE delegue a `operations/active_ability.py::get_unit`, qui EST le mirror deja
    porte de cette meme resolution en domaine `(col, row)` -- surtout pas un 2e port du predicat
    d'occupation."""
    if entity_id is None:
        return None
    try:
        eid = int(entity_id)
    except (TypeError, ValueError):
        return None
    e = state.get_entity(eid)
    if e is not None:
        if e.get_component(MachineComponent) is not None:
            return None                              # type `Machine` -> ni Unit, ni Tile -> null
        if e.get_component(UnitComponent) is not None:
            return eid                               # type `Unit` -> l'entite ELLE-MEME
    board = getattr(state, "board", None)
    if board is None or eid not in getattr(board, "by_id", {}):
        return None
    return _aa.get_unit(state, board.coord(eid))     # type `Tile` -> son occupant


def machine_id(state, entity_id) -> int | None:
    """`IdunBattle.Entities.UnitExtensions$$GetMachine(entity, state)` en DOMAINE ID :

        if (entity == null)             return null;
        if (IsType(entity, Machine))    return entity;
        if (IsType(entity, Tile))       return TileExtensions.GetMachinePlatformContent(entity, state);
        return null;

    ⚠ La branche TUILE reste NON PORTEE, et c'est un residu NOMME, pas un oubli : le port ne
    modelise pas les PLATEFORMES de MoW comme contenu de tuile (une MoW n'a ni `PositionComponent`
    ni tuile -- cf. `snapshot._load_machines`, « hors-plateau »), donc il n'existe aucun substrat
    d'ou tirer `GetMachinePlatformContent`. Rendre `None` y est la degradation FIDELE a ce que le
    port sait : aucune plateforme inventee."""
    if entity_id is None:
        return None
    try:
        eid = int(entity_id)
    except (TypeError, ValueError):
        return None
    e = state.get_entity(eid)
    if e is not None and e.get_component(MachineComponent) is not None:
        return eid
    return None


def actual_target(state, options, caster_id, target_id) -> int | None:
    """`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget(options, caster, target)` en
    DOMAINE ID -- la transformation que le natif applique a TOUTE cible AVANT ses gates et avant
    `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities` (#287-r14).

    Corps relu (build rnca9r7q6c), l'ordre des quatre branches est CELUI-LA :

        if (options.isSelfCasting == 0) {                      // byte @options+0x00
            if (options.rules & 0x40)          return EntityExtensions.GetMainTile(target, state);
            if (options.rules & (1<<44))       return UnitExtensions.GetMachine(target, state);
            if (options.rules & (1<<46)) { u = UnitExtensions.GetUnit(target, state);
                                           if (u != null) return u;
                                           return UnitExtensions.GetMachine(target, state); }
            return UnitExtensions.GetUnit(target, state);
        }
        return caster;                                          // self-cast

    ⚠ La branche MACHINE n'essaie PAS `GetUnit` d'abord -- seule la branche ACTOR enchaine les deux.
    Recopier « unit puis machine » partout serait un masque faux, du meme genre que recopier le
    litteral d'un ctor a preset.

    `options is None` = masque NON RE-LU -> on rend `target_id` TEL QUEL. Meme doctrine que
    `TARGETING_OPTIONS` cote gate de cible : sans masque le port ne devine pas, il ne transforme
    pas. Inventer `GetUnit` par defaut ferait resoudre en unite des cibles dont on ignore le
    domaine.

    IDEMPOTENCE (ce qui autorise les DEUX branchements du port -- `AbilityHandler` au rang natif ET
    la tete des `execute_behaviour` tile-target) : chaque branche est un projecteur.
    `GetMainTile(<tuile>)` rend la tuile (`main_tile_id` teste le `PositionComponent` d'abord, la
    tuile du board en repli -- l'ordre natif de `GetMainTileId`), `GetUnit(<unite>)` rend l'unite,
    `GetMachine(<MoW>)` rend la MoW, et le self-cast rend `caster` quel que soit l'argument.
    Appliquer la resolution deux fois rend donc exactement ce que la premiere a rendu."""
    if options is None:
        return target_id
    if getattr(options, "self_cast", False):
        return caster_id
    if options.is_tile_targeting:
        # SUBSTRAT DE TUILES NON MESURE -> aucune resolution, `target_id` rendu TEL QUEL.
        # `state.board is None` n'est pas « la cible n'a pas de tuile » : c'est « le port n'a pas
        # charge le boardGraph » (`load_state(dv, ob, snap)` sans `board=`, ce que font plusieurs
        # tests et tout appelant qui n'a pas la capture du plateau). Le natif, lui, a TOUJOURS son
        # board. Rabattre ce cas sur le `null` de `GetMainTile` transformerait une non-mesure en
        # REFUS -- exactement la degradation que la regle « `None` = pas mesure, jamais un zero »
        # interdit. MESURE : sans ce repli, `test_valkyrie_strike_migration_live` passe de
        # « l'arbre DSL pose 1022 » a `execute_behaviour -> None` (no-op complet).
        if getattr(state, "board", None) is None:
            return target_id
        return main_tile_id(state, target_id)
    if options.is_machine_targeting:
        return machine_id(state, target_id)
    if options.is_actor_targeting:
        u = unit_id(state, target_id)
        return u if u is not None else machine_id(state, target_id)
    return unit_id(state, target_id)
