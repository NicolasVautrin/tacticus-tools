// FOYER UNIQUE des ADRESSES EPINGLEES, cote LIVE (#475).
//
// Une adresse EPINGLEE est une VA ghidra TRANSCRITE A LA MAIN, pour un point du binaire qui
// ne se resout par AUCUN symbole au runtime : placeholder `FUN_*` (aucun `MethodInfo`), point
// INTERNE a une fonction (return-address d'un call site), donnee statique `DAT_*`, corps
// d'iterateur. `CLAUDE.md` autorise ces cas-la a rester en VA -- mais cette phrase est ecrite
// pour la CITATION, pas pour l'ATTACHEMENT.
//
// Pour un hook l'exigence est differente, parce que la degradation est MUETTE :
// `Interceptor.attach` REUSSIT sur du code arbitraire. Une VA perimee ne produit ni erreur ni
// crash -- seulement un capteur qui ne fire jamais, ou qui fire et corrompt. Mesure #475 :
// les six adresses en dur de `bucket-audit` et `modifier-observe` etaient 6/6 PERIMEES, et la
// seule encore armee attachait `Interceptor` a `FUN_180026780+0x40` -- au milieu d'une AUTRE
// fonction. Personne ne l'a su : #597 a du lire le predicat au decompile.
//
// Ce module est le pendant LIVE de `scripts/python/build_pin.require_pinned` (#431), qui tient
// le meme contrat pour la face OFFLINE. Meme semantique, deliberement : le porteur DECLARE son
// build, le foyer le CONFRONTE au build reellement charge, et REFUSE en le DISANT plutot que
// de degrader. On ne devine pas, on ne retombe pas sur « le seul autre build present ».
//
// C'est aussi le SEUL module ou `il2cppBase.add(<constante>)` a le droit d'exister -- c'est
// exactement ce que le cliquet `probe_475_pinned_addresses.py` tient.

import { il2cppBase, IL2CPP_MODULE_NAME } from "./helpers.js";
import { log } from "../runtime/diag.js";

/** Base d'image ghidra du `GameAssembly.dll`. Les VA epinglees s'ecrivent COMPLETES et la RVA
 *  se calcule EN CODE : ecrire la RVA a la main a DEJA produit une constante fausse et latente
 *  (`RVA_VALUE_MOD_MODIFY` valait `0x1fadfc0` pour une VA `@180fadfc0`, dont la RVA est
 *  `0xfadfc0` -- elle pointait en plein corps de `FPSCounterData$$set_Average`). */
export const IL2CPP_VA_BASE = 0x180000000;

/** Forme d'un hash de build Tacticus (`rnca9r7q6c`, `gqfc5mff6c`, `t6dpr4k06g`, ...).
 *
 *  ⚠ CE MOTIF A DEJA EPINGLE UNE REGULARITE ACCIDENTELLE, ET CA A COUTE TOUT LE CAPTEUR.
 *  Il valait `/^[a-z0-9]{8}6c$/` -- le suffixe `6c` etait ecrit EN DUR parce que les six
 *  premiers builds observes le portaient. Le build `t6dpr4k06g` finit en `6g` : le motif l'a
 *  refuse, `installedBuild()` a rendu `build: null` (« NON MESURABLE »), et `pinnedAddress` a
 *  donc refuse les ONZE pins de la session -- pas parce que le build differait, mais parce
 *  qu'il n'etait plus LISIBLE. Mesure du 2026-08-15 (`nameResolutionStatus`) :
 *  `buildWhy = "le segment 't6dpr4k06g' n'a pas la forme d'un hash de build"`,
 *  `pinnedAddressRefusals` = 11. Cote consommateur, `scorerElevTraceDump` et
 *  `scorerLeafTraceDump` rendaient 0 entree, donc `X_nat = Tile7 - Elevation - TileEffects`
 *  etait `None` sur TOUTES les tuiles -- et les gardes qui en dependent passaient A VIDE.
 *
 *  LE GATE EST DONC DELIBEREMENT LARGE, et c'est un raisonnement sur la DIRECTION DE PANNE,
 *  pas un relachement : ce qui identifie le build est sa POSITION (le segment juste apres
 *  `games/`), pas sa forme. Une forme trop STRICTE degrade en `build: null` -> refus de TOUT,
 *  en silence. Une forme trop LARGE degrade en `probe.build != pin.build` -> refus de ce pin,
 *  ce qui est le meme cote sur. Il n'existe aucun chemin ou un segment lu par erreur fasse
 *  ACCEPTER un pin : il faudrait qu'il soit EGAL au build declare. On garde donc le minimum
 *  qui ecarte un repertoire de service (`.tmp`, `backup-1`) : alphanumerique minuscule.
 *  Les SEPT builds observes le verifient (`nb3o9lmt6c`, `uu2fr8mv6c`, `kqkbjqfb6c`,
 *  `rmvdp0v56c`, `gqfc5mff6c`, `rnca9r7q6c`, `t6dpr4k06g`). */
