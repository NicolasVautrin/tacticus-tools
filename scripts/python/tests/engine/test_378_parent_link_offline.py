"""CLIQUET du canal PARENT (#378) -- `ChildComponent.ParentId`, du capteur au consommateur.

Le lien enfant -> SUMMONER n'etait publie par AUCUN RPC exploitable : `decisionView` en portait
bien un `parentId`, mais SANS discriminant (un capteur mort et une unite sans parent y rendaient
tous deux `null`), et `combatSnapshot` -- le canal de SEED de `load_state` et le seul re-lu PAR PAS
-- ne le portait pas du tout. Consequence MESUREE (#372 SS 7) : la chance du jumeau drone
`1307 DefenderOfTheGreaterGood_ExtraHitsDrone` se lisait sur SES tours au lieu de ceux de son
summoner, donc SOUS-ESTIMEE.

CE FICHIER NE TOUCHE PAS AU LIVE. Il exerce la logique de DECISION (les verdicts purs du probe) et
la CHAINE DE PORT (seed -> Scene -> substrat du noeud `Parent`), la ou un test live ne saurait pas
distinguer « pas de capteur » de « pas de summon ». La confrontation live vit dans
`probe_378_parent_link.py`, qui rend `NON CONFRONTE` en NOMMANT la cause tant que le bundle
`frida/hooks/*` n'a pas ete reinjecte.

VUE ROUGE, par mutation adversariale -- chaque garde ci-dessous a ete confrontee a son mutant.
Messages VERBATIM (obtenus en retirant la piece nommee) :

  (a) `_load_unit_parent` ecrit sans consulter `parentMeasured`
      (`if su.get("parentMeasured") is not True: continue` supprime) :
        AssertionError: MUTANT (a) : un capteur MUET a EFFACE le parent pose par la simulation --
        parent_of(u3) = None, attendu u1

  (b) `_parent_from_snapshot` filtre sur `parentId is not None` au lieu de `parentMeasured is True`
      (le reflexe naturel -- et il PERD l'information « mesure, sans parent ») :
        AssertionError: MUTANT (b) : une unite MESUREE SANS parent est absente de la table --
        Scene.parent_measured(2) = False, donc indistinguable d'un capteur muet

  (c) le cablage `"parent_by_id": scene.parent_by_id` retire de
      `playbook/prediction/normal_attack.py` (le port d'AVANT, reconstitue) :
        AssertionError: MUTANT (c) : la face PREDICTION ne threade pas parent_by_id --
        chance du drone 0 au lieu de 100 (il lit SES tours, pas ceux de son summoner)

  (d) `supreme_commander._has_friendly_kell` reduit a l'heuristique SEULE -- le port d'AVANT,
      reconstitue par retrait du bloc de lecture :
        AssertionError: MUTANT (d) : le gate accepte un summon d'un AUTRE summoner --
        la mesure `parentId != caster` a ete court-circuitee par la derivation config

      ⚠ Le mutant « `elif` -> `if` » (le premier essaye) N'EST PAS DISCRIMINANT : il DURCIT le gate
      (les deux conditions deviennent conjointes) au lieu de l'assouplir, et les 14 gardes restent
      VERTES. La degradation a chasser ici est PERMISSIVE, donc le mutant doit RETIRER la lecture,
      pas la doubler.

ASCII only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import probe_378_parent_link as P378                                          # noqa: E402
from engine.playbook.scene import Scene, _parent_from_snapshot                # noqa: E402
from engine.runner.snapshot import _load_unit_parent                          # noqa: E402
from engine.runner.components import UnitComponent, parent_of                 # noqa: E402
from engine.runner.state import State                                         # noqa: E402


# --------------------------------------------------------------- verdicts du probe (fonctions pures)

def test_un_hook_anterieur_est_DETECTE_et_pas_lu():
    """Un hook d'avant #378 ne connait pas `parentMeasured` : sa reponse ne porte pas la cle. On rend
    NON CONFRONTE et on ne lit AUCUN `parentId` -- le lire reviendrait a prendre le `null` d'une
    unite sans `ChildComponent` pour une mesure, exactement l'ambiguite qu'on ferme.

    ⚠ Le discriminant ne peut PAS etre `parentId` : l'ancien `readParentId` le publiait deja cote
    `decisionView`, et il vaut `null` dans les deux mondes."""
    ancien = {"units": [{"entityId": 1, "parentId": None}, {"entityId": 2, "parentId": None}]}
    v = P378.check_channel(ancien)
    assert v["status"] == "not_reinjected"
    assert v["message"] == P378.HOOK_NOT_REINJECTED
    assert "reinject" in v["message"]


def test_le_capteur_charge_est_reconnu_meme_sans_aucun_summon():
    """Un board SANS summon rend `parentMeasured=True` + `parentId=None` partout. C'est une mesure
    PLEINE, pas une absence -- et le probe doit la reconnaitre comme telle, sinon toute campagne
    sans summon se lirait « capteur non charge »."""
    v = P378.check_channel({"units": [{"entityId": 1, "parentId": None, "parentMeasured": True},
                                      {"entityId": 2, "parentId": None, "parentMeasured": True}]})
    assert v["status"] == "measured"


def test_parentMeasured_false_n_est_JAMAIS_lu_comme_absence_de_parent():
    """`parentMeasured=False` = classe `ChildComponent` irresolue ou lecture KO. Le `parentId` qui
    l'accompagne ne veut rien dire, et le verdict doit le DIRE au lieu de conclure « pas d'enfant »."""
    snap = {"units": [{"entityId": 3, "parentId": None, "parentMeasured": False}]}
    v = P378.check_link(snap, 3, 1)
    assert v["status"] == "not-measured"
    assert "n'a PAS eu lieu" in v["message"]


def test_un_fork_des_deux_canaux_est_DENONCE():
    """`combatSnapshot` et `decisionView` partagent le lecteur `readParentLink` : un desaccord n'est
    pas un etat de jeu, c'est un fork de la source unique."""
    snap = {"units": [{"entityId": 3, "parentId": 1, "parentMeasured": True}]}
    dv_ok = {"units": [{"id": 3, "parentId": 1, "parentMeasured": True}]}
    dv_ko = {"units": [{"id": 3, "parentId": 7, "parentMeasured": True}]}
    assert P378.check_agreement(snap, dv_ok)["status"] == "ok"
    v = P378.check_agreement(snap, dv_ko)
    assert v["status"] == "fork"
    assert "source unique" in v["message"]


