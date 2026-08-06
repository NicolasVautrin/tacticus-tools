"""#287-r11-r1 -- GARDE des trois regles dynamiques de ciblage portees (1016, 1180, 1197).

Le probe LIVE (`probe_287r11r1_regles_ciblage_live.py`) prouve que les trois regles repondent COMME
LE NATIF sur un plateau reel ; ce fichier-ci garde ce que le live ne peut pas atteindre -- les bras
qu'aucun montage n'a produits -- et surtout les lectures NON TRIVIALES de la RE, chacune sous un
substrat qui SEPARE deux lectures concurrentes.

  1. RECENSEMENT       -- les trois ids sont evaluables (surcharge / table) et posent le bit.
  2. RAYON 1016        -- `GetSpawnedUnitRange` etait un HARDCODE (`= 2`) ; il est desormais DERIVE
                          de `GetUnitMaxRange(unitId)`. L'etage FIGE la valeur mesuree a la
                          conversion (le cliquet `probe_313` compare des mirrors, pas des valeurs
                          ECRITES AU SITE : sans ce cran, une derivation qui glisse reste verte)
                          ET verifie que la source est bien le CATALOGUE (mutant sur `GC.unit`).
  3. BASCULE 1016      -- le bras `Steppable`, qu'aucun montage live ne produit : `includeCenter = 1`
                          fait entrer la tuile de la CIBLE dans le disque, et `onlyEmptyOrSteppable`
                          l'accepte quand la cible est `Steppable`. Plus la mesure du RAYON par la
                          GEOMETRIE (accepte a d=2, refuse a d=3) -- pas par lecture de constante.
  4. BASCULE 1180      -- le COURT-CIRCUIT `GetMinDistance < 2` (une cible au contact est valide
                          MEME quand aucune tuile n'est atteignable), la chargeabilite, et le fait
                          que la portee de mouvement vient de `constants.range` (refus a d=4).
  5. BASCULE 1197      -- ligne AVEC ennemi / SANS ennemi / avec un ALLIE (le filtre `Enemies`
                          mord) / avec un ennemi AU-DELA de `nrOfTiles` (la longueur de ligne mord).
  6. MUTANTS en DELTA  -- desarmee, chaque bascule doit S'EFFONDRER. Sans cet etage, les precedents
                          seraient verts sur un port qui ne consulte plus rien.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import gameconfig as GC                                                    # noqa: E402
import hexgeo                                                              # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import DYNAMIC_TARGET_RULE_UNPORTED  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

# ⚠ LES DEUX SYMBOLES NEUFS DE LA TRANCHE SONT IMPORTES *DANS* LEURS TESTS, PAS EN TETE, et c'est
# la seule raison : sur l'arbre TEMOIN (avant #287-r11-r1) ils n'existent pas, et un import de tete
# fait echouer la COLLECTE -- donc un rouge d'UNE ligne au lieu d'une ventilation. La vue rouge
# publiee dans la case-doc n'aurait alors montre aucun bras.

WAVE = int(ActiveAbilityType.SendInTheNextWave)          # 1016
FUSILLADE = int(ActiveAbilityType.HeroicFusillade)       # 1180
FREQUENCIES = int(ActiveAbilityType.ExcruciatingFrequencies)   # 1197
IDS = (WAVE, FUSILLADE, FREQUENCIES)

REFUS = int(TR.TargetMatchesDynamicRule)                 # 2

# `GetSpawnedUnitRange` MESURE au moment de la conversion du hardcode (2026-08-06, build
# `rnca9r7q6c`) : `astraSmnGuardsman.weapons = [Physical(sans portee), Las(Range 2)]` -> `max(1, 2)`.
# C'est la valeur que la constante `SITNW_SPAWNED_UNIT_RANGE` portait ; l'etage 2 la FIGE.
RAYON_SPAWN_MESURE = 2
# `HeroicFusillade.constants.range`, MESUREE de meme : la portee de MOUVEMENT de la charge.
RANGE_FUSILLADE_MESURE = 2
# `ExcruciatingFrequencies.constants.nrOfTiles`, MESUREE de meme : la longueur du rayon.
NR_OF_TILES_MESURE = 3


# ================================================================================================
# substrat -- board LIGNE, taille choisie par le cas
# ================================================================================================
#
# Un board 6x6 (celui de `probe_287r4r1`) ne permet PAS d'exercer les bras « rien de libre autour de
# la cible » : il faudrait 18 unites pour saturer un disque de rayon 2. Une LIGNE de N tuiles rend
# ces bras atteignables avec 2 ou 3 unites, et la geometrie y est mesurable
# (`hexgeo.distance((0,0),(k,0)) == k`, verifie par `test_la_ligne_du_substrat_a_la_geometrie_voulue`).

def _tid(col: int, row: int) -> int:
    return col * 100 + row + 1                 # ids de TUILE, disjoints des ids d'unite ci-dessous


def _board_ligne(n: int) -> Board:
    """Board de `n` tuiles alignees sur `row = 0`. Plat, marchable, sans mur."""
    tuiles = []
    for col in range(n):
        nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, 0) if r == 0 and 0 <= c < n]
        tuiles.append({"id": _tid(col, 0), "col": col, "row": 0, "elevation": 0,
                       "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat(unites: list, n: int):
    """`State` runner sur un board LIGNE de `n` tuiles. `unites` = (id, visualId, team, col, traits).

    Meme canal de traits que `probe_287r4r1.substrat` (`combatSnapshot.units[].traits`, #264) :
    l'ensemble effectif de `UnitExtensions$$HasTrait`, independant du catalogue."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": col, "row": 0}, "effects": []}
        for (uid, vid, team, col, _tr) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": [int(t) for t in tr]}
                      for (uid, _v, _t, _c, tr) in unites]}
    return load_state(dv, ob, snap, board=_board_ligne(n))


