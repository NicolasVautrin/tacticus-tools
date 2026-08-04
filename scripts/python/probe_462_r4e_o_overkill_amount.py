"""#462-r4e-o -- MESURE du regime OVERKILL : le tag `Amount` per-coup vs le degat BRUT.

Question binaire tranchee au decompile, ce probe ne fait que CONFRONTER :

    `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` ecrit le tag `Amount` (TagKey 225) de
    l'event `UnitDamaged` depuis le champ @+0 de la valeur de retour d'
    `IdunBattle.Operations.ApplyDamageOperation$$Execute` -- un accumulateur alimente par EXACTEMENT
    deux termes : `FillUpStatComponent.Reduce(healthComp, dar.healthDamage, false)` et
    `ApplyDamageOperation.ReduceShield(unit, dar.shieldDamage)`.
    L'ETAGE QUI BORNE est `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` :
    `Min(Max(0, damage), Current)` (+ plancher `Minimum` @+0x1c).

TROIS regimes, choisis pour DISCRIMINER (un seul coup letal ne separe pas
« borner au coup letal » de « borner aux PV restants A CHAQUE COUP ») :

  * `letal`     -- MC1_67 / 31337 : la cible meurt au DERNIER coup ; un seul coup est borne.
  * `cadavre`   -- C3_01 / 777    : la cible meurt au coup 3 (borne PARTIELLE) et le coup 4 tombe
                                    sur un cadavre (`Amount` 0). C'est le regime QUI TRANCHE.
  * `survivant` -- MC1_67 / 31337 + `--hp-target` eleve : la cible SURVIT -> la borne est INACTIVE
                                    et `per_hit` doit rester le degat brut (temoin de non-regression).
  * `multi_cadavre` -- MC1_67 / 31337 + `--hp-target 2000` : la cible tombe DES LE 1er coup. Ce
                                    regime n'est PAS un garde de la borne : il expose le residu
                                    #462-r4e-o-r1 (CARDINALITE des events), cf. `_verdict_r1`.

`--mutate brut` remplace `damage_amount_applied` par le port d'AVANT #462-r4e-o (degat brut
rapporte) : `letal` et `cadavre` DOIVENT alors diverger, `survivant` non.

Usage :
    python scripts/python/probe_462_r4e_o_overkill_amount.py [--mutate brut] [--only <regime>]
    ... [--attacker <visualId>]

ASCII only. Dispose ses runners.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tests", "engine", "runner"))
import rl_collect_batch as R                                          # noqa: E402
from _combat_replay import replay_normal_attack                       # noqa: E402
from engine.runner.operations import damage_hits as DH                # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_SID = R._resolve_session()
_STATE = os.path.abspath(os.path.join(          # SORTIE -> logs/, jamais data/ (#349)
    _HERE, "..", "..", "logs", "runners", f"_probe462r4eo_{uuid.uuid4().hex[:8]}_state.json"))
_created = []

ATTACKER = "astraBullgryn"       # 4 coups melee, profil vanilla (aucun modificateur de degat)
TARGET = "eldarFarseer"          # cible vanille du catalogue #462-r4e

REGIMES = {
    # nom          board      seed     extra build            attend une borne ?
    "letal":     ("MC1_67", "31337", [],                      True),
    "cadavre":   ("C3_01",  "777",   [],                      True),
    "survivant": ("MC1_67", "31337", ["--hp-target", "999999"], False),
    # PV ecrases : la cible tombe DES LE PREMIER coup -> plusieurs coups derriere elle.
    # Regime qui EXPOSE le residu #462-r4e-o-r1 (CARDINALITE des events, cf. `_verdict_r1`).
    "multi_cadavre": ("MC1_67", "31337", ["--hp-target", "2000"], True),
}

# Regime dont le verdict porte sur le RESIDU (#462-r4e-o-r1), pas sur la borne.
RESIDU_R1 = "multi_cadavre"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _build_factory(board: str, cap_wait_s: int = 900, poll_s: int = 20):
    """Fabrique un `build_runner` compatible `_combat_replay`, cale sur `board`. ATTEND le cap
    MAX_RUNNERS / une fenetre DRAIN (session partagee entre agents, cf. runner.md)."""
    def _build(seed="777", extra=None, board_=board):
        extra = list(extra or [])
        args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
                "--state-file", _STATE, "--board", board_, *extra]
        waited = 0.0
        while True:
            try:
                os.unlink(_STATE)
            except OSError:
                pass
            p = subprocess.run(args, cwd=_HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if os.path.exists(_STATE):
                rid = json.loads(open(_STATE).read())["runnerId"]
                _created.append(rid)
                return {"rid": rid}
            out = (p.stderr or p.stdout or "")
            if ("runner cap reached" not in out and "runner creation paused" not in out) \
                    or waited >= cap_wait_s:
                raise RuntimeError(f"build KO: {out[-500:]}")
            print(f"  cap/drain, attente {poll_s}s ({waited:.0f}/{cap_wait_s})")
            time.sleep(poll_s)
            waited += poll_s
    return _build


def _mutate_brut():
    """Contre-epreuve : restaure le port d'AVANT #462-r4e-o (le degat BRUT rapporte per-coup)."""
    DH.damage_amount_applied = lambda health, shield, hp_left, hp_floor=None: (
        int(health) + int(shield), hp_left)


