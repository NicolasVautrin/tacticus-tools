#!/usr/bin/env python
"""Probe #178 / #R33 -- les arguments de la surcharge d'INSTANCE de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`.

SIGNATURE NATIVE (relue au build, `data/symbols/gqfc5mff6c/frida/methods.tsv`) :

    DamagePrediction.IsOverkill(target:IEntity, hitDamage:int, deniedDamage:int, isCritical:bool,
                                isForceOverkill:bool, targetHealthBeforeAttack:Nullable<int>,
                                minimumHealth:Nullable<int>) -> bool
    DamagePrediction.IsOverkill(targetInitialHealth:int, healthDamage:int, isCritical:bool,
                                isForceOverkill:bool, isPreventOverkill:bool, allowOverkill:bool,
                                overkillDmgPctOfHealth:int, targetMinimumHealth:Nullable<int>)

Le corps prive rend **`isCritical`** dans le cas << letal mais SOUS le seuil >>
(`targetInitialHealth <= healthDamage` et `pct < overkillDmgPctOfHealth`). Autrement dit : un coup
CRITIQUE qui tue sans doubler les PV EST un overkill. Le port passait ce champ a 0 EN DUR.

DEUX MONTAGES, DEUX OBSERVABLES INDEPENDANTS (aucun RPC ne lit `UnitFlag.Overkilled` directement) :

  A. CRESCENDO -- `TerrifyingCrescendo` (triggered 1435, passif d'`emperNoiseMarine` << Shiron >>),
     branche 1 = `On(UnitDeath=0) & OwnerIsActor & TargetIsOverkilled`, et
     `IdunBattleLogic.Entities.DSLFactory$$TargetIsOverkilled` = `HasFlagAbilityTrigger(target, 8)`.
     Chaque declenchement incremente `TerrifyingCrescendo_ExtraDmg` (1424) sur Shiron, dont le
     `level` est expose par `decisionView.units[].effects[]`.
     Regimes : `control` / `titus` (gates d'unite, #178) et `crit` / `nocrit` (#R33).

  B. REVIVE -- `Narthecium_ReviveEffect` (passif d'`ultraApothecary`) revive un allie adjacent(2)
     **unless Overkilled** (`get_ReviveOnOverkill = 0` -> `OnDeathEvent` ajoute
     `NOT(HasFlag(dying, 8))`), chance 100 (gameconfig `Narthecium.constants.chance`).
     Observable = la victime est-elle VIVANTE apres le coup letal.
     Regimes : `revive-crit` / `revive-nocrit`.

     POURQUOI CE 2e MONTAGE EST NECESSAIRE (attribution, pas redondance) : `emperNoiseMarine` porte
     le trait `ThrillSeekers` (1056), dont le rider << defeats an enemy with a Crit -> always
     overkilled >> force `isForceOverkill` quand l'attaquant a le trait ET l'effet `Thrilled` ET que
     le coup est CRITIQUE. Sur le montage A, un overkill au crit pourrait donc venir du rider et non
     d'`isCritical`. Le montage B tue avec `ultraInceptorSgt`, qui NE porte PAS ThrillSeekers : plus
     aucun rider ne peut expliquer l'observation.

REGIME << LETAL SOUS LE SEUIL >> : on tune les PV de la victime a `dmin` (borne BASSE du degat), et
on VERIFIE `dmax < 2 x PV`. Toute la plage de degat est alors letale ET sous le seuil
(`overkillDmgPctOfHealth` = 100) -> le verdict ne depend plus du tirage, seulement du flag crit.
`--crit "CC,CD"` patche CritChance/CritDamage des p-units : `100,1` = crit garanti pour +1 de base
d'attaque (degat quasi inchange), `0,0` = `CouldCrit` faux (GetStat(10) == 0) donc AUCUN crit
possible, meme si un effet ajoute de la crit-chance.

MELEE OBLIGATOIRE (montage A) : le trait `SuppressiveFire` de Shiron pose `Pinned` (1065) sur les
attaques RANGED, ce qui alimente la BRANCHE 2 du MEME crescendo. Au contact hex l'attaque normale
part en melee, et la paire est auto-certifiante : un regime a +0 => la branche 2 est muette.

GEOMETRIE DRIVEE (jamais subie) : `applyAction move` ne verifie PAS la propriete -> on TELEPORTE la
victime au centre et les autres acteurs sur son ring 1.

Le probe confronte, sur CHAQUE regime : le LIVE, le corps SUPPRIME de #178 (recopie verbatim), le
verdict de `unit_is_overkill` sur l'ETAT OFFLINE reellement charge, et -- pour les regimes crit --
le REJEU COMPLET de l'attaque par le port (`AttackDamageOperation`), dont on lit le vrai
`UnitFlagsComponent.OVERKILLED`.

ASCII only (cp1252). Usage :
  python probe_178_overkill_gate.py --case both
  python probe_178_overkill_gate.py --case crit
  python probe_178_overkill_gate.py --case revive-crit
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.services.trait_damage_limits import (unit_is_overkill,         # noqa: E402
                                                 _overkill_threshold_pct)
from engine.runner.components import (can_be_overkilled,                   # noqa: E402
                                      unit_prevents_overkill, UnitComponent,
                                      UnitFlagsComponent, HealthComponent)
from engine.runner.snapshot import load_state                              # noqa: E402

SHIRON = "emperNoiseMarine"       # passif TerrifyingCrescendo (compteur d'overkills lisible)
KILLER = "ultraInceptorSgt"       # 2e unite de mon camp : sans elle l'attaque de Shiron finit mon tour
# 2e ennemi OBLIGATOIRE : sans lui, tuer la victime TERMINE la bataille et `decisionView` ne rend plus
# d'unites -> le crescendo devient illisible (faux negatif mesure a la 1re passe). Tenu a l'ecart.
FILLER = "astraBullgryn"
APOTHECARY = "ultraApothecary"    # Narthecium : revive un allie adjacent(2) UNLESS Overkilled
CRESCENDO = "TerrifyingCrescendo_ExtraDmg"
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)

# Regimes du montage A (crescendo). `hp = None` => tune AUTOMATIQUEMENT a `dmin` (regime letal-sous-
# le-seuil) ; un entier => PV fixes (regimes #178, ou le degat depasse 2x PV).
CASES = {
    "control": {"victim": "genesPrimus", "hp": 400, "crit": "0,0", "attacker": SHIRON},
    "titus":   {"victim": "ultraTitus",  "hp": 400, "crit": "0,0", "attacker": SHIRON},
    "nocrit":  {"victim": "genesPrimus", "hp": None, "crit": "0,0", "attacker": SHIRON},
    "crit":    {"victim": "genesPrimus", "hp": None, "crit": "100,1", "attacker": SHIRON},
}
VICTIMS = {k: v["victim"] for k, v in CASES.items()}     # compat conftest #178

BLIGHTLORD = "deathBlightlord"    # FlailSwing (1042) : `alwaysOverkilled` = AttackOptions@+4
FLAIL_SWING = 1042

# Regimes du montage B (revive Narthecium). Tueur SANS ThrillSeekers dans TOUS les cas.
#   `revive-nocrit` / `revive-crit` : discriminent `isCritical` (DealDamageInfo@+0x1c).
#   `revive-flail`  : discrimine `isForceOverkill` (@+0x2c) SANS aucun crit -- FlailSwing pose le
#       flag `alwaysOverkilled`, donc « des que letal, overkill » meme tres en-dessous du seuil.
REVIVE_CASES = {
    "revive-nocrit": {"crit": "0,0", "attacker": KILLER, "ability": NORMAL_ATTACK},
    "revive-crit":   {"crit": "100,1", "attacker": KILLER, "ability": NORMAL_ATTACK},
    "revive-flail":  {"crit": "0,0", "attacker": BLIGHTLORD, "ability": FLAIL_SWING},
}

_BAND_CACHE: dict = {}            # (attaquant, victime) -> (dmin, dmax) mesures a crit "0,0"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, p_units, a_units, hp_target: int,
          crit_spec: str = "0,0") -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", "MC1_67", "--rank", "17",
         "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
         "--hp-target", str(hp_target), "--crit", crit_spec, "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[178] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def by_visual(dv, vis, alive=True):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and (bool(u.get("alive")) or not alive):
            return u
    return None


def crescendo_level(dv, unit_id) -> int:
    """Niveau de `TerrifyingCrescendo_ExtraDmg` sur `unit_id` (0 = effet absent)."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) != int(unit_id):
            continue
        for e in (u.get("effects") or []):
            if e.get("name") == CRESCENDO and not e.get("removed"):
                return int(e.get("level") or 0)
    return 0


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def attack(sid, rid, attacker_id, target_id, ability=NORMAL_ATTACK):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(attacker_id), "targetId": int(target_id),
        "abilityType": int(ability)}}, 120)


