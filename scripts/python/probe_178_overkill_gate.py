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
     `IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled` = `HasFlagAbilityTrigger(target, 8)`.
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

REGIME << LETAL SOUS LE SEUIL >> : la PASSE 1 (`_measure_live_damage`) monte un runner JETABLE a la
MEME seed, MEME composition et MEME geometrie que le regime mesure, mais avec la victime INCREVABLE
(`--hp-target 200000`) ; elle caste le vecteur EN LIVE et lit `hp_avant - hp_apres`. C'est le degat
REEL du vecteur, non tronque par la mort. Les PV du regime valent alors `95 % de ce degat` : le coup
est LETAL (marge 5 %) et TRES en-dessous du seuil (`overkillDmgPctOfHealth` = 100 % exigerait
`degat >= 2 x PV`, soit 1,9 x le degat mesure) -> le verdict ne depend plus du tirage, seulement du
flag crit.

POURQUOI PAS `aiPredict`/`aiPlaybookPredict` (#268) : sur le build `rnca9r7q6c`, le DECODEUR du
struct de prediction lit des offsets PERIMES et rend `[1,100]` pour TOUT couple -- les bornes de
degat, `mightCrit`, `preventOverkill` et `probability` sont du GARBAGE (`hpBefore` et `armorBefore`
sont les seuls champs encore justes). C'est ce canal mort, et non un roster mal choisi, qui faisait
dire au tuning << plage [1,100] trop large >>. Detail et offsets re-derives :
`docs/rl/case-268-decodeur-prediction-perime.md`.

Le tirage de degat est REPRODUCTIBLE a seed + sequence d'actions egales -- mesure du 2026-07-30 :
trois runners de seed 17811 rendent `2375 / 2375 / 2375`, et trois seeds voisines rendent
`2375 / 2575 / 3051`. La passe 1 rend donc le tirage EXACT que la passe 2 produira.

`--crit "CC,CD"` patche CritChance/CritDamage des p-units : `100,1` = crit garanti pour +1 de base
d'attaque (degat quasi inchange), `0,0` = `CouldCrit` faux (GetStat(10) == 0) donc AUCUN crit
possible, meme si un effet ajoute de la crit-chance. La PASSE 1 mesure TOUJOURS a `0,0` : les PV du
regime sont donc les memes pour la paire `crit`/`nocrit`, ce qui rend la paire comparable.

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


def prediction_channel_health(sid, rid, attacker_id, target_id, ability=NORMAL_ATTACK) -> dict:
    """SANTE du canal `aiPredict` -- diagnostic seul, AUCUN verdict n'en depend (#268).

    Le decodeur du struct de prediction (`frida/hooks/features/ai-step/rpc-predict.ts`) fige les
    offsets d'un build ancien ; sur `rnca9r7q6c` il rend `[1,100]` pour tout couple. Trois
    SENTINELLES suffisent a le dire sans rien deviner :
      * `hpBefore` doit egaler les PV reels de la cible (champ encore juste) ;
      * `mightCrit` est un `bool` : toute valeur hors {0,1} prouve que la lecture a derape ;
      * un vecteur qui inflige des degats ne peut pas annoncer `healthDmgMax == 0`.
    Rend `{"alive": bool, "pred": ..., "why": ...}` -- `alive=False` = canal MORT."""
    p = (_r(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker_id),
                               "targetId": int(target_id), "abilityType": int(ability)}, 90)
         or {}).get("pred") or {}
    if not p:
        return {"alive": False, "pred": None, "why": "aiPredict ne rend aucune prediction"}
    why = []
    if int(p.get("mightCrit") or 0) not in (0, 1):
        why.append("mightCrit=%s hors {0,1}" % p.get("mightCrit"))
    if int(p.get("healthDmgMax") or 0) <= 0:
        why.append("healthDmgMax=%s alors que le vecteur inflige des degats"
                   % p.get("healthDmgMax"))
    return {"alive": not why, "pred": p, "why": " ; ".join(why) or "sentinelles OK"}


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


# Fraction du degat REEL retenue comme PV du regime << letal sous le seuil >>. 5 % de marge de
# LETALITE (le coup doit rester >= PV) contre 90 % de marge sous le SEUIL (il faudrait
# `degat >= 2 x PV`, soit 1,9 x le degat mesure, pour que l'overkill devienne NATUREL).
_LETHAL_FRACTION = 0.95

_DMG_CACHE: dict = {}     # (seed, attaquant, victime, compo, ability) -> degat REEL mesure LIVE


