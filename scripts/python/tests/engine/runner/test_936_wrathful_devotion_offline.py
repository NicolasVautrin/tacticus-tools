"""#936 -- `WrathfulDevotion` (passif `worldTerminator`, triggered 1214) : ce que le LIVE ne peut
PAS garder, et le verdict DEAD CODE de la troisieme branche de son `switch (triggerType)`.

CE FICHIER EXISTE POUR TROIS RAISONS, TOUTES MESUREES :

 1. **L'immediat `0x40b` est un `EffectType`, et l'ordinal est VALIDE dans les DEUX autres espaces.**
    `CurrentAbilityIs(AbilityOrEffect(...))` du `CreateTrigger` natif recoit `mov edx, 0x40b` puis
    la surcharge `op_Implicit(effect: **EffectType**)` (tranchee a l'ADRESSE du `call`, face aux
    QUATRE homonymes). 1035 = `EffectType.TeleportStrike_TeleportingIn`, mais aussi
    `TriggeredAbilityType.UnstoppableFerocity` et `ActiveAbilityType.PlagueWind`. Une confusion
    d'espace ne leve RIEN et ne se voit que par le NOM -- donc elle se garde ici.
 2. **La branche `triggerType == UnitDeath` de `$$CreateBehaviour` est INATTEIGNABLE**, donc l'effet
    `0x517 WrathfulDevotionKilled_Visual` n'est JAMAIS pose. Le verdict est re-derive DU BINAIRE
    (les immediats `On(x)` de `$$CreateTrigger`), pas recopie d'une lecture.
 3. **Le canal `On(UnitBecameTargetable)` vient d'etre AJOUTE au port par cette tranche.** Un
    evenement qu'aucun site n'emet rend inerte tout consommateur -- c'est exactement ce qui bloquait
    la 4e disjonction de `SavageKiller` (#929-r1). La garde de l'EMETTEUR vit donc ici, avec sa
    contre-epreuve (un effet NON-untargetable ne doit rien emettre).

ASCII only.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

import pe_symboles as PE
import hexgeo
import gameconfig as GC
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.effects_state import EffectsState
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import HealthComponent, ShieldComponent, UnitComponent
from engine.runner.operations.remove_effects import remove_effect_instance
from engine.runner.operations.triggers.dispatch import move_death as MD
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import wrathful_devotion as WD

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/wrathful_devotion.py",
        # le FOYER PARTAGE ou l'emetteur du vecteur a ete ajoute, et le module qui le construit
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        # le domaine du gate de TYPE (`is UntargetableEffect`) que l'emetteur consulte
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # le registre qui inscrit l'ability sur le kit
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # les mirrors d'enum dont ce fichier FIGE les ordinaux et la DISJONCTION des espaces
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        # les selecteurs et la feuille dont il verifie la composition
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # les deux lecteurs de gameconfig qu'il confronte au port, et la table i2 que le
        # premier ouvre pour resoudre les libelles
        "scripts/python/gameconfig.py", "scripts/python/unit_map.py", "data/i2_en.json",
        # la cascade que `load_state` + le dispatch tirent (mesuree par l'empreinte #457, pas
        # devinee) : le registre d'abilities/effets par entite et l'emetteur de flux
        "scripts/python/engine/entities/abilities/__init__.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        "scripts/python/engine/runner/caches/__init__.py",
        "scripts/python/engine/runner/caches/ability_and_effect_cache.py",
        "scripts/python/engine/streams/__init__.py",
        "scripts/python/engine/streams/verify_turn_finished.py",
    ),
    # Il LIT `GameAssembly.dll` (les immediats `On(x)` aux octets) et le gameconfig d'`AppData`,
    # tous deux HORS de l'arbre : un changement de build peut le faire basculer sans qu'un fichier
    # du depot bouge. Le foyer ajoute `data/symbols/**` de lui-meme.
    "build": True,
    "toujours": False,
    "raison": "Il grave ce que le live ne peut PAS garder : l'ESPACE D'ENUM de l'immediat 0x40b "
              "(silencieux en ordinal, valide dans les trois espaces), le verdict DEAD CODE de la "
              "branche `triggerType == UnitDeath` re-derive AUX OCTETS du binaire, et l'existence "
              "de l'EMETTEUR d'`On(UnitBecameTargetable)` -- un evenement jamais emis rendrait la "
              "face B inerte SANS rien faire rougir.",
}

ROOT = Path(__file__).resolve().parents[4].parent          # racine du depot
IMAGE_BASE = 0x180000000                                   # base de l'image PE de GameAssembly.dll

COLS, ROWS = 6, 6
WRASK = 10              # `worldTerminator`  -- alliance Chaos, porteur du passif
ALLY_CHAOS = 11         # `worldJakhal`      -- alliance Chaos, ADJACENT
ALLY_OTHER = 12         # `orksBoy`          -- alliance Xenos, ADJACENT (doit etre EXCLU)
ALLY_FAR = 13           # `worldExecutions`  -- alliance Chaos mais LOIN (doit etre EXCLU)
FOE_NEAR = 20           # ennemi ADJACENT
FOE_FAR = 21            # ennemi LOIN
HP = 100000
PASSIVE_LEVEL = 50


# --------------------------------------------------------------------------------- le montage
def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state(mult: int = 100, traits_mesures: bool = False):
    """`State` offline minimal : un board plat 6x6 et six unites, dont les positions sont CHOISIES
    pour que chaque bras du selecteur ait son temoin POSITIF et son temoin NEGATIF.

    `traits_mesures` choisit le CANAL du pseudo-trait `Chaos` (0x7ea), qui n'est dans le `traits`
    d'AUCUN kit gameconfig -- la couche meta l'injecte dans le BC. Les DEUX canaux du port sont
    exerces, parce qu'ils ne se recouvrent pas (#264) :
      * `False` (defaut) -- pas de cle `traits` dans le `combatSnapshot` : `traits_measured` reste
        faux et `entity_trait_names` DERIVE l'alliance (`GrandAlliance$$GetTrait`). C'est le regime
        d'un etat monte offline ;
      * `True` -- `traits` fourni, alliance COMPRISE : `traits_measured` passe a vrai et la
        derivation est court-circuitee. C'est le regime LIVE (`combatSnapshot.units[].traits`).
    Un montage qui poserait `traits: []` (le piege) ECRASERAIT le kit par << aucun trait >>."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    board = Board(tiles, adjacency="evenq")
    placement = [
        (WRASK, "worldTerminator", 1, 1, 2, 2),
        (ALLY_CHAOS, "worldJakhal", 1, 1, 2, 3),
        (ALLY_OTHER, "orksBoy", 1, 1, 3, 2),
        (ALLY_FAR, "worldExecutions", 1, 1, 5, 5),
        (FOE_NEAR, "necroWarden", 2, 2, 1, 2),
        (FOE_FAR, "necroImmortal", 2, 2, 5, 0),
    ]
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vis, "alive": True, "team": team, "owner": owner,
         "pos": {"col": col, "row": row}, "effects": []}
        for (uid, vis, team, owner, col, row) in placement]}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in decision["units"]]}
    import unit_map
    rows = []
    for u in decision["units"]:
        row = {"entityId": u["id"], "entityType": 1,
               "stats": {"health": HP, "movement": 3, "turnsStarted": 0},
               "healthMax": HP, "unitFlags": [],
               "unitConfig": {"visualId": u["visualId"], "level": PASSIVE_LEVEL,
                              "passiveAbilityLevel": PASSIVE_LEVEL,
                              "activeAbilityLevel": PASSIVE_LEVEL,
                              "abilityVariablesMultiplier": mult}}
        if traits_mesures:
            # Le canal natif publie des IDS `UnitTrait` (lus au runtime par `dumpEnum`), pas des
            # noms -- `trait_names_from_ids` les traduit et LEVE sur un id inconnu. On monte donc
            # le kit + l'alliance EN IDS, comme le capteur.
            kit = unit_map.kit(u["visualId"]) or {}
            noms = list(kit.get("traits") or []) + [kit.get("alliance")]
            row["traits"] = [int(UnitTrait[n]) for n in noms if n and n in UnitTrait.__members__]
        rows.append(row)
    snapshot = {"units": rows}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _shield(st, uid: int) -> int:
    e = st.get_entity(uid)
    sc = e.get_component(ShieldComponent) if e is not None else None
    return int(sc.get_total_shield()) if sc is not None else 0


