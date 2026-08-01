"""#418 -- GARDE DU PORT de `1511 PrimarchOfTheFirstLegion` : le CIBLAGE et son cout en TIRAGES.

`1109 DrawFire` (#411-r1) choisit sa cible sans aucun alea : le porteur EST la cible de transfert.
`1511`, lui, la TIRE -- `Randomize -> SortByFormula -> First` -- et c'est ce qui rend ce port
faux-ou-juste de facon INVISIBLE : un port qui rendrait la bonne unite en consommant un tirage de
trop (ou de moins) decale tout le flux aleatoire EN AVAL, et le symptome n'apparait pas sur la
valeur mesuree -- il apparait plus loin, ailleurs, sans lien apparent.

Ces tests comptent donc les TIRAGES (`call_count` du MT), pas seulement la cible choisie.

La loi native, lue dans `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` avec les
litteraux qu'ecrit `IdunBattleLogic.Entities.DSLSelectors$$Randomize` (`amount = 0x7fffffff`,
`allowDuplicates = false`, `maxDuplicatesAllowed = 0x7fffffff`, `ignoreForcedTargets = false`) :

    pool de N -> **N tirages**, bornes DECROISSANTES N, N-1, …, 1 ; pool VIDE -> **0**.

Le dernier tirage (`Next(0, 1)`) n'est PAS court-circuite : `IdunBattle.Utils.PRNG.
IntBasedMersenneTwister$$IdunBattle.Utils.PRNG.IPseudoRNG.Next` prend la branche puissance-de-2,
consomme un `genrand_int32` et rend toujours 0. **Un pool d'UNE unite coute donc UN tirage** -- le
cas qui ne discrimine aucune valeur et que seul un ledger attrape.

RE : `docs/rl/case-411-r3-primarch-of-the-first-legion.md`. Confrontation live : `probe_418_primarch_
transfer.py`.

ASCII only.
"""
from __future__ import annotations

from engine.dsl.base import Const, DslContext
from engine.entities.formulas import If as FIf
from engine.entities.selectors.accessors import Owner, Subject
from engine.entities.selectors.units import EntitiesFromPersistentDataList
from engine.entities.triggers import Contains
from engine.runner.abilities.loki.splash import _pick_randomly_n
from engine.runner.operations.triggers.loki.primarch_first_legion import (
    PERSISTENT_DATA_KEY, PRIMARCH_EXTRA_DAMAGE, PRIMARCH_OF_THE_FIRST_LEGION,
    primarch_transfer_target_selector)
from engine.runner.prng import IntBasedMersenneTwister


# --------------------------------------------------------------------------- harnais minimal

class _CountingMT(IntBasedMersenneTwister):
    """MT qui compte ses appels a `next_internal` -- LE ledger de cette tranche.

    ⚠ Pourquoi pas `call_count` : le mirror l'incremente DEUX fois par tirage (une fois dans
    `next_internal`, une fois dans le `genrand_int32` qu'il appelle -- c'est ce que fait le natif
    sur son compteur `@+0x14`, cf. l'en-tete de `runner/prng.py`), et DAVANTAGE quand la boucle de
    rejet tourne. Un compteur de `genrand` ne repondrait donc pas non plus a la question posee ici,
    qui est : **combien de fois le selecteur a-t-il appele `IPseudoRNG.Next` ?**"""

    __slots__ = ("draws",)

    def __init__(self, seed: int):
        super().__init__(seed)
        self.draws = 0

    def next_internal(self, lo: int, hi: int) -> int:
        self.draws += 1
        return super().next_internal(lo, hi)


class _FakeState:
    """Le seul membre que `_pick_randomly_n` lit est le PRNG de bataille."""

    def __init__(self, seed: int):
        self.rng = _CountingMT(seed)


def _unit(uid: int, col: int, row: int, team: int = 1, faction: str = "DarkAngels"):
    return {"id": uid, "team": team, "player": team, "alive": True, "hp": 100,
            "pos": {"col": col, "row": row}, "visualId": "vid%d" % uid, "_faction": faction,
            "_traits": set()}


