#!/usr/bin/env python
"""Probe #369 -- `ncPlaybookPredict` est-il indexe sur le BON key-space d'enum ?

LA QUESTION (binaire)
---------------------
Peut-on faire charger a `ncPlaybookPredict` le playbook designe par `TriggeredAbilityType`, de
sorte qu'un id triggered rende SON playbook (ou une ERREUR FRANCHE), et jamais celui d'une autre
ability ?

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`, RE : `docs/rl/case-369-oracle-triggered-playbook.md`)
-------------------------------------------------------------------------------------------------
`IdunBattle.AI.PlaybookDatabase` porte QUATRE entrees a key-spaces DISTINCTS, chacune avec sa
propre paire de dictionnaires sur l'instance :

    LoadPlaybook(ActiveAbilityType, bool fallbackToDefault) -> IPlaybook
    LoadPlaybook(TriggeredAbilityType)                      -> ITriggeredAbilityPlaybook
    LoadPlaybookNonOwner(TriggeredAbilityType)              -> ITriggeredAbilityNonOwnerPlaybook
    LoadPlaybook(UnitSpecificBehaviourType)                 -> IUnitSpecificBehaviourPlaybook

Seule la face ACTIVE a un builder par DEFAUT. Les deux faces triggered font `return 0` sur un miss
du registry, et
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`
traite ce `0` par un `continue`. L'erreur franche n'est donc pas fabriquee : c'est la lecture.

CE QUE CE PROBE MESURE
----------------------
  etape 0 (OFFLINE, aucune plateforme requise) -- LA COLLISION EST-ELLE REELLE ?
          Compte, depuis `data/symbols/<build>/frida/enums.tsv`, les ids presents dans
          `ActiveAbilityType` ET `TriggeredAbilityType`, et parmi eux ceux qui designent des
          abilities de NOM DIFFERENT. Verifie les trois cas mesures (#384). C'est ce qui etablit
          que « meme id » ne dit RIEN, et donc qu'un oracle sans key-space rend une valeur pour la
          mauvaise ability.
  etape 1 (OFFLINE) -- LE HARNAIS DESAMBIGUISE-T-IL ?
          Garde STRUCTURELLE sur les sources du hook : la face triggered doit resoudre sur
          `TriggeredAbilityType`, et `rpc-nc-predict.ts` doit router par `abilityKind`. Cette garde
          ROUGIT sur mutation adversariale (remplacer le type par `ActiveAbilityType`, ou supprimer
          le routage) -- c'est elle qui tient le correctif en l'absence de fenetre de reinject.
  etape 2 (OFFLINE) -- LE REGIME DISCRIMINANT EST-IL ATTEIGNABLE ?
          Construit la FIXTURE : un seed BC dont `minDmg`/`maxDmg` sont forces a un couple
          `== 3 mod 4` (le SEUL regime ou troncature et demi-vers-le-pair divergent, cf. #350-r3b),
          et verifie que les deux formes rendent bien des valeurs DIFFERENTES.
  etape 3 (LIVE, CAPTEUR REQUIS) -- l'oracle repond-il par le BON playbook ?
          Interroge `ncPlaybookPredict` avec `abilityKind: "triggered"`. Un hook anterieur a #369
          ne connait pas ce champ : sa reponse ne le porte pas, et c'est cela qu'on teste AVANT de
          lire le moindre chiffre. Detection explicite => NON CONFRONTE nomme, jamais un accord
          suppose sur un playbook d'active.

Codes de retour : 0 = tout confronte et vert ; 1 = ECHEC ; 2 = rien n'a echoue mais une etape n'a
PAS ETE CONFRONTEE (typiquement : hook non reinjecte).

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_369_playbook_keyspace.py --offline
    python probe_369_playbook_keyspace.py
    python probe_369_playbook_keyspace.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]
HOOKS = ROOT / "frida" / "hooks" / "features" / "ai-step"

import symbols_layout as SL                                              # noqa: E402

ACTIVE_ENUM = "IdunBattle.Entities.Enum.ActiveAbilityType"
TRIGGERED_ENUM = "IdunBattle.Entities.Enum.TriggeredAbilityType"

# --- FIXTURES NOMMEES ---------------------------------------------------------------------------

# Les trois cas MESURES sur le hook d'avant #369 (PR #384, runner MC1_67, seed 350363) : ce que le
# RPC chargeait quand on lui passait un id TRIGGERED. `expected_playbook` = ce qu'il doit charger.
_FIXTURE_COLLISIONS = (
    (1103, "LightImUp", "Supercharge", "LightImUpPlaybook"),
    (1054, "MassiveScythingTalons", "CallRipperSwarms2", "MassiveScythingTalonsPlaybook"),
    # 1247 n'existe PAS dans ActiveAbilityType -> la face active retombait sur le fallback.
    (1247, "FuryOfTheAncients", None, "FuryOfTheAncientsPlaybook"),
)

# Le REGIME discriminant, et son porteur. `orksWarboss` (Gulgortz) porte `1103 LightImUp` et est au
# pool (`rl_duel build --list-pool`, rank 17). Le couple vise vaut 3 mod 4 : c'est le SEUL regime
# ou `RandomAmount` lu au slot 4 (troncature) et `Half(Sum(...))` lu au slot 1 (demi-vers-le-pair)
# rendent des valeurs differentes -- d'exactement 1, le demi-vers-le-pair MONTANT.
_FIXTURE_REGIME = {
    "ability": "LightImUp", "ability_id": 1103, "level": 50,
    "min_dmg": 831,     # valeur NOMINALE du gameconfig au niveau 50
    "max_dmg": 1112,    # 831 + 1112 = 1943 == 3 mod 4  (nominal 1109 -> 1940 == 0, non discriminant)
    "carrier": "orksWarboss", "board": "MC1_67", "seed": 36901, "rank": 17,
    "p_units": "orksWarboss,astraBullgryn", "a_units": "necroWarden,ultraTitus",
}

# --- etape 0 : OFFLINE, la collision des key-spaces ----------------------------------------------


def enum_members(build: str | None = None) -> dict:
    """{nom_d_enum: {valeur: membre}} depuis `data/symbols/<build>/frida/enums.tsv`.

    Format d'une ligne : `<nom>\\t<v>=<membre>,<v>=<membre>,...`. Entree VERSIONNEE (invariant 3 du
    CLAUDE.md) : lisible depuis n'importe quel worktree, sans plateforme."""
    path = SL.build_dir(build) / "frida" / "enums.tsv"
    out: dict = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#!"):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        members: dict = {}
        for kv in cols[1].split(","):
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            try:
                members[int(k)] = v
            except ValueError:
                continue
        out[cols[0]] = members
    return out


