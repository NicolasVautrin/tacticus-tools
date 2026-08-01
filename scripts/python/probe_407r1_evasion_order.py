#!/usr/bin/env python
"""probe #407-r1 -- l'ESQUIVE precede le BLOCK : ce que l'ordre change, et quand.

QUESTION (binaire) : entre le modele PORTE avant #407-r1 (evasion et block MUTUELLEMENT
EXCLUSIFS, drapeau `evasion_branch` toujours `False` -> le block seul) et le modele NATIF
(esquive d'abord, block ensuite, et l'esquive n'ecarte le block que si elle REUSSIT), y a-t-il un
regime ou les deux DIVERGENT -- et ce regime est-il atteignable ?

RE (decompile = verite, rnca9r7q6c), corps d'`IdunBattle.Core.Services.DamagePrediction$$
CalculateDamageOperation`, slots d'`IDamageCalculations` :

    blockChances  = slot 0   CalculateBlockChances(attacker, defender, failedBlockIds)   # 0 RNG
    evasionChance = slot 1   CalculateEvasionChance(attacker, defender)                  # 0 RNG
    shieldPart    = slot 0xc CalculateDamageBlockedByShield(shield, damage)              # 0 RNG
    rest          = Math.Max(0, damage - shieldPart)
    if damageInfo[+0x1E] == 0:               # trait de profil : saute block ET esquive
        if damageInfo[+0x1D] == 0:           # pas de block GARANTI
            ev   = slot 3 ApplyRandomEvasion(evasionChance, rest, attacker, defender)
            if !ev.didEvade:  bd = slot 2 ApplyRandomBlockDamage(blockChances, rest)
        else: rest = slot 4 ApplyBlockDamage(blockChances, rest)   # AUCUN tirage

Il n'existe donc AUCUN drapeau XOR « block vs evasion » : c'est une SEQUENCE. Et l'octet que le
port citait comme tel (`uStack_5b0>>0x28`) est `damageInfo[+0x1D]`, le block GARANTI.

DEUX CONTREFACTUELS, parce que les deux fautes possibles ne se voient PAS dans le meme regime :

  * `--mutate legacy` = le port d'AVANT #407-r1 : l'esquive n'est JAMAIS evaluee, on va droit au
    block. A `evasion_chance == 0` c'est BIT-EXACT identique au port livre (l'esquive ne consomme
    rien) ; des `evasion_chance > 0` il DIVERGE -- 1 `next_bool` de moins, tout le flux decale.
    => discriminant du seul axe ORDRE, dans un regime que le jeu n'atteint pas (cf.
       `probe_407r1_evasion_carriers.py` : aucun porteur sur 5 voies).
  * `--mutate xor` = `block_runs_after_evasion` rendu toujours `False` : l'esquive est evaluee mais
    le block n'est PLUS JAMAIS atteint. Diverge des qu'une source de block existe, MEME a
    `evasion_chance == 0`.
    => discriminant SANS porteur d'esquive : c'est LUI que la garde live peut jouer.

L'observable est la FENETRE de coups (per_hit + rolls + tirages consommes), jamais un point : le
tirage en trop/en moins est consomme APRES le `GetDamage`/resolve du coup courant, donc c'est le
coup SUIVANT qui bouge (piege mesure de #407 : 0/5 seeds discriminants a l'index 0, 5/5 sur la
fenetre).

100 % offline : aucun runner, aucun RPC. Sortie ASCII (cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from engine.runner.operations.damage_hits import HitDamage, _DamageHitsMixin  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402
from engine.services import damage_combat as DC  # noqa: E402
from engine.runner.operations import damage_hits as DH  # noqa: E402

# Montage synthetique : plusieurs coups, une source de block qui ECHOUE souvent (chance basse ->
# elle entre dans la failed-list et s'eteint), bornes larges pour que chaque `GetDamage`/resolve
# consomme un tirage bien visible.
HITS = 6
BOUNDS = (900, 1100)


def _sources(chance: int, amount: int, n: int = 2):
    """n sources de block INDEPENDANTES (ids distincts) : la chaine `ApplyRandomBlockDamage` en
    tire une par une jusqu'a la 1re REUSSITE, donc plusieurs sources = plusieurs tirages a decaler."""
    return [DC.BlockSource(chance=chance, amount=amount, block_id=100 + i) for i in range(n)]


