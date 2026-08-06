"""#486-r1 -- garde du CACHE DE VERDICT PAR FICHIER (`verdict_cache`).

Un cache est le second endroit de ce depot ou l'on peut fabriquer un FAUX VERT (le premier est la
selection par diff de `probe_457`) : il REMPLACE une mesure par une attestation. Ce fichier garde
les proprietes qui le rendent acceptable.

    PEREMPTION   la cle est le sha du CONTENU : une entree qui ne correspond plus MANQUE, donc
                 fait recalculer. Elle ne peut pas mentir par vieillissement.
    FIDELITE     a contenu egal, la valeur servie est EXACTEMENT celle qui avait ete calculee --
                 c'est ce qui autorise a comparer une sortie chaude a une sortie froide.
    CONTEXTE     source du cliquet ou table de symboles differente => cache VIDE, cout plein.
    MENAGE       une entree que le run ne visite plus DISPARAIT : le fichier versionne ne derive
                 pas, et une entree d'un ancien perimetre ne peut pas ressurgir.
    PANNE        un cache absent, tronque ou corrompu se degrade en RECALCUL, jamais en verdict.
    LOCALITE     et surtout : AUCUN cliquet a verdict GLOBAL ne doit etre cache. Un cache par
                 fichier ne verrait jamais une collision entre un fichier TOUCHE et un fichier NON
                 TOUCHE -- c'est litteralement la collision `#477-r43` du 2026-08-05, verte sur
                 chacune des deux PR prise seule.

⚠ CE QUE CE FICHIER FIGE AUSSI, PARCE QUE C'EST UNE LIMITE ET PAS UN DEFAUT : une entree
FALSIFIEE DE FACON COHERENTE -- verdict faux ecrit en face du hash JUSTE -- fait MENTIR le cache,
et aucune cle ne peut l'en empecher. Le seul controle qui la voit est la RE-VERIFICATION
(`verdict_cache.verifier`, expose par `--verifier-cache` sur les trois cliquets caches). Les deux
faits sont testes ensemble : si un jour la falsification cessait d'etre servie, le test le dirait.

Montage 100 % offline et JETABLE (`tmp_path`) : aucun cliquet n'est joue, aucun fichier du depot
n'est ecrit. Les etages de CABLAGE lisent le source des cliquets, ils ne les executent pas.

ASCII only (console cp1252).
"""
import ast
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import verdict_cache as VC  # noqa: E402

REPO = _PYDIR.parents[1]

#: Les cliquets CACHES, avec le nom de leur fichier de cache versionne.
CACHES = {
    "probe_477r24r1_slots_interface": "probe_477r24r1_slots_interface",
    "probe_477r25_slots_autres_interfaces": "probe_477r25_slots_autres_interfaces",
    "probe_313_enum_mirror_bijection": "probe_313_enum_mirror_bijection",
    #: #486-r11 -- le SEUL dont la cle de ligne n'est PAS le sha d'un fichier : c'est celui de la
    #: FERMETURE transitive des imports du module. La localite est la meme, elle porte juste sur
    #: un SOUS-GRAPHE au lieu d'un fichier ; tout le reste du contrat (peremption, contexte,
    #: menage, panne, re-verification) est identique, et c'est pourquoi il entre ICI.
    "probe_270r4r2_import_en_premier": "probe_270r4r2_import_en_premier",
}

#: Les cliquets dont le verdict est GLOBAL ou dont la localite N'EST PAS ETABLIE. Ils ne doivent
#: PAS toucher a `verdict_cache`. La raison est ecrite ici, pas ailleurs : c'est elle qui fait la
#: difference entre un choix et un oubli.
NON_CACHABLES = {
    "probe_468_collision_numeros":
        "GLOBAL par construction -- une collision est une RELATION entre deux definitions, dont "
        "l'une peut vivre dans un fichier NON touche",
    "probe_485_imports_differes":
        "le critere CYCLE charge la cible dans un process FRAIS : le verdict depend du "
        "SOUS-GRAPHE d'imports atteignable, pas d'un fichier. ATTENTION : #486-r11 a RENDU ce "
        "critere cachable en prenant pour cle la FERMETURE (`import_closure`) -- ce probe-ci "
        "n'y est pas cable et reste NON cache, ce qui est un RESIDU, pas une impossibilite",
    "probe_273_gitignored_inputs":
        "les etapes 0 et 0c resolvent leurs chemins par un POINT FIXE sur un `modenv` PARTAGE -- "
        "mesure #486-r1 : 58 fichiers sur 2090 empruntent une racine a un AUTRE module",
    "probe_181_targeting_gaps":
        "aucun perimetre de fichiers : il croise un REGISTRE importe, et son verdict porte sur le "
        "compte GLOBAL",
}


