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
    `IStatsFormula.StatsUsingProgressionIndexFor` a TOUS les ranks 0..20 (`v2 patch: system error`).
    CONTRE-EPREUVE indispensable, faite : `thousDaemonPrince` injecte par le MEME outil dans le MEME
    seed BC ENTRE dans `normalized` -> le refus est une propriete du NPC, pas de la voie d'injection.

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
    python probe_228_echoes_carriers.py --seed-bc <bc.json>          # + verdict natif au rank 17
    python probe_228_echoes_carriers.py --seed-bc <bc.json> --ranks  # + balayage rank 0..20
    # le seed BC porteur se fabrique par :
    #   python catalog_inject.py --units thousNpc4Terminator --out <abs>.json

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


if __name__ == "__main__":
    main()
