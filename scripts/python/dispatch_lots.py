"""Choisit N lots `engine/` dont les SURFACES DE FOYERS sont disjointes -- des agents en vol,
et entre elles.

    python scripts/python/dispatch_lots.py            # 3 lots, ancres DERIVEES de la flotte
    python scripts/python/dispatch_lots.py -n 5
    python scripts/python/dispatch_lots.py --ancre engine/runner/abilities/targeting.py

POURQUOI CE FICHIER EXISTE. Il a vecu trois sessions dans le scratchpad, ou il a fallu
REPARER LES MEMES TROIS BUGS a chaque fois -- le scratchpad est efface entre sessions, donc
chaque reparation mourait avec elle. Les trois sont ci-dessous, chacune avec la mesure qui
l'a etablie ; elles ne sont pas evidentes et elles rendent toutes un resultat FAUX MAIS
VRAISEMBLABLE, ce qui est le pire mode de panne pour un outil de dispatch.

LE CRITERE N'EST PAS << residus communs >> MAIS << FOYERS communs >>. Deux residus
differents qui editent le meme fichier collisionnent quand meme. Et la FAMILLE (`#287-r11`
vs `#287-r11-r2`) est le MAUVAIS axe : mesure du 2026-08-07, `#287` compte 10 residus sur
5 foyers disjoints, tandis que `probe_457_offline_tests_green.py` est le foyer de 3 residus
de familles DIFFERENTES. Le foyer TRAVERSE les familles.

Sortie ASCII uniquement (console Windows cp1252).
"""
import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "docs" / "rl" / "index-foyers.md"

# L'index a la MEME forme de tableau dans plusieurs sections. Avaler << Par BLOCAGE >> fait
# de `aucun` un faux foyer partage par ~300 residus, donc une surface interdite qui couvre
# tout et un outil qui ne propose plus rien.
SECTIONS_FOYER = ("## Points de COLLISION", "## Foyers ISOLES")


