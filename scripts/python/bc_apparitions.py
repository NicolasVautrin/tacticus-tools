"""RECENSER TOUT CE QUI PEUT APPARAITRE dans une bataille, depuis sa `BattleConfiguration`.

    python scripts/python/bc_apparitions.py --bc logs/sandbox-bc-waves-<ts>.json
    python scripts/python/bc_apparitions.py --bc <f> --cibles          # a coller dans --enhancement
    python scripts/python/bc_apparitions.py --bc <f> --camp 12         # un seul camp

POURQUOI CET OUTIL EXISTE
-------------------------
Viser une unite par `--enhancement` exige la chaine EXACTE (`tyranNpc3Termagant:6`, pas
`tyranNpc3Termagant`) : le natif apparie par `UnitConfigId$$op_Equality`, qui confronte PureId,
Rarity, Level ET IsBorrowed. Une cible approximative n'apparie RIEN, sans lever, et l'installation
se declare quand meme `ok`. Il faut donc pouvoir LIRE ce qui va apparaitre, pas le deviner.

TROIS GISEMENTS, ET LE TROISIEME N'EST DANS AUCUNE LISTE DE SPAWN
-----------------------------------------------------------------
  1. `PredefinedUnits[].Units[]`                      -- pose au depart, par playerId
  2. `UnitSpawningOverTime.Tiers[<round>][<player>]`  -- les VAGUES, programmees
  3. les SUMMONS                                       -- declares dans les `Constants` d'une
     ability, donc atteignables seulement par FERMETURE TRANSITIVE depuis 1 et 2

⚠ LES CLES DE SUMMON SONT HETEROGENES, ET UNE LISTE BLANCHE RATERAIT CELLE QU'ELLE A OUBLIEE.
Mesure du 2026-08-23 sur le seed BC : `unitId`, `unitId_2`, `unitId_3`, `unitId_4`, `unitIds`,
`summonId`, `unitToSpawn` -- sept orthographes pour une notion. On ne les enumere donc PAS : on
retient toute constante dont la VALEUR est un id du catalogue `BC.Units`, et les cles trouvees
sont un RESULTAT imprime, pas une entree. Une huitieme orthographe apparaitra toute seule.

⚠⚠ MAIS << LA VALEUR EST UN ID >> NE PROUVE PAS << CA L'INVOQUE >>, ET C'EST MESURE.
`HailOfLivingAmmunition` porte `{extraHit: 1, unitIds: "tyranNpc3Termagant,tyranSmnTermagant,
GuildBoss1Npc1...,GuildBoss1Npc2...,GuildBoss1Npc3..."}` : c'est une LISTE BLANCHE d'unites
auxquelles le passif s'applique, pas un spawn. La premiere version de cet outil l'a classe summon
et a annonce un `tyranSmnTermagant` qui n'apparait jamais. Le discriminant retenu, DERIVE et non
suppose : le SINGULIER (`unitId`, `unitId_N`, `summonId`, `unitToSpawn`) designe une cible de
spawn ; le PLURIEL (`unitIds`) enumere un filtre -- 2 cas sur 2 dans le seed BC
(`HungeringSwarm`, `HailOfLivingAmmunition`), tous deux des filtres.

⚠ ET `nrOfSummons` N'EST PAS LE MARQUEUR -- piste ESSAYEE puis REFUTEE. `ScarabHive`,
`Poxwalkers`, `ResurrectionOrb`, `MightFromBelow` invoquent toutes SANS lui. S'en servir comme
critere raterait la majorite des summons. Il n'est garde que comme SIGNAL corroborant, affiche.

⇒ CE QUE CET OUTIL NE TRANCHE PAS. La BC ne distingue pas structurellement un spawn d'un filtre :
seul l'arbre DSL de l'ability le fait (`SpawnUnitBehaviour` au decompile). Les summons sortent
donc en CANDIDATS. Pour ce a quoi ils servent -- nommer des cibles -- sur-inclure est sans
consequence (une cible qui n'apparait pas n'apparie rien) ; sous-inclure, si.

⚠ L'ECART SE DIT AUSSI. Une valeur qui ressemble a un id mais qu'aucune entree de `BC.Units` ne
porte sort en `SUSPECTS` : soit une autre semantique (`damageProfile: "Flame"`), soit un summon
dont la `UnitConfiguration` MANQUE -- auquel cas il ne peut pas apparaitre. Jamais jetee en
silence. L'appariement retombe sur le `PureId` quand la cle exacte manque, parce que les listes
nomment `tyranNpc3Termagant` la ou le catalogue tient `tyranNpc3Termagant:1` et `:6`.

⚠ UN ORDINAL D'ABILITY NE DIT PAS SON ENUM. `BC.Units[].ActiveAbilities` porte des ordinaux
d'`ActiveAbilityType`, `PassiveAbilities`/`TertiaryAbility` des ordinaux de `TriggeredAbilityType`,
et les deux tables PARTAGENT des ordinaux en nommant autre chose. Le nom resolu est donc RECOUPE
contre les cles des configs de la BC : s'il n'y figure pas, la ligne sort en `NON RESOLU` au lieu
d'etre lue de travers.

⚠ `BC.Units[].ConfigId` PORTE DEJA LA STRUCT RESOLUE. On ne re-parse pas le `Id` : le champ est
exactement ce que `Targets[].Target` attend. Il corrobore le mirror de
`IdunBattle.Configuration.UnitConfigId$$CreateFromString` cote hook, par une source independante.

Sorties ASCII uniquement (console Windows cp1252).
"""
import argparse
import io
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENUM_ACTIF = "IdunBattle.Entities.Enum.ActiveAbilityType"
ENUM_DECLENCHE = "IdunBattle.Entities.Enum.TriggeredAbilityType"


