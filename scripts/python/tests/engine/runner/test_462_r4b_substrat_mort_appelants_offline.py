"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1 (+ -r2) -- GARDE de CE QUE LE PORT SAIT D'UNE UNITE MORTE.

TROIS choses sont verrouillees ici, et elles ne se gardent pas au meme endroit.

  1. L'ENUMERATION ne derive pas. Le residu `-r1` laissait DEUX sites `INDECIDABLE`
     (`UnitEffectStateView.__init__`, `Scene.unit_state`) parce que leurs appelants n'avaient pas
     ete enumeres. Ils le sont : 19 cles, ventilees. Un appelant NEUF rend la ventilation MUETTE
     sur lui -- d'ou un cliquet d'exhaustivite, pas un seuil.

  2. LA DEGRADATION EST EXERCEE, pas affirmee. `-r1` dit << cle `traits` absente ⇒ une condition de
     TRAIT rend VRAI >>. C'est un CONTREFACTUEL, et il se joue : meme cadavre, meme `Pinned`, on
     change UNIQUEMENT la presence du substrat de traits et on compare `active_effects`. Sans ca,
     la phrase n'est qu'une prose que rien ne contredit si elle devient fausse.
     ⚠ ET LE CONTREFACTUEL DOIT ASSERTIONNER SA PROPRE NON-DEGENERESCENCE : si les deux bras
     rendaient la meme chose, le test passerait au VERT en ne mesurant plus rien.

  3. LE REGISTRE (`-r2`). La question << `AbilityAndEffectCache` retire-t-il l'entite a la mort ? >>
     se tranche un cran plus bas : `IdunBattle.Operations.EvaluateTriggerOperation$$
     CanGetAbilityTrigger` teste `IsAlive(owner)` A LA LECTURE, sous une exemption
     `ability.get_AllowForDeadOwner()` (`ITriggeredAbility` slot 8 -- ce n'est PAS un `IsAtomic`,
    cf. `probe_10015_allow_for_dead_owner.py`). Si le cache retirait les morts, ce gate ET son exemption seraient
     inatteignables -- la branche atomique n'existe QUE pour laisser passer un owner MORT. Donc le
     `if sc is None: continue` du port et le natif concordent pour toute ability NON atomique, et
     ne peuvent diverger que sur les `fire_on_death`. Le cliquet garde ce raisonnement : tout
     porteur `fire_on_death` NEUF doit etre trie.

OFFLINE, et c'est un choix : tout est predicat pur ou lecture de source. Le montage vit dans le
probe (aucun fork : ce fichier l'IMPORTE).

ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LA CASCADE DES CONFTEST est DERIVEE par le foyer depuis #531 -- ne pas la recopier ici.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER, nomme. Ce fichier n'exerce QUE le substrat `unit_state` (ses deux faces), les
        # six balayages d'entites qui le consomment, et le registre des triggered-abilities.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/additional_hits.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/entities/effects/loki/status.py",
        "scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_r1_appelants.py",
        # L'etage 5 IMPORTE le montage de crush de la tranche precedente (aucun fork de montage) :
        # ce chemin est donc une ENTREE de ce fichier, pas un voisin.
        "scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py",
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/operations/triggers/genestealer.py",
        # AJOUTES SUR `master` (2026-08-08) : le cliquet rougissait ICI et pas dans le worktree
        # d'origine, parce que la CONFRONTATION N'AVAIT PAS LE MEME NOMBRE DE SOURCES. Tant que ce
        # fichier n'a pas d'entree d'empreinte, seule la fermeture d'IMPORTS est verifiee ; des que
        # `--measure-missing` en grave une, les TEMOINS de ce que le fichier a reellement OUVERT
        # s'ajoutent -- et ils sont plus larges. Rejouer le cliquet AVANT de graver l'empreinte ne
        # peut donc pas voir ce rouge : ce n'est pas une negligence de l'auteur, c'est un ORDRE.
        #
        # Les six `__init__.py` sont la CASCADE DE PAQUET que l'import de chaque feuille traine
        # (`engine.entities`, `engine.streams`, ...) ; les deux modules nommes sont ouverts par
        # cette meme cascade, pas par une ligne `import` de ce fichier. Ils sont declares
        # LITTERALEMENT plutot que par un glob `engine/**` : ce fichier ne veut PAS etre
        # reselectionne a chaque edition d'une feuille d'`engine/` qu'il n'exerce pas.
        "scripts/python/engine/entities/__init__.py",
        "scripts/python/engine/entities/abilities/__init__.py",
        "scripts/python/engine/entities/effects/loki/__init__.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        "scripts/python/engine/runner/caches/__init__.py",
        "scripts/python/engine/runner/caches/ability_and_effect_cache.py",
        "scripts/python/engine/streams/__init__.py",
        "scripts/python/engine/streams/verify_turn_finished.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE d'un SUBSTRAT (le `unit_state` passe a `EffectsState.active_effects`) "
              "et d'un REGISTRE (les triggered-abilities d'un cadavre). Aucun RPC, aucun runner : "
              "tout est predicat pur ou lecture de source. La mesure vit dans "
              "`probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_r1_appelants.py`. Les huit derniers "
              "chemins ne sont pas des foyers SOUS TEST : c'est la cascade de paquet que le "
              "chargement des feuilles ci-dessus traine, et elle est nommee parce que l'empreinte "
              "la MESURE -- pas parce que ce fichier en depend logiquement.",
}

