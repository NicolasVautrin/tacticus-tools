"""Playbooks NonComparable — une classe Python HOMONYME par playbook natif.

Remplace l'ancien switch `if kind in ("summon","adjacent_count","target_hp")` d'engine_decide
par un mecanisme generique (registre de classes + driver commun). Structure FIDELE au decompile
(confirme sur AberrantHypermorphPlaybook.EvaluateNonComparable @1811197d0) :

  - `ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` range chaque ability NonComparable par
    son playbook dans `dict[get_Priority]` ; `GetDefaultActiveAbilityActionGenerators @1810ed0c0`
    cree UN generator par tier [1000,100,0,-100,-1000] ; le tactic prend le PREMIER generator
    non-vide -> une NC qui passe son MIN_UTILITY prime sur toute Comparable, ET une NC de tier
    superieur prime sur une NC de tier inferieur PAR L'ORDRE (pas l'utilite). PRIORITY par classe
    (get_Priority, litteral compile-time slot0 interface) : les 4 attaques/buffs portees = 0 ;
    NovaBoost=1000, NovaShield=-1000 (exercent l'ordre inter-tier).
  - Le generator `ActiveAbilityActionGenerator.<GenerateActions>d__7.MoveNext @18119a3f0` BALAIE
    les positions candidates du caster (tuiles de move) et appelle par position
    `<Playbook>.EvaluateNonComparable(this, ctx, position)` : celui-ci cree un Bucket (MIN_UTILITY
    du cctor), enumere les cibles eligibles via `BasePlaybook.GetEligibleTargetsSelectable
    @18111f0d0`, score chacune (`<Playbook>.GetUtility`), et gate `Bucket.AddAction @1813fbcc0`
    (util >= min, remplacement STRICT `>`).
  - `Bucket.ChooseAction` = argmax STRICT (tie -> premier enumere).

Mapping : une CLASSE = un playbook natif ; `evaluate_non_comparable` = la methode homonyme
(formule EvaluateNonComparable INLINE, VA citee) ; `generate_candidates` = le balayage
generator+selector propre a l'ability (positions/cibles specifiques). Les requetes spatiales
(GetAdjacentEnemies/Friends) deleguent a `engine/battle_query.py` (primitive IBattleQuery).
Le driver generique `choose_action` (mirror ChooseAction) collecte les candidats de toutes les
abilities NC usable de l'unite et rend l'argmax -> remplace le switch. Utilite = heuristique BRUTE
(pas de terme Tile7 : CalculateActionUtility/Tile7 est un chemin Comparable-only).

cf. engine/battle_query.py (primitives), docs/rl/playbook/architecture.md §2.3 + playbooks.md.
Vit dans le namespace unifie `engine.playbook` (= `IdunBattle.AI.Playbook`), aux cotes de
`comparable.py`/`common.py` (les playbooks Comparable).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import hexgeo
import gameconfig as _gc
from engine import battle_query as bq
from engine.ai.utilities import get_movement_utility   # IdunBattle.AI.Utilities : GetMovementUtility
from engine.utilities.utility_type import UtilityType


_CFG_CACHE: dict = {}


def _unit_cfg(visual_id) -> dict:
    """Config gameconfig d'une unite par visualId (resolue + cachee ; `resolve_unit_id` d'abord, comme
    `_faction`). Le dict porte `traits` / `GrandAllianceId` / `kind`. Vide si introuvable."""
    if not visual_id:
        return {}
    c = _CFG_CACHE.get(visual_id)
    if c is None:
        try:
            uid = _gc.resolve_unit_id(visual_id)
            c = (_gc.unit(uid) if uid else _gc.unit(visual_id)) or {}
        except Exception:
            c = {}
        _CFG_CACHE[visual_id] = c
    return c


def _traits(visual_id) -> list:
    """Traits gameconfig (Hero/Mechanical). heal = Healable = non-Mecanique ; resurrect hero = Hero(16)."""
    return _unit_cfg(visual_id).get("traits") or []


def _sweep_origin_first(ctx: "NCContext") -> list:
    """Ordre de balayage des positions candidates pour un SELF-CAST (heal/repair/rites) : ORIGINE
    D'ABORD, puis les tuiles de move.

    Le generateur natif `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` evalue chaque
    position dans un Bucket ; `Bucket.AddAction @1813fbcc0` SEED le 1er ajoute puis ne remplace QUE si
    STRICTEMENT superieur (`System.TimeSpan.op_GreaterThan`) -> keep-first au tie. La `NullPosition`
    (cast EN PLACE) est TOUJOURS evaluee. CONFIRME LIVE (#76, deathRotbone RevitalizingMalignancy) :
    a utilite CONSTANTE (seul le caster blesse -> terme adjacents = 0) le natif RESTE EN PLACE (target
    = MainTile origine), il ne bouge QUE si une tuile de move AMELIORE STRICTEMENT la somme de soin.
    -> origine EN TETE du sweep + remplacement strict `>` = origine gagne le tie ; un move ne gagne
    que sur gain strict. (Le port balayait `reach_nc` = [moves..., origine] -> gardait la 1re tuile de
    move au tie -> divergence : bougeait pour rien.)"""
    if ctx.origin is None:
        return list(ctx.reach_nc)
    return [ctx.origin] + [t for t in ctx.reach_nc if t != ctx.origin]


@dataclass
class NCContext:
    """Etat live consomme par les generators de playbook (bundle du scope engine_decide)."""
    uid: int
    origin: tuple | None
    reach_nc: list                 # origine + tuiles de MOVE = positions candidates du caster
    epos: list                     # positions ennemies (GetAdjacentEnemies, slot 124/126)
    fpos: list                     # positions alliees, self exclu (GetAdjacentFriends, slot 128)
    plan: dict                     # plan natif (evals rankes) — abilities d'ATTAQUE
    hp_cur_by_id: dict             # PV courants par id cible (GetStat 5 = Health ; Vexilla)
    ability_targets: object = None # callable(uid, ability_id) -> dict RPC abilityTargets (summon)
    obs_units: list = field(default_factory=list)  # observeBattle.units (isDead/teamId/visualId/pos) :
    #                                SOURCE DES MORTS pour RitesOfRestoration (decisionView garde les
    #                                depouilles -> observeBattle.isDead, cf. project_decisionview_keeps_dead)
    elev_by_pos: dict = None       # {(col,row): elevation} (tileMeta) — porte d'adjacence |Δelev|<2
    wt: object = None              # Weights BC (NovaShield : terme Tile(7) = tile_utility)
    is_temporary_by_pos: dict = field(default_factory=dict)  # Tile(7) (feuille is_temporary)
    effects_by_pos: dict = field(default_factory=dict)       # Tile(7) (feuille TileEffects)
    tile_id_by_pos: dict = field(default_factory=dict)       # {(col,row): tileEntityId} (boardGraph) :
    #                            cible d'une self-cast AoE (heal) = MainTile-id du caster, PAS son unit-id
    active_levels: object = None   # callable() -> {unitId: activeAbilityLevel} (lazy combatSnapshot) :
    #                            niveau d'ability des allies pour InspiredToGreatness (util = level)
    units: list = field(default_factory=list)   # dv.units (par-unite abilities + usable/cooldown) :
    #                            etat cooldown des allies pour InspiredToGreatness (GetActive usable)
    cast_from_tiles: object = None   # callable(uid, target_id, ability_id) -> {currentValid, moveTiles} :
    #                            positionnement move-to-reach des NC ally-targeted (#81)
    debug: bool = False


class NonComparablePlaybook:
    """`NonComparablePlaybook<T>` — playbook à heuristique ENTIÈRE écrite dans la feuille (summons,
    buffs, retraite), par opposition à `ComparablePlaybook<T>` (attaques/soins = somme pondérée sur
    prédictions). Priorité Normal(0) pour tous les portés. Sous-classe = un playbook natif homonyme
    (selector + leaf `EvaluateNonComparable` + MIN_UTILITY du cctor)."""
    ABILITY_ID: int = -1
    MIN_UTILITY: float = 0.0       # cctor du playbook -> gate Bucket.AddAction (util >= min)
    PRIORITY: int = 0              # get_Priority (slot0) -> tier NonComparable (dict[prio], @1810ed540)
    #                                les 4 portés = 0 (confirmé live via abilityPreferences/get_Priority)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror <GenerateActions>d__7 pour CETTE ability : balaie positions/cibles (selector
        propre), score (evaluate_non_comparable), gate par MIN_UTILITY. Rend 0 ou 1 candidat
        {target, ability, to, pred} = le meilleur de l'ability (Bucket local deja argmax-e)."""
        raise NotImplementedError


class _PlanTargetPlaybook(NonComparablePlaybook):
    """Base des abilities d'ATTAQUE NonComparable (BloodyFury, VexillaMagnifica). Le generator
    natif enumere ici les couples (cible, tuile d'attaque) via le plan natif rank
    (`abilityTargets`/ranked du plan) au lieu d'un balayage de tuiles de move ; leaf par sous-classe.
    """
    def evaluate_non_comparable(self, tile: tuple, target, ctx: NCContext) -> float | None:
        raise NotImplementedError

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None  # (target, tile, util)
        for ev in (ctx.plan.get("evals") or []):
            if ev.get("abilityId") != self.ABILITY_ID or not ev.get("rankCount"):
                continue
            ranked = ev.get("ranked") or []
            if not ranked:
                continue
            tile = (ranked[0].get("col"), ranked[0].get("row"))
            tgt = ev.get("targetId")
            nu = self.evaluate_non_comparable(tile, tgt, ctx)
            if nu is None:
                continue
            if best is None or nu > best[2]:   # strict > : premier max garde
                best = (tgt, tile, nu)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]


