"""TheQuickeningPlaybook — teleport-echange NonComparable (utilite = paliers +1 cumulatifs)."""
from __future__ import annotations

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.triggered_ability_type import triggered_ability_ids

from ._base import (NCContext, NonComparablePlaybook, _unit_cfg,
                    _get_num_attack_targets_in_position, _sweep_origin_first)

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

    ⚠ PAS ENREGISTRE dans `PLAYBOOKS` (cf. `__init__.py`) — PORTE DE DECISION NATIVE NON RESOLUE.
    Mesure live (seed 31337, board MC1_67, 2026-07-20) :
      - pas 5 (u81 origine (5,8), 21 tuiles de move, `abilityTargets` = 36 tuiles valides, ability
        `usable=true`) : le NATIF joue l'attaque NORMALE (ab 69 sur u95) et N'EMET PAS 1151 — alors
        que l'unique gate du decompile (`GetNumAttackTargetsInPosition(caster, T) > 0`) passe pour
        de nombreuses tuiles, y compris (3,5) qui est justement la tuile d'ou le natif attaque.
      - pas 15 (origine (3,5), 4 tuiles de move) : le natif EMET 1151 vers la tuile 52 = (4,4).
    Une NonComparable qui « sort » prime sur toute Comparable PAR L'ORDRE des generateurs : si le
    playbook avait produit une action au pas 5, le natif n'aurait pas pu attaquer. Il MANQUE donc une
    porte (ShouldEvaluate ? usabilite runtime ? condition de round ?) invisible dans
    `EvaluateNonComparable @18116afb0` (aucun `ShouldEvaluate`/`ShouldExecute` sur ce playbook dans la
    table des symboles). Enregistrer en l'etat = sur-tir MESURE (anti-pattern #31) -> on attend le RE
    de la porte. Second point ouvert : l'utilite est PLATE (tous les candidats a 2.0 = base 1 + palier
    FuryOfTheAncients) quand aucune tuile cible ne porte d'ami -> l'accord de CIBLE se joue alors sur
    l'ORDRE d'enumeration (keep-first du Bucket), pas sur l'utilite.

    Ecarts assumes : (1) l'eligibilite par position est reconstituee en filtrant l'union
    `abilityTargets` (`GetAllValidTargetsFromAllPossibleMovementTiles`) par distance HEX <= 2 de la
    position balayee — le natif dit « movement range 2 » (distance de CHEMIN) ; (2)
    `GetNumAttackTargetsInPosition` est porte via le plan natif, donc vaut 0 pour un ALLIE quand le
    contexte ne fournit pas son plan (bridge offline) -> le 3e palier degrade a la baisse."""
    ABILITY_ID = int(ActiveAbilityType.TheQuickening)  # 1151
    MIN_UTILITY = 1.0     # cctor @18116b550 = Fix64(1)
    PRIORITY = 0

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
        best = None      # (util, position, targetTile)
        for P in _sweep_origin_first(ctx):
            for T in tiles:
                if hexgeo.distance(P, T) > _RANGE:
                    continue      # hors portee depuis CETTE position (eligibilite par-position)
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
