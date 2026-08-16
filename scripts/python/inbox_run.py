"""Boite de reception : lire les envois, ECARTER ceux qui contiennent de la stamina, reclamer.

    python scripts/python/inbox_run.py                 # inventaire, RIEN n'est reclame
    python scripts/python/inbox_run.py --reclamer      # reclame tout SAUF la stamina

POURQUOI EPARGNER LA STAMINA, et pourquoi c'est le pilote qui decide.

La stamina se REGENERE seule et PLAFONNE : la reclamer jauge pleine en jette la difference,
definitivement. Les autres recompenses s'empilent sans perte. Le tri appartient donc a
l'utilisateur, qui sait ou en est sa jauge -- et c'est aussi pourquoi le hook (`inbox.ts`) ne
filtre RIEN : il expose le type de chaque recompense, cet outil choisit. Une politique enfouie
dans le hook serait invisible d'ici, meme faute que le seuil d'echecs de `promo-code.ts`.

⚠ UN ENVOI MIXTE EST EPARGNE EN ENTIER. `ClaimInboxItem` prend une IDENTITE d'envoi, pas une
recompense : il n'existe aucun moyen de n'en prendre qu'une partie. Un envoi qui contient de la
stamina ET autre chose est donc laisse INTACT, et il est LISTE comme tel -- a toi de le
reclamer a la main quand ta jauge est basse.

⚠ LES NOMS DE TYPES SE DEMANDENT AU JEU (`dumpEnum IdunMetaLogic.Loot RewardType`), on n'en
recopie pas la table : un miroir fige ici se perimerait en silence au changement de build.
`Stamina` y vaut 5 aujourd'hui -- et c'est le NOM qui est teste, jamais l'ordinal.

⚠ UN ENVOI RECLAME NE DISPARAIT PAS : il RESTE en boite, marque `claimed`. Le decompile le dit
(`InboxProgression$$ClaimInboxItemInternal` pose le drapeau, appelle `ReadInboxItemInternal` et
`BroadcastInboxItemChanged` -- il n'y a AUCUN `RemoveInboxItemLocally`). La premiere version de
cet outil attestait par la DISPARITION : elle a donc rapporte << 0 / 23 reclames >> sur une
reclamation qui avait parfaitement marche. Un oracle faux accuse le code juste.

⚠ Le retour d'une reclamation ne prouve rien non plus : on relit la boite et on regarde
`isClaimed`, c'est LUI qui atteste.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

NOM_STAMINA = "Stamina"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


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

    def noms_recompenses(self):
        """La table des types, DEMANDEE AU JEU. `None` = pas mesuree (on n'invente pas)."""
        d = self.rpc("dumpEnum", [{"asm": "", "ns": "IdunMetaLogic.Loot", "cls": "RewardType"}])
        v = d.get("values") if isinstance(d, dict) else None
        if not isinstance(v, dict):
            return None
        return {int(n): k for k, n in v.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", type=int, default=13)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--reclamer", action="store_true", help="sans ce drapeau : lecture seule")
    ap.add_argument("--avec-stamina", action="store_true",
                    help="NE PAS epargner la stamina (geste delibere : jauge pleine = perte)")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()

    jeu = Jeu(a.hote, a.session)
    noms = jeu.noms_recompenses()
    if noms is None:
        print("table `IdunMetaLogic.Loot.RewardType` NON MESUREE (`dumpEnum` muet).")
        print("On ne peut pas reconnaitre la stamina -- donc on ne reclame RIEN.")
        return 1

    d = jeu.rpc("inboxList")
    if not isinstance(d, dict) or d.get("ok") is not True:
        print("inboxList a echoue : %s" % ascii_(json.dumps(d, ensure_ascii=False))[:400])
        return 1
    envois = d.get("entries") or []
    print("=== %d envoi(s) en boite de reception ===" % len(envois))
    print()

    a_prendre, a_epargner, sans_guid, deja = [], [], [], []
    for e in envois:
        recs = e.get("rewards")
        # `null` = la classe ne porte pas de `<rewards>` : NON MESURE. On ne reclame pas un
        # envoi dont on n'a pas pu lire le contenu -- il pourrait contenir de la stamina.
        detail = []
        stamina = False
        if isinstance(recs, list):
            for r in recs:
                n = noms.get(r.get("type"), "INCONNU(%s)" % r.get("type"))
                if n == NOM_STAMINA:
                    stamina = True
                detail.append("%s x%s%s" % (n, r.get("amount"),
                                            (" [%s]" % r["id"]) if r.get("id") else ""))
        marque = "  <<< STAMINA" if stamina else ""
        print("  %-38s %-3s %-26s %s%s"
              % (ascii_(str(e.get("guid")))[:38],
                 "OK" if e.get("isClaimed") else "",       # deja reclame
                 ascii_(str(e.get("type")))[:26],
                 ascii_(" + ".join(detail)) if detail
                 else ("(recompenses NON LISIBLES)" if recs is None else "(aucune recompense)"),
                 marque))
        # DEJA RECLAME -> rien a faire. Un envoi reclame RESTE en boite (cf. l'en-tete), donc
        # sans ce test on le rejouerait a chaque passage.
        if e.get("isClaimed"):
            deja.append(e)
        elif not e.get("guid"):
            sans_guid.append(e)
        elif recs is None:
            a_epargner.append((e, "contenu NON LISIBLE"))
        elif stamina and not a.avec_stamina:
            a_epargner.append((e, "contient de la stamina"))
        else:
            a_prendre.append(e)

    print()
    print("=== tri ===")
    print("  a reclamer      : %d" % len(a_prendre))
    print("  deja reclames   : %d (ils RESTENT en boite, c'est normal)" % len(deja))
    for e, motif in a_epargner:
        print("  EPARGNE    : %-38s (%s)" % (ascii_(str(e.get("guid")))[:38], motif))
    for e in sans_guid:
        print("  SANS GUID  : %s -- non reclamable par cette voie"
              % ascii_(str(e.get("cls"))))
    print()

    if not a.reclamer:
        print("LECTURE SEULE. Relancer avec --reclamer pour prendre les %d." % len(a_prendre))
        return 0
    if not a_prendre:
        print("RIEN a reclamer.")
        return 0

    guids = [e["guid"] for e in a_prendre][:a.max]
    print("=== inboxClaim (%d) ===" % len(guids))
    r = jeu.rpc("inboxClaim", [{"guids": guids, "confirmer": True}], timeout=120000)
    print("  %s" % ascii_(json.dumps(r, ensure_ascii=False))[:900])
    print()

    # ATTESTER : c'est la boite relue qui fait foi, pas le retour ci-dessus.
    time.sleep(2)
    d2 = jeu.rpc("inboxList")
    if not isinstance(d2, dict) or d2.get("ok") is not True:
        print("relecture IMPOSSIBLE -- les reclamations sont DEJA PARTIES, ne pas rejouer.")
        return 1
    apres = d2.get("entries") or []
    # ⚠ L'ATTESTATION EST LE DRAPEAU `isClaimed`, PAS LA DISPARITION. Un envoi reclame reste
    #   en boite (cf. l'en-tete) : attester par la disparition rapportait << 0 / 23 >> sur une
    #   reclamation reussie, et accusait le code au lieu de l'oracle.
    etat = {x.get("guid"): bool(x.get("isClaimed")) for x in apres}
    ok = [g for g in guids if etat.get(g) is True]
    rate = [g for g in guids if etat.get(g) is False]
    absent = [g for g in guids if g not in etat]
    print("=== ATTESTATION (drapeau `claimed`) ===")
    print("  boite : %d -> %d envoi(s)  (un envoi reclame RESTE, c'est normal)"
          % (len(envois), len(apres)))
    print("  reclames : %d / %d" % (len(ok), len(guids)))
    if absent:
        print("  DISPARUS de la boite : %d -- inattendu, mais pas un echec" % len(absent))
    if rate:
        print("  TOUJOURS NON RECLAMES (%d) -- la reclamation n'a PAS mordu." % len(rate))
        print("  NE PAS rejouer sans avoir compris pourquoi.")
        for g in rate[:10]:
            print("    %s" % ascii_(g))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
