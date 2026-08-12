"""CLIQUETS OFFLINE #928 -- `LegacyOfCombat` (1319, passif de `custoBladeChampion`), ses TROIS faces.

Ce que ces etages figent, et POURQUOI chacun :

  1. les ORDINAUX ECRITS AUX SITES, contre le build -- et les collisions qui rendent le NOM
     obligatoire (`1319` est aussi un `EffectType`) ;
  2. le VECTEUR : `On(0xb = UnitAbility)`, emis par les DEUX voies du port, avec l'ordre natif
     `0x2a -> execution -> 0xb -> 0xc -> 0xe` ;
  3. le TRIGGER : ses quatre termes, et surtout l'EGALITE STRICTE a 1 (un `> 0` ferait re-trigger
     la 2e attaque du tour) ;
  4. le BEHAVIOUR : la STRUCTURE de l'arbre (`If` + deux feuilles), les DEUX volets de config qui
     ne doivent pas se croiser, et le filtre `BigTarget` sur la branche `then` ;
  5. la face DECISION MOVE : registre, cle BC, comptage d'ENNEMIS sans inclusion de self ;
  6. la face DECISION ATTACK, **DEAD** : absence DELIBEREE du registre ATTACK, RE-DERIVEE du
     binaire (le corps natif y rend un zero constant) et non citee ;
  7. l'import isole (cliquet #433-r1).

ASCII only.
"""
from __future__ import annotations

import pytest

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py",
        # LE PROBE qui RE-DERIVE la RE du binaire (etage 6 : le verdict DEAD), et sa fermeture
        # d'imports MESUREE -- `probe_928` importe `probe_509` (le montage live), qui tire lui-meme
        # `Runner` et le dispatch de phase ; `probe_366` tire `probe_364` et `probe_358`.
        "scripts/python/probe_928_legacy_of_combat.py",
        "scripts/python/probe_364_effect_1582_registration.py",
        "scripts/python/probe_366_inventaire_effets_forme_b.py",
        "scripts/python/probe_358_effects_database_registry.py",
        "scripts/python/probe_212_bc_key_literals.py",
        "scripts/python/probe_509_martial_inspiration.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        # ... et l'etage 7 du probe (terme de tuile, face DECISION) tire `probe_193c`, dont le pin
        # de build refuse d'armer les hooks sur un binaire etranger.
        "scripts/python/probe_193c_move_playbook_terms.py",
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_provenance.py",
        # LES DEUX MIRRORS du cas et leurs registres.
        "scripts/python/engine/runner/operations/triggers/loki/legacy_of_combat.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/playbook/legacy_of_combat.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/psyker.py",
        # LE VECTEUR `On(0xb)` et ses DEUX emetteurs.
        "scripts/python/engine/runner/operations/triggers/dispatch/ability.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/abilities/handler.py",
        # LES ENUMS dont ce fichier fige les ordinaux ECRITS AUX SITES.
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/damage_profile_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        # LES NOEUDS DSL de l'arbre : un etage retire ou une signature changee doit rougir ici.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/operations/damage_prediction_sort.py",
        # LE COMPTEUR d'attaques du tour, que le trigger compare a 1.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/battle_query.py",
    ),
    # `build: True` -- les ordinaux figes (etage 1) et le verdict DEAD (etage 6) sont RE-DERIVES du
    # binaire et du gameconfig VIVANT : un changement de build peut les deplacer, et c'est
    # precisement ce que ce fichier doit rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde le port des trois faces de `1319 LegacyOfCombat` : le vecteur "
        "`On(0xb = UnitAbility)` et ses deux emetteurs, le trigger (dont l'EGALITE STRICTE a 1 "
        "attaque), l'arbre du behaviour (`If` + deux volets de config qui ne doivent pas se "
        "croiser), le playbook MOVE et son absence DELIBEREE du registre ATTACK."),
}

ABILITY_ID = "LegacyOfCombat"


# ---------------------------------------------------------------------------------------------
# 1. IDENTITE -- les ordinaux ECRITS aux sites, contre le build
# ---------------------------------------------------------------------------------------------

