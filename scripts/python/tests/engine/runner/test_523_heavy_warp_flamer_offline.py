"""GARDE #523 (OFFLINE PURE) -- `1227 HeavyWarpFlamer` (`thousSekhetar` « Sekhetar Robot »,
Thousand Sons), face EXECUTION.

CE QU'ELLE PROTEGE. Avant ce port, 1227 etait absente d'`ABILITY_CLASSES` : le cast tombait sur le
no-op SILENCIEUX d'`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet,
AUCUNE erreur) alors que la face DECISION la choisissait deja (playbook porte depuis #27). Ce
fichier fige les cinq choses qui peuvent regresser sans qu'aucun autre test ne rougisse :

  1. **LE REGISTRE** -- l'entree dans `ABILITY_CLASSES`. Sa disparition rendrait l'ability muette,
     pas rouge.
  2. **LES DEUX LITTERAUX DU REGISTRE** (`TARGETING_OPTIONS`, `ABILITY_ATTACK_TYPE`). Le masque
     vient de la forme **PRESET STATIQUE COPIE** (`<TargetingOptions statics>+0x140`, AUCUN appel a
     `TargetingOptions$$.ctor`, donc aucun flag ajoute) : il n'existe nulle part comme litteral dans
     le `$$.ctor`, c'est exactement le genre de valeur qu'une regeneration remettrait de travers. Un
     `TARGETING_OPTIONS` absent ne casse rien -- il rend `get_invalid_target_reason` PERMISSIF, en
     silence. Le preset VOISIN `+0x180` (Fragstorm 1048) a le MEME `rules` et l'AUTRE
     `forceMeleeTarget` : recopier celui de la voisine donnerait le bon masque et le mauvais regime
     de portee.
  3. **LES DEUX `reference` DES SELECTEURS DE `GetOtherTargets`**. `AdjacentFriends` et
     `SurroundingEnemies` ont chacun une surcharge ou le MEME selecteur est centre ET reference
     d'equipe, et le port collapse `reference=None` sur `ctx.caster`. Ici le centre de
     `AdjacentFriends` est la **CIBLE** : sans `reference=Target()` le port rendrait les ALLIES du
     caster au lieu de ses ennemis -- le camp INVERSE, sans erreur.
  4. **LE `hits` DU SELECTEUR DE PREDICTION** = **1**, pas `nrOfHits`. Le natif passe le champ
     `<DSLFormulas+0x20>`, que `IdunBattleLogic.Entities.DSLFormulas$$.ctor` initialise a la
     constante 1 ; 1048, qui monte la MEME feuille, y passe `Direct(nrOfHits)`. Copier le patron du
     voisin changerait le classement des cibles de report.
  5. **LE NOEUD DYNAMIQUE `GetNumTotalHits`**, et non un scalaire fige : `Sum(Direct(nrOfHits),
     Min(GetPersistentData(1227, Owner, "PSYCHIC_ATTACKS_KEY"), maxNrOfHits - nrOfHits))`. Le
     compteur est ecrit par la triggered `1546 HeavyWarpFlamer_AttackTracking` (HORS perimetre
     #523) ; tant qu'elle n'est pas portee le noeud rend `nrOfHits`, mais il rendra la vraie valeur
     SANS toucher a ce port le jour ou elle le sera. Les trois regimes (compteur absent / present /
     au-dela du plafond) sont evalues ici.

Mesure live de bout en bout (`ported`, chaine, degats par coup, report, masque vs `fromHere`) :
`python scripts/python/probe_523_heavy_warp_flamer.py` et sa garde
`test_523_heavy_warp_flamer_live.py`.
RE : `docs/rl/case-523-heavy-warp-flamer.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Perimetre pris LARGE, et non feuille a feuille : charger une ability
        # tire le registre, le vocabulaire DSL, les Operations, l'IA et le pathfinding -- la
        # fermeture d'imports MESUREE depasse la centaine de modules, et un declencheur trop etroit
        # est un FAUX VERT. Les foyers vraiment load-bearing, pour la relecture humaine :
        # `abilities/thousandsons.py` (le port), `operations/damage_prediction_sort.py` (le
        # selecteur de chaine), `handler.py` + `attack_type.py` + `targeting.py` (les registres),
        # `behaviours/combat.py` (la feuille partagee de chainage), `entities/formulas.py` +
        # `entities/selectors/**` (les noeuds DSL dont la forme est ASSERTEE ici).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les magnitudes et constantes de 1227 viennent du gameconfig du BUILD.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'entree au registre `ABILITY_CLASSES`, les deux litteraux du "
              "registre (masque 0x4002 issu du preset STATIQUE statics+0x140 copie sans flags, "
              "avec `forceMeleeTarget = RangedBool.True`, et AbilityAttackType 0), les deux "
              "`reference` de `GetOtherTargets`, le `hits = 1` du selecteur de prediction et le "
              "noeud DYNAMIQUE `GetNumTotalHits`. Aucun runner, aucune session Frida : le seul "
              "acces disque est le depot (gameconfig du build pour les magnitudes).",
}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from engine.dsl.base import Const, DslContext                               # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType       # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType           # noqa: E402
from engine.entities.effects.magnitude import ability_var                   # noqa: E402
from engine.entities.formulas import Difference, GetPersistentData, Min, Sum  # noqa: E402
from engine.entities.selectors.accessors import Owner, Target               # noqa: E402
from engine.entities.selectors.tiles import Caster                          # noqa: E402
from engine.entities.selectors.units import (AdjacentFriends, And,           # noqa: E402
                                             Damageable, SurroundingEnemies)
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,       # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                 # noqa: E402
from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG,           # noqa: E402
                                               RANGED_BOOL_TRUE,
                                               DYNAMIC_TARGET_RULE_UNPORTED,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR      # noqa: E402
from engine.runner.abilities.thousandsons import (                          # noqa: E402
    HEAVY_WARP_FLAMER_ID, HEAVY_WARP_FLAMER_PREDICTION_HITS, HEAVY_WARP_FLAMER_PROFILE,
    HEAVY_WARP_FLAMER_STACK_KEY, HeavyWarpFlamerAbility, heavy_warp_flamer_num_extra_hits,
    heavy_warp_flamer_num_total_hits, heavy_warp_flamer_other_targets, heavy_warp_flamer_tree)
from engine.runner.operations.damage_prediction_sort import SortTargetsByDamagePrediction  # noqa: E402

HWF = int(ActiveAbilityType.HeavyWarpFlamer)          # 1227


def _config():
    """Les TROIS constantes de config LUES au decompile (`GetNumberConstant` 0x2f / 0x48 / 0x16)."""
    return (int(ability_var(HEAVY_WARP_FLAMER_ID, "nrOfHits", is_constant=True) or 0),
            int(ability_var(HEAVY_WARP_FLAMER_ID, "maxNrOfHits", is_constant=True) or 0),
            int(ability_var(HEAVY_WARP_FLAMER_ID, "range", is_constant=True) or 0))


def test_1227_est_au_registre_des_abilities_portees():
    """(1) Sans cette entree, `visit_ActiveAbilityMessage` pose `ported: False` et RETOURNE."""
    assert HWF == 1227
    assert HWF in ABILITY_CLASSES, "1227 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #523"
    assert ABILITY_CLASSES[HWF] is HeavyWarpFlamerAbility


def test_1227_masque_de_ciblage_et_attack_type():
    """(2) Preset STATIQUE `<TargetingOptions statics>+0x140`, copie SANS flags :
    `rules = 0x4002`, `range <- TargetingRange statics+0x18` (= `RANGE_FROM_CONFIG`),
    `forceMeleeTarget = 0` (`RangedBool.True` -- l'enum natif est INVERSE : True=0, False=1)."""
    opts = HeavyWarpFlamerAbility.TARGETING_OPTIONS
    assert opts is not None, "TARGETING_OPTIONS absent -> gate PERMISSIF silencieux"
    assert int(opts.rules) == 0x4002
    # decomposition exhaustive : aucun bit residuel
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy)
    assert opts.self_cast is False
    assert opts.range == RANGE_FROM_CONFIG
    # ⚠ le preset VOISIN `+0x180` (Fragstorm 1048) a le MEME `rules` et l'AUTRE `forceMeleeTarget` :
    # c'est le seul champ qui les separe, et il change le regime de portee au contact.
    assert opts.force_melee_target == RANGED_BOOL_TRUE
    # 3e argument d'`AActiveAbility$$.ctor` -- litteral `0`, transcrit tel quel.
    assert ABILITY_ATTACK_TYPE.get(HWF) == AbilityAttackType.DirectTargetAttack


