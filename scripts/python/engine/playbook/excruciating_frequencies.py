"""ExcruciatingFrequenciesPlaybook — attaque COMPARABLE ligne-AoE ciblant une TUILE (id 1197).

`IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` (ComparablePlaybook<0x4ad=1197>,
IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$.ctor). Ability RANGED profil Blast (HitsMultipleMembers) : un rayon de 3 tuiles en ligne
droite depuis le caster dans l'une des 6 directions, qui inflige `1x Blast` a CHAQUE ennemi sur les
tuiles affectees (tooltip + Suppressed). La cible de DECISION est une TUILE (l'aim/direction), PAS une
unite -- comme DarkTalonStrike (mais Comparable : le score = Sigma degat par ennemi, pas un comptage NC).

Ce playbook N'EST PAS pilote par `attackPlans` (les evals natives 1197 ont rankCount=0 : la structure
d'affichage par-unite ne range pas une ability ligne-ciblant-tuile). Il est donc traite par un
GENERATEUR BESPOKE dans `ComparableAbilityGenerator` (comme heal/repair), qui balaie positions x aims.

Structure native (mirror IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions) :
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAttackTargets` = `Enemies(Units(GetAffectedTiles))` : ennemis sur les tuiles de ligne.
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles` =
    `SortReverse(TilesBehindInLine(from=CasterTile@0x168, to=TargetTiles@0x190, settings{1,1},
    Direct(nrOfTiles = const 0x17 = 3)))` : les `nrOfTiles` tuiles en ligne droite depuis le caster a
    travers l'aim, TRONQUEES au 1er echec du gate de tuile (walkable + `|Delta elev| < 2`, cf.
    `_line_tiles` / #124). Geometrie CUBE droite (parite-independante) : `tile_k = caster + k*dir`,
    dir = cube(aim) - cube(caster), k=1..nrOfTiles (l'aim = la 1re tuile, voisine du caster).
  - Par ennemi touche -> `GenerateMultiHitAttackPredictions(base=IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetDamageFormula =
    MinMaxDamage(avg minDmg/maxDmg), hits=IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits = GetNumberConstant(0x2f=nrOfHits=1),
    profile=GetDamageProfile=Blast)`. = exactement le chemin per-cible generique de `prediction.
    make_damage_predictions` (profil Blast + PiercingRatio 15 lus de la config).
  - `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` = Sigma `CalculateUtilityFromDamageEvent` sur tous les
    ennemis touches (+ Tile(7) hors scorer). IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$ShouldExecute : util > 0.

RECONCILIATION LIVE (seed 1357 s7 u79 emperNoiseMarine, board MC1_67) : caster (6,7), movable set restreint
-> la position (4,5) est la seule d'ou une ligne touche 2 ennemis. aim (3,5)=tile 44 -> ligne
[(3,5),(2,4),(1,4)] touche u95@(2,4) + u93@(1,4). DEGAT REEL EXECUTE : u95 -3044, u93 -2912 (2 ennemis
~3000 chacun). Le natif MOVE->(4,5) + caste 1197 sur tile 44 (2 ennemis) plutot que l'attaque normale 69
(1 ennemi). Les lignes 3-ennemis (depuis (3,5)/(2,5)) sont HORS du movable set de u79 -> l'enumeration se
borne a `ctx.reach_nc`. Le moteur ratait car 1197 absent de tout candidat (plan rankCount=0) -> retombait
sur 69->95.

- enumeration = positions `ctx.reach_nc` (movable + origine) x 6 aims voisins (directions unitaires).
- ligne = `_line_tiles(P, aim, nrOfTiles)` ; ennemis touches = ennemis sur ces tuiles.
- degat par ennemi = `prediction.make_damage_predictions(scene, uid, E, 1197, name, attack_pos=P)` (Blast).
- util = Sigma `calculate_utility_from_damage_event` + Tile(7)@P (mirror `calculate_action_utility`).
- candidat emis = {target = tileEntityId(aim), ability = 1197, to = P, pred, full} -> l'agreement compare
  ability==1197 ET target==tileId(aim) ; le score `full` compete dans le bucket Comparable vs l'attaque
  normale (une NonComparable primerait a tort -> 1197 est bien Comparable, il gagne par UTILITE).
"""
from __future__ import annotations

import hexgeo

from engine import battle_query as bq   # get_tiles_behind : mirror UNIQUE de la ligne hex (#117/#124)
from engine.entities.abilities.ability_configuration import AbilityConfiguration
import gameconfig as _gc

_ABILITY_ID = 1197
_ABILITY_NAME = "ExcruciatingFrequencies"


def _n_tiles() -> int:
    """`nrOfTiles` = `GetNumberConstant(0x17)` de la config (= longueur de ligne). Lu de gameconfig
    (pas de hardcode) ; defaut 3 (valeur observee) si absent."""
    try:
        cfg = AbilityConfiguration.from_gameconfig(_ABILITY_NAME, _gc.ability(_ABILITY_NAME))
        n = int((cfg.constants or {}).get("nrOfTiles") or 0) if cfg is not None else 0
        return n if n > 0 else 3
    except Exception:
        return 3


