"""EarlyWarningOverridePlaybook — summon overwatch self-cast NonComparable (utilite POSITIONNELLE :
+50 par ennemi hors de sa portee - 10 x distance ; cible = SOI, position = argmax)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _unit_cfg, _sweep_origin_first


def _enemy_max_range(visual_id) -> int:
    """Portee d'attaque MAX d'une unite (gameconfig `weapons` : `Range` present -> ranged, absent ->
    melee=1). Mirror APPROCHE d'`IsTileInRangeOfAnyAbility` (slot 0xc4 = tuiles attaquables depuis la
    tuile COURANTE de l'ennemi) : la vraie methode enumere les ranges d'ABILITY + LoS ; on approxime par
    la portee d'ARME max (sans LoS ni mouvement). >=1 toujours."""
    ws = _unit_cfg(visual_id).get("weapons") or []
    rs = [int(w["Range"]) if "Range" in w else 1 for w in ws]
    return max(rs) if rs else 1


class EarlyWarningOverridePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable` (id 0x435=1077, Loki/tauCrisis).
    Summon SELF-CAST : `IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour` fait apparaitre un drone
    (EarlyWarningOverride_SpawnSummonUtility) + pose `EarlyWarningOverride_ReactivateOverwatchEffect`. La
    cible de DECISION = le CASTER lui-meme (spawn/effet centre sur soi ; VALIDE LIVE : abilityTargets =
    unit 77 SEUL). L'utilite est POSITIONNELLE (choisit une tuile qui menace des ennemis en restant hors
    de leur portee) -> le natif BOUGE avant de caster.

    Structure native (mirror EvaluateNonComparable) : Bucket ctor 2-arg, min = Fix64(1) (IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.cctor
    pose `**(DAT_1832106c0+0xb8)=Fix64(1)` -> MIN_UTILITY=1). Par position P balayee, enumere
    `GetEligibleTargetsSelectable(MainTile=P)` (= SOI) ; pour la cible eligible :
      GATE : nearest = slot0x49 `GetNearestEnemy(self)` ; si `dist(nearest, self) < 9` (slot0x6b, dist des
             tuiles COURANTES = position-INDEPENDANT) -> evalue, sinon skip (pas d'action).
      UTIL(P) = 0 ; POUR CHAQUE unite vivante ennemie E (slot0x89 `GetAllAliveUnits` + filtre `IsEnemy`) :
        d = dist(P, E)                                            (slot0x6c = hexdist, CONFIRME LIVE)
        si CASTER (tuile COURANTE=origine) PAS adjacent a E :
            si NON `IsTileInRangeOfAnyAbility(P, E)` (slot0xc5)   -> util += 50   (P hors de portee de E)
        sinon (caster deja adjacent a E) :
            si `threshold(E) < d`  (threshold = slot0xb3(E).Nullable ?? 1)  -> util += 50   [branche B]
        util -= d * 10
      GenerateAction(P, SOI, Fix64(util)) + Bucket.AddAction (argmax STRICT `>`, keep-first au tie).

    LA PRIMITIVE D'ADJACENCE, LUE (#433-r4-r2). Le test « caster adjacent a E » est, VERBATIM :

        casterTile = EntityExtensions.GetMainTile(caster, state)        # tuile REELLE, pas P
        otherTiles = EntityExtensions.GetTiles(otherUnit, state)
        adj        = TileExtensions.IsAdjacentTo(casterTile, otherTiles)

    -- la surcharge `(tile, otherTiles)` d'`IdunBattle.Entities.TileExtensions$$IsAdjacentTo`, qui
    est un `exists` sur la liste dont chaque paire passe par
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` (surcharge SCALAIRE) :
    `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent.IsNeighbour(t1, t2))`. Ce N'EST donc PAS
    `TileQuery$$IterateAdjacentTiles`, et surtout ce n'est pas une distance hex nue : la PORTE
    D'ELEVATION en fait partie. Foyer mirror = `battle_query.are_entities_adjacent`.

    Le terme d'identite (`t1 == t2`) y est INATTEIGNABLE (tuile du caster vs tuiles d'un ennemi
    VIVANT distinct) ; c'est la porte d'elevation qui mord, et elle bascule le consommateur d'une
    BRANCHE A L'AUTRE -- ce qui n'est PAS monotone cote natif : passer de B a A rend l'utilite plus
    petite quand `range(E) >= 2` (A exige `d > range` la ou B se contente de `d > 1`), et plus
    GRANDE quand E porte un `threshold` slot0xb3 superieur a 1 face a un E de melee. Le port ne
    modelise que `threshold = 1` (defaut `Nullable ?? 1`), donc de SON cote la bascule est
    restrictive ; le bras permissif reste NATIF-seul tant que slot0xb3 n'est pas identifie.

    RESIDU herite (#419-r1-tr10-r2) : le natif compare la tuile principale du caster aux tuiles
    de l'EMPREINTE COMPLETE de l'ennemi (`GetTiles`) ; le port collapse l'ennemi sur sa tuile
    principale. Ecart sur les seules unites MULTI-TUILES, non traite ici.

    RECONCILIATION LIVE (ncEvaluate, seed 54321 s9 u77 tauCrisis, board MC1_67) : util(P) colle AU BIT
    a `200 - 10*Sum(dist(P,E))` sur les 4 ennemis vivants team-1 {(3,2),(2,3),(3,3),(2,4)} = 50*4 - 10*Sd
    (les 4 ennemis d=3..8 tous HORS de leur portee 1-2 -> +50 chacun = +200 constant). 12/12 positions
    exactes (origine (6,8)=-80=200-280 ; (3,7)=(4,6)=(5,6)=40=200-160 ; (6,5)=30=200-170). Le natif MOVE
    ->(3,7) = argmax (1re du tie 40 en ordre movable) puis caste 1077 sur soi. Le moteur ratait car 1077
    absent du registre -> emettait un MOVE PUR (par chance deja (3,7) via move-scoring). En NC, l'action
    porte la position (3,7) ET l'ability -> les DEUX dimensions HIT.

    - cible = SOI (ctx.uid) ; unique cible eligible (self-cast). VALIDE LIVE.
    - position = argmax util (sweep ORIGINE-FIRST keep-first : l'origine gagne le tie, un move ne gagne
      que sur util STRICTEMENT superieure -- ordre confirme par les castes en place Grapnel/DarkTalon).
    - MIN_UTILITY=1 (cctor) : positions a util < 1 rejetees ; l'ability ne fire QUE si un P atteint >= 1.
    - GATE nearest-enemy-within-9 (slot0x49=GetNearestEnemy) : modele par `min_E dist(origine,E) < 9`.
    - IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.ctor = `NonComparablePlaybook(0x435)` -> 1er arg=ability_id ; PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).

    FLAGS VALIDATEUR (approximations non exercees a s9) :
      * `IsTileInRangeOfAnyAbility` (slot0xc4) approxime par `dist(P,E) <= portee_arme_max(E)` : la vraie
        methode enumere les ranges d'ABILITY + LoS + `GetFeetCount>1 -> toujours in-range`. A s9 les 4
        ennemis sont melee/courte-portee et loin (d>=3) -> cover=false partout, l'approx est EXACTE.
        Un ennemi RANGED longue-portee ou GROS (multi-feet) pres du caster n'est PAS fidele.
      * BRANCHE B (caster adjacent a un ennemi a l'origine) : threshold=slot0xb2 NON identifie ->
        defaut Nullable??1 (`+50 si d>1`). NON exercee a s9 (tauCrisis loin des ennemis)."""
    ABILITY_ID = int(ActiveAbilityType.EarlyWarningOverride)  # 1077
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.cctor = Fix64(1) -> admission Bucket util>=1
    PRIORITY = 0
    _COVER_BONUS = 50.0   # Fix64.FromInt(0x32) IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable : +50 par ennemi non-couvert / hors-portee
    _DIST_PENALTY = 10.0  # Fix64.FromInt(iVar7*10) IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable : -10 x distance par ennemi
    _NEAREST_GATE = 9     # slot0x6b(nearest,self) < 9 (gate GetNearestEnemy IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        # cible eligible = SOI (self-cast). Genere ssi SOI est eligible a cette ability.
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        self_eligible = False
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") == ctx.uid:
                        self_eligible = True
        if not self_eligible:
            return []
        # ennemis vivants (slot0x88 GetAllAliveUnits + IsEnemy) : {pos, range}.
        enemies = [(e.get("pos"), _enemy_max_range(e.get("visualId"))) for e in (ctx.enemies or [])]
        enemies = [((p["col"], p["row"]), rg) for (p, rg) in enemies
                   if p and p.get("col") is not None]
        if not enemies:
            return []
        # GATE : nearest enemy within 9 de l'ORIGINE (slot0x49=GetNearestEnemy, position-independant).
        origin = ctx.origin
        if origin is not None:
            nearest = min(hexgeo.distance(origin, ep) for (ep, _) in enemies)
            if nearest >= self._NEAREST_GATE:
                return []
        # ennemis adjacents a l'ORIGINE (caster tuile courante) -> branche B ; sinon branche A.
        # `TileExtensions$$IsAdjacentTo(GetMainTile(caster), GetTiles(E))` -> foyer mirror
        # `are_entities_adjacent` (= `MovementUtil$$AreTilesAdjacent` : identite + porte
        # d'elevation `|dElev| < 2`). Une distance hex nue ratait la porte (#433-r4-r2).
        adj_origin = set()
        if origin is not None:
            for (ep, _) in enemies:
                if bq.are_entities_adjacent(origin, ep, ctx.elev_by_pos):
                    adj_origin.add(ep)
        best_p, best_u = None, None
        for P in _sweep_origin_first(ctx):        # ORIGINE-FIRST + keep-first (strict >)
            u = 0.0
            for (ep, rg) in enemies:
                d = hexgeo.distance(P, ep)
                if ep not in adj_origin:            # branche A : +50 si P hors de portee de E
                    if d > rg:
                        u += self._COVER_BONUS
                else:                               # branche B : +50 si d > threshold (defaut 1)
                    if d > 1:
                        u += self._COVER_BONUS
                u -= self._DIST_PENALTY * d
            if u < self.MIN_UTILITY:
                continue                            # admission Bucket util>=1
            if best_u is None or u > best_u:        # strict > : 1re position du max gagne (keep-first)
                best_p, best_u = P, u
        if best_p is None:
            return []
        to = None if best_p == origin else best_p
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] EarlyWarningOverride pos={best_p} util={best_u} "
                  f"tgt=self(to={to})", file=sys.stderr)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID, "to": to, "pred": best_u}]
