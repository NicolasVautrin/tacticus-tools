"""#572 -- `UnbreakableDuty` (1061, `templAncient`) : le CAST, confronte au natif.

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
Quatre questions BINAIRES, et aucune n'est deductible des trois autres :

  1. Le GATE des deux morts SEPARE-t-il bien deux regimes ? Un port qui poserait les cinq
     mecaniques inconditionnellement passerait le bras OUVERT sans qu'on le voie. Le bras FERME
     est ce qui rend le gate ATTRIBUABLE -- et il exige que le cast ne pose RIEN d'autre que
     l'aura.
  2. QUI porte l'aura ? Le natif la pose sur `Owner@DSLSelectors+0x30` -- UNE entite-effet, sur le
     CASTER -- et la PROJETTE par le `CreateTargetSelector` de l'effet. Un port qui la
     materialiserait sur chaque beneficiaire (le patron de `SereneUnifierSenseOfStone`, qui est
     structurellement JUMEAU) mettrait l'effet dans la liste des amis. Ce n'est pas ce que fait
     le natif.
  3. Le SOIN mord-il ? `ChangeStat(Owner, Position(Health, Current), mode 2 = Add, extraHp)` monte
     les PV COURANTS. C'est le canal ou le port pouvait ecrire dans `ctx.stats[5]` -- que RIEN ne
     relit pour les PV -- et perdre le soin SANS ERREUR.
  4. Le degat de l'attaque LIBRE est-il bit-exact ? C'est un SCALAIRE : il ne peut concorder que
     si le `+extraDmg` (pose AVANT elle par l'ordre `op_Addition`), le tirage RNG et le resolveur
     d'arme concordent tous les trois.

Le pas `aura` mesure l'OBSERVABLE de la reduction -- le DEGAT recu par un ami a portee -- avec son
CONTRE-MODELE (le meme coup, port avec l'instance 1097 consommee) et son bras de CONTROLE (le meme
banc, ami a 3 hexes) : sans eux, une concordance ne serait pas attribuable a l'aura.

La face DECISION (`UnbreakableDutyPlaybook`) n'est PAS portee -- residu NOMME `#572-r2`, hors de
ce fichier.

⚠ Ce fichier monte QUATRE runners (un par bras) et les dispose. Aucun state-file partage.

ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE et non feuille a feuille : le montage passe par le
        # visiteur de message, donc par le registre d'abilities, le vocabulaire DSL, les
        # Operations d'effet, le modele de degat et le PRNG. Une liste choisie serait un faux
        # vert -- elle ne pourrait pas montrer le module qu'elle a oublie. Foyers vraiment
        # load-bearing, pour la relecture humaine : `abilities/blacktemplars.py` (l'arbre),
        # `entities/effects/loki/unbreakable_duty.py` (les trois classes d'effet),
        # `entities/selectors/units.py` (`units_with_traits`, `ValidNormalAttackTargets`),
        # `runner/abilities/behaviours/stats.py` (la branche HEALTH du `ChangeStat`),
        # `runner/damage_model.py` (le canal AURA defenseur), `handler.py` + `attack_type.py` +
        # `targeting.py` (les registres).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest importe une vingtaine de probes plus
        # `hexgeo` / `board`, et CE fichier consomme `probe_572_unbreakable_duty` (qui monte les
        # runners), `probe_112_darkangels` et `probe_462_r4b_r1_terminator_commanded_attack`.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1061 UnbreakableDuty` : l'oracle est le jeu "
              "lui-meme (quels effets sur QUEL porteur, le gain de PV courants, le degat de "
              "l'attaque libre et celui encaisse sous l'aura). Un changement de build peut faire "
              "changer ce fichier d'avis sans qu'une ligne du port bouge.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

from engine.entities.effect_type import EffectType                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402

UNBREAKABLE_DUTY = int(ActiveAbilityType.UnbreakableDuty)          # 1061
DR = int(EffectType.UnbreakableDuty_DamageReduction)               # 1097
HEALTH = int(EffectType.UnbreakableDuty_Health)                    # 1251
DAMAGE = int(EffectType.UnbreakableDuty_Damage)                    # 1256


@pytest.fixture(scope="module")
def ferme():
    """Gate FERME : aucun allie mort. UN cast, les DEUX faces, MEME etat de depart."""
    import probe_572_unbreakable_duty as P
    from rl_collect_batch import _resolve_session
    return P.measure_cast(_resolve_session(), gate_open=False)


@pytest.fixture(scope="module")
def ouvert():
    """Gate OUVERT : DEUX allies `Imperial`+`Hero` tues avant le cast."""
    import probe_572_unbreakable_duty as P
    from rl_collect_batch import _resolve_session
    return P.measure_cast(_resolve_session(), gate_open=True)


@pytest.fixture(scope="module")
def aura():
    """Les DEUX bras de l'aura : ami A PORTEE (d = 1) et ami HORS PORTEE (d = 3)."""
    import probe_572_unbreakable_duty as P
    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    return {"pres": P.measure_aura(sid, ally_far=False),
            "loin": P.measure_aura(sid, ally_far=True)}


