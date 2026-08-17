"""probe_491 -- MESURE de `1069 SeekerMissileFrequencyLock` (`tauMarksman` Sho'syl, Tau, HERO).

QUESTION BINAIRE, posee AVANT la methode : **le CAST de 1069 inflige-t-il des degats ?**
L'audit `combat-ability-coverage` le classe `DAMAGE(HeavyRound)` et la PREDICTION native affiche
bien un intervalle de degat pour cette ability. Le decompile dit non :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
ne porte AUCUN noeud d'attaque -- il pose trois effets et les compose par
`IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` :

    turns = Sum(TurnsFromRounds(1), Direct(1))  == IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn
      AddEffect(     1122 Markerlight, AbilityStateReference, source=Caster, targets=Target, turns)
    & AddBondEffect( 1123 SeekerMissileFrequencyLock_Target, CreateSnapshot(abilityState),
                     source=Caster, targets=Target, bonded=Caster, options=ZERO)
    & AddBondEffect( 1136 SeekerMissileFrequencyLock_Aiming, CreateSnapshot(abilityState),
                     source=Caster, targets=Caster, bonded=Target, options=ZERO)

Le `HeavyRound` du kit appartient a la PHASE 2 --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`
(`TriggeredAbilityType.SeekerMissileFrequencyLock_Attack` = 1127, rendu par
`IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect$$GetTriggeredAbilityType`),
NON portee (residu #491-r1). Meme patron 2-phases que `HeavyRailRifle` (1160).

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [1] EXECUTION portee            : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX)
  [2] empreinte d'effets          : port == natif, `{unite -> {effectType: remaining}}`
  [3] PORTEURS et BONDS           : 1123 sur la CIBLE bonde au CASTER ; 1136 sur le CASTER bonde a la
                                    CIBLE (les deux selecteurs, dans l'ordre INVERSE -- lu au
                                    decompile, et c'est le point ou une recopie du voisin se trompe)
  [4] AUCUN DEGAT                 : HP inchanges des DEUX cotes -- la refutation de l'audit
  [5] CONSEQUENCE du Markerlight  : la prediction native d'une attaque RANGED T'AU sur la cible
                                    passe a x(100 + MarkerlightDmgBonusPct)/100. C'est ce qui
                                    distingue « effet pose » de « effet pose ET vivant ».

Le placement est FORCE (`--place`/`--a-place`) : la geometrie de spawn de MC1_67 met Sho'syl
hors de portee (range=5 depuis `constants.range`), et « bloque par la geometrie » n'est pas un
resultat.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_491_seeker_missile_frequency_lock.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

SEEKER = 1069                  # ActiveAbilityType.SeekerMissileFrequencyLock
MARKERLIGHT = 1122             # EffectType.Markerlight
SEEKER_TARGET = 1123           # EffectType.SeekerMissileFrequencyLock_Target
SEEKER_AIMING = 1136           # EffectType.SeekerMissileFrequencyLock_Aiming
BOARD = "MC1_67"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/tau.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/behaviours/effects.py",
                "scripts/python/engine/entities/effects/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1069 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + primitives AddEffect/AddBondEffect + la classe MarkerlightEffect "
              "qui porte le bonus) ET du build charge (le natif est l'oracle).",
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
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-1500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec


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
    """MEME empreinte cote port (`remaining_turns is None` == le `remaining 0` live = permanent)."""
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


def find(dec, visual_id):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)


def plan_damage(dec, attacker: int, target: int) -> dict:
    """`decisionView.attackPlans[].evals[].ranked[]` : la prediction NATIVE de `attacker` -> `target`,
    INDEXEE PAR TUILE `{(col,row) -> (dmgMin, dmgMax)}`.

    L'indexation par tuile n'est pas cosmetique : `ranked[0]` est la MEILLEURE tuile, et elle peut
    CHANGER entre deux mesures -- comparer `ranked[0]` avant/apres comparerait alors deux positions
    differentes et attribuerait a l'effet un ecart de GEOMETRIE."""
    out = {}
    for p in (dec.get("attackPlans") or []):
        if int(p.get("unitId", -1)) != int(attacker):
            continue
        for ev in (p.get("evals") or []):
            if int(ev.get("targetId", -1)) != int(target):
                continue
            for r in (ev.get("ranked") or []):
                out[(r.get("col"), r.get("row"))] = (int(r.get("dmgMin", 0)),
                                                     int(r.get("dmgMax", 0)))
    return out


