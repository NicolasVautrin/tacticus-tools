"""#193 - INVENTAIRE re-derivable du gisement « playbooks de MOUVEMENT ».

Derive les DEUX faces du compte, offline, depuis les entrees VERSIONNEES du depot :

* face NATIVE  : `data/symbols/<build>/frida/classes.tsv` (dump metadata IL2CPP).
  Deux populations distinctes, a ne PAS confondre :
    - CORPS PROPRE  : la classe possede son iterateur imbrique
      `<CalculateMovementUtilityInStepsInternal>d__N` -> elle a un corps a elle.
    - CORPS HERITE  : la classe derive (transitivement) de
      `IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` SANS iterateur
      propre -> elle partage le corps commun et n'override que
      `GetAdjacent{Friend,Enemy}Utility` (3 lignes chacune).
  Le chiffre herite « 84 » ne comptait QUE la 1re population. La 2e est invisible dans
  `methods.tsv` / `functions.tsv` (corps DEDUPLIQUE, tables indexees par ADRESSE) : c'est
  `classes.tsv` — indexe par NOM — qui est la seconde source independante.

* face PORT    : le registre `TRIGGERED_MOVE_PLAYBOOKS` de
  `engine/playbook/adjacent_unit_preference.py`, importe pour de vrai (pas grep).

Usage :
  python probe_193_move_playbook_inventory.py                 # les deux chiffres + le delta
  python probe_193_move_playbook_inventory.py --list          # la liste des manquants
  python probe_193_move_playbook_inventory.py --json <path>   # dump machine (pour la doc)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SYMBOLS = _REPO / "data" / "symbols"

ITER_MARK = ".<CalculateMovementUtilityInStepsInternal>d__"
ADJ_BASE = "IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook`1"


def build_hash() -> str:
    """Hash du build qui FAIT FOI (`data/symbols/CURRENT`) -- cf. `symbols_layout.py`.
    Exigeait auparavant un repertoire unique, ce qui cassait des qu'un build archive
    trainait a cote (on les conserve EXPRES, pour le diff inter-build)."""
    from symbols_layout import current_build
    return current_build()


def load_classes(h: str) -> dict[str, str]:
    """nom de classe -> nom du parent (col 3 de classes.tsv)."""
    p = _SYMBOLS / h / "frida" / "classes.tsv"
    out: dict[str, str] = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#!"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 3:
                out[cols[0]] = cols[2]
    return out


def load_enum(h: str, enum_name: str) -> dict[str, int]:
    """`enums.tsv` : <nom complet>\\t<v=NAME,v=NAME,...>. Rend NAME -> valeur."""
    p = _SYMBOLS / h / "frida" / "enums.tsv"
    with p.open(encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols and cols[0] == enum_name:
                out: dict[str, int] = {}
                for pair in cols[1].split(","):
                    v, _, n = pair.partition("=")
                    if n and n not in out:
                        out[n] = int(v)
                return out
    raise SystemExit("enum introuvable: %s" % enum_name)


def load_bc() -> dict[str, dict[str, float]]:
    bc = json.loads((_REPO / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    return bc.get("Utilities", {}).get("Default", {}) or {}


def ancestors(cls: str, parents: dict[str, str]) -> list[str]:
    out, seen, cur = [], set(), parents.get(cls)
    while cur and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = parents.get(cur)
    return out


def derive_native(parents: dict[str, str]) -> dict:
    """Les deux populations natives, derivees de classes.tsv."""
    own_body: dict[str, str] = {}          # classe porteuse -> nom de l'iterateur
    for name in parents:
        i = name.find(ITER_MARK)
        if i > 0:
            own_body[name[:i]] = name

    # Toute classe dont un ancetre est la base AdjacentUnitPreference (donc: corps commun),
    # en excluant les bases generiques elles-memes (`...`1`).
    inherited: list[str] = []
    for name in parents:
        if name.endswith("`1") or ITER_MARK in name:
            continue
        if ADJ_BASE in ancestors(name, parents):
            inherited.append(name)

    concrete_own = sorted(c for c in own_body if not c.endswith("`1"))
    generic_own = sorted(c for c in own_body if c.endswith("`1"))
    return {
        "own_body_concrete": concrete_own,
        "own_body_generic": generic_own,
        "inherited_body": sorted(inherited),
        "iterators": own_body,
    }


TRIGGERED_BASE = "IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1"


def exhaustivity_check(parents: dict[str, str], nat: dict) -> list[str]:
    """GARDE-FOU : une descendante de `TriggeredAbilityPlaybook`1` ratee par les deux populations ?

    Ventile TOUTE classe qui descend de la base et n'est ni un corps propre ni un concret
    AdjacentUnitPreference. Attendu : uniquement du BRUIT -- les instanciations generiques FERMEES
    (`AdjacentUnitPreferenceTriggeredAbilityPlaybook<XxxAbility>`, meme classe vue sous son nom
    ferme) et la base abstraite `AUnitSpecificBehaviourPlaybook`. Tout AUTRE nom serait un playbook
    reellement omis par le compte -> le script le remonte.
    """
    own = set(nat["own_body_concrete"]) | set(nat["own_body_generic"])
    inh = set(nat["inherited_body"])
    suspects = []
    for n in parents:
        if ITER_MARK in n or n.endswith("`1") or n in own or n in inh:
            continue
        if TRIGGERED_BASE not in ancestors(n, parents):
            continue
        s = n.rsplit(".", 1)[-1]
        if s.endswith("Ability>") or s == "AUnitSpecificBehaviourPlaybook":
            continue                       # bruit attendu
        suspects.append(n)
    return sorted(suspects)


