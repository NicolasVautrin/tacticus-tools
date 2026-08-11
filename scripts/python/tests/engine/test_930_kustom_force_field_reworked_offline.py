"""#930 -- gardes OFFLINE de la face COMBAT du passif `KustomForceFieldReworked` (`orksBigMek`).

Ce que ces tests FIGENT, et pourquoi chacun existe :

1. **Les DEUX appariements (effectType -> variable, filtre de faction)**. Le natif pose DEUX
   `ADynamicStatModifierEffect` qui partagent le MEME selecteur de tete et ne different que par
   leur variable (`extraArmor` / `extraArmor_2`) et par l'`op_LogicalNot` de leur filtre. Les
   confondre est SILENCIEUX : les deux ecrivent `FixedArmor`, sur des unites adjacentes, et un
   swap ne se voit que sur la VALEUR (797 vs 1197).
2. **Le PORTEUR est DANS sa propre aura.** `AdjacentFriends` l'exclut (`op_Subtraction`), le
   `op_Addition` du `CreateTargetSelector` le RE-AJOUTE. Ni l'i2 (« All friendly **adjacent**
   units », version non reworked) ni le voisin de forme le plus proche (`IconOfObstinacy`, MEME
   `AdjacentFriends` **sans** `op_Addition`) ne le disent. Mesure live : +1197 sur le Big Mek.
3. **Les magnitudes EXACTES**, mesurees live (797 / 1197), jamais un `> 0`. C'est le seul canal ou
   un swap de variable, une perte du multiplier de rarete ou un mauvais niveau se voient.
4. **La re-evaluation au MOUVEMENT** (bout-en-bout `refresh_aura_stat_modifiers`) : un allie qui
   entre dans le ring-1 gagne la modification, un allie qui en sort la PERD. Le seed ne la fige
   pas.
5. **L'ABSENCE de l'interface self-buff.** La declarer donnerait au porteur son bonus DEUX fois
   (une par l'aura qui l'inclut, une par le canal SELF) -- et aucun autre garde ne bougerait.

Tests OFFLINE (aucun runner) -- ils tournent en quelques dixiemes de seconde.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le port lui-meme : les deux classes d'aura et leurs colonnes mesurees.
        "scripts/python/engine/entities/effects/loki/kustom_force_field.py",
        # Le FOYER PARTAGE du noeud de tete (`Owner + AdjacentFriends`) et de `faction_of`.
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # Le registre qui les fait exister cote combat + la pose a l'init.
        "scripts/python/engine/entities/effects/factory.py",
        # Le driver de l'aura stat-mod et ses DEUX points de cablage (seed / mouvement).
        "scripts/python/engine/runner/operations/aura_stat_mods.py",
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/snapshot.py",
        # Les mirrors d'enum dont les ordinaux sont assertionnes ici.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/stats.py",
        # Les DEUX faces DECISION du meme passif (#271) -- cette garde fige qu'elles restent
        # branchees sur la MEME ability et qu'aucune ne partage de cle avec l'autre.
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/non_owner.py",
        # Le consommateur du foyer que cette tranche a modifie (LionHelm lit `faction_of`).
        "scripts/python/engine/entities/effects/loki/dark_angels_passives.py",
        # Le paquet qui expose le module d'effets (sa cascade decide de ce qui est importable).
        "scripts/python/engine/entities/effects/loki/__init__.py",
        # Le confront LIVE dont ces gardes figent le resultat.
        "scripts/python/probe_930_kustom_force_field_reworked.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ces gardes figent des APPARIEMENTS et des MAGNITUDES mesures live (effectType -> variable, "
        "filtre de faction, 797/1197) que rien d'autre ne tient : les deux effets ecrivent la MEME "
        "stat sur des unites adjacentes, donc un swap ne se voit que sur la valeur. "
        "`build: True` : les ordinaux assertionnes (1566/1567 EffectType, 1547 TriggeredAbilityType, "
        "27/157 AbilityVariableType, 5 UnitFaction, 16 StatType) sont LUS dans les tables du hash "
        "courant -- un renumerotage au changement de build les rend faux, et c'est precisement ce "
        "que ce fichier doit voir."
    ),
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

import hexgeo                                                          # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType  # noqa: E402
from engine.entities.effect_type import EffectType                     # noqa: E402
from engine.entities.effects import aura_selectors as ASel             # noqa: E402
from engine.entities.effects.factory import (                          # noqa: E402
    ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES)
from engine.entities.effects.loki import kustom_force_field as KFF     # noqa: E402
from engine.entities.effects_state import EffectsState                 # noqa: E402
from engine.entities.stats import StatType, UnitStats                  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.entities.unit_context import UnitContext                   # noqa: E402
from engine.entities.unit_faction import UnitFaction                   # noqa: E402
from engine.runner.components import (                                 # noqa: E402
    HealthComponent, OwnerComponent, PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.aura_stat_mods import refresh_aura_stat_modifiers  # noqa: E402
from engine.runner.state import State                                  # noqa: E402

#: Le porteur, son ability level et son multiplier tels que `buildNormalizedBC` les pose au rank 17
#: -- et tels que la mesure live a ete faite.
PORTEUR = "orksBigMek"
ABILITY_LEVEL = 50
MULTIPLIER_PCT = 180

#: (nom d'EffectType, id, classe portee, variable gameconfig, membre d'enum, cibles Orks ?,
#:  magnitude MESUREE live au niveau/multiplier ci-dessus).
ATTENDU = [
    ("KustomForceFieldReworked", 1566, KFF.KustomForceFieldReworkedEffect,
     "extraArmor", AbilityVariableType.extraArmor, False, 797),
    ("KustomForceFieldReworked_Orks", 1567, KFF.KustomForceFieldReworkedOrksEffect,
     "extraArmor_2", AbilityVariableType.extraArmor_2, True, 1197),
]

#: Le montage de la mesure live (`probe_930`), rejoue ici sur un `State` synthetique :
#: (visual_id, col, row). Le RING-2 est PEUPLE deliberement : sans lui, elargir le rayon du
#: selecteur (`AdjacentTiles` -> `SurroundingTiles(2)`) est un mutant INERTE -- mesure, il passait
#: 20/20. Un montage dont toutes les unites sont a distance 1 ou >= 3 ne peut pas voir le rayon.
BIG_MEK_POS = (1, 0)
VOISINS = [("orksNob", 0, 0),                # Ork     dist 1 -> 1567
           ("ultraApothecary", 1, 1),        # non-Ork dist 1 -> 1566
           ("orksKillaKan", 3, 0),           # Ork     dist 2 -> RIEN (temoin de RAYON)
           ("astraBullgryn", 4, 4)]          # non-Ork dist 6 -> RIEN


def _monde(hostile_pos=None):
    """`State` synthetique : le Big Mek + ses trois voisins, tous team 1 ; `hostile_pos` place en
    plus un ennemi ADJACENT (team 2) pour que le volet `Friends` du selecteur soit DISCRIMINANT --
    sans lui, « meme equipe » serait vacuement vrai et un port qui l'oublie passerait."""
    state = State()
    state.effects = EffectsState.seed({})
    ids = {}

    def _unit(vid, col, row, team=1):
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=(3 if team == 1 else 4)))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
        stats = UnitStats()
        stats.ensure_seeded(StatType.FIXED_ARMOR, 0)
        e.add_component(StatsComponent(ctx=UnitContext(
            entity_id=e.id, visual_id=vid, active_ability_level=ABILITY_LEVEL,
            passive_ability_level=ABILITY_LEVEL, ability_variables_multiplier=MULTIPLIER_PCT,
            stats=stats)))
        ids[vid] = e.id
        return e.id

    _unit(PORTEUR, *BIG_MEK_POS)
    for vid, col, row in VOISINS:
        _unit(vid, col, row)
    if hostile_pos is not None:
        _unit("orksWarboss", hostile_pos[0], hostile_pos[1], team=2)   # ENNEMI, et Ork
    return state, ids


