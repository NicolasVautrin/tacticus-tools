"""#270-r1 -- ENUMERE les litteraux entiers en position EXECUTABLE sous `engine/`.

CE PROBE NE REND AUCUN VERDICT, ET C'EST SA RAISON D'ETRE.

Le vice qu'il evite est celui d'un balayage qui CHERCHE DES VIOLATIONS : un motif qui essaie de
reconnaitre une faute rate tout ce qu'il n'a pas prevu, et son zero se lit comme « rien a
signaler ». Ici on ne devine pas -- on RECENSE. Tout entier place la ou Python l'EXECUTE est
candidat, sans exception ; l'arbitrage (designateur ? vraie quantite ? site de definition ?
decompile cite ?) appartient a un lecteur, jamais a ce fichier.

Consequence directe : ce probe est COMPLET PAR CONSTRUCTION sur son domaine. L'AST ne voit que
du code -- docstrings et commentaires lui sont invisibles -- donc une citation de decompile
(`if (rules & 0x8000)` recopie dans une docstring) n'y entre JAMAIS, et n'a pas besoin d'etre
filtree.

DEUX FOIS CE PROBE A RENDU UN ZERO RASSURANT, ET DEUX FOIS PAR LA MEME CAUSE -- il ne regardait
pas. Les deux trous sont fermes ici, et la lecon vaut au-dela de ce fichier :
  * ROLE MANQUANT (#270-r1-r1) : ses cinq roles ne visitaient pas `ast.Tuple`/`List`/`Set`, donc
    161 litteraux en position d'ELEMENT DE CONTENEUR n'entraient par aucune porte. Un recenseur
    qui n'enumere pas un role rend zero SUR CE ROLE, et ce zero se lit comme une couverture.
  * SEUIL (#270-r3) : la couverture de dict filtrait a `>= 3 cles`, donc 8 cles reelles dormaient
    dessous et le `0` affiche disait « rien au-dessus de 3 », pas « plus de gisement ». Le seuil
    vaut desormais 1 par defaut, reste reglable (`--seuil-dict`), et CE QU'IL ECARTE EST COMPTE
    ET IMPRIME -- un compte filtre doit dire ce qu'il filtre.

CE QU'IL NE COUVRE PAS, et qui doit etre dit plutot que suppose :
  * les entiers construits (`1 << n` avec `n` variable, `int("0x8000", 16)`, arithmetique) --
    ils ne sont pas des LITTERAUX, donc hors domaine ;
  * les valeurs venues d'un JSON / de la BC -- ce sont des donnees, pas du code ;
  * `scripts/python/tests/**` et les probes -- perimetre volontairement limite a `engine/`,
    le code de PRODUCTION. L'elargir est un choix a poser, pas un defaut a corriger en silence.

UN FICHIER QUI NE PARSE PAS EST LISTE, JAMAIS COMPTE ZERO (tri-etat : `null` != `0`). Un
`SyntaxError` avale sinon tout un fichier en silence, et le total continue de se lire comme une
couverture complete.

Usage :
    python probe_270r1_enum_candidates.py                     # resume par role + par fichier
    python probe_270r1_enum_candidates.py --lister             # TSV, une ligne par candidat
    python probe_270r1_enum_candidates.py --lister --only engine/runner/abilities/targeting.py
    python probe_270r1_enum_candidates.py --lots 12            # propose un decoupage equilibre

Sortie ASCII stricte (console Windows cp1252).
"""
import argparse
import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

RACINE_DEFAUT = Path(__file__).resolve().parent / "engine"

# Un entier de faible magnitude est presque toujours structurel (index, increment, sentinelle
# `-1`, comparaison a 0/1). On ne le JETTE pas -- on le RANGE a part, pour que le lecteur puisse
# decider de l'inclure. Un seuil qui filtre en silence serait le meme vice que le motif qui
# cherche des violations.
SEUIL_STRUCTUREL = 3

ROLES = ("cle de dict", "comparaison", "operation de bit", "argument d'appel", "argument nomme",
         "element de conteneur")

