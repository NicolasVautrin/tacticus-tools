"""N5 -- la chaine `&` derriere un `AddEffect` qui n'ABOUTIT PAS (refus, no-op, cible nulle) NE TOMBE PAS.

CRITERE : quand `IdunBattle.Operations.AddEffectOperation$$Execute` abandonne (gate
`EntityIsImmuneToEffect`, cf. case-224), la SUITE de la chaine `op_BitwiseAnd` s'execute-t-elle ?

⚠ MONTAGE CORRIGE (#208) : le couple `Pinned` x `TerminatorArmour` utilise ici comme exemple de
« refus » n'en est PAS un -- l'effet est POSE puis rendu INERTE par sa `CreateActiveCondition`
(mesure `probe_208_pinned_inactive.py` : `decisionView includeInactive` publie 1065, `active=False`).
Cela ne change RIEN a la conclusion sur la chaine (`AddEffectBehaviour$$Execute` jette la valeur de
retour de l'operation dans TOUS les cas), mais le verrou structurel exerce desormais un VRAI refus
(trait `Immune` accorde sur l'etat charge), et l'axe `Pinned` des tests live se lit sur le canal
ACTIF des deux cotes.

REPONSE (decompile + live) : OUI. Deux artefacts natifs l'etablissent, et rien ne les contredit :

  * `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` ZERO-INITIALISE son `OperationResult`
    de retour (`*param_1 = 0 ... param_1[7] = 0`) et NE LE REECRIT JAMAIS : la valeur de retour de
    l'operation (`longlong` = l'entite-effet, 0 sur chaque gate) est appelee via le slot 0x10 du
    processeur et JETEE. Contraste avec une feuille qui, elle, PROPAGE :
    `IdunBattle.Entities.Behaviours.DiscardHitBehaviour$$Execute` recopie les 8 slots du resultat de
    son operation dans son propre retour.
  * `IdunBattle.DSL.CombinedBehaviour$$Execute` ne court-circuite que sur `*(char *)(param_1 + 4)`
    (= le byte @+0x20 du resultat, OU-propage par `IdunBattle.Core.OperationResult$$Combine`). Un
    resultat toujours-nul ne peut donc JAMAIS interrompre le `&`.

Le port est conforme par construction (`Seq` teste `r.stop` ; `AddEffect` rend `OperationResult.ok()`).
Ces tests VERROUILLENT cette conformite -- le piege est symetrique : poser `stop` des que
`eff is None` tuerait des chaines que le natif poursuit (et `eff is None` couvre AUSSI la voie
« effet DEJA PRESENT », qui n'est meme pas un refus : `UpdateExistingEffect` a fait son refresh).

MESURE LIVE (`probe_n5_chain_after_refused_addeffect.py`, runner MC1_67 seed 112112, camp joueur
DEPLOYE au contact de la victime) -- `ExemplarOfHate` (1140, darkaAsmodai) sur `blackAbaddon`
(trait `TerminatorArmour`) :

    groupes : ExemplarOfHate_Target | TemporaryStatOverride | Loki_NormalAttack | 6x degat
              | TerminatorArmour_ReduceDmg | TemporaryStatOverride (retrait)
    Pinned  : ABSENT          hp cible : 10038 -> 7442

soit `Pinned` refuse ET la suite du `&` (override d'Attack -> attaque libre -> retrait) EXECUTEE.
C'est ce qui LEVE le confond de case-224 §5.2 : la branche y paraissait entierement absente parce
qu'AUCUN attaquant DarkAngels n'etait a portee -- sans attaquant elu, les trois feuilles qui suivent
le `Pinned` sont vides de toute facon, et « chaine tombee » etait indiscernable de « personne pour
attaquer ». Ici le caster est AU CONTACT (d=1), donc candidat garanti.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_112_darkangels as PR
import probe_n5_chain_after_refused_addeffect as N5
from engine.dsl.effects import ExecutionContext
from engine.entities.behaviours import Emit, Seq
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.selectors import Target
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.darkangels import ExemplarOfHateAbility
from engine.runner.components import HealthComponent, unit_state_for_effects
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

EXEMPLAR = 1140
PINNED = int(EffectType.Pinned)                     # 1065
STUNNED = int(EffectType.Stunned)                   # 1162
IMMUNE_VICTIM, CONTROL_VICTIM = N5.IMMUNE_VICTIM, N5.CONTROL_VICTIM


# ------------------------------------------------------------------ helpers

def _snapshot(sid, rid):
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, dv, ob, cs


def _seeded_state(sid, rid, board, dv, ob, cs):
    """Etat port CALE SUR LE RNG DU RUNNER : sans ca `UseActiveAbility` se degrade en no-op
    (`state.rng is None` -> `AttackDamageOperation` non appele) et l'on ne pourrait PAS distinguer
    « chaine tombee » de « attaque non resolvable offline » -- exactement la confusion a eviter ici."""
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng, dict) and rng.get("mt")):
        pytest.skip("dumpRng KO")
    st = load_state(dv, ob, cs, board=board)
    r = IntBasedMersenneTwister()
    r.mt = list(rng["mt"])
    r.mti = rng["mti"]
    st.rng = r
    return st


def _port_hp(state, uid):
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


def _port_active(state, uid) -> set:
    """EffectTypes ACTIFS (flag `EffectComponent.IsActive` + `CreateActiveCondition`) -- le pendant
    EXACT du canal live qui emet un groupe d'evenement / que publie `decisionView` par defaut."""
    if state.effects is None:
        return set()
    return {e.effect_type
            for e in state.effects.active_effects(int(uid), unit_state_for_effects(state, int(uid)))}


