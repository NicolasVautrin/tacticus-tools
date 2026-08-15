"""#939 -- cliquet OFFLINE du port de `1144 BioMinefield` (`tyranBiovore`).

Ce que chaque cran garde, et pourquoi il peut ROUGIR :

  1. **LE CONTRAT DU REGISTRE** -- `1144` est dans `ABILITY_CLASSES` AVEC son `TARGETING_OPTIONS`
     et son `ABILITY_ATTACK_TYPE`, et elle a QUITTE `TARGETING_OPTIONS_UNPORTED`. Sans le masque,
     `get_invalid_target_reason` rend 0 et le gate de ciblage saute EN SILENCE ; en double, les
     deux sources divergeraient sans bruit.
  2. **LES ORDINAUX ECRITS AU SITE** -- `probe_313` compare le MIRROR au BUILD, donc il redevient
     vert des qu'on regenere un mirror renumerote, alors que la valeur ECRITE ici, elle, a change.
     Ce cran fige les cinq ordinaux que la tranche a MESURES au decompile.
  3. **LA STRUCTURE DE L'ARBRE, noeud par noeud** -- c'est le seul cran qui distingue le port de
     l'ability de sa CARICATURE. Il verifie notamment `ChildrenOf` et NON `Children` : les deux
     primitives natives sont HOMONYMES, et brancher la mauvaise rend un ensemble TOUJOURS VIDE ->
     condition toujours fausse -> branche `then` INATTEIGNABLE, sans aucune erreur.
  4. **LES DEUX COMPOSITES NEUFS** -- `random_adjacent_free_tile` et `has_adjacent_enemies` sont
     des FABRIQUES (le natif compose, il n'alloue aucun selecteur dedie). Si quelqu'un les
     re-implemente en classe, la composition cesse d'etre la source unique.
  5. **LE SEUIL `>= 1` d'`has_adjacent_enemies`** -- le nom de ctor affiche par ghidra
     (`AmountIsGreaterAbilityTrigger`) est un mislabel ICF : le singleton alloue est celui
     d'`AmountIsEqualOrGreater`. Lire `>` rendrait le predicat faux pour exactement UN ennemi
     adjacent, le cas NORMAL.
  6. **L'UTILITE IMPOSEE AU MOUVEMENT** -- `PerformAIMovement` doit porter l'`UtilityType` 62 lu
     dans `BioMinefieldAbility$$.ctor` (`UtilityBucket(0x3e)`), pas le playbook par defaut.
  7. **LES CONSTANTES DE CONFIG SONT LUES, PAS FIGEES** -- le port passe par
     `GetNumberConstant`/`GetStringConstant` ; ce cran verifie que le gameconfig du build les porte
     encore et que ce sont bien elles que l'arbre consomme.

MESURE LIVE de reference (branche `else`, board MC1_67 / seed 777, 2026-08-11) : 3 mines
`tyranSmnSporeMine` adjacentes a la CIBLE, `BioMinefield_Target` sur elle a 1 tour, parent = la MoW.
Rejouable : `python probe_939_bio_minefield.py --state-file <ABSOLU>`.

⚠ **CE QUI N'EST PAS COUVERT ICI** : la branche `then` n'a PAS ete confrontee LIVE (les mines de
1144 sont adjacentes a un ennemi par construction, donc mortes au tour suivant -- cf. la docstring
du probe). Ce fichier en garde la STRUCTURE, pas le comportement observe. Residu `#939-r1`.

ASCII only.
"""
from __future__ import annotations

import gameconfig as GC

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.behaviours import If, Seq
from engine.entities.effect_type import EffectType
from engine.entities.formulas import Count
from engine.entities.selectors.accessors import Owner, Subject, Target
from engine.entities.selectors.composites import random_adjacent_free_tile
from engine.entities.selectors.geometry import EntitiesWithoutEffects, PickRandomly
from engine.entities.selectors.tiles import AdjacentTiles, CanAddUnit, Children, ChildrenOf
from engine.entities.selectors.units import (Alive, AdjacentUnits, Enemies, Filter, Tiles,
                                             UnitsWithoutTrait)
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggers import AmountIsEqualOrGreater, has_adjacent_enemies
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.ai_control import PerformAIMovement
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.behaviours.lifecycle import Kill
from engine.runner.abilities.behaviours.summon import Spawn
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.loki.bio_minefield import (BIO_MINEFIELD_ID,
                                                        BIO_MINEFIELD_MOVE_UTILITY,
                                                        BioMinefieldAbility, bio_minefield_tree)
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED, targeting_options_for
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.utilities.utility_type import UtilityType

