#!/usr/bin/env python
"""Probe #902 -- confront LIVE des deux actives du `necroReanimator` (MACHINE OF WAR Necrons) :
`1223 ReanimationBeam` et `1224 NanoscarabRepairProtocols`.

MONTAGE : le porteur est `kind: lineup` et HORS du pool (`rl_duel build --list-pool` : 8 MoW
spawnables, pas lui) -> injection catalogue (`catalog_inject --units necroReanimator`) puis
`build --seed-bc <inj> --p-mow necroReanimator`. Le board doit porter un slot `MachineOfWarPosition`
des deux cotes (`C1_02`). Le chemin `--explicit-stats necroNpcMoWReanimator` (formule NPC) n'a PAS
ete retenu : l'injection lineup donne l'entree de CATALOGUE de l'unite JOUABLE (donc ses vraies
`level`/`multiplier` d'ability -- mesure : `level=50 multiplier=160`), la ou la voie NPC substitue un
porteur different dont rien ne garantit qu'il partage la config d'ability.

TROIS phases, trois TEMOINS distincts :

  * `--phase gates`  : ORACLE NATIF `abilityTargets(...).fromHere` (la query native de legalite,
                       PAS le port) confronte, unite par unite, au verdict du port
                       (`targeting.get_invalid_target_reason`). Joue AVANT et APRES un marquage, ce
                       qui exerce les DEUX branches des deux gates dynamiques.
  * `--phase nrp`    : cast 1224 -- delta de PV et effets poses, offline vs live.
  * `--phase beam`   : cast 1223 sur DEUX machines marquees et ENDOMMAGEES : le discriminant est que
                       le natif repare **toutes** les machines marquees, pas la cible du cast.

CE QUE CES TEMOINS NE VOIENT PAS (dit explicitement, cf. le rapport) : la RESURRECTION de l'effet
1547 (sa classe d'effet n'est pas portee -- l'effet est POSE des deux cotes, il n'agit d'aucun cote).

⚠ ET UN ANGLE MORT **STRUCTUREL**, mesure : sur 1223, le slot `Actor@+0x40` du volet [C] n'est PAS
distinguable de `Target`/`Caster`. Cause LUE, pas supposee --
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` commence par
`if (options.isSelfCasting != 0) return caster;`, et 1223 a `isSelfCasting = 1` : la cible EFFECTIVE
d'un cast de 1223 est TOUJOURS le caster (verifie au diagnostic : `target_id=53 ctx.target=53
ctx.actor=53`). Le mutant « `Actor()` -> `Target()` » passe donc AVEUGLE, et c'est un fait du natif,
pas un trou du temoin. Ce que le temoin garde en revanche, et qui a trouve un VRAI bug : sans le fil
`actor_id=caster_id`, `ActorSelector` rend VIDE et le port ne pose AUCUN effet 1547 (mutant M8 : rc 1).

ASCII only (cp1252). Usage :
    python probe_902_reanimator.py --phase gates
    python probe_902_reanimator.py --phase nrp
    python probe_902_reanimator.py --phase beam
    python probe_902_reanimator.py --phase summons
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.entities.pathfinding.board import Board                       # noqa: E402
from engine.runner.abilities.handler import AbilityHandler                # noqa: E402
from engine.runner.abilities.targeting import get_invalid_target_reason   # noqa: E402
from engine.runner.components import (HealthComponent, StatsComponent,    # noqa: E402
                                      UnitComponent)
from engine.runner.messages import ActiveAbilityMessage                   # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                    # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402
from engine.entities.effect_type import EffectType                        # noqa: E402

REANIMATION_BEAM = 1223
NANOSCARAB_REPAIR_PROTOCOLS = 1224
MARKER = int(EffectType.NanoscarabRepairProtocols)          # 1545
EXTRA_HP = int(EffectType.NanoscarabRepairProtocols_ExtraHp)  # 1546
REVIVE = int(EffectType.ReanimationBeam_Revive)             # 1547

MOW = "necroReanimator"
ALLIES = "necroOverlord,necroSpyder,necroWarden"
FOES = "ultraTitus,ultraApothecary"
BOARD = "C1_02"


# --------------------------------------------------------------------------- helpers RPC / runner

def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _inject(out: Path) -> Path:
    subprocess.run([sys.executable, "catalog_inject.py", "--units", MOW, "--out", str(out)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not out.exists():
        print("[902] injection catalogue KO")
        sys.exit(2)
    return out


def _build(state_path: Path, extra: list, retries: int = 40) -> int:
    """`rl_duel build`. Le plafond MAX_RUNNERS est PARTAGE : `runner cap reached` n'est pas une
    erreur du probe mais une contention -> on ATTEND un slot (on ne dispose JAMAIS celui d'un autre).
    Un `503 runner creation paused` est une fenetre de maintenance : meme traitement."""
    for attempt in range(max(1, retries)):
        state_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)] + extra,
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if state_path.exists():
            return json.loads(state_path.read_text())["runnerId"]
        out = (proc.stderr or "") + (proc.stdout or "")
        if ("runner cap reached" in out or "runner creation paused" in out) and attempt + 1 < retries:
            print("[902] slot indisponible -- attente (%d/%d)" % (attempt + 1, retries), flush=True)
            time.sleep(20)
            continue
        print("[902] build KO:", out[-1200:])
        sys.exit(2)
    sys.exit(2)


def _dispose(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


def _capture(sid, rid):
    """`mkstate()` rebatit un etat OFFLINE neuf depuis les MEMES payloads (replay-diff)."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec


def _mow_id(dec) -> int | None:
    for m in (dec.get("mows") or []):
        if m.get("visualId") == MOW:
            return int(m.get("casterId") or m.get("machineId"))
    return None


def _units(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _by_visual(dec, visual):
    return next((int(u["id"]) for u in _units(dec) if u.get("visualId") == visual), None)


def _from_here(sid, rid, caster, ability):
    """Cibles LEGALES SANS bouger, ORACLE NATIF. JAMAIS `targets` (superset move-inclus, #111)."""
    at = _r(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 120)
    for u in (at.get("units") or []) + (at.get("mows") or []):
        if int(u.get("unitId") or u.get("casterId") or -1) != int(caster):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or ab.get("id") or -1) == int(ability):
                return {_tid(t) for t in (ab.get("fromHere") or [])}
    return None


def _tid(t):
    if isinstance(t, dict):
        for k in ("unitId", "entityId", "id", "targetId"):
            if t.get(k) is not None:
                return int(t[k])
        return None
    return int(t)


def _cast_live(sid, rid, caster, target, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(caster), "targetId": int(target),
        "abilityType": int(ability)}}, 120)


