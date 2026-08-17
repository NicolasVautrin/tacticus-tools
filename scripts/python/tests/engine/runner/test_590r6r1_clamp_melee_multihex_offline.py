"""#590-r6-r1 -- GARDE de la DOUBLE BOUCLE de
`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee`, atteinte par
`IdunBattle.Core.Services.AttackQuery$$ShouldApplyRangedInMelee` (slot `IAttackQuery 21`).

CE QUE LE DECOMPILE DIT, ET QUE LE PORT NE FAISAIT PAS :

    if (attackerTiles == null || attackerTiles.Count == 0) return false;
    if (!HasTrait(attacker, 0xb) && !ignoreTrait)          return false;
    if (UnitExtensions.HasFlag(attacker, 0x1c))            return false;
    foreach (attackerTile in attackerTiles)                  // <- BOUCLE 1, sur TOUS les pieds
      foreach (adj in <voisins de attackerTile>)             // <- BOUCLE 2
        u = UnitExtensions.GetUnit(adj, state);              // <- N'IMPORTE QUEL pied resout
        if (u != null && IsUnit(u) && !IsFriend(attacker, u, state)
            && !TileExtensions.HasSteppableUnit(adj, state)
            && DamageCalculations.CanMeleeAttackOverElevationDifference(attackerTile, adj)
            && IsTargetable(u) && IsAlive(u, state))  return true;
    return false;

DEUX ECARTS, tous deux PERMISSIFS (le port sous-estimait le clamp, donc laissait une portee que le
natif rabat a 1), tous deux BORNES AU MULTI-HEX :

  1. CASTER  -- le port prenait `_tile_of` (la MAIN TILE) au lieu de boucler sur `attackerTiles` ;
  2. CIBLE   -- le port comparait la `PositionComponent` (donc la MAIN TILE) de chaque entite a
     l'ensemble des voisins, la ou `UnitExtensions$$GetUnit(adj, state)` suit
     `TileContentComponent -> UnitFootComponent -> unite parente` (les TROIS surcharges lues) ;
     l'elevation testee changeait avec, puisque `CanMeleeAttackOverElevationDifference` prend la
     tuile ADJACENTE et le PIED de la boucle, pas deux main tiles.

REGIME DEGENERE, ET C'EST LA RAISON DE CE FICHIER : sur une unite a 1 pied des DEUX cotes, les
deux formes coincident EXACTEMENT -- un montage mono-hex serait vert avant comme apres, donc ne
conclurait RIEN. Chaque bascule ci-dessous porte donc un TEMOIN MULTI-HEX non nul, et l'etage 5
joue les MUTANTS (la forme d'avant, remise en place par substitution) : chacun doit faire
S'EFFONDRER la bascule qu'il vise.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et ASSUME : ce fichier importe `load_state` (tout le substrat runner) et le
    # foyer `targeting`. Les DEUX formes de glob sont necessaires (`**/` exige un SEGMENT).
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` : aucune valeur n'est figee depuis le binaire. Ce qui est fige, c'est la
    # STRUCTURE lue au decompile (deux boucles, et la resolution d'occupant par TOUT pied).
    "build": False,
    # offline, board fabrique, ~1 s.
    "toujours": True,
    "raison": "Double boucle de ShouldApplyRangedInMelee (#590-r6-r1) : le clamp melee se mesure "
              "depuis TOUS les pieds du caster et contre l'occupant de la tuile ADJACENTE, quel "
              "que soit le pied par lequel il l'occupe. Le fichier ne peut changer de verdict que "
              "si ce mirror, le substrat de montage ou l'adjacence du board changent.",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                          # noqa: E402
from engine.entities.unit_flag import UnitFlag                                   # noqa: E402
from engine.runner.snapshot import load_state                                    # noqa: E402
import engine.runner.abilities.targeting as T                                    # noqa: E402

# ================================================================================================
# SUBSTRAT -- grille hexagonale 6 x 4, PLATE par defaut, elevations posables tuile par tuile
# ================================================================================================
#
#   Le CASTER occupe TROIS tuiles : main (1,1), puis (1,2), puis (2,2).
#     * `(2,1)` est voisine de la MAIN TILE      -> les deux formes du port la voient ;
#     * `(3,2)` est voisine de `(2,2)` SEULEMENT -> SEULE la double boucle la voit.
#   La geometrie est DERIVEE (`hexgeo.neighbors`), jamais recopiee : l'etage 0 la re-mesure.

COLS, ROWS = 6, 4

CASTER_FEET = [(1, 1), (1, 2), (2, 2)]      #: ordre des pieds == ordre d'`AddFoot` == `_feet`
TUILE_VOISINE_DE_LA_MAIN = (2, 1)
TUILE_VOISINE_DU_SEUL_3E_PIED = (3, 2)
TUILE_LOINTAINE = (5, 0)

#: Cible MULTI-HEX connexe dont la MAIN TILE est hors de portee du caster mono-hex en (1,1), et
#: dont le DERNIER pied, lui, le touche. C'est le volet 2 (`GetUnit(adj)` remonte au parent).
CIBLE_FEET = [(4, 1), (3, 1), (2, 1)]

U_CASTER, U_ENNEMI = 9001, 9002


def _board(elevations=None) -> Board:
    elevations = elevations or {}
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row,
                           "elevation": int(elevations.get((col, row), 0)),
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _tid(col: int, row: int) -> int:
    return col * 100 + row + 1                 # ids de TUILE, disjoints des ids d'unite


def _substrat(unites, elevations=None, traits=None, flags=None):
    """`unites` = [(uid, team, [pieds...])]. Les pieds arrivent par `observeBattle` (UNE LIGNE PAR
    PIED, `entityId` croissant), qui est EXACTEMENT le canal que `snapshot._load_feet` consomme --
    pas un `set_unit_feet` pose a la main."""
    traits, flags = traits or {}, flags or {}
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "u%d" % uid, "alive": True, "team": team, "owner": team,
         "pos": {"col": pieds[0][0], "row": pieds[0][1]}, "effects": []}
        for (uid, team, pieds) in unites]}
    ob_units, eid = [], 100
    for (uid, _team, pieds) in unites:
        for (col, row) in pieds:
            eid += 1
            ob_units.append({"squadId": uid, "entityId": eid, "col": col, "row": row,
                             "hp": 100, "hpMax": 100})
    snap = {"units": [{"entityId": uid, "traits": list(traits.get(uid, ())),
                       "unitFlags": list(flags.get(uid, ()))}
                      for (uid, _t, _p) in unites]}
    return load_state(dv, {"units": ob_units}, snap, board=_board(elevations))


def _clamp(unites, **kw) -> bool:
    return T.should_apply_ranged_in_melee(_substrat(unites, **kw), U_CASTER)


# ================================================================================================
# 0. LE SUBSTRAT DIT-IL CE QU'ON CROIT ? (sans ca, toutes les bascules sont vraies par VACUITE)
# ================================================================================================

def test_la_geometrie_du_montage_est_celle_qu_on_croit():
    """Les deux tuiles-leviers sont DERIVEES de `hexgeo`, jamais supposees : l'une ne touche QUE le
    3e pied, l'autre touche la main tile. Si cette relation cassait, l'etage 1 deviendrait vert
    pour la mauvaise raison."""
    main = CASTER_FEET[0]
    vois_main = set(hexgeo.neighbors(*main))
    vois_3e = set(hexgeo.neighbors(*CASTER_FEET[2]))
    assert TUILE_VOISINE_DU_SEUL_3E_PIED in vois_3e, "le levier ne touche plus le 3e pied"
    assert TUILE_VOISINE_DU_SEUL_3E_PIED not in vois_main, "le levier touche AUSSI la main tile"
    assert TUILE_VOISINE_DE_LA_MAIN in vois_main, "le temoin ne touche plus la main tile"
    assert TUILE_LOINTAINE not in (vois_main | vois_3e | set(hexgeo.neighbors(*CASTER_FEET[1])))
    # ... et la cible multi-hex : main tile HORS de portee, dernier pied AU CONTACT.
    assert CIBLE_FEET[0] not in vois_main, "la main tile de la cible touche deja le caster"
    assert CIBLE_FEET[-1] in vois_main, "le dernier pied de la cible ne touche plus le caster"
    for a, b in zip(CIBLE_FEET, CIBLE_FEET[1:]):
        assert b in set(hexgeo.neighbors(*a)), "l'empreinte de la cible n'est pas connexe"


def test_le_seed_des_pieds_mord_vraiment():
    """`snapshot._load_feet` ne materialise `UnitComponent.feet` qu'a partir de DEUX lignes. Un
    montage qui n'en poserait qu'une rendrait tout ce fichier mono-hex, donc DEGENERE."""
    st = _substrat([(U_CASTER, 1, CASTER_FEET)])
    from engine.runner.components import get_unit_feet, get_main_tile  # noqa: PLC0415
    assert get_unit_feet(st, U_CASTER) == CASTER_FEET
    assert get_main_tile(st, U_CASTER) == CASTER_FEET[0], "la main tile n'est pas `feet[0]`"


# ================================================================================================
# 1. VOLET CASTER -- `foreach (attackerTile in attackerTiles)`
# ================================================================================================

def test_un_ennemi_au_contact_d_un_pied_NON_PRINCIPAL_clampe():
    """LA BASCULE DE #590-r6-r1. L'ennemi ne touche AUCUNE tuile voisine de la main tile ; il est au
    contact du 3e pied. Le natif boucle sur les trois pieds -> `true`. Le port d'avant lisait
    `_tile_of` -> `false`, donc laissait la portee entiere : ecart PERMISSIF."""
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])]) is True


def test_le_temoin_MAIN_TILE_et_le_temoin_LOINTAIN_encadrent_la_bascule():
    """Sans ces deux-la, le `True` ci-dessus pourrait venir d'un mirror devenu constant."""
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DE_LA_MAIN])]) is True
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_LOINTAINE])]) is False


