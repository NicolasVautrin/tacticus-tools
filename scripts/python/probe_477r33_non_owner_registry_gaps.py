#!/usr/bin/env python
"""#477-r33 -- QUELS `*NonOwnerPlaybook` natifs manquent au registre du port, et LESQUELS PESENT ?

QUESTION BINAIRE, posee avant la methode : sur nos montages de reference, quels termes
`TriggeredAbilitiesNonOwner(4)` le NATIF ajoute-t-il aujourd'hui SANS que le port les porte ?

CE PROBE FAIT DEUX CHOSES, et la premiere est un RECENSEMENT RE-DERIVE (aucun compte herite) :

  ETAPE 0 -- le recensement, 100 % offline
    a) les concrets de la famille sont derives par le **PARENT** dans
       `data/symbols/<build>/frida/classes.tsv`, JAMAIS par le nom : trois d'entre eux ne portent
       pas le suffixe `NonOwnerPlaybook` (`CabalOfSorcerersPlaybook`, `WisdomOfTheAncientsPlaybook`,
       `VoltagheistFieldPlaybook`) et un grep par nom les rate DEUX fois (leurs state machines
       nichees ne portent pas la chaine non plus). C'est la faute que #433-r4-r3-r1 avait deja
       corrigee et que le residu #477-r33 avait RE-INTRODUITE en citant « 25 ».
    b) la FACE de chaque concret est lue a ses state machines `<Calculate*UtilityInSteps>d__N` dans
       `data/symbols/<build>/ghidra/functions.tsv` -- MOVE / ATTACK / REPAIR. Seule la face MOVE
       est consommee par `engine/utilities/tile.py::TriggeredAbilitiesNonOwnerUtility.evaluate`.
    c) l'id d'ability de chaque concret est celui que son `.ctor` passe a la base, RE-LU ici dans le
       binaire (`mov edx, imm32` juste avant le `jmp` vers le ctor de base).
       ⚠ Pour `PrimarchOfTheFirstLegion` cet id est FAUX (copier-coller de `NetherRealmCasket`) :
       le port l'indexe sur l'id du SITE D'ENREGISTREMENT (#433-r4-r3-r1). Le probe le SAIT et
       n'en fait pas un ecart.
    d) le poids BC de chaque terme est resolu au LITTERAL (`probe_212_bc_key_literals`), puis
       confronte a la capture `data/seed-bc.json` ET au gameconfig VIVANT (piege #271).
    e) l'atteignabilite est ventilee par VOIE (equipee au seed / porteur au pool + relique /
       porteur hors pool / MoW / summon / npc), et pas par le faux axe binaire.

  ETAPE 0bis -- LE DECOMPTE DES CONFONDS
    Pour chaque unite du seed BC, on croise ses abilities declenchees (kit gameconfig + relique
    `TertiaryAbility`) avec les faces MOVE **non portees**. Toute unite qui arrive en bataille avec
    l'une d'elles ARME un terme que le natif ajoute et que le port ignore. C'est la vraie mesure de
    ce residu -- et c'est ainsi que `1457 KardiocoreGalvanus` a ete trouve, +20 sur les tuiles du
    terme mesure par #477-r31.

  ETAPE 1 -- le confront LIVE (montages, cf. `--montage`)
    Discipline de #477-r29 / #477-r31 : A/B ou seul le facteur teste change, les DEUX bras observes
    A EGALITE par `scorerTileTermTrace` (qui ne voit que le tier COMPARABLE), contre-epreuve dont
    chaque mutant DECLARE son observable, `a_mordu` rendu SEPAREMENT du verdict, inertie declaree
    ASSERTIONNEE DANS LES DEUX SENS.

    * `kardio` -- la geometrie `camp` de `probe_477r31`, JOUEE SANS `unequip_relic`. C'est
      litteralement le montage sur lequel le confond a ete paye : `admecMarshall` porte AU SEED la
      relique `1457`, un exemplaire ALLIE et un exemplaire ENNEMI encadrent une cible neutre, et le
      carrier `admecDominus` est Mechanical. Les deux bras sont donc observes a egalite (mesure de
      #477-r31), et le terme attendu vaut `AttractMechanicals(10) + KardiocoreGalvanus(20)` sur le
      bras ALLIE, `0` sur le bras ENNEMI.
    * `kardio-gate` -- MEME geometrie, carrier NON Mechanical (`orksNob`, celui de #477-r29). Le
      gate `IsMechanical` doit alors couper les DEUX termes : `X_nat = 0` partout, et c'est le
      mutant `SANS-GATE` qui doit mordre.
    * `bookoffate` -- `blackPossession` recoit la relique `BookOfFate` (`--equip-relic`, etat 2)
      cote ALLIE et cote ENNEMI. Le corps natif n'a AUCUN gate : le terme vaut 5 sur toute tuile
      candidate adjacente au porteur AMI, 0 cote ennemi (pre-gate `IsFriend` d'`IterateAbilities`).

Usage (ASCII only, depuis scripts/python) :
  python probe_477r33_non_owner_registry_gaps.py --offline-only
  python probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage kardio
  python probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage kardio-gate
  python probe_477r33_non_owner_registry_gaps.py --board MC1_67 --seed 777 --montage bookoffate
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin import BuildPinRefused                                    # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from probe_193c_move_playbook_terms import (_r, _by_tile, _one, _port_leaves,   # noqa: E402
                                            _exiger_build_des_rva, x_port,
                                            cause_x_nat_non_mesurable)
from probe_212_spiritual_leader_tile_term import _apply_native_via       # noqa: E402
from probe_477r31_attract_mechanicals_camp import LAYOUTS_CAMP           # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: la BASE dont derivent tous les concrets de la famille -- le filtre est le PARENT, pas le NOM.
_BASE = "IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybook`1"
#: la base INTERMEDIAIRE, dont les 10 concrets PARTAGENT leur `CalculateMovementUtilityInSteps`.
_MID = "IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook"

_FACES = {"CalculateMovementUtilityInSteps": "MOVE",
          "CalculateAttackUtilityInSteps": "ATTACK",
          "CalculateRepairUtilityInSteps": "REPAIR"}

#: `PrimarchOfTheFirstLegionNonOwnerPlaybook$$.ctor` recopie le litteral de `NetherRealmCasket`
#: (0x5b6 = 1462). L'id du REGISTRE est 1511 (#433-r4-r3-r1, tranche deux fois : balayage du site
#: d'enregistrement + confront live). Ce n'est donc PAS un ecart a signaler.
_CTOR_MENTEUR = {"PrimarchOfTheFirstLegionNonOwnerPlaybook": (1462, 1511)}


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- recensement offline
# --------------------------------------------------------------------------------------------
def _build_hash() -> str:
    import build_pin
    return build_pin.installed_build()


def _concrets(build: str) -> dict:
    """`nom court -> {"plein": ..., "parent": ...}` pour tout concret de la famille.

    Filtre par PARENT sur `frida/classes.tsv` : direct (`_BASE`) OU via la base intermediaire
    `AdjacentToOwnerNonOwnerPlaybook<T>` (dont les instanciations inflatees ont, elles, `_BASE`
    pour parent). Les DEFINITIONS generiques (`...`1`) et les INSTANCIATIONS (`...<X>`) ne sont pas
    des concrets : elles sont ecartees explicitement."""
    p = ROOT / "data" / "symbols" / build / "frida" / "classes.tsv"
    out = {}
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 3:
                continue
            nom, parent = c[0], c[2]
            if not (parent == _BASE or parent.startswith(_MID)):
                continue
            if nom.endswith("`1") or "<" in nom:      # definition generique / instanciation
                continue
            out[nom.rsplit(".", 1)[-1]] = {"plein": nom, "parent": parent}
    return out


def _faces(build: str, concrets: dict) -> dict:
    """`nom court -> set(FACE)` lu aux methodes `Calculate*UtilityInSteps` de `ghidra/functions.tsv`.

    ⚠ UN CORPS PARTAGE N'A PAS DE SYMBOLE PROPRE. Les 10 concrets d'`AdjacentToOwnerNonOwnerPlaybook
    <T>` n'ont AUCUN `Calculate*` a leur nom : leur face MOVE vit dans l'UNIQUE corps gshared de la
    base intermediaire (#433-r4-r3-r1). Chercher leur face par leur propre nom rend l'ensemble VIDE
    -- exactement le faux negatif que le `CLAUDE.md` interdit de lire comme « pas de face ». Leur
    face est donc CREDITEE depuis leur PARENT, et le parent, lui, est lu."""
    p = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    noms = list(concrets)
    out = {n: set() for n in noms}
    partagees = set()
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            for meth, face in _FACES.items():
                if meth not in line:
                    continue
                if _MID in line:
                    partagees.add(face)
                for n in noms:
                    if n in line:
                        out[n].add(face)
    for n, info in concrets.items():
        if info["parent"].startswith(_MID):
            out[n] |= partagees
    return out


def _ctor_ids(build: str, concrets: dict) -> dict:
    """`nom court -> id passe par son `.ctor`` -- RE-LU dans le binaire, jamais recopie.

    Le corps d'un `.ctor` de cette famille est un `jmp` vers le ctor de base precede d'un
    `mov edx, imm32` (`BA <imm32 LE>`) qui porte l'id d'ability. On releve le PREMIER imm32 dans la
    plage des `TriggeredAbilityType`."""
    from probe_212_bc_key_literals import PE, load_functions, paths_for, function_end
    dll, _meta, tsv = paths_for(build)
    pe = PE(dll)
    by_name, addrs = load_functions(tsv)
    out = {}
    for court, info in concrets.items():
        sym = info["plein"] + "$" + "$.ctor"
        va = by_name.get(sym)
        if va is None:
            out[court] = None
            continue
        body = pe.read(va, function_end(va, addrs) - va) or b""
        val = None
        i = 0
        while i < len(body) - 5:
            if body[i] == 0xBA:
                (v,) = struct.unpack_from("<I", body, i + 1)
                if 1000 <= v <= 2100:
                    val = v
                    break
                i += 5
            else:
                i += 1
        out[court] = val
    return out


def _key_of(build, symbole, pe, meta, by_name, addrs):
    """La cle BC lue par `symbole` -- resolution au LITTERAL (`probe_212`), jamais par prefixe."""
    from probe_212_bc_key_literals import literals_read_by, bc_utilities
    lits, err = literals_read_by(symbole, pe, meta, by_name, addrs)
    if err or not lits:
        return None, err or "aucun literal"
    flat = bc_utilities()
    hits = [s for _t, s in lits if s in flat]
    return (hits or [s for _t, s in lits]), None


#: le SYMBOLE qui lit la cle BC de la face MOVE, par nom court de concret. DEUX formes, et la
#: seconde n'est pas un repli cosmetique :
#:   * derivee DIRECTE  -> la state machine `<CalculateMovementUtilityInSteps>d__N$$MoveNext`. Le
#:     suffixe `d__N` VARIE (`HaywireMineNonOwnerPlaybook` est en `d__5`) : il est CHERCHE ;
#:   * concret d'`AdjacentToOwnerNonOwnerPlaybook<T>` -> le corps de la SM est PARTAGE et ne lit
#:     aucune cle ; la cle vit dans le SEUL point de variation, `$$GetAdjacencyUtility`.
def _move_sm(build: str, concrets: dict) -> dict:
    p = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out = {}
    noms = set(concrets)
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            sym = line.rstrip("\n").split("\t")[-1]
            sm = ("u003CCalculateMovementUtilityInStepsu003Ed__" in sym and "MoveNext" in sym)
            adj = sym.endswith("GetAdjacencyUtility")
            if not (sm or adj):
                continue
            for n in noms:
                marque = ("." + n + ".") if sm else ("." + n + "$")
                if marque in sym and (sm or n not in out):
                    out[n] = sym
    return out


def step0(verbeux: bool = True) -> tuple:
    """Rend `(rc, recensement)`. `recensement[nom court] = {...}`."""
    import io
    import contextlib
    from engine import weights as W
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS

    build = _build_hash()
    print("=== ETAPE 0 -- RECENSEMENT (offline, build %s) ===" % build)
    concrets = _concrets(build)
    faces = _faces(build, concrets)
    ctors = _ctor_ids(build, concrets)
    sms = _move_sm(build, concrets)

    par_face = {}
    for n, fs in faces.items():
        for f in (fs or {"(aucune)"}):
            par_face.setdefault(f, []).append(n)
    print("  concrets derives par le PARENT : %d" % len(concrets))
    for f in sorted(par_face):
        print("    face %-9s %2d" % (f, len(par_face[f])))
    direct = [n for n, i in concrets.items() if i["parent"] == _BASE]
    print("    dont derivees DIRECTES %d, via AdjacentToOwner %d"
          % (len(direct), len(concrets) - len(direct)))

    # noms d'enum, depuis le mirror (bijectif, sous cliquet probe_313)
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    par_id = {int(m): m.name for m in T}

    from probe_212_bc_key_literals import PE, Metadata, load_functions, paths_for
    dll, meta_path, tsv = paths_for(build)
    pe = PE(dll)
    meta = Metadata(meta_path)
    by_name, addrs = load_functions(tsv)

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = (((bc.get("Utilities") or {}).get("Default") or {})
           .get("TriggeredAbilitiesNonOwner") or {})
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()

    rec, rc = {}, 0
    move = sorted(n for n in concrets if "MOVE" in faces[n])
    print("\n  --- les %d faces MOVE ---" % len(move))
    print("  %-42s %-6s %-26s %-8s %s" % ("classe", "id", "ability", "registre", "cle BC (poids)"))
    for n in move:
        cid = ctors.get(n)
        rid = _CTOR_MENTEUR.get(n, (None, None))[1] or cid
        porte = rid in NON_OWNER_MOVE_PLAYBOOKS if rid is not None else False
        keys, kerr = (None, "SM introuvable")
        if n in sms:
            keys, kerr = _key_of(build, sms[n], pe, meta, by_name, addrs)
        if not keys:
            # DEUX classes (`PropheticSentinel`, `TimesplinterMantle`) ne lisent PAS leur cle
            # inline : elle vit dans un champ STATIQUE que le `.cctor` remplit (#433-r4-r3-r1).
            # Chercher la cle au seul corps de la methode rendrait « aucune cle », ce qui est FAUX.
            k2, e2 = _key_of(build, concrets[n]["plein"] + "$" + "$.cctor",
                             pe, meta, by_name, addrs)
            if k2:
                keys, kerr = k2, None
        detail = []
        for k in (keys or ()):
            detail.append("%s=%s/%s" % (k, cap.get(k), wt.sub("TriggeredAbilitiesNonOwner", k)))
        rec[n] = {"id": rid, "ctor_id": cid, "ability": par_id.get(rid),
                  "porte": porte, "cles": list(keys or ()), "sm": sms.get(n),
                  "face": sorted(faces[n]), "plein": concrets[n]["plein"]}
        print("  %-42s %-6s %-26s %-8s %s"
              % (n[:42], rid, par_id.get(rid), "PORTE" if porte else "MANQUE",
                 " ".join(detail) or ("<%s>" % kerr)))

    hors = sorted(n for n in concrets if "MOVE" not in faces[n])
    print("\n  --- les %d faces NON-MOVE (hors feuille 4 cote MOUVEMENT) ---" % len(hors))
    for n in hors:
        print("    %-42s %-8s %s" % (n[:42], ",".join(sorted(faces[n])) or "(aucune)",
                                     par_id.get(ctors.get(n))))

    manquants = [n for n in move if not rec[n]["porte"]]
    print("\n  PORTEES %d / %d faces MOVE  -- MANQUANTES : %d"
          % (len(move) - len(manquants), len(move), len(manquants)))
    # `RedemptionOfTheRisen` (1522) est PORTEE mais deliberement HORS registre (0 porteur, #419).
    from engine.playbook import non_owner as NO
    classes_portees = {getattr(c, "ABILITY_ID", None)
                       for c in vars(NO).values() if isinstance(c, type)}
    ecrites_hors_registre = [n for n in manquants if rec[n]["id"] in classes_portees]
    if ecrites_hors_registre:
        print("    dont ECRITES mais volontairement hors registre (dead code) : %s"
              % ", ".join("%s(%s)" % (n, rec[n]["id"]) for n in ecrites_hors_registre))
    return rc, rec


# --------------------------------------------------------------------------------------------
# ETAPE 0bis -- LE DECOMPTE DES CONFONDS
# --------------------------------------------------------------------------------------------
def step0bis(rec: dict) -> int:
    """Quelles unites du seed BC ARMENT un terme non-owner NON PORTE ?

    Deux voies, et les DEUX comptent : le kit gameconfig (`passiveAbilities` / `mythicAbilities`)
    et la relique `BC.Units[].TertiaryAbility` -- c'est cette seconde-la qui a paye #477-r31, et
    aucun `--equip-relic` ne l'a demandee."""
    import gameconfig as GC
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T

    print("\n=== ETAPE 0bis -- LE DECOMPTE DES CONFONDS ===")
    manquants = {v["id"]: (n, v) for n, v in rec.items() if not v["porte"] and v["id"] is not None}
    #: TROIS etats, pas deux. Un id sans face MOVE non-owner N'EST PAS « porte » : il n'a
    #: simplement AUCUN playbook non-owner, donc il n'arme rien. Les confondre ferait lire
    #: `1475 SupaCyborkBody` comme une entree du registre, ce qu'elle n'est pas.
    connus = {v["id"] for v in rec.values() if v["id"] is not None}
    noms_manquants = {}
    for aid, (n, v) in manquants.items():
        if v["ability"]:
            noms_manquants[v["ability"]] = aid

    # a) les reliques EQUIPEES AU SEED -- personne ne les a demandees.
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    armes_relique = []
    for u in (bc.get("Units") or ()):
        ta = u.get("TertiaryAbility")
        if not ta:
            continue
        nom = next((m.name for m in T if int(m) == int(ta)), "<inconnu %s>" % ta)
        if int(ta) in manquants:
            etat = "NON PORTE"
        elif int(ta) in connus:
            etat = "porte"
        else:
            etat = "aucun playbook non-owner"
        armes_relique.append((u.get("VisualId") or u.get("visualId"), int(ta), nom, etat))
    print("  reliques EQUIPEES AU SEED (BC.Units[].TertiaryAbility) : %d" % len(armes_relique))
    for vis, aid, nom, etat in armes_relique:
        print("    %-22s %-5d %-24s %-26s%s"
              % (vis, aid, nom, etat,
                 "<-- CONFOND ARME" if etat == "NON PORTE" else ""))

    # b) le kit gameconfig des unites SPAWNABLES (le pool) : passif / mythique, sans aucun montage.
    pool = _pool()
    armes_kit = []
    for uid in pool:
        u = GC.unit(uid) or {}
        for voie in ("passiveAbilities", "mythicAbilities", "activeAbilities"):
            for nom in (u.get(voie) or ()):
                if nom in noms_manquants:
                    armes_kit.append((uid, voie, nom, noms_manquants[nom]))
    print("\n  unites DU POOL dont le KIT porte une face MOVE non portee : %d" % len(armes_kit))
    for uid, voie, nom, aid in armes_kit:
        print("    %-22s %-18s %-26s %d" % (uid, voie, nom, aid))
    if not armes_kit:
        print("    (aucune)")

    n = sum(1 for _v, _a, _n, e in armes_relique if e == "NON PORTE") + len(armes_kit)
    print("\n  TOTAL des confonds armes SANS MONTAGE : %d" % n)
    return 0


def _pool() -> list:
    """Le pool spawnable, DERIVE (`rl_duel build --list-pool`), jamais recopie."""
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"], cwd=str(PYDIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [l.strip() for l in (p.stdout or "").splitlines() if l.startswith("   ") and l.strip()]


# --------------------------------------------------------------------------------------------
# ETAPE 1 -- le confront LIVE
# --------------------------------------------------------------------------------------------
#: `kardio` / `kardio-gate` reutilisent la geometrie `camp` de `probe_477r31` -- SANS l'inventer.
CARRIER_MECH = "admecDominus"          # HERO du pool, Mechanical : le gate de 1457 PASSE
#: HERO du pool NON Mechanical -- le gate de 1457 COUPE. ⚠ CE CHOIX A ETE PAYE PAR UNE MESURE
#: ROUGE : le premier carrier essaye etait `orksNob` (celui de #477-r29), et il porte DEUX
#: playbooks natifs a face MOUVEMENT (`IdunBattle.AI.Playbook.Loki.SmashaEadPlaybook$$
#: CalculateMovementUtilityInStepsInternal` et `IdunBattle.AI.Playbook.Loki.
#: UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable`) dont le port ne rend rien : `X_nat`
#: valait **+1 UNIFORME** sur 7 tuiles des DEUX bras. Ce terme-la est ORTHOGONAL a celui qu'on
#: mesure (il ne depend pas du camp), mais il rend l'ACCORD absolu impossible. `eldarAutarch` est
#: le SEUL hero non-Mechanical du pool dont AUCUNE des deux abilities n'a de `*Playbook$$.ctor`
#: dans le binaire -- critere DERIVE (balayage de `ghidra/functions.tsv`), pas suppose.
CARRIER_NONMECH = "eldarAutarch"
MARSHAL_UNIT = "admecMarshall"         # porte AU SEED la relique 1457 KardiocoreGalvanus
TARGET_FOE = "necroWarden"
NEUTRAL_FRIEND = "orksNob"
#: `bookoffate` : porteur AU POOL, relique NON equipee au seed -> etat 2 (`--equip-relic`).
BOF_OWNER = "blackPossession"
#: mover quelconque -- le corps natif de 1461 n'a AUCUN gate. On reprend le carrier du montage
#: `kardio` : c'est le SEUL des deux dont la trajectoire native HOOKE les deux bras sur cette
#: geometrie (MESURE : avec `CARRIER_NONMECH`, 2 puis 5 tuiles hookees, TOUTES du bras ENNEMI --
#: un montage dont un bras n'est pas observe ne separe rien, cf. #477-r29). Son gate
#: `AttractMechanicals` est ici INERTE PAR ALGEBRE : aucune unite du montage ne porte
#: `ActiveAbilityType.DoctrinaImperatives`, donc cette feuille-la vaut 0 partout et n'ajoute aucun
#: terme au mesurande.
BOF_CARRIER = CARRIER_MECH

#: `norncrown` : porteur AU POOL, relique NON equipee au seed -> etat 2 (`--equip-relic`).
#: `tyranNeurothrope` est a la fois le PORTEUR de 1495 et une source `Synapse` du predicat, et il
#: est `Psyker` -- trois roles pour une seule unite, ce qui rend le montage minimal.
NC_OWNER = "tyranNeurothrope"
#: le mover DOIT franchir le gate `Psyker OU Summon`. `thousInfernalMaster` est `Hero, Psyker,
#: WeaverOfFate` -- il n'est NI `Synapse` (sinon il se satisferait lui-meme partout, regime
#: DEGENERE) NI Mechanical (sinon `AttractMechanicals` s'ajouterait).
NC_CARRIER = "thousInfernalMaster"
#: le CONTROLE du gate : meme geometrie, mover NI Psyker NI Summon.
NC_CARRIER_NOGATE = CARRIER_NONMECH     # `eldarAutarch` : Flying, Hero, TeleportStrike

MONTAGES = ("kardio", "kardio-gate", "bookoffate", "norncrown", "norncrown-gate")


def _layout(board: str) -> dict:
    lay = LAYOUTS_CAMP.get(board)
    if lay is None:
        raise SystemExit("[477-r33] aucune geometrie `camp` pour le board %r (connus : %s). "
                         "Un placement hors zone plate reintroduirait l'asymetrie d'elevation que "
                         "le montage exclut." % (board, ", ".join(sorted(LAYOUTS_CAMP))))
    return lay


def build_extra(board: str, montage: str) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage avec la garde."""
    lay = _layout(board)
    if montage in ("kardio", "kardio-gate"):
        carrier = CARRIER_MECH if montage == "kardio" else CARRIER_NONMECH
        p_units = [carrier, MARSHAL_UNIT]
        places = [("--place", "%s:%d,%d" % (carrier, lay["carrier"][0], lay["carrier"][1])),
                  ("--place", "%s:%d,%d" % (MARSHAL_UNIT, lay["ally"][0], lay["ally"][1])),
                  ("--a-place", "%s:%d,%d" % (MARSHAL_UNIT, lay["foe"][0], lay["foe"][1])),
                  ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
        if carrier != NEUTRAL_FRIEND:
            p_units.append(NEUTRAL_FRIEND)
            places.insert(2, ("--place", "%s:%d,%d"
                              % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])))
        a_units = [MARSHAL_UNIT, TARGET_FOE]
    elif montage in ("norncrown", "norncrown-gate"):
        # MEME geometrie `camp`. Le terme de 1495 ne lit NI le porteur NI sa position : ce qui le
        # declenche est un ami `Synapse` dans le disque de rayon 2 de la tuile candidate. La cible
        # neutre est donc remplacee par un SECOND `tyranNeurothrope` ENNEMI, ce qui donne des
        # `Synapse` DES DEUX CAMPS a geometrie miroir -- le seul montage ou « amis » et « toutes
        # les unites » se separent.
        carrier = NC_CARRIER if montage == "norncrown" else NC_CARRIER_NOGATE
        p_units = [carrier, NC_OWNER, NEUTRAL_FRIEND]
        a_units = [NC_OWNER, TARGET_FOE]
        places = [("--place", "%s:%d,%d" % (carrier, lay["carrier"][0], lay["carrier"][1])),
                  ("--place", "%s:%d,%d" % (NC_OWNER, lay["ally"][0], lay["ally"][1])),
                  ("--place", "%s:%d,%d" % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])),
                  ("--a-place", "%s:%d,%d" % (NC_OWNER, lay["foe"][0], lay["foe"][1])),
                  ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
    else:
        # MEME geometrie que `kardio-gate`, au PORTEUR pres : carrier + porteur ALLIE + un ami
        # neutre du cote temoin ; cote adverse, le porteur ENNEMI (c'est lui qui exerce le pre-gate
        # `IsFriend`) et la cible neutre. L'ami neutre n'est pas decoratif : sans lui la trajectoire
        # native ne hooke qu'un seul bras (MESURE -- 2 puis 5 tuiles, toutes du bras ENNEMI).
        p_units = [BOF_CARRIER, BOF_OWNER, NEUTRAL_FRIEND]
        a_units = [BOF_OWNER, TARGET_FOE]
        places = [("--place", "%s:%d,%d" % (BOF_CARRIER, lay["carrier"][0], lay["carrier"][1])),
                  ("--place", "%s:%d,%d" % (BOF_OWNER, lay["ally"][0], lay["ally"][1])),
                  ("--place", "%s:%d,%d" % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])),
                  ("--a-place", "%s:%d,%d" % (BOF_OWNER, lay["foe"][0], lay["foe"][1])),
                  ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
    out = ["--seed-bc", "<pose par l'appelant>",
           "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    for flag, val in places:
        out += [flag, val]
    # #419-r6-r3 -- NEUTRALISATION du canal CRIT/BLOCK sur les QUATRE faces.
    #
    # L'axe de ce fichier est l'UTILITE DE MOUVEMENT des playbooks non-owner : ce qu'il mesure est
    # une trajectoire native et un accord de tuiles, jamais un montant de degat. Le crit et le
    # block y sont donc HORS AXE par construction -- et depuis la bascule du defaut a << equiper >>
    # (#419-r6) ils raccourcissent la bataille, qui atteint `Finished` avant les pas discriminants
    # (mesure : << trajectoire native epuisee au pas 17 >>, 6 failed / 35 passed).
    #
    # ⚠ Ce n'est PAS `--no-bis-items`, et la difference est le coeur de l'arbitrage. `--no-bis-items`
    # restituerait le regime DEGENERE d'avant #419-r5 -- crit et block structurellement impossibles
    # sur TOUTE unite, plus la perte des autres slots d'items (`FixedArmor` sur 49 unites du seed,
    # `Health` sur 4) : ce serait acheter la couleur au prix de la mesure. Les quatre drapeaux
    # ci-dessous epinglent QUATRE SCALAIRES sur CE montage, le reste de l'etat equipe demeurant.
    # C'est le remede-type etabli par #419-r5 et applique 17 fois par #419-r6 : local, ecrit au
    # build, et motive par l'AXE du fichier.
    #
    # Les QUATRE faces sont necessaires : `--crit`/`--block-player` n'epinglent que les p-units,
    # `--crit-target`/`--block-target` que les a-units -- et ce montage a des porteurs des DEUX
    # cotes (`NC_OWNER` allie ET ennemi), donc deux faces sur quatre laisseraient le canal ouvert.
    return out + ["--hp-player", "100000", "--hp-target", "100000",
                  "--crit", "0,0", "--crit-target", "0,0",
                  "--block-player", "0,0", "--block-target", "0,0"]


def _seed_bc_montage(out_path: Path, montage: str) -> Path:
    """Le seed BC du montage.

    ⚠ `kardio` / `kardio-gate` : on NE RETIRE PAS la relique. C'est tout l'objet du cas -- le
    confond de #477-r31 devient ici le MESURANDE. On VERIFIE seulement qu'elle est bien la : si le
    seed changeait, la mesure ne mesurerait plus rien et il faut le savoir AVANT.
    `bookoffate` : la relique `BookOfFate` est POSEE (etat 2), sur le porteur ALLIE et sur le
    porteur ENNEMI -- c'est ce second-la qui exerce le pre-gate `IsFriend`."""
    import catalog_inject
    bc = catalog_inject._load_seed(None)
    if montage in ("norncrown", "norncrown-gate"):
        rep = catalog_inject.equip_relic(bc, NC_OWNER, "NornCrown", 1)
        print("  relique posee : %s -> %s (id %s), %d entree(s) BC.Units patchee(s), "
              "config ajoutee=%s, porteurs autorises=%s"
              % (rep["unitId"], rep["ability"], rep["abilityId"], rep["unitsPatched"],
                 rep["configAdded"], rep["allowedUnits"]))
        if not rep["unitsPatched"]:
            print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
    elif montage in ("kardio", "kardio-gate"):
        porte = [u for u in (bc.get("Units") or ())
                 if (u.get("VisualId") or u.get("visualId")) == MARSHAL_UNIT]
        ta = [u.get("TertiaryAbility") for u in porte]
        print("  relique AU SEED de %s : TertiaryAbility=%s (attendu 1457)" % (MARSHAL_UNIT, ta))
        if 1457 not in [t for t in ta if t]:
            print("  ATTENTION : le seed ne porte PLUS 1457 sur %s -- le montage ne mesure plus le "
                  "terme vise ; relire `_seed_bc_montage` avant de croire quoi que ce soit"
                  % MARSHAL_UNIT)
    else:
        rep = catalog_inject.equip_relic(bc, BOF_OWNER, "BookOfFate", 1)
        print("  relique posee : %s -> %s (id %s), %d entree(s) BC.Units patchee(s), "
              "config ajoutee=%s, porteurs autorises=%s"
              % (rep["unitId"], rep["ability"], rep["abilityId"], rep["unitsPatched"],
                 rep["configAdded"], rep["allowedUnits"]))
        if not rep["unitsPatched"]:
            print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return out_path


def _build(seed, board, montage, seed_bc: Path, state: Path):
    extra = build_extra(board, montage)
    extra[1] = str(seed_bc)
    argv = ([sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
             "--state-file", str(state)] + extra)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:]))
        return None
    print((p.stdout or "").strip()[-700:])
    return json.loads(state.read_text())["runnerId"]


