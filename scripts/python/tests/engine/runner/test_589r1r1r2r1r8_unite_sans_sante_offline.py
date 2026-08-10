"""`#589-r1-r1-r2-r1-r8` -- UNE UNITE SANS SANTE N'EST PAS UN CADAVRE.

`IdunBattle.Entities.Components.HealthComponent$$IsAlive` a TROIS branches, et le port n'en portait
qu'UNE (`hp >= 1`) :

    if (RemainingValue@+0x18 >= 1)          return true;    // PV courants > 0 -> VIVANT
    if (get_CurrentMaximumValue() > 0)      return false;   // PV <= 0 mais un MAX -> MORT
    if (<+0x1c> is Nullable<int> HasValue)  return Value != -1;
    return true;                                            // PV <= 0 ET max <= 0 -> VIVANT

Le champ `+0x1c` EST `HealthComponent.minimal_health` cote port (le plancher du HP-floor).

MESURE qui a ouvert le residu (`probe_589r1r1r2r1r8_compteur_natif.py`, `C3_14` seed 777) :
`genesSmnDecoy`, un DECOY present au deploiement, porte `combatSnapshot.stats.health = 0` **et**
`healthMax = 0`, avec `decisionView.alive = true`. Le natif le COMPTE -- il allume
`AmuletOfTheVoidwyrm_CritDamageReduction` sur un porteur adjacent, et le compteur natif LU DU DEGAT
vaut **1** (modeles entiers 0/1/2/3, RNG neutralise). Le port, lui, rendait **0** : `_is_alive` le
declarait mort et `_within` le retirait de TOUT selecteur d'occupation -- sans erreur, sans
evenement, donc invisible.

(!) Ce fichier garde AUSSI le cran du dessous : `hpMax` doit rester PUBLIE dans le dict d'unite du
contexte DSL (`_unit_dict`) et rester dans `_LIVE_KEYS`. Sans cette clef, `_is_alive` ne peut pas
distinguer un cadavre d'une unite sans sante, et le mirror redevient inerte SANS qu'aucune de ses
assertions ne rougisse -- c'est exactement la forme de regression silencieuse que le residu a
trouvee.

ASCII only (console cp1252).
"""
from __future__ import annotations

import inspect

import hexgeo
import pytest

from engine.dsl.base import DslContext, _is_alive, _within
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import Owner
from engine.entities.selectors.units import AdjacentFriends
from engine.dsl.base import Const
from engine.runner.components import HealthComponent, unit_is_alive
from engine.runner.abilities.behaviours.context import _LIVE_KEYS, _unit_dict

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        # PROPRE A CE FICHIER. Foyers load-bearing, pour la relecture :
        # `engine/runner/components.py` (`unit_is_alive`, mirror de `HealthComponent$$IsAlive`, et
        # `HealthComponent` lui-meme), `engine/dsl/base.py` (`_is_alive` et `_within`),
        # `engine/runner/abilities/behaviours/context.py` (`_unit_dict` publie `hpMax`,
        # `_LIVE_KEYS` le re-lit), `engine/entities/selectors/units.py` (`AdjacentFriends`),
        # `engine/entities/pathfinding/board.py` (`neighbours_native`).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    # Aucun oracle natif ici : ce fichier confronte le port au decompile CITE et a lui-meme.
    # Le BUILD ne peut pas le faire changer d'avis (aucun ordinal d'enum, aucune table lue).
    "build": False,
    "toujours": False,
    "raison": "Verdicts figes : les QUATRE branches de `HealthComponent$$IsAlive` (PV > 0 ; PV <= 0 "
              "avec un maximum -> MORT ; PV <= 0 sans maximum -> VIVANT ; plancher `+0x1c` == -1), "
              "leur consommation par `_is_alive`/`_within`/`AdjacentFriends`, et la PUBLICATION de "
              "`hpMax` dans le dict d'unite. Aucun runner, aucune session Frida.",
}

COLS, ROWS = 5, 5
CENTRE = (2, 2)
VOISIN = (2, 1)
LOIN = (0, 0)

#: decalages even-q, recopies du montage de `test_515_adjacence_elevation_offline`.
EVENQ_EVEN = ((0, -1), (1, -1), (1, 0), (0, 1), (-1, 0), (-1, -1))
EVENQ_ODD = ((0, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))


