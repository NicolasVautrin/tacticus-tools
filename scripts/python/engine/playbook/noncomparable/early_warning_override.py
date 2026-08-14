"""EarlyWarningOverridePlaybook — summon overwatch self-cast NonComparable (utilite POSITIONNELLE :
+50 par ennemi hors de sa portee - 10 x distance ; cible = SOI, position = argmax)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.ai import context as aictx   # forme B (#485-r1-r1) : foyer du tri-etat du canal OCCUPANT
from engine.services import ability_caster_gates as acg
from engine.services import ability_range as ar
from engine.services import battle_query as bqs

from ._base import (NCContext, NonComparablePlaybook, _sweep_origin_first,
                    is_turn_of_unit_by_pos, occupant_team_by_pos)


def _ranged_weapon_threshold(visual_id) -> int:
    """`threshold(E)` de la BRANCHE B, mirror 1:1 du fragment natif d'
    `IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable` :

        w   = <IBattleQuery slot 0xb3>(otherUnit)          // BattleQuery$$FindRangedWeapon(unit)
        n   = (w != null) ? *(Nullable<int>*)(w + 0x24) : default(Nullable<int>)
        thr = n.HasValue ? n.GetValueOrDefault() : 1        // le `?? 1` du natif, LU
        if (thr < d) util += 50

    Le foyer de la 1re ligne est `engine.services.battle_query.find_ranged_weapon` (deja porte, 1:1 :
    filtre `!WeaponProfile.get_IsMelee` puis `SelectMaxRangeWeapon`). Ce module ne le REECRIT pas --
    c'etait precisement la faute de `_enemy_max_range` (residu `#433-r4-r2-r2`), un fork de foyer qui
    figeait le seuil a `1`.

    Deux consequences LUES qui ne se devinent pas, et que le fork ratait toutes les deux :
      * `get_IsMelee` = `!Range.HasValue || Range.Value < 2` -> une arme de portee **1 est MELEE** et
        n'entre donc PAS dans le set de `FindRangedWeapon` ;
      * `w == null` (aucune arme a distance) -> `Nullable` par defaut -> `HasValue` faux -> **1**.

    MESURE (`probe_433_r4_r2_adjacency_foyer.py --step partition`, ennemi PLAT `tauMarksman`, dont le
    kit porte une arme `Range=3` et une arme de melee sans `Range`) : le bonus natif vaut `0` jusqu'a
    `d = 3` et `50` a `d = 4`, c'est-a-dire `d > 3` = sa portee -- et non `d > 1`."""
    w = bqs.find_ranged_weapon(visual_id)
    r = (w or {}).get("Range")
    return int(r) if r is not None else 1


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

    LE CONTENU DES DEUX BRANCHES (#433-r4-r2-r1 et -r2, FERMES ENSEMBLE). Les fermer separement
    aurait produit un port DEGENERE : `threshold` (branche B) et l'ancienne approximation de la
    branche A (`portee d'arme max`) sont NUMERIQUEMENT egales sur toute unite a une seule arme a
    distance -- le partage A/B aurait cesse d'etre observable dans le port. Ils interrogent
    desormais DEUX fonctions natives distinctes, dont les valeurs DIFFERENT :

      * **branche A** -- `IsTileInRangeOfAnyAbility` (slot 0xc5), foyer
        `engine.services.ability_range.is_tile_in_range_of_any_ability`. Le slot `0xe` du service
        `attack` a `BattleQuery+0x20` est LU : c'est
        `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit,
        {GetMainTile(unit)}, includeNormalAttack: true)`. **AUCUN mouvement** n'y entre (l'ensemble
        de positions est le SINGLETON de la tuile courante) -- la fiche heritee de `#433-r4-r2` §7
        annoncait « MOUVEMENT et LoS compris », ce que la lecture du slot REFUTE. Ce qui porte a
        `d = 5` sur `tauMarksman` (arme de portee 3) est son ability `SeekerMissileFrequencyLock`,
        dont le `TargetingRange` est `RANGE_FROM_CONFIG` et le `constants.range` vaut 5.
        MESURE (`probe_433_r4_r2_r1_ability_range.py --step seam`, sweep de 40 positions,
        `d = 2..10`) : le natif rend « en portee » EXACTEMENT jusqu'a `d <= 5`, sans exception.
      * **branche B** -- `threshold(E) = FindRangedWeapon(E).Range ?? 1` (slot 0xb3), foyer
        `engine.services.battle_query.find_ranged_weapon` (deja porte 1:1). MESURE : ennemi PLAT
        `tauMarksman`, bonus natif `0` a `d <= 3` et `50` a `d = 4` -- `d > 3`, sa portee d'ARME.

    Sur ce meme `tauMarksman` les deux branches valent donc 5 et 3 : elles sont SEPAREES.

    RESIDUS de la branche A, NOMMES et mesures (cf. `docs/rl/case-433-r4-r2-r1-r2-portees.md`) :
      * le court-circuit `GetFeetCount(unit) > 1 -> true` n'est pas atteignable cote DECISION (aucun
        canal ne publie le compte de pieds) -> le port passe `feet_count = 1` ;
      * `UseWholeBoard` et `CustomRange(GetRange)` rendent la portee non derivable -> l'ability ne
        verse RIEN (borne INFERIEURE), ce que la mesure `astraDreir` (`LeadingTheCharge`,
        whole-board) confirme : le natif rend « hors portee » des `d >= 2` ;
      * la ZONE est modelisee par un DISQUE de rayon `max(portees)` : ni LoS ni forme. Les TROIS
        gates CASTER en amont (`AActiveAbility$$CanStillBeUsed` slot 0x14,
        `AActiveAbility$$IsDisabled` slot 0x13, `AttackQuery$$GetInvalidCasterReason`) sont
        MODELISES depuis `#433-r4-r2-r1-r1-c` : `enemies_of` passe l'etat d'abilities de chaque
        ennemi, donc une ability en cooldown / desarmee ne verse plus sa portee. MESURE
        (`darkaTerminator`, arme de MELEE + `PlasmaCannon` de zone 3) : le natif rend « en portee »
        jusqu'a `d = 3` quand l'ability est prete et `d <= 1` tant que son `initialCooldownTurns`
        brule -- le port rendait 3 dans les DEUX cas."""
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
        """`GetAllAliveUnits(null)` filtre `IsEnemy` -> `[(tuile, visualId, threshold, etat, na)]`.

        Les termes par ENNEMI sont pre-calcules ici parce qu'ils sont tous position-INDEPENDANTS
        (ils ne lisent que le kit de l'ennemi, son etat d'abilities et sa tuile COURANTE), la ou
        `utility_at` est evalue par POSITION du caster :
          * `visualId` -> substrat de la branche A (`is_tile_in_range_of_any_ability`, qui derive
            l'union des portees du kit -- cache par `visual_id` cote `services.ability_range`) ;
          * `threshold` -> branche B (`FindRangedWeapon(E).Range ?? 1`) ;
          * `etat` / `na` -> les TROIS gates CASTER de `AttackQuery$$GetAllTilesInAbilityRange`
            (#433-r4-r2-r1-r1-c), lus sur la ligne `decisionView` de l'ennemi
            (`abilities[].usable/disabled/cooldown/ammoCost/hasAmmo`). Le canal n'est peuple que
            si l'appelant a demande `allAbilities: true` ; sinon les tables sont vides et seul
            `IsDisabled` (derivable du kit) peut mordre -- borne SUPERIEURE, statu quo."""
        out = []
        for e in (ctx.enemies or []):
            p, vid = e.get("pos"), e.get("visualId")
            if not p or p.get("col") is None:
                continue
            out.append(((p["col"], p["row"]), vid, _ranged_weapon_threshold(vid),
                        acg.ability_state_map(e), acg.normal_attack_id(e)))
        return out

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
        return {e[0] for e in enemies
                if bq.are_entities_adjacent(ctx.origin, e[0], ctx.elev_by_pos, bq.neigh_map(ctx))}

    def utility_at(self, P: tuple, enemies: list, adj_origin: set, elev_by_pos=None,
                   is_wall_by_pos=None, team_by_pos=None, walkable_by_pos=None,
                   is_in_fog_by_pos=None, is_turn_by_pos=None, occupant_by_pos=None) -> float:
        """UTIL(P) du corps natif, ennemi par ennemi (mirror de la boucle `GetAllAliveUnits`).

        Extrait de `generate_candidates` pour etre CONFRONTABLE POSITION PAR POSITION a l'oracle
        `ncEvaluate` (qui invoque `Evaluate(unit, UnitPosition, tiles)` une fois par tuile et rend
        l'utilite du Bucket) -- comparer les seuls argmax laisserait passer un desaccord compense.

        Les deux branches interrogent desormais DEUX fonctions natives DISTINCTES -- c'est ce qui
        rend leur partage observable dans le port (cf. l'avertissement de `#433-r4-r2-r2`) :
        `IsTileInRangeOfAnyAbility` lit l'union des portees du KIT (attaque normale + abilities),
        `FindRangedWeapon` la seule portee de l'arme A DISTANCE. Sur `tauMarksman` (arme 3, ability
        `SeekerMissileFrequencyLock` de portee 5) elles valent respectivement 5 et 3."""
        u = 0.0
        for (ep, vid, thr, st, na) in enemies:
            d = hexgeo.distance(P, ep)
            if ep not in adj_origin:            # branche A : +50 si P hors de la zone d'ability de E
                # `caster_team` = l'equipe de E LUI-MEME, lue sur SA propre tuile : le natif
                # compare `GetCurrentPlayer(caster)` a l'occupant de la tuile-cible, donc la
                # meme carte sert aux deux bouts (#433-r4-r2-r1-r2-r2).
                if not ar.is_tile_in_range_of_any_ability(ep, P, vid, elev_by_pos=elev_by_pos,
                                                          ability_state=st, normal_attack_id=na,
                                                          is_wall_by_pos=is_wall_by_pos,
                                                          caster_team=(team_by_pos or {}).get(ep),
                                                          team_by_pos=team_by_pos,
                                                          walkable_by_pos=walkable_by_pos,
                                                          is_in_fog_by_pos=is_in_fog_by_pos,
                                                          # `IsTurnOfUnit(E)` -- PREFIXE de
                                                          # `CasterHasNotMoved`, lu sur E (le
                                                          # « caster » de CETTE question), jamais
                                                          # sur le porteur d'EarlyWarningOverride
                                                          # (#447-r1-r1-r3).
                                                          is_turn_of_unit=(is_turn_by_pos or {}).get(ep),
                                                          # #433-r4-r2-r1-r1-a-r1 : les sept gates
                                                          # `GATE_VALID_ON_EMPTY_TILE` retirent la
                                                          # tuile OCCUPEE. `None` = canal non
                                                          # mesure -> aucun retrait (statu quo).
                                                          occupant_by_pos=occupant_by_pos):
                    u += self._COVER_BONUS
            else:                               # branche B : +50 si `threshold(E) < d`
                if thr < d:
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
            nearest = min(hexgeo.distance(origin, e[0]) for e in enemies)
            if nearest >= self._NEAREST_GATE:
                return []
        # ennemis adjacents a l'ORIGINE (caster tuile courante) -> branche B ; sinon branche A.
        adj_origin = self.adjacent_at_origin(ctx, enemies)
        team_by_pos = occupant_team_by_pos(ctx)   # gardes « ami » de la ligne de vue (#-r1-r2-r2)
        is_turn_by_pos = is_turn_of_unit_by_pos(ctx)   # PREFIXE de `CasterHasNotMoved` (#447-r1-r1-r3)
        # #433-r4-r2-r1-r1-a-r1 -- l'OCCUPANT par tuile, substrat des sept gates
        # `GATE_VALID_ON_EMPTY_TILE`. Le tri-etat est DERIVE, jamais un `bool()` sur la table : une
        # table vide alors que des unites sont positionnees est un capteur MUET, pas un plateau
        # libre (vice #943-r8 -- un transport mort qui passe pour une mesure honnete).
        _occ = getattr(ctx, "occupant_by_pos", None) or {}
        occupant_by_pos = _occ if aictx.occupant_channel_is_measured(_occ, ctx.units) else None
        best_p, best_u = None, None
        for P in _sweep_origin_first(ctx):        # ORIGINE-FIRST + keep-first (strict >)
            u = self.utility_at(P, enemies, adj_origin, ctx.elev_by_pos,
                                getattr(ctx, "is_wall_by_pos", None), team_by_pos,
                                getattr(ctx, "walkable_by_pos", None),
                                getattr(ctx, "is_in_fog_by_pos", None), is_turn_by_pos,
                                occupant_by_pos)
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
