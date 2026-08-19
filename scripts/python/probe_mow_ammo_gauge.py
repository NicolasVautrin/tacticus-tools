"""La jauge de MUNITIONS d'une Machine of War en runner isole -- CAUSE et LEVIER.

CRITERE : pourquoi la jauge ne monte-t-elle jamais dans un runner, et est-ce reparable cote
harnais, ou une propriete du mode de jeu ?

RE (decompile gqfc5mff6c, symboles) :

  * la jauge vit dans `IdunBattle.Entities.Components.PlayerComponent` @+0x6c (par JOUEUR,
    PAS par machine) -- lue par `IdunBattle.Core.Services.BattleQuery$$HasPlayerEnoughAmmo`
    (`return cost <= pc+0x6c`) et par
    `IdunBattle.View.FSM.VisualBattleQuery$$GetPlayerAmmoFromMachine` (qui prend une MoW en
    entree mais resout `EntityExtensions$$GetOriginalPlayer` -> `GetPlayerComponent` -> +0x6c) ;
  * elle est INITIALISEE une seule fois par `IdunBattle.Operations.AddPlayerOperation$$Execute`
    (`pc+0x6c = param_8`), et `IdunBattle.Operations.SetupGameOperation$$AddPlayers` lui passe
    `PlayerConfiguration+0x20` = le champ **`MachineOfWarAmmo`** de la BattleConfiguration ;
  * le SEUL autre ecrivain de +0x6c dans tout le binaire est
    `IdunBattle.Operations.SpendAmmoOperation$$Execute` :
    `pc+0x6c = Math.Max(pc+0x6c - cost, 0)` ; `pc+0x70 += cost`.
    **Aucune operation n'INCREMENTE +0x6c** : la jauge est monotone DECROISSANTE en bataille.

Donc rien de casse cote harnais : `data/seed-bc.json` capture une bataille ou les trois
`Player.Players[*].MachineOfWarAmmo` valent 0, et le runner reproduit fidelement une bataille a
zero munition. Le levier est la BC, pas le moteur.

Ce probe MESURE, dans l'ordre :

  1. phase AMMO=0  -- reproduction de la mesure de depart : `1223 ReanimationBeam` publie
     `ammoCost=1, hasAmmo=false`, le cast est ACCEPTE mais NO-OPE ;
  2. phase AMMO=1  -- meme runner, meme board, seul `MachineOfWarAmmo` change : `hasAmmo=true`,
     le cast MUTE, et l'effet **1547 ReanimationBeam_Revive** est reellement pose ;
  3. RAYON DE SOUFFLE de 1547 (`docs/rl/case-229` section 3) : que publie `readEffectsByUnit`
     aux DEUX canaux (defaut / `includeInactive`) une fois 1547 pose ? Temoin de canal =
     nombre d'entrees `active: false` tous types confondus ;
  4. la jauge ne remonte PAS : apres le spend (1 -> 0), N `endturn` et `hasAmmo` reste faux.

Prealable de ciblage, LU dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetDynamicInvalidTargetReason` :
la cible doit porter l'effet `0x609 = 1545 NanoscarabRepairProtocols` ET etre Mechanical,
sinon `reason = 2`. On caste donc `1224` AVANT `1223`, sur la meme cible.

Usage :  python probe_mow_ammo_gauge.py [--verbose] [--endturns 6]
ASCII only (console cp1252). Sorties dans `logs/` (jamais `data/`, qui ne porte que des ENTREES).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                              # noqa: E402
from catalog_inject import write_augmented_seed_bc                        # noqa: E402

CARRIER = "necroReanimator"          # MoW Necron, kit [ReanimationBeam, NanoscarabRepairProtocols]
BEAM = 1223                          # ActiveAbilityType.ReanimationBeam (0x4c7)
NANOSCARAB_ABILITY = 1224            # pose 1545, prerequis de ciblage de 1223
NANOSCARAB = 1545                    # EffectType.NanoscarabRepairProtocols (0x609)
BEAM_EFFECT = 1547                   # EffectType.ReanimationBeam_Revive (0x60b)
BOARD, SEED = "MC1_67", "777"
ALLIES = "admecDestroyer,necroDestroyer"     # allies MECHANICAL (le ciblage exige IsMechanical)
ENEMY = "worldKharn"

LOGS = ROOT / "logs"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(sid, method, body=None, timeout=120):
    return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_bc(ammo: int) -> Path:
    """Seed BC augmente du porteur ET dote de `MachineOfWarAmmo = ammo` sur les joueurs non
    Environment (`PlayerType != 2`). Le seed partage n'est jamais touche."""
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = ammo
    out = LOGS / f"_probe_mow_ammo_bc{ammo}_{uuid.uuid4().hex[:8]}.json"
    p, _added, _ab = write_augmented_seed_bc(out, [CARRIER], seed_bc=bc)
    return p