def _slay(st, uid: int) -> None:
    """Amene la victime a l'etat que `On(UnitDefeated)` observe : PV a zero, `alive` faux (le
    vecteur natif est publie APRES `On(UnitDeath)`, donc la victime est deja morte)."""
    e = st.get_entity(uid)
    e.get_component(HealthComponent).hp = 0
    e.get_component(UnitComponent).alive = False


def _put(st, uid: int, effect_type, name: str):
    eff = BaseEffect(name=name, effect_type=int(effect_type), target=int(uid))
    st.effects.add_effect(int(uid), eff)
    return eff


def _has_visual(st, uid: int) -> bool:
    return any(not e.consumed and int(e.effect_type) == WD.TELEPORTED_VISUAL
               for e in (st.effects.by_unit.get(int(uid)) or []))


# ------------------------------------------------------------------- les CONSTANTES (gameconfig)
def test_le_montant_est_shieldHp_et_il_suit_le_bonus_de_rarete():
    """`GetVariableForLevel(cfg, AbilityVariableType.shieldHp = 0x27, abilityState, 0)`.

    L'attendu est calcule ICI depuis le TABLEAU du gameconfig -- jamais par `ability_var`, la
    fonction meme que le port appelle : un attendu recalcule par la fonction testee est l'un des
    faux verts recenses (il survit a toute mutation de cette fonction)."""
    cfg = GC.ability(WD.ABILITY_ID) or {}
    table = ((cfg.get("variables") or {}).get(WD.SHIELD_HP_KEY)) or []
    assert len(table) == 65, f"`WrathfulDevotion.variables.shieldHp` a {len(table)} paliers (65 lus)"
    assert int(table[-1]) == 2910, (
        f"dernier palier = {table[-1]} ; l'i2 annonce << a Shield with 2910 Health >>")
    assert WD.SHIELD_HP_KEY in (cfg.get("variablesAffectedByRarityBonus") or []), (
        "`shieldHp` n'est plus affectee par le bonus de rarete -> le multiplicateur ne doit plus "
        "etre applique, et le port le passe encore")
    attendu = int(table[PASSIVE_LEVEL - 1])                # `Level$$ToZeroBasedIndex`
    st = _state(mult=100)
    assert WD.shield_hp(st, WRASK) == attendu, (
        f"shield_hp = {WD.shield_hp(st, WRASK)} != gameconfig[{PASSIVE_LEVEL - 1}] = {attendu}")
    # le MULTIPLICATEUR mord : c'est le volet `variablesAffectedByRarityBonus`.
    st180 = _state(mult=180)
    assert WD.shield_hp(st180, WRASK) > attendu, (
        "le multiplicateur de rarete (180 %) ne change pas le montant : `ability_var` ne voit plus "
        "`shieldHp` comme affectee par la rarete")


def test_le_porteur_expose_bien_le_passif_et_le_trait_TeleportStrike():
    """Les DEUX faces reposent sur le kit de `worldTerminator` : la voie PASSIVE (qui inscrit
    l'ability au registre) et le trait `TeleportStrike` (sans lequel la face B n'a pas de
    substrat -- personne ne poserait `TeleportStrike_TeleportingIn` sur lui)."""
    import unit_map
    kit = unit_map.kit("worldTerminator")
    assert WD.ABILITY_ID in ((kit.get("voies") or {}).get("passive") or []), (
        f"`WrathfulDevotion` n'est plus une passive de worldTerminator : {kit.get('voies')}")
    assert "TeleportStrike" in (kit.get("traits") or []), (
        "worldTerminator n'a plus `TeleportStrike` : la face B (Deep Strike) perd son substrat")


