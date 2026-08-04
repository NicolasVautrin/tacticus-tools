"""#469 -- `ratchets-bg.ps1` tourne en priorite BASSE, et l'heritage marche VRAIMENT.

CE QUE CE TEST GARDE, ET POURQUOI IL EN FAUT DEUX ETAGES
--------------------------------------------------------
La parade de #469 tient en une ligne de `ratchets-bg.ps1` : abaisser la classe de priorite Win32
du process courant AVANT tout lancement, pour que le `pwsh` de `ratchets.ps1` et les 44 python
qu'il lance en HERITENT. Mesure du 2026-08-04 : surcout par agent 1 499 -> 891 s (-41 %).

Sa disparition ne produirait AUCUN rouge. La banque resterait juste, les verdicts identiques ;
seul le cout invisible -- la duree des agents -- remonterait. C'est le profil exact des gisements
de ce depot : une degradation qui ne casse rien.

D'ou DEUX etages, parce que le premier seul serait creux :

  1. STATIQUE -- la ligne existe ET elle est posee AVANT le premier lancement de process. La
     position est load-bearing : une classe de priorite est heritee A LA CREATION, donc la poser
     apres coup ne toucherait aucun enfant deja parti. Un grep qui se contente de la PRESENCE
     validerait cette version cassee.
  2. COMPORTEMENTAL -- l'heritage fonctionne sur CETTE machine. C'est une propriete de l'OS, pas
     du depot : un test qui ne verifie que le texte prouve qu'on a ecrit l'intention, jamais
     qu'elle produit l'effet. On lance donc un process fils reel et on LIT sa priorite.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
BG = RACINE / "scripts" / "ratchets-bg.ps1"

_POSE = re.compile(r"PriorityClass\s*=\s*\r?\n?\s*\[System\.Diagnostics\.ProcessPriorityClass\]::BelowNormal")
# Ce qui, dans ce script, CREE un process. `Note` et `Write-Host` n'en creent pas ; `git`, `pwsh`
# et `Remove-Item` si. On cherche le PREMIER, pour comparer sa position a celle de la pose.
_LANCE = re.compile(r"^\s*(?:\$\w+\s*=\s*)?(?:@?\(\s*)?(?:git|&\s*pwsh|Remove-Item|Copy-Item)\b",
                    re.MULTILINE)


def _source() -> str:
    assert BG.is_file(), "ratchets-bg.ps1 introuvable : %s" % BG
    return BG.read_text(encoding="utf-8", errors="replace")


def verdicts(src: str) -> dict:
    """Les TROIS predicats, en fonctions PURES d'une source.

    Cette forme est ce qui rend la contre-epreuve jouable : on peut soumettre des sources MUTEES
    sans jamais toucher au vrai `ratchets-bg.ps1` -- que la banque d'un autre agent est peut-etre
    en train de lire a la seconde meme. Un garde qui exigerait de muter le fichier reel pour se
    prouver serait un garde qu'on ne prouve jamais.
    """
    m_pose = _POSE.search(src)
    i_pwsh = src.find("& pwsh")
    return {
        "pose": bool(m_pose),
        "avant_lancement": bool(m_pose) and i_pwsh > 0 and m_pose.start() < i_pwsh,
        "echappatoire": "PrioriteNormale" in src,
    }


def test_priorite_basse_est_posee():
    src = _source()
    assert _POSE.search(src), (
        "ratchets-bg.ps1 n'abaisse plus sa classe de priorite. La banque de fond reprendrait "
        "le CPU des agents : surcout par agent mesure 891 -> 1499 s (#469). Aucun cliquet ne "
        "rougirait -- la degradation est purement de cout.")


def test_priorite_posee_AVANT_le_premier_lancement():
    """La POSITION, pas la presence : une priorite est heritee A LA CREATION du process."""
    src = _source()
    m_pose = _POSE.search(src)
    assert m_pose, "pose de priorite absente (cf. test_priorite_basse_est_posee)"
    # On ignore les lancements qui precedent dans les COMMENTAIRES et le bloc d'aide : on part du
    # premier `git` executable, qui est la resolution de la racine du depot.
    corps = src
    m_lance = _LANCE.search(corps)
    assert m_lance, "aucun lancement de process trouve -- le motif de detection a derive"
    # NB : le tout premier `git` (rev-parse de la racine) precede volontairement la pose, il est
    # instantane et ne lance rien d'autre. Ce qui compte est que la pose precede le `& pwsh`.
    i_pwsh = corps.find("& pwsh")
    assert i_pwsh > 0, "le lancement `& pwsh` de ratchets.ps1 est introuvable"
    assert m_pose.start() < i_pwsh, (
        "la priorite est posee APRES le lancement de ratchets.ps1 : les cliquets n'en heriteraient "
        "pas. Une classe de priorite est heritee A LA CREATION du process.")


def test_echappatoire_de_diagnostic_existe():
    src = _source()
    assert "PrioriteNormale" in src, (
        "l'echappatoire de diagnostic a disparu : on ne pourrait plus reproduire l'ancien "
        "comportement pour re-mesurer la parade.")


def test_les_trois_predicats_rougissent_sur_leur_mutation():
    """CONTRE-EPREUVE : sur une contre-epreuve, le VERT est le resultat suspect.

    Chaque predicat doit basculer sur SA mutation, et sur elle seule -- sinon on ne saurait pas si
    le garde repond a la faute qu'il pretend voir ou a n'importe quel changement.
    """
    src = _source()
    assert all(verdicts(src).values()), "le fichier reel doit satisfaire les trois predicats"

    # (a) la pose retiree
    sans_pose = _POSE.sub("PriorityClass = [System.Diagnostics.ProcessPriorityClass]::Normal", src)
    v = verdicts(sans_pose)
    assert v["pose"] is False and v["avant_lancement"] is False
    assert v["echappatoire"] is True, "cette mutation ne doit pas emporter les autres predicats"

    # (b) la pose DEPLACEE apres le lancement -- presente, donc invisible a un grep de presence
    m = _POSE.search(src)
    bloc = src[m.start():m.end()]
    deplacee = src[:m.start()] + src[m.end():]
    i = deplacee.find("& pwsh")
    deplacee = deplacee[:i + 40] + "\n" + bloc + "\n" + deplacee[i + 40:]
    v = verdicts(deplacee)
    assert v["pose"] is True, "la mutation (b) laisse la ligne PRESENTE -- c'est tout son interet"
    assert v["avant_lancement"] is False, (
        "une pose de priorite APRES le lancement n'est pas heritee, et le garde doit le voir")

    # (c) l'echappatoire retiree
    v = verdicts(src.replace("PrioriteNormale", "AutreChose"))
    assert v["echappatoire"] is False
    assert v["pose"] is True and v["avant_lancement"] is True


@pytest.mark.skipif(os.name != "nt", reason="classes de priorite Win32")
def test_l_heritage_de_priorite_fonctionne_vraiment():
    """Un fils lance par un process BELOW_NORMAL doit etre BELOW_NORMAL.

    C'est une propriete de l'OS, donc elle se MESURE : verifier le texte de `ratchets-bg.ps1`
    prouverait qu'on a ecrit l'intention, jamais qu'elle produit l'effet.
    """
    BELOW_NORMAL = 0x00004000
    # `restype = c_void_p` est LOAD-BEARING : sans lui ctypes traite le pseudo-handle rendu par
    # GetCurrentProcess() comme un int 32 bits, le tronque, et GetPriorityClass rend 0 -- un
    # ECHEC DE L'INSTRUMENT qui se lirait comme << la parade est inoperante sur cette machine >>.
    lecture = ("import ctypes\n"
               "k=ctypes.WinDLL('kernel32')\n"
               "k.GetCurrentProcess.restype=ctypes.c_void_p\n"
               "k.GetPriorityClass.argtypes=[ctypes.c_void_p]\n"
               "v=k.GetPriorityClass(k.GetCurrentProcess())\n"
               "assert v != 0, 'GetPriorityClass a echoue'\n"
               "print(v)\n")
    # Un pere a priorite basse -> son fils python doit rendre la meme classe.
    pere = subprocess.run([sys.executable, "-c", lecture], capture_output=True, text=True,
                          creationflags=BELOW_NORMAL)
    assert pere.returncode == 0, "lecture de la classe de priorite impossible : %s" % pere.stderr
    assert int(pere.stdout.strip()) == BELOW_NORMAL, (
        "un process cree avec BELOW_NORMAL_PRIORITY_CLASS ne rend pas cette classe : "
        "la parade #469 serait inoperante sur cette machine (lu : %s)" % pere.stdout.strip())

    # Et le PETIT-fils aussi : c'est bien ce dont depend la parade (bg -> pwsh -> python).
    en_cascade = ("import subprocess,sys\n"
                  "r=subprocess.run([sys.executable,'-c',%r],capture_output=True,text=True)\n"
                  "print(r.stdout.strip())\n" % lecture)
    petit = subprocess.run([sys.executable, "-c", en_cascade], capture_output=True, text=True,
                           creationflags=BELOW_NORMAL)
    assert petit.returncode == 0, petit.stderr
    assert int(petit.stdout.strip()) == BELOW_NORMAL, (
        "la classe de priorite ne se transmet pas au PETIT-fils : la chaine reelle est "
        "ratchets-bg -> pwsh -> python, donc la parade ne porterait pas sur les cliquets "
        "(lu : %s)" % petit.stdout.strip())
