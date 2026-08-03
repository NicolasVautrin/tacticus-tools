"""MortarionsPlagueWind (1093, porteur `deathBossMortarion` npc -> GREFFE) -- face DECISION.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La GREFFE exerce bien `MortarionsPlagueWindPlaybook`.** Le seul porteur de 1093 est un npc ; le
   natif charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), donc greffer
   `[1093]` sur `deathBlightlord` (Death Guard, pool) suffit -- et le natif le PROUVE en emettant
   `ActiveAbilityMessage(1093)`. Si cette assertion tombe, « npc-only = non confrontable » redevient
   vrai et tout le reste du fichier est sans objet.
B. **Le TERME EXISTE cote natif, et il porte sur la CIBLE.** Bras A : le natif retient `T1` alors que
   son PROPRE `u_full` (`pairUtility` = `CalculateUtilityFromPredictions`, custom EXCLU) favorise
   `T2` de 0.435. Il va donc CONTRE sa preference de degat -- il n'y a aucun autre terme qui
   distingue ces deux actions (meme caster, meme tuile de cast, meme ability).
C. **C'est bien le TRAIT `Psyker` qui decide.** Bras B = bras A avec les occupants de `V1` et `V2`
   PERMUTES. Mesure : `u_full` natif est **strictement identique** dans les deux bras (13.2764 /
   13.7118) -- la permutation ne change donc RIEN au degat -- et pourtant le choix natif BASCULE de
   `T1` a `T2`. C'est la contre-epreuve : a `u_full` egal, seul le trait a bouge.
D. **La MAGNITUDE `1` est MESUREE, pas seulement lue.** On fait varier `u_full(T1)` par les PV de T1
   (seul levier qui ne touche ni la geometrie ni les traits) et on lit ou le natif bascule :
   a `delta = -0.90` il tient `T1`, a `delta = -1.10` il lache. Le terme d'UN Psyker est donc
   encadre dans `(0.90, 1.10)` -- et le port rend `1.0`.
E. **La VAGUE 3 est portee.** Bras C : le Psyker est en `W1`, voisin de `V1` et NON voisin de `T1`.
   Il n'entre dans le compte que par `t3 = Unique(Enemies(AdjacentUnits(t2))) - t1 - t2`. Un port
   qui s'arreterait aux deux premieres vagues rendrait `0`.
F. **La chaine DSL est EXACTE, pas approchee** (offline) : les trois vagues, l'exclusion `- t1 - t2`,
   et le filtre `Psyker` sont verifies sur une geometrie synthetique ou chaque vague est peuplee.

G. **L'ACCORD DE DECISION de bout en bout, moteur<->natif** (#27-r5-r1). Il etait IMPOSSIBLE tant que
   `IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions` n'etait pas
   porte : le natif y fait TROIS batchs `GenerateMultiHitAttackPredictions` (un par vague, avec
   `GetDamage1`/`GetDamage2`/`GetDamage3`), la ou le port heritait du chemin generique mono-cible.
   MESURE d'alors, bras A : `u_full` port 1.1220 / 5.6097 contre natif 13.2764 / 13.7118, et le
   moteur choisissait `T2` dans les TROIS bras. Depuis #27-r5-r1, `u_full` port et natif coincident
   a **1e-8** (Fix64 vs double) et `engine_decide` rend la cible du natif dans les trois bras --
   bras A COMPRIS, celui ou le natif va CONTRE son propre `u_full`. Ces deux assertions auraient
   ete ROUGES avant ce port : c'est ce qui les rend non triviales.

CE QUI N'EST PAS GARDE, ET POURQUOI (dit plutot que masque) :

* La branche `If(HasTrait(Target, 2 = Summon), Multiply(..., x2), ...)` des formules de degat n'est
  pas exercee ICI (aucune cible `Summon` dans ce montage) : elle l'est dans
  `test_plague_wind_prediction_live.py`, sur le meme porteur greffe.
* Le filtre `Enemies` est exerce (les allies du caster ne sont jamais dans `t2`/`t3` puisque le
  caster est seul de son camp), mais pas avec un allie POSITIONNE dans l'anneau : garde offline.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r5_mortarions_plague_wind as AB             # noqa: E402
from engine import dsl                                      # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait      # noqa: E402
from engine.runner.abilities.deathguard import (             # noqa: E402
    mortarions_plague_wind_psyker_selector, plague_wind_wave_selectors)

MPW = AB.MPW


# --------------------------------------------------------------------------- F : la chaine, OFFLINE

class _Board:
    """Graphe de tuiles MINIMAL : une ligne d'hexes (col, 0) ou chaque tuile touche ses deux
    voisines. Suffit a peupler les trois vagues et a les distinguer, sans dependre d'un board dumpe.
    Meme contrat que `engine.board.Board` pour ce que `_within`/`AdjacentTiles` consomment."""

    def __init__(self, n: int = 8):
        self.by_id = {i: {"col": i, "row": 0} for i in range(n)}

    def id_at(self, col, row):
        return col if (row == 0 and col in self.by_id) else None

    def coord(self, tid):
        t = self.by_id.get(tid)
        return None if t is None else (t["col"], t["row"])

    def neighbours_native(self, tid):
        return [t for t in (tid - 1, tid + 1) if t in self.by_id]


def _unit(uid, col, team, psyker=False):
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": col, "row": 0}, "psyker": psyker}


def _ctx(units, caster, target):
    return dsl.DslContext(units=units, caster=caster, target=target, board=_Board(),
                          has_trait=lambda u, t: bool((u or {}).get("psyker"))
                          and int(t) == int(UnitTrait.Psyker))


def _chain():
    """Une ligne : caster(0) | T(1) | S(2) | X(3) | Y(4). Toutes les unites 1..4 sont ENNEMIES.
    Vagues attendues pour `target = T` : t1={T}, t2={S}, t3={X} (Y est a 3 hexes -> hors)."""
    caster = _unit(10, 0, team=1)
    t, s, x, y = (_unit(11, 1, 2), _unit(12, 2, 2), _unit(13, 3, 2), _unit(14, 4, 2))
    return caster, t, s, x, y


def test_the_three_waves_are_exactly_t1_t2_t3():
    """F -- structure : chaque vague contient ce que le decompile dit, et rien d'autre."""
    caster, t, s, x, y = _chain()
    ctx = _ctx([caster, t, s, x, y], caster, t)
    n1, n2, n3 = plague_wind_wave_selectors()
    # `_units_of` = le normaliseur du DSL (`Target()` rend l'ENTITE, pas une liste ; c'est lui que
    # `Union`/`Sub` appliquent aux operandes). L'utiliser ici, c'est lire les vagues comme le port
    # les consomme -- iterer `evaluate()` a nu rendrait les CLES du dict.
    ids = lambda sel: sorted(u["id"] for u in dsl.base._units_of(sel, ctx))     # noqa: E731
    assert ids(n1) == [11], "t1 doit valoir exactement la CIBLE (<DSLSelectors+0x60> = Target)"
    assert ids(n2) == [12], "t2 = Enemies(AdjacentUnits(t1)) -- la cible s'exclut elle-meme"
    assert ids(n3) == [13], ("t3 = Unique(Enemies(AdjacentUnits(t2))) - t1 - t2 : X seul (Y est a "
                             "3 hexes), et la soustraction retire bien T et S")


