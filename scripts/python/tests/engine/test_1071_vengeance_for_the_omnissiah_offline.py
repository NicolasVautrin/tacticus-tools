"""#1071 OFFLINE -- le passif `VengeanceForTheOmnissiah` (`TriggeredAbilityType` 0x512 = 1298,
`admecSmnTechpriest` << Tech-Priest Enginseer >> et son jumeau npc `admecNpc2Techpriest`).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage du registre, les TROIS conjoints du `CreateTrigger`, la CIBLE du behaviour (`Owner@+0x30`,
pas `Target@+0x60`), et -- surtout -- que la constante lue est une NUMBER-CONSTANT, hors niveau.

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change (meme cran que `test_1023`).

CE QUE CE FICHIER NE COUVRE PAS, et c'est ECRIT :
  * le canal DEGAT de `1365 MachineVengeance` (`MachineVengeanceEffect$$
    CreateEffectDamageBonusForAttack`) n'est PAS porte -- l'effet n'a aucune classe dans
    `EFFECT_CLASSES`. Le gain est donc observable par le NIVEAU, pas par un degat. C'est le residu
    #1023-r1, INCHANGE par cette tranche et garde a l'etage 6 ci-dessous ;
  * le volet `Untargetable` du `selectionType = 2` : le montage offline n'alimente pas
    `ctx.has_unit_flag`, donc la clause degrade en VRAI (tri-etat documente d'`IsAdjacent`). Ce
    n'est PAS une non-morsure mesuree, c'est un canal absent -- ecrit comme tel a l'etage 5.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE : le module de trigger, le registre, l'emetteur du vecteur et les feuilles DSL sont tous
    # dans la fermeture d'imports de ce fichier, donc dans la cascade DERIVEE par le foyer.
    # Recopier des chemins ici serait la faute #531.
    "chemins": (),
    # VRAI : la magnitude vient du gameconfig du build
    # (`VengeanceForTheOmnissiah.constants.effectLevel`). Un re-dump qui renommerait cette cle
    # ferait tomber le gain a 0 -- exactement le rouge attendu.
    "build": True,
    "toujours": False,
    "raison": (
        "Offline : fige les ordinaux ECRITS AU SITE (0x512 = 1298 la triggered, 0x555 = 1365 "
        "l'effet, 0x36 = 54 le vecteur, 0x73 = 115 la constante), le cablage d'`ABILITY_TRIGGERS`, "
        "les TROIS conjoints du `CreateTrigger` (`AreFriends`, `IsAdjacent(.,.,2)`, "
        "`IsMechanical(Target,2)`) plus le `ownerNeedsToBeAlive` collapse, la CIBLE du behaviour "
        "(`Owner@+0x30` DEUX FOIS, pas `Target@+0x60`), le `maxLevel = NULL` (aucun cap), et le "
        "fait que la constante lue est une NUMBER-CONSTANT hors niveau -- la lecture qui rend cet "
        "item confrontable malgre le defaut #1049-r1 d'`--explicit-stats`."
    ),
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.effect_type import EffectType
from engine.entities.effects_state import EffectsState
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_context import UnitContext
from engine.entities.unit_selection_type import UnitSelectionType
from engine.entities.unit_team_selection_type import UnitTeamSelectionType
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.dispatch.move_death import unit_defeated_triggers
from engine.runner.operations.triggers.loki import vengeance_for_the_omnissiah as VO
from engine.runner.state import State

TECHPRIEST = "admecSmnTechpriest"
#: Le JUMEAU npc -- meme `visualId` que le summon, donc le porteur MIROIR du montage live
#: (`--explicit-stats admecNpc2Techpriest:45`), et non une greffe.
TECHPRIEST_NPC = "admecNpc2Techpriest"
#: Les traits REELS du porteur (`gameconfig.units.summons.admecSmnTechpriest.traits`).
TECHPRIEST_TRAITS = ("Summon", "Mechanical", "Mechanic")

LEVEL, MULT = 50, 100
HP_MAX = 20000


class _Ctx(UnitContext):
    """Le minimum de `UnitContext` que `collect_triggered_abilities` et `entities_from_state` lisent.

    `passive_abilities` est le canal MESURE dont le collecteur se sert en priorite -- c'est aussi le
    canal exact d'un montage live, donc offline et live passent par la MEME porte."""

    def __init__(self, visual_id: str, traits=(), passives=None):
        super().__init__(entity_id=0, visual_id=visual_id)
        self.traits = list(traits)
        if passives is not None:
            self.passive_abilities = list(passives)
        self.active_ability_level = LEVEL
        self.passive_ability_level = LEVEL
        self.ability_variables_multiplier = MULT