def predicted_damage(sid, rid, attacker_id, target_id, ability=NORMAL_ATTACK):
    """Plage de degat BRUT du prochain coup (`aiPredict` = `GetAllPredictions`). `totalDmg*` = brut
    sante+armure+bouclier -> EGALE le degat sante brut quand la cible n'a ni armure ni bouclier
    (le cas ici : `--hp-target` remet `Armor`/`FixedArmor` a 0, et personne n'a de bouclier)."""
    p = (_r(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker_id),
                               "targetId": int(target_id), "abilityType": int(ability)}, 90)
         or {}).get("pred") or {}
    if p.get("totalDmgMin") is None:
        return None, None
    return int(p["totalDmgMin"]), int(p["totalDmgMax"])


def killed_by(dv, uid, killer_id) -> bool:
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), None)
    return u is not None and u.get("killerId") is not None and int(u["killerId"]) == int(killer_id)


def _legacy_is_overkill(hp_before, damage) -> bool:
    """LE CORPS SUPPRIME (doublon 2-args de `services/damage_prediction.py`, pre-#178), conserve ici
    VERBATIM pour que le probe puisse dire LEQUEL des corps le live refute."""
    import gameconfig as GC
    if damage is None or hp_before is None or hp_before <= 0:
        return False
    pct = int(GC.global_value("overkillDmgPctOfHealth") or 100)
    return (int(damage) - int(hp_before)) * 100 >= pct * int(hp_before)


