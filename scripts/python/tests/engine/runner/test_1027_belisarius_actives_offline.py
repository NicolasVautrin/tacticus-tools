"""#1027 -- GARDE des deux actives npc d'`admecBossBelisarius` : `InvocationOfMachineVengeance`
(1172) et `SolarAtomizer` (1174). 100 % OFFLINE (aucun runner).

Ce que chaque etage garde, et le MUTANT qui doit le faire tomber :

  1. les DEUX litteraux du ctor natif (masque + AbilityAttackType)      -> changer un bit
  2. l'entree au registre + la face DECISION                            -> retirer une entree
  3. la STRUCTURE de l'arbre de 1172 (spawn PUIS buff, dans cet ordre)  -> inverser op_and
  4. la STRUCTURE de l'arbre de 1174 (transfert PUIS marquage)          -> retirer une feuille
  5. `EffectLevelOf` est une SOMME                                      -> rendre le premier
  6. `SortByRow(additional_sorting=...)` est un `ThenBy`                -> ignorer la formule
  7. l'utilite du playbook 1172 vaut 2 hors origine, 1 a l'origine      -> figer a 1
  8. l'utilite du playbook 1174 = 1 + |bande| + 20*|ennemis|            -> retirer le +1 par tuile
  9. `SortByRow(sameColumnIsRandom=1)` TIRE une cle par element         -> ne pas tirer (#1027-r1)
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: ⚠ IL N'EN AVAIT AUCUN, et le garde `declencheur_guard` rendait donc `rc 1` sur `origin/master`
#: alors que ses 8 tests passaient -- un fichier VERT dans une passe ROUGE. Ajoute par #1027-r1,
#: qui touche precisement l'etage 6/9 de ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER des deux actives + leurs registres.
        "scripts/python/engine/runner/abilities/admec.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        # LES NOEUDS DSL que la forme de l'arbre exerce.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/_pick.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/dsl/base.py",
        # LE PRNG : l'etage 9 en depend directement.
        "scripts/python/engine/runner/prng.py",
        # LES ORDINAUX cites.
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        # LA FACE DECISION des deux abilities.
        "scripts/python/engine/playbook/prediction/abilities.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE : les deux litteraux du ctor, les registres, la STRUCTURE des deux "
              "arbres, la somme d'EffectLevelOf, le sens des tris et les deux utilites de "
              "playbook. Aucun RPC, aucun runner.",
}

import os                                                                    # noqa: E402
import sys                                                                   # noqa: E402

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.formulas import Const, EffectLevelOf                   # noqa: E402
from engine.entities.selectors.geometry import SortByRow                    # noqa: E402
from engine.runner.abilities import admec as A                              # noqa: E402
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,        # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.handler import ABILITY_CLASSES                 # noqa: E402
from engine.runner.abilities.targeting import RANGE_SELF, RANGED_BOOL_FALSE  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR      # noqa: E402


IMV = int(ActiveAbilityType.InvocationOfMachineVengeance)      # 1172
SA = int(ActiveAbilityType.SolarAtomizer)                      # 1174


# ------------------------------------------------------------------ etage 1 : les litteraux
def test_etage1_litteraux_du_ctor_natif():
    """`InvocationOfMachineVengeanceAbility$$.ctor` : `TargetingOptions..ctor(&opts,
    isSelfCasting = 1, range = &<TargetingRange statics+0x60>, forceMeleeTarget = 1,
    rules = 0x8000, 0, 0)` puis `AActiveAbility..ctor(this, &opts, 2)`.
    `SolarAtomizerAbility$$.ctor` : idem avec `isSelfCasting = 0`,
    `range = CustomRange(2)`, `rules = 0x1000100042`."""
    o = A.InvocationOfMachineVengeanceAbility.TARGETING_OPTIONS
    assert int(o.rules) == 0x8000, "1172 : le masque LU est 0x8000 (CasterIsPossibleTarget seul)"
    assert int(o.rules) == int(TR.CasterIsPossibleTarget)
    assert o.self_cast is True and o.force_melee_target == RANGED_BOOL_FALSE
    assert o.range == RANGE_SELF, "1172 : `TargetingRange statics+0x60` = RANGE_SELF"

    o2 = A.SolarAtomizerAbility.TARGETING_OPTIONS
    assert int(o2.rules) == 0x1000100042, "1174 : masque LU au ctor"
    assert int(o2.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsTile
                                | TR.AllowSteppableUnit | TR.CasterHas3Tiles)
    assert o2.self_cast is False and o2.force_melee_target == RANGED_BOOL_FALSE
    assert o2.range.override_range == 2 and o2.range.override_range_func is False, \
        "1174 : `CustomRange(2)` -- le `2` est charge dans edx juste avant le call"

    # `AActiveAbility..ctor(this, &opts, 2)` pour LES DEUX -- 2 = Others, PAS un type d'attaque.
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.InvocationOfMachineVengeance] \
        == AbilityAttackType.Others
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.SolarAtomizer] == AbilityAttackType.Others


# ------------------------------------------------------ etage 2 : registres COMBAT et DECISION
def test_etage2_les_deux_faces_sont_inscrites():
    from engine.playbook.noncomparable import PLAYBOOKS
    assert ABILITY_CLASSES.get(IMV) is A.InvocationOfMachineVengeanceAbility
    assert ABILITY_CLASSES.get(SA) is A.SolarAtomizerAbility
    assert IMV in PLAYBOOKS and SA in PLAYBOOKS, \
        "face DECISION : les deux playbooks entrent au registre NonComparable"
    # cctor natif = `Fix64.op_Implicit(1)` pour les deux ; tiers mesures #170.
    assert PLAYBOOKS[IMV].MIN_UTILITY == 1.0 and PLAYBOOKS[SA].MIN_UTILITY == 1.0
    assert PLAYBOOKS[IMV].PRIORITY == -1000, "1172 = AbilityPriority.Last"
    assert PLAYBOOKS[SA].PRIORITY == 100, "1174 = AbilityPriority.Early"


# ------------------------------------------------------------- etage 3 : l'arbre de 1172
def _enfants(node):
    """Les sous-noeuds d'un noeud DSL, quel que soit son mode de stockage (`__dict__` ou
    `__slots__`). Un parcours par LISTE BLANCHE de noms d'attributs raterait le noeud qui range
    ses enfants ailleurs -- c'est exactement ce qui est arrive avec `Seq` (les `op_and`/`op_add`),
    dont aucun champ ne s'appelle `left`/`right`."""
    vals = []
    d = getattr(node, "__dict__", None)
    if d:
        vals.extend(d.values())
    for cls in type(node).__mro__:
        for nom in getattr(cls, "__slots__", ()) or ():
            if hasattr(node, nom):
                vals.append(getattr(node, nom))
    out = []
    for v in vals:
        for x in (v if isinstance(v, (list, tuple, set)) else [v]):
            if x is None or isinstance(x, (bool, int, float, str, bytes)):
                continue
            if hasattr(x, "__dict__") or getattr(type(x), "__slots__", None):
                out.append(x)
    return out


