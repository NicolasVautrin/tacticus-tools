"""#71 LasCannon pierce bonus (+50) -- gate OFFLINE (patron CondemnorStake : carrier NON spawnable).

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio` (RE decompile, mirror 1:1) :
    p = profile.PiercingDamageRatio                         # DamageProfile @+0x14
    if profile.HasTrait(DamageTrait.LasCannon=3)
       and attacker.HasTrait(UnitTrait.HeavyWeapon=1001 | Emplacement=1016):
        p += 50                                             # static_field[0] de StaticBattleRules.DamageTrait,
                                                            # ecrit 0x32 par sa .idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor (`**(int**)
                                                            # (cls+0xb8)=0x32`) ; lu `iVar3 += **(int**)(cls+0xb8)`
    return clamp(0, 100, p)

Le bonus est applique par `GetPiercingRatio`, appele par les DEUX faces natives :
  - PREDICTION/UI : `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (xrefs DATA-only = service delegate partage).
  - COMBAT        : `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` (appele par `CalculateBaseDamageWithAll
                    Modifiers IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers+0x336`, la fn per-coup partagee combat+prediction) -> `GetDamageWithPiercing`.
Le port Python a UN seul foyer partage `battle_query.select_weapon_pierce` (prediction ET combat) ; le fix #71
y ajoute le bonus via `get_piercing_ratio` -> les deux faces sont couvertes.

NON-CONFRONTABLE LIVE (patron CondemnorStake, doctrine feedback_validate_discriminant_spawnable) : le gate
COMPOSE (profil Las ET attaquant HeavyWeapon/Emplacement) n'est satisfait par AUCUN carrier spawnable :
  - les 18 unites a arme 'Las' du gameconfig : les seules qui portent AUSSI HeavyWeapon/Emplacement sont des
    NPC (`astraNpc2Lascannon`) et summons (`astraSmnLascannon`), HORS du pool spawnable (buildNormalizedBC
    filtre les NPC/summons -- verifie via `rl_duel build --list-pool`) et non normalisables par injection ;
    `astraSmnLascannon` n'est invoque que par `EnvFactionSummons:Custodes` (mecanique Environnement, non drivable).
  - les Las du pool (astraCreed, astraOrdnance) n'ont PAS HeavyWeapon/Emplacement -> pas de bonus (contrefactuel) ;
  - les HeavyWeapon du pool (adeptRetributor, blackObliterator, ...) n'utilisent PAS de profil Las.
=> validation par MIRROR + TOGGLE OFFLINE de l'etat (comme CondemnorStake toggle le trait cible, mais offline).
La spawnabilite du gate est verifiee AVANT (pas de datapoint live mande sur un artefact non spawnable).

ZERO-REGRESSION : le bonus ne fire QUE sur Las+HeavyWeapon/Emplacement ; AUCUN pool-unit ne satisfait les deux
-> le fix est un NO-OP prouve pour toute unite spawnable (les tests combat live pool restent inchanges).

ASCII-only.
"""
from __future__ import annotations

import os
import sys

import gameconfig as GC

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import damage_profile_pierce    # noqa: E402

from engine.services.static_battle_rules import (
    W_LASCANNON_PIERCE_BONUS, get_piercing_ratio, get_damage_with_piercing)
from engine.services.damage_prediction import get_attack_piercing_damage_ratio
from engine.services.battle_query import select_weapon_pierce
from engine.entities.damage_trait import DamageTrait
from engine.entities.traits.unit_trait import UnitTrait

LAS_CARRIER = "astraNpc2Lascannon"   # arme Las (Range 4) + Emplacement (kit gameconfig reel)


class _Ctx:
    """UnitContext minimal pour select_weapon_pierce : arme resolue par visual_id (gameconfig),
    traits/extra-pierce injectables (toggle du discriminant offline)."""
    def __init__(self, visual_id, traits, extra_pierce=0, extra_pierce_ranged=0,
                 extra_pierce_melee=0, normal_hits=1):
        self.visual_id = visual_id
        self.traits = list(traits)
        self.extra_pierce = extra_pierce
        self.extra_pierce_ranged = extra_pierce_ranged
        self.extra_pierce_melee = extra_pierce_melee
        self.normal_hits = normal_hits


# ------------------------------------------------------------------ 1. constante + enums

def test_constant_is_50():
    """La constante = 50 (0x32), lue du cctor natif `StaticBattleRules.DamageTrait$$.idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor`."""
    assert W_LASCANNON_PIERCE_BONUS == 50


