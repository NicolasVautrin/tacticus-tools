"""Primitives IBattleQuery — requêtes spatiales sur l'état de bataille (une fonction par slot natif).

Mirror des slots `IBattleQuery` que le playbook natif appelle pour ses heuristiques NonComparable :
  - `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies`  (slot 126, `FUN_180007c20(0x7e,...)`)
  - `GetAdjacentFriends`             (slot 128)
Ces méthodes construisent leurs voisins via `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
puis `GetUnitsOnTiles`. On porte le comptage (ce que les feuilles consomment : `.Count`).
"""
from __future__ import annotations

import hexgeo


def is_adjacent(tile: tuple, pos: tuple, elev_by_pos: dict | None = None) -> bool:
    """`pos` est-il sur une tuile ADJACENTE à `tile` selon l'adjacence NATIVE ?

    Primitive d'adjacence COMMUNE à tous les usages du playbook : les comptages `GetAdjacent*`
    (slots 124/126/128) ET `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` (= `AdjacentTiles` puis `Units`,
    ciblage des heals `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets`). Les deux passent par `IterateAdjacentTiles`, donc
    la MÊME porte d'élévation doit s'appliquer.

    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` applique, APRÈS les filtres terrain optionnels
    (temporary/walkable/emptyOrSteppable), un gate INCONDITIONNEL :
    `iVar4 = abs(elev(tile) - elev(voisin)) ; if (iVar4 < 2) yield`. Pour un usage sur unités
    (comptage OU somme de poids), les filtres terrain ne retirent jamais une tuile occupée (une unité
    y stationne) → seule l'élévation discrimine ; le gate est symétrique (abs). elev = champ
    `tile→[0x20]→[0x18]` (= tileMeta.elevation). `elev_by_pos = {(col,row): elev}` : fourni ET les 2
    élévations connues -> gate `|Δ| < 2` ; sinon on retient (fallback hexgeo pur = dégradation sûre)."""
    if hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) != 1:
        return False
    if elev_by_pos is not None:
        te = elev_by_pos.get((tile[0], tile[1]))
        pe = elev_by_pos.get((pos[0], pos[1]))
        if te is not None and pe is not None and abs(te - pe) >= 2:
            return False   # voisin hors portée d'élévation (|Δelev| >= 2) — natif l'exclut
    return True


def count_adjacent(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`GetAdjacentEnemies/Friends(tile).Count` — nombre d'unités de `positions` sur une tuile
    ADJACENTE à `tile`, filtrées par la porte d'élévation native (cf. `is_adjacent`)."""
    return sum(1 for p in (positions or []) if is_adjacent(tile, p, elev_by_pos))


def in_arc(tile: tuple, pos: tuple, elev_by_pos: dict | None = None) -> bool:
    """`pos` est-il dans l'ARC de `tile` (ring-1 UNION ring-2) ? ring-1 = `is_adjacent` (dist hex 1,
    porte d'élévation `|Δelev| < 2`) ; ring-2 = dist hex EXACTEMENT 2 (`Unobscured` PASSE-TOUT v1
    pour ce prédicat d'ÉLIGIBILITÉ, non exercé par les seeds). Prédicat PARTAGÉ par
    `count_enemies_in_arc` (gate d'éligibilité par-position) et `enemies_in_arc` (cible émise)."""
    if is_adjacent(tile, pos, elev_by_pos):                              # ring-1 (dist 1, élévation-gaté)
        return True
    return hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) == 2    # ring-2 (dist 2, Unobscured passe-tout)


