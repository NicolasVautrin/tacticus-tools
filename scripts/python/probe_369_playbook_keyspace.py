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
  etape 2 (OFFLINE) -- LE REGIME DISCRIMINANT EST-IL ATTEIGNABLE, ET ARRIVE-T-IL AU RUNNER ?
          Construit la FIXTURE : un seed BC dont `minDmg`/`maxDmg` sont forces a un couple
          `== 3 mod 4` (le SEUL regime ou troncature et demi-vers-le-pair divergent, cf. #350-r3b),
          verifie que les deux formes rendent bien des valeurs DIFFERENTES, PUIS -- et c'est le
          cliquet de #375 -- relit la fixture PAR LE CHEMIN DU BUILD (`_load_seed_bc`) pour verifier
          que le patch SURVIT. Il ne survivait pas : `refresh_ability_configs` re-synthetisait
          `LightImUp` depuis le gameconfig vivant et REVERTAIT les valeurs, EN SILENCE.
  etape 3 (LIVE, CAPTEUR REQUIS) -- l'oracle repond-il par le BON playbook ?
          Interroge `ncPlaybookPredict` avec `abilityKind: "triggered"`. Un hook anterieur a #369
          ne connait pas ce champ : sa reponse ne le porte pas, et c'est cela qu'on teste AVANT de
          lire le moindre chiffre. Detection explicite => NON CONFRONTE nomme, jamais un accord
          suppose sur un playbook d'active.
          #375 y ajoute la FORME de la reponse MUETTE : sur `via: attackUtilityInSteps` le natif ne
          construit AUCUN `ProbableDamageEvent` tant que le `UtilityAttackCase` ne nomme pas
          d'ability -- il yielde exactement un `Fix64(0)`. C'est une reponse, pas un trou ; on
          l'asserte au lieu de la subir.
  etape 4 (LIVE) -- LA FACE DEMI-VERS-LE-PAIR, CONFRONTEE
          TROIS montages sur la MEME geometrie, via `attackUtilityForMainTarget` (call-site natif
          qui appelle `ProbableDamageEvent$$.ctor` DIRECTEMENT) : une reference `971` sans
          ambiguite, une reference `972` sans ambiguite, et le regime discriminant. La reference
          basse DOIT differer de la haute (sinon l'etage aval ecrase l'ecart -> NON CONFRONTE, pas
          vert), et le regime discriminant doit tomber sur la reference HAUTE.

Codes de retour : 0 = tout confronte et vert ; 1 = ECHEC ; 2 = rien n'a echoue mais une etape n'a
PAS ETE CONFRONTEE (typiquement : hook non reinjecte, ou montage non observable).

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
#
# ⚠ `armor_target: 0` N'EST PAS UN CONFORT, C'EST LA CONDITION D'OBSERVABILITE (#375, MESUREE).
# La valeur demi-vers-le-pair entre dans le `DamagePredictionResult` par l'argument `damage` de
# `GetAttackPrediction` -- mais l'etage aval la MULTIPLIE (profil de degat x armure de la cible).
# Mesure du 2026-07-31 sur `necroWarden` a son armure nominale : le facteur vaut ~0.18, donc
# `damage = 971` et `damage = 972` rendent TOUS DEUX `healthDmgMin = 175` -- l'ecart de 1 est
# ecrase, et la mesure ne conclut RIEN (elle avait l'air verte). Armure a 0, le meme balayage rend
# `971 -> 1166` et `972 -> 1167` : l'ecart survit. C'est la reference basse/haute de l'etape 4 qui
# le VERIFIE a chaque run, au lieu de le supposer.
_FIXTURE_REGIME = {
    "ability": "LightImUp", "ability_id": 1103, "level": 50,
    "min_dmg": 831,     # valeur NOMINALE du gameconfig au niveau 50
    "max_dmg": 1112,    # 831 + 1112 = 1943 == 3 mod 4  (nominal 1109 -> 1940 == 0, non discriminant)
    "max_low": 1111,    # 831 + 1111 = 1942 == 2 mod 4 -> 971 par les DEUX formes
    "max_high": 1113,   # 831 + 1113 = 1944 == 0 mod 4 -> 972 par les DEUX formes
    "armor_target": "0",
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


def _success_payload(src: str) -> str:
    """Le litteral d'objet du chemin SUCCES de `ncPlaybookPredict` (`const out: ... = { ... };`).

    ⚠ POURQUOI CETTE EXTRACTION EXISTE. La premiere version de cette garde cherchait
    `"abilityKind: keySpace"` dans TOUT le fichier -- et elle est restee VERTE quand on a supprime
    l'echo du chemin succes, parce que la MEME chaine apparait dans les retours d'ERREUR
    (`return { ok: false, abilityKind: keySpace, ... }`). Mesure le 2026-07-31 par mutation
    adversariale : 10 tests verts sur un hook mute. Une garde qui matche n'importe ou dans un
    fichier ne garde rien -- il faut viser le chemin qu'on protege."""
    marker = "const out: Record<string, unknown> = {"
    i = src.find(marker)
    if i < 0:
        return ""
    j = src.find("\n        };", i)
    return src[i:j] if j > i else src[i:]


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
    # L'echo doit etre dans le chemin SUCCES, pas seulement dans un retour d'erreur : c'est lui que
    # l'appelant lit pour savoir si le hook connait `abilityKind`.
    payload = _success_payload(src_r)
    _check("RPC echoe abilityKind (chemin SUCCES)",
           bool(payload) and "abilityKind: keySpace" in payload,
           "le litteral `out` porte le key-space effectivement interroge")
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

def build_regime_seed_bc(out_path: Path, max_dmg: int | None = None) -> dict:
    """Ecrit la FIXTURE : un seed BC dont `LightImUp.minDmg/maxDmg` valent le couple demande.

    Rend `{path, report, min_dmg, max_dmg, trunc, half_even, roundtrip}`. C'est le montage
    REUTILISABLE de #369 : le passer a `rl_duel build --seed-bc <path>` amene le regime en bataille.

    ⚠ `write_variable_patched_seed_bc` ecrit AUSSI le sidecar `<path>.pins.json` (#375). Sans lui
    `rl_collect_batch._load_seed_bc` re-synthetise `LightImUp` depuis le gameconfig vivant et
    REVERTE le patch, sans un mot -- la fixture etait alors ecrite, jamais jouee. `roundtrip` rend
    ce que le CHEMIN DU BUILD relit reellement : c'est la seule lecture qui prouve quelque chose.

    ⚠⚠ CE SEED BC EST NATIF-ONLY (#366-r1-bcpatch-invisible). Le regime `minDmg + maxDmg == 3 mod 4`
    n'existe a AUCUN niveau du gameconfig : l'ecrire dans le BC ne change donc que le NATIF, et le
    moteur Python continue de lire `831/1109` la ou le natif lit `831/1112`. Ce montage ne
    confronte QUE l'oracle (`ncPlaybookPredict`) et des `Const(...)` explicites -- ne JAMAIS s'en
    servir pour confronter une PREDICTION PYTHON. Exception nommee dans
    `probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS`."""
    import catalog_inject as CI
    fx = _FIXTURE_REGIME
    mx = fx["max_dmg"] if max_dmg is None else int(max_dmg)
    path, reports = CI.write_variable_patched_seed_bc(
        out_path,
        [(fx["ability"], fx["level"], {"minDmg": fx["min_dmg"], "maxDmg": mx})],
        rank=fx["rank"], ability_level=fx["level"])
    forms = discriminating_forms(fx["min_dmg"], mx)
    return {"path": path, "report": reports[0], "pins": CI.read_pins(path),
            "min_dmg": fx["min_dmg"], "max_dmg": mx,
            "roundtrip": seed_bc_roundtrip(path), **forms}


def seed_bc_roundtrip(path: Path) -> dict:
    """Ce que `rl_duel build --seed-bc <path>` LIRA reellement pour `LightImUp` au niveau vise.

    Passe par `rl_collect_batch._load_seed_bc` -- le chemin EXACT du build, rattrapage #254 inclus.
    Lire le fichier sur disque ne prouverait rien : c'est precisement l'ecart entre le disque et ce
    chemin qui a rendu la fixture inerte."""
    from rl_collect_batch import _load_seed_bc
    fx = _FIXTURE_REGIME
    bc = _load_seed_bc(str(path))
    cfg = ((bc.get("Abilities") or {}).get("PassiveAbilities") or {}).get(fx["ability"]) or {}
    variables = cfg.get("Variables") or {}
    idx = max(0, fx["level"] - 1)
    def _at(name):
        arr = variables.get(name) or []
        return int(arr[min(idx, len(arr) - 1)]) if arr else None
    return {"min_dmg": _at("minDmg"), "max_dmg": _at("maxDmg"),
            "rarity_affected": cfg.get("VariablesAffectedByUnitRarityMultiplier")}


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
    rt = fx["roundtrip"]
    # LE CLIQUET DE #375 : le patch doit survivre au CHEMIN DU BUILD, pas seulement au disque.
    survives = (rt["min_dmg"] == fx["min_dmg"] and rt["max_dmg"] == fx["max_dmg"]
                and not rt["rarity_affected"])
    ok = bool(fx["discriminating"] and fx["half_even"] - fx["trunc"] == 1 and survives)
    if verbose:
        print("[369/2] regime discriminant (fixture reutilisable)")
        print("  seed BC ecrit : %s" % fx["path"])
        print("  epingles (#375) : %s" % fx["pins"])
        print("  %s lvl %d : minDmg=%d maxDmg=%d (somme %% 4 = %d)"
              % (_FIXTURE_REGIME["ability"], _FIXTURE_REGIME["level"],
                 fx["min_dmg"], fx["max_dmg"], fx["sum_mod_4"]))
        print("  multiplicateur de rarete neutralise : %s (variables %s)"
              % (fx["report"]["rarity_neutralized"], fx["report"]["deaffected"]))
        print("  troncature (slot 4) = %d   demi-vers-le-pair (slot 1) = %d   ecart = %d"
              % (fx["trunc"], fx["half_even"], fx["half_even"] - fx["trunc"]))
        print("  RELU par le chemin du build : minDmg=%s maxDmg=%s rarityAffected=%s -> %s"
              % (rt["min_dmg"], rt["max_dmg"], rt["rarity_affected"],
                 "SURVIT" if survives else "ECRASE (fixture INERTE)"))
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "path": str(fx["path"]), "min_dmg": fx["min_dmg"],
            "max_dmg": fx["max_dmg"], "trunc": fx["trunc"], "half_even": fx["half_even"],
            "sum_mod_4": fx["sum_mod_4"], "report": fx["report"], "pins": fx["pins"],
            "roundtrip": rt, "survives": survives}


# --- plomberie LIVE ------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc              # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, fx: dict, seed_bc: Path | None, extra=()) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--state-file", str(state_file), "--board", fx["board"], "--rank", str(fx["rank"]),
           "--p-units", fx["p_units"], "--a-units", fx["a_units"], "--no-ai"]
    if seed_bc is not None:
        cmd += ["--seed-bc", str(seed_bc)]
    cmd += list(extra)
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