def step0_collision(verbose: bool = True) -> dict:
    build = SL.current_build()
    enums = enum_members(build)
    act = enums.get(ACTIVE_ENUM) or {}
    trg = enums.get(TRIGGERED_ENUM) or {}
    shared = sorted(set(act) & set(trg))
    divergent = [i for i in shared if act[i] != trg[i]]

    cases = []
    for aid, trg_name, act_name, _pb in _FIXTURE_COLLISIONS:
        cases.append({
            "id": aid,
            "triggered": trg.get(aid), "active": act.get(aid),
            "triggered_ok": trg.get(aid) == trg_name,
            "active_ok": act.get(aid) == act_name,
        })
    ok = bool(act and trg and divergent
              and all(c["triggered_ok"] and c["active_ok"] for c in cases))

    if verbose:
        print("[369/0] build = %s (data/symbols/CURRENT)" % build)
        print("  |ActiveAbilityType| = %d   |TriggeredAbilityType| = %d" % (len(act), len(trg)))
        print("  ids presents dans LES DEUX enums          : %d" % len(shared))
        print("  ... dont le membre DIFFERE d'un enum a l'autre : %d" % len(divergent))
        for c in cases:
            print("    %-5d triggered=%-24s active=%s" % (
                c["id"], c["triggered"] or "<absent>", c["active"] or "<absent>"))
        print("  -> %s" % ("OK" if ok else "ECHEC"))

    return {"ok": ok, "build": build, "n_active": len(act), "n_triggered": len(trg),
            "n_shared": len(shared), "n_divergent": len(divergent), "cases": cases}