const BUILD_SHAPE = /^[a-z0-9]+$/;

export interface PinnedAddress {
    /** VA ghidra COMPLETE, telle qu'elle se grepe dans
     *  `data/symbols/<build>/ghidra/functions.tsv`. Jamais une RVA. */
    va: number;
    /** Hash du build sur lequel cette VA a ete MESUREE. */
    build: string;
    /** Symbole ghidra VERBATIM a cette VA (`FUN_1800267c0`, `X$$Y`, `X$$Y+0x1b` pour un point
     *  interne). Il n'est PAS lu au runtime : c'est ce que `probe_475` confronte, offline, a la
     *  table versionnee du build declare -- le seul controle qui attrape une transcription
     *  fausse a l'interieur du BON build. */
    symbol: string;
    /** `code` (defaut) = la VA designe une fonction ou un point interne ; `data` = une donnee
     *  statique (`DAT_*`), qu'on LIT et qu'on n'attache pas. Le cliquet ne cherche un symbole de
     *  fonction que pour `code` -- pour `data` il verifie que la VA tombe HORS de la zone des
     *  fonctions, ce qui est ce qui se derive offline (et il DIT que c'est tout ce qu'il verifie). */
    kind?: "code" | "data";
    /** Ce que le hook en fait. Imprime dans le refus, sinon le refus est un cul-de-sac. */
    what: string;
    /** Comment re-deriver la VA sur un build neuf. Imprime dans le refus. */
    how?: string;
}

interface BuildProbe { build: string | null; why: string }

let cached: BuildProbe | null = null;

/** Hash du build reellement CHARGE dans le processus, lu sur le chemin du module.
 *
 *  Tri-etat obligatoire, et chaque panne porte son NOM (#467-r6) : `null` ne veut jamais dire
 *  « un autre build », il veut dire « je n'ai pas pu mesurer » -- et `why` dit laquelle des
 *  trois pannes c'est. Un capteur qui ne sait pas nommer sa panne fait corriger la mauvaise
 *  cause. Dans les deux cas le pin est REFUSE : on n'attache pas sur un doute. */
export function installedBuild(): BuildProbe {
    if (cached !== null) return cached;
    cached = probeBuild();
    return cached;
}

function probeBuild(): BuildProbe {
    const mod = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (mod === null) {
        return { build: null, why: "module " + IL2CPP_MODULE_NAME + " introuvable" };
    }
    const path = mod.path;
    if (typeof path !== "string" || path.length === 0) {
        return { build: null, why: "le module charge ne porte aucun chemin (Module.path vide)" };
    }
    const segs = path.split(/[\\/]/);
    let i = -1;
    for (let k = segs.length - 1; k >= 0; k--) {
        if (segs[k] === "games") { i = k; break; }
    }
    if (i < 0 || i + 1 >= segs.length) {
        return { build: null,
            why: "chemin hors de la disposition `.../tacticus/games/<build>/` : " + path };
    }
    const b = segs[i + 1];
    if (!BUILD_SHAPE.test(b)) {
        return { build: null,
            why: "le segment `" + b + "` n'a pas la forme d'un hash de build : " + path };
    }
    return { build: b, why: "" };
}

/** Trace des refus, pour qu'un hook muet se DIAGNOSTIQUE au lieu de se supposer. */
const refusals: string[] = [];

/** Les refus emis depuis le chargement du script (diagnostic, expose par les RPC de statut). */
export function pinnedAddressRefusals(): string[] {
    return refusals.slice();
}

/** Adresse epinglee, ou `null` si le build a bouge / n'est pas mesurable.
 *
 *  JAMAIS d'attachement en aveugle : un appelant qui recoit `null` n'attache pas, et le refus
 *  est deja imprime. C'est le contrat exact de `build_pin.require_pinned` cote offline -- a
 *  ceci pres qu'ici on rend `null` au lieu de lever, parce qu'un hook doit pouvoir renoncer a
 *  UNE cible sans faire tomber tout le script injecte. */
export function pinnedAddress(pin: PinnedAddress): NativePointer | null {
    const probe = installedBuild();
    if (probe.build === pin.build) {
        return il2cppBase.add(pin.va - IL2CPP_VA_BASE);
    }
    const cause = probe.build === null
        ? "build NON MESURABLE (" + probe.why + ")"
        : "build charge = " + probe.build;
    const msg = "[build-pin] REFUS -- adresse epinglee sur " + pin.build + ", " + cause
        + " ; cible : " + pin.symbol + " (" + pin.what + ")"
        + ". Aucun attachement : une VA d'un autre build designe du code arbitraire, et"
        + " Interceptor.attach y REUSSIT en silence."
        + (pin.how ? " RE-DERIVER : " + pin.how : "");
    refusals.push(msg);
    log(msg);
    return null;
}
