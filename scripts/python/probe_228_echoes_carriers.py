#!/usr/bin/env python
"""#228 -- ventilation des PORTEURS d'`EchoesFromTheWarp` (1219 / effet 1284 `EchoesFromTheWarp_Revive`).

QUESTION : la branche `StatAmount(src, Health, max)` du fork d'`amount` de
`IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` a-t-elle un porteur
CONFRONTABLE en runner ? (L'autre branche, `Direct(GetVariableForLevel(config, 0x1d = 'hp'))`, est
celle de `TimeFlux_Revive` 1186 -- portee et validee live par #213.)

REPONSE MESUREE (2026-07-29) : **NON -- NON PERTINENT**. Un seul porteur dans tout le parc,
`thousNpc4Terminator` (« Scarab Occult Terminator », ThousandSons), bucket **npc** :
  * absent de `--list-pool` (rank 17 : 97 unites regulieres + 8 MoW) ;
  * **aucun summoner** -- 0 des 559 abilities du gameconfig ne cite son id (ses 308 occurrences dans
    le gameconfig sont des `waves[].army` de campagne PvE, pas des aretes de summon) ;
  * meme injecte au catalogue `BC.Units` par `catalog_inject.py`, **refuse par le natif**
    `IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` a TOUS les ranks 0..20
    (`v2 patch: system error`). CONTRE-EPREUVE indispensable, faite : `thousDaemonPrince` injecte par
    le MEME outil dans le MEME seed BC ENTRE dans `normalized` -> le refus est une propriete de
    l'unite, pas de la voie d'injection.

CAUSE DU REFUS -- LUE au decompile, pas deduite (la deduction « le NPC n'a pas de table de
progression » est FAUSSE et ce probe la refute) :

    if (ContainsIndex(<cfg+0x40>+0x80 /* ou +0x88 si isMow */, progressionIndex))
         v = list[progressionIndex]+0x28;          // <- branche qui NE THROW PAS (index absent -> 0)
    else v = 0;
    Dictionary.get_Item(<cfg+0x40>+0x10, unitId);  // <- L'EXCEPTION EST ICI (KeyNotFound)

C'est un lookup PAR UNITID. Le hook (`frida/hooks/features/normalize-bc/json-build.ts`) ne passe a la
formule que `(unitId, isMow, rank, progressionIndex, items)` -- JAMAIS le bloc `UnitConfiguration`
injecte. Donc AUCUN enrichissement du seed BC ne peut lever ce refus. `--buckets` le confirme par
prediction : `lineup` -> True ; `npc` et `summons` -> False.

⚠ NE PAS CONFONDRE avec le « system error » de #226 (`case-220/blood-angels`), qui a une tout autre
cause et est, LUI, reparable : celui-la est leve par `AbilityConfiguration$$GetVariableForLevel` AU
CAST parce que `BC.Abilities` n'a pas la config de l'ability (`catalog_inject` la pose desormais).
Le notre est leve A LA NORMALISATION, avant tout spawn. Meme libelle (`system error` = exception
managee remontee par l'invoke IL2CPP), diagnostics opposes : distinguer par l'APPELANT.

Le domaine de la branche est par ailleurs FERME au decompile (`classes.tsv` / `enums.tsv`) :
`GhostReviveAbility` a EXACTEMENT deux sous-classes (`TimeFluxReviveAbility` 0x4a2 = 1186 ->
branche 'hp' ; `EchoesFromTheWarpAbility` 0x504 = 1284 -> cette branche), `GhostEffect` n'en a AUCUNE,
et les seuls `EffectType` du couple sont 1186 / 1284. Aucun autre chemin n'atteint `StatAmount`.

=> pas de port (un port sans porteur spawnable serait invalidable, donc speculatif).
Detail : `docs/rl/case-66-revive-in-place.md` §8.4.

CE PROBE RE-DERIVE TOUT -- ne pas recopier les chiffres ci-dessus, les recalculer. Ce qui rouvrirait
la fiche apparaitrait ici : le porteur promu jouable (il entrerait dans `--list-pool`), ou une 3e
sous-classe de `GhostReviveAbility`.

USAGE
    python probe_228_echoes_carriers.py
    python probe_228_echoes_carriers.py --seed-bc <bc.json>            # + verdict natif au rank 17
    python probe_228_echoes_carriers.py --seed-bc <bc.json> --ranks    # + balayage rank 0..20
    python probe_228_echoes_carriers.py --seed-bc <bc.json> --buckets  # + generalisation par bucket
    # le seed BC se fabrique par (les ids de --buckets doivent y etre injectes) :
    #   python catalog_inject.py --units thousNpc4Terminator,necroNpc1Warrior,ultraSmnInceptor,\
    #       necroSmnSwarm,thousDaemonPrince --out <abs>.json

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import gameconfig as GC

ABILITY = "EchoesFromTheWarp"
# Unite de CONTROLE de la contre-epreuve : un hero/MoW absent du seed BC que `catalog_inject`
# debloque REELLEMENT. Sans elle, un `buildNormalizedBC` qui refuse le porteur ne prouve rien --
# ce pourrait etre l'outil d'injection qui produit une entree invalide.
CONTROL_UNIT = "thousDaemonPrince"
RANKS = (0, 1, 3, 5, 8, 11, 14, 17, 19, 20)
# `--buckets` : PREDICTION issue de la lecture du decompile (lookup par unitId dans un Dictionary qui
# ne couvre que le roster JOUEUR). Si elle tombe, c'est la lecture qui est fausse -- pas le contraire.
BUCKET_SAMPLE = ("thousNpc4Terminator", "necroNpc1Warrior",      # npc      -> attendu False
                 "ultraSmnInceptor", "necroSmnSwarm",           # summons  -> attendu False
                 "thousDaemonPrince")                            # lineup   -> attendu True
BUCKET_EXPECTED = {"lineup": True, "npc": False, "summons": False}


def _units_with(passive: str):
    """Toutes les unites du gameconfig (lineup + npc + summons) dont le kit cite `passive`.
    Les trois buckets sont des DICTS keyes par unitId (cf. `gameconfig._index`)."""
    idx = GC._index()
    out = []
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            names = []
            for key in ("passiveAbilities", "activeAbilities", "abilities"):
                v = u.get(key)
                if isinstance(v, list):
                    names += [x for x in v if isinstance(x, str)]
                elif isinstance(v, dict):
                    names += [x for x in v.keys() if isinstance(x, str)]
            hit = [n for n in names if passive in n]
            if hit:
                out.append({"id": uid, "bucket": bucket, "hits": hit,
                            "faction": u.get("FactionId") or u.get("faction") or ""})
    return out


def _pool():
    """Pool natif spawnable -- `rl_duel.py build --list-pool` (le sous-commande `build` est
    OBLIGATOIRE : sans lui argparse sort en rc=2 et la liste est vide, ce qui se lit a tort comme
    « le porteur n'y est pas »)."""
    here = Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, str(here / "rl_duel.py"), "build", "--list-pool"],
                       capture_output=True, text=True, cwd=str(here))
    return p.stdout, p.returncode


