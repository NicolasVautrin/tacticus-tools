"""#902-r1 volet `1547` -- CLIQUET de la refutation. **L'effet EST porte, sur l'AUTRE rail.**

`#902-r1` (et sa re-mesure #984 §3.3) annoncait : « RESTE `1547 ReanimationBeam_Revive`, et lui
seul. Chaine d'heritage a mirrorer sur TROIS etages (`ReviveEffect` -> `PlayerTurnEffect` ->
`BaseEffect`) [...] NON PORTE ici ». **C'est faux depuis #79, et ce fichier le garde executable.**

La prémisse vient de `case-902` sec.8, qui ecrit : « la classe d'effet n'est pas portee
(`EFFECT_CLASSES` n'a ni 1545, ni 1546, ni 1547) -> `AddEffectOperation` pose un `BaseEffect` nu.
L'effet **existe** des deux cotes [...] mais **n'agit** d'aucun ». Le constat sur `EFFECT_CLASSES`
est exact ; la conclusion « n'agit d'aucun » ne l'est pas, parce qu'elle regarde **UN SEUL des deux
rails**.

  * `EFFECT_CLASSES` / `EffectFactory` = le rail des CONTRIBUTIONS (stat-mods, degat, reparation).
    `ReanimationBeam_ReviveEffect` n'a ni `ApplyInternal` ni `RevertInternal` -- il ne contribue a
    RIEN. Un `BaseEffect` nu y est donc la degradation EXACTE, pas un manque.
  * `EFFECT_TRIGGERS` (`triggers/dispatch/registry.py`) = le rail du COMPORTEMENT. C'est la que vit
    `1547`, via `ReanimationBeamReviveTrigger`, mirror de la base
    `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger` /
    `$$CreateTargetTriggerBehaviour` plus le seul virtuel propre a la feuille,
    `IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter`.

Re-mesure du BUILD COURANT (`data/symbols/rnca9r7q6c`) : la classe ne porte que **DEUX** methodes
nommees -- `...ReanimationBeam_ReviveEffect$$.ctor` et `...$$CreateTargetFilter` (`methods.tsv` et
`ghidra/functions.tsv` concordent), et sa base est bien `IdunBattle.Entities.Effects.ReviveEffect`
(`classes.tsv`). Les quatre autres virtuels sont ICF-dedupliques et **deja portes en constantes de
classe**, lus dans le bloc `methodPointers` du PE : `get_ReviveOnOverkill = 0`, `get_HealType = 1`
(Mechanical/Repair -- le << piege mesure >> que le residu annonce), `GetReviveChance = 100`,
`GetReviveHP` partage avec Narthecium.

Les deux autres arguments du `.ctor` que #984 nomme LOAD-BEARING sont eux aussi sans objet ici :
`activationFrequency = 0 Automatic` **vide** `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`,
donc il n'y a aucun rail << par tour >> a porter, et `turnsEnabled = 2 Both` ne gouverne que ce
rail-la. Ce qui reste du `.ctor` est `removeEffect = true`, qui EST porte (`remove_effect = True`).

⚠ **L'ENJEU N'EST PAS DOCUMENTAIRE.** Repondre au residu en creant une classe d'effet `1547` dans
`EFFECT_CLASSES` ecrirait une SECONDE implementation du revive a cote de celle du rail trigger --
un fork, avec deux regles pour un `ReviveEffect` natif unique. Le cliquet porte donc sur le
COMPORTEMENT (le revive mord, et ses quatre gates discriminent), pas sur l'emplacement du code.

Ce fichier est OFFLINE INTEGRAL : `State` synthetique, aucun runner, aucun RPC. Le fichier live
existant (`tests/engine/runner/test_revive_retrofit_offline_live.py`) garde les MEMES verdicts sur
un etat CAPTURE ; il ne pouvait pas jouer le role de cliquet ici, puisqu'il monte un runner.
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.revive import kill_unit_revive_gate, reset_revive_gates
from engine.runner.operations.triggers.dispatch.core import collect_effect_triggers
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
from engine.runner.operations.triggers.loki.reanimation_beam import ReanimationBeamReviveTrigger
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State


#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE : tout ce que ce fichier lit -- le registre `EFFECT_TRIGGERS`, le trigger 1547, la base
    # `ReviveEffect`, le pipeline de mort -- est dans sa propre fermeture d'imports, donc dans la
    # cascade DERIVEE par le foyer. Recopier des chemins ici serait la faute #531 (une seconde
    # liste qui se perime en silence).
    "chemins": (),
    # VRAI : la magnitude du revive vient du gameconfig du build
    # (`ability_var("ReanimationBeam", "hp", ...)`). Un re-dump qui renommerait la variable ou la
    # cle d'ability ferait tomber le montant a 0 -- exactement le rouge attendu.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde UN comportement : que l'effet 1547 pose sur le Reanimator RESSUSCITE un "
        "allie Mechanical porteur de 1545, et que ses quatre gates (amitie, trait, effet 1545, "
        "healType) discriminent. Il ne balaie ni le parc de tests ni l'arbre : son verdict ne "
        "depend que de sa fermeture d'imports et du gameconfig du build. Il existe pour empecher "
        "que #902-r1 soit rouvert a tort et 'repare' par une classe d'effet 1547 dans "
        "EFFECT_CLASSES, qui forkerait le revive deja porte sur le rail EFFECT_TRIGGERS."
    ),
}

REVIVE = int(EffectType.ReanimationBeam_Revive)              # 0x60b = 1547
NANOSCARAB = int(EffectType.NanoscarabRepairProtocols)       # 0x609 = 1545
#: niveau / multiplicateur de l'ability SOURCE, transportes par l'effet (comme la voie POSE).
LEVEL, MULT = 50, 180
HP_MAX = 20000


class _Ctx:
    """Le minimum de `UnitContext` que `entities_from_state` / `_unit_traits` lisent."""

    def __init__(self, traits=()):
        self.traits = list(traits)
        self.active_ability_level = LEVEL
        self.passive_ability_level = LEVEL
        self.ability_variables_multiplier = MULT


def _unite(st: State, uid: int, *, team: int, traits=(), pos=(0, 0), hp=HP_MAX) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent("u%d" % uid, True))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(hp, HP_MAX))
    e.add_component(StatsComponent(ctx=_Ctx(traits)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


def _pose(st: State, uid: int, effect_type: int, name: str) -> BaseEffect:
    eff = BaseEffect(name=name, effect_type=int(effect_type), active_ability_level=LEVEL,
                     ability_level=LEVEL, ability_variables_multiplier=MULT,
                     source=int(uid), target=int(uid))
    st.effects.by_unit.setdefault(int(uid), []).append(eff)
    return eff


@pytest.fixture
def montage():
    """FIXTURE NOMMEE, reutilisable : le Reanimator (`beam`) porte 1547, l'allie (`cible`) est
    Mechanical et porte 1545. C'est le montage MINIMAL qui remplit
    `...ReanimationBeam_ReviveEffect$$CreateTargetFilter` -- chaque face negative se fabrique en
    retirant UNE de ses trois pieces, jamais en en ajoutant une."""
    def _monter(mechanical: bool = True, nanoscarab: bool = True, meme_equipe: bool = True):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(777)
        beam = _unite(st, 10, team=1, pos=(0, 0))
        cible = _unite(st, 11, team=(1 if meme_equipe else 2),
                       traits=(UnitTrait.Mechanical.name,) if mechanical else (), pos=(1, 0))
        _pose(st, beam, REVIVE, EffectType.ReanimationBeam_Revive.name)
        if nanoscarab:
            _pose(st, cible, NANOSCARAB, EffectType.NanoscarabRepairProtocols.name)
        return st, beam, cible
    return _monter


def _tuer(st: State, uid: int, killer: int, overkill: bool = False):
    """`On(1 = PreUnitDeath)` PUIS la garde `IdunBattle.Operations.KillUnitOperation$$Execute`
    (`kill_unit_revive_gate`), qui draine la `ReviveData` posee par la feuille `Revive`."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)
    kill_unit_revive_gate(st, uid)
    return out


