#!/usr/bin/env python3
"""#330-r3 -- la FORME d'un hash de build se DERIVE de l'arbre, et son echec est BRUYANT.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE
-----------------------------------------------
`probe_330` et `probe_431` portaient chacun `r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])"`. Le
suffixe `6c` etait une REGULARITE des six premiers builds observes, pas une regle : le build
courant `t6dpr4k06g` finit en `6g`. Les deux recenseurs comptaient donc 2 905 occurrences en
etant AVEUGLES aux 176 du build courant -- et `probe_431` est le cliquet DES LITTERAUX DE BUILD,
donc ses candidats derivaient de sa propre cecite.

La meme regularite avait deja tue un capteur en LIVE (`build-pin.ts`, `/^[a-z0-9]{8}6c$/`,
#10011) : `installedBuild()` nul, ONZE pins refuses, et un `test_le_natif_suit_le_PORT` VERT sur
zero assertion evaluee.

CE QUI EST TESTE ICI, ET DANS QUEL SENS CHAQUE ASSERTION PEUT TOMBER
---------------------------------------------------------------------
1. le build COURANT est reconnu par les DEUX foyers -- l'invariant qui manquait ;
2. la forme generique reconnait CHAQUE build connu, et sa contre-epreuve : rebranchee sur
   l'ANCIENNE forme, `verifier_la_forme()` LEVE. Sans cette contre-epreuve, (1) ne prouverait
   rien -- une derivation qui part de `CURRENT` ne peut pas rater `CURRENT`, et un invariant
   vrai par construction est celui qu'on cesse de mesurer ;
3. les deux foyers portent le MEME motif -- les separer, c'etait garantir qu'ils divergent, et
   ils avaient diverge (la doctrine a corrige `build-pin.ts` sans voir ces deux-ci) ;
4. AUCUN hash de build n'est ecrit en dur dans le code executable des trois modules -- le vice
   exact que ce residu nomme : ajouter `t6dpr4k06g` en dur aurait fait passer `probe_431` au
   VERT en GAGNANT le gisement qu'il existe pour tenir ;
5. le tri-etat des entrees hors depot (`None`, jamais `[]`) ;
6. le RECENSEMENT ne regresse pas : tout jeton que l'ANCIENNE forme voyait dans l'arbre est
   soit un build connu, soit un jeton SYNTHETIQUE d'un fichier de test. Sans ce point, on
   aurait echange un angle mort contre un autre.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PYDIR = REPO / "scripts" / "python"
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import build_hash as BH  # noqa: E402
import probe_330_prose_va_and_build_stamps as P330  # noqa: E402
import probe_431_build_literals as P431  # noqa: E402

#: LA forme d'avant, telle qu'elle etait ecrite dans les deux foyers. Elle ne sert QU'A la
#: contre-epreuve et au temoin de non-regression -- c'est la seule place du depot ou elle a
#: encore le droit d'exister, et elle y est INERTE.
ANCIENNE_FORME = re.compile(r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])")

#: Les trois modules dont le metier EST de reconnaitre un hash : aucun ne doit en porter un.
FOYERS = ("build_hash.py",
          "probe_330_prose_va_and_build_stamps.py",
          "probe_431_build_literals.py")


# ================================================ 1. le build COURANT, vu par les DEUX foyers


def test_le_build_COURANT_est_reconnu_par_les_deux_foyers():
    """L'invariant qui manquait, et le seul qui compte pour un lecteur.

    `BUILD_RE.search(current_build())` rendait `None` dans les deux modules. Un recenseur qui
    ne voit pas le build courant rend un compte qui a l'air d'une mesure -- 2 905 occurrences
    vues, 176 invisibles.
    """
    courant = BH.rapport_des_sources()["courant"]
    assert courant, "data/symbols/CURRENT illisible -- rien ne peut etre mesure"
    for nom, rx in (("probe_330", P330.BUILD_RE), ("probe_431", P431.BUILD_RE)):
        assert rx.fullmatch(courant) is not None, (
            "%s ne reconnait pas le build COURANT (%s) -- c'est EXACTEMENT #330-r3"
            % (nom, courant))
    # Et il est vu DANS une phrase, pas seulement en isolation : les deux probes cherchent
    # dans du texte, jamais sur une chaine deja isolee.
    phrase = "table lue sur le build %s, migration depuis rnca9r7q6c" % courant
    assert P330.BUILD_RE.search(phrase).group(1) == courant
    assert P431.BUILD_RE.search(phrase).group(1) == courant


def test_les_deux_foyers_portent_le_MEME_motif():
    """Le code disait deja << les deux comptes doivent rester comparables >>, et les portait
    quand meme separement. Un litteral duplique diverge : c'est ce qui a laisse `probe_330:81`
    (`DECLARES_RE`) porter une TROISIEME copie de la meme forme."""
    assert P330.BUILD_RE.pattern == P431.BUILD_RE.pattern
    # `DECLARES_RE` embarque le meme motif, pas une copie -- c'est la 3e occurrence historique.
    assert P330.BUILD_RE.pattern in P330.DECLARES_RE.pattern


# ============================================== 2. la FORME generique, et sa CONTRE-EPREUVE


def test_la_forme_generique_reconnait_chaque_build_CONNU():
    """La forme est une HYPOTHESE ; ici elle est confrontee a l'arbre, pas supposee."""
    connus = BH.builds_connus()
    assert len(connus) >= 2, (
        "moins de deux builds connus (%s) -- l'assertion suivante serait DEGENERE" % connus)
    invisibles = [b for b in connus if not BH.FORME.fullmatch(b)]
    assert invisibles == [], (
        "la forme generique ne voit plus %s -- l'elargir, et surtout PAS y ecrire le nouveau "
        "suffixe (ce serait la meme faute, avec une date de peremption plus lointaine)"
        % invisibles)
    assert BH.verifier_la_forme() is not None


