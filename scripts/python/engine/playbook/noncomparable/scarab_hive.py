"""ScarabHivePlaybook — summon d'attaque NonComparable (utilite plate, gate #tuiles-libres adjacentes cible)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class ScarabHivePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ScarabHivePlaybook$$EvaluateNonComparable` (id 0x3ef=1007, necroSpyder/Canoptek Spyder).
    Summon d'attaque : `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` fait apparaitre N=2 Scarab Swarms
    (necroSmnSwarm) sur des tuiles adjacentes a la CIBLE (`AdjacentTiles(target) -> CanAddUnit -> First(N)
    -> Spawn`), qui attaquent immediatement, + effet 0x4a3 OverrideDamageProfile (Piercing au 1er coup).

    Structure native (mirror EvaluateNonComparable) : pour chaque cible eligible
    (`GetEligibleTargetsSelectable(MainTile=position)`), lit `iVar1 = ability+0xf0` (= N=2, IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$.ctor : `*(this+0xf0)=2`) puis `count = query.slot0x4e(target,1,1,1).Count` ; SI `count >= iVar1`
    -> `GenerateAction(position, cible, Fix64.FromInt(1))` + `Bucket.AddAction`. Utilite CONSTANTE 1.0.
    slot 0x4e (IBattleQuery DAT_18327ff80) = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(target,1,1,1)` (memes bools que
    HammerOfWrath #116 : requireEmptyOrSteppable/requireWalkable/allowTemporary) -> tuiles adjacentes LIBRES
    placables = `GetPossibleSpawnTiles`/`GetFreeAdjacentTiles`. Le gate = "assez de place pour les 2 scarabs".

    RECONCILIATION LIVE (seed 2468 s9 u79, board MC1_67, ncEvaluate) : seule pos(4,5) -> cible u93 util=1
    (freeAdj(u93)=3 tuiles libres >= 2) ; toutes les autres positions -> bucket vide (u93 hors portee).
    Le natif : move (4,5) + ScarabHive->u93. Le moteur ratait car ScarabHive absent (retombait sur l'attaque
    normale 69). NonComparable -> une fois enregistre, il prime sur l'attaque normale (Comparable).

    - utilite = 1.0 CONSTANTE par cible eligible passant le gate (Fix64.FromInt(1) IdunBattle.AI.Playbook.Loki.ScarabHivePlaybook$$EvaluateNonComparable).
    - gate = `adjacent_addable_count(tuile-cible) >= N` avec N=2 (= #scarabs, IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$.ctor). Primitive
      = celle de HammerOfWrath (_displacement_bonus, #116) : GetAdjacentTiles(cible) filtre par CanAddUnit
      (walkable + vide, porte |dElev|<2). Occupation = epos U fpos U origine (TOUTES unites vivantes).
    - PAS de MIN_UTILITY explicite (Bucket ctor 2-arg IdunBattle.AI.Playbook.Loki.ScarabHivePlaybook$$EvaluateNonComparable -> min defaut ; util 1 toujours admise).
    - IdunBattle.AI.Playbook.Loki.ScarabHivePlaybook$$.ctor = `NonComparablePlaybook(0x3ef)` -> 1er arg=ability_id ; PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).
    - cible = ENNEMI eligible (kind unit) ; position = 1re tuile atteignable (movable order) d'ou la cible
      est castable (`cast_from_tiles`). Cibles multiples passant le gate -> util egale (1.0) -> le driver
      choose_action garde la 1re (mirror bucket keep-first sur l'ordre GetEligibleTargetsSelectable)."""
    ABILITY_ID = int(ActiveAbilityType.ScarabHive)  # 1007
    MIN_UTILITY = 1.0     # util constante 1 ; gate reel = adjacent_addable_count(cible) >= N
    PRIORITY = 0
    _N_SUMMONS = 2        # ability+0xf0 = 2 (IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$.ctor) = #scarabs -> seuil du gate

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # cibles ENNEMIES eligibles (GetEligibleTargetsSelectable = kind unit) dans l'ordre natif.
        elig: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        elig.append(t["targetId"])
        if not elig:
            return []
        occupied = bq.occupied_positions(ctx)     # #969-r3 : PAR PIED (`TileContentComponent`)
        cands: list[dict] = []
        for T in elig:                       # ordre GetEligibleTargetsSelectable -> keep-first au tie
            tp = self._pos_of(ctx, T)
            if tp is None:
                continue
            # gate : #tuiles adjacentes LIBRES a la CIBLE >= N (place pour les 2 scarabs).
            free = bq.adjacent_addable_count(tp, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                             occupied, ctx.elev_by_pos)
            if free < self._N_SUMMONS:
                continue
            to = self._first_cast_pos(ctx, T)
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] ScarabHive tgt={T} free={free}>=N{self._N_SUMMONS} to={to}",
                      file=sys.stderr)
            cands.append({"target": T, "ability": self.ABILITY_ID, "to": to, "pred": 1.0})
        return cands

    @staticmethod
    def _pos_of(ctx: NCContext, uid: int):
        u = next((x for x in (ctx.units or []) if x.get("id") == uid), None)
        p = (u or {}).get("pos") if u else None
        if p and p.get("col") is not None:
            return (p["col"], p["row"])
        return None

    def _first_cast_pos(self, ctx: NCContext, T: int):
        """1re position (ordre movable natif) d'ou ScarabHive->T est castable (`cast_from_tiles`).
        currentValid -> caste en place (to=None). Seam absente -> None (le natif a bouge (4,5) au miss)."""
        if ctx.cast_from_tiles is None:
            return None
        try:
            cf = ctx.cast_from_tiles(ctx.uid, T, self.ABILITY_ID) or {}
        except Exception:
            return None
        if cf.get("currentValid"):
            return None
        posset = {(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])
                  if t.get("col") is not None}
        for P in (ctx.reach_nc or []):
            if P in posset:
                return None if P == ctx.origin else P
        return None
