"""#498-r3 -- `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` : les QUATRE refus, et le SITE
qui n'en portait AUCUN.

CE QUE CE FICHIER GARDE

Le port testait DEUX conditions la ou le natif en teste QUATRE, et un 8e site
(`SwitchPositionOperation`) n'en testait aucune -- alors que la tete d'`IdunBattle.Operations.
DisplaceUnitOperation$$Execute` s'execute AVANT le `switch(direction)`, donc AUSSI pour son case 5.

Decompile relu VERBATIM sur le build courant :

    if (unit == null)                                        return false;
    if (GetEntityType(unit) != EntityType.Unit)              return false;   // iface, slot 1
    if (GetBaseUnitComponent(unit) != null
        && BaseUnitComponent.HasTrait(unit, 0x11))           return false;   // Immovable
    if (GetBaseUnitComponent(unit) != null
        && BaseUnitComponent.HasTrait(unit, 0x3))            return false;   // Hulking
    big = GetBaseUnitComponent(unit) != null
          && BaseUnitComponent.HasTrait(unit, 0x3f9);                        // BigTarget
    return !UnitExtensions.HasFlag(unit, 0x19) && !big;               // UnitFlag.Undisplaceable

DEUX faits que le nom de la fonction ne laisse pas deviner, et que ce fichier verrouille :

  * **AUCUNE LIVENESS.** Le natif ne teste ni PV, ni `UnitFlag.Dead`, ni appartenance au pool. Le
    gate `alive` du port vit HORS du foyer, aux trois `execute()` qui l'avaient deja -- il est
    CONSERVE et NOMME, direction RESTRICTIVE. Le foyer, lui, accepte un cadavre : etage 5.
  * **`0x19` designe DEUX choses differentes a deux lignes d'ecart.** Dans `IsDisplaceable` c'est un
    `UnitFlag` (`Undisplaceable`) ; dans `DamagePrediction$$GetKnockback`, juste apres l'appel,
    c'est un `UnitTrait` (`Immune`). L'ecart n'etait donc PAS visible a l'ordinal -- etage 0.

Les ETAGES (chacun tombe pour une cause DIFFERENTE) :
  0. les cinq ordinaux, FIGES A LA CONVERSION et re-confrontes a `frida/enums.tsv` ;
  1. la table de verite du foyer -- chaque condition refuse SEULE ;
  2. les quatre operations de `displace.py` refusent une cible non deplacable ;
  3. le recenseur `probe_498r3_is_displaceable_sites.py` est vert ;
  4. CONTRE-EPREUVE : re-introduire une copie en dur dans un arbre TEMOIN fait ROUGIR le
     recenseur (sans elle, l'etage 3 serait un vert qui ne prouve rien) ;
  5. le foyer n'a PAS de gate `alive`, et les trois `execute()` en ont un.

ASCII only ; offline (aucun runner).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER. Perimetre pris LARGE, pas feuille a feuille : l'etage 4 COPIE
        # l'arbre `engine/` entier dans un temoin, et le recenseur le PARCOURT -- toute feuille
        # d'`engine/**` entre donc dans la fermeture, et une liste choisie rendrait ce cliquet
        # rouge. Foyers vraiment load-bearing, pour la relecture humaine :
        # `runner/components.py` (le foyer `unit_extensions_is_displaceable`),
        # `runner/operations/displace.py` (les quatre `execute`), `entities/traits/unit_trait.py`
        # et `entities/unit_flag.py` (les deux enums), `probe_498r3_is_displaceable_sites.py`.
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        # L'etage 0 QUALIFIE les six ordinaux contre la table d'enums du BUILD.
        "data/symbols/**",
        # L'etage 2 passe par `_apply_knockback_to`, dont le pourcentage se resout par
        # `services/damage_config.resolve_damage_field` -- qui DERIVE son defaut du seed BC
        # (#449-r2-r4-r4). Mesure de l'empreinte, pas une supposition.
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : les six ordinaux d'`IsDisplaceable` (3 traits, 1 flag, 2 valeurs "
              "d'EntityType), la table de verite du foyer, le no-op des quatre operations de "
              "`displace.py` sur une cible non deplacable, et la CONTRE-EPREUVE du recenseur. "
              "Aucun runner, aucune session Frida : le seul acces disque est le depot (table "
              "d'enums du build, plus une copie de `engine/` en tmp pour l'etage 4).",
}

import shutil
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_498r3_is_displaceable_sites as P                            # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.unit_context import UnitContext                     # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                  # noqa: E402
from engine.entities.unit_flag import UnitFlag                           # noqa: E402
from engine.runner.components import (MachineComponent,                  # noqa: E402
                                      OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent,
                                      UnitFlagsComponent,
                                      unit_extensions_is_displaceable)
from engine.runner.events import EventBus                                # noqa: E402
from engine.runner.operations.displace import (DirectDisplaceOperation,  # noqa: E402
                                               DisplaceUnitOperation,
                                               PullUnitOneTileOperation,
                                               SwitchPositionOperation,
                                               _apply_knockback_to)
from engine.runner.state import State                                    # noqa: E402


# --- ETAGE 0 : les ordinaux, FIGES ICI ---------------------------------------------------------- #
# Mesures A LA CONVERSION (#498-r3). `probe_313` compare le MIRROR au BUILD : il redevient vert des
# qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
# change. Ces six lignes sont le cran du dessous.
ORDINAUX_MESURES = {
    "UnitTrait.Immovable": 0x11,
    "UnitTrait.Hulking": 0x3,
    "UnitTrait.BigTarget": 0x3f9,
    "UnitFlag.Undisplaceable": 0x19,
    "EntityType.Unit": 1,
    "EntityType.Machine": 6,
}


def test_etage0_les_ordinaux_du_site_sont_ceux_du_mirror():
    assert int(UnitTrait.Immovable) == ORDINAUX_MESURES["UnitTrait.Immovable"]
    assert int(UnitTrait.Hulking) == ORDINAUX_MESURES["UnitTrait.Hulking"]
    assert int(UnitTrait.BigTarget) == ORDINAUX_MESURES["UnitTrait.BigTarget"]
    assert int(UnitFlag.Undisplaceable) == ORDINAUX_MESURES["UnitFlag.Undisplaceable"]


def test_etage0_les_ordinaux_nomment_encore_la_meme_chose_dans_le_build():
    """Qualification contre `data/symbols/<build>/frida/enums.tsv`, pas contre le mirror."""
    qual = P.etape_qualification()
    assert qual["rows"], "aucun ordinal qualifie : la table d'enums n'a pas ete lue"
    assert not qual["bad"], "ordinaux qui ne nomment plus la meme chose : %s" % (qual["bad"],)


def test_etage0_le_0x19_de_knockback_est_un_TRAIT_pas_le_FLAG():
    """`DamagePrediction$$GetKnockback` = `IsDisplaceable(t)` PUIS `HasTrait(t, 0x19)`. Les deux
    `0x19` sont a deux lignes d'ecart et ne designent PAS la meme chose. Un port qui confondrait
    les deux ne leverait AUCUNE erreur -- c'est ce qui rend le NOM obligatoire."""
    assert int(UnitTrait.Immune) == 0x19
    assert int(UnitFlag.Undisplaceable) == 0x19
    assert UnitTrait.Immune.name != UnitFlag.Undisplaceable.name