class BloodyFuryPlaybook(_PlanTargetPlaybook):
    """BloodyFuryPlaybook.EvaluateNonComparable @181122be0 = 1 + (#ennemis adjacents a la tuile
    d'attaque) x ADJACENT_ENEMIES_UTILITY. cctor @181123340 : MIN_UTILITY=1, ADJACENT=10."""
    ABILITY_ID = 1129
    MIN_UTILITY = 1.0
    _ADJACENT_ENEMIES_UTILITY = 10   # cctor @181123340

    def evaluate_non_comparable(self, tile, target, ctx):
        if tile is None:
            return None
        adj = bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos)   # GetAdjacentEnemies @18105af60
        return 1.0 + adj * self._ADJACENT_ENEMIES_UTILITY


class VexillaMagnificaPlaybook(_PlanTargetPlaybook):
    """VexillaMagnificaPlaybook.EvaluateNonComparable @18117f6f0 = FromInt(GetStat(cible,5=Health))
    -> PV courants de la cible. cctor @18117fa30 : MIN_UTILITY=1. [filtre HasEffect 0x48a : TODO]."""
    ABILITY_ID = 1183
    MIN_UTILITY = 1.0

    def evaluate_non_comparable(self, tile, target, ctx):
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5=Health)
        return float(hp) if hp and hp > 0 else None


class FightingRetreatPlaybook(NonComparablePlaybook):
    """FightingRetreatPlaybook.EvaluateNonComparable @181131ff0 : u = |ennemis adj a la tuile| +
    (si >0) |allies adj a la tuile - self|, balaye sur les tuiles atteignables (origine EN TETE) ;
    cible = SELF. cctor @1811323b0 : MIN_UTILITY=2."""
    ABILITY_ID = 1081
    MIN_UTILITY = 2.0

    def evaluate_non_comparable(self, tile, ctx):
        # A = GetAdjacentEnemies(tile) [slot 124] ; B = GetAdjacentFriends(tile)-self [slot 128]
        # (self deja exclu de ctx.fpos ; le natif fait B.Remove(self)). u = |A| + (|A|>0 ? |B| : 0).
        a = bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos)
        if a == 0:
            return 0.0
        return float(a + bq.count_adjacent(tile, ctx.fpos, ctx.elev_by_pos))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best_t, best_u = None, None
        for T in ctx.reach_nc:
            u_ = self.evaluate_non_comparable(T, ctx)
            if best_u is None or u_ > best_u:   # strict > : premier max garde (ordre reach_nc)
                best_t, best_u = T, u_
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] FR aid={self.ABILITY_ID} reach={len(ctx.reach_nc)} "
                  f"best={best_t} u={best_u} min={self.MIN_UTILITY}", file=sys.stderr)
        if best_u is None or best_u < self.MIN_UTILITY:
            return []
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]


