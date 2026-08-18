"""#498-r4 -- la face DECISION d'`IsDisplaceable` : ce qu'on NE cable PAS, et ce qui MORDAIT.

#498-r3 a ferme le volet RUNNER (foyer unique, 4 refus + tete). Restaient les deux miroirs de
DECISION -- `MortisRoundPlaybook._is_displaceable` et `ItItchesPlaybook._is_displaceable` -- qui ne
portent ni `HasFlag(0x19 = UnitFlag.Undisplaceable)` ni la tete `EntityType == Unit`.

LES DEUX CONDITIONS NE SONT PAS CABLEES, ET LES DEUX VERDICTS SONT MESURES, PAS SUPPOSES :

  * **`UnitFlag.Undisplaceable`** -- recensement EXHAUSTIF des ecrivains natifs du flag, sur les
    DEUX voies : `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag` a **10** appelants (litteral relu
    a chacun : `0x0, 0x1, 0x15, 0x16, 0x16, 0x17, 0x18, 0x18, 0x19, 0x1c`) -- **UN SEUL** pose
    `0x19`, `...UnstoppableMomentumReworkedAbility$$ExecuteBehaviour`, qui porte le `RemoveFlag`
    apparie dans la MEME fonction ; `IdunBattle.Entities.Components.UnitFlagsComponent$$Add` a
    **40** sites de jeu, litteral relu a chacun, qui posent 21 ordinaux distincts et JAMAIS `0x19` ;
    `UnitFlagsComponent$$.ctor` construit un `OrderedSet` VIDE ; `$$RemoveTurnFlags` ne retire que
    `0, 1, 2, 3, 4, 0xc, 0x1b`. Le flag n'existe donc qu'a l'INTERIEUR d'une execution d'ability.
  * **`EntityType == Unit`** -- STRUCTURELLEMENT inerte : le `unit` des deux miroirs ne vient que de
    `ctx.units`, dont le foyer offline (`ai/state_bridge.py::_dv_units`) EXCLUT les MoW et dont le
    foyer live est `decisionView.units`, canal separe de `.mows`.

CE QUI MORDAIT, ET QUE LE CADRAGE DU RESIDU CACHAIT : `ItItchesPlaybook._is_displaceable` lisait
`_traits(visualId)` -- le KIT gameconfig SEUL -- la ou le natif lit
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` (la collection `+0x48`/`+0x40`, qui
porte AUSSI les traits ACCORDES EN BATAILLE). Ecart PERMISSIF, meme famille exacte que les six
copies divergentes de #498-r3. C'est CE volet qui est porte ici.

LES ETAGES :
  1. le tuple des trois traits a UN SEUL foyer (les trois sites designent le MEME objet) ;
  2. `ItItchesPlaybook` lit les traits ACCORDES -- et le MUTANT (kit seul) est SEPARE ;
  3. les deux miroirs se comportent IDENTIQUEMENT sur le meme substrat ;
  4. la tete `EntityType` est inerte PAR CONSTRUCTION du canal (`_dv_units` exclut les MoW), et
     c'est verifie sur un `State` qui PORTE une MoW, pas sur une lecture de source ;
  5. le recenseur `probe_498r3_is_displaceable_sites.py` juge par AST et non par PROSE -- une
     docstring qui NOMME une condition ne doit plus crediter le site de cette condition.

100 % OFFLINE. ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: PERIMETRE MESURE : l'import de ce module charge `engine/**` (le playbook tire tout le paquet) et
#: exactement trois modules hors `engine/` -- `gameconfig.py`, `hexgeo.py`, plus le probe recense.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER. `engine/**` en bloc, et c'est une MESURE : l'etage 5 fait PARCOURIR
        # tout `engine/**` au recenseur, donc toute feuille y entre. Foyers load-bearing, pour la
        # relecture : `engine/runner/components.py` (`NOT_DISPLACEABLE_TRAITS` + le foyer),
        # `engine/playbook/loki_custom.py` et `engine/playbook/noncomparable/it_itches.py` (les
        # deux miroirs), `engine/ai/state_bridge.py` (`_dv_units`, la tete),
        # `engine/entities/traits/unit_trait.py` (`entity_trait_names`).
        "scripts/python/engine/**/*.py",
        # La couche de modules de TETE : le recenseur joue a l'etage 5
        # (`probe_498r3_is_displaceable_sites.py`, `catalog_inject.py` pour son `enum_map`), plus
        # les **15** chemins que la cascade des `conftest.py` tire et qui vivent tous DIRECTEMENT
        # sous `scripts/python/` (`engine_validate.py`, `board.py`, `enum_maps.py`, `host_inputs.py`,
        # les `probe_17_*`...) -- mesure `probe_486r15_declencheurs_tests.py`. Glob NON RECURSIF :
        # il EXCLUT `tests/**`.
        "scripts/python/*.py",
        # L'etage 0 du recenseur QUALIFIE les six ordinaux contre la table d'enums du BUILD.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : le foyer UNIQUE du tuple des trois traits refusants, le substrat de "
              "traits d'`ItItchesPlaybook` (traits ACCORDES en bataille, avec son MUTANT kit-seul "
              "separe), l'accord des deux miroirs de DECISION sur le meme substrat, l'inertie "
              "STRUCTURELLE de la tete `EntityType` (mesuree sur un State portant une MoW), et le "
              "fait que le recenseur juge par AST et non par PROSE. Aucun runner, aucune session "
              "Frida. `build: True` parce que l'etage 0 du recenseur lit la table d'enums du build "
              "et que `gameconfig.py` est dans la fermeture.",
}

import subprocess                                                        # noqa: E402
import sys                                                               # noqa: E402
from pathlib import Path                                                 # noqa: E402

PYDIR = Path(__file__).resolve().parents[2]                              # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.ai import state_bridge as SB                                 # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                  # noqa: E402
from engine.entities.unit_context import UnitContext                     # noqa: E402
from engine.playbook.loki_custom import MortisRoundPlaybook              # noqa: E402
from engine.playbook.noncomparable.it_itches import ItItchesPlaybook     # noqa: E402
from engine.runner.components import (MachineComponent, OwnerComponent,  # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.state import State                                    # noqa: E402

# ⚠ `NOT_DISPLACEABLE_TRAITS` EST IMPORTE **DANS** SES TESTS, PAS EN TETE, et c'est la seule
# raison : le nom n'existe pas sur l'arbre TEMOIN (il y est prive, `_NOT_DISPLACEABLE_TRAITS`),
# donc en tete il ferait echouer la **COLLECTE** et la vue rouge se reduirait a UNE ligne
# d'`ImportError` au lieu d'une ventilation par etage. Meme mesure qu'en #287-r11-r1-r1.


class _Scene:
    """Le minimum que les deux miroirs demandent a `ctx.scene` : `ctx(uid) -> UnitContext`."""

    def __init__(self, by_id):
        self._by_id = by_id

    def ctx(self, uid):
        return self._by_id.get(uid)


class _Ctx:
    def __init__(self, units, scene=None):
        self.units = units
        self.scene = scene


def _uctx(traits, entity_id=7, visual_id="__kit_sans_trait__"):
    """Un `UnitContext` dont la liste `traits` est celle de l'ENTITE (kit + accordes en bataille).

    `traits_measured=True` : c'est le regime d'un etat CHARGE (`snapshot._load_unit_traits` a lu
    `combatSnapshot.units[].traits`), et il court-circuite la derivation d'alliance -- donc la
    liste posee ici est EXACTEMENT ce que le port lira."""
    return UnitContext(entity_id=entity_id, visual_id=visual_id,
                       traits=list(traits), traits_measured=True)


# =================================================================================================
# ETAGE 1 -- LE TUPLE DES TROIS TRAITS N'A QU'UN FOYER
# =================================================================================================

def test_les_trois_sites_partagent_LE_MEME_tuple():
    """Trois exemplaires du meme tuple existaient (`runner/components.py`, `loki_custom.py`,
    `it_itches.py`). #498-r3 a montre ce que devient une liste recopiee : elle DIVERGE. Le test
    compare les OBJETS, pas leur contenu -- deux tuples egaux aujourd'hui restent libres de diverger
    demain, et c'est precisement le gisement."""
    from engine.playbook.noncomparable import it_itches as II
    from engine.runner.components import NOT_DISPLACEABLE_TRAITS
    assert MortisRoundPlaybook._NOT_DISPLACEABLE is NOT_DISPLACEABLE_TRAITS
    assert II._NOT_DISPLACEABLE is NOT_DISPLACEABLE_TRAITS
    assert tuple(NOT_DISPLACEABLE_TRAITS) == (UnitTrait.Immovable, UnitTrait.Hulking,
                                              UnitTrait.BigTarget)