def test_1227_contrat_de_disjonction_des_sources_de_masque():
    """Une ability a UNE source de masque, jamais deux : portee au registre => absente des deux
    listes de non-portage."""
    assert HWF not in TARGETING_OPTIONS_UNPORTED
    assert HWF not in DYNAMIC_TARGET_RULE_UNPORTED


def test_1227_constantes_de_config_et_profil():
    """Les trois `GetNumberConstant` du decompile, nommees par leur membre d'enum."""
    assert int(AbilityConstantType.nrOfHits) == 0x2F
    assert int(AbilityConstantType.maxNrOfHits) == 0x48
    assert int(AbilityConstantType.range) == 0x16
    nr, mx, rng = _config()
    assert (nr, mx, rng) == (4, 9, 2)
    assert HEAVY_WARP_FLAMER_PROFILE == "Flame"


def test_1227_other_targets_est_l_intersection_des_deux_volets():
    """(3) `And(Damageable(AdjacentFriends(Target, ref=Target)),
    SurroundingEnemies(Caster, Const(range), ref=Caster))`.

    Les DEUX `reference` sont le cran : sans elles le port collapse sur `ctx.caster`, et
    `AdjacentFriends` centre sur la CIBLE rendrait alors le camp INVERSE."""
    _nr, _mx, rng = _config()
    sel = heavy_warp_flamer_other_targets(rng)
    assert isinstance(sel, And)
    gauche, droite = sel.a, sel.b
    assert isinstance(gauche, Damageable)
    adj = gauche.inner
    assert isinstance(adj, AdjacentFriends)
    assert isinstance(adj.center, Target), "le centre d'AdjacentFriends est la CIBLE"
    assert isinstance(adj.reference, Target), (
        "reference=None collapserait sur ctx.caster -> les ALLIES du caster, camp INVERSE")
    assert isinstance(adj.radius, Const) and adj.radius.value == 1     # `AdjacentTiles`, pas un rayon
    assert isinstance(droite, SurroundingEnemies)
    assert isinstance(droite.center, Caster)
    assert isinstance(droite.reference, Caster), (
        "surcharge 4 args : le MEME selecteur est centre ET reference d'equipe")
    assert isinstance(droite.radius, Const) and droite.radius.value == rng


