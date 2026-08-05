#!/usr/bin/env python3
"""#477-r18 -- PERIMETRE du DEROULE DE BATAILLE dans le flux de replay, DERIVE du natif.

Le port emet le flux et il est egal au natif sur le DEPLOIEMENT (`probe_477r15a`). La borne
(a) de cet oracle publie le reste du chemin : 2 `GroupType` exerces sur 104, 6 `StepType` sur
62, 36 `TagKey` sur 244. Ce probe repond a "qui produit les 102 / 56 / 208 autres, et lesquels
sont MORTS".

CE QU'IL MESURE -- rien n'est enumere a la main :

  1. L'INTERFACE emettrice est DERIVEE, jamais ecrite en dur. `IdunBattle.Streams.IStreamListener`
     declare trois methodes, slots 0/1/2 = `StartGroup` / `FinishGroup` / `Action`. En IL2CPP un
     appel d'interface passe par un helper `FUN_*(<slot>, <Il2CppClass* de l'interface>, <this>,
     <args...>)` : le `DAT_*` de l'interface se DEDUIT de deux temoins independants et le probe
     REFUSE de continuer s'ils ne concordent pas.
  2. Les PRODUCTEURS = les xrefs de ce `DAT_*`. Second canal INDEPENDANT :
     `IdunBattle.Core.AOperation$$get_Events` -- toute fonction qui obtient le flux. L'ecart entre
     les deux ensembles est IMPRIME, dans les deux sens.
  3. Les LITTERAUX de chaque site : `StartGroup(<GroupType>, ...)` / `Action(<StepType>, ...)`.
     Un argument NON litteral (variable) est compte a part et NOMME -- c'est le cas des groupes
     portes par un champ de behaviour, qu'aucune lecture de call-site ne peut trancher.
  4. Les TAGS : `Dictionary<TagKey,int>.Add(dict, &var, ...)` precede de `var = <imm>`. Balaye
     dans les producteurs ET dans les fabriques de tags (`StreamHelper$$Get*Tags`,
     `UnitExtensions$$GetFullStateUpdateTags`).
  5. Le CROISEMENT avec le port : chaque producteur natif est confronte a `engine/`.

CE QU'IL NE VOIT PAS -- imprime a chaque run, jamais rabattu sur un zero :
  - un GroupType/StepType passe par VARIABLE (compte separement, avec ses porteurs) ;
  - un producteur dont le corps est un generique pleinement partage (present dans Ghidra,
    absent du dump Frida) ;
  - les valeurs poussees par du code que Ghidra n'a pas nomme (`FUN_*`).

Sortie ASCII. Aucun ecrit hors `logs/`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghidra_symbols import BINARY, GhidraDown, GhidraMCP, loaded_build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "logs" / "477r18-decompile"

# Les deux temoins servant a DERIVER le Il2CppClass* de IStreamListener. Choisis parce que leur
# role est etabli par la RE deja livree (#477-r15) : l'un n'emet que des `Action`, l'autre ouvre
# et ferme un groupe. Le DAT retenu doit apparaitre dans les DEUX, et porter les trois slots.
TEMOINS_INTERFACE = (
    "IdunBattle.Operations.AddPlayerOperation$$Execute",
    "IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup",
)

SLOT_START_GROUP = 0
SLOT_FINISH_GROUP = 1
SLOT_ACTION = 2

# Fabriques de tags : leur corps ne contient aucun appel au flux, mais il ecrit les TagKey.
FABRIQUES_TAGS = (
    "IdunBattle.Core.Services.StreamHelper$$",
    "IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags",
)

RE_APPEL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
RE_IMM = re.compile(r"^(0x[0-9a-fA-F]+|\d+)$")
#: `local_28[0] = 0xd5;` -- Ghidra ecrit la cle du tag dans une locale juste avant l'`Add`.
RE_AFFECT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)(?:\[0\])?\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;")
#: Le dictionnaire de tags est un `Dictionary<TagKey,int>` : son `Add` gshared se reconnait au
#: `MethodInfo*` passe en DERNIER argument. Ce DAT est DERIVE d'une fabrique temoin, pas ecrit.
RE_DICT_ADD = re.compile(r"Dictionary[A-Za-z0-9_]*u003E__(?:Add|set_Item)\s*\(")


def _args_equilibres(txt: str, i: int) -> tuple[list[str], int]:
    """Decoupe les arguments d'un appel dont la parenthese ouvrante est a `i`."""
    prof, arg, out = 0, [], []
    j = i
    while j < len(txt):
        c = txt[j]
        if c == "(":
            prof += 1
            if prof == 1:
                j += 1
                continue
        elif c == ")":
            prof -= 1
            if prof == 0:
                out.append("".join(arg).strip())
                return out, j + 1
        if prof == 1 and c == ",":
            out.append("".join(arg).strip())
            arg = []
        else:
            arg.append(c)
        j += 1
    return out, j