# Le seuil de la COUVERTURE DE DICT. Il vaut 1 -- c'est-a-dire qu'il ne filtre RIEN -- et ce
# defaut est le correctif de #270-r3 : le seuil valait 3, et c'est ce seuil, pas l'absence de
# gisement, qui expliquait le `0` rendu apres le volet 2 (8 cles / 5 dicts restaient dessous).
# Un recenseur qui filtre par CARDINALITE rend un zero rassurant sur ce qu'il ne regarde pas,
# exactement comme un recenseur a qui il manque un ROLE. Le seuil reste REGLABLE (`--seuil-dict`)
# parce qu'un dict a 1 cle est structurellement ambigu -- mais alors ce qu'il ecarte est COMPTE
# et DIT, jamais avale.
SEUIL_DICT_DEFAUT = 1


def _dicts_entiers(racine: Path, seuil: int = SEUIL_DICT_DEFAUT) -> tuple[list[dict], list[dict]]:
    """Les dicts litteraux a cles entieres. Rend (RETENUS >= `seuil`, ECARTES par le seuil).

    POURQUOI CE CRITERE PLUTOT QUE L'IMPORT : mesure du 2026-08-05 sur
    `engine/runner/abilities/attack_type.py`, la plus grosse concentration du depot (105 cles) --
    le fichier n'importe AUCUN enum, donc un croisement par import ne le voit pas, alors que ses
    105 cles sur 105 sont des membres d'`ActiveAbilityType`. La COUVERTURE du dict est un signal
    bien plus fort que ce que le fichier importe : si toutes les cles d'un dict appartiennent au
    meme enum, ce dict EST clee par cet enum, quoi qu'il importe.

    LES ECARTES SONT RENDUS, PAS JETES : un filtre muet est indistinguable d'une absence de
    gisement. C'est la lecon de #270-r3, mesuree -- 8 cles reelles dormaient sous `seuil=3`."""
    retenus: list[dict] = []
    ecartes: list[dict] = []
    for f in sorted(racine.rglob("*.py")):
        try:
            texte = f.read_text(encoding="utf-8")
            arbre = ast.parse(texte)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rel = f.as_posix()
        if "/engine/" in rel:
            rel = "engine/" + rel.split("/engine/", 1)[1]
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Dict):
                continue
            cles = [k.value for k in n.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, int)
                    and not isinstance(k.value, bool)]
            if not cles:
                continue
            (retenus if len(cles) >= seuil else ecartes).append(
                {"fichier": rel, "ligne": n.lineno, "cles": cles})
    return retenus, ecartes


def _conteneurs_entiers(racine: Path, seuil: int = SEUIL_DICT_DEFAUT) -> tuple[list[dict], list[dict]]:
    """Meme chose pour les CONTENEURS litteraux (`ast.Tuple` / `List` / `Set`).

    Le pendant exact de `_dicts_entiers` sur l'axe #270-r1-r1 : un tuple/set dont TOUS les
    elements entiers sont membres d'un meme enum du build EST une collection de membres de cet
    enum, quoi que le fichier importe. C'est le seul discriminant disponible ici -- un conteneur
    n'a pas de « cle », donc pas de couverture de cle ; l'import du fichier, lui, est un signal
    plus FAIBLE (mesure #270-r1 : `attack_type.py` n'importe aucun enum et porte 105 membres).

    On ne visite QUE les conteneurs dont TOUS les elements sont des constantes entieres : un
    tuple heterogene (`("nom", 3, None)`) est une STRUCTURE, pas une collection de designateurs,
    et lui chercher un enum commun n'aurait aucun sens."""
    retenus: list[dict] = []
    ecartes: list[dict] = []
    for f in sorted(racine.rglob("*.py")):
        try:
            texte = f.read_text(encoding="utf-8")
            arbre = ast.parse(texte)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rel = f.as_posix()
        if "/engine/" in rel:
            rel = "engine/" + rel.split("/engine/", 1)[1]
        for n in ast.walk(arbre):
            if not isinstance(n, (ast.Tuple, ast.List, ast.Set)):
                continue
            if not n.elts:
                continue
            vals = [e.value for e in n.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, int)
                    and not isinstance(e.value, bool)]
            if len(vals) != len(n.elts):
                continue
            (retenus if len(vals) >= seuil else ecartes).append(
                {"fichier": rel, "ligne": n.lineno, "cles": vals,
                 "kind": type(n).__name__})
    return retenus, ecartes


