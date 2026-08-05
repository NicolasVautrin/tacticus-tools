"""#477-r21-r3 -- GARDE offline de l'ALLOCATEUR d'entites ECS.

`probe_477r21r3_allocation_effets.py` MESURE en live (il monte un runner par scenario, lit le
flux, confronte chaque identifiant). Ce fichier GARDE : il fige ce que la mesure a etabli, et
surtout il verifie que le port DISCRIMINE -- qu'il rougit sur les lectures FAUSSES du decompile.

CE QUI EST FIGE ICI vient d'une mesure live NOMMEE : session Frida 1, build `rnca9r7q6c`, seed
777, boards `C1_02` / `MC1_67` / `MC1_67` en roster 2v2, 2 tours d'IA, 2026-08-06. Les ancres
mesurees sont 59 / 87 / 81, et la regle reproduit 63/63, 67/67 et 22/22 allocations du deroule
des lors que la SEQUENCE DE CREATION lui est donnee.

⚠ POURQUOI UN TEST DE PLUS QUE LE PROBE. `probe_313` garde les mirrors d'ENUM ; rien ne gardait
une regle de CALCUL. Un renumerotage silencieux du binaire (build suivant) ferait bouger les
chiffres sans qu'aucun mirror ne change : ce sont les valeurs MESUREES qui sont figees ici, pas
la capacite du port a se regenerer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.streams.entity_allocator import (MATCH_ENTITY_ID, MatchComponent,  # noqa: E402
                                             add_effect, add_machine,
                                             add_machine_of_war_platform, add_tile, add_unit,
                                             allocate_setup_game, initialize_match,
                                             new_match_after_setup)
from engine.streams.game_setup import (GameSetup, PLATFORM_POSITIONS, PlayerSetup,  # noqa: E402
                                       TileSetup, UnitSetup, assign_entity_ids)

#: Les trois scenarios de la mesure live : (nom, P, E, T, nb unites deployees, ANCRE mesuree).
#: `T` est `Width * Height` du board versionne ; `E` est la regle #477-r16 sur le seed courant.
ANCRES_MESUREES = (
    ("C1_02", 3, 6, 35, 5, 59),
    ("MC1_67", 3, 6, 63, 5, 87),
    ("MC1_67-2v2", 3, 6, 63, 2, 81),
)


# ------------------------------------------------------- etage 1 : le COMPTEUR, mirror 1:1

def test_ctor_pose_un():
    """`MatchComponent$$.ctor` : `*(undefined4 *)(this + 0x10) = 1;`."""
    assert MatchComponent().last_id == 1


def test_next_id_pre_incremente():
    """`MatchComponent$$NextId` : `this.<+0x10> += 1 ; return this.<+0x10>`.

    Un POST-increment rendrait 1 puis 2 : c'est la mutation `post-increment` du probe, et elle
    decale TOUT le flux."""
    m = MatchComponent()
    assert (m.next_id(), m.next_id()) == (2, 3)
    assert m.last_id == 3


def test_return_last_id_decremente():
    """`MatchComponent$$ReturnLastId` : `this.<+0x10> -= 1`."""
    m = MatchComponent()
    m.next_id()
    m.return_last_id()
    assert m.last_id == 1


def test_initialize_match_incremente_sans_allouer():
    """`InitializeMatchOperation$$Execute` incremente le champ DIRECTEMENT, sans passer par
    `NextId` -- la valeur n'est rendue a personne."""
    m = MatchComponent()
    initialize_match(m)
    assert m.last_id == 2


def test_id_deux_jamais_attribue():
    """L'entite MATCH prend le LITTERAL 1, le `.ctor` pose 1, `InitializeMatch` passe a 2 : le
    premier `NextId` rend donc 3, et 2 n'est JAMAIS attribue. Mesure #477-r16 : les trois
    joueurs recoivent 3, 4, 5 sur trois boards."""
    m = MatchComponent()
    initialize_match(m)
    rendus = [m.next_id() for _ in range(5)]
    assert rendus == [3, 4, 5, 6, 7]
    assert MATCH_ENTITY_ID == 1


# ------------------------------------------------- etage 2 : le COUT de chaque site, par site

