"""#419-r1-tr14-r5-r2-r1-r1-r1-r2-r4 -- POURQUOI le natif ne bascule qu'entre `u = 5` et `u = 20`.

#592 a mesure, par dichotomie et sur UN seul montage, que le natif refuse `1150 PlasmaCannon`
jusqu'a `u_port = 10` et l'accepte a partir de `u_port = 15`, alors que le seuil LU au `.cctor` de
`IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook` vaut `Fix64(1)`. Elle a laisse DEUX causes non
separees :

  1. une divergence de PREDICTION/UTILITE -- le natif calculerait un `u` PLUS PETIT que le port,
     si bien que SON `ShouldExecute` mordrait la ou on ne l'attend pas ;
  2. un FILTRE au-dessus du playbook, qui rejetterait l'action APRES que `ShouldExecute` l'a
     acceptee.

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

Les deux causes predisent le MEME resultat sur le canal de #592 (`aiDryRunAllUnits` : refus en bas,
acceptation en haut). Il faut donc un canal qui les SEPARE, et il y en a deux, independants.

### Etape 1 -- OFFLINE : LIRE le predicat (la piste 2 se tranche au decompile)

`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` appelle,
AVANT toute insertion, le corps designe par `<klass.rgctx>+0x40` ; `...$$ChooseAction` appelle le
MEME. Ce corps est `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$IsValidAction`,
lu verbatim :

    IsValidAction(this, action):
        if (action == null) return false;
        if (!this.<Nullable @+0x10>.HasValue) return true;      // Nullable<TUtility>.get_HasValue
        return Fix64.op_GreaterThanOrEqual(action.Utility, this.<Nullable @+0x10>.Value);

Le predicat ne peut donc refuser une action QUE si le bucket porte un seuil. Or les DEUX buckets du
chemin `ActiveAbilityActionGenerator` sont inertes, et c'est LU, pas suppose :

  * le bucket RACINE (`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`)
    est construit par la surcharge `Bucket..ctor(this)` -- celle a DEUX arguments, qui n'ecrit ni
    `+0x10` ni `+0x18`. `static_fields`/champs d'objet sont alloues zero-initialises, donc
    `HasValue == false` : `IsValidAction` rend `true` pour toute action NON NULLE ;
  * le bucket du PLAYBOOK (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`)
    ecrit `+0x10` avec `Nullable<Fix64>(FixMath.NET.Fix64$$op_Implicit(0x80000000))`. Et
    `FixMath.NET.Fix64$$op_Implicit` vaut `(long)(int)value << 32`, donc
    `op_Implicit(0x80000000) = (-2147483648L) << 32 = long.MinValue = Fix64.MinValue`. Le seuil est
    `-inf` : `action.Utility >= Fix64.MinValue` est TOUJOURS vrai.

`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$Merge` n'ajoute rien --
il rappelle `AddAction` sur le bucket CIBLE (racine, donc sans seuil).

L'etape 1 de ce probe RE-DERIVE ces quatre corps depuis `data/symbols/<build>/ghidra/functions.tsv`
(le dump GHIDRA -- ils sont `__Il2CppFullySharedGeneric`, donc structurellement ABSENTS du dump
FRIDA, cf. `docs/rl/case-259-couverture-gshared.md`), et elle CONFRONTE les RVA que le seul capteur
live existant (`frida/hooks/features/bucket-audit.ts`) porte EN DUR : elles datent du build
`gqfc5mff6c`. C'est pourquoi la piste 2 devait etre tranchee au decompile, et non armee live.

### Etape 2 -- LIVE : mesurer l'utilite NATIVE, sur le montage de #592

`pairUtility` invoque
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
sur le playbook NATIF de l'ability, depuis la tuile courante : c'est EXACTEMENT le second terme de
l'argument que `CalculateActionUtility` passe a `ShouldExecute` (le premier,
`CalculateCustomUtility`, vaut 0 pour la base). Les deux causes predisent alors des resultats
OPPOSES sur les MEMES trois bras :

  * cause 1 (divergence d'utilite) -> `u_natif` est nettement PLUS PETIT que `u_port`, et le rapport
    est tel que `u_natif <= 1` dans les bras ou le natif refuse, `> 1` dans celui ou il accepte ;
  * cause 2 (filtre au-dessus)     -> `u_natif == u_port` (a l'arrondi Fix64 pres), donc le natif
    voit `u = 5 > 1` dans le bras `mid` et refuse QUAND MEME : le refus est ailleurs.

### Etape 3 -- LIVE : par ETAGE, si (et seulement si) l'etape 2 designe la cause 1

`aiPlaybookPredict` invoque `<Ability>Playbook.MakeDamagePredictions` NATIF et rend sa liste de
`ProbableDamageEvent`. Confrontee a celle du port, elle separe « la prediction de degat est fausse »
de « le barème/agregation est faux ». Le candidat NOMME est
`IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`, qui appelle
`GenerateMultiHitAttackPredictions` DEUX fois (batch principal sur le selecteur de l'ability, puis
batch SECONDAIRE pondere par `Fix64.FromIntFraction(maxSecondary, actualCount)`).

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif.py
    python scripts/python/probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif.py --live \\
        --state-file <ABSOLU>

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_419r1tr14r5r2r1r1r1r2_static_threshold_gate as P

_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

#: Les QUATRE corps gshared du BucketSystem, tels qu'ils s'ecrivent dans `ghidra/functions.tsv`.
#: L'echappement `u003C`/`u003E` est conserve VERBATIM -- c'est ce qui rend le grep code <-> table
#: immediat (cf. CLAUDE.md, « on cite un SYMBOLE, jamais une adresse »).
BUCKET_BODIES = (
    "IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction",
    "IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddActionToBucket",
    "IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$ChooseAction",
    "IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$IsValidAction",
)

#: Nom du champ du hook `bucket-audit.ts` -> symbole gshared correspondant.
AUDIT_RVA_FIELDS = {
    "addAction": BUCKET_BODIES[0],
    "addActionToBucket": BUCKET_BODIES[1],
    "chooseAction": BUCKET_BODIES[2],
    "isValidAction": BUCKET_BODIES[3],
}

IL2CPP_IMAGE_BASE = 0x180000000


# --------------------------------------------------------------------------- etape 1 : OFFLINE

def _symbol_table(build: str, which: str) -> dict:
    """`data/symbols/<build>/<which>/functions.tsv|methods.tsv` -> {symbole: adresse-ou-None}."""
    if which == "ghidra":
        path = os.path.join(_ROOT, "data", "symbols", build, "ghidra", "functions.tsv")
        out = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 2:
                    continue
                out.setdefault(cols[1], int(cols[0], 16))
        return out
    path = os.path.join(_ROOT, "data", "symbols", build, "frida", "methods.tsv")
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 2:
                continue
            out.setdefault(cols[1], None)
    return out


def _audit_hook_rvas() -> dict:
    """RVA ecrites EN DUR dans `frida/hooks/features/bucket-audit.ts` (le seul capteur live de cet
    ancrage). Le module les documente lui-meme comme build-specifiques."""
    path = os.path.join(_ROOT, "frida", "hooks", "features", "bucket-audit.ts")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    out = {}
    for name in AUDIT_RVA_FIELDS:
        m = re.search(r"\b%s:\s*(0x[0-9a-fA-F]+)" % name, src)
        if m:
            out[name] = int(m.group(1), 16)
    return out


def etape1_predicat_offline(verbose: bool = True) -> dict:
    """Les quatre corps existent-ils dans le dump GHIDRA (et sont-ils absents du dump FRIDA) ?

    C'est la mesure qui autorise a LIRE le predicat au decompile : un corps
    `__Il2CppFullySharedGeneric` n'a PAS de `methodPointer` propre cote Frida (le pointeur d'une
    definition generique est un thunk), donc son absence de `methods.tsv` ne prouve rien -- et sa
    presence dans `functions.tsv` est la seule voie de lecture."""
    build = P._build_hash()
    gh = _symbol_table(build, "ghidra")
    fr = _symbol_table(build, "frida")
    bad = 0
    if verbose:
        print("[etape 1] BucketSystem -- corps gshared, dump ghidra build=%s" % build)
    rows = []
    for sym in BUCKET_BODIES:
        va = gh.get(sym)
        in_frida = sym in fr
        ok = (va is not None) and (not in_frida)
        if not ok:
            bad += 1
        rows.append({"symbol": sym, "va": va, "inFrida": in_frida})
        if verbose:
            short = sym.split("$$")[-1]
            print("  %s %-20s ghidra=%-12s frida=%s"
                  % ("OK " if ok else "BAD", short,
                     "absent" if va is None else ("rva 0x%x" % (va - IL2CPP_IMAGE_BASE)), in_frida))
    # Le capteur live existant est FIGE sur un autre build -- c'est la raison pour laquelle la
    # piste 2 devait etre tranchee au decompile. On le MESURE au lieu de l'affirmer.
    stale = []
    hook = _audit_hook_rvas()
    for field, sym in AUDIT_RVA_FIELDS.items():
        va = gh.get(sym)
        want = None if va is None else va - IL2CPP_IMAGE_BASE
        got = hook.get(field)
        if got is not None and want is not None and got != want:
            stale.append({"field": field, "hook": got, "build": want})
    if verbose:
        if stale:
            print("  NOTE `frida/hooks/features/bucket-audit.ts` porte %d/%d RVA d'un AUTRE build"
                  % (len(stale), len(AUDIT_RVA_FIELDS)))
            for s in stale:
                print("       %-18s hook=0x%-9x build courant=0x%x"
                      % (s["field"], s["hook"], s["build"]))
            print("       -> ce capteur ne peut PAS etre arme sur ce build (il attacherait sur du"
                  " code arbitraire). Le predicat a donc ete lu au DECOMPILE.")
        else:
            print("  NOTE `bucket-audit.ts` : RVA a jour pour ce build.")
    return {"bad": bad, "build": build, "rows": rows, "staleAuditRvas": stale}


# --------------------------------------------------------------------------- etape 2/3 : LIVE

def _native_pair_utility(rid: int, uid: int, tid: int, ability: int):
    r = P.rpc("pairUtility", {"runnerId": rid, "unitId": uid, "targetId": tid,
                              "abilityType": ability}, 120) or {}
    if not r.get("ok"):
        return None, r
    return r.get("utility"), r


def _native_events(rid: int, uid: int, tid: int, ability: int) -> list:
    r = P.rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": uid, "targetId": tid,
                                    "abilityType": ability}, 120) or {}
    if not r.get("ok"):
        return [{"error": r.get("error") or json.dumps(r)[:200]}]
    out = []
    for e in (r.get("events") or ()):
        out.append({"target": e.get("target") if "target" in e else e.get("targetId"),
                    "hMin": e.get("healthDmgMin"), "hMax": e.get("healthDmgMax"),
                    "hits": e.get("appliedHits"), "prob": e.get("probability")})
    return out


def _port_events(ctx, ability: int, target: int) -> list:
    from engine.playbook import get_playbook_or_default
    pb = get_playbook_or_default(ability)
    evs = pb.make_damage_predictions(ctx, ctx.origin, target, ability) or []
    out = []
    for e in evs:
        f = e.composite_fields()
        out.append({"target": e.target, "hMin": f.get("healthDmgMin"), "hMax": f.get("healthDmgMax"),
                    "hits": f.get("appliedHits"), "prob": e.probability})
    return out


def _measure_arm(case: dict) -> dict:
    """UNE ligne : `u_port` et `u_natif` sur la MEME scene, plus les deux listes d'events."""
    vis, ability, thr, want_d = P.LIVE_CASTERS[0]
    uid = case["ids"][vis]
    tid = case["foe"]
    _dv, ctx = P._ctx(case, uid)
    u_port, port_action = P._port_u(ctx, ability, tid)
    u_nat, raw = _native_pair_utility(case["rid"], uid, tid, ability)
    nat = P._native_proposes(case)[vis]
    return {
        "arm": case["tag"], "caster": vis, "ability": ability, "threshold": thr,
        "hp": case["hp"], "dist": case["dist"].get(vis), "frozen": case["frozen"].get(vis),
        "u_port": u_port, "u_native": u_nat,
        "port_action": port_action, "native_proposes": nat[0], "msgs": nat[1],
        "native_events": _native_events(case["rid"], uid, tid, ability),
        "port_events": _port_events(ctx, ability, tid),
        "pair_raw_error": None if u_nat is not None else (raw.get("error") if isinstance(raw, dict) else str(raw)),
    }