#: Perimetre qui doit RE-JOUER ce fichier (#486-r15). Pris LARGE : le port traverse le vocabulaire
#: DSL (selecteurs/triggers/formules/behaviours), le registre d'abilities, la couche AI-control et
#: les utilites de tuile.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/engine/entities/",
        "scripts/python/engine/runner/abilities/",
        "scripts/python/engine/runner/operations/summon_ai.py",
        "scripts/python/engine/ai/action_generators.py",
        "scripts/python/engine/utilities/",
        "scripts/python/engine/playbook/noncomparable/",
    ),
    "build": False,
    "toujours": False,
    "raison": "cliquet OFFLINE du port 1144 -- registre, ordinaux figes, structure de l'arbre",
}

#: Ordinaux MESURES au decompile a la conversion (cran 2 -- cf. docstring).
ORDINAUX = {
    "ActiveAbilityType.BioMinefield": (int(ActiveAbilityType.BioMinefield), 1144),
    "EffectType.BioMinefield_Target": (int(EffectType.BioMinefield_Target), 1315),
    "EffectType.Taunted_BlockMovement": (int(EffectType.Taunted_BlockMovement), 25),
    "UtilityType.BioMinefield_MoveTowardsTarget": (
        int(UtilityType.BioMinefield_MoveTowardsTarget), 62),
    "UnitTrait.Object": (int(UnitTrait.Object), 13),
    "UnitTrait.Steppable": (int(UnitTrait.Steppable), 27),
    "UnitSelectionType.OnlyAliveAndTargetable": (
        int(UnitSelectionType.OnlyAliveAndTargetable), 3),
    "AbilityAttackType.Others": (int(AbilityAttackType.Others), 2),
}


# ------------------------------------------------------------------------------------------------
# 1. Le contrat du registre
# ------------------------------------------------------------------------------------------------

def test_1144_est_au_registre_avec_ses_deux_donnees_obligatoires():
    assert ABILITY_CLASSES.get(1144) is BioMinefieldAbility, (
        "1144 a quitte `ABILITY_CLASSES` -- l'IA la choisirait et l'execution serait un NO-OP "
        "SILENCIEUX (zero degat, zero effet, aucune erreur)")
    opts = getattr(BioMinefieldAbility, "TARGETING_OPTIONS", None)
    assert opts is not None, (
        "1144 entree au registre SANS son masque : `get_invalid_target_reason` rend 0 et le gate "
        "de ciblage est DESARME en silence")
    assert ABILITY_ATTACK_TYPE.get(1144) == AbilityAttackType.Others, (
        "littéral `AbilityAttackType` absent ou faux -- `AActiveAbility$$.ctor(this, &opts, 2)`")


def test_le_masque_est_celui_du_ctor_et_les_deux_sources_restent_disjointes():
    """`BioMinefieldAbility$$.ctor` : forme FLAGS-DIRECTS a 7 parametres, `rules = 0x40004020`,
    `range = <TargetingRange statics+0x48>` = RANGE_WHOLE_BOARD."""
    opts = BioMinefieldAbility.TARGETING_OPTIONS
    assert int(opts.rules) == 0x40004020, (
        "masque %#x, attendu 0x40004020 (flags directs)" % int(opts.rules))
    attendu = int(TR.TargetHasFreeAdjacentTile | TR.TargetIsEnemy | TR.AllowNullCasterTile)
    assert int(opts.rules) == attendu, "le masque ne se decompose plus sur les trois membres nommes"
    assert opts.range is not None and opts.range.use_whole_board, (
        "portee : RANGE_WHOLE_BOARD attendu (`statics+0x48`)")
    assert int(opts.rules) & int(TR.AllowNullCasterTile), (
        "bit `AllowNullCasterTile` perdu : c'est la PERMISSION sans laquelle aucune ability de MoW "
        "n'est castable (une machine n'a aucune tuile)")
    assert 1144 not in TARGETING_OPTIONS_UNPORTED, (
        "doublon avec `ABILITY_CLASSES[1144]` -- contrat de disjonction rompu : "
        "`targeting_options_for` en servirait une et l'autre deriverait en silence")
    assert int(targeting_options_for(1144).rules) == 0x40004020, (
        "`targeting_options_for(1144)` ne rend plus le masque -- la migration a casse le lecteur")