def test_unite_coute_un_plus_ses_pieds():
    """`AddUnitOperation$$Execute` alloue l'unite PUIS une `FootEntity` par tuile occupee.

    Le pas de 2 des flux temoins n'est pas la regle -- c'est la consequence de rosters
    mono-pied. Une unite BI-PIED en coute 3."""
    m = MatchComponent()
    mono = add_unit(m, 1)
    bi = add_unit(m, 2)
    assert (mono.entity_id, mono.foot_entity_ids) == (2, (3,))
    assert (bi.entity_id, bi.foot_entity_ids) == (4, (5, 6))
    assert m.last_id == 6


def test_effet_coute_exactement_un():
    """`Blueprints$$Effect(id)` construit une `Core.EffectEntity` et lui attache un seul
    `EffectComponent` : aucune sous-entite. C'est la mutation `effet-avec-pied` du probe."""
    m = MatchComponent()
    assert [add_effect(m) for _ in range(3)] == [2, 3, 4]
    assert m.last_id == 4


def test_effet_ne_rend_jamais_son_id():
    """`ReturnLastId` n'a que DEUX sites d'appel dans tout le binaire, tous deux sur le chemin
    TUILE. Aucun effet retire ne rend son identifiant -- c'est la mutation `effet-recycle`."""
    m = MatchComponent()
    premier = add_effect(m)
    second = add_effect(m)
    assert (premier, second) == (2, 3)
    assert m.last_id == 3


def test_machine_na_pas_de_pied():
    """`Blueprints$$Machine` ne cree aucune `UnitFoot` : c'est ce qui distingue une machine
    d'une unite dans le compteur."""
    m = MatchComponent()
    assert (add_machine(m), add_machine_of_war_platform(m)) == (2, 3)
    assert m.last_id == 3


def test_rollback_seulement_sur_la_tuile():
    """`AddTileOperation$$Execute` alloue AVANT d'appeler la factory et rend l'id si celle-ci
    renvoie `null`. `AddUnitOperation` / `AddMachineOperation` ne le font PAS : l'id est brule."""
    m = MatchComponent()
    assert add_tile(m, factory_returned_entity=True) == 2
    assert add_tile(m, factory_returned_entity=False) is None
    assert m.last_id == 2


# ------------------------------------------- etage 3 : la SEQUENCE, confrontee aux mesures live

@pytest.mark.parametrize("nom,p,e,t,unites,ancre", ANCRES_MESUREES)
def test_ancre_du_deroule_reproduite(nom, p, e, t, unites, ancre):
    """L'ANCRE -- le premier identifiant que le deroule consomme -- est DERIVEE de la seule BC,
    du board et du roster. Elle est confrontee EXACTE sur les trois scenarios."""
    match, _alloc = new_match_after_setup(
        player_count=p, environment_ability_count=e, tile_count=t,
        machine_of_war_platform_count=len(PLATFORM_POSITIONS),
        unit_foot_counts=[1] * unites)
    assert match.last_id + 1 == ancre, nom


def test_offsets_de_la_mesure_477r16():
    """Les deux chiffres que #477-r16 a confrontes sur douze criteres : la premiere tuile vaut
    `3 + P + E`, la premiere unite `premiere tuile + T + 2`."""
    match = MatchComponent()
    initialize_match(match)
    alloc = allocate_setup_game(match, player_count=3, environment_ability_count=6,
                                tile_count=35,
                                machine_of_war_platform_count=len(PLATFORM_POSITIONS),
                                unit_foot_counts=[1] * 5)
    assert alloc.players == (3, 4, 5)
    assert alloc.first_tile_entity_id == 3 + 3 + 6
    assert alloc.tiles[-1] == 46
    assert alloc.machine_of_war_platforms == (47, 48)
    assert alloc.first_unit_entity_id == alloc.first_tile_entity_id + 35 + 2


def test_les_deux_plateformes_sont_inconditionnelles():
    """`SetupGameOperation$$Execute` appelle `AddMachineOfWarPlatform` DEUX fois, positions 2
    puis 1, quel que soit le roster. En allouer une seule decale toutes les unites."""
    assert len(PLATFORM_POSITIONS) == 2
    match = MatchComponent()
    initialize_match(match)
    deux = allocate_setup_game(match, player_count=3, environment_ability_count=6, tile_count=35,
                               machine_of_war_platform_count=2, unit_foot_counts=[1])
    match_bis = MatchComponent()
    initialize_match(match_bis)
    une = allocate_setup_game(match_bis, player_count=3, environment_ability_count=6,
                              tile_count=35, machine_of_war_platform_count=1,
                              unit_foot_counts=[1])
    assert deux.first_unit_entity_id != une.first_unit_entity_id


