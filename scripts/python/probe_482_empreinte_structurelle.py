#!/usr/bin/env python3
"""Garde de l'empreinte structurelle (#482) : elle doit etre AVEUGLE a la relocation et
SENSIBLE au changement de corps. Les deux bornes, mesurees -- pas l'une sans l'autre.

POURQUOI LES DEUX BORNES
------------------------
Une empreinte qui rougit sur tout ne vaut rien : entre deux builds le layout est entierement
reorganise, donc un hash naif des octets rend <<100 % change>>. Une empreinte qui ne rougit
jamais ne vaut rien non plus : un capteur muet se lit comme une bonne nouvelle. Cette garde
mesure donc separement :

  ETAGE 1  FAUX POSITIF -- meme corps, layout different  => l'empreinte doit etre IDENTIQUE
  ETAGE 2  FAUX NEGATIF -- corps mute                    => l'empreinte doit CHANGER
  ETAGE 3  LIMITE ASSUMEE -- une ref de DONNEE qui change => l'empreinte NE bouge PAS.
           Ce n'est pas un echec : c'est le trou connu de la methode, et on le MESURE au lieu
           de le taire. Il rougit seulement s'il s'AGGRANDIT (une autre famille devient
           invisible).
  ETAGE 4  Le diff d'un build avec LUI-MEME rend zero changement.
  ETAGE 5  SYMETRIE DES CHAINES : les octets lus depuis le PE et depuis Ghidra sont les memes.
           C'est la condition de validite de toute comparaison entre un build courant (PE) et
           un build archive (projet Ghidra). Si ghidra-mcp est injoignable, l'etage se declare
           NON MESURE -- il ne se rabat pas sur un vert.

`a_mordu` EST SEPARE DU VERDICT : un mutant qui ne modifie aucun octet rendrait <<empreinte
inchangee>> et se lirait comme un echec de l'empreinte, alors que c'est le MUTANT qui est
casse. Chaque mutation verifie donc d'abord qu'elle a bien mordu.

USAGE
    python probe_482_empreinte_structurelle.py
    python probe_482_empreinte_structurelle.py --sans-mcp     # saute l'etage 5
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fingerprint_functions as F  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# Une adresse de DONNEE : hors de tout segment executable, donc reduite au meme jeton quelle
# que soit sa valeur. C'est le trou mesure par l'etage 3.
VA_DATA_A = 0x183100000
VA_DATA_B = 0x183200000


def corps_temoin(va_f: int, va_g: int, va_data: int) -> bytes:
    """Un corps de fonction SYNTHETIQUE contenant un panel representatif de ce qui doit etre
    neutralise ou conserve. Ecrit a la main pour que chaque octet soit connu et mutable.

      off  taille  instruction                        role dans le test
      ---  ------  ---------------------------------  ---------------------------------
        0     4     sub rsp, 0x28                      instruction pure
        4     6     mov eax, dword ptr [rcx + 0xa8]    offset de struct -> CONSERVE
       10     5     cmp eax, 0x539                     constante de formule -> CONSERVE
       15     6     jl +12 (interne)                   saut interne -> delta CONSERVE
       21     7     lea rcx, [rip + d]  -> donnee      ref DONNEE -> neutralisee
       28     5     call G                             ref CODE -> neutralisee + empreinte
       33     4     add rsp, 0x28
       37     1     ret                                terminal
    """
    b = bytearray()
    b += bytes.fromhex("4883EC28")                             # sub rsp, 0x28
    b += bytes.fromhex("8B81A8000000")                         # mov eax, [rcx+0xa8]
    b += bytes.fromhex("3D39050000")                           # cmp eax, 0x539
    b += bytes.fromhex("0F8C") + struct.pack("<i", 12)         # jl -> offset 33
    b += bytes.fromhex("488D0D") + struct.pack("<i", va_data - (va_f + 28))   # lea rcx,[rip+d]
    b += b"\xE8" + struct.pack("<i", va_g - (va_f + 33))       # call G
    b += bytes.fromhex("4883C428")                             # add rsp, 0x28
    b += b"\xC3"                                               # ret
    assert len(b) == 38, len(b)
    return bytes(b)


CORPS_G = bytes.fromhex("8B4110C3")          # mov eax,[rcx+0x10] ; ret


def image_synthetique(va_f, va_g, va_data, corps_f=None):
    """Une image d'un seul segment executable contenant F et G aux adresses demandees."""
    base = 0x180001000
    fin = 0x180200000
    data = bytearray(b"\xcc" * (fin - base))
    cf = corps_f if corps_f is not None else corps_temoin(va_f, va_g, va_data)
    data[va_f - base: va_f - base + len(cf)] = cf
    data[va_g - base: va_g - base + len(CORPS_G)] = CORPS_G
    image = F.ImageCode([(base, fin, "il2cpp", bytes(data))], 0x180000000, "synthetique")
    entrees = sorted([(va_f, "F"), (va_g, "G")])
    return image, entrees, dict(entrees)