# --- montage ------------------------------------------------------------------------------------ #
def _unit(st, uid, pos, team, traits=(), flags=(), machine=False):
    e = st.add_entity(uid)
    if pos is not None:
        e.add_component(PositionComponent(pos[0], pos[1]))
    e.add_component(UnitComponent("vis%d" % uid, True))
    e.add_component(OwnerComponent(team))
    # `traits_measured=True` -> `entity_trait_names` rend EXACTEMENT cette liste (pas de
    # re-derivation d'alliance, pas de lecture gameconfig) : le montage controle le substrat.
    e.add_component(StatsComponent(UnitContext(uid, visual_id="vis%d" % uid,
                                               traits=[t.name for t in traits],
                                               traits_measured=True)))
    e.add_component(UnitFlagsComponent({int(f) for f in flags}))
    if machine:
        e.add_component(MachineComponent(slot=1))
    return e


def _strip_board(n=8):
    """Une bande de `n` tuiles collineaires (col 0), toutes marchables. Suffit aux trois
    operations qui cherchent une destination (le push va TOUJOURS a 1 hex)."""
    return Board([{"id": 100 + r, "col": 0, "row": r, "walkable": True, "elevation": 0}
                  for r in range(n)], adjacency="native_sym")


# --- ETAGE 1 : la table de verite du FOYER ------------------------------------------------------ #
def test_etage1_une_unite_nue_est_deplacable():
    st = State()
    e = _unit(st, 1, (0, 1), 10)
    assert unit_extensions_is_displaceable(e) is True


