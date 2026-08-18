"""#462-r4b-r1-r1 -- GARDES OFFLINE du RAYON DE SOUFFLE de #462-r4b-r1.

#462-r4b-r1 a deplace l'additif DEFENSEUR dans le slot PRE-PERCAGE de l'attaquant
(`AttackDamageOperation._apply_defender_flat_reductions`), mais **un seul de ses TROIS producteurs**
avait ete confronte en COMBAT (`ExemplarOfHate_Target`). Ce fichier verrouille les DEUX autres et,
surtout, la porte par laquelle un QUATRIEME entrerait sans mesure.

Ce que chaque garde est SEUL a voir :

  1. `test_le_registre_des_producteurs_...` -- un producteur NEUF d'additif defenseur entre dans
     `engine/` sans passer par ce dossier. C'est EXACTEMENT le vice de ce cas : le canal a cesse
     d'etre inerte sans que personne ne le voie.
  2. `test_les_magnitudes_..._INTEGRALES` -- le residu de TRONCATURE PAR TERME. Le natif applique
     `FixMath.NET.Fix64$$op_Explicit` (`raw >> 32`) a CHAQUE `Addition` avant de sommer ; le port
     somme des flottants puis arrondit. Les deux coincident tant que chaque producteur rend un
     ENTIER -- ce garde le MESURE au lieu de le supposer.
  3. `test_le_combat_thread_...` -- le fork prediction/combat sur l'axe MAGNITUDE (le pendant de
     celui que #462-r4b-r1 a ferme sur l'axe PLACEMENT).
  4/5. les deux regimes MESURES, chacun avec son contre-modele ECRIT.

Chiffres LUS de `probe_462_r4b_r1_r1_defender_additive_carriers.py` (runner `MC1_67`/seed 112112).
ASCII only.
"""
from __future__ import annotations

import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.entities.effects.loki.damage_reduction import (                 # noqa: E402
    ChronometronExtraDamageEffect, ExemplarOfHateTargetEffect,
    HeraldOfTheApocalypseExtraDamageEffect, NeuroparasiteEffect)
from engine.entities.effects.loki.holy_duel import HolyDuelDmgReductionEffect  # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation           # noqa: E402
from engine.services.damage_modifiers import (                              # noqa: E402
    DamageModifiers, apply_all_modifiers)
from engine.services.damage_prediction import apply_pierce_and_modifiers    # noqa: E402

# --- Les TROIS producteurs d'additif DEFENSEUR, et le chemin par lequel chacun est CONFRONTE. ---
# La cle est `<module>.<classe>` ; la valeur dit ce qui l'atteste. Un producteur qui apparait dans
# `engine/` sans etre ici fait ROUGIR le premier test : c'est le cliquet du canal.
_DR = "entities.effects.loki.damage_reduction."
PRODUCTEURS_ATTESTES = {
    _DR + "ExemplarOfHateTargetEffect":
        "#462-r4b-r1 (PR #548) -- blackAbaddon, 7730 -> 2596 bit-exact",
    _DR + "ChronometronExtraDamageEffect":
        "#462-r4b-r1-r1 -- bras `chrono`, port 61 == natif 61, contre-modele 950",
    _DR + "NeuroparasiteEffect":
        "#462-r4b-r1-r1 -- bras `neuro`, port 4448 == natif 4448, contre-modele 3888",
    "entities.effects.loki.holy_duel.HolyDuelDmgReductionEffect":
        "#549 -- `probe_549_holy_duel.py --step defense` : le champion encaisse le coup de son "
        "duelliste (il y est CONTRAINT, `ForcedAttackTargetsComponent`), port 1196 == natif 1196, "
        "contre-modele ECRIT (instance 1093 consommee) 2027",
    _DR + "HeraldOfTheApocalypseExtraDamageEffect":
        "#547-r2 -- bras `herald` (entre par la PR #836 SANS confrontation, c'est ce cliquet qui "
        "l'a vu) : blackHaarken caste l'active 1020 a portee 2, l'effet 1027 est LU sur ses "
        "porteurs dans `decisionView`, puis darkaHellblaster frappe l'un d'eux (armure forcee "
        "50000 -> branche PERCAGE, pierce 65, %-list attaquant 1.25). additif = 1795 "
        "(`extraDmg[50] = 997 x mult 180`), port 3151 == natif 3151 (delta PV), contre-modele "
        "ECRIT (placement POST-%-list) 3265",
}

