"""#287-r5 -- le RECENSEMENT des 46 ids sans regle dynamique portee, RE-DERIVE de la table.

CE QUE CE PROBE CORRIGE. `probe_287r4r1_dynamic_target_rules.py` porte une table `SYMBOLE_NATIF`
ECRITE A LA MAIN : elle dit, id par id, si une surcharge native est lisible. Une table ecrite ne se
perime pas bruyamment -- au prochain build elle continue de repondre, avec les noms d'hier. Ici le
recensement est DERIVE de `data/symbols/<build>/ghidra/functions.tsv` : l'appariement se fait par le
nom de classe `<AbilityName>Ability`, et un id dont le symbole disparait le DIT.

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
ETAGE_BLOQUANT = {
    ActiveAbilityType.TheQuickening: "tuiles de mouvement du caster",
    ActiveAbilityType.VigilanceEternal: "tuiles de mouvement du caster",
    ActiveAbilityType.LeadingTheCharge: "tuiles de mouvement du caster",
    ActiveAbilityType.AlphaWarrior: "trigger DSL (IsInTeamSynapseRange)",
    ActiveAbilityType.EntropyCannons: "trigger DSL (ContagionsOfNurgleAura + HasNegativeModifier)",
    ActiveAbilityType.SquigLaunchas: "trigger DSL (HasMinimumAdjacent{Orks,FriendlyUnits})",
    ActiveAbilityType.ExcruciatingFrequencies: "selecteur DSL (GetAttackTargets)",
    ActiveAbilityType.SendInTheNextWave: "selecteur DSL (GetSurroundingTiles + GetUnitMaxRange)",
    ActiveAbilityType.HeroicFusillade: "pathfinding (MovementQuery$$IsInMovementRange)",
    ActiveAbilityType.SkyStrike: "battleQuery (DidMove + AreEntitiesAdjacent + GetAdjacentTiles)",
    ActiveAbilityType.CultDemagogue: "battleQuery (trois slots + GetStringConstant)",
    ActiveAbilityType.ExemplarOfTheKauyon: "battleQuery (IsFreeTile + GetAdjacentUnits)",
    ActiveAbilityType.MV71SniperDroneSquadAttack: "methodes de sa classe (IsMeleeAttack + PickTile)",
    ActiveAbilityType.AttemptedPossession: "SIMULATION d'effet (GetChildren + SimulateEffects)",
    ActiveAbilityType.MindControl: "ILLISIBLE -- predicat statique a corps DEDUPLIQUE",
    # ⚠ `DeathOnTheWind` EST SORTIE D'ICI (#287-r11, 2026-08-15) -- et son etage declare etait une
    # PREMISSE PERIMEE, pas un blocage. La ligne disait « SEEDING absent, pas l'etage » ; RE-MESURE :
    # `frida/hooks/features/ai-step/rpc-snapshot.ts` publie `actorStats.attacksReceivedThisTurn`
    # (`ActorStatisticsComponent+0x38`) et `snapshot.py` le seede dans
    # `UnitComponent.times_attacked_this_turn` depuis #287-r5-r2. Le capteur que la fiche reclamait
    # etait DEJA POSE ; il ne restait que le mirror, desormais dans
    # `abilities/darkangels.DeathOnTheWindAbility.get_dynamic_invalid_target_reason`.
    # La garder ici ferait rougir le CLIQUET a l'envers : une entree d'etage pour une regle PORTEE
    # ne serait plus dans `dette`, donc jamais imprimee -- une declaration muette et fausse.
}


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
    for etage, noms in sorted(par_etage.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print("  %-2d  %-62s %s" % (len(noms), etage, ",".join(sorted(noms))))

    # CLIQUET D'APPARIEMENT : la table d'etages et la table de symboles doivent rester en phase.
    orphelins = [nom for aid, nom, _s in res["dette"] if aid not in ETAGE_BLOQUANT]
    fantomes = [ActiveAbilityType(aid).name for aid in ETAGE_BLOQUANT
                if ActiveAbilityType(aid).name + "Ability" not in symboles_natifs(build)]
    print("[287-r5] CLIQUET")
    print("  ids a surcharge native SANS etage recense (le recensement se tait) : %d %s"
          % (len(orphelins), ",".join(orphelins) or ""))
    print("  entrees d'ETAGE_BLOQUANT sans symbole natif (renomme/disparu)      : %d %s"
          % (len(fantomes), ",".join(fantomes) or ""))

    if a.ids:
        print("[287-r5] DETAIL")
        for cle in ("portee", "table", "dette", "base"):
            for aid, nom, symbole in res[cle]:
                print("  %-6d %-30s %-8s %s" % (aid, nom, cle, symbole or "-"))

    ok = bool(aucune or res["portee"]) and not orphelins and not fantomes
    print("[287-r5] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