# ----------------------------------------------------------------- le MECANISME (jetable)

def _cache(tmp_path, contexte="ctx-1", relire=True):
    return VC.CacheCliquet("essai_486", contexte, dossier=tmp_path, relire=relire)


def test_une_entree_dont_le_contenu_a_change_MANQUE(tmp_path):
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["verdict-v1"])
    assert c.enregistrer(), "l'enregistrement doit aboutir"
    d = _cache(tmp_path)
    assert d.obtenir("a.py", "ap", VC.sha_texte("v1")) == ["verdict-v1"], (
        "a contenu EGAL, la valeur servie doit etre celle qui avait ete calculee")
    assert d.obtenir("a.py", "ap", VC.sha_texte("v2")) is VC.MANQUE, (
        "un contenu DIFFERENT doit MANQUER -- sinon le cache atteste pour un autre fichier")


def test_le_sha_porte_sur_le_TEXTE_pas_sur_les_octets(tmp_path):
    #: `core.autocrlf` vaut `true` : le meme fichier versionne est CRLF sous Windows et LF
    #: ailleurs. Un sha sur les octets rendrait le cache versionne toujours froid.
    assert VC.sha_texte("a\nb\n") == VC.sha_texte("a\nb\n")
    assert VC.sha_texte("a\nb") != VC.sha_texte("a\nc")


def test_le_CONTEXTE_portable_ignore_les_fins_de_ligne_la_ou_sha_fichiers_ne_le_fait_PAS(tmp_path):
    """#486-r11 -- `sha_fichiers` hache les OCTETS : un `git rebase` sous `core.autocrlf=true`
    suffit a changer le contexte d'un cliquet dont AUCUNE source n'a bouge.

    Vice VECU le 2026-08-07 : le cache de `probe_270r4r2_import_en_premier` est reparti a zero
    apres un rebase qui n'avait touche aucune de ses trois sources -- 119 s au lieu de 20 s. Et
    sur une plateforme a LF, un cache VERSIONNE serait froid en PERMANENCE, c'est-a-dire inutile
    la ou il existe. `sha_texte` documentait deja ce piege pour la cle de LIGNE ; le contexte y
    echappait.

    Les deux moities comptent : la variante portable doit IGNORER la fin de ligne, et l'ancienne
    doit encore la voir -- sans quoi ce test serait vert sur deux fonctions identiques.
    """
    f = tmp_path / "src.py"
    f.write_bytes(b"X = 1\r\nY = 2\r\n")
    crlf_texte, crlf_octets = VC.sha_fichiers_texte(f), VC.sha_fichiers(f)
    f.write_bytes(b"X = 1\nY = 2\n")
    assert VC.sha_fichiers_texte(f) == crlf_texte, (
        "le contexte PORTABLE bouge sur une simple conversion de fins de ligne")
    assert VC.sha_fichiers(f) != crlf_octets, (
        "`sha_fichiers` ne voit plus les octets : ce test compare deux fonctions identiques")


def test_le_CONTEXTE_portable_voit_un_VRAI_changement_et_une_ABSENCE(tmp_path):
    """Le pendant du precedent : normaliser ne doit pas rendre l'empreinte aveugle."""
    f = tmp_path / "src.py"
    f.write_bytes(b"X = 1\n")
    avant = VC.sha_fichiers_texte(f)
    f.write_bytes(b"X = 2\n")
    assert VC.sha_fichiers_texte(f) != avant, "un changement de CONTENU ne bouge pas l'empreinte"
    apres = VC.sha_fichiers_texte(f)
    f.unlink()
    assert VC.sha_fichiers_texte(f) != apres, (
        "un fichier ABSENT rend la meme empreinte qu'un fichier present : son absence doit etre "
        "une donnee du contexte, pas un silence")


def test_un_contexte_different_VIDE_le_cache(tmp_path):
    c = _cache(tmp_path, contexte="build-A")
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    c.enregistrer()
    autre = _cache(tmp_path, contexte="build-B")
    assert autre.obtenir("a.py", "ap", VC.sha_texte("v1")) is VC.MANQUE, (
        "au changement de contexte (source du cliquet, table de symboles), TOUT doit manquer")