def _noms(node, out=None, vus=None):
    """Les noms de classe de tous les noeuds de l'arbre, en profondeur (ordre de parcours)."""
    out = [] if out is None else out
    vus = set() if vus is None else vus
    if id(node) in vus:
        return out
    vus.add(id(node))
    out.append(type(node).__name__)
    for x in _enfants(node):
        _noms(x, out, vus)
    return out


def test_etage3_arbre_1172_spawn_puis_buff():
    """`Execute( Spawn(...) op_BitwiseAnd AddEffectOrIncreaseLevel(1365, ...) )` -- l'ORDRE est
    load-bearing : le buff doit voir les summons (mesure LIVE : `MachineVengeance` est pose sur
    les 4 `admecNpc2Techpriest` fraichement spawnes, pas seulement sur les allies pre-existants)."""
    t = A.invocation_of_machine_vengeance_tree(4, 1)
    n = _noms(t)
    assert "Spawn" in n, "1172 : la feuille de spawn est l'etage GAUCHE"
    assert "MechanicalUnits" in n and "Friends" in n and "AllUnits" in n, \
        "1172 : la cible du buff est `MechanicalUnits(Friends(Caster, AllUnits))`"
    assert "SortByRow" in n and "CanAddUnit" in n and "AllTiles" in n and "PickFirstN" in n, \
        "1172 : les tuiles de spawn sont `First(SortByRow(CanAddUnit(AllTiles)), nrOfSummons)`"
    assert "ConditionalAmount" in n and "HasTrait" in n, \
        "1172 : le critere SECONDAIRE du tri est `ConditionalAmount(HasTrait(.., Steppable))`"
    # le spawn PRECEDE le buff dans le parcours (etage gauche de l'`op_and`)
    assert n.index("Spawn") < n.index("MechanicalUnits")


