"""Chemin ABSOLU d'un script FRERE de `scripts/python/` -- foyer UNIQUE (#464-r1).

LE DEFAUT QUE CE MODULE FERME
-----------------------------
Quinze scripts de `scripts/python/**` invoquaient un frere par son nom NU :

    subprocess.run([sys.executable, "rl_duel.py", "build", ...])

`sys.executable` est absolu, `"rl_duel.py"` ne l'est pas : Python le resout depuis le
CWD. Lance d'ailleurs que `scripts/python`, l'interpreteur rend
`can't open file '<cwd>\\rl_duel.py'` (rc 2). Sur les 15, **8** ne lisent meme pas ce rc
(`subprocess.run(...)` en instruction seule) et enchainent sur la lecture du state-file.

POURQUOI UN ANCRAGE, ET NON LE VERROU `_exiger_cwd` DE #464
-----------------------------------------------------------
`probe_457_offline_tests_green.py` REFUSE de tourner hors de son repertoire, et c'est
justifie LA : les chemins qu'il passe a pytest sont relatifs au ROOTDIR que fixe
`pytest.ini`, contrainte qu'on ne peut pas lever en les absolutisant.

Ici il n'y a AUCUNE contrainte de ce genre : `str(_PYDIR / "rl_duel.py")` fonctionne depuis
n'importe quel repertoire. Refuser CONTRAINDRAIT l'outil (ces probes sont lances a la main,
depuis la racine aussi souvent que depuis `scripts/python`) ; ancrer le REPARE. On prefere
donc rendre le script insensible au CWD plutot que d'exiger un CWD.

⚠ LE PIEGE MESURE : NE PAS "CORRIGER" EN AJOUTANT `cwd=`
---------------------------------------------------------
Le reflexe naturel -- passer `cwd=_PYDIR` au sous-processus -- est ici une REGRESSION.
`rl_duel.py` ancre deja un `--state-file` RELATIF sur la RACINE DU DEPOT, pas sur le CWD
(`STATE = sf if sf.is_absolute() else (ROOT / sf)`), precisement pour que
<< meme chemin nominal = meme fichier, quel que soit le cwd de l'acteur >>. Poser un `cwd=`
different de celui du probe DECOUPLE les deux : `rl_duel` ecrirait le state-file sous
`<depot>/logs/x.json` pendant que le probe le relirait sous `<son cwd>/logs/x.json`.
L'ancrage du seul chemin de SCRIPT laisse les deux cotes partager le meme CWD, donc la meme
resolution -- c'est ce qui rend la correction sure.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

from pathlib import Path

#: Le repertoire de CE module, donc de ses freres. Derive de `__file__` : il ne depend ni du
#: CWD, ni de `sys.path`, ni de la maniere dont l'appelant a ete lance.
_PYDIR = Path(__file__).resolve().parent


def sibling_script(nom: str) -> str:
    """Chemin ABSOLU du script frere `nom`, pour un argv de `subprocess`.

    LEVE `FileNotFoundError` si le frere n'existe pas. C'est voulu, et c'est la seconde
    moitie du correctif : un nom de script errone (renomme, supprime, faute de frappe) se
    manifestait jusqu'ici par un `rc=2` de l'interpreteur enfant que 8 des 15 appelants ne
    lisaient PAS -- l'echec se rejouait alors plus loin, en `FileNotFoundError` sur le
    state-file, qui accuse le mauvais coupable. On echoue ICI, en nommant le frere absent.
    """
    p = _PYDIR / nom
    if not p.is_file():
        raise FileNotFoundError(
            "script frere introuvable : %s (attendu dans %s)" % (nom, _PYDIR))
    return str(p)