# --- etape 3bis (#375) : la FORME de la reponse MUETTE, et pourquoi elle est CORRECTE -------------
#
# `via: attackUtilityInSteps` rendait `capturedCount: 0` / `captured: []` pour les TROIS abilities,
# sans erreur -- et c'etait lu comme « le capteur ne capture rien ». Le decompile dit autre chose,
# et il dit DEUX choses distinctes :
#
#  * `1103` / `1054` -- l'ancrage `ProbableDamageEvent$$.ctor` est bien sur le chemin, mais le
#    chemin n'y arrive pas. `IdunBattle.AI.Playbook.Loki.LightImUpPlaybook.u003CCalculateAttack
#    UtilityInStepsInternalu003Ed__2$$MoveNext` teste `TriggeredAbilityPlaybook<T>$$IsMeleeAttack`
#    PUIS `$$IsRegularAttack` avant tout ; son homologue
#    `...MassiveScythingTalonsPlaybook.u003C...u003Ed__2$$MoveNext` teste `$$IsRegularAttack` en
#    PREMIERE instruction. Or `$$IsRegularAttack` commence par `Nullable<AbilityOrEffect>.
#    get_HasValue()` sur `case+0xf0` -- et `buildUtilityAttackCase` (triggered-predict.ts) passe ce
#    Nullable ZERO-REMPLI, donc `HasValue = false`, donc `false` immediat. Les deux machines a etats
#    yieldent alors exactement UN `Fix64(0)` et sortent : aucun `ProbableDamageEvent` n'est
#    construit. `capturedCount: 0` est la reponse EXACTE du natif au cas soumis.
#  * `1247` -- raison DIFFERENTE et sans rapport : `FuryOfTheAncientsPlaybook` ne surcharge PAS
#    `CalculateAttackUtilityInStepsInternal` (aucun symbole, cf. `ghidra/functions.tsv`). Le corps
#    herite `TriggeredAbilityPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__37
#    u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` yielde UN `Fix64(0)` et rien d'autre. Sa
#    prediction (slot 4, TRONCATURE) vit sur la voie MOUVEMENT :
#    `FuryOfTheAncientsPlaybook$$GetDamagePrediction` n'a qu'UN appelant, `$$GetDamagedEnemyUtility`.
#
# On asserte donc la FORME de ce silence (un seul 0 yielde, aucune erreur) au lieu de l'ignorer --
# et l'assertion S'INVERSE des que le hook echoe `attackAbility` (correctif #375), ce qui rend la
# prochaine fenetre de reinject auto-verifiante.

