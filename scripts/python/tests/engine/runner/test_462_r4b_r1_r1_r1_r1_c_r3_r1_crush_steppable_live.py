"""#462-r4b-r1-r1-r1-r1-c-r3-r1 -- un `Steppable` ECRASE perd ses effets, comme dans le natif.

LE CRUSH EST UNE MORT ORDINAIRE POUR LE NATIF. Les quatre `*$$KillSteppableUnits` construisent
INLINE le meme `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` (`+0x00 = 2` =
`DamageReason.Steppable`, `+0x44 = +0x45 = 1`, `+0x46 = 0`) et appellent le slot `KillUnit` --
c'est-a-dire `IdunBattle.Operations.KillUnitOperation$$Execute`, le MEME corps que pour une mort par
degat. Les TROIS `IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` y sont donc
joues, et AUCUN des quatre tests sur `options` n'est sur leur chemin (lu au decompile du build
`rnca9r7q6c` : `+0x45` court-circuite le predicat `IsSteppable`, `+0x44` gate `RecordDeathReason` et
l'emission analytics, `+0x46` gate le flag `Overkilled` -- rien d'autre). Le port, lui, posait
`alive=False` + `hp=0` et RIEN d'autre.

POURQUOI CA MORDAIT. La tranche `-c-r3` a leve les DEUX gates d'owner de la face EFFET (mirror de
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger`, qui n'en a aucun). Un
`Steppable` ecrase etait alors le SEUL regime du port ou un effet-trigger pouvait firer alors que le
natif l'avait deja retire -- et de facon PERSISTANTE, puisque rien ne retirait jamais ces effets.

⚠ DEUX BRAS DE CE FICHIER ONT CHANGE DE SENS AVEC `-r1`/`-r3`, ET C'EST LE SIGNAL QU'ILS DEVAIENT
DONNER. Ils gardaient le RESIDU de la tranche precedente -- « le port ne publie qu'`On(0x35)` » et
« AUCUN kit `Steppable` n'est inscrit a un registre » -- en annoncant qu'ils rougiraient le jour ou
l'emission serait portee / ou un porteur naturel apparaitrait. Les deux sont arrives ENSEMBLE :
`_kill_steppable_kill_unit` joue desormais `IdunBattle.Operations.KillUnitOperation$$Execute` en
entier, et `HaywireMineSteppable` est inscrite. Les bras gardent maintenant l'etat INVERSE (les cinq
evenements sont publies ; les deux mines Haywire sont les SEULS kits `Steppable` inscrits), et la
confrontation de ce nouveau comportement vit dans
`test_462_r4b_r1_r1_r1_r1_c_r3_r1_r1_crush_death_events_live.py` (natif vs port sur une mine REELLE).

⚠ LE REGIME DU RETRAIT RESTE QUASI-VIDE COTE KIT : les **27** kits `Steppable` (dont **20**
`Immune`) n'ont que l'entree `HaywireMineSteppable`. Aucune garde de comportement du RETRAIT sur un
porteur naturel n'est donc possible. Ce fichier garde a la place (a) la STRUCTURE (le port
appelle-t-il les trois retraits, dans l'ordre ?), (b) des montages SYNTHETIQUES explicitement
etiquetes comme tels, et (c) l'INVENTAIRE des porteurs inscrits, qui rougit a tout mouvement.

ASCII only.
"""
from __future__ import annotations

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effects.factory import EffectFactory
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait, has_trait
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.messages import MoveUnitMessage
from engine.runner.operations import movement as MV
from engine.runner.operations.movement import _kill_steppable_kill_unit, _kill_steppable_units
from engine.entities.kill_unit_step import KillUnitStep
from engine.runner.operations.spawn import spawn_decoy
from engine.runner.operations.triggers.base import EffectTrigger, TriggerEvent
from engine.runner.operations.triggers.dispatch import core as CORE
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state
from engine.runner.state import State

import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable as PR

# Board et roster explicites (jamais le defaut) -- DIFFERENTS de ceux de `-c-r3` (`C3_01`,
# `ultraTitus,bloodIntercessor,eldarFarseer` vs `worldKharn,orksNob,orksWarboss`) : le crush ne doit
# dependre d'aucune particularite de l'etat qui a servi a la tranche precedente.
BUILD = ["--p-units", "necroSpyder,orksKillaKan,adeptMorvenn",
         "--a-units", "genesPatriarch,genesMagus,tyranNeurothrope",
         "--rank", "17", "--board", "MC1_67"]