def _measure_live_damage(sid, seed, attacker, victim, state_file, p_units, a_units, center,
                         ability=NORMAL_ATTACK, crit_spec="0,0", verbose=True):
    """PASSE 1 -- DEGAT REEL DU VECTEUR, MESURE **LIVE** (aucune prediction, aucun rejeu offline).

    Monte un runner JETABLE a la MEME seed, MEME composition et MEME geometrie que le regime
    mesure, mais avec la victime INCREVABLE (`--hp-target 200000`), caste le vecteur EN LIVE et
    lit `hp_avant - hp_apres`. La victime survivant, la lecture donne le degat CALCULE du vecteur
    entier (tous ses coups), non tronque par la mort -- exactement la grandeur que
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` compare a `targetInitialHealth`.

    Remplace les DEUX anciennes passes 1 :
      * `_tune_hp`, qui lisait `aiPredict` -- canal MORT sur `rnca9r7q6c` (#268) ;
      * `_tune_hp_replay`, qui rejouait le vecteur OFFLINE -- donc le PORT tunait le montage
        cense l'eprouver. Ici les deux bouts sont LIVE.

    Les PV du regime sont TOUJOURS calibres sur la mesure a `--crit 0,0` : la paire `crit`/`nocrit`
    partage ainsi ses PV (le crit majore le degat, jamais les PV) et reste comparable. Appelee une
    seconde fois avec le `crit_spec` du regime, elle rend le degat REEL de CE regime -- celui qui
    doit tomber dans `[PV, 2 x PV)`."""
    key = (int(seed), attacker, victim, tuple(p_units), tuple(a_units), int(ability), crit_spec)
    if key in _DMG_CACHE:
        return _DMG_CACHE[key]
    rid = None
    try:
        rid, ids = setup(sid, state_file, seed, attacker, victim, list(p_units),
                         list(a_units), center, hp_target=200000, crit_spec=crit_spec,
                         verbose=False, check_hp=False)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp_before = int(vic["hp"])
        attack(sid, rid, ids[attacker], vic["id"], ability)
        dv2 = view(sid, rid)
        u = next((x for x in (dv2.get("units") or []) if int(x["id"]) == int(vic["id"])), None)
        if u is None or u.get("hp") is None:
            raise RuntimeError("passe 1 : victime %s illisible apres le cast" % victim)
        if not u.get("alive"):
            raise RuntimeError("passe 1 : la victime increvable (%d PV) est MORTE -- le degat "
                               "depasse le plafond, la mesure serait tronquee" % hp_before)
        total = hp_before - int(u["hp"])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if total <= 0:
        raise RuntimeError("passe 1 : le vecteur %s ability %s n'a inflige AUCUN degat a %s "
                           "(hors de portee ? cast refuse ?)" % (attacker, ability, victim))
    hp = max(1, int(total * _LETHAL_FRACTION))
    if verbose:
        print("[178] passe 1 LIVE %s ability %s crit %s -> %s : degat REEL %d => PV = %d "
              "(2 x PV = %d)" % (attacker, ability, crit_spec, victim, total, hp, 2 * hp))
    _DMG_CACHE[key] = (hp, total)
    return _DMG_CACHE[key]


REVIVE_P_UNITS = (KILLER, FILLER)         # aucun porteur de ThrillSeekers sur le plateau
REVIVE_A_UNITS = ("genesPrimus", APOTHECARY)


def _replay_attack(st, attacker_id, victim_id, ability=NORMAL_ATTACK):
    """Rejoue OFFLINE le vecteur d'attaque du regime sur l'etat `st` (attaque normale ou ability).

    ⚠ #277 -- LA VOIE D'ABILITY PASSE PAR `Runner.apply`, JAMAIS PAR `execute_behaviour` A LA MAIN.
    Le natif n'a qu'UN point d'entree de cast (`IdunBattle.Operations.ActiveAbilityOperation$$
    ExecuteInternal`), qui emet `On(0x2a = PreUnitAbility)` AVANT la behaviour. Cote port ce vecteur
    est emis par `AbilityHandler.visit_ActiveAbilityMessage` : appeler `FlailSwingAbility().
    execute_behaviour(...)` directement SAUTE l'emission, donc saute le `PickRandomly` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
    (`min(|pool|, 2)` tirages, case-207) que `deathBlightlord` paie a chaque cast. Le flux RNG du
    rejeu demarrait alors `|pool|` tirages TROP TOT et les coups d'arme lisaient la mauvaise fenetre :
    seed 17833, montage `revive-flail`, port 21680 contre live 21023 (+3,1 %) -- un ecart de
    DECALAGE, pas de formule (cellule, percage, armure et `GetStat(Attack)` sont IDENTIQUES des deux
    cotes). Re-derivation : `python probe_277_flail_damage_stages.py --seeds 17833 --regimes k1,k0`.

    La voie d'ATTAQUE NORMALE, elle, emet deja `On(0x2a = PreUnitAbility)` DANS `AttackDamageOperation$$Execute`
    (`damage_ops/normal.py`, marqueur `ability_type = 1013`) : elle n'a jamais eu ce trou et reste
    sur l'appel d'operation, pour ne pas ajouter au regime les vecteurs after-hit/turn-flow que le
    `Runner` poserait en plus."""
    from engine.runner.operations.damage import AttackDamageOperation
    if int(ability) == FLAIL_SWING:
        from engine.runner.runner import Runner
        from engine.runner.messages import ActiveAbilityMessage
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(int(attacker_id), int(victim_id), int(ability)))
        return getattr(runner.ability_handler, "last", None)
    return AttackDamageOperation.execute(st, int(attacker_id), int(victim_id), 20)


