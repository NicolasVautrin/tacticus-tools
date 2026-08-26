"""#10048 -- LE REFUS EXECUTABLE : une forge neuve ne PEUT PLUS oublier.

Deux gisements trouves le meme jour, de forme IDENTIQUE : un mecanisme correct, cable sur
CERTAINS chemins et pas sur les autres, et rien pour le dire.

  #10046  `declarerSourceDeChargement` -- 4 forges sur 7 ne declaraient pas leur source, donc
          `ciblesAuto: "moi"` rendait `0 cible` sur ces chemins-la. Repare par un point de
          passage unique, `chargerBcDepuisSource`.
  (id.)   `sandbox_fenetre_armer` -- seul `sandbox_boss.py` armait la fermeture de fenetre ;
          `sandbox_campagne.py` laissait 19 relais d'ECRITURE armes apres une sandbox quittee,
          dont `sandboxModeBcOverride`. Repare par un appel de plus.

⛔ MAIS UN HELPER DISPONIBLE N'EST PAS UNE GARANTIE, C'EST UNE INVITATION. Apres les deux
correctifs, rien n'empeche la forge SUIVANTE d'appeler `invokeMethod` en direct, ni le pilote
SUIVANT d'oublier la fermeture. C'est exactement le motif qui a echoue deux fois : un contrat
qu'on tient en recopiant le voisin tient jusqu'a ce qu'on ecrive sans regarder. Ce probe est le
refus executable qui manquait -- la prose n'arrete pas un comportement.

CE QU'IL GARDE, en INVARIANTS (jamais un seuil, qui se degrade) :

  ETAGE 1  tout `LoadBattle*` invoque sur une source de mode passe par `chargerBcDepuisSource`.
  ETAGE 2  tout pilote Python qui ARME un relais d'ecriture sandbox arme AUSSI la fermeture.

⚠ LES DEUX PERIMETRES SONT DERIVES, PAS RECOPIES. L'etage 1 decouvre ses sites en cherchant les
resolutions de methode ; l'etage 2 lit la liste des relais dans `relais_sandbox.ECRIVENT`, la
source unique. Une liste blanche ecrite ici ne pourrait pas montrer le chemin qu'elle a oublie --
c'est le vice meme qu'on gardera.

⚠ ET LE PROBE ASSERTE SON PROPRE NON-VIDE. Un recenseur qui ne visite rien rend zero violation et
passe pour vert : c'est un faux vert, pas un succes. Si l'etage 1 ne trouve AUCUNE resolution, ou
aucun site conforme, il ROUGIT en le disant -- son detecteur est casse, pas le depot propre.

Sortie ASCII pure (console Windows cp1252).
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
HOOKS = RACINE / "frida" / "hooks"
PILOTES = RACINE / "scripts" / "python"

sys.path.insert(0, str(PILOTES))
from relais_sandbox import ECRIVENT              # noqa: E402  -- la source UNIQUE de la liste

HELPER = "chargerBcDepuisSource"
FERMETURE = "sandbox_fenetre_armer"

# Une resolution de `LoadBattle*` liee a un nom : `const mi = findMethodByParamCount(k, "LoadBattle", 1)`
# ou `const mi = methodeDe(src, "LoadBattleInternal", 1)`. On capture le NOM et la METHODE.
RESOLUTION = re.compile(
    r"(?:const|let)\s+(\w+)\s*=\s*(?:findMethodByParamCount|methodeDe)\s*\("
    r"[^;]*?[\"'](LoadBattle\w*)[\"']",
    re.S)


def etage1():
    """Tout `LoadBattle*` passe-t-il par le point de passage unique ?"""
    resolutions, conformes, violations = 0, [], []
    for f in sorted(HOOKS.rglob("*.ts")):
        src = f.read_text(encoding="utf-8", errors="replace")
        if "LoadBattle" not in src:
            continue
        for var, methode in RESOLUTION.findall(src):
            resolutions += 1
            rel = f.relative_to(RACINE).as_posix()
            # L'invoke se cherche par le NOM LIE, pas par proximite de lignes : une distance en
            # lignes se casse au premier commentaire insere.
            direct = re.search(r"\binvokeMethod\s*\(\s*%s\.info\b" % re.escape(var), src)
            passe = re.search(r"\b%s\s*\(\s*%s\.info\b" % (re.escape(HELPER), re.escape(var)), src)
            if passe:
                conformes.append((rel, var, methode))
            elif direct:
                violations.append((rel, var, methode, src[:direct.start()].count("\n") + 1))
            # Ni l'un ni l'autre : la resolution ne debouche sur aucun invoke dans ce fichier
            # (sonde, controle d'existence). Ce n'est pas une violation -- et on ne l'invente pas.
    return resolutions, conformes, violations


# ⚠ CE QUI FAIT D'UN ARMEMENT UNE SANDBOX SE DERIVE, IL NE SE LISTE PAS. `deploiement_commun.py`
# documente exactement les relais qui n'ont AUCUN sens sur une bataille reelle : la phase FORCEE
# (une vraie partie a deja la sienne), le pool DELEGUE a une autre source (`SandboxGameModeSource`
# ne fournit pas de roster), et `sandboxModeGameViews` (inerte ailleurs). Un pilote qui en arme
# UN monte une sandbox ; les deux chaines de bataille REELLE n'en arment aucun et s'excluent donc
# toutes seules -- sans liste d'exemptions a tenir a jour, qui se perimerait au premier ajout.
#
# ⛔ ET C'EST VOULU QUE LES CHAINES REELLES SOIENT EXCLUES : elles NE DOIVENT PAS eteindre leurs
# relais en fin de passe, la boucle de farm en rejoue une autre derriere.
#
# ⚠ DEUX DEFAUTS DE DETECTEUR, TROUVES AU PREMIER PASSAGE ET CORRIGES ICI -- un cliquet qui
# classe mal est pire qu'aucun cliquet :
#   (a) `deploiement_commun.py` etait accuse sur un marqueur CITE DANS UN COMMENTAIRE (le bloc
#       << CE QUI N'EST VRAI QUE POUR LA SANDBOX >>). On depouille donc les commentaires avant
#       de chercher. Limite assumee : un `#` a l'interieur d'une chaine coupe la ligne trop tot,
#       ce qui peut MASQUER un armement -- jamais en INVENTER un.
#   (b) `sandbox_gw.py` etait classe << reel >> parce que ses relais sont un DICT
#       (`{"nom": {...}}`) et non des tuples (`("nom", {...})`). Les deux formes sont acceptees.
FORME = r"[\"']%s[\"']\s*[,:]\s*\{[^}]*[\"']%s[\"']\s*:%s"
MARQUEURS_SANDBOX = (
    FORME % ("deploymentPhaseArmer", "forcer", r"\s*True"),
    FORME % ("deploymentPoolArmer", "source", ""),
    FORME % ("sandboxModeGameViews", "armer", r"\s*True"),
)


def sans_commentaires(src):
    """Depouiller les commentaires de ligne. Voir (a) ci-dessus pour la limite assumee."""
    return "\n".join(l.split("#", 1)[0] for l in src.split("\n"))

# LA DETTE ATTESTEE -- des pilotes sandbox non encore convertis, NOMMES. Ce cliquet ne rougit que
# sur un pilote NEUF : un garde qui rougit toujours est un garde qu'on cesse de lire, et c'est
# exactement ce qui laisse repasser le cas qu'il devait attraper (`relais_sandbox.py` porte deja
# cette lecon). Cette liste ne doit que DECROITRE.
DETTE_ATTESTEE = {
    "scripts/python/sandbox_pvp.py",
    "scripts/python/sandbox_incursion.py",
    "scripts/python/sandbox_guildwar.py",
    "scripts/python/sandbox_gw.py",
}


def etage2():
    """Tout pilote qui monte une SANDBOX arme-t-il l'extinction de ses relais ?"""
    noms = {n for n, _ in ECRIVENT}
    conformes, dette, neufs, hors = [], [], [], []
    for f in sorted(PILOTES.glob("*.py")):
        brut = f.read_text(encoding="utf-8", errors="replace")
        if f.name in ("relais_sandbox.py", "desarmer_relais.py") or f.name.startswith("probe_"):
            continue
        src = sans_commentaires(brut)
        arme = [n for n in noms
                if re.search(FORME % (re.escape(n), "armer", r"\s*True"), src)]
        if not arme:
            continue
        rel = f.relative_to(RACINE).as_posix()
        if not any(re.search(m, src) for m in MARQUEURS_SANDBOX):
            hors.append((rel, len(arme)))          # bataille REELLE : exclu, et on le DIT
        elif FERMETURE in src or "armer_relais_sandbox" in src:
            conformes.append((rel, len(arme)))
        elif rel in DETTE_ATTESTEE:
            dette.append((rel, len(arme)))
        else:
            neufs.append((rel, sorted(arme)[:4], len(arme)))
    return conformes, dette, neufs, hors


