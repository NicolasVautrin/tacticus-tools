"""#419 -- INVENTAIRE des playbooks a corps ATTACK / MOVE non trivial, verdict a DEUX AXES.

Recense, depuis la table de symboles VERSIONNEE `data/symbols/<CURRENT>/ghidra/functions.tsv`,
toutes les classes `*Playbook` qui SURCHARGENT une face d'utilite, les VENTILE par CANAL DE
CHARGEMENT natif, et croise le canal TRIGGERED-OWNER avec les registres du port.

LES QUATRE CANAUX (lus au decompile, `IdunBattle.AI.PlaybookDatabase`, un couple
`Dictionary<cle, builder>` + cache singleton par canal) :

  `LoadPlaybook(TriggeredAbilityType)`      builders +0x88 / cache +0x90   -> canal `triggered`
  `LoadPlaybookNonOwner(TriggeredAbilityType)` builders +0x98 / cache +0xa0 -> canal `non_owner`
  `LoadPlaybook(specificBehaviour)`         builders +0xa8 / cache +0xb0   -> canal `specific`
  `LoadDefaultActiveAbilityPlaybook(ActiveAbilityType)` builders +0x80 / cache +0x78 -> `active`

Seul le canal `triggered` est ce que #419 vise : c'est lui qu'iterent les DEUX faces du dispatcher
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility` (UtilityType 2). Le canal `non_owner` a son
propre dispatcher (`TriggeredAbilitiesNonOwnerUtility`, UtilityType 4) et le canal `specific` est
charge par unite, pas par ability -- les melanger gonflerait le gisement.

Registres du port croises :
  * face ATTACK -> `engine.playbook.psyker.TRIGGERED_ATTACK_PLAYBOOKS`
  * face MOVE   -> `engine.playbook.adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`
  * non-owner   -> `engine.playbook.non_owner.NON_OWNER_MOVE_PLAYBOOKS`

DEUX AXES INDEPENDANTS par item (c'est le point de #419) :

  1. PORTE / NON PORTE  -- une classe Python existe-t-elle ET est-elle dans le registre ?
  2. CABLE / NON CABLE  -- le dispatcher ITERE-t-il l'id pour au moins un porteur reel ?
     Le cablage offline passe par `kit_triggered_ability_ids` = `passiveAbilities` gameconfig
     + `TRAIT_TRIGGERED_ABILITY_IDS`. Les voies `relic` / `mythic` / `item` (#323) existent au
     gameconfig mais ne sont PAS lues par ce dispatcher offline : porteurs REELS dont le cablage
     AI est ABSENT -- comptes a part (`carriers_other_voies`), jamais comme « pas de porteur ».

La combinaison qui SAIGNE est PORTE + NON CABLE : le code existe, personne ne l'appelle, aucun
test ne rougit. C'est exactement l'etat de `SuppressiveFire` (1044) avant #415/#456.

METHODE -- pourquoi Ghidra et pas Frida
---------------------------------------
`frida/methods.tsv` est indexee par ADRESSE et IL2CPP DEDUPLIQUE les corps triviaux : un
`yield 0` partage par N playbooks n'a qu'UN proprietaire. Les bases generiques
(`TriggeredAbilityPlaybook<T>`, `NonComparablePlaybook<T>`) sont en outre ABSENTES du dump Frida
(le methodPointer d'une definition generique est un thunk). La table GHIDRA, elle, les porte.
=> l'inventaire se fait sur Ghidra ; une absence cote Frida ne prouverait RIEN (CLAUDE.md).

Le corps REEL d'une face est la state machine `u003C<Face>Internalu003Ed__N$$MoveNext` ; le
`$$<Face>` public n'est que le stub qui la monte. Un playbook qui n'a QUE le stub (corps
deduplique) est signale `stub` et non `SM` -- l'inventaire ne masque pas la difference.

Usage :
    python scripts/python/probe_419_triggered_playbook_inventory.py             # tableau + comptes
    python scripts/python/probe_419_triggered_playbook_inventory.py --json      # sortie machine
    python scripts/python/probe_419_triggered_playbook_inventory.py --residuals # residus nommes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_ROOT = os.path.dirname(os.path.dirname(_HERE))


def _symbols_dir() -> str:
    cur = open(os.path.join(_ROOT, "data", "symbols", "CURRENT"), encoding="utf-8").read().strip()
    return os.path.join(_ROOT, "data", "symbols", cur)


# `<namespace>.<Name>Playbook$$<Method>` ; les state machines sont
# `<namespace>.<Name>Playbook.u003C<Face>Internalu003Ed__<N>$$MoveNext`.
# Le namespace n'est PAS filtre : les playbooks vivent dans QUATRE namespaces
# (`IdunBattle.AI.Playbook[.Loki|.Common]`, `IdunBattleLogic.Playbook.Triggered.Loki`,
# `IdunBattleLogic.Playbook.UnitSpecificBehaviour`) -- un filtre sur `.AI.` en ratait deux.
_RE_PB = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.]*\.(?P<cls>[A-Za-z0-9_]+Playbook))"
    r"(?:\.u003C(?P<sm>[A-Za-z0-9_]+)u003Ed__(?P<idx>\d+))?"
    r"\$\$(?P<meth>.+)$"
)

_FACE_ATTACK = "CalculateAttackUtilityInSteps"
_FACE_MOVE = "CalculateMovementUtilityInSteps"

# Seuil de corps TRIVIAL (`yield Fix64.FromInt(0)`), CALIBRE sur la base elle-meme :
# `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__37u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
# -- decompile LU, il rend `Fix64.op_Implicit(0)` et rien d'autre. Meme demarche que #193 §2, mais
# calibree sur le build COURANT plutot que reprise. `--sizes` imprime la distribution pour re-calibrer.
_TRIVIAL_MAX = 0x80

# Classes dont le nom N'EST PAS le nom de son membre `TriggeredAbilityType`. Chaque entree est
# SOURCEE -- on ne devine pas un id depuis un nom de classe.
_EXPLICIT_ABILITY_NAME = {
    # `PsykerPlaybook` est le playbook du triggered `PsykerExtraAttack` (1013), accorde par le TRAIT
    # `Psyker`. Etabli et valide a l'agreement live (#45-s18, cf. `engine/playbook/psyker.py` :
    # `IsPsykerAttackSuppressed`, `GetAttackDamage`, `PossibleTargets` sont tous des membres de
    # `PsykerExtraAttackAbility`).
    "Psyker": "PsykerExtraAttack",
}

# Classes chargees par un canal AUTRE que `LoadPlaybook(TriggeredAbilityType)`. Le suffixe suffit a
# les separer : `*NonOwnerPlaybook` -> canal non-owner, `*SpecificBehaviourPlaybook` -> canal
# `LoadPlaybook(specificBehaviour)` (parametre NOMME ainsi par Ghidra a `PlaybookDatabase$$LoadPlaybook`
# builders +0xa8), qui se resout par UNITE et non par ability.
_SUF_NON_OWNER = "NonOwnerPlaybook"
_SUF_SPECIFIC = "SpecificBehaviourPlaybook"


def _sizes() -> dict[str, int]:
    """{symbole -> taille en octets}, derivee du DELTA d'adresses de la table triee.

    Proxy assume (deja utilise et CONFIRME AU DECOMPILE par #193 §2) : un corps de face reduit a
    `yield Fix64.FromInt(0)` a une taille FIXE sur un build donne. Il sert a separer, parmi les
    corps PROPRES, ceux qui ne peuvent rien departager. Tout item ainsi classe se RELIT au
    decompile avant port -- la taille trie, elle ne conclut pas."""
    rows: list[tuple[int, str]] = []
    path = os.path.join(_symbols_dir(), "ghidra", "functions.tsv")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                rows.append((int(parts[0], 16), parts[1]))
            except ValueError:
                continue
    rows.sort()
    out: dict[str, int] = {}
    for i, (addr, sym) in enumerate(rows):
        nxt = rows[i + 1][0] if i + 1 < len(rows) else addr
        out[sym] = max(0, nxt - addr)
    return out


def scan_native() -> dict[str, dict]:
    """{classe playbook -> {owner, attack_sm, move_sm, attack_stub, move_stub, methods:[...]}}."""
    out: dict[str, dict] = {}
    sizes = _sizes()
    path = os.path.join(_symbols_dir(), "ghidra", "functions.tsv")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            m = _RE_PB.match(parts[1])
            if m is None:
                continue
            rec = out.setdefault(m.group("cls"), {
                "owner": m.group("owner"), "attack_sm": False, "move_sm": False,
                "attack_stub": False, "move_stub": False, "methods": set(),
                "attack_size": None, "move_size": None,
            })
            sm, meth = m.group("sm"), m.group("meth")
            # DEUX nomenclatures, MESUREES : la base OWNER (`TriggeredAbilityPlaybook<T>`) expose un
            # wrapper non virtuel `<Face>` qui delegue au virtuel `<Face>Internal` (c'est celui-la
            # qu'un concret override) ; la base NON-OWNER n'a pas ce relais et ses concrets
            # overrident `<Face>` NU. Compter la seule forme `Internal` faisait tomber les 16
            # non-owner a ZERO -- et deux OWNER (`CabalOfSorcerers`, `WisdomOfTheAncients`) qui
            # overrident eux aussi la forme nue.
            if sm is not None:
                if meth == "MoveNext":
                    if sm in (_FACE_ATTACK, _FACE_ATTACK + "Internal"):
                        rec["attack_sm"] = True
                        rec["attack_size"] = sizes.get(parts[1])
                    elif sm in (_FACE_MOVE, _FACE_MOVE + "Internal"):
                        rec["move_sm"] = True
                        rec["move_size"] = sizes.get(parts[1])
                continue
            rec["methods"].add(meth)
            if meth in (_FACE_ATTACK, _FACE_ATTACK + "Internal"):
                rec["attack_stub"] = True
            elif meth in (_FACE_MOVE, _FACE_MOVE + "Internal"):
                rec["move_stub"] = True
    for rec in out.values():
        rec["methods"] = sorted(rec["methods"])
    return out


def _enum_by_name() -> dict[str, int]:
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    return {n: int(v) for n, v in TriggeredAbilityType.__members__.items()}


def _resolve_id(base: str, by_name: dict[str, int]) -> tuple[int | None, str]:
    """(id, comment) -- `comment` dit COMMENT l'id a ete resolu ; '' si echec."""
    if base in _EXPLICIT_ABILITY_NAME:
        nm = _EXPLICIT_ABILITY_NAME[base]
        return by_name.get(nm), f"explicite -> {nm}"
    if base in by_name:
        return by_name[base], "nom exact"
    low = {k.lower(): v for k, v in by_name.items()}
    if base.lower() in low:                      # le jeu ecrit `ECogSupport`, l'enum `EcogSupport`
        return low[base.lower()], "casse"
    flat = {k.replace("_", "").lower(): v for k, v in by_name.items()}
    if base.replace("_", "").lower() in flat:
        return flat[base.replace("_", "").lower()], "underscore"
    return None, ""


def _registries() -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
    return ({int(k): type(v).__name__ for k, v in TRIGGERED_ATTACK_PLAYBOOKS.items()},
            {int(k): type(v).__name__ for k, v in TRIGGERED_MOVE_PLAYBOOKS.items()},
            {int(k): type(v).__name__ for k, v in NON_OWNER_MOVE_PLAYBOOKS.items()})


def _carriers() -> tuple[dict[int, dict[str, list[str]]], dict[str, dict[str, list[str]]]]:
    """(id -> {kind: [unitId]} pour la voie DISPATCHEE offline,
        nom d'ability -> {voie: [unitId]} pour relic/mythic/item/active).

    La voie dispatchee est exactement ce qu'itere le port : `kit_triggered_ability_ids`
    (passiveAbilities + `TRAIT_TRIGGERED_ABILITY_IDS`). Les autres voies (#323) sont rendues a
    part : porteur REEL, cablage AI absent -- la distinction est le coeur du verdict."""
    import gameconfig as GC
    import unit_map as UM
    from engine.entities.triggered_ability_type import kit_triggered_ability_ids

    ids = GC.all_unit_ids()
    disp: dict[int, dict[str, list[str]]] = {}
    other: dict[str, dict[str, list[str]]] = {}
    for kind in ("lineup", "npc", "summons"):
        for uid in ids[kind]:
            for aid in kit_triggered_ability_ids(uid):
                disp.setdefault(int(aid), {}).setdefault(kind, []).append(uid)
            u = GC.unit(uid) or {}
            for voie, field in UM.UNIT_ABILITY_FIELDS.items():
                if voie == "passive":          # deja compte par la voie dispatchee
                    continue
                for nm in (u.get(field) or []):
                    other.setdefault(nm, {}).setdefault(voie, []).append(uid)
    for uid, pairs in UM._relic_items().items():
        for aid, _item in pairs:
            other.setdefault(aid, {}).setdefault("item", []).append(uid)
    return disp, other


def build_inventory() -> list[dict]:
    native = scan_native()
    by_name = _enum_by_name()
    atk_reg, mov_reg, no_reg = _registries()
    disp, other = _carriers()

    rows: list[dict] = []
    for cls, rec in sorted(native.items()):
        if not (rec["attack_sm"] or rec["move_sm"] or rec["attack_stub"] or rec["move_stub"]):
            continue
        if cls.endswith(_SUF_NON_OWNER):
            canal, base = "non_owner", cls[:-len(_SUF_NON_OWNER)]
            if base.endswith("Playbook"):      # `ECogSupportPlaybookNonOwnerPlaybook`
                base = base[:-len("Playbook")]
        elif cls.endswith(_SUF_SPECIFIC):
            canal, base = "specific", cls[:-len(_SUF_SPECIFIC)]
        else:
            canal, base = "triggered", cls[:-len("Playbook")]
        aid, how = (None, "") if canal == "specific" else _resolve_id(base, by_name)
        carr = disp.get(aid, {}) if aid is not None else {}
        rows.append({
            "playbook": cls, "owner": rec["owner"], "canal": canal,
            "ability_name": base, "ability_id": aid, "id_resolved_by": how,
            "native_attack": bool(rec["attack_sm"] or rec["attack_stub"]),
            "native_attack_sm": bool(rec["attack_sm"]),
            "native_move": bool(rec["move_sm"] or rec["move_stub"]),
            "native_move_sm": bool(rec["move_sm"]),
            "attack_size": rec["attack_size"], "move_size": rec["move_size"],
            "attack_trivial": rec["attack_size"] is not None and rec["attack_size"] <= _TRIVIAL_MAX,
            "move_trivial": rec["move_size"] is not None and rec["move_size"] <= _TRIVIAL_MAX,
            "ported_attack": (aid in atk_reg) if aid is not None else False,
            "ported_move": (aid in mov_reg) if aid is not None else False,
            "ported_non_owner": (aid in no_reg) if aid is not None else False,
            "carriers": carr,
            "n_carriers": sum(len(v) for v in carr.values()),
            "carriers_other_voies": other.get(base, {}),
            # DEUX niveaux de cablage, et les confondre est ce qui rend le verdict faux :
            #   `wired`      = la voie DISPATCHEE OFFLINE (`kit_triggered_ability_ids` =
            #                  passiveAbilities + TRAIT_TRIGGERED_ABILITY_IDS) ;
            #   `wired_live` = ce que le dispatcher voit REELLEMENT en bataille, l'AbilitiesComponent
            #                  lu par `unitAbilityStates` -- il porte AUSSI relique / mythique /
            #                  item. Les DEUX faces le lisent (MOVE depuis #304, ATTACK depuis #419).
            # Un playbook `wired_live` mais pas `wired` est CABLE : c'est le cas de toute relique.
            "wired": bool(carr),
            "wired_live": bool(carr) or bool(other.get(base, {})),
            "methods": rec["methods"],
        })
    return rows


def _fmt(rows: list[dict]) -> str:
    hdr = (f"{'playbook':<46} {'canal':<10} {'id':>5} {'natATK':>6} {'natMOV':>6} {'ptA':>4} "
           f"{'ptM':>4} {'ptNO':>4} {'kit':>4} {'autres voies':<22}")
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        ov = ",".join(f"{k}:{len(v)}" for k, v in sorted(r["carriers_other_voies"].items()))
        out.append(
            f"{r['playbook']:<46} {r['canal']:<10} {str(r['ability_id'] or '-'):>5} "
            f"{('SM' if r['native_attack_sm'] else ('stub' if r['native_attack'] else '-')):>6} "
            f"{('SM' if r['native_move_sm'] else ('stub' if r['native_move'] else '-')):>6} "
            f"{('yes' if r['ported_attack'] else '-'):>4} "
            f"{('yes' if r['ported_move'] else '-'):>4} "
            f"{('yes' if r['ported_non_owner'] else '-'):>4} "
            f"{r['n_carriers']:>4} {ov:<22}")
    return "\n".join(out)


def _bucket(sel: list[dict], pk: str) -> dict[str, list[dict]]:
    """Le croisement a DEUX AXES de #419. L'axe CABLAGE est pris au niveau `wired_live` (ce que le
    dispatcher voit reellement en bataille) : un playbook de relique n'est PAS un « non cable »."""
    return {
        "porte+cable": [r for r in sel if r[pk] and r["wired_live"]],
        "PORTE+NON CABLE": [r for r in sel if r[pk] and not r["wired_live"]],
        "non porte+cable": [r for r in sel if not r[pk] and r["wired_live"]],
        "non porte+non cable": [r for r in sel if not r[pk] and not r["wired_live"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--residuals", action="store_true")
    ap.add_argument("--sizes", action="store_true",
                    help="distribution des tailles de corps par face (calibrage de _TRIVIAL_MAX)")
    args = ap.parse_args()

    rows = build_inventory()
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    if args.sizes:
        base = _sizes().get(
            "IdunBattle.AI.Playbook.TriggeredAbilityPlaybook.u003CCalculateAttackUtilityInStepsInternal"
            "u003Ed__37u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext")
        print(f"corps de la BASE (yield 0, decompile lu) : {base} octets (0x{base:x})")
        for face, key in (("ATTACK", "attack_size"), ("MOVE", "move_size")):
            vals = sorted((r[key], r["playbook"]) for r in rows
                          if r["canal"] == "triggered" and r[key] is not None)
            print(f"--- {face} : {len(vals)} corps propres, tailles croissantes ---")
            for sz, cls in vals:
                print(f"   0x{sz:<5x} {cls}")
        return 0

    trig = [r for r in rows if r["canal"] == "triggered"]
    no_rows = [r for r in rows if r["canal"] == "non_owner"]
    spec = [r for r in rows if r["canal"] == "specific"]
    atk = [r for r in trig if r["native_attack"]]
    mov = [r for r in trig if r["native_move"]]

    print(_fmt(rows))
    print()
    print(f"classes *Playbook avec une face ATTACK ou MOVE surchargee : {len(rows)}")
    print(f"  canal `triggered`  (LoadPlaybook(TriggeredAbilityType)) : {len(trig)}")
    print(f"  canal `non_owner`  (LoadPlaybookNonOwner)               : {len(no_rows)}")
    print(f"  canal `specific`   (LoadPlaybook(specificBehaviour))    : {len(spec)}")
    unres = [r for r in trig if r["ability_id"] is None]
    if unres:
        print(f"  ATTENTION -- id NON resolu : {[r['playbook'] for r in unres]}")
    atk_live = [r for r in atk if not r["attack_trivial"]]
    mov_live = [r for r in mov if not r["move_trivial"]]
    print()
    print("GISEMENT #419 -- canal `triggered` seul :")
    print(f"  face ATTACK surchargee   : {len(atk)}  "
          f"(SM propre : {sum(1 for r in atk if r['native_attack_sm'])})")
    print(f"     dont corps TRIVIAL (`yield Fix64(0)`, <= 0x{_TRIVIAL_MAX:x}) : "
          f"{len(atk) - len(atk_live)}   ==> gisement REEL : {len(atk_live)}")
    print(f"  face MOVE   surchargee   : {len(mov)}  "
          f"(SM propre : {sum(1 for r in mov if r['native_move_sm'])})")
    print(f"     dont corps TRIVIAL : {len(mov) - len(mov_live)}   "
          f"==> gisement REEL : {len(mov_live)}")
    print("  NB face MOVE : ce compte ne voit QUE les corps PROPRES. La population a corps")
    print("     HERITE (concrets d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook<T>`, corps")
    print("     DEDUPLIQUE donc invisible d'une table indexee par ADRESSE) se compte sur")
    print("     `frida/classes.tsv` -- c'est le role de `probe_193_move_playbook_inventory.py`.")
    print("     AUCUNE base parametree n'implemente la face ATTACK (verifie : la seule est")
    print("     `TriggeredAbilityPlaybook<T>$$CalculateAttackUtilityInStepsInternal`, qui rend 0)")
    print("     -> pour ATTACK, les corps propres SONT l'inventaire complet.")
    print()
    for face, sel, pk in (("ATTACK", atk_live, "ported_attack"), ("MOVE", mov_live, "ported_move"),
                          ("NON-OWNER", no_rows, "ported_non_owner")):
        b = _bucket(sel, pk)
        print(f"[{face}] (corps non triviaux) " + "  ".join(f"{k}={len(v)}" for k, v in b.items()))
        if b["PORTE+NON CABLE"]:
            print("   PORTE+NON CABLE (saigne) : "
                  + ", ".join(f"{r['playbook']}({r['ability_id']})" for r in b["PORTE+NON CABLE"]))
    if args.residuals:
        print()
        print("RESIDUS NOMMES -- face NATIVE non triviale, NON portee, porteur DISPATCHE reel :")
        for face, sel, pk in (("ATTACK", atk_live, "ported_attack"),
                              ("MOVE", mov_live, "ported_move"),
                              ("NON-OWNER", no_rows, "ported_non_owner")):
            for r in sorted(sel, key=lambda x: -x["n_carriers"]):
                if r[pk] or not r["wired_live"]:
                    continue
                ex = sorted(v[0] for v in r["carriers"].values())
                print(f"  {face:<9} {r['playbook']:<44} id={str(r['ability_id']):<5} "
                      f"porteurs={r['n_carriers']:<4} "
                      f"kinds={ {k: len(v) for k, v in r['carriers'].items()} } ex={ex[:3]}")
        print()
        print("PORTEUR REEL PAR UNE VOIE QUE LE KIT OFFLINE IGNORE (relic/mythic/item, #323) --")
        print("  cablage assure par le canal LIVE `unitAbilityStates` (MOVE #304, ATTACK #419) :")
        for r in rows:
            if r["wired"] or not r["carriers_other_voies"]:
                continue
            print(f"  {r['playbook']:<44} id={str(r['ability_id']):<5} "
                  f"voies={ {k: len(v) for k, v in r['carriers_other_voies'].items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
