"""R1 — « le natif AGIT SANS BOUGER » : le moteur doit rester sur place LUI AUSSI.

GARDE de l'angle mort de l'agrément historique. `run_agreement` ne compare la POSITION que si le
natif a émis un `MoveUnitMessage` : un port qui déplace l'unité alors que le natif castait sur
place passait donc INAPERÇU (son `ability` matchait, et `pos` ne comptait rien). Le compteur
`stay` ferme ce trou ; ce test l'assertit.

VÉRITÉ NATIVE confrontée ici (RE gqfc5mff6c) : les positions candidates du tactic viennent de
`IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery` slot +0xe =
`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, dont l'`OrderedSet` est
SEEDÉ avec `GetUnitPosition(unit)` PUIS `UnionWith(GetMovablePositionsFor(...))`. La position
COURANTE est donc candidate, **et première** ; `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
étant keep-first (`>` STRICT), à utilité ÉGALE le natif RESTE EN PLACE.

Couple (board, seed) NON arbitraire : `C3_01` / `31337` EXERCE l'invariant (pas 11, `spaceStormcaller`
u89 — `StormcallerPlaybook` a une utilité position-INDÉPENDANTE, donc toutes ses positions légales
sont à égalité et seul l'ordre tranche). Avant le fix : le port balayait `reach_nc` = moves puis
origine -> il castait depuis la 1re tuile de move (2,4) quand le natif restait en (2,3) — `stay` 1/2.
L'oracle reste l'IA native LIVE (aucun snapshot gelé) ; le couple n'est qu'un générateur de bataille
choisi pour couvrir la branche.
"""
from __future__ import annotations

import os

import pytest

STEPS = int(os.environ.get("STAY_STEPS", "26"))
BOARD = os.environ.get("STAY_BOARD", "C3_01")
SEED = os.environ.get("STAY_SEED", "31337")


@pytest.fixture(scope="module")
def stay_agreement(live_session, build_runner):
    """Marche la trajectoire native une fois sur le couple qui exerce l'invariant."""
    import engine_validate as EV

    info = build_runner(SEED, extra=["--board", BOARD])
    wt = EV.weights.load()
    res = EV.run_agreement(live_session, info["rid"], STEPS, wt, log=lambda *a, **k: None)
    return res


def test_stay_coverage(stay_agreement):
    """Garde-fou anti-faux-vert : la trajectoire DOIT contenir des chunks « sans move »,
    sinon l'assertion suivante ne teste rien."""
    n = stay_agreement["stay"]["n"]
    assert n >= 1, (
        f"aucun chunk natif « agit sans bouger » sur {BOARD}/{SEED} : l'invariant R1 n'est pas "
        f"exercé (change STAY_BOARD/STAY_SEED/STAY_STEPS)")


def test_engine_stays_when_native_stays(stay_agreement):
    """R1 : natif sur place => moteur sur place (`to` nul ou égal à l'origine)."""
    st = stay_agreement["stay"]
    misses = [r for r in stay_agreement["records"] if r["kind"] == "stay" and not r["match"]]
    detail = "\n  ".join(
        f"step {r['step']} u{r['uid']}: natif reste en {r['native']}, moteur -> {r['engine']} "
        f"(engine_kind={r['engine_kind']})" for r in misses)
    assert not misses, (
        f"le moteur deplace une unite que le natif laissait sur place "
        f"({len(misses)}/{st['n']}):\n  " + detail)
