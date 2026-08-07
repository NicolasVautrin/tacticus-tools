"""#494-r1 -- CLIQUET de l'ORDRE des cibles de `SortUnitsByDamageUtilitySelector`.

Ce que ce fichier garde, et qu'aucune mesure live ne garde : les deux proprietes dont la perte
serait SILENCIEUSE (ni erreur, ni crash -- juste une 4e cible differente de celle du natif).

  [1] LE TIE-BREAK EST L'ORDRE SOURCE, PAS L'ORDRE PAR `id`. Le natif finit par
      `units.OrderBy(u => -dict[u]).ToList()` et `System.Linq.Enumerable.OrderBy` est **STABLE** :
      a utilite egale, l'ordre du selecteur ressort intact. Le port imposait
      `sorted(int(c) for c in candidates)` AVANT de trier -- ce qui ne « approxime » pas la
      stabilite, ca la DETRUIT, en substituant un ordre source qui n'est pas celui du natif.
      Regime `L1` de `probe_494_doombolt_sort_order.py` (4 x `orksNob` identiques sur des tuiles
      TOUTES a l'elevation du caster) : les quatre utilites sont egales et le natif rend l'ordre
      SOURCE `cube-lex (x, y)`.

  [2] LA CLE N'EST PAS CONSTANTE : ELLE DEPEND DU COUPLE (caster, cible). Le natif appelle la
      prediction d'attaque DANS sa boucle `foreach u`, en lui passant la POSITION DU CASTER
      (`dc+0x20 = GetUnitPosition(owner)`) ; les feuilles POSITIONNELLES du builder partage
      `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
      (`…$$CalculateElevationBonusModifier`, `…$$CalculateTrenchReduction`) rendent donc la plage
      predite differente d'une cible a l'autre -- sans qu'aucune stat de cible n'ait bouge.
      Corollaire executable : les quatre call-sites DOIVENT passer `owner_id=`. Un call-site qui
      l'oublie retombe exactement sur le comportement d'avant (cle constante), sans rien casser.

  [3] CE QUE CETTE TABLE REFUTE. #494 avait mesure, sur sept geometries dont deux predictions hors
      echantillon, que l'ordre natif etait l'enumeration de tuiles `cube-lex (x, y)` ASCENDANTE
      **rotee d'un cran vers la gauche**, sans pouvoir l'attribuer a un etage natif. Les trois
      regimes `L*` -- qui font varier l'ELEVATION et rien d'autre -- la contredisent TOUS LES
      TROIS. Ce n'etait pas une loi d'ordre : c'etait l'ombre d'une cle non constante, tous les
      montages de #494 ayant melange des elevations. La table ci-dessous fige les trois mesures,
      pour qu'un futur retour a un tri par `id` (ou une perte du cablage `owner_id`) la rougisse.

MESURES FIGEES (board `MC1_67`, seed 777, build `rnca9r7q6c`, 2026-08-07 ; caster `thousAhriman`
@(3,3) elevation 3 ; cibles = 4 x `orksNob` IDENTIQUES, `--hp-target 400000` donc
`Armor = FixedArmor = 0` et `statDelta` VIDE ; cible du message u79) :

    | regime | positions des cibles                | elevations   | ordre SOURCE   | NATIF joue   |
    | L1     | (3,4) (1,4) (2,4) (5,4)             | 3 3 3 3      | 81 83 79 85    | 79 81 83     |
    | L2     | (3,4) (1,4) (2,4) (4,4)             | 3 3 3 2      | 81 83 79 85    | 79 85 81     |
    | L3     | (3,4) (1,2) (2,4) (5,4)             | 3 2 3 3      | 81 83 79 85    | 79 81 83     |

(`N = 3` coups sur `C = 4` cibles -> `[1, 1, 1, 0]`, donc la 4e place ne se lit pas dans la
sequence jouee ; ce qui se lit est l'ordre des TROIS premieres.)

ASCII only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.runner.components import HealthComponent          # noqa: E402
from engine.runner.operations import damage_utility as DU     # noqa: E402

#: DECLENCHEUR -- volontairement LARGE. Ce fichier importe `engine.runner.operations.damage_utility`
#: (donc toute sa fermeture : composants, poids de la BC, services de degat) ET balaie
#: STATIQUEMENT `scripts/python/engine/**` a la recherche des call-sites du foyer. Un declencheur
#: restreint aux deux fichiers touches manquerait le cas qui compte : un call-site NEUF ajoute
#: ailleurs dans `engine/**` sans son `owner_id=`. `**/` exige un SEGMENT, d'ou les deux globs.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le foyer PARTAGE du tri par utilite de degat (`damage_utility`) et ses QUATRE "
              "call-sites (Doombolt, FinalJustice, AncestralFortune, KillMaimBurn), plus tout ce "
              "que la fermeture d'imports traverse : poids d'utilite lus dans la BC, services "
              "`damage_modifiers` (feuilles positionnelles elevation/trench), composants du "
              "runner. Le balayage statique de l'etage 3 porte sur `engine/**` entier.",
}

ENGINE = PYDIR / "engine"
FOYER = ("sort_units_by_damage_utility", "first_by_damage_utility")


# --------------------------------------------------------------------------------------------
# Substrat MINIMAL -- juste ce que `_target_utility` lit : `state.get_entity(id)` puis
# `get_component(HealthComponent)`. Aucun board : les etages 1 et 2 mesurent le TIE-BREAK et le
# CABLAGE, pas la valeur du bonus (qui est, elle, la mesure live du probe).
# --------------------------------------------------------------------------------------------
class _Health:
    def __init__(self, hp: int):
        self.hp, self.hp_max = hp, hp


class _Entity:
    def __init__(self, hp: int):
        self._hc = _Health(hp)

    def get_component(self, cls):
        return self._hc if cls is HealthComponent else None


class _State:
    board = None
    effects = None

    def __init__(self, hps: dict):
        self._e = {int(k): _Entity(int(v)) for k, v in hps.items()}

    def get_entity(self, eid):
        return self._e.get(int(eid))


# --------------------------------------------------------------------------------------------
# [1] TIE-BREAK = ORDRE SOURCE
# --------------------------------------------------------------------------------------------
# Chaque ordre source est choisi NON TRIE par id : c'est la seule facon de separer « stable sur
# l'ordre source » de « re-trie par id ». `L1` est l'ordre source reel du regime mesure.
ORDRES_SOURCE = [
    [81, 83, 79, 85],          # regime L1 (cube-lex ASC), l'ordre que le natif rend tel quel
    [85, 79, 83, 81],
    [83, 85, 81, 79],
    [79, 85, 83, 81],
]


@pytest.mark.parametrize("src", ORDRES_SOURCE)
def test_tie_break_rend_l_ordre_source_tel_quel(src):
    """A utilite EGALE, `sort_units_by_damage_utility` rend l'ordre SOURCE -- jamais l'ordre `id`."""
    st = _State({eid: 400000 for eid in src})
    got = DU.sort_units_by_damage_utility(st, list(src), 1197, 1197)
    assert got == list(src), "tie-break: attendu l'ordre SOURCE %s, obtenu %s" % (src, got)


def test_tie_break_n_est_pas_l_ordre_par_id():
    """Contre-epreuve NON DEGENERE : sur un ordre source qui n'est PAS croissant, le resultat doit
    differer de `sorted(ids)`. Sans cette assertion, l'etage 1 passerait aussi avec l'ancien code
    des que l'ordre source se trouve etre deja trie."""
    src = [85, 79, 83, 81]
    assert src != sorted(src), "temoin degenere : cet ordre source est deja trie par id"
    st = _State({eid: 400000 for eid in src})
    got = DU.sort_units_by_damage_utility(st, list(src), 1197, 1197)
    assert got != sorted(src), "tie-break: le port a RE-TRIE par id (%s)" % (got,)


