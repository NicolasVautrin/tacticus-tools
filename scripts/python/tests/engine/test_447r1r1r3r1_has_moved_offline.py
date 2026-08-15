"""#447-r1-r1-r3-r1 -- CLIQUETS du canal `has_moved` jusqu'a `CasterSubstrate` (face DECISION).

`IdunBattle.Entities.UnitExtensions$$DidMove(caster)` = `UnitFlagsComponent.Has(UnitFlag.Moved)` :
c'est le SECOND terme de la regle `CasterHasNotMoved`, dont `#447-r1-r1-r3` avait cable le PREFIXE
(`BattleQuery$$IsTurnOfUnit`).

LA PREMISSE `BLOCAGE: seeding` ETAIT PERIMEE, et ce fichier le garde : `NCContext.scene` porte
`Scene.moved_by_id`, alimente par `combatSnapshot.units[].unitFlags` (id du flag LU au runtime dans
`unitFlagTypes`, jamais ecrit en dur) et RE-CAPTURE a chaque pas par `refresh_shields`. Le transport
ne coute donc AUCUN RPC supplementaire.

⚠ SON GISEMENT EST ETROIT, ET C'EST UNE MESURE, PAS UNE EXCUSE. La clause est GARDEE par son
prefixe : chez l'unique appelant de production (`early_warning_override`), le << caster >>
interroge est un ENNEMI du joueur courant, donc `is_turn_of_unit` y est FAUX et ce terme reste
INERTE -- sauf sous CONTROLE MENTAL, ou une unite dont le `playerId` est le NOTRE (donc prefixe
VRAI) est jouee par l'adversaire et apparait cote ennemi. L'etage 3 exerce EXACTEMENT ce regime :
sans lui, ces tests seraient verts sur un chemin que rien ne parcourt.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[2]

DECLENCHEUR = {
    "chemins": (
        # Les quatre etages du transport, de la derivation au juge.
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/noncomparable/early_warning_override.py",
        "scripts/python/engine/services/ability_range.py",
        "scripts/python/engine/services/ability_caster_gates.py",
        # La source du fait : `Scene.moved_by_id` et son alimentation.
        "scripts/python/engine/playbook/scene.py",
        # Le mirror d'enum dont depend la lecture du flag cote OFFLINE.
        "scripts/python/engine/entities/unit_flag.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Perimetre BORNE aux quatre etages du transport PLUS ses deux sources. `scene.py` y est "
        "parce que le tri-etat de `has_moved` y est produit : s'il y devenait un `False` par "
        "defaut, la table d'ici se remplirait de mesures fabriquees et l'etage 2 resterait vert. "
        "`unit_flag.py` y est parce que `Moved` doit rester l'index 0 : une renumerotation cote "
        "build changerait le fait sans changer une ligne des quatre etages."),
}


def _nc(**kw):
    from engine.playbook.noncomparable._base import NCContext

    base = dict(uid=7, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                hp_cur_by_id={}, units=[], obs_units=[])
    base.update(kw)
    return NCContext(**base)


class _Scene:
    """TRI-ETAT fidele a `engine.playbook.scene.Scene.has_moved` : `None` = non mesure."""

    def __init__(self, moved_by_id=None):
        self.moved_by_id = moved_by_id or {}

    def has_moved(self, uid):
        return self.moved_by_id.get(uid)


# =================================================================================================
# ETAGE 1 -- la DERIVATION par position preserve le tri-etat
# =================================================================================================

def test_etage1_une_unite_NON_MESUREE_est_ABSENTE_de_la_table():
    """Le piege central : inscrire `False` pour une unite dont le capteur n'a rien dit ferait lire
    << elle n'a pas bouge >>, donc ACCEPTER un caster que le natif refuse. L'absence est la seule
    ecriture honnete -- le consommateur lit alors `None`."""
    from engine.playbook.noncomparable._base import has_moved_by_pos

    obs = [{"squadId": 1, "col": 0, "row": 0, "isDead": False},
           {"squadId": 2, "col": 1, "row": 0, "isDead": False},
           {"squadId": 3, "col": 2, "row": 0, "isDead": False}]
    t = has_moved_by_pos(_nc(obs_units=obs, scene=_Scene({1: True, 2: False})))
    assert t == {(0, 0): True, (1, 0): False}
    assert (2, 0) not in t, "l'unite 3 n'est PAS mesuree : elle ne doit pas entrer sous `False`"


def test_etage1_sans_scene_la_table_est_VIDE():
    """Statu quo EXACT d'avant le transport : aucune position ne porte de verdict."""
    from engine.playbook.noncomparable._base import has_moved_by_pos

    obs = [{"squadId": 1, "col": 0, "row": 0, "isDead": False}]
    assert has_moved_by_pos(_nc(obs_units=obs)) == {}