def derive_port() -> dict[int, str]:
    sys.path.insert(0, str(_REPO / "scripts" / "python"))
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS  # noqa: E402
    return {int(k): type(v).__name__ for k, v in TRIGGERED_MOVE_PLAYBOOKS.items()}


def short(cls: str) -> str:
    return cls.rsplit(".", 1)[-1]


# Le nom de classe est `<AbilityName>Playbook` dans l'ecrasante majorite des cas ; la casse peut
# diverger (`ECogSupportPlaybook` <-> `EcogSupport`). Ce mapping-par-nom est une PREMIERE source :
# la VERITE reste le litteral passe par `<X>Playbook$$.ctor`, releve au decompile. Toute entree
# non resolue ici doit etre tranchee au decompile -- le script la signale.
_ALIAS: dict[str, str] = {
    # nom de classe (sans .Playbook) -> nom d'enum TriggeredAbilityType, RELEVE AU DECOMPILE.
    # `IdunBattle.AI.Playbook.Loki.PsykerPlaybook$$.ctor` passe le litteral 0x3f5 = 1013 a la base
    # -> `PsykerExtraAttack`, et non un hypothetique enum « Psyker ».
    "Psyker": "PsykerExtraAttack",
}

# Les 4 `*SpecificBehaviourPlaybook` ne portent PAS de TriggeredAbilityType : leur ctor appelle
# `IdunBattle.AI.Playbook.AUnitSpecificBehaviourPlaybook$$.ctor(this, <index>)` (verifie sur
# `IdunBattleLogic.Playbook.UnitSpecificBehaviour.CyrusSpecificBehaviourPlaybook$$.ctor` : index 0).
# Leurs poids vivent dans `Utilities.Default.UnitSpecificBehaviours`, pas `TriggeredAbilities`.
# `ability_id = None` est donc le verdict JUSTE pour eux, pas un trou de resolution.
UNIT_SPECIFIC_BEHAVIOUR = ("MagnusSpecificBehaviourPlaybook", "MortarionSpecificBehaviourPlaybook",
                           "CyrusSpecificBehaviourPlaybook", "RiptideSpecificBehaviourPlaybook")


def map_ability(cls_short: str, enum: dict[str, int]) -> tuple[str | None, int | None]:
    base = cls_short[:-len("Playbook")] if cls_short.endswith("Playbook") else cls_short
    base = _ALIAS.get(base, base)
    if base in enum:
        return base, enum[base]
    low = {k.lower(): k for k in enum}
    if base.lower() in low:
        k = low[base.lower()]
        return k, enum[k]
    return None, None


