#!/usr/bin/env python3
"""Garde de l'ARCHIVAGE de l'empreinte structurelle (#482-r3).

CE QUE CETTE GARDE PROTEGE, ET POURQUOI CE N'EST PAS CE QUE PROTEGE #482
------------------------------------------------------------------------
`probe_482` garde la MESURE : l'empreinte est-elle aveugle a la relocation et sensible au
changement de corps ? Cette garde-ci garde la CONSERVATION : l'empreinte sera-t-elle encore
CALCULABLE demain, et l'archive qu'on a rangee dit-elle bien de quel binaire elle vient ?

Les deux sont independants. Une empreinte parfaite dont le binaire a disparu ne se calcule
plus ; une archive parfaitement calculee mais rangee sous le mauvais build comparerait deux
binaires sans rapport et rendrait un changement fabrique de toutes pieces.

LE VICE VISE, NOMME
-------------------
<<Un capteur muet passe pour une bonne nouvelle.>> Le capteur repond a
<<cette empreinte est-elle encore recuperable ?>> en interrogeant DEUX repertoires qui vivent
hors du depot (`games/`, `ghidra-projects/`). Si l'un est illisible, une lecture nue rend
<<absent>>, et <<absent des deux>> se conclut PERDUE -- un verdict DEFINITIF rendu sur une
mesure qui n'a pas eu lieu. L'etage 3 est ecrit pour ca, et c'est le plus important des six.

`a_mordu` EST SEPARE DU VERDICT, partout : un mutant qui n'ecrit rien laisserait l'etat
inchange, ce qui se lirait comme <<le capteur n'a pas vu la mutation>> alors que c'est le
MUTANT qui est casse. Chaque mutation verifie d'abord qu'elle a mordu.

TOUT EST OFFLINE ET SUR ARBRE SYNTHETIQUE : aucun etage n'ecrit dans `data/`, aucun ne monte
de runner, aucun ne touche a un projet Ghidra.

USAGE
    python probe_482r3_archive_empreinte.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_fingerprint_archive as A  # noqa: E402
import fingerprint_functions as F  # noqa: E402
import symbols_sync as S  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

SHA_A = "a" * 64
SHA_B = "b" * 64

# --- corps x86-64 minuscules, ecrits a la main pour que chaque octet soit connu ------------
#   mov eax, <imm32> ; ret
def _mov_ret(imm: int) -> bytes:
    return b"\xb8" + struct.pack("<I", imm) + b"\xc3"


#   mov eax, dword ptr [rcx + 0xa8] ; ret        (offset de struct -> STRUCTUREL)
CORPS_CHAMP = bytes.fromhex("8B81A8000000C3")


def _call_ret(va_self: int, va_cible: int) -> bytes:
    """sub rsp,0x28 ; call <cible> ; add rsp,0x28 ; ret -- le `call` porte un delta qui
    change a chaque relocation : c'est ce qui rend l'etage 5 non trivial."""
    b = bytes.fromhex("4883EC28")
    b += b"\xe8" + struct.pack("<i", va_cible - (va_self + len(b) + 5))
    b += bytes.fromhex("4883C428") + b"\xc3"
    return b


class Faux:
    """Un depot SYNTHETIQUE : `data/symbols/<build>/`, un `games/`, un `ghidra-projects/`.

    Les constantes de module sont substituees le temps du contexte, puis RESTAUREES. Aucun
    etage ne peut donc ecrire dans le vrai `data/` -- ce qui ferait rougir `probe_273` 0c et
    salirait l'arbre de l'agent sans qu'il ait rien edite.
    """

    def __init__(self):
        self.racine = Path(tempfile.mkdtemp(prefix="probe482r3_"))
        self.symbols = self.racine / "data" / "symbols"
        self.games = self.racine / "games"
        self.projets = self.racine / "ghidra-projects"
        for p in (self.symbols, self.games, self.projets):
            p.mkdir(parents=True, exist_ok=True)
        self._sauve = {}

    def __enter__(self):
        self._sauve = dict(A_SYMBOLS=A.SYMBOLS, A_GAMES=A.GAMES_DIR,
                           F_REPO=F.REPO, F_SYMBOLS=F.SYMBOLS_DIR,
                           A_current=A.current_build,
                           env=os.environ.get(A._ENV_PROJETS))
        A.SYMBOLS = self.symbols
        A.GAMES_DIR = self.games
        F.REPO = self.racine
        F.SYMBOLS_DIR = self.symbols
        os.environ[A._ENV_PROJETS] = str(self.projets)
        return self

    def __exit__(self, *exc):
        A.SYMBOLS = self._sauve["A_SYMBOLS"]
        A.GAMES_DIR = self._sauve["A_GAMES"]
        F.REPO = self._sauve["F_REPO"]
        F.SYMBOLS_DIR = self._sauve["F_SYMBOLS"]
        A.current_build = self._sauve["A_current"]
        if self._sauve["env"] is None:
            os.environ.pop(A._ENV_PROJETS, None)
        else:
            os.environ[A._ENV_PROJETS] = self._sauve["env"]
        shutil.rmtree(self.racine, ignore_errors=True)
        return False

    # -- construction ------------------------------------------------------
    def build(self, nom: str, sha: str = SHA_A, table: bool = True) -> Path:
        d = self.symbols / nom
        (d / "frida").mkdir(parents=True, exist_ok=True)
        (d / "frida" / "methods.tsv").write_text(
            "#!il2cpp-provenance\tsha256=%s\tbuild=%s\tgenerated=2026-01-01T00:00:00"
            "\tsource=test\n" % (sha, nom), encoding="utf-8", newline="\n")
        if table:
            (d / "ghidra").mkdir(parents=True, exist_ok=True)
            (d / "ghidra" / "functions.tsv").write_text(
                "# build=%s\n180001000\tX$$Y\n" % nom, encoding="utf-8", newline="\n")
        return d

    def poser_dll(self, nom: str) -> None:
        (self.games / nom).mkdir(parents=True, exist_ok=True)
        (self.games / nom / "GameAssembly.dll").write_bytes(b"MZ")

    def retirer_dll(self, nom: str) -> None:
        shutil.rmtree(self.games / nom, ignore_errors=True)

    def poser_projet(self, nom: str) -> None:
        (self.projets / ("ghidra_%s" % nom)).mkdir(parents=True, exist_ok=True)

    def poser_archive(self, nom: str, sha: str = SHA_A, n: int = 42,
                      build_annonce: str | None = None) -> Path:
        p = A.archive_path(nom)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!empreinte-structurelle\tbuild=%s\torigine=test\tfonctions=%d"
                     "\tgenere=2026-01-01T00:00:00\tsha256=%s\n"
                     "#va\tsym\ttaille\tn_ins\th_local\th_body\th_mnem\th_calls\th_imm\tflags\n"
                     % (build_annonce or nom, n, sha), encoding="utf-8", newline="\n")
        return p

    def poser_blocs(self, dossier: Path, va_base: int, corps: dict, sha: str) -> Path:
        """Un dump de blocs a la forme de `GhidraDumpCodeBytes.java`. `corps` = {va: octets}."""
        dossier.mkdir(parents=True, exist_ok=True)
        fin = va_base + 0x10000
        data = bytearray(b"\xcc" * (fin - va_base))
        for va, oct_ in corps.items():
            data[va - va_base: va - va_base + len(oct_)] = oct_
        (dossier / "block_il2cpp.bin").write_bytes(bytes(data))
        (dossier / "blocks.meta").write_text(
            "#nom\tstartVA\ttaille\tr\tw\tx\tinitialise\tfichier\n"
            "il2cpp\t%x\t%d\ttrue\tfalse\ttrue\ttrue\tblock_il2cpp.bin\n"
            % (va_base, fin - va_base), encoding="utf-8", newline="\n")
        (dossier / "image.meta").write_text(
            "imageBase\t180000000\nexecutableSHA256\t%s\n" % sha,
            encoding="utf-8", newline="\n")
        return dossier

    def poser_table(self, nom: str, entrees: list[tuple[int, str]]) -> None:
        d = self.symbols / nom / "ghidra"
        d.mkdir(parents=True, exist_ok=True)
        d.joinpath("functions.tsv").write_text(
            "# build=%s\n" % nom + "".join("%x\t%s\n" % e for e in entrees),
            encoding="utf-8", newline="\n")


# ===========================================================================
def etage1_discrimination() -> bool:
    """Chaque configuration doit rendre SON etat -- un capteur qui rend le meme mot partout
    ne mesure rien. `a_mordu` = la configuration a bien ete construite sur disque."""
    print("-- ETAGE 1 : le capteur DISCRIMINE les etats --")
    ok = True
    with Faux() as f:
        # (libelle, construction, etat attendu, sonde de a_mordu)
        f.build("bArchive"); f.poser_archive("bArchive")
        f.build("bPE"); f.poser_dll("bPE")
        f.build("bGhidra"); f.poser_projet("bGhidra")
        f.build("bPerdu")
        f.build("bSansTable", table=False)
        f.build("bDiscord"); f.poser_archive("bDiscord", build_annonce="autre")

        cas = [
            ("archive presente et coherente", "bArchive", A.ARCHIVEE,
             lambda: A.archive_path("bArchive").is_file()),
            ("pas d'archive, binaire present", "bPE", A.RECUPERABLE_PE,
             lambda: (f.games / "bPE" / "GameAssembly.dll").is_file()),
            ("pas d'archive, projet Ghidra seul", "bGhidra", A.RECUPERABLE_GHIDRA,
             lambda: (f.projets / "ghidra_bGhidra").is_dir()),
            ("ni binaire ni projet (les DEUX mesures)", "bPerdu", A.PERDUE,
             lambda: f.games.is_dir() and f.projets.is_dir()),
            ("pas de table de symboles", "bSansTable", A.SANS_TABLE,
             lambda: not (f.symbols / "bSansTable" / "ghidra" / "functions.tsv").is_file()),
            ("archive rangee sous le mauvais build", "bDiscord", A.DISCORDANTE,
             lambda: A.archive_path("bDiscord").is_file()),
        ]
        for libelle, build, attendu, sonde in cas:
            mordu = sonde()
            vu = A.etat_archive(build).etat
            bon = mordu and vu == attendu
            ok &= bon
            print("   %-42s a_mordu=%-5s attendu=%-18s vu=%-18s %s"
                  % (libelle, mordu, attendu, vu, "OK " if bon else "ECHEC"))
    print("   => %s\n" % ("DISCRIMINE" if ok else "NE DISCRIMINE PAS"))
    return ok


def etage2_mutants_entete() -> bool:
    """Une archive VALIDE, mutee dans son en-tete, doit basculer en DISCORDANTE.

    C'est la seule chose qui separe <<une archive>> de <<une archive DE CE BUILD>>. Sans cet
    etage, un fichier recopie d'un autre build passerait pour une mesure."""
    print("-- ETAGE 2 : MUTANTS sur l'en-tete d'une archive valide --")
    ok = True
    with Faux() as f:
        f.build("b", sha=SHA_A)
        p = f.poser_archive("b", sha=SHA_A)
        avant_octets = p.read_bytes()
        etat_ref = A.etat_archive("b").etat
        print("   reference : %s" % etat_ref)
        if etat_ref != A.ARCHIVEE:
            print("   ECHEC : la reference n'est meme pas ARCHIVEE\n")
            return False

        lignes = avant_octets.decode("utf-8").split("\n")
        mutants = [
            ("build= annonce un AUTRE build",
             lignes[0].replace("build=b\t", "build=zzz\t")),
            ("sha256 d'un autre binaire",
             lignes[0].replace("sha256=" + SHA_A, "sha256=" + SHA_B)),
            ("sha256 absent (provenance inconnue)",
             lignes[0].replace("\tsha256=" + SHA_A, "")),
            ("fonctions=0 (fichier vide deguise)",
             lignes[0].replace("fonctions=42", "fonctions=0")),
            ("marqueur #! retire",
             lignes[0].replace("#!empreinte-structurelle", "#empreinte-structurelle")),
        ]
        for libelle, entete in mutants:
            mute = "\n".join([entete] + lignes[1:]).encode("utf-8")
            p.write_bytes(mute)
            mordu = mute != avant_octets
            vu = A.etat_archive("b").etat
            bon = mordu and vu == A.DISCORDANTE
            ok &= bon
            print("   %-42s a_mordu=%-5s vu=%-14s %s"
                  % (libelle, mordu, vu, "OK " if bon else "ECHEC"))
            p.write_bytes(avant_octets)
    print("   => %s\n" % ("SENSIBLE" if ok else "AVEUGLE a une archive incoherente"))
    return ok


