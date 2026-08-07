"""#524-r1 -- le BOND d'un effet COMPOSITE doit descendre a ses SOUS-EFFETS.

CE QUE CE FICHIER GARDE, et pourquoi il ne peut pas etre vert pour rien :

  * `test_materialisation_offline` -- a la POSE, les trois enfants de `Taunted_OnlySpecificTargets`
    portent le MEME `bonded` que leur parent. TEMOIN NON NUL exige dans le meme bras : le parent
    porte un bond NON NUL, sinon `None == None` passerait au vert sans rien prouver.
  * `test_hydratation_offline`     -- MEME exigence sur un etat RECONSTRUIT d'une capture (le
    canal par lequel un taunt arrive quand la bataille a commence avant nous). C'est un foyer
    DISTINCT (`snapshot._load_effect_parent_links`), et le rater laisserait la moitie du gisement.
  * `test_regime_degenere_nomme_offline` -- le composite `Stunned` (1162) n'est pose par AUCUN
    `AddBondEffect` du port : ses enfants ont `bonded is None` des deux cotes. Ce bras EXISTE pour
    empecher qu'on lise le vert des deux premiers comme « la propagation marche partout » : il
    NOMME le regime ou elle est inerte, et il verifie que l'heritage ne FABRIQUE pas un bond.

ARTEFACT NATIF (`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal`, build `rnca9r7q6c`) --
et c'est un CONTEXTE PARTAGE, pas une propagation recablee a la main :

    ctx = new <options>()
    ctx.<+0x10> = <abilityState lu de l'effet parent>
    ctx.<+0x18> = IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId(this, effect)   // du PARENT
    AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <25>),   0x19)
    AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <26>),   0x1a)
    AddSubEffectWithSameTurns(this, effect, target, new EffectBuilder(ctx, <1237>), 0x4d5)
    // puis la MEME valeur `ctx.<+0x18>` alimente `ForcedAttackTargetsComponent` de la cible

`IdunBattle.Entities.Effects.BaseEffect$$AddSubEffectWithSameTurns` ne transporte QUE
`{ turns = <EffectComponent du parent>.RemainingTurns, parentEffect }` : le bond arrive par
l'`EffectBuilder`, donc par le CONTEXTE. Le port a deja cette valeur (elle alimente son
`writes_forced_attack_targets`) -- il ne la passait simplement pas aux enfants.

A QUOI SERT le bond d'un enfant : `IdunBattle.Entities.Effects.Taunted_RefreshUnitTurnFinishedEffect
$$get_Range` rend `Nullable<int>(1)`, exactement comme `IdunBattle.Entities.Effects.TauntedEffect
$$get_Range`. Chaque enfant porte donc SON PROPRE gate de rupture de bond (distance au bonded),
qu'un `bonded` nul rend ininterpretable.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, pris LARGE : la pose d'un effet tire le registre d'effets, les
        # Operations et l'`EffectsState`. Foyers load-bearing pour la relecture humaine :
        # `runner/operations/effects.py` (`_spawn_sub_effects`), `runner/snapshot.py`
        # (`_load_effect_parent_links`), `entities/effects/base.py` (`SubEffectSpec`),
        # `entities/effects/loki/status.py` (`TauntedEffect`/`StunnedEffect`),
        # `entities/effects_state.py`.
        "scripts/python/engine/**/*.py",
        # LA CASCADE DES CONFTEST N'EST PLUS ICI, ET C'ETAIT LE POINT DE #531. Ces 16 modules
        # (`board`, `catalog_inject`, `engine_agreement_stages` et ses quatre probes...) etaient
        # recopies a la main parce que declarer `tests/engine/conftest.py` ne declare PAS ce
        # qu'il importe -- et ce fichier a rendu `master` ROUGE pour l'avoir declare HONNETEMENT.
        # Le foyer les DERIVE desormais (`declencheur_cliquet.chemins_du_harnais`, ajout 3) : le
        # perimetre effectif est le MEME, seul l'auteur change. Mesure : la derivation en rend
        # 86 pour `tests/engine/`, soit un SUR-ensemble strict des 16.
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE d'un invariant de structure (le bond descend aux sous-effets). Aucun "
              "RPC, aucun runner : seul un changement du moteur peut la faire changer d'avis.",
}

import pytest

from engine.entities.effect_type import EffectType
from engine.runner.operations.effects import AddEffectOperation

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)              # 0x1b = 27
TAUNTED_ENFANTS = (int(EffectType.Taunted_BlockMovement),          # 0x19 = 25
                   int(EffectType.Taunted_CantUseAbility),         # 0x1a = 26
                   int(EffectType.Taunted_RefreshUnitTurnFinished))  # 0x4d5 = 1237
STUNNED = int(EffectType.Stunned)                                  # 1162
STUNNED_ENFANTS = (int(EffectType.Stunned_CantUseAbility),
                   int(EffectType.Stunned_MovementOverride),
                   int(EffectType.Stunned_DamageModifier))

TAUNTANT, TAUNTEE = 81, 79            # ids arbitraires, distincts et NON NULS


def _state():
    """`State` minimal : deux unites VIVANTES et un `EffectsState`. Les entites doivent EXISTER --
    `AddEffectOperation.execute` abandonne (rend `None`) sur une cible absente, et l'abandon se
    lirait comme un rouge de fond alors que c'est le montage."""
    from engine.entities.effects_state import EffectsState
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State
    st = State()
    st.turn_order_player_count = 2
    st.current_player_id = 3
    # `State()` nu a `effects is None` (capture sans `combatSnapshot`) et `AddEffectOperation`
    # abandonne alors la pose : sans cette ligne, les trois bras rougiraient sur le MONTAGE.
    st.effects = EffectsState()
    for uid, team, player, pos in ((TAUNTANT, 1, 3, (3, 3)), (TAUNTEE, 2, 4, (4, 3))):
        e = st.add_entity(uid)
        e.add_component(UnitComponent("u%d" % uid, True))
        e.add_component(OwnerComponent(team, player))
        e.add_component(PositionComponent(pos[0], pos[1]))
    return st