class AberrantHypermorphPlaybook(NonComparablePlaybook):
    """AberrantHypermorphPlaybook.EvaluateNonComparable @1811197d0 (action COMPOSEE move+summon).
    Le generator balaie les tuiles de MOVE du caster ; par tuile T, le selector
    `GetEligibleTargetsSelectable @18111f0d0` rend les tuiles de SPAWN eligibles (ring-1 libre,
    portee=1 — gameconfig 1166 « free adjacent hex ») ; utilite d'un spawn ST = #ennemis adjacents
    (`GetUtility @181119c10`, slot 126 GetAdjacentEnemies -> Fix64.FromInt). Le caster BOUGE vers la
    tuile T qui maximise ce count. cctor @181119cd0 : MIN_UTILITY=1.

    NB abilityTargets.targets = UNION des spawns sur TOUTES les tuiles de move
    (GetAllValidTargetsFromAllPossibleMovementTiles, dist 0-4 de l'origine) — le filtre
    distance(T,ST)==1 reconstitue le per-tuile."""
    ABILITY_ID = 1166
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        spawn_tiles = self._eligible_spawn_tiles(ctx)
        best_t, best_u = None, None
        for T in ctx.reach_nc:   # positions candidates du caster (origine + tuiles de move)
            # GetUtility @181119c10 (slot 126 GetAdjacentEnemies) = #ennemis adjacents au spawn ST.
            cnt = [float(bq.count_adjacent(ST, ctx.epos, ctx.elev_by_pos))
                   for ST in spawn_tiles if hexgeo.distance(T, ST) == 1]
            u_ = max(cnt) if cnt else 0.0
            if best_u is None or u_ > best_u:   # strict > : premier max garde (ordre reach_nc)
                best_t, best_u = T, u_
        if best_t is None or best_u < self.MIN_UTILITY:
            return []
        return [{"target": None, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]

    def _eligible_spawn_tiles(self, ctx: NCContext) -> list[tuple]:
        """Mirror BasePlaybook.GetEligibleTargetsSelectable @18111f0d0 : union des tuiles de spawn
        (kind="tile") via l'RPC abilityTargets."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tiles: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    tiles = [(t["tile"].get("col"), t["tile"].get("row"))
                             for t in (a.get("targets") or [])
                             if t.get("kind") == "tile" and t.get("tile")
                             and t["tile"].get("col") is not None]
        return tiles


class NovaBoostPlaybook(NonComparablePlaybook):
    """`NovaBoostPlaybook.EvaluateNonComparable @18114ee60` : util = `Fix64.FromInt(1)` CONSTANTE par
    cible éligible (self ; marque les hex adjacents au caster). cctor @18114f1e0 : MIN_UTILITY=1.
    ctor @18114f250 (id 0x4a8=1192). Tier get_Priority=**1000** (validateur : `@1807D66A0` = `mov eax,0x3E8`).

    STATUT : DECOMPILE-PROVEN, **ARENE-INAGREABLE** (Riptide non spawnable au rank 17 -> pas de test
    d'agreement live ; le mecanisme repose sur le decompile, tiers tranches a l'octet par le validateur).
    - R1 RESOLU (#80) : NovaBoost est un SELF-buff (cible = self, util=1 CONSTANTE) -> MEME CLASSE que les
      self-cast heals. Le generateur `<GenerateActions>d__7 @18119a3f0` GATE chaque tuile de move par
      `HasValidTargets(0x3f)(unit, movePos, ability)` puis `Bucket.AddAction` garde le 1er ajoute (NullPosition
      = cast EN PLACE, TOUJOURS evaluee). Pour un SELF-target la cible (self) est position-INDEPENDANTE -> le
      gate ne motive aucune tuile de move -> le natif CASTE EN PLACE. CONFIRME LIVE (self-cast heal #76 :
      deathRotbone self-heal RESTE EN PLACE a util constante). FIX = `_sweep_origin_first` (origine d'abord ->
      to=None), mirror du comportement heal confirme. [La fonction exacte de `HasValidTargets` est derriere un
      dispatch d'interface (@180028910 = trampoline), non lisible statiquement -> la base est la COHERENCE
      GENERATEUR + la classe self-target confirmee, PAS un agreement (arene-inagreable). Cf. NovaShield =
      classe TILE-target, comportement OPPOSE.]
    - N1 : gate `ShouldEvaluate @18114f160` = `if query.slot0x1a(unit,2) then base.ShouldEvaluate else 0`
      (précondition Nova, prob. charge, + base) NON modélisé -> on s'appuie sur le filtre driver
      `usable is False` (supposé encoder la précondition). L'eligible-empty (`GetEligibleTargetsSelectable`
      vide -> le natif n'émet rien) est modélisé ci-dessous."""
    ABILITY_ID = 1192
    MIN_UTILITY = 1.0
    PRIORITY = 1000

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._has_eligible_target(ctx):
            return []   # N1 : GetEligibleTargetsSelectable vide -> le natif n'émet rien
        # R1 RESOLU (#80) : SELF-target (util=1 CONSTANTE) = MEME CLASSE que les self-cast heals #76 -> le
        # generateur gate les tuiles de move (self-cible position-independante) -> keep-first sur NullPosition
        # => le natif RESTE EN PLACE. `_sweep_origin_first` (origine d'abord) -> to=None.
        to = next(iter(_sweep_origin_first(ctx)), None)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (to if to != ctx.origin else None), "pred": 1.0}]

    def _has_eligible_target(self, ctx: NCContext) -> bool:
        """`BasePlaybook.GetEligibleTargetsSelectable @18111f0d0` non-vide. Cible éligible d'un self-buff =
        self (via abilityTargets, qui inclut les cibles NON-attaque). PERMISSIF si la source d'éligibilité
        est indisponible (le driver filtre déjà `usable is False`)."""
        if ctx.ability_targets is None:
            return True
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID and (a.get("targets") or []):
                    return True
        return False


