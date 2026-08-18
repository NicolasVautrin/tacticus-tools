"""#287-r5 -- le RECENSEMENT des 46 ids sans regle dynamique portee, RE-DERIVE de la table.

CE QUE CE PROBE CORRIGE. `probe_287r4r1_dynamic_target_rules.py` porte une table `SYMBOLE_NATIF`
ECRITE A LA MAIN : elle dit, id par id, si une surcharge native est lisible. Une table ecrite ne se
perime pas bruyamment -- au prochain build elle continue de repondre, avec les noms d'hier. Ici le
recensement est DERIVE de `data/symbols/<build>/ghidra/functions.tsv` : l'appariement se fait par le
nom de classe `<AbilityName>Ability`, et un id dont le symbole disparait le DIT.

⚠ ETAT AU 2026-08-18 (#287-r5-r3) : la population (a) ci-dessous vaut **0** -- la dette est
RESORBEE, les quinze etages recenses ont tous ete franchis. Le cliquet ACTIF de ce probe est donc
`orphelins` (un id a surcharge native lisible et non evaluable doit DECLARER son etage) doublé du
NON-EFFONDREMENT, qui remplace `fantomes` devenu vacant. Re-deriver ces chiffres, ne pas les citer.

CE QUE LE RECENSEMENT A CHANGE (mesure du 2026-08-06). Le chiffre « aucune regle : 46 » melangeait
DEUX populations que rien ne separait :

  (a) 19 ids dont une surcharge NATIVE est lisible -- le port ne sait pas evaluer un corps qui
      EXISTE. C'est la dette reelle.
  (b) 27 ids sans aucune surcharge dans la table. Pour eux, le delegue `options+0x38` pointe le
      corps de BASE `IdunBattle.Entities.Abilities.AActiveAbility$$GetDynamicInvalidTargetReason`,
      dont le corps est `return 0` -- LU au decompile, et lu par une voie qui ne suppose rien : le
      fallback EXPLICITE de `...ForwardObserversAbility$$GetDynamicInvalidTargetReason` appelle ce
      corps, que Ghidra mislabelle `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`
      (IL2CPP deduplique les corps triviaux et n'attribue qu'UN proprietaire). Le `0` du port y
      COINCIDE donc avec le natif.

⚠ CE QUE (b) NE PROUVE PAS. L'absence d'un symbole dans une table indexee par ADRESSE ne prouve
jamais qu'une classe ne surcharge pas (CLAUDE.md, « l'ABSENCE d'une methode dans les tables ne prouve
RIEN »). (b) dit exactement ceci : le port n'a RIEN A LIRE, et la seule lecture disponible -- le
corps de base -- concorde avec ce qu'il rend. Trancher formellement demanderait le slot de vtable
`+0x480` sur l'INSTANCE, au runtime. Le probe l'ECRIT au lieu de le taire.

DEUX MESURES, toutes OFFLINE :

  1. RECENSEMENT PAR ETAGE. Chaque id de la population (a) porte l'ETAGE qui bloque son port, LU au
     decompile. Le probe imprime le compte par etage : c'est le seul chiffre qui repond a « quel
     etage debloque le plus d'ids ».
  2. CLIQUET D'APPARIEMENT. Tout id de la table d'etages doit encore trouver son symbole natif dans
     `functions.tsv`, et tout id classe « sans surcharge » doit encore n'en avoir aucun. Un
     renommage inter-build fait donc ROUGIR ce probe au lieu de le laisser mentir.

Usage :
    python scripts/python/probe_287r5_etages_bloquants.py
    python scripts/python/probe_287r5_etages_bloquants.py --ids
ASCII only ; exit 0 = l'appariement tient et le recensement n'est pas vide.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import symbols_layout                                                          # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                                 # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402

SUFFIXE = "$$GetDynamicInvalidTargetReason"

# Le corps de BASE, partage par toute sous-classe qui ne surcharge pas. Ghidra l'attribue a un autre
# proprietaire (deduplication IL2CPP d'un `return 0`) ; c'est le fallback explicite de
# `...ForwardObserversAbility$$GetDynamicInvalidTargetReason` qui l'identifie sans ambiguite.
CORPS_DE_BASE = "Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId"

# L'ETAGE bloquant, id par id -- LU dans le decompile de la surcharge native, jamais devine. Un id
# absent de cette table alors que son symbole existe fait ROUGIR l'etape 2 : le recensement ne peut
# pas se taire sur un corps qu'il voit.
# `AActiveAbility+0x20` est `IdunBattle.Core.Services.BattleQuery` -- etabli par
# `IdunBattle.Core.Services.TargetingQuery$$Init`, qui le pose en `+0x18`, et par le second site de
# `TargetingQuery$$GetTilesInRange`. Les etages sont GROUPES par leur libelle : c'est ce groupement
# qui repond a « quel etage debloque le plus d'ids », et non le detail par ability.
ETAGE_BLOQUANT: dict = {
    # ⚠ VIDE, ET C'EST UNE MESURE -- PAS UN OUBLI (#287-r5-r3, 2026-08-18).
    #
    # Cette table a porte quinze entrees. Les quinze sont SORTIES, pour la raison exacte que le
    # commentaire de `DeathOnTheWind` (#287-r11) avait deja ecrite : une entree d'etage pour une
    # regle PORTEE n'est plus dans `dette`, donc jamais imprimee -- une declaration muette et
    # fausse. Ce qui a change entre-temps, c'est que la condition s'est mise a valoir pour TOUTES :
    #
    #   `P.evaluabilite(aid)` rend `surcharge` pour les 15 -- TheQuickening, VigilanceEternal,
    #   LeadingTheCharge, AlphaWarrior, EntropyCannons, SquigLaunchas, ExcruciatingFrequencies,
    #   SendInTheNextWave, HeroicFusillade, SkyStrike, CultDemagogue, ExemplarOfTheKauyon,
    #   MV71SniperDroneSquadAttack, AttemptedPossession, MindControl.
    #
    # Les etages qu'elles declaraient (tuiles de mouvement du caster, triggers et selecteurs DSL,
    # pathfinding, battleQuery, SIMULATION d'effet, predicat statique a corps deduplique) ont donc
    # tous ete franchis. La DETTE mesuree est passee de 19 a **0**.
    #
    # ⚠ CE QUE CE VIDE COUTE, ET CE QUI LE REMPLACE. Le cliquet `fantomes` boucle SUR cette table :
    # vide, il devient vacant. Il gardait un fait reel -- « `ghidra/functions.tsv` repond encore aux
    # noms qu'on lui demande » -- et ce fait ne doit pas cesser d'etre garde parce que la dette a
    # disparu. Il l'est desormais par `symboles_natifs()` NON EFFONDRE (cf. `main` et
    # `test_287r5_dynamic_target_rules_offline.py`) : si la table cessait de repondre, TOUT id
    # tomberait dans `base` -- « aucune surcharge, le port coincide » -- et le probe rendrait un
    # VERT PUR sur un recensement qui n'a rien lu. C'est le seul regime dangereux ici, et c'est
    # celui-la qu'il faut garder, pas le compte d'une dette eteinte.
    #
    # Une entree NEUVE se remet ici des qu'un id a surcharge native lisible n'est pas evaluable :
    # le cliquet `orphelins` -- lui, toujours arme, et desormais le cran ACTIF de ce probe -- le
    # reclame nommement.
}

#: Borne BASSE de non-effondrement de `symboles_natifs()`. MESUREE le 2026-08-18 sur
#: `t6dpr4k06g` : **60** surcharges directes lisibles. Ecrite BASSE (20) -- elle garde
#: l'effondrement (table illisible, suffixe renomme, layout change), pas la cadence.
PLANCHER_SYMBOLES = 20

#: Borne BASSE de la population VISITEE (`ids_portant_le_bit`). MESUREE : **85**. Meme discipline.
PLANCHER_POPULATION = 40


def symboles_natifs(build: str | None = None) -> dict:
    """`{nom court de classe: symbole plein}` pour toutes les surcharges DIRECTES de la table.

    Les lambdas et les `<>c__DisplayClass` sont ECARTES : leur nom ne se termine pas par le suffixe
    (ils portent `u003CGetDynamicInvalidTargetReasonu003Eb__N`), donc ce ne sont pas des corps de
    surcharge mais des fermetures internes."""
    tsv = symbols_layout.build_dir(build) / "ghidra" / "functions.tsv"
    out = {}
    for ligne in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if SUFFIXE not in ligne:
            continue
        _addr, _, nom = ligne.partition("\t")
        if not nom.endswith(SUFFIXE):
            continue
        out.setdefault(nom[:-len(SUFFIXE)].split(".")[-1], nom)
    return out


def recenser(build: str | None = None) -> dict:
    """Ventile les ids qui posent le bit, avec leur symbole natif RE-DERIVE."""
    par_classe = symboles_natifs(build)
    res = {"portee": [], "table": [], "dette": [], "base": []}
    for aid in P.ids_portant_le_bit():
        nom = ActiveAbilityType(aid).name
        symbole = par_classe.get(nom + "Ability")
        etat = P.evaluabilite(aid)
        if etat == "surcharge":
            res["portee"].append((aid, nom, symbole))
        elif etat == "table":
            res["table"].append((aid, nom, symbole))
        elif symbole is not None:
            res["dette"].append((aid, nom, symbole))
        else:
            res["base"].append((aid, nom, None))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r5 : les etages qui bloquent le port")
    ap.add_argument("--ids", action="store_true", help="detail id par id")
    ap.add_argument("--build", default=None)
    a = ap.parse_args()

    build = a.build or symbols_layout.current_build()
    res = recenser(build)
    aucune = res["dette"] + res["base"]
    print("[287-r5] RECENSEMENT RE-DERIVE de data/symbols/%s/ghidra/functions.tsv" % build)
    print("  ids posant TargetMatchesDynamicRule            : %d"
          % sum(len(v) for v in res.values()))
    print("  regle EVALUABLE par le port (surcharge/table)  : %d"
          % (len(res["portee"]) + len(res["table"])))
    print("  AUCUNE regle portee (le `0` permissif)         : %d" % len(aucune))
    print("    dont surcharge NATIVE lisible -> DETTE REELLE : %d" % len(res["dette"]))
    print("    dont AUCUNE surcharge -> corps de BASE `%s` = `return 0`, le port COINCIDE : %d"
          % (CORPS_DE_BASE, len(res["base"])))
    print("      (l'absence dans une table indexee par ADRESSE ne PROUVE pas le non-override :")
    print("       trancher demanderait le slot de vtable +0x480 sur l'INSTANCE, au runtime)")

    par_etage = {}
    for aid, nom, _s in res["dette"]:
        par_etage.setdefault(ETAGE_BLOQUANT.get(aid, "<NON RECENSE>"), []).append(nom)
    print("[287-r5] ETAGES BLOQUANTS -- combien d'ids chacun retient")
    if not par_etage:
        print("  (aucun) -- DETTE VIDE : plus aucun id ne pose le bit avec une surcharge NATIVE")
        print("  lisible et non evaluable. Ce n'est PAS un silence : le non-effondrement ci-dessous")
        print("  etablit que le recensement a bien lu la table avant de rendre ce zero.")
    for etage, noms in sorted(par_etage.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print("  %-2d  %-62s %s" % (len(noms), etage, ",".join(sorted(noms))))

    # CLIQUET D'APPARIEMENT : la table d'etages et la table de symboles doivent rester en phase.
    par_classe = symboles_natifs(build)
    orphelins = [nom for aid, nom, _s in res["dette"] if aid not in ETAGE_BLOQUANT]
    fantomes = [ActiveAbilityType(aid).name for aid in ETAGE_BLOQUANT
                if ActiveAbilityType(aid).name + "Ability" not in par_classe]
    # NON-EFFONDREMENT -- le remplacant de `fantomes`, qui devient vacant quand ETAGE_BLOQUANT se
    # vide. Sans lui, une table illisible ferait tomber TOUT id dans `base` et le probe rendrait
    # OK sur un recensement qui n'a rien lu.
    population = len(list(P.ids_portant_le_bit()))
    effondre = []
    if len(par_classe) < PLANCHER_SYMBOLES:
        effondre.append("symboles natifs lus = %d < %d (functions.tsv illisible, suffixe %r "
                        "renomme, ou layout de build change)"
                        % (len(par_classe), PLANCHER_SYMBOLES, SUFFIXE))
    if population < PLANCHER_POPULATION:
        effondre.append("ids posant le bit = %d < %d (la population VISITEE s'est effondree)"
                        % (population, PLANCHER_POPULATION))
    print("[287-r5] CLIQUET")
    print("  ids a surcharge native SANS etage recense (le recensement se tait) : %d %s"
          % (len(orphelins), ",".join(orphelins) or ""))
    print("  entrees d'ETAGE_BLOQUANT sans symbole natif (renomme/disparu)      : %d %s"
          % (len(fantomes), ",".join(fantomes) or ""))
    print("  NON-EFFONDREMENT : %d symbole(s) natif(s) lu(s), %d id(s) visite(s) -- %s"
          % (len(par_classe), population, "OK" if not effondre else "ROUGE"))
    for ligne in effondre:
        print("    ROUGE %s" % ligne)

    if a.ids:
        print("[287-r5] DETAIL")
        for cle in ("portee", "table", "dette", "base"):
            for aid, nom, symbole in res[cle]:
                print("  %-6d %-30s %-8s %s" % (aid, nom, cle, symbole or "-"))

    ok = bool(aucune or res["portee"]) and not orphelins and not fantomes and not effondre
    print("[287-r5] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
