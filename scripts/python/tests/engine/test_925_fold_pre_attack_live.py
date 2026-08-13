"""#925 -- le CLIQUET du drapeau `is_outside_attack` du FOLD primaire.

`<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` rend un
`IdunBattleLogic.Entities.DSLBehaviors$$If(<cond>, <AttackDamage>)` -- une feuille **NUE**, composee
dans l'unique `IdunBattleLogic.Entities.DSLBehaviors$$Attack` que
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
monte autour des trois volets (coups d'ARME `&` FOLD `&`
`ExecuteAdditionalHitsWithDamageProfileType`). Elle n'ouvre donc AUCUNE attaque : `StartAttack`
(slot 58) n'est pousse que par `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, et
`IdunBattle.Operations.StartAttackOperation$$Execute` est le seul emetteur d'
`EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5)` sur cette voie.

Le port emettait `On(5)` pour le fold AUSSI -- le defaut `is_outside_attack=True` d'
`AttackWithAttackDamage` etait pris par les DEUX volets, alors que seul le CLEAVE
(`$$GetAdditionalTargetsAttackBehavior`) emballe sa feuille dans son propre `$$Attack`.

CE QUE CE FICHIER GARDE :

  1. **LE CANAL EST ARME** -- le trait `LetTheGalaxyBurn` est sur l'ENTITE du porteur (lu dans les
     traits MESURES, canal `combatSnapshot`), sans quoi aucun consommateur d'`On(5)` ne consomme de
     tirage et un accord ne prouverait rien. Montage non installe -> `pytest.fail`, jamais un skip.
  2. **LE DRAPEAU PILOTE EXACTEMENT UNE EMISSION** (etage STRUCTUREL, offline pur).
  3. **LE PORT EGALE LA VENTILATION NATIVE COUP PAR COUP** sur la cible primaire.
  4. **LA CONTRE-EPREUVE MORD** : le port MUTANT (l'ancien comportement) s'en ecarte.
  5. **LE REGIME NOMINAL NE REGRESSE PAS** -- `probe_478 --regime boltstorm`, sans aucune greffe,
     reste exact sur les QUATRE etages (le fix ne doit rien deplacer la ou le canal est inerte).

ASCII only. Probe jumeau : `scripts/python/probe_925_fold_pre_attack.py`.
"""
from __future__ import annotations

import os

import pytest

import probe_478_cleave_additional_targets as P478
import probe_925_fold_pre_attack as P925

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # le drapeau teste et les deux volets qui le prennent
        "scripts/python/engine/runner/abilities/loki/additional_targets.py",
        # la feuille qui le consomme, et l'operation qui emet `On(PreAttack = 5)`
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
        # le dispatcher de l'event 5 et ses DEUX consommateurs portes (le canal du montage)
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/loki/let_the_galaxy_burn.py",
        "scripts/python/engine/runner/operations/triggers/loki/suppressive_fire.py",
        # le call-site qui joue les deux volets dans l'ordre natif
        "scripts/python/engine/runner/operations/damage.py",
        # les probes : montage, oracle geometrique et replay-diff en viennent
        "scripts/python/probe_925_fold_pre_attack.py",
        "scripts/python/probe_478_cleave_additional_targets.py",
        "scripts/python/probe_446_r3b_fealty_talon_asymetrie.py",
        # la FERMETURE d'imports du montage, mesuree par `probe_486r15` : la geometrie du board,
        # le pilote de messages et l'ordonnanceur de phases (le replay offline les traverse), et
        # les probes que `probe_446_r3b` tire pour ecrire le seed BC greffe.
        "scripts/python/board.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        "scripts/python/probe_226_seed_bc_ability_configs.py",
        "scripts/python/probe_27_3_live.py",
        "scripts/python/probe_27_custom_utility_inventory.py",
        "scripts/python/probe_27_r1_massdriver_custom.py",
        "scripts/python/probe_353_ramming_speed_prediction.py",
        "scripts/python/probe_380_seed_bc_patch_survival.py",
        "scripts/python/repo_read.py"),
    "build": False,
    "toujours": False,
    "raison": "Il confronte la ventilation par coup d'une attaque normale a fold au natif, sous "
              "un canal `On(PreAttack = 5)` arme : le drapeau, la feuille qui le lit, l'operation "
              "qui emet l'event, ses consommateurs, et le harnais de montage.",
}