def git(*a, cwd=None):
    r = subprocess.run(["git", "-C", str(cwd or REPO)] + list(a),
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


# --------------------------------------------------------------- lecture de l'index
def lire_index():
    """`{foyer -> {residus}}`, lu UNIQUEMENT dans les sections de foyers."""
    if not INDEX.exists():
        sys.exit("index ABSENT : %s -- le regenerer par index_foyers.py" % INDEX)
    res_par_foyer = {}
    dans_foyers = False
    for L in INDEX.read_text(encoding="utf-8").splitlines():
        if L.startswith("## "):
            dans_foyers = any(L.startswith(s) for s in SECTIONS_FOYER)
            continue
        if not dans_foyers or not L.startswith("|"):
            continue
        cells = [x.strip() for x in L.strip("|").split("|")]
        if len(cells) < 3:
            continue
        foyer = cells[0].strip("`").strip()
        if not foyer or foyer == "foyer" or set(foyer) <= set("-: "):
            continue
        ids = [i.strip() for i in cells[-1].split(",") if i.strip().startswith("#")]
        if ids:
            res_par_foyer.setdefault(foyer, set()).update(ids)
    return res_par_foyer


# --------------------------------------------------- REPARATION 1 : foyers DEGENERES
def foyer_nomme(f: str) -> bool:
    """Un foyer n'est exploitable que s'il NOMME quelque chose.

    Mesure du 2026-08-15 : le lot le mieux classe par le glouton avait pour surface
    `['', 'scripts/python/']` -- des libelles de repertoire, voire la chaine vide. Il passait
    tous les filtres et sortait EN TETE. Dispatcher dessus, c'est promettre une disjonction
    qu'on n'a pas mesuree, puisque la surface ne designe aucun fichier.
    """
    return f.endswith(".py") or "**" in f


# ------------------------------------------------- REPARATION 2 : containment des GLOBS
def chevauche(a: str, b: str) -> bool:
    """Deux foyers se recouvrent-ils REELLEMENT ?

    ⚠ Surtout pas `set & set`. Un foyer GLOB (`runner/abilities/**`) CONTIENT des foyers
    concrets (`runner/abilities/behaviours/combat.py`) : comme chaines ils sont distincts,
    donc l'intersection est vide et le glouton les declare disjoints -- alors que deux
    agents editeraient le meme repertoire. Mesure du 2026-08-15 : deux lots sont sortis
    << disjoints >> dans exactement cette configuration.
    """
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith("**") and y.startswith(x[:-2]):
            return True
    return False


def se_croisent(s1, s2) -> bool:
    return any(chevauche(a, b) for a in s1 for b in s2)


# ------------------------------------------------ REPARATION 3 : appariement des ANCRES
def apparier(res_par_foyer, ancre: str):
    """Les foyers de l'index portent le chemin COMPLET (`scripts/python/engine/...`).

    Un appariement EXACT rend une surface VIDE, donc un filtre qui ne filtre rien -- et les
    agents en vol ressortent dans leur PROPRE liste de << lots libres >>. On apparie donc par
    suffixe.
    """
    return [f for f in res_par_foyer if f.endswith(ancre)]


def surface_de(res_par_foyer, foyers_du_residu, foyer):
    s = set()
    for i in res_par_foyer[foyer]:
        s |= foyers_du_residu[i]
    return s


# ------------------------------------------------------- ancres DERIVEES de la flotte
RE_ENGINE = re.compile(r"(scripts/python/(?:engine|tests)/\S+\.py)")
# Le BRIEF ecrit les foyers en chemin COURT (`entities/effects/loki/extra_damage_aura.py`,
# `runner/abilities/**`), sans le prefixe `scripts/python/`. On accepte donc les deux formes.
RE_BRIEF = re.compile(
    r"((?:scripts/python/)?(?:engine/)?"
    r"(?:entities|runner|playbook|services|utilities|dsl|ai)/[\w./]*"
    r"(?:\.py|\*\*))")


BUDGET_TETE_KO = 96


def brief_par_la_tete(FB, agent_id: str) -> str:
    """Le brief d'un agent, lu par le DEBUT de son transcript.

    ⚠ NE PAS prendre `row["brief"]` de `fleet_board`. Son lecteur est borne aux 64 DERNIERS
    Ko (`_lignes_bornees`), parce que tout ce qui decide de l'etat d'un agent est a la FIN --
    optimisation juste, et sa propre docstring previent que << `brief` peut manquer >>. Or le
    brief est le PREMIER message `user` : il tombe hors fenetre des que le transcript depasse
    le budget. Mesure du 2026-08-15 : `brief` valait 0 pour les 4 agents vifs, dont trois
    venaient d'etre lances -- le canal etait donc muet exactement quand il est indispensable.
    """
    sess = FB.session_de_l_agent(agent_id)
    if not sess:
        return ""
    p = FB.project_dir() / sess / "subagents" / ("agent-%s.jsonl" % agent_id)
    if not p.exists():
        return ""
    with p.open("rb") as fh:
        brut = fh.read(BUDGET_TETE_KO * 1024).decode("utf-8", errors="replace")
    import json as _json
    for ln in brut.split("\n"):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            o = _json.loads(ln)
        except Exception:
            continue          # derniere ligne tronquee par le budget : normal
        msg = o.get("message") or {}
        if msg.get("role") != "user":
            continue
        c = msg.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            t = "\n".join(b.get("text", "") for b in c
                          if isinstance(b, dict) and b.get("type") == "text")
            if t:
                return t
    return ""


def ancres_des_agents_en_vol():
    """Ce que les agents VIFS s'appretent a editer -- par DEUX canaux, et il en faut deux.

    (1) GIT, dans leur worktree : ce qu'ils touchent REELLEMENT. Ces ancres etaient jusqu'ici
        recopiees A LA MAIN depuis le libelle de la tache, c'est-a-dire depuis ce qu'on
        CROYAIT que l'agent touchait. Or un agent deborde : mesure du 2026-08-15, celui qui
        etait annonce sur `triggers/dispatch/registry.py` editait aussi
        `effects/aura_selectors.py` et trois fichiers `triggers/loki/`.

    (2) LE BRIEF : ce qu'on lui a DEMANDE d'editer.

    ⚠ GIT SEUL NE SUFFIT PAS, ET LE MANQUE EST EXACTEMENT DANS LE SENS DANGEREUX. Un agent
    LANCE A L'INSTANT n'a encore rien ecrit : il rend `0 fichier touche`, donc surface vide,
    donc son foyer ressort comme << libre >>. Mesure du 2026-08-15 : trois agents venaient
    d'etre dispatches sur `extra_damage_aura.py`, `abilities/targeting.py` et
    `behaviours/combat.py` ; l'outil, branche sur git seul, a re-propose les trois. C'est le
    doublon que cet outil existe pour empecher, et il l'aurait FABRIQUE.

    ⚠ Le brief seul ne suffit pas non plus -- c'est le cas (1). Les deux canaux se rattrapent
    l'un l'autre, et l'UNION est la bonne operation : pour une surface INTERDITE, sur-inclure
    fait seulement eviter davantage, tandis que sous-inclure fait collisionner.

    Rend `(ancres, agents)`. Se branche sur `fleet_board` plutot que de re-deriver l'etat de
    la flotte : le critere d'arret d'un agent y vit deja, et il est subtil (composition des
    blocs de la derniere entree du transcript, pas un timer).
    """
    try:
        import fleet_board as FB
    except Exception as e:                                     # pragma: no cover
        sys.exit("fleet_board illisible (%s) -- sans lui, aucune ancre n'est derivable" % e)
    rows = [r for r in FB.collect(include_done=False, only_alive=True)
            if r.get("wt") and int(r.get("depth") or 1) == 1]
    ancres, agents = set(), []
    for r in rows:
        wt = r["wt"]
        # non commite + commite au-dessus de la base : un agent qui vient de commiter ne doit
        # pas disparaitre de la surface interdite entre deux appels.
        brut = git("status", "--porcelain", cwd=wt) + "\n"
        brut += git("diff", "--name-only", "origin/master...HEAD", cwd=wt)
        par_git = set(RE_ENGINE.findall(brut.replace("\\", "/")))
        brief = brief_par_la_tete(FB, r["id"]) or (r.get("brief") or "")
        par_brief = set(RE_BRIEF.findall(brief.replace("\\", "/")))
        vus = par_git | par_brief
        agents.append((r["name"], len(par_git), len(par_brief)))
        ancres |= vus
    return ancres, agents


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=3, help="nombre de lots (defaut 3)")
    ap.add_argument("--ancre", action="append", default=[],
                    help="ancre SUPPLEMENTAIRE a interdire (repetable)")
    ap.add_argument("--min-residus", type=int, default=3,
                    help="taille minimale d'un lot (defaut 3)")
    ap.add_argument("--sans-flotte", action="store_true",
                    help="ne PAS deriver les ancres de la flotte (n'utiliser que --ancre)")
    args = ap.parse_args()

    res_par_foyer = lire_index()
    foyers_du_residu = collections.defaultdict(set)
    for f, ids in res_par_foyer.items():
        for i in ids:
            foyers_du_residu[i].add(f)
    tous = set().union(*res_par_foyer.values()) if res_par_foyer else set()
    print("index : %d foyers, %d residus distincts" % (len(res_par_foyer), len(tous)))

    ancres = set(args.ancre)
    if not args.sans_flotte:
        derivees, agents = ancres_des_agents_en_vol()
        ancres |= derivees
        print("flotte : %d agent(s) vif(s) de tete" % len(agents))
        for nom, k_git, k_brief in agents:
            print("   %-44s git %2d | brief %2d" % (nom[:44], k_git, k_brief))
    if not ancres:
        print("aucune ancre -- rien a interdire, tous les lots sont libres")

    interdit, absentes = set(), []
    for a in sorted(ancres):
        trouve = apparier(res_par_foyer, a)
        if not trouve:
            absentes.append(a)
            continue
        for f in trouve:
            interdit |= surface_de(res_par_foyer, foyers_du_residu, f)
    if absentes:
        # Une ancre absente de l'index est une INFORMATION (ce fichier ne porte aucun residu
        # ouvert), pas une panne. La faire echouer dur ferait renoncer a un filtre par
        # ailleurs valide.
        print("ancres sans residu ouvert (informatif) : %d" % len(absentes))
        for a in absentes:
            print("   - %s" % a)
    if ancres and not interdit:
        # CE QUI DOIT BLOQUER, c'est un filtre VACANT : lui laisse repartir un agent sur le
        # foyer d'un autre, silencieusement.
        sys.exit("surface interdite VIDE alors que des ancres existent -- filtre vacant, arret")
    print("surface INTERDITE : %d foyers" % len(interdit))

    degeneres = [f for f in res_par_foyer if "engine/" in f and not foyer_nomme(f)]
    if degeneres:
        print("foyers DEGENERES ecartes (ne nomment aucun fichier) : %d" % len(degeneres))
        for f in sorted(degeneres):
            print("   - %r" % f)

    cands = sorted(((f, len(i)) for f, i in res_par_foyer.items()
                    if "engine/" in f and len(i) >= args.min_residus and foyer_nomme(f)),
                   key=lambda x: -x[1])

    print()
    print("--- %d lot(s) LIBRE(S), disjoints des agents en vol ET entre eux ---" % args.n)
    choisis = []
    for f, k in cands:
        s = surface_de(res_par_foyer, foyers_du_residu, f)
        if se_croisent(s, interdit):
            continue
        if any(se_croisent(s, surface_de(res_par_foyer, foyers_du_residu, g))
               for g in choisis):
            continue
        choisis.append(f)
        court = f.split("engine/")[-1]
        print("  RETENU  %-50s %2d residus, surface %2d" % (court[:50], k, len(s)))
        print("      residus : %s" % ", ".join(sorted(res_par_foyer[f])))
        print("      surface : %s" % ", ".join(sorted(x.split("engine/")[-1] for x in s)))
        if len(choisis) >= args.n:
            break
    if not choisis:
        print("  AUCUN -- tout l'engine est dans la surface des agents en vol.")
    elif len(choisis) < args.n:
        print("  (%d seulement sur %d demandes)" % (len(choisis), args.n))

    print()
    print("PORTEE -- ce que cet outil ne garantit PAS : l'index est un GENERE, il date de sa")
    print("derniere regeneration (index_foyers.py) ; un residu dont la ligne n'a pas de champ")
    print("FOYER: n'y figure pas du tout, et ne sera donc jamais interdit.")


if __name__ == "__main__":
    main()