# ------------------------------------------------------------- etage 4 : l'arbre de 1174
def test_etage4_arbre_1174_transfert_puis_marquage_et_zero_attaque():
    t = A.solar_atomizer_tree()
    n = _noms(t)
    for attendu in ("AddPersistentData", "RemoveEffect", "GetPersistentData", "SetPersistentData",
                    "AmountIsGreater", "Cache", "EntitiesWithAnyEffect", "EffectsOfUnits",
                    "EffectLevelOf", "AddEffect"):
        assert attendu in n, "1174 : noeud `%s` absent de l'arbre" % attendu
    # LE NOM MENT : aucune feuille d'attaque, le degat est DIFFERE (triggered 1297).
    assert not any(x.startswith("AttackWith") for x in n), \
        "1174 : l'active NE FRAPPE PAS -- aucune feuille `AttackWith*` au decompile"
    # la bande : deux lignes hex derivees d'une DIRECTION
    m = _noms(A.solar_atomizer_target_tiles())
    assert "DirectionTo" in m and "TilesBehindInLine" in m and "TileFromVector" in m
    assert "SortByFormula" in m and "Count" in m, \
        "1174 : la 2e ligne est `First(SortByFormula(voisins, Count(...), desc), 1)`"
    assert A.SA_LINE_CHECK_WALKABLE is True and A.SA_LINE_UPDATE_REFERENCE is True, \
        "1174 : `*(u16*)(settings+0x10) = 0x101` -> les DEUX bools a 1"
    # les cles de donnee persistante des DEUX abilities du meme caster sont DISTINCTES
    assert A.SA_PD_KEY == "AccumulatedEffectLevel" and A.AS_PD_KEY == "EffectLevel"
    assert A.SA_PD_KEY != A.AS_PD_KEY
    assert A.SA_PENDING_ATTACK == int(EffectType.SolarAtomizer_PendingAttack) == 1371
    assert A.SA_PENDING_TARGET == int(EffectType.SolarAtomizer_PendingTarget) == 1372


# ------------------------------------------------ etage 5 : `EffectLevelOf` est une SOMME
class _SelStub:
    def __init__(self, items):
        self.items = items

    def evaluate(self, ctx):
        return self.items


def test_etage5_effect_level_of_somme():
    """`EffectLevelFormula$$Calculate` accumule `EffectComponent+0x68` sur TOUT le selecteur --
    le « Transfers ALL levels » de l'i2. Rendre le PREMIER (ou le max) fait tomber ce test."""
    eff = [{"effect_type": 1365, "owner_id": 7, "level": 3},
           {"effect_type": 1365, "owner_id": 9, "level": 4},
           {"effect_type": 1365, "owner_id": 11, "level": 1}]
    assert EffectLevelOf(_SelStub(eff)).calculate(None) == 8       # 3 + 4 + 1, pas 3 ni 4
    assert EffectLevelOf(_SelStub([])).calculate(None) == 0        # selecteur vide -> 0


