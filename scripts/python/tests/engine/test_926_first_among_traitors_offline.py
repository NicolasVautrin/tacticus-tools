"""#926 -- GARDES OFFLINE du passif `FirstAmongTraitors` (`blackAbaddon`).

Ce fichier fige ce que la RE a ETABLI (decompile `rnca9r7q6c`), pas ce que le port fait
aujourd'hui. Chaque assertion nomme le corps natif dont elle est le mirror. Le pendant LIVE
(oracle natif par tuile, mutants) vit dans `tests/engine/runner/test_926_first_among_traitors_live.py`.

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE CRAN EXISTE
------------------------------------------------------
1. Les TROIS faces sont au registre -- une seule d'entre elles etait portee avant #926
   (`FirstAmongTraitorsNonOwnerPlaybook`, #477-r37) alors que `kit-coverage` n'annoncait
   qu'« il manque 1 ».
2. Le porteur EST EXCLU de sa propre aura (`SurroundingFriends` retire `Tiles(Owner)` et RIEN ne
   le re-ajoute) -> la classe ne doit PAS declarer `create_effect_damage_bonus_for_attack`. Ce
   cran est le seul qui separe ce cas de `DestroyTheWitch_ExtraDamage` et
   `IconOfObstinacy_ExtraDmg`, dont les selecteurs FONT `+ Owner`.
3. Le CAP est un `Min(., ConfigVar(maxDmg))`, et son point de bascule est corrobore par une
   constante que le port NE LIT PAS (`buffMaxLevel`) : `extraDmg + buffMaxLevel x extraDmg_2`
   tombe EXACTEMENT sur `maxDmg`. C'est un temoin INDEPENDANT de la formule portee.
4. Les ordinaux ecrits aux sites sont figes (cf. CLAUDE.md : `probe_313` compare le mirror au
   build et redevient vert apres un renumerotage -- ce cran-ci garde la valeur MESUREE ici).

ASCII only (console cp1252)."""
from __future__ import annotations

#: #486-r15 -- les chemins dont une modification DOIT rejouer ce fichier. Ce fichier fige des
#: LITTERAUX (ordinaux, cles BC, constantes de gameconfig) et la FORME du port : tout ce qui les
#: porte entre au perimetre, plus les deux registres qui font exister les faces.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/first_among_traitors.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/playbook/friends_in_range.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/battle_query.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS AUX SITES (que `probe_313` ne voit pas -- il "
              "compare le mirror au build, pas le site), les deux cles `BC.Utilities` distinctes "
              "des deux faces DECISION, la formule `Min(Sum(., Multiply(.)), cap)` et son point "
              "de bascule corrobore par `buffMaxLevel`. Le gameconfig entre au perimetre : les "
              "valeurs comparees en sortent.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.first_among_traitors import (
    CHAOS_TRAIT, EXTRA_DMG_2_VAR, EXTRA_DMG_VAR, FIRST_AMONG_TRAITORS, MAX_DMG_VAR,
    FirstAmongTraitorsExtraDmgEffect, first_among_traitors_range)
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.playbook.adjacent_unit_preference import load_playbook
from engine.playbook.friends_in_range import FirstAmongTraitorsPlaybook
from engine.playbook.non_owner import load_playbook_non_owner

EFFECT_NAME = "FirstAmongTraitors_ExtraDmg"


def _effet(level=50, mult=100):
    e = FirstAmongTraitorsExtraDmgEffect(EFFECT_NAME)
    e.ability_level, e.ability_variables_multiplier = level, mult
    return e


def _ctx(att_id=2, owner_id=1, att_team=0, owner_team=0, att_pos=(3, 4), owner_pos=(3, 3),
         traits=("Chaos",), n=0):
    return {"att_id": att_id, "owner_id": owner_id, "att_team": att_team,
            "owner_team": owner_team, "att_pos": att_pos, "owner_pos": owner_pos,
            "att_traits": tuple(traits), "owner_total_attacks_made": {owner_id: n}}


