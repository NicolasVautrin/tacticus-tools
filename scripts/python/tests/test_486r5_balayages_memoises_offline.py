"""#486-r5 -- GARDE des balayages AST MEMOISES. Offline pur, aucune session.

CE QUE CE FICHIER TIENT
-----------------------
Quatre balayages de tout `scripts/python/**` (2089 fichiers, 37 Mo) etaient re-executes a chaque
test qui en avait besoin. Mesure du 2026-08-06, machine chargee :

    `_substitution_impls()`   (test_additional_hits_variant_signatures_offline)  18 - 26 s  x3
    `P380.scan()`             (test_380_seed_bc_patch_survival_offline)          32 - 36 s  x2
    lecture + `ast.parse`     (test_ability_registry_ratchet, 2 visites)         18 - 20 s  x2
    `P448.index()`            (test_448_r3_r1_r1_greffe_sans_canal_offline)      3 parses PAR FICHIER

Ventilation du plus gros (`P380.scan`) : `ast.parse` 27,8 s, la visite 10,4 s, la lecture en
SERIE 3,2 s, et `Path(__file__).resolve()` RECALCULE dans la boucle 2,3 s.

La correction est un cache de RESULTAT -- jamais un cache d'AST : mesure du meme jour, retenir
les 2089 arbres de ce corpus coute **1013 Mo** de tas Python. Ce qui est memoise est donc
minuscule (deux tuples de chaines ; 180 records pour `scan`).

CE QU'UN CACHE PEUT CASSER, ET CE QUE CHAQUE ETAGE VERIFIE
---------------------------------------------------------
1. **LE BALAYAGE VOIT ENCORE** -- exerce sur un corpus SYNTHETIQUE dont on connait la reponse.
   Un cache pose sur un balayage devenu aveugle rendrait le silence DEFINITIF.
2. **PAS DE FUITE D'ETAT** -- l'objet partage doit etre immuable, ou re-clone a chaque appel.
   Un test qui muterait le releve du suivant produirait un vert (ou un rouge) sans rapport avec
   le depot. `scan()` rend des listes de dicts : la garde exige donc des objets DISTINCTS.
3. **LE CACHE MORD** -- un cache jamais consulte ne garderait rien et le gain serait imaginaire.
   Mesure par SUBSTITUTION du balayage sous-jacent (compteur d'appels), pas par un chronometre.
4. **LE CACHE REND CE QUE LE BALAYAGE A RENDU** -- pas une valeur reconstruite ni tronquee.
   Verifie par substitution, donc sans re-balayer le corpus complet.

POURQUOI PAS DE BALAYAGE REEL DU CORPUS ICI. Une premiere version le faisait : elle a coute
**+150 s**, soit plus que le gain qu'elle gardait -- un cliquet ne doit pas rouvrir le gisement
qu'il ferme. Les balayages reels du corpus complet sont exerces par les fichiers qu'ils
servent, chacun avec ses propres assertions.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
# Les modules de test cibles ne sont importables que si LEUR repertoire est sur le chemin :
# `tests/` n'est pas un paquet, et pytest ne l'y met qu'au moment ou il les collecte lui-meme.
for _d in (PYDIR, PYDIR / "tests", PYDIR / "tests" / "engine" / "runner"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import probe_380_seed_bc_patch_survival as P380                          # noqa: E402
import test_additional_hits_variant_signatures_offline as T393           # noqa: E402
import test_ability_registry_ratchet as T167                             # noqa: E402


# --- 1. LE BALAYAGE VOIT ENCORE (corpus synthetique, reponse connue) ----------------------------

_SUBSTITUTION = '''\
def _faux_exec(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods):
    return {}


def _hors_canal(state, attacker_id, autre):
    return {}
'''


def test_le_balayage_des_substitutions_TROUVE_la_forme_du_canal(tmp_path):
    """Le critere est structurel : les SIX premiers parametres. Un balayage qui ne verrait plus
    rien rendrait les cliquets de signature verts A VIDE -- et un cache pose dessus figerait cet
    aveuglement pour toute la passe."""
    (tmp_path / "faux_harnais.py").write_text(_SUBSTITUTION, encoding="utf-8")
    (tmp_path / "sans_rapport.py").write_text("def f(a, b):\n    return a\n", encoding="utf-8")
    vus = T393._balayer_substitutions(tmp_path)
    assert [(rel, nom) for rel, nom, _l, _p, _s in vus] == [("faux_harnais.py", "_faux_exec")], vus
    _rel, _nom, ligne, params, star = vus[0]
    assert ligne == 1 and star is False
    assert params[:6] == T393._HEAD


_CIBLAGE = '''\
RULE_TARGET_IS_ENEMY = 0x4000


def f(options):
    return options.has(0x4000)
'''


def test_le_balayage_de_ciblage_TROUVE_les_deux_formes(tmp_path):
    """Les deux releves sont produits par la MEME passe : si l'un des deux cessait d'etre
    alimente, son test resterait vert sur une liste vide -- exactement le vert vacueux."""
    (tmp_path / "fautif.py").write_text(_CIBLAGE, encoding="utf-8")
    (tmp_path / "sain.py").write_text(
        "from x import TR\nX = TR.TargetIsEnemy\n\n\ndef g(opts):\n"
        "    return opts.has(TR.TargetIsEnemy)\n", encoding="utf-8")
    constantes, bits = T167._balayer_ciblage(tmp_path)
    assert constantes == ("fautif.py:1  RULE_TARGET_IS_ENEMY = 0x4000",), constantes
    assert bits == ("fautif.py:5  options.has(0x4000)",), bits


_GREFFE = '''\
import catalog_inject as CI
from engine.runner.snapshot import load_state


def monte():
    CI.graft_passive_ability("tauCrisis", "NovaShield")
    return load_state({}, {}, {})
'''


def test_le_balayage_de_scan380_TROUVE_un_patch_de_seed_bc(tmp_path):
    """`_balayer` doit continuer a RETENIR les modules qui touchent un seed BC, et a ECARTER les
    autres -- un balayage devenu muet ferait rendre `SANS-PATCH` a tout le depot."""
    (tmp_path / "patcheur.py").write_text(
        'import json\n'
        'def ecrire(bc, out):\n'
        '    bc["Abilities"]["PassiveAbilities"]["LightImUp"] = {}\n'
        '    out.write_text(json.dumps(bc))\n', encoding="utf-8")
    (tmp_path / "neutre.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    recs = P380._balayer(tmp_path)
    noms = [r["path"].name for r in recs]
    assert noms == ["patcheur.py"], noms
    assert recs[0]["risky"], recs[0]


# --- 2. PAS DE FUITE D'ETAT ---------------------------------------------------------------------

def test_les_releves_de_ciblage_sont_IMMUABLES(tmp_path):
    """`tuple` de `str` : aucun test ne peut modifier ce que verra le suivant.

    Mesure sur une racine SYNTHETIQUE, et c'est deliberе : l'immuabilite est une propriete du
    BALAYAGE (il rend deja des tuples), pas du corpus. La verifier sur `scripts/python/**`
    couterait un balayage complet -- soit rouvrir le gisement que ce fichier ferme."""
    (tmp_path / "fautif.py").write_text(_CIBLAGE, encoding="utf-8")
    releves = T167._balayer_ciblage(tmp_path)
    assert isinstance(releves, tuple) and len(releves) == 2
    for seau in releves:
        assert isinstance(seau, tuple)
        assert seau and all(isinstance(x, str) for x in seau)


def test_le_releve_des_substitutions_est_IMMUABLE(tmp_path):
    """Meme propriete, autre balayage : `_substitution_impls` convertit en `tuple` de `tuple`s."""
    (tmp_path / "faux_harnais.py").write_text(_SUBSTITUTION, encoding="utf-8")
    lignes = T393._balayer_substitutions(tmp_path)
    assert lignes and all(isinstance(x, tuple) for x in lignes)
    assert all(isinstance(x[3], tuple) for x in lignes), "les parametres doivent etre un tuple"


def test_scan380_rend_des_objets_DISTINCTS_a_chaque_appel(monkeypatch, tmp_path):
    """`scan()` rend des listes de DICTS -- donc mutables. La seule facon sure de les memoiser
    est de rendre une copie profonde : muter le retour d'un appel ne doit rien changer au
    suivant. C'est le piege inverse d'une mise en cache, celui qui rend VERT un test qui
    devrait rougir.

    Joue sur une racine SYNTHETIQUE : c'est la PROPRIETE du cache qu'on mesure, pas le corpus."""
    (tmp_path / "patcheur.py").write_text(
        'import json\n'
        'def ecrire(bc, out):\n'
        '    bc["Abilities"]["PassiveAbilities"]["LightImUp"] = {}\n'
        '    out.write_text(json.dumps(bc))\n', encoding="utf-8")
    monkeypatch.setattr(P380, "_SCAN_CACHE", {})
    a = P380.scan(tmp_path)
    b = P380.scan(tmp_path)
    assert a is not b
    assert a == b
    assert a[0] is not b[0], "les records sont partages -- une mutation fuirait d'un test a l'autre"

    a[0]["risky"] = [("MUTATION-486r5", 0, 0, False)]
    a.append({"path": Path("faux.py"), "parse_error": None, "risky": [], "benign": [],
              "disk": [], "consumes": []})
    c = P380.scan(tmp_path)
    assert len(c) == len(b), "une insertion a fuite dans le cache"
    assert c[0]["risky"] == b[0]["risky"], "une mutation a fuite dans le cache"


# --- 3-4. LE CACHE MORD, ET IL REND CE QUE LE BALAYAGE A RENDU ----------------------------------

_TEMOIN_IMPLS = [("faux.py", "_exec", 1, ("state", "attacker_id", "target_id", "tgt", "thc",
                                          "groups"), False)]


def test_le_cache_des_substitutions_EVITE_le_second_balayage(monkeypatch):
    """Sans cette garde, le cache pourrait ne jamais etre consulte : les tests resteraient verts
    et le cout reviendrait, sans que rien ne le dise. Le balayage est SUBSTITUE -- on mesure la
    memoisation, pas le corpus."""
    appels = []

    def _faux(racine=None):
        appels.append(racine)
        return list(_TEMOIN_IMPLS)

    monkeypatch.setattr(T393, "_balayer_substitutions", _faux)
    monkeypatch.setattr(T393, "_IMPLS_CACHE", None)
    vus = [T393._substitution_impls() for _ in range(3)]
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 3 appels" % len(appels)
    assert all(v == tuple(_TEMOIN_IMPLS) for v in vus), vus
    assert all(isinstance(v, tuple) for v in vus), "la valeur memoisee doit etre IMMUABLE"
    assert vus[0] is vus[1] is vus[2], "le cache reconstruit sa valeur a chaque appel"


def test_le_cache_de_scan380_EVITE_le_second_balayage(monkeypatch, tmp_path):
    appels = []
    temoin = [{"path": tmp_path / "x.py", "parse_error": None, "risky": [("a", 1, "b", False)],
               "benign": [], "disk": [], "consumes": []}]

    monkeypatch.setattr(P380, "_balayer", lambda root: (appels.append(root), temoin)[1])
    monkeypatch.setattr(P380, "_SCAN_CACHE", {})
    a, b = P380.scan(tmp_path), P380.scan(tmp_path)
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a == temoin and b == temoin, (a, b)
    # ... et une RACINE differente n'est PAS servie par le cache de la premiere.
    autre = tmp_path / "sous"
    autre.mkdir()
    P380.scan(autre)
    assert len(appels) == 2, "le cache a servi une AUTRE racine -- le releve serait faux"


def test_le_cache_des_releves_de_ciblage_EVITE_le_second_balayage(monkeypatch):
    appels = []
    temoin = (("a.py:1  RULE_X = 0x1",), ("b.py:2  options.has(0x2)",))

    def _faux(racine=None):
        appels.append(racine)
        return temoin

    monkeypatch.setattr(T167, "_balayer_ciblage", _faux)
    monkeypatch.setattr(T167, "_RELEVES_CACHE", None)
    a, b = T167._releves_de_ciblage(), T167._releves_de_ciblage()
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a is b and a == temoin, (a, b)


# --- 5. probe_448 : UN SEUL `ast.parse` par fichier ---------------------------------------------

def test_index448_ne_parse_chaque_fichier_QU_UNE_FOIS(tmp_path, monkeypatch):
    """`index` appelait `parse` trois fois par fichier (ici, puis `resolve_calls`, puis
    `file_symbols`), chacune avec sa propre relecture disque. `ast.parse` de tout
    `scripts/python/**` coutant 27,8 s, cela pesait ~83 s des 107,8 s du fichier de test.

    L'arbre est passe en ARGUMENT, jamais memoise : la memoire reste celle d'UN arbre."""
    import probe_448_r3_r1_r1_greffe_sans_canal as P448

    (tmp_path / "a.py").write_text("import os\n\n\ndef f():\n    return os.getcwd()\n",
                                   encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import f\n\n\ndef g():\n    return f()\n",
                                   encoding="utf-8")
    vus = []
    reel = P448.parse
    monkeypatch.setattr(P448, "parse",
                        lambda path, texte=None: (vus.append(path), reel(path, texte))[1])
    idx = P448.index(P448.corpus(tmp_path), tmp_path)
    assert sorted(p.name for p in vus) == ["a.py", "b.py"], [p.name for p in vus]
    assert ("b", "g") in idx["graph"], sorted(idx["graph"])
    assert ("a", "f") in idx["graph"][("b", "g")], idx["graph"][("b", "g")]


# --- 6. probe_270-r4-r2 : un interpreteur par module, UNE SEULE FOIS ----------------------------

#: Trois modules REELS d'`engine/`, aux fermetures differentes. Depuis #486-r11 la cle n'est plus
#: une empreinte d'arbre substituable : c'est la FERMETURE du module, qui n'existe que pour un
#: module qui existe. Des noms fictifs (`engine.x`) partiraient en recalcul a chaque appel, et le
#: test serait vert a vide.
_REELS = ["engine.entities.stats", "engine.playbook.psyker", "engine.runner.snapshot"]


def _bac(monkeypatch, tmp_path, lances):
    import probe_270r4r2_import_en_premier as IP
    import verdict_cache

    def _faux(mod):
        lances.append(mod)
        return mod, 0, "", (IP.IC.CLOTURE.fermeture(mod) or frozenset())

    monkeypatch.setattr(IP, "_essayer", _faux)
    monkeypatch.setattr(IP, "_ESSAIS", {})
    monkeypatch.setattr(IP, "_OPAQUES", {})
    monkeypatch.setattr(IP, "_VUS", set())
    monkeypatch.setattr(IP, "_LANCES", [0])
    monkeypatch.setattr(IP, "_CACHE", verdict_cache.CacheCliquet(
        "jouet_486r5", "contexte-jouet", dossier=tmp_path))
    return IP


def test_essayer_tous_ne_relance_PAS_un_interpreteur_deja_lance(monkeypatch, tmp_path):
    """`_essayer` lance UN interpreteur par module -- 0,54 s piece, 131,6 s pour les 437 modules
    d'`engine/` a 8 workers. Deux fichiers de test balaient dans la MEME passe, et leurs
    perimetres se recouvrent a 201 modules : 44,1 s payes deux fois."""
    lances = []
    IP = _bac(monkeypatch, tmp_path, lances)

    a = IP.essayer_tous(_REELS[:2])
    b = IP.essayer_tous(_REELS[1:])
    assert lances == _REELS, lances
    assert a == [(m, 0, "") for m in _REELS[:2]], a
    assert b == [(m, 0, "") for m in _REELS[1:]], b


def test_essayer_tous_RE_ESSAIE_quand_SA_FERMETURE_a_CHANGE(monkeypatch, tmp_path):
    """LE piege inverse du cache : un verdict perime, et perime dans le sens VERT.

    #486-r11 : la cle n'est plus l'empreinte de l'arbre ENTIER mais celle de la FERMETURE du
    module. Ce que cet etage garde reste le meme invariant -- un changement de cle DOIT relancer.
    Que la cle bouge sur le bon perimetre (et PAS sur le reste) est garde, dans les deux sens,
    par `test_486r11_cle_sous_graphe_offline.py`.
    """
    lances = []
    IP = _bac(monkeypatch, tmp_path, lances)
    cible = _REELS[0]
    vraies = IP.IC.CLOTURE.cles([cible])

    IP.essayer_tous([cible])
    IP.essayer_tous([cible])
    assert lances == [cible], "le cache ne mord pas : %s" % lances

    monkeypatch.setattr(IP, "_cles", lambda mods: {m: "CLE-V2" for m in mods})
    IP.essayer_tous([cible])
    assert lances == [cible, cible], (
        "un verdict d'import a survecu a un changement de sa fermeture : %s" % lances)
    assert vraies[cible] != "CLE-V2"


# --- 7. probe_457 : le graphe d'imports, FIGE et memoise ----------------------------------------

def test_le_graphe_d_imports_457_est_FIGE_et_memoise(monkeypatch, tmp_path):
    """`_import_graph` lit et `ast.parse` tout `scripts/python/**` ; trois tests de
    `test_457_r8_selection_par_diff_offline.py` l'exercent sur l'arbre REEL.

    DEUX proprietes, et la premiere est celle qui evite le piege du cache : la valeur rendue est
    FIGEE (`frozenset`), donc un appelant ne peut pas modifier ce que verra le suivant -- le
    `defaultdict(set)` d'origine, lui, l'aurait laisse faire."""
    import probe_457_offline_tests_green as P457

    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("X = 1\n", encoding="utf-8")
    mods = {"a.py": "a", "b.py": "b"}
    monkeypatch.setattr(P457, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(P457, "_GRAPHE_CACHE", {})

    calculs = []
    reel = P457._calculer_import_graph
    monkeypatch.setattr(P457, "_calculer_import_graph",
                        lambda m, r: (calculs.append(1), reel(m, r))[1])

    inverse, incertains = P457._import_graph(mods)
    assert inverse.get("b.py") == frozenset({"a.py"}), inverse
    assert isinstance(incertains, frozenset)
    assert all(isinstance(v, frozenset) for v in inverse.values()), inverse

    P457._import_graph(mods)
    assert len(calculs) == 1, "le graphe a ete recalcule %d fois pour 2 appels" % len(calculs)

    # ... et une source MODIFIEE le fait recalculer : un graphe perime SOUS-selectionnerait,
    # c'est-a-dire un FAUX VERT.
    (tmp_path / "a.py").write_text("import b\nimport c\n", encoding="utf-8")
    P457._import_graph(mods)
    assert len(calculs) == 2, "un graphe d'imports a survecu a une modification de source"


def test_l_empreinte_de_l_arbre_engine_est_NON_VIDE_et_BOUGE(tmp_path, monkeypatch):
    """Une empreinte vide (ou constante) rendrait la garde ci-dessus tautologique.

    #486-r11 : `empreinte_engine` n'est plus la CLE du cache, c'est le DETECTEUR DE GENERATION --
    il dit « l'arbre a bouge, les fermetures calculees sont peremees » pour ~437 `stat` sous
    0,2 s, la ou re-parser tout l'arbre coute ~3,9 s. Il reste AUSSI la cle grossiere de repli
    des modules opaques. Les deux usages exigent la meme chose de lui : etre non vide et sensible.
    """
    import probe_270r4r2_import_en_premier as IP

    avant = IP.empreinte_engine()
    assert len(avant) >= 300, "empreinte derisoire : %d entree(s)" % len(avant)
    # ... et elle est SENSIBLE : sur une racine jetable, ecrire un fichier la fait changer.
    monkeypatch.setattr(IP, "RACINE", tmp_path)
    (tmp_path / "engine").mkdir()
    e0 = IP.empreinte_engine()
    (tmp_path / "engine" / "m.py").write_text("X = 1\n", encoding="utf-8")
    e1 = IP.empreinte_engine()
    (tmp_path / "engine" / "m.py").write_text("X = 2222\n", encoding="utf-8")
    e2 = IP.empreinte_engine()
    assert e0 != e1, "un fichier AJOUTE ne change pas l'empreinte"
    assert e1 != e2, "un fichier MODIFIE ne change pas l'empreinte"


# --- 8. #941 : les TROIS balayages memoises par la tranche du parc de cliquets ------------------
#
# Meme forme que les etages 3-4 ci-dessus, et pour la meme raison : un memo qui n'est jamais
# consulte ne garde rien, et le gain serait imaginaire. On mesure par SUBSTITUTION du balayage
# (compteur d'appels), jamais par un chronometre -- donc sans balayer le corpus reel.

def test_le_cache_de_invocations_287r13r1_EVITE_le_second_balayage(monkeypatch):
    """`invocations()` visite TOUT `git ls-files` et `ast.unparse` chaque `Call` des fichiers qui
    citent `rl_duel` -- **38 s** mesures le 2026-08-11 -- et les TROIS tests du cliquet
    #287-r13-r1 le refaisaient chacun pour son compte (180,7 s sous charge)."""
    import probe_287r13r1_rayon_refus_roster as P287

    appels = []
    temoin = [("a.py", 1, "rc teste", True)]

    def _faux():
        appels.append(1)
        return list(temoin)

    monkeypatch.setattr(P287, "_balayer_invocations", _faux)
    monkeypatch.setattr(P287, "_INVOCATIONS_CACHE", None)
    a, b = P287.invocations(), P287.invocations()
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a is b and a == tuple(temoin), (a, b)
    assert isinstance(a, tuple), "la valeur memoisee doit etre IMMUABLE"


