"""#1015-r1 -- la GARDE du port `BeastSnagga` (le probe, lui, MESURE : `probe_1015r1_beast_snagga`).

CE QU'ELLE GARDE. Le trait `BeastSnagga` (0x406 = 1030) derive la `TriggeredAbilityType` 1084, dont
le `CreateBehaviour` pose DEUX effets sur son porteur. Trois choses peuvent se casser en silence, et
chacune a son etage :

  1. LE CABLAGE -- les deux registres (`TRAIT_DERIVED_ABILITIES`, `ABILITY_INIT_OWNER_EFFECTS`) et
     les deux classes d'effet. Sans eux, le SEUL porteur du kit (`tauNpcFarsight`, npc) n'aurait
     jamais l'effet offline : il n'est dans aucun seed, donc rien ne le capterait.
  2. LE GATE -- `OwnerIsCaster & IsMeleeAttack & (HasTrait(CIBLE, Vehicle) | HasTrait(CIBLE,
     BigTarget))`. Le confondre avec << le PORTEUR a le trait >> donnerait un bonus permanent.
  3. LA SOURCE ET LA STAT -- `beastSnaggaDmgBonus` (20) pour le degat, `beastSnaggaDmgAsMaxHpPct`
     (20) pour le block, et surtout `StatAmount(Health, Maximum)` et NON `FixedArmor`. Les deux
     variables valent 20 : les intervertir serait SILENCIEUX sur l'axe degat.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.entities.effect_type import EffectType                        # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.effects import factory as F                          # noqa: E402
from engine.entities.effects import defender_effect_block_sources         # noqa: E402
from engine.entities.effects.loki import extra_damage as XD               # noqa: E402
from engine.entities.effects.loki import hits as H                        # noqa: E402
from engine.entities.effects.magnitude import trait_var                   # noqa: E402

#: Ce qui doit faire REJOUER ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Les cinq foyers sont atteints par la fermeture d'imports : les deux classes d'effet, le "
        "registre qui les cable, l'agregateur `defender_effect_block_sources` (dont l'etage 5 "
        "verifie le THREADING du 3e substrat) et la signature de base du hook de block. Le "
        "gameconfig, lui, n'est atteint par aucun import -- mais un changement de "
        "`globalValues.traitVariables` change le BUILD, donc le declencheur de build le couvre."
    ),
}


def _dmg_effect():
    return XD.BeastSnaggaExtraDmgEffect(name=EffectType.BeastSnagga_ExtraDmg.name,
                                        effect_type=int(EffectType.BeastSnagga_ExtraDmg))


def _block_effect():
    return H.BeastSnaggaExtraBlockEffect(name=EffectType.BeastSnagga_ExtraBlock.name,
                                         effect_type=int(EffectType.BeastSnagga_ExtraBlock))


# ================================================================================================
# 1. LE CABLAGE
# ================================================================================================

def test_les_ordinaux_du_build_sont_ceux_ecrits_au_site():
    """Les quatre ids LUS au decompile. `probe_313` garde la BIJECTION mirror <-> build ; il ne
    garde PAS que le port a ecrit CET ordinal-la (il redevient vert si on regenere le mirror apres
    un renumerotage). C'est le cran du dessous."""
    assert int(UnitTrait.BeastSnagga) == 0x406 == 1030
    assert int(TriggeredAbilityType.BeastSnagga) == 0x43c == 1084
    assert int(EffectType.BeastSnagga_ExtraDmg) == 0x438 == 1080
    assert int(EffectType.BeastSnagga_ExtraBlock) == 0x439 == 1081
    # ⚠ 1030 est AUSSI une `TriggeredAbilityType` (celle que DERIVE le trait `BigTarget`) : deux
    # enums, meme ordinal. C'est pourquoi le port ecrit des MEMBRES et jamais l'entier.
    assert int(TriggeredAbilityType.BigTarget) == 1030


def test_le_trait_derive_son_ability_et_l_ability_pose_ses_deux_effets():
    """`AddTraitOperation$$AddDerivedAbilities` puis `BeastSnaggaAbility$$CreateBehaviour`.

    L'ORDRE de la liste est celui d'EXECUTION (`AddEffect` puis `AddExtraBlockEffectToOwner`), qui
    est l'INVERSE de l'ordre de CONSTRUCTION du pseudo-C -- meme piege que `MonsterSlayerOfCaliban`
    (#1009). Il n'a aucun observable ici (poses independantes et idempotentes) ; il est garde parce
    qu'il est LU, pour qu'un futur lecteur ne << corrige >> pas dans le mauvais sens."""
    assert F.TRAIT_DERIVED_ABILITIES[UnitTrait.BeastSnagga.name] == ["BeastSnagga"]
    assert F.ABILITY_INIT_OWNER_EFFECTS["BeastSnagga"] == [
        EffectType.BeastSnagga_ExtraDmg.name, EffectType.BeastSnagga_ExtraBlock.name]
    assert F.EFFECT_CLASSES[EffectType.BeastSnagga_ExtraDmg.name] is XD.BeastSnaggaExtraDmgEffect
    assert F.EFFECT_CLASSES[EffectType.BeastSnagga_ExtraBlock.name] is H.BeastSnaggaExtraBlockEffect