def test_les_ordinaux_du_cas_sont_ceux_du_build():
    """`LegacyOfCombatPlaybook$$.ctor` porte le litteral `0x527` (= 1319) et
    `...LegacyOfCombatAbility$$CreateBehaviour` le litteral `0x3f9` (= `UnitTrait.BigTarget`).

    Ce test fige les ordinaux **ECRITS AU SITE** : `probe_313` compare le MIRROR au BUILD et
    redevient vert des qu'on regenere le mirror apres un renumerotage, alors que la valeur ecrite
    au site, elle, a change (CLAUDE.md, cran #270-r1-r1-r3)."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.operations.triggers.loki import legacy_of_combat as L
    assert int(TriggeredAbilityType.LegacyOfCombat) == 0x527 == 1319
    assert L.LEGACY_OF_COMBAT == 0x527
    assert int(UnitTrait.BigTarget) == 0x3f9 == 1017
    assert L.BIG_TARGET == 0x3f9
    assert int(EventTriggerType.UnitAbility) == 0xb == 11
    assert L._ON_UNIT_ABILITY == 0xb


def test_la_collision_d_ordinal_existe_et_c_est_elle_qui_rend_le_NOM_obligatoire():
    """`1319` nomme AUTRE CHOSE en `EffectType` -- la surcharge d'`AbilityOrEffect$$op_Implicit`
    appelee par le natif est `set_TriggeredAbility` (adresse du `call` resolue), pas `set_Effect`.
    Confondre les deux ne leverait AUCUNE erreur."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert TriggeredAbilityType(1319).name == "LegacyOfCombat"
    assert EffectType(1319).name != "LegacyOfCombat"


def test_les_DEUX_volets_de_config_sont_DISJOINTS_et_le_gameconfig_les_porte():
    """`GetHits()` = `GetNumberConstant(0x2f = nrOfHits)` / `GetHits2()` = `(0x32 = nrOfHits_2)` ;
    `MinMaxDamage` lit `minDmg`/`maxDmg` (`0xc`/`0xd`), `MinMaxDamage2` lit `minDmg_2`/`maxDmg_2`.

    Croiser deux clefs de volets differents ne leve rien : ca lit simplement l'autre attaque. Les
    quatre constantes doivent donc etre DISTINCTES au site ET presentes au gameconfig."""
    import gameconfig as GC
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.runner.operations.triggers.loki import legacy_of_combat as L
    assert int(AbilityConstantType.nrOfHits) == 0x2f
    assert int(AbilityConstantType.nrOfHits_2) == 0x32
    assert int(AbilityVariableType.minDmg) == 0xc and int(AbilityVariableType.maxDmg) == 0xd
    assert L.HITS_KEY_ADJACENT != L.HITS_KEY_BIG_TARGET
    assert (L.MIN_KEY_ADJACENT, L.MAX_KEY_ADJACENT) != (L.MIN_KEY_BIG_TARGET, L.MAX_KEY_BIG_TARGET)
    assert L.PROFILE_ADJACENT != L.PROFILE_BIG_TARGET
    cfg = GC.ability(ABILITY_ID) or {}
    cst, var = cfg.get("constants") or {}, cfg.get("variables") or {}
    assert int(cst[L.HITS_KEY_ADJACENT]) == 3 and int(cst[L.HITS_KEY_BIG_TARGET]) == 1
    assert cst["damageProfile"] == L.PROFILE_ADJACENT == "Power"
    assert cst["damageProfile_2"] == L.PROFILE_BIG_TARGET == "Piercing"
    for k in (L.MIN_KEY_ADJACENT, L.MAX_KEY_ADJACENT,
              L.MIN_KEY_BIG_TARGET, L.MAX_KEY_BIG_TARGET):
        assert var.get(k), "variable de config absente : %s" % k
    # les bornes du volet 2 sont STRICTEMENT plus hautes -> croiser les clefs est OBSERVABLE.
    assert var[L.MIN_KEY_BIG_TARGET][0] > var[L.MIN_KEY_ADJACENT][0]


# ---------------------------------------------------------------------------------------------
# 2. LE VECTEUR `On(0xb = UnitAbility)` -- deux emetteurs, ordre natif
# ---------------------------------------------------------------------------------------------

