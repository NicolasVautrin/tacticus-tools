"""#409-r1 -- un cliquet NOMME par la banque sans en etre une ENTREE n'est joue par RIEN.

LE GISEMENT, ET POURQUOI LES DEUX GARDES DE LA BANQUE ETAIENT AVEUGLES
-----------------------------------------------------------------------
`probe_319_scan_fidelity.py` -- SEUL garde de la fidelite de `probe_273` -- a crashe des mois
(`AttributeError: _root_vars`) sans que rien ne le signale, et derriere, son montage etait
perime par #349. Il echappait aux deux gardes que la banque a sur elle-meme :

  * `probe_439` (etape principale) ne juge que les ENTREES -- un recenseur ne peut pas rendre
    zero sur ce qu'il ne visite pas ;
  * `probe_486r2` cherche un probe a la fois ORPHELIN et NON EXECUTABLE. `probe_319` etait
    NOMME (dans les docs) ET executable : ni orphelin, ni muet -- simplement jamais joue.

CE QUI RESTAIT OUVERT ETAIT LE PROCESSUS, pas la reparation : `probe_319` est entre dans la
banque, mais rien ne garantissait que le PROCHAIN garde y entre.

LE CRITERE EST BORNE, ET C'EST CE QUI LE REND UTILISABLE. Mesure du 2026-08-08 :
  * << tout probe doit etre un cliquet >> : 906 probes -- l'immense majorite sont des MESURES,
    pas des gardes. Inutilisable ;
  * << tout fichier qui NOMME un cliquet de la banque >> : 35 fichiers, presque tous de
    simples citations en docstring. Trop bruyant ;
  * << un `probe_*.py` cite dans `ratchets.ps1`, prose comprise >> : **38 nommes, 37 entrees,
    1 ecart** -- et cet ecart etait REEL (`probe_486r12_declencheurs.py`).

Le troisieme est retenu : il porte sur ce que la banque DIT D'ELLE-MEME.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_439_cliquet_peut_rougir.py",
        "scripts/ratchets.ps1",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Il n'eprouve que l'etape `etape_nommes_hors_banque` de `probe_439` et le contrat de "
        "declaration `# HORS-BANQUE:` que la banque porte. Les cas de mutation substituent "
        "`BANQUE` par un fichier de `tmp_path` : aucune autre entree n'est lue."
    ),
}

import sys                                                                    # noqa: E402
from pathlib import Path                                                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import probe_439_cliquet_peut_rougir as R                                     # noqa: E402

#: Un `Argv` minimal, de la forme que `banque_par_texte` rend.
ARGVS = {"probe_x": ["probe_x_garde.py"]}


def _banque(tmp_path, monkeypatch, corps: str, existants=("probe_x_garde.py",)):
    """Ecrit une banque synthetique et fait pointer `probe_439` dessus."""
    b = tmp_path / "ratchets.ps1"
    b.write_text(corps, encoding="utf-8")
    pyd = tmp_path / "python"
    pyd.mkdir(exist_ok=True)
    for nom in existants:
        (pyd / nom).write_text("# vide\n", encoding="utf-8")
    monkeypatch.setattr(R, "BANQUE", b)
    monkeypatch.setattr(R, "PY_DIR", pyd)


# =====================================================================================
#  [1] LE CRAN MORD -- un cliquet nomme, non entree, non exempte
# =====================================================================================
def test_un_cliquet_NOMME_sans_etre_ENTREE_est_ROUGE(tmp_path, monkeypatch, capsys):
    _banque(tmp_path, monkeypatch,
            "# probe_319_scan_fidelity.py garde la fidelite de probe_x_garde.py\n",
            existants=("probe_x_garde.py", "probe_319_scan_fidelity.py"))
    assert R.etape_nommes_hors_banque(ARGVS) == 1
    out = capsys.readouterr().out
    assert "probe_319_scan_fidelity.py" in out and "n'est joue par RIEN" in out


def test_une_ENTREE_de_la_banque_n_est_PAS_accusee(tmp_path, monkeypatch, capsys):
    """Contre-epreuve : sans elle, un cran qui accuserait TOUT passerait pour vert-sur-rien."""
    _banque(tmp_path, monkeypatch, "# la banque joue probe_x_garde.py\n")
    assert R.etape_nommes_hors_banque(ARGVS) == 0
    assert "ROUGE" not in capsys.readouterr().out


# =====================================================================================
#  [2] L'EXEMPTION -- explicite, MOTIVEE, et gardee dans les DEUX directions
# =====================================================================================
def test_une_exemption_MOTIVEE_eteint_le_rouge(tmp_path, monkeypatch, capsys):
    _banque(tmp_path, monkeypatch,
            "# probe_319_scan_fidelity.py est cite ici\n"
            "# HORS-BANQUE: probe_319_scan_fidelity.py -- il rend rc=99 par construction, "
            "son empreinte perime a chaque changement de cliquet\n",
            existants=("probe_x_garde.py", "probe_319_scan_fidelity.py"))
    assert R.etape_nommes_hors_banque(ARGVS) == 0
    assert "hors banque, motive" in capsys.readouterr().out


def test_une_raison_TROP_COURTE_est_refusee(tmp_path, monkeypatch, capsys):
    """Une raison qui tient en trois mots ne dit pas POURQUOI, elle constate."""
    _banque(tmp_path, monkeypatch,
            "# probe_319_scan_fidelity.py\n"
            "# HORS-BANQUE: probe_319_scan_fidelity.py -- trop cher\n",
            existants=("probe_x_garde.py", "probe_319_scan_fidelity.py"))
    assert R.etape_nommes_hors_banque(ARGVS) == 1
    assert "trop courte" in capsys.readouterr().out


def test_une_raison_MULTILIGNE_est_lue_ENTIEREMENT(tmp_path, monkeypatch, capsys):
    """Faute commise a la premiere passe : 39 caracteres lus pour une raison de sept lignes,
    donc un cran qui refusait une raison qu'il avait lui-meme tronquee."""
    _banque(tmp_path, monkeypatch,
            "# probe_319_scan_fidelity.py\n"
            "# HORS-BANQUE: probe_319_scan_fidelity.py -- il rend rc=99\n"
            "#  par construction, et sa remesure exige de rejouer TOUTE la banque\n"
            "#  sous audit hook.\n",
            existants=("probe_x_garde.py", "probe_319_scan_fidelity.py"))
    assert R.etape_nommes_hors_banque(ARGVS) == 0
    src = (tmp_path / "ratchets.ps1").read_text(encoding="utf-8")
    raison = R.exemptions_hors_banque(src)["probe_319_scan_fidelity.py"]
    assert "audit hook" in raison, raison
    assert len(raison) > R.RAISON_HORS_BANQUE_MIN


