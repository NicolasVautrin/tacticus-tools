#!/usr/bin/env python3
"""probe #302 tranche 4 -- POPULATION COMPLETE des abilities a cible TUILE (bit `TargetIsTile`).

QUESTION BINAIRE
    Sur la TOTALITE des `ActiveAbilityType` enregistrees par le jeu -- pas seulement les 9x deja
    portees dans `ABILITY_CLASSES` -- lesquelles portent le bit 6 `TargetingRule.TargetIsTile` de
    leurs `TargetingOptions.Rules`, et pour chacune la face DECISION a-t-elle une route ?

    `probe_302_tile_target_route.py --inventory` ne lisait le bit QUE sur le registre du port. La
    population reelle n'etait donc pas connue. Cette tranche la mesure au DECOMPILE, ability par
    ability, et rend un compte VENTILE avec un axe explicite « NON MESURABLE ».

CHAINE NATIVE LUE (build courant ; `decompile = verite`)

  1. Le REGISTRE des abilities actives
     `IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities` remplit un
     `Dictionary<ActiveAbilityType, Func<AActiveAbility>>`. Chaque entree est
     `dict.Add(<id>, <>9__27_N ??= new Func(<>9, b__27_N))`, et
     `...AbilitiesDatabase.u003Cu003Ec$$u003CInitializeActiveAbilitiesu003Eb__27_N` fait
     exactement `new <X>Ability()`. Le champ de cache `<>9__27_N` vit dans les statics de
     `<>c` a l'offset `8 + 8*N` (le slot 0 est le singleton `<>9`) -- relation VERIFIEE, pas
     supposee : le report la re-derive et REFUSE de conclure si elle ne tient pas (voir
     `_calibrate`).

  2. Le MASQUE effectif d'une ability
     `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, targetingOptions, attackType)`
     copie la struct recue dans `this+0x70..0xaf` ; c'est CE champ que
     `IdunBattle.Entities.Abilities.AActiveAbility$$GetValidTargets` relit (mesure : le decompile
     de `GetValidTargets` ne touche que `this+0x70`). Le second jeu, `this+0xb0`, est
     `TargetingOptionsForContinue` et ne decide PAS du domaine.
     Les `Rules` sont a `TargetingOptions+0x28` (64 bits) ; `TargetIsTile` = bit 6, exactement ce
     que rend `IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting`
     (`*(byte*)(this+0x28) >> 6 & 1`).

  3. Les TROIS overloads du ctor de `TargetingOptions`, tous les trois mesures dans ce build --
     c'est le premier piege, et il est PAYE dans ce depot :
       (a) `.ctor(this, isSelfCasting, range, forceMeleeTarget, RULES, dynCaster, dynTarget)`
           -> `RULES` litteral, 5e argument.
       (b) `.ctor(this, template, additionalRules)`
           -> `rules = template.rules | additionalRules`. Le litteral VISIBLE (`additionalRules`)
              n'est PAS le masque : ex. `...Loki.TheQuickeningAbility$$.ctor` combine le preset
              `TargetingOptions_statics+0x200` avec `0x806000000`.
       (c) `.ctor(this, template)` -> copie pure du preset.
     Et une QUATRIEME forme, sans aucun appel : le ctor RECOPIE les 0x40 octets d'un champ
     statique de `TargetingOptions` et passe la copie a `AActiveAbility$$.ctor`. Le masque est
     alors la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
     `<preset>+0x28`. Les presets ne sont PAS interchangeables (mesure : 16 presets, 5 valeurs de
     `rules` distinctes portant le bit 6 ou non) -- d'ou la regle : lire ability par ability,
     jamais generaliser.

CE QUE CE PROBE NE PEUT PAS LIRE -- dit, jamais rabattu sur zero (tri-etat)
    `measured`       le ctor de la classe (ou d'un de ses ctors de base suivis) expose un masque.
    `not_measurable` la classe n'expose AUCUNE des quatre formes -- typiquement un ctor de base
                     DEDUPLIQUE par IL2CPP et mislabel par Ghidra (`GenericAddEffectToOwnerAbility`
                     appelle un corps nomme `Unity_Services_Core_...UnityThreadUtilsInternal___ctor`),
                     ou une base generique absente du dump. « Pas de masque lisible » n'est PAS
                     « masque nul » : une telle ability peut porter le bit sans qu'on le voie.
    `absent`         l'entree du registre n'a pas pu etre reliee a une classe.

SOUS-COMMANDES (ASCII only, depuis scripts/python)
    scan    -> interroge ghidra-mcp, ecrit logs/probe_302_4_raw.json (brut, gitignore)
    report  -> 100 % offline depuis ce brut : tables + compte ventile
    all     -> scan puis report

CONTRAT MACHINE (chemins STABLES)
    docs/rl/case-302-4/tile-target-population.tsv    une ligne par ActiveAbilityType enregistree
    docs/rl/case-302-4/tile-target-population.json   manifeste + compte ventile + la table
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from ghidra_symbols import BINARY, GhidraDown, GhidraMCP, loaded_build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"
RAW = REPO / "logs" / "probe_302_4_raw.json"
TABLES = REPO / "docs" / "rl" / "case-302-4"

SCHEMA_VERSION = "1.0"

# `IdunBattle.Core.Services.TargetingRule.TargetIsTile` -- bit 6. Le port le mirroir dans
# `engine.runner.abilities.targeting_rule` (module GENERE) ; ici on lit le decompile, donc on
# re-derive le bit depuis ce module plutot que de le declarer une seconde fois.
LAMBDA_PREFIX = ("IdunBattle.Core.Services.AbilitiesDatabase.u003Cu003Ec$$"
                 "u003CInitializeActiveAbilitiesu003Eb__27_")
# `search_symbols_by_name` prend une REGEX : `$$` du symbole doit y etre echappe.
LAMBDA_QUERY = r"AbilitiesDatabase\.u003Cu003Ec\$\$u003CInitializeActiveAbilitiesu003Eb__27_\d+$"
INIT_ACTIVE = "IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities"
TO_CCTOR = "IdunBattle.Core.Services.TargetingOptions$$.cctor"

PRESET_STRIDE = 0x40          # sizeof(TargetingOptions)
PRESET_RULES_OFF = 0x28       # TargetingOptions+0x28 = Rules (64 bits)

# Les FABRIQUES statiques de `TargetingOptions` (5e forme). Leurs noms sont lus dans la table de
# symboles au scan ; leur `Rules` est extrait de leur propre decompile, jamais code en dur ici.
FACTORY_QUERY = (r"Core\.Services\.TargetingOptions\$\$"
                 r"(CustomIdunNormalAttackOptions|CustomLokiNormalAttackOptions"
                 r"|SelfCastIfEnemyInCustomRangeOptions)$")


# --------------------------------------------------------------------------------- utilitaires

def _norm(code: str) -> str:
    """Decompile Ghidra -> une instruction par ligne (les appels sont coupes en colonne 80)."""
    code = code.replace("\r\n", "\n")
    # Une continuation d'appel commence par des espaces puis '(' -- on la recolle.
    code = re.sub(r"\n\s+\(", "(", code)
    code = re.sub(r",\n\s+", ",", code)
    return code


def _int(tok: str) -> int:
    tok = tok.strip()
    return int(tok, 16) if tok.lower().startswith("0x") else int(tok)


def _args(call: str) -> list:
    """Decoupe la liste d'arguments d'un appel deja recolle, en respectant les parentheses."""
    out, depth, cur = [], 0, ""
    for ch in call:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        if depth >= 1:
            if ch == "," and depth == 1:
                out.append(cur.strip())
                cur = ""
                continue
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _literal(tok: str):
    """`(void *)0x40000042` / `0x2` / `1000` -> int ; sinon None (ce n'est pas un litteral).

    ⚠ Un immediat 64 bits dont la valeur tombe dans l'espace d'adressage de l'image est rendu par
    Ghidra comme une REFERENCE (`&LAB_180004000`), pas comme un nombre. VERIFIE AUX OCTETS sur
    `...Loki.DeathScreamAbility$$.ctor` : `48 b8 00 40 00 80 01 00 00 00` = `mov rax, 0x180004000`,
    puis `mov [rsp+0x20], rax` -> c'est bien le 5e argument `rules`, valeur `0x180004000`. Sans
    cette lecture, l'ability ressortait `not_measurable` alors que son masque est explicite.
    """
    tok = tok.strip()
    m = re.fullmatch(r"(?:\(\s*void\s*\*\s*\)\s*)?(0x[0-9a-fA-F]+|\d+)", tok)
    if m:
        return _int(m.group(1))
    m = re.fullmatch(r"(?:\(\s*void\s*\*\s*\)\s*)?&(?:LAB|DAT|UNK|FUN)_([0-9a-fA-F]+)", tok)
    return int(m.group(1), 16) if m else None


# ------------------------------------------------------------------------------ scan (ghidra)

def _decompile(g: GhidraMCP, targets: list, timeout: int = 120) -> dict:
    """name/addr -> code. Batch : `decompile_function` accepte une liste.

    ATTENTION -- `GhidraMCP.call` ne rend que le PREMIER bloc `content`, donc le premier resultat
    d'un batch : l'utiliser ici rendrait 1 fonction sur N, SILENCIEUSEMENT (mesure : le premier
    scan a rendu 257 lambdas avec un `code` vide, et rien n'a leve). On lit donc
    `result.structuredContent`, qui porte la liste ENTIERE.
    """
    body = g._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "decompile_function",
                               "arguments": {"binary_name": BINARY, "name_or_address": targets,
                                             "timeout_sec": timeout}}})
    frames = g._frames(body)
    if not frames:
        raise GhidraDown("reponse vide de ghidra-mcp pour decompile_function")
    res = (frames[0].get("result") or {})
    items = ((res.get("structuredContent") or {}).get("result")) or []
    out = {}
    for i, item in enumerate(items):
        key = targets[i] if i < len(targets) else item.get("name")
        out[key] = {"ghidra_name": item.get("name"), "code": item.get("code") or "",
                    "error": item.get("error")}
    missing = [t for t in targets if t not in out]
    if missing:
        # Jamais silencieux : une cible non rendue doit se voir dans le brut.
        for t in missing:
            out[t] = {"ghidra_name": None, "code": "", "error": "non rendu par le batch"}
    return out


def _cached(build: str) -> dict:
    """Brut precedent, s'il porte le MEME build : evite de repayer la decompilation des lambdas."""
    if not RAW.exists():
        return {}
    try:
        prev = json.loads(RAW.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return prev if prev.get("build") == build else {}


def cmd_scan(args) -> int:
    g = GhidraMCP(timeout=600).connect()
    build = loaded_build(g)
    print("build charge par ghidra-mcp : %s" % build)
    idx = _symbol_index(build)
    if idx.get("__collisions__"):
        print("  NOTE : %d noms C aplatis ambigus dans la table (resolus par la 1re occurrence)"
              % len(idx["__collisions__"]))
    prev = {} if args.refresh else _cached(build)

    # 1. registre + cctor des presets
    print("  [1/4] InitializeActiveAbilities + TargetingOptions.cctor ...", flush=True)
    big = {}
    for key, slot in ((INIT_ACTIVE, "init_active_abilities"),
                      (TO_CCTOR, "targeting_options_cctor")):
        if (prev.get(slot) or {}).get("code"):
            big[key] = prev[slot]
        else:
            big.update(_decompile(g, [key], timeout=300))

    # 1b. les fabriques statiques de TargetingOptions (5e forme de masque)
    fsyms = (g.call("search_symbols_by_name",
                    {"binary_name": BINARY, "query": FACTORY_QUERY,
                     "functions_only": True, "limit": 50}) or {}).get("symbols") or []
    fnames = sorted({s["name"] for s in fsyms})
    print("        %d fabriques TargetingOptions : %s"
          % (len(fnames), [n.rsplit("$$", 1)[-1] for n in fnames]), flush=True)
    fac_code = _decompile(g, fnames) if fnames else {}

    # 2. les lambdas de fabrique
    print("  [2/4] lambdas b__27_N ...", flush=True)
    syms = (g.call("search_symbols_by_name",
                   {"binary_name": BINARY, "query": LAMBDA_QUERY,
                    "functions_only": True, "limit": 2000}) or {}).get("symbols") or []
    lam = {}
    for s in syms:
        m = re.search(r"b__27_(\d+)$", s["name"])
        if m:
            lam[int(m.group(1))] = {"addr": s["address"], "symbol": s["name"]}
    print("        %d lambdas trouvees" % len(lam), flush=True)

    prev_lam = prev.get("lambdas") or {}
    names = [lam[n]["symbol"] for n in sorted(lam)
             if not (prev_lam.get(str(n)) or {}).get("code")]
    lam_code = {}
    print("        %d a decompiler (%d reprises du brut precedent)"
          % (len(names), len(lam) - len(names)), flush=True)
    for i in range(0, len(names), 25):
        lam_code.update(_decompile(g, names[i:i + 25]))
        print("        decompile %d/%d" % (min(i + 25, len(names)), len(names)), flush=True)
    for n in sorted(lam):
        lam[n]["code"] = (lam_code.get(lam[n]["symbol"], {}).get("code")
                          or (prev_lam.get(str(n)) or {}).get("code") or "")

    # 3. les ctors de classes d'ability referencees par ces lambdas (+ chaines de base)
    print("  [3/4] ctors des classes d'ability ...", flush=True)
    wanted, ctor_code = set(), {}
    empty = [n for n in sorted(lam) if not lam[n]["code"]]
    if empty:
        print("        ATTENTION : %d lambdas sans code decompile (ex. %s)"
              % (len(empty), empty[:5]), flush=True)
    for n in sorted(lam):
        for cls in _classes_constructed(lam[n]["code"], idx):
            wanted.add(cls)
    print("        %d classes d'ability distinctes referencees" % len(wanted), flush=True)
    prev_ctors = prev.get("ctors") or {}
    todo = sorted(wanted)
    rounds = 0
    while todo and rounds < 6:
        got, ask = {}, [c for c in todo if not (prev_ctors.get(c) or {}).get("code")]
        for c in todo:
            if (prev_ctors.get(c) or {}).get("code"):
                got[c + "$$.ctor"] = prev_ctors[c]
        for i in range(0, len(ask), 20):
            got.update(_decompile(g, [c + "$$.ctor" for c in ask[i:i + 20]]))
            print("        round %d : %d/%d" % (rounds, min(i + 20, len(ask)), len(ask)),
                  flush=True)
        nxt = []
        for cls in todo:
            item = got.get(cls + "$$.ctor") or {}
            ctor_code[cls] = item
            for base in _base_ctors(item.get("code") or "", idx):
                if base not in ctor_code and base not in nxt:
                    nxt.append(base)
        todo = nxt
        rounds += 1

    # 4. ecriture du brut
    print("  [4/4] ecriture du brut ...", flush=True)
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "build": build,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "init_active_abilities": big.get(INIT_ACTIVE, {}),
        "targeting_options_cctor": big.get(TO_CCTOR, {}),
        "targeting_options_factories": fac_code,
        "lambdas": {str(k): v for k, v in sorted(lam.items())},
        "ctors": ctor_code,
    }, indent=1), encoding="utf-8")
    print("OK  brut -> %s (%.1f Mo)" % (RAW, RAW.stat().st_size / 1e6))
    return 0


