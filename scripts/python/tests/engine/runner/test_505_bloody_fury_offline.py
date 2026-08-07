"""GARDE #505 (OFFLINE PURE) -- `1129 BloodyFury` (`worldTerminator` « Wrask », WorldEaters),
face EXECUTION.

CE QU'ELLE PROTEGE. Avant ce port, 1129 etait absente d'`ABILITY_CLASSES` : le cast tombait sur le
no-op SILENCIEUX d'`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet,
AUCUNE erreur). Ce fichier fige les cinq choses qui peuvent regresser sans qu'aucun autre test ne
rougisse :

  1. **LE REGISTRE** -- l'entree dans `ABILITY_CLASSES`. Sa disparition rendrait l'ability muette,
     pas rouge.
  2. **LES DEUX LITTERAUX DU REGISTRE** (`TARGETING_OPTIONS`, `ABILITY_ATTACK_TYPE`), et la
     DISJONCTION : 1129 ne doit PLUS etre dans `TARGETING_OPTIONS_UNPORTED`. Le masque vient de la
     forme **PRESET SEUL** (copie PURE des 0x40 octets de `TargetingOptions` statics `+0x40`, par la
     surcharge a DEUX arguments) : le decompile ressemble a un PRESET+FLAGS dont le litteral aurait
     disparu, et seules les XREFS ENTRANTES tranchent -- exactement le piege de `1029 Drachnyen`.
  3. **LA FORMULE DE COUPS** -- le SNOWBALL `Sum(nrOfHits, Min(extraHit x TotalTimesAttacked(Owner),
     maxNrOfHits - nrOfHits))`. Trois crans y sont figes : le PLAFOND (`maxNrOfHits`), l'ORDRE des
     operandes du `Subtract` (`maxNrOfHits - nrOfHits` ; l'inverse rendrait un `Min` NEGATIF et
     tuerait le snowball), et le fait que le compteur lu est le TOTAL DE LA BATAILLE.
  4. **LES DEUX COMPTEURS D'ATTAQUES RECUES, ET LEUR RESET ASYMETRIQUE.** `RegisterAttackReceived`
     incremente `+0x34` ET `+0x38` ; `ResetAttacksReceivedThisTurn` n'efface QUE `+0x38`. Brancher
     la formule sur le compteur PER-TOUR est une faute SILENCIEUSE (elle ne se voit qu'apres un
     changement de tour) : ce fichier la fait rougir sans live.
  5. **LE `hits` DU SELECTEUR DE TRI = 1**, LU au champ `<DSLFormulas+0x20>` (la formule-constante
     `1` memoisee par `DSLFormulas$$.ctor`) et NON `nrOfHits` -- c'est l'ecart avec le voisin
     `1048 FragstormGrenadeLauncher`, qui monte la MEME feuille et passe, lui,
     `Direct(GetNumberConstant(0x2f))`.

Mesure live de bout en bout (`ported`, snowball, chaine, degats par coup, report) :
`python scripts/python/probe_505_bloody_fury.py --attackers 0,1,3 --attacks 3`.
ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE SOCLE COMMUN (la cascade des `conftest.py` et sa fermeture) N'EST PLUS ICI : le
        # foyer le DERIVE (`declencheur_cliquet.chemins_du_harnais`, #531). Pour ce repertoire
        # il rend 161 chemins -- un sur-ensemble strict des quatorze qui etaient recopies ici.
        # PROPRE A CE FICHIER, perimetre pris LARGE : la FERMETURE D'IMPORTS d'un test d'ability
        # compte ~139 modules (charger une ability tire le registre, le vocabulaire DSL, les
        # Operations, l'IA et le pathfinding). Foyers VRAIMENT load-bearing, pour la relecture :
        # `abilities/worldeaters.py` (le port), `runner/components.py` +
        # `operations/minimal_health.py` (les DEUX compteurs et leur reset asymetrique),
        # `entities/formulas.py` (`TotalTimesAttacked`), `abilities/behaviours/context.py`
        # (le substrat `totalTimesAttacked` du dict d'unite), `handler.py` + `attack_type.py` +
        # `targeting.py` (les registres et la disjonction).
        "scripts/python/engine/**/*.py",
        # `scripts/python/*.py` a ete RETIRE (#486-r24) : il couvrait les ~830 probes de la
        # racine, dont aucun ne peut changer le verdict de ce fichier -- il ne les importe pas.
        # Ce qu'il servait vraiment (la cascade du harnais) est desormais DERIVE.
        # Les constantes de 1129 (`nrOfHits`/`extraHit`/`maxNrOfHits`/`damageProfile`) viennent du
        # gameconfig du BUILD.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'entree au registre `ABILITY_CLASSES`, les deux litteraux du "
              "registre (masque 0x4000 issu du PRESET SEUL statics+0x40, et AbilityAttackType 0) "
              "avec la DISJONCTION vis-a-vis de `TARGETING_OPTIONS_UNPORTED`, la formule de coups "
              "SNOWBALL et son plafond, la lecture du compteur TOTAL DE BATAILLE (et non du "
              "per-tour), et le `hits = 1` du selecteur de tri. Aucun runner, aucune session "
              "Frida : le seul acces disque est le depot (gameconfig du build).",
}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import gameconfig as GC                                                    # noqa: E402
from engine.dsl.base import DslContext                                     # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.formulas import TotalTimesAttacked                    # noqa: E402
from engine.entities.selectors.accessors import Owner, Target              # noqa: E402
from engine.entities.selectors.units import AdjacentEnemies, Damageable, Sub  # noqa: E402
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,      # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (RANGE_ADJACENT,             # noqa: E402
                                               RANGED_BOOL_FALSE,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.abilities.worldeaters import (BLOODY_FURY_ID,           # noqa: E402
                                                 BLOODY_FURY_PROFILE,
                                                 BloodyFuryAbility,
                                                 bloody_fury_hits_formula,
                                                 bloody_fury_other_targets,
                                                 bloody_fury_tree)
from engine.runner.components import UnitComponent                         # noqa: E402
from engine.runner.operations.damage_prediction_sort import (              # noqa: E402
    SortTargetsByDamagePrediction)

BLOODY_FURY = int(ActiveAbilityType.BloodyFury)      # 1129


def test_1129_est_au_registre_des_abilities_portees():
    """(1) Sans cette entree, `visit_ActiveAbilityMessage` pose `ported: False` et RETOURNE."""
    assert BLOODY_FURY == 1129
    assert BLOODY_FURY in ABILITY_CLASSES
    assert ABILITY_CLASSES[BLOODY_FURY] is BloodyFuryAbility


def test_1129_masque_de_ciblage_attack_type_et_disjonction():
    """(2) `preset statics+0x40` recopie par la surcharge COPIE PURE a DEUX arguments :
    `rules = 0x4000` (`TargetIsEnemy` SEUL), `isSelfCasting = 0`, `range` = `TargetingRange`
    statics `+0x30` = `RANGE_ADJACENT`, `forceMeleeTarget = 1` = `RangedBool.False`. Puis
    `AActiveAbility..ctor(this, &opts, 0)` -> `AbilityAttackType.DirectTargetAttack`."""
    opts = BloodyFuryAbility.TARGETING_OPTIONS
    assert opts is not None, "masque ABSENT -> `get_invalid_target_reason` devient PERMISSIF"
    assert int(opts.rules) == int(TR.TargetIsEnemy) == 0x4000
    assert opts.self_cast is False
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert ABILITY_ATTACK_TYPE.get(BLOODY_FURY) == AbilityAttackType.DirectTargetAttack
    # CONTRAT DE DISJONCTION : une ability a UNE source de masque, jamais deux.
    assert BLOODY_FURY not in TARGETING_OPTIONS_UNPORTED, (
        "1129 est au registre COMBAT : sa ligne de `TARGETING_OPTIONS_UNPORTED` doit sortir dans "
        "le MEME commit")


def test_1129_constantes_de_config_lues_au_decompile():
    """Les trois `GetNumberConstant` de `$$GetNumTotalHits`/`$$GetNumExtraHits`, par leur MEMBRE
    d'enum, plus le profil et la nature du coup -- tous LUS dans le gameconfig du build."""
    assert int(AbilityConstantType.nrOfHits) == 0x2F
    assert int(AbilityConstantType.extraHit) == 0x2B
    assert int(AbilityConstantType.maxNrOfHits) == 0x48
    cfg = GC.ability(BLOODY_FURY_ID) or {}
    consts = cfg.get("constants") or {}
    assert int(consts["nrOfHits"]) == 1
    assert int(consts["extraHit"]) == 1
    assert int(consts["maxNrOfHits"]) == 8
    assert consts["damageProfile"] == BLOODY_FURY_PROFILE == "Chain"
    # `attackRangeType = Melee` -> l'arbre monte `is_melee=True`.
    assert cfg.get("attackRangeType") == "Melee"