# ================================================================================================
# 2. LE GATE -- les traits de la CIBLE, et la nature MELEE
# ================================================================================================

def test_le_bonus_de_degat_gate_sur_les_traits_de_la_cible_et_sur_la_melee():
    """`get_OwnerIsCaster & IsMeleeAttack & (HasTrait(cible, Vehicle) | HasTrait(cible, BigTarget))`.

    Les DEUX faces du gate sont exercees : ce qui l'OUVRE et ce qui le FERME. Un test qui
    n'exercerait que l'ouverture passerait sur un port ayant oublie le gate entier."""
    eff = _dmg_effect()
    pct = trait_var("BeastSnagga", "beastSnaggaDmgBonus")
    assert pct == 20, "le gameconfig a bouge : %r" % pct
    for traits in (frozenset({UnitTrait.Vehicle.name}), frozenset({UnitTrait.BigTarget.name}),
                   frozenset({UnitTrait.Vehicle.name, UnitTrait.BigTarget.name})):
        b = eff.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=traits)
        assert b is not None and b.kind == "PercentIncrease" and b.value == 20, (traits, b)
    # FERME : cible sans aucun des deux traits, cible inconnue, et attaque NON melee.
    assert eff.create_effect_damage_bonus_for_attack(
        is_ranged=False, target_traits=frozenset({UnitTrait.Hero.name})) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=None) is None
    assert eff.create_effect_damage_bonus_for_attack(
        is_ranged=True, target_traits=frozenset({UnitTrait.BigTarget.name})) is None
    # `is_ranged=None` = nature NON PROUVEE melee -> gate FAUX (#106), pas << on suppose melee >>.
    assert eff.create_effect_damage_bonus_for_attack(
        is_ranged=None, target_traits=frozenset({UnitTrait.BigTarget.name})) is None


def test_la_paire_de_traits_cible_est_ecrite_par_membre_d_enum():
    assert XD._BEAST_SNAGGA_TARGET_TRAITS == frozenset(
        {UnitTrait.Vehicle.name, UnitTrait.BigTarget.name})


# ================================================================================================
# 3. LA STAT DU BLOCK -- Health/Maximum, PAS FixedArmor
# ================================================================================================

def test_le_block_lit_les_PV_MAX_et_AUCUNE_autre_stat_du_defenseur():
    """`PercentageOf(StatAmount(Owner, Health = 0x5, Maximum = 0x2), Direct(GetNumberConstant(0x36)))`.

    ⚠ LE CONTRASTE AVEC LE JUMEAU EST LE POINT DU TEST. `BeastSlayer_ExtraBlock` lit
    `PercentageOf(StatAmount(FixedArmor))` et `Daemon_ExtraBlock` `PercentageOf(Attack)` -- les deux
    autres substrats du MEME hook. Recopier l'un des deux (les corps de `CreateDamageModifier` des
    deux Beast* etant IDENTIQUES, la tentation est reelle) donnerait un amount plausible et FAUX.
    Ce test garde que `defender_fixed_armor` et `defender_attack` sont IGNORES."""
    eff = _block_effect()
    chance = trait_var("BeastSnagga", "beastSnaggaBlockChance")
    pct = trait_var("BeastSnagga", "beastSnaggaDmgAsMaxHpPct")
    assert (chance, pct) == (10, 20), "le gameconfig a bouge : %r" % ((chance, pct),)
    a = eff.create_effect_block_source_for_defense(defender_max_health=9000)
    assert (a.chance, a.amount) == (10, 1800)                 # 20 % de 9000
    b = eff.create_effect_block_source_for_defense(defender_fixed_armor=99999,
                                                   defender_attack=99999,
                                                   defender_max_health=9000)
    assert (b.chance, b.amount, b.block_id) == (a.chance, a.amount, a.block_id)
    # Substrat NON threade -> pas de source (jamais un amount devine).
    assert eff.create_effect_block_source_for_defense() is None
    assert eff.create_effect_block_source_for_defense(defender_fixed_armor=99999) is None


