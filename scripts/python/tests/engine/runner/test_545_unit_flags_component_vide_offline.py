"""#545 -- GARDE du foyer `snapshot._load_unit_flags` : un `UnitFlagsComponent` VIDE est un ETAT,
pas une absence. Et #508-r1 -- le substrat `AmountOfAttacksMadeThisTurn`.

LE FAIT NATIF (#545). `IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor` construit un
`OrderedSet` **VIDE** et `IdunBattle.Entities.Factories.UnitFactory` le monte sur **CHAQUE** unite.
`IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` (et son jumeau `RemoveFlag`) resout le
composant sans garde et **LEVE** s'il est absent -- il ne l'ignore pas. Natif, « unite sans
`UnitFlagsComponent` » n'existe donc pas.

CE QUE LE PORT FAISAIT. `_load_unit_flags` ne materialisait le composant que si la ligne du snapshot
portait une liste **NON VIDE**. Toute unite sans aucun flag n'en avait donc pas, et chaque site qui
fait `if fc is None: return` avant de POSER un flag devenait un **no-op silencieux** -- mesure
#498-r4-r1 : natif `unitFlags = [1, 2, 3, 4, 25]` apres le cast de `1152`, port RIEN.

TRI-ETAT : `unitFlags` ABSENT ou `null` = canal NON MESURE -> on ne touche a rien (retro-compatible
avec un bundle Frida anterieur) ; une LISTE, meme VIDE, est une MESURE -> composant materialise.

LE FAIT NATIF (#508-r1). `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade`
fait `this[0x24] += 1` (et `+0x2c`/`+0x28` selon `rangeType`), et
`ActorStatisticsComponent$$ResetUnitsAttackedThisTurn` -- dont le NOM ne le dit pas -- remet les
trois a zero (`*(long long*)(this + 0x24) = 0` : une ecriture 64 bits qui couvre `+0x24` ET `+0x28`,
puis `this[0x2c] = 0`). `AmountOfAttacksMadeThisTurnFormula$$Calculate` lit `+0x24` quand son
`Nullable<rangeType>` est VIDE, ce qui est le cas des DEUX call-sites de `LeadingTheCharge`.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LA CASCADE DES CONFTEST est DERIVEE par le foyer depuis #531 -- ne pas la recopier ici.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER, nomme -- pas de glob indiscriminant : ce fichier n'exerce QUE le chargeur de
        # flags, le composant qui les porte, les deux abstentions de `turnflow` qui les
        # DISTINGUENT, et les trois compteurs d'attaques emises.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/state.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/operations/revive.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/probe_545_unit_flags_component_vide.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE d'un SUBSTRAT (materialisation d'un composant et deux compteurs de "
              "l'ActorStatisticsComponent). Aucun RPC, aucun runner : la mesure du rayon de souffle "
              "vit dans `probe_545_unit_flags_component_vide.py`.",
}

import pytest                                                                   # noqa: E402

from engine.runner import snapshot as SNAP                                      # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,           # noqa: E402
                                      PositionComponent, UnitComponent,
                                      UnitFlagsComponent,
                                      register_attack_made,
                                      reset_units_attacked_this_turn,
                                      unit_attacks_made_this_turn,
                                      unit_turns_with_attacks_made)
from engine.runner.state import State                                           # noqa: E402


def _etat(nb=1):
    st = State()
    for i in range(1, nb + 1):
        e = st.add_entity(i)
        e.add_component(UnitComponent(visual_id="orksNob", alive=True))
        e.add_component(OwnerComponent(team=1 if i == 1 else 2, player=1 if i == 1 else 2))
        e.add_component(PositionComponent(col=i, row=1))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    return st


# ─────────────────────────── ETAGE 1 : le TRI-ETAT du chargeur ────────────────────────────────
@pytest.mark.parametrize("ligne,attendu_composant,attendu_flags", [
    ({"entityId": 1}, False, None),                        # champ ABSENT   -> NON mesure
    ({"entityId": 1, "unitFlags": None}, False, None),      # champ `null`   -> NON mesure
    ({"entityId": 1, "unitFlags": []}, True, []),           # liste VIDE     -> MESURE
    ({"entityId": 1, "unitFlags": [0, 25]}, True, [0, 25]),  # liste PLEINE  -> MESURE
])
def test_le_tri_etat_du_chargeur_de_flags(ligne, attendu_composant, attendu_flags):
    """Une LISTE, meme vide, materialise le composant ; l'ABSENCE et le `null` n'y touchent pas."""
    st = _etat()
    SNAP._load_unit_flags(st, {"units": [ligne]})
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert (fl is not None) is attendu_composant, (
        "ligne %r : composant present = %s, attendu %s" % (ligne, fl is not None,
                                                           attendu_composant))
    if attendu_flags is not None:
        assert sorted(fl.flags) == attendu_flags


def test_le_compte_rendu_dit_combien_de_lignes_etaient_VIDES():
    """`state.unit_flags_seed['vides']` -- l'amplitude doit etre LISIBLE, pas devinee : c'est
    exactement le nombre d'entites que le port laissait SANS composant avant #545."""
    st = _etat(nb=3)
    SNAP._load_unit_flags(st, {"units": [{"entityId": 1, "unitFlags": []},
                                         {"entityId": 2, "unitFlags": []},
                                         {"entityId": 3, "unitFlags": [3]}]})
    seed = st.unit_flags_seed
    assert seed["vides"] == 2, seed
    assert seed["units"] == 3, seed
    for i in (1, 2, 3):
        assert st.get_entity(i).get_component(UnitFlagsComponent) is not None