# --- Bras `chrono` : `Chronometron_ExtraDamage` (1550), profil `Physical` (PiercingRatio = 1). ---
CHRONO_BASE = 5202          # valeur TIREE reconstituee du ledger live (port 61 / contre-modele 950)
CHRONO_ADD = 898.0          # `extraDmg[50] x mult 180` -- MESURE dans `def_mods.additive`
CHRONO_PIERCE, CHRONO_ARMOR = 1, 50000
CHRONO_NATIF, CHRONO_POST = 61, 950

# --- Bras `neuro` : `Neuroparasite` (1218), profil `Psychic` (PiercingRatio = 100). ---
NEURO_BASE = 1648           # valeur TIREE reconstituee (port inerte 2192 / correct 4448)
NEURO_ADD = 1696.0          # `extraDmg[50] x mult 180` x niveau 1 de parasite
NEURO_PIERCE, NEURO_ARMOR = 100, 50000
NEURO_RANGED_SPECIALIST = (1.33, None)      # `%-list` ATTAQUANT du Neurothrope
NEURO_INERTE, NEURO_POST, NEURO_NATIF = 2192, 3888, 4448


def _reduced(base, pierce, armor, att, deff):
    """Les deux etages que `_reduced_bounds` enchaine, a l'identique du combat."""
    return apply_all_modifiers(
        apply_pierce_and_modifiers(base, pierce, armor, att, hit_mult=1,
                                   attacker_additive_pre=True),
        deff, round_materialize=True)


def _accus(add_def, att_pct=()):
    att = DamageModifiers()
    for e in att_pct:
        att.pct_list.append(e)
    deff = DamageModifiers()
    deff.additive = add_def
    return att, deff


# ------------------------------------------------- (1) le CLIQUET du canal : qui alimente ce champ

def _sites_for_addition_defenseur():
    """Balaie l'arbre `engine/` de CE checkout (chemin derive du fichier de test -- #434 : un garde
    ne lit JAMAIS au-dessus de son propre checkout) et rend
    `{<module>.<classe>: [(ligne, <valeur litterale> | None), ...]}` pour chaque appel
    `for_addition(False, ...)` -- `owner_is_caster=False` = face DEFENSEUR.

    La VALEUR est desormais lue, et c'est le correctif de #462-r4b-r1-r1-r2 : `for_addition` a la
    signature `(owner_is_caster: bool, value: int)`, donc le second argument (positionnel ou
    `value=`) EST la magnitude. `None` = ce n'est pas un litteral (une expression, donc un montant
    calcule). Lecture AST : pas de regex sur du texte, pas d'import de tout l'arbre."""
    root = os.path.join(_PY, "engine")
    found = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8") as fh:
                try:
                    tree = ast.parse(fh.read(), filename=path)
                except SyntaxError:                       # pragma: no cover - arbre toujours sain
                    continue
            rel = os.path.relpath(path, root)[:-3].replace(os.sep, ".")
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for sub in ast.walk(node):
                    if not isinstance(sub, ast.Call):
                        continue
                    fname = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    if fname != "for_addition" or not sub.args:
                        continue
                    a0 = sub.args[0]
                    if not (isinstance(a0, ast.Constant) and a0.value is False):
                        continue
                    val = sub.args[1] if len(sub.args) > 1 else next(
                        (kw.value for kw in sub.keywords if kw.arg == "value"), None)
                    litt = val.value if isinstance(val, ast.Constant) else None
                    found.setdefault("%s.%s" % (rel, node.name), []).append((sub.lineno, litt))
    return found


def _ventiler_les_sites():
    """(producteurs, porteurs_de_gate) -- la partition EXHAUSTIVE des classes trouvees.

    * PORTEUR DE GATE : **tous** ses `for_addition(False, ...)` portent le litteral `0`. Le natif
      rend alors un `EffectBonus` dont toutes les formules valent zero, dont l'unique role est de
      faire passer le bloc de `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` ou
      `IgnoreArmor()` est evalue -- la magnitude vit sur l'axe ARMURE, pas sur l'additif.
    * PRODUCTEUR : au moins un site dont la magnitude n'est pas le litteral `0`.

    Un `for_addition(False, <expression>)` est TOUJOURS un producteur, meme si l'expression peut
    valoir zero a l'execution : le cliquet ne doit pas dependre d'une evaluation du gameconfig."""
    sites = _sites_for_addition_defenseur()
    porteurs = {k for k, v in sites.items() if all(litt == 0 for _l, litt in v)}
    return {k for k in sites if k not in porteurs}, porteurs


