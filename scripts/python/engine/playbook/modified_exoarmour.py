"""`ModifiedExoarmourPlaybook` — le playbook de MOUVEMENT du passif `ModifiedExoarmour` (1529).

Famille « corps propre » (comme `friends_in_range.py` / `geminae_superia.py`) : il n'override pas
les `GetAdjacent{Friend,Enemy}Utility` du corps partage
`AdjacentUnitPreferenceTriggeredAbilityPlaybook`, il a SON PROPRE iterateur
`CalculateMovementUtilityInStepsInternal`. Le dispatcher est le meme (feuille de tuile
`TriggeredAbilitiesUtility(2)` -> `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`),
d'ou l'enregistrement commun dans `TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

CE QUI REND CETTE FEUILLE DIFFERENTE DE TOUTES LES AUTRES DU REGISTRE : elle ne compte ni des
voisins ni des tuiles, elle se paie **PAR TUILE PARCOURUE** -- `5 x |chemin|`. Elle GRANDIT donc
avec la distance, et un port qui l'ignore sous-estime systematiquement le desir de bouger de son
porteur. Mesure #27-r1 (board MC1_67, seed 909, `votanChampion` Kimm injectee, `Damage = 1000`) :
natif = move + attaque normale, moteur = 1222 sur place. C'est ce terme, et lui seul, qui avait
oblige #27-r1 a RETIRER le passif de son montage principal.

⚠ La cle BC `ModifiedExoarmour_LikesMovingPerTile` est **AJOUTEE par le build `rnca9r7q6c`** : elle
est ABSENTE de `data/seed-bc.json` (la capture) et vaut **5** au gameconfig VIVANT
(`aiUtilities.Default.TriggeredAbilities`). Les deux cotes la lisent grace au refresh
`catalog_inject.refresh_ai_utilities` (natif) / `engine.weights.load` (moteur) -- sans lui, natif et
port liraient tous deux 0 et seraient d'accord, faux tous les deux (meme piege que #271).
"""
from __future__ import annotations

from ..entities.pathfinding.walk_pathfinder import get_path_node_counts_by_pos
from ..entities.pathfinding.tile_blocking import TILE_MOVEMENT_BLOCKING_EFFECT_TYPES
from ..services.static_battle_rules import not_blocking_movement_of_traits
from ..entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3


_CACHE_KEY = "_modified_exoarmour_path_nodes"     # memo par-DECISION (le `tile_leaf_ctx` est unique
                                                  # sur tout le sweep de tuiles, cf. `engine.move`)


def _blocking_positions(ctx: dict) -> set:
    """Positions qui BLOQUENT le passage au sens
    `IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit(nextTile, unit)` :

        occ = TileExtensions.GetTileContent(nextTile).<occupant>
        if (occ == null)                          return false
        if (UnitExtensions.HasTrait(occ, 0x1b))   return false      // UnitTrait.Steppable
        return UnitExtensions.IsEnemy(occ, unit)

    Cote port, `enemy_units` du `tile_leaf_ctx` porte deja le filtre de camp (ce sont les ennemis
    VIVANTS du mover) et leur `traits` (noms). Les AMIS ne bloquent jamais -- on peut les traverser,
    seulement pas s'y arreter, et cette derniere contrainte est celle de l'ENUMERATION
    (`get_movable_positions`), pas celle du chemin."""
    out = set()
    for u in (ctx.get("enemy_units") or ()):
        p = u.get("pos")
        if not p:
            continue
        if "Steppable" in (u.get("traits") or ()):     # HasTrait(occ, 0x1b) -> ne bloque pas
            continue
        out.add((p[0], p[1]))
    return out


def _block_entering_positions(ctx: dict) -> set:
    """Positions dont `WalkPathfinder$$GetTileBlockingReasons(tile, unit) & 1` vaut 1 pour CE mover
    -- celles que `WeightCost` facture `10000 - elevation` au lieu de `10 - elevation`.

    Substrat : `tile_effect_type_ids_by_pos` (= `tileMeta.effects[].effectType`, l'`EffectComponent
    +0x58` que le natif compare) croise avec `TILE_MOVEMENT_BLOCKING_EFFECT_TYPES` (les six classes
    d'effet qui s'enregistrent au `MovementComponent` de la tuile, cf. `tile_blocking.py`), moins les
    EXEMPTIONS de trait `StaticBattleRules.Effect$$NotBlockingMovementOfTraits(effectType)` --
    `unit_traits` du `tile_leaf_ctx` est deja une liste d'IDS `UnitTrait`, la meme forme que la table
    d'exemption (Kimm porte `Unstoppable` = 1042, donc AUCUNE Swamp ne la penalise).

    ⚠ RESIDU (herite de `tile_blocking.tile_blocks_entering`) : le natif distingue un bloqueur NEUTRE
    (`blockerId == 0` -> bit 0x1) d'un bloqueur POSE PAR UNE UNITE (-> bit 0x4, qui ne penalise que
    les ennemis du poseur). `tileMeta` ne remonte pas le `blockerId` -> on traite tout effet bloqueur
    comme neutre. Carte absente -> aucune penalite (degradation PERMISSIVE : le chemin est alors
    seulement le plus court, jamais coupe a tort)."""
    by_pos = ctx.get("tile_effect_type_ids_by_pos")
    if not by_pos:
        return set()
    traits = {int(t) for t in (ctx.get("unit_traits") or ())}
    out = set()
    for pos, ids in by_pos.items():
        for et in (ids or ()):
            if int(et) not in TILE_MOVEMENT_BLOCKING_EFFECT_TYPES:
                continue
            if traits & {int(t) for t in not_blocking_movement_of_traits(int(et))}:
                continue                          # `Any(exemptTraits, t => HasTrait(unit, t))`
            out.add((pos[0], pos[1]))
            break
    return out


