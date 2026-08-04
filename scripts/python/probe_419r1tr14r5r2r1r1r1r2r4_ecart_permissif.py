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

MESURE (2026-08-04, board `MC1_67`, seed `4242`) : `u_natif == u_port` a l'arrondi Fix64 pres sur
les TROIS bras (`0.0851` / `5.0` / `20.0`), et `aiPlaybookPredict` rend la MEME liste d'events que
le port (`hMin 2724`, `hMax 4083`, `hits 3`, `prob 1`). **Les deux causes sont donc REFUTEES** :
aucune divergence d'utilite, et aucun filtre au-dessus. Le refus vient du gate `ShouldExecute`
lui-meme -- son SEUIL n'etait pas celui que la tranche precedente avait lu.

### Etapes 3 et 4 -- LIVE : le seuil EFFECTIF, encadre puis confirme sur une identite OPPOSEE

`<X>Playbook$$ShouldExecute` lit le PREMIER static de sa classe. Ce champ a DEUX ecrivains, et la
tranche precedente n'en avait lu qu'un :

* `<X>Playbook$$.cctor` -- QUATRE des douze classes en declarent un, qui y ecrit `Fix64(1)` ;
* `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.cctor` --
  `FixMath.NET.Fix64$$op_Implicit(0xa)` stocke a `**(<klass resolu par RGCTX> + 0xb8)`, c.-a-d. le
  MEME slot. C'est le SEUL `Fix64(10)` de la couche playbook.