_CTOR_CALL = re.compile(r"\b([A-Za-z0-9_]+)___ctor\s*\(")
_SYMIDX: dict = {}


def _symbol_index(build: str) -> dict:
    """`<nom C aplati de la classe>` -> `<symbole Ghidra verbatim>`, pour toute classe qui a un
    `$$.ctor` dans la table du build.

    On NE DEVINE PAS le nom pointe a partir du nom C : Ghidra remplace les `.` par des `_`, et un
    nom de classe peut deja contenir un `_` (mesure : `...Active.Loki.Loki_NormalAttackAbility`
    devine faux en `...Active.Loki.Loki.NormalAttackAbility`, et la cible ressort introuvable).
    L'index inverse la transformation par CONSTAT, depuis `data/symbols/<build>/ghidra/functions.tsv`.
    """
    if build in _SYMIDX:
        return _SYMIDX[build]
    p = SYMBOLS_DIR / build / "ghidra" / "functions.tsv"
    idx, collisions = {}, {}
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                _addr, _, name = line.rstrip("\n").partition("\t")
                if not name.endswith("$$.ctor"):
                    continue
                cls = name[:-len("$$.ctor")]
                flat = cls.replace(".", "_")
                if flat in idx and idx[flat] != cls:
                    collisions.setdefault(flat, {idx[flat]}).add(cls)
                idx.setdefault(flat, cls)
    idx["__collisions__"] = collisions
    _SYMIDX[build] = idx
    return idx