# ---- les modeles confrontes ---------------------------------------------------------------
def _owners_adj(tile, lc, ability_id: int, camp: str) -> int:
    """Nombre de porteurs de `ability_id` du camp `camp` ADJACENTS a `tile` (adjacence NATIVE)."""
    from engine import battle_query as bq
    elev, neigh = lc.get("elev_by_pos"), bq.neigh_map(lc)
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    return sum(1 for u in (src or ())
               if u.get("pos") and bq.are_entities_adjacent(tile, tuple(u["pos"]), elev, neigh)
               and int(ability_id) in (u.get("triggered") or ()))


def _synapse_near(tile, lc, camp: str, radius: int, avec_self: bool) -> int:
    """Nombre d'unites `Synapse` du camp `camp` dans le DISQUE de rayon `radius` autour de `tile`.

    `is_surrounding` (et non `are_entities_adjacent`) : l'itinerateur natif
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` est
    PUREMENT geometrique et ne porte AUCUNE porte d'elevation. `avec_self` rejoue le fait que
    `GetSurroundingFriends(actor, ...)` n'exclut PAS l'acteur, encore sur son origine."""
    from engine import battle_query as bq
    from engine.entities.traits.unit_trait import UnitTrait
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    n = sum(1 for u in (src or ())
            if u.get("pos") and bq.is_surrounding(tile, tuple(u["pos"]), radius, True)
            and UnitTrait.Synapse.name in (u.get("traits") or ()))
    if avec_self and camp == "ami":
        sp = lc.get("self_pos")
        if sp and bq.is_surrounding(tile, tuple(sp), radius, True) \
                and int(UnitTrait.Synapse) in {int(t) for t in (lc.get("unit_traits") or ())}:
            n += 1
    return n


