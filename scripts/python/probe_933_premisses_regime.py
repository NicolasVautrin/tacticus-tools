#!/usr/bin/env python
"""#933 -- les PREMISSES DE REGIME perimees par la bascule « items Best-In-Slot ».

POURQUOI CE PROBE EXISTE
------------------------
Depuis #419-r5/-r6, `_normalize_and_extract_pool` equipe les items Best-In-Slot PAR DEFAUT.
Aucun code de moteur n'a bouge, et pourtant tout test ecrit AVANT cette bascule qui presuppose
un porteur A ZERO est devenu rouge -- ou, pire, TROMPEUR-MAIS-VERT. Cinq victimes connues au
2026-08-11, dont TROIS trouvees PAR HASARD en jouant une regression sans rapport.

`probe_419r6_perimetre_bascule.py` a derive le perimetre par TROIS canaux (coup propre exige /
deja neutralise / valeur en dur > 100). Ce probe-ci ouvre le QUATRIEME, celui qu'aucun des trois
ne voit : l'ASSERTION SUR UNE STAT TOTALE SENSIBLE AU REGIME.

LES DEUX FORMES, ET POURQUOI ELLES SONT LA MEME
------------------------------------------------
  (Z) PREMISSE-ZERO   `assert stat(...) == 0`, `== (0, 0)`, `not crit_chance`
      -> devient ROUGE des que la base cesse d'etre nulle. Se voit dans un `rc`.
  (P) ATTENDU-POSITIF `assert stat(...) > 0`
      -> reste VERT, et cesse de mesurer quoi que ce soit : avec une base non nulle, il passe
         MEME SI le mecanisme teste est mort. Aucun `rc` ne le signale. C'est la forme
         dangereuse, et c'est exactement le cas des deux `seed[...] > 0` de
         `test_lion_helm_block_aura_live.py`, dont le voisin `== (0, 0)` etait rouge.

Les deux ont le MEME remede : rendre la base nulle AU MONTAGE (`--unit-stat <u>:<Stat>=0`),
ce qui fait de la stat TOTALE la CONTRIBUTION -- la seule grandeur que ces tests visent.
Pas `TACTICUS_BIS_ITEMS=0`, qui deshabille tout le roster : c'est l'instrument de DIAGNOSTIC
(mode `--jouer`), jamais le remede (#914 §3.3).

CE QU'IL VISITE, ET CE QU'IL NE VISITE PAS -- imprime, jamais tu
-----------------------------------------------------------------
Il visite TOUS les `test_*.py` de `scripts/python/tests/`, classe live/offline par les memes
marqueurs de harnais que #419-r6, et pour chaque LIVE derive ses comparaisons. Il ne visite PAS
les probes `scripts/python/probe_*.py`, ni la face DECISION hors tests (`engine_validate.py`,
`predict_sweep.py`), ni ce qu'un test atteint via la fixture d'un autre paquet.

Aucune assertion : c'est un probe, il MESURE. La garde vit dans
`tests/engine/test_933_premisse_regime_offline.py`.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TESTS = _HERE / "tests"

# ---------------------------------------------------------------------------
# 1. LES STATS SENSIBLES AU REGIME -- derivees, jamais recopiees
# ---------------------------------------------------------------------------
# Ces deux jeux sont le RESULTAT de `--stats` (etage LIVE ci-dessous) sur le seed BC au rank 17 :
# les champs de `BC.Units[]` dont la valeur DIFFERE entre `equip_items=False` et
# `equip_items=True`. Ils sont ecrits ici pour que le recensement STATIQUE et le cliquet tournent
# OFFLINE ; `--stats` les re-derive et DIT s'ils ont bouge (c'est le cran qui empeche cette liste
# de se perimer en silence, exactement comme la premisse qu'elle sert a garder).
#
# LA DISTINCTION EST LE COEUR DU TRI, et elle est MESUREE, pas supposee (2026-08-11, 106 unites) :
#
#   champ            bouge   0->x    x->0
#   CritDamage          98     98       0      <- ZERO OUVERT
#   CritChance          98     98       0      <- ZERO OUVERT
#   BlockChance         46     46       0      <- ZERO OUVERT
#   BlockDamage         46     46       0      <- ZERO OUVERT
#   FixedArmor          49      0       0
#   Health               4      0       0
#   RemainingHealth      4      0       0
#
# Une stat dont AUCUNE unite ne passe de 0 a non-0 ne peut PAS perimer une premisse `== 0`, et
# un `> 0` ecrit sur elle etait deja vrai avant la bascule -- donc ni rouge ni trompeur par CE
# canal. Les quatre stats a ZERO OUVERT, elles, periment les DEUX formes d'un coup.
# `FixedArmor`/`Health` restent sensibles par le canal (C) « valeur en dur » de #419-r6, qui a
# ete balaye par `probe_419r6_perimetre_bascule.py` : ce probe-ci ne le redouble pas.
_STATS_ZERO_OUVERT = ("CritChance", "CritDamage", "BlockChance", "BlockDamage")
_STATS_QUI_BOUGENT = ("FixedArmor", "Health", "RemainingHealth")
_STATS_SENSIBLES = _STATS_ZERO_OUVERT + _STATS_QUI_BOUGENT

# Les noms sous lesquels ces memes stats s'ecrivent dans un test : cote `combatSnapshot`
# (camelCase), cote `StatType` (SCREAMING_SNAKE), et les abreviations d'usage. Le
# rapprochement se fait sur le TEXTE de l'expression comparee -- c'est une heuristique de NOM,
# et elle est declaree comme telle dans la sortie.
_MOTS_PAR_STAT = {
    "CritChance": ("critchance", "crit_chance", "crit_chances", "CRIT_CHANCE", "critC", "cc"),
    "CritDamage": ("critdamage", "crit_damage", "CRIT_DAMAGE", "critD", "cd"),
    "BlockChance": ("blockchance", "block_chance", "BLOCK_CHANCE", "blockC", "bc"),
    "BlockDamage": ("blockdamage", "block_damage", "BLOCK_DAMAGE", "blockD", "bd"),
    "FixedArmor": ("fixedarmor", "fixed_armor", "FIXED_ARMOR", "armour", "armor"),
    "Health": ("health", "hp", "HEALTH", "maxhealth", "max_health"),
    "RemainingHealth": ("remaininghealth", "remaining_health"),
}
# Un mot de 2 a 4 lettres (`cc`, `bd`, `hp`) est AMBIGU en identifiant nu : mesure sur le corpus,
# `cc` designe aussi des coordonnees de caster (`hexgeo.distance(cc, tc)`) et `bc` le
# BattleConfiguration. On ne l'accepte donc QUE comme CHAINE LITTERALE (`d["cc"]`), qui est la
# forme sous laquelle nos tests s'en servent comme cle. Les identifiants nus sont ECARTES et
# COMPTES (`ecartes_mot_court`) : un filtre qui ne dit pas ce qu'il jette se lit comme un zero.
_MOTS_COURTS = {m for ms in _MOTS_PAR_STAT.values() for m in ms if len(m) <= 4}

# Le montage qui NEUTRALISE la base d'une stat sensible. `--unit-stat …:<Stat>=0` est le remede
# etabli (#912, #914, #923) ; `--crit`/`--block-*` epinglent le TIRAGE, ce qui neutralise le
# BRUIT mais PAS la base -- ils comptent donc pour le canal (A) de #419-r6, pas pour celui-ci.
_RE_NEUTRALISE = re.compile(
    r"(?:--unit-stat|unit_stat|explicit-stats|explicit_stats)", re.I)
_RE_NEUTRALISE_STAT = re.compile(
    r"(CritChance|CritDamage|BlockChance|BlockDamage|FixedArmor|Health|Armor)\s*=\s*0\b")
# `--hp-target`/`--hp-player`/`--armor-target` ecrivent eux aussi `Armor`/`FixedArmor`/`Health`
# du BC : ce sont des neutralisations de base a part entiere, sur ces stats-la.
_RE_NEUTRALISE_LEVIER = re.compile(r"--(?:hp-target|hp-player|armor-target|dmg-target)")

_MARQUEURS_LIVE = ("build_runner", "live_session", '"rl_duel.py", "build"',
                   "'rl_duel.py', 'build'")


# ---------------------------------------------------------------------------
# 2. RECENSEMENT STATIQUE -- toutes les comparaisons, role DERIVE du noeud
# ---------------------------------------------------------------------------
def _texte(src_lignes: list[str], noeud) -> str:
    try:
        return ast.get_source_segment("\n".join(src_lignes), noeud) or ""
    except Exception:                                             # noqa: BLE001
        return ""


_ECARTES_MOT_COURT: Counter = Counter()


def _stats_nommees(txt: str) -> list[str]:
    """Quelles stats sensibles le TEXTE de cette expression nomme-t-il ?

    Heuristique de NOM, declaree : un test qui lit une stat sans jamais l'ecrire (via un
    helper opaque, un index numerique, un `*u`) n'est PAS vu ici. C'est la premiere des
    portees imprimees par `--recenser`.
    """
    bas = txt.lower()
    litteraux = {s for s in re.findall(r"""["']([A-Za-z_][A-Za-z_0-9]*)["']""", txt)}
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", txt))
    out = []
    for stat, mots in _MOTS_PAR_STAT.items():
        for m in mots:
            if m in _MOTS_COURTS:
                if m in litteraux:
                    out.append(stat)
                    break
                if m in tokens:
                    _ECARTES_MOT_COURT[m] += 1
            elif m.lower() in bas:
                out.append(stat)
                break
    return out


def _est_zero(noeud) -> bool:
    """`0`, `(0, 0)`, `[0, 0]`, `0.0` -- la valeur nulle sous ses formes ecrites."""
    if isinstance(noeud, ast.Constant):
        return isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool) \
            and noeud.value == 0
    if isinstance(noeud, (ast.Tuple, ast.List)):
        return bool(noeud.elts) and all(_est_zero(e) for e in noeud.elts)
    return False