def _classes_constructed(code: str, idx: dict) -> list:
    """Classe instanciee par une lambda de fabrique (`new <X>()`).

    On ne filtre PAS sur le nom : deux entrees du registre construisent des classes qui ne portent
    pas « Ability » (`...Active.TestTargetAndAdjacentAttack`, `...Active.TestTileAttack`), et le
    filtre les rendait `absent`. Le motif du corps suffit a lever l'ambiguite : la lambda alloue
    (`thunk_FUN_...`) puis appelle UN ctor -- on retient celui qui est resolu par la table des
    symboles, ce qui exclut les helpers d'allocation.
    """
    norm = _norm(code)
    out = []
    for m in _CTOR_CALL.finditer(norm):
        flat = m.group(1)
        if flat in idx:
            out.append(idx[flat])
        elif flat.endswith("Ability") or "Ability_" in flat:
            out.append(flat.replace("_", "."))
    return out


def _base_ctors(code: str, idx: dict) -> list:
    """Ctors de classe de BASE appeles depuis un ctor d'ability.

    Le filtre porte sur « contient Ability », pas « finit par Ability » : la base de
    `...Loki.SwoopingHawkAbility` s'appelle `DiveAttackAbilityBase`, et exiger le suffixe la
    rendait invisible -- ses deux heritieres (1064, 1091) ressortaient `not_measurable` alors que
    leur masque est parfaitement lisible UN CRAN plus haut.
    """
    out = []
    for m in _CTOR_CALL.finditer(_norm(code)):
        flat = m.group(1)
        if "Ability" not in flat or flat.endswith("AActiveAbility"):
            continue
        if flat.endswith("ADeprecatedActiveAbility"):
            continue
        out.append(idx.get(flat) or flat.replace("_", "."))
    return out


# ------------------------------------------------------------------------------------- report

def _parse_presets(code: str) -> dict:
    """`TargetingOptions$$.cctor` -> {offset_du_preset: rules}. Les stores sont sur les statics de
    `TargetingOptions` ; les LECTURES viennent d'une autre classe (les `TargetingRange`), d'ou le
    suivi des variables plutot qu'un grep d'offsets."""
    code = _norm(code)
    stat_vars, presets, dats = set(), {}, {}
    for line in code.split("\n"):
        line = line.strip()
        m = re.match(r"(\w+)\s*=\s*\*\(\w+ \*+\)\((DAT_[0-9a-f]+) \+ 0xb8\);", line)
        if m:
            stat_vars.add(m.group(1))
            dats[m.group(1)] = m.group(2)
            continue
        m = re.match(r"\*\(undefined8 \*\)\((\w+) \+ (0x[0-9a-f]+|\d+)\)\s*=\s*(0x[0-9a-f]+|\d+);",
                     line)
        if m and m.group(1) in stat_vars:
            off = _int(m.group(2))
            if off % PRESET_STRIDE == PRESET_RULES_OFF:
                presets[off - PRESET_RULES_OFF] = (_int(m.group(3)), dats.get(m.group(1)))
            continue
        m = re.match(r"(\w+)\[(\d+)\]\s*=\s*(0x[0-9a-f]+|\d+);", line)
        if m and m.group(1) in stat_vars:
            off = int(m.group(2)) * 8
            if off % PRESET_STRIDE == PRESET_RULES_OFF:
                presets[off - PRESET_RULES_OFF] = (_int(m.group(3)), dats.get(m.group(1)))
    # Le DAT majoritaire parmi les stores EST la classe TargetingOptions.
    owners = [d for _v, d in presets.values() if d]
    dat = max(set(owners), key=owners.count) if owners else None
    return {"dat": dat, "rules_by_offset": {o: v for o, (v, _d) in sorted(presets.items())}}