def test_le_tri_etat_du_bloc_unitsNotAlive_est_PRESERVE():
    """`units_not_alive` reste `None` (jamais `0`) quand le canal n'a pas ete mesure -- la regle
    `host_inputs.py`, qui existait avant #545 et que cette tranche ne doit pas eroder."""
    st = _etat()
    SNAP._load_unit_flags(st, {"units": []})                       # champ ABSENT
    assert st.unit_flags_seed["units_not_alive"] is None
    assert st.unit_flags_seed["units_not_alive_channel"] == "absent"
    st2 = _etat()
    SNAP._load_unit_flags(st2, {"units": [], "unitsNotAlive": None})
    assert st2.unit_flags_seed["units_not_alive"] is None
    assert st2.unit_flags_seed["units_not_alive_channel"] == "muet"
    st3 = _etat()
    SNAP._load_unit_flags(st3, {"units": [], "unitsNotAlive": [{"entityId": 1,
                                                                "unitFlags": [9]}]})
    assert st3.unit_flags_seed["units_not_alive"] == 1
    assert st3.unit_flags_seed["units_not_alive_channel"] == "lu"


# ───────────── ETAGE 2 : les DEUX sites que le composant VIDE fait BASCULER ────────────────────
def test_MarkUnitAsNoActionAvailable_ne_s_abstient_plus_sur_une_unite_MESUREE():
    """`MarkUnitAsNoActionAvailableOperation.execute` rendait `found: False` sur composant ABSENT.
    C'est l'une des DEUX seules positions d'`engine/**` que le passage VIDE/ABSENT distingue
    (mesure : `probe_545_unit_flags_component_vide.py` etape 1, 49 sites, 5 distinguants dont
    2 dans ce foyer). Le natif, lui, `TryGetComponent` sur une unite qui en porte TOUJOURS un."""
    from engine.runner.operations.turnflow import MarkUnitAsNoActionAvailableOperation as M
    st = _etat()
    assert M.execute(st, 1)["found"] is False, "prealable : sans composant, le port s'abstient"
    SNAP._load_unit_flags(st, {"units": [{"entityId": 1, "unitFlags": []}]})
    r = M.execute(st, 1)
    assert r["found"] is True and r["changed"] is True, r
    assert st.get_entity(1).get_component(UnitFlagsComponent).has(
        UnitFlagsComponent.NO_ACTION_AVAILABLE)


