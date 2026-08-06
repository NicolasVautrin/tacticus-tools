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
     dans les producteurs, dans les fabriques de tags (`StreamHelper$$Get*Tags`,
     `UnitExtensions$$GetFullStateUpdateTags`), ET -- canal 4 -- dans TOUTE fonction qui
     reference le `MethodInfo*` de ce `Add`. Ce dernier canal est le SYMETRIQUE du canal 1 sur
     l'axe des tags : ECRIRE un tag et EMETTRE dans le flux sont deux gestes distincts, et
     `DSLBehaviors$$InformWeapon` ne fait que le premier.
  5. Canal 5 -- les TABLES STATIQUES de cles. Une struct de configuration dont les champs sont
     des `TagKey` a un `.ctor` de VALUE TYPE, donc INLINE, donc SANS appelant : ni le canal 3
     (call-sites) ni le canal 4 (elle n'ecrit pas le dictionnaire) ne peuvent la lire. Ses
     litteraux vivent dans le `.cctor` qui remplit la table, empaquetes DEUX PAR STORE 64 BITS.
  6. Le CROISEMENT avec le port : chaque producteur natif est confronte a `engine/`.

CE QU'IL NE VOIT PAS -- imprime a chaque run, jamais rabattu sur un zero :
  - un GroupType/StepType passe par VARIABLE (compte separement, avec ses porteurs) ;
  - un producteur dont le corps est un generique pleinement partage (present dans Ghidra,
    absent du dump Frida) ;
  - les valeurs poussees par du code que Ghidra n'a pas nomme (`FUN_*`).

Sortie ASCII. Aucun ecrit hors `logs/`.
"""
from __future__ import annotations

import argparse
import hashlib
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
#: Ghidra ecrit un argument entier tantot nu (`0x16`), tantot CASTE (`(void *)0x4e`,
#: `(ulonglong)7`). Mesure : sans le decapsulage, le canal 3 rendait 657 sites d'appel et
#: **0** litteral -- un zero produit par le parseur, pas par le binaire.
RE_CAST = re.compile(r"^\s*(?:\((?:void|u?longlong|u?int\w*|undefined\d*)\s*\**\)\s*)+")
#: `local_28[0] = 0xd5;` -- Ghidra ecrit la cle du tag dans une locale juste avant l'`Add`.
#: TROISIEME forme, trouvee par un flux temoin CRAFTE : quand la variable est plus LARGE que la
#: valeur (typiquement un PARAMETRE reutilise), Ghidra ecrit une affectation de CHAMP --
#: `removeEffects._0_4_ = 7;` dans `IdunBattle.Operations.RepairUnitOperation$$Execute`. Sans le
#: suffixe dans la capture, le nom lu etait `_0_4_` et ne pouvait plus s'apparier a la cle
#: `&removeEffects` de l'`Add` : le tag sortait « sans producteur ».
RE_AFFECT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\._\d+_\d+_)?)(?:\[0\])?"
                       r"\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;")
#: SEUL l'offset 0 designe la meme adresse que `&var` : `cfg._4_4_` est un AUTRE champ de la
#: struct, et le normaliser sur `cfg` ferait ecrire une cle FAUSSE (pire qu'une cle manquante).
RE_CHAMP0 = re.compile(r"\._0_\d+_$")
#: Le dictionnaire de tags est un `Dictionary<TagKey,int>` : son `Add` gshared se reconnait au
#: `MethodInfo*` passe en DERNIER argument. Ce DAT est DERIVE d'une fabrique temoin, pas ecrit.
RE_DICT_ADD = re.compile(r"Dictionary[A-Za-z0-9_]*u003E__(?:Add|set_Item)\s*\(")
#: Le NOM d'une locale Ghidra PORTE son offset de pile (`local_2e8`, `uStack_2e0`, `lStack_210`).
#: C'est ce qui rend lisible une struct ecrite champ par champ : ses slots sont contigus, de 8 en 8.
RE_SLOT = re.compile(r"^(?:local|[A-Za-z]*Stack)_([0-9a-f]+)$")
#: `uStack_2d0 = CONCAT44(uStack_2fc,0x29);` -- Ghidra fusionne deux dwords dont UN SEUL est un
#: immediat. Sans cette forme, le dword litteral du couple est perdu (mesure : 1 cle sur 62).
RE_CONCAT44 = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*CONCAT44\s*\(([^,()]+),([^,()]+)\)\s*;")
#: Les trois formes de ligne du flux, pour la contre-epreuve (le paquet `engine.streams` porte
#: les memes : on ne les importe pas, ce probe doit rester lisible SANS lui).
RE_L_GROUP = re.compile(r"^ *Group=([^ ]*) ")
RE_L_ACTION = re.compile(r"^ *Action=([^ ]*) ")
RE_L_TAG = re.compile(r"^ *Tag=([^:]*):")


def immediat(expr: str):
    """La valeur entiere d'un argument, casts Ghidra retires -- ou `None` si ce n'en est pas un."""
    if not expr:
        return None
    e = RE_CAST.sub("", expr).strip()
    while e.startswith("(") and e.endswith(")"):
        e = e[1:-1].strip()
    return int(e, 0) if RE_IMM.match(e) else None


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


def _ecrire_atomique(f: Path, texte: str) -> None:
    """Ecrit le cache par fichier TEMPORAIRE + `replace`, jamais en place.

    Le cache est partage entre runs -- et `ghidra-mcp` l'est entre agents. Une ecriture en place
    laisse une fenetre ou un autre lecteur voit un corps TRONQUE : il le prendrait pour un corps
    valide et rendrait un compte trop bas, c'est-a-dire un zero produit par la concurrence et non
    par le binaire. `os.replace` est atomique sur NTFS.
    """
    tmp = f.with_suffix(f.suffix + ".%d.part" % os.getpid())
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, f)


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
        _ecrire_atomique(f, json.dumps(xs))
        return xs

    def decompile(self, nom: str, timeout_sec: int = 60) -> str | None:
        f = CACHE / ("fn_%s%s.c" % (re.sub(r"[^A-Za-z0-9_]", "_", nom),
                                    "" if timeout_sec == 60 else "__t%d" % timeout_sec))
        if f.exists():
            t = f.read_text(encoding="utf-8", errors="replace")
            return None if t == "\0ABSENT" else t
        if self.hors_ligne:
            return None
        try:
            res = self._client().call("decompile_function",
                                      {"binary_name": BINARY, "name_or_address": nom,
                                       "timeout_sec": timeout_sec})
        except (GhidraDown, RuntimeError):
            return None
        if isinstance(res, dict) and isinstance(res.get("result"), list):
            rs = res["result"]
            code = (rs[0].get("code") if rs else None) or ""
        else:
            code = (res or {}).get("code") or ""
        _ecrire_atomique(f, code if code else "\0ABSENT")
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
        _ecrire_atomique(f, json.dumps(out))
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
            slot = immediat(args[0]) if len(args) >= 3 else None
            if slot is not None and (args[1] or "").startswith("DAT_"):
                cand.setdefault(args[1], set()).add(slot)
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
    from engine.streams.group_type import GroupType
    from engine.streams.step_type import StepType
    from engine.streams.tag_key import TagKey  # noqa: E402
    return GroupType, StepType, TagKey


def nom_enum(cls, v: int) -> str:
    try:
        return cls(v).name
    except ValueError:
        return "<INCONNU:%d>" % v


def _sites_indirects(code: str, dat: str):
    """DEUXIEME forme d'appel d'interface : la resolution est SORTIE de l'appel.

        puVar6 = FUN_1801e7040(this, <DAT interface>, <slot>);
        (*(code *)*puVar6)(this, 0x37, entity, tags, ...);

    Ghidra emet cette forme quand il a inline la recherche de slot. Mesure : sans elle,
    `AddOrUpdateShield` et `RemoveShield` -- tous deux OBSERVES dans le flux live -- sortaient
    « sans producteur lu ». Rend (slot, [args de l'appel indirect]).
    """
    for m in re.finditer(r"=\s*\(?[^;\n=]*?\)?\s*(?:\(undefined8 \*\))?\s*"
                         r"\w+\s*\(\s*[^,()]+,\s*" + re.escape(dat) + r"\s*,\s*(\d+)\s*\)", code):
        slot = int(m.group(1), 0)
        j = code.find("(*(code *)*", m.end())
        if j < 0 or j - m.end() > 400:
            continue
        k = code.find(")(", j)
        if k < 0:
            continue
        args, _ = _args_equilibres(code, k + 1)
        yield slot, args


def scanner_producteur(code: str, dat: str):
    """Rend (sites_groupes, sites_actions, sites_finish, variables) pour un corps."""
    groupes, actions, finish, variables = [], [], [], []
    for slot, args in _sites_indirects(code, dat):
        # L'appel indirect porte `this` en tete, puis les arguments de la methode.
        brut = args[1] if len(args) >= 2 else ""
        if slot == SLOT_FINISH_GROUP:
            finish.append(True)
            continue
        if slot not in (SLOT_START_GROUP, SLOT_ACTION):
            continue
        v = immediat(brut)
        if v is None:
            variables.append(("StartGroup" if slot == SLOT_START_GROUP else "Action", brut))
        else:
            (groupes if slot == SLOT_START_GROUP else actions).append(v)
    for _nom, args, _pos in appels(code):
        slot = immediat(args[0]) if len(args) >= 3 else None
        if slot is None or args[1] != dat:
            continue
        reste = args[3:]
        if slot in (SLOT_START_GROUP, SLOT_ACTION):
            brut = reste[0] if reste else ""
            v = immediat(brut)
            cible = groupes if slot == SLOT_START_GROUP else actions
            if v is None:
                variables.append(("StartGroup" if slot == SLOT_START_GROUP else "Action", brut))
            else:
                cible.append(v)
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


def racine_variable(expr: str) -> str:
    """Le NOM de la variable derriere `&x`, `x[0]` ou `x._0_4_` -- les trois formes de Ghidra.

    Normalise les DEUX cotes de l'appariement (l'affectation et l'argument CLE de l'`Add`), sans
    quoi une meme variable porte deux noms differents selon le site et le tag est perdu.
    """
    e = expr.strip().lstrip("&").split("[")[0].strip()
    return RE_CHAMP0.sub("", e)


def scanner_tags(code: str, dats_tag: set) -> set:
    """TagKey ecrits : `var = <imm>;` puis `Dictionary<TagKey,int>.Add(dict, var, valeur, DAT)`."""
    affect = [(m.start(), racine_variable(m.group(1)), int(m.group(2), 0))
              for m in RE_AFFECT.finditer(code)]
    trouves = set()
    for pos, args in _sites_add(code):
        if dats_tag and args[-1] not in dats_tag:
            continue
        cle = racine_variable(args[1])
        val = None
        for p, nom, v in affect:
            if p < pos and nom == cle:
                val = v
        if val is not None:
            trouves.add(val)
    return trouves


def ecrivains_de_tags(gh: Ghidra, dats_tag: set) -> list:
    """CANAL 4 -- les xrefs du `MethodInfo*` de `Dictionary<TagKey,int>.Add`.

    STRICTEMENT SYMETRIQUE du canal 1 : celui-la rend qui EMET dans le flux, celui-ci rend qui
    ECRIT un tag. Les deux ensembles ne se recouvrent PAS, et c'est tout l'interet --
    `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon` ecrit trois `TagKey`
    (`Attack_Weapon_DamageProfile`, `_IsMelee`, `_Use_Special`) et n'appelle jamais
    `IStreamListener` : c'est un noeud DSL, son dictionnaire part vers
    `IdunBattle.Operations.InformOperation$$Execute`. Sans ce canal, ces tags sortaient
    « sans producteur » alors que le flux live les emet.
    """
    out = set()
    for d in sorted(dats_tag):
        for x in gh.xrefs(d[len("DAT_"):]):
            if x.get("function_name"):
                out.add(x["function_name"])
    return sorted(out)


def litteraux_table_statique(code: str, n_cles: int):
    """CANAL 5 -- les cles d'une TABLE STATIQUE de configuration, lues slot par slot.

    Une struct de configuration (`TransformUnitOperation.ModStatTransformConfig`) porte ses
    `TagKey` en CHAMPS. Son `.ctor` est un ctor de VALUE TYPE : le compilateur l'INLINE, donc il
    n'a AUCUN appelant nomme et le canal 3 ne peut rien y lire. Les litteraux vivent alors dans
    le `.cctor` qui remplit la table, ecrits en stores 64 bits qui EMPAQUETTENT DEUX champs
    (`local_198 = 0x2b0000002a` = champ0 `UnitStats_FixedArmor`, champ1 `..._Modification`).

    Ce qui rend la lecture EXACTE plutot qu'heuristique : la struct est passee par ADRESSE au
    `Dictionary.Add` de la table (3e argument), et le NOM Ghidra de cette locale porte son offset
    de pile -- les `n_cles * 4` octets de cles occupent donc les `ceil(n_cles/2)` slots suivants,
    de 8 en 8. On ne lit que ceux-la : la variable passee en CLE de la table (un `StatType`, pas
    un `TagKey`) est HORS de cette plage, donc jamais confondue.

    Le `0` est EXCLU : c'est le sentinelle « non implemente », et
    `IdunBattle.Operations.TransformUnitOperation$$AddTagIfImplemented` commence par
    `if (key != 0)` -- un champ nul n'ecrit aucun tag.
    """
    n_slots = (n_cles * 4 + 7) // 8
    par_offset = {}

    def _noter(nom, pos, val):
        s = RE_SLOT.match(nom)
        if s:
            par_offset.setdefault(int(s.group(1), 16), []).append((pos, val))

    for m in RE_AFFECT.finditer(code):
        _noter(m.group(1), m.start(), int(m.group(2), 0))
    for m in RE_CONCAT44.finditer(code):
        haut, bas = immediat(m.group(2)), immediat(m.group(3))
        if haut is None and bas is None:
            continue
        _noter(m.group(1), m.start(), ((haut or 0) << 32) | (bas or 0))
    valeurs, sites = set(), 0
    for pos, args in _sites_add(code):
        if len(args) < 3:
            continue
        s = RE_SLOT.match(args[2].lstrip("&").strip())
        if not s:
            continue
        sites += 1
        base = int(s.group(1), 16)
        for i in range(n_slots):
            avant = [(p, v) for p, v in par_offset.get(base - 8 * i, ()) if p < pos]
            if not avant:
                continue
            v = max(avant)[1]
            valeurs |= {v & 0xFFFFFFFF, (v >> 32) & 0xFFFFFFFF}
    return {v for v in valeurs if v}, sites


def tables_statiques_de_cles(gh: Ghidra, build: str, tg: dict, par_symbole: dict) -> list:
    """Les porteurs de cles INLINES, et le `.cctor` ou leurs litteraux se trouvent reellement.

    Rend une liste de (symbole du ctor, symbole du cctor lu, n_cles, valeurs, sites). Un porteur
    qui a des appelants nommes n'entre PAS ici : c'est le canal 3 qui le lit.
    """
    out = []
    for m in methodes_typees(build, "IdunBattle.Streams.TagKey"):
        if len(m["index"]) < 2:
            continue
        sym = tg.get(m["rva"])
        if not sym:
            out.append((m["nom"], None, len(m["index"]), set(), "SANS SYMBOLE GHIDRA"))
            continue
        va = "%x" % (int(m["rva"], 16) + 0x180000000)
        if [x for x in gh.xrefs(va) if x.get("function_name") and x.get("type") != "DATA"]:
            continue  # appelable : le canal 3 le lit
        if sorted(m["index"]) != list(range(len(m["index"]))):
            out.append((sym, None, len(m["index"]), set(),
                        "cles NON contigues en tete de la struct"))
            continue
        classe = sym.split("$$")[0]
        cands = [c + "$$.cctor" for c in (classe, classe.rsplit(".", 1)[0]) if "." in c]
        cctor = next((c for c in cands if c in par_symbole), None)
        if cctor is None:
            out.append((sym, None, len(m["index"]), set(), "aucun .cctor pour %s" % classe))
            continue
        code, _n = decompile_robuste(gh, cctor, par_symbole)
        if code is None:
            out.append((sym, cctor, len(m["index"]), set(), "cctor NON decompilable"))
            continue
        vals, sites = litteraux_table_statique(code, len(m["index"]))
        out.append((sym, cctor, len(m["index"]), vals, "%d entree(s) de table" % sites))
    return out


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


def adresses_par_symbole(build: str) -> dict:
    """symbole -> [adresses]. Un symbole IL2CPP peut couvrir N SURCHARGES.

    Mesure : `IdunBattle.Messages.InputMessageProcessor$$Visit` en a **37**. `decompile_function`
    et `list_xrefs` rendent une ERREUR sur un nom ambigu -- soit, en sortie, un corps vide et
    « 0 appelant ». Sans cette table, les 12 sites du plus gros producteur du binaire sortaient en
    « non decompilable », ce qui se lit comme une absence.
    """
    p = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    t = {}
    with p.open(encoding="utf-8", errors="replace") as f:
        for ligne in f:
            c = ligne.rstrip("\n").split("\t")
            if len(c) >= 2:
                t.setdefault(c[1], []).append(c[0].lower().lstrip("0x"))
    return t


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


def decompile_robuste(gh: Ghidra, nom: str, par_symbole: dict) -> tuple:
    """1) par nom ; 2) budget LARGE (corps enorme) ; 3) par ADRESSE, une par SURCHARGE.

    Le 3e cran n'est pas un luxe : un nom porte par plusieurs surcharges fait rendre a
    `decompile_function` un corps VIDE, sans erreur. Mesure : `UnitExtensions$$GetFullStateUpdateTags`
    en a 3, et son absence retirait **23** `TagKey` pourtant EMIS par le flux live.
    """
    code = gh.decompile(nom) or gh.decompile(nom, timeout_sec=300)
    if code is not None:
        return code, 0
    morceaux = [c for c in (gh.decompile(va, timeout_sec=180)
                            for va in par_symbole.get(nom, ())) if c]
    return ("\n".join(morceaux) if morceaux else None), len(morceaux)


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
                v = immediat(args[idx])
                if v is not None:
                    vals.add(v)
        trouves.append((nom, kind, expr, idx, sorted(vals), sorted(appelants)))
    return trouves


def contre_epreuve_live(GroupType, StepType, TagKey, groupes, actions, tags) -> None:
    """LE controle du balayage statique : tout ce que le flux EMET doit y avoir ete atteint.

    Sans lui, le statique se juge lui-meme. Mesure : il a trouve DEUX trous reels --
    `AddOrUpdateShield` / `RemoveShield` (deuxieme forme d'appel d'interface) et 23 `TagKey`
    (surcharges non decompilees). Un ecart NON NUL nomme la lacune ; il ne la cache pas.
    """
    flux = sorted((REPO / "logs").glob("477r18-flux-*.txt"))
    print("\n[8] CONTRE-EPREUVE -- ce que le flux LIVE emet, le statique l'a-t-il atteint ?")
    if not flux:
        print("    PAS MESURE : aucun flux sous logs/477r18-flux-*.txt "
              "(lancer --flux-live d'abord). Ce n'est PAS un zero.")
        return
    obs = {"GroupType": set(), "StepType": set(), "TagKey": set()}
    for f in flux:
        for ligne in f.read_text(encoding="utf-8").split("\n"):
            for cle, rx in (("GroupType", RE_L_GROUP), ("StepType", RE_L_ACTION),
                            ("TagKey", RE_L_TAG)):
                m = rx.match(ligne)
                if m:
                    obs[cle].add(m.group(1))
                    break
    print("    corpus : %s" % ", ".join(f.name for f in flux))
    for lib, cls, vus in (("GroupType", GroupType, groupes), ("StepType", StepType, actions),
                          ("TagKey", TagKey, tags)):
        ordinaux = {int(x) for x in cls}
        atteints = {cls(v).name for v in vus if v in ordinaux}
        manquants = sorted(obs[lib] - atteints)
        print("    %-9s emis %3d ; atteint %3d ; EMIS MAIS NON ATTEINT %d %s"
              % (lib, len(obs[lib]), len(atteints), len(manquants),
                 ": " + ", ".join(manquants) if manquants else ""))


def volet_flux_live(board: str, tours: int, p_units=None, a_units=None) -> int:
    """Ce que le natif EMET REELLEMENT, ventile par GROUPE RACINE.

    Le canal statique dit ce qui est EMISSIBLE ; il ne dit pas ce qu'une bataille produit. Un
    inventaire qui hierarchiserait les tranches sans ce poids classerait par nombre de membres
    d'enum -- c'est-a-dire par le vocabulaire des abilities, alors que le squelette du tour tient
    en quelques groupes. Monte UN runner, joue `tours` tours d'IA, dispose dans le `finally`.
    """
    import subprocess
    import urllib.request

    sys.path.insert(0, str(REPO / "scripts" / "python"))
    from engine.streams import conformance as CONF  # noqa: E402

    hote = "http://127.0.0.1:8765"
    with urllib.request.urlopen("%s/api/admin/status" % hote, timeout=10) as r:
        session = int((json.loads(r.read().decode())["session"])["id"])
    etat = REPO / "logs" / "477r18-flux-live.json"
    etat.parent.mkdir(parents=True, exist_ok=True)
    ici = REPO / "scripts" / "python"

    def rl(*args, t=900):
        return subprocess.run([sys.executable, "rl_duel.py", *args, "--state-file", str(etat)],
                              cwd=str(ici), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=t)

    # Le ROSTER se pilote : le corpus temoin de l'etape [8] ne vaut que ce que la bataille
    # EXERCE, et deux equipes tirees par defaut ne castent qu'une poignee d'abilities. Un
    # roster choisi (boucliers, invocations, transformations) est ce qui fait apparaitre des
    # `TagKey` qu'aucun board ne ferait sortir tout seul.
    roster = []
    if p_units:
        roster += ["--p-units", p_units]
    if a_units:
        roster += ["--a-units", a_units]
    try:
        p = rl("build", "--seed", "777", "--board", board, "--record-replay", "--no-ai", *roster)
        if not etat.is_file():
            print("MESURE IMPOSSIBLE (build) : %s" % (p.stderr or p.stdout)[-400:])
            return 3
        print("    runner %s monte sur %s%s"
              % (json.loads(etat.read_text())["runnerId"], board,
                 (" ; roster " + " ".join(roster)) if roster else ""))
        for i in range(tours):
            q = rl("aiturn", t=600)
            if q.returncode != 0:
                print("    tour %d : aiturn rc=%d -- ARRET (%s)"
                      % (i + 1, q.returncode, (q.stderr or "")[-160:]))
                break
        body = json.dumps({"method": "replayOutputStream",
                           "args": [{"runnerId": json.loads(etat.read_text())["runnerId"],
                                     "maxChars": 8000000}],
                           "timeout": 60000}).encode()
        req = urllib.request.Request("%s/api/scripts/%d/rpc" % (hote, session), data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            flux = ((json.loads(r.read().decode()).get("result") or {}).get("outputStream") or "")
    finally:
        rl("dispose", t=180)

    if not flux:
        print("    MESURE IMPOSSIBLE : `replayOutputStream` rend un flux VIDE")
        return 3
    lignes = flux.split("\n")
    # Le nom du fichier porte le roster : deux flux du MEME board avec des equipes differentes
    # sont deux TEMOINS, pas un ecrasement. L'empreinte est un sha STABLE, jamais `hash()` --
    # qui est randomise par processus et rendrait le nom du temoin non reproductible.
    empreinte = hashlib.sha1(" ".join(roster).encode()).hexdigest()[:6] if roster else ""
    brut = REPO / "logs" / ("477r18-flux-%s%s.txt"
                            % (board, ("-" + empreinte) if empreinte else ""))
    brut.write_text(flux, encoding="utf-8")
    print("    flux natif : %d lignes, %d octets -> %s" % (len(lignes), len(flux), brut))

    racines, pile, courant, debut = [], 0, None, 0
    for i, s in enumerate(lignes):
        m = CONF.RE_GROUP.match(s)
        if m:
            if pile == 0:
                courant, debut = m.group("sym"), i
            pile += 1
        elif CONF.RE_FINISH.match(s):
            pile -= 1
            if pile == 0 and courant is not None:
                racines.append((courant, i - debut + 1, lignes[debut:i + 1]))
                courant = None

    hors = len(lignes) - sum(n for _s, n, _l in racines)
    agg = {}
    for sym, n, corps in racines:
        e = agg.setdefault(sym, {"n": 0, "lignes": 0, "groupes": set(), "actions": set(),
                                 "tags": set()})
        e["n"] += 1
        e["lignes"] += n
        for s in corps:
            mg, ma, mt = (CONF.RE_GROUP.match(s), CONF.RE_ACTION.match(s), CONF.RE_TAG.match(s))
            if mg:
                e["groupes"].add(mg.group("sym"))
            elif ma:
                e["actions"].add(ma.group("sym"))
            elif mt:
                e["tags"].add(mt.group("sym"))
    # « NOUVEAU » = ce que le groupe ajoute au vocabulaire DEJA exerce par le deploiement. C'est
    # ce chiffre-la qui hierarchise les tranches : le nombre de lignes seul classerait en tete un
    # groupe entierement compose de motifs deja portes.
    base = agg.get("System_GameSetup") or {"groupes": set(), "actions": set(), "tags": set()}
    print("    %-26s %4s %7s  %-13s %s"
          % ("GROUPE RACINE", "occ", "lignes", "vocab G/S/T", "NOUVEAU vs deploiement"))
    for sym, e in sorted(agg.items(), key=lambda kv: -kv[1]["lignes"]):
        print("    %-26s %4d %7d  %-13s +%d / +%d / +%d"
              % (sym, e["n"], e["lignes"],
                 "%d / %d / %d" % (len(e["groupes"]), len(e["actions"]), len(e["tags"])),
                 len(e["groupes"] - base["groupes"]), len(e["actions"] - base["actions"]),
                 len(e["tags"] - base["tags"])))
    print("    lignes HORS de tout groupe racine (Action= a profondeur 0) : %d" % hors)
    print("    sequence des groupes racines : %d, dont %d distincts"
          % (len(racines), len(agg)))
    return 0


def croiser_avec_le_port(producteurs: list) -> None:
    """Chaque producteur natif est-il CITE dans `engine/` ? -- le classement demande.

    Un symbole cite verbatim dans le port veut dire que la mecanique est mirroree ; une classe
    citee sans la methode veut dire que la classe est portee mais pas ce point d'emission. Ce
    n'est PAS une preuve de fidelite -- c'est ce qui distingue « quelques heures » d'un chantier.
    """
    racine = REPO / "scripts" / "python" / "engine"
    pat = re.compile(r"\b(IdunBattle[A-Za-z.]*\.[A-Za-z0-9_]+)\$\$([A-Za-z0-9_|]+)")
    cites, classes = {}, {}
    for p in racine.rglob("*.py"):
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(t):
            plein = m.group(1) + "$$" + m.group(2)
            cites.setdefault(plein, set()).add(p.name)
            classes.setdefault(m.group(1).rsplit(".", 1)[-1], set()).add(p.name)
    exact = [p for p in producteurs if p in cites]
    par_classe = [p for p in producteurs if p not in cites
                  and p.split("$$")[0].rsplit(".", 1)[-1] in classes]
    absents = [p for p in producteurs if p not in cites
               and p.split("$$")[0].rsplit(".", 1)[-1] not in classes]
    print("\n[7] CROISEMENT AVEC LE PORT -- %d producteur(s) natif(s)" % len(producteurs))
    print("    symbole EXACT cite dans engine/ : %d" % len(exact))
    print("    CLASSE citee, autre methode     : %d" % len(par_classe))
    print("    AUCUNE trace dans engine/       : %d" % len(absents))
    familles = {}
    for p in absents:
        familles.setdefault(p.split("$$")[0].rsplit(".", 1)[0], []).append(p)
    for fam, lst in sorted(familles.items(), key=lambda kv: -len(kv[1])):
        print("      %-56s %d" % (fam, len(lst)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hors-ligne", action="store_true",
                    help="n'interroge pas ghidra-mcp : n'exploite que le cache logs/")
    ap.add_argument("--json", type=str, default=None, help="ecrit la carte brute (sous logs/)")
    ap.add_argument("--flux-live", action="store_true",
                    help="volet LIVE : ventile un vrai flux natif par groupe racine")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default=None,
                    help="volet LIVE : roster JOUEUR passe tel quel a `rl_duel build`")
    ap.add_argument("--a-units", default=None,
                    help="volet LIVE : roster ADVERSE passe tel quel a `rl_duel build`")
    a = ap.parse_args()

    if a.flux_live:
        print("=" * 78)
        print("#477-r18 -- POIDS MESURE de chaque GROUPE RACINE dans un flux natif")
        print("=" * 78)
        return volet_flux_live(a.board, a.tours, a.p_units, a.a_units)

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
    par_symbole = adresses_par_symbole(build_courant)
    codes_fabriques = {n: decompile_robuste(gh, n, par_symbole)[0] for n in fabriques}
    dats_tag = dat_dictionnaire_de_tags([c for c in codes_fabriques.values() if c])
    print("\n[2bis] DICTIONNAIRE DE TAGS -- MethodInfo* derive de %d fabrique(s) : %s"
          % (len(fabriques), ", ".join(sorted(dats_tag)) or "AUCUN (le compte de tags sera NUL)"))

    carte = {}
    groupes_vus, actions_vues, tags_vus = {}, {}, {}
    variables = []
    illisibles = []
    surcharges = 0
    for nom in producteurs:
        code, n_surch = decompile_robuste(gh, nom, par_symbole)
        surcharges += n_surch
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

    # CANAL 4 -- symetrique du canal 1, sur l'axe des TAGS. Un ecrivain de tags n'est pas force
    # d'emettre : le noeud DSL construit le dictionnaire, l'Operation l'envoie.
    print("\n[3bis] CANAL 4 -- xrefs du MethodInfo* de Dictionary<TagKey,int>.Add")
    ecrivains = ecrivains_de_tags(gh, dats_tag)
    deja = set(producteurs) | set(fabriques)
    avant_c4 = {v for v in tags_vus}
    neufs, illisibles_c4 = 0, []
    for nom in ecrivains:
        if nom in deja:
            continue
        neufs += 1
        code, _n = decompile_robuste(gh, nom, par_symbole)
        if code is None:
            illisibles_c4.append(nom)
            continue
        for v in scanner_tags(code, dats_tag):
            tags_vus.setdefault(v, []).append(nom)
    apres_c4 = {v for v in tags_vus}
    exclusifs = sorted(apres_c4 - avant_c4)
    print("    ecrivains de tags : %d ; deja balayes par le canal 1 / les fabriques : %d ; "
          "neufs : %d ; non decompilables : %d"
          % (len(ecrivains), len(ecrivains) - neufs, neufs, len(illisibles_c4)))
    print("    TagKey atteints UNIQUEMENT par ce canal : %d" % len(exclusifs))
    for v in exclusifs:
        print("      %-44s <- %s" % (nom_enum(TagKey, v), ", ".join(sorted(set(tags_vus[v])))))
    for n in illisibles_c4[:6]:
        print("      NON DECOMPILABLE %s" % n)

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
    # ⚠ Le vocabulaire des TAGS est aussi LU par la VUE (`IdunBattle.View.*`, `idun.Game.Board.*`,
    # `IdunBattle.ViewLogic.*`) : sur les porteurs de `TagKey`, un canal 3 non filtre compterait
    # des CONSOMMATEURS comme des producteurs. Le filtre est DERIVE, pas ecrit : un porteur ne
    # compte que s'il EMET dans le flux (canal 1) ou s'il ECRIT un tag (canal 4). Ce qu'il ecarte
    # est IMPRIME. `GroupType` / `StepType` n'ont pas ce double usage : aucun filtre.
    emetteurs = set(producteurs) | set(fabriques) | set(ecrivains)
    for lib, cls, vus, natif, filtre in (
            ("GroupType", GroupType, groupes_vus, "IdunBattle.Streams.GroupType", None),
            ("StepType", StepType, actions_vues, "IdunBattle.Streams.StepType", None),
            ("TagKey", TagKey, tags_vus, "IdunBattle.Streams.TagKey", emetteurs)):
        ms = methodes_typees(build_courant, natif)
        avant = len([m for m in cls if int(m) in vus])
        sites, lus, ecartes = 0, 0, set()
        for m in ms:
            sym = tg.get(m["rva"])
            if not sym:
                porteurs_sans_litteral.append((lib, m["nom"], "SANS SYMBOLE GHIDRA"))
                continue
            if filtre is not None and sym not in filtre:
                ecartes.add(sym)
                continue
            cible = nom_ghidra_en_c(sym)
            # Par ADRESSE, jamais par nom : `DSLBehaviors$$AtomicGroup` a TROIS surcharges
            # homonymes, et `list_xrefs` sur un nom ambigu rend une erreur -- soit, en sortie,
            # « 0 appelant » : un zero qui ne mesure rien. L'adresse, elle, est unique.
            va = "%x" % (int(m["rva"], 16) + 0x180000000)
            appelants = [x.get("function_name") for x in gh.xrefs(va)
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
                        v = immediat(args[j]) if 0 <= j < len(args) else None
                        if v is not None:
                            lus += 1
                            vus.setdefault(v, []).append(sym + " <- " + src)
        apres = len([m2 for m2 in cls if int(m2) in vus])
        print("    %-9s : %d methode(s) porteuse(s), %d site(s) d'appel, %d litteral(aux) lus"
              % (lib, len(ms), sites, lus))
        print("              couverture %d -> %d / %d" % (avant, apres, len(list(cls))))
        if filtre is not None:
            # Le filtre ne peut que SOUS-compter, jamais sur-compter -- et ce qu'il ecarte est
            # NOMME : c'est la seule facon de voir un jour qu'il ecarte a tort.
            print("              ECARTES PAR CE FILTRE : %d symbole(s) qui n'emettent ni "
                  "n'ecrivent" % len(ecartes))
            for s in sorted(ecartes):
                print("                %s" % s)
    for lib, nom, cause in porteurs_sans_litteral[:12]:
        print("      NON LU  %-9s %-58s %s" % (lib, nom, cause))
    if len(porteurs_sans_litteral) > 12:
        print("      ... %d porteur(s) non lu(s) de plus" % (len(porteurs_sans_litteral) - 12))

    print("\n[4ter] CANAL 5 -- TABLES STATIQUES de cles (porteurs INLINES, sans appelant)")
    hors_enum_c5, avant_c5 = [], len([m for m in TagKey if int(m) in tags_vus])
    for sym, cctor, n_cles, vals, cause in tables_statiques_de_cles(gh, build_courant, tg,
                                                                   par_symbole):
        connues = {v for v in vals if v in {int(x) for x in TagKey}}
        hors_enum_c5 += sorted(vals - connues)
        for v in connues:
            tags_vus.setdefault(v, []).append(cctor or sym)
        bouts = sym.split("$$")
        court = (bouts[0].rsplit(".", 1)[-1] + "$$" + bouts[1]) if len(bouts) > 1 else sym
        print("    %-62s %d cles" % (court, n_cles))
        print("      table lue dans %-52s %s ; %d valeur(s), %d dans TagKey"
              % (cctor or "<AUCUNE>", cause, len(vals), len(connues)))
    print("    couverture TagKey %d -> %d / %d"
          % (avant_c5, len([m for m in TagKey if int(m) in tags_vus]), len(list(TagKey))))
    # Un parseur qui derape produit des entiers ARBITRAIRES : le controle est qu'ils tombent TOUS
    # dans l'enum. Un non-vide ici accuse la lecture, pas le binaire.
    print("    valeurs lues HORS de l'enum TagKey (doit etre VIDE) : %s"
          % (sorted(set(hors_enum_c5)) if hors_enum_c5 else "aucune"))

    print("\n[5] CE QUE CETTE MESURE NE VOIT PAS")
    print("    corps lus PAR ADRESSE faute d'un nom unique (surcharges) : %d" % surcharges)
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

    croiser_avec_le_port(producteurs)
    contre_epreuve_live(GroupType, StepType, TagKey, groupes_vus, actions_vues, tags_vus)

    if a.json:
        p = REPO / "logs" / a.json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"dat": dat, "producteurs": carte,
             "groupes_vus": {str(k): v for k, v in groupes_vus.items()},
             "actions_vues": {str(k): v for k, v in actions_vues.items()},
             "tags_vus": {str(k): v for k, v in tags_vus.items()},
             "variables": variables, "illisibles": illisibles,
             "fabriques": fabriques, "canal2": canal2,
             "ecrivains_de_tags": ecrivains}, indent=1), encoding="utf-8")
        print("\ncarte brute -> %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GhidraDown as exc:
        print("MESURE IMPOSSIBLE : %s" % exc)
        sys.exit(3)