def appels(code: str):
    """Tous les appels du pseudo-C, sous forme (nom, [args], position)."""
    for m in RE_APPEL.finditer(code):
        args, _ = _args_equilibres(code, m.end() - 1)
        yield m.group(1), args, m.start()


class Ghidra:
    def __init__(self, hors_ligne: bool):
        self.hors_ligne = hors_ligne
        self.g = None
        CACHE.mkdir(parents=True, exist_ok=True)

    def _client(self) -> GhidraMCP:
        if self.g is None:
            self.g = GhidraMCP(timeout=180).connect()
        return self.g

    def build(self) -> str:
        return loaded_build(self._client())

    def xrefs(self, cible: str) -> list:
        f = CACHE / ("xrefs_%s.json" % re.sub(r"[^A-Za-z0-9_]", "_", cible))
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        if self.hors_ligne:
            return []
        res = self._client().call("list_xrefs", {"binary_name": BINARY, "name_or_address": cible})
        # `ghidra-mcp` rend soit {"result":[{...}]} (cible multiple) soit l'objet nu (cible unique).
        if isinstance(res, dict) and isinstance(res.get("result"), list):
            out = res["result"]
            xs = (out[0].get("cross_references") or []) if out else []
        else:
            xs = (res or {}).get("cross_references") or []
        f.write_text(json.dumps(xs), encoding="utf-8")
        return xs

    def decompile(self, nom: str) -> str | None:
        f = CACHE / ("fn_%s.c" % re.sub(r"[^A-Za-z0-9_]", "_", nom))
        if f.exists():
            t = f.read_text(encoding="utf-8", errors="replace")
            return None if t == "\0ABSENT" else t
        if self.hors_ligne:
            return None
        try:
            res = self._client().call("decompile_function",
                                      {"binary_name": BINARY, "name_or_address": nom,
                                       "timeout_sec": 60})
        except (GhidraDown, RuntimeError):
            return None
        if isinstance(res, dict) and isinstance(res.get("result"), list):
            rs = res["result"]
            code = (rs[0].get("code") if rs else None) or ""
        else:
            code = (res or {}).get("code") or ""
        f.write_text(code if code else "\0ABSENT", encoding="utf-8")
        return code or None

    def symboles(self, requete: str, limite: int = 200) -> list:
        f = CACHE / ("sym_%s.json" % re.sub(r"[^A-Za-z0-9_]", "_", requete))
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        if self.hors_ligne:
            return []
        res = self._client().call("search_symbols_by_name",
                                  {"binary_name": BINARY, "query": requete,
                                   "functions_only": True, "limit": limite})
        out = (res or {}).get("symbols") or []
        f.write_text(json.dumps(out), encoding="utf-8")
        return out


def deriver_dat_interface(gh: Ghidra) -> tuple[str, dict]:
    """Le Il2CppClass* de IStreamListener, deduit de deux temoins -- jamais ecrit en dur."""
    vus = []
    for nom in TEMOINS_INTERFACE:
        code = gh.decompile(nom)
        if code is None:
            raise RuntimeError("temoin d'interface introuvable : %s" % nom)
        cand = {}
        for _, args, _pos in appels(code):
            if len(args) >= 3 and RE_IMM.match(args[0] or "") and (args[1] or "").startswith("DAT_"):
                cand.setdefault(args[1], set()).add(int(args[0], 0))
        vus.append(cand)
    communs = set(vus[0]) & set(vus[1])
    # Le bon DAT est celui qui porte les trois slots sur l'union des temoins.
    retenus = [d for d in communs
               if {SLOT_START_GROUP, SLOT_FINISH_GROUP, SLOT_ACTION} <= (vus[0][d] | vus[1][d])]
    if len(retenus) != 1:
        raise RuntimeError("derivation du DAT d'interface AMBIGUE : %r (candidats communs %r)"
                           % (retenus, sorted(communs)))
    dat = retenus[0]
    return dat, {n: sorted(v.get(dat, ())) for n, v in zip(TEMOINS_INTERFACE, vus)}