def test_le_vecteur_UnitAbility_existe_et_est_emis_par_les_DEUX_voies():
    """`ActiveAbilityOperation$$ExecuteInternal` publie `0x2a` -> execution -> **`0xb`** ->
    `if (IsActiveAbility) 0xc` -> `AddFlagsAfterAbilityExecution` -> `0xe`.

    Le port a DEUX portes d'operation la ou le natif n'a qu'un site (#120) : n'emettre que d'un
    cote recreerait le fork. Le test lit le SOURCE des deux emetteurs -- c'est ce qui attrape une
    suppression silencieuse d'un des deux appels."""
    import inspect
    from engine.runner.abilities import handler as H
    from engine.runner.operations.triggers.dispatch import ability as A
    from engine.runner.operations.triggers.dispatch import attack as AT
    assert callable(getattr(A, "unit_ability_triggers", None))
    # voie ABILITY
    src_h = inspect.getsource(H.AbilityHandler)
    assert "_unit_ability(" in src_h and "unit_ability_triggers" in inspect.getsource(H)
    # voie NORMALE
    assert "unit_ability_triggers" in inspect.getsource(AT.after_hit_normal_attack)


def test_l_ordre_natif_0xb_AVANT_0xc_est_tenu_dans_les_DEUX_branches_du_handler():
    """`0xb` est INCONDITIONNEL, `0xc` est gate par `IsActiveAbility` : inverser les deux ferait
    fire le passif APRES un vecteur qui, lui, se tait pour l'attaque normale."""
    import inspect
    import re
    from engine.runner.abilities import handler as H
    src = inspect.getsource(H.AbilityHandler._active_ability_operation)
    # Un APPEL, pas une sous-chaine : `_unit_ability(` est INCLUS dans `_unit_active_ability(` et
    # dans `_post_unit_ability(` -- compter la sous-chaine rendait 5 au lieu de 2.
    appels = re.findall(r"self\.(_unit_ability|_unit_active_ability|_post_unit_ability)\(msg\)",
                        src)
    assert appels.count("_unit_ability") == 2, (
        "les DEUX branches du handler (ability non portee / portee) doivent emettre `On(0xb)` : "
        "%d trouvee(s) -- %r" % (appels.count("_unit_ability"), appels))
    # sequence attendue, branche NON PORTEE puis branche PORTEE : 0xb, 0xc, 0xe, 0xb, 0xc, 0xe
    attendu = ["_unit_ability", "_unit_active_ability", "_post_unit_ability"] * 2
    assert appels == attendu, appels


#: Les consommateurs ATTESTES du vecteur `On(0xb = EventTriggerType.UnitAbility)`. Un ENSEMBLE
#: nomme, et non le singleton d'origine : #928 a EMIS le vecteur (il ne l'etait pas), et rien
#: n'empeche -- ni ne doit empecher -- qu'un port ulterieur s'y branche. Ce qui doit rester vrai,
#: c'est que CHAQUE ecouteur ait ete LU, parce que l'emission est desormais reelle pour tous.
#:
#:   * `LegacyOfCombatAdditionalAttackAbility` (#928) -- le consommateur d'origine, celui pour qui
#:     le vecteur a ete emis.
#:   * `AggressiveOnslaughtSummonAbility` (#958) -- `AggressiveOnslaught_SummonAbility$$CreateTrigger`
#:     = `On(0xb = UnitAbility) & <DSLTriggers+0x20 = OwnerIsAlive> & get_OwnerIsCaster`, lu au
#:     decompile et ecrit verbatim en tete d'`operations/triggers/loki/aggressive_onslaught.py`.
#:
#: ⚠ On N'AJOUTE PAS un nom pour faire taire ce test : on l'ajoute avec le `CreateTrigger` natif qui
#: etablit qu'il ecoute REELLEMENT 0xb. Un ecouteur non lu ferait tirer une ability a chaque cast.
CONSOMMATEURS_0XB_ATTESTES = {
    "LegacyOfCombatAdditionalAttackAbility",     # #928
    "AggressiveOnslaughtSummonAbility",          # #958
}