def _group_sources(action) -> list:
    return [e.get("source") for e in (action.get("events") or []) if e.get("kind") == "group"]


@pytest.fixture(scope="module")
def enemy_layout(live_session):
    """Positions REELLES du camp adverse (build de reconnaissance jetable) -- elles servent d'ancre de
    deploiement pour les runners de mesure : on CHOISIT les positions au lieu de les subir."""
    sid = live_session
    return N5.enemy_layout(sid)


def _run(sid, layout, victim_visual):
    """Cast `ExemplarOfHate` sur `victim_visual` depuis un caster DEPLOYE AU CONTACT, cote LIVE et cote
    PORT sur le MEME etat. Rend (live, port) sous forme de dicts comparables."""
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=layout[victim_visual],
                    occupied=layout.values())
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        if "darkaAsmodai" not in bv or victim_visual not in bv:
            pytest.skip("roster incomplet: %s" % sorted(bv))
        caster, tgt = bv["darkaAsmodai"]["id"], bv[victim_visual]["id"]
        import hexgeo
        pos = PR.positions(dv)
        if hexgeo.distance(pos[caster], pos[tgt]) > 1:
            pytest.skip("caster non adjacent -> confond d'election d'attaquant non leve")
        if tgt not in PR.legal_from_here(sid, rid, caster, EXEMPLAR):
            pytest.skip("cible %s non legale depuis la position courante" % victim_visual)

        st = _seeded_state(sid, rid, board, dv, ob, cs)
        php0 = _port_hp(st, tgt)
        port = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
        php1 = _port_hp(st, tgt)
        hp0 = PR.hp_of(sid, rid)
        res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
        assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
        hp1 = PR.hp_of(sid, rid)
        srcs = _group_sources(res)
        live = {"pinned": "Pinned" in srcs,
                "override": "TemporaryStatOverride" in srcs,
                "attack": any(s and "NormalAttack" in s for s in srcs),
                "damaged": (hp0.get(tgt) or (0,))[0] != (hp1.get(tgt) or (0,))[0]}
        # AXE `pinned` = « l'effet CONTRIBUE-t-il ? », pas « a-t-il ete pose ? ». Cote LIVE c'est
        # l'emission d'un groupe `Pinned` (un effet INACTIF n'applique rien, donc n'emet rien) ; le
        # pendant EXACT cote port est `active_effects`, PAS la liste des poses (#208 : sur une cible
        # `TerminatorArmour` le natif POSE l'effet et le laisse inerte -- mesure probe_208).
        port_v = {"pinned": PINNED in _port_active(st, tgt),
                  "placed": PINNED in (port.get("effects") or []),
                  "override": port.get("attack_override") is not None,
                  "attack": port.get("attack") is not None,
                  "damaged": php0 != php1}
        print("\n[%s] live=%s port=%s" % (victim_visual, live, port_v))
        return live, port_v
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------- (1) le CRITERE, live + port