def test_les_deux_caches_de_287r14r1_EVITENT_leurs_seconds_balayages(monkeypatch):
    """DEUX balayages dans le meme cliquet : `appels_directs` lit et parse tout `.py` versionne,
    `ventiler` refait un `inspect.getsource` par ability du registre."""
    import probe_287r14r1_resolution_tile_target as P14

    nv, na = [], []

    def _faux_vent():
        nv.append(1)
        return ((1011, "TunnelingHorrorAbility", "OUI"),), (), ()

    def _faux_appels():
        na.append(1)
        return (("a.py", 1, "XAbility", "tuile"),), ()

    monkeypatch.setattr(P14, "_balayer_ventilation", _faux_vent)
    monkeypatch.setattr(P14, "_balayer_appels_directs", _faux_appels)
    monkeypatch.setattr(P14, "_VENTILATION_CACHE", None)
    monkeypatch.setattr(P14, "_APPELS_CACHE", None)

    v1, v2 = P14.ventiler(), P14.ventiler()
    d1, d2 = P14.appels_directs(), P14.appels_directs()
    assert len(nv) == 1 and len(na) == 1, (nv, na)
    assert v1 is v2 and d1 is d2
    assert all(isinstance(x, tuple) for x in v1), "la ventilation doit etre IMMUABLE"
    assert all(isinstance(x, tuple) for x in d1), "les appels directs doivent etre IMMUABLES"


