"""#590-r6-r3 -- GARDE du threading de `casterTiles` jusqu'a la SURCHARGE PAR TYPE d'attaque
normale, et de l'ETAGE qui la lit.

CE QUE LE RESIDU DISAIT, ET CE QUE LES DECOMPILES DISENT
---------------------------------------------------------
La fiche imputait l'ecart a `PickTile` : « sur `tauMarksman`, une interrogation depuis une position
hypothetique evalue `PickTile` depuis la position REELLE », et proposait de propager `caster_tiles`
jusqu'a `_filter_can_attack_target_tile_from`. Les decompiles disent l'INVERSE, et c'est une
lecture -- chaque maillon est cite au site :

  * `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` memset une struct de 0x128
    octets, puis n'ecrit QUE `+0x08 caster`, `+0x10 target`, `+0x18 caster`, `+0x48 casterTiles`
    (`targetTiles`, son 4e parametre, n'est ecrit NULLE PART) ;
  * `IdunBattle.Entities.Abilities.AbilityEntities$$get_CasterPosition` rend `this+0x48` quand il
    est non nul, sinon un `UnitPosition` bati sur `this+0x40` ; `$$get_HasCasterPosition` est
    `+0x48 != 0 || +0x40 != 0` ;
  * `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger` -- le trigger que
    `DSLTriggers$$IsMeleeAttack` construit -- fait
    `pos = HasCasterPosition ? CasterPosition : EntityExtensions$$GetUnitPosition(caster, state)` ;
  * `PickTile`, lui, ne touche jamais `+0x48` : il lit `Target` (`entities+0x10`) pour l'anneau et
    la ligne de vue, et passe le caster en tant qu'ENTITE a
    `BattleQuery$$IsTargetInAttackRangeForSummon` (slot 0xc4) comme a
    `FilterTilesIfCanAttackTargetTileFromSelector$$Select`, qui resout ses deux selecteurs en une
    ENTITE et une TUILE.

L'etage lecteur est donc `IsMeleeAttack`, et lui SEUL. Ce fichier garde les deux moities : que le
relais TRANSMET (la surcharge le declare, donc `_invoque_regle_dynamique` le passe), et que le
port ne l'envoie PAS a `_pick_tile` -- un etage que le natif n'a pas.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et ASSUME : importer `handler` tire tout le paquet `abilities`. Les DEUX
    # formes de glob sont necessaires (`**/` exige un SEGMENT).
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                # HORS de `scripts/python/` : la table des noms d'ability vit dans le bundle Frida
                # et la cascade d'import la LIT (omission mesuree au merge de #806).
                "frida/hooks/data/ability-names.ts"),
    # Le rayon du drone et `maxSummons` sont LUS dans le gameconfig du build.
    "build": True,
    "toujours": False,
    "raison": "Threading de `casterTiles` vers la surcharge par type (#590-r6-r3) : ce fichier ne "
              "peut changer de verdict que si le relais par signature, la surcharge de 1076, le "
              "mirror `_is_melee_attack` ou le substrat de montage changent.",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.runner.snapshot import load_state                                    # noqa: E402
import engine.runner.abilities.targeting as T                                    # noqa: E402
import engine.runner.abilities.loki.mv71 as MV                                   # noqa: E402

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)   # 1076
PORTEUR = "tauMarksman"
U_CASTER, U_CIBLE = 9001, 9002


def _tid(col: int, row: int) -> int:
    return col * 100 + row + 1


def _board(n: int = 6) -> Board:
    tuiles = []
    for col in range(n):
        nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, 0) if r == 0 and 0 <= c < n]
        tuiles.append({"id": _tid(col, 0), "col": col, "row": 0, "elevation": 0,
                       "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat(unites, n: int = 6):
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": col, "row": 0}, "effects": []}
        for (uid, vid, team, col) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _c) in unites]}
    return load_state(dv, ob, snap, board=_board(n))


#: Caster en (4,0), cible en (0,0) : d = 4, donc PAS adjacent depuis la position REELLE. La tuile
#: (1,0), elle, EST adjacente a la cible : c'est la position hypothetique qui fait basculer.
LOIN = [(U_CASTER, PORTEUR, 1, 4), (U_CIBLE, "necroWarden", 2, 0)]

U_A, U_B = 9003, 9004
#: Le MEME regime, mais sur une LIGNE DE 4 dont le disque r=4 de la cible est SATURE (bloqueurs en
#: (1,0) et (3,0), caster en (2,0)). C'est ce montage-la qui DISCRIMINE : sans le bras melee,
#: `PickTile` ne trouve aucune tuile de spawn et la regle REFUSE. Sur la ligne de 6, `PickTile`
#: reussit -- un mutant y serait vert pour une raison qui n'est pas le threading (mesure du
#: premier jet de ce fichier : `assert 0 != 0`).
SATURE = [(U_CASTER, PORTEUR, 1, 2), (U_CIBLE, "necroWarden", 2, 0),
          (U_A, "ultraTitus", 1, 1), (U_B, "ultraTitus", 1, 3)]


# ================================================================================================
# 0. LE SUBSTRAT ET L'AIGUILLAGE -- sans eux les bascules seraient vraies par VACUITE
# ================================================================================================

def test_le_substrat_aiguille_bien_vers_la_surcharge_de_1076():
    st = _substrat(LOIN)
    assert T.normal_attack_type_for(st, U_CASTER) == MV71, (
        "l'attaque normale de `%s` n'est plus 1076 : le threading ne se mesure plus" % PORTEUR)
    assert hexgeo.distance((4, 0), (0, 0)) == 4, "la geometrie du substrat a change"
    assert hexgeo.distance((1, 0), (0, 0)) == 1


def test_1076_est_bien_la_SEULE_surcharge_par_type():
    """La fiche annonce « une seule surcharge », et c'est ce qui borne la portee de cette tranche.
    On le RE-DERIVE du registre plutot que de le recopier."""
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    surchargeurs = sorted(
        aid for aid in T.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE
        if (handler.ABILITY_CLASSES.get(int(aid)) is not None
            and "get_dynamic_invalid_target_reason"
            in handler.ABILITY_CLASSES[int(aid)].__dict__))
    assert surchargeurs == [MV71], (
        "la liste des types qui SURCHARGENT la regle dynamique a change : %r" % (surchargeurs,))


# ================================================================================================
# 1. LE RELAIS TRANSMET -- c'est ce que le residu tenait ouvert
# ================================================================================================

def test_la_surcharge_DECLARE_caster_tiles_donc_le_relais_le_transmet():
    """`_invoque_regle_dynamique` ne passe l'argument que si le porteur le DECLARE (threading par
    signature). Tant que 1076 ne le declarait pas, la chaine s'arretait la."""
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    porteur = handler.ABILITY_CLASSES[MV71]()
    assert T._accepte_caster_tiles(porteur.get_dynamic_invalid_target_reason) is True