class NovaShieldPlaybook(NonComparablePlaybook):
    """`NovaShieldPlaybook.EvaluateNonComparable @18114f9d0` (tier get_Priority=**-1000**, id 0x4aa=1194).
    cctor @1811502c0 : MIN_UTILITY=1. Marque un hex CENTRE + son ring-1 (hors trench), dégât AoE différé.
    Par (casterPos ∈ reach, center ∈ cibles-éligibles) :
        marked(center) = {center} ∪ neighbors(center) \\ trench          # GetMarkedTiles @1811f83c0
        util = 100*CountEnemiesOnTiles(marked) + Count(marked)            # @1814aae40 (non-alliés) + get_Count
               + Tile(7)@casterPos + DislikeStartingTiles(27)@casterPos   # GetMovementUtility @1814ab490
    Les 2 termes mouvement dépendent de `casterPos` SEUL (constants sur la boucle center). `ChooseAction`
    = argmax STRICT `>`, gate util >= 1. Cible native = le CENTRE marqué (kind=tile).
    HYPOTHÈSE(trench) : flag isTrench non capturé -> ring géométrique complet (biais <=6 sur Count,
    écrasé par 100*enemies).
    STATUT : DECOMPILE-PROVEN, ARENE-INAGREABLE (Riptide non spawnable). R1 (#80) : NovaShield est
    TILE-target (marque un CENTRE hex, cible kind=tile) -> classe DIFFERENTE des self-cast heals/NovaBoost.
    Le generateur `<GenerateActions>d__7 @18119a3f0` gate les tuiles de move par `HasValidTargets(0x3f)` :
    pour une TILE-target les hex a marquer existent depuis la plupart des positions -> les tuiles de move NE
    sont PAS gatees comme un self-cast -> au tie keep-first la 1re tuile de move gagne (le natif BOUGE). De
    plus l'utilite DEPEND de la position (100*ennemis marques) -> argmax non-trivial, le tie-break n'est que
    secondaire. => on GARDE le sweep origine-LAST (`ctx.reach_nc`). [UNVERIFIED : arene-inagreable +
    `HasValidTargets` derriere dispatch d'interface ; la classe TILE-target n'a PAS de confirmation live comme
    la classe self-target #76 -> ne PAS asserter fermement.] R2 : `DislikeStartingTilesUtility` no-op (poids
    BC non confirmé, arene-inagreable)."""
    ABILITY_ID = 1194
    MIN_UTILITY = 1.0
    PRIORITY = -1000

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        centers = self._eligible_mark_centers(ctx)
        if not centers:
            return []
        epos = set(ctx.epos or [])
        board = ctx.elev_by_pos or {}
        best = None  # (caster_pos, util)
        for caster_pos in ctx.reach_nc:
            # GetMovementUtility(Tile) + GetMovementUtility(DislikeStartingTiles) @1814ab490 (2 appels natifs).
            move_term = (get_movement_utility(ctx, caster_pos, UtilityType.Tile)
                         + get_movement_utility(ctx, caster_pos, UtilityType.DislikeStartingTilesUtility))
            for center in centers:
                marked = [center] + [n for n in hexgeo.neighbors(*center)
                                     if (not board) or (n in board)]        # GetMarkedTiles \ trench
                n_enemy = sum(1 for t in marked if t in epos)               # CountEnemiesOnTiles @1814aae40
                u = 100.0 * n_enemy + len(marked) + move_term              # 100*enemies + get_Count(marked)
                if best is None or u > best[1]:   # strict > : 1er max garde
                    best = (caster_pos, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        caster_pos, u = best
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] NovaShield centers={len(centers)} best_to={caster_pos} "
                  f"u={u} min={self.MIN_UTILITY}", file=sys.stderr)
        return [{"target": None, "ability": self.ABILITY_ID,
                 "to": (caster_pos if caster_pos != ctx.origin else None), "pred": u}]

    def _eligible_mark_centers(self, ctx: NCContext) -> list[tuple]:
        """Mirror `BasePlaybook.GetEligibleTargetsSelectable @18111f0d0` : hex candidats du marquage
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


class RitesOfRestorationPlaybook(NonComparablePlaybook):
    """`RitesOfRestorationPlaybook.EvaluateNonComparable @181157a60` (NonComparable, id 1039). Soin AoE +
    RESURRECTION (adeptHospitaller). Emet l'action en 1039, ciblee sur SOI (confirme live : ATK(1039,78)).

    - `ShouldEvaluate @1811580a0` : `Count(GetPossibleResurrectTargets) > 0` -> l'IA n'evalue Rites QUE
      s'il y a un allie DEFAIT. Morts lus via `obs_units.isDead` (decisionView garde les depouilles ->
      observeBattle est la source ; cf. project_decisionview_keeps_dead).
    - Gate (par position T du caster) : `(heroDead>=1 & |resurrectTiles|>=1) | (summonDead>=2 & |tiles|>=2)`.
      hero = allie mort avec trait `Hero` (UnitsWithTrait 0x10 @GetPossibleResurrectHeroTargets 181203d00) ;
      summon = allie mort SANS `Hero` (UnitsWithTrait 2 @181203d40). resurrectTiles = `CanAddUnit(
      AdjacentTiles(T))` @181203f70 = hex adjacents sur board, libres (unite vivante absente).
    - util = `1 + Count(GetHealTargets)` (cctor Fix64(1) @1811581d0 ; GetHealTargets @181203c80 =
      `Healable(owner + AdjacentFriends(owner,1))` = self (non-Mecanique) + amis adjacents non-Mecaniques).
      MIN_UTILITY=1 (Bucket du cctor). Sweep reach_nc (adjacence -> depend de la position -> le caster va
      la ou il soigne le plus).
    PRIORITY=0 ASSUME (get_Priority non RE ; a confirmer si l'inter-tier est exerce)."""
    ABILITY_ID = 1039
    MIN_UTILITY = 1.0
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        # ShouldEvaluate : Count(GetPossibleResurrectTargets) > 0. GetPossibleResurrectTargets @181203d80
        # = AllDeadUnits -> Friends -> UnitsWithTrait(0x1a=Imperial=26) -> UnitsAffectedByHealType(0).
        # IsAffectedByHealType(u,0) @180ed77d0 = HasTrait(0x421) OU non-Mecanique. (R1 corrige : mon port
        # ignorait les filtres Imperial + heal-type -> FAUX POSITIF sur allie mort non-Imperial/Mecanique,
        # masque par le test all-Imperial. Imperial = gameconfig GrandAllianceId ; heal-affectable ~
        # non-Mecanique, trait 0x421 override NON modelise -> TODO.) Morts lus via obs_units.isDead.
        def _resurrectable(u):
            cfg = _unit_cfg(u.get("visualId"))
            return (cfg.get("GrandAllianceId") == "Imperial"                 # UnitsWithTrait(0x1a=26)
                    and "Mechanical" not in (cfg.get("traits") or []))       # AffectedByHealType(0)
        dead = [u for u in obs if u.get("teamId") == team and u.get("isDead")
                and u.get("squadId") != ctx.uid and _resurrectable(u)]
        if not dead:
            return []   # Count(GetPossibleResurrectTargets) == 0 -> ability non evaluee
        # hero = ResurrectTargets ∩ UnitsWithTrait(0x10=Hero=16) @181203d00 ; summon = ∩ UnitsWithTrait(
        # Summon=2) @181203d40. Le trait "Summon" EST exposé par gameconfig (59 unités ; les summons
        # Imperial sont en section kind="summons", PAS "npc") -> l'ancien proxy kind=="npc" ratait 100%
        # des vrais summons ET comptait des npc non-summon (faux nég + faux pos, validateur) -> trait exact.
        hero_dead = sum(1 for u in dead if "Hero" in _traits(u.get("visualId")))
        summon_dead = sum(1 for u in dead if "Summon" in _traits(u.get("visualId")))
        # Alliees VIVANTES non-Mecaniques (heal targets adjacents) + occupation (resurrectTiles).
        ally_nonmech_pos = [(u.get("col"), u.get("row")) for u in obs
                            if u.get("teamId") == team and not u.get("isDead")
                            and u.get("squadId") != ctx.uid and u.get("col") is not None
                            and "Mechanical" not in _traits(u.get("visualId"))]
        self_nonmech = "Mechanical" not in _traits(me_obs.get("visualId"))
        occupied = {(u.get("col"), u.get("row")) for u in obs
                    if not u.get("isDead") and u.get("squadId") != ctx.uid
                    and u.get("col") is not None}                # le caster (mobile) n'occupe pas
        board = ctx.elev_by_pos or {}
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            res_tiles = [n for n in hexgeo.neighbors(*T)
                         if ((not board) or n in board) and n not in occupied]
            gate = (hero_dead >= 1 and len(res_tiles) >= 1) or (summon_dead >= 2 and len(res_tiles) >= 2)
            if not gate:
                continue
            heal_count = (1 if self_nonmech else 0) + sum(
                1 for p in ally_nonmech_pos if bq.is_adjacent(T, p, ctx.elev_by_pos))  # AdjacentUnits gate (#45/#76)
            util = 1.0 + heal_count
            if best is None or util > best[1]:   # strict > : 1er max garde (ordre reach_nc)
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Rites deadHero={hero_dead} deadSum={summon_dead} "
                  f"best={best} min={self.MIN_UTILITY}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,   # cast sur SOI (self-target)
                 "to": (T if T != ctx.origin else None), "pred": util}]