def test_le_cache_de_etape1_514_EVITE_le_second_balayage_ET_REJOUE_ses_echecs(monkeypatch,
                                                                             capsys):
    """`etape_1` rend un dict de LISTES -- donc mutable : le memo doit RE-CONSTRUIRE, sinon un
    test mute ce que verra le suivant. Et ses ECHECS s'accumulent dans le `fails` de l'appelant :
    les memoiser sans les rejouer les ferait disparaitre du second appel."""
    import probe_514_allunits_rayon_de_souffle as P514

    appels = []
    fige = ({"AllUnits": (("a.py", "f", 1),), "AllAliveUnits": ()}, ("un echec",))

    def _faux():
        appels.append(1)
        return fige

    monkeypatch.setattr(P514, "_balayer_etape_1", _faux)
    monkeypatch.setattr(P514, "_ETAPE1_CACHE", None)
    f1, f2 = [], []
    a = P514.etape_1(f1)
    b = P514.etape_1(f2)
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a == b == {"AllUnits": [("a.py", "f", 1)], "AllAliveUnits": []}, (a, b)
    assert a["AllUnits"] is not b["AllUnits"], "la liste est PARTAGEE -- une mutation fuirait"
    assert f1 == f2 == ["un echec"], "les echecs ne sont pas rejoues : (%r, %r)" % (f1, f2)

    a["AllUnits"].append("MUTATION-941")
    assert P514.etape_1([])["AllUnits"] == [("a.py", "f", 1)], "une mutation a fuite dans le cache"