def test_le_relais_passe_bien_la_VALEUR_pas_seulement_la_signature(monkeypatch):
    """Declarer ne suffit pas : on verifie que la valeur ARRIVE, en observant l'argument recu."""
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    vus = []
    klass = handler.ABILITY_CLASSES[MV71]
    monkeypatch.setattr(klass, "get_dynamic_invalid_target_reason",
                        lambda self, state, cid, tid, caster_tiles=None:
                        (vus.append(caster_tiles), 0)[1])
    st = _substrat(LOIN)
    porteur = T._NormalAttackTargeting(T.normal_attack_targeting_options(st, U_CASTER))
    porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE, [(1, 0)])
    porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE)
    assert vus == [[(1, 0)], None], (
        "le relais n'achemine pas la position interrogee jusqu'a la surcharge : %r" % (vus,))


# ================================================================================================
# 2. L'ETAGE LECTEUR EST `IsMeleeAttack`, ET SA BASCULE EST OBSERVABLE
# ================================================================================================

def test_is_melee_attack_bascule_sur_la_position_INTERROGEE():
    """`AbilityEntities.CasterPosition` gagne sur `GetUnitPosition(caster)` : depuis (4,0) la cible
    n'est pas adjacente, depuis (1,0) elle l'est."""
    st = _substrat(LOIN)
    assert MV._is_melee_attack(st, U_CASTER, U_CIBLE) is False, "position REELLE : d = 4"
    assert MV._is_melee_attack(st, U_CASTER, U_CIBLE, [(1, 0)]) is True, (
        "position INTERROGEE adjacente : le natif prend `CasterPosition`, pas la position reelle")


def test_le_bras_melee_de_la_regle_dynamique_suit_la_position_interrogee():
    """Le verdict COMPLET, pas seulement le predicat : `IsMeleeAttack` court-circuite `PickTile`,
    donc la regle rend `0` (aucun refus) des que la position interrogee est au contact -- ET, sur
    le montage SATURE, elle REFUSE sans lui. Les deux bras sur le MEME substrat : c'est ce qui
    rend la bascule attribuable au threading et pas a la geometrie."""
    st = _substrat(SATURE, 4)
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    porteur = handler.ABILITY_CLASSES[MV71]()
    assert int(porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE) or 0) != 0, (
        "depuis la position REELLE (d = 2, disque sature) la regle doit REFUSER")
    assert int(porteur.get_dynamic_invalid_target_reason(
        st, U_CASTER, U_CIBLE, [(1, 0)]) or 0) == 0, (
        "depuis (1,0) le bras MELEE doit court-circuiter, donc AUCUN refus")


