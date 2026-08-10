"""#564 -- le PIPELINE de RESURRECTION, etage par etage (cliquet OFFLINE, aucun runner).

Le test LIVE (`tests/engine/runner/test_564_rites_of_restoration_live.py`) montre qu'UNE
resurrection tombe au bon endroit avec les bons PV. Il ne peut pas montrer que chaque ETAGE du natif
existe et qu'il est branche DANS LE BON ORDRE : un montage a UNE cible et UNE tuile est justement
celui ou le zip, le pre-filtre et le gate se confondent tous avec « ca marche ». Ce fichier separe
ce que le live confond.

Les etages, dans l'ordre du decompile :

    IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute
      0. hp = <+0x60>.Calculate(entities)                      -- evalue UNE fois, AVANT les selecteurs
      1. targets = <+0x50>.Select(entities)
      2. ListExtensions.Remove(targets, !IsValidTarget)        -- DECALE l'appariement du zip
      3. tiles   = <+0x58>.Select(entities)
      4. zip borne par Math.Min(|targets|, |tiles|)
      5. processor.ResurrectUnit(targets[i], healType, tiles[i], hp, abilityType, options)

    IdunBattle.Operations.ResurrectUnitOperation$$Execute
      a. IsDefeated(unit)                                      -- sortie SANS mutation
      b. battleQuery.CanBeResurrected(unit, healType)          -- sortie SANS mutation
      c. UpdateFlags / SetHealth (FillUp)
      d. options ? RemoveTurnFlags(1,1) : MarkUnitAsNoActionAvailable(unit)

    IdunBattle.Core.Services.BattleQuery$$CanBeResurrected
      i.   HasFlag(0x16 PreventResurrect)   -> false
      ii.  !HasFlag(9 Fled) => GetStat(Health) > 0 -> false ; !HasFlag(6 Dead) -> false
      iii. IsAffectedByHealType(healType) && !HasTrait(0x41a PermaDeath)

Et les DEUX donnees obligatoires du registre, FIGEES au litteral du ctor : le masque `0x8508` de
`RitesOfRestorationAbility$$.ctor` et son `AbilityAttackType` (le 3e argument, `2 = Others`).

ASCII only (console cp1252).
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LA FEUILLE, L'OPERATION, LE GATE -- les trois etages que ce fichier separe.
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/runner/components.py",
        # LES DEUX DONNEES DU REGISTRE, figees ici au litteral du ctor.
        "scripts/python/engine/runner/abilities/sisterhood.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        # L'AUTRE call-site de l'Operation : son `heal_type` explicite est ce qui l'empeche
        # d'heriter du defaut restrictif.
        "scripts/python/engine/runner/operations/triggers/genestealer.py",
        # ⚠ ELARGI : la liste ci-dessus dit OU regarder ; les deux globs disent ce qui fait
        # vraiment changer d'avis (importer `lifecycle` tire tout le paquet `runner`). Les DEUX
        # formes sont necessaires : `**/` exige un SEGMENT.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "La feuille `Resurrect`, l'Operation qu'elle appelle, le gate `CanBeResurrected` et "
              "les deux donnees du registre de 1039. Aucun runner, aucun canal live -> `build: "
              "False` : le verdict ne depend que de l'arbre.",
}

import pytest

from engine.dsl.effects import ExecutionContext
from engine.entities.selectors.units import UnitSet
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_flag import UnitFlag
from engine.runner.abilities.attack_query import can_be_resurrected
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.lifecycle import Resurrect
from engine.runner.abilities.sisterhood import RitesOfRestorationAbility
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations.resurrect import ResurrectUnitOperation
from engine.runner.state import State

HP_MAX = 1000


class _Ctx:
    """Le minimum de `UnitContext` que `targeting._unit_traits` lit : la liste de traits."""
    def __init__(self, traits):
        self.traits = list(traits)
        self.active_ability_level = 1
        self.ability_variables_multiplier = 100


def _unite(st: State, *, alive: bool, hp: int, traits=(), flags=(), pos=(0, 0)) -> int:
    e = st.add_entity()
    e.add_component(HealthComponent(hp, HP_MAX))
    e.add_component(UnitComponent("u", alive))
    fl = e.add_component(UnitFlagsComponent())
    for f in flags:
        fl.add(int(f))
    e.add_component(StatsComponent(ctx=_Ctx(traits)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return max(st.entities)


# --------------------------------------------------------------------------------------------
# 1. `BattleQuery$$CanBeResurrected` -- les trois etages, chacun discriminant
# --------------------------------------------------------------------------------------------

def test_gate_accepte_un_mort_ordinaire():
    """La ligne de base : mort (alive=False, PV 0), non-mecanique, sans flag ni trait bloquant."""
    st = State()
    uid = _unite(st, alive=False, hp=0)
    assert can_be_resurrected(st, uid, 0) is True


def test_gate_refuse_une_unite_vivante_a_pv_positifs():
    """`if (!fled) { if (GetStat(Health) > 0) return false; }` -- une unite DEBOUT n'est pas
    ressuscitable, et c'est ce test-la (pas `IsDefeated`) qui le dit dans le gate."""
    st = State()
    uid = _unite(st, alive=True, hp=HP_MAX)
    assert can_be_resurrected(st, uid, 0) is False