def _parse_factories(raw: dict, presets: dict, to_dat: str) -> dict:
    """Les fabriques statiques -> `{nom C aplati: {rules, extra}}`.

    Deux ecritures possibles du champ `Rules` (+0x28) dans une fabrique :
      - `*(...)(out + 0x28) = <litteral>;`             -> masque COMPLET ;
      - `*(...)(out + 0x28) = *(...)(<statics> + N) | <reg>;` -> `<preset>.Rules | extraRules`, et
        `extraRules` n'est PAS lisible chez l'appelant -> masque MINORANT (`extra = True`).
    """
    out = {}
    for name, item in (raw.get("targeting_options_factories") or {}).items():
        code = _norm(item.get("code") or "")
        short = name.rsplit("$$", 1)[-1]
        flat = name.replace(".", "_").replace("$$", "__")
        rules, extra = None, False
        stat_vars = set()
        for line in code.split("\n"):
            line = line.strip()
            m = re.match(r"(\w+)\s*=\s*\*\(\w+ \*+\)\((DAT_[0-9a-f]+) \+ 0xb8\);", line)
            if m and (not to_dat or m.group(2) == to_dat):
                stat_vars.add(m.group(1))
                continue
            m = re.match(r"\*\(\w+ \*\)\(\(longlong\)\w+ \+ 0x28\)\s*=\s*(.+);", line)
            if not m:
                continue
            rhs = m.group(1)
            lit = _literal(rhs)
            if lit is not None:
                rules, extra = lit, False
                continue
            mm = re.match(r"\*\(ulonglong \*\)\((\w+) \+ (0x[0-9a-f]+|\d+)\)\s*\|", rhs.strip())
            if mm and mm.group(1) in stat_vars:
                off = _int(mm.group(2))
                base = off - (off % PRESET_STRIDE)
                if base in presets:
                    rules, extra = presets[base], True
        if rules is not None:
            out[flat] = {"rules": rules, "extra": extra, "symbol": name, "short": short}
    return out


def _parse_registry(code: str) -> list:
    """`InitializeActiveAbilities` -> [(offset du champ de cache `<>9__27_N`, abilityId)].

    Deux formes de `Dictionary.Add` sortent du decompilateur : l'appel generique avec la cle
    passee par adresse (`local_X[0] = <id>; ...Add(dict, local_X, val, MI)`) et l'appel inline
    avec la cle en litteral (`FUN_...(dict, <id>, val, MI)`). Les deux sont lues.
    """
    code = _norm(code)
    out, cur_off = [], None
    for line in code.split("\n"):
        line = line.strip()
        m = re.search(r"\*\(longlong \*\)\(\*\(longlong \*\)\(DAT_[0-9a-f]+ \+ 0xb8\) \+ "
                      r"(0x[0-9a-f]+|\d+)\)\s*=\s*\w+;", line)
        if m:
            cur_off = _int(m.group(1))
            continue
        m = re.search(r"\w+\s*=\s*\*\(longlong \*\)\(\*\(longlong \*\)\(DAT_[0-9a-f]+ \+ 0xb8\) \+ "
                      r"(0x[0-9a-f]+|\d+)\);", line)
        if m:
            cur_off = _int(m.group(1))
            continue
        m = re.match(r"(\w+)\[0\]\s*=\s*(0x[0-9a-f]+|\d+);", line)
        if m and cur_off is not None:
            out.append((cur_off, _int(m.group(2))))
            cur_off = None
            continue
        m = re.match(r"FUN_[0-9a-f]+\(\w+,(0x[0-9a-f]+|\d+),\w+,", line)
        if m and cur_off is not None:
            out.append((cur_off, _int(m.group(1))))
            cur_off = None
    return out


def _enum_members(build: str) -> dict:
    """`ActiveAbilityType` du BUILD, lu dans `data/symbols/<build>/frida/enums.tsv`.

    On ne lit PAS l'enum du port ici : le denominateur doit venir du jeu, pas du mirror. Les deux
    sont ensuite compares -- un ecart est une derive de mirror, et il se dit.
    """
    p = SYMBOLS_DIR / build / "frida" / "enums.tsv"
    if not p.exists():
        return {}
    out = {}
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            name, _, vals = line.rstrip("\n").partition("\t")
            if name != "IdunBattle.Entities.Enum.ActiveAbilityType":
                continue
            for pair in vals.split(","):
                k, _, v = pair.partition("=")
                try:
                    out.setdefault(int(k), []).append(v)
                except ValueError:
                    pass
    return out


def _ability_class_of(lam_code: str, idx: dict) -> str:
    cls = _classes_constructed(lam_code, idx)
    return cls[0] if cls else ""


_STACK_VAR = re.compile(r"^(?:local|uStack|aStack|auStack)_([0-9a-f]+)$")


def _stack_off(var: str):
    """`local_48` / `uStack_20` -> l'offset de pile encode dans le nom Ghidra (0x48 / 0x20).

    Ghidra nomme une variable de pile par son deplacement depuis le cadre. Deux variables du MEME
    cadre sont donc a distance `off(a) - off(b)` l'une de l'autre -- c'est ce qui permet de trouver
    le champ `Rules` (+0x28) d'une struct construite INLINE, sans aucun appel de ctor.
    """
    m = _STACK_VAR.match(var.strip().lstrip("&").strip())
    return int(m.group(1), 16) if m else None


def _factory_rules(code: str, factories: dict):
    """Le ctor delegue-t-il a une FABRIQUE statique de `TargetingOptions` ?

    Trois existent dans ce build (`CustomIdunNormalAttackOptions`, `CustomLokiNormalAttackOptions`,
    `SelfCastIfEnemyInCustomRangeOptions`). Deux d'entre elles font `Rules = <preset> | extraRules`,
    et `extraRules` passe par un registre que le decompile de l'APPELANT n'expose pas -> le masque
    rendu est alors un MINORANT, et l'etat le dit (`measured_partial`).
    """
    for name, info in factories.items():
        if re.search(r"\b%s\s*\(" % re.escape(name), code):
            return dict(info, factory=name)
    return None