import pytest                                                                   # noqa: E402

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_r1_appelants as P                # noqa: E402
# Le montage du CRUSH vit dans le probe de la tranche precedente -- aucun fork : on l'IMPORTE.
import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits as P_CRUSH       # noqa: E402


# ================================================================================================
# ETAGE 1 -- l'ENUMERATION ne derive pas sous la table
# ================================================================================================
def test_la_table_ventile_exactement_l_inventaire():
    """CLIQUET d'EXHAUSTIVITE. Un appelant NEUF du substrat rend la ventilation de cette tranche
    MUETTE sur lui : elle ne dit rien de son sujet, donc rien de son risque. On exige la
    coincidence exacte -- pas un seuil (une garde en seuil cesse de mordre des qu'un contributeur
    ne remonte pas le seuil).

    C'est ce cliquet qui remplace le verdict `INDECIDABLE` des deux sites du residu : ils ne sont
    plus indecidables parce que leurs appelants sont ENUMERES, et le jour ou un nouveau apparait,
    c'est ce test qui le dit."""
    trouves = {P.cle(s) for s in P.sites()}
    table = set(P.VENTILATION)
    manquantes = sorted(trouves - table)
    orphelines = sorted(table - trouves)
    assert not manquantes, (
        "%d appelant(s) du substrat `unit_state` que la table ne ventile PAS : %r. Ventiler le site "
        "(son sujet peut-il etre une entite chargee MORTE ?) fait partie du changement qui l'a "
        "cree." % (len(manquantes), manquantes))
    assert not orphelines, (
        "%d entree(s) de table sans site : %r. L'appelant a ete deplace ou supprime ; mettre la "
        "table a jour, sans quoi elle decrit un etat perime." % (len(orphelines), orphelines))


def test_aucun_verdict_ATTEIGNABLE_ne_reste_sans_gate():
    """Un `ATTEIGNABLE` de la table est une DETTE OUVERTE tant qu'aucun gate ne le ferme. Le seul
    qu'elle porte (`defender_fixed_armor`) a recu le sien ; l'etage 2 le verifie au source."""
    restants = sorted(c for c, (v, _m) in P.VENTILATION.items() if v in P.VERDICTS_A_TRAITER)
    couverts = set(P.BALAYAGES)
    orphelins = [c for c in restants if (c[0], c[1]) not in couverts]
    assert not orphelins, (
        "%d site(s) ATTEIGNABLE(s) hors du registre des balayages gardes : %r. Un ATTEIGNABLE non "
        "garde est un cadavre qui traverse le port en silence." % (len(orphelins), orphelins))


