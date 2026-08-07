#!/usr/bin/env python
"""probe #512-r2 -- la famille de factory ABILITY emet-elle `On(PreAttack = 5)` ?

CE QUE LE DECOMPILE DIT (relu verbatim, build courant)
-------------------------------------------------------
  * `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -- surcharge RACINE a 7
    arguments, celle a laquelle les trois autres delegent -- construit un `AbilityDamageBehaviour`
    PUIS `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor(caster, target, <ce behaviour>,
    abilityOrEffect)`, et c'est l'`AttackBehaviour` qu'elle RETOURNE. La famille ABILITY ouvre donc
    une attaque exactement comme la famille ATTACK -> `StartAttack` -> `On(5)`.
  * MAIS `IdunBattleLogic.Entities.DSLBehaviors$$AbilityDamage` (8 arguments, dont
    `isOutsideAttack`) construit la feuille **NUE** -- aucun `AttackBehaviour`. C'est CELLE-LA
    qu'utilise `1088 HellfyreMissileRack`, deux fois, sous un `SortedAttackSeries`.
  * `IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour$$Execute` invoque les slots
    `0x3a`/`0x3b` = **58 `StartAttack` / 59 `FinishAttack`** (arite 3, LUS dans
    `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`) a chaque CHANGEMENT de cible de
    sa serie. C'est le QUATRIEME emetteur de `On(5)` du binaire, et il emet **par cible DISTINCTE**.

=> le critere n'est pas la FAMILLE, c'est `isOutsideAttack` + le noeud qui ouvre la serie.

CE QUE CE PROBE MESURE
------------------------
Porteur `thousTerminator` << Toth >> (LINEUP, DANS le pool) : trait `SuppressiveFire`, et **PAS**
`TerrifyingCrescendo` -- la pose de `Pinned` ne se paie donc pas en degat, elle se LIT.
Son active `1088 HellfyreMissileRack` est `attackRangeType = Ranged` et famille ABILITY.

  E0  `ported`
  E1  ensemble des `Pinned` (1065) poses -- PORT vs NATIF (le natif est l'oracle)
  E2  nombre d'emissions `On(5)` cote PORT == nombre de cibles DISTINCTES de la serie

CONTRE-EPREUVES (chacune ne change QU'UNE lecture, sur la MEME capture) :
  AB1  le gate `is_attack_damage_op` restaure sur `damage_ops/ability.py` -- l'etat d'AVANT #512-r2.
  AB2  `SortedAttackSeries` rendu MUET (il n'emet plus) -- montre que c'est bien LUI qui porte
       l'emission ici, et pas les feuilles.
  AB3  `is_outside_attack = True` sur les feuilles ET noeud muet -- la lecture NAIVE (« la famille
       ABILITY emet, donc chaque feuille emet »). Elle SUR-EMET des que deux feuilles tombent sur la
       MEME cible ; le probe l'exerce en posant, cote port, la trace Psychic qui rend la cible
       eligible au 2e volet de 1088 (`HasTakenDamageOfDamageProfileThisTurn`).

Usage (depuis `scripts/python`, ASCII only) :
    python probe_512r2_famille_ability_preattack.py [--keep] [--state-file <absolu>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

HELLFYRE = 1088                        # `ActiveAbilityType.HellfyreMissileRack`
PINNED = 1065                          # `EffectType.Pinned` (0x429) -- UI << Suppressed >>
PSYCHIC = 13                           # `DamageProfileType.Psychic` (0xd)

CASTER = "thousTerminator"             # trait SuppressiveFire, PAS TerrifyingCrescendo, DANS le pool
FOES = ("necroWarden", "orksNob", "tauMarksman")

BOARD = "MC1_67"
SEED = 5122

#: Geometrie DRIVEE : caster en (4,5), cible d'ORIGINE sur la tuile VOISINE (4,6) -- une ability
#: `Ranged(2)` castee AU CONTACT, ce que la branche positionnelle declarerait melee.
P_PLACE = ((CASTER, "4,5"),)
A_PLACE = ((FOES[0], "4,6"), (FOES[1], "4,7"), (FOES[2], "3,6"))
ORIGINE = FOES[0]


def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


def build(state_file: str):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--hp-target", "400000",
            "--p-units", ",".join(v for v, _t in P_PLACE),
            "--a-units", ",".join(v for v, _t in A_PLACE),
            "--state-file", state_file]
    for vid, tile in P_PLACE:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACE:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-1800:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def vue(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {
            "id": u.get("id"), "pos": (p.get("col"), p.get("row")),
            "alive": not u.get("isDead"),
            "effets": sorted(e.get("effectType") for e in (u.get("effects") or [])
                             if isinstance(e, dict) and e.get("effectType") is not None)}
    return out


def capture(sid, rid):
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def assert_montage(u, cap):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer."""
    import engine.battle_query as bq
    voulu = dict(P_PLACE) | dict(A_PLACE)
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide : %r" % (mauvais,))
    neigh, elev = {}, {}
    byid = {t["id"]: (t["col"], t["row"]) for t in cap["tiles"]}
    for t in cap["tiles"]:
        elev[(t["col"], t["row"])] = t.get("elevation", 0)
        neigh[(t["col"], t["row"])] = [byid[n] for n in (t.get("neighbours") or []) if n in byid]
    if not bq.are_entities_adjacent(u[CASTER]["pos"], u[ORIGINE]["pos"], elev, neigh):
        raise SystemExit("la cible d'ORIGINE n'est PAS adjacente au caster -- la branche "
                         "`Ranged(2) ne lit aucune position` ne serait PAS mesuree")