def bonds_from_cascade(act: dict) -> dict:
    """`{effectType -> {'on': porteur, 'bonded': BondEffect_BondedId, ...}}` lu dans la CASCADE du
    cast NATIF -- le SEUL canal qui publie le BOND (`decisionView.effects` ne porte que
    `effectType`/`remaining`, donc l'empreinte de l'etape [2] ne peut pas voir une inversion).

    Format REEL (mesure) : `act.events` est une liste PLATE de
    `{kind, entity, group?, source?, step?, tags?}` ou `tags` est une CHAINE JSON.
      * `kind == "group"` : `entity` = l'ID D'INSTANCE de l'effet, `source` = son NOM ;
      * `kind == "action"` : `entity` = le PORTEUR, `tags.Effect_Id` = ce meme id d'INSTANCE.

    `Effect_Id` est donc un id D'INSTANCE (108/109/110), PAS un `EffectType` -- les confondre
    lirait n'importe quoi. On resout instance -> NOM (canal `group.source`) puis NOM -> `EffectType`
    par le mirror, conformement a « la conversion se fait PAR NOM, jamais par l'ordinal »."""
    from engine.entities.effect_type import EffectType
    nom_par_instance, out = {}, {}
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") == "group" and ev.get("source"):
            nom_par_instance[ev.get("entity")] = str(ev.get("source"))
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict) or ev.get("kind") != "action":
            continue
        raw = ev.get("tags")
        try:
            tags = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        inst = tags.get("Effect_Id")
        nom = nom_par_instance.get(inst)
        if nom is None or "Effect_SourceId" not in tags:      # l'evenement PORTEUR de l'effet
            continue
        etype = getattr(EffectType, nom, None)
        if etype is None:
            continue
        out[int(etype)] = {"on": ev.get("entity"), "bonded": tags.get("BondEffect_BondedId"),
                           "source": tags.get("Effect_SourceId"),
                           "remaining": tags.get("Effect_RemainingTurns")}
    return out


