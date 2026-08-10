"""#883-r1 -- GARDE de l'ARRONDI de `DakkaDakkaDakkaAbility$$GetHealthToLose`. OFFLINE.

LE SITE. `entities/abilities/active_ability.py::DakkaDakkaDakkaAbility.get_health_to_lose` etait le
DERNIER `// 100` executable non confronte du moteur (#883 avait corrige `ice_crit_damage_addition`).
Le natif, relu au decompile `rnca9r7q6c` :

    IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose
        amount     = DSLFormulas.StatAmount(owner@+0x48, 5 = Health, 2)
        percentage = DSLFormulas.ConfigConst(0x4f = AbilityConstantType.healthPct, this+0x60)
        return       DSLFormulas.PercentageOf(amount, percentage, roundingRule: 0)

et `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` ventile `1` = `Fix64.Ceiling`, `2` =
`Fix64.Floor`, **tout le reste** = `Fix64.Round`. Le `0` du 4e argument tombe donc dans le dernier
bras -- demi-vers-le-PAIR (`FixMath.NET.Fix64$$Round` avec `midpointRounding == 0` : la partie
entiere si la fraction est `< 0.5`, `+1` si `> 0.5`, et le PAIR sur `0x80000000` exact).

POURQUOI CE FICHIER EXISTE, ET PAS SEULEMENT LE CORRECTIF. Le floor precedent a tenu parce que la
mesure qui l'attestait n'etait PAS DISCRIMINANTE (#883 : `probe_45f --case crit` forcait `cd = 700`,
et `700 x 25 / 100 = 175.0` n'a aucune partie fractionnaire -- floor et round y COINCIDENT).
L'etage 3 ci-dessous ne se contente donc pas de comparer le port a une attente : il ASSERTIONNE que
son propre jeu de temoins SEPARE les trois regles, et il le fait dans les deux sens du
demi-vers-le-pair (un temoin qui monte, un temoin qui reste). Sans cela, un port en `round-half-up`
passerait pour juste.

CINQ ETAGES :
  1. l'ORDINAL du call-site (`0x4f`), fige a la valeur LUE ;
  2. le `pct` vient bien du GAMECONFIG et n'est pas nul (sans quoi le site rend `None` et tout ce
     fichier serait vert sur du vide) ;
  3. la VALEUR, sur un jeu de temoins PROUVE discriminant ;
  4. la PROVENANCE (AST) : le site appelle le foyer d'arrondi et n'ecrit plus de division entiere ;
  5. le MUTANT : forcer le mode `2` (Floor) doit faire tomber l'etage 3 -- sans lui, l'etage 3
     serait vert pour un port qui ne consulte aucun mode.

ASCII only (cp1252).
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from fractions import Fraction
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig as GC                                                      # noqa: E402
from engine.dsl.base import _round_fix64                                     # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType        # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration   # noqa: E402
from engine.entities.abilities.active_ability import DakkaDakkaDakkaAbility  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType            # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": (),
    "build": True,
    "toujours": True,
    "raison": (
        "`chemins` VIDE, et c'est MESURE : `probe_486r15 --proposer` rend RIEN A DECLARER hors "
        "de la cascade -- la fermeture d'imports de ce fichier (479 modules, dont le site "
        "`entities/abilities/active_ability.py`, le foyer `dsl/base.py::_round_fix64` et le mirror "
        "`entities/ability_constant_type.py`) tient entierement dans la cascade DERIVEE du foyer, "
        "qu'on ne redeclare pas (#531). D'ou `toujours: True` : un perimetre vide avec "
        "`toujours: False` ne serait JAMAIS rejoue, et ce fichier est offline et court (13 tests, "
        "~3 s, aucun runner, aucun RPC). "
        "`build: True` parce qu'il FIGE un ordinal du binaire au site -- `ConfigConst(0x4f)` = "
        "`AbilityConstantType.healthPct`, le litteral que passe "
        "`DakkaDakkaDakkaAbility$$GetHealthToLose`. `probe_313` compare le mirror au build et "
        "redeviendrait vert apres un renumerotage ; ce cliquet-ci garde la valeur ECRITE, donc il "
        "doit se rejouer au changement de build. "
        "Ce qu'il prouve, et que rien d'autre ne voit : le 4e argument `roundingRule` du call-site "
        "natif vaut `0`, donc `Fix64.Round` (demi-vers-le-PAIR) et NON le `// 100` que le port "
        "ecrivait -- avec un jeu de temoins dont la DISCRIMINANCE est elle-meme assertionnee, "
        "contre floor ET contre half-up."),
}

#: Le call-site natif passe `0` -- le bras `Fix64.Round` de `AAmountFormula$$RoundFix64Result`.
ROUNDING_RULE_LU = 0

#: `max_hp` des temoins. Choisis pour couvrir les QUATRE regimes de la fraction `3*hp/20` :
#: nulle (1000), `< 0.5` (1234), `> 0.5` (1237), et `== 0.5` DANS LES DEUX SENS -- 10 et 50 montent
#: vers le pair, 30 et 70 y restent. Ce sont ces deux derniers qui separent half-even de half-up.
TEMOINS = (1000, 1234, 1237, 10, 30, 50, 70)


def _ability(level: int = 50) -> DakkaDakkaDakkaAbility:
    """L'ability sur sa config GAMECONFIG reelle. `caster = None` : `get_health_to_lose` ne lit que
    la config et son argument, et le niveau est fourni par l'`AbilityState` per-ability (#100)."""
    a = GC.ability("DakkaDakkaDakka") or {}
    cfg = AbilityConfiguration("DakkaDakkaDakka", a.get("variables") or {},
                               a.get("constants") or {})
    return DakkaDakkaDakkaAbility(int(ActiveAbilityType.DakkaDakkaDakka), None, cfg,
                                  {"level": int(level)})


