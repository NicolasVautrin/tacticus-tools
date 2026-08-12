"""#985 -- gardes OFFLINE des deux dernieres faces DECISION portees (1068, 1160).

Un probe MESURE, un test GARDE. Ce fichier garde ce que la tranche a etabli, et surtout ce qui
se PERIME en silence : la refutation de `#970-r2` tient a ce que la config de l'active
`HeavyRailRifle` reste lisible et que le call-site reste inscrit au registre des formes de
moyenne. Si l'un des deux disparait, le port de 1160 se met a rendre `[]` sans erreur.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)


# ── etage 1 : les deux abilities sont INSCRITES, et par la voie attendue ──────────────────────
def test_1068_et_1160_sont_portees_par_le_registre_noncomparable():
    import decision_face_voies as DFV
    tables, att = DFV.voies_par_ability(), DFV.attestations()
    for aid, nom in ((1068, "SilentDeath"), (1160, "HeavyRailRifle")):
        etat, detail = DFV.etat(aid, nom, tables, att)
        assert etat == "PORTEE", "%s (%d) : etat %s (%s)" % (nom, aid, etat, detail)
        assert "PLAYBOOKS" in detail, (
            "%s doit etre portee par `noncomparable.PLAYBOOKS` (la route NonComparable), "
            "pas par %s" % (nom, detail))


def test_les_deux_playbooks_declarent_le_min_utility_et_la_priorite_du_natif():
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable._base import native_priority
    for aid in (1068, 1160):
        pb = PB.playbook_for(aid)
        assert pb is not None, "playbook %d absent du registre" % aid
        # `.cctor` des deux playbooks = `Fix64.FromInt(1)`.
        assert pb.MIN_UTILITY == 1.0, "%d : MIN_UTILITY %s" % (aid, pb.MIN_UTILITY)
        # Aucune des deux n'est dans `NATIVE_PRIORITY` -> tier `Normal` (0).
        assert pb.PRIORITY == native_priority(aid) == 0, "%d : PRIORITY %s" % (aid, pb.PRIORITY)


# ── etage 2 : le gate de 1068 -- le `- origin` du selecteur natif ─────────────────────────────
def test_1068_le_gate_exclut_la_cible_de_son_propre_voisinage():
    """`DSLSelectors$$AdjacentUnits` = `Units(AdjacentTiles(origin), ...) - origin`.

    Sans le `- origin`, la cible (qui EST un ennemi du caster) se compterait elle-meme et le gate
    serait TOUJOURS vrai. Ce test fixe la consequence observable : une cible SEULE ne passe pas."""
    from engine.playbook.noncomparable import NCContext
    from engine.playbook.noncomparable.silent_death import SilentDeathPlaybook

    cible = {"id": 79, "pos": {"col": 3, "row": 4}, "visualId": "ultraTitus"}
    allie = {"id": 81, "pos": {"col": 3, "row": 5}, "visualId": "ultraApothecary"}

    def _at(_uid, aid):
        return {"units": [{"abilities": [{"abilityId": aid,
                                          "targets": [{"kind": "unit", "targetId": 79}]}]}]}

    def _ctx(epos, units):
        return NCContext(uid=77, origin=(3, 3), reach_nc=[(3, 3)], epos=epos, fpos=[],
                         plan={}, hp_cur_by_id={}, ability_targets=_at, units=units)

    pb = SilentDeathPlaybook()
    # (a) la cible est SEULE : son unique voisin serait elle-meme -> le gate REFUSE.
    assert pb.generate_candidates(_ctx([(3, 4)], [cible])) == []
    # (b) un allie A ELLE est colle : le gate PASSE, utilite PLATE 1.
    got = pb.generate_candidates(_ctx([(3, 4), (3, 5)], [cible, allie]))
    assert got and got[0]["target"] == 79 and got[0]["pred"] == 1.0, got
    assert got[0]["to"] is None, "utilite position-INDEPENDANTE -> l'origine gagne au tie"


# ── etage 3 : la REFUTATION de #970-r2, rendue OPERATOIRE ─────────────────────────────────────
def test_1160_la_config_du_triggered_est_celle_de_l_active_et_elle_est_LISIBLE():
    """Le coeur de la refutation : `HeavyRailRifle_Attack` n'existe nulle part, et pourtant les
    entrees du port sont lisibles -- parce qu'elles vivent sur l'ACTIVE."""
    import gameconfig as GC
    assert GC.ability("HeavyRailRifle_Attack") is None, (
        "le triggered a acquis une entree propre : la refutation change de forme, RE-MESURER")
    act = GC.ability("HeavyRailRifle") or {}
    consts, vars_ = act.get("constants") or {}, act.get("variables") or {}
    # Les deux constantes LUES par `HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`
    # (`ConfigConst(0x4c)` / `ConfigConst(0xf)`), qui etablissent l'appariement.
    for n in ("dmgPctReduction", "extraDmgPct"):
        assert n in consts, "`%s` a disparu de la config de l'active -- l'appariement tombe" % n
    # Ce dont le port a besoin.
    for n in ("minDmg", "maxDmg"):
        assert n in vars_, "`%s` absent" % n
    for n in ("nrOfHits", "damageProfile"):
        assert n in consts, "`%s` absent" % n


def test_1160_l_appariement_des_deux_constantes_reste_UNIQUE():
    """L'etage qui rend l'argument non circulaire : si ces constantes devenaient banales, la
    concordance ne designerait plus `HeavyRailRifle` en particulier."""
    import gameconfig as GC
    toutes = GC._index()["abilities"]
    paire = [k for k, a in toutes.items()
             if all(n in ((a or {}).get("constants") or {})
                    for n in ("dmgPctReduction", "extraDmgPct"))]
    assert paire == ["HeavyRailRifle"], (
        "l'appariement n'est plus unique (%d porteuses : %s) -- la refutation de #970-r2 "
        "reposait sur son unicite" % (len(paire), paire))


def test_1160_le_call_site_est_inscrit_au_registre_des_formes_et_TRONQUE():
    """La ligne existait depuis #350-r3b SANS consommateur ; c'est ce module qui la consomme.
    Si elle disparaissait, `triggered_prediction_damage` leverait `KeyError` -- deliberement."""
    from engine.entities.abilities.triggered_ability import TRIGGERED_PREDICTION_AVERAGE_FORM
    from engine.playbook.noncomparable.heavy_rail_rifle import _CALL_SITE
    assert _CALL_SITE in TRIGGERED_PREDICTION_AVERAGE_FORM, _CALL_SITE
    getter, slot = TRIGGERED_PREDICTION_AVERAGE_FORM[_CALL_SITE]
    # slot 4 = `AAmountFormula$$CalculateAverage` sur un noeud `RandomAmount` = TRONCATURE.
    assert (getter, slot) == ("GetDamage", 4), (getter, slot)


def test_1160_les_entrees_du_port_sont_calculables():
    """La refutation est OPERATOIRE, pas seulement vraie : les trois entrees sortent non nulles."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.triggered_ability import triggered_prediction_damage
    from engine.playbook.noncomparable.heavy_rail_rifle import _ABILITY_NAME, _CALL_SITE

    cfg = AbilityConfiguration.from_gameconfig(_ABILITY_NAME, GC.ability(_ABILITY_NAME))
    assert cfg is not None
    dmg = triggered_prediction_damage(_ABILITY_NAME, 50, 100, _CALL_SITE)
    assert dmg is not None and dmg > 0, "degat du triggered non calculable : %r" % (dmg,)
    hits = cfg.get_variable_for_level("nrOfHits", 50, fallback_to_default=0)
    assert hits >= 1, "nrOfHits = %r" % (hits,)


