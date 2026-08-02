"""#446-r1 -- le FOLD de l'attaque normale de `Boltstorm`, confronte au NATIF.

L'attaque normale de `templAggressor` n'est pas la generique 69 : c'est `1128
Boltstorm_NormalAttack`, instanciee sur une sous-classe qui SURCHARGE la prediction --
`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack` =
`ALoki_NormalAttackAbility$$PredictAttack` + `GetAdditionalDamagePrediction`, sommes par
`IdunBattle.Core.Services.DamagePredictionResult$$Add`, sous la gate « l'arme choisie n'est PAS
melee ». Le mold etait PORTE depuis #57c-C mais son registre de dispatch
(`_RANGED_FOLLOWUP_PASSIVES`) etait VIDE : porte et INERTE, faute d'un porteur identifie. C'est
`Boltstorm` le porteur, et c'est ce qui produisait l'ecart residuel nomme par #446 (§5).

CE QUE CE TEST GARDE -- quatre choses :

  1. **LES COUPS** -- `appliedHits` natif == port, EXACTEMENT. C'est le fait le plus dur du cas
     (natif 6, port 3 avant le fix) et il ne depend d'aucune tolerance.
  2. **L'ECART DE PAIRE EST FERME** -- `|port - natif|` sur `pairUtility` tombe sous `GAP_MAX`
     (mesure #446 avant fix : -4.159792 sur la cible entouree, -5.639718 sur l'isolee ; apres le
     fold : -0.0075 et 0.0 ; apres **#446-r2** : **0.0 et 0.0**, champ a champ).
     ⚠ Le seuil bornait le residu `#446-r2` (3 points de degat sur la cible entouree, soit 0.0075
     d'utilite a 40000 PV). Ce residu est FERME (arrondi INTER-FACES de
     `CalculateBaseDamageWithAllModifiers`, cf. `docs/rl/case-446-r2-arrondi-inter-faces.md`), donc
     le seuil est RESSERRE a `EPS` : il n'y a plus rien a tolerer, et un seuil laxiste laisserait
     re-passer exactement l'ecart qu'on vient de fermer.
  3. **LES CONTRE-EPREUVES MORDENT** -- trois mutants (dispatch retire, montant ramene a `minDmg`,
     modifiers retires) doivent DEPLACER le port. Le critere est le deplacement par rapport au
     port NON MUTE, jamais l'ecart au natif : la paire porte encore `#446-r2`, donc un critere
     « ecart au natif > EPS » serait VRAI meme pour un mutant inerte (piege mesure par #446).
     Les deux dernieres gardent chacune une correction distincte, et chacune mord seule.
  4. **LA GATE** -- caster amene AU CONTACT, le natif retombe au compte de coups de l'arme et le
     port avec lui. Sans ce cran, un port qui folderait INCONDITIONNELLEMENT passerait (1)-(3).

Porteur : `templAggressor` (HERO au pool). Les 4 npc `templBossAggressor*` portent le meme passif,
donc le meme mold. ASCII only. Probe jumeau : `scripts/python/probe_446_r1_pair_residual.py`.
"""
from __future__ import annotations

import pytest

import probe_446_boltstorm_pair_term as P446
import probe_446_r1_pair_residual as R1

EPS = R1.EPS
# #446-r2 FERME : la paire est desormais EXACTE (0.000000 sur les deux cibles, champ a champ). Le
# seuil retombe donc a la tolerance Fix64-contre-float du harnais -- plus aucun residu a border.
GAP_MAX = EPS


@pytest.fixture(scope="module")
def fu_case(live_session, rpc, build_runner):
    try:
        rid = build_runner(P446.SEED, P446.BUILD_ARGS)["rid"]
        return P446.build_case(live_session, rpc, rid)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def fu_rows(fu_case, rpc):
    try:
        return [R1.decompose(rpc, fu_case, k) for k in ("T", "A")]
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def fu_mutants(fu_rows, fu_case):
    return R1.mutants(fu_case)


@pytest.fixture(scope="module")
def fu_melee(fu_mutants, fu_case, live_session, rpc):
    """EN DERNIER : ce cran DEPLACE le caster et laisse la geometrie ailleurs."""
    try:
        return R1.melee_regime(live_session, rpc, fu_case)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_followup_applied_hits_match_native(fu_rows):
    """(1) LES COUPS. `nrOfHits` (constante 0x2f) du passif s'ajoute aux coups de l'arme : le natif
    en applique 6 la ou l'arme seule en donne 3. Aucune tolerance ici."""
    assert fu_rows, "aucune mesure produite"
    for r in fu_rows:
        nat, off = r["nat_f"]["appliedHits"], r["off_f"]["appliedHits"]
        assert nat == off, (
            f"cible {r['target']} : le natif applique {nat} coups et le port {off} -- le fold "
            f"`GetAdditionalDamagePrediction` n'est pas (ou mal) dispatche")
        assert nat > 3, (
            f"cible {r['target']} : {nat} coups seulement -- le regime FOLD n'est pas atteint "
            f"(l'arme seule en donne 3), cette garde ne prouverait rien")


def test_followup_closes_the_pair_gap(fu_rows):
    """(2) L'ECART DE PAIRE EST FERME. Confronte `pairUtility` natif au port sur les DEUX cibles ;
    le residu tolere est celui, ANTERIEUR, de `#446-r2`."""
    for r in fu_rows:
        assert abs(r["gap"]) <= GAP_MAX, (
            f"cible {r['target']} : ecart port-natif {r['gap']:+.6f} au-dela de {GAP_MAX} "
            f"(natif {r['native']}, port {r['port']}) -- prediction natif={r['nat_f']} "
            f"port={r['off_f']}")


def test_followup_utility_stage_is_exact(fu_rows):
    """L'etage UTILITE reste EXACT : la meme formule offline, nourrie des champs NATIFS, reproduit
    `pairUtility` au chiffre pres. C'est ce qui autorise a lire tout ecart restant comme un ecart
    de PREDICTION -- si ce cran tombe, la localisation par etage de #446-r1 est caduque."""
    for r in fu_rows:
        assert abs(r["u_hybrid_total"] - r["native"]) < EPS, (
            f"cible {r['target']} : la formule offline nourrie du NATIF rend "
            f"{r['u_hybrid_total']} contre {r['native']} au scoreur natif")


def test_followup_counter_probes_bite(fu_mutants):
    """(3) LES CONTRE-EPREUVES MORDENT, chacune seule."""
    for m in fu_mutants:
        det = {k: round(v, 6) for k, v in m["shift"].items()}
        assert m["bites"], (
            f"la contre-epreuve `{m['mutant']}` NE MORD PAS (deplacement {det}) : l'axe qu'elle "
            f"coupe n'est pas exerce, la garde ne prouve rien dessus")


def test_followup_gate_is_ranged_only(fu_melee):
    """(4) LA GATE. Au contact, l'arme choisie est melee -> aucun fold : natif et port doivent
    retomber sur les 3 coups de l'arme, et s'accorder."""
    nat, port = fu_melee["native"], fu_melee["port"]
    assert nat[2] == 3, (
        f"au contact ({fu_melee['tile']}) le natif applique {nat[2]} coups au lieu des 3 de "
        f"l'arme -- la gate `!IsMelee` du mold n'est pas celle qu'on croit")
    assert port[2] == nat[2], (
        f"au contact, le port applique {port[2]} coups contre {nat[2]} au natif -- le port folde "
        f"en MELEE alors que la gate l'interdit")