# --- etape 1 : OFFLINE, le harnais desambiguise-t-il ? -------------------------------------------
#
# Garde STRUCTURELLE. Elle ne remplace pas la confrontation live -- elle la PRECEDE, et elle est le
# seul cliquet jouable tant que le hook n'est pas reinjecte. Elle est ecrite pour ROUGIR sur les
# deux mutations adversariales qui reintroduiraient le bug :
#   (a) faire resoudre la face triggered sur `ActiveAbilityType` ;
#   (b) supprimer le routage par `abilityKind` dans le RPC.

_TRIGGERED_SRC = HOOKS / "triggered-predict.ts"
_RPC_SRC = HOOKS / "rpc-nc-predict.ts"


def step1_harness(verbose: bool = True) -> dict:
    checks = []

    def _check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if not _TRIGGERED_SRC.is_file():
        _check("module triggered-predict.ts", False, "fichier absent : %s" % _TRIGGERED_SRC)
        src_t = ""
    else:
        src_t = _TRIGGERED_SRC.read_text(encoding="utf-8", errors="replace")
        _check("module triggered-predict.ts", True, "present")

    src_r = _RPC_SRC.read_text(encoding="utf-8", errors="replace") if _RPC_SRC.is_file() else ""

    # (a) la face triggered resout bien sur le TYPE `TriggeredAbilityType`.
    _check("key-space triggered = TriggeredAbilityType",
           'triggered: "TriggeredAbilityType"' in src_t
           and 'triggeredNonOwner: "TriggeredAbilityType"' in src_t,
           "KEY_SPACE_PARAM_CLASS mappe les deux faces triggered sur TriggeredAbilityType")
    _check("key-space active = ActiveAbilityType",
           'active: "ActiveAbilityType"' in src_t,
           "KEY_SPACE_PARAM_CLASS mappe la face active sur ActiveAbilityType")
    # `LoadPlaybookNonOwner` est un SYMBOLE distinct, pas un overload -- s'il retombait sur
    # `LoadPlaybook` on interrogerait le dictionnaire du proprietaire.
    _check("LoadPlaybookNonOwner distinct",
           'triggeredNonOwner: "LoadPlaybookNonOwner"' in src_t,
           "KEY_SPACE_METHOD nomme le symbole propre de la face non-owner")

    # (b) le RPC route par `abilityKind` et l'ECHOE (c'est ce qui rend un vieux hook detectable).
    _check("RPC route par abilityKind",
           "loadPlaybookByKeySpace" in src_r and "isAbilityKeySpace" in src_r,
           "rpc-nc-predict.ts appelle le chargeur par key-space")
    _check("RPC echoe abilityKind",
           "abilityKind: keySpace" in src_r,
           "la reponse porte le key-space effectivement interroge")
    # (c) durcissement : plus de fallback silencieux au DefaultActiveAbilityPlaybook.
    _check("durcissement allowDefault",
           "allowDefault" in src_r and "allowDefault" in src_t,
           "le fallback par defaut doit etre demande explicitement")
    # (d) le RPC ne doit plus passer par le chargeur mono-key-space.
    _check("plus d'appel a loadPlaybook(active-only)",
           "loadPlaybook(" not in src_r,
           "rpc-nc-predict.ts n'appelle plus playbook-predict.ts::loadPlaybook")

    ok = all(c["ok"] for c in checks)
    if verbose:
        print("[369/1] garde structurelle du harnais")
        for c in checks:
            print("  %-42s %-6s %s" % (c["name"], "OK" if c["ok"] else "ROUGE", c["detail"]))
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "checks": checks}


# --- etape 2 : OFFLINE, le regime discriminant est-il atteignable ? ------------------------------

def build_regime_seed_bc(out_path: Path) -> dict:
    """Ecrit la FIXTURE : un seed BC dont `LightImUp.minDmg/maxDmg` valent le couple `3 mod 4`.

    Rend `{path, report, min_dmg, max_dmg, trunc, half_even}`. C'est le montage REUTILISABLE de
    #369 : le passer a `rl_duel build --seed-bc <path>` amene le regime en bataille."""
    import catalog_inject as CI
    fx = _FIXTURE_REGIME
    path, reports = CI.write_variable_patched_seed_bc(
        out_path,
        [(fx["ability"], fx["level"], {"minDmg": fx["min_dmg"], "maxDmg": fx["max_dmg"]})],
        rank=fx["rank"], ability_level=fx["level"])
    forms = discriminating_forms(fx["min_dmg"], fx["max_dmg"])
    return {"path": path, "report": reports[0],
            "min_dmg": fx["min_dmg"], "max_dmg": fx["max_dmg"], **forms}


