#!/usr/bin/env python
"""#477-r16 -- la REGLE d'allocation des entites ECS : derivee du decompile, confrontee live.

CE QUE CE PROBE TRANCHE
-----------------------
Un emetteur de flux cote port doit reproduire l'`Entity=<id>` de chaque ligne. Cet id est un
COMPTEUR D'ALLOCATION GLOBAL (#477-r15). La question est : sa sequence est-elle reproductible
depuis la `BattleConfiguration` ?

LA REGLE, LUE DANS LE DECOMPILE (aucune loi ajustee sur des mesures)
-------------------------------------------------------------------
Allocateur UNIQUE -- `IdunBattle.Entities.Components.MatchComponent$$NextId` :
    this.<+0x10> += 1 ; return this.<+0x10>          (PRE-incrementation)
`MatchComponent$$.ctor` pose le champ a **1**. `MatchComponent$$ReturnLastId` le decremente
(rollback), et n'est appele que par `AddTileOperation$$Execute` / `$$CreateTile`.

Les NEUF sites d'appel de `NextId` sont la liste EXHAUSTIVE des allocateurs (xrefs Ghidra) :
    AddPlayerOperation$$Execute .......................... 1 par joueur
    AddEnvironmentAbilityOperation$$Execute .............. 1 (deux sites EXCLUSIFS)
    AddEnvironmentAbilityOperation$$CreateEntity ......... 1 (deux sites EXCLUSIFS)
    AddTileOperation$$Execute / $$CreateTile ............. 1 par tuile, rollback si Build rend null
    AddUnitOperation$$Execute ........................... 1 + 1 PAR PIED (le 2e site est DANS
                                                           une boucle sur les tuiles occupees)
    AddMachineOperation$$Execute ........................ 1 par machine
    AddMachineOfWarPlatformOperation$$Execute ........... 1 par plateforme
    AddEffectOperation$$Execute ......................... 1 par effet

Ordre du deploiement -- `IdunBattle.Operations.SetupGameOperation$$Execute`, sequence FIXE :
    InitializeMatch(matchEntityId=1, ...)   -> l'entite Match prend l'id LITTERAL 1, puis
                                               `InitializeMatchOperation$$Execute` fait `+= 1`
                                               sur le compteur : il passe de 1 a 2, donc
                                               **l'id 2 n'est JAMAIS attribue**
    AddPlayers()                            -> SortedDictionary (ordre par cle, deterministe)
    AddEnvironmentAbilities()               -> List de `GetEnvironmentAbilities`
    AddTiles()                              -> for row in 0..Width-1 { for col in 0..Height-1 }
    SetupRoom / RevealHumanPlayerRoom       -> N'ALLOUENT RIEN (absents des xrefs de NextId)
    AddPredefinedUnits()                    -> puis AddPredefinedMachines, AddBossUnit

D'ou la prediction, SANS aucun parametre ajuste :
    premier id de tuile = 3 + P + E
    premier id d'unite  = premier id de tuile + T          (T = Width * Height du board)
    ids de tuiles       = intervalle CONTIGU de longueur T
    pas entre deux unites mono-tuile = 2  (l'unite + son unique UnitFoot)

P se lit dans le BC (`Player.Players`). E, lui, N'EST PAS ENTIEREMENT DANS LE BC : il vaut
    |BC.EnvironmentAbilities| + |BC.EnhancementsEnvironmentAbilities|
  + 2 constantes EN DUR dans `SetupGameOperation$$GetEnvironmentAbilities` (0x5cb, 0x18)
  + |StaticBattleRules.DamageTrait$$GetDamageTraitAbilities()|   (table STATIQUE du binaire)
  + |GetDerivedEnvironmentAbilities(k)| pour chaque passif du BC (table STATIQUE du binaire)
  + 1 si GameMode == SyncPVP (0x52e)
Les deux tables statiques ne sont pas dans la BC : un emetteur doit les MIRRORER. Le probe
derive la 1re depuis l'enum `IdunBattle.Entities.Enum.DamageTrait` (versionne) et affiche la
2nde comme un RESIDU NOMME, jamais comme un zero silencieux.

CE QUE LE PROBE FAIT
--------------------
Volet OFFLINE (aucun runner) : re-derive P, E et la prediction depuis `data/` versionne.
Volet LIVE (--session)      : monte un runner par board, lit `replayOutputStream`, et
                              confronte la sequence reelle a la prediction IMPRIMEE AVANT.

⚠ Trois boards de TAILLES DISTINCTES sont imposes : deux boards de meme taille rendent les
memes ids et se lisent, a tort, comme une preuve d'independance (piege paye en #477-r15 :
MC1_67 et C1_70 font tous deux 63 tuiles). Deux points valident n'importe quelle droite --
le probe REFUSE de conclure sous trois tailles distinctes.

USAGE
    python scripts/python/probe_477r16_allocation_entites_ecs.py                 # offline seul
    python scripts/python/probe_477r16_allocation_entites_ecs.py --session <sid> # + confrontation
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RACINE = HERE.parent.parent
DATA = RACINE / "data"
HOST = "http://127.0.0.1:8765"

# Les deux constantes ajoutees EN DUR par SetupGameOperation$$GetEnvironmentAbilities.
# Lues au decompile (`IncludeEnvironmentAbility(this, list, 0x5cb)` puis `(..., 0x18)`), pas
# devinees. Elles ne figurent nulle part dans la BattleConfiguration.
ENV_ABILITIES_EN_DUR = (0x5CB, 0x18)
# Ajoutee seulement si le GameMode est SyncPVP (`idun.Shared.Battle.GameMode` 8=SyncPVP).
ENV_ABILITY_SYNCPVP = 0x52E

# Trois boards de tailles DISTINCTES : 5x7=35, 7x9=63, 7x10=70. Les trois tailles sont les
# SEULES presentes dans les ~780 dumps (verifie par balayage), donc ce triplet epuise l'axe.
BOARDS_DEFAUT = ("C1_02", "MC1_67", "C4_09")
ROSTER_P = "adeptCanoness,adeptCanoness,adeptRetributor"
ROSTER_A = "adeptHospitaller,adeptMorvenn"


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


# --------------------------------------------------------------------------- offline

def build_courant() -> str:
    p = DATA / "symbols"
    noms = [d.name for d in p.iterdir() if d.is_dir() and (d / "BUILD").is_file()]
    if not noms:
        raise MesureImpossible("aucun dossier data/symbols/<build> avec un fichier BUILD")
    if len(noms) == 1:
        return noms[0]
    # Plusieurs builds versionnes : prendre celui dont le BUILD se nomme lui-meme.
    for n in noms:
        if (p / n / "BUILD").read_text(encoding="utf-8").strip() == n:
            return n
    return sorted(noms)[-1]


def membres_enum(build: str, nom: str) -> dict[int, str]:
    """{ordinal: nom} pour un enum de la table versionnee. Leve si l'enum a disparu."""
    f = DATA / "symbols" / build / "frida" / "enums.tsv"
    if not f.is_file():
        raise MesureImpossible("table d'enums absente : %s" % f)
    for ligne in f.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#!"):
            continue
        champs = ligne.split("\t")
        if len(champs) >= 2 and champs[0] == nom:
            out = {}
            for m in champs[1].split(","):
                if "=" in m:
                    k, v = m.split("=", 1)
                    out[int(k)] = v
            return out
    raise MesureImpossible("enum introuvable dans la table du build %s : %s" % (build, nom))


