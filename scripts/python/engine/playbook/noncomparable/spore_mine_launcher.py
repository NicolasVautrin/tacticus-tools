"""SporeMineLauncherPlaybook (1145, `tyranBiovore` -- Biovore, MachineOfWar) -- face DECISION (#971).

⚠ QUALIFIER L'ENUM AVANT DE LIRE QUOI QUE CE SOIT : `1145` est ICI un `ActiveAbilityType`
(`SporeMineLauncher`). Le MEME ordinal est aussi un `TriggeredAbilityType` (`SereneUnifier`,
`tauAunShi`), deja porte sous `engine/playbook/serene_unifier.py`. Les deux playbooks n'ont rien
de commun ; un `git grep 1145` les melange.

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`
(`IdunBattle.AI.Playbook.Loki.SporeMineLauncherPlaybook  112  IdunBattle.AI.Playbook.
NonComparablePlaybook`1`), pas deduite du ctor (Ghidra etiquette le corps gshared
`ComparablePlaybook<...>$$.ctor` pour les DEUX hierarchies).

REACHABILITE : `data/symbols/<build>/metadata/active_playbook_builders.tsv` ->
`active 1145 IdunBattle.AI.Playbook.Loki.SporeMineLauncherPlaybook`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.SporeMineLauncherPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics>+0x00))     # `.cctor` : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        u = Fix64.op_Implicit(1)
        foreach otherUnit in battleQuery.<slot 0x73>(entities@+0x30, 2):     # GetUnitsAtDistance
            if (UnitExtensions.IsEnemy(otherUnit, entities@+0x08, state))    # +0x08 = Caster
                u = u + Fix64.op_Implicit(1)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, u))

et `IdunBattle.AI.Playbook.Loki.SporeMineLauncherPlaybook$$.cctor` = `Fix64.op_Implicit(1)`.

=> **utilite = 1 + le nombre d'ennemis du caster a distance EXACTEMENT 2 de la tuile visee.**

LE SLOT EST LU : `data/symbols/<build>/metadata/interface_slots.tsv` donne `IBattleQuery 115
GetUnitsAtDistance 2` (0x73). C'est un RING **EXACT**, pas un disque --
`IdunBattle.Core.Services.BattleQuery$$GetUnitsAtDistance` passe par
`IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance`, qui filtre `dist == R` (meme lecture
et meme slot que `MasterOfTheTutelariesPlaybook`, dont le terme `nE2` est le jumeau exact). Un
ennemi ADJACENT a la tuile visee ne compte donc PAS, et un ennemi a 3 hex non plus.

LES DEUX CHAMPS D'`AbilityEntities` DU CORPS NE SONT PAS LE MEME, ET LES DEUX SONT LUS
---------------------------------------------------------------------------------------
`GetUnitsAtDistance` recoit `entities@+0x30` = **TargetTile**, tandis que `GenerateAction` emet
`entities@+0x10` = **Target**. La carte de champs est celle que le port cite partout
(`+0x08 Caster`, `+0x10 Target`, `+0x30 TargetTile`, `+0x38 TargetPosition`, `+0x40 CasterTile`,
`+0x48 CasterPosition` -- cf. `engine/entities/selectors/accessors.py`), et elle est RE-CONFIRMEE
ici par le remplisseur lui-meme : `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`
ecrit `+0x08 = caster`, `+0x10 = entity`, `+0x30 = GetMainTile(entity)`,
`+0x38 = GetTiles(entity)`, `+0x40 = possibleCasterTile`, `+0x48 = ToList(possibleCasterTile)`.
Pour un cast TILE-TARGET, `GetMainTile(<entite-tuile>)` est la tuile elle-meme : les deux champs
designent la MEME tuile, et le port n'en manipule qu'une.

POSITION-INDEPENDANTE, ET C'EST DEMONTRABLE
--------------------------------------------
Aucun terme de l'utilite ne lit `casterPosition`. Et l'ENSEMBLE des cibles ne le lit pas non plus :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$.ctor` =
`TargetingOptions(0, <TargetingRange statics>+0x48, 1, 0x40046001042, 0, 0, 0)` -- portee
`RANGE_WHOLE_BOARD`, et le masque (`TargetMatchesDynamicRule | TargetIsTile | TargetTileIsFree |
AllowObscuredTarget | AllowNullCasterTile | TargetIsNotAdjacentToEnemy`, deja transcrit par
`engine/runner/abilities/tyranids.py::SporeMineLauncherAbility.TARGETING_OPTIONS`) ne porte AUCUNE
regle qui depende de la tuile du caster (pas de `CasterHasNotMoved`, pas de portee finie). Le
caster ne bougeant pas pendant le sweep, l'occupation lue par `TargetTileIsFree` est elle aussi
constante.

`Bucket$$AddAction` remplacant par `Fix64.op_GreaterThan` STRICT et `reach_nc` commencant par
l'ORIGINE, l'argmax est donc TOUJOURS atteint a l'origine -> `to = None`, et la vue `fromHere`
(l'ordre EXACT du selecteur natif a l'origine) est la seule dont on a besoin. Le sweep de
positions n'est pas ecrit parce qu'il ne peut rien changer, pas parce qu'on l'a oublie.

⚠ Le porteur est une MACHINE OF WAR : `ctx.origin` peut etre `None` (la plateforme n'est pas une
unite de `dv.units`). Aucun terme de ce playbook n'en depend -- c'est verifie ligne a ligne
ci-dessous, et c'est ce qui rend le port utilisable sur ce porteur-la.

GATE `MIN_UTILITY` : `Fix64(1)`, et le gate d'`AddAction` est INCLUSIF
(`FUN_18004ed00` : `action.utility >= minUtility.Value`). L'utilite valant `1 + n >= 1`, il ne
mord JAMAIS. Il est ecrit parce qu'il est LU, pas parce qu'un regime l'exerce.
"""
from __future__ import annotations

