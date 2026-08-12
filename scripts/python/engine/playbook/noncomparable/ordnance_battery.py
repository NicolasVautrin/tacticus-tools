"""Les DEUX faces DECISION d'`astraOrdnanceBattery` (MACHINE OF WAR Astra Militarum) -- #967.

`MalleusRocketLauncher` (1142, DAMAGE/Blast) et `ForwardSpotter` (1143, SUMMON) partagent leur
porteur ; leurs utilites, elles, n'ont rien en commun -- deux classes, un module.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` : les deux derivent de
`IdunBattle.AI.Playbook.NonComparablePlaybook`1`. Leur `.ctor` decompile NOMME
`ComparablePlaybook<...>..ctor` (corps trivial DEDUPLIQUE -- piege #487-r1).

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` :
`active 1142 -> ...MalleusRocketLauncherPlaybook`, `active 1143 -> ...ForwardSpotterPlaybook`.

RECENSEMENT AU BLOC (`probe_967_playbook_blocks.py`) : trois corps CONTIGUS chacun
(`EvaluateNonComparable`, `.cctor`, `.ctor`), voisin suivant = une autre classe. Rien de fondu
DEDANS -- mais les deux appellent des methodes d'ability dont le corps est fondu AILLEURS, et
Ghidra les nomme alors d'apres l'autre proprietaire (cf. les deux encadres ci-dessous).

⚠ Les deux prennent `GetEligibleTargetsSelectable(caster, casterPosition.get_MainTile())` --
l'overload TUILE, pas l'overload POSITION (contraste 1213/1214/1223/1224). Pour une MoW, sans
`PositionComponent`, les deux degenerent sur la meme unique position candidate.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

import engine.playbook.noncomparable._targets as TGT              # FORME B, ABSOLU (#962)
import engine.playbook.noncomparable.summon_attack_range as SAR   # FORME B, ABSOLU -- #967 slot 195
from ._base import NCContext, NonComparablePlaybook


class MalleusRocketLauncherPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.MalleusRocketLauncherPlaybook$$EvaluateNonComparable`
    (0x476 = 1142).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # `.cctor` : Fix64(1)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition.get_MainTile()):
            util = Fix64(0)
            u = UnitExtensions.GetUnit(entities@+0x10, this.state@+0x20)
            if (u != null)
                util += Fix64( UnitExtensions.IsFriend(u, caster, state) ? -3 : +3 )
            adj = <MalleusRocketLauncherAbility>$$GetAdjacentDamageTargets(this.ability@+0x68)
            foreach unit in TargetsSelector.SelectAllUnits(adj, entities, 3):
                f = UnitExtensions.IsFriend(unit, caster, state)
                util += Fix64( ((f & 0xff) ^ 1) * 2 - 1 )                 # ami -1, ennemi +1
            if (util > Fix64(0))
                bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, util))

    Soit : **+3 / -3 pour l'OCCUPANT de la tuile visee** (rien s'il n'y en a pas), puis **+1 par
    ennemi et -1 par allie ADJACENT** a cette tuile. C'est un score de ciblage de tir de barrage :
    il PENALISE les tirs amis, et il le fait au meme titre qu'il recompense les touches.

    L'arithmetique du signe est LUE, pas devinee : `((f & 0xff) ^ 1) * 2 - 1` vaut `-1` quand
    `f == 1` (ami) et `+1` quand `f == 0` (ennemi).

    DEUX GATES, ET ILS NE SONT PAS REDONDANTS DANS LE PRINCIPE
    ----------------------------------------------------------
    Le natif teste `util > 0` INLINE (aucune action n'est meme construite pour une cible qui
    echoue), puis `Bucket.AddAction` re-teste `util >= MIN_UTILITY = 1` (le `.cctor`). Sur des
    entiers les deux coincident (`> 0` <=> `>= 1`) ; le port ecrit les deux, parce que c'est le
    natif qui les ecrit et que leur coincidence tient a la NATURE ENTIERE de l'utilite, pas a une
    egalite de seuils.

    LE NOM QUE GHIDRA DONNE EST CELUI D'UNE AUTRE ABILITY
    -----------------------------------------------------
    `GetAdjacentDamageTargets` est appelee sur `this.ability@+0x68`, qui EST une
    `MalleusRocketLauncherAbility` -- mais Ghidra la nomme
    `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetAdjacentDamageTargets`,
    et `frida/methods.tsv` n'en connait qu'UN proprietaire (elle est indexee par RVA, sans
    doublon). Corps FONDU par ICF, donc corps IDENTIQUE, donc lisible tel quel :

        return DSLSelectors.AdjacentUnits(dsl, <dsl+0x60 = Target>, unique: 1, 3)

    `<dsl+0x60>` est le referent **Target** (le meme offset que le `Target@0x178` cite par la face
    COMBAT de 1213, a la translation de base pres, et le meme que le `<DSLSelectors+0x60>` de
    `CultDemagogueAbility$$PossibleTilesForDecoys`). L'ancrage est donc la CIBLE, jamais le caster
    -- et c'est le point exact ou #957 s'est trompee. Ici il n'y a d'ailleurs pas de choix : le
    caster est une MoW SANS position, un ancrage caster ne rendrait rien.

    SUBSTRAT OFFLINE
    ----------------
    `AdjacentUnits(Target)` = toutes les unites (les DEUX camps) sur une tuile adjacente a la
    tuile visee -> `bq.count_adjacent` sur `ctx.epos` et `ctx.fpos`, qui portent la MEME porte
    d'adjacence native (liste stockee + porte d'elevation).

    ECART NOMME : `ctx.fpos` exclut le CASTER. Inerte ici -- le caster est une MoW sans position,
    il ne peut etre adjacent a rien."""
    ABILITY_ID = int(ActiveAbilityType.MalleusRocketLauncher)   # 0x476 = 1142
    MIN_UTILITY = 1.0     # `MalleusRocketLauncherPlaybook$$.cctor` : `Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `IsFriend(u, caster) ? -3 : +3` -- l'occupant de la tuile visee.
    OCCUPANT_ENEMY, OCCUPANT_FRIEND = 3, -3
    #: `((f & 0xff) ^ 1) * 2 - 1` -- chaque unite adjacente a la tuile visee.
    ADJACENT_ENEMY, ADJACENT_FRIEND = 1, -1

    def _utility(self, ctx: NCContext, pos: tuple) -> float:
        epos = [p for p in (ctx.epos or []) if p and p[0] is not None]
        fpos = [p for p in (ctx.fpos or []) if p and p[0] is not None]
        util = 0.0
        if pos in epos:                                   # `GetUnit(target) != null` + `!IsFriend`
            util += self.OCCUPANT_ENEMY
        elif pos in fpos:                                 # `GetUnit(target) != null` + `IsFriend`
            util += self.OCCUPANT_FRIEND
        neigh = bq.neigh_map(ctx)
        util += self.ADJACENT_ENEMY * bq.count_adjacent(pos, epos, ctx.elev_by_pos, neigh)
        util += self.ADJACENT_FRIEND * bq.count_adjacent(pos, fpos, ctx.elev_by_pos, neigh)
        return util

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_any(ctx, self.ABILITY_ID)
        if not elig:
            return []
        best = None                                       # (targetId, util)
        scored = []
        for tid, pos, _kind in elig:
            if tid is None or pos is None:
                continue
            u = self._utility(ctx, pos)
            scored.append((tid, pos, u))
            if u <= 0:
                continue                                  # gate INLINE `util > Fix64(0)`
            if best is None or u > best[1]:               # `AddAction` : remplacement STRICT
                best = (tid, u)
        if best is None or best[1] < self.MIN_UTILITY:    # gate Bucket `util >= min`
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] MalleusRocketLauncher target=%s util=%s scored=%s"
                  % (ctx.uid, best[0], best[1], scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


class ForwardSpotterPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ForwardSpotterPlaybook$$EvaluateNonComparable` (0x477 = 1143).

    LE CORPS, TERME A TERME
    -----------------------
        bucket   = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))   # `.cctor` : Fix64(1)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition.get_MainTile()):
            util     = Fix64(1)
            summonId = <ForwardSpotterAbility>$$GetSummonId(this.ability@+0x68)
            foreach tile in battleQuery.<slot itf 79>(entities@+0x10, 1, 1, 1):
                b = battleQuery.<slot itf 195>(caster, summonId, tile)
                util += Fix64(b)
            bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, util))

    Soit : **1 + le nombre de tuiles de spawn depuis lesquelles le Cadian invoque aurait une cible
    a portee**. Le playbook choisit donc l'allie autour duquel le spotter servira le mieux.

    Le plancher `Fix64(1)` est POSE AVANT la boucle, et `MIN_UTILITY` vaut exactement `1` : **toute
    cible eligible passe le gate**. Contraste net avec `AlphaWarriorPlaybook` (1112), qui partage
    le slot 195 mais dont l'utilite est le BOOLEEN NU -- la, `MIN_UTILITY = 1` fait un VETO. Meme
    requete, seuils identiques, semantiques opposees : c'est le `Fix64(1)` initial qui fait toute
    la difference, et le recopier de travers transformerait 1143 en veto.

    LES DEUX SLOTS, LUS DANS `metadata/interface_slots.tsv`
    -------------------------------------------------------
    * **79 = 0x4f** `GetAdjacentTiles(4 params)`. Corps :
      `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(from, onlyEmptyOrSteppable,
      onlyWalkableTiles, allowTemporary)` -> `IterateAdjacentTiles`. Les trois arguments sont
      passes a `1` : tuiles adjacentes LIBRES et MARCHABLES, temporaires admises. C'est exactement
      le `CanAddUnit(AdjacentTiles(target@0x178))` que la face COMBAT mirrore deja
      (`engine/runner/abilities/astramilitarum.py::forward_spotter_pick_tiles`).
    * **195 = 0xc3** `HasSummonTargetInAttackRangeAtTile(3 params)` -> foyer
      `summon_attack_range.py`. ⚠ Le porteur `astraOrdnanceBattery` est une **MACHINE OF WAR**,
      donc `EntityExtensions.IsMachine(parent)` est VRAI et le natif prend la branche
      `...WithMachineParent` -- celle qui teste TOUS les ennemis, pas seulement le plus proche.
      C'etait le residu `#945-r1`, ferme ici.

    `<ForwardSpotterAbility>$$GetSummonId` est le corps FONDU que Ghidra nomme
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetSummonId` ; son
    corps est `AbilityConfiguration.GetStringConstant(config, 0)`, et l'index 0 EST `unitId` --
    `astraSmnGuardsman` pour 1143 (gameconfig, jamais code en dur).

    CIBLES : des unites **ALLIEES** (`ForwardSpotterAbility$$GetDynamicInvalidTargetReason` :
    `IsUnit(target) && target != caster` ; confirme live par `abilityTargets`, cf. la face COMBAT).

    ⚠ `1143` tombe dans le court-circuit `TargetIsFriendly` sans `TargetIsEnemy` de
    `TargetingQuery$$GetPossibleTargetTiles` (zone VIDE, cf. #433-r4-r2-r1-r1-a) : sa portee est
    STATIQUEMENT exacte, ce qui rend `abilityTargets` fiable comme mirror du selecteur."""
    ABILITY_ID = int(ActiveAbilityType.ForwardSpotter)   # 0x477 = 1143
    MIN_UTILITY = 1.0     # `ForwardSpotterPlaybook$$.cctor` : `Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `util = Fix64(1)` POSE AVANT la boucle -- le plancher qui distingue 1143 d'`AlphaWarrior`.
    BASE_UTILITY = 1.0
    #: `EntityExtensions.IsMachine(parent)` : `astraOrdnanceBattery` porte le trait `MachineOfWar`.
    MACHINE_PARENT = True

    def _spawn_tiles(self, ctx: NCContext, pos: tuple) -> list:
        """`IBattleQuery` slot 79 `GetAdjacentTiles(target, onlyEmptyOrSteppable: 1,
        onlyWalkableTiles: 1, allowTemporary: 1)` -- les tuiles adjacentes LIBRES et MARCHABLES.

        Mirror offline : le voisinage NATIF (`bq.neigh_map`, liste stockee, ni triee ni
        symetrisee) filtre par `ctx.walkable_by_pos` et par l'occupation VIVANTE (`ctx.epos` +
        `ctx.fpos`). Canal de voisinage muet -> `[]` (borne INF assumee : aucune tuile de spawn,
        donc utilite = le plancher 1, jamais une utilite inventee)."""
        neigh = bq.neigh_map(ctx)
        if not neigh:
            return []
        occupied = set(p for p in (ctx.epos or []) if p and p[0] is not None)
        occupied |= set(p for p in (ctx.fpos or []) if p and p[0] is not None)
        walk = ctx.walkable_by_pos or {}
        out = []
        for t in (neigh.get(pos) or []):
            if t in occupied:
                continue                                  # `onlyEmptyOrSteppable`
            if walk and walk.get(t) is False:
                continue                                  # `onlyWalkableTiles`
            out.append(t)
        return out

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        sid = SAR.summon_id(ActiveAbilityType(self.ABILITY_ID).name)
        best, scored = None, []
        for tid, pos in elig:
            util = self.BASE_UTILITY
            if pos is not None:
                for tile in self._spawn_tiles(ctx, pos):
                    if SAR.has_summon_target_in_attack_range_at_tile(
                            ctx, tile, sid, machine_parent=self.MACHINE_PARENT):
                        util += 1.0
            scored.append((tid, pos, util))
            if best is None or util > best[1]:            # `AddAction` : remplacement STRICT
                best = (tid, util)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] ForwardSpotter target=%s util=%s scored=%s"
                  % (ctx.uid, best[0], best[1], scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
