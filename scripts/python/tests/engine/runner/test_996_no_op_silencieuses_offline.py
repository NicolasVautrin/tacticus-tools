"""CLIQUET #996 (volet OFFLINE) -- les TROIS no-op silencieuses portees par la tranche :
1010 `StormOfFlensingBlades`, 1133 `WarConstruct`, 1185 `ForwardObservers`.

Ce que ce fichier fige, et pourquoi chaque cran existe :

  1. **LE REGISTRE.** Une ability absente d'`ABILITY_CLASSES` est routee par
     `AbilityHandler.visit_ActiveAbilityMessage` vers un NO-OP : `ported: False`, 0 degat, 0 effet,
     AUCUNE erreur. La face DECISION peut donc la CHOISIR pendant que l'EXECUTION l'ignore --
     divergence d'etat invisible en replay et en self-play. Pour 1185 ce n'etait pas theorique :
     sa face decision etait DEJA portee (`engine/playbook/loki_custom.py::ForwardObserversPlaybook`)
     quand sa face combat ne faisait rien.
  2. **LES DEUX DONNEES OBLIGATOIRES**, dans le meme commit : `TARGETING_OPTIONS` (sans lui,
     `get_invalid_target_reason` rend 0 immediatement -- gate DESARME en silence) et le litteral
     `ABILITY_ATTACK_TYPE` (3e argument d'`AActiveAbility$$.ctor`).
  3. **LE CONTRAT DE DISJONCTION** : un masque migre sur la classe SORT de
     `TARGETING_OPTIONS_UNPORTED`. `probe_181` est un garde d'EXISTENCE, structurellement aveugle a
     la DOUBLE declaration -- c'est ce cran-la qui a deja rendu `master` rouge.
  4. **LES ORDINAUX MESURES A LA CONVERSION.** `probe_313` compare le MIRROR au BUILD : il redevient
     vert des qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE AU SITE, elle,
     a change. Ce cran-la garde l'ordinal tel qu'il a ete lu au decompile.
  5. **LA STRUCTURE DES TROIS ARBRES.** C'est le seul cran qui distingue « l'ability est inscrite »
     de « l'ability fait ce que le natif fait ». En particulier :
       * 1185 lit DEUX constantes DIFFERENTES (`nrOfRounds` = 2 sur la CIBLE, `nrOfRounds_2` = 1 sur
         l'OWNER) -- les confondre est le premier ecart possible, et rien dans le nom ne le signale ;
       * 1133 porte le LITTERAL 1 aux deux volets (son kit ne porte NI `constants` NI `variables`) ;
       * 1010 est une DOUBLE attaque NORMALE -- pas un buff, quoi qu'en dise la colonne
         « categorie » de `combat-ability-coverage.md`, qui derive du `damageProfile` de l'ARME du
         porteur et non du behaviour (residu #491-r2 ; 4 des 6 no-op du lot la portaient FAUSSE).

⚠ CE FICHIER EST OFFLINE ET IL EST NOMME COMME TEL (les tests offline heberges dans un `*_live.py`
sont invisibles des gardes de selection, qui excluent les `_live.py` par choix).

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre qui doit RE-JOUER ce fichier (#486-r15). DERIVE des fichiers dont une edition peut
#: rendre faux ce qui est fige ici -- pas un `toujours: True` deguise en glob.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/tau.py",
        "scripts/python/engine/runner/abilities/aeldari.py",
        "scripts/python/engine/runner/abilities/necrons.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/runner/abilities/behaviours/",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/streams/group_type.py",
        "scripts/python/gameconfig.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "cliquet OFFLINE du lot #996 -- registre, contrat de disjonction, ordinaux figes a la "
              "conversion et structure des trois arbres. Aucune grandeur n'est derivee d'une "
              "adresse ni d'un dump : les litteraux natifs sont RECOPIES dans le port, et c'est le "
              "port que ce cliquet garde.",
}

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.behaviours import AtomicGroup, Seq
from engine.entities.effect_type import EffectType
from engine.entities.selectors.accessors import Owner, Target
from engine.entities.selectors.tiles import Caster
from engine.runner.abilities.aeldari import (WAR_CONSTRUCT_ROUNDS, WarConstructAbility,
                                             war_construct_tree)
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.combat import UseActiveAbility
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.necrons import (STORM_OF_FLENSING_BLADES_ATTACKS,
                                             StormOfFlensingBladesAbility,
                                             storm_of_flensing_blades_tree)
from engine.runner.abilities.targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF,
                                               RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.abilities.tau import (CONST_FO_ROUNDS, CONST_FO_ROUNDS_2,
                                         ForwardObserversAbility, forward_observers_tree)
from engine.streams.group_type import GroupType

_STORM = 1010
_WAR_CONSTRUCT = 1133
_FORWARD_OBSERVERS = 1185

#: Ordinaux MESURES au decompile a la conversion (cran 4 -- cf. docstring). Chaque valeur de droite
#: est le litteral LU dans le pseudo-C, pas une relecture du mirror.
ORDINAUX = {
    "ActiveAbilityType.StormOfFlensingBlades": (int(ActiveAbilityType.StormOfFlensingBlades), 1010),
    "ActiveAbilityType.WarConstruct": (int(ActiveAbilityType.WarConstruct), 1133),
    "ActiveAbilityType.ForwardObservers": (int(ActiveAbilityType.ForwardObservers), 1185),
    # 0x462 / 0x575 -- les deux `AddEffect` de `ForwardObserversAbility$$ExecuteBehaviour`.
    "EffectType.Markerlight": (int(EffectType.Markerlight), 0x462),
    "EffectType.ForwardObservers_DamageReduction": (
        int(EffectType.ForwardObservers_DamageReduction), 0x575),
    # 0x516 / 0x506 -- les deux `AddEffect` de `WarConstructAbility$$ExecuteBehaviour`.
    "EffectType.IgnoreUsedAbilityInOverwatch": (int(EffectType.IgnoreUsedAbilityInOverwatch), 0x516),
    "EffectType.WarConstruct_CounterAttack": (int(EffectType.WarConstruct_CounterAttack), 0x506),
    # `GetNumberConstant(config@0x60, <ici>)`, DEUX cles differentes.
    "AbilityConstantType.nrOfRounds": (int(AbilityConstantType.nrOfRounds), 0x45),
    "AbilityConstantType.nrOfRounds_2": (int(AbilityConstantType.nrOfRounds_2), 0x77),
    # 2e argument de `DSLBehaviors$$AtomicGroup` dans `StormOfFlensingBladesAbility$$ExecuteBehaviour`.
    "GroupType.StormOfFlensingBlades_Attacks": (
        int(GroupType.StormOfFlensingBlades_Attacks), 0x3e),
    "AbilityAttackType.Others": (int(AbilityAttackType.Others), 2),
    "AbilityAttackType.DirectTargetAttack": (int(AbilityAttackType.DirectTargetAttack), 0),
}


def test_ordinaux_figes_a_la_conversion():
    """Cran 4 : les ordinaux ECRITS AUX SITES, tels que lus au decompile. `probe_313` redeviendrait
    vert apres un renumerotage du build (il compare mirror et build) ; ce test-la, non."""
    assert ORDINAUX, "table d'ordinaux VIDE -- un test vide passerait pour vert"
    faux = {nom: (lu, attendu) for nom, (lu, attendu) in ORDINAUX.items() if lu != attendu}
    assert not faux, "ordinaux qui ont GLISSE depuis la conversion : %r" % (faux,)


# ------------------------------------------------------------------------------------------------
# 1. Le registre et ses deux donnees obligatoires -- pour les TROIS
# ------------------------------------------------------------------------------------------------

def test_les_trois_sont_au_registre_avec_leurs_deux_donnees_obligatoires():
    attendu = {
        _STORM: (StormOfFlensingBladesAbility, AbilityAttackType.DirectTargetAttack),
        _WAR_CONSTRUCT: (WarConstructAbility, AbilityAttackType.Others),
        _FORWARD_OBSERVERS: (ForwardObserversAbility, AbilityAttackType.Others),
    }
    assert attendu, "perimetre VIDE -- le test passerait pour vert sans rien evaluer"
    for aid, (klass, attack_type) in attendu.items():
        assert ABILITY_CLASSES.get(aid) is klass, (
            "%d a quitte `ABILITY_CLASSES` -- l'IA la choisirait et l'execution serait un NO-OP "
            "SILENCIEUX (zero degat, zero effet, aucune erreur)" % aid)
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        assert opts is not None, (
            "%d entree au registre SANS son masque : `get_invalid_target_reason` rend 0 et le gate "
            "de ciblage est DESARME en silence" % aid)
        assert ABILITY_ATTACK_TYPE.get(aid) == attack_type, (
            "litteral `AbilityAttackType` absent ou faux pour %d -- il se lit dans le 3e argument "
            "d'`AActiveAbility$$.ctor`, jamais dans le profil de degat du kit" % aid)


def test_contrat_de_disjonction_masques_declares_une_seule_fois():
    """Cran 3 : un masque migre sur la classe SORT de `TARGETING_OPTIONS_UNPORTED`. `probe_181`
    verifie qu'un masque EXISTE, jamais qu'il est UNIQUE."""
    unported = {int(k) for k in TARGETING_OPTIONS_UNPORTED}
    assert unported, "table UNPORTED vide -- l'assertion ci-dessous ne prouverait plus rien"
    for aid in (_STORM, _WAR_CONSTRUCT, _FORWARD_OBSERVERS):
        assert aid not in unported, (
            "%d est declaree DEUX fois (registre + TARGETING_OPTIONS_UNPORTED) -- c'est cette "
            "double declaration qui a deja rendu `master` rouge" % aid)


# ------------------------------------------------------------------------------------------------
# 2. Les masques, champ pour champ -- relus au ctor, pas recopies du voisin
# ------------------------------------------------------------------------------------------------

def test_masque_1010_storm_of_flensing_blades():
    """`...StormOfFlensingBladesAbility$$.ctor` : forme FLAGS-DIRECTS,
    `.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x4010, 0, 0)`."""
    opts = StormOfFlensingBladesAbility.TARGETING_OPTIONS
    assert int(opts.rules) == (int(TR.CasterHasNotMoved) | int(TR.TargetIsEnemy)) == 0x4010
    assert bool(opts.self_cast) is False
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE


def test_masque_1133_war_construct():
    """`...WarConstructAbility$$.ctor` : forme FLAGS-DIRECTS,
    `.ctor(&opts, 1, &<TargetingRange statics+0x60>, 1, 0x8000, 0, 0)`. AUCUN bit de cible : le
    domaine est fixe par `isSelfCasting`, pas par le masque."""
    opts = WarConstructAbility.TARGETING_OPTIONS
    assert int(opts.rules) == int(TR.CasterIsPossibleTarget) == 0x8000
    assert bool(opts.self_cast) is True
    assert opts.range == RANGE_SELF
    assert opts.force_melee_target == RANGED_BOOL_FALSE


def test_masque_1185_forward_observers():
    """`...ForwardObserversAbility$$.ctor` : forme FLAGS-DIRECTS,
    `.ctor(&opts, 0, &<TargetingRange statics+0x18>, 0, 0x200004002, 0, 0)`.

    ⚠ `forceMeleeTarget = 0` = `RangedBool.True` -- le SEUL des trois dans ce regime. C'est
    exactement le champ qu'une recopie du voisin aurait rate."""
    opts = ForwardObserversAbility.TARGETING_OPTIONS
    assert int(opts.rules) == (int(TR.TargetMatchesDynamicRule) | int(TR.TargetIsEnemy)
                               | int(TR.TargetIsNotAnObject)) == 0x200004002
    assert bool(opts.self_cast) is False
    assert opts.range == RANGE_FROM_CONFIG
    assert opts.force_melee_target == RANGED_BOOL_TRUE
    assert opts.force_melee_target != RANGED_BOOL_FALSE, (
        "1185 est le seul du lot a `RangedBool.True` -- l'aligner sur ses voisins serait FAUX")