def test_une_entree_non_visitee_DISPARAIT(tmp_path):
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    c.poser("b.py", "ap", VC.sha_texte("v1"), ["y"])
    c.enregistrer()
    d = _cache(tmp_path)
    d.obtenir("a.py", "ap", VC.sha_texte("v1"))          # seul `a.py` est visite
    d.enregistrer()
    e = _cache(tmp_path)
    assert e.obtenir("a.py", "ap", VC.sha_texte("v1")) == ["x"]
    assert e.obtenir("b.py", "ap", VC.sha_texte("v1")) is VC.MANQUE, (
        "une entree que le run ne visite plus doit sortir du fichier versionne")


def test_contribution_calcule_UNE_fois_puis_ressert(tmp_path):
    appels = []
    c = _cache(tmp_path)
    for _ in range(3):
        v = c.contribution("a.py", "ap", VC.sha_texte("v1"),
                           lambda: appels.append(1) or ["calcule"])
        assert v == ["calcule"]
    assert len(appels) == 3, "sans enregistrement intermediaire, chaque process recalcule"
    c.enregistrer()
    d = _cache(tmp_path)
    appels2 = []
    assert d.contribution("a.py", "ap", VC.sha_texte("v1"),
                          lambda: appels2.append(1) or ["autre"]) == ["calcule"]
    assert appels2 == [], "l'entree valide doit EVITER le calcul"


@pytest.mark.parametrize("contenu", [
    "",                                              # fichier vide
    "pas d'en-tete\ta\tb\tc",                        # en-tete absente
    "# format=99\tcontexte=ctx-1\ta.py\tap\tsha\t[]",  # autre FORMAT
    "# format=1\tcontexte=ctx-1\n# x\na.py\tap",     # colonnes manquantes
    "# format=1\tcontexte=ctx-1\n# x\na.py\tap\tsha\t{pas du json",
])
def test_un_cache_corrompu_se_degrade_en_RECALCUL(tmp_path, contenu):
    (tmp_path / "essai_486.tsv").write_text(contenu, encoding="utf-8")
    c = _cache(tmp_path)
    assert c.obtenir("a.py", "ap", "sha") is VC.MANQUE, (
        "une panne du CACHE ne rend jamais un verdict : elle fait recalculer")


def test_l_encodeur_recoit_l_APPEL_et_pas_seulement_la_valeur(tmp_path):
    """Un meme cliquet cache des valeurs de FORMES DIFFERENTES selon l'appel.

    Faute REELLE de #486-r1 : `probe_477r25` cache des citations (nonuplet) ET un simple entier
    (`autre_casse`). Un encodeur qui ne regardait que la valeur levait `TypeError` sur la seconde
    forme -- et ce n'est pas un test qui l'a vu, c'est le controle de FIDELITE : le run SANS cache
    passait, celui AVEC cache plantait. Le contrat est donc FIGE ici."""
    vus = []

    def enc(v, appel):
        vus.append(appel)
        return {"n": v} if appel == "entier" else list(v)

    def dec(b, appel):
        return b["n"] if appel == "entier" else tuple(b)

    c = VC.CacheCliquet("essai_486", "ctx-1", encoder=enc, decoder=dec, dossier=tmp_path)
    c.poser("a.py", "entier", VC.sha_texte("v1"), 7)
    c.poser("a.py", "tuple", VC.sha_texte("v1"), (1, 2))
    assert vus == ["entier", "tuple"], vus
    c.enregistrer()
    d = VC.CacheCliquet("essai_486", "ctx-1", encoder=enc, decoder=dec, dossier=tmp_path)
    assert d.obtenir("a.py", "entier", VC.sha_texte("v1")) == 7
    assert d.obtenir("a.py", "tuple", VC.sha_texte("v1")) == (1, 2)


def test_un_cache_NON_UTF8_se_degrade_en_RECALCUL(tmp_path):
    #: `read_text` leve `UnicodeDecodeError`, pas `OSError` : c'est un chemin d'echec distinct,
    #: et le confondre ferait remonter l'exception jusqu'au cliquet -- une panne du cache
    #: deviendrait un plantage du garde-fou.
    (tmp_path / "essai_486.tsv").write_bytes(b"# format=1\tcontexte=ctx-1\n\xff\xfe\x00pas utf-8")
    c = _cache(tmp_path)
    assert c.obtenir("a.py", "ap", "sha") is VC.MANQUE