def _load(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    st = load_state(cap["dec"], cap["ob"], cap["snap"],
                    board=Board(cap["bg"]["tiles"], adjacency="evenq"))
    s = cap.get("rng") or {}
    if s.get("mt"):                       # replay-diff : le MT du runner, cale AVANT le coup live
        r = IntBasedMersenneTwister()
        r.mt = list(s["mt"])
        r.mti = s["mti"]
        st.rng = r
    return st


def offline_verdict(cap, victim_id, hp, dmg, is_critical=False):
    """Le corps LIVRE (`unit_is_overkill`), evalue sur l'ETAT OFFLINE reellement charge."""
    st = _load(cap)
    tgt = st.get_entity(int(victim_id))
    cbo = can_be_overkilled(tgt)
    prv = unit_prevents_overkill(st, int(victim_id))
    return unit_is_overkill(hp, dmg, can_be_overkilled=cbo, prevent_overkill=prv,
                            is_critical=is_critical), cbo, prv


def replay_flag(cap, attacker_id, victim_id):
    """REJEU COMPLET de l'attaque normale par le port sur l'etat capture, puis lecture du VRAI
    `UnitFlagsComponent.OVERKILLED` pose par `AttackDamageOperation._fire_death_if_killed`.
    C'est le chemin de production, pas une re-evaluation de formule : la garde porte donc sur le
    cablage (`hits_result` / `_did_overkill`), pas seulement sur `unit_is_overkill`.
    Rend `(flag, total, crits, hp_after)` ou `(None, ...)` si le rejeu n'a pas tue."""
    from engine.runner.operations.damage import AttackDamageOperation
    st = _load(cap)
    res = AttackDamageOperation.execute(st, int(attacker_id), int(victim_id), 20) or {}
    ent = st.get_entity(int(victim_id))
    fl = ent.get_component(UnitFlagsComponent) if ent is not None else None
    hc = ent.get_component(HealthComponent) if ent is not None else None
    flag = bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED))
    return flag, int(res.get("total") or 0), list(res.get("crits") or []), \
        (hc.hp if hc is not None else None)