#: Les PORTEURS DE GATE, exclus du cliquet des producteurs -- avec ce qui atteste l'exclusion.
#: Chacun est RE-MESURE EXECUTABLEMENT par `test_les_porteurs_de_gate_...` ci-dessous : la sortie
#: du registre n'est PAS accordee sur la foi d'un litteral lu a l'AST.
PORTEURS_DE_GATE_ATTESTES = {
    "entities.effects.loki.helspear.HelspearIgnoreArmorEffect":
        "`Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense` (1583) -- toutes formules "
        "NULLES, trigger `get_OwnerIsTarget & IsUnit(Caster@u003CDSLSelectors+0x48u003E)` ; la "
        "magnitude est `IgnoreArmor()` (slot virtuel +0x718 -> `DamageModifiers+0x28`)",
    "entities.effects.loki.strike_from_the_shadows.StrikeFromTheShadowsEffect":
        "`StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense` (1549) -- six slots de "
        "magnitude a zero, trigger `IsRangedAttack() & get_OwnerIsTarget` ; meme axe ARMURE",
}


def test_le_registre_des_producteurs_d_additif_defenseur_est_COMPLET():
    """LE cliquet de ce cas. `def_mods.additive` n'a que cinq alimentateurs, et chacun a du etre
    confronte en COMBAT parce que #462-r4b-r1 a CHANGE ce que le moteur en fait. Un sixieme qui
    entrerait sans mesure reproduirait exactement la regression silencieuse d'origine : ni erreur,
    ni crash, juste un montant au mauvais etage.

    ⚠ #462-r4b-r1-r1-r2 -- L'INVENTAIRE ETAIT FAUX, ET IL ACCUSAIT. Le recenseur creditait tout
    `for_addition(False, ...)` SANS LIRE LA MAGNITUDE. Il a donc accuse `HelspearIgnoreArmorEffect`
    et `StrikeFromTheShadowsEffect`, qui rendent `for_addition(False, 0)` : un `EffectBonus` a
    formules NULLES dont l'unique role est de PORTER LA GATE du bloc `IgnoreArmor()`. Un montant
    NUL ne peut pas etre << au mauvais etage >> -- le placement pre-percage est l'identite dessus.
    Les accuser aurait fait reclamer une confrontation live pour un axe algebriquement inerte, et
    -- pire -- aurait pu faire SUPPRIMER ces deux appels comme << inutiles, ils valent zero >>,
    ce que les deux docstrings interdisent explicitement (cela DESARMERAIT la penetration)."""
    trouves, _porteurs = _ventiler_les_sites()
    attestes = set(PRODUCTEURS_ATTESTES)
    nouveaux = trouves - attestes
    assert not nouveaux, (
        "producteur(s) d'additif DEFENSEUR non atteste(s) : %s.\n"
        "Chacun traverse `AttackDamageOperation._apply_defender_flat_reductions` et est donc "
        "AFFECTE par le placement pre-percage (#462-r4b-r1). Le confronter en COMBAT (probe "
        "`probe_462_r4b_r1_r1_defender_additive_carriers.py`) puis l'inscrire dans "
        "PRODUCTEURS_ATTESTES avec sa mesure." % sorted(nouveaux))
    disparus = attestes - trouves
    assert not disparus, (
        "producteur(s) atteste(s) INTROUVABLE(S) : %s -- le canal a-t-il ete recable ? "
        "Les gardes live correspondants ne mesurent alors plus rien." % sorted(disparus))