# --- 9. #941-r2 : les QUATRE balayages memoises par la seconde tranche du parc ------------------
#
# Meme forme que l'etage 8, meme methode (SUBSTITUTION du balayage, jamais un chronometre). Un
# etage de plus ici, et c'est le seul VRAIMENT neuf : un memo peut aussi figer un VERDICT, et un
# verdict fige est un vert qui ment -- pas un cout qui revient.

def test_le_cache_de_step_on_283_EVITE_le_second_balayage_ET_RE_CONSTRUIT(monkeypatch, capsys):
    """`step_on` etait appele DEUX fois par `test_enum_ordinal_ratchet_offline.py`, avec les
    memes arguments : un test lit `decales` (quotes indecidables), l'autre `fails` (ancres
    perimees). Deux verdicts, un seul balayage -- 34,7 s + 30,5 s mesures le 2026-08-11.

    L'IMPRESSION reste rejouee : elle depend de `verbose`, donc la memoiser ferait taire le
    second appel."""
    import probe_283_enum_ordinal_sweep as SW

    appels = []
    #: 5e position depuis #1031 : les ancres dont l'annotation n'est PAS attribuable (plusieurs
    #: ancres nues pour une seule annotation sur la ligne). Elle entre ICI parce que le contrat
    #: garde par ce test est << CHAQUE releve est re-construit >> -- un releve neuf qui resterait
    #: partage fuirait exactement comme les trois autres, sans que rien ne le dise.
    fige = (7, (("a.py", 1, "0x2b", "X", "Y", "On"),),
            (("b.py", 2, "0x2a", "PreUnitAbility", "FUN"),),
            (("c.py", 3, "0x2b", "PreUnitAbility", 43, 42, "FUN"),),
            (("d.py", 4, "0x34", "PreUnitFled", 2, "On"),))

    monkeypatch.setattr(SW, "_balayer_step_on", lambda racine: (appels.append(racine), fige)[1])
    monkeypatch.setattr(SW, "_ON_CACHE", {})
    a = SW.step_on(verbose=False)
    b = SW.step_on(verbose=False)
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a[0] == b[0] == 7
    for i in (1, 2, 3, 4):
        assert list(a[i]) == list(fige[i]), (i, a[i])
        assert a[i] is not b[i], "les releves sont PARTAGES -- une mutation fuirait (position %d)" % i
    a[3].append(("MUTATION-941r2",))
    assert len(SW.step_on(verbose=False)[3]) == len(fige[3]), "une mutation a fuite dans le cache"
    assert "etape 5" in capsys.readouterr().out, "l'impression ne doit PAS etre memoisee"

    # ... et une RACINE differente n'est PAS servie par le cache de la premiere.
    SW.step_on(verbose=False, racine="frida")
    assert len(appels) == 2, "le cache a servi une AUTRE racine -- le releve serait faux"