# ------------------------------------------------------------- les ENUMS, et leur DISJONCTION
def test_l_immediat_0x40b_est_un_EffectType_et_l_ordinal_ment_dans_les_deux_autres_espaces():
    """LE PIEGE de cette ability, et il est SILENCIEUX EN ORDINAL.

    `CurrentAbilityIs` recoit `AbilityOrEffect(op_Implicit((EffectType)0x40b))` -- la surcharge est
    tranchee a l'ADRESSE de la cible du `call` (`op_Implicit(effect: EffectType)`), pas au pseudo-C,
    qui EFFACE l'immediat. Ce test grave l'ordinal ET le fait qu'il nomme autre chose dans les deux
    autres espaces : c'est le seul canal ou la confusion serait visible."""
    assert int(EffectType.TeleportStrike_TeleportingIn) == 0x40b == 1035
    assert WD._TELEPORT_STRIKE_TELEPORTING_IN == int(EffectType.TeleportStrike_TeleportingIn)
    assert TriggeredAbilityType(1035).name != "TeleportStrike_TeleportingIn", (
        "TriggeredAbilityType 1035 nomme desormais l'effet : la garde ne discrimine plus les "
        "espaces, il faut re-lire la surcharge `op_Implicit` du call-site")
    assert ActiveAbilityType(1035).name != "TeleportStrike_TeleportingIn", (
        "ActiveAbilityType 1035 nomme desormais l'effet : meme perte de discrimination")


def test_les_ordinaux_du_port_sont_ceux_du_build():
    """Les cinq ordinaux ECRITS au site, figes a la valeur MESUREE (`probe_313` garde le mirror
    contre le build ; il redevient vert apres un renumerotage, ce test non)."""
    assert int(TriggeredAbilityType.WrathfulDevotion) == 0x4be == 1214
    assert WD.WRATHFUL_DEVOTION == int(TriggeredAbilityType.WrathfulDevotion)
    assert int(EffectType.WrathfulDevotionKilled_Visual) == 0x517 == 1303
    assert int(EffectType.WrathfulDevotionTeleported_Visual) == 0x518 == 1304
    assert WD.TELEPORTED_VISUAL == 1304 and WD.KILLED_VISUAL_DEAD == 1303
    assert int(UnitTrait.Chaos) == 0x7ea == 2026 and int(WD.CHAOS_TRAIT) == 2026
    assert int(UnitSelectionType.OnlyAliveAndTargetable) == 3 and int(WD.SELECTION) == 3


def test_les_deux_abonnements_et_pas_un_de_plus():
    """GARDE STRUCTURELLE : `$$CreateTrigger` est une union de DEUX disjonctions, `On(0x36)` et
    `On(0x3b)`. Retirer l'une (le plus probable) ou en ajouter une fait rougir."""
    abonnes = ({int(WD.WrathfulDevotionAbility.event_id)}
               | {int(e) for e in WD.WrathfulDevotionAbility.event_ids})
    assert abonnes == {int(EventTriggerType.UnitDefeated),
                       int(EventTriggerType.UnitBecameTargetable)}, (
        f"abonnements = {sorted(abonnes)} ; le decompile en veut EXACTEMENT ces deux")
    assert int(EventTriggerType.UnitDeath) not in abonnes, (
        "`UnitDeath` a ete abonne. C'est l'evenement de la branche MORTE du `switch (triggerType)` "
        "-- l'abonner reveillerait `WrathfulDevotionKilled_Visual`, que le natif ne pose jamais")
    assert ABILITY_TRIGGERS.get(WD.ABILITY_ID) == [WD.WrathfulDevotionAbility], (
        "le registre n'inscrit plus l'ability sous sa cle gameconfig -> le passif ne serait "
        "collecte sur AUCUN porteur")


# ---------------------------------------------------------------------------- le SELECTEUR
def test_le_selecteur_prend_le_porteur_et_les_allies_Chaos_ADJACENTS_et_eux_seuls():
    """`Owner op_Addition UnitsWithTrait(AdjacentFriends(Owner, 1, 3), UnitTrait.Chaos, 3)`.

    QUATRE temoins, dont TROIS negatifs : l'allie non-Chaos adjacent (le bras `UnitsWithTrait`),
    l'allie Chaos LOIN (le bras `AdjacentFriends`), et l'ennemi adjacent (le bras `Friends`)."""
    st = _state()
    ids = [int(u["id"]) for u in WD.wrathful_devotion_targets().evaluate(entities_from_state(st, WRASK))]
    assert sorted(ids) == [WRASK, ALLY_CHAOS], (
        f"cibles = {sorted(ids)} ; attendu [{WRASK}, {ALLY_CHAOS}] "
        f"(exclus : {ALLY_OTHER} non-Chaos adjacent, {ALLY_FAR} Chaos mais loin, "
        f"{FOE_NEAR} ennemi adjacent)")
    assert len(ids) == len(set(ids)), (
        f"doublon dans l'`op_Addition` : {ids} -- le porteur ne doit PAS etre dans l'anneau")


def test_le_selecteur_donne_le_MEME_ensemble_quand_les_traits_sont_MESURES():
    """LE PSEUDO-TRAIT `Chaos` ARRIVE PAR DEUX CANAUX DISJOINTS (#264), et le port doit voir le
    meme ensemble par les deux : la DERIVATION `GrandAlliance$$GetTrait` (etat monte offline, pas
    de cle `traits`) et la MESURE `combatSnapshot.units[].traits`, ou le BC porte l'alliance
    explicitement (regime LIVE, `traits_measured` court-circuite la derivation).

    Sans ce test, le port pourrait dependre du seul canal offline et se taire en live -- exactement
    ce que le premier montage de ce fichier faisait (`traits: []` ECRASE le kit, et le selecteur
    tombait a un seul element)."""
    st = _state(traits_mesures=True)
    ids = sorted(int(u["id"]) for u in
                 WD.wrathful_devotion_targets().evaluate(entities_from_state(st, WRASK)))
    assert ids == [WRASK, ALLY_CHAOS], (
        f"canal MESURE : cibles = {ids} ; attendu [{WRASK}, {ALLY_CHAOS}]")