# =================================================================================================
# ETAGE 2 -- LE SUBSTRAT DE TRAITS : ACCORDES EN BATAILLE, PAS SEULEMENT LE KIT
# =================================================================================================

def test_it_itches_refuse_un_trait_ACCORDE_en_bataille():
    """L'ECART REPARE. Le natif lit `BaseUnitComponent$$HasTrait`, donc la collection de l'ENTITE ;
    ce site lisait le KIT gameconfig seul, et jugeait poussable une unite qui s'est vu ACCORDER
    `BigTarget` en cours de bataille. Direction : PERMISSIVE."""
    unit = {"id": 7, "visualId": "__kit_sans_trait__", "alive": True}
    ctx_nu = _Ctx(units=[unit], scene=_Scene({7: _uctx([])}))
    ctx_big = _Ctx(units=[unit], scene=_Scene({7: _uctx([UnitTrait.BigTarget.name])}))
    assert ItItchesPlaybook._is_displaceable(ctx_nu, unit) is True
    assert ItItchesPlaybook._is_displaceable(ctx_big, unit) is False, (
        "le trait ACCORDE en bataille n'est pas lu -- le site est retombe sur le kit gameconfig")


def test_MUTANT_lire_le_KIT_seul_est_SEPARE():
    """FRONTIERE, et le test ASSERTIONNE SON PROPRE NON-VIDE : si aucun regime ne separait
    `entity_trait_names` du kit seul, l'etage precedent serait vert sans rien mesurer."""
    from engine.entities.traits.unit_trait import has_any_trait, unit_trait_names
    from engine.runner.components import NOT_DISPLACEABLE_TRAITS
    unit = {"id": 7, "visualId": "__kit_sans_trait__", "alive": True}
    separateurs = []
    for accorde in ([UnitTrait.Immovable.name], [UnitTrait.Hulking.name],
                    [UnitTrait.BigTarget.name]):
        ctx = _Ctx(units=[unit], scene=_Scene({7: _uctx(accorde)}))
        vrai = ItItchesPlaybook._is_displaceable(ctx, unit)
        mutant = not has_any_trait(unit_trait_names(unit["visualId"]), NOT_DISPLACEABLE_TRAITS)
        if vrai != mutant:
            separateurs.append(accorde[0])
    assert len(separateurs) == 3, separateurs


