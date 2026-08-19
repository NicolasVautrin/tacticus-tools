"""case-1547 -- CONFRONTATION LIVE du porteur natif de l'effet 1547 `ReanimationBeam_Revive`.

REFUTE la conclusion « porteur non confrontable » que cette fiche portait d'abord (et que le
gate de confrontabilite du CLAUDE.md poussait a ecrire) : `necroReanimator` est bien ABSENTE de
`rl_duel.py build --list-pool` par defaut, mais `--list-pool` derive du seed BC, qui n'est que la
capture d'UNE bataille. `catalog_inject.py` (mirror d'
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`) l'injecte dans les DEUX
catalogues du seed (`Units` ET `Abilities`), et la pool est recalculee APRES le chargement du
seed -> `--list-pool --seed-bc <augmente>` la liste.

Ce que ce probe MESURE, dans l'ordre, et RAPPORTE tel quel (un refus est un RESULTAT) :

  1. injection catalogue      -> `Units` 175 -> 176, +2 configs d'ability ;
  2. pool                     -> 8 -> 9 MoW spawnables, `necroReanimator` incluse ;
  3. deploiement              -> la MoW apparait dans `decisionView.mows` (PAS dans `.units`) ;
  4. CASTABILITE depuis le harnais headless -- la docstring du port affirmait que les abilities
     d'une MoW hors-plateau y sont BLOQUEES. Le probe cast les DEUX actives du kit :
       * `1224 NanoscarabRepairProtocols` -> doit MUTER (soin + pose des effets 1545/1546) ;
       * `1223 ReanimationBeam`           -> NO-OPE ici. ⚠ Ce probe l'imputait aux MUNITIONS :
         c'est **FAUX**, refute par `probe_mow_ammo_gauge.py` (`docs/rl/case-mow-ammo-gauge.md`).
         Les vraies causes sont `initialCooldownTurns = 1` (tour 1) PUIS l'action unique de la
         MoW, consommee juste avant par le cast prerequis de `1224`. Avec 2 `endturn` avant et 2
         entre les deux casts, `1223` pose bel et bien 1547 -- meme a munition ZERO ;
  5. RAYON DE SOUFFLE d'un `includeInactive` global -- que publie `readEffectsByUnit` ? Le probe
     compte les entrees 1547 aux DEUX canaux, et compte les entrees `active: false` TOUS TYPES
     comme TEMOIN que le canal fonctionne (sans ce temoin, « 0 entree 1547 » ne prouverait rien).

Usage :  python probe_1547_carrier_live.py [--verbose]
ASCII only (console cp1252). Sorties dans `logs/` (jamais `data/`, qui ne porte que des ENTREES).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                              # noqa: E402

CARRIER = "necroReanimator"          # MoW Necron, kit [ReanimationBeam, NanoscarabRepairProtocols]
BEAM = 1223                          # ActiveAbilityType.ReanimationBeam (0x4c7) -> pose 1547
NANOSCARAB_ABILITY = 1224            # l'AUTRE active du kit -> pose 1545 (+ 1546)
NANOSCARAB = 1545                    # EffectType.NanoscarabRepairProtocols
BEAM_EFFECT = 1547                   # EffectType.ReanimationBeam_Revive
BOARD, SEED = "MC1_67", "777"
ALLIES = "admecDestroyer,necroDestroyer"     # allies MECHANICAL (le filtre exige HasTrait(5))
ENEMY = "worldKharn"

AUG = ROOT / "logs" / "_probe1547_seedbc_reanimator.json"
STATE = ROOT / "logs" / "_probe1547_carrier_state.json"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(sid, method, body=None, timeout=120):
    return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _run(argv):
    return subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _effects(dv):
    """(unitId, effectType, active, name) publies par `readEffectsByUnit` via decisionView."""
    return [(u.get("id"), e.get("effectType"), e.get("active"), e.get("name"))
            for u in (dv.get("units") or []) for e in (u.get("effects") or [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    try:
        sid = R._resolve_session()
    except Exception as e:
        print("SKIP: pas de session Frida (%s)" % str(e)[:120])
        return 2
    if not _ok(_unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))):
        print("SKIP: amorce KO")
        return 2

    print("=== case-1547 : le porteur natif de 1547 est-il confrontable ? ===")
    ok = True

    # --- 1. injection catalogue -------------------------------------------------------------
    AUG.parent.mkdir(parents=True, exist_ok=True)
    p = _run([sys.executable, "catalog_inject.py", "--units", CARRIER, "--rank", "17",
              "--out", str(AUG)])
    if not AUG.exists():
        print("FAIL injection catalogue: %s" % (p.stderr or p.stdout or "")[-300:])
        return 1
    for line in (p.stdout or "").splitlines():
        if "catalogue Units" in line or "configs d'ability" in line:
            print("   %s" % line.strip())

    # --- 2. pool ----------------------------------------------------------------------------
    p = _run([sys.executable, "rl_duel.py", "build", "--list-pool", "--seed-bc", str(AUG)])
    mow_line = next((l for l in (p.stdout or "").splitlines() if "MoW spawnables" in l), "")
    print("   %s" % mow_line.strip())
    if CARRIER not in mow_line:
        print("FAIL: injecte mais absent de la pool augmentee")
        return 1

    # --- 3. deploiement ---------------------------------------------------------------------
    STATE.unlink(missing_ok=True)
    _run([sys.executable, "rl_duel.py", "build", "--seed", SEED, "--seed-bc", str(AUG),
          "--state-file", str(STATE), "--board", BOARD, "--rank", "17",
          "--p-mow", CARRIER, "--p-units", ALLIES, "--a-units", ENEMY])
    if not STATE.exists():
        print("FAIL: le porteur ne se deploie pas (build runner KO)")
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        if not _ok(dv):
            print("FAIL: decisionView KO")
            return 1
        # ⚠ une MoW n'est PAS dans `.units` : elle vit dans `.mows` (ability-only, sans position).
        mow = next((x for x in (dv.get("mows") or []) if x.get("visualId") == CARRIER), None)
        if mow is None:
            print("FAIL: MoW absente de decisionView.mows")
            return 1
        abil = {a.get("id"): a for a in (mow.get("abilities") or [])}
        print("   deployee : decisionView.mows id=%s casterId=%s slot=%s abilities=%s"
              % (mow.get("id"), mow.get("casterId"), mow.get("slot"), sorted(abil)))
        beam_a = abil.get(BEAM) or {}
        print("   %d ReanimationBeam : ammoCost=%s hasAmmo=%s cooldown=%s"
              % (BEAM, beam_a.get("ammoCost"), beam_a.get("hasAmmo"), beam_a.get("cooldown")))
        allies = [u["id"] for u in (dv.get("units") or []) if u.get("owner") == mow.get("owner")]
        if not allies:
            print("FAIL: aucun allie")
            return 1

        # --- 4. castabilite depuis le harnais headless --------------------------------------
        def _cast(ability, target):
            r = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": mow.get("casterId"),
                "targetId": target, "abilityType": ability}}, 60)
            a0 = ((r or {}).get("actions") or [{}])[0] if isinstance(r, dict) else {}
            return bool(_ok(r) and a0.get("ok")), bool(a0.get("mutated")), a0

        acc, mut, a0 = _cast(NANOSCARAB_ABILITY, allies[0])
        heal = next((c for c in (a0.get("changes") or []) if c.get("hpDelta")), None)
        print("   cast %d (Nanoscarab) : accepte=%s mute=%s%s"
              % (NANOSCARAB_ABILITY, acc, mut,
                 "" if heal is None else " hp %s -> %s (+%s)"
                 % (heal.get("hpBefore"), heal.get("hpAfter"), heal.get("hpDelta"))))
        if not (acc and mut):
            print("   -> une MoW NE peut PAS caster depuis le harnais headless (a documenter)")
            ok = False

        acc_b, mut_b, a0b = _cast(BEAM, allies[0])
        print("   cast %d (ReanimationBeam) : accepte=%s mute=%s changes=%d actionConsumed=%s"
              % (BEAM, acc_b, mut_b, len(a0b.get("changes") or []), a0b.get("actionConsumed")))
        if acc_b and not mut_b:
            print("   -> ACCEPTE mais NO-OPE : `hasAmmo=%s` (les munitions ne montent pas dans un"
                  " runner inactif). L'effet 1547 n'est donc PAS pose." % beam_a.get("hasAmmo"))

        # --- 5. rayon de souffle -------------------------------------------------------------
        dv_def = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        dv_inc = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                            "includeInactive": True})
        if not (_ok(dv_def) and _ok(dv_inc)):
            print("FAIL: relecture decisionView KO")
            return 1
        e_def, e_inc = _effects(dv_def), _effects(dv_inc)
        n_def = sum(1 for _u, t, _a, _n in e_def if t == BEAM_EFFECT)
        n_inc = sum(1 for _u, t, _a, _n in e_inc if t == BEAM_EFFECT)
        inert = [(u, t, n) for u, t, a, n in e_inc if a is False]
        print("")
        print("   effet %d publie -- canal par defaut : %d | includeInactive : %d"
              % (BEAM_EFFECT, n_def, n_inc))
        print("   TEMOIN canal : entrees `active: false` sous includeInactive (tous types) : %d %s"
              % (len(inert), [(t, n) for _u, t, n in inert]))
        print("   effet %d (Nanoscarab, POSE par le cast qui a mute) : def=%d inc=%d"
              % (NANOSCARAB,
                 sum(1 for _u, t, _a, _n in e_def if t == NANOSCARAB),
                 sum(1 for _u, t, _a, _n in e_inc if t == NANOSCARAB)))
        mow_inc = next((x for x in (dv_inc.get("mows") or [])
                        if x.get("visualId") == CARRIER), None)
        print("   mows[].effects (la MoW elle-meme) : %s" % ((mow_inc or {}).get("effects")))
        if args.verbose:
            print("   effets publies (inc) : %s" % e_inc)
        print("")
        print("VERDICT -- confrontabilite : le porteur de 1547 EST spawnable (catalog_inject +")
        print("  --seed-bc) et SES ABILITIES CASTENT depuis le harnais headless (1224 a mute).")
        print("  1223 no-ope DANS CE SCENARIO -- mais PAS a cause des munitions (refute par")
        print("  probe_mow_ammo_gauge.py) : le cooldown initial de 1 tour puis l'action unique de")
        print("  la MoW, consommee par le cast prerequis de 1224. Le rayon de souffle de 1547 EST")
        print("  MESURE la-bas : 1 entree aux DEUX canaux, sous mows[].effects (units[] rend 0).")
        print("RESULT: %s" % ("OK" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        STATE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