# ----------------------------------------------------------------- FACE A : le kill en melee
def test_face_A_un_kill_en_melee_pose_le_bouclier_et_AUCUN_visuel():
    """`On(UnitDefeated) & OwnerIsActor & IsDefeatedByMeleeAttack(Target)` -> branche `default` du
    `switch` natif = le bouclier SEUL. L'absence de marqueur n'est pas un oubli du port : c'est le
    verdict DEAD de la branche `triggerType == UnitDeath`."""
    st = _state()
    attendu = WD.shield_hp(st, WRASK)
    assert attendu > 0, "montage casse : le montant du bouclier est nul"
    _slay(st, FOE_NEAR)
    MD.unit_defeated_triggers(st, FOE_NEAR, killer_id=WRASK)
    assert _shield(st, WRASK) == attendu, f"bouclier du porteur = {_shield(st, WRASK)} != {attendu}"
    assert _shield(st, ALLY_CHAOS) == attendu, "l'allie Chaos adjacent n'a pas recu le bouclier"
    assert _shield(st, ALLY_OTHER) == 0, "un allie NON-Chaos a recu le bouclier"
    assert _shield(st, ALLY_FAR) == 0, "un allie Chaos NON adjacent a recu le bouclier"
    for uid in (WRASK, ALLY_CHAOS):
        assert not _has_visual(st, uid), (
            "la face A a pose un marqueur visuel : le natif tombe en branche `default`")
        assert not any(int(e.effect_type) == WD.KILLED_VISUAL_DEAD
                       for e in (st.effects.by_unit.get(uid) or [])), (
            "`WrathfulDevotionKilled_Visual` a ete pose : sa branche est du DEAD CODE")


def test_face_A_un_kill_A_DISTANCE_ne_declenche_rien():
    """`IsDefeatedByMeleeAttack` -- le conjoint que le port approxime POSITIONNELLEMENT. Sans lui le
    trigger serait PERMISSIF, et c'est la degradation que la doctrine condamne."""
    st = _state()
    _slay(st, FOE_FAR)
    MD.unit_defeated_triggers(st, FOE_FAR, killer_id=WRASK)
    assert _shield(st, WRASK) == 0 and _shield(st, ALLY_CHAOS) == 0, (
        "un kill a distance a pose le bouclier")


def test_face_A_un_kill_par_QUELQU_UN_D_AUTRE_ne_declenche_rien():
    """`get_OwnerIsActor` : le porteur doit etre le TUEUR. Temoin NEGATIF du conjoint que la face B
    n'a PAS (elle porte `get_OwnerIsTarget`) -- recopier l'une sur l'autre eteindrait une face."""
    st = _state()
    _slay(st, FOE_NEAR)
    MD.unit_defeated_triggers(st, FOE_NEAR, killer_id=ALLY_CHAOS)
    assert _shield(st, WRASK) == 0, "le bouclier est parti alors que Wrask n'est pas le tueur"


# --------------------------------------------------- FACE B : la sortie de Deep Strike
def test_face_B_la_sortie_de_deep_strike_pose_le_bouclier_ET_le_visuel():
    """`On(UnitBecameTargetable) & OwnerIsTarget & CurrentAbilityIs((EffectType)1035)`.

    Le vecteur est publie par le retrait de `TeleportStrike_TeleportingIn`, dont le gate natif est
    `EffectsDatabase.GetEffect(type) is UntargetableEffect`. Ce test exerce la CHAINE COMPLETE :
    `remove_effect_instance` -> `unit_became_targetable_triggers` -> la face B."""
    st = _state()
    attendu = WD.shield_hp(st, WRASK)
    eff = _put(st, WRASK, EffectType.TeleportStrike_TeleportingIn,
               EffectType.TeleportStrike_TeleportingIn.name)
    assert remove_effect_instance(st, WRASK, eff) is True
    assert _shield(st, WRASK) == attendu, "le porteur n'a pas recu son bouclier en sortie de deep strike"
    assert _shield(st, ALLY_CHAOS) == attendu, "l'allie Chaos adjacent n'a pas recu le bouclier"
    assert _shield(st, ALLY_OTHER) == 0 and _shield(st, ALLY_FAR) == 0
    # ... et le marqueur, que SEULE cette face pose (`b__1`, branche `triggerType == 0x3b`).
    assert _has_visual(st, WRASK) and _has_visual(st, ALLY_CHAOS), (
        "`WrathfulDevotionTeleported_Visual` n'a pas ete pose : la branche `0x3b` du `switch` "
        "natif est justement celle qui EST atteignable")
    assert not _has_visual(st, ALLY_OTHER), "le marqueur est parti sur une unite hors selecteur"


def test_les_DEUX_durees_ne_se_convertissent_PAS_pareil():
    """`CreateShield(..., turns: **TurnsFromRounds(1)**)` contre `AddEffect(..., turns:
    **Direct(1)**)` -- deux nœuds de duree DIFFERENTS dans le MEME `CreateBehaviour`.

    `TurnsFromRounds` passe par `BattleQuery$$ConvertRoundsToTurns` (x nombre de joueurs) ;
    `Direct(n)` est deja en TOURS et n'est PAS converti. A un joueur les deux coincident et le
    montage ne prouve rien -- c'est pourquoi ce test pose DEUX joueurs, seul regime ou la confusion
    est observable (elle vaudrait un facteur 2 sur la duree du bouclier, ou sur celle du marqueur)."""
    st = _state()
    st.turn_order_player_count = 2
    eff = _put(st, WRASK, EffectType.TeleportStrike_TeleportingIn, "X")
    assert remove_effect_instance(st, WRASK, eff) is True
    sc = st.get_entity(WRASK).get_component(ShieldComponent)
    assert [int(s.remaining) for s in sc.shields] == [2], (
        f"duree du bouclier = {[s.remaining for s in sc.shields]} tours a DEUX joueurs ; "
        "`TurnsFromRounds(1)` doit valoir 2 (sinon la conversion rounds->tours a saute)")
    visuels = [e for e in st.effects.by_unit.get(WRASK, [])
               if not e.consumed and int(e.effect_type) == WD.TELEPORTED_VISUAL]
    assert len(visuels) == 1 and int(visuels[0].remaining_turns) == 1, (
        f"duree du marqueur = {[e.remaining_turns for e in visuels]} ; `Direct(1)` est deja en "
        "TOURS -- le convertir donnerait 2, et ce serait un `TurnsFromRounds` invente")