def carriers_index() -> dict[str, list[tuple[str, str]]]:
    """ability (nom gameconfig) -> [(unitId, kind)] pour lineup/npc/summons.

    Le gameconfig keye les abilities par NOM, exactement comme l'enum `TriggeredAbilityType`
    (`GeminaeSuperia`, `RitesOfBattle`, ...) : le pont enum <-> gameconfig est le NOM.
    `kind` vaut `lineup` / `npc` / `summons` -- ce n'est PAS la gate de confrontabilite :
    seul `rl_duel.py --list-pool` (live) dit quels lineup sont HERO/MoW spawnables, et un
    `summons` compte via son summoner. Voir la gate du CLAUDE.md.
    """
    sys.path.insert(0, str(_REPO / "scripts" / "python"))
    import gameconfig as GC  # noqa: E402
    out: dict[str, list[tuple[str, str]]] = {}
    ids = GC.all_unit_ids()
    for kind in ("lineup", "npc", "summons"):
        for uid in ids[kind]:
            u = GC.unit(uid) or {}
            for a in (u.get("passiveAbilities") or []) + (u.get("activeAbilities") or []):
                out.setdefault(str(a), []).append((uid, kind))
    # 2e chemin d'octroi : les RELIQUES. `items[<relicId>].abilityId` porte l'ability et
    # `.allowedUnits` les heros qui peuvent l'equiper (ex. `R_Booster_Crit_KardiocoreGalvanus`
    # -> admecDestroyer/Ruststalker/Marshall). Une ability de relique est donc CONFRONTABLE des
    # que l'un de ses `allowedUnits` l'est -- l'oublier range a tort ces items en « indirect ».
    for iid, it in (GC._cfg().get("items") or {}).items():
        aid = it.get("abilityId")
        if not aid:
            continue
        for uid in (it.get("allowedUnits") or []):
            u = GC.unit(uid)
            if u is not None:
                out.setdefault(str(aid), []).append((uid, u.get("kind") or "lineup"))
    return out


