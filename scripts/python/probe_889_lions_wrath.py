"""#889 -- `1217 TheLionsWrath` (`darkaBossLion` « le Lion ») confrontee au NATIF, les DEUX phases.

CE QUE CE PROBE DISCRIMINE, et ce qu'il ne discrimine pas -- a lire AVANT ses verts :

  * [A] LE CAST (phase 1). Trois observables INDEPENDANTS : le DEGAT (profil `Power`,
    `nrOfHits = 2`), les TROIS effets poses (1522 sur le CASTER, 27 + 1521 sur la CIBLE) et le
    fait que les deux bonds soient sous `IfAlive(Target)`. Un port qui poserait les bonds hors du
    `If` accorderait sur une cible survivante et divergerait sur une cible tuee -- le bras
    `--step kill` force ce regime en ecrasant les bornes de degat.
  * [B] LE CRIT DU SECOND COUP. `chance = 100` et `AmountIsEqual(CurrentHitIndex(), 1)` : le coup
    d'index 1 doit criter, le coup d'index 0 non. C'est le SEUL etage ou le threading
    `att_ctx["hit_index"]` se voit. ⚠ Il EXIGE `CouldCrit` vrai chez le caster
    (`GetStat(9) >= 1 && GetStat(10) > 0`) : le palier `:4` du Lion porte `CritChance 20` /
    `CritDamage 4735`, le palier `:1` **NON** -- sur `:1` cet etage serait DEGENERE (les deux
    modeles rendraient `0` par construction) et son accord ne prouverait RIEN.
  * [C] LA PHASE 2. Le coup differe part au DEBUT DU TOUR SUIVANT DU LION (`IsTurnOf(bonded)`),
    avec le SECOND jeu (`minDmg_2`/`maxDmg_2`/`damageProfile_2 = Piercing`/`nrOfHits_2`), et le
    1522 est retire **HORS** du `If(IsAlive & IsAdjacent)`. Le temoin negatif est le tour ENNEMI
    intercalaire : rien ne doit partir.

  NON DISCRIMINE, et il faut le dire :
  * le champ `+0x08` des `AttackDamageBehaviourOptions` (une `List<int>{1}`) est NON RESOLU
    (residu #889-r2) -- si le natif lui prete un effet, ce probe le verrait comme un ecart de
    DEGAT sans pouvoir le nommer ;
  * la branche `On(0x25 = UnitRemoved)` du second `Triggered()` n'est PAS exercee : `On(0x25)` n'est
    publie que par `RemoveUnitOperation`, qu'aucune ability du roster ne declenche ici ;
  * `Overwatch` et `Parry` du Lion ne sont pas neutralises -- ils ne mordent pas sur un cast
    (aucun deplacement du caster : le Lion est `moveNone`), mais ils mordraient sur une sequence
    d'attaques normales, que ce probe ne joue pas.

MONTAGE. `--board CE6_boss` (SA carte : 7x10, 65 tuiles jouables, 8 points de spawn cote boss --
contre 7x9 / 63 / 5 pour `MC1_67`), boss au palier `:4`, cible ADJACENTE par `--a-place` : le Lion
est `moveNone`, donc c'est la CIBLE qu'on deplace, jamais « bloque par la geometrie de spawn ».
⚠ `TACTICUS_ALLOW_ROSTER_DEFICIT=1` est POSE PAR CE PROBE : le jeu publie le boss sous l'id
d'entite REMAPPE `GuildBoss12Boss1DarkaLion`, que le garde de roster de `rl_duel` compare a
`darkaBossLion` -- le refus est un FAUX NEGATIF connu, et le boss EST en bataille (verifie ici par
la presence de son entite dans le `decisionView`).

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

THE_LIONS_WRATH = 1217          # ActiveAbilityType.TheLionsWrath
LW_EXTRA_CRIT = 1522            # EffectType.TheLionsWrath_ExtraCritChance
LW_PENDING_ATTACK = 1521        # EffectType.TheLionsWrath_PendingAttack
TAUNTED = 27                    # EffectType.Taunted_OnlySpecificTargets
LW_ATTACK = 1520                # TriggeredAbilityType.TheLionsWrath_PendingAttack
BOARD = "CE6_boss"              # LA carte du boss (gameconfig battles[].BoardId)
BOSS = "darkaBossLion:4"        # palier HAUT : le seul a porter un CritChance non nul

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/darkangels.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/combat.py",
                "scripts/python/engine/runner/abilities/behaviours/effects.py",
                "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
                "scripts/python/engine/runner/operations/damage.py",
                "scripts/python/engine/runner/operations/damage_ops/**",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/loki/lions_wrath_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/entities/effects/loki/lions_wrath.py",
                "scripts/python/engine/entities/effects/factory.py",
                "scripts/python/engine/entities/effects/__init__.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF les DEUX phases de 1217 (cast + attaque differee), le canal "
              "crit-chance par INDEX DE COUP (att_ctx['hit_index']) et la structure `IfAlive` du "
              "cast. C'est le seul porteur porte du noeud `AmountIsEqual(CurrentHitIndex(), 1)`.",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Le boss arrive sous un id d'entite REMAPPE -> le garde de roster rend un FAUX NEGATIF.
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2000:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind_transport(sid: int):
    """LIE le transport ambiant que `load_state` utilise pour tirer `unitAbilityStates`.
    SANS LUI le kit DECLENCHE du caster est ampute (`1520` est une ability DERIVEE d'une active,
    absente du kit gameconfig) et la phase 2 refuserait l'attaquant -- meme cause que #513."""
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    abst = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles, ability_states=abst), dec


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def footprint_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(u["id"])] = effs
    return out