@pytest.mark.parametrize("trait", [UnitTrait.Immovable, UnitTrait.Hulking, UnitTrait.BigTarget])
def test_etage1_chacun_des_trois_traits_refuse_SEUL(trait):
    """Les trois `BaseUnitComponent$$HasTrait` du decompile. `Hulking` (0x3) etait le refus
    MANQUANT cote runner -- il ne se voyait pas parce que les deux autres suffisaient partout."""
    st = State()
    e = _unit(st, 1, (0, 1), 10, traits=(trait,))
    assert unit_extensions_is_displaceable(e) is False


def test_etage1_le_flag_Undisplaceable_refuse_SEUL():
    """`UnitExtensions.HasFlag(unit, 0x19)`. C'est le flag que la charge de 1152 pose et retire
    elle-meme (`AddFlag`/`RemoveFlag` autour d'`ExecuteBehaviour`) : il est bien ECRIT cote port."""
    st = State()
    e = _unit(st, 1, (0, 1), 10, flags=(UnitFlag.Undisplaceable,))
    assert unit_extensions_is_displaceable(e) is False


def test_etage1_une_machine_de_guerre_refuse_par_la_TETE():
    """`GetEntityType(unit) != EntityType.Unit` -> false. Une MoW est `EntityType.Machine` (6) ;
    cote port le discriminant est `MachineComponent`, MEME choix que `unit_extensions_is_alive`.
    Mesure : les 8 MoW du seed BC ne portent NI `BigTarget` NI `Immovable` -- sans cette tete,
    aucun trait ne les arretait."""
    st = State()
    e = _unit(st, 1, (0, 1), 10, machine=True)
    assert unit_extensions_is_displaceable(e) is False


def test_etage1_entite_absente_refuse():
    assert unit_extensions_is_displaceable(None) is False


# --- ETAGE 2 : les quatre operations de `displace.py` ------------------------------------------- #
def _sw(traits=(), flags=()):
    st = State()
    _unit(st, 1, (0, 1), 10)                       # caster / displacingUnit
    _unit(st, 2, (0, 4), 20, traits=traits, flags=flags)   # target / displacedUnit
    return st, SwitchPositionOperation(1, 2).execute(st, EventBus())


def test_etage2_switch_position_echange_quand_la_cible_est_deplacable():
    """Temoin NON DEGENERE : sans lui, un refus systematique passerait pour un succes du gate."""
    st, res = _sw()
    assert res["switched"] is True
    assert res["caster_to"] == (0, 4) and res["target_to"] == (0, 1)


@pytest.mark.parametrize("traits,flags", [
    ((UnitTrait.BigTarget,), ()),
    ((UnitTrait.Immovable,), ()),
    ((UnitTrait.Hulking,), ()),
    ((), (UnitFlag.Undisplaceable,)),
])
def test_etage2_switch_position_est_un_NO_OP_sur_une_cible_non_deplacable(traits, flags):
    """LE site que le constat d'origine n'avait pas vu : `SwitchPositionOperation` ne portait
    AUCUNE des quatre conditions. Degradation PERMISSIVE -- le port echangeait les tuiles d'une
    unite que `DisplaceUnitOperation$$Execute` REFUSE de deplacer des sa tete."""
    st, res = _sw(traits, flags)
    assert res["switched"] is False
    assert res["reason"] == "not displaceable"
    from engine.runner.components import PositionComponent as PC
    assert (st.get_entity(1).get_component(PC).col,
            st.get_entity(1).get_component(PC).row) == (0, 1)
    assert (st.get_entity(2).get_component(PC).col,
            st.get_entity(2).get_component(PC).row) == (0, 4)


