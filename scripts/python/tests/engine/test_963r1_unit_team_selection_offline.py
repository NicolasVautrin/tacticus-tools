"""#963-r1 -- le 3e argument `UnitTeamSelectionType` d'`AreEnemies` / `AreFriends`.

Ce fichier garde les cinq points ou un port distrait resterait VERT partout ailleurs :

  1. **LE RECENSEMENT.** Le residu se resout en LISANT le litteral de chaque call-site natif, pas
     en generalisant depuis celui de `RedRampage`. Mesure (`probe_963r1_team_selection_callsites`,
     balayage EXHAUSTIF de l'image) : `AreEnemies` = **54** sites, `AreFriends` = **79**, dont
     **2 + 2** passent `ByOriginalTeam`. Un seul des quatre est PORTE. Figer ce compte est ce qui
     fera rougir un build ou un cinquieme site apparaitrait.
  2. **LE DEFAUT.** 129 des 133 sites passent `ByCurrentTeam` : le comportement d'avant ce residu
     y est JUSTE. Un defaut mal choisi retournerait silencieusement ces 129 sites.
  3. **LA CLE ABSENTE N'EST PAS UNE EQUIPE INCONNUE.** Un substrat qui ne modelise pas la
     possession (decision, prediction) ne publie pas `originalTeam` ; la seule reponse qui
     n'invente rien est alors l'equipe COURANTE -- qui EST l'equipe d'origine tant qu'aucun
     `ChangeUnitOwnerOperation` n'a couru. Rendre `None` la rabattrait sur << pas d'equipe >>,
     donc sur un predicat FAUX : une degradation silencieuse, dans le sens restrictif.
  4. **LE SUBSTRAT.** L'ecart n'est OBSERVABLE que sur une unite dont l'equipe courante differe de
     son origine. Le seul producteur de ce regime est l'owner-swap
     (`IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute`, effet `1209`) -- la fixture le
     JOUE, elle ne fabrique pas le couple a la main.
  5. **LE CABLAGE DE `RedRampage`.** Le litteral etait DEJA nomme dans le module
     (`TEAM_SELECTION`) sans etre passe au noeud : une constante declaree mais non consommee est
     exactement le genre de faux temoin qui fait croire le port fidele.

Aucune valeur de gameplay n'est ecrite en dur ; ce qui est fige, ce sont les LITTERAUX lus au
binaire et les STRUCTURES.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe `engine.entities.triggers` (qui tire
    # selecteurs / formules / effets), le substrat runner (`behaviours/context.py`), les
    # Operations d'owner-swap et l'arbre `red_rampage`. Sa fermeture d'import couvre l'essentiel
    # de `engine/**`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: True` -- l'etage 1 LIT `GameAssembly.dll` et fige des comptes de call-sites. Un
    # changement de build DOIT le rejouer : c'est precisement ce qu'il garde.
    "build": True,
    # `toujours: False` : l'etage 1 balaye 60 Mo de section `il2cpp` (~40 s). Les etages 2 a 6
    # sont, eux, instantanes.
    "toujours": False,
    "raison": "3e argument `UnitTeamSelectionType` d'`AreEnemies`/`AreFriends` : recensement "
              "EXHAUSTIF des 133 call-sites natifs et de leur litteral, defaut `ByCurrentTeam`, "
              "degradation d'un substrat sans possession, publication d'`originalTeam` par "
              "l'owner-swap REEL, et cablage de `ByOriginalTeam` dans l'arbre `RedRampage`.",
}

import pytest

from engine.entities.selectors.accessors import Target
from engine.entities.selectors.tiles import Caster
from engine.entities.triggers import AreEnemies, AreFriends
from engine.entities.unit_team_selection_type import UnitTeamSelectionType, team_for_selection

#: Les QUATRE sites natifs qui passent `ByOriginalTeam`, MESURES au balayage exhaustif de l'image
#: (`probe_963r1_team_selection_callsites.py`). Ecrits par leur SYMBOLE, jamais par une VA.
SITES_BY_ORIGINAL_TEAM = {
    "AreEnemies": {
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedRampage_BuffAbility$$CreateTrigger",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheArdentBlade_TriggerAbility$$CreateTrigger",
    },
    "AreFriends": {
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.Reinforcements_DamageAbility$$CreateTrigger",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheWrathfulDeadAbility_Overkill$$CreateTrigger",
    },
}
#: Nombre TOTAL de call-sites par primitive, meme mesure.
SITES_TOTAL = {"AreEnemies": 54, "AreFriends": 79}


# ---------------------------------------------------------------------------------------------
# FIXTURE NOMMEE -- le SEUL regime ou l'ecart est observable
# ---------------------------------------------------------------------------------------------
class _Entity:
    def __init__(self, comps):
        self._c = {type(c): c for c in comps}

    def get_component(self, cls):
        return self._c.get(cls)


class _State:
    def __init__(self, entities):
        self.entities = entities
        self.board = None
        self.effects = None

    def get_entity(self, uid):
        return self.entities.get(uid)


class _Ctx:
    """Contexte DSL minimal : `Caster()` lit `ctx.caster`, `Target()` lit `ctx.target`."""

    def __init__(self, caster, target):
        self.caster = caster
        self.target = target

    def __getattr__(self, _n):
        return None


@pytest.fixture(name="etat_possede")
def _etat_possede():
    """L'unite `2` (team 2 / player 4) est PASSEE sous le controle de l'unite `1` (team 1).

    Le couple `(team courante, team d'origine)` n'est PAS ecrit a la main : il est produit par
    `IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute` -- l'unique producteur natif de ce
    regime, celui que declenche l'effet `1209 AttemptedPossession_Possessed`. Un montage qui
    poserait `originalTeam` directement testerait le test, pas le port.

    Rend `(state, caster_dict, victime_dict)`."""
    from engine.runner.abilities.behaviours.context import _unit_dict
    from engine.runner.components import OwnerComponent
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation

    st = _State({1: _Entity([OwnerComponent(1, 3)]),
                 2: _Entity([OwnerComponent(2, 4)])})
    assert ChangeUnitOwnerOperation.execute(st, 2, 1) is True, \
        "l'owner-swap doit AVOIR LIEU, sinon le regime decisif n'existe pas"
    caster, victime = _unit_dict(st, 1), _unit_dict(st, 2)
    # TEMOIN NON NUL : sans cet ecart, les deux hypotheses rendraient le meme resultat et le
    # fichier entier ne conclurait RIEN (regime degenere).
    assert victime["team"] != victime["originalTeam"], \
        "regime DEGENERE : la victime doit avoir une equipe courante != de son origine"
    return st, caster, victime


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- LE RECENSEMENT (piege 1), LU au binaire
# ---------------------------------------------------------------------------------------------
def test_le_recensement_exhaustif_des_call_sites_natifs():
    """Balayage EXHAUSTIF de l'image, pas la table de xrefs.

    ⚠ `list_xrefs` de ghidra rendait **39** sites pour `AreFriends` la ou l'image en porte **79** :
    un recensement qui s'y arrete ne peut pas montrer le site qu'il a oublie. Et le pseudo-C replie
    les registres, donc le litteral affiche y est parfois une DEDUCTION du decompilateur -- 8 sites
    d'`AreFriends` alimentent leur 5e argument depuis un registre."""
    import probe_963r1_team_selection_callsites as P

    r = P.Recenseur()
    for court, total in SITES_TOTAL.items():
        sites = r.mesurer(court)
        assert len(sites) == total, \
            "%s : %d call-sites mesures, %d attendus" % (court, len(sites), total)
        indet = [fn for _va, fn, sel, _p in sites if sel is None]
        assert not indet, "selectionType INDETERMINE (aucune valeur n'est devinee) : %s" % indet
        by_orig = {fn for _va, fn, sel, _p in sites if sel == int(UnitTeamSelectionType.ByOriginalTeam)}
        assert by_orig == SITES_BY_ORIGINAL_TEAM[court], \
            "%s : les sites `ByOriginalTeam` ont bouge -- mesure=%s attendu=%s" \
            % (court, sorted(by_orig), sorted(SITES_BY_ORIGINAL_TEAM[court]))
        hors = {sel for _va, _fn, sel, _p in sites} - {0, 1}
        assert not hors, "un litteral HORS des deux membres de l'enum est apparu : %s" % hors


