"""#1033 -- `1107 Reveal` (`eldarNpc2Warlock`) : la face EXECUTION, son gate dynamique, l'effet
1219 `Revealed`, et le CORRECTIF de l'audit qui comptait `Maugetar` comme un no-op.

CE QUE CE FICHIER GARDE, et pourquoi chaque etage existe :

  0. les TROIS registres dans le meme commit (`ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`,
     `EFFECT_CLASSES`) -- l'entree d'effet est la moins visible et la plus facile a oublier : sans
     elle l'ability poserait un `BaseEffect` NU, donc INERTE, en rendant `ported: True` ;
  1. le MASQUE et sa decomposition EXHAUSTIVE -- le piege de forme est ici la surcharge
     `TargetingOptions..ctor(&opts, &preset, flags)`, dont le corps fait `Rules = flags |
     template.Rules` : le litteral visible au ctor (`0x6000002`) N'EST PAS le masque effectif ;
  2. le litteral `AbilityAttackType` ;
  3. l'ARBRE, terme a terme (une seule feuille, source != cible, duree LUE du gameconfig) ;
  4. le GATE DYNAMIQUE et ses trois sorties, avec les contre-epreuves qui separent chaque conjoint ;
  5. l'EFFET : magnitude, les trois noeuds de son trigger, et sa FACE native ;
  6. le CORRECTIF DE L'AUDIT (`audit_combat_ability_coverage`) : un nom d'`activeAbilities` qui
     n'est pas un `ActiveAbilityType` n'est PAS un no-op silencieux.

TOUT est offline : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import pytest

import audit_combat_ability_coverage as AUDIT
import enum_maps as EM

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.revealed import AELDARI_FACTION, RevealedEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.effects_state import EffectsState
from engine.entities.selectors.accessors import Target
from engine.entities.selectors.tiles import Caster
from engine.entities.unit_context import UnitContext
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.loki.reveal import RevealAbility, REVEAL_ID, REVEALED, reveal_tree
from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_FALSE,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import OwnerComponent, StatsComponent, UnitComponent
from engine.runner.state import State

#: L'ORDINAL FIGE A LA CONVERSION (#270-r1-r1-r3) : `probe_313` compare le MIRROR au BUILD, donc il
#: redevient vert des qu'on regenere le mirror apres un renumerotage -- alors que la valeur ECRITE
#: au site, elle, aurait change. Ce couple-ci est le cran du dessous.
REVEAL_ORDINAL = 1107
REVEALED_ORDINAL = 1219

#: Le masque EFFECTIF, re-ecrit ici en DUR pour que le test rougisse si le port change de valeur --
#: `0x4002` (preset `<TargetingOptions statics>+0x180`) OR `0x6000002` (flags additionnels du ctor).
MASQUE_EFFECTIF = 0x6004002

#: `eldarNpc2Warlock` est le SEUL porteur de 1107 (mesure `unit_map`), et il est AELDARI.
WARLOCK = "eldarNpc2Warlock"
#: Un autre Aeldari, pour jouer le role du mort AMI ; et un T'au, pour la contre-epreuve de faction.
AELDARI_ALLIE, NON_AELDARI = "eldarRanger", "tauCrisis"


# ================================================================================================
#  LE MONTAGE -- fixture NOMMEE et reutilisable (jamais inline)
# ================================================================================================

def _unit(state, vis, team, *, alive=True):
    """Une entite-unite minimale : `UnitComponent` (visual_id + alive), `OwnerComponent` (team) et
    un `StatsComponent` porteur du `UnitContext`. C'est exactement le substrat que lisent
    `units_are_friends` (equipe), `_faction` (visual_id) et le balayage de `death_source`."""
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=alive))
    e.add_component(OwnerComponent(team=team))
    e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id=vis)))
    return e.id


class MontageReveal:
    """Le montage de `Reveal` : un caster Aeldari (team 1), une cible ennemie (team 2), et ce qu'il
    faut pour fabriquer des MORTS imputables a qui on veut.

    REUTILISABLE : `tuer(visual_id, team, par=<id>)` ajoute un cadavre dont la `DamageSource`
    designe `par` -- c'est le seul substrat que lit
    `IdunBattle.Core.Services.BattleQuery$$GetDeadUnitsKilledBy` (`UnitComponent+0x108`)."""

    def __init__(self):
        self.state = State()
        self.state.effects = EffectsState()
        self.caster = _unit(self.state, WARLOCK, 1)
        self.cible = _unit(self.state, NON_AELDARI, 2)
        self.ability = RevealAbility()

    def tuer(self, visual_id, team, *, par, imputable=True):
        """Un cadavre `visual_id`/`team` dont le tueur est `par`. `imputable=False` laisse
        `death_source` a `None` -- la forme du `!ds.HasValue` natif (cadavre-au-chargement)."""
        uid = _unit(self.state, visual_id, team, alive=False)
        if imputable:
            uc = self.state.get_entity(uid).get_component(UnitComponent)
            uc.death_source = (int(par), 0, None)
        return uid

    def raison(self, cible=None):
        """Le verdict du gate dynamique pour cette cible (defaut : la cible ennemie du montage)."""
        return self.ability.get_dynamic_invalid_target_reason(
            self.state, self.caster, self.cible if cible is None else cible)


@pytest.fixture
def montage():
    return MontageReveal()


# ================================================================================================
#  Etage 0 -- LES TROIS REGISTRES, dans le meme commit
# ================================================================================================

def test_etage0_les_trois_registres_portent_reveal():
    """L'entree d'EFFET est la moins visible des trois et la seule dont l'oubli est SILENCIEUX :
    sans `EFFECT_CLASSES['Revealed']`, `EffectFactory` materialise un `BaseEffect` nu -- l'ability
    rend `ported: True`, pose bien un effet, et cet effet ne contribue RIEN."""
    assert ABILITY_CLASSES.get(REVEAL_ORDINAL) is RevealAbility
    assert ABILITY_ATTACK_TYPE.get(ActiveAbilityType.Reveal) == AbilityAttackType.Others
    assert EFFECT_CLASSES.get(EffectType.Revealed.name) is RevealedEffect


def test_etage0_les_ordinaux_sont_figes_au_site():
    """Cran du dessous de `probe_313` : il compare le MIRROR au BUILD, donc il redevient vert des
    qu'on regenere le mirror -- ce test-ci garde la valeur MESUREE a la conversion."""
    assert int(ActiveAbilityType.Reveal) == REVEAL_ORDINAL == RevealAbility.ABILITY_TYPE
    assert int(EffectType.Revealed) == REVEALED_ORDINAL == REVEALED


