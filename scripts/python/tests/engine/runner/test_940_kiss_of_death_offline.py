"""#940 -- GARDE OFFLINE du port de `KissOfDeath` (`ActiveAbilityType` 1108).

Le probe `probe_940_kiss_of_death_live.py` MESURE (il confronte au natif sur un runner) ; ce
fichier GARDE ce qui se garde SANS runner, et il garde en priorite ce dont l'echec serait
SILENCIEUX :

  [1] LE REGISTRE, ET SES DEUX DONNEES OBLIGATOIRES -- 1108 dans `ABILITY_CLASSES`, son
      `TARGETING_OPTIONS` et son `ABILITY_ATTACK_TYPE`, aux valeurs LUES au decompile. Sans le
      masque, `get_invalid_target_reason` rend 0 et le gate saute EN SILENCE.
  [2] LES ORDINAUX ECRITS AU SITE -- fige la valeur MESUREE a la conversion. `probe_313` compare le
      *mirror* au *build* et redevient vert des qu'on regenere le mirror ; c'est ici qu'un
      renumerotage se voit.
  [3] LE SUBSTRAT ORDONNE -- `ActorStatisticsComponent+0x40` est un `OrderedSet` NATIF, et son ORDRE
      est LU par `Last(...)` / `AtIndex(..., 1)`. Un `set` Python itere par HASH : l'ecart serait
      silencieux (une tuile d'atterrissage plausible, et fausse).
  [4] `PickLastN`, SES QUATRE REGIMES -- dont les deux que le decompile impose et qu'on ne devine
      pas : `n >= Count` rend la source ENTIERE, `n <= 0` rend VIDE des que la source ne l'est pas.
  [5] LE CHAMP QUI MUTE -- `unitsAttackedThisTurn` DOIT etre dans `_LIVE_KEYS`. Fige au seed, il
      rendrait toujours la liste d'AVANT la chaine, et l'atterrissage tomberait sur son 3e repli.
      C'est exactement le regime qu'on a MESURE avant correction (port (2,3) vs natif (2,4)).
  [6] LA FORME DE L'ARBRE -- quatre membres, dans l'ordre du decompile
      (`((AddEffect & Chain) & FlyUnit) & RemoveEffect`), sous un `AtomicGroup`.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LA CASCADE DES CONFTEST est DERIVEE par le foyer depuis #531 -- ne pas la recopier ici.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER, nomme -- ce fichier n'exerce QUE le port de 1108, ses deux selecteurs neufs,
        # son substrat ordonne et les trois registres.
        "scripts/python/engine/runner/abilities/aeldari.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/behaviours/chain.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # L'`__init__` du paquet `behaviours` : il est TRAVERSE par l'import des deux modules
        # ci-dessus, donc il fait partie du perimetre REEL. Son absence rendait ce fichier
        # `DECLARE TROP ETROIT` -- un declencheur trop etroit est un FAUX VERT (#486-r15) : le
        # fichier ne se rejoue pas quand ce qu'il garde a bouge.
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        # `PickLastN` a DEMENAGE dans ce module FEUILLE (#1032-r2) : sans lui, ce fichier ne se
        # rejouerait plus quand ce qu'il garde change -- un declencheur trop ETROIT est un FAUX
        # VERT. `geometry.py` ne fait plus que le re-exporter.
        "scripts/python/engine/entities/selectors/_pick.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/probe_940_kiss_of_death_live.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE : registre + masque + ordinaux + substrat ordonne + les deux "
              "selecteurs neufs + la forme de l'arbre. Aucun RPC, aucun runner -- la "
              "confrontation au natif vit dans `probe_940_kiss_of_death_live.py`.",
}

import pytest                                                                    # noqa: E402

from engine.dsl.base import Const                                                # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType            # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.effect_type import EffectType                               # noqa: E402
from engine.entities.selectors.geometry import AtIndex, PickLastN                # noqa: E402
from engine.entities.selectors.tiles import Caster                               # noqa: E402
from engine.entities.selectors.units import UnitsAttackedThisTurn                # noqa: E402
from engine.runner.abilities import aeldari as A                                 # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE              # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                      # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR           # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,           # noqa: E402
                                      PositionComponent, UnitComponent,
                                      register_attack_made,
                                      reset_units_attacked_this_turn)
from engine.runner.state import State                                            # noqa: E402
from engine.utilities.utility_type import UtilityType                            # noqa: E402


def _state(n: int = 6) -> State:
    st = State()
    for i in range(1, n + 1):
        e = st.add_entity(i)
        e.add_component(UnitComponent(visual_id="eldarNpc3Harlequin", alive=True))
        e.add_component(OwnerComponent(team=1 if i == 1 else 2, player=1 if i == 1 else 2))
        e.add_component(PositionComponent(col=i, row=1))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    return st


# --------------------------------- [1] LE REGISTRE -------------------------------------------
def test_940_registre_et_ses_deux_donnees_obligatoires():
    """1108 est au registre, avec son MASQUE et son `AbilityAttackType` -- les trois dans le meme
    commit. `TARGETING_OPTIONS` absent = `get_invalid_target_reason` rend 0, donc AUCUN gate."""
    cls = ABILITY_CLASSES.get(int(ActiveAbilityType.KissOfDeath))
    assert cls is A.KissOfDeathAbility, "1108 doit etre au registre (sinon : NO-OP silencieux)"
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "masque ABSENT -> le gate de ciblage saute EN SILENCE"
    # `<TargetingOptions statics>+0x68` = 0x4000, ecrit par `TargetingOptions$$.cctor`, recopie par
    # `KissOfDeathAbility$$.ctor` (forme « preset statique », aucun ctor appele).
    assert int(opts.rules) == 0x4000 == int(TR.TargetIsEnemy)
    assert opts.self_cast is False
    # `<TargetingRange statics>+0x30` : `onlyAdjacent = RangedBool.True`, `overrideRange = 1`.
    # ⚠ PAS `RANGE_FROM_CONFIG` (`statics+0x18`) : mesure du 2026-08-11, cette confusion faisait
    # accepter au port QUATRE ennemis plus le caster la ou le natif n'en accepte qu'UN.
    from engine.runner.abilities.targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    # `AActiveAbility$$.ctor(this, &opts, 0)` -- le 3e argument, TRANSCRIT.
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.KissOfDeath] == 0     # DirectTargetAttack


# --------------------------------- [2] LES ORDINAUX ------------------------------------------
@pytest.mark.parametrize("membre,attendu,ou", [
    (int(ActiveAbilityType.KissOfDeath), 1108, "`ComparablePlaybook..ctor(this, 0x454)`"),
    (int(EffectType.Untargetable), 1044, "`DSLBehaviors$$AddEffect(this, 0x414, ...)`"),
    (int(AbilityVariableType.dmg), 11, "`GetVariableForLevel(config, 0xb, ...)`"),
    (int(AbilityVariableType.maxAdjacentTargets), 0, "`DSLFormulas$$ConfigVar(this, 0x0, ...)`"),
    (int(AbilityConstantType.nrOfHits), 47, "`GetHits` -> `GetNumberConstant(0x2f)`"),
    (int(UtilityType.Tile), 7, "`SortTilesByUtility(..., 7, null)`"),
    (int(TR.TargetIsEnemy), 0x4000, "`<TargetingOptions statics>+0x68`"),
])
def test_940_ordinaux_ecrits_au_site(membre, attendu, ou):
    """Fige l'ordinal MESURE a la conversion. Un renumerotage de build le fait rougir ICI ; le
    mirror, lui, redeviendrait vert des qu'on le regenere."""
    assert membre == attendu, "ordinal glisse -- lu au site %s" % (ou,)