def test_un_seul_des_quatre_sites_by_original_team_est_porte():
    """La question binaire du residu : le port ECARTE-t-il un call-site qui devrait lire l'origine ?

    Reponse MESUREE : sur les 4 sites natifs qui passent `ByOriginalTeam`, un SEUL a un arbre porte
    -- `RedRampage_BuffAbility`. Les trois autres (`TheArdentBlade_TriggerAbility`,
    `Reinforcements_DamageAbility`, `TheWrathfulDeadAbility_Overkill`) n'ont AUCUN arbre DSL cote
    port : leur id vit dans les enums, rien de plus. Ce test fige ce fait -- le jour ou l'un des
    trois est porte, il doit poser son litteral DANS LE MEME COMMIT, exactement comme un masque de
    ciblage."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.operations.triggers.dispatch import registry as R

    # PERIMETRE DERIVE, jamais une liste ecrite : tout attribut du module qui est un conteneur de
    # classes de trigger. Une allowlist de registres ne pourrait pas montrer le registre oublie --
    # c'est le vice que le recenseur de #270-r1 a du corriger.
    classes = set()

    def _avaler(v):
        if isinstance(v, type):
            classes.add(v)
        elif isinstance(v, (list, tuple, set, frozenset)):
            for x in v:
                _avaler(x)

    for nom in dir(R):
        if nom.startswith("__"):
            continue
        val = getattr(R, nom)
        if isinstance(val, dict):
            for v in val.values():
                _avaler(v)
        else:
            _avaler(val)
    portes = {int(i) for i in (getattr(c, "TRIGGERED_ABILITY_ID", None) for c in classes)
              if isinstance(i, int)}
    assert portes, "perimetre VIDE : le balayage du registre n'a rien trouve (test auto-invalide)"
    assert int(TriggeredAbilityType.RedRampage) in portes, \
        "RedRampage doit etre porte -- c'est le SEUL des quatre a l'etre"
    for nom in ("TheArdentBlade", "Reinforcements", "TheWrathfulDead"):
        membre = getattr(TriggeredAbilityType, nom, None)
        if membre is None:
            continue
        assert int(membre) not in portes, (
            "%s est desormais PORTE : son arbre doit passer explicitement son litteral "
            "`UnitTeamSelectionType` a `AreEnemies`/`AreFriends` (cf. SITES_BY_ORIGINAL_TEAM)" % nom)


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- LE FOYER `team_for_selection` (pieges 2 et 3)
# ---------------------------------------------------------------------------------------------
def test_le_foyer_choisit_la_bonne_equipe():
    u = {"id": 7, "team": 1, "originalTeam": 2}
    assert team_for_selection(u, UnitTeamSelectionType.ByCurrentTeam) == 1
    assert team_for_selection(u, UnitTeamSelectionType.ByOriginalTeam) == 2


def test_une_cle_originalTeam_ABSENTE_degrade_sur_l_equipe_COURANTE():
    """Piege 3. Un substrat qui ne modelise pas la possession ne publie pas `originalTeam` ; y
    repondre `None` rabattrait le predicat sur FAUX -- degradation RESTRICTIVE silencieuse."""
    u = {"id": 7, "team": 2}
    assert team_for_selection(u, UnitTeamSelectionType.ByOriginalTeam) == 2, \
        "cle absente => equipe COURANTE (== l'origine tant qu'aucun owner-swap n'a couru)"


def test_une_valeur_HORS_enum_rend_None_le_return_false_natif():
    """`IdunBattle.Entities.UnitExtensions$$IsFriend` a une 3e branche : toute valeur autre que
    `0`/`1` fait `return false`. Aucun call-site natif ne l'emprunte (etage 1), mais elle EXISTE au
    decompile."""
    u = {"id": 7, "team": 1, "originalTeam": 2}
    assert team_for_selection(u, 7) is None


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- LES DEUX NOEUDS, sur le regime decisif (piege 4)
# ---------------------------------------------------------------------------------------------
def test_areenemies_bascule_avec_le_selecteur_d_equipe(etat_possede):
    """MESURE AVANT/APRES, sur la MEME entree : seule la valeur du 3e argument change.

    Une victime passee sous MON controle est ALLIEE au courant et ENNEMIE a l'origine. C'est
    exactement le cas ou Cezare doit gagner son +1 Movement."""
    _st, caster, victime = etat_possede
    ctx = _Ctx(caster, victime)
    par_courant = AreEnemies(Caster(), Target(), UnitTeamSelectionType.ByCurrentTeam).evaluate(ctx)
    par_origine = AreEnemies(Caster(), Target(), UnitTeamSelectionType.ByOriginalTeam).evaluate(ctx)
    assert par_courant is False, "equipe COURANTE : la victime possedee est une ALLIEE"
    assert par_origine is True, "equipe D'ORIGINE : la victime reste une ENNEMIE"


def test_arefriends_bascule_en_MIROIR(etat_possede):
    _st, caster, victime = etat_possede
    ctx = _Ctx(caster, victime)
    assert AreFriends(Caster(), Target(), UnitTeamSelectionType.ByCurrentTeam).evaluate(ctx) is True
    assert AreFriends(Caster(), Target(), UnitTeamSelectionType.ByOriginalTeam).evaluate(ctx) is False


def test_le_DEFAUT_des_deux_noeuds_est_ByCurrentTeam(etat_possede):
    """Piege 2 : 129 des 133 call-sites natifs passent `0`. Le defaut doit reproduire EXACTEMENT
    le comportement d'avant ce residu pour eux."""
    _st, caster, victime = etat_possede
    ctx = _Ctx(caster, victime)
    assert AreEnemies(Caster(), Target()).selection_type == int(UnitTeamSelectionType.ByCurrentTeam)
    assert AreFriends(Caster(), Target()).selection_type == int(UnitTeamSelectionType.ByCurrentTeam)
    assert AreEnemies(Caster(), Target()).evaluate(ctx) is False
    assert AreFriends(Caster(), Target()).evaluate(ctx) is True


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- LE SUBSTRAT publie l'equipe d'ORIGINE, et l'owner-swap la produit
# ---------------------------------------------------------------------------------------------
def test_le_substrat_publie_originalTeam_depuis_l_owner_swap_REEL(etat_possede):
    st, _caster, victime = etat_possede
    from engine.runner.abilities.behaviours.context import _unit_dict
    from engine.runner.operations.change_unit_owner import ResetUnitOwnerOperation

    assert (victime["team"], victime["originalTeam"]) == (1, 2), \
        "apres swap : equipe COURANTE = celle du posseur, ORIGINE = la sienne"
    assert ResetUnitOwnerOperation.execute(st, 2) is True
    apres = _unit_dict(st, 2)
    assert (apres["team"], apres["originalTeam"]) == (2, 2), \
        "apres revert : les deux se rejoignent, bit pour bit"


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- LE CABLAGE de `RedRampage` (piege 5)
# ---------------------------------------------------------------------------------------------
def _feuilles(noeud, out=None):
    out = [] if out is None else out
    out.append(noeud)
    for attr in ("a", "b"):
        v = getattr(noeud, attr, None)
        if hasattr(v, "evaluate"):
            _feuilles(v, out)
    return out