def _case(rpc, build_runner, tmp_path_factory, regime: str) -> dict:
    """Le montage GREFFE : le layout de #478 + le trait canal sur l'ENTITE du porteur de fold."""
    porteur, layout = P925.REGIMES[regime]
    try:
        elev, playable = P478.R3B.board_geometry(P478.BOARD)
        lay = P478.LAYOUTS[layout](elev, playable)
        if lay is None:
            pytest.fail(f"montage NON INSTALLE : aucun layout {layout} sur {P478.BOARD}",
                        pytrace=False)
        bc = os.path.join(str(tmp_path_factory.mktemp(f"c925{regime}")), "seed-bc.json")
        P478.R3B.write_seed_bc(bc)
        extra = list(P478.build_args(lay, bc)) + P925.trait_arg(porteur)
        rid = build_runner(P478.SEED, extra)["rid"]
        st = P478.stage(rpc, rid, lay, elev)
        r = P478.replay(rpc, st, porteur)
        bundle = r["bundle"]
        return {"r": r, "bundle": bundle, "porteur": porteur,
                "traits": P925.traits_mesures(bundle),
                "corr": P925.rejoue(bundle, fold_emet=False),
                "mut": P925.rejoue(bundle, fold_emet=True)}
    except P478.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def case(rpc, build_runner, tmp_path_factory):
    """`Boltstorm` sur `templAggressor` -- fold gate `IdunBattleLogic.Entities.DSLTriggers$$
    IsRangedPosition` (le porteur tire, a distance hex 2 de sa cible)."""
    return _case(rpc, build_runner, tmp_path_factory, "boltstorm")


@pytest.fixture(scope="module")
def case_rr(rpc, build_runner, tmp_path_factory):
    """GENERALISATION -- `RighteousRepugnance` sur `adeptMorvenn`, le SECOND (et dernier) porteur de
    fold, dont la gate est l'INVERSE (`<DSLTriggers+0x18>` = `IsMeleePosition`, porteur AU CONTACT).

    Le foyer porte est le MEME (`additional_targets._attack_damage_leaf`) : jouer les deux est ce
    qui distingue « le fix est juste » de « le fix est juste sur CE porteur »."""
    return _case(rpc, build_runner, tmp_path_factory, "rr")


