"""#287-r11-r2-r1 -- GARDE du mirror d'`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttack
RangeForSummon` (`IBattleQuery` slot 196), le troisieme filtre de
`MV71SniperDroneSquadAttackAbility$$PickTile` -- et donc, depuis #287-r11-r2, du gate de ciblage de
`1076 MV71SniperDroneSquadAttack`.

Le probe LIVE (`probe_287r11r2r1_los_summon_live.py`) prouve les DEUX etages neufs sur un plateau
reel (`C3_47`) : LIGNE DE VUE -- disque r=4 dont les 10 tuiles libres sont masquees par un mur de
roche, natif `0x1 ValidRequest`, port `0x1`, temoin (collapse d'avant) `0x0` ; et CLAMP MELEE
DEPUIS LA TUILE CANDIDATE -- meme geometrie, seule l'EQUIPE de l'occupant de (2,4) change, natif
`0x0 -> 0x1`. Ce fichier-ci garde ce que le live n'atteint pas, et les lectures NON TRIVIALES :

  1. SLOTS        -- les trois slots d'interface LUS dans `metadata/interface_slots.tsv`, et
                     surtout le fait que `<slot 0x10>` est celui d'`IMovementQuery`, PAS
                     d'`IBattleQuery` : c'est `BattleQuery$$GetDistance` qui l'etablit (slot 9 du
                     MEME champ `this+0x10`).
  2. LIGNE DE VUE -- bascule sous une SEULE variable : l'elevation du rocher. Distance, occupation
                     et compte du disque INVARIANTS entre les deux bras.
  3. PAS LA CASCADE -- ce call-site N'EST PAS gate par `TargetingConfiguration.EnableObscuring
                     Terrain` : il appelle `IMovementQuery` DIRECTEMENT. Passer par
                     `services.targeting_query` rendrait faussement << non obscurci >>.
  4. CLAMP MELEE  -- `ShouldApplyRangedInMelee` DEPUIS LA TUILE CANDIDATE (pas depuis le caster).
  5. ELEVATION    -- `CanMeleeAttackOverElevationDifference` est IMPLIQUE par `IsAdjacentTo` sur
                     une cible A UN PIED, et ne discrimine que sur une cible MULTI-PIEDS. C'est
                     une lecture, pas une supposition : les deux predicats ne lisent pas les memes
                     tuiles (TOUS les pieds vs la MAIN TILE seule).
  6. TARGETABLE   -- le premier bras du corps natif.
  7. REPLI        -- `UnobscuredTilesSelector$$IsObscured` : liste source VIDE -> OBSCURCI.
  8. MUTANTS      -- desarme, la bascule doit S'EFFONDRER (la vue rouge, offline).

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE CORPS PORTE -- l'objet meme de ce fichier.
        "scripts/python/engine/runner/abilities/loki/mv71.py",
        # LA GEOMETRIE de la ligne de vue et les litteraux `(6, 2)` nommes.
        "scripts/python/engine/services/movement_query.py",
        "scripts/python/engine/services/targeting_query.py",
        # L'ADJACENCE (`MovementUtil$$AreTilesAdjacent`, porte d'elevation comprise) et le substrat.
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        "scripts/python/engine/runner/snapshot.py",
        # L'AIGUILLAGE et le registre, par lesquels la cascade atteint la regle de 1076.
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/services/custom_normal_attack.py",
        # LE RECENSEMENT et le desarmement dont ce fichier se sert comme mutant.
        "scripts/python/probe_287r4r1_dynamic_target_rules.py",
        # ⚠ LARGE ET ASSUME : importer `handler` tire tout le paquet `abilities`. Les DEUX formes
        # sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py` ne voit PAS
        # `scripts/python/gameconfig.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
        # ⚠ HORS de `scripts/python/` -- donc AUCUN des deux globs ne le couvre (lecon de #806).
        "frida/hooks/data/ability-names.ts",
        # L'etage 1 lit la table des slots, l'etage 9 celle des ENUMS (l'ordinal de
        # `UnitFlag.IngoreRangedInMelee`, #287-r11-r2-r1-r2) : les deux vivent hors des globs.
        "data/symbols/CURRENT",
        "data/symbols/*/metadata/interface_slots.tsv", "data/symbols/*/frida/enums.tsv",
    ),
    # Les slots d'interface, le rayon du drone et `maxSummons` sont LUS dans les artefacts du BUILD
    # (`data/symbols/**`) : un re-dump peut les faire bouger, et l'etage 1 doit alors rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Le troisieme filtre de `PickTile` est un mirror d'un corps natif ; il ne peut changer de "
        "verdict que si le corps porte, la geometrie de ligne de vue, l'adjacence, l'aiguillage, "
        "le substrat de montage ou les artefacts du build changent."),
}

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import hexgeo                                                              # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.services.targeting_query import (                              # noqa: E402
    BLOCKING_ELEVATION_DIFFERENCE, OBSCURING_TYPE_ALL)

# ⚠ LES SYMBOLES NEUFS DE LA TRANCHE SONT IMPORTES *DANS* LEURS TESTS, PAS EN TETE : sur l'arbre
# TEMOIN (avant #287-r11-r2-r1) ils n'existent pas, et un import de tete ferait echouer la
# COLLECTE -- donc un rouge d'UNE ligne au lieu d'une ventilation.

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)   # 1076
PORTEUR = "tauMarksman"
DRONE = "tauSmnDroneSniper"
REFUS = int(TR.ValidRequest)              # le litteral `1` du decompile (#287-r11-r2)
MAX_SUMMONS_MESURE = 3

BUILD = (PY.parents[1] / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
SLOTS_TSV = PY.parents[1] / "data" / "symbols" / BUILD / "metadata" / "interface_slots.tsv"


# ================================================================================================
# substrat -- board LIGNE, avec un ROCHER dont l'elevation est le SEUL levier
# ================================================================================================
#
#   col      0        1         2        3        4
#          CIBLE   ROCHER    CASTER   libre    libre
#   elev     0      <var>       0        0        0
#   walk    oui      NON       oui      oui      oui
#
# Le rocher est NON MARCHABLE (il n'est donc jamais candidat) ; son elevation decide seule si les
# tuiles libres (3,0) et (4,0) sont MASQUEES depuis la cible. `DetermineBlockingTiles` compare
# `elev(intermediaire) - elev(<reference>) >= 2` : rocher a 3 -> masque, rocher a 1 -> clair.

def _tid(col: int, row: int) -> int:
    return col * 100 + row + 1                 # ids de TUILE, disjoints des ids d'unite


def _board(elev_rocher: int, n: int = 5) -> Board:
    tuiles = []
    for col in range(n):
        nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, 0) if r == 0 and 0 <= c < n]
        rocher = (col == 1)
        tuiles.append({"id": _tid(col, 0), "col": col, "row": 0,
                       "elevation": elev_rocher if rocher else 0,
                       "walkable": not rocher, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


U_CASTER, U_CIBLE, U_ENNEMI = 9001, 9002, 9003

# CASTER en (2,0) : d = 2 de la cible, donc PAS adjacent -> `IsMeleeAttack` ne court-circuite pas.
BASE = [(U_CASTER, PORTEUR, 1, 2), (U_CIBLE, "necroWarden", 2, 0)]
# + un ennemi en (4,0), ADJACENT a la seule tuile libre restante (3,0) : c'est le levier du clamp.
AVEC_ENNEMI = BASE + [(U_ENNEMI, "necroWarden", 2, 4)]


def _substrat(unites, elev_rocher: int):
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": col, "row": 0}, "effects": []}
        for (uid, vid, team, col) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _c) in unites]}
    return load_state(dv, ob, snap, board=_board(elev_rocher))


def _regle(unites, elev_rocher: int, caster_id=U_CASTER, target_id=U_CIBLE) -> int:
    """La regle telle que la cascade la consulte par la VOIE DU REGISTRE (`turnflow`)."""
    st = _substrat(unites, elev_rocher)
    return int(P._porteur(MV71).get_dynamic_invalid_target_reason(st, caster_id, target_id) or 0)


# ================================================================================================
# 0. LE SUBSTRAT DIT-IL CE QU'ON CROIT ?
# ================================================================================================

def test_le_substrat_a_la_geometrie_voulue():
    """Un substrat dont la geometrie n'est pas celle qu'on croit rend les bras VRAIS PAR VACUITE."""
    from engine.runner.abilities.loki.mv71 import _drone_attack_range     # noqa: PLC0415
    for k in range(1, 5):
        assert hexgeo.distance((0, 0), (k, 0)) == k, "la ligne n'est pas isometrique en col"
    b = _board(3)
    assert not b.walkable(_tid(1, 0)), "le rocher doit etre NON marchable"
    assert [b.walkable(_tid(c, 0)) for c in range(5)] == [True, False, True, True, True]
    # les deux tuiles libres du montage sont DANS le disque du drone
    rng = _drone_attack_range(DRONE)
    assert rng >= 4, rng
    assert all(1 <= hexgeo.distance((0, 0), (k, 0)) <= rng for k in (2, 3, 4))


# ================================================================================================
# 1. LES SLOTS -- lus dans la table du build, jamais devines
# ================================================================================================

def _slots():
    lignes = SLOTS_TSV.read_text(encoding="utf-8").splitlines()
    out = {}
    for ln in lignes:
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split("\t")
        if len(p) >= 4:
            out[(p[0], int(p[1]))] = (p[2], int(p[3]))
    return out


def test_les_slots_d_interface_sont_ceux_que_la_RE_a_lus():
    """La lecon de #287-r11-r1 : un slot se LIT dans `metadata/interface_slots.tsv`.

    ⚠ ET LE `<slot 0x10>` DU DECOMPILE N'EST PAS CELUI D'`IBattleQuery` : le service interroge est
    `this+0x10`, et `BattleQuery$$GetDistance(tileA, tileB)` appelle le slot `9` du MEME champ, que
    la table nomme `IMovementQuery 9 GetDistance/2`. `IBattleQuery 16` est `GetChainedUnits/3` --
    lire le slot sur la mauvaise interface aurait donne une reponse fausse sans le dire."""
    s = _slots()
    assert s[("IBattleQuery", 196)] == ("IsTargetInAttackRangeForSummon", 4)
    assert s[("IMovementQuery", 9)] == ("GetDistance", 2)
    assert s[("IMovementQuery", 16)] == ("GetTilesObscuringTerrain", 4)
    # la surcharge LISTE est le slot 15 (celle qu'appelle `TargetingQuery` avec `casterTiles`)
    assert s[("IMovementQuery", 15)] == ("GetTilesObscuringTerrain", 4)
    # et la confusion qu'on a evitee : le slot 16 d'`IBattleQuery` designe autre chose
    assert s[("IBattleQuery", 16)] != ("GetTilesObscuringTerrain", 4)


def test_les_litteraux_du_call_site_passent_par_leurs_NOMS():
    """`(6, 2)` = `ObscuringType.All` et `blockingElevationDifference`. Le site EXECUTABLE ne doit
    pas porter les entiers nus -- c'est la regle << un ENTIER qui DESIGNE passe par un ENUM >>.

    Le critere est SYNTAXIQUE (`ast`), pas textuel : le decompile CITE dans les docstrings porte
    justement `(tile, t, 6, 2)` verbatim, et il doit rester tel quel."""
    import ast                                                             # noqa: PLC0415
    assert int(OBSCURING_TYPE_ALL) == 6 and int(BLOCKING_ELEVATION_DIFFERENCE) == 2
    src = (PY / "engine" / "runner" / "abilities" / "loki" / "mv71.py").read_text(encoding="utf-8")
    appels = [n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "get_tiles_obscuring_terrain"]
    assert len(appels) == 2, (
        "le nombre d'appels a la geometrie de ligne de vue a change : %d" % len(appels))
    for call in appels:
        noms = [a.id for a in call.args[3:5] if isinstance(a, ast.Name)]
        assert noms == ["OBSCURING_TYPE_ALL", "BLOCKING_ELEVATION_DIFFERENCE"], (
            "les deux derniers arguments ne sont pas les constantes NOMMEES : %s"
            % [ast.dump(a) for a in call.args[3:5]])


# ================================================================================================
# 2. LA LIGNE DE VUE -- bascule sous une SEULE variable
# ================================================================================================

def test_bascule_rocher_haut_vs_rocher_bas():
    """MEMES unites, MEMES positions, MEME distance, MEME compte de tuiles libres : seule
    l'elevation du rocher change. Rocher a 3 -> les deux tuiles libres sont MASQUEES et le gate
    refuse ; rocher a 1 -> elles sont CLAIRES et le gate accepte."""
    from engine.runner.abilities.loki.mv71 import _pick_tile               # noqa: PLC0415
    assert _regle(BASE, 3) == REFUS, "rocher haut : toutes les candidates sont masquees"
    assert _regle(BASE, 1) == 0, "rocher bas : la ligne de vue est degagee"
    # LE COMPTE EST INVARIANT : ce n'est PAS le disque qui decide (contraste avec #287-r11-r2).
    for elev in (1, 3):
        st = _substrat(BASE, elev)
        libres = [t for t in st.board.by_id
                  if st.board.walkable(t)
                  and 1 <= hexgeo.distance(st.board.coord(t), (0, 0)) <= 4
                  and st.board.coord(t) not in ((0, 0), (2, 0))]
        assert sorted(st.board.coord(t) for t in libres) == [(3, 0), (4, 0)], elev
    # et le port refuse bien AU NIVEAU `PickTile`, pas par un autre bras du gate
    assert _pick_tile(_substrat(BASE, 3), U_CASTER, U_CIBLE, DRONE,
                      MAX_SUMMONS_MESURE, first_only=True) is None
    assert _pick_tile(_substrat(BASE, 1), U_CASTER, U_CIBLE, DRONE,
                      MAX_SUMMONS_MESURE, first_only=True) is not None


def test_la_geometrie_obscurcissante_est_celle_de_MovementQuery():
    """Le mirror ne re-implemente pas la ligne : il APPELLE
    `MovementQuery$$GetTilesObscuringTerrain`. On le verifie sur le meme substrat, dans le meme
    sens que le decompile (candidate -> cible)."""
    from engine.services.movement_query import get_tiles_obscuring_terrain  # noqa: PLC0415
    haut, bas = _board(3), _board(1)
    for pos in ((3, 0), (4, 0)):
        assert get_tiles_obscuring_terrain(haut, pos, (0, 0), OBSCURING_TYPE_ALL,
                                           BLOCKING_ELEVATION_DIFFERENCE) == {(1, 0)}
        assert get_tiles_obscuring_terrain(bas, pos, (0, 0), OBSCURING_TYPE_ALL,
                                           BLOCKING_ELEVATION_DIFFERENCE) == set()


# ================================================================================================
# 3. CE CALL-SITE N'EST PAS LA CASCADE DE CIBLAGE
# ================================================================================================

def test_EnableObscuringTerrain_ne_desarme_PAS_ce_call_site():
    """`TargetingQuery$$GetTilesObscuringTerrain` gate sur `TargetingConfiguration.
    EnableObscuringTerrain (+0x10)`, sur `IsFriendOrHasFriendlyUnitOnIt` et sur les bits 25/26 ;
    `IsTargetInAttackRangeForSummon`, lui, appelle `IMovementQuery` DIRECTEMENT avec les litteraux
    `(6, 2)`. Un port qui aurait reutilise `services.targeting_query.target_is_obscured` rendrait
    donc << non obscurci >> des que la BC pose ce drapeau a faux -- et ACCEPTERAIT une cible que le
    natif refuse."""
    st = _substrat(BASE, 3)
    assert st.enable_obscuring_terrain is True, "le defaut du port a change"
    st.enable_obscuring_terrain = False
    assert int(P._porteur(MV71).get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE) or 0) \
        == REFUS, "le drapeau de la CASCADE a desarme un call-site qui ne le lit pas"
    # contre-epreuve : le foyer de la CASCADE, lui, l'honore (sinon le test ci-dessus ne dit rien)
    from engine.services.targeting_query import target_is_obscured          # noqa: PLC0415
    assert target_is_obscured(_board(3), [(3, 0)], (0, 0), int(TR.TargetIsEnemy),
                              enable_obscuring_terrain=True) is True
    assert target_is_obscured(_board(3), [(3, 0)], (0, 0), int(TR.TargetIsEnemy),
                              enable_obscuring_terrain=False) is False


# ================================================================================================
# 4. LE CLAMP MELEE -- depuis la TUILE CANDIDATE, pas depuis le caster
# ================================================================================================

def test_clamp_melee_depuis_la_tuile_candidate():
    """Rocher BAS (ligne de vue degagee, donc ce n'est pas elle qui decide). Un ennemi en (4,0) est
    ADJACENT a la tuile libre (3,0) : `ShouldApplyRangedInMelee(parent, [(3,0)], ...)` devient vrai
    -> la portee tombe a 1 -> `IsAdjacentTo((3,0), (0,0))` est FAUX (d = 3) -> refus. La tuile
    (4,0), elle, est occupee par cet ennemi, donc n'est plus candidate.

    ⚠ C'est bien le VOISINAGE DE LA CANDIDATE qui decide, pas celui du CASTER : le caster est en
    (2,0), et son seul voisin marchable est (3,0), qui reste VIDE dans les deux bras."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _occupants_by_tile, _should_apply_ranged_in_melee_from_tile)
    assert _regle(BASE, 1) == 0, "sans l'ennemi, le gate accepte"
    assert _regle(AVEC_ENNEMI, 1) == REFUS, "l'ennemi adjacent a la candidate doit faire refuser"
    st = _substrat(AVEC_ENNEMI, 1)
    occ = _occupants_by_tile(st, st.board)
    assert _should_apply_ranged_in_melee_from_tile(st.board, _tid(3, 0), 1, occ) is True
    # ... et le CASTER, lui, n'a aucun ennemi au contact (sinon un AUTRE bit deciderait)
    from engine.runner.abilities.targeting import should_apply_ranged_in_melee   # noqa: PLC0415
    assert should_apply_ranged_in_melee(st, U_CASTER) is False


def test_le_clamp_est_desarme_par_l_elevation_entre_candidate_et_ennemi():
    """`CanMeleeAttackOverElevationDifference(attackerTile, adj)` est une CONJONCTION de
    `ShouldApplyRangedInMelee` : un ennemi separe de la candidate par 2 crans d'elevation ne
    declenche pas le clamp. Substrat FABRIQUE (le montage precedent est plat)."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _should_apply_ranged_in_melee_from_tile)
    b = _board(1)
    occ_proche = {_tid(4, 0): (2, False, True)}
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ_proche) is True
    b.by_id[_tid(4, 0)]["elevation"] = 2          # |0 - 2| >= 2 -> l'ennemi ne compte plus
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ_proche) is False


def test_un_ALLIE_adjacent_a_la_candidate_ne_clampe_pas():
    """`!IsFriend(attacker, u, state)` : c'est l'EQUIPE qui decide, et c'est exactement la seule
    variable du montage live `degage` -> `melee-candidate`."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _should_apply_ranged_in_melee_from_tile)
    b = _board(1)
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1,
                                                   {_tid(4, 0): (1, False, True)}) is False
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1,
                                                   {_tid(4, 0): (2, False, True)}) is True


