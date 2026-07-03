"""Playbooks NonComparable — une classe Python HOMONYME par playbook natif.

Remplace l'ancien switch `if kind in ("summon","adjacent_count","target_hp")` d'engine_decide
par un mecanisme generique (registre de classes + driver commun). Structure FIDELE au decompile
(confirme sur AberrantHypermorphPlaybook.EvaluateNonComparable @1811197d0) :

  - `ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` range chaque ability NonComparable par
    son playbook ; `GetDefaultActiveAbilityActionGenerators @1810ed0c0` cree les generators par
    priorite (tous les portes = Normal 0, aucun n'override get_Priority) ; le tactic prend le
    PREMIER generator non-vide -> une NC qui passe son MIN_UTILITY prime sur toute Comparable.
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

from dataclasses import dataclass

import hexgeo
from engine import battle_query as bq


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
    elev_by_pos: dict = None       # {(col,row): elevation} (tileMeta) — porte d'adjacence |Δelev|<2
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


# Registre abilityType -> instance de playbook (remplace le switch `kind`).
PLAYBOOKS: dict[int, NonComparablePlaybook] = {
    pb.ABILITY_ID: pb for pb in (
        BloodyFuryPlaybook(),
        VexillaMagnificaPlaybook(),
        FightingRetreatPlaybook(),
        AberrantHypermorphPlaybook(),
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
