"""#448-r1 -- GARDES de l'effet `1179 StormboyzStrike_AlreadyUsedTile`.

Ce que ces tests verrouillent, et POURQUOI chacun peut casser en silence :

1. `1179` n'a AUCUN lecteur par immediat dans le binaire ; son unique lecteur passe par le NOM
   (`Enum.ToString`) et le poids IA `BC.Utilities.<profil>.TileEffects`. Un futur refactor de
   `TileEffectsUtility` vers une liste blanche d'effets connus eteindrait le poids SANS erreur.
2. Le poids vaut `-100` et c'est le PLUS NEGATIF de sa categorie -- c'est ce qui donne son sens
   mecanique au marqueur (le Stormboy suivant evite la tuile deja utilisee). Une regression qui
   le ramenerait au niveau des `-40` serait invisible autrement.
3. `IdunBattle.AI.Utilities.TileEffectsUtility` ne multiplie un poids par
   `$$GetStatusEffectMultiplier` QUE si `StaticBattleRules.Effect$$IsTileStatusEffect(type)` --
   un `OrderedSet` de CINQ valeurs, peuple par immediats dans le `.cctor`. `1179` n'y est pas,
   donc le poids BRUT du port est EXACT. Le docstring du port annonce le multiplicateur comme
   « non porte » : ce test dit que cette limite est INERTE pour cet effet, au lieu de la laisser
   se lire comme un ecart possible.

RE complete : `docs/rl/case-448-r1-stormboyz-fallback-miss.md`.
Mesure live du poseur : `python scripts/python/probe_448_r1_stormboyz_fallback_miss.py --live`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
EFFECT_NAME = "StormboyzStrike_AlreadyUsedTile"
EFFECT_TYPE = 1179

#: `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor`, lu au
#: desassemblage : cinq `OrderedSet.Add` consecutifs juste apres le `.ctor` du set.
TILE_STATUS_EFFECTS = {5, 17, 58, 1244, 1476}   # Fire, Ice, Darkness, Contaminated, DespoiledGround


@pytest.fixture(scope="module")
def bc() -> dict:
    return json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))


def test_the_bc_carries_the_tile_effect_weight(bc):
    """Le poids EXISTE dans la categorie `TileEffects` du profil `Default`."""
    cat = bc["Utilities"]["Default"]["TileEffects"]
    assert EFFECT_NAME in cat, (
        "le poids IA de %s a disparu du seed BC -- le marqueur pose par "
        "StormboyzStrike_FallbackAbility n'aurait plus AUCUN lecteur" % EFFECT_NAME)
    assert cat[EFFECT_NAME] == -100


def test_it_is_the_most_negative_weight_of_its_category(bc):
    """C'est le poids le plus DISSUASIF de la categorie -- devant les `-40` des pending-attack.

    Ce n'est pas un detail esthetique : le Fallback choisit sa tuile par
    `SortTilesByUtility(CanAddUnit(AllTiles), Caster, UtilityDefinition(UtilityType.UnitMovement))`,
    dont `TileEffects` est une feuille. Si le poids cessait de dominer, deux Stormboyz du meme
    tour pourraient viser la meme tuile."""
    cat = bc["Utilities"]["Default"]["TileEffects"]
    worst = min(cat.items(), key=lambda kv: kv[1])
    assert worst[0] == EFFECT_NAME, "le poids le plus negatif est %s (%s), plus %s" % (
        worst[0], worst[1], EFFECT_NAME)


def test_the_port_reads_the_weight_by_name(bc):
    """`TileEffectsUtility` du port rend bien -100 pour une tuile marquee.

    Le natif fait `Enum.ToString(effectType)` puis `GetUtilityValue(name)` : la lecture est
    GENERIQUE PAR NOM, jamais par une liste d'effets connus. Le port doit le rester."""
    from engine.utilities.tile import TileEffectsUtility
    from engine.weights import Weights

    wt = Weights(bc["Utilities"])
    u = TileEffectsUtility().evaluate(None, {"effects": [EFFECT_NAME]}, None, wt)
    assert u == -100.0


def test_an_unmarked_tile_scores_zero(bc):
    """CONTRE-BRAS : sans le marqueur, la meme feuille rend 0. Sans ce bras, un port qui
    rendrait -100 PARTOUT passerait le test precedent."""
    from engine.utilities.tile import TileEffectsUtility
    from engine.weights import Weights

    wt = Weights(bc["Utilities"])
    assert TileEffectsUtility().evaluate(None, {"effects": []}, None, wt) == 0.0
    assert TileEffectsUtility().evaluate(None, {}, None, wt) == 0.0


def test_the_duration_multiplier_does_not_reach_this_effect():
    """`IsTileStatusEffect(1179)` est FAUX -> le poids brut du port est EXACT.

    Le port note dans son docstring que le multiplicateur de duree natif n'est pas porte. Ce test
    fige la raison pour laquelle ce n'est PAS un ecart ici : l'`OrderedSet` que lit le natif ne
    contient que cinq EffectType, et 1179 n'en fait pas partie."""
    assert EFFECT_TYPE not in TILE_STATUS_EFFECTS


def test_no_dedicated_effect_class_exists_for_1179():
    """Aucune classe `*AlreadyUsedTile*Effect` : le builder d'`EffectsDatabase` (lambda
    `<InitializeEffects>b__14_197`) construit un `IdunBattle.Entities.Effects.NoneEffect`.
    L'effet ne contribue donc a AUCUN canal de COMBAT -- son seul role est le poids IA ci-dessus.
    Si une classe apparaissait dans un build futur, ce verdict serait a refaire."""
    hits = []
    for tsv in (ROOT / "data" / "symbols").glob("*/frida/classes.tsv"):
        for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
            if "AlreadyUsedTile" in line:
                hits.append(line.split("\t")[0])
    assert hits == [], "une classe d'effet dediee est apparue : %s" % hits