def _mirroirs_python(racine: Path) -> dict[str, dict[int, str]]:
    """Les enums Python declares sous `engine/` : {NomClasse: {valeur: membre}}.

    Critere : une classe dont une base s'appelle `IntEnum` / `IntFlag` / `Enum`. On lit les
    affectations `MEMBRE = <litteral>` de son corps. Les membres calcules (`1 << n` avec `n`
    variable, alias) sont ignores -- ils ne sont pas des litteraux, meme regle que le domaine
    du recensement."""
    out: dict[str, dict[int, str]] = {}
    for f in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ClassDef):
                continue
            bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in n.bases}
            if not (bases & {"IntEnum", "IntFlag", "Enum"}):
                continue
            membres: dict[int, str] = {}
            for st in n.body:
                if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)):
                    continue
                v = st.value
                val = None
                if isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(v.value, bool):
                    val = v.value
                elif (isinstance(v, ast.BinOp) and isinstance(v.op, ast.LShift)
                      and isinstance(v.left, ast.Constant) and isinstance(v.right, ast.Constant)):
                    val = v.left.value << v.right.value
                if val is not None:
                    membres.setdefault(val, st.targets[0].id)
            if membres:
                out.setdefault(n.name, {}).update(membres)
    return out


def _table_native(depot: Path) -> dict[str, dict[int, str]]:
    """Les enums DU BUILD, lus dans `data/symbols/<CURRENT>/frida/enums.tsv`.

    C'est la source d'ou proposer un nom -- JAMAIS le miroir Python. Un miroir peut avoir derive
    (`TriggeredAbilityType` porte 107 ids morts, #270-c) : proposer depuis lui ecrirait des noms
    FAUX, pire que l'ordinal, qui ne ment pas."""
    cur = (depot / "data" / "symbols" / "CURRENT")
    if not cur.is_file():
        return {}
    build = cur.read_text(encoding="utf-8").strip()
    tsv = depot / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not tsv.is_file():
        return {}
    out: dict[str, dict[int, str]] = {}
    for ligne in tsv.read_text(encoding="utf-8").splitlines():
        if not ligne or ligne.startswith("#"):
            continue
        parts = ligne.split("\t")
        if len(parts) < 2:
            continue
        nom, corps = parts[0], parts[1]
        membres: dict[int, str] = {}
        for paire in corps.split(","):
            if "=" not in paire:
                continue
            v, m = paire.split("=", 1)
            try:
                membres.setdefault(int(v), m)
            except ValueError:
                continue
        if membres:
            out[nom] = membres
    return out