# --------------------------------------------------- etage 4 : le RACCORD sur l'emetteur de flux

def _setup_temoin(nb_unites: int = 3) -> GameSetup:
    """Une structure de deploiement dont TOUS les `entity_id` sont volontairement ABSURDES :
    `assign_entity_ids` doit les remplacer, jamais les propager."""
    return GameSetup(
        players=tuple(PlayerSetup(entity_id=-1, player_id=11 + i) for i in range(3)),
        tiles=tuple(TileSetup(entity_id=-1, column=i % 5, row=i // 5) for i in range(35)),
        units=tuple(UnitSetup(entity_id=-1, owner_id=3, foot_tile_ids=(20 + i,))
                    for i in range(nb_unites)),
    )


def test_assign_entity_ids_derive_tout_le_deploiement():
    setup, match = assign_entity_ids(_setup_temoin(5), environment_ability_count=6)
    assert [p.entity_id for p in setup.players] == [3, 4, 5]
    assert setup.tiles[0].entity_id == 12 and setup.tiles[-1].entity_id == 46
    assert tuple(setup.platform_entity_ids) == (47, 48)
    assert [u.entity_id for u in setup.units] == [49, 51, 53, 55, 57]
    assert match.last_id + 1 == 59, "l'ancre mesuree sur `C1_02`"


def test_assign_entity_ids_ne_propage_aucun_id_recu():
    """Le contrat est explicite : les `entity_id` du setup recu sont IGNORES. Un port qui les
    recopierait rendrait -1, et l'emetteur ecrirait `Entity=-1` sans erreur."""
    setup, _ = assign_entity_ids(_setup_temoin(2), environment_ability_count=6)
    valeurs = ([p.entity_id for p in setup.players] + [t.entity_id for t in setup.tiles]
               + [u.entity_id for u in setup.units] + list(setup.platform_entity_ids))
    assert all(v > 0 for v in valeurs)


def test_assign_entity_ids_lit_le_foot_count_declare():
    """`UnitSetup.foot_count` prime sur `len(foot_tile_ids)` -- les deux collections sont
    DISTINCTES dans la signature native, et c'est `feet.Count` qui pilote la boucle."""
    base = _setup_temoin(2)
    trafique = GameSetup(players=base.players, tiles=base.tiles,
                         units=(UnitSetup(entity_id=-1, owner_id=3, foot_tile_ids=(20,),
                                          foot_count=2),
                                base.units[1]))
    setup, _ = assign_entity_ids(trafique, environment_ability_count=6)
    assert [u.entity_id for u in setup.units] == [49, 52], "la 1re unite consomme 49, 50 et 51"


def test_environment_ability_count_decale_tout():
    """`E` n'est pas dans le `setup` : c'est une entree, et la passer fausse decale l'ensemble.
    Ce test existe pour que la dependance soit VISIBLE, pas pour la deplorer."""
    a, _ = assign_entity_ids(_setup_temoin(1), environment_ability_count=6)
    b, _ = assign_entity_ids(_setup_temoin(1), environment_ability_count=7)
    assert b.tiles[0].entity_id == a.tiles[0].entity_id + 1


# ------------------------------------ etage 5 : les verdicts du probe DISCRIMINENT (fonctions pures)

def test_auto_test_des_gardes_du_probe():
    """Le probe porte ses propres crans, et chacun doit avoir ete VU ROUGE. Ce test appelle son
    mode `--auto-test-gardes`, qui est PUREMENT OFFLINE (aucune session, aucun runner)."""
    import probe_477r21r3_allocation_effets as P  # noqa: E402

    ok, lignes = P.auto_test_gardes()
    assert ok, "\n".join(lignes)


def test_la_mutation_unite_pas_fixe_est_declaree_non_exercee_sur_du_mono_pied():
    """Un corpus mono-pied ne peut PAS exercer `unite-pas-fixe`. Le probe doit le DIRE plutot
    que de rendre un vert : c'est la difference entre « cran passe » et « cran non exerce »."""
    import probe_477r21r3_allocation_effets as P  # noqa: E402

    assert P.inerte_par_construction("unite-pas-fixe", [1, 1, 1])
    assert not P.inerte_par_construction("unite-pas-fixe", [1, 2])
    assert not P.inerte_par_construction("post-increment", [1, 1, 1])
