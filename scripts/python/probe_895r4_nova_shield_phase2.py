"""#895-r4 volet (a) -- la PHASE 2 de `NovaShield` (1194 -> triggered 1325) CONFRONTEE au NATIF.

LE CRITERE, en une question binaire : **au tour SUIVANT du boss, l'occupant d'une tuile marquee
prend-il des degats ?** -- posee au NATIF et au PORT sur le MEME etat de depart. Avant ce port,
1325 etait absente de `TRIGGERED_ABILITY_BEHAVIOURS` et 1414 de `PENDING_ATTACK_EFFECTS` : un boss
qui avait caste 1194 n'infligeait RIEN au tour suivant -- aucune erreur, aucun evenement, zero
degat. Meme signature que `#491-r1` et `#503-r1` avant leur port.

MONTAGE, et pourquoi c'est CE montage-la
-----------------------------------------
`--board GB_Riptide_01` (SA carte), boss `tauBossRiptide:4` monte par `--explicit-stats` -- PAS de
greffe : la fiche `case-92` §5bis autorise la greffe quand le playbook est charge PAR ABILITY, mais
la PHASE 2 y ajoute un piege MESURE -- le gate de kit du noeud `TriggerAbility` derive de
`ACTIVE_DERIVED_TRIGGERED_ABILITY_IDS` sur le GAMECONFIG, pas des `ActiveAbilities` patchees dans
la seed BC, donc une phase 2 greffee sur `tauCrisis` rendrait `notCarrying` cote PORT alors que le
natif l'executerait (`UnitFactory$$AddDerivedAbilities` lit la BC).

Le cast est TILE-TARGET whole-board (`TARGETING_OPTIONS` de 1194 = `0x6000040`), donc le boss
`moveNone` peut marquer n'importe ou. On vise une tuile OCCUPEE par un ennemi : la marque `1415`
est posee sur `Filter(Target + AdjacentTiles(Target), NOT IsTrenchTile)` et c'est l'OCCUPANT
COURANT de ces tuiles que la phase 2 frappe.

Les pas sont APPARIES sur `decisionView.currentPlayer`, jamais sur le NOM qu'on donne au pas
(#889-r4), et le RNG offline est re-seede AVANT chaque bascule.

ETAGES
------
  [A] LE CAST (phase 1) sert de PREMISSE, pas d'observable -- il est deja confronte par
      `probe_895_nova_boss_riptide.py` (zone marquee, magnitudes, sources). On le rejoue ici
      seulement pour ARMER la phase 2 des deux cotes.
  [B] LE COUP DIFFERE : delta de PV par unite, natif vs port. C'est L'observable.
  [C] LA MARQUE : les 1415 doivent avoir DISPARU des deux cotes (le `RemoveEffect` du meme arbre).
  [D] ANTI-TAUTOLOGIE : le port a REELLEMENT emis un `AttackWithAttackDamage`. Un `dhp` vide des
      deux cotes serait un accord en regime DEGENERE, pas une confirmation -- on le fait ROUGIR.

ASCII only. SORTIES -> logs/, jamais data/ (#349).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

NOVA_SHIELD = 1194              # ActiveAbilityType.NovaShield
NS_ATTACK = 1325                # TriggeredAbilityType.NovaShield_Attack
NS_PENDING_TARGET = 1415        # EffectType.NovaShield_PendingTarget
NS_PENDING_ATTACK = 1414        # EffectType.NovaShield_PendingAttack
BOARD = "GB_Riptide_01"
BOSS = "tauBossRiptide:4"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/operations/triggers/loki/nova_shield_attack.py",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/runner/abilities/tau.py",
                "scripts/python/engine/entities/selectors/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la PHASE 2 de 1194 -- le coup differe sur les occupants des "
              "tuiles marquees et le retrait des marques 1415.",
}


def _session() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=20).json()["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state_path.unlink()
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=dict(os.environ))
    if not state_path.exists() or proc.returncode != 0:
        print((proc.stderr or proc.stdout or "")[-2000:])
        raise SystemExit("build KO (rc=%s)" % proc.returncode)
    return int(json.loads(state_path.read_text())["runnerId"])


def bind(sid: int):
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec, bg


def seed_offline_rng(state, dump: dict):
    """Cale le MT19937 du port sur celui du natif -- sinon les rolls ne sont pas comparables."""
    from engine.runner.prng import IntBasedMersenneTwister
    mt, mti = (dump or {}).get("mt"), (dump or {}).get("mti")
    if not mt or mti is None:
        raise SystemExit("MONTAGE : `dumpRng` n'a rien rendu -- les rolls ne seraient pas comparables")
    r = IntBasedMersenneTwister()
    r.mt = list(int(x) & 0xFFFFFFFF for x in mt)
    r.mti = int(mti)
    state.rng = r


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or []) if u.get("hp") is not None}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    out = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def _dhp(before: dict, after: dict) -> dict:
    return {str(k): [before[k], after[k]] for k in sorted(before)
            if k in after and after[k] != before[k]}


def _stats_natives(sid, rid, uid: int) -> dict:
    """Les stats RESOLUES d'une unite, cote NATIF (`combatSnapshot.units[].stats`). `{}` = pas
    mesure -- jamais rabattu sur des zeros."""
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60) or {}
    for u in (snap.get("units") or []):
        if int(u.get("entityId") or -1) == int(uid):
            s = u.get("stats") or {}
            return {k: s.get(k) for k in ("attack", "critChance", "critDamage", "blockChance",
                                          "blockDamage", "extraHits", "extraPierce",
                                          "extraPierceRanged")}
    return {}


def _coups_natifs(act: dict) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS du pas, dans l'ORDRE d'emission.

    C'est ce qui DECOMPOSE un ecart de degat par ETAGE au lieu de le laisser en total : un ecart de
    -13 847 PV ne dit pas s'il vient du NOMBRE de coups, des BORNES, ou du crit. La liste, si."""
    out = {}
    for a in (act.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            try:
                tags = json.loads(td) if isinstance(td, str) else td
            except Exception:
                continue
            amt = tags.get("Amount") if isinstance(tags, dict) else None
            if amt is None:
                continue
            tid = tags.get("Target_Id") or tags.get("TargetId") or tags.get("Damage_Target_Id")
            out.setdefault(int(tid) if tid is not None else -1, []).append(int(amt))
    return out


def _types_events(act: dict) -> dict:
    """`{type: n}` -- la VENTILATION des events natifs. Un `_coups_natifs` VIDE ne dit pas si le
    natif n'a pas frappe ou si ce lecteur-la ne sait pas lire ses events : ce compte-ci tranche."""
    out = {}
    for a in (act.get("actions") or []):
        for e in (a.get("events") or []):
            k = str(e.get("type") or e.get("name") or e.get("eventType") or "?")
            out[k] = out.get(k, 0) + 1
    return out


def marques_live(sid, rid) -> list:
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    return sorted((int(t["col"]), int(t["row"])) for t in (tm.get("tiles") or [])
                  if any(int(x.get("effectType") or -1) == NS_PENDING_TARGET
                         for x in (t.get("effects") or [])))


def marques_off(state) -> list:
    return sorted(int(k) for k, effs in (state.effects.by_unit or {}).items()
                  if any(not e.consumed and int(e.effect_type) == NS_PENDING_TARGET for e in effs))


def controle(sid: int, rid: int) -> dict:
    """LE BRAS TEMOIN : aucun cast, une seule bascule de tour. Tout PV perdu ici n'est PAS de la
    phase 2 -- et le `dhp` du bras principal n'est comparable qu'apres l'avoir retranche."""
    bind(sid)
    # ⚠ LE TEMOIN DOIT REJOUER **LE MEME PAS** que le bras principal, pas un pas voisin. Dans le
    # bras principal la mesure est prise sur la bascule `joueur ADVERSE -> joueur du BOSS` (le cast
    # a deja rendu la main). Un temoin qui mesurerait `BOSS -> ADVERSE` ne dirait rien de ce
    # qu'un DEBUT DE TOUR DU BOSS coute aux ennemis. On joue donc DEUX bascules et on ne mesure que
    # la SECONDE.
    dec0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    hp0 = hp_live(sid, rid)
    act = rpc(sid, "applyAction",
              {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 120) or {}
    dec2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    return {"tours": {"depart": dec0.get("currentPlayer"), "apres_1": dec1.get("currentPlayer"),
                      "apres_2": dec2.get("currentPlayer")},
            "dhp_natif": _dhp(hp0, hp_live(sid, rid)),
            "events": _types_events(act)}


def mesure(sid: int, rid: int, cible: tuple) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind(sid)
    state, dec0, bg = load(sid, rid)
    byid = {(int(t["col"]), int(t["row"])): int(t["id"]) for t in bg["tiles"]}
    boss = next((u for u in (dec0.get("units") or [])
                 if "Riptide" in str(u.get("visualId") or "")), None)
    if boss is None:
        raise AssertionError("SCENARIO NON MONTE : le boss est absent du decisionView")
    caster = int(boss["id"])
    mon_joueur = dec0.get("currentPlayer")
    tid = byid[cible]

    # ---- [A] LE CAST, des DEUX cotes (premisse) ---------------------------------------------
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    diag = ABILITY_CLASSES[NOVA_SHIELD]().execute_behaviour(state, caster, tid) or {}
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster, "abilityType": NOVA_SHIELD,
        "targetId": tid}}, 120) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours = {"apres_cast": dec1.get("currentPlayer")}

    m_nat0, m_off0 = marques_live(sid, rid), marques_off(state)
    hp_l0, hp_o0 = hp_live(sid, rid), hp_off(state)

    # ---- [B]/[C] LA BASCULE : le natif rouvre le tour du boss --------------------------------
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    act2 = rpc(sid, "applyAction",
               {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 120) or {}
    dec2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours["apres_endturn_1"] = dec2.get("currentPlayer")
    # Le port joue la MEME bascule, pour le MEME joueur que celui a qui le natif vient de donner la
    # main -- lu APRES la bascule, jamais devine d'apres le nom du pas.
    off = delayed_attack_triggers(state, dec2.get("currentPlayer"))

    hp_l1, hp_o1 = hp_live(sid, rid), hp_off(state)
    return {
        "rid": rid, "caster": caster, "mon_joueur": mon_joueur, "tours": tours,
        "cast_error": cast_error,
        "cast_port": {k: diag.get(k) for k in ("ported", "invalid_target", "marked", "armed")},
        "marques_apres_cast": {"natif": m_nat0, "port": m_off0},
        "marques_apres_phase2": {"natif": marques_live(sid, rid), "port": marques_off(state)},
        "off_phase2": off,
        "emis_port": sorted({n for r in (off or [])
                             for f in ((r or {}).get("fired") or [])
                             for x in (f.get("results") or []) if isinstance(x, dict)
                             for n in (x.get("emis") or [])}),
        "dhp_natif": _dhp(hp_l0, hp_l1),
        "dhp_port": _dhp(hp_o0, hp_o1),
        # LES STATS QUI PILOTENT UN MULTIPLICATEUR DE COUP, lues au canal NATIF. Un ecart de total
        # qui DEPASSE le maximum sans crit ne peut venir ni des bornes ni du tirage : il faut alors
        # savoir ce que le natif a pu appliquer en plus.
        "stats_caster": _stats_natives(sid, rid, caster),
        # ⚠ L'`abilityState` PUBLIE PAR ABILITY, cote NATIF. C'est l'entree que
        # `BaseTriggeredAbility$$MinMaxDamage(this, abilityState)` consomme, et le port la resout
        # par `TRIGGERED_ABILITY_USES_ACTIVE_CONFIG` (1325 -> 1194). Si le natif prenait l'AUTRE
        # branche de `UnitExtensions$$GetAbilityState` (celle du `TriggeredAbilityComponent`), le
        # couple serait DIFFERENT -- et c'est exactement ce qu'un ecart de bornes accuserait.
        "ability_states_caster": [{k: u2.get(k) for k in ("abilityId", "abilityType", "type",
                                                          "level", "multiplier")}
                                  for u in (dec1.get("units") or []) if int(u["id"]) == caster
                                  for u2 in (u.get("abilities") or [])],
        "effets_caster_apres_cast": [x for u in (dec1.get("units") or [])
                                     if int(u["id"]) == caster
                                     for x in (u.get("effects") or [])],
        # LES ETAGES, pas seulement le total (doctrine : jamais fitter un scalaire).
        "coups_natifs": _coups_natifs(act2),
        "events_natifs_types": _types_events(act2),
        "coups_port": {str(d.get("target")): (d.get("etages") or {}).get("per_hit")
                       for r in (off or [])
                       for f in ((r or {}).get("fired") or [])
                       for x in (f.get("results") or []) if isinstance(x, dict)
                       for d in (x.get("damage") or [])},
        "bornes_port": {str(d.get("target")): [(d.get("etages") or {}).get("base_min"),
                                               (d.get("etages") or {}).get("base_max")]
                        for r in (off or [])
                        for f in ((r or {}).get("fired") or [])
                        for x in (f.get("results") or []) if isinstance(x, dict)
                        for d in (x.get("damage") or [])},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--tag", default=str(os.getpid()))
    #: La cible du cast, et le placement adverse : l'ennemi doit se tenir SUR une tuile marquee
    #: (`Target + AdjacentTiles(Target)`), sinon la phase 2 ne frappe personne et le probe mesure
    #: un accord en regime DEGENERE.
    ap.add_argument("--cible", default="6,2")
    ap.add_argument("--a-place", action="append",
                    default=["tauCrisis:6,2", "orksNob:6,3"])
    #: ⚠ `--hp-target` N'EST PAS UN CONFORT, C'EST CE QUI REND LA MESURE POSSIBLE. Mesure du
    #: premier jet, sans lui : la phase 2 native TUE les deux ennemis (`10542 -> 0`, `10040 -> 0`),
    #: la bataille se TERMINE, `decisionView.currentPlayer` rend `None` -- et le port, a qui l'on
    #: passe ce `None`, ne declenche rien. Le probe accusait alors le PORT d'un no-op qui etait en
    #: realite une fin de partie. Gonfler les PV garde la bataille ouverte et le tour comparable.
    ap.add_argument("--hp-target", default="400000")
    #: ⚠ **LE CONTROLE QUI DIT SI LE `dhp` NATIF EST IMPUTABLE A LA PHASE 2.** Meme montage, meme
    #: bascule -- mais SANS CASTER. Tout PV perdu dans ce bras vient d'AUTRE CHOSE (un DoT, une
    #: unite jouee automatiquement au debut du tour, une riposte). Sans lui, un ecart de degat
    #: accuse la phase 2 alors qu'il peut n'en rien devoir : c'est la meme faute que #889-r7
    #: nommait en refusant d'imputer un `dhp` melange.
    ap.add_argument("--controle", action="store_true",
                    help="ne CASTE PAS : mesure ce que la seule bascule de tour coute aux ennemis")
    ap.add_argument("--strict-dhp", action="store_true",
                    help="fait ROUGIR un ecart de TOTAL de PV. A n'employer qu'apres avoir rendu "
                         "le temoin `--controle` NUL -- sinon on accuse le port d'une part qui ne "
                         "lui appartient pas")
    a = ap.parse_args()
    cible = tuple(int(x) for x in a.cible.split(","))

    sid = _session()
    path = LOGS / ("probe_895r4_%s.json" % a.tag)
    args = ["--seed", a.seed, "--board", BOARD,
            "--explicit-stats", BOSS, "--p-units", BOSS,
            "--a-units", ",".join(p.split(":")[0] for p in a.a_place),
            "--place", "%s:3,4" % BOSS]
    for p in a.a_place:
        args += ["--a-place", p]
    if a.hp_target:
        args += ["--hp-target", str(a.hp_target)]
    rid = build(path, args)
    if a.controle:
        try:
            c = controle(sid, rid)
        finally:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        print("[895r4] CONTROLE (aucun cast) : tours=%s | dhp natif=%s | events=%s"
              % (c["tours"], json.dumps(c["dhp_natif"], sort_keys=True),
                 json.dumps(c["events"], sort_keys=True)))
        if c["dhp_natif"]:
            print("        -> LE `dhp` DU BRAS PRINCIPAL EST CONTAMINE : la seule bascule de tour "
                  "coute deja des PV aux ennemis. Aucun ecart de degat n'accuse la phase 2 tant "
                  "que cette part n'est pas retranchee.")
            return 1
        print("        -> TEMOIN PROPRE : la bascule seule ne coute RIEN. Le `dhp` du bras "
              "principal est bien imputable a la phase 2.")
        return 0
    try:
        m = mesure(sid, rid, cible)
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    print("[895r4] runner=%s caster=%s err=%s" % (m["rid"], m["caster"], m["cast_error"]))
    print("[895r4] currentPlayer par pas : %s (mon_joueur=%s)" % (m["tours"], m["mon_joueur"]))
    print("[895r4] [A] cast port : %s" % json.dumps(
        {k: (len(v) if isinstance(v, list) else v) for k, v in m["cast_port"].items()},
        default=str))
    print("[895r4] MARQUES 1415 apres cast : natif=%s port=%s"
          % (m["marques_apres_cast"]["natif"], m["marques_apres_cast"]["port"]))
    print("[895r4] [B] natif dhp = %s" % json.dumps(m["dhp_natif"], sort_keys=True))
    print("[895r4] [B] port  dhp = %s" % json.dumps(m["dhp_port"], sort_keys=True))
    print("[895r4] [B] coups natifs = %s" % json.dumps(m["coups_natifs"], sort_keys=True))
    print("[895r4] [B] events natifs= %s" % json.dumps(m["events_natifs_types"], sort_keys=True))
    print("[895r4] [B] coups port   = %s" % json.dumps(m["coups_port"], sort_keys=True))
    print("[895r4] [B] bornes port  = %s" % json.dumps(m["bornes_port"], sort_keys=True))
    print("[895r4] port emis     = %s" % m["emis_port"])
    print("[895r4] stats caster natif = %s" % json.dumps(m["stats_caster"], sort_keys=True))
    print("[895r4] abilityStates caster = %s"
          % json.dumps(m["ability_states_caster"], sort_keys=True))
    print("[895r4] effets caster apres cast = %s"
          % json.dumps(m["effets_caster_apres_cast"], sort_keys=True)[:400])
    print("[895r4] [C] MARQUES apres phase 2 : natif=%s port=%s"
          % (m["marques_apres_phase2"]["natif"], m["marques_apres_phase2"]["port"]))
    print("[895r4] phase2 port   = %s" % json.dumps(m["off_phase2"], default=str)[:1500])

    out = LOGS / ("probe_895r4_nova_shield_phase2_%s.json" % a.tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")
    print("[895r4] -> %s" % out)

    rc = 0
    # ⚠ LE PAS DOIT ETRE COMPARABLE AVANT D'ETRE COMPARE. Si la bataille s'est TERMINEE pendant la
    # bascule, `currentPlayer` rend `None` et le port ne peut declencher pour PERSONNE : accuser le
    # port serait accuser le mauvais etage (mesure du premier jet, cf. `--hp-target`).
    if m["tours"].get("apres_endturn_1") is None:
        print("[895r4] MONTAGE : `currentPlayer` est None apres la bascule -- la bataille s'est "
              "TERMINEE (la phase 2 native a tue ses cibles). Monter `--hp-target`.")
        return 1
    # [D] ANTI-TAUTOLOGIE d'abord : un accord sur `{}` contre `{}` ne prouve RIEN.
    if not m["dhp_natif"]:
        print("[895r4] REGIME DEGENERE : le natif n'a inflige AUCUN degat -- aucun ennemi ne se "
              "tenait sur une tuile marquee. Replacer une cible (cf. MARQUES ci-dessus).")
        rc = 1
    if "AttackWithAttackDamage" not in (m["emis_port"] or []):
        print("[895r4] [D] LE PORT N'A EMIS AUCUN `AttackWithAttackDamage` -- c'est le no-op "
              "SILENCIEUX que ce port existe pour supprimer.")
        rc = 1
    # ⚠ **LE TOTAL DE PV N'EST PAS COMPARABLE SUR CE MONTAGE, ET C'EST MESURE.** Le bras
    # `--controle` (aucun cast, MEME bascule `ADVERSE -> BOSS`) rend `{"90": -6621, "92": -6069}` :
    # la seule transition de tour coute deja des PV aux ennemis, d'une source qui n'est PAS la
    # phase 2. Comparer les totaux accuserait donc le PORT d'un ecart dont une part lui est
    # etrangere -- exactement l'erreur que `probe_889r7` nomme (<< NON COMPARABLE : le `dhp` de ce
    # pas melange deux etages >>). Le total est IMPRIME, jamais transforme en verdict, sauf sous
    # `--strict-dhp` (a n'utiliser qu'apres avoir rendu le temoin NUL).
    if m["dhp_natif"] == m["dhp_port"]:
        print("[895r4] [B] ACCORD BIT-EXACT sur le delta de PV : %s"
              % json.dumps(m["dhp_natif"], sort_keys=True))
    else:
        print("[895r4] [B] TOTAL NON COMPARABLE (temoin `--controle` NON NUL) : natif %s / port %s. "
              "Ce qui EST confronte ici, c'est QUI est frappe, QUAND, et quelles marques tombent."
              % (json.dumps(m["dhp_natif"], sort_keys=True),
                 json.dumps(m["dhp_port"], sort_keys=True)))
        if a.strict_dhp:
            rc = 1
    # CE QUI RESTE CONFRONTABLE, ET QUI L'EST : l'ENSEMBLE des unites frappees. Il ne depend
    # d'aucune magnitude -- une cible frappee d'un cote et pas de l'autre est un ecart REEL.
    cibles_nat, cibles_port = set(m["dhp_natif"]), set(m["dhp_port"])
    if cibles_nat != cibles_port:
        print("[895r4] [B] ECART D'ENSEMBLE DE CIBLES : natif=%s port=%s -- celui-la ne depend "
              "d'AUCUNE magnitude" % (sorted(cibles_nat), sorted(cibles_port)))
        rc = 1
    else:
        print("[895r4] [B] MEMES CIBLES FRAPPEES des deux cotes : %s" % sorted(cibles_nat))
    if m["marques_apres_phase2"]["natif"] or m["marques_apres_phase2"]["port"]:
        print("[895r4] [C] DES MARQUES 1415 SUBSISTENT : natif=%s port=%s"
              % (m["marques_apres_phase2"]["natif"], m["marques_apres_phase2"]["port"]))
        rc = 1
    print("[895r4] VERDICT : %s" % ("OK" if rc == 0 else "ECART(S)"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
