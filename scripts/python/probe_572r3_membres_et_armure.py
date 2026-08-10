#!/usr/bin/env python3
"""#572-r3 -- `NumberOfMembers`(20) et `Armor`(4), les DEUX AUTRES stats fill-up du natif.

    python probe_572r3_membres_et_armure.py [--session N] [--board MC1_67]
                                            [--p-units ...] [--a-units ...] [--tours 14]

CE QU'IL MESURE
---------------
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` (xref UNIQUE d'`ApplyModifier`) a TROIS
cases qui vont a `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` :

    case 4  = StatType.Armor            -> `IdunBattle.Entities.Components.ArmorComponent`
    case 5  = StatType.Health           -> `IdunBattle.Entities.Components.HealthComponent`
    case 20 = StatType.NumberOfMembers  -> `IdunBattle.Entities.Components.NumberOfMembersComponent`

(⚠ le composant du case 20 s'appelle `NumberOfMembersComponent` -- `GroupUnitComponent` n'existe
PAS dans le build `rnca9r7q6c` ; les trois heritent bien de `FillUpStatComponent`, LU dans
`data/symbols/<build>/frida/classes.tsv`.)

Sur un `FillUpStatComponent`, `GetStatPart` SEPARE trois lectures que le port CONFOND :

    case 0 (Current)  -> `*(int*)(this+0x18)`
    case 2 (Maximum)  -> `get_CurrentMaximumValue()` = override ?? (clamp(mod) + base@+0x14)
    case 3 (Initial)  -> `*(int*)(this+0x10)`

Cote port, `NumberOfMembers` et `Armor` vivent dans `UnitStats` sous un `StatComponent`
generique, dont `get_stat_part` rend `get_CurrentValue()` pour les parts 0 ET 2. Ce probe
confronte, par unite et par tour :

    natif  : `combatSnapshot.stats.numberOfMembers` (= GetStat part Current)
             `combatSnapshot.numberOfMembersMax`    (= GetStat part Maximum, capteur #477-r15-r5)
             `observeBattle.armor` (champ BRUT `RemainingValue(+0x18)` du `ArmorComponent`, LU
             dans `frida/hooks/game/match-state.ts::projectSquadStats`)
             `combatSnapshot.armorMax`              (= GetStat part Maximum, capteur #477-r15-r7)
    port   : `seed_unit_stats(...)` re-seede depuis CE snapshot, puis
             `UnitStats.get_stat(<stat>, part)` pour les parts 0/2/3.

⚠ POURQUOI L'ARMURE PASSE PAR `observeBattle` ET PAS PAR `combatSnapshot.stats` : la cle `armor`
n'est PAS dans `COMBAT_STAT_IDS` -- elle vit dans `STAT_IDS_MAX_SEUL` (`rpc-snapshot.ts`), la
table des ids lus UNIQUEMENT en `StatPart.Maximum`. `combatSnapshot` ne publie donc AUCUN
`stats.armor`, et un probe qui l'attendrait ecarterait toutes les unites en silence (mesure : 0
entite vue). Corollaire mesure : `seed_unit_stats` n'inscrit JAMAIS de composant pour
`StatType.Armor`, donc `UnitStats.get_stat(4, part)` rend `0` par la branche « composant absent ».

LE TEMOIN, ET POURQUOI IL EST DISCRIMINANT SANS AUCUNE STAT-MODIFICATION
------------------------------------------------------------------------
Le champ courant du natif est ENTRETENU : `IdunBattle.Operations.UpdateUnitMembersOperation$$Execute`
pose `NumberOfMembersComponent+0x18 = IBattleQuery.<slot 184 GetGroupUnitRemainingMemberCount>(unit,
null)` -- et `IdunBattle.Operations.ApplyDamageOperation$$UpdateNumberOfMembersStat` l'appelle apres
chaque degat, en rendant `avant - apres` = les membres morts. Donc des qu'un membre meurt, le natif
SEPARE Current (restants) et Maximum (nrOfMembers), sans qu'aucun stat-mod n'existe.

⚠ AU DEPLOIEMENT LES DEUX COINCIDENT. Un accord avant la premiere mort de membre ne prouve RIEN
(regime degenere). Le probe compte donc les observations ou `Current != Maximum` cote NATIF et
REFUSE de rendre un verdict sur un corpus qui n'en porte aucune.

LE MONTAGE
----------
Meme que `probe_477r15r5_membres_discrimine.py` : les deux seuls summoners de summons
multi-membres qui sont AU POOL. Un de chaque cote, l'IA joue les deux camps.

    necroSpyder   (Aleph-Null) --ScarabHive--> necroSmnSwarm       (5 membres)
    tyranParasite (Parasite)   --ItItches----> tyranSmnRipperSwarm (5 membres)

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-file sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
OUT = ROOT / "logs"
HOST = "http://127.0.0.1:8765"

from engine.entities.stats import StatPart, StatType, seed_unit_stats  # noqa: E402

P_UNITS_DEFAUT = "necroSpyder,ultraInceptorSgt"
A_UNITS_DEFAUT = "tyranParasite,blackTerminator"
BOARD_DEFAUT = "MC1_67"
SEED = 777

#: Les deux grandeurs fill-up du residu. `source_cur` dit D'OU vient la lecture Current :
#: `stats` = `combatSnapshot.stats[<cle>]`, `observe` = `observeBattle[<cle>]` (cf. docstring).
GRANDEURS = (
    ("membres", int(StatType.NUMBER_OF_MEMBERS), "stats", "numberOfMembers", "numberOfMembersMax"),
    ("armure", int(StatType.ARMOR), "observe", "armor", "armorMax"),
)


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


def rpc(session: int, method: str, args: dict, timeout: int = 180) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 150000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def session_courante() -> int:
    try:
        with urllib.request.urlopen("%s/api/admin/status" % HOST, timeout=10) as r:
            st = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("host injoignable : %s" % e) from e
    sid = ((st.get("session") or {}).get("id"))
    if sid is None:
        raise MesureImpossible("aucune session Frida vivante")
    return int(sid)


def build(board: str, state_file: Path, p_units: str, a_units: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--board", board,
           "--p-units", p_units, "--a-units", a_units,
           "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not state_file.is_file():
        raise MesureImpossible("build %s echoue : %s" % (board, (p.stderr or p.stdout)[-600:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def dispose(state_file: Path) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_file)],
                   cwd=str(HERE), capture_output=True, text=True, timeout=180)


def lire(session: int, rid: int) -> tuple:
    """`(statTypes, [unite], {squadId: ligne observeBattle})`. Leve si un capteur manque -- jamais
    de repli : rabattre `armorMax` sur la lecture brute fabriquerait l'alias qu'on doit refuter."""
    cs = rpc(session, "combatSnapshot", {"runnerId": rid})
    unites = cs.get("units")
    if unites is None:
        raise MesureImpossible("combatSnapshot ne rend aucune unite")
    stat_ids = cs.get("statTypes")
    if not stat_ids:
        raise MesureImpossible("combatSnapshot ne publie pas `statTypes`")
    for u in unites:
        for _, _, _, _, cle_max in GRANDEURS:
            if cle_max not in u:
                raise MesureImpossible(
                    "combatSnapshot ne publie pas `%s` -- capteur absent du bundle charge" % cle_max)
        break
    obs = rpc(session, "observeBattle", {"runnerId": rid})
    par_obs = {int(o["squadId"]): o for o in (obs.get("units") or [])
               if o.get("squadId") is not None}
    if not par_obs:
        raise MesureImpossible("observeBattle ne rend aucune unite avec un `squadId`")
    return stat_ids, unites, par_obs


def parts_du_port(u: dict, stat_ids: dict, idx: int) -> dict:
    """Les trois parts que le PORT rend pour `idx`, sur un `UnitStats` re-seede depuis CE snapshot.

    C'est exactement ce que fait `UnitContext.from_snapshot` (meme appel, memes arguments) : on
    mesure donc le reservoir REEL du port, pas une reconstruction de circonstance."""
    us = seed_unit_stats(u.get("stats") or {}, u.get("statDelta"), stat_ids)
    return {"current": us.get_stat(idx, StatPart.CURRENT),
            "maximum": us.get_stat(idx, StatPart.MAXIMUM),
            "initial": us.get_stat(idx, StatPart.INITIAL)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--board", default=BOARD_DEFAUT)
    ap.add_argument("--p-units", default=P_UNITS_DEFAUT)
    ap.add_argument("--a-units", default=A_UNITS_DEFAUT)
    ap.add_argument("--tours", type=int, default=14)
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else session_courante()
    except MesureImpossible as e:
        print("[572-r3] MESURE IMPOSSIBLE : %s" % e)
        return 2

    print("[572-r3] session=%d board=%s p=%s a=%s tours=%d"
          % (session, args.board, args.p_units, args.a_units, args.tours))
    state = OUT / "state-572r3-membres-armure.json"
    state.parent.mkdir(parents=True, exist_ok=True)

    #: TEMOINS -- un « 0 ecart » sans eux se lirait comme un accord alors qu'il peut vouloir dire
    #: « le regime n'a jamais ete atteint ».
    vues = {nom: set() for nom, _, _, _, _ in GRANDEURS}
    non_nulles = {nom: set() for nom, _, _, _, _ in GRANDEURS}
    #: observations ou le NATIF separe Current et Maximum = le SEUL regime qui teste quoi que ce soit
    separees = {nom: [] for nom, _, _, _, _ in GRANDEURS}
    ecarts = {nom: [] for nom, _, _, _, _ in GRANDEURS}
    #: CONTROLE DU MIRROR : dans un regime SANS modification ni override, le natif a
    #: `get_CurrentMaximumValue() == +0x14 == +0x10`, donc `Maximum == Initial`. Le port
    #: reconstruit `Initial = Current - statDelta` (seule voie : `seed_unit_stats` ne recoit
    #: AUCUN maximum). Compter les cas ou les deux DIVERGENT dit si cette reconstruction suffit :
    #: 0 => elle est exacte sur ce corpus ; >0 => une modification `+0x28` existe et le port ne
    #: peut PAS la reconstruire (il lui faudrait le canal `numberOfMembersMax`).
    initial_vs_max = {nom: [] for nom, _, _, _, _ in GRANDEURS}
    tours_joues = 0

    def absorber(pas: int) -> None:
        stat_ids, unites, par_obs = lire(session, rid)
        for u in unites:
            eid = u.get("entityId")
            st = u.get("stats") or {}
            o = par_obs.get(int(eid)) if eid is not None else None
            for nom, idx, source_cur, cle_cur, cle_max in GRANDEURS:
                src = st if source_cur == "stats" else (o or {})
                cur_n, max_n = src.get(cle_cur), u.get(cle_max)
                if cur_n is None or max_n is None:
                    continue                       # PAS MESURE sur cette entite (tri-etat)
                cur_n, max_n = int(cur_n), int(max_n)
                vues[nom].add(eid)
                if cur_n or max_n:
                    non_nulles[nom].add(eid)
                p = parts_du_port(u, stat_ids, idx)
                if cur_n != max_n:
                    separees[nom].append({"tour": pas, "entityId": eid,
                                          "current": cur_n, "maximum": max_n})
                for part, attendu in (("current", cur_n), ("maximum", max_n)):
                    if p[part] != attendu:
                        ecarts[nom].append({"tour": pas, "entityId": eid, "part": part,
                                            "natif": attendu, "port": p[part],
                                            "visualId": (o or {}).get("visualId")})
                if p["initial"] != max_n:
                    initial_vs_max[nom].append({"tour": pas, "entityId": eid,
                                                "initial_port": p["initial"], "maximum_natif": max_n})

    try:
        rid = build(args.board, state, args.p_units, args.a_units)
        print("  runner %d monte" % rid)
        for pas in range(args.tours):
            absorber(pas)
            r = rpc(session, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1})
            tours_joues += 1
            if r.get("ok") is False:
                print("  arret au tour %d : %s" % (pas, r.get("error")))
                break
            if r.get("finished") or r.get("winner") is not None:
                print("  bataille terminee au tour %d (winner=%s)" % (pas, r.get("winner")))
                break
        absorber(tours_joues)
    except MesureImpossible as e:
        print("[572-r3] MESURE IMPOSSIBLE : %s" % e)
        dispose(state)
        return 2
    finally:
        dispose(state)

    print("")
    print("=== TEMOINS (sans eux, un zero ne veut rien dire) ===")
    print("  tours d'equipe joues : %d" % tours_joues)
    for nom, _, _, _, _ in GRANDEURS:
        print("  %-8s entites vues %-3d  dont valeur NON NULLE %-3d  observations ou le NATIF "
              "SEPARE Current/Maximum : %d"
              % (nom, len(vues[nom]), len(non_nulles[nom]), len(separees[nom])))
        div = initial_vs_max[nom]
        print("           `Initial` reconstruit (Current - statDelta) != `Maximum` natif : %d"
              " -- 0 == la reconstruction suffit (aucune modification `+0x28` sur ce corpus)"
              % len(div))
        for e in div[:4]:
            print("             tour %-3d entite %-5s initial_port=%d maximum_natif=%d"
                  % (e["tour"], e["entityId"], e["initial_port"], e["maximum_natif"]))

    print("")
    print("=== VERDICT PAR GRANDEUR ===")
    rc = 0
    for nom, _, _, _, _ in GRANDEURS:
        if not non_nulles[nom]:
            print("  %-8s REGIME VIDE : la grandeur vaut ZERO sur les %d entite(s) vues en %d "
                  "tour(s). Rien a discriminer -- ce corpus ne teste AUCUN reservoir."
                  % (nom.upper(), len(vues[nom]), tours_joues))
            rc = max(rc, 3)
            continue
        if not separees[nom]:
            print("  %-8s REGIME DEGENERE : %d entite(s) non nulles, mais le natif n'a JAMAIS "
                  "separe Current et Maximum en %d tour(s). Un accord ici ne prouve rien."
                  % (nom.upper(), len(non_nulles[nom]), tours_joues))
            rc = max(rc, 3)
            continue
        if ecarts[nom]:
            print("  %-8s PORT DIVERGENT : %d ecart(s) sur %d observation(s) discriminantes."
                  % (nom.upper(), len(ecarts[nom]), len(separees[nom])))
            for e in ecarts[nom][:8]:
                print("      tour %-3d entite %-5s %-8s natif=%-5d port=%-5d  (%s)"
                      % (e["tour"], e["entityId"], e["part"], e["natif"], e["port"],
                         e["visualId"]))
            rc = max(rc, 1)
        else:
            print("  %-8s ACCORD sur %d observation(s) DISCRIMINANTES (natif Current != Maximum)."
                  % (nom.upper(), len(separees[nom])))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