def test_le_block_id_separe_BeastSnagga_de_BeastSlayer():
    """Les DEUX sources ont chance 10. `block_id` est l'ENTITE-EFFET (`BlockChanceInfo.entityId`,
    cle du `failedBlockIds` de `CalculateBlockChances`) : prendre la CHANCE comme identite les
    confondrait dans l'exclusion inter-coups de `_run_hits` -- un tirage perdu des le coup 2."""
    snagga = _block_effect().create_effect_block_source_for_defense(defender_max_health=9000)
    slayer = H.BeastSlayerExtraBlockEffect(
        name=EffectType.BeastSlayer_ExtraBlock.name,
        effect_type=int(EffectType.BeastSlayer_ExtraBlock)
    ).create_effect_block_source_for_defense(defender_fixed_armor=500)
    assert snagga.chance == slayer.chance == 10, "les deux chances ont diverge : le test ne "\
        "discrimine plus rien"
    assert snagga.block_id != slayer.block_id
    assert snagga.block_id == int(EffectType.BeastSnagga_ExtraBlock)


# ================================================================================================
# 4-5. LE THREADING -- un substrat non propage rend la source INERTE, en silence
# ================================================================================================

def test_l_agregateur_propage_le_troisieme_substrat():
    """`defender_effect_block_sources` est le foyer UNIQUE des deux faces (combat via
    `AttackDamageOperation._block_sources`, prediction via `playbook/prediction/_shared`). S'il
    n'acheminait pas `defender_max_health`, la source DISPARAITRAIT sans erreur -- et le port
    sauterait un jet de block que le natif roule, ce qui desynchronise tout le RNG en aval (meme
    signature que le trou #221 sur l'Attack)."""
    eff = _block_effect()
    assert defender_effect_block_sources([eff]) == []
    src = defender_effect_block_sources([eff], defender_max_health=9000)
    assert len(src) == 1 and (src[0].chance, src[0].amount) == (10, 1800)


def test_aucun_site_du_hook_de_block_ne_reste_a_l_ancienne_signature():
    """LE GISEMENT QUE CETTE TRANCHE A OUVERT, ET QU'ELLE REFERME.

    Ajouter un parametre au hook casse tout site qui le REDEFINIT ou le SUBSTITUE. La banque a
    trouve `tests/engine/runner/test_daemon_extra_block_live.py` (`TypeError` au premier run apres
    rebase) -- mais elle ne joue PAS les probes, et DEUX d'entre eux portaient le meme stub
    (`probe_221_daemon_normal_attack.py`, `probe_brazier_daemon_offset.py`) : la faute y aurait
    dormi jusqu'au prochain run manuel. C'est le vice deja mesure ailleurs dans le depot (un
    patcheur qu'aucune passe n'execute).

    Le perimetre est DERIVE (tout `.py` de `scripts/python/**`), jamais une liste blanche : un
    quatrieme site ecrit demain sort tout seul.

    ⚠ Un stub `**kwargs` passerait ce test et serait PIRE : il masquerait la disparition d'un
    substrat cote agregateur. Le critere est donc la PRESENCE NOMMEE des trois."""
    import re
    racine = PY
    motif = re.compile(
        r"(?:def|lambda)\s+(?:create_effect_block_source_for_defense\s*\(\s*self|self)\s*,"
        r"(?P<params>[^)]*)\)", re.S)
    sites, fautifs = [], []
    for f in sorted(racine.rglob("*.py")):
        try:
            src = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "create_effect_block_source_for_defense" not in src:
            continue
        for m in motif.finditer(src):
            params = m.group("params")
            if "defender_fixed_armor" not in params:
                continue                              # autre signature : pas ce hook
            rel = f.relative_to(racine).as_posix()
            sites.append(rel)
            if "defender_max_health" not in params:
                fautifs.append((rel, src[:m.start()].count("\n") + 1))
    assert len(sites) >= 8, (
        "seulement %d site(s) trouve(s) : le balayage ne visite plus le hook (regex ou arbre), donc "
        "son zero ne prouverait RIEN. Sites : %r" % (len(sites), sites))
    assert fautifs == [], (
        "site(s) du hook de block restes a l'ANCIENNE signature (2 substrats sur 3) : %r. Un appel "
        "de l'agregateur y leve `TypeError` -- et dans un probe, personne ne le verra." % fautifs)


def test_les_trois_vecteurs_de_combat_threadent_le_maxhp():
    """Le foyer est unique cote agregateur, mais les APPELANTS sont trois (`normal`, `normal_like`,
    `ability`) : un seul oublie et le block de `BeastSnagga` disparait sur ce vecteur-la, en
    silence. On lit la SOURCE plutot que d'appeler les trois (elles exigent un `State` complet)."""
    base = PY / "engine" / "runner" / "operations" / "damage_ops"
    for nom in ("normal.py", "normal_like.py", "ability.py"):
        src = (base / nom).read_text(encoding="utf-8")
        i = src.find("_block_sources(")
        assert i > 0, "%s n'appelle plus `_block_sources` : ce test est PERIME" % nom
        assert "defender_max_health=" in src[i:i + 400], (
            "%s appelle `_block_sources` sans threader `defender_max_health` -- la source "
            "`BeastSnagga_ExtraBlock` y serait INERTE, sans erreur." % nom)