def run_window(seed: int, evasion_chance: int, model: str, block_chance: int = 25,
               block_amount: int = 40) -> dict:
    """Rejoue la MEME fenetre de coups sur le MEME flux RNG, sous le modele demande."""
    rng = IntBasedMersenneTwister(seed)
    orig_cdo, orig_gate = DH.calculate_damage_operation, DC.block_runs_after_evasion
    try:
        if model == "legacy":
            def _legacy(raw_dmg, *, shield=0, armor_pool=0, armor_pct=0, block_sources=None,
                        evasion_chance=0, rng=None):
                """Le port d'AVANT #407-r1, verbatim : `if evasion_branch: ... elif block: ...`
                avec `evasion_branch` TOUJOURS `False` cote appelant -> l'esquive n'est jamais
                evaluee et ne consomme rien, quelle que soit `evasion_chance`."""
                d = DC.Damage()
                remaining = raw_dmg
                if shield > 0:
                    d.shield = DC.calculate_damage_blocked_by_shield(remaining, shield)
                    remaining -= d.shield
                if armor_pool > 0 and armor_pct > 0:
                    d.armor = min(armor_pool,
                                  DC.calculate_damage_blocked_by_armor(remaining, armor_pct))
                    remaining -= d.armor
                if rng is not None and block_sources:
                    bd = DC.apply_random_block_damage(rng, block_sources, remaining)
                    d.did_block = bd.did_block
                    d.failed_block_ids = bd.failed_block_ids
                    remaining = bd.damage
                d.health = max(0, remaining)
                return d
            DH.calculate_damage_operation = _legacy
        elif model == "xor":
            DC.block_runs_after_evasion = lambda _did_evade: False
        elif model != "shipped":
            raise SystemExit("modele inconnu: %s" % model)

        # Le port livre n'expose pas encore `evasion_chance` a `_run_hits` (aucun porteur) : on le
        # FORCE ici, sur le seul etage concerne, en enveloppant l'appel du split combat. C'est la
        # SEULE chose que ce probe injecte -- le reste du coup est le port, inchange.
        inner = DH.calculate_damage_operation

        def _with_evasion(raw_dmg, **kw):
            kw["evasion_chance"] = evasion_chance
            return inner(raw_dmg, **kw)
        DH.calculate_damage_operation = _with_evasion

        r = _DamageHitsMixin._run_hits(
            rng, HitDamage(*BOUNDS), HitDamage(*BOUNDS), crit_chance=0, crit_enabled=False,
            hits=HITS, block_sources=_sources(block_chance, block_amount))
        return {"per_hit": list(r["per_hit"]), "rolls": list(r["rolls"]),
                "did_block": r["did_block"], "did_evade": r["did_evade"],
                "draws": rng.call_count, "failed": sorted(r["failed_block"])}
    finally:
        DH.calculate_damage_operation = orig_cdo
        DC.block_runs_after_evasion = orig_gate


def compare(seed: int, evasion_chance: int, block_chance: int, block_amount: int) -> dict:
    ship = run_window(seed, evasion_chance, "shipped", block_chance, block_amount)
    leg = run_window(seed, evasion_chance, "legacy", block_chance, block_amount)
    xor = run_window(seed, evasion_chance, "xor", block_chance, block_amount)
    return {"seed": seed, "ev": evasion_chance, "shipped": ship, "legacy": leg, "xor": xor,
            "legacy_diverges": (ship["per_hit"] != leg["per_hit"]
                                or ship["draws"] != leg["draws"]),
            "xor_diverges": (ship["per_hit"] != xor["per_hit"]
                             or ship["draws"] != xor["draws"])}


def main() -> int:
    ap = argparse.ArgumentParser(description="#407-r1 : l'ordre esquive->block")
    ap.add_argument("--seeds", default="12345,314159,88,777,31337,2026")
    ap.add_argument("--evasions", default="0,20,50",
                    help="valeurs de `evasionChance` a balayer (0 = le regime REEL du jeu)")
    ap.add_argument("--block-chance", type=int, default=25)
    ap.add_argument("--block-amount", type=int, default=40)
    a = ap.parse_args()

    seeds = [int(s) for s in a.seeds.split(",") if s]
    evs = [int(s) for s in a.evasions.split(",") if s != ""]
    print("=== #407-r1 : ordre esquive->block, %d seeds x %d regimes d'evasion ==="
          % (len(seeds), len(evs)))
    print("montage: %d coups, bornes %s, %d sources de block (chance=%d amount=%d)"
          % (HITS, BOUNDS, 2, a.block_chance, a.block_amount))
    print()
    tally = {}
    for ev in evs:
        n_leg = n_xor = n_same = 0
        for seed in seeds:
            m = compare(seed, ev, a.block_chance, a.block_amount)
            n_leg += int(m["legacy_diverges"])
            n_xor += int(m["xor_diverges"])
            n_same += int(not m["legacy_diverges"])
            if seed == seeds[0]:
                print("[ev=%d seed=%d] livre   per_hit=%s draws=%d block=%s evade=%s"
                      % (ev, seed, m["shipped"]["per_hit"], m["shipped"]["draws"],
                         m["shipped"]["did_block"], m["shipped"]["did_evade"]))
                print("               legacy  per_hit=%s draws=%d"
                      % (m["legacy"]["per_hit"], m["legacy"]["draws"]))
                print("               xor     per_hit=%s draws=%d"
                      % (m["xor"]["per_hit"], m["xor"]["draws"]))
        tally[ev] = (n_leg, n_xor, n_same, len(seeds))
        print("[ev=%d] legacy diverge %d/%d | xor diverge %d/%d | legacy IDENTIQUE %d/%d"
              % (ev, n_leg, len(seeds), n_xor, len(seeds), n_same, len(seeds)))
        print()
    print("LECTURE :")
    print("  ev=0   -> legacy doit etre IDENTIQUE (l'esquive ne consomme rien) et xor DIVERGER")
    print("            => le port livre ne change RIEN a ce que le jeu atteint reellement,")
    print("               et la garde live a un contrefactuel qui casse.")
    print("  ev>0   -> legacy doit DIVERGER => l'ordre porte a bien un effet, dans un regime")
    print("            que le jeu n'atteint pas (NON CONFRONTE, cf. probe_407r1_evasion_carriers).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