# ---------------------------------------------------------------- 1. les TROIS faces au registre
def test_les_trois_faces_sont_au_registre():
    """`kit-coverage` annoncait « manque 1 » pour un passif a TROIS faces natives distinctes :
    `FirstAmongTraitorsPlaybook` (DECISION owner), `FirstAmongTraitorsNonOwnerPlaybook`
    (DECISION non-owner, portee des #477-r37) et `FirstAmongTraitors_ExtraDmgEffect` (COMBAT)."""
    aid = int(TriggeredAbilityType.FirstAmongTraitors)
    assert type(load_playbook(aid)).__name__ == "FirstAmongTraitorsPlaybook", \
        "face DECISION OWNER absente de `TRIGGERED_MOVE_PLAYBOOKS`"
    assert type(load_playbook_non_owner(aid)).__name__ == "FirstAmongTraitorsNonOwnerPlaybook", \
        "face DECISION NON-OWNER absente du registre non-owner"
    assert EFFECT_CLASSES.get(EFFECT_NAME) is FirstAmongTraitorsExtraDmgEffect, \
        "face COMBAT absente d'`EFFECT_CLASSES`"
    # `AOwnerEffectTriggeredAbility$$CreateBehaviour` = `AddEffect(GetEffectType() = 0x427, ...,
    # source = Owner, targets = Owner)` -> owner-effect PERMANENT pose a l'init de l'ability.
    assert ABILITY_INIT_OWNER_EFFECTS.get("FirstAmongTraitors") == [EFFECT_NAME], \
        "le poseur (`ABILITY_INIT_OWNER_EFFECTS`) manque : l'effet ne serait jamais seede offline"


def test_ordinaux_ecrits_aux_sites():
    """Les ordinaux MESURES a la conversion (build `rnca9r7q6c`). `probe_313` garde la BIJECTION
    mirror<->build ; ce cran-ci garde la VALEUR ecrite au site, qu'un renumerotage deplacerait
    sans faire rougir `probe_313`."""
    assert int(TriggeredAbilityType.FirstAmongTraitors) == 0x428      # 1064
    assert int(EffectType.FirstAmongTraitors_ExtraDmg) == 0x427       # 1063
    assert int(UnitTrait.Chaos) == 0x7ea                              # 2026
    assert int(AbilityConstantType.range) == 0x16                     # 22
    assert int(AbilityVariableType.extraDmg) == 0x08
    assert int(AbilityVariableType.extraDmg_2) == 0x09
    assert int(AbilityVariableType.maxDmg) == 0x0d
    # Le meme ordinal nomme AUTRE CHOSE dans les enums voisins -- c'est ce qui rend le NOM
    # obligatoire (CLAUDE.md : une confusion d'enums est SILENCIEUSE en ordinal).
    assert EffectType(1064).name != "FirstAmongTraitors"
    assert TriggeredAbilityType(1063).name != "FirstAmongTraitors_ExtraDmg"


# --------------------------------------------------- 2. le porteur est EXCLU (pas de patte SELF)
def test_pas_de_patte_self_le_porteur_est_exclu():
    """`CreateTargetSelector` = `UnitsWithTrait(SurroundingFriends(Owner, ConfigConst(range), true,
    3), 0x7ea, 3)`. `DSLSelectors$$SurroundingFriends` se deplie en
    `Friends(unit, Units(SurroundingTiles(unit, range) - Tiles(unit), ...))` : le porteur est
    RETIRE, et AUCUN `op_Addition Owner` ne le re-ajoute (contrairement a
    `DestroyTheWitch_ExtraDamage` et `IconOfObstinacy_ExtraDmg`).

    Consequence de PORT : la classe ne doit PAS declarer `create_effect_damage_bonus_for_attack`
    -- l'heritage de `BaseEffect` rend `None`, et c'est le comportement voulu. Declarer cette patte
    donnerait a Abaddon un bonus que le natif ne lui donne pas (mutant `patte SELF ajoutee`, rouge
    en live)."""
    assert "create_effect_damage_bonus_for_attack" \
        not in vars(FirstAmongTraitorsExtraDmgEffect), \
        ("la classe declare une patte SELF -- le selecteur natif EXCLUT le porteur "
         "(`SurroundingTiles - Tiles(Owner)`, aucun `op_Addition Owner`)")
    # Et le canal AURA l'exclut aussi explicitement (l'agregateur le fait deja, ce cran garde la
    # redondance du port au cas ou un appelant tiers ne le ferait pas).
    e = _effet()
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(att_id=1, owner_id=1)) is None


# ------------------------------------------------------------------- 3. les gates, un par un
@pytest.mark.parametrize("traits,attendu", [(("Chaos",), True), (("Imperial",), False),
                                            ((), False), (("Chaos", "Psyker"), True)])
def test_gate_trait_chaos(traits, attendu):
    """`UnitsWithTrait(., 0x7ea = UnitTrait.Chaos, 3)` -- le pseudo-trait de GRANDE-ALLIANCE, qui
    n'existe QUE dans le substrat d'ENTITE (`BaseUnitComponent+0x40`), jamais dans
    `gameconfig.unit().traits`."""
    eb = _effet().create_aura_attack_damage_bonus_for_ally(_ctx(traits=traits))
    assert (eb is not None) is attendu
    assert CHAOS_TRAIT.name == "Chaos"