_INSTEPS_EXPECT = {1103: "gate", 1054: "gate", 1247: "no-override"}

_INSTEPS_REASON = {
    1103: "gate IsMeleeAttack/IsRegularAttack : le UtilityAttackCase ne nomme aucune ability",
    1054: "gate IsRegularAttack : le UtilityAttackCase ne nomme aucune ability",
    1247: "FuryOfTheAncientsPlaybook ne surcharge pas la voie ATTAQUE (corps de base = un 0)",
}

INSTEPS_ANOMALY = ("#375 FORME INATTENDUE : ability %d via attackUtilityInSteps rend"
                   " capturedCount=%r triggeredUtilities=%r -- attendu 0 / [0] (le natif yielde un"
                   " seul Fix64(0) : %s).")

INSTEPS_STILL_MUTE = ("#375 REGRESSION : le hook echoe attackAbility=%r (le case NOMME une ability)"
                      " mais ability %d via attackUtilityInSteps rend toujours capturedCount=%r --"
                      " la gate IsRegularAttack aurait du passer.")


def check_insteps_shape(resp: dict, ability_id: int) -> dict:
    """Verdict sur la FORME de la reponse `attackUtilityInSteps`. Pur, testable sans plateforme."""
    if "abilityKind" not in resp:
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    if resp.get("error"):
        return {"status": "rpc-error",
                "message": "#375 ability %d via attackUtilityInSteps a rendu une erreur: %s"
                           % (ability_id, str(resp.get("error"))[:200])}
    n = resp.get("capturedCount")
    utils = resp.get("triggeredUtilities")
    named = resp.get("attackAbility")
    kind = _INSTEPS_EXPECT.get(ability_id, "gate")
    if named in (None, {}, "") or kind == "no-override":
        if n == 0 and utils == [0]:
            return {"status": "mute-expected", "message": None,
                    "reason": _INSTEPS_REASON.get(ability_id, "?")}
        return {"status": "anomaly",
                "message": INSTEPS_ANOMALY % (ability_id, n, utils,
                                              _INSTEPS_REASON.get(ability_id, "?"))}
    if isinstance(n, int) and n >= 1:
        return {"status": "captured", "message": None, "reason": "case NOMME une ability"}
    return {"status": "anomaly", "message": INSTEPS_STILL_MUTE % (named, ability_id, n)}