def _summoners_of(unit_id: str):
    """Abilities du gameconfig dont une constante cite `unit_id` -- le graphe summon
    (`constants.unitId*` / `unitIds` / `unitToSpawn`). Vide => le porteur n'est PAS un summon,
    donc la porte SUMMON du gate de confrontabilite est fermee elle aussi."""
    idx = GC._index()
    return [aid for aid, a in idx["abilities"].items() if unit_id in json.dumps(a)]


def _normalize_verdict(seed_bc_path: str, unit_id: str, rank: int = 17):
    """Verdict NATIF : `buildNormalizedBC` accepte-t-il `unit_id` au rank donne ?

    C'est la porte que `--list-pool` expose (`result.normalized` = les unites qui passent
    `IStatsFormula.StatsUsingProgressionIndexFor`) ; `result.skipped[].reason` dit POURQUOI une
    entree du catalogue `BC.Units` n'y entre pas. On interroge le RPC directement plutot que de
    conclure d'une simple absence de la liste."""
    from rl_collect_batch import _resolve_session, _rpc, _load_seed_bc
    sid = _resolve_session()
    bc = _load_seed_bc(seed_bc_path)
    args = {"baseBcJson": json.dumps(bc), "targetRank": rank, "targetProgressionIndex": rank,
            "targetRarity": 5, "targetLevel": 50, "targetStarLevel": 5, "targetAbilityLevel": 50}
    out = _rpc(sid, "buildNormalizedBC", [args], timeout=60).get("result") or {}
    norm = set(out.get("normalized") or [])
    skipped = {s.get("unitId"): s.get("reason") for s in (out.get("skipped") or [])}
    return {"ok": bool(out.get("ok")), "in_normalized": unit_id in norm,
            "skip_reason": skipped.get(unit_id), "normalized_count": len(norm),
            "skipped_count": len(skipped)}