def _vivant(st: State, uid: int) -> bool:
    return bool(st.get_entity(uid).get_component(UnitComponent).alive)


# ------------------------------------------------------- 1. le CABLAGE : 1547 a bien un rail
def test_1547_est_INSCRIT_au_registre_des_triggers_d_effet():
    """La refutation en une ligne : le residu cherchait 1547 dans `EFFECT_CLASSES`, il vit dans
    `EFFECT_TRIGGERS`. Un `1547` absent des DEUX registres serait le vrai no-op annonce."""
    assert REVIVE in EFFECT_TRIGGERS, (
        "1547 n'est plus inscrit au rail COMPORTEMENT -- le revive du Reanimator redevient un "
        "no-op, et le volet 1547 de #902-r1 redevient VRAI")
    assert ReanimationBeamReviveTrigger in EFFECT_TRIGGERS[REVIVE]


def test_les_quatre_virtuels_ICF_dedupliques_sont_portes_en_CONSTANTES():
    """Aucun des quatre n'a de symbole propre (corps folde par ICF) : ils sont LUS dans le bloc
    `methodPointers` du PE et figes ici. `get_HealType = 1` est le << piege mesure >> du residu --
    la BASE rend `0`, et l'heriter inverserait le comportement (une cible Mechanical serait
    REJETEE par `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType`)."""
    assert ReanimationBeamReviveTrigger.heal_type == 1, "get_HealType = 1 (Mechanical/Repair)"
    assert ReanimationBeamReviveTrigger.revive_on_overkill is False, "get_ReviveOnOverkill = 0"
    assert ReanimationBeamReviveTrigger.default_chance == 100, "GetReviveChance = 100"
    assert ReanimationBeamReviveTrigger.remove_effect is True, "ctor removeEffect = TRUE"
    from engine.runner.operations.triggers.revive_effect import _ReviveEffectCore
    assert _ReviveEffectCore.heal_type == 0, (
        "temoin NON DEGENERE : la base doit rendre 0, sinon l'override 1 ne prouve rien")