def step3_live(verbose: bool = True, keep: bool = False) -> dict:
    resolve_session, rpc = _rpc_mod()
    sid = resolve_session()
    fx = _FIXTURE_REGIME
    state = ROOT / "logs" / "probe369" / "runner-369.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    seed_bc = ROOT / "logs" / "probe369" / "seed-bc-regime.json"
    # TOUJOURS re-ecrite : c'est elle qui pose le sidecar d'epinglage (#375). Reutiliser un
    # fichier ecrit avant le correctif remonterait une fixture sans epingle, donc INERTE.
    build_regime_seed_bc(seed_bc)
    rid = _build(state, fx, seed_bc, extra=("--armor-target", fx["armor_target"]))
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
            shape = check_insteps_shape(resp, aid)
            results.append({"ability": aid, "name": trg_name, "expected": pb,
                            "playbookClass": resp.get("playbookClass"),
                            "rpcError": resp.get("error"),
                            "capturedCount": resp.get("capturedCount"),
                            "triggeredUtilities": resp.get("triggeredUtilities"),
                            "attackAbility": resp.get("attackAbility"),
                            "captured": resp.get("captured"),
                            "shape": shape["status"], "shapeMessage": shape["message"],
                            "shapeReason": shape.get("reason"),
                            **verdict})
    finally:
        if not keep:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                        # noqa: BLE001
                pass
    not_reinjected = any(r["status"] == "not_reinjected" for r in results)
    failed = [r for r in results
              if r["status"] == "mismatch" or r["shape"] in ("anomaly", "rpc-error")]
    if verbose:
        print("[369/3] oracle LIVE (runner %d, %s)" % (rid, fx["board"]))
        for r in results:
            print("  %-5d %-24s -> %-32s %s" % (
                r["ability"], r["name"], r["playbookClass"] or "<none>", r["status"].upper()))
            if r["message"]:
                print("      %s" % r["message"])
            if r["rpcError"]:
                print("      rpc error: %s" % str(r["rpcError"])[:180])
            print("      inSteps: capturedCount=%s utilities=%s -> %s%s"
                  % (r["capturedCount"], r["triggeredUtilities"], r["shape"].upper(),
                     (" (" + r["shapeReason"] + ")") if r.get("shapeReason") else ""))
            if r["shapeMessage"]:
                print("      %s" % r["shapeMessage"])
        if not_reinjected:
            print("  -> NON CONFRONTE (hook non reinjecte)")
        else:
            print("  -> %s" % ("OK" if not failed else "ECHEC"))
    return {"ok": not failed, "confronted": not not_reinjected,
            "runner": rid, "results": results}