print("=" * 78)
print("#10048 -- LE POINT DE PASSAGE DES FORGES, ET LA FERMETURE DES FENETRES SANDBOX")
print("=" * 78)

res, conformes, viols = etage1()
print()
print("ETAGE 1 : `LoadBattle*` -> `%s`" % HELPER)
print("  resolutions trouvees : %d   conformes : %d   VIOLATIONS : %d"
      % (res, len(conformes), len(viols)))
for rel, var, m, ligne in viols:
    print("    ROUGE  %s:%d  `%s` (%s) invoque en DIRECT -- doit passer par `%s`"
          % (rel, ligne, var, m, HELPER))
for rel, var, m in conformes:
    print("    ok     %s  `%s` (%s)" % (rel, var, m))

conf, dette, neufs, hors = etage2()
print()
print("ETAGE 2 : monter une SANDBOX -> armer l'extinction des relais")
print("  sandbox conformes : %d   dette attestee : %d   NEUFS : %d   hors perimetre (reel) : %d"
      % (len(conf), len(dette), len(neufs), len(hors)))
for rel, exemples, n in neufs:
    print("    ROUGE  %s arme %d relais d'ecriture (%s...) sans armer l'extinction"
          % (rel, n, ", ".join(exemples)))
for rel, n in conf:
    print("    ok     %s (%d relais)" % (rel, n))