def test_le_cache_des_temoins_519_MEMOISE_le_corpus_mais_PAS_le_VERDICT(monkeypatch):
    """L'ETAGE QUI COMPTE, et il n'existait pour aucun des memos precedents.

    `balayer` rend des sites AVEC leur verdict, et ce verdict ne se derive PAS du disque : il
    interroge l'etat du moteur (`ABILITY_CLASSES`, `TARGETING_OPTIONS_UNPORTED`,
    `targeting_options_for`), que la cadence de portage fait bouger et qu'un appelant peut
    substituer. Memoiser le tout aurait fige exactement ce que ce cliquet garde -- un vert qui
    ment, pas un cout qui revient. Le memo s'arrete donc au CORPUS (8,97 s mesurees), et les
    verdicts sont RE-POSES a chaque appel (0,00 s)."""
    import probe_519_temoins_de_camp as T

    appels = []
    site = ("engine/x.py", 12, 1091, "targeting_options_for(1091) is None", False)
    monkeypatch.setattr(T, "_balayer_sites", lambda racine: (appels.append(racine), (site,))[1])
    monkeypatch.setattr(T, "_SITES_CACHE", {})

    monkeypatch.setattr(T, "_camp_courant", lambda aid, texte: False)
    a = T.balayer()
    assert len(appels) == 1 and [s.verdict for s in a] == [T.PERISSABLE], (appels, a)

    # LE CRAN : le corpus n'a pas bouge (aucun second balayage), mais l'etat du moteur, si.
    monkeypatch.setattr(T, "_camp_courant", lambda aid, texte: True)
    b = T.balayer()
    assert len(appels) == 1, "le corpus a ete rebalaye %d fois pour 2 appels" % len(appels)
    assert [s.verdict for s in b] == [T.PERIME], (
        "le verdict a ete MEMOISE avec le corpus : ce cliquet est devenu aveugle a ce qu'il garde")
    assert a[0] is not b[0], "les objets `Site` sont partages -- une mutation fuirait"

    # ... et une RACINE differente n'est PAS servie par le cache de la premiere.
    T.balayer(racine=T._ICI.parent)
    assert len(appels) == 2, "le cache a servi une AUTRE racine"