class Recensement:
    """Partition EXHAUSTIVE des litteraux entiers d'un module, etiquetes par leur noeud PARENT.

    POURQUOI PAS UNE LISTE DE ROLES (le correctif de fond de #270-r1-r1). La version d'origine
    declarait cinq `visit_<X>` et se disait « complete par construction ». Elle ne l'etait pas :
    un role non declare ne rend pas une erreur, il rend ZERO -- et ce zero se lit comme une
    couverture. Trois positions manquaient, mesurees sur le depot :

        `frozenset({1030, 1036})`  element de conteneur   -- le gisement de #270-r1-r1
        `return 7`                 valeur de retour       -- ex. `get_stat_modification_stat`
        `_GALVANIC_REPAIR_ID = 1119`  affectation         -- des designateurs purs

    Ajouter trois `visit_` de plus reconduirait le vice : la liste blanche suivante en oublierait
    une quatrieme. On INVERSE donc le critere -- on visite TOUS les `ast.Constant` entiers, et le
    role se DERIVE du type du noeud parent. Une position inconnue n'est plus invisible : elle
    sort sous le libelle `autre (<NoeudParent>)`, VISIBLE dans le resume. La somme des roles est
    donc, par construction, le nombre total de litteraux entiers du module.

    ⚠ Consequence assumee : les comptes par role ne sont PAS comparables a ceux d'avant
    #270-r1-r1 (`comparaison` ne voyait que le cote DROIT d'un `Compare`, jamais `5 == x`)."""

    # Le libelle est le NOM DU ROLE, pas le nom du noeud : il doit se lire par un humain qui
    # arbitre. Les cinq premiers sont ceux d'origine, conserves a l'identique pour que les
    # decisions deja prises restent citables.
    def __init__(self, chemin: str, lignes: list[str]):
        self.chemin = chemin
        self.lignes = lignes
        self.candidats: list[dict] = []
        self.importe: set[str] = set()

    # ---------------------------------------------------------------- role depuis le parent
    @staticmethod
    def _role(parent: ast.AST | None, noeud: ast.Constant) -> str:
        if parent is None:
            return "module"
        if isinstance(parent, ast.Dict):
            return "cle de dict" if any(k is noeud for k in parent.keys) else "valeur de dict"
        if isinstance(parent, ast.Compare):
            return "comparaison"
        if isinstance(parent, ast.BinOp):
            if isinstance(parent.op, (ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift)):
                return "operation de bit"
            return "operande arithmetique"
        if isinstance(parent, ast.Call):
            return "argument d'appel"
        if isinstance(parent, ast.keyword):
            return "argument nomme"
        if isinstance(parent, (ast.Tuple, ast.List, ast.Set)):
            return "element de conteneur"
        if isinstance(parent, ast.Return):
            return "valeur de retour"
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            return "affectation"
        if isinstance(parent, (ast.Subscript, ast.Slice)):
            return "indice"
        if isinstance(parent, ast.arguments):
            return "valeur par defaut"
        if isinstance(parent, ast.IfExp):
            return "branche de conditionnelle"
        if isinstance(parent, ast.UnaryOp):
            return "operande unaire"
        if isinstance(parent, (ast.FormattedValue, ast.JoinedStr)):
            return "f-string"
        if isinstance(parent, (ast.comprehension, ast.ListComp, ast.SetComp,
                               ast.DictComp, ast.GeneratorExp)):
            return "comprehension"
        if isinstance(parent, (ast.BoolOp, ast.Expr, ast.Starred, ast.Await, ast.Yield)):
            return "expression"
        return "autre (%s)" % type(parent).__name__

    def visiter(self, arbre: ast.AST) -> None:
        # Les enums IMPORTES par le fichier : discriminant CONTEXTUEL du croisement.
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom):
                for al in n.names:
                    self.importe.add(al.asname or al.name)

        # Corps d'enum = le SEUL endroit ou ces litteraux sont OBLIGATOIRES. Sans cette marque,
        # `targeting_rule.py` sort 54 « violations » qui sont l'enum en train d'etre defini.
        dans_enum: set[int] = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.ClassDef):
                bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                         for b in n.bases}
                if bases & {"IntEnum", "IntFlag", "Enum"}:
                    for d in ast.walk(n):
                        dans_enum.add(id(d))

        parent: dict[int, ast.AST] = {}
        for n in ast.walk(arbre):
            for enfant in ast.iter_child_nodes(n):
                parent[id(enfant)] = n

        for n in ast.walk(arbre):
            if not isinstance(n, ast.Constant):
                continue
            val = n.value
            if isinstance(val, bool) or not isinstance(val, int):
                continue
            src = ""
            if 0 < n.lineno <= len(self.lignes):
                src = self.lignes[n.lineno - 1].strip()
            self.candidats.append({
                "fichier": self.chemin,
                "ligne": n.lineno,
                "role": self._role(parent.get(id(n)), n),
                "valeur": val,
                "structurel": abs(val) <= SEUIL_STRUCTUREL,
                "definition": id(n) in dans_enum,
                "source": src[:160],
            })


def recenser(racine: Path, only: list[str] | None) -> tuple[list[dict], list[tuple[str, str]], int]:
    """Rend (candidats, illisibles, nb_fichiers_parses). `illisibles` n'est JAMAIS un zero."""
    fichiers = sorted(racine.rglob("*.py"))
    if only:
        vises = {Path(o).as_posix().lstrip("./") for o in only}
        fichiers = [f for f in fichiers
                    if any(f.as_posix().endswith(v) or v in f.as_posix() for v in vises)]
    candidats: list[dict] = []
    illisibles: list[tuple[str, str]] = []
    parses = 0
    for f in fichiers:
        try:
            texte = f.read_text(encoding="utf-8")
            arbre = ast.parse(texte)
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            illisibles.append((f.as_posix(), type(e).__name__))
            continue
        parses += 1
        rel = f.as_posix()
        marqueur = "/engine/"
        if marqueur in rel:
            rel = "engine/" + rel.split(marqueur, 1)[1]
        v = Recensement(rel, texte.splitlines())
        v.visiter(arbre)
        # Les enums IMPORTES par le fichier sont le discriminant CONTEXTUEL du croisement :
        # chercher une valeur dans les 2 221 enums du build rendrait des centaines de collisions
        # (l'entier `5` existe partout). Ce qu'un fichier importe borne ce qu'il peut designer.
        for c in v.candidats:
            c["importe"] = sorted(v.importe)
        candidats.extend(v.candidats)
    return candidats, illisibles, parses