def lire_seed_bc() -> dict:
    f = DATA / "seed-bc.json"
    if not f.is_file():
        raise MesureImpossible("seed BC absent : %s (python dump_boards.py)" % f)
    return json.loads(f.read_text(encoding="utf-8"))


def taille_board(board_id: str) -> tuple[int, int]:
    """(Width, Height) du dump versionne. T = Width * Height = nb de cellules balayees."""
    for kind in ("pvp", "syncPvp", "global"):
        f = DATA / "boards" / kind / ("%s.json" % board_id)
        if f.is_file():
            b = json.loads(f.read_text(encoding="utf-8"))["board"]
            return int(b["Width"]), int(b["Height"])
    raise MesureImpossible("board absent des dumps versionnes : %s (python dump_boards.py)" % board_id)


def deriver_regle() -> dict:
    """Re-derive P, E et l'offset depuis les ENTREES versionnees. Aucun chiffre fige ici."""
    build = build_courant()
    bc = lire_seed_bc()

    joueurs = (bc.get("Player") or {}).get("Players") or {}
    p = len(joueurs)

    env = bc.get("EnvironmentAbilities") or {}
    e_bc = len(env.get("EnvironmentAbilities") or []) + len(env.get("EnhancementsEnvironmentAbilities") or [])

    traits = membres_enum(build, "IdunBattle.Entities.Enum.DamageTrait")
    # `-1=Unknown` n'est pas un trait ; les autres membres sont les abilities rendues par
    # `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities`.
    n_traits = len([k for k in traits if k >= 0])

    modes = membres_enum(build, "idun.Shared.Battle.GameMode")
    mode_nom = bc.get("GameMode")
    est_syncpvp = (mode_nom == modes.get(8))

    e_derive = e_bc + len(ENV_ABILITIES_EN_DUR) + n_traits + (1 if est_syncpvp else 0)
    return {
        "build": build,
        "P": p,
        "cles_joueurs": sorted(joueurs, key=lambda k: int(k)) if joueurs else [],
        "E_bc": e_bc,
        "E_en_dur": len(ENV_ABILITIES_EN_DUR),
        "E_damage_traits": n_traits,
        "noms_damage_traits": [traits[k] for k in sorted(traits) if k >= 0],
        "E_syncpvp": 1 if est_syncpvp else 0,
        "E_derive": e_derive,
        "game_mode": mode_nom,
        # premier id de tuile = 3 + P + E  (cf. en-tete : match=1, compteur a 2 apres
        # InitializeMatch, donc le premier NextId rend 3)
        "premier_id_tuile": 3 + p + e_derive,
    }


