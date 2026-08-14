"""#914-r1 OFFLINE -- un champ de `BC.Units[]` RECALCULE par `buildNormalizedBC` ne peut pas etre
patche depuis le SEED BC, et le montage doit le DIRE.

LE VICE MESURE (#914) : deux probes jumeaux ecrivaient `Health = 900000` dans le seed BC et
l'annoncaient dans leur propre `print` ; la cible arrivait a ~9539 PV, mourait en cours de serie,
et le dernier montant live devenait un OVERKILL -- ce qui a fait rougir un test de percage en
accusant la magnitude portee. Rien ne signalait l'ecrasement.

Ce fichier garde les DEUX faces :
  1. la LISTE des champs recalculee est DERIVEE du foyer natif (`json-build.ts`) et confrontee a
     la constante Python, dans les deux sens -- une entree qui apparait ou disparait cote TS fait
     ROUGIR ici, elle ne se perime pas en silence ;
  2. le rapport ne parle QUE dans son regime -- patch delibere ET valeur EFFECTIVEMENT ecrasee --
     et se tait sur les cinq positions voisines, dont le CARRIER DE SUMMON (formule heros qui
     leve -> `skipped` -> l'entree traverse INTACTE, donc le patch est legitime et survit).

⚠ Une quatrieme condition (« l'unite est dans `result.normalized` ») a ete RETIREE du code : la
mutation qui la neutralise laissait ce fichier integralement VERT, donc elle etait redondante avec
le test d'ecrasement effectif -- et une branche qu'aucune contre-epreuve ne peut faire mordre est
une branche non gardee, pas une securite.
"""
from __future__ import annotations

