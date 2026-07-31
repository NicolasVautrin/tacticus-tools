"""AberrantHypermorphPlaybook — action composee move+summon (NonComparable)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class AberrantHypermorphPlaybook(NonComparablePlaybook):
    """IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$EvaluateNonComparable (action COMPOSEE move+summon).
    Le generator balaie les tuiles de MOVE du caster ; par tuile T, le selector
    `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` rend les tuiles de SPAWN eligibles (ring-1 libre,
    portee=1 — gameconfig 1166 « free adjacent hex ») ; utilite d'un spawn ST = #ennemis adjacents
    (`IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility`, slot 0x7f GetAdjacentEnemies -> Fix64.FromInt). Le caster BOUGE vers la
    tuile T qui maximise ce count. IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$.cctor : MIN_UTILITY=1.

    CIBLE EMISE = la TUILE DE SPAWN (id via `ctx.tile_id_by_pos`), comme MasterOfTheTutelaries.
    MESURE #343 (decompile) : le natif boucle SUR LES CIBLES et emet UNE action par tuile de spawn —
    `UnitAction..ctor(new UnitPosition(MainTile(casterPosition)), summonTile, abilityType)`, ou
    `summonTile` est le champ `+0x10` de l'element de la liste rendue par
    `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (cet element est un struct de
    0x128 octets dont `+0x10` = l'ENTITE cible, ecrit par le selector juste apres
    `GetEligibleTargetsEntities`). Le nom du parametre le confirme :
    `IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility(caster, summonTile)`.
    L'ancien port rendait `target: None` — il gardait l'argmax de l'utilite mais JETAIT la tuile
    argmax ; le natif, lui, n'a jamais de cible nulle ici.

    ORDRE (mirror du bucket) : positions T dans l'ordre de `reach_nc` (origine d'abord), et par
    position les cibles dans l'ordre du selector ;
    `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` ne remplace
    que si STRICTEMENT superieur -> la PREMIERE paire (T, ST) du maximum gagne. Une position sans
    tuile de spawn eligible n'ajoute AUCUNE action au bucket (elle ne peut donc pas gagner).

    NB abilityTargets.targets = UNION des spawns sur TOUTES les tuiles de move
    (GetAllValidTargetsFromAllPossibleMovementTiles, dist 0-4 de l'origine) — le filtre
    distance(T,ST)==1 reconstitue le per-tuile."""
    ABILITY_ID = int(ActiveAbilityType.AberrantHypermorph)  # 1166
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        spawn_tiles = self._eligible_spawn_tiles(ctx)
        best = None   # (position T, tuile de spawn ST, utilite)
        for T in ctx.reach_nc:   # positions candidates du caster (origine + tuiles de move)
            for ST in spawn_tiles:
                if hexgeo.distance(T, ST) != 1:
                    continue     # spawn = hex libre ADJACENT a la position T
                # IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$GetUtility (slot 0x7f GetAdjacentEnemies) = #ennemis adjacents au spawn ST.
                u_ = float(bq.count_adjacent(ST, ctx.epos, ctx.elev_by_pos))
                if best is None or u_ > best[2]:   # strict > : 1re paire (T, ST) du max garde
                    best = (T, ST, u_)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        t, st, u_ = best
        tid = (ctx.tile_id_by_pos or {}).get(st)
        return [{"target": (tid if tid is not None else st), "ability": self.ABILITY_ID,
                 "to": (t if t != ctx.origin else None), "pred": u_}]

    def _eligible_spawn_tiles(self, ctx: NCContext) -> list[tuple]:
        """Mirror IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable : union des tuiles de spawn
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
