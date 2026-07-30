"""L'etage `scoring` du mouvement (#320) -- la TUILE COURANTE est-elle dans le candidate-set ?

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident
--------------------------------------------------------------------
A. **Sur un pas ou le natif n'emet AUCUN `MoveUnitMessage`, le port ne propose aucun deplacement
   REEL** -- il choisit la tuile COURANTE. C'est la question binaire de #320. Avant le correctif, le
   candidate-set du generateur de mouvement etait `ctx.move_tiles` (RPC `aiMovableTiles` =
   `GetMovableTilesFor`), qui EXCLUT la tuile courante : « rester sur place » n'etait pas
   representable, donc le port proposait toujours un deplacement REEL.
B. **La contre-epreuve MORD** : le bras `NEUTRE` remet le candidate-set d'AVANT (`ctx.move_tiles`
   seul) et doit DIVERGER sur ces memes pas. Les deux bras sont joues sur le MEME etat, au meme pas
   (`engine_decide` est pur) -- pas sur « deux runners identiques ».
C. **DEUX couples (board, seed)**, dont le second est designe sur MESURE (`probe_320 --scan`), et
   surtout **DEUX REGIMES DE DEPARTAGE OPPOSES** (cf. le tableau ci-dessous). Un montage unique ne
   distingue pas un correctif JUSTE d'un correctif qui COINCIDE ; deux montages ou la meme feuille
   tranche dans le meme sens non plus.
D. **RIEN DE JUSTE N'EST CASSE** : le probe ventile les pas discriminants en `fixed` / `broken`.
   Un lot ou les deux se compensent laisserait un total d'accord flatteur et un port PIRE.
E. **Les pas ou le natif BOUGE ne se degradent pas** : `same >= neu_same` sur ce sous-ensemble.
F. **L'ORDRE est garde OFFLINE** : la tuile courante doit etre PREMIERE dans le candidate-set. Ce
   n'est pas cosmetique -- l'argmax natif remplace sur `>` STRICT (keep-first), donc c'est l'ordre
   qui produit « a utilite EGALE, reste sur place ».

LES DEUX REGIMES MESURES (table par feuille, `probe_320 --table`) -- c'est ce qui interdit de
fitter un scalaire : la MEME feuille y prend des valeurs de SIGNE OPPOSE, et les deux tombent
ensemble avec le seul correctif.

| montage | pas | origine | tuile du port NEUTRE | ce qui DEPARTAGE |
|---|---|---|---|---|
| `C1_12`/12100 | step 8, u79 | (3,6) tile=+4 mindist=-300 -> **-296** | (4,5) tile=-30 mindist=-300 -> -330 | `TileEffectsUtility` (+9 cover heberge vs -25 `Thorns_DefenseReduction`), MinDist EGAL |
| `C1_12`/909   | step 3, u93 | (4,5) tile=-30 mindist=**-200** -> **-230** | (5,5) tile=+10 mindist=-300 -> -290 | `MinDistanceToClosestEnemy` (pathdist 2 vs 3) -- ici le terme de TUILE DEFAVORISE l'origine |

MECANIQUE (decompile = verite, build `rnca9r7q6c`) :
* `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` appelle le slot `+0xe` de
  l'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, dont
  l'`OrderedSet` est **SEEDE avec la position courante** puis `UnionWith(GetMovablePositionsFor)` ;
* `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
  construit UN `IdunBattle.AI.Utilities.UtilityMovementCase` par position et delegue a
  `IdunBattleLogic.AI.Utilities.UtilityDecider` ;
* l'argmax est dans
  `IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext`
  et remplace sur `FixMath.NET.Fix64$$op_GreaterThan` -- **STRICT**, donc keep-first.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_320_movement_scoring_origin as AB              # noqa: E402

# DEUX montages nommes. Le premier est le residu `scoring` que `case-309` avait NOMME et laisse
# ouvert (« step 8, unite u79, origine (3,6), 15 tuiles movables, le port propose (4,5) »). Le
# second n'est pas choisi a l'intuition : `probe_320 --scan 777,909,4242,31337` l'a designe -- c'est
# le SEUL des quatre a porter un pas DISCRIMINANT (les trois autres rendent le meme resultat dans
# les deux bras, donc ne concluent RIEN et sont ecartes SUR MESURE).
MONTAGES = (("C1_12", 12100, 12), ("C1_12", 909, 14))


@pytest.fixture(scope="module")
def walks():
    out = {}
    for board, seed, steps in MONTAGES:
        res = AB.run(seed=seed, board=board, steps=steps, verbose=False)
        if "error" in res:
            pytest.fail("montage %s/%d NON INSTALLE : %s" % (board, seed, res["error"]))
        out["%s/%d" % (board, seed)] = res["walk"]
    return out


def test_the_montage_actually_exercises_the_stay_regime(walks):
    """Un montage ou le natif bouge TOUJOURS ne mesure rien de cette tranche -- et une garde qui
    passe sur un montage vide est pire qu'absente (`C1_03` a ete ecarte comme ca en #309)."""
    for k, w in walks.items():
        assert w["stay"]["n"] > 0, (
            "montage %s : aucun pas ou le natif n'emet de `MoveUnitMessage` sur %d pas decides "
            "-- il ne mesure rien" % (k, w["n"]))