# ------------------------------------------------------------------------------------------------
# 2. Les ordinaux ECRITS au site
# ------------------------------------------------------------------------------------------------

def test_les_ordinaux_mesures_a_la_conversion_sont_figes():
    assert ORDINAUX, "table vide -- ce cran ne mesurerait RIEN"
    for nom, (courant, mesure) in sorted(ORDINAUX.items()):
        assert courant == mesure, (
            "%s vaut %d, mesure %d a la conversion : un renumerotage de build a bouge la valeur "
            "ECRITE au site, et `probe_313` (mirror vs build) ne peut pas le voir" %
            (nom, courant, mesure))


def test_les_ordinaux_communs_nomment_autre_chose():
    """Contre-epreuve : confondre les deux enums serait SILENCIEUX en ordinal. `1144` est un
    `ActiveAbilityType` ET un `EffectType` valide -- mais ils ne nomment pas la meme chose."""
    homonyme = getattr(EffectType, "_value2member_map_", {}).get(1144)
    assert homonyme is not None, (
        "gisement VIDE : `1144` n'est plus un `EffectType` valide -- ce cran passerait pour vert "
        "sans rien mesurer ; le re-choisir sur un ordinal reellement partage")
    assert homonyme.name != "BioMinefield", (
        "`EffectType(1144)` s'appelle desormais BioMinefield : l'ordinal ne discrimine plus, et "
        "toute confusion d'enum deviendrait invisible")


# ------------------------------------------------------------------------------------------------
# 3. La structure de l'arbre, noeud par noeud
# ------------------------------------------------------------------------------------------------

def test_l_arbre_est_addeffect_puis_if_avec_ses_deux_branches():
    """`Execute( AddEffect(...) & If(cond, move & kill, spawn) )` -- le `Seq` externe est
    `AbilityBehaviour$$op_BitwiseAnd`, donc l'`AddEffect` passe QUELLE QUE SOIT la branche."""
    arbre = bio_minefield_tree()
    assert isinstance(arbre, Seq), "la racine n'est plus le `op_BitwiseAnd(AddEffect, If)`"
    marque, branche = arbre.left, arbre.right
    assert isinstance(marque, AddEffect), "le terme GAUCHE n'est plus l'`AddEffect`"
    assert marque.effect_type == int(EffectType.BioMinefield_Target)
    assert marque.duration_turns == 1, (
        "`turns` = `<DSLFormulas+0x20>` = `Direct(1)`, deja en TOURS -- pas des ROUNDS")
    assert isinstance(marque.target_sel, Target), "`targets` = `Target@DSLSelectors+0x60`"
    assert isinstance(marque.source_ref, Owner), (
        "`source` = `Owner@DSLSelectors+0x30` -- c'est cette source que la feuille d'utilite 62 "
        "relira pour designer la cible du deplacement des mines")
    assert isinstance(branche, If), "le terme DROIT n'est plus le `If`"
    assert branche.otherwise is not None, (
        "la branche `else` a disparu : le natif passe QUATRE arguments a `DSLBehaviors$$If`, et "
        "c'est elle qui porte tout le summon")