U_CASTER, U_CIBLE, U_A, U_B, U_C = 9001, 9002, 9003, 9004, 9005


def _regle(aid: int, st, target_id, caster_id=U_CASTER) -> int:
    return int(P._porteur(int(aid)).get_dynamic_invalid_target_reason(
        st, caster_id, target_id) or 0)


def test_la_ligne_du_substrat_a_la_geometrie_voulue():
    """Un substrat dont la geometrie n'est pas celle qu'on croit rend les bras VRAIS PAR VACUITE.
    On mesure donc la ligne AVANT de s'en servir : distances, et connexite du chemin."""
    for k in range(1, 6):
        assert hexgeo.distance((0, 0), (k, 0)) == k, "la ligne n'est pas isometrique en col"
    b = _board_ligne(4)
    assert sorted(b.coord(t) for t in b.by_id) == [(0, 0), (1, 0), (2, 0), (3, 0)]
    for k in range(3):
        voisins = {b.coord(t) for t in b.neighbours(_tid(k, 0))}
        assert (k + 1, 0) in voisins, "la ligne n'est pas connexe en %d" % k


# ================================================================================================
# 1. RECENSEMENT
# ================================================================================================

def test_les_trois_ids_sont_evaluables():
    attendu = {WAVE: "surcharge", FUSILLADE: "surcharge", FREQUENCIES: "table"}
    for aid, voie in attendu.items():
        assert P.evaluabilite(aid) == voie, (
            "%d n'est plus evaluable par `%s` (%s)" % (aid, voie, P.evaluabilite(aid)))


def test_les_trois_ids_posent_le_bit_au_masque():
    """Sans le bit, la cascade n'appelle JAMAIS la regle : le port serait permissif en silence."""
    for aid in IDS:
        opts = P.targeting_options_for(aid)
        assert opts is not None and opts.has(TR.TargetMatchesDynamicRule), (
            "%d ne pose plus TargetMatchesDynamicRule : la regle ne serait jamais consultee" % aid)


def test_1197_reste_hors_ABILITY_CLASSES_donc_sa_regle_vit_dans_la_TABLE():
    """1197 n'a pas de behaviour portee : sa regle vit dans `DYNAMIC_TARGET_RULE_UNPORTED`, pas dans
    une classe. Le jour ou elle entrerait au registre, ce test rougit -- et c'est voulu : il faudrait
    alors DEPLACER la regle en surcharge (et poser `TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE`)."""
    assert FREQUENCIES not in ABILITY_CLASSES
    assert ActiveAbilityType.ExcruciatingFrequencies in DYNAMIC_TARGET_RULE_UNPORTED


# ================================================================================================
# 2. RAYON 1016 -- le hardcode converti en derivation
# ================================================================================================

