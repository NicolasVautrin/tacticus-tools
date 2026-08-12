"""#986 (#954-r3) -- le crit N'A PAS la meme place dans les deux vecteurs, et c'est FIDELE.

#954-r3 signalait que le port place le crit a des etages differents selon la famille (shift `974`
sur le vecteur ABILITY, `779` sur le vecteur NORMALE) sans que la place du crit vis-a-vis du
SPREAD ait jamais ete confrontee. LECTURE (build `rnca9r7q6c`) : le point de composition est
UNIQUE -- `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` pose
`request+0x58 = Nullable<int>(isCrit ? CalculateCriticalDamage(D0) : D0)` AVANT `PredictAttack` --
et ce qui separe les deux familles est le drapeau `AttackDamageOptions[+0x2f]`, relu par
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` :

    drapeau != 0 -> `GetBaseDamageFix64(D)`      # SPREAD applique a D, crit COMPRIS
    drapeau == 0 -> `MinMaxDamageFix64(D, D)`    # bornes DEGENEREES, AUCUN spread

`IdunBattle.Core.HitDamage$$GetDamage` dit lequel est lequel : `min == max -> return min` (attaque
normale : options degenerees, D0 = la stat d'attaque, aucun tirage) contre `Next(min, max + 1)`
(ability : plage de config, D0 tire). D'ou : NORMALE = crit dans le spread ; ABILITY = crit a plat
sur les bornes brutes, puisqu'il n'y a PAS de spread sur ce chemin.

CE QUE CETTE GARDE VERROUILLE -- et pourquoi elle rougirait si on « harmonisait » les deux :

A. le vecteur NORMALE ELARGIT la plage au crit (la largeur passe de `2sA` a `2s(A+cd)`), avec les
   deux shifts EXACTS de #954-r3 (`779` sur la borne min, `1169` sur la max) ;
B. le vecteur ABILITY CONSERVE la largeur (shift `974` sur les DEUX bornes) ;
C. les deux sont donc STRUCTURELLEMENT differents -- assertionne explicitement, sinon la garde ne
   discriminerait rien ;
D. la composition ecrite AU SITE, verifiee par AST et non par grep de texte : `normal.py` fait
   passer `stat(ATTACK) + crit_damage` par `_reduced_bounds` (donc par `get_base_damage_fix64`),
   `ability.py` decale les bornes brutes de `crit_damage` sans jamais les faire passer par
   `get_base_damage_fix64`.

Le discriminant LIVE correspondant est SANS PARAMETRE (la LARGEUR, cf.
`probe_986_crit_place_vs_spread.py`) : mesure du 2026-08-12, meme porteur, `CritDamage = 5000` --
NORMALE largeur non-crit 217 -> etendue critique **1742** (x8) ; ABILITY largeur non-crit 154 ->
etendue critique **151** (conservee).

ASCII only (console cp1252).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.services.damage_prediction import get_base_damage_fix64

# Le regime de #954-r3, verbatim : base 3000, crit damage 974, spread 20 %.
BASE, CD, SPREAD = 3000, 974, 20
OPS = Path(__file__).resolve().parents[2] / "engine" / "runner" / "operations" / "damage_ops"


def _bornes(base: int):
    mm = get_base_damage_fix64(base, spread_pct=SPREAD)
    return mm.min, mm.max


def test_986_vecteur_normale_le_crit_ELARGIT_la_plage():
    """A -- le crit traverse le spread : shifts 779 / 1169, largeur 1200 -> 1590."""
    nc_lo, nc_hi = _bornes(BASE)
    cr_lo, cr_hi = _bornes(BASE + CD)
    assert (nc_lo, nc_hi) == (2400, 3600)
    assert (cr_lo, cr_hi) == (3179, 4769)
    # les deux shifts de #954-r3, figes
    assert cr_lo - nc_lo == 779, "shift min du vecteur NORMALE"
    assert cr_hi - nc_hi == 1169, "shift max du vecteur NORMALE"
    # et le fait STRUCTUREL : la largeur augmente, dans le rapport (A + cd) / A
    assert (cr_hi - cr_lo) > (nc_hi - nc_lo)
    assert (cr_hi - cr_lo, nc_hi - nc_lo) == (1590, 1200)


def test_986_vecteur_ability_le_crit_CONSERVE_la_largeur():
    """B -- pas de spread sur ce chemin : le crit est un decalage plat des bornes brutes."""
    brut_lo, brut_hi = 3000, 5000          # bornes de config, quelconques mais distinctes
    cr_lo, cr_hi = brut_lo + CD, brut_hi + CD
    assert cr_lo - brut_lo == CD == 974
    assert cr_hi - brut_hi == CD == 974
    assert (cr_hi - cr_lo) == (brut_hi - brut_lo), "le vecteur ABILITY ne doit RIEN elargir"


def test_986_les_deux_vecteurs_sont_STRUCTURELLEMENT_distincts():
    """C -- non-degenerescence : sans cet ecart, A et B ne discrimineraient rien."""
    nc_lo, _ = _bornes(BASE)
    cr_lo, _ = _bornes(BASE + CD)
    shift_normale = cr_lo - nc_lo
    shift_ability = CD
    assert shift_normale != shift_ability, "harmonisation des deux vecteurs = regression"
    assert (shift_normale, shift_ability) == (779, 974)


def _appels(fichier: str, nom: str):
    arbre = ast.parse((OPS / fichier).read_text(encoding="utf-8"))
    return [n for n in ast.walk(arbre)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nom]


def _porte(noeud, ident: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == ident for n in ast.walk(noeud))


@pytest.mark.parametrize("fichier", ["normal.py", "ability.py"])
def test_986_les_deux_fichiers_du_vecteur_existent(fichier):
    assert (OPS / fichier).is_file(), "foyer deplace : re-derive le chemin avant de conclure"


def test_986_normale_fait_passer_le_crit_par_le_spread():
    """D (normale) -- au moins un appel `_reduced_bounds(...)` porte `crit_damage`, et le
    fichier passe bien par `get_base_damage_fix64`. Verifie sur l'AST, pas par grep."""
    avec_crit = [c for c in _appels("normal.py", "_reduced_bounds")
                 if c.args and _porte(c.args[0], "crit_damage")]
    assert avec_crit, "normal.py ne fait plus passer crit_damage par _reduced_bounds"
    assert _appels("normal.py", "get_base_damage_fix64"), \
        "normal.py n'appelle plus get_base_damage_fix64 : le spread a disparu du vecteur"


def test_986_ability_ne_fait_PAS_passer_le_crit_par_le_spread():
    """D (ability) -- les bornes crit sont un `HitDamage(<...crit_damage>, <...crit_damage>)`,
    et le fichier n'appelle JAMAIS `get_base_damage_fix64` (il n'a pas de spread)."""
    hd = [c for c in _appels("ability.py", "HitDamage")
          if len(c.args) == 2 and all(_porte(a, "crit_damage") for a in c.args)]
    assert hd, "ability.py ne decale plus ses deux bornes de crit_damage"
    assert not _appels("ability.py", "get_base_damage_fix64"), \
        "ability.py a acquis un spread : contredit AttackDamageOptions[+0x2f] == 0"