def _ctx(total_times_attacked: int) -> DslContext:
    """Contexte MINIMAL : la formule ne lit que l'OWNER, par la cle `totalTimesAttacked` que
    `runner/abilities/behaviours/context.py::_unit_dict` publie."""
    owner = {"id": 1, "team": 1, "totalTimesAttacked": int(total_times_attacked),
             "times_attacked": 0}
    return DslContext(units=[owner], caster=owner, target=None)


def test_1129_formule_de_coups_snowball_et_son_plafond():
    """(3) `Sum(Direct(nrOfHits), Min(Multiply(Direct(extraHit), TotalTimesAttacked(Owner)),
    Subtract(Direct(maxNrOfHits), Direct(nrOfHits))))` -- balaye sur TOUTE la plage, plafond
    compris. Config 1129 : nrOfHits=1, extraHit=1, maxNrOfHits=8.

    Le point `k = 0` est le TEMOIN DEGENERE (coups = `nrOfHits`) et les points `k >= 7` sont le
    PLAFOND : sans eux, une formule sans `Min` passerait."""
    f = bloody_fury_hits_formula(1, 1, 8)
    mesure = {k: int(f.evaluate(_ctx(k))) for k in (0, 1, 2, 3, 6, 7, 8, 20)}
    assert mesure == {0: 1, 1: 2, 2: 3, 3: 4, 6: 7, 7: 8, 8: 8, 20: 8}, mesure
    # CONFRONTATION LIVE (probe_505, regimes TEMOIN et SNOWBALL) : `+0x34 = 0` -> 1 coup ;
    # `+0x34 = 3` -> 4 coups, per-coup bit-exact [8006, 4775, 5049, 4390] des deux cotes.
    assert int(f.evaluate(_ctx(0))) == 1
    assert int(f.evaluate(_ctx(3))) == 4