def test_les_porteurs_de_gate_sont_EXCLUS_SUR_MESURE_pas_sur_un_litteral():
    """LE GARDE QUI REMPLACE CE QUE L'EXCLUSION RETIRE. Sans lui, `_ventiler_les_sites` serait une
    echappatoire : ecrire `for_addition(False, 0)` suffirait a sortir du cliquet des producteurs.

    Pour chaque classe exclue, on MESURE, en l'executant, les quatre faits qui justifient la
    sortie -- et le quatrieme est le vrai : le montant de cette classe existe, il vit simplement
    sur l'AXE ARMURE. Une classe dont la penetration serait nulle AUSSI ne serait pas un porteur de
    gate mais un effet mort, et ce test le dirait."""
    from engine.entities.effects.loki.helspear import HelspearIgnoreArmorEffect
    from engine.entities.effects.loki.strike_from_the_shadows import StrikeFromTheShadowsEffect

    # Le `kw` qui OUVRE la gate de chacun, LU au site (cf. les deux docstrings de mirror) :
    #   Helspear            : `IsUnit(Caster)` -> un `attacker_ctx` porteur d'un id ;
    #   StrikeFromTheShadows: `IsRangedAttack()` -> `is_melee=False` (tri-etat : `None` ferme).
    cas = [(HelspearIgnoreArmorEffect,
            "entities.effects.loki.helspear.HelspearIgnoreArmorEffect",
            {"attacker_ctx": {"id": 9}}),
           (StrikeFromTheShadowsEffect,
            "entities.effects.loki.strike_from_the_shadows.StrikeFromTheShadowsEffect",
            {"is_melee": False, "attacker_ctx": {"id": 9}})]

    _trouves, porteurs = _ventiler_les_sites()
    # NON-VACUITE : sans porteur trouve, les boucles ci-dessous seraient vides et ce test vert.
    assert porteurs == set(PORTEURS_DE_GATE_ATTESTES), (
        "porteurs de gate trouves %s != attestes %s -- toute entree/sortie de cette partition doit "
        "etre MESUREE ici, jamais seulement declaree"
        % (sorted(porteurs), sorted(PORTEURS_DE_GATE_ATTESTES)))

    for cls, cle, kw in cas:
        assert cle in porteurs, "%s n'est plus classe porteur de gate" % cle
        eff = cls({"name": cls.__name__, "source": 9})
        eff.source = 9
        eff.level = 1
        eff.times_applied = 1
        eff.ability_level = 50
        eff.active_ability_level = 50
        eff.ability_variables_multiplier = 180
        bonus = eff.create_effect_damage_malus_for_defense(**kw)
        # (1) la gate S'OUVRE -- sinon la mesure ne porterait sur rien.
        assert bonus is not None, "%s : gate fermee -> ce garde ne mesure rien" % cls.__name__
        # (2) c'est bien la face DEFENSEUR (le gisement du cliquet, pas un autre).
        assert bonus.owner_is_caster is False, "%s : ce n'est pas la face DEFENSEUR" % cls.__name__
        # (3) la magnitude est NULLE -- ce qui rend le placement pre-percage une identite.
        assert float(bonus.value) == 0.0, (
            "%s rend un additif defenseur NON NUL (%r) : il traverse alors "
            "`_apply_defender_flat_reductions` avec un montant, donc il est AFFECTE par le "
            "placement de #462-r4b-r1. Le confronter en COMBAT et le faire passer dans "
            "PRODUCTEURS_ATTESTES." % (cls.__name__, bonus.value))
        # (4) LE CRAN QUI COMPTE : son montant existe, sur l'AXE ARMURE. Un zero ici aussi
        #     signifierait un effet mort, pas un porteur de gate.
        pen = eff.get_armor_penetration()
        assert pen, (
            "%s : magnitude nulle sur l'additif ET penetration %r -- ce n'est pas un porteur de "
            "gate, c'est un effet INERTE. L'exclusion du cliquet des producteurs ne se justifie "
            "que parce que le montant vit sur l'axe ARMURE." % (cls.__name__, pen))