def count_enemies_in_arc(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(unit, MainTile(T))` (compte) — nombre
    d'unités de `positions` (ennemis) dans l'ARC de `tile` = ring-1 UNION ring-2 (`in_arc`), l'ensemble
    des CIBLES ÉLIGIBLES depuis la position T. C'est le set ancré à T que le natif énumère pour
    `GenerateAction(pos, eligible_target, util)` : si ce set est VIDE à T, AUCUNE action n'est générée
    (bucket vide) quelle que soit l'utilité — gate PROUVÉ live (probe_49x_realanchor phase B, C1_25 :
    23/23 positions, les 6 vides = exactement celles sans ennemi à dist <= 2 de T).
    ⚠ CASE-49x (2026-07-21) : ce compte n'est PAS l'utilité Gauntlets. L'utilité =
    `|ring1(T) ∪ surrounding_enemies(TUILE RÉELLE)|` (cf. `surrounding_enemies` + le playbook) —
    la conclusion antérieure « ring-2 mort » (case-49 §2bis) confondait les deux ancrages."""
    return sum(1 for p in (positions or []) if in_arc(tile, p, elev_by_pos))


def eligible_targets_count(tile: tuple, positions: list,
                           elev_by_pos: dict | None = None) -> int:
    """`BasePlaybook.GetEligibleTargetsEntities(unit, MainTile(T))` (via `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`) — nombre de CIBLES ÉLIGIBLES depuis la position T = ennemis à dist hex <= 2 de T,
    **SANS porte d'élévation au ring-1** : PROUVÉ live (probe_49x phase B, C1_25 : T=(0,2) elev 4,
    ennemi (1,3) elev 2 adjacent -> |Δelev|=2 exclurait via IterateAdjacentTiles, or le natif GÉNÈRE
    une action -> l'éligibilité n'utilise pas cette porte, contrairement au terme utilité
    `AdjacentTiles`). Si 0 : la boucle `GenerateAction` n'est jamais entrée -> bucket VIDE à T quelle
    que soit l'utilité (gate par-position, 23/23 sur E1-repro). v1 FLAG : dist-2 sans filtre
    Unobscured (non exercé par les mesures ; cf. `is_target_tile_obscured` si un cas le falsifie)."""
    tk = (tile[0], tile[1])
    return sum(1 for p in (positions or [])
               if hexgeo.distance(tk, (p[0], p[1])) <= 2)


def is_target_tile_obscured(frm: tuple, to: tuple, elev_by_pos: dict | None = None) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$IsTargetTileObscured` -> `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain` (mask 6 : élévation bit 2 + murs bit 4 — pas d'IndirectFire ici), TERRAIN uniquement,
    restreint à dist hex == 2 (le seul cas où le playbook NC l'exerce ; à dist 1 le natif ne teste
    rien : `2 < count` faux -> jamais obscurci ; dist > 2 hors périmètre Gauntlets).

    Élévation (`DetermineBlockingTiles IdunBattle.Core.Services.MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles|40_0`, seuil closure[3]=2) : la ligne from->to (dist 2,
    count=3) teste l'UNIQUE tuile intermédiaire idx=1 (== count-2) contre elev(from) PUIS elev(to) ;
    bloque si `elev(mid) - elevRef >= 2` pour l'UNE des deux réfs. Fat-line (lignes A/B ±eps ->
    candidates différentes = les 2 voisins communs) : bloque SSI les DEUX candidates passent le
    seuil pour la MÊME réf (`bVar1 & bVar2`). Mids offline = voisins communs hexgeo (bit-exact
    cube-line pour dist 2 : trajet droit -> 1 mid ; diagonal -> midpoint sur l'arête -> ±eps
    départage les 2 candidates). LIMITES v1 (flaggées) : murs (bit 4) non modélisés (aucun
    `wall_by_pos` offline ; aucun board d'agreement n'a de mur en zone jouable) ; nudge eps natif
    (FloatCube @DAT_1832593f8+0xb8) supposé départager les 2 candidates du cas diagonal (si les
    lignes A/B tombaient sur la MÊME candidate, le natif bloquerait sur elle seule)."""
    fk, tk = (frm[0], frm[1]), (to[0], to[1])
    if hexgeo.distance(fk, tk) != 2 or not elev_by_pos:
        return False
    ef, et = elev_by_pos.get(fk), elev_by_pos.get(tk)
    if ef is None or et is None:
        return False
    mids = [p for p in hexgeo.neighbors(*fk) if hexgeo.distance((p[0], p[1]), tk) == 1]
    mids = [elev_by_pos[p] for p in mids if p in elev_by_pos]   # GetTileAt null -> pas bloquant
    if not mids:
        return False
    if len(mids) == 1:                                          # ligne DROITE : 1 seul mid
        return (mids[0] - ef >= 2) or (mids[0] - et >= 2)
    blk_f = all(m - ef >= 2 for m in mids)                      # fat-line : ET des 2 candidates
    blk_t = all(m - et >= 2 for m in mids)
    return blk_f or blk_t


def surrounding_enemies(origin: tuple, positions: list,
                        elev_by_pos: dict | None = None) -> set:
    """`Unobscured(DSLFactory.SurroundingEnemies(Caster, r=2))` — le terme « surrounding » de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector`, ancré à la TUILE RÉELLE
    du caster (`Caster@+0x160` = CasterSelector -> ENTITÉ -> `GetMainTile` dans
    `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` — PAS la tuile balayée du contexte).

    Chaîne native (décompilée, case-49x) : `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies` =
    `Enemies(Units(SurroundingTiles(caster, r=2) - Tiles(caster)))` ; `SurroundingTiles` -> slot
    0x65 = `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` -> `IdunBattle.Core.Services.TileQuery$$IterateSurroundingTiles` (cube-loop DISQUE dist <= 2 — pas le ring exact) avec flags MESURÉS au call-site
    (IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor <- SurroundingTiles(query, caster, 1, r=2, 0, 0)) :
      - requireEmptyOrSteppable = OFF (p4=0) -> les tuiles OCCUPÉES par des ennemis PASSENT
        (la conclusion case-49 §2bis « empty-only / ring-2 mort » était FAUSSE) ;
      - filtre restant = `IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, src, 1, 0)` = non-mur +
        walkable, SANS test d'élévation ni d'occupation (une unité stationne sur du walkable -> no-op
        offline) ; PAS de porte |Δelev| ici (contrairement au ring-1 `IterateAdjacentTiles`) ;
      - includeSelf = ON (p7=1) puis `- Tiles(caster)` au niveau DSL -> exclure `origin`.
    `IdunBattleLogic.Entities.DSLFactory$$Unobscured` -> `IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` depuis la tuile
    RÉELLE : dist 1 jamais obscurci, dist 2 via `is_target_tile_obscured`.
    Retour : set de positions (== unités : 1 unité/tuile) — l'union avec ring1(T) est dédupliquée
    par le `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits` du playbook.
    VALIDÉ LIVE (probe_49x_realanchor, 2026-07-21) : craft-P MC1_67 plat (disque réel compte : util
    3 = 1 ring1(T) + 2 dist-2-du-réel) ; craft-N (dist-2-de-T ne compte PAS) ; E1-repro C1_25
    (17/23 positions util=2 = les 2 ennemis à dist 2 du réel, indépendant de T)."""
    ok = (origin[0], origin[1])
    out = set()
    for p in (positions or []):
        pk = (p[0], p[1])
        if pk == ok:
            continue
        d = hexgeo.distance(ok, pk)
        if d > 2:
            continue
        if d == 2 and is_target_tile_obscured(ok, pk, elev_by_pos):
            continue
        out.add(pk)
    return out


def iterate_surrounding_tiles_order_key(pos: tuple) -> tuple:
    """Clé d'ORDRE d'énumération de `TileQuery.IterateSurroundingTiles` (`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`) —
    le tie-break NATIF de cible à utilité égale au sein d'une position (#57g, 12345 s15).

    Le natif énumère le disque par triple boucle cube ASCENDANTE : `for x in cx-R..cx+R:
    for y in cy-R..cy+R: for z in cz-R..cz+R: if x+y+z==0 -> yield` — pour (x,y) donnés un seul z
    matche, donc l'ordre = LEXICOGRAPHIQUE (cube.x, cube.y) CROISSANT des tuiles émises ; le centre ne
    fait que borner le disque, il ne change PAS l'ordre relatif de deux tuiles. Cet ordre survit à toute
    la chaîne de ciblage (chaque étage filtre en préservant l'ordre via OrderedSet/List.Remove) :
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` (argmax cibles STRICT `op_GreaterThan` -> PREMIÈRE
    énumérée gagne au tie) <- `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` (List + Remove
    prédicat) <- `IdunBattle.Core.Services.AttackQuery$$GetValidTargetsWithCache` <- `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` (itère les possibles, OrderedSet.Add si valide) <- `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` <- `IdunBattle.Core.Services.TargetingQuery$$GetUnitsInRange` (slot 0x76) <- `IdunBattle.Core.Services.BattleQuery$$GetUnitsAtDistance` (tuiles du ring -> GetUnit, ordre préservé) <- `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance`
    (filtre dist==R, ordre préservé) <- `GetSurroundingTiles` -> l'itérateur ci-dessus.

    Champs cube natifs (0,1,2) == (x,y,z) `hexgeo.to_cube` : `IdunBattle.Utils.Hex.CubeCoordinate$$ToAxialCoordinate` (field3==0) = inverse exact de `to_cube` (col=x ; row=z+(x+(x&1))//2). Limites :
    cible multi-tuiles = rang de sa première tuile émise (non exercé) ; l'empilement de rings pour
    range>1 (ordre inter-distances) est non lu — le tie s15 est mêlée R=1 (un seul ring)."""
    x, y, _z = hexgeo.to_cube(pos[0], pos[1])
    return (x, y)


def enemies_in_arc(tile: tuple, enemies: list, elev_by_pos: dict | None = None) -> list:
    """Ennemis (unités decisionView `{id, pos:{col,row}}`) dans l'ARC de `tile` = ring-1 UNION ring-2
    (`in_arc`), DANS L'ORDRE d'énumération de `enemies`. Fallback de `gauntlets_target` sans neighbours."""
    out = []
    for e in (enemies or []):
        p = e.get("pos") if isinstance(e, dict) else None
        if p and p.get("col") is not None and in_arc(tile, (p["col"], p["row"]), elev_by_pos):
            out.append(e)
    return out


def can_add_unit(pos: tuple, walkable_by_pos: dict | None = None,
                 occupied: set | None = None) -> bool:
    """`IdunBattle.Entities.TileExtensions$$CanAddUnit` (prédicat OFFLINE, args du call Hammer arg3=1/arg4=0/arg5=false).

    Le natif (décodé re-expert #116) réduit, pour ces args, à : la tuile est une tuile de board RÉELLE
    placeable (walkable, non-wall) ET VIDE (`IdunBattle.Entities.Components.TileContentComponent$$IsEmpty` = pas de contenu
    unité). Offline : `walkable_by_pos[pos]` (= `BattleQuery.IsWalkableTile` = `TileExtensions.IsWalkable`,
    qui folds déjà isWall, cf. rpc-board.ts) ET `pos ∉ occupied` (occupation LIVE = TOUTES les unités
    vivantes, lue FRAÎCHE via epos/fpos/origine — PAS le `occupantUnitId` du boardGraph caché = périmé).
    LIMITATION v1 (flaggée par verdict RE + validator FEU VERT) : (a) co-location trait 0x1b — arg3=1
    admet un occupant trait-27 pass-through -> ici une tuile occupée = fail (borne INF, corner négligeable) ;
    (b) les flags runtime `tile[4]+0x40` (bloqué) / `+0x2c` (réservé) ne sont modélisés QUE si `walkable`
    les folds (HYPOTHÈSE : `walkable==false` couvre `+0x40` ; une tuile walkable-mais-réservée serait
    sur-comptée) ; (c) le filtre IsTemporary de l'itérateur natif `GetAdjacentTiles` n'est PAS appliqué
    dans le call Hammer — RE #118 RÉSOLU (non-issue) : le call slot-78 passe
    `GetAdjacentTiles(unit, 1, 1, 1)` (IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable) [RE ctors #148 : param3=requireEmptyOrSteppable,
    param4=requireWalkable, param5=allowTemporary (polarite inversee : 1=inclure)] ;
    les 3 bools transitent `<IterateAdjacentTiles>d__94 IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__94$$MoveNext` (+0x40/+0x42/+0x44) ->
    `TileQuery.<>d__8 IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Le gate temporary y est `(field != 0) || !IsTemporary(tile)`, alimenté
    par param5=allowTemporary : param5=1 -> court-circuite VRAI -> tuiles temporaires ACTIVES INCLUSES par le
    natif (comme par le port -> aucune exclusion à ajouter). (Le call jumeau `MovementQuery.IsAdjacent` passe
    (0,1,1) = param3=0 inclut les occupées + param5=1 inclut les temporaires : occupance-independant, adapté à
    un test d'adjacence.) `is_temporary_by_pos` reste hors de ce chemin (légitimement utilisé ailleurs : TemporaryTileUtility)."""
    if occupied is not None and (pos[0], pos[1]) in occupied:
        return False
    if not walkable_by_pos:
        return True   # pas de donnée board (fallback pré-plumbing) -> permissif (borne SUP)
    return bool(walkable_by_pos.get((pos[0], pos[1]), False))   # tuile absente = hors-board -> non placeable


def can_use_ability(unit: dict, ability: dict) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$CanUseAbility` — gate d'USABILITE d'une ability (stun/taunt).

    Le natif enchaine : (1) l'unite possede l'ability (slot itf 0x14) ; (2) un bool
    d'interface (slot 0x13) doit etre FAUX — le blocage par effet de la famille
    `CantUseAbilityEffect` : 26 `Taunted_CantUseAbility`, 1165 `Stunned_CantUseAbility`
    (frida/hooks/data/effect-type-names.ts) ; (3) `GetInvalidCasterReason` valide.
    Offline : (1) et (3) sont deja couverts par l'enumeration decisionView
    (`usable`/`disabled`), MAIS le capteur `usable` lit l'entree ActiveAbility et
    IGNORE les effets -> ce mirror porte le maillon (2), le seul manquant.
    L'attaque NORMALE (kind 'normal') n'est PAS bloquee : vecu 777 s15 (u83 stunne
    par 1183 attaque encore 69->87) + wiki §Stunned (« bloque UNIQUEMENT les
    actives », valide live seed 97000). Match par SUFFIXE de nom `_CantUseAbility`
    = proxy offline du check par CLASSE d'effet (couvre les 2 membres connus et
    tout futur membre de la famille) ; les effets decisionView sont deja
    IsActive-filtres (on ignore `remaining`)."""
    if (ability or {}).get("kind") == "normal":
        return True
    for e in (unit or {}).get("effects") or []:
        if str(e.get("name") or "").endswith("_CantUseAbility"):
            return False
    return True


def adjacent_addable_count(tile: tuple, neigh_by_pos: dict | None,
                           walkable_by_pos: dict | None, occupied: set | None,
                           elev_by_pos: dict | None = None) -> int:
    """`|{ n ∈ GetAdjacentTiles(unit@tile) : CanAddUnit(n) }|` — nombre de voisins ring-1 de `tile` où
    une unité peut être placée. `GetAdjacentTiles` = IBattleQuery slot 0x4e (IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles ; prouvé
    re-expert #116 via `IdunBattle.Core.Services.MovementQuery$$IsAdjacent` + le slot-map du décorateur
    RecordedSimulationRequestsBattleQuery) -> `IterateAdjacentTiles` -> voisins `boardGraph.neighbours`
    avec la MÊME porte d'élévation `|Δelev| < 2` que `is_adjacent` (#45). Filtre chaque voisin par
    `can_add_unit`. Utilisé par `HammerOfWrathPlaybook` (+5/voisin, #116). Le call Hammer passe `(1,1,1)` =
    param3=requireEmptyOrSteppable, param4=requireWalkable, param5=allowTemporary (mapping RE via les CTORs
    des itérateurs #148 ; TileQuery inverse l'ordre des champs). Effet : temporaires INCLUS (param5=1, cf.
    `can_add_unit` flag c) ; requireWalkable + requireEmptyOrSteppable subsumés par `can_add_unit` (walkable +
    empty ; empty ⊂ emptyOrSteppable -> l'intersection GetAdjacent ∩ CanAddUnit = {walkable, empty} = ce que le
    port compte -> agree). Sans `neigh_by_pos` (offline
    pur) : fallback `hexgeo.neighbors` (dist-1, même porte d'élévation via `is_adjacent`)."""
    tkey = (tile[0], tile[1])
    neigh = (neigh_by_pos or {}).get(tkey)
    if neigh is None:
        neigh = list(hexgeo.neighbors(tile[0], tile[1]))   # fallback (ordre non natif, mais compte identique)
    return sum(1 for p in neigh
               if is_adjacent(tile, p, elev_by_pos)          # porte |Δelev|<2 (IterateAdjacentTiles, #45)
               and can_add_unit(p, walkable_by_pos, occupied))


def gauntlets_target(tile: tuple, enemies: list, neigh_by_pos: dict | None = None,
                     elev_by_pos: dict | None = None):
    """Id de la CIBLE émise par `IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable`.

    Le natif boucle sur `GetEligibleTargetsSelectable(caster, MainTile)` et `GenerateAction(pos,
    eligible_target, Fix64(count))` : 1 action / eligible target, MÊME utilité (arc-count, tuile-only)
    -> `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` garde le PREMIER à égalité (remplace SSI `op_GreaterThan` strict).
    L'énumération des eligible targets est INVERSÉE (`DSLFactory.Tiles`=`SortReverseSelector IdunBattleLogic.Entities.DSLFactory$$Tiles`)
    -> la cible = 1er ennemi ring-1 dans l'ordre `boardGraph.neighbours` (= `GetAdjacentTiles` natif)
    **INVERSÉ**, sinon ring-2. VALIDÉ LIVE (#117 : caster@(3,5), ring-1 fwd [80,114,78,118] -> inversé ->
    118 = cible native EXACTE).

    `enemies` = unités `{id, pos:{col,row}}` ; `neigh_by_pos` = {(col,row): [voisins ordre natif]}
    (boardGraph, id résolus -> pos). Porte d'élévation `|Δelev|<2` sur ring-1 (comme l'arc ; non validée
    sur terrain à élévation -> assomption documentée). Sans `neigh_by_pos` (offline pur) : fallback = 1er
    ennemi de l'arc dans l'ordre `enemies` (ordre natif indisponible). Ring-2 (dist 2) : ordre exact non
    validé -> dernier (miroir de l'inversion). None si aucun ennemi dans l'arc."""
    if not enemies:
        return None
    pos2e = {(e["pos"]["col"], e["pos"]["row"]): e for e in enemies
             if isinstance(e, dict) and e.get("pos") and e["pos"].get("col") is not None}
    neigh = (neigh_by_pos or {}).get((tile[0], tile[1]))
    if neigh:
        for p in reversed(neigh):                    # ring-1, ordre natif INVERSÉ
            e = pos2e.get((p[0], p[1]))
            if e is None:
                continue
            if elev_by_pos is not None:              # p est un voisin natif -> adjacent ; seul l'élévation filtre
                te, pe = elev_by_pos.get((tile[0], tile[1])), elev_by_pos.get((p[0], p[1]))
                if te is not None and pe is not None and abs(te - pe) >= 2:
                    continue
            return e.get("id")
        # aucun ennemi ring-1 -> ring-2 (dist hex 2) ; dernier (miroir inversion), ordre exact non validé.
        ring2 = [e for (pp, e) in pos2e.items() if hexgeo.distance((tile[0], tile[1]), pp) == 2]
        return ring2[-1].get("id") if ring2 else None
    arc = enemies_in_arc(tile, enemies, elev_by_pos)  # fallback offline (ordre natif indisponible)
    return arc[0].get("id") if arc else None