def etage3_tri_etat() -> bool:
    """LE PLUS IMPORTANT. Une sonde qui n'a PAS PU mesurer ne doit JAMAIS produire PERDUE.

    `PERDUE` est un verdict definitif : il autorise a nettoyer un projet Ghidra. Le rendre
    sur un repertoire simplement illisible ferait detruire du materiel irremplacable.
    """
    print("-- ETAGE 3 : TRI-ETAT -- un capteur muet ne conclut JAMAIS a la perte --")
    ok = True
    with Faux() as f:
        f.build("b")
        # temoin : les deux sondes mesurent, rien n'est trouve -> PERDUE est LEGITIME
        temoin = A.etat_archive("b").etat
        d_ok = A.dll_present("b")
        print("   temoin (les deux repertoires existent) : dll_present=%r etat=%s"
              % (d_ok, temoin))
        ok &= (d_ok is False and temoin == A.PERDUE)

        cas = [
            ("games/ introuvable", lambda: shutil.rmtree(f.games), None),
            ("ghidra-projects/ introuvable", lambda: shutil.rmtree(f.projets), "garde"),
        ]
        for libelle, casser, _ in cas:
            casser()
            mordu = not (f.games.is_dir() and f.projets.is_dir())
            e = A.etat_archive("b")
            bon = mordu and e.etat == A.INDETERMINEE
            ok &= bon
            print("   %-42s a_mordu=%-5s vu=%-14s %s"
                  % (libelle, mordu, e.etat, "OK " if bon else "ECHEC"))
            if e.etat == A.PERDUE:
                print("        ^ FAUTE GRAVE : conclut a la perte sur une mesure absente")
            f.games.mkdir(parents=True, exist_ok=True)
            f.projets.mkdir(parents=True, exist_ok=True)

        # dll_present doit rendre None -- pas False -- quand la racine manque
        shutil.rmtree(f.games)
        vu = A.dll_present("b")
        bon = vu is None
        ok &= bon
        print("   %-42s vu=%-14r %s"
              % ("dll_present sans games/", vu, "OK " if bon else "ECHEC"))
        f.games.mkdir(parents=True, exist_ok=True)

        # projets_orphelins doit rendre None -- pas [] -- quand la racine manque
        shutil.rmtree(f.projets)
        vu = A.projets_orphelins()
        bon = vu is None
        ok &= bon
        print("   %-42s vu=%-14r %s"
              % ("projets_orphelins sans racine", vu, "OK " if bon else "ECHEC"))
        f.projets.mkdir(parents=True, exist_ok=True)
        vu = A.projets_orphelins()
        bon2 = vu == []
        ok &= bon2
        print("   %-42s vu=%-14r %s"
              % ("  ... racine VIDE mais lisible", vu, "OK " if bon2 else "ECHEC"))
    print("   => %s\n" % ("TRI-ETAT TENU" if ok else "TRI-ETAT ROMPU -- un muet passe pour un vide"))
    return ok


