"""#549 -- `HolyDuel` (1050, `templChampion`) : le CAST, confronte au natif.

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
Trois questions BINAIRES, et aucune n'est deductible des deux autres :

  1. QUI porte QUOI ? Le natif pose 1091 sur la CIBLE, puis
     `HolyDuel_TauntEffect$$ApplyInternal` en derive QUATRE sous-effets dont TROIS vivent sur
     l'entite BONDEE (le champion). Un port qui poserait tout sur le porteur du parent -- le seul
     comportement que le foyer `_spawn_sub_effects` savait faire avant cette tranche -- laisserait
     le champion SANS `Taunted`, SANS `HolyDuel_ExtraDmg` et SANS `HolyDuel_DmgReduction`.
  2. Vers QUI pointe chaque bond ? Ils sont CROISES (celui de la cible designe le champion, ceux du
     champion designent la cible). C'est ce qui rend le taunt opposable au ciblage
     (`ForcedAttackTargetsComponent`, #436) DANS LES DEUX SENS.
  3. Le DEGAT du cast porte-t-il DEJA le `+extraDmg` ? L'arbre pose le bond AVANT l'attaque
     (`op_BitwiseAnd` evalue a gauche d'abord), donc oui -- et c'est un SCALAIRE, donc un port qui
     poserait bien les effets mais ne les lirait pas se verrait ici et nulle part ailleurs.
     ⚠ C'est exactement ce qui est arrive pendant la mise au point : effets bit-identiques des deux
     cotes, degat natif 6140 contre port 3678. La cause n'etait PAS dans `HolyDuel` mais un etage
     plus bas -- `damage_model.attacker_modifiers` ne threadait pas `tgt_id`, donc le gate
     `AreEqual(Target@0x60, BondedEntityFromEffect(Effect))` de 1092 ne pouvait pas se fermer.
     Decomposer par etage l'a montre ; fitter un scalaire l'aurait masque.

La face DECISION (`playbook/noncomparable/holy_duel.py`) preexiste a ce port et n'est PAS l'objet
de ce fichier.

⚠ Ce fichier monte UN runner et le dispose. Il ne partage aucun state-file avec un autre module.

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
        # `entities/effects/loki/holy_duel.py` (les trois classes d'effet),
        # `entities/effects/base.py` (`SubEffectSpec.on_bonded_entity`),
        # `runner/operations/effects.py` (`_spawn_sub_effects` : porteur/bond croises, recursion,
        # etat d'ability propage), `runner/damage_model.py` (le threading de `tgt_id`),
        # `handler.py` + `attack_type.py` + `targeting.py` (les registres).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest importe une vingtaine de probes plus
        # `hexgeo` / `engine_validate`, et CE fichier consomme `probe_549_holy_duel` (qui monte le
        # runner) ainsi que le montage partage de `probe_462_r4b_r1_r1_r1_r1_b_bond_range`.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1050 HolyDuel` : l'oracle est le jeu lui-meme "
              "(quels effets sur QUEL porteur, vers QUI pointe chaque bond, et le degat de "
              "l'attaque normale dispatchee par le cast). Un changement de build peut donc faire "
              "changer ce fichier d'avis sans qu'une ligne du port bouge.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType               # noqa: E402

HOLY_DUEL = int(ActiveAbilityType.HolyDuel)                    # 1050
TAUNT = int(EffectType.HolyDuel_Taunt)                         # 1091
EXTRA_DMG = int(EffectType.HolyDuel_ExtraDmg)                  # 1092
DMG_REDUCTION = int(EffectType.HolyDuel_DmgReduction)          # 1093
TAUNTED_FAMILY = [25, 26, 27, 1237]


@pytest.fixture(scope="module")
def cast():
    """UN cast, les DEUX faces, sur le MEME etat de depart (capture avant le cast natif)."""
    import probe_549_holy_duel as P
    from rl_collect_batch import _resolve_session
    return P.measure_cast(_resolve_session())


# ================================================================================================
# 1. QUI porte QUOI
# ================================================================================================
def test_la_cible_porte_le_bond_et_le_composite_taunted(cast):
    """1091 sur la CIBLE + le composite 27 et ses trois enfants, des deux cotes."""
    for face in ("nat_victim", "port_victim"):
        got = set(cast[face])
        assert TAUNT in got, "%s : 1091 absent (%s)" % (face, sorted(got))
        assert set(TAUNTED_FAMILY) <= got, "%s : famille Taunted incomplete (%s)" % (face, sorted(got))


def test_le_champion_porte_le_taunt_symetrique_et_les_deux_modificateurs(cast):
    """LE point du cas : trois des quatre sous-effets vivent sur l'entite BONDEE.

    i2 : << Brother Jaeger deals +582 Damage and takes -364 Damage from the target while it's
    Taunted by him. Brother Jaeger is also Taunted by the target. >>"""
    for face in ("nat_champ", "port_champ"):
        got = set(cast[face])
        assert set(TAUNTED_FAMILY) <= got, (
            "%s : le CHAMPION n'est pas taunte en retour (%s)" % (face, sorted(got)))
        assert EXTRA_DMG in got and DMG_REDUCTION in got, (
            "%s : le champion n'a pas ses deux modificateurs de duel (%s)" % (face, sorted(got)))
    assert TAUNT not in set(cast["port_champ"]), (
        "le parent 1091 ne doit vivre QUE sur la cible")


def test_les_deux_faces_posent_exactement_la_meme_famille(cast):
    """Aucun effet EN PLUS ni EN MOINS, sur l'un ou l'autre porteur."""
    assert sorted(cast["port_victim"]) == sorted(cast["nat_victim"])
    assert sorted(cast["port_champ"]) == sorted(cast["nat_champ"])


# ================================================================================================
# 2. Les bonds sont CROISES -- et le taunt est opposable dans les DEUX sens
# ================================================================================================
def test_les_bonds_sont_croises(cast):
    """`b__0` passe `ctx.<+0x18>` (le bonde du parent) au builder de l'enfant pose sur le porteur ;
    `b__1`/`b__2`/`b__3` passent `ctx.<+0x20>.Id` (le porteur du parent) a ceux poses sur le bonde."""
    champ, victim = cast["champ"], cast["victim"]
    assert cast["port_bond_victim"].get(TAUNT) == champ
    assert cast["port_bond_victim"].get(27) == champ
    for et in (27, EXTRA_DMG, DMG_REDUCTION):
        assert cast["port_bond_champ"].get(et) == victim, (
            "effet %d du champion : bonded=%s attendu %s"
            % (et, cast["port_bond_champ"].get(et), victim))


def test_les_cibles_forcees_sont_croisees(cast):
    """`TauntedEffect$$ApplyInternal` ecrit `ForcedAttackTargetsComponent = [BondedEntityId]` sur
    CHAQUE porteur d'un 27 -- donc sur les deux duellistes, chacun contraint a l'autre."""
    assert cast["port_forced_victim"] == [cast["champ"]]
    assert cast["port_forced_champ"] == [cast["victim"]]


# ================================================================================================
# 3. Le DEGAT du cast porte deja le +extraDmg
# ================================================================================================
def test_le_degat_du_cast_est_bit_exact(cast):
    """L'attaque NORMALE dispatchee par `UseActiveAbility` mord AVEC le bonus, des ce coup."""
    assert cast["nat_dmg"] is not None and cast["port_dmg"] is not None, "degat non lisible"
    assert int(cast["port_dmg"]) == int(cast["nat_dmg"]), (
        "degat du cast : natif=%s port=%s (ecart %s)"
        % (cast["nat_dmg"], cast["port_dmg"], cast["nat_dmg"] - cast["port_dmg"]))