def _arg(flag: str):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    carriers = _units_with(ABILITY)
    print("== porteurs gameconfig de %s ==" % ABILITY)
    for c in carriers:
        print("  %-22s bucket=%-8s faction=%-16s hits=%s"
              % (c["id"], c["bucket"], c["faction"], ",".join(c["hits"])))
    if not carriers:
        print("  (aucun)")
    print()

    out, rc = _pool()
    print("== rl_duel build --list-pool (rc=%d) ==" % rc)
    ids = [c["id"] for c in carriers]
    hits = [l.strip() for l in out.splitlines()
            if any(i and i.lower() in l.lower() for i in ids)]
    for h in hits:
        print("  POOL HIT: %s" % h)
    if not hits:
        print("  AUCUN porteur dans le pool -> porte HERO/MoW FERMEE")
    # La sortie de `rl_duel` contient du non-ASCII (tiret cadratin, accents) -> on ne la relaie
    # JAMAIS telle quelle vers stdout (cp1252 leve `UnicodeEncodeError`) : on en extrait des compteurs.
    # Critere STRUCTUREL (pas une liste de prefixes de faction, qui sous-compterait en silence a la
    # premiere faction oubliee) : `rl_duel` imprime un unitId par ligne INDENTEE, ses en-tetes
    # commencent par `[`. Les unitId sont ASCII, les en-tetes non -> on filtre aussi la-dessus.
    reg = [l.strip() for l in out.splitlines()
           if l[:1].isspace() and l.strip() and not l.strip().startswith("[")
           and l.strip().isascii()]
    print("  pool regulier lu: %d entrees" % len(reg))
    print()

    print("== graphe summon (qui spawne le porteur ?) ==")
    for c in carriers:
        s = _summoners_of(c["id"])
        print("  %-22s summoners=%s" % (c["id"], s if s else "AUCUN -> porte SUMMON FERMEE"))
    print()

    seed = _arg("--seed-bc")
    if not seed:
        print("(pas de --seed-bc : verdict natif non evalue ; cf. USAGE dans la docstring)")
        return
    ranks = RANKS if "--ranks" in sys.argv else (17,)
    print("== verdict natif buildNormalizedBC (seed BC = %s) ==" % seed)
    for c in carriers:
        for r in ranks:
            v = _normalize_verdict(seed, c["id"], rank=r)
            print("  %-22s rank=%-2d in_normalized=%-5s reason=%s (norm=%d, skipped=%d)"
                  % (c["id"], r, v["in_normalized"], v["skip_reason"],
                     v["normalized_count"], v["skipped_count"]))
    # CONTRE-EPREUVE : le controle doit passer sur CE MEME seed BC, sinon un refus ne prouve rien.
    v = _normalize_verdict(seed, CONTROL_UNIT, rank=17)
    print("  [controle] %-12s rank=17 in_normalized=%s  <- doit valoir True si %s est injecte"
          % (CONTROL_UNIT, v["in_normalized"], CONTROL_UNIT))

    if "--buckets" not in sys.argv:
        return
    print()
    print("== generalisation par bucket (la porte est-elle le BUCKET ?) ==")
    idx = GC._index()
    bad = 0
    for uid in BUCKET_SAMPLE:
        bucket = next((b for b in ("lineup", "npc", "summons") if uid in idx[b]), "?")
        got = _normalize_verdict(seed, uid, rank=17)["in_normalized"]
        exp = BUCKET_EXPECTED.get(bucket)
        ok = (exp is None) or (got == exp)
        bad += 0 if ok else 1
        print("  %-22s bucket=%-8s in_normalized=%-5s attendu=%-5s %s"
              % (uid, bucket, got, exp, "OK" if ok else "*** PREDICTION FAUSSE ***"))
    print("  -> %s" % ("prediction tenue : la porte est le BUCKET (lineup seul), pas le bloc BC"
                       if bad == 0 else
                       "%d ecart(s) : la lecture du decompile est a refaire" % bad))


if __name__ == "__main__":
    main()