def etage4_garde_reagit() -> bool:
    """L'axe 6 de `symbols_sync` doit PARLER sur une archive manquante et LEVER sur une
    archive discordante. Un capteur juste dont la garde ne fait rien est en prose."""
    print("-- ETAGE 4 : la garde symbols_sync (axe 6) REAGIT --")
    ok = True
    with Faux() as f:
        f.build("b"); f.poser_dll("b")
        A.current_build = lambda: "b"

        # 1. archive manquante mais recuperable -> l'axe PARLE (propre == False)
        lignes, propre = S.axe6_archive_empreinte()
        bon = (propre is False) and any("NON ARCHIVEE" in l for l in lignes)
        ok &= bon
        print("   %-42s propre=%-5s %s" % ("archive manquante -> le hook parle",
                                           propre, "OK " if bon else "ECHEC"))

        # 2. archive posee -> l'axe se TAIT (propre == True)
        f.poser_archive("b")
        lignes, propre = S.axe6_archive_empreinte()
        bon = propre is True
        ok &= bon
        print("   %-42s propre=%-5s %s" % ("archive posee -> le hook se tait",
                                           propre, "OK " if bon else "ECHEC"))

        # 3. archive discordante -> LEVEE (rc 1 de la garde)
        f.poser_archive("b", build_annonce="autre")
        try:
            S.axe6_archive_empreinte()
            leve = False
        except S.Desync:
            leve = True
        ok &= leve
        print("   %-42s leve=%-5s %s" % ("archive discordante -> Desync",
                                         leve, "OK " if leve else "ECHEC"))

        # 4. perte DEFINITIVE : imprimee, mais ne LEVE pas (alarme inextinguible = desarmement)
        A.archive_path("b").unlink()
        f.retirer_dll("b")
        try:
            lignes, propre = S.axe6_archive_empreinte()
            leve = False
        except S.Desync:
            leve = True
        bon = (not leve) and any("PERDUE" in l for l in lignes) and propre is False
        ok &= bon
        print("   %-42s leve=%-5s %s" % ("perte definitive -> imprimee, pas de levee",
                                         leve, "OK " if bon else "ECHEC"))
    print("   => %s\n" % ("LA GARDE MORD" if ok else "LA GARDE NE MORD PAS"))
    return ok