def test_gate_refuse_le_flag_PreventResurrect():
    """`if (HasFlag(target, 0x16 PreventResurrect)) return false;` -- le PREMIER test du natif, et
    le seul qui coupe AVANT la branche `fled`."""
    st = State()
    uid = _unite(st, alive=False, hp=0, flags=(UnitFlag.PreventResurrect,))
    assert can_be_resurrected(st, uid, 0) is False


def test_gate_refuse_le_trait_PermaDeath():
    """`return IsAffectedByHealType(...) && !HasTrait(target, 0x41a PermaDeath);` -- la conjonction
    de queue. Sans elle, une unite marquee « morte pour de bon » reviendrait."""
    st = State()
    uid = _unite(st, alive=False, hp=0, traits=("PermaDeath",))
    assert can_be_resurrected(st, uid, 0) is False


def test_le_healType_separe_mecaniques_et_non_mecaniques():
    """`IsAffectedByHealType(unit, healType)` : `0` EXCLUT les mecaniques, `1` n'accepte QU'ELLES,
    `2` (le litteral de l'Ambush genestealer) ne filtre RIEN.

    C'est l'etage qui separe `RitesOfRestoration` (healType 0, i2 « Only affects non-Mechanical
    units ») de `ResurrectionOrb` (healType 1, heros MECANIQUES) : les confondre inverserait
    exactement l'ensemble des cibles."""
    st = State()
    mech = _unite(st, alive=False, hp=0, traits=("Mechanical",))
    chair = _unite(st, alive=False, hp=0)
    assert can_be_resurrected(st, mech, 0) is False, "healType 0 doit EXCLURE une mecanique"
    assert can_be_resurrected(st, mech, 1) is True, "healType 1 doit ACCEPTER une mecanique"
    assert can_be_resurrected(st, chair, 0) is True
    assert can_be_resurrected(st, chair, 1) is False, "healType 1 doit EXCLURE une non-mecanique"
    for u in (mech, chair):
        assert can_be_resurrected(st, u, 2) is True, "healType 2 ne filtre RIEN (Ambush)"


def test_le_gate_est_EN_TETE_de_l_operation_et_sort_sans_muter():
    """`ResurrectUnitOperation$$Execute` sort sur le gate SANS aucune mutation : ni position, ni
    `alive`, ni PV, ni flags. C'est le mode de panne que #564 ferme (l'Operation mutait sans jamais
    consulter `CanBeResurrected`)."""
    st = State()
    uid = _unite(st, alive=False, hp=0, traits=("Mechanical",), pos=(3, 3))
    r = ResurrectUnitOperation.execute(st, uid, (5, 5), 400, immediate_turn=False, heal_type=0)
    e = st.get_entity(uid)
    assert r is None, "l'Operation a rendu un resultat malgre le gate : %s" % (r,)
    assert e.get_component(UnitComponent).alive is False
    assert e.get_component(HealthComponent).hp == 0
    assert (e.get_component(PositionComponent).col,
            e.get_component(PositionComponent).row) == (3, 3), "la position a bouge malgre le gate"


# --------------------------------------------------------------------------------------------
# 2. Les DEUX bras du `if (options)` de queue
# --------------------------------------------------------------------------------------------

def test_sans_tour_immediat_l_unite_est_marquee_sans_action():
    """`if (!options) processor.<slot 0x23>(unit, 1)` =
    `MarkUnitAsNoActionAvailableOperation$$Execute` -- le « unable to act on this turn » de l'i2 de
    1039. Sans ce bras, le ressuscite pourrait JOUER le tour de son retour."""
    st = State()
    uid = _unite(st, alive=False, hp=0)
    r = ResurrectUnitOperation.execute(st, uid, (1, 1), 400, immediate_turn=False, heal_type=0)
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert r is not None and r["no_action"] is not None
    assert fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE), (
        "le flag NoActionAvailable n'est pas pose -- le bras `!options` est absent")