class CombatRestorativesPlaybook(NonComparablePlaybook):
    """`CombatRestorativesPlaybook.EvaluateNonComparable @181125fd0` (NonComparable, id 1002 ;
    ultraApothecary/Incisus). Soin AoE self + allies adjacents. Emet l'action ciblee sur SOI.

    - Ciblage `CombatRestorativesAbility.HealTargets @1811cca50` = `Friends(AdjacentUnits(caster,r=1))
      + self` -> SOI + unites ALLIEES adjacentes. Pas de wrapper `Healable` (contrairement a Rites
      @181203c80) : inclut les allies MECANIQUES (le natif compte leur fraction de PV manquante).
    - util(T) = `Σ (1 - FillUpStatComponent.RemainingPercentage) @180f9be60` sur {self + allies
      adjacents a T}. `RemainingPercentage = max(0, cur/max)` (Health fillup : cur@+0x18 / CurrentMax)
      -> `1 - RemainingPercentage = missing/maxHP` = FRACTION de PV MANQUANTE. N'utilise PAS le
      montant `hpToHeal` (magnitude != utilite dans ce regime NonComparable). Un allie plein -> 0.
    - MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (cctor @1811265c0). Sweep reach_nc (le caster
      va la ou la somme des fractions manquantes adjacentes est max), argmax STRICT.
    PRIORITY=0 ASSUME (get_Priority non RE ; a confirmer si l'inter-tier est exerce)."""
    ABILITY_ID = 1002
    MIN_UTILITY = 0.9      # cctor @1811265c0 : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    @staticmethod
    def _wound_fraction(u: dict) -> float:
        """`1 - FillUpStatComponent.RemainingPercentage` = `(maxHP - curHP)/maxHP` (>= 0). Health fillup
        lu depuis obs_units (hp/hpMax). maxHP <= 0 -> 0 (evite /0, comme le +1 defensif natif absent ici)."""
        mx = int(u.get("hpMax") or 0)
        if mx <= 0:
            return 0.0
        cur = int(u.get("hp") or 0)
        return max(0.0, 1.0 - cur / mx)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        self_wound = self._wound_fraction(me_obs)      # self TOUJOURS dans HealTargets (0 si plein)
        # Allies VIVANTS (self exclu) avec position -> candidats "adjacents a T" (Friends(AdjacentUnits)).
        allies = [(u.get("col"), u.get("row"), self._wound_fraction(u)) for u in obs
                  if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            # AdjacentUnits(caster@T, r=1) @180de8320 = AdjacentTiles + porte d'elevation |dElev|<2
            # d'IterateAdjacentTiles (#45/#76). bq.is_adjacent = MEME adjacence que les comptages
            # GetAdjacent* -> plus de fork raw-hexgeo qui sur-comptait des voisins hors-elevation.
            util = self_wound + sum(w for c, r, w in allies if bq.is_adjacent(T, (c, r), ctx.elev_by_pos))
            if best is None or util > best[1]:         # strict > : 1er max garde (ordre reach_nc)
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] CombatRestoratives selfW={self_wound:.2f} "
                  f"best={best} min={self.MIN_UTILITY}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        # Cible native = MainTile-id du caster (self-cast AoE : GenerateAction(this, pos, MainTile, util) ;
        # mesure live tgt=22 = id de la tuile (1,0) du caster). Fallback ctx.uid si tile-id absent.
        target = ctx.tile_id_by_pos.get(T, ctx.uid)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


