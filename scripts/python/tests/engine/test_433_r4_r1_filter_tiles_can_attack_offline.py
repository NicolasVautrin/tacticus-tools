"""#433-r4-r1 -- le BRAS DE RATTRAPAGE de
`IdunBattle.Entities.Selectors.FilterTilesIfCanAttackTargetTileFromSelector$$Select`.

Ce que cette garde verrouille
-----------------------------
Le natif, verbatim :

    if (query.GetAdjacentUnits(tile, null, enemyOf, false).Count == 0
        || TileExtensions.IsAdjacentTo(tile, targetTile))
        result.Add(tile);

Le SECOND bras rattrape une tuile que le premier refuse. Trois choses peuvent le faire disparaitre
en silence, et chacune a son test ici :

  1. ne pas porter le bras du tout -> l'ensemble rendu se reduit aux tuiles SANS ennemi adjacent
     (`test_le_bras_de_rattrapage_change_l_ensemble` : 3 tuiles gardees contre 0) ;
  2. porter le bras avec `hexgeo.distance == 1` au lieu de
     `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` -> la paire IDENTIQUE (`tile ==
     targetTile`) est refusee la ou le natif l'accorde par court-circuit
     (`test_identite_la_tuile_candidate_est_la_tuile_cible`, qui compare AUX DEUX predicats) ;
  3. porter le PREMIER bras avec la mauvaise primitive -- `AreTilesAdjacent` au lieu
     d'`IterateAdjacentTiles` -> un ennemi pose SUR la tuile candidate compterait comme adjacent
     (`test_l_occupant_de_la_tuile_candidate_n_est_pas_son_propre_voisin`).

S'y ajoutent les quatre axes du filtre d'unites de `BattleQuery$$CountOrGetUnitsOnTiles` (ami vs
ennemi, mort, pied SECONDAIRE d'une multi-hex, porte d'elevation) et la degradation des selections
vides. 100 % OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.dsl.base import DslContext                                     # noqa: E402
from engine.entities.selectors.accessors import FixedTileIds, Target
from engine.entities.selectors.tiles import Caster, FilterTilesIfCanAttackTargetTileFrom  # noqa: E402


class _Board:
    """Board hex minimal : la grille 7x7 complete, toutes les tuiles marchables."""

    def __init__(self, cols=7, rows=7):
        self._ids = {}
        n = 1
        for col in range(cols):
            for row in range(rows):
                self._ids[(col, row)] = n
                n += 1
        self._pos = {v: k for k, v in self._ids.items()}
        self.by_id = {t: {"col": p[0], "row": p[1]} for t, p in self._pos.items()}

    def id_at(self, col, row):
        return self._ids.get((int(col), int(row)))

    def coord(self, tid):
        return self._pos.get(tid)

    def neighbours(self, tid):
        c = self._pos[tid]
        return [self._ids[p] for p in hexgeo.neighbors(*c) if p in self._ids]

    def walkable(self, tid):
        return tid in self._pos


BOARD = _Board()
CASTER = {"id": 1, "team": 1, "alive": True, "hp": 100, "pos": {"col": 3, "row": 3}}
TARGET = {"id": 2, "team": 2, "alive": True, "hp": 100, "pos": {"col": 5, "row": 3}}


def _unit(uid, team, pos, alive=True, hp=100, feet=None):
    d = {"id": uid, "team": team, "alive": alive, "hp": hp,
         "pos": {"col": pos[0], "row": pos[1]}}
    if feet is not None:
        d["feet"] = [tuple(f) for f in feet]
    return d


def _ctx(units, elev=None, caster=CASTER, target=TARGET):
    return DslContext(units=units, caster=caster, target=target, board=BOARD, elev_by_pos=elev)


def _sel(tile_positions):
    ids = [BOARD.id_at(*p) for p in tile_positions]
    return FilterTilesIfCanAttackTargetTileFrom(Caster(), Target(), FixedTileIds(ids))


def _kept(ctx, tile_positions):
    return [BOARD.coord(t) for t in _sel(tile_positions).select(ctx)]


# ---------------------------------------------------------------- le bras lui-meme

def test_le_bras_de_rattrapage_change_l_ensemble():
    """Montage ou les DEUX ensembles DIFFERENT : toutes les candidates ont un ennemi adjacent.

    Sans le second bras, le selecteur rendrait VIDE ; avec lui, il rend exactement les tuiles
    adjacentes a la tuile de la cible. Le montage est construit pour que l'ecart soit maximal
    (0 contre 3) -- un accord entre les deux lectures serait tautologique."""
    tgt = (5, 3)
    ring = [p for p in hexgeo.neighbors(*tgt) if BOARD.id_at(*p) is not None]
    far = [(1, 1), (1, 3), (1, 5)]                     # loin de la cible, deux a deux disjointes
    bloqueurs = [(1, 2), (1, 4)]                       # un ennemi adjacent a CHACUNE des `far`
    for p in far:
        assert hexgeo.distance(p, tgt) >= 2, p
        assert any(hexgeo.distance(p, b) == 1 for b in bloqueurs), p
    units = [CASTER, TARGET] + [_unit(100 + i, 2, b) for i, b in enumerate(bloqueurs)]
    ctx = _ctx(units)
    cands = ring + far

    kept = _kept(ctx, cands)
    # la cible elle-meme est un ennemi adjacent a chaque tuile de son anneau -> premier bras FAUX
    # partout ; seul le bras de rattrapage les sauve.
    assert set(kept) == set(ring), (kept, ring)
    assert kept and len(kept) == len(ring) >= 3

    # CONTRE-EPREUVE : le port SANS le bras (premier operande seul) rendrait vide.
    from engine import battle_query as bq
    occ = [(u["pos"]["col"], u["pos"]["row"]) for u in units if u["team"] != CASTER["team"]]
    sans_bras = [p for p in cands if not any(bq.is_adjacent(p, o, None) for o in occ)]
    assert sans_bras == [], sans_bras


def test_identite_la_tuile_candidate_est_la_tuile_cible():
    """`tile == targetTile` : le natif GARDE la tuile par le court-circuit d'identite d'
    `MovementUtil$$AreTilesAdjacent`, un port en `hexgeo.distance == 1` la REFUSE.

    Le test compare explicitement les deux predicats sur la MEME paire : si le foyer venait a
    retomber sur la distance, l'assertion `distance != 1` rendrait le montage muet -- on verifie
    donc les deux, pas seulement le verdict."""
    tgt = (5, 3)
    # un ennemi adjacent a la tuile cible -> premier bras FAUX, seul le rattrapage peut sauver
    units = [CASTER, TARGET, _unit(10, 2, (5, 4))]
    ctx = _ctx(units)

    assert hexgeo.distance(tgt, tgt) != 1          # un port naif refuserait
    assert _kept(ctx, [tgt]) == [tgt]              # le port, lui, garde -- comme le natif

    from engine import battle_query as bq
    assert bq.are_entities_adjacent(tgt, tgt, None) is True
    assert bq.is_adjacent(tgt, tgt, None) is False  # les DEUX primitives sont bien distinctes


def test_l_occupant_de_la_tuile_candidate_n_est_pas_son_propre_voisin():
    """`GetAdjacentUnits` passe par `IterateAdjacentTiles`, qui ne rend JAMAIS la tuile source.

    Un ennemi pose SUR la tuile candidate ne la bloque donc pas. Confondre le premier bras avec
    `AreTilesAdjacent` (le foyer du SECOND) le ferait bloquer."""
    cand = (1, 1)
    units = [CASTER, TARGET, _unit(10, 2, cand)]
    assert _kept(_ctx(units), [cand]) == [cand]


# ------------------------------------------- le filtre d'unites de CountOrGetUnitsOnTiles

def test_un_ami_adjacent_ne_bloque_pas():
    """`enemiesOf: enemyOf` -> seuls les ENNEMIS du referent comptent (`friendsOf` est null)."""
    cand = (1, 1)
    units = [CASTER, TARGET, _unit(10, CASTER["team"], (1, 2))]
    assert _kept(_ctx(units), [cand]) == [cand]
    # et le meme voisin passe en camp adverse bloque, lui
    units[-1]["team"] = 2
    assert _kept(_ctx(units), [cand]) == []


def test_un_mort_n_occupe_plus_sa_tuile():
    """`GetUnit(tile)` lit le `TileContentComponent`, que `KillUnit` libere -> un cadavre adjacent
    ne compte pas (le canal `decisionView`, lui, garde les morts : sans ce filtre le port
    sur-compterait)."""
    cand = (1, 1)
    units = [CASTER, TARGET, _unit(10, 2, (1, 2), alive=False, hp=0)]
    assert _kept(_ctx(units), [cand]) == [cand]


def test_un_pied_secondaire_bloque_comme_la_main_tile():
    """Le contenu d'une tuile est une entite-PIED que la surcharge PIED re-resout en son unite
    (#433-r3-r1a) -> un ennemi multi-hex dont SEUL un pied secondaire est adjacent bloque."""
    cand = (1, 1)
    voisin = [p for p in hexgeo.neighbors(*cand) if BOARD.id_at(*p) is not None][0]
    loin = (6, 6)
    assert hexgeo.distance(loin, cand) > 1
    units = [CASTER, TARGET, _unit(10, 2, loin, feet=[loin, voisin])]
    assert _kept(_ctx(units), [cand]) == []
    # la MAIN TILE seule (port pre-#433-r3-r1a) ne verrait rien
    units[-1].pop("feet")
    assert _kept(_ctx(units), [cand]) == [cand]


def test_la_porte_d_elevation_vaut_pour_les_deux_bras():
    """`|dElev| < 2` est INCONDITIONNEL dans `IterateAdjacentTiles` et foldee dans
    `AreTilesAdjacent`. Un voisin trop haut ne bloque pas ; et une tuile cible trop haute ne
    rattrape pas."""
    cand = (1, 1)
    voisin = (1, 2)
    elev = {cand: 0, voisin: 5}
    units = [CASTER, TARGET, _unit(10, 2, voisin)]
    assert _kept(_ctx(units, elev=elev), [cand]) == [cand]      # voisin hors portee d'elevation
    assert _kept(_ctx(units), [cand]) == []                     # sans elevation : il bloque

    # bras 2 : la tuile cible est adjacente MAIS 5 crans plus haut -> pas de rattrapage
    tgt = (5, 3)
    cand2 = (5, 4)
    elev2 = {cand2: 0, tgt: 5, (5, 2): 0}
    units2 = [CASTER, TARGET, _unit(11, 2, (5, 5))]
    assert _kept(_ctx(units2), [cand2]) == [cand2]              # sans elevation : rattrape
    assert _kept(_ctx(units2, elev=elev2), [cand2]) == []       # avec : plus de rattrapage


# ---------------------------------------------------------------- degradations nommees

def test_selection_vide_rend_une_liste_vide():
    """`if (enemyOf == null || targetTile == null) return new List<Tile>();` -- les DEUX branches."""
    units = [CASTER, TARGET]
    sel = _sel([(1, 1)])
    assert sel.select(_ctx(units, caster=None)) == []
    assert sel.select(_ctx(units, target=None)) == []


def test_l_ordre_source_et_les_doublons_sont_preserves():
    """Le natif accumule dans un `List<Tile>` (pas un `OrderedSet`) : ni tri, ni dedup."""
    units = [CASTER, TARGET]
    a, b = (1, 1), (2, 2)
    assert _kept(_ctx(units), [b, a, b]) == [b, a, b]


# ------------------------------------- le CABLAGE : le repli de PickTile (1076) le traverse

class _StubBoard:
    """Board reduit aux SEULES tuiles fournies -- toutes marchables. Comme elles sont TOUTES
    occupees au montage, le chemin PRIMAIRE de `PickTile` rend une liste de candidates VIDE, ce qui
    est exactement la condition d'entree dans la branche de REPLI native.

    ⚠ PLAT ET SANS MUR, DELIBEREMENT (#287-r11-r2-r1) : le repli traverse desormais AUSSI le maillon
    `UnobscuredTiles` (le noeud DSL, monte par `mv71._unobscured_tiles` depuis #287-r11-r2-r1-r3),
    qui lit `elevation` / `is_wall` / `by_coord`.
    Les rendre CONSTANTS rend cet etage-la INERTE, et ce fichier continue donc de mesurer le seul
    maillon qui l'interesse -- `FilterTilesIfCanAttackTargetTileFrom`. La ligne de vue a sa propre
    garde (`test_287r11r2r1_los_summon_offline.py`)."""

    def __init__(self, positions):
        self._pos = {i + 1: (int(p[0]), int(p[1])) for i, p in enumerate(positions)}
        self._ids = {v: k for k, v in self._pos.items()}
        self.by_id = {t: {"col": p[0], "row": p[1], "elevation": 0} for t, p in self._pos.items()}
        self.by_coord = dict(self._ids)

    def id_at(self, col, row):
        return self._ids.get((int(col), int(row)))

    def coord(self, tid):
        return self._pos.get(tid)

    def neighbours(self, tid):
        c = self._pos[tid]
        return [self._ids[p] for p in hexgeo.neighbors(*c) if p in self._ids]

    def walkable(self, tid):
        return tid in self._pos

    def elevation(self, tid):
        return 0 if tid in self._pos else None

    def is_wall(self, tid):
        return False


class _StubScene:
    def __init__(self, board, units):
        self.board = board
        self._u = {u["id"]: u for u in units}
        self.pos_by_id = {u["id"]: u["pos"] for u in units}
        self.vis_by_id = {u["id"]: u.get("visualId") for u in units}
        self.tile_effects_by_pos = {}

    def pos(self, uid):
        return self.pos_by_id.get(uid)

    def hp(self, uid):
        return (self._u.get(uid) or {}).get("hp")

    def team(self, uid):
        return (self._u.get(uid) or {}).get("team")

    def ctx(self, uid):
        """`Scene.ctx(uid)` -- le `UnitContext` de l'unite (`ctx_by_id`).

        AJOUTE PAR #287-r11-r2-r1-r2 : `pick_tile_scene` lit desormais les traits par cette voie
        (le MEME objet que le `StatsComponent.ctx` de la face runner) au lieu de la borne STATIQUE
        `entity_trait_names(None, visualId)`. Ce stub n'a pas de contexte a offrir -> `None`, ce
        que `entity_trait_names` traite exactement comme avant (repli sur la borne statique) : le
        montage de CE fichier est donc inchange."""
        return None


def _scene_pick(drone_pos, enemy_pos=None):
    """Montage du REPLI de `PickTile` : cap atteint (3 drones), plateau entierement occupe.

    Rend ce que `pick_tile_scene` choisit -- la position de la tuile du drone le plus faible, ou
    None quand le dernier maillon (`FilterTilesIfCanAttackTargetTileFrom`) la refuse."""
    from engine.runner.abilities.loki import mv71
    unit_id = "tauSmnDroneSniper"
    rng = mv71._drone_attack_range(unit_id)
    assert rng >= 2, rng                      # le montage a besoin d'une distance 2 dans la portee
    tgt, cas = (5, 5), (0, 0)
    others = [(9, 9), (9, 8)]                 # les deux autres drones, plus PV -> pas les plus faibles
    pos = [tgt, cas, drone_pos] + others + ([enemy_pos] if enemy_pos else [])
    board = _StubBoard(pos)
    units = [
        {"id": 1, "team": 1, "hp": 100, "pos": cas, "visualId": "tauMarksman"},
        {"id": 2, "team": 2, "hp": 100, "pos": tgt, "visualId": "cible"},
        {"id": 3, "team": 1, "hp": 10, "pos": drone_pos, "visualId": unit_id},
        {"id": 4, "team": 1, "hp": 90, "pos": others[0], "visualId": unit_id},
        {"id": 5, "team": 1, "hp": 91, "pos": others[1], "visualId": unit_id},
    ]
    if enemy_pos:
        units.append({"id": 6, "team": 2, "hp": 100, "pos": enemy_pos, "visualId": "gene"})
    return mv71.pick_tile_scene(_StubScene(board, units), 1, 2, unit_id, 3)


def test_le_repli_de_pick_tile_traverse_le_bras():
    """Les TROIS regimes du dernier maillon, sur la chaine reelle de `PickTile` :

      * sans ennemi adjacent  -> la tuile passe (premier bras VRAI) ;
      * ennemi adjacent, tuile LOIN de la cible -> REFUSEE -> `PickTile` rend null (cast NO-OP) ;
      * ennemi adjacent (la cible ELLE-MEME), tuile ADJACENTE a la cible -> RATTRAPEE.

    Le troisieme cas est le discriminant : le port d'avant #433-r4-r1 rendait la tuile dans les
    TROIS cas, donc il ne differait du natif que sur le deuxieme -- une eviction de drone, un spawn,
    une attaque et un Markerlight de trop."""
    loin = (5, 3)                                    # distance 2 de la cible (5,5)
    colle = (5, 4)                                   # adjacente a la cible
    assert hexgeo.distance(loin, (5, 5)) == 2
    assert hexgeo.distance(colle, (5, 5)) == 1

    assert _scene_pick(loin) == loin                          # aucun ennemi adjacent
    assert _scene_pick(loin, enemy_pos=(5, 2)) is None        # bloque, pas de rattrapage
    assert _scene_pick(colle) == colle                        # la CIBLE est l'ennemi adjacent
