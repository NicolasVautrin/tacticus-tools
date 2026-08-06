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

def test_essayer_tous_ne_relance_PAS_un_interpreteur_deja_lance(monkeypatch):
    """`_essayer` lance UN interpreteur par module -- 0,54 s piece, 131,6 s pour les 437 modules
    d'`engine/` a 8 workers. Deux fichiers de test balaient dans la MEME passe, et leurs
    perimetres se recouvrent a 201 modules : 44,1 s payes deux fois."""
    import probe_270r4r2_import_en_premier as IP

    lances = []
    monkeypatch.setattr(IP, "_essayer", lambda m: (lances.append(m), (m, 0, ""))[1])
    monkeypatch.setattr(IP, "_ESSAIS", {})
    monkeypatch.setattr(IP, "empreinte_engine", lambda: ("EMPREINTE-TEMOIN",))

    a = IP.essayer_tous(["engine.x", "engine.y"])
    b = IP.essayer_tous(["engine.y", "engine.z"])
    assert lances == ["engine.x", "engine.y", "engine.z"], lances
    assert a == [("engine.x", 0, ""), ("engine.y", 0, "")], a
    assert b == [("engine.y", 0, ""), ("engine.z", 0, "")], b


def test_essayer_tous_RE_ESSAIE_quand_l_arbre_a_CHANGE(monkeypatch):
    """LE piege inverse du cache : un verdict perime, et perime dans le sens VERT. La cle porte
    l'empreinte de l'arbre `engine/`, donc une source modifiee la fait tomber d'elle-meme."""
    import probe_270r4r2_import_en_premier as IP

    lances = []
    etat = {"emp": ("V1",)}
    monkeypatch.setattr(IP, "_essayer", lambda m: (lances.append(m), (m, 0, ""))[1])
    monkeypatch.setattr(IP, "_ESSAIS", {})
    monkeypatch.setattr(IP, "empreinte_engine", lambda: etat["emp"])

    IP.essayer_tous(["engine.x"])
    IP.essayer_tous(["engine.x"])
    assert lances == ["engine.x"], "le cache ne mord pas : %s" % lances
    etat["emp"] = ("V2",)                                  # une source a change
    IP.essayer_tous(["engine.x"])
    assert lances == ["engine.x", "engine.x"], (
        "un verdict d'import a survecu a une modification de l'arbre : %s" % lances)


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
    """Une empreinte vide (ou constante) rendrait la garde ci-dessus tautologique."""
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
