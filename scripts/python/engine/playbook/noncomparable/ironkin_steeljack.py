"""IronkinSteeljackPlaybook (1219, `votanMemnyr` -- Memnyr) -- face DECISION (#971).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`
(`IdunBattle.AI.Playbook.Loki.IronkinSteeljackPlaybook  112  IdunBattle.AI.Playbook.
NonComparablePlaybook`1`), et NON deduite du ctor : Ghidra etiquette le corps gshared du ctor
`ComparablePlaybook<__Il2CppFullySharedGenericType>$$.ctor` pour les DEUX hierarchies.

REACHABILITE : `data/symbols/<build>/metadata/active_playbook_builders.tsv` ->
`active 1219 IdunBattle.AI.Playbook.Loki.IronkinSteeljackPlaybook` (le dict `+0x68` de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`). Le playbook est ENREGISTRE.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.IronkinSteeljackPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>()                       # ctor SANS borne (cf. plus bas)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        u = GetUtility(caster, entities@+0x10)              # +0x10 = Target = l'entite-TUILE
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition.get_MainTile(),
                                                     entities@+0x10, u))

et `IdunBattle.AI.Playbook.Loki.IronkinSteeljackPlaybook$$GetUtility(caster, summonTile)` :

    pos     = new UnitPosition(summonTile)
    nearest = battleQuery.<slot 0x4a>(caster, Nullable(pos))          # GetNearestEnemy
    if (nearest == null)
        return <Fix64 statics>+0x28                                   # Fix64.Zero
    return Fix64.op_Implicit( -battleQuery.<slot 0x6c>(               # GetDistance
                                  EntityExtensions.GetMainTile(nearest), summonTile) )

=> **utilite = MOINS la distance de la tuile de spawn a l'ennemi le plus proche** : l'argmax est
la tuile libre adjacente la PLUS PROCHE d'un ennemi. Aucune lecture des PV, des traits, ni de la
distance au caster.

LES DEUX SLOTS SONT LUS, PAS DEDUITS d'un nom : `data/symbols/<build>/metadata/
interface_slots.tsv` donne `IBattleQuery 74 GetNearestEnemy 2` (0x4a) et `IBattleQuery 108
GetDistance 2` (0x6c). Les re-deriver au changement de build
(`probe_477r25_slots_autres_interfaces.py --regenerer`).

`<Fix64 statics>+0x28` EST `Fix64.Zero` -- deja etabli et cite par quatre ports
(`playbook/loki_custom.py`, `playbook/resurrection_orb.py`, `services/damage_modifiers.py`,
`noncomparable/stormcaller.py`). Il n'est atteint que si le plateau ne porte AUCUN ennemi.

⚠ CE PLAYBOOK N'A **AUCUNE** BORNE D'UTILITE, ET C'EST LA LECTURE QUI DECIDE DU PORT
----------------------------------------------------------------------------------------
Deux signaux INDEPENDANTS, tous deux LUS :

1. le ctor du Bucket. Waaagh et SporeMineLauncher appellent la surcharge a QUATRE arguments
   `Bucket$$.ctor(this, 0, &Nullable<Fix64>(min), <type>)` ; celui-ci appelle la surcharge a DEUX
   `Bucket$$.ctor(this, <type>)` -- il ne passe aucun `Nullable` ;
2. la classe n'a **pas de `.cctor`** (ni symbole Ghidra, ni ligne dans
   `data/symbols/<build>/frida/methods.tsv`), donc aucun statique de seuil a passer.

Et le gate est celui-ci (`IdunBattle.AI.BucketSystem.Bucket<T>$$AddAction` ->
`FUN_18004ed00`, LU) :

    if (action == null)               return false
    if (!this.minUtility.HasValue)    return true          # <- CETTE branche ici
    return action.utility >= minUtility.Value              # comparaison INCLUSIVE

L'utilite d'Ironkin etant NEGATIVE (`-d`, avec `d >= 1` : la tuile de spawn est libre, donc aucun
ennemi ne s'y trouve), un `MIN_UTILITY` herite de la valeur par defaut `0.0` de
`NonComparablePlaybook` aurait rejete **tous** les candidats, en silence. D'ou `-inf`.

`AddAction` remplace par `Fix64.op_GreaterThan` STRICT -> a utilite EGALE la PREMIERE paire
(position, tuile) enumeree gagne, et `reach_nc` commence par l'ORIGINE.

VOIE D'ENUMERATION -- CIBLE TUILE, RING-1 DU SELECTEUR
-------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor` =
`TargetingOptions(0, <TargetingRange statics>+0x30, 1, 0x1040, 0, 0, 0)` : `TargetIsTile |
TargetTileIsFree`, `onlyAdjacent = RangedBool.True` -- le MEME ctor, octet pour octet, que
`AberrantHypermorphAbility` et `MasterOfTheTutelariesAbility` (deja transcrit par
`engine/runner/abilities/votann.py::IronkinSteeljackAbility.TARGETING_OPTIONS`). La contrainte
« hex adjacent » vient donc du SELECTEUR (`TargetingQuery$$GetTilesInRange` -> slot
`GetAdjacentTiles` -> `IterateAdjacentTiles` = liste STOCKEE du `ConnectivityComponent` puis
`|dElev| < 2`), pas d'un filtre du playbook : la re-projection de l'union sur la position
candidate T EST `bq.is_adjacent(T, ST)`. Chaine detaillee : `GrotTankPlaybook` (#616).

L'ORDRE PAR POSITION EST DERIVABLE, ET IL N'EST PAS CELUI DE L'UNION
--------------------------------------------------------------------
`eligible_target_tiles` rend `(fromHere, union)` : `fromHere` porte l'ORDRE NATIF du selecteur a
la position d'ORIGINE, `union` l'agregat sur toutes les tuiles de move -- et l'ordre de l'union
n'est celui d'AUCUNE position. Or l'utilite ne departage PAS toujours : plusieurs tuiles de spawn
d'une meme position peuvent etre a la MEME distance du plus proche ennemi, et `AddAction` est
alors keep-first. L'ORDRE **EST** la decision, exactement comme pour `CultDemagogue` (#957).

Le port ne se contente donc pas de l'union : pour une position `T`, il enumere les tuiles
eligibles **dans l'ordre de `ctx.neigh_by_pos[T]`**, c'est-a-dire la liste d'adjacence STOCKEE du
`ConnectivityComponent` -- celle-la meme que parcourt la chaine native
`TargetingQuery$$GetTilesInRange` (`onlyAdjacent`) -> slot `GetAdjacentTiles` ->
`BattleQuery$$IterateAdjacentTiles`, dont `TargetingQuery$$GetValidTargets` preserve l'ordre dans
son `OrderedSet`. C'est le MEME substrat que celui qu'`AdjacentTilesSelector$$Select` consomme
cote COMBAT (`engine/entities/selectors/tiles.py::AdjacentTiles`, « ORDRE (R28-1) »).

MESURE (#971, board `MC1_67`, seed 4242, oracle `ncEvaluate`, 13 positions) : l'ordre de l'UNION
donne **11 classes natives contre 10 portees** -- les positions `(0,1)` et `(1,1)` retiennent la
MEME tuile cote port et DEUX tuiles distinctes cote natif, toutes deux a utilite `-8`. L'ordre du
voisinage stocke referme cet ecart. `neigh_by_pos` absent (canal muet) -> repli sur l'ordre de
l'union, et le port le DIT plutot que de rendre un ordre invente.

RESIDU NOMME `#971-r1` : `GetNearestEnemy` est mirrore ICI pour la TROISIEME fois
(`noncomparable/alpha_warrior.py::_nearest_enemy`, ancre sur la tuile de spawn, rend `(id, pos)` ;
`noncomparable/master_of_the_tutelaries.py::_nearest_enemy_tile`, ancre sur l'ORIGINE, rend une
tuile). Les trois portent le meme corps natif ; les converger sur un foyer unique
(`engine/battle_query.py`, ou vivent deja `are_entities_adjacent` / `adjacent_addable_count`)
est une tranche a part -- les trois signatures different, donc le deplacement demande de
re-valider les deux appelants existants.
"""
from __future__ import annotations