# ================================================================================================
# 1. LE GATE separe bien deux regimes
# ================================================================================================
def test_gate_FERME_le_cast_ne_pose_QUE_l_aura(ferme):
    """i2 : l'aura est INCONDITIONNELLE ; les quatre autres mecaniques sont sous le
    << If 2 or more friendly Imperial Characters are dead >>."""
    assert ferme["nat_caster"] == [DR], ferme["nat_caster"]
    assert ferme["port_caster"] == [DR], ferme["port_caster"]
    assert ferme["port_result"]["gate_passed"] is False


def test_gate_FERME_ni_soin_ni_attaque(ferme):
    """CE QUI REND LE GATE ATTRIBUABLE : un port inconditionnel passerait le bras OUVERT."""
    assert ferme["nat_gain"] == 0 and ferme["port_gain"] == 0
    assert not ferme["nat_free_dmg"] and not ferme["port_free_dmg"]


def test_gate_OUVERT_les_trois_effets(ouvert):
    assert ouvert["nat_caster"] == sorted([DR, HEALTH, DAMAGE]), ouvert["nat_caster"]
    assert ouvert["port_caster"] == sorted([DR, HEALTH, DAMAGE]), ouvert["port_caster"]
    assert ouvert["port_result"]["gate_passed"] is True


def test_les_deux_self_buffs_sont_PERMANENTS_des_deux_cotes(ouvert):
    """`turns = null` natif -> `DefaultAmountOfRounds` -> aucun compte a rebours. Le canal live
    publie `remaining = 0`, le port `None` : c'est le MEME fait (`EffectFactory` mappe `0 -> None`
    parce qu'un `0` capte signifie << pas de compte a rebours >>)."""
    for et in (HEALTH, DAMAGE):
        assert ouvert["nat_caster_rem"].get(et) in (0, None), ouvert["nat_caster_rem"]
        assert ouvert["port_caster_rem"].get(et) is None, ouvert["port_caster_rem"]
    # L'aura, elle, est CHRONOMETREE (`TurnsFromRounds(1)`) -- et la valeur est la MEME des deux cotes.
    assert ouvert["nat_caster_rem"][DR] == ouvert["port_caster_rem"][DR]
    assert int(ouvert["nat_caster_rem"][DR]) > 0


# ================================================================================================
# 2. QUI porte l'aura : le CASTER, jamais les beneficiaires
# ================================================================================================
def test_l_aura_vit_sur_le_PORTEUR_et_n_est_PAS_materialisee_sur_l_ami(ferme, ouvert):
    """Le natif cible `Owner@+0x30` : UNE entite-effet. La projection est le
    `CreateTargetSelector` de l'EFFET, pas une pose par beneficiaire (contraste
    `SereneUnifierSenseOfStone`, dont le POSEUR passe le selecteur a l'`AddEffect`)."""
    for cas in (ferme, ouvert):
        assert cas["d_ally"] <= 2, "l'ami doit etre DANS la portee de l'aura (d=%s)" % cas["d_ally"]
        assert cas["nat_ally"] == [], cas["nat_ally"]
        assert cas["port_ally"] == [], cas["port_ally"]