# ================================================================================================
# ETAGE 2 -- les SIX balayages portent tous leur gate de vivacite
# ================================================================================================
@pytest.mark.parametrize("cle", sorted(P.BALAYAGES))
def test_chaque_balayage_porte_son_gate_de_vivacite(cle):
    """PROVENANCE, par AST. Un balayage de `state.entities` qui appelle `active_effects` sur chaque
    entite visitee DOIT ecarter les morts : le board natif est une OCCUPATION DE TUILE
    (`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` = `Units(AdjacentTiles(.)) - .`), un mort
    n'y est plus.

    ⚠ POURQUOI UN CRITERE DE SOURCE ET PAS DE VALEUR : `defender_fixed_armor` etait SANS gate et
    restait pourtant inerte, par une PROPRIETE DU CAPTEUR --
    `IdunBattle.Operations.KillUnitOperation$$Execute` appelle trois fois `RemoveEffects(killed,
    <step>)`, donc `decisionView.units[].effects` est vide pour un mort et le `if not effs:
    continue` qui suit l'ecartait. Aucun critere de VALEUR ne pouvait donc voir le trou ; seul un
    etat construit HORS capture (greffe, seed synthetique) le revele."""
    etat = {c: (a, h) for c, a, h, _m in P.etat_gates()}
    lit_alive, compare_hp = etat[cle]
    assert lit_alive or compare_hp, (
        "`%s::%s` ne teste NI `alive` NI `hp` : son balayage visite les cadavres-au-chargement "
        "(`decisionView.units[]` les conserve, et `snapshot._load_stats_and_effects` seede leurs "
        "effets dans `EffectsState`). Ses cinq freres portent tous ce gate depuis `#57m`." % cle)


# ================================================================================================
# ETAGE 3 -- la DEGRADATION PERMISSIVE, exercee
# ================================================================================================
def test_la_cle_traits_absente_rend_un_effet_de_trop():
    """CONTREFACTUEL. Meme cadavre, meme `Pinned` porte, meme tout : SEULE change la presence du
    substrat de traits. Si les deux bras rendaient la meme chose, ce test serait un VERT qui ment
    -- d'ou l'assertion de NON-DEGENERESCENCE en tete.

    Le sens du verdict n'est pas decoratif : la degradation est PERMISSIVE (un effet de trop),
    jamais restrictive. C'est ce qui la rend invisible en self-play et exploitable par un
    entrainement."""
    from engine.runner.components import unit_state_for_effects
    sorties = {}
    cles = {}
    for mesures in (False, True):
        st = P.etat_cadavre(mesures)
        us = unit_state_for_effects(st, 7)
        cles[mesures] = "traits" in us
        sorties[mesures] = sorted(getattr(x, "name", None)
                                  for x in st.effects.active_effects(7, us))
    assert cles == {False: False, True: True}, (
        "le montage ne produit plus les deux etats du substrat : cle `traits` %r. Sans cette "
        "difference, le contrefactuel ne mesure RIEN." % (cles,))
    assert sorties[False] != sorties[True], (
        "REGIME DEGENERE : les deux bras rendent %r. Le contrefactuel ne discrimine plus la "
        "presence de la cle `traits` -- le reparer, pas s'en satisfaire." % (sorties[False],))
    assert sorties[False] == ["Pinned"] and sorties[True] == [], (
        "la degradation a change de SENS. Attendu : `Pinned` ACTIF sans le substrat (permissif, un "
        "effet de trop) et INACTIF avec (le natif immunise un porteur `TerminatorArmour` -- "
        "`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f))`). Vu : sans=%r "
        "avec=%r" % (sorties[False], sorties[True]))


def test_le_rayon_de_souffle_de_la_cle_traits_est_mesure_et_non_vide():
    """Le nombre de consommateurs de la cle `traits` BORNE le risque de tous les appelants a la
    fois : un site ATTEIGNABLE dont le consommateur aval ne lit pas cette cle ne porte aucun ecart
    par ce canal.

    ⚠ ASSERTION DE NON-VIDE. Un recenseur qui rend zero se lit comme << rien a signaler >> alors
    qu'il peut n'avoir rien visite (le vice mesure en #270-r1-r1-r3). Ici, zero consommateur
    voudrait dire que la degradation du residu n'existe pas -- ce que l'etage 3 refute."""
    cons = P.consommateurs_cle_traits()
    assert cons, (
        "AUCUN consommateur de la cle `traits` trouve. Soit le recenseur ne visite plus les "
        "`is_active`, soit `PinnedEffect` a change de forme -- dans les deux cas la ventilation "
        "ci-dessus repose sur une borne qui n'est plus mesuree.")
    fichiers = sorted({c[0] for c in cons})
    assert "entities/effects/loki/status.py" in fichiers, (
        "`PinnedEffect.is_active` n'est plus le consommateur de la cle `traits` (vu : %r). C'est "
        "LUI qui donne son rayon a la degradation ; s'il a bouge, la re-mesurer." % (fichiers,))