# ------------------------- [3] LE SUBSTRAT EST ORDONNE, ET C'EST LU ---------------------------
def test_940_units_attacked_this_turn_preserve_l_ordre_d_insertion():
    """`ActorStatisticsComponent+0x40` est un `idun.shared.collections.OrderedSet` : l'ORDRE
    d'insertion EST le contrat que lisent `Last(...)` et `AtIndex(..., 1)`."""
    st = _state()
    ent = A.entities_from_state(st, 1, 2)
    att = UnitsAttackedThisTurn(Caster())
    assert [u["id"] for u in att.evaluate(ent)] == []
    for t in (4, 2, 5, 4):                      # 4 est re-frappee : `OrderedSet$$Add` NE la remonte PAS
        register_attack_made(st, 1, t)
    assert [u["id"] for u in att.evaluate(ent)] == [4, 2, 5]
    assert [u["id"] for u in PickLastN(att, Const(1)).evaluate(ent)] == [5]
    assert [u["id"] for u in AtIndex(att, 1).evaluate(ent)] == [2]
    reset_units_attacked_this_turn(st, 1)       # `StartTurnOperation` / `ResetUnitsAttackedThisTurn`
    assert [u["id"] for u in att.evaluate(A.entities_from_state(st, 1, 2))] == []


# --------------------------- [4] `PickLastN`, SES QUATRE REGIMES ------------------------------
@pytest.mark.parametrize("n,attendu,pourquoi", [
    (1, [5], "les `n` DERNIERS, ordre preserve"),
    (2, [2, 5], "idem, n = 2"),
    (99, [4, 2, 5], "`n >= Count` -> la source ENTIERE (le `if` natif ne se declenche pas)"),
    (0, [], "`n <= 0` -> VIDE des que la source ne l'est pas (boucle de Count a Count)"),
])
def test_940_pick_last_n(n, attendu, pourquoi):
    """`IdunBattle.Entities.Selectors.PickLastNSelector$$Select`, terme a terme."""
    st = _state()
    ent = A.entities_from_state(st, 1, 2)
    for t in (4, 2, 5):
        register_attack_made(st, 1, t)
    att = UnitsAttackedThisTurn(Caster())
    assert [u["id"] for u in PickLastN(att, Const(n)).evaluate(ent)] == attendu, pourquoi