def test_la_condition_compte_les_enfants_VIVANTS_du_owner():
    """⚠ LE CRAN LE PLUS IMPORTANT DU FICHIER. `DSLSelectors$$Children(parent)` (AVEC argument) est
    `ChildrenOf`, pas `Children` (SANS argument = l'accumulateur des summons de CE cast). Brancher
    `Children` rendrait un ensemble TOUJOURS VIDE au premier cast -> condition toujours fausse ->
    branche `then` INATTEIGNABLE, sans aucune erreur."""
    cond = bio_minefield_tree().right.cond
    assert isinstance(cond, AmountIsEqualOrGreater), (
        "la condition n'est plus un `AmountIsEqualOrGreater` (`>=`) -- un `>` STRICT decalerait "
        "le seuil de un")
    assert isinstance(cond.a, Count), "le terme gauche doit etre `DSLFormulas$$Count(...)`"
    alive = cond.a.selector
    assert isinstance(alive, Alive), "`Alive(...)` manquant : les mines MORTES compteraient"
    assert isinstance(alive.source, ChildrenOf), (
        "`ChildrenOf` attendu, trouve %s -- `Children` (sans argument) est l'accumulateur du cast "
        "COURANT et rendrait TOUJOURS un ensemble vide ici" % type(alive.source).__name__)
    assert not isinstance(alive.source, Children), "homonyme `Children` branche par erreur"
    assert isinstance(alive.source.parent, Owner), "`Children(Owner@DSLSelectors+0x30)`"
    seuil = int(cond.b.evaluate(None)) if hasattr(cond.b, "evaluate") else int(cond.b)
    assert seuil == int(((GC.ability(BIO_MINEFIELD_ID) or {}).get("constants") or {})
                        ["nrOfSummons"]), (
        "le seuil doit etre LU dans `GetNumberConstant(nrOfSummons)`, pas fige")


def test_la_branche_then_est_le_mouvement_puis_le_kill():
    then = bio_minefield_tree().right.then
    assert isinstance(then, Seq), "`then` = `PerformAIMovement & Kill` (op_BitwiseAnd)"
    move, kill = then.left, then.right
    assert isinstance(move, PerformAIMovement), (
        "`PerformAIMovement` attendu -- `PerformAIAction` ferait jouer un TOUR d'IA complet "
        "(attaque comprise), ce que le natif ne demande PAS ici")
    assert isinstance(move.selector, EntitiesWithoutEffects), (
        "les mines TAUNTEES ne bougent pas : `EntitiesWithoutEffects(..., [25])`")
    assert list(move.selector.effect_types) == [int(EffectType.Taunted_BlockMovement)], (
        "le tableau d'`EffectType` natif a UN element, ecrit a `+0x20` = 0x19")
    assert int(move.range.evaluate(None)) == 1, "`range` = `Direct(1)` : UNE tuile"
    assert tuple(move.override_utility) == BIO_MINEFIELD_MOVE_UTILITY, (
        "l'utilite de tuile IMPOSEE doit venir du `.ctor` (`UtilityBucket(0x3e)`)")
    assert isinstance(kill, Kill), "`DSLBehaviors$$Kill` attendu"
    assert kill.subject_sel is kill.units_sel, (
        "`Kill(pvVar13, pvVar13, 0)` : le natif passe LE MEME sous-arbre en killer ET en cible -- "
        "les mines se tuent ELLES-MEMES (c'est l'explosion)")
    assert isinstance(kill.units_sel, Filter), "`Filter(AliveChildren(), HasAdjacentEnemies(...))`"