def test_un_parentId_ZERO_non_normalise_est_pris_en_defaut():
    """`0` n'est PAS un id d'entite : `IdunBattle.Entities.Components.MatchComponent$$NextId` est un
    PRE-incrementeur sur un champ zeroe (source UNIQUE des ids -- ses xrefs sont les
    `Add*Operation$$Execute`), donc le premier id emis est `1`. Un `ParentId = 0` est le zero d'un
    champ que `ChildComponent$$.ctor` n'ecrit jamais : « pas de parent ».

    MESURE du 2026-07-31 (runner 264) : le hook COURANT publiait `parentId: 0` sur les 4 unites du
    roster et `83` sur les 2 `orksOrkBoys` invoques ; `dumpEntityComponents(entityId: 0)` rend
    `entity 0 not found`. Le capteur #378 normalise donc `0 -> null` -- mirror du
    `state.GetEntity(0) -> null` que `UnitExtensions$$GetParent` produit (il ne gate PAS sur zero).

    Cette garde est le CLIQUET de cette normalisation : un capteur qui laisserait passer le `0` brut
    injecterait un id d'entite FAUX dans `parent_by_id` et dans `UnitComponent.parent_id`."""
    brut = {"units": [{"entityId": 1, "parentId": 0, "parentMeasured": True}]}
    v = P378.check_roster_has_no_parent(brut, [1])
    assert v["status"] == "wrong", (
        "un `parentId: 0` NON normalise passe pour un vrai parent -- "
        "0 n'est jamais un id d'entite (MatchComponent$$NextId pre-incremente)")
    normalise = {"units": [{"entityId": 1, "parentId": None, "parentMeasured": True}]}
    assert P378.check_roster_has_no_parent(normalise, [1])["status"] == "ok"


def test_un_capteur_qui_pose_un_parent_PARTOUT_est_pris_en_defaut():
    """Contre-epreuve du roster : sans elle, un capteur qui rendrait un id CONSTANT sur toutes les
    lignes passerait l'etage du lien (le summon aurait, par hasard, le bon)."""
    snap = {"units": [{"entityId": 1, "parentId": 1, "parentMeasured": True},
                      {"entityId": 2, "parentId": 1, "parentMeasured": True}]}
    v = P378.check_roster_has_no_parent(snap, [1, 2])
    assert v["status"] == "wrong"
    assert P378.check_roster_has_no_parent(
        {"units": [{"entityId": 1, "parentId": None, "parentMeasured": True}]}, [1])["status"] == "ok"


# --------------------------------------------------------------- seed du port (`_load_unit_parent`)

def _state_with(units) -> State:
    """`State` minimal : des entites porteuses d'un `UnitComponent`, rien d'autre. Le seed n'a besoin
    que de ca (il n'ecrit qu'un champ)."""
    st = State()
    for uid, parent in units:
        e = st.add_entity(uid)
        e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True, parent_id=parent))
    return st