def _build(seed_bc: Path) -> int | None:
    state = LOGS / f"_probe_mow_ammo_state_{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", SEED,
                    "--seed-bc", str(seed_bc), "--state-file", str(state),
                    "--board", BOARD, "--rank", "17", "--p-mow", CARRIER,
                    "--p-units", ALLIES, "--a-units", ENEMY],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not state.exists():
        return None
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    state.unlink(missing_ok=True)
    return rid


def _effects(dv):
    """(ownerId, effectType, active, name) publies par `readEffectsByUnit` via decisionView.

    ⚠ Les MoW comptent : `rpc-decision.ts` remplit `units[].effects` ET `mows[].effects`
    depuis la MEME map `readEffectsByUnit(statePtr, { includeInactive })` (cle = `casterId`
    pour une machine). Ne lire que `units[]` fait conclure a tort « effet non publie »."""
    rows = [(u.get("id"), e.get("effectType"), e.get("active"), e.get("name"))
            for u in (dv.get("units") or []) for e in (u.get("effects") or [])]
    rows += [(m.get("casterId"), e.get("effectType"), e.get("active"), e.get("name"))
             for m in (dv.get("mows") or []) for e in (m.get("effects") or [])]
    return rows


def _effects_units_only(dv):
    return [(u.get("id"), e.get("effectType"), e.get("active"), e.get("name"))
            for u in (dv.get("units") or []) for e in (u.get("effects") or [])]


def _mow_view(sid, rid, inactive=False):
    body = {"runnerId": rid, "maxRank": 1, "allAbilities": True}
    if inactive:
        body["includeInactive"] = True
    dv = _rpc(sid, "decisionView", body, 180)
    if not _ok(dv):
        return None, None
    mow = next((x for x in (dv.get("mows") or []) if x.get("visualId") == CARRIER), None)
    return dv, mow


def _abil(mow, aid):
    return next((a for a in ((mow or {}).get("abilities") or []) if a.get("id") == aid), {}) or {}


def _entity_effects(sid, rid, etype):
    """`effectAbilityStates` enumere les entites `EntityType.Effect` de l'etat -- le SEUL capteur
    qui voit un effet porte par une MACHINE : `readEffectsByUnit` (canal de `decisionView`) ne
    publie que `EntityType.Unit`/`Machine` cote UNITE, et `mows[].effects` rend `[]`."""
    r = _rpc(sid, "effectAbilityStates", {"runnerId": rid, "effectType": etype}, 120)
    return (r or {}).get("effects") or [] if _ok(r) else []


def _cast(sid, rid, caster, ability, target):
    r = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "targetId": target,
        "abilityType": ability}}, 90)
    a0 = ((r or {}).get("actions") or [{}])[0] if isinstance(r, dict) else {}
    return bool(_ok(r) and a0.get("ok")), bool(a0.get("mutated")), a0