def test_un_allie_Chaos_adjacent_EN_DEEP_STRIKE_est_exclu():
    """`UnitSelectionType.OnlyAliveAndTargetable = 3`, le DERNIER argument des DEUX selecteurs.

    Son volet TARGETABLE retire les unites portant un effet d'`UntargetableEffect` -- ici l'allie
    Chaos adjacent est lui-meme en Deep Strike. Sans ce temoin, `selection_type` serait un
    argument DECORATIF : rien dans le montage ne le distinguerait de `Any`."""
    st = _state()
    _put(st, ALLY_CHAOS, EffectType.TeleportStrike_TeleportingIn,
         EffectType.TeleportStrike_TeleportingIn.name)
    ids = sorted(int(u["id"]) for u in
                 WD.wrathful_devotion_targets().evaluate(entities_from_state(st, WRASK)))
    assert ids == [WRASK], (
        f"cibles = {ids} ; un allie NON CIBLABLE (deep strike) doit sortir du selecteur "
        "(`OnlyAliveAndTargetable`)")


def test_le_site_ECRIT_l_enum_EffectType_et_pas_un_homonyme_d_ordinal():
    """LE SEUL CANAL OU LA CONFUSION D'ESPACE EST VISIBLE, et il n'est pas executable.

    `int(EffectType.TeleportStrike_TeleportingIn)` et `int(TriggeredAbilityType.
    UnstoppableFerocity)` valent TOUS DEUX 1035 : un mutant qui remplacerait l'un par l'autre
    passerait TOUS les tests de comportement de ce fichier, et le port lirait le mauvais espace
    sans que rien ne leve. La garde porte donc sur le TEXTE du site -- c'est le seul endroit ou
    l'information existe encore."""
    src = (ROOT / "scripts" / "python" / "engine" / "runner" / "operations" / "triggers" / "loki"
           / "wrathful_devotion.py").read_text(encoding="utf-8")
    assert "int(EffectType.TeleportStrike_TeleportingIn)" in src, (
        "le site n'ecrit plus `EffectType.TeleportStrike_TeleportingIn` : l'ordinal 1035 est "
        "VALIDE dans `TriggeredAbilityType` et `ActiveAbilityType`, ou il nomme autre chose")
    for interdit in ("TriggeredAbilityType.UnstoppableFerocity", "ActiveAbilityType.PlagueWind"):
        assert interdit not in src, f"le site cite `{interdit}` : mauvais espace d'enum pour 1035"


def test_face_B_un_effet_NON_untargetable_n_emet_PAS_le_vecteur():
    """CONTRE-EPREUVE du gate de TYPE `is UntargetableEffect` -- OBSERVEE A L'EMISSION, et c'est
    load-bearing.

    ⚠ MUTANT M10, MESURE : remplacer le gate par `if True:` (emettre `On(0x3b)` a CHAQUE retrait
    d'effet) ne faisait ROUGIR AUCUN test tant que cette garde regardait l'AVAL (le bouclier).
    Cause : `CurrentAbilityIs(1035)` de la face B refuse deja tout autre effet, donc l'observable
    aval est identique -- le gate d'EMISSION etait masque par le gate de l'ABILITY. Un vecteur
    sur-emis reste pourtant une divergence : il ferait firer, au moindre retrait d'effet, tout
    futur consommateur d'`On(UnitBecameTargetable)` (a commencer par la 4e disjonction de
    `SavageKiller`, #929-r1). On observe donc l'APPEL, par substitution."""
    import engine.runner.operations.remove_effects as RE
    vus: list = []
    reel = MD.unit_became_targetable_triggers
    try:
        MD.unit_became_targetable_triggers = lambda st, tid, et: vus.append((tid, int(et))) or []
        st = _state()
        eff = _put(st, WRASK, EffectType.Pinned, EffectType.Pinned.name)
        assert RE.remove_effect_instance(st, WRASK, eff) is True
    finally:
        MD.unit_became_targetable_triggers = reel
    assert vus == [], (
        f"le retrait d'un effet ORDINAIRE (`Pinned`) a EMIS `On(UnitBecameTargetable)` : {vus}. "
        "Le gate `EffectsDatabase.GetEffect(type) is UntargetableEffect` ne mord plus")
    # ... et le pendant AVAL, qui reste utile : meme sur-emis, le gate de l'ability doit tenir.
    st2 = _state()
    eff2 = _put(st2, WRASK, EffectType.Pinned, EffectType.Pinned.name)
    assert remove_effect_instance(st2, WRASK, eff2) is True
    assert _shield(st2, WRASK) == 0, "le retrait d'un effet ORDINAIRE a declenche la face B"


def test_face_B_le_deep_strike_D_UN_AUTRE_ne_declenche_rien():
    """`get_OwnerIsTarget` : sur ce vecteur, `target == owner ==` le PORTEUR de l'effet retire.
    Un allie qui sort de deep strike ne donne donc rien -- temoin NEGATIF du conjoint propre."""
    st = _state()
    eff = _put(st, ALLY_CHAOS, EffectType.TeleportStrike_TeleportingIn,
               EffectType.TeleportStrike_TeleportingIn.name)
    assert remove_effect_instance(st, ALLY_CHAOS, eff) is True
    assert _shield(st, WRASK) == 0 and _shield(st, ALLY_CHAOS) == 0, (
        "la face B a fire sur le deep strike d'une AUTRE unite")


