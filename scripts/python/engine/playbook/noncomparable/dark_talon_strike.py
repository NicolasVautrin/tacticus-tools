"""DarkTalonStrikePlaybook — beam en ligne NonComparable (cible = TILE ; util = #ennemis continus
touches par le rayon depuis le caster a travers la tuile visee)."""
from __future__ import annotations

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def _beam_count(origin: tuple, aim: tuple, enemy_set: set) -> int:
    """#ennemis CONTINUS sur le rayon droit depuis `origin` a travers `aim`, en partant de `aim`
    vers l'exterieur (`TilesBehindInLine` + `FilterContinuous(hasUnit & areEnemies)` IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine).
    Extension en coordonnees CUBE (rayon droit parite-independant) : dir = cube(aim)-cube(origin)
    (aim ADJACENT -> pas unitaire) ; on avance k=1,2,... tant que la tuile est un ennemi. Le compte
    S'ARRETE au 1er trou (tuile sans ennemi) = continuite du beam."""
    ox, _oy, oz = hexgeo.to_cube(origin[0], origin[1])
    ax, _ay, az = hexgeo.to_cube(aim[0], aim[1])
    dx, dz = ax - ox, az - oz
    if dx == 0 and dz == 0:
        return 0
    cnt, k = 0, 1
    while k <= 12:
        tile = hexgeo.from_cube(ox + dx * k, oz + dz * k)
        if tile in enemy_set:
            cnt += 1
            k += 1
        else:
            break
    return cnt


class DarkTalonStrikePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable` (id 0x444=1092, Loki/darkaAzrael).
    Attaque en LIGNE (beam) : `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` tire un rayon qui
    frappe tous les ennemis alignes. La cible de DECISION = une TILE (l'aim du beam ; targetId natif =
    l'ENTITE-TUILE, id BAS ~43, PAS une unite).

    Structure native (mirror EvaluateNonComparable) : Bucket ctor 3-arg, min = Nullable(Fix64(2))
    (IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.cctor pose `**(DAT_1831e5be8+0xb8)=Fix64(2)` -> MIN_UTILITY=2). Par position balayee,
    enumere `GetEligibleTargetsSelectable(MainTile=P)` (= tuiles-ennemi ou aimer, kind=tile) ; pour
    CHAQUE tuile eligible T :
      bestLine = `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine(ability)` (DSL AdjacentTiles + SortByFormula angle/count
                  + First) ; `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetAttackTargets(bestLine)` = `Enemies(Units(bestLineTiles))` ;
      `util = Fix64.FromInt( <slot2>(attackTargets, T) )` = #ennemis touches par le rayon vise sur T ;
      GenerateAction(P, T, util) + Bucket.AddAction (argmax STRICT `>`, keep-first au tie).

    RECONCILIATION LIVE (ncEvaluate, seed 54321 s11 u91 darkaAzrael, board MC1_67) : caster (3,3),
    tuiles eligibles fromHere = {(3,4),(4,3),(4,2)} (ennemis adjacents). util(aim (3,4)) = 5 = les 5
    ennemis CONTINUS sur la colonne 3 : u81(3,4), u140-decoy(3,5), u85(3,6), u77(3,7), u159(3,8) ;
    aim (4,3)/(4,2) = 1. Le natif caste EN PLACE (origine (3,3) = util 5 max) sur la tuile (3,4) =
    entity 43 (tgtLow 751647920 @ncEvaluate). La feuille beam offline (`_beam_count`, rayon cube droit
    continu) reproduit AU BIT les util 5/1/1. Le moteur ratait car 1092 absent du registre -> le traitait
    en attaque Comparable et visait une UNITE (t83).

    - cible = TILE : l'aim maximisant `_beam_count` depuis l'origine (fromHere) ; emise comme
      `tile_id_by_pos[aim]` (entity-tuile, ce que l'agreement compare = 43). util = beam count.
    - MIN_UTILITY=2 (cctor) : n'aime QUE si >= 2 ennemis alignes ; sinon fallback Comparable.
    - position : sweep ORIGINE-FIRST keep-first -> cast EN PLACE (to=None) quand l'origine porte l'aim
      max (cas s11 ; confirme par les castes en place de la tranche). PRIORITY=0 (#115).
    - IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.ctor = `NonComparablePlaybook(0x444)` -> 1er arg=ability_id.

    FLAGS VALIDATEUR (approximations) :
      * beam = RAYON DROIT continu (cube-line) ; la vraie geometrie `GetTilesInBestLine` inclut une
        variante ANGLE (AngleBetweenLines + SortByFormula) / ligne coudee NON modelisee. A s11 le rayon
        droit colle exactement (5/1/1). Un beam coude ne serait pas fidele.
      * AIM depuis l'ORIGINE uniquement (`fromHere`) : le natif balaie aussi les tuiles de MOVE (aimer
        apres deplacement). Non modelise -> si le natif MOVE+caste (meilleur beam ailleurs), le port
        caste en place (miss residuel). SUR : le port ne fire QUE si beam-origine >= 2, ce qui implique
        que le generateur NC natif etait NON-VIDE (global max >= 2) -> le natif caste AUSSI DarkTalon
        (jamais un cast d'ability parasite ; au pire une tuile/position residuelle differente)."""
    ABILITY_ID = int(ActiveAbilityType.DarkTalonStrike)  # 1092
    MIN_UTILITY = 2.0     # IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.cctor = Fix64(2) -> aime ssi beam >= 2 ennemis alignes
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None or ctx.origin is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # tuiles d'aim eligibles DEPUIS L'ORIGINE (fromHere, kind=tile) = GetEligibleTargetsSelectable.
        aims: list[tuple] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "tile" and t.get("tile"):
                        aims.append((t["tile"]["col"], t["tile"]["row"]))
        if not aims:
            return []
        enemy_set = {ep for ep in (ctx.epos or []) if ep and ep[0] is not None}
        best_aim, best_c = None, None
        for T in aims:                            # keep-first au tie (ordre GetEligibleTargets)
            c = _beam_count(ctx.origin, T, enemy_set)
            if best_c is None or c > best_c:      # strict > : 1re tuile du max gagne
                best_aim, best_c = T, c
        if best_aim is None or best_c < self.MIN_UTILITY:
            return []
        tile_id = (ctx.tile_id_by_pos or {}).get(best_aim)
        if tile_id is None:
            return []                             # pas d'entity-tuile -> ne peut pas emettre la cible
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] DarkTalonStrike aim={best_aim} beam={best_c} "
                  f"tileId={tile_id}", file=sys.stderr)
        # cast EN PLACE (origine porte l'aim max ; sweep origine-first keep-first).
        return [{"target": tile_id, "ability": self.ABILITY_ID, "to": None, "pred": float(best_c)}]
