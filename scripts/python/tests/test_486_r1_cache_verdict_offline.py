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
        "scripts/python/verdict_cache.py", "scripts/cliquets-cache/**",
        # MESURE : le controle de fidelite REJOUE des cliquets reels, donc leur source
        # entre au verdict.
        "scripts/python/probe_181_targeting_gaps.py",
        "scripts/python/probe_485_imports_differes.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le foyer du cache de verdict et les fichiers de cache VERSIONNES qu'il ecrit : ce "
              "test recalcule tout en mode espion et confronte au disque, donc il depend du code "
              "du cache et du contenu de `scripts/cliquets-cache/`. Rien d'autre du depot "
              "n'entre dans son verdict.",
}
import ast
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import verdict_cache as VC  # noqa: E402

REPO = _PYDIR.parents[1]

#: Les cliquets CACHES a CONTRAT COMPLET, avec le nom de leur fichier de cache versionne.
#: « Contrat complet » = ils exposent `--verifier-cache` (le seul controle qui voie une entree
#: falsifiee de facon coherente) ET ils appellent `rendre_compte_du_cache` (le cran de fraicheur
#: #486-r22). Ce ne sont PAS tous les caches du depot : cf. `CACHES_VERSIONNES` juste apres.
CACHES = {
    "probe_477r24r1_slots_interface": "probe_477r24r1_slots_interface",
    "probe_477r25_slots_autres_interfaces": "probe_477r25_slots_autres_interfaces",
    "probe_313_enum_mirror_bijection": "probe_313_enum_mirror_bijection",
    #: #486-r11 -- le SEUL dont la cle de ligne n'est PAS le sha d'un fichier : c'est celui de la
    #: FERMETURE transitive des imports du module. La localite est la meme, elle porte juste sur
    #: un SOUS-GRAPHE au lieu d'un fichier ; tout le reste du contrat (peremption, contexte,
    #: menage, panne, re-verification) est identique, et c'est pourquoi il entre ICI.
    "probe_270r4r2_import_en_premier": "probe_270r4r2_import_en_premier",
    #: #486-r17 -- meme critere qu'au-dessus (charger la cible dans un process FRAIS), donc meme
    #: cle : la FERMETURE de la cible. Il etait dans `NON_CACHABLES` avec la raison « le verdict
    #: depend du sous-graphe » -- laquelle decrit exactement la cle qui EXISTE depuis #486-r11.
    "probe_485_imports_differes": "probe_485_imports_differes",
}