# --------------------------------------------------- 2. le COMPORTEMENT : le revive MORD
def test_le_revive_MORD_sur_un_allie_mechanical_nanoscarabe(montage):
    """Le coeur de la refutation : l'effet 1547 AGIT. Si ce test rougit, le volet 1547 de
    #902-r1 redevient VRAI et le comportement doit etre (re)porte."""
    st, beam, cible = montage()
    attendu = min(int(ability_var("ReanimationBeam", "hp", LEVEL, multiplier_pct=MULT) or 0), HP_MAX)
    assert attendu > 0, "temoin degenere : le gameconfig ne rend aucun `hp` pour ReanimationBeam"
    pc = st.get_entity(cible).get_component(PositionComponent)
    pos0 = (pc.col, pc.row)
    _tuer(st, cible, beam)
    assert _vivant(st, cible), "l'effet 1547 n'agit PAS -- le rail EFFECT_TRIGGERS ne mord plus"
    assert int(st.get_entity(cible).get_component(HealthComponent).hp) == attendu, \
        "hp != Min(Direct(hp[lvl]), StatAmount(Target, Health, Initial))"
    assert (pc.col, pc.row) == pos0, "le revive doit etre EN PLACE"


# ------------------------------- 3. les gates DISCRIMINENT (sinon le test 2 ne garde rien)
def test_le_noeud_HasEffect_1545_du_filtre_discrimine(montage):
    """`HasEffect(target, 0x609 = 1545)` -- le noeud d'accroche est l'effet pose par l'AUTRE
    active du Reanimator."""
    st, beam, cible = montage(nanoscarab=False)
    _tuer(st, cible, beam)
    assert not _vivant(st, cible), "revive sans l'effet 1545"


def test_le_noeud_HasTrait_Mechanical_du_filtre_discrimine(montage):
    """`HasTrait(target, 5 = Mechanical)` -- l'INVERSE de Narthecium, qui EXCLUT les Mechanical.
    DOUBLE barriere : le filtre ET `IsAffectedByHealType(healType = 1)`."""
    st, beam, cible = montage(mechanical=False)
    _tuer(st, cible, beam)
    assert not _vivant(st, cible), "revive d'une cible non-Mechanical"


def test_le_noeud_AreFriends_du_filtre_discrimine(montage):
    """`AreFriends(self@0x148, target@0x178)` -- le Reanimator ne ressuscite pas un ENNEMI."""
    st, beam, cible = montage(meme_equipe=False)
    _tuer(st, cible, beam)
    assert not _vivant(st, cible), "revive d'une cible ENNEMIE (noeud AreFriends absent)"


def test_l_overkill_bloque_et_le_one_shot_est_DEFINITIF(montage):
    """`OnPreDeath(triggerOnOverkill = false)` et `removeEffect = TRUE` : deux lectures du `.ctor`
    et du bloc `methodPointers`, opposees sur le MEME montage."""
    st, beam, cible = montage()
    _tuer(st, cible, beam, overkill=True)
    assert not _vivant(st, cible), "revive malgre l'overkill"

    st2, beam2, cible2 = montage()
    _tuer(st2, cible2, beam2)
    assert _vivant(st2, cible2), "temoin : le 1er revive doit passer"
    assert all(e.consumed for e in st2.effects.by_unit[int(beam2)]
               if e.effect_type == REVIVE), "effet 1547 non RETIRE (removeEffect = TRUE)"
    reset_revive_gates(st2)
    _tuer(st2, cible2, beam2)
    assert not _vivant(st2, cible2), "2e revive apres reset -- one-shot DEFINITIF non respecte"


def test_le_gate_IsActive_de_l_instance_1547_discrimine(montage):
    """`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` n'appelle
    `ShouldTrigger` puis `Execute` que `if (EffectComponent.IsActive @+0x5c)`. Le COLLECTEUR, lui,
    doit continuer a instancier le trigger -- c'est ce qui prouve que le refus vient du `matches`
    du rail TARGETS et non d'un filtre pose au mauvais etage."""
    st, beam, cible = montage()
    insts = [e for e in st.effects.by_unit[int(beam)] if e.effect_type == REVIVE]
    assert insts, "montage KO : aucune instance 1547"
    for e in insts:
        e.active = False
    assert any(isinstance(t, ReanimationBeamReviveTrigger) and t.owner_id == beam
               for t in collect_effect_triggers(st)), \
        "le collecteur ne doit PAS filtrer sur `active`"
    _tuer(st, cible, beam)
    assert not _vivant(st, cible), "revive par une instance 1547 INERTE"
    assert not any(e.consumed for e in insts), \
        "effet 1547 consomme par un trigger que le natif n'evalue meme pas"