# ================================================================================================
# 3. Le SOIN (`ChangeStat` mode Add sur la stat FILL-UP Health)
# ================================================================================================
def test_le_gain_de_PV_courants_vaut_extraHp_des_deux_cotes(ouvert):
    """Ce canal etait celui ou le port pouvait perdre le soin SANS ERREUR : `apply_change_stat`
    ecrit dans `ctx.stats[5]`, que rien ne relit pour les PV."""
    attendu = ouvert["expected"]["extraHp"]
    assert attendu > 0
    assert ouvert["nat_gain"] == attendu, (ouvert["nat_gain"], attendu)
    assert ouvert["port_gain"] == attendu, (ouvert["port_gain"], attendu)


# ================================================================================================
# 4. L'attaque LIBRE -- un SCALAIRE
# ================================================================================================
def test_le_degat_de_l_attaque_libre_est_bit_exact(ouvert):
    """Elle ne peut concorder que si le `+extraDmg` (pose AVANT elle), le tirage RNG et le
    resolveur d'arme concordent tous les trois."""
    assert ouvert["nat_free_dmg"], "l'attaque libre n'a pas eu lieu cote NATIF"
    assert ouvert["port_free_dmg"], "l'attaque libre n'a pas eu lieu cote PORT"
    assert int(ouvert["port_free_dmg"]) == int(ouvert["nat_free_dmg"]), (
        "natif=%s port=%s" % (ouvert["nat_free_dmg"], ouvert["port_free_dmg"]))


def test_l_attaque_libre_vise_un_ennemi_ADJACENT(ouvert):
    """`AdjacentEnemies(Caster@+0x48, unique, selectionType)` -- surcharge a 3 arguments, AUCUN
    rayon, donc ring-1 : << an adjacent enemy >> de l'i2."""
    assert ouvert["d_foe"] == 1, ouvert["d_foe"]


# ================================================================================================
# 5. L'OBSERVABLE de l'aura : le DEGAT, avec contre-modele et bras de controle
# ================================================================================================
def test_l_ami_a_portee_encaisse_moins_bit_exact(aura):
    m = aura["pres"]
    assert m["nat_dmg"] is not None and m["port_dmg"] is not None
    assert int(m["port_dmg"]) == int(m["nat_dmg"]), (
        "degat RECU par l'ami : natif=%s port=%s" % (m["nat_dmg"], m["port_dmg"]))


def test_le_contre_modele_SANS_l_aura_rend_un_nombre_DIFFERENT(aura):
    """Sans lui, la concordance ci-dessus ne serait pas attribuable a la reduction."""
    m = aura["pres"]
    assert m["port_sans"] is not None
    assert int(m["port_sans"]) != int(m["port_dmg"]), (
        "le port rend la MEME valeur SANS 1097 (%s) -- l'aura est INERTE" % m["port_sans"])
    assert int(m["port_sans"]) > int(m["port_dmg"]), "l'aura doit REDUIRE le degat"


def test_hors_de_portee_l_aura_ne_mord_PAS(aura):
    """BRAS DE CONTROLE : le MEME banc, ami a `range + 1` hexes. C'est ce qui rend la geometrie
    (`SurroundingFriends(Owner, ConfigConst(range) = 2)`) attribuable, et pas un bonus global."""
    c = aura["loin"]
    assert c["d_ally"] > c["expected"]["range"], (c["d_ally"], c["expected"]["range"])
    assert c["nat_dmg"] is not None and c["port_dmg"] is not None
    assert int(c["port_dmg"]) == int(c["nat_dmg"]), (c["nat_dmg"], c["port_dmg"])
    assert int(c["port_sans"]) == int(c["port_dmg"]), (
        "l'aura mord a %d hexes alors que `range` vaut %d (sans=%s avec=%s)"
        % (c["d_ally"], c["expected"]["range"], c["port_sans"], c["port_dmg"]))


# ------------------------------------------------------------ face DECISION (#572-r2)
# `UnbreakableDutyPlaybook` -- portee par #572-r2, que ce fichier declarait NON portee.
# FOYER UNIQUE du montage et des criteres : `probe_572r2_unbreakable_duty_decision.campagne`.