def test_l_accumulateur_attaquant_porte_l_additif_du_duel(cast):
    """CONTRE-EPREUVE DE L'ETAGE, pas du scalaire : la contribution de 1092 doit exister DANS
    `attackModifiers`, en `Addition` (`EffectBonus.ForAddition`), et valoir `extraDmg[level]` scale
    par le multiplicateur de rarete du champion.

    Sans elle le total pourrait coincider par compensation ; avec elle, l'etage est nomme."""
    adds = [d for d in cast["port_att_details"] if d.kind == "Addition"]
    assert adds, ("aucun `Addition` dans l'accumulateur ATTAQUANT -- le gate "
                  "`AreEqual(Target@0x60, BondedEntityFromEffect)` de 1092 ne se ferme pas "
                  "(details=%s)" % (cast["port_att_details"],))
    assert cast["expected_extra_dmg"] > 0
    assert any(int(a.value) == int(cast["expected_extra_dmg"]) for a in adds), (
        "additif du duel : attendu %s, obtenu %s"
        % (cast["expected_extra_dmg"], [a.value for a in adds]))


def test_l_additif_ne_mord_QUE_sur_le_duelliste(cast):
    """CONTROLE : le meme accumulateur, calcule contre une TIERCE unite, ne doit RIEN porter du
    duel. C'est ce qui rend le test precedent attribuable au gate `AreEqual`, et pas a un additif
    inconditionnel."""
    if cast["port_att_details_tierce"] is None:
        pytest.skip("aucune tierce unite dans ce montage")
    adds = [d for d in cast["port_att_details_tierce"] if d.kind == "Addition"]
    assert not adds, ("le +extraDmg du duel mord sur une TIERCE unite : le gate `AreEqual` est "
                      "inerte (%s)" % (adds,))