@pytest.fixture(scope="module")
def case_nominal(rpc, build_runner, tmp_path_factory):
    """Le regime NOMINAL, SANS greffe : `templAggressor` avec son kit reel. Le canal `On(5)` y est
    inerte (son seul consommateur, `SuppressiveFire`, re-poserait un `Pinned` deja present, que le
    gate << deja present >> d'`IdunBattle.Operations.AddEffectOperation$$Execute` refuse) -- donc le
    fix ne doit RIEN y deplacer, et c'est ce que ce cas garde."""
    try:
        elev, playable = P478.R3B.board_geometry(P478.BOARD)
        lay = P478.layout_boltstorm(elev, playable)
        if lay is None:
            pytest.fail(f"montage NON INSTALLE : aucun layout boltstorm sur {P478.BOARD}",
                        pytrace=False)
        bc = os.path.join(str(tmp_path_factory.mktemp("c925n")), "seed-bc.json")
        P478.R3B.write_seed_bc(bc)
        rid = build_runner(P478.SEED, P478.build_args(lay, bc))["rid"]
        st = P478.stage(rpc, rid, lay, elev)
        return P478.replay(rpc, st, P925.REGIMES["boltstorm"][0])
    except P478.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_canal_est_arme_sur_l_entite(fx, request):
    """(1) Sans le trait sur l'ENTITE, aucun consommateur d'`On(5)` ne tire : tous les etages qui
    suivent seraient des accords en regime DEGENERE."""
    case = request.getfixturevalue(fx)
    assert P925.TRAITS[-1] in case["traits"], (
        f"canal NON ARME : l'entite de {case['porteur']} porte {sorted(case['traits'])} -- "
        f"{P925.TRAITS[-1]} n'y est pas. `--unit-stat Traits=[...]` n'a pas mordu, et un accord "
        f"aux etages suivants ne discriminerait RIEN.")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_drapeau_pilote_exactement_une_emission_on5(fx, request):
    """(2) ETAGE STRUCTUREL. `fold_emits_pre_attack` doit valoir EXACTEMENT une emission
    `On(PreAttack = 5)` -- ni zero (le drapeau serait inerte), ni deux (il piloterait autre chose)."""
    case = request.getfixturevalue(fx)
    corr, mut = case["corr"], case["mut"]
    assert mut["on5"] - corr["on5"] == 1, (
        f"`fold_emits_pre_attack` change le nombre d'`On(5)` de {mut['on5'] - corr['on5']}, attendu "
        f"exactement 1 (corrige {corr['on5']}, mutant {mut['on5']}) -- le drapeau ne pilote pas ce "
        f"que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` dit qu'il pilote")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_montage_exerce_bien_le_fold(fx, request):
    """(2bis) NON-TRIVIALITE : sans coup de FOLD, le drapeau teste n'est meme pas atteint et les
    etages 3/4 jugeraient une branche morte. Les coups de fold natifs sont ceux dont l'
    `Active_Ability_Type` est NUL (feuille `AttackDamageBehaviour` nue)."""
    case = request.getfixturevalue(fx)
    r, corr = case["r"], case["corr"]
    n_fold_nat = sum(1 for k in r["nat_primaire_kinds"] if k is None)
    assert r["want_primary_fold"] and n_fold_nat and corr["fold"], (
        f"montage TRIVIAL : fold attendu par la RE {r['want_primary_fold']}, coups de fold natifs "
        f"{n_fold_nat}, coups de fold du port {corr['fold']}")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_port_egale_la_ventilation_native_coup_par_coup(fx, request):
    """(3) Le VERDICT. Il porte sur la suite des `Amount` natifs de la cible primaire.

    ⚠ PREMISSE PERIMEE, corrigee par `#925-r1` : ce test disait << PAS sur le total de PV >>, parce
    qu'a l'ecriture de #925 le montage reveillait une divergence TIERCE (port 4134 contre 3508
    natif sur la primaire). Sa cause a ete trouvee et corrigee -- le FOLD, feuille NUE, rejouait le
    canal #179, qui est un VOLET FRERE du `Attack(...)` et non un enfant de la feuille. Le total de
    PV est desormais EXACT lui aussi ; il fait verdict dans
    `tests/engine/test_925r1_ltgb_attribution_live.py`, qui le garde par cible. Ici, la ventilation
    par coup reste le verdict PROPRE au drapeau `fold_emits_pre_attack`, et la coherence du NATIF
    est assertionnee juste en dessous."""
    case = request.getfixturevalue(fx)
    r, corr = case["r"], case["corr"]
    nat = list(r["nat_primaire_hits"])
    got = list(corr["arme"]) + list(corr["fold"])
    assert nat, "le NATIF ne rapporte AUCUN coup sur la cible primaire -- rien n'a eu lieu"
    assert got == nat, (
        f"ventilation par COUP sur la cible primaire -- port {got} (arme {corr['arme']} + fold "
        f"{corr['fold']}) != natif {nat} (kinds {r['nat_primaire_kinds']})")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_natif_est_coherent_donc_la_ventilation_fait_verdict(fx, request):
    """(3bis) La somme des coups natifs DOIT egaler le delta de PV natif. Sans ce cran, ecarter le
    total de PV du verdict serait une echappatoire ; avec lui, c'est une MESURE : le natif est
    complet, le port ajoute ailleurs."""
    case = request.getfixturevalue(fx)
    r = case["r"]
    s = sum(int(x) for x in r["nat_primaire_hits"])
    assert s == int(r["nat_primaire"]), (
        f"le NATIF est INCOHERENT : somme des coups {s} != delta de PV {r['nat_primaire']} -- la "
        f"ventilation ne peut alors pas servir de verdict")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_la_contre_epreuve_mord(fx, request):
    """(4) Le port MUTANT (`fold_emits_pre_attack() == True`, l'ancien comportement) DOIT s'ecarter
    de la ventilation native. S'il l'egalait, le canal serait inerte et le test precedent
    n'aurait discrimine RIEN."""
    case = request.getfixturevalue(fx)
    r, mut = case["r"], case["mut"]
    nat = list(r["nat_primaire_hits"])
    mgot = list(mut["arme"]) + list(mut["fold"])
    assert mgot != nat, (
        "le port MUTANT (un `On(5)` de trop) rend EXACTEMENT la ventilation native -- le canal est "
        "INERTE sur ce montage, donc l'accord du test precedent ne discrimine rien")


def test_le_regime_nominal_ne_regresse_pas(case_nominal):
    """(5) NON-REGRESSION. Sans greffe, le canal `On(5)` est inerte : le port doit egaler le natif
    sur les QUATRE etages de #478 (primaire, cardinal, montant par cible, ventilation)."""
    bad = P478.verdict([case_nominal])
    assert not bad, (
        "le regime NOMINAL (aucune greffe) diverge apres #925 -- le fix a deplace quelque chose la "
        "ou le canal est cense etre inerte :\n  - " + "\n  - ".join(bad))