def test_la_branche_else_pose_les_mines_autour_de_la_CIBLE():
    """MESURE LIVE : cible en (1,1), les 3 mines en (2,0), (0,0), (2,1) -- adjacentes a la CIBLE,
    pas au caster (une MoW n'a aucune tuile)."""
    spawn = bio_minefield_tree().right.otherwise
    assert isinstance(spawn, Spawn), "`else` = le `DSLBehaviors$$Spawn`"
    assert spawn.unit_id_constant == "unitId", (
        "`GetStringConstant(config, 0)` = `AbilityConstantType.unitId` -- `unitToSpawn` (8) "
        "rendrait `None` et le spawn serait SILENCIEUSEMENT absent")
    assert spawn.summon_ability == BIO_MINEFIELD_ID
    assert spawn.ability_state is None, (
        "le natif passe `Get(abilityState.<f0>)`/`Get(abilityState.<f1>)`, qui sont EXACTEMENT le "
        "fallback null de `WithStatsFromConfig` -- le defaut du port est donc l'equivalent exact ; "
        "poser un couple ici ferait croire a une divergence")
    tiles = spawn.tile_selector
    assert isinstance(tiles, PickRandomly), "`RandomAdjacentFreeTile` -> `PickRandomAmountSelector`"
    assert isinstance(tiles.source, CanAddUnit), "`CanAddUnit(AdjacentTiles(origin))`"
    assert isinstance(tiles.source.source, AdjacentTiles)
    assert isinstance(tiles.source.source.source, Target), (
        "l'origine est `Target@DSLSelectors+0x60` : les mines apparaissent autour de la CIBLE")
    n = int(tiles.amount.evaluate(None))
    assert n == int(((GC.ability(BIO_MINEFIELD_ID) or {}).get("constants") or {})
                    ["nrOfSummons_2"]), (
        "le nombre de mines doit etre LU dans `GetNumberConstant(nrOfSummons_2)`")
    assert n == 3, "MESURE LIVE : 3 mines posees ; la config du build a bouge -> re-confronter"


# ------------------------------------------------------------------------------------------------
# 4-5. Les deux composites neufs
# ------------------------------------------------------------------------------------------------

def test_random_adjacent_free_tile_compose_et_n_alloue_rien_de_neuf():
    sel = random_adjacent_free_tile(Target(), 7)
    assert isinstance(sel, PickRandomly)
    assert sel.allow_duplicates is False and sel.max_duplicates == 0x7FFFFFFF, (
        "les constantes du `PickRandomAmountSelector` natif (false, 0x7fffffff, false) sont les "
        "DEFAUTS de `PickRandomly` -- les reposer dupliquerait une valeur au lieu de la lire")
    assert sel.ignore_forced_targets is False
    assert isinstance(sel.source, CanAddUnit)
    assert sel.source.allow_steppable is True, (
        "#462-...-r5-r3 : la surcharge a UN argument de `DSLSelectors$$CanAddUnit` -- celle "
        "qu'appelle `DSLSelectors$$RandomAdjacentFreeTile` -- code son trigger EN DUR a "
        "`<DSLTriggers+0x48>` = `op_LogicalNot(<trigger nu>)`, donc `ShouldTrigger` FAUX, donc "
        "`allowSteppable` VRAI apres l'inversion de `CanAddUnitTileSelector$$Select`. "
        "L'assertion inverse qui vivait ici (`is False`) etait une DEDUCTION -- << autoriser les "
        "Steppable poserait des mines sur des tuiles occupees >> -- que le corps natif contredit ; "
        "elle est ce que le residu appelait << la branche == 0 implementee partout >>. Le meme "
        "appariement slot/valeur est deja grave par "
        "`tests/engine/runner/test_955r2_free_tiles_steppable_offline.py`")


def test_has_adjacent_enemies_compose_ses_quatre_etages_et_lit_le_seuil_1():
    trig = has_adjacent_enemies(Subject(), Tiles(Subject()))
    assert isinstance(trig, AmountIsEqualOrGreater), (
        "⚠ le singleton alloue par `DSLTriggers$$HasAdjacentEnemies` est celui des DEUX surcharges "
        "d'`AmountIsEqualOrGreater` -- `AmountIsGreater` (STRICT) est une classe DISTINCTE, et la "
        "lire ici rendrait le predicat faux pour exactement UN ennemi adjacent")
    assert int(trig.b.evaluate(None)) == 1, "`Direct(1)` : au moins UN ennemi adjacent"
    assert isinstance(trig.a, Count), "le comptage natif vit dans `ShouldTrigger` -> `Count` ici"
    sans_stepp = trig.a.selector
    assert isinstance(sans_stepp, UnitsWithoutTrait)
    assert sans_stepp.trait == int(UnitTrait.Steppable), "dernier filtre : Steppable (0x1b)"
    sans_obj = sans_stepp.source
    assert isinstance(sans_obj, UnitsWithoutTrait)
    assert sans_obj.trait == int(UnitTrait.Object), "filtre precedent : Object (0xd)"
    ennemis = sans_obj.source
    assert isinstance(ennemis, Enemies), "`DSLSelectors$$Enemies(unit, adj, 3)`"
    assert isinstance(ennemis.inner, AdjacentUnits), "`DSLSelectors$$AdjacentUnits(unitTile, ...)`"
    st = int(UnitSelectionType.OnlyAliveAndTargetable)
    for etage in (sans_stepp, sans_obj, ennemis, ennemis.inner):
        assert etage.selection_type == st, (
            "les QUATRE etages passent `selectionType = 3` au decompile ; sans eux le filtre ne "
            "retiendrait RIEN (defaut historique `None`)")


