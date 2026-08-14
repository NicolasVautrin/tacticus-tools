"""#468 -- CONTRE-EPREUVE du cliquet << un numero attribue deux fois >>.

Deux exigences symetriques, et les DEUX doivent tenir :
  * le cliquet ROUGIT sur une collision fabriquee -- sinon il occupe la place d'un garde-fou
    en s'imprimant << rien a signaler >> (le vice de #439) ;
  * il reste VERT sur les renvois LEGITIMES du depot REEL -- sinon il rougit sur tout, ce qui
    est pire que rien : il se fait desarmer en une journee.

L'echantillon negatif n'est PAS synthetique. Ce sont les lignes du `backlog.md` et les noms de
case-docs du depot : le dossier est plein de renvois croises (une case-doc qui cite le residu
d'une autre, une colonne << Point d'entree >> qui pointe la voisine), et c'est exactement ce
qu'un critere par simple presence de `#<n>` ferait rougir.

⚠ SUR UNE CONTRE-EPREUVE, VERT EST LE RESULTAT SUSPECT. Chaque mutation est donc verifiee DEUX
fois : le bras NON MUTE doit etre vert, et le bras MUTE rouge. Un bras mute qui reste vert peut
signifier que la mutation n'a pas MORDU (patch qui ne matche pas, chemin ignore), pas que le
detecteur est indulgent.

Arbre jetable : `mkdtemp()` SANS `dir=` -- un cliquet n'ecrit JAMAIS sous `scripts/python`, la
banque tourne en parallele (#455).

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend. Liste EXPLICITE et non `scripts/python/*.py` : le
        # glob large retiendrait ce test a chaque modification d'un probe quelconque.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/probe_468_collision_numeros.py",
        # MESURE : la declaration << arbres synthetiques seulement >> etait FAUSSE. Des cas
        # font tourner le detecteur sur le corpus REEL (`docs/rl`, 7 chemins vus par la
        # confrontation) et lisent le ledger de numeros versionne.
        "docs/rl/**", "scripts/ratchets-468-numeros-attestes.json",
        # #547-r2 : le CACHE des sujets de commit, LU par le probe pour son corpus `git log`.
        # L'empreinte REECRITE en entier l'a montre ; l'ancienne, partielle, le cachait.
        "scripts/ratchets-468-sujets-de-commit.txt",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le seul probe sous test. Ses cas montent des arbres SYNTHETIQUES en repertoire "
              "temporaire, donc ni `docs/rl/` ni `git log` du depot reel n'entrent dans son "
              "verdict -- c'est le probe lui-meme qui est juge, pas le corpus.",
}

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_468_collision_numeros as p468  # noqa: E402

PROBE = PYDIR / "probe_468_collision_numeros.py"


@pytest.fixture(autouse=True)
def le_registre_du_depot_REEL_ne_bouge_pas():
    """AUCUN test de ce fichier ne doit ALLOUER dans le registre PARTAGE du depot reel.

    CE GARDE EXISTE PARCE QUE CE FICHIER A COMMIS LA FAUTE (2026-08-11). Depuis #468-r14,
    `suggerer` ALLOUE : deux cas d'ici l'appellent EN PROCESS apres `viser(<depot jetable>)`, et
    la premiere version de `_vider_reservations` remettait `REPO` en dur au lieu de restaurer la
    cible precedente. Resultat MESURE : deux entrees parasites dans
    `<principal>/.git/tacticus-468-reservations` -- `#917` et `#900-r8`, reconnaissables a leur
    metadonnee (meme pid, `pour` vide) -- soit deux entiers brules pour tout le monde, et
    indistinguables d'une allocation legitime une fois posees.

    Le registre est PARTAGE et SURVIT a tout : c'est ce qui fait la valeur du remede, et c'est
    ce qui le rend polluable. Il verifie aussi que la cible de `viser` a ete rendue -- c'est par
    la que la faute est arrivee, et un test qui la laisse ailleurs fait tourner le SUIVANT ou il
    ne croit pas.

    ⚠ L'ACCUSATION SE PORTE PAR AUTEUR, PAS PAR FENETRE TEMPORELLE (#935). La premiere version
    comparait la POPULATION avant/apres et accusait << ce test >> de toute entree neuve. Or ce
    registre est partage par 35 worktrees et des agents qui allouent en continu : mesure du
    2026-08-11, `#936` y est apparu pendant ce test, alloue par `worktree-agent-ab5c3278368678ce3`
    (pid 62856) -- ni par ce test, ni meme depuis ce worktree. Le cliquet rougissait donc EXACTEMENT
    quand la campagne tourne, c'est-a-dire quand on a le plus besoin de lui, et un cliquet qui
    accuse a tort se fait desarmer. Le discriminant est le `pid` ecrit dans la metadonnee : la
    faute mesuree (`#917`, `#900-r8`) etait une allocation EN PROCESS, donc `os.getpid()`. Les
    entrees d'un AUTRE pid sont de la concurrence : elles sont IMPRIMEES, jamais accusees.

    PORTEE -- ce que ce garde ne voit pas : une allocation faite par un SOUS-PROCESSUS de ce
    fichier. Elle est couverte par l'autre bout, statiquement et sur le futur, par
    `test_aucun_sous_process_de_ce_fichier_ne_vise_le_depot_REEL` : les quinze appels de
    `--suggere` d'ici passent tous `--racine <depot jetable>`, donc ecrivent dans le registre du
    jetable."""
    p468.viser(REPO)
    dossier = p468._dossier_reservations()
    avant = set(p468._identifiants_des_reservations(dossier))
    yield
    cible = p468.REPO
    p468.viser(REPO)
    apres = set(p468._identifiants_des_reservations(dossier))
    neuves = set(apres) - set(avant)
    if neuves:
        par_cle = {p468.normaliser(k): ctx for k, ctx in p468.lire_reservations(dossier)}
        miennes = sorted(k for k in neuves if par_cle.get(k, {}).get("pid") == os.getpid())
        tierces = sorted(k for k in neuves if k not in miennes)
        if tierces:
            print("[468] concurrence pendant ce test (allocations d'AUTRES processus, non "
                  "imputables) : %s" % ", ".join("#" + k for k in tierces))
        assert not miennes, (
            "ce test a ALLOUE dans le registre PARTAGE du depot reel : %s -- ces numeros sont "
            "desormais brules pour tout le monde" % ", ".join("#" + k for k in miennes))
    assert cible == REPO, (
        "ce test a laisse `viser` pointe sur %s : le test SUIVANT tournerait ailleurs qu'il ne "
        "croit" % cible)

#: Ce qui doit changer pour que cette contre-epreuve puisse changer d'avis.
#:
#: Une contre-epreuve est normalement de PORTEE 4 -- son verdict ne depend que de {la source du
#: cliquet teste, la sienne}, puisque tout ce qu'elle monte est FABRIQUE. Celle-ci ne l'est PAS :
#: son echantillon NEGATIF est le depot REEL -- `docs/rl/backlog.md` (lignes de tableau et de
#: continuation), les NOMS de `docs/rl/case-*.md`, et des SUJETS DE COMMIT reels que
#: `definitions_du_backlog` doit lire comme des MENTIONS.
#:
#: ELLE ETAIT `toujours: True`, ET C'EST #486-r18 QUI L'A FERME. Les sujets de commit venaient de
#: `git log --format=%s -n 400`, lu EN DIRECT : l'historique bouge a chaque commit, donc sous
#: toute selection par diff l'echantillon avait change PAR CONSTRUCTION, et les **140,9 s** du
#: fichier (46 tests) etaient rejouees a CHAQUE passe. L'historique PASSE etant immuable, le
#: geler ne perd rien de ce qu'il portait : `scripts/ratchets-468-sujets-de-commit.txt` porte
#: **2 444** sujets distincts contre **374** dans la fenetre vivante -- l'echantillon est
#: ~6,5x plus RICHE, et il est desormais un CHEMIN, donc declarable.
#:
#: ⚠ CE QUI EST PERDU EST BORNE ET NOMME : les formes de sujet inventees APRES le gel. Elles
#: reviennent au premier `--geler-sujets`, et l'artefact porte le commit de son gel pour que sa
#: peremption se LISE. La contre-epreuve n'est PAS affaiblie : c'est elle qui etablit que le
#: critere ne rougit pas sur les mentions, et elle porte plus de mentions qu'avant.
DECLENCHEUR = {
    "chemins": ("docs/rl/*", "docs/rl/**",
                "scripts/ratchets-468-sujets-de-commit.txt",
                "scripts/ratchets-468-numeros-attestes.json",
                "scripts/python/probe_468_collision_numeros.py",
                "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
                "scripts/python/green_skip_guard.py", "scripts/python/pytest.ini"),
    "build": False,
    "toujours": False,
    "raison": "Contre-epreuve de portee 4 SAUF pour son echantillon negatif, qui est le depot "
              "reel : `docs/rl` et l'echantillon GELE de sujets de commit -- tous deux des "
              "CHEMINS depuis #486-r18, donc bornables. Elle ne lit plus `git log`.",
}


# ==========================================================================================
#  L'ECHANTILLON NEGATIF : le depot REEL, ses renvois croises compris
# ==========================================================================================

def _lignes_backlog_reel():
    return (REPO / "docs" / "rl" / "backlog.md").read_text(encoding="utf-8").splitlines()


def test_le_depot_reel_separe_definitions_et_mentions():
    """Le critere doit porter sur la POSITION, pas sur la presence.

    Si la quasi-totalite des `#<n>` du depot etait lue comme une definition, le cliquet
    rougirait sur les renvois legitimes -- et ce depot en est plein."""
    total, defs, fichiers = p468.ventiler_occurrences()
    assert fichiers > 100, "corpus trop maigre pour conclure quoi que ce soit"
    assert total > 1000, "moins de 1000 occurrences : l'echantillon negatif n'est pas represente"
    part = 100.0 * defs / total
    assert part < 30.0, (
        "%.1f%% des occurrences sont lues comme des DEFINITIONS (%d/%d) : le detecteur ne separe "
        "plus definition et mention" % (part, defs, total))


def test_aucune_mention_reelle_du_backlog_n_est_lue_comme_definition():
    """Les lignes de CONTINUATION (indentees) portent des dizaines de renvois `#<n>` : aucune
    ne doit ouvrir un dossier. C'est la forme la plus dense de faux positif possible."""
    lignes = _lignes_backlog_reel()
    continuations = [l for l in lignes
                     if l.startswith(("  ", "\t")) and "#" in l]
    assert len(continuations) > 50, "pas assez de lignes de continuation pour que le test morde"
    assert p468.definitions_du_backlog(continuations) == []