def test_the_montage_is_discriminant(walks):
    """Un lot ou les DEUX bras donnent le meme resultat ne conclut RIEN. Ce test dit lequel des
    montages exhibe reellement l'ecart."""
    for k, w in walks.items():
        assert w["discriminant"], (
            "montage %s : aucun pas ou le candidate-set CHANGE le resultat -- les deux bras sont "
            "d'accord partout, ce montage ne conclut rien" % k)


def test_engine_never_moves_where_native_stays_put(walks):
    """A : la question binaire de #320. **Formulee sur le DEFAUT lui-meme**, pas sur les pas
    discriminants : un pas est du ressort de cette tranche quand le natif n'emet aucun
    `MoveUnitMessage` et que le port propose un DEPLACEMENT REEL vers une autre tuile. Zero attendu.

    ⚠ La restreindre aux pas `discriminant` la rendrait VACUOUS sous mutation : si l'on remet le
    candidate-set d'AVANT, les deux bras redeviennent identiques, `discriminant` est VIDE et un test
    ainsi ecrit passerait au VERT sur un port faux. Mesure faite -- c'etait le cas."""
    for k, w in walks.items():
        assert not w["scoring_miss"], (
            "montage %s : %d pas ou le natif ne bouge pas et ou le port propose un deplacement "
            "REEL -- %s" % (k, len(w["scoring_miss"]), w["scoring_miss"]))


def test_removing_the_current_tile_makes_the_engine_diverge(walks):
    """B : le ROUGE conserve, sur les DEUX faces. Sans la tuile courante au candidate-set, le port
    vise une AUTRE tuile la ou le natif reste sur place. Si ce test cessait de mordre, l'accord
    ci-dessus viendrait d'ailleurs que du correctif."""
    for k, w in walks.items():
        assert w["neu_scoring_miss"], (
            "montage %s : le port SANS la tuile courante ne propose AUCUN deplacement indu -- la "
            "contre-epreuve ne mesure plus rien" % k)
        assert w["fixed"], (
            "montage %s : aucun pas ou le candidate-set CHANGE le resultat -- la contre-epreuve "
            "ne mesure plus rien" % k)


def test_the_fix_breaks_nothing_that_was_right(walks):
    """D : zero pas CASSE. Le correctif ne doit pas troquer un accord contre un autre."""
    for k, w in walks.items():
        assert not w["broken"], (
            "montage %s : %d pas que le port d'AVANT avait JUSTE et que le correctif casse -- %s"
            % (k, len(w["broken"]), w["broken"]))


def test_steps_where_native_moves_are_not_degraded(walks):
    """E : sur les pas ou le natif BOUGE, le correctif ne doit rien perdre. C'est le sous-ensemble
    que la metrique `pos` de `engine_validate.run_agreement` compare -- une perte ici serait une
    regression VISIBLE de l'agreement."""
    for k, w in walks.items():
        assert w["moved"]["same"] >= w["moved"]["neu_same"], (
            "montage %s : accord de position DEGRADE sur les pas de deplacement -- CABLE=%d "
            "NEUTRE=%d" % (k, w["moved"]["same"], w["moved"]["neu_same"]))


def test_current_tile_is_first_in_the_candidate_set():
    """F -- OFFLINE. `GetCurrentAndMovablePositionsFor` SEEDE son `OrderedSet` avec la position
    courante : elle est PREMIERE. L'argmax natif remplaçant sur `>` STRICT (keep-first), c'est cet
    ORDRE qui produit « a utilite EGALE, le natif reste sur place ». Un candidate-set qui contient
    la tuile courante mais la met en QUEUE serait faux sur toute egalite -- et aucun montage live ne
    le verrait tant qu'aucune egalite n'y tombe."""
    from types import SimpleNamespace
    from engine.ai.action_generators import movement_candidate_positions
    from engine.ai.context import action_tiles_for

    origin = (3, 6)
    movable = [{"col": 4, "row": 5}, {"col": 2, "row": 6}, {"col": 4, "row": 6}]
    ctx = SimpleNamespace(action_tiles=action_tiles_for(origin, movable))
    got = movement_candidate_positions(ctx)
    assert got, "candidate-set VIDE -- le generateur n'evaluerait aucune tuile"
    assert (got[0]["col"], got[0]["row"]) == origin, (
        "la tuile courante n'est pas PREMIERE dans le candidate-set : %r" % (got[:3],))
    assert len(got) == 1 + len(movable), (
        "candidate-set de taille %d pour 1 origine + %d movables -- doublon ou perte"
        % (len(got), len(movable)))
    # ...et elle n'y est qu'UNE fois : le natif fait une UNION, pas une concatenation.
    coords = [(t["col"], t["row"]) for t in got]
    assert coords.count(origin) == 1, "la tuile courante apparait %d fois" % coords.count(origin)
