// delegate — fabriquer un delegate managé INERTE pour un natif qui EXIGE un callback.
//
// POURQUOI CE MODULE EXISTE
//
// Beaucoup de methodes du jeu prennent un `System.Action<T>` en dernier argument, et
// **passer `null` n'est pas une option** : le compilateur IL2CPP insere un null-check avant
// d'invoquer le delegate, et sa branche « faux » tombe sur `raise_null_reference_exception`
// suivi d'un `INT 3`. Mesure du 2026-08-10 (#600) : un envoi d'Operation avec `callback = null`
// est **enregistre par le serveur**, PUIS tue le process a la reception de la reponse. Le
// crash est DIFFERE, donc il ne designe pas son site.
//
// Quand on appelle un tel natif depuis Frida, il faut donc lui fournir un delegate qui existe
// et ne fait rien. Ce module le fabrique. Il porte QUATRE pieges, tous mesures, et c'est la
// raison d'etre du fichier : chacun a coute un aller-retour.
//
//   1. `il2cpp_object_new` NU, jamais `createObject`. Ce dernier enchaine sur
//      `findMethod(klass, ".ctor")` et l'invoque avec `args = null` -- or un ctor de delegate
//      en prend DEUX (`object target, IntPtr method`) : `runtime_invoke` lit alors `params[0]`
//      a 0x0 et `params[1]` a 0x8, d'ou le tres litteral « access violation accessing 0x8 ».
//      Un delegate ne se construit pas par son ctor ici : on alloue, et on ecrit les champs.
//
//   2. ENRACINER, et tout de suite. L'objet rendu n'est reference par RIEN de manage : une
//      `NativePointer` cote Frida n'est pas scannee par le GC IL2CPP. Entre l'allocation et le
//      moment ou le natif range le delegate, une collecte peut le liberer -- et `invoke_impl`
//      serait invoque sur de la memoire recyclee, a la RECEPTION de la reponse, loin du site
//      fautif. `gcRoot.add` pose un `il2cpp_gchandle_new(obj, pinned)`.
//
//   3. ZERO JAVASCRIPT dans le corps du callback. Le delegate est invoque depuis le thread
//      qui traite la reponse ; y mettre un `NativeCallback` ferait entrer Frida dans QuickJS
//      depuis ce thread-la. Le corps est donc du code natif pur, qui DEPOSE ses arguments sur
//      une ardoise ; c'est le PUMP qui vient les ramasser, sur le main thread.
//      « Le natif depose, le pump ramasse » -- jamais l'inverse.
//
//   4. UN SEUL delegate par classe, partage. Il ne porte aucun etat : le natif ne fait que le
//      RANGER, il ne le mute jamais. En fabriquer un par appel laisserait un objet EPINGLE de
//      plus a chaque fois, jamais libere -- mesure : six fabrications ont fait monter
//      `gcRoot.count()` de 0 a 6.
//
// ⚠ CE MODULE NE REND PAS UN CALLBACK QUI **AGIT**. Si tu as besoin qu'il agisse, ne mets pas
// la logique dedans : lis l'ardoise depuis le pump et agis la-bas.
//
// ⚠ ET IL NE DISPENSE PAS DE DETACHER TES SONDES. Invoquer une methode qu'on ancre, depuis du
// JS qui tourne sur le main thread, deadlocke a coup sur (3 gels sur 3) : l'appel natif
// retombe dans notre propre trampoline, Frida veut y executer un handler JS, et le runtime
// est deja tenu par ce thread. Detacher AVANT d'appeler. Detail :
// `docs/rl/case-600-gel-du-dispatch-natif.md`.
//
// ⚠ ⚠ CETTE PHRASE VAUT POUR LE DISPATCH DE DELEGATE, PAS PARTOUT -- ET ELLE A DEJA ETE CITEE
// TROP LARGE. `retreat-capture.ts` s'en est servi pour justifier un churn d'`Interceptor`
// (douze `detach` + douze `attach` autour de chaque invoke, en plein demontage de scene), puis
// un refus. CONTRE-EPREUVE du 2026-08-21, meme nombre d'essais que la mesure ci-dessus : douze
// ancrages ARMES -- dont la methode invoquee elle-meme -- invoke par `invokeMethod`
// (`il2cpp_runtime_invoke`), **6/6 revenus** en 0,25 a 1,64 s, avec 3 handlers JS ayant tire
// PENDANT chaque appel et l'effet natif produit. Le trampoline EST re-entre, sans geler.
// Deux causes restent en lice pour les 3 gels d'origine, et rien ici ne les separe : (a) ils
// precedent de DIX JOURS le passage d'`il2cpp_runtime_invoke` en `exceptions: "propagate"`
// (`95e88699`), et une exception managee confisquee gele avec le MEME symptome ; (b) le regime
// mesure ici n'est pas le dispatch de delegate. AVANT de recopier cet avertissement ailleurs :
// mesure-le dans TON regime. Detail : `docs/rl/case-10041-le-deadlock-de-trampoline-refute-sur-la-retraite.md`.

