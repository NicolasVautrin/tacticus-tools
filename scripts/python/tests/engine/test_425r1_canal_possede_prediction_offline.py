"""#425-r1 (volet b) -- la face PREDICTION lisait le canal ACTIF-ONLY la ou le natif n'a AUCUN gate.

L'ETAT D'AVANT, ET POURQUOI IL A SURVECU
-----------------------------------------
`IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` itere
`EffectsOwnedComponent.ActiveEffectIds` de la MainTile (le nom trompe : le filtre d'activite n'y
est PAS) et somme `HasUtilityValue(nom) ? GetUtilityValue(nom) : 0` **sans consulter `IsActive` ni
`Removed`** -- relu sur DEUX corps, l'autre etant `DespoiledGroundUtility.<...>d__5$$MoveNext`.

La face MOVE a ete rebranchee sur la liste POSSEDEE (`ctx.effects_by_pos`, `only_active=False`).
La face PREDICTION, elle, est restee sur `Scene.tile_effects_by_pos`, le canal ACTIF-ONLY : les
DEUX chemins du MEME natif ne rendaient donc pas la meme chose. Le basculement etait REFUSE parce
que << le rayon de souffle n'est PAS mesure >> -- la `Scene` n'est pas lue QUE par des feuilles.

CE QUE CETTE TRANCHE FAIT, ET POURQUOI LE RAYON DEVIENT NUL PAR CONSTRUCTION
----------------------------------------------------------------------------
La `Scene` porte desormais les DEUX tables, et un seul lecteur change :

  * `Scene.tile_effects_by_pos`        (ACTIF-ONLY)  -> bonus de degat a magnitude POSITIONNELLE
                                                        (`avalanche_of_muscle.py`,
                                                        `entities/effects/base.py` via `att_ctx`),
                                                        dont le natif est un AUTRE noeud
                                                        (`HasTileStatusEffect`) -- INCHANGE ;
  * `Scene.tile_effects_owned_by_pos`  (POSSEDEE)    -> `SceneTileState`, donc la SEULE feuille
                                                        `TileEffects(10)`.

MESURE LIVE (2026-08-15, `t6dpr4k06g`, `probe_425r1_daemonic_ordnance_inactif.py`, montage
`--p-mow blackForgefiend` + cast de `1148 DaemonicOrdnance` sur `MC1_67`) :
  * `tileMeta` defaut et `includeInactive` publient les MEMES 8 tuiles a effet, MEMES noms ;
  * **0** effet de tuile a `active == False` -> gisement toujours VIDE sur ce regime ;
  * et une decouverte de capteur : le canal DEFAUT **ne publie PAS le champ `active`** (12 effets
    sans la cle). `_tile_effect_names(only_active=True)` ne filtre donc RIEN sur ce canal -- c'est
    seulement sous `includeInactive` que le drapeau existe. L'absence est une ABSENCE DE MESURE,
    jamais un `False`.

⚠ **LE `BLOCAGE: porteur` DE CE RESIDU EST REFUTE** : `blackForgefiend`, seul porteur non-npc de
`1148 DaemonicOrdnance`, est dans les **8 MoW spawnables** du pool -- le montage ne demande ni
injection catalogue ni greffe. Ce qui reste ouvert n'est pas un porteur mais un ETAT : un effet de
tuile dont l'`ActiveCondition` est fausse pendant qu'il reste dans la liste possedee.

100 % OFFLINE. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.ai.context import _tile_effect_names                            # noqa: E402
from engine.playbook.scene import Scene                                     # noqa: E402
from engine.utilities.tile import SceneTileState                            # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/utilities/tile.py",
        "scripts/python/engine/ai/context.py",
        "scripts/python/engine/playbook/avalanche_of_muscle.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("garde la SEPARATION de deux canaux de `Scene` et le lecteur de chacun ; aucun "
               "runner, aucune RPC, aucune lecture du binaire"),
}


class _Board:
    by_id = {1: {"col": 0, "row": 0}, 2: {"col": 1, "row": 0}}

    def id_at(self, c, r):
        return {(0, 0): 1, (1, 0): 2}.get((c, r))


def _scene(**kw) -> Scene:
    """`Scene` minimale -- les 11 champs positionnels du dataclass, vides. On construit la VRAIE
    classe (pas un double) : c'est elle qui doit porter les DEUX tables."""
    base = dict(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None)
    base.update(kw)
    sc = Scene(**base)
    sc.board = _Board()
    return sc


