"""Probe case-224 item 5 -- `CursedPlagueBellAttackAbility` (la RIPOSTE Psychique de Corrodius).

i2 : « Enemy PSYKER units within Corrodius' Contagion aura deal {nrOfHits}x {dmg} Psychic Damage
       TO THEMSELVES each time one of their attacks deals Psychic Damage. »

Ce que le probe MESURE, etage par etage (jamais un scalaire fitte) :

  etape 0  OFFLINE  garde de substrat : la classe est au registre, l'arbre porte les bons parametres
                    (profil / coups / mode `amount` / spread 0 / factory `attack`), les DEUX sources
                    de « Psychic » sont distinctes, et la collision d'espace d'id 1071
                    (`ActiveAbilityType.AnnihilatorBeam` vs `TriggeredAbilityType.CursedPlagueBell`)
                    qui interdit de threader `ability_type` est RE-DERIVEE des tables versionnees.
  etape A  LIVE     un PSYKER du camp joueur, place a distance `d` de Corrodius (camp adverse),
                    porte une attaque NORMALE ; on lit SES PV avant/apres. Le delta EST la riposte
                    (l'attaquant ne subit rien d'autre entre les deux lectures). Le PORT rejoue la
                    MEME attaque sur le MEME etat avec le MEME MT (`dumpRng`) et on confronte.
  etape B  LIVE     le gate PROFIL, sur la MEME unite : `ultraTigurius` a une arme MELEE Physical et
                    une arme RANGED Psychic -> au contact il n'y a PAS de riposte, a distance il y en
                    a une. Rien d'autre ne change.
  etape C  LIVE     le gate `AreEnemies`, par INVERSION DE CAMP (`--allies`) : le meme psyker, mais
                    ALLIE de Corrodius et dans son aura, attaque un ennemi en Psychic -> aucune
                    riposte.

Le palier de rayon est pilote par `--advance N` (le seul levier qui fait monter
`TurnsStarted(Corrodius)`).

⚠ RESULTAT PRINCIPAL DE CE PROBE, et il RENVERSE une lecture : le SEUIL natif vaut EXACTEMENT
`GetCurrentRange(TurnsStarted)`, mesure a DEUX paliers -- range 2 : la cloche part a d=1 et d=2, pas
a d=3 ; range 3 : elle part a d=2 et d=3, pas a d=4. Le comparateur EFFECTIF est donc INCLUSIF, la
ou `case-224-is-in-contagions-of-nurgle-range.md` §2.1 le disait STRICT (lecture litterale du ctor
`AmountIsGreaterAbilityTrigger`, jamais confrontee au natif faute de consommateur porte). Detail de
la tension decompile/mesure : docstring d'`engine/entities/triggers.py::IsInUnitAura`.

L'ATTRIBUTION est le tag natif `Passive_Ability_Type = 1071` appose sur l'evenement de degat -- pas
un delta de PV, qui est CONTAMINE (overwatch et contre-attaques frappent le meme attaquant : mesure,
850 PV imputes a tort a la cloche au premier montage).

Usage (depuis scripts/python) :
    python probe_224_cursed_plague_bell_attack.py --offline-only
    python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 6  --dists 1,2,3
    python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4
    python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3 --allies
    python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2 \
        --psykers ultraTigurius --tgt-dist 1                       # contre-cas de PROFIL (melee)
    python probe_224_cursed_plague_bell_attack.py ... --mutate {registry|range1|strict|profile|enemies}

ASCII only (cp1252). Discipline runner : state-file ABSOLU sous logs/, dispose en fin de passe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
STATE = ROOT / "logs" / "probe_224_cpb_attack.json"

CARRIER = "deathBlightbringer"        # Corrodius -- POOL-HERO rank 17, passif CursedPlagueBell
AURA = 1071                           # EffectType.ContagionsOfNurgle_ArmorReduction1
TRIGGERED = 1071                      # TriggeredAbilityType.CursedPlagueBell (MEME nombre, AUTRE enum)


# --------------------------------------------------------------------------- plomberie RPC

def _sid() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(method: str, arg=None, timeout: int = 90):
    body = json.dumps({"method": method, "args": [arg] if arg is not None else [],
                       "timeout": timeout * 1000}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{_sid()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def build(p_units: str, a_units: str, board: str, seed: str, advance: int = 0,
          hp_player: str = "999999", hp_target: str = "999999") -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    # PV gonfles des DEUX cotes : `--advance` fait jouer l'IA, et sans cela les psykers (ou leurs
    # cibles) meurent avant la mesure -- mesure : a `--advance 10`, deux des trois psykers etaient
    # morts et la passe rendait « aucun cas exerce ».
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", p_units, "--a-units", a_units, "--state-file", str(STATE),
           "--hp-player", hp_player, "--hp-target", hp_target]
    if advance:
        cmd += ["--advance", str(int(advance)), "--maxpump", "400"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        raise SystemExit("build KO: " + (proc.stderr or proc.stdout)[-900:])
    return json.loads(STATE.read_text())["runnerId"]


def dispose(rid: int):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
    except Exception as exc:                                     # noqa: BLE001
        print("dispose KO:", exc)


def move(rid, uid, col, row):
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40)
    return (r.get("actions") or [{}])[0].get("error")


# --------------------------------------------------------------------------- etape 0 (offline)

def offline_guard() -> int:
    """Garde de SUBSTRAT : ce que le port lit, confronte a ce que le decompile / les tables
    versionnees disent. Aucun live."""
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.cursed_plague_bell import (
        CursedPlagueBellAttackAbility, ATTACK_GATE_PROFILE, cursed_plague_bell_attack_hits,
        cursed_plague_bell_attack_tree)
    from engine.runner.abilities.deathguard import cursed_plague_bell_damage_profile
    from engine.entities.effects.aura import aura_range_on_owner_turn
    bad = 0
    classes = [c.__name__ for c in ABILITY_TRIGGERS.get("CursedPlagueBell", ())]
    if "CursedPlagueBellAttackAbility" not in classes:
        print("KO registre:", classes); bad += 1
    # `On(9)` = `EventTriggerType.Attack` (table versionnee), et l'id de la triggered = 1071.
    if CursedPlagueBellAttackAbility.event_id != 9:
        print("KO event_id", CursedPlagueBellAttackAbility.event_id); bad += 1
    if CursedPlagueBellAttackAbility.TRIGGERED_ABILITY_ID != TRIGGERED:
        print("KO TRIGGERED_ABILITY_ID", CursedPlagueBellAttackAbility.TRIGGERED_ABILITY_ID); bad += 1
    # L'arbre = la feuille `AttackWithAttackDamage`, mode `amount`, options natives VIDES.
    tree = cursed_plague_bell_attack_tree(123)
    cfg = GC.ability("CursedPlagueBell") or {}
    want_hits = int((cfg.get("constants") or {}).get("nrOfHits") or 1)
    checks = [("profil", tree.profile, cursed_plague_bell_damage_profile()),
              ("is_melee", tree.is_melee, False),           # attackRangeType = "Ranged"
              ("hits", tree.hits, want_hits),               # GetNumberConstant(0x2f)
              ("spread", tree.amount_spread_pct, 0),        # Nullable<AttackDamageBehaviourOptions> vide
              ("factory", tree.native_factory, "attack"),   # AttackWithAttackDamage (pas Ability)
              ("ability_type", tree.ability_type, None)]    # cf. collision d'espace ci-dessous
    for name, got, want in checks:
        if got != want:
            print(f"KO arbre.{name}: {got!r} != {want!r}"); bad += 1
    if int(tree.amount.evaluate(None)) != 123:              # `DSLFormulas.Get(int)` = noeud constante
        print("KO amount node"); bad += 1
    # Les DEUX sources de « Psychic » sont DISTINCTES au decompile (litteral 0xd du gate vs
    # `GetAffectedDamageProfile().GetValueOrDefault(0xd)` du profil d'attaque). Elles coincident au
    # gameconfig courant -- on l'AFFICHE plutot que de fusionner les deux lectures.
    print("etape 0 profils : gate(litteral 0xd) =", ATTACK_GATE_PROFILE,
          "| attaque(GetAffectedDamageProfile) =", cursed_plague_bell_damage_profile(),
          "| nrOfHits =", cursed_plague_bell_attack_hits())
    # La collision d'espace d'id qui INTERDIT de threader `ability_type` -- re-derivee des tables
    # versionnees, jamais heritee d'un commentaire.
    coll = _enum_name("IdunBattle.Entities.Enum.ActiveAbilityType", TRIGGERED)
    trig = _enum_name("IdunBattle.Entities.Enum.TriggeredAbilityType", TRIGGERED)
    print(f"etape 0 collision d'id {TRIGGERED} : ActiveAbilityType={coll} "
          f"| TriggeredAbilityType={trig}")
    if coll is None or coll == trig:
        print("KO: la collision d'espace n'est plus verifiee -> re-examiner le non-threading"); bad += 1
    # Rayon EFFECTIF du predicat par UNITE. MESURE (etape A, 2 paliers) : il vaut `GetCurrentRange`
    # EXACTEMENT -- le meme que la version d'EQUIPE, et non `range - 1` comme le laissait croire la
    # lecture STRICTE du comparateur (cf. le docstring d'`IsInUnitAura`).
    print("etape 0 rayon effectif (INCLUSIF, mesure) (TurnsStarted 0..7) :",
          [aura_range_on_owner_turn(n) for n in range(8)])
    print("etape 0:", "OK" if bad == 0 else f"{bad} ECARTS")
    return bad


def _enum_name(enum_full_name: str, value: int):
    """Nom d'un membre d'enum lu dans la table VERSIONNEE `data/symbols/<build>/frida/enums.tsv`
    (jamais une constante recopiee dans le probe)."""
    build = (ROOT / "data" / "symbols")
    for d in sorted(p for p in build.iterdir() if p.is_dir()):
        f = d / "frida" / "enums.tsv"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if parts and parts[0] == enum_full_name and len(parts) > 1:
                for kv in parts[1].split(","):
                    k, _, v = kv.partition("=")
                    try:
                        if int(k) == int(value):
                            return v
                    except ValueError:
                        continue
    return None


# --------------------------------------------------------------------------- helpers live/port

def _load(rid, tiles):
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap, board=Board(tiles, adjacency="evenq"))
    return dec, ob, snap, state


def _seed_rng(dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


def _turns_started(state, uid):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    st = getattr(sc.ctx, "stats", None) if sc is not None else None
    return int(st.get_stat(int(StatType.TURNS_STARTED), 0)) if st is not None else None


def _dmg_events_on(act, uid):
    """Les events de DEGAT dont la cible est `uid`, avec leurs tags -- c'est l'ETAGE, pas le
    scalaire. MESURE : le delta de PV brut de l'attaquant est CONTAMINE (un overwatch d'une 3e
    unite lui a coute 850 PV dans le premier montage, `Attacker_Id` = une autre entite). Seuls les
    tags permettent d'attribuer."""
    out = []
    for e in (act.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == uid and "Amount" in td:
            out.append(dict(td))                       # TOUS les tags : on n'ampute pas la mesure
    return out


def _all_dmg_events(act) -> list:
    """Tous les coups de l'action, en forme compacte (attaquant -> cible, montant, profil, source).
    Sert a compter combien d'ATTAQUES natives distinctes une seule action produit."""
    out = []
    for e in (act.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        out.append({"a": td.get("Attacker_Id"), "t": td.get("Target_Id"),
                    "amt": td.get("Amount"), "prof": td.get("DamageProfileType"),
                    "pass": td.get("Passive_Ability_Type"), "ab": td.get("Ability_Type"),
                    "first": td.get("Attack_Is_First_Hit")})
    return out


def _bell_hits_live(act, uid) -> list:
    """LES coups natifs IMPUTES A LA CLOCHE. Attribution par le tag `Passive_Ability_Type == 1071`
    que le natif appose lui-meme sur l'evenement de degat -- c'est l'oracle, pas une inference.
    Recoupement structurel : ces coups ont `Attacker_Id == Target_Id == le psyker` (signature de
    `AttackWithAttackDamage(caster = Actor, target = Actor)`) et `DamageProfileType == 13`."""
    return [e for e in _dmg_events_on(act, uid)
            if e.get("Passive_Ability_Type") == TRIGGERED and e.get("Attacker_Id") == uid]


def _bell_recoil_live(act, uid) -> int:
    return sum(int(e.get("Amount") or 0) for e in _bell_hits_live(act, uid))


def _ranged_hits(visual_id):
    """Nombre de coups de l'arme RANGED du psyker (gameconfig) -- l'hypothese a discriminer quand le
    natif declenche la cloche PLUSIEURS fois pour UNE attaque."""
    import gameconfig as GC
    u = GC.unit(visual_id) or {}
    for w in (u.get("weapons") or []):
        if (w.get("Range") or 0) >= 2:
            return int(w.get("hits") or 1)
    return None


def _port_aura_stage(state, carrier_id, actor_id) -> dict:
    """Les DEUX entrees du predicat, cote port : `MinDistance(Actor, Owner)` et
    `AuraEffectRange(Owner)`, plus le verdict du noeud. Decomposition par etage -- si le natif et le
    port divergent, c'est ici qu'on voit LEQUEL des deux etages devie."""
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.deathguard import is_in_contagions_of_nurgle_range
    ctx = entities_from_state(state, int(carrier_id), None, int(actor_id))
    node = is_in_contagions_of_nurgle_range()
    return {"port_dist": int(node.distance_formula.calculate(ctx)),
            "port_range": int(node.range_formula.calculate(ctx)),
            "port_in_aura": bool(node.should_trigger(ctx))}


def _normal_ability_id(dec, uid):
    """L'id CONCRET de l'attaque normale de l'unite (per-unit, `NormalAttackType` -- jamais 17)."""
    u = next((x for x in (dec.get("units") or []) if x.get("id") == uid), None)
    if u is None:
        return None
    ab = next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
    return None if ab is None else ab.get("id")


# --------------------------------------------------------------------------- scenario live

def _one_case(rid, tiles, byrc, psyker_vid, want_d, carrier_id, mutate, out_rows, tgt_dist=None):
    """UN cas : place `psyker_vid` a distance `want_d` de Corrodius, lui fait porter son attaque
    NORMALE sur un ennemi a portee, et confronte le delta de SES PV (= la riposte) live vs port.

    Rend un dict de resultat, TOUJOURS -- avec `exercised=False` et une `reason` quand le montage
    n'a pas pu etre realise. Un cas non exerce ne compte JAMAIS comme un accord."""
    import hexgeo
    dec, ob, snap, state = _load(rid, tiles)
    me = next((u for u in ob["units"] if u["visualId"] == psyker_vid and not u.get("isDead")), None)
    carrier = next((u for u in ob["units"] if u["squadId"] == carrier_id and not u.get("isDead")),
                   None)
    if me is None or carrier is None:
        return {"unit": psyker_vid, "d": want_d, "exercised": False, "reason": "unite absente/morte"}
    ck = (carrier["col"], carrier["row"])
    my_team = me["teamId"]
    enemies = [u for u in ob["units"] if u["teamId"] != my_team and not u.get("isDead")]
    if not enemies:
        return {"unit": psyker_vid, "d": want_d, "exercised": False, "reason": "aucun ennemi vivant"}
    occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
    occ.discard((me["col"], me["row"]))
    # Tuile a distance EXACTE `want_d` de Corrodius, libre, et d'ou une cible ennemie est a portee
    # (<= 2 : les armes Psychic RANGED du roster portent a 2). On DEPLACE -- on ne subit pas la
    # geometrie de spawn.
    cands = []
    for t in tiles:
        k = (t["col"], t["row"])
        if not t.get("walkable", True) or k in occ:
            continue
        if hexgeo.distance(k, ck) != want_d:
            continue
        # cible la PLUS PROCHE depuis cette tuile : maximise la chance qu'elle soit legale
        # (portee/LOS), et la garde `abilityTargets` plus bas tranche pour de vrai.
        near = sorted(enemies, key=lambda e: hexgeo.distance(k, (e["col"], e["row"])))
        for tgt in near:
            dt = hexgeo.distance(k, (tgt["col"], tgt["row"]))
            # `tgt_dist` FORCE la distance a la cible : 1 = contact -> le natif choisit l'arme
            # MELEE. C'est le levier du contre-cas de PROFIL sur une unite qui porte une arme melee
            # NON-Psychic et une arme ranged Psychic (`ultraTigurius`).
            ok = (dt == int(tgt_dist)) if tgt_dist is not None else (dt <= 2)
            if ok:
                cands.append((t, tgt))
                break
    if not cands:
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": f"aucune tuile libre a d={want_d} du porteur avec une cible a portee"}
    # `applyAction move` REFUSE silencieusement une tuile deja prise -> on essaie les candidates
    # jusqu'a ce que la distance REELLE soit celle voulue, et on refuse un montage degrade.
    got_d, tile, target, err, me2 = None, None, None, None, None
    for t, tg in cands[:8]:
        err = move(rid, me["squadId"], t["col"], t["row"])
        dec, ob, snap, state = _load(rid, tiles)
        me2 = next((u for u in ob["units"] if u["squadId"] == me["squadId"]), None)
        if me2 is None or me2.get("isDead"):
            return {"unit": psyker_vid, "d": want_d, "exercised": False,
                    "reason": f"psyker mort/absent apres deplacement ({err})"}
        got_d = hexgeo.distance((me2["col"], me2["row"]), ck)
        if got_d == want_d:
            tile, target = t, tg
            break
    if tile is None:
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": f"deplacement refuse sur {len(cands[:8])} tuiles ({err}),"
                          f" distance reelle {got_d}"}
    # la cible doit etre VIVANTE et a portee depuis la position REELLE
    target = next((e for e in ob["units"]
                   if e["squadId"] == target["squadId"] and not e.get("isDead")), None)
    if target is None:
        return {"unit": psyker_vid, "d": want_d, "exercised": False, "reason": "cible morte"}
    norm = _normal_ability_id(dec, me["squadId"])
    if norm is None:
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": "pas d'attaque normale dans decisionView"}
    # GARDE DE MONTAGE : la cible doit etre LEGALE depuis la position courante, sans bouger. Sans
    # cette garde, un cast hors portee rend `ok:true` avec DEUX events et ZERO degat -- mesure : le
    # port frappait pour 2428 la ou le natif ne faisait rien, et l'ecart se lisait comme un
    # desaccord du PORT alors que c'etait le MONTAGE qui etait faux.
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": me["squadId"],
                                "abilityType": norm}, 60) or {}
    row_at = next((u for u in (at.get("units") or []) if u.get("unitId") == me["squadId"]), None)
    legal = set()
    for a in ((row_at or {}).get("abilities") or []):
        if a.get("abilityType") in (norm, None):
            for t in (a.get("fromHere") or []):
                legal.add(t.get("targetId"))
    if target["squadId"] not in legal:
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": f"cible {target['visualId']} illegale sans bouger (portee/LOS) -- "
                          f"cibles legales: {sorted(x for x in legal if x is not None)}"}
    hp_before = _hp(state, me["squadId"])
    tgt_before = _hp(state, target["squadId"])
    ts = _turns_started(state, carrier_id)
    dmp = rpc("dumpRng", {"runnerId": rid}, 30)
    if not isinstance(dmp, dict) or "mt" not in dmp:
        return {"unit": psyker_vid, "d": want_d, "exercised": False, "reason": "dumpRng indispo"}
    state.rng = _seed_rng(dmp)
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": me["squadId"], "targetId": target["squadId"],
        "abilityType": norm}}, 60)
    act = (res.get("actions") or [{}])[0]
    if not act.get("ok"):
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": f"attaque live refusee: {act.get('error')}"}
    # Les PV se relisent par `observeBattle` APRES coup : le payload d'`applyAction` est un snapshot
    # PARTIEL (mesure -- il rendait un PV perime pour la cible, ce qui simulait un degat nul).
    ob3 = rpc("observeBattle", {"runnerId": rid}, 40)
    live_hp = {u["squadId"]: u.get("hp") for u in ob3["units"]}
    live_after = live_hp.get(me["squadId"])
    live_tgt_after = live_hp.get(target["squadId"])
    if live_after is None or live_tgt_after is None:
        return {"unit": psyker_vid, "d": want_d, "exercised": False,
                "reason": "PV live illisibles (attaquant ou cible)"}
    if mutate:
        _apply_mutation(mutate)
    fired = _capture_bell()                     # capte les invocations du behaviour PORTE
    try:
        runner.apply(AttackUnitMessage(me["squadId"], target["squadId"]))
    finally:
        _release_bell()
        if mutate:
            _undo_mutation(mutate)
    port_after = _hp(state, me["squadId"])
    port_tgt_after = _hp(state, target["squadId"])
    row = {"unit": psyker_vid, "d": got_d, "ts": ts, "exercised": True,
           "hp_before": int(hp_before), "live_after": int(live_after),
           "port_after": None if port_after is None else int(port_after),
           # L'ETAGE mesure des deux cotes : le recul IMPUTE A LA CLOCHE (natif = degats
           # psyker->psyker dans le flot de l'attaque ; port = total des invocations du behaviour).
           "live_bell": _bell_recoil_live(act, me["squadId"]),
           "live_fires": len(_bell_hits_live(act, me["squadId"])),
           "port_bell": sum(int(f.get("total") or 0) for f in fired),
           "port_fires": len(fired),
           "ranged_hits": _ranged_hits(psyker_vid),
           # profil de l'attaque PRIMAIRE tel que le natif le tague (`DamageProfileType`) : c'est
           # l'entree du gate `CurrentAttackDamageProfilesContain`, pas une deduction depuis l'arme.
           "primary_profiles": sorted({e["prof"] for e in _all_dmg_events(act)
                                       if e.get("a") == me["squadId"] and e.get("pass") is None
                                       and e.get("prof") is not None}),
           # Les deltas de PV BRUTS restent affiches, mais ils ne fondent AUCUN verdict (contamines
           # par overwatch / contre-attaques -- mesure, cf. `_dmg_events_on`).
           "live_recoil": int(hp_before) - int(live_after),
           "port_recoil": None if port_after is None else int(hp_before) - int(port_after),
           # Le volet CIBLE : l'egalite dessus prouve que l'attaque primaire est jouee au MEME rang
           # RNG des deux cotes -- sans elle, un accord sur le recul ne vaudrait rien.
           "live_tgt": int(tgt_before) - int(live_tgt_after),
           "port_tgt": (None if port_tgt_after is None
                        else int(tgt_before) - int(port_tgt_after)),
           "target": target["visualId"], "target_id": target["squadId"],
           "on_attacker": _dmg_events_on(act, me["squadId"]),
           "all_dmg": _all_dmg_events(act),
           "raw": {"att_id": me["squadId"], "carrier_id": carrier_id,
                   "att_pos": [me2["col"], me2["row"]], "carrier_pos": [ck[0], ck[1]],
                   "att_before": int(hp_before), "att_live": int(live_after),
                   "att_port": port_after, "tgt_before": int(tgt_before),
                   "tgt_live": int(live_tgt_after), "tgt_port": port_tgt_after,
                   "ability": norm, "events": len((act.get("events") or [])),
                   # ETAGE du predicat cote PORT, sur l'etat AVANT l'attaque : la distance que
                   # `MinDistance` calcule et le verdict du noeud. C'est ce qu'il faut confronter
                   # quand le natif et le port ne s'accordent pas sur « dans l'aura ».
                   **_port_aura_stage(state, carrier_id, me["squadId"])}}
    row["agree"] = (row["live_bell"] == row["port_bell"]
                    and row["live_tgt"] == row["port_tgt"])
    out_rows.append(row)
    return row