import { getFieldOffset } from "./helpers.js";
import { il2cpp_object_new } from "./invoke.js";
import { gcRoot } from "./gc-root.js";

/** Les cinq champs de `System.Delegate` qu'il faut ecrire. Ils ne sont DECLARES par aucun
 *  `Action<T>` : `getFieldOffset` les trouve en remontant les classes de base, ce qu'une
 *  resolution ecrite a la main oublie (mesure : 0 champ sur 5, lu comme « classe inconnue »). */
const CHAMPS = ["invoke_impl", "method_ptr", "method_code", "method", "m_target"] as const;

export interface DelegateInerte {
    ptr: NativePointer;
    /** `true` si on rend celui deja fabrique pour cette classe. */
    reutilise: boolean;
    offsets: Record<string, number>;
    /** L'ardoise ou le stub depose ses arguments. Lire par `ardoiseDelegate`. */
    ardoise: NativePointer;
    /** ⚠ LA PAGE DE CODE, GARDEE ICI POUR QU'ELLE NE SOIT PAS LIBEREE. Ce champ n'est pas
     *  de la documentation : c'est la REFERENCE FORTE. Frida rend la memoire d'un
     *  `Memory.alloc` des que sa derniere reference JS disparait, et le delegate, lui,
     *  survit -- son `invoke_impl` pointerait alors sur une page rendue au systeme.
     *
     *  MESURE (2026-08-10) : la premiere version de ce module gardait `ardoise` et PAS
     *  `code`. Le RPC d'envoi a rendu `ok: true` en 0,39 s, jeu `Responding: True` -- puis
     *  le process est MORT quelques secondes plus tard, quand la reponse serveur a saute
     *  dans la page liberee. La mort est DIFFEREE, donc elle ne designe pas son site : elle
     *  se lit comme un echec de l'envoi alors que l'envoi avait abouti.
     *
     *  Ne jamais retirer ce champ sous pretexte que personne ne le lit. */
    code: NativePointer;
}

export interface Ardoise {
    /** Nombre d'invocations depuis la fabrication. `0` = jamais appele. */
    appels: number;
    /** `rcx` -- `method_code` tel qu'on l'a ecrit (donc `0x0` ici). */
    rcx: string;
    /** `rdx` -- LA VALEUR passee. ⚠ Mesure : c'est une ADRESSE de pile, pas la valeur
     *  elle-meme ; le decompile laissait l'ambiguite ouverte. Garde brut, non interprete. */
    rdx: string;
    /** `r8` -- `method` tel qu'on l'a ecrit. */
    r8: string;
}

interface Entree { d: DelegateInerte }
const parClasse = new Map<string, Entree>();

/** Alloue la page de code + son ardoise. Le stub ENREGISTRE puis rend la main.
 *
 *  `<Execute>b__0` invoque ainsi : `(*(d+0x18))( *(d+0x40), <valeur>, *(d+0x28) )`, donc en
 *  ABI Win64 : rcx = `method_code`, rdx = la valeur, r8 = `method`. `rax` est volatile, on
 *  peut l'ecraser ; la signature rend `void`, et l'appelant nettoie la pile.
 *
 *  W^X : la page de code est `r-x`, l'ardoise est une allocation `rw` SEPAREE.
 *
 *  Ardoise :  +0x00 uint32 appels · +0x08 rcx · +0x10 rdx · +0x18 r8 */
function forgerStub(): { code: NativePointer; ardoise: NativePointer } | null {
    try {
        const slot = Memory.alloc(64);
        const page = Memory.alloc(Process.pageSize);
        Memory.patchCode(page, 32, (code) => {
            code.writeByteArray([0x48, 0xb8]);              // movabs rax, imm64
            code.add(2).writePointer(slot);
            code.add(10).writeByteArray([
                0xff, 0x00,                                 // inc dword ptr [rax]
                0x48, 0x89, 0x48, 0x08,                     // mov [rax+0x08], rcx
                0x48, 0x89, 0x50, 0x10,                     // mov [rax+0x10], rdx
                0x4c, 0x89, 0x40, 0x18,                     // mov [rax+0x18], r8
                0xc3,                                       // ret
            ]);
        });
        Memory.protect(page, Process.pageSize, "r-x");
        return { code: page, ardoise: slot };
    } catch { return null; }
}