import hexgeo

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, eligible_target_tiles


class IronkinSteeljackPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.IronkinSteeljackPlaybook$$EvaluateNonComparable` (0x4c3 = 1219).

    Utilite = `-GetDistance(GetMainTile(GetNearestEnemy(caster, <tuile de spawn>)), <tuile de
    spawn>)`, ou `Fix64.Zero` si le plateau ne porte aucun ennemi."""

    ABILITY_ID = int(ActiveAbilityType.IronkinSteeljack)   # 0x4c3 = 1219
    #: PAS de `.cctor`, PAS de `Nullable` au ctor du Bucket -> `minUtility.HasValue == false` ->
    #: `AddAction` accepte TOUT. `-inf` est la transcription de cette absence (cf. l'en-tete) ;
    #: le `0.0` par defaut de la base aurait rejete l'integralite des candidats, l'utilite etant
    #: negative par construction.
    MIN_UTILITY = float("-inf")
    #: 1219 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170 des 258 valeurs de l'enum)
    #: -> tier `AbilityPriority.Normal`.
    PRIORITY = 0

    def _nearest_enemy(self, ctx: NCContext, frm: tuple):
        """`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position)` -- la
        `position` fournie REMPLACE celle du caster (`if (position.HasValue) tilesA = position.Value
        else tilesA = GetUnitPosition(caster)`), donc les distances sont mesurees DEPUIS LA TUILE DE
        SPAWN :

            best = null ; bestDist = int.MaxValue ; bestAdj = false
            foreach u in GetAllAliveUnits(null):
                if (!UnitExtensions.IsEnemy(caster, u, state))  continue
                if (UnitExtensions.IsIrrelevantObject(u))       continue
                d   = GetDistance(tilesA, u) ; adj = AreEntitiesAdjacent(tilesA, u)
                if (d < bestDist || (adj && !bestAdj)) { best = u ; bestDist = d ; bestAdj = adj }
            return best

        Le tie-break n'est PAS un simple `min` : un candidat ADJACENT evince un candidat non
        adjacent meme a distance EGALE ou INFERIEURE. Le port le transcrit tel quel plutot que de
        le collapser en `min`, parce que l'adjacence native est la liste STOCKEE
        (`bq.are_entities_adjacent` -> `MovementUtil$$AreTilesAdjacent`, court-circuit d'identite
        + porte `|dElev| < 2`) et non la distance hex : rien ne garantit qu'un voisin stocke soit
        a distance 1.

        RESIDUS NOMMES, les MEMES que les deux mirrors freres : `IsIrrelevantObject` n'est pas
        porte (`ctx.epos` ne publie pas le trait `Object`) ; le natif compare des EMPREINTES
        (`GetTiles(u)`) la ou le port compare des tuiles principales ; l'ordre d'enumeration natif
        (`GetAllAliveUnits`) est approxime par celui de `ctx.epos` (tie residuel)."""
        neigh = bq.neigh_map(ctx)
        best = None                      # (pos, dist, adj)
        for p in (ctx.epos or []):
            q = (p[0], p[1])
            d = hexgeo.distance(frm, q)
            adj = bq.are_entities_adjacent(frm, q, ctx.elev_by_pos, neigh)
            if best is None or d < best[1] or (adj and not best[2]):
                best = (q, d, adj)
        return None if best is None else best[0]

    def _tiles_in_native_order(self, ctx: NCContext, T: tuple, from_here: list, union: list,
                               eligibles: set, neigh) -> list:
        """Les tuiles de spawn eligibles DEPUIS `T`, dans l'ORDRE que le natif enumere.

        A l'ORIGINE : `fromHere`, qui EST la reponse par-position du RPC -- rien a deriver.
        Ailleurs : l'ordre de `ctx.neigh_by_pos[T]` (liste d'adjacence STOCKEE), restreint aux
        tuiles que le RPC declare eligibles. C'est la chaine `GetTilesInRange` (`onlyAdjacent`) ->
        `GetAdjacentTiles` -> `IterateAdjacentTiles`, dont `GetValidTargets` preserve l'ordre.

        Canal `neigh_by_pos` MUET -> repli sur l'ordre de l'union, NOMME : on ne fabrique pas un
        ordre, on dit qu'on ne l'a pas."""
        if T == ctx.origin and from_here:
            return list(from_here)
        ring = (ctx.neigh_by_pos or {}).get((T[0], T[1]))
        if not ring:
            return list(union)
        ordered = [p for p in ((p[0], p[1]) for p in ring) if p in eligibles]
        # Toute tuile eligible ADJACENTE que la liste stockee ne porte pas resterait invisible :
        # on la remet EN QUEUE plutot que de la perdre (le natif, lui, ne l'aurait pas vue -- mais
        # une perte silencieuse serait pire qu'un ordre de queue explicite).
        reste = [p for p in union if p in eligibles and p not in ordered]
        return ordered + reste

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror du sweep natif : positions candidates (origine d'abord) x tuiles de spawn ring-1.

        Le natif appelle `EvaluateNonComparable` UNE FOIS PAR POSITION candidate, avec
        `casterPosition` ; a l'interieur, `GetEligibleTargetsSelectable(caster,
        casterPosition.MainTile)` re-interroge `IBattleQuery` slot 0x42 = `GetValidTargets(caster,
        UnitPosition(P), abilityType)` -- donc l'ensemble des tuiles de spawn est PAR POSITION. Le
        RPC n'ayant de vue par-position que pour l'origine (`fromHere`), les autres positions
        lisent l'union RE-PROJETEE par le predicat du selecteur (`is_adjacent`), comme
        `GrotTankPlaybook` et `MasterOfTheTutelariesPlaybook`.

        CIBLE EMISE = la TUILE DE SPAWN (`ctx.tile_id_by_pos`) : c'est l'`entities@+0x10` que
        `GenerateAction` recoit, et le `targetId` que le cast natif attend (`TargetIsTile`)."""
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        if not from_here and not union:
            return []
        neigh = bq.neigh_map(ctx)
        eligibles = set(from_here) | set(union)
        best = None                       # (tuile de spawn ST, position T, utilite)
        for T in (ctx.reach_nc or []):    # origine d'abord (Bucket keep-first au tie)
            tiles = self._tiles_in_native_order(ctx, T, from_here, union, eligibles, neigh)
            for ST in tiles:
                if not bq.is_adjacent(T, ST, ctx.elev_by_pos, neigh):
                    continue              # spawn = hex ADJACENT a T, au sens du SELECTEUR
                near = self._nearest_enemy(ctx, ST)
                # `nearest == null` -> `Fix64.Zero` ; sinon `-GetDistance(nearest, ST)`.
                u = 0.0 if near is None else -float(hexgeo.distance(near, ST))
                if best is None or u > best[2]:   # strict > : 1re paire (T, ST) du max gagne
                    best = (ST, T, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        st, t, u = best
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] IronkinSteeljack ST=%s T=%s u=%s"
                  % (ctx.uid, st, t, u), file=sys.stderr)
        tid = (ctx.tile_id_by_pos or {}).get(st)
        return [{"target": (tid if tid is not None else st), "ability": self.ABILITY_ID,
                 "to": (t if t != ctx.origin else None), "pred": u}]
