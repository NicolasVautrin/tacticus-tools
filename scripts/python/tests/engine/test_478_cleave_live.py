"""#478 -- le CLIQUET des DEUX volets de `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour`.

Quatre attaques normales CONCRETES portent ce corps : `Boltstorm`, `RighteousRepugnance`, `Fealty`,
`TalonOfHorus`. Il a DEUX consommateurs, et le port doit les jouer TOUS LES DEUX, DANS L'ORDRE :

  * `$$GetCustomNormalAttackBehaviour` (vslot 0x4a8, compose DANS `ExecuteNormalAttack`) -> un
    paquet sur la cible **PRIMAIRE**. N'existe QUE pour `Boltstorm` et `RighteousRepugnance`.
  * `$$GetAdditionalTargetsAttackBehavior` (le `Foreach` d'`Execute<X>`) -> le **CLEAVE** sur les
    cibles rendues par `<X>Ability$$GetAdditionalTargets`. Existe pour les QUATRE.

CE QUE CE FICHIER GARDE :

  1. **LE MONTAGE EST ATTESTE** -- attaques normales live `1220`/`1205`/`1182`/`1128`, regime
     d'ARME conforme a la gate de CHAQUE ability (elle est INVERSEE pour `Boltstorm`), et cardinal
     geometrique egal a celui qu'un ORACLE ECRIT A LA MAIN depuis la RE impose. Un montage qui ne
     s'installe pas fait `pytest.fail`, JAMAIS un skip.
  2. **LE PORT FRAPPE LES MEMES CIBLES POUR LES MEMES MONTANTS**, decompose en QUATRE etages :
     l'attaque primaire, le CARDINAL des cibles additionnelles, le MONTANT par cible, et la
     VENTILATION PAR COUP sur la cible primaire (arme PUIS fold). Un total juste avec un mauvais
     decoupage rougit a l'etage 4.
  3. **LE SECOND CAS DISCRIMINANT** -- deux geometries, trois cardinaux (0, 1, 2). Sans lui,
     « le port rend le bon total » ne distinguerait pas un selecteur porte d'une constante calee
     sur un montage.
  4. **LES CONTRE-EPREUVES MORDENT** -- quatre mutations du port, rejouees sur le MEME etat
     pre-cast (donc a cout ZERO : aucun runner, aucun cast live supplementaire). Chacune DOIT
     deplacer un chiffre, et une mutation qui ne deplace RIEN est un discriminant MORT.

ASCII only. Probe jumeau : `scripts/python/probe_478_cleave_additional_targets.py`.
"""
from __future__ import annotations

import os

import pytest

import probe_478_cleave_additional_targets as P478


def _case(rpc, build_runner, tmp_path_factory, regime: str) -> dict:
    """Monte le regime et joue le replay-diff, UN ETAT VIERGE PAR PORTEUR.

    L'etat vierge par porteur n'est pas du confort : joues a la suite sur le meme runner, le
    troisieme cast diverge pour une cause etrangere au cleave (mesure : natif 7830 / port 2081,
    avec une cible additionnelle qui REGAGNE 6000 PV)."""
    try:
        elev, playable = P478.R3B.board_geometry(P478.BOARD)
        lay = P478.LAYOUTS[regime](elev, playable)
        if lay is None:
            pytest.fail(f"montage NON INSTALLE : aucun layout '{regime}' sur {P478.BOARD}",
                        pytrace=False)
        bc = os.path.join(str(tmp_path_factory.mktemp(f"c478{regime}")), "seed-bc.json")
        P478.R3B.write_seed_bc(bc)
        rows = []
        for vis in list(lay["C"]):
            rid = build_runner(P478.SEED, P478.build_args(lay, bc))["rid"]
            st = P478.stage(rpc, rid, lay, elev)
            rows.append(P478.replay(rpc, st, vis))
        return {"lay": lay, "rows": rows}
    except P478.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def case_rr(rpc, build_runner, tmp_path_factory):
    """Le regime le plus RICHE : `adeptMorvenn` (cleave 1 **et** fold primaire), `blackAbaddon`
    (cleave 1, aucun fold), `ultraTitus` (cleave 0, aucun fold)."""
    return _case(rpc, build_runner, tmp_path_factory, "rr")