# ── etage 4 : le discriminant MACHINE, sans lequel 1160 prendrait la mauvaise branche ─────────
def test_1160_le_discriminant_machine_ne_rate_aucune_MoW_du_pool():
    """`IsMachine` = `EntityType == 6`, sans canal cote DECISION. Le port le derive de
    `mythicAbilities`. Un faux NEGATIF ferait passer une Machine par la branche DEGAT."""
    from engine.playbook.noncomparable.heavy_rail_rifle import _is_machine
    import probe_985_six_faces as P
    for uid in P.MOW_POOL:
        assert _is_machine(uid) is True, "%s n'est pas vu comme une Machine" % uid
    for uid in ("eldarJainZar", "ultraTitus", "worldJakhal"):
        assert _is_machine(uid) is False, "%s vu a tort comme une Machine" % uid
    # Tri-etat : un visualId inconnu n'est PAS rabattu sur False.
    assert _is_machine("unitQuiNExistePas") is None
    assert _is_machine(None) is None


def test_1160_la_branche_machine_prend_la_face_deterministe_du_tirage():
    """`ShouldPreferMachine` = `pseudoRNG.NextBool(50)`. Le port prend `1` (branche fausse) et
    NE DOIT PAS rendre `int.MaxValue`, qui serait un choix arbitraire deguise en mesure."""
    from engine.playbook.noncomparable.heavy_rail_rifle import HeavyRailRiflePlaybook
    pb = HeavyRailRiflePlaybook()
    assert pb.MACHINE_PREFERRED_UTILITY == float(0x7fffffff)
    src = __import__("inspect").getsource(pb.generate_candidates)
    assert "u = 1.0" in src, (
        "la branche machine doit prendre la face DETERMINISTE du tirage (utilite 1)")
    assert "MACHINE_PREFERRED_UTILITY" not in src, (
        "le port ne doit pas CHOISIR la face aleatoire du tirage a 50 %")


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
