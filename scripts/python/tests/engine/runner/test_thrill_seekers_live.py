"""Trait `ThrillSeekers` (1056, x5 Emperor's Children) -> ability triggered 1444 -> effet
« Thrilled » 1434 : replay-diff LIVE vs moteur, sur les DEUX branches + le refresh + le contre-cas.

RE (decompile ghidra, build gqfc5mff6c) — cf. `engine/runner/operations/triggers/loki/thrill_seekers.py` :
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateTrigger` =
      ( On(PreAttackHit=6) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target)) )
      | ( On(DamageTaken=0xf) & OwnerIsTarget )
  `...$$CreateBehaviour` = If(Not(HasFlag(Owner, Dead=6)),
                              If(HasEffect(Owner, 1434),
                                 ChangeEffectTurns(Owner, 1434, TurnsFromRounds(nrOfRounds), Set),
                                 AddStaticStatModifierEffect(Owner, 1434, CritChance=9,
                                                             extraCritChance, TurnsFromRounds(...))))
  gameconfig : `thrillSeekersNrOfRounds`=1, `thrillSeekersExtraCritChance`=15.

Quatre invariants confrontes LIVE puis REJOUES offline (bit-exact) :
  1. ATTAQUE D'UNE CIBLE A PLEINE VIE -> le porteur gagne `Thrilled` (1434) et +extraCritChance de
     Crit Chance, duree `TurnsFromRounds(1)` = 2 tours en duel.
  2. CONTRE-CAS `Not(IsWounded)` : la MEME attaque sur une cible DEJA BLESSEE ne pose RIEN (c'est
     LE discriminant du predicat -- sans lui le port poserait l'effet dans les deux cas).
  3. DEGAT SUBI (`On(DamageTaken)` & OwnerIsTarget) -> meme pose, sur la VICTIME cette fois.
  4. REFRESH : re-declencher alors que l'effet est DEJA porte n'EMPILE PAS le stat-mod (la crit
     chance reste a +extraCritChance, pas x2) et remet la duree a `TurnsFromRounds(1)` --
     branche `ChangeEffectTurns(Set)` du `If(HasEffect, ...)`.
  5. EXPIRATION : le stat-mod SORT quand le timer tombe (mirror
     `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`).
  6. EXPIRATION D'UN STACK **SEEDE** (#118) : meme invariant, mais l'etat offline est charge
     APRES la pose (l'effet est DEJA actif, son +15 DEJA CUIT dans `combatSnapshot.stats`). Le
     natif garde la contribution dans une `ValueModification` keyee par l'ENTITE-EFFET et la
     retire au retrait ; le port doit donc l'attribuer AU SEED pour pouvoir la retirer.

FIXTURES : `emperNoiseMarine` (Shiron, ranged r3) + `emperKakophonist` (Adamatar, melee), les DEUX
porteurs spawnables du rank courant, contre des ennemis NON-Necron (`orksNob`/`astraBullgryn` -- un
Necron regenere via `LivingMetal` et peut revenir a PLEINE VIE entre deux mesures, ce qui casserait
le contre-cas) avec `--hp-target 60000` : les cibles ENCAISSENT sans mourir, donc l'etat « blesse »
est STABLE et la bataille dure. Positions DRIVEES (`applyAction move` sur les DEUX camps) -- rien
n'est laisse au spawn. Chaque test a SA bataille (fixture function-scope) : aucun couplage d'ordre.
"""
from __future__ import annotations

import pytest

from engine.entities.stats import StatType
from engine.entities.pathfinding.board import Board
from engine.runner.components import StatsComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