def _board() -> Board:
    """Plateau 5x5 PLAT, avec le champ `neighbours` que le capteur produit."""
    idof = {(c, r): 1 + c * ROWS + r for c in range(COLS) for r in range(ROWS)}
    tiles = []
    for (c, r), i in idof.items():
        ds = EVENQ_EVEN if c % 2 == 0 else EVENQ_ODD
        tiles.append({"id": i, "col": c, "row": r, "elevation": 0, "tileDefId": "Grass",
                      "isTemporary": False, "isWall": False, "walkable": True,
                      "occupantUnitId": None,
                      "neighbours": [idof[(c + dc, r + dr)] for dc, dr in ds
                                     if (c + dc, r + dr) in idof]})
    return Board(tiles, adjacency="evenq")


def _u(uid, pos, team=2, hp=100, hp_max=100, alive=True, traits=()):
    d = {"id": uid, "team": team, "alive": alive,
         "pos": {"col": pos[0], "row": pos[1]}, "_traits": set(traits)}
    if hp is not None:
        d["hp"] = hp
    if hp_max is not None:
        d["hpMax"] = hp_max
    return d


class _Entite:
    """Entite MINIMALE : `unit_is_alive` ne lit qu'un `HealthComponent`, rien d'autre."""

    def __init__(self, hc):
        self._hc = hc

    def get_component(self, cls):
        return self._hc if cls is HealthComponent else None


# ------------------------------------------------------------------ etage 0 : le montage MORD
def test_589r1r1r2r1r8_le_montage_est_discriminant():
    """Sans ce cran, les tests d'apres pourraient etre verts pour la mauvaise raison : il faut que
    le temoin SANS SANTE et le temoin CADAVRE soient a la MEME distance du centre (hex 1), et que
    seule la sante les separe."""
    assert hexgeo.distance(CENTRE, VOISIN) == 1
    assert hexgeo.distance(CENTRE, LOIN) > 1
    b = _board()
    tid = b.id_at(CENTRE[0], CENTRE[1])
    assert tid is not None, "centre non resolvable : le montage ne mesure rien"
    voisins = {b.coord(v) for v in b.neighbours_native(tid)}
    assert voisins, "liste d'adjacence STOCKEE vide : le montage ne mesure rien"
    assert VOISIN in voisins, "le montage a perdu son temoin de voisinage stocke"


# ------------------------------------------------------------------ etage 1 : le mirror ENTITE
@pytest.mark.parametrize("hp,hp_max,mini,attendu,pourquoi", [
    (100, 100, None, True, "PV courants > 0 -> `RemainingValue >= 1`"),
    (1, 100, None, True, "PV courants a 1 : la borne du natif est `>= 1`, pas `> 1`"),
    (0, 100, None, False, "CADAVRE : PV <= 0 mais `get_CurrentMaximumValue() > 0`"),
    (-5, 100, None, False, "PV negatifs avec un maximum : cadavre aussi"),
    (0, 0, None, True, "SANS SANTE : PV <= 0 ET maximum <= 0 -> le natif rend VRAI"),
    (0, 0, -1, False, "plancher `+0x1c` == -1 -> le natif rend FAUX"),
    (0, 0, 3, True, "plancher `+0x1c` != -1 -> le natif rend VRAI"),
])
def test_589r1r1r2r1r8_unit_is_alive_mirror(hp, hp_max, mini, attendu, pourquoi):
    """`IdunBattle.Entities.Components.HealthComponent$$IsAlive`, branche par branche."""
    e = _Entite(HealthComponent(hp=hp, hp_max=hp_max, minimal_health=mini))
    assert unit_is_alive(e) is attendu, pourquoi


def test_589r1r1r2r1r8_unit_is_alive_degradations_nommees():
    """Les DEUX degradations conservatrices, ecrites pour etre relues -- pas des effets de bord.

    `hp` non capte -> VIVANT (on ne gate jamais sur un etat de PV non mesure, comportement d'avant
    ce mirror) ; MAXIMUM non capte avec `hp <= 0` -> MORT (on n'etend PAS la branche << sans
    sante >> a tout ce qui n'a pas publie son maximum)."""
    assert unit_is_alive(_Entite(None)) is True
    assert unit_is_alive(_Entite(HealthComponent(hp=None, hp_max=None))) is True
    assert unit_is_alive(_Entite(HealthComponent(hp=0, hp_max=None))) is False
    assert unit_is_alive(None) is True


# ------------------------------------------------------------------ etage 2 : le mirror DICT
@pytest.mark.parametrize("hp,hp_max,alive,attendu", [
    (100, 100, True, True),
    (0, 100, True, False),          # cadavre
    (0, 0, True, True),             # SANS SANTE -- la branche que le port ne portait pas
    (0, 0, False, False),           # hors du pool `AliveUnits` : le `alive` prime
    (100, 100, False, False),
])
def test_589r1r1r2r1r8_is_alive_dict(hp, hp_max, alive, attendu):
    assert _is_alive(_u(1, CENTRE, hp=hp, hp_max=hp_max, alive=alive)) is attendu


