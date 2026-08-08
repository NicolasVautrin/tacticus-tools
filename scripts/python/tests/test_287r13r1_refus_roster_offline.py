#!/usr/bin/env python3
"""#287-r13-r1 -- garde du REFUS DUR sur le deficit de roster, et de ce qui borne son rayon.

Le comportement lui-meme (rc 3 par defaut, rc 0 sous `TACTICUS_ALLOW_ROSTER_DEFICIT=1`) est
confronte LIVE par `probe_287r13r1_rayon_refus_roster.py --live` etage 3, sur le montage a
deficit de #287-r13 (`C1_02`/4242, quatre `necroWarden` pour trois `--a-place`).

Ce fichier garde ce qu'un montage live ne peut pas montrer : les DEUX proprietes STRUCTURELLES
dont depend le rayon mesure a 16 sites sur 245.

  1. le `return 3` arrive APRES `_save_state` -- sinon le runner deviendrait ORPHELIN (il
     mangerait le cap partage sans proprietaire) et surtout tout appelant, meme celui qui
     ignore le `rc`, verrait son montage disparaitre : le rayon passerait de 16 a 245 ;
  2. l'echappatoire existe, elle est lue dans l'ENVIRONNEMENT, et son nom est ECRIT dans le
     message d'erreur -- une echappatoire qu'il faut deviner n'en est pas une.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_287r13r1_rayon_refus_roster as P  # noqa: E402

#: ⚠ << rien d'autre ne peut le faire changer d'avis >> ETAIT FAUX -- et c'est le refus dur
#: lui-meme qui le rend faux (corrige apres #845, meme faute que ses deux voisins de tranche).
#:
#: Le dernier test garde `len(risque) * 3 < len(montent)` : si le RAYON franchit le tiers des
#: appelants, il rougit et le refus par defaut doit etre re-arbitre. Or ce rayon se mesure en
#: visitant TOUT `.py` versionne qui cite `rl_duel` -- **259** invocations, dont 245 qui montent
#: une bataille. Un probe NEUF qui teste `.returncode` apres un `rl_duel build` deplace donc le
#: verdict, sans toucher ni a `rl_duel.py` ni a la sonde. Les nommer serait re-saisir
#: l'inventaire que l'etage 1 existe pour DERIVER, et le figer ferait exactement le
#: sous-comptage sur l'absence duquel le refus dur repose.
#:
#: `toujours: True`, donc -- et le bypass `hors_confrontation` devient inutile : retire.
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": False,
    "toujours": True,
    "raison": "Le RAYON qui autorise le refus dur se derive de TOUT `.py` versionne citant "
              "`rl_duel` (259 invocations, 245 qui montent), et un test garde qu'il reste sous "
              "le tiers. Un probe NEUF qui inspecte le `rc` d'un `build` change ce verdict sans "
              "toucher au foyer.",
}

ENV = "TACTICUS_ALLOW_ROSTER_DEFICIT"
RL_DUEL = PYDIR / "rl_duel.py"


@pytest.fixture(scope="module")
def source():
    return RL_DUEL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cmd_build(source):
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.FunctionDef) and n.name == "cmd_build":
            return n
    pytest.fail("`cmd_build` introuvable dans rl_duel.py")


# ================================ 1. le refus est DUR, et il participe bien au `return 3`
def test_le_deficit_de_roster_participe_au_return_3(cmd_build):
    """Le coeur du residu : `roster_problems` doit CONDITIONNER un `rc` non nul.

    Avant #287-r13-r1 il n'apparaissait que dans des `print` : le montage etait faux et le
    `rc` disait 0. On lit le `return 3`, pas la doc qui le raconte.
    """
    vus = []
    for n in ast.walk(cmd_build):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) \
                and n.value.value == 3:
            vus.append(n)
    assert vus, "aucun `return 3` dans `cmd_build`"
    # au moins un `return 3` dont la condition englobante mentionne `roster_problems`
    ok = False
    for n in ast.walk(cmd_build):
        if not isinstance(n, ast.If):
            continue
        cond = ast.unparse(n.test)
        if "roster_problems" not in cond:
            continue
        for m in ast.walk(n):
            if isinstance(m, ast.Return) and isinstance(m.value, ast.Constant) \
                    and m.value.value == 3:
                ok = True
    assert ok, "`roster_problems` ne conditionne AUCUN `return 3` -- le refus est reste mou"


def test_le_refus_arrive_APRES_save_state(source, cmd_build):
    """LA propriete qui borne le rayon a 16 sites, et non a 245.

    Le state-file ecrit, le runner reste utilisable : un appelant qui n'inspecte pas le `rc`
    poursuit exactement comme avant. Sortir AVANT `_save_state` laisserait en plus un runner
    ORPHELIN -- il mangerait le cap partage sans proprietaire (raison deja ecrite au site pour
    les placements).
    """
    ligne_save = None
    for n in ast.walk(cmd_build):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_save_state":
            ligne_save = n.lineno
    assert ligne_save is not None, "`_save_state` introuvable dans `cmd_build`"
    retours3 = [n.lineno for n in ast.walk(cmd_build)
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                and n.value.value == 3]
    assert retours3, "aucun `return 3`"
    assert min(retours3) > ligne_save, (
        "un `return 3` precede `_save_state` (ligne %d) : le runner serait ORPHELIN et le "
        "rayon du refus passerait de 16 a 245 appelants" % ligne_save)


# ============================================ 2. l'ECHAPPATOIRE existe, et elle est NOMMEE
def test_l_echappatoire_est_lue_dans_l_environnement(source):
    """Par ENV et non par drapeau : un appelant bloque est un probe DEJA ECRIT, souvent celui
    d'un autre agent. Lui demander d'editer son fichier pour se debloquer lui ferait payer
    notre cliquet. Meme forme que `TACTICUS_ALLOW_GREEN_SKIP` (#455)."""
    assert "os.environ" in source and ENV in source, \
        "l'echappatoire %s n'est pas lue dans l'environnement" % ENV
    assert "import os" in source


def test_le_message_d_erreur_NOMME_l_echappatoire(source):
    """Une echappatoire qu'il faut deviner n'en est pas une : le message doit la citer.

    C'est ce qui distingue un refus utilisable d'un mur.
    """
    # le nom doit apparaitre dans une chaine imprimee sur stderr, pas seulement en commentaire
    arbre = ast.parse(source)
    dans_un_print = False
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print":
            for a in ast.walk(n):
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and ENV in a.value:
                    dans_un_print = True
    assert dans_un_print, "%s n'est cite dans aucun `print` -- l'echappatoire est invisible" % ENV


def test_les_trois_diagnostics_sont_imprimes_avant_tout_retour(cmd_build):
    """Un montage peut echouer sur PLUSIEURS axes ; sortir au premier cache les suivants.

    Avant cette tranche, `placement_problems` rendait 3 sans jamais laisser parler
    `modifier_problems` -- l'appelant relancait pour decouvrir le second.
    """
    lignes_if = {}
    for n in ast.walk(cmd_build):
        if isinstance(n, ast.If):
            cond = ast.unparse(n.test)
            for cle in ("roster_problems", "placement_problems", "modifier_problems"):
                if cond.strip() == cle:
                    lignes_if[cle] = n.lineno
    assert set(lignes_if) == {"roster_problems", "placement_problems", "modifier_problems"}, \
        "les trois blocs de diagnostic ne sont pas tous presents : %r" % sorted(lignes_if)
    retours3 = [n.lineno for n in ast.walk(cmd_build)
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                and n.value.value == 3]
    assert min(retours3) > max(lignes_if.values()), \
        "un `return 3` coupe avant le dernier bloc de diagnostic"


# ============================================ 3. le RECENSEUR de rayon reste fidele
def test_le_recenseur_separe_list_pool_de_ce_qui_MONTE():
    """`--list-pool` n'atteint jamais `_verify_roster` : le compter gonflerait le rayon
    d'appelants structurellement hors de portee."""
    inv = P.invocations()
    assert inv, "le recenseur ne trouve AUCUNE invocation de `rl_duel build`"
    montent = [i for i in inv if i[3]]
    pool = [i for i in inv if not i[3]]
    assert pool, "aucun `--list-pool` releve : le discriminant a cesse de mordre"
    assert len(montent) > 100, "trop peu d'invocations qui montent (%d)" % len(montent)


def test_le_recenseur_classe_les_quatre_gardes():
    """La partition doit etre TOTALE : une invocation sans classe serait une invocation muette,
    exactement le vice de perimetre que #458 a corrige ailleurs."""
    inv = P.invocations()
    classes = {g for _r, _l, g, _m in inv}
    assert classes <= {"check=True", "rc teste", "rc IGNORE", "resultat non lie"}
    assert "rc teste" in classes and "rc IGNORE" in classes, \
        "le recenseur ne distingue plus qui LIT le rc : %r" % sorted(classes)


def test_le_rayon_reste_petit_devant_le_total():
    """Le fait qui a autorise le refus dur. Ce n'est pas un seuil arbitraire : si le rayon
    devenait majoritaire, le refus par defaut ne serait plus defendable et il faudrait le
    repasser derriere l'echappatoire."""
    inv = P.invocations()
    montent = [i for i in inv if i[3]]
    risque = [i for i in montent if i[2] in ("check=True", "rc teste")]
    assert risque, "rayon NUL : le recenseur ne voit plus personne lire le rc"
    assert len(risque) * 3 < len(montent), (
        "le rayon a franchi le tiers des appelants (%d / %d) -- re-arbitrer le refus par defaut"
        % (len(risque), len(montent)))
