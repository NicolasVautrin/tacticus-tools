"""#486-r5 -- GARDE des balayages AST MEMOISES. Offline pur, aucune session.

CE QUE CE FICHIER TIENT
-----------------------
Trois balayages de tout `scripts/python/**` (2089 fichiers, 37 Mo) etaient re-executes a chaque
test qui en avait besoin. Mesure du 2026-08-06, machine chargee :

    `_substitution_impls()`  (test_additional_hits_variant_signatures_offline)   18 - 26 s x3
    `P380.scan()`            (test_380_seed_bc_patch_survival_offline)           32 - 36 s x2
    lecture + `ast.parse`    (test_ability_registry_ratchet, 2 visites)          18 - 20 s x2

Ventilation du plus gros (`P380.scan`) : `ast.parse` 27,8 s, la visite 10,4 s, la lecture en
SERIE 3,2 s, et `Path(__file__).resolve()` RECALCULE dans la boucle 2,3 s.

La correction est un cache de RESULTAT -- jamais un cache d'AST : mesure du meme jour,
retenir les 2089 arbres de ce corpus coute **1013 Mo** de tas Python. Ce qui est memoise est
donc minuscule (deux tuples de chaines ; 180 records pour `scan`).

CE QU'UN CACHE PEUT CASSER, ET CE QUE CHAQUE ETAGE VERIFIE
---------------------------------------------------------
1. **FIDELITE** -- le cache doit rendre ce que rend le balayage. Un cache qui derive rendrait
   VERT un test qui devrait rougir : le mode de defaillance le plus couteux ici.
2. **PAS DE FUITE D'ETAT** -- l'objet partage doit etre immuable, ou re-clone a chaque appel.
   Un test qui muterait le releve du suivant produirait un vert (ou un rouge) sans rapport avec
   le depot. `scan()` rend des listes de dicts : la garde exige donc des objets DISTINCTS.
3. **LE CACHE MORD** -- un cache qui ne serait jamais consulte ne garderait rien et le gain
   serait imaginaire. On le mesure par SUBSTITUTION du balayage sous-jacent (compteur d'appels),
   pas par un chronometre.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))
if str(PYDIR / "tests" / "engine" / "runner") not in sys.path:
    sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

import probe_380_seed_bc_patch_survival as P380                          # noqa: E402
import test_additional_hits_variant_signatures_offline as T393           # noqa: E402
import test_ability_registry_ratchet as T167                             # noqa: E402


# --- 1. FIDELITE : le cache rend ce que rend le balayage ----------------------------------------

def test_le_cache_des_substitutions_rend_le_MEME_releve_que_le_balayage():
    """Le releve memoise doit etre EGAL au balayage refait a neuf. S'ils divergeaient, le
    cliquet de signature (`test_toute_substitution_suit_la_signature_du_port`) jugerait un
    corpus qui n'est plus celui du depot."""
    frais = tuple(T393._balayer_substitutions())
    assert T393._substitution_impls() == frais
    assert frais, "balayage VIDE -- la garde ne prouverait rien (cf. le port lui-meme y figure)"


def test_le_cache_de_scan380_rend_le_MEME_releve_que_le_balayage():
    frais = P380._balayer(P380.PY_ROOT)
    cache = P380.scan()
    assert [r["path"] for r in cache] == [r["path"] for r in frais]
    assert cache == frais
    assert frais, "balayage VIDE -- la garde ne prouverait rien"


def test_les_deux_releves_de_ciblage_sont_ceux_du_balayage():
    frais = T167._balayer_ciblage()
    assert T167._releves_de_ciblage() == frais
    assert len(frais) == 2 and all(isinstance(x, tuple) for x in frais)


# --- 2. PAS DE FUITE D'ETAT ---------------------------------------------------------------------

def test_les_releves_memoises_sont_IMMUABLES():
    """`tuple` de scalaires : aucun test ne peut modifier ce que verra le suivant."""
    impls = T393._substitution_impls()
    assert isinstance(impls, tuple)
    assert all(isinstance(x, tuple) for x in impls)

    releves = T167._releves_de_ciblage()
    assert isinstance(releves, tuple) and len(releves) == 2
    for seau in releves:
        assert isinstance(seau, tuple)
        assert all(isinstance(x, str) for x in seau)


def test_scan380_rend_des_objets_DISTINCTS_a_chaque_appel():
    """`scan()` rend des listes de DICTS -- donc mutables. La seule facon sure de les memoiser
    est de rendre une copie profonde : muter le retour d'un appel ne doit rien changer au
    suivant. C'est le piege inverse d'une mise en cache, celui qui rend VERT un test qui
    devrait rougir."""
    a = P380.scan()
    b = P380.scan()
    assert a is not b
    assert a == b
    assert a[0] is not b[0], "les records sont partages -- une mutation fuirait d'un test a l'autre"

    a[0]["risky"] = [("MUTATION-486r5", 0, 0, False)]
    a.append({"path": Path("faux.py"), "parse_error": None, "risky": [], "benign": [],
              "disk": [], "consumes": []})
    c = P380.scan()
    assert len(c) == len(b), "une insertion a fuite dans le cache"
    assert c[0]["risky"] == b[0]["risky"], "une mutation a fuite dans le cache"


# --- 3. LE CACHE MORD ---------------------------------------------------------------------------

def test_le_cache_des_substitutions_EVITE_le_second_balayage(monkeypatch):
    """Sans cette garde, le cache pourrait ne jamais etre consulte : les tests resteraient verts
    et le cout reviendrait, sans que rien ne le dise."""
    appels = []
    reel = T393._balayer_substitutions
    monkeypatch.setattr(T393, "_balayer_substitutions",
                        lambda: (appels.append(1), reel())[1])
    monkeypatch.setattr(T393, "_IMPLS_CACHE", None)
    T393._substitution_impls()
    T393._substitution_impls()
    T393._substitution_impls()
    assert appels == [1], "le balayage a ete refait %d fois pour 3 appels" % len(appels)


def test_le_cache_de_scan380_EVITE_le_second_balayage(monkeypatch):
    appels = []
    reel = P380._balayer
    monkeypatch.setattr(P380, "_balayer",
                        lambda root: (appels.append(root), reel(root))[1])
    monkeypatch.setattr(P380, "_SCAN_CACHE", {})
    P380.scan()
    P380.scan()
    assert len(appels) == 1, "le balayage a ete refait %d fois pour 2 appels" % len(appels)


def test_le_cache_des_releves_de_ciblage_EVITE_le_second_balayage(monkeypatch):
    appels = []
    reel = T167._balayer_ciblage
    monkeypatch.setattr(T167, "_balayer_ciblage",
                        lambda: (appels.append(1), reel())[1])
    monkeypatch.setattr(T167, "_RELEVES_CACHE", None)
    T167._releves_de_ciblage()
    T167._releves_de_ciblage()
    assert appels == [1], "le balayage a ete refait %d fois pour 2 appels" % len(appels)