def _pct() -> int:
    return int((GC.ability("DakkaDakkaDakka") or {}).get("constants", {}).get("healthPct") or 0)


def _floor(hp: int, pct: int) -> int:
    return (hp * pct) // 100


def _half_up(hp: int, pct: int) -> int:
    q = Fraction(hp * pct, 100)
    return int(q + Fraction(1, 2)) if q >= 0 else -int(-q + Fraction(1, 2))


def _half_even(hp: int, pct: int) -> int:
    return _round_fix64(Fraction(hp * pct, 100), ROUNDING_RULE_LU)


# ================================================================== 1. ORDINAL DU CALL-SITE

def test_l_ordinal_du_config_const_est_celui_lu_au_decompile():
    """`ConfigConst(0x4f)` -- l'ordinal est fige a la valeur MESUREE, et il est nomme par son enum.

    `probe_313` compare le mirror au build et redeviendrait VERT apres un renumerotage ; ce test-ci
    est le cran qui attrape le glissement d'un ordinal ECRIT AU SITE (cf. CLAUDE.md)."""
    assert int(AbilityConstantType.healthPct) == 0x4f
    assert AbilityConstantType.healthPct.name == "healthPct"


# ================================================================== 2. LE SUBSTRAT N'EST PAS VIDE

def test_le_pourcentage_vient_du_gameconfig_et_n_est_pas_nul():
    """Sans `healthPct`, `get_health_to_lose` rend `None` et TOUS les etages suivants seraient verts
    sur du vide. On exige donc la valeur, et par le chemin REEL du port.

    Le natif appelle `ConfigConst` (donc `GetNumberConstant`) d'emblee ; le port passe par
    `get_variable_for_level`, qui retombe sur les CONSTANTES a defaut de variable. `healthPct` vit
    dans `constants` pour cette ability -- c'est cette retombee qui le rend, et elle est ici
    exercee."""
    pct = _pct()
    assert pct > 0, ("`DakkaDakkaDakka.constants.healthPct` est absent ou nul : le site rend `None` "
                     "et ce fichier ne garde plus rien.")
    ab = _ability()
    assert ab.config is not None
    assert ab.config.get_variable_for_level("healthPct", ab.level, 0) == pct, (
        "le port ne lit plus `healthPct` par la retombee CONSTANTES de `get_variable_for_level`.")


# ================================================================== 3. LA VALEUR (temoin discriminant)

def test_le_jeu_de_temoins_separe_bien_les_trois_regles():
    """CONTRE-CONTROLE, ET IL EST LA RAISON D'ETRE DU FICHIER. Un temoin non discriminant valide
    n'importe quel arrondi -- c'est exactement ce qui a maintenu le floor en place (#883, `cd = 700`
    -> `175.0`). On exige donc, SUR CE JEU-CI : au moins un temoin ou FLOOR diverge du natif, et au
    moins un ou HALF-UP diverge. Le second est le plus facile a oublier : sans lui, un port en
    demi-vers-le-HAUT serait indistinguable."""
    pct = _pct()
    vs_floor = [hp for hp in TEMOINS if _floor(hp, pct) != _half_even(hp, pct)]
    vs_half_up = [hp for hp in TEMOINS if _half_up(hp, pct) != _half_even(hp, pct)]
    assert vs_floor, ("aucun temoin ne separe FLOOR de `Fix64.Round` : le jeu `TEMOINS` ne "
                      "discrimine plus rien (regarder `healthPct`, qui a pu changer).")
    assert vs_half_up, ("aucun temoin ne separe HALF-UP de `Fix64.Round` : le demi-vers-le-PAIR "
                        "n'est pas exerce, un port en demi-vers-le-haut passerait pour juste.")


