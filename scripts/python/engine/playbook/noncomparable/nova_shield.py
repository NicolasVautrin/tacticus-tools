"""NovaShieldPlaybook — marquage AoE tile-target NonComparable."""
from __future__ import annotations

import hexgeo
from engine.ai.utilities import get_movement_utility
from engine.utilities.utility_type import UtilityType
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, native_priority


class NovaShieldPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.NovaShieldPlaybook$$EvaluateNonComparable` (id 0x4aa=1194 ; tier
    get_Priority=**-1000** = `AbilityPriority.Last` : `NovaShieldPlaybook` SURCHARGE le slot 0 de
    l'interface IPlaybook — MESURE #170, sweep exhaustif des 257 ActiveAbilityType par invocation du
    slot 0 (`pbGate`) + voie independante `abilityPreferences`, 0 divergence ; `get_IsComparable` =
    False donc le tier est REELLEMENT exerce. Le 0 pose par #115 etait un FAUX NEGATIF de methode :
    les corps `mov eax,imm32 ; ret` sont dedupliques par IL2CPP, invisibles a un grep de symboles).
    IdunBattle.AI.Playbook.Loki.NovaShieldPlaybook$$.cctor : MIN_UTILITY=1. Marque un hex CENTRE + son ring-1 (hors trench), dégât AoE différé.
    Par (casterPos ∈ reach, center ∈ cibles-éligibles) :
        marked(center) = {center} ∪ neighbors(center) \\ trench          # IdunBattleLogic.Entities.Abilities.Active.Loki.NovaShieldAbility$$GetMarkedTiles
        util = 100*CountEnemiesOnTiles(marked) + Count(marked)            # IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CountEnemiesOnTiles (non-alliés) + get_Count
               + Tile(7)@casterPos + DislikeStartingTiles(28)@casterPos   # IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility
    Les 2 termes mouvement dépendent de `casterPos` SEUL (constants sur la boucle center). `ChooseAction`
    = argmax STRICT `>`, gate util >= 1. Cible native = le CENTRE marqué (kind=tile).
    MESURE #343 (decompile) : l'action emise est
    `IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(casterPosition, target, utility)` ->
    `IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)`, ou `target`
    est le champ `+0x10` de l'element du selector `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`
    (struct de 0x128 octets ; `+0x10` = l'ENTITE cible, ecrite juste apres `GetEligibleTargetsEntities`).
    Le port rendait `target: None` : il gardait l'argmax d'utilite mais JETAIT le centre argmax.
    Le natif n'emet JAMAIS de cible nulle ici — la cible EST le centre (entite-tuile, `ctx.tile_id_by_pos`).
    HYPOTHÈSE(trench) : flag isTrench non capturé -> ring géométrique complet (biais <=6 sur Count,
    écrasé par 100*enemies).
    STATUT : DECOMPILE-PROVEN, ARENE-INAGREABLE (Riptide non spawnable). L'ancienne note « classe
    TILE-target -> le natif BOUGE au tie -> sweep origine-LAST », deja marquee [UNVERIFIED], est
    RETIREE : elle reposait sur l'idee que l'ordre brut du generateur mettait l'origine en dernier.
    Le decompile dit l'inverse — la liste `tiles` vient de `ABaseAiUnitTactic$$GenerateActionTiles`
    -> `IBattleQuery`+0xe = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`,
    dont l'`OrderedSet` est SEEDE avec la position COURANTE. Il n'y a donc pas deux classes d'ordre :
    `ctx.reach_nc` est origine-FIRST pour tout le monde (R1). Reste vrai et inchange : l'utilite
    DEPEND ici de la position (100*ennemis marques), donc le tie-break n'est que secondaire.
    R2 : `DislikeStartingTilesUtility` no-op (poids BC non confirmé, arene-inagreable)."""
    ABILITY_ID = int(ActiveAbilityType.NovaShield)  # 1194
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(1194)   # -1000 = AbilityPriority.Last (surcharge mesuree, #170)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        centers = self._eligible_mark_centers(ctx)
        if not centers:
            return []
        epos = set(ctx.epos or [])
        board = ctx.elev_by_pos or {}
        best = None  # (caster_pos, center, util)
        for caster_pos in ctx.reach_nc:
            # GetMovementUtility(Tile) + IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility(DislikeStartingTiles) (2 appels natifs).
            move_term = (get_movement_utility(ctx, caster_pos, UtilityType.Tile)
                         + get_movement_utility(ctx, caster_pos, UtilityType.DislikeStartingTilesUtility))
            for center in centers:
                marked = [center] + [n for n in hexgeo.neighbors(*center)
                                     if (not board) or (n in board)]        # GetMarkedTiles \ trench
                n_enemy = sum(1 for t in marked if t in epos)               # IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CountEnemiesOnTiles
                u = 100.0 * n_enemy + len(marked) + move_term              # 100*enemies + get_Count(marked)
                if best is None or u > best[2]:   # strict > : 1re paire (pos, centre) du max garde
                    best = (caster_pos, center, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        caster_pos, center, u = best
        tid = (ctx.tile_id_by_pos or {}).get(center)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] NovaShield centers={len(centers)} best_to={caster_pos} "
                  f"center={center} tid={tid} u={u} min={self.MIN_UTILITY}", file=sys.stderr)
        return [{"target": (tid if tid is not None else center), "ability": self.ABILITY_ID,
                 "to": (caster_pos if caster_pos != ctx.origin else None), "pred": u}]

    def _eligible_mark_centers(self, ctx: NCContext) -> list[tuple]:
        """Mirror `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` : hex candidats du marquage
        (kind="tile") via l'RPC abilityTargets (union sur toutes les tuiles de move)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    out = [(t["tile"].get("col"), t["tile"].get("row"))
                           for t in (a.get("targets") or [])
                           if t.get("kind") == "tile" and t.get("tile")
                           and t["tile"].get("col") is not None]
        return out