def test_etage0_le_contrat_de_disjonction_est_tenu():
    """Une ability PORTEE porte son masque sur SA classe, jamais dans la table des non-portees."""
    assert REVEAL_ORDINAL not in TARGETING_OPTIONS_UNPORTED


# ================================================================================================
#  Etage 1 -- LE MASQUE, et sa decomposition EXHAUSTIVE
# ================================================================================================

def test_etage1_le_masque_est_l_union_du_preset_et_des_flags():
    """LE PIEGE DE FORME. `...RevealAbility$$.ctor` appelle la surcharge PRESET+FLAGS
    `IdunBattle.Core.Services.TargetingOptions$$.ctor(this, template, additionalRules)`, dont le
    corps LU fait `this.Rules@+0x28 = additionalRules | template.Rules@+0x28`.

    Prendre le litteral visible (`0x6000002`) pour le masque effectif PERDRAIT `TargetIsEnemy`
    (0x4000) -- l'ability accepterait alors de marquer un ALLIE."""
    assert RevealAbility.TARGETING_OPTIONS.rules == MASQUE_EFFECTIF
    assert MASQUE_EFFECTIF == (0x4002 | 0x6000002)
    assert MASQUE_EFFECTIF & int(TR.TargetIsEnemy), "le bit du PRESET a ete perdu"


def test_etage1_la_decomposition_ne_laisse_aucun_bit_residuel():
    """Un bit non nomme serait une regle qu'on applique sans savoir laquelle."""
    attendus = (TR.TargetMatchesDynamicRule | TR.TargetIsEnemy
                | TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls)
    assert RevealAbility.TARGETING_OPTIONS.rules == int(attendus)


def test_etage1_le_bit_dynamique_est_pose_donc_le_gate_est_consulte():
    """`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` n'invoque la regle-delegue
    `options+0x38` QUE sous le bit `TargetMatchesDynamicRule` (0x2). Sans lui, tout l'etage 4 de ce
    fichier serait du code mort."""
    assert RevealAbility.TARGETING_OPTIONS.rules & int(TR.TargetMatchesDynamicRule)