def test_avec_tour_immediat_les_flags_de_tour_sont_RETIRES():
    """L'AUTRE bras (`RemoveTurnFlags(unit, 1, 1)`), celui que prend l'Ambush genestealer. Les deux
    sont EXCLUSIFS : un port qui poserait `NoActionAvailable` dans les deux cas casserait le tour
    immediat d'Ambush."""
    st = State()
    uid = _unite(st, alive=False, hp=0, flags=(UnitFlagsComponent.NO_ACTION_AVAILABLE,))
    r = ResurrectUnitOperation.execute(st, uid, (1, 1), 400, immediate_turn=True, heal_type=2)
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert r is not None and r["no_action"] is None
    assert not fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE), (
        "NoActionAvailable persiste malgre `takesImmediateTurn` -- le tour immediat est mort")


# --------------------------------------------------------------------------------------------
# 3. La feuille `Resurrect` : le ZIP et le PRE-FILTRE
# --------------------------------------------------------------------------------------------

class _Board:
    """Le minimum de `Board` que la feuille ET l'Operation lisent. Les ids de tuile sont ici les
    entiers 10, 11, 12 -- ce que rendent `AdjacentTiles`/`CanAddUnit` en domaine ID.

    ⚠ `id_at` / `walkable` ont ete AJOUTES par #564-r3 : l'Operation evalue desormais le gate
    `TilesAreWalkable` (`BattleQuery` slot 0xa1), qui les appelle. Un board de test qui ne les
    porte pas fait LEVER `AttributeError` -- ce qui est le bon signal (le gate est bien joue), pas
    une raison de rendre le gate permissif. Toutes les tuiles du mapping sont marchables : ce
    fichier mesure le ZIP et le PRE-FILTRE, pas le substrat de tuile."""
    def __init__(self, mapping):
        self._m = dict(mapping)
        self._rev = {(int(c), int(r)): int(t) for t, (c, r) in self._m.items()}

    def coord(self, tid):
        return self._m[int(tid)]

    def id_at(self, col, row):
        return self._rev.get((int(col), int(row)))

    def walkable(self, tid):
        return int(tid) in self._m


def _live(st, uid):
    """La vue `dict` d'unite que consomment les selecteurs (`UnitSet` prend des dicts)."""
    e = st.get_entity(uid)
    p = e.get_component(PositionComponent)
    sc = e.get_component(StatsComponent)
    return {"id": uid, "alive": e.get_component(UnitComponent).alive,
            "hp": e.get_component(HealthComponent).hp, "team": 1,
            "pos": {"col": p.col, "row": p.row},
            "traits": list(sc.ctx.traits)}


def _run_leaf(st, targets, tiles, board, hp=400, heal_type=0, immediate=False):
    from engine.dsl.base import DslContext
    from engine.entities.selectors.accessors import FixedTileIds
    # LE MEME board des DEUX cotes -- c'est ce que fait `entities_from_state` (`board=state.board`).
    # La feuille convertit l'ID de tuile en COORDONNEE par `state.board` : sans lui, `dest_coord`
    # est `None` et l'unite ressuscite SUR PLACE, sans erreur.
    st.board = board
    ctx = DslContext(units=[_live(st, u) for u in st.entities], board=board,
                     caster=_live(st, min(st.entities)))
    leaf = Resurrect(UnitSet([_live(st, u) for u in targets]), FixedTileIds(list(tiles)), hp,
                     heal_type=heal_type, immediate_turn=immediate)
    ectx = ExecutionContext(state=st, rng=st.rng)
    leaf.execute(ctx, ectx)
    return [p for n, p in ectx.emitted if n == "Resurrect"][0]


def test_le_zip_est_borne_par_le_min_des_deux_listes():
    """`n = Math.Min(targets.Count, tiles.Count)` -- TROIS cibles, DEUX tuiles : deux resurrections,
    et la 3e cible reste morte. Un port qui bouclerait sur les cibles en cherchant une tuile en
    ressusciterait trois."""
    st = State()
    a = _unite(st, alive=False, hp=0, pos=(0, 0))
    b = _unite(st, alive=False, hp=0, pos=(0, 1))
    c = _unite(st, alive=False, hp=0, pos=(0, 2))
    board = _Board({10: (5, 5), 11: (6, 6), 12: (7, 7)})
    out = _run_leaf(st, [a, b, c], [10, 11], board)
    got = [(r["resurrected"], tuple(r["tile"])) for r in out["resurrections"]]
    assert got == [(a, (5, 5)), (b, (6, 6))], got
    assert st.get_entity(c).get_component(UnitComponent).alive is False, (
        "la 3e cible est revenue alors qu'il n'y avait que DEUX tuiles")


