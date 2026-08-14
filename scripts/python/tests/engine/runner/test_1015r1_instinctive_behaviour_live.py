"""GARDE live du trait `InstinctiveBehaviour` (UnitTrait 2021) -- #1015-r1.

Le probe MESURE (`probe_1015r1_instinctive_behaviour.py`), ce test GARDE : il rejoue, sur UN
montage monte une fois, l'accord natif/port sur les DEUX faces du trait, dans DEUX regimes, avec un
TEMOIN NON NUL.

    tyranTyrantGuard, trait 2021 FORCE (`--unit-stat Traits=[...]`)
      regime LOIN (d = 3) : cible forcee POSEE, mouvement LIBRE
      regime PRES (d = 1) : cible forcee POSEE, mouvement BLOQUE
    ultraCalgar, MEME plateau, MEME contact, SANS le trait : ni cible forcee ni blocage

CE QUE CHAQUE EXIGENCE FERME :
  * l'ability derivee 1043 est INSCRITE par `TRAIT_TRIGGERS` -- sinon rien ne tourne ;
  * la cible forcee du port est CELLE du natif : le natif refuse toute AUTRE cible avec
    `TargetIsAllowedForCaster` (0x800000) et n'oppose PAS ce code a la cible que le port force.
    Sans une ligne REFUSEE, un accord ne distinguerait pas << le natif restreint comme nous >> de
    << personne ne restreint >> ;
  * le MOUVEMENT bascule dans le BON SENS entre les deux regimes, des DEUX cotes. Le regime LOIN
    est ce qui rend la mesure discriminante : un port qui bloquerait TOUT porteur du trait y
    serait pris ;
  * l'effet 1235 est ACTIF cote port en PRES et INACTIF en LOIN -- c'est le conjoint
    `Any(ForcedAttackTargets, IsInAttackOrAbilityRange(Owner, It))` de sa
    `CreateActiveCondition`, et rien d'autre ne le distingue ;
  * le TEMOIN reste libre dans les deux regimes -- un accord en regime degenere (tout le monde
    bloque) ne prouverait rien.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_1015r1_instinctive_behaviour as P
from engine.entities.effect_type import EffectType
from engine.runner.abilities.targeting_rule import TargetingRule as TR

BLOCK_MOVEMENT = int(EffectType.InstinctiveBehaviour_BlockMovement)     # 0x4d3 = 1235

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Il garde une chaine LIVE de bout en bout -- montage (`rl_duel build` + `--unit-stat Traits`),
#: seed (`snapshot`/`spawn`), registres (trait -> ability derivee, EffectType -> classe d'effet),
#: arbre DSL des DEUX faces, et les deux lecteurs (`get_only_targets`, `turnflow._can_move`). Un
#: declencheur trop LARGE est sain ; trop ETROIT est un faux vert.
DECLENCHEUR = {
    "chemins": (
        # LES DEUX SEULS chemins que la cascade DERIVEE ne couvre pas (`--proposer` : fermeture de
        # 687 modules, dont 686 deja derives par le foyer -- ne PAS les recopier, cf. #531).
        # Le probe porte tout le montage ET toute la mesure ; ce fichier ne fait que garder ses
        # verdicts. Son socle de harnais (`probe_247`) fournit `_build` / RPC / conduite.
        "scripts/python/probe_1015r1_instinctive_behaviour.py",
        "scripts/python/probe_247_splash_targeting.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "`build: True` parce que L'ORACLE EST LE NATIF : ce fichier confronte `aiMovableTiles` et "
        "`abilityReason` du jeu au port. Un changement de build peut retourner son verdict sans "
        "qu'aucun chemin du depot ne bouge -- c'est exactement le regime que ce champ existe pour "
        "declarer. Il lit aussi le gameconfig par `--unit-stat Traits=[...]` (la liste des traits "
        "du porteur y est reconstruite), et le mirror `UnitTrait` par ses ordinaux. "
        "Les deux chemins ENUMERES sont ceux que `--proposer` sort comme non derives ; tout le "
        "reste du port (les deux arbres DSL, `turnflow._can_move`, les registres trait->ability et "
        "EffectType->classe, `snapshot`/`spawn`, `targeting`) entre par la FERMETURE D'IMPORTS du "
        "probe -- verifie, pas suppose. `toujours: False` est donc un RESULTAT : le perimetre est "
        "derivable, et l'elargir a la main dupliquerait la cascade au lieu de la completer."
    ),
}


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe COMPLET et rend ses deux regimes. Le probe dispose SON runner (jamais ceux
    des autres) et rend 0 quand ses cinq crans passent."""
    import contextlib
    import io
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([])
    txt = buf.getvalue()
    print(txt[-4000:])
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


