"""#287-r9 -- QUI mesure a travers un oracle `abilityReason` COURT-CIRCUITE, et qui n'y est pas.

CE QUE CE PROBE RECENSE, et pourquoi il existe. #287-r6 a etabli que le RPC `abilityReason`
appelle `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui place DEUX etages AVANT
la cascade de ciblage. Quand l'un d'eux mord, l'oracle rend `TargetingRule.ValidRequest` pour TOUTE
cible et ne dit plus rien du ciblage. Le foyer du cran est `oracle_targeting`. Au moment ou #287-r6
a ete livre, UN SEUL consommateur le consultait. Ce probe repond a la question binaire :

    « Parmi les consommateurs qui ne consultent pas le cran, lesquels mesurent REELLEMENT a
      travers un oracle court-circuite ? »

TROIS ETATS, jamais deux -- et le troisieme est un RESULTAT, pas un aveu :

    SAIN                 aucun des ids qu'il exerce ne peut court-circuiter, OU il debloque deja
                         (cran consulte, ou attente explicite du cooldown avant toute mesure).
    EXPOSE ET VERIFIE    l'expose est MESURE (casterReason == ValidRequest constate live).
    EXPOSE, NON VERIFIE  il exerce un id du gisement et ne debloque pas -- mais personne n'a
                         mesure. On le NOMME avec ce qui manque pour trancher.

⚠ LE GISEMENT NE SE LIT PAS DANS LE REGISTRE. `oracle_targeting.ids_a_cooldown_initial()` sans
argument ne visite qu'`ABILITY_CLASSES` (104 ids) : il rend 15. L'etage amont natif, lui, est
INDIFFERENT a notre registre Python -- il mord sur l'`ActiveAbilityType`, porte ou non. Balaye sur
l'enum COMPLET (260), le gisement est de 21 : SIX ids court-circuitent sans etre portes
(`ExemplarOfTheKauyon`, `BioMinefield`, `UnstoppableMomentumReworked`, `AetherStride`,
`InfernalCannon`, `TitanhammerSquad`). Un recenseur ne peut pas rendre zero sur ce qu'il ne visite
pas : ce module derive donc TOUJOURS le gisement de l'enum, et IMPRIME sa portee.

CE QUE LE CLIQUET GARDE (il ne peut pas exiger zero -- la dette est nommee, pas soldee) :

  A. AUCUN consommateur EXPOSE ne doit apparaitre hors du registre `DETTE` ci-dessous. C'est le
     cran anti-cadence : notre propre portage rouvre ce gisement a chaque probe neuf qui exerce
     un des 21 ids sans debloquer -- meme forme que `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE`.
  B. AUCUN consommateur declare `REPARE` ne doit cesser de consulter le foyer. Un fichier qui
     recopierait le predicat au lieu d'appeler `oracle_targeting` rendrait le cran inerte sans
     que rien ne rougisse (meme vice que la garde structurelle `G.O is O` de #287-r6).
  C. Le gisement doit rester NON VIDE et la mesure COMPLETE : un enum vide ou un corpus vide
     rendrait un vert qui ne mesure rien.

Usage (100 % offline, aucun runner) :
    python scripts/python/probe_287r9_consommateurs_oracle.py
    python scripts/python/probe_287r9_consommateurs_oracle.py --tout      # y compris les SAINS
    python scripts/python/probe_287r9_consommateurs_oracle.py --json
ASCII only ; exit 0 = les trois crans passent.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig                                                          # noqa: E402
import oracle_targeting as O                                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402

# Le nom du RPC dont on recense les consommateurs. Ecrit ici UNE fois : c'est la cle du corpus.
RPC = "abilityReason"

# Le foyer du cran. Un consommateur « crante » l'IMPORTE -- recopier le predicat ne compte pas
# (c'est exactement ce que le cran C interdit).
FOYER = "oracle_targeting"

# Les fonctions du foyer qui, appelees, valent consultation du cran.
FOYER_APPELS = ("oracle_court_circuite", "rendre_oracle_passant", "debloquer_oracle",
                "cycler_sans_ia", "cause_du_court_circuit", "ids_a_cooldown_initial",
                "cooldown_initial")

# Les ids d'`ActiveAbilityType` reconnaissables a l'etat de LITTERAL NU. Sert a distinguer « le
# fichier FIXE son ability, et elle est hors gisement » (SAIN demontre) de « il ne la fixe pas »
# (indeterminable offline) : sans cette distinction, les deux sortaient sous le meme `ids=-`.
#
# ⚠ CE FILTRE ECARTE 12 MEMBRES, ET IL FAUT LE DIRE : l'enum porte 0, 3, 4, 8, 9, 12, 13, 17, 18,
# 28, 69 et 9999. Ces valeurs sont des entiers ORDINAIRES partout ailleurs (un index, un compte, un
# timeout) : les compter ferait declarer « ability fixee » a peu pres tout fichier, donc SAIN a peu
# pres tout consommateur -- exactement le faux vert qu'on corrige. Aucun n'est dans le gisement
# (1025..1232), donc l'ecart ne peut pas MASQUER un expose : au pire il range un fichier en
# INDETERMINE au lieu de SAIN, ce qui est le sens prudent. Un `ActiveAbilityType.<X>` NOMME, lui,
# compte quelle que soit sa valeur -- c'est le nom qui leve l'ambiguite, pas l'ordinal.
SEUIL_LITTERAL_NU = 1000
TOUS_IDS = frozenset(int(m) for m in ActiveAbilityType if int(m) >= SEUIL_LITTERAL_NU
                     and int(m) != 9999)
IDS_ECARTES = sorted(int(m) for m in ActiveAbilityType if int(m) not in TOUS_IDS)

# ------------------------------------------------------------------------------------------------
# LE REGISTRE DE DETTE. Chaque consommateur EXPOSE y porte son ETAT, mesure par #287-r9.
# Il ne peut que DECROITRE : un expose absent d'ici fait rougir le cran A.
#
#   "REPARE"       -- il consulte le foyer et debloque. Le cran B verifie qu'il continue.
#   "SAIN_MESURE"  -- expose par ses ids, mais il DEBLOQUE deja par une voie propre (attente
#                     explicite du cooldown), verifiee A LA MAIN et citee dans `pourquoi`.
#   "SAIN_LU"      -- le recenseur STATIQUE le croit expose, la LECTURE du site montre que l'id du
#                     gisement n'atteint jamais l'oracle (il est dans une liste DOCUMENTAIRE, pas
#                     dans celle qui est confrontee). C'est une limite ASSUMEE du recensement par
#                     litteraux : il voit ce qui est ECRIT, pas ce qui est PASSE au RPC.
#   "NON_VERIFIE"  -- expose, ne debloque pas ; personne n'a mesure. `pourquoi` dit ce qui manque.
# ------------------------------------------------------------------------------------------------
DETTE = {
    # ---- REPARES par #287-r9 (le cran pose, contre-epreuve live dans le rapport) ----------------
    "probe_91_duty_eternal.py": (
        "REPARE",
        "1158/1159 sur la MoW `ultraDreadnought`. MESURE : au tour 1, casterReason=ValidRequest, "
        "cooldown=2. La boucle d'attente n'avait PAS de `else` -- elle pouvait expirer et la "
        "mesure partait quand meme. `for/else` + `debloquer_oracle` desormais."),
    "probe_589r1r1r1_empyric_ambush_pose_live.py": (
        "REPARE",
        "1232 sur `eldarLhykhis`. MESURE : au tour 1, casterReason=ValidRequest, cooldown=1 ; 0 un "
        "tour plus tard. `face_decision` lisait `targetReason` sans le discriminant -- sur les "
        "ENNEMIS (le bras qui compte) la branche « permissif » avalait le 0x1 : vert vide."),
    "probe_targeting_masks_lot4.py": (
        "REPARE",
        "1200/1201. `_wait_castable` IMPRIMAIT son echec puis rendait la main, et le verdict final "
        "ignorait `n_skip` : les lignes court-circuitees etaient ecartees en silence. Le compteur "
        "`n_bloque` les fait ROUGIR, et le discriminant est `casterReason`, pas `targetReason`."),
    "probe_115_targeting_masks.py": (
        "REPARE",
        "1150 PlasmaCannon (cd initial 1). `casterReason` etait deja LU (`natc`) et seulement "
        "IMPRIME : aucune ligne de verdict ne le consultait."),
    "test_targeting_masks_live.py": (
        "REPARE",
        "1150. `_advance` COMPTAIT 6 `endturn` sans rien verifier -- et compter n'est pas mesurer "
        "(1143/1158 demandent deux tours ; une MoW sans munitions n'est JAMAIS debloquee par des "
        "tours). Le cran lit `casterReason` une fois par ability, avant les cibles."),

    # ---- SAINS etablis par LECTURE, la ou le recenseur statique se trompe -----------------------
    "test_targeting_options_masks_live.py": (
        "SAIN_LU",
        "1200/1201 sont dans `LOT` (liste DOCUMENTAIRE des 13 abilities de la tranche) mais PAS "
        "dans `POOL_CASES`, la seule liste passee a `abilityReason` : les 5 cas confrontes (1009, "
        "1006, 1179, 1180, 1202) sont tous hors gisement. RESIDU tout de meme : son "
        "`if nt == 0x1: continue` ecarte en silence, sans lire `casterReason` -- inoffensif "
        "aujourd'hui, faux vert des qu'un id du gisement entrera dans `POOL_CASES`."),

    # ---- EXPOSES, NON VERIFIES -- ce qui manque est NOMME, pas suppose ---------------------------
    "probe_249_deathguard_targeting.py": (
        "NON_VERIFIE",
        "1169 PlagueburstMortar (cd initial 1) sur la MoW `deathCrawler` -- donc DEUX termes amont "
        "possibles (cooldown ET munitions). Manque : une mesure de `casterReason` sur ce montage "
        "(`probe_287r9_expose_mesure_live.py --ability 1169 --mow deathCrawler`)."),
    "probe_250_blacklegion_targeting.py": (
        "NON_VERIFIE",
        "1148 DaemonicOrdnance (cd initial 1). Manque : la meme mesure sur son porteur."),
    "probe_253_astramilitarum_targeting.py": (
        "NON_VERIFIE",
        "1142 MalleusRocketLauncher (cd 1) et 1143 ForwardSpotter (cd 2 -- le plus long du "
        "gisement avec 1158). Manque : la meme mesure, et un deblocage a DEUX tours."),
    "probe_447_add_caster_dynamic_rule.py": (
        "NON_VERIFIE",
        "1115 FearOfTheUnseen (cd initial 1). Manque : la meme mesure."),
    "probe_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason.py": (
        "NON_VERIFIE",
        "ITERE `ABILITY_CLASSES`, donc il balaye les 15 ids du gisement presents au registre. "
        "Manque : savoir lesquels ses porteurs portent reellement -- indeterminable offline."),
    "probe_444_obscured_targeting.py": (
        "NON_VERIFIE",
        "ITERE `ABILITY_CLASSES`. Meme angle mort. ⚠ Ce probe est de plus le seul a exercer la "
        "LIGNE DE VUE : `InFogOfWarBrokenTargetingRule` n'est PAS decodee par le hook et sortirait "
        "en `hex: \"0x0\"` (« cible valide ») pour un REFUS -- distinct du court-circuit amont."),
    "test_ability_target_gate_live.py": (
        "NON_VERIFIE",
        "ITERE `ABILITY_CLASSES`. Meme angle mort."),
}


def gisement() -> dict:
    """Les `ActiveAbilityType` dont l'oracle court-circuite AU TOUR 1, derives de l'enum COMPLET.

    ⚠ PAS `ids_a_cooldown_initial()` sans argument : celui-la ne visite qu'`ABILITY_CLASSES` et
    rend 15 la ou l'enum en porte 21. L'etage amont natif ne connait pas notre registre."""
    return O.ids_a_cooldown_initial(sorted(set(int(m) for m in ActiveAbilityType)))


def _parents(arbre):
    """{noeud enfant -> noeud parent} -- le role d'une constante se DERIVE de son parent."""
    out = {}
    for n in ast.walk(arbre):
        for enfant in ast.iter_child_nodes(n):
            out[enfant] = n
    return out