def _est_positif(noeud) -> bool:
    if isinstance(noeud, ast.Constant):
        return isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool) \
            and noeud.value >= 0
    if isinstance(noeud, (ast.Tuple, ast.List)):
        return bool(noeud.elts) and all(_est_positif(e) for e in noeud.elts)
    return False


def _premisses(path: Path, src: str) -> list[dict]:
    """Toutes les comparaisons a une valeur NULLE ou POSITIVE, dans un fichier qui LIT une stat.

    ⚠ LE LIEN NOM <-> VALEUR NE SE FAIT PAS DANS L'EXPRESSION, et c'est la faute que la premiere
    ecriture de ce probe a commise : elle exigeait que l'expression comparee NOMME la stat, et
    ratait donc son propre cas d'entree -- `assert seed[az] == (0, 0)` de
    `test_lion_helm_block_aura_live.py`, ou le mot « block » n'apparait que dans le nom de la
    FONCTION qui a produit `seed`. Un recenseur qui ne voit pas la victime connue ne peut rien
    dire des inconnues.

    Le rattachement se fait donc au niveau du FICHIER (`_lit_stats`), et ce sont TOUTES les
    comparaisons a 0 / a un positif qui sont recensees. Le fait que l'expression nomme elle-meme
    la stat devient un ATTRIBUT (`nomme`), utile pour trier, jamais un filtre.

    Le role est DERIVE de l'operateur et de la valeur comparee, pas choisi dans une liste blanche
    de formes ; une comparaison inconnue sort sous `autre`. La somme des roles est imprimee comme
    partition exhaustive des comparaisons VISITEES.
    """
    out: list[dict] = []
    try:
        arbre = ast.parse(src)
    except SyntaxError:
        return out
    lignes = src.splitlines()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Compare):
            continue
        txt = _texte(lignes, n)
        nomme = sorted(set(_stats_nommees(txt)))
        for op, comp in zip(n.ops, n.comparators):
            role = None
            if isinstance(op, ast.Eq) and _est_zero(comp):
                role = "premisse-zero"
            elif isinstance(op, ast.NotEq) and _est_zero(comp):
                role = "attendu-non-nul"
            elif isinstance(op, (ast.Gt, ast.GtE)) and _est_positif(comp):
                role = "attendu-positif"
            elif isinstance(op, (ast.Lt, ast.LtE)) and _est_positif(comp):
                role = "borne-superieure"
            elif isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) \
                    and isinstance(comp.value, int) and not isinstance(comp.value, bool):
                role = "valeur-en-dur"
            if role is None:
                continue
            out.append({
                "ligne": n.lineno,
                "role": role,
                "nomme": nomme,
                "src": (lignes[n.lineno - 1].strip()[:118] if n.lineno <= len(lignes) else ""),
            })
    return out


