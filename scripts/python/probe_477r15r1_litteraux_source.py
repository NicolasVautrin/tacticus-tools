#!/usr/bin/env python3
"""#477-r15-r1 -- d'ou vient `Source=` ? (et ce que la table de litteraux resout vraiment)

    python probe_477r15r1_litteraux_source.py [--board C1_02] [--tours 8]
    python probe_477r15r1_litteraux_source.py --offline      # etapes 0..2 seules

CE QUE CE PROBE A REFUTE
------------------------
Le residu posait : « le `sourceId` est un handle de LITTERAL, non resoluble statiquement ; le
meme mur bloquera tout `Source=` non vide, c'est-a-dire la quasi-totalite du deroule ». La
mesure dit autre chose, et l'ecart est le resultat principal de cette tranche :

    sur les 8 `Source=` non vides d'un flux de DEROULE reel (C1_02, 7 tours IA),
    1 seul est un litteral IL2CPP. Les 8 sont des NOMS DE MEMBRES D'ENUM.

`Source=` n'est donc pas un handle de litteral : c'est un `Enum.ToString()`, exactement le
mecanisme deja porte par `format_enum_value` pour `Group=`, `Action=` et `Tag=`. La table qui
le resout -- `data/symbols/<build>/frida/enums.tsv` -- EXISTAIT DEJA, et les mirrors Python
correspondants sont sous cliquet (`probe_313`). Mesure : 9/9 resolus par le port tel quel.

⚠ CE QUE CELA NE PROUVE PAS, ET C'EST LA TRANCHE D : que le port sache QUEL enum et QUEL
  ordinal passer a CHAQUE `StartGroup`. Ce probe mesure que le NOM est atteignable, pas que
  l'emission soit portee. Le mur n'etait pas la resolution ; il est dans les producteurs.

⚠ ET LE NOM NE SUFFIT PAS A DESIGNER L'ENUM : `BigTarget` est porte par `TriggeredAbilityType`
  (1030) ET par `UnitTrait` (1017). Un comparateur qui resoudrait « par le nom » choisirait au
  hasard -- c'est la regle de qualification du CLAUDE.md, mesuree ici sur un cas reel.

CE QUE LA TABLE DE LITTERAUX RESOUT, ELLE
-----------------------------------------
Elle n'est pas la voie de `Source=`, mais elle tient ce qui etait verifiable :
  * le handle du groupe `AddUnit` est la chaine VIDE, pas `null` -- indiscernables sur le flux,
    tranches ici statiquement ;
  * les CINQ litteraux du writer (`StreamCache`), que `case-477r15` declarait « MESURES, PAS
    LUS », sont desormais LUS, et concordent 5/5 avec la mesure ;
  * n'importe quel `DAT_<slot>` d'un decompile devient lisible.

LES ETAPES
----------
0. OFFLINE  la table existe, sa provenance concorde avec le binaire installe, le pont est mesure.
1. OFFLINE  le pont sur du code natif reel -- scan des references RIP-relatives du PE,
            INDEPENDANT de Ghidra, donc il CONFRONTE la table au binaire au lieu de la croire.
2. OFFLINE  CONTRE-EPREUVE : « tout est dans la table » ne vaut rien si la table matche
            n'importe quoi. Chaque valeur mutee d'un caractere doit DISPARAITRE.
3. LIVE     les `Source=` reels d'un flux de DEROULE, ventiles par voie de resolution.
4. LIVE     le PORT les rend-il aujourd'hui ? (mirrors Python + `format_enum_value`)

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-file sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import string_literals as SL  # noqa: E402
from il2cpp_provenance import ProvenanceError, installed_dll  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"
HOST = "http://127.0.0.1:8765"

ROSTER_P = "astraBullgryn"
ROSTER_A = "thousTzaangor"
SEED = 777

#: Fonctions natives NOMMEES de la couche de flux : temoins du scan PE.
TEMOINS = (
    "IdunBattle.Operations.AddUnitOperation$$Execute",
    "IdunBattle.BattleStream.Loggers.StreamCache$$StartGroup",
    "IdunBattle.BattleStream.Loggers.StreamCache$$Action",
    "IdunBattle.BattleStream.Loggers.StreamCache$$FinishGroup",
)

#: Mirrors Python susceptibles de nommer un `Source=`. La cle est le nom COURT de l'enum
#: natif ; la valeur, le chemin d'import du mirror. Ils sont deja gardes en bijection par
#: `probe_313` -- ce probe ne les garde pas, il MESURE ce qu'ils couvrent.
MIRRORS = {
    "EffectType": ("engine.entities.effect_type", "EffectType"),
    "TriggeredAbilityType": ("engine.entities.triggered_ability_type", "TriggeredAbilityType"),
    "ActiveAbilityType": ("engine.entities.active_ability_type", "ActiveAbilityType"),
    "UnitTrait": ("engine.entities.traits.unit_trait", "UnitTrait"),
}


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


# --- scan PE : les references RIP-relatives d'une plage de code ---------------


def sections_pe(dll: Path) -> tuple[int, list[tuple[int, int, int]]]:
    raw = dll.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    nb = struct.unpack_from("<H", raw, pe + 6)[0]
    taille_opt = struct.unpack_from("<H", raw, pe + 20)[0]
    base = struct.unpack_from("<Q", raw, pe + 24 + 0x18)[0]
    secs = []
    off = pe + 24 + taille_opt
    for i in range(nb):
        h = off + i * 40
        vsize, vaddr, rawsize, rawoff = struct.unpack_from("<4I", raw, h + 8)
        secs.append((base + vaddr, base + vaddr + max(vsize, rawsize), rawoff))
    return base, secs


def refs_rip(code: bytes, va_debut: int) -> set[int]:
    """Cibles des `mov r64,[rip+disp32]` / `lea r64,[rip+disp32]` d'un bloc de code.

    Decodage MINIMAL : REX.W (0x48..0x4F), opcode 0x8B ou 0x8D, ModRM mod=00 rm=101 -> disp32
    relatif a la FIN de l'instruction. C'est la seule forme par laquelle IL2CPP charge un slot.

    Ce balayage n'est pas un desassembleur : il peut lire un motif A L'INTERIEUR d'une autre
    instruction. C'est assume -- un faux positif rend une adresse qui n'est simplement pas dans
    la table, donc la table le filtre. Rater une reference ne ferait que SOUS-estimer."""
    out: set[int] = set()
    for i in range(len(code) - 7):
        if not (0x48 <= code[i] <= 0x4F):
            continue
        if code[i + 1] not in (0x8B, 0x8D):
            continue
        if (code[i + 2] & 0xC7) != 0x05:
            continue
        out.add(va_debut + i + 7 + struct.unpack_from("<i", code, i + 3)[0])
    return out


def plage_fonction(symbole: str, functions_tsv: Path) -> tuple[int, int]:
    """(debut, fin), la fin etant l'entree de la fonction SUIVANTE -- une MAJORANTE.

    `ghidra/functions.tsv` ne porte que les points d'entree. La majorante suffit : un slot lu
    au-dela appartient a une autre fonction et n'ajoute que du bruit, jamais un retrait."""
    entrees = []
    with functions_tsv.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            a, _, nom = ligne.rstrip("\n").partition("\t")
            try:
                entrees.append((int(a, 16), nom))
            except ValueError:
                continue
    entrees.sort()
    for i, (va, nom) in enumerate(entrees):
        if nom == symbole:
            return va, (entrees[i + 1][0] if i + 1 < len(entrees) else va + 0x4000)
    raise MesureImpossible("symbole absent de functions.tsv : %s" % symbole)


