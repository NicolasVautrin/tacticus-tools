"""REMAPPER les entites d'un replay sur celles de la bataille REELLEMENT montee.

    python scripts/python/replay_remap.py --replay <fichier>            # rapport, rien d'ecrit
    python scripts/python/replay_remap.py --replay <fichier> --ecrire <sortie.json>

POURQUOI CE MODULE EXISTE -- ET POURQUOI << REPOSER DANS LE BON ORDRE >> NE SUFFIT PAS
--------------------------------------------------------------------------------------
Les coups d'un replay sont adresses PAR ENTITE (`UnitId`, `CasterId`, `TargetId`). L'entite
d'une unite est attribuee au START, dans l'ordre de conversion des placeholders. Or cet ordre
obeit a une loi MESUREE (2026-08-21, cf. `deploiement_commun.poser_le_deploiement`) :

    plateau VIERGE ................. conversion = U + [M]
    plateau PLEIN (un clear avant) . conversion = [M] + reverse(U)      <- la liste libre
                                                                           des paires est une PILE

⛔ Sur un plateau PLEIN la Machine of War est TOUJOURS en tete, et aucune permutation des
unites ne l'en delogera -- elle n'est pas dans la partie permutee. Les replays du depot
l'enregistrent EN DERNIER : ils ne sont donc reproductibles QU'A PARTIR d'un plateau vierge.

Et une entree REELLE (boss de guilde, guerre) arrive PRE-REMPLIE par la memoire du jeu. Le
plateau n'y est jamais vierge, donc l'ordre du replay n'y est pas atteignable -- mesure du
2026-08-24 : `[MoW 79] + reverse(Warboss, Dominus, Ruststalker, Marshall, Manipulus)`, soit
79/80/82/84/86/88 la ou le replay attend 79/81/83/85/87 + 89.

⇒ On ne corrige pas le DEPLOIEMENT, on corrige les COUPS.

CE QUI REND LE REMAPPAGE SAIN, ET CE QUI LE RENDRAIT FAUX
---------------------------------------------------------
Le remappage n'est legitime que si la permutation est CONFINEE au bloc de deploiement --
sinon une entite non permutee serait reetiquetee, ou l'inverse. L'invariant est donc :

    (I) le bloc de deploiement occupe LE MEME ENSEMBLE d'ids des deux cotes.

Mesure du 2026-08-24 sur `GuildBoss-29710292` : bloc = 79..89 dans les deux regimes (5 squads
+ 5 pieds + 1 machine), et les creations d'apres-START commencent a 119 des deux cotes. Les
tuiles (0..76), le boss (77/78) et les entites nees en cours de partie gardent donc leur id.

(I) N'EST PAS SUPPOSE ICI, IL EST VERIFIE, et un ecart REFUSE. C'est ce qui distingue ce
module d'une table ecrite a la main : si le bloc ne coincide pas, le remappage est faux et il
le DIT au lieu d'envoyer des coups sur les mauvaises unites.

⚠ CE MODULE NE DEVINE JAMAIS UNE ENTITE. Tout id reference par un coup est classe, et un id
qui tombe DANS le bloc sans avoir de correspondance est un REFUS -- pas un `identite` par
defaut. Le defaut permissif est exactement ce qui ferait frapper a cote sans que rien ne rougisse.

ASCII only en sortie (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

#: Les champs d'un message qui portent un ID D'ENTITE. Toute cle absente d'ici est laissee
#: INTACTE -- et c'est voulu : `ActiveAbilityType`, `PlayerId`, `SpawnSource`, `Tag`... sont
#: des entiers qui ne designent PAS une entite. Les remapper serait une corruption silencieuse.
CHAMPS_ENTITE = ("UnitId", "CasterId", "TargetId")

#: `AddUnitMessage` porte `UnitId` en CHAINE (l'id de catalogue, "orksWarboss"), pas en entier.
#: Le filtre `isinstance(v, int)` suffit donc, mais on le dit : c'est le meme NOM de champ pour
#: deux natures differentes selon le message.
MSG_POSE = ("AddUnitMessage", "AddMachineMessage")

#: L'ancre qui separe LE MONTAGE de LA POSE dans le flux d'un coup. Vaut pour l'unite ET pour
#: la machine (mesure du 2026-08-24 : le flux d'`AddMachineMessage` ouvre lui aussi sur
#: `Group=User_PlaceUnit`). Voir le pave d'`entites_du_replay` : sans elle, la premiere unite
#: se lit sur le BOSS.
ANCRE_POSE = "Group=User_PlaceUnit"


class Refus(RuntimeError):
    """Rendu au lieu d'une table : un remappage douteux ne doit JAMAIS s'appliquer."""


# --------------------------------------------------------------------------- lecture du replay
def _corps(m: dict) -> dict:
    return json.loads((m.get("Message") or {}).get("MessageJson") or "{}")


def entites_du_replay(d: dict) -> dict:
    """`{unitId: entite}` du DEPLOIEMENT, LU dans le flux -- jamais calcule.

    (!)ON LE LIT, ON NE LE DEDUIT PAS. Une formule (`79 + 2*i`) est vraie pour UN replay et
    fausse au suivant : c'est le flux qui nomme l'entite que le jeu a REELLEMENT attribuee,
    par `Group=User_PlaceUnit` puis `Action=AddUnit Entity=<n>`. La machine, elle, sort sous
    `Action=AddMachine` -- mais SOUS LA MEME ancre `User_PlaceUnit` (mesure du 2026-08-24).

    ⛔ L'ANCRE N'EST PAS DECORATIVE, ET LA SAUTER DONNE UN RESULTAT FAUX ET PLAUSIBLE. Le flux
    du PREMIER coup porte tout le montage (`Group=System_GameSetup` : les tuiles, puis le BOSS
    en `Action=AddUnit Entity=77`) AVANT la pose du joueur. Un `re.search` non ancre rend donc
    77 pour la premiere unite -- un id qui existe, qui est bien une unite, et qui n'est pas la
    sienne. Attrape par `test_replay_remap_offline` a la premiere execution.

    Rend `{}` si une seule pose n'est pas lisible -- un appariement PARTIEL vaut moins que pas
    d'appariement, parce qu'il passerait pour un controle.
    """
    out: dict[str, int] = {}
    for m in d.get("Messages") or []:
        c = _corps(m)
        nom = c.get("Name")
        if nom == "StartBattleMessage":
            break
        if nom not in MSG_POSE:
            continue
        uid = c.get("UnitId")
        if not isinstance(uid, str) or not uid:
            return {}
        flux = m.get("OutputStream") or ""
        i = flux.find(ANCRE_POSE)
        if i < 0:
            return {}
        mm = re.search(r"Action=Add(?:Unit|Machine) Entity=(\d+)", flux[i:])
        if not mm:
            return {}
        out[uid] = int(mm.group(1))
    return out


def bloc_de_deploiement(d: dict) -> set:
    """L'ENSEMBLE des ids que le deploiement consomme -- squads, PIEDS compris, et machine.

    (!)LES PIEDS COMPTENT. Une unite consomme DEUX entites consecutives (squad N, unite N+1) ;
    borner le bloc aux seuls squads le sous-estimerait, et un pied tomberait alors en
    << identite >> alors qu'il est PERMUTE. On prend donc toutes les creations qui precedent le
    `StartBattleMessage` et qui suivent le bloc statique (tuiles, boss, plateformes).
    """
    ids: set[int] = set()
    debut = None
    for m in d.get("Messages") or []:
        c = _corps(m)
        if c.get("Name") == "StartBattleMessage":
            break
        if c.get("Name") not in MSG_POSE:
            continue
        flux = m.get("OutputStream") or ""
        # ⛔ MEME ANCRE, MEME RAISON qu'`entites_du_replay` -- et la faute avait ete commise
        # ICI AUSSI : sans elle le balayage avale le montage (tuiles, plateformes 75/76, boss
        # 77/78) et le bloc part de 0, donc TOUT devient << dans le bloc >> et l'invariant (I)
        # ne peut plus rien discriminer.
        i = flux.find(ANCRE_POSE)
        if i < 0:
            continue
        flux = flux[i:]
        for mm in re.finditer(r"Action=Add(Unit|Machine|MachinePlatform) Entity=(\d+)", flux):
            genre, n = mm.group(1), int(mm.group(2))
            if debut is None:
                debut = n
            ids.add(n)
            # ⛔ LE PIED DE LA DERNIERE UNITE MANQUAIT AU BLOC, ET CA REFUSAIT UN REMAPPAGE JUSTE.
            #
            # Une unite consomme DEUX entites consecutives (squad N, unite N+1) et le pied ne
            # porte PAS d'`Action=Add*` a lui. Prendre l'intervalle jusqu'a `max(ids)` couvre donc
            # tous les pieds INTERMEDIAIRES -- ils tombent entre deux squads -- mais jamais celui
            # du DERNIER, qui est au-dela de la derniere ligne vue.
            #
            # Ca ne se voyait pas tant que le mapper ne servait qu'au boss de guilde : la Machine
            # of War y est posee EN DERNIER, et ses `AddMachine`/`AddMachinePlatform` fournissent
            # une borne haute qui couvre le pied d'avant. Des que la derniere creation est une
            # UNITE -- campagne, onslaught -- le bloc s'arrete un cran trop bas, et l'invariant (I)
            # tombe face a un `bloc_vif` qui, lui, compte `max + 2`.
            #
            # Mesure du 2026-08-27, refus rencontre en generalisant le mapper a l'onslaught :
            # replay `93..101` contre vivant `93..102`. Effet du correctif sur le corpus --
            # `GuildBoss-29710292` (79..89, LE cas qui a servi a ecrire ce module) INCHANGE,
            # `dogalpha` INCHANGE ; campagne, GW `fenris` et onslaught gagnent leur dernier pied.
            if genre == "Unit":
                ids.add(n + 1)
    if debut is None:
        return set()
    # Les PIEDS ne portent pas d'`Action=Add*` a eux : ils vivent entre deux squads. Le bloc est
    # donc l'INTERVALLE, pas l'ensemble des lignes vues -- borne haute incluse.
    return set(range(debut, max(ids) + 1))


def ids_references(d: dict) -> dict:
    """`{id: [(index_du_coup, champ)]}` -- tout id d'entite qu'un coup ADRESSE.

    C'est la liste que le remappage doit couvrir INTEGRALEMENT. Un recenseur qui n'enumere que
    les champs auxquels il pense ne peut pas montrer celui qu'il a oublie : on balaye donc TOUS
    les champs du message et on retient les entiers portes par `CHAMPS_ENTITE`.
    """
    out: dict[int, list] = {}
    for i, m in enumerate(d.get("Messages") or []):
        c = _corps(m)
        for k, v in c.items():
            if k not in CHAMPS_ENTITE:
                continue
            if isinstance(v, bool) or not isinstance(v, int):
                continue        # `AddUnitMessage.UnitId` est une CHAINE -- pas une entite
            out.setdefault(v, []).append((i, k))
    return out


# --------------------------------------------------------------------------- la table
def table(rep: dict, vivant: dict, bloc_rep: set, bloc_vif: set) -> dict:
    """`{entite_du_replay: entite_vivante}`, ou LEVE.

    Trois refus, et aucun n'est negociable :
      1. une unite du replay absente du vivant (ou l'inverse) -- l'appariement serait partiel ;
      2. les deux blocs n'occupent pas le MEME ensemble d'ids -- l'invariant (I) tombe, donc
         une entite hors table ne peut plus etre declaree << identite >> ;
      3. la correspondance n'est pas une bijection -- deux unites viseraient la meme entite.
    """
    manquantes = set(rep) ^ set(vivant)
    if manquantes:
        raise Refus("unites non appariees entre le replay et la bataille : %s. Le remappage "
                    "exige les MEMES unites des deux cotes." % sorted(manquantes))
    if bloc_rep != bloc_vif:
        raise Refus(
            "les blocs de deploiement n'occupent PAS le meme ensemble d'ids "
            "(replay=%s..%s, vivant=%s..%s). L'invariant qui autorise le remappage tombe : "
            "hors du bloc, on ne peut plus affirmer qu'une entite garde son id, donc les "
            "tuiles, le boss et les unites nees en cours de partie deviennent indecidables."
            % (min(bloc_rep or [0]), max(bloc_rep or [0]),
               min(bloc_vif or [0]), max(bloc_vif or [0])))

    t = {}
    for uid, e_rep in rep.items():
        t[e_rep] = vivant[uid]
    if len(set(t.values())) != len(t):
        raise Refus("la correspondance n'est PAS une bijection : %s" % t)

    # Les PIEDS suivent leur squad. Le flux ne les nomme pas un par un, mais la loi est
    # structurelle (squad N -> unite N+1) et elle vaut des DEUX cotes : on la propage, et on
    # verifie que le resultat reste dans le bloc et bijectif.
    for e_rep, e_vif in list(t.items()):
        if (e_rep + 1) in bloc_rep and (e_rep + 1) not in t:
            t[e_rep + 1] = e_vif + 1
    if len(set(t.values())) != len(t):
        raise Refus("la propagation aux PIEDS casse la bijection : %s" % t)
    return t


def classer(refs: dict, t: dict, bloc: set) -> dict:
    """Range chaque id reference : `remappe`, `identite`, ou `REFUS`.

    (!)LE DEFAUT EST LE REFUS, PAS L'IDENTITE. Un id qui tombe dans le bloc sans correspondance
    est une entite de deploiement qu'on n'a pas su apparier -- la laisser passer telle quelle la
    ferait frapper une AUTRE unite, en silence.
    """
    out = {"remappe": {}, "identite": [], "refus": []}
    for e, sites in sorted(refs.items()):
        if e in t:
            out["remappe"][e] = {"vers": t[e], "sites": len(sites)}
        elif e in bloc:
            out["refus"].append({"entite": e, "sites": sites,
                                 "motif": "DANS le bloc de deploiement mais SANS correspondance"})
        else:
            out["identite"].append({"entite": e, "sites": len(sites)})
    return out


def reecrire(d: dict, t: dict) -> dict:
    """Rend un replay NEUF dont les coups adressent les entites vivantes.

    (!)ON NE TOUCHE QUE `CHAMPS_ENTITE`, et seulement quand la valeur est un ENTIER. Le reste du
    message -- types d'ability, positions, drapeaux -- est recopie verbatim : un remappeur qui
    << nettoie >> au passage ne serait plus confrontable au replay d'origine.

    (!)L'`OutputStream` N'EST PAS REECRIT, et c'est deliberatement : il reste la reference
    ATTENDUE, celle du replay d'origine. La comparer au flux produit accuse donc les ecarts
    reels ; la reecrire ferait passer le test par construction.
    """
    neuf = json.loads(json.dumps(d))
    for m in neuf.get("Messages") or []:
        env = m.get("Message") or {}
        c = json.loads(env.get("MessageJson") or "{}")
        touche = False
        for k in CHAMPS_ENTITE:
            v = c.get(k)
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            if v in t:
                c[k] = t[v]
                touche = True
        if touche:
            env["MessageJson"] = json.dumps(c, ensure_ascii=False)
    return neuf


# --------------------------------------------------------------------------- pilote
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="replay_remap", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--ecrire", metavar="sortie.json",
                    help="ecrire le replay remappe (sinon : rapport seul)")
    a = ap.parse_args(argv)

    d = json.loads(Path(a.replay).read_text(encoding="utf-8"))
    rep = entites_du_replay(d)
    if not rep:
        print("REFUS : appariement du replay NON LISIBLE dans son flux.")
        return 2
    bloc_rep = bloc_de_deploiement(d)
    print("replay : %d unites deployees, bloc %s..%s"
          % (len(rep), min(bloc_rep), max(bloc_rep)))
    for u, e in sorted(rep.items(), key=lambda x: x[1]):
        print("   %-22s -> entite %s" % (u, e))

    sys.path.insert(0, str(RACINE / "scripts" / "python"))
    import expedition_run as R                                    # noqa: E402
    sid = a.session if a.session is not None else R.session_vivante()
    o = R.rpc(sid, "observeBattle", {}) or {}
    if not o.get("units"):
        print("REFUS : aucune bataille montee -- il n'y a rien a quoi apparier.")
        return 2

    vivant = {u["visualId"]: u["squadId"] for u in o["units"] if u.get("squadId") is not None}
    for m in (o.get("mows") or []):
        if m.get("visualId") and m.get("machineId") is not None:
            vivant[m["visualId"]] = m["machineId"]
    vivant = {u: e for u, e in vivant.items() if u in rep}
    bloc_vif = set(range(min(vivant.values()), max(vivant.values()) + 2)) if vivant else set()

    print()
    print("vivant : %d unites, bloc %s..%s"
          % (len(vivant), min(bloc_vif or [0]), max(bloc_vif or [0])))
    for u, e in sorted(vivant.items(), key=lambda x: x[1]):
        print("   %-22s -> entite %s" % (u, e))

    try:
        t = table(rep, vivant, bloc_rep, bloc_vif)
    except Refus as e:
        print()
        print("REFUS : %s" % e)
        return 2

    cl = classer(ids_references(d), t, bloc_rep)
    print()
    print("REMAPPES : %d entites" % len(cl["remappe"]))
    for e, info in sorted(cl["remappe"].items()):
        print("   %4s -> %-4s  (%d site(s))" % (e, info["vers"], info["sites"]))
    print("IDENTITE : %d entites hors bloc (tuiles, boss, unites nees en cours de partie)"
          % len(cl["identite"]))
    if cl["refus"]:
        print()
        for r in cl["refus"]:
            print("REFUS : entite %s %s -- sites %s"
                  % (r["entite"], r["motif"], r["sites"][:6]))
        return 2

    if not a.ecrire:
        print()
        print("(rapport seul -- `--ecrire <sortie.json>` pour produire le replay remappe)")
        return 0

    Path(a.ecrire).write_text(json.dumps(reecrire(d, t), ensure_ascii=False), encoding="utf-8")
    print()
    print("ECRIT : %s" % a.ecrire)
    return 0


if __name__ == "__main__":
    sys.exit(main())