def test_l_elevation_se_mesure_DEPUIS_LE_PIED_de_la_boucle_pas_depuis_la_main_tile():
    """`CanMeleeAttackOverElevationDifference(attackerTile, adj)` prend la tuile de la boucle. On
    pose une elevation ABSURDE sur la MAIN TILE : elle ne doit RIEN changer, puisque la paire
    evaluee est (3e pied, tuile de l'ennemi). Un port qui mesurerait depuis la main tile rendrait
    `False` ici (|5 - 0| >= 2)."""
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])],
                  elevations={CASTER_FEET[0]: 5}) is True
    # ... et la porte MORD bien quand c'est la BONNE paire qui est ecartee.
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])],
                  elevations={TUILE_VOISINE_DU_SEUL_3E_PIED: 2}) is False


def test_les_trois_conjonctions_du_corps_natif_tiennent_sur_le_pied_NON_PRINCIPAL():
    """`!IsFriend`, `!HasSteppableUnit(adj)` et `IsTargetable(u)` -- evaluees sur l'occupant trouve
    par la 2e boucle, donc sur le MEME chemin que la bascule ci-dessus."""
    base = [(U_CASTER, 1, CASTER_FEET), (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])]
    ami = [(U_CASTER, 1, CASTER_FEET), (U_ENNEMI, 1, [TUILE_VOISINE_DU_SEUL_3E_PIED])]
    assert _clamp(ami) is False, "`!IsFriend(caster, u, state)`"
    assert _clamp(base, traits={U_ENNEMI: [int(UnitTrait.Steppable)]}) is False, \
        "`!TileExtensions.HasSteppableUnit(adj, state)`"
    assert _clamp(base, flags={U_ENNEMI: [int(UnitFlag.Untargetable)]}) is False, \
        "`UnitExtensions.IsTargetable(u)`"