@pytest.mark.parametrize("apos,attendu", [((3, 3), True), ((3, 4), True), ((3, 5), True),
                                          ((3, 6), False), ((0, 0), False)])
def test_gate_distance_inclusif(apos, attendu):
    """`SurroundingTiles(Owner, range)` = le DISQUE hex de rayon `range` (= 2). Le comparateur est
    `<=` : distance 2 INCLUSE, distance 3 exclue. Le porteur pose en (3,3)."""
    assert first_among_traitors_range() == 2, "constante `range` du gameconfig vivant"
    eb = _effet().create_aura_attack_damage_bonus_for_ally(_ctx(att_pos=apos))
    assert (eb is not None) is attendu, "distance %s -> %s attendu" % (apos, attendu)


def test_gate_equipe():
    """`Friends(unit, ...)` -- meme equipe que le PORTEUR."""
    assert _effet().create_aura_attack_damage_bonus_for_ally(_ctx(att_team=1)) is None


def test_aucun_gate_de_type_d_attaque():
    """`CreateEffectDamageBonusForAttack` = `ForAddition(get_OwnerIsCaster, CurrentDamageBonus)` --
    UN SEUL noeud de trigger. Ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack`, ni
    `CurrentAbilityIs`, ni `HasTrait(Target, ...)` : le bonus vaut pour TOUTES les attaques du
    beneficiaire. Un port qui recopierait le gate melee de son voisin `DestroyTheWitch` annulerait
    le bonus sur toute attaque a distance."""
    c = _ctx()
    for cle, val in (("is_melee", False), ("is_melee", True), ("is_normal_attack", False),
                     ("tgt_traits", ()), ("target_armor_reduced", False)):
        eb = _effet().create_aura_attack_damage_bonus_for_ally({**c, cle: val})
        assert eb is not None and eb.value > 0, "gate parasite sur %s=%r" % (cle, val)


# ------------------------------------------------------------------------- 4. la MAGNITUDE
@pytest.mark.parametrize("mult", [100, 180])
def test_magnitude_min_sum_multiply(mult):
    """`Min(Sum(ConfigVar(extraDmg), Multiply(TotalAttacksMade(EffectSource), ConfigVar(extraDmg_2))),
    ConfigVar(maxDmg))`, les trois variables indexees sur l'`AbilityState` de la SOURCE."""
    base = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, 50, multiplier_pct=mult))
    per = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_2_VAR, 50, multiplier_pct=mult))
    cap = int(ability_var(FIRST_AMONG_TRAITORS, MAX_DMG_VAR, 50, multiplier_pct=mult))
    assert base > 0 and per > 0 and cap > base, \
        "regime DEGENERE : sans base/pas/cap non nuls, ce test ne prouverait rien"
    e = _effet(mult=mult)
    for n in (0, 1, 2, 5, 13, 14, 100):
        assert e._current_damage_bonus(n) == min(base + n * per, cap), "n=%d mult=%d" % (n, mult)


def test_le_cap_est_corrobore_par_une_constante_que_le_port_ne_lit_pas():
    """`buffMaxLevel` (= 13) est une CONSTANTE du gameconfig qu'AUCUNE ligne du port ne consulte.
    `extraDmg + buffMaxLevel x extraDmg_2` doit tomber EXACTEMENT sur `maxDmg` : c'est un temoin
    INDEPENDANT de la formule portee -- si la lecture `0x0d = maxDmg` etait fausse, elle ne
    coinciderait pas avec ce point."""
    buff_max = ability_var(FIRST_AMONG_TRAITORS, "buffMaxLevel", is_constant=True)
    assert buff_max is not None, "constante `buffMaxLevel` absente du gameconfig"
    for lvl in (1, 10, 50):
        base = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, lvl))
        per = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_2_VAR, lvl))
        cap = int(ability_var(FIRST_AMONG_TRAITORS, MAX_DMG_VAR, lvl))
        assert base + int(buff_max) * per == cap, "niveau %d" % lvl


def test_magnitude_indexee_sur_le_PORTEUR_pas_sur_le_beneficiaire():
    """Les quatre noeuds de `CurrentDamageBonus` lisent `EffectSource(effect)` : le compteur pris
    est celui du PORTEUR, resolu par `owner_id` dans la map `owner_total_attacks_made`. Une lecture
    indexee sur l'attaquant rendrait une autre valeur des que les deux different."""
    e = _effet(mult=100)
    c = _ctx(owner_id=1, att_id=2, n=0)
    c["owner_total_attacks_made"] = {1: 3, 2: 40}      # porteur 3, beneficiaire 40
    eb = e.create_aura_attack_damage_bonus_for_ally(c)
    base = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, 50))
    per = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_2_VAR, 50))
    assert eb is not None and eb.value == base + 3 * per, \
        "le compteur lu n'est pas celui du PORTEUR (`EffectSource`)"