def etape2_live(logs: str, verbose: bool = True) -> dict:
    """Les TROIS bras de #592, avec l'utilite NATIVE mesuree a cote de celle du port."""
    rows = []
    case = P._stage(logs, "lo", P.HP_LO)
    try:
        rows.append(_measure_arm(case))
    finally:
        P._dispose(case["rid"])
    ref = rows[0]
    if not ref["u_port"] or ref["u_port"] <= 0:
        print("[etape 2] CALIBRAGE IMPOSSIBLE : u_port=%s dans le bras lo" % ref["u_port"])
        return {"bad": 1, "rows": rows}
    for tag, target in (("mid", P.U_MID_TARGET), ("hi", P.U_HI_TARGET)):
        hp = max(1, int(round((P.HP_LO + 2) * ref["u_port"] / target)) - 2)
        case = P._stage(logs, tag, hp)
        try:
            rows.append(_measure_arm(case))
        finally:
            P._dispose(case["rid"])

    bad = 0
    if verbose:
        print("[etape 2] live -- board %s seed %s, Movement=%d, cible %s"
              % (P.BOARD, P.SEED, P.MOVEMENT, P.FOE))
        for r in rows:
            ratio = (r["u_port"] / r["u_native"]) if (r["u_native"] not in (None, 0)) else None
            print("  [%-3s] hp=%-9d dist=%-2s frozen=%-5s u_port=%-9s u_natif=%-9s ratio=%-8s "
                  "natifPropose=%-5s portAction=%s"
                  % (r["arm"], r["hp"], r["dist"], r["frozen"],
                     "None" if r["u_port"] is None else round(r["u_port"], 4),
                     "None" if r["u_native"] is None else round(r["u_native"], 4),
                     "None" if ratio is None else round(ratio, 3),
                     r["native_proposes"], r["port_action"]))
        print("  -- events (natif <- aiPlaybookPredict | port <- make_damage_predictions) --")
        for r in rows:
            print("     [%-3s] natif=%s" % (r["arm"], json.dumps(r["native_events"])[:300]))
            print("           port =%s" % json.dumps(r["port_events"])[:300])

    # MONTAGE : sans lui la ligne ne mesure pas ce qu'elle annonce (cf. #592).
    for r in rows:
        if not r["frozen"]:
            print("  BAD MONTAGE [%s] : Movement=0 n'a pas mordu" % r["arm"])
            bad += 1
        if r["u_native"] is None:
            print("  BAD CAPTEUR [%s] : pairUtility KO (%s)" % (r["arm"], r["pair_raw_error"]))
            bad += 1
    if bad:
        return {"bad": bad, "rows": rows}

    # LE DISCRIMINANT.
    by_arm = {r["arm"]: r for r in rows}
    accord = all(abs(r["u_native"] - r["u_port"]) <= 1e-6 * max(1.0, abs(r["u_port"]))
                 for r in rows)
    seuil = rows[0]["threshold"]
    # cause 1 : le gate natif explique EXACTEMENT le point de bascule mesure.
    cause1 = all((r["u_native"] > seuil) == r["native_proposes"] for r in rows)
    verdict = "INDETERMINE"
    if accord and not cause1:
        verdict = "CAUSE-2 (filtre au-dessus du playbook)"
    elif (not accord) and cause1:
        verdict = "CAUSE-1 (divergence d'utilite ; le gate natif suffit)"
    elif accord and cause1:
        verdict = "AUCUN ECART (le natif et le port s'accordent)"
    if verbose:
        print("  accord u_natif == u_port : %s" % accord)
        print("  `u_natif > %.1f` explique le verdict natif sur les 3 bras : %s" % (seuil, cause1))
        print("  VERDICT DISCRIMINANT: %s" % verdict)
        if verdict.startswith("CAUSE-1"):
            for r in rows:
                if r["u_native"] and r["u_port"]:
                    print("     [%-3s] u_port / u_natif = %.4f" % (r["arm"], r["u_port"] / r["u_native"]))
    if verdict == "INDETERMINE":
        print("  BAD : le montage ne separe pas les deux causes (accord=%s cause1=%s)"
              % (accord, cause1))
        bad += 1
    return {"bad": bad, "rows": rows, "accord": accord, "cause1": cause1, "verdict": verdict,
            "byArm": by_arm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="joue l'etape 2 (monte 3 runners, un a la fois)")
    ap.add_argument("--state-file", default=None, help="prefixe ABSOLU des state-files (avec --live)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    r1 = etape1_predicat_offline()
    r2 = {"bad": 0, "rows": []}
    if args.live:
        if not args.state_file:
            print("--live exige --state-file (chemin ABSOLU)")
            return 2
        logs = os.path.dirname(os.path.abspath(args.state_file))
        os.makedirs(logs, exist_ok=True)
        print("")
        r2 = etape2_live(logs)
    total = r1["bad"] + r2["bad"]
    print("")
    print("VERDICT: %s (etape1=%d BAD, etape2=%d BAD)"
          % ("PASS" if total == 0 else "FAIL", r1["bad"], r2["bad"]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"etape1": r1, "etape2": r2}, fh, indent=1)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