def test_le_cache_desactive_ne_sert_ni_n_ecrit(tmp_path, monkeypatch):
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    c.enregistrer()
    monkeypatch.setenv(VC.ENV_SANS_CACHE, "1")
    d = VC.CacheCliquet("essai_486", "ctx-1", dossier=tmp_path)
    assert d.obtenir("a.py", "ap", VC.sha_texte("v1")) is VC.MANQUE
    d.poser("a.py", "ap", VC.sha_texte("v1"), ["y"])
    assert d.enregistrer() is False, "desactive, il ne doit pas TOUCHER l'artefact versionne"


def test_une_ecriture_impossible_n_est_PAS_un_verdict(tmp_path):
    #: Le fichier de cache est un REPERTOIRE : `write_text` echoue. Le cliquet a deja rendu son
    #: verdict quand `enregistrer` est appele ; l'echec doit etre avale, pas propage.
    (tmp_path / "essai_486.tsv").mkdir()
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    assert c.enregistrer() is False


# ------------------------------- la SOURCE HORS ARBRE : le binaire du jeu (`deriver`)

def test_sha_gros_fichiers_rend_NONE_sur_un_absent(tmp_path):
    """TRI-ETAT : un fichier absent n'a pas de sha, il a un « pas mesure ».

    C'est ce qui empeche un depot SANS le jeu installe de se voir servir une derivation qu'aucune
    machine n'a produite ici. Un sha fabrique (chaine vide, zeros) serait exactement le vice que
    `host_inputs` combat sur l'autre gisement d'entrees."""
    assert VC.sha_gros_fichiers(tmp_path / "absent.dat") is None
    p = tmp_path / "present.dat"
    p.write_bytes(b"x" * (3 << 20))                     # 3 Mo : plusieurs blocs de lecture
    assert VC.sha_gros_fichiers(p) is not None
    q = tmp_path / "autre.dat"
    q.write_bytes(b"x" * (3 << 20) + b"y")
    assert VC.sha_gros_fichiers(p) != VC.sha_gros_fichiers(q)
    #: L'ordre et le nombre de fichiers comptent : deux jeux differents ne se confondent pas.
    assert VC.sha_gros_fichiers(p, q) != VC.sha_gros_fichiers(q, p)


@pytest.mark.parametrize("mod", ["probe_477r24r1_slots_interface",
                                 "probe_477r25_slots_autres_interfaces"])
def test_la_derivation_est_clee_sur_le_BINAIRE_DU_JEU(mod):
    """La memoisation de `deriver()` n'est pas tautologique -- et voici pourquoi, mecaniquement.

    L'etage 2 confronte la derivation (cote METADATA) a l'entree versionnee (cote DEPOT). Ce qui
    est cache est le seul cote METADATA, sous une cle qui contient le hash du `global-metadata.dat`
    ET de `frida/methods.tsv`. Les deux cotes restent donc INDEPENDANTS, et c'est ce qui fait que
    falsifier l'entree ne peut produire qu'un faux ROUGE (bruyant), jamais un faux VERT (mesure
    #486-r1 : table tronquee a 40 -> 110 ecarts, rc=1).

    Si un jour la cle cessait de porter le binaire, ce test rougirait -- avant que quiconque
    n'ait le temps de croire un vert."""
    src = _source(mod)
    corps = src.split("def deriver(")[1].split("\ndef ")[0]
    assert "sha_gros_fichiers(meta_path, methods_tsv)" in corps, (
        "la cle de `deriver` doit contenir le HASH DU BINAIRE DU JEU, pas seulement le build")
    assert "if sha is None:" in corps, (
        "sha non calculable => RECALCUL, jamais une attestation servie")


# ------------------------------------------------- la LIMITE : falsification COHERENTE