import hexgeo

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class SporeMineLauncherPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SporeMineLauncherPlaybook$$EvaluateNonComparable` (0x479 = 1145
    `ActiveAbilityType.SporeMineLauncher`).

    Utilite = `1 + |{ u in GetUnitsAtDistance(targetTile, 2) : IsEnemy(u, caster) }|`."""

    ABILITY_ID = int(ActiveAbilityType.SporeMineLauncher)   # 0x479 = 1145
    #: `SporeMineLauncherPlaybook$$.cctor` = `Fix64.op_Implicit(1)` -> la borne `Nullable` que le
    #: ctor du Bucket recoit. Gate INCLUSIF (`>=`), donc inerte ici (l'utilite vaut `1 + n`).
    MIN_UTILITY = 1.0
    #: 1145 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> `AbilityPriority.Normal`.
    PRIORITY = 0
    #: Le `2` LITTERAL du 2e argument de `GetUnitsAtDistance(entities@+0x30, 2)`. Il n'est derive
    #: d'AUCUNE constante de la config (`SporeMineLauncher.constants` = `unitId` / `nrOfHits` /
    #: `initialCooldownTurns`, aucun rayon) : on transcrit le litteral.
    _RING = 2

    def _eligible_target_tiles(self, ctx: NCContext) -> list[tuple]:
        """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` = `IBattleQuery` slot
        0x42 = `GetValidTargets(caster, UnitPosition(P), abilityType)`, puis un
        `idun.shared.extensions.ListExtensions$$Remove` d'ineligibilite.

        `fromHere` est la vue PAR POSITION a l'origine, donc l'ORDRE EXACT du selecteur natif ;
        `targets` est l'UNION sur toutes les tuiles de move, dont l'ordre n'est celui d'aucune
        position. On prend `fromHere` -- l'argmax etant a l'origine (cf. l'en-tete), c'est la seule
        vue pertinente ; `targets` ne sert que de REPLI NOMME quand `fromHere` est vide alors que
        l'union ne l'est pas (porteur MoW dont la position courante n'est pas publiee)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        from_here: list[tuple] = []
        union: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for key, out in (("fromHere", from_here), ("targets", union)):
                    for t in (a.get(key) or []):
                        tl = t.get("tile")
                        if t.get("kind") == "tile" and tl and tl.get("col") is not None:
                            out.append((tl.get("col"), tl.get("row")))
        return from_here or union

    def _enemies_at_ring(self, ctx: NCContext, tile: tuple) -> int:
        """`|{ u in GetUnitsAtDistance(tile, 2) : UnitExtensions.IsEnemy(u, caster, state) }|`.

        `GetUnitsAtDistance` = ring EXACT (`GetTilesAtDistance` filtre `dist == R`), et le filtre
        `IsEnemy(u, caster)` fait de `ctx.epos` -- les seules positions ENNEMIES publiees -- le
        substrat exact du compte. Meme composition, meme slot et meme rayon que le terme `nE2` de
        `MasterOfTheTutelariesPlaybook`.

        RESIDU NOMME (partage avec ce jumeau) : `ctx.epos` publie une entree par unite, donc la
        tuile PRINCIPALE ; le natif compte les unites OCCUPANT chaque tuile du ring, donc une
        multi-tuile dont seul un pied touche le ring y serait comptee. Aucun regime porte ne
        l'expose (les MoW sont hors de ce canal)."""
        return sum(1 for p in (ctx.epos or [])
                   if hexgeo.distance(tile, (p[0], p[1])) == self._RING)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror du corps natif : une action par tuile eligible, argmax STRICT (tie -> la PREMIERE
        tuile enumeree par le selecteur, `Bucket$$AddAction` ne remplacant que sur `>`).

        CIBLE EMISE = la TUILE (`ctx.tile_id_by_pos`) : `GenerateAction` recoit `entities@+0x10`,
        et le cast natif attend un id d'entite-tuile (`TargetIsTile`)."""
        tiles = self._eligible_target_tiles(ctx)
        if not tiles:
            return []
        best = None                       # (tuile, utilite)
        for tl in tiles:
            u = 1.0 + float(self._enemies_at_ring(ctx, tl))
            if best is None or u > best[1]:      # strict > : 1re tuile du max gagne
                best = (tl, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        tl, u = best
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] SporeMineLauncher tile=%s u=%s"
                  % (ctx.uid, tl, u), file=sys.stderr)
        tid = (ctx.tile_id_by_pos or {}).get(tl)
        # `to = None` : l'utilite ET l'ensemble des cibles sont position-INDEPENDANTS, et le natif
        # balaie l'origine en premier -> il ne bouge jamais pour caster (cf. l'en-tete).
        return [{"target": (tid if tid is not None else tl), "ability": self.ABILITY_ID,
                 "to": None, "pred": u}]
