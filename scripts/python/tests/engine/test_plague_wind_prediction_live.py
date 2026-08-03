"""PlagueWind (1035) et MortarionsPlagueWind (1093) -- face PREDICTION, les TROIS batchs (#27-r5-r1).

CE QUE CE FICHIER GARDE (et pourquoi rien n'y passe par accident) :

A. **LES TROIS BATCHS EXISTENT ET PORTENT CHACUN SA BASE.** Les deux
   `<X>PlagueWindPlaybook$$MakeDamagePredictions` enchainent trois
   `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` (un par vague, avec sa formule et le
   MEME `GetHits()`) puis `AddRange` des trois ; le port n'en rendait qu'UN. La garde est un accord
   BIT-A-BIT avec `aiPlaybookPredict` (le `MakeDamagePredictions` NATIF) sur la LISTE ENTIERE
   d'events, cible par cible et champ par champ. La geometrie a trois anneaux (T / voisin de T /
   voisin du voisin) rend les trois batchs SEPAREMENT observables, parce que les trois plages de
   degat de la config different (1093 : 1109-1385 / 1662-1939 / 2770-3878).
B. **LE FACTEUR `Summon` VAUT 2, ET IL EST LU.** `MortarionsPlagueWindAbility$$GetDamage{1,2,3}` =
   `If(HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon), Multiply(<avg>, <DSLFormulas+0x28>),
   <avg>)`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor` ecrit `+0x28 = Direct(2)` (meme classe
   et meme ctor que `DSLFormulas$$Direct`). L'i2 (« Summons take double damage ») ne le PROUVAIT
   pas : la constante vient du ctor, pas du texte.
C. **LE QUIRK : le `HasTrait` porte sur la CIBLE PRINCIPALE, pas sur l'unite frappee.**
   `GenerateMultiHitAttackPredictions` evalue sa formule **une seule fois, HORS de sa boucle**, sur
   l'`AbilityEntities` du message (`target = param_4`). Deux bras live le tranchent dans les deux
   sens : cible `Summon` -> les TROIS vagues sont doublees, y compris sur des unites qui ne sont pas
   des summons ; voisin `Summon` et cible ordinaire -> AUCUNE ne l'est, pas meme celle du summon.
D. **1035 N'A PAS le facteur.** Son `d_i` est `MinMaxDamage{,2,3}Average` NUE
   (`StranglethornCannonAbility$$GetDamageAmountMain` / `$$GetDamageAmountAdjacent` /
   `PlagueWindAbility$$GetDamage3`). Les deux abilities sont mesurees sur le MEME etat, dans les
   MEMES bras : si le port appliquait le facteur aux deux, 1035 rougirait sur `summon_T`.
E. **LES MUTATIONS DEBORDENT ZERO.** `waves` (pas de batch 2/3) rougit dans TOUS les bras ;
   `summon` (facteur retire) rougit sur `summon_T` SEUL ; `quirk` (formule evaluee par unite
   frappee) rougit sur `summon_T` ET `summon_V` mais pas sur `plain` ni `wide`. Une mutation qui
   rougirait partout ne discriminerait rien.
F. **La structure de la formule et l'arrondi, OFFLINE** -- sans runner.
G. **LA MULTIPLICITE DANS UNE VAGUE** (bras `wide`, geometrie DERIVEE du `boardGraph` vivant) :
   DEUX unites en vague 2, une en vague 3, soit QUATRE events dont deux partagent la base de la
   vague 2. Les trois bras `line` ne peuplent jamais une vague de plus d'une unite -- un port qui
   emettrait un event par VAGUE au lieu d'un par UNITE y serait indiscernable.

CE QUI N'EST PAS COUVERT, ET POURQUOI (dit plutot que masque) :

* **Le `hits_override` n'est pas discrimine LIVE.** `AActiveAbility$$GetHits` est le LITTERAL
  `GetNumberConstant(0x2f = nrOfHits)` ; le chemin generique du port passe par
  `GetDefaultAttackHits(nrOfHits, ExtraHits[, ExtraHitsMelee])`, qui AJOUTE la stat `ExtraHits` du
  caster. Les deux coincident tant que `ExtraHits == 0`, et `ExtraHits` (StatType 17) n'a AUCUN
  champ dans `BC.Units` -- il ne vient que d'un effet, donc `--unit-stat` ne l'atteint pas. L'axe
  est garde OFFLINE (`test_the_hits_are_the_literal_constant_not_the_default_attack_hits`), et le
  correctif est du meme mold que `_stikkbomb_inputs` / `_ramming_speed_inputs`, tous deux
  confrontes live sur leur propre tranche.
* **Le `param_8` de 1035 vs 1093.** 1093 passe `Nullable(AActiveAbility$$GetDamageProfile)`
  (`GetValueOrDefault(-1)`), 1035 passe le `Nullable` BRUT d'`AbilityConfiguration$$GetDamageProfile`.
  Les deux configs portent `damageProfile = Psychic` : la distinction est structurellement
  INOBSERVABLE ici et aucun override n'est pose. Elle ne le deviendrait que sur une config SANS
  `damageProfile`, regime qu'aucune des deux n'a.
* **Le masque `3` de `SelectUniqueUnits`** (vivante ET sans le flag `0x11 NotTargetable`) : residu
  commun a tous les sets AoE portes, aucun substrat sur la face prediction.

ASCII only.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                             # noqa: E402
import probe_27_r5_r1_plague_wind_prediction as PB                                  # noqa: E402
from engine.dsl.base import Const, DslContext, _round_fix64                         # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration    # noqa: E402
from engine.entities.abilities.active_ability import (                              # noqa: E402
    AActiveAbility, _PREDICTION_MINMAX_AVERAGE)
from engine.entities.formulas import Half, If, Multiply, Sum                        # noqa: E402
from engine.entities.stats import StatType                                          # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                             # noqa: E402
from engine.entities.triggers import HasTrait                                       # noqa: E402
from engine.entities.unit_context import UnitContext                                # noqa: E402
from engine.playbook.prediction import abilities as PA                              # noqa: E402
from engine.playbook.prediction import plague_wind as PW                            # noqa: E402

PLAGUE_WIND = PB.PW            # 1035
MORTARIONS = PB.MPW            # 1093


# ------------------------------------------------------------------------- F : la structure, OFFLINE

def test_both_abilities_are_registered_on_both_tables():
    """Un batch principal SANS ses entrees, ou des vagues SANS leur handler, se degrade en
    SILENCE (moins d'events / la mauvaise base) : les deux tables se gardent ensemble."""
    for aid in (PLAGUE_WIND, MORTARIONS):
        assert PA._MAKE_DMG_INPUT_OVERRIDES.get(aid) is PA._plague_wind_inputs, (
            "%d n'a plus ses entrees de batch principal -- le port reprendrait `get_special_hits` "
            "(qui ajoute `ExtraHits`) et, pour 1093, perdrait le facteur `Summon`" % aid)
        assert PA._MAKE_DMG_EXTRA_EVENTS.get(aid) is PA._plague_wind_wave_events, (
            "%d n'emet plus ses vagues 2 et 3 -- le port retombe a UN event (l'ecart mesure en "
            "#27-r5 : `u_full` 1.1220 contre 13.2764)" % aid)


def test_the_wave_variables_are_the_three_native_pairs():
    """`AActiveAbility$$MinMaxDamage{,2,3}Average` lisent `(0xc,0xd)`, `(0x36,0x37)`, `(0x38,0x39)`
    = `(minDmg,maxDmg)`, `(minDmg_2,maxDmg_2)`, `(minDmg_3,maxDmg_3)`. Les six existent en config
    pour les DEUX abilities -- sans quoi une vague rendrait une base nulle, donc aucun event."""
    assert PW.WAVE_DAMAGE_VARS == (("minDmg", "maxDmg"), ("minDmg_2", "maxDmg_2"),
                                   ("minDmg_3", "maxDmg_3"))
    for name in ("PlagueWind", "MortarionsPlagueWind"):
        variables = (GC.ability(name) or {}).get("variables") or {}
        for pair in PW.WAVE_DAMAGE_VARS:
            for key in pair:
                assert variables.get(key), "%s : variable %s absente de la config" % (name, key)


def test_1035_takes_the_bare_average_and_1093_wraps_it_in_the_summon_if():
    """La difference de FORME entre les deux `GetDamage`, lue au decompile."""
    bare = PW.wave_damage_formula(PLAGUE_WIND, 1994, 2493)
    assert isinstance(bare, Half) and isinstance(bare.a, Sum), (
        "1035 : `StranglethornCannonAbility$$GetDamageAmountMain` forwarde a "
        "`MinMaxDamageAverage` = `Half(Sum(Direct(mn), Direct(mx)), 0)`, sans enveloppe")
    wrapped = PW.wave_damage_formula(MORTARIONS, 1109, 1385)
    assert isinstance(wrapped, If), (
        "1093 : `MortarionsPlagueWindAbility$$GetDamage1` est un `DSLFormulas$$If`")
    assert isinstance(wrapped.cond, HasTrait)
    assert int(wrapped.cond.trait) == int(UnitTrait.Summon) == 2
    assert isinstance(wrapped.a, Multiply) and isinstance(wrapped.b, Half), (
        "branche VRAIE = `Multiply(<avg>, <DSLFormulas+0x28>)`, branche FAUSSE = `<avg>`")
    assert isinstance(wrapped.a.b, Const) and wrapped.a.b.value == 2, (
        "`<DSLFormulas+0x28>` est `Direct(2)` -- LU dans `DSLFormulas$$.ctor` (qui alloue "
        "`+0x18 Direct(0)`, `+0x20 Direct(1)`, `+0x28 Direct(2)`, `+0x30 Direct(100)`, "
        "`+0x38 Direct(-1)`), jamais deduit du texte i2")


@pytest.mark.parametrize("mn, mx", [(29, 38), (35, 48), (20, 27), (1994, 2493), (1109, 1385)])
def test_the_average_rounds_half_to_even_like_get_damage(mn, mx):
    """`Half` -> `DivideAmount$$Calculate` -> `RoundFix64Result(., 0)` = demi-vers-le-PAIR : la
    MEME primitive que `AActiveAbility.get_damage()` pour les abilities du registre (a), dont 1035
    et 1093 font partie. Un port qui tronquerait rendrait une unite de moins sur `3 mod 4`."""
    ctx = DslContext()
    want = _round_fix64(Fraction(mn + mx, 2), 0)
    assert PW.min_max_damage_average(mn, mx).evaluate(ctx) == want
    for aid in (PLAGUE_WIND, MORTARIONS):
        assert aid in _PREDICTION_MINMAX_AVERAGE
        cfg = AbilityConfiguration(name="synthetique", variables={"minDmg": [mn], "maxDmg": [mx]},
                                   constants={})
        ab = AActiveAbility(ability_type=aid, caster=UnitContext(entity_id=1), config=cfg,
                            ability_state={"level": 1, "multiplier": 100})
        assert ab.get_damage() == want, (
            "le foyer generique et la formule de vague doivent rendre la MEME valeur sur la vague 1 "
            "hors facteur -- sinon le port aurait DEUX moyennes")


def _summon_ctx(main_is_summon: bool, other_is_summon: bool) -> DslContext:
    """Contexte MINIMAL : la cible principale et une autre unite, chacune `Summon` ou non."""
    main, other = {"id": 1}, {"id": 2}
    summons = ({1} if main_is_summon else set()) | ({2} if other_is_summon else set())
    return DslContext(units=[main, other], caster={"id": 9}, target=main,
                      has_trait=lambda u, t: (u or {}).get("id") in summons
                      and int(t) == int(UnitTrait.Summon))


def test_the_summon_factor_reads_the_MAIN_target_only():
    """C, offline -- l'operande du `HasTrait` est le selecteur `Target`, donc la cible du message.
    Une autre unite `Summon` ne change RIEN, et c'est ce que le bras live `summon_V` mesure."""
    avg = _round_fix64(Fraction(1109 + 1385, 2), 0)
    f = PW.wave_damage_formula(MORTARIONS, 1109, 1385)
    assert f.evaluate(_summon_ctx(False, False)) == avg
    assert f.evaluate(_summon_ctx(False, True)) == avg, (
        "une unite `Summon` AUTRE que la cible a change la base -- le port lirait le trait de "
        "l'unite frappee, ce que le decompile refute (formule evaluee HORS boucle)")
    assert f.evaluate(_summon_ctx(True, False)) == 2 * avg
    assert PW.wave_damage_formula(PLAGUE_WIND, 1109, 1385).evaluate(_summon_ctx(True, True)) == avg, (
        "1035 n'a AUCUN facteur `Summon` : ses trois `d_i` sont les `MinMaxDamage*Average` nues")


def test_the_hits_are_the_literal_constant_not_the_default_attack_hits():
    """`AActiveAbility$$GetHits` = `GetNumberConstant(0x2f = nrOfHits)`, LITTERAL. Le chemin
    generique (`get_special_hits`) y AJOUTE la stat `ExtraHits` du caster -- que ce playbook
    n'ajoute pas. L'axe n'est pas confrontable live (`ExtraHits` n'a aucun champ `BC.Units` : il ne
    vient que d'un effet), il est donc garde ICI."""
    caster = UnitContext(entity_id=1)
    caster.stats.set_stat_override(int(StatType.EXTRA_HITS), 2)
    for aid, name in ((PLAGUE_WIND, "PlagueWind"), (MORTARIONS, "MortarionsPlagueWind")):
        cfg = AbilityConfiguration.from_gameconfig(name, GC.ability(name))
        ab = AActiveAbility(ability_type=aid, caster=caster, config=cfg,
                            ability_state={"level": 50, "multiplier": 100})
        literal = int((cfg.constants or {}).get("nrOfHits"))
        got = PW.main_batch_inputs(scene=None, caster_id=1, target_id=2, ab=ab, cfg=cfg)
        assert got.get("hits_override") == literal
        assert ab.get_special_hits(is_melee=False) == literal + 2, (
            "le chemin generique doit bien DIFFERER du litteral quand `ExtraHits > 0` -- sinon "
            "cette garde ne garderait rien")


def test_main_batch_overrides_the_base_only_for_1093():
    """La vague 1 de 1035 est `MinMaxDamageAverage` nue == `ab.get_damage()` : poser un
    `base_override` la dupliquerait. Celle de 1093 porte le `If(Summon)` : sans override, une cible
    `Summon` serait sous-predite d'un facteur 2. `scene=None` -> pas de contexte DSL -> degradation
    NOMMEE (seul `hits` survit), jamais une valeur inventee."""
    for aid, name in ((PLAGUE_WIND, "PlagueWind"), (MORTARIONS, "MortarionsPlagueWind")):
        cfg = AbilityConfiguration.from_gameconfig(name, GC.ability(name))
        ab = AActiveAbility(ability_type=aid, caster=UnitContext(entity_id=1), config=cfg,
                            ability_state={"level": 50, "multiplier": 100})
        got = PW.main_batch_inputs(scene=None, caster_id=1, target_id=2, ab=ab, cfg=cfg)
        assert "base_override" not in got, "contexte absent -> aucune base inventee"
    assert PW.MORTARIONS_PLAGUE_WIND == MORTARIONS and PW.PLAGUE_WIND == PLAGUE_WIND


# --------------------------------------------------------------------------- A-E : le LIVE

@pytest.fixture(scope="module")
def arms():
    """Un runner PAR BRAS (chaque unite ne fait qu'UN deplacement), dispose au fil de l'eau. Chaque
    bras mesure les DEUX abilities sur le MEME etat -- c'est ce qui fait de 1035 le temoin de 1093."""
    out = {}
    for name in sorted(PB.ARMS):
        out[name] = PB.run_arm(name)
        try:
            PB.L._rpc("disposeRunner", [{"runnerId": out[name]["rid"]}])
        except Exception:                                   # noqa: BLE001
            pass
    return out


def test_native_and_port_agree_event_by_event_in_every_arm(arms):
    """A -- accord BIT-A-BIT sur la liste ENTIERE, dans les trois bras et pour les deux abilities."""
    for name, r in arms.items():
        for aid, res in r["base"].items():
            assert res["match"], (
                "bras %s / ability %d : deltas=%r missing=%r extra=%r"
                % (name, aid, res["deltas"][:6], res["missing"], res["extra"]))


def test_the_event_count_is_the_one_the_geometry_dictates(arms):
    """A -- le COMPTE. Bras `line` : T / voisin de T / voisin du voisin + un temoin LOIN -> trois
    events, le temoin exclu (borne de la chaine). Bras `wide` : DEUX voisins de T -> quatre."""
    for name, r in arms.items():
        want = PB.EXPECT_EVENTS[name]
        for aid, res in r["base"].items():
            n_nat = sum(len(v) for v in res["nat"].values())
            n_off = sum(len(v) for v in res["off"].values())
            assert n_nat == n_off == want, (
                "bras %s / ability %d : natif %d events, port %d (attendu %d)"
                % (name, aid, n_nat, n_off, want))


def test_a_wave_with_TWO_units_gives_both_the_SAME_base(arms):
    """A, GENERALISATION -- bras `wide` : la vague 2 porte DEUX unites. Le natif leur donne la MEME
    base (`MinMaxDamage2Average`), DISTINCTE de celle de la vague 1 et de celle de la vague 3.

    Les trois bras `line` ne peuvent pas voir ce point : ils ne peuplent jamais une vague de plus
    d'une unite, donc un port qui n'emettrait qu'UN event par vague (au lieu d'un par UNITE) y
    serait indiscernable. Le montage derive ses tuiles du `boardGraph` vivant -- la geometrie
    n'est pas la meme que celle des bras `line`, ce qui en fait aussi une generalisation du SET."""
    r = arms["wide"]["base"]
    for aid in (PLAGUE_WIND, MORTARIONS):
        bases = sorted(e["healthDmgMax"] for evs in r[aid]["nat"].values() for e in evs)
        assert len(bases) == 4, "bras wide : %d events, attendu 4" % len(bases)
        # 4 events = {vague1} + {vague2 x2} + {vague3} -> une valeur EXACTEMENT en double.
        doubled = [v for v in set(bases) if bases.count(v) == 2]
        assert len(doubled) == 1 and len(set(bases)) == 3, (
            "ability %d : les 4 events devraient valoir 3 valeurs distinctes dont UNE en double "
            "(les deux unites de la vague 2) -- lu %r" % (aid, bases))
        off = sorted(e["healthDmgMax"] for evs in r[aid]["off"].values() for e in evs)
        assert off == bases, "ability %d : port %r != natif %r" % (aid, off, bases)


def test_the_summon_factor_doubles_all_three_waves_of_1093_only(arms):
    """B + C + D -- la cible est un `Summon` : les TROIS vagues de 1093 doublent, y compris sur des
    unites qui n'en sont pas ; 1035, mesuree sur le MEME etat, ne bouge pas d'un point."""
    plain, summon = arms["plain"]["base"], arms["summon_T"]["base"]

    def _mx(res):
        return {t: [e["healthDmgMax"] for e in evs] for t, evs in res["nat"].items()}
    p93, s93 = _mx(plain[MORTARIONS]), _mx(summon[MORTARIONS])
    assert set(p93) == set(s93) and p93, "la grappe a change entre les deux bras"
    for t in p93:
        for a, b in zip(p93[t], s93[t]):
            assert b > a, ("1093 : la cible est `Summon` et l'event de %s n'a pas augmente "
                           "(%d -> %d)" % (t, a, b))
    p35, s35 = _mx(plain[PLAGUE_WIND]), _mx(summon[PLAGUE_WIND])
    assert p35 == s35, (
        "1035 a bouge alors que ses `d_i` sont les `MinMaxDamage*Average` NUES : le port applique "
        "le facteur `Summon` a la mauvaise ability (%r -> %r)" % (p35, s35))


def test_a_summon_that_is_not_the_target_changes_nothing(arms):
    """C -- le bras miroir : le voisin (vague 2) est `Summon`, la cible ne l'est pas. Le natif ne
    double RIEN, pas meme l'event de ce voisin. C'est la lecture naive qui tombe ici."""
    plain, sec = arms["plain"]["base"], arms["summon_V"]["base"]
    for aid in (PLAGUE_WIND, MORTARIONS):
        a = {t: [e["healthDmgMax"] for e in evs] for t, evs in plain[aid]["nat"].items()}
        b = {t: [e["healthDmgMax"] for e in evs] for t, evs in sec[aid]["nat"].items()}
        assert a == b, ("ability %d : le trait d'une unite FRAPPEE a change le degat natif -- la "
                        "formule serait evaluee par cible (%r vs %r)" % (aid, a, b))


@pytest.mark.parametrize("mutation", sorted(PB.EXPECT_MUTATION))
def test_each_mutation_reddens_exactly_where_the_re_says(arms, mutation):
    """E -- les trois mutations debordent zero : chacune rougit LA ou la RE dit, et reste VERTE
    ailleurs. Une mutation rouge partout ne discriminerait pas ce qu'elle pretend garder."""
    for name, r in arms.items():
        m = r["mutations"][mutation]
        assert m["ok"], ("bras %s / mutation %s : rouge=%s, attendu %s"
                         % (name, mutation, m["red"], m["want"]))
