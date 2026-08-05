"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r1 / -r2 / -r3 -- le crush d'un `Steppable` PUBLIE ses evenements
de mort, avec sa RAISON, et la mine Haywire les CONSOMME.

La tranche precedente (`-c-r3-r1`) avait porte le RETRAIT des effets du crushe et laisse l'EMISSION
dehors : blast radius mesure a 27 classes, aucune confrontation possible SUR UN PORTEUR NATUREL (le
croisement kit x registres rendait alors **0** kit `Steppable` inscrit). Cette tranche ferme les
trois residus ENSEMBLE, parce qu'ils ne se confrontent que l'un par l'autre :

  `-r2` `RecordDeathReason(killer, killed, uc, DamageReason.Steppable = 2)` -- gate `options+0x44`,
        qui vaut `1` sous `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` ;
  `-r1` les QUATRE evenements manquants (`On(1)`, `On(2)`, `On(0)`, `On(0x36)`) -- le crush passe
        desormais par le MEME `IdunBattle.Operations.KillUnitOperation$$Execute` que la mort par
        degat (`movement.py::_kill_steppable_kill_unit` -> `damage.py::_kill_unit_operation`) ;
  `-r3` `HaywireMineSteppableAbility`, qui n'existe QUE pour ce regime : son `CreateTrigger` teste
        `HasDeathReason(Owner, DamageReason.Steppable)`, valeur que SEUL un crush grave.

GROUND TRUTH LIVE (mesuree avant d'ecrire une ligne de port, runner `MC1_67`, `astarCyrus` injecte
au catalogue) -- un `necroWarden` **MECHANICAL** marche sur une mine posee par Cyrus :

    [Ability_Power e=110 «HaywireMineSteppable»]
      Amount=3832 DamageProfileType=18 (Blast)  Attacker=110 Target=77 FirstHit=1
      Amount=318  DamageProfileType=16 (Energy) Attacker=110 Target=77 FirstHit=1
      Amount=323  DamageProfileType=16 (Energy) Attacker=110 Target=77 FirstHit=0
    DirectlyKillUnit e=110 / RemoveUnitFromTiles e=110 / RemoveUnit e=110

-> 1 coup `Blast` + 2 coups `Energy` = le `If(HasTrait(Actor, 5 = Mechanical), atk1 + atk2, atk1)`
du behaviour, ET l'explosion PRECEDE le retrait de la mine du plateau (donc `On(1 = PreUnitDeath)`
est bien publie AVANT `processor.<slot 6>`, comme au decompile). Sur un `orksNob` NON-mecanique la
meme mine ne produit qu'UN evenement (`Amount=1403`, profil 18) : la branche `else`.

⚠ LE HARNAIS A DU ETRE REPARE POUR QUE LA MESURE AIT UN SENS. Une unite INVOQUEE n'a AUCUNE
`UnitConfiguration` native, donc `combatSnapshot.unitConfig` rend `{"error": "config null"}` et le
port lisait `passive_ability_level = 0` : toutes les variables per-niveau d'un passif de SUMMON
etaient prises a l'index 0. Mesure sur cette mine : `minDmg[0] = 50` au lieu de
`minDmg[49] x 180 % = 4986`, facteur ~55. `snapshot._load_passive_abilities` seede desormais
l'`AbilityState` depuis `unitAbilityStates` **quand, et seulement quand, le trou existe**.