def test_le_prefiltre_IsValidTarget_DECALE_l_appariement():
    """`ListExtensions.Remove(targets, !IsValidTarget)` s'applique AVANT le zip, donc une cible
    ecartee NE CONSOMME PAS sa tuile.

    Discriminant : la 1re cible est VIVANTE (donc ecartee). Si le filtre vivait en aval, dans
    l'Operation, la 2e cible prendrait la tuile d'INDEX 1 ; comme il vit dans la feuille, elle prend
    la tuile d'INDEX 0. Les deux ports ressuscitent la meme unite -- seule la TUILE les separe, et
    c'est exactement ce que le test live confronte au natif."""
    st = State()
    vivant = _unite(st, alive=True, hp=HP_MAX, pos=(0, 0))
    mort = _unite(st, alive=False, hp=0, pos=(0, 1))
    board = _Board({10: (5, 5), 11: (6, 6)})
    out = _run_leaf(st, [vivant, mort], [10, 11], board)
    got = [(r["resurrected"], tuple(r["tile"])) for r in out["resurrections"]]
    assert got == [(mort, (5, 5))], (
        "appariement %s : la cible ecartee a consomme sa tuile (filtre place en AVAL)" % got)


def test_le_prefiltre_ecarte_AUSSI_ce_que_le_gate_refuse():
    """`IsValidTarget` = `IsDefeated(t) && CanBeResurrected(t, healType)` -- les DEUX conjoints. Une
    cible MORTE mais MECANIQUE sous `healType 0` est ecartee au meme titre qu'une vivante, donc elle
    ne consomme pas de tuile non plus."""
    st = State()
    mech = _unite(st, alive=False, hp=0, traits=("Mechanical",), pos=(0, 0))
    chair = _unite(st, alive=False, hp=0, pos=(0, 1))
    board = _Board({10: (5, 5), 11: (6, 6)})
    out = _run_leaf(st, [mech, chair], [10, 11], board)
    got = [(r["resurrected"], tuple(r["tile"])) for r in out["resurrections"]]
    assert got == [(chair, (5, 5))], got


def test_le_montant_de_PV_est_evalue_une_seule_fois():
    """`hp = <+0x60>.Calculate(entities)` est HORS de la boucle : deux ressuscites recoivent le MEME
    montant, et le noeud n'est evalue qu'UNE fois (contre-epreuve : un `amount_fn` compteur)."""
    st = State()
    a = _unite(st, alive=False, hp=0, pos=(0, 0))
    b = _unite(st, alive=False, hp=0, pos=(0, 1))
    board = _Board({10: (5, 5), 11: (6, 6)})
    appels = []

    def _hp(entities, ectx):
        appels.append(1)
        return 400
    out = _run_leaf(st, [a, b], [10, 11], board, hp=_hp)
    assert len(appels) == 1, "le noeud MONTANT a ete evalue %s fois, attendu 1" % len(appels)
    assert out["hp"] == 400
    assert all(st.get_entity(u).get_component(HealthComponent).hp == 400 for u in (a, b))


# --------------------------------------------------------------------------------------------
# 4. Le selecteur `Healable` -- il DELEGUE, et il porte le CASTER
# --------------------------------------------------------------------------------------------

def test_healable_garde_les_blesses_et_ecarte_les_pleins_PV():
    """`HealableUnitsSelector$$Select` = `EntityCanBeHealed(caster, u, scope, removeEffects 1)` par
    unite. Le discriminant est `AttackQuery$$IsDamagedUnit` : une cible a PLEINS PV n'est PAS
    soignable (et c'est ce qui rend `GetHealTargets` VIDE au tour 1 -- l'observable du regime t0 du
    test live)."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.units import Healable
    st = State()
    caster = _unite(st, alive=True, hp=HP_MAX)
    blesse = _unite(st, alive=True, hp=HP_MAX // 2)
    plein = _unite(st, alive=True, hp=HP_MAX)

    def _ecbh(healer, target, scope, remove_effects):
        from engine.runner.abilities.attack_query import entity_can_be_healed
        return entity_can_be_healed(st, (healer or {}).get("id"), (target or {}).get("id"),
                                    scope=scope, remove_effects=remove_effects)
    ctx = DslContext(units=[_live(st, u) for u in st.entities], caster=_live(st, caster),
                     entity_can_be_healed=_ecbh)
    got = [u["id"] for u in Healable(UnitSet([_live(st, u) for u in (caster, blesse, plein)])
                                     ).evaluate(ctx)]
    assert got == [blesse], "Healable = %s, attendu [%s] (le seul blesse)" % (got, blesse)


def test_healable_sans_accesseur_rend_VIDE_jamais_tout():
    """Degradation NOMMEE : sans `ctx.entity_can_be_healed` (contexte hors runner), le noeud rend
    `[]` -- jamais un « tout passe » qui ferait soigner des cibles que le natif refuse."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.units import Healable
    st = State()
    blesse = _unite(st, alive=True, hp=1)
    ctx = DslContext(units=[_live(st, blesse)], caster=_live(st, blesse))
    assert Healable(UnitSet([_live(st, blesse)])).evaluate(ctx) == []