def test_les_lecteurs_NEUTRES_ne_bougent_PAS():
    """Les 31 sites NEUTRES du recensement ecrivent `fl is not None and fl.has(X)` : un
    `OrderedSet` vide est indiscernable d'une absence pour eux. Temoin sur trois d'entre eux."""
    from engine.runner.components import (unit_has_moved, unit_is_overkilled,
                                          unit_extensions_is_displaceable)
    st = _etat()
    e = st.get_entity(1)
    avant = (unit_has_moved(st, 1), unit_is_overkilled(e), unit_extensions_is_displaceable(e))
    SNAP._load_unit_flags(st, {"units": [{"entityId": 1, "unitFlags": []}]})
    apres = (unit_has_moved(st, 1), unit_is_overkilled(e), unit_extensions_is_displaceable(e))
    assert avant == apres == (False, False, True), (avant, apres)


# ───────── ETAGE 3 : l'ECRIVAIN qui SAUTAIT la rafale quand le composant manquait ──────────────
def test_le_revive_ne_saute_plus_sa_rafale_de_flags():
    """`revive.py` faisait `if fl is not None:` -- donc `Add(0x14 = Revived)` n'etait JAMAIS pose
    sur une unite sans composant. Meme forme que `_set_charge_flag` avant #498-r4-r1."""
    from engine.runner.operations.revive import ReviveUnitOperation
    st = _etat()
    uc = st.get_entity(1).get_component(UnitComponent)
    uc.alive = False
    st.get_entity(1).get_component(HealthComponent).hp = 0
    # Signature NATIVE : le HP n'est PAS un parametre, il vient de la `ReviveData` posee sur
    # `UnitComponent + 0xa8` (`pending_revive` cote port).
    uc.pending_revive = {"amount": 500}
    assert st.get_entity(1).get_component(UnitFlagsComponent) is None, "prealable : pas de composant"
    ReviveUnitOperation.execute(st, 1)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl is not None, "le revive doit CREER le composant absent, pas sauter la rafale"
    assert fl.has(UnitFlagsComponent.REVIVED)


# ─────────── ETAGE 4 : #508-r1, le substrat `AmountOfAttacksMadeThisTurn` (+0x24) ──────────────
def test_le_compteur_d_attaques_emises_monte_et_se_remet_a_zero():
    """`RegisterAttackMade` fait `this[0x24] += 1` A CHAQUE attaque (contraste `+0x30`, qui
    n'avance qu'au PREMIER coup du tour) ; `ResetUnitsAttackedThisTurn` le remet a zero."""
    st = _etat(nb=3)
    assert unit_attacks_made_this_turn(st, 1) == 0
    register_attack_made(st, 1, 2)
    register_attack_made(st, 1, 3)
    register_attack_made(st, 1, 2)                     # MEME cible : `+0x24` avance quand meme
    assert unit_attacks_made_this_turn(st, 1) == 3
    # `+0x30` est un compte de TOURS : une seule avancee pour ces trois attaques.
    assert unit_turns_with_attacks_made(st, 1) == 1
    reset_units_attacked_this_turn(st, 1)
    assert unit_attacks_made_this_turn(st, 1) == 0
    assert unit_turns_with_attacks_made(st, 1) == 1, "le reset ne touche PAS `+0x30`"


def test_le_compteur_ignore_un_attaquant_NON_UNITE():
    """Caster entite-TUILE (DoT de feu) : pas de `UnitComponent` -> le natif n'a pas de composant
    d'acteur non plus. Aucune levee, aucun compteur."""
    st = _etat(nb=2)
    register_attack_made(st, 999, 2)                  # id inconnu
    assert unit_attacks_made_this_turn(st, 999) == 0


def test_le_gate_de_spawn_de_LeadingTheCharge_lit_le_compteur_et_pas_un_proxy():
    """`If( AmountIsGreater(TimesAttackMadeThisTurn(caster, null), Cache(<idem>)), Spawn )` : le
    port comparait « une emission d'attaque de plus » ; il compare desormais le COMPTEUR a
    lui-meme, ce que le natif ecrit. Le predicat doit basculer avec le compteur."""
    st = _etat(nb=2)
    cache = unit_attacks_made_this_turn(st, 1)          # `SetCache(...)` -- fige AVANT l'attaque
    assert not (unit_attacks_made_this_turn(st, 1) > cache), (
        "sans attaque emise, le predicat doit etre FAUX -- sinon le spawn partirait toujours")
    register_attack_made(st, 1, 2)
    assert unit_attacks_made_this_turn(st, 1) > cache