# --- etape 4 (#375) : LIVE, la face DEMI-VERS-LE-PAIR confrontee ---------------------------------
#
# POURQUOI `attackUtilityForMainTarget` ET PAS `attackUtilityInSteps`. Les deux sont des call-sites
# NATIFS ; le second ne peut pas construire de `ProbableDamageEvent` tant que le case ne nomme pas
# d'ability (cf. etape 3bis). Le premier, lui, n'a AUCUNE gate :
# `IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForMainTarget` va droit a
# `MassiveScythingTalonsAbility$$GetAverageDamage` -> `<IAmountFormula slot 1 = Calculate>`
# (= DEMI-VERS-LE-PAIR) -> `<IBattleQuery slot 0x28 = GetMultiHitAttackPrediction>` -> `ProbableDamageEvent
# $$.ctor`. Et c'est exactement le call-site que `...u003Ed__2$$MoveNext` appelle lui-meme.
#
# POURQUOI TROIS MONTAGES. La valeur demi-vers-le-pair n'apparait PAS telle quelle dans `captured` :
# elle entre par l'argument `damage` de `GetAttackPrediction`, que l'etage aval transforme. On ne
# peut donc pas lire « 972 » ; on lit une SIGNATURE, et on la compare a DEUX references mesurees sur
# la meme geometrie -- une ou les deux formes valent 971, une ou elles valent 972. Si ces deux
# references sont EGALES, l'etage aval ecrase l'ecart et la mesure ne conclut RIEN : c'est NON
# CONFRONTE, jamais vert. (Mesure du 2026-07-31 : a l'armure NOMINALE de `necroWarden` elles sont
# egales -- 175/175 ; a `--armor-target 0` elles se separent -- 1166 vs 1167.)