def charger_enums(build=None):
    """`{<nom d'enum>: {<ordinal>: <nom>}}`. `None` = PAS LU -- jamais un dict vide."""
    if build is None:
        p = os.path.join(RACINE, "data", "symbols", "CURRENT")
        if not os.path.exists(p):
            return None, "data/symbols/CURRENT absent"
        build = io.open(p, encoding="utf-8").read().strip()
    f = os.path.join(RACINE, "data", "symbols", build, "frida", "enums.tsv")
    if not os.path.exists(f):
        return None, "%s absent" % f
    out = {}
    for ligne in io.open(f, encoding="utf-8"):
        if ligne.startswith("#") or "\t" not in ligne:
            continue
        nom, _, paires = ligne.rstrip("\n").partition("\t")
        membres = {}
        for p in paires.split(","):
            o, sep, m = p.partition("=")
            if sep:
                try:
                    membres[int(o)] = m
                except ValueError:
                    pass
        out[nom] = membres
    return out, build


def configs_ability(bc):
    """`{<famille>: {<nom>: <config ou None>}}`, tel que la BC les porte."""
    ab = bc.get("Abilities") or {}
    return {k: (ab.get(k) or {}) for k in
            ("ActiveAbilities", "PassiveAbilities", "EnvironmentAbilities")}


def index_unites(bc):
    """`{<Id>: <entree>}` du catalogue `BC.Units`."""
    return {e["Id"]: e for e in (bc.get("Units") or []) if isinstance(e, dict) and e.get("Id")}