def test_face_B_un_AUTRE_effet_untargetable_ne_passe_pas_CurrentAbilityIs():
    """`CurrentAbilityIs((EffectType)1035)` : le vecteur est emis pour les QUATRE feuilles
    d'`ATeleportingEffect` portees, mais la face B n'accepte que `TeleportStrike_TeleportingIn`.
    Temoin qui separe l'EMETTEUR (large) du GATE (etroit)."""
    st = _state()
    eff = _put(st, WRASK, EffectType.FearOfTheUnseen_TeleportingIn,
               EffectType.FearOfTheUnseen_TeleportingIn.name)
    assert remove_effect_instance(st, WRASK, eff) is True
    assert _shield(st, WRASK) == 0, (
        "la face B a fire sur un AUTRE effet untargetable : `CurrentAbilityIs(1035)` ne mord pas")


def test_l_emetteur_du_vecteur_existe_et_est_CABLE():
    """GARDE << evenement jamais emis >>. Un canal declare mais non emis rend inerte tout
    consommateur SANS rien faire rougir -- c'est le defaut qui a maintenu #929-r1. On verifie donc
    l'EXISTENCE du vecteur ET son APPEL depuis le foyer de retrait, par substitution."""
    import engine.runner.operations.remove_effects as RE
    assert hasattr(MD, "unit_became_targetable_triggers")
    vus: list = []
    reel = MD.unit_became_targetable_triggers
    try:
        MD.unit_became_targetable_triggers = lambda st, tid, et: vus.append((tid, int(et))) or []
        st = _state()
        eff = _put(st, WRASK, EffectType.TeleportStrike_TeleportingIn, "X")
        RE.remove_effect_instance(st, WRASK, eff)
    finally:
        MD.unit_became_targetable_triggers = reel
    assert vus == [(WRASK, int(EffectType.TeleportStrike_TeleportingIn))], (
        f"`remove_effect_instance` n'appelle plus l'emetteur (vu : {vus}). La substitution MORD "
        "parce que le foyer importe le MODULE (forme B) -- si elle ne mord plus, c'est que "
        "l'import est repasse en forme A et que la garde est devenue vacue")


# ------------------------------------------------------ le verdict DEAD, cote PORT
def test_aucun_site_du_port_ne_pose_le_visuel_KILLED():
    """VERDICT : `0x517 WrathfulDevotionKilled_Visual` n'est pose NULLE PART, et c'est le verdict,
    pas un oubli.

    ⚠ Cette garde ASSERTIONNE SON PROPRE NON-VIDE : elle exige de trouver au moins un site qui pose
    le visuel ATTEIGNABLE (`0x518`). Sans ce cran, un balayage qui ne trouverait plus rien du tout
    (module renomme, motif change) passerait pour vert."""
    racine = ROOT / "scripts" / "python" / "engine"
    poseurs_1304, poseurs_1303 = [], []
    for p in racine.rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        if "WrathfulDevotionTeleported_Visual" in txt and "AddEffect(" in txt:
            poseurs_1304.append(p.name)
        # un poseur du visuel MORT : le nom passe a `AddEffect(` ou la constante du module
        if "AddEffect(" in txt and ("WrathfulDevotionKilled_Visual," in txt
                                    or "KILLED_VISUAL_DEAD," in txt):
            poseurs_1303.append(p.name)
    assert poseurs_1304, (
        "AUCUN site ne pose `WrathfulDevotionTeleported_Visual` : la garde ci-dessous serait VACUE "
        "(elle conclurait de l'absence sans avoir rien vu). Le port a-t-il perdu la face B ?")
    assert poseurs_1303 == [], (
        f"`WrathfulDevotionKilled_Visual` est desormais pose par {poseurs_1303}. Sa branche "
        "(`triggerType == UnitDeath`) est INATTEIGNABLE : `$$CreateTrigger` n'abonne que "
        "{UnitDefeated, UnitBecameTargetable}. Re-lire la RE avant de porter quoi que ce soit.")


# --------------------------------------------------- le verdict DEAD, RE-DERIVE DU BINAIRE
# #10026-r1 -- CES HELPERS DELEGUENT AU FOYER (`pe_symboles`, #10028). Ils etaient RECOPIES dans
# TROIS fichiers, avec trois corps differents, et deux d'entre eux rendaient la PREMIERE VA portant
# le nom -- verts PAR CHANCE (leurs symboles n'ont qu'une VA sur ce build), pas par construction.
# Trois copies, c'est trois dates de peremption. Depuis, `va_du_symbole` REFUSE un nom partage.
#
# ⚠ CE SONT DES WRAPPERS, PAS DES LIAISONS. `_va_of = PE.va_du_symbole` gelerait la fonction a
# l'import (forme A) et NE MORDRAIT PAS sous `monkeypatch.setattr("pe_symboles.va_du_symbole", …)`.
# Un wrapper resout l'attribut A CHAQUE APPEL -- c'est la forme B que le CLAUDE.md prescrit.
def _build_hash():
    return PE.build_avec_dll()


def _va_of(build, symbole):
    return PE.va_du_symbole(build, symbole)


def _vas_of(build, symbole):
    return PE.vas_du_symbole(build, symbole)


def _read_at_va(dll, va, size):
    return PE.lire_a_la_va(dll, va, size)