ASCII only.
"""
from __future__ import annotations

import json
import uuid

import pytest

import hexgeo

from engine.entities import formulas as F
from engine.entities.damage_reason import DamageReason
from engine.entities.pathfinding.board import Board
from engine.entities.traits import UnitTrait, has_trait
from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r1_crush_death_events as PR

BOARD = "MC1_67"
SUMMONER = "astarCyrus"                 # HERO `lineup` HORS seed BC -> catalog_inject
MINE_VIS_FRAGMENT = "HaywireMine"       # le summon prend le visualId npc `astarNpc1HaywireMine`
MECH_ENEMY = "necroWarden"              # MECHANICAL -> exerce la branche `If(...)` VRAIE
ALLY = "ultraTitus"                     # meme equipe que Cyrus -> bras NEGATIF (`AreEnemies`)
BLAST = 18                              # `DamageProfileType.Blast`  (constante `damageProfile`)
ENERGY = 16                             # `DamageProfileType.Energy` (constante `damageProfile_2`)


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    """`decisionView` -- LE canal de vivacite. ⚠ PAS `observeBattle` : son `isDead` est derive des
    PV, or une mine Haywire a **0 PV par construction** (`UnitStats_MaxHealth=0` a l'`AddUnit`), donc
    elle y apparait `isDead: true` des sa pose. Mesure : un montage filtre sur `observeBattle`
    voyait ZERO mine sur un plateau qui en portait deux. `decisionView.units[].alive` porte, lui, le
    `UnitComponent` -- il distingue la mine POSEE de la mine ECRASEE."""
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _by_vis(dv, vis, contains=False):
    for u in _units(dv):
        v = u.get("visualId") or ""
        if (vis in v) if contains else (v == vis):
            return u
    return None


def _uid(u):
    return u.get("id", u.get("squadId", u.get("entityId")))


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _move(rpc, rid, unit_id, dest):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": unit_id, "to": {"col": dest[0], "row": dest[1]}}}, 120)


def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _step_one(rpc, rid, unit_id, cur, target, avoid=()):
    """UN SEUL hex vers `target`, choisi dans le set LEGAL (`aiMovableTiles`), hors `avoid`.

    UN SEUL, et c'est load-bearing : `MoveUnitOperation` traverse TOUTES les tuiles du chemin, donc
    une destination lointaine ecrase les mines rencontrees EN ROUTE. Mesure du montage naif
    (destination = la plus proche du but) : `necroWarden` a detruit QUATRE mines et s'est tue avant
    la premiere capture. En ne bougeant que d'un hex, le chemin EST la tuile choisie."""
    tiles = {t for t in (_movable(rpc, rid, unit_id) - set(avoid))
             if hexgeo.distance(t, tuple(cur)) == 1}
    if not tiles:
        return None
    best = min(tiles, key=lambda t: hexgeo.distance(t, tuple(target)))
    _move(rpc, rid, unit_id, best)
    return best


def _assure_tour(rpc, rid, unit_id, max_endturns: int = 3) -> bool:
    """Amene le tour sur l'equipe de `unit_id` : `aiMovableTiles` ne rend QUE le joueur courant, donc
    un set VIDE veut souvent dire << pas son tour >>, pas << aucun deplacement legal >>. Rend False
    si l'unite n'a toujours aucun pas apres `max_endturns` (deja agi, ou vraiment bloquee)."""
    for _ in range(max_endturns + 1):
        if _movable(rpc, rid, unit_id):
            return True
        _endturn(rpc, rid)
    return bool(_movable(rpc, rid, unit_id))


def _mines(dv):
    """`{(col,row): unitId}` des mines VIVANTES du plateau."""
    return {_pos(u): _uid(u) for u in _units(dv)
            if MINE_VIS_FRAGMENT in (u.get("visualId") or "")}


def _mine_a_portee(rpc, rid, unit_id):
    """Une mine VIVANTE dans le set de deplacement LEGAL de `unit_id` ? -> `((col,row), mineId, dv)`.

    ⚠ `aiMovableTiles` ne rend QUE les unites du joueur COURANT : appeler ceci hors du tour de
    `unit_id` rend systematiquement `None`, ce qui se lirait a tort comme << aucune mine a portee >>."""
    dv = _vue(rpc, rid)
    mines = _mines(dv)
    reach = _movable(rpc, rid, unit_id)
    for p in sorted(mines):
        if p in reach:
            return p, mines[p], dv
    return None, None, dv


def _dmg_events(res):
    """Les `UnitDamaged` de la cascade d'un `applyAction` (tags JSON sous `actions[].events[]`)."""
    out = []
    for act in ((res or {}).get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td:
                out.append(td)
    return out


def _capture(rpc, rid):
    """Tout ce qu'il faut pour rejouer le pas OFFLINE, capture AVANT le crush."""
    cap = {"bg": rpc("boardGraph", {"runnerId": rid}, 60),
           "dv": rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120),
           "ob": rpc("observeBattle", {"runnerId": rid}, 60),
           "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
           "tm": rpc("tileMeta", {"runnerId": rid}, 60),
           "ab": rpc("unitAbilityStates", {"runnerId": rid}, 60)}
    assert _ok(cap["dv"]) and _ok(cap["ob"]) and _ok(cap["snap"]), \
        "capture live KO -- montage non installe"
    return cap


def _state(cap, seed=777):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"],
                    ability_states=cap.get("ab"))
    st.rng = IntBasedMersenneTwister(seed)
    return st