def _mask_from_ctor(code: str, to_dat: str, presets: dict, factories: dict = None) -> dict:
    """Masque `Rules` effectif expose par un ctor d'ability. Rend un dict TRI-ETAT."""
    code = _norm(code)
    # variables recevant le DEBUT (offset multiple de 0x40) d'un preset de TargetingOptions
    stat_vars, preset_of_var, presets_read = set(), {}, set()
    for line in code.split("\n"):
        line = line.strip()
        m = re.match(r"(\w+)\s*=\s*\*\(\w+ \*+\)\((DAT_[0-9a-f]+) \+ 0xb8\);", line)
        if m:
            if to_dat and m.group(2) == to_dat:
                stat_vars.add(m.group(1))
            continue
        m = re.match(r"(\w+)\s*=\s*\*\(undefined8 \*\)\((\w+) \+ (0x[0-9a-f]+|\d+)\);", line)
        if m and m.group(2) in stat_vars:
            off = _int(m.group(3))
            presets_read.add(off - (off % PRESET_STRIDE))
            if off % PRESET_STRIDE == 0:
                preset_of_var[m.group(1)] = off
            continue
        m = re.match(r"(\w+)\s*=\s*\*(\w+);", line)          # `uVar5 = *puVar2;` (offset 0)
        if m and m.group(2) in stat_vars:
            presets_read.add(0)
            preset_of_var[m.group(1)] = 0

    calls = [c for c in re.findall(r"IdunBattle_Core_Services_TargetingOptions___ctor\s*\([^;]*\)",
                                   code)]
    if calls:
        a = _args(calls[0])
        if len(a) >= 7:
            lit = _literal(a[4])
            if lit is None:
                return {"state": "not_measurable", "why": "overload 7-args, RULES non litteral",
                        "form": "literal"}
            return {"state": "measured", "rules": lit, "form": "literal"}
        if len(a) == 3:
            tpl = _preset_for(a[1], preset_of_var, presets_read)
            add = _literal(a[2])
            if tpl is None or add is None or tpl not in presets:
                return {"state": "not_measurable",
                        "why": "overload PRESET+flags : preset=%r additional=%r" % (tpl, add),
                        "form": "preset+flags"}
            return {"state": "measured", "rules": presets[tpl] | add, "form": "preset+flags",
                    "preset": tpl, "additional": add}
        if len(a) == 2:
            tpl = _preset_for(a[1], preset_of_var, presets_read)
            if tpl is None or tpl not in presets:
                return {"state": "not_measurable", "why": "overload PRESET seul : preset=%r" % tpl,
                        "form": "preset"}
            return {"state": "measured", "rules": presets[tpl], "form": "preset", "preset": tpl}
        return {"state": "not_measurable", "why": "overload inconnu (%d args)" % len(a),
                "form": "?"}

    # Quatrieme forme : aucun appel de ctor -- copie directe des 0x40 octets d'un preset statique.
    if len(presets_read) == 1:
        tpl = next(iter(presets_read))
        if tpl in presets:
            return {"state": "measured", "rules": presets[tpl], "form": "static-copy",
                    "preset": tpl}
    if len(presets_read) > 1:
        return {"state": "not_measurable",
                "why": "copie statique AMBIGUE : presets lus = %s" % sorted(presets_read),
                "form": "static-copy"}

    # Cinquieme forme : une FABRIQUE statique de `TargetingOptions` remplit la struct.
    fac = _factory_rules(code, factories or {})
    if fac is not None:
        if fac.get("extra"):
            return {"state": "measured_partial", "rules": fac["rules"], "form": "factory",
                    "factory": fac["factory"],
                    "why": ("%s fait `Rules = <preset> | extraRules` et `extraRules` passe par un "
                            "registre invisible du decompile de l'appelant -- masque MINORANT"
                            % fac["factory"])}
        return {"state": "measured", "rules": fac["rules"], "form": "factory",
                "factory": fac["factory"]}

    # Sixieme forme : la struct est construite INLINE sur la pile, sans ctor ni preset. On retrouve
    # le champ `Rules` par l'offset encode dans les noms de variables Ghidra (base - 0x28).
    m = re.search(r"(?:AActiveAbility|ADeprecatedActiveAbility)___ctor\s*\(\s*this\s*,\s*&(\w+)",
                  code)
    if m:
        base = _stack_off(m.group(1))
        if base is not None:
            want = base - PRESET_RULES_OFF
            for line in code.split("\n"):
                mm = re.match(r"(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+);", line.strip())
                if mm and _stack_off(mm.group(1)) == want:
                    return {"state": "measured", "rules": _int(mm.group(2)), "form": "inline",
                            "stack_base": hex(base)}
            return {"state": "not_measurable",
                    "why": "struct INLINE : champ Rules (base %s - 0x28) non ecrit par un litteral"
                           % hex(base), "form": "inline"}

    return {"state": "not_measurable", "why": "aucune forme de TargetingOptions dans ce ctor",
            "form": "none"}


def _preset_for(arg: str, preset_of_var: dict, presets_read: set):
    v = arg.strip().lstrip("&").strip()
    if v in preset_of_var:
        return preset_of_var[v]
    if len(presets_read) == 1:
        return next(iter(presets_read))
    return None


def _calibrate(registry: list, lambdas: dict, idx: dict) -> dict:
    """Relation offset du champ de cache `<>9__27_N` <-> N. Elle est AFFINE et se VERIFIE.

    Le report ne la suppose pas : il la derive de la borne (offsets et N sont deux suites
    croissantes de meme cardinal), puis exige une CONCORDANCE DE NOMS massive entre le nom de
    l'`ActiveAbilityType` et le nom de la classe construite. Sous le seuil, le report REFUSE de
    conclure -- une calibration fausse decale TOUT l'inventaire d'un cran.
    """
    from engine.entities.active_ability_type import ActiveAbilityType

    offs = sorted({o for o, _i in registry})
    if not offs or not lambdas:
        return {"ok": False, "why": "registre ou lambdas vides"}
    step = 8
    base = min(offs) - step * min(int(n) for n in lambdas)
    best = None
    for cand in (base, min(offs), min(offs) - step):
        ok = agree = total = 0
        for off, aid in registry:
            n = (off - cand) // step
            if (off - cand) % step or str(n) not in lambdas:
                continue
            ok += 1
            cls = _ability_class_of(lambdas[str(n)].get("code") or "", idx)
            short = cls.rsplit(".", 1)[-1]
            try:
                nm = ActiveAbilityType(aid).name
            except ValueError:
                continue
            total += 1
            if short.lower().replace("_", "") == (nm + "Ability").lower().replace("_", ""):
                agree += 1
        score = (agree / total) if total else 0.0
        if best is None or score > best["score"]:
            best = {"base": cand, "score": score, "agree": agree, "checked": total,
                    "mapped": ok}
    best["ok"] = best["score"] >= 0.5
    return best