def _instance(nom, eid, level=ABILITY_LEVEL, mult=MULTIPLIER_PCT):
    cls = EFFECT_CLASSES[nom]
    inst = cls(effect_type=eid, name=nom)
    inst.ability_level = level
    inst.ability_variables_multiplier = mult
    return inst


# ─────────────────────────────────────────────────────────────────── 1. registre et appariements

@pytest.mark.parametrize("nom,eid,cls,var,var_type,orks,_amt", ATTENDU)
def test_ids_registre_et_appariements(nom, eid, cls, var, var_type, orks, _amt):
    """Le mirror d'enum, les DEUX registres, et les trois colonnes LUES au decompile."""
    assert int(getattr(EffectType, nom)) == eid
    assert EFFECT_CLASSES.get(nom) is cls
    assert cls._VAR == var
    assert int(cls._VAR_TYPE) == int(var_type)
    assert cls._ORKS_ONLY is orks
    assert int(cls("x").aura_stat_modification_stat()) == int(StatType.FIXED_ARMOR) == 16


def test_les_deux_variables_sont_distinctes_et_les_deux_filtres_opposes():
    """Sans cette assertion, une uniformisation (« les deux lisent extraArmor », ou « les deux
    ciblent les Orks ») passerait -- et c'est EXACTEMENT ce que le decompile interdit : les DEUX
    `GetDynamicStatModificationAmount` different par leur seul `variableType`, les DEUX
    `CreateTargetSelector` par le seul `op_LogicalNot`."""
    vars_ = {c._VAR for _n, _i, c, _v, _t, _o, _a in ATTENDU}
    filtres = {c._ORKS_ONLY for _n, _i, c, _v, _t, _o, _a in ATTENDU}
    assert vars_ == {"extraArmor", "extraArmor_2"}, vars_
    assert filtres == {False, True}, filtres
    # non-vide du discriminant : les deux ordinaux d'AbilityVariableType diffèrent aussi.
    assert int(AbilityVariableType.extraArmor) == 27
    assert int(AbilityVariableType.extraArmor_2) == 157
    assert int(AbilityVariableType.extraArmor) != int(AbilityVariableType.extraArmor_2)


