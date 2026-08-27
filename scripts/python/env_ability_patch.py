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


# ⛔ `--help` PLANTAIT, ET C'EST LE PIRE ENDROIT OU PLANTER. `argparse` imprime `description=__doc__`,
# donc TOUTE la docstring de ce module part vers une console cp1252 ; le premier `⛔` y levait un
# `UnicodeEncodeError` et l'aide entiere devenait inaccessible (mesure du 2026-08-27). La regle du
# depot -- << ASCII only en sortie >> -- vise les chaines qu'ON ecrit ; ici c'est argparse qui
# imprime, et purger les pavas de leurs marqueurs les rendrait illisibles a la relecture.
#
# ⚠ ON NE CHANGE PAS L'ENCODAGE, ON CHANGE LA POLITIQUE D'ERREUR. Passer stdout en UTF-8 ferait
# sortir des octets que la console ne sait pas rendre ; `backslashreplace` garde cp1252 et
# remplace l'irreproductible par sa forme echappee. Aucune sortie ne peut plus faire tomber le
# script, et ce qui etait deja ASCII est inchange.
try:
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
except Exception:      # flux redirige/remplace : on n'insiste pas, on n'a rien casse
    pass


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
    ap.add_argument("--une-fois", dest="une_fois", action="store_true",
                    help="`consumeOnce` : le patch est consomme par le PREMIER `LoadBattle`. "
                         "A poser quand la SOURCE n'est presente qu'a ce premier passage (chaine "
                         "de l'evenement Machines of War) -- sinon la seconde application, sans "
                         "source, derive 0 cible et ECRASE la premiere. Cf. le commentaire au "
                         "site de `consumeOnce`.")
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
    # LES DEUX VERROUS DE LA PROPAGATION DU FEU -- et plus generalement, tout ce qui vit hors du
    # catalogue d'ENVIRONNEMENT.
    #
    # ⛔ POURQUOI CE N'EST PAS `--config-ability`. `BC.Abilities` porte QUATRE familles ; le champ
    # ci-dessus n'atteint que `EnvironmentAbilities`. Les abilities de TUILE sont des PASSIFS :
    # `DryBushFireSpread` y range son `spreadProbability`, et `BC.Tiles[].TriggeredAbilities` dit
    # quels TYPES de tuile sont eligibles. Les deux se lisent au decompile dans
    # `DryBushFireSpreadAbility$$CreateBehaviour` :
    #     AdjacentTiles(moi) -> TilesWithTriggeredAbility(0x39) -> EntitiesWithoutEffects([5])
    #                        -> Maybe(GetNumberConstant(0x25))
    # `0x39` = 57 (l'ability elle-meme, cherchee dans le catalogue de TYPES) et
    # `AbilityConstantType 0x25` = `spreadProbability`.
    #
    # ⚠ ON PATCHE, ON NE SUBSTITUE PLUS. La premiere version passait par `sandboxModeBcOverride`
    # (`sandbox_campagne --bc`) : ca marche en sandbox et NE PEUT PAS marcher ailleurs, l'override
    # ne detournant que `SandboxGameModeSource`. Mesure du 2026-08-27 en bataille REELLE -- la BC
    # chargee rendait `spreadProbability: "10"` et `Grass.TriggeredAbilities: []`, pendant que le
    # patch d'environnement, lui, etait bien la (`EnvFireTileDamage.hpPct: "0"`).
    ap.add_argument("--config-passive", action="append", default=[], metavar="SPEC",
                    help="meme forme que `--config-ability`, mais dans "
                         "`BC.Abilities.PassiveAbilities` -- la famille des abilities de TUILE. "
                         "Ex. 'DryBushFireSpread=spreadProbability:100' (10 au gameconfig, donc "
                         "10 %% par voisin et par tour).")
    ap.add_argument("--tuile-ability", action="append", default=[], metavar="SPEC",
                    help="rend un TYPE de tuile porteur d'abilities declenchees : "
                         "'TileId=<Nom>[,<Nom>]'. Ex. 'Grass=DryBushFireSpread' pour que l'herbe "
                         "devienne inflammable (sur `C2_28` : 4 cases sur 35 -> 29). Le NOM est la "
                         "forme normale ; un ordinal nu est accepte mais DECONSEILLE (il se perime "
                         "en silence au changement de build). On AJOUTE a la liste existante, "
                         "jamais on ne la remplace -- `DryBush` porte [DryBushFireSpread, "
                         "LightCover] et perdre `LightCover` fausserait les degats a distance.")
    # ⛔ `--vider-pose` RETIRE (2026-08-23), avec le champ `viderPredefinedUnits` du hook et son
    # unique appelant `sandbox_onslaught.py`. Il vidait `BC.PredefinedUnits` pour rattraper une BC
    # fabriquee par `SandboxWavesBattleConfig`, dont le ctor confond catalogue et pose. Sur une BC
    # montee par sa SOURCE -- la forme que le jeu produit vraiment, mesuree sur 6 replays reels --
    # `PredefinedUnits` porte l'ADVERSAIRE et les unites du joueur entrent par `AddUnitMessage` :
    # le vider y effacerait l'ennemi. On laisse la source monter sa BC, le besoin disparait.
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
    # `rl_duel.py` -- du HARNAIS. Ce qu'ils visaient se fait par `--enhancement` (viser des
    # unites NOMMEES).
    #
    # ⛔ `--ordre-des-tours` ET `--adversaire-ouvre` RETIRES AUSSI (2026-08-23), avec le champ
    # `turnOrder` du hook et `ecrireOrdreDesTours`. Aucun appelant par programme : les probes qui
    # citent `BC.Player.TurnOrder` le LISENT depuis un seed BC sur disque, elles n'ecrivaient
    # jamais par ce canal. Ils ne servaient qu'au bouclier d'environnement `EnvStartProtection`,
    # dont on a decide de ne pas se servir.
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

    if not (a.ability or a.config_ability or a.enhancement
            or a.config_passive or a.tuile_ability):
        print("REFUS : `--poser` sans `--ability`, `--config-ability`, `--enhancement`,")
        print("        `--config-passive` ni `--tuile-ability`. Rien a faire.")
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

    # `consumeOnce: False` par defaut -- le montage traverse plusieurs `LoadBattle` (la lecture de
    # la source, puis le montage lui-meme). On RETIRE explicitement apres coup (`--retirer`), ce
    # qui est verifiable, alors qu'une consommation automatique ne se voit pas.
    #
    # ⛔ MAIS SUR UNE CHAINE OU LA SOURCE N'EST PRESENTE QU'AU PREMIER `LoadBattle`, LE SECOND
    # PASSAGE DETRUIT LE TRAVAIL DU PREMIER -- et en silence. Mesure du 2026-08-24, evenement
    # Machines of War : la forge (`mowEventSourceForger`) applique AVEC la source et derive
    # << 29 cible(s) = 24 de la SOURCE U ... >> ; le montage sandbox re-applique SANS elle
    # (`source=SandboxGameModeSource`), derive << 0 cible(s) (voie=aucune) >> et REECRIT le noeud
    # (`relu=true`). L'enhancement final porte donc ZERO cible : rien n'est buffe, et la seule
    # trace est un avertissement dans `lastApply` -- que personne ne relit APRES le montage,
    # puisqu'on l'a deja lu, juste, APRES la forge.
    # ⇒ `--une-fois` fait consommer le patch par le PREMIER `LoadBattle`. La BC substituee au
    #   montage porte alors deja l'installation correcte : il n'y a plus rien a re-appliquer.
    # ⚠ LE VRAI REMEDE EST DANS LE HOOK, et il n'est PAS ici : une application qui ne sait deriver
    #   AUCUNE cible pour un `ciblesAuto` ne devrait pas pouvoir ECRASER une installation qui en
    #   porte. Ca demande un rebuild + reinject, donc une fenetre ; ce drapeau est la parade
    #   d'ici la.
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
        # ⛔ `auto=` AVANT LE PREMIER `;` EST UNE CIBLE, PAS UNE OPTION -- ET CA NE LEVE RIEN.
        #
        # `Nom=auto=adversaire;stack=1` se lit `cibles = ["auto=adversaire"]` : la sentinelle part
        # dans la BC comme `UnitConfigId.PureId`, aucune unite ne lui correspond, et l'enhancement
        # se lie a PERSONNE. Mesure du 2026-08-26 sur un banc onslaught -- le patch s'installait,
        # `installees` rendait 3, et le debuff n'existait pas :
        #
        #     camps derives : 0 unite(s) a MOI, 4 ADVERSE(S)          <- la derivation MARCHE
        #     1 Target(s) ECRITE(S) = [{"PureId":"auto=adversaire"}]  <- mais c'est CA qui est ecrit
        #
        # La faute se voit a l'absence de ligne `cible(s) =` pour cette entree : la branche de
        # resolution n'a jamais tourne, puisque `ciblesAuto` etait resté nul. La forme juste met la
        # liste de cibles a VIDE et passe l'auto en OPTION : `Nom=;auto=adversaire;stack=1`.
        #
        # On refuse plutot que de corriger en douce : accepter les deux ecritures ferait croire que
        # `Nom=auto=moi` marche aussi, alors que la meme faute y est silencieuse dans l'autre sens.
        _sentinelles = [c for c in cibles if c.startswith("auto=")]
        if _sentinelles:
            print("REFUS : --enhancement %r -- %s est ECRIT COMME UNE CIBLE, pas comme une option."
                  % (spec, ", ".join(repr(s) for s in _sentinelles)))
            print("  Tout ce qui precede le premier `;` est une liste d'unitIds. La sentinelle")
            print("  partirait dans la BC comme `UnitConfigId.PureId` et ne matcherait AUCUNE")
            print("  unite -- l'enhancement serait installe et INERTE, sans le moindre message.")
            print("  Forme juste (liste de cibles VIDE, auto en option) :")
            print("      --enhancement '%s=;%s%s'"
                  % (nom, _sentinelles[0],
                     "".join(";" + o for o in morceaux[1:])))
            return 2
        opts = {}
        auto = None
        for o in morceaux[1:]:
            k, s2, v = o.partition("=")
            if not s2 or k not in ("stack", "niveau", "player", "auto"):
                print("REFUS : --enhancement, option inconnue %r (attendu stack= / niveau= /"
                      " player= / auto=)" % o)
                return 2
            # ⚠ `auto` NE SE RESOUT PAS ICI. Les cibles se derivent de la BC, qui n'existe qu'a
            # la fenetre `LoadBattle.onLeave` -- c'est justement ce qui permet a UN armement de
            # mordre sur n'importe quelle proposition sans qu'on renomme quoi que ce soit.
            if k == "auto":
                if v not in ("adversaire", "moi"):
                    print("REFUS : --enhancement, `auto=` attend `adversaire` ou `moi`,"
                          " recu %r" % v)
                    return 2
                auto = v
                continue
            try:
                opts[k] = int(v)
            except ValueError:
                print("REFUS : --enhancement, `%s` attend un entier, recu %r" % (k, v))
                return 2
        e = {"ability": nom, "cibles": cibles,
             "stack": opts.get("stack", 1), "niveau": opts.get("niveau", 1)}
        if auto is not None:
            e["ciblesAuto"] = auto
        if "player" in opts:
            e["playerId"] = opts["player"]
        enhancements.append(e)
        print("  enhancement %-30s cibles=%s stack=%d niveau=%d%s%s"
              % (nom, ",".join(cibles) or ("(AUTO)" if auto else "(AUCUNE)"),
                 e["stack"], e["niveau"],
                 (" auto=%s" % auto) if auto else "",
                 (" player=%d" % e["playerId"]) if "playerId" in e else ""))
        if auto is not None:
            camp = "d'un TeamId AUTRE que le mien" if auto == "adversaire" else "de MON TeamId"
            print("      cibles DERIVEES a l'application : tout ce qui appartient a un joueur %s"
                  % camp)
            print("      (`BC.Player.Players`, `PlayerType 0` = moi ; poses + machines + vagues).")
            print("      Rien a renommer quand la proposition ou la lineup change.")
            if auto == "moi":
                print("      UNION avec les %d cible(s) ecrite(s) ci-dessus, MOINS tout ce qui est"
                      % len(cibles))
                print("      adverse (`UnitConfigId$$Equals` ignore `IsPvpOpponent`, donc la copie")
                print("      d'en face serait appariee elle aussi).")
                if not cibles:
                    print("      (!) AUCUNE cible ecrite : en PvP la BC ne porte PAS ta lineup (elle")
                    print("          entre par `AddUnitMessage` au deploiement) -- l'entree y serait")
                    print("          VIDE. Fournir un sur-ensemble (le roster) est ce qui tient.")
            elif cibles:
                print("      (!) les %d cible(s) ecrite(s) ci-dessus seront IGNOREES :"
                      % len(cibles))
                print("          `auto=adversaire` derive integralement.")
        elif not cibles:
            print("      (!) AUCUNE cible : legitime pour une ability qui choisit sa cible dans")
            print("          son propre arbre (ex. EnhancementRegeneration, qui vise team 1 /")
            print("          UnitTrait.Hero), mais la famille EnhancementAddTrait ne tirera PAS.")

    # --- les PASSIFS et les TUILES : meme fenetre, autres dictionnaires ---------------------
    #
    # (!)ON REUTILISE L'ANALYSEUR DE `--config-ability`, PARCE QUE LA FORME EST LA MEME. Ce qui
    # change est la FAMILLE visee, pas la grammaire. En ecrire un second divergerait au premier
    # correctif.
    passifs = []
    for spec in a.config_passive:
        nom, sep, reste = spec.partition("=")
        if not sep or not nom:
            print("REFUS : --config-passive attend 'Nom=cle:valeur[,cle:valeur]', recu %r" % spec)
            return 2
        consts = {}
        for kv in reste.split(","):
            if not kv:
                continue
            k, s2, v = kv.partition(":")
            if not s2 or not k:
                print("REFUS : --config-passive, paire illisible %r dans %r" % (kv, spec))
                return 2
            consts[k] = str(v)
        if not consts:
            print("REFUS : --config-passive `%s` sans aucune constante -- une definition VIDE"
                  " ferait LEVER le premier getter au lieu de le doter." % nom)
            return 2
        ordinal = par_nom.get(nom)
        if ordinal is None:
            print("REFUS : `%s` n'est pas un `TriggeredAbilityType` connu du build." % nom)
            return 2
        passifs.append({"abilityType": ordinal, "nom": nom, "constants": consts})

    tuiles = []
    for spec in a.tuile_ability:
        tid, sep, reste = spec.partition("=")
        if not sep or not tid:
            print("REFUS : --tuile-ability attend 'TileId=<Nom>[,<Nom>]', recu %r" % spec)
            print("        ex. --tuile-ability 'Grass=DryBushFireSpread'")
            return 2
        ords, lus = [], []
        for x in reste.split(","):
            x = x.strip()
            if not x:
                continue
            # ⚠ LE NOM EST LA FORME NORMALE, L'ORDINAL EST L'EXCEPTION -- et c'est la regle du
            # depot, pas un gout : << un ENTIER qui DESIGNE quelque chose passe par un ENUM >>.
            # Un ordinal juste aujourd'hui devient faux au changement de build, EN SILENCE, et
            # `TilesWithTriggeredAbility` comparerait alors une ability que personne ne cherche.
            # On accepte quand meme l'entier (il faut bien pouvoir viser un membre que le miroir
            # n'a pas encore), mais on le SIGNALE et on imprime le nom qu'il designe.
            if x.lstrip("-").isdigit():
                n = int(x)
                nom_lu = par_ord.get(n)
                print("  (!) --tuile-ability `%s` : ordinal NU %d. Il designe `%s` sur CE build ;"
                      % (tid, n, nom_lu if nom_lu else "AUCUN membre connu"))
                print("      ecrire le nom le rend stable au changement de build.")
                if nom_lu is None:
                    print("REFUS : l'ordinal %d n'est AUCUN `%s` de ce build -- on n'inscrit pas"
                          " une ability que rien ne nomme." % (n, ENUM_CLS))
                    return 2
                ords.append(n)
                lus.append("%s(%d)" % (nom_lu, n))
            else:
                n = par_nom.get(x)
                if n is None:
                    print("REFUS : --tuile-ability, `%s` n'est pas un `%s` de ce build."
                          % (x, ENUM_CLS))
                    proches = [k for k in par_nom if x.lower() in k.lower()][:6]
                    if proches:
                        print("        noms approchants : %s" % ", ".join(proches))
                    return 2
                ords.append(n)
                lus.append("%s(%d)" % (x, n))
        if not ords:
            print("REFUS : --tuile-ability `%s` sans aucune ability." % tid)
            return 2
        # (!)ON IMPRIME CE QU'ON VA ECRIRE, RESOLU. C'est la seule ligne qui relie le nom tape a
        # l'ordinal qui partira dans la BC -- sans elle, `Grass=57` ne dit rien a personne.
        print("  tuile %-12s <- %s" % (tid, ", ".join(lus)))
        tuiles.append({"tileId": tid, "ajouter": ords})

    patch = {"consumeOnce": bool(a.une_fois)}
    if configs:
        patch["environmentAbilityConfigs"] = configs
    if passifs:
        patch["passiveAbilityConfigs"] = passifs
    if tuiles:
        patch["tileTriggeredAbilities"] = tuiles
    if enhancements:
        patch["environmentEnhancements"] = enhancements
    if demandes:
        patch["environmentAbilities"] = demandes
    r = j.rpc("setBattleConfigPatch", [patch], 60000) or {}
    if not r.get("ok"):
        print("REFUS : %s" % ascii_(json.dumps(r, ensure_ascii=False))[:400])
        return 1

    print()
    # (!)LE BILAN NOMME LES CINQ FAMILLES, MEME A ZERO. Il en taisait deux (`--config-passive`,
    # `--tuile-ability`) : on lisait << 2 definitions de catalogue >> sur un patch qui en portait
    # aussi une de passif et une de tuile, donc on ne pouvait pas voir qu'elles etaient parties.
    print("patch ARME : %d ability(ies) d'environnement, %d definition(s) de catalogue,"
          " %d enhancement(s),"
          % (len(demandes), len(configs), len(enhancements)))
    print("             %d config(s) de PASSIF, %d type(s) de TUILE."
          % (len(passifs), len(tuiles)))
    print("Applique au PROCHAIN `LoadBattle`, PAR MUTATION de la BC que la source produit.")
    print("Monter ensuite le noeud, puis `--etat` : `lastApply.operations` dit ce qui a ete")
    print("REELLEMENT installe (`installees`), et `warnings` nomme une absence du CATALOGUE.")
    print("L'armement, lui, ne prouve RIEN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