# ================================================================================================
# ETAGE 4 -- le REGISTRE (-r2) : tout porteur `fire_on_death` est TRIE
# ================================================================================================
def test_tout_porteur_fire_on_death_est_trie():
    """CLIQUET du residu `-r2`. Le port retire un cadavre-au-chargement du registre
    (`collect_triggered_abilities` : `if sc is None: continue`). Le natif, lui, le CONSERVE dans
    `AbilityAndEffectCache` et le trie a la LECTURE
    (`EvaluateTriggerOperation$$CanGetAbilityTrigger`, `IsAlive(owner)` sauf
    `get_AllowForDeadOwner`). Les deux
    concordent donc pour toute ability NON atomique, et ne peuvent diverger que sur les
    `fire_on_death` -- et seulement si l'evenement ecoute peut encore se produire APRES la mort du
    porteur.

    Ce test exige que CHAQUE porteur `fire_on_death` tombe dans l'une des trois cases instruites.
    Un porteur NEUF qui ecoute autre chose que sa propre mort rougit ici, et c'est exactement le
    moment ou la question doit etre re-posee."""
    lst = P.porteurs_fire_on_death()
    assert lst, "aucun porteur `fire_on_death` trouve : le recenseur ne visite plus rien."
    non_tries = []
    for rel, nom, evid, evids, face in lst:
        ev = evid or evids or ""
        if face == "EFFET":
            continue                          # `_owner_gate_applies` est FAUX : aucun gate d'owner
        if any(k in ev for k in P._EVENTS_DE_SA_PROPRE_MORT):
            continue                          # l'evenement a deja eu lieu avant la capture
        if nom in P.REGISTRE_HORS_MORT:
            continue                          # instruit, avec sa consequence mesuree
        non_tries.append((rel, nom, ev))
    assert not non_tries, (
        "%d porteur(s) `fire_on_death` dont l'evenement n'EST PAS leur propre mort et qui ne sont "
        "pas instruits : %r. Un tel porteur DIVERGE du natif sur un cadavre-au-chargement (le port "
        "ne l'inscrit meme pas au registre). Le trier -- ou nommer sa consequence dans "
        "`REGISTRE_HORS_MORT`." % (len(non_tries), non_tries))


# ================================================================================================
# ETAGE 5 -- l'ECRIVAIN et le RESET de `killed_this_turn`, exerces sur le CHEMIN REEL
# ================================================================================================
# ⚠ CET ETAGE EXISTE PARCE QUE LA MATRICE DE MUTANTS L'A EXIGE. Deux mutations ne mordaient PAS :
# retirer `killed_this_turn = True` du foyer de mort, et retirer son reset au turn-start. Cause :
# tous les bras precedents partent d'un etat SYNTHETIQUE qui pose le champ A LA MAIN -- ils gardent
# le LECTEUR (`_valid_dead_decoys`) et rien d'autre. Un champ qu'aucun test n'ecrit par le vrai
# chemin est un champ que personne ne garde.
def test_le_foyer_de_mort_pose_killed_this_turn(monkeypatch):
    """`IdunBattle.Operations.KillUnitOperation$$Execute+0x828` : `unitComponent+0x17a = 1`, dans la
    branche NON-REVIVE. Exerce par le CRUSH (`_kill_steppable_units`), qui traverse le foyer
    partage `damage.py::_kill_unit_operation`.

    Le bras de CONTROLE est l'entree du vecteur : avant le crush, le steppable est VIVANT et son
    drapeau vaut `None` (non mesure). Sans lui, un `True` pose au chargement passerait pour une
    mesure du run."""
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.dispatch import move_death as TRG
    from engine.runner.operations.movement import _kill_steppable_units
    monkeypatch.setattr(TRG, "post_unit_kill_triggers", lambda *a, **k: [])
    st = P_CRUSH.etat_crush("genesSmnDecoy", avec_stats=True, vivant=True)
    uc = st.get_entity(2).get_component(UnitComponent)
    assert uc.killed_this_turn is None, (
        "CONTROLE : avant tout crush, le steppable VIVANT doit porter `None` (non mesure), pas %r."
        % (uc.killed_this_turn,))
    tues = _kill_steppable_units(st, (3, 3), mover_id=1)
    assert tues == [2], "le montage ne crushe plus (tues=%r) : le bras ne mesure rien." % (tues,)
    assert uc.killed_this_turn is True, (
        "apres le crush, `UnitComponent.killed_this_turn` vaut %r au lieu de True. Le foyer "
        "`damage.py::_kill_unit_operation` ne pose plus le drapeau `+0x17a` -- le conjoint natif "
        "`IsKilledThisTurn` n'a plus de substrat, et `_valid_dead_decoys` refusera TOUT decoy."
        % (uc.killed_this_turn,))