def test_pose_a_l_init_et_pas_dans_ability_triggers():
    """Le trigger est HERITE (`On(0x21 = AbilityInit) & get_OwnerIsActor`) : la classe native
    `KustomForceFieldReworkedAbility` ne declare QUE `CreateBehaviour` -> canal
    `ABILITY_INIT_OWNER_EFFECTS`, JAMAIS `ABILITY_TRIGGERS` (pas de trigger propre) ni
    `ABILITY_CLASSES` (ce n'est pas une active)."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert ABILITY_INIT_OWNER_EFFECTS.get("KustomForceFieldReworked") == [
        "KustomForceFieldReworked", "KustomForceFieldReworked_Orks"]
    assert "KustomForceFieldReworked" not in ABILITY_TRIGGERS
    assert int(TriggeredAbilityType.KustomForceFieldReworked) == 1547
    assert int(TriggeredAbilityType.KustomForceFieldReworked) not in ABILITY_CLASSES


@pytest.mark.parametrize("nom,eid,cls,_v,_t,_o,_a", ATTENDU)
def test_aucune_interface_self_buff(nom, eid, cls, _v, _t, _o, _a):
    """Le porteur recoit son bonus PAR L'AURA (qui l'inclut), pas par le canal SELF. Declarer
    `get_stat_modification_*` le lui donnerait DEUX fois -- +2394 au lieu de +1197 -- et aucun
    autre garde ne bougerait."""
    inst = _instance(nom, eid)
    assert inst.get_stat_modification_stat() is None
    assert inst.get_stat_modification_amount() in (None, 0)
    # ... et l'interface AURA, elle, DOIT etre la (sinon `aura_stat_mods` ne voit aucun carrier).
    assert callable(getattr(inst, "aura_stat_modification_stat", None))
    assert callable(getattr(inst, "aura_stat_modification_targets", None))


# ─────────────────────────────────────────────────────────────────────────── 2. le SELECTEUR

def test_le_montage_est_bien_discriminant():
    """Contre-epreuve du montage lui-meme : sans elle, un `State` ou personne n'est adjacent
    rendrait DEUX ensembles vides et les tests ci-dessous passeraient a vide.

    Le RING-2 doit etre PEUPLE : c'est ce qui rend le rayon observable (mesure : sans `orksKillaKan`
    a distance 2, elargir le selecteur a `SurroundingTiles(2)` laissait les 20 tests VERTS)."""
    d = {vid: hexgeo.distance(BIG_MEK_POS, (c, r)) for vid, c, r in VOISINS}
    assert d == {"orksNob": 1, "ultraApothecary": 1, "orksKillaKan": 2, "astraBullgryn": 6}, d
    assert 2 in set(d.values())            # non-vide du temoin de RAYON


def test_selecteur_partitionne_par_faction_et_inclut_le_porteur():
    """`Filter(Owner + AdjacentFriends(Owner), [!]HasFaction(Subject, Orks))`.

    Le porteur (Ork) part dans l'effet `_Orks` ; l'ami Ork adjacent aussi ; l'ami non-Ork adjacent
    dans l'autre ; l'ami non-Ork ELOIGNE dans aucun ; l'ENNEMI Ork adjacent dans aucun (volet
    `Friends`)."""
    state, ids = _monde(hostile_pos=(2, 0))
    assert hexgeo.distance(BIG_MEK_POS, (2, 0)) == 1        # l'ennemi EST adjacent
    owner = ids[PORTEUR]
    non_orks = _instance("KustomForceFieldReworked", 1566).aura_stat_modification_targets(
        state, owner)
    orks = _instance("KustomForceFieldReworked_Orks", 1567).aura_stat_modification_targets(
        state, owner)
    assert set(orks) == {owner, ids["orksNob"]}, orks
    assert set(non_orks) == {ids["ultraApothecary"]}, non_orks
    assert ids["orksKillaKan"] not in set(orks) | set(non_orks)      # ring-2 : RAYON
    assert ids["astraBullgryn"] not in set(orks) | set(non_orks)     # ring-1 seulement
    assert ids["orksWarboss"] not in set(orks) | set(non_orks)       # `Friends` = meme equipe


def test_les_deux_ensembles_sont_disjoints_et_couvrent_le_ring():
    """Le `op_LogicalNot` est le SEUL ecart entre les deux selecteurs : leur union doit etre
    exactement le noeud de tete, et leur intersection vide. Un port qui oublierait un des deux
    filtres ferait cumuler les DEUX modifications sur les memes unites."""
    state, ids = _monde()
    owner = ids[PORTEUR]
    tete = set(ASel.adjacent_friends_including_owner(state, owner))
    a = set(_instance("KustomForceFieldReworked", 1566)
            .aura_stat_modification_targets(state, owner))
    b = set(_instance("KustomForceFieldReworked_Orks", 1567)
            .aura_stat_modification_targets(state, owner))
    assert a & b == set()
    assert a | b == tete
    assert owner in tete                       # `op_Addition(Owner, ...)`
    assert tete == {owner, ids["orksNob"], ids["ultraApothecary"]}
    assert ids["orksKillaKan"] not in tete     # ring-2 exclu par `AdjacentTiles`


def test_faction_inconnue_est_ecartee_des_deux_effets():
    """Tri-etat : `faction_of` rend `None` (pas de `visual_id` gameconfig) = NON MESURE, jamais
    « non-Ork ». Le rabattre poserait un buff que le natif ne pose peut-etre pas."""
    state, ids = _monde()
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id="__inconnu__", alive=True))
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(PositionComponent(col=2, row=0))
    e.add_component(HealthComponent(hp=10, hp_max=10))
    stats = UnitStats()
    stats.ensure_seeded(StatType.FIXED_ARMOR, 0)
    e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id="__inconnu__",
                                                   stats=stats)))
    owner = ids[PORTEUR]
    assert e.id in set(ASel.adjacent_friends_including_owner(state, owner))   # bien dans le ring
    assert ASel.faction_of(state, e.id) is None
    for nom, eid, _c, _v, _t, _o, _a in ATTENDU:
        assert e.id not in set(_instance(nom, eid).aura_stat_modification_targets(state, owner))


# ────────────────────────────────────────────────────────────────────────── 3. les MAGNITUDES

@pytest.mark.parametrize("nom,eid,_c,_v,_t,_o,attendu", ATTENDU)
def test_magnitude_exacte_mesuree_live(nom, eid, _c, _v, _t, _o, attendu):
    """Valeur EXACTE (jamais un `> 0`) : c'est le seul canal ou un swap de variable, la perte du
    multiplier de rarete (443/665 au lieu de 797/1197) ou un mauvais niveau se voient."""
    assert _instance(nom, eid).aura_stat_modification_amount() == attendu


@pytest.mark.parametrize("nom,eid,_c,_v,_t,_o,_a", ATTENDU)
def test_sans_ability_level_pas_de_magnitude(nom, eid, _c, _v, _t, _o, _a):
    """`ConfigVar` sans `AbilityState` -> pas de magnitude. `None`, jamais `0` : `_aura_carriers`
    ecarte alors le porteur au lieu d'ecrire une modification nulle."""
    assert _instance(nom, eid, level=None).aura_stat_modification_amount() is None