def litteraux_de(symbole: str, dll: Path, table: SL.TableLitteraux,
                 functions_tsv: Path) -> dict[int, str]:
    va, fin = plage_fonction(symbole, functions_tsv)
    _, secs = sections_pe(dll)
    raw = dll.read_bytes()
    for d, f, off in secs:
        if d <= va < f:
            code = raw[off + (va - d):off + (fin - d)]
            break
    else:
        raise MesureImpossible("0x%x hors des sections de %s" % (va, dll.name))
    return {c: v for c in refs_rip(code, va) for v in [table.by_va(c)] if v is not None}


# --- enums du build (table VERSIONNEE, independante des mirrors) --------------


def enums_du_build(build: str) -> dict[str, dict[str, int]]:
    path = SL.SYMBOLS / build / "frida" / "enums.tsv"
    if not path.is_file():
        raise MesureImpossible("enums.tsv absent : %s" % path)
    out: dict[str, dict[str, int]] = {}
    with path.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            nom, _, vals = ligne.rstrip("\n").partition("\t")
            membres: dict[str, int] = {}
            for pair in vals.split(","):
                v, _, n = pair.partition("=")
                if n:
                    try:
                        membres[n] = int(v)
                    except ValueError:
                        pass
            out[nom] = membres
    return out


def porteurs_du_nom(enums: dict[str, dict[str, int]], nom: str) -> list[tuple[str, int]]:
    return sorted((e, m[nom]) for e, m in enums.items() if nom in m)


# --- live --------------------------------------------------------------------