def test_le_turn_start_efface_le_drapeau_des_VIVANTS_et_seulement_d_eux():
    """`IdunBattle.Operations.StartTurnOperation$$ResetUnit` : `*(undefined2*)(uc + 0x179) = 0`.

    LES DEUX MOITIES COMPTENT, et la seconde est le coeur de la semantique. `ResetUnit` est appele
    sur `PlayerComponent.CurrentlyOwnedUnitIds`, dont `PlayerComponent$$get_CurrentlyOwnedUnitIds`
    retire les defaits : le drapeau d'un MORT n'est donc JAMAIS efface. `IsKilledThisTurn` ne veut
    pas dire << tuee pendant le tour courant >> mais << tuee, et n'a pas redemarre de tour depuis >>
    -- et c'est cette moitie-la qui rend le predicat utile a `GetValidDeadDecoys`, dont le sujet
    est justement un MORT.

    Un test qui n'aurait que le bras VIVANT laisserait passer un reset GLOBAL, qui viderait le
    drapeau de tous les cadavres a chaque tour et desarmerait le conjoint en silence."""
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent)
    from engine.runner.state import State, Entity
    from engine.runner.operations import turnflow

    st = State()
    for uid, vivant in ((1, True), (2, False)):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id="orksNob", alive=vivant))
        e.add_component(OwnerComponent(team=1, player=11))
        e.add_component(PositionComponent(col=uid, row=1))
        e.add_component(HealthComponent(hp=100 if vivant else 0, hp_max=100))
        e.get_component(UnitComponent).killed_this_turn = True     # revive / cadavre du run
        st.entities[uid] = e
    turnflow.StartTurnOperation.execute(st, 11)
    vivant = st.get_entity(1).get_component(UnitComponent).killed_this_turn
    mort = st.get_entity(2).get_component(UnitComponent).killed_this_turn
    assert vivant is False, (
        "l'unite VIVANTE du joueur entrant garde `killed_this_turn=%r` : le reset de "
        "`StartTurnOperation$$ResetUnit` n'est plus pose. Un porteur revive resterait << tue >> "
        "indefiniment." % (vivant,))
    assert mort is True, (
        "l'unite MORTE a vu son drapeau efface (`killed_this_turn=%r`). `ResetUnit` ne visite que "
        "`CurrentlyOwnedUnitIds`, d'ou les defaits sont retires : un reset global desarmerait le "
        "conjoint `IsKilledThisTurn` de `GetValidDeadDecoys`, dont le sujet EST un mort." % (mort,))


def test_la_face_des_porteurs_est_resolue_par_la_MRO_pas_par_le_nom_de_base():
    """CONTRE-EPREUVE DE METHODE. `RitesOfMorkaiReviveTrigger(ReviveEffectTrigger)` derive
    d'`EffectTrigger` par un INTERMEDIAIRE : un critere sur le NOM de la base directe le classait
    << NON TRIE >>, un faux rouge que seule la vraie MRO dissout. Ce test fige que le recenseur
    resout la face pour de bon -- c'est la meme faute de forme que << l'absence dans une table ne
    prouve rien >>."""
    faces = {nom: face for _r, nom, _e, _es, face in P.porteurs_fire_on_death()}
    assert faces.get("RitesOfMorkaiReviveTrigger") == "EFFET", (
        "`RitesOfMorkaiReviveTrigger` n'est plus reconnue comme face EFFET (vu %r). Si sa base a "
        "change, le gate d'owner la concerne desormais et son verdict doit etre re-instruit ; si "
        "c'est le recenseur qui a regresse vers un test de nom, le reparer."
        % (faces.get("RitesOfMorkaiReviveTrigger"),))
    assert "INCONNUE" not in set(faces.values()), (
        "au moins un porteur n'est pas resolvable par import (%r) : le recenseur rend un verdict "
        "sur une classe qu'il ne charge pas."
        % (sorted(n for n, f in faces.items() if f == "INCONNUE"),))
