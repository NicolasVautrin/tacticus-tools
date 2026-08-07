"""GARDE #489 (OFFLINE PURE) -- `1048 FragstormGrenadeLauncher` (`templAggressor` « Brother
Burchard », Black Templars), face EXECUTION.

CE QU'ELLE PROTEGE. Avant ce port, 1048 etait absente d'`ABILITY_CLASSES` : le cast tombait sur le
no-op SILENCIEUX d'`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet,
AUCUNE erreur). Ce fichier fige les quatre choses qui peuvent regresser sans qu'aucun autre test ne
rougisse :

  1. **LE REGISTRE** -- l'entree dans `ABILITY_CLASSES`. Sa disparition rendrait l'ability muette,
     pas rouge.
  2. **LES DEUX LITTERAUX DU REGISTRE** (`TARGETING_OPTIONS`, `ABILITY_ATTACK_TYPE`). Le masque
     vient de la forme **PRESET + FLAGS** (`preset` statics `+0x180` | `0x2000000`), donc le litteral
     visible au `$$.ctor` n'est PAS le masque effectif : c'est exactement le genre de valeur qu'une
     regeneration « propre » remettrait de travers. Un `TARGETING_OPTIONS` absent ne casse rien --
     il rend `get_invalid_target_reason` PERMISSIF, en silence.
  3. **LA FORME DE L'ARBRE** -- `ChainLeftOverHitsAttackDamage` avec `extraHits = 0`. Copier le
     patron du voisin `1006 MultiThreatEliminator` (qui, lui, porte `GetNumberConstant(0x2b)`)
     donnerait un coup bonus par ennemi tue que le natif n'accorde PAS ici.
  4. **LE NOEUD DE LA FORMULE DE TRI** -- `ActiveTarget()`, jamais `Subject()`. C'est le cran qui a
     MORDU en live (#489) : le natif passe `DSLSelectors+0x68` = `ActiveTarget`, que `SortByFormula`
     ne re-lie PAS par element -> la formule est CONSTANTE et le tri par PV est un NO-OP, l'ordre
     SOURCE survivant jusqu'au selecteur de prediction. Avec `Subject()` le tri devenait ACTIF et le
     report partait sur la MAUVAISE cible (mesure : port `u81`, natif `u107` ; apres correctif,
     chaine `[u79, u107]` des deux cotes).

Mesure live de bout en bout (`ported`, chaine, degats par coup, report) :
`python scripts/python/probe_489_fragstorm_grenade_launcher.py`.
RE : `docs/rl/case-489-fragstorm-grenade-launcher.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture (aucun test ne les IMPORTE -- c'est de la semantique pytest).
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # ... y compris les DEUX conftest intermediaires du chemin de ce fichier, qui portent
        # les fixtures de montage dont chaque test depend.
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        # PROPRE A CE FICHIER. Perimetre pris LARGE, et non feuille a feuille : la FERMETURE
        # D'IMPORTS mesuree par le cliquet compte ~139 modules (charger une ability tire le
        # registre, le vocabulaire DSL, les Operations, l'IA et le pathfinding ; et la cascade
        # des `conftest.py` tire une vingtaine de probes de la RACINE). La liste choisie qui
        # vivait ici rendait ce cliquet ROUGE -- reparé par #490, meme correctif que celui
        # applique a `test_490_psychic_maelstrom_live.py`. Les foyers VRAIMENT load-bearing,
        # pour la relecture humaine : `abilities/blacktemplars.py` (le port),
        # `operations/damage_prediction_sort.py` (le selecteur de chaine), `handler.py` +
        # `attack_type.py` + `targeting.py` (les registres), `behaviours/combat.py` (la feuille
        # partagee de chainage), `entities/formulas.py` + `entities/selectors/**` (les noeuds
        # DSL dont la forme est ASSERTEE ici).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        "scripts/python/engine/entities/stats.py",
        # Les magnitudes/constantes de 1048 viennent du gameconfig du BUILD.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'entree au registre `ABILITY_CLASSES`, les deux litteraux du "
              "registre (masque 0x2004002 issu du preset statics+0x180 | 0x2000000, et "
              "AbilityAttackType 0), la forme de l'arbre (`extraHits` NUL) et le noeud de la "
              "formule de tri (`ActiveTarget`, jamais `Subject`). Aucun runner, aucune session "
              "Frida : le seul acces disque est le depot (gameconfig du build pour les "
              "magnitudes).",
}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.formulas import StatAmount                            # noqa: E402
from engine.entities.selectors.accessors import ActiveTarget, Owner, Target  # noqa: E402
from engine.entities.selectors.units import (Damageable, SortByFormula,    # noqa: E402
                                             Sub, SurroundingEnemies)
from engine.entities.stats import StatType                                 # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE        # noqa: E402
from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage  # noqa: E402
from engine.runner.abilities.blacktemplars import (                        # noqa: E402
    FragstormGrenadeLauncherAbility, fragstorm_grenade_launcher_other_targets,
    fragstorm_grenade_launcher_tree)
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG,          # noqa: E402
                                               RANGED_BOOL_FALSE)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.operations.damage_prediction_sort import (              # noqa: E402
    KEY_MIGHT_BE_KILL, KEY_WILL_BE_KILL, SortTargetsByDamagePrediction)

FRAG = int(ActiveAbilityType.FragstormGrenadeLauncher)      # 1048


def test_1048_est_au_registre_des_abilities_portees():
    """(1) Sans cette entree, `visit_ActiveAbilityMessage` pose `ported: False` et RETOURNE."""
    assert FRAG == 1048
    assert FRAG in ABILITY_CLASSES
    assert ABILITY_CLASSES[FRAG] is FragstormGrenadeLauncherAbility


def test_1048_masque_de_ciblage_et_attack_type():
    """(2) `preset statics+0x180` (rules `0x4002`, `RANGE_FROM_CONFIG`, `forceMeleeTarget = 1`)
    combine par la surcharge PRESET+FLAGS avec `0x2000000` -> `rules = 0x2004002`. Valeur
    CONCORDANTE avec la mesure independante de `docs/rl/case-302-4/tile-target-population.tsv`."""
    opts = FragstormGrenadeLauncherAbility.TARGETING_OPTIONS
    assert opts is not None, "TARGETING_OPTIONS absent -> gate PERMISSIF silencieux"
    assert int(opts.rules) == 0x2004002
    # decomposition exhaustive : aucun bit residuel
    bits = (TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation)
    assert int(opts.rules) == int(bits)
    assert opts.range == RANGE_FROM_CONFIG
    # ⚠ le preset VOISIN `+0x140` (Stikkbomb/PlasmaGrenade) a le MEME `rules` et l'AUTRE
    # `forceMeleeTarget` : c'est le seul champ qui les separe.
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert ABILITY_ATTACK_TYPE.get(FRAG) == 0        # AbilityAttackType.DirectTargetAttack


def test_1048_forme_de_l_arbre_et_extra_hits_nul():
    """(3) UN seul noeud terminal, `extraHits` NUL, caster `Owner` et cible initiale `Target`."""
    tree = fragstorm_grenade_launcher_tree(None, 2, 1746, 2183, 6, 15)
    assert isinstance(tree, ChainLeftOverHitsAttackDamage)
    assert isinstance(tree.caster_sel, Owner)
    assert isinstance(tree.target_sel, Target)
    assert tree.ability_id == "FragstormGrenadeLauncher"
    assert tree.profile == "Blast"
    assert tree.hits == 6
    # `extraHitsAfterTargetKilled` = **null** au call-site natif (MTE, lui, passe
    # `Get(GetNumberConstant(0x2b))`) -> AUCUN coup bonus par ennemi tue.
    assert tree.extra_hits == 0
    assert tree.is_melee is False
    assert tree.native_factory == "attack"           # famille ATTACK (2 tirages/coup a cc=0)


def test_1048_selecteur_de_chaine_trie_par_prediction_sur_ActiveTarget():
    """(4) LE cran qui a mordu : la formule de tri lit `ActiveTarget` (`DSLSelectors+0x68`), PAS
    `Subject`. Avec `Subject`, `SortByFormula` re-lie l'element -> le tri par PV devient ACTIF et le
    report change de cible (mesure live #489)."""
    tree = fragstorm_grenade_launcher_tree(None, 2, 1746, 2183, 6, 15)
    chain = tree.next_target_sel
    assert isinstance(chain, SortTargetsByDamagePrediction)
    assert isinstance(chain.attacker, Owner)
    assert chain.hits == 6 and chain.damage_min == 1746 and chain.damage_max == 2183
    assert chain.damage_profile == "Blast" and chain.pierce == 15
    assert chain.ability_type == FRAG

    src = chain.targets
    assert isinstance(src, SortByFormula)
    assert src.ascending is True                     # flag natif `1` -> `OrderBy` (ascendant)
    assert isinstance(src.formula, StatAmount)
    assert int(src.formula.stat_type) == int(StatType.HEALTH)
    assert isinstance(src.formula.selector, ActiveTarget), \
        "la formule de tri doit lire ActiveTarget (DSLSelectors+0x68), jamais Subject"


def test_1048_other_targets_est_le_mirror_de_GetOtherTargets():
    """`Damageable( SurroundingEnemies(Owner, range, reference=Owner) - Target )` -- la surcharge
    NATIVE a 4 arguments fait servir le MEME selecteur de centre ET de reference d'equipe."""
    sel = fragstorm_grenade_launcher_other_targets(2)
    assert isinstance(sel, Damageable)
    diff = sel.inner
    assert isinstance(diff, Sub)
    assert isinstance(diff.b, Target)
    surr = diff.a
    assert isinstance(surr, SurroundingEnemies)
    assert isinstance(surr.center, Owner)
    assert isinstance(surr.reference, Owner), "surcharge 4-args : centre ET reference = le meme noeud"
    assert surr.radius.evaluate(None) == 2


def test_1048_rangs_du_selecteur_et_moyenne_entiere():
    """Les deux rangs sont les LITTERAUX de `<Select>b__0` (`int.MaxValue` / `int.MaxValue - 1`), et
    `AAmountFormula$$CalculateAverage` est une division ENTIERE."""
    assert KEY_WILL_BE_KILL == 0x7FFFFFFF
    assert KEY_MIGHT_BE_KILL == 0x7FFFFFFE
    node = SortTargetsByDamagePrediction(None, Owner(), Owner(), FRAG, 1746, 2183, 6, "Blast", 15)
    assert node._damage_average() == (1746 + 2183) // 2 == 1964
    # `state = None` (hors runner) : aucune prediction evaluable -> la source est rendue TELLE QUELLE,
    # jamais une liste vide (une liste vide couperait la chaine en silence).
    assert node.select is not None
