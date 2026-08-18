"""#449-r2 -- INVENTAIRE AST des portes de variance d'arme de la face COMBAT.

Pourquoi un AST et pas un grep : sur ce motif precis, un grep textuel MENT DANS LE SENS
RASSURANT. Mesure du 2026-08-02 sur ce depot : `spread_pct=0` apparait 6 fois dans
`engine/`, dont 5 en COMMENTAIRE ou DOCSTRING et UNE SEULE dans du code executable. Un
inventaire par texte aurait donc rendu 6 sites a trancher dont 5 fantomes -- et, pire, il
rate integralement le gisement REEL : les call-sites qui OMETTENT le mot-cle et prennent
le DEFAUT du constructeur (l'absence du mot-cle EST une decision de portage, invisible au
grep).

CE QUE CE PROBE DERIVE, ET CE QU'IL ATTESTE (#449-r2-r5)
-------------------------------------------------------
La premiere version de ce probe CODAIT EN DUR les valeurs par defaut (« defaut 0 » pour le
mode `amount`, « defaut 20 » pour `execute_normal_like`). Contre-epreuve du 2026-08-02 :
changer le DEFAUT DE LA SIGNATURE

    -  is_first_hit: bool = True, amount_spread_pct: int = 0):
    +  is_first_hit: bool = True, amount_spread_pct: int = 20):

laissait le probe VERT et sa garde pytest a 4 passed, alors que ce seul caractere bascule
en +-20 % les DEUX porteurs qui prennent ce defaut. Le probe gardait les call-sites et pas
la valeur dont ils dependent. La ligne de partage est donc :

  * DERIVE (lu du depot, jamais recopie) -- le PERIMETRE (quelles definitions portent une
    variance), la VALEUR par defaut de chacune, la POSITION du parametre (un call-site peut
    le passer POSITIONNELLEMENT), et le GATE d'activation (`AttackWithAttackDamage` ne lit
    `amount_spread_pct` que dans sa branche mode-`amount`, ce que le probe lit dans le corps
    de la classe au lieu de le supposer).
  * ATTESTE (saisi AVEC sa raison, parce que la source est le decompile natif, qui n'est pas
    dans le depot) -- `EXPECTED_DEFAULT` (ce que le natif impose a chaque defaut) et
    `EXPECTED_ZERO` (les sites dont le natif impose une variance nulle).

LES RAILS, tous DERIVES de `VARIANCE_PARAMS` -- toute definition de `engine/` dont la
signature porte l'un de ces noms est une porte d'entree de la variance et entre ici
d'elle-meme. C'est ce qui fait qu'une porte NEUVE ne peut pas entrer en silence : elle
arrive sans attestation, et une definition sans attestation est ROUGE.

Le probe ne juge PAS la fidelite (c'est le decompile qui tranche, ability par ability) :
il rend l'inventaire EXHAUSTIF a trancher, et il rougit des qu'un fait DERIVE contredit un
fait ATTESTE.

Usage :
    python probe_449r2_spread_inventory.py            # inventaire + verdict
    python probe_449r2_spread_inventory.py --list     # detail par site
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Racine = le repertoire `engine/` DE CE CHECKOUT (jamais une remontee vers l'arbre
# principal : cf. #434, un cliquet ne balaie que son propre checkout).
ENGINE = Path(__file__).resolve().parent / "engine"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 438 fichiers -- `scripts/python/engine/**` et son propre source. Aucune table de
#: symboles : ce qui vient du natif est ATTESTE dans le source (`EXPECTED_DEFAULT`,
#: `EXPECTED_ZERO`), donc le declencheur de cette moitie-la EST ce fichier.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/**/*.py",),
    "build": False,
    "toujours": False,
    "raison": "`rglob('*.py')` sur `engine/` DE CE CHECKOUT, lu en AST -- il n'importe rien. Le "
              "verdict n'est pas local a un fichier : il DERIVE le perimetre des portes de "
              "variance, indexe leurs gates, puis RESOUT les call-sites contre ces "
              "definitions, ce qui traverse les modules. La moitie ATTESTEE (ce que le natif "
              "impose a chaque defaut) vit dans ce fichier, donc l'ajout implicite de son "
              "propre source suffit a la couvrir.",
}

# --- LE SEUL litteral de perimetre : les noms de parametre qui PORTENT la variance --------
# Il est lui-meme garde : un nom qui ne designe plus AUCUNE definition fait rougir (le probe
# serait devenu aveugle sans que rien ne le dise).
VARIANCE_PARAMS = ("amount_spread_pct", "spread_pct",
                   # #449-r2-r4-r4 -- la MEME regle vaut pour les AUTRES pourcentages de
                   # `BC.Damage` : ce sont des etats de la bataille, et AUCUN n'a de defaut natif
                   # (le ctor `IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise
                   # que le `Dictionary` DamageProfiles). Le gisement etait REEL et CHIFFRE :
                   # `ElevationBonus` etait fige a 50 -- sur le bras ou la BC ne porte PAS le
                   # champ, le natif inflige 5160 la ou le port calculait 8797 (+70,5 %).
                   "elevation_pct", "trench_reduction_pct")
# --- CE QUI RESTE HORS PERIMETRE, ET POURQUOI (residu `#449-r2-r4-r4-r1`) ------------------
# Quatre autres parametres portent une valeur de `BC.Damage`, et ce probe ne les garde PAS --
# non par oubli, mais parce que sa semantique est celle de la VARIANCE et ne leur transpose pas
# telle quelle (mesure : les inscrire rend 15 desaccords, dont plusieurs sont des artefacts) :
#   * `allow_overkill` -- gate BOOLEEN INVERSE (`if not allow_overkill: return 0`). Le detecteur
#     cherche un gate POSITIF, donc il le declare « parametre MORT » alors qu'il est bien lu.
#   * `overkill_dmg_pct_of_health` -- seuil de comparaison, pas un facteur de variance : aucun
#     des trois regimes (`0` / `LU_BC` / `REQUIS`) ne decrit ce qu'il doit valoir.
#   * `armor_pct` -- son defaut `0` est JUSTE (c'est ce que rend le natif a champ absent) et sa
#     branche n'est pas exercee (toutes les cibles live ont `RemainingArmor == 0`).
#   * `ranged_in_melee_reduction_pct` -- PREDICTION-only (trait 0xb jamais assigne, #161), donc
#     hors de la face que ce probe garde.
# Les y faire entrer demande d'elargir les REGIMES du detecteur, pas seulement sa liste de noms.


# =========================================================================================
#  Lecture de l'arbre
# =========================================================================================
_MODULES = {}          # cache de parsing : le verdict traverse `engine/` trois fois


def _iter_modules(root: Path):
    """Rend (chemin relatif au parent de `root`, arbre AST) pour chaque module lisible.

    Les arbres sont mis en cache par racine : le verdict enchaine derivation du perimetre,
    indexation des gates et resolution des call-sites, soit trois traversees. Sans cache le
    cliquet passait de 7 s a 19 s -- et son cout MARGINAL en parallele est le critere
    d'admission a la banque.
    """
    key = str(root)
    if key not in _MODULES:
        mods = []
        for path in sorted(root.rglob("*.py")):
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                mods.append((path.relative_to(root.parent).as_posix(),
                             ast.parse(src, filename=str(path))))
            except SyntaxError:
                continue
        _MODULES[key] = mods
    return list(_MODULES[key])


def _literal_int(node):
    """Rend l'int si le noeud est un litteral entier, sinon None (expression dynamique)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return node.value
    return None


def _is_staticmethod(fn) -> bool:
    for d in fn.decorator_list:
        name = d.id if isinstance(d, ast.Name) else (d.attr if isinstance(d, ast.Attribute) else "")
        if name == "staticmethod":
            return True
    return False


def _signature_slot(fn, param: str, drop_receiver: bool):
    """Rend (noeud_defaut, index_positionnel) pour `param`, ou None s'il n'y est pas.

    `index_positionnel` = le rang auquel un APPELANT peut passer ce parametre sans mot-cle
    (None pour un keyword-only). `drop_receiver` retire `self`/`cls`, que l'appelant ne
    fournit pas quand il appelle la methode sur une instance (ou la classe pour un ctor).
    C'est CE calcul qui rend visible un call-site qui passe la variance POSITIONNELLEMENT
    -- angle mort total d'un inventaire par mot-cle.
    """
    args = fn.args
    positional = list(args.posonlyargs) + list(args.args)
    names = [a.arg for a in positional]
    offset = 0
    if drop_receiver and names and names[0] in ("self", "cls"):
        offset = 1
    if param in names:
        i = names.index(param)
        first_defaulted = len(names) - len(args.defaults)
        node = args.defaults[i - first_defaulted] if i >= first_defaulted else None
        return node, i - offset
    kwonly = [a.arg for a in args.kwonlyargs]
    if param in kwonly:
        return args.kw_defaults[kwonly.index(param)], None
    return None


