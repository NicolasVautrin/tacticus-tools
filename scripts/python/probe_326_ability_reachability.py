"""#326 phase 2 -- ETAGE B : JOIGNABILITE de chaque ability (porteurs + categorie hero/MoW/summon/npc).

Repond a « cette ability est-elle CONFRONTABLE, et par quel chemin ? » pour les 572 abilities du
gameconfig. Sortie machine : `logs/326_ability_reachability.tsv` (chemin RELATIF au checkout).

SOURCE DES PORTEURS = `unit_map.all_kits()` (repare par #323/PR #335, il lit les CINQ voies
derivables du gameconfig : `active`, `passive`, `relic`, `mythic`, `item`). On ne re-implemente pas
la resolution de porteurs -- on la CONSOMME, et on ne lit du gameconfig en direct que ce que
`unit_map` n'expose pas : la CHAINE SUMMON (voie explicitement NON couverte, cf.
`unit_map.VOIES_NON_COUVERTES`).

LA VOIE RELIQUE A TROIS ETATS, PAS DEUX
---------------------------------------
« porteur dans le pool » ne dit PAS « arrive en bataille avec sa relique » : la relique se
materialise dans `BattleConfiguration.Units[].TertiaryAbility`, et le seed BC n'en porte que 4
equipees (mesure re-derivee ci-dessous, pas heritee). D'ou :
  * `RELIQUE_EQUIPEE_SEED`  -- l'ability est deja dans un `TertiaryAbility` du seed BC : confrontable
    telle quelle.
  * `RELIQUE_POOL_A_EQUIPER` -- un porteur autorise est dans le pool, mais rien ne l'equipe : il faut
    ECRIRE le montage (patch du BC).
  * `RELIQUE_HORS_POOL`      -- porteur autorise hors pool : injection de catalogue
    (`docs/rl/case-92-catalog-injection.md` par. 6).

TRI-ETAT PARTOUT
----------------
  * Pool NON mesurable (RPC `buildNormalizedBC` muet) -> tous les verdicts « confrontable » sont
    rabattus en `NON_MESURABLE_POOL`. On ne rend jamais un ensemble vide pour « pas mesure ».
  * Une ability sans porteur sur les 5 voies derivables sort en `SANS_PORTEUR_MESURE` et porte la
    colonne `voies_non_couvertes` qui NOMME ce qui n'a pas ete regarde (`trait`, `liveevent`,
    `summon`, `tile`). Ce zero ne prouve pas que l'ability est morte -- meme doctrine que le pied
    de page de `unit_map find --ability`.
  * Les familles de MODE (`Enhancement*` de live-event, `Env*`/`PowerUp_*` d'environnement,
    `ComingSoon*`) sont sorties en categorie A PART (`HORS_KIT_UNITE`) : elles n'ont par
    construction aucun porteur-unite, les compter comme « non confrontables » gonflerait le
    denominateur d'items qui ne sont pas des abilities de kit.
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

import gameconfig as gc          # noqa: E402
import unit_map                  # noqa: E402

# Cles de `abilities[*].constants` qui NOMMENT une unite summon -- l'unique canal gameconfig du
# lien summoner -> summon (balaye exhaustivement : aucun autre chemin du document ne pointe vers
# `units.summons`, hormis `globalValues.traitVariables.ambushUnitToSpawn`).
SUMMON_REF_KEYS = ("unitId", "unitId_2", "unitId_3", "unitId_4", "unitToSpawn",
                   "summonId", "affectedUnitId")

# Familles d'abilities qui ne sont PAS des abilities de kit d'unite (canal de mode de jeu).
HORS_KIT_RE = re.compile(r"^(Enhancement|Env[A-Z]|PowerUp_|ComingSoon)")


def load_pool(pool_file, rank):
    """(units, mow) depuis `rl_duel build --list-pool` (RPC `buildNormalizedBC`, lecture seule --
    aucun inject). (None, None) si la mesure n'a pas pu etre faite."""
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
            # `[pool] 8 MoW spawnables : ['a', 'b', ...]` -- le PREMIER `[...]` est le prefixe
            # `[pool]` lui-meme : on prend la LISTE, apres le `:`.
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


def seed_equipped_abilities():
    """Noms d'ability EQUIPEES dans le seed BC (`Units[].TertiaryAbility`, un id numerique
    resolu par les mirrors d'enum). Retourne None si le seed n'est pas lisible (tri-etat)."""
    path = os.path.join(REPO, "data", "seed-bc.json")
    if not os.path.exists(path):
        return None
    try:
        bc = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return None
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.entities.active_ability_type import ActiveAbilityType as A
    out = {}
    for u in (bc.get("Units") or []):
        aid = u.get("TertiaryAbility")
        if not aid:
            continue
        name = None
        if aid in T._value2member_map_:
            name = T(aid).name
        elif aid in A._value2member_map_:
            name = A(aid).name
        if name:
            out.setdefault(name, set()).add(u.get("Id") or u.get("ConfigId"))
    return out