# Les noms sous lesquels un fichier LIT une stat a zero ouvert -- y compris les predicats natifs
# derives (`CouldCrit`/`CouldBlock`) et les tags d'evenement (`didCrit`), qui sont FAUX par
# construction tant que la stat vaut 0 et deviennent atteignables apres la bascule.
_LECTURES_ZERO_OUVERT = (
    "critchance", "crit_chance", "CRIT_CHANCE", "critdamage", "crit_damage", "CRIT_DAMAGE",
    "blockchance", "block_chance", "BLOCK_CHANCE", "blockdamage", "block_damage", "BLOCK_DAMAGE",
    "could_crit", "couldcrit", "could_block", "couldblock",
    "did_crit", "didcrit", "did_block", "didblock", "mightcrit", "might_crit",
)


def _lit_stats(src: str) -> list[str]:
    bas = src.lower()
    return sorted({m for m in _LECTURES_ZERO_OUVERT if m.lower() in bas})


def _classe_fichier(src: str) -> dict:
    neutralise_stats = set()
    if _RE_NEUTRALISE.search(src):
        neutralise_stats |= {m for m in _RE_NEUTRALISE_STAT.findall(src)}
    if _RE_NEUTRALISE_LEVIER.search(src):
        neutralise_stats |= {"Health", "FixedArmor", "Armor"}
    return {
        "live": any(m in src for m in _MARQUEURS_LIVE),
        "neutralise": sorted(neutralise_stats),
    }


