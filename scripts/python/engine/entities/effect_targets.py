"""`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)` -- FOYER UNIQUE.

Le noeud construit un `IdunBattle.Entities.Triggers.IsEffectTargetTrigger`, dont le
`$$ShouldTrigger` resout le selecteur `+0x10` puis invoque le slot d'interface `+0x20` avec
`(entity, effectType@+0x18, onlyActive = 0)`. Ce slot est
`IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget`, qui :

  1. `...$$GetEffectsWithTargets(unit = null, onlyActive)` -- balaye **TOUTES** les entites-effet du
     state (pas seulement celles de l'entite testee), retient celles dont
     `EffectComponent.Targets @+0x48` est non vide, et publie `(effectType @+0x58, targets @+0x48)` ;
  2. rend `true` des qu'une entree de type `effectType` contient l'id de l'entite testee.

Deux consequences STRUCTURELLES, mesurees, qui font que `HasEffect` n'est PAS un substitut :

* **Le PORTEUR n'est pas la CIBLE.** `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` inscrit
  l'entite-effet dans l'`EffectsOwnedComponent` de son **OWNER** (`ec.OwnerId @+0x14`), et c'est cette
  liste-la que publie la capture (`decisionView.units[].effects`, `frida/hooks/game/effects.ts`
  lit `EffectsOwnedComponent.ActiveEffectIds`). `EffectsState.by_unit` est donc indexee par PORTEUR.
* **`Targets @+0x48` a un SEUL peupleur** : `IdunBattle.Operations.RefreshEffectsOperation$$
  AddTargetsToEffect` (unique appelant d'`IdunBattle.Entities.Components.EffectComponent$$AddTargetId`),
  appele par `...$$UpdateEffectTargets` avec le `desiredTargets` rendu par le
  `<Effect>$$CreateTargetSelector` de l'effet, evalue avec `Owner = l'owner de l'instance`.

=> La liste de cibles est **la geometrie du selecteur de l'EFFET**, jamais celle du call-site : le
selecteur passe au noeud (`Owner@DSLSelectors+0x30`, `Caster@+0x48`, `Target@+0x60`, ...) designe le
SUJET du test, pas la forme de l'aura. Ce module re-derive donc `Targets` A LA LECTURE, en appliquant
le `CreateTargetSelector` de CHAQUE effectType inscrit sur CHACUN de ses porteurs.

`EFFECT_TARGET_SELECTORS` n'inscrit QUE des geometries LUES au decompile et CONFRONTEES live. Un
`effect_type` absent rend `None` (= << non porte >>), jamais `False` : l'appelant doit degrader
explicitement. Les geometries lues mais non consommees par le port vivent dans
`docs/rl/case-418-r1-is-effect-target.md`, pas ici -- pas de port speculatif.
"""
from __future__ import annotations

from typing import Optional

import hexgeo

from .. import battle_query as bq       # forme B (#485-r1-r1) : `battle_query` n'importe que
#                                        `hexgeo` + `.hex_corner`, donc AUCUN cycle a fermer ici.
from .effect_type import EffectType
# #1015-r1 : les trois traits + la faction du selecteur de `1052 Synapse_Effect`. Deux mirrors
# d'enum FEUILLES (`unit_trait` n'importe que `enum`/`functools`, `unit_faction` de meme) -- les
# hisser ici n'allonge la cascade d'aucun module.
from .traits.unit_trait import UnitTrait
from .unit_faction import UnitFaction

#: `UnitTrait.Psyker` (`0x3ea`) et `UnitTrait.Immune` (`0x19`) -- les deux filtres de trait du
#: `CreateTargetSelector` de `1191`. Noms tels que la capture les publie (`StatsComponent.ctx.traits`
#: cote runner, `Scene.ctx_by_id[...].traits` cote decision).
_TRAIT_PSYKER = "Psyker"
_TRAIT_IMMUNE = "Immune"