def etage5_simulation() -> bool:
    """SIMULATION DU SCENARIO REEL, sur artefacts controles :
    un build disparait, un nouveau arrive, l'archive est la, le diff sort.

    CE QUI EST MESURE : la chaine complete `archiver --blocs` -> `data/symbols/<b>/
    fingerprints/` -> capteur -> `diff`, y compris apres SUPPRESSION du binaire du build
    sortant, et avec une RELOCATION integrale entre les deux builds.
    CE QUI NE L'EST PAS : la suppression par le vrai lanceur Tacticus (elle ne se provoque
    pas), et le cout reel (~70 s / build sur 150 000 fonctions contre 3 ici).
    """
    print("-- ETAGE 5 : SIMULATION -- un build disparait, un autre arrive, le diff sort --")
    ok = True
    with Faux() as f:
        # -- BUILD SORTANT : 3 fonctions, binaire "installe"
        base_a = 0x180001000
        va = dict(f1=base_a, f2=base_a + 0x20, f3=base_a + 0x40)
        corps_a = {va["f1"]: _mov_ret(0x539), va["f2"]: CORPS_CHAMP,
                   va["f3"]: _call_ret(va["f3"], va["f1"])}
        f.build("sortant", sha=SHA_A)
        f.poser_table("sortant", [(va["f1"], "Z$$Formule"), (va["f2"], "Z$$Champ"),
                                  (va["f3"], "Z$$Appelle")])
        f.poser_dll("sortant")
        blocs_a = f.poser_blocs(f.racine / "dump_a", base_a, corps_a, SHA_A)

        rc = F.main(["archiver", "--build", "sortant", "--blocs", str(blocs_a)])
        etat = A.etat_archive("sortant")
        bon = rc == 0 and etat.etat == A.ARCHIVEE
        ok &= bon
        print("   1. archive du build COURANT           rc=%d etat=%-10s %s"
              % (rc, etat.etat, "OK " if bon else "ECHEC"))

        # -- LA MISE A JOUR : le lanceur efface le dossier du sortant, le neuf arrive.
        f.retirer_dll("sortant")
        mordu = not (f.games / "sortant").is_dir()
        etat = A.etat_archive("sortant")
        # SANS archive, cet etat serait PERDUE (aucun projet Ghidra ici) : c'est exactement
        # ce que l'archivage anticipe evite.
        bon = mordu and etat.etat == A.ARCHIVEE
        ok &= bon
        print("   2. binaire du sortant EFFACE          a_mordu=%-5s etat=%-10s %s"
              % (mordu, etat.etat, "OK " if bon else "ECHEC"))

        # Contre-epreuve : sans l'archive, le meme etat serait PERDUE.
        sauve = A.archive_path("sortant").read_bytes()
        A.archive_path("sortant").unlink()
        sans = A.etat_archive("sortant").etat
        A.archive_path("sortant").write_bytes(sauve)
        bon = sans == A.PERDUE
        ok &= bon
        print("      contre-epreuve SANS archive        etat=%-10s %s"
              % (sans, "OK (l'archive est bien ce qui sauve)" if bon else "ECHEC"))

        # -- BUILD ENTRANT : tout est RELOCALISE (+0x8000), et Z$$Formule change sa constante.
        base_b = 0x180001000
        dec = 0x8000
        vb = dict(f1=base_b + dec, f2=base_b + dec + 0x20, f3=base_b + dec + 0x40)
        corps_b = {vb["f1"]: _mov_ret(0x53A),                     # <- CORPS CHANGE
                   vb["f2"]: CORPS_CHAMP,                          # <- identique
                   vb["f3"]: _call_ret(vb["f3"], vb["f1"])}        # <- delta d'appel different
        f.build("entrant", sha=SHA_B)
        f.poser_table("entrant", [(vb["f1"], "Z$$Formule"), (vb["f2"], "Z$$Champ"),
                                  (vb["f3"], "Z$$Appelle")])
        f.poser_dll("entrant")
        blocs_b = f.poser_blocs(f.racine / "dump_b", base_b, corps_b, SHA_B)

        etat = A.etat_archive("entrant")
        bon = etat.etat == A.RECUPERABLE_PE
        ok &= bon
        print("   3. build ENTRANT non archive          etat=%-18s %s"
              % (etat.etat, "OK " if bon else "ECHEC"))

        rc = F.main(["archiver", "--build", "entrant", "--blocs", str(blocs_b)])
        bon = rc == 0 and A.etat_archive("entrant").etat == A.ARCHIVEE
        ok &= bon
        print("   4. archive du build ENTRANT           rc=%d %s"
              % (rc, "OK " if bon else "ECHEC"))

        # -- LE DIFF : c'est la raison d'etre de tout le dispositif.
        _ea, av = F.lire_tsv(A.archive_path("sortant"))
        _eb, ap = F.lire_tsv(A.archive_path("entrant"))
        ia, ib, communs, _x, _y = F.apparier(av, ap)
        verdicts = {s: F.classifier(ia[s], ib[s])[0] for s in communs}
        attendu = {"Z$$Formule": "CORPS_CHANGE",     # constante 0x539 -> 0x53A
                   "Z$$Champ": "IDENTIQUE",          # rien n'a bouge que l'adresse
                   "Z$$Appelle": "APPELES_CHANGES"}  # corps propre stable, cible mutee
        bon = verdicts == attendu
        ok &= bon
        print("   5. DIFF des deux archives             %s" % ("OK " if bon else "ECHEC"))
        for s in sorted(attendu):
            marque = "OK " if verdicts.get(s) == attendu[s] else "ECHEC"
            print("        %-14s attendu=%-16s vu=%-16s %s"
                  % (s, attendu[s], verdicts.get(s, "(absent)"), marque))
        if bon:
            print("        -> la RELOCATION integrale (+0x%x) n'a produit AUCUN faux positif,"
                  % dec)
            print("           et le seul corps reellement change est le seul signale.")
    print("   => %s\n" % ("SCENARIO TENU DE BOUT EN BOUT" if ok else "SCENARIO ROMPU"))
    return ok