def graines(bc):
    """Ce qui est POSE ou PROGRAMME. Liste de `(categorie, playerId, unitId)`."""
    out = []
    for grp in (bc.get("PredefinedUnits") or []):
        pid = grp.get("Id")
        for u in (grp.get("Units") or []):
            uid = u.get("UnitId")
            if uid:
                out.append(("predefini", pid, uid))

    # ⚠ FORME MESUREE sur `data/seed-bc.json` (2026-08-23), pas devinee :
    #     PredefinedMachines: [{"Id": <playerId>, "MachineOfWar": {"UnitId": <id|null>}}]
    # Le premier jet lisait `m["Id"]` en repli et prenait donc le CAMP (un entier) pour une unite
    # -- il plantait au tri. Une extraction << defensive >> sur une forme non confrontee n'est pas
    # prudente : elle invente.
    for m in (bc.get("PredefinedMachines") or []):
        if not isinstance(m, dict):
            continue
        uid = ((m.get("MachineOfWar") or {}).get("UnitId")
               if isinstance(m.get("MachineOfWar"), dict) else None)
        if isinstance(uid, str) and uid:
            out.append(("machine", m.get("Id"), uid))

    # ⚠ `BossUnit` est NUL sur les deux bancs disponibles -- sa forme non nulle n'est PAS
    # confrontee. On n'accepte donc qu'une chaine, et un dict sort en `boss?` pour etre VU.
    b = bc.get("BossUnit")
    if isinstance(b, str) and b:
        out.append(("boss", None, b))
    elif isinstance(b, dict):
        uid = b.get("UnitId")
        if isinstance(uid, str) and uid:
            out.append(("boss?", b.get("PlayerId"), uid))

    tiers = ((bc.get("UnitSpawningOverTime") or {}).get("Tiers") or {})
    for rnd in sorted(tiers, key=lambda x: (len(str(x)), str(x))):
        parjoueur = tiers[rnd] or {}
        for pid, spec in (parjoueur.items() if isinstance(parjoueur, dict) else []):
            for s in ((spec or {}).get("ToSpawn") or []):
                uid = s.get("UnitId")
                if uid:
                    out.append(("vague r%s" % rnd, pid, uid))
    return out


def _est_pluriel(cle):
    """`unitIds` = un FILTRE, pas un spawn. Mesure 2/2 sur le seed BC (cf. l'en-tete)."""
    return cle.rstrip("_0123456789").endswith("Ids")


def summons_de(unite, cfgs, enums, catalogue, parpur):
    """Les unites qu'une entree de `BC.Units` peut FAIRE APPARAITRE.

    Rend `(candidats, filtres, suspects, non_resolus)` :
      candidats   : [(unitId, ability, cle, aNrOfSummons)]  -- cle SINGULIERE, valeur au catalogue
      filtres     : [(unitId, ability, cle)]                -- cle PLURIELLE : liste blanche
      suspects    : [(valeur, ability, cle)]                -- ressemble a un id, HORS catalogue
      non_resolus : [(ordinal, champ, motif)]               -- l'enum ou la config n'a pas repondu
    """
    trouves, filtres, suspects, non_res = [], [], [], []
    champs = (("ActiveAbilities", "ActiveAbilities", ENUM_ACTIF),
              ("PassiveAbilities", "PassiveAbilities", ENUM_DECLENCHE),
              ("TertiaryAbility", "PassiveAbilities", ENUM_DECLENCHE))
    for champ, famille, enom in champs:
        v = unite.get(champ)
        ordinaux = v if isinstance(v, list) else ([v] if isinstance(v, int) else [])
        for o in ordinaux:
            table = (enums or {}).get(enom)
            nom = table.get(o) if table else None
            if nom is None:
                non_res.append((o, champ, "ordinal absent de `%s`" % enom.rsplit(".", 1)[-1]))
                continue
            cfg = cfgs.get(famille, {}).get(nom)
            if cfg is None:
                # Le nom resolu n'est pas une cle des configs de CETTE BC : soit l'ability n'y est
                # pas embarquee, soit l'enum choisi est le mauvais. On ne tranche pas -- on le dit.
                non_res.append((o, champ, "`%s` absent de BC.Abilities.%s" % (nom, famille)))
                continue
            if not isinstance(cfg, dict):
                continue
            consts = cfg.get("Constants") or {}
            # SIGNAL corroborant seulement -- REFUTE comme critere (cf. l'en-tete).
            compte = any(k.startswith("nrOfSummons") for k in consts)
            for cle, val in consts.items():
                brut = val if isinstance(val, list) else str(val).split(",")
                for morceau in brut:
                    m = str(morceau).strip()
                    if not m or m.lstrip("+-").isdigit():
                        continue
                    # Les listes nomment le PureId nu la ou le catalogue tient des variantes.
                    cible = m if m in catalogue else None
                    if cible is None and m in parpur:
                        cible = m           # resolu par PureId ; les variantes sont dites au rendu
                    if cible is None:
                        if any(c.isalpha() for c in m) and m not in ("True", "False"):
                            suspects.append((m, nom, cle))
                    elif _est_pluriel(cle):
                        filtres.append((cible, nom, cle))
                    else:
                        trouves.append((cible, nom, cle, compte))
    return trouves, filtres, suspects, non_res