def test_1227_forme_de_l_arbre_et_extra_hits_nul():
    """UN seul noeud terminal, `extraHits` NUL, caster `Owner`, cible initiale `Target`, profil
    `Flame`, vecteur RANGED."""
    nr, mx, rng = _config()
    tree = heavy_warp_flamer_tree(None, rng, 1964, 2619, nr, mx, 25)
    assert isinstance(tree, ChainLeftOverHitsAttackDamage)
    assert isinstance(tree.caster_sel, Owner)
    assert isinstance(tree.target_sel, Target)
    assert tree.extra_hits == 0, (
        "`extraHitsAfterTargetKilled` est NULL au call-site ; copier 1006 MultiThreatEliminator "
        "(`Get(GetNumberConstant(0x2b))`) accorderait un coup bonus par ennemi tue")
    assert tree.profile == HEAVY_WARP_FLAMER_PROFILE
    assert tree.is_melee is False
    assert tree.native_factory == "attack"
    assert tree.ability_id == HEAVY_WARP_FLAMER_ID


def test_1227_selecteur_de_chaine_et_son_hits_unitaire():
    """(4) Le selecteur de cible suivante est `SortTargetsByDamagePredictionSelector`, et son
    `hits` vaut **1** (`<DSLFormulas+0x20>`), pas `nrOfHits` comme chez 1048."""
    nr, mx, rng = _config()
    tree = heavy_warp_flamer_tree(None, rng, 1964, 2619, nr, mx, 25)
    chain = tree.next_target_sel
    assert isinstance(chain, SortTargetsByDamagePrediction)
    assert isinstance(chain.attacker, Owner)
    assert isinstance(chain.targets, And), "la source du tri est `GetOtherTargets`, non triee avant"
    assert chain.ability_type == HWF
    assert chain.damage_profile == HEAVY_WARP_FLAMER_PROFILE
    assert chain.is_melee is False
    assert HEAVY_WARP_FLAMER_PREDICTION_HITS == 1
    assert chain.hits == 1, ("`hits` du selecteur de prediction = `<DSLFormulas+0x20>` = 1 ; "
                             "`nrOfHits` (%d) est ce que passe 1048, pas 1227" % nr)