# ------------------------------------------------------------ face PREDICTION (#549-r1)
# Le `tgt_id` que #549 a threade cote PREDICTION n'avait PAS ete confronte a `aiPlaybookPredict`.
# FOYER UNIQUE du montage et des criteres : `probe_549r1_holy_duel_prediction.campagne`.

@pytest.fixture(scope="module")
def prediction549():
    import probe_549r1_holy_duel_prediction as P549
    try:
        sid = P549._resolve_session()
    except Exception as e:
        pytest.skip("host indisponible (%s)" % (e,))
    recs = P549.campagne(sid)
    if not recs:
        pytest.skip("build KO -- session/host indisponible")
    return {rec["tag"]: rec for rec in recs}


def test_549r1_la_prediction_du_duel_est_bit_exacte(prediction549):
    """Oracle = `aiPlaybookPredict` (= `<Ability>Playbook$$MakeDamagePredictions`, ce que le scorer
    de DECISION consomme), PAS le preview `aiPredict`. Le champion porte 1092 bonde a sa victime :
    le gate `AreEqual(Target@0x60, BondedEntityFromEffect(Effect@0x38))` se ferme et le `+extraDmg`
    entre dans l'accumulateur ATTAQUANT de la PREDICTION."""
    rec = prediction549["duel"]
    assert rec["natif"] and "min" in rec["natif"], (
        "l'oracle n'a rendu aucun event de degat : %r" % (rec["natif"],))
    assert (rec["port"]["min"], rec["port"]["max"]) == (rec["natif"]["min"], rec["natif"]["max"])


def test_549r1_le_CONTROLE_hors_duel_concorde_aussi(prediction549):
    """MEME paire, AVANT le cast : aucun duel, le gate est ferme des deux cotes. Sans ce bras, une
    concordance sur `duel` ne dirait pas si elle vient du duel ou du reste du chemin."""
    rec = prediction549["avant"]
    assert (rec["port"]["min"], rec["port"]["max"]) == (rec["natif"]["min"], rec["natif"]["max"])


def test_549r1_retirer_tgt_id_de_l_att_ctx_MORD_et_SEULEMENT_dans_le_duel(prediction549):
    """La contre-epreuve rejoue le port d'AVANT #549 (cle `tgt_id` retiree de l'`att_ctx`), et rien
    d'autre. Elle doit etre INERTE hors duel et MORDRE dans le duel -- c'est ce couple qui ATTRIBUE
    la concordance au threading, et pas a une compensation.

    ⚠ Le patch vise le binding LOCAL de `prediction/normal_attack.py` : ce module importe par
    `from ._shared import *`, donc substituer le module qui DEFINIT la fonction ne mordrait pas."""
    av, du = prediction549["avant"], prediction549["duel"]
    assert av["sans_tgt_id"] == av["port"], (
        "la contre-epreuve change quelque chose HORS duel (%r vs %r) : elle ne mesure pas le gate"
        % (av["sans_tgt_id"], av["port"]))
    assert du["sans_tgt_id"] != du["port"], (
        "retirer `tgt_id` ne change RIEN dans le duel : le `+extraDmg` n'entre pas par cette cle")
    assert du["sans_tgt_id"]["max"] < du["port"]["max"], (
        "la degradation d'avant #549 doit etre RESTRICTIVE (sous-estimation), pas l'inverse")
