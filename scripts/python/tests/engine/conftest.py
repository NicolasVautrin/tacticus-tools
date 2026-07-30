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

`martial_inspiration_case` (#17, residu « s18 MartialInspiration ») -- MONTAGE NOMME du canal
`actorStats` PAR-PAS (`TotalAttacksMade`, +0x20) qui indexe la prediction de MartialInspiration
(1191). Montage dans `scripts/python/probe_17_martial_inspiration.py` ; la fixture n'en est que la
porte pytest.

`active_ability_used_case` (#17, l'autre residu `move`) -- MONTAGE NOMME du gate d'entree du
generateur d'abilities de l'IA (`HasFlag(unit, ActiveAbilityUsed = 2)`). Montage dans
`scripts/python/probe_17_active_ability_used_gate.py`.

`normal_attack_bonus_case` (#308) -- MONTAGE NOMME du `+1` que l'attaque NORMALE ajoute a son utilite
d'ACTION (`ALoki_NormalAttackPlaybook<T>$$CalculateCustomUtility` = `Fix64(1)` contre `Fix64(0)` a la
base). Le montage fabrique la fenetre d'exactement UN point d'utilite ou ce terme, et lui seul, decide
l'action. Montage dans `scripts/python/probe_308_normal_attack_bonus.py`.

Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un regime non
atteint est un VERT qui ment -- aucune mesure n'a eu lieu et la suite ne rougit pour personne."""
from __future__ import annotations

import pytest

import probe_17_active_ability_used_gate as AAU
import probe_17_hammer_corpse as HC
import probe_17_martial_inspiration as MI
import probe_308_normal_attack_bonus as NAB


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


@pytest.fixture(scope="module")
def martial_inspiration_case(live_session):
    """Fabrique : `martial_inspiration_case()` -> le dict de mesure du probe #17 MartialInspiration.

    Chaque appel monte UN runner isole (build + contact drive + N tours d'attaque) et le DISPOSE en
    sortie de `run()`. Portee MODULE : deux couples (board, seed) = deux mesures, partagees par les
    assertions du fichier."""
    cache: dict = {}

    def _case(seed: int = 11911, board: str = MI.BOARD, rounds: int = 3) -> dict:
        key = (seed, board, rounds)
        if key not in cache:
            r = MI.run(seed=seed, board=board, rounds=rounds, verbose=True)
            if "error" in r:
                pytest.fail(f"montage martial-inspiration NON INSTALLE (seed={seed}, board={board}, "
                            f"rounds={rounds}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def active_ability_used_case(live_session):
    """Fabrique : `active_ability_used_case()` -> le dict de mesure du probe #17 gate d'action.

    Chaque appel monte UN runner isole (build + drive au contact + cast d'ItItches) et le DISPOSE en
    sortie de `run()`."""
    cache: dict = {}

    def _case(seed: int = 12100, board: str = AAU.BOARD) -> dict:
        key = (seed, board)
        if key not in cache:
            r = AAU.run(seed=seed, board=board, verbose=True)
            if "error" in r:
                pytest.fail(f"montage active-ability-used NON INSTALLE (seed={seed}, "
                            f"board={board}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def normal_attack_bonus_case(live_session):
    """Fabrique : `normal_attack_bonus_case()` -> le dict de mesure du probe #308.

    Chaque appel monte les DEUX bras de l'A/B (`Damage` juste sous / juste au-dessus du seuil de
    bascule natif), pose la geometrie (cible amenee au contact) et DISPOSE ses runners. Les
    `damages` par defaut sont les constantes MESUREES du probe ; en passer d'autres (ou
    `auto=True`) re-calibre le montage sur un autre couple (board, seed, cible).

    Portee MODULE : chaque couple = deux builds, partages par les assertions du fichier."""
    cache: dict = {}

    def _case(board: str = NAB.BOARD, seed: int = NAB.SEED, target: str = NAB.TARGET,
              damages=None, auto: bool = False) -> dict:
        ds = tuple(damages) if damages else (NAB.D_BELOW, NAB.D_WINDOW)
        key = (board, seed, target, ds, auto)
        if key not in cache:
            res = None
            try:
                res = NAB.scenario(board=board, seed=seed, target=target,
                                   damages=None if auto else list(ds), auto=auto, verbose=True)
            except RuntimeError as exc:                 # montage non installe -> ROUGE, jamais skip
                pytest.fail(f"montage normal-attack-bonus NON INSTALLE (board={board}, seed={seed}, "
                            f"cible={target}, damages={ds}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    NAB.dispose(res)
            cache[key] = res
        return cache[key]
    return _case