def test_scene_absente_retombe_sur_le_substrat_STATIQUE_sans_lever():
    """`ctx.scene is None` (contexte construit a la main) : `entity_trait_names(None, visualId)` est
    une BORNE documentee, pas une regression -- c'est exactement le comportement d'avant."""
    unit = {"id": 7, "visualId": "__kit_sans_trait__", "alive": True}
    assert ItItchesPlaybook._is_displaceable(_Ctx(units=[unit]), unit) is True


# =================================================================================================
# ETAGE 3 -- LES DEUX MIROIRS SE COMPORTENT IDENTIQUEMENT
# =================================================================================================

def test_les_deux_miroirs_rendent_le_MEME_verdict():
    """Deux miroirs du MEME predicat natif qui divergent sont un bug par construction. Le test
    balaye les quatre regimes qui comptent, et exige l'ACCORD."""
    regimes = [
        ("aucun trait", [], True),
        ("Immovable", [UnitTrait.Immovable.name], False),
        ("Hulking", [UnitTrait.Hulking.name], False),
        ("BigTarget", [UnitTrait.BigTarget.name], False),
    ]
    vus = set()
    for libelle, traits, attendu in regimes:
        unit = {"id": 7, "visualId": "__kit_sans_trait__", "alive": True}
        ctx = _Ctx(units=[unit], scene=_Scene({7: _uctx(traits)}))
        a = MortisRoundPlaybook._is_displaceable(ctx, unit)
        b = ItItchesPlaybook._is_displaceable(ctx, unit)
        assert a is b is attendu, (libelle, a, b, attendu)
        vus.add(attendu)
    assert vus == {True, False}, "regime DEGENERE : tous les cas rendent le meme verdict"