def test_le_drapeau_IngoreRangedInMelee_court_circuite_AVANT_les_deux_boucles():
    """`if (HasFlag(attacker, 0x1c)) return false;` est en TETE : il dispense du clamp, il ne filtre
    pas les voisins. (Typo native conservee : `enums.tsv` porte `28=IngoreRangedInMelee`.)"""
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])],
                  flags={U_CASTER: [int(UnitFlag.IngoreRangedInMelee)]}) is False


# ================================================================================================
# 2. VOLET CIBLE -- `GetUnit(adj, state)` remonte de N'IMPORTE QUEL pied a son unite
# ================================================================================================

def test_une_cible_multihex_touchant_par_un_pied_NON_PRINCIPAL_clampe():
    """Caster a UN pied, cible a TROIS. Sa main tile `(4,1)` est loin ; son dernier pied `(2,1)`
    touche le caster. Le port d'avant comparait la `PositionComponent` de la cible (donc `(4,1)`)
    a l'ensemble des voisins -> `False`. Le natif resout l'occupant de `(2,1)` -> l'UNITE."""
    assert _clamp([(U_CASTER, 1, [CASTER_FEET[0]]), (U_ENNEMI, 2, CIBLE_FEET)]) is True
    # temoin : la MEME cible, translatee d'un cran, ne touche plus rien
    loin = [(c + 2, r) for (c, r) in CIBLE_FEET]
    assert _clamp([(U_CASTER, 1, [CASTER_FEET[0]]), (U_ENNEMI, 2, loin)]) is False