def build_index():
    """Index porteurs par ability, CONSOMMANT `unit_map` pour les 5 voies gameconfig."""
    kits = unit_map.all_kits()
    cat, voies_of = {}, {}
    carriers = defaultdict(lambda: defaultdict(set))   # ability -> voie -> {unitId}
    for k in kits:
        uid, kind = k["id"], k["kind"]
        if kind == "lineup":
            cat[uid] = "mow" if "MachineOfWar" in (k.get("traits") or []) else "hero"
        elif kind == "npc":
            cat[uid] = "npc"
        else:
            cat[uid] = "summon"
        voies_of[uid] = k.get("voies") or {}
        for voie, abils in (k.get("voies") or {}).items():
            for aid in abils:
                carriers[aid][voie].add(uid)

    c = gc._cfg()
    abilities = c["units"]["abilities"]
    summons = c["units"]["summons"]
    spawned_by = defaultdict(set)
    for aid, d in abilities.items():
        for key in SUMMON_REF_KEYS:
            v = (d.get("constants") or {}).get(key)
            if isinstance(v, str) and v in summons:
                spawned_by[v].add(aid)
    tv = (c.get("globalValues") or {}).get("traitVariables") or {}
    amb = tv.get("ambushUnitToSpawn")
    if isinstance(amb, str) and amb in summons:
        spawned_by[amb].add("trait:Ambush")
    return {"abilities": abilities, "cat": cat, "carriers": carriers,
            "spawned_by": spawned_by, "summons": summons}