# ------------------------------------------------------------------------------------------------
# 3. La structure des trois arbres -- le cran qui distingue « inscrite » de « fidele »
# ------------------------------------------------------------------------------------------------

def test_arbre_1185_deux_effets_deux_durees_deux_cibles():
    """`op_Addition( AddEffect(1122 Markerlight -> Target, TurnsFromRounds(nrOfRounds)),
                     AddEffect(1397 FO_DamageReduction -> Owner, TurnsFromRounds(nrOfRounds_2)) )`.

    LE POINT DE FIDELITE : DEUX constantes DIFFERENTES et DEUX cibles DIFFERENTES."""
    import gameconfig as GC
    kit = GC.ability("ForwardObservers") or {}
    consts = kit.get("constants") or {}
    # Les deux cles existent DANS LE KIT, et elles ne portent pas la meme valeur : sans ca, la
    # confusion `nrOfRounds` / `nrOfRounds_2` serait INOBSERVABLE et ce test ne prouverait rien.
    assert CONST_FO_ROUNDS.name in consts and CONST_FO_ROUNDS_2.name in consts
    assert int(consts[CONST_FO_ROUNDS.name]) != int(consts[CONST_FO_ROUNDS_2.name]), (
        "les deux constantes de duree de 1185 sont devenues EGALES dans le gameconfig : ce test "
        "ne peut plus distinguer un port qui les confond -- le re-armer avant de le croire")

    tree = forward_observers_tree()
    assert isinstance(tree, Seq)
    mark, self_buff = tree.left, tree.right
    assert isinstance(mark, AddEffect) and isinstance(self_buff, AddEffect)
    assert mark.effect_type == int(EffectType.Markerlight)
    assert isinstance(mark.target_sel, Target), "le Markerlight va sur la CIBLE (`Target@+0x60`)"
    assert mark.duration_rounds == int(consts[CONST_FO_ROUNDS.name])
    assert self_buff.effect_type == int(EffectType.ForwardObservers_DamageReduction)
    assert isinstance(self_buff.target_sel, Owner), (
        "la reduction de degats va sur l'OWNER (`Owner@+0x30`), PAS sur la cible")
    assert self_buff.duration_rounds == int(consts[CONST_FO_ROUNDS_2.name])
    assert mark.duration_rounds != self_buff.duration_rounds
    # `duration_turns` doit rester None : le natif passe un `TurnsFromRounds(...)`, donc la
    # conversion `ConvertRoundsToTurns` DOIT avoir lieu -- `duration_turns` la court-circuiterait.
    assert mark.duration_turns is None and self_buff.duration_turns is None