def test_aucun_AUTRE_consommateur_du_vecteur_0xb_n_a_ete_reveille():
    """Avant #928 le vecteur n'etait PAS emis (`handler.py` : << aucun consommateur porte >>).
    L'ajouter est un no-op strict pour tout le reste -- a condition que TOUTE entree de registre
    qui ecoute `event_id == 11` ait ete LUE au decompile. Si une entree non attestee apparait, ce
    test la NOMME."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch import registry as R
    ecouteurs = []
    for nom in ("ABILITY_TRIGGERS", "TRAIT_TRIGGERS", "EFFECT_TRIGGERS", "GLOBAL_TRIGGERS",
                "RELIC_ABILITY_TRIGGERS", "ACTIVE_ABILITY_TRIGGERS",
                "PASSIVE_HELPER_ABILITY_TRIGGERS", "CUSTOM_TRIGGERED_ABILITIES"):
        d = getattr(R, nom, None)
        if not isinstance(d, dict):
            continue
        for cle, v in d.items():
            for cls in (v if isinstance(v, (list, tuple)) else [v]):
                ev = getattr(cls, "event_id", None)
                if ev is not None and int(ev) == int(EventTriggerType.UnitAbility):
                    ecouteurs.append((nom, cle, getattr(cls, "__name__", str(cls))))
    vus = {e[2] for e in ecouteurs}
    # NON-DEGENERESCENCE : le consommateur d'origine doit TOUJOURS etre la, sans quoi ce fichier
    # entier garderait un vecteur que plus personne ne lit.
    assert "LegacyOfCombatAdditionalAttackAbility" in vus, (
        "le consommateur d'ORIGINE de #928 a disparu du registre : %r" % (ecouteurs,))
    assert not (vus - CONSOMMATEURS_0XB_ATTESTES), (
        "consommateur(s) NON ATTESTE(S) du vecteur 0xb : %s. Lire leur `CreateTrigger` au "
        "decompile, puis les inscrire dans `CONSOMMATEURS_0XB_ATTESTES` DANS LE MEME COMMIT que "
        "le port -- pas apres coup pour faire taire ce test."
        % sorted(vus - CONSOMMATEURS_0XB_ATTESTES))


# ---------------------------------------------------------------------------------------------
# 3. LE TRIGGER -- quatre termes, dont une EGALITE STRICTE
# ---------------------------------------------------------------------------------------------

class _Ev:
    """Duck-type minimal du `TriggerEvent` que le dispatch passe a `matches`."""
    def __init__(self, actor_id, ability_type=1013):
        self.actor_id, self.ability_type = actor_id, ability_type


class _Uc:
    def __init__(self, n):
        self.attacks_made_this_turn = n


class _Ent:
    def __init__(self, n):
        self._uc = _Uc(n)

    def get_component(self, cls):
        return self._uc


class _St:
    def __init__(self, n):
        self._n = n

    def get_entity(self, uid):
        return _Ent(self._n)


class _StNul:
    """`State` SANS entite : `ability_attack_params` retombe alors sur `level = 0` (comportement
    documente de son repli). Suffit pour lire la STRUCTURE de l'arbre, qui ne depend d'aucun etat."""
    def get_entity(self, uid):
        return None


def _trigger(owner_id=7):
    from engine.runner.operations.triggers.loki.legacy_of_combat import (
        LegacyOfCombatAdditionalAttackAbility)
    t = LegacyOfCombatAdditionalAttackAbility.__new__(LegacyOfCombatAdditionalAttackAbility)
    t.owner_id = owner_id
    return t


def test_le_gate_du_compteur_est_une_EGALITE_STRICTE_a_UNE_attaque():
    """`AmountIsEqual( TimesAttackMadeThisTurn(Owner, rangeType = null), <DSLFormulas+0x20> =
    Direct(1) )`.

    ⚠ C'EST LE POINT DU TRIGGER. Un `AmountIsGreaterThanZero` (le voisin de forme le plus proche,
    et celui que porte `IconOfObstinacy` sous la forme `AmountIsZero`) serait vrai a 2, 3, 4
    attaques : le passif re-declencherait a CHAQUE attaque du tour au lieu d'UNE SEULE. Et comme
    l'attaque supplementaire incremente elle-meme le compteur (une fois par cible frappee), la
    2e evaluation voit deja `>= 2` -- c'est exactement ce que l'egalite refuse."""
    t = _trigger()
    assert t.matches(_St(1), _Ev(7)) is True
    assert t.matches(_St(0), _Ev(7)) is False
    for n in (2, 3, 4, 7):
        assert t.matches(_St(n), _Ev(7)) is False, "le passif re-declenche a %d attaques" % n


def test_le_gate_OwnerIsActor_refuse_un_acteur_TIERS():
    """`get_OwnerIsActor` = `AreEqual(Owner@+0x30, Actor@+0x40)` : le passif ne fire QUE sur les
    abilities de son porteur, pas sur celles d'un allie ou d'un ennemi."""
    t = _trigger(owner_id=7)
    assert t.matches(_St(1), _Ev(8)) is False
    assert t.matches(_St(1), _Ev(None)) is False


def test_le_gate_anti_recursion_refuse_l_ability_ELLE_MEME():
    """`NOT CurrentAbilityIs(AbilityOrEffect(<this+0x10> = 1319))`.

    ⚠ STRUCTURELLEMENT toujours vrai sur les emetteurs portes (les deux voies renseignent un
    `ActiveAbilityType`, jamais un `TriggeredAbilityType`) -- le terme est porte parce qu'il est
    ECRIT. Le test le rend EXECUTABLE : il rougirait si quelqu'un le supprimait en le croyant mort,
    et il documente ce qui se passerait si un vecteur `0xb` etait publie sous `CurrentAbility=1319`."""
    from engine.runner.operations.triggers.loki.legacy_of_combat import LEGACY_OF_COMBAT
    t = _trigger()
    assert t.matches(_St(1), _Ev(7, ability_type=LEGACY_OF_COMBAT)) is False
    # `None` = canal non threade -> le natif ne peut pas comparer, le port laisse PASSER.
    assert t.matches(_St(1), _Ev(7, ability_type=None)) is True


# ---------------------------------------------------------------------------------------------
# 4. LE BEHAVIOUR -- la STRUCTURE de l'arbre, terme a terme
# ---------------------------------------------------------------------------------------------

def test_l_arbre_est_un_If_avec_les_DEUX_feuilles_du_decompile():
    """`If( AmountIsGreaterThanZero(firstBigTarget), AttackWithAttackDamage(volet 2),
    AttackWithAttackDamage(volet 1) )`.

    Le test lit la STRUCTURE, pas une valeur : c'est ce qui attrape un port qui aurait << aplati >>
    le `If` en une seule attaque, ou croise les deux jeux de clefs de config."""
    from engine.entities.behaviours import If
    from engine.entities.selectors.units import AdjacentEnemies, First
    from engine.entities.triggers import AmountIsGreaterThanZero
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.operations.triggers.loki import legacy_of_combat as L

    arbre = L.legacy_of_combat_tree(_StNul(), 7)
    assert isinstance(arbre, If)
    assert isinstance(arbre.cond, AmountIsGreaterThanZero)
    assert isinstance(arbre.then, AttackWithAttackDamage)
    assert isinstance(arbre.otherwise, AttackWithAttackDamage)
    # branche `then` = volet 2 (BigTarget), cible = le `First(...)` du selecteur trie
    assert isinstance(arbre.then.target_sel, First)
    assert (arbre.then.min_key, arbre.then.max_key, arbre.then.hits_key) == (
        L.MIN_KEY_BIG_TARGET, L.MAX_KEY_BIG_TARGET, L.HITS_KEY_BIG_TARGET)
    assert arbre.then.profile == L.PROFILE_BIG_TARGET
    # branche `else` = volet 1, cible = TOUS les ennemis adjacents
    assert isinstance(arbre.otherwise.target_sel, AdjacentEnemies)
    assert (arbre.otherwise.min_key, arbre.otherwise.max_key, arbre.otherwise.hits_key) == (
        L.MIN_KEY_ADJACENT, L.MAX_KEY_ADJACENT, L.HITS_KEY_ADJACENT)
    assert arbre.otherwise.profile == L.PROFILE_ADJACENT
    # les DEUX feuilles portent l'`abilityOrEffect` natif ET le mode MULTI-CIBLE.
    for f in (arbre.then, arbre.otherwise):
        assert f.ability_type == L.LEGACY_OF_COMBAT
        assert f.multi is True, "le natif passe un SELECTEUR en `target` : aucun collapse mono-cible"
        assert f.level_slot == "passive", "1319 est un PASSIF : la config s'indexe au niveau passif"
        assert f.is_melee is True                      # gameconfig `attackRangeType: Melee`


def test_le_selecteur_de_BigTarget_est_la_chaine_des_QUATRE_noeuds():
    """`First(SortTargetsByDamagePredictionSelector(Randomize(UnitsWithTrait(AdjacentEnemies,
    BigTarget))), amount = 1)`.

    ⚠ Le `Randomize` n'est PAS decoratif : il est le TIE-BREAK entre deux Big Targets de meme
    prediction, et il CONSOMME du RNG (`len(pool)` tirages). Le retirer laisse la meme cible a
    pool 1 mais desaligne tout le flux -- CONFRONTE LIVE (mutant `sans_randomize` : 8 tirages au
    lieu de 10, natif 10)."""
    from engine.entities.selectors.geometry import Randomize
    from engine.entities.selectors.units import AdjacentEnemies, First, UnitsWithTrait
    from engine.entities.selectors.accessors import Owner
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.runner.operations.damage_prediction_sort import SortTargetsByDamagePrediction
    from engine.runner.operations.triggers.loki import legacy_of_combat as L

    sel = L.big_target_selector(_StNul(), 7)
    assert isinstance(sel, First)
    tri = sel.source
    assert isinstance(tri, SortTargetsByDamagePrediction)
    assert isinstance(tri.attacker, Owner)
    assert tri.ability_type == L.LEGACY_OF_COMBAT
    assert tri.damage_profile == L.PROFILE_BIG_TARGET and tri.is_melee is True
    rnd = tri.targets
    assert isinstance(rnd, Randomize), "etage Randomize absent : %r" % (rnd,)
    wt = rnd.source
    assert isinstance(wt, UnitsWithTrait)
    assert int(wt.trait) == int(UnitTrait.BigTarget) == 1017
    assert wt.selection_type == L._SELECTION_ALIVE_AND_TARGETABLE == 3
    adj = wt.source
    assert isinstance(adj, AdjacentEnemies)
    assert isinstance(adj.center, Owner)
    assert adj.selection_type == L._SELECTION_ALIVE_AND_TARGETABLE


def test_le_selecteur_de_cible_ne_FILTRE_PAS_par_trait_sur_la_branche_else():
    """La branche << else >> vise `AdjacentEnemies` NU : le natif n'y remet AUCUN filtre. C'est le
    point ou recopier la branche `then` (qui, elle, filtre `BigTarget`) donnerait un port qui ne
    frappe rien quand il n'y a pas de Big Target -- exactement le contraire du texte i2."""
    from engine.entities.selectors.units import AdjacentEnemies, UnitsWithTrait
    from engine.runner.operations.triggers.loki import legacy_of_combat as L
    els = L.legacy_of_combat_tree(_StNul(), 7).otherwise.target_sel
    assert isinstance(els, AdjacentEnemies)
    assert not isinstance(els, UnitsWithTrait)
    # ... et c'est le MEME noeud (memes arguments) que la source de la branche `then`.
    src = L.big_target_selector(_StNul(), 7).source.targets.source.source
    assert type(src) is type(els) and src.selection_type == els.selection_type


