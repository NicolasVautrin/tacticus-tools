"""#75 — `UnitTrait.TwoManTeam` (0x3fa=1018) : le trait est un TAG DE TOOLTIP, la mecanique est le
member-cap GROUP-UNIT deja porte.

PREMISSE REFUTEE (preuve RE) : `HasTrait(x, 0x3fa)` n'existe NULLE PART dans GameAssembly.dll (build
gqfc5mff6c) — les 7 occurrences de `,0x3fa,` sont ValkyrieStrike/ActOfFaith (ActiveAbilityType 1018,
homonyme d'id) et un pass Unity. Aucune fonction native ne LIT ce trait. Ce que le tooltip i2 decrit
(<< Takes a maximum of 50% of its max Health in Damage from a single hit. Does not apply to Blast
Damage. Once below 50% of its max Health, cannot be healed above 50% of its max Health again. >>) est
EXACTEMENT le comportement du GroupUnitComponent pour `nrOfMembers == 2`, keye sur le NOMBRE DE
MEMBRES, pas sur le trait :

  - cap par-coup     = `IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit
                       -> cap = cumul - maxHealthWith(remaining-1) = 1 membre = 50% de maxHP a 2 membres
  - exclusion Blast  = `DamageProfile.HasTrait(profile, 2)` = `DamageTrait.HitsMultipleMembers`
                       (SEUL le profil `Blast` le porte dans gameconfig) -> early-return, pas de cap
  - plafond de soin  = `IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit (+ `AttackQuery.
                       IdunBattle.Core.Services.AttackQuery$$IsAtGroupUnitHealLimit) -> maxHealthWith(membres RESTANTS) - hp,
                       soit 50% de maxHP des qu'un des 2 membres est mort

Ces tests VERROUILLENT l'identite numerique "TwoManTeam == group-cap a 2 membres" sur les porteurs
REELS lus dans gameconfig (aucune fixture synthetique) : si un refactor du member-cap cassait l'un des
trois bords, le tooltip TwoManTeam cesserait d'etre honore silencieusement.
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.entities.damage_trait import DamageTrait
from engine.services.trait_damage_limits import (apply_group_unit_damage_limit,
                                                 get_group_unit_heal_limit,
                                                 is_at_group_unit_heal_limit)

# Porteurs REELS du trait TwoManTeam (gameconfig, build gqfc5mff6c) : 4 npc + 2 summons, tous
# `nrOfMembers == 2`. Les 2 summons sont invoques par `EnvFactionSummons:*` (summons d'ENVIRONNEMENT,
# pas une ability de heros) -> aucun porteur atteignable via le pool runner (cf. rapport #75).
TWO_MAN_TEAM_CARRIERS = ["astraNpc2Lascannon", "astraNpc4Mortar", "astraNpc4MortarSurv",
                         "orksNpc5LootGrotTeam", "astraSmnLascannon", "astraSmnMortar"]


def test_two_man_team_carriers_are_all_two_member_units():
    """Le trait et `nrOfMembers == 2` sont coextensifs : c'est ce qui autorise a dire que le
    member-cap PRODUIT le comportement du tooltip sans lire le trait."""
    for uid in TWO_MAN_TEAM_CARRIERS:
        u = GC.unit(uid)
        assert u is not None, f"porteur {uid} absent de gameconfig"
        assert "TwoManTeam" in (u.get("traits") or []), f"{uid} n'a plus le trait TwoManTeam"
        assert int(u.get("nrOfMembers") or 1) == 2, \
            f"{uid} nrOfMembers={u.get('nrOfMembers')} (attendu 2)"


def test_blast_is_the_only_profile_that_bypasses_the_member_cap():
    """<< Does not apply to Blast Damage >> = `HasTrait(profile, 2)` = HitsMultipleMembers, porte par
    le SEUL profil Blast."""
    idx = GC._index()
    carriers = [name for name, p in idx["damageProfiles"].items()
                if DamageTrait.HitsMultipleMembers.name in (p.get("Traits") or [])]
    assert carriers == ["Blast"], f"profils HitsMultipleMembers attendus ['Blast'], obtenu {carriers}"


@pytest.mark.parametrize("hp_max", [7312, 4802, 1001, 2, 3])
def test_single_hit_cap_is_half_max_health_at_full_health(hp_max):
    """Cap par-coup a PV pleins, 2 membres = 50% de maxHP (arrondi natif : la division des PV repartit
    le reste sur les PREMIERS membres -> cap = hp_max - hp_max//2, exactement `maxHealthWith(1)`)."""
    dealt = 10 ** 9                                  # degat brut enorme : seul le cap doit le brider
    capped = apply_group_unit_damage_limit(dealt, False, 2, hp_max, hp_max)
    expected = hp_max - (hp_max // 2 + (1 if hp_max % 2 else 0))   # hp_max - PV du 1er membre
    assert capped == expected, f"hp_max={hp_max}: cap={capped} attendu {expected}"
    assert capped <= hp_max // 2 + 1, "le cap doit valoir ~50% de maxHP (tooltip TwoManTeam)"


def test_hit_exactly_at_the_cap_is_not_reduced():
    """BORD : un coup EXACTEMENT au cap passe tel quel (le natif ne cape que `dmg > limit`)."""
    hp_max = 7312
    cap = apply_group_unit_damage_limit(10 ** 9, False, 2, hp_max, hp_max)
    assert apply_group_unit_damage_limit(cap, False, 2, hp_max, hp_max) == cap
    assert apply_group_unit_damage_limit(cap - 1, False, 2, hp_max, hp_max) == cap - 1
    assert apply_group_unit_damage_limit(cap + 1, False, 2, hp_max, hp_max) == cap


def test_blast_profile_bypasses_the_single_hit_cap():
    """<< Does not apply to Blast Damage >> : avec le flag HitsMultipleMembers le degat n'est PAS cape."""
    hp_max = 7312
    huge = hp_max * 3
    assert apply_group_unit_damage_limit(huge, True, 2, hp_max, hp_max) == huge, \
        "Blast (HitsMultipleMembers) doit BYPASSER le member-cap"
    assert apply_group_unit_damage_limit(huge, False, 2, hp_max, hp_max) < huge, \
        "hors Blast le cap doit mordre"


def test_hero_single_member_is_never_capped():
    """CONTROLE : une unite mono-membre (tout heros) n'est jamais capee — le member-cap est bien keye
    sur `nrOfMembers`, il ne fuit pas sur les unites normales."""
    huge = 10 ** 6
    assert apply_group_unit_damage_limit(huge, False, 1, 9537, 9537) == huge


def test_heal_ceiling_is_half_max_health_once_one_member_is_dead():
    """<< Once below 50% of its max Health, cannot be healed above 50% >> : des qu'un des 2 membres est
    mort, le plafond de soin = maxHealthWith(1 membre restant) = ~50% de maxHP."""
    hp_max = 7312
    first_member = hp_max - hp_max // 2            # PV du membre 1 (reste sur les premiers)
    hp = 1                                         # 1 membre mort, l'autre a 1 PV
    limit = get_group_unit_heal_limit(hp_max, 2, hp)
    assert hp + limit == first_member, \
        f"plafond de soin {hp}+{limit} attendu {first_member} (~50% de {hp_max})"
    assert is_at_group_unit_heal_limit(hp_max, 2, first_member) is True, \
        "a 50% pile, l'unite est AU plafond (tout soin de plus ne ferait que reveiller un membre)"
    assert is_at_group_unit_heal_limit(hp_max, 2, first_member - 1) is False


def test_heal_ceiling_is_absent_for_a_hero():
    """CONTROLE : mono-membre -> pas de plafond (int.MaxValue natif) et jamais 'at limit'."""
    assert get_group_unit_heal_limit(9537, 1, 10) == 0x7fffffff
    assert is_at_group_unit_heal_limit(9537, 1, 10) is False