@pytest.fixture(scope="module")
def case_two(rpc, build_runner, tmp_path_factory):
    """Le SECOND cas discriminant : DEUX cibles additionnelles pour chacun des deux cleaveurs."""
    return _case(rpc, build_runner, tmp_path_factory, "two")


@pytest.fixture(scope="module")
def case_boltstorm(rpc, build_runner, tmp_path_factory):
    """Le regime RANGED : `Boltstorm`, dont les DEUX gates sont inversees. Il exerce la gate
    `IsRangedPosition` du fold primaire ; son CLEAVE, lui, ancre sur `Owner@0x30` et reste
    inobservable sur cette voie (residu `#478-r4`)."""
    return _case(rpc, build_runner, tmp_path_factory, "boltstorm")


# --------------------------------------------------------------------------- (1) et (2)

@pytest.mark.parametrize("fx", ["case_rr", "case_two", "case_boltstorm"])
def test_le_port_frappe_les_memes_cibles_pour_les_memes_montants(fx, request):
    """(1)+(2) LE MIRROR TIENT, etage par etage. Entiers, aucune tolerance."""
    case = request.getfixturevalue(fx)
    bad = P478.verdict(case["rows"])
    assert not bad, "\n".join(bad)


def test_les_trois_cardinaux_sont_couverts(case_rr, case_two, case_boltstorm):
    """(3) LE SECOND CAS DISCRIMINANT EXISTE VRAIMENT. Les cardinaux effectivement MESURES cote
    natif doivent couvrir `0`, `1` et `2` : sans ces trois-la, un port qui rendrait une constante
    passerait le test precedent."""
    got = sorted({len(r["nat_addts"])
                  for c in (case_rr, case_two, case_boltstorm) for r in c["rows"]})
    assert got == [0, 1, 2], (
        f"cardinaux NATIFS mesures {got} -- il en faut 0, 1 ET 2, sinon « le port rend le bon "
        f"total » ne distingue pas un selecteur porte d'une constante")


def test_le_fold_primaire_est_exerce_et_discrimine(case_rr, case_boltstorm):
    """(3bis) LES DEUX VOLETS SONT EXERCES SEPAREMENT. Il faut au moins un porteur QUI FOLDE
    (`RighteousRepugnance`, `Boltstorm`) et au moins un QUI NE FOLDE PAS (`Fealty`,
    `TalonOfHorus`) : sinon « le port reproduit la ventilation » serait vrai pour une raison
    structurelle."""
    rows = case_rr["rows"] + case_boltstorm["rows"]
    folds = {r["vis"]: bool(r["off_primaire_fold_hits"]) for r in rows}
    assert any(folds.values()), f"aucun porteur ne FOLDE dans la passe -- {folds}"
    assert not all(folds.values()), f"tous les porteurs FOLDENT dans la passe -- {folds}"


# --------------------------------------------------------------------------- (4) contre-epreuves

def _mutate(monkeypatch, **kw):
    """Remplace les champs nommes de l'entree `NORMAL_ATTACK_CLEAVES[passive]`, le temps du test."""
    import engine.runner.abilities.loki.additional_targets as AT
    for passive, fields in kw.items():
        entry = AT.NORMAL_ATTACK_CLEAVES[passive]
        for k, v in fields.items():
            monkeypatch.setattr(entry, k, v, raising=True)


def _row(case, vis):
    return next(r for r in case["rows"] if r["vis"] == vis)


def test_ce_vider_le_registre_fait_diverger(case_rr, monkeypatch):
    """(4a) Sans dispatch, plus AUCUN des deux volets ne part -- et les trois porteurs a volet non
    vide doivent s'eloigner du natif. Si l'un ne bouge pas, c'est que la mesure ne le voyait deja
    pas."""
    import engine.runner.abilities.loki.additional_targets as AT
    monkeypatch.setattr(AT, "cleave_for", lambda *a, **k: None)
    for vis in ("adeptMorvenn", "blackAbaddon"):
        r = _row(case_rr, vis)
        got = P478.port_only(r["bundle"])
        assert (got["primaire"], got["addts"]) != (r["nat_primaire"], r["nat_addts"]), (
            f"{vis} : vider le registre ne DEPLACE RIEN (primaire {got['primaire']}, addts "
            f"{got['addts']}) -- le discriminant est MORT et l'accord du mirror est vide")