def test_une_entree_falsifiee_de_facon_COHERENTE_est_SERVIE(tmp_path):
    """MESURE, pas defaut : aucune cle ne peut voir un verdict faux pose sur le BON hash."""
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["VRAI"])
    c.enregistrer()
    p = tmp_path / "essai_486.tsv"
    p.write_text(p.read_text(encoding="utf-8").replace('["VRAI"]', '["FAUX"]'), encoding="utf-8")
    d = _cache(tmp_path)
    assert d.obtenir("a.py", "ap", VC.sha_texte("v1")) == ["FAUX"], (
        "si ceci change, la conception du cache a change : re-lire #486-r1 avant d'y toucher")
    #: ⚠ ET ELLE EST AUTO-PERSISTANTE : le run suivant la RELIT (le sha correspond) et la
    #: REECRIT telle quelle. Rejouer le cliquet ne la repare donc PAS -- mesure #486-r1. La
    #: seule sortie est `--verifier-cache` (qui la NOMME) puis SUPPRESSION du fichier.
    d.enregistrer()
    e = _cache(tmp_path)
    assert e.obtenir("a.py", "ap", VC.sha_texte("v1")) == ["FAUX"], (
        "un rejeu ne lave pas une entree falsifiee -- c'est pourquoi la reparation est une "
        "SUPPRESSION, et pourquoi ce fait doit rester ecrit")


def test_verifier_NOMME_l_entree_falsifiee(tmp_path):
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["VRAI"])
    c.poser("b.py", "ap", VC.sha_texte("v1"), ["VRAI"])
    c.enregistrer()
    p = tmp_path / "essai_486.tsv"
    p.write_text(p.read_text(encoding="utf-8").replace('a.py\tap\t', 'a.py\tap\t', 1)
                 .replace('["VRAI"]', '["FAUX"]', 1), encoding="utf-8")
    espion = _cache(tmp_path, relire=False)
    for rel in ("a.py", "b.py"):
        assert espion.contribution(rel, "ap", VC.sha_texte("v1"),
                                   lambda: ["VRAI"]) == ["VRAI"], "l'espion RECALCULE tout"
    ecarts = VC.verifier(espion)
    assert len(ecarts) == 1 and "FALSIFIEE" in ecarts[0] and "a.py" in ecarts[0], ecarts
    assert "b.py" not in " ".join(ecarts), "une entree JUSTE ne doit pas etre accusee"


def test_verifier_voit_l_entree_ORPHELINE_et_l_entree_ABSENTE(tmp_path):
    c = _cache(tmp_path)
    c.poser("mort.py", "ap", VC.sha_texte("v1"), ["x"])
    c.enregistrer()
    espion = _cache(tmp_path, relire=False)
    espion.contribution("neuf.py", "ap", VC.sha_texte("v1"), lambda: ["y"])
    ecarts = " | ".join(VC.verifier(espion))
    assert "ORPHELINE mort.py" in ecarts, ecarts
    assert "ABSENTE neuf.py" in ecarts, ecarts


# ------------------------------------------------------------------ le CABLAGE (statique)

def _source(mod):
    return (_PYDIR / (mod + ".py")).read_text(encoding="utf-8")


def _contextes(mod) -> list[str]:
    """Le SOURCE de l'argument `contexte` de CHAQUE `CacheCliquet(...)` construit dans `mod`.

    ⚠ LE DISCRIMINANT EST LA CONSTRUCTION DU CACHE, PAS L'APPEL A `sha_fichiers`, et c'est ce qui
    a sauve ce test -- deux fois. Version 1 : arguments de tous les `sha_fichiers` APLATIS sous un
    `any`, donc muter le contexte de `cache()` seul restait vert (l'appel du mode espion suffisait
    a satisfaire le `any`). Version 2 : un contexte par APPEL `sha_fichiers`, donc remplacer celui
    de `cache()` par un litteral FAISAIT DISPARAITRE l'appel -- et un critere qui n'enumere que ce
    qu'il trouve ne peut pas voir ce qui a ete retire. Enumerer les CONSTRUCTIONS ferme les deux :
    un cache construit sans contexte derive est visible, qu'il en porte un faux ou aucun.

    Lu par AST, pas par grep : le meme appel s'ecrit sur une ou trois lignes selon la longueur de
    ses arguments, et un critere textuel rougissait sur la seule mise en forme.
    """
    out = []
    for n in ast.walk(ast.parse(_source(mod))):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "CacheCliquet"):
            continue
        kw = {k.arg: ast.unparse(k.value) for k in n.keywords}
        out.append(kw.get("contexte", "<ABSENT>"))
    return out


@pytest.mark.parametrize("mod", sorted(CACHES))
def test_un_cliquet_cache_porte_SON_source_dans_son_contexte(mod):
    """Editer une regex du cliquet DOIT invalider ses entrees -- sinon le cache atteste pour un
    critere qui n'existe plus. Le seul appariement sur est le sha du source."""
    ctxs = _contextes(mod)
    assert ctxs, "%s ne construit aucun `CacheCliquet` : le cablage a disparu" % mod
    for c in ctxs:
        assert "sha_fichiers" in c and "__file__" in c, (
            "CHAQUE contexte doit etre DERIVE du SOURCE du cliquet, sinon editer son critere "
            "laisserait les anciennes entrees valides -- vu : %s" % c)


