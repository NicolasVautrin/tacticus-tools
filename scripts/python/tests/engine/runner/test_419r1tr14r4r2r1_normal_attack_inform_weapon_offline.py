"""#419-r1-tr14-r4-r2-r1 -- GARDE du chemin ATTAQUE NORMALE d'`InformWeapon`.

CE QUE CE FICHIER VERROUILLE, ET POURQUOI IL EST OFFLINE

Le noeud `InformWeapon` etait porte (#419-r1-tr14-r4-r2) mais AUCUNE attaque normale ne le
jouait, alors que le flux natif porte ses tags sur CHAQUE attaque normale -- mesure du
2026-08-06, MC1_67 : deux attaques, quatre lignes `Tag=Attack_Weapon_*`. Le vert de
`probe_477r15a_stream_conformance.py` ne pouvait pas le dire : ce probe ne compare QUE le groupe
racine `System_GameSetup`, et ces lignes vivent dans `Group=Ability_Power ...
Source=Loki_NormalAttack`. C'etait un TROU DE PERIMETRE, pas un accord.

Les faits de RE qui rendent ce port actionnable se periment en silence -- d'ou ce fichier :

  * `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteInformWeapon`
    a **9** appelants, tous des `<X>_NormalAttackAbility`. Sept passent `useSpecial = 0` ; **deux**
    passent `1`, chacun dans une branche gardee (etage 1).
  * son `isMelee` n'est PAS un litteral : il est DERIVE par
    `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(weapon, useSpecial)` --
    `damageProfileType = Nullable(weapon->{+0x10})`, `isMelee = WeaponProfile.get_IsMelee(weapon)`.
    La MEME unite rend donc `IsMelee=1` au contact et `IsMelee=0` a distance (etage 3).
  * la troisieme cle est CONDITIONNELLE (etage 4) : la poser a `0` ajouterait une ligne au flux.

CE QUE CE FICHIER NE COUVRE PAS -- confrontation live :
`probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[3]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))


# =============================================================================================
# ETAGE 1 -- les NEUF appelants d'`ExecuteInformWeapon` et leur litteral `useSpecial`
# =============================================================================================

#: LU au decompile le 2026-08-06 (build `rnca9r7q6c`, ghidra-mcp), appelant par appelant. La
#: valeur est le 4e argument (`useSpecial`) du call-site ; `1` s'ecrit `CONCAT71(..., 1)`.
#: `garde` NOMME la condition sous laquelle le site est atteint -- `None` = inconditionnel dans
#: sa fonction.
USE_SPECIAL_PAR_APPELANT = {
    "ALoki_NormalAttackAbility$$ExecuteBehaviour": (0, None),
    "ProperKilly_NormalAttackAbility$$ExecuteBehaviour": (0, "WeaponProfile.get_IsMelee(weapon)"),
    "RighteousRepugnance_NormalAttackAbility$$ExecuteRighteousRepugnance": (0, None),
    "TalonOfHorus_NormalAttackAbility$$ExecuteTalonOfHorus": (0, None),
    "Boltstorm_NormalAttackAbility$$ExecuteBehaviour": (0, None),
    "Boltstorm_NormalAttackAbility$$ExecuteBoltstorm": (0, None),
    "Fealty_NormalAttackAbility$$ExecuteFealty": (0, None),
    # Les DEUX seuls sites du binaire qui posent `Attack_Weapon_Use_Special` par cette voie.
    "FeederTendrils_NormalAttackAbility$$ExecuteBehaviour": (1, "DSLTriggers$$IsCharging(caster)"),
    "OptimizedGait_NormalAttackAbility$$ExecuteBehaviour": (1, "HasEffect(caster, 0x4e2)"),
}


def test_etage1_les_neuf_appelants_sont_lus_et_deux_posent_use_special():
    """Le CHIFFRE, fige. Le residu parent annoncait « 6 xrefs NON LUES » et pariait sur
    « aucune ne pose 1 » : c'est FAUX, deux la posent. Ce test existe pour que la correction ne
    se reperde pas -- et il assertionne son propre NON-VIDE, faute de quoi une table videe
    passerait pour verte."""
    assert len(USE_SPECIAL_PAR_APPELANT) == 9, "les 9 xrefs d'ExecuteInformWeapon"
    poseurs = sorted(n for n, (v, _) in USE_SPECIAL_PAR_APPELANT.items() if v)
    assert poseurs == ["FeederTendrils_NormalAttackAbility$$ExecuteBehaviour",
                       "OptimizedGait_NormalAttackAbility$$ExecuteBehaviour"], (
        "les DEUX seuls appelants a `useSpecial = 1`, lus au decompile")
    # Les deux sont GARDES : aucun ne pose la cle inconditionnellement.
    for nom in poseurs:
        assert USE_SPECIAL_PAR_APPELANT[nom][1], "%s doit porter sa garde nommee" % nom


def test_etage1_le_gate_useSpecial_porte_exige_LES_DEUX_termes():
    """`(charging & isMelee) == 0` -> branche generique. Le second terme est
    `WeaponProfile.get_IsMelee(weapon)`, PAS un second predicat de charge : le lire comme un
    `IsCharging` seul poserait la cle sur un TIR de charge, que le natif ne pose pas.

    Sur ce gate-ci, le foyer ne repond `1` que pour `FeederTendrils_NormalAttack`.
    `OptimizedGait_NormalAttack` (l'autre poseur natif) est porte depuis #419-r1-tr14-r4-r2-r1-r2 --
    son ANCRE est le CASTER -- mais par un gate d'EFFET, jamais par la charge : c'est ce que la
    derniere boucle verifie (aucun etat de charge ne le fait repondre `1`)."""
    from engine.services.custom_normal_attack import inform_weapon_use_special
    assert inform_weapon_use_special("FeederTendrils_NormalAttack", True, True) is True
    assert inform_weapon_use_special("FeederTendrils_NormalAttack", True, False) is False
    assert inform_weapon_use_special("FeederTendrils_NormalAttack", False, True) is False
    assert inform_weapon_use_special("FeederTendrils_NormalAttack", False, False) is False
    # les sept autres appelants, et le repli generique : litteral `0`, quel que soit l'etat.
    # `OptimizedGait_NormalAttack` y figure a DESSEIN : la CHARGE ne doit rien lui faire poser,
    # meme depuis que son propre gate (l'EFFET sur le caster) est porte.
    for nom in (None, "Loki_NormalAttack", "Boltstorm_NormalAttack",
                "OptimizedGait_NormalAttack"):
        assert inform_weapon_use_special(nom, True, True) is False, nom


# =============================================================================================
# ETAGE 2 -- la DERIVATION depuis l'arme (`DSLBehaviors$$InformWeapon(weapon, useSpecial)`)
# =============================================================================================

def test_etage2_from_weapon_derive_profil_et_is_melee_de_larme():
    from engine.runner.abilities.behaviours.combat import InformWeapon
    from engine.services.battle_query import weapon_is_melee
    from engine.streams.tag_key import TagKey

    # `Range is None` -> melee ; `Range >= 2` -> distance. Le seuil est `< 2`, LU dans
    # `IdunShared.Battle.WeaponProfile$$get_IsMelee`.
    melee = {"DamageProfile": "Power", "Range": None}
    ranged = {"DamageProfile": "Physical", "Range": 3}
    assert weapon_is_melee(melee) is True and weapon_is_melee(ranged) is False

    tm = InformWeapon.from_weapon(melee).tags()
    tr = InformWeapon.from_weapon(ranged).tags()
    assert tm[TagKey.Attack_Weapon_IsMelee] == 1
    assert tr[TagKey.Attack_Weapon_IsMelee] == 0
    assert tm[TagKey.Attack_Weapon_DamageProfile] == 14      # DamageProfileType.Power
    assert tr[TagKey.Attack_Weapon_DamageProfile] == 0       # DamageProfileType.Physical


def test_etage2_from_weapon_leve_sur_arme_nulle_comme_le_natif():
    """Le natif fait `FUN_1801f51f0()` (NullReferenceException) : le gate `weapon == null` vit en
    AMONT, dans `ExecuteBehaviour`. Rendre `-1` en silence masquerait un gate saute."""
    from engine.runner.abilities.behaviours.combat import InformWeapon
    with pytest.raises(ValueError):
        InformWeapon.from_weapon(None)


def test_etage2_le_seuil_de_get_IsMelee_est_bien_STRICTEMENT_INFERIEUR_A_2():
    """`Range == 1` est encore de la MELEE pour le natif (`local_res8[0] < 2`). Un port qui
    testerait `Range is None` seul rangerait cette arme en DISTANCE et ecrirait `IsMelee=0`."""
    from engine.runner.abilities.behaviours.combat import InformWeapon
    from engine.streams.tag_key import TagKey
    for portee, attendu in ((None, 1), (0, 1), (1, 1), (2, 0), (3, 0)):
        t = InformWeapon.from_weapon({"DamageProfile": "Physical", "Range": portee}).tags()
        assert t[TagKey.Attack_Weapon_IsMelee] == attendu, "Range=%r" % portee


# =============================================================================================
# ETAGE 3 -- le CABLAGE, EXECUTE : une vraie attaque normale pose les tags
# =============================================================================================
#
# ⚠ POURQUOI EXECUTER PLUTOT QUE GREPPER. Une empreinte de PRESENCE ne distingue pas « pas encore
# cable » de « cable et casse » (le vice mesure par #426 sur `test_411`). Ce bloc monte un ECS
# reel et joue `AttackDamageOperation.execute`, exactement comme le runner.

_ATTAQUANT = "admecDestroyer"     # DEUX armes : Flame (melee) et Physical (Range 3)
_CIBLE = "astraBullgryn"
_HP = 10 ** 7
_COLS = _ROWS = 9


def _board():
    import hexgeo
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(_COLS):
        for row in range(_ROWS):
            nb = [c * _ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < _COLS and 0 <= r < _ROWS]
            tiles.append({"id": col * _ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _scene(cible_pos, attaquant=None, charge: bool = False):
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import StatType, UnitStats
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.state import State

    st = State()
    st.effects = EffectsState.seed({})
    st.rng = IntBasedMersenneTwister(777)
    st.board = _board()

    def _unit(vid, pos, team):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=(3 if team == 1 else 4)))
        e.add_component(PositionComponent(col=pos[0], row=pos[1]))
        e.add_component(HealthComponent(hp=_HP, hp_max=_HP))
        stats = UnitStats()
        stats.ensure_seeded(StatType.ATTACK, 100)
        stats.ensure_seeded(StatType.EXTRA_HITS, 0)
        for s in (StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE, StatType.FIXED_ARMOR,
                  StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE):
            stats.ensure_seeded(s, 0)
        e.add_component(StatsComponent(ctx=UnitContext(
            entity_id=e.id, visual_id=vid, active_ability_level=50, passive_ability_level=50,
            ability_variables_multiplier=100, stats=stats)))
        return e.id

    att = _unit(attaquant or _ATTAQUANT, (4, 4), 2)
    tgt = _unit(_CIBLE, cible_pos, 1)
    if charge:
        # `UnitComponent.ChargedUnitIds@+0x190` -- la liste que `MoveUnitOperation$$UpdateCharging`
        # remplit des unites NOUVELLEMENT adjacentes du pas. La poser directement est le montage
        # ECRIT de l'etat « a charge cette cible ce tour ».
        from engine.runner.components import UnitComponent
        st.get_entity(att).get_component(UnitComponent).charged_unit_ids = [tgt]
    return st, att, tgt


def _attaque(cible_pos, attaquant=None, charge: bool = False) -> dict:
    from engine.runner.operations.damage import AttackDamageOperation
    st, att, tgt = _scene(cible_pos, attaquant, charge)
    r = AttackDamageOperation.execute(st, att, tgt)
    assert r is not None, "montage incomplet : l'attaque normale n'a pas tourne"
    return r


def test_etage3_une_attaque_normale_POSE_les_tags():
    from engine.streams.tag_key import TagKey
    r = _attaque((4, 3))                       # voisin hex evenq de (4,4) -> CONTACT
    tags = r.get("inform_weapon_tags")
    assert tags, ("le chemin ATTAQUE NORMALE ne pose AUCUN tag `Attack_Weapon_*` -- c'est "
                  "exactement le residu #419-r1-tr14-r4-r2-r1")
    assert set(tags) == {int(TagKey.Attack_Weapon_DamageProfile),
                         int(TagKey.Attack_Weapon_IsMelee)}, (
        "DEUX cles, jamais trois : `useSpecial = 0` sur ce foyer -- lu %r" % (dict(tags),))


def test_etage3_le_DISCRIMINANT_la_meme_unite_change_de_IsMelee_avec_la_distance():
    """ANTI-REGIME-DEGENERE, et c'est le coeur du port : `isMelee` est DERIVE de l'arme que
    `GetAttackWeaponForDefaultNormalAttack` a choisie, donc de la DISTANCE. Une constante
    passerait le test precedent et echouerait celui-ci."""
    from engine.streams.tag_key import TagKey
    contact = _attaque((4, 3))["inform_weapon_tags"]
    loin = _attaque((4, 7))["inform_weapon_tags"]        # distance hex 3 <= Range 3
    assert contact[TagKey.Attack_Weapon_IsMelee] == 1, dict(contact)
    assert loin[TagKey.Attack_Weapon_IsMelee] == 0, dict(loin)
    assert (contact[TagKey.Attack_Weapon_DamageProfile]
            != loin[TagKey.Attack_Weapon_DamageProfile]), (
        "le TEMOIN du temoin : les deux armes doivent aussi differer de PROFIL, sinon seul un "
        "des deux tags est exerce -- lu %r vs %r" % (dict(contact), dict(loin)))
    # Recoupement avec le canal `ranged` que l'attaque publie deja : les deux doivent s'accorder.
    assert bool(_attaque((4, 3))["ranged"]) is False
    assert bool(_attaque((4, 7))["ranged"]) is True


def test_etage3_le_gate_darme_precede_la_pose_des_tags():
    """`if (weapon == null) return default;` -- NI `ExecuteInformWeapon`, NI `ExecuteNormalAttack`.
    Une cible hors de portee de l'arme distance et non adjacente ne rend AUCUNE arme."""
    import hexgeo
    from engine.runner.operations.damage import AttackDamageOperation
    hors = (4, 8)                              # DANS le board 9x9 -- sinon l'attaque echouerait
    assert hexgeo.distance((4, 4), hors) == 4, "montage : la cible doit etre a 4 > Range 3"
    st, att, tgt = _scene(hors)
    assert AttackDamageOperation.execute(st, att, tgt) is None, (
        "sans arme utilisable le natif NO-OPE : ni tags, ni degat")


# =============================================================================================
# ETAGE 4 -- la cle CONDITIONNELLE
# =============================================================================================

_DEATHLEAPER = "tyranDeathleaper"        # passif `FeederTendrils` -> `FeederTendrils_NormalAttack`


def test_etage3_useSpecial_EXECUTE_deathleaper_en_charge_pose_la_cle():
    """LE CRAN QUE SEULE L'EXECUTION VOIT : la cle n'est posee que si le foyer sait, DANS l'ECS,
    (a) que l'attaque normale de l'entite est `FeederTendrils_NormalAttack` -- ce qui passe par la
    cascade `custom_normal_attack` -- et (b) qu'elle a CHARGE cette cible. Le natif ecrit alors
    `Tag=Attack_Weapon_Use_Special:1` (MESURE live du 2026-08-06, `tyranDeathleaper` sur MC1_67).

    Les deux bras temoins isolent chacun un terme : sans charge, et sur une autre unite."""
    from engine.streams.tag_key import TagKey
    charge = _attaque((4, 3), attaquant=_DEATHLEAPER, charge=True)["inform_weapon_tags"]
    assert charge.get(TagKey.Attack_Weapon_Use_Special) == 1, dict(charge)
    # profil `Bio` = 22, mesure dans le flux natif du meme montage.
    assert charge[TagKey.Attack_Weapon_DamageProfile] == 22, dict(charge)

    sans = _attaque((4, 3), attaquant=_DEATHLEAPER, charge=False)["inform_weapon_tags"]
    assert TagKey.Attack_Weapon_Use_Special not in sans, (
        "sans charge, le natif prend la branche generique (`useSpecial = 0`) -- %r" % (dict(sans),))
    autre = _attaque((4, 3), charge=True)["inform_weapon_tags"]
    assert TagKey.Attack_Weapon_Use_Special not in autre, (
        "une unite SANS `FeederTendrils` ne pose jamais la cle, meme en charge -- %r"
        % (dict(autre),))


def test_etage4_use_special_est_absente_a_zero_et_presente_a_un():
    from engine.runner.abilities.behaviours.combat import InformWeapon
    from engine.streams.inform_ops import get_inform_weapon_tags
    from engine.streams.tag_key import TagKey
    w = {"DamageProfile": "Power", "Range": None}
    assert TagKey.Attack_Weapon_Use_Special not in InformWeapon.from_weapon(w).tags()
    t1 = InformWeapon.from_weapon(w, use_special=True).tags()
    assert t1[TagKey.Attack_Weapon_Use_Special] == 1
    # Le foyer PARTAGE se comporte pareil (une seconde table divergerait en silence).
    assert TagKey.Attack_Weapon_Use_Special not in get_inform_weapon_tags(0, False, False)
    assert get_inform_weapon_tags(0, False, True)[TagKey.Attack_Weapon_Use_Special] == 1


def test_etage4_le_noeud_DSL_et_la_face_STREAM_partagent_le_MEME_foyer():
    """Le vice qu'interdit ce test : deux tables de cles, l'une dans le noeud, l'autre dans
    l'Operation, qui divergent sans que rien ne le dise."""
    import inspect
    from engine.runner.abilities.behaviours.combat import InformWeapon
    src = inspect.getsource(InformWeapon.tags)
    assert "get_inform_weapon_tags" in src, (
        "`InformWeapon.tags` doit DELEGUER au foyer `engine.streams.inform_ops`")


# =============================================================================================
# ETAGE 5 -- la face STREAM : `InformOperation$$Execute` ECRIT bien la ligne
# =============================================================================================

def test_etage5_inform_ecrit_action_Info_sur_NO_ENTITY():
    """`Events.Action(StepType.Info, 0 /*NO_ENTITY*/, tags)`. La forme exacte est MESUREE dans le
    flux natif de MC1_67 (2026-08-06) :

        Action=Info Entity=NO_ENTITY
            Tag=Attack_Weapon_IsMelee:1
            Tag=Attack_Weapon_DamageProfile:14
    """
    from engine.runner.abilities.behaviours.combat import InformWeapon
    from engine.streams import StreamCache, StreamDispatcher
    from engine.streams.group_type import GroupType
    from engine.streams.inform_ops import inform

    lignes = []

    class _Capture:
        def on_root_group_finished(self, group):
            lignes.append(group)

        def on_log(self, chunk):
            pass

    cache = StreamCache()
    cache.add_listener(_Capture())
    events = StreamDispatcher()
    events.subscribe(cache)
    events.start_group(int(GroupType.Ability_Power), 83, "Loki_NormalAttack", 77)
    inform(events, InformWeapon.from_weapon({"DamageProfile": "Power", "Range": None}).tags())
    events.finish_group()

    assert len(lignes) == 1, "un seul groupe racine flushe"
    texte = lignes[0]
    assert "Action=Info Entity=NO_ENTITY" in texte, texte
    assert "Tag=Attack_Weapon_IsMelee:1" in texte, texte
    assert "Tag=Attack_Weapon_DamageProfile:14" in texte, texte
    assert "Attack_Weapon_Use_Special" not in texte, (
        "la cle conditionnelle ne doit PAS apparaitre a `useSpecial = 0`")
    # L'ordre d'ECRITURE est celui des ORDINAUX (0x92 avant 0x93), pas celui de l'insertion.
    assert texte.index("Attack_Weapon_IsMelee") < texte.index("Attack_Weapon_DamageProfile"), texte


# =============================================================================================
# ETAGE 6 -- les ORDINAUX ecrits au site, figes (le registre `probe_313` ne les voit pas)
# =============================================================================================

def test_etage6_les_trois_TagKey_gardent_leur_ordinal_mesure():
    """`probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE dans le flux, elle, a change. Ce test fige
    ce que la mesure live du 2026-08-06 a observe."""
    from engine.streams.step_type import StepType
    from engine.streams.tag_key import TagKey
    assert int(TagKey.Attack_Weapon_IsMelee) == 0x92
    assert int(TagKey.Attack_Weapon_DamageProfile) == 0x93
    assert int(TagKey.Attack_Weapon_Use_Special) == 0x94
    assert int(StepType.Info) == 0x1d


def test_etage6_AUCUNE_arme_du_catalogue_ne_fait_LEVER_la_derivation():
    """LA REGRESSION QUE CE TEST INTERDIT EST UN CRASH, pas une divergence de valeur.
    `InformWeapon.tags` convertit le NOM de profil par `_PROFILE_INDEX_BY_NAME[...]` -- un
    `KeyError` volontaire, pour qu'un profil inconnu ne parte pas en `-1` muet. Le prix de ce
    choix : un profil present au gameconfig et ABSENT de l'enum ferait planter TOUTE attaque
    normale de son porteur, puisque la derivation est desormais sur le chemin.

    Mesure du 2026-08-06 : **683** unites, **933** armes, **20** profils distincts, **0** absent,
    **0** levee. Le balayage est re-derive a chaque run -- il n'est pas fige."""
    import gameconfig as GC
    from engine.runner.abilities.behaviours.combat import InformWeapon
    ids = [u for _k, v in GC.all_unit_ids().items() for u in v]
    assert len(ids) > 100, "le catalogue doit etre charge (temoin de non-vide)"
    armes = leves = 0
    for uid in ids:
        for w in ((GC.unit(uid) or {}).get("weapons") or []):
            armes += 1
            try:
                InformWeapon.from_weapon(w).tags()
            except Exception:                                    # noqa: BLE001 -- on COMPTE
                leves += 1
    assert armes > 500, "temoin de non-vide : %d arme(s) balayee(s)" % armes
    assert leves == 0, "%d arme(s) sur %d font LEVER la derivation" % (leves, armes)


def test_etage6_le_profil_vide_secrit_None_et_vaut_moins_un():
    from engine.entities.damage_profile_type import DamageProfileType
    from engine.streams.inform_ops import get_inform_weapon_tags
    from engine.streams.tag_key import TagKey
    assert int(DamageProfileType.None_) == -1
    t = get_inform_weapon_tags(None, False, False)
    assert t[TagKey.Attack_Weapon_DamageProfile] == -1