#: Perimetre : le foyer natif qui RECALCULE (le TS), le mirror Python de sa liste et le rapport
#: qui s'en sert. Le seed BC de reference entre au perimetre parce que le rapport s'en sert comme
#: TEMOIN de « non patche ».
DECLENCHEUR = {
    "chemins": (
        "frida/hooks/features/normalize-bc/json-build.ts",
        "scripts/python/rl_collect_batch.py",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : DERIVE du TS la liste des champs que buildNormalizedBC recalcule et la "
              "confronte a CHAMPS_RECALCULES_PAR_NORMALISATION (#914-r1), puis garde que le "
              "rapport d'ecrasement ne parle que dans son regime -- en particulier son SILENCE "
              "sur une unite `skipped` (carrier de summon), dont le patch de PV est legitime.",
}

import json          # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import re            # noqa: E402
import sys           # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest        # noqa: E402

_SP = Path(__file__).resolve().parents[2]
if str(_SP) not in sys.path:
    sys.path.insert(0, str(_SP))

import rl_collect_batch as R                                                  # noqa: E402

_TS = _SP.parents[1] / "frida" / "hooks" / "features" / "normalize-bc" / "json-build.ts"


def _champs_ecrits_par_le_ts() -> set:
    """Toutes les ecritures `u.<champ> = ...` du foyer natif, commentaires RETIRES.

    Retirer les commentaires n'est pas cosmetique : le fichier en contient qui citent des
    ecritures (`u.RemainingHealth = u.Health`) et les compter ferait passer pour mesure ce qui
    n'est que de la prose.
    """
    src = _TS.read_text(encoding="utf-8")
    sans = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    sans = re.sub(r"^\s*//.*$", "", sans, flags=re.M)
    return set(re.findall(r"\bu\.([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)", sans))


# ------------------------------------------------- 1. la LISTE, derivee du TS et non recopiee
def test_le_ts_est_lisible_et_non_degenere():
    """Le fichier natif existe et porte des ecritures -- sinon les etages suivants sont vacants."""
    assert _TS.exists(), f"foyer natif introuvable : {_TS}"
    champs = _champs_ecrits_par_le_ts()
    assert len(champs) >= 10, (
        f"seulement {len(champs)} ecriture(s) `u.<champ> =` derivee(s) du TS -- l'extraction "
        f"ne mesure plus ce qu'elle croit ({sorted(champs)})")


def test_la_constante_python_est_en_bijection_avec_le_ts():
    ts = _champs_ecrits_par_le_ts()
    py = set(R.CHAMPS_RECALCULES_PAR_NORMALISATION)
    assert py - ts == set(), (
        f"champs declares recalcules cote Python mais que le TS n'ecrit PAS : {sorted(py - ts)} "
        f"-- un faux positif fait renoncer a un patch pourtant valide")
    assert ts - py == set(), (
        f"champs ECRITS par buildNormalizedBC et absents du mirror Python : {sorted(ts - py)} "
        f"-- c'est exactement le trou de #914 : un patch de seed BC ecrase EN SILENCE")


def test_pas_de_doublon_dans_la_constante():
    py = R.CHAMPS_RECALCULES_PAR_NORMALISATION
    assert len(py) == len(set(py)), f"doublon dans la constante : {py}"


# ------------------------------------------- 2. le RAPPORT : il parle dans son regime, et seulement
def _ref(monkeypatch, units: list) -> None:
    """Substitue la reference `data/seed-bc.json` (le TEMOIN de « non patche »)."""
    monkeypatch.setattr(R, "_REF_CACHE", {"bc": {"Units": units}})


def test_le_patch_ecrase_est_signale(monkeypatch):
    _ref(monkeypatch, [{"Id": "u1", "Health": 5000, "RemainingHealth": 5000}])
    base = {"Units": [{"Id": "u1", "Health": 900000, "RemainingHealth": 900000}]}
    apres = {"Units": [{"Id": "u1", "Health": 9539, "RemainingHealth": 9539}]}
    lignes = R._rapport_champs_ecrases(base, apres)
    assert len(lignes) == 1, lignes
    assert "900000" in lignes[0] and "9539" in lignes[0]
    assert "--unit-stat u1:" in lignes[0], "le message ne nomme pas le levier qui MORD"


def test_silence_quand_l_entree_traverse_intacte_carrier_de_summon(monkeypatch):
    """Le faux positif que la fiche nomme explicitement -- et par quoi il est REELLEMENT evite.

    Un CARRIER DE SUMMON fait LEVER la formule heros : `json-build.ts` saute au `catch` AVANT
    toute ecriture `u.<champ> = ...`, donc son entree sort IDENTIQUE et son patch de PV survit.
    Le silence vient donc du test d'ECRASEMENT EFFECTIF, pas d'une condition sur `normalized` --
    laquelle a ete retiree du code apres qu'une mutation l'a montree redondante (le fichier
    restait integralement vert sans elle). C'est ce test-ci qui porte l'invariant.
    """
    _ref(monkeypatch, [{"Id": "carrier", "Health": 100}])
    base = {"Units": [{"Id": "carrier", "Health": 900000}]}
    apres = {"Units": [{"Id": "carrier", "Health": 900000}]}
    assert R._rapport_champs_ecrases(base, apres) == []


def test_silence_sans_patch(monkeypatch):
    """Le chemin PAR DEFAUT (seed BC = reference) : recalcul ordinaire, zero ligne.

    C'est la condition de non-bruit : sans elle, les 175 entrees du seed parleraient a chaque
    build et le signal serait noye.
    """
    _ref(monkeypatch, [{"Id": "u1", "Health": 5000}])
    base = {"Units": [{"Id": "u1", "Health": 5000}]}
    apres = {"Units": [{"Id": "u1", "Health": 9539}]}
    assert R._rapport_champs_ecrases(base, apres) == []


def test_silence_sur_une_unite_injectee_au_catalogue(monkeypatch):
    """Une unite ABSENTE de la reference (`catalog_inject.augment`) : on ne sait rien de ce
    qu'elle « aurait du » valoir, donc on se tait au lieu d'inventer."""
    _ref(monkeypatch, [{"Id": "u1", "Health": 5000}])
    base = {"Units": [{"Id": "injectee", "Health": 900000}]}
    apres = {"Units": [{"Id": "injectee", "Health": 9539}]}
    assert R._rapport_champs_ecrases(base, apres) == []


def test_silence_sur_un_champ_NON_recalcule(monkeypatch):
    """Un champ hors liste n'est PAS compare, meme quand sa valeur change entre les deux BC.

    Le regime existe : `explicitStats` ecrit `u[k]` pour des cles ARBITRAIRES (`json-build.ts`),
    donc un champ hors liste peut tres bien differer. Le faire changer est ce qui rend ce test
    discriminant -- avec `Shield` identique des deux cotes, il passait meme quand on remplacait le
    filtre par `list(u.keys())`, c.-a-d. qu'il ne mesurait pas le filtre.
    """
    assert "Shield" not in R.CHAMPS_RECALCULES_PAR_NORMALISATION
    _ref(monkeypatch, [{"Id": "u1", "Shield": 0}])
    base = {"Units": [{"Id": "u1", "Shield": 999}]}
    apres = {"Units": [{"Id": "u1", "Shield": 42}]}
    assert R._rapport_champs_ecrases(base, apres) == [], (
        "un champ HORS de la liste des recalcules a ete signale -- le filtre ne mord pas")


def test_silence_si_le_patch_a_SURVECU(monkeypatch):
    """Un champ recalcule dont la valeur patchee ressort IDENTIQUE n'a pas ete ecrase.

    Le critere est l'ECRASEMENT effectif, pas l'appartenance a la liste : signaler sur la seule
    liste ferait crier sur un montage qui a mordu.
    """
    _ref(monkeypatch, [{"Id": "u1", "Rank": 6}])
    base = {"Units": [{"Id": "u1", "Rank": 17}]}
    apres = {"Units": [{"Id": "u1", "Rank": 17}]}
    assert R._rapport_champs_ecrases(base, apres) == []


def test_reference_illisible_ne_fabrique_aucun_verdict(monkeypatch):
    """Reference absente -> AUCUNE ligne. On ne rend jamais un verdict sur une mesure manquante."""
    monkeypatch.setattr(R, "_REF_CACHE", {"bc": {}})
    base = {"Units": [{"Id": "u1", "Health": 900000}]}
    apres = {"Units": [{"Id": "u1", "Health": 9539}]}
    assert R._rapport_champs_ecrases(base, apres) == []


# --------------------------------------------- 3. la reference REELLE porte bien les champs vises
def test_la_reference_reelle_porte_les_champs_de_la_constante():
    """Sur `data/seed-bc.json`, chaque champ de la constante existe sur au moins une entree.

    Sans ce cran, une faute de frappe dans la constante (`Helth`) serait un NO-OP silencieux :
    le rapport ne comparerait jamais ce champ et se tairait a jamais.
    """
    bc = json.loads((_SP.parents[1] / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    assert units, "seed BC de reference vide"
    presents = set()
    for u in units:
        presents |= set(u.keys())
    manquants = [c for c in R.CHAMPS_RECALCULES_PAR_NORMALISATION if c not in presents]
    assert manquants == [], (
        f"champs de la constante absents de TOUTE entree du seed BC : {manquants} -- le rapport "
        f"ne les comparera jamais (faute de frappe, ou champ disparu du schema)")