def _line_tiles(caster: tuple, aim: tuple, n: int,
                walkable_by_pos: dict | None = None, elev_by_pos: dict | None = None) -> list:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles`
    = `SortReverse( TilesBehindInLine(from = CasterTile@0x168, to = TargetTiles@0x190,
    settings{+0x10 = 1, +0x11 = 1}, Direct(GetNumberConstant(0x17 = nrOfTiles))) )` — mirror 1:1 via
    `engine.battle_query.get_tiles_behind` (LE mirror partage avec la face COMBAT, #117/#124).

    Geometrie : `aim + k*dir`, k = 0..n-1, `dir = cube(aim) - cube(caster)` (aim = voisine du caster
    -> pas unitaire ; = `caster + k*dir`, k = 1..n). GATE PAR TUILE (#124) : `settings +0x10 = 1`
    active `IsWalkable` **ET** le gate d'ELEVATION `|elev(ref) - elev(tile)| < 2` de
    `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` ; `+0x11 = 1` fait SUIVRE la reference le
    long de la ligne. La reference initiale est la tuile du CASTER (`from`), donc la 1re marche
    testee est `caster -> aim`. La ligne S'ARRETE a la 1re tuile invalide (PREFIXE, pas un filtre) :
    avant #124 la feuille rendait les `n` tuiles inconditionnellement et SUR-ESTIMAIT l'utilite d'un
    rayon traversant une marche >= 2.

    `SortReverse` ne change que l'ORDRE (l'utilite est une SOMME sur les ennemis touches) -> non
    porte ici ; il compterait pour la face COMBAT (consommation du RNG coup par coup)."""
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(walkable_by_pos, elev_by_pos)
    return bq.get_tiles_behind(caster, aim, max_count=n, check_walkable=True, update_reference=True,
                               walkable_at=walkable_at, elevation_at=elevation_at,
                               tile_exists=tile_exists)


def _score(ctx, P: tuple, line_enemies: list):
    """Mirror `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` pour 1197 (Comparable) : Sigma
    `CalculateUtilityFromDamageEvent` sur les ennemis touches (degat Blast per-ennemi) + Tile(7)@P.
    Renvoie (u, u_full) ou None si aucun event de degat (ShouldExecute : util > 0 -> u <= 0 filtre)."""
    from engine.playbook import prediction
    from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
    from engine.utilities.tile import triggered_abilities_attack_utility
    from engine.playbook.base import tile_utility
    name = (ctx.ab_name_by_id.get(_ABILITY_ID) if getattr(ctx, "ab_name_by_id", None) else None) \
        or _ABILITY_NAME
    events = []
    for E in line_enemies:
        events += prediction.make_damage_predictions(ctx.scene, ctx.uid, E, _ABILITY_ID, name,
                                                     attack_pos=P) or []
    if not events:
        return None
    u = 0.0
    for ev in events:
        ua = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(ev.target))
        # #438 : `prediction` = la `DamagePrediction` du case de CET event (`ForDamagePrediction`).
        trig = triggered_abilities_attack_utility(ctx, ctx.uid, _ABILITY_ID, ev.target, P,
                                                  prediction=ev.prediction)
        if trig:
            ua += (-1.0 if ev.friendly else 1.0) * ev.probability * trig
        u += ua
    if u <= 0:
        return None                                  # ShouldExecute : util > 0
    return u, u + tile_utility(ctx, P)


def excruciating_frequencies_candidates(ctx) -> list:
    """Generateur BESPOKE de 1197 (`ComparableAbilityGenerator`) : balaie positions `ctx.reach_nc` x aims
    voisins ; par (position, aim) calcule la ligne, les ennemis touches et l'utilite Blast sommee. Rend
    le MEILLEUR candidat {target=tileId(aim), ability=1197, to, pred, full} (argmax `full`, keep-first sur
    le sweep positions puis aims), ou [] si le caster n'a pas 1197 usable / aucune ligne ne touche d'ennemi."""
    me = ctx.me
    ab = next((a for a in ((me or {}).get("abilities") or [])
               if a.get("id") == _ABILITY_ID and a.get("usable") is not False), None)
    if ab is None or ctx.scene is None or not ctx.tile_id_by_pos:
        return []
    n = _n_tiles()
    epos = set(ctx.epos or [])
    enemy_by_pos = {}
    for e in (ctx.enemies or []):
        p = e.get("pos")
        if p and p.get("col") is not None:
            enemy_by_pos[(p["col"], p["row"])] = e.get("id")
    if not enemy_by_pos:
        return []
    best = None   # (full, u, aim_tile_id, P)
    for P in (ctx.reach_nc or []):
        for aim in hexgeo.neighbors(P[0], P[1]):
            aim_id = ctx.tile_id_by_pos.get(aim)
            if aim_id is None:
                continue                              # aim hors board -> pas de cible-tuile emettable
            line = _line_tiles(P, aim, n,
                               ctx.walkable_by_pos, ctx.elev_by_pos)   # gate d'elevation (#124)
            line_enemies = [enemy_by_pos[t] for t in line if t in epos and t in enemy_by_pos]
            if not line_enemies:
                continue                              # ligne sans ennemi -> aucune prediction (util 0)
            sc = _score(ctx, P, line_enemies)
            if sc is None:
                continue
            u, full = sc
            if best is None or full > best[0]:        # strict > : 1re (position, aim) du max gagne
                best = (full, u, aim_id, P)
    if best is None:
        return []
    full, u, aim_id, P = best
    to = None if P == ctx.origin else P
    if ctx.debug:
        import sys
        print(f"    [dbg 1197 u{ctx.uid}] aimTile={aim_id} to={to} pred={round(u, 1)} full={round(full, 1)}",
              file=sys.stderr)
    return [{"target": aim_id, "ability": _ABILITY_ID, "to": to, "pred": u, "full": full}]
