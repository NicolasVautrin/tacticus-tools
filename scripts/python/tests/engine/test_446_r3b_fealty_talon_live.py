"""#446-r3b -- `Fealty` (1512) et `TalonOfHorus` (1484) : le CLIQUET D'ASYMETRIE.

Ces deux abilities ont, comme `Boltstorm` et `RighteousRepugnance`, un
`<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` -- mais **ni** `$$PredictAttack` **ni**
`$$GetAdditionalDamagePrediction`. Elles infligent donc du degat additionnel en COMBAT (un CLEAVE
sur les ennemis adjacents a la fois au caster et a la cible) sans qu'aucun paquet ne soit attribue
a la cible PRIMAIRE en DECISION. Le texte i2 le dit aussi, et c'est une seconde source :
`RighteousRepugnance` porte la clause « **to the target** and to all enemy units adjacent to both
[...] », `TalonOfHorus` ne la porte PAS.

CE QUE CE FICHIER GARDE -- il rougit si quelqu'un « comble » l'asymetrie :

  1. **LE MONTAGE EST ATTESTE** -- attaques normales live `1220` / `1205` / `1182`, les trois
     porteurs ADJACENTS NATIFS a la meme cible, et une cible ADDITIONNELLE adjacente aux deux
     porteurs greffes (sans elle, « pas de fold » se mesurerait la ou il n'y a rien d'additionnel).
     Un montage qui ne s'installe pas fait `pytest.fail`, JAMAIS un skip.
  2. **LE MIRROR TIENT** -- natif et port s'accordent CHAMP A CHAMP sur les trois porteurs.
     C'est CE test qui rougit le jour ou `Fealty`/`TalonOfHorus` entrent dans
     `_MELEE_FOLLOWUP_PASSIVES` « par coherence ».
  3. **LE DISCRIMINANT MORD DANS LES DEUX SENS** -- sans lui l'accord de (2) serait vide :
     - greffer le fold sur les deux DOIT les faire diverger du natif (la mesure sait voir un fold
       de trop) ;
     - vider le registre DOIT faire diverger `adeptMorvenn`, temoin POSITIF qui folde vraiment
       (la mesure sait voir un fold qui manque).
  4. **LA FACE COMBAT EST BIEN LA** -- le cleave natif retire des PV a la cible ADDITIONNELLE.
     C'est ce qui interdit de relire l'asymetrie comme « ces abilities ne font rien ».

⚠ Ce fichier ne garde PAS la face COMBAT du PORT : le cleave n'y est pas porte (residu nomme
`#478`, numero ALLOUE par `probe_468_collision_numeros.py --suggere`, cf.
`docs/rl/case-446-r3b-fealty-talon-asymetrie.md`). Le garder « absent » serait un cliquet a
l'envers.

ASCII only. Probe jumeau : `scripts/python/probe_446_r3b_fealty_talon_asymetrie.py`.
"""
from __future__ import annotations

import os

import pytest

import probe_446_r3b_fealty_talon_asymetrie as R3B


@pytest.fixture(scope="module")
def r3b_case(live_session, rpc, build_runner, tmp_path_factory):
    try:
        elev, playable = R3B.board_geometry(R3B.BOARD)
        lay = R3B.find_layout(elev, playable)
        if lay is None:
            pytest.fail(f"montage NON INSTALLE : aucune configuration (T, A, 3 porteurs) sur "
                        f"{R3B.BOARD}", pytrace=False)
        bc = os.path.join(str(tmp_path_factory.mktemp("r3b")), "seed-bc.json")
        R3B.write_seed_bc(bc)
        rid = build_runner(R3B.SEED, R3B.build_args(lay, bc))["rid"]
        st = R3B.stage(live_session, rpc, rid, lay, elev)
        st["layout"] = lay
        return st
    except R3B.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def r3b_rows(r3b_case, rpc):
    try:
        return R3B.measure_decision(rpc, r3b_case)
    except R3B.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_le_montage_est_atteste(r3b_case, r3b_rows):
    """(1) LE MONTAGE EST ATTESTE. `stage()` a deja leve sur toute attestation manquante ; ici on
    re-DIT les trois faits dont depend la lecture, pour qu'un echec les nomme."""
    got = {v: c["ab"] for v, c in r3b_case["cases"].items()}
    want = {v: aid for (v, _n, _p, aid, _f, _g) in R3B.CARRIERS}
    assert got == want, (
        f"les attaques normales live sont {got}, attendu {want} -- les greffes n'ont pas mordu "
        f"(sans elles `ultraTitus`/`blackAbaddon` rendraient la generique 69)")
    assert len(r3b_rows) == len(R3B.CARRIERS), (
        f"{len(r3b_rows)} porteur(s) mesure(s) sur {len(R3B.CARRIERS)}")
    assert any(r["folds"] for r in r3b_rows.values()), (
        "aucun temoin POSITIF dans le montage -- rien ne prouverait que la mesure sait voir un fold")