def test_un_STEPPABLE_ou_un_UNTARGETABLE_adjacent_ne_clampe_pas():
    """Les deux autres conjonctions du corps natif : `!HasSteppableUnit(adj)` et `IsTargetable(u)`.
    Aucun montage live ne les produit -- il faudrait un decoy adjacent a la tuile de spawn."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _should_apply_ranged_in_melee_from_tile)
    b = _board(1)
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1,
                                                   {_tid(4, 0): (2, True, True)}) is False
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1,
                                                   {_tid(4, 0): (2, False, False)}) is False


# ================================================================================================
# 5. L'ELEVATION FINALE -- ce qu'elle DISCRIMINE, et ce qu'elle ne discrimine pas
# ================================================================================================

def test_CanMeleeAttackOverElevationDifference_est_IMPLIQUE_sur_une_cible_a_UN_pied():
    """LECTURE, pas supposition. Quand `range == 1`, le natif exige d'abord `IsAdjacentTo(tile,
    GetTiles(target))` -- et `TileExtensions$$IsAdjacentTo` delegue a
    `MovementUtil$$AreTilesAdjacent`, qui porte DEJA la porte `|dElev| < 2`. Sur une cible A UN
    PIED, `GetMainTile(target)` EST cette tuile-la : la clause finale ne peut donc jamais changer
    le verdict. Elle ne discrimine que sur une cible MULTI-PIEDS, ou `IsAdjacentTo` regarde TOUS
    les pieds et l'elevation la MAIN TILE seule."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _is_target_in_attack_range_for_summon)
    from engine.services.battle_query import are_tiles_adjacent            # noqa: PLC0415
    b = _board(0)                                 # rocher a plat : il n'obscurcit rien
    b.by_id[_tid(1, 0)]["walkable"] = True        # (1,0) devient une candidate legitime
    # PLAT : la candidate (1,0) est adjacente a la cible, et le gate de portee 1 passe.
    assert are_tiles_adjacent((1, 0), (0, 0), b) is True
    assert _is_target_in_attack_range_for_summon(b, _tid(1, 0), [(0, 0)], 1, 1, {}) is True
    # CIBLE SURELEVEE DE 2 CRANS : `AreTilesAdjacent` refuse DEJA -- la clause finale, qui compare
    # les MEMES deux tuiles, ne peut plus rien trancher.
    b.by_id[_tid(0, 0)]["elevation"] = 2
    assert are_tiles_adjacent((1, 0), (0, 0), b) is False
    assert _is_target_in_attack_range_for_summon(b, _tid(1, 0), [(0, 0)], 1, 1, {}) is False


def test_CanMeleeAttackOverElevationDifference_DISCRIMINE_sur_une_cible_MULTI_PIEDS():
    """La cible occupe DEUX tuiles : (0,0) -- sa MAIN TILE, surelevee -- et (2,0), plate. La
    candidate (3,0) est adjacente au SECOND pied (|dElev| = 0), donc `IsAdjacentTo` passe ; mais
    `CanMeleeAttackOverElevationDifference(tile, GetMainTile(target))` compare a (0,0), et
    |0 - 2| >= 2 -> refus. C'est le SEUL regime ou cette clause change le verdict."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _is_target_in_attack_range_for_summon)
    b = _board(1)
    b.by_id[_tid(0, 0)]["elevation"] = 2                     # la MAIN TILE, surelevee
    pieds = [(0, 0), (2, 0)]                                 # `GetTiles(target)`, dans l'ORDRE
    occ = {_tid(4, 0): (2, False, True)}                     # ennemi adjacent a (3,0) -> clamp a 1
    assert _is_target_in_attack_range_for_summon(b, _tid(3, 0), pieds, 4, 1, occ) is False
    # CONTRE-EPREUVE : main tile a plat -> la clause laisse passer, TOUT LE RESTE ETANT EGAL.
    b.by_id[_tid(0, 0)]["elevation"] = 0
    assert _is_target_in_attack_range_for_summon(b, _tid(3, 0), pieds, 4, 1, occ) is True


# ================================================================================================
# 6. LE PREMIER BRAS -- `IsTargetable(target)`
# ================================================================================================

def test_une_cible_non_ciblable_fait_rendre_faux():
    """`if (target == null || !UnitExtensions.IsTargetable(target)) return false;` -- premiere
    ligne du corps natif. INERTE dans nos runners (aucun chemin du port ne pose
    `UnitFlag.Untargetable`), le mirror est ecrit pour que la regle s'active d'elle-meme le jour ou
    le drapeau sera pose."""
    from engine.runner.abilities.loki.mv71 import (                        # noqa: PLC0415
        _is_target_in_attack_range_for_summon)
    b = _board(1)
    assert _is_target_in_attack_range_for_summon(b, _tid(3, 0), [(0, 0)], 4, 1, {},
                                                 target_is_targetable=True) is True
    assert _is_target_in_attack_range_for_summon(b, _tid(3, 0), [(0, 0)], 4, 1, {},
                                                 target_is_targetable=False) is False
    # et une cible SANS tuile (`GetTiles` vide) : la boucle de ligne de vue ne tourne pas, mais le
    # `min` de distance n'a rien a comparer -> le natif ne peut rien affirmer -> faux.
    assert _is_target_in_attack_range_for_summon(b, _tid(3, 0), [], 4, 1, {}) is False


# ================================================================================================
# 7. LE REPLI -- `UnobscuredTilesSelector$$IsObscured`
# ================================================================================================

def _obscurci(board, from_tiles, tile_pos) -> bool:
    """Le maillon `UnobscuredTiles`, appele PAR SON NOEUD DSL (#287-r11-r2-r1-r3).

    Il etait un collapse imperatif (`mv71._is_obscured_from_tiles`) jusqu'au 2026-08-15 ; son
    artefact natif est un `IdunBattleLogic.Entities.DSLSelectors$$UnobscuredTiles`, donc un ARBRE
    (doctrine #149). Ce helper monte le `DslContext` minimal que le noeud exige -- c'est-a-dire le
    board ET l'accesseur `tiles_obscuring_terrain`, que la face DECISION pose elle aussi a la main.
    Les assertions qui suivent sont INCHANGEES : c'est la MEME formule, evaluee par l'arbre."""
    from engine.dsl.base import DslContext                                 # noqa: PLC0415
    from engine.runner.abilities.loki import mv71                          # noqa: PLC0415
    ctx = DslContext(units=[], board=board,
                     tiles_obscuring_terrain=mv71._tiles_obscuring_terrain_for(board))
    tid = board.id_at(int(tile_pos[0]), int(tile_pos[1]))
    return mv71._unobscured_tiles(ctx, from_tiles, int(tid))


def test_IsObscured_liste_source_vide_rend_OBSCURCI():
    """`foreach (c in caster) { if (...Count == 0) return false; } return true;` -- sur une liste
    VIDE la boucle ne tourne pas et le natif rend `true`. Le collapse d'un `return true` en
    `return false` aurait garde une tuile que le natif RETIRE.

    ⚠ Le NOEUD atteint le meme verdict par un chemin DIFFERENT, et c'est LU : `Select` ne va meme
    pas jusqu'a `IsObscured`, il sort sur `if (caster.Count == 0) return <liste VIDE>`. Les deux
    lectures coincident sur cette entree-la, et c'est ce que ce test grave."""
    assert _obscurci(_board(1), [], (3, 0)) is True


def test_IsObscured_une_seule_ligne_degagee_suffit():
    """`return false` des la PREMIERE source degagee : c'est un OU, pas un ET (contraste avec la
    boucle de `IsTargetInAttackRangeForSummon`, qui refuse des qu'UNE tuile de la cible est
    masquee)."""
    haut = _board(3)
    assert _obscurci(haut, [(0, 0)], (3, 0)) is True
    # (2,0) voit (3,0) sans traverser le rocher -> une source degagee suffit
    assert _obscurci(haut, [(0, 0), (2, 0)], (3, 0)) is False


def test_le_repli_de_pick_tile_traverse_le_maillon_UnobscuredTiles():
    """Le cap est atteint (3 drones), aucune candidate primaire : le repli propose la tuile du
    drone le plus faible -- et la RETIRE si elle est masquee depuis la cible."""
    from engine.runner.abilities.loki.mv71 import _pick_tile               # noqa: PLC0415
    # 3 drones : le plus faible en (3,0). Toutes les tuiles marchables sont occupees -> repli.
    drones = [(9101, DRONE, 1, 3), (9102, DRONE, 1, 4), (9103, DRONE, 1, 2)]
    unites = [(U_CIBLE, "necroWarden", 2, 0), (U_CASTER, PORTEUR, 1, 1)] + drones
    # le caster doit etre sur une tuile MARCHABLE : on prend un board sans rocher pour ce bras,
    # et on remet l'obstruction par l'elevation de la tuile (1,0) elle-meme.
    def _st(elev):
        b = _board(elev)
        b.by_id[_tid(1, 0)]["walkable"] = True          # le caster s'y tient
        dv = {"currentPlayer": 1, "units": [
            {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
             "pos": {"col": col, "row": 0}, "effects": []}
            for (uid, vid, team, col) in unites]}
        ob = {"units": [{"squadId": u["id"], "hp": 10 if u["id"] == 9101 else 100,
                         "hpMax": 100} for u in dv["units"]]}
        snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _c) in unites]}
        return load_state(dv, ob, snap, board=b)
    assert _pick_tile(_st(1), U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE) == _tid(3, 0), (
        "rocher bas : le repli doit rendre la tuile du drone le plus faible")
    assert _pick_tile(_st(3), U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE) is None, (
        "rocher haut : `UnobscuredTiles` doit retirer cette tuile")


# ================================================================================================
# 8. MUTANTS EN DELTA -- desarme, la bascule doit s'effondrer
# ================================================================================================

def test_desarme_le_port_redevient_PERMISSIF(monkeypatch):
    """LA VUE ROUGE, offline. Substituer le troisieme filtre par le collapse d'avant
    (`1 <= d <= portee`, deja applique par l'anneau, donc `True` partout) fait perdre les DEUX
    refus -- celui de la ligne de vue et celui du clamp melee. Sans cet etage, les tests precedents
    seraient verts sur un port qui ne consulte plus rien."""
    from engine.runner.abilities.loki import mv71                          # noqa: PLC0415
    monkeypatch.setattr(mv71, "_is_target_in_attack_range_for_summon", lambda *a, **k: True)
    # #287-r11-r2-r1-r3 : le collapse `_is_obscured_from_tiles` est devenu `_unobscured_tiles`, qui
    # monte le NOEUD DSL. Le patch vise le nouveau nom -- viser l'ancien laisserait ce mutant sans
    # morsure, donc un desarmement qui ne desarme rien (le vice exact de #485-r1-r1).
    monkeypatch.setattr(mv71, "_unobscured_tiles", lambda *a, **k: False)
    assert _regle(BASE, 3) == 0, "le desarmement ne mord pas : la mesure ne prouve rien"
    assert _regle(AVEC_ENNEMI, 1) == 0


def test_la_bascule_est_restauree_hors_mutant():
    """Le mutant precedent est `monkeypatch`e : ce test-ci echoue si la restauration n'a pas eu
    lieu (ordre-dependance, cf. #485-r1-r3)."""
    assert _regle(BASE, 3) == REFUS
    assert _regle(AVEC_ENNEMI, 1) == REFUS


# ================================================================================================
# 9. #287-r11-r2-r1-r2 -- LE TROISIEME GATE DE `ShouldApplyRangedInMelee`, ET LE CANAL DES TRAITS
# ================================================================================================
#
# Le corps natif a TROIS gardes avant sa boucle, pas deux :
#
#     if (attackerTiles == null || attackerTiles.Count == 0)         return false;
#     if (!UnitExtensions.HasTrait(attacker, 0xb) && !ignoreTrait)   return false;
#     if (UnitExtensions.HasFlag(attacker, 0x1c))                    return false;   <-- CELUI-CI
#
# Il manquait aux DEUX mirrors. Sa direction est celle de #287-r11-r1-r1-r2 : le port CLAMPAIT une
# portee que le natif laisse entiere (ecart RESTRICTIF).

def test_l_ordinal_28_nomme_TROIS_choses_differentes():
    """LE PIEGE D'ORDINAL, MESURE -- c'est ce qui rend le NOM obligatoire (#498-r3).

    `0x1c` vaut `UnitFlag.IngoreRangedInMelee` (typo native), MAIS aussi `UnitTrait.Impervious`,
    et le BIT 28 de `TargetingRule` est `CasterCanMove`. Confondre les trois n'aurait leve AUCUNE
    erreur : le port aurait juste teste autre chose. Le mirror doit donc citer le MEMBRE, et ce
    test fige les trois noms."""
    from engine.entities.traits.unit_trait import UnitTrait as _UT           # noqa: PLC0415
    from engine.entities.unit_flag import UnitFlag                           # noqa: PLC0415
    assert int(UnitFlag.IngoreRangedInMelee) == 28
    assert UnitFlag(28).name == "IngoreRangedInMelee"
    assert _UT(28).name == "Impervious", "l'ordinal 28 nomme AUTRE CHOSE dans UnitTrait"
    assert UnitFlag(28).name != _UT(28).name
    bit28 = [r.name for r in TR if int(r) == (1 << 28)]
    assert bit28 == ["CasterCanMove"], bit28


def test_l_ordinal_du_flag_est_celui_du_BUILD():
    """`data/symbols/<build>/frida/enums.tsv` est la source ; le mirror ne doit pas deriver."""
    from engine.entities.unit_flag import UnitFlag                           # noqa: PLC0415
    tsv = PY.parents[1] / "data" / "symbols" / BUILD / "frida" / "enums.tsv"
    ligne = next((l for l in tsv.read_text(encoding="utf-8").splitlines()
                  if l.startswith("IdunBattle.Entities.Enum.UnitFlag\t")), None)
    assert ligne is not None, "l'enum `UnitFlag` est absente de la table du build"
    membres = dict(p.split("=", 1) for p in ligne.split("\t")[1].split(","))
    assert membres["28"] == "IngoreRangedInMelee", membres.get("28")
    assert int(UnitFlag[membres["28"]]) == 28


def test_le_gate_du_mirror_targeting_court_circuite_le_clamp():
    """`targeting.should_apply_ranged_in_melee` : MEME substrat, le flag SEUL change le verdict.

    Le montage est celui du clamp (un ennemi au contact du caster) ; sans le flag le mirror rend
    `True`, avec le flag il rend `False` -- exactement le `return false` natif, AVANT la boucle."""
    from engine.entities.unit_flag import UnitFlag                           # noqa: PLC0415
    from engine.runner.abilities.targeting import should_apply_ranged_in_melee   # noqa: PLC0415
    from engine.runner.components import UnitFlagsComponent                  # noqa: PLC0415
    # CASTER en (2,0), ennemi en (3,0) : ADJACENTS -> le clamp s'arme.
    unites = [(U_CASTER, PORTEUR, 1, 2), (U_CIBLE, "necroWarden", 2, 0),
              (U_ENNEMI, "necroWarden", 2, 3)]
    st = _substrat(unites, 1)
    assert should_apply_ranged_in_melee(st, U_CASTER) is True, (
        "le montage doit VRAIMENT armer le clamp, sinon le bras suivant est vrai par vacuite")
    ent = st.get_entity(U_CASTER)
    fl = ent.get_component(UnitFlagsComponent) or ent.add_component(UnitFlagsComponent())
    fl.add(UnitFlag.IngoreRangedInMelee)
    assert should_apply_ranged_in_melee(st, U_CASTER) is False


def test_le_behaviour_pose_ET_retire_le_flag_autour_de_l_attaque_du_drone(monkeypatch):
    """LE SEUL POSEUR DU FLAG DANS TOUT LE BINAIRE, et le port l'omettait.

    `MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` compose
    `AddEffect & AddEffect & AddFlag(sel, 0x1c) & UseActiveAbility(...) & RemoveFlag(sel, 0x1c)` --
    le porteur du flag est le **DRONE**, et il est TRANSITOIRE (l'etat final est INCHANGE, ce que
    les deux dernieres assertions verifient).

    Le discriminant est donc l'ETAT PENDANT L'ATTAQUE : on substitue `AttackDamageOperation.execute`
    par un temoin qui releve le flag du drone au moment ou le natif l'aurait pose."""
    from engine.entities.unit_flag import UnitFlag                           # noqa: PLC0415
    from engine.runner.abilities.loki import mv71                            # noqa: PLC0415
    from engine.runner.components import UnitFlagsComponent                  # noqa: PLC0415
    st = _substrat(BASE, 1)
    vu = {}

    def _temoin(state, att, tgt, *a, **k):
        """L'attaque elle-meme n'est PAS rejouee : elle exigerait un `state.rng` cale, et ce test
        ne porte pas sur le degat mais sur l'ETAT DU DRONE a cet instant precis."""
        e = state.get_entity(int(att))
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        vu["pendant"] = bool(fl is not None and fl.has(UnitFlag.IngoreRangedInMelee))
        vu["drone"] = int(att)
        return None

    monkeypatch.setattr(mv71.AttackDamageOperation, "execute", staticmethod(_temoin))
    out = mv71.MV71SniperDroneSquadAttackAbility().execute_behaviour(st, U_CASTER, U_CIBLE)
    assert out.get("spawned"), "aucun drone invoque : le montage ne mesure rien -- %r" % (out,)
    assert vu.get("pendant") is True, (
        "le flag `IngoreRangedInMelee` n'est PAS pose sur le drone pendant son attaque")
    # ... et il est RETIRE : l'etat final ne le porte plus (le natif fait `RemoveFlag`).
    e = st.get_entity(vu["drone"])
    fl = e.get_component(UnitFlagsComponent)
    assert not (fl is not None and fl.has(UnitFlag.IngoreRangedInMelee)), (
        "le flag survit a l'attaque : le `RemoveFlag` de la chaine DSL n'est pas porte")


def test_le_gate_du_mirror_mv71_est_en_TRI_ETAT():
    """`_should_apply_ranged_in_melee_from_tile` : `True` MESURE court-circuite ; `False` et `None`
    laissent la boucle s'evaluer.

    La DIRECTION est le livrable : `None` = pas mesure -> on n'allege PAS. Alleger elargirait la
    portee du drone (le clamp a 1 disparaitrait) et fabriquerait des candidates que le natif
    refuse."""
    from engine.runner.abilities.loki.mv71 import (                          # noqa: PLC0415
        _should_apply_ranged_in_melee_from_tile)
    b = _board(1)
    occ = {_tid(4, 0): (2, False, True)}          # un ennemi au contact de la candidate (3,0)
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ) is True
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ, None) is True
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ, False) is True
    assert _should_apply_ranged_in_melee_from_tile(b, _tid(3, 0), 1, occ, True) is False


def test_le_cablage_runner_lit_le_flag_du_PARENT(monkeypatch):
    """`BattleQuery$$IsTargetInAttackRangeForSummon` passe **`parent`** a `ShouldApplyRangedInMelee`,
    pas le drone -- donc `_pick_tile` doit lire le `UnitFlagsComponent` du CASTER.

    Le compteur est la contre-epreuve : sans lui, un cablage qui ne passerait JAMAIS le flag
    (defaut `None` partout) rendrait le meme verdict et ce test serait vert par coincidence."""
    from engine.entities.unit_flag import UnitFlag                           # noqa: PLC0415
    from engine.runner.abilities.loki import mv71                            # noqa: PLC0415
    from engine.runner.components import UnitFlagsComponent                  # noqa: PLC0415
    vus = []
    origine = mv71._should_apply_ranged_in_melee_from_tile
    monkeypatch.setattr(mv71, "_should_apply_ranged_in_melee_from_tile",
                        lambda b, t, team, occ, ign=None: (vus.append(ign)
                                                           or origine(b, t, team, occ, ign)))
    st = _substrat(AVEC_ENNEMI, 1)
    mv71._pick_tile(st, U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE)
    assert vus, "le foyer n'a pas ete consulte : le montage ne mesure rien"
    assert set(vus) == {False}, "sans le flag, le cablage doit passer `False` MESURE : %r" % (vus,)

    vus.clear()
    ent = st.get_entity(U_CASTER)
    fl = ent.get_component(UnitFlagsComponent) or ent.add_component(UnitFlagsComponent())
    fl.add(UnitFlag.IngoreRangedInMelee)
    mv71._pick_tile(st, U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE)
    assert set(vus) == {True}, "le flag du PARENT n'atteint pas le foyer : %r" % (vus,)


def _pick_pred(st, steppable_sur_ennemi: bool):
    """`pick_tile_scene` (face PREDICTION) sur une `Scene` derivee du MEME `State` que le runner.

    `steppable_sur_ennemi` accorde le trait EN BATAILLE (`AddTraitOperation` -> `ctx.traits`),
    c'est-a-dire hors du kit gameconfig -- le seul regime qui separe les deux canaux."""
    from engine.entities.traits.unit_trait import UnitTrait                  # noqa: PLC0415
    from engine.playbook.scene import Scene                                  # noqa: PLC0415
    from engine.runner.abilities.loki.mv71 import pick_tile_scene            # noqa: PLC0415
    from engine.runner.components import StatsComponent                      # noqa: PLC0415
    if steppable_sur_ennemi:
        sc = st.get_entity(U_ENNEMI).get_component(StatsComponent)
        sc.ctx.traits = list(sc.ctx.traits or ()) + [UnitTrait.Steppable.name]
    return pick_tile_scene(Scene.from_state(st), U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE)


def test_la_face_prediction_lit_les_traits_du_UnitContext_pas_la_borne_statique():
    """SECOND VOLET, CONFRONTE AU SITE. `Steppable` passait par `entity_trait_names(None, visualId)`
    -- la BORNE STATIQUE (kit gameconfig + alliance), aveugle a tout trait ACCORDE EN BATAILLE et a
    la mesure live `combatSnapshot.units[].traits`. Or `entity_trait_names` documente que
    `Scene.ctx(uid)` est LE MEME objet que le `StatsComponent.ctx` que lit la face RUNNER : c'etait
    un FORK entre les deux faces, pas une borne assumee.

    LE DISCRIMINANT EST LE VERDICT DE `pick_tile_scene`, pas la valeur d'un helper : l'ennemi de
    (4,0) est au contact de la seule candidate (3,0) ; sans `Steppable` il ARME le clamp melee
    (`!HasSteppableUnit(adj)`) et la candidate tombe, avec `Steppable` il ne l'arme plus. La face
    RUNNER voit le trait accorde en bataille et rend la tuile ; la face PREDICTION doit rendre LA
    MEME chose. Sur l'arbre d'avant la tranche elle lisait le kit et rendait `None`."""
    from engine.entities.traits.unit_trait import (UnitTrait,                # noqa: PLC0415
                                                   entity_trait_names)
    from engine.runner.abilities.loki.mv71 import _pick_tile                 # noqa: PLC0415
    # Le KIT ne porte pas le trait -- sans quoi les deux canaux coincideraient et rien ne serait
    # discrimine.
    assert UnitTrait.Steppable.name not in entity_trait_names(None, "necroWarden")

    # (a) TEMOIN, sans le trait : les DEUX faces refusent (le clamp mord).
    assert _pick_tile(_substrat(AVEC_ENNEMI, 1), U_CASTER, U_CIBLE, DRONE,
                      MAX_SUMMONS_MESURE) is None
    assert _pick_pred(_substrat(AVEC_ENNEMI, 1), False) is None

    # (b) trait ACCORDE EN BATAILLE : la face RUNNER le voit et rend la tuile (3,0).
    st_run = _substrat(AVEC_ENNEMI, 1)
    from engine.runner.components import StatsComponent                      # noqa: PLC0415
    sc = st_run.get_entity(U_ENNEMI).get_component(StatsComponent)
    sc.ctx.traits = list(sc.ctx.traits or ()) + [UnitTrait.Steppable.name]
    tid_runner = _pick_tile(st_run, U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE)
    assert tid_runner == _tid(3, 0), tid_runner

    # (c) ... et la face PREDICTION doit rendre LA MEME tuile. C'est ici que le fork se voyait.
    pos_pred = _pick_pred(_substrat(AVEC_ENNEMI, 1), True)
    assert pos_pred is not None, (
        "la face PREDICTION ne voit pas le trait accorde en bataille : elle lit encore la BORNE "
        "STATIQUE `entity_trait_names(None, visualId)`")
    assert tuple(pos_pred) == (3, 0), pos_pred
