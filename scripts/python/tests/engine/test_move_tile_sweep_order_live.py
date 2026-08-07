"""GARDE R1-b -- ORDRE des positions candidates dans le sweep du tier Comparable.

REGLE PORTEE (mirror, cf. `ComparableAbilityGenerator._sweep_tiles` pour la chaine native complete) :
le generateur d'action natif balaie les positions dans l'ordre de la liste `tiles` du tactic, c.-a-d.
`[origine] + ordre d'insertion de MovementQuery$$GetMovableTilesFor` -- EXACTEMENT ce que le RPC
`aiMovableTiles` expose -- et `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
est KEEP-FIRST (`>` STRICT). Donc a utilite d'action EGALE, la tuile la PLUS TOT dans `action_tiles`
gagne. L'ordre CONCURRENT -- celui de `ranked` (`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom`,
un classement par utilite de MOUVEMENT) -- ne pilote AUCUNE boucle du generateur d'action.

Ce que ces gardes attrapent : toute re-imposition de l'ordre `ranked` (ou de n'importe quel tri) sur
le sweep de position. Elles ne comparent PAS a la tuile choisie par le natif : une divergence de
tuile peut aussi venir du TERME DE TUILE (composite Tile(7)), dont plusieurs feuilles sont dormantes
offline -- confondre les deux est exactement l'erreur que R1-b a couteee (cf.
`docs/rl/case-r1b-move-tile-sweep-order.md`).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

from engine.ai.action_generators import ComparableAbilityGenerator

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _move_tile_sweep_order import build_sweep_order_case  # noqa: E402

# (board, seed, pas) -- deux montages INDEPENDANTS portant un TIE de sweep. `C4_09`/999 pas 14 est
# celui dont l'ordre `ranked` et l'ordre `action_tiles` DIVERGENT sur les tuiles a egalite (le seul
# couple discriminant trouve sur 10 couples balayes) ; `C4_09`/4242 pas 15 porte le meme tie sur les
# MEMES deux tuiles avec une autre ability, les deux ordres y coincidant -- il garde l'invariant sans
# le discriminer, et c'est dit tel quel.
#
# ⚠ #506-r1 -- LE PAS N'EST PLUS EPINGLE, IL EST CHERCHE, et c'est ce qui rend ce fichier
# probant a nouveau. Un pas epingle est structurellement fragile : la trajectoire est marchee par
# le NATIF, donc toute tranche qui change une stat globale la deplace. Depuis la bascule
# « equiper » de #419-r6, le pas 14 de `C4_09`/999 -- « le seul couple discriminant trouve sur 10
# couples balayes » -- partait en `montage NON discriminant : les deux ordres coincident`, et le
# pas 15 de `C4_09`/4242 en `sans tie`. Le fichier restait VERT au `rc` en n'evaluant plus RIEN :
# exactement l'invisibilite que #455 documente. Le CRITERE de recherche est la premisse que les
# assertions supposent (un TIE d'au moins deux tuiles), et pour le 1er couple la DIVERGENCE des
# deux ordres -- celle-la meme qui fait qu'il discrimine.
#
# (board, seed, pas de DEPART, largeur de recherche, exiger la divergence des deux ordres)
CASES = [("C4_09", "999", 14, 24, True), ("C4_09", "4242", 15, 24, False)]


def _tie_d_au_moins_deux(c) -> bool:
    """La premisse COMMUNE aux deux gardes de tie : sans >= 2 tuiles a l'utilite max, l'ordre ne
    departage rien et le montage ne dit rien."""
    return c.best is not None and len(c.tie_tiles) >= 2


def _tie_discriminant(c) -> bool:
    """... et, pour le couple DISCRIMINANT, les deux ordres doivent DIVERGER sur les tuiles a
    egalite -- sinon `test_tie_is_won_by_the_earliest_action_tile` passerait aussi avec l'ancien
    sweep (celui qui suivait `ranked`) et ne prouverait rien."""
    if not _tie_d_au_moins_deux(c):
        return False
    tied = set(c.tie_tiles)
    return [t for t in c.action_tiles if t in tied] != [t for t in c.ranked_union if t in tied]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-s%d" % c[:3])
def sweep_case(request, rpc, build_runner):
    board, seed, step, search, discriminant = request.param
    accept = _tie_discriminant if discriminant else _tie_d_au_moins_deux
    c = build_sweep_order_case(rpc, build_runner, seed=seed, board=board, step=step,
                               accept=accept, search=search)
    print("\n[R1-b] %s/%s : pas RETENU %d (%s), tie=%r, %d pas ecarte(s)"
          % (board, seed, c.step, c.visual_id, c.tie_tiles, len(c.searched or [])))
    return c


def test_sweep_tiles_is_the_native_action_tiles_order(sweep_case):
    """`_sweep_tiles` rend `ctx.action_tiles` A L'IDENTIQUE, ordre compris (aucun tri, aucun filtre).

    C'est le mirror de la liste `tiles` que `DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5`
    passe au generateur : origine en tete puis l'ordre de `GetMovableTilesFor`."""
    c = sweep_case
    gen = ComparableAbilityGenerator()
    union = [t for t in c.ranked_union]
    got = gen._sweep_tiles(c.ctx, union)
    assert c.action_tiles, "action_tiles vide -- montage sans position candidate"
    assert got[:len(c.action_tiles)] == c.action_tiles, (
        "sweep de position REORDONNE : attendu action_tiles=%r, obtenu %r"
        % (c.action_tiles, got[:len(c.action_tiles)]))
    assert c.origin is None or got[0] == c.origin, (
        "l'ORIGINE n'est pas en tete du sweep : origin=%r got[0]=%r" % (c.origin, got[0]))
    extra = got[len(c.action_tiles):]
    assert not extra, (
        "tuile(s) `ranked` hors d'`action_tiles` : %r -- `ranked` est construit sur "
        "GetMovableTilesFor + mainTile, il ne peut rien contenir de plus" % (extra,))