def etage6_depot_reel() -> bool | None:
    """Les archives REELLEMENT presentes dans ce checkout sont-elles exploitables ?

    NON MESURE s'il n'y en a aucune -- un vert rendu sur un corpus vide dirait <<les archives
    vont bien>> alors qu'il n'y en a pas. Le vice que ce depot a deja paye plusieurs fois.
    """
    print("-- ETAGE 6 : les archives du depot COURANT sont lisibles et appariables --")
    inv = [e for e in A.inventaire() if e.etat == A.ARCHIVEE]
    if not inv:
        print("   NON MESURE : aucune archive dans ce checkout (rien a confronter)\n")
        return None
    ok = True
    tables = {}
    for e in inv:
        entete, lignes = F.lire_tsv(A.archive_path(e.build))
        bon = (entete.get("build") == e.build and len(lignes) == e.fonctions
               and entete.get("sha256"))
        ok &= bool(bon)
        tables[e.build] = lignes
        print("   %-12s %6d lignes, en-tete annonce %s, sha256 %s  %s"
              % (e.build, len(lignes), entete.get("fonctions"),
                 "present" if entete.get("sha256") else "ABSENT", "OK " if bon else "ECHEC"))
    if len(tables) >= 2:
        (na, la), (nb, lb) = sorted(tables.items())[:2]
        _ia, _ib, communs, _x, _y = F.apparier(la, lb)
        bon = len(communs) > 0
        ok &= bon
        print("   appariement %s <-> %s : %d symboles communs  %s"
              % (na, nb, len(communs), "OK " if bon else "ECHEC (0 commun : forme incompatible)"))
    else:
        print("   un seul build archive : appariement inter-build NON MESURE")
    print("   => %s\n" % ("EXPLOITABLES" if ok else "INEXPLOITABLES"))
    return ok


