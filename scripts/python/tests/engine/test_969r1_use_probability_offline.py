"""#969-r1 / #971-r2 -- CLIQUETS de la PROBABILITE d'usage (`GetUseProbability`).

CE QUE CES TESTS GARDENT, ET POURQUOI CE N'EST PAS `should_evaluate`
---------------------------------------------------------------------
`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` a deux etages, et le port les separe comme le
natif : le slot `0x1f8` `GetUseProbability` produit un `p`, le triage des trois branches le
consomme. Seul le PREMIER est confrontable -- le capteur `shouldEvaluateTrace` publie la `prob`
EXACTE passee a `NextBool`, et c'est ce que `probe_969r1_prob_confrontee.py` a mesure.

Les VALEURS figees plus bas sont donc des MESURES LIVE, pas des attentes ecrites de memoire
(seed 777 / MC1_67, deux montages, capteur arme, tour d'IA declenche par `aiDryRunAllUnits`) :

    montage SPAWN     u83 templHelbrecht CrusadeOfWrath  port 0.40  natif 0.40  ACCORD
                      u85 spaceBlackmane WarHowl         port 0.00  natif AUCUN TIRAGE   ACCORD
                      u87 orksWarboss    Waaagh          port 0.25  natif 0.25  ACCORD
    montage CONTACT   u79 templHelbrecht CrusadeOfWrath  port 0.40  natif 0.40  ACCORD
                      u81 spaceBlackmane WarHowl         port 0.75  natif 0.75  ACCORD
                      u83 orksWarboss    Waaagh          port 0.15  natif 0.15  ACCORD

⚠ LE SECOND MONTAGE N'EST PAS UN DOUBLON : il DEPLACE les unites pour amener Ragnar au contact,
seul regime ou `WarHowl` sort de son zero deterministe et entre dans la bande de TIRAGE. C'est lui
qui a exerce le compteur `n` (et trouve un vrai bug : `has_ranged_weapon` vit dans
`engine.services.battle_query`, pas `engine.battle_query`).

⚠ LE TIRAGE, LUI, N'EST PAS REPRODUCTIBLE, ET C'EST MESURE : deux executions du MEME dry-run sur le
MEME etat ont rendu `False` puis `True` pour `Waaagh` a `p = 0.25`. Aucun test ne garde donc un
resultat de tirage -- seulement la PROBABILITE.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[2]
NC = RACINE / "engine" / "playbook" / "noncomparable"

DECLENCHEUR = {
    "chemins": (
        # Le foyer des DEUX etages : la probabilite (`use_probability`) et son triage
        # (`probability_gate`). L'etage 3 balaie de surcroit TOUT `noncomparable/`.
        "scripts/python/engine/playbook/noncomparable/_base.py",
        # Les trois porteurs dont les valeurs sont FIGEES depuis une mesure live.
        "scripts/python/engine/playbook/noncomparable/crusade_of_wrath.py",
        "scripts/python/engine/playbook/noncomparable/waaagh.py",
        "scripts/python/engine/playbook/noncomparable/war_howl.py",
        # Le module qui porte `has_ranged_weapon` -- et celui qui ne doit PAS le porter :
        # l'etage 2 garde justement lequel des deux est lu.
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/battle_query.py",
        # Le capteur qui rend ces valeurs confrontables. Sa disparition ne casserait aucun test
        # d'ici, mais elle retirerait la SOURCE des chiffres figes : le declencheur le dit.
        "frida/hooks/probes/should-evaluate-trace.ts",
        "scripts/python/probe_969r1_prob_confrontee.py",
    ),
    # Ni le binaire ni `data/symbols/**` : toutes les valeurs natives sont TRANSCRITES dans les
    # docstrings du port et figees ici en litteraux. Ce fichier ne relit aucun dump.
    "build": False,
    "toujours": False,
    "raison": (
        "Perimetre BORNE et derivable : les six chemins Python sont ceux que les assertions "
        "LISENT (le foyer, les trois porteurs, et les deux modules `battle_query` dont l'etage 2 "
        "tranche lequel porte `has_ranged_weapon`). Les deux derniers chemins ne sont pas lus par "
        "une assertion : ils PRODUISENT les valeurs figees a l'etage 2 (mesure live seed 777 / "
        "MC1_67), et une derive du capteur ou du probe rendrait ces chiffres invalidables sans "
        "qu'aucun test ne rougisse -- c'est pourquoi ils sont declares LARGE plutot qu'omis."),
}


def _nc(**kw):
    from engine.playbook.noncomparable._base import NCContext

    base = dict(uid=7, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                hp_cur_by_id={}, units=[], obs_units=[])
    base.update(kw)
    return NCContext(**base)


class _Scene:
    """Le strict minimum que `use_probability` lit sur la `Scene` : le compteur de tours demarres."""

    def __init__(self, ts_by_id=None):
        self._ts = ts_by_id or {}

    def turns_started(self, uid):
        return self._ts.get(uid)


# =================================================================================================
# ETAGE 1 -- le TRIAGE `probability_gate` est le mirror EXACT des trois branches natives
# =================================================================================================

def test_etage1_les_trois_branches_natives():
    """    if (prob >= Fix64.One)  return true;
        if (prob <= Fix64.Zero) return false;
        return random.<slot 4>(prob);            // TIRAGE -> PERMISSIF assume

    Les bornes sont INCLUSIVES des deux cotes -- `>=` et `<=`, pas `>` et `<`."""
    from engine.playbook.noncomparable._base import probability_gate

    assert probability_gate(1.0) is True          # borne HAUTE inclusive
    assert probability_gate(1.5) is True
    assert probability_gate(0.0) is False         # borne BASSE inclusive
    assert probability_gate(-0.5) is False
    for p in (0.15, 0.25, 0.4, 0.5, 0.75, 0.99):  # bande OUVERTE -> permissif DECLARE
        assert probability_gate(p) is True


def test_etage1_le_non_mesure_ne_refuse_JAMAIS():
    """`None` = PAS MESURE. Le rabattre sur `0.0` prononcerait un REFUS que le natif n'a pas
    prononce, et rendrait l'ability INVISIBLE du moteur -- le trou silencieux de #967."""
    from engine.playbook.noncomparable._base import probability_gate

    assert probability_gate(None) is True


