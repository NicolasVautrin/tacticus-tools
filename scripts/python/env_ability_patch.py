"""INSTALLER une ability d'ENVIRONNEMENT par **MUTATION** de la BC que la source produit.

    python scripts/python/env_ability_patch.py --lister-shield
    python scripts/python/env_ability_patch.py --poser --ability EnvReinforcementShield:1
    python scripts/python/env_ability_patch.py --etat
    python scripts/python/env_ability_patch.py --retirer

Puis MONTER le noeud, qui declenche `CampaignGameModeSource$$LoadBattle` :

    python scripts/python/sandbox_campagne.py --campagne indomitus --noeud 6 --confirmer

⛔ CE N'EST PAS UNE SUBSTITUTION. Le patch est applique par le hook `LoadBattle.onLeave` a la BC
que la source vient de construire, en memoire. Meme fenetre, meme foyer que le calendrier de
vagues (`machine_hunt_patch.py`).

DEUX CHAMPS PORTENT LE NOM `EnvironmentAbilities`, ET LES CONFONDRE EST LE PIEGE :

    BC.EnvironmentAbilities             <- le RECEPTACLE : ce qui est INSTALLE (ce qu'on ecrit)
    BC.Abilities.EnvironmentAbilities   <- le CATALOGUE  : 166 DEFINITIONS (a quoi ca ressemble)

Un grep de la BC trouve un nom dans le SECOND et fait croire au PREMIER. Seul le COMPTE DES
MEMBRES du receptacle tranche -- c'est ce que rend `installees` dans `--etat`.

⚠ LA CIBLE N'EST PAS UN ARGUMENT : ELLE EST ECRITE DANS LE `CreateTrigger` DE L'ABILITY.
Il n'existe aucun champ << equipe >> a passer. Lu au decompile sur `t6dpr4k06g` :

  EnvReinforcementShield (1270)
      On(UnitAdded) | On(InitialMatchUnitAdded)  AND IsHero(Actor) AND IsInTeam(Actor, 1)
      -> l'equipe du JOUEUR. `BC.Player.Players` : playerId=11 TeamId=1 PlayerType=0 << player >>.
      Bouclier = PercentageOf(StatAmount(Actor, ...)), pose a l'AJOUT de chaque heros.
      ⚠ ABSENTE du catalogue de `data/seed-bc.json` -- cf. le paragraphe suivant.

  EnvStartProtection (1280)
      On(TurnStart_EffectActivation) AND TotalTurnsFinished == <const>
      cible `_allAliveUnits - _currentTurnUnits`, donc le camp qui NE JOUE PAS ce tour-la.
      TEAM-AGNOSTIQUE : ce n'est pas << ta team >>, c'est << celui qui ne joue pas >>.
      Bouclier plat : `shieldHp: 500`. PRESENTE au catalogue.

⚠ LE CATALOGUE EST UNE CONDITION QUI N'EMET AUCUN SIGNAL -- meme forme que le `UnitId` d'une
vague, qui a coute une seance entiere. Une ability absente de `BC.Abilities.EnvironmentAbilities`
peut etre parfaitement INSTALLEE et ne rien produire, sans erreur ni evenement. Le hook PUBLIE
donc, pour chaque ability, si son nom y est (`auCatalogue`, tri-etat : `null` = pas mesure).

⚠ `AbilitiesConfigurations` reste VIDE, comme dans `guild-war-config` : sa cle est un TYPE
VALEUR, et se tromper de convention ne leve pas -- ca CRASHE le jeu (2026-08-21).

⚠ LES ORDINAUX SE DEMANDENT AU JEU (`dumpEnum`), on ne recopie pas de table : un miroir fige ici
se perimerait en silence au changement de build.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"
ENUM_NS, ENUM_CLS = "IdunBattle.Entities.Enum", "TriggeredAbilityType"


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--session", type=int, default=None,
                    help="par defaut : la session vivante, demandee au host")
    ap.add_argument("--poser", action="store_true")
    ap.add_argument("--retirer", action="store_true")
    ap.add_argument("--etat", action="store_true")
    ap.add_argument("--lister-shield", action="store_true",
                    help="les abilities d'environnement qui posent un BOUCLIER, et leur cible")
    ap.add_argument("--ability", action="append", default=[],
                    help="`<nom|ordinal>[:niveau]`, repetable. Niveau par defaut 1 "
                         "(0 n'arme RIEN -- c'est ce que fait le natif).")
    # L'EQUIPE D'UN JOUEUR -- un entier ECRIT EN PLACE dans `BC.Player.Players[<id>].TeamId`.
    #
    # ⚠ POURQUOI : les abilities d'environnement sont ecrites pour la GUERRE DE GUILDE, ou
    # l'equipe 1 ATTAQUE et l'equipe 2 DEFEND. Lu au decompile : `EnvFortified` buffe
    # `UnitsFromTeam(..., 2)`, `EnvArtillerySupport` bombarde `UnitsFromTeam(..., 1)`. Or le
    # joueur est `TeamId = 1`. Tout arrive donc a l'envers -- une cause UNIQUE, pas une
    # malchance ability par ability.
    #
    # ⚠ RISQUE NON BORNE PAR LA LECTURE : `TeamId` est un CHAMP, donc tous les
    # `if (a.TeamId == b.TeamId)` du moteur sont INVISIBLES d'un index par methode. Ce qui est
    # etabli : `GetHumanPlayerTeamId` le DERIVE (aucun 1 en dur), et `ToOldPlayerIndex` code en
    # dur mais n'est appele que par du RENDU. Se teste, ne se devine pas.
    # ⚠ LE SEPARATEUR EST `=`, ET CE N'EST PAS UN CAPRICE : un nom d'ability d'environnement
    # CONTIENT des `:` (`EnhancementAddTrait:Stationary`). Couper au `:` -- comme le font
    # `--ability` ou `--place` -- rendrait ces noms-la inexprimables.
    ap.add_argument("--config-ability", action="append", default=[], metavar="SPEC",
                    help="DOTE ou REECRIT une definition du CATALOGUE "
                         "(`BC.Abilities.EnvironmentAbilities`, cle CHAINE) : "
                         "'Nom=cle:valeur[,cle:valeur]'. Repetable. Sert (a) a doter une ability "
                         "qui n'a AUCUNE config -- sans quoi son 1er GetNumberConstant LEVE, en "
                         "<< system error >> ; (b) a CHANGER une constante existante, ex. "
                         "'EnhancementDamageBoost=extraDmgPct:-100' qui met les degats de la "
                         "cible a ZERO. Rien a voir avec `env.AbilitiesConfigurations`, dont la "
                         "cle est un TYPE VALEUR et dont l'insertion a la main crashe le jeu.")
    ap.add_argument("--enhancement", action="append", default=[], metavar="SPEC",
                    help="Installe un ENHANCEMENT -- la SECONDE liste du receptacle, la SEULE "
                         "qui cible par unite NOMMEE : "
                         "'Nom=unitId[,unitId][;stack=N][;niveau=N][;player=N]'. Repetable. "
                         "`stack` est le MULTIPLICATEUR (`DSLFormulas$$EnhancementStack`), pas un "
                         "compteur : mesure sur `EnhancementRegeneration`, stack 1 -> +30 %% des "
                         "PV max, stack 2 -> +60 %%. Une ability gardee par `IsEnhancementTarget` "
                         "(toute la famille `EnhancementAddTrait`) sans cible ne tire JAMAIS -- "
                         "le hook le DIT au lieu de te le laisser deviner.")
    # ⛔ `--equipe`, `--inverser-equipes` et `--sans-groupes-spawn` RETIRES (2026-08-23).
    # Ils pilotaient `playerTeamIds` / `spawnGroupPlayerIndexes`, deux contournements d'un
    # symptome qui n'etait pas le leur : #10046 a mesure que l'inversion des `TeamId` FONCTIONNE
    # cote natif, et que la disparition du camp adverse venait d'un `TWPI 0` code en dur dans
    # `rl_duel.py` -- du HARNAIS. Ce qu'ils visaient se fait par `--adversaire-ouvre` (le camp que
    # protege `EnvStartProtection`) ou par `--enhancement` (viser des unites NOMMEES).
    ap.add_argument("--ordre-des-tours", default=None, metavar="IDS",
                    help="reordonne `BC.Player.TurnOrder`, ex. `12,11,13`. PERMUTATION SEULEMENT "
                         "(le hook refuse toute valeur qui n'est pas un rearrangement de "
                         "l'existant).")
    ap.add_argument("--adversaire-ouvre", action="store_true",
                    help="LE LEVIER DU BOUCLIER : met l'ennemi(12) en tete de TurnOrder. "
                         "`EnvStartProtection` protege le camp qui N'OUVRE PAS -- par defaut "
                         "c'est TOI qui ouvres, donc le bouclier va a l'adversaire. Raccourci de "
                         "`--ordre-des-tours 12,11,13`.")
    a = ap.parse_args()

    if not (a.poser or a.retirer or a.etat or a.lister_shield):
        print("REFUS : choisir --poser, --retirer, --etat ou --lister-shield.")
        return 2

    sid = a.session if a.session is not None else session_vivante(a.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante. Injecter d'abord -- ce script n'injecte "
              "JAMAIS.")
        return 2
    j = Jeu(a.hote, sid)
    print("session %d" % sid)

    # LA TABLE DES ORDINAUX, DEMANDEE AU JEU. `None` = pas mesuree : on ne devine pas.
    d = j.rpc("dumpEnum", [{"asm": "", "ns": ENUM_NS, "cls": ENUM_CLS}], 60000)
    vals = d.get("values") if isinstance(d, dict) else None
    if not isinstance(vals, dict):
        print("REFUS : `dumpEnum %s.%s` MUET -- on jouerait a l'aveugle." % (ENUM_NS, ENUM_CLS))
        return 1
    par_nom = {k: int(v) for k, v in vals.items()}
    par_ord = {v: k for k, v in par_nom.items()}

    if a.lister_shield:
        # Les neuf appelants de `DSLBehaviors$$CreateShield` (case-342), restreints a
        # l'environnement. La CIBLE vient du `CreateTrigger`, lue au decompile.
        cibles = {
            "EnvReinforcementShield": "l'equipe du JOUEUR (IsInTeam 1) -- heros, a leur AJOUT",
            "EnvStartProtection": "le camp qui NE JOUE PAS ce tour (allAlive - currentTurn)",
            "EnvCapturePointShield": "lie aux points de capture (mode SyncPVP)",
        }
        print("\n=== abilities d'ENVIRONNEMENT qui posent un bouclier ===")
        for nom, cible in cibles.items():
            o = par_nom.get(nom)
            print("  %-24s ordinal %-6s cible : %s"
                  % (nom, o if o is not None else "ABSENT DU BUILD", cible))
        print("\n(la cible est ecrite dans le `CreateTrigger` de l'ability -- aucun argument")
        print(" d'ici ne la change.)")
        return 0

    if a.etat:
        r = j.rpc("getBattleConfigPatchStatus", [], 60000) or {}
        print(json.dumps(r, ensure_ascii=False, indent=1)[:3000])
        return 0

    if a.retirer:
        r = j.rpc("clearBattleConfigPatch", [], 60000) or {}
        print("patch RETIRE : %s" % ascii_(json.dumps(r, ensure_ascii=False))[:200])
        return 0 if r.get("ok") else 1

    if not a.ability and not a.config_ability and not a.enhancement:
        print("REFUS : `--poser` sans `--ability`, `--config-ability` ni `--enhancement`."
              " Rien a faire.")
        return 2

    demandes = []
    for spec in a.ability:
        nom, _, niv = spec.partition(":")
        niveau = int(niv) if niv else 1
        if nom.isdigit():
            ordinal = int(nom)
            libelle = par_ord.get(ordinal)
            if libelle is None:
                print("REFUS : ordinal %d ABSENT de `%s` sur ce build." % (ordinal, ENUM_CLS))
                return 3
        else:
            if nom not in par_nom:
                proches = sorted(k for k in par_nom if nom.lower()[:6] in k.lower())
                print("REFUS : `%s` ABSENT de `%s` sur ce build." % (nom, ENUM_CLS))
                if proches:
                    print("        approchants : %s" % ", ".join(proches[:8]))
                return 3
            ordinal, libelle = par_nom[nom], nom
        if niveau == 0:
            print("(!) `%s` a niveau 0 : le natif N'ARME RIEN. Pose quand meme, et le hook le"
                  " DIRA." % libelle)
        demandes.append({"abilityType": ordinal, "niveau": niveau})
        print("  %-28s ordinal %-6d niveau %d" % (libelle, ordinal, niveau))

    # `consumeOnce: False` -- le montage traverse plusieurs `LoadBattle` (la lecture de la source,
    # puis le montage lui-meme). On RETIRE explicitement apres coup (`--retirer`), ce qui est
    # verifiable, alors qu'une consommation automatique ne se voit pas.
    configs = []
    for spec in a.config_ability:
        nom, sep, reste = spec.partition("=")
        if not sep or not nom:
            print("REFUS : --config-ability attend 'Nom=cle:valeur[,cle:valeur]', recu %r" % spec)
            return 2
        consts = {}
        for kv in reste.split(","):
            if not kv:
                continue
            k, s2, v = kv.partition(":")
            if not s2 or not k:
                print("REFUS : --config-ability, paire illisible %r dans %r" % (kv, spec))
                return 2
            # Les constantes de la BC sont des CHAINES, meme quand elles portent un nombre.
            consts[k] = str(v)
        if not consts:
            print("REFUS : --config-ability `%s` sans aucune constante. Ecrire une definition"
                  " VIDE ferait LEVER le premier getter au lieu de le doter." % nom)
            return 2
        # ⚠ LA CLE EST UN ORDINAL, PAS UN NOM. Le catalogue est keye par un
        # `TriggeredAbilityConfigId` (TYPE VALEUR) ; le hook passe donc par
        # `AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbilityType, ...)`, qui prend un
        # ENUM PLAT. Consequence : une VARIANTE (`EnhancementAddTrait:Stationary` = ordinal PLUS
        # `VariantId`) est INEXPRIMABLE par cette voie -- on REFUSE plutot que d'ecrire sur la
        # base et de laisser croire que la variante est dotee.
        if ":" in nom:
            base = nom.split(":", 1)[0]
            print("REFUS : `%s` est une VARIANTE. Le catalogue se keye par un"
                  " `TriggeredAbilityConfigId`" % nom)
            print("        (ordinal + VariantId) et la voie du patch ne passe qu'un ordinal :"
                  " ecrire ici")
            print("        doterait `%s` tout court, pas ta variante. Les 106"
                  " `EnhancementAddTrait:<Trait>`" % base)
            print("        restent joignables par la voie SEED BC (`--seed-bc` de rl_duel), ou"
                  " Newtonsoft")
            print("        construit les cles lui-meme.")
            return 3
        if nom not in par_nom:
            proches = sorted(k for k in par_nom if nom.lower()[:6] in k.lower())
            print("REFUS : `%s` ABSENT de `%s` sur ce build." % (nom, ENUM_CLS))
            if proches:
                print("        approchants : %s" % ", ".join(proches[:8]))
            return 3
        configs.append({"abilityType": par_nom[nom], "nom": nom, "constants": consts})
        print("  catalogue %-30s ordinal %-6d <- %s"
              % (nom, par_nom[nom], json.dumps(consts, ensure_ascii=False)))

    enhancements = []
    for spec in a.enhancement:
        nom, sep, reste = spec.partition("=")
        if not sep or not nom:
            print("REFUS : --enhancement attend 'Nom=unitId[,unitId][;stack=N]', recu %r" % spec)
            return 2
        morceaux = reste.split(";")
        cibles = [u for u in morceaux[0].split(",") if u]
        opts = {}
        for o in morceaux[1:]:
            k, s2, v = o.partition("=")
            if not s2 or k not in ("stack", "niveau", "player"):
                print("REFUS : --enhancement, option inconnue %r (attendu stack= / niveau= /"
                      " player=)" % o)
                return 2
            try:
                opts[k] = int(v)
            except ValueError:
                print("REFUS : --enhancement, `%s` attend un entier, recu %r" % (k, v))
                return 2
        e = {"ability": nom, "cibles": cibles,
             "stack": opts.get("stack", 1), "niveau": opts.get("niveau", 1)}
        if "player" in opts:
            e["playerId"] = opts["player"]
        enhancements.append(e)
        print("  enhancement %-30s cibles=%s stack=%d niveau=%d%s"
              % (nom, ",".join(cibles) or "(AUCUNE)", e["stack"], e["niveau"],
                 (" player=%d" % e["playerId"]) if "playerId" in e else ""))
        if not cibles:
            print("      (!) AUCUNE cible : legitime pour une ability qui choisit sa cible dans")
            print("          son propre arbre (ex. EnhancementRegeneration, qui vise team 1 /")
            print("          UnitTrait.Hero), mais la famille EnhancementAddTrait ne tirera PAS.")

    patch = {"consumeOnce": False}
    if configs:
        patch["environmentAbilityConfigs"] = configs
    if enhancements:
        patch["environmentEnhancements"] = enhancements
    if demandes:
        patch["environmentAbilities"] = demandes
    ordre = None
    if a.ordre_des_tours:
        try:
            ordre = [int(x) for x in a.ordre_des_tours.replace(" ", "").split(",") if x]
        except ValueError:
            print("REFUS : --ordre-des-tours attend des entiers separes par des virgules.")
            return 2
    elif a.adversaire_ouvre:
        # PLAYER_ID_AI en tete. On ne touche NI aux equipes NI aux groupes de spawn : le ciblage
        # d'`EnvStartProtection` est team-agnostique, seul l'ordre compte.
        ordre = [12, 11, 13]
    if ordre:
        patch["turnOrder"] = ordre
    r = j.rpc("setBattleConfigPatch", [patch], 60000) or {}
    if not r.get("ok"):
        print("REFUS : %s" % ascii_(json.dumps(r, ensure_ascii=False))[:400])
        return 1

    print()
    print("patch ARME : %d ability(ies) d'environnement, %d definition(s) de catalogue,"
          " %d enhancement(s)%s."
          % (len(demandes), len(configs), len(enhancements),
             (", TurnOrder -> [%s]" % ",".join(str(x) for x in ordre)) if ordre else ""))
    print("Applique au PROCHAIN `LoadBattle`, PAR MUTATION de la BC que la source produit.")
    print("Monter ensuite le noeud, puis `--etat` : `lastApply.operations` dit ce qui a ete")
    print("REELLEMENT installe (`installees`), et `warnings` nomme une absence du CATALOGUE.")
    print("L'armement, lui, ne prouve RIEN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