def test_chain_survives_inert_addeffect(live_session, enemy_layout):
    """Cible `TerminatorArmour` : `AddEffect(Pinned)` ne CONTRIBUE PAS, et la suite du `&` (override
    d'Attack -> attaque libre -> retrait) S'EXECUTE QUAND MEME -- live ET port.

    C'est l'assertion qui DISTINGUE « la chaine tombe » de « l'effet ne contribue pas » : sans le volet
    `attack`/`damaged`, le test ne testerait que l'etage effet.

    ⚠ #208 : ici l'`AddEffect` n'est PAS refuse -- il ABOUTIT, et c'est sa `CreateActiveCondition`
    (`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, TerminatorArmour))`) qui le rend
    inerte (mesure `probe_208_pinned_inactive.py` : `decisionView includeInactive` publie 1065 avec
    `active=False`). Pour la CHAINE cela ne change rien -- `AddEffectBehaviour$$Execute` jette de
    toute facon la valeur de retour de l'operation -- mais le port doit desormais rendre `placed=True`
    ET `actif=False`, ce que les deux assertions ci-dessous verrouillent separement. Le VRAI refus
    d'immunite est exerce par le verrou structurel plus bas."""
    live, port = _run(live_session, enemy_layout, IMMUNE_VICTIM)
    assert live["pinned"] is False, "LIVE: Pinned CONTRIBUE sur une cible TerminatorArmour"
    assert live["attack"] and live["damaged"], \
        "LIVE: la chaine est TOMBEE derriere l'AddEffect inerte (%s)" % live
    assert live["override"], "LIVE: pas d'AddStatOverrideEffect -> chaine interrompue avant l'attaque"
    assert port["placed"] is True, "PORT: la pose a ete abandonnee (gate d'immunite fantome, #208)"
    assert port["pinned"] is False, "PORT: Pinned ACTIF sur une cible TerminatorArmour"
    assert port["attack"] and port["override"], \
        "PORT: la chaine est TOMBEE derriere l'AddEffect inerte (%s)" % port


# ------------------------------------------------------- (2) cas NOMINAL (AddEffect qui aboutit)

def test_chain_survives_placed_addeffect(live_session, enemy_layout):
    """CONTRE-CAS : meme ability, cible Chaos SANS le trait -> `Pinned` EST pose et la chaine continue.
    Garde du cas nominal : prouve que le verrou n'a pas casse le chemin ou l'effet aboutit."""
    live, port = _run(live_session, enemy_layout, CONTROL_VICTIM)
    assert live["pinned"] is True, "LIVE: Pinned refuse sur une cible sans TerminatorArmour"
    assert live["attack"] and live["damaged"], "LIVE: chaine interrompue sur le cas nominal (%s)" % live
    assert port["pinned"] is True, "PORT: Pinned refuse sur une cible sans TerminatorArmour"
    assert port["attack"] and port["override"], "PORT: chaine interrompue sur le cas nominal (%s)" % port


# ------------------------------------------------------- (2bis) GENERALISATION : l'attaquant n'est pas le caster

def test_chain_survives_refused_addeffect_with_ally_attacker(live_session, enemy_layout):
    """MEME critere, porteur d'attaque DIFFERENT : le caster est ECARTE (d=2, arme melee) et
    l'attaquant elu par `ExemplarOfHateAbility$$GetAttacker` est l'ALLIE RANGED `darkaHellblaster`
    (portee 3). La chaine doit tenir sur CET allie, sur une cible dont le `Pinned` reste inerte."""
    import hexgeo
    sid = live_session
    anchor = enemy_layout[IMMUNE_VICTIM]
    blocked = set(enemy_layout.values()) | set(hexgeo.ring(anchor[0], anchor[1], 1))
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=anchor, occupied=blocked)
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        if "darkaHellblaster" not in bv or IMMUNE_VICTIM not in bv:
            pytest.skip("roster incomplet: %s" % sorted(bv))
        caster, ally = bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"]
        tgt = bv[IMMUNE_VICTIM]["id"]
        pos = PR.positions(dv)
        if hexgeo.distance(pos[caster], pos[tgt]) < 2:
            pytest.skip("caster non ecarte -> ce n'est pas le montage allie")
        if tgt not in PR.legal_from_here(sid, rid, caster, EXEMPLAR):
            pytest.skip("cible non legale depuis la position courante")

        st = _seeded_state(sid, rid, board, dv, ob, cs)
        port = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
        res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
        assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
        srcs = _group_sources(res)
        print("\n[ally] port attacker=%s (caster=%s ally=%s) live=%s" % (
            port.get("attacker"), caster, ally, srcs))
        assert "Pinned" not in srcs, "LIVE: Pinned CONTRIBUE sur une cible TerminatorArmour"
        assert "TemporaryStatOverride" in srcs and any(s and "NormalAttack" in s for s in srcs), \
            "LIVE: chaine tombee alors que l'attaquant elu est un ALLIE (%s)" % srcs
        assert port.get("attacker") == ally, \
            "PORT: attaquant elu %s, attendu l'allie %s" % (port.get("attacker"), ally)
        assert port.get("attack_override") is not None, "PORT: chaine tombee avant l'override"
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------- (3) verrou STRUCTUREL du combinateur (offline)

