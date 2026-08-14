"""GetEmRuntzPlaybook — summon de grots NonComparable (gate minSummons HP%)."""
from __future__ import annotations

from engine import battle_query as bq   # forme B (#485-r1-r1) : foyer des DEUX etages
#                                         d'`IterateAdjacentTiles` (#943-r7)
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class GetEmRuntzPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$EvaluateNonComparable` (id 1045, orksRuntherd). Utilité = NOMBRE de
    tuiles de spawn = |hex LIBRES adjacents au caster ∩ adjacents à un ennemi| (`GetSpawnTileSelector`).
    `MIN_UTILITY` = `minSummons` DYNAMIQUE selon les PV% du caster (`IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$GetMinSummonsToUse` :
    `GetStat(Health, part1=%)` -> <=49 => 1 ; 49<..<75 => 2 ; >=75 => 3). L'IA caste si `numTiles >= minSummons` ;
    utilité = `numTiles`. IdunBattle.AI.Playbook.Loki.GetEmRuntzPlaybook$$.cctor : base 1. get_Priority = 0
    (`AbilityPriority.Normal` : 1045 hors `NATIVE_PRIORITY`, sweep exhaustif #170). NonComparable = évaluée AVANT
    l'attaque. Le caster NE bouge PAS (spawn autour de sa position actuelle)."""
    ABILITY_ID = int(ActiveAbilityType.GetEmRuntz)  # 1045
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
        """`GetEmRuntzAbility$$GetSpawnTileSelector` -- DECOMPILE RELU (#943-r7) :

            CanAddUnit( AdjacentTiles(Caster@+0x50) )
          & Unique( AdjacentTiles( UnitsWithoutTrait(Enemies(Caster@+0x48, AllUnits@+0x20, 3),
                                                     0x1b = Steppable, 3) ) )

        DEUX `AdjacentTiles`, donc les DEUX comparaisons portent le substrat STOCKE -- la premiere
        sur le voisinage du CASTER, la seconde sur celui de CHAQUE ENNEMI.

        ⚠ LA DIRECTION COMPTE, et la geometrie la masquait. `AdjacentTiles(source)` enumere le
        voisinage de la tuile SOURCE, et le canal `neighbours` est le champ BRUT (ni trie ni
        symetrise) : `is_adjacent(a, b)` lit `neigh[a]`, donc l'ordre des arguments n'est PAS
        indifferent la ou `hexgeo.distance(a, b) == hexgeo.distance(b, a)` l'etait. Le second terme
        s'ecrit donc `is_adjacent(e, T)` -- voisins de l'ENNEMI -- et non l'inverse.

        La face COMBAT du meme selecteur (`runner/abilities/loki/summon.py`, tile-selecteur DSL
        `CanAddUnit(AdjacentTiles(self))` -> `entities/selectors/tiles.py::AdjacentTiles` ->
        `board.neighbours_native`) lit DEJA la liste stockee : cabler ici **RESORBE** la divergence.

        ⚠ NON PORTE ICI, et ce n'est pas de l'adjacence : l'etage `UnitsWithoutTrait(..., 0x1b =
        Steppable)` du second terme (le port compte TOUT `ctx.epos`) et le `selectionType 3` du
        `Enemies`. Direction PERMISSIVE, hors perimetre #943-r7 -- releve, pas comble."""
        valid = set(ctx.elev_by_pos.keys()) if ctx.elev_by_pos else set()
        occ = bq.occupied_positions(ctx)          # #969-r3 : PAR PIED (`TileContentComponent`)
        elev, neigh = ctx.elev_by_pos, bq.neigh_map(ctx)
        n = 0
        for T in valid:
            # `AdjacentTiles(Caster)` : T est un voisin STOCKE de la tuile du caster.
            if T in occ or not bq.is_adjacent(ctx.origin, T, elev, neigh):
                continue
            # `AdjacentTiles(Enemies(...))` : T est un voisin STOCKE d'AU MOINS un ennemi.
            if any(bq.is_adjacent(e, T, elev, neigh) for e in ctx.epos):
                n += 1
        return n

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        num = self._spawn_tile_count(ctx)
        if num <= 0 or num < self._min_summons(ctx):     # gate minSummons (HP%-dépendant)
            return []
        # utilité = nombre de grots qui apparaîtraient ; caster ne bouge pas (to=None) ; target=None.
        return [{"target": None, "ability": self.ABILITY_ID, "to": None, "pred": float(num)}]
