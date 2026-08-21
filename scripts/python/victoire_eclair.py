"""VICTOIRE ECLAIR : gagne-t-on dans le nombre de rounds imparti ?

    python scripts/python/victoire_eclair.py                    # tous les replays de campagne
    python scripts/python/victoire_eclair.py <fichier.json>

LA REGLE, LUE DANS LE JEU : << Win the battle within {ROUNDS} rounds to double your guaranteed
Coins reward >> (`BattlePreviewPopup_LightningVictory_Tooltip`), et le tutoriel dit << Win by
Round 4 >> -- donc le seuil est INCLUSIF. Le nombre de rounds est PROPRE A CHAQUE BATAILLE : il
vit dans `battles.campaigns.<Type>[].battles[].lightningVictory` (campaign1 noeud 19 : 4).
`globalValues.lightningVictoryMultiplier` vaut 2 -- c'est le doublement des pieces.

CE QU'ON COMPTE, ET POURQUOI CELUI-LA. Le replay ne porte AUCUN champ << victoire eclair >> :
`BattleResult` sort vide (`EndReason: null`, `UnitsDefeated: []`). Le compte se lit dans le flux
d'evenements, sur `Tag=Match_AmountOfTurnsStartedByCurrentPlayer` -- le compteur que le jeu tient
lui-meme. On prend son MAXIMUM sur tout le flux : c'est le round atteint quand le match se
termine.

⚠ LE VAINQUEUR EST UNE ENTITE, PAS UN NUMERO DE JOUEUR. `Tag=Match_Winner:3` designe l'entite 3,
et c'est le flux d'ouverture qui dit laquelle porte le joueur (`Action=AddPlayer Entity=3
Tag=Player_Id:11`). On resout donc entite -> `Player_Id` -> le joueur nomme `player` dans
`BC.Player.Players`, au lieu d'ecrire << 3 >> en dur : rien ne garantit cette valeur d'une
bataille a l'autre.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gameconfig import _find_gameconfig            # noqa: E402

CAMPAGNE = RACINE / "data" / "replays" / "campaign"
TYPE_DU_PREFIXE = {"Campaign": "Standard", "Elite": "Elite",
                   "Mirror": "Mirror", "EliteMirror": "EliteMirror"}
_SEUILS = None


def noeud_normalise(v):
    """`"05"`, `"5"` et `5` designent LE MEME noeud -- on compare des ENTIERS.

    (!)MESURE DU 2026-08-22 : la campagne 3 numerote ses batailles avec un zero de tete
    (`Campaign3_05`, `Campaign3_01`), la campagne 1 non (`Campaign1_19`). Une comparaison de
    CHAINES rendait donc << seuil d'eclair ABSENT du gameconfig pour elite3 noeud 5 >> sur une
    bataille qui l'a. Le meme vice frappait l'appariement par plateau du classeur.

    Ce qui n'est pas numerique reste compare tel quel, en minuscules."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return str(v).strip().lower()


def seuils():
    """(type, campagne#, battleId) -> nombre de rounds pour la victoire eclair."""
    global _SEUILS
    if _SEUILS is not None:
        return _SEUILS
    cg = json.loads(_find_gameconfig().read_text(encoding="utf-8"))
    cg = cg.get("clientGameConfig") or cg
    t = {}
    for typ, camps in (cg["battles"]["campaigns"] or {}).items():
        if not isinstance(camps, list):
            continue
        for c in camps:
            for b in (c.get("battles") or []):
                cid = b.get("campaignId")
                if cid is None:
                    continue
                t[(typ, int(cid), noeud_normalise(b.get("battleId")))] = b.get("lightningVictory")
    _SEUILS = t
    return t


def seuil_de(identifiant, noeud):
    """Le nombre de rounds pour l'eclair, depuis l'IDENTIFIANT de campagne (`elite4`) et le noeud.

    Rend `None` si le gameconfig ne le porte pas -- NON MESURE, jamais un defaut devine."""
    from raids_plan import table_des_campagnes
    typ = None
    for ident, t, _ in table_des_campagnes().values():
        if ident == identifiant:
            typ = t
            break
    if typ is None:
        return None
    m = re.search(r"(\d+)$", str(identifiant))
    if not m:
        return None
    return seuils().get((typ, int(m.group(1)), noeud_normalise(noeud)))


def entite_du_joueur(replay):
    """L'entite qui porte le camp du JOUEUR -- resolue, jamais ecrite en dur."""
    bc = replay.get("BattleConfiguration") or {}
    joueurs = ((bc.get("Player") or {}).get("Players") or {})
    ids = [int(k) for k, v in joueurs.items()
           if isinstance(v, dict) and v.get("Name") == "player"]
    if not ids:
        return None, "aucun joueur nomme `player` dans `BC.Player.Players`"
    pid = ids[0]
    for m in replay.get("Messages") or []:
        f = m.get("OutputStream") or ""
        for mm in re.finditer(r"Action=AddPlayer Entity=(\d+)\s*\n\s*Tag=Player_Id:(\d+)", f):
            if int(mm.group(2)) == pid:
                return int(mm.group(1)), None
    return None, "aucun `AddPlayer` n'associe une entite au `Player_Id` %d" % pid