# ------------------------------------------------------- capture des invocations du behaviour porte

_BELL_SAVE = {}


def _capture_bell():
    """Enveloppe (dans le PROBE, jamais dans le moteur) `execute_behaviour` pour collecter ce que
    la classe portee produit reellement. Le total ainsi collecte est confronte au discriminant natif
    `_bell_recoil_live` -- un accord sur des deltas de PV bruts serait un accord VIDE."""
    import engine.runner.operations.triggers.loki.cursed_plague_bell as C
    fired = []
    orig = C.CursedPlagueBellAttackAbility.execute_behaviour
    _BELL_SAVE["fn"] = orig

    def _wrap(self, state, ev, _orig=orig):
        out = _orig(self, state, ev)
        if out is not None:
            fired.append(out)
        return out
    C.CursedPlagueBellAttackAbility.execute_behaviour = _wrap
    return fired


def _release_bell():
    import engine.runner.operations.triggers.loki.cursed_plague_bell as C
    fn = _BELL_SAVE.pop("fn", None)
    if fn is not None:
        C.CursedPlagueBellAttackAbility.execute_behaviour = fn


# --------------------------------------------------------------------------- mutations du fix

_MUT_SAVE = {}


def _apply_mutation(kind: str):
    """Contre-epreuve : on NEUTRALISE un etage du port et on rejoue la MEME mesure. Une mutation qui
    ne fait rouge aucun cas est un accord VIDE -- c'est ce que ces mutations verifient."""
    import engine.runner.operations.triggers.dispatch.registry as R
    import engine.entities.effects.aura as AU
    import engine.entities.triggers as TR
    if kind == "registry":
        _MUT_SAVE["registry"] = list(R.ABILITY_TRIGGERS["CursedPlagueBell"])
        R.ABILITY_TRIGGERS["CursedPlagueBell"] = [
            c for c in R.ABILITY_TRIGGERS["CursedPlagueBell"]
            if c.__name__ != "CursedPlagueBellAttackAbility"]
    elif kind == "range1":                       # rayon d'aura FIGE a 1 (les paliers disparaissent)
        _MUT_SAVE["range1"] = AU.aura_range_on_owner_turn
        AU.aura_range_on_owner_turn = lambda n: 1
    elif kind == "strict":
        # LA contre-epreuve du renversement de case-224 item 5 : on REMET le comparateur STRICT
        # (`dist < range`, la lecture litterale du decompile). Signature attendue : rouge
        # EXACTEMENT sur les cas ou `d == range`, vert partout ailleurs.
        _MUT_SAVE["strict"] = TR.IsInUnitAura.should_trigger
        TR.IsInUnitAura.should_trigger = lambda self, ctx: (
            int(self.distance_formula.calculate(ctx)) < int(self.range_formula.calculate(ctx)))
    elif kind == "profile":                      # gate `CurrentAttackDamageProfilesContain` RETIRE
        import engine.runner.operations.triggers.loki.cursed_plague_bell as C
        orig = C.CursedPlagueBellAttackAbility.matches
        _MUT_SAVE["profile"] = orig

        def _no_profile_gate(self, state, ev, _orig=orig):
            """Rend le gate de profil TOUJOURS vrai (on injecte le profil attendu dans l'evenement),
            au lieu de le rendre toujours faux -- une mutation qui ETEINT le trigger se confondrait
            avec `registry` et ne prouverait rien de ce gate-la."""
            saved = (ev.profiles, ev.profile)
            ev.profiles = set(ev.profiles or ()) | {C.ATTACK_GATE_PROFILE}
            try:
                return _orig(self, state, ev)
            finally:
                ev.profiles, ev.profile = saved
        C.CursedPlagueBellAttackAbility.matches = _no_profile_gate
    elif kind == "enemies":                      # gate `AreEnemies` neutralise
        import engine.runner.operations.triggers.loki.cursed_plague_bell as C
        from engine.runner.components import OwnerComponent
        orig = C.CursedPlagueBellAttackAbility.matches
        _MUT_SAVE["enemies"] = orig

        def _no_enemy_gate(self, state, ev, _orig=orig):
            """Neutralise le SEUL comparateur du gate (`aoc.team == ooc.team`) en donnant a l'owner
            une equipe qui n'existe pas, le temps de l'appel. Cible : aucun autre conjoint de
            `matches` ne lit l'equipe (le noeud d'aura ne consomme que traits/stats/positions)."""
            e = state.get_entity(self.owner_id)
            oc = e.get_component(OwnerComponent) if e is not None else None
            if oc is None:
                return _orig(self, state, ev)
            saved = oc.team
            oc.team = -999
            try:
                return _orig(self, state, ev)
            finally:
                oc.team = saved
        C.CursedPlagueBellAttackAbility.matches = _no_enemy_gate
    else:
        raise SystemExit("mutation inconnue: " + kind)