def test_arbre_1133_deux_effets_duree_litterale_1():
    """`op_Addition( AddEffect(1286 -> Target, TurnsFromRounds(1)),
                     AddEffect(1302 -> Owner, TurnsFromRounds(1)) )` -- l'ordre est CELUI DU
    DECOMPILE (`op_Addition([2], [1])`)."""
    import gameconfig as GC
    kit = GC.ability("WarConstruct") or {}
    assert not (kit.get("constants") or {}), (
        "le kit 1133 porte desormais des `constants` -- verifier au decompile si `TurnsFromRounds` "
        "lit toujours le LITTERAL 1 ou une cle de config")

    tree = war_construct_tree()
    assert isinstance(tree, Seq)
    counter, overwatch = tree.left, tree.right
    assert counter.effect_type == int(EffectType.WarConstruct_CounterAttack)
    assert isinstance(counter.target_sel, Target)
    assert overwatch.effect_type == int(EffectType.IgnoreUsedAbilityInOverwatch)
    assert isinstance(overwatch.target_sel, Owner)
    assert counter.duration_rounds == overwatch.duration_rounds == WAR_CONSTRUCT_ROUNDS == 1


def test_arbre_1010_double_attaque_normale_dans_un_groupe_atomique():
    """`AtomicGroup(GroupType.StormOfFlensingBlades_Attacks, <delegue>)` ou le delegue boucle DEUX
    fois sur `UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster))`.

    DEUX NOEUDS DISTINCTS, pas un `Repeat` : les options natives different entre les deux tours
    (`SkipEndTurnFlag = (i == 0)`), donc reutiliser le meme noeud effacerait la difference."""
    tree = storm_of_flensing_blades_tree()
    assert isinstance(tree, AtomicGroup), (
        "le groupe atomique a disparu -- le natif passe par la surcharge 4-arguments de "
        "`DSLBehaviors$$AtomicGroup`, executee par le PROCESSOR")
    inner = tree.child
    assert isinstance(inner, Seq)
    attacks = (inner.left, inner.right)
    assert len(attacks) == STORM_OF_FLENSING_BLADES_ATTACKS == 2
    for atk in attacks:
        assert isinstance(atk, UseActiveAbility), (
            "1010 est une DOUBLE ATTAQUE NORMALE -- l'audit l'annoncait EFFECT/BUFF, colonne "
            "derivee du `damageProfile` de l'ARME du porteur (residu #491-r2)")
        assert isinstance(atk.caster_sel, Caster) and isinstance(atk.target_sel, Target)
        # `spread_pct is None` : aucun etalement -- le natif ne passe aucune option de ce genre.
        assert atk.spread_pct is None
    assert attacks[0] is not attacks[1], (
        "les deux attaques sont le MEME objet : un `Repeat` deguise, qui efface la difference "
        "d'options entre les tours i=0 et i=1")


def test_1010_ne_pose_aucun_effet():
    """CONTRE-EPREUVE de la categorie annoncee. L'audit disait EFFECT/BUFF ; le decompile ne porte
    NI `AddEffect` NI `AddTrait` NI `ChangeStat`. Ce test rougit si quelqu'un « complete » l'arbre
    avec un effet invente."""
    tree = storm_of_flensing_blades_tree()
    vus = []
    pile = [tree]
    while pile:
        n = pile.pop()
        vus.append(type(n).__name__)
        for attr in ("child", "left", "right"):
            sub = getattr(n, attr, None)
            if sub is not None and hasattr(sub, "execute"):
                pile.append(sub)
    assert vus, "parcours VIDE -- le test ne prouverait rien"
    assert "AddEffect" not in vus and "AddTrait" not in vus and "ChangeStat" not in vus, (
        "1010 s'est vu ajouter une pose d'effet : le decompile n'en porte aucune (noeuds vus : %r)"
        % (vus,))