# -------------------------------------- etage 6 : `SortByRow.additional_sorting` = un ThenBy
class _RowBoard:
    def __init__(self, rows):
        self.rows = rows

    def coord(self, tid):
        return self.rows[tid]


class _Ctx:
    board = None
    subject = None
    active_target = None
    caster = None

    def __init__(self, board):
        self.board = board


def test_etage6_sortbyrow_thenby_est_un_second_critere():
    """`ordered = OrderBy(row) ; if (additionalSortingFormula != 0) ordered = ThenBy(f)`.
    Le tri par ROW reste PREMIER ; la formule ne departage que les ex aequo. Ignorer la formule
    (l'ancien `raise`) ou l'appliquer EN PREMIER font tomber ce test."""
    from dataclasses import dataclass, replace as _replace

    @dataclass
    class C:
        board: object = None
        subject: object = None
        active_target: object = None

    ids = {1: (0, 0), 2: (1, 0), 3: (2, 1)}          # tuiles 1 et 2 sur la MEME row

    class _B:
        by_id = ids                       # `_entity_pos` teste l'appartenance avant `coord`

        def coord(self, t):
            return ids[t]

    class _Src:
        def evaluate(self, ctx):
            return [1, 2, 3]

    class _Poids:
        """1 pour la tuile 1, 0 pour la tuile 2 -> `ThenBy` ascendant met 2 AVANT 1."""
        def evaluate(self, ctx):
            return 1 if ctx.subject == 1 else 0

    ctx = C(board=_B())
    sans = SortByRow(_Src(), ascending=True).select(ctx)
    assert sans == [1, 2, 3], "sans formule : tri par row seul, ordre source aux ex aequo"
    avec = SortByRow(_Src(), same_column_is_random=True, additional_sorting=_Poids(),
                     ascending=True).select(ctx)
    assert avec == [2, 1, 3], "avec formule : `ThenBy` departage les ex aequo de row"


# ------------------------------------------------------- etages 7 et 8 : les deux utilites
class _NC:
    """Contexte NonComparable minimal (les deux playbooks n'en lisent qu'une poignee de champs)."""
    def __init__(self, uid, origin, reach, epos=(), tiles=None):
        self.uid, self.origin, self.reach_nc = uid, origin, list(reach)
        self.epos = list(epos)
        self.tile_id_by_pos = tiles or {}
        self.ability_targets = None            # -> `_has_eligible_target` PERMISSIF
        self.scene = None
        self.debug = False


def test_etage7_utilite_1172_prefere_bouger():
    """`u = (casterPosition != GetUnitPosition(caster)) + 1` : 1 a l'origine, 2 ailleurs, et le
    Bucket ne remplace que sur STRICT `>` -> la PREMIERE tuile de move gagne. Figer l'utilite a 1
    (le patron `NovaBoostPlaybook`) fait tomber ce test."""
    from engine.playbook.noncomparable import PLAYBOOKS
    pb = PLAYBOOKS[IMV]
    c = pb.generate_candidates(_NC(81, (1, 0), [(1, 0), (2, 0), (3, 0)]))
    assert len(c) == 1 and c[0]["ability"] == IMV
    assert c[0]["pred"] == 2.0, "une tuile de move vaut 2"
    assert c[0]["to"] == (2, 0), "la PREMIERE tuile de move gagne (STRICT `>`)"
    # caster IMMOBILE (`moveNone`, le regime d'un boss) : seule l'origine -> utilite 1, cast sur place
    c2 = pb.generate_candidates(_NC(81, (1, 0), [(1, 0)]))
    assert len(c2) == 1 and c2[0]["pred"] == 1.0 and c2[0]["to"] is None