#: ---------------------------------------------------------------- LE REGISTRE DES 11 CACHES
#:
#: ⚠ POURQUOI CE REGISTRE EXISTE, ET CE QU'IL A RATTRAPE (#486-r17, mesure du 2026-08-15).
#: `CACHES` ci-dessus etait ENUMERE, et il a DECROCHE : le depot porte **11** fichiers sous
#: `scripts/cliquets-cache/`, produits par **8** modules, quand `CACHES` en connaissait **4**.
#: Sept caches VERSIONNES n'etaient donc gardes par RIEN -- ni forme, ni contexte, ni fraicheur --
#: et deux d'entre eux ont ete pris en flagrant delit de derive SILENCIEUSE : jouer
#: `probe_326_dsl_primitive_inventory.py` reecrit son cache et rend `rc=0` (1 ligne ajoutee,
#: 2 retirees), jouer `probe_283_enum_ordinal_sweep.py --step mirror` idem (402 ajoutees,
#: 237 retirees). Exactement le regime que #486-r22 disait avoir ferme.
#:
#: ⚠ IL EST ECRIT A LA MAIN, ET C'EST LE POINT. Un registre DERIVE du code ne peut pas montrer
#: l'oubli : il epouserait toute construction neuve et resterait vert. Ce qui est derive, c'est
#: la REALITE (les `.tsv` presents, les `CacheCliquet(...)` construits) ; ce qui est declare, c'est
#: l'ATTENDU. Les deux sont confrontes DANS LES DEUX SENS -- un fichier sans ligne ici rougit,
#: une ligne sans fichier aussi.
#:
#:      module          le module qui CONSTRUIT ce cache
#:      cran            ce module appelle-t-il `rendre_compte_du_cache` ? (fraicheur #486-r22)
#:      espion          ce module expose-t-il `--verifier-cache` ? (fidelite #486-r1)
#:      pourquoi        pour un `False`, la RAISON. C'est elle qui separe un choix d'un oubli.
CACHES_VERSIONNES = {
    "probe_477r24r1_slots_interface": {
        "module": "probe_477r24r1_slots_interface", "cran": True, "espion": True},
    "probe_477r25_slots_autres_interfaces": {
        "module": "probe_477r25_slots_autres_interfaces", "cran": True, "espion": True},
    "probe_313_enum_mirror_bijection": {
        "module": "probe_313_enum_mirror_bijection", "cran": True, "espion": True},
    "probe_270r4r2_import_en_premier": {
        "module": "probe_270r4r2_import_en_premier", "cran": True, "espion": True},
    "probe_485_imports_differes": {
        "module": "probe_485_imports_differes", "cran": True, "espion": True},
    "probe_283_step_mirror": {
        "module": "probe_283_enum_ordinal_sweep", "cran": True, "espion": True},
    "probe_283_step_exec": {
        "module": "probe_283_enum_ordinal_sweep", "cran": True, "espion": True},
    "probe_175r2_derivation_get_CanBeImmuneTo": {
        "module": "probe_175r2_can_be_immune_to", "cran": False, "espion": False,
        "pourquoi": "cle par les ENTREES DU BUILD (`sha_gros_fichiers`), pas par un fichier du "
                    "depot : ce cache ne peut bouger qu'a une mise a jour du jeu, jamais a une "
                    "PR. Le cran de fraicheur y rougirait sur le seul evenement ou la "
                    "regeneration est deja obligatoire et deja faite -- il n'ajouterait aucun "
                    "signal. Et le mode espion suppose un balayage a recalculer ; ici l'entree "
                    "est UNIQUE par getter, donc `--verifier-cache` se reduit a rejouer le "
                    "cliquet, ce que le cache ne dispense pas de faire."},
    "probe_175r2_derivation_get_KeepOnChangeOwner": {
        "module": "probe_175r2_can_be_immune_to", "cran": False, "espion": False,
        "pourquoi": "idem `get_CanBeImmuneTo` -- meme deriveur, meme cle de build, un fichier "
                    "par getter pour que le menage de l'un n'evince pas l'entree de l'autre"},
    "probe_175r2_derivation_get_RemoveOnDeathStep": {
        "module": "probe_175r2_can_be_immune_to", "cran": False, "espion": False,
        "pourquoi": "idem `get_CanBeImmuneTo`"},
    "probe_175r2_derivation_get_KeepOnRevive": {
        "module": "probe_175r2_can_be_immune_to", "cran": False, "espion": False,
        "pourquoi": "idem `get_CanBeImmuneTo` -- quatrieme getter du meme deriveur (`IEffect` "
                    "slot 2, repositionne par `probe_547r13_keep_on_revive.py`), meme cle de "
                    "build, un fichier par getter"},
    "probe_326_inventaire_natif": {
        "module": "probe_326_dsl_primitive_inventory", "cran": False, "espion": False,
        "pourquoi": "ecrit depuis `native_primitives`, appelee EN BIBLIOTHEQUE par d'autres "
                    "cliquets : le process qui reecrit le fichier n'est pas celui qui rend le "
                    "verdict, donc il n'y a pas de rc a teinter. Cle par les deux tables du "
                    "build -- il ne bouge qu'a un re-dump."},
    "il2cpp_noms_declares": {
        "module": "il2cpp_metadata", "cran": False, "espion": False,
        "pourquoi": "`il2cpp_metadata` est une BIBLIOTHEQUE : aucun `main`, aucun rc. Cle par "
                    "`global-metadata.dat` (hors depot) et `frida/methods.tsv` -- il ne bouge "
                    "qu'a une mise a jour du jeu."},
}

