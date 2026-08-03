"""#419-r1-tr14-r5 -- le DISPATCH de l'attaque normale suit les PASSIFS DE L'ENTITE, pas le kit.

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` substitue a l'attaque normale
generique (`69 Loki_NormalAttack`) une attaque CONCRETE des que
`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` trouve, dans
`UnitConfiguration.PassiveAbilities`, un passif que la table statique
`StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` associe a une. Le port resolvait cette
cle depuis le KIT gameconfig par `visualId` -- un FORK : les deux coincident tant que personne ne
touche a la liste de passifs, et divergent en silence des qu'un montage la modifie.

CE QUE CE TEST GARDE -- quatre choses, et aucune n'est redondante :

  1. **LE DISCRIMINANT EST INSTALLE.** Les deux bras ne different QUE par
     `BC.Units[tauMarksman].PassiveAbilities` (`[1119]` contre `[]`), et le natif le rend visible :
     l'attaque normale LIVE vaut `1076 MV71SniperDroneSquadAttack` sur le bras `kit` et
     `69 Loki_NormalAttack` sur le bras `strip`. Sans ce cran, un accord global ne prouverait rien
     (les deux bras pourraient scorer la meme chose pour une raison etrangere).
  2. **CONFORMITE EN NIVEAU, aux DEUX bras et aux QUATRE crans** -- `pairUtility` natif contre
     l'utilite d'action portee. C'est ici assertable (contrairement aux gardes des tranches 12/13/14,
     qui n'assertent que l'invariance d'un ecart) parce que ce test EST celui de l'ecart en question.
  3. **CONFORMITE DE L'ETAGE PREDICTION** -- `aiPlaybookPredict` (`healthDmgMin/Max`) contre
     `make_normal_attack_predictions`. C'est l'etage OU l'ecart vivait ; l'asserter separement
     empeche qu'une compensation a l'etage UTILITE fasse passer un port faux.
  4. **LA CONTRE-EPREUVE MORD** -- dispatch du port FORCE sur le chemin arme, l'ecart au natif
     REAPPARAIT sur le bras `kit` aux deux crans a distance. Un montage ou elle serait inerte aurait
     cesse de discriminer (la cible ne serait plus atteignable, le regime aurait change...), et le
     vert du point 2 ne vaudrait plus rien -- piege #441/#446.

⚠ Les deux crans a TUILE ADJACENTE sont volontairement conserves alors qu'ils accordaient DEJA avant
le fix : ils sont la reciproque. Le dispatch custom ne mord qu'a distance (la branche MELEE de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PredictAttack`
delegue integralement au chemin arme), donc un fix qui deborderait sur la melee les ferait rougir.

Mesure d'ouverture (`master`, post-#544) et de fermeture : `docs/rl/case-419-r1-tr14-r5-dispatch-
attaque-normale.md`. ASCII only. Probe jumeau :
`scripts/python/probe_419r1tr14r5_normal_attack_stages.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5_normal_attack_stages as P

EPS = 1e-4

# Les crans a TUILE A DISTANCE : les seuls ou le dispatch custom peut mordre (la branche melee
# delegue au chemin arme). C'est la ou la contre-epreuve doit se deplacer.
_RANGED_STEPS = ("far", "realAdj_tileFar")


@pytest.fixture(scope="module")
def dispatch_measure(live_session, rpc, build_runner, tmp_path_factory):
    """DEUX runners qui ne different QUE par `BC.Units[tauMarksman].PassiveAbilities`, le layout
    commun, puis les quatre crans. Un `MontageError` devient un ECHEC, jamais un skip."""
    logs = str(tmp_path_factory.mktemp("tr14r5_dispatch"))
    try:
        arms = {}
        layout = None
        for arm in ("kit", "strip"):
            extra, _before = P.build_args(logs, arm)
            rid = build_runner(P.SEED, extra)["rid"]
            case = P.stage(live_session, rpc, rid, layout)
            layout = case["layout"]
            arms[arm] = case
        return {"rows": P.measure(live_session, rpc, arms), "arms": arms}
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def generalize_measure(live_session, rpc, build_runner):
    """GENERALISATION : second porteur (`templAggressor`), second mold (`Boltstorm`, le fold
    additional-damage de #446-r1 -- PAS le chemin drone), second board (`C2_02`). Un resultat
    obtenu sur le seul montage MV71 ne dirait rien du second call-site corrige."""
    try:
        return P.run_generalize(live_session, rpc,
                                lambda seed, extra: build_runner(seed, extra)["rid"],
                                verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _by(rows, arm):
    return {r["step"]: r for r in rows if r["arm"] == arm}


def test_dispatch_discriminant_installe(dispatch_measure):
    """(1) Les deux bras portent bien DEUX attaques normales natives differentes."""
    rows = dispatch_measure["rows"]
    kit, strip = _by(rows, "kit"), _by(rows, "strip")
    assert kit and strip, "les deux bras doivent avoir ete mesures"
    kit_ab = {r["ab"] for r in kit.values()}
    strip_ab = {r["ab"] for r in strip.values()}
    assert kit_ab == {1076}, (
        f"bras `kit` : attaque normale native {kit_ab} au lieu de 1076 "
        f"MV71SniperDroneSquadAttack -- `GetCustomNormalAttackTypeFromPassive` n'a pas substitue, "
        f"le montage ne discrimine plus")
    assert strip_ab == {69}, (
        f"bras `strip` : attaque normale native {strip_ab} au lieu de 69 Loki_NormalAttack -- "
        f"vider `PassiveAbilities` devrait retirer la substitution ; sans cet ecart le test est vide")


def test_utilite_de_paire_conforme_aux_deux_bras(dispatch_measure):
    """(2) `pairUtility` natif == utilite d'action portee, aux DEUX bras et aux QUATRE crans."""
    for r in dispatch_measure["rows"]:
        assert r["port_u"] is not None, f"cran {r['step']}/{r['arm']} : le port n'emet AUCUNE action"
        assert abs(r["port_u"] - r["nat_u"]) < EPS, (
            f"cran {r['step']} bras {r['arm']} (tuile {r['tile']}, ability native {r['ab']}) : "
            f"port {r['port_u']} contre natif {r['nat_u']} -- le dispatch d'attaque normale suit-il "
            f"encore `UnitConfiguration.PassiveAbilities` ?")


def test_etage_prediction_conforme_aux_deux_bras(dispatch_measure):
    """(3) L'etage PREDICTION lui-meme accorde -- pas seulement l'utilite qui le consomme."""
    for r in dispatch_measure["rows"]:
        nat, port = r["nat_pred"], r["port_pred"]
        assert (port["dmin"], port["dmax"]) == (nat["dmin"], nat["dmax"]), (
            f"cran {r['step']} bras {r['arm']} : bornes de degat portees "
            f"({port['dmin']},{port['dmax']}) contre natif ({nat['dmin']},{nat['dmax']}) -- "
            f"l'ecart est DANS la prediction, pas dans le composite d'utilite")
        assert port["hits"] == nat["hits"], (
            f"cran {r['step']} bras {r['arm']} : {port['hits']} coups portes contre "
            f"{nat['hits']} natifs")


def test_contre_epreuve_dispatch_force_mord(dispatch_measure):
    """(4) Dispatch du port FORCE sur le chemin arme : l'ecart REAPPARAIT sur le bras `kit`, aux
    deux crans a distance. S'il n'y reapparait pas, le montage a cesse de discriminer et le vert
    des points 2/3 ne prouve plus rien."""
    kit = _by(dispatch_measure["rows"], "kit")
    for step in _RANGED_STEPS:
        r = kit[step]
        shift = r["arm_u"] - r["nat_u"]
        assert abs(shift) > EPS, (
            f"cran {step} bras `kit` : forcer le chemin ARME laisse l'utilite a {r['arm_u']} "
            f"(natif {r['nat_u']}) -- la contre-epreuve est INERTE, le montage n'exerce plus le "
            f"dispatch et le reste du fichier est un vert vide")
    # RECIPROQUE : sur les crans a tuile ADJACENTE, forcer le chemin arme est un NO-OP -- la branche
    # melee du natif delegue deja au chemin arme. Un fix qui deborderait sur la melee les ferait
    # rougir ici.
    for step, r in kit.items():
        if step in _RANGED_STEPS:
            continue
        assert abs(r["arm_u"] - r["nat_u"]) < EPS, (
            f"cran {step} bras `kit` (tuile adjacente) : forcer le chemin ARME deplace l'utilite de "
            f"{r['arm_u'] - r['nat_u']} alors que la branche MELEE de "
            f"`MV71SniperDroneSquadAttackAbility$$PredictAttack` delegue DEJA au chemin arme")


def test_generalisation_second_porteur_second_mold(generalize_measure):
    """(5) `templAggressor` / `Boltstorm` sur `C2_02` : le MEME fix, sur l'AUTRE call-site.

    Le discriminant est la meme mutation d'ETAT (`PassiveAbilities` vide, ici par `--unit-stat`
    comme le controle apparie de #446-r1 §4), et le natif y repond en ramenant l'attaque normale de
    `1128 Boltstorm_NormalAttack` a `69 Loki_NormalAttack` -- donc en cessant de folder
    (`GetAdditionalDamagePrediction`), ce que les COUPS rendent visible."""
    rows = generalize_measure["rows"]
    kit = _by(rows, "kit")["ranged"]
    strip = _by(rows, "strip")["ranged"]
    assert kit["ab"] == P.G_ABILITY_KIT, (
        f"bras `kit` : attaque normale native {kit['ab']} au lieu de {P.G_ABILITY_KIT} "
        f"Boltstorm_NormalAttack -- le montage ne discrimine plus")
    assert strip["ab"] == P.G_ABILITY_STRIP, (
        f"bras `strip` : attaque normale native {strip['ab']} au lieu de {P.G_ABILITY_STRIP} "
        f"Loki_NormalAttack -- vider `PassiveAbilities` devrait retirer la substitution")
    assert kit["nat_pred"]["hits"] > strip["nat_pred"]["hits"], (
        f"le fold devrait AJOUTER des coups cote natif : {kit['nat_pred']['hits']} avec le passif "
        f"contre {strip['nat_pred']['hits']} sans -- sans cet ecart le cran ne teste rien")
    for r in (kit, strip):
        assert abs(r["port_u"] - r["nat_u"]) < EPS, (
            f"bras {r['arm']} : port {r['port_u']} contre natif {r['nat_u']}")
        assert r["port_pred"]["hits"] == r["nat_pred"]["hits"], (
            f"bras {r['arm']} : {r['port_pred']['hits']} coups portes contre "
            f"{r['nat_pred']['hits']} natifs -- le fold suit-il encore l'ETAT ?")


def test_generalisation_canal_coupe_mord(generalize_measure):
    """(6) CONTRE-EPREUVE de (5) : canal de mesure COUPE (`passive_abilities = None`), donc repli
    KIT = le comportement d'AVANT le fix. Il doit MORDRE sur le bras `strip` (le kit dit toujours
    `Boltstorm`) et rester INERTE sur le bras `kit` (kit et entite concordent). Une mutation
    inerte des deux cotes signifierait que le fix n'est plus ce qui produit le vert de (5)."""
    kit = _by(generalize_measure["rows"], "kit")["ranged"]
    strip = _by(generalize_measure["rows"], "strip")["ranged"]
    assert abs(strip["arm_u"] - strip["nat_u"]) > EPS, (
        f"bras `strip`, canal coupe : l'utilite reste a {strip['arm_u']} (natif {strip['nat_u']}) "
        f"-- le repli KIT devrait faire folder a tort, la contre-epreuve est INERTE")
    assert abs(kit["arm_u"] - kit["nat_u"]) < EPS, (
        f"bras `kit`, canal coupe : l'utilite bouge de {kit['arm_u'] - kit['nat_u']} alors que le "
        f"kit et l'entite portent tous deux `Boltstorm` -- le repli ne doit rien changer LA")