def _undo_mutation(kind: str):
    import engine.runner.operations.triggers.dispatch.registry as R
    import engine.entities.effects.aura as AU
    import engine.entities.triggers as TR
    if kind == "registry":
        R.ABILITY_TRIGGERS["CursedPlagueBell"] = _MUT_SAVE.pop("registry")
    elif kind == "range1":
        AU.aura_range_on_owner_turn = _MUT_SAVE.pop("range1")
    elif kind == "strict":
        TR.IsInUnitAura.should_trigger = _MUT_SAVE.pop("strict")
    elif kind == "profile":
        import engine.runner.operations.triggers.loki.cursed_plague_bell as C
        C.CursedPlagueBellAttackAbility.matches = _MUT_SAVE.pop("profile")
    elif kind == "enemies":
        import engine.runner.operations.triggers.loki.cursed_plague_bell as C
        C.CursedPlagueBellAttackAbility.matches = _MUT_SAVE.pop("enemies")


# --------------------------------------------------------------------------- pilote

def scenario(args) -> int:
    """Camp JOUEUR = les psykers (pilotables par `applyAction`) ; camp ADVERSE = Corrodius + tanks.
    `--allies` INVERSE : Corrodius passe du cote joueur -> le psyker devient son ALLIE, ce qui exerce
    le gate `AreEnemies` sans dependre de l'IA."""
    psykers = args.psykers.split(",")
    if args.allies:
        p_units = CARRIER + "," + args.psykers
        a_units = args.tanks
    else:
        p_units = args.psykers
        a_units = CARRIER + "," + args.tanks
    rid = build(p_units, a_units, args.board, args.seed, advance=args.advance)
    print("runner", rid, "| advance", args.advance, "| allies", args.allies,
          "| mutate", args.mutate or "-")
    bad = 0
    rows = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = bg["tiles"]
        byrc = {(t["col"], t["row"]): t for t in tiles}
        dec, ob, snap, state = _load(rid, tiles)
        carrier = next((u for u in ob["units"] if u["visualId"] == CARRIER
                        and not u.get("isDead")), None)
        if carrier is None:
            print("KO: Corrodius absent du plateau"); return 1
        cid = carrier["squadId"]
        ts = _turns_started(state, cid)
        from engine.entities.effects.aura import aura_range_on_owner_turn
        rng_now = aura_range_on_owner_turn(int(ts or 0))
        print(f"Corrodius id={cid} team={carrier['teamId']} TurnsStarted={ts}"
              f" -> range={rng_now}, rayon EFFECTIF (mesure : INCLUSIF) = {rng_now}")
        # Un cas par (psyker, distance) : chaque unite ne peut attaquer QU'UNE fois par tour, donc
        # on balaie les distances en changeant d'unite plutot qu'en changeant de tour (ce qui
        # ferait bouger TurnsStarted, donc le palier).
        plan = []
        for i, d in enumerate(int(x) for x in args.dists.split(",")):
            if i < len(psykers):
                plan.append((psykers[i], d))
        for vid, d in plan:
            r = _one_case(rid, tiles, byrc, vid, d, cid, args.mutate, rows, args.tgt_dist)
            if not r.get("exercised"):
                print(f"NON-EXERCE  {vid} d={d} : {r.get('reason')}")
                continue
            # Attente = la CONJONCTION des trois gates que ce montage sait faire varier :
            #  * `AreEnemies` (faux en mode `--allies`) ;
            #  * `CurrentAttackDamageProfilesContain(Psychic)` -- lu sur le TAG natif du coup
            #    primaire, pas deduit de l'arme (`--tgt-dist 1` force la melee, donc le profil
            #    melee de l'unite : Physical pour `ultraTigurius`) ;
            #  * la portee d'aura (`d <= range`).
            psychic = 13 in (r["primary_profiles"] or [])
            if args.allies:
                expect = "aucune (gate AreEnemies)"
            elif not psychic:
                expect = f"aucune (gate PROFIL : primaire={r['primary_profiles']})"
            else:
                expect = "riposte" if d <= rng_now else "aucune (hors aura)"
            flag = "OK " if r["agree"] else "KO "
            if not r["agree"]:
                bad += 1
            print(f"{flag}{vid} d={r['d']} TurnsStarted={r['ts']} (attendu {expect})"
                  f" | CLOCHE natif={r['live_bell']} ({r['live_fires']} fires)"
                  f" port={r['port_bell']} ({r['port_fires']} fires)"
                  f" | rangedHits={r['ranged_hits']} | attaque primaire sur {r['target']}"
                  f" natif={r['live_tgt']} port={r['port_tgt']}")
            if not r["agree"] or args.verbose:
                print("    brut:", json.dumps(r["raw"], default=str))
                print("    TOUS les coups de l'action:",
                      json.dumps(r["all_dmg"], default=str)[:1800])
        ex = [r for r in rows if r.get("exercised")]
        print(f"etape A : {len(ex)} cas EXERCES / {len(plan)} tentes, {bad} desaccords")
        if not ex:
            print("VERDICT: NON CONCLUANT -- aucun cas exerce (accord vide refuse)")
            return 1
        # Le verdict ne se contente pas de l'accord : il exige qu'un cas ait REELLEMENT porte une
        # riposte OU que le palier attendu soit 0 (rayon effectif nul), sinon la mesure ne
        # discrimine rien.
        fired = [r for r in ex if r["live_bell"] > 0]
        in_aura = [r for r in ex if r["d"] <= rng_now]
        if args.allies:
            # Le montage n'a de valeur QUE si au moins un cas etait DANS l'aura : sinon c'est la
            # geometrie, pas le gate `AreEnemies`, qui explique l'absence de riposte.
            if not in_aura:
                print("VERDICT: NON CONCLUANT -- aucun cas dans l'aura : le gate AreEnemies n'est"
                      " pas ce qui decide, l'accord serait vide")
                return 1
            if fired:
                print("KO: le natif a riposte sur un ALLIE du porteur"); bad += 1
            else:
                print(f"etape C (gate AreEnemies) : {len(in_aura)} cas DANS l'aura, 0 riposte des"
                      " DEUX cotes -- le gate mord")
        else:
            # Un cas est DISCRIMINANT-POSITIF s'il reunit les trois gates : dans l'aura, ennemi, et
            # attaque primaire de profil Psychic. Sans un tel cas, l'accord ne prouve rien.
            positives = [r for r in ex if r["d"] <= rng_now and 13 in (r["primary_profiles"] or [])]
            if positives and not fired:
                print("KO: un cas reunissait les trois gates et le natif n'a pas riposte"); bad += 1
            elif not positives:
                gates = [r for r in ex if 13 not in (r["primary_profiles"] or [])]
                if gates:
                    print(f"etape B (gate PROFIL) : {len(gates)} cas DANS l'aura avec une attaque"
                          " NON-Psychic, 0 riposte des DEUX cotes -- le gate mord")
                else:
                    print("VERDICT: NON CONCLUANT -- aucun cas discriminant-positif (aucun cas ne"
                          " reunit aura + ennemi + profil Psychic), l'accord serait vide")
                    return 1
        print("VERDICT:", "OK" if bad == 0 else f"{bad} DESACCORDS")
    finally:
        if not args.keep:
            dispose(rid)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--psykers", default="astraPrimarisPsy,bloodMephiston,spaceStormcaller",
                    help="psykers du camp pilote, un par distance de --dists")
    ap.add_argument("--tanks", default="custoKyrus,astraBullgryn,ultraTitus")
    ap.add_argument("--dists", default="1,2,3")
    ap.add_argument("--advance", type=int, default=0,
                    help="tours joues AVANT la mesure -- seul levier qui fait monter "
                         "TurnsStarted(Corrodius), donc le palier de rayon")
    ap.add_argument("--allies", action="store_true",
                    help="Corrodius du cote JOUEUR -> exerce le gate AreEnemies")
    ap.add_argument("--mutate", default=None,
                    choices=["registry", "range1", "strict", "profile", "enemies"])
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--tgt-dist", type=int, default=None,
                    help="distance EXACTE psyker->cible (1 = contact -> le natif prend l'arme "
                         "MELEE) ; defaut : la cible la plus proche a <= 2")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    bad = offline_guard()
    if not args.offline_only:
        bad += scenario(args)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
