"""#287-r6 -- l'ORACLE de ciblage se COURT-CIRCUITE en amont, et ca se MESURE sur `casterReason`.

CE QUE CE PROBE ETABLIT. L'oracle `abilityReason` n'appelle PAS la fonction que le port mirror.
Il appelle `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui place DEUX etages
AVANT la cascade de ciblage -- lus a l'octet sur `rnca9r7q6c` :

    ability = ActiveAbilityComponent.GetOrNull(<collection de l'unite>, abilityType);
    if (ability == null || !ability.CanCurrentlyBeUsed || *(int*)(ability+0x44) == 0)
        -> GenericBrokenTargetingRule(1)                        // TargetingRule.ValidRequest
    if (IsDamagedMachine(unit) && !IsMachinePrimaryAbilityType(unit, abilityType))
        -> GenericBrokenTargetingRule(1)
    if (AttackQuery.IsAlreadyUsedThisTurn(...))  -> 0x40000000000000
    sinon -> <ITargetingQuery>.GetInvalidTargetReason(...)       // LA cascade

Le port, lui, mirror `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`, qui n'a
AUCUN de ces etages : il resout la config d'ability puis appelle DIRECTEMENT le meme slot
d'`ITargetingQuery`. Les deux ne repondent donc pas a la meme question des que l'etage amont mord.

LE DISCRIMINANT EST DEJA PUBLIE, et n'exige aucun capteur neuf :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` porte le MEME etage de
disponibilite, avec le MEME code `1`, et il ne depend PAS de la cible. Donc
`casterReason.hex == 0x1` signe le court-circuit AMONT -- pour TOUTES les cibles a la fois --
la ou un `targetReason.hex == 0x1` isole resterait ambigu (la cascade elle-meme peut rendre `1`
sur sa branche `TargetIsTile` quand la tuile n'est pas marchable).

⚠ POURQUOI ON NE PEUT PAS SE CONTENTER DE `targetReason`. `1` est REUTILISE par le natif a deux
rangs differents : `ValidRequest` (amont, ability indisponible) et le litteral rendu par la branche
`TargetIsTile` de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (tuile non
marchable). Un meme ordinal, deux sens. Seul `casterReason` les separe.

⚠ ET LE COURT-CIRCUIT N'EST PAS UN ACCIDENT DE MONTAGE : `SquigMine` (1201) porte
`constants.initialCooldownTurns = 1` au gameconfig, donc son `ActiveAbility.Cooldown` vaut `1` au
TOUR 1 et `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` rend `false`
(son terme `cooldown.HasValue && cooldown.Value < 1`). Toute mesure prise au tour 1 sur cette
ability confronte donc un etage que le port ne traverse pas -- quel que soit le board.

LES TROIS ETAPES :

  1. DISCRIMINANT. `casterReason` par couple (caster, ability), sur le montage EXACT qui a produit
     le rouge de #287-r4-r1. Temoin non degenere EXIGE : au moins un couple court-circuite ET au
     moins un passant -- sinon le discriminant ne discrimine rien.

  2. BASCULE TEMPORELLE. On rend l'oracle PASSANT en laissant retomber le cooldown (fin de tour +
     tour adverse), et l'on exige que `casterReason(1201)` passe de `ValidRequest` a `0`. C'est la
     contre-epreuve du diagnostic : si le `0x1` venait de la TUILE, il survivrait au changement de
     tour.

  3. CONFRONTATION, enfin possible. L'oracle traversant, on confronte `targetReason` au port cible
     par cible sur des tuiles OCCUPEES et LIBRES -- exactement le domaine que #287-r4-r1 avait
     mesure a travers le court-circuit. Contrat de fidelite identique a
     `probe_287r4r1_generalisation_live` : natif 0 => port 0 ; natif != 0 => port == natif ou 0.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r6_oracle_court_circuite.py
    python scripts/python/probe_287r6_oracle_court_circuite.py --board C1_02
ASCII only ; exit 0 = les trois etapes passent.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import oracle_targeting as O                                               # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"

# (abilityType, visualId du porteur) -- les memes couples que `probe_287r4r1_generalisation_live`,
# pour que le diagnostic porte EXACTEMENT sur le montage qui a produit le rouge.
COUPLES = [
    (int(ActiveAbilityType.AdaptiveStrategy), "necroWarden"),          # 1005, unite reguliere
    (int(ActiveAbilityType.FoulInfusion), "deathPutrifier"),           # 1038, unite reguliere
    (int(ActiveAbilityType.SquigMine), "orksRukkatrukk"),              # 1201, MoW, cooldown initial
]
CIBLE_1201 = int(ActiveAbilityType.SquigMine)


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _acteurs(dec: dict) -> dict:
    by_vis = {}
    for u in (dec.get("units") or []):
        by_vis.setdefault(u.get("visualId"), {"id": u["id"], "kind": "unit"})
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"), {"id": m["casterId"], "kind": "mow"})
    return by_vis


def _reason(rid: int, cid: int, at: int, tid=None) -> dict:
    body = {"runnerId": rid, "casterId": int(cid), "abilityType": int(at)}
    if tid is not None:
        body["targetId"] = int(tid)
    return _rpc("abilityReason", body, 60000) or {}


def _hex(bloc) -> int:
    """Le meme lecteur que le foyer -- reexporte pour que ce probe n'en ait pas un SECOND."""
    return O._hex_de(bloc)