def test_les_deux_booleens_de_has_adjacent_enemies_retirent_bien_un_etage():
    """Contre-epreuve du cran precedent : les deux `UnitsWithoutTrait` sont CONDITIONNELS au
    decompile. Si le port les posait inconditionnellement, ce cran le verrait."""
    tout = has_adjacent_enemies(Subject(), Tiles(Subject()),
                                include_objects=True, include_steppables=True)
    assert isinstance(tout.a.selector, Enemies), (
        "avec les deux booleens VRAIS, aucun `UnitsWithoutTrait` ne doit rester")
    sans_obj = has_adjacent_enemies(Subject(), Tiles(Subject()), include_objects=True)
    assert isinstance(sans_obj.a.selector, UnitsWithoutTrait)
    assert sans_obj.a.selector.trait == int(UnitTrait.Steppable)
    assert isinstance(sans_obj.a.selector.source, Enemies), "un seul etage doit rester"


# ------------------------------------------------------------------------------------------------
# 6-7. L'utilite imposee, et les constantes LUES
# ------------------------------------------------------------------------------------------------

def test_l_utilite_de_mouvement_est_celle_du_ctor():
    assert BIO_MINEFIELD_MOVE_UTILITY == (int(UtilityType.BioMinefield_MoveTowardsTarget),), (
        "`BioMinefieldAbility$$.ctor` alloue UN `UtilityBucket(0x3e)` -- un bucket de plus ou de "
        "moins changerait le scoring de tuile impose aux mines")
    from engine.utilities.tile import TILE_LEAVES
    entree = TILE_LEAVES.get(UtilityType.BioMinefield_MoveTowardsTarget)
    assert entree is not None and entree[1] is not None, (
        "la feuille 62 a disparu de `TILE_LEAVES` : le scoring impose n'aurait plus AUCUNE feuille "
        "a evaluer et `PerformAIMovement` deviendrait un no-op muet")


def test_les_constantes_de_config_du_build_sont_celles_que_l_arbre_lit():
    cst = (GC.ability(BIO_MINEFIELD_ID) or {}).get("constants") or {}
    assert cst, "la config d'ability `BioMinefield` a disparu du gameconfig du build"
    assert cst.get("unitId") == "tyranSmnSporeMine", (
        "l'unite posee a change : re-confronter live (MESURE : tyranSmnSporeMine)")
    assert int(cst["nrOfSummons"]) == 3 and int(cst["nrOfSummons_2"]) == 3, (
        "`nrOfSummons`/`nrOfSummons_2` ont bouge -- le seuil de branche ET le nombre de mines "
        "viennent de la, et la mesure live (3 mines) est a rejouer")


def test_le_playbook_non_comparable_est_enregistre():
    """Face DECISION : `metadata/active_playbook_builders.tsv` porte `active 1144
    BioMinefieldPlaybook`. Un port de la face COMBAT sans la face DECISION laisserait l'IA choisir
    l'ability par le fallback Comparable."""
    from engine.playbook.noncomparable import PLAYBOOKS
    pb = PLAYBOOKS.get(1144)
    assert pb is not None, "1144 a quitte le registre `PLAYBOOKS` (NonComparable)"
    assert pb.MIN_UTILITY == 1.0, (
        "`BioMinefieldPlaybook$$.cctor` ecrit `Fix64$$op_Implicit(1)` -- c'est le `minUtility` du "
        "`Bucket`, donc le plancher d'acceptation")
    assert pb.ABILITY_ID == int(ActiveAbilityType.BioMinefield)