def test_le_mirror_tient_champ_a_champ(r3b_rows):
    """(2) LE MIRROR TIENT. Entiers, aucune tolerance. ROUGIT si un fold en DECISION est ajoute a
    `Fealty`/`TalonOfHorus` -- c'est la raison d'etre de ce fichier."""
    for v, r in r3b_rows.items():
        assert not r["d_livre"], (
            f"{v} ({r['passive']}, attaque normale {r['ab']}) : le port diverge du natif -- "
            f"{r['d_livre']} (natif {r['nat']}, port {r['port']})")


def test_greffer_le_fold_par_analogie_fait_diverger(r3b_rows):
    """(3a) LE DISCRIMINANT MORD. Inscrire `Fealty`/`TalonOfHorus` au registre de fold -- le geste
    « par coherence » que cette tranche interdit -- DOIT les eloigner du natif. Sinon l'accord du
    test precedent serait vrai pour une raison structurelle, et ne prouverait rien."""
    for v, r in r3b_rows.items():
        if r["folds"]:
            assert not r["d_foldall"], (
                f"{v} est le temoin POSITIF : greffer le fold des DEUX AUTRES ne doit pas le "
                f"deplacer, or {r['d_foldall']}")
            continue
        assert r["d_foldall"], (
            f"{v} ({r['passive']}) : greffer le fold ne DEPLACE RIEN -- le discriminant est MORT "
            f"(montant d'ability nul ? gate melee non exercee ?), et « natif == port » est vide")


def test_vider_le_registre_fait_diverger_le_temoin_positif(r3b_rows):
    """(3b) L'AUTRE SENS. Vider `_MELEE_FOLLOWUP_PASSIVES` doit faire diverger `adeptMorvenn` (son
    fold NATIF disparait cote port) et ne RIEN changer pour les deux autres (ils n'en avaient
    pas). Sans ce bras, on ne saurait pas que la mesure sait voir un fold qui MANQUE."""
    for v, r in r3b_rows.items():
        if r["folds"]:
            assert r["d_nofold"], (
                f"{v} (temoin POSITIF) : vider le registre ne DEPLACE RIEN -- la mesure ne sait "
                f"pas voir un fold absent, l'accord des autres porteurs est vide")
        else:
            assert not r["d_nofold"], (
                f"{v} : vider le registre DEPLACE le port ({r['d_nofold']}) -- il foldait donc "
                f"deja, contrairement au natif")


def test_le_cleave_natif_retire_des_pv_a_la_cible_additionnelle(r3b_case, rpc):
    """(4) LA FACE COMBAT EST BIEN LA. L'asymetrie n'est pas « ces abilities ne font rien » : le
    natif inflige le degat additionnel en EXECUTION, sur les ennemis adjacents a la fois au caster
    et a la cible. Ce test ECRIT donc dans l'etat du runner -- il est joue en dernier."""
    for v in R3B.CLEAVERS:
        try:
            m = R3B.measure_combat(rpc, r3b_case, v)
        except R3B.MontageError as e:
            pytest.fail(str(e), pytrace=False)
        assert m["primaire"] > 0, (
            f"{v} : la cible PRIMAIRE ne perd aucun PV -- l'attaque normale n'a pas eu lieu")
        assert m["additionnelle"] > 0, (
            f"{v} (ability {m['ability']}) : la cible ADDITIONNELLE ne perd AUCUN PV alors "
            f"qu'elle est adjacente au caster ET a la cible -- le cleave natif n'a pas eu lieu "
            f"(deltas mesures : {m['tous_deltas']})")