@pytest.mark.parametrize("traits,flags", [
    ((UnitTrait.Hulking,), ()),
    ((), (UnitFlag.Undisplaceable,)),
])
def test_etage2_push_pull_direct_refusent_les_DEUX_conditions_manquantes(traits, flags):
    """Les trois `execute()` portaient deja `Immovable`/`BigTarget` ; ce test cible les deux qui
    MANQUAIENT, donc il tombait AVANT le fix et pas apres."""
    st = State()
    st.board = _strip_board()
    _unit(st, 1, (0, 1), 10)
    _unit(st, 2, (0, 2), 20, traits=traits, flags=flags)
    for op in (DisplaceUnitOperation(1, 2),
               PullUnitOneTileOperation(1, 2),
               DirectDisplaceOperation(1, 2, [(0, 5)])):
        res = op.execute(st, EventBus())
        assert res["moved"] is False, "%s a deplace une unite non deplacable" % type(op).__name__
        assert res["reason"] == "not displaceable"


def test_etage2_push_deplace_bien_une_cible_deplacable():
    """Temoin non degenere du parametre precedent."""
    st = State()
    st.board = _strip_board()
    _unit(st, 1, (0, 1), 10)
    _unit(st, 2, (0, 2), 20)
    res = DisplaceUnitOperation(1, 2).execute(st, EventBus())
    assert res["moved"] is True and res["to"] == (0, 3)


def test_etage2_le_knockback_suit_le_meme_gate():
    """`DamagePrediction$$GetKnockback` = `IsDisplaceable(t) && !HasTrait(t, Immune)` -> 0. Le port
    fusionnait les trois traits en UN seul `has_any_trait` ; les deux `0x19` y etaient donc
    indiscernables."""
    st = State()
    from engine.runner.components import HealthComponent
    for uid, traits, flags in ((1, (), ()), (2, (UnitTrait.Hulking,), ()),
                               (3, (), (UnitFlag.Undisplaceable,)), (4, (UnitTrait.Immune,), ())):
        e = _unit(st, uid, (0, uid), 20, traits=traits, flags=flags)
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    _unit(st, 9, (0, 0), 10)
    assert _apply_knockback_to(st, EventBus(), 9, 1) is not None      # temoin : degat applique
    for uid in (2, 3, 4):
        assert _apply_knockback_to(st, EventBus(), 9, uid) is None, "unite %d" % uid


# --- ETAGE 3+4 : le recenseur, et sa contre-epreuve --------------------------------------------- #
def test_etage3_le_recenseur_est_vert():
    rec = P.etape_recensement()
    cli = P.etape_cliquet(rec)
    assert not cli["copies"], "copie du predicat hors foyer : %s" % (
        [(s["fichier"], s["fonction"]) for s in cli["copies"]],)
    assert not cli["incomplets"], "miroir runner incomplet : %s" % (
        [(s["fichier"], s["fonction"], s["manque"]) for s in cli["incomplets"]],)
    # ASSERTIONNER SON PROPRE NON-VIDE : un recenseur qui ne visite rien rendrait 0 copie et
    # 0 incomplet, donc du vert. Le foyer et les quatre `execute()` DOIVENT etre vus.
    noms = {"%s::%s" % (s["fichier"], s["fonction"]) for s in rec["sites"]}
    assert "runner/components.py::unit_extensions_is_displaceable" in noms
    assert sum(1 for s in rec["sites"]
               if s["fichier"] == "runner/operations/displace.py"
               and s["fonction"] == "execute") == 4, (
        "les QUATRE cases portees de `DisplaceUnitOperation$$Execute` doivent etre recensees")
    assert cli["miroirs_runner"] >= 7


