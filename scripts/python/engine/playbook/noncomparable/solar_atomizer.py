"""SolarAtomizerPlaybook (1174, `admecBossBelisarius`) -- #1027.

Face DECISION du marquage de bande de Belisarius Cawl. Le PENDANT COMBAT vit dans
`engine.runner.abilities.admec.SolarAtomizerAbility`.
"""
from __future__ import annotations

from dataclasses import replace

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.selectors.accessors import FixedTileIds
from engine.runner.abilities.admec import solar_atomizer_target_tiles
from engine.playbook.tile_targets import dsl_context_for_tile_target, unit_on_tile
from engine.services.battle_query import has_minimum_remaining_turns

from ._base import NCContext, NonComparablePlaybook, eligible_target_tiles, native_priority


class SolarAtomizerPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.SolarAtomizerPlaybook$$EvaluateNonComparable` -- MIRROR du
    decompile, remis en C# :

        bucket = new Bucket(0, Nullable<Fix64>(<statique du cctor> = Fix64.op_Implicit(1)));
        foreach (e in BasePlaybook.GetEligibleTargetsSelectable(this, caster, casterPosition)) {
            u     = Fix64.op_Implicit(1);
            sel   = SolarAtomizerAbility.GetTargetTiles(<this+0x68 = l'ability>);
            tiles = TargetsSelector.SelectTiles(sel, e);          // `e` = l'AbilityEntities de e
            foreach (t in tiles) {
                unit = UnitExtensions.GetUnit(t, <this+0x20 = state>);
                if (unit != null && UnitExtensions.IsEnemy(unit, caster, state))
                    u = Fix64.op_Addition(u, Fix64.op_Implicit(0x14));      // +20
                u = Fix64.op_Increment(u);                                  // +1, INCONDITIONNEL
            }
            bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, e.<+0x10>, u) );
        }
        return bucket;

    Soit, en clair : **`u = 1 + |bande| + 20 x |ennemis dans la bande|`**. L'increment est HORS du
    `if` (deux sites distincts au decompile, le `+20` dans la branche et le `++` apres elle) : une
    tuile vide vaut donc 1 et une tuile ennemie 21, jamais 20.

    La bande est celle de `SolarAtomizerAbility$$GetTargetTiles`, RE-EVALUEE par cible candidate --
    le meme arbre que la face COMBAT, importe depuis `runner.abilities.admec` pour qu'il n'existe
    qu'UN mirror (une seconde transcription divergerait en silence). La cible est une ENTITE-TUILE
    (`TargetIsTile` au masque), donc le vehicule de collapse est `FixedTileIds([tid])`, comme chez
    les autres playbooks tile-target.

    `ShouldEvaluate(unit)` -- MIRROR du decompile, gate AMONT :

        if (!<this+0x28 = IBattleQuery>.<slot 0x1b>(unit, 2)) return false;   // HasMinimumRemainingTurns
        p = <vtable+0x1f8> GetUseProbability(unit);
        if (p >= 1) return true;
        if (p <= 0) return false;
        return <this+0x30 = rng>.NextBool(p);

    Le slot `0x1b` est resolu par `data/symbols/<build>/metadata/interface_slots.tsv` :
    `IBattleQuery` slot 27 = `HasMinimumRemainingTurns` (2 parametres). Le gate a un SENS : le
    degat de 1174 ne tombe qu'au tour SUIVANT (triggered `1297 SolarAtomizer_PendingAttack`), donc
    marquer alors qu'il reste moins de 2 tours ne servirait a rien.

    `GetUseProbability(unit)` (`SolarAtomizerPlaybook$$GetUseProbability`) rend `Fix64(1)` quand
    `BaseUnitComponent+0x5c != 0` et `Fix64.FromIntFraction(50, 100) = 0.5` sinon : la branche 0.5
    est une porte ALEATOIRE, NON modelisee -- meme ecart assume que `BlackRagePlaybook` /
    `ItItchesPlaybook` (moteur deterministe, cf. la docstring de
    `NonComparablePlaybook.should_evaluate`). Le champ `BaseUnitComponent+0x5c` n'est pas identifie ;
    residu `#1027-r3`.

    `.ctor` -> `<base>..ctor(this, 0x496 = 1174)` (ABILITY_ID, pas une priorite ; le nom
    `ComparablePlaybook<T>$$.ctor` que rend Ghidra est un corps gshared DEDUPLIQUE -- le
    discriminant LU est l'override d'`EvaluateNonComparable`, seul corps qu'appelle
    `NonComparablePlaybook<T>$$EvaluateInternal`).
    `.cctor` : `<statique> = Fix64.op_Implicit(1)` -> `minUtility` du Bucket = **1**.
    Tier `get_Priority` = **100** (`AbilityPriority.Early`), mesure #170.

    RESIDU NOMME (`#1027-r4`) : `dsl_context_for_tile_target` ne REPOSITIONNE PAS le caster sur la
    position candidate, alors que `GetEligibleTargetsSelectable(caster, casterPosition)` construit
    ses `AbilityEntities` A CETTE POSITION. Or `GetTargetTiles` lit `CasterTiles@+0x58` (la
    direction de la bande EN DEPEND). Consequence : la bande est calculee depuis l'empreinte
    COURANTE du caster pour toutes les positions balayees. Inerte tant que Belisarius ne bouge pas
    (boss 3 hex), mais le dire vaut mieux que le taire."""
    ABILITY_ID = int(ActiveAbilityType.SolarAtomizer)          # 1174
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.SolarAtomizer))   # 100 = AbilityPriority.Early
    #: `Fix64.op_Implicit(0x14)` -- le bonus par tuile ENNEMIE de la bande.
    ENEMY_TILE_BONUS = 20.0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`SolarAtomizerPlaybook$$ShouldEvaluate` : `HasMinimumRemainingTurns(unit, 2)` puis la
        porte probabiliste (non modelisee, cf. la docstring de classe).

        ⚠ Le parametre `unit` n'est PAS lu par le natif (le corps ne consulte que le plafond de
        rounds de la BC et le compteur de tours termines) -- c'est la mesure de `#287-r11-r1-r1`,
        et le foyer partage `engine.services.battle_query.has_minimum_remaining_turns` le dit. Le
        `State` n'existe pas sur la face DECISION : le plafond arrive alors VIDE et le natif comme
        le port rendent `True` (bras 1), degradation PERMISSIVE nommee, jamais un gate a l'aveugle.
        Residu `#1027-r5` : brancher le plafond de rounds sur le contexte de decision."""
        st = getattr(ctx, "state", None)
        return bool(has_minimum_remaining_turns(ctx.uid, 2, state=st))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self.should_evaluate(ctx):
            return []
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        if not from_here and not union:
            return []
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None:
            return []
        board = getattr(dctx, "board", None)
        epos = set(ctx.epos or [])
        best = None            # (centre, position caster, utilite) -- `AddAction` : STRICT `>`
        for caster_pos in ctx.reach_nc:
            # Selecteur PAR POSITION : `fromHere` a l'origine (ordre natif exact), union ailleurs.
            centers = from_here if (caster_pos == ctx.origin and from_here) else union
            for center in centers:
                tid = (ctx.tile_id_by_pos or {}).get(center)
                if tid is None:
                    continue
                sel = solar_atomizer_target_tiles(FixedTileIds([tid]))
                tiles = sel.evaluate(replace(dctx, subject=None, active_target=None)) or []
                u = 1.0                                        # `Fix64.op_Implicit(1)`
                for t in tiles:
                    if self._tile_holds_enemy(dctx, board, t, epos):
                        u += self.ENEMY_TILE_BONUS             # `+ Fix64(0x14)`
                    u += 1.0                                   # `op_Increment`, INCONDITIONNEL
                if best is None or u > best[2]:
                    best = (center, caster_pos, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        center, caster_pos, u = best
        tid = (ctx.tile_id_by_pos or {}).get(center)
        return [{"target": (tid if tid is not None else center), "ability": self.ABILITY_ID,
                 "to": (caster_pos if caster_pos != ctx.origin else None), "pred": u}]

    def _tile_holds_enemy(self, dctx, board, tile_id, epos: set) -> bool:
        """`unit = GetUnit(tile, state); unit != null && IsEnemy(unit, caster, state)`.

        Deux canaux, le premier autoritaire : `unit_on_tile` resout l'occupant VIVANT depuis le
        substrat DECISION (`dv.units`), et l'appartenance a `ctx.epos` (positions ennemies du
        contexte, le meme canal que `NovaShieldPlaybook$$CountEnemiesOnTiles`) tranche « ennemi ».
        Board absent -> `False` : on ne compte pas un ennemi qu'on ne voit pas."""
        if board is None:
            return False
        if unit_on_tile(dctx, tile_id) is None:
            return False                       # `unit == null`
        c = board.coord(int(tile_id)) if hasattr(board, "coord") else None
        return c is not None and (int(c[0]), int(c[1])) in epos
