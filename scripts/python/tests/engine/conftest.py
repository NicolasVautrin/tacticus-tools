"""Fixtures locales a la tranche DECISION (prediction / playbook / utilites).

`hammer_corpse_case` (#17, residu « s8 Hammer ») -- MONTAGE NOMME ET REUTILISABLE du filtre VIVANT des
cibles secondaires de `HammerOfWrath` (1153) sur la face DECISION. Le montage lui-meme (build isole,
geometrie DRIVEE autour de la cible, fabrication d'un vrai CADAVRE hex-adjacent, capture du seam de
decision, evaluation de `make_hammer_wrath_events` + instrument de magnitude auto-verifie) vit dans
`scripts/python/probe_17_hammer_corpse.py` -- la fixture n'en est que la PORTE pytest.

Deux regimes, `probe_17_hammer_corpse.CASES` : `witness` (cadavre ET temoin vivant adjacents) et
`corpse-only` (le cadavre est le SEUL adjacent). Ajouter un cas = ajouter une entree la-bas, pas
dupliquer un montage inline dans un test.

Portee MODULE : chaque regime coute un build + un drive + un kill ; les assertions d'un meme fichier se
partagent la mesure.

Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un regime non
atteint est un VERT qui ment -- aucune mesure n'a eu lieu et la suite ne rougit pour personne."""
from __future__ import annotations

import pytest

import probe_17_hammer_corpse as HC


@pytest.fixture(scope="module")
def hammer_corpse_case(live_session):
    """Fabrique : `hammer_corpse_case("witness")` -> le dict de mesure du probe #17.

    `live_session` est tire ICI (le montage exige la session Frida) ; le runner est DISPOSE par le probe
    en sortie de `run()`, donc rien a liberer au teardown."""
    cache: dict = {}

    def _case(case: str, seed: int = 17153, board: str = HC.BOARD, center=HC.CENTER) -> dict:
        assert case in HC.CASES, f"cas inconnu : {case} (connus : {sorted(HC.CASES)})"
        key = (case, seed, board, tuple(center))
        if key not in cache:
            r = HC.run(case=case, seed=seed, board=board, center=center, verbose=True)
            if "error" in r:
                pytest.fail(f"montage hammer-corpse NON INSTALLE ({case}, seed={seed}, "
                            f"board={board}, centre={tuple(center)}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case