def _on_immediates(blob: bytes, va: int, vas_on) -> list:
    """Les `EventTriggerType` passes a `DSLTriggers$$On` -- RE-DERIVES du code, pas recopies.

    Motif : `BA <imm32>` (`mov edx, imm32` = le 2e argument x64 Windows) immediatement suivi de
    `E8 <rel32>` dont la cible est UNE DES surcharges de `$$On`. On ne reconnait donc un immediat
    QUE s'il alimente reellement un de ces appels-la.

    `vas_on` est un ENSEMBLE, pas une adresse : les trois surcharges portent le meme nom, les deux
    `On(EventTriggerType, bool)` prennent bien le `triggerType` en `edx`, et la troisieme
    (`On(params int[])`) recoit un POINTEUR de tableau -- elle ne peut donc pas produire de faux
    positif sur ce motif, et l'exclure de l'ensemble nous ferait rater un jour ou le codegen change
    de surcharge (ce qui est exactement ce qui est arrive entre `rnca9r7q6c` et `t6dpr4k06g`)."""
    cibles = {int(v) for v in vas_on}
    out = []
    i = 0
    while i + 10 <= len(blob):
        if blob[i] == 0xBA and blob[i + 5] == 0xE8:
            rel = struct.unpack_from("<i", blob, i + 6)[0]
            if va + i + 10 + rel in cibles:
                out.append(struct.unpack_from("<I", blob, i + 1)[0])
                i += 10
                continue
        i += 1
    return out


def _cmp_imm8(blob: bytes) -> list:
    """Immediats des `cmp r32, imm8` (`83 /7 ib`, modrm `F8..FF` = mod 11 + reg 7) du corps.

    C'est le seul canal offline qui montre CONTRE QUOI le `switch (triggerType)` compare."""
    out = []
    i = 0
    while i + 3 <= len(blob):
        if blob[i] == 0x83 and 0xF8 <= blob[i + 1] <= 0xFF:
            out.append(blob[i + 2])
            i += 3
        else:
            i += 1
    return out


def _wd_binaire():
    build = _build_hash()
    if build is None:
        pytest.skip("aucun build avec table `ghidra/functions.tsv` ET GameAssembly.dll installee")
    dll = PE.chemin_dll(build)                 # meme foyer que `_build_hash` (#10026-r1)
    return build, dll


def test_le_decodeur_d_appels_On_n_est_PAS_aveugle():
    """LE CRAN SOUS LE CRAN (#10026) -- il n'a pas besoin de la DLL, et c'est le point.

    Le test binaire ci-dessous conclut `UnitDeath` INATTEIGNABLE de l'ABSENCE de l'immediat `0`
    parmi les `On(x)` lus. Une telle conclusion ne vaut que si le lecteur SAIT voir ce qu'il
    cherche -- or il a passe une migration de build entiere a ne rien voir du tout, sauve par sa
    seule garde d'anti-vacuite. On exerce donc le decodeur sur des octets FABRIQUES, dont on
    connait la reponse, sur les quatre regimes qui comptent :

      1. il rend les deux immediats attendus meme quand ils visent des surcharges DIFFERENTES ;
      2. il VOIT un `On(UnitDeath = 0)` -- le regime que le test binaire declare absent ;
      3. il IGNORE un `mov edx, imm32 ; call <autre chose>` (pas de faux positif) ;
      4. `_va_of` REFUSE un nom partage au lieu d'en choisir un au hasard (la cause racine).
    """
    va = IMAGE_BASE
    on_a, on_b, on_c = va + 0x1000, va + 0x2000, va + 0x3000
    famille = {on_a, on_b, on_c}

    def _call_on(pos, imm, cible):
        rel = (cible - (va + pos + 10)) & 0xFFFFFFFF
        return struct.pack("<BI", 0xBA, imm) + struct.pack("<BI", 0xE8, rel)

    # 1. deux surcharges DIFFERENTES, deux immediats
    blob = _call_on(0, 0x36, on_b) + b"\x90" * 6 + _call_on(16, 0x3b, on_a) + b"\x90" * 6
    assert _on_immediates(blob, va, famille) == [0x36, 0x3b]
    # 2. un `On(UnitDeath)` fabrique DOIT etre vu -- sinon le verdict DEAD est vacu
    blob2 = blob + b"\x90" * 6 + _call_on(len(blob) + 6, int(EventTriggerType.UnitDeath), on_c)
    assert _on_immediates(blob2, va, famille) == [0x36, 0x3b, int(EventTriggerType.UnitDeath)]
    # 3. un appel HORS famille ne produit rien
    assert _on_immediates(_call_on(0, 0x36, va + 0x9999), va, famille) == []
    # 4. la cause racine : un nom PARTAGE ne rend plus une VA arbitraire
    build = _build_hash()
    if build is not None:
        with pytest.raises(AssertionError):
            _va_of(build, "IdunBattleLogic.Entities.DSLTriggers$$On")
        assert len(_vas_of(build, "IdunBattleLogic.Entities.DSLTriggers$$On")) >= 2, (
            "`$$On` n'a plus qu'une VA dans ce build : le regime qui a casse ce fichier a "
            "disparu -- re-lire `_vas_of` avant de simplifier quoi que ce soit")


