"""#970-r3 -- garde LIVE de la face DECISION `1200 SquigLaunchas` : le gate NATIF separe-t-il la
ou le port separe ?

Mesure : `probe_970r3_squig_launchas_live.py` (un runner, un build, et l'on passe du regime
SEPARANT au regime PASSANT en DEPLACANT un Ork au contact de la cible).

Ce que cette garde verrouille, et pourquoi chaque cran existe :

  * **LE REGIME EST SEPARANT, ET IL EST NON DEGENERE.** La cible du regime A est LEGALE -- elle est
    dans `abilityTargets(...).fromHere`, donc le gate de CIBLAGE natif l'accepte -- et pourtant le
    playbook la REFUSE. Sans face DECISION, le port la proposait.
  * **LE TEMOIN EST NON NUL.** Le natif emet en regime B. Un accord << 0 des deux cotes partout >>
    ne prouverait rien -- et c'est exactement ce qui s'est produit a la premiere passe, avec un
    capteur muet (cf. ci-dessous).
  * **LE CAPTEUR EST LE BON, ET IL EST VERIFIE.** `ncEvaluate` est STRUCTURELLEMENT AVEUGLE AUX
    MACHINES OF WAR (son hook filtre sur `ty === EntityType.Unit`, une MoW est
    `EntityType.Machine`) : il rend `ok: false` pour 1200 COMME pour `1201 SquigMine`, dont le
    playbook NC est pourtant porte et valide. Le probe LEVE desormais sur `ok: false` au lieu de
    lire l'echec comme un refus, et passe par `ncPlaybookPredict(via="evaluate")`. La garde exige
    en plus que le natif ait charge `SquigLaunchasPlaybook` (champ `playbookClass` echoe) : sans ce
    cran, un mauvais appariement d'ability rendrait les chiffres d'une AUTRE classe.
  * **LES BORNES DU TIRAGE SONT LUES, PAS SUPPOSEES.** Les utilites natives doivent tomber dans
    `[1, 9]` (`NextInternal` : `min + (g % (max - min))`, borne haute EXCLUE), et VARIER -- ce qui
    distingue un TIRAGE d'une constante, et donc justifie que le port ne porte pas la valeur
    (residu `#970-r6`) au lieu de la fitter.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        'scripts/python/probe_970r3_squig_launchas_live.py',
    ),
    "build": False,
    "toujours": False,
    "raison": "UN seul chemin a declarer, et c'est le probe : il porte le MONTAGE (roster, "
              "`--place`, board, le deplacement qui fait basculer le regime), le CAPTEUR "
              "(`ncPlaybookPredict` plutot qu'`ncEvaluate`, aveugle aux MoW) et la table des "
              "verdicts. Le toucher change ce que la garde MESURE sans toucher au code porte, et "
              "rien d'autre ne le verrait -- la face portee elle-meme est deja gardee, offline et "
              "a chaque passe, par `test_970r3_squig_launchas_decision_offline.py`, dont le "
              "DECLENCHEUR enumere ses foyers. `build: False` : aucune valeur n'est figee depuis "
              "le binaire -- les seuils sont RELEVES au gameconfig et les utilites natives sont "
              "seulement BORNEES, jamais comparees a un litteral. `toujours: False` : le fichier "
              "monte un runner et coute ~60 s.",
}

import sys                                                          # noqa: E402
from pathlib import Path                                            # noqa: E402

import pytest                                                       # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]                         # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_970r3_squig_launchas_live as P                         # noqa: E402


@pytest.fixture(scope="module")
def v():
    sf = PYDIR.parents[1] / "logs" / "t970r3_live_pytest.json"
    return P.run(str(sf), verbose=False)


def _reg(v, tag):
    return next((x for x in (v.get("regimes") or []) if x["libelle"].startswith(tag)), None)


def test_le_montage_a_tenu(v):
    """Rien a conclure d'un montage qui n'a pas atteint ses deux regimes : le probe DIT ce qui a
    manque (move non mordu, tuile de contact introuvable, capteur muet) au lieu de rendre un zero."""
    assert not v.get("erreurs"), "montage/capteur en faute : %s" % v["erreurs"]
    assert _reg(v, "A") and _reg(v, "B"), "regimes incomplets -- NON CONFRONTE"


def test_la_cible_du_regime_separant_est_LEGALE(v):
    """C'est ce qui fait la SEPARATION : la cible passe le gate de CIBLAGE natif
    (`...$$GetDynamicInvalidTargetReason`) et echoue seulement au gate du PLAYBOOK
    (`...$$FulfillsSummonCriteria`, seuils PLUS HAUTS)."""
    A = _reg(v, "A")
    assert A["port_eligibles"] >= 1, (
        "aucune cible legale en regime A : ce n'est pas un regime separant, juste une absence "
        "de cible")
    assert A["orks_adjacents"] == 1, "regime A : %d Ork(s) adjacent(s)" % A["orks_adjacents"]


def test_le_natif_a_charge_le_playbook_attendu(v):
    for tag in ("A", "B"):
        assert _reg(v, tag)["playbookClass"] == ["SquigLaunchasPlaybook"], (
            "regime %s : le natif a charge %s" % (tag, _reg(v, tag)["playbookClass"]))


def test_le_temoin_est_non_nul(v):
    """Un accord << 0 partout >> est DEGENERE. Le natif doit emettre quelque part, sinon la garde
    ne distingue pas << le gate refuse >> de << le capteur est muet >>."""
    assert _reg(v, "B")["natif_actions"] >= 1, (
        "le natif n'emet nulle part : l'accord du regime A ne prouve RIEN")


def test_le_gate_natif_refuse_en_regime_separant(v):
    assert _reg(v, "A")["natif_actions"] == 0, (
        "le natif EMET sur une cible que le critere de summon refuse : la RE du gate est fausse")


def test_le_port_concorde_avec_le_natif_dans_les_deux_regimes(v):
    for tag, attendu in (("A", 0), ("B", 1)):
        r = _reg(v, tag)
        assert (r["port_candidats"] > 0) == (r["natif_actions"] > 0), (
            "regime %s : port=%d candidat(s), natif=%d action(s)"
            % (tag, r["port_candidats"], r["natif_actions"]))
        assert (r["port_candidats"] > 0) == (attendu > 0), (
            "regime %s : port=%d, attendu %s" % (tag, r["port_candidats"], attendu))


def test_les_utilites_natives_sont_dans_les_bornes_LUES(v):
    """`Next(1, 10)` -> `[1, 9]`, borne haute EXCLUE. Un `10` prouverait que la borne est mal lue,
    un `0` que la borne basse l'est."""
    utils = _reg(v, "B")["natif_utils"]
    assert utils, "aucune utilite relevee : la borne n'est pas mesuree"
    hors = [u for u in utils if not (1 <= float(u) <= 9)]
    assert not hors, "utilites HORS [1,9] : %s" % hors


def test_l_utilite_native_VARIE_donc_c_est_un_tirage(v):
    """Ce qui justifie `#970-r6` : la valeur n'est pas portable, donc le port pose la borne BASSE
    (identite sur l'argmax) au lieu de fitter du bruit. Si toutes les invocations rendaient la
    MEME valeur, ce serait une CONSTANTE et le port devrait la porter.

    Risque de faux rouge si c'est bien un tirage uniforme sur 9 valeurs : `9 * (1/9)^(N-1)`, soit
    ~2e-6 pour N = 8."""
    utils = _reg(v, "B")["natif_utils"]
    assert len(utils) >= 2, "une seule invocation : la variabilite n'est pas mesurable"
    assert len(set(utils)) >= 2, (
        "les %d invocations rendent la MEME utilite %s : ce n'est pas un tirage"
        % (len(utils), sorted(set(utils))))