@pytest.fixture(scope="module")
def env_mine(live_session, rpc, build_runner, tmp_path_factory):
    """Un runner ou une MINE REELLE existe, avec un ennemi MECANIQUE a portee d'elle.

    ⚠ Aucun `pytest.skip` : un montage qui ne s'installe pas ECHOUE (#268). La mine est posee par le
    passif `HaywireMine` d'`astarCyrus` (`On(4 = UnitAfterMove) & OwnerIsActor` -> `Spawn` sur sa
    tuile PRECEDENTE) -- le port ne pose PAS de mine (residu nomme), c'est le NATIF qui la pose."""
    import catalog_inject
    # Le seed BC augmente est un JETABLE de CE run : `tmp_path_factory`, jamais un chemin construit
    # sous la racine (`data/` est REFUSE par `catalog_inject --out`, et un chemin `logs/` fabrique
    # ici ferait rougir `probe_273` -- une entree gitignoree lue depuis la racine hors
    # `host_inputs`).
    bc = tmp_path_factory.mktemp("seedbc") / ("cyrus-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [SUMMONER])
    built = build_runner("777", extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--rank", "17", "--no-ai",
        "--p-units", "%s,%s" % (SUMMONER, ALLY), "--a-units", "%s,orksNob" % MECH_ENEMY,
        # LEVIER DE MONTAGE, pas de confort : les spawns de `MC1_67` sont a ~10 hex et Cyrus ne
        # seme ses mines que sur sa tuile PRECEDENTE. Un rapprochement pas-a-pas fait traverser les
        # mines par leur porteur (`MoveUnitOperation` ecrase TOUTES les tuiles du chemin -- mesure :
        # 4 mines detruites et l'ennemi tue avant la 1re capture). En donnant la PORTEE au marcheur,
        # le pas mesure est UNIQUE et choisi par nous. Aucune incidence sur ce qu'on mesure : le
        # `Movement` n'entre dans aucun etage de `HaywireMineSteppableAbility`.
        "--unit-stat", "%s:Movement=25" % MECH_ENEMY,
        "--unit-stat", "%s:Movement=25" % ALLY], keep=True)
    rid = built["rid"]

    dv = _vue(rpc, rid)
    assert _ok(dv), "decisionView KO -- montage non installe"
    cyrus = _by_vis(dv, SUMMONER)
    foe = _by_vis(dv, MECH_ENEMY)
    assert cyrus is not None and foe is not None, \
        "%s / %s absents du plateau -- injection catalogue ou pool KO" % (SUMMONER, MECH_ENEMY)
    cyrus_id, foe_id = _uid(cyrus), _uid(foe)

    # POSE DES MINES : SEUL Cyrus bouge, un hex a la fois, en EVITANT ses propres mines (il les
    # ecraserait -- le crush ne regarde pas l'equipe). L'ennemi et l'allie, eux, ne bougent PAS
    # pendant cette phase : c'est ce qui garantit qu'ils arrivent INTACTS au moment de la capture,
    # et que leur unique pas mesure est celui qu'on leur fait faire. TROIS mines : une par bras qui
    # en CONSOMME une (positif MECANIQUE, negatif ALLIE) plus celle que lit le bras de HARNAIS.
    for _ in range(3):
        assert _assure_tour(rpc, rid, cyrus_id), "Cyrus n'a aucun pas legal -- montage non installe"
        dv = _vue(rpc, rid)
        c, f = _by_vis(dv, SUMMONER), _by_vis(dv, MECH_ENEMY)
        assert c is not None and f is not None, (
            "un protagoniste est mort avant la mesure -- montage instable ; vus = %s"
            % [(u.get("visualId"), _uid(u), u.get("alive"))
               for u in ((dv or {}).get("units") or [])])
        assert _step_one(rpc, rid, cyrus_id, _pos(c), _pos(f), avoid=_mines(dv)) is not None, \
            "aucun pas d'UN hex libre pour Cyrus -- montage non installe"
        _endturn(rpc, rid)
    dv = _vue(rpc, rid)
    assert len(_mines(dv)) >= 3, (
        "le passif `HaywireMine` de %s n'a pas pose 3 mines (%d) -- le montage n'exerce rien"
        % (SUMMONER, len(_mines(dv))))
    assert _assure_tour(rpc, rid, foe_id), \
        "%s n'a aucun deplacement legal -- montage non installe" % MECH_ENEMY
    pos, mine_id, _dv = _mine_a_portee(rpc, rid, foe_id)
    assert pos is not None, (
        "aucune mine dans le set de deplacement de %s -- le levier `Movement` n'a pas pris"
        % MECH_ENEMY)
    return {"rid": rid, "cyrus": cyrus_id, "foe": foe_id, "ally_vis": ALLY,
            "mine_pos": pos, "mine_id": mine_id}