def test_le_multiplier_de_rarete_est_bien_applique():
    """Contre-epreuve : a multiplier 100 les magnitudes retombent sur les valeurs BRUTES du
    gameconfig. Sans elle, un port qui ignore `variablesAffectedByRarityBonus` passerait tous les
    tests ci-dessus si l'attendu avait ete fige a la valeur brute."""
    assert _instance("KustomForceFieldReworked", 1566, mult=100
                     ).aura_stat_modification_amount() == 443
    assert _instance("KustomForceFieldReworked_Orks", 1567, mult=100
                     ).aura_stat_modification_amount() == 665


# ────────────────────────────────────────────────────────── 4. bout-en-bout : POSE et REVERT

def _pose_les_deux(state, owner_id):
    """Materialise les DEUX effets sur le porteur, comme le fait le seed
    (`ABILITY_INIT_OWNER_EFFECTS`) ou la capture `decisionView.effects`."""
    state.effects.by_unit[owner_id] = [_instance(nom, eid)
                                       for nom, eid, _c, _v, _t, _o, _a in ATTENDU]


def _armure(state, uid):
    ent = state.get_entity(uid)
    return ent.get_component(StatsComponent).ctx.stats.get_stat(int(StatType.FIXED_ARMOR))


def test_refresh_pose_les_deux_modifications_aux_bonnes_unites():
    """Bout-en-bout par le driver generique : chaque cible recoit la modification de SON effet, et
    l'unite hors ring n'en recoit aucune."""
    state, ids = _monde()
    owner = ids[PORTEUR]
    _pose_les_deux(state, owner)
    refresh_aura_stat_modifiers(state)
    assert _armure(state, owner) == 1197                       # Ork -> extraArmor_2
    assert _armure(state, ids["orksNob"]) == 1197              # Ork adjacent
    assert _armure(state, ids["ultraApothecary"]) == 797       # non-Ork adjacent
    assert _armure(state, ids["orksKillaKan"]) == 0            # Ork a distance 2 -> RIEN
    assert _armure(state, ids["astraBullgryn"]) == 0           # hors ring-1