def _bonds(st, uid, types):
    """`{effect_type: bonded}` pour les types demandes, lu la ou le moteur le lit."""
    out = {}
    for e in (st.effects.by_unit.get(int(uid)) or []):
        t = int(getattr(e, "effect_type", -1))
        if t in types:
            out[t] = getattr(e, "bonded", None)
    return out


def test_materialisation_offline():
    """POSE : les trois enfants heritent du bond du parent (mirror du CONTEXTE PARTAGE natif)."""
    st = _state()
    parent = AddEffectOperation.execute(
        st, source=TAUNTANT, target=TAUNTEE, effect_type=TAUNTED,
        name=EffectType.Taunted_OnlySpecificTargets.name, duration_override=6, bonded=TAUNTANT)
    assert parent is not None, "la pose du composite a ete abandonnee -- montage non conforme"

    # TEMOIN NON NUL : sans bond au parent, l'egalite ci-dessous serait `None == None`.
    assert getattr(parent, "bonded", None) == TAUNTANT, \
        "le PARENT ne porte pas le bond : ce bras ne prouverait rien"

    enfants = _bonds(st, TAUNTEE, set(TAUNTED_ENFANTS))
    assert sorted(enfants) == sorted(TAUNTED_ENFANTS), \
        "les trois sous-effets ne sont pas materialises : %r" % (sorted(enfants),)
    assert enfants == {t: TAUNTANT for t in TAUNTED_ENFANTS}, (
        "#524-r1 -- le bond du composite NE DESCEND PAS a ses sous-effets. "
        "`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` ecrit "
        "`ctx.<+0x18> = ABondEffect$$BondedEntityId(parent)` et passe CE contexte aux trois "
        "`EffectBuilder`, donc les trois enfants portent le bond du parent. "
        "attendu %r ; obtenu %r" % ({t: TAUNTANT for t in TAUNTED_ENFANTS}, enfants))


def test_hydratation_offline():
    """ETAT RECONSTRUIT : meme exigence, autre foyer (`snapshot._load_effect_parent_links`).

    C'est le canal par lequel un taunt arrive quand la bataille a commence avant la capture. Le
    rater laisserait la moitie du gisement -- et c'est precisement le regime des tests live, qui
    chargent un `State` depuis `decisionView`/`combatSnapshot`."""
    from engine.entities.effects.factory import EffectFactory
    from engine.runner.snapshot import _load_effect_parent_links

    st = _state()
    # Le parent arrive BONDE (le capteur publie `bondedEntityId`), les enfants NON (mesure #524 :
    # le port ne les bondait pas ; cote natif ils le sont, `bondMeasured` vrai).
    parent = EffectFactory.create({"name": EffectType.Taunted_OnlySpecificTargets.name,
                                   "effectType": TAUNTED, "level": 1, "remaining": 6,
                                   "source": TAUNTANT})
    parent.bonded = TAUNTANT
    st.effects.add_effect(TAUNTEE, parent)
    for t in TAUNTED_ENFANTS:
        st.effects.add_effect(TAUNTEE, EffectFactory.create(
            {"name": EffectType(t).name, "effectType": t, "level": 1, "remaining": 6,
             "source": TAUNTANT}))

    _load_effect_parent_links(st)

    enfants = _bonds(st, TAUNTEE, set(TAUNTED_ENFANTS))
    assert getattr(parent, "bonded", None) == TAUNTANT, "temoin nul : le parent n'est pas bonde"
    assert enfants == {t: TAUNTANT for t in TAUNTED_ENFANTS}, (
        "#524-r1 (hydratation) -- un etat RECONSTRUIT laisse les sous-effets sans bond. "
        "attendu %r ; obtenu %r" % ({t: TAUNTANT for t in TAUNTED_ENFANTS}, enfants))


def test_regime_degenere_nomme_offline():
    """`Stunned` (1162) n'est pose par AUCUN `AddBondEffect` du port -> ses enfants n'ont PAS de
    bond, et l'heritage ne doit pas en FABRIQUER un.

    Ce bras existe pour que le vert des deux premiers ne se lise pas comme « la propagation marche
    partout » : il NOMME le regime ou elle est inerte. Il garde aussi le sens de l'heritage --
    on recopie le bond du parent, on n'invente pas la source."""
    st = _state()
    parent = AddEffectOperation.execute(
        st, source=TAUNTANT, target=TAUNTEE, effect_type=STUNNED,
        name=EffectType.Stunned.name, duration_override=4)          # PAS de `bonded`
    assert parent is not None, "la pose de Stunned a ete abandonnee -- montage non conforme"
    assert getattr(parent, "bonded", None) is None, \
        "Stunned n'est pose par aucun AddBondEffect : son parent ne doit pas etre bonde"

    enfants = _bonds(st, TAUNTEE, set(STUNNED_ENFANTS))
    assert sorted(enfants) == sorted(STUNNED_ENFANTS), \
        "les trois sous-effets de Stunned ne sont pas materialises : %r" % (sorted(enfants),)
    assert all(v is None for v in enfants.values()), (
        "l'heritage a FABRIQUE un bond la ou le parent n'en a pas : %r" % (enfants,))
