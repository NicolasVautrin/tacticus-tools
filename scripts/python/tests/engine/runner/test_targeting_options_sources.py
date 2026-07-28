"""#217 -- CLIQUET des DEUX SOURCES de masque `TargetingOptions` (offline pur, aucune session).

CE QUE CE FICHIER GARDE
-----------------------
Depuis #217 le masque de ciblage d'une ability se lit par `engine.runner.abilities.targeting.
targeting_options_for(ability_id)`, qui a DEUX sources :

  1. `ABILITY_CLASSES[aid].TARGETING_OPTIONS` -- la classe du registre COMBAT (source historique) ;
  2. `TARGETING_OPTIONS_UNPORTED[aid]`        -- le masque RE-LU d'une ability dont la face COMBAT
     n'est PAS portee (le litteral vit dans `<X>Ability$$.ctor`, pas dans `ExecuteBehaviour` : il se
     lit et se porte independamment du registre).

DEUX sources = un risque de DOUBLE DECLARATION qui divergerait silencieusement (deux masques pour la
meme ability, celui qui gagne dependant de l'ordre de lecture). Le contrat est donc la DISJONCTION,
et c'est ce test qui le tient.

Il garde AUSSI le cliquet de routage : aucune ability dont le masque REFUSE toute cible ennemie
(`refuses_all_enemy_targets` = `TargetIsFriendly` ou `TargetIsCaster`, les deux seules regles de camp
du filtre statique) ne doit etre routee vers les ENNEMIS par `state_bridge._is_attack_ability`.
C'est la regression que #217 a fermee : `SorcerousFacade` (1100) porte un `constants.damageProfile`
(Psychic) et cible pourtant un ALLIE Psyker -- le moteur en fabriquait une action par ennemi, la ou
`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` n'en rend AUCUNE (il gate chaque
tuile candidate par `AttackQuery.GetInvalidTargetReason`).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import gameconfig as GC
import enum_maps as EM
from engine.ai.state_bridge import _is_attack_ability, _resolve_ability
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (
    TARGETING_OPTIONS_UNPORTED, refuses_all_enemy_targets, targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR


def _castable_ability_ids() -> set:
    """Les `ActiveAbilityType` declares par au moins une unite du gameconfig (l'univers atteignable)."""
    rev = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    out = set()
    for group in GC.all_unit_ids().values():
        for vid in group:
            for key in ((GC.unit(vid) or {}).get("activeAbilities") or []):
                aid = rev.get(key)
                if aid is not None:
                    out.add(int(aid))
    return out


def test_les_deux_sources_de_masque_sont_disjointes():
    """Une ability = UNE source de masque. Une entree de `TARGETING_OPTIONS_UNPORTED` qui entre dans
    `ABILITY_CLASSES` doit MIGRER sur la classe (et disparaitre de la table), jamais coexister."""
    dup = sorted(set(TARGETING_OPTIONS_UNPORTED) & set(ABILITY_CLASSES))
    assert not dup, ("masque declare DEUX fois (classe du registre ET table hors-registre) : %s "
                     "-- porter le masque sur la classe et retirer l'entree de la table" % dup)


def test_toute_entree_hors_registre_est_resolue_par_le_resolveur():
    """`targeting_options_for` doit rendre exactement l'entree de la table pour ces abilities (garde
    contre un resolveur qui cesserait de consulter la 2e source)."""
    for aid, opts in TARGETING_OPTIONS_UNPORTED.items():
        assert targeting_options_for(aid) is opts, "targeting_options_for(%d) ne rend pas la table" % aid


def test_sorcerous_facade_cible_un_allie():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$.ctor` :
    `TargetingOptions..ctor(&opts, 0, <TargetingRange statics+0x48 UseWholeBoard>, 1, 0x402, 0, 0, 0)`
    = `TargetIsFriendly | TargetMatchesDynamicRule`. CONFIRME LIVE (`probe_217_facade_live.py`) :
    `abilityTargets` natif rend UNE seule cible, l'ALLIE Psyker."""
    opts = targeting_options_for(1100)
    assert opts is not None, "le masque de SorcerousFacade (1100) doit rester RE-lu"
    assert int(opts.rules) == int(TR.TargetIsFriendly | TR.TargetMatchesDynamicRule)
    assert refuses_all_enemy_targets(opts)
    assert not opts.is_enemy_targeting and not opts.is_tile_targeting


def test_aucune_ability_a_masque_ami_n_est_routee_vers_les_ennemis():
    """LE CLIQUET. Une ability dont le masque refuse toute cible ennemie ne doit JAMAIS passer par
    `_is_attack_ability` (la seule porte vers `_best_attack` / les `plans` d'attaque offline)."""
    bad = []
    for aid in sorted(_castable_ability_ids()):
        opts = targeting_options_for(aid)
        if opts is None or not refuses_all_enemy_targets(opts):
            continue
        _name, cfg = _resolve_ability(aid)
        if _is_attack_ability(aid, cfg):
            bad.append((aid, _name, hex(int(opts.rules))))
    assert not bad, ("abilities routees vers les ENNEMIS alors que leur masque le REFUSE : %s" % bad)