def fermeture(bc, enums):
    """GRAINES puis FERMETURE TRANSITIVE par les summons. Garde-fou de cycle."""
    catalogue = index_unites(bc)
    cfgs = configs_ability(bc)
    parpur = {}
    for k in catalogue:
        parpur.setdefault(k.split(":")[0], []).append(k)

    apparitions = {}      # unitId -> {"voies": set, "camps": set, "compte": int}
    for cat, pid, uid in graines(bc):
        e = apparitions.setdefault(uid, {"voies": set(), "camps": set(), "compte": 0})
        e["voies"].add(cat)
        if pid is not None:
            e["camps"].add(str(pid))
        e["compte"] += 1

    suspects, non_res, invoques, filtres = [], [], {}, []
    frontiere = list(apparitions)
    vus = set()
    while frontiere:
        uid = frontiere.pop()
        if uid in vus:
            continue
        vus.add(uid)
        u = catalogue.get(uid)
        if u is None:
            continue
        t, f, s, n = summons_de(u, cfgs, enums, catalogue, parpur)
        suspects.extend((val, uid, ab, cle) for val, ab, cle in s)
        filtres.extend((val, uid, ab, cle) for val, ab, cle in f)
        non_res.extend((o, uid, ch, motif) for o, ch, motif in n)
        for cible, ab, cle, compte in t:
            if cible == uid:
                continue
            invoques.setdefault(cible, []).append((uid, ab, cle, compte))
            e = apparitions.setdefault(cible, {"voies": set(), "camps": set(), "compte": 0})
            e["voies"].add("summon?")
            e["camps"].update(apparitions.get(uid, {}).get("camps", set()))
            frontiere.append(cible)
    return apparitions, invoques, filtres, suspects, non_res, catalogue, parpur