def _ctx(state, units, owner, persist=None):
    """`AbilityEntities` minimale. Le contexte est monte sur le PORTEUR en caster : le gate
    `AreEqual(Owner, Target)` du `CreateTrigger` natif rend `owner == target == le defenseur`, et
    `Owner()` retombe sur `ctx.caster` (cf. `primarch_first_legion.PrimarchTransfer._entities`).

    Pas de `board` : `_within` retombe alors sur l'ordre de `ctx.units` (degradation NOMMEE de
    `dsl/base.py`). C'est VOULU ici -- ces tests gardent la CONSOMMATION et la STRUCTURE du tri ;
    l'ordre d'enumeration des tuiles (`AdjacentTilesSelector`, R28-1) se confronte LIVE."""
    bag = dict(persist or {})
    by_id = {int(u["id"]): u for u in units}
    return DslContext(
        units=units, caster=owner, target=owner, actor=None, board=None,
        faction_of=lambda u: (u or {}).get("_faction"),
        persistent_data_list=lambda u, key: list(bag.get((int((u or {}).get("id") or -1), key)) or ()),
        entity_by_id=lambda eid: by_id.get(int(eid)) if eid is not None else None,
        pick_randomly=lambda items, n, rep=False, mx=0x7FFFFFFF: _pick_randomly_n(
            state, list(items), int(n), allow_repeat=bool(rep), max_repeats=int(mx)))


def _ring(state, n_allies: int, served=(), faction="DarkAngels"):
    """Le porteur en (5,5) + `n_allies` allies ADJACENTS (les six voisins hex de la colonne paire).

    `served` = les INDICES des allies deja ranges dans la liste persistante du porteur (ceux que
    `Contains(GetPersistentDataListAsEntities(...), It)` doit reconnaitre)."""
    owner = _unit(100, 5, 5)
    around = [(5, 4), (5, 6), (4, 4), (4, 5), (6, 4), (6, 5)]
    allies = [_unit(10 + i, c, r, faction=faction) for i, (c, r) in enumerate(around[:n_allies])]
    key = (owner["id"], (PRIMARCH_OF_THE_FIRST_LEGION, PERSISTENT_DATA_KEY))
    persist = {key: [allies[i]["id"] for i in served]} if served else None
    return owner, allies, _ctx(state, [owner] + allies, owner, persist)


# ------------------------------------------------------ la LOI DE CONSOMMATION (le coeur #418)

def test_pool_de_UN_consomme_QUAND_MEME_un_tirage():
    """LE cas de la tranche. Le pool degenere ne discrimine aucune valeur -- la cible est connue
    d'avance -- mais le natif tire `Next(0, 1)` malgre tout. Un port qui sauterait ce tirage
    rendrait la BONNE cible et desynchroniserait tout l'aval."""
    st = _FakeState(777)
    owner, allies, ctx = _ring(st, 1)
    n0 = st.rng.draws
    picked = primarch_transfer_target_selector().evaluate(ctx)
    assert [u["id"] for u in picked] == [allies[0]["id"]]
    assert st.rng.draws - n0 == 1, \
        "pool de 1 -> %d tirage(s), attendu 1" % (st.rng.draws - n0)


def test_le_pool_VIDE_ne_consomme_RIEN_et_ne_transfere_pas():
    """`candidates.Count < 1` sort AVANT le premier `Next` -- et `If(AmountIsGreaterThanZero(target),
    …)` fait du behaviour un no-op complet."""
    st = _FakeState(777)
    owner, allies, ctx = _ring(st, 0)
    n0 = st.rng.draws
    assert primarch_transfer_target_selector().evaluate(ctx) == []
    assert st.rng.draws == n0


def test_le_nombre_de_tirages_EGALE_la_taille_du_pool():
    """N candidats -> N tirages, bornes decroissantes. Un court-circuit « le pool tient deja dans
    amount » (amount = int.MaxValue) en couterait 0 ; un `First` paresseux en couterait 1."""
    for n in (1, 2, 3, 4, 5, 6):
        st = _FakeState(31337)
        owner, allies, ctx = _ring(st, n)
        n0 = st.rng.draws
        picked = primarch_transfer_target_selector().evaluate(ctx)
        assert len(picked) == 1                       # `First(…, amount = 1)`
        assert st.rng.draws - n0 == n, \
            "pool de %d -> %d tirage(s)" % (n, st.rng.draws - n0)