def test_etage1_portee_et_force_melee_viennent_du_preset():
    """`<preset +0x180>+0x08` <- `TargetingRange statics+0x18` = `RANGE_FROM_CONFIG` (la portee est
    `constants.range`, ce que dit l'i2), et `+0x20` = 1 = `RangedBool.False`."""
    opt = RevealAbility.TARGETING_OPTIONS
    assert opt.range == RANGE_FROM_CONFIG and opt.range.use_range_from_config is True
    assert opt.force_melee_target == RANGED_BOOL_FALSE
    assert opt.self_cast is False                       # `<preset +0x180>+0x00` = 0


# ================================================================================================
#  Etage 3 -- L'ARBRE, terme a terme
# ================================================================================================

def test_etage3_l_arbre_est_une_seule_feuille_addeffect():
    """`...RevealAbility$$ExecuteBehaviour` passe le resultat d'`AddEffect` DIRECTEMENT a
    `AActiveAbility$$Execute` : aucun `op_Addition`, donc aucune attaque, aucun `ResetMovement`."""
    t = reveal_tree()
    assert isinstance(t, AddEffect)
    assert t.effect_type == REVEALED_ORDINAL and t.name == EffectType.Revealed.name


def test_etage3_la_source_et_la_cible_sont_DEUX_selecteurs_differents():
    """`source = Caster@+0x48`, `targets = Target@+0x60`. Les confondre (comme le fait
    `FireAndReposition`, dont les deux lisent `+0x48`) poserait le marquage SUR LE CASTER."""
    t = reveal_tree()
    assert isinstance(t.target_sel, Target)
    assert isinstance(t.source_ref, Caster)


def test_etage3_la_duree_est_LUE_du_gameconfig_pas_un_litteral():
    """`TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))`. Un litteral en dur se perimerait au
    prochain equilibrage sans que rien ne le signale."""
    attendu = ability_var(REVEAL_ID, AbilityConstantType.nrOfRounds.name, is_constant=True)
    assert attendu is not None and reveal_tree().duration_rounds == attendu
    assert reveal_tree().duration_turns is None, "le natif passe un TurnsFromRounds, pas des TOURS"


def test_etage3_l_abilitystate_est_transmis():
    """3e argument natif (`AActiveAbility$$get_AbilityStateReference`). INERTE pour la magnitude de
    CET effet (une constante), mais le natif le PASSE -- on transcrit ce qui est ecrit."""
    assert reveal_tree().scale_from_source is True


def test_etage3_le_cast_pose_l_effet_sur_la_CIBLE(montage):
    """La boucle complete, sans runner : le cast marque la CIBLE, pas le caster."""
    out = montage.ability.execute_behaviour(montage.state, montage.caster, montage.cible)
    assert out is not None and out["effect_placed"] is True
    assert montage.state.effects.has_effect(montage.cible, REVEALED_ORDINAL)
    assert not montage.state.effects.has_effect(montage.caster, REVEALED_ORDINAL)


# ================================================================================================
#  Etage 4 -- LE GATE DYNAMIQUE, conjoint par conjoint
# ================================================================================================

def test_etage4_sans_mort_imputable_la_cible_est_REFUSEE(montage):
    """Troisieme sortie du natif : `dead.Count == 0` -> `return 2`."""
    assert montage.raison() == int(TR.TargetMatchesDynamicRule)


def test_etage4_un_aeldari_ami_defait_par_la_cible_VALIDE(montage):
    """`GetDeadUnitsKilledBy(target)` filtre par `HasFaction(Aeldari) & IsFriend(caster)` -> > 0."""
    montage.tuer(AELDARI_ALLIE, 1, par=montage.cible)
    assert montage.raison() == 0


def test_etage4_une_cible_DEJA_revealed_est_refusee(montage):
    """Deuxieme sortie : `HasEffect(target, 0x4c3)` -> `return 2`, AVANT meme de balayer les morts.

    Contre-epreuve construite pour etre SEPARANTE : on pose d'abord le mort qui rendrait la cible
    valide, de sorte que le refus ne puisse venir QUE du `HasEffect`."""
    montage.tuer(AELDARI_ALLIE, 1, par=montage.cible)
    assert montage.raison() == 0, "temoin : sans l'effet, cette cible est VALIDE"
    montage.ability.execute_behaviour(montage.state, montage.caster, montage.cible)
    assert montage.raison() == int(TR.TargetMatchesDynamicRule)


def test_etage4_sans_cible_le_natif_rend_ZERO(montage):
    """Premiere sortie, LUE : `if (target == null) return 0;`. Ce n'est pas une permissivite du
    port -- c'est ce que le decompile ecrit."""
    assert montage.ability.get_dynamic_invalid_target_reason(
        montage.state, montage.caster, None) == 0


