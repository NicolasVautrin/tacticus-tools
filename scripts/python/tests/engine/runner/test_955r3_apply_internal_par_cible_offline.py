"""GARDE #955-r3 (OFFLINE PURE) -- `<Effect>$$ApplyInternal` est joue PAR CIBLE, a chaque reveil du
driver d'aura, pas UNE FOIS au moment de la pose.

CE QUE CE FICHIER PROTEGE. `IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect$$ApplyInternal`
tient en deux instructions, LUES :

    AStatModifierEffect.ApplyInternal(this, owner, target, effect)
    BaseEffect.AddSubEffect(this, effect, target, 0x437 = IgnoreBattleFatigue, turns = null)

et le `target` est la CIBLE SELECTIONNEE -- le 3e argument que
`IdunBattle.Operations.RefreshEffectsOperation$$ApplyEffectsForTargets` alimente une cible a la
fois, via `BaseEffect$$Apply` (slot 0xe) puis le slot virtuel 0x548. Le natif pose donc l'immunite
sur CHACUNE, et la pose a NOUVEAU des qu'une cible ENTRE dans le selecteur.

Le port la posait depuis le behaviour du trigger, **une fois**, au moment de la materialisation de
1031. Consequence : un allie qui entrait dans le selecteur PLUS TARD recevait le stat-mod -- le
driver, lui, re-evalue -- mais **pas** l'immunite. Ecart muet : rien ne leve, et le symptome n'est
visible qu'au prochain `BattleFatigue` (l'unite fuit alors qu'elle devrait ignorer).

⚠ LE REGIME EST ATTEIGNABLE, ET LE RESIDU DISAIT LE CONTRAIRE. Il concluait « aucun montage porte ne
le produit -- le trait est statique dans le gameconfig ». C'est le mauvais axe : ce qui compte n'est
pas qu'une unite ACQUIERE `BattleFatigue`, c'est qu'une unite qui le PORTE DEJA entre dans le
selecteur APRES coup. Un SUMMON en est un (`genesSmnNeophyte`, `astraSmnGuardsman`, `orksOrkBoys`,
`tyranSmnRipperSwarm` portent le trait), et `operations/spawn.py` reveille DEJA
`refresh_aura_stat_modifiers` -- le stat-mod suivait donc deja, l'immunite non.

ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.summary_execution import (IGNORE_BATTLE_FATIGUE,
                                                            SummaryExecutionBaseEffect,
                                                            SummaryExecutionEffect)
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.components import UnitComponent
from engine.runner.operations.aura_stat_mods import refresh_aura_stat_modifiers
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # le driver (le 4e point d'interface) et l'effet qui le declare
        "scripts/python/engine/runner/operations/aura_stat_mods.py",
        "scripts/python/engine/entities/effects/loki/summary_execution.py",
        # le behaviour du trigger, dont le poseur bespoke a ete RETIRE au profit du driver
        "scripts/python/engine/runner/operations/triggers/loki/summary_execution.py",
        # le poseur que le driver appelle, et son gate << deja present >>
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/entities/effects_state.py",
        # les mirrors d'enum dont ce fichier FIGE les ordinaux
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # la cascade que `load_state` tire
        "scripts/python/engine/runner/snapshot.py",
    ),
    # Il lit le gameconfig d'`AppData` (la magnitude de l'aura), HORS de l'arbre.
    "build": True,
    "toujours": False,
    "raison": "Il grave que l'`ApplyInternal` d'un effet-AURA est joue PAR CIBLE et RE-joue a "
              "chaque reveil du driver. Le collapse inverse (une pose unique depuis le behaviour) "
              "ne leve rien : la cible entrante recoit le stat-mod et pas l'immunite, et le "
              "symptome n'apparait qu'au prochain `BattleFatigue`.",
}

COLS, ROWS = 7, 7
YARRICK, FATIGUE_TOT, FATIGUE_TARD, SANS_TRAIT = 10, 20, 30, 40
NIVEAU, MULT = 50, 100


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


@pytest.fixture
def state():
    """Yarrick + deux allies `BattleFatigue` + un allie SANS le trait. `FATIGUE_TARD` commence MORT :
    il entrera dans le selecteur (`AllAliveUnits`) au moment ou le test le rendra vivant -- c'est le
    mirror offline d'un summon qui apparait apres coup."""
    board = Board(_tiles(), adjacency="evenq")
    pos = {YARRICK: (1, 1), FATIGUE_TOT: (2, 2), FATIGUE_TARD: (3, 3), SANS_TRAIT: (4, 4)}
    fatigues = (FATIGUE_TOT, FATIGUE_TARD)
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "astraYarrick" if uid == YARRICK else "astraSmnGuardsman",
         "alive": uid != FATIGUE_TARD, "team": 1, "owner": 1,
         "pos": {"col": pos[uid][0], "row": pos[uid][1]}, "effects": []}
        for uid in (YARRICK, FATIGUE_TOT, FATIGUE_TARD, SANS_TRAIT)]}
    observe = {"units": [{"squadId": u["id"],
                          "hp": 1000 if u["alive"] else 0, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000 if u["alive"] else 0, "movement": 3,
                                     "turnsStarted": 0, "attack": 500},
                           "healthMax": 1000,
                           "traits": ([int(UnitTrait.BattleFatigue)]
                                      if u["id"] in fatigues else []),
                           "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": NIVEAU,
                                          "passiveAbilityLevel": NIVEAU,
                                          "activeAbilityLevel": NIVEAU,
                                          "abilityVariablesMultiplier": MULT}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    return st


def _pose_aura(st) -> SummaryExecutionEffect:
    """L'effet 1031 sur Yarrick, tel que `SummaryExecutionAbility$$CreateBehaviour` le materialise."""
    eff = SummaryExecutionEffect(name=EffectType.SummaryExecution_Effect.name,
                                 effect_type=int(EffectType.SummaryExecution_Effect),
                                 target=YARRICK, active=True,
                                 ability_level=NIVEAU, ability_variables_multiplier=MULT)
    st.effects.add_effect(YARRICK, eff)
    return eff


def _porte(st, uid: int) -> bool:
    return bool(st.effects.has_effect(uid, effect_type=IGNORE_BATTLE_FATIGUE))


def _vivifie(st, uid: int) -> None:
    """L'entree dans le selecteur : `AllAliveUnits` filtre `alive` ET `hp > 0` (mirror de
    `BattleQuery$$GetAllAliveUnits` sur `EntityPool.AliveUnits`)."""
    ent = st.get_entity(uid)
    ent.get_component(UnitComponent).alive = True
    from engine.runner.components import HealthComponent
    hc = ent.get_component(HealthComponent)
    if hc is not None:
        hc.hp = 1000


# ------------------------------------------------------------------ le montage est-il NON DEGENERE

def test_le_montage_distingue_bien_les_TROIS_populations(state):
    """CONTROLE : la magnitude de l'aura est resoluble (sinon `_aura_carriers` skippe et TOUT le
    fichier passerait pour vert sans rien exercer), et le selecteur ne retient que les porteurs du
    trait VIVANTS."""
    eff = _pose_aura(state)
    assert eff.aura_stat_modification_amount(), (
        "magnitude nulle -> le driver skippe l'effet : montage DEGENERE (gameconfig absent ?)")
    cibles = set(eff.aura_stat_modification_targets(state, YARRICK))
    assert FATIGUE_TOT in cibles                       # porteur du trait, vivant
    assert FATIGUE_TARD not in cibles                  # porteur du trait, mais MORT -> hors `AllAliveUnits`
    assert SANS_TRAIT not in cibles                    # vivant, mais pas le trait


# ------------------------------------------------------------------------------------ LE FIX

def test_une_cible_qui_ENTRE_apres_coup_recoit_l_immunite(state):
    """LE REGIME DU RESIDU. L'aura est posee alors que `FATIGUE_TARD` n'est pas encore la ; il
    entre ensuite (le mirror offline d'un summon `BattleFatigue`), le driver est reveille, et
    `ApplyInternal` est joue POUR LUI."""
    _pose_aura(state)
    refresh_aura_stat_modifiers(state)                 # 1er reveil : seul `FATIGUE_TOT` est cible
    assert _porte(state, FATIGUE_TOT) is True
    assert _porte(state, FATIGUE_TARD) is False        # la mutation n'a pas encore mordu
    _vivifie(state, FATIGUE_TARD)                      # ... il ENTRE dans le selecteur
    refresh_aura_stat_modifiers(state)                 # 2e reveil (ce que fait `spawn.py`)
    assert _porte(state, FATIGUE_TARD) is True, (
        "l'`ApplyInternal` n'est pas rejoue pour une cible ENTRANTE : le port est retombe sur la "
        "pose UNIQUE depuis le behaviour (#955-r3)")


def test_une_unite_HORS_selecteur_ne_recoit_JAMAIS_l_immunite(state):
    """CONTRE-EPREUVE MORDANTE, sur le MEME etat : sans le trait, pas d'immunite -- meme apres deux
    reveils. Sans elle, l'etage precedent serait indiscernable d'une pose sur tout le monde."""
    _pose_aura(state)
    refresh_aura_stat_modifiers(state)
    _vivifie(state, FATIGUE_TARD)
    refresh_aura_stat_modifiers(state)
    assert _porte(state, SANS_TRAIT) is False
    # Le PORTEUR non plus : `Friends(Owner, UnitsWithTrait(AllAliveUnits, BattleFatigue))` ne le
    # soustrait pas (cf. la docstring du selecteur partage), mais il faut quand meme le TRAIT --
    # et Yarrick ne l'a pas. Les deux gates sont donc exerces separement par ce fichier.
    assert _porte(state, YARRICK) is False


def test_la_pose_est_IDEMPOTENTE(state):
    """Le natif ne joue `ApplyInternal` que sur les cibles ENTRANTES (`GetTargetsToAdd` = desired -
    current). Le port n'a pas la liste `Targets@+0x48` par instance : il derive l'entree du gate
    << deja present >> d'`AddEffectOperation`. Trois reveils ne doivent donc poser qu'UNE instance."""
    _pose_aura(state)
    for _ in range(3):
        refresh_aura_stat_modifiers(state)
    n = sum(1 for e in state.effects.by_unit.get(FATIGUE_TOT, [])
            if not e.consumed and int(e.effect_type) == IGNORE_BATTLE_FATIGUE)
    assert n == 1, f"{n} instances d'immunite empilees -- le gate << deja present >> ne mord plus"


def test_l_AUTRE_aura_du_kit_ne_pose_AUCUN_sous_effet(state):
    """`SummaryExecution_AlwaysEffectEffect` (1043) est posee au CHARGEMENT et partage le meme
    selecteur, mais le natif ne surcharge `ApplyInternal` que sur 1031. Si l'interface etait portee
    sur la base commune, tout allie `BattleFatigue` serait immunise des le debut de la bataille --
    et le passif de Yarrick n'aurait plus d'objet."""
    base = SummaryExecutionBaseEffect(name=EffectType.SummaryExecution_BaseEffect.name,
                                      effect_type=int(EffectType.SummaryExecution_BaseEffect),
                                      target=YARRICK, active=True,
                                      ability_level=NIVEAU, ability_variables_multiplier=MULT)
    state.effects.add_effect(YARRICK, base)
    assert getattr(base, "aura_sub_effects_on_apply", None) is None
    refresh_aura_stat_modifiers(state)
    assert _porte(state, FATIGUE_TOT) is False, (
        "l'immunite est posee par la seule aura PERMANENTE -- `aura_sub_effects_on_apply` a ete "
        "hissee sur la base commune")
