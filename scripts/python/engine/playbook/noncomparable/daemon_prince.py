"""Les DEUX faces DECISION de `thousDaemonPrince` (MACHINE OF WAR Thousand Sons) -- #978.

`AetherStride` (1208, SUMMON teleporte) et `InfernalCannon` (1209, DAMAGE) partagent leur porteur ;
leurs utilites n'ont rien en commun -- deux classes, un module (meme decoupage que
`ordnance_battery.py`).

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` : les deux derivent de
`IdunBattle.AI.Playbook.NonComparablePlaybook`1`. Leur `.ctor` decompile NOMME
`ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor` -- corps gshared trivial DEDUPLIQUE,
donc mislabele (piege #487-r1 / #945 / #957 / #967). C'est la STRUCTURE qui tranche, jamais le nom.

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` :
`active 1208 -> ...AetherStridePlaybook`, `active 1209 -> ...InfernalCannonPlaybook`. Les deux
sont des cles du dict `active` de `PlaybookDatabase` -- donc reellement construites.

PORTEUR = MACHINE OF WAR (`gameconfig thousDaemonPrince.traits = ['MachineOfWar']`). Deux
consequences STRUCTURELLES, les memes que #970 :
  * `ctx.reach_nc == []` (pas de `PositionComponent`) -> AUCUNE des deux ne peut heriter
    `_PlanTargetPlaybook`, dont le sweep de positions serait VIDE : elles seraient enregistrees
    et INERTES. On prend `NonComparablePlaybook` + le foyer `_targets.py` (`fromHere`).
  * `EntityExtensions.IsMachine(parent)` est VRAI -> `AetherStride` prend la branche
    `...WithMachineParent` du slot 195 (tous les ennemis, pas seulement le plus proche).

Les deux appellent l'overload **POSITION** de `GetEligibleTargetsSelectable(caster,
casterPosition)` -- pas l'overload TUILE (contraste 1102/1064 de la meme tranche). Pour une MoW
sans position les deux degenerent sur la meme unique position candidate, donc l'ecart est INERTE
ici ; il est cite parce qu'il est LU, pas parce qu'il mord.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.services import spawn_tile_shape as STS

import engine.playbook.noncomparable._targets as TGT              # FORME B, ABSOLU (#962)
import engine.playbook.noncomparable.summon_attack_range as SAR   # FORME B, ABSOLU -- slot 195
from ._base import NCContext, NonComparablePlaybook, _traits


# #979 -- `_CtxBoard` et `_occupied` sont DEPLACES dans le foyer partage du paquet (`_targets.py`)
# et re-exposes ici sous leur nom d'origine. Motif : `DutyEternal` (1158) consomme le MEME
# `ThreeTileUnitSpawnShape` -- ce sont les DEUX SEULES xrefs du selecteur dans le build --, et les
# recopier aurait fait le FORK DE FOYER que la docstring de `CtxBoard` interdit elle-meme.
_CtxBoard = TGT.CtxBoard
_occupied = TGT.occupied


class AetherStridePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.AetherStridePlaybook$$EvaluateNonComparable` (0x4b8 = 1208).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>( 0, Nullable(<statics+0x00>) )    # `.cctor` : Fix64(1)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
            util = Fix64(0)
            area = <AetherStrideAbility>$$GetTargetAreaTiles(this.ability@+0x68)
                       .<ITargetsSelector slot 0 = Select>(entities)
            a = HasAdjacentFriendlyPsyker(area, entities.Caster@+0x08)
            b = HasEnemyInRange(area, entities.Caster@+0x08)
            if ((a & b) != 0)  util += Fix64(1)
            bucket.AddAction( GenerateAction(casterPosition, entities.Target@+0x10, util) )

    Soit une utilite BOOLEENNE `0`/`1`, et `MIN_UTILITY` vaut exactement `1` : c'est donc un
    **VETO** -- seules les tuiles de spawn qui satisfont LES DEUX predicats sont proposees. Meme
    forme qu'`AlphaWarriorPlaybook` (1112), et contraste net avec `ForwardSpotterPlaybook` (1143)
    dont le plancher `Fix64(1)` POSE AVANT la boucle fait passer toute cible.

    ⚠ LES DEUX PREDICATS SONT EVALUES, PAS COURT-CIRCUITES : le natif calcule `a` puis `b` puis
    teste `(a & b)` (ET bit-a-bit sur deux valeurs deja produites), il n'ecrit pas un `&&`. Sans
    effet observable ici -- aucun des deux n'a d'effet de bord -- mais c'est ce qui est ecrit.

    ⚠ LES DEUX PREDICATS NE PARTAGENT PAS LEUR TUILE. Chacun balaie l'aire ENTIERE de son cote et
    rend au premier succes : l'ami psyker peut etre adjacent a `area[0]` pendant que la cible a
    portee ne l'est que depuis `area[2]`. Exiger LA MEME tuile pour les deux serait plus strict que
    le natif.

    LE NOM QUE GHIDRA DONNE EST CELUI D'UNE AUTRE ABILITY
    -----------------------------------------------------
    `GetTargetAreaTiles` est appelee sur `this.ability@+0x68`, qui EST une `AetherStrideAbility` --
    mais Ghidra la nomme
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$GetTargetAreaTiles`. Corps
    FONDU par ICF, donc corps IDENTIQUE, donc lisible tel quel :

        return DSLSelectors.ThreeTileUnitSpawnShape(dsl, <dsl+0x60 = Target>)

    `<dsl+0x60>` est le referent **Target** (le meme que le `Target` de
    `MalleusRocketLauncherPlaybook` et de `...DutyEternalAbility$$ExecuteBehaviour`) : l'empreinte a
    3 pieds est ancree sur la TUILE VISEE, jamais sur le caster. Et ce nom-la n'est pas un accident
    de dedup : `spawn_tile_shape` releve que les XREFS EXHAUSTIVES de `ThreeTileUnitSpawnShape` sont
    exactement `AetherStrideAbility` et `DutyEternalAbility` -- les deux seules du build.

    LES DEUX SLOTS, LUS DANS `data/symbols/<build>/metadata/interface_slots.tsv`
    ---------------------------------------------------------------------------
    * **131 = 0x83** `GetAdjacentFriends(2 params)` -> `GetAdjacentFriends(tile, caster)`.
    * **195 = 0xc3** `HasSummonTargetInAttackRangeAtTile(3 params)` -> foyer
      `summon_attack_range.py`, branche `machine_parent=True` (le porteur est une MoW).

    `<AetherStrideAbility>$$GetSummonId` est ici INLINE dans `HasEnemyInRange` :
    `AbilityConfiguration.GetStringConstant(this.ability@+0x68 .config@+0x60, 0)`, et l'index 0 EST
    `unitId` -- `thousSmnDaemonPrince` pour 1208 (LU au gameconfig, jamais code en dur).

    LE TRAIT EST NOMME, PAS DEVINE : `UnitExtensions.HasTrait(unit, 0x3ea)` et `0x3ea = 1002 =
    UnitTrait.Psyker` (`engine/entities/traits/unit_trait.py`). Le meme ordinal est deja cite par
    `effects/base.py` (`UnitsWithTrait(0x3ea)` = les psykers ennemis de DaughterOfTheAbyss)."""
    ABILITY_ID = int(ActiveAbilityType.AetherStride)     # 0x4b8 = 1208 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `AetherStridePlaybook$$.cctor` : `FixMath.NET.Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `if ((a & b) != 0) util += Fix64(1)` -- l'unique increment du corps.
    BOTH_PREDICATES_UTILITY = 1.0
    #: `EntityExtensions.IsMachine(parent)` : `thousDaemonPrince` porte le trait `MachineOfWar`.
    MACHINE_PARENT = True

    def _area(self, ctx: NCContext, anchor: tuple) -> list:
        """`ThreeTileUnitSpawnShape(Target).Select(entities)` = l'empreinte a 3 pieds ancree sur la
        tuile visee, ou `[]` si aucune des six directions ne porte d'aire valide.

        Le corps geometrique est le foyer `spawn_tile_shape.get_area` (deja porte et confronte
        live sur `DutyEternal`) ; ce module ne lui fournit que le plateau et l'occupation."""
        return STS.get_area(_CtxBoard(ctx), _occupied(ctx), anchor)

    def _has_adjacent_friendly_psyker(self, ctx: NCContext, area: list) -> bool:
        """`AetherStridePlaybook$$HasAdjacentFriendlyPsyker(area, caster)` -- MIRROR :

            foreach (tile in area)
                foreach (unit in battleQuery.<slot 131>(tile, caster))     # GetAdjacentFriends
                    if (UnitExtensions.HasTrait(unit, 0x3ea = Psyker)) return true;
            return false;

        Substrat : `ctx.fpos` (positions ALLIEES, self exclu -- le canal `GetAdjacentFriends` du
        port) filtre par le voisinage NATIF (`bq.neigh_map`, liste stockee, ni triee ni
        symetrisee) et la porte d'elevation d'`IterateAdjacentTiles` -- les deux etages, comme
        `_get_num_attack_targets_in_position` le rappelle. Le trait se lit sur le `visualId` que
        `ctx.obs_units` publie a cette position."""
        fpos = [p for p in (ctx.fpos or []) if p and p[0] is not None]
        if not fpos or not area:
            return False
        vid_by_pos = {(u.get("col"), u.get("row")): u.get("visualId")
                      for u in (ctx.obs_units or [])
                      if not u.get("isDead") and u.get("col") is not None}
        neigh = bq.neigh_map(ctx)
        psyker = [p for p in fpos
                  if int(UnitTrait.Psyker) in _trait_ids(vid_by_pos.get((p[0], p[1])))]
        if not psyker:
            return False
        for tile in area:
            # `count_adjacent` porte les DEUX etages natifs (voisinage stocke + |dElev| < 2) ;
            # `> 0` mirrore le `return true` au premier psyker trouve.
            if bq.count_adjacent(tile, psyker, ctx.elev_by_pos, neigh) > 0:
                return True
        return False

    def _has_enemy_in_range(self, ctx: NCContext, area: list) -> bool:
        """`AetherStridePlaybook$$HasEnemyInRange(area, caster)` -- MIRROR :

            summonId = AbilityConfiguration.GetStringConstant(this.ability.config@+0x60, 0)
            foreach (tile in area)
                if (battleQuery.<slot 195>(caster, summonId, tile)) return true;
            return false;

        Le `summonId` est relu a CHAQUE tour de boucle par le natif ; il est invariant, donc on le
        resout une fois -- seule difference, et elle n'est pas observable."""
        sid = SAR.summon_id(ActiveAbilityType(self.ABILITY_ID).name)
        for tile in (area or []):
            if SAR.has_summon_target_in_attack_range_at_tile(
                    ctx, tile, sid, machine_parent=self.MACHINE_PARENT):
                return True
        return False

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # Domaine TUILE : l'ancre de `ThreeTileUnitSpawnShape` est la tuile visee. `eligible_any`
        # (et non `eligible_tiles`) parce que le corps natif ne teste RIEN sur le contenu de la
        # cible -- il la passe telle quelle au selecteur ; le domaine se LIT dans la reponse, il ne
        # se devine pas (meme raison que `MalleusRocketLauncherPlaybook`).
        elig = TGT.eligible_any(ctx, self.ABILITY_ID)
        if not elig:
            return []
        best, scored = None, []
        for tid, pos, _kind in elig:
            util = 0.0
            if pos is not None:
                area = self._area(ctx, pos)
                a = self._has_adjacent_friendly_psyker(ctx, area)
                b = self._has_enemy_in_range(ctx, area)     # PAS de court-circuit : le natif
                if a and b:                                 # calcule les deux puis fait `a & b`
                    util += self.BOTH_PREDICATES_UTILITY
            scored.append((tid, pos, util))
            if best is None or util > best[1]:              # `AddAction` : remplacement STRICT
                best = (tid, util)
        if best is None or best[1] < self.MIN_UTILITY:      # gate Bucket `util >= min` -> VETO
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] AetherStride target=%s util=%s scored=%s"
                  % (ctx.uid, best[0], best[1], scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


class InfernalCannonPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.InfernalCannonPlaybook$$EvaluateNonComparable` (0x4b9 = 1209).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>( 0, Nullable(<statics+0x00>) )    # `.cctor` : Fix64(1)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
            util = Fix64(1)                                               # PLANCHER, avant le test
            u = UnitExtensions.GetUnit(entities.Target@+0x10, this.state@+0x20)
            if (u != null && UnitExtensions.IsEnemy(u, entities.Caster@+0x08, state))
                util += Fix64( UnitExtensions.GetStat(u, 5, 2, 0) )
            bucket.AddAction( GenerateAction(casterPosition, entities.Target@+0x10, util) )

    Soit : **1 + les PV MAXIMUM de la cible si c'est un ennemi**. Le canon vise donc la plus GROSSE
    cible ennemie -- et, `MIN_UTILITY` valant `1`, une cible sans occupant ou amie passe quand meme
    le gate a l'utilite plancher `1` (elle ne gagne l'argmax que si elle est seule).

    ⚠ **`statPart = 2 = Maximum`, PAS `Current`** -- et c'est le seul endroit ou le port peut se
    tromper sans que rien ne le dise. `GetStat(actor, statType, statPart, entityId)` :
      * ici          `GetStat(u, StatType.Health = 5, StatPart.Maximum = 2, 0)` ;
      * `MindControlPlaybook` (1164) et `VexillaMagnificaPlaybook` ecrivent le MEME `5` avec
        `StatPart.Current = 0` ;
      * `ExemplarOfHatePlaybook` (1140) ecrit `StatPart.CurrentPct = 1`.
    Les trois ont le meme squelette et lisent trois stats DIFFERENTES : l'ordinal du 3e argument est
    tout le discriminant. Les noms sont lus dans `frida/enums.tsv`
    (`IdunBattle.Entities.Enum.StatPart`), jamais devines.

    ⚠ `IsEnemy(u, entities.Caster, ...)` compare a l'**occupant de l'AbilityEntities**, pas au
    `caster` argument de la methode. Les deux valent le caster ici (`GetEligibleTargetsSelectable`
    ecrit `caster` a `+0x08` ET a `+0x18`), donc l'ecart est INERTE -- transcrit parce que lu.

    PRIORITY = **-100** (`AbilityPriority.Late`), deja presente dans la table mesuree
    `NATIVE_PRIORITY` (_base.py, sweep exhaustif #170 des 258 valeurs d'enum). Consequence
    EXERCEE et non theorique : `thousDaemonPrince` porte AUSSI `AetherStride` (tier 0), donc le
    generateur du tier 0 est evalue AVANT celui du tier -100 -- si `AetherStride` passe son veto,
    `InfernalCannon` n'est jamais atteinte, par l'ORDRE DES GENERATEURS et non par comparaison
    d'utilites. C'est le seul couple de la tranche ou les deux tiers coexistent sur une meme
    unite."""
    ABILITY_ID = int(ActiveAbilityType.InfernalCannon)   # 0x4b9 = 1209 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `InfernalCannonPlaybook$$.cctor` : `FixMath.NET.Fix64.op_Implicit(1)`
    #: `NATIVE_PRIORITY[InfernalCannon] = -100` -- mesure #170, pas une deduction.
    PRIORITY = -100

    #: `utility = Fix64(1)` POSE AVANT le test -- le plancher que toute cible eligible conserve.
    BASE_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_any(ctx, self.ABILITY_ID)
        if not elig:
            return []
        # `GetStat(u, Health, Maximum)` : `observeBattle.hpMax` = `HealthComponent.hp_max`, le seul
        # canal de PV MAX de `NCContext`. Cle = `squadId` (l'id d'unite de `obs_units`).
        hpmax_by_id, hpmax_by_pos, enemy_pos = {}, {}, set()
        for u in (ctx.obs_units or []):
            if u.get("isDead"):
                continue
            if u.get("squadId") is not None:
                hpmax_by_id[u["squadId"]] = int(u.get("hpMax") or 0)
            if u.get("col") is not None:
                hpmax_by_pos[(u["col"], u["row"])] = int(u.get("hpMax") or 0)
        for p in (ctx.epos or []):
            if p and p[0] is not None:
                enemy_pos.add((p[0], p[1]))
        best, scored = None, []
        for tid, pos, kind in elig:
            util = self.BASE_UTILITY
            # `GetUnit(target) != null && IsEnemy(...)` : la cible porte-t-elle un ENNEMI vivant ?
            # `ctx.epos` EST le canal « positions ennemies » du port (slot `GetAdjacentEnemies`),
            # donc l'appartenance a `epos` porte les DEUX conjoints a la fois.
            if pos is not None and pos in enemy_pos:
                hp_max = hpmax_by_id.get(tid) if kind == "unit" else None
                if not hp_max:
                    hp_max = hpmax_by_pos.get(pos) or 0
                util += float(hp_max)          # GetStat(u, Health = 5, Maximum = 2)
            scored.append((tid, pos, util))
            if best is None or util > best[1]:              # `AddAction` : remplacement STRICT
                best = (tid, util)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] InfernalCannon target=%s util=%s scored=%s"
                  % (ctx.uid, best[0], best[1], scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


def _trait_ids(visual_id) -> set:
    """Les traits gameconfig d'un `visualId`, **en ORDINAUX** -- le substrat de
    `UnitExtensions$$HasTrait(unit, <ordinal>)`.

    `_base._traits` rend les NOMS (`['Hero', 'Psyker', ...]`) ; le natif, lui, teste un ordinal.
    On convertit par le mirror `UnitTrait`, et un nom inconnu du mirror est IGNORE plutot que
    devine -- il ne peut alors que faire manquer un psyker (degradation conservatrice, dans le
    sens du veto), jamais en inventer un."""
    out = set()
    for name in (_traits(visual_id) or []):
        try:
            out.add(int(UnitTrait[str(name)]))
        except (KeyError, ValueError):
            continue
    return out