def test_1129_ordre_des_operandes_du_subtract():
    """(3bis) `Subtract(Direct(maxNrOfHits), Direct(nrOfHits))` -- l'ORDRE est LU au call-site.
    Inverse, le `Min` deviendrait NEGATIF et le snowball rendrait MOINS que `nrOfHits`.

    Le controle a besoin d'un jeu de constantes ou l'inversion est VISIBLE : avec `nrOfHits = 1` et
    `maxNrOfHits = 8`, l'ecart `7` vs `-7` est franc."""
    bon = bloody_fury_hits_formula(1, 1, 8)
    inverse = bloody_fury_hits_formula(8, 1, 1)    # meme arbre, bornes echangees
    assert int(bon.evaluate(_ctx(20))) == 8
    assert int(inverse.evaluate(_ctx(20))) < 8, (
        "un `Subtract` inverse doit se voir : sinon ce controle ne mesure rien")


def test_1129_le_compteur_lu_est_le_total_de_bataille_pas_le_per_tour():
    """(4) `TotalTimesAttackedFormula$$Calculate` rend `ActorStatisticsComponent + 0x34`.
    `RegisterAttackReceived` incremente `+0x34` ET `+0x38` ; `ResetAttacksReceivedThisTurn`
    n'efface QUE `+0x38`. Le port doit donc : (a) bumper les DEUX au meme site, (b) ne remettre a
    zero QUE le per-tour au changement de tour, (c) faire lire le TOTAL par la formule.

    C'est le cran qu'un live seul ne montre pas : brancher la formule sur le per-tour donne le MEME
    resultat tant qu'on ne traverse pas de tour."""
    from engine.runner.operations.minimal_health import (record_attacked,
                                                         reset_times_attacked)
    from engine.runner.state import State

    st = State()
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id="worldTerminator", alive=True))
    uid = ent.id
    uc = st.get_entity(uid).get_component(UnitComponent)
    assert uc.total_times_attacked == 0 and uc.times_attacked_this_turn == 0

    for _ in range(3):                       # (a) les DEUX montent au MEME site
        record_attacked(st, uid)
    assert (uc.total_times_attacked, uc.times_attacked_this_turn) == (3, 3)

    reset_times_attacked(st)                 # (b) SEUL le per-tour retombe
    assert (uc.total_times_attacked, uc.times_attacked_this_turn) == (3, 0)

    record_attacked(st, uid)
    assert (uc.total_times_attacked, uc.times_attacked_this_turn) == (4, 1)

    # (c) la formule lit le TOTAL : apres le reset, un port branche sur le per-tour rendrait 1.
    unite = {"id": uid, "team": 1, "totalTimesAttacked": uc.total_times_attacked,
             "times_attacked": uc.times_attacked_this_turn}
    ctx = DslContext(units=[unite], caster=unite, target=None)
    assert int(TotalTimesAttacked(Owner()).evaluate(ctx)) == 4
    # ... et le noeud SANS selecteur garde la forme DEGRADEE de la face PREDICTION.
    assert int(TotalTimesAttacked().evaluate(DslContext(times_attacked=9))) == 9