class DefendTheDivineWorkPlaybook(NonComparablePlaybook):
    """`DefendTheDivineWorkPlaybook.EvaluateNonComparable @18112b9b0` (NonComparable REPAIR, id 1117 ;
    admecManipulus/Actus). Repair AoE self + allies adjacents ; emet l'action ciblee sur SOI (MainTile).

    - Ciblage = `CombatRestorativesAbility.HealTargets @1811cca50` REUTILISE (self + amis adjacents),
      GATE par `GetEligibleTargetsEntities` : l'ability n'est evaluee QUE s'il existe >=1 cible eligible
      (repair -> unite MECANIQUE). Sinon aucune action a cette position.
    - util(T) = `Σ (1 - FillUpStatComponent.RemainingPercentage_health @180f9be60)` sur {self + adjacents}
      + `0.5 × |{cible : IBattleQuery.HasValidTargets(cible, pos(cible), NormalAttackType(cible))}|`
      (slot 0x3f @18106e8d0 = "la cible peut-elle attaquer un ennemi avec son attaque NORMALE depuis sa
      position" = combat-readiness ; +0.5 par allie repare pret a combattre).
      *** GAP #37 : le terme +0.5 N'EST PAS PORTE (necessite HasValidTargets PAR-ALLIE = attack-reachability
      d'une AUTRE unite, absent offline). util port = Σ health-wound SEULE = BORNE INF de la native. ***
      Fiable des qu'un mecanique adjacent est lourdement blesse (Σ >= 0.9) ; marginal sinon (le +0.5
      manquant peut faire manquer le gate quand Σ health-wound seule < 0.9).
    - MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (cctor @18112c070). Sweep reach_nc, argmax STRICT.
    PRIORITY=0 ASSUME (get_Priority non RE)."""
    ABILITY_ID = 1117
    MIN_UTILITY = 0.9      # cctor @18112c070 : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        wf = CombatRestorativesPlaybook._wound_fraction
        self_wound = wf(me_obs)                                       # self TOUJOURS dans HealTargets
        self_mech = "Mechanical" in _traits(me_obs.get("visualId"))   # repair-eligible = Mecanique
        allies = [(u.get("col"), u.get("row"), wf(u), "Mechanical" in _traits(u.get("visualId")))
                  for u in obs if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            adj = [(w, mech) for c, r, w, mech in allies
                   if bq.is_adjacent(T, (c, r), ctx.elev_by_pos)]   # AdjacentUnits gate (#45/#76)
            # GATE GetEligibleTargetsEntities : >=1 cible MECANIQUE (self ou adjacent) sinon ability non evaluee.
            if not (self_mech or any(mech for _, mech in adj)):
                continue
            # util = Σ (1 - healthPct) sur self + adjacents (mirror boucle HealTargets). +0.5 readiness OMIS.
            util = self_wound + sum(w for w, _ in adj)
            if best is None or util > best[1]:                       # strict > : 1er max garde
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] DefendTheDivineWork selfMech={self_mech} best={best} "
                  f"min={self.MIN_UTILITY} (+0.5 readiness OMIS)", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)                  # MainTile-id (self-cast AoE)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


class RevitalizingMalignancyPlaybook(NonComparablePlaybook):
    """`RevitalizingMalignancyPlaybook.EvaluateNonComparable @181156790` (NonComparable heal, id 1037 ;
    deathRotbone/Nauseous). Soin AoE self + adjacents, FILTRE non-Imperial ET non-Mecanique.

    - Ciblage `GetAllHealTargets @181201150` = `Healable(UnitsWithoutTrait(0x1a=Imperial=26,
      Friends(AdjacentUnits(caster,r=1)) + self))` = self + amis adjacents qui sont NON-Imperial ET
      non-Mecanique (`Healable`). (Chaos ne soigne pas les Imperials ni les machines.)
    - util(T) = `Σ (1 - RemainingPercentage_health @180f9be60)` sur ces cibles (= Σ missing/max). Meme
      formule que CombatRestoratives. MIN_UTILITY = `Fix64.FromIntFraction(9,10) = 0.9` (cctor @181156d30).
      Sweep reach_nc, argmax STRICT ; self-cast (MainTile-id). PRIORITY=0 ASSUME."""
    ABILITY_ID = 1037
    MIN_UTILITY = 0.9      # cctor @181156d30 : Fix64.FromIntFraction(9,10)
    PRIORITY = 0

    @staticmethod
    def _healable(u: dict) -> bool:
        """`Healable ∘ UnitsWithoutTrait(Imperial)` : non-Imperial (GrandAllianceId) ET non-Mecanique (trait)."""
        cfg = _unit_cfg(u.get("visualId"))
        return (cfg.get("GrandAllianceId") != "Imperial"
                and "Mechanical" not in (cfg.get("traits") or []))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        obs = ctx.obs_units or []
        me_obs = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me_obs is None:
            return []
        team = me_obs.get("teamId")
        wf = CombatRestorativesPlaybook._wound_fraction
        self_wound = wf(me_obs) if self._healable(me_obs) else 0.0   # self compte SSI Healable
        allies = [(u.get("col"), u.get("row"), wf(u)) for u in obs
                  if u.get("teamId") == team and not u.get("isDead")
                  and u.get("squadId") != ctx.uid and u.get("col") is not None
                  and self._healable(u)]
        best = None  # (T, util)
        for T in _sweep_origin_first(ctx):   # ORIGINE d'abord : keep-first au tie -> reste en place (#76)
            util = self_wound + sum(w for c, r, w in allies
                                    if bq.is_adjacent(T, (c, r), ctx.elev_by_pos))  # AdjacentUnits gate (#45/#76)
            if best is None or util > best[1]:
                best = (T, util)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util}]


def _active_ability_levels(ctx: NCContext) -> dict:
    """`{unitId: activeAbilityLevel}` — délègue à `ctx.active_levels()` (bound sur l'AiDecisionContext,
    combatSnapshot cache/rid). `{}` si non branché (harnais de sonde) -> level 0 = argmax trivial a UN
    seul candidat (le niveau ne départage QUE plusieurs allies en cooldown)."""
    f = getattr(ctx, "active_levels", None)
    return f() if callable(f) else {}


