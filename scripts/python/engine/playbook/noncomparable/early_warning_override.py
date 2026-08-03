"""EarlyWarningOverridePlaybook — summon overwatch self-cast NonComparable (utilite POSITIONNELLE :
+50 par ennemi hors de sa portee - 10 x distance ; cible = SOI, position = argmax)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _unit_cfg, _sweep_origin_first


def _enemy_max_range(visual_id) -> int:
    """Portee d'attaque MAX d'une unite (gameconfig `weapons` : `Range` present -> ranged, absent ->
    melee=1). Mirror APPROCHE d'`IsTileInRangeOfAnyAbility` (slot 0xc5) : la vraie methode
    court-circuite a VRAI sur un caster multi-tuiles puis interroge le slot 0xe du service a
    `BattleQuery+0x20` avec `{GetMainTile(unit)}`, donc MOUVEMENT et LoS compris. On approxime par la
    portee d'ARME max (ni mouvement, ni LoS, ni nombre de pieds). >=1 toujours.
    Residu `#433-r4-r2-r1` -- mesure de l'ecart dans `docs/rl/case-433-r4-r2-consommateurs-hors-foyer.md` §7."""
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

    Structure native (mirror EvaluateNonComparable) : Bucket construit par le ctor a DEUX arguments,
    donc SANS `min` -- le `Fix64(1)` que pose IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.cctor a `<statics>+0xb8` n'est lu par AUCUN
    des deux arguments (cf. `MIN_UTILITY` plus bas, residu `#433-r4-r2-r3`). Par position P balayee, enumere
    `GetEligibleTargetsSelectable(MainTile=P)` (= SOI) ; pour la cible eligible :
      GATE : nearest = slot0x4a `GetNearestEnemy(self)` ; si `dist(nearest, self) < 9` (slot0x6c, dist des
             tuiles COURANTES = position-INDEPENDANT) -> evalue, sinon skip (pas d'action).
      UTIL(P) = 0 ; POUR CHAQUE unite vivante ennemie E (slot0x89 `GetAllAliveUnits` + filtre `IsEnemy`) :
        d = dist(P, E)                                            (slot0x6c = hexdist, CONFIRME LIVE)
        si CASTER (tuile COURANTE=origine) PAS adjacent a E :
            si NON `IsTileInRangeOfAnyAbility(P, E)` (slot0xc5)   -> util += 50   (P hors de portee de E)
        sinon (caster deja adjacent a E) :
            si `threshold(E) < d`  (threshold = slot0xb3(E).Nullable ?? 1)  -> util += 50   [branche B]
        util -= d * 10
      GenerateAction(P, SOI, Fix64(util)) + Bucket.AddAction (argmax STRICT `>`, keep-first au tie).

    Les six slots d'interface cites ci-dessus sont RE-DERIVES AU RUNTIME par
    `probe_433_r4_r2_adjacency_foyer.py --step slots` (qui delegue a `probe_27_4g_battlequery_slots`)
    -- ils ont bouge d'un cran depuis `gqfc5mff6c`, donc les recopier d'une fiche est un faux ami.

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
    VIVANT distinct) ; c'est la porte d'elevation qui mord, et elle BASCULE le consommateur d'une
    BRANCHE A L'AUTRE. MESURE LIVE (`--step partition`, `MC1_67`) : meme caster, MEME tuile, meme
    sweep, seule la tuile de l'ennemi change d'un voisin PLAT a un voisin a `|dElev| = 2` -- le
    bonus natif a `d = 4` passe de `50` (branche B) a `0` (branche A). C'est le natif compare a
    LUI-MEME : la porte gouverne bien le partage.

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
      ⚠ CONTESTE, residu `#433-r4-r2-r3` : le Bucket de CE playbook est construit par le ctor a DEUX
      arguments -- donc SANS `min` -- la ou `MasterOfTheTutelariesPlaybook`, lui, LIT le statique
      `+0xb8` et le passe au ctor a quatre arguments. Et `ncEvaluate` rend bien un `best` a utilite
      NEGATIVE a chaque position du sweep (mesure `--step couple`). Le statique existe dans les deux
      cctors ; reste a etablir qui le lit ici (un `get_MinUtility` consomme par le generateur ?).
    - GATE nearest-enemy-within-9 (slot0x4a=GetNearestEnemy) : modele par `min_E dist(origine,E) < 9`.
      `min` est EXACT : la priorite melee de `GetNearestEnemy` ne peut departager que des ennemis
      ADJACENTS, donc a distance 1 -- deja le minimum (`AreEntitiesAdjacent` implique
      `GetDistance <= 1`, et 0 est impossible entre deux unites vivantes distinctes).
    - IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.ctor = `NonComparablePlaybook(0x435)` -> 1er arg=ability_id ; PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170).

    FLAGS VALIDATEUR -- le CONTENU des deux branches reste approxime (leur PARTAGE, lui, est porte) :
      * **branche A**, residu `#433-r4-r2-r1`. `IsTileInRangeOfAnyAbility` (slot0xc5) est approxime
        par `dist(P,E) <= portee_arme_max(E)`. Le natif, lu :
        `if (GetFeetCount(unit) > 1) return true ; return slot0xe(<this+0x20>, unit,
        OrderedSet{GetMainTile(unit)}, true).Contains(tile)` -- donc MOUVEMENT et LoS compris.
        MESURE LIVE (`--step partition`, `tauMarksman`, arme de portee 3) : le natif rend « en
        portee » jusqu'a `d = 5` inclus, et il EXCLUT une tuile a `d = 5` que ses voisines de meme
        distance incluent (LoS/elevation). L'approximation est donc fausse des `d > portee`, dans
        les DEUX sens. Elle reste exacte tant que `d <= portee`.
      * **branche B**, residu `#433-r4-r2-r2`. Le `threshold` est IDENTIFIE : slot0xb3 =
        `IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon`, dont le champ `Nullable<int>` a
        `+0x24` est la PORTEE de l'arme a distance (`?? 1` = melee). Le port fixe encore `1`.
        MESURE LIVE : ennemi PLAT `tauMarksman`, bonus natif `0` a `d <= 3` et `50` a `d = 4` --
        c'est-a-dire `d > 3`, sa portee, et non `d > 1`.
        ⚠ Consequence a garder en tete : une fois ce residu ferme, `threshold` vaudra la portee de
        l'arme a distance, soit la MEME valeur que `portee_arme_max` pour toute unite a une seule
        arme a distance. Les deux branches du PORT deviendront alors identiques, et le partage A/B
        ne sera plus observable dans le port tant que `#433-r4-r2-r1` n'est pas ferme lui aussi."""
    ABILITY_ID = int(ActiveAbilityType.EarlyWarningOverride)  # 1077
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$.cctor = Fix64(1) -> admission Bucket util>=1
    #                       CONTESTE, residu `#433-r4-r2-r3` : le Bucket de CE playbook est construit
    #                       par le ctor a DEUX arguments (donc SANS `min`), et `ncEvaluate` rend un
    #                       `best` a utilite NEGATIVE a chaque position. Non tranche, non touche.
    PRIORITY = 0
    _COVER_BONUS = 50.0   # Fix64.FromInt(0x32) IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable : +50 par ennemi non-couvert / hors-portee
    _DIST_PENALTY = 10.0  # Fix64.FromInt(iVar7*10) IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable : -10 x distance par ennemi
    _NEAREST_GATE = 9     # slot0x6c(nearest,self) < 9 (gate GetNearestEnemy IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable)

    def enemies_of(self, ctx: NCContext) -> list:
        """`GetAllAliveUnits(null)` filtre `IsEnemy` -> `[(tuile, portee d'arme max)]`."""
        out = [(e.get("pos"), _enemy_max_range(e.get("visualId"))) for e in (ctx.enemies or [])]
        return [((p["col"], p["row"]), rg) for (p, rg) in out
                if p and p.get("col") is not None]

    def adjacent_at_origin(self, ctx: NCContext, enemies: list) -> set:
        """Les ennemis que le natif declare adjacents a la TUILE REELLE du caster -> branche B.

        `adj = TileExtensions.IsAdjacentTo(GetMainTile(caster), GetTiles(otherUnit))`, evalue sur
        `caster` et NON sur la position balayee : le partage A/B est donc CONSTANT sur tout le
        sweep. Le predicat par paire est `MovementUtil$$AreTilesAdjacent` -> foyer mirror
        `battle_query.are_entities_adjacent` (identite + porte d'elevation `|dElev| < 2`).
        Canal d'elevation absent (`ctx.elev_by_pos` None/vide) -> le foyer se degrade en distance
        hex nue, exactement le comportement d'avant #433-r4-r2 (borne SUPERIEURE : on ne retire
        jamais une adjacence a l'aveugle)."""
        if ctx.origin is None:
            return set()
        return {ep for (ep, _) in enemies
                if bq.are_entities_adjacent(ctx.origin, ep, ctx.elev_by_pos)}

    def utility_at(self, P: tuple, enemies: list, adj_origin: set) -> float:
        """UTIL(P) du corps natif, ennemi par ennemi (mirror de la boucle `GetAllAliveUnits`).

        Extrait de `generate_candidates` pour etre CONFRONTABLE POSITION PAR POSITION a l'oracle
        `ncEvaluate` (qui invoque `Evaluate(unit, UnitPosition, tiles)` une fois par tuile et rend
        l'utilite du Bucket) -- comparer les seuls argmax laisserait passer un desaccord compense."""
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
        return u

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
        # ennemis vivants (slot0x89 GetAllAliveUnits + IsEnemy) : {pos, range}.
        enemies = self.enemies_of(ctx)
        if not enemies:
            return []
        # GATE : nearest enemy within 9 de l'ORIGINE (slot0x4a=GetNearestEnemy, position-independant).
        origin = ctx.origin
        if origin is not None:
            nearest = min(hexgeo.distance(origin, ep) for (ep, _) in enemies)
            if nearest >= self._NEAREST_GATE:
                return []
        # ennemis adjacents a l'ORIGINE (caster tuile courante) -> branche B ; sinon branche A.
        adj_origin = self.adjacent_at_origin(ctx, enemies)
        best_p, best_u = None, None
        for P in _sweep_origin_first(ctx):        # ORIGINE-FIRST + keep-first (strict >)
            u = self.utility_at(P, enemies, adj_origin)
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
