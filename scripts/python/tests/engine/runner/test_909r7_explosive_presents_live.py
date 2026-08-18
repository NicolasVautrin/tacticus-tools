"""#909-r7 -- GARDE de la face DECISION de `1170 ExplosivePresents`, CONFRONTEE au natif.

D'OU VIENT CE FICHIER. Le residu #909-r1 visait << les 12 actives de kit dont le playbook natif
surcharge `MakeDamagePredictions` >>. Sa population est VIDE sur `master` -- mais son perimetre,
`kind == lineup`, ECARTE par construction les porteurs npc. Re-derive sur les **233** cles du dict
`active` d'`IdunBattle.AI.PlaybookDatabase`, un porteur restait SANS VERDICT : `1170`, porteur
`orksRedGobbo` (npc).

MESURE avant le port : natif **5** evenements, port **1**. Sous-prediction MUETTE.

Le montage utilise le VRAI porteur (`--explicit-stats orksRedGobbo:5`), pas une greffe : la reserve
de la greffe (<< les stats, traits et armes du vrai porteur ne sont pas exercees >>) tombe.

⚠ `attack_pos` est OBLIGATOIRE dans l'appel au port : sans lui,
`engine/playbook/prediction/_shared.py` SAUTE le terme d'ELEVATION
(`if scene.elev_by_pos and attack_pos and t_pos`), et le port sous-predit de x1,5 toute cible plus
BASSE que le caster. C'est un ecart d'APPEL, pas de port -- il a failli faire accuser le port. Le
terme suit la TUILE, verifie par echange controle des deux occupants.

ASCII only.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402
import probe_909r7_explosive_presents_live as P  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/probe_909r7_explosive_presents_live.py",
                "scripts/python/tests/engine/runner/test_909r7_explosive_presents_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il garde l'ACCORD avec le natif du SET, de l'ORDRE, des COUPS et de la MAGNITUDE de "
              "la face DECISION de 1170, sur son porteur REEL.",
}


def _monte(isole, seed):
    rpc = P130.Rpc()
    sf = P.ROOT / "logs" / "runners" / ("t909r7-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = P._build(sf, seed=seed)
    if rid is None:
        pytest.fail("montage impossible : `rl_duel build` a echoue (ce n'est PAS un verdict sur le "
                    "port -- reparer le montage)")
    try:
        return P.confronte(rpc, rid, isole=isole)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


@pytest.fixture(scope="module", name="splash_1170")
def _splash_1170():
    res = _monte(False, "777")
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


@pytest.fixture(scope="module", name="isole_1170")
def _isole_1170():
    res = _monte(True, "31337")
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


def test_le_regime_est_ARME(splash_1170):
    """TEMOIN NON NUL, joue AVANT les verdicts. TROIS crans, chacun ferme un accord degenere :
    l'anneau doit etre NON VIDE (sinon le SET ne teste rien), l'ALLIE doit y etre (sinon le
    friendly-fire n'est pas exerce), et les cibles doivent occuper des ELEVATIONS DIFFERENTES
    (sinon le terme d'elevation -- le seul qui separe deux cibles par ailleurs identiques -- est
    inerte, et c'est exactement celui qui a failli faire accuser le port)."""
    assert splash_1170["ring"], "anneau VIDE : le SET ne s'exerce pas"
    assert int(splash_1170["ally"]) in [int(x) for x in splash_1170["ring"]], (
        "l'ALLIE n'est pas dans le voisinage de la cible : friendly-fire non exerce")
    el = splash_1170["elev"]
    cibles = {e["target"] for e in splash_1170["natif"]}
    niveaux = {el.get(t) for t in cibles if el.get(t) is not None}
    assert len(niveaux) > 1, (
        "regime DEGENERE : toutes les cibles sont a l'elevation %s -- le terme d'elevation est "
        "inerte, l'accord de magnitude ne prouverait rien" % (niveaux,))
    assert splash_1170["attack_pos"] is not None, (
        "`attack_pos` non mesure : le port sauterait le terme d'elevation et l'ecart accuserait "
        "l'APPEL, pas le port")


def test_le_natif_predit_cible_ET_voisinage_caster_exclu(splash_1170):
    """`...ExplosivePresentsAbility$$GetTargets` = `op_Subtraction(op_Addition(Target,
    AdjacentUnits(Target)), Caster)`. L'`op_Addition` est une CONCATENATION dedoublonnee : l'ordre
    natif est donc `[cible, puis le voisinage]`."""
    cibles = [e["target"] for e in splash_1170["natif"]]
    assert cibles[:1] == [splash_1170["target"]], (
        "la cible n'est pas en tete du SET natif : %s" % cibles)
    assert set(cibles) == {splash_1170["target"], *splash_1170["ring"]}, (
        "SET natif %s != cible + voisinage %s"
        % (sorted(set(cibles)), sorted({splash_1170["target"], *splash_1170["ring"]})))
    assert splash_1170["caster"] not in cibles, (
        "le CASTER est predit -- le set natif le SOUSTRAIT (`op_Subtraction <DSLSelectors+0x48>`)")


def test_le_friendly_fire_est_dans_la_face_decision(splash_1170):
    """AUCUN wrapper `Enemies` sur le set (contraste
    `...MassDriverAcceleratorAbility$$GetAdjacentAttackTargets`, qui en a un) : l'ALLIE adjacent est
    PREDIT, et son evenement est `friendly` -- utilite NEGEE."""
    cibles = {e["target"] for e in splash_1170["natif"]}
    assert splash_1170["ally"] in cibles, (
        "l'allie u%s n'est PAS predit : le set aurait un filtre d'equipe" % splash_1170["ally"])


def test_le_port_rend_LES_MEMES_evenements(splash_1170):
    """LE verdict : meme SET, meme ORDRE, memes COUPS, meme MAGNITUDE -- evenement par evenement.
    C'est ce test que le port d'avant #909-r7 rendait ROUGE (natif 5 evenements, port 1)."""
    nat = [(e["target"], e["hits"], e["min"], e["max"]) for e in splash_1170["natif"]]
    port = [(e["target"], e["hits"], e["min"], e["max"]) for e in splash_1170["port"]]
    assert port == nat, "port %s != natif %s" % (port, nat)


def test_un_seul_coup_quelle_que_soit_la_config(splash_1170):
    """`GenerateAttackPredictions` invoque `IBattleQuery` slot `0x24 = GetAttackPrediction` ; sa
    soeur multi-coups invoque le slot `0x28 = GetMultiHitAttackPrediction`, dont le corps EST la
    premiere suivie de `hits - 1` repetitions. Le chemin plain vaut donc exactement UN coup."""
    from engine.playbook.prediction.abilities import _explosive_presents_inputs
    assert _explosive_presents_inputs(None, None, None, None, None) == {"hits_override": 1}
    assert {e["hits"] for e in splash_1170["natif"]} == {1}, (
        "le natif n'applique pas 1 coup par evenement : %s"
        % sorted({e["hits"] for e in splash_1170["natif"]}))


def test_l_appartenance_aux_registres(splash_1170):
    """La FORME du port, pour ce que l'observable ne garde PAS.

    MESURE : retirer `1170` de `_MAKE_DMG_SELECTOR_ONLY` est un mutant MUET sur ce montage -- la
    voie `selector_only = False` emet `[<Target>] + (selecteur \\ <Target>)`, or l'`op_Addition`
    natif place DEJA `Target` en tete du selecteur : meme liste, meme ordre. L'appartenance reste
    JUSTE (le natif n'a aucun batch `<Target>` separe) et le deviendrait observable des qu'un
    `aoe_overrides` distinguerait les deux batchs. C'est donc la FORME qu'on garde ici, en le
    DISANT -- pas un observable deguise."""
    from engine.entities.abilities.active_ability import (_SPECIAL_ABILITY_CLASSES,
                                                          ExplosivePresentsAbility)
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.playbook.prediction.abilities import (_MAKE_DMG_INPUT_OVERRIDES,
                                                      _MAKE_DMG_SELECTOR_ONLY,
                                                      _explosive_presents_inputs)
    assert _SPECIAL_ABILITY_CLASSES.get("ExplosivePresents") is ExplosivePresentsAbility
    assert ActiveAbilityType.ExplosivePresents in _MAKE_DMG_SELECTOR_ONLY
    assert (_MAKE_DMG_INPUT_OVERRIDES.get(ActiveAbilityType.ExplosivePresents)
            is _explosive_presents_inputs)


def test_cible_isolee_un_seul_evenement(isole_1170):
    """CONTRE-CAS : le SET n'est pas un forfait -- sans voisin, le seul membre est la cible."""
    nat = [(e["target"], e["hits"]) for e in isole_1170["natif"]]
    port = [(e["target"], e["hits"]) for e in isole_1170["port"]]
    assert nat == [(isole_1170["target"], 1)], (
        "cible isolee : le natif predit %s, attendu le seul membre `Target`" % nat)
    assert port == nat, "port %s != natif %s" % (port, nat)
