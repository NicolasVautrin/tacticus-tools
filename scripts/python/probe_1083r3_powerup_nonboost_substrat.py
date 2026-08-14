"""#1083-r3 -- ce que le SUBSTRAT publie pour les quatre `PowerUp_*` non-boost NON PORTES.

PROBE (mesure), pas test : il imprime et rend `rc 0` tant que la mesure aboutit. Son objet est de
rendre RE-DERIVABLE la raison pour laquelle `PowerUp_Bomb`, `PowerUp_Reinforcement`,
`PowerUp_ReinforcementShield` et `PowerUp_Resurrect` ne sont pas portes -- et de faire ROUGIR la
premisse si elle change (un champ qui apparait cote port = le blocage est leve).

100 % OFFLINE : il lit `data/seed-bc.json` (entree VERSIONNEE) et les SOURCES du port. Aucun runner,
aucun RPC, aucun decompile.

    python scripts/python/probe_1083r3_powerup_nonboost_substrat.py

CE QU'IL ETABLIT, et pourquoi c'est la bonne question :

  * `PowerUp_Bomb` porte un gate `IsHumanPlayer(OriginalOwner(Actor))` qui est LOAD-BEARING : sans
    lui la bombe partirait aussi pour une equipe pilotee par l'IA, ce que le natif REFUSE
    (`If(cond, ..., null)`). Ce gate est une DISJONCTION sur `PlayerType` :
    `PlayerType == 0 (Human) OU == 4 (HumanAI)`.
  * La donnee EXISTE dans la BC (`BC.Player.Players[].PlayerType`) et elle est DISCRIMINANTE sur
    notre seed (0 / 1 / 2 pour les joueurs 11 / 12 / 13). Le gate n'est donc pas vacant : il
    separe reellement un joueur des deux autres.
  * Mais elle n'est PROJETEE nulle part cote port : aucun `PlayerComponent`, aucun `player_type`.
    Le port ne peut donc pas evaluer le gate -- et un port qui l'omettrait serait FAUX de façon
    PERMISSIVE (le pire regime : ni erreur, ni crash).
  * Les trois autres ecrivent dans `DraftingComponent` / `PlayerComponent`, dont les champs
    existent dans la BC (`Drafting`, `ReinforcementShield`) et n'ont AUCUN lecteur porte : la
    boucle qui les consomme (drafting du mode Survival) n'est pas portee.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
SEED_BC = RACINE / "data" / "seed-bc.json"
PORT = RACINE / "scripts" / "python" / "engine"

#: `IdunBattle.Entities.Enum.PlayerType` (build `rnca9r7q6c`) -- le membre NOMME, jamais l'ordinal.
PLAYER_TYPE = {0: "Human", 1: "AI", 2: "Environment", 3: "Network", 4: "HumanAI"}
#: `DSLTriggers$$IsHumanPlayer` = `<PlayerTypeTrigger>(p, 0) | <PlayerTypeTrigger>(p, 4)`.
HUMAINS = (0, 4)


def mesurer_bc():
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    joueurs = bc["Player"]["Players"]
    ordre = bc["Player"].get("TurnOrder")
    print("[1083-r3] BC.Player.Players : %d joueurs (TurnOrder=%s)" % (len(joueurs), ordre))
    humains, non_humains = [], []
    for pid, p in sorted(joueurs.items(), key=lambda kv: int(kv[0])):
        pt = p.get("PlayerType")
        nom = PLAYER_TYPE.get(pt, "?")
        est_humain = pt in HUMAINS
        (humains if est_humain else non_humains).append(pid)
        print("   joueur %-4s PlayerType=%s (%-11s) IsHumanPlayer=%-5s "
              "Drafting=%-3s ReinforcementShield=%s"
              % (pid, pt, nom, est_humain, "oui" if p.get("Drafting") else "non",
                 p.get("ReinforcementShield")))
    print("[1083-r3] gate `IsHumanPlayer` : VRAI pour %s, FAUX pour %s" % (humains, non_humains))
    if not humains or not non_humains:
        print("[1083-r3] ATTENTION -- TEMOIN DEGENERE : le gate ne separe RIEN sur ce seed.")
        print("           Un accord mesure dans ce regime ne prouverait pas que le gate est porte.")
    else:
        print("[1083-r3] temoin NON DEGENERE : le gate separe reellement %d joueur(s) de %d."
              % (len(humains), len(non_humains)))
    # Les champs consommes par les trois mecaniques de Survival.
    champs = sorted({k for p in joueurs.values() for k in p})
    print("[1083-r3] champs publies par joueur : %s" % (champs,))
    return humains, non_humains


def _est_declaration_denum(pile) -> bool:
    """VRAI si le noeud courant est une cible d'assignation DANS une classe qui derive d'un Enum.

    ⚠ Ce cran existe parce que sa premiere version manquait : un balayage TEXTUEL comptait
    `TriggeredAbilityType.PowerUp_ReinforcementShield` (la DECLARATION du membre, dans
    `entities/triggered_ability_type.py`) comme la preuve qu'un canal existait -- et concluait
    « blocage leve » alors que rien ne LIT ce membre. Un nom DECLARE n'est pas un LECTEUR ; c'est
    exactement la faute que ce probe est cense debusquer, commise par le probe lui-meme."""
    for n in pile:
        if isinstance(n, ast.ClassDef):
            for base in n.bases:
                nom = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if "Enum" in str(nom) or "Flag" in str(nom):
                    return True
    return False


def _identifiants_executables(chemin):
    """Rend `(identifiant, ligne)` pour tout nom qui est REELLEMENT evalue : `Name`, `Attribute`,
    mot-cle d'appel, parametre, nom de classe/fonction. Ignore par construction :
      * les `ast.Constant` -- donc les DOCSTRINGS et toute chaine (le decompile CITE y vit) ;
      * les commentaires, qui n'entrent meme pas dans l'AST ;
      * les membres declares dans un `class X(IntEnum)` (cf. `_est_declaration_denum`).
    C'est ce qui separe « le mot apparait » de « le port sait le lire »."""
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return
    pile = []

    def visite(n, parents):
        if isinstance(n, ast.Name):
            if not (isinstance(n.ctx, ast.Store) and _est_declaration_denum(parents)):
                yield n.id, n.lineno
        elif isinstance(n, ast.Attribute):
            yield n.attr, n.lineno
        elif isinstance(n, ast.keyword) and n.arg:
            yield n.arg, n.lineno
        elif isinstance(n, ast.arg):
            yield n.arg, n.lineno
        elif isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, n.lineno
        for enfant in ast.iter_child_nodes(n):
            for r in visite(enfant, parents + [n]):
                yield r

    for r in visite(arbre, pile):
        yield r