def test_940_pick_last_n_source_vide():
    """Source vide : `n >= 0 == Count` -> la source telle quelle, donc `[]`. C'est le regime dans
    lequel `KissOfDeath` bascule sur ses replis d'atterrissage."""
    st = _state()
    ent = A.entities_from_state(st, 1, 2)
    att = UnitsAttackedThisTurn(Caster())
    assert PickLastN(att, Const(1)).evaluate(ent) == []


# ------------------- [5] LE CHAMP MUTE PENDANT L'ARBRE QUI LE RELIT ---------------------------
def test_940_units_attacked_this_turn_est_une_cle_LIVE():
    """Sans cette entree, le dict d'unite est FIGE au seed : `UnitsAttackedThisTurn` rendrait la
    liste d'AVANT la chaine (donc vide), et `FlyUnit` atterrirait sur le 3e repli. Mesure du
    2026-08-11 avant correction : port (2,3) -- voisine de la CIBLE -- vs natif (2,4) -- voisine de
    la DERNIERE victime."""
    from engine.runner.abilities.behaviours import context as C
    assert "unitsAttackedThisTurn" in C._LIVE_KEYS
    st = _state()
    ent = A.entities_from_state(st, 1, 2)                 # contexte capture AVANT toute attaque
    att = UnitsAttackedThisTurn(Caster())
    assert att.evaluate(ent) == []
    register_attack_made(st, 1, 3)                        # mutation POSTERIEURE a la capture
    assert [u["id"] for u in att.evaluate(ent)] == [3], \
        "le MEME contexte doit voir la mutation -- c'est tout l'objet de `_LIVE_KEYS`"


# ------------------------------ [6] LA FORME DE L'ARBRE ---------------------------------------
def test_940_forme_de_l_arbre():
    """`ExecuteAtomic( ((AddEffect & Chain) & FlyUnit) & RemoveEffect, 0x2a )` -- quatre membres,
    dans CET ordre. L'`AddEffect` est le PREMIER (le Harlequin disparait AVANT de frapper) et le
    `RemoveEffect` le DERNIER (il reapparait APRES avoir vole)."""
    from engine.entities.behaviours import AtomicGroup, Seq
    from engine.runner.abilities.behaviours.chain import ChainAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect, RemoveEffect
    from engine.runner.abilities.behaviours.movement import FlyUnit
    tree = A.kiss_of_death_tree(dmg=1280, hits=1, max_targets=2)
    assert isinstance(tree, AtomicGroup), "`ExecuteAtomic(..., GroupType 0x2a)`"
    seq = tree.child
    membres = []
    while isinstance(seq, Seq):                            # `op_BitwiseAnd` gauche-associatif
        membres.append(seq.right)
        seq = seq.left
    membres.append(seq)
    membres.reverse()
    assert [type(m).__name__ for m in membres] == \
        ["AddEffect", "ChainAttackDamage", "FlyUnit", "RemoveEffect"]
    add, chain, fly, rem = membres
    assert isinstance(add, AddEffect) and add.effect_type == int(EffectType.Untargetable)
    # Le natif passe un `Nullable<AddEffectBehaviourOptions>` VIDE : ni duree ni niveau.
    assert add.duration_rounds is None and add.duration_turns is None
    assert isinstance(rem, RemoveEffect) and rem.effect_type == int(EffectType.Untargetable)
    assert isinstance(chain, ChainAttackDamage)
    # `chainOptions` : le ctor natif n'ecrit QUE `+0x12 = 1`.
    assert chain.deferred_hit is True
    assert chain.allow_repeat_targets is False and chain.allow_immediate_repeat is False
    # `dmgAmount` = `Direct(GetVariableForLevel(dmg))` -> mode `amount` de la feuille, PAS le mode
    # BORNES : la config 1108 n'a NI `minDmg` NI `maxDmg`, les lire rendrait 0 degat en silence.
    assert chain.damage.amount is not None, "le 4e argument de la factory doit etre TRANSMIS"
    assert int(chain.damage.amount.evaluate(None)) == 1280
    assert chain.damage.amount_spread_pct == 0, "`damageOptions` = 32 octets ZERO"
    assert isinstance(fly, FlyUnit)


def test_940_la_config_1108_n_a_ni_minDmg_ni_maxDmg():
    """La RAISON du mode `amount`, verifiee sur le gameconfig et non supposee : la config porte
    `dmg` et `maxAdjacentTargets`, pas le couple de bornes que lit le mode BORNES."""
    import gameconfig as GC
    v = (GC.ability("KissOfDeath") or {}).get("variables") or {}
    assert "dmg" in v and "maxAdjacentTargets" in v
    assert "minDmg" not in v and "maxDmg" not in v
    c = (GC.ability("KissOfDeath") or {}).get("constants") or {}
    assert c.get("damageProfile") == "DirectDamage" and c.get("nrOfHits") == "1"