def test_l_arbre_RedRampage_PASSE_son_litteral_au_noeud():
    """Le module NOMMAIT deja `TEAM_SELECTION = ByOriginalTeam` sans le passer : une constante
    declaree mais non consommee est un faux temoin de fidelite. On assertionne la valeur PORTEE PAR
    LE NOEUD de l'arbre construit, pas la constante du module."""
    from engine.runner.operations.triggers.loki.red_rampage import (TEAM_SELECTION,
                                                                    red_rampage_buff_trigger_tree)
    noeuds = [n for n in _feuilles(red_rampage_buff_trigger_tree())
              if isinstance(n, AreEnemies)]
    assert len(noeuds) == 1, "l'arbre du buff porte exactement un `AreEnemies`"
    assert noeuds[0].selection_type == int(UnitTeamSelectionType.ByOriginalTeam)
    assert noeuds[0].selection_type == int(TEAM_SELECTION), \
        "le noeud doit porter LE litteral du module, pas une valeur recopiee"


def test_l_arbre_RedRampage_FIRE_sur_une_victime_passee_sous_MON_controle(etat_possede):
    """Le fait de gameplay, bout en bout : Cezare tue un ennemi passe sous controle du joueur.

    Le terme `AreEnemies` de l'arbre est le SEUL a dependre de l'equipe ; on l'evalue isole sur le
    contexte, puis on verifie que l'arbre COMPLET n'ecarte pas la victime pour cette raison."""
    from engine.runner.operations.triggers.loki.red_rampage import red_rampage_buff_trigger_tree
    _st, caster, victime = etat_possede
    ctx = _Ctx(caster, victime)
    terme = [n for n in _feuilles(red_rampage_buff_trigger_tree()) if isinstance(n, AreEnemies)][0]
    assert terme.evaluate(ctx) is True, \
        "AVANT #963-r1 ce terme rendait False : le +1 Movement etait REFUSE a tort"