def test_the_caster_is_never_in_a_wave_even_when_adjacent():
    """F -- `Enemies(<DSLSelectors+0x48> = Caster, ...)` : un ALLIE adjacent n'entre dans aucune
    vague. Le caster est en (0) donc adjacent a la cible (1) -- sans le filtre d'equipe il serait
    dans `t2`."""
    caster, t, s, x, y = _chain()
    friend = _unit(15, 2, team=1)                     # allie, adjacent au secondaire ET a la cible
    ctx = _ctx([caster, friend, t, s, x, y], caster, t)
    _n1, n2, n3 = plague_wind_wave_selectors()
    got = {u["id"] for u in n2.evaluate(ctx)} | {u["id"] for u in n3.evaluate(ctx)}
    assert 10 not in got and 15 not in got, (
        "un allie est entre dans une vague -> le filtre `Enemies` n'est pas applique : %r" % (got,))


@pytest.mark.parametrize("psykers, want", [
    ((), 0),                       # aucun Psyker -> 0
    ((11,), 1),                    # la CIBLE elle-meme (vague 1)
    ((12,), 1),                    # un SECONDAIRE (vague 2)
    ((13,), 1),                    # un TERTIAIRE (vague 3)
    ((14,), 0),                    # hors des trois vagues -> ne compte pas
    ((11, 12, 13), 3),             # le compte est LINEAIRE sur les trois vagues
])
def test_the_count_is_the_utility(psykers, want):
    """F -- `Count(UnitsWithTrait(t1 + t2 + t3, Psyker))`. Aucun poids, aucune constante : le compte
    EST l'utilite. Le cas `(14,)` garde la BORNE de la chaine (une 4e vague n'existe pas)."""
    caster, t, s, x, y = _chain()
    for u in (t, s, x, y):
        u["psyker"] = u["id"] in psykers
    ctx = _ctx([caster, t, s, x, y], caster, t)
    assert len(mortarions_plague_wind_psyker_selector().evaluate(ctx)) == want


def test_a_unit_counted_twice_would_be_visible():
    """F -- les trois vagues sont DISJOINTES (le natif n'insere aucun `Unique` par-dessus l'union,
    parce que `t3` retranche deja `t1` et `t2`). Si le port laissait un doublon, ce compte vaudrait
    plus que le nombre d'unites Psyker distinctes."""
    caster, t, s, x, y = _chain()
    for u in (t, s, x):
        u["psyker"] = True
    ctx = _ctx([caster, t, s, x, y], caster, t)
    got = mortarions_plague_wind_psyker_selector().evaluate(ctx)
    assert len(got) == len({u["id"] for u in got}) == 3


# ------------------------------------------------------------------------------- A-E : le LIVE