def charger_mirrors():
    sys.path.insert(0, str(REPO / "scripts" / "python"))
    from engine.streams import GroupType, StepType, TagKey  # noqa: E402
    return GroupType, StepType, TagKey


def nom_enum(cls, v: int) -> str:
    try:
        return cls(v).name
    except ValueError:
        return "<INCONNU:%d>" % v


def scanner_producteur(code: str, dat: str):
    """Rend (sites_groupes, sites_actions, sites_finish, variables) pour un corps."""
    groupes, actions, finish, variables = [], [], [], []
    for _nom, args, _pos in appels(code):
        if len(args) < 3 or args[1] != dat or not RE_IMM.match(args[0] or ""):
            continue
        slot = int(args[0], 0)
        reste = args[3:]
        if slot == SLOT_START_GROUP:
            v = reste[0] if reste else ""
            (groupes if RE_IMM.match(v) else variables).append(
                int(v, 0) if RE_IMM.match(v) else ("StartGroup", v))
        elif slot == SLOT_ACTION:
            v = reste[0] if reste else ""
            (actions if RE_IMM.match(v) else variables).append(
                int(v, 0) if RE_IMM.match(v) else ("Action", v))
        elif slot == SLOT_FINISH_GROUP:
            finish.append(True)
    return groupes, actions, finish, variables


def _sites_add(code: str):
    """Tous les `Dictionary<...>.Add(dict, cle, valeur, <MethodInfo*>)` du corps, avec position.

    L'appel est SOUVENT coupe en deux lignes par Ghidra : on balaye le TEXTE, jamais les lignes.
    """
    for m in RE_DICT_ADD.finditer(code):
        args, _ = _args_equilibres(code, m.end() - 1)
        if len(args) >= 3:
            yield m.start(), args


def dat_dictionnaire_de_tags(codes) -> set:
    """Le(s) `MethodInfo*` de `Dictionary<TagKey,int>.Add`, DERIVE des fabriques de tags.

    Une fabrique `StreamHelper$$Get*Tags` ne construit qu'un dictionnaire de tags : le DAT de son
    `Add` identifie donc l'instanciation gshared voulue. Sans ce filtre, tout `Dictionary.Add` du
    binaire compterait pour un tag -- c'est ce qui rendrait un compte FAUX, pas un zero.
    """
    dats = set()
    for code in codes:
        for _pos, args in _sites_add(code):
            if args[-1].startswith("DAT_"):
                dats.add(args[-1])
    return dats


def scanner_tags(code: str, dats_tag: set) -> set:
    """TagKey ecrits : `var = <imm>;` puis `Dictionary<TagKey,int>.Add(dict, var, valeur, DAT)`."""
    affect = [(m.start(), m.group(1), int(m.group(2), 0)) for m in RE_AFFECT.finditer(code)]
    trouves = set()
    for pos, args in _sites_add(code):
        if dats_tag and args[-1] not in dats_tag:
            continue
        cle = args[1].lstrip("&").split("[")[0].strip()
        val = None
        for p, nom, v in affect:
            if p < pos and nom == cle:
                val = v
        if val is not None:
            trouves.add(val)
    return trouves


def methodes_typees(build: str, enum_natif: str) -> list:
    """Toute methode dont la SIGNATURE declare un parametre du type `enum_natif`.

    Canal 3, et le plus large : le vocabulaire n'est pas seulement pousse par les call-sites du
    flux. Un noeud DSL (`DSLBehaviors$$AtomicGroup(groupType, ...)`) porte un `GroupType` que
    l'ability lui passe en LITTERAL -- invisible de toute lecture des appels a `IStreamListener`.
    Le TYPE DECLARE est LU dans `frida/methods.tsv`, jamais deduit d'un ordinal.
    """
    p = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    out = []
    with p.open(encoding="utf-8", errors="replace") as f:
        f.readline()
        for ligne in f:
            c = ligne.rstrip("\n").split("\t")
            if len(c) < 6 or enum_natif not in c[5]:
                continue
            params = [a.split(":", 1) for a in c[5].split(",") if ":" in a]
            idx = [i for i, (_n, t) in enumerate(params) if t == enum_natif]
            if idx:
                out.append({"rva": c[0], "nom": c[1], "params": [n for n, _t in params],
                            "index": idx})
    return out


