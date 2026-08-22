"""LIBERER LE LATCH QUI BLOQUE `StartMatch` -- quand aucune voie native ne le fait.

    python scripts/python/deverrouiller_startmatch.py            # CONSTATE, n'ecrit rien
    python scripts/python/deverrouiller_startmatch.py --forcer   # ecrit `IsActive = 0`

`ViewCommandExecutor$$StartMatch` refuse de monter une bataille quand un booleen statique
<< un match tourne deja >> est arme : il journalise via `LogError` et RETOURNE, sans code de
retour ni exception. Porteur : `idun.IdunMainView` / `<IsActive>k__BackingField`.

(!)DEUX REGIMES, ET UN SEUL SE REPARE SANS ECRIRE.
  - latch arme AVEC une bataille montee -> `OnBattleSurrender` + `ContinueSurrender` suffisent,
    et c'est ce qu'il faut faire : on passe par le jeu. Ce script le DIT et refuse d'ecrire.
  - latch arme SANS bataille -> il n'y a rien a abandonner, aucune voie native ne le rend, et
    seule une relance du jeu le levait. C'est le seul cas ou `--forcer` a un sens.

⛔ ET ON N'ECRIT PAS SUR UN DIAGNOSTIC PARTIEL. Le script refuse tant qu'il n'a pas etabli les
TROIS conditions : latch a 1, aucune bataille active, chargeur au repos. Un latch a 1 pendant un
chargement est peut-etre simplement... un chargement.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante                    # noqa: E402
from sandbox_mode import Jeu                                # noqa: E402

NS, CLS, CHAMP = "idun", "IdunMainView", "<IsActive>k__BackingField"


def lire_latch(j):
    """`True` / `False` / `None` = NON MESURE. Jamais rabattu sur `False`."""
    r = j.rpc("staticFieldProbe", [{"ns": NS, "cls": CLS}], 120000) or {}
    for f in (r.get("fields") or []):
        if f.get("name") == CHAMP:
            brut = f.get("rawHex")
            return None if brut is None else (int(brut, 16) != 0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--forcer", action="store_true",
                    help="ECRIRE `IsActive = 0`. Sans lui : on constate, rien n'est ecrit.")
    args = ap.parse_args()

    sid = session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante.")
        return 2
    j = Jeu(args.hote, sid)

    latch = lire_latch(j)
    s = j.rpc("retreatStatus", [], 60000) or {}
    active = s.get("batailleActive")
    etape = (j.rpc("loaderStatus", [], 60000) or {}).get("etape")
    print("latch `%s` = %s | batailleActive = %s | chargeur etape = %s"
          % (CHAMP, latch, active, etape))

    if latch is None:
        print("REFUS : latch NON MESURE -- on n'ecrit pas sur ce qu'on n'a pas lu.")
        return 2
    if latch is False:
        print("RIEN A FAIRE : le latch est deja a 0, `StartMatch` n'est pas bloque par lui.")
        return 0
    if active is True:
        print("NE PAS FORCER : une bataille est MONTEE. La voie du jeu la libere proprement :")
        print("   retreatInvoke OnBattleSurrender puis ContinueSurrender")
        print("   (c'est ce que fait deja `campagne_rejeu_boucle.py` en sortie de boucle)")
        return 1
    if etape not in (0, None) or (etape is None):
        print("REFUS : chargeur a l'etape %s -- un latch a 1 pendant un CHARGEMENT est peut-etre "
              "simplement un chargement. On n'ecrit pas la-dessus." % etape)
        return 2

    if not args.forcer:
        print()
        print("LATCH ORPHELIN CONFIRME : arme, aucune bataille, chargeur au repos.")
        print("Aucune voie native ne le libere dans ce regime -- relancer avec `--forcer`.")
        return 0

    r = j.rpc("staticFieldWrite",
              [{"ns": NS, "cls": CLS, "field": CHAMP, "valeur": 0, "confirmer": True}], 120000)
    print("ecriture :", json.dumps(r, ensure_ascii=False)[:400])
    # ⚠ ON RELIT PAR NOTRE PROPRE VOIE, pas seulement le `apres` rendu par le RPC : une mutation
    #   se confronte depuis l'exterieur de ce qui l'a faite.
    apres = lire_latch(j)
    print("latch RELU : %s" % apres)
    if apres is False:
        print("LIBERE -- `StartMatch` peut de nouveau monter une bataille.")
        return 0
    print("TOUJOURS ARME -- l'ecriture n'a pas tenu (le jeu reecrit peut-etre derriere). "
          "Relancer le jeu reste la sortie sure.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