def test_etage1_les_depouilles_sont_filtrees():
    """Meme filtre qu'`occupant_team_by_pos`, meme raison : une depouille ne remplit plus sa tuile
    (`TileContentComponent$$IsFilled` est le premier gate de `GetUnit`)."""
    from engine.playbook.noncomparable._base import has_moved_by_pos

    obs = [{"squadId": 1, "col": 0, "row": 0, "isDead": True},
           {"squadId": 2, "col": 1, "row": 0, "isDead": False}]
    assert has_moved_by_pos(_nc(obs_units=obs, scene=_Scene({1: True, 2: True}))) == {(1, 0): True}


def test_etage1_la_cle_est_le_squadId():
    """⚠ `combatSnapshot.units[].entityId` EST le `squadId` d'`observeBattle`. Un appariement par
    `entityId` d'`observeBattle` lirait `None` sur TOUTES les unites et rendrait une table vide
    qui se lirait comme un capteur muet -- le faux negatif que `attack_query.py` documente."""
    from engine.playbook.noncomparable._base import has_moved_by_pos

    obs = [{"squadId": 42, "entityId": 999, "col": 3, "row": 3, "isDead": False}]
    assert has_moved_by_pos(_nc(obs_units=obs, scene=_Scene({42: True}))) == {(3, 3): True}
    assert has_moved_by_pos(_nc(obs_units=obs, scene=_Scene({999: True}))) == {}


# =================================================================================================
# ETAGE 2 -- le JUGE : la clause 1, son prefixe, et le tri-etat
# =================================================================================================

def _regle_caster_has_not_moved() -> int:
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    return int(TR.CasterHasNotMoved)


def _ability_avec_le_bit() -> int:
    """Une ability dont le masque porte REELLEMENT `CasterHasNotMoved` -- DERIVEE, jamais choisie
    de memoire : un id fige deviendrait faux au premier re-port de masque, et le test resterait
    vert en n'exercant plus rien."""
    from engine.runner.abilities import targeting as TGT
    from engine.playbook.noncomparable import PLAYBOOKS

    bit = _regle_caster_has_not_moved()
    for aid in sorted(PLAYBOOKS):
        opts = TGT.targeting_options_for(int(aid))
        if opts is not None and int(getattr(opts, "rules", 0) or 0) & bit:
            return int(aid)
    pytest.skip("aucune ability du registre ne porte `CasterHasNotMoved` -- gisement VIDE")
    raise AssertionError                                      # pragma: no cover


def test_etage2_la_clause_refuse_quand_les_DEUX_termes_sont_mesures_vrais():
    from engine.services import ability_caster_gates as ACG

    aid = _ability_avec_le_bit()
    sub = ACG.CasterSubstrate(is_turn_of_unit=True, has_moved=True)
    assert ACG.invalid_caster_reason(aid, sub) == _regle_caster_has_not_moved()


def test_etage2_un_terme_NON_MESURE_ne_refuse_JAMAIS():
    from engine.services import ability_caster_gates as ACG

    aid = _ability_avec_le_bit()
    assert ACG.invalid_caster_reason(aid, ACG.CasterSubstrate(is_turn_of_unit=True,
                                                              has_moved=None)) == 0
    assert ACG.invalid_caster_reason(aid, ACG.CasterSubstrate(is_turn_of_unit=True,
                                                              has_moved=False)) == 0


def test_etage2_le_PREFIXE_garde_la_clause():
    """`if (battleQuery.IsTurnOfUnit(caster) && (rules & 0x10))` -- sans le prefixe, le natif ne
    lit meme pas `DidMove`. Omettre ce garde faisait refuser 11 paires sur 42 que le natif ACCEPTE
    (#447-r1-r1)."""
    from engine.services import ability_caster_gates as ACG

    aid = _ability_avec_le_bit()
    for prefixe in (False, None):
        sub = ACG.CasterSubstrate(is_turn_of_unit=prefixe, has_moved=True)
        assert ACG.invalid_caster_reason(aid, sub) == 0, prefixe


def test_etage2_le_substrat_vide_reste_le_statu_quo():
    """Un `CasterSubstrate()` entierement non mesure = l'etat d'avant la tranche, et il est FROZEN."""
    from engine.services import ability_caster_gates as ACG

    sub = ACG.CasterSubstrate()
    assert all(getattr(sub, f.name) is None for f in dataclasses.fields(sub))
    with pytest.raises(dataclasses.FrozenInstanceError):
        sub.has_moved = True                                  # type: ignore[misc]


# =================================================================================================
# ETAGE 3 -- le TRANSPORT est REELLEMENT parcouru (contre le faux vert d'un canal mort)
# =================================================================================================

