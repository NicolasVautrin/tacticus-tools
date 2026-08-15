"""Confrontation LIVE de #952-r2 -- le filet de spawn de `GalvanicField` (passif d'`admecManipulus`).

CE QUE CE PROBE TRANCHE, et qui etait ECRIT A L'ENVERS dans la fiche :

  * la fiche disait << les DEUX seuls call-sites de `_seed_ability_owner_effects` sont le spawn de
    summon et l'atterrissage deep-strike, et aucun ne le materialise >>. Il y en a **TROIS** : le
    troisieme est `runner/snapshot.py` (la voie CAPTURE), qui boucle sur TOUTES les entites chargees
    -- donc le canal EST arrose pour un HERO deja sur le plateau ;
  * elle en concluait `BLOCAGE: porteur`. `admecManipulus` est **DANS `rl_duel build --list-pool`**
    (rank 17, 97 unites) et se monte en une commande : le porteur est CONFRONTABLE, et ce probe le
    fait. Le mot juste n'etait donc pas `porteur`.

CE QUE LE PROBE MESURE (et son TEMOIN, sans lequel il ne prouverait rien) :

  1. le porteur spawne, et `combatSnapshot` publie ses `unitFlags` ;
  2. le flag `CanRepairFullHealthUnits` y est -- son ORDINAL est LU dans `unitFlagTypes` du meme
     snapshot (`dumpEnum` au RUNTIME), jamais ecrit en dur : c'est ce qui le garde juste apres une
     renumerotation ;
  3. **TEMOIN** : une unite SANS `GalvanicField` ne porte PAS ce flag. Sans ce bras, un flag pose a
     tout le monde se lirait comme une confirmation (<< accord en regime DEGENERE = zero preuve >>) ;
  4. l'ECHANGE d'ability : `28 Repair` est ABSENTE des `abilityStates` du porteur et
     `1119 Repair_GalvanicField` presente -- les deux autres feuilles du `CreateBehaviour` natif
     (`RemoveActiveAbility(0x1c)` / `AddActiveAbility(0x45f)`).

⚠ Le decompile n'a PAS pu etre relu dans cette tranche (ghidra-mcp INJOIGNABLE sur 13337, port
refuse). La lecture des trois feuilles est celle de #952 ; ce probe en est la CONFIRMATION LIVE sur
le build `t6dpr4k06g`, ce qui est l'ordre inverse de la doctrine et doit etre dit.

    python probe_a899_952r2_galvanic_field.py --state-file <ABSOLU> [--runner <id>] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _resolve_session, _rpc          # noqa: E402

CARRIER = "admecManipulus"    # HERO Adeptus Mechanicus, AU POOL, porte `GalvanicField`
WITNESS = "tauCrisis"         # aucune `GalvanicField` -> ne doit PAS porter le flag
BOARD = "MC1_67"
SEED = 777
#: `ActiveAbilityType` -- ecrits par leur NOM cote port ; ici on compare des ids publies par le
#: snapshot, donc on garde les ordinaux AVEC leur nom en commentaire (le natif est cite verbatim).
REPAIR = 28                   # `ActiveAbilityType.Repair` -- RETIREE par le behaviour
REPAIR_GALVANIC = 1119        # `ActiveAbilityType.Repair_GalvanicField` -- AJOUTEE a la place
DEFEND = 1117                 # `DefendTheDivineWork`, l'active de kit (temoin d'un snapshot sain)
FLAG_NOM = "CanRepairFullHealthUnits"

_SID = None


def rpc(name, payload, timeout=150):
    global _SID
    if _SID is None:
        _SID = _resolve_session()
    return (_rpc(_SID, name, [payload], timeout=timeout).get("result") or {})


def build(state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--state-file", str(state_file),
            "--p-units", CARRIER, "--a-units", WITNESS]
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py")] + argv, cwd=str(HERE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print((p.stdout or "")[-2000:])
        print((p.stderr or "")[-1200:])
        raise SystemExit("[1] MONTAGE KO -- build rc=%d" % p.returncode)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    state_file = Path(args.state_file).resolve()
    rid = args.runner if args.runner is not None else build(state_file)
    print("[1] MONTAGE  runner=%d board=%s seed=%d porteur=%s temoin=%s"
          % (rid, BOARD, SEED, CARRIER, WITNESS))
    verdicts = []
    try:
        snap = rpc("combatSnapshot", {"runnerId": rid})
        ftypes = snap.get("unitFlagTypes") or {}
        # ORDINAL LU AU RUNTIME, jamais ecrit en dur (`dumpEnum` du capteur).
        ordinal = None
        if isinstance(ftypes, dict):
            ordinal = ftypes.get(FLAG_NOM)
            if ordinal is None:
                inv = {str(k): v for k, v in ftypes.items()}
                ordinal = inv.get(FLAG_NOM)
        print("    `UnitFlag.%s` lu dans `unitFlagTypes` = %s" % (FLAG_NOM, ordinal))
        verdicts.append(("flag_resolu_au_runtime", ordinal is not None))
        if ordinal is None:
            print("    -> IMPOSSIBLE DE CONTINUER sans l'ordinal : on ne le DEVINE pas.")
            return 1
        ordinal = int(ordinal)

        # APPARIEMENT PAR IDENTITE, jamais par position. Les `units[]` de `combatSnapshot` portent
        # `entityId` (PAS `id`, PAS `visualId` -- mesure sur `t6dpr4k06g`), et la `decisionView`
        # donne `id -> visualId`. Un appariement POSITIONNEL << marcherait >> ici a deux unites et
        # mentirait silencieusement des qu'un ordre change : l'identite est l'`entity_id`, partout.
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1})
        vid_by_id = {int(u["id"]): u.get("visualId") for u in (dv.get("units") or [])
                     if u.get("id") is not None}
        par_vid = {}
        for u in (snap.get("units") or []):
            eid = u.get("entityId", u.get("id"))
            vid = u.get("visualId") or (vid_by_id.get(int(eid)) if eid is not None else None)
            if vid:
                par_vid[vid] = u
        manquants = [n for n in (CARRIER, WITNESS) if n not in par_vid]
        if manquants:
            print("    KO -- unite(s) non appariee(s) par entityId : %s" % manquants)
            print("       snapshot entityIds=%s | decisionView ids=%s"
                  % ([u.get("entityId") for u in (snap.get("units") or [])], sorted(vid_by_id)))
            return 1

        # --- etage 2 : LE FLAG, avec son TEMOIN --------------------------------------------------
        flags_c = [int(f) for f in (par_vid[CARRIER].get("unitFlags") or [])]
        flags_w = [int(f) for f in (par_vid[WITNESS].get("unitFlags") or [])]
        print("[2] FLAG     %-18s unitFlags=%s" % (CARRIER, flags_c))
        print("             %-18s unitFlags=%s   <- TEMOIN" % (WITNESS, flags_w))
        porteur = ordinal in flags_c
        temoin = ordinal in flags_w
        print("    -> porteur de `GalvanicField` a le flag : %s | TEMOIN (sans le passif) : %s"
              % (porteur, temoin))
        if temoin:
            print("       ATTENTION -- LE TEMOIN PORTE LE FLAG AUSSI : la mesure est DEGENEREE,"
                  " ne rien conclure du verdict du porteur.")
        verdicts.append(("flag_discriminant", porteur and not temoin))

        # --- etage 3 : L'ECHANGE D'ABILITY -------------------------------------------------------
        # `abilityStates` = liste de DICTS `{id, name, kind, level, multiplier}` (mesure) -- pas une
        # liste d'entiers. Lire l'`id` par la cle, et garder le NOM pour l'affichage : c'est le nom
        # qui tranche une confusion d'enum, jamais l'ordinal.
        etats = [a for a in (par_vid[CARRIER].get("abilityStates") or []) if isinstance(a, dict)]
        ab_c = [int(a["id"]) for a in etats if a.get("id") is not None]
        print("[3] ECHANGE  %s abilityStates=%s"
              % (CARRIER, [(a.get("id"), a.get("name"), a.get("kind")) for a in etats]))
        print("    -> `28 Repair` RETIREE : %s | `1119 Repair_GalvanicField` AJOUTEE : %s"
              " | `1117 DefendTheDivineWork` (kit) : %s"
              % (REPAIR not in ab_c, REPAIR_GALVANIC in ab_c, DEFEND in ab_c))
        verdicts.append(("echange_ability", REPAIR not in ab_c and REPAIR_GALVANIC in ab_c
                         and DEFEND in ab_c))

        # --- etage 4 : LE PORTEUR EST-IL CONFRONTABLE ? (le mot du champ BLOCAGE) -----------------
        p = subprocess.run([sys.executable, str(HERE / "rl_duel.py"), "build", "--list-pool"],
                           cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        au_pool = CARRIER in ((p.stdout or "") + (p.stderr or ""))
        print("[4] PORTEUR  `%s` dans `rl_duel build --list-pool` : %s" % (CARRIER, au_pool))
        print("    -> le champ `BLOCAGE: porteur` de #952-r2 est %s"
              % ("JUSTE" if not au_pool else "FAUX (le porteur se monte en une commande)"))
        verdicts.append(("porteur_confrontable", au_pool))
    finally:
        if not args.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
                print("[*] runner %d dispose" % rid)
            except Exception as exc:                          # pragma: no cover - best effort
                print("[*] dispose KO : %s" % exc)

    print("")
    for nom, v in verdicts:
        print("  %-28s %s" % (nom, {True: "OK", False: "KO", None: "NON CONFRONTE"}[v]))
    return 0 if all(v is not False for _n, v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