@pytest.mark.parametrize("hp", TEMOINS)
def test_le_site_rend_l_arrondi_du_natif(hp):
    """`PercentageOf(hp_max, healthPct, roundingRule: 0)` = `Fix64.Round` demi-vers-le-pair.

    Les deux arrondis intermediaires de `PercentageOf$$CalculateInternal` (`x/100*100 -> Round
    -> /100`, deux fois) sont NEUTRES pour des operandes entieres -- `Fraction` les represente
    exactement. Seul l'arrondi FINAL est observable, et c'est celui qu'on garde ici."""
    pct = _pct()
    assert _ability().get_health_to_lose(hp) == _half_even(hp, pct), (
        "hp_max=%d : le port rend %r, le natif %d (floor aurait rendu %d, half-up %d)"
        % (hp, _ability().get_health_to_lose(hp), _half_even(hp, pct),
           _floor(hp, pct), _half_up(hp, pct)))


def test_un_pourcentage_nul_rend_None_et_pas_zero():
    """Le `if pct` du site est CONSERVE : `None` = « cette ability n'a pas de cout en PV », que le
    playbook distingue d'un cout NUL (il n'emet alors aucun `ProbableDamageEvent` SELF)."""
    cfg = AbilityConfiguration("DakkaDakkaDakka", {}, {})
    ab = DakkaDakkaDakkaAbility(int(ActiveAbilityType.DakkaDakkaDakka), None, cfg, {"level": 50})
    assert ab.get_health_to_lose(10_000) is None


# ================================================================== 4. PROVENANCE (AST)

def test_le_site_passe_par_le_foyer_d_arrondi_et_n_ecrit_plus_de_division_entiere():
    """PROVENANCE, par AST et pas par grep : une recopie LOCALE equivalente serait indistinguable en
    VALEUR aujourd'hui (meme contre-epreuve qu'en #462/#643/#646), et le risque qu'elle porte est la
    divergence FUTURE -- le jour ou `RoundFix64Result` gagne un bras."""
    src = textwrap.dedent(inspect.getsource(DakkaDakkaDakkaAbility.get_health_to_lose))
    tree = ast.parse(src)
    appels = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_round_fix64" in appels, (
        "le site n'appelle plus `_round_fix64` : l'arrondi est recompose localement, donc il "
        "cessera de suivre `AAmountFormula$$RoundFix64Result`.")
    divisions = [n for n in ast.walk(tree)
                 if isinstance(n, ast.BinOp) and isinstance(n.op, ast.FloorDiv)]
    assert not divisions, (
        "le site a de nouveau une division ENTIERE : c'est le FLOOR que #883-r1 a retire, et il "
        "n'est fidele que si le call-site natif passe `roundingRule = 2` -- ce qu'il ne fait pas.")


# ================================================================== 5. LE MUTANT

def test_forcer_le_mode_Floor_fait_tomber_le_temoin(monkeypatch):
    """LE MUTANT : si le port lisait `2` (Floor) au lieu du `0` du call-site, l'etage 3 doit tomber.

    Sans cet etage, un port qui ne consulterait AUCUN mode (et rendrait la bonne valeur par hasard
    sur ce jeu) serait indistinguable. On substitue le foyer `_round_fix64` DANS LE MODULE qui le
    consomme (forme B : le site le resout par son binding de module a chaque appel)."""
    import engine.entities.abilities.active_ability as AA
    pct = _pct()
    divergents = [hp for hp in TEMOINS if _floor(hp, pct) != _half_even(hp, pct)]
    assert divergents, "aucun temoin divergent : le mutant ne pourrait rien montrer."
    monkeypatch.setattr(AA, "_round_fix64", lambda value, mode: _round_fix64(value, 2))
    vus = [hp for hp in divergents if _ability().get_health_to_lose(hp) != _half_even(hp, pct)]
    assert vus == divergents, (
        "le mutant Floor ne change RIEN sur %r : le site ne consulte pas le foyer d'arrondi."
        % (sorted(set(divergents) - set(vus)),))