def recenser(racine: "Path | None" = None) -> dict:
    racine = racine or _TESTS
    fichiers = sorted(racine.rglob("test_*.py"))
    vus = {"fichiers": 0, "offline": 0, "live": 0, "live_sans_lecture": 0, "live_lecteur": 0}
    roles: Counter = Counter()
    par_fichier: dict[str, dict] = {}
    for p in fichiers:
        src = p.read_text(encoding="utf-8", errors="replace")
        rel = str(p.relative_to(racine)).replace("\\", "/")
        vus["fichiers"] += 1
        c = _classe_fichier(src)
        if not c["live"]:
            vus["offline"] += 1
            continue
        vus["live"] += 1
        lectures = _lit_stats(src)
        if not lectures:
            vus["live_sans_lecture"] += 1
            continue
        vus["live_lecteur"] += 1
        prem = _premisses(p, src)
        for e in prem:
            roles[e["role"]] += 1
        if prem:
            par_fichier[rel] = {"premisses": prem, "neutralise": c["neutralise"],
                                "lectures": lectures}
    return {"vus": vus, "roles": roles, "par_fichier": par_fichier}


_ROLES_PERIMABLES = ("premisse-zero", "attendu-positif", "attendu-non-nul", "valeur-en-dur")


def _suspects(rec: dict) -> dict[str, list[dict]]:
    """Les fichiers qui LISENT une stat a zero ouvert, COMPARENT a 0 / a un positif, et dont la
    base n'est PAS neutralisee au montage.

    Un fichier qui neutralise deja les 4 stats a zero ouvert est ecarte -- c'est le remede, et
    le compter comme suspect ferait du bruit qui noie les vrais.
    """
    zo = set(_STATS_ZERO_OUVERT)
    out: dict[str, list[dict]] = {}
    for rel, info in rec["par_fichier"].items():
        if zo <= set(info["neutralise"]):
            continue
        gardes = [e for e in info["premisses"] if e["role"] in _ROLES_PERIMABLES]
        if gardes:
            out[rel] = gardes
    return out