def test_enum_ids_match_native():
    """Ids natifs : LasCannon=3, HeavyWeapon=1001 (0x3e9), Emplacement=1016 (0x3f8)."""
    assert int(DamageTrait.LasCannon) == 3
    assert int(UnitTrait.HeavyWeapon) == 1001 == 0x3e9
    assert int(UnitTrait.Emplacement) == 1016 == 0x3f8


# ------------------------------------------------------------------ 2. get_piercing_ratio (formule pure)

def test_get_piercing_ratio_gate():
    """GetPiercingRatio : +50 SEULEMENT si profil.LasCannon ET attaquant.HW/Emp ; sinon base inchangee."""
    assert get_piercing_ratio(10, True, True) == 60      # las + hw/emp -> +50
    assert get_piercing_ratio(10, True, False) == 10     # las, pas hw/emp -> base
    assert get_piercing_ratio(10, False, True) == 10     # hw/emp, pas las -> base
    assert get_piercing_ratio(10, False, False) == 10    # ni l'un ni l'autre -> base


def test_get_piercing_ratio_clamped_100():
    """clamp(0,100) : un profil deja haut + bonus ne depasse pas 100."""
    assert get_piercing_ratio(80, True, True) == 100     # 80+50=130 -> clamp 100


def test_get_attack_piercing_damage_ratio_applies_bonus_by_default():
    """GetAttackPiercingDamageRatio (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio) applique le bonus par defaut (lascannon_bonus=50 intrinseque
    au natif, pas un param appelant). base=GetPiercingRatio + ExtraPierce(0 ici)."""
    got = get_attack_piercing_damage_ratio(
        10, profile_has_lascannon=True, attacker_extra_pierce=0, attacker_extra_pierce_dir=0,
        attacker_has_heavy_weapon_or_emplacement=True)
    assert got == 60
    got_off = get_attack_piercing_damage_ratio(
        10, profile_has_lascannon=False, attacker_extra_pierce=0, attacker_extra_pierce_dir=0,
        attacker_has_heavy_weapon_or_emplacement=True)
    assert got_off == 10


# ------------------------------------------------------------------ 3. carrier reel (gameconfig) + kit

def test_las_carrier_kit_from_gameconfig():
    """Le carrier a bien l'arme profil Las (Range 4) ET le trait Emplacement (kit gameconfig reel)."""
    u = GC.unit(LAS_CARRIER) or {}
    weapons = u.get("weapons") or []
    las = [w for w in weapons if w.get("DamageProfile") == "Las"]
    assert las, f"{LAS_CARRIER} n'a pas d'arme Las"
    assert any(w.get("Range") for w in las), "l'arme Las du carrier n'est pas ranged"
    assert "Emplacement" in (u.get("traits") or [])
    dp = GC.damage_profile("Las") or {}
    assert "LasCannon" in (dp.get("Traits") or []), "le profil Las ne porte pas DamageTrait.LasCannon"
    # La BASE de percage du profil Las est une valeur BRUTE de config : on ne la FIGE pas, on exige
    # seulement que l'oracle `damageProfiles.Las.PiercingRatio` soit LISIBLE (il echoue si la cle a
    # disparu) et strictement sous le clamp -- sinon le contrefactuel `base+50 -> clamp 100` de
    # `test_get_piercing_ratio_clamped_100` ne discriminerait plus rien ici.
    assert 0 < damage_profile_pierce("Las") < 100


# ------------------------------------------------------------------ 4. select_weapon_pierce (foyer partage) + TOGGLE

def _las_with_bonus() -> int:
    """Attendu du carrier gate-ON = `GetPiercingRatio` mirrote sur SES DEUX sources : la base BRUTE de config
    (`damageProfiles.Las.PiercingRatio`) et la constante NATIVE du cctor (`W_LASCANNON_PIERCE_BONUS`), sous le
    clamp 100. Aucune des deux n'est ecrite en dur ici."""
    return min(100, damage_profile_pierce("Las") + W_LASCANNON_PIERCE_BONUS)


def test_select_weapon_pierce_bonus_ranged():
    """Carrier Las+Emplacement au RANGE (dist<=Range4) -> pierce = base profil Las + bonus lascannon."""
    ctx = _Ctx(LAS_CARRIER, GC.unit(LAS_CARRIER)["traits"])
    pierce, is_ranged, _h, prof = select_weapon_pierce(ctx, is_adjacent=False, dist=3)
    assert prof == "Las" and is_ranged is True
    assert _las_with_bonus() > damage_profile_pierce("Las"), \
        "base + bonus sature deja le clamp : le gate ne serait plus DISCRIMINANT"
    assert pierce == _las_with_bonus()