def test_CONTRE_EPREUVE_l_ANCIENNE_forme_fait_REFUSER(monkeypatch):
    """LA demonstration : rebranche sur `[a-z0-9]{8}6c`, le cran MORD.

    Sans elle, le test precedent serait vacant : la derivation part de `CURRENT`, donc elle ne
    peut pas rater `CURRENT`. Ce qui doit etre prouve, c'est que le cran est capable de
    REFUSER -- et le seul regime ou on sait qu'il le doit est celui qu'on vient de reparer.
    """
    courant = BH.rapport_des_sources()["courant"]
    assert ANCIENNE_FORME.fullmatch(courant) is None, (
        "le build courant (%s) finit en `6c` : la contre-epreuve ne prouverait rien sur ce "
        "build-la. Choisir un autre temoin, ne pas la retirer." % courant)
    monkeypatch.setattr(BH, "FORME", ANCIENNE_FORME)
    with pytest.raises(BH.FormeRefusee) as exc:
        BH.verifier_la_forme()
    msg = str(exc.value)
    assert "FORME PERIMEE" in msg
    assert courant in msg, "le refus doit NOMMER le build qu'il ne voit plus, sinon il est muet"
    assert "suffixe" in msg, "le refus doit dire ce qu'il ne faut PAS faire (ecrire `6g`)"


def test_CONTRE_EPREUVE_le_cliquet_431_ROUGIT_quand_la_forme_est_REFUSEE(monkeypatch, capsys):
    """Le refus ne doit pas rester dans le module : il doit atteindre le `rc` du cliquet.

    En-process et sur UN fichier (`tracked_files` substitue) : la propriete est celle du
    verdict, pas du volume -- meme montage que l'etape 0 de `probe_431`.
    """
    monkeypatch.setattr(BH, "FORME", ANCIENNE_FORME)
    monkeypatch.setattr(P431, "tracked_files", lambda: ["CLAUDE.md"])
    monkeypatch.setattr(sys, "argv", ["probe_431_build_literals.py", "--cliquet"])
    rc = P431.main()
    out = capsys.readouterr().out
    assert rc == 1, "GARDE-MUET : une forme perimee n'a pas fait rougir le cliquet\n" + out
    assert "FORME REFUSEE" in out or "FORME PERIMEE" in out, out


def test_TEMOIN_le_cliquet_431_ne_rougit_PAS_de_ce_chef_avec_la_forme_courante(monkeypatch,
                                                                               capsys):
    """Le pendant du precedent : un garde qui refuse TOUJOURS ne garde rien.

    On ne peut pas exiger `rc == 0` (le cliquet a d'autres axes, et l'arbre porte des
    RESOLUTIONs reelles) -- on exige que le motif de refus SPECIFIQUE soit absent.
    """
    monkeypatch.setattr(P431, "tracked_files", lambda: ["CLAUDE.md"])
    monkeypatch.setattr(sys, "argv", ["probe_431_build_literals.py", "--cliquet"])
    P431.main()
    out = capsys.readouterr().out
    assert "FORME REFUSEE" not in out and "FORME PERIMEE" not in out, out


# ============================================= 3. AUCUN hash en dur dans les foyers eux-memes