# --------------------------------------------------------------------------- (a) LIVE vs PORT

def test_la_mine_explose_sur_l_ennemi_qui_l_ecrase_natif_vs_port(env_mine, rpc):
    """LE BRAS QUI CONFRONTE. Meme etat, meme pas : le natif applique l'explosion, le port aussi.

    Le TIRAGE ne peut pas coincider (le PRNG natif porte l'etat de toute la bataille, le port est
    reseede) -> on confronte ce qui est confrontable : la STRUCTURE (nombre de coups et profils) et
    l'ENCADREMENT (le total natif tombe entre le total du port force sur `RandomAmount.CalculateMin`
    et celui force sur `CalculateMax`). L'encadrement DISCRIMINE : avec le trou d'`AbilityState` du
    harnais (niveau 0), la fourchette du port valait ~[40, 60] pour un natif a ~4500."""
    rid, foe, dest = env_mine["rid"], env_mine["foe"], env_mine["mine_pos"]
    cap = _capture(rpc, rid)
    ob_avant = {u.get("squadId", u.get("entityId")): u.get("hp") for u in (cap["ob"]["units"] or [])}
    hp0 = ob_avant.get(foe)
    assert hp0, "PV de l'ennemi illisibles avant le pas -- montage non installe"

    res = _move(rpc, rid, foe, dest)
    evs = [td for td in _dmg_events(res) if td.get("Target_Id") == foe]
    natif = sum(int(td.get("Amount") or 0) for td in evs)
    profils_natifs = [int(td.get("DamageProfileType")) for td in evs]
    print("[natif] %d coup(s) profils=%s total=%d" % (len(evs), profils_natifs, natif))

    assert evs, ("le natif n'a inflige AUCUN degat au pas sur la mine : le montage n'exerce pas le "
                 "regime (mine absente ? allie ? deja explosee ?)")
    assert BLAST in profils_natifs, \
        "aucun coup `Blast` (%d) cote natif : profils=%s" % (BLAST, profils_natifs)

    # --- PORT : le MEME pas, sur l'etat capture AVANT.
    st = _state(cap)
    ent = st.get_entity(foe)
    assert ent is not None, "l'ennemi n'est pas dans l'etat offline -- capture partielle"
    mine = st.get_entity(env_mine["mine_id"])
    assert mine is not None, "la mine n'est pas dans l'etat offline -- capture partielle"
    traits = list(getattr(mine.get_component(StatsComponent).ctx, "traits", None) or [])
    assert has_trait(traits, UnitTrait.Steppable), \
        "l'entite ciblee n'est pas `Steppable` cote port : %s" % (traits,)

    def _port(mode):
        s = _state(cap)
        orig = F.RandomAmount.calculate
        if mode == "min":
            F.RandomAmount.calculate = lambda self, ctx: self.calculate_min(ctx)
        elif mode == "max":
            F.RandomAmount.calculate = lambda self, ctx: self.calculate_max(ctx)
        try:
            hc = s.get_entity(foe).get_component(HealthComponent)
            avant = int(hc.hp)
            Runner(s).install_default_handlers().apply(MoveUnitMessage(foe, dest))
            return avant - int(hc.hp), s
        finally:
            F.RandomAmount.calculate = orig

    port_min, _s1 = _port("min")
    port_max, s_max = _port("max")
    print("[port] fourchette [%d, %d] pour un natif a %d" % (port_min, port_max, natif))

    assert port_min > 0, ("le port n'inflige RIEN au crush : `HaywireMineSteppableAbility` n'est pas "
                          "inscrite, ou les evenements de mort du crush ne sont pas emis")
    assert port_min <= natif <= port_max, (
        "le degat natif (%d) est HORS de la fourchette du port [%d, %d] -- l'etage n'est pas le "
        "meme (niveau d'AbilityState ? profil ? nombre de coups ?)" % (natif, port_min, port_max))
    # ... et la mine est bien morte des DEUX cotes.
    assert s_max.get_entity(env_mine["mine_id"]).get_component(UnitComponent).alive is False, \
        "la mine n'a pas ete crushee cote port"


