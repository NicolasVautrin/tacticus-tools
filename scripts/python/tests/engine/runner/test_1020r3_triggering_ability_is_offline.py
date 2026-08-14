"""#1020-r3 -- le CLIQUET des deux `!TriggeringAbilityIs` de `SaviorProtocols`, et du CANAL
`AbilityEntities+0x98` qui les rend mordants.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident.

La faute d'origine etait PERMISSIVE : le port omettait les deux derniers conjoints de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$CreateTrigger`, donc il
acceptait des declenchements que le natif REFUSE. Rien ne levait, aucun test ne tombait -- la
signature exacte d'un `TARGETING_OPTIONS` absent.

Elle se ferme en DEUX pieces, et les deux sont necessaires : le NOEUD (l'arbre porte-t-il les
conjoints ?) et le CANAL (le vecteur alimente-t-il ce que les conjoints comparent ?). Porter le
noeud SANS le canal serait un vert vide : `AbilitiesAreEqualTrigger$$ShouldTrigger` rend FAUX sur
un `Nullable` vide, donc `!TriggeringAbilityIs(X)` serait TOUJOURS vrai et le gate resterait
grand ouvert. C'est l'etage 3 qui interdit ce faux vert.

Les cinq etages :

  1. NOEUD -- `TriggeringAbilityIs` mirror `AbilitiesAreEqualTrigger$$ShouldTrigger` : egalite sur
     le canal, et FAUX sur `Nullable` vide (lu verbatim, pas suppose).
  2. STRUCTURE -- l'arbre de `savior_trigger_tree()` porte EXACTEMENT les deux exclusions du
     decompile, avec les deux ids LUS AUX OCTETS. TEMOIN : un id fabrique doit en etre ABSENT.
  3. CANAL -- `pre_damage_taken_triggers` pose `source_ability` dans le champ `+0x98`. Sans lui les
     etages 1-2 seraient verts sur un gate MORT.
  4. BOUT EN BOUT -- `SaviorProtocolsAbility.matches` REFUSE les deux abilities exclues et ACCEPTE
     les autres. C'est le seul etage qui mesure le comportement observable.
  5. THREADING -- `_pre_damage_taken_per_hit` transporte `source_ability` jusqu'au dispatch.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

DECLENCHEUR = {
    "chemins": (
        # SOCLE d'un fichier de test OFFLINE : la cascade des `conftest.py` et les deux gardes de
        # passe. Aucun harnais live n'est traverse -- ce fichier ne monte AUCUN runner.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER, et pris LARGE : un declencheur trop etroit est un FAUX VERT (le
        # fichier ne se rejoue pas sous `--since` quand ce qu'il garde a bouge).
        # L'ABILITY et son arbre (etages 2 et 4).
        "scripts/python/engine/runner/operations/triggers/loki/savior_protocols.py",
        # Le NOEUD (etage 1) -- son `should_trigger` EST l'objet de l'etage.
        "scripts/python/engine/entities/triggers.py",
        # Le CANAL (etage 3) : le vecteur qui le pose, le champ d'evenement qui le porte, et le
        # chokepoint qui le thread (etage 5).
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/damage.py",
        # Le contexte DSL : `attack_ability_type` est le mapping du slot `<DSLSelectors+0x90>`.
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # Le sens des ordinaux cites (1327 / 1328 / 1120) et les composants du montage.
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/runner/components.py",
    ),
    # `build: True` -- les deux ids exclus sont des membres de `TriggeredAbilityType`, et l'etage 4
    # lit la FACTION T'au d'un `visual_id` du gameconfig. Un changement de build peut donc faire
    # basculer ce verdict SANS qu'un seul fichier du depot bouge.
    "build": True,
    # `toujours: False` -- les chemins ci-dessus bornent vraiment le verdict : les cinq etages
    # n'appellent que le noeud, l'arbre, le vecteur et le chokepoint, tous listes.
    "toujours": False,
    "raison": ("garde les deux `!TriggeringAbilityIs` qui terminent "
               "`SaviorProtocolsAbility$$CreateTrigger` (ids LUS AUX OCTETS : 0x530 = 1328 "
               "PinpointCounterOffensive, 0x52f = 1327 ATemptingTrap) ET le canal "
               "`AbilityEntities+0x98` qui les rend mordants -- le noeud sans le canal serait un "
               "gate MORT, donc un vert vide."),
}

from engine.dsl.base import DslContext                                          # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                      # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType         # noqa: E402
from engine.entities.triggers import Not, TriggeringAbilityIs                   # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,          # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.damage import AttackDamageOperation               # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent                 # noqa: E402
from engine.runner.operations.triggers.loki.savior_protocols import (           # noqa: E402
    EXCLUDED_PINPOINT, EXCLUDED_TEMPTING_TRAP, SaviorProtocolsAbility, savior_trigger_tree)
from engine.runner.state import State                                           # noqa: E402
from engine.entities.unit_context import UnitContext                            # noqa: E402

#: Les deux ids LUS AUX OCTETS de `SaviorProtocolsAbility$$CreateTrigger` (`mov edx, 0x530` puis
#: `mov edx, 0x52f`). Ecrits ICI en dur A DESSEIN : `probe_313` compare le MIRROR au BUILD, donc il
#: redevient vert apres un renumerotage alors que la valeur LUE au site, elle, a change. Ce couple
#: fige l'ordinal MESURE a la lecture -- c'est le cran que le registre ne tient pas.
_PINPOINT_MESURE = 1328
_TEMPTING_TRAP_MESURE = 1327

DRONE, VICTIME, SOURCE = 11, 22, 33


def _ctx(uid, *, visual):
    """Le VRAI `UnitContext` : `HasFaction` derive la faction du `visual_id` via le gameconfig, et
    un doublet trop pauvre ferait tomber le test sur son propre echafaudage."""
    c = UnitContext(entity_id=int(uid), visual_id=visual, traits=[],
                    active_ability_level=50, passive_ability_level=50,
                    ability_variables_multiplier=100)
    c.traits_measured = True
    return c


def _unite(st, uid, *, team, pos, visual):
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual, True))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(1000, 1000))
    e.add_component(StatsComponent(ctx=_ctx(uid, visual=visual)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def montage():
    """FIXTURE NOMMEE, reutilisable. Le regime NOMINAL du passif, celui que le probe live monte :

        SOURCE (ennemi) --attaque--> VICTIME (T'au, ne porte PAS 1120)
                                        ^ ADJACENTE
                                     DRONE (T'au, PORTE 1120, meme equipe que la VICTIME)

    Les quatre conjoints de `TargetIsValidTrigger` passent donc, et `IsAdjacent` aussi : le seul
    discriminant qui reste est le couple `!TriggeringAbilityIs`, ce qui est exactement ce que les
    etages 2 et 4 veulent isoler. Chaque face negative se fabrique en changeant UNE piece."""
    def _monter():
        st = State()
        _unite(st, DRONE, team=1, pos=(3, 4), visual="tauMarksman")
        _unite(st, VICTIME, team=1, pos=(3, 3), visual="tauMarksman")
        _unite(st, SOURCE, team=2, pos=(2, 3), visual="ultraTitus")
        return st
    return _monter


def _ev(source_ability):
    """L'evenement que `pre_damage_taken_triggers` construit : `actor` = la SOURCE du degat,
    `target` = la VICTIME, et le canal `+0x98` porte l'`AbilityOrEffect` de la `DamageSource`."""
    return TriggerEvent(int(EventTriggerType.PreDamageTaken), SOURCE, VICTIME,
                        ranged=False, profile="Physical",
                        triggering_effect=source_ability, triggering_ability=source_ability)


# ------------------------------------------------------------------ 1. LE NOEUD + son TEMOIN

def test_le_noeud_compare_le_canal_et_rend_vrai_sur_egalite():
    """ETAGE 1 -- `AbilityOrEffect.op_Equality(a.Value, b.Value)`."""
    ctx = DslContext(attack_ability_type=_TEMPTING_TRAP_MESURE)
    assert TriggeringAbilityIs(TriggeredAbilityType.ATemptingTrap).should_trigger(ctx) is True


def test_le_noeud_rend_FAUX_sur_un_canal_vide_et_c_est_la_reponse_NATIVE():
    """ETAGE 1 (le point load-bearing) -- `if (!a.HasValue) return false;`, lu verbatim dans
    `IdunBattle.Entities.Triggers.AbilitiesAreEqualTrigger$$ShouldTrigger`.

    Sous `op_LogicalNot`, ce FAUX rend le conjoint VRAI : un canal vide OUVRE le gate. C'est
    precisement pourquoi l'etage 3 doit exister -- sans le canal, les deux exclusions ne
    refuseraient jamais rien."""
    assert TriggeringAbilityIs(TriggeredAbilityType.ATemptingTrap).should_trigger(
        DslContext()) is False
    assert Not(TriggeringAbilityIs(TriggeredAbilityType.ATemptingTrap)).should_trigger(
        DslContext()) is True


def test_temoin_le_noeud_DISCRIMINE_il_ne_dit_pas_vrai_a_tout():
    """TEMOIN de l'etage 1. Un noeud qui rendrait vrai des que le canal est non vide passerait le
    premier test et serait FAUX ici."""
    ctx = DslContext(attack_ability_type=_PINPOINT_MESURE)
    assert TriggeringAbilityIs(TriggeredAbilityType.ATemptingTrap).should_trigger(ctx) is False


# ------------------------------------------------------------------ 2. LA STRUCTURE + son TEMOIN

def _exclusions_de_l_arbre():
    """Les ids que l'arbre porte sous un `Not(TriggeringAbilityIs(...))`, DERIVES de l'arbre lui
    meme -- pas une liste recopiee, sinon la garde ne mesurerait que sa propre copie.

    La descente enumere le `__dict__` de chaque noeud, elle ne nomme AUCUN attribut : une liste
    blanche (`a`, `b`, `trigger`, ...) ne peut pas voir le lien qu'elle a oublie, et c'est
    exactement ce qui a rendu la premiere version de cette garde ROUGE sur un arbre pourtant
    correct."""
    vus, pile, deja = set(), [savior_trigger_tree()], set()
    while pile:
        n = pile.pop()
        if id(n) in deja:
            continue
        deja.add(id(n))
        for fils in vars(n).values():
            enfants = fils if isinstance(fils, (list, tuple, set)) else [fils]
            for f in enfants:
                if isinstance(f, Not) or hasattr(f, "should_trigger"):
                    pile.append(f)
        if isinstance(n, Not):
            for fils in vars(n).values():
                if isinstance(fils, TriggeringAbilityIs):
                    vus.add(int(fils.ability_type))
    return vus


def test_l_arbre_porte_EXACTEMENT_les_deux_exclusions_du_decompile():
    """ETAGE 2 -- LA garde de la faute d'origine. `SaviorProtocolsAbility$$CreateTrigger` se
    termine par DEUX `op_LogicalNot(TriggeringAbilityIs(<cst>))`, et le port les omettait tous les
    deux.

    Les valeurs sont LUES AUX OCTETS (le decompile ne montre que le buffer de retour d'
    `IdunBattle.Core.AbilityOrEffect$$op_Implicit`) : `mov edx, 0x530` puis `mov edx, 0x52f`, et
    les deux `call` visent la surcharge dont le parametre se nomme `triggeredAbility`."""
    assert _exclusions_de_l_arbre() == {_PINPOINT_MESURE, _TEMPTING_TRAP_MESURE}, (
        "l'arbre doit porter les DEUX exclusions %s, obtenu %s -- un port qui en omet une seule "
        "reste PERMISSIF, et rien ne le signale"
        % (sorted((_PINPOINT_MESURE, _TEMPTING_TRAP_MESURE)), sorted(_exclusions_de_l_arbre())))


def test_les_deux_constantes_nommees_valent_les_ordinaux_MESURES():
    """ETAGE 2 (volet ordinal). `probe_313` compare le mirror au build : il redevient VERT apres un
    renumerotage. Ce test-ci fige ce qui a ete LU au site."""
    assert int(EXCLUDED_PINPOINT) == _PINPOINT_MESURE
    assert int(EXCLUDED_TEMPTING_TRAP) == _TEMPTING_TRAP_MESURE
    assert EXCLUDED_PINPOINT is TriggeredAbilityType.PinpointCounterOffensive
    assert EXCLUDED_TEMPTING_TRAP is TriggeredAbilityType.ATemptingTrap


def test_temoin_un_id_FABRIQUE_est_absent_de_l_arbre():
    """TEMOIN de l'etage 2 : sans lui, un extracteur qui rendrait « tous les ids du monde »
    passerait."""
    assert 1329 not in _exclusions_de_l_arbre(), (
        "TEMOIN AVEUGLE : l'extracteur rend un id que l'arbre ne porte pas")


# ------------------------------------------------------------------ 3. LE CANAL

def test_le_vecteur_pose_source_ability_dans_le_champ_0x98():
    """ETAGE 3 -- `ApplyDamageOperation$$Execute` construit son `AbilityEntities` en passant le
    MEME bloc `DamageAppliedResult+0x40` DEUX FOIS : 13e parametre `currentAbilityOrEffect`
    (`+0x60`) et 15e `triggerAbilityOrEffect` (`+0x98`). Cote port, `triggering_ability` porte le
    premier et `triggering_effect` le second.

    Sans cet etage, les etages 1-2 seraient verts sur un gate MORT."""
    vus = {}

    class _D:
        @staticmethod
        def pre_damage_taken_triggers(state, source_id, target_id, profile=None,
                                      is_first_damaging_hit=None, source_ability=None):
            vus["source_ability"] = source_ability
            return []

    thc = HealthComponent(hp=1000, hp_max=1000)
    AttackDamageOperation._pre_damage_taken_per_hit(
        None, SOURCE, VICTIME, thc, 300, 0, "Physical", None, _D(),
        is_first_damaging_hit=True, source_ability=_TEMPTING_TRAP_MESURE)
    assert vus.get("source_ability") == _TEMPTING_TRAP_MESURE, (
        "le chokepoint doit transporter `source_ability` jusqu'au vecteur (obtenu %r) -- sinon le "
        "canal `+0x98` reste vide et les deux exclusions ne refusent JAMAIS rien"
        % (vus.get("source_ability"),))


def test_l_evenement_construit_porte_le_canal_sur_les_deux_champs():
    """ETAGE 3 (volet evenement) -- les DEUX champs, parce que le ctor natif recoit deux copies du
    meme offset. Mesure sur le vecteur reel, pas sur un `TriggerEvent` fabrique a la main."""
    from engine.runner.operations.triggers.dispatch import attack as A
    vus = {}
    orig = A.evaluate_trigger_operation
    try:
        A.evaluate_trigger_operation = lambda st, ev: vus.setdefault("ev", ev) and []
        A.pre_damage_taken_triggers(None, SOURCE, VICTIME, profile="Physical",
                                    source_ability=_PINPOINT_MESURE)
    finally:
        A.evaluate_trigger_operation = orig
    ev = vus["ev"]
    assert ev.triggering_effect == _PINPOINT_MESURE, "le champ `+0x98` doit porter la DamageSource"
    assert ev.triggering_ability == _PINPOINT_MESURE, "le champ `+0x60` la porte AUSSI (13e param)"


# ------------------------------------------------------------------ 4. BOUT EN BOUT + TEMOIN

def test_le_regime_NOMINAL_declenche(montage):
    """ETAGE 4 (bras positif) -- sans lui, les trois bras negatifs ci-dessous seraient verts sur un
    gate qui refuse TOUT, et la garde ne prouverait rien. C'est le temoin non-nul exige : un accord
    en regime degenere ne vaut rien."""
    st = montage()
    assert SaviorProtocolsAbility(DRONE).matches(st, _ev(None)) is True, (
        "canal VIDE = le regime le plus courant (degat sans ability nommee) : le natif y ouvre le "
        "gate, puisque `!TriggeringAbilityIs` sur un `Nullable` vide vaut VRAI")


@pytest.mark.parametrize("exclu", [_PINPOINT_MESURE, _TEMPTING_TRAP_MESURE])
def test_les_deux_abilities_exclues_FERMENT_le_gate(montage, exclu):
    """ETAGE 4 -- LE comportement que la faute d'origine laissait passer. Avant #1020-r3 ces deux
    bras rendaient `True` : le port acceptait un transfert que le natif REFUSE."""
    st = montage()
    assert SaviorProtocolsAbility(DRONE).matches(st, _ev(exclu)) is False, (
        "l'ability %d est l'un des deux `!TriggeringAbilityIs` de `CreateTrigger` : le gate DOIT "
        "fermer, or il a laisse passer -- c'est la divergence PERMISSIVE de #1020-r3" % exclu)


def test_temoin_une_AUTRE_ability_laisse_le_gate_OUVERT(montage):
    """TEMOIN de l'etage 4 -- il separe « les deux exclusions ferment » de « le canal non vide
    ferme tout ». Un port qui aurait recable le gate sur « une ability est nommee » passerait les
    deux bras negatifs et serait FAUX ici."""
    st = montage()
    autre = int(TriggeredAbilityType.DaughterOfTheAbyss)          # 1329, voisin immediat des deux
    assert autre not in (_PINPOINT_MESURE, _TEMPTING_TRAP_MESURE)
    assert SaviorProtocolsAbility(DRONE).matches(st, _ev(autre)) is True, (
        "seules les DEUX abilities lues doivent fermer le gate, pas n'importe quelle source nommee")