def summoner_units(aid, idx, depth=0, seen=None):
    """Unites hero/MoW capables d'amener en bataille l'ability `aid` portee par un SUMMON.
    Remonte la chaine (un summon peut en spawner un autre) avec une profondeur bornee."""
    seen = seen or set()
    if aid in seen or depth > 3:
        return set()
    seen.add(aid)
    out = set()
    for voie, uids in idx["carriers"].get(aid, {}).items():
        for uid in uids:
            c = idx["cat"].get(uid, "?")
            if c == "summon":
                for sp in idx["spawned_by"].get(uid, ()):
                    out |= summoner_units(sp, idx, depth + 1, seen)
            elif c in ("hero", "mow"):
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

    equipped = seed_equipped_abilities()
    idx = build_index()
    non_couvertes = ",".join(n for n, _ in unit_map.VOIES_NON_COUVERTES)

    rows = []
    for aid in sorted(idx["abilities"]):
        chans = idx["carriers"].get(aid, {})
        by_cat = defaultdict(set)
        innate_voies, relic_voies = set(), set()
        for voie, uids in chans.items():
            for uid in uids:
                by_cat[idx["cat"].get(uid, "?")].add(uid)
            (relic_voies if voie in ("relic", "item", "mythic") else innate_voies).add(voie)

        hero_mow = by_cat["hero"] | by_cat["mow"]
        in_pool = (hero_mow & pool_all) if pool_measured else set()
        off_pool = hero_mow - in_pool

        # unites qui portent l'ability UNIQUEMENT par une voie relique/item
        relic_carriers = set()
        for voie in ("relic", "item"):
            relic_carriers |= chans.get(voie, set())
        kit_carriers = set()
        for voie in ("active", "passive", "mythic"):
            kit_carriers |= chans.get(voie, set())

        # chaine summon (voie NON couverte par unit_map : lue ici dans le gameconfig)
        summon_reach = set()
        for uid in by_cat["summon"]:
            for sp in idx["spawned_by"].get(uid, ()):
                summon_reach |= summoner_units(sp, idx)
        summon_reach_pool = (summon_reach & pool_all) if pool_measured else set()

        relic_state = "-"
        if relic_carriers:
            if equipped is not None and aid in equipped:
                relic_state = "RELIQUE_EQUIPEE_SEED"
            elif pool_measured and (relic_carriers & pool_all):
                relic_state = "RELIQUE_POOL_A_EQUIPER"
            elif pool_measured:
                relic_state = "RELIQUE_HORS_POOL"
            else:
                relic_state = "RELIQUE_POOL_NON_MESURE"

        if HORS_KIT_RE.match(aid) and not hero_mow and not by_cat["summon"]:
            verdict = "HORS_KIT_UNITE"
        elif not chans:
            verdict = "SANS_PORTEUR_MESURE"
        elif in_pool & kit_carriers:
            verdict = "CONFRONTABLE_POOL"
        elif relic_state == "RELIQUE_EQUIPEE_SEED":
            verdict = "CONFRONTABLE_POOL"
        elif summon_reach_pool:
            verdict = "CONFRONTABLE_SUMMON"
        elif relic_state == "RELIQUE_POOL_A_EQUIPER":
            verdict = "CONFRONTABLE_RELIQUE_A_EQUIPER"
        elif off_pool:
            verdict = "CONFRONTABLE_INJECTION"
        elif summon_reach:
            verdict = "CONFRONTABLE_SUMMON_INJECTION"
        elif by_cat["summon"]:
            verdict = "SUMMON_SANS_SUMMONER_MESURE"
        elif by_cat["npc"]:
            verdict = "NON_PERTINENT_NPC"
        else:
            verdict = "SANS_PORTEUR_MESURE"
        if not pool_measured and verdict.startswith("CONFRONTABLE"):
            verdict = "NON_MESURABLE_POOL"

        any_carrier = set()
        for uids in chans.values():
            any_carrier |= uids
        sample_src = in_pool or off_pool or relic_carriers or any_carrier
        rows.append({
            "ability": aid, "verdict": verdict, "relic_state": relic_state,
            "hero_pool": len(in_pool), "hero_offpool": len(off_pool),
            "n_hero": len(by_cat["hero"]), "n_mow": len(by_cat["mow"]),
            "n_summon": len(by_cat["summon"]), "n_npc": len(by_cat["npc"]),
            "voies": ",".join(sorted(chans)) or "-",
            "summoners": ",".join(sorted(summon_reach)[:4]) or "-",
            "sample_carrier": ",".join(sorted(sample_src)[:3]) or "-",
            "variante_portee": "-",
            "voies_non_couvertes": non_couvertes if not chans else "-",
        })

    # Beaucoup de « sans porteur » sont des versions REMPLACEES par une variante `*Reworked` (ou
    # inversement) qui, elle, a un porteur : le dire evite de lire ce zero comme « mecanique morte ».
    by_name = {r["ability"]: r for r in rows}
    for r in rows:
        if r["verdict"] not in ("SANS_PORTEUR_MESURE", "SUMMON_SANS_SUMMONER_MESURE"):
            continue
        base = r["ability"]
        for other in (base + "Reworked", base[:-len("Reworked")] if base.endswith("Reworked") else None):
            o = by_name.get(other) if other else None
            if o is not None and o["verdict"].startswith("CONFRONTABLE"):
                r["variante_portee"] = "%s (%s)" % (other, o["verdict"])
                break

    out_path = os.path.join(REPO, args.out)
    if not os.path.isdir(os.path.dirname(out_path)):
        os.makedirs(os.path.dirname(out_path))
    cols = ["ability", "verdict", "relic_state", "hero_pool", "hero_offpool", "n_hero", "n_mow",
            "n_summon", "n_npc", "voies", "summoners", "sample_carrier", "variante_portee",
            "voies_non_couvertes"]
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.reachability.v2\trank=%d\tpool_measured=%s\tseed_equipped=%s\n"
                 % (args.rank, "yes" if pool_measured else "NO",
                    "yes" if equipped is not None else "NO"))
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")

    counts, relics = defaultdict(int), defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1
        if r["relic_state"] != "-":
            relics[r["relic_state"]] += 1
    print("abilities gameconfig : %d" % len(rows))
    print("pool mesure : %s (%s units + %s MoW)" % (
        "oui" if pool_measured else "NON -- verdicts rabattus en NON_MESURABLE_POOL",
        len(pool_units) if pool_measured else "?", len(pool_mow) if pool_measured else "?"))
    print("seed BC : %s equipees (TertiaryAbility)" % (
        len(equipped) if equipped is not None else "NON MESURABLE"))
    for v in sorted(counts, key=lambda k: -counts[k]):
        print("  %-32s %4d" % (v, counts[v]))
    print("voie RELIQUE, trois etats :")
    for v in sorted(relics, key=lambda k: -relics[k]):
        print("  %-32s %4d" % (v, relics[v]))
    n_var = sum(1 for r in rows if r["variante_portee"] != "-")
    print("dont zeros expliques par une VARIANTE portee (`*Reworked`) : %d" % n_var)
    print("voies NON couvertes (tout zero ci-dessus les porte) : %s" % non_couvertes)
    print("ecrit : %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
