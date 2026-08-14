"""#996-r1-r3 -- GARDE du port de `1015 PrecisionShot` / `1012 PrecisionShot_Aim` et de l'etage
`UseActiveAbility` NON-NORMAL qu'ils ont exige.

Le probe (`probe_996r1r3_precision_shot_port.py`) MESURE contre le natif ; ce fichier GARDE, hors
ligne, ce que la mesure a etabli. Six etages, chacun rougissant sur une MUTATION differente :

  1. REGISTRE    -- 1015 ET 1012 au registre COMBAT, avec leur masque (0x8014) ET leur litteral
                    d'`AbilityAttackType` (2 = Others), et RETIREES de `TARGETING_OPTIONS_UNPORTED`
                    (contrat de disjonction, que `probe_181` -- garde d'EXISTENCE -- ne voit pas).
  2. REGLES DYNAMIQUES DE CASTER -- les DEUX sens, et le fait qu'ils soient INVERSES l'un de
                    l'autre. C'est le trou PERMISSIF que la tranche ferme : avant, le port rendait
                    `0` la ou le natif rend `0x2` (mesure live : `actionConsumed = False`).
  3. ARBRES      -- 1015 = UN noeud `UseActiveAbility(Caster, Caster, ability_type = 1012)` ;
                    1012 = `AddEffect(1015, 3 TOURS) & SetActiveAbilityUsed(1015)`.
  4. DISPATCH    -- l'aiguillage de `UseActiveAbility` : `None` et un type REGULAR -> chemin
                    ATTAQUE NORMALE (non-regression des 17 call-sites historiques) ; un type
                    NON-NORMAL -> `AbilityHandler.active_ability_operation` (slot 2), et le
                    diagnostic du sous-cast REMONTE (`sub_cast`).
  5. OPERATION   -- `SetActiveAbilityUsedOperation` : gate `HasUnusedAbility`, consommation de la
                    SEULE entree nommee, et TRI-ETAT sur le composant absent (`gate is None`).
  6. EFFET       -- `PrecisionShot_Aim` est au registre d'effets et spawne son sous-effet
                    `PrecisionShot_BlockMovement` en `SAME_TURNS` (mesure live : les DEUX effets,
                    meme duree).

100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.behaviours import Seq
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import SAME_TURNS
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.precision_shot import PrecisionShot_AimEffect
from engine.entities.effects_state import EffectsState
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.ability_state import SetActiveAbilityUsed
from engine.runner.abilities.behaviours.combat import UseActiveAbility
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.necrons import (PRECISION_SHOT_AIM_TURNS, PRECISION_SHOT_ID,
                                             PrecisionShot_AimAbility, PrecisionShotAbility,
                                             precision_shot_aim_tree, precision_shot_tree)
from engine.runner.abilities.targeting import (RANGE_SELF, RANGED_BOOL_FALSE,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import ActiveAbilitiesComponent, ActiveAbility
from engine.runner.operations.ability_reset import (SetActiveAbilityUsedOperation,
                                                    has_unused_ability)
from engine.runner.snapshot import load_state

#: #486-r15 -- ce que ce fichier LIT, donc ce qui peut changer son verdict. Volontairement LARGE sur
#: les foyers PARTAGES que la tranche touche : trop large est sain, trop etroit est un faux vert.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/engine/entities/",
        "scripts/python/engine/runner/",
        # ⚠ NOMME EXPLICITEMENT bien qu'il soit SOUS `engine/runner/` : `probe_486r15 --proposer`
        # le rend comme le SEUL chemin que la cascade d'imports ne couvre pas -- il est charge par
        # le HARNAIS (paquet), pas par une arete d'import de ce fichier. Une declaration au seul
        # repertoire le laissait donc dehors, et le probe rougissait « DECLARE TROP ETROIT ».
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "cliquet OFFLINE du port 1015/1012 -- registre + masque + AbilityAttackType, les deux "
              "regles dynamiques de caster, la structure des deux arbres, l'aiguillage de "
              "`UseActiveAbility` (normal vs dispatch), l'Operation `SetActiveAbilityUsed` et le "
              "sous-effet 1016. Il lit des REGISTRES en memoire (`ABILITY_CLASSES`, "
              "`ABILITY_ATTACK_TYPE`, `TARGETING_OPTIONS_UNPORTED`, `EFFECT_CLASSES`) et la SOURCE "
              "de `UseActiveAbility.execute` / `SetActiveAbilityUsedOperation.execute`, donc son "
              "declencheur est la fermeture d'import d'`engine.runner.*` et d'`engine.entities.*` "
              "-- prise au REPERTOIRE, un import indirect pouvant atteindre n'importe quel module. "
              "`build: False` : aucune valeur du dump n'y entre (les ordinaux viennent des mirrors "
              "d'enum, la duree `3` est le litteral du decompile).",
}

SHOT = int(ActiveAbilityType.PrecisionShot)              # 0x3f7 = 1015
AIM = int(ActiveAbilityType.PrecisionShot_Aim)           # 0x3f4 = 1012
ATTACK = int(ActiveAbilityType.PrecisionShot_Attack)     # 0x3f5 = 1013
AIM_EFFECT = int(EffectType.PrecisionShot_Aim)           # 0x3f7 = 1015 (EffectType, homonyme)
BLOCK_EFFECT = int(EffectType.PrecisionShot_BlockMovement)   # 0x3f8 = 1016
NORMAL = int(ActiveAbilityType.Loki_NormalAttack)        # 0x45 = 69

COLS = ROWS = 7
CASTER, FOE, PLAYER_MOI, PLAYER_ADV = 10, 20, 3, 4


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(caster_effects=None, abilities=True):
    """Etat runner minimal : le caster + un ennemi. `caster_effects` = lignes d'effet du canal
    `decisionView` ; `abilities=False` retire l'`ActiveAbilitiesComponent` (canal `allAbilities`
    non demande) -- c'est le regime TRI-ETAT de l'etage 5."""
    units = [{"id": CASTER, "visualId": "necroNpc3Deathmark", "alive": True, "team": 1,
              "owner": PLAYER_MOI, "pos": {"col": 2, "row": 3},
              "effects": list(caster_effects or []),
              "abilities": ([{"id": SHOT, "name": "PrecisionShot", "kind": "active",
                              "usable": True},
                             {"id": AIM, "name": "PrecisionShot_Aim", "kind": "active",
                              "usable": True}] if abilities else [])},
             {"id": FOE, "visualId": "necroWarden", "alive": True, "team": 2,
              "owner": PLAYER_ADV, "pos": {"col": 5, "row": 3}, "effects": [], "abilities": []}]
    decision = {"currentPlayer": PLAYER_MOI, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 500000, "hpMax": 500000} for u in units]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 500000, "movement": 3, "armour": 0,
                                     "turnsStarted": 0},
                           "healthMax": 500000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    st = load_state(decision, observe, snapshot,
                    board=Board(_tiles(), adjacency="evenq"), ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    if abilities:
        e = st.get_entity(CASTER)
        if e.get_component(ActiveAbilitiesComponent) is None:
            e.add_component(ActiveAbilitiesComponent(
                [ActiveAbility(SHOT), ActiveAbility(AIM)]))
    else:
        st.get_entity(CASTER).remove_component(ActiveAbilitiesComponent)
    return st


def _pose_aim(st):
    """Materialise l'effet de visee sur le caster, comme `AddEffectOperation` le ferait."""
    from engine.entities.effects.factory import EffectFactory
    st.effects.add_effect(CASTER, EffectFactory.create(
        {"name": "PrecisionShot_Aim", "effectType": AIM_EFFECT, "remaining": 3,
         "source": CASTER, "target": CASTER}))


