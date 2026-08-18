"""#895-r4 volet (a) -- la PHASE 2 de `NovaShield` (1194 -> triggered 1325), OFFLINE.

CE QUE CE FICHIER DISCRIMINE, et ce qu'il ne discrimine pas.

Le port de `...Triggered.Loki.NovaShield_AttackAbility$$CreateBehaviour` n'a PAS pu etre confronte
LIVE dans sa tranche de livraison : le budget de runners du host etait sature (50/50) de bout en
bout. Ce fichier est donc ce qui tient a sa place -- et il ne pretend pas etre l'equivalent :

  * il EXECUTE la chaine complete sur un etat monte a la main (cast de la phase 1, bascule de tour,
    `Triggered()` d'`APendingAttackEffect`, phase 2), donc il voit un no-op silencieux ;
  * il ne peut PAS confronter le MONTANT au natif -- aucune valeur native n'est disponible offline.
    Ce qui est confronte, c'est la STRUCTURE (l'arbre lu) et le COMPORTEMENT (qui est frappe, quelle
    marque disparait), jamais un scalaire.

ETAGES
------
  E0  le CABLAGE : `TRIGGERED_ABILITY_BEHAVIOURS[1325]`, `PENDING_ATTACK_EFFECTS[1414]` et son
      inscription DERIVEE dans `EFFECT_TRIGGERS`.
  E1  la FORME de l'arbre, arg par arg -- `op_and(rm, atk)` SANS `AtomicGroup`, le `Cache` PARTAGE
      entre les deux membres, et l'`abilityOrEffect` = l'ACTIVE 1194.
  E2  l'EXECUTION : la marque `1415` vit sur des TUILES et est relue AU TIR -- l'unite qui SORT y
      echappe, celle qui ENTRE la prend. Un port qui figerait les cibles AU CAST frapperait
      exactement l'inverse.
  E3  CONTRE-EPREUVES par MUTATION, chacune vue ROUGE : l'ordre `rm & atk` inverse (le `Cache`
      cesse de proteger), et le retrait de l'entree de `PENDING_ATTACK_EFFECTS` (la phase 2 ne part
      plus du tout).
  E4  TEMOIN NEGATIF : au tour de l'ADVERSE, rien ne part et la marque reste.

Sorties ASCII. Aucun runner, aucun RPC.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402
from engine.entities.effect_type import EffectType                  # noqa: E402
from engine.entities.pathfinding.board import Board                 # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.effects_state import EffectsState              # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister              # noqa: E402
from engine.runner.snapshot import load_state                       # noqa: E402

NOVA_SHIELD = int(ActiveAbilityType.NovaShield)                   # 0x4aa = 1194
NS_ATTACK = int(TriggeredAbilityType.NovaShield_Attack)           # 0x52d = 1325
NS_PENDING_TARGET = int(EffectType.NovaShield_PendingTarget)      # 0x587 = 1415
NS_PENDING_ATTACK = int(EffectType.NovaShield_PendingAttack)      # 0x586 = 1414

COLS = ROWS = 11
CASTER, PLAYER_MOI, PLAYER_ADV = 10, 3, 4
CASTER_POS = (5, 5)
#: La tuile VISEE. Le masque de 1194 est `0x6000040` (`TargetIsTile` + les deux `AllowObscured*`)
#: avec `use_whole_board` : aucune contrainte de distance, aucun `CasterHas7Tiles` -- le montage
#: n'a donc PAS besoin d'empreinte multi-hex (contraste LU avec `TheLantern`, cf.
#: `test_1030_the_lantern_offline._empreinte_7`). Le test E0b le RE-DERIVE du masque plutot que de
#: le supposer.
TARGET_POS = (5, 2)


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(foes: dict | None = None):
    """Etat runner minimal : le caster (joueur `PLAYER_MOI`) et `foes` = {uid: (col, row)}.

    ⚠ LE CANAL `triggered_abilities` EST POSE A LA MAIN, ET IL EST INDISPENSABLE. Le noeud
    `TriggerAbility` porte le gate `GetAbilityState` d'`IdunBattle.Operations.
    TriggerTriggeredAbilityOperation$$TriggerAbility` : l'unite declenchee doit PORTER l'ability
    triggered. `1325 NovaShield_Attack` est DERIVEE (`StaticBattleRules.ActiveAbility$$
    GetDerivedTriggeredAbilities`, dictionnaire peuple au RUNTIME), donc INVISIBLE du kit
    gameconfig : sans ce seed, le trigger fire et le noeud rend `dispatched: True,
    notCarrying: [caster]` -- zero degat, aucune erreur. Meme montage, meme raison que
    `test_1030_the_lantern_offline`.
    """
    units = [{"id": CASTER, "visualId": "tauBossRiptide", "alive": True, "team": 1,
              "owner": PLAYER_MOI, "pos": {"col": CASTER_POS[0], "row": CASTER_POS[1]},
              "effects": []}]
    for uid, p in sorted((foes or {}).items()):
        units.append({"id": uid, "visualId": "necroWarden", "alive": True, "team": 2,
                      "owner": PLAYER_ADV, "pos": {"col": p[0], "row": p[1]}, "effects": []})
    decision = {"currentPlayer": PLAYER_MOI, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 500000, "hpMax": 500000} for u in units]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 500000, "movement": 3, "armour": 0,
                                     "turnsStarted": 0},
                           "healthMax": 500000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    st = load_state(decision, observe, snapshot,
                    board=Board(_tiles(), adjacency="evenq"), ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    # ⚠ **LE PRNG EST OBLIGATOIRE, ET SON ABSENCE EST UN NO-OP TOTALEMENT SILENCIEUX.**
    # `AttackDamageOperation.execute_normal_like` -- la voie que prend `AttackWithAttackDamage` en
    # mode `amount` -- ouvre par `if state.rng is None: return None`. Sans cette ligne, l'arbre
    # s'execute, `AttackWithAttackDamage` est bien EMIS, les marques sont bien retirees... et
    # `total` vaut `None` : aucun PV ne bouge. Mesure faite en ecrivant ce fichier -- c'est
    # exactement la forme de no-op que ce module dit chasser, et un test qui n'aurait regarde que
    # `emis` l'aurait declare VERT.
    st.rng = IntBasedMersenneTwister(777)
    from engine.runner.components import StatsComponent
    sc = st.get_entity(CASTER).get_component(StatsComponent)
    if sc is not None and getattr(sc, "ctx", None) is not None:
        sc.ctx.triggered_abilities = [NS_ATTACK]
    return st


def _cast(st, tile_id: int):
    """La phase 1, par la voie COMPLETE (`Runner.apply`) -- gates de ciblage compris."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=CASTER, target_id=int(tile_id),
                                      ability_type=NOVA_SHIELD))
    return runner.ability_handler.last or {}


def _turn_start(st, player_id: int):
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers
    return delayed_attack_triggers(st, int(player_id))


def _marques(st) -> list:
    return sorted(t for t, effs in (st.effects.by_unit or {}).items()
                  if any(not e.consumed and int(e.effect_type) == NS_PENDING_TARGET
                         for e in effs))


def _hp(st, uid: int):
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


# =================================================================================================
# E0 -- LE CABLAGE
# =================================================================================================

def test_e0_le_cablage_des_trois_registres():
    """Un arbre porte mais non CABLE est un no-op parfaitement silencieux : les trois inscriptions
    se verifient ensemble, et la troisieme est DERIVEE de la seconde (jamais ecrite a la main)."""
    import engine.runner.operations.triggers.dispatch.registry  # noqa: F401  (effet de bord)
    from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
    from engine.runner.operations.triggers import pending_attack as PA

    assert NS_ATTACK in TRIGGERED_ABILITY_BEHAVIOURS, (
        "`TRIGGERED_ABILITY_BEHAVIOURS[%d]` absent : le `TriggerAbility` du `Triggered()` "
        "d'APendingAttackEffect ne trouvera rien a executer" % NS_ATTACK)
    spec = PA.PENDING_ATTACK_EFFECTS.get(NS_PENDING_ATTACK)
    assert spec is not None, "`PENDING_ATTACK_EFFECTS[%d]` absent" % NS_PENDING_ATTACK
    assert spec.triggered_ability == NS_ATTACK
    # `OwnerPendingAttackEffect` est GENERIQUE et PARAMETREE : le ctor lu est
    # `OwnerPendingAttackEffect(0x4aa, 0x52d)`. Il n'existe AUCUN `NovaShield*Effect` -- un
    # relecteur qui en chercherait un ne trouverait rien, d'ou cette assertion NOMMEE.
    assert spec.native == "IdunBattle.Entities.Effects.OwnerPendingAttackEffect"
    # `ATTACKER_BONDED` = le corps de la BASE (`ABondEffect$$BondedEntitySelector`). La phase 1
    # pose `AddBondEffect(0x586, ..., source = targets = bondedEntity = Owner@+0x30)`, donc les
    # TROIS lectures coincident sur ce porteur et le choix n'est PAS discriminant ici.
    assert spec.attacker == PA.ATTACKER_BONDED
    assert NS_PENDING_ATTACK in dict(PA.pending_attack_registry_entries()), (
        "l'inscription dans `EFFECT_TRIGGERS` n'est pas DERIVEE de la table")


def test_e0b_le_montage_est_dans_le_regime_qu_il_documente():
    """Le montage MONO-HEX n'est legitime que parce que le masque de 1194 ne porte PAS
    `CasterHas7Tiles` -- on le RE-DERIVE du registre au lieu de le supposer.

    Sans ce cran, un futur port du gate d'empreinte rendrait ce fichier ROUGE sans qu'on sache
    pourquoi -- c'est exactement ce qui est arrive a `test_1030_the_lantern_offline` (#10023)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    opts = ABILITY_CLASSES[NOVA_SHIELD].TARGETING_OPTIONS
    assert not (int(opts.rules) & int(TR.CasterHas7Tiles)), (
        "le masque de 1194 porte maintenant `CasterHas7Tiles` : ce montage mono-hex ne peut plus "
        "caster, il faut lui poser une empreinte SEPT HEX")
    assert int(opts.rules) & int(TR.TargetIsTile), (
        "1194 ne cible plus une TUILE : `TARGET_POS` n'est plus un id de tuile valide")


# =================================================================================================
# E1 -- LA FORME DE L'ARBRE
# =================================================================================================

def test_e1_forme_de_l_arbre():
    """`op_BitwiseAnd(rm, atk)`, SANS `AtomicGroup`, avec le `Cache` PARTAGE entre les deux membres.

    Les trois points sont LUS et chacun est load-bearing :
      * l'ORDRE (`rm` a GAUCHE) fait partir le retrait AVANT le coup ;
      * c'est le `Cache` -- le MEME objet des deux cotes -- qui empeche le second membre de lire un
        ensemble deja vide ;
      * l'absence d'`AtomicGroup` est un ECART LU avec `SolarAtomizer`, qui en pose un : recopier
        le voisin ajouterait un groupe que le natif n'a pas.
    """
    from engine.entities.behaviours import AtomicGroup, Seq
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import RemoveEffect
    from engine.runner.operations.triggers.loki import nova_shield_attack as NS

    st = _state()
    tree = NS.nova_shield_attack_tree(st, 50, 100)
    assert not isinstance(tree, AtomicGroup), (
        "un `AtomicGroup` est apparu : le natif rend l'`op_BitwiseAnd` NU (ecart lu avec "
        "`SolarAtomizer_PendingAttackAbility`, qui en pose un)")
    assert isinstance(tree, Seq), "l'arbre n'est plus un `op_BitwiseAnd`"
    rm, atk = tree.left, tree.right
    assert isinstance(rm, RemoveEffect), "le membre GAUCHE n'est pas le `RemoveEffect`"
    assert isinstance(atk, AttackWithAttackDamage), "le membre DROIT n'est pas l'attaque"
    assert int(rm.effect_type) == NS_PENDING_TARGET
    # LE MEMO : le `RemoveEffect` et l'attaque doivent viser LE MEME objet `Cache`.
    assert rm.target_sel is not None and rm.target_sel is _cache_de(atk), (
        "le `Cache` n'est pas PARTAGE entre les deux membres -- le retrait viderait l'ensemble que "
        "l'attaque doit encore lire")
    # L'ATTRIBUTION : l'ACTIVE 1194, jamais la triggered 1325 (immediat `mov edx, 0x4aa` lu aux
    # octets avant le `call AbilityOrEffect$$op_Implicit`).
    assert int(atk.ability_type) == NOVA_SHIELD, (
        "l'`abilityOrEffect` vaut %r : le natif passe l'ACTIVE 1194, et l'ordinal ne discrimine "
        "pas (1194 nomme aussi `TriggeredAbilityType.LordOfTempests`)" % (atk.ability_type,))
    assert atk.is_melee is False, "`attackRangeType` de 1194 est `Ranged`"
    assert atk.multi is True and atk.native_factory == "attack"
    # `Units(...)` S'INTERCALE entre le cache et `Enemies` -- ECRIT par le natif, pas collapse
    # (ecart LU avec `TheLantern`, qui passe le cache de TUILES directement a `Enemies`).
    assert _chaine_de_selecteurs(atk) == ["Enemies", "Units", "Cache", "EntitiesWithAnyEffect",
                                          "AllTiles"], _chaine_de_selecteurs(atk)


def _cache_de(atk):
    """Descend jusqu'au `Cache` dans `Enemies(Units(Cache(...)))` -- la FORME lue de l'arbre.

    Les trois noeuds portent le suivant sous un nom DIFFERENT (`Enemies.inner`, `Units.tiles`,
    `Cache.source`) : on les nomme tous les trois plutot que de deviner un attribut generique."""
    cur = getattr(atk, "target_sel", None)
    for _ in range(4):
        if cur is None or type(cur).__name__ == "Cache":
            return cur
        cur = next((getattr(cur, a) for a in ("inner", "tiles", "source")
                    if getattr(cur, a, None) is not None), None)
    return cur


def _chaine_de_selecteurs(atk) -> list:
    """La CHAINE de classes de `atk.target_sel`, de haut en bas -- `Units` INTERCALE compris.

    Le natif ecrit `Enemies(Caster@+0x48, Units(marked, unique = 1, 3), 3)` ; `TheLantern` passe le
    cache de TUILES directement a `Enemies`. On ECRIT l'ecart, on ne le collapse pas."""
    out, cur = [], getattr(atk, "target_sel", None)
    for _ in range(5):
        if cur is None:
            break
        out.append(type(cur).__name__)
        cur = next((getattr(cur, a) for a in ("inner", "tiles", "source")
                    if getattr(cur, a, None) is not None), None)
    return out


def test_e1b_les_deux_scalaires_viennent_du_GAMECONFIG():
    """`GetHits()` et `GetDamageProfileOrDefault(5)` lisent la config de l'ACTIVE 1194 -- la
    triggered n'a AUCUNE entree gameconfig (mesure : `GC.ability("NovaShield_Attack")` rend None).

    Le defaut `5` n'est donc jamais atteint : l'ecrire en dur serait un FIT."""
    import gameconfig as GC
    assert GC.ability("NovaShield_Attack") is None
    assert GC.ability("NovaShield_PendingAttack") is None
    consts = (GC.ability("NovaShield") or {}).get("constants") or {}
    st = _state()
    from engine.runner.operations.triggers.loki import nova_shield_attack as NS
    atk = NS.nova_shield_attack_tree(st, 50, 100).right
    assert int(atk.hits) == int(consts["nrOfHits"])
    assert str(atk.profile) == str(consts["damageProfile"])


# =================================================================================================
# E2 -- L'EXECUTION : la marque vit sur des TUILES et est relue AU TIR
# =================================================================================================

def test_e2_la_marque_est_relue_au_tir():
    """Le montage bouge DEUX unites entre le cast et le tir -- une dans chaque sens -- sur un etat
    par ailleurs identique. Un port qui figerait la liste des cibles AU CAST frapperait exactement
    l'inverse, et un port qui ne frapperait personne passerait pour << pas de degat >>."""
    from engine.runner.components import PositionComponent
    dedans, dehors = TARGET_POS, (0, 0)
    st = _state({20: dedans, 21: dehors})
    last = _cast(st, _tid(*TARGET_POS))
    assert last.get("ported") is True and "invalid_target" not in last, (
        "la phase 1 n'a pas casté (%r) : ce test mesurerait un etat vide" % (last,))
    marques = _marques(st)
    assert marques, "aucune marque 1415 posee par la phase 1 -- rien a tirer"
    st.get_entity(20).get_component(PositionComponent).col = dehors[0]
    st.get_entity(20).get_component(PositionComponent).row = dehors[1]
    st.get_entity(21).get_component(PositionComponent).col = dedans[0]
    st.get_entity(21).get_component(PositionComponent).row = dedans[1]
    hp0 = {u: _hp(st, u) for u in (20, 21)}
    fired = _turn_start(st, PLAYER_MOI)
    assert fired, "le `Triggered()` d'`APendingAttackEffect` n'a pas fire au tour du caster"
    hp1 = {u: _hp(st, u) for u in (20, 21)}
    assert hp1[20] == hp0[20], "l'unite SORTIE de la zone marquee a ete frappee"
    assert hp1[21] < hp0[21], "l'unite ENTREE dans la zone marquee n'a PAS ete frappee"
    assert not _marques(st), (
        "les marques 1415 subsistent : le `RemoveEffect` du meme arbre ne les a pas consommees")


def test_e4_temoin_negatif_rien_au_tour_adverse():
    """`IsTurnOf(GetAttackingUnitSelector())`. Sans ce cran, E2 ne distinguerait pas << fire au bon
    tour >> de << fire a tous les tours >>."""
    st = _state({20: TARGET_POS})
    _cast(st, _tid(*TARGET_POS))
    hp0 = _hp(st, 20)
    fired = _turn_start(st, PLAYER_ADV)
    assert not fired, "la phase 2 a fire au tour de l'ADVERSE"
    assert _hp(st, 20) == hp0
    assert _marques(st), "la marque a disparu alors que rien n'a tire"


# =================================================================================================
# E3 -- LES MUTANTS (chacun doit MORDRE)
# =================================================================================================

def test_e3_mutant_le_cache_n_est_plus_partage():
    """DEUX `Cache` distincts au lieu d'UN partage -- et le coup ne part plus.

    ⚠ **C'EST LE MUTANT QUI MORD, ET LE MUTANT << ORDRE INVERSE >> NE MORD PAS.** Mesure faite en
    ecrivant ce fichier : avec le memo PARTAGE, echanger les deux membres de l'`op_BitwiseAnd`
    laisse le coup partir a l'identique et n'est observable NULLE PART (les emissions sont rendues
    en ENSEMBLE trie, et le degat est le meme) -- c'est precisement ce que le `Cache` garantit.
    L'ORDRE reste donc garde par la TRANSCRIPTION (E1), qui est le bon cran pour un fait LU au
    decompile mais sans consequence observable sur ce montage ; on ne fabrique pas un faux
    discriminant pour lui.
    Ce que ce mutant-ci montre, en revanche, est le fait REEL : c'est le memo -- pas l'ordre --
    qui rend l'arbre vivable. Sans lui, le `RemoveEffect` de gauche vide l'ensemble que
    l'`EntitiesWithAnyEffect` de droite doit encore lire."""
    from engine.entities.behaviours import op_and
    from engine.entities.selectors.geometry import Cache, EntitiesWithAnyEffect
    from engine.entities.selectors.tiles import AllTiles
    from engine.entities.selectors.units import Enemies, Units
    from engine.runner.abilities.behaviours.effects import RemoveEffect
    from engine.runner.operations.triggers.loki import nova_shield_attack as NS

    orig = NS.nova_shield_attack_tree

    def _deux_caches(state, level, mult):
        """MEME arbre, mais chaque membre alloue SON cache."""
        t = orig(state, level, mult)
        atk = t.right
        atk.target_sel = Enemies(
            Units(Cache(EntitiesWithAnyEffect(AllTiles(), [NS_PENDING_TARGET])),
                  selection_type=NS._SELECTION),
            selection_type=NS._SELECTION)
        rm = RemoveEffect(NS_PENDING_TARGET,
                          Cache(EntitiesWithAnyEffect(AllTiles(), [NS_PENDING_TARGET])))
        return op_and(rm, atk)

    st_mut = _state({20: TARGET_POS})
    _cast(st_mut, _tid(*TARGET_POS))
    hp0 = _hp(st_mut, 20)
    try:
        NS.nova_shield_attack_tree = _deux_caches
        _turn_start(st_mut, PLAYER_MOI)
    finally:
        NS.nova_shield_attack_tree = orig
    assert _hp(st_mut, 20) == hp0, (
        "la mutation ne mord pas : avec DEUX caches le coup part quand meme, donc le memo ne "
        "protege rien et la garde E1 sur son partage est vide")

    st_ok = _state({20: TARGET_POS})
    _cast(st_ok, _tid(*TARGET_POS))
    hp0_ok = _hp(st_ok, 20)
    _turn_start(st_ok, PLAYER_MOI)
    assert _hp(st_ok, 20) < hp0_ok, "source restauree : le coup doit partir"


def test_e3_mutant_entree_retiree_la_phase_2_ne_part_plus():
    """Retirer `PENDING_ATTACK_EFFECTS[1414]` -- le regime AVANT ce port, et il est SILENCIEUX."""
    from engine.runner.operations.triggers import pending_attack as PA
    st = _state({20: TARGET_POS})
    _cast(st, _tid(*TARGET_POS))
    hp0 = _hp(st, 20)
    vrai = PA.PENDING_ATTACK_EFFECTS.pop(NS_PENDING_ATTACK)
    try:
        res = _turn_start(st, PLAYER_MOI)
        assert not res, "la phase 2 fire encore sans son entree de table -- la mutation ne mord pas"
        assert _hp(st, 20) == hp0, "du degat est parti sans l'entree de table"
    finally:
        PA.PENDING_ATTACK_EFFECTS[NS_PENDING_ATTACK] = vrai


def test_e3_mutant_attribution_triggered_au_lieu_d_active():
    """`ability_type = 1325` (la triggered) au lieu de `1194` (l'ACTIVE).

    ⚠ CE MUTANT NE MORD PAS SUR LES PV, ET C'EST TOUT SON PROPOS : l'axe touche est
    l'ATTRIBUTION (`Effect_Type` du degat, cle des bonus par ability), pas le total. Le seul cran
    qui puisse le voir est donc la garde de FORME (E1) -- et ce test l'EXIGE en verifiant qu'elle
    rougit. C'est aussi pourquoi le residu #895-r6 existe : deux ports voisins portent la valeur
    fausse et aucun test de PV ne pouvait le montrer."""
    import pytest
    from engine.runner.operations.triggers.loki import nova_shield_attack as NS
    vrai = NS.NS_ATTRIBUTION
    try:
        NS.NS_ATTRIBUTION = NS_ATTACK
        with pytest.raises(AssertionError):
            test_e1_forme_de_l_arbre()
    finally:
        NS.NS_ATTRIBUTION = vrai
    test_e1_forme_de_l_arbre()          # la source restauree doit repasser