def empreinte_de(va_f, va_g, va_data, corps_f=None):
    image, entrees, par_va = image_synthetique(va_f, va_g, va_data, corps_f)
    res = F.empreinter_build("test", image, entrees, par_va, verbose=False)
    return {r["sym"]: r for r in res}["F"]


# ===========================================================================
def etage1_invariance():
    """FAUX POSITIF : le meme corps, place ailleurs et appelant une cible placee ailleurs,
    doit rendre exactement la meme empreinte."""
    print("-- ETAGE 1 : invariance a la RELOCATION (faux positif) --")
    cas = [
        ("reference (F@0x180002000, G@0x180003000)", 0x180002000, 0x180003000, VA_DATA_A),
        ("module rebase   (tout decale de +0x40000)", 0x180042000, 0x180043000, VA_DATA_A),
        ("REORDONNANCE    (G eloigne : delta du call change)", 0x180002000, 0x180090000, VA_DATA_A),
        ("REORDONNANCE    (G avant F : delta NEGATIF)", 0x180080000, 0x180010000, VA_DATA_A),
    ]
    ref = None
    octets = {}
    ok = True
    for libelle, vf, vg, vd in cas:
        e = empreinte_de(vf, vg, vd)
        octets[libelle] = corps_temoin(vf, vg, vd)
        if ref is None:
            ref = e
            print("   %-52s h_local=%s  (reference)" % (libelle, e["h_local"]))
            continue
        # a_mordu : la relocation doit avoir REELLEMENT change les octets, sinon le test
        # ne prouve rien (on comparerait deux fois le meme buffer).
        a_mordu = octets[libelle] != octets[cas[0][0]]
        egal = (e["h_local"] == ref["h_local"] and e["h_body"] == ref["h_body"])
        etat = "OK " if (egal and a_mordu) else "ECHEC"
        if not (egal and a_mordu):
            ok = False
        print("   %-52s h_local=%s  octets_differents=%s  %s"
              % (libelle, e["h_local"], a_mordu, etat))
    print("   => %s\n" % ("INVARIANTE" if ok else "PAS INVARIANTE -- faux positifs"))
    return ok