def test_toggle_emplacement_gates_bonus():
    """TOGGLE OFFLINE du discriminant (mirror HasTrait(attacker, HW/Emp) natif) : retirer Emplacement -> base
    profil seule ; remettre HeavyWeapon -> base + bonus (l'un OU l'autre suffit)."""
    base_traits = list(GC.unit(LAS_CARRIER)["traits"])
    base_pierce = damage_profile_pierce("Las")
    with_bonus = _las_with_bonus()
    assert with_bonus > base_pierce, \
        "base + bonus sature deja le clamp : le toggle ne serait plus DISCRIMINANT"
    # Emplacement present -> bonus arme
    p_on = select_weapon_pierce(_Ctx(LAS_CARRIER, base_traits), False, 3)[0]
    assert p_on == with_bonus
    # Emplacement retire, aucun HW/Emp -> base du profil (bonus annule)
    stripped = [t for t in base_traits if t not in ("Emplacement", "HeavyWeapon")]
    p_off = select_weapon_pierce(_Ctx(LAS_CARRIER, stripped), False, 3)[0]
    assert p_off == base_pierce, f"sans HW/Emp le bonus devrait disparaitre (got {p_off})"
    # HeavyWeapon ajoute -> bonus arme (l'autre trait du gate suffit aussi)
    p_hw = select_weapon_pierce(_Ctx(LAS_CARRIER, stripped + ["HeavyWeapon"]), False, 3)[0]
    assert p_hw == with_bonus, f"HeavyWeapon devrait ARMER le bonus (got {p_hw})"


def test_toggle_profile_lascannon_gates_bonus():
    """Le gate profil : un carrier HeavyWeapon/Emplacement mais SANS arme Las -> pas de bonus (gate profil.Las)."""
    # astraNpc2Lascannon adjacent -> arme melee Physical (pas Las) -> pas de bonus meme avec Emplacement
    ctx = _Ctx(LAS_CARRIER, GC.unit(LAS_CARRIER)["traits"])
    pierce, is_ranged, _h, prof = select_weapon_pierce(ctx, is_adjacent=True, dist=1)
    assert prof != "Las", "en melee le carrier prend une arme non-Las"
    # Le percage est EXACTEMENT la base du profil melee selectionne (aucun bonus sur non-Las) -- derive
    # du profil RENDU par le selecteur, pas d'un seuil ecrit a la main.
    assert pierce == damage_profile_pierce(prof), \
        f"pas de bonus attendu sur une arme non-Las : {pierce} != damageProfiles.{prof}.PiercingRatio"


# ------------------------------------------------------------------ 5. le bonus CHANGE le degat de combat (armure)

def test_pierce_bonus_changes_combat_damage_vs_armor():
    """Discriminant COMBAT : contre une cible ARMUREE, pierce 60 (fix) donne un degat > pierce 10 (sans fix).
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing` : le percage est un PLANCHER = roll*pierce/100 vs roll-armure."""
    roll, armor = 3000, 1909            # magnitude realiste (cible tanky type necroOverlord armure ~1909)
    d60 = int(get_damage_with_piercing(roll, 60, armor))
    d10 = int(get_damage_with_piercing(roll, 10, armor))
    # pierce 60 -> plancher 0.6*3000=1800 > roll-armor=1091 -> 1800 ; pierce 10 -> max(1091, 300)=1091
    assert d60 > d10, f"le bonus de percage devrait AUGMENTER le degat contre armure (d60={d60} d10={d10})"
    assert d60 == 1800 and d10 == 1091, f"valeurs attendues (1800 vs 1091), got ({d60} vs {d10})"


# ------------------------------------------------------------------ 6. zero-regression (pool)

def test_zero_regression_pool_las_carriers_no_bonus():
    """Les Las du POOL spawnable (astraCreed, astraOrdnance) n'ont PAS HeavyWeapon/Emplacement -> pierce base
    INCHANGE par le fix (le bonus est un no-op pour tout carrier spawnable). Verrou anti-sur-application."""
    for vis in ("astraCreed", "astraOrdnance"):
        u = GC.unit(vis) or {}
        traits = u.get("traits") or []
        assert "HeavyWeapon" not in traits and "Emplacement" not in traits, \
            f"{vis} porte HW/Emp -> le contrefactuel n'est plus valide"
        ctx = _Ctx(vis, traits)
        # au range OU en melee : jamais de bonus -> le percage est EXACTEMENT la base du profil de l'arme
        # selectionnee (derive du profil rendu, pas d'un seuil ecrit a la main).
        for adj, dist in ((False, 3), (True, 1)):
            pierce, _ir, _h, prof = select_weapon_pierce(ctx, adj, dist)
            assert pierce == damage_profile_pierce(prof), (
                f"{vis} (adj={adj}) ne devrait PAS recevoir le bonus lascannon : {pierce} != "
                f"damageProfiles.{prof}.PiercingRatio")
