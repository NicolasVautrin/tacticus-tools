"""#925-r1 -- le CLIQUET du drapeau `leaf_executes_additional_hits` : une feuille NUE ne rejoue
PAS le canal #179.

`IdunBattleLogic.Entities.DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType` est un VOLET du
`Attack(...)`, FRERE de la feuille de coups :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
monte UN SEUL `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour de `b1 & b2 & b3` -- `b1` les
coups d'ARME (`$$AttackDamage`), `b2` le FOLD (`$$GetCustomNormalAttackBehaviour`, une feuille NUE,
`isOutsideAttack = false`) et `b3` ce canal. Le FOLD est un FRERE de `b3`, jamais son parent.

Le port le rejouait : le gate de `damage_ops/ability.py` etait `is_attack_damage_op` SEUL. Et comme
le port joue le fold APRES le `FinishAttack`/`On(Attack = 9)` de l'attaque primaire -- donc APRES
que `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`
a efface le flag persistant ET pose `DespoiledGround` sur la tuile de la cible --, le descripteur
d'`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` se re-qualifiait
par l'AUTRE branche de son gate (`TargetHasTileEffect | IsPersistentData`) : un coup de plus sur la
cible PRIMAIRE, et un tirage de plus, qui faisait ensuite rater au CLEAVE le `Maybe` que le natif
lui accorde.

CE QUE CE FICHIER GARDE :

  1. **LE CANAL EST ARME** -- le trait `LetTheGalaxyBurn` est sur l'ENTITE du porteur (traits
     MESURES, canal `combatSnapshot`), sans quoi aucun descripteur #179 n'existe et tout accord
     serait un accord en regime DEGENERE. Montage non installe -> `pytest.fail`, jamais un skip.
  2. **LE NATIF EST COHERENT** -- pour chaque cible, la somme de ses `Amount` == son delta de PV.
     C'est ce cran qui autorise le verdict par PV.
  3. **LE MONTAGE EXERCE BIEN LE CANAL** -- le natif porte un coup `LetTheGalaxyBurn` quelque part
     ET le drapeau change le nombre d'appels du canal par la voie `ability`.
  4. **LE PORT EGALE LE NATIF, PV PAR CIBLE ET COUP PAR COUP.**
  5. **LA CONTRE-EPREUVE MORD** -- sous mutation de
     `damage_ops.ability.leaf_executes_additional_hits` (l'ancien comportement), le port DOIT
     diverger.
  6. **LE SECOND PORTEUR DE FOLD** (`RighteousRepugnance` / `adeptMorvenn`, gate INVERSE) passe les
     memes crans : le foyer corrige est PARTAGE, donc confronter un seul porteur ne distinguerait
     pas << le fix est juste >> de << le fix est juste sur CE porteur >>.

ASCII only. Probe jumeau : `scripts/python/probe_925r1_ltgb_attribution.py`.
"""
from __future__ import annotations

import os

import pytest

import probe_478_cleave_additional_targets as P478
import probe_925_fold_pre_attack as P925
import probe_925r1_ltgb_attribution as P925R1

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # le drapeau teste et la facade qui le lit
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
        # l'AUTRE facade du canal #179 (l'attaque primaire) et le canal lui-meme
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/additional_hits.py",
        # le descripteur #179 confronte, et les deux triggers qui arment/desarment son gate
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/runner/operations/triggers/loki/let_the_galaxy_burn.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # les deux volets du fold/cleave et le call-site qui les joue dans l'ordre natif
        "scripts/python/engine/runner/abilities/loki/additional_targets.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/operations/damage.py",
        # les probes : montage, oracle geometrique, replay-diff, decomposition
        "scripts/python/probe_925r1_ltgb_attribution.py",
        "scripts/python/probe_925_fold_pre_attack.py",
        "scripts/python/probe_478_cleave_additional_targets.py",
        "scripts/python/probe_446_r3b_fealty_talon_asymetrie.py",
        # la FERMETURE d'imports du montage (meme que la garde jumelle #925)
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
    "raison": "Il confronte au natif le nombre d'executions du canal #179 (coups additionnels "
              "heterogenes) d'une attaque normale a FOLD, sous un descripteur `LetTheGalaxyBurn` "
              "arme : le drapeau, les deux facades du canal, le descripteur, ses triggers, et le "
              "harnais de montage.",
}


def _case(rpc, build_runner, tmp_path_factory, regime: str) -> dict:
    """FIXTURE DE MONTAGE, partagee par les deux porteurs de fold : le layout de #478 + la GREFFE du
    trait `LetTheGalaxyBurn` sur l'ENTITE du porteur (`--unit-stat Traits=[...]`, qui reecrit le
    seed BC -- donc elle mord des DEUX cotes, natif et port).

    Le cast LIVE n'a lieu qu'UNE fois ; les deux regimes du port sont ensuite rejoues sur le MEME
    bundle d'etat pre-cast (meme Mersenne Twister), ce qui rend la contre-epreuve GRATUITE."""
    porteur, layout = P925.REGIMES[regime]
    try:
        elev, playable = P478.R3B.board_geometry(P478.BOARD)
        lay = P478.LAYOUTS[layout](elev, playable)
        if lay is None:
            pytest.fail(f"montage NON INSTALLE : aucun layout {layout} sur {P478.BOARD}",
                        pytrace=False)
        bc = os.path.join(str(tmp_path_factory.mktemp(f"c925r1{regime}")), "seed-bc.json")
        P478.R3B.write_seed_bc(bc)
        extra = list(P478.build_args(lay, bc)) + P925.trait_arg(porteur)
        rid = build_runner(P478.SEED, extra)["rid"]
        st = P478.stage(rpc, rid, lay, elev)
        return P925R1.mesure(rpc, st, porteur)
    except P478.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def case(rpc, build_runner, tmp_path_factory):
    """`Boltstorm` sur `templAggressor` -- fold gate `IdunBattleLogic.Entities.DSLTriggers$$
    IsRangedPosition`, deux cibles de cleave."""
    return _case(rpc, build_runner, tmp_path_factory, "boltstorm")