def test_etage1_le_defaut_de_la_BASE_est_Fix64_UN():
    """Les deux surcharges `IdunBattle.AI.Playbook.BasePlaybook$$GetUseProbability` rendent
    litteralement `FixMath.NET.Fix64$$op_Implicit(1)` -> un playbook qui ne surcharge rien n'est
    PAS gate. C'est ce qui rend le foyer value-preserving pour les ~95 playbooks qui l'heritent."""
    from engine.playbook.noncomparable._base import NonComparablePlaybook

    assert NonComparablePlaybook().use_probability(_nc()) == 1.0
    assert NonComparablePlaybook().should_evaluate(_nc()) is True


# =================================================================================================
# ETAGE 2 -- les VALEURS MESUREES LIVE, figees (cf. l'en-tete)
# =================================================================================================

def test_etage2_crusade_of_wrath_vaut_un_dixieme_du_max_buffe():
    """`<statics +0x08> * Fix64(GetMaxFriendlyUnitsBuffed(unit))`, ou `<statics +0x08>` est
    `Fix64.FromIntFraction(1, 10)` ECRIT par le `.cctor`. La valeur 0.4 = 4 allies buffes est celle
    que le natif a rendue sur les DEUX montages."""
    from engine.playbook.noncomparable.crusade_of_wrath import (CrusadeOfWrathPlaybook,
                                                                _USE_PROBABILITY_FACTOR)

    assert _USE_PROBABILITY_FACTOR == 0.1
    pb = CrusadeOfWrathPlaybook()
    ctx = _nc()
    for n, attendu in ((0, 0.0), (4, 0.4), (9, 0.9), (10, 1.0), (13, 1.3)):
        pb._max_friendly_units_buffed = lambda _c, _n=n: _n     # type: ignore[method-assign]
        assert pb.use_probability(ctx) == pytest.approx(attendu), n
    # Le NATIF a rendu EXACTEMENT 0.4 (les deux montages) -> `n = 4`, bande OUVERTE.
    pb._max_friendly_units_buffed = lambda _c: 4                # type: ignore[method-assign]
    assert pb.use_probability(ctx) == pytest.approx(0.4)
    assert pb.should_evaluate(ctx) is True