def test_binaire_CreateTrigger_n_abonne_QUE_UnitDefeated_et_UnitBecameTargetable():
    """LE FAIT PORTEUR DU VERDICT DEAD, re-derive AUX OCTETS.

    `BaseTriggeredAbility$$GetEventTriggers` construit la liste des evenements abonnes en visitant
    l'arbre de `$$CreateTrigger`, et `EvaluateTriggerOperation$$EvaluateAbilityTrigger` passe
    l'evenement COURANT a `$$CreateBehaviour`. Donc : ce que `$$On` recoit ICI est exactement
    l'ensemble des `triggerType` possibles. `UnitDeath` n'y etant pas, la branche `== 0` du
    `switch` est INATTEIGNABLE -- et ce test rougira le jour ou un build la rebranche.

    SKIP (un seul, ce fichier a beaucoup d'autres tests) si le binaire n'est pas installe : ce
    n'est pas une entree versionnee."""
    build, dll = _wd_binaire()
    if not dll.exists():
        pytest.skip(f"GameAssembly.dll du build {build} non installee ({dll})")
    pref = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility$$"
    va_trigger = _va_of(build, pref + "CreateTrigger")
    va_other = _va_of(build, pref + "GetOtherTargets")     # le symbole SUIVANT -> borne de fenetre
    # ⚠ FAMILLE, pas adresse : `$$On` est SURCHARGE (cf. `_vas_of`). Prendre la premiere VA rendait
    # `imms == []` sur ce build, donc un rouge qui accusait le motif de decodage au lieu du port.
    vas_on = _vas_of(build, "IdunBattleLogic.Entities.DSLTriggers$$On")
    assert None not in (va_trigger, va_other) and vas_on, (
        f"symbole manquant dans la table du build {build} : "
        f"trigger={va_trigger} other={va_other} on={[hex(v) for v in vas_on]}")
    fenetre = va_other - va_trigger
    assert 0x40 <= fenetre <= 0x400, (
        f"fenetre de lecture aberrante ({fenetre:#x}) : `$$GetOtherTargets` ne suit plus "
        "`$$CreateTrigger` -- re-deriver les bornes avant de conclure")
    blob = _read_at_va(dll, va_trigger, fenetre)
    assert blob, "lecture PE impossible (traduction RVA -> offset fichier)"
    imms = _on_immediates(blob, va_trigger, vas_on)
    assert imms, (
        "AUCUN appel a `DSLTriggers$$On` reconnu dans `$$CreateTrigger` : le motif "
        f"`mov edx, imm32 ; call On` a change (surcharges cherchees : {[hex(v) for v in vas_on]}) "
        "-> l'assertion suivante serait VACUE")
    assert sorted(imms) == sorted([int(EventTriggerType.UnitDefeated),
                                   int(EventTriggerType.UnitBecameTargetable)]), (
        f"`$$CreateTrigger` abonne desormais {sorted(imms)} "
        f"(attendu {sorted([int(EventTriggerType.UnitDefeated), int(EventTriggerType.UnitBecameTargetable)])})")
    assert int(EventTriggerType.UnitDeath) not in imms, (
        "`On(UnitDeath)` est REVENU dans `$$CreateTrigger` : la branche `triggerType == 0` du "
        "`switch` de `$$CreateBehaviour` redevient VIVANTE -> porter `b__0` "
        "(`WrathfulDevotionKilled_Visual`) et retirer le verdict DEAD de la RE")


def test_binaire_CreateBehaviour_compare_a_UnitBecameTargetable_et_JAMAIS_a_UnitDefeated():
    """Le SECOND cran du verdict : le `switch (triggerType)` teste `0x3b` par un `cmp r32, imm8`
    et `0` par un `test r32, r32` -- il ne teste JAMAIS `0x36`. C'est ce qui fait tomber la face A
    dans la branche `default` (le bouclier SEUL), et c'est exactement ce que le port porte."""
    build, dll = _wd_binaire()
    if not dll.exists():
        pytest.skip(f"GameAssembly.dll du build {build} non installee ({dll})")
    pref = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility$$"
    va_beh = _va_of(build, pref + "CreateBehaviour")
    va_next = _va_of(build, pref + "CreateTrigger")        # le symbole SUIVANT dans le binaire
    assert None not in (va_beh, va_next)
    fenetre = va_next - va_beh
    assert 0x100 <= fenetre <= 0x600, f"fenetre aberrante ({fenetre:#x}) -- re-deriver les bornes"
    imms = _cmp_imm8(_read_at_va(dll, va_beh, fenetre))
    assert imms, "aucun `cmp r32, imm8` dans `$$CreateBehaviour` -- l'assertion serait VACUE"
    assert int(EventTriggerType.UnitBecameTargetable) in imms, (
        f"`$$CreateBehaviour` ne compare plus a 0x3b (`cmp` lus : {[hex(i) for i in imms]})")
    assert int(EventTriggerType.UnitDefeated) not in imms, (
        f"`$$CreateBehaviour` compare desormais a 0x36 (`UnitDefeated`) : le `switch` a ete "
        f"CORRIGE en amont, la face A ne tombe plus en `default` -- re-lire la RE "
        f"(`cmp` lus : {[hex(i) for i in imms]})")


def test_binaire_chaque_lambda_porte_SON_visuel():
    """L'APPARIEMENT branche <-> marqueur, aux octets : `b__0` (branche `UnitDeath`, MORTE) porte
    l'immediat `0x517` et pas `0x518` ; `b__1` (branche `UnitBecameTargetable`, VIVANTE) l'inverse.

    C'est ce qui interdit de croire que le port a << oublie >> un marqueur : les deux existent, ils
    sont dans DEUX lambdas distincts, et un seul des deux lambdas est atteignable."""
    build, dll = _wd_binaire()
    if not dll.exists():
        pytest.skip(f"GameAssembly.dll du build {build} non installee ({dll})")
    pref = ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility."
            "u003Cu003Ec__DisplayClass1_0$$u003CCreateBehaviouru003E")
    va0 = _va_of(build, pref + "b__0")
    va1 = _va_of(build, pref + "b__1")
    assert None not in (va0, va1), f"lambdas introuvables dans la table du build {build}"
    fenetre = abs(va1 - va0)
    assert 0x80 <= fenetre <= 0x400, f"fenetre aberrante ({fenetre:#x}) -- re-deriver les bornes"
    b0 = _read_at_va(dll, va0, fenetre)
    b1 = _read_at_va(dll, va1, fenetre)
    m_killed = struct.pack("<I", WD.KILLED_VISUAL_DEAD)      # 0x517
    m_teleported = struct.pack("<I", WD.TELEPORTED_VISUAL)   # 0x518
    assert m_killed in b0 and m_teleported not in b0, (
        "`b__0` ne porte plus le seul `WrathfulDevotionKilled_Visual` -- l'appariement "
        "branche <-> marqueur a change, re-lire `$$CreateBehaviour`")
    assert m_teleported in b1 and m_killed not in b1, (
        "`b__1` ne porte plus le seul `WrathfulDevotionTeleported_Visual` -- meme conclusion")