def _models_norncrown(tile, leaves, lc, wt) -> tuple:
    """Les modeles du montage `norncrown` -- ils ne portent PAS sur les memes axes que les autres.

    Le corps de 1495 ne lit NI `owner` NI sa position : son observable est le voisinage `Synapse`
    du MOVER, dans un disque de rayon 2. Les mutants declarent donc :
      * `CAMP-DEUX`  : les `Synapse` des DEUX camps compteraient (le natif filtre « amis du mover »
                       via `GetSurroundingFriends`) ;
      * `RAYON-1`    : le disque serait l'ADJACENCE (rayon 1) au lieu du litteral `2` ;
      * `SANS-SELF`  : l'acteur serait exclu de son propre voisinage ;
      * `SANS-GATE`  : le gate `Psyker OU Summon` sur le mover serait absent ;
      * `PRE-GATE-OFF`: le pre-gate `IsFriend` d'`IterateAbilities` serait absent -> le dispatcher
                       sommerait le terme UNE FOIS PAR PORTEUR, ennemi compris (+2x sur ce montage) ;
      * `ABSENT`     : l'etat du port AVANT cette tranche."""
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.utilities.utility_type import UtilityType
    from engine.playbook.non_owner import NornCrownNonOwnerPlaybook as NC

    w = float(wt.sub("TriggeredAbilitiesNonOwner", NC.KEY))
    tile = (tile[0], tile[1])
    ids = {int(t) for t in (lc.get("unit_traits") or ())}
    gate = bool(ids & {int(UnitTrait.Psyker), int(UnitTrait.Summon)})
    na = _synapse_near(tile, lc, "ami", NC.RADIUS, True)
    ne = _synapse_near(tile, lc, "ennemi", NC.RADIUS, True)
    n_own_ami = _owners_adj_any(lc, int(T.NornCrown), "ami")
    n_own_foe = _owners_adj_any(lc, int(T.NornCrown), "ennemi")
    porte = float(leaves.get(int(UtilityType.TriggeredAbilitiesNonOwner), 0.0))
    mods = {
        "PORT":         porte,
        "CAMP-DEUX":    float(w * n_own_ami * (1 if (gate and (na + ne)) else 0)),
        "RAYON-1":      float(w * n_own_ami
                              * (1 if (gate and _synapse_near(tile, lc, "ami", 1, True)) else 0)),
        "SANS-SELF":    float(w * n_own_ami
                              * (1 if (gate and _synapse_near(tile, lc, "ami", NC.RADIUS, False))
                                 else 0)),
        "SANS-GATE":    float(w * n_own_ami * (1 if na else 0)),
        "PRE-GATE-OFF": float(w * (n_own_ami + n_own_foe) * (1 if (gate and na) else 0)),
        "ABSENT":       0.0,
    }
    return mods, {"na": na, "ne": ne, "gate": gate,
                  "owners": (n_own_ami, n_own_foe), "w": w}