# Les CINQ evenements de `KillUnitOperation$$Execute`, dans l'ordre du decompile.
EVENTS_MORT = (int(EventTriggerType.PreUnitDeath), int(EventTriggerType.PreUnitDeath_2),
               int(EventTriggerType.UnitDeath), int(EventTriggerType.UnitDefeated),
               int(EventTriggerType.PostUnitKill))
# Le SEUL qui ne vienne PAS de la sequence de mort : `after_move_triggers` le publie APRES, sur le
# chemin MOVE (ecart d'ORDRE et de COUVERTURE prealable -- cf. `_kill_steppable_kill_unit`).
EVENT_HORS_SEQUENCE = int(EventTriggerType.PostUnitKill)


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="module")
def env_live(live_session, rpc, build_runner):
    """Un BOARD et des UNITES reels. Portee MODULE : un seul runner pour tout le fichier.

    ⚠ Un montage qui ne s'installe pas ECHOUE (#268) -- un `pytest.skip` serait un VERT qui ment."""
    built = build_runner("31337", extra=BUILD)
    rid = built["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible -- montage non installe"
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    st0 = load_state(dv, ob, snap, board=board, tiles=tm)
    assert getattr(st0, "effects", None) is not None, "pas d'EffectsState (combatSnapshot partiel)"
    assert st0.entities, "decisionView vide -- montage non installe"
    return {"rid": rid, "dv": dv, "ob": ob, "snap": snap, "board": board, "tiles": tm}


def _fresh(env, seed: int = 777) -> State:
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"], tiles=env["tiles"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


def _mover_et_tuile_libre(state: State, board):
    """Un mover VIVANT + une tuile marchable LIBRE adjacente -- on y posera le decoy a ECRASER.

    On DEPLACE la configuration plutot que d'esperer la geometrie de spawn : le decoy est pose sur
    une tuile choisie, et le mover y marche."""
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ.add(t)
    for uid, e in sorted(state.entities.items()):
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if pc is None or uc is None or not uc.alive or oc is None:
            continue
        mt = board.id_at(pc.col, pc.row)
        if mt is None:
            continue
        for t in sorted(board.neighbours(mt)):
            if board.walkable(t) and t not in occ:
                info = board.by_id.get(t)
                return uid, t, (info["col"], info["row"])
    pytest.fail("aucun mover vivant avec une tuile libre adjacente -- montage non installe")


def _pose_effets(state: State, uid: int, effect_types: list[int]) -> None:
    for i, et in enumerate(effect_types):
        state.effects.add_effect(int(uid), EffectFactory.create(
            {"name": "CrushSonde%d" % i, "effectType": int(et), "remaining": 0}, 100, None, None))


def _actifs(state: State, uid: int) -> list[int]:
    return [int(e.effect_type) for e in state.effects.by_unit.get(int(uid), []) if not e.consumed]


class _SondeEvents(EffectTrigger):
    """Effet-trigger NU qui NOTE les evenements vus, sans muter. Porte par une unite VIVANTE."""
    event_id = EVENTS_MORT[0]
    event_ids: tuple = EVENTS_MORT
    fire_on_death = False
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeEvents.vus.append(int(ev.event_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_libre() -> int:
    et = 960001
    while et in REG.EFFECT_TRIGGERS:
        et += 1
    return et


# --------------------------------------------------------------------------- (a) STRUCTURE

def test_le_crush_appelle_les_trois_RemoveEffects_dans_l_ordre(monkeypatch):
    """GARDE DE STRUCTURE -- le regime etant vide cote kit, c'est elle qui tient le port.

    Mirror de `IdunBattle.Operations.KillUnitOperation$$Execute` : `RemoveEffects(killed, 0)`
    (`+0x9be`), `RemoveEffects(killed, 1)` (`+0xd9c`), puis `RemoveEffects(killed, 2)` (`+0xf59`).
    L'ordre est LOAD-BEARING : les steps sont des FILTRES (`RemoveEffectsOptions+0x00`), pas des
    passes redondantes."""
    vus: list[int] = []

    def _capteur(state, dead_id, step):
        vus.append(int(step))
        return []

    monkeypatch.setattr("engine.runner.operations.damage._kill_unit_remove_effects", _capteur)
    st, mover, decoy = PR._make_state_crush([])
    tues = _kill_steppable_units(st, (1, 1), mover)
    assert tues == [decoy], "le crush n'a pas eu lieu (montage) : %s" % (tues,)
    assert vus == [int(KillUnitStep.PreUnitRemove), int(KillUnitStep.AfterUnitRemove),
                   int(KillUnitStep.AfterDeathTrigger)], \
        "les trois RemoveEffects ne sont pas joues dans l'ordre natif : %s" % (vus,)


def _steps_retires(trace) -> list[int]:
    """Les `KillUnitStep` joues, lus dans la trace de `_kill_unit_operation` (entrees
    `kill_remove_effects`)."""
    return [int(x["kill_remove_effects"]["step"]) for x in (trace or [])
            if isinstance(x, dict) and "kill_remove_effects" in x]


def test_la_garde_HEAL_saute_le_troisieme_retrait():
    """GARDE @`KillUnitOperation$$Execute+0xf35` : `if (health.hp > 0) RETURN`.

    ⚠ MONTAGE SYNTHETIQUE ASSUME -- ce regime EXIGE qu'un consommateur des evenements de mort
    SOIGNE le mourant entre le 2e et le 3e retrait. On appelle donc `_kill_steppable_kill_unit`
    DIRECTEMENT sur une unite a PV > 0.
    ⚠ DEPUIS `-r1` LA GARDE N'EST PLUS INERTE SUR CE CHEMIN : le crush publie desormais `On(1)`,
    `On(2)`, `On(0)` et `On(0x36)`, donc un `Heal`/`Revive` declenche par l'un d'eux peut vraiment
    ramener les PV au-dessus de zero avant le 3e `RemoveEffects`. C'est exactement ce que la
    tranche precedente avait anticipe en la portant << bien qu'inatteignable >>."""
    st, mover, decoy = PR._make_state_crush([])
    st.get_entity(decoy).get_component(HealthComponent).hp = 5      # << soigne >> avant le step 2
    steps = _steps_retires(_kill_steppable_kill_unit(st, decoy, mover))
    assert steps == [int(KillUnitStep.PreUnitRemove), int(KillUnitStep.AfterUnitRemove)], \
        "la garde HEAL n'a pas coupe le 3e retrait : %s" % (steps,)
    st2, m2, d2 = PR._make_state_crush([])
    st2.get_entity(d2).get_component(HealthComponent).hp = 0
    steps2 = _steps_retires(_kill_steppable_kill_unit(st2, d2, m2))
    assert len(steps2) == 3, "a PV 0 les TROIS retraits doivent tourner : %s" % (steps2,)


# --------------------------------------------------------------------------- (b) LIVE

def test_le_crush_vide_les_effets_du_steppable(env_live):
    """Sur un etat LIVE et par le VRAI pipeline de move : le decoy ecrase n'a plus AUCUN effet actif.

    Les effets sont posES a la main (aucun poseur naturel ne vise un `Steppable`, cf. l'en-tete),
    mais le CRUSH, lui, est le vrai : `Runner.apply(MoveUnitMessage)` ->
    `MoveUnitOperation.execute` -> `_kill_steppable_units`."""
    st = _fresh(env_live)
    board = env_live["board"]
    mover, tuile, dest = _mover_et_tuile_libre(st, board)
    decoy = spawn_decoy(st, tuile, mover)
    assert decoy is not None, "spawn_decoy a rendu None -- montage non installe"
    traits = list(getattr(st.get_entity(decoy).get_component(StatsComponent).ctx, "traits", None) or [])
    assert has_trait(traits, UnitTrait.Steppable), "le token pose n'est pas Steppable : %s" % traits
    et = _effect_type_libre()
    _pose_effets(st, decoy, [et, et + 1, et + 2])
    assert len(_actifs(st, decoy)) == 3, "montage : les 3 effets ne sont pas poses"

    Runner(st).install_default_handlers().apply(MoveUnitMessage(mover, dest))

    assert st.get_entity(decoy).get_component(UnitComponent).alive is False, "le decoy n'a pas ete crushe"
    assert _actifs(st, decoy) == [], \
        "le decoy ecrase garde des effets ACTIFS : %s" % (_actifs(st, decoy),)


def test_le_regime_c_r3_est_ferme_le_trigger_d_effet_ne_fire_plus(env_live):
    """LE BRAS QUI MORD -- et son TEMOIN, qui prouve qu'il discrimine.

    La face EFFET ne gate plus ni l'existence ni la vivacite du porteur (`-c-r3`, mirror de
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger`). Donc, tant que l'effet
    est la, son trigger fire -- mort ou pas. C'est exactement le regime que le retrait ferme, et il
    le ferme du BON COTE : l'effet n'existe plus, plutot qu'un gate que le natif n'a pas.

    | bras   | montage                         | attendu |
    |--------|---------------------------------|---------|
    | TEMOIN | decoy VIVANT, effet pose        | fire    |
    | MORD   | le meme decoy, ECRASE par le move | ne fire plus |"""
    et = _effect_type_libre()
    board = env_live["board"]

    class _Sonde(EffectTrigger):
        event_id = int(EventTriggerType.PreUnitDeath_2)
        fire_on_death = False
        vus: list = []

        def matches(self, state, ev) -> bool:
            _Sonde.vus.append(int(self.owner_id))
            return False

        def execute_behaviour(self, state, ev):
            return None

    REG.EFFECT_TRIGGERS[et] = [_Sonde]
    try:
        # --- TEMOIN : aucun crush
        st_t = _fresh(env_live)
        mover_t, tuile_t, _dest_t = _mover_et_tuile_libre(st_t, board)
        decoy_t = spawn_decoy(st_t, tuile_t, mover_t)
        assert decoy_t is not None, "spawn_decoy TEMOIN a rendu None -- montage non installe"
        _pose_effets(st_t, decoy_t, [et])
        _Sonde.vus = []
        CORE.evaluate_trigger_operation(st_t, TriggerEvent(
            _Sonde.event_id, mover_t, decoy_t, ranged=False, profile=None))
        temoin = len(_Sonde.vus)

        # --- MORD : le meme montage, mais le mover ECRASE le decoy
        st_m = _fresh(env_live)
        mover_m, tuile_m, dest_m = _mover_et_tuile_libre(st_m, board)
        decoy_m = spawn_decoy(st_m, tuile_m, mover_m)
        assert decoy_m is not None, "spawn_decoy MORD a rendu None -- montage non installe"
        _pose_effets(st_m, decoy_m, [et])
        Runner(st_m).install_default_handlers().apply(MoveUnitMessage(mover_m, dest_m))
        _Sonde.vus = []
        CORE.evaluate_trigger_operation(st_m, TriggerEvent(
            _Sonde.event_id, mover_m, decoy_m, ranged=False, profile=None))
        apres = len(_Sonde.vus)
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)

    assert temoin > 0, "le TEMOIN ne fire pas -- le montage ne discrimine RIEN (a reparer)"
    assert apres == 0, \
        "l'effet du decoy ECRASE fire encore (%d passage(s)) : le retrait n'a pas mordu" % apres


def test_les_cinq_evenements_de_mort_sont_emis_au_crush(env_live):
    """CE BRAS A CHANGE DE SENS AVEC `-r1`, et c'est le signal qu'il etait cense donner.

    Il gardait le RESIDU (« le port ne publie qu'`On(0x35)` ») ; l'emission est desormais portee
    (`movement.py::_kill_steppable_kill_unit` -> `damage.py::_kill_unit_operation`), donc il garde
    maintenant l'INVERSE : sur le chemin MOVE, un crush publie les CINQ evenements de
    `KillUnitOperation$$Execute`. Depuis #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 les cinq sortent du MEME
    foyer -- `On(0x35 = PostUnitKill)` ne vient plus, APRES coup, d'`after_move_triggers`.

    D'ou le second volet, qui n'avait pas lieu d'etre avant : `On(0x35)` doit partir UNE SEULE
    FOIS. Deplacer une emission sans retirer l'ancienne est le mode de panne exact de cette
    tranche, et l'assertion d'ENSEMBLE ci-dessus y est structurellement AVEUGLE.

    Une sonde portee par le MOVER (donc VIVANT, hors de tout gate) les ecoute tous les cinq. Le
    blast radius de cette emission est confronte par
    `test_462_r4b_r1_r1_r1_r1_c_r3_r1_r1_crush_death_events_live.py` (mine Haywire natif vs port,
    plus deux consommateurs portes par le MOVER avec leur temoin)."""
    et = _effect_type_libre()
    REG.EFFECT_TRIGGERS[et] = [_SondeEvents]
    try:
        st = _fresh(env_live)
        mover, tuile, dest = _mover_et_tuile_libre(st, env_live["board"])
        decoy = spawn_decoy(st, tuile, mover)
        assert decoy is not None, "spawn_decoy a rendu None -- montage non installe"
        _pose_effets(st, mover, [et])            # la sonde vit sur le MOVER, qui reste vivant
        _SondeEvents.vus = []
        Runner(st).install_default_handlers().apply(MoveUnitMessage(mover, dest))
        bruts = list(_SondeEvents.vus)
        vus = sorted(set(bruts))
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)

    assert st.get_entity(decoy).get_component(UnitComponent).alive is False, "le decoy n'a pas ete crushe"
    assert vus == sorted(EVENTS_MORT), (
        "le crush publie %s ; attendus les CINQ evenements %s -- si l'un manque, la sequence de "
        "mort du crush a ete rabotee" % (vus, sorted(EVENTS_MORT)))
    # #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 : `On(0x35)` a DEMENAGE (`after_move_triggers` -> le foyer).
    # Un DOUBLON serait invisible pour l'assertion d'ensemble ci-dessus, et signifierait que
    # l'ancienne emission n'a pas ete retiree -- donc DEUX heals pour un seul crush.
    n35 = bruts.count(int(EventTriggerType.PostUnitKill))
    assert n35 == 1, (
        "`On(0x35 = PostUnitKill)` est publie %d fois pour UN crush (sequence brute %s). Le foyer "
        "`_kill_unit_operation` le publie ; si un second emetteur subsiste (pipeline de move), tout "
        "consommateur -- `CosmicHorrorOnMoveAbility` en tete -- fire DEUX fois." % (n35, bruts))


# --------------------------------------------------------------------------- (c) L'ENONCE DU VIDE

def test_les_seuls_kits_steppable_inscrits_sont_les_mines_haywire():
    """CE BRAS AUSSI A CHANGE DE SENS, et c'est ce qu'il annoncait.

    Il enoncait le regime VIDE (« AUCUN kit `Steppable` n'est inscrit a un registre »), en disant
    qu'il rougirait « le jour ou un porteur naturel apparaitra : signal, pas regression ». Ce jour
    est arrive : `-r3` inscrit `HaywireMineSteppable`, portee par les DEUX mines du gameconfig
    (`astarSmnHaywireMine`, summon d'`astarCyrus` -- et `astarNpc1HaywireMine`, npc).

    Il garde donc maintenant l'inventaire EXACT : ces deux-la, et personne d'autre. Un troisieme
    porteur qui apparaitrait le ferait rougir -- meme signal, meme raison.

    ⚠ ET IL A ROUGI, EXACTEMENT COMME ANNONCE (#1083-r1, 2026-08-14) : les CINQ unites-objet
    `powup*` du gameconfig portent chacune un passif `PowerUp_*` de BOOST DE STAT, desormais inscrit
    a `ABILITY_TRIGGERS`. Ce sont des porteurs NATURELS au meme titre que les mines -- meme trait
    `Steppable`, meme vecteur : c'est leur MORT PAR ECRASEMENT (`On(1 = PreUnitDeath)` sous
    `KillUnitOperationOptions$$ForSteppable`) qui donne le bonus a celui qui les a traversees. Ils
    ne partagent donc PAS seulement le trait, ils partagent la mecanique que ce fichier garde.
    L'inventaire passe de 2 a 7 ; le cran reste EXACT.

    ⚠ ET IL A ROUGI UNE SECONDE FOIS, POUR LA MEME RAISON (#1083-r3, 2026-08-15) : la tranche 2
    inscrit les `PowerUp_*` NON-BOOST, dont deux ont un porteur `Steppable` -- `powupHealing`
    (`PowerUp_Healing`) et `powupReactivateAbility` (`PowerUp_ReactivateAbility`). Meme trait, meme
    vecteur de mort, et meme BASE : ces deux-la heritent le trigger d'`APowerUpAbility` sans le
    surcharger (ZERO des 22 `PowerUp_*` ne surcharge `CreateTrigger`). L'inventaire passe de 7 a 9.

    ⚠ Les QUATRE autres `PowerUp_*` non-boost (`Bomb`, `Reinforcement`, `ReinforcementShield`,
    `Resurrect`) portent le MEME trait et le MEME vecteur, mais ne sont PAS inscrits -- donc pas
    ici. Leur absence de cette liste est un FAIT PORTEUR, pas un oubli : elle dit que leur mecanique
    n'a pas d'observable porte (`PlayerType` non projete pour le gate `IsHumanPlayer` de `Bomb` ;
    ni `PlayerComponent` ni `DraftingComponent` pour les trois de Survival). Cf.
    `docs/rl/case-1083-r3-powerup-non-boost.md`. Le jour ou l'une entre au registre, ce cliquet
    rougira -- et ce sera le bon signal.

    ⚠ Il ne dit RIEN des EFFETS qu'un `Steppable` peut RECEVOIR de l'exterieur (DoT de tuile, aura,
    bond) : ceux-la ne sont pas dans le kit, et ce sont eux que les trois retraits emportent."""
    kits = PR._kits_steppable()
    assert len(kits) >= 2, "gisement vide -- gameconfig non charge (montage)"
    inscrits = []
    for k in kits:
        for t in (k.get("traits") or []):
            if REG.TRAIT_TRIGGERS.get(t):
                inscrits.append((k["id"], "trait:%s" % t))
        for a in (k.get("abilities_all") or []):
            for nom, reg in (("passive", REG.ABILITY_TRIGGERS), ("active", REG.ACTIVE_ABILITY_TRIGGERS),
                             ("relic", REG.RELIC_ABILITY_TRIGGERS)):
                if reg.get(a):
                    inscrits.append((k["id"], "%s:%s" % (nom, a)))
    attendus = [("astarNpc1HaywireMine", "passive:HaywireMineSteppable"),
                ("astarSmnHaywireMine", "passive:HaywireMineSteppable"),
                # #1083-r1 -- les cinq POWER-UPS de boost de stat. Meme trait, meme vecteur de mort.
                ("powupArmor", "passive:PowerUp_Armor"),
                ("powupDamage", "passive:PowerUp_Damage"),
                # #1083-r3 -- les NON-BOOST inscrits par la tranche 2 (ordre alphabetique).
                ("powupHealing", "passive:PowerUp_Healing"),
                ("powupHealth", "passive:PowerUp_Health"),
                # #10004 -- les NEUF `PowerUp_*Spawn*` VIVANTS. `powupHeroSpawn` et
                # `powupSummonSpawn` (les deux BASES) n'y sont PAS : leur gameconfig ne porte
                # aucune constante, donc elles ne spawnent rien et ne sont pas inscrites.
                ("powupHeroSpawn_BladeChampion", "passive:PowerUp_HeroSpawn_BladeChampion"),
                ("powupHeroSpawn_Uthar", "passive:PowerUp_HeroSpawn_Uthar"),
                ("powupHeroSpawn_VexilusPraeto", "passive:PowerUp_HeroSpawn_VexilusPraetor"),
                ("powupHits", "passive:PowerUp_Hits"),
                ("powupMeleeHits", "passive:PowerUp_MeleeHits"),
                ("powupReactivateAbility", "passive:PowerUp_ReactivateAbility"),
                ("powupSummonSpawn_bloodSmnIntercessor",
                 "passive:PowerUp_SummonSpawn_bloodSmnIntercessor"),
                ("powupSummonSpawn_darkaSmnHellblaster",
                 "passive:PowerUp_SummonSpawn_darkaSmnHellblaster"),
                ("powupSummonSpawn_darkaSmnTerminator",
                 "passive:PowerUp_SummonSpawn_darkaSmnTerminator"),
                ("powupSummonSpawn_templSmnAggressor",
                 "passive:PowerUp_SummonSpawn_templSmnAggressor"),
                ("powupSummonSpawn_ultraSmnHeavyIntercessor",
                 "passive:PowerUp_SummonSpawn_ultraSmnHeavyIntercessor"),
                ("powupSummonSpawn_ultraSmnInceptor",
                 "passive:PowerUp_SummonSpawn_ultraSmnInceptor")]
    assert sorted(inscrits) == attendus, (
        "les kits Steppable inscrits a un registre d'ability-trigger sont %s ; attendus %s -- un "
        "porteur NATUREL de plus (ou de moins) : re-confronter le regime" % (sorted(inscrits), attendus))