def test_etage2_crusade_of_wrath_canal_muet_rend_NON_MESURE():
    """`reach_nc` vide ou rayon illisible -> `None`, jamais `0.0` : un zero ferait REFUSER."""
    from engine.playbook.noncomparable.crusade_of_wrath import CrusadeOfWrathPlaybook

    pb = CrusadeOfWrathPlaybook()
    assert pb.use_probability(_nc(reach_nc=[])) is None
    assert pb.should_evaluate(_nc(reach_nc=[])) is True


def test_etage2_waaagh_vaut_un_vingtieme_du_produit():
    """`Fix64(nB * ts) * Fix64.FromIntFraction(5, 100)`. Les deux valeurs LIVE sont ici :
    `ts=1, nB=5 -> 0.25` (montage SPAWN) et `ts=1, nB=3 -> 0.15` (montage CONTACT)."""
    from engine.playbook.noncomparable.waaagh import WaaaghPlaybook, _USE_PROBABILITY_STEP

    assert _USE_PROBABILITY_STEP == 0.05
    pb = WaaaghPlaybook()
    for ts, nb, attendu in ((1, 5, 0.25), (1, 3, 0.15), (1, 1, 0.05), (5, 4, 1.0), (4, 5, 1.0)):
        ctx = _nc(scene=_Scene({7: ts}))
        pb.num_existing_units_buffed = lambda _c, _n=nb: _n     # type: ignore[method-assign]
        assert pb.use_probability(ctx) == pytest.approx(attendu), (ts, nb)


def test_etage2_waaagh_sans_compteur_de_tours_rend_NON_MESURE():
    """`ctx.scene` absente, ou `turns_started` non capte -> `None`. Meme regle que
    `_base._turns_started_gate` : on ne gate pas a l'aveugle."""
    from engine.playbook.noncomparable.waaagh import WaaaghPlaybook

    pb = WaaaghPlaybook()
    assert pb.use_probability(_nc()) is None                     # pas de `scene`
    assert pb.use_probability(_nc(scene=_Scene({}))) is None     # `scene` mais uid absent


def test_etage2_war_howl_les_trois_paliers_et_le_zero():
    """`if (mine.Count == 0) return 0` ; sinon `pct(n >= 3 ? 100 : (n == 1 ? 75 : 50))`.

    ⚠ `n == 0` ET `n == 2` valent TOUS DEUX `50` -- ce n'est PAS monotone, et c'est ce que le
    binaire ecrit (`if (n < 3) { u = (n == 1) ? 75 : 50; }`). Le port ne le << corrige >> pas.
    La valeur `0.75` (`n == 1`) est celle que le natif a rendue au montage CONTACT."""
    from engine.playbook.noncomparable.war_howl import WarHowlPlaybook

    pb = WarHowlPlaybook()
    ctx = _nc()
    pb._has_normal_attack_target_anywhere = staticmethod(       # type: ignore[method-assign]
        lambda _c, _u=None: False)
    assert pb.use_probability(ctx) == 0.0                        # ZERO DETERMINISTE
    pb._has_normal_attack_target_anywhere = staticmethod(       # type: ignore[method-assign]
        lambda _c, _u=None: True)
    for n, attendu in ((0, 0.50), (1, 0.75), (2, 0.50), (3, 1.00), (7, 1.00)):
        pb._num_buff_targets_with_attack = lambda _c, _n=n: _n   # type: ignore[method-assign]
        assert pb.use_probability(ctx) == pytest.approx(attendu), n


def test_etage2_war_howl_non_monotone_est_UNE_LECTURE():
    """Cran DEDIE au piege : `n = 0` et `n = 2` doivent rendre la MEME valeur. Un lecteur qui
    << corrigerait >> en interpolant casserait ce test, et c'est le but."""
    from engine.playbook.noncomparable.war_howl import WarHowlPlaybook

    pb = WarHowlPlaybook()
    ctx = _nc()
    pb._has_normal_attack_target_anywhere = staticmethod(       # type: ignore[method-assign]
        lambda _c, _u=None: True)
    pb._num_buff_targets_with_attack = lambda _c: 0             # type: ignore[method-assign]
    zero = pb.use_probability(ctx)
    pb._num_buff_targets_with_attack = lambda _c: 2             # type: ignore[method-assign]
    deux = pb.use_probability(ctx)
    assert zero == deux == pytest.approx(0.50)