def _owners_adj_any(lc, ability_id: int, camp: str) -> int:
    """Nombre de porteurs de `ability_id` du camp `camp` SUR LE PLATEAU (sans condition de tuile).

    Le dispatcher natif itere TOUTES les `TriggeredAbility` de la bataille : pour un playbook dont
    le corps ne lit pas le porteur, le terme est donc multiplie par le NOMBRE de porteurs retenus
    par le pre-gate, pas par leur proximite."""
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    return sum(1 for u in (src or ()) if int(ability_id) in (u.get("triggered") or ()))


def _models(tile, leaves, lc, wt, montage) -> dict:
    """Le terme rendu par CHAQUE modele -- le port (lu dans son VRAI foyer) et ses mutants.

    Chaque mutant DECLARE ce qu'il observe :
      * `CAMP-DEUX`   : le pre-gate `IsFriend` d'`IterateAbilities` n'existerait pas ;
      * `CAMP-ENNEMI` : le camp serait inverse ;
      * `SANS-GATE`   : le gate du corps (`IsMechanical` pour 1457) serait absent ;
      * `COUNT (x n)` : le terme s'ajouterait une fois PAR porteur adjacent (le natif ne le fait
                        pas : un seul `yield` par playbook et par paire) ;
      * `ABSENT`      : l'etat du port AVANT cette tranche."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.utilities.utility_type import UtilityType
    from engine.playbook.non_owner import _is_mechanical

    if montage in ("norncrown", "norncrown-gate"):
        return _models_norncrown(tile, leaves, lc, wt)
    if montage in ("kardio", "kardio-gate"):
        aid, key = int(T.KardiocoreGalvanus), "KardiocoreGalvanus_AdjacentFriendly"
        gate = _is_mechanical(lc)
    else:
        aid, key = int(T.BookOfFate), "BookOfFate_AdjacentSummons"
        gate = True
    w = float(wt.sub("TriggeredAbilitiesNonOwner", key))
    na = _owners_adj(tile, lc, aid, "ami")
    ne = _owners_adj(tile, lc, aid, "ennemi")
    porte = float(leaves.get(int(UtilityType.TriggeredAbilitiesNonOwner), 0.0))
    return {
        "PORT":          porte,
        "CAMP-DEUX":     float(w * (1 if (gate and (na + ne)) else 0)),
        "CAMP-ENNEMI":   float(w * (1 if (gate and ne) else 0)),
        "SANS-GATE":     float(w * (1 if na else 0)),
        "COUNT (x n)":   float(w * na) if gate else 0.0,
        "ABSENT":        0.0,
    }, {"na": na, "ne": ne, "gate": bool(gate), "w": w}


def _bras(prof, tiles):
    """(porteur AMI adjacent seul, porteur ENNEMI adjacent seul) -- les deux bras a EGALITE."""
    return ([t for t in tiles if prof[t]["na"] > 0 and prof[t]["ne"] == 0],
            [t for t in tiles if prof[t]["ne"] > 0 and prof[t]["na"] == 0])


def mesurer(call, rid, montage="kardio", max_steps=25, trace=print) -> dict:
    """Marche la trajectoire NATIVE jusqu'au pas ou les DEUX bras sont HOOKES, arme les hooks de
    `scorer-damage-trace` pour UN SEUL `aiStepDryRun`, et rend la mesure.

    `call(method, body, timeout)` est INJECTE (probe -> RPC de session ; garde -> fixture)."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    carrier = {"kardio": CARRIER_MECH, "kardio-gate": CARRIER_NONMECH,
               "bookoffate": BOF_CARRIER, "norncrown": NC_CARRIER,
               "norncrown-gate": NC_CARRIER_NOGATE}[montage]
    dv0 = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    cid = next((u.get("id") for u in (dv0.get("units") or [])
                if u.get("visualId") == carrier and u.get("ctrl")), None)
    trace("  carrier u%s (%s)" % (cid, carrier))
    if cid is None:
        return {"erreur": "carrier %s absent de la bataille" % carrier}

    step, seen = 0, 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"erreur": "trajectoire native epuisee au pas %d (%s) apres %d activation(s)"
                              % (step, dry.get("error"), seen)}
        if dry.get("activatedUnitId") != cid:
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        seen += 1
        dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = call("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        wt = W.load()
        pred = _scene.build_predictor(call, rid)
        ctx = _ai_ctx.build(call, rid, dv, mov_by_unit, cid, wt, pred)
        tiles = list(ctx.action_tiles or [])
        prof = {}
        for t in tiles:
            leaves, lc = _port_leaves(ctx, t)
            prof[t] = _models(t, leaves, lc, wt, montage)[1]
        ba, bb = _bras(prof, tiles)
        trace("  pas %-3d activation #%d : %d candidates | bras AMI=%d bras ENNEMI=%d"
              % (step, seen, len(tiles), len(ba), len(bb)))
        if not (ba and bb):
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        armement = call("scorerDamageTraceOn", {"runnerId": rid}, 90)
        call("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
        try:
            call("aiStepDryRun", {"runnerId": rid}, 90)
            tterm = call("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
            elev = call("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
            leaf = call("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        finally:
            call("scorerDamageTraceOff", {"runnerId": rid}, 60)

        tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
        el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
        te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                      "col", "row", "value")
        if not tt:
            # AUCUN tier Comparable a ce pas (le natif n'a evalue aucune tuile d'ATTAQUE) : ce
            # n'est pas une panne de hook, c'est une activation qui ne porte pas le regime. On
            # CONTINUE la marche -- s'arreter la ferait rendre un echec de MONTAGE comme un echec
            # de MESURE.
            trace("  aucun event tileTerm a ce pas -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        hooked = [t for t in tiles if t in tt]
        ha, hb = _bras(prof, hooked)
        trace("  tuiles HOOKEES=%d | bras AMI=%d bras ENNEMI=%d" % (len(hooked), len(ha), len(hb)))
        if not (ha and hb):
            trace("  les hooks n'ont pas couvert les DEUX bras -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        rows = []
        for t in sorted(hooked):
            vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
            leaves, lc = _port_leaves(ctx, t)
            mods, p = _models(t, leaves, lc, wt, montage)
            x = (vt - ve - vf) if None not in (vt, ve, vf) else None
            rows.append({"tile": t, "x_nat": x, "x_port": x_port(leaves), "models": mods,
                         "na": p["na"], "ne": p["ne"], "gate": p["gate"],
                         "tile7": vt, "elev": ve, "tile_eff": vf,
                         "leaves": {k: v for k, v in leaves.items() if abs(v) > 1e-9}})
        # ⚠ LE CRAN : une mesure ou AUCUNE ligne n'a de `x_nat` n'est pas une mesure, c'est un
        # SILENCE. Sans lui, `divergences` rend 0 pour TOUS les modeles (elle saute les `None`),
        # `test_le_natif_suit_le_PORT` passe A VIDE, et seules les contre-epreuves rougissent --
        # 12 rouges qui accusent les montages pour une panne de capteur (mesure du 2026-08-15,
        # build passe a `t6dpr4k06g`). On rend une `erreur` qui NOMME la panne : c'est
        # `test_le_montage_a_bien_ete_mesure` qui la porte, avec le remede.
        if not any(r["x_nat"] is not None for r in rows):
            return {"erreur": cause_x_nat_non_mesurable(call, rid, tt, el, te, armement),
                    "rows_muettes": len(rows)}
        _l0 = _port_leaves(ctx, tiles[0])[1]
        return {"rows": rows, "prof": prof, "step": step, "uid": cid, "montage": montage,
                "bras_a": ha, "bras_b": hb,
                "friend_units": list(_l0.get("friend_units") or ()),
                "enemy_units": list(_l0.get("enemy_units") or ())}

    return {"erreur": "aucun pas DISCRIMINANT en %d pas (%d activations du carrier)"
                      % (max_steps, seen)}


def divergences(rows) -> dict:
    """`{modele: nombre de tuiles ou X_nat != X_<modele>}` -- la contre-epreuve, chiffree."""
    out = {}
    for nom in (rows[0]["models"] if rows else {}):
        n = 0
        for r in rows:
            if r["x_nat"] is None:
                continue
            xm = r["x_port"] - r["models"]["PORT"] + r["models"][nom]
            if abs(r["x_nat"] - xm) > 1e-6:
                n += 1
        out[nom] = n
    return out


#: le mutant qui EST la question de chaque montage. S'il ne mord pas, le montage est DEGENERE.
MUTANT_SEPARATEUR = {"kardio": "CAMP-DEUX", "kardio-gate": "SANS-GATE",
                     "bookoffate": "CAMP-DEUX", "norncrown": "CAMP-DEUX",
                     "norncrown-gate": "SANS-GATE"}
#: les montages dont le CARRIER est choisi pour que le gate du corps COUPE. L'inertie qui en
#: decoule est DECLAREE ici et ASSERTIONNEE dans les deux sens par `run`.
MONTAGES_GATE_COUPE = ("kardio-gate", "norncrown-gate")


def run(call, rid, montage="kardio", max_steps=25) -> int:
    mes = mesurer(call, rid, montage, max_steps)
    if mes.get("erreur"):
        print("  ROUGE : %s" % mes["erreur"])
        return 1
    rows = mes["rows"]
    print("\n  tuile      nA nE gate | Tile7nat  Elev  TileEff  X_nat  | X_port  DELTA")
    bad = 0
    for r in rows:
        d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %2d %2d %4s | %-9s %-5s %-8s %-6s | %-7.4g %s"
              % (r["tile"], r["na"], r["ne"], r["gate"], r["tile7"], r["elev"], r["tile_eff"],
                 r["x_nat"], r["x_port"], ("%.4g" % d) if d is not None else "?"))

    if bad:
        from engine.utilities.utility_type import UtilityType
        print("\n  VENTILATION du port sur les tuiles en DESACCORD (feuilles non nulles) :")
        for r in rows:
            d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
            if d is None or abs(d) <= 1e-6:
                continue
            noms = []
            for k, v in sorted(r["leaves"].items()):
                try:
                    noms.append("%s=%g" % (UtilityType(k).name, v))
                except ValueError:
                    noms.append("<%d>=%g" % (k, v))
            print("    %-10s manque %+.4g | %s" % (r["tile"], d, ", ".join(noms) or "(aucune)"))
        print("  VOISINS vus par le port (pos / triggered / actives) :")
        for camp, us in (("ami", mes.get("friend_units") or ()),
                         ("ennemi", mes.get("enemy_units") or ())):
            for u in us:
                print("    %-6s %-22s @%-8s trg=%s act=%s"
                      % (camp, u.get("vis"), u.get("pos"), list(u.get("triggered") or ()),
                         list(u.get("active") or ())))

    mordu = divergences(rows)
    print("\n  CONTRE-EPREUVE (X_nat vs X_<modele>, sur les %d tuiles hookees) :" % len(rows))
    for nom, n in mordu.items():
        print("    %-14s divergences = %d / %d   a_mordu=%s"
              % (nom, n, len(rows), "OUI" if n else "NON"))

    rc = 0
    if bad:
        print("\n  ACCORD : ROUGE -- %d tuile(s) en desaccord X_nat vs X_port sur %d"
              % (bad, len(rows)))
        rc = 1
    else:
        print("\n  ACCORD : VERT -- 0 desaccord X_nat vs X_port sur %d tuiles" % len(rows))

    sep = MUTANT_SEPARATEUR[montage]
    if not mordu.get(sep):
        print("  SEPARATION : ROUGE -- le mutant %r rend la MEME chose que le port sur ce "
              "montage : REGIME DEGENERE, rien n'est tranche" % sep)
        rc = 1
    else:
        print("  SEPARATION : VERT -- le mutant %r diverge du natif sur %d tuile(s)"
              % (sep, mordu[sep]))

    # INERTIES declarees et ASSERTIONNEES DANS LES DEUX SENS.
    if montage in MONTAGES_GATE_COUPE:
        # le carrier ne franchit PAS le gate du corps : le terme est nul partout, donc tout mutant
        # qui ne touche PAS au gate est INERTE PAR ALGEBRE. C'est declare, pas subi.
        inertes = [m for m in mordu if m not in ("SANS-GATE", "PORT")]
        gate_actif = any(r["gate"] for r in rows)
        actifs = [m for m in inertes if mordu.get(m)]
        if gate_actif or actifs:
            print("  GATE : le gate a PASSE (gate=%s) ou un mutant declare INERTE a mordu (%s) -- "
                  "l'inertie declaree est FAUSSE" % (gate_actif, ", ".join(actifs) or "-"))
            rc = 1
        else:
            print("  GATE : INERTE PAR ALGEBRE (le carrier ne franchit pas le gate) -- %s ne "
                  "peuvent PAS mordre, et c'est ASSERTIONNE ; seul `SANS-GATE` separe ici"
                  % ", ".join(sorted(inertes)))
    else:
        gate_actif = all(r["gate"] for r in rows)
        if not gate_actif:
            print("  GATE : ROUGE -- le gate ne passe pas sur toutes les tuiles alors que le "
                  "carrier devrait le franchir : le montage ne mesure pas ce qu'il annonce")
            rc = 1
        else:
            print("  GATE : PASSE sur les %d tuiles (assertionne)" % len(rows))
        # INERTIE PAR ALGEBRE, declaree et ASSERTIONNEE DANS LES DEUX SENS : le carrier du montage
        # `norncrown` (`thousInfernalMaster`) n'est PAS `Synapse`, donc il ne peut pas se satisfaire
        # lui-meme -> `SANS-SELF` ne DOIT pas mordre. Le declarer sans l'assertionner reviendrait a
        # lire un silence comme une confirmation.
        if montage == "norncrown":
            from engine.entities.traits.unit_trait import UnitTrait
            import gameconfig as GC
            syn = UnitTrait.Synapse.name in ((GC.unit(NC_CARRIER) or {}).get("traits") or ())
            if syn or mordu.get("SANS-SELF"):
                print("  SELF : le carrier %s est Synapse (%s) ou `SANS-SELF` a MORDU -- l'inertie "
                      "declaree est FAUSSE" % (NC_CARRIER, syn))
                rc = 1
            else:
                print("  SELF : INERTE PAR ALGEBRE (le carrier %s n'est pas Synapse) -- "
                      "`SANS-SELF` ne peut pas mordre, et c'est ASSERTIONNE ; le volet self est "
                      "EXERCE offline (`test_477r33_non_owner_playbooks_live.py`)" % NC_CARRIER)
        for m in sorted(mordu):
            if m in ("PORT", "ABSENT", "SANS-SELF", MUTANT_SEPARATEUR[montage]) or mordu.get(m):
                continue
            print("  NON SEPARE ICI : le mutant %r rend la MEME chose que le port sur ce montage "
                  "-- son axe n'y est pas exerce, et le taire le ferait passer pour confirme." % m)
    print("  VERDICT : %s" % ("ROUGE" if rc else "VERT"))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--montage", default="kardio", choices=MONTAGES)
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    rc0, rec = step0()
    rc0 |= step0bis(rec)
    if a.offline_only:
        return rc0
    if rc0:
        print("ETAPE 0 ROUGE -> on n'arme rien")
        return rc0
    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    call = (lambda m, b, t=90: _r(sid, m, b, t))
    print("\n=== ETAPE 1 (live) -- montage %s ===" % a.montage)
    if a.runner is not None:
        return run(call, a.runner, a.montage, a.max_steps)
    tag = uuid.uuid4().hex[:8]
    state = Path(a.state_file) if a.state_file else (
        ROOT / "logs" / "runners" / ("probe477r33-%s.json" % tag))
    seed_bc = ROOT / "logs" / "runners" / ("probe477r33-seedbc-%s.json" % tag)
    _seed_bc_montage(seed_bc, a.montage)
    rid = _build(a.seed, a.board, a.montage, seed_bc, state)
    if rid is None:
        return 1
    print("  runner %d seed=%s board=%s montage=%s" % (rid, a.seed, a.board, a.montage))
    try:
        return run(call, rid, a.montage, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        for p in (state, seed_bc):
            try:
                p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