@pytest.fixture(scope="module")
def decision572():
    import os as _os
    import probe_572r2_unbreakable_duty_decision as D572
    try:
        sid = D572._resolve_session()
    except Exception as e:
        pytest.skip("host indisponible (%s)" % (e,))
    sf = _os.path.join(_os.environ.get("TEMP", "."), "t572d_%s.json" % _os.getpid())
    recs = D572.campagne(sid, sf, 57202, D572.BOARD)
    if not recs:
        pytest.skip("build KO -- session/host indisponible")
    return {rec["tag"]: rec for rec in recs}


def test_572r2_le_gate_BLOQUE_quand_GetUseProbability_vaut_zero(decision572):
    """`UnbreakableDutyPlaybook$$GetUseProbability` rend `10 * |allies dans le disque range=2|`, et
    `BasePlaybook$$ShouldEvaluate` refuse sur `prob <= 0`. Caster ISOLE, aucun mort : le natif
    n'evalue PAS 1061 sur AUCUN des tirages -- alors qu'un ennemi est a portee."""
    rec = decision572["isole"]
    assert rec["pct"] == 0, "le port mesure %d%% : le montage n'isole pas le caster" % rec["pct"]
    assert rec["casts"] == 0, (
        "le natif a caste 1061 %d fois sur %d alors que la probabilite est NULLE"
        % (rec["casts"], rec["tirages"]))
    assert rec["port"].get("ability") != 1061


def test_572r2_le_gate_LAISSE_PASSER_des_qu_un_allie_est_a_portee(decision572):
    """QUATRE allies dans le disque -> `p = 40`, donc `0 < prob < 1` : le natif TIRE. Le critere est
    donc l'EXISTENCE (>= 1 cast sur N), pas la frequence -- le regime `prob >= 1` exigerait DIX
    allies, et le maximum de spawns cote joueur sur les boards du depot est SEPT.

    Cote port le moteur est deterministe : il propose des que `p > 0` (ecart de FREQUENCE assume,
    meme statut que `BlackRage`/`ItItches`). Ce qui doit concorder, c'est la CIBLE."""
    rec = decision572["entoure"]
    assert rec["pct"] == 40, "le port mesure %d%% au lieu de 40 : montage different" % rec["pct"]
    assert rec["casts"] >= 1, (
        "le natif n'a JAMAIS caste 1061 sur %d tirages : le gate n'est pas vu laisser passer"
        % rec["tirages"])
    assert rec["port"].get("ability") == 1061
    assert rec["port"].get("target") == rec["natif_target"], (
        "cible divergente : natif u%s, port u%s" % (rec["natif_target"], rec["port"].get("target")))


def test_572r2_la_cible_est_un_ALLIE_et_le_plan_natif_ne_la_porte_PAS(decision572):
    """Le masque de 1061 est `0x8400` = `TargetIsFriendly | CasterIsPossibleTarget` : la cible est
    ALLIEE. Or `computeAttackPlans` n'enumere QUE des ennemis -- un port branche sur
    `ctx.plan["evals"]` serait donc MUET, sans erreur. Ce test fige la voie employee
    (`abilityTargets.fromHere`) en exigeant qu'un candidat SORTE du playbook."""
    rec = decision572["entoure"]
    assert rec["candidats"], (
        "le playbook ne rend AUCUN candidat alors que le natif caste : la voie d'enumeration est "
        "muette")
    assert rec["candidats"][0] == rec["natif_target"]


def test_572r2_la_contre_epreuve_sans_playbook_MORD(decision572):
    """Le port d'AVANT #572-r2 (registre ampute de 1061, donc fallback Comparable) doit DIVERGER
    sur `entoure`. Sur `isole` les deux s'abstiennent : l'accord y est REEL mais non attribuable,
    et c'est pourquoi la morsure se lit ici."""
    rec = decision572["entoure"]
    assert rec["sans_playbook"].get("ability") != 1061, (
        "le fallback Comparable proposait DEJA 1061 : ce banc n'attribue rien au playbook")