def _mentions(node, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(node))


def _self_attr(node):
    """Rend `X` si `node` est `self.X`, sinon None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
            and node.value.id == "self":
        return node.attr
    return None


def _attrs_assigned_from(init_fn, param: str):
    """Attributs `self.X` dont l'affectation dans `__init__` MENTIONNE `param`."""
    out = set()
    for node in ast.walk(init_fn):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        if not targets or getattr(node, "value", None) is None:
            continue
        if not _mentions(node.value, param):
            continue
        for t in targets:
            a = _self_attr(t)
            if a:
                out.add(a)
    return out


#: `{(fichier, nom d'appel): {"<base> (n definition(s))", ...}}` -- les classes de base qu'une
#: derivation n'a PAS su resoudre, remplies par `collect_definitions`. Rendues au rapport pour que
#: << je n'ai pas suivi cette base >> soit LU, jamais silencieux : c'est la seule difference entre
#: un doute assume et un angle mort.
BASES_NON_RESOLUES = {}


def _nom_de_base(node):
    """Le NOM SIMPLE d'une expression de classe de base (`Base`, `mod.Base`), sinon None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None                                   # `Generic[T]`, appel, etc. : non resolu


def _methodes_heritees(classe: ast.ClassDef, index: dict, ko: list):
    """Les methodes des classes de BASE de `classe`, remontees TRANSITIVEMENT.

    POURQUOI CE CANAL EXISTE (#956). La derivation d'origine ne cherchait les lectures d'un
    parametre de `__init__` que dans les autres methodes ECRITES DANS LA MEME `ClassDef`. Un
    port peut parfaitement mettre le lecteur dans la classe de BASE : mesure du 2026-08-12,
    `ChainAttackDamage` (`engine/runner/abilities/behaviours/chain.py`) n'a QUE son `__init__`
    -- il range `amount_spread_pct` dans le sous-objet `self.damage`, et c'est
    `ChainAbilityDamage.execute` (la base) qui lit `self.damage`. Zero lecture derivee, donc
    << parametre MORT >>, donc `master` ROUGE sur un port CORRECT.

    LA RESOLUTION EST EXIGEANTE, ET LE SENS DU DOUTE EST CELUI QUI ROUGIT. Un nom de base qui
    ne designe pas EXACTEMENT UNE `ClassDef` de l'arbre analyse n'est PAS suivi : on ne sait pas
    de quelle classe il s'agit, et l'inventer ferait COMPTER des lectures qui n'existent
    peut-etre pas -- c'est-a-dire fabriquer un FAUX NEGATIF, la seule direction dangereuse de ce
    detecteur. Un doute laisse donc le compte inchange, le cliquet rougit, et un humain lit. Les
    bases non resolues sont RENDUES (`ko`) pour que le rapport puisse le dire.
    """
    out, vues, pile = [], {classe.name}, list(classe.bases)
    while pile:
        base = pile.pop()
        nom = _nom_de_base(base)
        if nom is None or nom in vues:
            continue
        vues.add(nom)
        candidats = index.get(nom) or []
        if len(candidats) != 1:
            ko.append((nom, len(candidats)))
            continue
        cd = candidats[0]
        for sub in cd.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name != "__init__":
                out.append(sub)
        pile.extend(cd.bases)
    return out


def _positive_gates(fn, attrs, local_names=()):
    """Pour chaque LECTURE de la variance dans `fn`, les gates POSITIFS qui la dominent.

    Deux formes de lecture, selon la nature de la definition -- les CONFONDRE etait le
    premier bug de ce detecteur, trouve par son propre auto-test : un `@staticmethod` lit son
    parametre comme une VARIABLE LOCALE (`spread_pct`), pas comme un attribut (`self.X`), et
    chercher `self.X` partout faisait declarer MORTS quatre parametres bien vivants.

      * `attrs`       -- lecture `self.<attr>` (le parametre a ete stocke par `__init__`) ;
      * `local_names` -- lecture `<nom>` (le parametre est une variable de la fonction).

    Un gate positif = un `if self.G ...` / `if self.G is not None` dont la lecture est dans le
    corps VRAI. On ignore volontairement les branches `else` et les tests negatifs : un gate
    mal oriente ferait classer INERTE un site qui ne l'est pas, c'est-a-dire un FAUX NEGATIF
    -- exactement ce que ce probe existe pour ne pas produire.

    Rend la liste (une entree par lecture) des ensembles de gates. Une liste VIDE signifie que
    le parametre n'est LU NULLE PART : le port ne l'applique plus, et c'est rouge.
    """
    reads = []

    def walk(node, gates):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If):
                extra = set()
                test = child.test
                inner = test.left if isinstance(test, ast.Compare) else test
                if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
                    inner = None                      # `if not self.X` -> gate NEGATIF, ignore
                if isinstance(test, ast.Compare) and len(test.ops) == 1 \
                        and isinstance(test.ops[0], (ast.Is, ast.Eq)):
                    inner = None                      # `is None` / `== 0` -> negatif, ignore
                g = _self_attr(inner) if inner is not None else None
                if g:
                    extra.add(g)
                for sub in child.body:
                    walk(sub, gates | extra)
                for sub in child.orelse:
                    walk(sub, gates)                  # branche else : le gate ne s'applique pas
                continue
            if isinstance(child, ast.Attribute) and _self_attr(child) in attrs \
                    and isinstance(child.ctx, ast.Load):
                reads.append(set(gates))
            elif isinstance(child, ast.Name) and child.id in local_names \
                    and isinstance(child.ctx, ast.Load):
                reads.append(set(gates))
            walk(child, gates)

    walk(fn, frozenset())
    return reads


class Definition:
    """Une porte d'entree de la variance, DERIVEE de la signature."""

    __slots__ = ("file", "line", "call_name", "param", "default", "default_dynamic",
                 "default_kind", "pos_index", "gates", "reads", "is_class", "problems")

    def __init__(self, file, line, call_name, param):
        self.file, self.line, self.call_name, self.param = file, line, call_name, param
        self.default = None
        self.default_dynamic = False
        self.default_kind = None     # REQUIS | LU_BC | LITTERAL | DYNAMIQUE (cf. `_fill`)
        self.pos_index = None
        self.gates = frozenset()
        self.reads = None            # None = non applicable (fonction libre)
        self.is_class = False
        self.problems = []

    @property
    def key(self):
        return (self.file, self.call_name, self.param)


def collect_definitions(root: Path):
    """DERIVE le perimetre : toute definition de `root` dont la signature porte un
    `VARIANCE_PARAMS`. Le nom rendu est le NOM D'APPEL (celui d'une classe pour son
    `__init__`, celui de la methode ou de la fonction sinon)."""
    defs = []
    # INDEX DES CLASSES, prealable a la remontee d'heritage (#956). Une classe est indexee par son
    # NOM SIMPLE, et une collision de noms rend la resolution AMBIGUE -- donc NON suivie.
    index: dict = {}
    for _rel, tree in _iter_modules(root):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                index.setdefault(node.name, []).append(node)
    BASES_NON_RESOLUES.clear()
    for rel, tree in _iter_modules(root):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    is_ctor = sub.name == "__init__"
                    call_name = node.name if is_ctor else sub.name
                    for param in VARIANCE_PARAMS:
                        slot = _signature_slot(sub, param, drop_receiver=not _is_staticmethod(sub))
                        if slot is None:
                            continue
                        d = Definition(rel, sub.lineno, call_name, param)
                        d.is_class = is_ctor
                        _fill(d, slot)
                        if is_ctor:
                            # Le parametre est STOCKE puis relu ailleurs dans la classe : le
                            # GATE d'activation se lit dans le corps, il ne se suppose pas.
                            attrs = _attrs_assigned_from(sub, param)
                            reads = []
                            lecteurs = [o for o in node.body
                                        if isinstance(o, (ast.FunctionDef, ast.AsyncFunctionDef))
                                        and o is not sub]
                            # ... ET CEUX DES CLASSES DE BASE (#956) : le lecteur de l'attribut
                            # n'est pas tenu de vivre dans la meme `ClassDef`.
                            ko_bases = []
                            lecteurs.extend(_methodes_heritees(node, index, ko_bases))
                            for nom, n in ko_bases:
                                BASES_NON_RESOLUES.setdefault((rel, call_name), set()).add(
                                    "%s (%d definition(s) dans l'arbre)" % (nom, n))
                            for other in lecteurs:
                                reads.extend(_positive_gates(other, attrs))
                            d.reads = len(reads)
                            if reads:
                                common = set(reads[0])
                                for r in reads[1:]:
                                    common &= r
                                d.gates = frozenset(common - attrs)
                        else:
                            # Methode : le parametre est une VARIABLE LOCALE. Aucun gate --
                            # l'appelant fournit la valeur dans tous les cas, donc son choix
                            # est effectif quelle que soit la branche qui la consomme.
                            d.reads = len(_positive_gates(sub, (), local_names={param}))
                        defs.append(d)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Les methodes sont deja traitees au-dessus ; ast.walk les revisite, on ne
                # garde ici que ce qui n'appartient pas a une classe.
                continue
        # Fonctions de module (niveau superieur ou imbriquees hors classe).
        for node in _module_level_functions(tree):
            for param in VARIANCE_PARAMS:
                slot = _signature_slot(node, param, drop_receiver=False)
                if slot is None:
                    continue
                d = Definition(rel, node.lineno, node.name, param)
                _fill(d, slot)
                d.reads = len(_positive_gates(node, (), local_names={param}))
                defs.append(d)
    return defs


def _module_level_functions(tree):
    """Fonctions qui ne sont PAS des methodes (on ne descend pas dans les ClassDef)."""
    out = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(child)
            walk(child)

    walk(tree)
    return out


def _fill(d: Definition, slot):
    """Classe le DEFAUT de la signature dans l'un des quatre regimes possibles.

    #449-r2-r4 a change ce qui est ATTENDU ici, et donc ce que ce classement doit distinguer.
    Avant : le defaut nominal etait le litteral `20`. Depuis, `20` est precisement la faute --
    le natif ne connait le pct QUE par sa configuration
    (`IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` lit
    `configuration+0x20`), donc un port qui l'ECRIT dans une signature a re-fabrique un couplage
    non lu. Les quatre regimes :

        REQUIS    -- pas de defaut : tout appelant doit fournir sa valeur. Le plus sur.
        LU_BC     -- defaut `None` : la valeur est resolue a l'execution depuis la BC
                     (`engine.services.damage_config.resolve_spread_pct`). Le regime NOMINAL.
        LITTERAL  -- defaut entier ecrit dans la signature. N'est legitime que pour un `0` LU au
                     decompile (mode `amount` : `Nullable<AttackDamageBehaviourOptions>` vide).
        DYNAMIQUE -- toute autre expression : indeductible, donc ingardable.
    """
    node, pos = slot
    d.pos_index = pos
    if node is None:
        d.default_kind = "REQUIS"
        return
    if isinstance(node, ast.Constant) and node.value is None:
        d.default_kind = "LU_BC"
        return
    val = _literal_int(node)
    if val is None:
        d.default_kind = "DYNAMIQUE"
        d.default_dynamic = True
        d.problems.append("defaut NON LITTERAL (%s) : indeductible, donc ingardable"
                          % type(node).__name__)
    else:
        d.default_kind = "LITTERAL"
        d.default = val


# =========================================================================================
#  ATTESTATIONS -- saisies AVEC leur raison, parce que la source est le decompile natif.
# =========================================================================================
# Ce que le natif impose a chaque DEFAUT. C'est le fait que la contre-epreuve du 2026-08-02
# a pu changer sans faire rougir quoi que ce soit : les deux porteurs a variance nulle
# n'ECRIVENT PAS le mot-cle, donc le defaut EST leur valeur.
_RAISON_NULLABLE_VIDE = (
    "0 = le `Nullable<AttackDamageBehaviourOptions>` (8e argument des factories "
    "`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` / `$$AttackDamage`) est "
    "passe VIDE par le `CreateBehaviour` des porteurs -- "
    "`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor` appelle "
    "`Nullable<T>.GetValueOrDefault`, donc l'octet d'aiguillage +6 vaut 0 et "
    "`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` prend la branche PLATE. "
    "Un defaut non nul appliquerait +-20 % aux porteurs qui OMETTENT le mot-cle.")

_RAISON_NULLABLE_VIDE_CHAIN = (
    "0 = l'argument `damageOptions` de "
    "`IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage` -- un "
    "`Nullable<AttackDamageBehaviourOptions>` de 0x20 octets que la factory recopie TEL QUEL "
    "dans `IdunBattle.Entities.Behaviours.ChainAttackDamageBehaviour$$.ctor` -- est passe VIDE "
    "par les DEUX consommateurs lus : "
    "`IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour` et "
    "`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$CreateBehaviour` "
    "mettent les quatre qwords a ZERO juste avant l'appel. L'octet d'aiguillage +6 vaut donc 0 "
    "et `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` prend la branche PLATE. "
    "ATTENTION -- CE N'EST PAS LE MEME ARGUMENT que celui de `$$AttackWithAttackDamage` (8e, cf. "
    "`_RAISON_NULLABLE_VIDE`) : ici la signature native le NOMME et il est en 10e position, "
    "apres `abilityType` / `extraBehaviour` / `maxTargetsExtra`. Le recopier de la voisine "
    "aurait cite le mauvais slot.")

_RAISON_SPREAD_BC = (
    "LU_BC = la variance d'arme du canal de l'attaque NORMALE est "
    "`BattleConfiguration.Damage.DamageSpreadPercentage`, et le natif ne la connait QUE par sa "
    "configuration : `IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread` inline "
    "`$$get_DamageSpreadPercentageFix64`, qui lit `configuration+0x20` -- la signature native "
    "n'a AUCUN parametre de spread. Un defaut ECRIT dans la signature du port serait donc un "
    "couplage non lu (c'etait le residu `#449-r2-r4`, MESURE : a `DamageSpreadPercentage = 60` "
    "le natif inflige 7774 la ou le port a `20` en dur en calcule 9388). Le defaut nominal est "
    "`None` -> `engine.services.damage_config.resolve_spread_pct`.")

_RAISON_FOYER = (
    "LU_BC = c'est LE foyer lui-meme (`resolve_spread_pct`). Son `None` signifie « rien "
    "d'explicite » et declenche la lecture de la BC portee par le `State`, puis le defaut DERIVE "
    "de `data/seed-bc.json`. Un litteral ici recreerait le vice en UN point au lieu de treize.")

_RAISON_FEUILLE_POSITIONNELLE = (
    "REQUIS = aucun defaut, et c'est le POINT du correctif #449-r2-r4-r4. Ces deux feuilles sont "
    "le mirror de `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier` "
    "et `$$CalculateTrenchReduction`, dont les signatures natives ne portent AUCUN parametre de "
    "pourcentage : le natif lit `configuration+0x10` / `configuration+0x2c` -- il n'existe donc "
    "cote jeu aucune constante a recopier, et tout defaut ecrit ici serait une INVENTION. Le pct "
    "est fourni par l'appelant (`engine/runner/damage_model.py`), qui le resout au foyer "
    "`damage_config.resolve_damage_field(..., state=state)`. Les deux portaient auparavant une "
    "constante de module lue dans la SEED figee a l'import (`ELEVATION_BONUS_PCT` / `TRENCH_PCT`) "
    "-- juste tant que la BC valait la seed, faux sinon : mesure a `ElevationBonus` absent, natif "
    "5160 contre 8797 pour le port (+70,5 %).")

_RAISON_REQUIS = (
    "REQUIS = aucun defaut. `HitDamage.from_base` n'a AUCUN appelant sous `scripts/python` "
    "(mesure : 0 site `.from_base(`) : un defaut y serait un litteral que rien n'exerce, donc "
    "que rien ne peut invalider. L'exiger force le futur appelant a dire d'ou vient sa valeur.")

#: Regimes acceptes, par cle. Un `int` = litteral attendu (seul `0` est legitime, et seulement
#: la ou le decompile impose la variance nulle) ; une chaine = regime symbolique (`LU_BC`,
#: `REQUIS`).
EXPECTED_DEFAULT = {
    ("engine/runner/abilities/behaviours/combat.py", "AttackWithAttackDamage",
     "amount_spread_pct"): (0, _RAISON_NULLABLE_VIDE),
    ("engine/runner/abilities/behaviours/chain.py", "ChainAttackDamage",
     "amount_spread_pct"): (0, _RAISON_NULLABLE_VIDE_CHAIN),
    ("engine/runner/abilities/behaviours/combat.py", "UseActiveAbility",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    #: `UseNormalAttack` N'A PLUS D'ENTREE ICI, et son absence est un RESULTAT, pas un oubli.
    #: Sa lecture native reste vraie et vit dans le docstring de la classe : le corps de
    #: `IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttack` alloue
    #: `DSLSelectors$$UnitNormalAttackType(caster)` puis construit
    #: `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$.ctor(...)` en RECOPIANT les
    #: options telles quelles -- ce sont des `AbilityOptions` (0x14 octets), PAS des
    #: `AttackDamageBehaviourOptions`, donc l'octet d'aiguillage `options+6` n'existe pas sur ce
    #: chemin. Ce que le port en a tire : `UseNormalAttack` ne surcharge PLUS `__init__` et
    #: HERITE celui d'`UseActiveAbility` -- il n'y a donc plus de SIGNATURE a garder ici, et la
    #: garde est portee par l'entree `UseActiveAbility` juste au-dessus. Laisser l'entree ferait
    #: rougir `test_chaque_justification_designe_un_site_reel` (#956), a raison : une
    #: justification qui ne designe plus rien est une garde qui a survecu a son gisement.
    ("engine/runner/operations/additional_hits.py", "execute_additional_hits",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    #: Porte de variance ARRIVEE avec `#1050-r1` (PR #1077) et jamais attestee -- `master` en
    #: etait ROUGE, trouve en mesurant le rayon de souffle de #449-r2-r4-r1. L'attestation est
    #: MECANIQUE et n'a demande aucun decompile neuf : le site passe son `spread_pct` tel quel a
    #: `AttackDamageOperation.execute`, donc son `None` retombe sur `resolve_spread_pct` -- le
    #: MEME canal que l'attaque normale dont cette boucle rejoue le vecteur, mot pour mot.
    ("engine/runner/abilities/loki/ancient_fury.py", "execute_widened_normal_attack",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/runner/operations/damage.py", "DamageHandler",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/runner/operations/damage_hits.py", "from_base",
     "spread_pct"): ("REQUIS", _RAISON_REQUIS),
    ("engine/runner/operations/damage_ops/normal.py", "execute",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/runner/operations/damage_ops/normal_like.py", "execute_normal_like",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/runner/runner.py", "install_default_handlers",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_calculations.py", "calculate_damage_spread",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_calculations.py", "spread_to_min_max",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_config.py", "resolve_spread_pct",
     "spread_pct"): ("LU_BC", _RAISON_FOYER),
    ("engine/services/damage_prediction.py", "get_base_damage_fix64",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_prediction.py", "predict_attack_raw",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_prediction.py", "get_multi_hit_attack_prediction",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_prediction.py", "get_attack_prediction",
     "spread_pct"): ("LU_BC", _RAISON_SPREAD_BC),
    ("engine/services/damage_modifiers.py", "calculate_elevation_bonus_modifier",
     "elevation_pct"): ("REQUIS", _RAISON_FEUILLE_POSITIONNELLE),
    ("engine/services/damage_modifiers.py", "calculate_trench_reduction",
     "trench_reduction_pct"): ("REQUIS", _RAISON_FEUILLE_POSITIONNELLE),
}

# --- Liste ATTENDUE des CALL-SITES qui rendent une variance NULLE (spread 0) ---------------
# Chaque entree porte la RAISON LUE AU DECOMPILE. Un site qui rend 0 sans figurer ici fait
# ROUGIR : c'est un port qui a suppose l'absence de variance sans l'avoir lue. Cle =
# (fichier, nom d'appel). La LIGNE n'entre pas dans la cle (elle bouge a chaque edition du
# fichier ; c'est le SITE qui est garde, pas sa position).
EXPECTED_ZERO = {
    ("engine/runner/operations/triggers/loki/psyker.py", "AttackWithAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$"
        "CreateBehaviour passe le 8e argument Nullable<AttackDamageBehaviourOptions> VIDE "
        "(les 0x28 octets sont mis a zero juste avant l'appel a "
        "IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage).",
    ("engine/runner/operations/triggers/loki/cursed_plague_bell.py", "AttackWithAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$"
        "CreateBehaviour : meme forme, 8e argument Nullable VIDE (0x28 octets a zero).",
    ("engine/runner/abilities/aeldari.py", "ChainAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour "
        "met les quatre qwords de son `Nullable<AttackDamageBehaviourOptions>` a ZERO juste avant "
        "de le passer en `damageOptions` (10e argument) a "
        "IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage -- Nullable VIDE, donc octet "
        "d'aiguillage +6 nul, donc branche PLATE. Le site OMET le mot-cle : c'est le DEFAUT de la "
        "signature qui porte la decision (cf. EXPECTED_DEFAULT).",
    ("engine/runner/operations/triggers/loki/fury_of_the_ancients.py", "ChainAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$"
        "CreateBehaviour : meme forme, meme argument `damageOptions` de "
        "IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage, quatre qwords a ZERO ecrits "
        "juste avant l'appel. Le site OMET egalement le mot-cle.",
    ("engine/runner/operations/triggers/loki/haze_of_corruption.py", "AttackWithAttackDamage"):
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$"
        "CreateTargetTriggerBehaviour : chaque feuille est un "
        "IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage dont le 8e argument "
        "Nullable<AttackDamageBehaviourOptions> est VIDE (0x28 octets a zero).",
    # #1084 -- PHASE 2 de `SolarAtomizer` (la triggered 1297), livree par #894-r2 SANS attestation :
    # `master` en etait ROUGE. La variance nulle y est JUSTE, et c'est LU sur `t6dpr4k06g`.
    ("engine/runner/operations/triggers/loki/solar_atomizer_attack.py", "AttackWithAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SolarAtomizer_PendingAttackAbility$$"
        "CreateBehaviour ecrit les CINQ qwords de son `Nullable<AttackDamageBehaviourOptions>` "
        "(0x28 octets) a ZERO juste avant de le passer en 8e argument a "
        "IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage -- Nullable VIDE, donc "
        "l'octet d'aiguillage +6 est nul et "
        "IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw prend la branche PLATE. Le "
        "site OMET le mot-cle : c'est le DEFAUT de la signature qui porte la decision (cf. "
        "EXPECTED_DEFAULT). Contre-preuve du meme decompile : son 5e argument, lui, est un "
        "Nullable NON vide (`Nullable<T>..ctor(&local_c0, &damageProfile)`) -- la struct a zero "
        "est donc une ECRITURE, pas un artefact de decompilation.",
}

# Ce que ces trois entrees ont en commun, et pourquoi le ZERO y est un RESULTAT : le byte
# natif qui aiguille plate-vs-spread est `AttackDamageBehaviourOptions + 6`. Il n'est
# jamais constant cote COMBAT -- contre-preuve LUE :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` le
# pose a 1 en dur sur la meme struct (seul octet non nul), et le port lui donne bien 20
# (`engine/runner/abilities/sisterhood.py`).


# =========================================================================================
#  Inventaire des call-sites
# =========================================================================================
def _callee_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _kw(node: ast.Call, name: str):
    for k in node.keywords:
        if k.arg == name:
            return k
    return None


def _has_star(node: ast.Call) -> bool:
    return (any(isinstance(a, ast.Starred) for a in node.args)
            or any(k.arg is None for k in node.keywords))


def collect(root: Path, defs=None):
    """Rend (definitions, sites, ambigus).

    `definitions` = le perimetre DERIVE. `sites` = les call-sites resolus contre lui.
    `ambigus` = les noms d'appel qu'on ne peut PAS resoudre par nom simple parce qu'ils sont
    partages avec des definitions qui ne portent pas de variance (`execute`, par ex.) : leurs
    call-sites ne sont pas inventoriables, et c'est NOMME plutot que passe sous silence.
    """
    if defs is None:
        defs = collect_definitions(root)
        _index_gates(root, defs)

    # Un nom d'appel est RESOLVABLE si toutes les definitions de `root` qui le portent
    # s'accordent sur le parametre de variance. Sinon, l'appel est ambigu.
    all_names = {}
    for rel, tree in _iter_modules(root):
        # `ast.walk` revisite les methodes en tant que noeuds independants : sans ce garde, une
        # methode compte DEUX fois et son nom parait ambigu alors qu'il ne l'est pas (bug 2 de
        # ce detecteur, trouve par son auto-test -- `execute_normal_like` sortait a 2/1).
        vues = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                all_names.setdefault(node.name, []).append(("class", rel, node.lineno))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        vues.add(id(sub))
                        if sub.name != "__init__":
                            all_names.setdefault(sub.name, []).append(
                                ("method", rel, sub.lineno))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if id(node) in vues:
                    continue
                all_names.setdefault(node.name, []).append(("func", rel, node.lineno))

    by_name = {}
    for d in defs:
        by_name.setdefault(d.call_name, []).append(d)
    ambigus = {}
    resolvable = {}
    for name, group in by_name.items():
        homonymes = len(all_names.get(name, []))
        # `__init__` d'une classe n'est jamais compte : le nom d'appel EST celui de la classe.
        if homonymes > len(group):
            ambigus[name] = (homonymes, len(group))
        else:
            resolvable[name] = group

    sites = []
    for rel, tree in _iter_modules(root):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _callee_name(node)
            group = resolvable.get(name)
            if group is not None:
                for d in group:
                    sites.append(_resolve_site(rel, node, name, d))
            # BALAYAGE GLOBAL : un mot-cle de variance LITTERAL, quel que soit l'appele.
            # C'est ce qui rattrape les noms AMBIGUS (`AttackDamageOperation.execute(...,
            # spread_pct=0)`) que la resolution par nom ne peut pas trancher.
            if group is None:
                for param in VARIANCE_PARAMS:
                    k = _kw(node, param)
                    if k is None:
                        continue
                    sites.append({
                        "file": rel, "line": node.lineno, "callee": name, "param": param,
                        "source": "kwarg", "value": _literal_int(k.value),
                        "dynamic": _literal_int(k.value) is None, "inert": False,
                        "unresolved": False, "gates": frozenset(), "ambigu": True,
                    })
    return defs, sites, ambigus


def _resolve_site(rel, node: ast.Call, name: str, d: Definition):
    """Valeur EFFECTIVE de la variance a ce call-site, contre la signature DERIVEE."""
    star = _has_star(node)
    # Le GATE, derive du corps : hors de sa branche, le parametre n'est jamais lu. Un gate se
    # fournit par MOT-CLE ou POSITIONNELLEMENT -- les deux sont derives de la signature.
    inert = False
    if d.gates:
        fournis = set()
        for g in d.gates:
            if _kw(node, g) is not None:
                fournis.add(g)
                continue
            gpos = GATE_POS.get((d.key, g))
            if gpos is not None and len(node.args) > gpos:
                fournis.add(g)
        if not fournis and not star:
            inert = True
    kw = _kw(node, d.param)
    if kw is not None:
        val = _literal_int(kw.value)
        return {"file": rel, "line": node.lineno, "callee": name, "param": d.param,
                "source": "kwarg", "value": val, "dynamic": val is None, "inert": inert,
                "unresolved": False, "gates": d.gates, "ambigu": False}
    if d.pos_index is not None and len(node.args) > d.pos_index:
        arg = node.args[d.pos_index]
        val = _literal_int(arg)
        return {"file": rel, "line": node.lineno, "callee": name, "param": d.param,
                "source": "positionnel", "value": val, "dynamic": val is None,
                "inert": inert, "unresolved": False, "gates": d.gates, "ambigu": False}
    if star:
        # `*args` / `**kwargs` : la valeur peut venir de n'importe ou. On ne CLASSE PAS un
        # tel site en DEFAUT -- ce serait le meme vice que le defaut code en dur, un cran
        # plus loin : affirmer une valeur qu'on n'a pas lue.
        return {"file": rel, "line": node.lineno, "callee": name, "param": d.param,
                "source": "star", "value": None, "dynamic": True, "inert": inert,
                "unresolved": True, "gates": d.gates, "ambigu": False}
    # Le site prend le DEFAUT de la porte. Son regime est celui de la signature (`_fill`) :
    #   LU_BC    -> la variance vient de la BC a l'execution. C'est le regime NOMINAL depuis
    #               #449-r2-r4 : ni une valeur ecrite, ni un indetermine -- une LECTURE. Le
    #               garder ici n'aurait aucun sens (il n'y a plus de constante a garder) ; ce
    #               qui est garde, c'est le REGIME du defaut, cote signature.
    #   REQUIS   -> un site qui ne fournit rien alors que le parametre est obligatoire est un
    #               TypeError a l'execution : c'est une faute, pas un indetermine.
    #   LITTERAL -> valeur ecrite, tranchable comme avant.
    return {"file": rel, "line": node.lineno, "callee": name, "param": d.param,
            "source": "defaut", "value": d.default,
            "dynamic": d.default_dynamic, "from_bc": d.default_kind == "LU_BC",
            "inert": inert,
            "unresolved": d.default_kind == "REQUIS",
            "gates": d.gates, "ambigu": False}


# Position positionnelle des GATES, derivee des signatures (remplie par `_index_gates`).
GATE_POS = {}


def _index_gates(root: Path, defs):
    """Derive l'index positionnel de chaque gate, pour voir un call-site qui l'active sans
    mot-cle. Sans ca, un appel entierement positionnel serait classe INERTE a tort."""
    GATE_POS.clear()
    wanted = {}
    for d in defs:
        for g in d.gates:
            wanted.setdefault((d.file, d.call_name), set()).add((d.key, g))
    if not wanted:
        return
    for rel, tree in _iter_modules(root):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    call_name = node.name if sub.name == "__init__" else sub.name
                    for key, g in wanted.get((rel, call_name), ()):
                        slot = _signature_slot(sub, g, drop_receiver=not _is_staticmethod(sub))
                        if slot is not None:
                            GATE_POS[(key, g)] = slot[1]


# =========================================================================================
#  Verdict
# =========================================================================================
def evaluate(root: Path):
    """Rend (defs, sites, ambigus, reds). `reds` = liste de (motif, detail)."""
    defs2 = collect_definitions(root)
    _index_gates(root, defs2)               # positions des gates AVANT de resoudre les sites
    _, sites, ambigus = collect(root, defs2)
    reds = []

    # --- garde du GARDE : le perimetre lui-meme doit designer quelque chose ---------------
    for param in VARIANCE_PARAMS:
        if not any(d.param == param for d in defs2):
            reds.append(("perimetre AVEUGLE",
                         "aucune definition de engine/ ne porte le parametre `%s` : ce probe "
                         "ne garde plus rien sur ce rail (le parametre a-t-il ete renomme ?)"
                         % param))

    # --- les DEFAUTS : derives vs attestes ----------------------------------------------
    for d in defs2:
        for p in d.problems:
            reds.append(("signature ingardable", "%s:%d %s(%s) -- %s"
                         % (d.file, d.line, d.call_name, d.param, p)))
        if d.reads == 0:
            reds.append(("parametre MORT",
                         "%s:%d %s(%s) est accepte par la signature et LU NULLE PART : le port "
                         "ne l'applique plus, tout call-site qui le passe est un no-op "
                         "silencieux (la variance ne serait plus jamais appliquee)"
                         % (d.file, d.line, d.call_name, d.param)))
        # #449-r2-r4 -- LA GARDE DU LITTERAL REVENU. Un defaut entier NON NUL sur une porte de
        # variance est le vice lui-meme : le natif lit le pct dans `BattleConfiguration.Damage`,
        # jamais dans une constante. Le seul entier legitime est `0`, et seulement la ou le
        # decompile impose la variance nulle (mode `amount`, Nullable vide).
        if d.default_kind == "LITTERAL" and d.default != 0:
            reds.append(("LITTERAL DE SPREAD REVENU",
                         "%s:%d %s(%s) porte le defaut ECRIT %s -- le natif lit ce pct dans "
                         "`BattleConfiguration.Damage.DamageSpreadPercentage` "
                         "(`IdunBattle.Core.Services.DamageCalculations$$"
                         "get_DamageSpreadPercentageFix64` -> `configuration+0x20`). MESURE "
                         "#449-r2-r4 : a pct=60 le natif inflige 7774, un port a 20 en dur 9388. "
                         "Regime attendu : `= None` (foyer `damage_config.resolve_spread_pct`)."
                         % (d.file, d.line, d.call_name, d.param, d.default)))
        att = EXPECTED_DEFAULT.get(d.key)
        got = d.default if d.default_kind == "LITTERAL" else d.default_kind
        if att is None:
            reds.append(("porte de variance NON ATTESTEE",
                         "%s:%d %s(%s) defaut=%s -- une porte d'entree de la variance est "
                         "entree sans que son regime de defaut soit lu au decompile ; inscrire "
                         "sa raison dans EXPECTED_DEFAULT"
                         % (d.file, d.line, d.call_name, d.param, got)))
        elif got != att[0]:
            reds.append(("DEFAUT contredit le decompile",
                         "%s:%d %s(%s) : defaut LU = %s, attendu %s -- %s"
                         % (d.file, d.line, d.call_name, d.param, got, att[0], att[1])))
    seen_defs = {d.key for d in defs2}
    for key in EXPECTED_DEFAULT:
        if key not in seen_defs:
            reds.append(("attestation de defaut PERIMEE",
                         "%s :: %s(%s) ne designe plus aucune signature" % key))

    # --- les CALL-SITES : sens 1 (tout zero justifie) et sens 2 (tout justifie a zero) ----
    actifs = [s for s in sites if not s["inert"]]
    for s in actifs:
        if s["unresolved"]:
            reds.append(("variance INDETERMINABLE",
                         "%s:%d %s(%s) via %s -- la valeur ne se lit pas statiquement ; ce "
                         "probe ne DEVINE pas" % (s["file"], s["line"], s["callee"],
                                                  s["param"], s["source"])))
    zero = [s for s in actifs
            if not s.get("from_bc") and not s["dynamic"] and not s["unresolved"]
            and s["value"] == 0]
    for s in zero:
        if (s["file"], s["callee"]) not in EXPECTED_ZERO:
            reds.append(("zero NON JUSTIFIE",
                         "%s:%d %s(%s=0, %s)" % (s["file"], s["line"], s["callee"],
                                                 s["param"], s["source"])))
    zero_keys = {(s["file"], s["callee"]) for s in zero}
    by_key = {}
    for s in actifs:
        by_key.setdefault((s["file"], s["callee"]), []).append(s)
    for key in EXPECTED_ZERO:
        if key in by_key and key not in zero_keys:
            for s in by_key[key]:
                reds.append(("REGRESSION : attendu 0",
                             "%s:%d %s(%s=%s, %s)"
                             % (s["file"], s["line"], s["callee"], s["param"],
                                "dyn" if s["dynamic"] else s["value"], s["source"])))
    seen_sites = {(s["file"], s["callee"]) for s in actifs}
    for key in EXPECTED_ZERO:
        if key not in seen_sites:
            reds.append(("attestation de zero PERIMEE",
                         "%s :: %s ne designe plus aucun call-site actif" % key))
    return defs2, sites, ambigus, reds


# =========================================================================================
#  AUTO-TEST DU DETECTEUR -- joue a CHAQUE run, sur un arbre SYNTHETIQUE
# =========================================================================================
# Pourquoi il est DANS le probe et pas dans un fichier pytest a cote : #427 a mesure que
# « etre un test » et « etre joue » sont INDEPENDANTS dans ce depot (la suite complete est
# proscrite, un agent ne cible que les tests de sa tranche). Un auto-test qui n'est dans
# aucune liste qu'on lance ne garde rien. Ici il tourne avec le cliquet, pour un cout nul.
#
# Sur les TROIS derniers gardes livres, l'auto-test a trouve un bug DU DETECTEUR deux fois
# (#440, #455). Il en a trouve DEUX ici :
#   1. la detection « parametre MORT » cherchait `self.<param>` y compris dans un
#      `@staticmethod`, ou le parametre est une variable LOCALE -> quatre parametres bien
#      vivants declares morts (`execute_normal_like`, `from_base`, `execute`,
#      `install_default_handlers`) ;
#   2. `ast.walk` revisitant les methodes en noeuds independants, tout nom de methode
#      comptait DOUBLE -> `execute_normal_like` sortait « ambigu 2 definitions dont 1 »,
#      donc EXCLU de la resolution par nom, donc ses call-sites en DEFAUT invisibles.
#
# ECRITURE : tmpdir SYSTEME (`mkdtemp()` SANS `dir=`). Un cliquet n'ecrit JAMAIS sous
# `scripts/python/` -- la banque tourne en parallele, et #455 a mesure la course.

_SRC_FONCTION = '''
def porte(base, spread_pct=%s):
    return base * spread_pct

def appelant():
    return porte(10)
'''

_SRC_CLASSE_GATEE = '''
class Feuille:
    def __init__(self, cible, amount=None, spread_pct=0):
        self.cible = cible
        self.amount = amount
        self.spread_pct = int(spread_pct)

    def execute(self):
        if self.amount is not None:
            return self.amount * self.spread_pct
        return 0

def appelants():
    Feuille("bornes")
    Feuille("montant", amount=3)
'''

_SRC_CLASSE_NON_GATEE = '''
class Feuille:
    def __init__(self, cible, amount=None, spread_pct=0):
        self.cible = cible
        self.amount = amount
        self.spread_pct = int(spread_pct)

    def execute(self):
        return self.spread_pct

def appelants():
    Feuille("bornes")
    Feuille("montant", amount=3)
'''


def _arbre(fichiers):
    import tempfile
    base = Path(tempfile.mkdtemp())          # SANS `dir=` : jamais sous scripts/python (#455)
    for rel, code in fichiers.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")
    return base / "engine"


def _un_seul(defs, ko, cas):
    if len(defs) != 1:
        ko.append("%s : %d definition(s) derivee(s), 1 attendue" % (cas, len(defs)))
        return None
    return defs[0]


#: Les rails que les ARBRES SYNTHETIQUES de l'auto-test portent effectivement.
#: L'auto-test eprouve le DETECTEUR (defaut lu, gate, call-site positionnel), pas le PERIMETRE de
#: production : ses arbres tiennent en trois fichiers et ne portent qu'un rail. Or le garde
#: « perimetre AVEUGLE » exige que CHAQUE nom de `VARIANCE_PARAMS` designe au moins une definition
#: de la racine analysee -- exigence juste sur le vrai `engine/`, mais qui rendrait ROUGE tout
#: arbre synthetique des que `VARIANCE_PARAMS` s'elargit (mesure #449-r2-r4-r4 : les 6 rails
#: ajoutes ont fait echouer C13 sur un arbre pourtant CONFORME). On restreint donc le perimetre
#: pendant l'auto-test, et SEULEMENT pendant : le verdict sur l'arbre reel garde les 8 rails.
_SELF_TEST_PARAMS = ("amount_spread_pct", "spread_pct")


def self_test():
    """Rend la liste des echecs. Vide = le detecteur se comporte comme annonce."""
    import shutil
    ko = []
    a_nettoyer = []
    global VARIANCE_PARAMS
    _params_prod = VARIANCE_PARAMS
    VARIANCE_PARAMS = _SELF_TEST_PARAMS

    def arbre(fichiers):
        root = _arbre(fichiers)
        a_nettoyer.append(root.parent)
        return root

    try:
        # --- C1/C2 : LE DEFAUT EST LU, PAS SUPPOSE ------------------------------------
        # Le coeur de #449-r2-r5. Deux arbres RIGOUREUSEMENT identiques a un caractere
        # pres : si le defaut etait code en dur, les deux rendraient la meme chose.
        classes = {}
        for defaut in (0, 20):
            root = arbre({"engine/a.py": _SRC_FONCTION % defaut})
            defs = collect_definitions(root)
            d = _un_seul(defs, ko, "C1 defaut=%s" % defaut)
            if d is not None and d.default != defaut:
                ko.append("C1 : defaut LU = %r, attendu %r (le defaut n'est pas derive)"
                          % (d.default, defaut))
            _index_gates(root, defs)
            _, sites, _ = collect(root, defs)
            sites = [s for s in sites if s["callee"] == "porte"]
            if len(sites) != 1:
                ko.append("C1 : %d call-site(s), 1 attendu" % len(sites))
            else:
                classes[defaut] = sites[0]["value"]
                if sites[0]["source"] != "defaut":
                    ko.append("C1 : source=%r, 'defaut' attendu" % sites[0]["source"])
        if classes.get(0) == classes.get(20):
            ko.append("C2 (NEGATIF) : changer le DEFAUT n'a PAS change le classement du "
                      "call-site (%r vs %r) -- c'est exactement le vice #449-r2-r5"
                      % (classes.get(0), classes.get(20)))

        # --- C2bis (#449-r2-r4) : les QUATRE regimes de defaut sont DISTINGUES ----------
        # Sans ca, la garde « LITTERAL DE SPREAD REVENU » ne pourrait pas mordre : elle
        # repose entierement sur le fait que `= None` et `= 20` ne se classent PAS pareil.
        # Trois arbres identiques au defaut pres + un sans defaut du tout.
        regimes = {}
        for src, attendu in (("def porte(base, spread_pct=None):\n    return spread_pct\n",
                              "LU_BC"),
                             ("def porte(base, spread_pct=20):\n    return spread_pct\n",
                              "LITTERAL"),
                             ("def porte(base, spread_pct):\n    return spread_pct\n",
                              "REQUIS"),
                             ("K = 20\ndef porte(base, spread_pct=K):\n    return spread_pct\n",
                              "DYNAMIQUE")):
            root = arbre({"engine/a.py": src})
            d = _un_seul(collect_definitions(root), ko, "C2bis %s" % attendu)
            if d is not None:
                regimes[attendu] = d.default_kind
                if d.default_kind != attendu:
                    ko.append("C2bis : regime LU = %r, attendu %r" % (d.default_kind, attendu))
        if len(set(regimes.values())) != len(regimes):
            ko.append("C2bis (NEGATIF) : deux regimes de defaut se confondent (%r) -- la garde "
                      "du litteral revenu ne peut plus mordre" % (regimes,))

        # --- C2ter (#449-r2-r4) : un litteral NON NUL fait rougir, un `0` ATTESTE non ----
        for defaut, doit_rougir in ((20, True), (0, False)):
            root = arbre({"engine/a.py":
                          "def porte(base, spread_pct=%d):\n    return spread_pct\n" % defaut})
            cle = ("engine/a.py", "porte", "spread_pct")
            sauve = EXPECTED_DEFAULT
            try:
                globals()["EXPECTED_DEFAULT"] = {cle: (defaut, "attestation de test")}
                _, _, _, reds = evaluate(root)
            finally:
                globals()["EXPECTED_DEFAULT"] = sauve
            vu = any(m == "LITTERAL DE SPREAD REVENU" for m, _ in reds)
            if vu != doit_rougir:
                ko.append("C2ter : defaut=%d -> litteral revenu=%s, attendu %s (l'attestation "
                          "NE DOIT PAS pouvoir blanchir un litteral non nul)"
                          % (defaut, vu, doit_rougir))

        # --- C3 : le mot-cle EXPLICITE prime sur le defaut ------------------------------
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return spread_pct\n"
                                     "def f():\n    return porte(1, spread_pct=0)\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        s = [x for x in sites if x["callee"] == "porte"]
        if len(s) != 1 or s[0]["value"] != 0 or s[0]["source"] != "kwarg":
            ko.append("C3 : kwarg explicite mal lu -> %r" % (s,))

        # --- C4 : le POSITIONNEL est vu (angle mort total d'un inventaire par mot-cle) ---
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return spread_pct\n"
                                     "def f():\n    return porte(1, 0)\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        s = [x for x in sites if x["callee"] == "porte"]
        if len(s) != 1 or s[0]["value"] != 0 or s[0]["source"] != "positionnel":
            ko.append("C4 : argument POSITIONNEL non vu -> %r" % (s,))

        # --- C5 : le GATE est DERIVE du corps ------------------------------------------
        root = arbre({"engine/a.py": _SRC_CLASSE_GATEE})
        defs = collect_definitions(root)
        d = _un_seul(defs, ko, "C5")
        if d is not None and d.gates != frozenset({"amount"}):
            ko.append("C5 : gate derive = %r, {'amount'} attendu" % (set(d.gates),))
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        s = [x for x in sites if x["callee"] == "Feuille"]
        if sorted(x["inert"] for x in s) != [False, True]:
            ko.append("C5 : gate mal applique -> %r" % ([(x["line"], x["inert"]) for x in s],))

        # --- C6 (NEGATIF) : sans `if`, AUCUN gate n'est invente -------------------------
        root = arbre({"engine/a.py": _SRC_CLASSE_NON_GATEE})
        defs = collect_definitions(root)
        d = _un_seul(defs, ko, "C6")
        if d is not None and d.gates:
            ko.append("C6 (NEGATIF) : gate INVENTE %r sur un corps sans condition"
                      % (set(d.gates),))
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        if any(x["inert"] for x in sites if x["callee"] == "Feuille"):
            ko.append("C6 (NEGATIF) : site declare INERTE sans gate")

        # --- C7 : parametre MORT (accepte et jamais lu) ---------------------------------
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return base\n"})
        d = _un_seul(collect_definitions(root), ko, "C7")
        if d is not None and d.reads != 0:
            ko.append("C7 : parametre jamais lu compte %r lecture(s)" % d.reads)
        # ... et son NEGATIF : un parametre bien lu ne doit PAS etre dit mort.
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return base * spread_pct\n"})
        d = _un_seul(collect_definitions(root), ko, "C7bis")
        if d is not None and d.reads == 0:
            ko.append("C7bis (NEGATIF) : parametre LU declare MORT (bug 1 de ce detecteur)")
        # ... y compris dans un @staticmethod, ou il est une variable LOCALE.
        root = arbre({"engine/a.py": "class C:\n    @staticmethod\n"
                                     "    def porte(base, spread_pct=20):\n"
                                     "        return base * spread_pct\n"})
        d = _un_seul(collect_definitions(root), ko, "C7ter")
        if d is not None and d.reads == 0:
            ko.append("C7ter (NEGATIF) : parametre de @staticmethod declare MORT "
                      "(bug 1 de ce detecteur, tel qu'il s'est produit)")

        # --- C7quater (#956) : le lecteur peut vivre dans la classe de BASE --------------
        # LE FAUX POSITIF MESURE, tel qu'il s'est produit sur `master`. La derivation ne
        # cherchait les lectures que dans la MEME `ClassDef`. `ChainAttackDamage` n'a QUE son
        # `__init__` -- il range la variance dans `self.damage`, et c'est `ChainAbilityDamage.
        # execute` (la BASE) qui lit `self.damage`. Resultat : 0 lecture, << parametre MORT >>,
        # sur un port CORRECT.
        _BASE = ("class Base:\n"
                 "    def execute(self):\n        return self.damage\n\n")
        root = arbre({"engine/a.py": _BASE +
                      "class Chaine(Base):\n"
                      "    def __init__(self, cible, spread_pct=0):\n"
                      "        self.cible = cible\n"
                      "        self.damage = (cible, spread_pct)\n"})
        d = [x for x in collect_definitions(root) if x.call_name == "Chaine"]
        if len(d) != 1:
            ko.append("C7quater : %d definition(s) pour `Chaine`, 1 attendue" % len(d))
        elif d[0].reads == 0:
            ko.append("C7quater (NEGATIF) : un parametre lu par une methode HERITEE est declare "
                      "MORT -- c'est le faux positif #956 (`ChainAttackDamage`)")
        # ... LA BORNE : sans elle, la remontee d'heritage pourrait degenerer en << tout est lu >>.
        # Meme arbre, la base ne lit PLUS l'attribut : le parametre redevient MORT.
        root = arbre({"engine/a.py":
                      "class Base:\n    def execute(self):\n        return self.cible\n\n"
                      "class Chaine(Base):\n"
                      "    def __init__(self, cible, spread_pct=0):\n"
                      "        self.cible = cible\n"
                      "        self.damage = (cible, spread_pct)\n"})
        d = [x for x in collect_definitions(root) if x.call_name == "Chaine"]
        if len(d) != 1:
            ko.append("C7quinquies : %d definition(s) pour `Chaine`, 1 attendue" % len(d))
        elif d[0].reads != 0:
            ko.append("C7quinquies (BORNE) : la remontee d'heritage compte %r lecture(s) la ou "
                      "AUCUNE methode ne lit l'attribut" % d[0].reads)
        # ... et LE DOUTE ROUGIT : un nom de base porte par DEUX classes de l'arbre n'est PAS
        # suivi. Suivre au hasard fabriquerait un FAUX NEGATIF, la seule direction dangereuse.
        root = arbre({"engine/a.py": _BASE +
                      "class Chaine(Base):\n"
                      "    def __init__(self, cible, spread_pct=0):\n"
                      "        self.cible = cible\n"
                      "        self.damage = (cible, spread_pct)\n",
                      "engine/b.py": "class Base:\n    def autre(self):\n        return 1\n"})
        d = [x for x in collect_definitions(root) if x.call_name == "Chaine"]
        if len(d) != 1:
            ko.append("C7sexies : %d definition(s) pour `Chaine`, 1 attendue" % len(d))
        elif d[0].reads != 0:
            ko.append("C7sexies (DOUTE) : une base HOMONYME (2 definitions) a ete suivie quand "
                      "meme -- %r lecture(s) comptee(s)" % d[0].reads)
        elif not BASES_NON_RESOLUES:
            ko.append("C7sexies : la base non resolue n'est RAPPORTEE nulle part -- un doute "
                      "silencieux est un angle mort")

        # --- C8 : defaut NON LITTERAL -> ingardable, donc rouge --------------------------
        root = arbre({"engine/a.py": "SP = 20\ndef porte(base, spread_pct=SP):\n"
                                     "    return base * spread_pct\n"})
        d = _un_seul(collect_definitions(root), ko, "C8")
        if d is not None and not d.default_dynamic:
            ko.append("C8 : defaut non litteral pris pour un litteral")

        # --- C9 : `*args` -> INDETERMINE, jamais classe en DEFAUT ------------------------
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return spread_pct\n"
                                     "def f(a):\n    return porte(*a)\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        s = [x for x in sites if x["callee"] == "porte"]
        if len(s) != 1 or not s[0]["unresolved"]:
            ko.append("C9 : `*args` classe %r au lieu d'INDETERMINE" % (s,))

        # --- C10 : nom AMBIGU -> declare, jamais resolu en silence -----------------------
        root = arbre({"engine/a.py": "class A:\n    def execute(self, spread_pct=0):\n"
                                     "        return spread_pct\n"
                                     "class B:\n    def execute(self):\n        return 1\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, _, ambigus = collect(root, defs)
        if "execute" not in ambigus:
            ko.append("C10 : nom homonyme NON declare ambigu -> %r" % (sorted(ambigus),))
        # ... et son NEGATIF : un nom porte par une SEULE definition n'est pas ambigu
        # (bug 2 de ce detecteur : `ast.walk` comptait chaque methode DEUX fois).
        root = arbre({"engine/a.py": "class A:\n    def porte(self, spread_pct=0):\n"
                                     "        return spread_pct\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, _, ambigus = collect(root, defs)
        if "porte" in ambigus:
            ko.append("C10bis (NEGATIF) : nom UNIQUE declare ambigu (bug 2 de ce detecteur)")

        # --- C11 (NEGATIF) : une valeur DYNAMIQUE n'est pas un zero ----------------------
        root = arbre({"engine/a.py": "def porte(base, spread_pct=20):\n    return spread_pct\n"
                                     "def f(x):\n    return porte(1, spread_pct=x)\n"})
        defs = collect_definitions(root)
        _index_gates(root, defs)
        _, sites, _ = collect(root, defs)
        s = [x for x in sites if x["callee"] == "porte"]
        if len(s) != 1 or not s[0]["dynamic"] or s[0]["value"] == 0:
            ko.append("C11 (NEGATIF) : valeur dynamique mal classee -> %r" % (s,))

        # --- C12 (LIMITE ASSUMEE) : un parametre au nom VOISIN n'est PAS vu --------------
        root = arbre({"engine/a.py": "def porte(base, spread=0):\n    return base * spread\n"})
        if collect_definitions(root):
            ko.append("C12 : `spread` (hors VARIANCE_PARAMS) a ete recense -- le perimetre "
                      "n'est plus celui qui est documente")

        # --- C13 : le VERDICT, bout en bout, dans les deux sens --------------------------
        # L'arbre porte les DEUX parametres de `VARIANCE_PARAMS` : sans cela, la garde
        # « perimetre AVEUGLE » -- qui est JUSTE sur l'arbre reel -- rougit ici. Trouve par
        # ce meme auto-test ; on corrige le CAS DE TEST, jamais la garde.
        root = arbre({"engine/a.py": _SRC_FONCTION % 0,
                      "engine/b.py": "def porte_amount(base, amount_spread_pct=0):\n"
                                     "    return base * amount_spread_pct\n"})
        cle = ("engine/a.py", "porte", "spread_pct")
        cle_b = ("engine/b.py", "porte_amount", "amount_spread_pct")
        sauve_d, sauve_z = EXPECTED_DEFAULT, EXPECTED_ZERO
        try:
            globals()["EXPECTED_DEFAULT"] = {cle: (0, "attestation de test"),
                                             cle_b: (0, "attestation de test")}
            globals()["EXPECTED_ZERO"] = {("engine/a.py", "porte"): "attestation de test"}
            _, _, _, reds = evaluate(root)
            if reds:
                ko.append("C13 : arbre CONFORME rendu ROUGE -> %r" % (reds,))
            globals()["EXPECTED_DEFAULT"] = {cle: (20, "attestation de test"),
                                             cle_b: (0, "attestation de test")}
            _, _, _, reds = evaluate(root)
            if not any(m == "DEFAUT contredit le decompile" for m, _ in reds):
                ko.append("C13bis : defaut DIVERGENT du decompile non signale -> %r" % (reds,))
            globals()["EXPECTED_DEFAULT"] = {}
            _, _, _, reds = evaluate(root)
            if not any(m == "porte de variance NON ATTESTEE" for m, _ in reds):
                ko.append("C13ter : porte de variance NEUVE non signalee -> %r" % (reds,))
        finally:
            globals()["EXPECTED_DEFAULT"] = sauve_d
            globals()["EXPECTED_ZERO"] = sauve_z
    finally:
        VARIANCE_PARAMS = _params_prod      # le verdict sur l'arbre REEL garde tous les rails
        for base in a_nettoyer:
            shutil.rmtree(base, ignore_errors=True)
    return ko


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="detail par site")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-test du detecteur (diagnostic)")
    ap.add_argument("--root", default=None,
                    help="racine `engine/` a balayer (defaut : celle de ce checkout)")
    args = ap.parse_args()

    echecs = self_test()
    print("=== AUTO-TEST DU DETECTEUR ===")
    if echecs:
        print("ROUGE: %d cas d'auto-test en echec -- le detecteur ne fait pas ce qu'il dit, "
              "son verdict sur l'arbre ne vaut donc RIEN." % len(echecs))
        for e in echecs:
            print("  [auto-test] %s" % e)
        return 1
    print("OK: le detecteur derive bien le defaut, la position, le gate et le perimetre.")
    if args.self_test:
        return 0

    root = Path(args.root).resolve() if args.root else ENGINE
    if not root.is_dir():
        print("FAIL: engine/ introuvable sous %s" % root)
        return 1

    defs, sites, ambigus, reds = evaluate(root)

    print("=== PERIMETRE DERIVE -- definitions portant un parametre de variance ===")
    print("parametres cherches: %s" % ", ".join(VARIANCE_PARAMS))
    print("definitions: %d" % len(defs))
    for d in sorted(defs, key=lambda x: (x.file, x.line)):
        print("  %-56s %s:%d  param=%-18s defaut=%-9s pos=%-4s gate=%s"
              % (d.call_name, d.file, d.line, d.param,
                 d.default if d.default_kind == "LITTERAL" else d.default_kind,
                 d.pos_index if d.pos_index is not None else "kw",
                 ",".join(sorted(d.gates)) if d.gates else "-"))
    if BASES_NON_RESOLUES:
        # LE DOUTE EST DIT (#956). Ces classes ont une base que l'index n'a pas su designer, donc
        # ses methodes n'ont PAS ete visitees : le compte de lectures y est MINORE, ce qui pousse
        # vers le rouge (le sens SUR), mais un lecteur doit savoir que la remontee s'est arretee.
        print("bases NON RESOLUES (heritage non suivi -- lectures possiblement MINOREES) : %d"
              % len(BASES_NON_RESOLUES))
        for (rel, nom), bases in sorted(BASES_NON_RESOLUES.items()):
            print("  %-56s %s <- %s" % (nom, rel, ", ".join(sorted(bases))))

    actifs = [s for s in sites if not s["inert"]]
    inertes = [s for s in sites if s["inert"]]
    print("=== CALL-SITES ===")
    print("  actifs                  : %d" % len(actifs))
    print("  inertes (hors gate)     : %d" % len(inertes))
    bc = [s for s in actifs if s.get("from_bc")]
    reste = [s for s in actifs if not s.get("from_bc")]
    z = [s for s in reste if not s["dynamic"] and not s["unresolved"] and s["value"] == 0]
    nz = [s for s in reste if not s["dynamic"] and not s["unresolved"] and s["value"] != 0]
    dyn = [s for s in reste if s["dynamic"] or s["unresolved"]]
    print("  variance LUE DE LA BC    : %d" % len(bc))
    print("  variance NULLE (0)       : %d" % len(z))
    print("  variance NON NULLE       : %d" % len(nz))
    print("  variance DYNAMIQUE       : %d" % len(dyn))
    if args.list:
        for s in sorted(actifs, key=lambda x: (x["file"], x["line"])):
            print("    %s:%d  %s(%s)  spread=%s  %s"
                  % (s["file"], s["line"], s["callee"], s["param"],
                     "BC" if s.get("from_bc") else ("dyn" if s["dynamic"] else s["value"]),
                     s["source"]))

    print("=== ANGLE MORT NOMME -- noms d'appel AMBIGUS (non inventoriables par nom) ===")
    if not ambigus:
        print("  aucun")
    for name in sorted(ambigus):
        tot, port = ambigus[name]
        print("  %-24s %d definitions sous engine/, dont %d portant une variance -- seuls "
              "ses mots-cles LITTERAUX sont vus" % (name, tot, port))

    print("=== VERDICT ===")
    if reds:
        print("ROUGE: %d desaccord(s) entre ce qui est DERIVE et ce qui est ATTESTE." % len(reds))
        # Les motifs STRUCTURELS d'abord, et les repetitions capees : une seule faute de
        # structure (un parametre devenu MORT, un gate qui disparait) fait basculer d'un coup
        # les dizaines de call-sites qui en dependaient. Les imprimer tous noierait la CAUSE
        # sous ses consequences -- et `ratchets.ps1` ne montre que les 14 premieres lignes.
        ordre = ("perimetre AVEUGLE", "parametre MORT", "LITTERAL DE SPREAD REVENU",
                 "signature ingardable",
                 "DEFAUT contredit le decompile", "porte de variance NON ATTESTEE",
                 "attestation de defaut PERIMEE", "variance INDETERMINABLE",
                 "REGRESSION : attendu 0", "attestation de zero PERIMEE", "zero NON JUSTIFIE")
        rang = {m: i for i, m in enumerate(ordre)}
        vus = {}
        for motif, detail in sorted(reds, key=lambda r: rang.get(r[0], len(ordre))):
            vus[motif] = vus.get(motif, 0) + 1
            if vus[motif] <= 10:
                print("  [%s] %s" % (motif, detail))
        for motif in ordre:
            if vus.get(motif, 0) > 10:
                print("  [%s] ... et %d autre(s) du meme motif" % (motif, vus[motif] - 10))
        print("  -> lire l'artefact natif (8e arg Nullable<AttackDamageBehaviourOptions> pour")
        print("     un call-site ; le canal de variance pour un defaut), puis inscrire la")
        print("     raison dans EXPECTED_ZERO / EXPECTED_DEFAULT, ou corriger le port.")
        return 1
    print("VERT: %d definition(s) attestee(s), %d call-site(s) actif(s), %d a variance nulle "
          "tous justifies au decompile." % (len(defs), len(actifs), len(z)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