def test_tie_is_won_by_the_earliest_action_tile(sweep_case):
    """A utilite d'action EGALE, `_best_attack` retient la tuile la PLUS TOT dans `action_tiles`.

    C'est le keep-first de `Bucket$$AddAction` applique a l'ordre natif. Le montage n'est probant que
    s'il porte reellement un tie (>= 2 tuiles a l'utilite max) -- sinon il ne dit rien de l'ordre."""
    c = sweep_case
    assert c.best is not None, "aucune action d'attaque retenue au pas %d" % c.step
    if len(c.tie_tiles) < 2:
        pytest.skip("pas %d sans tie (%d tuile(s) a l'utilite max) -- ne departage aucun ordre"
                    % (c.step, len(c.tie_tiles)))
    expected = next(t for t in c.action_tiles if t in set(c.tie_tiles))
    assert c.best[4] == expected, (
        "tie sur %r a u=%.4f : le sweep doit retenir la 1re tuile d'action_tiles (%r), il a retenu "
        "%r. action_tiles=%r ranked=%r"
        % (c.tie_tiles, c.best[1], expected, c.best[4], c.action_tiles, c.ranked_union))


def test_tie_tiles_are_not_in_action_tiles_order_under_ranked(sweep_case):
    """MONTAGE DISCRIMINANT : sur au moins un des couples, l'ordre `ranked` et l'ordre `action_tiles`
    ne s'accordent PAS sur les tuiles a egalite -- sans quoi la garde precedente passerait aussi avec
    l'ancien sweep et ne prouverait rien. Le couple non-discriminant est SKIP, pas vert par defaut."""
    c = sweep_case
    if len(c.tie_tiles) < 2:
        pytest.skip("pas %d sans tie" % c.step)
    tied = set(c.tie_tiles)
    by_action = [t for t in c.action_tiles if t in tied]
    by_ranked = [t for t in c.ranked_union if t in tied]
    if by_action == by_ranked:
        pytest.skip("pas %d : les deux ordres coincident sur %r -- montage NON discriminant"
                    % (c.step, by_action))
    assert c.best[4] == by_action[0], (
        "montage DISCRIMINANT (action_tiles %r vs ranked %r) : le sweep doit suivre action_tiles"
        % (by_action, by_ranked))
