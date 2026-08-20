"""DEPLOYER ET DEMARRER une bataille de boss, a l'identique de la reference -- AVEC PRE-VOL.

Utilisable tel quel sur une bataille REELLE (`--reelle`) ou repete en SANDBOX (defaut) : c'est
le MEME chemin, avec les MEMES drapeaux. Repeter sans `--reelle` ne prouverait rien de ce qui
sera joue.

    python ... vraie_bataille.py             # repetition sandbox, drapeaux de vraie partie
    python ... vraie_bataille.py --reelle    # sur la partie du joueur

CE QU'IL VERIFIE, ET IL S'ARRETE AU PREMIER ECART
--------------------------------------------------
  1. une bataille est la ;
  2. le SEED a ete substitue -- exactement UNE entree NEUVE au journal depuis l'armement
     (le journal CUMULE sur toute la session : sa longueur brute ne prouve rien) ;
  3. le camp du joueur est VIDE ;
  4. les 5 + la MoW sont posees ;
  5. PRE-VOL : composition, cases ET identites d'entite CONFORMES a la reference ;
  6. START ;
  7. les 7 pas de mise en place, confrontes AU CARACTERE.

(!)ON NE REMPLACE JAMAIS LA BC. On force le seed, et on VERIFIE que le deploiement est celui du
replay -- c'est tout. Substituer la configuration d'un essai enregistre cote serveur est exclu.

⛔ AUCUN `retreatInvoke` sur une partie reelle : ce serait abandonner l'essai.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from rpc import rpc, session  # noqa: E402

REFERENCE = [("AddUnitMessage", 32519), ("AddUnitMessage", 2299), ("AddUnitMessage", 2735),
             ("AddUnitMessage", 2955), ("AddUnitMessage", 2740),
             ("AddMachineMessage", 2271), ("StartBattleMessage", 11980)]
REPLAY = r"data\replays\guild-boss\belisarius\belisarius-10040.json"

ap = argparse.ArgumentParser()
ap.add_argument("--reelle", action="store_true",
                help="agir sur la PARTIE DU JOUEUR (sinon : repetition sandbox)")
ap.add_argument("--seed-avant", type=int, default=None,
                help="longueur du journal de seed RELEVEE AVANT l'armement (cran 2)")
args = ap.parse_args()

d = json.loads(Path(REPLAY).read_text(encoding="utf-8"))
poses, mow = [], None
for m in d.get("Messages") or []:
    c = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
    if c.get("Name") == "AddUnitMessage":
        p = (c.get("UnitFeetPositions") or [{}])[0]
        poses.append({"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"),
                      "col": p.get("Column"), "row": p.get("Row")})
    elif c.get("Name") == "AddMachineMessage":
        mow = {"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"), "position": 2}
    elif c.get("Name") == "StartBattleMessage":
        break
# Les entites attendues : squad PAIR, unite IMPAIRE, allouees dans l'ordre de pose.
ENTITES = {p["unitId"]: 111 + 2 * i for i, p in enumerate(poses)}

sid = session()
REEL = bool(args.reelle)
FLAGS = {"surBatailleReelle": True} if REEL else {}


def stop(pourquoi):
    print()
    print("ARRET -- %s" % pourquoi)
    print("Rien de plus n'est envoye.")
    sys.exit(2)


print("session %s -- mode %s" % (sid, "PARTIE REELLE" if REEL else "repetition sandbox"))
print()
print("CRAN 1 -- une bataille est-elle la ?")
p = rpc(sid, "sandboxProbe", [{}], timeout=120000).get("result") or {}
if not p.get("instance"):
    stop("aucune `IdunMainView` vivante.")
print("   IdunMainView %s" % p.get("instance"))

print()
print("CRAN 2 -- le seed a-t-il ete SUBSTITUE pour CETTE bataille ?")
s = rpc(sid, "sandboxModeSeed", [{}], timeout=60000).get("result") or {}
j = s.get("journal") or []
imposes = [x for x in j if x.get("mode") == "impose"]
print("   journal : %d entree(s), dont %d imposition(s)" % (len(j), len(imposes)))
if not imposes:
    stop("aucune imposition de seed -- rejouer sur un autre tirage ne prouve rien.")
if args.seed_avant is not None:
    neuves = len(j) - args.seed_avant
    print("   entrees NEUVES depuis l'armement : %d" % neuves)
    if neuves != 1:
        stop("on attend EXACTEMENT une entree neuve (%d) -- le journal CUMULE sur la session, "
             "donc sa longueur brute ne dit pas quelle bataille a pris le seed." % neuves)
else:
    print("   (!) `--seed-avant` non fourni : on ne peut pas dire QUELLE bataille l'a pris.")

print()
print("CRAN 3 -- le camp du joueur est-il VIDE ?")
pl = rpc(sid, "deploymentPlateau", [{}], timeout=60000).get("result") or {}
if pl.get("duJoueur"):
    stop("le camp du joueur porte deja %s unite(s)." % pl.get("duJoueur"))
print("   duJoueur=0  total=%s" % pl.get("total"))

print()
print("CRAN 4 -- poser les 5 + la MoW, par l'etage FSM (la methode du clic humain)")
for nom, a in (("vueExceptionArmer", {"armer": True}),
               ("replayFinAuto", {"armer": True}),
               ("deploymentPoseFsmArmer", {"armer": True, "confirmer": True})):
    r = rpc(sid, nom, [a], timeout=120000).get("result")
    if not (isinstance(r, dict) and r.get("ok")):
        stop("`%s` non arme : %s" % (nom, json.dumps(r, ensure_ascii=False)[:200]))
rpc(sid, "deploymentMemoire", [{"poser": {"poses": poses, "mow": mow}}], timeout=120000)
rpc(sid, "deploymentMemoire", [dict(FLAGS, rejouer=True, confirmer=True)], timeout=180000)
for i in range(24):
    time.sleep(1.5)
    b = (rpc(sid, "deploymentBoutonArmer", [{}], timeout=60000).get("result") or {}).get("bouton")
    n = (b or {}).get("placees")
    if isinstance(n, int) and n >= len(poses) + 1:
        break
print("   HUD placees : %s" % n)
f = rpc(sid, "deploymentPoseFsmArmer", [{}], timeout=60000).get("result") or {}
rates = [x for x in (f.get("faits") or []) if not x.get("ok")]
if rates:
    stop("pose(s) REFUSEE(S) : " + json.dumps(rates, ensure_ascii=False)[:400])
print("   poses FSM : %d/%d" % (len(f.get("faits") or []) - len(rates), len(poses)))

print()
print("CRAN 5 -- PRE-VOL : le deploiement est-il CELUI DU REPLAY ?")
r = rpc(sid, "deploymentStartInvoquer", [dict(FLAGS, confirmer=True)], timeout=240000).get("result")
print("   START : %s" % json.dumps(r, ensure_ascii=False)[:220])
if not (isinstance(r, dict) and r.get("ok")):
    stop("le START a leve ou a ete refuse.")
time.sleep(7.0)

o = rpc(sid, "observeBattle", [{}], timeout=180000).get("result") or {}
miennes = [u for u in (o.get("units") or []) if u.get("teamId") == 1]
mows = o.get("mows")
mows = [mows] if isinstance(mows, dict) else (mows or [])
print("   stage=%s  unites=%d  mows=%d" % (o.get("stageName"), len(miennes), len(mows)))
ecarts = []
if o.get("stageName") != "Running":
    ecarts.append("stage=%s" % o.get("stageName"))
if len(miennes) != len(poses):
    ecarts.append("%d unite(s) pour %d attendues" % (len(miennes), len(poses)))
if mow is not None and not mows:
    ecarts.append("MoW ABSENTE")
for u in miennes:
    att = ENTITES.get(u.get("visualId"))
    if att is None:
        ecarts.append("unite INATTENDUE : %s" % u.get("visualId"))
    elif u.get("entityId") != att:
        ecarts.append("%s en entite %s au lieu de %s" % (u.get("visualId"), u.get("entityId"), att))
for x in miennes:
    print("      %-6s %-20s" % (x.get("entityId"), x.get("visualId")))
if ecarts:
    stop("PRE-VOL ROUGE : " + " ; ".join(ecarts))
print("   composition, MoW et identites d'entite CONFORMES.")

print()
print("CRAN 6 -- les 7 pas de mise en place, AU CARACTERE")
st = rpc(sid, "replaySteps", [{"maxSteps": 4000}], timeout=180000).get("result") or {}
if st.get("recorderArmed") is False:
    stop("`recorderArmed=false` -- le flux serait VIDE SANS ERREUR (#477-r1).")
pas = [(x.get("messageCls"), x.get("outputStreamLength")) for x in (st.get("steps") or [])]
nb = 0
print("   %-4s %-22s %-22s %9s %9s  %s" % ("#", "attendu", "obtenu", "att.", "obt.", "verdict"))
for i in range(max(len(REFERENCE), len(pas))):
    a = REFERENCE[i] if i < len(REFERENCE) else (None, None)
    g = pas[i] if i < len(pas) else (None, None)
    v = "OK" if a == g else ("MANQUANT" if g[0] is None else "ECART")
    if v != "OK":
        nb += 1
    print("   %-4d %-22s %-22s %9s %9s  %s" % (i, a[0] or "-", g[0] or "-", a[1], g[1], v))

print()
if nb:
    print("MISE EN PLACE NON CONFORME (%d ecart(s))." % nb)
    print("La BC d'une vraie bataille differe de la reference par les PV du boss, et le flux de")
    print("mise en place les porte. C'est A TOI de dire si on envoie les coups 7+.")
else:
    print("MISE EN PLACE CONFORME AU CARACTERE. Enchainer :")
print("    python scripts/python/replay_rejouer.py --vivant --depuis 7 --arret-au-premier-ecart")