def test_l_elevation_se_mesure_sur_la_TUILE_ADJACENTE_pas_sur_la_main_tile_de_la_cible():
    """Meme demonstration que l'etage 1, cote CIBLE : une elevation absurde sur SA main tile ne
    change rien ; c'est celle de la tuile au contact qui decide."""
    mono = [(U_CASTER, 1, [CASTER_FEET[0]]), (U_ENNEMI, 2, CIBLE_FEET)]
    assert _clamp(mono, elevations={CIBLE_FEET[0]: 5}) is True
    assert _clamp(mono, elevations={CIBLE_FEET[-1]: 2}) is False


# ================================================================================================
# 3. VALUE-PRESERVATION -- le regime MONO-HEX est celui d'avant, a l'identique
# ================================================================================================

def test_mono_hex_des_deux_cotes_le_verdict_est_inchange():
    """Les deux formes coincident exactement sur une unite a 1 pied : c'est ce qui rend l'ecart
    BORNE au multi-hex, et c'est aussi pourquoi aucun test mono-hex existant ne bouge."""
    for cible, attendu in ((TUILE_VOISINE_DE_LA_MAIN, True), (TUILE_LOINTAINE, False)):
        assert _clamp([(U_CASTER, 1, [CASTER_FEET[0]]), (U_ENNEMI, 2, [cible])]) is attendu


def test_le_parametre_caster_tiles_interroge_une_position_HYPOTHETIQUE():
    """`casterTiles` est le 2e argument natif : il REMPLACE l'empreinte reelle, et il accepte une
    LISTE -- donc une empreinte hypothetique complete, pas seulement sa premiere tuile."""
    st = _substrat([(U_CASTER, 1, [CASTER_FEET[0]]),
                    (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])])
    assert T.should_apply_ranged_in_melee(st, U_CASTER) is False, "position REELLE : pas au contact"
    assert T.should_apply_ranged_in_melee(st, U_CASTER, [CASTER_FEET[2]]) is True
    # la LISTE compte en entier : la 1re tuile ne touche rien, la 3e si.
    assert T.should_apply_ranged_in_melee(st, U_CASTER, CASTER_FEET) is True
    assert T.should_apply_ranged_in_melee(st, U_CASTER, []) is False, "`attackerTiles.Count == 0`"


# ================================================================================================
# 4. LE CLAMP REMONTE JUSQU'A `get_range` -- la face DECISION, pas seulement le predicat
# ================================================================================================

def test_le_clamp_rabat_la_portee_a_1_dans_get_range():
    """Sans ce cran, le mirror serait juste et INERTE : c'est `GetRange` qui consomme
    `ShouldApplyRangedInMelee`, sous `RangedBoolExtensions.IsTrue(options.ForceMeleeTarget)`.

    ⚠ LE PRESET GENERIQUE NE PEUT PAS SERVIR DE TEMOIN ICI, et c'est une MESURE, pas un choix de
    confort : son `onlyAdjacent` vaut `IfNotRangedCaster`, donc il est deja VRAI pour un caster
    sans le trait `Ranged` -- les deux bras rendraient `only_adjacent = True` et le test serait
    vert par VACUITE (mesure du premier jet : `Range(value=0, only_adjacent=True)` DANS LES DEUX).
    On prend donc un masque dont la portee est un `overrideRange` explicite : la bascule porte
    alors sur les DEUX champs a la fois."""
    opts = T.TargetingOptions(rules=T.TR.TargetIsEnemy,
                              range=T.TargetingRange(only_adjacent=T.RANGED_BOOL_FALSE,
                                                     override_range=5),
                              force_melee_target=T.RANGED_BOOL_TRUE)
    loin = _substrat([(U_CASTER, 1, CASTER_FEET), (U_ENNEMI, 2, [TUILE_LOINTAINE])])
    pres = _substrat([(U_CASTER, 1, CASTER_FEET),
                      (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])])
    r_loin = T.get_range(loin, U_CASTER, opts)
    r_pres = T.get_range(pres, U_CASTER, opts)
    assert (r_loin.value, r_loin.only_adjacent) == (5, False), (
        "sans ennemi au contact, la portee doit rester entiere -- sinon la bascule ne mesure rien")
    assert (r_pres.value, r_pres.only_adjacent) == (1, True), (
        "l'ennemi au contact d'un pied NON PRINCIPAL doit rabattre la portee a 1 et forcer "
        "`onlyAdjacent` : c'est l'ecart PERMISSIF de #590-r6-r1, vu par son consommateur")