def test_le_selecteur_d_adjacence_est_ENNEMI_et_non_AdjacentUnits():
    """`DSLSelectors$$AdjacentEnemies` = `Enemies(unit, Units(AdjacentTiles(unit), unique, sel)
    - unit, sel)` : le filtre d'equipe EST dans le noeud. Un `AdjacentUnits` (aucun filtre) ferait
    frapper les ALLIES adjacents de Kariyan -- friendly fire silencieux."""
    from engine.entities.selectors.units import AdjacentUnits, SurroundingEnemies
    from engine.runner.operations.triggers.loki import legacy_of_combat as L
    # Deduplication par IDENTITE : le sous-arbre `firstBigTarget` est PARTAGE entre la condition du
    # `If` et la branche `then` (le natif ne l'interpose d'aucun `Cache`, d'ou sa DOUBLE
    # evaluation -- confrontee live par le mutant `sans_randomize`). Un parcours naif le compterait
    # deux fois.
    noeuds, vus, pile = [], set(), [L.legacy_of_combat_tree(_StNul(), 7)]
    while pile:
        n = pile.pop()
        if id(n) in vus:
            continue
        vus.add(id(n))
        noeuds.append(type(n).__name__)
        for attr in ("source", "targets", "target_sel", "center", "cond", "then", "otherwise",
                     "a", "b"):
            v = getattr(n, attr, None)
            if hasattr(v, "select") or hasattr(v, "execute") or hasattr(v, "should_trigger"):
                pile.append(v)
    assert "AdjacentUnits" not in noeuds, (
        "l'arbre porte un `AdjacentUnits` : le natif filtre l'equipe (`AdjacentEnemies`)")
    assert "SurroundingEnemies" not in noeuds, "l'arbre n'est PAS un disque : ring-1 seul"
    # DEUX instances DISTINCTES, comme le decompile en construit deux (une par branche).
    assert noeuds.count("AdjacentEnemies") == 2, noeuds
    del AdjacentUnits, SurroundingEnemies          # importes pour NOMMER ce qui est interdit