def _run(name: str, attacker: str) -> dict:
    board, seed, extra, expects_clamp = REGIMES[name]
    r = replay_normal_attack(_rpc, _build_factory(board), attacker, target=TARGET,
                             extra=extra, seed=seed)
    if not r["ok"]:
        print(f"[{name}] SKIP {r['reason']}")
        return {"name": name, "ok": False}
    clamped = sum(r["off_ph"]) != sum(r["live_ph"])
    print(f"[{name}] {attacker} board={board} seed={seed} bitexact={r['exact']} "
          f"hp_before={r['hp_before']} "
          f"crit={r['did_crit']} block={r['did_block']} evade={r['did_evade']}")
    print(f"  live={r['live_ph']} (somme {sum(r['live_ph'])})")
    print(f"  off ={r['off_ph']} (somme {sum(r['off_ph'])})")
    print(f"  hp_after live={r['live_after']} off={r['off_after']} ; borne attendue={expects_clamp}")
    return {"name": name, "ok": True, "exact": r["exact"], "expects_clamp": expects_clamp,
            "live": r["live_ph"], "off": r["off_ph"], "diverged": clamped,
            "live_after": r["live_after"], "off_after": r["off_after"]}


def _verdict_r1(r: dict) -> tuple:
    """Verdict du regime qui expose le RESIDU #462-r4e-o-r1 -- CARDINALITE des events.

    MESURE (2 attaquants, meme motif) : quand la cible tombe des le 1er coup, le natif emet le coup
    letal PUIS UN SEUL event a `Amount` 0, et RIEN pour les coups suivants ; le port en emet un par
    coup restant. Foyer natif : le SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`
    -- `if (UnitExtensions.HasFlag(target, 8 = Overkilled)) { RecordHitStatistics ;
    AddLeftoverHit(.., 1) ; return; }` -- qui PRECEDE toute emission, le flag etant pose par
    `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(comp, 8)` sous
    `dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`. Le port n'evalue cette garde qu'a
    l'ENTREE DU GROUPE (`_apply_damage_pipeline`) : residu de GRANULARITE deja nomme dans
    `damage.py`. L'ETAT reste identique (memes PV, meme somme) -- c'est un ecart de RAPPORT.

    Ce verdict garde la FORME de l'ecart, pas son absence : `live` doit etre un PREFIXE de `off`, le
    reste de `off` doit etre nul, et les sommes egales. Si l'ecart change de nature (valeurs
    differentes, sommes differentes), le probe ROUGIT -- et il rougira aussi le jour ou le residu
    sera porte, ce qui est le signal voulu."""
    live, off = r["live"], r["off"]
    if live == off:
        return False, ("IDENTIQUE -- le residu #462-r4e-o-r1 a disparu (porte ?) : "
                       "mettre a jour ce verdict")
    forme = (len(off) >= len(live) and off[:len(live)] == live
             and all(x == 0 for x in off[len(live):])
             and sum(off) == sum(live) and r["off_after"] == r["live_after"])
    if forme:
        return True, (f"RESIDU #462-r4e-o-r1 (cardinalite) : live={live} off={off} "
                      "-- meme etat, meme somme, N entrees nulles en trop")
    return False, (f"ECART DE NATURE INATTENDUE : live={live} off={off} "
                   f"(sommes {sum(live)}/{sum(off)}, hp_after {r['live_after']}/{r['off_after']})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", choices=["brut"], default=None)
    ap.add_argument("--only", choices=sorted(REGIMES), default=None)
    ap.add_argument("--attacker", default=ATTACKER,
                    help="autre profil d'arme du catalogue confrontable (ex. tauAunShi = 5 coups)")
    a = ap.parse_args()
    if a.mutate == "brut":
        _mutate_brut()
        print("MUTATION: damage_amount_applied -> degat BRUT (port d'avant #462-r4e-o)")

    w = _unwrap(R._rpc(_SID, "warmupGameSingletons", [{}], timeout=180))
    print("warmup ok=", isinstance(w, dict) and w.get("ok"))
    out = []
    try:
        for name in ([a.only] if a.only else list(REGIMES)):
            out.append(_run(name, a.attacker))
    finally:
        for rid in _created:
            try:
                R._rpc(_SID, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass

    print("\n--- VERDICT ---")
    bad = 0
    for r in out:
        if not r.get("ok"):
            continue
        if r["name"] == RESIDU_R1:
            ok_r1, verdict = _verdict_r1(r)
            bad += 0 if ok_r1 else 1
        elif a.mutate == "brut" and r["expects_clamp"]:
            verdict = ("DIVERGE (attendu sous mutation)" if not r["exact"]
                       else "IDENTIQUE -- la mutation n'a PAS mordu")
            bad += 0 if not r["exact"] else 1
        else:
            verdict = "OK" if r["exact"] else "MISMATCH"
            bad += 0 if r["exact"] else 1
        print(f"  {r['name']}: {verdict}")
    print(f"VERDICT: {'PASS' if bad == 0 else 'FAIL'} ({bad} anomalie(s))")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
