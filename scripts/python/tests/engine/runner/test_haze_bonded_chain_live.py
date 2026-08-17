"""case-haze-bonded -- GARDE de l'ENTITE BONDEE de `HazeOfCorruption_DamageTransfer` (1077) et de la
CHAINE A DEUX RELAIS (`k = 2`).

Critere : le report compare-t-il l'entite REELLEMENT bondee (le 5e argument d'`AddBondEffect`,
ecrit dans le composant de bond de l'entite-effet par
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` et relu par
`IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`), et le port tient-il quand le PREMIER
relais MEURT du report ?

Le montage `k = 1` de case-209/case-221 ne separe PAS « bonded » de « l'auteur du coup fatal » :
les deux valent Maladus. `k = 2` fait mourir le 1er relais SOUS le report, ce qui exerce la
2e passe du bond (source = le 1er relais, cible = le 2e) -- le seul regime live ou la chaine
existe. Les DEUX bonds portent le MEME `bondedEntity` (`Self@0x148`), ce que le flux natif
publie sous `BondEffect_BondedId` : c'est le TEMOIN direct du champ porte.

Regime LIVE : PV 5000 (la cible meurt SANS overkill -> le coup bonus Toxic emet, et le 1er relais
meurt sur le DERNIER transfert). Un PV plus bas fait mourir la cible EN OVERKILL des le 1er coup :
`ApplyDamageOperation$$AddLeftoverHit` bascule alors sur son site (A) (`HasFlag(target, 8)`), qui
pousse la `LeftOverDamage` SANS emettre ni appliquer -- et le 1er relais meurt AVANT la fin de sa
serie de transferts, ce que le port (drain de mort IMMEDIAT) ne reproduit pas encore. Ce residu
d'ORDONNANCEMENT est documente dans `docs/rl/case-haze-bonded-entity.md` ; il n'est PAS
exerce ici, EXPRES.
"""
from __future__ import annotations

import pytest

PROBE = "probe_220_haze_bonded_chain"
SEEDS_CHAINE = ["777", "5", "21", "42"]     # les seeds dont le pick met le relais AMPLIFICATEUR en
                                            # tete -> le 1er relais meurt et la CHAINE part
SEEDS_SANS_CHAINE = ["88", "99"]            # le 1er relais survit : les bonds sont poses, rien ne chaine


def _row(seed, hp=5000):
    import importlib
    P = importlib.import_module(PROBE)
    rpc = P._mkrpc()

    class _A:
        armor, k = 0, 2
    r = P._run(rpc, seed, hp, _A())
    assert r is not None, "montage k=2 KO (seed %s hp %s)" % (seed, hp)
    return r


# --------------------------------------------------------------------------- OFFLINE (structure)

def test_l_instance_d_effet_porte_le_champ_bonded():
    """`DefaultBondEffectBuilder` ecrit `bondedEntityId` dans le composant de bond de l'entite-effet.
    Le port doit le stocker sur l'instance, et `AddEffectOperation` doit savoir le recevoir."""
    import inspect
    from engine.entities.effects.base import BaseEffect
    from engine.runner.operations.effects import AddEffectOperation
    assert BaseEffect.bonded is None, "defaut = effet non-bond"
    assert "bonded" in inspect.signature(AddEffectOperation.execute).parameters, \
        "AddEffectOperation.execute doit transporter le bonded jusqu'a l'instance"


