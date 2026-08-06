"""#270-r4-r2 -- EMPREINTE value-preserving : la coupe des cycles n'a rien change des VALEURS.

Un recablage d'imports ne doit RIEN changer. On le prouve en hachant, pour tout module
d'`engine/`, la valeur de CHAQUE attribut de module ET de classe, puis en comparant a un
arbre TEMOIN extrait par `git archive` (arbre COMPLET, pas seulement `scripts/python` :
sans `data/`, les caches *lazy* alimentes par le gameconfig restent vides d'un seul cote
et rendent des divergences FAUSSES).

Deux pieges deja mesures dans ce depot, tous deux evites ici :
  * hacher la REPRESENTATION (`repr`) rougit sur `6` vs `<PathfinderType...: 6>` alors qu'un
    `IntEnum` EST un `int` -> on canonicalise par `int(x)`, RECURSIVEMENT dans les conteneurs ;
  * une LISTE de structures choisies ne peut pas montrer la valeur qu'elle a oubliee -> la
    portee est LARGE (tout attribut public de module et de classe).

#270-r4-r2-r2-r2 -- UN FILET QUI RAPPORTE N'EST PAS UNE GARDE
-------------------------------------------------------------
Cette sonde VOYAIT deja une disparition de nom (197 116 -> 197 115, elle l'IMPRIMAIT) et rendait
`rc 0` : son verdict ne dependait QUE des divergences de VALEUR. Mesure a la relecture de #694 :
un hissage CASSE (import SUPPRIME au lieu d'etre deplace, `services/movement_query.py` ->
`is_like_flying`) ne faisait rougir NI la garde offline NI cette sonde. Un filet qui rapporte
sans echouer exige un lecteur humain -- exactement ce qu'une garde est censee supprimer.

QUATRE categories, et TROIS sont des regressions :
  * VALEUR    l'attribut existe des DEUX cotes et sa valeur a change              -> ECHEC ;
  * DISPARU   un nom qui n'est plus la. C'est la signature d'un hissage CASSE     -> ECHEC,
              sauf s'il est DECLARE par `--disparition-voulue <nom>` ;
  * IMPORT    un module qui s'importait dans le TEMOIN et ne s'importe plus       -> ECHEC.
              Il etait invisible : la cle `!IMPORT!<mod>` APPARAISSAIT, et un APPARU ne
              comptait pas ;
  * APPARU    un NOM neuf au niveau module. C'est ce que PRODUIT un hissage (le nom importe
              devient attribut du module) : liste, jamais un echec.

L'ECHAPPATOIRE est EXPLICITE, COMPTEE, IMPRIMEE -- et PERIMABLE : une declaration qui ne
correspond a AUCUNE disparition reelle fait ECHOUER elle aussi. Une porte laissee ouverte apres
usage est le mode de defaillance suivant.

Usage :
    python probe_270r4r2_empreinte_valeurs.py --emettre <fichier.json>
    python probe_270r4r2_empreinte_valeurs.py --comparer <temoin.json>
    python probe_270r4r2_empreinte_valeurs.py --comparer <temoin.json> \\
        --disparition-voulue engine.services.movement_query.is_like_flying
    python probe_270r4r2_empreinte_valeurs.py --mutants     # contre-epreuve, sans arbre temoin
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import pkgutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent

_ATOMES = (bool, int, float, str, bytes, type(None))


def _canon(v, prof=0):
    """Canonicalise EN VALEUR. `int(x)` sur tout ce qui est un int (donc les IntEnum),
    recursivement dans les conteneurs. Ce qui n'est pas serialisable rend un marqueur de TYPE."""
    if prof > 6:
        return "<profondeur>"
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, int):
        return int(v)          # dissout IntEnum / IntFlag
    if isinstance(v, float):
        return "f:%.12g" % v
    if isinstance(v, (str, bytes, type(None))):
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else v
    if isinstance(v, (list, tuple)):
        return [type(v).__name__] + [_canon(x, prof + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        try:
            elems = sorted(_canon(x, prof + 1) for x in v)
        except TypeError:
            elems = sorted((repr(_canon(x, prof + 1)) for x in v))
        return [type(v).__name__] + elems
    if isinstance(v, dict):
        out = []
        for k in v:
            out.append([_canon(k, prof + 1), _canon(v[k], prof + 1)])
        try:
            out.sort(key=lambda p: repr(p[0]))
        except TypeError:
            pass
        return ["dict"] + out
    return "<%s>" % type(v).__name__


def _attributs(obj, prefixe: str, out: dict, prof: int) -> None:
    for nom in sorted(vars(obj) if hasattr(obj, "__dict__") else ()):
        if nom.startswith("__"):
            continue
        try:
            v = getattr(obj, nom)
        except Exception as e:                       # property qui leve, descripteur...
            out["%s.%s" % (prefixe, nom)] = "<ERR %s>" % type(e).__name__
            continue
        if isinstance(v, type):
            # CLASSE : on descend d'un cran (attributs de classe), une seule fois
            if prof == 0 and getattr(v, "__module__", "").startswith("engine"):
                _attributs(v, "%s.%s" % (prefixe, nom), out, prof + 1)
            out["%s.%s" % (prefixe, nom)] = "<class>"
            continue
        if callable(v) and not isinstance(v, _ATOMES):
            out["%s.%s" % (prefixe, nom)] = "<callable>"
            continue
        out["%s.%s" % (prefixe, nom)] = _canon(v)


def empreinte() -> dict:
    import engine
    mods = []
    for m in pkgutil.walk_packages(engine.__path__, prefix="engine."):
        mods.append(m.name)
    mods.append("engine")
    out: dict[str, object] = {}
    n_ok = n_ko = 0
    for nom in sorted(set(mods)):
        try:
            mod = importlib.import_module(nom)
        except Exception as e:
            out["!IMPORT!" + nom] = "%s: %s" % (type(e).__name__, e)
            n_ko += 1
            continue
        n_ok += 1
        _attributs(mod, nom, out, 0)
    out["!TEMOIN!modules_importes"] = n_ok
    out["!TEMOIN!modules_en_echec"] = n_ko
    out["!TEMOIN!attributs"] = len(out)
    return out


def _sha(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=repr).encode("utf-8")).hexdigest()


ABSENT = "<!ABSENT!>"
PREFIXE_IMPORT = "!IMPORT!"
PREFIXE_TEMOIN = "!TEMOIN!"


def comparer(ref: dict, emp: dict, voulues=()) -> dict:
    """Le TRI, isole de toute E/S -- c'est ce qui le rend testable sur des dicts synthetiques.

    Rend un dict de categories + `rc`. Trois categories font echouer (VALEUR, DISPARU non
    declare, IMPORT casse), plus les declarations PERIMEES."""
    voulues = set(voulues)
    cles = sorted((set(ref) | set(emp)) - {k for k in set(ref) | set(emp)
                                           if k.startswith(PREFIXE_TEMOIN)})
    val, apparus, disparus, imports_casses, imports_repares = [], [], [], [], []
    for k in cles:
        a, b = ref.get(k, ABSENT), emp.get(k, ABSENT)
        if a == b:
            continue
        if k.startswith(PREFIXE_IMPORT):
            # `!IMPORT!<mod>` n'existe que si le module a ECHOUE a s'importer. Sa presence
            # dans la MESURE et pas dans le TEMOIN = une regression d'import -- invisible
            # jusqu'ici, parce qu'un APPARU ne comptait pas.
            (imports_casses if a == ABSENT else imports_repares).append(
                (k[len(PREFIXE_IMPORT):], b if a == ABSENT else a))
            continue
        if a == ABSENT:
            apparus.append((k, b))
        elif b == ABSENT:
            disparus.append((k, a))
        else:
            val.append((k, a, b))
    noms_disparus = {k for k, _ in disparus}
    non_declarees = [t for t in disparus if t[0] not in voulues]
    declarees_utilisees = sorted(voulues & noms_disparus)
    declarees_perimees = sorted(voulues - noms_disparus)
    return {
        "cles": cles,
        "val": val,
        "apparus": apparus,
        "disparus": disparus,
        "disparus_non_declares": non_declarees,
        "imports_casses": imports_casses,
        "imports_repares": imports_repares,
        "declarations_utilisees": declarees_utilisees,
        "declarations_perimees": declarees_perimees,
        "rc": 1 if (val or non_declarees or imports_casses or declarees_perimees) else 0,
    }


# ------------------------------------------------------------------ contre-epreuve par mutants

#: Un jeu de dicts SYNTHETIQUES : la contre-epreuve n'a besoin d'aucun arbre temoin, donc elle
#: tourne partout et ne peut pas devenir inerte faute de materiel. `a_mordu` est rendu SEPAREMENT
#: du verdict -- une contre-epreuve inerte passe pour mordante.
_REF_SYNTH = {
    "engine.m.A": 1, "engine.m.B": 2, "engine.m.C": ["list", 1, 2],
    "!TEMOIN!attributs": 3, "!TEMOIN!modules_importes": 1, "!TEMOIN!modules_en_echec": 0,
}

MUTANTS = [
    ("LA FAUTE HISTORIQUE : un nom DISPARU (import supprime au lieu d'etre deplace)",
     {"engine.m.A": 1, "engine.m.C": ["list", 1, 2]}, (), 1),
    ("divergence de VALEUR (deja couverte avant cette tranche)",
     {"engine.m.A": 1, "engine.m.B": 99, "engine.m.C": ["list", 1, 2]}, (), 1),
    ("un MODULE qui ne s'importe plus (cle !IMPORT! APPARUE)",
     {"engine.m.A": 1, "engine.m.B": 2, "engine.m.C": ["list", 1, 2],
      "!IMPORT!engine.m": "ImportError: cannot import name 'X'"}, (), 1),
    ("declaration PERIMEE : rien n'a disparu, la porte reste ouverte",
     {"engine.m.A": 1, "engine.m.B": 2, "engine.m.C": ["list", 1, 2]}, ("engine.m.B",), 1),
    ("un NOM APPARU (effet ATTENDU d'un hissage) : liste, JAMAIS un echec",
     {"engine.m.A": 1, "engine.m.B": 2, "engine.m.C": ["list", 1, 2], "engine.m.D": 4}, (), 0),
    ("disparition DECLAREE : l'echappatoire laisse passer",
     {"engine.m.A": 1, "engine.m.C": ["list", 1, 2]}, ("engine.m.B",), 0),
    ("arbres IDENTIQUES : rc 0 (sinon la sonde rougirait sur tout)",
     dict(_REF_SYNTH), (), 0),
]


def contre_epreuve() -> int:
    print("\nCONTRE-EPREUVE PAR MUTANTS (a_mordu est rendu SEPAREMENT du verdict)")
    echecs = 0
    for nom, mesure, voulues, rc_attendu in MUTANTS:
        d = comparer(_REF_SYNTH, mesure, voulues)
        ok = d["rc"] == rc_attendu
        etiquette = ("MORD" if rc_attendu else "PASSE") if ok else "INERTE"
        print("  %-6s rc=%d (attendu %d)  %s" % (etiquette, d["rc"], rc_attendu, nom))
        if not ok:
            echecs += 1
            print("        val=%d disparus_non_declares=%d imports_casses=%d perimees=%d"
                  % (len(d["val"]), len(d["disparus_non_declares"]),
                     len(d["imports_casses"]), len(d["declarations_perimees"])))
    print("  -> %d mutant(s) INERTE(s) sur %d" % (echecs, len(MUTANTS)))
    return echecs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emettre")
    ap.add_argument("--comparer")
    ap.add_argument("--disparition-voulue", action="append", default=[], metavar="NOM",
                    help="declare une suppression VOULUE (repetable). Comptee, imprimee -- et "
                         "une declaration qui ne correspond a AUCUNE disparition ECHOUE.")
    ap.add_argument("--mutants", action="store_true",
                    help="contre-epreuve du TRI sur des dicts synthetiques (aucun arbre temoin)")
    ap.add_argument("--noms", action="store_true",
                    help="liste INTEGRALE des noms apparus/disparus (par defaut : resume par classe)")
    args = ap.parse_args()

    if args.mutants and not (args.emettre or args.comparer):
        return 1 if contre_epreuve() else 0

    emp = empreinte()
    n_mod = emp["!TEMOIN!modules_importes"]
    n_ko = emp["!TEMOIN!modules_en_echec"]
    n_att = emp["!TEMOIN!attributs"]
    print("[270-r4-r2/empreinte] TEMOIN : %d modules importes, %d en echec, %d attributs haches"
          % (n_mod, n_ko, n_att))
    if n_mod == 0 or n_att < 100:
        print("[270-r4-r2/empreinte] ECHEC : portee VIDE ou derisoire -- un zero ne prouve RIEN")
        return 2

    if args.emettre:
        Path(args.emettre).write_text(json.dumps(emp, sort_keys=True, default=repr),
                                      encoding="utf-8")
        print("[270-r4-r2/empreinte] ecrit -> %s  (sha256 %s)" % (args.emettre, _sha(emp)[:16]))
        return 0

    if args.comparer:
        ref = json.loads(Path(args.comparer).read_text(encoding="utf-8"))
        d = comparer(ref, emp, args.disparition_voulue)
        cles, val = d["cles"], d["val"]
        apparus, disparus = d["apparus"], d["disparus"]
        print("[270-r4-r2/empreinte] temoin : %s attributs / mesure : %s / compares : %d"
              % (ref.get("!TEMOIN!attributs"), n_att, len(cles)))
        print("[270-r4-r2/empreinte] NOMS apparus = %d (effet ATTENDU d'un import HISSE, jamais "
              "un echec), NOMS disparus = %d (dont %d DECLARES)"
              % (len(apparus), len(disparus),
                 len(disparus) - len(d["disparus_non_declares"])))
        print("[270-r4-r2/empreinte] modules en echec : temoin %s / mesure %s"
              % (ref.get("!TEMOIN!modules_en_echec"), n_ko))
        # Resume par RACINE (`<module>.<nom>` sans les attributs de classe) : hisser un enum
        # fait apparaitre ses ~110 membres, qui noieraient le signal s'ils etaient tous listes.
        for titre, lot in (("+", apparus), ("-", disparus)):
            racines = {}
            for k, v in lot:
                r = k.split(".")
                # coupe apres le 1er segment qui commence par une MAJUSCULE (= une classe)
                for i, seg in enumerate(r):
                    if seg[:1].isupper():
                        r = r[:i + 1]
                        break
                racines.setdefault(".".join(r), []).append((k, v))
            for rac in sorted(racines):
                sites = racines[rac]
                if len(sites) == 1:
                    print("   %s %s = %s" % (titre, sites[0][0], repr(sites[0][1])[:140]))
                else:
                    print("   %s %s  (+%d attributs de cette classe)" % (titre, rac, len(sites) - 1))
        if args.noms:
            for titre, lot in (("+", apparus), ("-", disparus)):
                for k, v in lot:
                    print("      %s %s = %s" % (titre, k, repr(v)[:140]))

        # -- ECHAPPATOIRE : comptee, imprimee, et PERIMABLE --------------------------------
        print("[270-r4-r2/empreinte] DISPARITIONS declarees voulues : %d utilisee(s), "
              "%d PERIMEE(s)" % (len(d["declarations_utilisees"]),
                                 len(d["declarations_perimees"])))
        for nom in d["declarations_utilisees"]:
            print("   (voulue) %s" % nom)
        for nom in d["declarations_perimees"]:
            print("   ECHEC (declaration PERIMEE, porte laissee ouverte) : %s n'a PAS disparu"
                  % nom)
        if d["imports_repares"]:
            print("[270-r4-r2/empreinte] %d module(s) qui ECHOUAIENT dans le temoin s'importent "
                  "maintenant (amelioration, jamais un echec)" % len(d["imports_repares"]))

        # -- LES TROIS REGRESSIONS ---------------------------------------------------------
        if val:
            print("[270-r4-r2/empreinte] ECHEC : %d divergence(s) de VALEUR" % len(val))
            for k, a, b in val[:60]:
                print("   %s\n      temoin : %s\n      mesure : %s" % (k, repr(a)[:200], repr(b)[:200]))
        if d["disparus_non_declares"]:
            print("[270-r4-r2/empreinte] ECHEC : %d NOM(S) DISPARU(S) non declare(s) -- "
                  "signature d'un hissage CASSE (import SUPPRIME au lieu d'etre DEPLACE)."
                  % len(d["disparus_non_declares"]))
            print("   Si la suppression est VOULUE, la DECLARER : "
                  "--disparition-voulue <nom> (repetable).")
            for k, a in d["disparus_non_declares"][:60]:
                print("   - %s  (valeur au temoin : %s)" % (k, repr(a)[:140]))
        if d["imports_casses"]:
            print("[270-r4-r2/empreinte] ECHEC : %d module(s) s'importaient dans le TEMOIN et "
                  "ne s'importent PLUS" % len(d["imports_casses"]))
            for mod, err in d["imports_casses"][:40]:
                print("   - %s -> %s" % (mod, str(err)[:160]))
        if d["rc"] == 0:
            print("[270-r4-r2/empreinte] OK : 0 divergence de VALEUR, 0 nom disparu non declare, "
                  "0 import casse, sur %d attributs compares" % len(cles))
        rc = d["rc"]
        if args.mutants:
            rc = 1 if (contre_epreuve() or rc) else 0
        return rc

    print("[270-r4-r2/empreinte] sha256 = %s" % _sha(emp))
    if args.mutants:
        return 1 if contre_epreuve() else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