# ----------------------------------------------------------------------------- live

def rpc(session: int, method: str, args: dict, timeout: int = 60) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 45000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def build_runner(board: str, state_file: Path) -> int:
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", board,
           "--p-units", ROSTER_P, "--a-units", ROSTER_A,
           "--record-replay", "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=900)
    if not state_file.is_file():
        sortie = (p.stderr or "") + (p.stdout or "")
        if "maintenance" in sortie or "runner creation paused" in sortie or "503" in sortie:
            raise MesureImpossible("NON CONFRONTE -- fenetre DRAIN (creation de runner refusee)")
        raise MesureImpossible("build %s echoue : %s" % (board, sortie[-400:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def sequence_du_flux(flux: str) -> dict:
    """Extrait, dans l'ordre du flux, les `Entity=` de chaque famille d'action."""
    out = {"AddTile": [], "AddUnit": [], "AddPlayer": [], "ordre": []}
    for s in flux.split("\n"):
        m = re.match(r"\s*Action=(\w+) Entity=(-?\d+)", s)
        if not m:
            continue
        act, ent = m.group(1), int(m.group(2))
        out["ordre"].append((act, ent))
        if act in out:
            out[act].append(ent)
    return out


def mesurer_board(session: int, board: str) -> dict:
    w, h = taille_board(board)
    tmp = Path(tempfile.gettempdir()) / ("r16-alloc-%s.json" % board)
    rid = build_runner(board, tmp)
    try:
        flux = rpc(session, "replayOutputStream", {"runnerId": rid}).get("outputStream") or ""
        if not flux:
            raise MesureImpossible("flux VIDE sur %s -- enregistreur non arme ?" % board)
        seq = sequence_du_flux(flux)
        tuiles = seq["AddTile"]
        unites = seq["AddUnit"]
        return {
            "board": board, "runner": rid, "W": w, "H": h, "T_attendu": w * h,
            "tuiles": tuiles, "unites": unites, "joueurs": seq["AddPlayer"],
            "actions_distinctes": sorted({a for a, _ in seq["ordre"]}),
        }
    finally:
        try:
            rpc(session, "disposeRunner", {"runnerId": rid}, timeout=45)
        except MesureImpossible:
            pass


def analyser(m: dict, premier_id_tuile_prevu: int) -> dict:
    """Confronte UNE mesure a la prediction. Aucun ajustement : tout est deja fixe."""
    tuiles, unites = m["tuiles"], m["unites"]
    a = {"board": m["board"]}
    a["nb_tuiles"] = len(tuiles)
    a["T_concorde"] = (len(tuiles) == m["T_attendu"])
    a["tuiles_contigues"] = bool(tuiles) and tuiles == list(range(tuiles[0], tuiles[0] + len(tuiles)))
    a["premier_id_tuile"] = tuiles[0] if tuiles else None
    a["premier_id_tuile_prevu"] = premier_id_tuile_prevu
    a["offset_concorde"] = (a["premier_id_tuile"] == premier_id_tuile_prevu)
    a["premier_id_unite"] = unites[0] if unites else None
    a["premier_id_unite_prevu"] = (premier_id_tuile_prevu + m["T_attendu"]) if tuiles else None
    a["unite_concorde"] = (a["premier_id_unite"] == a["premier_id_unite_prevu"])
    a["pas_unites"] = [b - x for x, b in zip(unites, unites[1:])]
    a["pas_tous_a_2"] = all(d == 2 for d in a["pas_unites"]) if a["pas_unites"] else None
    a["unites_apres_tuiles"] = bool(tuiles and unites and unites[0] == tuiles[-1] + 1)
    return a


# ---------------------------------------------------------------------------- sortie

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", type=int, default=None,
                    help="id de session Frida ; sans lui, seul le volet OFFLINE tourne")
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT),
                    help="boards a jouer -- TAILLES DISTINCTES exigees (au moins trois)")
    a = ap.parse_args()

    print("=" * 78)
    print("#477-r16 -- regle d'allocation des entites ECS")
    print("=" * 78)

    try:
        r = deriver_regle()
    except MesureImpossible as e:
        print("VERDICT : PAS MESURE -- %s" % e)
        return 2

    print("\n[OFFLINE] la regle, re-derivee des entrees versionnees (build %s)" % r["build"])
    print("  MatchComponent$$.ctor pose le compteur a 1 ; InitializeMatchOperation$$Execute")
    print("  l'incremente -> 2. Entite Match = id 1 (litteral), et l'id 2 n'est JAMAIS attribue.")
    print("  P (Player.Players du seed BC) ........................ %d  %s"
          % (r["P"], r["cles_joueurs"]))
    print("  E = env abilities allouees, decomposee :")
    print("      depuis la BC (Environment + Enhancements) ........ %d" % r["E_bc"])
    print("      constantes EN DUR de GetEnvironmentAbilities ..... %d  %s"
          % (r["E_en_dur"], [hex(x) for x in ENV_ABILITIES_EN_DUR]))
    print("      GetDamageTraitAbilities (enum DamageTrait) ....... %d  %s"
          % (r["E_damage_traits"], r["noms_damage_traits"]))
    print("      SyncPVP (0x52e) -- GameMode=%s ................... %d"
          % (r["game_mode"], r["E_syncpvp"]))
    print("      -> E derive ...................................... %d" % r["E_derive"])
    print("  PREDICTION  premier id de tuile = 3 + P + E = %d" % r["premier_id_tuile"])
    print("              premier id d'unite   = ce nombre + Width*Height du board")
    print("  NON DERIVE ICI : GetDerivedEnvironmentAbilities(passif) lit une table STATIQUE du")
    print("    binaire, pas la BC. Elle est supposee vide sur ce seed ; l'ecart mesure ci-dessous")
    print("    la borne. Residu #477-r16-r1.")

    if a.session is None:
        print("\n[LIVE] PAS MESURE -- aucune --session fournie (volet offline seul).")
        print("VERDICT : regle DERIVEE, NON CONFRONTEE.")
        return 0

    boards = [x.strip() for x in a.boards.split(",") if x.strip()]
    tailles = {}
    for b in boards:
        try:
            w, h = taille_board(b)
            tailles[b] = w * h
        except MesureImpossible as e:
            print("\n[LIVE] board ecarte : %s" % e)
    if len(set(tailles.values())) < 3:
        print("\n[LIVE] REFUS DE CONCLURE : %d taille(s) distincte(s) parmi %s."
              % (len(set(tailles.values())), tailles))
        print("  Deux points valident n'importe quelle droite -- il en faut TROIS, de tailles")
        print("  differentes. Piege deja paye : MC1_67 et C1_70 font tous deux 63 tuiles.")
        return 2

    print("\n[LIVE] prediction par board, IMPRIMEE AVANT LA MESURE :")
    for b in boards:
        if b in tailles:
            print("  %-9s T=%-3d -> tuiles %d..%d, premiere unite %d"
                  % (b, tailles[b], r["premier_id_tuile"],
                     r["premier_id_tuile"] + tailles[b] - 1,
                     r["premier_id_tuile"] + tailles[b]))

    mesures, drain = [], False
    for b in boards:
        if b not in tailles:
            continue
        try:
            mesures.append(mesurer_board(a.session, b))
        except MesureImpossible as e:
            print("  PAS MESURE (%s) : %s" % (b, e))
            if "DRAIN" in str(e):
                drain = True
    if not mesures:
        print("\nVERDICT : %s" % ("NON CONFRONTE -- fenetre DRAIN." if drain
                                  else "PAS MESURE -- aucun board monte."))
        return 2

    analyses = [analyser(m, r["premier_id_tuile"]) for m in mesures]
    print("\n[LIVE] mesure")
    for m, an in zip(mesures, analyses):
        print("\n  [%s] runner=%d, %dx%d = %d cellules ; actions du flux : %s"
              % (m["board"], m["runner"], m["W"], m["H"], m["T_attendu"], m["actions_distinctes"]))
        print("      tuiles : %d emises, contigues=%s, 1re=%s (prevu %s) -> %s"
              % (an["nb_tuiles"], an["tuiles_contigues"], an["premier_id_tuile"],
                 an["premier_id_tuile_prevu"], "OK" if an["offset_concorde"] else "ECART"))
        print("      unites : %s" % m["unites"])
        print("      1re unite=%s (prevu %s) -> %s ; pas=%s ; juste apres les tuiles=%s"
              % (an["premier_id_unite"], an["premier_id_unite_prevu"],
                 "OK" if an["unite_concorde"] else "ECART",
                 an["pas_unites"], an["unites_apres_tuiles"]))

    tout_T = all(x["T_concorde"] for x in analyses)
    tout_contigu = all(x["tuiles_contigues"] for x in analyses)
    tout_offset = all(x["offset_concorde"] for x in analyses)
    tout_unite = all(x["unite_concorde"] for x in analyses)
    offsets = {x["premier_id_tuile"] for x in analyses}

    print("\n" + "-" * 78)
    print("VERDICT")
    print("  1. nb de tuiles emises == Width*Height ........................ %s" % ("OUI" if tout_T else "NON"))
    print("  2. ids de tuiles CONTIGUS ..................................... %s" % ("OUI" if tout_contigu else "NON"))
    print("  3. offset initial INVARIANT par board (%s) ..... %s"
          % (sorted(offsets), "OUI" if len(offsets) == 1 else "NON"))
    print("  4. offset == la prediction derivee (%d) ........................ %s"
          % (r["premier_id_tuile"], "OUI" if tout_offset else "NON"))
    print("  5. premier id d'unite == offset + T ........................... %s" % ("OUI" if tout_unite else "NON"))
    if not tout_offset and len(offsets) == 1:
        print("     ECART = %d entite(s) non derivee(s) -- probablement"
              % (list(offsets)[0] - r["premier_id_tuile"]))
        print("     GetDerivedEnvironmentAbilities (table statique). Residu #477-r16-r1.")
    ok = tout_T and tout_contigu and len(offsets) == 1 and tout_unite
    print("\n  => L'ordre d'allocation est %s"
          % ("MECANIQUE : un emetteur peut le reproduire." if ok
             else "MIS EN DEFAUT sur au moins un axe -- lire le detail ci-dessus."))
    return 0 if (ok and tout_offset) else 1


if __name__ == "__main__":
    raise SystemExit(main())