def test_une_exemption_qui_designe_une_ENTREE_est_MORTE(tmp_path, monkeypatch, capsys):
    _banque(tmp_path, monkeypatch,
            "# HORS-BANQUE: probe_x_garde.py -- une raison parfaitement longue et detaillee "
            "qui ne devrait jamais servir\n")
    assert R.etape_nommes_hors_banque(ARGVS) == 1
    assert "EST une entree" in capsys.readouterr().out


def test_une_exemption_dont_le_FICHIER_a_disparu_est_MORTE(tmp_path, monkeypatch, capsys):
    _banque(tmp_path, monkeypatch,
            "# probe_disparu_x.py\n"
            "# HORS-BANQUE: probe_disparu_x.py -- une raison parfaitement longue et detaillee "
            "qui ne designe plus rien\n")
    assert R.etape_nommes_hors_banque(ARGVS) == 1
    assert "ABSENT du disque" in capsys.readouterr().out


def test_une_exemption_que_la_banque_ne_NOMME_PLUS_est_MORTE(tmp_path, monkeypatch, capsys):
    """L'exemption ne masque plus rien : c'est du copier-colle qui a l'air de faire quelque
    chose -- meme regle que le bypass MORT de #486-r24."""
    b = tmp_path / "ratchets.ps1"
    pyd = tmp_path / "python"
    pyd.mkdir()
    (pyd / "probe_x_garde.py").write_text("# vide\n", encoding="utf-8")
    (pyd / "probe_ailleurs_y.py").write_text("# vide\n", encoding="utf-8")
    # Le marqueur est retire du corps : on simule une banque qui ne cite plus le probe, mais
    # dont l'exemption survit dans un artefact lu a part.
    b.write_text("# la banque joue probe_x_garde.py\n", encoding="utf-8")
    monkeypatch.setattr(R, "BANQUE", b)
    monkeypatch.setattr(R, "PY_DIR", pyd)
    monkeypatch.setattr(R, "exemptions_hors_banque",
                        lambda src: {"probe_ailleurs_y.py": "r" * 60})
    assert R.etape_nommes_hors_banque(ARGVS) == 1
    assert "ne le NOMME nulle part" in capsys.readouterr().out


# =====================================================================================
#  [3] LE TEMOIN SUR LE DEPOT REEL -- le critere doit etre NON VIDE et BORNE
# =====================================================================================
def test_sur_le_depot_REEL_le_critere_est_non_vide_et_borne():
    """Un critere qui ne designerait RIEN, ou qui designerait TOUT, ne garde rien.

    Les deux bornes sont assertionnees : la banque nomme au moins ses propres entrees (non
    vide), et l'ecart nommes/entrees reste de l'ordre de l'unite (borne) -- si un jour il
    explose, c'est le critere qu'il faut relire, pas le depot qu'il faut nettoyer.
    """
    src = R.BANQUE.read_text(encoding="utf-8", errors="replace")
    argvs = R.banque_par_texte()
    entrees = {a.rsplit("/", 1)[-1] for lst in argvs.values() for a in lst
               if a.endswith(".py")}
    nommes = set(R._RX_PROBE_NOMME.findall(src))
    assert len(entrees) > 20, "la banque REELLE doit porter ses entrees (temoin non nul)"
    assert entrees <= nommes, "toute entree est, par construction, nommee par la banque"
    assert len(nommes - entrees) <= 3, sorted(nommes - entrees)