def test_1016_le_rayon_de_spawn_vaut_la_valeur_MESUREE_a_la_conversion():
    """FIGE l'ordinal ECRIT AU SITE, pas seulement la coherence du mirror. `SITNW_SPAWNED_UNIT_RANGE`
    valait `2` en dur ; la derivation doit rendre la MEME valeur, sinon la conversion a change le
    comportement de `GetSpawnTilesSelector` (face COMBAT) sans que personne l'ait mesure."""
    from engine.runner.abilities.astramilitarum import (
        send_in_the_next_wave_spawned_unit_range)
    assert send_in_the_next_wave_spawned_unit_range() == RAYON_SPAWN_MESURE


def test_1016_le_rayon_vient_du_CATALOGUE_et_pas_d_un_defaut():
    """MUTANT DE SOURCE : si la derivation lisait un defaut en dur, retirer l'unite du catalogue ne
    changerait rien. Le natif rend `0` (`GetUnitConfig(unitId) == null`), et le port aussi."""
    from engine.services.battle_query import get_unit_max_range
    assert get_unit_max_range("astraSmnGuardsman") == RAYON_SPAWN_MESURE
    assert get_unit_max_range("unite-qui-n-existe-pas") == 0, (
        "unite inconnue : le natif rend `return 0`, pas un defaut de 1")


def test_1016_une_arme_SANS_portee_vaut_1_pas_0(monkeypatch):
    """`r = w.Range.HasValue ? w.Range.Value : 1` -- le litteral `1` de la branche `!HasValue`. Une
    unite purement corps-a-corps rend donc `1`, et c'est ce qui la distingue d'une unite INCONNUE
    (qui rend `0`) et d'une unite SANS liste d'armes (`0` aussi, l'autre `return 0` du haut de corps).

    ⚠ LE CATALOGUE N'EXERCE PAS CE BRAS -- mesure : **aucune** unite n'a QUE des armes sans portee
    (elles portent toutes une arme a `Range`). Un test derive du catalogue partait donc en `skip`,
    c'est-a-dire en INVISIBILITE (#455). Le substrat est donc FABRIQUE ici, et l'assertion
    ci-dessous VERIFIE d'abord que le catalogue ne l'exerce pas : le jour ou il l'exercerait, ce
    test le dirait au lieu de continuer a se justifier."""
    depuis_catalogue = [vid for vid in (GC.all_unit_ids() or [])
                        if ((GC.unit(vid) or {}).get("weapons")
                            and all((w or {}).get("Range") is None
                                    for w in (GC.unit(vid) or {}).get("weapons")))]
    assert depuis_catalogue == [], (
        "le catalogue exerce desormais ce bras (%s) : le substrat fabrique n'est plus necessaire"
        % depuis_catalogue[:3])

    import engine.services.battle_query as _bqs
    faux = {"melee-pur": {"weapons": [{"hits": 1, "DamageProfile": "Physical"},
                                      {"hits": 2, "DamageProfile": "Power"}]},
            "sans-armes": {"weapons": []}}
    monkeypatch.setattr(_bqs.GC, "unit", lambda vid: faux.get(vid), raising=True)
    assert _bqs.get_unit_max_range("melee-pur") == 1, (
        "toutes les armes sans portee -> le defaut `1` de la branche !HasValue doit sortir")
    assert _bqs.get_unit_max_range("sans-armes") == 0, "`config.Weapons == null` -> `return 0`"
    assert _bqs.get_unit_max_range("inconnue") == 0, "`GetUnitConfig(unitId) == null` -> `return 0`"


# ================================================================================================
# 3. BASCULE 1016
# ================================================================================================
#
# `SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason` :
#     tiles = GetSurroundingTiles(targetTiles, GetSpawnedUnitRange(),
#                                 onlyEmptyOrSteppable: 1, onlyWalkable: 1,
#                                 onlyMovable: 0, includeCenter: 1);
#     return tiles.Count() < 1 ? 2 : 0;

def _sub_1016(n: int, occupees: list, cible_steppable: bool = False):
    """Board LIGNE de `n` tuiles. Caster team1 en (0,0), cible team2 en (1,0), plus un allie du
    caster sur chaque colonne de `occupees`."""
    tr = [UnitTrait.Steppable] if cible_steppable else []
    unites = [(U_CASTER, "astraYarrick", 1, 0, []),
              (U_CIBLE, "necroWarden", 2, 1, tr)]
    for i, col in enumerate(occupees):
        unites.append(((U_A, U_B, U_C)[i], "ultraTitus", 1, col, []))
    return _substrat(unites, n)