def test_les_deux_miroirs_refusent_None_donc_tout_non_unite():
    """La tete native `EntityType != Unit -> false` est INERTE ici parce que le substrat ne peut pas
    presenter autre chose qu'une unite : un id absent de `ctx.units` rend `None` en amont, et les
    deux miroirs refusent `None`."""
    ctx = _Ctx(units=[], scene=_Scene({}))
    assert MortisRoundPlaybook._unit(ctx, 999) is None
    assert MortisRoundPlaybook._is_displaceable(ctx, None) is False
    assert ItItchesPlaybook._is_displaceable(ctx, None) is False


# =================================================================================================
# ETAGE 4 -- LA TETE `EntityType == Unit` EST INERTE **PAR CONSTRUCTION DU CANAL**
# =================================================================================================

def test_le_canal_de_decision_ne_publie_AUCUNE_machine_of_war():
    """MESURE, pas lecture de source : on construit un `State` qui PORTE une MoW et on verifie
    qu'elle n'entre ni dans `_dv_units` (le `ctx.units` de la face DECISION) ni dans `_obs_units`.

    C'est ce fait -- et lui seul -- qui rend la tete `EntityType == Unit` inerte cote decision. Le
    jour ou le canal publierait les MoW, ce test ROUGIT et la tete devra etre portee."""
    st = State()
    st.current_player_id = 3
    for eid, vis, mow in ((10, "unite", False), (11, "astraOrdnanceBattery", True)):
        e = st.add_entity(eid)
        e.add_component(OwnerComponent(team=3, player=3))
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(PositionComponent(col=1, row=1))
        e.add_component(StatsComponent(ctx=_uctx([], entity_id=eid, visual_id=vis)))
        if mow:
            e.add_component(MachineComponent())
    ids_dv = {u["id"] for u in SB._dv_units(st)}
    ids_obs = {u["squadId"] for u in SB._obs_units(st)}
    assert 10 in ids_dv and 10 in ids_obs, "l'unite ordinaire doit etre publiee"
    assert 11 not in ids_dv, "une MoW est entree dans `ctx.units` -- la tete EntityType MORD"
    assert 11 not in ids_obs


# =================================================================================================
# ETAGE 5 -- LE RECENSEUR JUGE PAR AST, PAS PAR PROSE
# =================================================================================================