# ------------------------------------------------------------------------------ 1. REGISTRE ----

def test_1015_et_1012_sont_au_registre_avec_masque_attack_type_et_disjonction():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` **et** son
    `ABILITY_ATTACK_TYPE` DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED`."""
    for aid, klass in ((SHOT, PrecisionShotAbility), (AIM, PrecisionShot_AimAbility)):
        assert ABILITY_CLASSES.get(aid) is klass, "%d absente d'ABILITY_CLASSES" % aid
        opts = klass.TARGETING_OPTIONS
        assert opts is not None, "%d entre au registre SANS masque -> gate DESARME" % aid
        # `0x8014` = le masque EFFECTIF, lu au `.cctor` : preset `+0x2a8` = 0x8004, `| 0x10` du ctor.
        assert int(opts.rules) == 0x8014, "%d : masque %s != 0x8014" % (aid, hex(int(opts.rules)))
        assert int(opts.rules) == int(TR.CasterHasNotMoved | TR.CasterMatchesDynamicRule
                                      | TR.CasterIsPossibleTarget)
        assert opts.self_cast is True and opts.range == RANGE_SELF
        assert opts.force_melee_target == RANGED_BOOL_FALSE
        assert ABILITY_ATTACK_TYPE.get(aid) == AbilityAttackType.Others, (
            "%d : `AActiveAbility..ctor(this, &opts, 2)` -> Others" % aid)
        assert aid not in TARGETING_OPTIONS_UNPORTED, (
            "%d est portee ET encore dans TARGETING_OPTIONS_UNPORTED : c'est la DOUBLE declaration "
            "que `probe_181` (garde d'EXISTENCE) ne voit pas" % aid)
    assert not (set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED)), (
        "la disjonction GLOBALE est rompue")


def test_1013_porte_deja_son_litteral_et_il_DIFFERE_des_deux_autres():
    """Le litteral ne se deduit ni du nom ni du triptyque : la SEULE des trois qui attaque porte
    `DirectTargetAttack`, les deux autres `Others`."""
    assert ABILITY_ATTACK_TYPE.get(ATTACK) == AbilityAttackType.DirectTargetAttack
    assert ABILITY_ATTACK_TYPE.get(SHOT) != ABILITY_ATTACK_TYPE.get(ATTACK)


# ------------------------------------------------- 2. REGLES DYNAMIQUES DE CASTER (les DEUX) ---

def test_la_regle_de_1015_refuse_HORS_visee_et_accepte_EN_visee():
    """`PrecisionShotAbility$$GetDynamicInvalidCasterReason` = `HasEffect(caster, 1015) ? 0 : 2`."""
    st = _state()
    assert PrecisionShotAbility().get_dynamic_invalid_caster_reason(st, CASTER) == int(
        TR.TargetMatchesDynamicRule), "sans visee, le natif rend 0x2 -- le port doit REFUSER"
    _pose_aim(st)
    assert PrecisionShotAbility().get_dynamic_invalid_caster_reason(st, CASTER) == 0


def test_la_regle_de_1012_est_L_INVERSE_EXACTE_de_celle_de_1015():
    """`PrecisionShot_AimAbility$$...` = `HasEffect(caster, 1015) ? 2 : 0`. Le couple est ce qui
    articule le triptyque : viser n'est legal que si l'on ne vise pas deja."""
    st = _state()
    assert PrecisionShot_AimAbility().get_dynamic_invalid_caster_reason(st, CASTER) == 0
    _pose_aim(st)
    assert PrecisionShot_AimAbility().get_dynamic_invalid_caster_reason(st, CASTER) == int(
        TR.TargetMatchesDynamicRule)
    # ... et le couple est bien ANTI-SYMETRIQUE dans les DEUX regimes, pas seulement dans l'un.
    for st2, attendu in ((_state(), (int(TR.TargetMatchesDynamicRule), 0)),):
        assert (PrecisionShotAbility().get_dynamic_invalid_caster_reason(st2, CASTER),
                PrecisionShot_AimAbility().get_dynamic_invalid_caster_reason(st2, CASTER)) == attendu


def test_le_gate_passe_bien_par_la_regle_puisque_le_bit_est_pose():
    """Sans le bit `CasterMatchesDynamicRule` dans le masque, la regle ne serait JAMAIS consultee
    (le natif ne l'invoque que sous ce bit) -- la surcharge serait du code mort."""
    for klass in (PrecisionShotAbility, PrecisionShot_AimAbility):
        assert int(klass.TARGETING_OPTIONS.rules) & int(TR.CasterMatchesDynamicRule)
        from engine.runner.abilities.base import ActiveAbility as Base
        assert (klass.get_dynamic_invalid_caster_reason
                is not Base.get_dynamic_invalid_caster_reason), (
            "%s pose le bit 0x4 sans surcharger la regle -> degradation PERMISSIVE" % klass.__name__)


# ---------------------------------------------------------------------------- 3. LES ARBRES ----

def test_l_arbre_de_1015_est_UN_dispatch_de_1012_et_rien_d_autre():
    """`Execute(UseActiveAbility(Caster@0x48, Caster@0x48, 0x3f4))` -- pas d'attaque, pas d'effet."""
    tree = precision_shot_tree()
    assert isinstance(tree, UseActiveAbility), "1015 n'a QU'UN noeud, et c'est celui-la"
    assert tree.ability_type == AIM, "le litteral natif est 0x3f4 = 1012 PrecisionShot_Aim"
    assert tree.ability_type != NORMAL, (
        "un type REGULAR ferait INVENTER une attaque normale -- pire qu'un no-op")


def test_l_arbre_de_1012_pose_l_effet_3_TOURS_puis_consomme_la_charge_de_1015():
    """`AddEffect(1015, stateRef, Owner@0x30, Nullable(3)) & SetActiveAbilityUsed(Owner@0x30, 1015)`.

    ⚠ Les DEUX `1015` sont dans des enums DIFFERENTS : l'effet et l'ability."""
    tree = precision_shot_aim_tree()
    assert isinstance(tree, Seq), "`op_and` = la composition native `op_BitwiseAnd`"
    add, used = tree.left, tree.right   # `Seq(left, right)` -- l'ORDRE des deux termes natifs
    assert isinstance(add, AddEffect) and isinstance(used, SetActiveAbilityUsed)
    assert add.effect_type == AIM_EFFECT                      # EffectType.PrecisionShot_Aim
    assert add.duration_turns == PRECISION_SHOT_AIM_TURNS == 3, "Nullable(3) TOURS, pas des rounds"
    assert add.duration_rounds is None, "aucun `TurnsFromRounds` au call-site natif"
    assert add.source_from_target is True, (
        "la surcharge 4-args d'`AddEffect` passe litteralement `source = 0` -> source = la cible")
    assert used.active_ability_type == SHOT                   # ActiveAbilityType.PrecisionShot
    assert used.active_ability_type != AIM, (
        "le 2e argument natif est 0x3f7 = 1015, PAS l'ability qui s'execute")


# ------------------------------------------------------------------- 4. AIGUILLAGE DU DISPATCH --

def test_le_type_normal_reste_sur_le_chemin_d_attaque_normale():
    """NON-REGRESSION des 17 call-sites historiques : `None` (selecteur `UnitNormalAttackType`) et
    un litteral REGULAR (`0x45`, ce que passent `UnbreakableDuty` et `RedemptionOfTheRisen`)
    prennent tous deux la specialisation ATTAQUE NORMALE."""
    from engine.runner.abilities.attack_type import is_regular_attack
    assert UseActiveAbility.__init__.__defaults__[-1] is None, "`ability_type` defaut = None"
    assert is_regular_attack(NORMAL) is True
    assert is_regular_attack(AIM) is False, "1012 n'est PAS une attaque reguliere -> dispatch"


def test_le_dispatch_non_normal_passe_par_l_operation_et_REMONTE_son_diagnostic(monkeypatch):
    """Le natif appelle le slot **2** d'`IOperationProcessor` (`OperationProcessor$$ActiveAbility`
    -> `ActiveAbilityOperation$$Execute`), PAS `AttackDamage`. Le port doit donc entrer par
    `AbilityHandler.active_ability_operation` -- et JAMAIS par `AttackDamageOperation.execute`.

    La substitution est posee sur le MODULE (`handler.AbilityHandler`), forme qui MORD quelle que
    soit la forme finale de l'import differe (cf. la regle des trois formes)."""
    from engine.runner.abilities.behaviours import combat as C
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities import handler as HD

    vus = []

    class _FauxHandler:
        def __init__(self, state):
            self.state = state

        def active_ability_operation(self, caster_id, target_id, ability_type):
            vus.append((int(caster_id), target_id, int(ability_type)))
            return {"ability_type": int(ability_type), "ported": True, "invalid_target": 2}

    def _interdit(*a, **k):                    # pragma: no cover - il ne doit JAMAIS etre appele
        raise AssertionError("le dispatch NON-NORMAL a appele AttackDamageOperation.execute")

    monkeypatch.setattr(HD, "AbilityHandler", _FauxHandler)
    monkeypatch.setattr(C.AttackDamageOperation, "execute", staticmethod(_interdit))
    st = _state()
    ectx = ExecutionContext(state=st, rng=st.rng)
    precision_shot_tree().execute(entities_from_state(st, CASTER, CASTER), ectx)
    assert vus == [(CASTER, CASTER, AIM)], "un seul sous-cast, sur le CASTER, avec 1012"
    emis = [p for n, p in ectx.emitted if n == "UseActiveAbility"]
    assert len(emis) == 1 and emis[0]["ability_type"] == AIM
    assert emis[0]["attack"] is None, "un dispatch non-normal ne produit AUCUNE attaque"
    assert (emis[0].get("sub_cast") or {}).get("invalid_target") == 2, (
        "le diagnostic du sous-cast doit REMONTER -- sinon un refus est un no-op muet")


# --------------------------------------------------------------------------- 5. L'OPERATION ----

def test_set_active_ability_used_consomme_la_SEULE_entree_nommee():
    """`SetActiveAbilityUsedOperation$$Execute` : `CanStillBeUsed = false` sur l'entree dont
    `AbilityName@0x44 == activeAbilityType`, et sur elle seule."""
    st = _state()
    comp = st.get_entity(CASTER).get_component(ActiveAbilitiesComponent)
    assert comp is not None and comp.get(SHOT).can_still_be_used is True
    r = SetActiveAbilityUsedOperation.execute(st, CASTER, SHOT)
    assert r["gate"] is True and r["used"] == [SHOT]
    assert comp.get(SHOT).can_still_be_used is False
    assert comp.get(AIM).can_still_be_used is True, "1012 ne doit PAS etre touchee"


def test_le_gate_HasUnusedAbility_rend_le_second_appel_INERTE():
    """Le gate d'entree est `UnitExtensions$$HasUnusedAbility` = `CanStillBeUsed@0x28` SEUL --
    re-consommer une charge deja consommee est un no-op NATIF, et le port le DIT."""
    st = _state()
    SetActiveAbilityUsedOperation.execute(st, CASTER, SHOT)
    r2 = SetActiveAbilityUsedOperation.execute(st, CASTER, SHOT)
    assert r2["gate"] is False and r2["used"] == [], "gate `False` = mesure faite, refus natif"


def test_le_composant_absent_rend_un_verdict_INCONNU_jamais_un_faux():
    """TRI-ETAT : `None` = canal `allAbilities` non demande. Le rabattre sur `False` ferait lire
    « charge deja consommee » sur une absence de MESURE."""
    st = _state(abilities=False)
    e = st.get_entity(CASTER)
    e.remove_component(ActiveAbilitiesComponent)           # `load_state` a pu le seeder
    # ⚠ ASSERTIONNER SON PROPRE NON-VIDE : sous un `if`, ce test passerait pour VERT sans avoir
    # rien evalue si le composant etait toujours la. Le regime est donc EXIGE, pas espere.
    assert e.get_component(ActiveAbilitiesComponent) is None, "le regime TRI-ETAT n'est pas monte"
    assert has_unused_ability(st, CASTER, SHOT) is None
    r = SetActiveAbilityUsedOperation.execute(st, CASTER, SHOT)
    assert r["gate"] is None and r["used"] == []


def test_une_ability_ABSENTE_de_la_collection_n_est_pas_consommee():
    """`GetOrNull` rend null -> `HasUnusedAbility` = false, l'Operation ne touche a rien."""
    st = _state()
    assert has_unused_ability(st, CASTER, ATTACK) is False
    r = SetActiveAbilityUsedOperation.execute(st, CASTER, ATTACK)
    assert r["gate"] is False and r["used"] == []


# ------------------------------------------------------------------------------- 6. L'EFFET ----

def test_l_effet_de_visee_est_au_registre_et_spawne_son_sous_effet_en_SAME_TURNS():
    """`PrecisionShot_AimEffect$$BlockMovement` -> `AddSubEffectWithSameTurns(..., 0x3f8)`.
    MESURE live : le natif publie `PrecisionShot_Aim` (3) ET `PrecisionShot_BlockMovement` (3)."""
    assert EFFECT_CLASSES.get("PrecisionShot_Aim") is PrecisionShot_AimEffect
    subs = PrecisionShot_AimEffect("PrecisionShot_Aim",
                                   effect_type=AIM_EFFECT).sub_effects_on_apply()
    assert len(subs) == 1, "UN seul sous-effet"
    assert subs[0].effect_type == BLOCK_EFFECT == 1016
    assert subs[0].name == EffectType.PrecisionShot_BlockMovement.name
    assert subs[0].turns == SAME_TURNS, "`AddSubEffectWithSameTurns` -- MEME duree que le parent"
    assert subs[0].on_bonded_entity is False, "l'enfant vit sur le PORTEUR, pas sur un bonde"


def test_la_pose_materialise_LES_DEUX_effets_avec_la_meme_duree():
    """Bout en bout, hors ligne : l'arbre de 1012 pose 1015 ET 1016, tous deux a 3 tours."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = _state()
    ectx = ExecutionContext(state=st, rng=st.rng)
    precision_shot_aim_tree().execute(entities_from_state(st, CASTER, CASTER), ectx)
    poses = {(e.effect_type, e.remaining_turns) for e in st.effects.active_effects(CASTER)}
    assert (AIM_EFFECT, 3) in poses, "l'effet de visee, 3 TOURS"
    assert (BLOCK_EFFECT, 3) in poses, "le sous-effet, MEME duree (SAME_TURNS)"
    comp = st.get_entity(CASTER).get_component(ActiveAbilitiesComponent)
    assert comp.get(SHOT).can_still_be_used is False, "la charge de 1015 est consommee par 1012"
