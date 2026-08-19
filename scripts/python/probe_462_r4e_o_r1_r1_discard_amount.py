"""#462-r4e-o-r1-r1 -- MESURE : un coup DISCARDE emet-il un event `UnitDamaged` a `Amount` 0 ?

QUESTION BINAIRE, tranchee au decompile (build `rnca9r7q6c`) ; ce probe ne fait que CONFRONTER.

    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` relit `OngoingAttack+0x98` juste apres
    `On(6 = PreAttackHit)` / `On(7)` et, si le flag `discard` du `Nullable<AttackHit>` est pose, fait
    `return this` sur un `OperationResult` MEMSET A 0. Ce `return` PRECEDE la sub-op **0x42**
    (`IdunBattle.Operations.DealDamageOperation$$Execute`), qui est le SEUL chemin vers le slot
    **0x43** (`IdunBattle.Core.Services.OperationProcessor$$ApplyDamage` ->
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`), lui-meme unique emetteur de l'evenement
    `UnitDamaged` porteur du tag `Amount` (`IdunBattle.Core.Services.StreamHelper$$GetDamageTags`,
    TagKey 225).
    => un coup discarde n'emet RIEN. Le port en appendait une entree a 0 : ecart de RAPPORT pur
    (meme etat, meme somme), invisible de tout test d'ETAT -- meme signature que #462-r4e-o-r1,
    AUTRE PORTE (celle-ci est en AMONT de la resolution, le SITE (A) est en aval).

MONTAGE. Le regime exige un porteur de `HarlequinsPanoply` (« the first time each turn this unit
blocks a hit, all further hits of the attack are discarded »). Ses deux porteurs sont
`eldarSmnHarlequin` (SUMMON) et `eldarNpc3Harlequin` (npc), et le seul artefact qui summone le
premier est `EnvFactionSummons:Aeldari`, une ability d'ENVIRONNEMENT -- aucun summoner du catalogue.
On passe donc par la GREFFE du passif sur une unite du pool (`catalog_inject.write_grafted_seed_bc`,
`case-92` SS5bis volet passif), voie DEJA etablie et confrontee par #366-r1/#406 : les deux
`CreateTrigger` du cluster ne lisent du porteur que son compteur de blocks et ses effets.
`--block-target 100,300` rend le block DETERMINISTE au coup 0 (BlockChance 100 ; BlockDamage > 0 est
OBLIGATOIRE -- une source a montant nul n'entre pas dans `block_sources`).

DEUX bras, et le TEMOIN n'est pas decoratif : sans lui, « 1 event » pourrait venir d'une arme
mono-coup ou d'un montage rate, et le verdict serait vert pour la mauvaise raison.

  * `greffe` -- le defenseur porte `HarlequinsPanoply` : le natif doit emettre **UN SEUL** event
    pour une arme a N coups ;
  * `temoin` -- meme seed, meme board, memes rosters, meme `--block-target` ; un seul bit de
    difference (la greffe) : le natif emet **N** events.

`--mutate cardinalite-discard` restaure le port d'AVANT (foyer `discarded_hit_emits` force a VRAI) :
le bras `greffe` DOIT alors diverger (une entree a 0 par coup jete), le `temoin` non.

Usage (depuis scripts/python, session warmee) :
    python probe_462_r4e_o_r1_r1_discard_amount.py [--mutate cardinalite-discard]
    ... [--only greffe|temoin] [--board MC1_67] [--seed 31337]

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
from engine.runner import snapshot as SNAP                            # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_SID = R._resolve_session()
_OUT = os.path.abspath(os.path.join(       # SORTIES -> logs/, jamais data/ (#349)
    _HERE, "..", "..", "logs", "runners"))
_STATE = os.path.join(_OUT, "_probe462r1r1_%s_state.json" % uuid.uuid4().hex[:8])
_created = []

ATTACKER = "necroDestroyer"      # 6 coups de MELEE -- l'ecart 1 vs 6 est massif
GRAFT = "astraBullgryn"          # defenseur : PV eleves -> survit aux 6 coups du temoin
ABILITY = "HarlequinsPanoply"
BLOCK = "100,300"                # BlockChance,BlockDamage : block DETERMINISTE, rogne sans annuler


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _build_factory(board: str, cap_wait_s: int = 900, poll_s: int = 20):
    """Fabrique un `build_runner` compatible `_combat_replay`, cale sur `board`. ATTEND le cap
    MAX_RUNNERS / une fenetre DRAIN (session partagee entre agents, cf. runner.md)."""
    def _build(seed="31337", extra=None, board_=board):
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
                raise RuntimeError("build KO: %s" % out[-500:])
            print("  cap/drain, attente %ds (%.0f/%d)" % (poll_s, waited, cap_wait_s))
            time.sleep(poll_s)
            waited += poll_s
    return _build


def _mutate_cardinalite_discard():
    """Contre-epreuve : OUVRE l'etape 5 (`discarded_hit_emits` toujours VRAI) = le port d'AVANT
    #462-r4e-o-r1-r1, ou chaque coup jete appendait son propre event a `Amount` 0."""
    DH.discarded_hit_emits = lambda: True