def test_la_raison_de_mort_du_crush_est_Steppable_live(env_mine, rpc):
    """`-r2` : `RecordDeathReason(..., DamageReason.Steppable)` sur un etat LIVE.

    C'est le canal que lit `HasDeathReasonTrigger$$IsMatchingDeathReason` -- sans lui, le trigger de
    la mine ne matcherait pas et le bras precedent serait vert pour la mauvaise raison."""
    rid, foe = env_mine["rid"], env_mine["foe"]
    cap = _capture(rpc, rid)
    st = _state(cap)
    mine_id = next((_uid(u) for u in _units(cap["dv"])
                    if MINE_VIS_FRAGMENT in (u.get("visualId") or "")), None)
    assert mine_id is not None and st.get_entity(mine_id) is not None, \
        "plus aucune mine VIVANTE sur le plateau -- ce bras n'a rien a mesurer"
    from engine.runner.operations.movement import _kill_steppable_units
    pc = st.get_entity(mine_id).get_component(PositionComponent)
    _kill_steppable_units(st, (pc.col, pc.row), foe)
    uc = st.get_entity(mine_id).get_component(UnitComponent)
    assert uc.death_source is not None, "aucune `DamageSource` gravee au crush (-r2 non porte)"
    killer, reason, abil = uc.death_source
    assert (killer, reason, abil) == (foe, int(DamageReason.Steppable), None), (
        "`death_source` = %s ; attendu (killer=%d, %d = DamageReason.Steppable, None)"
        % (uc.death_source, foe, int(DamageReason.Steppable)))