def _constantes_executables(src: str, nom: str) -> list:
    """Les chaines de l'AST qui ne sont NI un docstring -- les commentaires n'y sont pas."""
    arbre = ast.parse(src, filename=nom)
    docs = set()
    for node in ast.walk(arbre):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corps = getattr(node, "body", None)
            if corps and isinstance(corps[0], ast.Expr) \
                    and isinstance(corps[0].value, ast.Constant) \
                    and isinstance(corps[0].value.value, str):
                docs.add(id(corps[0].value))
    return [n for n in ast.walk(arbre)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


@pytest.mark.parametrize("fichier", FOYERS)
def test_aucun_hash_de_build_n_est_ECRIT_EN_DUR_dans_les_foyers(fichier):
    """LE vice que ce residu nomme, rendu executable.

    « Un correctif qui ajouterait `t6dpr4k06g` en dur ferait passer `probe_431` VERT en gagnant
    son propre gisement. » Ici, l'interdit porte sur les trois modules qui RECONNAISSENT un
    hash -- y compris en simple message, parce qu'un exemple ecrit dans un `print` se recopie.
    La prose (docstrings, commentaires) reste libre : c'est la qu'on CITE les builds observes.
    """
    connus = set(BH.builds_connus())
    assert connus, "aucun build connu -- l'assertion serait vacante"
    src = (PYDIR / fichier).read_text(encoding="utf-8")
    fautes = []
    for node in _constantes_executables(src, fichier):
        for b in connus:
            if b in node.value:
                fautes.append((getattr(node, "lineno", 0), b, node.value[:60]))
    assert fautes == [], (
        "%s ECRIT un hash de build en dur : %s\n"
        "  C'est exactement la reparation qui gagne son propre gisement. La liste des builds "
        "se DERIVE (`build_hash.builds_connus`)." % (fichier, fautes))


# ============================================================ 4. le POSITIONNEL, et le BRUIT


def test_le_critere_POSITIONNEL_voit_un_build_et_pas_le_bruit_de_meme_forme():
    """Ce qui identifie un build est sa POSITION, pas sa forme -- transpose de `build-pin.ts`.

    Les quatre jetons de bruit ci-dessous sont REELS : ils sortent du balayage de l'arbre par
    la forme generique seule (128 jetons distincts pour 4 builds reels sur le seul seau
    executable). Substituee telle quelle dans `probe_431`, elle faisait passer le cliquet de 3
    a 27 RESOLUTIONs, dont 24 de bruit pur.
    """
    vus = BH.POSITION.findall(
        r"C:\Users\x\AppData\Local\tacticus\games\aaaa1111zz\GameAssembly.dll "
        "et data/dumps/bbbb2222yy/dump.cs et data/symbols/cccc3333xx/ghidra/functions.tsv")
    assert vus == ["aaaa1111zz", "bbbb2222yy", "cccc3333xx"], vus
    # Le bruit de MEME forme, hors position : la forme le voit, la position ne le voit pas.
    bruit = "undefined8 cibles1444 c4battle75 probe366r1"
    assert sorted(BH.FORME.findall(bruit)) == ["c4battle75", "cibles1444",
                                               "probe366r1", "undefined8"]
    assert BH.POSITION.findall(bruit) == []


def test_l_inventaire_de_forme_ECARTE_les_litteraux_hexadecimaux():
    """`0x7fffffff` fait dix caracteres et melange chiffres et lettres : 33 jetons distincts,
    422 occurrences dans le seul seau executable. C'est un ECART, et il est DIT."""
    assert BH.FORME.findall("0x7fffffff 0x40000000") == []
    # Temoin : sans le `(?!0x)`, ils passeraient -- l'ecart mord donc bien sur ces valeurs-la.
    sans_ecart = re.compile(
        r"(?<![a-z0-9])(?=[a-z0-9]*[0-9])(?=[a-z0-9]*[a-z])([a-z0-9]{10})(?![a-z0-9])")
    assert sans_ecart.findall("0x7fffffff 0x40000000") == ["0x7fffffff", "0x40000000"]


def test_les_candidats_de_forme_ne_comptent_JAMAIS_un_build_connu():
    """L'inventaire est le complementaire des connus -- sinon les deux comptes se doubleraient."""
    connus = BH.builds_connus()
    texte = " ".join(connus) + " undefined8 cibles1444"
    cand = BH.candidats_de_forme(texte)
    assert set(cand) == {"undefined8", "cibles1444"}, cand


# ============================================ 5. tri-etat des entrees, et refus sans cible


def test_l_installation_locale_est_TRI_ETAT_jamais_une_liste_vide(monkeypatch, tmp_path):
    """Entree HORS depot : `None` = pas mesuree. Un `[]` se lirait << aucun build installe >>,
    ce qui est une MESURE -- et c'est la faute que `host_inputs` nomme."""
    monkeypatch.setattr(BH, "GAMES_DIR", tmp_path / "absent")
    assert BH._installes() is None
    (tmp_path / "present").mkdir()
    monkeypatch.setattr(BH, "GAMES_DIR", tmp_path / "present")
    assert BH._installes() == [], "repertoire PRESENT et vide : c'est une mesure, donc []"


def test_le_balayage_positionnel_est_TRI_ETAT_quand_git_est_muet(monkeypatch):
    """`git ls-files` muet -> `None`. Un ensemble ampute en silence redonnerait au recenseur
    l'angle mort qu'on lui retire."""
    monkeypatch.setattr(BH, "_fichiers_suivis", lambda: None)
    assert BH._positions_dans_le_depot() is None


def test_build_re_REFUSE_plutot_que_de_rendre_un_motif_qui_ne_matche_rien(monkeypatch):
    """Zero build connu -> refus. Un motif vide rendrait `0 occurrence`, et ce zero se lirait
    comme une mesure -- la forme exacte du bug qu'on repare."""
    monkeypatch.setattr(BH, "_cache", {
        "tables_versionnees": [], "courant": None, "position_de_chemin": [],
        "installation_locale": None, "connus": []})
    with pytest.raises(BH.FormeRefusee):
        BH.build_re()
    with pytest.raises(BH.FormeRefusee):
        BH.verifier_la_forme()


def test_les_sources_sont_DERIVEES_et_le_rapport_les_NOMME():
    """Un ensemble derive doit dire d'ou il sort, sinon il est indiscernable d'une liste saisie."""
    rap = BH.rapport_des_sources()
    assert set(rap) == {"tables_versionnees", "courant", "position_de_chemin",
                        "installation_locale", "connus"}
    assert rap["courant"] in rap["connus"]
    assert set(rap["tables_versionnees"]) <= set(rap["connus"])
    # La source 2 apporte des builds que la source 1 n'a pas : c'est ce qui remplace la liste
    # ecrite a la main des builds historiques. Si elle n'apportait rien, la derivation serait
    # reduite a `data/symbols/` -- a dire, pas a subir.
    assert rap["position_de_chemin"] is not None, "balayage positionnel NON MESURE"
    assert set(rap["position_de_chemin"]) - set(rap["tables_versionnees"]), (
        "la position de chemin n'apporte AUCUN build de plus que les tables versionnees -- "
        "verifier que le balayage lit bien l'arbre (sources : %s)" % rap)


# ================================================== 6. le RECENSEMENT ne REGRESSE pas


def test_AUCUN_build_vu_par_l_ANCIENNE_forme_n_est_PERDU():
    """On a elargi la cible ; il faut prouver qu'on n'en a pas laisse tomber une moitie.

    Les jetons que l'ancienne forme voyait dans l'arbre et que la nouvelle ne voit pas doivent
    etre SYNTHETIQUES -- ecrits par un fichier de test pour eprouver un refus. Mesure du
    2026-08-15 : 10 jetons vus par l'ancienne, 7 builds reels + 4 mutants de
    `test_431_build_pin_offline.py` (`aaaaaaaa6c`, `bbbbbbbb6c`, `rrrrrrrr6c`, `zzzzzzzz6c`),
    ce dernier etant de toute facon EXEMPTE du cliquet au titre d'auto-test.
    """
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, "git ls-files muet -- NON MESURE, pas 'aucune perte'"
    exclus = ("data/symbols/", ".claude/worktrees/", "node_modules/", "frida/dist/")
    fichiers = [p for p in r.stdout.split("\0")
                if p and not any(p.startswith(x) for x in exclus)]
    assert len(fichiers) > 1000, "arbre trop petit pour que ce temoin dise quoi que ce soit"
    connus = set(BH.builds_connus())
    perdus: dict = {}
    for rel in fichiers:
        try:
            texte = (REPO / rel).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        for h in ANCIENNE_FORME.findall(texte):
            if h not in connus:
                perdus.setdefault(h, set()).add(rel)
    # Non-vacuite : l'ancienne forme DOIT encore voir quelque chose, sinon ce temoin ne teste
    # rien (elle voyait 2 905 occurrences le jour du correctif).
    vus_total = sum(1 for rel in fichiers
                    if ANCIENNE_FORME.search(
                        (REPO / rel).read_bytes().decode("utf-8", errors="replace")))
    assert vus_total > 100, "l'ancienne forme ne voit plus rien : ce temoin est devenu vacant"
    porteurs = sorted({f for fs in perdus.values() for f in fs})
    non_tests = [f for f in porteurs if "/tests/" not in f and not Path(f).name.startswith("test_")]
    assert non_tests == [], (
        "des jetons de l'ancienne forme sont PERDUS hors des fichiers de test : %s\n"
        "  jetons : %s\n"
        "  Un build reel doit entrer par `build_hash` (table versionnee, position de chemin ou "
        "installation), jamais par une forme devinee." % (non_tests, sorted(perdus)))