def verdict(replay, identifiant=None):
    """Rend un dict. Toute valeur NON MESURABLE sort a `None` -- jamais rabattue sur un defaut.

    ⛔ `identifiant` (`elite2`, `eliteMirror3`...) EST EXIGE POUR LIRE LE SEUIL, et son absence
    n'est PAS rattrapable par `BC.Id`. Les quatre types portent le meme prefixe : `Campaign3_01`
    designe la Standard comme l'EliteMirror. Deduire << Standard >> du prefixe faisait lire le
    seuil d'UNE AUTRE BATAILLE -- mesure du 2026-08-22 sur `eliteMirror3_1`, ou le verdict
    << manquee, 3 rounds pour 2 >> comparait a la Standard (2) au lieu de l'EliteMirror (4).
    C'etait donc un ECLAIR, annonce manque.

    Sans identifiant, le seuil sort a `None` et `eclair` reste `None` -- on ne devine pas."""
    bc = replay.get("BattleConfiguration") or {}
    bcid = str(bc.get("Id"))
    r = {"bcId": bcid, "rounds": None, "seuil": None, "vainqueur": None,
         "entiteJoueur": None, "gagne": None, "eclair": None, "refus": None}

    ent, err = entite_du_joueur(replay)
    r["entiteJoueur"] = ent
    if err:
        r["refus"] = err

    rounds, vainqueur = 0, None
    for m in replay.get("Messages") or []:
        f = m.get("OutputStream") or ""
        for mm in re.finditer(r"Tag=Match_AmountOfTurnsStartedByCurrentPlayer:(\d+)", f):
            rounds = max(rounds, int(mm.group(1)))
        mm = re.search(r"Tag=Match_Winner:(\d+)", f)
        if mm:
            vainqueur = int(mm.group(1))
    r["rounds"] = rounds or None
    r["vainqueur"] = vainqueur
    if vainqueur is None:
        r["refus"] = (r["refus"] or "") + " ; aucun `Match_Winner` -- bataille NON TERMINEE"
        return r
    if ent is not None:
        r["gagne"] = (vainqueur == ent)

    m = re.match(r"^Campaign(\d+)_(\w+)$", bcid)
    if not m:
        r["refus"] = (r["refus"] or "") + " ; `BC.Id` %r hors forme `Campaign<n>_<noeud>`" % bcid
        return r
    if identifiant is None:
        r["refus"] = ((r["refus"] or "") + " ; identifiant de campagne NON FOURNI -- `BC.Id` ne "
                      "dit pas le type, le seuil reste NON MESURE")
        return r
    r["identifiant"] = identifiant
    r["seuil"] = seuil_de(identifiant, m.group(2))
    if r["seuil"] is None:
        r["refus"] = ((r["refus"] or "")
                      + " ; pas de `lightningVictory` pour %s noeud %s" % (identifiant, m.group(2)))
        return r
    if r["gagne"] and r["rounds"] is not None:
        r["eclair"] = r["rounds"] <= r["seuil"]
    return r


def ligne(nom, v):
    if v.get("eclair") is True:
        etat = "ECLAIR"
    elif v.get("eclair") is False:
        etat = "manquee"
    elif v.get("gagne") is False:
        etat = "PERDUE"
    else:
        etat = "?"
    return ("%-34s %-8s round %-4s / seuil %-4s  vainqueur=%s joueur=%s%s"
            % (nom[:32], etat, v.get("rounds"), v.get("seuil"),
               v.get("vainqueur"), v.get("entiteJoueur"),
               ("   [%s]" % v["refus"].strip(" ;")) if v.get("refus") else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fichier", nargs="?", default=None)
    args = ap.parse_args()
    src = [Path(args.fichier)] if args.fichier else sorted(CAMPAGNE.glob("*.json"))
    if not src:
        print("aucun replay de campagne dans %s" % CAMPAGNE)
        return 0
    n_ok = 0
    for p in src:
        d = json.loads(p.read_text(encoding="utf-8"))
        # L'identifiant est dans le NOM CANONIQUE (`elite2_14-716107981.json`) -- c'est la seule
        # source qui porte le TYPE, `BC.Id` ne le portant pas.
        ident = p.stem.split("_")[0] if "_" in p.stem else None
        v = verdict(d, ident)
        print(ligne(p.name, v))
        if v.get("eclair"):
            n_ok += 1
    print()
    print("%d victoire(s) eclair sur %d replay(s)" % (n_ok, len(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