def test_la_mine_n_explose_pas_sous_un_allie_natif_vs_port(env_mine, rpc):
    """BRAS NEGATIF -- gate `AreEnemies(Owner, Actor)`. Une unite de l'equipe de Cyrus ecrase la
    mine SANS declencher l'explosion, des DEUX cotes.

    Mesure LIVE de reference (meme runner, mine `u103`, `ultraTitus`) : `0 event(s) de degat`,
    PV inchanges. Sans ce bras, le bras positif ne prouverait pas que le gate existe."""
    rid = env_mine["rid"]
    dv = _vue(rpc, rid)
    ami = _by_vis(dv, ALLY)
    assert ami is not None, "%s absent -- montage non installe" % ALLY
    ami_id = _uid(ami)
    dest = mine_id = None
    for _ in range(14):
        if not _assure_tour(rpc, rid, ami_id):
            break
        dest, mine_id, dv = _mine_a_portee(rpc, rid, ami_id)
        if dest is not None:
            break
        mines = _mines(dv)
        assert mines, "plus aucune mine sur le plateau -- le bras negatif ne peut pas etre joue"
        a = _by_vis(dv, ALLY)
        assert a is not None, "l'ALLIE a disparu -- montage instable"
        _step_one(rpc, rid, ami_id, _pos(a), sorted(mines)[0], avoid=mines)
        _endturn(rpc, rid)
    assert dest is not None, \
        "aucune mine atteignable par l'ALLIE -- le bras negatif ne peut pas etre joue"

    cap = _capture(rpc, rid)
    hp0 = {u.get("squadId", u.get("entityId")): u.get("hp") for u in (cap["ob"]["units"] or [])}
    res = _move(rpc, rid, ami_id, dest)
    evs = [td for td in _dmg_events(res) if td.get("Target_Id") == ami_id]
    assert not evs, "le natif a fait exploser la mine sous un ALLIE : %s" % (evs,)

    st = _state(cap)
    hc = st.get_entity(ami_id).get_component(HealthComponent)
    avant = int(hc.hp)
    Runner(st).install_default_handlers().apply(MoveUnitMessage(ami_id, dest))
    assert int(hc.hp) == avant, \
        "le PORT a fait exploser la mine sous un ALLIE (%d -> %d)" % (avant, hc.hp)
    assert st.get_entity(mine_id).get_component(UnitComponent).alive is False, \
        "la mine n'a pas ete crushee (le pas n'a pas eu lieu ?) -- le bras est vide"
    assert hp0.get(ami_id) is not None, "PV de l'allie illisibles -- capture partielle"


# --------------------------------------------------------------------------- (b) STRUCTURE

def test_le_crush_publie_les_quatre_evenements_de_mort():
    """`-r1` : `On(1)`, `On(2)`, `On(0)` et `On(0x36)` partent au crush.

    C'est l'INVERSE du bras `test_les_quatre_evenements_de_mort_restent_non_emis` de la tranche
    precedente, qui gardait le residu. `On(0x35 = PostUnitKill)` reste hors de la sequence de mort
    (publie par `after_move_triggers` sur le chemin MOVE) : ecart PREALABLE, nomme, non touche."""
    from engine.entities.effects import EffectFactory
    from engine.runner.operations import movement as MV
    from engine.runner.operations.triggers.dispatch import registry as REG
    et = PR._effect_type_libre()
    REG.EFFECT_TRIGGERS[et] = [PR._SondeEvents]
    try:
        st, mover, decoy = PR._mk_crush()
        st.effects.add_effect(mover, EffectFactory.create(
            {"name": "SondeEvents", "effectType": int(et), "remaining": 0}, 100, None, None))
        PR._SondeEvents.vus = []
        tues = MV._kill_steppable_units(st, (1, 1), mover)
        vus = sorted(set(PR._SondeEvents.vus))
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)
    assert tues == [decoy], "le crush n'a pas eu lieu (montage) : %s" % (tues,)
    attendus = sorted(e for e in PR.EVENTS_MORT if e != PR.EVENT_HORS_SEQUENCE)
    assert vus == attendus, (
        "la sequence de mort du crush publie %s ; attendu %s (les quatre evenements de "
        "`KillUnitOperation$$Execute` hors `On(0x35)`)" % (vus, attendus))


def test_le_crush_reveille_les_consommateurs_portes_par_le_mover():
    """BLAST RADIUS JOUE, avec TEMOIN. Deux voies « owner = le MOVER » que la fiche `-c-r3-r1` avait
    nommees comme atteignables des le premier decoy ecrase -- elles le sont desormais VRAIMENT."""
    for nom, fn in (("ActOfFaith_Accumulate", PR._fire_actofaith),
                    ("TheBetrayer_AddEffect", PR._fire_betrayer)):
        temoin, avec = fn(crush=False), fn(crush=True)
        assert temoin == 0, "%s fire SANS crush (%d) -- le montage ne discrimine rien" % (nom, temoin)
        assert avec > 0, ("%s ne fire PAS au crush : l'emission des evenements de mort n'atteint "
                          "pas ce consommateur" % nom)


