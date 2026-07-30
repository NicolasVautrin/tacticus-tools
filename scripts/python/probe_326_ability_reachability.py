"""#326 phase 2 -- ETAGE B : JOIGNABILITE de chaque ability (porteurs + categorie hero/MoW/summon/npc).

Repond a « cette ability est-elle CONFRONTABLE, et par quel chemin ? » pour les 572 abilities du
gameconfig. Sortie machine : `logs/326_ability_reachability.tsv` (chemin RELATIF au checkout).

CANAUX DE PORTAGE LUS -- les cinq, pas seulement les deux evidents :
  1. `units.lineup[*].activeAbilities|passiveAbilities|mythicAbilities`   (hero + MoW)
  2. `units.npc[*].activeAbilities|passiveAbilities|relicAbilities|mythicAbilities`
  3. `units.summons[*].activeAbilities|passiveAbilities`
  4. RELIQUE : `items[*]` avec `isRelic == true` -> `abilityId` + `allowedUnits`. C'est le canal
     que `unit_map find --ability` ne voyait pas (#323) : il a rendu « 0 porteur, dead » pour une
     ability qu'un heros du pool porte EQUIPEE (`BC.Units[].TertiaryAbility`). On le lit ICI en
     direct dans le gameconfig, et on le rend comme un ETAT A PART (`relic`), jamais fondu dans
     les porteurs innes.
  5. CHAINE SUMMON : un summon n'entre pas au pool ; on l'amene en spawnant son summoner. Le lien
     se lit dans `abilities[*].constants.unitId|unitId_2|unitId_3|unitId_4|unitToSpawn|summonId`
     -> on remonte a l'ability de spawn, donc a SES porteurs. Une ability portee UNIQUEMENT par
     un summon reste donc CONFRONTABLE si le summoner l'est (cf. CLAUDE.md, gate de confrontabilite).

POOL : `python rl_duel.py build --list-pool` (RPC `buildNormalizedBC` -- lecture seule, aucun
inject). Sa sortie est mise en cache dans `logs/326_list_pool_rank<N>.txt` ; `--pool-file` permet
de la rejouer offline. HORS POOL != NON CONFRONTABLE : un heros hors pool s'injecte
(`docs/rl/case-92-catalog-injection.md` par. 6) -- il sort donc en `hero_offpool`, pas en zero.

TRI-ETAT : une ability sans aucun porteur dans CES canaux n'est pas declaree morte -- elle sort
en `SANS_PORTEUR_MESURE`, parce que le DSL lui-meme peut en accorder une a l'execution
(`DSLBehaviors$$AddTriggeredAbility`), canal que le gameconfig ne materialise pas.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts", "python"))

import gameconfig as gc  # noqa: E402

SUMMON_REF_KEYS = ("unitId", "unitId_2", "unitId_3", "unitId_4", "unitToSpawn",
                   "summonId", "affectedUnitId")


def load_pool(pool_file, rank):
    """(units, mow) depuis la sortie de `rl_duel build --list-pool`. Retourne (None, None) si la
    mesure n'a pas pu etre faite -- tri-etat : on ne rend JAMAIS un ensemble vide pour
    « pas mesure »."""
    path = os.path.join(REPO, pool_file) if not os.path.isabs(pool_file) else pool_file
    if not os.path.exists(path):
        try:
            res = subprocess.run(
                [sys.executable, "rl_duel.py", "build", "--list-pool", "--rank", str(rank)],
                cwd=os.path.join(REPO, "scripts", "python"),
                capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
        except Exception:
            return None, None
        if res.returncode != 0:
            return None, None
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(res.stdout)
    txt = io.open(path, encoding="utf-8", errors="replace").read()
    units, mow, in_list = [], [], False
    for line in txt.splitlines():
        if line.startswith("[pool]") and "MoW" in line:
            # La ligne vaut `[pool] 8 MoW spawnables : ['a', 'b', ...]` -- le PREMIER `[...]` est
            # le prefixe `[pool]` lui-meme : on prend la LISTE, apres le `:`.
            m = re.search(r":\s*\[([^\]]*)\]", line)
            if m:
                mow = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
            in_list = False
        elif line.startswith("[pool]"):
            in_list = True
        elif in_list and line.startswith("   "):
            units.append(line.strip())
    if not units:
        return None, None
    return set(units), set(mow)


def build_index():
    c = gc._cfg()
    u = c["units"]
    lineup, npc, summons = u["lineup"], u["npc"], u["summons"]
    abilities = u["abilities"]
    items = c.get("items") or {}

    # unite -> categorie
    cat = {}
    for uid, d in lineup.items():
        traits = d.get("traits") or []
        cat[uid] = "mow" if "MachineOfWar" in traits else "hero"
    for uid in npc:
        cat.setdefault(uid, "npc")
    for uid in summons:
        cat.setdefault(uid, "summon")

    # ability -> porteurs INNES, par canal
    carriers = defaultdict(lambda: defaultdict(set))   # aid -> canal -> {uid}
    for src, table in (("lineup", lineup), ("npc", npc), ("summons", summons)):
        for uid, d in table.items():
            for field in ("activeAbilities", "passiveAbilities", "mythicAbilities",
                          "relicAbilities"):
                for aid in (d.get(field) or []):
                    carriers[aid][field].add(uid)

    # ability -> unites autorisees par une RELIQUE
    relic_units = defaultdict(set)
    relic_items = defaultdict(set)
    for iid, d in items.items():
        if not isinstance(d, dict) or not d.get("isRelic"):
            continue
        aid = d.get("abilityId")
        if not aid:
            continue
        relic_items[aid].add(iid)
        for uid in (d.get("allowedUnits") or []):
            relic_units[aid].add(uid)

    # summon -> abilities qui le font apparaitre
    spawned_by = defaultdict(set)
    for aid, d in abilities.items():
        for k in SUMMON_REF_KEYS:
            v = (d.get("constants") or {}).get(k)
            if isinstance(v, str) and v in summons:
                spawned_by[v].add(aid)
    return {
        "abilities": abilities, "cat": cat, "carriers": carriers,
        "relic_units": relic_units, "relic_items": relic_items,
        "spawned_by": spawned_by, "lineup": lineup, "npc": npc, "summons": summons,
    }


def reachable_units_of(aid, idx, depth=0, seen=None):
    """Ensemble des unites qui peuvent AMENER l'ability en bataille, avec le chemin.
    Remonte la chaine summon (profondeur bornee : un summon dont le summoner est lui-meme un
    summon existe -- SendInTheNextWave)."""
    seen = seen or set()
    if aid in seen or depth > 3:
        return set()
    seen.add(aid)
    out = set()
    for chan, uids in idx["carriers"].get(aid, {}).items():
        for uid in uids:
            c = idx["cat"].get(uid, "?")
            if c == "summon":
                # le summon lui-meme n'est pas spawnable : on remonte a ses summoners
                for sp_aid in idx["spawned_by"].get(uid, ()):
                    for uid2 in reachable_units_of(sp_aid, idx, depth + 1, seen):
                        out.add(uid2)
                out.add(uid)
            else:
                out.add(uid)
    for uid in idx["relic_units"].get(aid, ()):
        out.add(uid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--pool-file", default=None)
    ap.add_argument("--out", default="logs/326_ability_reachability.tsv")
    args = ap.parse_args()

    pool_file = args.pool_file or ("logs/326_list_pool_rank%d.txt" % args.rank)
    pool_units, pool_mow = load_pool(pool_file, args.rank)
    pool_measured = pool_units is not None
    pool_all = (pool_units | pool_mow) if pool_measured else set()

    idx = build_index()
    rows = []
    for aid in sorted(idx["abilities"]):
        chans = idx["carriers"].get(aid, {})
        innate = set()
        for uids in chans.values():
            innate |= uids
        by_cat = defaultdict(set)
        for uid in innate:
            by_cat[idx["cat"].get(uid, "?")].add(uid)
        relic_u = idx["relic_units"].get(aid, set())
        relic_by_cat = defaultdict(set)
        for uid in relic_u:
            relic_by_cat[idx["cat"].get(uid, "?")].add(uid)

        hero_mow = by_cat["hero"] | by_cat["mow"] | relic_by_cat["hero"] | relic_by_cat["mow"]
        in_pool = (hero_mow & pool_all) if pool_measured else set()
        off_pool = hero_mow - in_pool

        # chaine summon : un summon carrier est joignable si un summoner l'est
        summon_reach = set()
        for uid in by_cat["summon"]:
            for sp_aid in idx["spawned_by"].get(uid, ()):
                for uid2 in reachable_units_of(sp_aid, idx):
                    c2 = idx["cat"].get(uid2, "?")
                    if c2 in ("hero", "mow"):
                        summon_reach.add(uid2)
        summon_reach_pool = (summon_reach & pool_all) if pool_measured else set()

        if not innate and not relic_u:
            verdict = "SANS_PORTEUR_MESURE"
        elif in_pool:
            verdict = "CONFRONTABLE_POOL"
        elif summon_reach_pool:
            verdict = "CONFRONTABLE_SUMMON"
        elif off_pool:
            verdict = "CONFRONTABLE_INJECTION"
        elif summon_reach:
            verdict = "CONFRONTABLE_SUMMON_INJECTION"
        elif by_cat["summon"] and not summon_reach:
            verdict = "SUMMON_SANS_SUMMONER_MESURE"
        elif by_cat["npc"]:
            verdict = "NON_PERTINENT_NPC"
        else:
            verdict = "SANS_PORTEUR_MESURE"
        if not pool_measured and verdict.startswith("CONFRONTABLE"):
            verdict = "NON_MESURABLE_POOL"

        rows.append({
            "ability": aid, "verdict": verdict,
            "hero_pool": len(in_pool), "hero_offpool": len(off_pool),
            "n_hero": len(by_cat["hero"]), "n_mow": len(by_cat["mow"]),
            "n_summon": len(by_cat["summon"]), "n_npc": len(by_cat["npc"]),
            "n_relic_units": len(relic_u),
            "relic_items": ",".join(sorted(idx["relic_items"].get(aid, ()))) or "-",
            "summon_reach": ",".join(sorted(summon_reach)[:4]) or "-",
            "sample_carrier": ",".join(sorted(in_pool or off_pool or innate or relic_u)[:3]) or "-",
            "channels": ",".join(sorted(chans)) or ("relic" if relic_u else "-"),
        })

    out_path = os.path.join(REPO, args.out)
    if not os.path.isdir(os.path.dirname(out_path)):
        os.makedirs(os.path.dirname(out_path))
    cols = ["ability", "verdict", "hero_pool", "hero_offpool", "n_hero", "n_mow", "n_summon",
            "n_npc", "n_relic_units", "relic_items", "summon_reach", "sample_carrier", "channels"]
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.reachability.v1\trank=%d\tpool_measured=%s\n"
                 % (args.rank, "yes" if pool_measured else "NO"))
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")

    counts = defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1
    print("abilities gameconfig : %d" % len(rows))
    print("pool mesure : %s (%s units + %s MoW)" % (
        "oui" if pool_measured else "NON -- verdicts rabattus en NON_MESURABLE_POOL",
        len(pool_units) if pool_measured else "?", len(pool_mow) if pool_measured else "?"))
    for v in sorted(counts, key=lambda k: -counts[k]):
        print("  %-30s %4d" % (v, counts[v]))
    n_relic = sum(1 for r in rows if r["n_relic_units"])
    print("abilities accordees par une RELIQUE (canal invisible a unit_map, #323) : %d" % n_relic)
    print("ecrit : %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