def footprint_off(state) -> dict:
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def rng_dump(sid, rid) -> dict:
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def seed_offline_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def _player_of(state, uid: int):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return None if oc is None else int(oc.player)


def _feet(dec) -> dict:
    """L'EMPREINTE de chaque unite, LUE et non supposee (`UnitComponent._feet`,
    `UnitExtensions$$GetUnitFeet`). Le Lion porte `BigTarget` : ce compte est la seule chose qui
    dise s'il occupe UNE tuile ou plusieurs, et un temoin ou tout le monde rend 1 ne discrimine
    pas -- on imprime donc la VENTILATION, pas un verdict."""
    out = {}
    for u in (dec.get("units") or []):
        f = u.get("feet")
        out[int(u["id"])] = {"visualId": u.get("visualId"), "pos": u.get("pos"),
                             "feet": f, "n": (len(f) if isinstance(f, list) else None)}
    return out


def _coups_natifs(act: dict) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS du pas, dans l'ORDRE d'emission."""
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


def measure(sid: int, seed: str = "777", board: str = BOARD,
            state_name: str = "probe_889_lions_wrath",
            extra_args: list | None = None):
    """Monte le scenario, joue le cast PUIS les deux passages de tour des DEUX cotes."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--explicit-stats", BOSS,
        "--p-units", BOSS,
        "--a-units", "custoVexilusPraetor,orksBigMek",
        # Le Lion est `moveNone` : c'est la CIBLE qu'on colle a lui, jamais l'inverse.
        "--place", "%s:3,3" % BOSS,
        "--a-place", "custoVexilusPraetor:3,4", "--a-place", "orksBigMek:2,2"]
        + list(extra_args or []))

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int) -> dict:
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind_transport(sid)
    dec0 = decision(sid, rid)
    caster = next((u for u in (dec0.get("units") or [])
                   if "DarkaLion" in str(u.get("visualId") or "")), None)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : le Lion est absent du decisionView "
                             "(visualId attendu ~ GuildBoss12Boss1DarkaLion)")
    caster_id = int(caster["id"])
    feet = _feet(dec0)

    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": THE_LIONS_WRATH}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == THE_LIONS_WRATH), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1217 "
                             "(le Lion est moveNone -- rapprocher la cible, pas le caster)")
    target_id = int(from_here[0])

    # ---- OFFLINE : le MEME cast, joue par le port -----------------------------------------
    state, _ = load(sid, rid)
    seed_offline_rng(state, rng_dump(sid, rid))
    off_before = footprint_off(state)
    off_hp0 = hp_off(state)
    res = _apply_active_ability(state, caster_id, target_id, THE_LIONS_WRATH) or {}
    off_cast = delta(off_before, footprint_off(state))
    off_hp1 = hp_off(state)
    mon_joueur = _player_of(state, caster_id)
    joueur_adverse = _player_of(state, target_id)
    diag = res.get("diag") or {}

    # ---- LIVE : le MEME cast, joue par le natif -------------------------------------------
    live_before = footprint_live(dec0)
    live_hp0 = hp_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": THE_LIONS_WRATH,
        "targetId": target_id}}, 90) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = decision(sid, rid)
    live_cast = delta(live_before, footprint_live(dec1))
    live_hp1 = hp_live(sid, rid)
    live_coups_cast = _coups_natifs(act)

    # ---- TOUR ENNEMI : le TEMOIN NEGATIF ---------------------------------------------------
    # ⚠ `tours` -- LE DISCRIMINANT DE #889-r4, et il manquait. Le probe NOMMAIT ses pas
    # (<< TOUR ENNEMI >>, << TOUR DU LION >>) sans jamais LIRE a qui le natif donne la main :
    # `decisionView.currentPlayer`. Or le modele de tour est par EQUIPE (`PickNextUnit`), pas par
    # unite -- si l'equipe du Lion n'a plus d'unite a jouer, le tour bascule DES la fin du cast, et
    # l'`endturn` du pas [C] termine alors le tour de l'ADVERSAIRE au lieu de l'ouvrir. Les deux
    # pas seraient decales d'un cran, et le << temoin negatif >> serait en fait le tour du Lion --
    # ce qui rendrait l'ecart observable SANS qu'aucun des deux moteurs ait tort.
    # Le nom d'un pas n'est pas une mesure : on lit le joueur actif A CHAQUE pas.
    tours = {"apres_cast": dec1.get("currentPlayer")}
    # APPARIEMENT DES PAS (#889-r4). Le natif emet `On(0x15 = TurnStart_DelayedAttacks)` pour le
    # joueur qui PREND la main (`IdunBattle.Operations.StartTurnOperation$$Execute`). Le port doit
    # donc jouer `delayed_attack_triggers` avec CE joueur-la, lu APRES la bascule -- pas avec un
    # joueur devine d'apres le NOM qu'on a donne au pas.
    # ⚠ Et le RNG se re-seede AVANT la bascule : sinon le port tire ses rolls depuis un etat que le
    # natif a deja consomme, et les deux montants ne sont plus comparables (c'est ce qui rendait
    # l'ecart 16919 / 9268 illisible).
    rng_av_b1 = rng_dump(sid, rid)
    seed_offline_rng(state, rng_av_b1)
    off_hp_avant_ennemi = hp_off(state)
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dec2 = decision(sid, rid)
    tours["apres_endturn_1"] = dec2.get("currentPlayer")
    # Le port joue la MEME bascule, pour le MEME joueur que celui a qui le natif vient de donner
    # la main.
    off_ennemi = delayed_attack_triggers(state, dec2.get("currentPlayer"))
    off_hp_apres_ennemi = hp_off(state)
    live_hp_apres_ennemi = hp_live(sid, rid)
    rng_avant = rng_dump(sid, rid)

    # ---- SECONDE BASCULE -- meme appariement -----------------------------------------------
    rng_off = seed_offline_rng(state, rng_avant)
    off_hp_avant = hp_off(state)
    off_foot_avant = footprint_off(state)

    act3 = rpc(sid, "applyAction",
               {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 90) or {}
    dec3 = decision(sid, rid)
    tours["apres_endturn_2"] = dec3.get("currentPlayer")
    off_tir = delayed_attack_triggers(state, dec3.get("currentPlayer"))
    off_hp_apres = hp_off(state)
    off_foot_apres = footprint_off(state)
    off_draws = int(getattr(rng_off, "call_count", 0) or 0)
    live_hp_apres = hp_live(sid, rid)
    rng_apres = rng_dump(sid, rid)

    return {
        "rid": rid, "caster": caster_id, "target": target_id, "from_here": from_here,
        "feet": feet,
        "mon_joueur": mon_joueur, "joueur_adverse": joueur_adverse, "tours": tours,
        "routed": res.get("routed"), "ported": diag.get("ported"),
        "diag": diag,
        "cast_error": cast_error,
        "off_cast": off_cast, "live_cast": live_cast,
        "off_hp_cast": (off_hp0, off_hp1), "live_hp_cast": (live_hp0, live_hp1),
        "live_coups_cast": live_coups_cast,
        "off_ennemi": off_ennemi,
        "off_hp_ennemi": (off_hp_avant_ennemi, off_hp_apres_ennemi),
        "live_hp_ennemi": (live_hp1, live_hp_apres_ennemi),
        "off_tir": off_tir,
        "off_hp_phase2": (off_hp_avant, off_hp_apres),
        "live_hp_phase2": (dict(live_hp_apres_ennemi), live_hp_apres),
        "off_foot_phase2": (off_foot_avant, off_foot_apres),
        "live_foot_phase2": (footprint_live(dec2), footprint_live(dec3)),
        "live_coups_phase2": _coups_natifs(act3),
        "off_draws": off_draws,
        "rng_avant": (rng_avant.get("callCount"), rng_avant.get("mti")),
        "rng_apres": (rng_apres.get("callCount"), rng_apres.get("mti")),
    }


def _dhp(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-name", default="probe_889_lions_wrath")
    # `--hp-target` : la CONTRE-EPREUVE par variation d'entree. Au regime nominal le cast TUE la
    # cible (11044 PV), donc (a) le total natif est CAPE par l'overkill et n'est plus comparable
    # coup a coup, et (b) l'`IfAlive(Target)` refuse les deux bonds -- les deux etages qu'on veut
    # mesurer sont eteints EN MEME TEMPS. Gonfler les PV les rallume tous les deux.
    ap.add_argument("--hp-target", default=None,
                    help="PV de la cible adverse (contre-epreuve : sans kill, les deux coups et "
                         "la phase 2 redeviennent observables)")
    # ⚠ `#889-r4` PROPOSAIT << un `endturn` NU des deux cotes (`--no-ai`) >> comme montage qui
    # tranche. **CE MONTAGE EST UN NO-OP, et c'est LU** (2026-08-13) :
    #   * `--no-ai` est un drapeau de `rl_duel play`, PAS de `build` -- et ce probe n'appelle jamais
    #     `play`. Le passer au `build` serait accepte par le parser GLOBAL et strictement inerte ;
    #   * l'`endturn` de ce probe est `applyAction {kind: "endturn"}`, que le bundle traduit en
    #     `runner.Apply(EndTurnMessage)` -- << message moteur, PAS IA >>
    #     (`frida/hooks/features/ai-step/internals.ts`). Le tour IA natif exige un
    #     `CheatRunAIMessage` explicite (`rl_duel _ai_turn`), qui n'est POSE NULLE PART ici.
    # Donc l'`endturn` intercalaire est DEJA nu : la cause candidate (b) << l'IA adverse a consomme
    # les effets >> est structurellement ECARTEE, et le montage propose n'aurait rien change.
    # Reste (a) la duree, et une TROISIEME hypothese que le residu ne nommait pas : (c) le coup
    # DIFFERE part cote natif au tour de l'ADVERSAIRE, la ou le port le route sur le tour du Lion
    # (`delayed_attack_triggers(state, joueur_adverse)` au pas [C] contre `mon_joueur` en phase 2).
    # C'est exactement la forme de l'observable rapporte (<< le coup differe natif ne part jamais,
    # le port le tire >>). Le montage qui tranche (a) contre (c) reste a ecrire.
    a = ap.parse_args()

    extra = ["--hp-target", str(a.hp_target)] if a.hp_target else []
    sid = _session()
    m, dispose = measure(sid, seed=a.seed, board=a.board, state_name=a.state_name,
                         extra_args=extra)
    try:
        print("[889] runner=%s caster=%s target=%s routed=%s ported=%s err=%s"
              % (m["rid"], m["caster"], m["target"], m["routed"], m["ported"], m["cast_error"]))
        print("[889] EMPREINTES (feet) -- ventilation, pas verdict :")
        for uid, f in sorted(m["feet"].items()):
            print("        u%s %-32s pos=%s n_feet=%s feet=%s"
                  % (uid, f["visualId"], f["pos"], f["n"], f["feet"]))
        print("[889] [A] CAST -- effets poses")
        print("        port  : %s" % m["off_cast"])
        print("        natif : %s" % m["live_cast"])
        # ⚠ #889-r9 : les deux `remaining` ne sont PAS pris au meme instant des que le cast a
        # BASCULE le tour. Le Lion est SEUL dans son camp ici -- son cast appelle donc
        # `FinishUnitTurn`, plus rien n'est activable, et le natif enchaine
        # `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` ->
        # `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` AVANT que
        # `decisionView` ne soit relu. Le port, lui, ne joue que le cast. Un `remaining` natif
        # inferieur d'exactement 1 est ce DECALAGE, pas une duree divergente : mesure
        # `probe_889r9_duree_pre_tick.py` -- avec un camarade activable derriere le Lion, les
        # deux cotes rendent 2, bit a bit.
        if m["tours"].get("apres_cast") != m["mon_joueur"]:
            print("        -> ATTENTION : le cast a BASCULE le tour, donc les `remaining` natifs "
                  "ci-dessus sont POST-tick. Ne PAS les comparer aux `remaining` du port sans "
                  "lui faire jouer le meme `EndTurnOperation` (#889-r9).")
        print("[889] [A] CAST -- degat")
        print("        port  : %s" % _dhp(*m["off_hp_cast"]))
        print("        natif : %s" % _dhp(*m["live_hp_cast"]))
        print("        coups natifs : %s" % m["live_coups_cast"])
        print("        diag port    : %s" % json.dumps(m["diag"], default=str)[:900])
        # LE DISCRIMINANT : a qui le NATIF donne-t-il la main a chaque pas ? Un pas NOMME
        # << tour ennemi >> qui rend `currentPlayer == mon_joueur` invalide le temoin negatif.
        print("[889] JOUEURS -- mon_joueur=%s joueur_adverse=%s" % (m["mon_joueur"],
                                                                   m["joueur_adverse"]))
        print("        currentPlayer natif par pas : %s" % m["tours"])
        _t = m["tours"]
        if _t.get("apres_cast") == m["mon_joueur"] and _t.get("apres_endturn_1") != m["mon_joueur"]:
            print("        -> les pas sont ALIGNES : [C] est bien le tour ADVERSE")
        else:
            print("        -> ATTENTION, PAS DECALES : le pas nomme << tour ennemi >> n'est PAS "
                  "le tour adverse. Le temoin negatif ne vaut rien tel quel (#889-r4).")
        print("[889] [C] TOUR ENNEMI (temoin NEGATIF : rien ne doit partir)")
        print("        port  : %s | dhp=%s" % (m["off_ennemi"], _dhp(*m["off_hp_ennemi"])))
        print("        natif : dhp=%s" % (_dhp(*m["live_hp_ennemi"]),))
        print("[889] [C] TOUR DU LION -- PHASE 2")
        print("        port  : %s" % json.dumps(m["off_tir"], default=str)[:900])
        print("        port  dhp=%s" % (_dhp(*m["off_hp_phase2"]),))
        print("        natif dhp=%s" % (_dhp(*m["live_hp_phase2"]),))
        print("        coups natifs : %s" % m["live_coups_phase2"])
        print("        port  effets : %s -> %s" % m["off_foot_phase2"])
        print("        natif effets : %s -> %s" % m["live_foot_phase2"])
        print("[889] rng %s -> %s ; tirages offline=%s"
              % (m["rng_avant"], m["rng_apres"], m["off_draws"]))
    finally:
        dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