class InspiredToGreatnessPlaybook(NonComparablePlaybook):
    """`InspiredToGreatnessPlaybook.EvaluateNonComparable @181145b80` (NonComparable, id 0x43a=1082 ;
    tauAunShi/Kroot). Refresh l'ability d'un ALLIE (`RepairOrHeal @1811eb050` = If(IsRepairable, Repair,
    Heal) + `InspiredToGreatness_OverrideLevelEffect`). Cible = l'ALLIE (unit-id), PAS une tuile.

    - Ciblage : `GetEligibleTargetsSelectable` (targeting `AActiveAbility`) filtre par
      `GetDynamicInvalidTargetReason @1811eaec0` = cible != caster, PAS trait 0x7e7, ET
      (repairable | healable-blesse | ability-en-cooldown) [slots 0x11/0x12/0x31]. -> on delegue au jeu
      via `ctx.ability_targets(uid, 1082)` (VIDE si aucun allie blesse/reparable/en-cooldown -> pas d'action).
    - util(cible) : le natif prend l'ACTIVE ability de la cible (`ActiveAbilityComponent.GetActive`) ;
      SEULEMENT si `ActiveAbility.CanCurrentlyBeUsed == FALSE` (= EN COOLDOWN) -> util =
      `Fix64.FromInt(Level.ToZeroBasedIndex(AbilityState.Level))` = NIVEAU zero-based de cette ability.
      Les allies dont l'active est PRETE (usable) NE contribuent PAS. `Bucket.AddAction` argmax STRICT ->
      l'IA refresh l'ability EN COOLDOWN de plus HAUT NIVEAU.
    - MIN_UTILITY=0 (ctor `NonComparablePlaybook(0x43a)` @181146090, SANS min explicite). PRIORITY=0 ASSUME.
    - Data offline : eligibilite = `abilityTargets` (jeu) ; cooldown = entree active de `dv.units[ally]
      .abilities` (`usable`) ; niveau = `combatSnapshot.unitConfig.activeAbilityLevel` (cfg+0xb8 ;
      `GetStat(18)`=null en snapshot -> via unitConfig). Le level ne departage QUE plusieurs allies en
      cooldown -> a UN seul candidat la cible est determinee sans lui. VALIDE LIVE (#78) : util=49 (level 50).
    - Eligibilite = `targets` (superset MOVE-inclus) : le natif BALAIE les tuiles de move et CASTE 1082 AVEC
      un move pour atteindre l'allie en cooldown quand il est hors portee in-place (VALIDE LIVE #78/#81).
    - POSITIONNEMENT move-to-reach (#81, PORTE + VALIDE LIVE via `castFromTiles`) : `to` = origine si l'allie
      est castable in-place (`currentValid`, origine-preference #76), sinon la 1re tuile de move LEGALE
      (`GetInvalidTargetReason(caster, tile, ally, 1082)` valide par tuile, ordre `GetMovableTilesFor`) ->
      MATCH EXACT natif (tauAunShi caste 1082 depuis (1,1) = port to=(1,1)). NB : le cas `currentValid=True`
      (origine castable) emet to=None par origine-preference #76 (self-cast confirme) ; NON separement crafte
      pour l'ally-target (le generateur keep-first-move-first pourrait BOUGER si des tuiles de move sont aussi
      legales -> a confirmer si un craft origine-castable apparait)."""
    ABILITY_ID = 1082
    MIN_UTILITY = 0.0     # ctor NonComparablePlaybook(0x43a) sans min -> 0
    PRIORITY = 0

    @staticmethod
    def _eligible_targets(at: dict) -> list:
        """Cibles alliees eligibles pour 1082 (le jeu a deja applique repairable/healable/on-cooldown).
        `targets` = superset MOVE-inclus (le natif balaie les tuiles de move pour atteindre l'allie ; cf.
        validation #78 ou le natif BOUGE pour caster). On prend ce superset pour l'ELIGIBILITE (ability+
        cible) ; la tuile de move exacte reste un raffinement de positionnement non porte."""
        out: list = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == InspiredToGreatnessPlaybook.ABILITY_ID:
                    src = a.get("targets") or []
                    out = [t.get("targetId") for t in src        # Tgt.targetId (PAS squadId)
                           if t.get("kind") == "unit" and t.get("targetId") is not None]
        return list(dict.fromkeys(out))

    @staticmethod
    def _active_ability(au: dict) -> dict | None:
        """`ActiveAbilityComponent.GetActive` : l'active NON-normale de l'unite (entree `kind` active/
        granted de `dv.units[i].abilities`)."""
        return next((ab for ab in (au.get("abilities") or [])
                     if ab.get("kind") in ("active", "granted")), None)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        eligible = self._eligible_targets(at)
        if not eligible:
            return []                                  # aucun allie eligible en portee -> pas d'action
        levels = _active_ability_levels(ctx)
        best = None  # (ally_id, level_zero_based)
        for ally_id in eligible:
            au = next((u for u in ctx.units if u.get("id") == ally_id), None)
            if au is None:
                continue
            active = self._active_ability(au)          # GetActive
            if active is None or active.get("usable") is not False:
                continue                               # requis : ability EN COOLDOWN (usable == False)
            lvl = max(0, int(levels.get(ally_id, 1)) - 1)   # ToZeroBasedIndex (activeAbilityLevel 1-based)
            if best is None or lvl > best[1]:          # argmax STRICT (keep-first au tie)
                best = (ally_id, lvl)
        if best is None:
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] InspiredToGreatness eligible={eligible} best=None",
                      file=sys.stderr)
            return []
        ally_id, lvl = best
        # POSITIONNEMENT (#81) : cast SANS bouger si l'allie est castable in-place (origine-preference #76) ;
        # sinon la 1re tuile de move LEGALE (GetInvalidTargetReason par tuile via castFromTiles) -> le natif
        # BALAIE les tuiles de move et caste depuis la 1re d'ou l'allie est atteignable (keep-first).
        to = None
        cft_fn = getattr(ctx, "cast_from_tiles", None)
        if callable(cft_fn):
            cft = cft_fn(ctx.uid, ally_id, self.ABILITY_ID) or {}
            if not cft.get("currentValid"):
                mt = cft.get("moveTiles") or []
                if mt:
                    to = (mt[0].get("col"), mt[0].get("row"))
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] InspiredToGreatness eligible={eligible} best={best} to={to}",
                  file=sys.stderr)
        # Cible = l'ALLIE (unit-id) ; to = origine (in-place) ou 1re tuile de move legale (#81).
        return [{"target": ally_id, "ability": self.ABILITY_ID, "to": to, "pred": float(lvl)}]


class ScarabSummonPlaybook(NonComparablePlaybook):
    """`ScarabSummonPlaybook.EvaluateNonComparable @181158f10` (auto-DÉDOUBLEMENT du scarab, id 0x417=1047).
    Pour CHAQUE cible éligible (`GetEligibleTargetsSelectable(MainTile(caster))` = tuiles de spawn ring-1
    libres adjacentes à SOI), `GenerateAction` à utilité CONSTANTE `Fix64.FromIntFraction(3,2)=1.5`.
    cctor @181159310 : MIN_UTILITY=1 (`Fix64.FromInt(1)`). ctor @181159380 : `NonComparablePlaybook(0x417)`
    SANS priorité -> get_Priority=**0** (défaut). Le caster NE bouge PAS (spawn adjacent à soi, pas de move).

    GAP : `GetUseProbability @181159220` (1.0 ou 1/2 selon un compteur runtime = `chance:50` gameconfig) =
    gate RNG NON modélisé offline -> le port décide TOUJOURS de se dédoubler dès qu'une tuile ring-1 est
    libre (le natif ~50%). Idem cap de duplication (`UnitDuplicationLimitSelector`) non porté."""
    ABILITY_ID = 1047
    MIN_UTILITY = 1.0
    _UTILITY = 1.5   # Fix64.FromIntFraction(3,2) — CONSTANTE par cible éligible

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # GetEligibleTargetsSelectable = tuiles de spawn ring-1 libres (kind="tile" via ability_targets offline).
        if ctx.ability_targets is None or self._UTILITY < self.MIN_UTILITY:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        has_tile = any(
            t.get("kind") == "tile"
            for u in (at.get("units") or [])
            for a in (u.get("abilities") or [])
            if a.get("abilityId") == self.ABILITY_ID
            for t in (a.get("targets") or []))
        if not has_tile:
            return []                                  # aucune tuile ring-1 libre -> pas de dédoublement
        # Utilité CONSTANTE 1.5 ; caster ne bouge pas (to=None) ; target=None (spawn adjacent-soi au runtime).
        return [{"target": None, "ability": self.ABILITY_ID, "to": None, "pred": self._UTILITY}]