def test_refresh_suit_le_mouvement_dans_les_deux_sens():
    """`UpdateEffectTargets` : le selecteur est purement geometrique, donc un pas le change.
    Mesure live : `astraBullgryn` amene en (2,0) GAGNE +797 ; `ultraApothecary` eloigne en (1,3)
    les PERD entierement."""
    state, ids = _monde()
    owner = ids[PORTEUR]
    _pose_les_deux(state, owner)
    refresh_aura_stat_modifiers(state)

    # (a) l'allie non-Ork ELOIGNE entre dans le ring -> il gagne la modification NON-Ork.
    loin = state.get_entity(ids["astraBullgryn"]).get_component(PositionComponent)
    loin.col, loin.row = 2, 0
    assert hexgeo.distance(BIG_MEK_POS, (2, 0)) == 1
    refresh_aura_stat_modifiers(state)
    assert _armure(state, ids["astraBullgryn"]) == 797

    # (b) l'allie non-Ork ADJACENT sort du ring -> `RevertModification`, retour a 0.
    proche = state.get_entity(ids["ultraApothecary"]).get_component(PositionComponent)
    proche.col, proche.row = 1, 3
    assert hexgeo.distance(BIG_MEK_POS, (1, 3)) > 1
    refresh_aura_stat_modifiers(state)
    assert _armure(state, ids["ultraApothecary"]) == 0
    # ... et le porteur n'a pas bouge : sa propre modification est INCHANGEE.
    assert _armure(state, owner) == 1197