def _graft(dest_dir: str) -> str:
    import catalog_inject as CI
    import host_inputs                                     # noqa: F401 (garde data/)
    out = os.path.join(dest_dir, "panoply-grafted-bc-%s.json" % uuid.uuid4().hex[:6])
    p, reports = CI.write_grafted_seed_bc(out, ["%s:%s" % (GRAFT, ABILITY)])
    # Garde de MONTAGE : un montage rate doit ASSERTER, jamais passer en silence.
    assert reports and reports[0]["abilityId"] == 1187, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1187], reports
    print("[montage] greffe %s:%s -> %s" % (GRAFT, ABILITY, reports[0]))
    return str(p)


def _port_sees_graft(rid: int) -> bool:
    """Garde de MONTAGE cote PORT : le canal MESURE (`unitAbilityStates`, hierarchie 2) publie-t-il
    reellement `HarlequinsPanoply` ? C'est la MEME source que `make_hit_interceptor`.

    ⚠ CE POINT A DEJA FAIT UN FAUX NEGATIF, mesure ici meme : sans `bind_live_rpc`, `load_state`
    n'a aucun transport pour aller tirer ce RPC, `UnitContext.passive_abilities` reste None et la
    detection retombe sur le kit gameconfig -- ou `astraBullgryn` ne porte evidemment pas le
    greffon. Le port rendait alors ses 6 coups et le probe accusait le PORT d'une panne de HARNAIS
    (meme piege que celui deja nomme par `docs/rl/case-366-r1...` SS6bis pour #406)."""
    payload = _rpc("unitAbilityStates", {"runnerId": int(rid)}, 90)
    if not isinstance(payload, dict):
        return False
    by_unit = SNAP.passive_ability_names_by_unit(payload)
    return any(ABILITY in (names or []) for names in by_unit.values())


def _run(name: str, board: str, seed: str, grafted: str, attacker: str = ATTACKER) -> dict:
    extra = ["--block-target", BLOCK]
    if name == "greffe":
        extra = ["--seed-bc", grafted] + extra
    r = replay_normal_attack(_rpc, _build_factory(board), attacker, target=GRAFT,
                             extra=extra, seed=seed)
    # Le runner du bras qu'on vient de jouer (le build est fait DANS `replay_normal_attack`).
    rid = _created[-1] if _created else None
    if rid is not None:
        vu = _port_sees_graft(rid)
        attendu = (name == "greffe")
        assert vu == attendu, (
            "MONTAGE CASSE [%s] : le canal `unitAbilityStates` %s %s -- attendu %s. "
            "Sans ca le verdict serait vert (ou rouge) pour la mauvaise raison."
            % (name, "publie" if vu else "ne publie PAS", ABILITY, attendu))
        print("[%s] montage verifie : %s %s le canal mesure" % (name, ABILITY,
                                                                "DANS" if vu else "ABSENT DE"))
    if not r["ok"]:
        print("[%s] SKIP %s" % (name, r["reason"]))
        return {"name": name, "ok": False, "reason": r["reason"]}
    print("[%s] %s -> %s board=%s seed=%s bitexact=%s hp_before=%s block=%s"
          % (name, attacker, GRAFT, board, seed, r["exact"], r["hp_before"], r["did_block"]))
    print("  live=%s (n=%d, somme %d)" % (r["live_ph"], len(r["live_ph"]), sum(r["live_ph"])))
    print("  off =%s (n=%d, somme %d)" % (r["off_ph"], len(r["off_ph"]), sum(r["off_ph"])))
    print("  hp_after live=%s off=%s" % (r["live_after"], r["off_after"]))
    return {"name": name, "ok": True, "exact": r["exact"],
            "live": r["live_ph"], "off": r["off_ph"],
            "live_after": r["live_after"], "off_after": r["off_after"],
            "did_block": r["did_block"]}