# ---------------------------------------------------------------------------
# 3. ETAGE LIVE -- re-deriver les stats sensibles (le jeu par defaut ci-dessus)
# ---------------------------------------------------------------------------
def mesurer_stats(rank: int) -> dict:
    sys.path.insert(0, str(_HERE))
    import rl_collect_batch as R                                   # noqa: E402

    sid = R._resolve_session()
    seed = R._load_seed_bc()
    tpl_t, pool_t, mow_t = R._normalize_and_extract_pool(sid, seed, rank, equip_items=False)
    tpl_c, _, _ = R._normalize_and_extract_pool(sid, seed, rank, equip_items=True)
    ids = sorted(set(pool_t) | set(mow_t))
    t_by = {u["Id"]: u for u in tpl_t["Units"]}
    c_by = {u["Id"]: u for u in tpl_c["Units"]}

    bouge: Counter = Counter()
    zero_vers_non_zero: Counter = Counter()
    non_zero_vers_zero: Counter = Counter()
    champs = set()
    for uid in ids:
        a, b = t_by.get(uid, {}), c_by.get(uid, {})
        champs |= {k for k, v in a.items() if isinstance(v, (int, float))
                   and not isinstance(v, bool)}
    for uid in ids:
        a, b = t_by.get(uid, {}), c_by.get(uid, {})
        for k in champs:
            va, vb = a.get(k), b.get(k)
            if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
                continue
            if va == vb:
                continue
            bouge[k] += 1
            if va == 0 and vb != 0:
                zero_vers_non_zero[k] += 1
            elif va != 0 and vb == 0:
                non_zero_vers_zero[k] += 1
    return {"sid": sid, "n_unites": len(ids), "bouge": bouge,
            "zero_vers_non_zero": zero_vers_non_zero,
            "non_zero_vers_zero": non_zero_vers_zero}


# ---------------------------------------------------------------------------
# 4. ETAGE DE DIAGNOSTIC -- jouer un fichier dans les DEUX regimes
# ---------------------------------------------------------------------------
_BILAN = re.compile(r"(\d+) (passed|failed|skipped|error)")


def _jouer_un(rel: str, regime: str | None) -> dict:
    env = dict(os.environ)
    if regime is None:
        env.pop("TACTICUS_BIS_ITEMS", None)
    else:
        env["TACTICUS_BIS_ITEMS"] = regime
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/" + rel,
                        "-q", "--tb=no", "-p", "no:randomly"],
                       cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    compte = {k: 0 for k in ("passed", "failed", "skipped", "error")}
    for n, k in _BILAN.findall(p.stdout or ""):
        compte[k] = int(n)
    compte["rc"] = p.returncode
    compte["inerte"] = bool(compte["passed"] == 0 and compte["skipped"] > 0)
    compte["fichier"] = rel
    compte["regime"] = "defaut" if regime is None else regime
    return compte