def test_la_mine_haywire_choisit_sa_branche_sur_le_trait_Mechanical():
    """`-r3`, volet STRUCTURE : `If(HasTrait(Actor, 5 = Mechanical), atk1 + atk2, atk1)`.

    Montage SYNTHETIQUE assume (pas de board -> on appelle le trigger directement sur l'evenement
    `On(1)` du crush, apres avoir grave la `DamageSource` comme le fait
    `_kill_steppable_kill_unit`). Il garde ce que la mesure live montre : 1 attaque sur un ennemi
    ordinaire, 2 sur un MECANIQUE, aucune sur un ALLIE."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.haywire_mine import HaywireMineSteppableAbility

    def _joue(traits, ami):
        st, mine, stepper = PR._mk_mine_scene(traits, ami)
        st.rng = IntBasedMersenneTwister(777)
        st.get_entity(mine).get_component(UnitComponent).alive = False
        AttackDamageOperation._record_death_reason(
            st, mine, stepper, None, damage_reason=int(DamageReason.Steppable))
        ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), stepper, mine, ranged=False,
                          profile=None, killer_id=stepper, dying_id=mine)
        trig = HaywireMineSteppableAbility(mine)
        if not trig.matches(st, ev):
            return None
        return trig.execute_behaviour(st, ev)

    ordinaire = _joue(["Hero"], False)
    mecanique = _joue(["Hero", UnitTrait.Mechanical.name], False)
    allie = _joue(["Hero", UnitTrait.Mechanical.name], True)

    assert allie is None, "la mine explose sous un ALLIE : le gate `AreEnemies` ne mord pas"
    assert ordinaire is not None and len(ordinaire["hits"]) == 1, \
        "ennemi NON-mecanique : %s attaque(s), attendu 1 (branche `else`)" % (
            None if ordinaire is None else len(ordinaire["hits"]))
    assert mecanique is not None and len(mecanique["hits"]) == 2, \
        "ennemi MECANIQUE : %s attaque(s), attendu 2 (`atk1 + atk2`)" % (
            None if mecanique is None else len(mecanique["hits"]))
    assert mecanique["total"] > ordinaire["total"], (
        "le volet anti-mecanique n'ajoute rien (%s vs %s)"
        % (mecanique["total"], ordinaire["total"]))


def test_le_seed_de_l_ability_state_d_un_summon_vient_d_unitAbilityStates(env_mine, rpc):
    """LE TROU DE HARNAIS QUE CETTE TRANCHE A DU BOUCHER, garde explicitement.

    Une unite INVOQUEE n'a pas de `UnitConfiguration` : `combatSnapshot.unitConfig` rend
    `{"error": "config null"}`. Sans le seed depuis `unitAbilityStates`, `passive_ability_level`
    vaut 0 et TOUTE variable per-niveau d'un passif de summon est lue a l'index 0."""
    cap = _capture(rpc, env_mine["rid"])
    mine_id = next((_uid(u) for u in _units(cap["dv"])
                    if MINE_VIS_FRAGMENT in (u.get("visualId") or "")), None)
    assert mine_id is not None, "plus aucune mine VIVANTE -- ce bras n'a rien a mesurer"
    brut = next((u for u in (cap["snap"].get("units") or [])
                 if u.get("entityId") == mine_id), None)
    assert brut is not None, "la mine est absente du combatSnapshot -- capture partielle"
    assert (brut.get("unitConfig") or {}).get("error"), (
        "le summon a desormais une `unitConfig` : la cause de ce seed a disparu, RE-MESURER "
        "(le seed reste correct, mais son motif n'est plus celui-ci) -- %s" % (brut.get("unitConfig"),))
    st = _state(cap)
    ctx = st.get_entity(mine_id).get_component(StatsComponent).ctx
    assert int(getattr(ctx, "passive_ability_level", 0) or 0) >= 1, (
        "`passive_ability_level` de la mine = %s : le seed depuis `unitAbilityStates` n'a pas eu "
        "lieu, les variables per-niveau seront lues a l'index 0"
        % getattr(ctx, "passive_ability_level", None))
    assert "HaywireMineSteppable" in (getattr(ctx, "passive_abilities", None) or []), \
        "le passif de la mine n'est pas seede : %s" % (getattr(ctx, "passive_abilities", None),)