def test_le_sous_arbre_du_BigTarget_est_PARTAGE_entre_la_condition_et_la_branche_then():
    """`AmountIsGreaterThanZero(firstBT)` et `AttackWithAttackDamage(target = firstBT)` recoivent le
    MEME noeud : le decompile ne l'interpose d'AUCUN `Cache`, donc le natif l'evalue DEUX fois --
    et comme il contient un `Randomize`, il consomme `2 x len(pool)` tirages `genrand_int32`.

    MESURE (`probe_928 --step 6`, un Big Target adjacent) : natif 10 tirages, port 10 ; mutant
    `sans_randomize` 8. Instancier deux sous-arbres SEPARES rendrait le meme resultat ici (l'ordre
    des tirages ne changerait pas), mais figer le PARTAGE documente la structure lue."""
    from engine.runner.operations.triggers.loki import legacy_of_combat as L
    arbre = L.legacy_of_combat_tree(_StNul(), 7)
    assert arbre.cond.a is arbre.then.target_sel


# ---------------------------------------------------------------------------------------------
# 5. LA FACE DECISION MOVE
# ---------------------------------------------------------------------------------------------

class _Poids:
    """Duck-type minimal du `wt` que le dispatcher passe (`GetUtilityValue(<cle>)`)."""
    def __init__(self, v=10):
        self.v = v

    def sub(self, groupe, cle):
        assert groupe == "TriggeredAbilities"
        return self.v