@pytest.mark.parametrize("mod", ["probe_477r24r1_slots_interface",
                                 "probe_477r25_slots_autres_interfaces"])
def test_un_cliquet_qui_resout_contre_le_BUILD_porte_sa_table_dans_son_contexte(mod):
    """Les citations de #477 sont confrontees a la table de slots : au changement de build, tout
    doit MANQUER. Mesure #486-r1 : 4944 et 3708 entrees, hits 0 apres changement de table."""
    ctxs = _contextes(mod)
    assert ctxs
    for c in ctxs:
        assert "tsv_path()" in c, (
            "CHAQUE contexte doit contenir l'entree versionnee des slots -- vu : %s" % c)


@pytest.mark.parametrize("mod", sorted(CACHES))
def test_les_DEUX_contextes_d_un_cliquet_sont_IDENTIQUES(mod):
    """Le mode espion doit lire le MEME cache que le mode normal.

    S'ils divergeaient, `--verifier-cache` confronterait le recalcul a un fichier qu'il n'a jamais
    servi : il rendrait tout ORPHELIN et ABSENT, un rouge qui n'accuse rien -- ou pire, il
    resterait vert sur un cache reellement faux."""
    ctxs = _contextes(mod)
    assert len(ctxs) == 2, (
        "un cliquet cache construit exactement DEUX caches -- le normal et l'espion de "
        "`--verifier-cache` ; vu %d" % len(ctxs))
    assert ctxs[0] == ctxs[1], "les contextes divergent : %s" % ctxs


@pytest.mark.parametrize("mod", sorted(CACHES))
def test_chaque_cliquet_cache_expose_verifier_cache(mod):
    assert "--verifier-cache" in _source(mod), (
        "la falsification coherente n'est visible QUE par la re-verification : chaque cliquet "
        "cache doit l'exposer")


@pytest.mark.parametrize("mod,pourquoi", sorted(NON_CACHABLES.items()))
def test_aucun_cliquet_a_verdict_GLOBAL_n_est_cache(mod, pourquoi):
    """LA regle du chantier. Un cache sur un verdict global fabrique des faux verts."""
    arbre = ast.parse(_source(mod))
    importes = {a.name for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
    importes |= {n.module for n in ast.walk(arbre)
                 if isinstance(n, ast.ImportFrom) and n.module}
    assert "verdict_cache" not in importes, (
        "%s ne doit PAS etre cache : %s" % (mod, pourquoi))


@pytest.mark.parametrize("nom", sorted(CACHES.values()))
def test_le_cache_versionne_est_present_et_BIEN_FORME(nom):
    """Un cache versionne absent rendrait tout worktree frais FROID -- c'est-a-dire inutile."""
    p = VC.DOSSIER / (nom + ".tsv")
    assert p.is_file(), "cache versionne absent : %s" % p
    lignes = p.read_text(encoding="utf-8").splitlines()
    entete = [l for l in lignes if l.startswith("# format=")]
    assert len(entete) == 1 and "contexte=" in entete[0], entete
    corps = [l for l in lignes if not l.startswith("#") and l.strip()]
    assert corps, "un cache vide n'est pas un cache"
    cles = [(l.split("\t")[0], l.split("\t")[1]) for l in corps]
    assert all(l.count("\t") == 3 for l in corps), "4 colonnes par ligne, toujours"
    assert cles == sorted(cles), (
        "le fichier doit etre TRIE par (fichier, appel) : c'est ce qui rend le diff d'un commit "
        "proportionnel aux fichiers touches, et le conflit de merge rare")
    assert len(set(cles)) == len(cles), "une cle (fichier, appel) ne peut apparaitre qu'une fois"


def test_le_cache_ne_vit_ni_sous_data_ni_sous_logs():
    """`data/` ne porte que des ENTREES du jeu (invariant 3, garde par probe_273/0c) ; `logs/`
    meurt avec le worktree, donc un cache y serait toujours froid la ou il doit servir."""
    rel = VC.DOSSIER.resolve().relative_to(REPO.resolve()).as_posix()
    assert not rel.startswith("data/") and not rel.startswith("logs/"), rel
    assert rel == "scripts/cliquets-cache", rel