def _contexte(rid: int):
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    board = Board(bg["tiles"], adjacency="evenq")
    alive = [u for u in (dec.get("units") or []) if u.get("alive")]
    positions = {(int(u["pos"]["col"]), int(u["pos"]["row"])) for u in alive
                 if (u.get("pos") or {}).get("col") is not None}
    occupees = [t for t in sorted(board.by_id) if board.coord(t) in positions]
    libres = [t for t in sorted(board.by_id) if board.coord(t) not in positions]
    state = load_state(dec, ob, snap, board=board)
    return dec, state, _acteurs(dec), occupees, libres


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r6 : l'oracle se court-circuite en amont")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--p-units", default="necroWarden,deathPutrifier")
    ap.add_argument("--a-units", default="orksWarboss,thousTzaangor")
    ap.add_argument("--p-mow", default="orksRukkatrukk")
    ap.add_argument("--state-file", default="rs_287r6_amont.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    state_file = LOGS / a.state_file
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
            "--p-units", a.p_units, "--a-units", a.a_units, "--state-file", str(state_file)]
    if a.p_mow:
        args += ["--p-mow", a.p_mow]
    _run(args)
    if not state_file.exists():
        print("[287r6] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    etape1, etape2, etape3 = [], None, None
    empeche = ""
    try:
        # ---------------------------------------------------------------- 1. DISCRIMINANT
        dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        by_vis = _acteurs(dec)
        print("[287r6] board=%s seed=%d runner=%d" % (a.board, a.seed, rid))
        print("[287r6] ETAPE 1 -- le discriminant : `casterReason` (INDEPENDANT de la cible)")
        for at, vis in COUPLES:
            act = by_vis.get(vis)
            if act is None:
                print("  PORTEUR ABSENT de ce montage : %d (%s)" % (at, vis))
                continue
            r0 = _reason(rid, act["id"], at)
            cr = r0.get("casterReason") or {}
            print("  %-5d %-16s (%s u%-4s) casterReason=%-20s %-28s abilityState=%s"
                  % (at, vis, act["kind"], act["id"], cr.get("hex"),
                     ",".join(cr.get("reasons") or []) or "-", json.dumps(r0.get("abilityState"))))
            etape1.append((at, vis, act["id"], _hex(cr)))

        court = [x for x in etape1 if x[3] == O.CODE_AMONT]
        passants = [x for x in etape1 if x[3] == 0]
        print("  COURT-CIRCUITES en amont (casterReason == ValidRequest) : %d" % len(court))
        for at, vis, _cid, _ in court:
            print("     %-5d %s -- son `targetReason` ne dit RIEN du ciblage, pour AUCUNE cible"
                  % (at, vis))
        print("  PASSANTS (casterReason == 0) : %d" % len(passants))

        # ---------------------------------------------------------------- 2. BASCULE TEMPORELLE
        print("[287r6] ETAPE 2 -- bascule TEMPORELLE : on laisse retomber le cooldown initial")
        mow = by_vis.get(a.p_mow)
        if mow is None:
            empeche = "porteur %s absent" % (a.p_mow,)
        else:
            empeche = O.rendre_oracle_passant(_rpc, rid)
        if empeche:
            print("  %s" % empeche)
        else:
            r1 = _reason(rid, mow["id"], CIBLE_1201)
            cr1 = r1.get("casterReason") or {}
            print("  apres un tour : %-5d %-16s casterReason=%-20s %-28s abilityState=%s"
                  % (CIBLE_1201, a.p_mow, cr1.get("hex"),
                     ",".join(cr1.get("reasons") or []) or "-", json.dumps(r1.get("abilityState"))))
            etape2 = _hex(cr1)

        # ---------------------------------------------------------------- 3. CONFRONTATION
        print("[287r6] ETAPE 3 -- confrontation de la CASCADE (impossible tant que l'oracle "
              "court-circuitait)")
        if etape2 != 0:
            print("  NON CONFRONTE : l'oracle est encore court-circuite (casterReason=%s)"
                  % (etape2,))
        else:
            dec2, state, by_vis2, occupees, libres = _contexte(rid)
            cid = (by_vis2.get(a.p_mow) or {}).get("id")
            ab = P._porteur(CIBLE_1201)
            cibles = ([(t, "tuile OCCUPEE") for t in occupees[:4]]
                      + [(t, "tuile libre") for t in libres[:6]])
            res = {"accord_zero": [], "exact": [], "permissif": [], "viol": []}
            for tid, libelle in cibles:
                r = _reason(rid, cid, CIBLE_1201, tid)
                tr = r.get("targetReason") or {}
                nat = _hex(tr)
                port = int(is_invalid_target(state, int(cid), int(tid), ab) or 0)
                row = (tid, libelle, tr.get("hex"),
                       ",".join(tr.get("reasons") or []) or "-", hex(port))
                if nat == 0 and port == 0:
                    res["accord_zero"].append(row)
                elif nat == port:
                    res["exact"].append(row)
                elif port == 0:
                    res["permissif"].append(row)
                else:
                    res["viol"].append(row)
            for cle, titre in (("accord_zero", "accord sur ZERO"),
                               ("exact", "refus REPRODUIT A L'IDENTIQUE"),
                               ("permissif", "permissif (natif refuse, port 0)"),
                               ("viol", "VIOLATION (port != 0 et port != natif)")):
                print("  %-38s : %d" % (titre, len(res[cle])))
                for row in res[cle]:
                    print("     tgt u%-4s %-16s natif=%-20s %-28s port=%s" % row)
            etape3 = res
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    ok1 = bool([x for x in etape1 if x[3] == O.CODE_AMONT]) and \
        bool([x for x in etape1 if x[3] == 0])
    ok2 = etape2 == 0
    # L'etape 3 exige DEUX choses : aucune violation, ET un temoin non vide sur les tuiles
    # OCCUPEES -- c'est le regime exact que #287-r4-r1 avait mesure a travers le court-circuit.
    occ_confrontees = 0 if etape3 is None else sum(
        1 for cle in ("accord_zero", "exact", "permissif", "viol")
        for row in etape3[cle] if row[1] == "tuile OCCUPEE")
    ok3 = etape3 is not None and not etape3["viol"] and occ_confrontees > 0
    print("[287r6] ETAPE 1 (le discriminant separe)          : %s" % ("OK" if ok1 else "FAUTE"))
    print("[287r6] ETAPE 2 (l'oracle devient passant)        : %s"
          % ("OK" if ok2 else ("NON MESURE : " + empeche if empeche else "FAUTE")))
    print("[287r6] ETAPE 3 (%d tuile(s) OCCUPEE(s) confrontee(s)) : %s"
          % (occ_confrontees, "OK" if ok3 else "FAUTE"))
    print("[287r6] VERDICT : %s" % ("OK" if (ok1 and ok2 and ok3) else "FAUTES"))
    return 0 if (ok1 and ok2 and ok3) else 1


if __name__ == "__main__":
    raise SystemExit(main())