def _cast_offline(st, caster, target, ability):
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=None if target is None else int(target),
        ability_type=int(ability)))
    return h.last or {}


def _hp_of(dec):
    return {int(u["id"]): int(u.get("hp") or 0) for u in _units(dec)}


def _hp_offline(st):
    out = {}
    for eid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        hc = e.get_component(HealthComponent)
        if uc is not None and uc.alive and hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def _effects_of(dec, uid):
    """⚠ Une MoW n'est PAS indexee par `id` dans `decisionView` : sa ligne porte `id` (l'id de la
    MACHINE, 47) ET `casterId`/`machineId` (l'entite qui caste, 53). C'est `casterId` qui est l'id
    d'entite des messages -- chercher par `id` seul rend un ensemble VIDE et fait lire « effet absent »
    la ou il est present (faux negatif MESURE sur l'effet 1547 de cette tranche)."""
    for u in (dec.get("units") or []) + (dec.get("mows") or []):
        cand = {u.get("id"), u.get("machineId"), u.get("casterId")}
        if int(uid) in {int(c) for c in cand if c is not None}:
            return {int(e.get("type") or e.get("effectType") or -1)
                    for e in (u.get("effects") or [])}
    return set()


def _porteurs_offline(st, effect_type: int) -> set:
    """{id d'entite} portant `effect_type` dans l'ECS Python (`EffectsState.by_unit`)."""
    if st.effects is None:
        return set()
    return {int(uid) for uid, effs in st.effects.by_unit.items()
            if any(int(e.effect_type) == int(effect_type) for e in effs)}


def _porteurs_live(dec, effect_type: int) -> set:
    """Pendant LIVE : les MoW sont dans `dec.mows` (cle `casterId`), pas dans `dec.units`."""
    out = set()
    for u in (dec.get("units") or []):
        if effect_type in {int(e.get("type") or e.get("effectType") or -1)
                           for e in (u.get("effects") or [])}:
            out.add(int(u["id"]))
    for m in (dec.get("mows") or []):
        if effect_type in {int(e.get("type") or e.get("effectType") or -1)
                           for e in (m.get("effects") or [])}:
            out.add(int(m.get("casterId") or m.get("machineId")))
    return out