def test_le_Cache_evite_de_RE_TIRER_sur_une_seconde_lecture():
    """`Cache(matchAbilityEntities = 1)` : l'arbre est lu SIX fois dans `CreateBehaviour` (condition
    du `If`, `TransferHit`, `AddEffect`, `IfAlive`, `EntityId`, cible du `AddToPersistentDataList`).
    Sans memoisation ce serait 6xN tirages."""
    st = _FakeState(999)
    owner, allies, ctx = _ring(st, 4)
    tree = primarch_transfer_target_selector()
    n0 = st.rng.draws
    first = tree.evaluate(ctx)
    spent = st.rng.draws - n0
    for _ in range(5):
        assert [u["id"] for u in tree.evaluate(ctx)] == [u["id"] for u in first]
    assert st.rng.draws - n0 == spent == 4


def test_un_arbre_NEUF_re_tire():
    """Contre-epreuve du precedent : la memoisation est portee par l'INSTANCE du noeud. Le natif
    keye son dict par l'`AbilityEntities`, dont `hitIndex@+0x108` fait partie -> la cle change a
    chaque coup. Le port rebatit l'arbre par declenchement, ce qui produit le MEME effet.
    Sans ce test, un `Cache` accidentellement partage entre coups passerait le test precedent."""
    st = _FakeState(999)
    owner, allies, ctx = _ring(st, 4)
    n0 = st.rng.draws
    primarch_transfer_target_selector().evaluate(ctx)
    primarch_transfer_target_selector().evaluate(ctx)
    assert st.rng.draws - n0 == 8


# ------------------------------------------------------------- le TRI anti-repetition (le `If`)

def test_un_allie_DEJA_servi_passe_DERRIERE():
    """`SortByFormula(…, If(Contains(dejaServis, It), <DSLFormulas+0x18 = 0>, <+0x20 = 1>),
    ascending = 0)` -> tri DESCENDANT : les non-servis (cle 1) devant, les servis (cle 0) derriere.

    On sature le tirage : avec DEUX allies dont UN seul est deja servi, le `First` doit rendre
    l'autre, QUEL QUE SOIT l'ordre sorti du melange. Les deux seeds couvrent les deux permutations
    (verification explicite ci-dessous que le melange les produit bien toutes les deux)."""
    seen_first_positions = set()
    for seed in range(40):
        st = _FakeState(seed)
        owner, allies, ctx = _ring(st, 2, served=(0,))
        picked = primarch_transfer_target_selector().evaluate(ctx)
        assert [u["id"] for u in picked] == [allies[1]["id"]], \
            "seed %d : l'allie deja servi a ete repris" % seed
        # ordre brut du melange, pour prouver que le tri a REELLEMENT du travail sur certains seeds
        st2 = _FakeState(seed)
        seen_first_positions.add(_pick_randomly_n(st2, [allies[0], allies[1]], 0x7FFFFFFF)[0]["id"])
    assert seen_first_positions == {allies[0]["id"], allies[1]["id"]}, \
        "le melange n'a produit qu'UNE permutation -- le test ne discrimine rien"


def test_tous_servis_le_tri_redevient_NEUTRE():
    """Quand la liste persistante contient TOUT le pool, les cles valent 0 partout : `OrderByDescending`
    LINQ etant STABLE, l'ordre du melange est integralement preserve -> le choix est le premier
    TIRE. C'est le regime dans lequel le port entre en permanence tant que le clear de fin de tour
    n'est pas porte (residu nomme, cf. `primarch_first_legion` en-tete §4) -- et il ne coute rien
    au ledger : meme pool, memes N tirages."""
    for seed in (7, 21, 55, 101):
        st = _FakeState(seed)
        owner, allies, ctx = _ring(st, 3, served=(0, 1, 2))
        n0 = st.rng.draws
        picked = primarch_transfer_target_selector().evaluate(ctx)
        assert st.rng.draws - n0 == 3
        st2 = _FakeState(seed)
        expected = _pick_randomly_n(st2, list(allies), 0x7FFFFFFF)[0]["id"]
        assert picked[0]["id"] == expected