def test_un_ork_qui_entre_recoit_bien_extraArmor_2_et_pas_extraArmor():
    """Le discriminant du swap de variable en regime DYNAMIQUE : un Ork qui entre dans le ring
    doit recevoir 1197, pas 797. Sans ce test, echanger les deux `_VAR` laisserait le montage
    statique rouge mais ce chemin-la muet."""
    state, ids = _monde()
    owner = ids[PORTEUR]
    _pose_les_deux(state, owner)
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id="orksWarboss", alive=True))
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(PositionComponent(col=5, row=5))
    e.add_component(HealthComponent(hp=10, hp_max=10))
    stats = UnitStats()
    stats.ensure_seeded(StatType.FIXED_ARMOR, 0)
    e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id="orksWarboss",
                                                   stats=stats)))
    refresh_aura_stat_modifiers(state)
    assert _armure(state, e.id) == 0
    pc = e.get_component(PositionComponent)
    pc.col, pc.row = 2, 0
    refresh_aura_stat_modifiers(state)
    assert _armure(state, e.id) == 1197


# ─────────────────────────────────────────────────────── 5. les DEUX faces DECISION (#271)

def test_les_deux_faces_decision_restent_branchees_sur_la_meme_ability():
    """La face COMBAT ne remplace NI n'invalide les deux faces DECISION portees par #271 : elles
    lisent la MEME ability 1547 et des cles DISJOINTES, dans DEUX categories de poids distinctes
    (`TriggeredAbilities` vs `TriggeredAbilitiesNonOwner`)."""
    from engine.playbook.adjacent_unit_preference import (
        KustomForceFieldReworkedPlaybook, TRIGGERED_MOVE_PLAYBOOKS)
    from engine.playbook.non_owner import (
        KustomForceFieldReworkedNonOwnerPlaybook, NON_OWNER_MOVE_PLAYBOOKS)
    aid = int(TriggeredAbilityType.KustomForceFieldReworked)
    assert isinstance(TRIGGERED_MOVE_PLAYBOOKS.get(aid), KustomForceFieldReworkedPlaybook)
    assert isinstance(NON_OWNER_MOVE_PLAYBOOKS.get(aid),
                      KustomForceFieldReworkedNonOwnerPlaybook)
    assert (KustomForceFieldReworkedNonOwnerPlaybook.KEY
            == "KustomForceFieldReworked_FriendsLikeToBeAdjacent")
    assert int(KustomForceFieldReworkedNonOwnerPlaybook.ABILITY_ID) == aid


def test_le_x2_de_la_face_decision_porte_sur_la_MEME_faction_que_le_filtre_combat():
    """`UnitFaction.Orks = 5` est le MEME litteral aux trois endroits : `HasFaction(friend, 5)` de
    la face OWNER, `HasFaction(case.unit, 5)` de la face NON-OWNER, et le `HasFaction(Subject, 5)`
    du filtre de selecteur COMBAT. Le figer ensemble evite qu'un renumerotage n'en decale qu'un."""
    assert int(UnitFaction.Orks) == 5
    assert KFF._FACTION_ORKS == UnitFaction.Orks.name == "Orks"
    import gameconfig as GC
    assert (GC.unit(PORTEUR) or {}).get("FactionId") == KFF._FACTION_ORKS