Le `.cctor` derive est declenche par le `class_init` de la classe derivee (a l'allocation) ; celui
de la base l'est plus tard, par `ComparablePlaybook<T>..ctor` que le `.ctor` derive appelle ENSUITE.
Le dernier ecrivain gagne.

* **etape 3** encadre le seuil NATIF de `1150` (qui A un `.cctor` derive) par deux points calibres :
  mesure `(9.9997062, 10.0000000093]` -- ca CONTIENT `Fix64(10)` (raw `42949672960`) et ca EXCLUT
  `Fix64(1)` de 4 ordres de grandeur.
* **etape 4** rejoue l'encadrement sur `1069 SeekerMissileFrequencyLock`, qui ne declare AUCUN
  `.cctor` (la tranche precedente en concluait `Fix64(0)`), GREFFEE sur le meme caster : mesure
  `(9.8438, 10.0781]`. Deux seuils DECLARES opposes, UN seul seuil effectif.

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif.py
    python scripts/python/probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif.py --live --seuil \\
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
        verdict = "CAUSE-2 (un refus INDEPENDANT du seuil porte -- filtre ou seuil FAUX)"
    elif (not accord) and cause1:
        verdict = "CAUSE-1 (divergence d'utilite ; le gate natif suffit)"
    elif accord and cause1:
        verdict = ("ACCORD PLEIN : u_natif == u_port ET `u > %.1f` explique le verdict natif "
                   "-- le gate `ShouldExecute` au seuil porte suffit" % seuil)
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


# --------------------------------------------------------------------- etapes 3/4 : le SEUIL

#: `Fix64(10)`, ecrit par `ComparablePlaybook<T>$$.cctor` (op_Implicit(0xa) -> raw `10 << 32`).
FIX64_TEN_RAW = 10 * (1 << 32)
THRESHOLD = 10.0

#: Le TEMOIN a `.cctor` derive OPPOSE : `1069 SeekerMissileFrequencyLock` ne declare AUCUN `.cctor`
#: propre (la tranche precedente en concluait `Fix64(0)`), et `1150 PlasmaCannon` en declare un qui
#: ecrit `Fix64(1)`. Si les DEUX basculent a 10, aucun des deux seuils DECLARES n'est le seuil
#: effectif -- et le seul ecrivain restant est celui de la base generique.
WITNESS_ABILITY = 1069
WITNESS_REAL_CARRIER = "tauMarksman"      # porteur REEL -> sa config d'ability est au catalogue


def _graft_seed(out_path: str, ability: int, carrier: str) -> str:
    """Ecrit une COPIE du seed BC ou `darkaTerminator` porte `ability` a la place de la sienne.

    Greffe LEGITIME au sens de `docs/rl/case-92-catalog-injection.md` §5bis : le natif charge le
    playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), et `<X>Playbook$$
    ShouldExecute` ne lit NI stats NI traits du caster -- il lit un champ STATIQUE de sa classe.
    Le porteur REEL est injecte au catalogue pour que `BC.Abilities` porte SA config d'ability
    (sans elle, la premiere lecture de variable leve « system error », cf. #226).
    Le seed BC PARTAGE n'est jamais modifie."""
    import catalog_inject as CI
    CI.write_augmented_seed_bc(out_path, [carrier], seed_bc=CI._load_seed(None))
    with open(out_path, encoding="utf-8") as fh:
        bc = json.load(fh)
    vis = P.LIVE_CASTERS[0][0]
    for u in bc.get("Units", []):
        if u.get("Id") == vis or u.get("VisualId") == vis:
            u["ActiveAbilities"] = [ability]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(bc, fh)
    return out_path


def _stage(logs: str, tag: str, hp: int, *, seed_bc: str | None = None) -> dict:
    """Le montage de la tranche precedente (`Movement=0`, cible a distance 3), avec un seed BC
    optionnel (pour le temoin greffe)."""
    vis, ability, _thr, want_d = P.LIVE_CASTERS[0]
    sf = os.path.join(logs, "r4_%s.json" % tag)
    tail = ["--seed", P.SEED, "--board", P.BOARD, "--no-ai",
            "--p-units", vis, "--a-units", P.FOE,
            "--unit-stat", "%s:Movement=%d" % (vis, P.MOVEMENT),
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (P.FOE, hp, hp)]
    if seed_bc:
        tail = ["--seed-bc", seed_bc] + tail
    rid = P._build(sf, tail)
    dv = P.rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    ids, foe_id = {}, None
    for u in (dv.get("units") or ()):
        if u.get("visualId") == P.FOE:
            foe_id = u.get("id")
        else:
            ids[u.get("visualId")] = u.get("id")
    if ids.get(vis) is None or foe_id is None:
        P._dispose(rid)
        raise P.MontageError("montage NON INSTALLE (%s) : caster=%s cible=%s" % (tag, ids, foe_id))
    dist, reach, frozen = P._deploy(sf, rid, {vis: ids[vis]}, foe_id)
    return {"tag": tag, "rid": rid, "sf": sf, "hp": hp, "ids": ids, "foe": foe_id,
            "dist": dist, "reach": reach, "frozen": frozen, "ability": ability, "vis": vis}


def _one(logs: str, tag: str, hp: int, *, seed_bc: str | None = None) -> dict:
    import hexgeo
    case = _stage(logs, tag, hp, seed_bc=seed_bc)
    rid, vis, ability = case["rid"], case["vis"], case["ability"]
    uid, tid = case["ids"][vis], case["foe"]
    try:
        dv = P.rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
        by_id = {u.get("id"): u for u in (dv.get("units") or ())}
        pu = P.rpc("pairUtility", {"runnerId": rid, "unitId": uid, "targetId": tid,
                                   "abilityType": ability}, 120) or {}
        _dv, ctx = P._ctx(case, uid)
        u_port, port_action = P._port_u(ctx, ability, tid)
        dry = P.rpc("aiDryRunAllUnits", {"runnerId": rid}, 300) or {}
        msgs = []
        for uu in (dry.get("units") or ()):
            if uu.get("unitId") == uid:
                msgs = [(m.get("cls"), m.get("abilityType")) for m in (uu.get("proposed") or ())]
        return {
            "tag": tag, "hp": hp, "ability": ability, "playbook": pu.get("playbookClass"),
            "dist": hexgeo.distance(P._pos(by_id[uid]), P._pos(by_id.get(tid) or {})),
            "frozen": case["frozen"].get(vis), "normalPlan": P._normal_has_plan(dv, uid),
            "castableHere": P._ability_castable_here(dv, uid, ability),
            "u": pu.get("utility"), "uRaw": pu.get("utilRaw"), "u_port": u_port,
            "port": port_action,
            "native": any(c == "ActiveAbilityMessage" and a == ability for c, a in msgs),
            "msgs": msgs,
        }
    finally:
        P._dispose(case["rid"])


def _bracket(logs: str, tag: str, ability: int, seed_bc: str | None, verbose: bool) -> dict:
    """Encadre le seuil NATIF par DEUX points calibres autour de `THRESHOLD`.

    `u = 100 x dmg / (maxHP + 2)` sur cible pleine sans bouclier ==> `K = u x (maxHP + 2)` est
    INVARIANT a degat constant. Un premier bras a PV enormes donne `K` ; les deux points de
    l'encadrement s'en derivent, sans jamais supposer le degat. Le pas d'un PV donne un pas de
    `~3e-4` en `u` : l'encadrement est donc serre a ~3e-5 relatif."""
    P.LIVE_CASTERS = ((P.LIVE_CASTERS[0][0], ability, THRESHOLD, P.LIVE_CASTERS[0][3]),)
    ref = _one(logs, tag + "_cal", P.HP_LO, seed_bc=seed_bc)
    if not ref["u"] or ref["u"] <= 0:
        return {"bad": 1, "rows": [ref], "reason": "calibrage impossible (u=%s)" % ref["u"]}
    K = ref["u"] * (P.HP_LO + 2)
    hp0 = max(1, int(round(K / THRESHOLD)) - 2)
    # ⚠ `hp0` EXACTEMENT donne `u_port == 10.0` (le calcul flottant du port tombe pile) alors que
    # le natif, en Fix64 Q32.32, rend `10 + 9.3e-9` : a l'EGALITE le natif ACCEPTE et le port
    # REFUSE, pour une raison d'ARITHMETIQUE et non de seuil. On evite donc ce regime degenere --
    # il est MESURE et NOMME dans la case-doc, il ne fait pas un bon cran.
    under = _one(logs, tag + "_under", hp0 + 1, seed_bc=seed_bc)   # u JUSTE SOUS le seuil
    over = _one(logs, tag + "_over", max(1, hp0 - 1), seed_bc=seed_bc)   # u JUSTE AU-DESSUS
    rows = [ref, under, over]
    bad = 0
    if verbose:
        for r in rows:
            print("  [%-14s] ab=%-5d pb=%-34s hp=%-9d dist=%-2s frozen=%-5s normal=%-5s cast=%-5s "
                  "u_natif=%-13s u_port=%-13s natif=%-5s port=%s"
                  % (r["tag"], r["ability"], str(r["playbook"])[:34], r["hp"], r["dist"],
                     r["frozen"], r["normalPlan"], r["castableHere"],
                     "None" if r["u"] is None else ("%.7f" % r["u"]),
                     "None" if r["u_port"] is None else ("%.7f" % r["u_port"]),
                     r["native"], r["port"]))
    for r in rows:
        if not r["frozen"] or r["normalPlan"] or not r["castableHere"] or r["dist"] != 3:
            print("  BAD MONTAGE [%s] frozen=%s normal=%s cast=%s dist=%s"
                  % (r["tag"], r["frozen"], r["normalPlan"], r["castableHere"], r["dist"]))
            bad += 1
    if bad:
        return {"bad": bad, "rows": rows}
    # L'ENCADREMENT, et ce qu'il exclut.
    if not (under["u"] < THRESHOLD < over["u"]):
        print("  BAD CALIBRAGE [%s] : u_under=%s u_over=%s n'encadrent pas %.1f"
              % (tag, under["u"], over["u"], THRESHOLD))
        return {"bad": bad + 1, "rows": rows}
    if under["native"]:
        print("  VIOLE [%s] : le natif ACCEPTE a u=%.7f < %.1f" % (tag, under["u"], THRESHOLD))
        bad += 1
    if not over["native"]:
        print("  VIOLE [%s] : le natif REFUSE a u=%.7f > %.1f" % (tag, over["u"], THRESHOLD))
        bad += 1
    # ACCORD du port sur les DEUX points -- c'est ce que la correction de seuil achete.
    for r in (under, over):
        if bool(r["port"]) != bool(r["native"]):
            print("  VIOLE ACCORD [%s/%s] : natif=%s port=%s a u=%.7f"
                  % (tag, r["tag"], r["native"], r["port"], r["u"]))
            bad += 1
    if verbose:
        print("  SEUIL ability %d encadre dans (%.7f, %.7f] -- Fix64(10) raw=%d y est"
              % (ability, under["u"], over["u"], FIX64_TEN_RAW))
    return {"bad": bad, "rows": rows, "under": under["u"], "over": over["u"]}


def etape3_encadrement(logs: str, verbose: bool = True) -> dict:
    """`1150 PlasmaCannon` -- la classe qui declare un `.cctor` ecrivant `Fix64(1)`."""
    if verbose:
        print("[etape 3] encadrement du seuil NATIF -- 1150 (`.cctor` derive = Fix64(1))")
    return _bracket(logs, "e3_1150", 1150, None, verbose)


def etape4_temoin_greffe(logs: str, verbose: bool = True) -> dict:
    """`1069 SeekerMissileFrequencyLock` -- AUCUN `.cctor` derive. Greffee sur le MEME caster."""
    if verbose:
        print("[etape 4] temoin a `.cctor` OPPOSE -- %d greffee sur %s (porteur reel %s)"
              % (WITNESS_ABILITY, P.LIVE_CASTERS[0][0], WITNESS_REAL_CARRIER))
    seed = _graft_seed(os.path.join(logs, "r4_graft_%d.json" % WITNESS_ABILITY),
                       WITNESS_ABILITY, WITNESS_REAL_CARRIER)
    return _bracket(logs, "e4_%d" % WITNESS_ABILITY, WITNESS_ABILITY, seed, verbose)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="joue l'etape 2 (monte 3 runners, un a la fois)")
    ap.add_argument("--seuil", action="store_true", help="joue les etapes 3 et 4 (6 runners)")
    ap.add_argument("--state-file", default=None, help="prefixe ABSOLU des state-files (avec --live)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    r1 = etape1_predicat_offline()
    r2 = {"bad": 0, "rows": []}
    r3 = {"bad": 0, "rows": []}
    r4 = {"bad": 0, "rows": []}
    if args.live or args.seuil:
        if not args.state_file:
            print("--live/--seuil exigent --state-file (chemin ABSOLU)")
            return 2
        logs = os.path.dirname(os.path.abspath(args.state_file))
        os.makedirs(logs, exist_ok=True)
        if args.live:
            print("")
            r2 = etape2_live(logs)
        if args.seuil:
            print("")
            r3 = etape3_encadrement(logs)
            print("")
            r4 = etape4_temoin_greffe(logs)
    total = r1["bad"] + r2["bad"] + r3["bad"] + r4["bad"]
    print("")
    print("VERDICT: %s (etape1=%d BAD, etape2=%d BAD, etape3=%d BAD, etape4=%d BAD)"
          % ("PASS" if total == 0 else "FAIL", r1["bad"], r2["bad"], r3["bad"], r4["bad"]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"etape1": r1, "etape2": r2, "etape3": r3, "etape4": r4}, fh, indent=1)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