class GetEmRuntzPlaybook(NonComparablePlaybook):
    """`GetEmRuntzPlaybook.EvaluateNonComparable @18113ee00` (id 1045, orksRuntherd). Utilité = NOMBRE de
    tuiles de spawn = |hex LIBRES adjacents au caster ∩ adjacents à un ennemi| (`GetSpawnTileSelector`).
    `MIN_UTILITY` = `minSummons` DYNAMIQUE selon les PV% du caster (`GetMinSummonsToUse @18113f0b0` :
    `GetStat(Health, part1=%)` -> <=49 => 1 ; 49<..<75 => 2 ; >=75 => 3). L'IA caste si `numTiles >= minSummons` ;
    utilité = `numTiles`. cctor @18113f250 : base 1. get_Priority = 0 (défaut). NonComparable = évaluée AVANT
    l'attaque. Le caster NE bouge PAS (spawn autour de sa position actuelle)."""
    ABILITY_ID = 1045
    MIN_UTILITY = 1.0      # plancher structurel ; le vrai gate = minSummons dynamique (generate_candidates)

    def _min_summons(self, ctx: NCContext) -> int:
        # GetMinSummonsToUse : PV% du caster -> 1/2/3 (défaut prudent 3 si inconnu).
        hp = hpmax = None
        for u in (ctx.obs_units or []):
            if u.get("squadId") == ctx.uid:
                hp, hpmax = u.get("hp"), u.get("hpMax")
                break
        if not hp or not hpmax:
            return 3
        pct = 100 * int(hp) // int(hpmax)
        return 1 if pct <= 49 else (2 if pct < 75 else 3)

    def _spawn_tile_count(self, ctx: NCContext) -> int:
        # GetSpawnTileSelector : hex LIBRES adjacents au caster (dist hex 1) ∩ adjacents à >=1 ennemi.
        valid = set(ctx.elev_by_pos.keys()) if ctx.elev_by_pos else set()
        occ = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
        n = 0
        for T in valid:
            if T in occ or hexgeo.distance(ctx.origin, T) != 1:
                continue
            if any(hexgeo.distance(e, T) == 1 for e in ctx.epos):    # adjacent à un ennemi
                n += 1
        return n

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        num = self._spawn_tile_count(ctx)
        if num <= 0 or num < self._min_summons(ctx):     # gate minSummons (HP%-dépendant)
            return []
        # utilité = nombre de grots qui apparaîtraient ; caster ne bouge pas (to=None) ; target=None.
        return [{"target": None, "ability": self.ABILITY_ID, "to": None, "pred": float(num)}]


# Registre abilityType -> instance de playbook (remplace le switch `kind`).
PLAYBOOKS: dict[int, NonComparablePlaybook] = {
    pb.ABILITY_ID: pb for pb in (
        BloodyFuryPlaybook(),
        VexillaMagnificaPlaybook(),
        FightingRetreatPlaybook(),
        AberrantHypermorphPlaybook(),
        NovaBoostPlaybook(),
        NovaShieldPlaybook(),
        RitesOfRestorationPlaybook(),
        CombatRestorativesPlaybook(),
        DefendTheDivineWorkPlaybook(),
        RevitalizingMalignancyPlaybook(),
        InspiredToGreatnessPlaybook(),
        ScarabSummonPlaybook(),
        GetEmRuntzPlaybook(),
    )
}


def playbook_for(ability_id: int) -> NonComparablePlaybook | None:
    return PLAYBOOKS.get(ability_id)


def is_noncomp(ability_id: int) -> bool:
    """L'ability a-t-elle un playbook NonComparable porté ?"""
    return ability_id in PLAYBOOKS


def is_summon(ability_id: int) -> bool:
    """L'ability est-elle le summon composé (AberrantHypermorph) ? Son targetId natif = l'unité
    SPAWNÉE (post-exec) — la comparaison d'agreement se fait sur l'ability seule, pas la cible."""
    return isinstance(PLAYBOOKS.get(ability_id), AberrantHypermorphPlaybook)


def choose_action(abilities: list, ctx: NCContext, priority: int | None = None) -> dict | None:
    """Driver d'UN generateur NonComparable (mirror `ActiveAbilityActionGenerator.GenerateActions`
    @18119a3f0 + `Bucket.ChooseAction`) : pour chaque ability NC usable de l'unite DU TIER `priority`
    (get_Priority ; None = tous tiers confondus), collecte les candidats de son playbook (generator +
    gate MIN_UTILITY), rend l'argmax STRICT (tie -> 1er) ou None si le generateur est vide.

    Le natif range les NonComparable dans `dict[get_Priority]` (@1810ed540) : un generateur PAR tier,
    evalues dans l'ordre 1000..-1000 AVANT le fallback Comparable. `priority` selectionne ce tier."""
    nc_cands: list[dict] = []
    for ab in (abilities or []):
        pb = playbook_for(ab.get("id"))
        if pb is None or ab.get("usable") is False:
            continue
        if priority is not None and pb.PRIORITY != priority:
            continue   # ability d'un autre tier NonComparable -> pas dans CE generateur
        nc_cands += pb.generate_candidates(ctx)
    if not nc_cands:
        return None
    if ctx.debug:
        import sys
        print(f"    [dbg NC u{ctx.uid}] tier{priority}="
              f"{[(c['ability'], c.get('target'), c.get('to'), c['pred']) for c in nc_cands]}",
              file=sys.stderr)
    return max(nc_cands, key=lambda c: c["pred"])   # strict : max() garde le 1er a egalite