def _tune_hp(sid, seed, attacker, victim, state_file, p_units, a_units, verbose=True,
             ability=NORMAL_ATTACK):
    """PASSE 1 : monte un runner jetable pour LIRE la plage de degat de l'attaquant sur la victime,
    et en deduit les PV du regime << letal sous le seuil >> : `PV = dmin`, valide si `dmax < 2 x PV`
    (toute la plage tue sans jamais atteindre `overkillDmgPctOfHealth` = 100 %).

    La composition d'equipes de la passe 1 est IDENTIQUE a celle du regime mesure (memes auras,
    meme geometrie) -- sinon la plage lue ne serait pas celle du regime."""
    key = (attacker, victim, tuple(p_units), tuple(a_units), int(ability))
    if key in _BAND_CACHE:
        return _BAND_CACHE[key]
    rid = None
    try:
        rid, ids = setup(sid, state_file, seed, attacker, victim, list(p_units),
                         list(a_units), (3, 4), hp_target=4000, crit_spec="0,0",
                         verbose=False, check_hp=False)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        dmin, dmax = predicted_damage(sid, rid, ids[attacker], vic["id"], ability)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if dmin is None:
        raise RuntimeError("aiPredict illisible en passe 1 (%s -> %s)" % (attacker, victim))
    if dmax >= 2 * dmin:
        raise RuntimeError("plage [%d,%d] trop large : dmax >= 2 x dmin, pas de PV rendant TOUTE "
                           "la plage letale-sous-le-seuil" % (dmin, dmax))
    if verbose:
        print("[178] tune %s -> %s : plage [%d,%d] => PV = %d (2 x PV = %d)"
              % (attacker, victim, dmin, dmax, dmin, 2 * dmin))
    _BAND_CACHE[key] = (dmin, dmax)
    return _BAND_CACHE[key]


REVIVE_P_UNITS = (KILLER, FILLER)         # aucun porteur de ThrillSeekers sur le plateau
REVIVE_A_UNITS = ("genesPrimus", APOTHECARY)


def _replay_attack(st, attacker_id, victim_id, ability=NORMAL_ATTACK):
    """Rejoue OFFLINE le vecteur d'attaque du regime sur l'etat `st` (attaque normale ou ability)."""
    from engine.runner.operations.damage import AttackDamageOperation
    if int(ability) == FLAIL_SWING:
        from engine.runner.abilities.deathguard import FlailSwingAbility
        return FlailSwingAbility().execute_behaviour(st, int(attacker_id), int(victim_id))
    return AttackDamageOperation.execute(st, int(attacker_id), int(victim_id), 20)


def replay_damage_total(cap, attacker_id, victim_id, ability=NORMAL_ATTACK):
    """Degat TOTAL que le vecteur infligerait a une cible qui NE MEURT PAS : sur une copie de
    l'etat, on porte les PV de la victime tres haut avant de rejouer. C'est la mesure de reference
    du regime -- `aiPredict` ne rend que la preview de l'attaque NORMALE et ment de ~30 % sur un
    vecteur d'ABILITY (mesure FlailSwing : preview [9393,14091], degat reel 20884)."""
    st = _load(cap)
    ent = st.get_entity(int(victim_id))
    hc = ent.get_component(HealthComponent) if ent is not None else None
    if hc is None or hc.hp is None:
        return None
    big = 10 ** 7
    hc.hp = big
    _replay_attack(st, attacker_id, victim_id, ability)
    return big - int(hc.hp)


def _tune_hp_replay(sid, seed, attacker, victim, state_file, p_units, a_units, ability,
                    verbose=True):
    """PASSE 1 pour les vecteurs d'ABILITY : `aiPredict` (= `GetAllPredictions`) ne rend que la
    preview de l'ATTAQUE NORMALE -- MESURE : sur `FlailSwing`, il annonce [9393,14091] la ou le
    vecteur inflige REELLEMENT 20884 (3 coups de ~6960). Tuner les PV sur cette plage donnait un
    regime `dmg >= 2 x PV` = overkill NATUREL, donc NON discriminant pour `isForceOverkill` -- et
    le test passait pour la mauvaise raison.

    On mesure donc le degat REEL en rejouant le vecteur OFFLINE sur une cible a PV enormes (elle
    survit, `hp_before - hp_after` = le total), puis `PV = 80 % du total` : toute la dispersion du
    tirage reste LETALE (>= PV) et TRES en-dessous du seuil (pct ~ 25 % << 100 %)."""
    key = ("replay", attacker, victim, tuple(p_units), tuple(a_units), int(ability))
    if key in _BAND_CACHE:
        return _BAND_CACHE[key]
    rid = None
    try:
        rid, ids = setup(sid, state_file, seed, attacker, victim, list(p_units), list(a_units),
                         (3, 4), hp_target=200000, crit_spec="0,0", verbose=False, check_hp=False)
        cap = _capture(sid, rid)
        vid = by_visual(cap["dec"], victim)["id"]
        st = _load(cap)
        hc = st.get_entity(int(vid)).get_component(HealthComponent)
        before = int(hc.hp)
        _replay_attack(st, ids[attacker], vid, ability)
        total = before - int(hc.hp)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if total <= 0:
        raise RuntimeError("rejeu offline sans degat (%s / ability %s)" % (attacker, ability))
    hp = max(1, int(total * 0.8))
    if verbose:
        print("[178] tune-replay %s ability %s -> %s : total %d => PV = %d (2 x PV = %d)"
              % (attacker, ability, victim, total, hp, 2 * hp))
    _BAND_CACHE[key] = (hp, total)
    return _BAND_CACHE[key]