def table_ghidra(build: str) -> dict:
    """RVA (hex, sans base) -> symbole Ghidra, depuis la table VERSIONNEE du build."""
    p = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    t = {}
    with p.open(encoding="utf-8", errors="replace") as f:
        for ligne in f:
            c = ligne.rstrip("\n").split("\t")
            if len(c) >= 2:
                try:
                    t["%x" % (int(c[0], 16) - 0x180000000)] = c[1]
                except ValueError:
                    pass
    return t


def parametres(code: str) -> list:
    """Noms des parametres, lus sur la declaration en tete du pseudo-C."""
    i = code.find("{")
    tete = code[:i] if i > 0 else code
    j = tete.find("(")
    if j < 0:
        return []
    args, _ = _args_equilibres(tete, j)
    out = []
    for a in args:
        t = a.replace("*", " ").split()
        out.append(t[-1] if t else "")
    return out


def nom_ghidra_en_c(symbole: str) -> str:
    """`A.B.C$$M` -> `A_B_C__M`, la forme que Ghidra ecrit dans le pseudo-C des appelants."""
    return symbole.replace("$$", "__").replace(".", "_")


def propager_un_cran(gh: Ghidra, variables: list) -> list:
    """Un GroupType/StepType porte par un PARAMETRE se lit chez les APPELANTS -- un cran, pas plus.

    Borne volontaire : au-dela d'un cran, la valeur peut venir d'un champ ecrit ailleurs, et une
    chaine de deductions non lues serait une HYPOTHESE, pas une mesure. Ce qui reste ouvert est
    imprime.
    """
    trouves = []
    for nom, kind, expr in variables:
        code = gh.decompile(nom)
        if code is None:
            continue
        params = parametres(code)
        idx = next((i for i, p in enumerate(params) if p and p in expr), None)
        if idx is None:
            trouves.append((nom, kind, expr, None, []))
            continue
        cible = nom_ghidra_en_c(nom)
        vals, appelants = set(), set()
        for x in gh.xrefs(nom):
            src = x.get("function_name")
            if not src or x.get("type") == "DATA":
                continue
            ccode = gh.decompile(src)
            if ccode is None:
                continue
            for fn, args, _pos in appels(ccode):
                if fn != cible or idx >= len(args):
                    continue
                appelants.add(src)
                if RE_IMM.match(args[idx] or ""):
                    vals.add(int(args[idx], 0))
        trouves.append((nom, kind, expr, idx, sorted(vals), sorted(appelants)))
    return trouves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hors-ligne", action="store_true",
                    help="n'interroge pas ghidra-mcp : n'exploite que le cache logs/")
    ap.add_argument("--json", type=str, default=None, help="ecrit la carte brute (sous logs/)")
    a = ap.parse_args()

    gh = Ghidra(a.hors_ligne)
    GroupType, StepType, TagKey = charger_mirrors()

    print("=" * 78)
    print("#477-r18 -- PERIMETRE DU DEROULE DE BATAILLE (derive du natif)")
    print("=" * 78)

    build_courant = (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    if not a.hors_ligne:
        b = gh.build()
        print("build charge par ghidra-mcp : %s ; data/symbols/CURRENT : %s" % (b, build_courant))
        if b != build_courant:
            print("REFUS : build charge != build des tables versionnees.")
            return 2

    dat, temoins = deriver_dat_interface(gh)
    print("\n[1] INTERFACE EMETTRICE -- derivee, pas ecrite en dur")
    print("    IdunBattle.Streams.IStreamListener -> %s" % dat)
    for n, slots in temoins.items():
        print("    temoin %-64s slots %s" % (n.split("$$")[0].split(".")[-1] + "$$"
                                             + n.split("$$")[1], slots))

    # `list_xrefs` s'interroge par ADRESSE : `DAT_<hex>` est le nom d'affichage d'une donnee sans
    # symbole, il ne resout pas. L'adresse est RE-DERIVEE du nom, jamais recopiee.
    xs = gh.xrefs(dat[len("DAT_"):])
    producteurs = sorted({x["function_name"] for x in xs if x.get("function_name")})
    sans_nom = sum(1 for x in xs if not x.get("function_name"))
    print("\n[2] PRODUCTEURS -- xrefs du Il2CppClass* de l'interface")
    print("    sites : %d   fonctions nommees : %d   sites sans fonction : %d"
          % (len(xs), len(producteurs), sans_nom))

    ev = gh.xrefs("IdunBattle.Core.AOperation$$get_Events")
    canal2 = sorted({x["function_name"] for x in ev
                     if x.get("function_name") and x.get("type") != "DATA"})
    print("    canal 2 INDEPENDANT (AOperation$$get_Events) : %d fonctions" % len(canal2))
    print("    dans get_Events mais PAS dans les xrefs du DAT : %d"
          % len(set(canal2) - set(producteurs)))
    print("    dans les xrefs du DAT mais PAS dans get_Events : %d"
          % len(set(producteurs) - set(canal2)))

    # Fabriques de tags : elles n'appellent pas le flux, mais ce sont elles qui ECRIVENT les
    # TagKey. Elles servent AUSSI a deriver le `MethodInfo*` du `Dictionary<TagKey,int>.Add`.
    fabriques = []
    for prefixe in FABRIQUES_TAGS:
        for s in gh.symboles(re.escape(prefixe)):
            fabriques.append(s["name"])
    fabriques = sorted(set(fabriques))
    codes_fabriques = {n: gh.decompile(n) for n in fabriques}
    dats_tag = dat_dictionnaire_de_tags([c for c in codes_fabriques.values() if c])
    print("\n[2bis] DICTIONNAIRE DE TAGS -- MethodInfo* derive de %d fabrique(s) : %s"
          % (len(fabriques), ", ".join(sorted(dats_tag)) or "AUCUN (le compte de tags sera NUL)"))

    carte = {}
    groupes_vus, actions_vues, tags_vus = {}, {}, {}
    variables = []
    illisibles = []
    for nom in producteurs:
        code = gh.decompile(nom)
        if code is None:
            illisibles.append(nom)
            continue
        g, ac, fi, va = scanner_producteur(code, dat)
        tg = scanner_tags(code, dats_tag)
        carte[nom] = {"groupes": sorted(set(g)), "actions": sorted(set(ac)),
                      "finish": len(fi), "variables": va, "tags": sorted(tg)}
        for v in set(g):
            groupes_vus.setdefault(v, []).append(nom)
        for v in set(ac):
            actions_vues.setdefault(v, []).append(nom)
        for v in tg:
            tags_vus.setdefault(v, []).append(nom)
        for kind, expr in va:
            variables.append((nom, kind, expr))
    for nom, code in codes_fabriques.items():
        if code is None:
            illisibles.append(nom)
            continue
        for v in scanner_tags(code, dats_tag):
            tags_vus.setdefault(v, []).append(nom)

    print("\n[3] VOCABULAIRE VIVANT -- litteraux lus aux call-sites")
    for lib, cls, vus in (("GroupType", GroupType, groupes_vus),
                          ("StepType", StepType, actions_vues),
                          ("TagKey", TagKey, tags_vus)):
        total = len(list(cls))
        connus = {v for v in vus if v in set(int(x) for x in cls)}
        inconnus = sorted(set(vus) - connus)
        print("    %-9s : %3d / %3d atteints par un litteral ; %d hors enum %s"
              % (lib, len(connus), total, len(inconnus), inconnus if inconnus else ""))
        morts = [m for m in cls if int(m) not in vus]
        print("              %d membres SANS aucun litteral trouve (voir ci-dessous)" % len(morts))

    print("\n[4] ARGUMENTS PORTES PAR UNE VARIABLE -- propagation d'UN cran chez les appelants")
    prop = propager_un_cran(gh, variables)
    for t in prop:
        nom, kind, expr = t[0], t[1], t[2]
        idx = t[3]
        if idx is None:
            print("    %-64s %-11s <- %s  [NON PROPAGEABLE : pas un parametre]"
                  % (nom.split("$$")[-1], kind, expr))
            continue
        vals, appelants = t[4], t[5]
        cls = GroupType if kind == "StartGroup" else StepType
        print("    %-64s %-11s param #%d : %d litteral(aux) chez %d appelant(s)"
              % (nom.split("$$")[-1], kind, idx, len(vals), len(appelants)))
        for v in vals:
            print("        %s" % nom_enum(cls, v))
            (groupes_vus if kind == "StartGroup" else actions_vues).setdefault(v, []).append(
                nom + " (via appelants)")

    print("\n[4bis] CANAL 3 -- methodes dont la SIGNATURE porte l'enum (type LU dans methods.tsv)")
    tg = table_ghidra(build_courant)
    porteurs_sans_litteral = []
    for lib, cls, vus, natif in (("GroupType", GroupType, groupes_vus,
                                  "IdunBattle.Streams.GroupType"),
                                 ("StepType", StepType, actions_vues,
                                  "IdunBattle.Streams.StepType")):
        ms = methodes_typees(build_courant, natif)
        avant = len([m for m in cls if int(m) in vus])
        sites, lus = 0, 0
        for m in ms:
            sym = tg.get(m["rva"])
            if not sym:
                porteurs_sans_litteral.append((lib, m["nom"], "SANS SYMBOLE GHIDRA"))
                continue
            cible = nom_ghidra_en_c(sym)
            appelants = [x.get("function_name") for x in gh.xrefs(sym)
                         if x.get("function_name") and x.get("type") != "DATA"]
            if not appelants:
                porteurs_sans_litteral.append((lib, sym, "0 appelant nomme"))
            for src in sorted(set(appelants)):
                code = gh.decompile(src)
                if code is None:
                    continue
                for fn, args, _pos in appels(code):
                    if fn != cible:
                        continue
                    sites += 1
                    # `this` implicite : le call-site porte un argument de plus que la signature.
                    decal = len(args) - len(m["params"])
                    for i in m["index"]:
                        j = i + decal
                        if 0 <= j < len(args) and RE_IMM.match(args[j] or ""):
                            lus += 1
                            vus.setdefault(int(args[j], 0), []).append(sym + " <- " + src)
        apres = len([m2 for m2 in cls if int(m2) in vus])
        print("    %-9s : %d methode(s) porteuse(s), %d site(s) d'appel, %d litteral(aux) lus"
              % (lib, len(ms), sites, lus))
        print("              couverture %d -> %d / %d" % (avant, apres, len(list(cls))))
    for lib, nom, cause in porteurs_sans_litteral[:12]:
        print("      NON LU  %-9s %-58s %s" % (lib, nom, cause))
    if len(porteurs_sans_litteral) > 12:
        print("      ... %d porteur(s) non lu(s) de plus" % (len(porteurs_sans_litteral) - 12))

    print("\n[5] CE QUE CETTE MESURE NE VOIT PAS")
    print("    fonctions productrices NON decompilables : %d" % len(illisibles))
    for n in illisibles[:10]:
        print("      %s" % n)
    print("    fabriques de tags balayees : %d" % len(fabriques))

    print("\n[6] APRES PROPAGATION -- le vocabulaire encore SANS aucun producteur lu")
    for lib, cls, vus in (("GroupType", GroupType, groupes_vus),
                          ("StepType", StepType, actions_vues),
                          ("TagKey", TagKey, tags_vus)):
        morts = [m.name for m in cls if int(m) not in vus]
        print("    %-9s : %3d / %3d atteints ; %d sans producteur lu"
              % (lib, len(cls) - len(morts), len(list(cls)), len(morts)))
        if lib != "TagKey":
            for i in range(0, len(morts), 4):
                print("        " + "  ".join("%-28s" % m for m in morts[i:i + 4]))

    if a.json:
        p = REPO / "logs" / a.json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"dat": dat, "producteurs": carte,
             "groupes_vus": {str(k): v for k, v in groupes_vus.items()},
             "actions_vues": {str(k): v for k, v in actions_vues.items()},
             "tags_vus": {str(k): v for k, v in tags_vus.items()},
             "variables": variables, "illisibles": illisibles,
             "fabriques": fabriques, "canal2": canal2}, indent=1), encoding="utf-8")
        print("\ncarte brute -> %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GhidraDown as exc:
        print("MESURE IMPOSSIBLE : %s" % exc)
        sys.exit(3)