def cmd_report(args) -> int:
    if not RAW.exists():
        print("brut absent : lancer `python probe_302_4_tile_target_population.py scan`")
        return 2
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.runner.abilities.targeting_rule import TargetingRule

    # ⚠ `TargetingRule.TargetIsTile` vaut le MASQUE (0x40), pas l'index du bit. Le confondre rend
    #    `(rules >> 64) & 1` = 0 pour TOUT LE MONDE -- un inventaire vide qui se lit « rien a
    #    signaler ». Mesure : le crosscheck a rendu « 0 / 97 » avant correction.
    mask = int(TargetingRule.TargetIsTile)

    idx = _symbol_index(raw["build"])
    pres = _parse_presets(raw["targeting_options_cctor"].get("code") or "")
    presets, to_dat = pres["rules_by_offset"], pres["dat"]
    factories = _parse_factories(raw, presets, to_dat)
    registry = _parse_registry(raw["init_active_abilities"].get("code") or "")
    lambdas = raw["lambdas"]
    ctors = raw["ctors"]

    cal = _calibrate(registry, lambdas, idx)
    if not cal.get("ok"):
        # On ne rend PAS un inventaire non calibre : il serait faux d'un cran, et se lirait juste.
        print("CALIBRATION REFUSEE : %s" % json.dumps(cal))
        print("  (registre lu = %d entrees, lambdas = %d) -- relancer `scan --refresh`"
              % (len(registry), len(lambdas)))
        return 3
    rows = []
    for off, aid in sorted(registry, key=lambda t: t[1]):
        n = (off - cal["base"]) // 8 if cal.get("ok") else None
        lam = lambdas.get(str(n)) if n is not None else None
        cls = _ability_class_of((lam or {}).get("code") or "", idx)
        try:
            nm = ActiveAbilityType(aid).name
        except ValueError:
            nm = "<hors enum du port>"
        found = {"state": "absent", "why": "aucune classe reliee"}
        chain = []
        if cls:
            found, chain = _mask_of_class(cls, ctors, to_dat, presets, idx, factories)
        rows.append({"id": aid, "enum_name": nm, "lambda": n, "cache_offset": off,
                     "ability_class": cls, "ctor_chain": chain, **found})

    _emit(rows, cal, presets, raw, mask, args)
    return 0


def _mask_of_class(cls: str, ctors: dict, to_dat: str, presets: dict, idx: dict,
                   factories: dict = None, depth: int = 0):
    """Masque d'une classe, en suivant au besoin la chaine de ctors de BASE (max 4 niveaux)."""
    chain = [cls]
    item = ctors.get(cls) or {}
    code = item.get("code") or ""
    if not code:
        return ({"state": "not_measurable",
                 "why": "ctor introuvable au decompile (%s)" % (item.get("error") or "absent"),
                 "form": "none"}, chain)
    res = _mask_from_ctor(code, to_dat, presets, factories)
    if res["state"].startswith("measured") or depth >= 4:
        return (res, chain)
    for base in _base_ctors(code, idx):
        if base == cls:
            continue
        sub, subchain = _mask_of_class(base, ctors, to_dat, presets, idx, factories, depth + 1)
        if sub["state"].startswith("measured"):
            return (sub, chain + subchain)
    return (res, chain)


def _routed_decision_ids() -> dict:
    """Abilities dont la face DECISION a une route PROPRE -- re-derivee du code, jamais recopiee.

    « Avoir une route » ne veut PAS dire « etre evaluable » : toute ability du registre passe par
    `DefaultActiveAbilityPlaybook`. Pour une cible TUILE, ce qui compte est un chemin qui emet une
    action dont le `target` EST une entite-tuile -- d'ou DEUX champs rendus : `route` (quel chemin)
    et `emits_tile_target` (ce chemin resout-il une cible par `ctx.tile_id_by_pos`).

    ⚠ `emits_tile_target = False` ne veut PAS dire « la route ignore les tuiles ». Mesure : les
    playbooks de `1166 AberrantHypermorph` et `1194 NovaShield` LISENT bien le domaine tuile
    (`ability_targets(...)` filtre `kind == "tile"`) mais emettent `target: None` -- ils choisissent
    une POSITION de caster, pas une cible. Le champ dit ce qu'il dit : la cible emise.

    Les registres sont consultes du PLUS specifique au moins specifique, et le premier gagne : la
    route non-attaque (seule a porter l'aiguillage `targets_tiles`), puis les NonComparable, puis
    les bespoke de `ComparableAbilityGenerator.generate`, et EN DERNIER `engine.playbook.REGISTRY`
    -- un playbook Comparable ordinaire tire ses candidats d'`attackPlans`/`_best_attack`, dont les
    tranches 1 et 3 ont MESURE qu'il rend l'attaque normale (69) sur un tile-target.
    """
    import inspect

    out = {}

    def _add(aid, label, tiles):
        try:
            out.setdefault(int(aid), {"route": label, "emits_tile_target": bool(tiles)})
        except (TypeError, ValueError):
            pass

    def _emits_tile_id(obj) -> bool:
        """Le module du playbook resout-il une cible par `ctx.tile_id_by_pos` ?

        C'est le SEUL pont `(col,row) -> tileEntityId` du port (`engine.ai.context`), donc sa
        presence dans le module est la trace, LUE DANS LE CODE, qu'une route emet une cible tuile.
        Mieux qu'une liste d'ids en dur : elle suit le code au lieu de se perimer avec lui.
        """
        try:
            return "tile_id_by_pos" in inspect.getsource(inspect.getmodule(type(obj)))
        except (OSError, TypeError):
            return False

    # 1. La route non-attaque, SEULE a porter l'aiguillage de domaine (`targets_tiles`, mirror de
    #    `get_IsTileTargeting`). C'est elle qu'il faut interroger, pas la simple presence au registre.
    from engine.playbook.nonattack import NONATTACK_PLAYBOOKS
    for aid, pb in NONATTACK_PLAYBOOKS.items():
        tiles = False
        try:
            tiles = bool(pb.targets_tiles(int(aid)))
        except Exception:                                               # noqa: BLE001
            tiles = False
        _add(aid, "nonattack:%s" % type(pb).__name__, tiles)
    # 2. Les NonComparable bespoke : chacune enumere son propre domaine. Celles qui emettent une
    #    cible TUILE se reconnaissent a leur usage de `ctx.tile_id_by_pos` (voir `_emits_tile_id`).
    from engine.playbook.noncomparable import PLAYBOOKS as NC_PLAYBOOKS
    for aid, pb in NC_PLAYBOOKS.items():
        _add(aid, "noncomparable:%s" % type(pb).__name__, _emits_tile_id(pb))
    # 3. Les bespoke cablees dans `ComparableAbilityGenerator.generate`.
    from engine.playbook.excruciating_frequencies import _ABILITY_ID as EXFREQ_ID
    _add(EXFREQ_ID, "bespoke excruciating_frequencies", True)
    from engine.playbook.bespoke import BESPOKE_SELFCAST
    for aid in BESPOKE_SELFCAST:
        _add(aid, "bespoke selfcast", False)
    from engine.ai.action_generators import _GALVANIC_REPAIR_ID
    _add(_GALVANIC_REPAIR_ID, "bespoke repair_galvanic", False)
    # 4. En DERNIER : un playbook Comparable au registre. Il n'enumere PAS de tuile -- ses candidats
    #    viennent d'`attackPlans`/`_best_attack`, dont la tranche 1 a MESURE qu'il rend l'attaque
    #    normale (69) sur un tile-target. Le marquer « route » sans le dire surestimerait la
    #    couverture, et c'est exactement ce que cette tranche doit eviter.
    import engine.playbook as PB
    for aid, pb in getattr(PB, "REGISTRY", {}).items():
        _add(aid, "REGISTRY:%s (domaine unite)" % type(pb).__name__, _emits_tile_id(pb))
    return out