def test_first_prend_le_premier_de_l_ordre_source():
    """`First(SortUnitsByDamageUtility(...), 1)` = l'argmax STRICT sur l'ordre SOURCE."""
    src = [85, 79, 83, 81]
    st = _State({eid: 400000 for eid in src})
    assert DU.first_by_damage_utility(st, list(src), 1197, 1197) == 85


def test_l_utilite_reste_discriminante_quand_les_pv_different():
    """Garde-fou d'auto-controle : le tri N'EST PAS devenu un simple passe-plat. Une cible dont les
    PV sont dans la plage de degat (kill) doit remonter DEVANT, meme placee en dernier."""
    src = [85, 79, 83, 81]
    st = _State({85: 400000, 79: 400000, 83: 400000, 81: 900})       # u81 mourra
    got = DU.sort_units_by_damage_utility(st, list(src), 1197, 1197)
    assert got[0] == 81, "l'utilite ne discrimine plus : %s" % (got,)


# --------------------------------------------------------------------------------------------
# [2] LA PART POSITIONNELLE DE LA CLE
# --------------------------------------------------------------------------------------------
def test_sans_owner_les_bornes_sont_inchangees():
    """`owner_id is None` -> le port ne devine AUCUNE geometrie."""
    assert DU.positional_damage_range(_State({}), None, 79, 1197, 2000) == (1197, 2000)