def test_CONTRE_EPREUVE_un_additif_NON_NUL_reste_accuse():
    """SANS CE TEST, L'EXCLUSION SERAIT UNE PORTE OUVERTE. On soumet au recenseur une source
    synthetique portant les deux formes, et on verifie qu'il ne confond pas :
    `for_addition(False, 0)` sort du cliquet, `for_addition(False, <expression>)` y reste --
    y compris quand l'expression pourrait valoir zero a l'execution."""
    src = ('class _Piege:\n'
           '    def a(self):\n'
           '        return for_addition(False, 0)\n'
           'class _Vrai:\n'
           '    def a(self):\n'
           '        return for_addition(False, self._m())\n'
           'class _VraiKw:\n'
           '    def a(self):\n'
           '        return for_addition(False, value=7)\n'
           'class _Mixte:\n'
           '    def a(self):\n'
           '        return for_addition(False, 0)\n'
           '    def b(self):\n'
           '        return for_addition(False, self._m())\n')
    tree = ast.parse(src)
    par_classe = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if (getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)) != "for_addition":
                continue
            a0 = sub.args[0]
            if not (isinstance(a0, ast.Constant) and a0.value is False):
                continue
            val = sub.args[1] if len(sub.args) > 1 else next(
                (kw.value for kw in sub.keywords if kw.arg == "value"), None)
            par_classe.setdefault(node.name, []).append(
                val.value if isinstance(val, ast.Constant) else None)
    porteurs = {k for k, v in par_classe.items() if all(x == 0 for x in v)}
    assert porteurs == {"_Piege"}, porteurs
    assert set(par_classe) - porteurs == {"_Vrai", "_VraiKw", "_Mixte"}, set(par_classe) - porteurs


# ------------------------------------- (2) la BORNE du residu de troncature : magnitudes INTEGRALES

def test_les_magnitudes_des_producteurs_sont_INTEGRALES():
    """LE RESIDU DE TRONCATURE PAR TERME, tenu comme BORNE et non comme suppostion.

    Le natif tronque CHAQUE `Addition` (`FixMath.NET.Fix64$$op_Explicit` = `raw >> 32`) AVANT de
    sommer : `base + trunc(A_att) + trunc(A_def)`. Le port somme des flottants puis arrondit
    (`apply_pierce_and_modifiers` : `round(d + mods.additive)`). Les deux coincident exactement tant
    que chaque terme est DEJA entier. Ce garde le mesure sur les trois producteurs ; s'il rougit,
    le regime devient OBSERVABLE et c'est un vrai bug de materialisation a fermer, pas une borne."""
    cas = [
        (ExemplarOfHateTargetEffect, {"is_melee": True}, {}),
        (ChronometronExtraDamageEffect, {"is_melee": True},
         {"id": 1, "is_unit": True, "team": 1, "team_by_id": {9: 1}, "traits": ()}),
        (NeuroparasiteEffect, {"damage_profile": "Psychic"},
         {"id": 9, "ability_level": 50, "multiplier": 180}),
        # #549 -- `HolyDuel_DmgReduction` (1093). Son gate est une EGALITE D'IDENTITE
        # (`AreEqual(Actor@DSLSelectors+0x40, BondedEntityFromEffect(Effect@0x38))`), donc l'attaquant
        # du ctx DOIT etre le bonde de l'instance, sans quoi le garde ne mesurerait rien.
        (HolyDuelDmgReductionEffect, {"is_melee": True}, {"id": 9}),
        # #547-r2 -- `HeraldOfTheApocalypse_ExtraDamage` (1027). Son trigger n'a que DEUX conjoints
        # (`get_OwnerIsTarget & IsUnit(caster@DSLSelectors+0x48)`) : ni `IsMeleeAttack`, ni
        # `DamageProfileIs`, ni `AreFriends` -- d'ou un `kw` VIDE. Le seul gate a ouvrir est
        # `is_unit` sur l'attaquant, sans quoi le port rend `None` et le garde ne mesurerait rien.
        (HeraldOfTheApocalypseExtraDamageEffect, {}, {"id": 9, "is_unit": True}),
    ]
    vus = 0
    for cls, kw, att in cas:
        eff = cls({"name": cls.__name__, "source": 9})
        eff.source = 9
        eff.level = 1
        eff.times_applied = 1
        eff.ability_level = 50
        eff.active_ability_level = 50
        eff.ability_variables_multiplier = 180
        # #549 -- l'ENTITE BONDEE de l'instance. `HolyDuel_DmgReduction` gate sur
        # `AreEqual(Actor@DSLSelectors+0x40, BondedEntityFromEffect(Effect@0x38))` : sans elle son
        # gate reste ferme et le garde ne mesurerait rien (il le DIT, cf. l'assertion suivante).
        # Inerte pour les trois autres, qui ne lisent pas ce champ.
        eff.bonded = att.get("id")
        bonus = eff.create_effect_damage_malus_for_defense(attacker_ctx=att, **kw)
        assert bonus is not None, "%s : gate ferme -> le garde ne mesure rien" % cls.__name__
        assert bonus.owner_is_caster is False, (
            "%s : ce n'est pas un additif DEFENSEUR" % cls.__name__)
        assert float(bonus.value).is_integer(), (
            "%s rend une magnitude FRACTIONNAIRE (%r) : la troncature PAR TERME du natif cesse "
            "de coincider avec le `round(somme)` du port -- residu #462-r4b-r1-r1 a rouvrir"
            % (cls.__name__, bonus.value))
        vus += 1
    assert vus == len(PRODUCTEURS_ATTESTES), "tous les producteurs attestes doivent etre couverts"