@pytest.mark.parametrize("cas,kw", [
    ("le mort est ENNEMI du caster (IsFriend faux)", {"team": 2}),
    ("le mort n'est PAS Aeldari (HasFaction faux)", {"visual_id": NON_AELDARI}),
    ("le cadavre n'a pas de DamageSource (!ds.HasValue)", {"imputable": False}),
])
def test_etage4_chaque_conjoint_du_filtre_separe(montage, cas, kw):
    """CONTRE-EPREUVES -- chacune casse UN conjoint et doit suffire a refuser la cible.

    Sans elles, un port qui ignorerait `HasFaction` ou `IsFriend` passerait le test positif."""
    montage.tuer(kw.get("visual_id", AELDARI_ALLIE), kw.get("team", 1),
                 par=montage.cible, imputable=kw.get("imputable", True))
    assert montage.raison() == int(TR.TargetMatchesDynamicRule), cas


def test_etage4_un_mort_tue_par_QUELQU_UN_D_AUTRE_ne_compte_pas(montage):
    """`get_KillerId(ds) == killer.Id` : c'est bien la CIBLE qui doit avoir tue, pas n'importe qui.

    Regime SEPARANT : le mort est Aeldari ET ami -- seul le tueur differe."""
    autre = _unit(montage.state, NON_AELDARI, 2)
    montage.tuer(AELDARI_ALLIE, 1, par=autre)
    assert montage.raison() == int(TR.TargetMatchesDynamicRule)


# ================================================================================================
#  Etage 5 -- L'EFFET 1219
# ================================================================================================

def _malus(faction=AELDARI_FACTION, owner_team=2, team=1):
    """Le canal `CreateEffectDamageMalusForDefense` avec le contexte d'attaquant du builder."""
    return RevealedEffect(name=EffectType.Revealed.name).create_effect_damage_malus_for_defense(
        attacker_ctx={"faction": faction, "owner_team": owner_team, "team": team})


def test_etage5_la_magnitude_est_la_CONSTANTE_extradmgpct():
    """`GetNumberConstant(0xf = extraDmgPct)` -- une CONSTANTE, donc aucun niveau a resoudre.
    La lire comme un `GetVariableForLevel` rendrait `None` (les `variables` de Reveal sont VIDES)."""
    attendu = ability_var(REVEAL_ID, AbilityConstantType.extraDmgPct.name, is_constant=True)
    assert attendu and RevealedEffect._extra_dmg_pct() == attendu
    b = _malus()
    assert b is not None and b.kind == "PercentIncrease" and b.value == attendu


def test_etage5_le_bonus_porte_sur_le_degat_RECU():
    """`get_OwnerIsTarget` : le porteur est le DEFENSEUR -> `owner_is_caster = False`."""
    assert _malus().owner_is_caster is False


def test_etage5_la_face_native_est_defender():
    """`RevealedEffect` derive de `BaseEffect` (`frida/classes.tsv`) et implemente le slot 0x1a
    DIRECTEMENT -> `defenseModifiers`. Son voisin de forme `MarkerlightEffect` derive de
    `DamageModifierAbilityEffect` et sort, LUI, par le forwarder ATTAQUANT : recopier sa face
    aurait change le nombre de `Fix64.Round`."""
    assert RevealedEffect.DEFENSE_MALUS_NATIVE_FACE == "defender"


@pytest.mark.parametrize("cas,kw", [
    ("attaquant non-Aeldari (HasFaction faux)", {"faction": "Tau"}),
    ("attaquant AMI du porteur (AreEnemies faux)", {"team": 2}),
    ("equipe de l'attaquant NON MESUREE", {"team": None}),
    ("equipe du porteur NON MESUREE", {"owner_team": None}),
])
def test_etage5_chaque_noeud_du_trigger_ferme(cas, kw):
    """Les trois noeuds de `GetAttackModifierTrigger`, plus le TRI-ETAT : une equipe non mesuree
    FERME le gate. Supposer l'inimitie ferait mordre le bonus sur du tir allie."""
    assert _malus(**kw) is None, cas


def test_etage5_aucun_gate_de_nature_de_coup():
    """AUCUN `IsRangedAttack`/`IsMeleeAttack` dans le trigger natif -- contraste `MarkerlightEffect`.
    En ajouter un refuserait des coups que le natif accepte."""
    e = RevealedEffect(name=EffectType.Revealed.name)
    ctx = {"faction": AELDARI_FACTION, "owner_team": 2, "team": 1}
    for is_melee in (True, False, None):
        assert e.create_effect_damage_malus_for_defense(
            is_melee=is_melee, attacker_ctx=ctx) is not None, is_melee


