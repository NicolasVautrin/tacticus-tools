"""#521-r1 -- la face TRIGGERED de `1195 TalonsOfTheEmperor` : `1330 TalonsOfTheEmperor_UsedAbilities`
FAIT-ELLE AVANCER LE COMPTEUR 1420 AUX MEMES MOMENTS QUE LE NATIF ?

C'est la question BINAIRE de la tranche, et elle se decompose en trois lectures independantes :

  1. **MONTAGE** -- le trigger est-il seulement INSCRIT sur `custoAtlacoya` ? Son kit ne porte 1330 ni
     en `passiveAbilities` ni en triggered derivee : le natif le monte par
     `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`
     (dict statique `<...ActiveAbility statics>+0x78`, SIX entrees), via
     `IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility`. Un port qui se tromperait de dict
     n'inscrirait RIEN et le compteur resterait fige -- **sans aucune erreur**.
  2. **QUAND** -- `On(0xe = UnitPostAbility) & AreFriends & HasTrait(Hero) & !HasTrait(MachineOfWar)
     & IsActiveAbilityCountedAsUsed(false)`. Le temoin NEGATIF est l'attaque NORMALE, qui EST une
     active ability cote natif et qui emet donc `On(0xe)` : seul le dernier gate l'ecarte.
  3. **DE COMBIEN** -- `AddEffectOrIncreaseLevel(0x58c, level = Formulas@+0x20 = Direct(1),
     maxLevel = NULL)` : +1, sans cap, sur le PORTEUR.

## Les regimes

`chaine` (UN build, DEUX captures) exerce les deux branches du `If` interne et le DEGAT :

  cap0  compteur 0
  live  `custoTrajann` caste `1184 MomentShackle` (SELF-CAST, place LOIN)   -> compteur 1
  cap1  compteur 1
  live  `custoAtlacoya` caste `1195 TalonsOfTheEmperor` sur la cible        -> degat, compteur 2

  PORT-A  rejoue le cast de Trajann depuis cap0 -> branche **AddEffect** (0 -> 1)
  PORT-B  rejoue le cast de Talons  depuis cap1 -> **degat** + branche **IncreaseEffectLevel** (1 -> 2)

  DEUX captures, et c'est deliberé : le compteur se mesure SANS le MT (il ne depend d'aucun tirage),
  le degat se mesure sur un MT CALE (cap1). Chainer les deux rejeux dans un seul `State` melerait la
  fidelite du compteur a celle des tirages de `MomentShackle` -- exactement le << fit d'un scalaire >>
  que la doctrine interdit.

`attaque_normale` (UN build) est le TEMOIN NEGATIF : Atlacoya porte son attaque normale sur la cible
adjacente ; le compteur doit rester a 0 des DEUX cotes. Un port qui aurait oublie
`IsActiveAbilityCountedAsUsed` passerait le regime `chaine` et echouerait ICI.

## Les contre-epreuves (chacune ne change QU'UNE lecture du mirror)

  * `sans_registre`  -- vide `PASSIVE_HELPER_ABILITY_TRIGGERS` : le compteur ne bouge plus. C'est la
                        garde VUE ROUGE du montage.
  * `sans_gate_compte`-- force `IsActiveAbilityCountedAsUsed` a VRAI : l'attaque normale se met a
                        compter. C'est ce qui prouve que ce gate est bien le discriminant du regime
                        `attaque_normale`, et pas un accident de montage.
  * `gates_forges`   -- OFFLINE, sur l'etat capture : `matches` doit rendre FAUX pour un acteur
                        ENNEMI (`AreFriends`), pour un acteur sans `Hero`, et pour un acteur
                        `MachineOfWar` -- les trois volets que le live ne separe pas.

Usage :
    python probe_521r1_talons_used_abilities.py [--regime chaine|attaque_normale|tous] [--seed N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, PYDIR)

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")

TALONS = 1195                         # ActiveAbilityType.TalonsOfTheEmperor
MOMENT_SHACKLE = 1184                 # ActiveAbilityType.MomentShackle (SELF-CAST)
TALONS_USED_ABILITIES = 1420          # EffectType.TalonsOfTheEmperor_UsedAbilities (0x58c)

CASTER = "custoAtlacoya"              # Atlacoya -- SEUL porteur de 1195, lineup, pool rank 17
ALLY_CASTER = "custoTrajann"          # Character allie qui INCREMENTE le compteur
P_FILLER = "astraDreir"               # figurant du camp joueur, place LOIN
FOE = "necroWarden"                   # cible NON-Psyker (branche `else` = profil Power)
FOE_FILLER = "necroOverlord"          # 2e a-unit : la bataille ne finit pas si la cible tombe

BOARD = "MC1_67"
RANK = 17
#: Geometrie LUE dans `boardGraph` de MC1_67 (identique a `probe_521_talons_of_the_emperor.py`) :
#:   (5,8) voisins STOCKES = [(6,8), (6,7), (5,7), (4,7), (4,8)]
PLACE_CASTER = "5,8"
PLACE_ALLY = "1,7"        # LOIN du caster : jamais dans `AdjacentFriends` (ne pollue pas le profil)
PLACE_FILLER = "0,7"
A_PLACE_FOE = "6,8"       # adjacent au caster
A_PLACE_FILLER = "6,7"

HP_FOE = 300000           # la cible ne meurt jamais : la fenetre de mesure reste ouverte
ARMURE = 2000             # armure NON nulle : sans elle Power et DirectDamage rendraient le meme degat

DP_POWER = 14             # IdunBattle.Entities.Enum.DamageProfileType.Power

RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")

REGIMES = {
    "chaine": {
        "p": [(CASTER, PLACE_CASTER), (ALLY_CASTER, PLACE_ALLY), (P_FILLER, PLACE_FILLER)],
        "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)],
    },
    "attaque_normale": {
        "p": [(CASTER, PLACE_CASTER), (P_FILLER, PLACE_FILLER)],
        "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)],
    },
}


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ montage

def build(state_file: str, seed: int, regime: str):
    spec = REGIMES[regime]
    argv = ["build", "--seed", str(seed), "--board", BOARD, "--rank", str(RANK),
            "--p-units", ",".join(v for v, _t in spec["p"]),
            "--a-units", ",".join(v for v, _t in spec["a"]),
            "--crit", "0,0", "--block-target", "0,0",
            "--armor-target", str(ARMURE),
            "--state-file", state_file]
    for vid, tile in spec["p"]:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in spec["a"]:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
        # PAS `--hp-target` : il mettrait AUSSI l'armure a 0 et les deux profils rendraient le meme
        # degat -- l'etage `If` de 1195 ne serait plus mesure.
        argv += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (vid, HP_FOE, HP_FOE)]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, (p.stdout or "")[-2000:],
                                            (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {"id": u.get("id"), "pos": (p.get("col"), p.get("row")),
                                  "hp": u.get("hp"), "owner": u.get("owner"),
                                  "abilities": u.get("abilities") or [],
                                  "effects": u.get("effects") or []}
    return out, dv


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    spec = REGIMES[regime]
    voulu = {v: t for v, t in (spec["p"] + spec["a"])}
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage %s invalide : unites absentes %r" % (regime, manquants))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage %s invalide, pas de mesure : %r"
                         % (regime, mauvais))
    if int(u[FOE]["hp"] or 0) < 1000:
        raise SystemExit("cible trop fragile (%s PV)" % u[FOE]["hp"])


def _ability_entry(u, aid):
    return next((a for a in u["abilities"] if a.get("id") == aid), None)


def _normal_id(u):
    """Id CONCRET de l'attaque normale (`kind == "normal"`), per-unite -- jamais le 17 generique."""
    return next((a.get("id") for a in u["abilities"] if a.get("kind") == "normal"), None)