def discriminating_forms(mn: int, mx: int) -> dict:
    """Les DEUX formes, calculees par le FOYER du moteur (#350-r3b) -- pas re-derivees ici.

    `trunc`   = `RandomAmount(mn, mx)` lu au slot 4 (`AAmountFormula$$CalculateAverage`)
    `half_even` = `Half(Sum(mn, mx), 0)` lu au slot 1 (`Calculate` -> `Fix64.Round`)"""
    from engine.dsl.base import DslContext, Const
    from engine.entities.formulas import Sum, Half, RandomAmount
    ctx = DslContext()
    trunc = int(RandomAmount(Const(mn), Const(mx)).calculate_average(ctx))
    half_even = int(Half(Sum(Const(mn), Const(mx)), 0).calculate(ctx))
    return {"trunc": trunc, "half_even": half_even,
            "sum_mod_4": (mn + mx) % 4, "discriminating": trunc != half_even}


def step2_regime(verbose: bool = True) -> dict:
    out = ROOT / "logs" / "probe369" / "seed-bc-regime.json"
    try:
        fx = build_regime_seed_bc(out)
    except Exception as exc:                                   # noqa: BLE001
        if verbose:
            print("[369/2] MONTAGE KO : %s" % exc)
        return {"ok": False, "error": str(exc)}
    ok = bool(fx["discriminating"] and fx["half_even"] - fx["trunc"] == 1)
    if verbose:
        print("[369/2] regime discriminant (fixture reutilisable)")
        print("  seed BC ecrit : %s" % fx["path"])
        print("  %s lvl %d : minDmg=%d maxDmg=%d (somme %% 4 = %d)"
              % (_FIXTURE_REGIME["ability"], _FIXTURE_REGIME["level"],
                 fx["min_dmg"], fx["max_dmg"], fx["sum_mod_4"]))
        print("  multiplicateur de rarete neutralise : %s (variables %s)"
              % (fx["report"]["rarity_neutralized"], fx["report"]["deaffected"]))
        print("  troncature (slot 4) = %d   demi-vers-le-pair (slot 1) = %d   ecart = %d"
              % (fx["trunc"], fx["half_even"], fx["half_even"] - fx["trunc"]))
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "path": str(fx["path"]), "min_dmg": fx["min_dmg"],
            "max_dmg": fx["max_dmg"], "trunc": fx["trunc"], "half_even": fx["half_even"],
            "sum_mod_4": fx["sum_mod_4"], "report": fx["report"]}