def test_la_feuille_add_bond_effect_a_son_5e_argument():
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect(effectType, abilityState, source, targets,
    **bondedEntity**, options)` : le 5e argument est un SELECTEUR, resolu a l'execution par
    `AddEffectBehaviour$$GetEffectBuilder`. La feuille portee doit l'exposer."""
    from engine.runner.abilities.behaviours.effects import AddBondEffect
    assert "bonded_ref" in AddBondEffect.__slots__


def test_le_target_finder_bonde_le_porteur_sur_les_deux_poses():
    """Les DEUX `AddBondEffect` de `HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` passent
    `Self@0x148` : seule la SOURCE change d'une pose a l'autre."""
    import inspect
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    src = inspect.getsource(H.HazeOfCorruptionTargetFinderAbility.execute_behaviour)
    assert "bonded_ref=Caster()" in src


def test_le_predicat_compare_le_bonded_et_non_le_kit_du_tueur():
    """`AreEqual(Actor@0x158, bonded)` = une EGALITE d'entite. Le port lisait « le tueur porte
    `HazeOfCorruption` » -- une inference qui coincide tant qu'un seul porteur est en jeu."""
    import inspect
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    src = inspect.getsource(H.HazeOfCorruptionDamageTransferTrigger.matches)
    assert "_bonded_id" in src and "int(ev.killer_id) != bonded" in src
    assert "_carries_haze(state, ev.killer_id)" not in src, \
        "le gate ne doit plus INFERER le bonded depuis le kit du tueur"


def test_le_bonded_discrimine_deux_porteurs_du_meme_passif():
    """LE test de l'egalite d'entite -- et il ne peut etre qu'OFFLINE : `HazeOfCorruption` n'a
    qu'UN porteur non-npc (`deathBlightlord`, les 4 autres sont `npc`), donc aucun montage live ne
    peut opposer deux bondes distincts. On monte l'etat a la main : l'effet est bonde a Maladus A,
    le coup fatal vient de Maladus B (qui porte le MEME passif). Le natif compare des ENTITES
    (`AreEqual(Actor@0x158, bonded)`) -> refus ; l'inference « le tueur porte HazeOfCorruption »
    disait OUI."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects_state import EffectsState
    from engine.runner.components import UnitComponent
    from engine.runner.state import State
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki import haze_of_corruption as H

    st = State()
    relay, dying = st.add_entity(), st.add_entity()
    a, b = st.add_entity(), st.add_entity()                # deux porteurs du MEME passif
    for e in (relay, dying, a, b):
        e.add_component(UnitComponent(visual_id="deathBlightlord", alive=True))
    eff = BaseEffect(name=H.HAZE_DAMAGE_TRANSFER_NAME, effect_type=H.HAZE_DAMAGE_TRANSFER)
    eff.source, eff.target, eff.bonded = dying.id, relay.id, a.id
    st.effects = EffectsState(by_unit={relay.id: [eff]})
    trg = H.HazeOfCorruptionDamageTransferTrigger(relay.id)

    def _ev(killer):
        return TriggerEvent(H._ON_PRE_UNIT_DEATH, killer, dying.id, ranged=False, profile=None,
                            killer_id=killer, dying_id=dying.id)
    assert trg.matches(st, _ev(a.id)) is True, "le BONDE tue -> le report part"
    assert trg.matches(st, _ev(b.id)) is False, (
        "un AUTRE porteur du passif tue -> `AreEqual(Actor, bonded)` est FAUX, le report ne part pas")
    # Et le report, s'il part, attaque avec le BONDE (`Attack(bonded, Owner@0x148, ...)`).
    assert trg._bonded_id(st, eff, _ev(b.id)) == a.id


def test_le_report_est_declenche_par_l_effet_0x435():
    """`BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(0x435)` dans l'`AbilityEntities` AVANT
    le behaviour -> la MORT qu'il engendre porte cet id, et c'est lui que lit le
    `NOT TriggeringEffectIs(0x435)` de `HazeCorruption_BonusHitAbility` (meme slot `+0x138` que
    `TriggeringAbilityIs`, decompile lu)."""
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    assert H.HazeOfCorruptionDamageTransferTrigger.TRIGGERED_ABILITY_ID == H.HAZE_DAMAGE_TRANSFER


# --------------------------------------------------------------------------- LIVE

@pytest.mark.parametrize("seed", SEEDS_CHAINE)
def test_la_chaine_a_deux_relais_est_bit_exacte(seed):
    r = _row(seed)
    assert len(r["relays"]) == 2, "montage k=2 attendu, relais lus : %s" % (r["relays"],)
    assert r["trace"]["xfer_fire"] == 2, (
        "la CHAINE doit partir (2 reports) -- trace %s" % (r["trace"],))
    assert r["n_off"] == r["n_native"], (
        "flux RNG : port %s tirages != natif %s (seed %s)" % (r["n_off"], r["n_native"], seed))
    port = {e["id"]: e for e in r["off_entities"]}
    for uid in [r["tid"]] + r["relays"]:
        live = sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == uid)
        off = int(r["hp"]) - int(port[uid]["hp"])
        assert live == off, "degat sur %s : live %s != port %s (seed %s)" % (uid, live, off, seed)


@pytest.mark.parametrize("seed", SEEDS_CHAINE + SEEDS_SANS_CHAINE)
def test_les_deux_bonds_portent_le_meme_bonded_que_le_natif(seed):
    """TEMOIN DIRECT du champ : `BondEffect_BondedId` du flux natif == le `bonded` que le port
    stocke, sur CHAQUE pose -- et c'est le PORTEUR, pas la source (qui, elle, change)."""
    r = _row(seed)
    natif = [(b[1], b[2]) for b in r["bonds"]]              # (source, bonded)
    porte = [(p["source"], p["bonded"]) for p in r["posted"] if p["placed"]]
    assert len(natif) == 2 and natif == porte, \
        "bonds natifs %s != bonds portes %s (seed %s)" % (natif, porte, seed)
    assert {b for _s, b in natif} == {r["cid"]}, \
        "les deux bonds doivent etre bondes au PORTEUR %s : %s" % (r["cid"], natif)
    assert len({s for s, _b in natif}) == 2, "les deux bonds ont des SOURCES distinctes"


@pytest.mark.parametrize("seed", SEEDS_SANS_CHAINE)
def test_sans_chaine_le_port_reste_bit_exact(seed):
    """Controle : meme montage k=2, mais le 1er relais SURVIT -> un seul report. Le port doit rester
    exact (sinon le correctif aurait deplace le regime deja valide)."""
    r = _row(seed)
    assert r["trace"]["xfer_fire"] == 1
    assert r["n_off"] == r["n_native"]