def _chain_probe(state, caster, target, effect_type, name):
    """`Seq(AddEffect(...), Emit(sonde))` = la plus petite chaine `op_BitwiseAnd` possible. Rend
    `(placed, sonde_executee)` -- deux axes INDEPENDANTS, c'est tout l'objet du test."""
    ectx = ExecutionContext(state=state, rng=None)
    tree = Seq(AddEffect(effect_type, name, Target()),
               Emit("SondeChaine", lambda _e, _c: {}))
    tree.execute(entities_from_state(state, caster, target), ectx)
    placed = next((p.get("placed") for n, p in ectx.emitted if n == "AddEffect"), None)
    return placed, any(n == "SondeChaine" for n, _p in ectx.emitted)


def test_seq_does_not_short_circuit_on_any_addeffect_outcome(live_session, enemy_layout):
    """VERROU STRUCTUREL, purement offline (aucun cast live) : la sonde placee DERRIERE l'`AddEffect`
    s'execute dans les TROIS issues de `AddEffectOperation` qui rendent `None` cote port --

      * REFUS d'immunite     (`Pinned` sur une cible portant le trait `Immune`) ;
      * effet DEJA PRESENT   (2e pose du meme type -- `UpdateExistingEffect` cote natif : ce n'est
                              PAS un refus, il incremente `TimesApplied`) ;
      * cible NULLE          (selecteur sans cible -> aucune iteration).

    C'est ce test qui tombe ROUGE si quelqu'un pose `stop` sur `eff is None` (le fork symetrique).
    `Stunned` sert de temoin d'une pose qui ABOUTIT."""
    sid = live_session
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=enemy_layout[IMMUNE_VICTIM],
                    occupied=enemy_layout.values())
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        if IMMUNE_VICTIM not in bv or CONTROL_VICTIM not in bv:
            pytest.skip("roster incomplet: %s" % sorted(bv))
        st = load_state(dv, ob, cs, board=board)
        caster = bv["darkaAsmodai"]["id"]
        immune, control = bv[IMMUNE_VICTIM]["id"], bv[CONTROL_VICTIM]["id"]

        # CRAFT du refus d'immunite REEL -- `BaseEffect$$EntityIsImmuneToEffect` =
        # `HasTrait(entity, 0x19 = Immune) && this.CanBeImmuneTo`, et `PinnedEffect.CanBeImmuneTo`
        # est vrai. AUCUNE unite du roster spawnable ne porte `Immune` (inventaire case-224 §1.3), or
        # le natif PEUT l'accorder en bataille (`AddTraitOperation` ecrit la collection
        # `BaseUnitComponent+0x48`) : on l'accorde donc ICI, sur l'etat charge, pour exercer le gate
        # lui-meme. ⚠ #208 : le trait `TerminatorArmour` NE convient PAS pour ce role -- il ne refuse
        # RIEN, il DESACTIVE (mesure `probe_208_pinned_inactive.py`).
        from engine.runner.components import StatsComponent
        _sc = st.get_entity(immune).get_component(StatsComponent)
        _sc.ctx.traits = list(_sc.ctx.traits or []) + ["Immune"]

        placed, probed = _chain_probe(st, caster, immune, PINNED, "Pinned")
        assert placed is False, "le gate d'immunite ne mord plus (HasTrait(Immune) && CanBeImmuneTo)"
        assert probed, "REFUS D'IMMUNITE: la chaine `&` a ete court-circuitee"

        placed, probed = _chain_probe(st, caster, control, STUNNED, "Stunned")
        assert placed is True and probed, "POSE ABOUTIE: chaine cassee (%s)" % placed

        placed, probed = _chain_probe(st, caster, control, STUNNED, "Stunned")
        assert placed is False, "2e pose du meme type: attendu no-op (refresh natif)"
        assert probed, "DEJA PRESENT: la chaine `&` a ete court-circuitee (ce n'est meme pas un refus)"

        ectx = ExecutionContext(state=st, rng=None)
        Seq(AddEffect(PINNED, "Pinned", Target()),
            Emit("SondeChaine", lambda _e, _c: {})).execute(
                entities_from_state(st, caster, None), ectx)
        assert not any(n == "AddEffect" for n, _p in ectx.emitted), "cible nulle: pose emise"
        assert any(n == "SondeChaine" for n, _p in ectx.emitted), \
            "CIBLE NULLE: la chaine `&` a ete court-circuitee"
    finally:
        PR.dispose(sid, rid)
