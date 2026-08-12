"""AlphaWarriorPlaybook (1112, `tyranWingedPrime`) -- face DECISION (#945).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable` (0x458 = 1112) :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))       # `.cctor` : Fix64(1)
    if (this.ability@+0x68 == null) throw
    summonId = <AlphaWarriorAbility>$$GetSummonId(this.ability)        # corps DEDUPLIQUE, etiquete
                                                                      # `SporeMineLauncherAbility$$GetSummonId`
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        b = battleQuery.<slot itf 195>(caster, summonId, entities@+0x10)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                     Fix64.op_Implicit(b ? 1 : 0)))

et `IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$.cctor` = `Fix64.op_Implicit(1)` -> le
statique qui sert de `minUtility` au Bucket. **`MIN_UTILITY = 1` et l'utilite vaut 0 ou 1** : le
gate `AddAction` (`util >= min`) transforme donc le booleen en VETO. Une tuile depuis laquelle le
Warrior invoque n'aurait aucune cible n'est jamais proposee -- c'est tout le playbook.

Le slot **195 = 0xc3** est `HasSummonTargetInAttackRangeAtTile` (3 params) --
`data/symbols/<build>/metadata/interface_slots.tsv`, pas une deduction de nom. Son corps
(`IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTile`) :

    if (EntityExtensions.IsMachine(parent))
        return HasSummonTargetInAttackRangeAtTileWithMachineParent(parent, unitId, tile)
    nearest = GetNearestEnemy(parent, position: Nullable(new UnitPosition(tile)))
    return IsTargetInAttackRangeForSummon(parent, unitId, tile, nearest)

`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position)` -- la `position` fournie
REMPLACE celle du caster (`if (position.HasValue) tilesA = position.Value else tilesA =
GetUnitPosition(caster)`), donc les distances sont mesurees DEPUIS LA TUILE DE SPAWN :

    best = null ; bestDist = int.MaxValue ; bestAdj = false
    foreach u in GetAllAliveUnits(null):
        if (!UnitExtensions.IsEnemy(caster, u, state)) continue
        if (UnitExtensions.IsIrrelevantObject(u)) continue
        d   = GetDistance(tilesA, u) ; adj = AreEntitiesAdjacent(tilesA, u)
        if (d < bestDist || (adj && !bestAdj)) { best = u ; bestDist = d ; bestAdj = adj }
    return best

`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile, target)` :

    if (target == null || !UnitExtensions.IsTargetable(target)) return false
    range = 0
    foreach w in GetUnitConfig(unitId).weapons:  range = Math.Max(range, w.Range ?? 1)
    if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
        range = 1 ; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
    } else if (range == 1) {
        if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
    }
    if (GetDistance(tile, target) > range) return false
    foreach t in GetTiles(target):
        if (!SetExtensions.IsNullOrEmpty(movementQuery.<slot itf 16>(tile, t, 6, 2))) return false
    if (range == 1 && !DamageCalculations.CanMeleeAttackOverElevationDifference(tile,
                                                    GetMainTile(target))) return false
    return true

Le slot **16 d'`IMovementQuery` est `GetTilesObscuringTerrain`** (4 params, meme table) : c'est un
test de LIGNE DE VUE, et un resultat NON VIDE fait echouer. Mask `6` = elevation + murs, seuil `2`
-- exactement les arguments que mirrore deja `battle_query.is_target_tile_obscured` (foyer partage,
aucun fork).

TROIS BRANCHES INERTES POUR CE PORTEUR, et c'est MESURE, pas suppose
---------------------------------------------------------------------
* `ShouldApplyRangedInMelee` est gate sur `HasTrait(attaquant, 0xb = UnitTrait.Ranged)`, trait
  qu'AUCUNE unite ne porte (0 dans gameconfig ET dans `BC.Units[].Traits`) -- mesure deja etablie
  et documentee par `playbook.prediction._shared._should_apply_ranged_in_melee`. La branche ne
  peut donc pas s'activer.
* `range == 1` : `tyranSmnWarrior` (le `unitId` constant de 1112) porte deux armes, l'une sans
  `Range` (melee -> 1) et l'autre `Range: 2` -> `Max` = **2**. Les deux gates `range == 1`
  (`IsAdjacentTo` et `CanMeleeAttackOverElevationDifference`) sont donc morts ici. Ils restent
  ECRITS dans `_is_target_in_attack_range_for_summon` : ils vivront si un autre porteur entre.
* `IsMachine(parent)` : `tyranWingedPrime` est une unite, pas une MACHINE OF WAR. La branche
  `...WithMachineParent` est donc INATTEIGNABLE ICI -- elle etait le residu `#945-r1`, **ferme
  par #967** : `ForwardSpotter` (1143) la rend obligatoire (porteur `astraOrdnanceBattery`, MoW),
  et les deux branches vivent desormais dans le foyer `summon_attack_range.py`. Ce playbook-ci
  passe `machine_parent=False`, ce qui restitue EXACTEMENT le comportement d'avant.

VOIE D'ENUMERATION -- CIBLE TUILE
----------------------------------
Le 3e argument du slot 195 est un TILE, et `GenerateAction` emet cette meme entite : la cible de
1112 est une TUILE de spawn. Voie employee, la MEME que `DarkTalonStrikePlaybook` :
`abilityTargets(uid, 1112).fromHere` filtre sur `kind == "tile"`, puis `ctx.tile_id_by_pos` pour
l'id d'entite-tuile. Ecart NOMME (identique) : `fromHere` n'enumere que depuis l'ORIGINE.

LE GATE `ShouldEvaluate`, ET IL EST DEJA PORTE
----------------------------------------------
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate` est le corps FOLDE (COMDAT,
refcount 7) `GetStat(unit, 0xc = TurnsStarted) > 1` -- il ne figure PAS dans `frida/methods.tsv`
(corps partage, un seul proprietaire par RVA), et c'est precisement cette classe qui le NOMME.
Le port l'a deja sous `_base._turns_started_gate`, dont la docstring cite les vtables resolues
LIVE (#46) : TheQuickening(1151), HeroicFusillade(1180), VigilanceEternal(1202) **et
AlphaWarrior**. `AlphaWarriorPlaybook` n'evalue donc JAMAIS au premier tour de son porteur.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from . import summon_attack_range as SAR   # FORME B (liaison de MODULE) : foyer #967 des DEUX
#                                            branches du slot 195, substituable par un patcheur.
from ._base import NCContext, NonComparablePlaybook, _turns_started_gate


class AlphaWarriorPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable` -- utilite
    BOOLEENNE (`Fix64(1)` / `Fix64(0)`) : le summon invoque sur cette tuile aurait-il une cible
    d'attaque a portee ? `MIN_UTILITY = 1` (le `.cctor`) en fait un VETO."""
    ABILITY_ID = int(ActiveAbilityType.AlphaWarrior)   # 0x458 = 1112
    MIN_UTILITY = 1.0   # `AlphaWarriorPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics+0x00
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 = le corps FOLDE `AlphaWarriorPlaybook$$ShouldEvaluate` :
        `GetStat(unit, 0xc = TurnsStarted) > 1` -- l'ability n'est jamais evaluee au PREMIER tour
        de son porteur. Foyer partage `_base._turns_started_gate` (aucune copie locale)."""
        return _turns_started_gate(ctx)

    def has_summon_target_in_attack_range_at_tile(self, ctx: NCContext, tile: tuple) -> bool:
        """`IBattleQuery` slot 195 -- l'utilite booleenne, en clair.

        `machine_parent=False` : `tyranWingedPrime` n'est PAS une MoW, donc le natif prend la
        branche `GetNearestEnemy` + `IsTargetInAttackRangeForSummon`. C'est exactement ce que le
        foyer rend pour ce drapeau -- le port n'a pas change de comportement en #967."""
        sid = SAR.summon_id(ActiveAbilityType(self.ABILITY_ID).name)
        return SAR.has_summon_target_in_attack_range_at_tile(ctx, tile, sid, machine_parent=False)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une cible TUILE.

        L'utilite ne vaut que 0 ou 1 et `MIN_UTILITY` vaut 1 : toutes les tuiles retenues sont a
        EGALITE, donc `AddAction` (remplacement STRICT) garde la PREMIERE de l'enumeration native
        -- d'ou l'arret des la premiere tuile qui passe."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tl = t.get("tile")
                    if t.get("kind") != "tile" or not tl or tl.get("col") is None:
                        continue
                    pos = (tl["col"], tl["row"])
                    if not self.has_summon_target_in_attack_range_at_tile(ctx, pos):
                        continue               # util 0 < MIN_UTILITY 1 -> jamais dans le bucket
                    tile_id = (ctx.tile_id_by_pos or {}).get(pos)
                    if tile_id is None:
                        continue               # pas d'entite-tuile -> cible inemissible
                    if ctx.debug:
                        import sys
                        print("    [dbg NC u%s] AlphaWarrior tile=%s tileId=%s"
                              % (ctx.uid, pos, tile_id), file=sys.stderr)
                    return [{"target": tile_id, "ability": self.ABILITY_ID,
                             "to": None, "pred": self.MIN_UTILITY}]
        return []
