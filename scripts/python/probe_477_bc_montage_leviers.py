"""#477-r5 / #477-r6 -- les deux leviers de montage de `BattleConfiguration`.

MESURE, pas garde : ce probe CONFRONTE au natif les deux champs que l'enquete #477
avait nommes sans les porter, et rend un verdict par levier.

    python probe_477_bc_montage_leviers.py --session 4 [--board MC1_67]

CE QU'IL ETABLIT
----------------
1. `BattleConfiguration.StartingActions` (champ @0xc0, `List<IInputMessage>`, consomme
   par `IdunBattle.Operations.SetupGameOperation$$ExecuteStartingMessages`) est
   **IGNORE par la deserialisation Newtonsoft** -- donc INATTEIGNABLE depuis notre
   chaine JSON (`initAndStart` -> `deserializeFromJson`). Le discriminant est un
   MAUVAIS TYPE : poser un scalaire la ou le champ attend une liste doit FAIRE LEVER
   la deserialisation si le champ est lu. Bras temoin obligatoire (`AbilitiesToHide`,
   une `List<T>` du meme BC qui, elle, EST deserialisee) : sans lui, un build vert ne
   distinguerait pas « champ ignore » de « Newtonsoft tolerant ».

2. `BattleConfiguration.UnitModifiers` (champ @0x50,
   `Dictionary<string, List<IdunBattleLogic.Shared.UnitModifier>>`) est, lui,
   PILOTABLE par le JSON, et ses huit `Id` sont ceux dispatches par
   `IdunBattle.Operations.SetupGameOperation$$ApplyModifiers`. Deux bras (temoin /
   modifie) sur les MEMES unites, MEME seed, MEME board -- la comparaison porte donc
   sur le seul dictionnaire.

3. Cas particulier mesure : `Id == "hp"` avec `Amount > 99` retire l'unite du
   deploiement (`...$$IsPredefinedUnitDisabledByModifiers` teste exactement
   `m.Id == "hp" && m.Amount > 99`). C'est le seul effet BINAIRE de la famille.

CE QU'IL NE MESURE PAS : la formule exacte de `fixedArmor` et `critDmg`. Ces deux-la
lisent un champ du COMPOSANT (`+0x48`) que `combatSnapshot` n'expose pas, donc l'ecart
observe est reel mais ne se recalcule pas depuis la valeur affichee. Le probe exige
qu'ils BOUGENT, pas qu'ils atteignent une valeur predite.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

# a-units du pool ork, et les modifiers portes par le bras MODIFIE. Une unite peut en
# porter plusieurs des lors que les stats visees sont distinctes.
A_UNITS = ["orksWarboss", "orksNob", "orksBigMek", "orksRuntherd", "orksKillaKan"]
# --unit-stat pose des bases NON NULLES la ou la normalisation rend 0 : sans elles,
# `blockChance`/`critChance`/`critDmg` seraient mesures sur 0 et un ecart de 0 vers -N
# ne se distinguerait pas d'un clamp.
UNIT_STAT = ("orksBigMek:BlockChance=50,CritChance=50;"
             "orksRuntherd:CritChance=50,CritDamage=300")
MODIFIERS = [
    ("orksWarboss", "dmg", 10, "attack", "pct"),
    ("orksWarboss", "fixedArmor", 50, "fixedArmor", "moves"),
    ("orksNob", "movement", 1, "movement", "abs"),
    ("orksNob", "hits", 1, "extraHits", "abs"),
    ("orksBigMek", "blockChance", 10, "blockChance", "abs"),
    ("orksBigMek", "critChance", 10, "critChance", "abs"),
    ("orksRuntherd", "critDmg", 100, "critDamage", "moves"),
]
HP_UNIT, HP_AMOUNT = "orksKillaKan", 111


def _run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(HERE))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _snapshot(sid: int, state_file: Path) -> dict[str, dict]:
    """visualId -> stats, pour les unites PRESENTES en bataille."""
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = st["runnerId"]
    obs = (_rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=30)
           .get("result") or {})
    snap = (_rpc(sid, "combatSnapshot", [{"runnerId": rid}], timeout=30)
            .get("result") or {})
    vis: dict[int, str] = {}
    for u in (obs.get("units") or []):
        vis[int(u["entityId"])] = str(u["visualId"])
        vis[int(u["squadId"])] = str(u["visualId"])
    out: dict[str, dict] = {}
    for u in (snap.get("units") or []):
        name = vis.get(int(u.get("entityId") or -1))
        if name:
            out[name] = u.get("stats") or {}
    return out


def _dispose(state_file: Path) -> None:
    if state_file.exists():
        _run(["dispose", "--state-file", str(state_file)])


def etape1_starting_actions(sid: int, board: str) -> list[str]:
    """`StartingActions` est-il lu par la deserialisation ? Deux bras de MAUVAIS TYPE."""
    fails: list[str] = []
    seed = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cases = [
        ("StartingActions", "le champ 0xc0", False),
        ("AbilitiesToHide", "temoin (List<T> deserialisee)", True),
    ]
    for field, label, must_throw in cases:
        bc = dict(seed)
        bc[field] = 42  # scalaire la ou le champ declare une List<T>
        sfile = OUT / f"probe477_seed_{field}.json"
        sfile.write_text(json.dumps(bc), encoding="utf-8")
        st = OUT / f"probe477_state_{field}.json"
        rc, out = _run(["build", "--seed", "777", "--board", board,
                        "--seed-bc", str(sfile), "--p-units", "ultraTitus",
                        "--a-units", "orksWarboss", "--state-file", str(st)])
        threw = ("initAndStart" in out and "error" in out)
        print(f"[etape1] {field:18s} {label:38s} -> "
              f"{'LEVE' if threw else 'passe'} (rc={rc})")
        if threw != must_throw:
            fails.append(f"etape1 {field}: attendu "
                         f"{'une levee' if must_throw else 'un build silencieux'}, "
                         f"obtenu {'une levee' if threw else 'un build silencieux'}")
        _dispose(st)
    if not fails:
        print("[etape1] VERDICT: BC.StartingActions (0xc0) est IGNORE par Newtonsoft "
              "-- INATTEIGNABLE depuis le JSON. Le temoin, lui, leve : la "
              "deserialisation SAIT refuser un mauvais type.")
    return fails


def etape2_unit_modifiers(sid: int, board: str) -> list[str]:
    """Temoin vs modifie, memes unites / seed / board / --unit-stat."""
    fails: list[str] = []
    common = ["build", "--seed", "777", "--board", board,
              "--p-units", "ultraTitus", "--a-units", ",".join(A_UNITS),
              "--unit-stat", UNIT_STAT]
    st_ctrl = OUT / "probe477_state_ctrl.json"
    rc, out = _run([*common, "--state-file", str(st_ctrl)])
    if rc != 0:
        return [f"etape2: build TEMOIN rc={rc}\n{out[-800:]}"]
    base = _snapshot(sid, st_ctrl)
    _dispose(st_ctrl)

    mod_args: list[str] = []
    for uid, ident, amount, _key, _kind in MODIFIERS:
        mod_args += ["--unit-modifier", f"{uid}:{ident}:{amount}"]
    mod_args += ["--unit-modifier", f"{HP_UNIT}:hp:{HP_AMOUNT}"]
    st_mod = OUT / "probe477_state_mod.json"
    rc, out = _run([*common, *mod_args, "--state-file", str(st_mod)])
    if rc != 0:
        _dispose(st_mod)
        return [f"etape2: build MODIFIE rc={rc}\n{out[-800:]}"]
    got = _snapshot(sid, st_mod)
    _dispose(st_mod)

    for uid, ident, amount, key, kind in MODIFIERS:
        b, g = (base.get(uid) or {}).get(key), (got.get(uid) or {}).get(key)
        if b is None or g is None:
            fails.append(f"etape2 {uid}:{ident}: stat '{key}' absente "
                         f"(temoin={b}, modifie={g})")
            continue
        if kind == "abs":
            want = b - amount
            ok = (g == want)
            detail = f"attendu {want} (= {b} - {amount}, ABSOLU)"
        elif kind == "pct":
            # `SetupGameOperation$$CalculatePercentage` : Fix64, Round puis Ceiling.
            delta = -(-(b * amount) // 100)
            want = b - delta
            ok = (g == want)
            detail = f"attendu {want} (= {b} - ceil({b}x{amount}%), POURCENTAGE)"
        else:  # "moves" : la base lue par le natif n'est pas la valeur affichee
            ok = (g != b)
            detail = "exige seulement un ECART (base native non exposee)"
        print(f"[etape2] {uid:14s} {ident:11s} {key:11s} temoin={b:<7} modifie={g:<7} "
              f"{'OK ' if ok else 'X  '}{detail}")
        if not ok:
            fails.append(f"etape2 {uid}:{ident}: temoin={b} modifie={g} -- {detail}")

    # hp > 99 : effet BINAIRE
    was, now = HP_UNIT in base, HP_UNIT in got
    print(f"[etape2] {HP_UNIT:14s} {'hp':11s} {'<deploy>':11s} temoin="
          f"{'present':<7} modifie={'present' if now else 'ABSENT':<7} "
          f"{'OK ' if (was and not now) else 'X  '}attendu ABSENT (Amount > 99)")
    if not was:
        fails.append(f"etape2 {HP_UNIT}: absent DEJA au temoin -- montage invalide")
    elif now:
        fails.append(f"etape2 {HP_UNIT}: hp={HP_AMOUNT} (>99) n'a pas empeche le "
                     f"deploiement")
    return fails


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=4)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--only", choices=["1", "2"], default=None)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    fails: list[str] = []
    if a.only in (None, "1"):
        fails += etape1_starting_actions(a.session, a.board)
    if a.only in (None, "2"):
        fails += etape2_unit_modifiers(a.session, a.board)

    print()
    if fails:
        print(f"ECHEC -- {len(fails)} constat(s) :")
        for f in fails:
            print("  -", f)
        return 1
    print("OK -- les deux leviers rendent le verdict attendu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