def test_etage2_war_howl_un_seul_allie_non_mesurable_rend_NON_MESURE():
    """TRI-ETAT STRICT sur `n` : un compte PARTIEL donnerait un `p` FAUX, et `p` est justement la
    valeur que la confrontation compare au natif. Mieux vaut `None` (permissif) qu'un chiffre
    approximatif qui ferait passer une divergence pour un accord."""
    from engine.playbook.noncomparable.war_howl import WarHowlPlaybook

    pb = WarHowlPlaybook()
    ctx = _nc()
    pb._has_normal_attack_target_anywhere = staticmethod(       # type: ignore[method-assign]
        lambda _c, _u=None: True)
    pb._num_buff_targets_with_attack = lambda _c: None          # type: ignore[method-assign]
    assert pb.use_probability(ctx) is None
    assert pb.should_evaluate(ctx) is True


def test_etage2_war_howl_lit_le_BON_module_battle_query():
    """CRAN DE NON-REGRESSION du bug trouve live : `has_ranged_weapon` n'existe QUE dans
    `engine.services.battle_query`. Le port avait ecrit `engine.battle_query`, et le montage de
    SPAWN ne l'atteignait pas (WarHowl y rend `0.0` avant) -- seul le montage AU CONTACT l'a leve.
    On garde donc le FAIT (quel module porte la fonction), pas le nom de la variable."""
    import engine.battle_query as B
    import engine.services.battle_query as S

    assert hasattr(S, "has_ranged_weapon")
    assert not hasattr(B, "has_ranged_weapon"), (
        "si `engine.battle_query` gagne un `has_ranged_weapon`, RE-LIRE les deux corps avant de "
        "changer de module : ce sont deux predicats natifs distincts a deux seuils differents")
    from engine.playbook.noncomparable import war_howl
    assert war_howl.SBQ is S


# =================================================================================================
# ETAGE 3 -- le FOYER est le SEUL chemin : personne ne re-implemente le triage
# =================================================================================================

def _surcharges(nom_methode: str) -> set:
    """Les modules de `noncomparable/` qui definissent `nom_methode` dans une classe."""
    out = set()
    for f in sorted(NC.glob("*.py")):
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        for cls in [n for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)]:
            for m in cls.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == nom_methode:
                    out.add((f.name, cls.name))
    return out


def test_etage3_les_trois_porteurs_du_residu_surchargent_use_probability_PAS_should_evaluate():
    """Le natif separe les deux etages ; le port doit faire pareil, sinon la formule redevient
    INCONFRONTABLE (le capteur ne peut comparer qu'une PROBABILITE)."""
    up = _surcharges("use_probability")
    se = _surcharges("should_evaluate")
    attendus = {("crusade_of_wrath.py", "CrusadeOfWrathPlaybook"),
                ("waaagh.py", "WaaaghPlaybook"),
                ("war_howl.py", "WarHowlPlaybook")}
    assert attendus <= up, "porteurs sans `use_probability` : %s" % (attendus - up)
    assert not (attendus & se), (
        "ces playbooks re-implementent `should_evaluate` : la probabilite y redevient invisible "
        "au capteur -- %s" % (attendus & se))


def test_etage3_le_triage_natif_n_est_ecrit_QU_UNE_fois():
    """Le couple de bornes `>= 1` / `<= 0` ne doit exister QUE dans `probability_gate`. Une seconde
    ecriture se desynchroniserait de la premiere le jour ou une borne bouge -- exactement ce que
    `_base.probability_gate` a resorbe pour `DutyEternal` (#1079)."""
    src = (NC / "_base.py").read_text(encoding="utf-8")
    arbre = ast.parse(src)
    porteurs = [n for n in ast.walk(arbre)
                if isinstance(n, ast.FunctionDef) and n.name == "probability_gate"]
    assert len(porteurs) == 1, "le foyer doit etre unique, trouve %s" % len(porteurs)
    # Le NON-VIDE du recenseur est asserte : un balayage qui ne visite rien passerait pour vert.
    assert _surcharges("use_probability"), "le recenseur n'a RIEN visite -- test vacant"