def test_avec_owner_les_deux_feuilles_positionnelles_sont_appelees(monkeypatch):
    """`positional_damage_range` delegue aux DEUX fonctions NOMMEES du moteur, avec le couple
    (attaquant, cible) -- c'est ce qui rend la plage differente d'une cible a l'autre.

    Le patch vise `damage_utility._damage_model.<nom>` : le foyer lie le MODULE (forme B), donc un
    `setattr` sur le module MORD. S'il repassait a `from ..damage_model import ...` au niveau
    module, ce test rougirait -- c'est voulu."""
    vus = []

    def _elev(state, mods, att, tgt):
        vus.append(("elevation", att, tgt))
        mods.pct_list.append((1.5, None))

    def _trench(state, mods, att, tgt):
        vus.append(("trench", att, tgt))

    monkeypatch.setattr(DU._damage_model, "apply_elevation_bonus", _elev)
    monkeypatch.setattr(DU._damage_model, "apply_trench_reduction", _trench)
    got = DU.positional_damage_range(_State({}), 77, 85, 1000, 2000)
    assert vus == [("elevation", 77, 85), ("trench", 77, 85)], vus
    assert got == (1500, 3000), got


def test_l_utilite_lit_la_plage_positionnelle(monkeypatch):
    """La plage POSITIONNELLE entre bien dans `_target_utility`, donc dans la cle de tri : la seule
    cible qui recoit le bonus remonte en TETE alors que l'ordre source la met en DERNIER."""
    src = [81, 83, 79, 85]

    def _elev(state, mods, att, tgt):
        if int(tgt) == 85:                       # regime L2 : u85 est la seule plus BASSE
            mods.pct_list.append((1.5, None))

    monkeypatch.setattr(DU._damage_model, "apply_elevation_bonus", _elev)
    monkeypatch.setattr(DU._damage_model, "apply_trench_reduction",
                        lambda state, mods, att, tgt: None)
    st = _State({eid: 400000 for eid in src})
    got = DU.sort_units_by_damage_utility(st, list(src), 1197, 1197, owner_id=77)
    assert got == [85, 81, 83, 79], got          # u85 en tete, le RESTE dans l'ordre SOURCE


# --------------------------------------------------------------------------------------------
# [3] LE CABLAGE `owner_id=` -- perimetre DERIVE, jamais une liste blanche
# --------------------------------------------------------------------------------------------
def _appels_du_foyer():
    """Tous les appels a `sort_units_by_damage_utility` / `first_by_damage_utility` dans
    `engine/**`, DERIVES de l'AST -- pas une liste ecrite a la main (elle ne pourrait pas montrer
    le call-site qu'on a oublie d'y inscrire)."""
    out = []
    for f in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:                                   # pragma: no cover
            pytest.fail("fichier non parsable : %s" % f)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            nom = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if nom in FOYER:
                out.append((f.relative_to(PYDIR).as_posix(), node.lineno, nom,
                            [k.arg for k in node.keywords]))
    return out


def test_le_perimetre_du_balayage_est_non_vide():
    """Un balayage qui ne trouve RIEN passerait pour vert. On assertionne son propre non-vide, et
    le compte MESURE des call-sites au moment de la tranche (4 : Doombolt, FinalJustice,
    AncestralFortune, KillMaimBurn) comme PLANCHER -- en ajouter est permis, en perdre non."""
    appels = _appels_du_foyer()
    assert len(appels) >= 4, "balayage degenere : %d call-site(s) trouve(s)" % len(appels)


def test_chaque_call_site_passe_owner_id():
    """Un call-site sans `owner_id=` retombe sur la cle CONSTANTE d'avant #494-r1, en silence."""
    manquants = [a for a in _appels_du_foyer() if "owner_id" not in a[3]]
    assert not manquants, ("call-site(s) du tri par utilite SANS owner_id= : %s"
                           % ["%s:%d %s" % (m[0], m[1], m[2]) for m in manquants])


def test_le_foyer_ne_retrie_pas_par_id():
    """Garde de NON-REGRESSION textuelle sur le foyer : le `sorted(int(c) for c in candidates)`
    supprime ne doit pas revenir. Il ne cassait rien -- il rendait juste une 4e cible differente
    de celle du natif, ce qu'aucun test ne voyait."""
    src = (ENGINE / "runner" / "operations" / "damage_utility.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name not in FOYER:
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "sorted"
                    and not node.keywords):
                pytest.fail("%s: `sorted(...)` SANS cle = re-tri par id, ligne %d"
                            % (fn.name, node.lineno))