# --------------------------------- (3) le FORK prediction/combat sur l'axe MAGNITUDE, ferme par #r1

def _mini_state(att_id=9, tgt_id=7, passive_level=50, mult=180):
    """Etat MINIMAL portant ce que `defender_modifiers` lit de l'ATTAQUANT. Pas de table d'effets
    (`state.effects is None` -> aucun effet actif) : ce garde ne regarde QUE le contexte construit."""
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    from engine.runner.state import Entity, State
    st = State()
    for eid, team, vis in ((att_id, 1, "tyranNeurothrope"), (tgt_id, 2, "blackPossession")):
        e = Entity(eid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team))
        e.add_component(PositionComponent(col=eid, row=0))
        e.add_component(HealthComponent(hp=9000, hp_max=9000))
        ctx = UnitContext(entity_id=eid, visual_id=vis)
        ctx.passive_ability_level = passive_level
        ctx.ability_variables_multiplier = mult
        e.add_component(StatsComponent(ctx=ctx))
        st.entities[eid] = e
    return st, att_id, tgt_id


def test_le_combat_thread_le_NIVEAU_et_le_MULTIPLICATEUR_de_l_attaquant():
    """`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense`
    indexe son `ConfigVar(8 = extraDmg)` sur `GetAbilityState(effect)` -- l'etat de la SOURCE -- et
    son gate `AreEqual(BondedEntity, damageSource)` FAIT de l'attaquant cette source. La PREDICTION
    posait deja `ability_level`/`multiplier` (`playbook/prediction/_shared.py`) ; le COMBAT ne les
    posait PAS, donc l'effet etait MATERIALISE et pourtant INERTE (`src_lvl is None -> None`).

    MESURE qui l'a etabli : natif 4448 contre port 2192, ecart 2256 = 1696 x 1.33 -- le separateur
    #88 que la face PREDICTION avait mesure le 2026-07-12."""
    from engine.runner import damage_model as DM
    st, att, tgt = _mini_state()
    seen = {}
    orig = DM.build_defender_modifiers_from_effects

    def _spy(effects, is_melee=None, damage_profile=None, attacker_ctx=None, defense_stat=None):
        seen.update(attacker_ctx or {})
        return orig(effects, is_melee, damage_profile, attacker_ctx=attacker_ctx,
                    defense_stat=defense_stat)

    DM.build_defender_modifiers_from_effects = _spy
    try:
        DM.defender_modifiers(st, tgt, 9000, is_melee=False, damage_profile="Psychic",
                              attacker_id=att, is_normal_attack=True)
    finally:
        DM.build_defender_modifiers_from_effects = orig
    assert seen.get("ability_level") == 50, (
        "le COMBAT ne thread pas `ability_level` (%r) -> tout additif defenseur indexe sur la "
        "SOURCE reste INERTE, sans erreur ni crash" % (seen.get("ability_level"),))
    assert seen.get("multiplier") == 180, (
        "le COMBAT ne thread pas `multiplier` (%r) -> magnitude non scalee par la rarete"
        % (seen.get("multiplier"),))


# ----------------------------------------- (4) le regime PERCAGE : le SEUL ou l'additif seul separe