def test_1016_refuse_quand_le_disque_est_entierement_occupe():
    """Ligne de 2 tuiles : caster (0,0) + cible (1,0). Les DEUX tuiles du disque sont occupees par
    des unites non-`Steppable` -> `IsEmptyOrSteppable` faux partout -> 0 tuile -> REFUS."""
    assert _regle(WAVE, _sub_1016(2, []), U_CIBLE) == REFUS


def test_1016_ACCEPTE_quand_la_cible_elle_meme_est_Steppable():
    """LE BRAS QUE LE LIVE NE PRODUIT PAS, et la lecture qui le rend possible : `includeCenter = 1`
    laisse la tuile de la CIBLE dans le disque, et `IsEmptyOrSteppable` l'accepte des lors que son
    occupant porte le trait `Steppable` (0x1b). Meme geometrie que le test precedent : SEUL le trait
    change -- retirer le centre « parce qu'il est occupe » ferait rougir ici."""
    assert _regle(WAVE, _sub_1016(2, [], cible_steppable=True), U_CIBLE) == 0


def test_1016_accepte_des_qu_une_tuile_libre_existe_dans_le_disque():
    """Ligne de 3 : (2,0) reste libre -> 1 tuile -> 0."""
    assert _regle(WAVE, _sub_1016(3, []), U_CIBLE) == 0


def test_1016_le_RAYON_effectif_se_mesure_par_la_geometrie():
    """Le rayon n'est pas relu de la config : il est MESURE. La seule tuile libre est placee a
    distance `d` de la cible ; le verdict doit basculer entre `d = RAYON` et `d = RAYON + 1`.

    Ligne de 4 : cible (1,0), (2,0) occupee, (3,0) libre -> d = 2 -> ACCEPTE.
    Ligne de 5 : cible (1,0), (2,0) et (3,0) occupees, (4,0) libre -> d = 3 -> REFUS."""
    assert RAYON_SPAWN_MESURE == 2, "ce montage est calibre pour un rayon de 2"
    assert hexgeo.distance((1, 0), (3, 0)) == 2 and hexgeo.distance((1, 0), (4, 0)) == 3
    assert _regle(WAVE, _sub_1016(4, [2]), U_CIBLE) == 0        # libre a d = 2 -> dans le disque
    assert _regle(WAVE, _sub_1016(5, [2, 3]), U_CIBLE) == REFUS  # libre a d = 3 -> HORS du disque


# ================================================================================================
# 4. BASCULE 1180
# ================================================================================================
#
# `HeroicFusilladeAbility$$GetDynamicInvalidTargetReason` :
#     tiles = GetSurroundingTiles(targetTiles, 1, oEoS: 0, oW: 1, oM: 0, incC: 1);
#     list  = tiles.Where(t => IsInMovementRange(caster, t, 1, {overrideRange = range})).ToList();
#     if (GetMinDistance(targetTiles, casterTiles) < 2) return 0;
#     return list.Count == 0 ? 2 : 0;

def _sub_1180(n: int, col_cible: int, occupees: list = ()):
    unites = [(U_CASTER, "genesKelermorph", 1, 0, []),
              (U_CIBLE, "necroWarden", 2, col_cible, [])]
    for i, col in enumerate(occupees):
        unites.append(((U_A, U_B, U_C)[i], "necroImmortal", 2, col, []))
    return _substrat(unites, n)


def test_1180_court_circuite_sur_une_cible_AU_CONTACT():
    """`GetMinDistance < 2` -> `return 0` AVANT tout test de chargeabilite. Ligne de 2 : caster
    (0,0), cible (1,0). Le disque ring-1 de la cible ne contient que deux tuiles OCCUPEES, donc
    AUCUNE n'est dans le stop-set : sans le court-circuit, ce cas REFUSERAIT."""
    st = _sub_1180(2, 1)
    assert hexgeo.distance((0, 0), (1, 0)) == 1
    assert _regle(FUSILLADE, st, U_CIBLE) == 0


def test_1180_refuse_une_cible_LOIN_dont_aucun_voisin_n_est_atteignable():
    """Ligne de 4 : caster (0,0), cible (3,0) (d = 3), (1,0) et (2,0) occupees par des ENNEMIS. Le
    BFS est bloque des le premier pas (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`) -> stop-set vide
    -> aucune tuile du ring-1 de la cible n'y est -> REFUS."""
    st = _sub_1180(4, 3, occupees=[1, 2])
    assert _regle(FUSILLADE, st, U_CIBLE) == REFUS