def mesurer_port():
    """Ce que le PORT expose -- la moitie qui manque. Balayage de TOUT `engine/`, par AST : un canal
    ajoute AILLEURS doit faire changer ce compte."""
    motifs = {
        "PlayerType / player_type": r"^(player_type|PlayerType)$",
        "PlayerComponent (classe)": r"^PlayerComponent$",
        "DraftingComponent (classe)": r"^DraftingComponent$",
        "reinforcement point": r"^(reinforcement_point|ReinforcementPoint|AddReinforcementPoint)$",
        "reinforcement shield": r"^(reinforcement_shield|ReinforcementShield)$",
        "resurrect draft": r"^(resurrect_draft|ResurrectDraft|AddResurrectDraftPoint)$",
        "IsHumanPlayer": r"^(IsHumanPlayer|is_human_player)$",
        # TEMOIN DE CONTROLE -- il DOIT rendre non-zero. Les sept motifs ci-dessus rendent tous
        # ZERO, et un recenseur qui ne rend que des zeros ne permet pas de distinguer « aucun
        # canal » de « le balayage ne visite rien ». `current_player_id` est l'axe joueur qui EST
        # porte (cf. `entities/triggers.py`), donc son zero serait la preuve d'un balayage casse.
        "[controle] current_player_id": r"^current_player_id$",
    }
    fichiers = sorted(PORT.rglob("*.py"))
    print()
    print("[1083-r3] balayage AST du port : %d fichiers sous engine/" % len(fichiers))
    print("          (un nom DECLARE dans un `class X(IntEnum)` n'est PAS compte comme lecteur,")
    print("           et les docstrings/commentaires ne sont pas visites du tout)")
    par_fichier = {f: list(_identifiants_executables(f)) for f in fichiers}
    resultats = {}
    for libelle, motif in motifs.items():
        rx = re.compile(motif)
        sites = []
        for f, ids in par_fichier.items():
            for nom, ligne in ids:
                if rx.match(nom):
                    sites.append("%s:%d" % (f.relative_to(RACINE).as_posix(), ligne))
        resultats[libelle] = sites
        print("   %-28s %-9s sites=%d" % (libelle, "CANAL" if sites else "ABSENT", len(sites)))
        for ref in sites[:5]:
            print("        -> %s" % ref)
    return resultats


def main() -> int:
    if not SEED_BC.exists():
        print("[1083-r3] MESURE IMPOSSIBLE : %s absent (rien n'est conclu)" % SEED_BC)
        return 2
    humains, non_humains = mesurer_bc()
    res = mesurer_port()
    print()
    if not res["[controle] current_player_id"]:
        print("[1083-r3] BALAYAGE CASSE : le temoin de controle `current_player_id` rend ZERO,")
        print("          alors qu'il est porte. Aucun des zeros ci-dessus ne prouve donc quoi que")
        print("          ce soit -- RIEN N'EST CONCLU.")
        return 3
    print("[1083-r3] temoin de controle OK (%d sites) : les zeros ci-dessus sont des MESURES."
          % len(res["[controle] current_player_id"]))
    print("[1083-r3] ---- CONSEQUENCE ----")
    code_pt = res["PlayerType / player_type"]
    if code_pt:
        print("   `PlayerType` a desormais un CANAL cote port (%d site(s)) : le blocage de"
              % len(code_pt))
        print("   `PowerUp_Bomb` est potentiellement LEVE -- relire la case-doc #1083-r3 avant")
        print("   de conclure, et re-jouer la confrontation.")
    else:
        print("   `PlayerType` n'existe cote port QU'EN COMMENTAIRE -> le gate `IsHumanPlayer` de")
        print("   `PowerUp_Bomb` n'est pas evaluable. L'omettre rendrait le port PERMISSIF (la")
        print("   bombe partirait pour l'IA), donc `PowerUp_Bomb` reste NON PORTE. BLOCAGE: seeding.")
    manquants = [lib for lib in ("reinforcement point", "reinforcement shield", "resurrect draft")
                 if not res[lib]]
    print("   Mecaniques de Survival sans AUCUN lecteur porte : %s" % (manquants,))
    print("   -> `PowerUp_Reinforcement` / `_ReinforcementShield` / `_Resurrect` : la BC PORTE les")
    print("      champs (`Drafting`, `ReinforcementShield`) mais rien ne les lit. BLOCAGE: etage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