def _verdict(r: dict, mutate=None, temoin_n=None) -> tuple:
    """Verdict par bras.

    `greffe` sans mutation : exige `live == off` ET que le regime soit DISCRIMINANT -- le natif doit
    avoir jete des coups (`len(live) < temoin_n`). Sans cette seconde clause, un montage rate (greffe
    invisible, aucun block) rendrait `live == off` a N entrees et passerait pour un succes.

    `greffe` sous mutation : exige la DIVERGENCE, et la forme EXACTE de l'ancien ecart (le live est
    un PREFIXE de l'offline, le reste est nul, somme et etat identiques)."""
    live, off = r["live"], r["off"]
    forme_ancienne = (len(off) > len(live) and off[:len(live)] == live
                      and all(x == 0 for x in off[len(live):])
                      and sum(off) == sum(live) and r["off_after"] == r["live_after"])
    if r["name"] == "temoin":
        if live == off and (temoin_n is None or len(live) == temoin_n):
            return True, "OK (temoin inchange) : %d events des DEUX cotes" % len(live)
        return False, "TEMOIN casse : live=%s off=%s" % (live, off)

    if mutate == "cardinalite-discard":
        if live == off:
            return False, ("IDENTIQUE sous mutation -- l'etape 5 n'a PAS mordu (foyer "
                           "`discarded_hit_emits` non substitue, ou aucun coup jete)")
        if forme_ancienne:
            return True, ("DIVERGE (attendu sous mutation) : live=%s off=%s -- exactement "
                          "l'ancien ecart de cardinalite" % (live, off))
        return False, "DIVERGENCE INATTENDUE sous mutation : live=%s off=%s" % (live, off)

    if live != off:
        if forme_ancienne:
            return False, ("REGRESSION #462-r4e-o-r1-r1 : live=%s off=%s -- meme etat, meme somme, "
                           "%d entree(s) nulle(s) en trop" % (live, off, len(off) - len(live)))
        return False, "ECART DE NATURE INATTENDUE : live=%s off=%s" % (live, off)
    if temoin_n is not None and len(live) >= temoin_n:
        return False, ("REGIME NON DISCRIMINANT : %d events comme le temoin (%d) -- le natif n'a "
                       "jete AUCUN coup, le vert ne prouve rien" % (len(live), temoin_n))
    return True, ("OK (cardinalite portee) : live=off=%s -- %d event(s) pour %s coups temoin"
                  % (live, len(live), temoin_n))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", choices=["cardinalite-discard"], default=None)
    ap.add_argument("--only", choices=["greffe", "temoin"], default=None)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--attacker", default=ATTACKER,
                    help="autre profil d'arme MULTI-COUPS du pool (ex. tauAunShi = 5 coups) -- "
                         "l'axe de GENERALISATION : le nombre de coups jetes doit suivre l'arme")
    a = ap.parse_args()
    if a.mutate == "cardinalite-discard":
        _mutate_cardinalite_discard()
        print("MUTATION: discarded_hit_emits -> toujours VRAI (etape 5 ouverte, "
              "port d'avant #462-r4e-o-r1-r1)")

    os.makedirs(_OUT, exist_ok=True)
    grafted = _graft(_OUT)
    # OBLIGATOIRE : `load_state` ne recoit que des PAYLOADS ; sans transport ambiant elle ne peut pas
    # tirer `unitAbilityStates`, donc `UnitContext.passive_abilities` reste None et la greffe est
    # INVISIBLE cote port (la detection retombe sur le kit gameconfig). Mesure faite ici : sans cette
    # ligne, le bras greffe rendait `off=[212,146,325,291,201,320]` contre `live=[212]` -- un rouge
    # qui accuse le PORT d'une panne de HARNAIS. Cf. `bind_live_rpc` (`engine/runner/snapshot.py`).
    SNAP.bind_live_rpc(_rpc)
    w = _unwrap(R._rpc(_SID, "autoBootExtraire", [{}], timeout=180))
    print("amorce ok=", isinstance(w, dict) and w.get("ok"))

    out = []
    try:
        # Le TEMOIN d'abord : il fixe le nombre de coups de l'arme, qui sert de reference au bras
        # greffe (garde anti-vacuite). `--only greffe` s'en passe -> verdict sans cette clause.
        for name in (["temoin", "greffe"] if a.only is None else [a.only]):
            out.append(_run(name, a.board, a.seed, grafted, attacker=a.attacker))
    finally:
        for rid in _created:
            try:
                R._rpc(_SID, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass

    temoin = next((r for r in out if r["name"] == "temoin" and r.get("ok")), None)
    temoin_n = len(temoin["live"]) if temoin else None

    print("\n--- VERDICT ---")
    bad = 0
    for r in out:
        if not r.get("ok"):
            print("  %s: SKIP (%s)" % (r["name"], r.get("reason")))
            bad += 1
            continue
        ok, verdict = _verdict(r, mutate=a.mutate, temoin_n=temoin_n)
        bad += 0 if ok else 1
        print("  %s: %s" % (r["name"], verdict))
    print("VERDICT: %s (%d anomalie(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
