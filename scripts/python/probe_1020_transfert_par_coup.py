"""#1020 -- MESURE de l'etage `On(0x39 = EventTriggerType.PreDamageTaken)` : emission PAR COUP,
retour LU par le champ pendant, et CONSERVATION du degat transfere.

Ce probe MESURE (il n'assertionne pas -- le cliquet, lui, est `tests/engine/test_1020_transfert_offline.py`).
Six etages, tous OFFLINE (aucun runner, aucun RPC) :

  0. l'invariant NO-OP du chokepoint : sans consommateur, `kept == total` a l'identique ;
  1. la GRANULARITE : autant d'emissions que de coups portant du degat ;
  2. le GATE `0 < DamageAppliedResult.get_Damage(&result)` : un coup a zero n'emet pas ;
  3. `isFirstDamagingHit` PAR COUP : seul le PREMIER coup damageant le porte ;
  4. la CONSOMMATION : un trigger qui vide le pending retire ce coup-la, et LUI SEUL ;
  5. la CONSERVATION sur `transfer_damage_operation` : ce que la victime ne perd pas, le
     protecteur le prend (deux entites nues, pas de board).

Usage : `python probe_1020_transfert_par_coup.py` depuis `scripts/python`.
"""
from __future__ import annotations

import sys


def _mk_health(hp=1000, hp_max=1000):
    from engine.runner.components import HealthComponent
    return HealthComponent(hp=hp, hp_max=hp_max)


class _FauxDispatch:
    """Substitut du module `triggers.dispatch.attack` : `_pre_damage_taken_per_hit` le recoit en
    ARGUMENT, donc aucune monkey-substitution n'est necessaire (et aucune forme A/B/C d'import ne
    peut desarmer la mesure -- cf. la regle sur les imports differes)."""

    def __init__(self, consume_at=None, thc=None):
        self.calls = []            # (profile, is_first_damaging_hit)
        self.consume_at = consume_at
        self.thc = thc

    def pre_damage_taken_triggers(self, state, source_id, target_id, profile=None,
                                  is_first_damaging_hit=None):
        idx = len(self.calls)
        self.calls.append((profile, is_first_damaging_hit))
        if self.consume_at is not None and idx == self.consume_at:
            # mirror `TransferDamageOperation$$GetDamage` : `*(qword*)(comp+0x64) = 0`
            self.thc.pending_damage = None
        return []


def etage_0_noop():
    """Sans consommateur, le chokepoint rend EXACTEMENT ce qu'il recevait avant #1020."""
    from engine.runner.operations.damage import AttackDamageOperation as A
    ok = True
    for pend, total, shield in (([(300, 0), (250, 0), (200, 0)], 750, 0),
                                ([(120, 30), (80, 0)], 200, 30),
                                (None, 500, 0),                 # vecteur sans decomposition
                                ([], 0, 0)):
        thc = _mk_health()
        d = _FauxDispatch()
        hits = None if pend is None else {"per_hit_pending": pend}
        kept_h, kept_s, tr = A._pre_damage_taken_per_hit(
            None, 1, 2, thc, total, shield, "Physical", hits, d,
            is_first_damaging_hit=True)
        good = (kept_h == total and kept_s == shield and tr == 0
                and thc.pending_damage is None)
        ok = ok and good
        print("[1020/0] pend=%-26s total=%4d shield=%3d -> kept=(%4d,%3d) transfers=%d  %s"
              % (pend, total, shield, kept_h, kept_s, tr, "OK" if good else "DIVERGE"))
    return ok


def etage_1_granularite():
    """Le natif appelle `ApplyDamageOperation$$Execute` UNE FOIS PAR COUP -- donc autant
    d'emissions `On(0x39)` que de coups portant du degat, la ou le port n'en faisait qu'UNE."""
    from engine.runner.operations.damage import AttackDamageOperation as A
    thc = _mk_health()
    d = _FauxDispatch()
    A._pre_damage_taken_per_hit(None, 1, 2, thc, 750, 0, "Physical",
                                {"per_hit_pending": [(300, 0), (250, 0), (200, 0)]}, d,
                                is_first_damaging_hit=True)
    good = len(d.calls) == 3
    print("[1020/1] 3 coups -> %d emission(s)  %s (le port par-groupe en faisait 1)"
          % (len(d.calls), "OK" if good else "DIVERGE"))
    return good


def etage_2_gate_zero():
    """`if (0 < DamageAppliedResult.get_Damage(&result))` : un coup entierement bloque n'emet pas.
    Le gate porte sur `health + shield`, donc un coup a `(0, 40)` emet BIEN."""
    from engine.runner.operations.damage import AttackDamageOperation as A
    thc = _mk_health()
    d = _FauxDispatch()
    A._pre_damage_taken_per_hit(None, 1, 2, thc, 300, 40, "Physical",
                                {"per_hit_pending": [(0, 0), (300, 0), (0, 40)]}, d,
                                is_first_damaging_hit=True)
    good = len(d.calls) == 2
    print("[1020/2] coups [(0,0),(300,0),(0,40)] -> %d emission(s), attendu 2  %s"
          % (len(d.calls), "OK" if good else "DIVERGE"))
    return good