def test_compteur_absent_degradation_NOMMEE():
    """Cle absente = canal qui ne publie pas le compteur -> le terme croissant est OMIS, jamais
    devine. Le sens de l'ecart est alors toujours un MANQUE (`n = 0`), jamais un sur-compte."""
    c = _ctx()
    c.pop("owner_total_attacks_made")
    eb = _effet().create_aura_attack_damage_bonus_for_ally(c)
    assert eb is not None and eb.value == int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, 50))


def test_sans_ability_level_aucune_contribution():
    """`ConfigVar` sans `AbilityState` -> pas de magnitude : « present != applique »."""
    e = FirstAmongTraitorsExtraDmgEffect(EFFECT_NAME)
    e.ability_level, e.ability_variables_multiplier = None, 100
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx()) is None


# -------------------------------------------- 5. la face DECISION owner (formule + geometrie)
class _W:
    """Le minimum de l'interface `weights` que la feuille consomme."""

    def __init__(self, val):
        self.val = val

    def sub(self, cat, key):
        return self.val if key == FirstAmongTraitorsPlaybook.WEIGHT_KEY else 0


def test_playbook_owner_compte_les_amis_chaos_du_disque_tuile_centrale_COMPRISE():
    """`GetSurroundingUnits(tile, range, case.unit, includeCenter = true)` puis, PAR UNITE,
    `u != case.unit && HasTrait(u, 0x7ea)` ; `value += w`.

    La tuile CENTRALE compte (`includeCenter = true`) -- c'est ce qui distingue cette geometrie de
    celle du `CreateTargetSelector` de l'effet, qui RETIRE les tuiles du porteur."""
    pb = FirstAmongTraitorsPlaybook()
    ctx = {"friend_units": [
        {"pos": (3, 3), "traits": ("Chaos",)},          # SUR la tuile candidate -> compte
        {"pos": (3, 4), "traits": ("Chaos",)},          # distance 1             -> compte
        {"pos": (3, 5), "traits": ("Chaos",)},          # distance 2             -> compte
        {"pos": (3, 6), "traits": ("Chaos",)},          # distance 3             -> HORS
        {"pos": (2, 3), "traits": ("Imperial",)},       # distance 1, pas Chaos  -> HORS
        {"pos": (4, 3), "traits": ()},                  # distance 1, sans trait -> HORS
    ]}
    assert pb.calculate_movement_utility_in_steps((3, 3), ctx, _W(10)) == 30.0
    # Poids nul -> aucun terme (le natif somme `w` par unite : `w = 0` rend 0).
    assert pb.calculate_movement_utility_in_steps((3, 3), ctx, _W(0)) == 0.0


def test_playbook_owner_le_mover_ne_se_compte_PAS_lui_meme():
    """`u != case.unit` -- le corps natif l'ecrit EXPLICITEMENT, la ou ses deux voisins de module
    (`AstartesBanner`, `Kardiocore`) ne l'ecrivent pas. Cote port, `friend_units` du
    `tile_leaf_ctx` est DEJA self-exclu : le cran garde que rien ne re-injecte le sujet."""
    pb = FirstAmongTraitorsPlaybook()
    ctx = {"friend_units": [], "self_pos": (3, 3), "uid": 1}
    assert pb.calculate_movement_utility_in_steps((3, 3), ctx, _W(10)) == 0.0


def test_playbook_owner_lit_la_CONSTANTE_range():
    """`FirstAmongTraitorsAbility$$GetRange` = `GetNumberConstant(config, 0x16)` -- un
    `AbilityConstantType`, pas un `AbilityVariableType`. Le meme accesseur que la face NON-OWNER
    et que le `CreateTargetSelector` de l'effet."""
    assert FirstAmongTraitorsPlaybook.CONST_RANGE is AbilityConstantType.range
    assert FirstAmongTraitorsPlaybook().get_range() == first_among_traitors_range() == 2
    assert FirstAmongTraitorsPlaybook.WEIGHT_KEY == "FIRSTAMONGTRAITORS_SurroundingChaosFriend"


def test_les_deux_faces_decision_lisent_des_cles_BC_DIFFERENTES():
    """Deux litteraux distincts du binaire (`string_literals.tsv`), dans deux SECTIONS distinctes
    de `BC.Utilities.Default`. Les confondre annulerait une des deux faces sans erreur."""
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as NO
    assert FirstAmongTraitorsPlaybook.WEIGHT_KEY != NO.KEY
    assert NO.KEY == "FIRSTAMONGTRAITORS_SurroundingOwner"