def test_1227_num_total_hits_est_un_noeud_dynamique():
    """(5) `Sum(Direct(nrOfHits), Min(GetPersistentData(1227, Owner, KEY), maxNrOfHits - nrOfHits))`
    -- la FORME, pas la valeur."""
    nr, mx, _rng = _config()
    node = heavy_warp_flamer_num_total_hits(nr, mx)
    assert isinstance(node, Sum)
    base = node.a if hasattr(node, "a") else node.terms[0]
    assert isinstance(base, Const) and base.value == nr
    extra = heavy_warp_flamer_num_extra_hits(nr, mx)
    assert isinstance(extra, Min)
    assert isinstance(extra.a, GetPersistentData)
    assert extra.a.ability_or_effect == HWF, (
        "la cle porte l'`AbilityOrEffect` de l'ACTIVE (0x4cb = 1227), pas l'id de la triggered 1546 "
        "-- c'est le litteral LU a l'assembleur dans `HeavyWarpFlamer_AttackTrackingAbility$$"
        "CreateBehaviour`, et c'est ce qui rend le mecanisme coherent")
    assert isinstance(extra.a.unit, Owner)
    assert extra.a.data_key == HEAVY_WARP_FLAMER_STACK_KEY == "PSYCHIC_ATTACKS_KEY"
    assert isinstance(extra.b, Difference)
    assert isinstance(extra.b.a, Const) and extra.b.a.value == mx
    assert isinstance(extra.b.b, Const) and extra.b.b.value == nr


def test_1227_num_total_hits_dans_ses_trois_regimes():
    """La VALEUR, dans les trois regimes que le noeud doit distinguer. Le regime `compteur absent`
    est celui d'aujourd'hui (la triggered 1546 n'est pas portee) ; les deux autres figent le
    comportement que le port aura SANS modification le jour ou elle le sera."""
    nr, mx, _rng = _config()
    node = heavy_warp_flamer_num_total_hits(nr, mx)
    owner = {"id": 1, "team": 1}
    base = dict(units=[], caster=owner, target={"id": 2, "team": 2}, owner=owner)

    # (a) cle ABSENTE -> `TryGetPersistData` laisse son `out` au defaut = 0.
    assert node.evaluate(DslContext(**base)) == nr

    # (b) compteur sous le plafond.
    def _pd(_u, key):
        return 3 if key == (HWF, HEAVY_WARP_FLAMER_STACK_KEY) else None
    assert node.evaluate(DslContext(persistent_data=_pd, **base)) == nr + 3

    # (c) compteur AU-DELA du plafond -> `Min` rabat sur `maxNrOfHits - nrOfHits`.
    assert node.evaluate(DslContext(persistent_data=lambda _u, _k: 1000, **base)) == mx


def test_1227_l_execution_refuse_une_cible_absente():
    """`ExecuteBehaviour` natif exige une cible (le `Target@+0x60` du `ChainLeftOverHits`) : sans
    elle le port rend `None`, jamais un cast a vide."""
    assert HeavyWarpFlamerAbility().execute_behaviour(None, 1, None) is None