def _scene(parent_by_id) -> Scene:
    """`Scene` reduite : seul `parent_by_id` porte du sens ici, le reste est le neutre exige par le
    dataclass."""
    return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None,
                 parent_by_id=parent_by_id)


def test_seed_un_capteur_MUET_ne_touche_a_RIEN():
    """MUTANT (a) -- le coeur du tri-etat. La simulation offline a pose `parent_id = 1` au spawn ;
    un snapshot pris par un hook ANTERIEUR (pas de `parentMeasured`) ou par un capteur en echec
    (`parentMeasured=False`) ne doit RIEN ecraser. Ecrire son `None` transformerait le capteur muet
    en REGRESSION de la voie qui marchait deja."""
    for row in ({"entityId": 3, "parentId": None},                       # hook anterieur
                {"entityId": 3, "parentId": None, "parentMeasured": False}):   # lecture KO
        st = _state_with([(1, None), (3, 1)])
        _load_unit_parent(st, {"units": [row]})
        par = parent_of(st, 3)
        assert par is not None and par.id == 1, (
            "MUTANT (a) : un capteur MUET a EFFACE le parent pose par la simulation -- "
            "parent_of(u3) = %r, attendu u1" % (None if par is None else par.id))


def test_seed_une_mesure_PLEINE_ecrit_y_compris_pour_effacer():
    """`parentMeasured=True` + `parentId=None` est un FAIT (`TryGetComponent<ChildComponent> ==
    false` cote natif) : il EFFACE legitimement. Sans ca, un port qui aurait pose un parent a tort
    ne serait jamais corrige par la mesure."""
    st = _state_with([(1, None), (3, 999)])
    _load_unit_parent(st, {"units": [{"entityId": 3, "parentId": None, "parentMeasured": True}]})
    assert parent_of(st, 3) is None
    st2 = _state_with([(1, None), (3, None)])
    _load_unit_parent(st2, {"units": [{"entityId": 3, "parentId": 1, "parentMeasured": True}]})
    assert parent_of(st2, 3).id == 1


def test_seed_ignore_une_entite_inconnue_sans_lever():
    """Le snapshot peut porter des lignes que l'ECS n'a pas (MoW non materialisee, corpse filtre) :
    le seed les saute, il ne leve pas."""
    st = _state_with([(1, None)])
    _load_unit_parent(st, {"units": [{"entityId": 42, "parentId": 1, "parentMeasured": True},
                                     {"parentId": 1, "parentMeasured": True}]})
    assert parent_of(st, 1) is None


# --------------------------------------------------------------- Scene (face PREDICTION)

def test_scene_distingue_MESURE_SANS_PARENT_de_NON_MESURE():
    """MUTANT (b) -- le tri-etat cote table. Filtrer sur `parentId is not None` (le reflexe naturel)
    PERD l'etat « mesure, sans parent » : l'unite sort de la table et devient indistinguable d'une
    non-mesuree. `Scene.parent_measured` est ce qui rend la distinction lisible."""
    snap = {"units": [{"entityId": 1, "parentId": None, "parentMeasured": True},   # mesure, no parent
                      {"entityId": 2, "parentId": None, "parentMeasured": True},
                      {"entityId": 3, "parentId": 1, "parentMeasured": True},      # mesure, parent
                      {"entityId": 4, "parentId": None, "parentMeasured": False},  # NON mesure
                      {"entityId": 5, "parentId": None}]}                          # hook anterieur
    sc = _scene(_parent_from_snapshot(snap))
    assert sc.parent(3) == 1
    assert sc.parent(1) is None and sc.parent_measured(1) is True, (
        "MUTANT (b) : une unite MESUREE SANS parent est absente de la table -- "
        "Scene.parent_measured(2) = %r, donc indistinguable d'un capteur muet"
        % sc.parent_measured(2))
    for uid in (4, 5):
        assert sc.parent(uid) is None and sc.parent_measured(uid) is False


def test_scene_sans_capteur_rend_le_comportement_ANTERIEUR():
    """Table vide (hook anterieur a #378) : tout le monde est `None`, le noeud
    `If(AmountIsGreaterThanZero(Parent(src)), Parent(src), src)` retombe sur `src`. C'est le
    comportement STRICTEMENT d'avant -- la degradation reste restrictive, jamais inventive."""
    sc = _scene({})
    assert sc.parent(3) is None and sc.parent_measured(3) is False


# --------------------------------------------------------------- consommateur #393 (chance du drone)

def _drone_ctx(parent_by_id):
    """Le contexte du canal AURA de COUPS, dans le regime de #372 : le drone (id 3, 0 tour) est
    l'aura-porteur, son summoner Shadowsun (id 1) a demarre 4 tours."""
    return {"owner_id": 3, "owner_pos": (0, 4), "owner_team": 1,
            "att_id": 2, "att_team": 1, "att_pos": (0, 3), "att_faction": "Tau",
            "is_melee": False, "damage_profile": "Physical",
            "turns_started_by_id": {1: 4, 3: 0}, "parent_by_id": parent_by_id}


