"""LE BANC D'ARENE -- monter en SANDBOX le duel qu'on nous propose, sans engager la tentative.

    python scripts/python/arene_banc.py                        # LIT et montre le plan
    python scripts/python/arene_banc.py --n 0 --units a,b,c,d,e --confirmer

CE QUE CA RESOUT
-----------------
Les propositions d'Arene TOURNENT : un replay capture sur un duel n'a plus de cible quelques
heures plus tard, donc rien ne se rejoue. Mais une proposition est de la DONNEE PURE --
`boardId`, `spawnPointsSet`, le lineup adverse et sa Machine of War -- et rien n'y pointe un
objet vivant. On peut donc la figer sur disque et remonter le duel a volonte, en sandbox.

⛔ CE BANC NE TOUCHE PAS AU CLASSEMENT, ET C'EST LE POINT. Il monte une bataille SANDBOX :
aucune tentative consommee, aucun octet envoye au serveur, aucun adversaire reel affecte. Il
sert a REPETER -- essayer une equipe, voir ou ca casse -- avant de decider quel duel engager
pour de vrai, a la main, par le jeu.

L'EQUIPE ADVERSE EST DESORMAIS LA VRAIE -- et le detour qu'on a failli prendre vaut d'etre dit.

Le defaut monte l'adversaire par `--adversaire <n>`, qui delegue a
`PvpOpponentProgressionData$$GetPublicProfileLineup(unitProgression, itemProgression, logger,
null)` : les services de lecture sont les NOTRES, les stats sortent de SES donnees (rank,
xpLevel, upgrades, items, ecrites par le serveur via `PvpServerResponseTranslator$$ApplyUnitInfo`).

⚠ CE QUI EST TOUJOURS FAUX, ET RESTE ACCESSIBLE : `--enemies <ids>` resout les identifiants par
`UnitProgression$$GetUnit`, donc sur la progression DU COMPTE -- l'equipe d'en face, c'est NOTRE
roster portant leurs noms. Mesure du 2026-08-22 sur la proposition 0 de `Player7419` :
`ultraTigurius` etait dans LES DEUX equipes et le catalogue n'en portait qu'UN exemplaire (la
meme entree, nos stats, des deux cotes) ; `darkaAzrael`, qu'on ne possede pas, sortait a RANG 0
/ puissance 562 contre 396 257 pour notre `ultraInceptorSgt`, sa MoW aussi. Ca garde un usage
-- essayer une COMPOSITION sur le bon plateau -- mais ca ne confronte personne, d'ou
l'echappatoire nommee `--adversaire-faux-je-sais`.

⚠ NE PAS RETOMBER SUR << banc de FORME, pas de PUISSANCE >> : cette formule a ete ecrite ici
avant la mesure, et elle est trop indulgente. Une unite a 562 de puissance n'approxime rien.

⛔ ET SURTOUT : IL N'Y AVAIT AUCUN HOOK A ECRIRE. Le plan precedent -- ancrer le resolveur
`<>c__DisplayClass37_0$$<GetHotseatSyncPvpConfig>g__GetEnemy|0` et poser le 14e parametre
`opponentUnitIdPostFix` de `GetPvpLevelConfig` -- etait une sur-ingenierie. Le decompile de
`GetHotseatSyncPvpConfig` montre que ce resolveur finit sur
`Enumerable.First(cfg.PlayerUnits[1], u => u.Id == unitId)` : LA DELEGATION EXISTE DEJA et lit
la liste qu'on fournit. Il n'y avait qu'a y mettre les bons modeles, comme tous les autres modes.

⚠ CE QUI RESTE OUVERT : le postfix. Il n'a d'effet que si les DEUX equipes alignent le meme
`unitId` -- `b__0` fait `cfg.Id = enemyTypeId`, donc deux homonymes se fondraient encore en une
entree de catalogue. C'est une tranche separee, et elle exige les deux crans ensemble (poser le
postfix SANS adapter le resolveur le fait LEVER : l'appariement est par egalite exacte, et
`Enumerable.First` n'a pas de variante `OrDefault`).

⚠ CORRECTION D'UNE AFFIRMATION FAUSSE ECRITE ICI : << le mode sandbox n'installe pas
`EnvEndBombardment` >>. Il l'installerait tres bien -- c'est NOUS qui ne remplissons pas le
champ. `SandboxPvpBattleConfig` porte QUATRE proprietes que le ctor a 9 arguments ne touche
pas, car il ne pose que `BoardId` (+0x28) a `BossUnit` (+0x58) :

    0x10  DeactivateActiveAbilitiesOnAI   Boolean
    0x11  DisableOverkill                 Boolean
    0x18  EnvironmentAbilities            EnvironmentAbilities
    0x20  EnvironmentAbilityTeams         Dictionary`2

`BattleConfigBuilder$$GetHotseatSyncPvpConfig` LIT `EnvironmentAbilities` (+0x18) -- il en tire
`GetExtraEnemyUnits` et le repasse a `GetPvpLevelConfig` en parametre `environmentAbilities`.
Un banc qui remplit ce champ retrouverait donc la pression de fin de l'Arene (8 rounds / 20 %).

LA CORRESPONDANCE EST LUE AU CORPS, plus deduite -- les 14 parametres de `GetPvpLevelConfig`
se posent un par un :

    opponentLineup            <- PlayerUnits[1]      (eux)
    overrideMainPlayerUnits   <- PlayerUnits[0]      (nous)
    getEnemyUnit              <- une CLOTURE Func<String, Boolean, IUnitModel>
    environmentAbilities      <- cfg.EnvironmentAbilities
    opponentMachineOfWarLineup / overrideMainPlayerMachineOfWar / mainPlayerType /
    enemyPlayerType / boardId / spawnPointsSet <- les champs homonymes

⚠ ET LE CTOR DE LA SOURCE N'EST PAS LE LEVIER, contrairement a ce qu'on pourrait croire en
voyant `SandboxGameModeSource..ctor(config, IUnitProgression, ...)` passer sa progression a
`BattleConfigBuilder..ctor(unitProgression, ...)`. Elle y va bien, mais `GetUnitConfiguration`
(unitModel, logger, remainingHealth) STATE A PARTIR DU MODELE SEUL : ce qui est deja un
`IUnitModel` est fige. Le seul levier est donc la position 4 du CONFIG.

⚠ OUVRIR L'ARENE NE COUTE RIEN, MAIS IL FAUT L'AVOIR OUVERTE : `latestOpponents` est nul tant
que l'ecran n'a pas charge. Ce script le fait lui-meme par `IdunNavigation.ToPvp` si la liste
est vide -- ouvrir ne consomme aucune tentative, seul un combat en consomme.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante                      # noqa: E402
from sandbox_mode import Jeu                                  # noqa: E402

HOTE = "http://127.0.0.1:8765"
#: Ou l'on fige les propositions. `logs/` = ce qu'on ECRIT (cf. CLAUDE.md).
ARCHIVE = RACINE / "logs" / "arene-propositions.jsonl"


def propositions(jeu, ouvrir=True, plafond_s=24.0):
    """Les trois propositions du jour. `None` = NON MESURE, jamais une liste vide inventee."""
    r = jeu.rpc("pvpOpponents", [{}], 120000)
    if not isinstance(r, dict) or not r.get("ok"):
        print("pvpOpponents NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:300])
        return None
    if r.get("nombre"):
        return r.get("propositions")
    if not ouvrir:
        print("aucune proposition, et `--sans-ouvrir` : %s" % (r.get("note") or r.get("error")))
        return None

    # (!)ON OUVRE L'ECRAN NOUS-MEMES. `_pvpProgressionData` se remplit a l'affichage de l'Arene ;
    # sans ca la liste reste nulle et on lirait << aucun adversaire >> pour << pas encore ouvert >>.
    a = jeu.rpc("autoBootExtraire", [{}], 180000) or {}
    nav = a.get("navigation")
    if not nav:
        print("pas d'instance `IdunNavigation` -- impossible d'ouvrir l'Arene.")
        return None
    print("Arene fermee : on l'ouvre (`ToPvp`) -- aucune tentative consommee.")
    jeu.rpc("viewInvoke", [{"surPointeur": nav, "methode": "ToPvp",
                            "args": [True, False], "confirmer": True}], 180000)
    debut = time.time()
    while time.time() - debut < plafond_s:
        time.sleep(2.0)
        r = jeu.rpc("pvpOpponents", [{}], 120000) or {}
        if r.get("nombre"):
            print("  propositions chargees apres %.0f s" % (time.time() - debut))
            return r.get("propositions")
    print("AUCUNE proposition apres %.0f s -- l'ecran n'a pas fini de charger." % plafond_s)
    return None


def archiver(props, horodatage):
    """Figer les propositions : c'est ce qui les rend NON PERISSABLES.

    ⚠ L'horodatage est passe par l'appelant, jamais pris ici -- une archive dont on ne sait pas
    QUAND elle a ete prise ne dit pas si elle est encore jouable a l'Arene."""
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE, "a", encoding="utf-8") as f:
        for p in props:
            f.write(json.dumps({"vu": horodatage, "proposition": p}, ensure_ascii=False) + "\n")
    print("archivees dans %s (%d ligne(s) ajoutee(s))" % (ARCHIVE, len(props)))