def test_589r1r1r2r1r8_is_alive_sans_hpmax_reste_comme_avant():
    """`hpMax` ABSENT -> verdict d'AVANT le mirror. C'est ce qui empeche l'entite-TUILE de
    `_tile_entity` (`hp: None`, aucun `hpMax`) d'entrer dans les selecteurs d'occupation."""
    assert _is_alive({"id": 1, "alive": True, "hp": 0}) is False
    assert _is_alive({"id": 1, "alive": True, "hp": None}) is False
    assert _is_alive({"id": 1, "alive": True, "hp": 100}) is True


# ------------------------------------------------------------------ etage 3 : la clef est PUBLIEE
def test_589r1r1r2r1r8_hpmax_publie_et_relu_live():
    """Le cran du dessous. `_is_alive` ne voit qu'un dict : si `_unit_dict` cesse de publier
    `hpMax`, le mirror de l'etage 2 devient INERTE et aucune de ses assertions ne rougit."""
    assert "hpMax" in _LIVE_KEYS, ("`hpMax` doit etre RE-LU du state (il mute : bumps de maximum) "
                                   "-- fige au seed, un predicat re-evalue lirait un maximum perime")
    # Lecture de SOURCE, et c'est assume : `_unit_dict` exige un `State` complet (composants,
    # `get_unit_feet`) qu'un stub ne peut pas fournir sans devenir un second moteur. Ce cran garde
    # donc la PRESENCE de la clef et de sa SOURCE (`hc.hp_max`), pas sa valeur -- la valeur, elle,
    # est confrontee LIVE par `probe_589r1r1r2r1r8_compteur_natif.py`.
    src = inspect.getsource(_unit_dict)
    assert '"hpMax"' in src, (
        "`_unit_dict` ne construit plus la clef `hpMax` : `_is_alive` ne peut plus distinguer un "
        "CADAVRE d'une unite SANS SANTE, et le mirror redevient INERTE en silence")
    assert "hp_max" in src, "`hpMax` ne vient plus de `HealthComponent.hp_max`"


# ------------------------------------------------------------------ etage 4 : la CONSOMMATION
def test_589r1r1r2r1r8_selecteur_occupation_ramasse_l_unite_sans_sante():
    """Le bout de la chaine, celui que la mesure live a pris en defaut : `AdjacentFriends(Owner)`
    doit rendre l'allie SANS SANTE pose sur un voisin STOCKE -- et continuer de refuser le
    CADAVRE, qui est au MEME endroit. Les deux temoins sont indispensables : sans le cadavre, un
    `_is_alive` rendu inconditionnellement vrai passerait ce test."""
    b = _board()
    porteur = _u(1, CENTRE)
    sans_sante = _u(2, VOISIN, hp=0, hp_max=0)
    ctx = DslContext(units=[porteur, sans_sante], caster=porteur, target=porteur, board=b)
    ids = sorted(u.get("id") for u in AdjacentFriends(Owner(), Const(1), Owner()).select(ctx))
    assert ids == [2], "l'allie SANS SANTE (0/0) doit etre compte : le natif le compte"

    cadavre = _u(3, VOISIN, hp=0, hp_max=100)
    ctx2 = DslContext(units=[porteur, cadavre], caster=porteur, target=porteur, board=b)
    ids2 = sorted(u.get("id") for u in AdjacentFriends(Owner(), Const(1), Owner()).select(ctx2))
    assert ids2 == [], "un CADAVRE sur la meme tuile ne doit PAS etre compte"


def test_589r1r1r2r1r8_within_non_degenere():
    """ANTI-VACUITE : `_within` doit rendre un ensemble NON VIDE dans le regime teste, sinon
    l'egalite de l'etage 4 serait un accord entre deux vides."""
    b = _board()
    porteur = _u(1, CENTRE)
    unites = [porteur, _u(2, VOISIN, hp=0, hp_max=0), _u(4, LOIN)]
    ring = _within(unites, porteur, 1, board=b, order="adjacent")
    assert [u.get("id") for u in ring] == [2], (
        "le ring doit contenir EXACTEMENT l'unite sans sante : ni vide (rien mesure), ni l'unite "
        "LOIN (le filtre d'appartenance ne mordrait plus)")