def compteur_live(u, visual_id=CASTER):
    """Niveau LIVE de l'effet 1420 sur le porteur, lu dans `decisionView.units[].effects` -- le MEME
    canal que celui dont `snapshot.load_state` seede `EffectsState`. None si le canal est muet."""
    effs = (u.get(visual_id) or {}).get("effects")
    if effs is None:
        return None
    total = 0
    for e in effs:
        et = e.get("effectType", e.get("effect_type"))
        if et is None:
            nm = e.get("name") or e.get("effectName") or ""
            if "TalonsOfTheEmperor_UsedAbilities" not in str(nm):
                continue
        elif int(et) != TALONS_USED_ABILITIES:
            continue
        total += int(e.get("level") or 0)
    return total


def capture(sid, rid):
    """L'etat COMPLET juste avant un cast natif -- le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "stats": _rpc(sid, "actorStats", {"runnerId": rid}, 60),
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng` (sans quoi le degat serait skippe
    par repli defensif et on lirait un faux 0)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"],
                    actor_stats=cap["stats"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable, aucune mesure de degat n'a de sens")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def compteur_porte(state, owner_id) -> int:
    """La MEME lecture que `runner/abilities/custodes.py::talons_used_abilities_level` -- somme des
    instances non consommees de 1420 portees par `owner_id`."""
    if getattr(state, "effects", None) is None:
        return 0
    return sum(int(e.level or 0) for e in state.effects.by_unit.get(int(owner_id), [])
               if not e.consumed and int(e.effect_type) == TALONS_USED_ABILITIES)


def rejeu_porte(cap, caster_id, target_id, ability_type, owner_id):
    """Rejoue UN cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`) : c'est
    ce qui exerce le dispatch `unit_post_ability_triggers` et donc le registre, et non un appel
    direct a `execute_behaviour`."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = compteur_porte(st, owner_id)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=int(ability_type)))
    last = getattr(runner.ability_handler, "last", None) or {}
    seq = [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
           for m in ((a.get("attack") or {}).get("per_hit_health") or [])]
    return {
        "ported": last.get("ported"),
        "compteur_avant": avant,
        "compteur_apres": compteur_porte(st, owner_id),
        "used_abilities_level": last.get("used_abilities_level"),
        "extra": last.get("extra_damage"),
        "seq": seq,
        "total": sum(m for _t, m in seq),
    }


def contre_epreuves(cap, caster_id, target_id, ability_type, owner_id):
    """Chacune ne change QU'UNE lecture. Si l'une rendait le MEME resultat que la REFERENCE, la
    lecture correspondante ne serait PAS mesuree par ce montage."""
    import engine.runner.operations.triggers.dispatch.registry as REG
    import engine.runner.operations.triggers.loki.fuelled_by_fury as FBF

    out = {"ref": rejeu_porte(cap, caster_id, target_id, ability_type, owner_id)}

    # `sans_registre` : le trigger n'est plus inscrit -> le compteur ne peut plus bouger.
    sauve = dict(REG.PASSIVE_HELPER_ABILITY_TRIGGERS)
    try:
        REG.PASSIVE_HELPER_ABILITY_TRIGGERS.clear()
        out["sans_registre"] = rejeu_porte(cap, caster_id, target_id, ability_type, owner_id)
    finally:
        REG.PASSIVE_HELPER_ABILITY_TRIGGERS.clear()
        REG.PASSIVE_HELPER_ABILITY_TRIGGERS.update(sauve)

    # `sans_gate_compte` : `IsActiveAbilityCountedAsUsed` fige a VRAI -> l'attaque normale compte.
    orig = FBF.is_active_ability_counted_as_used
    try:
        FBF.is_active_ability_counted_as_used = lambda *_a, **_k: True
        out["sans_gate_compte"] = rejeu_porte(cap, caster_id, target_id, ability_type, owner_id)
    finally:
        FBF.is_active_ability_counted_as_used = orig

    # Les deux LITTERAUX du `CreateBehaviour`, chacun mute seul. `execute_behaviour` resout
    # `talons_used_abilities_tree` dans les globals de SON module a chaque appel -> le `setattr`
    # mord (contraste une liaison `from ... import` posee ailleurs, qui ne mordrait pas).
    import engine.runner.operations.triggers.loki.talons_of_the_emperor as TOTE
    from engine.dsl.base import Const
    from engine.entities.selectors.tiles import Caster
    from engine.runner.abilities.behaviours.effects import add_effect_or_increase_level

    def _arbre(amount, max_level):
        return lambda: add_effect_or_increase_level(
            TOTE.TOTE_USED_ABILITIES, TOTE.TOTE_USED_ABILITIES_NAME, Caster(),
            amount=Const(amount), max_level=max_level)

    vrai_arbre = TOTE.talons_used_abilities_tree
    try:
        # `increment_2` : `level = Formulas@+0x20 = Direct(1)` remplace par `Direct(2)`.
        TOTE.talons_used_abilities_tree = _arbre(2, None)
        out["increment_2"] = rejeu_porte(cap, caster_id, target_id, ability_type, owner_id)
        # `avec_cap` : `maxLevel = NULL` remplace par un clamp a 1 (le litteral natif est NULL).
        TOTE.talons_used_abilities_tree = _arbre(1, Const(1))
        out["avec_cap"] = rejeu_porte(cap, caster_id, target_id, ability_type, owner_id)
    finally:
        TOTE.talons_used_abilities_tree = vrai_arbre
    return out


def gates_forges(cap, owner_id, ally_id, foe_id):
    """Les trois volets du `CreateTrigger` que le LIVE ne separe pas, evalues OFFLINE sur l'etat
    capture : `matches` doit rendre FAUX pour un acteur ENNEMI, pour un acteur sans `Hero`, et pour
    un acteur `MachineOfWar`. Les deux derniers sont obtenus en MUTANT la liste de traits de l'allie
    (l'etat est une copie locale : rien n'est ecrit live)."""
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.talons_of_the_emperor import (
        TalonsOfTheEmperorUsedAbilitiesAbility as A)

    st = etat_porte(cap)
    trig = A(int(owner_id))

    def _ev(actor):
        # `On(0xe = UnitPostAbility)` : `actor` = le caster de l'ability qui se ferme ; ni `ranged`
        # ni `profile` ne sont lus par ce trigger (aucun noeud de profil dans son `CreateTrigger`).
        return TriggerEvent(event_id=14, actor_id=int(actor), target_id=int(actor),
                            ranged=False, profile=None, ability_type=MOMENT_SHACKLE)

    def _traits(uid):
        e = st.get_entity(int(uid))
        sc = e.get_component(StatsComponent) if e is not None else None
        return sc.ctx if sc is not None else None

    res = {"allie_hero": bool(trig.matches(st, _ev(ally_id))),
           "ennemi": bool(trig.matches(st, _ev(foe_id)))}
    ctx = _traits(ally_id)
    if ctx is None:
        res["sans_hero"] = None
        res["machine_of_war"] = None
        return res
    orig = list(ctx.traits or [])
    try:
        ctx.traits = [t for t in orig if t != "Hero"]
        res["sans_hero"] = bool(trig.matches(st, _ev(ally_id)))
        ctx.traits = list(orig) + ["MachineOfWar"]
        res["machine_of_war"] = bool(trig.matches(st, _ev(ally_id)))
    finally:
        ctx.traits = orig
    return res


# ------------------------------------------------------------------ pilotage

def _endturn(sid, rid):
    return _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _rendre_la_main(sid, rid, me, max_steps=8):
    for _ in range(max_steps):
        _endturn(sid, rid)
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        if dv.get("currentPlayer") == me:
            return dv
    return _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def _cast(state_file, rid, cid, tid, aid):
    return _duel(["act", "ability", "--caster", str(cid), "--ability", str(aid),
                  "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])


def _degats(sortie, cid, aid):
    return [(int(t), int(a), int(pr))
            for _e, at, t, a, pr, ab in RE_DMG.findall(sortie or "")
            if int(ab) == int(aid) and int(at) == int(cid)]


def mesure_chaine(sid, state_file, seed, garder=False):
    rid = build(state_file, seed, "chaine")
    if rid is None:
        return None
    try:
        u, dv = unites(sid, rid)
        assert_montage(u, "chaine")
        me = u[CASTER]["owner"]
        if dv.get("currentPlayer") != me:
            _rendre_la_main(sid, rid, me)
            u, dv = unites(sid, rid)
        cid, tid = u[CASTER]["id"], u[FOE]["id"]
        aid_ally = u[ALLY_CASTER]["id"]
        c0 = compteur_live(u)
        cap0 = capture(sid, rid)

        # --- LIVE 1 : l'allie caste son active (SELF-CAST) -------------------------------------
        r1 = _cast(state_file, rid, aid_ally, aid_ally, MOMENT_SHACKLE)
        if r1.returncode != 0:
            raise SystemExit("cast ALLIE en echec (rc=%s) : %s"
                             % (r1.returncode, (r1.stdout or "")[-600:]))
        u, dv = unites(sid, rid)
        c1 = compteur_live(u)
        cap1 = capture(sid, rid)

        ent = _ability_entry(u[CASTER], TALONS)
        if not (ent and ent.get("usable") and not ent.get("disabled") and not ent.get("cooldown")):
            raise SystemExit("1195 NON castable au moment voulu : %r -- montage sterile" % (ent,))

        # --- PORT-A : le compteur, depuis cap0 -------------------------------------------------
        portA = contre_epreuves(cap0, aid_ally, aid_ally, MOMENT_SHACKLE, cid)
        # --- PORT-B : le degat + le 2e increment, depuis cap1 -----------------------------------
        portB = contre_epreuves(cap1, cid, tid, TALONS, cid)

        # --- LIVE 2 : le porteur caste 1195 ----------------------------------------------------
        r2 = _cast(state_file, rid, cid, tid, TALONS)
        seq_n = _degats(r2.stdout, cid, TALONS)
        u2, _ = unites(sid, rid)
        c2 = compteur_live(u2)

        forges = gates_forges(cap0, cid, aid_ally, tid)
        return {"regime": "chaine", "rid": rid, "caster": cid, "cible": tid, "allie": aid_ally,
                "compteurs_live": {"c0": c0, "apres_allie": c1, "apres_talons": c2},
                "portA": portA, "portB": portB, "forges": forges,
                "natif_talons": {"seq": [(t, a) for t, a, _p in seq_n],
                                 "profils": sorted({p for _t, _a, p in seq_n}),
                                 "total": sum(a for _t, a, _p in seq_n),
                                 "rc": r2.returncode,
                                 "out": (r2.stdout or "")[-1200:] + (r2.stderr or "")[-400:]}}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def mesure_normale(sid, state_file, seed, garder=False):
    rid = build(state_file, seed, "attaque_normale")
    if rid is None:
        return None
    try:
        u, dv = unites(sid, rid)
        assert_montage(u, "attaque_normale")
        me = u[CASTER]["owner"]
        if dv.get("currentPlayer") != me:
            _rendre_la_main(sid, rid, me)
            u, dv = unites(sid, rid)
        cid, tid = u[CASTER]["id"], u[FOE]["id"]
        nid = _normal_id(u[CASTER])
        if nid is None:
            raise SystemExit("attaque normale CONCRETE introuvable sur %s -- regime sterile" % CASTER)
        c0 = compteur_live(u)
        cap0 = capture(sid, rid)
        port = contre_epreuves(cap0, cid, tid, nid, cid)
        r = _cast(state_file, rid, cid, tid, nid)
        seq_n = _degats(r.stdout, cid, nid)
        u2, _ = unites(sid, rid)
        c1 = compteur_live(u2)
        return {"regime": "attaque_normale", "rid": rid, "caster": cid, "cible": tid,
                "normal_id": nid,
                "compteurs_live": {"c0": c0, "apres_attaque": c1},
                "port": port,
                "natif": {"coups": len(seq_n), "total": sum(a for _t, a, _p in seq_n),
                          "rc": r.returncode,
                          "out": (r.stdout or "")[-900:] + (r.stderr or "")[-300:]}}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


# ------------------------------------------------------------------ rapport

def rapport_chaine(m) -> bool:
    ok = True
    cl = m["compteurs_live"]
    print("[521r1:chaine] runner=%s porteur=u%s allie=u%s cible=u%s"
          % (m["rid"], m["caster"], m["allie"], m["cible"]))
    print("  compteur LIVE 1420 : depart=%s | apres cast ALLIE=%s | apres cast 1195=%s"
          % (cl["c0"], cl["apres_allie"], cl["apres_talons"]))

    if cl["c0"] != 0:
        print("  MONTAGE : compteur de depart %s != 0 -- le regime ne mesure pas ce qu'il croit"
              % cl["c0"])
        ok = False
    # --- etage 1 : le cast ALLIE fait-il monter le compteur ? --------------------------------
    a = m["portA"]
    print("  [A] cast allie 1184 : natif %s -> %s | port %s -> %s"
          % (cl["c0"], cl["apres_allie"], a["ref"]["compteur_avant"], a["ref"]["compteur_apres"]))
    if cl["apres_allie"] is None or a["ref"]["compteur_apres"] != cl["apres_allie"]:
        print("      ECART sur le compteur apres le cast allie")
        ok = False
    if cl["apres_allie"] == cl["c0"]:
        print("      REGIME DEGENERE : le natif lui-meme n'a pas bouge -- rien n'est mesure")
        ok = False
    # `avec_cap` n'a RIEN a discriminer en [A] (une 1re pose a 1 tient sous un cap de 1) : c'est en
    # [B], sur le 2e increment, qu'un cap mordrait. On ne l'exige donc PAS ici.
    for cle in ("sans_registre", "increment_2"):
        if a[cle]["compteur_apres"] == a["ref"]["compteur_apres"]:
            print("      CONTRE-EPREUVE MUETTE : `%s` rend le meme compteur -> ce regime ne mesure"
                  " PAS cette lecture" % cle)
            ok = False
        else:
            print("      contre-epreuve `%s` : compteur %s (au lieu de %s) -- DISCRIMINE"
                  % (cle, a[cle]["compteur_apres"], a["ref"]["compteur_apres"]))

    # --- etage 2 : le degat et le 2e increment ------------------------------------------------
    b = m["portB"]
    n = m["natif_talons"]
    print("  [B] cast 1195 : natif total=%s profils=%s coups=%s | port total=%s coups=%s"
          % (n["total"], n["profils"], len(n["seq"]), b["ref"]["total"], len(b["ref"]["seq"])))
    if not n["seq"]:
        print("      AUCUN coup natif capte -- la mesure de degat est vide")
        ok = False
    elif b["ref"]["seq"] != n["seq"]:
        print("      ECART coup par coup : natif=%r port=%r" % (n["seq"], b["ref"]["seq"]))
        ok = False
    if n["profils"] not in ([], [DP_POWER]):
        print("      profil natif inattendu %s (le regime vise la branche `else` = Power)"
              % n["profils"])
    print("      compteur apres 1195 : natif %s | port %s"
          % (cl["apres_talons"], b["ref"]["compteur_apres"]))
    if cl["apres_talons"] is None or b["ref"]["compteur_apres"] != cl["apres_talons"]:
        print("      ECART sur le 2e increment (branche IncreaseEffectLevel)")
        ok = False
    if b["ref"]["used_abilities_level"] != cl["apres_allie"]:
        print("      le degat a lu le compteur %s, or il valait %s au moment du cast"
              % (b["ref"]["used_abilities_level"], cl["apres_allie"]))
        ok = False
    # En [B] le compteur part de 1 : les TROIS lectures du `CreateBehaviour` mordent ici -- retirer
    # l'inscription (1), incrementer de 2 (3 au lieu de 2), ou poser le cap que le natif n'a PAS (1).
    for cle in ("sans_registre", "increment_2", "avec_cap"):
        if b[cle]["compteur_apres"] == b["ref"]["compteur_apres"]:
            print("      CONTRE-EPREUVE MUETTE en [B] : `%s` rend le meme compteur (%s)"
                  % (cle, b[cle]["compteur_apres"]))
            ok = False
        else:
            print("      contre-epreuve `%s` : compteur %s (au lieu de %s) -- DISCRIMINE"
                  % (cle, b[cle]["compteur_apres"], b["ref"]["compteur_apres"]))

    # --- etage 3 : les gates forges -----------------------------------------------------------
    f = m["forges"]
    print("  [C] gates OFFLINE : allie Hero=%s | ennemi=%s | sans Hero=%s | MachineOfWar=%s"
          % (f["allie_hero"], f["ennemi"], f["sans_hero"], f["machine_of_war"]))
    if f["allie_hero"] is not True:
        print("      le cas NOMINAL ne matche pas -- les trois refus ci-dessous ne prouveraient rien")
        ok = False
    for cle in ("ennemi", "sans_hero", "machine_of_war"):
        if f[cle] is not False:
            print("      gate `%s` NON respecte (matches=%r)" % (cle, f[cle]))
            ok = False
    return ok


def rapport_normale(m) -> bool:
    ok = True
    cl = m["compteurs_live"]
    p = m["port"]
    print("[521r1:attaque_normale] runner=%s porteur=u%s cible=u%s normal_id=%s"
          % (m["rid"], m["caster"], m["cible"], m["normal_id"]))
    print("  compteur LIVE 1420 : depart=%s | apres ATTAQUE NORMALE=%s (natif)"
          % (cl["c0"], cl["apres_attaque"]))
    print("  port : %s -> %s | coups natifs=%s"
          % (p["ref"]["compteur_avant"], p["ref"]["compteur_apres"], m["natif"]["coups"]))
    if m["natif"]["coups"] == 0:
        print("  AUCUN coup natif : l'attaque n'a pas eu lieu -- le temoin ne temoigne de rien")
        ok = False
    if cl["apres_attaque"] != cl["c0"]:
        print("  le NATIF a fait monter le compteur sur une attaque NORMALE -- lecture du gate"
              " `IsActiveAbilityCountedAsUsed` a revoir")
        ok = False
    if p["ref"]["compteur_apres"] != cl["apres_attaque"]:
        print("  ECART : le port a fait monter le compteur alors que le natif ne l'a pas fait")
        ok = False
    # La contre-epreuve qui rend ce temoin NON TRIVIAL : si le gate est force a VRAI, le compteur
    # DOIT monter -- sinon ce regime ne mesure pas le gate, seulement l'absence d'inscription.
    forces = p["sans_gate_compte"]["compteur_apres"]
    if forces == p["ref"]["compteur_apres"]:
        print("  CONTRE-EPREUVE MUETTE : gate force a VRAI -> compteur toujours %s. Ce regime ne"
              " mesure PAS `IsActiveAbilityCountedAsUsed`." % forces)
        ok = False
    else:
        print("  contre-epreuve `sans_gate_compte` : compteur %s (au lieu de %s) -- DISCRIMINE"
              % (forces, p["ref"]["compteur_apres"]))
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="tous",
                    choices=["tous", "chaine", "attaque_normale"])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    sid = _sid()
    base = a.state_file or os.path.join(PYDIR, "logs", "state_521r1_%d.json" % os.getpid())
    os.makedirs(os.path.dirname(base), exist_ok=True)

    regimes = (["chaine", "attaque_normale"] if a.regime == "tous" else [a.regime])
    ok = True
    for r in regimes:
        sf = base.replace(".json", "_%s.json" % r)
        m = (mesure_chaine(sid, sf, a.seed, a.garder) if r == "chaine"
             else mesure_normale(sid, sf, a.seed, a.garder))
        if m is None:
            print("[521r1:%s] BUILD ECHOUE -- aucune mesure" % r)
            ok = False
            continue
        ok = (rapport_chaine(m) if r == "chaine" else rapport_normale(m)) and ok
    print("\n[521r1] VERDICT : %s" % ("OK" if ok else "ECART"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
