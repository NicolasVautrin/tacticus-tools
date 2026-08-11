"""Probe #915 -- confront LIVE du passif de kit `PropheticSentinel` (`thousSekhetar`).

CE QUE CE PROBE MESURE, et pourquoi il est construit ainsi
---------------------------------------------------------
Le `CreateBehaviour` natif s'appelle `AddStaticStatModifierEffect**ToOwner**`, ce qui se lit comme
un SELF-BUFF. Il ne l'est pas : les trois entites-effet vivent bien sur le porteur (elles sont dans
son `decisionView.effects`) mais leur MODIFICATION DE STAT est PROJETEE sur les unites de leur
`CreateTargetSelector` -- et les DEUX selecteurs du kit ne portent PAS le meme trait. Le premier
port de cette tranche s'est fait prendre : il declarait `get_stat_modification_stat/amount`
(self-buff), et RIEN dans l'arbre offline n'aurait rougi.

Le regime est DISCRIMINANT par construction : QUATRE voisins, TOUS adjacents au porteur, couvrant
les quatre combinaisons du couple (Psyker, Chaos). Chaque colonne a un temoin positif ET un temoin
negatif -- un accord en regime degenere (0 voisin qualifiant, magnitude nulle) ne prouverait rien.

    voisin                traits                       attendu
    thousAhriman          Psyker + Chaos               fixedArmor + blockChance + blockDamage
    deathBlightbringer    Chaos, NON-Psyker            fixedArmor SEUL
    astraPrimarisPsy      Psyker, Imperial             blockChance + blockDamage SEULS
    adeptCanoness         ni Psyker ni Chaos           RIEN
    thousSekhetar         LE PORTEUR                   RIEN (`AdjacentFriends` retire sa tuile)

ETAGES
------
  1. VENTILATION NATIVE (`statModSources`) : la table ci-dessus, cote jeu.
  2. VENTILATION PORTEE : le MEME etat charge par `snapshot.load_state`, meme table.
  3. CONFRONTATION 1 vs 2, unite par unite ET stat par stat.
  4. GEOMETRIE : le voisin Psyker+Chaos est ELOIGNE ; sa contribution doit tomber a 0 des DEUX
     cotes (l'aura est re-evaluee au mouvement, elle n'est pas figee au seed).
  5. MUTANTS : trois mutations du port (trait echange, stat echangee, magnitude non scalee) DOIVENT
     faire rougir l'etage 3. Un mutant VERT dit que le temoin est aveugle.

Usage :
    python probe_915_prophetic_sentinel.py [--state-file <absolu>] [--seed 915] [--no-build]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _rpc, _resolve_session          # noqa: E402

# SORTIES du probe -> `logs/` (gitignore, meurt avec le worktree). `data/` est VERSIONNE et ne porte
# que des ENTREES (#349).
LOGS = PYDIR.parent.parent / "logs" / "runners"
SEED_BC = LOGS / "_915_prophetic_sentinel_bc.json"
BOARD = "MC1_67"

CARRIER = "thousSekhetar"
#: Les QUATRE regimes du couple (Psyker, Chaos), et la position FORCEE qui les rend tous adjacents
#: au porteur pose en (2,2) -- un hex a SIX voisins sur ce board (les spawns par defaut sont dans un
#: coin a TROIS voisins : la geometrie se PILOTE, elle ne se subit pas).
NEIGHBOURS = [
    # (unitId,             col, row, psyker, chaos)
    ("thousAhriman",        2, 1, True,  True),    # Psyker + Chaos
    ("deathBlightbringer",  1, 2, False, True),    # Chaos seul
    ("astraPrimarisPsy",    3, 2, True,  False),   # Psyker seul (Imperial)
    ("adeptCanoness",       2, 3, False, False),   # ni l'un ni l'autre
]
CARRIER_POS = (2, 2)
FOES = ["astraCreed", "adeptRetributor", "adeptHospitaller"]

#: `statModSources.statTypes` -> le nom de champ que le RPC publie, et le `StatType` du port.
STATS = (("fixedArmor", 16), ("blockChance", 7), ("blockDamage", 8))
#: L'attendu DERIVE du decompile + de la mesure : quel trait ouvre quelle stat.
STAT_TRAIT = {"fixedArmor": "chaos", "blockChance": "psyker", "blockDamage": "psyker"}


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=90):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def ensure_seed_bc():
    """`thousSekhetar` est HORS du seed BC capture -> injection catalogue (#92 §6). Sans elle,
    `--p-units thousSekhetar` repond << hors pool >> et la tranche serait declaree, a tort, non
    confrontable."""
    if SEED_BC.exists():
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "catalog_inject.py", "--units", CARRIER,
                    "--out", str(SEED_BC)], cwd=str(PYDIR), check=True)


def build(state_file: Path, seed: str, places: list) -> int:
    ensure_seed_bc()
    p_units = ",".join([CARRIER] + [n[0] for n in NEIGHBOURS])
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--seed-bc", str(SEED_BC), "--p-units", p_units, "--a-units", ",".join(FOES),
           "--state-file", str(state_file), "--no-ai"]
    for uid, col, row in places:
        cmd += ["--place", "%s:%d,%d" % (uid, col, row)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1600:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------- etage 1 : le NATIF


def natif_ventilation(sid, rid) -> tuple:
    """`(par_unite, visual_by_id)` -- `{visualId: {stat: total}}` LU dans `statModSources`.

    Seules les trois stats du kit sont retenues, et seule la contribution d'une source NON-UNITE
    (une entite-effet) compte : c'est ce que `AStatModifierEffect$$ApplyModification` ecrit."""
    dv = rpc(sid, "decisionView", {"runnerId": rid})
    vis = {u["id"]: u.get("visualId") for u in (dv.get("units") or [])}
    sm = rpc(sid, "statModSources", {"runnerId": rid}, 90)
    out: dict = {}
    for uu in (sm.get("units") or []):
        eid = uu.get("entityId")
        name = vis.get(eid)
        if name is None:
            continue
        mods = uu.get("mods") or {}
        row = {}
        for champ, _st in STATS:
            m = mods.get(champ) or {}
            tot = m.get("total")
            row[champ] = int(tot) if tot else 0
        out[name] = row
    for name in vis.values():
        out.setdefault(name, {c: 0 for c, _ in STATS})
    return out, vis


# --------------------------------------------------------------- etage 2 : le PORT


def port_ventilation(sid, rid) -> dict:
    """Meme table, cote PORT : l'etat live est charge par `snapshot.load_state` (qui appelle
    `attribute_aura_stat_modifiers`), puis on relit la contribution ATTRIBUEE a chaque effet-aura.

    On lit la contribution PAR SOURCE (`per_source` des `UnitStats` portes), pas le total : le total
    porte aussi le residu opaque de la capture, qui n'est pas ce que ce port produit."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    from engine.runner.operations.aura_stat_mods import aura_stat_mod_key

    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc(sid, "decisionView", {"runnerId": rid})
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    vis = {u["id"]: u.get("visualId") for u in (dv.get("units") or [])}

    # les cles des trois effets-aura du porteur (une par entite-effet)
    keys: dict = {}
    for owner_id, effs in (state.effects.by_unit or {}).items():
        for e in (effs or []):
            if not str(getattr(e, "name", "") or "").startswith("PropheticSentinel_"):
                continue
            fn = getattr(e, "aura_stat_modification_stat", None)
            if fn is None:
                continue
            keys[aura_stat_mod_key(owner_id, e)] = int(fn())

    out: dict = {}
    for uid, name in vis.items():
        row = {c: 0 for c, _ in STATS}
        ent = state.get_entity(int(uid))
        sc = ent.get_component(StatsComponent) if ent is not None else None
        stats = getattr(sc.ctx, "stats", None) if sc is not None else None
        if stats is not None:
            for key, stat in keys.items():
                amt = _per_source_amount(stats, stat, key)
                if not amt:
                    continue
                for champ, st in STATS:
                    if int(st) == int(stat):
                        row[champ] += int(amt)
        out[name] = row
    return out


def _per_source_amount(stats, stat: int, key) -> int:
    """La contribution de `key` a `stat` dans les `UnitStats` portes.

    Chemin LU dans `aura_stat_mods.attribute_aura_stat_modifiers` lui-meme :
    `UnitStats.components[stat].modification.per_source[key]` -- le meme conteneur que celui ou
    l'attribution ECRIT. Degrade a 0 si un maillon manque : un TROU ne doit pas lever, il doit se
    voir comme un desaccord a l'etage 3."""
    comps = getattr(stats, "components", None)
    comp = comps.get(int(stat)) if hasattr(comps, "get") else None
    mod = getattr(comp, "modification", None) if comp is not None else None
    ps = getattr(mod, "per_source", None) if mod is not None else None
    if not ps:
        return 0
    return int((ps.get(key) if hasattr(ps, "get") else 0) or 0)


# --------------------------------------------------------------- etage 3 : la CONFRONTATION


def attendu_theorique() -> dict:
    """La table ATTENDUE, DERIVEE du couple (trait du selecteur, trait du voisin) -- jamais recopiee
    d'une mesure. `None` = << non nul >> (la magnitude exacte est confrontee au natif, pas devinee
    ici : elle depend du niveau et du multiplier du porteur)."""
    out = {CARRIER: {c: 0 for c, _ in STATS}}
    for uid, _c, _r, psyker, chaos in NEIGHBOURS:
        row = {}
        for champ, _st in STATS:
            veut = psyker if STAT_TRAIT[champ] == "psyker" else chaos
            row[champ] = None if veut else 0
        out[uid] = row
    return out


def confronter(nat: dict, port: dict, attendu: dict, titre: str) -> list:
    ecarts = []
    print("\n=== %s ===" % titre)
    print("  %-22s %-28s %-28s" % ("unite", "NATIF (fA/bC/bD)", "PORT (fA/bC/bD)"))
    for uid in [CARRIER] + [n[0] for n in NEIGHBOURS]:
        n = nat.get(uid) or {c: 0 for c, _ in STATS}
        p = port.get(uid) or {c: 0 for c, _ in STATS}
        a = attendu.get(uid) or {}
        sn = "/".join(str(n.get(c, 0)) for c, _ in STATS)
        sp = "/".join(str(p.get(c, 0)) for c, _ in STATS)
        print("  %-22s %-28s %-28s" % (uid, sn, sp))
        for champ, _st in STATS:
            vn, vp, va = int(n.get(champ, 0)), int(p.get(champ, 0)), a.get(champ, None)
            if va == 0 and vn != 0:
                ecarts.append("%s/%s : le NATIF donne %d la ou la RE attend 0" % (uid, champ, vn))
            if va is None and vn == 0:
                ecarts.append("%s/%s : le NATIF donne 0 la ou la RE attend un bonus "
                              "(regime DEGENERE : rien a confronter)" % (uid, champ))
            if vn != vp:
                ecarts.append("%s/%s : natif=%d port=%d" % (uid, champ, vn, vp))
    return ecarts


def _non_degenere(nat: dict) -> list:
    """Le temoin doit etre NON DEGENERE : au moins un positif ET au moins un zero par stat, sinon
    l'accord ne discrimine RIEN. Un probe qui ne verifie pas son propre non-vide est un faux vert."""
    manques = []
    for champ, _st in STATS:
        vals = [int((nat.get(u[0]) or {}).get(champ, 0)) for u in NEIGHBOURS]
        if not any(v > 0 for v in vals):
            manques.append("stat %s : AUCUN temoin positif" % champ)
        if not any(v == 0 for v in vals):
            manques.append("stat %s : AUCUN temoin nul" % champ)
    return manques


#: ETAGE 5 -- les MUTATIONS du port qui DOIVENT faire rougir l'etage 3. Un mutant VERT dit que le
#: temoin est aveugle sur cet axe, et c'est un resultat qu'on NOMME, jamais qu'on tait.
#: `(libelle, classe, attribut, valeur)`.
def _mutants():
    from engine.entities.effects.loki import prophetic_sentinel as PS
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.stats import StatType
    return [
        ("TRAIT du selecteur ExtraArmor : Chaos -> Psyker",
         PS.PropheticSentinelExtraArmorEffect, "_TRAIT", UnitTrait.Psyker),
        ("TRAIT du selecteur ExtraBlockDamage : Psyker -> Chaos",
         PS.PropheticSentinelExtraBlockDamageEffect, "_TRAIT", UnitTrait.Chaos),
        ("STAT d'ExtraBlockChance : BlockChance -> BlockDamage",
         PS.PropheticSentinelExtraBlockChanceEffect, "_STAT", StatType.BLOCK_DAMAGE),
        ("VARIABLE d'ExtraBlockChance : blockChance -> blockDmg (l'inversion 0x15/0x14)",
         PS.PropheticSentinelExtraBlockChanceEffect, "_VAR", "blockDmg"),
    ]


def jouer_mutants(sid, rid, nat) -> list:
    """Chaque mutation est posee, l'etage 3 rejoue, puis la mutation est RETIREE. Un mutant qui
    laisse l'etage VERT est un trou du temoin : on le nomme avec sa cause."""
    verts = []
    print("\n=== ETAGE 5 : MUTANTS ===")
    for libelle, cls, attr, val in _mutants():
        avant = getattr(cls, attr)
        setattr(cls, attr, val)
        try:
            port = port_ventilation(sid, rid)
            ecarts = confronter(nat, port, attendu_theorique(), "mutant : %s" % libelle)
        finally:
            setattr(cls, attr, avant)
        if ecarts:
            print("  MUTANT ROUGE (attendu) : %s -- %d ecart(s)" % (libelle, len(ecarts)))
        else:
            print("  MUTANT VERT (TROU DU TEMOIN) : %s" % libelle)
            verts.append(libelle)
    return verts


def deplacer(sid, rid, unit_visual: str, col: int, row: int) -> bool:
    """Deplace une unite LIVE (on PILOTE la geometrie, on ne la subit pas). Rend False si le
    deplacement n'a pas eu lieu -- l'appelant doit alors ecrire NON CONFRONTE, jamais conclure."""
    dv = rpc(sid, "decisionView", {"runnerId": rid})
    uid = next((u["id"] for u in (dv.get("units") or []) if u.get("visualId") == unit_visual), None)
    if uid is None:
        return False
    # `kind`, pas `type` : c'est le champ que `rl_duel.cmd_act` construit et que le host valide.
    r = rpc(sid, "applyAction", {"runnerId": rid,
                                 "action": {"kind": "move", "unitId": int(uid),
                                            "to": {"col": int(col), "row": int(row)}}}, 90)
    dv2 = rpc(sid, "decisionView", {"runnerId": rid})
    pos = next((u.get("pos") for u in (dv2.get("units") or [])
                if u.get("visualId") == unit_visual), None)
    ok = bool(pos and int(pos.get("col")) == int(col) and int(pos.get("row")) == int(row))
    if not ok:
        print("      (move refuse : %s)" % json.dumps(r)[:200])
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(LOGS / "_915_ps.json"))
    ap.add_argument("--seed", default="915")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--no-geometrie", action="store_true")
    args = ap.parse_args()

    sf = Path(args.state_file)
    sf.parent.mkdir(parents=True, exist_ok=True)
    places = [(CARRIER, CARRIER_POS[0], CARRIER_POS[1])] + [(u, c, r) for u, c, r, _p, _x in NEIGHBOURS]
    rid = (int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"]) if args.no_build
           else build(sf, args.seed, places))
    sid = _resolve_session()
    print("[915] runner=%s session=%s board=%s" % (rid, sid, BOARD))

    nat = natif_ventilation(sid, rid)[0]
    port = port_ventilation(sid, rid)
    manques = _non_degenere(nat)
    if manques:
        print("[915] TEMOIN DEGENERE :")
        for m in manques:
            print("      %s" % m)
        return 3
    ecarts = confronter(nat, port, attendu_theorique(), "ETAGE 1-3 : ventilation adjacente")
    if ecarts:
        print("[915] ROUGE (%d ecart(s)) :" % len(ecarts))
        for e in ecarts:
            print("      %s" % e)
        return 1
    print("[915] etage 1-3 VERT : les quatre regimes concordent natif <-> port.")

    trous = [] if args.no_mutants else jouer_mutants(sid, rid, nat)

    # ETAGE 4 -- GEOMETRIE. Le voisin Psyker+Chaos s'ELOIGNE : ses trois contributions doivent
    # tomber a 0 des DEUX cotes. C'est le seul etage qui teste le SELECTEUR plutot que le mapping.
    if not args.no_geometrie:
        print("\n=== ETAGE 4 : GEOMETRIE (le voisin Psyker+Chaos s'eloigne) ===")
        if not deplacer(sid, rid, "thousAhriman", 4, 0):
            print("  NON CONFRONTE -- le deplacement n'a pas eu lieu (aucune conclusion tiree).")
        else:
            nat2 = natif_ventilation(sid, rid)[0]
            port2 = port_ventilation(sid, rid)
            att2 = attendu_theorique()
            att2["thousAhriman"] = {c: 0 for c, _ in STATS}       # hors adjacence -> plus rien
            e2 = confronter(nat2, port2, att2, "apres eloignement")
            if e2:
                print("[915] ROUGE (geometrie, %d ecart(s)) :" % len(e2))
                for e in e2:
                    print("      %s" % e)
                return 1
            reste = sum(int((nat2.get("thousAhriman") or {}).get(c, 0)) for c, _ in STATS)
            if reste:
                print("[915] ROUGE : le natif garde %d apres eloignement -- l'aura ne serait pas "
                      "geometrique, toute la RE est a reprendre." % reste)
                return 1
            print("  OK : les trois contributions tombent a 0 des deux cotes.")

    if trous:
        print("[915] %d MUTANT(S) VERT(S) -- le temoin est aveugle sur ces axes :" % len(trous))
        for t in trous:
            print("      %s" % t)
        return 2
    print("[915] VERT (tous etages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