for rel, n in dette:
    print("    dette  %s (%d relais) -- atteste, a convertir vers `armer_relais_sandbox`" % (rel, n))
for rel, n in hors:
    print("    hors   %s (%d relais) -- bataille REELLE : ne doit PAS eteindre (boucle de farm)"
          % (rel, n))

# ⚠ LE NON-VIDE, ET C'EST CE QUI SAUVE LE PROBE DE LUI-MEME.
print()
rc = 0
if res == 0:
    print("ROUGE (DETECTEUR) : AUCUNE resolution de `LoadBattle*` trouvee. Le depot n'est pas")
    print("  propre -- c'est le motif de detection qui ne mord plus (renommage, refactor).")
    rc = 2
elif not conformes:
    print("ROUGE (DETECTEUR) : aucun site CONFORME trouve. Meme cause : sans temoin positif,")
    print("  un zero de violations ne prouve rien.")
    rc = 2
if not (conf or dette or neufs or hors):
    print("ROUGE (DETECTEUR) : aucun pilote armeur trouve -- l'etage 2 ne visite rien.")
    rc = 2
elif not conf:
    print("ROUGE (DETECTEUR) : aucun pilote sandbox CONFORME. Sans temoin positif, un zero de")
    print("  neufs ne prouve rien -- le marqueur de conformite ne mord plus.")
    rc = 2

if rc == 0 and (viols or neufs):
    rc = 1
if dette:
    print("DETTE ATTESTEE : %d pilote(s) sandbox deroulent encore leur propre boucle." % len(dette))
    print("  Ce n'est PAS un vert sur eux -- c'est un cliquet qui ne doit que DECROITRE.")
print("VERDICT :", "VERT" if rc == 0 else ("ROUGE" if rc == 1 else "ROUGE (DETECTEUR CASSE)"))
sys.exit(rc)
