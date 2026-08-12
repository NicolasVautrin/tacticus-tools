"""Confrontation LIVE de #964-r1 -- `EcogSupport` (1487), passif de `votanIronmaster` << Vynn >>.

`votanIronmaster` est un HERO **hors pool** -> `catalog_inject.write_augmented_seed_bc`
(case-92 §6). Les allies a reparer doivent etre MECANIQUES (`AttackQuery$$EntityCanBeRepaired`
finit sur `IsAffectedByHealType(entity, 1 Mechanical)`).

QUATRE ETAGES, chacun mesurant une chose que le garde offline ne PEUT pas voir :

  1. MONTAGE  -- les trois unites spawnent, et Vynn porte bien `28 Repair` en `kind: granted`
                 (la voie TRAIT `Mechanic`, PAS son `activeAbilities` : c'est deja une mesure) ;
  2. FLAG     -- `UnitFlag.CanRepairFullHealthUnits`, AVEC SON TEMOIN. Les deux cibles sont forcees
                 a PV PLEINS, ou `EntityCanBeRepaired` n'a plus qu'UN disjunct possible. On compare
                 Vynn (porteur d'`EcogSupport`) a `necroSpyder` -- MEME trait `Mechanic`, MEME
                 ability `28 Repair`, MEMES cibles. Un montage sans temoin ne prouverait rien : une
                 cible acceptee pourrait l'etre parce qu'elle est entamee ;
  3. SUBSTRAT -- le repair-type se derive-t-il du KIT ou du TRAIT ? C'est le point ou une
                 derivation par `activeAbilities` rendrait `None` et laisserait le port MUET ;
  4. TRIGGER  -- une reparation REELLE de Vynn fait-elle apparaitre un E-Cog, et sous quel
                 `AbilityState` ?

GROUND TRUTH MESUREE le 2026-08-12 (runner `build#1232`, board `MC1_67`, seed 777) :

    [Ability_Power e=79 <<EcogSupport>>]
      [AddUnit e=103]
        AddUnit e=103  Unit_Owner_Id=3 Unit_IsSummoned=1 Unit_SpawnSource=2 Unit_Parent_Id=79
                       Unit_Foot_Tile_Id_1=30
        ChangeStats e=103  MaxHealth=3989 FixedArmor=1496 Attack=1496 Movement=3
        ChangeAbility e=103  ActiveAbility_Id=69 Level=50 VariableMultiplierPercentage=180
        ChangeAbility e=103  ActiveAbility_Id=28 Level=50 VariableMultiplierPercentage=180
        ChangeAbility e=103  TriggeredAbility_Id=1514 Level=50 VariableMultiplierPercentage=180
      ChangeStats e=103  TurnFinished=1 / ActionsAvailable=0

et, sur le meme montage, la ventilation du flag :

    votanIronmaster    targets=[necroDestroyer, necroSpyder]  fromHere=[necroDestroyer, necroSpyder]
    necroSpyder        targets=[]                             fromHere=[]
    necroDestroyer     targets=[]                             fromHere=[]
    abilityReason(necroSpyder -> necroDestroyer) = TargetIsRepairable (0x10000)
    abilityReason(vynn        -> necroDestroyer) = NoBrokenTargetingRule

Discipline runner : `--state-file` ABSOLU, `--runner` explicite pour rejouer, `dispose` en sortie.
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _resolve_session, _rpc         # noqa: E402

CARRIER = "votanIronmaster"        # Vynn -- HERO Leagues of Votann, HORS pool, porte `EcogSupport`
ALLY = "necroSpyder"               # allie MECANIQUE + trait `Mechanic` -> il a `28 Repair` AUSSI,
                                   # et PAS `EcogSupport` : c'est le TEMOIN du flag
ALLY2 = "necroDestroyer"           # 2e cible mecanique (le temoin doit avoir qui reparer)
FOE = "necroWarden"
BOARD = "MC1_67"
SEED = 777
SUMMON_ID = "votanSmnEcog"
REPAIR_ID = 28                     # `ActiveAbilityType.Repair`, accorde par le trait `Mechanic`
HP_FULL = 9000                     # PV forces EGAUX au max -> cibles INTACTES

_SID = None


def rpc(name, payload, timeout=150):
    global _SID
    if _SID is None:
        _SID = _resolve_session()
    return (_rpc(_SID, name, [payload], timeout=timeout).get("result") or {})


def build(state_file: Path) -> int:
    import catalog_inject as CI
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    seed_bc = state_file.with_name(state_file.stem + "-seedbc.json")
    CI.write_augmented_seed_bc(str(seed_bc), [CARRIER])
    # PV PLEINS sur les DEUX cibles : c'est ce qui rend l'etage 2 discriminant.
    stat = ";".join("%s:Health=%d,RemainingHealth=%d" % (u, HP_FULL, HP_FULL)
                    for u in (ALLY, ALLY2))
    argv = ["build", "--seed", str(SEED), "--board", BOARD,
            "--state-file", str(state_file), "--seed-bc", str(seed_bc),
            "--p-units", "%s,%s,%s" % (CARRIER, ALLY, ALLY2), "--a-units", FOE,
            "--unit-stat", stat]
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py")] + argv,
                       cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        print((p.stdout or "")[-2500:])
        print((p.stderr or "")[-1500:])
        raise SystemExit("[1] MONTAGE KO -- build rc=%d" % p.returncode)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _repair_targets(rid, unit_id):
    """Les cibles de `28 Repair` pour `unit_id`, LUES dans la reponse `abilityTargets`.

    ⚠ Le parametre est `abilityType`, PAS `abilityId` -- et la reponse ventile `targets`
    (ce tour, MOVE inclus) / `fromHere` (sans bouger). Se tromper de cle rend une liste VIDE qui se
    lit comme un refus du natif : un faux negatif parfaitement silencieux."""
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": int(unit_id),
                               "abilityType": REPAIR_ID})
    us = (r.get("units") or [{}])[0]
    ab = next((a for a in (us.get("abilities") or []) if a.get("abilityId") == REPAIR_ID), None)
    if ab is None:
        return None, None
    return ([t.get("visualId") for t in (ab.get("targets") or [])],
            [t.get("visualId") for t in (ab.get("fromHere") or [])])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    state_file = Path(args.state_file).resolve()
    rid = args.runner if args.runner is not None else build(state_file)
    print("[1] MONTAGE  runner=%d board=%s seed=%d" % (rid, BOARD, SEED))
    verdicts = []
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1})
        vus = {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}
        manquants = [n for n in (CARRIER, ALLY, ALLY2) if n not in vus]
        if manquants:
            print("    KO -- unite(s) absente(s) : %s" % manquants)
            return 1
        vynn = vus[CARRIER]
        abis = [(a.get("id"), a.get("name"), a.get("kind")) for a in (vynn.get("abilities") or [])]
        granted = [(i, n) for i, n, k in abis if k == "granted"]
        print("    %s" % {n: vus[n]["id"] for n in (CARRIER, ALLY, ALLY2)})
        print("    abilities de Vynn : %s" % (abis,))
        print("    -> `28 Repair` en kind=granted (voie TRAIT, pas activeAbilities) : %s"
              % ("OUI" if (REPAIR_ID, "Repair") in granted else "NON"))
        verdicts.append(("repair_granted_par_trait", (REPAIR_ID, "Repair") in granted))

        # --- etage 2 : le FLAG, AVEC SON TEMOIN --------------------------------------------------
        pleins = {n: int(vus[n].get("hp") or 0) == HP_FULL for n in (ALLY, ALLY2)}
        print("[2] FLAG     PV forces : %s" % pleins)
        vue = {}
        for who in (CARRIER, ALLY, ALLY2):
            tg, ici = _repair_targets(rid, vus[who]["id"])
            vue[who] = (tg, ici)
            print("    %-18s targets=%s fromHere=%s" % (who, tg, ici))
        porteur_cible = bool(vue[CARRIER][1])
        temoin_cible = bool(vue[ALLY][1])
        print("    -> porteur du flag cible a PV pleins : %s | TEMOIN (meme trait, meme ability,"
              " sans EcogSupport) : %s" % (porteur_cible, temoin_cible))
        if temoin_cible:
            print("       ⚠ LE TEMOIN MORD AUSSI -- le flag n'est PAS le discriminant de cette"
                  " mesure ; ne rien conclure du verdict du porteur.")
        rr = rpc("abilityReason", {"runnerId": rid, "casterId": int(vus[ALLY]["id"]),
                                   "abilityType": REPAIR_ID, "targetId": int(vus[ALLY2]["id"])})
        print("    raison du refus TEMOIN : %s"
              % ((rr.get("targetReason") or {}).get("reasons")))
        verdicts.append(("flag_discriminant", porteur_cible and not temoin_cible))

        # --- etage 3 : le SUBSTRAT du repair-type ------------------------------------------------
        import gameconfig as GC
        ecog = GC.unit(SUMMON_ID) or {}
        par_kit = list(ecog.get("activeAbilities") or [])
        par_trait = "Mechanic" in (ecog.get("traits") or [])
        print("[3] SUBSTRAT %s : activeAbilities=%s traits=%s" % (SUMMON_ID, par_kit,
                                                                  ecog.get("traits")))
        print("    -> une derivation par KIT SEUL rendrait None (filtre TOUJOURS vide, port MUET) ;"
              " la voie TRAIT repond : %s" % par_trait)
        verdicts.append(("substrat_est_le_trait", not par_kit and par_trait))

        # --- etage 4 : le TRIGGER ----------------------------------------------------------------
        avant = {int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
        argv = ["act", "ability", "--state-file", str(state_file),
                "--caster", str(vus[CARRIER]["id"]), "--target", str(vus[ALLY2]["id"]),
                "--ability", str(REPAIR_ID)]
        p = subprocess.run([sys.executable, str(HERE / "rl_duel.py")] + argv,
                           cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        flux = (p.stdout or "") + (p.stderr or "")
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1})
        neufs = [u for u in (dv2.get("units") or [])
                 if int(u.get("id", -1)) not in avant]
        cite = "EcogSupport" in flux
        spawn = bool(neufs) or "AddUnit" in flux
        print("[4] TRIGGER  act rc=%d | unites neuves=%s"
              % (p.returncode, [(u.get("id"), u.get("visualId")) for u in neufs]))
        print("    -> le stream natif cite `EcogSupport` : %s | une unite est AJOUTEE : %s"
              % (cite, spawn))
        for ligne in flux.splitlines():
            if "EcogSupport" in ligne or "AddUnit e=" in ligne or "TriggeredAbility_Id=1514" in ligne:
                print("       | %s" % ligne.strip()[:150])
        verdicts.append(("trigger_fire_et_spawne", cite and spawn))
    finally:
        if not args.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
                print("[*] runner %d dispose" % rid)
            except Exception as exc:                       # pragma: no cover - best effort
                print("[*] dispose KO : %s" % exc)

    print()
    for nom, v in verdicts:
        print("  %-28s %s" % (nom, {True: "OK", False: "KO", None: "NON CONFRONTE"}[v]))
    return 0 if all(v is not False for _n, v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