SHIRON_VIS = "emperNoiseMarine"     # ThrillSeekers + HeavyWeapon + SuppressiveFire, ranged r3
ADAMATAR_VIS = "emperKakophonist"   # ThrillSeekers, melee (2e porteur spawnable du rank courant)
ENEMY_A = "orksNob"                 # non-Necron (pas de regen LivingMetal), melee
ENEMY_B = "astraBullgryn"           # non-Necron, melee, encaisse (BigTarget)
THRILLED = 1434                     # EffectType.ThrillSeekers
EXTRA_CC = 15                       # traits.ThrillSeekers.variables.thrillSeekersExtraCritChance
TURNS = 2                           # TurnsFromRounds(thrillSeekersNrOfRounds=1) en duel (2 joueurs)
# `--hp-target` ET `--hp-player` : les DEUX camps encaissent sans mourir. Cote joueur c'est
# INDISPENSABLE au scenario REFRESH -- le porteur doit survivre a DEUX coups dans le meme tour
# adverse (avec ses 8533 PV de base, le 2e coup le tuait et l'effet disparaissait avec lui).
BUILD = ["--roster", "2", "--p-units", f"{SHIRON_VIS},{ADAMATAR_VIS}",
         "--a-units", f"{ENEMY_A},{ENEMY_B}",
         "--hp-target", "60000", "--hp-player", "60000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _cc(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            return (u.get("stats") or {}).get("critChance")
    return None


def _hp(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            return (u.get("stats") or {}).get("health")
    return None


def _eff(dec, uid, effect_type=THRILLED):
    """(present, remaining) de l'effet `effect_type` sur `uid` dans un decisionView."""
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            for e in (u.get("effects") or []):
                if e.get("effectType") == effect_type:
                    return True, e.get("remaining")
    return False, None


def _normal_ability(dec, uid):
    """Id de l'attaque NORMALE de `uid` (ActiveAbilityType PAR UNITE -- jamais 69 en dur)."""
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal":
                    return a.get("id")
    return None


class _Harness:
    """Wrapper mince sur `rpc` : vue, deplacement, attaque + capture avant/apres pour le replay."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board

    def dec(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def snap(self):
        return self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)

    def move(self, uid, col, row):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 60)

    def endturn(self):
        return self.rpc("applyAction",
                        {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)

    def owner_of(self, uid):
        for u in (self.dec().get("units") or []):
            if u.get("id") == uid:
                return u.get("owner")
        return None

    def give_turn_to(self, uid, max_end=4):
        """Fait tourner les fins de tour jusqu'a ce que le camp de `uid` soit actif."""
        want = self.owner_of(uid)
        for _ in range(max_end):
            if self.dec().get("currentPlayer") == want:
                return True
            self.endturn()
        return self.dec().get("currentPlayer") == want

    def attack(self, att, tgt):
        """Attaque NORMALE `att`->`tgt`. Renvoie la capture (etat AVANT + RNG cale pour le replay
        offline ; stats/effets AVANT et APRES pour la confrontation live)."""
        dec_b = self.dec()
        ab = _normal_ability(dec_b, att)
        assert ab is not None, f"pas d'attaque normale resolue pour u{att}"
        cap = {"dec_b": dec_b, "ob_b": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
               "snap_b": self.snap(), "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30),
               "att": att, "tgt": tgt}
        r = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": ab}}, 90)
        assert _ok(r), f"attaque u{att}->u{tgt} refusee: {str(r)[:200]}"
        cap["dec_a"], cap["snap_a"] = self.dec(), self.snap()
        dealt = (_hp(cap["snap_b"], tgt) or 0) - (_hp(cap["snap_a"], tgt) or 0)
        assert dealt > 0, (f"u{att}->u{tgt} n'a inflige AUCUN degat ({dealt}) -- le vecteur "
                           f"DamageTaken ne peut pas fire, scenario non arme")
        cap["dealt"] = dealt
        # PASSAGE DE TOUR AUTOMATIQUE : quand l'attaquant etait la DERNIERE unite activable de son
        # camp, le runner cloture le tour tout seul -> un `EndTurn` (donc un TICK de duree) tombe
        # ENTRE l'action et notre lecture. La duree lue vaut alors `TurnsFromRounds(n) - 1`. On le
        # DETECTE (le joueur courant a change) au lieu de le subir : le replay offline, lui, ne
        # tique pas -- d'ou l'ecart systematique de 1 si on ne corrige pas.
        cap["turn_ticked"] = (cap["dec_b"].get("currentPlayer")
                              != cap["dec_a"].get("currentPlayer"))
        return cap

    def replay(self, cap):
        """Rejoue OFFLINE l'attaque capturee et renvoie le `State` resultant."""
        state = load_state(cap["dec_b"], cap["ob_b"], cap["snap_b"], board=self.board)
        state.rng = _seed_rng(cap["rng"])
        Runner(state).install_default_handlers(20).apply(
            AttackUnitMessage(cap["att"], cap["tgt"]))
        return state


def _ctx(state, uid):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return sc.ctx if sc is not None else None


def _off_eff(state, uid, effect_type=THRILLED):
    for e in state.effects.by_unit.get(uid, []):
        if e.effect_type == effect_type and not e.consumed:
            return True, e.remaining_turns
    return False, None


def _battle(rpc, build_runner, seed, board="MC1_67"):
    """Bataille neuve + ids resolus. Chaque test la reconstruit -> aucun couplage d'ordre.
    `board` est une VARIABLE EXPERIMENTALE (geometrie/spawns) : le cas SEEDE (#118) est rejoue
    sur deux couples (board, seed, porteur) distincts pour ne pas conclure d'un seul plateau."""
    rid = build_runner(seed, extra=BUILD, board=board)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo"
    h = _Harness(rpc, rid, Board(bg["tiles"], adjacency="evenq"))
    ids = {}
    for u in (h.dec().get("units") or []):
        for key, vis in (("shiron", SHIRON_VIS), ("adamatar", ADAMATAR_VIS),
                         ("foeA", ENEMY_A), ("foeB", ENEMY_B)):
            if u.get("visualId") == vis:
                ids[key] = u["id"]
    assert {"shiron", "adamatar", "foeA", "foeB"} <= set(ids), f"unites absentes: {ids}"
    return h, ids


def test_thrill_seekers_full_health_target_and_wounded_counter_case(rpc, build_runner):
    """(1) attaque d'une cible PLEINE VIE -> `Thrilled` +15 cc, duree 2 tours ; le moteur reproduit.
    (2) CONTRE-CAS : la meme cible, DESORMAIS BLESSEE, ne pose RIEN (`Not(IsWounded(target))`)."""
    h, ids = _battle(rpc, build_runner, "5150")
    ada, shi, foe = ids["adamatar"], ids["shiron"], ids["foeB"]
    h.move(foe, 3, 3)          # cible au centre
    h.move(ada, 2, 3)          # Adamatar AU CONTACT (melee)
    h.move(shi, 1, 2)          # Shiron a 2 hex (portee 3)

    # --- (1) cible a PLEINE VIE -------------------------------------------------------------
    assert not _eff(h.dec(), ada)[0], "Thrilled deja porte avant la 1re attaque"
    cap1 = h.attack(ada, foe)
    cc_b, cc_a = _cc(cap1["snap_b"], ada), _cc(cap1["snap_a"], ada)
    present, rem = _eff(cap1["dec_a"], ada)
    print(f"\n[TS/full-hp] Adamatar cc {cc_b} -> {cc_a} | Thrilled present={present} rem={rem}")
    assert present, "LIVE: aucun Thrilled apres une attaque sur cible pleine vie"
    assert cc_a == cc_b + EXTRA_CC, f"LIVE: cc {cc_b} -> {cc_a}, attendu +{EXTRA_CC}"
    exp_rem = TURNS - (1 if cap1["turn_ticked"] else 0)     # cf. `_Harness.attack` (tick auto)
    assert rem == exp_rem, f"LIVE: duree {rem}, attendu TurnsFromRounds(1) = {exp_rem}"

    st1 = h.replay(cap1)
    off_present, off_rem = _off_eff(st1, ada)
    off_cc = _ctx(st1, ada).stat(StatType.CRIT_CHANCE)
    print(f"[TS/full-hp] MOTEUR cc={off_cc} present={off_present} rem={off_rem}")
    assert off_present, "MOTEUR: Thrilled non pose sur cible pleine vie"
    assert off_cc == cc_a, f"MOTEUR cc {off_cc} != live {cc_a}"
    # Le replay offline ne rejoue PAS le passage de tour automatique -> il porte la duree BRUTE.
    assert off_rem == TURNS, f"MOTEUR duree {off_rem} != TurnsFromRounds(1) = {TURNS}"

    # --- (2) CONTRE-CAS : Shiron frappe la MEME cible, maintenant BLESSEE --------------------
    hp_full = _hp(cap1["snap_b"], foe)
    hp_now = _hp(cap1["snap_a"], foe)
    assert hp_now < hp_full, f"cible non blessee (hp {hp_full} -> {hp_now}) -- contre-cas non arme"
    cap2 = h.attack(shi, foe)
    cc2_b, cc2_a = _cc(cap2["snap_b"], shi), _cc(cap2["snap_a"], shi)
    present2, _ = _eff(cap2["dec_a"], shi)
    print(f"[TS/wounded] Shiron cc {cc2_b} -> {cc2_a} | Thrilled present={present2} "
          f"(cible hp {hp_now}/{hp_full})")
    assert not present2, "LIVE: Thrilled pose alors que la cible etait BLESSEE (Not(IsWounded) muet)"
    assert cc2_a == cc2_b, f"LIVE: cc modifiee ({cc2_b} -> {cc2_a}) sur cible blessee"

    st2 = h.replay(cap2)
    assert not _off_eff(st2, shi)[0], "MOTEUR: Thrilled pose sur cible BLESSEE (contre-cas rate)"
    assert _ctx(st2, shi).stat(StatType.CRIT_CHANCE) == cc2_a, "MOTEUR: cc != live sur cible blessee"


def test_thrill_seekers_damage_taken_then_refresh(rpc, build_runner):
    """(3) `On(DamageTaken) & OwnerIsTarget` : le porteur qui ENCAISSE gagne `Thrilled`.
    (4) REFRESH : un SECOND coup encaisse dans le MEME tour adverse n'empile PAS le stat-mod
        (branche `ChangeEffectTurns(Set)`) et remet la duree a `TurnsFromRounds(1)`.

    Les DEUX ennemis sont amenes AU CONTACT de Shiron -> les deux coups tombent dans le meme
    tour adverse, donc l'effet est encore ACTIF au 2e (sinon il aurait expire entre deux tours)."""
    h, ids = _battle(rpc, build_runner, "606")
    shi, foe1, foe2 = ids["shiron"], ids["foeA"], ids["foeB"]
    h.move(shi, 2, 3)                 # Shiron au centre
    h.move(foe1, 3, 3)                # les deux ennemis melee AU CONTACT
    h.move(foe2, 2, 4)
    assert h.give_turn_to(foe1), "impossible de donner la main au camp adverse"
    assert not _eff(h.dec(), shi)[0], "Thrilled deja porte avant le 1er coup encaisse"

    # --- (3) 1er coup encaisse ---------------------------------------------------------------
    cap3 = h.attack(foe1, shi)
    cc_b, cc_a = _cc(cap3["snap_b"], shi), _cc(cap3["snap_a"], shi)
    present, rem = _eff(cap3["dec_a"], shi)
    print(f"\n[TS/damage-taken] Shiron cc {cc_b} -> {cc_a} (degat {cap3['dealt']}) | "
          f"Thrilled present={present} rem={rem}")
    assert present, "LIVE: aucun Thrilled apres un degat SUBI par le porteur"
    assert cc_a == cc_b + EXTRA_CC, f"LIVE: cc {cc_b} -> {cc_a}, attendu +{EXTRA_CC}"

    st3 = h.replay(cap3)
    off_present, off_rem = _off_eff(st3, shi)
    off_cc = _ctx(st3, shi).stat(StatType.CRIT_CHANCE)
    print(f"[TS/damage-taken] MOTEUR cc={off_cc} present={off_present} rem={off_rem}")
    assert off_present, "MOTEUR: Thrilled non pose sur degat subi"
    assert off_cc == cc_a, f"MOTEUR cc {off_cc} != live {cc_a}"
    assert off_rem == TURNS, f"MOTEUR duree {off_rem} != TurnsFromRounds(1) = {TURNS}"

    # --- (4) 2e coup encaisse, MEME tour -> REFRESH (pas d'empilement) -----------------------
    present_now, rem_now = _eff(h.dec(), shi)
    assert present_now, "Thrilled disparu entre les deux coups -- refresh non armable"
    cap4 = h.attack(foe2, shi)
    cc4_b, cc4_a = _cc(cap4["snap_b"], shi), _cc(cap4["snap_a"], shi)
    present4, rem4 = _eff(cap4["dec_a"], shi)
    print(f"[TS/refresh] Shiron cc {cc4_b} -> {cc4_a} | rem {rem_now} -> {rem4}")
    assert present4, "LIVE: Thrilled perdu au 2e declenchement"
    assert cc4_a == cc4_b, (f"LIVE: le stat-mod S'EMPILE ({cc4_b} -> {cc4_a}) -- la branche "
                            f"ChangeEffectTurns(Set) devrait etre prise, pas AddStatic")
    exp4 = TURNS - (1 if cap4["turn_ticked"] else 0)        # cf. `_Harness.attack` (tick auto)
    assert rem4 == exp4, (f"LIVE: duree non remise a {exp4} par ChangeEffectTurns(Set) "
                          f"(rem={rem4}, avant={rem_now}, tick auto={cap4['turn_ticked']})")

    st4 = h.replay(cap4)
    off4_present, off4_rem = _off_eff(st4, shi)
    off4_cc = _ctx(st4, shi).stat(StatType.CRIT_CHANCE)
    print(f"[TS/refresh] MOTEUR cc={off4_cc} rem={off4_rem}")
    assert off4_present, "MOTEUR: Thrilled perdu au refresh"
    assert off4_cc == cc4_a, f"MOTEUR: refresh divergent (cc={off4_cc} vs live {cc4_a})"
    # `ChangeEffectTurns(Set, TurnsFromRounds(1))` cote moteur (sans le tick auto du live) : la
    # duree est REMISE a `TURNS` -- c'est la preuve que la branche Set a bien ete prise (elle
    # valait `rem_now` < TURNS juste avant).
    assert off4_rem == TURNS, (f"MOTEUR: duree {off4_rem} != {TURNS} -- ChangeEffectTurns(Set) "
                               f"n'a pas remis le timer (avant={rem_now})")


def test_thrill_seekers_expires_and_reverts_the_stat_mod(rpc, build_runner):
    """(5) Le stat-mod SORT a l'expiration du timer, cote LIVE et cote MOTEUR (mirror
    `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`). Sans le foyer de revert
    au tick (`revert_stat_mods_of_removed_effects`), le port gardait le +15 A VIE."""
    from engine.runner.operations.turnflow import EndTurnOperation

    h, ids = _battle(rpc, build_runner, "31337")
    ada, foe = ids["adamatar"], ids["foeB"]
    h.move(foe, 3, 3)
    h.move(ada, 2, 3)
    cap = h.attack(ada, foe)
    assert _eff(cap["dec_a"], ada)[0], "Thrilled non pose -- expiration non testable"
    cc_on = _cc(cap["snap_a"], ada)

    # LIVE : tourner jusqu'a expiration -> la crit chance doit REDESCENDRE.
    for _ in range(TURNS + 2):
        h.endturn()
        if not _eff(h.dec(), ada)[0]:
            break
    cc_off_live = _cc(h.snap(), ada)
    print(f"\n[TS/expire] Adamatar cc actif={cc_on} -> apres expiration={cc_off_live}")
    assert not _eff(h.dec(), ada)[0], "LIVE: Thrilled n'expire pas"
    assert cc_off_live == cc_on - EXTRA_CC, (
        f"LIVE: cc {cc_off_live} apres expiration, attendu {cc_on - EXTRA_CC}")

    # MOTEUR : meme sequence depuis la capture (pose offline puis EndTurn jusqu'a expiration).
    st = h.replay(cap)
    ctx = _ctx(st, ada)
    assert ctx.stat(StatType.CRIT_CHANCE) == cc_on, "MOTEUR: pose divergente avant le tick"
    for _ in range(TURNS):
        EndTurnOperation.execute(st, advance=True)
    off_present, off_rem = _off_eff(st, ada)
    print(f"[TS/expire] MOTEUR cc apres {TURNS} EndTurn = {ctx.stat(StatType.CRIT_CHANCE)} "
          f"(effet rem={off_rem})")
    # A l'echeance l'effet N'EXISTE PLUS : `EffectComponent$$ShouldBeRemoved` (`HasTurns && Duration
    # == 0`) fait prendre a `RefreshEffectsOperation$$RefreshEffect` la branche `DeactivateEffect` +
    # retrait de l'entite-effet. Offline la marque est `consumed`, que `_off_eff` honore -> l'effet
    # sort de la vue, il ne reste pas « visible a rem<=0 ». (Ce predicat attendait l'ancien
    # comportement, ou seul `expired` etait pose ; corrige avec la dynamique d'expiration, O3.)
    assert not off_present, f"MOTEUR: effet non retire a l'echeance (present={off_present})"
    assert ctx.stat(StatType.CRIT_CHANCE) == cc_on - EXTRA_CC, (
        f"MOTEUR: stat-mod NON reverte a l'expiration "
        f"(cc={ctx.stat(StatType.CRIT_CHANCE)}, attendu {cc_on - EXTRA_CC})")


@pytest.mark.parametrize("carrier,seed,board", [
    # DEUX couples (porteur, seed, board) distincts : le verdict ne doit rien devoir a la geometrie
    # d'UN plateau ni au kit d'UN porteur. Adamatar = melee au contact ; Shiron = ranged a 2 hex.
    ("adamatar", "8118", "MC1_67"),
    ("shiron", "4242", "C4_09"),
])
def test_thrill_seekers_seeded_stat_mod_reverts_on_expiry(rpc, build_runner, carrier, seed, board):
    """(6) #118 -- STACK SEEDE : l'etat offline est charge APRES la pose, donc `Thrilled` est DEJA
    porte et son +15 est DEJA CUIT dans `combatSnapshot.stats`. Le stat-mod doit quand meme SORTIR
    a l'expiration, cote LIVE et cote MOTEUR.

    C'est le cas que le test (5) ne couvre PAS : lui charge l'etat AVANT l'attaque, donc l'effet est
    pose OFFLINE (la feuille `AddStaticStatModifierEffect` renseigne sa cle de source) -- le revert
    marchait deja. Ici l'effet arrive par `EffectsState.seed` / `UnitContext.from_snapshot` : sa
    contribution n'etait attribuee A AUCUNE source retirable (elle tombait dans le residu opaque
    `CAPTURED_SOURCE`), donc l'expiration offline gardait le +15 A VIE.

    Natif : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` ecrit un
    `IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat(Entity(target), Position(stat, part 5|9), 4,
    Direct(amount), Entity(<effectEntity>))` -- la SOURCE est l'entite-effet -- et
    `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` rejoue le MEME appel en
    `part 6` avec LA MEME entite -> `IdunBattle.Entities.Components.ValueModification$$ReverseModification`.
    Un effet a stat-mod ne peut donc PAS disparaitre en laissant sa contribution."""
    from engine.runner.operations.turnflow import EndTurnOperation

    h, ids = _battle(rpc, build_runner, seed, board=board)
    ada, foe = ids[carrier], ids["foeB"]
    h.move(foe, 3, 3)                        # cible au centre (tuile jouable sur les deux boards)
    h.move(ada, 2, 3) if carrier == "adamatar" else h.move(ada, 1, 2)   # contact / 2 hex (portee 3)
    h.attack(ada, foe)                       # pose `Thrilled` sur le porteur (cible pleine vie)

    # CAPTURE APRES LA POSE : c'est LA difference avec (5) -- l'effet est deja actif ici.
    dec, ob, snap = h.dec(), rpc("observeBattle", {"runnerId": h.rid}, 40), h.snap()
    present, rem = _eff(dec, ada)
    cc_on = _cc(snap, ada)
    print(f"\n[TS/seeded] capture AVEC Thrilled actif: present={present} rem={rem} cc={cc_on}")
    assert present and rem and rem > 0, (
        f"capture prise sans Thrilled a timer (present={present} rem={rem}) -- cas SEEDE non arme")

    # MOTEUR : etat SEEDE depuis cette capture, puis on tique jusqu'a expiration.
    st = load_state(dec, ob, snap, board=h.board)
    ctx = _ctx(st, ada)
    assert ctx.stat(StatType.CRIT_CHANCE) == cc_on, (
        f"MOTEUR: seed divergent avant tout tick (cc={ctx.stat(StatType.CRIT_CHANCE)} != {cc_on})")
    for _ in range(int(rem)):
        EndTurnOperation.execute(st, advance=True)
    off_present, off_rem = _off_eff(st, ada)
    off_cc = ctx.stat(StatType.CRIT_CHANCE)
    print(f"[TS/seeded] MOTEUR apres {rem} EndTurn: present={off_present} rem={off_rem} cc={off_cc}")
    # Meme point qu'au test precedent : a l'echeance l'entite-effet est RETIREE
    # (`EffectComponent$$ShouldBeRemoved` -> `RefreshEffect` branche `DeactivateEffect`), donc absente
    # de la vue -- et non « presente a rem<=0 ».
    assert not off_present, f"MOTEUR: effet seede non retire a l'echeance (present={off_present})"

    # LIVE : meme sequence, l'oracle. La crit chance doit redescendre du MEME montant.
    for _ in range(int(rem) + 2):
        h.endturn()
        if not _eff(h.dec(), ada)[0]:
            break
    assert not _eff(h.dec(), ada)[0], "LIVE: Thrilled n'expire pas"
    cc_live = _cc(h.snap(), ada)
    print(f"[TS/seeded] LIVE cc apres expiration = {cc_live} (etait {cc_on})")
    assert cc_live == cc_on - EXTRA_CC, (
        f"LIVE: cc {cc_live} apres expiration, attendu {cc_on - EXTRA_CC}")
    assert off_cc == cc_live, (
        f"MOTEUR: stat-mod SEEDE non reverte a l'expiration (cc={off_cc}, live {cc_live}) -- "
        f"la contribution du seed n'est attribuee a aucune source retirable")