_CAPTURE_KEYS = ("healthDmgMin", "healthDmgMax", "shieldDmgMin", "shieldDmgMax",
                 "totalDmgMin", "totalDmgMax", "willKillDmg", "mightKillDmg")

HALF_EVEN_NOT_OBSERVABLE = (
    "#375 NON CONFRONTE : les references 971 et 972 rendent la MEME prediction %s -- l'etage aval"
    " (profil de degat x armure) ecrase l'ecart de 1. Rien n'est mesure ; ne pas lire ce run comme"
    " un accord.")

HALF_EVEN_TRUNCATED = (
    "#375 ECHEC : sur le regime discriminant (minDmg+maxDmg == 3 mod 4) la prediction capturee %s"
    " est celle de la TRONCATURE (971), pas du demi-vers-le-pair (972 -> %s)."
    " `AAmountFormula$$RoundFix64Result` / `Fix64.Round` n'est donc pas la forme jouee.")

HALF_EVEN_UNKNOWN = (
    "#375 ECHEC : la prediction du regime discriminant %s ne coincide avec AUCUNE des deux"
    " references (971 -> %s, 972 -> %s) -- le montage a bouge entre les trois builds.")

HALF_EVEN_NO_CAPTURE = (
    "#375 NON CONFRONTE : `via: attackUtilityForMainTarget` rend capturedCount=%r sur le montage"
    " %s -- le capteur ProbableDamageEvent$$.ctor n'a rien vu la ou le decompile l'appelle"
    " DIRECTEMENT. error=%s")


def capture_fingerprint(resp: dict):
    """Signature comparable d'UNE prediction capturee. `None` si rien n'a ete capture."""
    cap = resp.get("captured") or []
    if not cap:
        return None
    return tuple(cap[0].get(k) for k in _CAPTURE_KEYS)


def check_half_even(low, test, high, trunc: int, half_even: int) -> dict:
    """Verdict de l'echelle. Pur, donc testable sans plateforme."""
    if low is None or test is None or high is None:
        return {"status": "no-capture", "message": None}
    if low == high:
        return {"status": "not-observable", "message": HALF_EVEN_NOT_OBSERVABLE % (low,)}
    if test == high:
        return {"status": "ok", "message": None, "value": half_even}
    if test == low:
        return {"status": "truncated",
                "message": HALF_EVEN_TRUNCATED % (test, half_even), "value": trunc}
    return {"status": "unknown", "message": HALF_EVEN_UNKNOWN % (test, low, high)}