def _carriers_index() -> dict:
    """`nom d'ability (minuscule)` -> porteurs ventiles par `kind`, depuis le gameconfig.

    Le gate de confrontabilite du depot exige de VENTILER hero/mow/summon/npc : un item dont tous
    les porteurs sont `npc` n'est pas « bloque », il est NON PERTINENT. On passe donc par
    `unit_map.all_kits()` (les 5 voies d'attribution derivables du gameconfig), et on rend `None`
    -- pas `{}` -- si le gameconfig n'est pas lisible : un zero sur un axe invisible se lirait
    « aucun porteur ».

    ⚠ Ce que cette colonne N'EST PAS : une gate de spawnabilite. Le `kind` du gameconfig MENT sur
    ce point (CLAUDE.md) -- la vraie gate HERO/MoW est la presence dans
    `rl_duel.py build --list-pool`, et une absence du pool se leve par injection catalogue
    (`case-92` §6). La colonne dit QUI porte, pas PAR OU on l'amene en bataille.
    """
    try:
        import unit_map as UM
        kits = UM.all_kits()
    except Exception as exc:                                            # noqa: BLE001
        return {"__error__": str(exc)}
    idx = {}
    for k in kits:
        for aid in (k.get("abilities_all") or []):
            idx.setdefault(aid.lower(), []).append((k.get("id"), k.get("kind")))
    return idx


def _carriers_of(name: str, idx: dict) -> dict:
    """Porteurs d'une ability par son NOM d'enum. Tri-etat : `None` = gameconfig non lu."""
    if not idx or "__error__" in idx:
        return None
    hits = idx.get((name or "").lower()) or []
    out = {}
    for uid, kind in hits:
        out.setdefault(kind or "?", []).append(uid)
    return out


