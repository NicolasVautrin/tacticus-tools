"""#446-r3 -- le TROISIEME mold de prediction d'attaque normale (`RighteousRepugnance`), confronte
au NATIF. Meme structure que le mold ferme par #446-r1, gate INVERSEE.

L'attaque normale d'`adeptMorvenn` n'est pas la generique 69 : c'est `1182
RighteousRepugnance_NormalAttack`, instanciee sur une sous-classe qui SURCHARGE la prediction --
`IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack`
= `ALoki_NormalAttackAbility$$PredictAttack` + `GetAdditionalDamagePrediction`, sommes par
`IdunBattle.Core.Services.DamagePredictionResult$$Add`, sous la gate « l'arme choisie EST melee »
(`IsMelee != 0` -- l'INVERSE de la gate `Boltstorm`). Le mold Python etait deja la (#446-r1 l'a
corrige), mais AUCUN registre ne le dispatchait sur cette gate : port present, registre inerte.

CE QUE CE TEST GARDE -- quatre choses :

  1. **LE REGIME EST ATTEINT** -- l'attaque normale LIVE du caster vaut `1182`, et le cran melee
     applique PLUS de coups que l'arme seule. Sans ce cran, tout le reste pourrait etre vert sur
     une unite qui n'instancie meme pas la sous-classe.
  2. **L'ACCORD EST EXACT, CHAMP A CHAMP** -- `rawHealthDmg{Min,Max}`, `healthDmg{Min,Max}` et
     `appliedHits` du natif == ceux du port, sur TOUS les crans. Aucune tolerance : ce sont des
     entiers.
  3. **LA GATE EST BIEN L'INVERSE** -- a distance (arme `Bolter` choisie), le natif NE FOLDE PAS et
     le port non plus. C'est le cran qui distingue ce mold de son jumeau : le montage qui exerce
     `Boltstorm` est exactement celui qui n'exerce PAS celui-ci.
  4. **LES CONTRE-EPREUVES MORDENT** -- quatre mutants (dispatch retire, montant ramene a `minDmg`,
     modifiers retires, gate INVERSEE) doivent DEPLACER le port. Le critere est le deplacement par
     rapport au port NON MUTE, jamais l'ecart au natif -- un critere « ecart au natif > 0 » serait
     vrai pour un mutant inerte des qu'un residu traine (piege mesure par #446).
     ⚠ `no_mods` ne mord QUE sur une tuile en SURPLOMB (le bonus d'elevation est le seul modifier
     du montage) : le test l'exige donc uniquement quand le cran `melee_elev` existe.

Porteur : `adeptMorvenn` (Morvenn Vahl, HERO **au pool** -- aucun montage catalogue). Les 3 npc
`adeptBossMorvenn*` / `adeptNpcMorvenn` portent le meme passif, donc le meme mold.
ASCII only. Probe jumeau : `scripts/python/probe_446_r3_repugnance_followup.py`.
"""
from __future__ import annotations

import pytest

import probe_446_r3_repugnance_followup as R3


@pytest.fixture(scope="module")
def rr_case(live_session, rpc, build_runner):
    try:
        rid = build_runner(R3.SEED, [a for a in R3._BASE_ARGS])["rid"]
        return R3._stage(live_session, rpc, rid, expect_fold=True)
    except R3.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def rr_rows(rr_case, rpc):
    try:
        return R3.measure(rpc, rr_case)
    except R3.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def rr_mutants(rr_rows, rr_case, rpc):
    return R3.mutants(rpc, rr_case)


def test_repugnance_regime_is_reached(rr_case, rr_rows):
    """(1) LE REGIME EST ATTEINT. `1182` live = la sous-classe surchargeante est instanciee ; et le
    cran melee applique 2 (arme) + 3 (`nrOfHits` du passif) coups, pas 2."""
    assert rr_case["ab"] == R3.NORMAL_ATTACK_ID, (
        f"l'attaque normale live du caster est {rr_case['ab']}, attendu {R3.NORMAL_ATTACK_ID} -- la "
        f"sous-classe qui surcharge PredictAttack n'est PAS instanciee")
    mel = next(r for r in rr_rows if r["step"] == "melee")
    assert mel["nat"]["appliedHits"] > 2, (
        f"au contact le natif applique {mel['nat']['appliedHits']} coups, soit ceux de l'arme "
        f"seule -- le fold n'a PAS lieu et cette garde ne prouverait rien")
    assert mel["followup"] is not None, "le port ne calcule AUCUN fold au contact"


def test_repugnance_fields_match_native(rr_rows):
    """(2) L'ACCORD EST EXACT, CHAMP A CHAMP, sur tous les crans -- entiers, aucune tolerance."""
    assert rr_rows, "aucune mesure produite"
    for r in rr_rows:
        assert not r["delta"], (
            f"cran `{r['step']}` @ {r['tile']} : le port diverge du natif -- {r['delta']} "
            f"(natif {r['nat']}, port {r['off']})")


def test_repugnance_gate_is_melee_only(rr_rows):
    """(3) LA GATE EST BIEN L'INVERSE de celle de `Boltstorm` : a distance, aucun fold."""
    rng = next((r for r in rr_rows if r["step"] == "ranged"), None)
    assert rng is not None, (
        "le cran RANGED n'a pas ete monte -- la gate n'est pas exercee et un port qui folderait "
        "inconditionnellement passerait le reste du fichier")
    assert rng["followup"] is None, (
        f"a distance ({rng['tile']}) le PORT folde alors que la gate `IsMelee` est fausse")
    mel = next(r for r in rr_rows if r["step"] == "melee")
    assert rng["nat"]["appliedHits"] < mel["nat"]["appliedHits"], (
        f"le natif applique {rng['nat']['appliedHits']} coups a distance contre "
        f"{mel['nat']['appliedHits']} au contact -- les deux crans ne se distinguent pas, la gate "
        f"n'est pas celle qu'on croit")


def test_repugnance_counter_probes_bite(rr_mutants, rr_case):
    """(4) LES CONTRE-EPREUVES MORDENT, chacune seule. `no_mods` est exempte quand le montage n'a
    aucun modifier a perdre -- et on le DIT plutot que de le laisser vert en silence."""
    has_elev = bool(rr_case["layout"].get("MELEE_ELEV"))
    for m in rr_mutants:
        if m["mutant"] == "no_mods" and not has_elev:
            continue
        assert m["bites"], (
            f"la contre-epreuve `{m['mutant']}` NE MORD PAS (deplacement {m['shift']}) : l'axe "
            f"qu'elle coupe n'est pas exerce, la garde ne prouve rien dessus")


def test_repugnance_gate_flip_moves_both_sides(rr_mutants):
    """La contre-epreuve PROPRE a cette tranche : brancher le mold sur `!IsMelee` (ce qu'aurait
    donne une recopie par analogie de `Boltstorm`) doit RETIRER le fold au contact ET l'AJOUTER a
    distance. Un mutant qui ne bougerait que d'un cote signalerait un montage ou un seul regime est
    reellement exerce."""
    m = next(x for x in rr_mutants if x["mutant"] == "gate_flip")
    assert m["shift"]["melee"]["appliedHits"] < 0, (
        f"gate inversee : les coups au contact ne BAISSENT pas ({m['shift']['melee']})")
    assert m["shift"]["ranged"]["appliedHits"] > 0, (
        f"gate inversee : les coups a distance ne MONTENT pas ({m['shift']['ranged']})")
