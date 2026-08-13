"""`IdunBattle.AI.Utilities` — DISPATCHER (`UtilitiesDatabase.GetUtility` + `Playbook.GetMovementUtility`)
+ utilites de MOUVEMENT propres (DislikeStartingTiles).

Les feuilles/composites Tile (7) et Damage (34) vivent dans `engine.utilities.{tile,damage}` (POUR EVITER
LES CYCLES D'IMPORT : `engine.playbook.base` les tire tres tot ; les heberger sous `engine.ai` creerait
un cycle via `engine.ai.context` -> `engine.playbook.scene`). Ce module les REFERENCE et les enregistre.

Doctrine « 1:1 classe native -> classe Python » : une CLASSE `*Utility` par utilite (BaseUtility/
ComposedUtility dans `engine.utilities.base`). `get_movement_utility` = `Playbook<T>.IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility` = `ComposedUtility.EvaluateMovement(UtilitiesDatabase.GetUtility(type), caster@pos)`.

SIGNATURE : chaque sous-systeme a la sienne (tile: `(tile,meta,ctx,wt)` ; damage: `(pred,max_hp,wt)` ;
mouvement: `(ctx,pos)`). `get_movement_utility` dispatch en connaissance de cause (Tile via l'adaptateur
`(ctx,pos)->tile` = `base.tile_utility` ; DislikeStartingTiles direct `(ctx,pos)`)."""
from __future__ import annotations

from engine.utilities.base import BaseUtility, ComposedUtility          # noqa: F401 (re-export)
from engine.utilities.tile import TILE_UTILITY, TILE_LEAVES
from engine.utilities.damage import DAMAGE_UTILITY
from engine.utilities.move import MIN_DIST_UTILITY, UNIT_MOVEMENT
from engine.utilities.heal import HEAL_UTILITY
from engine.utilities.repair import REPAIR_UTILITY
from engine.utilities.effect import ADDED_EFFECT_UTILITY
from engine.utilities.utility_type import UtilityType
# Forme B (module + acces attributaire) : `utilities_database` et `tile_leaf_ctx` sont substituables
# par un probe, ce qu'une liaison `from X import f` au niveau module gelerait (CLAUDE.md, morsure).
# Aucun cout de cascade : `engine.utilities.tile` est deja importe juste au-dessus.
import engine.utilities.tile as _tile_db


class DislikeStartingTilesUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.DislikeStartingTilesUtility` (`UtilityType.DislikeStartingTiles=27`,
    dump.cs gqfc5mff6c). `IdunBattle.AI.Utilities.DislikeStartingTilesUtility$$EvaluateMovementInSteps` (`<…>IdunBattle.AI.Utilities.DislikeStartingTilesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`) : penalite
    si l'empreinte de `pos` chevauche l'empreinte de DEBUT-DE-TOUR de l'unite (biais a quitter le spawn).
    Mirror du decompile (#R30 -- corps RELU en entier) :

        util  = Fix64.FromInt(0);
        start = EntityExtensions.GetTurnStartPosition(unit, state);      // Nullable<UnitPosition>
        n     = UnitExtensions.GetFeetCount(unit, state);
        tiles = new List<TileEntity> { case.UnitPosition.MainTile };     // UnitPosition$$get_MainTile
        if (n == 7) tiles.AddRange(battleQuery.GetAdjacentTiles(tiles, false, true, true));
        if (start.HasValue && start.Value.ContainsAnyOf(tiles))
            util += BaseUtility.GetUtilityValue(query, DislikeStartingTiles);
        return util;

    Deux points que la paraphrase « pos == origine » manquait :
      * l'empreinte candidate part de la MAIN TILE de la `UnitPosition` (= `feet[0]`), et **n'est
        etendue QUE si `GetFeetCount == 7`** (l'anneau des voisins). Une unite a **3** pieds n'etend
        RIEN ici : le natif ne teste que sa main tile. C'est un quirk, pas un oubli ;
      * le test final est un CHEVAUCHEMENT d'ensembles (`ContainsAnyOf`) entre l'empreinte de depart
        et l'empreinte candidate, pas une egalite de tuiles.
    Pour une unite a 1 pied les deux formulations coincident exactement (`{pos} inter {origin}`), donc
    le comportement du cas nominal est inchange.

    DATA-GAP LEVE (#343, 2026-07-31) — le poids etait a 0.0 avec la consigne « a confirmer live : si le
    poids BC DislikeStartingTiles est != 0, cabler `_WEIGHT` ». Les DEUX moities sont mesurees :

    * LIVE (`probe_343_tile_target_emission.py --item 1194`, board MC1_67/909, NovaShield greffe sur
      tauCrisis) : a utilite STRICTEMENT egale entre l'origine (1,0) et la tuile de move (0,0)
      — meme centre marque, meme terme Tile(7)=30, donc 137 contre 137 dans le modele du port — le
      natif EMET UN `MoveUnitMessage` vers (0,0) avant son `ActiveAbilityMessage`. Avec un poids nul
      il resterait sur place (`Bucket.AddAction` ne remplace que sur amelioration STRICTE, et
      l'origine est balayee EN PREMIER). Ce datapoint prouve donc le SIGNE (penalite < 0) et la
      NON-NULLITE ; il ne borne pas la magnitude (aucune tuile de move accessible n'ecartait le
      terme Tile de plus de 10).
    * BC : la categorie de poids de CETTE utilite (`BaseUtility` `this+0x58`, le `Dict<string,int>`
      que lit `IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue`) est
      `Default/DislikeStartingTilesUtility`, et elle porte EXACTEMENT UNE entree :
      `ActiveAbility_DislikesCurrentTiles = -40`. Meme forme et meme accesseur que
      `MinDistanceToClosestEnemy.PerTileDistance = -100`.

    CE QUI RESTE UNE INFERENCE, et il faut le dire : la CHAINE passee a `GetUtilityValue` est un
    litteral IL2CPP (`DAT_1833dcd00` dans
    `IdunBattle.AI.Utilities.DislikeStartingTilesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`)
    qui ne se lit pas statiquement ; on l'identifie a `ActiveAbility_DislikesCurrentTiles` parce que
    c'est la SEULE cle de la categorie. Si un jour la categorie en portait deux, il faudrait lire la
    chaine live avant de choisir.
    Le trou `GetFeetCount`, lui, etait deja COMBLE (substrat #R30). SEUL CONSOMMATEUR de ce terme
    dans la face DECISION : `engine/playbook/noncomparable/nova_shield.py` (rayon de souffle borne)."""
    UTILITY_TYPE = int(UtilityType.DislikeStartingTilesUtility)  # 28

    def candidate_footprint(self, ctx, pos) -> list:
        """`tiles` du corps natif : `[UnitPosition.MainTile]`, etendu de l'ANNEAU des voisins SI ET
        SEULEMENT SI `GetFeetCount(unit) == 7`. `ctx.feet_count` = le compte porte par l'appelant
        (absent -> 1, le cas nominal) ; `ctx.neigh_by_pos` fournit le voisinage natif."""
        tiles = [pos]
        if int(getattr(ctx, "feet_count", 1) or 1) != 7:
            return tiles
        neigh = getattr(ctx, "neigh_by_pos", None) or {}
        for n in (neigh.get(pos) or ()):               # GetAdjacentTiles(tiles, false, true, true)
            if n not in tiles:
                tiles.append(n)
        return tiles

    # `IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue(query, <cle>)` : categorie de poids BC
    # `Default/DislikeStartingTilesUtility`, cle unique `ActiveAbility_DislikesCurrentTiles` (cf. la
    # docstring de la classe pour ce qui est MESURE et ce qui est INFERE).
    WEIGHT_CATEGORY = "DislikeStartingTilesUtility"
    WEIGHT_KEY = "ActiveAbility_DislikesCurrentTiles"

    def evaluate(self, ctx, pos) -> float:
        wt = getattr(ctx, "wt", None)
        # Poids NON LU (contexte sans weights BC) -> 0.0 : on ne fabrique pas une penalite a l'aveugle.
        weight = float(wt.sub(self.WEIGHT_CATEGORY, self.WEIGHT_KEY)) if wt is not None else 0.0
        # `start.Value.ContainsAnyOf(tiles)` : chevauchement de l'empreinte de DEBUT DE TOUR
        # (`ctx.start_feet`, defaut = la seule `ctx.origin`) avec l'empreinte candidate.
        start = getattr(ctx, "start_feet", None)
        if not start:
            origin = getattr(ctx, "origin", None)
            start = [origin] if origin is not None else []
        if not start:
            return 0.0
        footprint = self.candidate_footprint(ctx, pos)
        return weight if any(s in footprint for s in start) else 0.0


class UtilitiesDatabase:
    """`IdunBattle.Core.Services.UtilitiesDatabase` — registre `UtilityType -> BaseUtility` (peuple par
    `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`). `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` = lookup par type (None si non porte)."""
    _BY_TYPE: dict = {}

    @classmethod
    def register(cls, util: BaseUtility) -> BaseUtility:
        cls._BY_TYPE[util.UTILITY_TYPE] = util
        return util

    @classmethod
    def get_utility(cls, utility_type: int) -> "BaseUtility | None":
        return cls._BY_TYPE.get(utility_type)


# Enregistrement (composites + feuilles + mouvement) — reproduit `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`.
UtilitiesDatabase.register(TILE_UTILITY)      # Tile = 7
UtilitiesDatabase.register(DAMAGE_UTILITY)    # Damage = 34
UtilitiesDatabase.register(UNIT_MOVEMENT)     # UnitMovement = 6 (Tile + MinDistanceToClosestEnemy)
UtilitiesDatabase.register(MIN_DIST_UTILITY)  # MinDistanceToClosestEnemy = 17
UtilitiesDatabase.register(HEAL_UTILITY)      # Heal = 44
UtilitiesDatabase.register(REPAIR_UTILITY)    # RepairedAmount = 48
UtilitiesDatabase.register(ADDED_EFFECT_UTILITY)  # AddedTileEffects = 46
_DISLIKE_STARTING_TILES = UtilitiesDatabase.register(DislikeStartingTilesUtility())  # 27
for _name, _inst in TILE_LEAVES.values():     # feuilles Tile (8, 9, 13, 19, …)
    if _inst is not None:
        UtilitiesDatabase.register(_inst)
for _child in DAMAGE_UTILITY.children:        # feuilles Damage (35, 36, 37)
    UtilitiesDatabase.register(_child)


def get_movement_utility(ctx, pos, utility_type: int) -> float:
    """`Playbook<T>.IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility` = `ComposedUtility.EvaluateMovement(
    UtilitiesDatabase.GetUtility(utility_type), caster@pos)`. Dispatch par signature de sous-systeme.
    0.0 si l'utilite de mouvement n'est pas (encore) resolue pour ce type."""
    if utility_type == UtilityType.Tile:
        # Tile(7) : l'eval MOUVEMENT passe par l'adaptateur (ctx,pos)->(tile,meta,{},wt) = base.tile_utility
        # (import LAZY pour eviter tout cycle). Carte plate ~0.
        if getattr(ctx, "wt", None) is None or getattr(ctx, "elev_by_pos", None) is None:
            return 0.0
        from engine.playbook.base import tile_utility
        return tile_utility(ctx, pos)
    if utility_type == UtilityType.DislikeStartingTilesUtility:
        return _DISLIKE_STARTING_TILES.evaluate(ctx, pos)
    # FEUILLES DE `UtilityMovementCase` a signature TILE (#996-r1) -- meme adaptateur que Tile(7)
    # ci-dessus, sans le `meta` par-tuile (`elevation`, `effects`, `is_temporary`), qu'aucun appelant
    # de CETTE branche ne construit. Le natif ne fait aucune distinction : toutes ces feuilles sont
    # des `EvaluateMovementInSteps(UtilityMovementCase)` que `ComposedUtility.EvaluateMovement`
    # appelle de la meme facon ; c'est le PORT qui avait deux signatures et n'en dispatchait qu'une.
    #
    # RAYON DE SOUFFLE, MESURE : `get_movement_utility` n'a que TROIS appelants
    # (`action_generators.movement_action_with_override`, `playbook/loki_custom.py`,
    # `playbook/noncomparable/nova_shield.py`) et les DEUX derniers ne passent que `Tile(7)` /
    # `DislikeStartingTiles`, tranches AVANT d'arriver ici. Reste le premier, dont l'unique producteur
    # est le behaviour DSL `PerformAIMovement` : ses call-sites portes sont `1144 BioMinefield`
    # (`UtilityType.BioMinefield_MoveTowardsTarget` = 62, **ABSENTE** d'`UTILITY_BY_TYPE` -> `None`
    # -> 0.0, exactement comme avant) et `1053 DevoutPush` (53, celle que cette tranche ajoute).
    # Le comportement mesure de #939 est donc inchange au bit pres.
    leaf = _tile_db.utilities_database(int(utility_type))
    if leaf is not None:
        wt = getattr(ctx, "wt", None)
        if wt is None:
            return 0.0                      # poids BC non lus : on ne fabrique aucun score
        return float(leaf.evaluate(pos, None, _tile_db.tile_leaf_ctx(ctx), wt) or 0.0)
    return 0.0
