"""TheQuickeningPlaybook — teleport-echange NonComparable (utilite = paliers +1 cumulatifs)."""
from __future__ import annotations

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.triggered_ability_type import triggered_ability_ids

from ._base import (NCContext, NonComparablePlaybook, _unit_cfg,
                    _get_num_attack_targets_in_position, _sweep_origin_first,
                    _turns_started_gate)

_FURY_OF_THE_ANCIENTS = 1247   # 0x4df — HasTriggeredAbility(caster, 0x4df)
_RANGE = 2                     # gameconfig `range:2` (« a hex within movement range 2 »)


class TheQuickeningPlaybook(NonComparablePlaybook):
    """`TheQuickeningPlaybook.EvaluateNonComparable @18116afb0` (id 0x47f=1151, bloodMephiston).

    NonComparable a utilite ENTIERE (aucun `Make*Predictions` — reframe #34) : Mephiston se teleporte sur
    un hex a portee 2 ; l'ami eventuellement present y est ECHANGE vers la position du caster. La cible
    natives est une TUILE (entite tuile), pas une unite.

    Utilite (paliers `Fix64.FromInt(1)` cumulatifs, evalues DANS CET ORDRE) :
      - base = champ statique [0] du cctor @18116b550 = `Fix64.FromInt(1)` ;
      - GATE : `GetNumAttackTargetsInPosition(caster, targetTile) == 0 -> continue` (le natif ne se
        teleporte QUE sur une tuile d'ou il peut attaquer) ;
      - `other` = unite sur la tuile (nulle si c'est le caster lui-meme) ; si `IsFriend(other, caster)` :
        `+1` ; puis si `HasFaction(other, GetFaction(caster))` : `+1` ; puis si
        `GetNumAttackTargetsInPosition(other, position)` > 0 (l'ami echange pourra attaquer depuis la
        position du caster) : `+1` ;
      - si `HasTriggeredAbility(caster, 0x4df=FuryOfTheAncients)` ET `caster.MainTile != position.MainTile`
        (le caster a DEJA bouge dans ce balayage) : `+1`.
    `MIN_UTILITY` = meme champ statique = 1 -> le gate discriminant est `GetNumAttackTargetsInPosition`.
    `PRIORITY`=0 (#115). `GenerateAction(position, targetTile, util)` -> la cible emise est l'ID D'ENTITE
    DE LA TUILE (`ctx.tile_id_by_pos`), pas un id d'unite.

    PORTE DE DECISION RESOLUE (#46, 2026-07-20) : le gate manquant = slot 4 `ShouldEvaluate(unit)`
    de la vtable (klass+0x298, resolu LIVE via `resolveVtableSlot`) -> corps FOLDE @18111af90
    (`AlphaWarriorPlaybook$$ShouldEvaluate`) = `GetStat(unit, 0xc=TurnsStarted) > 1` : 1151 n'est
    JAMAIS evaluee au PREMIER tour de l'unite (`should_evaluate` = `_turns_started_gate`).
    Mesures concordantes (seed 31337, board MC1_67) : pas 5 (1er tour u81, turnsStarted=1) ->
    slot4=0 (8/8) -> le natif attaque normal ; pas 15 (2e tour) -> slot4=1 -> le natif emet 1151 ;
    step 0 build frais (turnsStarted=0) -> slot4=0. NB : `BasePlaybook.ShouldEvaluate @18111fb70`
    (voie `prob := vtable[0x1f8] GetUseProbability`) n'est PAS l'impl de ce playbook (les 2
    surcharges de base @18111f9b0/@18111fa00 = `Fix64(1)` constant, verifie live = 1.0) — la piste
    « prob<=0 » du 1er RE etait la MAUVAISE implementation. La correlation RapidAssault (n=2)
    etait un PROXY du 1er tour, pas le mecanisme (anti-fit respecte).
    Point residuel : `ncEvaluate` au pas 15 rend util=3 sur exactement l'action native (4,5)->
    tuile 52 (u79 allie -> 3e palier) -> l'utilite n'est PAS plate dans le cas mesure ; le
    keep-first du Bucket ne departage que les vrais ties.

    Eligibilite PAR POSITION (#32, fixe 31337 s15) : cibles = union `abilityTargets`
    (`GetAllValidTargetsFromAllPossibleMovementTiles` ; inclut les tuiles ALLIE-occupees — mesure
    pas 15 = 25 tuiles dont (4,4) occupee par u79, la cible native), et POSITIONS legales PAR cible
    = `castFromTiles` (seam `ctx.cast_from_tiles` = `GetInvalidTargetReason` par tuile de move) —
    la « movement range 2 » native est une distance de CHEMIN : l'ancien filtre hex-dist <= 2
    admettait (3,6)->tuile 52 (illegal natif) et cassait le tie util=3 vers (3,6) quand le natif
    n'avait que origine(2)/(4,5)(3). Le fallback hex-dist reste si la seam est absente.
    Ecart assume : `GetNumAttackTargetsInPosition` est porte via le plan natif + FALLBACK geometrique
    MELEE hors univers movable (#46, cf. `_base`) — la partie RANGED du fallback (portee+LoS) n'est
    pas portee -> borne inf residuelle pour un allie echange purement ranged."""
    ABILITY_ID = int(ActiveAbilityType.TheQuickening)  # 1151
    MIN_UTILITY = 1.0     # cctor @18116b550 = Fix64(1)
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable (0x298) -> corps foldé @18111af90 : `turnsStarted > 1` (#46)."""
        return _turns_started_gate(ctx)

    def _eligible_target_tiles(self, ctx: NCContext) -> list[tuple]:
        """`GetEligibleTargetsSelectable` (tuiles) : union `abilityTargets` kind=tile (le filtre
        par-position est applique par l'appelant)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tl = t.get("tile") if t.get("kind") == "tile" else None
                    if tl and tl.get("col") is not None:
                        out.append((tl["col"], tl["row"]))
        return list(dict.fromkeys(out))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        tiles = self._eligible_target_tiles(ctx)
        if not tiles:
            return []
        me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
        my_team = (me or {}).get("team")
        my_faction = _unit_cfg((me or {}).get("visualId")).get("FactionId")
        has_fury = _FURY_OF_THE_ANCIENTS in (triggered_ability_ids((me or {}).get("visualId")) or ())
        unit_by_pos = {}
        for u in (ctx.units or []):
            if u.get("alive") is False:
                continue
            p = u.get("pos")
            if p and p.get("col") is not None:
                unit_by_pos[(p["col"], p["row"])] = u
        # Eligibilite PAR POSITION native (#32, 31337 s15) : `castFromTiles` (seam ctx.cast_from_tiles)
        # = `GetInvalidTargetReason` valide par tuile de move — la « movement range 2 » native est une
        # distance de CHEMIN, PAS l'hex-dist ((3,6)->tuile 52 : hex-dist 2 mais cast ILLEGAL natif ->
        # notre tie util=3 a (3,6) etait un FAUX eligible ; natif = origine(2) vs (4,5)(3) -> (4,5)).
        # Fallback hex-dist <= _RANGE si la seam est absente (borne sup, comportement pre-#32).
        elig_by_T: dict = {}
        if ctx.cast_from_tiles is not None:
            for T in tiles:
                tid = ctx.tile_id_by_pos.get(T)
                if tid is None:
                    continue
                try:
                    cf = ctx.cast_from_tiles(ctx.uid, tid, self.ABILITY_ID) or {}
                except Exception:
                    continue                        # RPC KO -> fallback hex-dist pour cette tuile
                posset = {(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])
                          if t.get("col") is not None}
                if cf.get("currentValid") and ctx.origin is not None:
                    posset.add(ctx.origin)
                elig_by_T[T] = posset
        best = None      # (util, position, targetTile)
        for P in _sweep_origin_first(ctx):
            for T in tiles:
                elig = elig_by_T.get(T)
                if elig is not None:
                    if P not in elig:
                        continue  # cast (1151 -> T) ILLEGAL depuis cette position (natif)
                elif hexgeo.distance(P, T) > _RANGE:
                    continue      # fallback : hors portee hex depuis CETTE position
                if _get_num_attack_targets_in_position(ctx, ctx.uid, T) == 0:
                    continue      # gate natif : rien a attaquer depuis la tuile d'arrivee
                util = 1.0
                other = unit_by_pos.get(T)
                if other is not None and other.get("id") == ctx.uid:
                    other = None                     # `lVar13 != param_2` : le caster ne compte pas
                if other is not None and my_team is not None and other.get("team") == my_team:
                    util += 1.0                      # IsFriend
                    if my_faction and _unit_cfg(other.get("visualId")).get("FactionId") == my_faction:
                        util += 1.0                  # HasFaction(other, GetFaction(caster))
                        if _get_num_attack_targets_in_position(ctx, other.get("id"), P) > 0:
                            util += 1.0              # l'ami echange pourra attaquer depuis `P`
                if has_fury and P != ctx.origin:
                    util += 1.0                      # FuryOfTheAncients + le caster a deja bouge
                if ctx.debug:
                    import sys
                    print(f"    [dbg TheQuickening u{ctx.uid}] cand pos={P} tile={T} "
                          f"tid={ctx.tile_id_by_pos.get(T)} util={util}", file=sys.stderr)
                if best is None or util > best[0]:   # Bucket.AddAction : remplacement STRICT `>`
                    best = (util, P, T)
        if best is None or best[0] < self.MIN_UTILITY:
            return []
        util, P, T = best
        if ctx.debug:
            import sys
            print(f"    [dbg TheQuickening u{ctx.uid}] pos={P} tile={T} util={util}", file=sys.stderr)
        return [{"target": ctx.tile_id_by_pos.get(T), "ability": self.ABILITY_ID,
                 "to": (P if P != ctx.origin else None), "pred": util}]