def test_1180_accepte_une_cible_LOIN_dont_un_voisin_est_atteignable():
    """Ligne de 4 : caster (0,0), cible (3,0) (d = 3), rien entre. (2,0) est a 2 pas -> dans le
    stop-set -- ET adjacente a la cible -> ACCEPTE. Meme distance que le test precedent : SEUL le
    blocage change."""
    st = _sub_1180(4, 3)
    assert _regle(FUSILLADE, st, U_CIBLE) == 0


def test_1180_la_PORTEE_DE_MOUVEMENT_est_celle_de_la_config():
    """Le `range` n'est pas « tout le plateau » (le volet STATIQUE, lui, l'est : `RANGE_WHOLE_BOARD`)
    -- c'est `GetNumberConstant(0x16)`. Ligne de 6, cible en (4,0) : son ring-1 le plus proche est
    (3,0), a 3 pas du caster, donc HORS du stop-set d'une portee 2 -> REFUS. Le meme montage avec
    une cible en (3,0) accepte (test precedent) : la bascule est bien a `range`."""
    assert RANGE_FUSILLADE_MESURE == 2, "ce montage est calibre pour une portee de 2"
    st = _sub_1180(6, 4)
    assert hexgeo.distance((0, 0), (3, 0)) == 3
    assert _regle(FUSILLADE, st, U_CIBLE) == REFUS


# ================================================================================================
# 5. BASCULE 1197 -- la CIBLE est une TUILE
# ================================================================================================
#
# `ExcruciatingFrequenciesAbility$$GetDynamicInvalidTargetReason` :
#     return GetAttackTargets().Count(entities{caster, target, targetTiles}) > 0 ? 0 : 2;
#     GetAttackTargets = Enemies(Caster@0x48, Units(SortReverse(TilesBehindInLine(
#                                CasterTile@0x50, TargetTile@0x78, {1,1},
#                                Direct(GetNumberConstant(0x17 nrOfTiles))))))

# ⚠ LA LIGNE CUBE N'EST PAS LA LIGNE `row` CONSTANTE, et le supposer a d'abord fait ROUGIR ce
# fichier : `cube(2,0) = (2,-1,-1)` alors que `cube(1,0) + (cube(1,0) - cube(0,0)) = (2,0,-2)`, qui
# est l'offset `(2,-1)`. Un board LIGNE (`row = 0`) tronque donc le rayon a UNE tuile -- et le refus
# se serait lu comme « le port ne trouve pas l'ennemi ». La geometrie est desormais DERIVEE
# (`_ligne_reelle`), jamais posee : on place les unites sur les tuiles que la marche native rend.

COLS_R = ROWS_R = 8
CASTER_R = (3, 1)          # `(3,1) -> (3,2)` rend une ligne VERTICALE exacte sur ce board
CIBLE_R = (3, 2)