def setup(sid, state_file, seed, attacker, victim, p_units, a_units, center,
          hp_target=400, crit_spec="0,0", verbose=True, check_hp=True):
    """Build + GEOMETRIE DRIVEE : victime au centre, les autres acteurs sur son ring 1."""
    rid = build(state_file, seed, p_units, a_units, hp_target, crit_spec)
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < 3:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring)))
    dv = view(sid, rid)
    names = list(dict.fromkeys(list(p_units) + list(a_units)))
    ids = {}
    for v in names:
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = u["id"]
    # `FILLER` (2e ennemi) tenu HORS de portee : il n'existe que pour que la bataille continue.
    if FILLER in ids:
        move(sid, rid, ids[FILLER], 6, 7)
    move(sid, rid, ids[victim], ccol, crow)
    slot = 0
    for v in names:
        if v in (victim, FILLER):
            continue
        move(sid, rid, ids[v], *ring[slot])
        slot += 1
    dv = view(sid, rid)
    for v, uid in ids.items():
        u = next(x for x in dv["units"] if int(x["id"]) == int(uid))
        if verbose:
            print("[178]   u%-3d %-18s pos=%s hp=%s eff=%s"
                  % (uid, v, u.get("pos"), u.get("hp"),
                     [e.get("name") for e in (u.get("effects") or [])]))
        if check_hp and v == victim and int(u.get("hp") or 0) != int(hp_target):
            # GARDE anti-pollution : un tir d'overwatch pendant le placement fausserait la mesure.
            raise RuntimeError("SETUP POLLUE : la victime a %s PV au lieu de %s"
                               % (u.get("hp"), hp_target))
    return rid, ids


def _capture(sid, rid):
    return {"dec": view(sid, rid),
            "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120),
            "bg": _r(sid, "boardGraph", {"runnerId": rid}, 60),
            # MT du runner AVANT le coup live -> le rejeu offline tire la MEME valeur (replay-diff).
            "rng": _r(sid, "dumpRng", {"runnerId": rid}, 30)}