def rpc(session: int, method: str, args: dict, timeout: int = 120) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 90000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def session_courante() -> int:
    try:
        with urllib.request.urlopen("%s/api/admin/status" % HOST, timeout=10) as r:
            st = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("host injoignable : %s" % e) from e
    sid = (st.get("session") or {}).get("id")
    if sid is None:
        raise MesureImpossible("aucune session Frida vivante")
    return int(sid)


def duel(*argv: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "rl_duel.py", *argv], cwd=str(HERE),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def flux_de_deroule(board: str, tours: int, state: Path) -> str:
    p = duel("build", "--seed", str(SEED), "--board", board,
             "--p-units", ROSTER_P, "--a-units", ROSTER_A,
             "--record-replay", "--state-file", str(state))
    if not state.is_file():
        raise MesureImpossible("build %s echoue : %s" % (board, (p.stderr or p.stdout)[-600:]))
    session = session_courante()
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    try:
        joues = 0
        for _ in range(tours):
            if duel("aiturn", "--state-file", str(state), timeout=300).returncode != 0:
                break
            joues += 1
        print("    tours IA joues : %d / %d demandes" % (joues, tours))
        if joues == 0:
            # Sans deroule, le flux ne porte que le deploiement -- OU `Source=` est vide par
            # construction. Un « 0 source non vide » s'y lirait comme un resultat : ce n'en
            # est pas un, c'est un regime qui ne discrimine pas.
            raise MesureImpossible("aucun tour joue : le flux ne porterait que le deploiement")
        return (rpc(session, "replayOutputStream",
                    {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        duel("dispose", "--state-file", str(state), timeout=180)


RE_GROUPE = re.compile(r"^\s*Group=(\S+) Entity=(\S+) Source=(.*?) InitialTarget=(.*)$")


def sources_du_flux(flux: str) -> tuple[list[str], int, int]:
    """(sources non vides distinctes, nb lignes `Group=`, nb a source vide)."""
    vues: list[str] = []
    lignes = vides = 0
    for ligne in flux.split("\n"):
        m = RE_GROUPE.match(ligne)
        if not m:
            continue
        lignes += 1
        if m.group(3) == "":
            vides += 1
        elif m.group(3) not in vues:
            vues.append(m.group(3))
    return vues, lignes, vides


# --- probe -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--tours", type=int, default=8)
    ap.add_argument("--offline", action="store_true", help="etapes 0..2 seules")
    args = ap.parse_args()

    rc = 0
    print("=" * 78)
    print("#477-r15-r1 -- d'ou vient `Source=` ?")
    print("=" * 78)

    # --- 0 -------------------------------------------------------------------
    print("\n[0] LA TABLE DE LITTERAUX ET SA PROVENANCE")
    try:
        table = SL.charger()
        dll = installed_dll()
    except (SL.TableAbsente, ProvenanceError) as exc:
        print("    REFUS : %s" % exc)
        return 2
    print("    build=%s  litteraux=%d  slots joints=%d  image_base=0x%x"
          % (table.build, len(table), table.slots_joints, table.image_base))
    print("    provenance confrontee au binaire installe : %s"
          % ("OUI" if table.verifiee else "NON"))
    if table.slots_joints == 0:
        print("    ROUGE : aucun slot joint -> la table ne resout aucun `DAT_<..>`.")
        return 1

    # --- 1 -------------------------------------------------------------------
    print("\n[1] LE PONT SUR DU CODE NATIF REEL (scan PE, independant de Ghidra)")
    ftsv = SL.SYMBOLS / table.build / "ghidra" / "functions.tsv"
    if not ftsv.is_file():
        print("    NON MESURE : %s absent" % ftsv)
        rc = 1
    else:
        total = 0
        for sym in TEMOINS:
            try:
                trouves = litteraux_de(sym, dll, table, ftsv)
            except MesureImpossible as exc:
                print("    %-52s NON MESURE (%s)" % (sym[-52:], exc))
                rc = 1
                continue
            total += len(trouves)
            print("    %-52s %3d litteraux" % (sym[-52:], len(trouves)))
            for va, v in sorted(trouves.items()):
                print("        DAT_%x -> %s" % (va, json.dumps(v)[:66]))
        if total == 0:
            print("    ROUGE : le scan ne resout AUCUN litteral sur les temoins.")
            rc = 1

    # --- 2 -------------------------------------------------------------------
    print("\n[2] CONTRE-EPREUVE -- la table discrimine-t-elle ?")
    valeurs = set(table.by_index(i) for i in range(len(table)))
    pas = max(1, len(table) // 400)
    echantillon = [v for v in (table.by_index(i) for i in range(0, len(table), pas))
                   if len(v) >= 4][:200]
    mutes = sum(1 for v in echantillon
                if (v[:-1] + ("Z" if v[-1] != "Z" else "Q")) in valeurs)
    print("    %d valeurs mutees d'UN caractere ; %d retrouvees dans la table"
          % (len(echantillon), mutes))
    if not echantillon:
        print("    ROUGE : echantillon VIDE -- la contre-epreuve n'a rien teste.")
        rc = 1
    elif mutes > len(echantillon) // 10:
        print("    ROUGE : la table matche des chaines qu'elle ne devrait pas.")
        rc = 1
    else:
        print("    OK : l'appartenance a la table est DISCRIMINANTE.")

    if args.offline:
        print("\n[3-4] LIVE -- NON JOUE (--offline)")
        print("\nrc=%d" % rc)
        return rc

    # --- 3 -------------------------------------------------------------------
    print("\n[3] LES `Source=` REELS D'UN FLUX DE DEROULE")
    state = OUT / ("state-477r15r1-%s.json" % args.board)
    state.parent.mkdir(parents=True, exist_ok=True)
    try:
        flux = flux_de_deroule(args.board, args.tours, state)
        enums = enums_du_build(table.build)
    except MesureImpossible as exc:
        print("    NON CONFRONTE : %s" % exc)
        print("\nrc=%d (les etapes offline restent valides)" % rc)
        return rc
    if not flux:
        print("    NON CONFRONTE : `replayOutputStream` rend un flux VIDE")
        return rc

    sources, lignes, vides = sources_du_flux(flux)
    print("    flux : %d octets, %d lignes `Group=`, dont %d a `Source=` VIDE"
          % (len(flux), lignes, vides))
    print("    sources NON VIDES distinctes : %d" % len(sources))
    print()
    print("    %-32s %-9s %s" % ("source", "litteral", "porteurs (enum=ordinal)"))
    orphelines, ambigues, litterales = [], [], []
    for s in sources:
        est_lit = s in valeurs
        porteurs = porteurs_du_nom(enums, s)
        if est_lit:
            litterales.append(s)
        if not porteurs and not est_lit:
            orphelines.append(s)
        if len(porteurs) > 1:
            ambigues.append((s, porteurs))
        print("    %-32s %-9s %s" % (s[:32], "OUI" if est_lit else "-",
                                     ", ".join("%s=%d" % (e, v) for e, v in porteurs) or "AUCUN"))
    print()
    print("    litteral IL2CPP  : %d / %d" % (len(litterales), len(sources)))
    print("    membre d'enum    : %d / %d" % (len(sources) - len(orphelines), len(sources)))
    if ambigues:
        print("    AMBIGUES (le nom seul ne designe pas l'enum) : %d" % len(ambigues))
        for s, p in ambigues:
            print("        %-28s %s" % (s, ", ".join("%s=%d" % (e, v) for e, v in p)))
    if orphelines:
        print("    ROUGE : %d source(s) resolue(s) par AUCUNE voie : %s"
              % (len(orphelines), orphelines))
        rc = 1

    # --- 4 -------------------------------------------------------------------
    print("\n[4] LE PORT REND-IL CES NOMS AUJOURD'HUI ?")
    from engine.streams.entity_id import format_enum_value
    charges = {}
    for court, (chemin, cls) in MIRRORS.items():
        try:
            charges[court] = getattr(__import__(chemin, fromlist=[cls]), cls)
        except Exception as exc:                     # noqa: BLE001 - on DIT lequel manque
            print("    mirror %s INDISPONIBLE : %s" % (court, exc))
    rendus = manques = 0
    for s in sources:
        for enum_natif, ordinal in porteurs_du_nom(enums, s):
            court = enum_natif.rsplit(".", 1)[-1]
            E = charges.get(court)
            if E is None:
                print("    %-28s %-22s PAS DE MIRROR" % (s[:28], court))
                manques += 1
                continue
            rendu = format_enum_value(E, ordinal)
            if rendu == s:
                rendus += 1
            else:
                manques += 1
                print("    %-28s %-22s ECART : mirror rend %r" % (s[:28], court, rendu))
    print("    couples (nom, enum) rendus a l'identique : %d ; ecarts : %d" % (rendus, manques))
    if manques:
        print("    ROUGE : le port ne sait pas nommer %d couple(s)." % manques)
        rc = 1
    elif rendus:
        print("    OK : `Source=` est REMPLISSABLE -- il ne manque que l'EMISSION (tranche D).")

    print("\nrc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