def _board_rect(cols: int, rows: int) -> Board:
    tuiles = []
    for col in range(cols):
        for row in range(rows):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < cols and 0 <= r < rows]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat_rect(unites: list):
    """`State` sur `_board_rect(COLS_R, ROWS_R)`. `unites` = (id, visualId, team, (col,row))."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": p[0], "row": p[1]}, "effects": []}
        for (uid, vid, team, p) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _p) in unites]}
    return load_state(dv, ob, snap, board=_board_rect(COLS_R, ROWS_R))


def _ligne_reelle(n: int) -> list:
    """Les `n` premieres tuiles de la marche `GetTilesBehind(CASTER_R -> CIBLE_R)` sur le board du
    substrat -- MEME foyer (`battle_query.get_tiles_behind`) et MEMES settings (`{1, 1}`) que le
    port. On DERIVE la geometrie au lieu de la supposer ; ce que les tests d'apres discriminent,
    c'est le FILTRE d'equipe et la BORNE de longueur, pas la marche."""
    import engine.battle_query as bq
    ex = (lambda p: 0 <= p[0] < COLS_R and 0 <= p[1] < ROWS_R)
    return bq.get_tiles_behind(CASTER_R, CIBLE_R, max_count=n, check_walkable=True,
                               update_reference=True, walkable_at=lambda p: True,
                               elevation_at=lambda p: 0, tile_exists=ex)


TUILE_VISEE = _tid(CIBLE_R[0], CIBLE_R[1])


def _sub_1197(sur_ligne: list):
    """Caster team1 en `CASTER_R` ; `sur_ligne` = [(indice dans la ligne longue, team)]."""
    L = _ligne_reelle(NR_OF_TILES_MESURE + 2)
    unites = [(U_CASTER, "emperNoiseMarine", 1, CASTER_R)]
    for i, (k, team) in enumerate(sur_ligne):
        unites.append(((U_CIBLE, U_A, U_B, U_C)[i],
                       "necroWarden" if team == 2 else "ultraTitus", team, L[k]))
    return _substrat_rect(unites)


def test_la_ligne_du_substrat_1197_est_assez_longue():
    """Sans ce cran, un board trop petit rendrait une ligne d'une seule tuile et TOUS les cas
    d'apres seraient vrais par vacuite -- c'est exactement ce qui est arrive au premier jet."""
    L = _ligne_reelle(NR_OF_TILES_MESURE + 2)
    assert len(L) >= NR_OF_TILES_MESURE + 1, (
        "ligne trop courte (%d) : la borne `nrOfTiles` ne peut pas etre exercee" % len(L))
    assert L[0] == CIBLE_R, "la 1re tuile de la marche DOIT etre la tuile visee"
    assert len(set(L)) == len(L), "la marche repasse sur une tuile : geometrie inutilisable"


def test_1197_accepte_quand_la_ligne_TOUCHE_un_ennemi():
    """Ennemi sur la 2e tuile du rayon -> `Count > 0` -> 0."""
    assert _regle(FREQUENCIES, _sub_1197([(1, 2)]), TUILE_VISEE) == 0


def test_1197_refuse_quand_la_ligne_ne_touche_PERSONNE():
    """Meme geometrie, aucune unite sur la ligne -> `Count == 0` -> REFUS."""
    assert _regle(FREQUENCIES, _sub_1197([]), TUILE_VISEE) == REFUS


def test_1197_refuse_quand_la_ligne_ne_touche_qu_un_ALLIE():
    """LE FILTRE `Enemies` MORD, et c'est le bras qui separe `Units(...)` de `Enemies(Units(...))` :
    MEME position que le cas ACCEPTE, l'unite passe simplement dans l'equipe du caster."""
    assert _regle(FREQUENCIES, _sub_1197([(1, 1)]), TUILE_VISEE) == REFUS


def test_1197_refuse_un_ennemi_AU_DELA_de_nrOfTiles():
    """LA BORNE `Direct(GetNumberConstant(0x17 nrOfTiles))` MORD. `nrOfTiles = 3` -> le rayon
    s'arrete a l'indice 2 ; un ennemi a l'indice 3 est ALIGNE mais hors du rayon -> REFUS. La
    contre-epreuve (meme board, meme ennemi UN CRAN plus pres) doit ACCEPTER -- sans elle, le refus
    pourrait venir du board et non de la borne."""
    assert NR_OF_TILES_MESURE == 3, "ce montage est calibre pour une ligne de 3"
    assert _regle(FREQUENCIES, _sub_1197([(NR_OF_TILES_MESURE, 2)]), TUILE_VISEE) == REFUS
    assert _regle(FREQUENCIES, _sub_1197([(NR_OF_TILES_MESURE - 1, 2)]), TUILE_VISEE) == 0


# ================================================================================================
# 6. MUTANTS en DELTA -- desarmee, chaque bascule s'effondre
# ================================================================================================

def _cas_mutants():
    """(aid, libelle, substrat_qui_REFUSE, target_id) -- un par regle."""
    return [
        (WAVE, "disque sature", _sub_1016(2, []), U_CIBLE),
        (FUSILLADE, "cible loin et bloquee", _sub_1180(4, 3, occupees=[1, 2]), U_CIBLE),
        (FREQUENCIES, "ligne vide", _sub_1197([]), TUILE_VISEE),
    ]


def test_desarmer_chaque_regle_fait_TOMBER_son_refus():
    """Le critere est un DELTA, pas `apres == 0` : une mutation que le substrat n'exerce pas
    rendrait `0` des deux cotes et se compterait comme un vert (faute mesuree sur la tranche
    parente, cf. `probe_287r4r1.mesurer_mutants`). On exige donc `avant == REFUS` ET `apres == 0`."""
    for aid, libelle, st, tid in _cas_mutants():
        avant = _regle(aid, st, tid)
        with P.desarme(aid):
            apres = _regle(aid, st, tid)
        assert avant == REFUS, "%d (%s) ne refuse plus : le substrat n'exerce pas la regle" % (
            aid, libelle)
        assert apres == 0, "%d (%s) refuse ENCORE une fois desarmee : le refus vient d'ailleurs" % (
            aid, libelle)