def test_les_deux_canaux_de_tileMeta_sortent_d_UN_SEUL_appel():
    """`_tile_effect_names` sert les deux lectures depuis les MEMES tuiles. Un effet SANS champ
    `active` est GARDE des deux cotes -- absence de mesure, jamais un retrait invente (c'est
    EXACTEMENT le regime du canal DEFAUT, mesure live : 12 effets sans la cle)."""
    tiles = [{"col": 0, "row": 0,
              "effects": [{"name": "Fire", "active": True}, {"name": "Ice", "active": False}]},
             {"col": 1, "row": 0, "effects": [{"name": "Thorns_DefenseReduction"}]}]
    possede = _tile_effect_names(tiles, only_active=False)
    actif = _tile_effect_names(tiles, only_active=True)
    assert possede[(0, 0)] == ["Fire", "Ice"]
    assert actif[(0, 0)] == ["Fire"]                     # TEMOIN : les deux DIFFERENT
    # ... et l'effet sans drapeau survit des DEUX cotes.
    assert possede[(1, 0)] == actif[(1, 0)] == ["Thorns_DefenseReduction"]


def test_SceneTileState_lit_la_liste_POSSEDEE():
    sc = _scene(tile_effects_by_pos={(0, 0): ["Fire"]},
                tile_effects_owned_by_pos={(0, 0): ["Fire", "Ice"]})
    noms = [e.name for e in SceneTileState(sc).effects.by_unit[1]]
    assert noms == ["Fire", "Ice"], noms


def test_le_REPLI_est_le_comportement_d_avant_jamais_un_vide():
    """Scene batie hors `context.py` (table possedee absente) -> on retombe sur l'actif-only."""
    sc = _scene(tile_effects_by_pos={(0, 0): ["Fire"]})
    assert sc.tile_effects_owned_by_pos is None
    noms = [e.name for e in SceneTileState(sc).effects.by_unit[1]]
    assert noms == ["Fire"], noms


def test_le_RAYON_DE_SOUFFLE_est_nul_le_canal_actif_only_est_INCHANGE():
    """Le lecteur des bonus de degat a magnitude positionnelle continue de voir l'ACTIF-ONLY.
    C'est ce qui rend la bascule sure : un seul consommateur change."""
    import inspect
    from engine.playbook import avalanche_of_muscle as AM
    src = inspect.getsource(AM)
    assert "scene.tile_effects_by_pos" in src
    assert "tile_effects_owned_by_pos" not in src
    # ... et le champ actif-only existe toujours, distinct.
    sc = _scene(tile_effects_by_pos={(0, 0): ["Fire"]},
                tile_effects_owned_by_pos={(0, 0): ["Fire", "Ice"]})
    assert sc.tile_effects_by_pos == {(0, 0): ["Fire"]}


def test_context_passe_bien_la_table_POSSEDEE_a_la_Scene():
    """Le CABLAGE : sans lui le champ resterait `None` et la bascule serait inerte."""
    import inspect
    from engine.ai import context as C
    src = inspect.getsource(C)
    assert src.count("tile_effects_owned_by_pos=effects_by_pos") == 2, \
        src.count("tile_effects_owned_by_pos=effects_by_pos")
    # ... et les DEUX tables continuent d'etre derivees du MEME appel `tileMeta`.
    assert "active_effects_by_pos = _tile_effect_names(tiles, only_active=True)" in src
    assert "effects_by_pos = _tile_effect_names(tiles, only_active=False)" in src