# ================================================================================================
#  Etage 6 -- LE CORRECTIF DE L'AUDIT (le livrable `Maugetar`)
# ================================================================================================

def test_etage6_maugetar_n_est_PAS_un_activeabilitytype():
    """LE FAIT QUI TRANCHE TOUT LE CAS. Mesure sur le BUILD (`frida/enums.tsv`) autant que sur le
    mirror : `Maugetar` n'est d'AUCUN `ActiveAbilityType`, il est `TriggeredAbilityType` 1498.
    Aucun `ActiveAbilityMessage` ne peut donc le designer, et aucune cle ne peut entrer dans
    `ABILITY_CLASSES` : le porter etait IMPOSSIBLE, pas difficile."""
    assert "Maugetar" not in ActiveAbilityType.__members__
    assert [k for k, v in EM.ACTIVE_ABILITY_TYPE.items() if v == "Maugetar"] == []
    assert [k for k, v in EM.PASSIVE_ABILITY_TYPE.items() if v == "Maugetar"] == [1498]


def test_etage6_l_audit_ne_compte_plus_maugetar_dans_les_no_op():
    """LA REGRESSION FERMEE. Le generateur resolvait le nom dans le SEUL `ACTIVE_ABILITY_TYPE` ;
    un nom absent rendait `aid = None`, donc `None in ABILITY_CLASSES` = False, donc « NO-OP ».
    C'est ainsi que `Maugetar` figurait au tableau des no-op avec un id `?`."""
    rows = AUDIT.collect()
    par_nom = {r[1]: r for r in rows}
    assert par_nom["Maugetar"][2] == "HORS-ACTIVE"
    assert "Maugetar" not in {r[1] for r in rows if r[2] == "NO-OP"}


def test_etage6_l_audit_dit_l_enum_REEL_et_le_registre_qui_le_porte():
    """Un verdict doit dire OU vit vraiment le nom, et si CETTE face-la est portee -- sinon on
    remplace un faux no-op par un trou muet. `Maugetar` est monte par `RELIC_ABILITY_TRIGGERS`
    (c'est une relique) : un predicat qui n'aurait regarde qu'`ABILITY_TRIGGERS` aurait rendu
    « NON PORTEE », ce qui etait le premier etat de ce correctif."""
    cat = {r[1]: r[3] for r in AUDIT.collect()}["Maugetar"]
    assert "TriggeredAbilityType(1498)" in cat
    assert "PORTEE via `RELIC_ABILITY_TRIGGERS`" in cat


def test_etage6_reveal_est_desormais_PORTEE_dans_l_audit():
    rows = {r[1]: r for r in AUDIT.collect()}
    assert rows["Reveal"][0] == REVEAL_ORDINAL and rows["Reveal"][2] == "PORTED"


def test_etage6_un_nom_d_AUCUN_enum_reste_un_signal(monkeypatch):
    """Le correctif ne doit pas fabriquer un silence : si un nom n'est dans AUCUN enum, l'audit
    doit le dire (`INCONNU`) au lieu de le ranger avec les inversions de voie. C'est le cas qui
    signalerait une divergence gameconfig <-> build."""
    monkeypatch.setattr(AUDIT, "_AUTRES_ENUMS", ())      # plus aucun enum de repli
    par_nom = {r[1]: r for r in AUDIT.collect()}
    assert par_nom["Maugetar"][2] == "INCONNU"
    assert "nom d'AUCUN enum" in par_nom["Maugetar"][3]


def test_etage6_le_predicat_de_portage_est_DERIVE_pas_enumere():
    """`_triggered_portee` balaie TOUT dict majuscule du module de registres. Une liste blanche ne
    peut pas montrer le registre qu'elle a oublie -- et c'est exactement la faute commise ici :
    ecrit avec le seul `ABILITY_TRIGGERS`, il rendait « NON PORTEE » pour une relique."""
    from engine.runner.operations.triggers.dispatch import registry as REG
    assert AUDIT._triggered_portee("Maugetar") == "RELIC_ABILITY_TRIGGERS"
    assert "Maugetar" not in REG.ABILITY_TRIGGERS, "le temoin de la faute a disparu"
    assert AUDIT._triggered_portee("NomQuiNExistePas__1033") is None