def ghidra_sizes(h: str) -> tuple[dict[str, int], dict[str, int]]:
    """`ghidra/functions.tsv` (VA -> symbole) : rend (symbole -> VA, symbole -> TAILLE approchee).

    La taille est le DELTA jusqu'a la fonction suivante dans l'ordre des adresses. C'est un PROXY
    (padding inter-fonctions, fonctions non listees) -- il sert uniquement a TRIER les corps a lire ;
    tout verdict « corps constant » est ensuite CONFIRME au decompile, jamais conclu de la taille.
    Ordre de grandeur mesure : un `yield Fix64.FromInt(0)` nu fait ~0xb0-0xe0 octets.
    """
    p = _SYMBOLS / h / "ghidra" / "functions.tsv"
    rows: list[tuple[int, str]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            a, _, s = line.rstrip("\n").partition("\t")
            if s:
                rows.append((int(a, 16), s))
    rows.sort()
    va = {s: a for a, s in rows}
    size = {}
    for i, (a, s) in enumerate(rows):
        size[s] = (rows[i + 1][0] - a) if i + 1 < len(rows) else 0
    return va, size


def movenext_symbol(cls: str, iterator: str | None) -> str | None:
    """Symbole Ghidra du corps : `<classe>.u003C...u003Ed__N$$MoveNext` (echappement conserve)."""
    if not iterator:
        return None
    esc = iterator.replace("<", "u003C").replace(">", "u003E")
    return esc + "$$MoveNext"


# Un `<...>d__N$$MoveNext` reduit a `yield Fix64.FromInt(0)` pese EXACTEMENT 0x80 octets sur ce
# build (prologue cctor + machine a etats + un seul `FromInt(0,0)`). Verdict CONFIRME AU DECOMPILE
# sur 13 corps de 0x80 (Psyker 1013, AggressiveOnslaught 1248, BarbedOvipositor 1204,
# FireOfAbsolution 1017, RepairEnthusiast 1514, SuppressiveFire 1044, TalonOfHorus 1484,
# ElectroShock 1303, OmnissiahsBlessing 1299, SpecialIssueCombiMelta 1545, CosmicHorror 1277,
# RighteousRepugnance 1107, Boltstorm 1090) : TOUS rendent 0. Le premier corps ACTIF au-dessus
# pese 0xd0 (`SwornProtector_ProtectPlaybook`, qui appelle bien `GetPositionUtility`).
# La taille reste un PROXY : tout item classe ici doit etre relu au decompile avant d'etre porte.
ZERO_BODY_BYTES = 0x80


def bc_catalog() -> set[str]:
    """Les unitIds presents dans le catalogue `BC.Units` du seed partage (`data/seed-bc.json`)."""
    bc = json.loads((_REPO / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    return {u.get("Id") for u in (bc.get("Units") or []) if u.get("Id")}


def confrontability(carriers: list[tuple[str, str]], catalog: set[str]) -> str:
    """Gate du CLAUDE.md, derivee OFFLINE.

    * `lineup`  -> CONFRONTABLE. Present dans `BC.Units` = spawnable tel quel ; absent = injectable
      par `catalog_inject.py` (17 lineup manquent du seed, cf. runner.md 1bis) -- jamais un blocage.
    * `summons` -> CONFRONTABLE via son summoner (le summon apparait dans l'equipe du summoner).
    * `npc` SEUL -> NON PERTINENT (hors-jeu, aucun chemin en bataille).
    """
    kinds = {k for _, k in carriers}
    if not kinds:
        return "porteur-indirect"          # relique / sous-ability / octroi par effet
    if "lineup" in kinds:
        direct = any(k == "lineup" and uid in catalog for uid, k in carriers)
        return "lineup-direct" if direct else "lineup-inject"
    if "summons" in kinds:
        return "summon"
    return "npc-only"


def bc_keys_for(ability_name: str | None, cls_short: str, bc: dict) -> dict[str, dict[str, float]]:
    """Cles BC dont le PREFIXE (avant le 1er '_') matche le nom d'ability, insensible a la casse.

    Heuristique de DEGROSSISSAGE : les cles reellement lues sont celles passees a
    `GetUtilityValue` par le corps -- a confirmer au decompile pour tout item qu'on porte.
    """
    base = (ability_name or (cls_short[:-len("Playbook")] if cls_short.endswith("Playbook") else cls_short)).lower()
    out: dict[str, dict[str, float]] = {}
    for cat in ("TriggeredAbilities", "TriggeredAbilitiesNonOwner", "UnitSpecificBehaviours"):
        for k, v in (bc.get(cat) or {}).items():
            pref = k.split("_", 1)[0].lower()
            if pref == base or pref == base.replace("_", ""):
                out.setdefault(cat, {})[k] = v
    return out


def main(argv: list[str]) -> int:
    want_list = "--list" in argv
    json_out = None
    if "--json" in argv:
        json_out = argv[argv.index("--json") + 1]

    h = build_hash()
    parents = load_classes(h)
    nat = derive_native(parents)
    port = derive_port()
    ported_names = set(port.values())

    own = nat["own_body_concrete"]
    inh = nat["inherited_body"]
    total = len(own) + len(inh)

    own_missing = [c for c in own if short(c) not in ported_names]
    inh_missing = [c for c in inh if short(c) not in ported_names]

    print("[#193] build=%s" % h)
    print("  NATIF  corps propre (concrets)      : %3d" % len(own))
    print("  NATIF  corps propre (bases gener.)  : %3d  %s" % (
        len(nat["own_body_generic"]), [short(c) for c in nat["own_body_generic"]]))
    print("  NATIF  corps HERITE (AdjacentUnitPreference, sans iterateur propre) : %3d" % len(inh))
    print("  NATIF  gisement total               : %3d" % total)
    print("  PORT   TRIGGERED_MOVE_PLAYBOOKS     : %3d  %s" % (
        len(port), sorted(port.values())))
    print("  MANQUANT corps propre               : %3d" % len(own_missing))
    print("  MANQUANT corps herite               : %3d" % len(inh_missing))

    # Garde-fou : tout port doit correspondre a une classe native connue.
    known = {short(c) for c in own} | {short(c) for c in inh}
    orphans = sorted(n for n in ported_names if n not in known)
    print("  PORT sans classe native homonyme    : %3d  %s" % (len(orphans), orphans))
    sus = exhaustivity_check(parents, nat)
    print("  EXHAUSTIVITE : descendantes de TriggeredAbilityPlaybook`1 hors des 2 populations : "
          "%3d  %s" % (len(sus), [short(s) for s in sus]))

    enum = load_enum(h, "IdunBattle.Entities.Enum.TriggeredAbilityType")
    bc = load_bc()
    carriers = carriers_index()
    catalog = bc_catalog()
    _va, gsize = ghidra_sizes(h)
    own_set = set(own)
    rows = []
    for cls in own + inh:
        s = short(cls)
        name, aid = map_ability(s, enum)
        car = carriers.get(name or "", [])
        sym = movenext_symbol(cls, nat["iterators"].get(cls))
        nb = gsize.get(sym or "", None)
        if cls not in own_set:
            term = "common-body"          # corps AdjacentUnitPreference : Sigma poids sur voisins R1
        elif nb == ZERO_BODY_BYTES:
            term = "constant-zero"        # ne departage JAMAIS (yield 0)
        elif nb is None:
            term = "unknown"
        else:
            term = "active"
        rows.append({
            "movenext": sym,
            "body_bytes": nb,
            "movement_term": term,
            "class": cls,
            "short": s,
            "body": "own" if cls in own_set else "inherited",
            "iterator": nat["iterators"].get(cls),
            "ability_name": name,
            "ability_id": aid,
            "bc": bc_keys_for(name, s, bc),
            "carriers": car,
            "carrier_kinds": sorted({k for _, k in car}),
            "confrontable": confrontability(car, catalog),
            "ported": s in ported_names,
        })
    unresolved = [r["short"] for r in rows
                  if r["ability_id"] is None and r["short"] not in UNIT_SPECIFIC_BEHAVIOUR]
    nobc = [r["short"] for r in rows if not r["bc"]]
    nocar = [r["short"] for r in rows if not r["carriers"]]
    print("  ability_id non resolu par NOM (a trancher au decompile) : %3d  %s" % (
        len(unresolved), unresolved))
    print("  sans cle BC par prefixe (poids ailleurs ou terme non-config)  : %3d" % len(nobc))
    print("  sans porteur gameconfig direct (sous-ability / octroye par effet) : %3d" % len(nocar))
    conf, terms = {}, {}
    for r in rows:
        if not r["ported"]:
            conf[r["confrontable"]] = conf.get(r["confrontable"], 0) + 1
            terms[r["movement_term"]] = terms.get(r["movement_term"], 0) + 1
    print("  confrontabilite des NON PORTES : %s" % dict(sorted(conf.items())))
    print("  terme de MOUVEMENT des NON PORTES : %s" % dict(sorted(terms.items())))
    live = [r for r in rows if not r["ported"] and r["movement_term"] != "constant-zero"
            and r["confrontable"] in ("lineup-direct", "lineup-inject", "summon")]
    print("  ==> GISEMENT REEL (terme non nul ET porteur confrontable) : %3d" % len(live))

    # --- 2e volet : le kit declenche EST-IL expose offline au dispatcher ? -----------------------
    # `runner_tile_leaf_ctx` (PR #196) alimente `ctx.unit_triggered_abilities` via
    # `engine.entities.triggered_ability_type.triggered_ability_ids(visualId)`, qui ne lit QUE
    # `gameconfig.passiveAbilities`. Le seed BC, lui, porte un 2e slot : `BC.Units[].TertiaryAbility`
    # = l'ability de RELIQUE equipee. On mesure ici l'ecart entre les deux.
    seed = json.loads((_REPO / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    from engine.entities.triggered_ability_type import triggered_ability_ids  # noqa: E402
    relic_gap, passive_gap = [], []
    for u in (seed.get("Units") or []):
        offline = sorted(triggered_ability_ids(u.get("Id")))
        if u.get("TertiaryAbility"):
            relic_gap.append((u["Id"], u["TertiaryAbility"]))
        if sorted(u.get("PassiveAbilities") or []) != offline:
            passive_gap.append((u["Id"], u.get("PassiveAbilities"), offline))
    print("\n  [volet 2] kit expose offline (`unit_triggered_abilities`) vs seed BC :")
    print("    BC.Units avec une RELIQUE equipee (TertiaryAbility) que le port n'expose PAS : %d  %s"
          % (len(relic_gap), relic_gap))
    print("    BC.PassiveAbilities != triggered_ability_ids(gameconfig) : %d  %s"
          % (len(passive_gap), passive_gap[:6]))

    if want_list:
        print("\n== GISEMENT REEL : terme non nul + porteur confrontable ==")
        for r in sorted(live, key=lambda x: (x["movement_term"], -(x["body_bytes"] or 0))):
            print("   %-42s id=%-5s %-14s %-12s sz=%-5s bc=%s" % (
                r["short"], r["ability_id"], r["confrontable"], r["movement_term"],
                r["body_bytes"] if r["body_bytes"] is not None else "-",
                ";".join("%s=%s" % (k, v) for c in r["bc"].values() for k, v in c.items()) or "-"))
        print("\n== ECARTES : terme CONSTANT NUL (le playbook ne contribue rien au mouvement) ==")
        for r in sorted((x for x in rows if not x["ported"] and x["movement_term"] == "constant-zero"),
                        key=lambda x: x["short"]):
            print("   %-42s id=%-5s %s" % (r["short"], r["ability_id"], r["confrontable"]))
        print("\n== ECARTES : porteur npc-only ou indirect (terme non nul) ==")
        for r in sorted((x for x in rows if not x["ported"] and x["movement_term"] != "constant-zero"
                         and x["confrontable"] in ("npc-only", "porteur-indirect")),
                        key=lambda x: (x["confrontable"], x["short"])):
            print("   %-42s id=%-5s %-16s sz=%s" % (
                r["short"], r["ability_id"], r["confrontable"], r["body_bytes"] or "-"))

    if json_out:
        Path(json_out).write_text(json.dumps({
            "build": h,
            "counts": {"own_body_concrete": len(own), "inherited_body": len(inh),
                       "native_total": total, "ported": len(port),
                       "own_missing": len(own_missing), "inherited_missing": len(inh_missing)},
            "own_body_generic": nat["own_body_generic"],
            "ported": port,
            "rows": rows,
        }, indent=1), encoding="utf-8")
        print("\n[#193] json -> %s" % json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
