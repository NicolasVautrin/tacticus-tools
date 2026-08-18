"""#977-r8 -- CLIQUET : le domaine `tile_aim` passe par le `RemoveAll(b__1)` de LIGNE DE VUE.

#977-r7 a cable la ZONE (`TargetingQuery$$GetTilesInRange` + son retrait de walkability). Restait
le SUR-ENSEMBLE : l'enumeration ne passait par aucun des trois `RemoveAll` que
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` applique ENSUITE. Un
sur-ensemble est une degradation PERMISSIVE -- ni erreur ni crash, donc invisible en self-play, et
exactement le trou qu'un entrainement irait exploiter.

CE QUE LA RE A RECTIFIE, ET C'ETAIT LA PREMISSE DE LA FICHE
------------------------------------------------------------
La fiche annoncait TROIS `RemoveAll` a porter, `b__0` decrit comme « camp / portee / regles
statiques ». Relu sur `t6dpr4k06g`, `b__0` commence par :

    if (!IdunBattle.Entities.EntityExtensions$$IsUnit(target)) return false;   // = GARDE la cible

et une TUILE n'est pas une unite -- `$$IsTile` est une fonction DISTINCTE, avec un test distinct
(`IsUnit` compare un discriminant a `1` ; `IsTile` passe par un `Is<T>` generique sur un autre
token). Les trois tests qui suivent -- `UnitExtensions$$IsAlive`, `TileExtensions$$HasSteppableUnit`,
`TileExtensions$$HasPowerup` -- ne visent que le domaine UNITE (`GetUnitsInRange`). **`b__0` est
donc INERTE sur le domaine tuile** : il n'y a rien a y porter, et ce n'est pas une degradation.

Reste DEUX predicats : `b__1` (LIGNE DE VUE, gate par AUCUN bit, il tourne TOUJOURS) -- PORTE par
cette tranche -- et `b__2` (regle DYNAMIQUE, gate par `rules & TargetMatchesDynamicRule`), non
porte offline, residu `#977-r10`.

REGIME, re-derive du registre et du gameconfig (etage 0, assertionne NON VIDE) : **15** abilities
sont reellement routees `tile_aim`. **9** ne portent AUCUN des deux bits `AllowObscuredTargetBy*`
-> la ligne de vue y filtre pleinement. Les **6** autres les portent TOUTES LES DEUX ->
`obscuring_type_for` rend `OBSCURING_TYPE_NONE` et l'etage est inerte : c'est le TEMOIN NEGATIF, et
il vient du natif, pas d'un choix de montage.

CONTRE-EPREUVES : l'etage 1 exige un no-op STRICT sur plateau plat (le fix ne doit pas retirer ce
que le natif garde) ; l'etage 2 exige que le mur RETIRE, et il verifie d'abord que le regime SANS
mur est non degenere ; l'etage 4 verifie que le temoin negatif est bien inerte POUR LA RAISON LUE.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import hexgeo                                                                # noqa: E402
import engine.ai.state_bridge as SB                                          # noqa: E402
from engine.entities.pathfinding.board import Board                          # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                  # noqa: E402
from engine.runner.abilities.targeting import targeting_options_for          # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,     # noqa: E402
                                      UnitComponent)
from engine.runner.state import State                                        # noqa: E402
from engine.services import ability_range as AR                              # noqa: E402
from engine.services import targeting_query as TQ                            # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/ai/state_bridge.py",
                "scripts/python/engine/services/targeting_query.py"),
    "build": True,
    "toujours": False,
    "raison": "Le cablage vit dans `state_bridge._aim_tiles_in_range` ; l'etage qu'il appelle "
              "(`target_is_obscured` et ses gardes) vit dans `targeting_query`. `build: True` : "
              "le regime (15 routees, 9 sans bit) est re-derive du registre COMBAT et du "
              "gameconfig du build, et l'etage 0 rougit si l'un des deux bouge.",
}

COLS, ROWS = 9, 9
CASTER_POS = (4, 4)
CASTER_VID = "ultraCalgar"                 # gameconfig : Movement = 3 (temoin non degenere)

#: `1092 DarkTalonStrike` -- routee `tile_aim`, `reach = 2`, AUCUN bit `AllowObscuredTargetBy*`
#: et PAS de `TargetMatchesDynamicRule` : la ligne de vue y est le SEUL filtre ajoute.
CIBLE = 1092
#: `1194 NovaShield` -- routee `tile_aim` et porteuse des DEUX bits : l'etage doit y etre INERTE.
TEMOIN_INERTE = 1194


def _board(elev_by_pos=None, murs=()) -> Board:
    idof, tiles, tid = {}, [], 1
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({
            "id": i, "col": c, "row": r,
            "elevation": (elev_by_pos or {}).get((c, r), 0),
            "tileDefId": "Grass", "isTemporary": False,
            "isWall": (c, r) in murs, "walkable": True, "isInFog": False,
            "occupantUnitId": None,
            "neighbours": [idof[n] for n in hexgeo.neighbors(c, r) if n in idof],
        })
    return Board(tiles, adjacency="evenq")


def _state(board, allie_en=None) -> State:
    st = State()
    st.board = board
    e = st.add_entity(1)
    e.add_component(UnitComponent(visual_id=CASTER_VID, alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(*CASTER_POS))
    if allie_en is not None:
        a = st.add_entity(3)
        a.add_component(UnitComponent(visual_id="ultraIntercessor", alive=True))
        a.add_component(OwnerComponent(team=1, player=1))       # MEME equipe que le caster
        a.add_component(PositionComponent(*allie_en))
    return st


def _tuiles(state, ability_id, caster_tiles, caster_team=1) -> set:
    out = SB._aim_tiles_in_range(state, ability_id, CASTER_VID, caster_tiles,
                                 caster_team=caster_team)
    return {(t["tile"]["col"], t["tile"]["row"]) for t in out}


def _routees() -> dict:
    """`{ability_id: (reach, bit25, bit26, bit_dyn)}` pour les abilities REELLEMENT routees
    `tile_aim`. Re-derive du registre COMBAT, jamais cite."""
    out = {}
    for aid in sorted(ABILITY_CLASSES):
        nom, cfg = SB._resolve_ability(aid)
        if SB._ability_kind(aid, nom, cfg) != "tile_aim":
            continue
        o = targeting_options_for(aid)
        r = int(o.rules)
        out[aid] = (AR.tiles_in_range_reach(aid, None),
                    bool(r & TQ.ALLOW_OBSCURED_TARGET_BY_ELEVATION),
                    bool(r & TQ.ALLOW_OBSCURED_TARGET_BY_WALLS),
                    bool(r & 2))
    return out


ROUTEES = _routees()


# --------------------------------------------------------------------------------------------
# ETAGE 0 -- le regime EXISTE et il est ventile comme ce fichier le croit.
# --------------------------------------------------------------------------------------------
def test_etage0_le_domaine_tile_aim_est_non_vide():
    assert ROUTEES, ("aucune ability routee `tile_aim` : ce fichier n'exercerait RIEN et "
                     "passerait pour vert")
    assert CIBLE in ROUTEES, "`%d` n'est plus routee `tile_aim` : le temoin est PERIME" % CIBLE
    assert TEMOIN_INERTE in ROUTEES, "le temoin negatif est PERIME"


def test_etage0bis_les_deux_temoins_ont_le_profil_de_bits_annonce():
    reach, e25, w26, dyn = ROUTEES[CIBLE]
    assert (e25, w26, dyn) == (False, False, False), (
        "`%d` porte desormais un bit qui neutralise ou complique l'etage 3 : (elev, walls, dyn) "
        "= (%s, %s, %s)" % (CIBLE, e25, w26, dyn))
    assert reach == 2, "portee de `%d` changee (%s) : la geometrie du montage est perimee" % (
        CIBLE, reach)
    _r, e25b, w26b, _d = ROUTEES[TEMOIN_INERTE]
    assert (e25b, w26b) == (True, True), (
        "le temoin negatif ne porte plus les DEUX bits `AllowObscuredTargetBy*` : l'etage 4 ne "
        "mesurerait plus l'inertie qu'il annonce")


def test_etage0ter_la_ventilation_des_bits_est_non_degeneree():
    sans = [a for a, (_r, e, w, _d) in ROUTEES.items() if not e and not w]
    avec = [a for a, (_r, e, w, _d) in ROUTEES.items() if e and w]
    assert sans, "aucune routee sans bit `AllowObscured*` : la ligne de vue serait inerte partout"
    assert avec, "aucune routee AVEC les deux bits : le temoin negatif serait introuvable"
    assert len(sans) + len(avec) == len(ROUTEES), (
        "une routee porte UN SEUL des deux bits (%s) : la ventilation binaire de ce fichier ne "
        "la couvre pas, relire avant de conclure"
        % [a for a, (_r, e, w, _d) in ROUTEES.items() if e != w])
    # `#977-r10` : la part NON couverte doit exister, sinon le residu ouvert serait vide.
    assert [a for a, (_r, _e, _w, d) in ROUTEES.items() if d], (
        "plus aucune routee ne porte `TargetMatchesDynamicRule` : le residu #977-r10 est SANS "
        "OBJET et doit etre ferme, pas laisse ouvert")


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- NO-OP STRICT sur plateau plat sans mur. Le fix ne retire pas ce que le natif garde.
# --------------------------------------------------------------------------------------------
def test_etage1_plateau_plat_sans_mur_est_un_no_op():
    """Sur un plateau PLAT sans mur, `GetTilesObscuringTerrain` ne peut rendre AUCUNE obstruction,
    donc l'etage 3 est un no-op strict et la zone reste celle de #977-r7.

    ⚠ La tuile-caster (`d == 0`) n'y est PAS, et c'est le NATIF qui le dit : la zone est celle de
    `GetTilesInRange` (verifiee ci-dessous par `tiles_in_range_zone_contains`), et les DEUX
    `AddRange(casterTiles)` de `GetPossibleTargetsForOptions` sont gates par des bits que `1092`
    ne porte pas. L'attendu est donc la COURONNE, pas le disque -- caracterisation re-derivee de
    l'etage amont, jamais recopiee de l'implementation qu'on juge."""
    st = _state(_board())
    tuiles = _tuiles(st, CIBLE, [CASTER_POS])
    attendu = {(c, r) for c in range(COLS) for r in range(ROWS)
               if AR.tiles_in_range_zone_contains(
                   CIBLE, CASTER_VID, hexgeo.distance(CASTER_POS, (c, r)))}
    assert tuiles == attendu, (
        "sur un plateau PLAT sans mur, `GetTilesObscuringTerrain` ne peut rien rendre : "
        "en trop %s ; manquantes %s" % (sorted(tuiles - attendu), sorted(attendu - tuiles)))
    assert len(tuiles) > 10, "montage degenere (%d tuiles)" % len(tuiles)
    assert CASTER_POS not in tuiles, (
        "la tuile-caster est emise alors que `1092` ne porte aucun des deux bits d'"
        "`AddRange(casterTiles)` -- relire l'etage amont avant de conclure")


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- UN MUR RETIRE, et il retire EXACTEMENT ce que l'etage porte designe.
# --------------------------------------------------------------------------------------------
def test_etage2_un_mur_retire_des_tuiles_du_domaine():
    mur = (5, 4)                                   # colle au caster, sur la ligne vers l'est
    sans = _tuiles(_state(_board()), CIBLE, [CASTER_POS])
    avec = _tuiles(_state(_board(murs=(mur,))), CIBLE, [CASTER_POS])
    assert avec < sans, (
        "le mur ne retire RIEN : le `RemoveAll(b__1)` n'est pas cable, ou le montage ne le "
        "declenche pas (sans=%d avec=%d)" % (len(sans), len(avec)))
    # l'ensemble retire est EXACTEMENT celui que le foyer designe -- pas un filtre reinvente.
    board = _board(murs=(mur,))
    attendu = {p for p in sans
               if TQ.target_is_obscured(board, [CASTER_POS], p, int(targeting_options_for(CIBLE).rules),
                                        caster_has_indirect_fire=AR._has_indirect_fire(CASTER_VID))}
    assert attendu, "contre-epreuve MUETTE : le foyer lui-meme ne designe aucune tuile obscurcie"
    assert sans - avec == attendu, (
        "le retrait ne coincide pas avec `target_is_obscured` -- en trop %s ; manquantes %s"
        % (sorted((sans - avec) - attendu), sorted(attendu - (sans - avec))))