def _jouer(rels: list[str], regime: str | None, workers: int,
           journal: "Path | None" = None) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    import threading

    deja: dict[str, dict] = {}
    if journal is not None and journal.exists():
        for ligne in journal.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ligne)
            except Exception:                                     # noqa: BLE001
                continue
            if r.get("fichier"):
                deja[r["fichier"]] = r
    a_jouer = [r for r in rels if r not in deja]
    if journal is not None:
        print("  [journal] %s : %d deja mesure(s), %d a jouer"
              % (journal.name, len(rels) - len(a_jouer), len(a_jouer)))
        journal.parent.mkdir(parents=True, exist_ok=True)
    verrou = threading.Lock()

    def _un(rel):
        r = _jouer_un(rel, regime)
        if journal is not None:
            with verrou, journal.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
        return r

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
        joues = list(ex.map(_un, a_jouer))
    return [deja[r] for r in rels if r in deja] + joues


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--recenser", action="store_true",
                    help="balayage STATIQUE exhaustif des tests (offline)")
    ap.add_argument("--lister", choices=["suspects", "tout"], default=None)
    ap.add_argument("--arbre", default=None,
                    help="racine de tests a recenser (defaut : scripts/python/tests). Sert a "
                         "recenser un arbre TEMOIN -- p. ex. l'etat d'avant une reparation, "
                         "pour verifier que le recenseur voit bien la victime CONNUE")
    ap.add_argument("--stats", action="store_true",
                    help="LIVE : re-derive les stats sensibles au regime (diff des templates)")
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--jouer", default=None,
                    help="LIVE : joue une liste explicite (rel. a tests/, virgules) ; "
                         "`suspects` joue les fichiers suspects du recensement")
    ap.add_argument("--regime", choices=["0", "1", "defaut"], default="defaut")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--journal", default=None)
    ap.add_argument("--depuis", type=int, default=0)
    ap.add_argument("--jusqu-a", type=int, default=0)
    a = ap.parse_args(argv)

    if not any((a.recenser, a.stats, a.jouer)):
        a.recenser = True

    rec = None
    if a.recenser or a.jouer == "suspects":
        if not _TESTS.exists():
            print("[933] ARBRE DE TESTS INTROUVABLE : %s -- aucune mesure" % _TESTS)
            return 2
        rec = recenser(Path(a.arbre) if a.arbre else None)
        susp = _suspects(rec)
        v = rec["vus"]
        print("=== #933 -- PREMISSES DE REGIME (balayage STATIQUE) ===")
        print("  arbre                               : %s" % (a.arbre or str(_TESTS)))
        print("  fichiers de test visites            : %d" % v["fichiers"])
        print("    dont OFFLINE (hors perimetre)     : %d" % v["offline"])
        print("    dont LIVE (montent un runner)     : %d" % v["live"])
        print("      dont LISANT une stat a zero ouvert : %d" % v["live_lecteur"])
        print("      dont n'en lisant AUCUNE            : %d  (ECARTES : rien a perimer)"
              % v["live_sans_lecture"])
        print("  stats a ZERO OUVERT (0 -> non-0)    : %s" % ", ".join(_STATS_ZERO_OUVERT))
        print("  stats qui BOUGENT sans passer par 0 : %s  (canal (C) de #419-r6)"
              % ", ".join(_STATS_QUI_BOUGENT))
        total = sum(rec["roles"].values())
        print("  comparaisons a 0 / a un positif, dans les fichiers LECTEURS : %d" % total)
        print("  -- partition EXHAUSTIVE par role (somme = %d) --" % total)
        for role, n in rec["roles"].most_common():
            print("     %-18s %d" % (role, n))
        print("  ECARTES : mots courts en identifiant NU (ambigus, cf. en-tete) : %s"
              % (dict(_ECARTES_MOT_COURT) if _ECARTES_MOT_COURT else "(aucun)"))
        print("  fichiers LECTEURS portant au moins une comparaison : %d"
              % len(rec["par_fichier"]))
        print("  fichiers SUSPECTS -- lecteur, comparaison perimable, base NON neutralisee : %d"
              % len(susp))
        print("  --- CE QUE CE BALAYAGE NE COUVRE PAS ---")
        print("   * une stat lue SANS que son nom soit ecrit (helper opaque, index numerique,")
        print("     deballage `*u`) : le rapprochement est une HEURISTIQUE DE NOM ;")
        print("   * les probes `scripts/python/probe_*.py` (ils mesurent, ils ne gardent rien) ;")
        print("   * la face DECISION hors tests (`engine_validate.py`, `predict_sweep.py`) ;")
        print("   * ce qu'un test atteint via la fixture d'un AUTRE paquet ;")
        print("   * les stats sensibles AUTRES que les %d listees -- `--stats` les re-derive."
              % len(_STATS_SENSIBLES))
        if a.lister:
            cible = susp if a.lister == "suspects" else {
                k: v2["premisses"] for k, v2 in rec["par_fichier"].items()}
            print("=== liste : %s (%d fichier(s)) ===" % (a.lister, len(cible)))
            for rel in sorted(cible):
                neutres = rec["par_fichier"][rel]["neutralise"]
                print("  %s%s" % (rel, ("   [neutralise: %s]" % ",".join(neutres))
                                  if neutres else ""))
                for e in cible[rel]:
                    print("      L%-5d %-18s %-24s %s"
                          % (e["ligne"], e["role"], ",".join(e["nomme"]) or "-", e["src"]))

    if a.stats:
        m = mesurer_stats(a.rank)
        print("=== #933 -- STATS SENSIBLES, RE-DERIVEES (session %d, %d unites, rank %d) ==="
              % (m["sid"], m["n_unites"], a.rank))
        print("  champ                 bouge   0->x    x->0")
        for k, n in m["bouge"].most_common():
            print("  %-20s %5d  %5d  %5d"
                  % (k, n, m["zero_vers_non_zero"].get(k, 0),
                     m["non_zero_vers_zero"].get(k, 0)))
        mesure = {k for k in m["bouge"]}
        ecrite = set(_STATS_SENSIBLES)
        if mesure != ecrite:
            print("  ATTENTION -- le jeu ECRIT dans ce probe DIFFERE de la mesure :")
            print("     mesurees et non ecrites : %s" % sorted(mesure - ecrite))
            print("     ecrites et non mesurees : %s" % sorted(ecrite - mesure))
        else:
            print("  le jeu ECRIT dans ce probe est CONFORME a la mesure (%d stats)"
                  % len(ecrite))

    if a.jouer:
        if a.jouer == "suspects":
            rels = sorted(_suspects(rec))
        else:
            rels = [s.strip() for s in a.jouer.split(",") if s.strip()]
        fin = a.jusqu_a or len(rels)
        rels = rels[a.depuis:fin]
        regime = None if a.regime == "defaut" else a.regime
        print("=== JEU : %d fichier(s), TACTICUS_BIS_ITEMS=%s ===" % (len(rels), a.regime))
        res = _jouer(rels, regime, a.workers, Path(a.journal) if a.journal else None)
        n_inerte = n_rouge = n_vert = 0
        for r in sorted(res, key=lambda x: x["fichier"]):
            if r["failed"] or r["error"] or r["rc"] not in (0, 1):
                etat, n_rouge = "ROUGE ", n_rouge + 1
            elif r["inerte"]:
                etat, n_inerte = "INERTE", n_inerte + 1
            else:
                etat, n_vert = "vert  ", n_vert + 1
            print("  %s %-62s p=%-3d s=%-3d f=%-3d e=%-3d rc=%d"
                  % (etat, r["fichier"], r["passed"], r["skipped"], r["failed"],
                     r["error"], r["rc"]))
        print("  BILAN : %d vert, %d INERTE (garde #455), %d ROUGE"
              % (n_vert, n_inerte, n_rouge))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