def test_etage3_ability_range_relaie_has_moved_jusqu_au_substrat():
    """CRAN CENTRAL. Un canal cable mais jamais relaye laisserait tous les tests ci-dessus verts
    en ne mesurant RIEN -- c'est exactement le vice d'un << transport mort >>. On SUBSTITUE
    `CasterSubstrate` pour capturer ce que le foyer lui passe VRAIMENT."""
    from engine.services import ability_caster_gates as ACG
    from engine.services import ability_range as AR

    vus = []
    original = ACG.CasterSubstrate

    def espion(**kw):
        vus.append(kw.get("has_moved"))
        return original(**kw)

    ACG.CasterSubstrate = espion                              # type: ignore[assignment]
    AR._REACH_CACHE.clear()
    try:
        AR.is_tile_in_range_of_any_ability((0, 0), (1, 0), "orksNob", has_moved=True)
    finally:
        ACG.CasterSubstrate = original                        # type: ignore[assignment]
        AR._REACH_CACHE.clear()
    assert vus, "`is_tile_in_range_of_any_ability` n'a construit AUCUN substrat -- test vacant"
    assert vus[0] is True, "le canal `has_moved` n'atteint PAS `CasterSubstrate`"


def test_etage3_early_warning_override_derive_ET_relaie_le_canal():
    """Le seul appelant de PRODUCTION. On verifie les deux moities separement : qu'il DERIVE la
    table (`has_moved_by_pos`) et qu'il la RELAIE a `utility_at`."""
    import inspect

    from engine.playbook.noncomparable import early_warning_override as EWO

    src = inspect.getsource(EWO.EarlyWarningOverridePlaybook.generate_candidates)
    assert "has_moved_by_pos(" in src, "la table n'est pas DERIVEE"
    params = inspect.signature(EWO.EarlyWarningOverridePlaybook.utility_at).parameters
    assert "has_moved_by_pos_" in params, "`utility_at` ne recoit pas la table"
    corps = inspect.getsource(EWO.EarlyWarningOverridePlaybook.utility_at)
    assert "has_moved=" in corps, "la table n'est pas RELAYEE a `is_tile_in_range_of_any_ability`"


def test_etage3_le_regime_ou_le_terme_MORD_est_le_controle_mental():
    """LE GISEMENT, EXERCE. Le prefixe est `playerId == currentPlayer`, PAS `teamId` : une unite
    qui NOUS appartient mais que l'adversaire controle porte encore NOTRE `playerId`, donc pendant
    NOTRE tour son prefixe est VRAI -- et c'est la, et seulement la, que `has_moved` peut refuser.
    Ce test EXHIBE la configuration au lieu de la decrire."""
    from engine.playbook.noncomparable._base import has_moved_by_pos, is_turn_of_unit_by_pos
    from engine.services import ability_caster_gates as ACG

    # u5 : `playerId` = 11 (NOUS) mais `teamId` = 2 (le camp adverse) == controle mental.
    obs = [{"squadId": 5, "playerId": 11, "teamId": 2, "col": 4, "row": 4, "isDead": False}]
    ctx = _nc(obs_units=obs, current_player=11, scene=_Scene({5: True}))
    prefixe = is_turn_of_unit_by_pos(ctx)
    moved = has_moved_by_pos(ctx)
    assert prefixe[(4, 4)] is True, "sans ce prefixe VRAI le gisement serait vide par construction"
    assert moved[(4, 4)] is True

    aid = _ability_avec_le_bit()
    sub = ACG.CasterSubstrate(is_turn_of_unit=prefixe[(4, 4)], has_moved=moved[(4, 4)])
    assert ACG.invalid_caster_reason(aid, sub) == _regle_caster_has_not_moved()

    # CONTRE-EPREUVE : le meme montage sans controle mental (playerId de l'adversaire) rend le
    # prefixe FAUX, donc la clause inerte. Sans ce bras, le test ci-dessus ne prouverait pas que
    # c'est bien le controle mental qui ouvre le gisement.
    obs_normal = [{"squadId": 5, "playerId": 12, "teamId": 2, "col": 4, "row": 4, "isDead": False}]
    ctx2 = _nc(obs_units=obs_normal, current_player=11, scene=_Scene({5: True}))
    assert is_turn_of_unit_by_pos(ctx2)[(4, 4)] is False
    sub2 = ACG.CasterSubstrate(is_turn_of_unit=False, has_moved=True)
    assert ACG.invalid_caster_reason(aid, sub2) == 0


def test_etage3_le_flag_natif_reste_l_index_ZERO():
    """`UnitFlag.Moved = 0`, LU dans `frida/enums.tsv`. Une renumerotation cote build changerait le
    fait sans changer une ligne du transport -- `probe_313` garde la bijection du mirror, ce cran
    garde la valeur que le port LIT."""
    from engine.entities.unit_flag import UnitFlag

    assert int(UnitFlag.Moved) == 0
