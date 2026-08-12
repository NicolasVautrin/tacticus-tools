"""#979 -- les DEUX faces DECISION portees par la tranche, sur substrat SYNTHETIQUE.

    1188 DevastatingRefrain  (`adeptExorcist`, MoW) -- util = 1 + #ennemis OCCUPANT la forme
    1158 DutyEternal         (`ultraDreadnought`, MoW) -- util = 1 + Somme (10 si adjacente sinon 1)

CE QUE CE FICHIER GARDE, ET POURQUOI IL EST NECESSAIRE
-------------------------------------------------------
Les deux corps natifs ont chacun UNE lecture qui ne se devine pas, et dont l'erreur serait MUETTE :

  * `1188` -- le `If(IsPositionMachineForCurrentPlayer(2), {3,1,5}, {0,2,4})` choisit la FORME.
    Sans canal, `tile_targets.dsl_context_for_tile_target` lisait `None` et le predicat rendait
    False d'office : la forme etait la mauvaise sur tout plateau ou la MoW du joueur courant est
    en `Bottom`. Etage 1 exerce LES DEUX branches et exige qu'elles DIFFERENT.
  * `1158` -- `GetSurroundingUnits(t, 2, friendsOf: null, includeCenter: FALSE)`. Deux erreurs
    possibles, toutes deux silencieuses : compter l'occupant de `t` (le `10` deviendrait celui d'un
    occupant, pas d'un voisin), et filtrer par camp (le natif compte les DEUX). Etages 2 et 3.

Chaque etage porte sa CONTRE-EPREUVE : la mutation est jouee, le rouge est constate, l'etat est
restaure. Un garde qu'on n'a pas vu mordre ne prouve rien.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import hexgeo                                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS              # noqa: E402
from engine.playbook.noncomparable._base import NCContext        # noqa: E402
import engine.playbook.noncomparable.duty_eternal as DE          # noqa: E402
import engine.playbook.noncomparable.devastating_refrain as DR   # noqa: E402
import engine.playbook.noncomparable._targets as TGT             # noqa: E402
from engine.runner.abilities import sisterhood as SH             # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les deux ports, et le registre qui les rend atteignables.
        "scripts/python/engine/playbook/noncomparable/devastating_refrain.py",
        "scripts/python/engine/playbook/noncomparable/duty_eternal.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        # Le foyer partage DEPLACE par cette tranche, et son ancien hote.
        "scripts/python/engine/playbook/noncomparable/_targets.py",
        "scripts/python/engine/playbook/noncomparable/daemon_prince.py",
        # Les DEUX foyers d'artefact que les ports APPELLENT au lieu de les recabler.
        "scripts/python/engine/runner/abilities/sisterhood.py",
        "scripts/python/engine/services/spawn_tile_shape.py",
        # Le substrat geometrique des deux formules.
        "scripts/python/engine/battle_query.py",
        "scripts/python/hexgeo.py",
        # Le contexte DSL de la route tile-target (canal `machine_of_war_position`).
        "scripts/python/engine/playbook/tile_targets.py",
        # Le dispatch de route : 1188 doit rester NonComparable.
        "scripts/python/engine/entities/abilities/active_ability.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("substrat entierement SYNTHETIQUE (aucun gameconfig, aucun dump lu) : seuls les "
               "chemins ci-dessus peuvent changer le verdict."),
}

REFRAIN = int(ActiveAbilityType.DevastatingRefrain)   # 0x4a4 = 1188
DUTY = int(ActiveAbilityType.DutyEternal)             # 0x486 = 1158


# =================================================================================================
#  Substrat synthetique : un plateau plat, des positions choisies
# =================================================================================================

def _plateau(cols=8, rows=8):
    """Toutes les tuiles marchables, un id par position, voisinage hex NATIF."""
    pos = [(c, r) for c in range(cols) for r in range(rows)]
    tid = {p: 1000 + i for i, p in enumerate(pos)}
    neigh = {p: [q for q in hexgeo.neighbors(p[0], p[1]) if q in tid] for p in pos}
    return pos, tid, neigh


def _ctx(epos=(), fpos=(), mow=None, uid=7):
    pos, tid, neigh = _plateau()
    return NCContext(
        uid=uid, origin=None, reach_nc=[], epos=list(epos), fpos=list(fpos), plan={},
        hp_cur_by_id={}, neigh_by_pos=neigh, walkable_by_pos={p: True for p in pos},
        elev_by_pos={p: 0 for p in pos}, tile_id_by_pos=tid, is_wall_by_pos={},
        is_temporary_by_pos={}, machine_of_war_position=(None if mow is None else (lambda: mow)))


class _DslCtxStub:
    """`DslContext` minimal pour `tile_targets.unit_on_tile` et le selecteur de forme de 1188.

    On ne substitue PAS la geometrie : `devastating_refrain_shape` est appele pour de vrai. Seul le
    SUBSTRAT (plateau + unites) est synthetique."""

    def __init__(self, tid, units, caster):
        self.board = _BoardStub(tid)
        self.units = units
        self.caster = caster
        self.elev_by_pos = {}


class _BoardStub:
    def __init__(self, tid):
        self.by_id = {t: p for p, t in tid.items()}
        self._tid = dict(tid)

    def coord(self, tid):
        return self.by_id.get(tid)

    def id_at(self, col, row):
        return self._tid.get((col, row))


# =================================================================================================
#  ETAGE 1 -- 1188 : la FORME depend du cote du plateau, et les deux branches DIFFERENT
# =================================================================================================

def test_etage1_1188_les_deux_branches_de_IsPositionMachineForCurrentPlayer_different():
    """`DevastatingRefrainAbility$$GetShape()` =
    `If(IsPositionMachineForCurrentPlayer(2), GetShape(+0xf0 = {3,1,5}), GetShape(+0xf8 = {0,2,4}))`.

    Les deux tuples de directions sont DISJOINTS ({South, NE, NW} contre {North, SE, SW}), donc les
    deux formes ancrees sur la meme tuile ne partagent QUE la tuile visee. Un port qui lirait
    toujours la meme branche serait faux la moitie du temps, sans erreur."""
    assert not (set(SH.SHAPE_DIRECTIONS_MACHINE) & set(SH.SHAPE_DIRECTIONS_OTHER)), \
        "les deux tuples de directions doivent etre DISJOINTS -- sinon ce test ne discrimine rien"
    pb = DR.DevastatingRefrainPlaybook()
    assert pb._shape_directions(_ctx(mow=SH.MACHINE_POSITION_BOTTOM)) is SH.SHAPE_DIRECTIONS_MACHINE
    assert pb._shape_directions(_ctx(mow=1)) is SH.SHAPE_DIRECTIONS_OTHER
    # TRI-ETAT : canal muet -> le predicat natif rend FAUX, donc la branche `else`.
    assert pb._shape_directions(_ctx(mow=None)) is SH.SHAPE_DIRECTIONS_OTHER


def test_etage1_1188_utilite_est_1_plus_les_ennemis_de_la_forme():
    """`util = Fix64(1) + |{t in shape : IsEnemy(GetUnit(t), caster)}|`.

    GEOMETRIE DRIVEE : la cible est en (4,4) ; on place les ennemis sur les tuiles que
    `devastating_refrain_shape` rend REELLEMENT pour la branche `Bottom`, jamais sur des tuiles
    choisies a vue. L'attendu est donc DERIVE de l'artefact, pas releve apres coup."""
    pos, tid, _neigh = _plateau()
    cible = (4, 4)
    forme = SH.devastating_refrain_shape(tid[cible], SH.SHAPE_DIRECTIONS_MACHINE)
    dctx = _DslCtxStub(tid, [], {"id": 7, "team": 1})
    tuiles = [dctx.board.coord(t) for t in forme.select(dctx)]
    assert len(tuiles) == 4, "la forme doit porter la tuile visee + 3 voisines, vu %d" % len(tuiles)

    pb = DR.DevastatingRefrainPlaybook()
    for n_ennemis in (0, 1, 3):
        units = [{"id": 7, "team": 1, "alive": True, "hp": 10,
                  "pos": {"col": 0, "row": 7}}]
        for i, p in enumerate(tuiles[:n_ennemis]):
            units.append({"id": 100 + i, "team": 2, "alive": True, "hp": 10,
                          "pos": {"col": p[0], "row": p[1]}})
        ctx = _ctx(mow=SH.MACHINE_POSITION_BOTTOM)
        stub = _DslCtxStub(tid, units, {"id": 7, "team": 1})
        util = _evaluate_1188(pb, ctx, cible, stub)
        assert util == 1.0 + n_ennemis, \
            "%d ennemis dans la forme -> util %s attendu %s" % (n_ennemis, util, 1.0 + n_ennemis)


def _evaluate_1188(pb, ctx, cible, stub):
    """Joue `evaluate_non_comparable` en substituant le SEUL etage que le substrat synthetique ne
    peut pas fournir : `dsl_context_for_tile_target`, qui exige une `Scene` live. La FORME et le
    comptage, eux, sont joues pour de vrai."""
    vrai = DR.dsl_context_for_tile_target
    try:
        DR.dsl_context_for_tile_target = lambda _c: stub
        return pb.evaluate_non_comparable(None, cible, ctx)
    finally:
        DR.dsl_context_for_tile_target = vrai


def test_etage1_contre_epreuve_1188_un_ami_sur_la_forme_ne_compte_PAS():
    """MUTATION JOUEE : les memes unites, mais dans le camp du CASTER. Le natif teste
    `IsEnemy(u, caster)` ; un port qui compterait tout occupant rendrait la meme valeur."""
    pos, tid, _neigh = _plateau()
    cible = (4, 4)
    forme = SH.devastating_refrain_shape(tid[cible], SH.SHAPE_DIRECTIONS_MACHINE)
    dctx = _DslCtxStub(tid, [], {"id": 7, "team": 1})
    tuiles = [dctx.board.coord(t) for t in forme.select(dctx)]
    units = [{"id": 7, "team": 1, "alive": True, "hp": 10, "pos": {"col": 0, "row": 7}}]
    for i, p in enumerate(tuiles[:3]):
        units.append({"id": 200 + i, "team": 1, "alive": True, "hp": 10,   # MEME camp
                      "pos": {"col": p[0], "row": p[1]}})
    util = _evaluate_1188(DR.DevastatingRefrainPlaybook(), _ctx(mow=SH.MACHINE_POSITION_BOTTOM),
                          cible, _DslCtxStub(tid, units, {"id": 7, "team": 1}))
    assert util == 1.0, "MUTATION NON MORDANTE : 3 ALLIES sur la forme doivent laisser util = 1"


# =================================================================================================
#  ETAGE 2 -- 1158 : `includeCenter = false` EXCLUT l'occupant de la tuile de l'empreinte
# =================================================================================================

def _aire(ctx, cible):
    return DE.DutyEternalPlaybook()._area(ctx, cible)


def test_etage2_1158_l_occupant_d_une_tuile_de_l_empreinte_n_est_PAS_compte():
    """`GetSurroundingUnits(t, 2, null, includeCenter: FALSE)` -- `IterateSurroundingTiles` exclut
    `t`. Une unite DEBOUT sur une tuile de l'empreinte n'est donc comptee QUE par les AUTRES tuiles
    de l'empreinte, jamais par la sienne.

    Le test compare deux configurations qui ne different que par la POSITION d'une unite : sur une
    tuile de l'empreinte, ou juste a cote. Si le port incluait le centre, les deux vaudraient
    pareil."""
    pb = DE.DutyEternalPlaybook()
    cible = (4, 4)
    aire = _aire(_ctx(), cible)
    assert len(aire) == 3, "l'empreinte doit porter 3 pieds, vue %s" % (aire,)
    # une unite SUR le premier pied de l'empreinte
    dessus = pb.evaluate_non_comparable(None, cible, _ctx(epos=[aire[0]]))
    # la MEME unite, sur une tuile hors empreinte mais adjacente au meme pied
    voisine = next(q for q in hexgeo.neighbors(*aire[0]) if tuple(q) not in [tuple(a) for a in aire])
    a_cote = pb.evaluate_non_comparable(None, cible, _ctx(epos=[tuple(voisine)]))
    assert dessus != a_cote, (
        "MUTATION NON MORDANTE : `includeCenter = false` doit rendre les deux configurations "
        "DIFFERENTES (dessus=%s, a cote=%s)" % (dessus, a_cote))


def test_etage2_1158_le_10_est_celui_des_ADJACENTES():
    """`GetDistance(u, t) < 2 ? 10 : 1`, le centre EXCLU : la branche `10` ne peut valoir que
    `distance == 1`.

    Le port passe par `get_surrounding_tiles` (disque cube, sans porte d'elevation) puis
    `bq.get_distance` ; l'attendu, lui, est calcule DIRECTEMENT depuis `hexgeo.distance`, donc par
    un autre chemin. C'est ce qui en fait un controle et pas une tautologie -- et le `d == 0`
    (l'occupant de la tuile), le cas discriminant, est deja garde par le test precedent.

    Le montage ASSERTIONNE SON PROPRE NON-VIDE dans les DEUX regimes : il exige un temoin qui
    touche la branche `10` et un qui ne touche que la branche `1`. Sans les deux il ROUGIT au lieu
    de passer en ne verifiant rien.

    (Aucune tuile n'est a distance 2 des TROIS pieds ni vue par un SEUL d'entre eux : les trois
    sont mutuellement adjacents. C'est une propriete de l'empreinte, pas une limite du montage.)"""
    pb = DE.DutyEternalPlaybook()
    cible = (4, 4)
    aire = _aire(_ctx(), cible)
    assert len(aire) == 3, "empreinte inattendue %s -- le montage ne mesure rien" % (aire,)
    pos, _tid, _neigh = _plateau()

    def _attendu(q):
        """`1 + Somme_{t in aire} (10 si d == 1, 1 si d == 2, 0 sinon)` -- le `0` est
        `includeCenter = false` (d == 0) et le hors-disque (d > 2)."""
        u = pb.BASE_UTILITY
        for a in aire:
            d = hexgeo.distance(a, q)
            u += pb.NEAR_UTILITY if d == 1 else (pb.FAR_UTILITY if d == 2 else 0.0)
        return u

    vus_pres, vus_loin, deplaces = 0, 0, 0
    for q in pos:
        att = _attendu(q)
        if att == pb.BASE_UTILITY:
            continue                                  # hors portee des trois pieds
        ctx = _ctx(epos=[tuple(q)])
        # ⚠ L'OCCUPATION DEPLACE L'EMPREINTE : `CorrectArea` exige des tuiles LIBRES, donc une
        # unite debout sur un pied fait choisir une AUTRE direction -- ou aucune. Ce regime est
        # reel (et c'est celui que le test precedent exerce) ; ici on ne compare que les positions
        # qui laissent l'empreinte INCHANGEE, sinon l'attendu porterait sur une autre aire.
        if pb._area(ctx, cible) != aire:
            deplaces += 1
            continue
        vus_pres += any(hexgeo.distance(a, q) == 1 for a in aire)
        vus_loin += all(hexgeo.distance(a, q) != 1 for a in aire)
        got = pb.evaluate_non_comparable(None, cible, ctx)
        assert got == att, "unite en %s : port %s, attendu %s (profil %s)" \
            % (q, got, att, [hexgeo.distance(a, q) for a in aire])
    assert vus_pres and vus_loin, ("montage DEGENERE : %d temoins branche 10, %d branche 1 -- il "
                                   "en faut des DEUX (%d positions ecartees pour empreinte "
                                   "deplacee)" % (vus_pres, vus_loin, deplaces))


# =================================================================================================
#  ETAGE 3 -- 1158 : `friendsOf = null` -> les DEUX camps comptent
# =================================================================================================

def test_etage3_1158_les_allies_comptent_autant_que_les_ennemis():
    """`friendsOf = null` au call-site -> le natif n'appelle JAMAIS `IsEnemy`. Un port qui
    filtrerait par camp (le reflexe, et ce que font `TitanhammerSquad` / `DevastatingRefrain`)
    sous-compterait, en silence."""
    pb = DE.DutyEternalPlaybook()
    cible = (4, 4)
    aire = _aire(_ctx(), cible)
    voisin = next(q for q in hexgeo.neighbors(*aire[0]) if tuple(q) not in [tuple(a) for a in aire])
    par_ennemi = pb.evaluate_non_comparable(None, cible, _ctx(epos=[tuple(voisin)]))
    par_ami = pb.evaluate_non_comparable(None, cible, _ctx(fpos=[tuple(voisin)]))
    assert par_ennemi == par_ami and par_ennemi > 1.0, \
        "ami %s / ennemi %s : les deux doivent compter PAREIL et non nul" % (par_ami, par_ennemi)


def test_etage3_1158_empreinte_vide_rend_le_plancher_et_PAS_None():
    """Canal muet -> `get_area` rend `[]` -> l'utilite se reduit au plancher `Fix64(1)`, ce que le
    natif rendrait aussi sur une aire vide. Le gate `minUtility` du `Bucket` vaut `1` et laisse
    donc passer : le port ne REFUSE rien de plus que le natif."""
    pb = DE.DutyEternalPlaybook()
    ctx = NCContext(uid=7, origin=None, reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    assert not pb._area(ctx, (4, 4)), "canal muet -> aire VIDE (degradation conservatrice)"
    assert pb.evaluate_non_comparable(None, (4, 4), ctx) == pb.BASE_UTILITY


# =================================================================================================
#  ETAGE 4 -- le foyer DEPLACE reste UN seul foyer
# =================================================================================================

def test_etage4_le_shim_CtxBoard_est_partage_et_pas_forke():
    """`ThreeTileUnitSpawnShape` n'a que DEUX xrefs natives (`AetherStrideAbility`,
    `DutyEternalAbility`) : les deux ports doivent lire le MEME adaptateur. `daemon_prince` le
    re-expose sous son ancien nom prive -- l'IDENTITE est ce qui garantit qu'il n'a pas ete
    recopie."""
    import engine.playbook.noncomparable.daemon_prince as DP
    assert DP._CtxBoard is TGT.CtxBoard, "le shim a ete FORKE au lieu d'etre partage"
    assert DP._occupied is TGT.occupied


@pytest.mark.parametrize("aid", [REFRAIN, DUTY])
def test_etage4_les_deux_faces_sont_ATTEIGNABLES(aid):
    """Une classe portee mais absente du registre serait INERTE, sans erreur -- le mode de
    defaillance que #976 nomme pour `1231`."""
    assert aid in PLAYBOOKS, "%s absente de `noncomparable.PLAYBOOKS`" % aid
    assert PLAYBOOKS[aid].MIN_UTILITY == 1.0