def etage2_mutants():
    """FAUX NEGATIF : chaque mutation du corps doit faire bouger l'empreinte."""
    print("-- ETAGE 2 : sensibilite aux MUTATIONS du corps (faux negatif) --")
    vf, vg, vd = 0x180002000, 0x180003000, VA_DATA_A
    base = corps_temoin(vf, vg, vd)
    ref = empreinte_de(vf, vg, vd)

    def muter(octets, pos, remplacement):
        b = bytearray(octets)
        b[pos:pos + len(remplacement)] = remplacement
        return bytes(b)

    mutants = [
        # (libelle, corps mute, couche qui DOIT reagir)
        ("constante 0x539 -> 0x53a",
         muter(base, 11, struct.pack("<i", 0x53A)), "h_imm"),
        ("offset de struct 0xa8 -> 0xb0",
         muter(base, 6, struct.pack("<i", 0xB0)), "h_imm"),
        ("opcode : add rsp,0x28 -> 4 nops",
         muter(base, 33, b"\x90\x90\x90\x90"), "h_mnem"),
        ("registre : mov eax,[rcx+..] -> mov eax,[rdx+..]",
         muter(base, 5, b"\x82"), "h_local"),
        ("saut interne : jl +12 -> jl +13 (cible decalee)",
         muter(base, 17, struct.pack("<i", 13)), "h_local"),
    ]
    ok = True
    for libelle, corps, couche in mutants:
        a_mordu = corps != base
        e = empreinte_de(vf, vg, vd, corps_f=corps)
        bouge_local = e["h_local"] != ref["h_local"]
        bouge_couche = e[couche] != ref[couche]
        bon = a_mordu and bouge_local and bouge_couche
        if not bon:
            ok = False
        print("   %-50s a_mordu=%-5s h_local_bouge=%-5s %s_bouge=%-5s %s"
              % (libelle, a_mordu, bouge_local, couche, bouge_couche,
                 "OK " if bon else "ECHEC"))

    # La cible d'appel : elle ne doit PAS bouger h_local (le corps propre est le meme),
    # mais elle DOIT bouger h_body (la fonction appelee n'est plus la meme).
    print("   -- cas particulier : changer la CIBLE d'un appel --")
    vg2 = 0x180004000
    image, entrees, par_va = image_synthetique(vf, vg2, vd)
    # On donne a la nouvelle cible un corps DIFFERENT, sinon appeler l'une ou l'autre est
    # sans consequence observable -- et l'empreinte aurait RAISON de ne pas bouger.
    seg = list(image.segments[0])
    d = bytearray(seg[3])
    d[vg2 - seg[0]: vg2 - seg[0] + 6] = bytes.fromhex("B82A000000C3")   # mov eax,42 ; ret
    seg[3] = bytes(d)
    image2 = F.ImageCode([tuple(seg)], 0x180000000, "synthetique")
    e2 = {r["sym"]: r for r in F.empreinter_build("test", image2, entrees, par_va,
                                                  verbose=False)}["F"]
    local_stable = e2["h_local"] == ref["h_local"]
    body_bouge = e2["h_body"] != ref["h_body"]
    bon = local_stable and body_bouge
    if not bon:
        ok = False
    print("   %-50s h_local_stable=%-5s h_body_bouge=%-5s %s"
          % ("appel vers une cible au corps different", local_stable, body_bouge,
             "OK " if bon else "ECHEC"))
    print("   => %s\n" % ("SENSIBLE" if ok else "AVEUGLE a une mutation -- faux negatifs"))
    return ok


def etage3_limite_data():
    """LIMITE ASSUMEE, mesuree et non tue : une reference vers une DONNEE differente ne
    change pas l'empreinte. On ne peut pas la nommer -- `functions.tsv` ne contient que des
    fonctions, et il n'existe pas de table de symboles de donnees par build."""
    print("-- ETAGE 3 : LIMITE CONNUE -- une reference de DONNEE est invisible --")
    vf, vg = 0x180002000, 0x180003000
    a = corps_temoin(vf, vg, VA_DATA_A)
    b = corps_temoin(vf, vg, VA_DATA_B)
    a_mordu = a != b
    ea = empreinte_de(vf, vg, VA_DATA_A)
    eb = empreinte_de(vf, vg, VA_DATA_B, corps_f=b)
    invisible = ea["h_local"] == eb["h_local"]
    print("   octets differents (a_mordu) : %s" % a_mordu)
    print("   empreinte identique         : %s" % invisible)
    print("   => %s\n" % ("LIMITE CONFIRMEE, inchangee (0x%x vs 0x%x indiscernables)"
                          % (VA_DATA_A, VA_DATA_B) if (a_mordu and invisible)
                          else "LA LIMITE A CHANGE -- re-mesurer et re-documenter"))
    # Cet etage ne fait PAS echouer la garde : il documente. Il rougit si la limite bouge.
    return a_mordu and invisible


def etage4_autodiff(chemin):
    """Un build compare a LUI-MEME ne doit rendre aucun changement."""
    print("-- ETAGE 4 : diff d'un build avec lui-meme --")
    p = Path(chemin)
    if not p.exists():
        print("   NON MESURE : %s absent (lancer `empreinte` d'abord)\n" % p)
        return None
    _e, lignes = F.lire_tsv(p)
    ia, ib, communs, _aa, _ab = F.apparier(lignes, lignes)
    n_change = sum(1 for s in communs if F.classifier(ia[s], ib[s])[0] != "IDENTIQUE")
    ok = n_change == 0
    print("   %d symboles apparies, %d changements  %s\n"
          % (len(communs), n_change, "OK " if ok else "ECHEC"))
    return ok


