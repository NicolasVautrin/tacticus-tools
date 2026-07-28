"""#193b - RECROISEMENT de la face PORTEUR du gisement « playbooks de MOUVEMENT ».

`probe_193_move_playbook_inventory.py` derive le gisement (45) avec une gate de
confrontabilite OFFLINE : `kind == lineup` du gameconfig + presence dans `BC.Units`.
Le CLAUDE.md dit que cette gate MENT : **la SEULE porte valable est
`rl_duel.py build --list-pool`** (HERO/MoW spawnables au rank courant), plus le chemin
SUMMON (le summon compte meme absent du pool, via son summoner).

Ce probe fait ce recroisement, item par item :

  POOL-HERO      un porteur `lineup` est DANS le pool `--list-pool`      -> spawnable tel quel
  POOL-MOW       un porteur est une Machine of War du pool               -> spawnable tel quel
  SUMMON-HERO    porteur `summons`, son SUMMONER est dans le pool        -> spawnable via summoner
  SUMMON-ENV     porteur `summons`, seul summoner = portail Environment  -> board-dependant
  INJECT         porteur `lineup` du gameconfig HORS pool                -> catalog_inject.py
  NPC-ONLY       tous les porteurs sont npc                              -> NON PERTINENT
  INDIRECT       aucun chemin d'octroi etabli                            -> residu

Le pool est LU EN LIVE (une session Frida warmee suffit ; aucun (re)inject).

Usage :
  python probe_193b_carrier_pool_crosscheck.py                    # appelle rl_duel build --list-pool
  python probe_193b_carrier_pool_crosscheck.py --pool-file <p>    # rejoue sur une capture du pool
  python probe_193b_carrier_pool_crosscheck.py --all              # tout le gisement, pas que les 45
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
sys.path.insert(0, str(_HERE))

import probe_193_move_playbook_inventory as INV  # noqa: E402
import gameconfig as GC  # noqa: E402

# Le portail d'invocation de l'ENVIRONMENT : ses summons n'ont pas de summoner HERO, ils
# arrivent par le 3e joueur permanent (Environment) et exigent un board qui porte le portail.
_ENV_ABILITY_RE = re.compile(r"^EnvFactionSummons(:|$)")


def read_pool(pool_file: str | None) -> tuple[set[str], set[str], str]:
    """Rend (pool regulier, pool MoW, origine). LIVE par defaut."""
    if pool_file:
        txt = Path(pool_file).read_text(encoding="utf-8", errors="replace")
        origin = "file:%s" % pool_file
    else:
        cp = subprocess.run([sys.executable, str(_HERE / "rl_duel.py"), "build", "--list-pool"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            cwd=str(_HERE))
        if cp.returncode != 0:
            raise SystemExit("rl_duel build --list-pool a echoue:\n%s" % (cp.stderr or cp.stdout))
        txt = cp.stdout
        origin = "live (rl_duel build --list-pool)"
    units, mow = set(), set()
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("[pool]"):
            m = re.search(r"MoW spawnables\s*:\s*\[(.*)\]", s)
            if m:
                mow = {x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()}
            continue
        if s and not s.startswith("[") and " " not in s:
            units.add(s)
    if not units:
        raise SystemExit("pool vide - sortie inattendue de --list-pool")
    return units, mow, origin


def summoner_index() -> dict[str, list[tuple[str, list[str]]]]:
    """summonUnitId -> [(nom d'ability qui l'invoque, [unitIds portant cette ability])].

    Le lien summoner->summon n'est PAS un champ de l'unite : il vit dans la CONFIG d'ability,
    `units.abilities[<name>].constants.unitId` (verifie : `GeminaeSuperia.constants.unitId` =
    `adeptSmnGeminaeSuperia`). On remonte donc l'ability, puis les unites qui la portent
    (active/passive).
    """
    cfg = GC._cfg()
    abilities = cfg["units"]["abilities"]
    summons = set(cfg["units"]["summons"])
    holders: dict[str, list[str]] = {}
    ids = GC.all_unit_ids()
    for kind in ("lineup", "npc", "summons"):
        for uid in ids[kind]:
            u = GC.unit(uid) or {}
            for a in (u.get("passiveAbilities") or []) + (u.get("activeAbilities") or []):
                holders.setdefault(str(a), []).append(uid)
    out: dict[str, list[tuple[str, list[str]]]] = {}
    for aname, adef in abilities.items():
        sid = ((adef or {}).get("constants") or {}).get("unitId")
        if isinstance(sid, str) and sid in summons:
            out.setdefault(sid, []).append((aname, holders.get(aname, [])))
    return out


def classify(carriers: list[tuple[str, str]], pool: set[str], mow: set[str],
             smn: dict[str, list[tuple[str, list[str]]]]) -> tuple[str, str]:
    """Rend (verdict, chemin lisible). L'ordre des tests est l'ordre de PREFERENCE."""
    lineups = [uid for uid, k in carriers if k == "lineup"]
    summonz = [uid for uid, k in carriers if k == "summons"]
    npcs = [uid for uid, k in carriers if k == "npc"]

    in_mow = [u for u in lineups if u in mow]
    if in_mow:
        return "POOL-MOW", "MoW du pool: %s" % ",".join(sorted(in_mow))
    in_pool = [u for u in lineups if u in pool]
    if in_pool:
        return "POOL-HERO", "pool: %s" % ",".join(sorted(in_pool))

    # SUMMON : le summon compte meme absent du pool, si son summoner y est.
    env_only, off_pool, untraced = [], [], []
    for sid in summonz:
        entries = smn.get(sid, [])
        if not entries:
            untraced.append(sid)
            continue
        for aname, hold in entries:
            hero = [h for h in hold if h in pool or h in mow]
            if hero:
                return "SUMMON-HERO", "%s <- %s (%s)" % (sid, ",".join(sorted(hero)), aname)
            if _ENV_ABILITY_RE.match(aname):
                env_only.append("%s <- portail Environment (%s)" % (sid, aname))
            elif hold:
                off_pool.append("%s <- %s (%s) HORS POOL" % (sid, ",".join(sorted(hold)), aname))
            else:
                untraced.append("%s <- %s (ability sans porteur)" % (sid, aname))
    if env_only:
        return "SUMMON-ENV", "; ".join(sorted(set(env_only)))
    if off_pool:
        return "SUMMON-INJECT", "; ".join(sorted(set(off_pool)))
    if untraced:
        return "SUMMON-ORPHAN", "; ".join(sorted(set(untraced)))

    if lineups:
        return "INJECT", "lineup hors pool: %s" % ",".join(sorted(lineups))
    if npcs:
        return "NPC-ONLY", ",".join(sorted(npcs)[:3])
    return "INDIRECT", "aucun chemin d'octroi"


def main(argv: list[str]) -> int:
    pool_file = None
    if "--pool-file" in argv:
        pool_file = argv[argv.index("--pool-file") + 1]
    show_all = "--all" in argv

    pool, mow, origin = read_pool(pool_file)
    print("[#193b] pool = %d regulieres + %d MoW  (%s)" % (len(pool), len(mow), origin))

    h = INV.build_hash()
    parents = INV.load_classes(h)
    nat = INV.derive_native(parents)
    port = INV.derive_port()
    ported = set(port.values())
    enum = INV.load_enum(h, "IdunBattle.Entities.Enum.TriggeredAbilityType")
    bc = INV.load_bc()
    carriers = INV.carriers_index()
    catalog = INV.bc_catalog()
    _va, gsize = INV.ghidra_sizes(h)
    smn = summoner_index()

    own = set(nat["own_body_concrete"])
    rows = []
    for cls in nat["own_body_concrete"] + nat["inherited_body"]:
        s = INV.short(cls)
        name, aid = INV.map_ability(s, enum)
        car = carriers.get(name or "", [])
        sym = INV.movenext_symbol(cls, nat["iterators"].get(cls))
        nb = gsize.get(sym or "", None)
        if cls not in own:
            term = "common-body"
        elif nb == INV.ZERO_BODY_BYTES:
            term = "constant-zero"
        elif nb is None:
            term = "unknown"
        else:
            term = "active"
        verdict, path = classify(car, pool, mow, smn)
        rows.append({"short": s, "id": aid, "term": term,
                     "offline": INV.confrontability(car, catalog),
                     "verdict": verdict, "path": path,
                     "ported": s in ported, "bytes": nb,
                     "bc": INV.bc_keys_for(name, s, bc)})

    gis = [r for r in rows if not r["ported"] and r["term"] != "constant-zero"
           and r["offline"] in ("lineup-direct", "lineup-inject", "summon")]
    print("[#193b] gisement OFFLINE de #193 (a recroiser) : %d" % len(gis))

    tally: dict[str, int] = {}
    for r in gis:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("[#193b] verdicts LIVE : %s" % dict(sorted(tally.items())))
    spawn = [r for r in gis if r["verdict"] in ("POOL-HERO", "POOL-MOW", "SUMMON-HERO")]
    print("[#193b] ==> SPAWNABLE TEL QUEL (pool ou summoner du pool) : %d / %d"
          % (len(spawn), len(gis)))

    print("\n== recroisement item par item ==")
    for r in sorted(gis, key=lambda x: (x["verdict"], x["term"], x["short"])):
        print("  %-13s %-42s id=%-5s %-12s off=%-14s %s" % (
            r["verdict"], r["short"], r["id"], r["term"], r["offline"], r["path"]))

    dis = [r for r in gis if r["offline"] in ("lineup-direct", "lineup-inject")
           and r["verdict"] not in ("POOL-HERO", "POOL-MOW")]
    print("\n== DESACCORD offline(lineup) vs live(pool) : %d ==" % len(dis))
    for r in sorted(dis, key=lambda x: x["short"]):
        print("  %-42s off=%-14s live=%-13s %s" % (r["short"], r["offline"], r["verdict"], r["path"]))

    if show_all:
        print("\n== TOUT le gisement natif (108) ==")
        for r in sorted(rows, key=lambda x: (x["ported"], x["verdict"], x["short"])):
            print("  %-6s %-13s %-42s id=%-5s %s" % (
                "PORTE" if r["ported"] else "-", r["verdict"], r["short"], r["id"], r["term"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