def _phase(sid, ammo, endturns, verbose, target_kind="unit", pre_endturns=0, split_turns=0):
    """Monte un runner a `MachineOfWarAmmo = ammo` et rend le dict de mesure.

    `target_kind` : `unit` (un allie MECHANICAL) ou `mow` (la MoW elle-meme). Le domaine du
    selecteur de `ReanimationBeamAbility$$ExecuteBehaviour` part de `DSLFactory+0x80`, pose par
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` -- les deux cibles discriminent.

    `pre_endturns` : tours a purger AVANT le cast. `ReanimationBeam` porte
    `initialCooldownTurns = 1` au gameconfig -> au tour 1 le 2e terme de
    `IdunBattle.View.ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown) est deja faux, ce qui
    masque completement le terme MUNITIONS. Sans cette purge, la mesure ne discrimine rien."""
    out = {"ammo": ammo, "target_kind": target_kind, "pre_endturns": pre_endturns,
           "split": split_turns}
    rid = _build(_seed_bc(ammo))
    if rid is None:
        out["error"] = "build KO"
        return out
    out["runnerId"] = rid
    try:
        for _ in range(pre_endturns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        dv, mow = _mow_view(sid, rid)
        if mow is None:
            out["error"] = "MoW absente de decisionView.mows"
            return out
        caster = mow.get("casterId")
        beam = _abil(mow, BEAM)
        out["beam_before"] = (beam.get("ammoCost"), beam.get("hasAmmo"), beam.get("usable"))
        out["cd_before"] = beam.get("cooldown")
        allies = [u for u in (dv.get("units") or []) if u.get("team") == mow.get("team")]
        if not allies:
            out["error"] = "aucun allie"
            return out
        tgt = mow.get("id") if target_kind == "mow" else allies[0]["id"]
        out["target"] = tgt
        at = _rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": caster,
                                          "abilityType": BEAM}, 120)
        out["abilityTargets"] = at if not _ok(at) else [
            (e.get("abilityType"), e.get("targets"), e.get("fromHere"))
            for e in (at.get("units") or at.get("entries") or [])][:4]
        out["abilityReason"] = _rpc(sid, "abilityReason", {
            "runnerId": rid, "casterId": caster, "abilityType": BEAM, "targetId": tgt}, 120)

        # 1545 d'abord : `GetDynamicInvalidTargetReason` exige HasEffect(target, 0x609) & Mechanical
        acc_n, mut_n, a0n = _cast(sid, rid, caster, NANOSCARAB_ABILITY, tgt)
        heal = next((c for c in (a0n.get("changes") or []) if c.get("hpDelta")), None)
        out["nano"] = (acc_n, mut_n, None if heal is None else heal.get("hpDelta"))

        # une MoW n'a qu'UNE action par tour : `split_turns` la lui rend avant le beam.
        for _ in range(split_turns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        if split_turns:
            _dv2, mow2 = _mow_view(sid, rid)
            b2 = _abil(mow2, BEAM)
            out["beam_presplit"] = (b2.get("ammoCost"), b2.get("hasAmmo"), b2.get("cooldown"))
            out["hasAction"] = (mow2 or {}).get("hasAction")
            out["n1545_presplit"] = len(_entity_effects(sid, rid, NANOSCARAB))
        out["ent1547_before"] = len(_entity_effects(sid, rid, BEAM_EFFECT))
        acc_b, mut_b, a0b = _cast(sid, rid, caster, BEAM, tgt)
        out["beam_cast"] = (acc_b, mut_b, len(a0b.get("changes") or []), a0b.get("errors"))
        ent = _entity_effects(sid, rid, BEAM_EFFECT)
        out["ent1547_after"] = len(ent)
        out["ent1547_rows"] = ent[:4]
        out["ent1545"] = len(_entity_effects(sid, rid, NANOSCARAB))

        dv_def, mow_def = _mow_view(sid, rid)
        dv_inc, mow_inc = _mow_view(sid, rid, inactive=True)
        e_def, e_inc = _effects(dv_def or {}), _effects(dv_inc or {})
        out["n1547"] = (sum(1 for _u, t, _a, _n in e_def if t == BEAM_EFFECT),
                        sum(1 for _u, t, _a, _n in e_inc if t == BEAM_EFFECT))
        out["n1547_units_only"] = (
            sum(1 for _u, t, _a, _n in _effects_units_only(dv_def or {}) if t == BEAM_EFFECT),
            sum(1 for _u, t, _a, _n in _effects_units_only(dv_inc or {}) if t == BEAM_EFFECT))
        out["mows_effects_def"] = (next((x for x in ((dv_def or {}).get("mows") or [])
                                         if x.get("visualId") == CARRIER), {}) or {}).get("effects")
        out["n1545"] = (sum(1 for _u, t, _a, _n in e_def if t == NANOSCARAB),
                        sum(1 for _u, t, _a, _n in e_inc if t == NANOSCARAB))
        out["inert_witness"] = [(t, n) for _u, t, a, n in e_inc if a is False]
        out["e1547"] = [(u, t, a, n) for u, t, a, n in e_inc if t == BEAM_EFFECT]
        out["mows_effects"] = (mow_inc or {}).get("effects")
        beam2 = _abil(mow_def, BEAM)
        out["beam_after"] = (beam2.get("ammoCost"), beam2.get("hasAmmo"), beam2.get("cooldown"))
        if verbose:
            out["all_effects_inc"] = e_inc

        # la jauge remonte-t-elle toute seule ?
        for _ in range(endturns):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        _dv, mow_end = _mow_view(sid, rid)
        beam3 = _abil(mow_end, BEAM)
        out["beam_after_turns"] = (beam3.get("ammoCost"), beam3.get("hasAmmo"),
                                   beam3.get("cooldown"))
        return out
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--endturns", type=int, default=6)
    args = ap.parse_args()

    try:
        sid = R._resolve_session()
    except Exception as e:
        print("SKIP: pas de session Frida (%s)" % str(e)[:120])
        return 2
    if not _ok(_unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))):
        print("SKIP: amorce KO")
        return 2
    LOGS.mkdir(parents=True, exist_ok=True)

    print("=== jauge de munitions MoW : PlayerComponent+0x6c <- BC.Player.Players[].MachineOfWarAmmo ===")
    res = {}
    for ammo, tk, pre, split in ((0, "unit", 0, 0), (1, "unit", 2, 2), (0, "unit", 2, 2)):
        r = _phase(sid, ammo, args.endturns, args.verbose, tk, pre, split)
        res[(ammo, tk, pre, split)] = r
        print("")
        print("--- MachineOfWarAmmo = %d, cible = %s, %d endturn avant, %d entre les 2 casts"
              " (runner %s) ---" % (ammo, tk, pre, split, r.get("runnerId")))
        if r.get("error"):
            print("    ERREUR: %s" % r["error"])
            continue
        print("    cooldown avant cast : %s" % r.get("cd_before"))
        if split:
            print("    apres le split : beam=%s hasAction=%s entites 1545 restantes=%s"
                  % (r.get("beam_presplit"), r.get("hasAction"), r.get("n1545_presplit")))
        if r.get("error"):
            print("    ERREUR: %s" % r["error"])
            continue
        print("    %d avant cast     : ammoCost=%s hasAmmo=%s usable=%s" % ((BEAM,) + r["beam_before"]))
        print("    cast %d (1545)   : accepte=%s mute=%s hpDelta=%s" % ((NANOSCARAB_ABILITY,) + r["nano"]))
        print("    cast %d (beam)   : accepte=%s mute=%s changes=%d errors=%s" % ((BEAM,) + r["beam_cast"]))
        print("    %d apres cast     : ammoCost=%s hasAmmo=%s cooldown=%s" % ((BEAM,) + r["beam_after"]))
        print("    effet %d publie   : defaut=%d includeInactive=%d" % ((BEAM_EFFECT,) + r["n1547"]))
        print("    effet %d publie   : defaut=%d includeInactive=%d" % ((NANOSCARAB,) + r["n1545"]))
        print("    ENTITES-effet %d (effectAbilityStates) : avant=%s apres=%s | %d -> %s"
              % (BEAM_EFFECT, r.get("ent1547_before"), r.get("ent1547_after"),
                 NANOSCARAB, r.get("ent1545")))
        if r.get("ent1547_rows"):
            print("    rows 1547 : %s" % (r["ent1547_rows"],))
        print("    temoin canal (entrees active:false, tous types) : %d %s"
              % (len(r["inert_witness"]), r["inert_witness"]))
        print("    dont canal units[] SEUL : defaut=%d includeInactive=%d"
              % r["n1547_units_only"])
        print("    entrees 1547 (inc) : %s" % (r["e1547"],))
        print("    mows[].effects defaut : %s" % (r["mows_effects_def"],))
        print("    mows[].effects inc    : %s" % (r["mows_effects"],))
        print("    apres %d endturn   : ammoCost=%s hasAmmo=%s cooldown=%s"
              % ((args.endturns,) + r["beam_after_turns"]))
        if args.verbose:
            print("    effets publies (inc) : %s" % (r.get("all_effects_inc"),))

    a0 = res.get((0, "unit", 0, 0)) or {}   # tour 1 : cooldown initial ACTIF -> ne discrimine rien
    a1 = res.get((1, "unit", 2, 2)) or {}   # cooldown purge + action rendue + munition
    a2 = res.get((0, "unit", 2, 2)) or {}   # idem SANS munition (le discriminant)
    print("")
    print("VERDICT :")
    ok = True
    if a0.get("beam_before") and a0["beam_before"][1] is False:
        print("  [OK] ammo=0 : hasAmmo=false -- la mesure de depart est REPRODUITE.")
    else:
        print("  [!!] ammo=0 : hasAmmo=%s (attendu false)" % (a0.get("beam_before"),))
        ok = False
    if a1.get("beam_before") and a1["beam_before"][1] is True:
        print("  [OK] ammo=1 : hasAmmo=true -- la seule variable changee est la BC"
              " (`MachineOfWarAmmo`).")
    else:
        print("  [!!] ammo=1 : hasAmmo=%s (attendu true)" % (a1.get("beam_before"),))
        ok = False
    print("  --- ce qui bloquait REELLEMENT le cast (cooldown initial + action unique) ---")
    print("  tour 1, un seul tour : cooldown=%s -> entites %d %s -> %s"
          % (a0.get("cd_before"), BEAM_EFFECT, a0.get("ent1547_before"),
             a0.get("ent1547_after")))
    print("  cooldown purge + action rendue, ammo=1 : entites %d %s -> %s | hasAmmo %s -> %s"
          % (BEAM_EFFECT, a1.get("ent1547_before"), a1.get("ent1547_after"),
             (a1.get("beam_before") or [None, None])[1],
             (a1.get("beam_after") or [None, None, None])[1]))
    print("  cooldown purge + action rendue, ammo=0 : entites %d %s -> %s | hasAmmo %s -> %s"
          % (BEAM_EFFECT, a2.get("ent1547_before"), a2.get("ent1547_after"),
             (a2.get("beam_before") or [None, None])[1],
             (a2.get("beam_after") or [None, None, None])[1]))
    if (a1.get("ent1547_after") or 0) >= 1:
        print("  [OK] l'effet %d EST pose NATIVEMENT -- ce qui bloquait n'etait NI le harnais"
              " NI la munition, mais `initialCooldownTurns=1` puis l'ACTION UNIQUE de la MoW"
              " consommee par le cast prerequis de %d." % (BEAM_EFFECT, NANOSCARAB_ABILITY))
    else:
        print("  [!!] effet %d toujours non pose : %s" % (BEAM_EFFECT, a1.get("ent1547_after")))
        ok = False
    if (a1.get("beam_before") or [None, None])[1] and not (
            a1.get("beam_after") or [None, None, None])[1]:
        print("  [OK] la munition EST consommee par le cast (SpendAmmoOperation$$Execute) :"
              " hasAmmo true -> false.")
    else:
        print("  [!!] munition non consommee : %s -> %s"
              % (a1.get("beam_before"), a1.get("beam_after")))
        ok = False
    if (a2.get("ent1547_after") or 0) >= 1:
        print("  [OK] a ammo=0 le cast pose 1547 AUSSI : le terme MUNITIONS gate la face"
              " DECISION (`get_CanCurrentlyBeUsed`), PAS l'EXECUTION via applyAction.")
    if a0.get("beam_after_turns") and a0["beam_after_turns"][1] is False:
        print("  [OK] la jauge NE REMONTE PAS toute seule : a ammo=0, hasAmmo reste false"
              " apres %d endturn." % args.endturns)
    else:
        print("  [??] hasAmmo apres endturn (ammo=0) = %s" % (a0.get("beam_after_turns"),))
    print("  RAYON DE SOUFFLE de %d : canal decisionView defaut=%s includeInactive=%s"
          " (dont units[] SEUL : %s) -- le porteur est une MACHINE, l'entree sort sous"
          " `mows[].effects`, MEME map `readEffectsByUnit`."
          % (BEAM_EFFECT, (a1.get("n1547") or ("?", "?"))[0],
             (a1.get("n1547") or ("?", "?"))[1], a1.get("n1547_units_only")))
    print("RESULT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