def test_la_chance_du_drone_suit_le_lien_LU():
    """MUTANT (c) -- le consommateur mesure de #393. Le noeud natif est
    `If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )`
    (`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$
    CreateEffectHitsBonusForAttack`). Avec le lien : `min(100, 25 x 4) = 100`. Sans lui : le drone
    retombe sur SES 0 tours -> 0. C'est le chiffre de reference du residu."""
    from engine.entities.effects.loki.hits import DefenderOfTheGreaterGoodExtraHitsDroneEffect
    d = DefenderOfTheGreaterGoodExtraHitsDroneEffect(
        name="DefenderOfTheGreaterGood_ExtraHits", effect_type=1307, level=1, ability_level=50)
    with_link = d.current_extra_hit_chance(_drone_ctx({3: 1}))
    without = d.current_extra_hit_chance(_drone_ctx({}))
    assert with_link == 100 and without == 0, (
        "MUTANT (c) : la face PREDICTION ne threade pas parent_by_id -- "
        "chance du drone %r au lieu de 100 (il lit SES tours, pas ceux de son summoner)" % with_link)


def test_la_face_PREDICTION_threade_bien_le_substrat():
    """Le cablage lui-meme : `normal_attack` doit deposer `scene.parent_by_id` dans le board de la
    formule de coups. On lit le SOURCE plutot que de monter une prediction complete -- la garde vise
    la presence du fil, que le test precedent exerce ensuite bout en bout."""
    import inspect
    from engine.playbook.prediction import normal_attack
    src = inspect.getsource(normal_attack)
    assert '"parent_by_id": scene.parent_by_id' in src, (
        "MUTANT (c) : la face PREDICTION ne threade pas parent_by_id -- "
        "le board de `attack_hits_with_modifiers` n'a plus le noeud Parent")


# --------------------------------------------------------------- consommateur DECISION (IsFriendlyKell)

class _NC:
    """`NCContext` reduit aux trois champs que lit `_has_friendly_kell`."""
    def __init__(self, uid, units, obs_units=()):
        self.uid, self.units, self.obs_units = uid, list(units), list(obs_units)


def test_isfriendlykell_LIT_le_parent_quand_il_est_mesure():
    """MIRROR de `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell` :
    `*(int *)(comp + 0x10) == EntityId(caster)` puis `UnitExtensions$$IsFriend`.

    MUTANT (d) : si le port retombe sur l'heuristique DERRIERE une mesure, un summon appartenant a un
    AUTRE summoner de la meme equipe (le cas que la derivation config ne sait PAS trancher, cf.
    `_kit_spawn_visual_ids`) passerait le gate."""
    from engine.playbook.noncomparable.supreme_commander import SupremeCommanderPlaybook
    pb = SupremeCommanderPlaybook()
    creed = {"id": 1, "visualId": "astraCreed", "team": 1}
    autre_creed = {"id": 9, "visualId": "astraCreed", "team": 1}
    # le Kell est l'enfant de l'AUTRE Creed (id 9) -- mesure sans ambiguite
    kell_autrui = {"id": 3, "visualId": "astraSmnKell", "team": 1,
                   "parentId": 9, "parentMeasured": True}
    assert pb._has_friendly_kell(_NC(1, [creed, autre_creed, kell_autrui])) is False, (
        "MUTANT (d) : le gate accepte un summon d'un AUTRE summoner -- "
        "la mesure `parentId != caster` a ete court-circuitee par la derivation config")
    kell_mien = {**kell_autrui, "parentId": 1}
    assert pb._has_friendly_kell(_NC(1, [creed, autre_creed, kell_mien])) is True


def test_isfriendlykell_garde_le_REPLI_ligne_par_ligne():
    """Une source qui ne porte PAS le champ (`observeBattle`, source des MORTS -- un Kell tombe
    satisfait encore le gate natif, dont le selecteur est `baseSelector + AllDeadUnits()`) reste
    traitee par la derivation config. Le repli est PAR LIGNE : la couverture ne baisse jamais."""
    from engine.playbook.noncomparable.supreme_commander import SupremeCommanderPlaybook
    pb = SupremeCommanderPlaybook()
    creed = {"id": 1, "visualId": "astraCreed", "team": 1}
    mort = {"squadId": 3, "visualId": "astraSmnKell", "teamId": 1}     # observeBattle : pas de parentId
    assert pb._has_friendly_kell(_NC(1, [creed], obs_units=[mort])) is True