#: Les TROIS traits et la faction du `CreateTargetSelector` de `1052 Synapse_Effect` (#1015-r1).
#: Membres NOMMES des deux mirrors (`UnitTrait` 0x3f7/0x7e5/0x7e8, `UnitFaction` 0xc), jamais des
#: ordinaux : les noms de MEMBRE sont exactement ce que publient `StatsComponent.ctx.traits` et le
#: `FactionId` gameconfig (cf. `entities/unit_faction.py`, ou `HasFaction` compare une CHAINE).
_TRAIT_BATTLE_FATIGUE = UnitTrait.BattleFatigue.name                 # 0x3f7 = 1015
_TRAIT_INSTINCTIVE_BEHAVIOUR = UnitTrait.InstinctiveBehaviour.name   # 0x7e5 = 2021
_TRAIT_SYNAPSE = UnitTrait.Synapse.name                              # 0x7e8 = 2024
_FACTION_TYRANIDS = UnitFaction.Tyranids.name                        # 0xc = 12
#: `range = 2` de `SurroundingUnits` -- litteral LU a sa POSITION dans la signature.
_SYNAPSE_RANGE = 2


class EffectTargetWorld:
    """Vue MINIMALE du monde que reclame la re-derivation. Deux substrats l'implementent -- l'ECS du
    runner (`runner/components.py`) et les tables de `Scene` (`playbook/scene.py`) -- exactement comme
    pour les autres noeuds a double face. Duck-typing : aucune sous-classe n'est requise."""

    def unit_ids(self):                       # -> iterable[int]
        raise NotImplementedError

    def carries(self, uid: int, effect_type: int) -> bool:
        """L'unite est-elle **OWNER** d'une instance de ce type (`EffectsOwnedComponent`) ?"""
        raise NotImplementedError

    def pos(self, uid: int):                  # -> (col, row) | None
        raise NotImplementedError

    def team(self, uid: int):                 # -> int | None
        raise NotImplementedError

    def alive(self, uid: int) -> bool:
        raise NotImplementedError

    def traits(self, uid: int):               # -> sequence[str]
        raise NotImplementedError

    # -- LE CANAL DE VOISINAGE NATIF (#943-r7) -----------------------------------------------
    # `AdjacentFriends` descend sur `TileQuery$$IterateAdjacentTiles`, dont l'ENUMERATION est la
    # liste STOCKEE du `ConnectivityComponent` et non la couronne hex (mesure #930 : la couronne
    # SUR-ATTEINT de 4 aretes sur `C1_74`, 38 sur `C3_14`, 0 dans l'autre sens). Les deux etages
    # sont des ENTREES du protocole, pas une derivation locale : ce module est le foyer COMMUN aux
    # deux substrats, donc il ne connait ni `Scene.board` ni `State.board` -- chacun publie le sien.
    #
    # TRI-ETAT OBLIGATOIRE : `None` = canal absent -> `battle_query.is_adjacent` garde son repli
    # GEOMETRIQUE nomme. Un `{}` se lirait << aucune tuile n'a de voisin >> et rendrait le predicat
    # FAUX partout -- le vice exact de `#381-r3`.
    def neigh_by_pos(self) -> "dict | None":
        """`{(col,row): [(col,row), ...]}` -- `boardGraph.neighbours`, la liste STOCKEE."""
        raise NotImplementedError

    def elev_by_pos(self) -> "dict | None":
        """`{(col,row): elevation}` -- le second etage (`|dElev| < 2`) d'`IterateAdjacentTiles`."""
        raise NotImplementedError