def test_healable_passe_bien_le_CASTER_au_gate():
    """L'ASYMETRIE avec `Repairable` : le selecteur HEALABLE appelle la surcharge a QUATRE arguments
    (caster en tete), pas la 3-args. Contre-epreuve : on substitue un accesseur qui EXIGE un caster
    non nul -- un port qui recopierait le patron du jumeau (caster = None) rendrait `[]`."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.units import Healable
    st = State()
    caster = _unite(st, alive=True, hp=HP_MAX)
    cible = _unite(st, alive=True, hp=1)
    vus = []

    def _exige_caster(healer, target, scope, remove_effects):
        vus.append((healer or {}).get("id"))
        return (healer or {}).get("id") is not None
    ctx = DslContext(units=[_live(st, u) for u in st.entities], caster=_live(st, caster),
                     entity_can_be_healed=_exige_caster)
    got = [u["id"] for u in Healable(UnitSet([_live(st, cible)])).evaluate(ctx)]
    assert vus == [caster], "le caster transmis au gate = %s, attendu [%s]" % (vus, caster)
    assert got == [cible]


# --------------------------------------------------------------------------------------------
# 5. Les DEUX donnees obligatoires du registre, figees au LITTERAL du ctor
# --------------------------------------------------------------------------------------------

def test_le_masque_de_ciblage_est_celui_du_ctor():
    """`RitesOfRestorationAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 1, &<TargetingRange
    statics+0x30>, 1, 0x8508, 0, 0)` -- forme FLAGS DIRECTS, le litteral EST le masque.

    Fige la VALEUR (`0x8508`) ET sa decomposition : un renumerotage de `TargetingRule` ferait
    diverger les deux, et c'est ce qu'on veut voir."""
    o = RitesOfRestorationAbility.TARGETING_OPTIONS
    assert int(o.rules) == 0x8508, "masque %s, attendu 0x8508" % hex(int(o.rules))
    assert int(o.rules) == int(TR.AddCasterIfMatchesDynamicRule | TR.TargetIsHealable
                               | TR.TargetIsFriendly | TR.CasterIsPossibleTarget)
    assert o.self_cast is True, "isSelfCasting = 1 au ctor"


def test_l_attack_type_est_le_troisieme_argument_du_ctor():
    """`AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`. TRANSCRIT du ctor,
    jamais deduit du fait que l'arbre ne fait aucun degat."""
    assert (ABILITY_ATTACK_TYPE.get(RitesOfRestorationAbility.ABILITY_TYPE)
            == AbilityAttackType.Others)


def test_le_registre_de_masques_non_portes_ne_double_PAS_l_entree():
    """CONTRAT DE DISJONCTION : une ability a UNE source de masque. Depuis que 1039 porte sa face
    COMBAT, sa ligne doit avoir QUITTE `TARGETING_OPTIONS_UNPORTED`."""
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    assert RitesOfRestorationAbility.ABILITY_TYPE not in TARGETING_OPTIONS_UNPORTED


def test_le_littéral_refuse_du_gate_de_caster_est_TargetMatchesDynamicRule():
    """`GetDynamicInvalidCasterReason` rend le code de la regle-DELEGUE tel quel : ici `2`
    (`TargetingRule.TargetMatchesDynamicRule`), et surtout PAS `4`
    (`CasterMatchesDynamicRule`, ce que rend `FearOfTheUnseenAbility`). Le natif ecrit `2` pour une
    regle de CASTER -- on transcrit, on ne corrige pas."""
    st = State()
    _unite(st, alive=True, hp=HP_MAX)                      # le caster, seul et a pleins PV
    uid = min(st.entities)
    ab = RitesOfRestorationAbility()
    assert ab.get_dynamic_invalid_caster_reason(st, uid) == int(TR.TargetMatchesDynamicRule)