def replay_damage_total(cap, attacker_id, victim_id, ability=NORMAL_ATTACK):
    """Degat TOTAL que le PORT infligerait a une cible qui ne meurt pas : sur une copie de l'etat,
    on porte les PV de la victime tres haut avant de rejouer.

    ⚠ C'est un CONTREPOINT du port, jamais la reference du regime : le regime est installe et
    verifie sur le degat mesure LIVE (`_measure_live_damage`). Le publier a cote du degat live rend
    l'ecart port/natif visible sans que le port ne tune quoi que ce soit."""
    st = _load(cap)
    ent = st.get_entity(int(victim_id))
    hc = ent.get_component(HealthComponent) if ent is not None else None
    if hc is None or hc.hp is None:
        return None
    big = 10 ** 7
    hc.hp = big
    _replay_attack(st, attacker_id, victim_id, ability)
    return big - int(hc.hp)


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

    Rend `{"case", "victim", "rid", "hp", "live_damage", "base_damage", "live_level_before",
    "live_level_after", "live_overkill", "port_overkill", "port_replay_overkill", "legacy_overkill",
    "can_be_overkilled", "prevent_overkill", "is_crit_regime", "lethal_below_threshold",
    "above_threshold", "pred_channel"}` -- ou `{"error": ...}` si le regime n'est pas atteint.

    `live_damage` est le degat REEL du vecteur, MESURE LIVE en passe 1 (cible increvable), et non
    une prediction : c'est lui qui situe le regime par rapport a `overkillDmgPctOfHealth`."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "ovk178.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    spec = CASES[case]
    victim, attacker, crit_spec = spec["victim"], spec["attacker"], spec["crit"]
    hp_target = spec["hp"]
    p_units, a_units = [SHIRON, KILLER], [victim, FILLER]
    rid = None
    try:
        # PASSE 1a -- degat SANS crit : calibre les PV (partages par la paire crit/nocrit).
        base_hp, base_dmg = _measure_live_damage(sid, seed, attacker, victim, sf, p_units,
                                                 a_units, center, verbose=verbose)
        if hp_target is None:
            hp_target = base_hp
        # PASSE 1b -- degat REEL du regime (avec SON crit) : c'est lui qui doit etre dans
        # [PV, 2 x PV) pour un regime letal-sous-le-seuil, ou >= 2 x PV pour un overkill NATUREL.
        live_damage = base_dmg if crit_spec == "0,0" else _measure_live_damage(
            sid, seed, attacker, victim, sf, p_units, a_units, center,
            crit_spec=crit_spec, verbose=verbose)[1]
        rid, ids = setup(sid, sf, seed, attacker, victim, p_units, a_units,
                         center, hp_target=hp_target, crit_spec=crit_spec, verbose=verbose)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp, lvl0 = int(vic["hp"]), crescendo_level(dv, ids[SHIRON])
        health = prediction_channel_health(sid, rid, ids[SHIRON], vic["id"])
        cap = _capture(sid, rid)
        attack(sid, rid, ids[SHIRON], vic["id"])
        dv2 = view(sid, rid)
        lvl1 = crescendo_level(dv2, ids[SHIRON])
        if not killed_by(dv2, vic["id"], ids[SHIRON]):
            return {"error": "%s : la victime n'a pas ete tuee par Shiron (PV %d, degat LIVE "
                             "mesure %d)" % (case, hp, live_damage)}
        live = (lvl1 - lvl0) > 0
        old = _legacy_is_overkill(hp, live_damage)
        is_crit = crit_spec.split(",")[0] != "0"
        new, cbo, prv = offline_verdict(cap, vic["id"], hp, live_damage, is_critical=is_crit)
        rflag, rtotal, rcrits, rhp = replay_flag(cap, ids[SHIRON], vic["id"])
        out = {"case": case, "victim": victim, "rid": rid, "hp": hp,
               "live_damage": live_damage, "base_damage": base_dmg,
               "live_level_before": lvl0, "live_level_after": lvl1, "live_overkill": live,
               "port_overkill": bool(new), "port_replay_overkill": bool(rflag),
               "replay_total": rtotal, "replay_crits": rcrits, "replay_hp_after": rhp,
               "legacy_overkill": bool(old),
               "can_be_overkilled": bool(cbo), "prevent_overkill": bool(prv),
               "is_crit_regime": is_crit, "pred_channel": health,
               # Les deux regimes du fichier, tranches sur le degat MESURE LIVE :
               #   letal-sous-le-seuil = PV <= degat < 2 x PV  (le verdict depend d'un ARGUMENT) ;
               #   overkill NATUREL    = degat >= 2 x PV       (le verdict est vrai sans argument).
               "lethal_below_threshold": bool(hp <= live_damage < 2 * hp),
               "above_threshold": bool(live_damage >= 2 * hp),
               # CONTREPOINT du port sur le meme etat -- jamais une entree du regime.
               "replay_below_threshold": bool(hp <= rtotal < 2 * hp)}
        if verbose:
            print("[178] %s : PV=%d degat LIVE=%d (base nocrit %d) seuil=%d%% crit=%s"
                  % (case, hp, live_damage, base_dmg, _overkill_threshold_pct(), crit_spec))
            print("[178]   regime : letal-sous-le-seuil=%s  overkill-naturel=%s"
                  % (out["lethal_below_threshold"], out["above_threshold"]))
            print("[178]   gates offline : can_be_overkilled=%s prevent_overkill=%s" % (cbo, prv))
            print("[178]   corps SUPPRIME (2 args)      -> overkill=%s" % old)
            print("[178]   corps LIVRE  (unit_is_overkill) -> overkill=%s" % new)
            print("[178]   REJEU port (flag reel)       -> overkill=%s (total=%s crits=%s hp=%s)"
                  % (rflag, rtotal, rcrits, rhp))
            print("[178]   LIVE crescendo %d -> %d       -> overkill=%s" % (lvl0, lvl1, live))
            print("[178]   ACCORD : rejeu=%s  supprime=%s" % (rflag == live, old == live))
            print("[178]   canal aiPredict : %s (%s)" % (health["alive"], health["why"]))
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
        # PASSE 1a -- degat SANS crit : calibre les PV (partages par la paire revive-crit/nocrit).
        hp_target, base_dmg = _measure_live_damage(sid, seed, attacker, victim, sf, p_units,
                                                   REVIVE_A_UNITS, center, ability=ability,
                                                   verbose=verbose)
        # PASSE 1b -- degat REEL du regime, avec SON crit.
        live_damage = base_dmg if crit_spec == "0,0" else _measure_live_damage(
            sid, seed, attacker, victim, sf, p_units, REVIVE_A_UNITS, center, ability=ability,
            crit_spec=crit_spec, verbose=verbose)[1]
        rid, ids = setup(sid, sf, seed, attacker, victim, p_units,
                         list(REVIVE_A_UNITS), center, hp_target=hp_target,
                         crit_spec=crit_spec, verbose=verbose)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp = int(vic["hp"])
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
        # `live_damage` = le degat REEL du vecteur, MESURE LIVE sur cible increvable (passe 1) --
        # ni la preview `aiPredict` (canal mort, #268), ni le rejeu du port. C'est LUI qui doit
        # etre dans [PV, 2 x PV) pour que le regime soit discriminant : au-dessus, l'overkill est
        # NATUREL et le test validerait sans que le flag serve a rien.
        out = {"case": case, "victim": victim, "rid": rid, "hp": hp,
               "live_damage": live_damage, "base_damage": base_dmg,
               "ability": int(ability), "attacker": attacker,
               "live_alive": live_alive, "port_alive": port_alive,
               "port_overkill": bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED)),
               "port_hp_after": (hc.hp if hc is not None else None),
               # CONTREPOINT du port sur le meme etat -- jamais une entree du regime.
               "replay_damage": replay_damage_total(cap, ids[attacker], vic["id"], ability),
               "is_crit_regime": crit_spec.split(",")[0] != "0",
               "lethal_below_threshold": bool(hp <= live_damage < 2 * hp)}
        out["replay_below_threshold"] = bool(
            out["replay_damage"] is not None and hp <= out["replay_damage"] < 2 * hp)
        if verbose:
            print("[178B] %s : PV=%d degat LIVE=%d (base nocrit %d) crit=%s ability=%s"
                  % (case, hp, live_damage, base_dmg, crit_spec, ability))
            print("[178B]   letal-sous-le-seuil=%s   (contrepoint port : degat %s -> %s)"
                  % (out["lethal_below_threshold"], out["replay_damage"],
                     out["replay_below_threshold"]))
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
