"""#547-r12 -- un CADAVRE-AU-CHARGEMENT porteur d'une `fire_on_death` entre au registre.

Le natif SEPARE ce que le port confondait : `IdunBattleLogic.Core.Services.Caches.
AbilityAndEffectCache$$AddEntity` garde TOUTE entite (aucun gate de vivacite -- relu verbatim sur
`t6dpr4k06g`), et c'est `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` qui
trie A LA LECTURE, sous l'exemption `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` (mirror
`fire_on_death`). Le port coupait AVANT le gate (`if sc is None: continue`), donc une entite
chargee morte -- presente dans `decisionView.units[]`, absente de `combatSnapshot.units[]`, donc
sans `StatsComponent` -- n'avait AUCUNE triggered-ability inscrite, exemptee comprise.

Les cinq etages vivent dans `probe_547r12_cadavre_au_registre.py` ; ce fichier les JOUE et les
FIGE. Chacun porte sa propre contre-epreuve (morsure ou temoin non vide) : un etage qui ne mord
d'aucun cote serait vert par vacuite.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_547r12_cadavre_au_registre as P                              # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE       # noqa: E402

DECLENCHEUR = {
    "chemins": (
        'scripts/python/probe_547r12_cadavre_au_registre.py',
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Ce fichier ne fait qu'APPELER les etages du probe : toute son assertion vit la-bas, "
        "donc une edition du probe change ce que ce test mesure sans toucher a ce fichier. "
        "Le reste de ce qui l'influence est DERIVE par la cascade d'imports (le foyer "
        "`engine/runner/operations/triggers/dispatch/core.py`, les six tables de registration, "
        "les classes de trigger, `gameconfig`), donc a ne PAS declarer (#531). Rien d'autre : "
        "aucune lecture de `data/**` ni du binaire -- le probe monte ses `State` en memoire et "
        "ne lit du gameconfig que par l'import, deja dans la cascade. `build: False` pour la "
        "meme raison : aucune entree `data/symbols/**` n'est ouverte ici (les VAs et les valeurs "
        "de slot sont CITEES en prose, pas relues)."
    ),
}


def test_547r12_le_cadavre_au_chargement_entre_au_registre():
    """ETAGE 1 -- et la MORSURE : neutraliser `_triggers_du_cadavre_au_chargement` le fait
    ressortir. Sans cette seconde moitie, l'etage passerait au vert sur un arbre ou le correctif
    n'existe pas (la Geminae y serait inscrite par une autre voie)."""
    assert P.step_inscription() == 0


def test_547r12_le_pending_de_celestine_est_consomme_seulement_dans_LA_cellule():
    """ETAGE 2 -- les QUATRE cellules (correctif x 1240) sont figees, pas seulement la verte.
    Celestine n'est epargnee que sous `(correctif, 1240)` : c'est la mecanique du 2e conjoint
    natif `IsAlive(Owner) | HasEffect(Owner, 0x4d8 = 1240, onlyActive: 0, 6)`, et c'est le
    correctif qui la rend atteignable."""
    assert P.step_observable() == 0


def test_547r12_aucun_AUTRE_porteur_fire_on_death_ne_tire_ni_ne_leve():
    """ETAGE 3, L'ADVERSARIAL -- le point ou cette tranche pouvait casser autre chose EN SILENCE.

    Les 23 autres porteurs `fire_on_death` etaient ranges << regime divergent VIDE >> par une
    LECTURE DE CODE (#547-r11) que rien n'exercait. Le correctif les inscrit pour de vrai : leur
    `matches` est donc EXERCE sur un cadavre-au-chargement, dans CINQ regimes. Les deux
    ATTEIGNABLES (le cadavre n'est ni acteur, ni cible, ni mourant) sont BLOQUANTS ; les trois
    autres sont un INVENTAIRE, avec la raison de leur inatteignabilite ecrite dans le probe.

    Deux crans de non-vacuite, tous deux dans le probe : `LifewardsAbility` DOIT tirer dans le
    regime enrichi (temoin), et NE DOIT PAS tirer dans le regime minimal (discrimination). Et
    AUCUN porteur ne doit LEVER -- une exception remonterait `evaluate_trigger_operation` et
    casserait le dispatch, ce qui est le vrai risque du correctif."""
    assert P.step_ventilation() == 0


def test_547r12_un_etat_sans_cadavre_est_bit_a_bit_inchange():
    """ETAGE 4 -- value-preserving. Le correctif ne vit que dans la branche `sc is None` ; un mort
    DU RUN garde son `StatsComponent` et passait deja par la branche ordinaire."""
    assert P.step_preservation() == 0


def test_547r12_l_amplitude_est_bornee_par_le_SEEDING_et_le_dit():
    """ETAGE 5 -- ce que le correctif NE ferme PAS, fige plutot que tu.

    Mesure LIVE (build `t6dpr4k06g`, runners 638 et 669) : un cadavre est bien conserve dans
    `decisionView.units[]`, mais il n'y porte AUCUN effet, y compris sous `includeInactive: true`.
    Les DEUX membres de la disjonction de `LifewardsAbility` sont donc faux sur un
    cadavre-au-chargement issu d'une capture -- l'ecart residuel est un ecart de SEEDING (residu
    #547-r13), pas de dispatch."""
    assert P.step_amplitude() == 0


def test_547r12_le_foyer_est_bien_le_seul_chemin_du_cadavre():
    """GARDE DE STRUCTURE -- le correctif doit rester un FOYER UNIQUE et GATE.

    Trois faits qu'un refactor pourrait perdre en silence : (a) la fonction est le seul appelant
    de la branche `sc is None` ; (b) elle REFUSE une entite non-unite (mirror d'
    `IdunBattle.Entities.EntityExtensions$$IsUnit`, que `CanGetAbilityTrigger` place devant ses
    deux gates) ; (c) elle REFUSE une unite VIVANTE sans `StatsComponent` -- l'inscrire
    demanderait TOUT son kit et non les seules exemptees, ce qui est un elargissement d'un autre
    ordre, nomme au residu."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent
    import gameconfig as GC
    from engine.runner.operations.behaviour import BEHAVIOUR_TRAIT_TRIGGERS

    st = P.etat_geminae()
    e = st.get_entity(P.GEMINAE)
    assert CORE._triggers_du_cadavre_au_chargement(e, P.GEMINAE, GC, BEHAVIOUR_TRAIT_TRIGGERS), (
        "le cadavre-Geminae doit rendre au moins une entree")

    # (b) entite SANS `UnitComponent` -> aucune inscription
    from engine.runner.state import Entity
    nu = Entity(999)
    assert CORE._triggers_du_cadavre_au_chargement(nu, 999, GC, BEHAVIOUR_TRAIT_TRIGGERS) == []

    # (c) unite VIVANTE sans stats -> aucune inscription
    vivant = Entity(998)
    vivant.add_component(UnitComponent(visual_id="adeptSmnGeminaeSuperia", alive=True))
    assert CORE._triggers_du_cadavre_au_chargement(vivant, 998, GC, BEHAVIOUR_TRAIT_TRIGGERS) == []

    # (a) et le gate est bien celui du dispatch : `State` vide -> rien, sans lever
    assert CORE.collect_triggered_abilities(State()) == []