def test_le_recenseur_ne_credite_pas_une_condition_seulement_CITEE():
    """LE FAUX VERT MESURE PENDANT CETTE TRANCHE. Le recenseur creditait une condition des que son
    nom apparaissait dans le TEXTE de la fonction -- donc dans une docstring qui EXPLIQUE qu'on ne
    la porte pas. Les deux miroirs de DECISION nomment desormais `UnitFlag.Undisplaceable` et
    `unit_extensions_is_displaceable` dans leur prose : ils doivent rester `MIROIR`, et leur
    `manque` doit rester NON VIDE."""
    import probe_498r3_is_displaceable_sites as P
    rec = P.etape_recensement()
    decision = {"%s::%s" % (s["fichier"], s["fonction"]): s
                for s in rec["sites"] if s["face"] == "DECISION" and s["fonction"] == "_is_displaceable"}
    # ⚠ BORNE INFERIEURE, ET C'EST L'ASYMETRIE QUI COMPTE. Ce compte etait `== 2` : un SEUIL
    # HAUT, qui se perime des qu'un port LEGITIME ajoute un miroir -- c'est arrive avec
    # `noncomparable/unstoppable_momentum.py` (PR #844), et `master` en est reste ROUGE.
    # Or le compte n'est PAS le fond de ce test : c'est l'ancrage de NON-VACUITE de la boucle
    # ci-dessous, qui porte les vraies proprietes (role, delegue, manque, traits). Mesure du
    # 2026-08-08 sur les 3 sites : **3/3 CONFORMES** -- la garde n'avait donc rien perdu, seul
    # son ancrage avait vieilli.
    # Une borne BASSE rougit sur ce qui est un vrai signal (un miroir qui DISPARAIT) et se tait
    # sur ce qui n'en est pas un (un miroir de plus, que la boucle verifie de toute facon).
    # Passer a `== 3` n'aurait fait que reporter la meme panne au 4e port.
    assert len(decision) >= 2, sorted(decision)
    for nom, s in decision.items():
        assert s["role"] == "MIROIR", (nom, s["role"])
        assert set(s["manque"]) == {"EntityType", "Undisplaceable"}, (nom, s["manque"])
        # ⚠ #498-r4-r2 -- `traits_EFFECTIFS`, PAS `traits_en_dur`. Un site qui DELEGUE son corps a
        # un foyer partage n'a, par construction, aucun trait EN DUR : c'est le but de la
        # factorisation. Exiger `traits_en_dur` ici revenait a exiger la DUPLICATION -- le vice
        # meme que `_alias_traits_global` avait deja du corriger sur l'axe des CONSTANTES. La
        # propriete a garder est que le recenseur VOIE encore les traits, que le corps soit sur
        # place ou dans le foyer.
        assert s["traits_effectifs"] == ["BigTarget", "Hulking", "Immovable"], (
            "%s a perdu ses traits : le recenseur ne resout plus la constante PARTAGEE ni la "
            "DELEGATION, donc il recompense la duplication" % nom)


def test_un_DELEGANT_ne_porte_JAMAIS_plus_que_son_delegataire():
    """LE FAUX VERT QUE LA GENERALISATION DE `delegue` AURAIT PU FABRIQUER (#498-r4-r2).

    L'ancien `delegue` creditait `set(CONDITIONS)` -- les CINQ -- d'office. C'etait juste tant que
    l'unique cible etait le foyer RUNNER, qui les porte toutes. Generaliser cette forme aux foyers
    de DECISION aurait rendu `manque = []` pour `loki_custom::_is_displaceable`, alors que son
    delegataire `displace_utility::is_displaceable` n'en porte que TROIS : le port aurait declare
    porter `Undisplaceable` et `EntityType` sans que personne ne les ecrive nulle part.

    Ce test fige le sens de la propagation : le manque TRAVERSE la delegation."""
    import probe_498r3_is_displaceable_sites as P
    rec = P.etape_recensement()
    par_cle = {"%s::%s" % (s["fichier"], s["fonction"]): s for s in rec["sites"]}

    delegant = par_cle.get("playbook/loki_custom.py::_is_displaceable")
    delegataire = par_cle.get("playbook/displace_utility.py::is_displaceable")
    assert delegant is not None and delegataire is not None, sorted(par_cle)
    # NON-VACUITE : un delegataire qui porterait TOUT rendrait l'egalite ci-dessous sans contenu.
    assert delegataire["manque"], (
        "le delegataire ne manque RIEN -- ce test ne distinguerait plus l'heritage fidele du "
        "credit d'office ; re-choisir un couple discriminant")
    assert delegant["delegue"] is True, (
        "`loki_custom::_is_displaceable` n'est plus vu comme delegant : son corps vit dans "
        "`displace_utility` depuis #977, et le recenseur doit suivre l'appel")
    assert delegant["manque"] == delegataire["manque"], (
        "le delegant porte %s et son delegataire %s -- un delegant ne peut pas porter plus que "
        "ce qu'il appelle" % (delegant["porte"], delegataire["porte"]))
    assert delegant["porte"] == delegataire["porte"]

    # Le pendant RUNNER, inchange : la ou le delegataire EST le foyer, l'heritage vaut bien 5.
    foyer = par_cle.get("runner/components.py::unit_extensions_is_displaceable")
    op = next((s for s in rec["sites"]
               if s["fichier"] == "runner/operations/displace.py"
               and s["classe"] == "DisplaceUnitOperation" and s["fonction"] == "execute"), None)
    assert foyer is not None and op is not None, sorted(par_cle)
    assert op["delegue"] is True, "le delegant RUNNER n'est plus vu comme tel"
    assert not foyer["manque"] and not op["manque"], (foyer["manque"], op["manque"])