# --------------------------------------------------------------------------- selecteurs d'effet
def _adjacent_friends(world, owner_id: int) -> Optional[set]:
    """`IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateTargetSelector` =
    `AdjacentFriends(unit = Owner@DSLSelectors+0x30, unitTile = <+0x50>, unique = 1)`.

    ⚠ La signature est `AdjacentFriends(unit, unitTile, unique)` : il n'y a **ni rayon ni
    includeCenter**. Le porteur est donc EXCLU, et la portee est le ring-1.

    ⚠ LE RING-1 N'EST PAS LA COURONNE HEX (#943-r7). `DSLSelectors$$AdjacentFriends(unit, unique,
    selType)` = `Friends(unit, Units(AdjacentTiles(unit)) - unit, selType)`, et `AdjacentTiles`
    descend sur `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : une ENUMERATION de la
    liste STOCKEE (`ConnectivityComponent+0x10`) suivie d'une porte `|dElev| < 2` INCONDITIONNELLE.
    Le port passe donc par `battle_query.is_adjacent`, qui porte les DEUX etages et DEGRADE SEUL en
    couronne hex quand les canaux sont absents (no-op demontrable sur les montages sans board).

    CE SITE EST LE FOYER DES DEUX FACES -- `_SceneEffectTargetWorld` (decision) et
    `_RunnerEffectTargetWorld` (combat) l'appellent tous les deux, donc le cablage ne peut pas
    creer de divergence de faces : il les deplace ENSEMBLE. C'est ce qui l'a fait retenir la ou
    l'expression JUMELLE du meme selecteur natif (le canal d'aura de `BigTargetAdjacentEffect$$
    CreateEffectHitsBonusForAttack`, `effects/loki/hits.py`) reste hors de portee -- son ctx est un
    dict sans board."""
    me, team = world.pos(owner_id), world.team(owner_id)
    if me is None or team is None:
        return None
    elev, neigh = world.elev_by_pos(), world.neigh_by_pos()
    out = set()
    for uid in world.unit_ids():
        if int(uid) == int(owner_id) or world.team(uid) != team or not world.alive(uid):
            continue
        p = world.pos(uid)
        if p is not None and bq.is_adjacent(me, p, elev, neigh):
            out.add(int(uid))
    return out


def _surrounding_enemy_psykers_r2(world, owner_id: int) -> Optional[set]:
    """`IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathPsykerSuppressionEffect$$
    CreateTargetSelector` =

        UnitsWithoutTrait(
            UnitsWithTrait(
                SurroundingEnemies(unit = Owner@+0x30, unitTile = <+0x50>, range = 2, unique = 1,
                                   unitSelectionType = 3),
                0x3ea = Psyker, 3),
            0x19 = Immune, 3)

    `range` est bien le 3e argument de la surcharge `SurroundingEnemies(unit, unitTile, range:Int32,
    unique, unitSelectionType)` -- lu dans la SIGNATURE, pas devine (`AdjacentFriends`, elle, n'en a
    pas : c'est le piege de lecture de #419/#429). `Surrounding*` = disque INCLUSIF."""
    me, team = world.pos(owner_id), world.team(owner_id)
    if me is None or team is None:
        return None
    out = set()
    for uid in world.unit_ids():
        t = world.team(uid)
        if t is None or t == team or not world.alive(uid):        # Enemies(owner, ...)
            continue
        p = world.pos(uid)
        if p is None or hexgeo.distance(me, p) > 2:               # range = 2, disque inclusif
            continue
        tr = world.traits(uid) or ()
        if _TRAIT_PSYKER not in tr or _TRAIT_IMMUNE in tr:        # WithTrait / WithoutTrait
            continue
        out.add(int(uid))
    return out