def _crosscheck(rows: list, mask: int) -> dict:
    """CONTROLE INDEPENDANT de la methode : les masques lus au decompile doivent redonner, sur les
    abilities DEJA portees, exactement le `TARGETING_OPTIONS.rules` que le port a inscrit -- chacun
    ayant ete relu a la main par la tranche qui a fait entrer l'ability. Un desaccord n'est PAS un
    detail : il signale soit une erreur d'extraction ici, soit un masque FAUX au registre.
    """
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (NORMAL_ATTACK_TARGETING_OPTIONS,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.entities.active_ability_type import ActiveAbilityType

    # Les TROIS sources de masque du port (les deux du registre + le preset de l'attaque normale,
    # qui n'appartient a aucune classe d'`ABILITY_CLASSES`).
    port_masks = {}
    for aid, cls in ABILITY_CLASSES.items():
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is not None:
            port_masks[int(aid)] = opts
    for aid, opts in TARGETING_OPTIONS_UNPORTED.items():
        port_masks.setdefault(int(aid), opts)
    port_masks.setdefault(int(ActiveAbilityType.Loki_NormalAttack), NORMAL_ATTACK_TARGETING_OPTIONS)

    agree, disagree, unported, unreadable = [], [], [], []
    for r in rows:
        opts = port_masks.get(r["id"])
        if opts is None:
            unported.append(r["id"])
            continue
        if r.get("state") != "measured":
            unreadable.append((r["id"], r.get("state")))
            continue
        port = int(opts.rules)
        if port == r["rules"]:
            agree.append(r["id"])
        else:
            disagree.append({"id": r["id"], "enum_name": r["enum_name"],
                             "port": hex(port), "decompile": hex(r["rules"]),
                             "form": r.get("form"),
                             "bit_differs": bool((port & mask) != (r["rules"] & mask))})
    return {"agree": len(agree), "disagree": disagree, "not_in_registry": len(unported),
            "registry_but_unreadable": unreadable}


def _emit(rows: list, cal: dict, presets: dict, raw: dict, mask: int, args) -> None:
    from engine.runner.abilities.handler import ABILITY_CLASSES

    routed = _routed_decision_ids()

    # `measured_partial` = base connue, `extraRules` illisible : le bit PRESENT est certain, le bit
    # ABSENT est INDETERMINE. On compte donc ces lignes a part, jamais dans un « n'a pas le bit ».
    tiles = [r for r in rows
             if r.get("state", "").startswith("measured") and (r.get("rules", 0) & mask)]
    partial = [r for r in rows if r.get("state") == "measured_partial"]
    partial_no_bit = [r for r in partial if not (r.get("rules", 0) & mask)]
    nomask = [r for r in rows if r.get("state") == "not_measurable"]
    absent = [r for r in rows if r.get("state") == "absent"]
    measured = [r for r in rows if r.get("state") == "measured"]

    for r in rows:
        r["in_ability_classes"] = r["id"] in ABILITY_CLASSES
        rt = routed.get(r["id"]) or {}
        r["decision_route"] = rt.get("route", "")
        r["route_emits_tile_target"] = bool(rt.get("emits_tile_target"))

    print("=== #302 tranche 4 -- population COMPLETE du bit TargetIsTile (masque %s) ==="
          % hex(mask))
    print("build                          : %s (brut du %s)" % (raw["build"], raw["generated_at"]))
    print("calibration offset<->lambda    : base=%s score=%.3f (%d/%d noms concordants) ok=%s"
          % (hex(cal.get("base", 0)), cal.get("score", 0), cal.get("agree", 0),
             cal.get("checked", 0), cal.get("ok")))
    print("presets TargetingOptions lus   : %d  (rules distinctes : %s)"
          % (len(presets), sorted({hex(v) for v in presets.values()})))
    print("")
    enum = _enum_members(raw["build"])
    reg_ids = {r["id"] for r in rows}
    print("--- DENOMINATEUR (re-derive, pas cite) ---")
    print("membres ActiveAbilityType (jeu): %d valeurs distinctes dans enums.tsv" % len(enum))
    print("fabriques b__27_N              : %d" % len(raw["lambdas"]))
    print("entrees du registre natif      : %d" % len(rows))
    print("  masque MESURE                : %d" % len(measured))
    print("  masque PARTIEL (minorant)    : %d  -> bit ABSENT = INDETERMINE sur %d d'entre elles"
          % (len(partial), len(partial_no_bit)))
    print("  masque NON MESURABLE         : %d" % len(nomask))
    print("  classe ABSENTE               : %d" % len(absent))
    print("valeurs d'enum SANS entree     : %d %s"
          % (len(set(enum) - reg_ids), sorted(set(enum) - reg_ids)[:12]))
    print("entrees SANS valeur d'enum     : %d %s"
          % (len(reg_ids - set(enum)), sorted(reg_ids - set(enum))[:12]))
    print("registre du PORT               : %d (ABILITY_CLASSES)" % len(ABILITY_CLASSES))
    print("")
    xc = _crosscheck(rows, mask)
    print("--- CONTROLE : masque decompile vs TARGETING_OPTIONS deja au registre ---")
    print("accord                         : %d" % xc["agree"])
    print("DESACCORD                      : %d" % len(xc["disagree"]))
    for d in xc["disagree"]:
        print("    %-6d %-30s port=%-16s decompile=%-16s forme=%-14s bit6 differe=%s"
              % (d["id"], d["enum_name"][:30], d["port"], d["decompile"], d["form"],
                 d["bit_differs"]))
    print("au registre mais ILLISIBLE ici : %d %s"
          % (len(xc["registry_but_unreadable"]), xc["registry_but_unreadable"] or ""))
    print("")
    print("--- PORTANT TargetIsTile ---")
    print("total                          : %d" % len(tiles))
    print("  route qui EMET une cible tuile: %d"
          % sum(1 for r in tiles if r["route_emits_tile_target"]))
    print("  route sans cible tuile emise : %d"
          % sum(1 for r in tiles if r["decision_route"] and not r["route_emits_tile_target"]))
    print("  AUCUNE route                 : %d" % sum(1 for r in tiles if not r["decision_route"]))
    print("  au registre COMBAT du port   : %d" % sum(1 for r in tiles if r["in_ability_classes"]))
    print("")
    cidx = _carriers_index()
    for r in tiles:
        r["carriers"] = _carriers_of(r["enum_name"], cidx)
    print("  %-6s %-32s %-14s %-6s %-5s %-26s %s"
          % ("id", "ability", "rules", "COMBAT", "tuile", "porteurs", "route DECISION"))
    for r in sorted(tiles, key=lambda r: r["id"]):
        c = r["carriers"]
        cs = ("NON MESURE" if c is None
              else (", ".join("%s:%d" % (k, len(v)) for k, v in sorted(c.items())) or "AUCUN"))
        print("  %-6d %-32s %-14s %-6s %-5s %-26s %s"
              % (r["id"], r["enum_name"][:32], hex(r["rules"]),
                 "oui" if r["in_ability_classes"] else "NON",
                 "OUI" if r["route_emits_tile_target"] else "-", cs,
                 r["decision_route"] or "-- AUCUNE --"))

    if partial:
        print("")
        print("--- MASQUE PARTIEL (%d) : base lue, `extraRules` ILLISIBLE -> minorant ---"
              % len(partial))
        for r in sorted(partial, key=lambda r: r["id"]):
            print("  %-6d %-30s base=%-12s bit6 dans la base=%s  (%s)"
                  % (r["id"], r["enum_name"][:30], hex(r["rules"]),
                     "OUI" if (r["rules"] & mask) else "non -> INDETERMINE",
                     r.get("factory", r.get("form", "?"))))
    if nomask:
        print("")
        print("--- NON MESURABLE (%d) : le masque n'est PAS nul, il est ILLISIBLE ici ---"
              % len(nomask))
        for r in sorted(nomask, key=lambda r: r["id"]):
            print("  %-6d %-34s %-14s %s"
                  % (r["id"], r["enum_name"][:34], r.get("form", "?"), r.get("why", "")))
    if absent:
        print("")
        print("--- CLASSE ABSENTE (%d) ---" % len(absent))
        for r in sorted(absent, key=lambda r: r["id"]):
            print("  %-6d %-34s %s" % (r["id"], r["enum_name"][:34], r.get("why", "")))

    TABLES.mkdir(parents=True, exist_ok=True)
    tsv = TABLES / "tile-target-population.tsv"
    cols = ["id", "enum_name", "ability_class", "state", "form", "rules", "targets_tile",
            "in_ability_classes", "decision_route", "route_emits_tile_target", "why"]
    with tsv.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# build=%s  schema=%s  source=%s\n" % (raw["build"], SCHEMA_VERSION, RAW.name))
        fh.write("\t".join(cols) + "\n")
        for r in sorted(rows, key=lambda r: r["id"]):
            tt = ""
            if r.get("state") == "measured":
                tt = "1" if (r["rules"] & mask) else "0"
            elif r.get("state") == "measured_partial":
                tt = "1" if (r["rules"] & mask) else "indetermine"
            fh.write("\t".join([
                str(r["id"]), r["enum_name"], r.get("ability_class", ""), r.get("state", ""),
                r.get("form", ""), hex(r["rules"]) if "rules" in r else "", tt,
                "1" if r["in_ability_classes"] else "0", r.get("decision_route", ""),
                "1" if r.get("route_emits_tile_target") else "0",
                r.get("why", "")]) + "\n")
    js = TABLES / "tile-target-population.json"
    js.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "build": raw["build"],
        "generated_at": raw["generated_at"], "mask_target_is_tile": hex(mask),
        "calibration": cal, "presets": {hex(k): hex(v) for k, v in presets.items()},
        "crosscheck_vs_port_registry": xc,
        "counts": {"enum_members_game": len(enum), "factories": len(raw["lambdas"]),
                   "registry_entries": len(rows), "measured": len(measured),
                   "measured_partial": len(partial),
                   "measured_partial_bit_indeterminate": len(partial_no_bit),
                   "not_measurable": len(nomask), "absent": len(absent),
                   "targets_tile": len(tiles),
                   "targets_tile_route_emits_tile_target":
                       sum(1 for r in tiles if r["route_emits_tile_target"]),
                   "targets_tile_route_non_tile":
                       sum(1 for r in tiles
                           if r["decision_route"] and not r["route_emits_tile_target"]),
                   "targets_tile_no_route": sum(1 for r in tiles if not r["decision_route"]),
                   "ability_classes": len(ABILITY_CLASSES)},
        "enum_values_without_registry_entry": sorted(set(enum) - reg_ids),
        "registry_entries_without_enum_value": sorted(reg_ids - set(enum)),
        "carriers_note": ("`carriers` ventile les porteurs par `kind` du gameconfig. Ce n'est PAS "
                          "une gate de spawnabilite : la gate HERO/MoW est `rl_duel build "
                          "--list-pool`, et une absence du pool se leve par injection catalogue."),
        "rows": rows}, indent=1), encoding="utf-8")
    print("")
    print("tables -> %s" % tsv)
    print("       -> %s" % js)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="interroge ghidra-mcp -> logs/probe_302_4_raw.json")
    p.add_argument("--refresh", action="store_true",
                   help="ignore le brut precedent (sinon les corps deja decompiles sont repris)")
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("report", help="offline : brut -> tables + compte ventile")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("all", help="scan puis report")
    p.set_defaults(func=lambda a: cmd_scan(a) or cmd_report(a))
    args = ap.parse_args()
    try:
        return args.func(args)
    except GhidraDown as exc:
        print("ERREUR : %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