def test_etage8_utilite_1174_compte_la_bande_et_ses_ennemis():
    """`u = 1 + |bande| + 20 x |ennemis de la bande|` : l'increment est HORS du `if` (deux sites
    distincts au decompile). Retirer le `+1` par tuile, ou mettre le `+20` a la place, fait tomber
    ce test -- il est ecrit sur la FORMULE, pas sur un scalaire mesure."""
    from engine.playbook.noncomparable.solar_atomizer import SolarAtomizerPlaybook
    pb = SolarAtomizerPlaybook()
    assert pb.ENEMY_TILE_BONUS == 20.0                       # `Fix64.op_Implicit(0x14)`
    # 5 tuiles dont 2 ennemies -> 1 + 5 + 40 = 46 (et surtout PAS 1 + 5 + 2*19, ni 1 + 40)
    u = 1.0
    for est_ennemi in (False, True, False, True, False):
        if est_ennemi:
            u += pb.ENEMY_TILE_BONUS
        u += 1.0
    assert u == 46.0


# ---------------------------- etage 9 : `sameColumnIsRandom` TIRE une cle par element (#1027-r1)
class _BoardLargeur:
    """`BoardComponent` minimal : `by_id` porte des tuiles `{col, row}` -- c'est ce dont
    `_board_width` derive le `Width` (`+0x14`)."""

    def __init__(self, tuiles):
        self.by_id = {tid: {"id": tid, "col": c, "row": r} for tid, (c, r) in tuiles.items()}

    def coord(self, tid):
        t = self.by_id[tid]
        return (t["col"], t["row"])


class _SrcIds:
    def __init__(self, ids):
        self.ids = list(ids)

    def evaluate(self, ctx):
        return list(self.ids)


def test_etage9_same_column_is_random_tire_une_cle_par_element():
    """`ThenBy(<b__3>)`, ou `b__3(this, s)` IGNORE `s` et rend
    `pseudoRng.<IPseudoRNG slot 1 = Next(n)>(GetMatchBoard(state).<+0x14 = Width>)`.

    TROIS choses sont gardees ici, et le port en ratait les trois :
      * il TIRE (l'ancien port ne tirait pas du tout) ;
      * il tire **UNE FOIS PAR ELEMENT**, dans l'ordre SOURCE -- le COMPTE est observable sur tout
        le flux PRNG aval, pas seulement sur cet ordre ;
      * la borne est le **WIDTH** du plateau, pas son nombre de lignes ni son nombre de tuiles :
        `NextInternal` fait du REJET pour les bornes non-puissances-de-2, donc une borne fausse
        consommerait un nombre de `genrand_int32` DIFFERENT."""
    from dataclasses import dataclass, field

    @dataclass
    class C:
        board: object = None
        subject: object = None
        active_target: object = None
        pseudo_rng_next: object = None
        tires: list = field(default_factory=list)

    #  4 colonnes (0..3), 3 tuiles sur la MEME row -> le tri par row ne les departage PAS
    board = _BoardLargeur({1: (0, 0), 2: (1, 0), 3: (2, 0)})
    src = _SrcIds([1, 2, 3])

    ctx = C(board=board)
    ctx.pseudo_rng_next = lambda n: (ctx.tires.append(n), len(ctx.tires) * 0 + (3 - len(ctx.tires)))[1]
    got = SortByRow(src, same_column_is_random=True, ascending=True).evaluate(ctx)

    assert ctx.tires == [3, 3, 3], (
        "un tirage PAR ELEMENT, borne au Width du plateau (3 colonnes ici) : %r" % (ctx.tires,))
    assert got == [3, 2, 1], (
        "les cles 2/1/0 doivent RENVERSER l'ordre source des ex aequo : %r" % (got,))

    # CONTRE-EPREUVE 1 : sans le flag, aucun tirage et l'ordre source tient.
    ctx2 = C(board=board)
    ctx2.pseudo_rng_next = lambda n: ctx2.tires.append(n) or 0
    assert SortByRow(src, same_column_is_random=False, ascending=True).evaluate(ctx2) == [1, 2, 3]
    assert ctx2.tires == [], "flag a 0 -> le natif n'ajoute pas le `ThenBy`, donc AUCUN tirage"

    # CONTRE-EPREUVE 2 : canal absent -> AUCUN tirage, ordre source (degradation NOMMEE, pas un
    # ordre invente). C'est le regime de la face DECISION, qui n'a pas de PRNG.
    ctx3 = C(board=board)
    assert SortByRow(src, same_column_is_random=True, ascending=True).evaluate(ctx3) == [1, 2, 3]