def test_etage2bis_une_elevation_bloquante_retire_aussi():
    """Le volet ELEVATION est independant du volet MUR (`obscuring_type_for` les compose
    separement). Une crete a `+5` entre le caster et la cible bloque."""
    sans = _tuiles(_state(_board()), CIBLE, [CASTER_POS])
    avec = _tuiles(_state(_board(elev_by_pos={(5, 4): 5})), CIBLE, [CASTER_POS])
    assert avec < sans, "l'elevation ne retire rien (sans=%d avec=%d)" % (len(sans), len(avec))


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- la garde « ami » : une tuile PORTANT une unite alliee n'est jamais retiree.
# --------------------------------------------------------------------------------------------
def test_etage3_une_tuile_occupee_par_un_allie_survit_au_mur():
    """`IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt` : la premiere garde de
    `GetTilesObscuringTerrain` rend un ensemble VIDE, donc la tuile est GARDEE."""
    mur = (5, 4)
    board = _board(murs=(mur,))
    perdues = _tuiles(_state(board), CIBLE, [CASTER_POS])
    perdues = {p for p in _tuiles(_state(_board()), CIBLE, [CASTER_POS])} - perdues
    assert perdues, "aucune tuile perdue : l'etage 3 n'aurait rien a sauver"
    cible = sorted(perdues)[0]
    avec_allie = _tuiles(_state(board, allie_en=cible), CIBLE, [CASTER_POS])
    assert cible in avec_allie, (
        "la tuile %s porte une unite de l'equipe du caster : `IsFriendOrHasFriendlyUnitOnIt` "
        "doit la faire GARDER, le natif rendant un ensemble d'obstructions vide" % (cible,))


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- TEMOIN NEGATIF : les DEUX bits `AllowObscuredTargetBy*` rendent l'etage INERTE,
# et pour la raison LUE (`obscuring_type_for` -> `OBSCURING_TYPE_NONE`).
# --------------------------------------------------------------------------------------------
def test_etage4_les_deux_bits_rendent_l_etage_inerte():
    rules = int(targeting_options_for(TEMOIN_INERTE).rules)
    assert TQ.obscuring_type_for(rules) == TQ.OBSCURING_TYPE_NONE, (
        "la RAISON de l'inertie a change : ce test ne mesurerait plus ce qu'il annonce")
    sans = _tuiles(_state(_board()), TEMOIN_INERTE, [CASTER_POS])
    avec = _tuiles(_state(_board(murs=((5, 4),), elev_by_pos={(3, 4): 5})),
                   TEMOIN_INERTE, [CASTER_POS])
    assert sans and sans == avec, (
        "l'ability porte les DEUX bits : ni mur ni elevation ne doivent retirer quoi que ce soit "
        "(sans=%d avec=%d)" % (len(sans), len(avec)))


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- CONSEQUENCE OBSERVABLE de `b__0` INERTE : aucun filtre d'UNITE n'est applique sur ce
# domaine. Une tuile occupee par un ENNEMI reste emise -- le natif ne la retire pas non plus,
# puisque son `IsUnit(target)` est faux sur une tuile.
# --------------------------------------------------------------------------------------------
def test_etage5_une_tuile_occupee_par_un_ennemi_reste_emise():
    st = _state(_board())
    f = st.add_entity(2)
    f.add_component(UnitComponent(visual_id="orkBoy", alive=True))
    f.add_component(OwnerComponent(team=2, player=2))
    f.add_component(PositionComponent(5, 4))
    tuiles = _tuiles(st, CIBLE, [CASTER_POS])
    assert (5, 4) in tuiles, (
        "une tuile occupee par un ennemi a ete retiree : le port a ajoute un filtre d'UNITE que "
        "`b__0` n'applique PAS sur ce domaine (son `IsUnit(target)` est faux sur une tuile)")