@pytest.fixture(scope="module")
def case_rr(rpc, build_runner, tmp_path_factory):
    """GENERALISATION -- `RighteousRepugnance` sur `adeptMorvenn`, le SECOND porteur de fold, dont
    la gate est l'INVERSE (`<DSLTriggers+0x18>` = `IsMeleePosition`). MEME foyer corrige."""
    return _case(rpc, build_runner, tmp_path_factory, "rr")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_canal_est_arme_sur_l_entite(fx, request):
    """(1) Sans le trait sur l'ENTITE, aucun descripteur #179 n'existe : les crans suivants
    seraient des accords en regime DEGENERE."""
    c = request.getfixturevalue(fx)
    assert P925.TRAITS[-1] in c["traits"], (
        f"canal NON ARME : l'entite de {c['porteur']} porte {sorted(c['traits'])} -- "
        f"{P925.TRAITS[-1]} n'y est pas, donc aucun coup additionnel n'est en jeu")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_natif_est_coherent_par_cible(fx, request):
    """(2) Pour CHAQUE cible, la somme de ses `Amount` natifs == son delta de PV. C'est ce cran qui
    autorise a faire porter le verdict sur le PV : le natif est complet."""
    c = request.getfixturevalue(fx)
    nat = c["r"]["nat"]
    for k, v in c["nat_hits"].items():
        tot = sum(int(a) for a, _ in v)
        got = int(nat.get(k, 0))
        if not got:
            continue
        assert tot == got, (
            f"le NATIF est INCOHERENT sur {k} : somme des coups {tot} != delta de PV {got} -- "
            f"le verdict par PV serait alors sans fondement")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_montage_exerce_bien_le_canal_179(fx, request):
    """(3) NON-TRIVIALITE. Le mutant DOIT tirer au moins un coup du canal #179 par le FOLD, et le
    corrige AUCUN.

    ⚠ Le discriminant est la CIBLE, pas le COMPTE : le CLEAVE emprunte la MEME voie `ability`, et
    sur le regime `boltstorm` les deux regimes tirent 1 coup chacun -- le corrige sur
    `necroDestroyer` (le cleave, legitime), le mutant sur la cible PRIMAIRE (le fold, en trop). Ce
    cran a d'abord ete ecrit en compte global et a ROUGI sur un montage pourtant juste (mesure du
    2026-08-13) : un cran de non-trivialite mal cible fait accuser le montage a la place du code."""
    c = request.getfixturevalue(fx)
    corr, mut = c["corr"], c["mut"]
    assert mut["n_hits_fold_179"] >= 1 and corr["n_hits_fold_179"] == 0, (
        f"montage TRIVIAL : coups du canal #179 tires par le FOLD (voie `ability`, cible PRIMAIRE) "
        f"-- corrige {corr['n_hits_fold_179']}, mutant {mut['n_hits_fold_179']} ; attendu 0 et "
        f">= 1. Le drapeau `leaf_executes_additional_hits` n'est pas atteint par ce montage.")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_port_egale_le_natif_pv_par_cible(fx, request):
    """(4) LE VERDICT. `#925-r1` etait un coup APPLIQUE hors ventilation : c'est donc bien le delta
    de PV PAR CIBLE (un dict, jamais un total) qui le porte."""
    c = request.getfixturevalue(fx)
    assert c["corr"]["pv"] == c["r"]["nat"], (
        f"PV par cible -- port corrige {c['corr']['pv']} != natif {c['r']['nat']}")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_port_egale_le_natif_coup_par_coup_sur_la_primaire(fx, request):
    """(4bis) Et la ventilation par COUP de la cible primaire, qui dit COMMENT le total se
    decompose -- un total juste par compensation ne passerait pas ce cran."""
    c = request.getfixturevalue(fx)
    nat = list(c["r"]["nat_primaire_hits"])
    got = list(c["corr"]["arme"]) + list(c["corr"]["fold"])
    assert nat, "le NATIF ne rapporte AUCUN coup sur la cible primaire"
    assert got == nat, (
        f"ventilation par COUP sur la primaire -- port {got} (arme {c['corr']['arme']} + fold "
        f"{c['corr']['fold']}) != natif {nat} (kinds {c['r']['nat_primaire_kinds']})")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_la_contre_epreuve_mord(fx, request):
    """(5) Le port MUTANT (`leaf_executes_additional_hits` toujours vrai = l'ancien gate) DOIT
    s'ecarter des PV natifs. S'il les egalait, le cran 4 n'aurait rien discrimine."""
    c = request.getfixturevalue(fx)
    assert c["mut"]["pv"] != c["r"]["nat"], (
        "le port MUTANT (le FOLD rejoue le canal #179) rend EXACTEMENT les PV natifs -- le canal "
        "est INERTE sur ce montage, donc l'accord du cran precedent ne discrimine rien")


@pytest.mark.parametrize("fx", ["case", "case_rr"])
def test_le_verdict_complet_du_probe_est_vert(fx, request):
    """(6) Le VERDICT du probe jumeau, joue sur le meme cas -- il agrege les cinq crans et c'est
    lui qui fait foi cote outillage. Un ecart entre les deux serait un fork de contrat."""
    c = request.getfixturevalue(fx)
    bad = P925R1.verdict(c)
    assert not bad, "verdict `probe_925r1_ltgb_attribution` :\n  - " + "\n  - ".join(bad)