#: Les cliquets dont le verdict est GLOBAL ou dont la localite N'EST PAS ETABLIE. Ils ne doivent
#: PAS toucher a `verdict_cache`. La raison est ecrite ici, pas ailleurs : c'est elle qui fait la
#: difference entre un choix et un oubli.
NON_CACHABLES = {
    "probe_468_collision_numeros":
        "GLOBAL par construction -- une collision est une RELATION entre deux definitions, dont "
        "l'une peut vivre dans un fichier NON touche",
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


# ------------------------------------- le CRAN DE FRAICHEUR ne juge QUE ce qu'il a ECRIT

def test_le_cran_de_fraicheur_rend_PAS_MESURE_tant_que_rien_n_a_ete_ECRIT(tmp_path):
    """#486-r17 -- LE FAUX VERT D'INTENDANCE, et ses TROIS portes.

    `cache_a_commiter` demande a `git diff` si le fichier differe de l'index. Sa premisse ecrite
    est « le run vient d'ecrire le fichier de toute facon ». Cette premisse n'est pas etablie par
    l'appel : trois chemins la violent, et sur les trois le `git diff` compare le fichier de la
    passe PRECEDENTE -- rendant `0`, c'est-a-dire « a jour », c'est-a-dire un VERT sur une mesure
    qui n'a pas eu lieu.

        1. `enregistrer()` jamais appele            (un mode partiel, un `--verifier-cache`)
        2. `enregistrer()` appele, RIEN vu          (perimetre vide, pre-filtre qui ecarte tout)
        3. `enregistrer()` appele, ECRITURE EN ECHEC (disque plein, fichier verrouille)

    Les trois doivent sortir en PAS MESURE (`None`), jamais en `False`."""
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    perime, detail = VC.cache_a_commiter(c, racine=tmp_path)
    assert perime is None and "enregistrer" in detail, (perime, detail)

    vide = _cache(tmp_path)
    assert vide.enregistrer() is False
    perime, detail = VC.cache_a_commiter(vide, racine=tmp_path)
    assert perime is None and "AUCUNE entree" in detail, (perime, detail)

    (tmp_path / "bloque.tsv").mkdir()
    casse = VC.CacheCliquet("bloque", "ctx-1", dossier=tmp_path)
    casse.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    assert casse.enregistrer() is False
    perime, detail = VC.cache_a_commiter(casse, racine=tmp_path)
    assert perime is None and "PANNE" in detail, (perime, detail)


def test_le_cran_de_fraicheur_NE_TEINTE_PAS_le_rc_quand_il_n_a_pas_mesure(tmp_path, capsys):
    """Une panne de capteur ne rend pas un verdict -- ni vert, ni rouge. Elle se DIT."""
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    assert VC.rendre_compte_du_cache(c, 0, racine=tmp_path) == 0
    assert "NON MESUREE" in capsys.readouterr().out


def _git_bouchon(monkeypatch, rc_ls_files: int, rc_diff: int):
    """Substitue `subprocess.run` en distinguant `ls-files` (suivi ?) de `diff` (modifie ?).

    Un bouchon qui rendrait le MEME rc aux deux ferait passer un « non suivi » pour un
    « modifie » -- et ce test-ci ne verrait plus la difference qu'il est cense garder."""
    class _R:
        def __init__(self, rc):
            self.returncode, self.stderr, self.stdout = rc, "", ""

    import subprocess as _sp

    def _run(argv, *a, **k):
        return _R(rc_ls_files if "ls-files" in argv else rc_diff)

    monkeypatch.setattr(_sp, "run", _run)


def test_le_cran_de_fraicheur_MORD_encore_apres_une_ECRITURE_REELLE(tmp_path, monkeypatch):
    """⚠ LA CONTRE-EPREUVE, et elle est indispensable : un cran qui n'accuse plus RIEN est aussi
    faux qu'un cran qui accuse a tort -- et le premier ne le dit pas. On substitue `git` pour
    n'eprouver QUE l'aiguillage, sans dependre d'un depot de test."""
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    assert c.enregistrer() is True and c.ecrit is True

    _git_bouchon(monkeypatch, rc_ls_files=0, rc_diff=1)
    perime, detail = VC.cache_a_commiter(c, racine=tmp_path)
    assert perime is True and "REECRIT" in detail, (perime, detail)
    assert VC.rendre_compte_du_cache(c, 0, racine=tmp_path) == VC.EX_CACHE_A_COMMITER

    _git_bouchon(monkeypatch, rc_ls_files=0, rc_diff=0)
    perime, _ = VC.cache_a_commiter(c, racine=tmp_path)
    assert perime is False, "un fichier identique a l'index doit se taire, pas rougir"
    assert VC.rendre_compte_du_cache(c, 0, racine=tmp_path) == 0

    _git_bouchon(monkeypatch, rc_ls_files=0, rc_diff=128)
    perime, detail = VC.cache_a_commiter(c, racine=tmp_path)
    assert perime is None and "rc=128" in detail, (perime, detail)


def test_un_cache_versionne_NON_SUIVI_par_git_ROUGIT(tmp_path, monkeypatch):
    """#486-r17 -- LA QUATRIEME PORTE, et la plus couteuse des quatre.

    `git diff --quiet -- <chemin>` IGNORE ce que git ne suit pas. Un cache tout neuf, ecrit pour
    la premiere fois et jamais `git add`-e, rendait donc « est a jour (identique a l'index) » --
    mesure du 2026-08-15, prise en flagrant delit au cablage du cache de `probe_485` : le fichier
    etait `??` et le cran se taisait.

    Ce n'est pas un detail d'intendance. Un cache qui n'entre jamais dans le depot fait repartir
    FROID tout worktree frais, c'est-a-dire exactement le regime pour lequel il est VERSIONNE
    (cf. l'en-tete de `verdict_cache`). L'optimisation existerait dans la boucle locale de son
    auteur et nulle part ailleurs, sans que rien ne le dise."""
    c = _cache(tmp_path)
    c.poser("a.py", "ap", VC.sha_texte("v1"), ["x"])
    assert c.enregistrer() is True

    _git_bouchon(monkeypatch, rc_ls_files=1, rc_diff=0)     # non suivi, et pourtant `diff` muet
    perime, detail = VC.cache_a_commiter(c, racine=tmp_path)
    assert perime is True and "SUIVI" in detail, (perime, detail)
    assert VC.rendre_compte_du_cache(c, 0, racine=tmp_path) == VC.EX_CACHE_A_COMMITER

    #: CONTRE-EPREUVE : une fois SUIVI et identique a l'index, le meme chemin doit se taire --
    #: sans quoi le cran deviendrait inextinguible et se ferait desarmer.
    _git_bouchon(monkeypatch, rc_ls_files=0, rc_diff=0)
    assert VC.cache_a_commiter(c, racine=tmp_path)[0] is False


def test_un_rc_deja_ROUGE_n_est_jamais_masque_par_le_cran(tmp_path):
    """Le gisement prime sur l'intendance, dans les deux sens : on ne masque pas un vrai rouge
    derriere un rouge d'artefact, ni l'inverse."""
    c = _cache(tmp_path)
    assert VC.rendre_compte_du_cache(c, 1, racine=tmp_path) == 1


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


def _modules_du_depot() -> list[str]:
    """Tous les modules `scripts/python/*.py` -- le PERIMETRE de la derivation, non filtre.

    Volontairement PLAT (pas de `rglob`) : un `CacheCliquet` ne se construit que dans un cliquet
    ou une bibliotheque de ce niveau, et `engine/**` n'en porte aucun. Si cela changeait, l'etage
    « tout .tsv a une ligne au registre » le verrait quand meme -- c'est le fichier PRODUIT qui
    est le temoin ultime, pas le site de construction.
    """
    return sorted(p.stem for p in _PYDIR.glob("*.py"))


def _constructions() -> dict[str, list[str]]:
    """`{module: [source de l'argument `contexte` de chaque `CacheCliquet(...)`]}`, par AST.

    ⚠ LA DERIVATION DIT CE QUI EXISTE, JAMAIS CE QUI DEVRAIT EXISTER. C'est `CACHES_VERSIONNES`
    qui porte l'attendu ; ici on ne fait que RECENSER, et un recenseur qui filtrerait par une
    liste de modules connus ne pourrait pas montrer le module qu'on a oublie.
    """
    out: dict[str, list[str]] = {}
    for mod in _modules_du_depot():
        try:
            arbre = ast.parse(_source(mod))
        except (OSError, SyntaxError, UnicodeDecodeError):       # pragma: no cover - arbre casse
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = (n.func.attr if isinstance(n.func, ast.Attribute)
                   else n.func.id if isinstance(n.func, ast.Name) else None)
            if nom != "CacheCliquet":
                continue
            kw = {k.arg: ast.unparse(k.value) for k in n.keywords}
            out.setdefault(mod, []).append(kw.get("contexte", "<ABSENT>"))
    return out


def test_le_recensement_des_constructions_est_NON_VIDE():
    """Un recenseur vide passerait pour vert sur tous les etages qui le consomment.

    Il a deja rendu zero une fois dans ce depot -- pas ici, mais sur le meme motif (`probe_181`
    rendait `0` inconditionnellement, un inventaire deguise en garde-fou). On assertionne donc
    son propre non-vide, et son ordre de grandeur."""
    trouve = _constructions()
    assert len(trouve) >= 8, (
        "le recensement des `CacheCliquet(...)` rend %d module(s) : soit le depot a perdu ses "
        "caches, soit le critere AST ne mord plus -- dans les deux cas ce fichier ne garde "
        "plus rien" % len(trouve))


def test_TOUT_cache_versionne_est_INSCRIT_au_registre():
    """SENS 1 -- du disque vers le registre. C'est l'etage qui a rattrape les 7 caches muets.

    Un `.tsv` qui apparait sous `scripts/cliquets-cache/` sans ligne ici est un cache que rien ne
    garde : ni sa forme, ni son contexte, ni sa fraicheur, ni sa fidelite. Le registre est ecrit
    a la main EXPRES -- s'il etait derive du disque, il epouserait le fichier neuf et cet etage
    serait tautologique."""
    sur_disque = sorted(p.stem for p in VC.DOSSIER.glob("*.tsv"))
    assert sur_disque, "aucun cache versionne trouve : le dossier a disparu ou change de nom"
    inconnus = [n for n in sur_disque if n not in CACHES_VERSIONNES]
    assert not inconnus, (
        "cache(s) VERSIONNE(S) hors registre : %s -- inscris-les dans `CACHES_VERSIONNES` avec "
        "leur module producteur et leur regime (`cran`, `espion`), DANS LE MEME COMMIT"
        % ", ".join(inconnus))


def test_TOUTE_ligne_du_registre_a_son_fichier():
    """SENS 2 -- du registre vers le disque. Sans lui, une ligne perimee ferait croire a une
    couverture qui n'existe plus, et les etages parametres sur le registre tourneraient a vide."""
    manquants = [n for n in CACHES_VERSIONNES if not (VC.DOSSIER / (n + ".tsv")).is_file()]
    assert not manquants, (
        "ligne(s) de registre sans fichier : %s -- le cache a-t-il ete renomme ou supprime ?"
        % ", ".join(manquants))


def test_TOUT_module_qui_construit_un_cache_est_PRODUCTEUR_au_registre():
    """SENS 3 -- du code vers le registre. Un module qui construit un `CacheCliquet` sans
    apparaitre comme producteur ecrit un artefact que personne n'a declare."""
    producteurs = {v["module"] for v in CACHES_VERSIONNES.values()}
    orphelins = sorted(set(_constructions()) - producteurs)
    assert not orphelins, (
        "module(s) construisant un `CacheCliquet` sans etre producteur declare : %s"
        % ", ".join(orphelins))


@pytest.mark.parametrize("nom,fiche", sorted(CACHES_VERSIONNES.items()))
def test_le_REGIME_declare_par_le_registre_est_CELUI_DU_CODE(nom, fiche):
    """⚠ CONTRE-EPREUVE BIDIRECTIONNELLE, et c'est ce qui empeche la declaration d'etre decorative.

    Un `cran: True` qui n'appelle rien serait un faux vert. Mais un `cran: False` qui appelle
    QUAND MEME le cran est tout aussi faux : la ligne « pourquoi » deviendrait une prescription
    perimee, et le jour ou quelqu'un la lit pour justifier un nouveau cache sans cran, il
    recopierait une exemption qui n'existe plus. Les deux sens sont donc assertes."""
    src = _source(fiche["module"])
    for clef, marqueur in (("cran", "rendre_compte_du_cache"), ("espion", "--verifier-cache")):
        present = marqueur in src
        if fiche[clef]:
            assert present, (
                "%s declare `%s: True` mais `%s` n'apparait pas dans %s.py"
                % (nom, clef, marqueur, fiche["module"]))
        else:
            assert fiche.get("pourquoi"), (
                "%s declare `%s: False` sans RAISON ecrite -- c'est la raison qui separe un "
                "choix d'un oubli" % (nom, clef))
            assert not present, (
                "%s declare `%s: False` mais %s.py appelle bien `%s` : la raison ecrite au "
                "registre est PERIMEE, et une exemption perimee se recopie"
                % (nom, clef, fiche["module"], marqueur))


def test_aucun_CONTEXTE_ne_passe_par_la_variante_OCTETS():
    """#486-r17 -- `sha_fichiers` hache les OCTETS : un cache versionne cle par elle repart a zero
    au moindre `git rebase` sous `core.autocrlf=true` (mesure : 119 s au lieu de 20 s), et serait
    froid EN PERMANENCE sur une plateforme a LF.

    La bascule a eu lieu le 2026-08-07 (`d4b78353`) ; ce qui manquait, c'est le cran qui empeche
    le retour. Il en faut un : `sha_fichiers` SURVIT (le test des deux variantes en a besoin comme
    temoin), donc rien n'empechait un cliquet neuf de l'appeler par imitation.

    ⚠ Le critere porte sur le CONTEXTE d'une construction, pas sur la presence du symbole dans le
    fichier -- sans quoi ce fichier-ci rougirait sur lui-meme."""
    fautifs = [(mod, c) for mod, ctxs in _constructions().items() for c in ctxs
               if "sha_fichiers_texte" not in c and "sha_fichiers" in c]
    assert not fautifs, (
        "contexte(s) cle(s) sur les OCTETS : %s -- employer `sha_fichiers_texte`"
        % "; ".join("%s -> %s" % f for f in fautifs))


@pytest.mark.parametrize("mod", sorted({v["module"] for v in CACHES_VERSIONNES.values()}))
def test_un_cliquet_cache_porte_SON_source_dans_son_contexte(mod):
    """Editer une regex du cliquet DOIT invalider ses entrees -- sinon le cache atteste pour un
    critere qui n'existe plus. Le seul appariement sur est le sha du source.

    ⚠ LE CRITERE PORTE SUR LA PROPRIETE, PAS SUR UNE FORME D'ECRITURE. Il exigeait `__file__`,
    ce qui est la forme employee par les QUATRE modules qu'il connaissait -- les quatre autres
    ecrivent `ici / "<mod>.py"`, tout aussi correct, et un critere de forme les aurait declares
    fautifs (ou, s'ils etaient restes hors du parametrage, invisibles). On demande donc : le
    contexte NOMME le source du module producteur, par `__file__` ou par son nom de fichier.
    """
    ctxs = _contextes(mod)
    assert ctxs, "%s ne construit aucun `CacheCliquet` : le cablage a disparu" % mod
    for c in ctxs:
        assert "sha_fichiers_texte" in c or "sha_texte" in c, (
            "CHAQUE contexte doit etre DERIVE d'un SOURCE, jamais un litteral -- vu : %s" % c)
        assert "__file__" in c or (mod + ".py") in c, (
            "CHAQUE contexte doit nommer le SOURCE du cliquet (`__file__` ou `%s.py`), sinon "
            "editer son critere laisserait les anciennes entrees valides -- vu : %s" % (mod, c))


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
def test_le_mode_ESPION_lit_le_MEME_cache_que_le_mode_NORMAL(mod):
    """Le mode espion doit lire le MEME cache que le mode normal.

    S'ils divergeaient, `--verifier-cache` confronterait le recalcul a un fichier qu'il n'a jamais
    servi : il rendrait tout ORPHELIN et ABSENT, un rouge qui n'accuse rien -- ou pire, il
    resterait vert sur un cache reellement faux.

    ⚠ LE CRITERE PORTE SUR LA PROPRIETE, PAS SUR UN COMPTE DE CONSTRUCTIONS. Il exigeait
    EXACTEMENT DEUX `CacheCliquet(...)` -- la forme des quatre premiers cliquets, qui ECRIVENT
    l'expression du contexte en toutes lettres aux deux endroits pour qu'on puisse les comparer.
    C'etait un critere de FORME, et il rougissait sur `probe_485_imports_differes`, dont la
    fabrique unique prend `relire` en parametre : une expression UNIQUE ne peut pas diverger
    d'elle-meme, donc cette forme-la est strictement PLUS SURE que celle qu'on exigeait. Le
    compte ne voyait d'ailleurs pas TROIS constructions divergentes ; la propriete, si.

    Les deux formes acceptees, et rien d'autre :
      * N constructions dont TOUS les contextes sont identiques (duplication comparee) ;
      * UNE construction, a condition qu'elle porte `relire` -- sans lui, aucun espion ne
        pourrait etre construit et `--verifier-cache` servirait le cache au lieu de le
        confronter.
    """
    ctxs = _contextes(mod)
    assert ctxs, "%s ne construit aucun `CacheCliquet` : le cablage a disparu" % mod
    if len(ctxs) == 1:
        arbre = ast.parse(_source(mod))
        parametre = any(
            isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "CacheCliquet"
            and any(k.arg == "relire" for k in n.keywords) for n in ast.walk(arbre))
        assert parametre, (
            "%s ne construit qu'UN cache et ne passe pas `relire` : le mode espion ne peut pas "
            "exister, donc `--verifier-cache` servirait le cache au lieu de le confronter" % mod)
        return
    assert len(set(ctxs)) == 1, (
        "les %d contextes de %s divergent -- le mode espion lirait un AUTRE fichier que le mode "
        "normal : %s" % (len(ctxs), mod, ctxs))


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