def test_ce_greffer_le_fold_primaire_par_analogie_fait_diverger(case_rr, monkeypatch):
    """(4b) Le geste « par coherence » : donner a `Fealty`/`TalonOfHorus` le
    `$$GetCustomNormalAttackBehaviour` que leur classe native N'A PAS. Il doit les eloigner du
    natif sur la cible PRIMAIRE -- c'est ce qui interdit de « combler » l'asymetrie de #446-r3b."""
    _mutate(monkeypatch, TalonOfHorus={"primary_fold_when_melee_position": True})
    r = _row(case_rr, "blackAbaddon")
    got = P478.port_only(r["bundle"])
    assert got["primaire"] != r["nat_primaire"], (
        f"greffer le fold primaire sur TalonOfHorus ne DEPLACE RIEN (primaire {got['primaire']} "
        f"== natif {r['nat_primaire']}) -- l'asymetrie n'est donc pas mesurable ici")


def test_ce_retirer_le_fold_primaire_de_righteous_repugnance_fait_diverger(case_rr, monkeypatch):
    """(4c) L'AUTRE SENS : retirer a `RighteousRepugnance` son fold primaire doit lui coûter
    exactement les coups que le natif applique en plus a la cible primaire."""
    _mutate(monkeypatch, RighteousRepugnance={"primary_fold_when_melee_position": None})
    r = _row(case_rr, "adeptMorvenn")
    got = P478.port_only(r["bundle"])
    assert got["primaire"] != r["nat_primaire"], (
        f"retirer le fold primaire de RighteousRepugnance ne DEPLACE RIEN (primaire "
        f"{got['primaire']} == natif {r['nat_primaire']})")
    assert got["arme"] == r["off_primaire_arme_hits"][:len(got["arme"])], (
        "les coups d'ARME ont bouge alors que seule la gate du FOLD a ete mutee -- la mutation "
        "ne cible pas ce qu'elle croit")


def test_ce_inverser_la_gate_de_cleave_fait_diverger(case_rr, monkeypatch):
    """(4d) La gate d'ARME. `Fealty`/`TalonOfHorus`/`RighteousRepugnance` cleavent sur
    `IsMelee` ; l'inverser (la gate de `Boltstorm`) doit VIDER leur cleave dans ce montage, ou tous
    sont au contact. C'est la garde de l'asymetrie de gate, celle qu'un port « par analogie sur les
    quatre » aurait ecrasee."""
    _mutate(monkeypatch, TalonOfHorus={"cleaves_when_melee": False})
    r = _row(case_rr, "blackAbaddon")
    got = P478.port_only(r["bundle"])
    assert got["addts"] != r["nat_addts"], (
        f"inverser la gate d'arme de TalonOfHorus ne DEPLACE RIEN (addts {got['addts']} == natif "
        f"{r['nat_addts']}) -- la gate n'est pas exercee par ce montage")


def test_ce_le_temoin_non_mute_reste_identique(case_rr):
    """(4e) LE BRAS TEMOIN. Rejouer le port SANS mutation, sur le meme etat pre-cast, doit rendre
    EXACTEMENT ce que la passe a mesure. Sans ce bras, les quatre precedents ne prouveraient pas
    que c'est bien la MUTATION qui deplace le chiffre -- seulement que le re-jeu est instable."""
    for r in case_rr["rows"]:
        got = P478.port_only(r["bundle"])
        assert (got["primaire"], got["addts"]) == (r["nat_primaire"], r["nat_addts"]), (
            f"{r['vis']} : le re-jeu SANS mutation ne reproduit pas la passe "
            f"(port {got['primaire']}/{got['addts']} vs natif "
            f"{r['nat_primaire']}/{r['nat_addts']}) -- le harnais de contre-epreuve n'est pas sain")