def test_le_playbook_MOVE_est_au_registre_avec_sa_cle_BC():
    """`LegacyOfCombatPlaybook$$.ctor` porte `0x527` = 1319 et son corps MOVE lit
    `LegacyOfCombat_LikesAdjacentEnemies` (litteral RESOLU dans `global-metadata.dat` par
    `probe_212`). La cle vaut 10 dans la CAPTURE comme dans le gameconfig VIVANT."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.legacy_of_combat import LegacyOfCombatPlaybook
    pb = TRIGGERED_MOVE_PLAYBOOKS[int(TriggeredAbilityType.LegacyOfCombat)]
    assert isinstance(pb, LegacyOfCombatPlaybook)
    assert pb.WEIGHT_KEY == "LegacyOfCombat_LikesAdjacentEnemies"
    import catalog_inject as CI
    vivant = (((CI.ai_utilities_from_gameconfig() or {}).get("Default") or {})
              .get("TriggeredAbilities") or {})
    assert int(vivant[pb.WEIGHT_KEY]) == 10


def test_le_playbook_MOVE_compte_les_ENNEMIS_adjacents_et_PAS_les_amis():
    """`IBattleQuery.<slot 127>(tile, case.unit, false)` = `GetAdjacentEnemies` : le corps natif
    n'a NI filtre de trait, NI cap, NI exclusion. Le terme est un produit plat.

    ⚠ Le pendant AMI (`friends_in_range`) compte l'unite qui evalue POUR ELLE-MEME (elle est sa
    propre alliee) ; ici c'est impossible par construction -- le natif demande les ENNEMIS de
    `case.unit`."""
    from engine.playbook.legacy_of_combat import LegacyOfCombatPlaybook
    pb = LegacyOfCombatPlaybook()
    tile = (2, 2)
    ctx = {"friend_units": [{"id": 1, "pos": (2, 3)}, {"id": 2, "pos": (2, 1)}],
           "enemy_units": [{"id": 3, "pos": (2, 3)}, {"id": 4, "pos": (2, 1)},
                           {"id": 5, "pos": (9, 9)}],
           "self_pos": (2, 3)}
    # 2 ennemis adjacents ; les 2 amis adjacents, l'ennemi LOINTAIN et `self_pos` ne comptent pas.
    assert pb.calculate_movement_utility_in_steps(tile, ctx, _Poids(10)) == 20.0
    assert pb.calculate_movement_utility_in_steps(tile, {"enemy_units": []}, _Poids(10)) == 0.0
    # poids nul -> le natif sommerait des zeros : on court-circuite, meme resultat.
    assert pb.calculate_movement_utility_in_steps(tile, ctx, _Poids(0)) == 0.0


# ---------------------------------------------------------------------------------------------
# 6. LA FACE DECISION ATTACK -- DEAD, et le verdict est RE-DERIVE du binaire
# ---------------------------------------------------------------------------------------------

def test_la_face_ATTACK_est_DEAD_et_c_est_RELU_DU_BINAIRE():
    """`...LegacyOfCombatPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` a
    pour corps ENTIER `yield return Fix64.op_Implicit(0)`.

    Le test ne CITE pas ce verdict : il le RE-DERIVE en desassemblant le corps et en constatant que
    le SEUL appel non-trivial est la conversion `Fix64`. Un build qui donnerait un corps a cette
    face ferait rougir ici -- et c'est exactement le moment ou il faudrait la porter.

    Skip EXPLICITE si le binaire du build n'est pas installe (ce n'est pas un verdict sur le port)."""
    import os
    import sys
    _PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _PY not in sys.path:
        sys.path.insert(0, _PY)
    try:
        import probe_366_inventaire_effets_forme_b as p366
        import probe_928_legacy_of_combat as p928
        _bhash, buf, secs, rows, _m = p366.load()
    except Exception as exc:                     # binaire/capstone absents != verdict du port
        pytest.skip("binaire du build indisponible (%s)" % (exc,))
    calls, _imms = p928._fn_calls_and_imms(buf, secs, rows, p928.PB_ATTACK)
    noms = [n for (_a, n) in calls
            if not n.startswith("FUN_") and "il2cpp_runtime_class_init" not in n]
    assert noms == ["FixMath.NET.Fix64$$op_Implicit"], (
        "la face ATTACK n'est plus un zero constant : %r -- il faut la PORTER" % (noms,))


def test_la_face_ATTACK_n_est_donc_PAS_au_registre():
    """L'inscrire n'ajouterait qu'un terme nul. Le test fige l'ARBITRAGE -- sans lui, << il manque
    une entree >> se lirait comme un oubli et quelqu'un l'ajouterait."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.playbook.legacy_of_combat import LegacyOfCombatPlaybook
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    assert int(TriggeredAbilityType.LegacyOfCombat) not in TRIGGERED_ATTACK_PLAYBOOKS
    assert not hasattr(LegacyOfCombatPlaybook, "calculate_attack_utility_in_steps")


