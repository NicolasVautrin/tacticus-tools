"""`DevastatingRefrainPlaybook` (1188, `adeptExorcist` -- Exorcist, Adepta Sororitas, MoW) -- face
DECISION.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

alors que `IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$.ctor` appelle
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this,
0x4a4, klass)` -- corps trivial DEDUPLIQUE par ICF, que ghidra etiquette du nom de l'autre
proprietaire. Meme piege, meme correction que `TitanhammerSquadPlaybook` (#976, verifie 5/5 sur son
lot) et `AdaptiveStrategyPlaybook` (#945). Seul l'`ability_id` `0x4a4` = 1188 se lit dans ce `.ctor`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$EvaluateNonComparable`, lu verbatim :

    bucket = new Bucket<UnitAction>(0, Nullable(<premier statique de la classe>))
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        shape = DevastatingRefrainAbility.GetShape()                 # surcharge SANS argument
        tiles = TargetsSelector.SelectTiles(shape, entities)
        util  = Fix64.op_Implicit(1)
        foreach t in tiles:
            u = UnitExtensions.GetUnit(t, this.<+0x20 = state>)
            if (u != null && UnitExtensions.IsEnemy(u, entities.<+0x08 = caster>, state))
                util = Fix64.op_Increment(util)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities.<+0x10 = target>, util))
    return bucket

`IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$.cctor` : `<statique> = Fix64.op_Implicit(1)`
-> `MIN_UTILITY = 1`. **Un seul ecrivain** : `IdunBattle.AI.Playbook.NonComparablePlaybook`1$$.cctor`
N'EXISTE PAS dans le build (recherche de symboles VIDE), donc le `Fix64(10)` qui ecrase les `.cctor`
derives de la famille COMPARABLE (`static_threshold_gate`, mesure #419-r1-tr14-r5-r2-r1-r1-r1-r2-r4)
n'a pas de pendant ici.

Donc : **utilite = 1 + le nombre d'ENNEMIS DU CASTER debout sur les tuiles de la forme**, forme
ancree sur la TUILE VISEE.

L'ARTEFACT DE FORME EST DEJA PORTE -- ON L'APPELLE, ON NE LE RECABLE PAS
------------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape()` (arite 1) =

    If( DSLTriggers.IsPositionMachineForCurrentPlayer(2),
        GetShape(this+0xf0 = {3,1,5}),
        GetShape(this+0xf8 = {0,2,4}) )

et `GetShape(this, List<int>)` (arite 2) =

    sel = DSLSelectors.<+0x60 = Target>
    foreach idx in list:  sel = sel + DSLSelectors.TileFromVector(Target, DSLFormulas.Get(idx))
    return sel

C'est le MEME artefact que la face COMBAT, portee et confrontee live par #90-B : ce module appelle
`engine.runner.abilities.sisterhood.devastating_refrain_shape` et ses deux tuples de directions. Le
re-ecrire serait un FORK DE FOYER -- la faute que `daemon_prince._CtxBoard` documente.

⚠ `If(IsPositionMachineForCurrentPlayer(2), ...)` fait dependre la GEOMETRIE de la forme du cote du
plateau ou la MoW du joueur COURANT est deployee. Ce predicat n'avait AUCUN canal sur la route
NonComparable avant cette tranche : `NCContext` ne portait pas la cascade, donc
`tile_targets.dsl_context_for_tile_target` lisait `None` et le predicat rendait False d'office --
la forme aurait ete la MAUVAISE des trois quarts du temps (mesure #302 : 173 des 675 boards
declarent une position non nulle). Le canal est desormais `NCContext.machine_of_war_position`, le
MEME callable que porte `AiDecisionContext` (cascade de quatre etages, tri-etat).

CE QUI N'EST PAS PORTE ICI, ET C'EST DIT
-----------------------------------------
* La PHASE 2 (le barrage lui-meme, effet `DevastatingRefrain_Attack` 1403 pose sur la MoW) n'entre
  pas dans cette utilite -- le natif non plus : `EvaluateNonComparable` ne fait AUCUNE prediction de
  degat, il compte des occupants. C'est pourquoi 1188 n'a aucun `Make*Predictions` et pourquoi son
  entree a `_NONCOMPARABLE_ABILITIES` est necessaire (sans elle,
  `playbook/prediction/abilities.make_damage_predictions` FABRIQUERAIT un event depuis les
  `minDmg`/`maxDmg` du gameconfig de 1188, que le natif n'emet jamais).
* Le residu de `unit_on_tile` vaut ici aussi : le natif resout l'occupant par
  `TileContentComponent`, rempli pour CHAQUE pied d'une unite multi-tuiles, la ou `dv.units` ne
  porte que la MAIN tile. Une unite dont seul un pied SECONDAIRE tombe dans la forme est vue par le
  natif et pas par ce port. Borne INFERIEURE, nommee.

VOIE D'ENUMERATION -- TILE-TARGETED, donc PAS le plan
------------------------------------------------------
Le masque de `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` porte
`TargetIsTile` (face COMBAT : `abilityTargets` rend `kind == "tile"`, 33 tuiles mesurees sur C1_02).
`computeAttackPlans` ne boucle que sur les ENNEMIS : un port branche dessus rendrait `rankCount = 0`
et serait MUET sans erreur. Voie employee : `eligible_target_tiles` (`abilityTargets(uid, 1188)`),
le mirror de `GetEligibleTargetsSelectable` en domaine TUILE -- la MEME que `TitanhammerSquad`.

ECART NOMME : `fromHere` n'enumere que depuis l'ORIGINE, alors que le natif balaie aussi les tuiles
de MOVE. Ici l'utilite est POSITION-INDEPENDANTE (l'ancre est la tuile visee, `casterPosition`
n'entre dans aucun terme), donc le sweep ne peut RIEN ameliorer : le `Bucket` garde la premiere
tuile a utilite egale, et le natif balaie l'origine en premier. L'ecart est nul par construction.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.tile_targets import dsl_context_for_tile_target, unit_on_tile
# Le foyer de la FORME est celui de la face COMBAT (#90-B) : on l'appelle, on ne le recable pas.
from engine.runner.abilities.sisterhood import (MACHINE_POSITION_BOTTOM, SHAPE_DIRECTIONS_MACHINE,
                                                SHAPE_DIRECTIONS_OTHER, devastating_refrain_shape)

from ._base import NCContext, NonComparablePlaybook, eligible_target_tiles


class DevastatingRefrainPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$EvaluateNonComparable` -- utilite =
    `1 + |ennemis du caster occupant une tuile de la forme ancree sur la TUILE VISEE|`."""

    ABILITY_ID = int(ActiveAbilityType.DevastatingRefrain)   # 0x4a4 = 1188
    #: `.cctor` : `Fix64.op_Implicit(1)` -> le `minUtility` du `Bucket` (gate `AddAction`). Un seul
    #: ecrivain : la base generique NonComparable n'a PAS de `.cctor` dans ce build.
    MIN_UTILITY = 1.0
    #: `Fix64.op_Implicit(1)` POSE AVANT la boucle -- ce plancher est ce qui fait qu'une cible sans
    #: aucun ennemi dans sa forme reste PROPOSEE (utilite 1 == MIN_UTILITY, donc retenue par le
    #: `Bucket`, dont le gate est `>=`). Le confondre avec un compte nu ferait un VETO.
    BASE_UTILITY = 1.0
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    @staticmethod
    def _shape_directions(ctx: NCContext):
        """`If(IsPositionMachineForCurrentPlayer(2), this+0xf0, this+0xf8)`.

        Le verdict est calcule ICI et la branche prise est instanciee -- exactement ce que fait
        deja la face COMBAT (`devastating_refrain_tree(target, on_machine_side)`) : le predicat ne
        depend d'aucun element courant, et un `If` du domaine SELECTEUR n'existe pas cote port.

        TRI-ETAT : canal muet (`None`) -> le predicat natif rendrait FAUX, donc la branche `else`
        (`SHAPE_DIRECTIONS_OTHER`). Ce n'est pas une degradation choisie, c'est le comportement du
        natif quand `GetPositionMachineForPlayer` ne rend pas `Bottom`."""
        mow = getattr(ctx, "machine_of_war_position", None)
        pos = mow() if callable(mow) else None
        return (SHAPE_DIRECTIONS_MACHINE if pos == MACHINE_POSITION_BOTTOM
                else SHAPE_DIRECTIONS_OTHER)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(1) + |{t in SelectTiles(GetShape(), entities) : IsEnemy(GetUnit(t), caster)}|`.

        `target` est une POSITION de tuile `(col, row)` (cf. `eligible_target_tiles`), pas un id
        d'unite : le masque de 1188 porte `TargetIsTile`.

        `tile` (la position candidate du caster) N'ENTRE PAS dans la formule -- l'ancre est la tuile
        visee, `casterPosition` n'apparait dans aucun terme du corps natif.

        Contexte DSL indisponible (`Scene` ou board absents) ou tuile hors `boardGraph` -> `None` :
        aucune utilite INVENTEE, l'ability n'est simplement pas proposee. Meme convention que
        `daemonic_ordnance.calculate_custom_utility`."""
        if target is None:
            return None
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None:
            return None
        tile_id = (ctx.tile_id_by_pos or {}).get((target[0], target[1]))
        if tile_id is None:
            return None
        caster_team = (dctx.caster or {}).get("team")
        shape = devastating_refrain_shape(int(tile_id), self._shape_directions(ctx))
        util = self.BASE_UTILITY
        for t in (shape.select(dctx) or []):
            # `UnitExtensions.GetUnit(tileEntity, state)` puis `UnitExtensions.IsEnemy(unit, caster,
            # state)` -- ce dernier compare `GetCurrentPlayer(x).Team.Index` des deux cotes, ce que
            # le substrat de decision expose en `unit["team"]` (meme convention que le noeud
            # `Enemies` et que `daemonic_ordnance`).
            u = unit_on_tile(dctx, t)
            if u is not None and caster_team is not None and u.get("team") != caster_team:
                util += 1.0
        return util

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une ability TILE-TARGETED.

        L'ordre d'enumeration de `fromHere` EST celui du selecteur natif ; `Bucket$$AddAction` ne
        remplace que sur amelioration STRICTE, donc a utilite egale la PREMIERE tuile gagne. Le `>`
        ci-dessous herite cette semantique."""
        from_here, _union = eligible_target_tiles(ctx, self.ABILITY_ID)
        best = None                                        # (tuile, utilite)
        for tpos in from_here:
            util = self.evaluate_non_comparable(ctx.origin, tpos, ctx)
            if util is None or util < self.MIN_UTILITY:
                continue                                   # gate `minUtility` du `Bucket`
            if best is None or util > best[1]:             # STRICT -> keep-first au tie
                best = (tpos, util)
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] DevastatingRefrain tile=%s util=%s"
                  % (ctx.uid, best[0], best[1]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


__all__ = ["DevastatingRefrainPlaybook"]