def test_les_messages_de_commit_ne_definissent_rien():
    """`git log --grep` depend des numeros, mais un message de commit est une MENTION.

    L'echantillon est GELE depuis #486-r18 (`scripts/ratchets-468-sujets-de-commit.txt`) : lu en
    direct, il rendait cette contre-epreuve non bornable, donc `toujours: True`, donc 140,9 s
    rejouees a chaque passe.
    """
    sujets = p468.lire_sujets_geles()
    assert len(sujets) > 500, ("echantillon trop maigre pour mordre : %d" % len(sujets))
    assert p468.definitions_du_backlog(sujets) == []


def test_l_echantillon_GELE_porte_les_sujets_qui_COMMENCENT_par_un_numero():
    """LE TEMOIN NON NUL DU GEL, et il garde une faute REELLE.

    La convention habituelle `#` = commentaire aurait ampute le corpus de ses lignes les PLUS
    adversariales -- celles dont la premiere colonne ressemble le plus a une definition de
    backlog (`#175-e / #175-r : ...`). Mesure du 2026-08-08 : **142** sujets sur 2 444 sont dans
    ce cas, et un lecteur naif les jetait tous en rendant un corpus qui se lit comme un vert.
    """
    sujets = p468.lire_sujets_geles()
    en_tete = [s for s in sujets if s.startswith("#")]
    assert len(en_tete) > 50, (
        "l'echantillon ne porte que %d sujet(s) commencant par `#` : soit le gel les ampute, "
        "soit le corpus a change de nature -- dans les deux cas c'est a relire" % len(en_tete))
    assert p468.definitions_du_backlog(en_tete) == []


def test_un_echantillon_ABSENT_LEVE_au_lieu_de_valider_tout(tmp_path, monkeypatch):
    """Un echantillon adversarial vide validerait TOUT : c'est le faux vert absolu."""
    monkeypatch.setattr(p468, "SUJETS_GELES", tmp_path / "n-existe-pas.txt")
    with pytest.raises(p468.Indisponible):
        p468.lire_sujets_geles()
    vide = tmp_path / "vide.txt"
    vide.write_text("# entete seule\n" + p468.SENTINELLE_SUJETS + "\n", encoding="utf-8")
    monkeypatch.setattr(p468, "SUJETS_GELES", vide)
    with pytest.raises(p468.Indisponible):
        p468.lire_sujets_geles()
    sans = tmp_path / "sans-sentinelle.txt"
    sans.write_text("# entete\nun sujet\n", encoding="utf-8")
    monkeypatch.setattr(p468, "SUJETS_GELES", sans)
    with pytest.raises(p468.Indisponible):
        p468.lire_sujets_geles()


#: Ce qui RESSEMBLE a une definition en 1re cellule, defini INDEPENDAMMENT du probe : un `|`,
#: un `#`, un token alphanumerique, la fermeture de cellule. Deliberement plus large que
#: `ID_POSITION` (il tolere un `-` final) -- c'est ce qui rend l'invariant ci-dessous
#: DISCRIMINANT : tout retrecissement de la grammaire du probe le fait rougir, tout
#: elargissement le laisse vert.
_OUVRE_UNE_CELLULE = re.compile(
    r"^\|\s*(~~)?\s*[`*]*\s*#([0-9a-zA-Z][0-9a-zA-Z-]*)\s*[`*]*\s*(~~)?\s*\|")


def test_aucune_ligne_de_tableau_du_backlog_REEL_n_echappe_au_detecteur():
    """#468-r1 -- L'INVARIANT, PAS UN SEUIL : zero ligne invisible.

    LE DEFAUT N'ETAIT PAS UN REPLIEMENT, C'ETAIT UNE DISPARITION. L'ancienne grammaire `ID`
    s'arretait au premier segment qu'elle ne savait pas lire (`-c1`, `-b-r1`, `-src`, `-1`), et
    comme `RE_LIGNE_TABLEAU` exige un `|` JUSTE APRES l'identifiant, la ligne ENTIERE cessait de
    correspondre. MESURE le 2026-08-15 sur `backlog.md` : **72 lignes de tableau** ne produisaient
    AUCUNE definition -- familles `#462-r4b-...-b/-c-r<k>` (31), `#462-r4e-o-r<k>` (9),
    `#366-r1-<mot>` (13), `#433-r4-r2-r1-r1-a/c-r<k>` (3), `#443-r2-b<k>` (2), plus les
    identifiants non numeriques `#o10-a/-c`, `#PAI-c/-k`, `#BL-*`, `#haze-ord`, `#254-bc*`.
    L'etape 1 leur etait STRUCTURELLEMENT aveugle.

    ⚠ AUCUNE ALLOWLIST, et c'est le point. Le critere est DERIVE de la forme d'une ligne, pas
    d'une liste de familles connues : une convention d'ecriture inventee demain entre dans le
    balayage sans que personne y pense -- c'est precisement ce que la liste des 72 aurait rate,
    puisque personne ne l'avait ecrite."""
    lignes = _lignes_backlog_reel()
    vues = {d.ou for d in p468.definitions_du_backlog(lignes)}
    candidates, invisibles = 0, []
    for n, ligne in enumerate(lignes, 1):
        m = _OUVRE_UNE_CELLULE.match(ligne)
        if not m:
            continue
        candidates += 1
        if "backlog.md:%d" % n not in vues:
            invisibles.append((n, m.group(2)))
    assert candidates > 500, (
        "seulement %d ligne(s) de tableau candidates dans le backlog reel -- le balayage est "
        "devenu aveugle, un `0 invisible` ne prouverait plus rien" % candidates)
    assert not invisibles, (
        "%d ligne(s) de tableau du backlog n'est/ne sont AUCUNE definition pour le detecteur -- "
        "l'etape 1 leur est aveugle : %s" % (len(invisibles), invisibles[:12]))


def test_bout_en_bout_une_DOUBLE_OUVERTURE_a_segment_alphanumerique_ROUGIT():
    """La generalisation de l'invariant ci-dessus au CABLAGE, pas seulement au detecteur.

    Voir une ligne ne suffit pas : ce qui compte est que l'etape 1 rougisse sur DEUX lignes
    ouvertes portant un identifiant de cette famille. Avant #468-r1, ces deux lignes-la ne
    produisaient aucune definition, donc aucun double, donc un VERT."""
    for ident in ("462-r4e-o-r2-r1", "366-r1-camo-seed", "PAI-c", "443-r2-b1", "222-1"):
        #: BRAS TEMOIN -- UNE seule ligne : le depot doit rester VERT, sinon le bras rouge
        #: n'accuserait pas la double ouverture mais la simple presence de l'identifiant.
        seul = _depot_jetable(BASE_SAINE + [_ligne(ident, "un sujet")], [])
        try:
            rc, txt = _jouer(seul)
            assert rc == 0, "#%s : une definition SEULE ne doit rien faire rougir :\n%s" % (
                ident, txt)
        finally:
            shutil.rmtree(seul, ignore_errors=True)

        r = _depot_jetable(BASE_SAINE + [_ligne(ident, "un sujet"),
                                         _ligne(ident, "un AUTRE sujet, meme numero")], [])
        try:
            rc, txt = _jouer(r)
            assert rc != 0, "#%s : la double ouverture n'a pas MORDU :\n%s" % (ident, txt)
            assert "etape 1 : 1 identifiant" in txt and "FAIL #%s" % ident in txt, txt
        finally:
            shutil.rmtree(r, ignore_errors=True)


def _arbre_de_puces(fichiers):
    """Un `docs/rl` jetable ne portant que des case-docs, pour la 4e position (#468-r7)."""
    racine = _depot_jetable(BASE_SAINE, [])
    for nom, corps in fichiers.items():
        (racine / "docs" / "rl" / nom).write_text(corps, encoding="utf-8")
    return racine


def test_la_4e_POSITION_separe_une_DEFINITION_de_puce_d_une_RE_CITATION():
    """#468-r7 -- le critere de SECTION seul NE SEPARE PAS, et c'est une mesure.

    Sur le depot reel il rend **33** identifiants portes par une puce ouverte dans deux
    case-docs ou plus ; les neuf qui survivent au discriminant PROPRIETAIRE ont ete lus un par
    un et sont **9/9 legitimes**. Ce test fige les trois regles du discriminant, dont la
    troisieme -- << sans proprietaire, toutes les puces definissent >> -- sans laquelle le cas
    MOTIVANT du residu (`case-467` ouvrant `#472-r1`) serait perdu."""
    corps = ("# titre\n\n## 1. Le defaut\n\n"
             "- **#500-r9** une puce HORS section Residus : jamais une definition.\n\n"
             "%s")
    racine = _arbre_de_puces({
        "case-500-un-sujet.md": corps % "## Residus\n\n- **#500-r1** le residu du sujet.\n",
        "case-600-un-autre.md": corps % "## Residus\n\n- **#500-r1** -- inchange, cf. case-500.\n",
        "case-700-orphelin.md": corps % "## Residus\n\n- **#800-r1** ouvert ICI, nulle part ailleurs.\n",
    })
    precedent = p468.REPO
    try:
        p468.viser(racine)
        defs, cites = p468.puces_des_case_docs()
        ou_def = {d.cle: sorted(x.ou for x in defs if x.cle == d.cle) for d in defs}
        ou_cite = {d.cle: sorted(x.ou for x in cites if x.cle == d.cle) for d in cites}
        # (1) hors section Residus : rien, dans aucun des deux seaux.
        assert "500r9" not in ou_def and "500r9" not in ou_cite, (ou_def, ou_cite)
        # (2) le PROPRIETAIRE par prefixe definit, le voisin ne fait que citer.
        assert ou_def.get("500r1") == ["case-500-un-sujet.md:9"], ou_def
        assert ou_cite.get("500r1") == ["case-600-un-autre.md:9"], ou_cite
        # (3) SANS proprietaire, la puce definit -- c'est le cas MOTIVANT du residu.
        assert ou_def.get("800r1") == ["case-700-orphelin.md:9"], ou_def
    finally:
        p468.viser(precedent)
        shutil.rmtree(racine, ignore_errors=True)