def test_le_registre_inscrit_l_ability_derivee(mesure):
    """`TRAIT_TRIGGERS['InstinctiveBehaviour']` -> `InstinctiveBehaviourUpdateTargetAbility` sur le
    porteur. Sans elle, tout le reste serait un accord par hasard."""
    for r in (mesure["loin"], mesure["pres"]):
        assert r["port_inscrite"], "%s : l'ability derivee n'est pas inscrite" % r["regime"]


def test_le_port_pose_une_cible_forcee_dans_les_deux_regimes(mesure):
    for r in (mesure["loin"], mesure["pres"]):
        assert r["port_only_targets"], "%s : aucune cible forcee cote port" % r["regime"]


def test_le_natif_refuse_toute_AUTRE_cible(mesure):
    """`TargetIsAllowedForCaster` (bit 23) sur une cible qui n'est PAS la forcee -- la preuve que
    le natif a, lui aussi, une liste non vide."""
    for r in (mesure["loin"], mesure["pres"]):
        assert r["autre"] is not None, "%s : pas de seconde cible a tester" % r["regime"]
        assert r["nat_reason_autre"] == int(TR.TargetIsAllowedForCaster), (
            "%s : le natif rend %s sur u%s au lieu de 0x800000"
            % (r["regime"], r["nat_reason_autre"], r["autre"]))


def test_la_cible_forcee_du_port_est_celle_du_natif(mesure):
    """Le natif n'oppose PAS `TargetIsAllowedForCaster` a la cible que le port force (il peut la
    refuser pour une AUTRE raison -- hors portee en regime LOIN, et c'est bien ce qu'il fait)."""
    for r in (mesure["loin"], mesure["pres"]):
        assert r["nat_reason_foe"] != int(TR.TargetIsAllowedForCaster), (
            "%s : le natif refuse aussi u%s -- les deux listes divergent" % (r["regime"], r["foe"]))
        assert int(r["port_only_targets"][0]) == int(r["foe"]), (
            "%s : port=%s natif force u%s" % (r["regime"], r["port_only_targets"], r["foe"]))


def test_le_mouvement_bascule_entre_les_deux_regimes(mesure):
    """LE test de la tranche cote MOUVEMENT : LOIN libre / PRES bloque, des DEUX cotes."""
    loin, pres = mesure["loin"], mesure["pres"]
    assert loin["nat_movable"] > 0, "LOIN : le natif rend 0 tuile -- regime non exerce"
    assert loin["port_can_move"] is not False, "LOIN : le port BLOQUE la ou le natif laisse bouger"
    assert pres["nat_movable"] == 0, (
        "PRES : le natif rend %d tuiles -- l'effet 1235 ne bloque pas" % pres["nat_movable"])
    assert pres["port_can_move"] is False, "PRES : le port laisse bouger la ou le natif bloque"


def test_l_effet_1235_n_est_actif_qu_en_regime_PRES(mesure):
    """Le conjoint `Any(ForcedAttackTargets, IsInAttackOrAbilityRange(Owner, It))`. Un effet actif
    dans les DEUX regimes signifierait que ce conjoint-la n'est pas evalue."""
    assert BLOCK_MOVEMENT in mesure["pres"]["port_effets_actifs"], (
        "PRES : 1235 inactif (%s)" % mesure["pres"]["port_effets_actifs"])
    assert BLOCK_MOVEMENT not in mesure["loin"]["port_effets_actifs"], (
        "LOIN : 1235 ACTIF alors que la cible n'est pas a portee (%s)"
        % mesure["loin"]["port_effets_actifs"])


def test_le_temoin_sans_le_trait_reste_libre(mesure):
    """TEMOIN NON NUL : sans le trait, ni cible forcee ni blocage -- dans les deux regimes."""
    for r in (mesure["loin"], mesure["pres"]):
        assert r.get("witness") is not None, "%s : temoin absent du plateau" % r["regime"]
        assert not r["wit_port_only_targets"], (
            "%s : le TEMOIN a des cibles forcees %s" % (r["regime"], r["wit_port_only_targets"]))
        assert r["wit_nat_movable"] > 0 and r["wit_port_can_move"] is not False, (
            "%s : le TEMOIN est bloque (nat=%s port=%s)"
            % (r["regime"], r["wit_nat_movable"], r["wit_port_can_move"]))


def test_verdict_global_du_probe(mesure):
    assert mesure["rc"] == 0, "le probe a rendu rc=%s" % mesure["rc"]