def _lots(par_fichier: list[tuple[str, int]], n: int) -> list[list[tuple[str, int]]]:
    """Repartit les fichiers en `n` lots de charge comparable (glouton, plus gros d'abord).

    Le decoupage se DERIVE de la mesure : trois fichiers concentrent un tiers des candidats, donc
    un partage par nombre de FICHIERS produirait des lots 30x deseqilibres."""
    lots: list[list[tuple[str, int]]] = [[] for _ in range(n)]
    charges = [0] * n
    for nom, poids in sorted(par_fichier, key=lambda kv: -kv[1]):
        i = charges.index(min(charges))
        lots[i].append((nom, poids))
        charges[i] += poids
    return [l for l in lots if l]


def main() -> int:
    ap = argparse.ArgumentParser(description="#270-r1 : enumere, n'arbitre pas")
    ap.add_argument("--racine", default=str(RACINE_DEFAUT))
    ap.add_argument("--only", nargs="*", help="restreint a ces chemins (sous-chaine suffit)")
    ap.add_argument("--lister", action="store_true", help="TSV, une ligne par candidat")
    ap.add_argument("--structurels", action="store_true",
                    help="inclut les entiers de faible magnitude (|n| <= %d)" % SEUIL_STRUCTUREL)
    ap.add_argument("--lots", type=int, default=0, help="propose un decoupage en N lots")
    ap.add_argument("--croiser", action="store_true",
                    help="propose un membre d'enum par candidat, depuis la table DU BUILD")
    ap.add_argument("--seuil-dict", type=int, default=SEUIL_DICT_DEFAUT,
                    help="cardinalite minimale d'un dict/conteneur pour la couverture "
                         "(defaut %d = ne filtre rien ; ce qui est ecarte est TOUJOURS compte)"
                         % SEUIL_DICT_DEFAUT)
    a = ap.parse_args()

    racine = Path(a.racine)
    if not racine.is_dir():
        print("[270-r1] RACINE INTROUVABLE : %s" % racine)
        return 2

    candidats, illisibles, parses = recenser(racine, a.only)
    definitions = [c for c in candidats if c["definition"]]
    retenus = [c for c in candidats
               if (a.structurels or not c["structurel"]) and not c["definition"]]

    if a.croiser:
        depot = racine.parent.parent.parent          # scripts/python/engine -> racine du depot
        natif = _table_native(depot)
        miroirs = _mirroirs_python(racine)
        # Un miroir Python porte le nom de sa classe (`ActiveAbilityType`) ; son homologue natif
        # est suffixe (`IdunBattle.Entities.Enum.ActiveAbilityType`). On apparie par SUFFIXE.
        appariement = {}
        for nom in miroirs:
            for nat in natif:
                if nat.rsplit(".", 1)[-1] == nom:
                    appariement[nom] = nat
                    break
        nommes, muets = [], []
        for c in retenus:
            props = []
            for imp in c["importe"]:
                if imp not in miroirs:
                    continue
                nat = appariement.get(imp)
                # Le nom vient de la table DU BUILD quand elle existe -- pas du miroir, qui peut
                # avoir derive. Si les deux divergent, on le DIT plutot que de choisir.
                m_nat = natif.get(nat, {}).get(c["valeur"]) if nat else None
                m_py = miroirs[imp].get(c["valeur"])
                if m_nat or m_py:
                    props.append((imp, m_nat, m_py))
            (nommes if props else muets).append((c, props))

        print()
        print("[270-r1] CROISEMENT -- source des noms : table du BUILD (`enums.tsv`), pas le miroir")
        print("   miroirs Python trouves : %d ; apparies au natif : %d"
              % (len(miroirs), len(appariement)))
        print("   candidats avec un membre PROPOSABLE : %d" % len(nommes))
        print("   candidats SANS proposition          : %d" % len(muets))
        # ⚠ Comparer les noms BRUTS mesurerait la CASSE, pas la derive : le miroir Python ecrit
        # `EXTRA_MAX_DAMAGE` la ou le natif ecrit `ExtraMaxDamage`. Mesure du 2026-08-05 : 22
        # « divergences » sur 22 etaient de pures conventions d'ecriture. On normalise.
        def _norm(s: str) -> str:
            return s.replace("_", "").lower()

        divergents = [(c, p) for c, p in nommes
                      if any(mn and mp and _norm(mn) != _norm(mp) for _, mn, mp in p)]
        # Un litteral qui matche PLUSIEURS enums importes est AMBIGU : l'import ne suffit plus a
        # trancher, il faut lire le site. C'est la limite honnete du croisement automatique.
        ambigus = [(c, p) for c, p in nommes if len(p) > 1]
        print("   dont NATIF != MIROIR apres normalisation de casse : %d" % len(divergents))
        print("   dont AMBIGUS (la valeur matche >1 enum importe)   : %d" % len(ambigus))
        surs = [x for x in nommes if x not in ambigus and x not in divergents]
        print("   => proposables SANS ambiguite ni divergence        : %d" % len(surs))
        par_f = Counter(c["fichier"] for c, _ in nommes)
        print("   repartis sur %d fichiers ; top :" % len(par_f))
        for nom, n in par_f.most_common(8):
            print("      %4d  %s" % (n, nom))
        if a.lister:
            print()
            print("fichier\tligne\tvaleur\tenum\tnom_natif\tnom_miroir\tsource")
            for c, props in sorted(nommes, key=lambda x: (x[0]["fichier"], x[0]["ligne"])):
                for imp, mn, mp in props:
                    print("%s\t%d\t%d\t%s\t%s\t%s\t%s"
                          % (c["fichier"], c["ligne"], c["valeur"], imp,
                             mn or "-", mp or "-", c["source"]))
        for c, props in divergents[:10]:
            for imp, mn, mp in props:
                if mn and mp and _norm(mn) != _norm(mp):
                    print("   DIVERGENT %s:%d  %d -> natif=%s  miroir=%s"
                          % (c["fichier"], c["ligne"], c["valeur"], mn, mp))

        # --- COUVERTURE DE DICT et DE CONTENEUR : le signal fort, INDEPENDANT des imports ----
        def _couverture(titre: str, retenus: list[dict], ecartes: list[dict], seuil: int,
                        libelle_unite: str) -> None:
            print()
            print("[270-r1] %s -- un groupe dont TOUS les entiers sont membres d'un enum" % titre)
            print("        EST une collection de membres de cet enum, quoi que le fichier importe.")
            total_cles, attribuees, lignes = 0, 0, []
            for d in retenus:
                cles = d["cles"]
                total_cles += len(cles)
                possibles = [nom.rsplit(".", 1)[-1] for nom, membres in natif.items()
                             if all(k in membres for k in cles)]
                if possibles:
                    attribuees += len(cles)
                    lignes.append((len(cles), d["fichier"], d["ligne"], possibles))
            lignes.sort(key=lambda x: -x[0])
            print("   SEUIL applique : >= %d %s entier(s) par groupe" % (seuil, libelle_unite))
            # UN COMPTE FILTRE DIT CE QU'IL FILTRE (#270-r3). Sans cette ligne, un `0` en tete
            # se lit comme « plus de gisement » alors qu'il ne dit que « rien au-dessus du seuil ».
            print("   ECARTES PAR CE SEUIL : %d groupe(s), %d %s(s) -- NON examines ci-dessous"
                  % (len(ecartes), sum(len(d["cles"]) for d in ecartes), libelle_unite))
            for d in ecartes[:12]:
                print("      ECARTE  %d %s(s)  %s:%d  %s"
                      % (len(d["cles"]), libelle_unite, d["fichier"], d["ligne"],
                         ",".join(str(k) for k in d["cles"][:6])))
            print("   groupes a >= %d %s(s) entiere(s) : %d ; %ss totales : %d"
                  % (seuil, libelle_unite, len(retenus), libelle_unite, total_cles))
            print("   %ss couvertes a 100%% par au moins un enum du build : %d"
                  % (libelle_unite, attribuees))
            # Le seul chiffre qui autorise une conversion MECANIQUE : les entiers d'un groupe que
            # le build n'attribue qu'a UN enum. Le reste demande une lecture du site -- et le dire
            # est le point.
            sans_ambig = [x for x in lignes if len(x[3]) == 1]
            print("   groupes a enum UNIQUE : %d, soit %d %ss CONVERTIBLES mecaniquement"
                  % (len(sans_ambig), sum(x[0] for x in sans_ambig), libelle_unite))
            print("   groupes AMBIGUS       : %d, soit %d %ss a LIRE (le build ne tranche pas seul)"
                  % (len(lignes) - len(sans_ambig),
                     sum(x[0] for x in lignes if len(x[3]) > 1), libelle_unite))
            print("   groupes ATTRIBUABLES : %d ; top :" % len(lignes))
            for n, fich, ln, cands in lignes[:12]:
                marque = "" if len(cands) == 1 else "   [%d enums possibles -- AMBIGU]" % len(cands)
                print("      %4d %ss  %s:%d  -> %s%s"
                      % (n, libelle_unite, fich, ln, " | ".join(cands[:2]), marque))

        d_ret, d_ec = _dicts_entiers(racine, a.seuil_dict)
        _couverture("COUVERTURE DE DICT", d_ret, d_ec, a.seuil_dict, "cle")
        c_ret, c_ec = _conteneurs_entiers(racine, a.seuil_dict)
        _couverture("COUVERTURE DE CONTENEUR (#270-r1-r1)", c_ret, c_ec, a.seuil_dict, "element")

    if a.lister:
        print("fichier\tligne\trole\tvaleur\tsource")
        for c in sorted(retenus, key=lambda c: (c["fichier"], c["ligne"])):
            print("%s\t%d\t%s\t%d\t%s" % (c["fichier"], c["ligne"], c["role"], c["valeur"], c["source"]))
        print()

    print("[270-r1] fichiers parses : %d ; ILLISIBLES : %d" % (parses, len(illisibles)))
    for nom, err in illisibles:
        print("   ILLISIBLE (pas un zero) : %s  [%s]" % (nom, err))

    print("[270-r1] candidats retenus : %d (structurels %s ; %d ecartes comme DEFINITIONS d'enum)"
          % (len(retenus), "INCLUS" if a.structurels else "exclus, |n| <= %d" % SEUIL_STRUCTUREL,
             len(definitions)))
    # On imprime TOUS les roles OBSERVES, jamais une liste ecrite d'avance : une liste ecrite
    # d'avance ne peut pas montrer le role qu'elle a oublie -- c'est exactement le trou de
    # #270-r1-r1. `ROLES` ne sert donc plus qu'a fixer l'ORDRE d'affichage des roles connus ;
    # les autres suivent, par frequence.
    roles = Counter(c["role"] for c in retenus)
    for r in ROLES:
        if roles.get(r):
            print("   %6d  %s" % (roles[r], r))
    for r, n in roles.most_common():
        if r not in ROLES:
            print("   %6d  %s" % (n, r))
    print("   ------  (partition EXHAUSTIVE : somme des roles = %d = candidats retenus)"
          % sum(roles.values()))

    par_fichier = Counter(c["fichier"] for c in retenus)
    print("[270-r1] fichiers porteurs : %d" % len(par_fichier))
    for nom, n in par_fichier.most_common(10):
        print("   %5d  %s" % (n, nom))

    if a.lots:
        print()
        print("[270-r1] decoupage en %d lots (equilibre par CHARGE, pas par nombre de fichiers) :" % a.lots)
        for i, lot in enumerate(_lots(list(par_fichier.items()), a.lots), 1):
            total = sum(p for _, p in lot)
            print("  lot %2d : %4d candidats, %2d fichier(s)" % (i, total, len(lot)))
            for nom, p in lot:
                print("            %4d  %s" % (p, nom))

    print("[270-r1] VERDICT: N/A -- ce probe ENUMERE, il n'arbitre pas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