def decrire(i, p):
    a = p.get("adversaire") or {}
    print("[%d] board=%-10s sps=%-2s  gain=%-4s perte=%-4s  %s (rating %s, niveau %s)"
          % (i, p.get("boardId"), p.get("spawnPointsSet"), p.get("ratingGain"),
             p.get("ratingLoss"), a.get("displayName"), a.get("rating"), a.get("level")))
    print("     en face : %s" % ", ".join(a.get("lineup") or []))
    print("     MoW     : %s" % (a.get("machineOfWarLineup") or "aucune"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--n", type=int, default=None,
                    help="indice de la proposition a monter. Sans lui : on LIT et on s'arrete.")
    ap.add_argument("--units", default="",
                    help="NOTRE equipe, ids separes par des virgules")
    ap.add_argument("--machine", default=None, help="NOTRE Machine of War (optionnel)")
    ap.add_argument("--account-units", dest="account_units", action="store_true",
                    help="poser `useAccountUnits` -- les unites viennent de la progression "
                         "du compte")
    ap.add_argument("--sans-ouvrir", dest="sans_ouvrir", action="store_true",
                    help="ne pas naviguer vers l'Arene si la liste est vide")
    ap.add_argument("--sans-archive", dest="sans_archive", action="store_true")
    ap.add_argument("--sans-environnement", dest="sans_environnement", action="store_true",
                    help="NE PAS greffer l'environnement d'Arene. Le banc se joue alors sans "
                         "limite de tour : pas d'`EnvEndBombardment`, donc un duel peut "
                         "s'eterniser. La greffe est le DEFAUT.")
    ap.add_argument("--confirmer", action="store_true",
                    help="MONTER la bataille. Sans lui : on imprime la commande, rien n'est monte.")
    ap.add_argument("--adversaire-faux-je-sais", dest="adversaire_faux", action="store_true",
                    help="monter l'equipe adverse depuis NOTRE progression (`--enemies`) au "
                         "lieu de la sienne -- banc de COMPOSITION, pas de confrontation. "
                         "Cf. l'entete de ce fichier.")
    args = ap.parse_args()

    sid = args.session or session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante.")
        return 2
    jeu = Jeu(args.hote, sid)

    props = propositions(jeu, ouvrir=not args.sans_ouvrir)
    if props is None:
        return 2
    print()
    for i, p in enumerate(props):
        decrire(i, p)
    print()
    if not args.sans_archive:
        archiver(props, time.strftime("%Y-%m-%dT%H:%M:%S"))
        print()

    if args.n is None:
        print("--- LECTURE SEULE. `--n <indice> --units <les notres>` pour monter le banc.")
        return 0
    if not (0 <= args.n < len(props)):
        print("REFUS : indice %d hors des %d proposition(s)." % (args.n, len(props)))
        return 2
    if not args.units:
        print("REFUS : `--units` est obligatoire pour monter -- c'est NOTRE equipe.")
        return 2

    p = props[args.n]
    adv = p.get("adversaire") or {}
    lineup = adv.get("lineup") or []
    if not lineup:
        print("REFUS : la proposition %d ne porte pas de lineup adverse (%s) -- rien a monter "
              "en face." % (args.n, p.get("refusAdversaire")))
        return 2

    cmd = [sys.executable, str(Path(__file__).resolve().parent / "sandbox_mode.py"),
           "start" if args.confirmer else "bc",
           "--mode", "pvp", "--session", str(sid),
           "--board", str(p.get("boardId")),
           "--spawn-set", str(p.get("spawnPointsSet")),
           "--units", args.units]
    if args.adversaire_faux:
        # ⚠ L'INDICE DU BANC EST CELUI DE `pvpOpponents`, et les deux voies DOIVENT viser la
        #   meme proposition. Ici on n'envoie que des ids : le lineup vient de la proposition
        #   `args.n` qu'on vient de lire, donc la cible est la meme -- ce sont les STATS qui
        #   seront fausses, pas l'adversaire designe.
        cmd += ["--enemies", ",".join(lineup)]
        if adv.get("machineOfWarLineup"):
            cmd += ["--enemy-machine", adv["machineOfWarLineup"]]
    else:
        # LA VOIE FIDELE : `sandbox_mode.py` ira lire `latestOpponents[n]` lui-meme et
        # materialisera l'equipe ET la MoW par `GetPublicProfileLineup` sur SA progression.
        cmd += ["--adversaire", str(args.n)]
    # ⚠ LA GREFFE EST LE DEFAUT ICI, et c'est le point : un banc d'ARENE sans la pression de fin
    #   n'est pas l'Arene. `EnvEndBombardment` (8 rounds / 20 % PV) est ce qui empeche un duel de
    #   s'eterniser ; sans lui on repete une bataille qui n'existe pas. `--sans-environnement`
    #   reste possible, mais il faut le DEMANDER.
    if not args.sans_environnement:
        cmd += ["--environnement", "arene"]
    if args.machine:
        cmd += ["--machine", args.machine]
    if args.account_units:
        cmd += ["--account-units"]
    if args.confirmer:
        cmd += ["--confirmer"]

    print("--- %s" % ("MONTAGE" if args.confirmer else "PLAN (rien ne sera monte)"))
    print("    " + " ".join(cmd[1:]))
    print()
    p2 = subprocess.run(cmd, cwd=str(RACINE), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    for ligne in (p2.stdout or "").splitlines():
        print("  | " + ligne)
    if p2.returncode != 0:
        print("  | " + (p2.stderr or "")[:600])
        print("`sandbox_mode.py` a rendu %d." % p2.returncode)
    return p2.returncode


if __name__ == "__main__":
    sys.exit(main())