def test_etage4_contre_epreuve_une_copie_reintroduite_fait_rougir(tmp_path, monkeypatch):
    """Sans cet etage, l'etage 3 serait un vert qui ne prouve rien : il faut montrer que le
    recenseur SAIT rougir. On copie l'arbre `engine/` et on re-ecrit dans le TEMOIN la forme
    exacte qui vivait sur `master` avant #498-r3 (deux traits en dur, foyer court-circuite)."""
    temoin = tmp_path / "engine"
    shutil.copytree(PYDIR / "engine", temoin)
    cible = temoin / "runner" / "operations" / "displace.py"
    src = cible.read_text(encoding="utf-8")
    avant = "        if not unit_extensions_is_displaceable(pushed):\n"
    assert avant in src, "la forme attendue n'est plus au site : contre-epreuve INVALIDE"
    apres = ("        sc = pushed.get_component(StatsComponent)\n"
             "        traits = getattr(sc.ctx, 'traits', None) if sc is not None else None\n"
             "        if has_any_trait(traits, (UnitTrait.Immovable, UnitTrait.BigTarget)):\n")
    cible.write_text(src.replace(avant, apres, 1), encoding="utf-8")

    monkeypatch.setattr(P, "ENGINE", temoin)
    rec = P.etape_recensement()
    cli = P.etape_cliquet(rec)
    assert cli["copies"], "la copie re-introduite N'A PAS ete vue -- le recenseur ne mord pas"
    noms = {"%s::%s" % (s["fichier"], s["fonction"]) for s in cli["copies"]}
    assert "runner/operations/displace.py::execute" in noms
    # et elle est INCOMPLETE : il lui manque Hulking, le flag et la tete
    inc = [s for s in cli["incomplets"] if s["fichier"] == "runner/operations/displace.py"]
    assert inc and set(inc[0]["manque"]) == {"Hulking", "Undisplaceable", "EntityType"}


# --- ETAGE 5 : le gate `alive` est HORS du foyer, et il est NOMME ------------------------------- #
def test_etage5_le_foyer_ne_teste_AUCUNE_liveness():
    """`IsDisplaceable` ne lit ni PV, ni `UnitFlag.Dead`, ni pool. Un cadavre y est DEPLACABLE."""
    st = State()
    e = _unit(st, 1, (0, 1), 10)
    e.get_component(UnitComponent).alive = False
    e.get_component(UnitFlagsComponent).add(int(UnitFlag.Dead))
    assert unit_extensions_is_displaceable(e) is True


def test_etage5_le_gate_alive_a_MIGRE_au_rang_natif_et_le_switch_ne_l_a_toujours_pas():
    """⚠ **CET ETAGE A CHANGE DE VERDICT (#550-r4-r1), ET C'EST LE POINT.** Il gardait << le gate
    `alive` des trois `execute()` est ABSENT du natif ; il est CONSERVE >>. La premiere moitie
    etait juste, la seconde etait le defaut : ce `return` sec abandonnait TOUTE l'operation la ou
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute` -- qui ne teste la mort NULLE PART --
    ne saute QUE l'ecriture de position (le 2e gate de `SetUnitPositionOperation$$Execute`) et joue
    quand meme `$$AddTilesMoved` puis `$$EventAndAbilitiesAndEffects`.

    Le refus existe donc toujours, mais il est desormais IMPUTE a son gate natif -- d'ou
    `set-position-unit-dead` et non plus `dead`. La queue, elle, est jouee : c'est
    `test_433r3r2r1_550r4r1_untargetable_et_rang_offline.py` etage 8 qui la garde.

    `SwitchPositionOperation` ne l'avait deja pas -- le natif y traite la mort explicitement
    (`HasFlag(u, UnitFlag.Dead)`), moitie par moitie, et c'est deja porte."""
    st = State()
    st.board = _strip_board()
    _unit(st, 1, (0, 1), 10)
    mort = _unit(st, 2, (0, 2), 20)
    mort.get_component(UnitComponent).alive = False
    assert DisplaceUnitOperation(1, 2).execute(st, EventBus())["reason"] == "set-position-unit-dead"

    st2 = State()
    _unit(st2, 1, (0, 1), 10)
    m2 = _unit(st2, 2, (0, 4), 20)
    m2.get_component(UnitComponent).alive = False
    res = SwitchPositionOperation(1, 2).execute(st2, EventBus())
    assert res.get("reason") != "not displaceable"
    assert res["target_to"] is None and res["caster_to"] == (0, 4)   # moitie CIBLE muette