/** Rend un delegate inerte pour `klass` (typiquement obtenu par `methodParamClass`).
 *
 *  Rend `{d}` ou `{err}` -- JAMAIS un `null` muet. Mesure : un `catch { return null; }` a
 *  deja fait afficher « impossible de fabriquer » avec les cinq offsets resolus JUSTE A
 *  COTE : le refus etait juste, son motif introuvable.
 *
 *  `neuf` force une fabrication fraiche au lieu du partage -- reserve a la MESURE (isoler
 *  l'allocation), et chaque appel laisse alors un objet epingle de plus. */
export function delegateInerte(
    klass: NativePointer | null, opts?: { neuf?: boolean },
): { d?: DelegateInerte; err?: string } {
    if (!klass || klass.isNull()) return { err: "classe du delegate NON RESOLUE" };
    const cle = klass.toString();
    if (!opts?.neuf) {
        const deja = parClasse.get(cle);
        if (deja) return { d: { ...deja.d, reutilise: true } };
    }

    const offsets: Record<string, number> = {};
    const manquants: string[] = [];
    for (const nom of CHAMPS) {
        const o = getFieldOffset(klass, nom);   // -1 si absent (⚠ truthy en JS)
        if (o >= 0) offsets[nom] = o; else manquants.push(nom);
    }
    if (manquants.length) {
        return { err: "champs introuvables sur la classe et ses parents : "
                    + manquants.join(", ") };
    }

    const stub = forgerStub();
    if (!stub) return { err: "stub natif NON ALLOUE" };

    let d: NativePointer;
    try {
        d = il2cpp_object_new(klass) as NativePointer;   // NU -- cf. piege n°1 en tete
    } catch (e) {
        return { err: "il2cpp_object_new : "
                    + String((e as Error).message || e).slice(0, 140) };
    }
    if (d.isNull()) return { err: "il2cpp_object_new a rendu NULL" };

    gcRoot.add(d);                                       // cf. piege n°2

    try {
        d.add(offsets["invoke_impl"]).writePointer(stub.code);
        d.add(offsets["method_ptr"]).writePointer(stub.code);
        d.add(offsets["method_code"]).writePointer(ptr(0));
        d.add(offsets["method"]).writePointer(ptr(0));
        d.add(offsets["m_target"]).writePointer(ptr(0));
    } catch (e) {
        return { err: "ecriture des champs : "
                    + String((e as Error).message || e).slice(0, 140) };
    }

    const inerte: DelegateInerte = {
        ptr: d, reutilise: false, offsets,
        // Les DEUX allocations sont retenues ici. `ardoise` parce qu'on la relit ; `code`
        // UNIQUEMENT pour la garder en vie. Cf. le champ `code` de l'interface.
        ardoise: stub.ardoise, code: stub.code,
    };
    // ⚠ `neuf` N'ECHAPPE PAS A LA REGLE : un delegate hors registre n'est retenu que par
    // l'objet rendu a l'appelant. S'il le jette, la page meurt avec lui -- et le delegate,
    // lui, peut encore etre invoque. `neuf` est reserve a la MESURE pour cette raison.
    if (!opts?.neuf) parClasse.set(cle, { d: inerte });
    return { d: inerte };
}

/** Ce que le stub a depose. A LIRE DEPUIS LE PUMP.
 *
 *  `null` = aucun delegate fabrique pour cette classe, donc RIEN N'A ETE MESURE -- a ne
 *  surtout pas lire comme « le callback n'a pas ete appele ». Un callback jamais appele,
 *  lui, rend `appels: 0`. */
export function ardoiseDelegate(klass: NativePointer | null): Ardoise | null {
    if (!klass || klass.isNull()) return null;
    const e = parClasse.get(klass.toString());
    if (!e) return null;
    return lireArdoise(e.d.ardoise);
}

/** Variante pour qui detient deja l'ardoise (cas d'un delegate fabrique avec `neuf`). */
export function lireArdoise(ardoise: NativePointer | null): Ardoise | null {
    if (!ardoise || ardoise.isNull()) return null;
    try {
        return {
            appels: ardoise.readU32(),
            rcx: ardoise.add(8).readPointer().toString(),
            rdx: ardoise.add(16).readPointer().toString(),
            r8: ardoise.add(24).readPointer().toString(),
        };
    } catch { return null; }
}
