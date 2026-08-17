"""Pipeline des codes promotionnels : lire Discord, ecarter les deja-tentes, jouer, attester.

    python scripts/python/promo_run.py --lister        # lecture seule, RIEN n'est joue
    python scripts/python/promo_run.py --jouer         # joue les codes encore non tentes

CE QUE COMPTE `MaxFailsReached` : UN CUMUL D'ECHECS SUR LE COMPTE. MESURE, PAS SUPPOSE.

`thor.UserProgress.RedeemPromoCodeResult` porte `MaxFailsReached = 5`. Le compteur vit cote
SERVEUR -- aucun decompile ne dit ce qu'il agrege, le client ne recoit que le verdict. Il a
donc fallu le MESURER, et les deux hypotheses successives etaient fausses :

  * << cumul global, arret a 4 ECHECS CONSECUTIFS >> : protecteur par accident, mais sur la
    MAUVAISE GRANDEUR -- et il a fait renoncer a 90 codes des sa premiere sortie ;
  * << compteur PAR CODE, donc enchainer des codes distincts ne risque rien >> : REFUTE le
    2026-08-16 -- `MaxFailsReached` est tombe sur `SETZSOLOVESCAFFY`, un code JAMAIS tente.

LA MESURE (registre du 2026-08-16, 39 tentatives) : au declenchement, les echecs CONSECUTIFS
valaient 3 et les echecs CUMULES 21. Un SUCCES remet le consecutif a zero mais PAS le cumul --
`FOURFOR40` reussit a 18 cumules, et trois echecs plus tard le serveur bloque. Le seuil est
donc CUMULATIF, autour de 20.

D'ou le garde actuel, `--budget-echecs` (defaut 12) : on compte les echecs DEJA INSCRITS AU
REGISTRE dans les dernieres 24 h et on s'arrete avant le seuil mesure.

⚠ MAIS LA FENETRE N'EST **PAS** GLISSANTE SUR 24 H -- MESURE LE 2026-08-17, ET CE GARDE BLOQUE
DONC A TORT TOUS LES MATINS. Le texte precedent disait << 24 h glissantes est une approximation
prudente, pas une mesure ; si elle etait quotidienne, ce garde serait un peu plus strict que
necessaire >>. C'est le << un peu >> qui etait faux. Mesure : le 2026-08-17 a 07:26 UTC, le
registre portait 21 echecs dans les 24 h glissantes (les 39 tentatives du 16/08 tiennent dans
DIX MINUTES, 10:24:55 -> 10:34:27 UTC), donc le garde refusait de jouer. Une SONDE payee avec un
code PERIME (`WEEK2WAAAGH`, 07/07) a rendu `OutOfTimeFrame` -- pas `MaxFailsReached`. Le compteur
serveur etait OUVERT, et les trois codes du 16/08 sont passes dans la foulee. La remise a zero
est donc QUOTIDIENNE (vraisemblablement minuit UTC, comme le rafraichissement d'Operations), pas
glissante -- le garde par defaut aurait fait attendre ~3 h pour RIEN.

  * COMMENT TRANCHER SANS RIEN RISQUER, et c'est la seule methode qui ne coute pas un code
    frais : jouer UN code notoirement PERIME. `MaxFailsReached` => compteur ferme, on attend ;
    tout autre verdict => compteur ouvert, on enchaine. Un code deja mort ne perd rien.
  * Ce qui reste NON MESURE : l'heure exacte de la bascule. On sait qu'a 07:26 UTC c'etait
    ouvert alors que le glissant disait ferme ; on n'a pas borne l'instant.

Reste vrai, et c'etait deja la :

  * le REGISTRE local (`logs/promo-codes-tentes.json`) -- un code tente n'est JAMAIS rejoue.
    Il ne protege pas du cumul, mais il evite de rebruler les memes echecs a chaque passage.

Le reste releve de l'EFFICACITE, et se regle :

  * l'ORDRE DE JEU : du plus RECENT au plus ANCIEN. Les codes recents sont les seuls a avoir
    une vraie chance -- mesure : les 15 succes du 2026-08-16 vont du 10 au 15 aout, rien
    au-dela ;
  * l'ARRET SUR `AlreadyUsed` : dans cet ordre, un code deja consomme prouve qu'on avait deja
    reclame jusque-la, donc tout ce qui est plus ancien l'est aussi -- on arrete par INUTILITE ;
  * `--echecs-max` : arret apres N echecs consecutifs. DESACTIVE par defaut (0), puisque sous
    la lecture par code il n'y a rien a economiser. Le mettre a 4 restitue l'ancien regime ;
  * un PLAFOND par execution (`--max`), qui borne la duree, pas le risque ;
  * l'arret sur `verrou` cote hook, qui ne s'arme plus que sur `MaxFailsReached` REELLEMENT
    observe -- un fait dit par le serveur, pas une extrapolation.

⚠ LE VERDICT N'EST PAS DANS LE RETOUR DE L'APPEL. La reponse est un aller-retour serveur : on
sonde `promoLire` jusqu'a ce que l'ardoise du delegue-capteur bouge. Un code dont la reponse
n'arrive pas est rendu `SANS REPONSE`, jamais rabattu sur un echec -- la tentative, elle, est
consommee quand meme.

⚠ ET `SANS REPONSE` PEUT MASQUER UN **SUCCES** -- MESURE LE 2026-08-17. `BUZZKILLSAUG` est sorti
`SANS REPONSE` a l'attente par defaut (12 s) ; retire du registre et REJOUE a 45 s, il a rendu
`AlreadyUsed`. La reclamation avait donc ABOUTI du premier coup, et c'est la LECTURE du verdict
qui avait manque. Consequences, les deux comptent :

  * l'inscription `SANS REPONSE` fige comme irresolu un code qui est en fait ENCAISSE -- le
    registre ne le represente plus jamais, donc on ne le sait jamais. La seule sortie est de
    retirer l'entree et de rejouer : `AlreadyUsed` = c'etait passe, tout autre verdict = ca ne
    l'etait pas. Ca coute UNE tentative, et ca ne se tente que compteur OUVERT ;
  * `--attente` a 12 s est trop court AU MOINS PARFOIS. ⚠ Ne pas conclure que 12 s EST la cause :
    entre l'echec et la sonde reussie, DEUX choses ont change -- l'attente ET la sortie d'une
    bataille sandbox montee a l'ecran. Temoin confondu, cause NON ETABLIE. Ce qui est etabli,
    lui, ne depend pas de la cause : la reclamation passe meme quand le verdict ne revient pas.

⚠ Les recompenses vont dans la BOITE DE RECEPTION, pas dans l'inventaire.

⚠ LES NOMS DE RESULTATS SE DEMANDENT AU JEU (`dumpEnum`), on n'en recopie pas la table : un
miroir fige ici se perimerait en silence au changement de build.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
REGISTRE = RACINE / "logs" / "promo-codes-tentes.json"

# Un code du canal : un message dont le contenu ENTIER est un jeton majuscule. Le canal alterne
# code / ping de role, et les pings portent `<@&...>` -- ce motif les ecarte de lui-meme.
MOTIF_CODE = re.compile(r"^[A-Z0-9]{4,32}$")


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


# ---------------------------------------------------------------------------------------
# Discord (GET seulement)
# ---------------------------------------------------------------------------------------
def lire_canal(fichier_session, canal, max_messages, pause):
    S = json.loads(Path(fichier_session).read_text(encoding="utf-8"))
    ent = dict(S.get("entetes") or {})
    ent["authorization"] = S["token"]
    ent["user-agent"] = S["user_agent"]
    ck = "; ".join("%s=%s" % (k, v) for k, v in (S.get("cookies") or {}).items())
    if ck:
        ent["cookie"] = ck

    def get(url):
        req = urllib.request.Request(url, headers=ent, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                d = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    d = gzip.decompress(d)
                return r.status, json.loads(d.decode("utf-8"))
        except urllib.error.HTTPError as e:
            c = e.read().decode("utf-8", "replace")
            if e.code == 429:
                att = float(json.loads(c).get("retry_after", 5)) if c.startswith("{") else 5.0
                time.sleep(att + 0.5)
                return get(url)
            return e.code, c
        except Exception as e:
            return -1, "%s: %s" % (type(e).__name__, e)

    msgs, avant = [], None
    while len(msgs) < max_messages:
        st, lot = get("https://discord.com/api/v10/channels/%s/messages?limit=100%s"
                      % (canal, ("&before=%s" % avant) if avant else ""))
        if st != 200 or not lot:
            if st != 200:
                print("Discord statut=%s %s" % (st, ascii_(str(lot))[:200]))
                return None                    # ⚠ None = PAS MESURE, jamais une liste vide
            break
        msgs += lot
        avant = lot[-1]["id"]
        time.sleep(pause)
    msgs.reverse()

    vus, codes = set(), []
    for m in msgs:
        txt = (m.get("content") or "").strip()
        if MOTIF_CODE.match(txt) and txt not in vus:
            vus.add(txt)
            codes.append({"code": txt, "quand": (m.get("timestamp") or "")[:19].replace("T", " "),
                          "par": (m.get("author") or {}).get("username", "?")})
    return codes


# ---------------------------------------------------------------------------------------
# Jeu
# ---------------------------------------------------------------------------------------
class Jeu:
    def __init__(self, hote, session):
        self.hote, self.session = hote, session

    def rpc(self, methode, args=None, timeout=60000):
        corps = json.dumps({"method": methode, "args": args or [],
                            "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request("%s/api/scripts/%d/rpc" % (self.hote, self.session),
                                     data=corps, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=(timeout / 1000.0) + 20) as r:
                return json.loads(r.read().decode("utf-8")).get("result")
        except urllib.error.HTTPError as e:
            return {"_http": e.code, "_corps": e.read().decode("utf-8", "replace")[:400]}
        except Exception as e:
            return {"_err": "%s: %s" % (type(e).__name__, e)}

    def noms_resultats(self):
        """La table des noms, DEMANDEE AU JEU. `None` = pas mesuree (on n'invente pas)."""
        d = self.rpc("dumpEnum", [{"asm": "", "ns": "thor.UserProgress",
                                   "cls": "RedeemPromoCodeResult"}])
        v = d.get("values") if isinstance(d, dict) else None
        if not isinstance(v, dict):
            return None
        return {int(n): k for k, n in v.items()}


def charger_registre():
    if not REGISTRE.exists():
        return {}
    try:
        return json.loads(REGISTRE.read_text(encoding="utf-8"))
    except Exception as e:
        print("registre ILLISIBLE (%s) -- on s'arrete plutot que de rejouer des codes" % e)
        sys.exit(1)


def ecrire_registre(reg):
    REGISTRE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRE.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", type=int, default=11)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--canal", default="1119363760990204034")
    ap.add_argument("--session-file", required=True,
                    help="le JSON de session Discord (HORS DEPOT : il porte un token)")
    ap.add_argument("--max-messages", type=int, default=300)
    ap.add_argument("--pause-discord", type=float, default=1.0)
    ap.add_argument("--jouer", action="store_true", help="sans ce drapeau : lecture seule")
    ap.add_argument("--lister", action="store_true")
    ap.add_argument("--max", type=int, default=40, help="plafond de codes joues par execution")
    ap.add_argument("--echecs-max", type=int, default=0,
                    help="arret apres N echecs CONSECUTIFS ; 0 = desactive (defaut)")
    ap.add_argument("--budget-echecs", type=int, default=12,
                    help="plafond d'echecs CUMULES sur 24 h (seuil serveur mesure : 20)")
    ap.add_argument("--pause", type=float, default=3.0, help="secondes entre deux codes")
    ap.add_argument("--attente", type=float, default=12.0, help="secondes d'attente d'une reponse")
    a = ap.parse_args()

    codes = lire_canal(a.session_file, a.canal, a.max_messages, a.pause_discord)
    if codes is None:
        print("Discord NON LU -- on ne joue rien.")
        return 1
    reg = charger_registre()
    neufs = [c for c in codes if c["code"] not in reg]

    print("=== %d code(s) vu(s) sur le canal, %d deja tente(s), %d NEUF(S) ==="
          % (len(codes), len(codes) - len(neufs), len(neufs)))
    for c in codes:
        d = reg.get(c["code"])
        etat = ("%s" % d.get("nom", d.get("resultat"))) if d else "-- non tente --"
        print("  %-20s %s  %-14s %s" % (c["code"], c["quand"][:10], ascii_(c["par"])[:14], etat))
    print()

    if a.lister or not a.jouer:
        print("LECTURE SEULE. Relancer avec --jouer pour tenter les %d neuf(s)." % len(neufs))
        return 0
    if not neufs:
        print("RIEN a jouer : tous les codes du canal ont deja ete tentes.")
        return 0

    jeu = Jeu(a.hote, a.session)
    noms = jeu.noms_resultats()
    if noms is None:
        print("table des resultats NON MESUREE (`dumpEnum` muet) -- on jouerait a l'aveugle,")
        print("donc on s'arrete. Verifier que la session porte bien le bundle courant.")
        return 1

    # ⚠ DU PLUS RECENT AU PLUS ANCIEN, et ce n'est pas un detail de confort. Le serveur COMPTE
    # les echecs : jouer par ordre chronologique depenserait les premieres tentatives sur les
    # codes les plus surement PERIMES, et le verrou tomberait avant d'avoir atteint les codes
    # du jour -- les seuls qui aient une chance. L'affichage, lui, reste chronologique.
    lot = sorted(neufs, key=lambda c: c["quand"], reverse=True)[:a.max]
    if len(neufs) > a.max:
        print("PLAFOND : %d neufs, on en joue %d (--max), DU PLUS RECENT AU PLUS ANCIEN."
              % (len(neufs), a.max))
        print("Les autres restent au canal -- rien n'est perdu, ils seront proposes au")
        print("prochain passage (le registre ne retient que ce qui a ete REELLEMENT tente).")
        print()

    # LE BUDGET D'ECHECS CUMULES. Le compteur du serveur est CUMULATIF (mesure : 21 echecs au
    # declenchement, dont seulement 3 consecutifs), et il survit a nos executions -- donc on le
    # reconstitue depuis le REGISTRE, pas depuis cette boucle.
    # ⚠ La fenetre de remise a zero du serveur est INCONNUE : 24 h glissantes est une
    #   approximation PRUDENTE, pas une mesure.
    recent = time.time() - 24 * 3600
    cumul = sum(1 for v in reg.values()
                if v.get("resultat") not in (0, None) and (v.get("ts") or 0) >= recent)
    print("echecs cumules sur 24 h (registre) : %d / budget %d  [seuil serveur mesure : 20]"
          % (cumul, a.budget_echecs))
    if cumul >= a.budget_echecs:
        print("BUDGET ATTEINT -- on ne joue rien. Attendre la remise a zero du serveur, ou")
        print("relever --budget-echecs en sachant que le blocage tombe vers 20.")
        return 0
    print()

    echecs = 0
    for i, c in enumerate(lot):
        code = c["code"]
        if cumul >= a.budget_echecs:
            print("--- BUDGET d'echecs cumules atteint (%d) -- arret." % cumul)
            break
        print("--- [%d/%d] %s" % (i + 1, len(lot), code))
        r = jeu.rpc("promoRedeem", [{"code": code, "confirmer": True}], timeout=60000)
        if not isinstance(r, dict) or r.get("ok") is not True:
            msg = (r or {}).get("error") or ascii_(json.dumps(r, ensure_ascii=False))[:220]
            print("    REFUSE / ECHEC : %s" % ascii_(msg))
            if isinstance(r, dict) and r.get("verrou"):
                print("    VERROU ARME -- on s'arrete la.")
                break
            # Un refus AVANT l'appel ne consomme pas de tentative : on n'inscrit rien.
            continue

        avant = ((r.get("reclamation") or {}).get("appelsAvant"))
        fin = time.time() + a.attente
        lu = None
        while time.time() < fin:
            time.sleep(0.5)
            lu = jeu.rpc("promoLire")
            if isinstance(lu, dict) and lu.get("repondu") and lu.get("appelsAvant") == avant:
                break
        else:
            lu = None

        if not isinstance(lu, dict) or not lu.get("repondu"):
            print("    SANS REPONSE apres %.0f s -- la tentative EST consommee cote serveur."
                  % a.attente)
            print("    On l'inscrit quand meme au registre : la rejouer brulerait une "
                  "tentative de plus.")
            reg[code] = {"ts": int(time.time()), "resultat": None, "nom": "SANS REPONSE"}
            ecrire_registre(reg)
            break

        ordinal = lu.get("resultat")
        nom = noms.get(ordinal, "INCONNU(%s)" % ordinal)
        inbox = lu.get("inboxItemNonNul")
        print("    -> %-20s (ordinal %s)%s" % (nom, ordinal,
                                               "   RECOMPENSES EN BOITE DE RECEPTION"
                                               if inbox else ""))
        reg[code] = {"ts": int(time.time()), "resultat": ordinal, "nom": nom,
                     "inbox": bool(inbox)}
        ecrire_registre(reg)

        # ARRET SUR `AlreadyUsed` -- consequence directe de l'ordre de jeu.
        # On descend du plus RECENT au plus ANCIEN. Tomber sur un code deja consomme signifie
        # qu'on avait deja reclame jusque-la ; tout ce qui est PLUS VIEUX l'est donc aussi.
        # Continuer ne ferait que depenser des tentatives sur des `AlreadyUsed` certains --
        # et c'est ce compteur-la qui mene a `MaxFailsReached`.
        # ⚠ Compare par le NOM resolu au jeu (`dumpEnum`), pas par l'ordinal 2 recopie ici.
        if nom == "AlreadyUsed":
            print("    DEJA RECLAME -- on s'arrete : les codes plus anciens le sont aussi.")
            break

        # La POLITIQUE d'echecs consecutifs vit ici, pas dans le hook -- et elle est desactivee
        # par defaut. Sous la lecture << compteur par code >>, enchainer des codes DISTINCTS ne
        # coute rien ; sous la lecture globale, `--echecs-max 4` restitue l'ancien regime.
        if ordinal != 0:
            cumul += 1
        echecs = 0 if ordinal == 0 else echecs + 1
        if a.echecs_max and echecs >= a.echecs_max:
            print("    %d echecs consecutifs (seuil --echecs-max=%d) -- on s'arrete."
                  % (echecs, a.echecs_max))
            break

        if lu.get("verrou"):
            print("    VERROU ARME : %s" % ascii_(str(lu.get("verrou"))))
            print("    On s'arrete -- les codes restants ne sont PAS perdus, ils sont au canal.")
            break
        if i + 1 < len(lot):
            time.sleep(a.pause)

    print()
    print("=== bilan ===")
    succes = [k for k, v in reg.items() if v.get("resultat") == 0]
    print("  registre : %d code(s) tente(s), dont %d SUCCES" % (len(reg), len(succes)))
    print("  %s" % REGISTRE)
    j = jeu.rpc("promoJournal")
    if isinstance(j, dict) and j.get("verrou"):
        print("  VERROU : %s" % ascii_(str(j.get("verrou"))))
        print("  (lever par `promoReset {confirmer:true}` -- seulement en sachant pourquoi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