def test_le_cache_des_ordinaux_519_EVITE_le_second_balayage(monkeypatch):
    """Deux tests l'appellent : l'un pour les citations perimees, l'autre pour attester qu'il
    EXISTE des membres decales (sans quoi le zero du premier ne dirait rien)."""
    import probe_519_ordinaux_decales as O

    appels = []
    fige = ([(Path("x.py"), 3, "Damage", 34, 33)], {"Damage": 34}, {"Damage": 33}, ("v", "n"))
    monkeypatch.setattr(O, "_balayer", lambda: (appels.append(1), fige)[1])
    monkeypatch.setattr(O, "_BALAYAGE_CACHE", None)

    a = O.balayer()
    b = O.balayer()
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)
    assert a[0] == b[0] == fige[0] and a[3] == fige[3]
    assert a[1] is not b[1] and a[2] is not b[2], "les tables sont PARTAGEES -- une mutation fuirait"
    a[1]["Damage"] = 999
    a[0].append("MUTATION-941r2")
    assert O.balayer()[1]["Damage"] == 34, "une mutation a fuite dans le cache"
    assert len(O.balayer()[0]) == len(fige[0]), "une insertion a fuite dans le cache"


def test_les_trois_lectures_de_480r8_EVITENT_leurs_seconds_balayages(monkeypatch):
    """Ce fichier de test lisait le depot DEUX FOIS, de chaque cote d'une frontiere de process
    qu'aucun memo ne traverse. Depuis #941-r2 les deux etages partagent le process ; ces memos
    sont ce qui rend ce partage payant (6,32 + 7,90 + 1,66 s mesurees)."""
    import probe_480r8_rpc_ventilation as P480

    n = {"rpc": 0, "exec": 0, "doc": 0}

    def _c(cle, val):
        def _f():
            n[cle] += 1
            return val
        return _f

    monkeypatch.setattr(P480, "_balayer_rpc", _c("rpc", ({"aRpc": ["frida/hooks/x.ts"]}, 1)))
    monkeypatch.setattr(P480, "_balayer_corpus_executable", _c("exec", {"a.ts": "aRpc"}))
    monkeypatch.setattr(P480, "_balayer_corpus_doc", _c("doc", {"a.md": "aRpc"}))
    monkeypatch.setattr(P480, "_LECTURES_CACHE", {})

    for _ in range(3):
        decl, _n = P480.recenser_rpc()
        ce = P480.corpus_executable()
        cd = P480.corpus_doc()
    assert n == {"rpc": 1, "exec": 1, "doc": 1}, n
    assert decl == {"aRpc": ["frida/hooks/x.ts"]} and ce == {"a.ts": "aRpc"} and cd == {"a.md": "aRpc"}

    # ... et le retour est RE-CONSTRUIT : muter ce qu'on recoit ne touche pas le suivant.
    decl["aRpc"].append("MUTATION-941r2")
    ce["MUTATION-941r2"] = "x"
    assert P480.recenser_rpc()[0] == {"aRpc": ["frida/hooks/x.ts"]}, "une mutation a fuite"
    assert "MUTATION-941r2" not in P480.corpus_executable(), "une mutation a fuite"


def test_confronter_486r15_UTILISE_la_fermeture_injectee_et_en_cree_une_SINON(monkeypatch):
    """INJECTION, pas cache : le defaut reste une fermeture NEUVE, donc aucun appelant existant
    ne change de comportement. C'est l'appelant qui decide de la fraicheur -- et il le faut,
    parce que ce meme fichier de test ECRIT dans des arbres jetables entre deux confrontations.
    """
    import probe_486r15_declencheurs_tests as G486
    import declencheur_cliquet as DC486

    creees = []
    reelle = DC486.Fermeture

    monkeypatch.setattr(G486, "Fermeture",
                        lambda racine: (creees.append(racine), reelle(racine))[1])
    G486.confronter({})
    assert len(creees) == 1, "le defaut ne construit plus sa propre fermeture"

    partagee = reelle(G486.ROOT)
    G486.confronter({}, ferm=partagee)
    G486.confronter({}, ferm=partagee)
    assert len(creees) == 1, "la fermeture injectee a ete ignoree : %d construction(s)" % len(creees)