# ================================================================================================
# 5. MUTANTS -- la forme d'AVANT, remise en place. Chaque bascule doit S'EFFONDRER.
# ================================================================================================

def _occupants_MAIN_TILE_SEULE(state, board):
    """Le mutant du volet CIBLE : la forme d'avant, qui indexait la `PositionComponent`."""
    from engine.runner.components import (PositionComponent, UnitComponent)   # noqa: PLC0415
    out = {}
    for _eid, ent in state.entities.items():
        uc = ent.get_component(UnitComponent)
        pc = ent.get_component(PositionComponent)
        if uc is None or pc is None or not uc.alive:
            continue
        tid = board.id_at(pc.col, pc.row)
        if tid is not None:
            out.setdefault(int(tid), ent)
    return out


def test_MUTANT_occupant_par_la_main_tile_effondre_le_volet_CIBLE(monkeypatch):
    monkeypatch.setattr(T, "_occupants_by_tile_id", _occupants_MAIN_TILE_SEULE)
    assert _clamp([(U_CASTER, 1, [CASTER_FEET[0]]), (U_ENNEMI, 2, CIBLE_FEET)]) is False, (
        "le volet CIBLE est vert MEME avec l'occupant lu a la main tile : il ne mesure rien")
    # ... mais le volet CASTER, lui, doit SURVIVRE a ce mutant-ci (les deux sont independants).
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])]) is True


def test_MUTANT_caster_reduit_a_sa_main_tile_effondre_le_volet_CASTER(monkeypatch):
    monkeypatch.setattr(T, "caster_tiles_of",
                        lambda state, cid, tiles=None: (T.entity_tiles(state, cid) or [])[:1]
                        if tiles is None else [(int(t[0]), int(t[1])) for t in tiles][:1])
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])]) is False, (
        "le volet CASTER est vert MEME avec le caster reduit a sa main tile")
    # ... et le TEMOIN main tile survit : le mutant n'a pas simplement tout eteint.
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DE_LA_MAIN])]) is True


def test_MUTANT_elevation_lue_a_la_main_tile_effondre_l_etage_3(monkeypatch):
    """Le mutant le plus fin : boucler sur les pieds MAIS garder l'elevation de la main tile."""
    origine = T.should_apply_ranged_in_melee

    def _mutant(state, caster_id, caster_tiles=None):
        board = state.board
        feet = T.caster_tiles_of(state, caster_id, caster_tiles)
        if board is None or not feet:
            return False
        main_tid = board.id_at(feet[0][0], feet[0][1])
        occ = T._occupants_by_tile_id(state, board)
        from engine.runner.components import OwnerComponent            # noqa: PLC0415
        c_owner = state.get_entity(int(caster_id)).get_component(OwnerComponent)
        for src in feet:
            stid = board.id_at(src[0], src[1])
            if stid is None:
                continue
            for tid in board.neighbours(stid):
                ent = occ.get(int(tid))
                if ent is None or int(ent.id) == int(caster_id):
                    continue
                oc = ent.get_component(OwnerComponent)
                if oc is None or oc.team == c_owner.team:
                    continue
                if abs(board.elevation(main_tid) - board.elevation(tid)) >= 2:
                    continue                       # <- MUTATION : elevation de la MAIN TILE
                return True
        return False

    monkeypatch.setattr(T, "should_apply_ranged_in_melee", _mutant)
    assert origine is not T.should_apply_ranged_in_melee
    assert _clamp([(U_CASTER, 1, CASTER_FEET),
                   (U_ENNEMI, 2, [TUILE_VOISINE_DU_SEUL_3E_PIED])],
                  elevations={CASTER_FEET[0]: 5}) is False, (
        "l'etage 3 est vert MEME avec l'elevation lue a la main tile : il ne discrimine pas")