def test_les_case_docs_reelles_se_coupent_en_identifiant_et_slug():
    noms = sorted(p.name for p in (REPO / "docs" / "rl").glob("case-*.md"))
    assert len(noms) > 300
    for nom in noms:
        ident, _slug = p468.couper_nom(Path(nom).stem)
        assert ident, nom
        assert not ident.endswith("-"), nom


# ==========================================================================================
#  LES TROIS FORMES, fabriquees
# ==========================================================================================

#: Une ligne de tableau du backlog, a la forme reelle.
def _ligne(ident, titre, tag="`[opus]`", ptr="`case-x`", barre=False):
    if barre:
        return "| ~~#%s~~ | ~~**%s**~~ | **LIVRE (2026-08-04)** | %s |" % (ident, titre, ptr)
    return "| #%s | **%s** | %s | %s |" % (ident, titre, tag, ptr)


BASE_SAINE = [
    "| # | Tache | Modele | Point d'entree |",
    "|---|---|---|---|",
    _ligne("900", "un sujet"),
    _ligne("900-r1", "un residu du sujet", ptr="`case-900` ; voir aussi #901 et #900-r2"),
    _ligne("901", "un autre sujet, qui CITE #900-r1 dans son texte"),
    _ligne("902", "un sujet clos", barre=True),
    "",
    "## Residus documentes",
    "- **`#900-r2`** -- un residu ouvert par puce.",
    "  Sa continuation cite #900-r1, #901 et `case-900-quelque-chose.md` : ce sont des MENTIONS.",
]


def test_forme_A_double_ouverture_au_backlog():
    """Deux lignes OUVERTES pour un meme identifiant = deux taches sous un numero."""
    sain = p468.etape1_double_ouverture(p468.definitions_du_backlog(BASE_SAINE))
    assert sain == [], "le bras NON MUTE doit etre vert : %r" % (sain,)

    mute = BASE_SAINE + [_ligne("900-r1", "un TOUT AUTRE sujet, pris au vol")]
    trouve = p468.etape1_double_ouverture(p468.definitions_du_backlog(mute))
    assert len(trouve) == 1, "la mutation n'a pas MORDU : %r" % (trouve,)
    cle, defs = trouve[0]
    assert cle == "900r1" and len(defs) == 2


def test_forme_A_une_ligne_BARREE_ne_compte_pas():
    """Un dossier CLOS qui cohabite avec une re-ouverture du meme sujet n'est pas une collision.

    C'est la restriction qui ecarte `#27-r4` et `#437-r1` du depot reel -- sans elle, le cliquet
    rougirait sur toute tache ré-ouverte."""
    mute = BASE_SAINE + [_ligne("900-r1", "le meme sujet, re-ouvert", barre=True)]
    assert p468.etape1_double_ouverture(p468.definitions_du_backlog(mute)) == []


def test_forme_A_les_deux_graphies_se_rejoignent():
    """`#900-r1` et `#900r1` sont le MEME residu : une collision ne doit pas passer entre les
    deux ecritures (le depot emploie les deux -- `case-366-r1-*` a cote de `case-366r1-*`)."""
    mute = BASE_SAINE + [_ligne("900r1", "sujet different, graphie collee")]
    trouve = p468.etape1_double_ouverture(p468.definitions_du_backlog(mute))
    assert len(trouve) == 1 and trouve[0][0] == "900r1"


def test_forme_B_cohabitation_ouvert_et_case_doc():
    """Un numero OUVERT au backlog dont une case-doc porte deja le meme identifiant."""
    defs_b = p468.definitions_du_backlog(BASE_SAINE)
    sain = p468.etape2_cohabitations(defs_b, p468.definitions_des_case_docs(
        ["case-902-le-dossier-clos.md", "case-903-un-numero-libre.md"]))
    assert sain == [], "le bras NON MUTE doit etre vert : %r" % (sain,)

    trouve = p468.etape2_cohabitations(defs_b, p468.definitions_des_case_docs(
        ["case-902-le-dossier-clos.md", "case-900-r1-un-autre-sujet.md"]))
    assert len(trouve) == 1, "la mutation n'a pas MORDU : %r" % (trouve,)
    cle, ligne, cases = trouve[0]
    assert cle == "900r1" and cases[0].ou == "case-900-r1-un-autre-sujet.md"
    assert ligne.ouverte


def test_forme_C_deux_case_docs_n_est_PAS_un_critere():
    """MESURE, pas opinion : la troisieme forme relevee a l'oeil est INDECIDABLE.

    Sur le depot reel, 30+ identifiants portent >= 2 case-docs, et ce sont des TRANCHES d'une
    meme tache livrees au fil de l'eau (`case-217-blackrage` / `-stormcaller` / ...). Rien ne
    distingue textuellement un multi-items d'une collision : meme numero, sujets sans rapport.
    Ce test FIGE le constat -- si un jour un critere separait les deux, il faudrait le REFUTER
    ici avant de faire rougir la forme."""
    noms = sorted(p.name for p in (REPO / "docs" / "rl").glob("case-*.md"))
    par_cle = {}
    for d in p468.definitions_des_case_docs(noms):
        par_cle.setdefault(d.cle, []).append(d)
    multi = {k: v for k, v in par_cle.items() if len(v) > 1}
    assert len(multi) >= 20, (
        "seulement %d identifiants a >= 2 case-docs : si ce gisement s'est tari, la forme "
        "redevient peut-etre gardable -- le re-examiner" % len(multi))
    # Et le gisement est bien fait de tranches, pas de collisions : les identifiants les plus
    # charges sont des taches-parapluie connues.
    assert max(len(v) for v in multi.values()) >= 4


# ==========================================================================================
#  BOUT-EN-BOUT : le cablage (lecture, ledger, code de sortie), pas seulement les detecteurs
# ==========================================================================================

def _depot_jetable(lignes_backlog, case_docs, attestations=None):
    racine = Path(tempfile.mkdtemp(prefix="p468_"))       # SANS dir= : #455
    (racine / "docs" / "rl").mkdir(parents=True)
    (racine / "scripts").mkdir()
    (racine / "docs" / "rl" / "backlog.md").write_text(
        "\n".join(lignes_backlog) + "\n", encoding="utf-8")
    for nom in case_docs:
        (racine / "docs" / "rl" / nom).write_text("# %s\n" % nom, encoding="utf-8")
    if attestations is not None:
        (racine / "scripts" / "ratchets-468-numeros-attestes.json").write_text(
            json.dumps({"attestations": attestations}), encoding="utf-8")
    return racine