def _measure_regime(rpc, sid, tag: str, max_dmg: int, keep: bool) -> dict:
    fx = _FIXTURE_REGIME
    out = ROOT / "logs" / "probe369"
    out.mkdir(parents=True, exist_ok=True)
    seed_bc = out / ("seed-bc-%d-%d.json" % (fx["min_dmg"], max_dmg))
    forms = build_regime_seed_bc(seed_bc, max_dmg)
    state = out / ("runner-369-%d.json" % max_dmg)
    rid = _build(state, fx, seed_bc, extra=("--armor-target", fx["armor_target"]))
    try:
        dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32},
                180)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if u.get("visualId") == fx["carrier"]), None)
        victim = next((u for u in units
                       if caster and u.get("team") != caster.get("team")), None)
        if caster is None or victim is None:
            raise RuntimeError("montage : caster %r ou cible absente du decisionView"
                               % fx["carrier"])
        resp = _r(rpc, sid, "ncPlaybookPredict", {
            "runnerId": rid, "unitId": int(caster["id"]), "targetId": int(victim["id"]),
            "abilityType": fx["ability_id"], "abilityKind": "triggered",
            "via": "attackUtilityForMainTarget", "hits": 1}, 240)
    finally:
        if not keep:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                        # noqa: BLE001
                pass
    return {"tag": tag, "runner": rid, "max_dmg": max_dmg, "roundtrip": forms["roundtrip"],
            "trunc": forms["trunc"], "half_even": forms["half_even"],
            "sum_mod_4": forms["sum_mod_4"], "playbookClass": resp.get("playbookClass"),
            "capturedCount": resp.get("capturedCount"), "error": resp.get("error"),
            "fingerprint": capture_fingerprint(resp),
            "utility": resp.get("triggeredUtilityTotal")}


def step4_half_even(verbose: bool = True, keep: bool = False) -> dict:
    resolve_session, rpc = _rpc_mod()
    sid = resolve_session()
    fx = _FIXTURE_REGIME
    runs = [_measure_regime(rpc, sid, "REF 971", fx["max_low"], keep),
            _measure_regime(rpc, sid, "TEST", fx["max_dmg"], keep),
            _measure_regime(rpc, sid, "REF 972", fx["max_high"], keep)]
    low, test, high = (r["fingerprint"] for r in runs)
    verdict = check_half_even(low, test, high, runs[1]["trunc"], runs[1]["half_even"])
    if verdict["status"] == "no-capture":
        miss = next(r for r in runs if r["fingerprint"] is None)
        verdict = {"status": "no-capture",
                   "message": HALF_EVEN_NO_CAPTURE % (miss["capturedCount"], miss["tag"],
                                                      str(miss["error"])[:200])}
    if verbose:
        print("[369/4] face DEMI-VERS-LE-PAIR (via attackUtilityForMainTarget, armure cible = %s)"
              % fx["armor_target"])
        for r in runs:
            print("  %-8s minDmg=%s maxDmg=%s (somme %% 4 = %d) trunc=%d half=%d"
                  " | n=%s fp=%s"
                  % (r["tag"], r["roundtrip"]["min_dmg"], r["roundtrip"]["max_dmg"],
                     r["sum_mod_4"], r["trunc"], r["half_even"],
                     r["capturedCount"], r["fingerprint"]))
            if r["error"]:
                print("      rpc error: %s" % str(r["error"])[:180])
        if verdict["message"]:
            print("  %s" % verdict["message"])
        print("  -> %s" % {"ok": "OK (972, demi-vers-le-pair)", "truncated": "ECHEC",
                           "not-observable": "NON CONFRONTE", "unknown": "ECHEC",
                           "no-capture": "NON CONFRONTE"}[verdict["status"]])
    confronted = verdict["status"] in ("ok", "truncated", "unknown")
    return {"ok": verdict["status"] == "ok", "confronted": confronted,
            "status": verdict["status"], "message": verdict["message"], "runs": runs}


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
        for name, fn in (("step3", step3_live), ("step4", step4_half_even)):
            try:
                out[name] = fn(v, keep=args.keep)
            except Exception as exc:                                 # noqa: BLE001
                out[name] = {"ok": False, "confronted": True, "error": str(exc)}
            st = out[name]
            # NON CONFRONTE (rc 2) n'est PAS un echec : c'est « rien n'a ete mesure ». Un ECHEC
            # (rc 1) est une mesure qui CONTREDIT le decompile -- les deux ne se confondent pas.
            if st.get("ok"):
                if not st.get("confronted") and rc == 0:
                    rc = 2
            elif st.get("confronted"):
                rc = 1
            elif rc == 0:
                rc = 2
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