# ------------------------------------------------------------------- le FILTRE DE FACTION (0xa)

def test_seuls_les_DARK_ANGELS_entrent_au_pool():
    """`UnitsFromFaction(AdjacentFriends(Owner), 0xa)` : `0xa` = `UnitFaction.DarkAngels`. Un allie
    adjacent d'une AUTRE faction n'est ni tire ni compte -- donc il ne coute AUCUN tirage non plus."""
    st = _FakeState(777)
    owner = _unit(100, 5, 5)
    da = _unit(10, 5, 4, faction="DarkAngels")
    other = _unit(11, 5, 6, faction="Ultramarines")
    ctx = _ctx(st, [owner, da, other], owner)
    n0 = st.rng.draws
    picked = primarch_transfer_target_selector().evaluate(ctx)
    assert [u["id"] for u in picked] == [10]
    assert st.rng.draws - n0 == 1, "l'unite hors faction a ete tiree"


def test_un_ENNEMI_adjacent_dark_angels_n_entre_pas():
    """`AdjacentFriends` filtre sur l'equipe de la REFERENCE (= le centre = l'Owner)."""
    st = _FakeState(777)
    owner = _unit(100, 5, 5, team=1)
    foe = _unit(10, 5, 4, team=2, faction="DarkAngels")
    ctx = _ctx(st, [owner, foe], owner)
    n0 = st.rng.draws
    assert primarch_transfer_target_selector().evaluate(ctx) == []
    assert st.rng.draws == n0


def test_le_PORTEUR_lui_meme_n_entre_pas_dans_son_pool():
    """La surcharge native est `Friends(X, Units(AdjacentTiles(X), …) - X, …)` -- le `- X` retire le
    centre. Sans lui, le Lion se transfererait le coup a lui-meme (boucle)."""
    st = _FakeState(777)
    owner, allies, ctx = _ring(st, 2)
    picked = primarch_transfer_target_selector().evaluate(ctx)
    assert picked[0]["id"] != owner["id"]


# ------------------------------------------------- les deux PRIMITIVES neuves, prises isolement

def test_Contains_compare_par_ID_et_exige_un_element_UNIQUE():
    """`IdunBattle.Entities.Triggers.XContainsYTrigger$$ShouldTrigger` : `elements` passe par
    **SelectSingle** (0 ou >1 -> FALSE) et la comparaison est sur `get_Id`."""
    st = _FakeState(1)
    a, b = _unit(1, 0, 0), _unit(2, 0, 1)
    ctx = _ctx(st, [a, b], a)
    from engine.dsl.base import TargetsSelector

    class _Lit(TargetsSelector):
        def __init__(self, v):
            self.v = v

        def select(self, _ctx):
            return self.v

    assert Contains(_Lit([a, b]), _Lit(a)).evaluate(ctx) is True
    assert Contains(_Lit([b]), _Lit(a)).evaluate(ctx) is False
    assert Contains(_Lit([a, b]), _Lit([a, b])).evaluate(ctx) is False   # SelectSingle : >1 -> False
    assert Contains(_Lit([a, b]), _Lit([])).evaluate(ctx) is False       # SelectSingle : 0  -> False
    # comparaison par ID, pas par identite d'objet
    assert Contains(_Lit([dict(a)]), _Lit(a)).evaluate(ctx) is True


def test_EntitiesFromPersistentDataList_garde_l_ORDRE_et_jette_les_ids_inconnus():
    """`EntitiesFromPersistentDataListSelector$$Select` : aucun tri, et `GetEntity(id)` nul ->
    l'entree est silencieusement jetee."""
    st = _FakeState(1)
    a, b, c = _unit(1, 0, 0), _unit(2, 0, 1), _unit(3, 0, 2)
    holder = _unit(100, 5, 5)
    key = (PRIMARCH_OF_THE_FIRST_LEGION, PERSISTENT_DATA_KEY)
    ctx = _ctx(st, [holder, a, b, c], holder, persist={(100, key): [3, 999, 1, 2]})
    sel = EntitiesFromPersistentDataList(PRIMARCH_OF_THE_FIRST_LEGION, Owner(), PERSISTENT_DATA_KEY)
    assert [u["id"] for u in sel.evaluate(ctx)] == [3, 1, 2]      # 999 inconnu -> jete, ordre garde


