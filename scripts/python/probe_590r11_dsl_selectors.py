#!/usr/bin/env python
"""Probe #590-r11 -- les selecteurs PARTAGES de `IdunBattleLogic.Entities.DSLSelectors`.

CE QUE LE RESIDU DISAIT, ET CE QUI ETAIT FAUX. Il annoncait << le NOM des selecteurs partages
n'est lisible par AUCUNE voie offline >> et reclamait un capteur. C'est faux : le RPC `classFields`
rend le nom de CHAMP de chaque slot, en lecture pure de la metadata IL2CPP -- aucun hook, aucun
reinject. La lecture STRUCTURELLE du port (chaque site contraint son slot par l'usage) etait juste
a 5 identifications sur 6 ; la sixieme etait FAUSSE -- le port ecrivait `It@+0x68`, le champ
s'appelle **`ActiveTarget`**.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UNE TABLE. Une inversion de deux slots au prochain build
serait SILENCIEUSE : le port continuerait de citer `Owner@+0x30` sur un slot devenu autre chose, et
rien ne rougirait. Ce probe a donc DEUX etages, et le second est OFFLINE (jouable sans le jeu) :

  1. `--regenerer` -- (re)ecrit `data/symbols/<build>/metadata/dsl_selectors.tsv` depuis le RPC
     `classFields`. Exige le jeu + la session Frida.
  2. defaut, 100 % OFFLINE -- confronte la table VERSIONNEE aux CITATIONS ecrites dans
     `scripts/python/**` (`<Nom>@[<][DSLSelectors|Sel]+0xNN[>]`). Une citation dont le nom ne
     correspond pas au champ du slot est INCOHERENTE.

⚠ LA BASE ATTESTEE N'EST PAS UNE LISTE BLANCHE DE FICHIERS -- c'est un plafond PAR COUPLE
`(fichier, nom, offset)`, qui ne doit que DECROITRE. Un fichier deja liste ne devient donc pas
aveugle : y ajouter une citation incoherente DE PLUS fait rougir. Elle existe parce que les 25
modules du rayon sont tenus par plusieurs agents en parallele et qu'un sweep de masse sur des
fichiers partages est precisement ce que la doctrine interdit.

⚠ CE QUE CE PROBE NE VOIT PAS, et il le DIT : un site qui cite un slot SANS ecrire de nom devant
(`<sel+0x40>` nu) n'est pas apparie -- il est compte a part et imprime. Un zero de la colonne
<< citations visitees >> ferait donc un vert-sur-rien : le probe ASSERTIONNE son propre non-vide.

ASCII only. Usage (depuis `scripts/python`) :
    python probe_590r11_dsl_selectors.py                # cliquet OFFLINE (rc 0/1)
    python probe_590r11_dsl_selectors.py --report       # inventaire, ne rougit jamais
    python probe_590r11_dsl_selectors.py --regenerer    # LIVE : refait le TSV + le confronte
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
RACINE = PYDIR.parent.parent

NS = "IdunBattleLogic.Entities"
CLS = "DSLSelectors"

#: Base ATTESTEE : plafond du nombre de citations INCOHERENTES par (fichier, nom, offset).
#: Ne doit que DECROITRE. Un couple absent d'ici vaut plafond 0.
BASE = RACINE / "scripts" / "ratchets-590r11-citations-heritees.json"

#: ⚠ LE DECLENCHEUR EST ETROIT PAR NECESSITE, ET LA MESURE LE DIT. Un premier jet appariait
#: `<Nom>@[+]0xNN` sans exiger de marqueur de struct : il a rendu **plus de 60** << incoherences >>
#: dont la quasi-totalite etaient FAUSSES (`UtilityAttackCase@0x28`, `config@0x60`,
#: `NormalAttackType@0x28`, ...) -- tout struct du build a un `+0x30`, donc l'offset SEUL ne
#: designe rien. Un cliquet a ce taux de faux positifs se fait desarmer. Ce qui etablit qu'une
#: citation designe CE struct-la, c'est le MARQUEUR ecrit au site.
#:
#: `<Nom>@[<]{DSLSelectors|Sel}+0xNN[>]` -- la forme MARQUEE.
CITATION = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)@<?(?:DSLSelectors|Sel)\+?(0x[0-9a-fA-F]{2})\b>?")

#: `sel@0xNN <Nom>` -- la forme ou le nom SUIT le slot (probes #462).
CITATION_POSTFIXE = re.compile(r"\bsel@(0x[0-9a-fA-F]{2})\s+([A-Za-z_][A-Za-z0-9_]*)")

#: L'ALIAS HERITE, seul nom que le port ait invente : `It`. Il n'est champ d'AUCUN struct du build,
#: donc un `It@...0xNN` ne peut designer que le slot DSLSelectors -- pas d'ambiguite, marqueur ou
#: pas. C'est EXACTEMENT le defaut que #590-r11 nomme, et le seul appariement non marque qu'on
#: s'autorise. Les formes MARQUEES (`It@<DSLSelectors+0x68>`) sont deja prises par `CITATION` --
#: ce motif-ci ne vise QUE les nues, sinon la meme citation serait comptee deux fois.
ALIAS_HERITE = re.compile(r"\bIt@\+?(0x[0-9a-fA-F]{2})\b")

#: Un slot CITE sans nom NI marqueur : `<DSLSelectors+0xNN>` nu. Compte, jamais apparie.
SANS_NOM = re.compile(r"(?<![A-Za-z0-9_])<(?:DSLSelectors|Sel)\+(0x[0-9a-fA-F]{2})>")

#: Les champs PRIVES portent le nom de backing du compilateur ; le port cite la forme publique.
#: Ces alias sont LUS de la table elle-meme (`_allTiles` -> `AllTiles`), pas inventes : le seul
#: geste est de retirer le `_` de tete. Aucun autre assouplissement -- surtout pas de comparaison
#: laxiste, qui rendrait le cliquet vacant.
def _normaliser(nom: str) -> str:
    return nom.lstrip("_").lower()


def chemin_tsv(build: str) -> Path:
    # Foyer UNIQUE du << quel build fait foi >> (`data/symbols/CURRENT`) : on ne re-derive
    # surtout pas la regle ici -- un second devineur qui choisit un AUTRE build ferait
    # confronter le port a une table etrangere, et le cliquet rougirait pour rien.
    from symbols_layout import build_dir
    return build_dir(build) / "metadata" / "dsl_selectors.tsv"


def lire_table(build: str) -> dict:
    """{offset_int: nom} depuis le TSV VERSIONNE."""
    p = chemin_tsv(build)
    if not p.is_file():
        raise SystemExit("[590-r11] table absente : %s -- la (re)generer avec --regenerer" % p)
    table = {}
    for ligne in p.read_text(encoding="utf-8").splitlines():
        if not ligne or ligne.startswith("#"):
            continue
        col = ligne.split("\t")
        if len(col) >= 2:
            table[int(col[0], 16)] = col[1]
    return table


def regenerer(build: str) -> dict:
    """LIVE -- `classFields(IdunBattleLogic.Entities, DSLSelectors)`, lecture pure."""
    import rl_duel as R
    sid = R._resolve_session()
    res = R._rpc(sid, "classFields", [NS, CLS], timeout=30).get("result") or {}
    if not res.get("ok"):
        raise SystemExit("[590-r11] classFields(%s, %s) : %s" % (NS, CLS, res.get("err")))
    champs = res.get("fields") or []
    if not champs:
        raise SystemExit("[590-r11] classFields rend 0 champ -- refus d'ecrire une table VIDE")
    lignes = []
    for f in champs:
        nom = f["name"]
        if nom.startswith("<") and nom.endswith(">k__BackingField"):
            nom = nom[1:-len(">k__BackingField")]
        lignes.append((int(f["offset"]), nom, f.get("type") or "", f.get("declaredBy") or ""))
    p = chemin_tsv(build)
    entete = [l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("#")] \
        if p.is_file() else ["#offset\tnom\ttype\tdeclaredBy"]
    corps = ["0x%x\t%s\t%s\t%s" % t for t in lignes]
    p.write_text("\n".join(entete + corps) + "\n", encoding="utf-8")
    print("[590-r11] %s reecrit : %d champ(s), boxedSize=%s fieldsSize=%s"
          % (p, len(lignes), res.get("boxedSize"), res.get("fieldsSize")))
    return {o: n for o, n, _t, _d in lignes}


def _fichiers():
    for p in sorted(PYDIR.rglob("*.py")):
        if p.name == Path(__file__).name:
            continue
        yield p


def confronter(table: dict) -> tuple:
    """Rend (coherentes, incoherentes, sans_nom, hors_table)."""
    coherentes, incoherentes, sans_nom, hors_table = 0, [], 0, 0
    attendu = {off: _normaliser(nom) for off, nom in table.items()}
    for p in _fichiers():
        rel = p.relative_to(RACINE).as_posix()
        try:
            texte = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        paires = [(m.group(1), m.group(2)) for m in CITATION.finditer(texte)]
        paires += [(m.group(2), m.group(1)) for m in CITATION_POSTFIXE.finditer(texte)]
        paires += [("It", m.group(1)) for m in ALIAS_HERITE.finditer(texte)]
        for nom, off_hex in paires:
            off = int(off_hex, 16)
            if off not in attendu:
                hors_table += 1          # `Self@0x148`, `Targets@0x190`, ... : pas un slot DSLSelectors
                continue
            if _normaliser(nom) == attendu[off]:
                coherentes += 1
            else:
                incoherentes.append((rel, nom, off_hex, table[off]))
        sans_nom += len(SANS_NOM.findall(texte))
    return coherentes, incoherentes, sans_nom, hors_table


def _base_attestee() -> dict:
    if not BASE.is_file():
        return {}
    d = json.loads(BASE.read_text(encoding="utf-8"))
    return {tuple(k.split("|")): int(v) for k, v in (d.get("plafonds") or {}).items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--regenerer", action="store_true", help="LIVE : refait le TSV depuis classFields")
    ap.add_argument("--report", action="store_true", help="inventaire seul, rc toujours 0")
    ap.add_argument("--ecrire-base", action="store_true",
                    help="reecrit la base attestee depuis l'etat COURANT (a n'utiliser qu'en baisse)")
    a = ap.parse_args(argv)

    from symbols_layout import LayoutError, current_build
    try:
        build = current_build()
    except LayoutError as exc:
        # PAS MESURE != vide : on ne devine pas un build, on le DIT (rc 99, jamais un vert).
        print("[590-r11] build indetermine : %s" % exc)
        return 99
    table = regenerer(build) if a.regenerer else lire_table(build)

    print("[590-r11] build %s -- %d slot(s) dans la table VERSIONNEE" % (build, len(table)))
    for off in sorted(table):
        print("    +0x%-4x %s" % (off, table[off]))

    coherentes, incoherentes, sans_nom, hors_table = confronter(table)
    print("\n[590-r11] citations VISITEES sous scripts/python : %d coherente(s), %d incoherente(s)"
          % (coherentes, len(incoherentes)))
    print("[590-r11] NON APPARIEES (comptees, pas jugees) : %d slot cite SANS nom devant, "
          "%d offset hors table (Self@0x148, Targets@0x190, ...)" % (sans_nom, hors_table))

    # Un recenseur qui ne visite RIEN rendrait 0 incoherence et passerait pour vert.
    if coherentes + len(incoherentes) == 0:
        print("[590-r11] FAIL -- AUCUNE citation visitee : le recenseur ne mesure rien")
        return 1

    # ---- LES DEUX ETAGES, ET POURQUOI UN SEUL BLOQUE -------------------------------------------
    # BLOQUANT : l'alias `It`, le seul nom que le port ait INVENTE. Il n'est champ d'aucun struct
    #   du build, il designe toujours `ActiveTarget`, et c'est nommement le defaut de #590-r11.
    # INVENTAIRE : tous les autres desaccords nom/slot. Ils melangent des ALIAS LEGITIMES du
    #   vocabulaire du port (`Subject()` est le noeud DSL de l'element courant, `EffectSelf` celui
    #   de `Effect`, `AllUnits` celui de `_allAliveUnits`) et de VRAIS glissements
    #   (`ActiveTarget@0x48` alors que `0x48` est `Caster`). Les trier exige de lire chaque site
    #   un par un, sur 25 modules tenus par plusieurs agents -- c'est le residu ouvert par cette
    #   tranche, pas son livrable. Un critere BLOQUANT qui rougirait sur des alias legitimes se
    #   ferait desarmer (meme lecon que le premier jet, cf. `CITATION` ci-dessus).
    bloquantes = [t for t in incoherentes if t[1] == "It"]
    inventaire = [t for t in incoherentes if t[1] != "It"]

    inv_par_couple: dict = {}
    for rel, nom, off_hex, attendu in inventaire:
        inv_par_couple.setdefault((rel, nom, off_hex), []).append(attendu)
    print("\n[590-r11] INVENTAIRE (jamais bloquant) -- %d couple(s) nom/slot en desaccord, alias "
          "LEGITIMES du port et glissements REELS confondus :" % len(inv_par_couple))
    for (rel, nom, off_hex), att in sorted(inv_par_couple.items()):
        print("    %s : `%s@%s` -> slot `%s` (x%d)" % (rel, nom, off_hex, att[0], len(att)))

    print("\n[590-r11] BLOQUANT -- l'alias herite `It` :")
    plafonds = _base_attestee()
    par_couple: dict = {}
    for rel, nom, off_hex, attendu in bloquantes:
        par_couple.setdefault((rel, nom, off_hex), []).append(attendu)

    if a.ecrire_base:
        BASE.write_text(json.dumps(
            {"_commentaire": "Plafond du nombre de citations INCOHERENTES par (fichier|nom|offset). "
                             "Ne doit que DECROITRE. Genere par probe_590r11_dsl_selectors.py "
                             "--ecrire-base ; cf. #590-r11.",
             "plafonds": {"|".join(k): len(v) for k, v in sorted(par_couple.items())}},
            indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
        print("[590-r11] base attestee reecrite : %s (%d couple(s))" % (BASE, len(par_couple)))
        return 0

    neufs = []
    for couple, attendus in sorted(par_couple.items()):
        plafond = plafonds.get(couple, 0)
        etat = "ATTESTE" if len(attendus) <= plafond else "NEUF"
        print("    [%s] %s : `%s@%s` -- le slot s'appelle `%s` (x%d, plafond %d)"
              % (etat, couple[0], couple[1], couple[2], attendus[0], len(attendus), plafond))
        if len(attendus) > plafond:
            neufs.append(couple)

    if not par_couple:
        print("    (aucune)")
    if a.report:
        return 0
    if neufs:
        print("\n[590-r11] FAIL -- %d couple(s) `It@0xNN` au-dessus de leur plafond atteste."
              % len(neufs))
        return 1
    print("\n[590-r11] PASS -- aucun `It@0xNN` NEUF (l'inventaire ci-dessus ne bloque pas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