# --- plomberie LIVE ------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc              # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, fx: dict, seed_bc: Path | None) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--state-file", str(state_file), "--board", fx["board"], "--rank", str(fx["rank"]),
           "--p-units", fx["p_units"], "--a-units", fx["a_units"], "--no-ai"]
    if seed_bc is not None:
        cmd += ["--seed-bc", str(seed_bc)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


# --- etape 3 : LIVE, l'oracle repond-il par le BON playbook ? ------------------------------------
#
# LE MESSAGE ROUGE EST VERBATIM. C'est lui que la garde publie quand un id triggered resout sur un
# playbook d'active -- exactement le mode de panne mesure par #384.

KEYSPACE_MISMATCH = ("#369 KEY-SPACE : ability TRIGGERED %d (%s) a resolu sur le playbook %r"
                     " -- attendu %r. ncPlaybookPredict interroge le key-space ActiveAbilityType.")

HOOK_NOT_REINJECTED = ("#369 NON CONFRONTE : le hook deploye ignore `abilityKind` (champ absent de"
                       " la reponse de ncPlaybookPredict) -- fenetre de reinject requise.")


def check_keyspace_response(resp: dict, ability_id: int, triggered_name: str,
                            expected_playbook: str) -> dict:
    """Verdict sur UNE reponse de `ncPlaybookPredict`. Pur, donc testable sans plateforme.

    Trois issues, jamais deux :
      * `not_reinjected` -- la reponse ne porte pas `abilityKind` : le hook est anterieur a #369.
        NON CONFRONTE, et on ne lit AUCUN chiffre (ils viendraient de la mauvaise ability).
      * `mismatch`       -- le playbook charge n'est pas celui attendu -> ECHEC, message VERBATIM.
      * `ok`             -- le key-space demande est bien celui qui a repondu.
    """
    if "abilityKind" not in resp:
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    got = resp.get("playbookClass")
    if resp.get("abilityKind") != "triggered":
        return {"status": "mismatch",
                "message": "#369 KEY-SPACE : abilityKind rendu = %r, attendu 'triggered'"
                           % resp.get("abilityKind")}
    if got != expected_playbook:
        return {"status": "mismatch",
                "message": KEYSPACE_MISMATCH % (ability_id, triggered_name, got,
                                                expected_playbook)}
    return {"status": "ok", "message": None, "playbookClass": got}


def step3_live(verbose: bool = True, keep: bool = False) -> dict:
    resolve_session, rpc = _rpc_mod()
    sid = resolve_session()
    fx = _FIXTURE_REGIME
    state = ROOT / "logs" / "probe369" / "runner-369.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    seed_bc = ROOT / "logs" / "probe369" / "seed-bc-regime.json"
    if not seed_bc.is_file():
        build_regime_seed_bc(seed_bc)
    rid = _build(state, fx, seed_bc)
    results = []
    try:
        dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32},
                180)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if u.get("visualId") == fx["carrier"]), None)
        victim = next((u for u in units
                       if caster and u.get("team") != caster.get("team")), None)
        if caster is None or victim is None:
            return {"ok": False, "confronted": False,
                    "error": "montage : caster %r ou cible absente du decisionView" % fx["carrier"]}
        for aid, trg_name, _act_name, pb in _FIXTURE_COLLISIONS:
            resp = _r(rpc, sid, "ncPlaybookPredict", {
                "runnerId": rid, "unitId": int(caster["id"]), "targetId": int(victim["id"]),
                "abilityType": aid, "abilityKind": "triggered",
                "via": "attackUtilityInSteps", "hits": 1}, 240)
            verdict = check_keyspace_response(resp, aid, trg_name, pb)
            results.append({"ability": aid, "name": trg_name, "expected": pb,
                            "playbookClass": resp.get("playbookClass"),
                            "rpcError": resp.get("error"),
                            "capturedCount": resp.get("capturedCount"),
                            "captured": resp.get("captured"),
                            **verdict})
    finally:
        if not keep:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                        # noqa: BLE001
                pass
    not_reinjected = any(r["status"] == "not_reinjected" for r in results)
    failed = [r for r in results if r["status"] == "mismatch"]
    if verbose:
        print("[369/3] oracle LIVE (runner %d, %s)" % (rid, fx["board"]))
        for r in results:
            print("  %-5d %-24s -> %-32s %s" % (
                r["ability"], r["name"], r["playbookClass"] or "<none>", r["status"].upper()))
            if r["message"]:
                print("      %s" % r["message"])
            if r["rpcError"]:
                print("      rpc error: %s" % str(r["rpcError"])[:180])
        if not_reinjected:
            print("  -> NON CONFRONTE (hook non reinjecte)")
        else:
            print("  -> %s" % ("OK" if not failed else "ECHEC"))
    return {"ok": not failed, "confronted": not not_reinjected,
            "runner": rid, "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="#369 -- key-space d'enum de ncPlaybookPredict")
    ap.add_argument("--offline", action="store_true", help="etapes 0 a 2 seulement")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    args = ap.parse_args()
    v = not args.json

    out = {"step0": step0_collision(v), "step1": step1_harness(v), "step2": step2_regime(v)}
    rc = 0 if all(out[k]["ok"] for k in ("step0", "step1", "step2")) else 1
    if not args.offline:
        try:
            out["step3"] = step3_live(v, keep=args.keep)
        except Exception as exc:                                     # noqa: BLE001
            out["step3"] = {"ok": False, "confronted": False, "error": str(exc)}
        if not out["step3"].get("ok"):
            rc = 1
        elif not out["step3"].get("confronted") and rc == 0:
            rc = 2
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