def test_le_regime_PERCAGE_separe_les_deux_placements_SANS_pct_list():
    """Bras `chrono`. Le plancher `max(d x pierce%, d - armure)` est affine de pente 1 sur la branche
    ARMURE -- donc `P(v + A) = P(v) + A` et les deux placements coincident. Sur la branche PERCAGE il
    est de pente `pierce/100`, et l'ecart vaut `A x (1 - pierce/100)`. Avec le profil `Physical`
    (PiercingRatio = 1) et une armure forcee a 50000, l'additif seul suffit a separer : 61 contre 950
    -- SANS aucune `%-list` defenseur, ce que le bras de #462-r4b-r1 ne pouvait pas montrer."""
    att, deff = _accus(CHRONO_ADD)
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _reduced(CHRONO_BASE, CHRONO_PIERCE, CHRONO_ARMOR, att, deff) == CHRONO_NATIF

    att, deff = _accus(CHRONO_ADD)                    # AUCUN merge = l'etat d'avant #462-r4b-r1
    assert _reduced(CHRONO_BASE, CHRONO_PIERCE, CHRONO_ARMOR, att, deff) == CHRONO_POST
    assert CHRONO_POST != CHRONO_NATIF, "regime NON discriminant"
    # La branche PERCAGE doit bien gagner, sinon le cran ne dit rien.
    d = CHRONO_BASE + CHRONO_ADD
    assert d * CHRONO_PIERCE / 100.0 > d - CHRONO_ARMOR, "regime hors branche PERCAGE"


def test_le_regime_ARMURE_de_Chronometron_est_une_BORNE_pas_une_confirmation():
    """Le bras temoin `chrono-flat` (armure 0) rend `port == contre-modele == natif == 5983`. Ce
    garde fige POURQUOI cet accord ne prouve rien : sur la branche ARMURE les deux placements sont
    algebriquement CONFONDUS. Si ce bras devenait discriminant, la lecture du probe serait a revoir."""
    att, deff = _accus(CHRONO_ADD)
    post = _reduced(CHRONO_BASE, CHRONO_PIERCE, 0, att, deff)
    att, deff = _accus(CHRONO_ADD)
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _reduced(CHRONO_BASE, CHRONO_PIERCE, 0, att, deff) == post, (
        "sur la branche ARMURE les deux placements doivent COINCIDER")


# --------------------------- (5) le regime du Neuroparasite : INERTIE et PLACEMENT, deux axes separes

def test_le_regime_Neuroparasite_separe_INERTIE_ET_PLACEMENT():
    """Bras `neuro`. Le gate `DamageProfileIs(0xd = Psychic)` confine cet effet a un profil dont
    `PiercingRatio = 100` : `GetDamageWithPiercing(d, 100, armure) = d`, l'IDENTITE. L'axe PERCAGE y
    est donc STRUCTURELLEMENT degenere, quelle que soit l'armure -- ce qui separe les placements ici,
    c'est la `%-list` ATTAQUANT (`RangedSpecialist` x1.33), parce que l'additif pre-percage la
    traverse. TROIS valeurs distinctes, donc un montage discriminant sur les DEUX axes a la fois."""
    att, deff = _accus(0.0, att_pct=[NEURO_RANGED_SPECIALIST])          # port AVANT le fix : inerte
    assert _reduced(NEURO_BASE, NEURO_PIERCE, NEURO_ARMOR, att, deff) == NEURO_INERTE

    att, deff = _accus(NEURO_ADD, att_pct=[NEURO_RANGED_SPECIALIST])    # vivant, MAL place
    assert _reduced(NEURO_BASE, NEURO_PIERCE, NEURO_ARMOR, att, deff) == NEURO_POST

    att, deff = _accus(NEURO_ADD, att_pct=[NEURO_RANGED_SPECIALIST])    # vivant, BIEN place
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _reduced(NEURO_BASE, NEURO_PIERCE, NEURO_ARMOR, att, deff) == NEURO_NATIF
    assert len({NEURO_INERTE, NEURO_POST, NEURO_NATIF}) == 3, "les trois regimes doivent differer"


def test_l_axe_PERCAGE_est_degenere_pour_tout_effet_gate_Psychic():
    """La BORNE structurelle du bras `neuro`, lue du gameconfig et non supposee : `Psychic` a
    `PiercingRatio = 100`, donc aucune armure ne rend son plancher discriminant. Tout additif
    defenseur gate sur ce profil exige une `%-list` (l'une ou l'autre face) pour que son placement
    soit observable."""
    import gameconfig as GC
    assert int((GC.damage_profile("Psychic") or {}).get("PiercingRatio")) == 100
    att, deff = _accus(NEURO_ADD)                       # sans %-list : les deux placements coincident
    post = _reduced(NEURO_BASE, NEURO_PIERCE, NEURO_ARMOR, att, deff)
    att, deff = _accus(NEURO_ADD)
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _reduced(NEURO_BASE, NEURO_PIERCE, NEURO_ARMOR, att, deff) == post
