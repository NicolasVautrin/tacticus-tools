"""probe #217 -- ROUTAGE de ciblage du generateur d'actions offline : le moteur genere-t-il des
paires (ability, cible) que le natif REFUSE ?

CRITERE BINAIRE (cliquet) : aucune ability dont le masque `TargetingOptions` RE-LU REFUSE toute
cible ennemie (`TargetIsFriendly` / `TargetIsCaster`, cf.
`engine.runner.abilities.targeting.refuses_all_enemy_targets`) ne doit etre routee vers les ENNEMIS
par `engine.ai.state_bridge._is_attack_ability`. Sortie != 0 si le cliquet casse.

POURQUOI c'est un probleme de ROUTAGE et pas d'utilite : le generateur offline
`state_bridge._plans_for_unit` construit ses tuiles legales par la SEULE distance hex
(`hexgeo.distance <= _ability_reach`), alors que son homologue natif
`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` filtre CHAQUE tuile candidate :

    reason = AttackQuery.GetInvalidTargetReason(unit, new UnitPosition(tile), target, ability);
    if (IBrokenTargetingRuleExtensions.IsInvalid(reason)) continue;

Une ability `TargetIsFriendly` rompt sur TOUS les ennemis -> le natif ne rend AUCUNE tuile, donc
AUCUNE paire (ability, ennemi) ; le moteur, lui, en fabriquait une par ennemi.

INVENTAIRES annexes (mesures, PAS des cliquets -- ce sont des residus documentes) :
  * DOMAINE : ability routee vers des UNITES ennemies alors que son masque est TILE-targeting
    (`get_IsTileTargeting`) -- le natif enumere des TUILES (`GetPossibleTargetsForOptions`), pas des
    unites. Non corrige : les playbooks NonComparable deja portes consomment `ability_targets` sous
    la forme « unites ennemies » ; basculer le domaine est un chantier separe.
  * SOUS-GENERATION : masque avec bit ennemi mais ability NON routee (aucun `damageProfile`). Le
    veto est volontairement SOUSTRACTIF : il ne promeut jamais vers la route ennemie.
  * MASQUE INCONNU : ability hors des deux sources de masque -> non decidable offline.

Usage : python probe_217_phantom_action_routing.py [--verbose]
ASCII only.
"""
from __future__ import annotations

import sys

import gameconfig as GC
import enum_maps as EM
from engine.ai.state_bridge import _is_attack_ability, _resolve_ability, _ability_kind
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (
    TARGETING_OPTIONS_UNPORTED, refuses_all_enemy_targets, targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR


def _castable_ability_ids() -> dict:
    """{abilityId: [visualId, ...]} des actives declarees par une unite du gameconfig (l'univers
    reellement atteignable en bataille), id resolu par reverse-lookup `ACTIVE_ABILITY_TYPE`."""
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    out: dict = {}
    all_ids = [v for group in GC.all_unit_ids().values() for v in group]
    for vid in all_ids:
        for key in ((GC.unit(vid) or {}).get("activeAbilities") or []):
            aid = rev.get(key)
            if aid is None:
                continue
            out.setdefault(int(aid), []).append(vid)
    return out


def main() -> int:
    verbose = "--verbose" in sys.argv
    universe = _castable_ability_ids()
    broken, domain, under, unknown, vetoed = [], [], [], [], []
    n_masked = 0
    for aid in sorted(universe):
        name, cfg = _resolve_ability(aid)
        opts = targeting_options_for(aid)
        routed_enemy = _is_attack_ability(aid, cfg)
        kind = _ability_kind(aid, name, cfg)
        row = (aid, name, kind, None if opts is None else "0x%x" % int(opts.rules),
               len(universe[aid]), universe[aid][:3])
        if opts is None:
            if routed_enemy:
                unknown.append(row)
            continue
        n_masked += 1
        if refuses_all_enemy_targets(opts):
            vetoed.append(row)
            if routed_enemy:
                broken.append(row)                      # CLIQUET
        elif routed_enemy and opts.is_tile_targeting:
            domain.append(row)
        elif (not routed_enemy) and opts.is_enemy_targeting and not opts.self_cast:
            under.append(row)

    def dump(title, rows):
        print("%s : %d" % (title, len(rows)))
        for (aid, name, kind, mask, n, carriers) in rows:
            print("   %-5d %-34s kind=%-8s mask=%-18s porteurs=%d %s"
                  % (aid, name, kind, mask, n, ",".join(carriers)))

    print("univers = %d abilities actives declarees par au moins une unite" % len(universe))
    print("masques RE-lus applicables = %d (registre combat = %d entrees ; table hors-registre = %d)"
          % (n_masked, len(ABILITY_CLASSES), len(TARGETING_OPTIONS_UNPORTED)))
    print("")
    dump("VETO -- masque refusant TOUTE cible ennemie (TargetIsFriendly/TargetIsCaster)", vetoed)
    dump("RESIDU domaine -- routee vers des UNITES ennemies, masque TILE-targeting", domain)
    if verbose:
        dump("RESIDU sous-generation -- masque enemy, NON routee", under)
        dump("MASQUE INCONNU -- routee ENNEMI, masque non RE-lu", unknown)
    else:
        print("RESIDU sous-generation -- masque enemy, NON routee : %d" % len(under))
        print("MASQUE INCONNU -- routee ENNEMI, masque non RE-lu : %d "
              "(--verbose pour le detail)" % len(unknown))
    print("")
    dump("CLIQUET CASSE -- routee ENNEMI alors que le masque le REFUSE", broken)
    # Contrat de disjonction des deux sources de masque (une ability = UNE source).
    dup = sorted(set(TARGETING_OPTIONS_UNPORTED) & set(ABILITY_CLASSES))
    if dup:
        print("CONTRAT ROMPU -- masque declare DEUX fois : %s" % dup)
    ok = not broken and not dup
    print("VERDICT : %s" % ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