def _unite(st: State, uid: int, visual_id: str, *, team: int, traits=("Mechanical",),
           passives=None, pos=(0, 0), alive=True) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual_id, alive))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(HP_MAX, HP_MAX))
    e.add_component(StatsComponent(ctx=_Ctx(visual_id, traits, passives)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


def _level(st: State, uid: int) -> int:
    """Le niveau LU comme le lit `EffectLevelFormula$$Calculate` : la SOMME des instances non
    consommees. Second chemin de lecture volontaire -- on ne s'auto-teste pas avec le port."""
    return sum(int(getattr(e, "level", 0) or 0)
               for e in st.effects.by_unit.get(int(uid), [])
               if not getattr(e, "consumed", False)
               and int(getattr(e, "effect_type", -1)) == VO.MACHINE_VENGEANCE)


@pytest.fixture
def montage():
    """FIXTURE NOMMEE ET REUTILISABLE -- un Tech-Priest porteur, un allie MECANIQUE ADJACENT qui va
    mourir, et un tueur adverse.

    Chaque face NEGATIVE se fabrique en RETIRANT une piece du montage (l'adjacence, l'egalite
    d'equipe, le trait Mechanical, la vie du porteur), jamais en en ajoutant une."""
    def _monter(adjacent: bool = True, meme_equipe: bool = True, mechanical: bool = True,
                porteur_vivant: bool = True, porteur_niveau: int = 0,
                passives=(VO.VENGEANCE_FOR_THE_OMNISSIAH,), porteur_visual: str = TECHPRIEST):
        st = State()
        st.effects = EffectsState()
        porteur = _unite(st, 10, porteur_visual, team=1, traits=list(TECHPRIEST_TRAITS),
                         passives=list(passives), pos=(0, 0), alive=porteur_vivant)
        victime = _unite(st, 11, "admecDestroyer",
                         team=(1 if meme_equipe else 2),
                         traits=([UnitTrait.Mechanical.name] if mechanical else ["Infantry"]),
                         pos=((1, 0) if adjacent else (5, 5)))
        tueur = _unite(st, 20, "necroWarden", team=2, traits=["Mechanical"], pos=(4, 4))
        if porteur_niveau:
            AddEffectOperation.execute(st, source=porteur, target=porteur,
                                       effect_type=VO.MACHINE_VENGEANCE,
                                       name=VO.MACHINE_VENGEANCE_NAME, level=int(porteur_niveau))
        return st, porteur, victime, tueur
    return _monter


def _fire(st: State, victime: int, tueur: int):
    """Joue le vecteur `On(0x36 = UnitDefeated)` et rend les sorties de CE passif."""
    out = unit_defeated_triggers(st, victime, tueur) or []
    return [e for e in out if isinstance(e, dict)
            and e.get("passive") == VO.VENGEANCE_FOR_THE_OMNISSIAH]


# --------------------------------------------------------------------------- 1. les ORDINAUX LUS
def test_ordinaux_ecrits_aux_sites():
    """Les litteraux du decompile, figes AU SITE (cf. l'en-tete du fichier). Le MEMBRE est sur LA
    LIGNE, pas quelques lignes plus haut (#1031) : sans lui, rien ne dirait QUEL membre l'entier
    designe, et un renumerotage laisserait le site pointer ailleurs."""
    assert int(TriggeredAbilityType.VengeanceForTheOmnissiah) == 1298 == 0x512
    assert int(EffectType.MachineVengeance) == 1365 == 0x555
    assert int(EventTriggerType.UnitDefeated) == 54 == 0x36
    assert int(AbilityConstantType.effectLevel) == 115 == 0x73
    assert VO.VENGEANCE_FOR_THE_OMNISSIAH_ID == 1298
    assert VO.MACHINE_VENGEANCE == 1365
    assert VO.MACHINE_VENGEANCE_NAME == "MachineVengeance"
    assert VO.VengeanceForTheOmnissiahAbility.event_id == 54 == int(EventTriggerType.UnitDefeated)
    assert VO.VengeanceForTheOmnissiahAbility.TRIGGERED_ABILITY_ID == 1298
    # La cle du registre EST le nom gameconfig de la `passiveAbilities`, pas un id.
    assert VO.VENGEANCE_FOR_THE_OMNISSIAH == "VengeanceForTheOmnissiah"
    # Les deux `selectionType` litteraux du `CreateTrigger`, et le `comparisonType` d'`AreFriends`.
    assert VO._SELECTION == 2 == int(UnitSelectionType.OnlyTargetable)
    assert VO._TEAM_SELECTION == 0 == int(UnitTeamSelectionType.ByCurrentTeam)


def test_effectLevel_115_n_est_PAS_effectLevel_2_118():
    """⚠ Homonymes proches : `AbilityConstantType.effectLevel` = 115 est la constante de CE passif ;
    `effectLevel_2` = 118 est le CAP que lit `ArcScourgeAbility$$GetDynamicInvalidCasterReason` sur
    une AUTRE ability. Les confondre lirait la mauvaise cle du gameconfig SANS lever."""
    assert int(AbilityConstantType.effectLevel) == 115
    assert int(AbilityConstantType.effectLevel_2) == 118
    assert VO.EFFECT_LEVEL_CONSTANT is AbilityConstantType.effectLevel


def test_l_effet_pose_est_LE_MEME_que_celui_qu_OmnissiahsBlessing_transfere():
    """Ce passif POSE la pile que son co-passif 1299 TRANSFERE, sur la MEME unite. Si les deux
    constantes divergeaient, chacun porterait sur un effet que l'autre ignore -- une panne
    SILENCIEUSE des deux cotes."""
    from engine.runner.abilities.admec import AS_MACHINE_VENGEANCE
    from engine.runner.operations.triggers.loki import omnissiahs_blessing as OB
    assert VO.MACHINE_VENGEANCE == OB.MACHINE_VENGEANCE == AS_MACHINE_VENGEANCE == 1365


# --------------------------------------------------------------------------- 2. le CABLAGE
def test_le_registre_porte_la_classe():
    assert REG.ABILITY_TRIGGERS.get("VengeanceForTheOmnissiah") == [
        VO.VengeanceForTheOmnissiahAbility]


def test_ce_n_est_PAS_une_relique_ni_une_helper_d_active():
    """C'est une `passiveAbilities` de kit : elle entre par `ABILITY_TRIGGERS` et par LUI SEUL. Une
    entree dans un autre registre la ferait porter par un chemin de montage que le natif n'emprunte
    pas (`TertiaryAbility` / `relicAbilities` / `GetPassiveHelperAbility`)."""
    assert "VengeanceForTheOmnissiah" not in REG.RELIC_ABILITY_TRIGGERS
    assert "VengeanceForTheOmnissiah" not in REG.PASSIVE_HELPER_ABILITY_TRIGGERS
    assert "VengeanceForTheOmnissiah" not in REG.ACTIVE_ABILITY_TRIGGERS


def test_les_DEUX_porteurs_gameconfig_portent_bien_ce_passif():
    """La cle du registre doit etre EXACTEMENT le nom que `collect_triggered_abilities` lira dans
    `gameconfig.units.*.<id>.passiveAbilities` -- sinon l'inscription est un no-op silencieux
    (`.get(cle, ())` rend `()`). Et le SUMMON et son JUMEAU npc doivent tous deux le porter : c'est
    ce qui rend le montage live par `--explicit-stats <jumeau>` un MIROIR, pas une greffe."""
    import gameconfig as GC
    for uid in (TECHPRIEST, TECHPRIEST_NPC):
        u = GC.unit(uid) or {}
        assert "VengeanceForTheOmnissiah" in (u.get("passiveAbilities") or []), uid
    # Le jumeau est identifie par son `visualId`, pas par son nom.
    assert (GC.unit(TECHPRIEST) or {}).get("visualId") == TECHPRIEST_NPC
    assert set(TECHPRIEST_TRAITS) <= set((GC.unit(TECHPRIEST) or {}).get("traits") or [])


def test_l_emetteur_du_vecteur_existe_et_passe_le_MORT_en_TARGET():
    """`On(0x36)` serait un registered-but-dead sans `unit_defeated_triggers` -- et les TROIS
    conjoints du passif se lisent sur `Target@+0x60`, donc l'emetteur DOIT y mettre le MORT."""
    import inspect
    src = inspect.getsource(unit_defeated_triggers)
    assert "EventTriggerType.UnitDefeated" in src
    assert "dying_id" in src and "killer_id" in src


# --------------------------------------------------------- 3. le GAIN nominal et son ABSENCE de cap
def test_le_gain_nominal_pose_la_pile_sur_LE_PORTEUR(montage):
    """`AddEffectOrIncreaseLevel(0x555, ..., source = Owner@+0x30, targets = Owner@+0x30,
    ConfigConst(effectLevel), NULL)` -- << the Tech-Priest Enginseer gains 1 level of Machine
    Vengeance >>."""
    st, porteur, victime, tueur = montage()
    assert _level(st, porteur) == 0
    ev = _fire(st, victime, tueur)
    assert len(ev) == 1 and ev[0]["defeated"] == victime and ev[0]["level"] == 1
    assert _level(st, porteur) == 1, "la pile n'a pas ete posee sur le PORTEUR"
    assert _level(st, victime) == 0, "rien ne doit atterrir sur le MORT"


def test_le_gain_INCREMENTE_une_pile_existante_et_SANS_cap(montage):
    """`maxLevel = NULL` : `IncreaseEffectLevelOperation$$Execute` ne clampe rien. La branche prise
    est `IncreaseEffectLevel` (l'effet est deja present), pas `AddEffect`. Le montage part de 12 --
    au-dela du cap 9 d'`effectLevel_2` que porte une AUTRE ability -- precisement pour montrer que
    CE plafond-la ne borne PAS cette accumulation."""
    st, porteur, victime, tueur = montage(porteur_niveau=12)
    ev = _fire(st, victime, tueur)
    assert len(ev) == 1
    assert _level(st, porteur) == 13, "12 + 1 attendus, cumul SANS cap"


def test_la_magnitude_vient_du_gameconfig_et_PAS_du_niveau_d_ability():
    """LECTURE 1 de l'en-tete du module, gardee : la surcharge native est
    `ConfigAmount$$.ctor(this, config, constantType)` -> slot `+0x38` renseigne, `+0x30` VIDE ->
    `ConfigAmount$$Calculate` prend la branche `AbilityConfiguration$$GetNumberConstant`.

    Consequence testable, et c'est ce qui rend l'item confrontable malgre #1049-r1 : la valeur est
    la MEME quel que soit le niveau d'ability annonce. On l'etablit sur la SOURCE (la fonction ne
    prend aucun argument de niveau et lit `constants`, pas `variables`), pas sur une coincidence
    numerique."""
    import gameconfig as GC
    import inspect
    cfg = GC.ability(VO.VENGEANCE_FOR_THE_OMNISSIAH) or {}
    assert cfg.get("constants", {}).get("effectLevel") is not None
    assert not (cfg.get("variables") or {}), \
        "ce passif n'a AUCUNE variable per-niveau -- si le build en ajoute, la lecture change"
    assert VO.vengeance_effect_level() == 1
    # La fonction ne prend AUCUN parametre : ni niveau, ni multiplicateur ne peuvent l'influencer.
    assert list(inspect.signature(VO.vengeance_effect_level).parameters) == []
    # ⚠ On inspecte le CORPS, jamais `getsource` nu : la DOCSTRING cite `get_variable_for_level`
    # pour dire qu'on ne l'appelle PAS, et un `not in` sur la source entiere rougirait dessus --
    # un test qui accuse sa propre explication (mesure : premier jeu de ce fichier).
    noms = set(VO.vengeance_effect_level.__code__.co_names)
    assert "constants" not in noms          # `constants` est une chaine, pas un nom -> co_consts
    assert "get_variable_for_level" not in noms, \
        "la lecture passerait par le chemin PER-NIVEAU -- ce n'est pas la surcharge native"
    assert "ability" in noms, "la constante doit etre lue au gameconfig"
    consts = {c for c in VO.vengeance_effect_level.__code__.co_consts if isinstance(c, str)}
    assert "constants" in consts, "c'est bien le bloc `constants` du gameconfig qui est lu"
    assert "variables" not in consts


# ------------------------------------------------------- 4. les TROIS conjoints, un par contre-face
def test_un_allie_NON_ADJACENT_ne_declenche_PAS(montage):
    """`IsAdjacent(Owner@+0x30, Target@+0x60, 2)`. TEMOIN d'abord (adjacent -> 1 gain), puis la
    face negative -- deux montages qui rendraient le meme resultat ne concluraient rien."""
    st_t, porteur_t, victime_t, tueur_t = montage(adjacent=True)
    assert len(_fire(st_t, victime_t, tueur_t)) == 1, "le TEMOIN doit declencher"
    st, porteur, victime, tueur = montage(adjacent=False)
    assert _fire(st, victime, tueur) == []
    assert _level(st, porteur) == 0


def test_un_ENNEMI_adjacent_et_mecanique_ne_declenche_PAS(montage):
    """`AreFriends(Owner@+0x30, Target@+0x60, comparisonType: 0, anyEntity: false)`."""
    st, porteur, victime, tueur = montage(meme_equipe=False)
    assert _fire(st, victime, tueur) == []
    assert _level(st, porteur) == 0


def test_un_allie_adjacent_NON_MECANIQUE_ne_declenche_PAS(montage):
    """`IsMechanical(Target@+0x60, 2)` -- le predicat porte sur LA VICTIME, jamais sur le porteur."""
    st, porteur, victime, tueur = montage(mechanical=False)
    assert _fire(st, victime, tueur) == []
    assert _level(st, porteur) == 0


def test_un_porteur_MORT_ne_declenche_PAS(montage):
    """`On(0x36, ownerNeedsToBeAlive: 1)` -- le seul conjoint COLLAPSE du port, sur
    `UnitComponent.alive`."""
    st, porteur, victime, tueur = montage(porteur_vivant=False)
    assert _fire(st, victime, tueur) == []


def test_le_predicat_mecanique_accepte_les_TROIS_traits_de_la_disjonction(montage):
    """`UnitExtensions$$IsMechanical` = `HasTrait(Mechanical 5) || HasTrait(LivingMetal 1000) ||
    HasTrait(Vehicle 1029)`. Ecrire `HasTrait(Mechanical)` a la main raterait DEUX traits sur trois
    -- refus SILENCIEUX sur un allie `LivingMetal` (necrons) ou `Vehicle`."""
    for trait in (UnitTrait.LivingMetal.name, UnitTrait.Vehicle.name):
        st = State()
        st.effects = EffectsState()
        porteur = _unite(st, 10, TECHPRIEST, team=1, traits=list(TECHPRIEST_TRAITS),
                         passives=[VO.VENGEANCE_FOR_THE_OMNISSIAH], pos=(0, 0))
        victime = _unite(st, 11, "allie", team=1, traits=[trait], pos=(1, 0))
        tueur = _unite(st, 20, "necroWarden", team=2, traits=["Mechanical"], pos=(4, 4))
        assert len(_fire(st, victime, tueur)) == 1, trait
        assert _level(st, porteur) == 1, trait


def test_AUCUN_gate_sur_le_TUEUR(montage):
    """Le `CreateTrigger` natif ne porte NI `OwnerIsActor` NI `OwnerIsTarget` : le porteur gagne sa
    pile quel que soit le tueur -- y compris quand c'est LUI (`actor == owner`) ou quand le canal
    est absent. En ajouter un serait inventer un refus que le natif n'a pas."""
    for tueur_choisi in ("ennemi", "porteur", None):
        st, porteur, victime, tueur = montage()
        killer = {"ennemi": tueur, "porteur": porteur, None: None}[tueur_choisi]
        ev = _fire(st, victime, killer)
        assert len(ev) == 1, tueur_choisi
        assert _level(st, porteur) == 1, tueur_choisi


# --------------------------------------------------------------------------- 5. les CONTRE-EPREUVES
def test_MUTANT_la_cible_du_behaviour_est_le_MORT_au_lieu_du_PORTEUR(montage):
    """CONTRE-EPREUVE CENTRALE. Le natif relit DEUX FOIS `<Selectors>+0x30` (`source` ET `targets`).
    Le voisin de forme `OmnissiahsBlessing`, lui, vise `Target@+0x60` -- recopier son `Target()`
    ici poserait la pile sur un CADAVRE, ou elle n'a aucun effet et d'ou rien ne la reprend.

    TEMOIN d'abord (l'arbre NATIF met 1 sur le porteur, 0 sur le mort), mutant ensuite (l'inverse)."""
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors.accessors import Target
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.effects import add_effect_or_increase_level

    st_t, porteur_t, victime_t, _k = montage()
    VO.vengeance_behaviour_tree(1).execute(
        entities_from_state(st_t, porteur_t, victime_t),
        ExecutionContext(state=st_t, rng=st_t.rng))
    assert (_level(st_t, porteur_t), _level(st_t, victime_t)) == (1, 0), \
        "le TEMOIN doit poser la pile sur le PORTEUR"

    st, porteur, victime, _k2 = montage()
    mutant = add_effect_or_increase_level(VO.MACHINE_VENGEANCE, VO.MACHINE_VENGEANCE_NAME,
                                          Target(), amount=1, max_level=None)
    mutant.execute(entities_from_state(st, porteur, victime),
                   ExecutionContext(state=st, rng=st.rng))
    assert (_level(st, porteur), _level(st, victime)) == (0, 1), \
        "le mutant doit poser sur le MORT -- si ce n'est pas le cas, le temoin ne prouve rien"


def test_MUTANT_un_gate_IsAlive_sur_la_victime_eteindrait_TOUT(montage):
    """`selectionType = 2` = `OnlyTargetable`, qui n'appelle PAS `IsAlive`. C'est le meme regime que
    `BattleFatigueAbility$$CreateTrigger`. Ecrire `OnlyAlive` (1) ou `OnlyAliveAndTargetable` (3)
    ici -- le reflexe naturel puisqu'on ecoute une MORT -- ferait taire le passif en TOTALITE.

    Ce test rend cette substitution BRUYANTE : il MESURE que les deux autres valeurs refusent.
    ⚠ Le montage n'alimente pas `ctx.has_unit_flag`, donc le volet `Untargetable` de la valeur 2
    degrade en VRAI (tri-etat d'`IsAdjacent`) : ce fichier garde le choix de la VALEUR, pas le
    filtre de flag, qui n'est observable que live."""
    from engine.entities.selectors.accessors import Owner, Target
    from engine.entities.triggers import AreFriends, IsAdjacent, TriggerAnd, is_mechanical
    from engine.runner.abilities.behaviours.context import entities_from_state

    st, porteur, victime, _k = montage()
    # La victime est MORTE au moment ou le vecteur passe -- c'est le pipeline natif.
    st.get_entity(victime).get_component(UnitComponent).alive = False
    ents = entities_from_state(st, porteur, victime)

    def _arbre(sel):
        t = TriggerAnd(AreFriends(Owner(), Target(), VO._TEAM_SELECTION),
                       IsAdjacent(Owner(), Target(), int(sel)))
        return TriggerAnd(t, is_mechanical(Target(), int(sel)))

    assert bool(_arbre(UnitSelectionType.OnlyTargetable).evaluate(ents)) is True, \
        "le TEMOIN (2 = la valeur NATIVE) doit accepter un cadavre"
    for mauvais in (UnitSelectionType.OnlyAlive, UnitSelectionType.OnlyAliveAndTargetable):
        assert bool(_arbre(mauvais).evaluate(ents)) is False, \
            "%s ferait taire le passif sur toute mort" % mauvais.name


def test_MUTANT_sans_l_inscription_au_registre_le_passif_est_MUET(montage):
    """`.get(cle, ())` rend `()` sur un nom absent : ni erreur, ni trace. C'est le vice que garde
    l'etape 5 de `probe_313`, reproduit ici sur CE passif."""
    st, porteur, victime, tueur = montage(passives=("UnNomQuiNExistePas",))
    assert _fire(st, victime, tueur) == []
    assert _level(st, porteur) == 0


# ------------------------------------------------------- 6. ce qui N'EST PAS porte, AFFIRME
def test_l_effet_1365_n_a_toujours_AUCUNE_classe_portee():
    """Residu #1023-r1, INCHANGE par cette tranche. `MachineVengeanceEffect$$
    CreateEffectDamageBonusForAttack` = `ForPercentIncrease(OwnerIsCaster, Multiply(
    GetNumberConstant(config, 7), EffectLevel(Effect)))` n'est pas porte : le niveau est observable
    en propre, mais il ne se convertit pas encore en degat.

    Ce test AFFIRME l'absence pour qu'un port futur le fasse ROUGIR au lieu de passer inapercu."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    assert VO.MACHINE_VENGEANCE not in EFFECT_CLASSES, \
        ("1365 a desormais une classe d'effet : le residu #1023-r1 est ferme, mettre a jour "
         "ce test ET l'en-tete de `vengeance_for_the_omnissiah.py`")


# ---------------------------------------------------------- 7. la face DECISION (playbook MOVE)
class _WT:
    """Le porteur de poids minimal : `wt.sub(groupe, cle)`. On rend le poids MESURE dans la capture
    (`data/seed-bc.json`), pas un nombre rond arbitraire."""

    def __init__(self, valeur=30):
        self.valeur, self.vus = valeur, []

    def sub(self, groupe, cle):
        self.vus.append((groupe, cle))
        return self.valeur


def _ctx_move(voisins, uid=10):
    return {"uid": uid, "elev_by_pos": None, "friend_units": list(voisins)}


def _pb():
    from engine.playbook.adjacent_unit_preference import load_playbook
    return load_playbook(int(TriggeredAbilityType.VengeanceForTheOmnissiah))


def test_le_playbook_MOVE_est_inscrit_et_charge():
    """`PlaybookDatabase$$LoadPlaybook` : sans entree au registre, la face DECISION est inerte --
    et rien ne le signale (le dispatcher fait `if playbook == null: continue`)."""
    from engine.playbook.vengeance_for_the_omnissiah import VengeanceForTheOmnissiahPlaybook
    pb = _pb()
    assert isinstance(pb, VengeanceForTheOmnissiahPlaybook)
    assert pb.ability_id == 1298 == int(TriggeredAbilityType.VengeanceForTheOmnissiah)


def test_la_face_ATTAQUE_reste_ABSENTE_du_registre():
    """`<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` a pour corps ENTIER
    `yield Fix64.op_Implicit(0)` : un ZERO constant, sans lecture d'etat. L'inscrire serait une
    entree sur un corps trivial -- ce que `test_419_playbook_wiring_ratchet_offline` refuse. Son
    absence EST le comportement natif (un step a 0 ne se distingue pas d'un playbook absent)."""
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    assert int(TriggeredAbilityType.VengeanceForTheOmnissiah) not in TRIGGERED_ATTACK_PLAYBOOKS


def test_la_cle_de_poids_existe_dans_la_capture_BC():
    """Une cle absente rendrait 0 partout, sans erreur : le terme disparaitrait en silence."""
    import json
    from pathlib import Path
    racine = Path(__file__).resolve().parents[4]
    bc = json.loads((racine / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    poids = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilities") or {}
    from engine.playbook.vengeance_for_the_omnissiah import VENGEANCE_LIKES_ADJACENT_MECHANICAL
    assert VENGEANCE_LIKES_ADJACENT_MECHANICAL in poids
    assert int(poids[VENGEANCE_LIKES_ADJACENT_MECHANICAL]) == 30
    # Le poids est lu dans le groupe `TriggeredAbilities`, pas `TriggeredAbilitiesNonOwner`.
    wt = _WT()
    _pb().calculate_movement_utility_in_steps(
        (6, 6), _ctx_move([{"id": 11, "pos": (6, 7), "traits": ["Mechanical"]}]), wt)
    assert wt.vus == [("TriggeredAbilities", VENGEANCE_LIKES_ADJACENT_MECHANICAL)]


def test_MUTANT_le_terme_est_BINAIRE_et_PAS_un_produit_par_le_nombre():
    """CONTRE-EPREUVE CENTRALE de la face DECISION. Le corps natif `break` au PREMIER voisin
    qualifie, donc la valeur vaut `w` ou `0` -- jamais `w x N`. TOUS les voisins de forme du
    registre (`legacy_of_combat`, `close_combat_weakness`, `first_among_traitors`) sont, eux, des
    `count_adjacent x poids` : recopier leur corps ici multiplierait le terme, et **seulement sur
    les tuiles a plusieurs voisins mecaniques** -- invisible sur un montage a un seul voisin.

    TEMOIN d'abord (1 voisin -> 30 des deux formes, donc ce regime ne DISCRIMINE PAS), puis le
    regime a 3 voisins, ou les deux formes divergent (30 contre 90)."""
    from engine import battle_query as bq
    pb, wt = _pb(), _WT(30)
    un = [{"id": 11, "pos": (6, 7), "traits": ["Mechanical"]}]
    trois = un + [{"id": 12, "pos": (6, 5), "traits": ["Mechanical"]},
                  {"id": 13, "pos": (5, 6), "traits": ["Mechanical"]}]

    def produit(tile, ctx):                    # LA FORME DES VOISINS, montee ici pour etre refutee
        n = bq.count_adjacent(tile, [u["pos"] for u in ctx["friend_units"]
                                     if u.get("id") != ctx["uid"]],
                              ctx.get("elev_by_pos"), bq.neigh_map(ctx))
        return float(30 * n)

    assert pb.calculate_movement_utility_in_steps((6, 6), _ctx_move(un), wt) == 30.0
    assert produit((6, 6), _ctx_move(un)) == 30.0, \
        "a UN voisin les deux formes coincident -- ce regime ne prouve rien, d'ou celui d'apres"
    n3 = bq.count_adjacent((6, 6), [u["pos"] for u in trois], None, None)
    assert n3 >= 2, "le montage a 3 voisins doit en rendre au moins 2 ADJACENTS, sinon rien ne separe"
    assert pb.calculate_movement_utility_in_steps((6, 6), _ctx_move(trois), wt) == 30.0, \
        "le terme doit rester BINAIRE quel que soit le nombre de voisins"
    assert produit((6, 6), _ctx_move(trois)) > 30.0, \
        "la forme PRODUIT doit diverger ici -- sinon le mutant ne mord pas et le test ne prouve rien"


def test_le_MOVER_lui_meme_ne_compte_PAS():
    """`u == case.<+0x10>` : le porteur est son propre allie ET il est `Mechanical` (trait reel).
    Sans ce gate, le terme serait CONSTANT sur toutes les tuiles -- un biais silencieux.

    ⚠ LE SELF EST POSE SUR UNE TUILE **ADJACENTE** A LA TUILE CANDIDATE, PAS SUR ELLE. Premier jeu
    de ce test : le self etait en `(6,6)`, c.-a-d. SUR la tuile evaluee, et le 0 obtenu ne
    distinguait pas << exclu par le gate d'identite >> de << non adjacent a lui-meme >>
    (`IterateAdjacentTiles` exclut la tuile elle-meme). Regime DEGENERE : le test passait
    meme sans le gate. Le TEMOIN, place au MEME endroit avec un autre id, est ce qui l'a revele --
    il rendait 0 lui aussi."""
    pb, wt = _pb(), _WT(30)
    # Le self OCCUPE `(6,7)` et l'IA evalue la tuile voisine `(6,6)` : sans le gate d'identite, il
    # se compterait lui-meme et le terme vaudrait 30.
    seul = [{"id": 10, "pos": (6, 7), "traits": ["Mechanical", "Mechanic"]}]
    assert pb.calculate_movement_utility_in_steps((6, 6), _ctx_move(seul, uid=10), wt) == 0.0
    # TEMOIN : le MEME record, a la MEME position, avec un id DIFFERENT -> il compte. La seule
    # variable qui bouge est l'identite, donc l'ecart est imputable au SEUL gate teste.
    autre = [{"id": 99, "pos": (6, 7), "traits": ["Mechanical", "Mechanic"]}]
    assert pb.calculate_movement_utility_in_steps((6, 6), _ctx_move(autre, uid=10), wt) == 30.0


def test_le_filtre_mecanique_de_la_face_DECISION_couvre_les_TROIS_traits():
    """MEME disjonction que la face COMBAT (`UnitExtensions$$IsMechanical`), MEME foyer
    (`entities/traits/unit_trait.py::is_mechanical`). Ecrire `"Mechanical" in traits` raterait
    `LivingMetal` (necrons) et `Vehicle`, sans lever."""
    pb, wt = _pb(), _WT(30)
    for trait, attendu in (("Mechanical", 30.0), ("LivingMetal", 30.0), ("Vehicle", 30.0),
                           ("Infantry", 0.0)):
        got = pb.calculate_movement_utility_in_steps(
            (6, 6), _ctx_move([{"id": 11, "pos": (6, 7), "traits": [trait]}]), wt)
        assert got == attendu, "%s -> %s" % (trait, got)


def test_un_poids_NUL_court_circuite_sans_lire_les_voisins():
    """Meme forme que tous les voisins du registre : `if not w: return 0.0`. Un poids absent de la
    capture doit rendre 0 sans parcourir -- pas lever."""
    pb = _pb()
    assert pb.calculate_movement_utility_in_steps(
        (6, 6), _ctx_move([{"id": 11, "pos": (6, 7), "traits": ["Mechanical"]}]), _WT(0)) == 0.0


def test_un_voisin_ADJACENT_est_requis_pas_seulement_present():
    """La query native est `GetAdjacentFriends(TUILE CANDIDATE, unit)` : un ami mecanique LOIN de la
    tuile evaluee ne compte pas. C'est ce qui fait du terme une preference de POSITION."""
    pb, wt = _pb(), _WT(30)
    loin = [{"id": 11, "pos": (0, 0), "traits": ["Mechanical"]}]
    assert pb.calculate_movement_utility_in_steps((6, 6), _ctx_move(loin), wt) == 0.0