def _synapse_targets(world, owner_id: int) -> Optional[set]:
    """`IdunBattle.Entities.Effects.Loki.SynapseEffect$$CreateTargetSelector` -- MIRROR du
    decompile, noeud par noeud :

        S = SurroundingUnits(origin = Owner@DSLSelectors+0x30, range = 2, unique = true,
                             includeCenter = FALSE, unitSelectionType = 3)
        F = Friends(of = Owner@+0x30, entities = S, selectionType = 3)
        return Unique(   UnitsWithTrait(F, 0x3f7 = 1015 BattleFatigue,          3)
                       + UnitsWithTrait(F, 0x7e5 = 2021 InstinctiveBehaviour,   3)
                       + UnitsFromFaction( UnitsWithoutTrait(F, 0x7e8 = 2024 Synapse, 3),
                                           0xc = UnitFaction.Tyranids, 3) )

    Les litteraux `range = 2` / `unique = 1` / `includeCenter = 0` / `unitSelectionType = 3` sont
    LUS a leur POSITION dans la signature `SurroundingUnits(origin, range, unique, includeCenter,
    unitSelectionType)` (`frida/methods.tsv`) -- jamais devines.

    ⚠ **`includeCenter = FALSE` : l'emetteur n'est PAS dans sa propre bulle.** C'est le MEME fait
    que la mesure live #1011 (patte SELF a 0 avec le Neurothrope pour seul porteur `Synapse`), ici
    par un SECOND site natif et INDEPENDANT -- `BattleQuery$$GetInRangeAuraAmount` le disait sur
    l'axe AURA, ce selecteur-ci le dit sur l'axe CIBLES.

    ⚠ **Le 3e disjoint exige le canal FACTION.** Il est OPTIONNEL du protocole : un substrat qui
    ne publie pas `faction(uid)` fait rendre `None` (NON MESURE) -- **jamais un ensemble PARTIEL**,
    qui affirmerait « cette unite n'est pas ciblee » sur la foi de deux disjoints sur trois. Seul
    le substrat RUNNER l'implemente ; la face DECISION n'a aucun lecteur de ce type.

    CONSOMMATEUR PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    InstinctiveBehaviour_UpdateTargetAbility$$GetUpdatedForcedTarget`, dont le gate est
    `NOT IsEffectTarget(Owner@+0x30, 0x41c = Synapse_Effect)` -- litteralement le « Friendly units
    within 2 hexes ignore the effects of Instinctive Behaviour » de l'i2."""
    faction = getattr(world, "faction", None)
    if faction is None:
        return None                                   # canal absent -> NON MESURE (cf. docstring)
    me, team = world.pos(owner_id), world.team(owner_id)
    if me is None or team is None:
        return None
    out = set()
    for uid in world.unit_ids():
        if int(uid) == int(owner_id):                 # `includeCenter = false`
            continue
        if world.team(uid) != team or not world.alive(uid):        # `Friends(Owner, ..., 3)`
            continue
        p = world.pos(uid)
        if p is None or hexgeo.distance(me, p) > _SYNAPSE_RANGE:   # `range = 2`, disque
            continue
        tr = world.traits(uid) or ()
        if _TRAIT_BATTLE_FATIGUE in tr or _TRAIT_INSTINCTIVE_BEHAVIOUR in tr:
            out.add(int(uid))                         # disjoints 1 et 2
            continue
        if _TRAIT_SYNAPSE in tr:                      # `UnitsWithoutTrait(F, Synapse)`
            continue
        if faction(int(uid)) == _FACTION_TYRANIDS:    # `UnitsFromFaction(..., Tyranids)`
            out.add(int(uid))
    return out


#: `effect_type -> <Effect>$$CreateTargetSelector` porte. N'inscrire QUE ce qui est LU au decompile
#: ET confronte live (case-366-r1 pour `1026`, case-418-r1 pour `1191`, #1015-r1 pour `1052`).
EFFECT_TARGET_SELECTORS = {
    int(EffectType.BigTarget_AdjacentEffect): _adjacent_friends,                    # 1026
    int(EffectType.HuntersBeyondDeathPsykerSuppression): _surrounding_enemy_psykers_r2,   # 1191
    int(EffectType.Synapse_Effect): _synapse_targets,                               # 1052
}


def is_effect_target(world, unit_id: int, effect_type: int) -> Optional[bool]:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)` ->
    `IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget(target, effectType, onlyActive = 0)`.

    `None` = geometrie NON PORTEE pour ce type (pas d'entree dans `EFFECT_TARGET_SELECTORS`) ou
    substrat manquant (position/equipe inconnue) -- **jamais** un `False` invente. Le natif, lui,
    lit une liste MATERIALISEE : rendre `False` ici reviendrait a affirmer que le refresh natif l'a
    laissee vide, ce qu'on n'a pas mesure.

    `onlyActive = 0` (litteral du `IsEffectTargetTrigger$$ShouldTrigger` porte) : on ne filtre PAS
    sur `EffectComponent.IsActive`, donc le porteur est cherche dans `EffectsState.has_effect`
    (filtre `consumed` seul), pas dans `active_effects`."""
    sel = EFFECT_TARGET_SELECTORS.get(int(effect_type))
    if sel is None:
        return None
    for uid in world.unit_ids():
        if not world.carries(int(uid), int(effect_type)):
            continue
        targets = sel(world, int(uid))
        if targets is None:
            return None                       # substrat manquant sur un porteur REEL -> inconnu
        if int(unit_id) in targets:
            return True
    # Aucun porteur atteint => aucune entite-effet de ce type ne cible l'unite. Le natif ferme de la
    # meme facon : `GetEffectsWithTargets` ne publie que des entites-effet EXISTANTES, et son
    # pre-filtre `IdunBattle.Core.Services.EffectsQuery$$IsEffectInPlay` court-circuite a FAUX quand
    # aucune n'est du type demande.
    return False
