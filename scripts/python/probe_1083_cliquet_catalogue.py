"""probe #1083 -- CLIQUET : un catalogue d'enum ecrit en vrac ne doit JAMAIS re-saturer
le signal code de `audit_passive_ability_coverage`.

Ce cliquet existe parce que le gisement s'est ouvert TOUT SEUL, par notre propre cadence :
#1080 a porte `BattleFocus`, qui exige `TilesWithoutPowerUps`, qui exige un mirror du
`HashSet<TriggeredAbilityType>` de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor`.
Ce mirror re-liste 22 membres `PowerUp_*` par leur NOM (comme la regle d'enum l'exige), et les
19 passifs correspondants sont sortis de la file GAP d'un seul bloc. Personne ne l'a vu dans la
PR : c'est un effet a distance d'un fichier vers un audit.

⚠ Il est ecrit sur l'AST, jamais par grep de source. Un cran teste par grep aurait ete un FAUX
VERT ici : le commentaire de l'auteur de `_power_up_ids()` cite lui-meme les litteraux
`PowerUp_*`, donc n'importe quel grep les trouve, catalogue exclu ou non.

Les trois etages -- le 3e est ce qui empeche le cliquet de passer au vert pour la mauvaise raison :

  1. un CATALOGUE (conteneur dont tous les elements sont attributaires sur la MEME base) est ECARTE ;
  2. un USAGE ISOLE du meme membre est CONSERVE (le correctif n'est pas trop large -- sans cet
     etage, `code_symbols` rendant l'ensemble VIDE passerait l'etage 1) ;
  3. les fixtures sont NON VIDES et les deux regimes DIFFERENT reellement (un test qui compare
     deux ensembles vides est vert et ne prouve rien).

Usage :
    python probe_1083_cliquet_catalogue.py        # rc 0 = tient, rc 1 = rompu
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit_passive_ability_coverage as A  # noqa: E402

# Un catalogue : tous les elements attributaires, MEME base -> ECARTE.
_CATALOGUE = '''
from x import TriggeredAbilityType as _T

def _power_up_ids():
    return frozenset(int(v) for v in (
        _T.CatPowerUp_Alpha, _T.CatPowerUp_Beta, _T.CatPowerUp_Gamma))
'''

# Un usage ISOLE (hors conteneur) -> CONSERVE.
_ISOLE = '''
from x import EffectType

_NOT_UPDATABLE = EffectType.SoloPowerUp_Delta
'''

# Un conteneur MIXTE (un element non attributaire) -> ce n'est PAS un catalogue -> CONSERVE.
_MIXTE = '''
from x import EffectType

PAIRE = (EffectType.MixPowerUp_Epsilon, 1234)
'''


def _syms(source: str) -> set:
    fd, path = tempfile.mkstemp(suffix=".py")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        syms, _lits, _ne = A.code_symbols(path)
        return syms
    finally:
        os.unlink(path)


def main() -> int:
    echecs = []

    cat = _syms(_CATALOGUE)
    iso = _syms(_ISOLE)
    mix = _syms(_MIXTE)

    # --- etage 3 d'abord : les fixtures voient-elles quelque chose ? -------------------
    # Sans lui, un `code_symbols` casse (rendant toujours l'ensemble vide) rendrait les
    # etages 1 et 2 verts pour la mauvaise raison sur l'etage 1.
    for nom, s in (("CATALOGUE", cat), ("ISOLE", iso), ("MIXTE", mix)):
        if not s:
            echecs.append("fixture %s : code_symbols rend un ensemble VIDE -- "
                          "le cliquet ne mesure rien" % nom)
    # et les deux regimes doivent REELLEMENT differer
    if not echecs:
        temoin = A._catalogue_member_ids
        try:
            A._catalogue_member_ids = lambda tree: set()
            cat_sans = _syms(_CATALOGUE)
        finally:
            A._catalogue_member_ids = temoin
        if cat_sans == cat:
            echecs.append("regime NON DISCRIMINANT : avec et sans l'exclusion, `code_symbols` "
                          "rend le MEME ensemble sur le catalogue -- accord en regime degenere")

    # --- etage 1 : le catalogue est ecarte ---------------------------------------------
    for membre in ("CatPowerUp_Alpha", "CatPowerUp_Beta", "CatPowerUp_Gamma"):
        if membre in cat:
            echecs.append("etage 1 : %r est encore compte alors qu'il est dans un CATALOGUE "
                          "(conteneur homogene attributaire) -- le signal code est re-sature"
                          % membre)

    # --- etage 2 : un usage isole est conserve (correctif pas trop large) ---------------
    if "SoloPowerUp_Delta" not in iso:
        echecs.append("etage 2 : un USAGE ISOLE (`EffectType.SoloPowerUp_Delta`) a ete ecarte -- "
                      "le correctif est TROP LARGE, il effacerait des cablages reels")
    if "MixPowerUp_Epsilon" not in mix:
        echecs.append("etage 2 : un conteneur MIXTE a ete traite comme un catalogue -- "
                      "le critere doit exiger que TOUS les elements soient attributaires")

    if echecs:
        print("[1083] CLIQUET ROMPU (%d)" % len(echecs))
        for e in echecs:
            print("   - %s" % e)
        return 1
    print("[1083] cliquet catalogue : OK (3 etages, fixtures non vides, regimes discriminants)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
