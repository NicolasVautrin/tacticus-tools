"""probe #281 -- INVENTAIRE du raccourci `execute_behaviour` et de ses montages FAUX.

Residu #277-r1. #277 a etabli (et ce probe ne le re-prouve pas) qu'appeler
`<X>Ability().execute_behaviour(...)` A LA MAIN court-circuite
`AbilityHandler.visit_ActiveAbilityMessage`, donc l'emission de `On(PreUnitAbility)` que le
natif place TOUT EN HAUT d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`.
Le raccourci n'est FAUX que si le CASTER du montage porte un consommateur NON INERTE de ce
vecteur -- c'est le caster qui decide, pas le call-site.

Ce probe repond a trois questions, chacune re-derivee, aucune heritee d'un rapport :

  --step natif     : QUI s'abonne a `On(PreUnitAbility)` dans GameAssembly.dll ?
                     Scan BINAIRE exhaustif du `.text` : tout `call` vers l'un des overloads de
                     `IdunBattleLogic.Entities.DSLTriggers$$On` dont l'argument `edx` (2e param =
                     l'EventTriggerType) vaut l'ordinal de PreUnitAbility. Exhaustif par
                     construction -- contrairement a un grep de decompile, qui depend du
                     formatage ghidra.
  --step port      : QUI s'abonne a `EventTriggerType.PreUnitAbility` dans le PORT, et quels
                     UNIT IDS portent ces triggers (registre de spawn + gameconfig).
  --step callsites : OU le raccourci est pris (AST, tout `scripts/python` hors moteur), et quel
                     CASTER chaque montage utilise reellement.
  --step classify  : le croisement -> SAIN / A CORRIGER, montage par montage.

ATTENTION AUX ORDINAUX. Le decompile passe `0x2a` et l'enum porte vaut
`EventTriggerType.PreUnitAbility = 42 = 0x2a`. Plusieurs docstrings du port ecrivent
"0x2b = 43" : c'est une erreur de transcription (43 = `UnitHealed`). Ce probe ne code AUCUN
ordinal en dur -- il lit `engine.dsl.event_trigger_type.EventTriggerType`.

Sortie ASCII stricte (console cp1252).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

REPO = HERE.parent.parent

# ---------------------------------------------------------------------------
# etape NATIF : scan binaire du .text
# ---------------------------------------------------------------------------

SYMBOL_ON = "IdunBattleLogic.Entities.DSLTriggers$$On"

# Les DEUX autres voies par lesquelles un ordinal d'EventTriggerType atteint un trigger. Elles ne
# sont PAS optionnelles : sans elles le scan rate `AnvilShieldAbility_FrozenAttackerAdvantage` et
# `ATeleportingEffect`, et le tri classerait « sain » un montage faux.
#
#  * `TRIGGER_CTOR` : ctor d'objet trigger appele INLINE, `(obj, <ordinal>, <flag>)`. Ghidra le
#    nomme `Stash.Native.StashNative.u003COpenCardOrModalInternalu003Ed__46$$.ctor` -- un corps
#    trivial DEDUPLIQUE ; le nom ne veut RIEN dire. Ce qui l'identifie est la distribution de son
#    2e argument sur ses 361 sites : elle epouse `EventTriggerType` (UnitDeath=0 x224,
#    PreUnitDeath=1, Attack=9, TurnEnd=23...), verifiee par `--step natif --verbose`.
#  * `BASE_EFFECT_ON` : `IdunBattle.Entities.Effects.BaseEffect$$On(this, eventTrigger)`, simple
#    RELAIS vers `DSLTriggers$$On` -- l'ordinal vient de SON appelant, dans le meme registre (edx).
TRIGGER_CTOR = "Stash.Native.StashNative.u003COpenCardOrModalInternalu003Ed__46$$.ctor"
BASE_EFFECT_ON = "IdunBattle.Entities.Effects.BaseEffect$$On"


def _build_hash() -> str:
    """Hash du build INSTALLE, confronte a la table de symboles (regle CLAUDE.md : si les deux
    ne matchent pas, on REFUSE l'analyse offline plutot que de croiser un mauvais dump)."""
    games = Path(os.environ["LOCALAPPDATA"]) / "tacticus" / "games"
    installed = sorted(d.name for d in games.iterdir() if (d / "GameAssembly.dll").exists())
    have = sorted(d.name for d in (REPO / "data" / "symbols").iterdir()
                  if (d / "ghidra" / "functions.tsv").exists())
    common = [h for h in installed if h in have]
    if not common:
        raise SystemExit("aucun build commun entre le jeu %s et data/symbols %s"
                         % (installed, have))
    if len(common) > 1:
        raise SystemExit("ambigu : plusieurs builds communs %s" % common)
    return common[0]


def _game_dll(build: str) -> Path:
    p = Path(os.environ["LOCALAPPDATA"]) / "tacticus" / "games" / build / "GameAssembly.dll"
    if not p.exists():
        raise SystemExit("GameAssembly.dll absent for build %s -- refus d'analyser offline" % build)
    return p


def _load_functions(build: str) -> list[tuple[int, str]]:
    """functions.tsv = `<adresse hex>\\t<symbole>`, trie par adresse croissante."""
    tsv = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out: list[tuple[int, str]] = []
    with tsv.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                out.append((int(parts[0], 16), parts[1]))
            except ValueError:
                continue
    out.sort()
    return out


class _PE:
    """Lecteur PE minimal : mapping VA <-> offset fichier, sections. Aucune VA en dur."""

    def __init__(self, path: Path):
        self.buf = path.read_bytes()
        e_lfanew = struct.unpack_from("<I", self.buf, 0x3C)[0]
        assert self.buf[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE"
        coff = e_lfanew + 4
        n_sec = struct.unpack_from("<H", self.buf, coff + 2)[0]
        opt_size = struct.unpack_from("<H", self.buf, coff + 16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", self.buf, opt)[0]
        assert magic == 0x20B, "expected PE32+"
        self.image_base = struct.unpack_from("<Q", self.buf, opt + 24)[0]
        sec_off = opt + opt_size
        self.sections = []
        for i in range(n_sec):
            s = sec_off + i * 40
            name = self.buf[s:s + 8].rstrip(b"\0").decode("ascii", "replace")
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", self.buf, s + 8)
            chars = struct.unpack_from("<I", self.buf, s + 36)[0]
            self.sections.append((name, vaddr, vsize, raddr, rsize, chars))

    def code_sections(self):
        """Toutes les sections EXECUTABLES (`IMAGE_SCN_MEM_EXECUTE`).

        Sur ce binaire le code manage IL2CPP vit dans la section `il2cpp` (~41 Mo), PAS dans
        `.text` (~2,8 Mo) : ne scanner que `.text` rendait 0 site -- un faux « aucun abonne ».
        """
        out = []
        for name, vaddr, vsize, raddr, rsize, chars in self.sections:
            if chars & 0x20000000:                            # IMAGE_SCN_MEM_EXECUTE
                out.append((name, vaddr, min(vsize, rsize), raddr))
        if not out:
            raise SystemExit("no executable section")
        return out


def _resolve_on_overloads(funcs: list[tuple[int, str]]) -> list[int]:
    return sorted(a for a, n in funcs if n == SYMBOL_ON)


def _owner_of(funcs: list[tuple[int, str]], va: int) -> str:
    """Symbole de la fonction CONTENANTE (dernier symbole <= va)."""
    lo, hi = 0, len(funcs) - 1
    best = "?"
    while lo <= hi:
        mid = (lo + hi) // 2
        if funcs[mid][0] <= va:
            best = funcs[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def scan_native_subscribers(ordinal: int, verbose: bool = False,
                            any_callee: bool = False) -> list[dict]:
    """Sites d'abonnement natifs a `On(<ordinal>)`.

    Deux voies, et la seconde a failli etre manquee :

    1. `call <overload de DSLTriggers$$On>` precede d'un `mov edx, <ordinal>` -- la voie
       « normale » (ex. `HazeOfCorruption_TargetFinderAbility$$CreateTrigger`).
    2. **ctor de trigger INLINE** : la fonction alloue l'objet trigger et appelle son `.ctor`
       avec `(obj, <ordinal>, <flag>)`, SANS passer par `DSLTriggers$$On`. C'est le cas de
       `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`
       (ghidra mislabel le ctor en `Stash_Native_...u003COpenCardOrModalInternalu003Ed__46___ctor`
       -- corps trivial DEDUPLIQUE : ne JAMAIS se fier a ce nom). Un scan limite a la voie 1
       rend ce trigger INVISIBLE et classerait « sain » tout montage dont le caster le porte.

    `any_callee=True` active la voie 2 : tout `mov edx, <ordinal>` suivi d'un `call rel32`
    proche, quelle que soit la cible. Le tri se fait alors sur la fonction CONTENANTE (celle
    qui construit le trigger), jamais sur le nom de la cible.
    """
    build = _build_hash()
    funcs = _load_functions(build)
    targets = set(_resolve_on_overloads(funcs))
    if not targets:
        raise SystemExit("symbole %s introuvable dans functions.tsv" % SYMBOL_ON)
    ctor = {a for a, n in funcs if n == TRIGGER_CTOR}
    relay = {a for a, n in funcs if n == BASE_EFFECT_ON}
    if any_callee:
        targets = targets | ctor | relay
    kind = {}
    for a in targets:
        kind[a] = "ctor" if a in ctor else ("relais" if a in relay else "On")
    pe = _PE(_game_dll(build))
    base = pe.image_base

    hits: list[dict] = []
    calls_to_on = 0
    scanned = 0
    for name, vaddr, size, raddr in pe.code_sections():
        text = pe.buf[raddr:raddr + size]
        text_va = base + vaddr
        scanned += len(text)
        i = 0
        n = len(text)
        while i < n - 5:
            if text[i] == 0xE8:                              # call rel32
                rel = struct.unpack_from("<i", text, i + 1)[0]
                dst = text_va + i + 5 + rel
                if dst in targets:
                    calls_to_on += 1
                    imm = _last_edx_write(text, i)
                    if imm == ordinal:
                        site = text_va + i
                        hits.append({"site_va": site, "owner": _owner_of(funcs, site),
                                     "target": dst, "target_sym": _owner_of(funcs, dst),
                                     "voie": kind[dst], "section": name})
                i += 5
                continue
            i += 1
    if verbose:
        print("  [scan] %d octets executables, %d cible(s) d'abonnement (On/ctor/relais), "
              "%d call-sites vers elles, %d retenus (edx == %d)"
              % (scanned, len(targets), calls_to_on, len(hits), ordinal))
    return hits


def _last_edx_write(text: bytes, call_off: int) -> int | None:
    """Dernier IMMEDIAT ecrit dans edx avant `call_off`, ou None si edx vient d'ailleurs.

    Le balayage repart de `call_off` VERS L'ARRIERE et s'arrete au premier `call` rencontre :
    un `call` clobbe rdx (volatile dans l'ABI Win64), donc un `mov edx, imm` situe AVANT lui
    ne dit rien de la valeur passee. Sans cette borne, on attribue a un site l'immediat d'un
    site voisin -- 350/350 sites « resolus » dont plusieurs a tort, et les WRAPPERS
    (`BaseEffect$$On`, qui relaie le type recu en parametre) passent inapercus.
    """
    start = max(0, call_off - 64)
    j = call_off - 1
    while j >= start:
        # `mov edx, imm32` = BA imm32, cadre exactement sur les 5 octets precedant un point
        if j >= 4 and text[j - 4] == 0xBA:
            # candidat : verifier qu'aucun call n'a lieu entre la fin du mov et call_off
            end_mov = j + 1
            if _has_call_between(text, end_mov, call_off):
                return None
            return struct.unpack_from("<I", text, j - 3)[0]
        if j >= 1 and text[j - 1] in (0x33, 0x31) and text[j] == 0xD2:   # xor edx, edx
            if _has_call_between(text, j + 1, call_off):
                return None
            return 0
        j -= 1
    return None


def _has_call_between(text: bytes, start: int, end: int) -> bool:
    k = start
    while k < end - 4:
        if text[k] == 0xE8:
            return True
        k += 1
    return False


# ---------------------------------------------------------------------------
# etape PORT : qui ecoute PreUnitAbility cote Python, et qui le PORTE
# ---------------------------------------------------------------------------

def port_subscribers() -> list[dict]:
    """Triggers PORTES dont l'`event_id` vaut `EventTriggerType.PreUnitAbility`.

    On IMPORTE les modules de triggers et on lit l'attribut de classe `event_id` -- pas un grep :
    une classe qui NOMME `PreUnitAbility` dans une docstring sans y etre abonnee serait comptee a
    tort, et une classe qui herite son `event_id` d'une base serait manquee.
    """
    import importlib
    import inspect
    import pkgutil
    from engine.dsl.event_trigger_type import EventTriggerType
    import engine.runner.operations.triggers as pkg

    ordinal = int(EventTriggerType.PreUnitAbility)
    out: list[dict] = []
    for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            mod = importlib.import_module(m.name)
        except Exception:
            continue
        for nm, obj in vars(mod).items():
            if not inspect.isclass(obj) or obj.__module__ != m.name:
                continue
            ev = getattr(obj, "event_id", None)
            # `event_id` peut etre un slot non lie (`member_descriptor`) sur une base abstraite :
            # seule une valeur CONCRETE de classe compte comme abonnement.
            if not isinstance(ev, int) or ev != ordinal:
                continue
            out.append({"module": m.name, "cls": nm, "ordinal": ordinal})
    return out


# ---------------------------------------------------------------------------
# etape PORTEURS : quelles UNITES portent un consommateur de PreUnitAbility
# ---------------------------------------------------------------------------

# Familles natives abonnees a `On(PreUnitAbility)`, re-derivees par `--step natif` (scan
# binaire exhaustif). La cle est le prefixe d'ability tel qu'il apparait dans le kit
# gameconfig ; la valeur dit ce que le trigger FAIT quand il part -- c'est ce qui decide si le
# raccourci est faux, pas le simple fait d'ecouter l'evenement.
NATIVE_CONSUMERS = {
    "HazeOfCorruption": "RNG (PickRandomly dans CreateBehaviour) -- decale le flux",
    "SwornProtector": "deplacement d'unite (switch protecteur) + summon",
    "MartialSuperiority": "riposte AttackWithAttackDamage (2 coups Power)",
    "AnvilShield": "stat-mod block (+20 %) pose AVANT le calcul du block",
    "SavageKiller": "cible initiale / trigger d'active",
    "FuryFromTheDelve": "trigger d'ability",
    "StandVigil": "mise a jour de portee d'effet",
}

# Le GATE D'ATTAQUE de chaque famille, lu au decompile. C'est LUI qui decide si le raccourci est
# faux, pas le simple abonnement : `execute_behaviour` est TOUJOURS une voie de CAST d'ability, donc
# une famille gatee `IsNormalAttack` ne peut structurellement pas partir sur ce chemin.
#
#   HazeOfCorruption   : `On(PreUnitAbility, 1) & get_OwnerIsCaster`  -- AUCUN gate d'attaque
#   FuryFromTheDelve   : `... & IsNormalAttack & get_OwnerIsActor`    -- jamais sur un cast
#   AnvilShield        : `... & IsNormalAttack & get_OwnerIsTarget`   -- jamais sur un cast
#   SwornProtector*    : `... & (AbilityHasAttackType(0)|AbilityHasAttackType(1)) & ...`
#   MartialSuperiority : `... & IsDirectTargetAttack(@0x130) & OwnerOrOwnerTileIsTarget
#                          & NOT IsTurnOf(Owner) & IsMeleeAttack`
#   SavageKiller / StandVigil : non portes (aucun consommateur cote Python)
#
# `role` = QUI doit porter la famille pour que le trigger parte : le caster, la cible, ou un ennemi.
FAMILY_GATE = {
    "HazeOfCorruption": {"role": "caster", "attack_gate": None, "ported": True},
    "SwornProtector": {"role": "ennemi du caster", "attack_gate": "AbilityHasAttackType(0|1)",
                       "ported": True},
    "MartialSuperiority": {"role": "cible", "attack_gate": "IsDirectTargetAttack + melee adjacent"
                                                           " + tour adverse", "ported": True},
    "AnvilShield": {"role": "cible", "attack_gate": "IsNormalAttack", "ported": True},
    "FuryFromTheDelve": {"role": "acteur", "attack_gate": "IsNormalAttack", "ported": False},
    "SavageKiller": {"role": "cible (ConditionalSelector)", "attack_gate": None, "ported": False},
    "StandVigil": {"role": "porteur d'effet", "attack_gate": None, "ported": False},
}

# TROIS abonnes de plus, sans porteur de KIT : ce sont des EFFETS, portes par l'unite qui les
# RECOIT -- donc introuvables par une intersection sur `gameconfig.abilities`. Aucun n'est porte
# cote Python, donc aucun n'agit sur un rejeu offline ; ils sont nommes ici pour que le prochain
# lecteur n'ait pas a re-scanner :
#   `Idun_MeleeCounterAttackEffect$$GetTriggerType`             -- branche `On(0x2a = PreUnitAbility) & IsNormalAttack`
#                                                                  (l'autre branche est `On(0x11)`)
#   `Loki.JustSummonedEffect$$CreateRemoveEffectTrigger`        -- retrait de l'effet « fraichement
#                                                                  invoque »
#   `Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` -- via le RELAIS `BaseEffect$$On`
EFFECT_SUBSCRIBERS_NO_KIT_CARRIER = (
    "IdunBattle.Entities.Effects.Idun_MeleeCounterAttackEffect$$GetTriggerType",
    "IdunBattle.Entities.Effects.Loki.JustSummonedEffect$$CreateRemoveEffectTrigger",
    "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal",
)

# Familles qui rendent le raccourci faux SANS condition sur la nature de l'ability : porteur en
# position de CASTER + aucun gate d'attaque. Aujourd'hui une seule -- c'est le gisement du cliquet.
UNCONDITIONAL = sorted(f for f, g in FAMILY_GATE.items()
                       if g["attack_gate"] is None and g["role"] == "caster" and g["ported"])

# Montages TOLERES par le gate, avec la raison. Une entree DOIT citer pourquoi le raccourci y est
# inoffensif ; une entree devenue inutile est signalee (pas bloquante) plutot que silencieuse.
GATE_ALLOWLIST = {
    ("probe_281_pre_unit_ability_shortcut.py", "measure_flail"):
        "le raccourci y est pris EXPRES, comme terme de comparaison anti-tautologique : c'est la "
        "voie dont on MESURE qu'elle diverge du live quand le pool Haze n'est pas vide",
    ("probe_277_flail_damage_stages.py", "_replay"):
        "raccourci PRIS EXPRES : c'est la colonne `direct` de la decomposition par etage de "
        "#277, celle dont on MESURE qu'elle saute les tirages amont",
    ("tests/engine/runner/test_flail_swing_live.py",
     "test_flail_swing_cast_entry_point_haze_pool_live"):
        "raccourci PRIS EXPRES : le volet (4) de #277 exige `direct != live` (anti-tautologie). "
        "Le router VIDERAIT le test de son contenu",
    ("tests/engine/runner/test_ability_hits_channel_live.py", "_frenzy_offline"):
        "le caster de CE call-site est `FRENZY_VIS = blackObliterator` ; `deathBlightlord` est la "
        "constante `CASTER_VIS` d'AUTRES volets du meme fichier (qui, eux, ne prennent pas le "
        "raccourci). Faux positif de l'heuristique 'constantes de module'",
}


def carriers() -> dict[str, list[str]]:
    """Unites gameconfig dont le kit contient une ability d'une famille consommatrice."""
    import unit_map
    kits = unit_map.all_kits()
    out: dict[str, list[str]] = {}
    for fam in NATIVE_CONSUMERS:
        low = fam.lower()
        # `abilities_all` et non `abilities` (#323) : la seconde n'est que active+passive, et un
        # recensement de PORTEURS qui ignore les voies relique/mythique rend des « 0 porteur »
        # faux -- exactement ce qui a fait classer l'effet 1456 DEAD (#310 -> #317 -> #323).
        out[fam] = sorted(k["id"] for k in kits
                          if any(low in a.lower() for a in k.get("abilities_all", []) or []))
    return out


# ---------------------------------------------------------------------------
# etape CALLSITES : AST des montages + caster reellement utilise
# ---------------------------------------------------------------------------

def _unit_ids() -> set[str]:
    import unit_map
    return {k["id"] for k in unit_map.all_kits()}


class _CallSiteVisitor(ast.NodeVisitor):
    """Repere `<qqch>.execute_behaviour(...)` hors `self.`/`super()`, et note la fonction
    contenante -- c'est dans SON corps que se lisent les unit ids du montage."""

    def __init__(self):
        self.stack: list[str] = []
        self.sites: list[dict] = []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "execute_behaviour":
            recv = f.value
            skip = (isinstance(recv, ast.Name) and recv.id in ("self", "super")) or (
                isinstance(recv, ast.Call) and isinstance(recv.func, ast.Name)
                and recv.func.id == "super")
            if not skip:
                self.sites.append({"lineno": node.lineno,
                                   "func": self.stack[-1] if self.stack else "<module>",
                                   "recv": ast.unparse(recv)})
        self.generic_visit(node)


def scan_callsites() -> list[dict]:
    """Tous les call-sites `execute_behaviour` des MONTAGES (probes + tests), avec les unit ids
    que le montage cite -- d'abord dans la fonction contenante, a defaut dans le fichier.

    `scripts/python/engine/**` est EXCLU : c'est le moteur, ou l'appel est la voie normale
    (le handler appelle la behaviour APRES avoir emis le vecteur). `scripts/python/tests/**`
    est INCLUS -- piege mesure : ces chemins contiennent le segment `engine` (`tests/engine/
    runner/...`), donc un filtre naif `path ne contient pas 'engine'` les efface tous.
    """
    root = REPO / "scripts" / "python"
    engine_root = root / "engine"
    ids = _unit_ids()
    out: list[dict] = []
    for py in sorted(root.rglob("*.py")):
        try:
            py.relative_to(engine_root)
            continue                                          # moteur -> voie normale
        except ValueError:
            pass
        src = py.read_text(encoding="utf-8", errors="replace")
        if "execute_behaviour" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        v = _CallSiteVisitor()
        v.visit(tree)
        if not v.sites:
            continue
        file_ids = sorted({s for s in _string_literals(tree) if s in ids})
        # Les constantes de MODULE comptent comme unites du montage : le caster est tres souvent
        # une constante top-level (`CASTER_VIS = "deathBlightlord"`), invisible depuis le corps de
        # la fonction. Sans elles, `test_flail_swing_live.py` -- dont le caster EST un porteur
        # HazeOfCorruption -- ressortait « sain ».
        mod_ids = sorted({s for n in tree.body
                          if isinstance(n, (ast.Assign, ast.AnnAssign))
                          for s in _string_literals(n) if s in ids})
        func_ids: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_ids[node.name] = sorted({s for s in _string_literals(node) if s in ids})
        for s in v.sites:
            s["file"] = str(py.relative_to(root)).replace("\\", "/")
            s["file_units"] = file_ids
            s["module_units"] = mod_ids
            s["func_units"] = sorted(set(func_ids.get(s["func"], [])) | set(mod_ids))
            out.append(s)
    return out


def _string_literals(tree) -> set[str]:
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def classify() -> list[dict]:
    """Trois verdicts, et la nuance porte tout le tri :

      A CORRIGER  : le montage cite un porteur d'une famille INCONDITIONNELLE (`UNCONDITIONAL`)
                    dans son perimetre (fonction + constantes de module). Le raccourci y est faux
                    des que ce porteur caste.
      A EXAMINER  : le montage cite un porteur d'une famille CONDITIONNELLE (gate `IsNormalAttack`,
                    `AbilityHasAttackType`, role cible/ennemi...). Le raccourci n'y est faux que si
                    le role ET le gate sont tenus -- indecidable statiquement, donc on NOMME au
                    lieu de trancher.
      SAIN        : aucun porteur cite. Attention : « aucun porteur cite » n'est une preuve que si
                    le montage NOMME ses unites ; ceux qui n'en citent aucune sont marques
                    INDETERMINE.
    """
    car = carriers()
    by_unit: dict[str, list[str]] = {}
    for fam, units in car.items():
        for u in units:
            by_unit.setdefault(u, []).append(fam)
    rows = []
    for s in scan_callsites():
        units = s["func_units"]
        fams = sorted({f for u in units for f in by_unit.get(u, [])})
        hot = sorted({u for u in units if u in by_unit})
        if set(fams) & set(UNCONDITIONAL):
            verdict = "A CORRIGER"
        elif fams:
            verdict = "A EXAMINER"
        elif not s["file_units"]:
            verdict = "INDETERMINE"
        else:
            verdict = "SAIN"
        rows.append({**s, "carriers": hot, "families": fams, "verdict": verdict})
    return rows


# ---------------------------------------------------------------------------
# etape MESURE (LIVE) : l'ecart du montage `test_flail_swing_live.py`, deux regimes
# ---------------------------------------------------------------------------

FLAIL_ABILITY = 1042
FLAIL_CASTER = "deathBlightlord"            # `CASTER_VIS` du montage -- porteur `HazeOfCorruption`
FLAIL_A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"
HAZE_BOND_TRIGGER = 1076                    # `Effect_SourceTriggeredAbility` des bonds Haze


def _genrand_steps(before, after, limit=200):
    """Tirages `genrand_int32` consommes par le NATIF entre deux `dumpRng` (re-simulation du
    Mersenne Twister depuis `before` jusqu'a retomber sur `after`). -1 = non retrouve."""
    from engine.runner.prng import IntBasedMersenneTwister
    m = IntBasedMersenneTwister()
    m.mt = list(before["mt"]); m.mti = before["mti"]
    tgt = (list(after["mt"]), after["mti"])
    for k in range(limit + 1):
        if (m.mt, m.mti) == tgt:
            return k
        m.genrand_int32()
    return -1


def _counting_rng(s):
    """PRNG cale sur l'etat live + COMPTEUR de tirages -- l'observable de l'etage AMONT."""
    from engine.runner.prng import IntBasedMersenneTwister
    box = [0]

    class _Counting(IntBasedMersenneTwister):
        __slots__ = ()

        def genrand_int32(self):
            box[0] += 1
            return IntBasedMersenneTwister.genrand_int32(self)

    r = _Counting()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r, box


def measure_flail(regime: str, seed: str = "777", hp: str = "90000") -> int:
    """Monte le montage du volet (1) de `test_flail_swing_live.py` et confronte, sur le MEME etat
    et le MEME flux, les deux voies de rejeu offline au LIVE.

    `regime = far`  : geometrie ACTUELLE du test (le 2e ennemi a distance > 1 du caster) -> le pool
                      `AdjacentEnemies(Self) & AdjacentFriends(Target)` est VIDE, aucun tirage amont.
    `regime = near` : le 2e ennemi place ADJACENT au caster ET a la cible -> pool = 1 candidat, donc
                      1 tirage amont paye par `On(PreUnitAbility)`. C'est la geometrie que le test
                      ne produit pas, et qui rend le raccourci FAUX.
    """
    import subprocess
    import uuid
    from rl_collect_batch import _resolve_session, _rpc
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.abilities.deathguard import FlailSwingAbility

    pydir = REPO / "scripts" / "python"
    sid = _resolve_session()

    def r(m, b, t=90):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    sf = REPO / "logs" / "runners" / ("p281-%s-%s.json" % (regime, uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", FLAIL_CASTER,
         "--a-units", FLAIL_A_UNITS, "--hp-target", hp, "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(pydir), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("build KO : %s" % (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = int(json.loads(sf.read_text())["runnerId"])
    try:
        bg = r("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return r("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        def find(dv, vis):
            return next((u for u in (dv.get("units") or [])
                         if u.get("visualId") == vis and u.get("alive")), None)

        myp = None
        for _ in range(20):
            dv = dview()
            c = find(dv, FLAIL_CASTER)
            if c is None:
                print("caster absent du build")
                return 1
            myp = c.get("owner")
            if dv.get("currentPlayer") == myp:
                break
            r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        dv = dview()
        c = find(dv, FLAIL_CASTER)
        cid = c["id"]
        cpos = (c["pos"]["col"], c["pos"]["row"])
        ctile = board.id_at(*cpos)
        tgt = find(dv, "necroWarden")
        sec = find(dv, "necroOverlord")
        keep = {tgt["id"], sec["id"]}
        far = [t for t in sorted(board.by_id)
               if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
        it = iter(far)
        for e in (u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")):
            if e["id"] in keep:
                continue
            ft = next(it, None)
            if ft is None:
                break
            r("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": e["id"],
                "to": {"col": board.coord(ft)[0], "row": board.coord(ft)[1]}}}, 60)
        nbrs = [n for n in board.neighbours(ctile) if board.walkable(n)]
        tcoord = board.coord(nbrs[0])
        r("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt["id"], "to": {"col": tcoord[0], "row": tcoord[1]}}}, 60)
        # le SEUL parametre du regime : la distance du 2e ennemi AU CASTER
        want_near = (regime == "near")
        cand = [n for n in board.neighbours(board.id_at(*tcoord))
                if board.walkable(n) and board.coord(n) != cpos
                and ((hexgeo.distance(board.coord(n), cpos) == 1) if want_near
                     else (hexgeo.distance(board.coord(n), cpos) > 1))]
        if not cand:
            print("regime %s : aucune tuile candidate pour le 2e ennemi" % regime)
            return 1
        sc = board.coord(cand[0])
        r("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sec["id"], "to": {"col": sc[0], "row": sc[1]}}}, 60)

        at = r("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": FLAIL_ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == FLAIL_ABILITY), {})
        fh = [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]
        if tgt["id"] not in fh:
            print("cast illegal dans le regime %s" % regime)
            return 1
        tid = tgt["id"]

        dv2 = dview()
        ob2 = r("observeBattle", {"runnerId": rid}, 60)
        snap2 = r("combatSnapshot", {"runnerId": rid}, 90)
        s0 = r("dumpRng", {"runnerId": rid}, 30)

        cast = r("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": FLAIL_ABILITY},
            "captureEvents": True}, 150)
        s1 = r("dumpRng", {"runnerId": rid}, 30)
        live, bonds = [], 0
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if td.get("Effect_SourceTriggeredAbility") == HAZE_BOND_TRIGGER:
                    bonds += 1
                if "Amount" in td and td.get("Target_Id") == tid \
                        and td.get("Active_Ability_Type") == FLAIL_ABILITY:
                    live.append(int(td["Amount"]))
        n_native = _genrand_steps(s0, s1)

        st_d = load_state(dv2, ob2, snap2, board=board)
        st_d.rng, box_d = _counting_rng(s0)
        direct = list((((FlailSwingAbility().execute_behaviour(st_d, cid, tid) or {})
                        .get("attack") or {}).get("per_hit")) or [])

        st_p = load_state(dv2, ob2, snap2, board=board)
        st_p.rng, box_p = _counting_rng(s0)
        runner = Runner(st_p).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(cid, tid, FLAIL_ABILITY))
        pipe = list((((getattr(runner.ability_handler, "last", None) or {})
                      .get("attack") or {}).get("per_hit")) or [])

        d_cs = hexgeo.distance(sc, cpos)
        print("[%s] d(caster, 2e ennemi) = %d | bonds natifs = %d | genrand natif = %d"
              % (regime, d_cs, bonds, n_native))
        print("[%s] tirages : raccourci = %d | production = %d" % (regime, box_d[0], box_p[0]))
        print("[%s] live       = %s" % (regime, live))
        print("[%s] raccourci  = %s   %s" % (regime, direct, "OK" if direct == live else "ECART"))
        print("[%s] production = %s   %s" % (regime, pipe, "OK" if pipe == live else "ECART"))
        if live and direct != live:
            print("[%s] ecart raccourci/live : somme %d vs %d (%+.2f %%)"
                  % (regime, sum(direct), sum(live),
                     100.0 * (sum(direct) - sum(live)) / float(sum(live))))
        return 0
    finally:
        try:
            r("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="natif",
                    choices=["natif", "port", "callsites", "classify", "mesure"])
    ap.add_argument("--regime", default="near", choices=["near", "far"],
                    help="mesure : geometrie du 2e ennemi (near = pool Haze non vide)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.step == "mesure":
        return measure_flail(args.regime, seed=args.seed)

    if args.step == "natif":
        from engine.dsl.event_trigger_type import EventTriggerType
        ordinal = int(EventTriggerType.PreUnitAbility)
        print("[natif] EventTriggerType.PreUnitAbility = %d (0x%x)" % (ordinal, ordinal))
        hits = scan_native_subscribers(ordinal, verbose=args.verbose, any_callee=True)
        by_owner: dict[str, dict] = {}
        for h in hits:
            row = by_owner.setdefault(h["owner"], {"n": 0, "voies": set()})
            row["n"] += 1
            row["voies"].add(h["voie"])
        print("[natif] %d site(s) d'abonnement dans %d fonction(s) contenantes"
              % (len(hits), len(by_owner)))
        for owner in sorted(by_owner):
            print("   [%-6s] %-98s x%d"
                  % ("/".join(sorted(by_owner[owner]["voies"])), owner, by_owner[owner]["n"]))
        return 0

    if args.step == "port":
        for row in port_subscribers():
            print("%-70s %s" % (row["cls"], row["module"]))
        return 0

    if args.step == "callsites":
        rows = scan_callsites()
        files = sorted({r["file"] for r in rows})
        print("[callsites] %d call-site(s) `execute_behaviour` de MONTAGE dans %d fichier(s)"
              % (len(rows), len(files)))
        for r in rows:
            print("   %-62s:%-5d %-34s recv=%s" % (r["file"], r["lineno"], r["func"], r["recv"]))
            print("        units(func)=%s" % (r["func_units"] or r["file_units"]))
        return 0

    if args.step == "classify":
        car = carriers()
        print("[porteurs] familles natives abonnees a On(PreUnitAbility), gate d'attaque et role :")
        for fam in sorted(car):
            g = FAMILY_GATE[fam]
            print("   %-20s role=%-16s gate=%-42s porte=%-5s %s"
                  % (fam, g["role"], str(g["attack_gate"]), g["ported"], car[fam]))
        print("   -> familles INCONDITIONNELLES (porteur caster, aucun gate d'attaque) : %s"
              % UNCONDITIONAL)
        rows = classify()
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        print()
        print("[classify] %d call-site(s) de montage : %s"
              % (len(rows), ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts))))
        blocking = []
        for r in rows:
            if r["verdict"] not in ("A CORRIGER", "A EXAMINER", "INDETERMINE"):
                continue
            key = (r["file"], r["func"])
            allowed = GATE_ALLOWLIST.get(key)
            tag = r["verdict"]
            if r["verdict"] == "A CORRIGER" and allowed is None:
                blocking.append(r)
            print("   %-11s %-52s:%-5d %s" % (tag, r["file"], r["lineno"], r["func"]))
            if r["carriers"]:
                print("        porteurs cites : %s -> familles %s" % (r["carriers"], r["families"]))
            if allowed:
                print("        TOLERE : %s" % allowed)
        used = {(r["file"], r["func"]) for r in rows if r["verdict"] == "A CORRIGER"}
        for key in sorted(set(GATE_ALLOWLIST) - used):
            print("   [allowlist obsolete] %s::%s -- l'entree peut etre retiree" % key)
        print()
        if blocking:
            print("GATE ROUGE : %d montage(s) prennent le raccourci avec un caster porteur d'une "
                  "famille inconditionnelle %s" % (len(blocking), UNCONDITIONAL))
            return 1
        print("GATE VERT : aucun montage ne prend le raccourci avec un caster porteur de %s "
              "(hors allowlist documentee)" % UNCONDITIONAL)
        return 0

    print("step %s : pas encore implemente" % args.step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