def _jouer(racine):
    out = subprocess.run([sys.executable, str(PROBE), "--racine", str(racine)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=str(PYDIR))
    return out.returncode, out.stdout + out.stderr


def test_bout_en_bout_vert_puis_rouge_sur_chaque_forme():
    """Le bras SAIN doit rendre 0, sinon les deux bras rouges ne prouveraient rien."""
    sain = _depot_jetable(BASE_SAINE, ["case-902-le-dossier-clos.md"])
    try:
        rc, txt = _jouer(sain)
        assert rc == 0, "le bras SAIN doit etre vert :\n%s" % txt
        assert "VERDICT: PASS" in txt
    finally:
        shutil.rmtree(sain, ignore_errors=True)

    # Forme A -- double ouverture
    a = _depot_jetable(BASE_SAINE + [_ligne("900-r1", "un autre sujet")], [])
    try:
        rc, txt = _jouer(a)
        assert rc != 0, "forme A : la mutation n'a pas MORDU :\n%s" % txt
        assert "etape 1 : 1 identifiant" in txt and "FAIL #900-r1" in txt
    finally:
        shutil.rmtree(a, ignore_errors=True)

    # Forme B -- cohabitation ouvert x case-doc
    b = _depot_jetable(BASE_SAINE, ["case-900-r1-un-autre-sujet.md"])
    try:
        rc, txt = _jouer(b)
        assert rc != 0, "forme B : la mutation n'a pas MORDU :\n%s" % txt
        assert "NON attestee" in txt and "case-900-r1-un-autre-sujet.md" in txt
    finally:
        shutil.rmtree(b, ignore_errors=True)


def test_bout_en_bout_une_attestation_eteint_la_cohabitation_pas_la_double_ouverture():
    """Les deux constats sont INDEPENDANTS : attester l'un ne doit pas dispenser de l'autre.

    Sans la portee `@backlog`, une attestation de cohabitation aurait eteint la double ouverture
    du meme identifiant -- un silencieux pose par megarde."""
    lignes = BASE_SAINE + [_ligne("900-r1", "un autre sujet")]
    r = _depot_jetable(lignes, ["case-900-r1-un-autre-sujet.md"],
                       attestations={"900r1|case-900-r1-un-autre-sujet.md": "tranche de la meme tache"})
    try:
        rc, txt = _jouer(r)
        assert rc != 0, "la double ouverture doit SUBSISTER :\n%s" % txt
        assert "FAIL #900-r1" in txt
        assert "etape 2 : 1 cohabitation(s) ouvert-x-case-doc, 0 NON attestee" in txt
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_une_attestation_sans_raison_est_REFUSEE():
    """Une attestation vide serait un blanc-seing : le mode d'ecriture la refuse (rc 2)."""
    r = _depot_jetable(BASE_SAINE, [])
    try:
        out = subprocess.run([sys.executable, str(PROBE), "--racine", str(r),
                              "--attester", "900r1|case-x.md="],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(PYDIR))
        assert out.returncode == 2 and "REFUS" in out.stdout
    finally:
        shutil.rmtree(r, ignore_errors=True)


# ==========================================================================================
#  LE TRI-ETAT (#471) : un chemin qui ne peut pas rendre les TROIS ne vaut rien
# ==========================================================================================

def test_tri_etat_montage_absent_rend_99_et_non_un_rouge():
    """`docs/rl` introuvable = MONTAGE en echec : un dépôt PARFAIT le subirait aussi.

    Rendre `1` ici accuserait le dépôt d'une panne de harnais -- le vice exact que #471 a mesuré
    sur `probe_457:s3` (rouge de gisement pour un `git ls-files` en 128)."""
    racine = Path(tempfile.mkdtemp(prefix="p468_vide_"))   # SANS docs/rl
    try:
        rc, txt = _jouer(racine)
        assert rc == p468.EX_INDISPONIBLE, "attendu 99 (INDISPONIBLE), vu %d :\n%s" % (rc, txt)
        assert "INDISPONIBLE" in txt and "docs/rl introuvable" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_tri_etat_un_backlog_VIDE_est_un_ROUGE_pas_un_indisponible():
    """La frontière à ne pas laisser glisser : `docs/rl` existe, le registre a disparu.

    C'est un fait sur le CONTENU du dépôt, comme « `git ls-files` rc=0 et liste vide »."""
    racine = _depot_jetable([], [])
    try:
        rc, txt = _jouer(racine)
        assert rc == 1, "attendu 1 (ROUGE), vu %d :\n%s" % (rc, txt)
        assert "absent ou vide" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_tri_etat_un_ledger_au_json_invalide_est_un_ROUGE():
    """Le ledger est DANS le dépôt : son contenu invalide accuse le dépôt, pas la machine."""
    racine = _depot_jetable(BASE_SAINE, ["case-900-r1-un-autre-sujet.md"])
    (racine / "scripts" / "ratchets-468-numeros-attestes.json").write_text("{ pas du json",
                                                                          encoding="utf-8")
    try:
        rc, txt = _jouer(racine)
        assert rc == 1, "attendu 1 (ROUGE), vu %d :\n%s" % (rc, txt)
        assert "JSON invalide" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_le_ledger_du_depot_est_lisible_et_chaque_entree_porte_une_raison():
    """Un ledger dont une entree serait vide desarmerait le cliquet en silence."""
    att = p468.lire_ledger()
    brut = json.loads((REPO / "scripts" / "ratchets-468-numeros-attestes.json")
                      .read_text(encoding="utf-8"))["attestations"]
    assert att == brut, "une entree du ledger a ete rejetee (raison vide ou non-chaine)"
    for cle, raison in att.items():
        assert "|" in cle, cle
        assert raison.strip(), cle


# ==========================================================================================
#  `--suggere` (#468-r4) -- le critere s'INVERSE : ici l'UNION, mentions comprises
# ==========================================================================================

def _depot_git(lignes_backlog, case_docs=(), messages=(), merge=None):
    """Depot jetable AVEC historique -- `--suggere` refuse de mesurer sans lui.

    `merge` : sujet d'un commit de MERGE a fabriquer par-dessus (#468-r13). Les deux commits
    ordinaires qu'il reunit portent des sujets SANS numero, et le contenu n'en porte pas non
    plus : le sujet du merge est alors la SEULE trace du numero dans tout le depot -- exactement
    la situation de `#432-r1`, livre par la PR #479 et introuvable de `git grep`."""
    racine = _depot_jetable(lignes_backlog, case_docs)
    (racine / "scripts" / "python").mkdir(parents=True, exist_ok=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ.get("PATH", "")}
    def git(*a):
        subprocess.run(["git", "-C", str(racine)] + list(a), check=True,
                       capture_output=True, env=env)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "socle")
    for m in messages:
        (racine / "docs" / "rl" / "backlog.md").write_text(
            (racine / "docs" / "rl" / "backlog.md").read_text(encoding="utf-8") + "\n",
            encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", m)
    if merge:
        # Le nom de la branche par defaut n'est PAS suppose (`master` / `main` selon la config
        # de la machine) : on le LIT. Une supposition ferait echouer le montage, donc rougir le
        # test pour la mauvaise cause.
        tete = subprocess.run(["git", "-C", str(racine), "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env).stdout.strip() or "master"
        git("checkout", "-q", "-b", "cote-jetable")
        (racine / "docs" / "rl" / "note-laterale.md").write_text("aucun numero\n",
                                                                encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "branche laterale, aucun numero")
        git("checkout", "-q", tete)
        (racine / "docs" / "rl" / "note-principale.md").write_text("aucun numero\n",
                                                                   encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "avance de la principale, aucun numero")
        git("merge", "-q", "--no-ff", "-m", merge, "cote-jetable")
    return racine


def _suggere(racine, *args):
    out = subprocess.run([sys.executable, str(PROBE), "--racine", str(racine), "--suggere"]
                         + [a for a in args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=str(PYDIR))
    return out.returncode, out.stdout + out.stderr


def test_aucun_sous_process_de_ce_fichier_ne_vise_le_depot_REEL():
    """L'AUTRE BOUT du garde `le_registre_du_depot_REEL_ne_bouge_pas` (#935).

    Ce garde-la accuse par `pid`, donc il ne voit pas un SOUS-PROCESSUS. Celui-ci ferme la porte
    par l'autre cote, et STATIQUEMENT -- donc sur du code qui n'a pas encore tourne : tout appel
    de `probe_468` lance depuis ce fichier doit passer `--racine`, et cette racine ne doit jamais
    etre `REPO`. C'est ce qui rend l'accusation par pid SUFFISANTE ; sans lui, la reduction de
    portee serait un trou.

    Derive de l'AST de CE fichier : un appel futur non conforme rougit sans que personne ait a y
    penser -- c'est le meme principe que le declencheur derive plutot qu'enumere."""
    arbre = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    fautifs = []
    vus = 0
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        #: la LISTE d'arguments d'un `subprocess.run([...])` -- seule forme employee ici.
        if not isinstance(n.args[0], ast.List):
            continue
        #: on descend DANS chaque element : la forme reelle est `[sys.executable, str(PROBE),
        #: "--racine", str(racine), "--suggere"]` -- ni `PROBE` ni `racine` n'y sont des
        #: `ast.Name` DIRECTS. Une lecture au premier niveau rendait `vus = 0`, et c'est
        #: l'anti-vacuite qui l'a dit (elle a mordu au premier rejeu).
        litteraux, noms = [], []
        for e in n.args[0].elts:
            for sous in ast.walk(e):
                if isinstance(sous, ast.Constant) and isinstance(sous.value, str):
                    litteraux.append(sous.value)
                elif isinstance(sous, ast.Name):
                    noms.append(sous.id)
        if "PROBE" not in noms and not any("probe_468" in s for s in litteraux):
            continue
        vus += 1
        if "--racine" not in litteraux:
            fautifs.append((n.lineno, "aucun `--racine` : le sous-process viserait le depot REEL"))
            continue
        if "REPO" in noms:
            fautifs.append((n.lineno, "`--racine REPO` : c'est le depot REEL"))
    assert vus, ("aucun lancement de `probe_468` en sous-process trouve dans ce fichier -- le "
                 "balayage est devenu aveugle, il ne prouverait plus rien")
    assert not fautifs, (
        "sous-process(es) de ce fichier visant le depot REEL : %s -- une allocation faite la "
        "brulerait un numero pour tout le monde, et le garde par `pid` ne la verrait pas"
        % fautifs)


def _vider_reservations(racine):
    """Efface les RESERVATIONS du depot jetable, entre les deux bras d'une meme contre-epreuve.

    POURQUOI C'EST OBLIGATOIRE DEPUIS #468-r14, ET LA MESURE QUI L'ETABLIT. `--suggere` n'OBSERVE
    plus, elle ALLOUE : le premier appel d'un test RESERVE son numero, donc le second l'ecarterait
    DE TOUTE FACON -- quelle que soit la source du corpus qu'on est en train de mettre a l'epreuve.
    Les cinq tests ci-dessous auraient continue de passer en accusant la mauvaise cause.

    MESURE (2026-08-11), en coupant chaque source hors-arbre dans le probe et en rejouant les
    tests qui la gardent :

        source coupee dans `probe_468`   | AVANT #468-r14 | APRES, sans ce vidage
        ---------------------------------|----------------|----------------------
        `_identifiants_des_pr`           |    2 ROUGES    |      2 VERTS
        `_identifiants_des_worktrees`    |    2 ROUGES    |      2 VERTS
        `_identifiants_des_refs_hors_head`|    1 ROUGE    |      1 VERT

    Vider entre les deux bras ISOLE l'axe mesure ici -- les sources du CORPUS. La reservation,
    elle, n'est pas laissee sans garde : elle a son propre cliquet, et il porte la contre-epreuve
    de concurrence (`tests/test_468r14_reservation_offline.py`).

    ⚠ IL RESTAURE LA CIBLE PRECEDENTE, PAS `REPO`. Deux des cinq tests appellent `p468.suggerer`
    EN PROCESS, apres avoir vise le depot jetable : un helper qui remettrait `REPO` en dur ferait
    repartir le bras suivant sur le depot REEL, qui rend evidemment un autre numero -- le test
    passerait pour la mauvaise raison. Faute commise a la premiere ecriture de ce helper, vue
    parce que la contre-epreuve du desarmement rendait << 1 failed, 1 passed >> la ou les deux
    devaient rougir.
    """
    precedent = p468.REPO
    p468.viser(racine)
    try:
        dossier = p468._dossier_reservations()
    finally:
        p468.viser(precedent)
    shutil.rmtree(dossier, ignore_errors=True)


def test_suggere_ne_rend_RIEN_quand_le_corpus_est_AMPUTE():
    """Le point de conception : une mesure incomplete ne rend JAMAIS de numero.

    Suggerer sur un corpus ampute fabrique exactement la collision qu'on pretend eviter --
    c'est la lecon des 13 racines qui ne vivent que dans les messages de commit. Sans depot
    git, l'historique est illisible : INDISPONIBLE (99), et AUCUN numero imprime."""
    racine = _depot_jetable(BASE_SUGGERE, [])          # PAS de `git init`
    try:
        rc, txt = _suggere(racine)
        assert rc == 99, "un corpus ampute doit rendre 99, pas %d :\n%s" % (rc, txt)
        assert "LIBRE" not in txt, "un numero a ete suggere sur un corpus ampute :\n%s" % txt
        assert "INDISPONIBLE" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def _numero_propose(txt):
    return txt.split("LIBRE : #")[1].splitlines()[0].strip()


#: LE CORPUS DE LA SECTION `--suggere` VIT AU-DESSUS DE LA BANDE (#468-r8), ET C'EST CE QUI
#: GARDE CES TESTS DISCRIMINANTS.
#:
#: Depuis la bande, une racine neuve est allouee a `max(borne + 1, PLANCHER_RACINE)`. Sur un
#: depot jetable dont la borne est `902`, le numero propose serait donc `10000` QUOI QU'IL
#: ARRIVE -- et toute assertion de la forme << le numero X n'a pas ete propose >> deviendrait
#: VACANTE : verte que la source qui rend X invisible fonctionne ou non. Sept tests etaient dans
#: ce cas (worktree voisin, ref hors HEAD, corps de PR, message de commit, mention en prose).
#:
#: Le remede n'est PAS d'affaiblir ces assertions mais de placer le corpus dans le regime ou
#: elles mordent : au-dessus du plancher, c'est de nouveau `borne + 1` qui commande, donc le
#: numero propose redevient sensible a ce que le corpus voit. La bande, elle, est gardee par ses
#: propres tests (`test_la_BANDE_*`, `test_l_INTERVALLE_*`).
BASE_SUGGERE = [
    "| # | Tache | Modele | Point d'entree |",
    "|---|---|---|---|",
    _ligne("10900", "un sujet"),
    _ligne("10900-r1", "un residu du sujet", ptr="`case-10900` ; voir aussi #10901"),
    _ligne("10901", "un autre sujet, qui CITE #10900-r1 dans son texte"),
    _ligne("10902", "un sujet clos", barre=True),
]

#: La borne de `BASE_SUGGERE` : `10902` est la plus grande racine DEFINIE que son backlog
#: connait (barree ou non -- la borne mesure l'espace employe, pas ce qui reste ouvert). La
#: suggestion demarre donc a `10903`, et c'est CE numero que les tests suivants doivent voir
#: ecarte. Sans cette contrainte ils ne DISCRIMINENT pas : viser `#10901`, deja defini, les
#: rendait verts meme apres mutation du probe -- mesure a la contre-epreuve.
PREMIER_AU_DESSUS = "10903"


def test_suggere_evite_un_numero_SEULEMENT_MENTIONNE():
    """Le critere s'inverse : une MENTION suffit a reserver, alors qu'elle ne DEFINIT rien.

    C'est litteralement l'occurrence `#448-r1-r1-r2` -- le rapport employait le numero alors
    qu'aucun artefact ne le portait. Un `--suggere` qui ne regarderait que les DEFINITIONS
    (le critere des etapes 1 et 2) le rendrait comme libre."""
    lignes = BASE_SUGGERE + ["", "Un renvoi en PROSE vers #%s, qui ne definit rien." % PREMIER_AU_DESSUS]
    racine = _depot_git(lignes)
    try:
        rc, txt = _suggere(racine)
        assert rc == 0, txt
        assert _numero_propose(txt) != PREMIER_AU_DESSUS, \
            "un numero seulement MENTIONNE a ete propose :\n%s" % txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_suggere_evite_un_numero_qui_n_existe_QUE_dans_un_MESSAGE_DE_COMMIT():
    """MESURE (2026-08-04) : 13 racines pures < 500 -- #28, #269, #297, #300, #307 -- ne
    vivent QUE la. Le corpus documentaire les donne pour des trous LIBRES ; `git log --grep`
    prouve le contraire, et c'est une voie de tracabilite de plein droit."""
    racine = _depot_git(BASE_SUGGERE,
                        messages=("fix(#%s): un dossier dont il ne reste que ceci"
                                  % PREMIER_AU_DESSUS,))
    try:
        rc, txt = _suggere(racine)
        assert rc == 0, txt
        assert _numero_propose(txt) != PREMIER_AU_DESSUS, \
            "un numero vivant SEULEMENT dans l'historique a ete propose :\n%s" % txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_suggere_evite_un_numero_qui_n_existe_QUE_dans_un_SUJET_DE_MERGE():
    """#468-r13 -- `--no-merges` jetait la SEULE trace que le squash-merge laisse dans l'arbre.

    MESURE sur le depot reel (2026-08-15) : 698 commits de merge, **647 portent un `#`**
    (`merge(#1039) : ...`, `merge PR #1023 (#1027) -- ...`) ; ils apportent **96 identifiants
    inedits** et **1 numero rendu change** -- `--suggere 432` proposait `#432-r1`, LIVRE par la
    PR #479, et `git grep -E '#432-?r1' -- docs/rl scripts/python` rend **0**.

    DEUX BRAS, et c'est le premier qui rend le second probant : sans le merge, le numero DOIT
    etre propose. Un test a un seul bras ne distinguerait pas << la source marche >> de << ce
    numero etait de toute facon hors d'atteinte >>."""
    #: BRAS TEMOIN -- le meme depot, sans le merge : le numero est LIBRE et doit sortir.
    temoin = _depot_git(BASE_SUGGERE)
    try:
        rc, txt = _suggere(temoin)
        assert rc == 0, txt
        assert _numero_propose(txt) == PREMIER_AU_DESSUS, (
            "le bras TEMOIN ne propose pas %s : le bras suivant ne prouverait rien\n%s"
            % (PREMIER_AU_DESSUS, txt))
    finally:
        shutil.rmtree(temoin, ignore_errors=True)

    #: BRAS MESURE -- le numero n'existe QUE dans le sujet du commit de merge.
    racine = _depot_git(BASE_SUGGERE,
                        merge="merge(#%s) : une tranche livree, dont le sujet de merge est "
                              "l'unique trace" % PREMIER_AU_DESSUS)
    try:
        rc, txt = _suggere(racine)
        assert rc == 0, txt
        assert _numero_propose(txt) != PREMIER_AU_DESSUS, (
            "un numero vivant SEULEMENT dans un sujet de COMMIT DE MERGE a ete propose -- "
            "`--no-merges` est revenu quelque part dans le corpus :\n%s" % txt)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_le_mode_RESIDU_ecarte_lui_aussi_un_numero_venu_d_un_SUJET_DE_MERGE():
    """La generalisation de #468-r13 a l'autre mode -- c'est la ou la mesure a MORDU.

    Sur le depot reel, le seul numero rendu que la correction change est un RESIDU (`#432-r1`),
    pas une racine : depuis la bande (#468-r8) une racine neuve part de `PLANCHER_RACINE`, donc
    le corpus n'y commande plus. Garder la seule racine laisserait le mode RESIDU -- celui que la
    mesure accuse -- sans cliquet."""
    #: BRAS TEMOIN : `#10900-r1` est deja pris par `BASE_SUGGERE`, donc `r2` est le prochain.
    temoin = _depot_git(BASE_SUGGERE)
    try:
        rc, txt = _suggere(temoin, "10900")
        assert rc == 0, txt
        assert "LIBRE : #10900-r2" in txt, (
            "le bras TEMOIN ne propose pas r2 : le bras suivant ne prouverait rien\n%s" % txt)
    finally:
        shutil.rmtree(temoin, ignore_errors=True)

    racine = _depot_git(BASE_SUGGERE,
                        merge="merge PR #4242 (#10900-r2) -- residu livre, trace unique")
    try:
        rc, txt = _suggere(racine, "10900")
        assert rc == 0, txt
        assert "LIBRE : #10900-r2" not in txt, (
            "un RESIDU vivant seulement dans un sujet de merge a ete propose :\n%s" % txt)
        assert "LIBRE : #10900-r3" in txt, txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_suggere_ne_RECYCLE_pas_un_trou_sous_la_borne():
    """La suggestion est MONOTONE. Un trou peut etre reserve par une PR EN VOL, que l'arbre
    ne voit pas -- le recycler rouvrirait la collision par l'autre bout. Ils sont LISTES."""
    lignes = [_ligne("10900", "socle"), _ligne("10910", "sommet")]
    racine = _depot_git(lignes)
    try:
        rc, txt = _suggere(racine)
        assert rc == 0, txt
        propose = int(txt.split("LIBRE : #")[1].splitlines()[0].strip())
        assert propose > 10910, "un trou SOUS la borne a ete propose (%d) :\n%s" % (propose, txt)
        assert "trou(s) libre(s) DANS LES BANDES OUVERTES" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_la_borne_ECARTE_les_id_d_ability_portes_par_un_nom_de_case_doc(monkeypatch):
    """`case-1014-*`, `case-1203-*`, `case-1547-*` portent des id d'ability ou d'effet, pas des
    numeros de tache. Sans le filtre << connue du backlog >>, la borne saute a 1547.

    ⚠ CE TEST VISE DESORMAIS `borne_des_taches` DIRECTEMENT, ET C'EST UNE REPARATION, PAS UNE
    COMMODITE. Il passait par le NUMERO PROPOSE (`assert propose < 1000`), or depuis la bande
    (#468-r8) une racine neuve part de `PLANCHER_RACINE` : tant que la borne est sous le
    plancher, elle n'influence plus le numero du tout. L'assertion d'origine serait devenue
    VACANTE -- verte que le filtre marche ou non, puisque `max(1503, 10000)` et `max(911, 10000)`
    valent tous deux 10000. Un cliquet dont le sujet a disparu sous lui est exactement le << faux
    vert >> que ce fichier chasse ailleurs.

    En visant la fonction PURE, le test redevient discriminant : il rougit sur toute regression
    du filtre, aujourd'hui comme quand les racines auront depasse le plancher.
    """
    lignes = [_ligne("900", "socle"), _ligne("910", "sommet")]
    racine = _depot_git(lignes, case_docs=["case-1502-rites-of-morkai.md"])
    try:
        # Les memes globales que `viser()` pose, mais par `monkeypatch` : `viser` les ecrit
        # DEFINITIVEMENT pour le process, donc elle fuirait sur les tests suivants.
        monkeypatch.setattr(p468, "REPO", Path(racine).resolve())
        monkeypatch.setattr(p468, "DOCS_RL", Path(racine) / "docs" / "rl")
        monkeypatch.setattr(p468, "BACKLOG", Path(racine) / "docs" / "rl" / "backlog.md")
        assert p468.borne_des_taches() == 910, \
            "l'id d'ability 1502 a ete pris pour une racine de tache"
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_la_BANDE_met_les_racines_neuves_HORS_DE_PORTEE_des_numeros_de_PR():
    """#468-r8 -- le correctif de la collision `#1084`, et la raison pour laquelle il fallait
    une BANDE et pas seulement une source de plus.

    LE DEFAUT : `#<n>` designe a la fois une tache et une PR. Tant que les racines vivaient a
    ~500 et les PR a ~1500, une collision etait accidentelle. MESURE le 2026-08-14 : racine en
    usage max **1084**, PR max **1088** -- les deux compteurs se sont croises, donc TOUTE racine
    neuve heurtait une PR.

    POURQUOI AJOUTER LES NUMEROS DE PR AU CORPUS NE SUFFIT PAS -- c'est ce que le second volet
    mesure : marquer `#1088` pris fait allouer `#1089`, que GitHub donnera a la PR suivante.
    Le premier volet montre que la bande, elle, met le numero hors d'atteinte."""
    pris_pr = {str(i): {p468.SRC_PR_NUMERO} for i in range(1, 1089)}
    pris = dict(pris_pr)
    pris.update({str(i): {"backlog"} for i in range(1, 1085)})

    cle, n = p468.candidat_observe("", dict(pris), 1079)
    assert n >= p468.PLANCHER_RACINE, \
        "une racine neuve a ete allouee SOUS le plancher de bande (%s)" % cle
    assert n > max(int(k) for k in pris_pr), \
        "une racine neuve a ete allouee dans l'espace des numeros de PR (%s)" % cle

    #: Le CONTRE-FAIT : sans la bande, l'allocation retombe dans l'espace des PR -- donc le
    #: premier volet ne passe PAS << par accident >>, et retirer la bande le fait rougir.
    sans_bande = max(1079 + 1, 0)
    while str(sans_bande) in pris:
        sans_bande += 1
    assert sans_bande <= max(int(k) for k in pris_pr) + 1, \
        "le contre-fait ne reproduit plus le defaut : ce test ne prouve plus rien"


def test_l_INTERVALLE_ENTRE_LES_BANDES_n_est_PAS_compte_comme_des_trous():
    """Un TROU (numero saute, peut-etre pris par une PR en vol) et un INTERVALLE DE BANDE
    (jamais ouvert) ne sont pas la meme chose. Les confondre ferait annoncer ~8900 << trous
    libres >> a chaque allocation -- un compte faux qui noie les vrais trous, dont la liste est
    precisement ce qui permet a un humain de rattraper une reservation perdue."""
    pris = {str(i): {"backlog"} for i in range(1, 1085)}
    del pris["500"]                                  # un VRAI trou, dans la bande historique
    trous = p468.trous_des_bandes(1084, pris)
    assert trous == [500], "l'intervalle entre les bandes a ete compte : %d entrees" % len(trous)

    #: Apres la scission, la bande neuve est balayee elle aussi -- mais toujours pas l'entre-deux.
    pris.update({str(i): {"backlog"} for i in (10000, 10001, 10002)})
    del pris["10001"]
    trous = p468.trous_des_bandes(10003, pris)
    assert trous == [500, 10001], "les deux bandes ne sont pas balayees correctement : %s" % trous


def test_suggere_un_RESIDU_sous_un_parent_donne():
    """Le second mode : le plus petit `r<k>` libre sous un parent -- ce que reclamait #468-r5."""
    lignes = [_ligne("900", "socle"), _ligne("900-r1", "premier"), _ligne("900-r2", "second")]
    racine = _depot_git(lignes)
    try:
        rc, txt = _suggere(racine, "900")
        assert rc == 0, txt
        assert "LIBRE : #900-r3" in txt, txt
        assert "pris sous #900 : r1, r2" in txt, txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


# ==========================================================================================
#  #468-r10 -- L'ANGLE MORT DES AGENTS EN VOL
# ==========================================================================================
#
# Le defaut repare ici n'etait PAS une collision manquee : c'etait un `PASS` RASSURANT rendu
# dans le SEUL regime ou nos collisions se produisent. Le corpus de `--suggere` etait ce qui
# est ECRIT ET FUSIONNE, alors qu'une allocation se fait au DEBUT d'une tranche.
#
# Trois gardes, une par niveau d'aveuglement (cf. docstring du probe) :
#   N1 refs hors HEAD | N2 autres worktrees | N3 irreductible -> l'AVERTISSEMENT.

def _ajouter_worktree(racine, nom, branche):
    """Un VRAI second worktree du meme `.git` -- c'est le montage, pas une simulation.

    Place a COTE de `racine` : un worktree imbrique serait balaye par le `git grep` du
    premier, et le test passerait pour la mauvaise raison."""
    wt = racine.parent / (racine.name + "_" + nom)
    subprocess.run(["git", "-C", str(racine), "worktree", "add", "-q", "-b", branche, str(wt)],
                   check=True, capture_output=True)
    return wt


def test_deux_suggere_depuis_deux_worktrees_ne_rendent_PLUS_le_meme_numero():
    """CE TEST A CHANGE D'EXIGENCE, ET C'EST LA TRANCHE #468-r14 QUI L'A RETOURNE.

    Il exigeait l'inverse -- que les deux worktrees rendent le MEME numero (`n1 == n2 ==
    PREMIER_AU_DESSUS`), et qu'ils se contentent de DIRE qu'ils ne pouvaient pas se voir.
    C'etait la formulation honnete de #468-r10 : le corpus ne pouvait structurellement pas
    departager deux agents dont aucun n'a encore rien ecrit, donc on ne pouvait exiger que
    l'aveu. Ce qui a change n'est pas le corpus, c'est la NATURE de `--suggere` : elle ALLOUE
    (creation exclusive sous le `.git` commun) au lieu d'observer. Ce que ce test exigeait est
    devenu faux ; ce qu'il n'osait pas exiger est devenu vrai.

    Le montage est le meme -- deux worktrees du meme depot, aucune ecriture entre les deux
    appels -- pour que la comparaison avec l'ancienne exigence soit directe."""
    racine = _depot_git(BASE_SUGGERE)
    wt2 = None
    try:
        wt2 = _ajouter_worktree(racine, "b", "agent-b")
        rc1, txt1 = _suggere(racine)
        rc2, txt2 = _suggere(wt2)
        assert rc1 == 0 and rc2 == 0, "%s\n---\n%s" % (txt1, txt2)
        n1, n2 = _numero_propose(txt1), _numero_propose(txt2)
        assert n1 == PREMIER_AU_DESSUS, (
            "bras de reference : le premier appel doit rendre #%s, sinon la comparaison ne dit "
            "rien :\n%s" % (PREMIER_AU_DESSUS, txt1))
        assert n1 != n2, (
            "deux worktrees, aucune ecriture entre les deux appels, MEME numero (%s) : "
            "l'allocation n'est pas exclusive entre worktrees.\n%s\n---\n%s" % (n1, txt1, txt2))
        # La portee reste imprimee dans les deux : ce qui est desormais garanti, et ce qui ne
        # l'est pas (un numero pris hors outil, un autre clone du depot).
        manque = [nom for nom, t in (("worktree 1", txt1), ("worktree 2", txt2))
                  if p468.MARQUEUR_ANGLE_MORT not in t]
        assert not manque, ("%s n'imprime plus sa portee (%s absent) :\n%s"
                            % (" et ".join(manque), p468.MARQUEUR_ANGLE_MORT, txt1))
        assert "RESERVE :" in txt1 and "RESERVE :" in txt2, (
            "le numero est rendu sans dire qu'il a ete PRIS :\n%s" % txt1)
        # Et la concurrence est CHIFFREE, pas seulement evoquee.
        assert "concurrence : 1 autre(s) worktree(s)" in txt1, txt1
    finally:
        if wt2:
            shutil.rmtree(wt2, ignore_errors=True)
        shutil.rmtree(racine, ignore_errors=True)


def test_N2_un_numero_ecrit_dans_un_AUTRE_worktree_n_est_plus_propose():
    """`git grep --untracked` ne lit que SON checkout : un `case-<n>-*.md` ecrit chez le
    voisin lui est invisible. MESURE sur le depot reel (2026-08-05) : `--suggere 425` rendait
    `#425-r3`, qu'un `probe_425r3_*.py` d'un worktree en vol portait deja."""
    racine = _depot_git(BASE_SUGGERE)
    wt2 = None
    try:
        wt2 = _ajouter_worktree(racine, "b", "agent-b")
        rc, txt = _suggere(racine)
        assert rc == 0 and _numero_propose(txt) == PREMIER_AU_DESSUS, (
            "bras NON MUTE : le numero de reference doit etre %s :\n%s"
            % (PREMIER_AU_DESSUS, txt))
        # L'agent d'a cote ouvre son dossier -- sans commiter, comme au premier geste.
        (wt2 / "docs" / "rl" / ("case-%s-pris-par-le-voisin.md" % PREMIER_AU_DESSUS)).write_text(
            "# pris\n", encoding="utf-8")
        _vider_reservations(racine)      # ISOLE l'axe mesure ici : la source WORKTREE VOISIN
        rc, txt2 = _suggere(racine)
        assert rc == 0, txt2
        assert _numero_propose(txt2) != PREMIER_AU_DESSUS, (
            "un numero DEJA OUVERT dans un worktree voisin a ete propose :\n%s" % txt2)
    finally:
        if wt2:
            shutil.rmtree(wt2, ignore_errors=True)
        shutil.rmtree(racine, ignore_errors=True)


def test_N2_generalisation_un_PROBE_du_voisin_bloque_le_mode_RESIDU():
    """L'AUTRE combinaison, et c'est celle du cas REEL : le porteur mesure de `#425-r3` etait un
    `probe_425r3_removed_writers.py` -- pas une case-doc -- et la demande etait `--suggere 425`,
    pas une racine. Un patch qui ne fermerait que le couple (case-doc, racine) laisserait
    passer exactement la collision qui a ouvert ce dossier."""
    lignes = [_ligne("900", "socle"), _ligne("900-r1", "premier residu")]
    racine = _depot_git(lignes)
    wt2 = None
    try:
        wt2 = _ajouter_worktree(racine, "b", "agent-b")
        rc, txt = _suggere(racine, "900")
        assert rc == 0 and "LIBRE : #900-r2" in txt, (
            "bras NON MUTE : le residu de reference doit etre #900-r2 :\n%s" % txt)
        # Le voisin ouvre `#900-r2` par un PROBE, la graphie COLLEE que le depot emploie aussi.
        (wt2 / "scripts" / "python").mkdir(parents=True, exist_ok=True)
        (wt2 / "scripts" / "python" / "probe_900r2_pris_par_le_voisin.py").write_text(
            "# pris\n", encoding="utf-8")
        _vider_reservations(racine)      # ISOLE l'axe mesure ici : la source WORKTREE VOISIN
        rc, txt2 = _suggere(racine, "900")
        assert rc == 0, txt2
        assert "LIBRE : #900-r2" not in txt2, (
            "un residu deja ouvert chez le voisin (par un PROBE, graphie collee) a ete "
            "propose :\n%s" % txt2)
        assert "LIBRE : #900-r3" in txt2, txt2
        # ... et la portee est imprimee AUSSI dans le mode residu.
        assert p468.MARQUEUR_ANGLE_MORT in txt2, txt2
    finally:
        if wt2:
            shutil.rmtree(wt2, ignore_errors=True)
        shutil.rmtree(racine, ignore_errors=True)


def test_N1_un_numero_commite_sur_une_ref_HORS_HEAD_n_est_plus_propose():
    """Un worktree d'agent est FIGE a son commit de lancement : `git log` sans `--all` est
    aveugle a `master` qui avance et aux branches des voisins. MESURE : `--suggere 448`
    rendait `#448-r3`, dont le dossier etait commite ailleurs."""
    racine = _depot_git(BASE_SUGGERE)
    try:
        rc, txt = _suggere(racine)
        assert rc == 0 and _numero_propose(txt) == PREMIER_AU_DESSUS, txt
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ.get("PATH", "")}

        def git(*a):
            subprocess.run(["git", "-C", str(racine)] + list(a), check=True,
                           capture_output=True, env=env)
        depart = subprocess.run(["git", "-C", str(racine), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        git("checkout", "-q", "-b", "agent-voisin")
        (racine / "docs" / "rl" / "note.md").write_text("x\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "feat(#%s): le voisin a deja ouvert ce dossier"
            % PREMIER_AU_DESSUS)
        git("checkout", "-q", depart)
        _vider_reservations(racine)      # ISOLE l'axe mesure ici : la source REF HORS HEAD
        rc, txt2 = _suggere(racine)
        assert rc == 0, txt2
        assert _numero_propose(txt2) != PREMIER_AU_DESSUS, (
            "un numero commite sur une ref HORS de la lignee de HEAD a ete propose :\n%s" % txt2)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_un_capteur_de_concurrence_MUET_ne_se_rabat_JAMAIS_sur_zero(capsys):
    """Meme regle que `loop_status` : `null` n'est pas `0` (#467).

    Un << 0 autre worktree >> fabrique se lirait << personne d'autre ne travaille >> -- soit
    exactement le PASS rassurant que cette tranche existe pour supprimer."""
    p468._imprimer_portee({}, None, [])
    muet = capsys.readouterr().out
    assert "NON MESUREE" in muet, muet
    assert "0 autre worktree" not in muet, "un capteur muet a ete rendu comme un ZERO :\n%s" % muet

    p468._imprimer_portee({}, [], [])
    vide = capsys.readouterr().out
    assert "0 autre worktree MESURE" in vide, vide
    # ... et meme a zero concurrent, l'angle mort N3 subsiste : PR en vol, worktree supprime.
    assert p468.MARQUEUR_ANGLE_MORT in vide, vide


def test_un_worktree_list_MUET_n_est_pas_lu_comme_ZERO_WORKTREE(monkeypatch):
    """Le piege est dans le contrat de `_git`, pas dans le capteur : il TOLERE `rc=1`, parce
    que `git grep` rend 1 quand il ne trouve rien -- reponse valide. Pour `worktree list`,
    `rc=1` est une PANNE (sous-commande absente d'un git ancien) et sort en stdout VIDE.

    Sans discriminant, cette panne se lirait << 0 autre worktree MESURE >>, c'est-a-dire
    exactement le zero fabrique que #468-r10 existe pour supprimer. Le discriminant est
    DERIVE : un `worktree list` qui reussit liste TOUJOURS au moins l'arbre courant."""
    monkeypatch.setattr(p468, "_git", lambda args, quoi: "")
    assert p468._autres_worktrees() is None, (
        "une sortie VIDE de `git worktree list` a ete lue comme << aucun autre worktree >>")


def test_un_worktree_ILLISIBLE_est_NOMME_et_non_compte_pour_vide(capsys):
    """Tri-etat PAR worktree : un repertoire disparu en cours de balayage (worktree jetable de
    pytest, agent nettoye) ne doit pas passer pour << rien a signaler >>."""
    absent = Path(tempfile.gettempdir()) / "p468_worktree_qui_n_existe_pas"
    ids, illisibles = p468._identifiants_des_worktrees([(absent, None)])
    assert ids == {} and len(illisibles) == 1 and illisibles[0][0] == absent
    p468._imprimer_portee({}, [(absent, None)], illisibles)
    txt = capsys.readouterr().out
    assert "ILLISIBLE (non mesure, pas vide)" in txt and absent.name in txt, txt


# ==========================================================================================
#  #468-r11 -- LA MONOTONIE VAUT DANS LES DEUX MODES
# ==========================================================================================
#
# Le mode RACINE refusait de recycler un trou ; le mode RESIDU s'arretait au PREMIER trou et le
# PROPOSAIT, en n'imprimant comme << pris >> que le prefixe contigu. MESURE sur le depot reel :
# `--suggere 477` rendait `#477-r14` alors que `r15`, `r16` et `r17` existent -- et le corpus
# les VOYAIT (verifie dans `employes()`, pas deduit de la sortie). 11 parents sur 218 etaient
# dans ce cas.

def test_le_mode_RESIDU_ne_RECYCLE_pas_un_trou_lui_non_plus():
    """Le motif ecrit pour les racines s'applique MOT POUR MOT a un residu : `#900-r2` peut
    avoir ete alloue par un agent qui n'a encore rien ecrit, ou porte par une PR ouverte dont
    le worktree est deja supprime. Le bras NON MUTE (`r1`+`r2` -> `r3`) est garde par
    `test_suggere_un_RESIDU_sous_un_parent_donne`."""
    lignes = [_ligne("900", "socle"), _ligne("900-r1", "premier"),
              _ligne("900-r3", "TROISIEME -- le r2 est un trou")]
    racine = _depot_git(lignes)
    try:
        rc, txt = _suggere(racine, "900")
        assert rc == 0, txt
        assert "LIBRE : #900-r2" not in txt, (
            "un TROU a ete propose en mode residu, alors que le mode racine le refuse :\n%s" % txt)
        assert "LIBRE : #900-r4" in txt, txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_le_mode_RESIDU_LISTE_ce_qui_est_pris_AU_DELA_du_trou():
    """Un compte FILTRE doit dire ce qu'il filtre (#468-r10). L'ancienne sortie annoncait
    << pris sous #900 : r1 >> et s'arretait la : un lecteur ne pouvait pas juger, alors que
    `r3` etait dans le corpus. Ici les DEUX faces sont exigees -- ce qui est pris au-dela, et
    le trou lui-meme, nomme comme NON propose."""
    lignes = [_ligne("900", "socle"), _ligne("900-r1", "premier"), _ligne("900-r3", "troisieme")]
    racine = _depot_git(lignes)
    try:
        rc, txt = _suggere(racine, "900")
        assert rc == 0, txt
        ligne_pris = [l for l in txt.splitlines() if "pris sous #900" in l]
        assert ligne_pris, txt
        assert "r3" in ligne_pris[0], (
            "`r3` est PRIS et n'est pas dit : la restitution filtre sans le dire :\n%s"
            % ligne_pris[0])
        trous = [l for l in txt.splitlines() if "trou(s) libre(s) SOUS" in l]
        assert trous and "r2" in trous[0], (
            "le trou r2 n'est pas LISTE comme non propose :\n%s" % txt)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_la_liste_des_trous_ne_MENT_pas_sur_ce_qu_elle_tronque():
    """Meme regle que `en_vol` : ne pas annoncer N et n'en montrer que 12 sans le dire."""
    assert p468._lister_trous([], str) == "(aucun)"
    assert p468._lister_trous(list(range(1, 8)), str) == "1, 2, 3, 4, 5, 6, 7"
    long = p468._lister_trous(list(range(1, 31)), lambda i: "r%d" % i)
    assert long.endswith("... (18 de plus)"), long


# ==========================================================================================
#  #468-r11 -- LA QUATRIEME SOURCE HORS-ARBRE : LE CORPS DES PULL REQUESTS
# ==========================================================================================
#
# Le corps d'une PR n'est PAS dans l'arbre : le squash-merge ne l'y recopie pas. MESURE sur le
# depot reel -- `git grep "479-?r2"` = 0, `git log --all --grep 479-r2` = 0, et pourtant la PR
# #663 ouvre `#479-r2` dans son corps. `--suggere 479` le rendait comme libre.

class _GhFactice:
    """Substitut de `subprocess.run` pour `gh` -- rend ce qu'on lui dit, sans reseau."""

    def __init__(self, rc=0, stdout="[]", stderr="", boum=None):
        self.rc, self.stdout, self.stderr, self.boum = rc, stdout, stderr, boum
        self.argv = None

    def __call__(self, argv, **kw):
        self.argv = argv
        if self.boum is not None:
            raise self.boum
        return subprocess.CompletedProcess(argv, self.rc, self.stdout, self.stderr)


def test_un_numero_ouvert_SEULEMENT_dans_le_CORPS_d_une_PR_n_est_pas_propose(monkeypatch,
                                                                            capsys):
    """LA condition de retournement de #468-r11 (parade (c) de #468-r10).

    Le bras NON MUTE (aucune PR) doit proposer le numero de reference -- sinon le bras rouge ne
    prouverait rien."""
    racine = _depot_git(BASE_SUGGERE)
    try:
        p468.viser(racine)
        # Bras NON MUTE : `gh` rend une liste vide -- une mesure, pas une panne.
        monkeypatch.setattr(p468, "_pull_requests", lambda: ([], None))
        p468.suggerer("")
        assert _numero_propose(capsys.readouterr().out) == PREMIER_AU_DESSUS

        # Bras MUTE : une PR OUVRE ce numero dans son corps, et nulle part ailleurs.
        _vider_reservations(racine)      # ISOLE l'axe mesure ici : la source CORPS DE PR
        monkeypatch.setattr(p468, "_pull_requests", lambda: (
            [{"number": 999, "title": "un titre sans numero",
              "body": "son verdict ne pese pas `manquants` => #%s." % PREMIER_AU_DESSUS}], None))
        p468.suggerer("")
        txt = capsys.readouterr().out
        assert _numero_propose(txt) != PREMIER_AU_DESSUS, (
            "un numero ouvert dans le CORPS d'une PR a ete propose :\n%s" % txt)
    finally:
        p468.viser(REPO)
        shutil.rmtree(racine, ignore_errors=True)


def test_le_mode_RESIDU_ecarte_lui_aussi_un_numero_venu_d_une_PR(monkeypatch, capsys):
    """Generalisation, et elle n'est pas decorative : le cas REEL mesure etait `--suggere 479`,
    un RESIDU -- un correctif qui ne cablerait la source que dans le mode racine laisserait
    passer exactement la collision qui a ouvert ce dossier."""
    racine = _depot_git([_ligne("900", "socle"), _ligne("900-r1", "premier")])
    try:
        p468.viser(racine)
        monkeypatch.setattr(p468, "_pull_requests", lambda: ([], None))
        p468.suggerer("900")
        assert "LIBRE : #900-r2" in capsys.readouterr().out

        _vider_reservations(racine)      # ISOLE l'axe mesure ici : la source CORPS DE PR
        monkeypatch.setattr(p468, "_pull_requests", lambda: (
            [{"number": 999, "title": "#900-r2 : deja ouvert par cette PR", "body": ""}], None))
        p468.suggerer("900")
        txt = capsys.readouterr().out
        assert "LIBRE : #900-r2" not in txt, (
            "un residu ouvert par une PR a ete propose :\n%s" % txt)
        assert "LIBRE : #900-r3" in txt, txt
    finally:
        p468.viser(REPO)
        shutil.rmtree(racine, ignore_errors=True)


def test_gh_ne_lit_PAS_le_nom_de_branche_et_c_est_une_MESURE():
    """Sur 40 PR, le nom de branche lu par `couper_nom` -- la voie que le probe emploie deja
    pour les NOMS de fichiers -- rend `worktree` et `agent` : **0** signal, du bruit pur. Meme
    famille que le `--name-only` refuse en #468-r10 section 3.

    ⚠ L'ASSERTION EST UNE EGALITE, et c'est ce qui a manque au premier jet : un `not [k for k
    in ids if 'worktree' in k]` restait VERT sur la mutation, parce que `RE_TOKEN_LARGE` exige
    un `#` et ne tire donc RIEN d'un nom de branche. Le mutant ne mordait pas -- il accusait
    l'assertion, et la mesure qui la justifiait (elle prefixait un `#` que le code n'ecrit
    jamais). L'egalite, elle, rougit sur TOUTE forme de lecture du nom de branche."""
    prs = [{"number": 1, "title": "#900-r7 un vrai residu", "body": "et #901 en prose",
            "headRefName": "worktree-agent-a5af8da60c785fce4"},
           {"number": 2, "title": "un titre sans numero", "body": "",
            "headRefName": "agent-477r16r1"}]
    ids = p468._identifiants_des_pr(prs)
    #: `1` et `2` sont les NUMEROS PROPRES des deux PR (#468-r8) : dans un espace de noms
    #: partage, une PR rend son numero pris sans rien citer. L'egalite reste l'assertion --
    #: c'est elle qui rougit sur TOUTE forme de lecture du nom de branche, y compris celles
    #: qu'un `not in` laisserait passer.
    assert set(ids) == {"900r7", "901", "1", "2"}, (
        "le nom de branche a ete lu (ou un identifiant a ete perdu) : %s" % sorted(ids))
    #: Les deux provenances sont DISTINCTES, et c'est ce qui permet a un lecteur de savoir si
    #: `#1084` est pris parce qu'une PR le CITE ou parce qu'une PR l'EST.
    assert ids["900r7"] == {p468.SRC_PR} and ids["901"] == {p468.SRC_PR}
    assert ids["1"] == {p468.SRC_PR_NUMERO} and ids["2"] == {p468.SRC_PR_NUMERO}


@pytest.mark.parametrize("nom,factice,attendu", [
    ("binaire absent", _GhFactice(boum=FileNotFoundError()), "introuvable"),
    ("delai depasse", _GhFactice(boum=subprocess.TimeoutExpired("gh", 30)), "n'a pas repondu"),
    ("erreur systeme", _GhFactice(boum=OSError("acces refuse")), "injouable"),
    ("token invalide (rc=1)", _GhFactice(rc=1, stdout="", stderr="HTTP 401: Bad credentials"),
     "Bad credentials"),
    ("non authentifie (rc=4)", _GhFactice(rc=4, stdout="", stderr="gh auth login required"),
     "auth login"),
    ("rc=0 mais sortie illisible", _GhFactice(rc=0, stdout="{ pas du json"), "illisible"),
    ("rc=0 mais sortie inattendue", _GhFactice(rc=0, stdout='{"a": 1}'), "inattendue"),
])
def test_une_panne_de_gh_est_NOMMEE_et_ne_fabrique_JAMAIS_un_zero(monkeypatch, nom, factice,
                                                                 attendu):
    """Deux exigences, et la seconde est celle qui compte.

    (1) La panne porte son NOM -- un `rc` ne nomme rien : sur `gh 2.88.1`, `rc=1` couvre a lui
        seul le token invalide, le depot inconnu et l'erreur d'usage (#467-r6). C'est le STDERR
        qui separe, donc c'est lui qu'on remonte.
    (2) AUCUNE de ces pannes ne rend une liste VIDE. Un `[]` se lirait << aucune PR ne porte ce
        numero >>, c'est-a-dire le zero fabrique que tout ce dossier existe pour supprimer."""
    monkeypatch.setattr(subprocess, "run", factice)
    prs, raison = p468._pull_requests()
    assert prs is None, "%s : une panne a rendu une LISTE (%r), donc un zero fabrique" % (nom, prs)
    assert raison and attendu in raison, "%s : la panne n'est pas NOMMEE -> %r" % (nom, raison)


def test_gh_qui_REUSSIT_a_vide_est_une_MESURE_et_non_une_panne(monkeypatch):
    """La frontiere symetrique : un depot sans aucune PR rend legitimement `[]`.

    Contrairement a `git worktree list` (ou une sortie vide NE PEUT PAS etre vraie), il n'existe
    ici aucun discriminant derive : `rc == 0` + JSON valide est le seul disponible, et on le dit
    plutot que d'inventer une regle."""
    monkeypatch.setattr(subprocess, "run", _GhFactice(rc=0, stdout="[]"))
    prs, raison = p468._pull_requests()
    assert prs == [] and raison is None


def test_la_PORTEE_distingue_PR_NON_MESUREES_de_PR_LUES(capsys):
    """Tri-etat imprime : `null` n'est pas `0`, et la panne est en clair dans la sortie."""
    p468._imprimer_portee({}, [], [], None, "`gh` rc=1 -- HTTP 401: Bad credentials")
    muet = capsys.readouterr().out
    assert "PR GitHub : NON MESUREES" in muet, muet
    assert "Bad credentials" in muet, "la panne n'est pas NOMMEE au lecteur :\n%s" % muet
    assert "0 PR" not in muet and "0 pull" not in muet.lower(), (
        "un capteur muet a ete rendu comme un ZERO :\n%s" % muet)

    p468._imprimer_portee({}, [], [], [{"number": 1}], None)
    lu = capsys.readouterr().out
    assert "PR GitHub : 1 lue(s)" in lu and "plus ANCIENNES ne sont PAS lues" in lu, lu


def test_gh_MUET_ne_fait_PAS_echouer_suggere(monkeypatch, capsys):
    """Capteur d'APPOINT, meme arbitrage que `git worktree list` : sans lui `--suggere` retombe
    sur les quatre autres sources -- degrade, pas faux. Le faire lever rendrait l'outil
    inutilisable hors ligne, donc ferait revenir au geste qu'il supprime (choisir au vol)."""
    racine = _depot_git(BASE_SUGGERE)
    try:
        p468.viser(racine)
        monkeypatch.setattr(p468, "_pull_requests",
                            lambda: (None, "`gh` introuvable sur le PATH"))
        rc = p468.suggerer("")
        txt = capsys.readouterr().out
        assert rc == 0, txt
        assert _numero_propose(txt) == PREMIER_AU_DESSUS, txt
        assert "PR GitHub : NON MESUREES -- `gh` introuvable sur le PATH" in txt, txt
    finally:
        p468.viser(REPO)
        shutil.rmtree(racine, ignore_errors=True)


def test_sur_le_depot_REEL_le_numero_suggere_n_apparait_NULLE_PART():
    """Garde sur l'arbre vivant : le numero rendu doit etre absent de l'UNION -- docs/rl,
    scripts/python, noms de fichiers ET messages de commit."""
    pris = p468.employes()
    borne = p468.borne_des_taches()
    assert borne > 0, "la borne des taches est nulle : le backlog reel ne definit plus rien"
    n = borne + 1
    while str(n) in pris:
        n += 1
    assert str(n) not in pris
    assert n > borne, "la suggestion doit rester au-dessus de la borne (monotonie)"
    # Et la borne ne doit pas avoir ete contaminee par un id d'ability.
    #
    # ⚠ LE SEUIL QUI TENAIT CE ROLE (`borne < 1000`) A EXPIRE, et il a rougi `master` (#1001,
    # 2026-08-13) : l'espace des TACHES a franchi 1000 -- `--suggere` a rendu `#1001` alors que la
    # borne valait 996 et que 997..1000 etaient deja pris. Un seuil plus haut ne ferait que
    # reporter la meme peremption ; c'est le mode de panne que la doctrine appelle << une garde en
    # SEUIL se degrade en silence >>.
    #
    # L'INVARIANT qu'il approximait : la borne doit etre ADOSSEE AU BACKLOG -- le numero doit y
    # etre DEFINI (1re cellule d'une ligne, racine ou residu), pas seulement porte par une
    # case-doc NOMMEE d'apres un id d'ability. C'est exactement ce qui separe `#1001` (defini par
    # la ligne `#1001-r1`) des trois contaminants que `borne_des_taches` documente :
    # `case-1014-*`, `case-1203-*`, `case-1547-*`, dont AUCUNE racine n'est definie au backlog
    # (verifie par le second bras ci-dessous, qui rendrait ce test vide s'il n'y en avait plus).
    racines_backlog = {m.group(1)
                       for d in p468.definitions_du_backlog(p468._lignes_backlog())
                       for m in [re.match(r"^(\d+)", d.cle)] if m}
    assert str(borne) in racines_backlog, (
        "la borne (%d) n'est DEFINIE nulle part dans backlog.md : elle a absorbe un identifiant "
        "qui n'est pas une tache (typiquement une case-doc nommee d'apres un id d'ability)" % borne)
    contaminants = {m.group(1)
                    for d in p468.definitions_des_case_docs(p468._fichiers_case_docs())
                    for m in [re.match(r"^(\d+)", d.cle)] if m} - racines_backlog
    assert contaminants, (
        "aucune case-doc n'est nommee d'apres un id hors backlog : le bras ci-dessus ne separe "
        "plus rien -- verifier que `borne_des_taches` filtre encore ces identifiants")