def test_il_n_y_a_PAS_de_face_NON_OWNER_et_c_est_LA_PARENTE_qui_le_dit():
    """`LegacyOfCombatPlaybook` derive de `TriggeredAbilityPlaybook<LegacyOfCombatAbility>`
    (`frida/classes.tsv`), pas d'`AdjacentToOwnerNonOwnerPlaybook` : aucune face non-owner, et la
    table `metadata/non_owner_slot4.tsv` -- qui enumere TOUS les concrets de cette famille -- ne la
    porte pas. Skip si la table du build n'est pas la (entree VERSIONNEE, donc normalement
    presente)."""
    import os
    from engine.playbook import non_owner as NO
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(TriggeredAbilityType.LegacyOfCombat) not in getattr(
        NO, "TRIGGERED_NONOWNER_PLAYBOOKS", {})
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))))
    import glob
    tsvs = glob.glob(os.path.join(root, "data", "symbols", "*", "metadata",
                                  "non_owner_slot4.tsv"))
    if not tsvs:
        pytest.skip("table `non_owner_slot4.tsv` absente du checkout")
    for t in tsvs:
        with open(t, "r", encoding="utf-8") as f:
            assert "LegacyOfCombat" not in f.read(), (
                "%s porte LegacyOfCombat : la face NON-OWNER existerait" % t)


# ---------------------------------------------------------------------------------------------
# 7. L'IMPORT ISOLE (cliquet #433-r1)
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("mod", [
    "engine.runner.operations.triggers.loki.legacy_of_combat",
    "engine.playbook.legacy_of_combat",
])
def test_le_module_s_importe_SEUL_en_process_frais(mod):
    """Chaque module d'`engine/**` doit s'importer seul. Une arete neuve le casserait sans qu'aucun
    test fonctionnel ne bouge."""
    import subprocess
    import sys as _s
    r = subprocess.run([_s.executable, "-c", "import " + mod], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