def cible_ecrite(uid, catalogue):
    """La chaine a passer a `--enhancement`, et la struct que le natif en fera."""
    e = catalogue.get(uid)
    cfg = (e or {}).get("ConfigId")
    return uid, cfg


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bc", required=True, help="la BattleConfiguration en JSON "
                                               "(ex. la sortie de `sandbox_mode.py bc`)")
    ap.add_argument("--camp", default=None, help="ne garder qu'un playerId (ex. 12 = l'ennemi)")
    ap.add_argument("--cibles", action="store_true",
                    help="n'imprimer que l'argument `--enhancement` pret a coller")
    ap.add_argument("--build", default=None, help="hash de build (defaut : data/symbols/CURRENT)")
    a = ap.parse_args()

    if not os.path.exists(a.bc):
        print("REFUS : `%s` introuvable." % a.bc)
        return 2
    bc = json.load(io.open(a.bc, encoding="utf-8"))
    enums, build = charger_enums(a.build)
    if enums is None:
        # TRI-ETAT : sans table, les summons ne sont PAS recensables. On refuse plutot que de
        # rendre << 0 summon >>, qui se lirait comme une absence.
        print("REFUS : table des enums NON LUE (%s). Les summons ne seraient pas recensables,"
              " et un zero se lirait comme une absence." % build)
        return 1

    apparitions, invoques, filtres, suspects, non_res, catalogue, parpur = fermeture(bc, enums)

    if a.camp:
        apparitions = {k: v for k, v in apparitions.items()
                       if a.camp in v["camps"] or (not v["camps"] and "summon" in v["voies"])}

    if a.cibles:
        print(",".join(sorted(apparitions)))
        return 0

    print("BC        : %s" % os.path.basename(a.bc))
    print("build     : %s   GameMode=%s" % (build, bc.get("GameMode")))
    print("catalogue : %d entrees dans BC.Units" % len(catalogue))
    print()
    print("APPARITIONS (%d unites distinctes ; `summon?` = CANDIDAT, cf. l'en-tete)"
          % len(apparitions))
    print("  %-30s %-30s %-6s %s" % ("unitId (a ECRIRE tel quel)", "voie", "camp", "ConfigId"))
    for uid in sorted(apparitions):
        v = apparitions[uid]
        uid_ecrit, cfg = cible_ecrite(uid, catalogue)
        if cfg is None:
            var = parpur.get(uid) or []
            rendu = ("(!) pas de cle exacte au catalogue ; variantes : %s" % ",".join(sorted(var))
                     if var else "(!) ABSENT du catalogue -- ne peut PAS apparaitre")
        else:
            bits = ["PureId=%s" % cfg.get("PureId")]
            for k in ("Rarity", "Level"):
                if cfg.get(k) is not None:
                    bits.append("%s=%s" % (k, cfg[k]))
            for k in ("IsBorrowed", "IsPvpOpponent"):
                if cfg.get(k):
                    bits.append(k)
            rendu = " ".join(bits)
        n = (" x%d" % v["compte"]) if v["compte"] > 1 else ""
        voies = ",".join(sorted(v["voies"])) + n
        if len(voies) > 30:
            voies = voies[:27] + "..."
        print("  %-30s %-30s %-6s %s" % (uid_ecrit, voies,
                                         ",".join(sorted(v["camps"])) or "-", rendu))

    if invoques:
        print()
        print("SUMMONS CANDIDATS -- qui pourrait les faire apparaitre")
        print("  La BC ne distingue pas un spawn d'un filtre : trancher se fait au DECOMPILE")
        print("  (`SpawnUnitBehaviour` dans l'arbre DSL de l'ability). `nrOfSummons` n'est qu'un")
        print("  SIGNAL -- il est absent de la majorite des summons reels.")
        for cible in sorted(invoques):
            for src, ab, cle, compte in invoques[cible]:
                print("  %-28s <- %-22s %s.%s%s"
                      % (cible, src, ab, cle, "   [nrOfSummons]" if compte else ""))

    if filtres:
        print()
        print("LISTES BLANCHES -- cle PLURIELLE : le passif s'APPLIQUE a ces unites, il ne les")
        print("  invoque PAS. Ecartees des apparitions (2/2 verifiees sur le seed BC).")
        vus = set()
        for val, porteur, ab, cle in filtres:
            k = (val, ab, cle)
            if k in vus:
                continue
            vus.add(k)
            print("  %-28s dans %-24s %s.%s" % (val, porteur, ab, cle))

    if suspects:
        print()
        print("SUSPECTS -- constante qui RESSEMBLE a un id mais ABSENTE de BC.Units (%d)"
              % len(suspects))
        print("  soit une AUTRE semantique, soit un summon SANS UnitConfiguration (il ne peut")
        print("  alors pas apparaitre). Non tranche ici -- lire la config de l'ability.")
        vus = set()
        for val, porteur, ab, cle in suspects:
            k = (val, ab, cle)
            if k in vus:
                continue
            vus.add(k)
            print("  %-28s porte par %-22s %s.%s" % (val, porteur, ab, cle))

    if non_res:
        print()
        print("NON RESOLUS -- ordinal ou nom d'ability sans reponse (%d)" % len(non_res))
        print("  Ces abilities N'ONT PAS ete inspectees : un summon peut s'y cacher.")
        vus = set()
        for o, porteur, champ, motif in non_res:
            k = (o, champ, motif)
            if k in vus:
                continue
            vus.add(k)
            print("  ordinal %-8s %-18s %-22s %s" % (o, champ, porteur, motif))

    print()
    print("A COLLER : --enhancement 'EnhancementDamageBoost=<ids separes par des virgules>'")
    print("           (`--cibles` imprime la liste seule ; `--camp 12` la restreint a l'ennemi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