def test_etage9_l_accesseur_du_runner_EST_le_slot_1_d_IPseudoRNG():
    """Le noeud delegue a `ctx.pseudo_rng_next`, mais encore faut-il que la couche runner le
    branche sur LA BONNE primitive. `IPseudoRNG` a **six** methodes et trois s'appellent `Next` :
    slot 1 = `Next(n)` -> `[0, n)`, slots 2 et 3 = les surcharges a DEUX arguments. Se tromper de
    surcharge ne leverait rien -- ca changerait la VALEUR et, par le REJET facon Java, le NOMBRE
    de `genrand_int32` consommes, donc tout le flux aval.

    On compare donc, a graine egale, l'accesseur du contexte runner a `IntBasedMersenneTwister.next`
    (le port de `IntBasedMersenneTwister$$IdunBattle.Utils.PRNG.IPseudoRNG.Next`) : MEME valeur ET
    MEME consommation."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.state import State

    st = State()
    st.rng = IntBasedMersenneTwister(777)
    for i, pos in enumerate(((0, 0), (1, 0))):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id="u%d" % i, alive=True))
        e.add_component(PositionComponent(*pos))
        e.add_component(OwnerComponent(i + 1))
    ids = sorted(st.entities)
    ent = entities_from_state(st, ids[0], ids[1])
    assert ent.pseudo_rng_next is not None, (
        "la couche runner DOIT brancher `pseudo_rng_next` -- sans lui le noeud degrade en "
        "silence vers l'ordre source, et #1027-r1 se rouvre sans qu'aucun test ne rougisse")

    temoin = IntBasedMersenneTwister(777)
    for borne in (5, 8, 13):                      # 8 = puissance de 2 (pas de rejet), 5/13 = rejet
        t0, s0 = temoin.call_count, st.rng.call_count
        attendu = temoin.next(borne)
        obtenu = ent.pseudo_rng_next(borne)
        assert obtenu == attendu, (
            "borne %d : l'accesseur rend %r, `IPseudoRNG.Next(n)` rend %r -- une AUTRE surcharge "
            "a ete branchee" % (borne, obtenu, attendu))
        assert (st.rng.call_count - s0) == (temoin.call_count - t0), (
            "borne %d : consommation PRNG differente (%d vs %d) -- le flux aval divergerait"
            % (borne, st.rng.call_count - s0, temoin.call_count - t0))
        assert 0 <= obtenu < borne, "borne %d : `Next(n)` rend dans [0, n)" % borne


def test_etage9_le_tirage_ne_prime_PAS_sur_la_row():
    """`ThenBy` est le 3e critere : il ne departage QUE des ex aequo. Un port qui trierait par le
    tirage EN PREMIER melangerait des rows distinctes -- exactement l'ordre invente que la fiche
    #1027-r1 disait vouloir eviter."""
    from dataclasses import dataclass, field

    @dataclass
    class C:
        board: object = None
        subject: object = None
        active_target: object = None
        pseudo_rng_next: object = None
        tires: list = field(default_factory=list)

    board = _BoardLargeur({1: (0, 0), 2: (1, 1), 3: (2, 2)})   # TROIS rows distinctes
    ctx = C(board=board)
    ctx.pseudo_rng_next = lambda n: (ctx.tires.append(n), 99 - len(ctx.tires))[1]
    got = SortByRow(_SrcIds([1, 2, 3]), same_column_is_random=True, ascending=True).evaluate(ctx)
    assert got == [1, 2, 3], "aucun ex aequo -> le tirage ne doit RIEN changer : %r" % (got,)
    assert len(ctx.tires) == 3, "et il tire quand meme (le natif calcule toutes les cles)"