def run(case: str, seed: int = 17811, center=(3, 4), state_file=None,
        keep: bool = False, verbose: bool = True) -> dict:
    """MONTAGE A (crescendo) d'un regime, reutilisable (le probe EST la fixture).

    Rend `{"case", "victim", "rid", "hp", "dmg_min", "dmg_max", "live_level_before",
    "live_level_after", "live_overkill", "port_overkill", "port_replay_overkill", "legacy_overkill",
    "can_be_overkilled", "prevent_overkill", "is_crit_regime", "lethal_below_threshold"}`
    -- ou `{"error": ...}` si le regime n'est pas atteint."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "ovk178.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    spec = CASES[case]
    victim, attacker, crit_spec = spec["victim"], spec["attacker"], spec["crit"]
    hp_target = spec["hp"]
    rid = None
    try:
        if hp_target is None:
            hp_target = _tune_hp(sid, seed + 500, attacker, victim, sf,
                                 [SHIRON, KILLER], [victim, FILLER], verbose=verbose)[0]
        rid, ids = setup(sid, sf, seed, attacker, victim, [SHIRON, KILLER], [victim, FILLER],
                         center, hp_target=hp_target, crit_spec=crit_spec, verbose=verbose)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp, lvl0 = int(vic["hp"]), crescendo_level(dv, ids[SHIRON])
        dmin, dmax = predicted_damage(sid, rid, ids[SHIRON], vic["id"])
        if dmin is None:
            return {"error": "aiPredict illisible (%s)" % case}
        cap = _capture(sid, rid)
        attack(sid, rid, ids[SHIRON], vic["id"])
        dv2 = view(sid, rid)
        lvl1 = crescendo_level(dv2, ids[SHIRON])
        if not killed_by(dv2, vic["id"], ids[SHIRON]):
            return {"error": "%s : la victime n'a pas ete tuee par Shiron" % case}
        live = (lvl1 - lvl0) > 0
        old = _legacy_is_overkill(hp, dmin)
        is_crit = crit_spec.split(",")[0] != "0"
        new, cbo, prv = offline_verdict(cap, vic["id"], hp, dmin, is_critical=is_crit)
        rflag, rtotal, rcrits, rhp = replay_flag(cap, ids[SHIRON], vic["id"])
        out = {"case": case, "victim": victim, "rid": rid, "hp": hp,
               "dmg_min": dmin, "dmg_max": dmax,
               "live_level_before": lvl0, "live_level_after": lvl1, "live_overkill": live,
               "port_overkill": bool(new), "port_replay_overkill": bool(rflag),
               "replay_total": rtotal, "replay_crits": rcrits, "replay_hp_after": rhp,
               "legacy_overkill": bool(old),
               "can_be_overkilled": bool(cbo), "prevent_overkill": bool(prv),
               "is_crit_regime": is_crit,
               "lethal_below_threshold": bool(dmin >= hp and dmax < 2 * hp),
               # GARDE-FOU (cf. `replay_damage_total`) : c'est le degat REEL du coup rejoue, pas la
               # preview, qui doit etre letal ET sous le seuil pour que le regime discrimine.
               # `replay_total` = `_run_hits.total` = degat CALCULE (non tronque par les PV).
               "replay_below_threshold": bool(hp <= rtotal < 2 * hp)}
        if verbose:
            print("[178] %s : PV=%d degat=[%s,%s] seuil=%d%% crit=%s"
                  % (case, hp, dmin, dmax, _overkill_threshold_pct(), crit_spec))
            print("[178]   gates offline : can_be_overkilled=%s prevent_overkill=%s" % (cbo, prv))
            print("[178]   corps SUPPRIME (2 args)      -> overkill=%s" % old)
            print("[178]   corps LIVRE  (unit_is_overkill) -> overkill=%s" % new)
            print("[178]   REJEU port (flag reel)       -> overkill=%s (total=%s crits=%s hp=%s)"
                  % (rflag, rtotal, rcrits, rhp))
            print("[178]   LIVE crescendo %d -> %d       -> overkill=%s" % (lvl0, lvl1, live))
            print("[178]   ACCORD : rejeu=%s  supprime=%s" % (rflag == live, old == live))
        return out
    except RuntimeError as exc:
        return {"error": str(exc)}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def run_revive(case: str, seed: int = 17833, center=(3, 4), state_file=None,
               keep: bool = False, verbose: bool = True) -> dict:
    """MONTAGE B (revive Narthecium) -- observable INDEPENDANT du crescendo, et tueur SANS le trait
    `ThrillSeekers` : `ultraInceptorSgt` tue `genesPrimus`, `ultraApothecary` (allie de la victime,
    a <= 2 hex) revive **unless Overkilled**. La victime survit-elle ?"""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "ovk178rev.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    spec = REVIVE_CASES[case]
    crit_spec, attacker, ability = spec["crit"], spec["attacker"], spec["ability"]
    p_units = [attacker, FILLER]
    victim = "genesPrimus"
    rid = None
    try:
        if int(ability) == NORMAL_ATTACK:
            hp_target, _ = _tune_hp(sid, seed + 500, attacker, victim, sf,
                                    p_units, REVIVE_A_UNITS, verbose=verbose, ability=ability)
        else:
            hp_target, _ = _tune_hp_replay(sid, seed + 500, attacker, victim, sf,
                                           p_units, REVIVE_A_UNITS, ability, verbose=verbose)
        rid, ids = setup(sid, sf, seed, attacker, victim, p_units,
                         list(REVIVE_A_UNITS), center, hp_target=hp_target,
                         crit_spec=crit_spec, verbose=verbose)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp = int(vic["hp"])
        dmin, dmax = predicted_damage(sid, rid, ids[attacker], vic["id"], ability)
        if dmin is None:
            return {"error": "aiPredict illisible (%s)" % case}
        cap = _capture(sid, rid)
        attack(sid, rid, ids[attacker], vic["id"], ability)
        dv2 = view(sid, rid)
        u = next((x for x in (dv2.get("units") or []) if int(x["id"]) == int(vic["id"])), None)
        live_alive = bool(u and u.get("alive"))
        # REJEU port : la victime est-elle vivante apres l'attaque rejouee offline ?
        st = _load(cap)
        _replay_attack(st, ids[attacker], vic["id"], ability)
        ent = st.get_entity(int(vic["id"]))
        fl = ent.get_component(UnitFlagsComponent) if ent is not None else None
        hc = ent.get_component(HealthComponent) if ent is not None else None
        uc = ent.get_component(UnitComponent) if ent is not None else None
        port_alive = bool(uc is not None and uc.alive)
        # `replay_damage` = le degat REEL du vecteur (rejeu offline sur cible increvable), et non la
        # preview `aiPredict`. C'est LUI qui doit etre dans [PV, 2 x PV) pour que le regime soit
        # discriminant : la preview mentait de 30 % sur FlailSwing, et sans ce garde-fou le test
        # aurait valide un overkill NATUREL (`dmg >= 2 x PV`) en croyant mesurer le flag.
        out = {"case": case, "victim": victim, "rid": rid, "hp": hp,
               "dmg_min": dmin, "dmg_max": dmax, "ability": int(ability), "attacker": attacker,
               "live_alive": live_alive, "port_alive": port_alive,
               "port_overkill": bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED)),
               "port_hp_after": (hc.hp if hc is not None else None),
               "replay_damage": replay_damage_total(cap, ids[attacker], vic["id"], ability),
               "is_crit_regime": crit_spec.split(",")[0] != "0",
               "lethal_below_threshold": bool(dmin >= hp and dmax < 2 * hp)}
        out["replay_below_threshold"] = bool(
            out["replay_damage"] is not None and hp <= out["replay_damage"] < 2 * hp)
        if verbose:
            print("[178B] %s : PV=%d preview=[%s,%s] crit=%s ability=%s"
                  % (case, hp, dmin, dmax, crit_spec, ability))
            print("[178B]   degat REEL du vecteur (rejeu) = %s -> letal-sous-le-seuil=%s"
                  % (out["replay_damage"], out["replay_below_threshold"]))
            print("[178B]   LIVE victime vivante apres le coup letal -> %s" % live_alive)
            print("[178B]   REJEU port : vivante=%s overkill=%s hp=%s"
                  % (port_alive, out["port_overkill"], out["port_hp_after"]))
        return out
    except RuntimeError as exc:
        return {"error": str(exc)}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="both",
                    choices=tuple(CASES) + tuple(REVIVE_CASES) + ("both", "r33", "all"))
    ap.add_argument("--seed", type=int, default=17811)
    ap.add_argument("--center", default="3,4")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    center = tuple(int(x) for x in args.center.split(","))
    if args.case == "both":
        cases, rev = ("control", "titus"), ()
    elif args.case == "r33":
        cases, rev = ("nocrit", "crit"), ("revive-nocrit", "revive-crit")
    elif args.case == "all":
        cases, rev = tuple(CASES), tuple(REVIVE_CASES)
    elif args.case in CASES:
        cases, rev = (args.case,), ()
    else:
        cases, rev = (), (args.case,)
    oks = []
    for i, case in enumerate(cases):
        r = run(case, seed=args.seed + i, center=center, state_file=args.state_file,
                keep=args.keep)
        if "error" in r:
            print("[178] %s : %s" % (case, r["error"]))
            oks.append(False)
        else:
            oks.append(r["port_replay_overkill"] == r["live_overkill"])
    for i, case in enumerate(rev):
        r = run_revive(case, seed=args.seed + 20 + i, center=center,
                       state_file=args.state_file, keep=args.keep)
        if "error" in r:
            print("[178B] %s : %s" % (case, r["error"]))
            oks.append(False)
        else:
            oks.append(r["port_alive"] == r["live_alive"])
    print("[178] BILAN : %s" % ("OK" if oks and all(oks) else "ECHEC/INDETERMINE %s" % (oks,)))
    sys.exit(0 if (oks and all(oks)) else 1)


if __name__ == "__main__":
    main()