def path_node_counts(ctx: dict) -> dict:
    """`{(col,row) -> Count}` de `IPathfinders.GetPath(unit, GetMainTile(unit), <pos>, null)` depuis
    l'ORIGINE du mover, memoise sur le dict `ctx` (constant sur toute la decision).

    `self_pos` absent (unite hors plateau) -> `{}` : le natif deref `GetMainTile` et n'a pas de
    chemin -- degradation fidele (`IsNullOrEmpty(path)` -> terme 0)."""
    hit = ctx.get(_CACHE_KEY)
    if hit is not None:
        return hit
    sp = ctx.get("self_pos")
    counts = {} if not sp else get_path_node_counts_by_pos(
        (sp[0], sp[1]),
        neigh_by_pos=ctx.get("neigh_by_pos"),
        walkable_by_pos=ctx.get("walkable_by_pos"),
        elev_by_pos=ctx.get("elev_by_pos"),
        blocking_positions=_blocking_positions(ctx),
        block_entering_positions=_block_entering_positions(ctx))
    try:
        ctx[_CACHE_KEY] = counts
    except Exception:                             # ctx non mutable (mapping fige) -> pas de memo
        pass
    return counts


class ModifiedExoarmourPlaybook:
    """`ModifiedExoarmourPlaybook` (`IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook$$.ctor` :
    ability 0x5f9 = 1529 `ModifiedExoarmour`, passif de `votanChampion` / Kimm -- HERO, injectable au
    pool par `catalog_inject.py --units votanChampion`).

    `IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook$$CalculateMovementUtilityInStepsInternal`
    (signature `methods.tsv` : `(case: UtilityMovementCase, getUtilityVal: Func<String, Int32>) ->
    IEnumerator<Fix64>`) ; corps `IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook.
    u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`, remis en C# depuis le
    decompile :

        int val = 0;
        if (case.Unit != null && !case.StaysOnTile(state)) {
            var path = pathfinders.GetPath(case.Unit,                       // IPathfinders slot 3
                                           EntityExtensions.GetMainTile(case.Unit, state),
                                           case.MovementTile, null);
            if (!CollectionExtensions.IsNullOrEmpty(path))
                val = getUtilityVal("ModifiedExoarmour_LikesMovingPerTile") * path.Count;
        }
        yield return Fix64.op_Implicit(val);

    QUATRE lectures qui font le port, et qu'on ne devine pas :

    1. **`Count` = des NOEUDS, extremites INCLUSES** (`BasePathfinder$$FindPath` ajoute `toTile` PUIS
       remonte le dict parent jusqu'a `fromTile` INCLUS, avant `Reverse`) -> une tuile ADJACENTE vaut
       `5 x 2 = 10`, pas 5. C'est la meme convention que `MinDistanceToClosestEnemyUtility$$
       GetMinDistanceToEnemy`, qui lit le meme `route+0x18` et l'appelle « distance ».
    2. **`StaysOnTile`** (`IdunBattle.AI.Utilities.UtilityMovementCase$$StaysOnTile` =
       `GetMainTile(case.Unit, state) == case.MovementPosition.MainTile`) court-circuite AVANT le
       pathfinding : rester sur place vaut **0**, pas `5 x 1`.
    3. **Le pathfinder n'est PAS le type 1** : le playbook appelle le slot 3 de `IPathfinders`
       (`GetPath(unit, from, to, useTeleporter)`), qui derive le type de l'unite
       (`Pathfinders$$GetPath` -> `IMovementQuery.GetPathfinderTypeForUnit` -> `WalkPathfinder` = 0
       pour une unite non volante sans effet de mouvement special). La feuille
       `MinDistanceToClosestEnemy(17)`, elle, passe le LITTERAL `1` (slot 4) et tombe sur
       `IgnoreTerrainPathfinder`. Les deux pathfinders different sur le cout d'arete ET sur le
       blocage par occupant -> `ctx.pathdist_by_pos` n'est PAS reutilisable ici.
    4. **Aucun gate d'ability** : `TriggeredAbilityPlaybook<T>$$CalculateMovementUtilityInSteps` se
       contente de fabriquer le `Func<string,int>` (= `GetUtilityValue`, qui rend **0** et logge
       quand la cle manque) et d'appeler l'iterateur. Ni cooldown, ni charge, ni `IsAbilityActive`.

    Terme = `5 x (nombre de tuiles du chemin de cout minimal, origine et arrivee comprises)`, et
    **0** sur la tuile d'origine. Sur un board plat il vaut donc `5 x (pas + 1)` : il croit
    strictement avec la distance parcourue et pousse le porteur a s'eloigner.
    """

    ABILITY_ID = TriggeredAbilityType.ModifiedExoarmour                                    # 0x5f9 -- litteral du `..ctor`
    WEIGHT_KEY = "ModifiedExoarmour_LikesMovingPerTile"  # BC (gameconfig vivant) = 5

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        ctx = ctx or {}
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0                                   # `GetUtilityValue` : cle absente -> 0
        sp = ctx.get("self_pos")
        tk = (tile[0], tile[1])
        if sp is None or (sp[0], sp[1]) == tk:
            return 0.0                                   # `case.Unit == null` / `StaysOnTile`
        n = path_node_counts(ctx).get(tk)
        if not n:                                        # `IsNullOrEmpty(path)` -> aucun chemin
            return 0.0
        return float(w) * float(n)