@pytest.fixture(scope="module")
def arms():
    """Un runner PAR BRAS (chaque unite ne peut faire qu'UN deplacement), disposes au fil de l'eau."""
    out = {}
    for name in ("A", "B", "C"):
        rid = AB.build()
        try:
            out[name] = AB.run_arm(name, rid, AB.EXPECT[name])
        finally:
            try:
                AB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass
    return out


def test_graft_makes_the_native_emit_the_ability(arms):
    """A -- sans ca, « npc-only = non confrontable » redevient vrai et rien d'autre ne vaut."""
    for name, r in arms.items():
        assert any(ab == MPW for _c, ab, _t in r["native"]), (
            "bras %s : le natif n'a pas propose 1093 (%r) -- la greffe n'exerce pas le playbook"
            % (name, r["native"]))


def test_native_choice_goes_against_its_own_damage_preference(arms):
    """B -- bras A : le natif retient `T1` alors que son `u_full` favorise `T2`. C'est LA mesure du
    terme : aucun autre terme ne distingue ces deux actions."""
    a = arms["A"]
    assert a["d_uf"] < 0, ("le montage a derive : `u_full(T1) - u_full(T2)` = %+.4f, il doit etre "
                           "NEGATIF pour que le choix de T1 soit contre-nature" % a["d_uf"])
    assert a["chosen"] == "T1"
    assert a["against"] is True


def test_permuting_the_psyker_flips_the_native_choice(arms):
    """C -- la contre-epreuve. `u_full` natif est IDENTIQUE dans les deux bras : seule la position du
    trait a bouge, et le choix natif bascule."""
    a, b = arms["A"], arms["B"]
    assert a["uf_native"] == b["uf_native"], (
        "la permutation a change `u_full` (%r vs %r) -- le bras B ne serait plus une contre-epreuve "
        "du TRAIT mais un scenario different" % (a["uf_native"], b["uf_native"]))
    assert (a["chosen"], b["chosen"]) == ("T1", "T2")


def test_port_reproduces_the_count_in_every_arm(arms):
    """B/C/E -- le port rend exactement le compte que la RE predit, dans les trois geometries."""
    for name, r in arms.items():
        assert r["custom"] == AB.EXPECT[name]["custom"], (
            "bras %s : custom port %r != %r" % (name, r["custom"], AB.EXPECT[name]["custom"]))


def test_third_wave_is_counted_live(arms):
    """E -- bras C : le Psyker n'est atteint QUE par `t3`. Un port a deux vagues rendrait 0."""
    assert arms["C"]["custom"]["T1"] == 1.0


def test_magnitude_is_bracketed_by_the_native_flip():
    """D -- encadrement de la constante par bascule : (0.90, 1.10) pour UN Psyker."""
    assert AB.run_magnitude(), "l'encadrement de la magnitude a echoue -- cf. la sortie du probe"


# ------------------------------------------------------- G : l'accord de DECISION (#27-r5-r1)

def test_port_u_full_matches_the_native_in_every_arm(arms):
    """G -- `CalculateUtilityFromPredictions` port == natif, dans les trois bras.

    C'est l'etage qui portait le residu : le port n'emettait qu'UN des trois batchs de
    `MakeDamagePredictions`. Ecart d'alors, bras A : `1.1220` contre `13.2764` (facteur ~12).
    Tolerance `1e-6` -- le natif calcule en `Fix64` (pas 2^-32) et le port en `double` ; l'ecart
    RESIDUEL mesure est ~`1e-8`, soit deux ordres de grandeur sous la tolerance et sept sous
    l'ecart que ce test existe pour interdire."""
    for name, r in arms.items():
        for key in ("T1", "T2"):
            d = abs(r["uf_port"][key] - r["uf_native"][key])
            assert d < 1e-6, (
                "bras %s / %s : u_full port %.6f != natif %.6f (ecart %.3e) -- un batch de "
                "`MakeDamagePredictions` manque ou porte la mauvaise base"
                % (name, key, r["uf_port"][key], r["uf_native"][key], d))


def test_engine_decides_the_same_target_as_the_native_in_every_arm(arms):
    """G -- `engine_decide` rend l'ability ET la cible du natif dans les trois bras.

    Le bras A est le plus fort des trois : le natif y va CONTRE son propre `u_full` (il retient
    `T1` alors que `T2` vaut 0.435 de plus), donc le moteur ne peut le suivre qu'en portant A LA
    FOIS les trois batchs de degat ET le terme custom. La contre-epreuve est dans le meme dict :
    `zero` (custom force a 0) doit designer l'AUTRE cible sur ce bras -- sinon l'accord ne viendrait
    pas du terme."""
    for name, r in arms.items():
        want = r["targets"][r["chosen"]]
        assert r["on"] == (MPW, want), (
            "bras %s : moteur %r, natif (%d, %s)" % (name, r["on"], MPW, want))
    a = arms["A"]
    assert a["zero"] == (MPW, a["targets"]["T2"]), (
        "bras A : custom desarme -> le moteur devrait retomber sur T2 (l'argmax de `u_full`) ; il "
        "rend %r. Sans cette bascule, l'accord du bras A ne prouverait pas que le terme decide."
        % (a["zero"],))