def etage5_symetrie(pe_path):
    """Les octets lus par pefile et par Ghidra doivent etre IDENTIQUES.

    C'est la condition de validite d'une comparaison PE (build courant) vs projet Ghidra
    (build archive). Sans elle, un ecart mesure pourrait venir de la chaine d'extraction
    et non du jeu.
    """
    print("-- ETAGE 5 : symetrie des chaines d'extraction (PE vs Ghidra) --")
    import json
    import urllib.error
    import urllib.request

    build = (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    pe = Path(pe_path)
    if not pe.exists():
        print("   NON MESURE : %s absent\n" % pe)
        return None
    try:
        image = F.charger_depuis_pe(pe)
        entrees, _ = F.charger_functions_tsv(build)
    except SystemExit as exc:
        print("   NON MESURE : %s\n" % exc)
        return None

    url = "http://127.0.0.1:13337/mcp"
    hdrs = {"Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"}
    session = [None]

    def appel(nom, args):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": nom, "arguments": args}}
        h = dict(hdrs)
        if session[0]:
            h["Mcp-Session-Id"] = session[0]
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            if not session[0]:
                session[0] = r.headers.get("Mcp-Session-Id")
            txt = r.read().decode("utf-8", "replace")
        for ligne in txt.splitlines():
            if ligne.startswith("data: "):
                txt = ligne[6:]
        return json.loads(txt)

    # Initialisation MCP (obligatoire avant tout tools/call).
    try:
        init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "probe482", "version": "1"}}}
        req = urllib.request.Request(url, data=json.dumps(init).encode(),
                                     headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            session[0] = r.headers.get("Mcp-Session-Id")
            r.read()
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        h = dict(hdrs)
        h["Mcp-Session-Id"] = session[0]
        urllib.request.urlopen(urllib.request.Request(
            url, data=json.dumps(notif).encode(), headers=h, method="POST"), timeout=20).read()
    except (urllib.error.URLError, OSError) as exc:
        print("   NON MESURE : ghidra-mcp injoignable (%s)" % exc)
        print("   -> l'etage ne se rabat PAS sur un vert : la symetrie reste NON VERIFIEE\n")
        return None

    # Sondes choisies par POSITION (deterministe), reparties sur tout l'espace d'adresses.
    n = len(entrees)
    positions = [1, n // 8, n // 4, n // 2, 3 * n // 4, 7 * n // 8, n - 3]
    accord = desaccord = 0
    for k in positions:
        va, sym = entrees[k]
        mien = image.octets(va, 32)
        try:
            rep = appel("read_bytes", {"binary_name": "GameAssembly.dll",
                                       "address": hex(va), "size": 32})
            contenu = rep["result"]["content"][0]["text"]
            sien = bytes.fromhex(json.loads(contenu)["data"])
        except Exception as exc:                                  # noqa: BLE001
            print("   %x  NON LU (%s)" % (va, str(exc)[:60]))
            continue
        if mien == sien:
            accord += 1
        else:
            desaccord += 1
            print("   %x  DESACCORD  pe=%s  ghidra=%s" % (va, mien.hex()[:32], sien.hex()[:32]))
    ok = desaccord == 0 and accord > 0
    print("   %d sondes en accord, %d en desaccord  %s\n"
          % (accord, desaccord, "OK " if ok else "ECHEC"))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sans-mcp", action="store_true", help="sauter l'etage 5")
    ap.add_argument("--empreinte", default=str(REPO / "logs" / "fingerprints" / "rnca9r7q6c.tsv"))
    ap.add_argument("--pe", default=r"C:\Users\nicolasv\AppData\Local\tacticus\games"
                                    r"\rnca9r7q6c\GameAssembly.dll")
    args = ap.parse_args(argv)

    print("=" * 78)
    print("GARDE #482 -- empreinte structurelle par fonction")
    print("=" * 78)
    resultats = {
        "1 invariance relocation": etage1_invariance(),
        "2 sensibilite mutations": etage2_mutants(),
        "3 limite ref donnee": etage3_limite_data(),
        "4 auto-diff": etage4_autodiff(args.empreinte),
    }
    if not args.sans_mcp:
        resultats["5 symetrie PE/Ghidra"] = etage5_symetrie(args.pe)

    print("=" * 78)
    echecs = [k for k, v in resultats.items() if v is False]
    non_mesures = [k for k, v in resultats.items() if v is None]
    for k, v in resultats.items():
        etat = {True: "OK", False: "ECHEC", None: "NON MESURE"}[v]
        print("  %-28s %s" % (k, etat))
    if non_mesures:
        print("\n  NON MESURE (jamais rabattu sur un vert) : %s" % ", ".join(non_mesures))
    if echecs:
        print("\nRESULTAT: ECHEC sur %s" % ", ".join(echecs))
        return 1
    print("\nRESULTAT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