def test_value_preservation_le_regime_None_est_celui_d_avant():
    """`caster_tiles=None` doit rendre EXACTEMENT le verdict d'avant, sur les deux voies."""
    st = _substrat(LOIN)
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    porteur = handler.ABILITY_CLASSES[MV71]()
    sans = int(porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE) or 0)
    trois_args = int(MV.mv71_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE) or 0)
    assert sans == trois_args
    assert MV._is_melee_attack(st, U_CASTER, U_CIBLE) is False


# ================================================================================================
# 3. CE QUE LE PORT NE DOIT **PAS** FAIRE -- `PickTile` ne lit pas `casterTiles`
# ================================================================================================

def test_pick_tile_ne_recoit_PAS_caster_tiles():
    """Le remede que la fiche proposait aurait ecrit un etage que le natif n'a pas. On fige la
    lecture : `_pick_tile` garde son contrat, et le relais ne lui passe rien de plus.

    Cran STRUCTUREL (la signature) **et** cran de SITE (le corps du relais) : le premier seul
    redeviendrait vert si quelqu'un ajoutait un parametre par defaut sans jamais le passer."""
    import inspect                                                               # noqa: PLC0415
    assert "caster_tiles" not in inspect.signature(MV._pick_tile).parameters, (
        "`_pick_tile` a recu un parametre `caster_tiles` : le decompile de `PickTile` ne lit "
        "JAMAIS `entities+0x48` -- il lit `Target` et le caster en tant qu'ENTITE")
    assert "caster_tiles" not in inspect.signature(
        MV._filter_can_attack_target_tile_from).parameters
    src = Path(MV.__file__).read_text(encoding="utf-8")
    corps = src.split("def mv71_dynamic_invalid_target_reason", 1)[1].split("\ndef ", 1)[0]
    assert "_is_melee_attack(state, caster_id, target_id, caster_tiles)" in corps, (
        "le relais n'achemine plus la position interrogee vers son SEUL etage lecteur")
    assert "caster_tiles" not in corps.split("_pick_tile(", 1)[1].split(")", 1)[0], (
        "le relais passe `caster_tiles` a `_pick_tile` : etage inexistant cote natif")


# ================================================================================================
# 4. MUTANTS -- chaque bascule doit S'EFFONDRER quand on retire ce qui la porte
# ================================================================================================

def test_MUTANT_une_surcharge_qui_ne_DECLARE_pas_ne_recoit_rien(monkeypatch):
    """La forme d'AVANT : le porteur garde son contrat a trois arguments -> `_invoque_regle_
    dynamique` ne transmet rien, et le bras melee ne peut plus basculer."""
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    klass = handler.ABILITY_CLASSES[MV71]
    monkeypatch.setattr(klass, "get_dynamic_invalid_target_reason",
                        lambda self, state, cid, tid:
                        MV.mv71_dynamic_invalid_target_reason(state, cid, tid))
    st = _substrat(SATURE, 4)
    porteur = T._NormalAttackTargeting(T.normal_attack_targeting_options(st, U_CASTER))
    assert T._accepte_caster_tiles(klass().get_dynamic_invalid_target_reason) is False
    # la position interrogee est PERDUE : le verdict redevient celui de la position reelle -- et
    # ce verdict-la est un REFUS, donc la bascule s'effondre pour de bon (pas un `0 == 0` vacant).
    avec = int(porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE, [(1, 0)]) or 0)
    sans = int(porteur.get_dynamic_invalid_target_reason(st, U_CASTER, U_CIBLE) or 0)
    assert avec == sans != 0, (
        "le mutant n'effondre pas la bascule : avec=%r sans=%r" % (avec, sans))


def test_MUTANT_is_melee_attack_qui_ignore_caster_tiles(monkeypatch):
    """Le mirror d'avant : la position lue est celle du `PositionComponent`, toujours."""
    monkeypatch.setattr(MV, "_is_melee_attack",
                        lambda state, cid, tid, caster_tiles=None: False)
    st = _substrat(SATURE, 4)
    from engine.runner.abilities import handler                                  # noqa: PLC0415
    porteur = handler.ABILITY_CLASSES[MV71]()
    assert int(porteur.get_dynamic_invalid_target_reason(
        st, U_CASTER, U_CIBLE, [(1, 0)]) or 0) != 0, (
        "sans le bras melee, la regle doit retomber sur `PickTile` et REFUSER (disque SATURE) -- "
        "si elle rend 0, l'etage 2 est vert pour une autre raison que le threading")