def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale (a appeler sous `snapshot.live_rpc`)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def _pinned_du_port(st, ids):
    from engine.runner.components import has_effect_of_type
    return sorted(i for i in ids if has_effect_of_type(st, int(i), PINNED))


def rejeu_porte(cap, caster_id, target_id, ids, marquer_psychic=None):
    """Rejoue le cast hors-ligne. `marquer_psychic` = id d'une unite a qui l'on POSE la trace
    << a pris du Psychic ce tour >>, ce qui la rend eligible au 2e volet de 1088 -- donc frappee
    DEUX fois par la serie. C'est le seul regime ou la SUR-EMISSION est observable."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    import engine.runner.operations.triggers.dispatch.attack as ATK
    st = etat_porte(cap)
    if marquer_psychic is not None:
        # LE CANAL EST `UnitComponent.received_damage_this_turn` -- mirror d'
        # `ActorStatisticsComponent+0x80 = receivedDamageThisTurn`, que
        # `DSLTriggers$$HasTakenDamageOfDamageProfileThisTurn` lit par PRESENCE de cle.
        from engine.runner.components import UnitComponent
        e = st.get_entity(int(marquer_psychic))
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None:
            raise SystemExit("pas de `UnitComponent` sur u%s -- la trace Psychic ne peut pas etre "
                             "posee, le regime de recouvrement ne serait pas monte"
                             % (marquer_psychic,))
        d = uc.received_damage_this_turn
        if not isinstance(d, dict):
            d = uc.received_damage_this_turn = {}
        d[int(PSYCHIC)] = int(d.get(int(PSYCHIC), 0)) + 1
    emissions: list = []
    attaques: list = []
    vrai = ATK.pre_attack_triggers
    from engine.runner.operations.damage import AttackDamageOperation
    vrai_atk = AttackDamageOperation.execute_ability_attack

    def _compte(state, attacker_id, tgt, **kw):
        emissions.append((int(attacker_id), int(tgt)))
        return vrai(state, attacker_id, tgt, **kw)

    def _compte_atk(state, aid, tid_, *a, **kw):
        attaques.append((int(aid), int(tid_)))
        return vrai_atk(state, aid, tid_, *a, **kw)

    ATK.pre_attack_triggers = _compte
    AttackDamageOperation.execute_ability_attack = staticmethod(_compte_atk)
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                          ability_type=HELLFYRE))
    finally:
        ATK.pre_attack_triggers = vrai
        AttackDamageOperation.execute_ability_attack = staticmethod(vrai_atk)
    last = getattr(runner.ability_handler, "last", None) or {}
    return {"ported": last.get("ported"), "pinned": _pinned_du_port(st, ids),
            "emissions": emissions, "attaques": attaques}


def contre_epreuves(cap, caster_id, target_id, ids, psychic_id):
    import engine.runner.abilities.behaviours.combat as CB
    import engine.runner.operations.damage_ops.ability as DA
    from engine.runner.abilities import thousandsons as TS
    out = {}

    def _joue(marquer=None):
        r = rejeu_porte(cap, caster_id, target_id, ids, marquer_psychic=marquer)
        return (r["pinned"], len(r["emissions"]), len(r["attaques"]))

    out["REF"] = _joue()
    out["REF + trace Psychic (recouvrement)"] = _joue(psychic_id)

    # AB1 -- le gate de famille RESTAURE : `execute_ability_attack` n'emet plus rien pour la
    # famille ABILITY, et le noeud non plus (l'etat d'AVANT #512-r2, ou rien n'etait emis).
    vrai_ser = CB.SortedAttackSeries.execute
    try:
        CB.SortedAttackSeries.execute = _muet(vrai_ser)
        out["AB1 noeud MUET (etat d'avant #512-r2)"] = _joue()
    finally:
        CB.SortedAttackSeries.execute = vrai_ser

    # AB2 -- la lecture NAIVE : chaque FEUILLE emet, le noeud reste muet. On force le drapeau AU
    # POINT D'ENTREE de l'Operation, pas sur l'arbre : l'arbre est construit une fois pour toutes
    # par la classe d'ability, donc patcher sa FABRIQUE (forme A, binding gele) ou son `__init__`
    # ne mordrait PAS -- mesure faite, les deux rendaient 0 emission.
    from engine.runner.operations.damage import AttackDamageOperation
    vrai_atk = AttackDamageOperation.execute_ability_attack

    def _force_outside(state, aid, tid_, *a, **kw):
        kw["is_outside_attack"] = True
        return vrai_atk(state, aid, tid_, *a, **kw)

    try:
        CB.SortedAttackSeries.execute = _muet(vrai_ser)
        AttackDamageOperation.execute_ability_attack = staticmethod(_force_outside)
        out["AB2 feuilles OUTSIDE + noeud muet (lecture naive)"] = _joue(psychic_id)
    finally:
        CB.SortedAttackSeries.execute = vrai_ser
        AttackDamageOperation.execute_ability_attack = staticmethod(vrai_atk)
    _ = (DA, TS)     # importes pour documenter les foyers touches ; aucune mutation ici
    return out


def _muet(vrai):
    """`SortedAttackSeries.execute` prive de SON emission -- celles des FEUILLES passent.

    ⚠ Le discriminant est l'ARGUMENT, pas la pile : le noeud appelle `pre_attack_triggers` SANS
    `profile` (il n'en a pas -- le profil vit sur chaque feuille), les feuilles avec. Neutraliser
    tout appel pendant `execute` (premiere version de ce probe) etouffait AUSSI les feuilles, et
    rendait la contre-epreuve AB2 INERTE : elle mesurait 0 emission au lieu de 2."""
    def _wrap(self, entities, ectx):
        import engine.runner.operations.triggers.dispatch.attack as ATK
        sauve = ATK.pre_attack_triggers

        def _filtre(state, aid, tid_, **kw):
            if kw.get("profile") is None:              # <- l'emission DU NOEUD
                return []
            return sauve(state, aid, tid_, **kw)

        ATK.pre_attack_triggers = _filtre
        try:
            return vrai(self, entities, ectx)
        finally:
            ATK.pre_attack_triggers = sauve
    return _wrap


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #512-r2 -- On(PreAttack=5) famille ABILITY")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS le runner")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = a.state_file or os.path.join(tempfile.gettempdir(), "p512r2_%d.json" % os.getpid())
    sid = _sid()
    rid = build(sf)
    if rid is None:
        print("[512-r2] build KO -- rien mesure")
        return 99
    try:
        u = vue(sid, rid)
        cap = capture(sid, rid)
        assert_montage(u, cap)
        ids = [u[v]["id"] for v in u]
        cid, tid = u[CASTER]["id"], u[ORIGINE]["id"]
        inv = {u[v]["id"]: v for v in u}
        from engine.runner.snapshot import live_rpc
        with live_rpc(lambda m, b=None, t=120: _rpc(sid, m, b, t)):
            port = rejeu_porte(cap, cid, tid, ids)
            ab = contre_epreuves(cap, cid, tid, ids, tid)
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(HELLFYRE),
                   "--target", str(tid), "--state-file", sf, "--runner", str(rid)])
        apres = vue(sid, rid)
        natif = sorted(apres[v]["id"] for v in apres if PINNED in (apres[v]["effets"] or []))
        nom = lambda s: [("%s/u%s" % (inv.get(i, "?"), i)) for i in s]
        print("[512-r2] runner=%s caster=%s@%s (SuppressiveFire, PAS TerrifyingCrescendo)"
              % (rid, CASTER, u[CASTER]["pos"]))
        print("        cible d'ORIGINE %s@%s -- ADJACENTE au caster (1088 est `Ranged`)"
              % (ORIGINE, u[ORIGINE]["pos"]))
        print("        unites : " + " ".join("%s=u%s@%s" % (v, u[v]["id"], u[v]["pos"])
                                             for v in sorted(u)))
        print("  E0 ported    = %s" % (port["ported"],))
        print("  E1 PINNED (1065)  PORT =%s" % (nom(port["pinned"]),))
        print("                    NATIF=%s" % (nom(natif),))
        print("  E2 emissions On(5) cote PORT = %d  -> %s"
              % (len(port["emissions"]), [(inv.get(x[0], x[0]), inv.get(x[1], x[1]))
                                          for x in port["emissions"]]))
        print("  -- contre-epreuves (hors-ligne, meme capture) --")
        ref = ab["REF"]
        for k, v in ab.items():
            marque = ""
            if k != "REF":
                marque = "  <- INERTE (ne mesure rien)" if v == ref else ""
            print("     %-52s pinned=%s emissions=%d attaques=%d%s"
                  % (k, nom(v[0]), v[1], v[2], marque))
        ok = bool(port["ported"]) and port["pinned"] == natif and len(natif) >= 1
        # La contre-epreuve qui garde le VOLET 1 : sans emission, aucun `Pinned`.
        mord_ab1 = ab["AB1 noeud MUET (etat d'avant #512-r2)"][0] != ref[0]
        # Celle qui garde le VOLET 2 (pas de sur-emission) : sous RECOUVREMENT (deux feuilles sur
        # la MEME cible), le port emet UNE fois et la lecture naive DEUX.
        rec = ab["REF + trace Psychic (recouvrement)"]
        naif = ab["AB2 feuilles OUTSIDE + noeud muet (lecture naive)"]
        recouvre = rec[2] > ref[2]                    # le 2e volet a bien re-frappe la meme cible
        mord_ab2 = recouvre and naif[1] > rec[1]
        if not ok:
            print("     sortie du cast NATIF (diagnostic) :\n%s" % ((p.stdout or "")[-2500:],))
        if not mord_ab1:
            print("     !! AB1 est INERTE : le volet 1 (la famille ABILITY emet) n'est PAS mesure")
        if not recouvre:
            print("     !! le RECOUVREMENT n'a pas eu lieu (attaques REF=%d, avec trace=%d) -- "
                  "la SUR-EMISSION n'est PAS mesuree ici" % (ref[2], rec[2]))
        elif not mord_ab2:
            print("     !! AB2 est INERTE malgre le recouvrement (emissions REF=%d, naive=%d)"
                  % (rec[1], naif[1]))
        print("[512-r2] %s (AB1 mord=%s, AB2 mord=%s)"
              % ("ACCORD port/natif" if ok else "DESACCORD", mord_ab1, mord_ab2))
        return 0 if (ok and mord_ab1) else 1
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", sf, "--runner", str(rid)], timeout=120)


if __name__ == "__main__":
    raise SystemExit(main())