def test_CONTRE_EPREUVE_une_docstring_ne_credite_RIEN():
    """SANS CE TEST, LE PRECEDENT SERAIT VERT SUR L'ARBRE D'AVANT, donc il ne garderait pas le
    DURCISSEMENT -- seulement la prose qui l'a revele. On soumet ici au recenseur une fonction dont
    la DOCSTRING nomme les trois choses qui creditaient : le foyer, le flag et les traits.

    Un critere TEXTUEL la classerait `delegue` (donc 5/5 conditions portees) ; le critere AST doit
    n'en crediter AUCUNE."""
    import ast
    import probe_498r3_is_displaceable_sites as P
    src = (
        'def _piege(unit):\n'
        '    """Ce site NE porte PAS `UnitFlag.Undisplaceable`, ne DELEGUE PAS a\n'
        '    `unit_extensions_is_displaceable`, ne lit ni `UnitTrait.Immovable` ni\n'
        '    `UnitTrait.BigTarget` ni `MachineComponent`. Il le DIT, il ne le FAIT pas."""\n'
        '    return True\n')
    node = ast.parse(src).body[0]
    symb = P._symboles(node)
    appels = P._appels(node)
    for interdit in ("UnitFlag.Undisplaceable", "UnitTrait.Immovable", "UnitTrait.BigTarget",
                     "MachineComponent"):
        assert interdit not in symb, (
            "`%s` est credite depuis une DOCSTRING -- le critere est redevenu textuel" % interdit)
    assert P.FOYER_CALL not in appels, (
        "la DELEGATION est deduite d'une mention en prose, pas d'un appel")
    # ...et la contre-epreuve de la contre-epreuve : le MEME symbole, ECRIT DANS LE CODE, compte.
    vrai = ast.parse('def _vrai(u):\n'
                     '    return u.flags.has(UnitFlag.Undisplaceable)\n').body[0]
    assert "UnitFlag.Undisplaceable" in P._symboles(vrai), (
        "le critere AST ne voit plus le symbole ECRIT -- il ne mesurerait plus rien")


def test_le_recenseur_reste_vert_et_le_cliquet_RUNNER_aussi():
    """Le volet RUNNER de #498-r3 ne doit pas bouger : un seul foyer, zero copie, zero incomplet."""
    r = subprocess.run([sys.executable, "probe_498r3_is_displaceable_sites.py"],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, (r.stdout or "")[-2000:]
    import probe_498r3_is_displaceable_sites as P
    cli = P.etape_cliquet(P.etape_recensement())
    assert cli["copies"] == [] and cli["incomplets"] == []
    assert cli["miroirs_runner"] >= 7
