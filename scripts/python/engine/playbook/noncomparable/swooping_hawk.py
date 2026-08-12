"""SwoopingHawkPlaybook -- face DECISION de `1064 Loki_SwoopingHawk` (`eldarAutarch`). #978.

La face COMBAT est portee et confrontee (`engine/runner/abilities/loki/dive_attack.py` +
`aeldari.py`, #502 / #507). Ce module porte la face DECISION, et il ferme au passage le RESIDU
NOMME de `dive_attack.py` : « `GetTargetUnitsSelector()` N'EST PAS porte ici : c'est l'accesseur de
la face PREDICTION/UI [...] Residu nomme, commun aux deux heritieres. » -- c'est exactement ce que
le playbook appelle.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.AI.Playbook.Loki.SwoopingHawkPlaybook` -> `IdunBattle.AI.Playbook.NonComparablePlaybook`1`.
Le `.ctor` decompile NOMME `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x428)`
-- corps gshared trivial DEDUPLIQUE, donc mislabele.

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` :
`active 1064 -> ...SwoopingHawkPlaybook`.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.ai import cast_positions as CP        # FORME B (liaison de MODULE) : carte
#                                                 position x cible, foyer #350-r3a-r4.
from engine.entities.active_ability_type import ActiveAbilityType

import engine.playbook.noncomparable._targets as TGT              # FORME B, ABSOLU (#962)
from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class SwoopingHawkPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SwoopingHawkPlaybook$$EvaluateNonComparable` (0x428 = 1064).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>( 0, Nullable(Fix64(1)) )       # construit INLINE (cf. plus bas)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition.get_MainTile()):
            sel  = <SwoopingHawkAbility>$$GetTargetUnitsSelector(this.ability@+0x68)
            lst  = sel.<ITargetsSelector slot 0 = Select>(entities)
            n    = lst.<ICollection get_Count>
            util = Fix64(n - 1)
            bucket.AddAction( GenerateAction(casterPosition, entities.Target@+0x10, util) )

    Soit : **(nombre d'ennemis que la vague traverserait) MOINS UN**. Avec `MIN_UTILITY = 1`, il
    faut donc au moins **3** ennemis alignes pour que l'ability soit proposee (`n - 1 >= 1` exige
    `n >= 2`... et la cible elle-meme compte dans `n`, donc `n >= 2` = la cible **plus** un
    second). Le `-1` neutralise exactement la cible visee : le playbook ne paie que les ennemis
    SUPPLEMENTAIRES que l'alignement offre.

    ⚠ PAS DE `.cctor` POUR CETTE CLASSE, ET CE N'EST PAS UNE ABSENCE DE BORNE. Les quatre autres
    playbooks de la tranche lisent leur `MIN_UTILITY` dans un champ statique pose par un `.cctor` ;
    ici `Fix64.op_Implicit(1)` est calcule **INLINE** juste avant le `Nullable<Fix64>..ctor` du
    Bucket. La borne vaut donc `1` comme les autres -- mais un recensement « ce playbook n'a pas de
    `.cctor` donc pas de `MIN_UTILITY` » se tromperait, et c'est le contraste avec
    `EarlyWarningOverridePlaybook`, ou le `.cctor` EXISTE et n'est lu par AUCUN des deux arguments
    du Bucket (residu `#433-r4-r2-r3`). Le discriminant est le SITE DE LECTURE, pas la presence du
    `.cctor`.

    ⚠ LE SELECTEUR EST EVALUE PAR CIBLE (piege #957, sens DIRECT). `GetTargetUnitsSelector()` est
    appele DANS la boucle et son `Select(entities)` recoit le contexte de CHAQUE cible -- l'arbre
    depend de `Target`, donc le terme n'est PAS constant.

    L'ARBRE, LU (Ghidra le nomme d'apres la BASE, `DiveAttackAbilityBase`)
    ----------------------------------------------------------------------
        GetTargetUnitsSelector() = Enemies( caster@+0x48,
                                            Units( GetTargetTilesSelector(), unique: 1, 3 ),
                                            3 )
        GetTargetTilesSelector() = First( TilesBehindInLine(
                                              from = casterTile@+0x50,
                                              to   = First(SortByDistance(Tiles(Target@+0x60),
                                                                          casterTile@+0x50), 1),
                                              settings = NULL, maxAmount = NULL ), 3 )

    `SortByDistance` + `First(1)` sur `Tiles(Target)` est l'IDENTITE quand la cible est mono-hex
    (toutes le sont sauf les trois-pieds de `ThreeTileUnitSpawnShape`) : la « direction » est la
    tuile de la cible. `TilesBehindInLine` prolonge alors la droite `caster -> cible` et **sa 1re
    tuile rendue EST la cible** (cf. `selectors/geometry.TilesBehindInLine`), d'ou le `-1`.

    `settings = NULL` n'est PAS une absence : `TilesBehindInLineSelector$$.ctor` construit un
    `TilesBehindSettings` par defaut (tous champs a zero) -> `check_walkable = False` ET
    `update_reference = False` -- lecture deja etablie et confrontee par la face COMBAT
    (`dive_attack.py` note 2). La ligne des 3 tuiles n'est donc bornee QUE par le bord du plateau,
    jamais par la walkabilite ni par l'elevation. On REUTILISE le foyer
    `engine.battle_query.get_tiles_behind` (mirror UNIQUE en domaine POSITION, #124) avec ces deux
    drapeaux : le re-ecrire serait un fork.

    ⚠ L'UTILITE DEPEND AUSSI DE LA POSITION : `casterTile@+0x50` est la tuile CANDIDATE (l'overload
    TUILE de `GetEligibleTargetsSelectable` ecrit `possibleCasterTile` dans `AbilityEntities`).
    L'Autarch se place donc pour ALIGNER le plus d'ennemis derriere sa cible."""
    ABILITY_ID = int(ActiveAbilityType.Loki_SwoopingHawk)   # 0x428 = 1064 (argument du ctor natif)
    #: `Fix64.op_Implicit(1)` construit **INLINE** dans `EvaluateNonComparable` (pas de `.cctor`).
    MIN_UTILITY = 1.0
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `First(TilesBehindInLine(...), 3)` -- litteral `3`, le meme que la face COMBAT
    #: (`dive_attack.DIVE_WAVE_TILES`) ; ce n'est PAS une constante de config.
    WAVE_TILES = 3
    #: `utility = Fix64(n - 1)` -- la cible visee ne se paie pas elle-meme.
    SELF_TARGET_OFFSET = 1

    def _wave_enemy_count(self, ctx: NCContext, tile: tuple, target_pos: tuple) -> int:
        """`Enemies(Units(GetTargetTilesSelector(), 1, 3)).Select(entities).Count`.

        `get_tiles_behind` est le mirror natif de `BattleQuery$$GetTilesBehind` +
        `TileUtil$$IsTileValidForList` (PREFIXE, pas filtre) ; avec `check_walkable=False` et
        `update_reference=False` il ne s'arrete qu'au bord du plateau. `Units(..., unique: 1)` puis
        `Enemies(caster, ...)` = les positions ENNEMIES parmi ces tuiles, dedupliquees -- une
        position porte au plus une unite, donc l'unicite est structurelle offline.

        `tile_exists` vient de `ctx.walkable_by_pos` / `ctx.neigh_by_pos` (les canaux de plateau de
        `NCContext`). Canal muet -> la ligne s'arrete tout de suite : borne INF assumee, jamais une
        vague inventee."""
        neigh = bq.neigh_map(ctx) or {}
        walk = ctx.walkable_by_pos or {}
        known = set(walk) | set(neigh) | set(ctx.tile_id_by_pos or {})

        def _exists(p):
            return (not known) or (p in known)

        positions = bq.get_tiles_behind(
            (tile[0], tile[1]), (target_pos[0], target_pos[1]),
            max_count=self.WAVE_TILES,
            check_walkable=False, update_reference=False,      # `settings = NULL` -> defauts
            walkable_at=lambda p: bool(walk.get(p, True)),
            elevation_at=lambda p: int((ctx.elev_by_pos or {}).get(p, 0) or 0),
            tile_exists=_exists)
        epos = {(p[0], p[1]) for p in (ctx.epos or []) if p and p[0] is not None}
        return sum(1 for p in positions if (p[0], p[1]) in epos)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)     # domaine UNITE (cible = un ennemi)
        if not elig:
            return []
        best = None                                          # (target, tile, util)
        for P in _sweep_origin_first(ctx) or ([ctx.origin] if ctx.origin else []):
            if P is None:
                continue
            for tid, tpos in elig:                           # LISTE : ordre natif, jamais un `set`
                if tid is None or tpos is None:
                    continue
                if P != ctx.origin:
                    # Meme gate de castabilite par position que `DoomboltPlaybook` -- foyer
                    # `cast_positions`, canal muet -> ensemble vide -> cible ignoree ici.
                    ok = CP.positions_castables({}, getattr(ctx, "cast_from_tiles", None),
                                                ctx.uid, tid, self.ABILITY_ID, ctx.origin)
                    if P not in ok:
                        continue
                n = self._wave_enemy_count(ctx, P, tpos)
                util = float(n - self.SELF_TARGET_OFFSET)    # `Fix64(n - 1)`
                if util < self.MIN_UTILITY:
                    continue                                 # gate Bucket `util >= min`
                if best is None or util > best[2]:           # strict > : 1er (position, cible) max
                    best = (tid, P, util)
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] SwoopingHawk target=%s tile=%s util=%s"
                  % (ctx.uid, best[0], best[1], best[2]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