def _nom_appele(noeud) -> str:
    f = noeud.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# Ce qui, dans le `else` d'une boucle d'attente, SIGNALE que le deblocage a echoue au lieu de
# laisser la mesure partir quand meme.
SORTIES_TERMINALES = ("fail", "skip", "exit", "SystemExit")


def _est_terminal(corps) -> bool:
    """Ce bloc INTERROMPT-il ? (`raise`, `return`, `pytest.fail`, `pytest.skip`, `sys.exit`)"""
    for n in ast.walk(ast.Module(body=list(corps), type_ignores=[])):
        if isinstance(n, (ast.Raise, ast.Return)):
            return True
        if isinstance(n, ast.Call) and _nom_appele(n) in SORTIES_TERMINALES:
            return True
    return False


def _deblocage(arbre) -> tuple:
    """(debloque, garde) -- la BOUCLE D'ATTENTE et son filet.

    UNE BOUCLE D'ATTENTE est un `for`/`while` qui contient un `endturn` : c'est la seule voie pour
    faire retomber un `initialCooldownTurns`. Elle est GARDEE si son echec est SIGNALE -- soit par
    le `else` de la boucle (`for ... else: pytest.fail(...)`), soit par un `assert`/`raise`/`return`
    qui la SUIT immediatement.

    ⚠ C'EST TOUTE LA DIFFERENCE MESUREE ENTRE `test_multihex_dutyeternal_live` ET
    `probe_91_duty_eternal` : boucle d'attente IDENTIQUE sur 1158, `for ... else: pytest.fail` d'un
    cote, RIEN de l'autre. Une boucle non gardee qui expire laisse la mesure partir a travers un
    oracle court-circuite, sans un mot. Ce n'est donc pas « il debloque » qui vaut cran, c'est
    « il debloque ET il rougit quand le deblocage n'a pas eu lieu »."""
    debloque = garde = False
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.For, ast.While)):
            continue
        corps = ast.Module(body=list(n.body), type_ignores=[])
        if not any(isinstance(c, ast.Constant) and c.value == "endturn"
                   for c in ast.walk(corps)):
            continue
        debloque = True
        if n.orelse and _est_terminal(n.orelse):
            garde = True
            continue
        # Pas de `else` : un `assert`/`raise`/`return` dans les lignes qui SUIVENT immediatement
        # la boucle tient le meme role (`assert window, "fenetre jamais ouverte"`).
        fin = getattr(n, "end_lineno", None)
        if fin is None:
            continue
        for m in ast.walk(arbre):
            if isinstance(m, (ast.Assert, ast.Raise)) and fin < getattr(m, "lineno", 0) <= fin + 12:
                garde = True
                break
    return debloque, garde