def etage_3_first_damaging_hit():
    """`DamageAppliedResult+0x18 isFirstDamagingHit` est PROPRE AU COUP. Le flag threade dit
    « aucun degat encore inflige dans CETTE attaque » ; il se consomme au premier coup qui emet."""
    from engine.runner.operations.damage import AttackDamageOperation as A
    thc = _mk_health()
    d = _FauxDispatch()
    A._pre_damage_taken_per_hit(None, 1, 2, thc, 500, 0, "Physical",
                                {"per_hit_pending": [(0, 0), (300, 0), (200, 0)]}, d,
                                is_first_damaging_hit=True)
    flags = [f for (_p, f) in d.calls]
    good = flags == [True, False]
    print("[1020/3] flags emis = %s, attendu [True, False]  %s"
          % (flags, "OK" if good else "DIVERGE"))
    # groupe qui n'est PAS le premier damageant : aucun coup ne porte le flag.
    thc2, d2 = _mk_health(), _FauxDispatch()
    A._pre_damage_taken_per_hit(None, 1, 2, thc2, 500, 0, "Physical",
                                {"per_hit_pending": [(300, 0), (200, 0)]}, d2,
                                is_first_damaging_hit=False)
    flags2 = [f for (_p, f) in d2.calls]
    good2 = flags2 == [False, False]
    print("[1020/3] groupe non-premier -> %s, attendu [False, False]  %s"
          % (flags2, "OK" if good2 else "DIVERGE"))
    return good and good2


def etage_4_consommation():
    """Un consommateur qui vide `HealthComponent.pending_damage` retire le degat de CE COUP-LA,
    et lui seul -- c'est la difference entre DEPLACER et DOUBLER."""
    from engine.runner.operations.damage import AttackDamageOperation as A
    ok = True
    for at, attendu in ((0, 450), (1, 500), (2, 550)):
        thc = _mk_health()
        d = _FauxDispatch(consume_at=at, thc=thc)
        kept_h, kept_s, tr = A._pre_damage_taken_per_hit(
            None, 1, 2, thc, 750, 0, "Physical",
            {"per_hit_pending": [(300, 0), (250, 0), (200, 0)]}, d,
            is_first_damaging_hit=True)
        good = (kept_h == attendu and tr == 1)
        ok = ok and good
        print("[1020/4] consomme le coup %d -> kept=%3d (attendu %3d), transfers=%d  %s"
              % (at, kept_h, attendu, tr, "OK" if good else "DIVERGE"))
    # bouclier : la part `+0x08` disparait aussi du pending relu
    thc = _mk_health()
    d = _FauxDispatch(consume_at=0, thc=thc)
    kh, ks, _ = A._pre_damage_taken_per_hit(None, 1, 2, thc, 200, 30, "Physical",
                                            {"per_hit_pending": [(120, 30), (80, 0)]}, d,
                                            is_first_damaging_hit=True)
    good = (kh, ks) == (80, 0)
    ok = ok and good
    print("[1020/4] coup (120,30) consomme -> kept=(%d,%d), attendu (80,0)  %s"
          % (kh, ks, "OK" if good else "DIVERGE"))
    return ok


def etage_5_conservation():
    """`transfer_damage_operation` : ce que la victime ne perd plus, le protecteur le prend.
    Deux entites NUES (ni board ni adjacence) -- l'operation elle-meme ne les consulte pas."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, PendingDamage
    from engine.runner.operations.transfer_damage import transfer_damage_operation
    st = State()
    victime, drone, source = st.add_entity(), st.add_entity(), st.add_entity()
    for e, hp in ((victime, 1000), (drone, 800), (source, 900)):
        e.add_component(UnitComponent(visual_id="tauCrisis", alive=True))
        e.add_component(_mk_health(hp=hp, hp_max=hp))
    from engine.runner.components import HealthComponent
    vhc = victime.get_component(HealthComponent)
    dhc = drone.get_component(HealthComponent)
    vhc.pending_damage = PendingDamage("Physical", 240, 0)
    hp_v0, hp_d0 = vhc.hp, dhc.hp
    res = transfer_damage_operation(st, source.id, victime.id, drone.id)
    perdu_v = hp_v0 - (vhc.hp or 0)
    perdu_d = hp_d0 - (dhc.hp or 0)
    consomme = vhc.pending_damage is None
    good = (perdu_v == 0 and perdu_d == 240 and consomme and res is not None)
    print("[1020/5] pending 240 -> victime perd %d PV, drone perd %d PV, pending consomme=%s  %s"
          % (perdu_v, perdu_d, consomme, "OK" if good else "DIVERGE"))
    # pending VIDE -> l'operation ne fait RIEN (le `if (*pcVar7 != 0)` du natif)
    hp_d1 = dhc.hp
    res2 = transfer_damage_operation(st, source.id, victime.id, drone.id)
    good2 = (res2 is None and dhc.hp == hp_d1)
    print("[1020/5] pending vide -> res=%s, drone inchange=%s  %s"
          % (res2, dhc.hp == hp_d1, "OK" if good2 else "DIVERGE"))
    return good and good2


def main() -> int:
    print("=== #1020 -- etage PreDamageTaken par coup + transfert ===")
    res = [("noop", etage_0_noop()),
           ("granularite", etage_1_granularite()),
           ("gate zero", etage_2_gate_zero()),
           ("isFirstDamagingHit", etage_3_first_damaging_hit()),
           ("consommation", etage_4_consommation()),
           ("conservation", etage_5_conservation())]
    print("--- bilan ---")
    for nom, ok in res:
        print("  %-20s %s" % (nom, "OK" if ok else "DIVERGE"))
    return 0 if all(ok for _n, ok in res) else 1


if __name__ == "__main__":
    sys.exit(main())