def test_EntitiesFromPersistentDataList_sans_accesseur_rend_VIDE():
    """Contexte hors runner (pas de `persistent_data_list` / `entity_by_id`) -> liste vide, meme
    polarite que le natif quand la cle est absente (`?? new List<T>()`)."""
    sel = EntitiesFromPersistentDataList(PRIMARCH_OF_THE_FIRST_LEGION, Owner(), PERSISTENT_DATA_KEY)
    a = _unit(1, 0, 0)
    assert sel.evaluate(DslContext(units=[a], caster=a)) == []


# ------------------------------------------------------------------------ la formule de tri nue

def test_la_formule_de_tri_rend_bien_ZERO_pour_un_servi_et_UN_sinon():
    """Les DEUX constantes viennent de `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
    (`+0x18 = 0`, `+0x20 = 1`). Les inverser retournerait la preference sans rien casser d'autre --
    d'ou ce test qui les lit a l'endroit exact ou elles comptent."""
    from dataclasses import replace
    st = _FakeState(1)
    a, b = _unit(1, 0, 0), _unit(2, 0, 1)
    holder = _unit(100, 5, 5)
    key = (PRIMARCH_OF_THE_FIRST_LEGION, PERSISTENT_DATA_KEY)
    ctx = _ctx(st, [holder, a, b], holder, persist={(100, key): [a["id"]]})
    already = EntitiesFromPersistentDataList(PRIMARCH_OF_THE_FIRST_LEGION, Owner(),
                                             PERSISTENT_DATA_KEY)
    rank = FIf(Contains(already, Subject()), Const(0), Const(1))
    assert rank.evaluate(replace(ctx, subject=a)) == 0            # deja servi
    assert rank.evaluate(replace(ctx, subject=b)) == 1            # jamais servi


# ---------------------------------------------------------------------------- donnees de RE gelees

def test_les_ids_d_enum_sont_ceux_du_decompile():
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert PRIMARCH_OF_THE_FIRST_LEGION == int(TriggeredAbilityType.PrimarchOfTheFirstLegion) == 1511
    assert PRIMARCH_EXTRA_DAMAGE == int(EffectType.PrimarchOfTheFirstLegion_ExtraDamage) == 1523
    assert PRIMARCH_EXTRA_DAMAGE == 0x5F3                        # le litteral de `AddEffect`


def test_l_effet_1523_est_ENREGISTRE_et_additif_sans_gate_de_prediction():
    """`ForAddition(get_OwnerIsCaster, ConfigVar(8 = extraDmg))` -- gate SEUL. Contraste LU avec
    `SmashaEad` / `FeederTendrils`, qui portent en plus `IsNormalAttack` et rendent donc `None` en
    prediction. Recopier leur `if is_prediction: return None` ici serait la faute inverse."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki import PrimarchOfTheFirstLegionExtraDamageEffect
    assert EFFECT_CLASSES["PrimarchOfTheFirstLegion_ExtraDamage"] is \
        PrimarchOfTheFirstLegionExtraDamageEffect
    eff = PrimarchOfTheFirstLegionExtraDamageEffect(
        name="PrimarchOfTheFirstLegion_ExtraDamage", ability_level=50)
    b_combat = eff.create_effect_damage_bonus_for_attack(is_prediction=False)
    b_pred = eff.create_effect_damage_bonus_for_attack(is_prediction=True)
    assert b_combat is not None and b_combat.kind == "Addition" and b_combat.owner_is_caster is True
    # `extraDmg[level - 1]` du gameconfig, multiplier 100 par defaut -> la valeur EXACTE de la table
    import gameconfig as GC
    expected = ((GC.ability("PrimarchOfTheFirstLegion") or {})["variables"]["extraDmg"])[49]
    assert b_combat.value == expected
    # AUCUN gate `is_prediction` : le natif n'a que `get_OwnerIsCaster`
    assert b_pred is not None and b_pred.value == b_combat.value