def analyser(chemin: Path, gis: dict) -> dict:
    """Ce qu'on peut dire d'un fichier SANS l'executer. Toute deduction porte sa VOIE."""
    src = chemin.read_text(encoding="utf-8", errors="replace")
    try:
        arbre = ast.parse(src)
    except SyntaxError as exc:
        return {"fichier": chemin.name, "erreur": "SyntaxError: %s" % exc}
    par = _parents(arbre)

    appelle = False          # "abilityReason" en ARGUMENT d'un appel -> vrai consommateur du RPC
    mentionne = False        # la chaine existe, mais ailleurs (docstring, commentaire porte, cle)
    lit_caster = False
    consulte_foyer = False
    importe_foyer = False
    balaye_registre = False
    balaye_dynamique = False
    caste = False            # le fichier CASTE une ability -> regime R2 (cooldown ACQUIS)
    ids = {}                 # id du GISEMENT -> voie d'attribution
    fixes = set()            # TOUS les ids d'ability FIXES statiquement, gisement ou non

    noms_gis = {gameconfig.ability_name(i): i for i in gis if gameconfig.ability_name(i)}

    for n in ast.walk(arbre):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if n.value == RPC:
                # Le ROLE se derive du parent : argument d'appel (direct ou via une structure
                # passee en argument) = consommateur ; tout le reste = simple mention.
                p = par.get(n)
                while isinstance(p, (ast.List, ast.Tuple, ast.Dict, ast.keyword)):
                    p = par.get(p)
                if isinstance(p, ast.Call):
                    appelle = True
                else:
                    mentionne = True
            elif n.value == "casterReason":
                lit_caster = True
            elif n.value in noms_gis:
                ids.setdefault(noms_gis[n.value], "nom gameconfig")
            elif n.value == "abilities":
                balaye_dynamique = True
            elif n.value == "ability":
                # `{"kind": "ability", ...}` d'`applyAction`, ou `act ability` de `rl_duel` : le
                # fichier CONSOMME l'ability -> tout `abilityReason` pris APRES est court-circuite
                # par l'USAGE, quel que soit le cooldown INITIAL. C'est le regime R2 (acquis),
                # celui que `probe_287r5_forward_observers_live` a rencontre en vrai.
                p = par.get(n)
                if isinstance(p, ast.Dict):
                    cles = [k.value for k in p.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    caste = caste or "kind" in cles
                elif isinstance(p, ast.List):
                    caste = True                       # `["act", "ability", ...]` de `rl_duel`
        elif isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value in TOUS_IDS:
            p = par.get(n)
            role = type(p).__name__ if p is not None else "?"
            fixes.add(n.value)
            if n.value in gis:
                ids.setdefault(n.value, "litteral entier (%s)" % role)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                and n.value.id == "ActiveAbilityType":
            aid = ActiveAbilityType.__members__.get(n.attr)
            if aid is not None:
                fixes.add(int(aid))
                if int(aid) in gis:
                    ids.setdefault(int(aid), "ActiveAbilityType.%s" % n.attr)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            mod = getattr(n, "module", None) or ""
            noms = [al.name for al in n.names]
            if mod == FOYER or FOYER in noms or mod.endswith("." + FOYER):
                importe_foyer = True
        elif isinstance(n, ast.Name) and n.id == "ABILITY_CLASSES":
            # ⚠ IMPORTER le registre ne prouve RIEN : la voie de LOIN la plus frequente est le
            # LOOKUP `ABILITY_CLASSES[<un id>]()`, qui n'exerce QUE cet id. Seule une ITERATION
            # (`for k in ...`, `sorted(...)`, `.items()`, une comprehension) exerce les 104.
            # Confondre les deux marquait 22 fichiers « exposes » qui ne le sont pas.
            p = par.get(n)
            if isinstance(p, ast.Subscript):
                continue
            if isinstance(p, ast.Attribute) and p.attr not in ("items", "keys", "values"):
                continue
            balaye_registre = True
        elif isinstance(n, ast.Call):
            if _nom_appele(n) in FOYER_APPELS:
                consulte_foyer = True

    # LA PARTITION EST EXHAUSTIVE, et c'est ce qui la rend utilisable : tout consommateur tombe
    # dans exactement une case, aucune n'est un fourre-tout.
    #   REGISTRE  -- il ITERE le registre : il exerce donc les 104, gisement compris.
    #   GISEMENT  -- au moins un id du gisement, FIXE au source.
    #   HORS      -- des ids FIXES, aucun dans le gisement. C'est un SAIN DEMONTRE.
    #   DYNAMIQUE -- aucun id fixe : ils viennent du runner (`decisionView[].abilities`) ou de la
    #                ligne de commande. Indeterminable OFFLINE -> jamais rabattu sur SAIN.
    debloque, garde = _deblocage(arbre)
    if balaye_registre:
        portee = "REGISTRE" + ("+GISEMENT" if ids else "")
    elif ids:
        portee = "GISEMENT"
    elif fixes:
        portee = "HORS GISEMENT"
    else:
        portee = "DYNAMIQUE"
    return {
        "fichier": chemin.name,
        "chemin": str(chemin.relative_to(HERE.parents[1])).replace("\\", "/"),
        "appelle": appelle,
        "mentionne_seulement": mentionne and not appelle,
        "cran": bool(importe_foyer and consulte_foyer),
        "importe_foyer": importe_foyer,
        "caster_reason": lit_caster,
        "portee": portee,
        "caste": caste,
        "debloque": debloque,
        "garde": garde,
        "ids_fixes": sorted(fixes),
        "ids_exposes": {i: v for i, v in sorted(ids.items())},
    }


def corpus() -> list:
    """Tous les .py de `scripts/python` (probes, tests, moteur) -- le foyer lui-meme EXCLU.

    On ne filtre PAS par prefixe `probe_`/`test_` : un module moteur qui appellerait le RPC serait
    un consommateur au meme titre, et une liste blanche de prefixes ne peut pas montrer le fichier
    qu'elle a oublie."""
    racine = HERE
    return sorted(p for p in racine.rglob("*.py")
                  if p.name != Path(__file__).name and p.name != FOYER + ".py")


def etat_de(row: dict) -> str:
    """Les TROIS etats -- jamais deux. `SAIN` n'est pas un defaut : c'est un RESULTAT.

    ⚠ `DYNAMIQUE` n'est PAS `SAIN` : ne pas lire l'id au source ne prouve pas qu'il est hors
    gisement. Le rabattre sur un vert serait exactement le zero-de-methode qu'on corrige."""
    if row["cran"]:
        return "REPARE"
    declare = DETTE.get(row["fichier"])
    if declare is not None:
        return declare[0]
    if row["portee"] == "HORS GISEMENT":
        return "SAIN"
    if row["debloque"] and row["garde"]:
        # Il ne consulte pas le foyer, mais il DEBLOQUE et son deblocage rougit s'il echoue :
        # l'oracle est passant quand il mesure. C'est un SAIN, par une autre voie.
        return "SAIN_MESURE"
    if row["portee"] == "DYNAMIQUE":
        return "INDETERMINE"
    return "EXPOSE_NON_DECLARE"


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r9 : recensement des consommateurs d'oracle")
    ap.add_argument("--tout", action="store_true", help="imprimer aussi les SAINS")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    gis = gisement()
    fichiers = corpus()
    rows = [analyser(p, gis) for p in fichiers]
    erreurs = [r for r in rows if r.get("erreur")]
    conso = [r for r in rows if r.get("appelle")]
    mentions = [r for r in rows if r.get("mentionne_seulement")]

    for r in conso:
        r["etat"] = etat_de(r)

    if a.json:
        print(json.dumps({"gisement": gis, "consommateurs": conso}, indent=1))
        return 0

    print("[287r9] PORTEE DE LA MESURE")
    print("  corpus                  : %d fichiers .py sous scripts/python (foyer exclu)"
          % len(fichiers))
    print("  gisement (enum COMPLET) : %d ids sur %d membres d'ActiveAbilityType"
          % (len(gis), len(list(ActiveAbilityType))))
    print("  gisement (registre seul): %d ids -- ce que rend `ids_a_cooldown_initial()` sans "
          "argument" % len(O.ids_a_cooldown_initial()))
    print("  NON VU par ce probe     : les ids exerces DYNAMIQUEMENT (lus dans `decisionView`), "
          "les .ts et les .md")
    print("  ECARTES DU LITTERAL NU  : %s -- ambigus a l'etat d'entier nu (aucun dans le gisement, "
          "donc aucun expose masque)" % (IDS_ECARTES,))
    if erreurs:
        print("  NON ANALYSES (SyntaxError) : %d" % len(erreurs))
        for r in erreurs:
            print("     %s : %s" % (r["fichier"], r["erreur"]))

    print("[287r9] CONSOMMATEURS du RPC `%s` : %d (appel) + %d (mention seule) = %d citations"
          % (RPC, len(conso), len(mentions), len(conso) + len(mentions)))
    par_etat = {}
    for r in conso:
        par_etat.setdefault(r["etat"], []).append(r)
    ordre = ("EXPOSE_NON_DECLARE", "NON_VERIFIE", "INDETERMINE", "SAIN_MESURE", "SAIN_LU",
             "REPARE", "SAIN")
    assert set(par_etat) <= set(ordre), "etat non imprime : %s" % (set(par_etat) - set(ordre))
    for etat in ordre:
        lot = par_etat.get(etat, [])
        print("  %-20s : %d" % (etat, len(lot)))
        if etat in ("SAIN", "INDETERMINE") and not a.tout:
            continue
        for r in sorted(lot, key=lambda x: x["fichier"]):
            ids = ", ".join("%d(%s)" % (i, v) for i, v in r["ids_exposes"].items()) or "-"
            print("     %-58s cran=%-5s caster=%-5s debloque=%-5s garde=%-5s portee=%-18s ids=%s"
                  % (r["fichier"], r["cran"], r["caster_reason"], r["debloque"], r["garde"],
                     r["portee"], ids))
            decl = DETTE.get(r["fichier"])
            if decl:
                print("        %s" % decl[1])

    # ------------------------------------------------------------------ les trois crans
    non_declares = par_etat.get("EXPOSE_NON_DECLARE", [])
    regressions = [f for f, (etat, _) in DETTE.items() if etat == "REPARE"
                   and not any(r["fichier"] == f and r["cran"] for r in conso)]
    complet = bool(gis) and bool(conso) and not erreurs

    print("[287r9] CRAN A (aucun expose hors du registre de dette) : %s"
          % ("OK" if not non_declares else "FAUTE (%d)" % len(non_declares)))
    for r in non_declares:
        print("     %s exerce %s sans debloquer -- l'inscrire au registre avec son ETAT"
              % (r["fichier"], sorted(r["ids_exposes"])))
    print("[287r9] CRAN B (les REPARES consultent toujours le foyer) : %s"
          % ("OK" if not regressions else "FAUTE : %s" % regressions))
    print("[287r9] CRAN C (gisement et corpus non vides, 0 fichier illisible) : %s"
          % ("OK" if complet else "FAUTE"))
    ok = not non_declares and not regressions and complet
    print("[287r9] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