def _endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _aiturn(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


# --------------------------------------------------------------------------- phases

def _mount(state_path: Path, seedbc: Path, damaged: bool, harmless_foes: bool = False):
    extra = ["--seed", "777", "--board", BOARD, "--seed-bc", str(seedbc),
             "--p-mow", MOW, "--p-units", ALLIES, "--a-units", FOES, "--no-ai"]
    if harmless_foes:
        # Le montage SUMMONS a besoin de TROIS tours (spawn, 2 marquages, beam) et le summon mourait
        # avant le beam. On DRIVE la condition testee au lieu de la subir : `--dmg-target 0` rend les
        # ennemis inoffensifs SANS toucher a la mecanique mesuree (leur stat d'ATTAQUE, pas leurs PV
        # ni leurs traits) -- ils restent des cibles vivantes pour l'attaque libre du summon.
        extra += ["--dmg-target", "0"]
    if damaged:
        # DRIVE l'etat teste : on ne SUBIT pas des PV pleins qui rendraient le `Repair` inerte
        # (`AttackQuery$$EntityCanBeRepaired` refuse une unite sans PV manquants -- c'est ce qui a
        # rendu le 1er cast 1223 exploratoire silencieux). `RemainingHealth` seul : `Health` (le max)
        # reste intact, donc les PV MANQUENT vraiment.
        extra += ["--unit-stat",
                  "necroSpyder:RemainingHealth=2000;necroWarden:RemainingHealth=2000;"
                  "necroOverlord:RemainingHealth=2000"]
    return _build(state_path, extra)


def phase_gates(sid, state_path, seedbc):
    """ORACLE NATIF `abilityTargets.fromHere` vs PORT `get_invalid_target_reason`, sur TOUTES les
    unites vivantes, pour les DEUX abilities, AVANT et APRES un marquage.

    Le temoin DISCRIMINE : avant le marquage, 1223 n'accepte AUCUNE unite (aucune ne porte 1545) et
    1224 en accepte exactement 3 ; apres, les ensembles s'INVERSENT sur la cible marquee. Un port qui
    ignorerait le gate accepterait tout ; un port qui confondrait les deux gates les rendrait egaux."""
    rid = _mount(state_path, seedbc, damaged=False)
    ok = True
    for etape in ("avant marquage", "apres marquage"):
        mkstate, dec = _capture(sid, rid)
        st = mkstate()
        cid = _mow_id(dec)
        if cid is None:
            print("[902] MoW absente -- montage KO")
            return False
        from engine.runner.abilities.handler import ABILITY_CLASSES
        for ability in (REANIMATION_BEAM, NANOSCARAB_REPAIR_PROTOCOLS):
            natif = _from_here(sid, rid, cid, ability)
            if natif is None:
                print("[902][gates] %s ability %d : fromHere INDISPO -- non confronte"
                      % (etape, ability))
                continue
            cls = ABILITY_CLASSES.get(ability)
            port = set()
            for u in _units(dec):
                uid = int(u["id"])
                if get_invalid_target_reason(st, cid, uid, cls()) == 0:
                    port.add(uid)
            # Le self-cast (`isSelfCasting=1` de 1223) passe par `GetCasterNotAddedReason`, un
            # chemin que ce temoin n'exerce pas cote port (le caster est une MoW, absente de
            # `dec.units`) -> on le retire de l'ORACLE avant comparaison, et on le DIT.
            natif_units = {t for t in natif if t != cid}
            marque = "=" if natif_units == port else "!"
            print("[902][gates] %-15s ability %d : natif(fromHere)=%s port=%s %s"
                  % (etape, ability, sorted(natif_units), sorted(port), marque))
            if cid in natif:
                print("             (+ self-cast %d dans l'oracle natif, ecarte : chemin "
                      "GetCasterNotAddedReason, hors de ce temoin)" % cid)
            ok = ok and (natif_units == port)
        if etape == "avant marquage":
            tgt = _by_visual(dec, "necroSpyder")
            _cast_live(sid, rid, cid, tgt, NANOSCARAB_REPAIR_PROTOCOLS)
            _endturn(sid, rid)
            _aiturn(state_path)
    return ok


def phase_nrp(sid, state_path, seedbc):
    """1224 : delta de PV et effets poses, OFFLINE vs LIVE, sur le MEME etat de depart."""
    rid = _mount(state_path, seedbc, damaged=True)
    mkstate, dec = _capture(sid, rid)
    cid = _mow_id(dec)
    tgt = _by_visual(dec, "necroSpyder")
    if cid is None or tgt is None:
        print("[902] montage KO (mow=%s cible=%s)" % (cid, tgt))
        return False

    st = mkstate()
    hp_before_off = _hp_offline(st)
    diag = _cast_offline(st, cid, tgt, NANOSCARAB_REPAIR_PROTOCOLS)
    hp_after_off = _hp_offline(st)
    d_off = {u: hp_after_off[u] - hp_before_off.get(u, 0)
             for u in hp_after_off if hp_after_off[u] != hp_before_off.get(u)}
    eff_off = {e.effect_type for e in (st.effects.by_unit.get(int(tgt)) or [])}

    hp_before_live = _hp_of(dec)
    _cast_live(sid, rid, cid, tgt, NANOSCARAB_REPAIR_PROTOCOLS)
    _mk2, dec2 = _capture(sid, rid)
    hp_after_live = _hp_of(dec2)
    d_live = {u: hp_after_live[u] - hp_before_live.get(u, 0)
              for u in hp_after_live if hp_after_live[u] != hp_before_live.get(u)}
    eff_live = _effects_of(dec2, tgt)

    print("[902][nrp] extra_hp(port) = %s" % diag.get("extra_hp"))
    print("[902][nrp] delta PV  offline=%s  live=%s  %s"
          % (d_off, d_live, "=" if d_off == d_live else "!"))
    print("[902][nrp] effets sur la cible : offline 1545=%s 1546=%s | live 1545=%s 1546=%s"
          % (MARKER in eff_off, EXTRA_HP in eff_off, MARKER in eff_live, EXTRA_HP in eff_live))
    ok = (d_off == d_live and d_off.get(int(tgt), 0) == int(diag.get("extra_hp") or -1)
          and MARKER in eff_off and MARKER in eff_live
          and EXTRA_HP in eff_off and EXTRA_HP in eff_live)
    print("[902][nrp] %s" % ("OK" if ok else "DIVERGENCE"))
    return ok


def phase_beam(sid, state_path, seedbc):
    """1223 : le DISCRIMINANT est la reparation de MASSE -- le natif repare TOUTES les machines
    alliees marquees 1545, pas la cible du cast. On en marque DEUX, on les laisse endommagees, et on
    cible la premiere : si le port ne lisait que `Target`, la seconde ne bougerait pas."""
    rid = _mount(state_path, seedbc, damaged=True)
    _mk, dec = _capture(sid, rid)
    cid = _mow_id(dec)
    a = _by_visual(dec, "necroSpyder")
    b = _by_visual(dec, "necroWarden")
    if cid is None or a is None or b is None:
        print("[902] montage KO (mow=%s a=%s b=%s)" % (cid, a, b))
        return False
    # deux marquages -> deux tours (une MoW n'agit qu'une fois par tour)
    for tgt in (a, b):
        _cast_live(sid, rid, cid, tgt, NANOSCARAB_REPAIR_PROTOCOLS)
        _endturn(sid, rid)
        _aiturn(state_path)

    mkstate, dec = _capture(sid, rid)
    st = mkstate()
    hp_before_off = _hp_offline(st)
    revive_before_off = _porteurs_offline(st, REVIVE)
    diag = _cast_offline(st, cid, a, REANIMATION_BEAM)
    hp_after_off = _hp_offline(st)
    d_off = {u: hp_after_off[u] - hp_before_off.get(u, 0)
             for u in hp_after_off if hp_after_off[u] != hp_before_off.get(u)}
    revive_off = _porteurs_offline(st, REVIVE) - revive_before_off

    hp_before_live = _hp_of(dec)
    revive_before_live = _porteurs_live(dec, REVIVE)
    _cast_live(sid, rid, cid, a, REANIMATION_BEAM)
    _mk2, dec2 = _capture(sid, rid)
    hp_after_live = _hp_of(dec2)
    d_live = {u: hp_after_live[u] - hp_before_live.get(u, 0)
              for u in hp_after_live if hp_after_live[u] != hp_before_live.get(u)}
    revive_live = _porteurs_live(dec2, REVIVE) - revive_before_live

    print("[902][beam] PV avant le beam : %s"
          % {int(u["id"]): "%s/%s" % (u.get("hp"), u.get("maxHp"))
             for u in _units(dec) if u.get("ctrl")})
    print("[902][beam] amount(port) = %s ; repairs = %s"
          % (diag.get("amount"), diag.get("repairs")))
    print("[902][beam] delta PV  offline=%s  live=%s  %s"
          % (d_off, d_live, "=" if d_off == d_live else "!"))
    print("[902][beam] cible du cast = %d ; l'AUTRE machine marquee = %d" % (a, b))
    # LE DISCRIMINANT : le natif repare des machines marquees qui NE SONT PAS la cible du cast. Un
    # port qui aurait lu `Target` au lieu de `Repairable(carriers)` ne les toucherait pas. Le critere
    # « au moins 2 unites » serait FAUX ici : la cible peut etre PLEINE (LivingMetal regenere entre
    # les tours), et c'est justement ce regime qui rend le temoin le plus tranchant -- la SEULE unite
    # reparee est alors celle que le port naif ignorerait.
    hors_cible = set(d_live) - {int(a)}
    print("[902][beam] unites reparees HORS de la cible du cast : %s" % sorted(hors_cible))
    # ⚠ CE VOLET A ETE AJOUTE PARCE QU'UN MUTANT L'A EXIGE : le temoin ne lisait que le cote LIVE,
    # donc le mutant « `AddEffect(1547, Actor())` -> `Target()` » passait AVEUGLE (rc 0). Un porteur
    # confronte DES DEUX COTES le fait rougir : l'acteur est la MoW, la cible une unite.
    print("[902][beam] porteurs NEUFS de 1547 : offline=%s live=%s %s (acteur attendu = %d)"
          % (sorted(revive_off), sorted(revive_live),
             "=" if revive_off == revive_live else "!", cid))
    ok = (d_off == d_live) and bool(hors_cible) and revive_off == revive_live
    print("[902][beam] %s" % ("OK" if ok else "DIVERGENCE"))
    return ok


def phase_summons(sid, state_path, seedbc):
    """Volet [B] de 1223 : un SUMMON mecanique marque agit (Attack OVERRIDE + PerformAIAction).
    `necroOverlord` invoque `necroSmnWarrior` (1009), on le marque, puis on tire le beam."""
    rid = _mount(state_path, seedbc, damaged=True, harmless_foes=True)
    _mk, dec = _capture(sid, rid)
    cid = _mow_id(dec)
    ov = _by_visual(dec, "necroOverlord")
    if cid is None or ov is None:
        print("[902] montage KO")
        return False
    # ⚠ ORDRE CONTRAINT PAR LA DUREE DE VIE DU SUMMON, et il a fallu le MESURER : marquer le summon
    # puis le `necroSpyder` lui coutait DEUX tours d'attente et il ne survivait pas jusqu'au beam
    # (« le summon est mort avant le beam », y compris avec des ennemis rendus inoffensifs). On marque
    # donc la machine NON-summon EN PREMIER, avant meme de l'invoquer.
    #
    # ⚠ ON MARQUE **DEUX** MACHINES, et la seconde n'est PAS un summon : sans elle, `carriers` et
    # `UnitsWithTrait(carriers, Summon)` sont le MEME ensemble, et le mutant « retirer le filtre
    # Summon » passe AVEUGLE (mesure M11). Avec le `necroSpyder` marque, un port qui perdrait le
    # filtre le ferait attaquer lui aussi -> les degats divergent.
    spy = _by_visual(dec, "necroSpyder")
    if spy is not None:
        _cast_live(sid, rid, cid, spy, NANOSCARAB_REPAIR_PROTOCOLS)
        _endturn(sid, rid)
        _aiturn(state_path)
        _mk, dec = _capture(sid, rid)
    before = {int(u["id"]) for u in _units(dec)}
    _cast_live(sid, rid, ov, ov, 1009)                       # ResurrectionOrb : SELF-cast
    _mk, dec = _capture(sid, rid)
    born = sorted({int(u["id"]) for u in _units(dec)} - before)
    print("[902][summons] summons apparus : %s" % born)
    if not born:
        print("[902][summons] NON CONFRONTE -- aucun summon (hexes libres ? formule a 0)")
        return None
    smn = born[0]
    _cast_live(sid, rid, cid, smn, NANOSCARAB_REPAIR_PROTOCOLS)
    _endturn(sid, rid)
    _aiturn(state_path)
    mkstate, dec = _capture(sid, rid)
    if smn not in {int(u["id"]) for u in _units(dec)}:
        print("[902][summons] NON CONFRONTE -- le summon est mort avant le beam")
        return None
    st = mkstate()
    hp_foes_before = {int(u["id"]): int(u.get("hp") or 0) for u in _units(dec) if not u.get("ctrl")}
    diag = _cast_offline(st, cid, smn, REANIMATION_BEAM)
    # ⚠ CE TEMOIN COMPARE LES DEUX COTES, et il a fallu le REPARER pour cela : sa 1re version ne
    # regardait que les degats LIVE, donc aucun mutant du PORT (statPart, trait Summon, asGroup,
    # stat de l'override) ne pouvait la faire rougir. On confronte desormais {cible -> degats}.
    port_hits: dict = {}
    for r in ((diag.get("summons") or {}).get("results") or []):
        atk = (r or {}).get("attack") or {}
        if atk.get("target") is not None and atk.get("total"):
            port_hits[int(atk["target"])] = port_hits.get(int(atk["target"]), 0) + int(atk["total"])
    acteurs = {int(r["uid"]) for r in ((diag.get("summons") or {}).get("results") or [])
               if r.get("uid") is not None}
    print("[902][summons] acteurs (port) = %s ; attendu = {%d} (le SEUL summon marque ; le "
          "`necroSpyder` est marque mais n'a PAS le trait Summon)" % (sorted(acteurs), smn))
    res = _cast_live(sid, rid, cid, smn, REANIMATION_BEAM)
    _mk2, dec2 = _capture(sid, rid)
    hp_foes_after = {int(u["id"]): int(u.get("hp") or 0) for u in _units(dec2) if not u.get("ctrl")}
    hit = {u: hp_foes_before[u] - hp_foes_after.get(u, 0)
           for u in hp_foes_before if hp_foes_after.get(u, 0) != hp_foes_before[u]}
    print("[902][summons] degats aux ENNEMIS : port=%s live=%s %s"
          % (port_hits, hit, "=" if port_hits == hit else "! (etage IA, cf. ci-dessous)"))
    print("[902][summons] mutated=%s" % res.get("mutated"))
    # DECOUPAGE PAR ETAGE, assume et ecrit : **l'arbre DSL de 1223 decide QUI agit** (le filtre
    # `UnitsWithTrait(carriers, Summon)`), **`ComputerActionOperation` decide OU et SUR QUI**. Le 1er
    # etage est de cette tranche et il est GARDE strictement ; le second est un mirror PARTAGE du
    # moteur d'utilite natif, deja approxime (residu #338, meme famille que
    # `perform_ai_attack_from_current_position`) -- il est MESURE et RAPPORTE, jamais fitte ici.
    # Mesure des deux regimes : un seul summon en jeu -> accord EXACT port {49: 3680} == live
    # {49: 3680} ; deux summons (dont un seul marque) -> le port choisit u51, le natif u49.
    ok = bool(hit) and acteurs == {int(smn)}
    if port_hits != hit:
        print("[902][summons] ECART D'ETAGE (choix de cible de l'IA), HORS du perimetre de l'arbre "
              "porte : l'ensemble des ACTEURS, lui, concorde -- c'est ce que garde ce probe.")
    print("[902][summons] %s" % ("OK" if ok else "DIVERGENCE"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=("gates", "nrp", "beam", "summons"))
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    a = ap.parse_args()

    root = PYDIR.parents[1]
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    seedbc = _inject(logs / "seedbc_reanimator_902.json")
    state_path = Path(a.state_file) if a.state_file else (logs / ("rb902_%s.json" % a.phase))
    sid = _resolve_session()
    try:
        res = {"gates": phase_gates, "nrp": phase_nrp, "beam": phase_beam,
               "summons": phase_summons}[a.phase](sid, state_path, seedbc)
    finally:
        if not a.keep:
            _dispose(state_path)
    if res is None:
        print("[902] phase %s : NON CONFRONTE" % a.phase)
        sys.exit(0)
    print("[902] phase %s : %s" % (a.phase, "PROBE OK" if res else "PROBE KO"))
    sys.exit(0 if res else 1)


if __name__ == "__main__":
    main()