def measure(sid: int, seed: str = "777", board: str = BOARD, state_name: str = "probe_491_seeker"):
    """Monte le scenario, joue le cast des DEUX cotes, rend `(mesures, dispose)`.

    Le TEST de garde (`tests/engine/runner/test_seeker_missile_frequency_lock_live.py`) appelle
    CETTE fonction : une seule implementation du montage et des lectures, donc aucune divergence
    possible entre ce qui est MESURE ici et ce qui est GARDE la-bas."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "tauMarksman,tauShadowsun",
        "--a-units", "orksNob,orksRuntherd",
        # DRIVE des positions : la geometrie de spawn de MC1_67 met Sho'syl hors de portee 5.
        # « Bloque par la geometrie de spawn » n'est pas un resultat.
        "--place", "tauMarksman:2,2", "--place", "tauShadowsun:1,2",
        "--a-place", "orksNob:2,5", "--a-place", "orksRuntherd:4,4"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int) -> dict:
    from engine.entities.effects.magnitude import bc_effect_config
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    dec0 = decision(sid, rid)
    caster = find(dec0, "tauMarksman")
    ally = find(dec0, "tauShadowsun")
    if caster is None or ally is None:
        raise AssertionError("SCENARIO NON MONTE : tauMarksman/tauShadowsun absents du decisionView")
    caster_id, ally_id = int(caster["id"]), int(ally["id"])

    # Cible = une cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a « l'ability ne fait
    # rien » -- #111).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": SEEKER}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    # La cle est `abilityId` (pas `id`) : `abilities[0]` marcherait tant que la reponse ne porte
    # QUE l'ability demandee -- on ne s'appuie pas dessus.
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SEEKER), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    targets_superset = [t.get("targetId") for t in (ab.get("targets") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1069 "
                             "(drive des positions KO) -- fromHere vide")
    target_id = int(from_here[0])

    # ---- GATE DE CIBLAGE : le masque TargetIsEnemy MORD-il ? -----------------------------
    # C'est la donnee posee AVEC l'entree au registre. Sans elle, `get_invalid_target_reason`
    # rend 0 immediatement : degradation PERMISSIVE, invisible en self-play.
    state_gate, _ = load(sid, rid)
    ability = ABILITY_CLASSES[SEEKER]()
    gate = {
        "ennemi": get_invalid_target_reason(state_gate, caster_id, target_id, ability),
        "allie": get_invalid_target_reason(state_gate, caster_id, ally_id, ability),
        "soi": get_invalid_target_reason(state_gate, caster_id, caster_id, ability),
    }
    # L'oracle natif du meme gate : `targets` (superset move-inclus) n'enumere QUE des ennemis.
    gate_natif = {"allie_dans_targets": ally_id in targets_superset,
                  "soi_dans_targets": caster_id in targets_superset}

    # ---- OFFLINE : le MEME cast, joue par le port ----------------------------------------
    state, _ = load(sid, rid)
    off_hp_before = hp_off(state)
    off_before = footprint_off(state)
    res = _apply_active_ability(state, caster_id, target_id, SEEKER) or {}
    diag = res.get("diag") or {}
    off = delta(off_before, footprint_off(state))
    off_hp_after = hp_off(state)
    off_bonds = {}
    for uid, effs in (state.effects.by_unit or {}).items():
        for e in effs:
            if int(e.effect_type) in (SEEKER_TARGET, SEEKER_AIMING) and not e.consumed:
                off_bonds[int(e.effect_type)] = {"on": int(uid), "bonded": getattr(e, "bonded", None)}

    # ---- LIVE : le MEME cast, joue par le natif ------------------------------------------
    live_before = footprint_live(dec0)
    live_hp_before = hp_live(sid, rid)
    pred_before = plan_damage(dec0, ally_id, target_id)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SEEKER,
        "targetId": target_id}}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    dec1 = decision(sid, rid)

    return {
        "rid": rid, "caster": caster_id, "ally": ally_id, "target": target_id,
        "from_here": from_here, "targets_superset": targets_superset,
        "routed": res.get("routed"), "ported": diag.get("ported"), "turns": diag.get("turns"),
        "diag": diag, "cast_error": act0.get("error"),
        "off": off, "live": delta(live_before, footprint_live(dec1)),
        "off_bonds": off_bonds, "live_bonds": bonds_from_cascade(act0),
        "off_hp": (off_hp_before, off_hp_after),
        "live_hp": (live_hp_before, hp_live(sid, rid)),
        "pred_before": pred_before, "pred_after": plan_damage(dec1, ally_id, target_id),
        "markerlight_pct": bc_effect_config("MarkerlightDmgBonusPct", 15),
        "gate": gate, "gate_natif": gate_natif,
    }


def main() -> int:
    sid = _session()
    print("[build] board=%s" % BOARD)
    m, dispose = measure(sid)
    try:
        caster_id, ally_id, target_id = m["caster"], m["ally"], m["target"]
        off, live = m["off"], m["live"]
        off_bonds, bonds = m["off_bonds"], m["live_bonds"]
        diag, res = m["diag"], {"routed": m["routed"]}
        off_hp_before, off_hp_after = m["off_hp"]
        live_hp_before, live_hp_after = m["live_hp"]
        pred_before, pred_after = m["pred_before"], m["pred_after"]
        act0 = {"error": m["cast_error"]}

        print("[scenario] caster=u%d ally=u%d target=u%d" % (caster_id, ally_id, target_id))
        print("           fromHere=%s  (targets=%s -- SUPERSET move-inclus, #111)"
              % (m["from_here"], m["targets_superset"]))

        print("\n[1] EXECUTION PORTEE")
        print("    routed=%s ported=%s turns=%s" % (res.get("routed"), m.get("ported"),
                                                    diag.get("turns")))
        if m.get("ported") is not True:
            print("    ECHEC : 1069 reste un NO-OP SILENCIEUX cote port")
            return 1
        if act0.get("error"):
            print("    cast natif BLOQUE : %s" % act0.get("error"))
            return 1

        print("\n[2] EMPREINTE D'EFFETS  (port vs natif)")
        print("    port  = %s" % off)
        print("    natif = %s" % live)
        ok2 = off == live
        print("    -> %s" % ("ACCORD" if ok2 else "DIVERGENCE"))

        print("\n[3] PORTEURS ET BONDS")
        attendu = {caster_id: {SEEKER_AIMING}, target_id: {MARKERLIGHT, SEEKER_TARGET}}
        obtenu = {k: set(v) for k, v in off.items()}
        print("    attendu (decompile) = %s" % {k: sorted(v) for k, v in attendu.items()})
        print("    obtenu  (port)      = %s" % {k: sorted(v) for k, v in obtenu.items()})
        ok3 = obtenu == attendu
        print("    bonds natif (cascade) = %s" % bonds)
        print("    bonds port            = %s" % off_bonds)
        attendu_bonds = {SEEKER_TARGET: {"on": target_id, "bonded": caster_id},
                         SEEKER_AIMING: {"on": caster_id, "bonded": target_id}}
        ok3b = all(off_bonds.get(et, {}).get("on") == v["on"]
                   and off_bonds.get(et, {}).get("bonded") == v["bonded"]
                   for et, v in attendu_bonds.items())
        # Le natif est l'ORACLE : s'il publie les bonds, c'est LUI qui tranche, pas le decompile seul.
        ok3c = all(bonds.get(et, {}).get("on") == v["on"]
                   and bonds.get(et, {}).get("bonded") == v["bonded"]
                   for et, v in attendu_bonds.items()) if bonds else None
        print("    -> porteurs %s | bonds INVERSES port %s | natif %s"
              % ("OK" if ok3 else "KO", "OK" if ok3b else "KO",
                 "NON MESURE (cascade muette)" if ok3c is None else ("OK" if ok3c else "KO")))

        print("\n[4] AUCUN DEGAT  (la refutation de l'audit DAMAGE(HeavyRound))")
        off_dmg = {k: (off_hp_before[k], off_hp_after.get(k))
                   for k in off_hp_before if off_hp_after.get(k) != off_hp_before[k]}
        live_dmg = {k: (live_hp_before[k], live_hp_after.get(k))
                    for k in live_hp_before if live_hp_after.get(k) != live_hp_before[k]}
        print("    port  : HP changes = %s" % (off_dmg or "AUCUN"))
        print("    natif : HP changes = %s" % (live_dmg or "AUCUN"))
        ok4 = not off_dmg and not live_dmg
        print("    -> %s" % ("AUCUN DEGAT des deux cotes" if ok4 else "DEGAT OBSERVE"))

        print("\n[5] CONSEQUENCE DU MARKERLIGHT  (prediction NATIVE, allie T'AU ranged -> cible)")
        pct = m["markerlight_pct"]                             # regle GLOBALE, section BC `Effect`
        # On ne compare QUE les tuiles presentes AVANT ET APRES : une tuile apparue/disparue est un
        # ecart de geometrie, pas un effet du marquage.
        communes = sorted(set(pred_before) & set(pred_after))
        print("    MarkerlightDmgBonusPct = %s ; tuiles communes = %d" % (pct, len(communes)))
        # ⚠ ON NE RECONSTITUE PAS L'ARRONDI NATIF. `dmgMin`/`dmgMax` sont DEJA arrondis : la valeur
        # interne derriere `6008` vit dans [6007.5, 6008.5), et x1.15 la place dans
        # [6908.6, 6909.8) -- 6909 comme 6910 sont donc des sorties LEGITIMES du meme calcul.
        # Exiger `round(affiche * 1.15)` serait fitter un scalaire sur une entree qu'on ne detient
        # pas. Le critere est l'ENCADREMENT : la sortie doit tomber dans l'intervalle image de
        # l'intervalle d'incertitude de l'entree.
        ok5, lignes = bool(communes), []
        for tile in communes:
            avant, apres = pred_before[tile], pred_after[tile]
            ok_tile = True
            bornes = []
            for v0, v1 in zip(avant, apres):
                lo = (v0 - 0.5) * (100 + int(pct)) / 100
                hi = (v0 + 0.5) * (100 + int(pct)) / 100
                dedans = (lo - 0.5) <= v1 <= (hi + 0.5)
                ok_tile = ok_tile and dedans
                bornes.append("%d->%d in [%.1f,%.1f]%s" % (v0, v1, lo, hi, "" if dedans else " KO"))
            if not ok_tile:
                ok5 = False
            lignes.append("      %s : %s  %s" % (tile, " ; ".join(bornes),
                                                 "OK" if ok_tile else "HORS BORNES"))
        for line in lignes[:6]:
            print(line)
        # ANTI-DEGENERESCENCE : un encadrement passe TRIVIALEMENT si le bonus est nul (l'intervalle
        # image contient alors l'entree). On EXIGE un temoin non-nul -- accord en regime degenere
        # = zero preuve.
        bouge = any(pred_after[t] != pred_before[t] for t in communes)
        if not (int(pct) > 0 and bouge):
            ok5 = False
            print("      REGIME DEGENERE : pct=%s bouge=%s -> l'encadrement ne prouve RIEN"
                  % (pct, bouge))
        print("    -> %s" % ("le marquage MORD sur la prediction native (+%s%%)" % pct if ok5
                             else "NON CONCLUANT (aucune tuile commune, hors bornes, ou degenere)"))

        print("\n[6] GATE DE CIBLAGE  (TargetIsEnemy -- la donnee posee AVEC l'entree au registre)")
        gate, gate_natif = m["gate"], m["gate_natif"]
        print("    port  : ennemi=%s (0 attendu) allie=0x%x soi=0x%x"
              % (gate["ennemi"], gate["allie"], gate["soi"]))
        print("    natif : allie dans `targets`=%s soi dans `targets`=%s (False attendu)"
              % (gate_natif["allie_dans_targets"], gate_natif["soi_dans_targets"]))
        ok6 = (gate["ennemi"] == 0 and gate["allie"] != 0 and gate["soi"] != 0
               and not gate_natif["allie_dans_targets"] and not gate_natif["soi_dans_targets"])
        print("    -> %s" % ("le masque MORD (allie et soi REFUSES des deux cotes)" if ok6
                             else "le gate NE MORD PAS -- degradation PERMISSIVE"))

        # `ok3c is None` = le natif n'a pas publie les bonds : on ne le compte NI pour NI contre
        # (une mesure absente n'est pas une mesure verte -- elle est dite, pas rabattue sur zero).
        etages = {"[2] empreinte": ok2, "[3] porteurs": ok3, "[3] bonds port": ok3b,
                  "[3] bonds natif": ok3c, "[4] aucun degat": ok4, "[5] markerlight": ok5,
                  "[6] gate ciblage": ok6}
        rouges = [k for k, v in etages.items() if v is False]
        muets = [k for k, v in etages.items() if v is None]
        print("\nETAGES : %s" % {k: ("OK" if v else ("NON MESURE" if v is None else "KO"))
                                 for k, v in etages.items()})
        if muets:
            print("NON MESURE : %s" % ", ".join(muets))
        print("PROBE OK" if not rouges else "PROBE KO -- %s" % ", ".join(rouges))
        return 0 if not rouges else 1
    finally:
        dispose()          # dispose MES runners, jamais ceux des autres


if __name__ == "__main__":
    raise SystemExit(main())