def etage7_contre_epreuve() -> bool:
    """La garde elle-meme est-elle EPROUVEE ? On casse le CAPTEUR, les etages doivent tomber.

    Les etages 1 a 5 mutent l'OBJET OBSERVE (une archive, un repertoire). Celui-ci mute
    l'OBSERVATEUR -- c'est la seule facon de savoir si un 6/6 vert prouve quelque chose. Un
    probe qui reste vert quand son capteur est casse est un faux vert, et c'est le mode de
    panne le plus courant d'un garde-fou.

    L'exigence n'est PAS <<au moins un etage tombe>> : c'est <<EXACTEMENT les etages vises>>.
    Une garde qui rougit partout sur n'importe quelle mutation n'attribue rien -- elle
    signalerait sans jamais dire ou regarder, et le premier diagnostic partirait de travers.

    Ce cran vit DANS le probe, et pas dans un script jetable : une contre-epreuve qu'il faut
    penser a relancer n'est rejouee ni apres un rebase ni par un relecteur.
    """
    import io
    from contextlib import redirect_stdout

    print("-- ETAGE 7 : CONTRE-EPREUVE -- casser le capteur doit faire ROUGIR la garde --")

    def jouer(libelle, muter, restaurer, vises):
        muter()
        try:
            with redirect_stdout(io.StringIO()):
                res = {"1": etage1_discrimination(), "2": etage2_mutants_entete(),
                       "3": etage3_tri_etat(), "4": etage4_garde_reagit(),
                       "5": etage5_simulation()}
        finally:
            restaurer()
        tombes = sorted(k for k, v in res.items() if v is False)
        bon = tombes == sorted(vises)
        print("   %-44s tombes=%-8s vises=%-8s %s"
              % (libelle, ",".join(tombes) or "AUCUN", ",".join(sorted(vises)),
                 "OK " if bon else "ECHEC"))
        return bon

    ok = True
    vrai_dll, vrai_sha = A.dll_present, A._sha_attendu
    vrai_orph, vrai_etat, vrai_axe = A.projets_orphelins, A.etat_archive, S.axe6_archive_empreinte

    def _laxiste(b, courant=False):
        e = vrai_etat(b, courant)
        if e.etat == A.DISCORDANTE:
            e.etat = A.ARCHIVEE
        return e

    ok &= jouer("dll_present : None -> False (LE vice vise)",
                lambda: setattr(A, "dll_present", lambda b: bool(vrai_dll(b))),
                lambda: setattr(A, "dll_present", vrai_dll), ["3"])
    ok &= jouer("projets_orphelins : None -> []",
                lambda: setattr(A, "projets_orphelins", lambda: vrai_orph() or []),
                lambda: setattr(A, "projets_orphelins", vrai_orph), ["3"])
    ok &= jouer("_sha_attendu muet (plus de controle croise)",
                lambda: setattr(A, "_sha_attendu", lambda b: None),
                lambda: setattr(A, "_sha_attendu", vrai_sha), ["2"])
    ok &= jouer("axe6 ne leve plus (garde decorative)",
                lambda: setattr(S, "axe6_archive_empreinte",
                                lambda: (["  OK  tout va bien"], True)),
                lambda: setattr(S, "axe6_archive_empreinte", vrai_axe), ["4"])
    ok &= jouer("DISCORDANTE rabattu sur ARCHIVEE",
                lambda: setattr(A, "etat_archive", _laxiste),
                lambda: setattr(A, "etat_archive", vrai_etat), ["1", "2", "4"])

    print("   => %s\n" % ("LA GARDE DISCRIMINE" if ok
                          else "FAUX VERT -- elle survit a un capteur casse"))
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args(argv)

    print("=" * 78)
    print("GARDE #482-r3 -- archivage de l'empreinte structurelle")
    print("=" * 78)
    resultats = {
        "1 discrimination": etage1_discrimination(),
        "2 mutants en-tete": etage2_mutants_entete(),
        "3 tri-etat": etage3_tri_etat(),
        "4 la garde reagit": etage4_garde_reagit(),
        "5 simulation bout en bout": etage5_simulation(),
        "6 depot reel": etage6_depot_reel(),
        "7 contre-epreuve": etage7_contre_epreuve(),
    }
    print("=" * 78)
    echecs = [k for k, v in resultats.items() if v is False]
    non_mesures = [k for k, v in resultats.items() if v is None]
    for k, v in resultats.items():
        print("  %-28s %s" % (k, {True: "OK", False: "ECHEC", None: "NON MESURE"}[v]))
    if non_mesures:
        print("\n  NON MESURE (jamais rabattu sur un vert) : %s" % ", ".join(non_mesures))
    if echecs:
        print("\nRESULTAT: ECHEC sur %s" % ", ".join(echecs))
        return 1
    print("\nRESULTAT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
