"""`#916-r1` / `#590-r2` -- DERIVATION des deux slots d'`IEffect` que le decompile ne nomme pas.

## Les deux residus, et la premisse COMMUNE qui est FAUSSE

Les deux disaient `BLOCAGE: capteur`, sur le meme motif : « le nom du slot est une valeur runtime
derriere la metadata IL2CPP, donc illisible statiquement ».

  * `#916-r1` -- `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect` consulte le
    **slot 5** de l'`IEffect` du type et SAUTE (`continue`) les instances pour lesquelles il rend
    vrai ; si aucune n'est retenue, l'appelant materialise une NOUVELLE entite-effet. Le residu
    affirmait que c'est « exactement la bifurcation que le port encode par
    `BaseEffect.stacks_stat_mod_on_add` ». **CE PROBE LE REFUTE** -- cf. l'encadre ci-dessous.
  * `#590-r2` -- `IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects` consulte le
    **slot 3** et met l'effet dans la liste de suppression quand il rend FAUX.

**Le NOM des deux slots est deja versionne dans le depot** :
`data/symbols/<build>/metadata/interface_slots.tsv` donne `IEffect 3 get_KeepOnChangeOwner 0` et
`IEffect 5 get_AlwaysCreateOneEntityPerEffect 0`. Aucun capteur n'etait requis pour NOMMER.

## Ce qui restait, et pourquoi ce probe n'exige pas de fenetre non plus

Restait la VALEUR par classe concrete -- « quels effets empilent ? », « lesquels survivent au
changement de proprietaire ? ». Les getters constants sont **dedupliques par IL2CPP** : un meme
corps `mov al,1 ; ret` sert des dizaines de classes, et `frida/methods.tsv` (indexee par ADRESSE)
n'en garde qu'UN proprietaire. Ghidra nomme donc ces corps d'apres une classe SANS RAPPORT --
mesure : le corps du `true` s'appelle `UnityEngine.U2D.IK.Solver2D$$DoValidate` et celui du `false`
`Stash.Native.StashNative$$get_IsPurchaseProcessing`. **Le nom du proprietaire n'est pas
l'identite ; seuls les OCTETS comptent.**

La derivation passe donc par la **vtable RUNTIME**, et le RPC qui la lit -- `resolveVtableSlot` --
**est deja charge dans la session**. On compare, classe par classe, la RVA installee au slot a
celle de `BaseEffect` :

  * RVA IDENTIQUE a celle de la base  -> la classe HERITE (valeur = celle de la base) ;
  * RVA DIFFERENTE                    -> la classe OVERRIDE, et sa RVA est publiee pour que le
                                        corps soit lu au decompile (une poignee de RVA distinctes).

⚠ **La vtable est CALIBREE, pas supposee.** `vtableStart` est cherche en balayant les offsets
jusqu'a trouver la signature invariante de `System.Object` (`Equals`, `Finalize`, `GetHashCode`,
`ToString` aux quatre premiers slots). L'ecrire en dur serait la faute de la RVA epinglee : juste
aujourd'hui, faux EN SILENCE au prochain build, et le symptome serait des noms de slots DECALES --
donc un verdict faux, pas une erreur. Le probe REFUSE de conclure si la calibration echoue.

⚠ **On ne resout PAS par `interfaceOffset`** : il se DERIVE de la calibration (position de `Init`,
slot 0 d'`IEffect`, dans la vtable plate), et on le VERIFIE en exigeant que le nom lu au slot
corresponde a celui qu'`interface_slots.tsv` annonce. Deux sources independantes qui doivent
concorder ; sinon, refus.

## ⚠ CE QUE LA MESURE A REFUTE : le slot 5 n'est PAS `stacks_stat_mod_on_add`

Le port pose `stacks_stat_mod_on_add = True` sur trois classes, chacune par une MESURE LIVE
distincte -- dont `ActOfFaithBuffEffect`, dont l'empilement additif est observe (`145 290 435 ...`
au lieu de `145 145 145 ...`). Or ce probe mesure que **`ActOfFaithBuffEffect` HERITE de la base**,
c'est-a-dire `get_AlwaysCreateOneEntityPerEffect == false`.

Les deux notions ne coincident donc pas, et le decompile dit pourquoi : quand
`UpdateExistingEffect` RETIENT une instance (slot 5 faux), elle ne se contente pas de rafraichir
une duree -- elle incremente le compteur de stacks `EffectComponent+0x6c` **et** ecrit
`statModifierValue` sur le composant. L'empilement d'`ActOfFaith` passe donc par CE chemin, pas par
la creation d'une seconde entite-effet. Le slot 5 signifie « une entite SEPAREE par application »
(le cas des taunts, des liens et des attaques en attente -- voir la liste des overrides), ce qui
est une AUTRE question.

⇒ **« Deriver le drapeau des classes d'effet au lieu de le poser a la main » aurait ecrit
`stacks_stat_mod_on_add = False` sur `ActOfFaith` et casse un comportement live-valide.** Ce probe
recense un fait natif utile ; il ne remplace PAS les mesures du port.

Lecture PURE : `resolveVtableSlot` ne fait que lire des pointeurs (aucun `Interceptor`, aucune
invocation, aucun heap scan).

⚠ **Le recensement est PARTIEL et le DIT.** IL2CPP ne remplit la vtable d'une classe qu'a son
INITIALISATION : une classe d'effet jamais instanciee dans la session rend des slots vides, et le
probe la range en `NON MESUREE` -- **jamais** en « herite ». Mesure du 2026-08-12 : 244 mesurees
sur 465. Compter les non-mesurees comme heritantes fabriquerait un faux « aucun override ».

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

#: Les deux slots en cause, LUS dans `metadata/interface_slots.tsv` (jamais ecrits de memoire).
SLOTS_VOULUS = {3: "get_KeepOnChangeOwner", 5: "get_AlwaysCreateOneEntityPerEffect"}
#: La signature invariante de `System.Object`, dans l'ordre des slots -- l'ancre de calibration.
OBJECT_SLOTS = ["Equals", "Finalize", "GetHashCode", "ToString"]
BASE_NS, BASE_CLS = "IdunBattle.Entities.Effects", "BaseEffect"


def _build() -> str:
    """Le build dont les DEUX tables necessaires existent.

    ⚠ `data/symbols/` porte PLUSIEURS builds (les anciens ne sont pas purges), et prendre le
    premier par ordre alphabetique rend `gqfc5mff6c` -- un build de mai, dont
    `metadata/interface_slots.tsv` n'existe meme pas. Un probe qui lirait une table d'un AUTRE
    build rendrait des noms de slots faux SANS erreur : c'est exactement le mode de panne que la
    section << Hash du build = identite du dump >> decrit. On exige donc les deux tables, et on
    prend le plus RECENT. Le build retenu est IMPRIME."""
    p = HERE.parent.parent / "data" / "symbols"
    cands = []
    for d in sorted(p.iterdir()):
        if not d.is_dir() or not (d / "BUILD").exists():
            continue
        if (d / "BUILD").read_text(encoding="utf-8").strip() != d.name:
            continue
        if (d / "metadata" / "interface_slots.tsv").exists() and (d / "frida" / "classes.tsv").exists():
            cands.append((d.stat().st_mtime, d.name))
    if not cands:
        raise SystemExit("aucun build sous data/symbols ne porte A LA FOIS "
                         "metadata/interface_slots.tsv et frida/classes.tsv")
    return sorted(cands)[-1][1]


def slots_attendus(build: str) -> dict:
    """`IEffect <slot> <nom> <arite>` depuis la table VERSIONNEE -- la source du NOM."""
    f = HERE.parent.parent / "data" / "symbols" / build / "metadata" / "interface_slots.tsv"
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) >= 3 and p[0] == "IEffect":
            try:
                out[int(p[1])] = p[2]
            except ValueError:
                continue
    return out


def classes_effet(build: str) -> list:
    """Les classes dont le PARENT est `BaseEffect` -- lues dans `frida/classes.tsv`.

    On prend le parent DIRECT : une classe d'effet concrete derive de `BaseEffect`. Les
    intermediaires eventuels sont recuperes par une seconde passe (leurs enfants pointent sur
    elles), donc la fermeture transitive est calculee, pas supposee."""
    f = HERE.parent.parent / "data" / "symbols" / build / "frida" / "classes.tsv"
    par = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) >= 3 and p[0] and p[2]:
            par[p[0]] = p[2]
    racine = BASE_NS + "." + BASE_CLS
    out, change = {racine}, True
    while change:
        change = False
        for k, v in par.items():
            if v in out and k not in out:
                out.add(k)
                change = True
    res = []
    for full in sorted(out):
        i = full.rfind(".")
        if i > 0:
            res.append((full[:i], full[i + 1:], full))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="0 = toutes les classes")
    ap.add_argument("--json", default=None, help="chemin de sortie JSON (hors data/)")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(m, body, timeout=90):
        r = R._rpc(sid, m, [body], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    build = _build()
    attendus = slots_attendus(build)
    print("== #916-r1 / #590-r2 -- les deux slots d'`IEffect`, DERIVES (build %s)" % build)
    print("")
    print("=== etape 0 -- le NOM des slots, LU dans la table VERSIONNEE ===")
    for s, nom in sorted(SLOTS_VOULUS.items()):
        vu = attendus.get(s)
        print("   slot %-2d attendu=%-38s table=%s  %s"
              % (s, nom, vu, "OK" if vu == nom else "DIVERGE"))
        if vu != nom:
            print("   La table du build ne porte PAS ce nom a ce slot. Rien n'est conclu : "
                  "c'est la table qui fait foi, pas la constante ecrite dans ce probe.")
            return 2

    def vtable(ns, cls):
        """La vtable CALIBREE d'une classe : les entrees ordonnees + l'offset de depart.

        ⚠ **Les DEUX PHASES sont balayees, et c'est indispensable.** `resolveVtableSlot` avance
        par pas de `0x10` depuis le `start` fourni : partir de `0x100` n'atteint jamais un offset
        congru a 8 modulo 0x10. Or la vtable de ce build commence a `klass+0x138` (LU dans le
        dispatch d'interface : `... * 0x10 + 0x138 + klass`), donc en phase `+8`. Un balayage
        mono-phase rendait << CALIBRATION IMPOSSIBLE >> sur une classe pourtant lisible -- un faux
        refus, mesure au premier jet. On essaie les deux et on garde celle qui porte la signature
        `System.Object` ; aucune des deux n'est ecrite comme la bonne."""
        par_off = {}
        for start in (0x100, 0x108):
            res = rpc("resolveVtableSlot", {"ns": ns, "cls": cls, "start": start, "end": 0x800})
            if not isinstance(res, dict) or not res.get("ok"):
                return None, (res or {}).get("error") if isinstance(res, dict) else "rpc KO"
            for s in (res.get("slots") or []):
                if s.get("off"):
                    par_off[int(s["off"], 16)] = s
        depart = None
        for off in sorted(par_off):
            noms = [(par_off.get(off + i * 0x10) or {}).get("method") for i in range(4)]
            if noms == OBJECT_SLOTS:
                depart = off
                break
        if depart is None:
            return None, "CALIBRATION IMPOSSIBLE (signature System.Object introuvable)"
        ordonnes = []
        off = depart
        while off in par_off:
            ordonnes.append(par_off[off])
            off += 0x10
        return {"depart": depart, "slots": ordonnes}, None

    print("")
    print("=== etape 1 -- la BASE (`%s.%s`) ===" % (BASE_NS, BASE_CLS))
    vt, err = vtable(BASE_NS, BASE_CLS)
    if vt is None:
        print("   REFUS : %s" % err)
        return 2
    print("   vtable calibree a l'offset 0x%x (signature System.Object aux slots 0..3)"
          % vt["depart"])
    # `Init` est le slot 0 d'`IEffect` : sa position dans la vtable plate EST l'interfaceOffset.
    noms_base = [s.get("method") for s in vt["slots"]]
    if attendus.get(0) not in noms_base:
        print("   REFUS : le slot 0 d'IEffect (`%s`) n'est pas dans la vtable de la base"
              % attendus.get(0))
        return 2
    iface_off = noms_base.index(attendus.get(0))
    print("   interfaceOffset(BaseEffect, IEffect) = %d (position de `%s`)"
          % (iface_off, attendus.get(0)))
    base_rva = {}
    for s, nom in sorted(SLOTS_VOULUS.items()):
        idx = iface_off + s
        if idx >= len(vt["slots"]):
            print("   REFUS : slot %d hors vtable" % s)
            return 2
        e = vt["slots"][idx]
        if e.get("method") != nom:
            print("   REFUS : a l'index %d la vtable porte `%s`, la table annonce `%s` -- les "
                  "deux sources DIVERGENT, on ne conclut pas." % (idx, e.get("method"), nom))
            return 2
        base_rva[s] = e.get("funcRVA")
        print("   slot %-2d %-38s rva=%-12s ghidraVA=%s"
              % (s, nom, e.get("funcRVA"), e.get("ghidraVA")))

    print("")
    print("=== etape 2 -- balayage des classes d'effet ===")
    cls = classes_effet(build)
    if a.limite:
        cls = cls[:a.limite]
    print("   %d classe(s) derivant de `BaseEffect` (fermeture transitive)" % len(cls))
    overrides = {3: {}, 5: {}}
    herite = {3: 0, 5: 0}
    echecs = []
    for i, (ns, cn, full) in enumerate(cls):
        if full == BASE_NS + "." + BASE_CLS:
            continue
        vt2, err2 = vtable(ns, cn)
        if vt2 is None:
            echecs.append((full, err2))
            continue
        noms2 = [s.get("method") for s in vt2["slots"]]
        if attendus.get(0) not in noms2:
            echecs.append((full, "slot 0 d'IEffect absent"))
            continue
        off2 = noms2.index(attendus.get(0))
        for s, nom in sorted(SLOTS_VOULUS.items()):
            idx = off2 + s
            if idx >= len(vt2["slots"]):
                echecs.append((full, "slot %d hors vtable" % s))
                continue
            e = vt2["slots"][idx]
            if e.get("method") != nom:
                echecs.append((full, "slot %d porte `%s`" % (s, e.get("method"))))
                continue
            rva = e.get("funcRVA")
            if rva == base_rva[s]:
                herite[s] += 1
            else:
                overrides[s].setdefault(rva, []).append(full)
        if (i + 1) % 50 == 0:
            print("   ... %d/%d" % (i + 1, len(cls)))

    print("")
    print("=== etape 3 -- RESULTAT ===")
    for s, nom in sorted(SLOTS_VOULUS.items()):
        print("")
        print("-- slot %d `%s` (rva de la base = %s)" % (s, nom, base_rva[s]))
        print("   HERITENT de la base : %d classe(s)" % herite[s])
        if not overrides[s]:
            print("   AUCUN override -- toutes les classes rendent la valeur de la base.")
        for rva, noms in sorted(overrides[s].items(), key=lambda kv: -len(kv[1])):
            ghidra = hex(0x180000000 + int(rva, 16))
            print("   OVERRIDE rva=%-12s (ghidraVA=%s) : %d classe(s)"
                  % (rva, ghidra, len(noms)))
            for n in noms[:40]:
                print("        %s" % n)
            if len(noms) > 40:
                print("        ... et %d de plus" % (len(noms) - 40))
    if echecs:
        print("")
        print("   %d classe(s) NON MESUREE(S) (jamais comptees comme heritantes) :" % len(echecs))
        for n, e in echecs[:20]:
            print("        %-70s %s" % (n, e))

    if a.json:
        out = Path(a.json)
        if "data" in out.parts:
            print("REFUS : `--json` sous data/ (data = ce qu'on LIT, logs = ce qu'on ECRIT)")
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "build": build, "baseRva": base_rva, "interfaceOffset": iface_off,
            "overrides": {str(k): v for k, v in overrides.items()},
            "herite": {str(k): v for k, v in herite.items()},
            "echecs": echecs,
        }, indent=1), encoding="utf-8")
        print("")
        print("   [json] %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
