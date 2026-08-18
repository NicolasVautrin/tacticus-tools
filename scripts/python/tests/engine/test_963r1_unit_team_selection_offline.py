"""#963-r1 -- le 3e argument `UnitTeamSelectionType` d'`AreEnemies` / `AreFriends`.

Ce fichier garde les cinq points ou un port distrait resterait VERT partout ailleurs :

  1. **LE RECENSEMENT.** Le residu se resout en LISANT le litteral de chaque call-site natif, pas
     en generalisant depuis celui de `RedRampage`. Mesure (`probe_963r1_team_selection_callsites`,
     balayage EXHAUSTIF de l'image) : `AreEnemies` = **54** sites, `AreFriends` = **79**, dont
     **2 + 2** passent `ByOriginalTeam`. Figer ce compte est ce qui fera rougir un build ou un
     cinquieme site apparaitrait.
     ⚠ **Le nombre de sites PORTES n'est PAS un compteur de ce fichier**, et c'est delibere : il
     monte a chaque tranche de portage (1 au 2026-08-13 avec `RedRampage`, **2** au 2026-08-14 avec
     `TheArdentBlade`, #1013-r2). Ce qui est garde, c'est que **tout site porte PASSE son litteral
     au noeud** -- une exigence qui ne se perime pas, la ou un compte qu'on incremente pour faire
     passer une passe serait l'inventaire deguise en garde-fou que la doctrine proscrit.
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


def _ids_de(valeurs):
    """Les `TRIGGERED_ABILITY_ID` de toutes les classes ATTEIGNABLES dans `valeurs`.

    ⚠ **UNE VALEUR DE DICT EST UNE VOIE D'ATTEINTE**, et l'oublier a rendu `master` ROUGE. Ce
    balayage descendait dans `list/tuple/set/frozenset` mais PAS dans `dict` : les neuf classes de
    `PowerUp_*Spawn_*` (#10004) sont FABRIQUEES par `type()` dans une comprehension et n'existent
    sous AUCUN nom -- elles ne vivent que comme valeurs de `POWER_UP_SPAWN_ABILITIES`, le seul
    objet que `registry.py` importe. Le balayage dit LARGE en rendait donc 102 quand `_ids_inscrits`
    -- qui itere `d.values()` explicitement -- en rendait 111. « Un recenseur ne peut pas rendre
    zero sur ce qu'il ne visite pas », a la lettre : ce n'etait pas une incoherence du port mais un
    trou du RECENSEUR.

    `vus` garde la recursion finie si une structure se contient elle-meme."""
    classes = set()
    vus = set()

    def _avaler(v):
        if isinstance(v, type):
            classes.add(v)
            return
        if id(v) in vus:
            return
        if isinstance(v, dict):
            vus.add(id(v))
            for cle, val in v.items():          # une CLE peut etre une classe (registre indexe)
                _avaler(cle)
                _avaler(val)
        elif isinstance(v, (list, tuple, set, frozenset)):
            vus.add(id(v))
            for x in v:
                _avaler(x)

    for v in valeurs:
        _avaler(v)
    return {int(i) for i in (getattr(c, "TRIGGERED_ABILITY_ID", None) for c in classes)
            if isinstance(i, int)}


def _ids_par_NOM_de_module():
    """Les ids des classes de trigger qui sont un attribut DIRECT de `registry` -- donc celles
    qu'un `import` NOMME.

    Base VOLONTAIREMENT independante de `_ids_de` : elle ne descend dans AUCUN conteneur. Elle ne
    sert qu'a exhiber la population « atteignable UNIQUEMENT par un conteneur », qui est le regime
    que le controle de coherence garde -- et qui, sans elle, ne serait plus observable."""
    from engine.runner.operations.triggers.dispatch import registry as R
    out = set()
    for n in dir(R):
        if n.startswith("__"):
            continue
        v = getattr(R, n)
        i = getattr(v, "TRIGGERED_ABILITY_ID", None) if isinstance(v, type) else None
        if isinstance(i, int):
            out.add(int(i))
    return out


def _ids_connus():
    """Les `TriggeredAbilityType` dont une classe de trigger EXISTE et est atteignable depuis le
    module de registre -- **y compris par un simple import de module**.

    PERIMETRE LARGE et DERIVE, jamais une liste ecrite : tout attribut du module. Une allowlist de
    registres ne pourrait pas montrer le registre oublie -- c'est le vice que le recenseur de
    #270-r1 a du corriger. C'est la bonne mesure pour « cette ability a-t-elle un ARBRE porte ? ».

    ⚠ Ce n'est PAS « inscrite dans un registre » : `registry.py` importe ses classes au niveau
    module, donc chacune est un attribut. Confondre les deux rendait ce fichier AVEUGLE au retrait
    d'une entree de registre -- mesure : la mutation << TheArdentBlade sort du registre >> restait
    VERTE. D'ou le second recenseur ci-dessous."""
    from engine.runner.operations.triggers.dispatch import registry as R
    return _ids_de(getattr(R, n) for n in dir(R) if not n.startswith("__"))


def _ids_inscrits():
    """Les `TriggeredAbilityType` REELLEMENT inscrits -- les VALEURS des dicts de registre, et elles
    seules. C'est ce que lit `collect_triggered_abilities` ; une classe seulement importee ne fire
    JAMAIS."""
    from engine.runner.operations.triggers.dispatch import registry as R
    dicts = [getattr(R, n) for n in dir(R) if not n.startswith("__")]
    return _ids_de(v for d in dicts if isinstance(d, dict) for v in d.values())


#: Pour chacun des QUATRE sites `ByOriginalTeam`, le NOM du membre `TriggeredAbilityType` et, quand
#: l'arbre est PORTE, la fabrique qui le construit. La PRIMITIVE attendue (`AreEnemies` /
#: `AreFriends`) n'est PAS ecrite ici : elle est DERIVEE de `SITES_BY_ORIGINAL_TEAM` -- la meme
#: mesure sert au recensement (etage 1) et a la verification, donc les deux ne peuvent pas diverger.
#:
#: ⚠ **Une entree `arbre = None` est un FAIT MESURE, pas une dispense.** Elle dit « cette ability
#: n'a AUCUN arbre DSL cote port : son id vit dans les enums, rien de plus ». Le jour ou l'une
#: d'elles est portee, le test ci-dessous EXIGE sa fabrique -- il ne se contente pas de cesser
#: d'assertionner. C'est ce qui distingue un cliquet d'un inventaire.
SITE_SYMBOLE_VERS_ABILITY = {
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedRampage_BuffAbility$$CreateTrigger":
        "RedRampage",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheArdentBlade_TriggerAbility$$CreateTrigger":
        "TheArdentBlade",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.Reinforcements_DamageAbility$$CreateTrigger":
        "Reinforcements",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheWrathfulDeadAbility_Overkill$$CreateTrigger":
        "TheWrathfulDead",
}


def _fabrique_d_arbre(ability: str):
    """La fabrique de l'arbre de TRIGGER d'une ability portee, ou `None` si elle ne l'est pas.

    Import DIFFERE et par ability : un `from ... import` en tete lierait les quatre modules, dont
    trois n'existent pas -- et c'est precisement le fait que ce test mesure."""
    if ability == "RedRampage":
        from engine.runner.operations.triggers.loki.red_rampage import red_rampage_buff_trigger_tree
        return red_rampage_buff_trigger_tree
    if ability == "TheArdentBlade":
        # #1013-r2 : SECOND site `ByOriginalTeam` d'`AreEnemies` a entrer au port. Le litteral
        # `1` est LU dans `...TheArdentBlade_TriggerAbility$$CreateTrigger` (3e argument
        # d'`AreEnemies`, type DECLARE `IdunBattle.Entities.Enum.UnitTeamSelectionType` dans
        # `frida/methods.tsv`), et l'etage 1 de ce fichier le RE-MESURE au binaire.
        from engine.runner.operations.triggers.loki.the_ardent_blade import ardent_blade_trigger_tree
        return ardent_blade_trigger_tree
    return None


def test_tout_site_by_original_team_PORTE_passe_son_litteral_au_noeud():
    """La question binaire du residu : le port ECARTE-t-il un call-site qui devrait lire l'origine ?

    Ce test ne COMPTE pas les sites portes -- il exige, POUR CHACUN, l'une des deux reponses :

      * **PORTE** -> son arbre doit contenir un noeud de la primitive du site (`AreEnemies` ou
        `AreFriends`, DERIVEE de `SITES_BY_ORIGINAL_TEAM`) portant `ByOriginalTeam`. C'est la
        verification, pas un compteur : un port qui laisserait le defaut `ByCurrentTeam` rougit ici
        alors qu'il resterait VERT partout ailleurs (les deux equipes coincident tant qu'aucun
        owner-swap n'a couru -- cf. l'etage 3, qui est le seul regime discriminant) ;
      * **NON PORTE** -> le fait est fige, avec sa prescription.

    ETAT MESURE au 2026-08-14 : **2 des 4 portes** (`RedRampage_BuffAbility` depuis #963-r1,
    `TheArdentBlade_TriggerAbility` depuis #1013-r2). Les deux autres (`Reinforcements_DamageAbility`,
    `TheWrathfulDeadAbility_Overkill`) n'ont AUCUN arbre DSL cote port : leur id vit dans les enums,
    rien de plus."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    portes, inscrits = _ids_connus(), _ids_inscrits()
    assert portes, "perimetre VIDE : le balayage du registre n'a rien trouve (test auto-invalide)"
    assert inscrits, "perimetre VIDE : aucun dict de registre peuple (test auto-invalide)"
    # COHERENCE DES DEUX RECENSEURS -- le LARGE doit contenir le STRICT. Il ne le contenait PAS
    # (rouge de `master`, 9 ids >= 1436 manquants) : `_ids_de` ne descendait pas dans les `dict`,
    # et les neuf `PowerUp_*Spawn_*` de #10004 sont fabriquees par `type()`, donc atteignables par
    # AUCUN nom. Rouge de RECENSEUR, aucun defaut de port.
    assert inscrits <= portes, (
        "un id INSCRIT est absent du balayage LARGE : recenseurs incoherents -- manquants=%s"
        % sorted(inscrits - portes))
    # ...ET LE CRAN QUI EMPECHE L'ASSERTION CI-DESSUS DE REDEVENIR VACANTE. Depuis que `_ids_de`
    # descend dans les dicts, `inscrits <= portes` est vrai PAR CONSTRUCTION tant que tout registre
    # est un dict attribut de module : elle ne mord plus par elle-meme. Ce qu'elle gardait, c'est la
    # VOIE -- une classe atteignable UNIQUEMENT par une valeur de conteneur. On exige donc (a) que
    # cette voie EXISTE dans l'arbre, sinon le controle n'exerce rien et passerait pour vert sur un
    # ensemble vide, et (b) que le balayage large la voie. Une regression de `_ids_de` rougit ici
    # meme si l'assertion precedente reste verte.
    par_nom = _ids_par_NOM_de_module()
    seulement_par_conteneur = inscrits - par_nom
    assert seulement_par_conteneur, (
        "TEMOIN DEGENERE : plus aucune classe de trigger n'est atteignable UNIQUEMENT par une "
        "valeur de conteneur. Le regime que ce controle garde (classes fabriquees par `type()` et "
        "inscrites via un dict -- #10004) a disparu de l'arbre : le controle ne prouve plus rien. "
        "Le retablir, ou retirer ce cran EN LE DISANT.")
    assert seulement_par_conteneur <= portes, (
        "le balayage LARGE ne descend plus dans les conteneurs : %s atteints par un conteneur seul "
        "et invisibles de `_ids_de`" % sorted(seulement_par_conteneur - portes))

    # PRIMITIVE par SYMBOLE, derivee du recensement de l'etage 1 -- jamais reecrite.
    primitive_par_site = {sym: (AreEnemies if court == "AreEnemies" else AreFriends)
                          for court, syms in SITES_BY_ORIGINAL_TEAM.items() for sym in syms}
    assert set(primitive_par_site) == set(SITE_SYMBOLE_VERS_ABILITY), (
        "la table symbole -> ability a DIVERGE du recensement : mesure=%s table=%s"
        % (sorted(primitive_par_site), sorted(SITE_SYMBOLE_VERS_ABILITY)))

    vus = 0
    for symbole, ability in sorted(SITE_SYMBOLE_VERS_ABILITY.items()):
        membre = getattr(TriggeredAbilityType, ability, None)
        assert membre is not None, "%s a disparu de `TriggeredAbilityType`" % ability
        fabrique = _fabrique_d_arbre(ability)
        if int(membre) not in portes:
            assert fabrique is None, (
                "%s a une fabrique d'arbre mais n'est dans AUCUN registre de dispatch : "
                "l'arbre serait registered-but-dead" % ability)
            continue
        vus += 1
        assert fabrique is not None, (
            "%s est desormais PORTE (site %s) : son arbre doit passer explicitement son litteral "
            "`UnitTeamSelectionType` a `AreEnemies`/`AreFriends` DANS LE MEME COMMIT, et etre "
            "atteignable par une FONCTION NOMMEE pour que ce cliquet puisse le verifier. "
            "Incrementer un compteur ici serait un inventaire deguise en garde-fou." % (ability, symbole))
        # REGISTERED-BUT-DEAD : une classe seulement IMPORTEE par `registry.py` est un attribut de
        # module, donc elle entre dans le balayage LARGE -- mais elle ne fire jamais. Le litteral
        # serait alors verifie sur un arbre que le moteur n'atteint pas.
        assert int(membre) in inscrits, (
            "%s a un arbre porte mais n'est INSCRIT dans aucun dict de registre : son litteral "
            "`ByOriginalTeam` serait garde sur du code MORT" % ability)
        cls = primitive_par_site[symbole]
        noeuds = [n for n in _feuilles(fabrique()) if isinstance(n, cls)]
        assert len(noeuds) == 1, (
            "%s : l'arbre porte %d noeud(s) `%s`, 1 attendu (le site natif en a UN)"
            % (ability, len(noeuds), cls.__name__))
        assert noeuds[0].selection_type == int(UnitTeamSelectionType.ByOriginalTeam), (
            "%s : le noeud `%s` de l'arbre porte `%r`, `ByOriginalTeam` attendu -- le litteral du "
            "site natif n'est pas passe au noeud" % (ability, cls.__name__, noeuds[0].selection_type))
    assert vus >= 1, (
        "TEMOIN DEGENERE : aucun des quatre sites n'est porte, donc la verification du litteral "
        "n'a rien exerce -- le test passerait pour une raison etrangere a ce qu'il mesure")


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
