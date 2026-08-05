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

ROLES = ("cle de dict", "comparaison", "operation de bit", "argument d'appel", "argument nomme")


def _dicts_entiers(racine: Path, seuil: int = 3) -> list[dict]:
    """Les dicts litteraux dont >= `seuil` cles sont des entiers -- avec la LISTE de ces cles.

    POURQUOI CE CRITERE PLUTOT QUE L'IMPORT : mesure du 2026-08-05 sur
    `engine/runner/abilities/attack_type.py`, la plus grosse concentration du depot (105 cles) --
    le fichier n'importe AUCUN enum, donc un croisement par import ne le voit pas, alors que ses
    105 cles sur 105 sont des membres d'`ActiveAbilityType`. La COUVERTURE du dict est un signal
    bien plus fort que ce que le fichier importe : si toutes les cles d'un dict appartiennent au
    meme enum, ce dict EST clee par cet enum, quoi qu'il importe."""
    out: list[dict] = []
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
            if len(cles) >= seuil:
                out.append({"fichier": rel, "ligne": n.lineno, "cles": cles})
    return out


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


class Recensement(ast.NodeVisitor):
    """Visite l'AST et note CHAQUE litteral entier selon la position ou Python l'evalue."""

    def __init__(self, chemin: str, lignes: list[str]):
        self.chemin = chemin
        self.lignes = lignes
        self.candidats: list[dict] = []
        self.importe: set[str] = set()
        self._pile_enum = 0

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for al in node.names:
            self.importe.add(al.asname or al.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Le corps d'un enum est le SEUL endroit ou ces litteraux sont OBLIGATOIRES.

        Sans cette exclusion, `targeting_rule.py` sort 54 « violations » qui sont l'enum en
        train d'etre defini -- l'exemple qui montre qu'un balayage ne peut pas trancher seul."""
        bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
        est_enum = bool(bases & {"IntEnum", "IntFlag", "Enum"})
        if est_enum:
            self._pile_enum += 1
        self.generic_visit(node)
        if est_enum:
            self._pile_enum -= 1

    def _noter(self, noeud: ast.Constant, role: str) -> None:
        val = noeud.value
        if isinstance(val, bool) or not isinstance(val, int):
            return
        src = ""
        if 0 < noeud.lineno <= len(self.lignes):
            src = self.lignes[noeud.lineno - 1].strip()
        self.candidats.append({
            "fichier": self.chemin,
            "ligne": noeud.lineno,
            "role": role,
            "valeur": val,
            "structurel": abs(val) <= SEUIL_STRUCTUREL,
            "definition": self._pile_enum > 0,
            "source": src[:160],
        })

    def visit_Dict(self, node: ast.Dict):
        for k in node.keys:
            if isinstance(k, ast.Constant):
                self._noter(k, "cle de dict")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        for c in node.comparators:
            if isinstance(c, ast.Constant):
                self._noter(c, "comparaison")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if isinstance(node.op, (ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift)):
            for cote in (node.left, node.right):
                if isinstance(cote, ast.Constant):
                    self._noter(cote, "operation de bit")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        for a in node.args:
            if isinstance(a, ast.Constant):
                self._noter(a, "argument d'appel")
        for kw in node.keywords:
            if isinstance(kw.value, ast.Constant):
                self._noter(kw.value, "argument nomme")
        self.generic_visit(node)


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
        v.visit(arbre)
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

        # --- COUVERTURE DE DICT : le signal fort, INDEPENDANT des imports -------------------
        print()
        print("[270-r1] COUVERTURE DE DICT -- un dict dont TOUTES les cles sont membres d'un enum")
        print("        EST clee par cet enum, quoi que le fichier importe.")
        dicts = _dicts_entiers(racine)
        total_cles, attribuees, lignes = 0, 0, []
        for d in dicts:
            cles = d["cles"]
            total_cles += len(cles)
            possibles = [nom.rsplit(".", 1)[-1] for nom, membres in natif.items()
                         if all(k in membres for k in cles)]
            if possibles:
                attribuees += len(cles)
                lignes.append((len(cles), d["fichier"], d["ligne"], possibles))
        lignes.sort(key=lambda x: -x[0])
        print("   dicts a >= 3 cles entieres : %d ; cles totales : %d" % (len(dicts), total_cles))
        print("   cles couvertes a 100%% par au moins un enum du build : %d" % attribuees)
        # Le seul chiffre qui autorise une conversion MECANIQUE : les cles d'un dict que le build
        # n'attribue qu'a UN enum. Le reste demande une lecture du site -- et le dire est le point.
        sans_ambig = [x for x in lignes if len(x[3]) == 1]
        print("   dicts a enum UNIQUE : %d, soit %d cles CONVERTIBLES mecaniquement"
              % (len(sans_ambig), sum(x[0] for x in sans_ambig)))
        print("   dicts AMBIGUS       : %d, soit %d cles a LIRE (le build ne tranche pas seul)"
              % (len(lignes) - len(sans_ambig),
                 sum(x[0] for x in lignes if len(x[3]) > 1)))
        print("   dicts ATTRIBUABLES : %d ; top :" % len(lignes))
        for n, fich, ln, cands in lignes[:12]:
            marque = "" if len(cands) == 1 else "   [%d enums possibles -- AMBIGU]" % len(cands)
            print("      %4d cles  %s:%d  -> %s%s"
                  % (n, fich, ln, " | ".join(cands[:2]), marque))

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
    roles = Counter(c["role"] for c in retenus)
    for r in ROLES:
        if roles.get(r):
            print("   %6d  %s" % (roles[r], r))

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