def test_1129_forme_de_l_arbre_et_hits_du_selecteur_de_tri():
    """(5) `ChainLeftOverHitsAttackDamage(Owner, Target, SortTargetsByDamagePrediction(...),
    "BloodyFury", "Chain", <formule de coups>, extraHits = 0, is_melee = True)` et surtout
    `hits = 1` dans le SELECTEUR DE TRI (`<DSLFormulas+0x20>`), pas `nrOfHits`."""
    hits_node = bloody_fury_hits_formula(1, 1, 8)
    tree = bloody_fury_tree(None, hits_node, 1000, 2000, 15)
    assert isinstance(tree, ChainLeftOverHitsAttackDamage)
    assert isinstance(tree.caster_sel, Owner) and isinstance(tree.target_sel, Target)
    assert tree.ability_id == BLOODY_FURY_ID and tree.profile == "Chain"
    assert tree.is_melee is True
    assert tree.native_factory == "attack"
    assert tree.hits is hits_node, "le `hits` de la CHAINE est la FORMULE, pas une constante"
    assert int(tree.extra_hits) == 0, (
        "`extraHitsAfterTargetKilled` est NULL au call-site natif : copier le patron de "
        "`1006 MultiThreatEliminator` donnerait un coup bonus par ennemi tue")

    chain = tree.next_target_sel
    assert isinstance(chain, SortTargetsByDamagePrediction)
    assert chain.hits == 1, (
        "le natif passe `<DSLFormulas+0x20>` = `Direct(1)` -- recopier le `Direct(nrOfHits)` du "
        "voisin 1048 changerait l'ordre de priorite du report")
    assert chain.ability_type == BLOODY_FURY
    assert chain.damage_profile == "Chain" and chain.is_melee is True
    assert isinstance(chain.attacker, Owner)


def test_1129_pool_de_report_est_adjacent_moins_la_cible():
    """`$$GetOtherTargets` = `Damageable(AdjacentEnemies(Owner) op_Subtraction Target)`.
    La FORME est figee ici : un `SurroundingEnemies(range)` (le patron de 1048) elargirait le pool
    a un disque, alors que 1129 n'a meme pas de constante `range`."""
    sel = bloody_fury_other_targets()
    assert isinstance(sel, Damageable)
    inner = sel.inner
    assert isinstance(inner, Sub)
    assert isinstance(inner.a, AdjacentEnemies)
    assert isinstance(inner.a.center, Owner), "le natif passe `DSLSelectors+0x30` = Owner"
    assert int(inner.a.radius.evaluate(_ctx(0))) == 1, "AdjacentEnemies = ring 1, jamais un disque"
    assert isinstance(inner.b, Target)
    assert (GC.ability(BLOODY_FURY_ID) or {}).get("constants", {}).get("range") is None, (
        "1129 n'a AUCUNE constante `range` : sa portee vient du preset (RANGE_ADJACENT)")
