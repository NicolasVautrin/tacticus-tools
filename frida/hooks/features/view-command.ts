// view-command — la surface de COMMANDES du jeu, rendue REQUETABLE (#992).
//
// POURQUOI UN RPC GENERIQUE, ET PAS UN PAR COMMANDE
// --------------------------------------------------
// `idun.shared.commands.ViewCommandExecutor` porte **516 methodes** et `idun.IdunMainView` **82**
// (dont **7 STATIQUES**). Ecrire un RPC par commande, c'est figer aujourd'hui le sous-ensemble
// qu'on croit utile -- et le depot a deja paye ce reflexe : le pilotage de l'UI existe parce
// qu'on ne savait pas ATTEINDRE ces objets, pas parce que le jeu l'exigeait.
// On expose donc : QUI est joignable, QUOI existe dessus, et un INVOKE garde.
//
// COMMENT ON LES ATTEINT -- deux voies DIFFERENTES, et la difference est mesuree
// ------------------------------------------------------------------------------
//   `ViewCommandExecutor`  parent = `System.Object`  => **PAS** un MonoBehaviour.
//        `FindObjectsByType` ne le trouvera JAMAIS (meme piege que `thor.Menu.MenuSystems`,
//        qui porte un `Update()` et rend `instances: 0`). Il se prend par le champ NOMME
//        `_viewCommandExecutor` d'`idun.UI.IdunNavigation`, que `IdunNavigation$$Init` recoit
//        en 1er parametre et range.
//   `IdunMainView`         parent = `UnityEngine.MonoBehaviour` (taille 352) => enumerable.
//
// ⇒ « ca ressemble a un composant » ne dit RIEN. C'est la CHAINE D'HERITAGE qui tranche, et ce
// module la publie (`chaine`) pour qu'un glissement de build se voie au lieu de rendre 0.
//
// LES STATIQUES N'ONT BESOIN D'AUCUNE INSTANCE
// ---------------------------------------------
// `IdunMainView$$get_IsBattleActive() -> Boolean` et `get_IsActive()` sont STATIQUES : elles
// repondent « suis-je en bataille ? » sans instance et sans UI. Le harnais le deduisait
// jusqu'ici de l'etat des ECRANS -- un proxy, la ou le jeu porte la reponse.
// La cible `statique` sert exactement a ca : `obj = null` a l'invoke.
//
// CE QUE CE MODULE REFUSE
// ------------------------
//   - la famille `Cheat_*` / `Cheat*` : elle MUTE LE COMPTE. Refus INCONDITIONNEL, aucun
//     `confirmer` ne l'ouvre. (`ViewCommandExecutor` en porte plusieurs, et `IdunMainView`
//     porte `CheatFinishBattle`.)
//   - tout invoke sans `confirmer: true`. Ce n'est pas un lecteur : c'est un EXECUTEUR DE
//     COMMANDES -- `StartCampaignMatch` lance une vraie bataille, `SetBattleNotRunning` desarme
//     le garde « deja en cours ». Lister est libre ; appeler se declare.
//
// ⚠ ET IL NE DISPENSE PAS D'OBSERVER D'ABORD. Un natif qui ECRIT s'observe avant d'etre
// invoque -- le depot a deja rendu `ok: true` puis trouve le jeu MORT. `viewList` est la pour
// que l'observation precede l'appel, pas pour rendre l'appel commode.

import {
    class_get_methods, class_get_name, class_get_parent, findClassAnywhere,
    findMethodByParamCount, getFieldOffset, getSystemType, method_get_name,
    method_get_param_count, methodParamClassName, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
// ⚠ IMPORTES, PAS RECOPIES. Deux tables de coercition d'arguments divergeraient en silence ;
// le depot proscrit de recopier le voisin de forme. Leur place est dans `il2cpp/` -- residu
// declare dans `fsm-input.ts`, a deplacer hors d'une fenetre.
import { argIl2cpp, decoderRetour } from "./fsm-input.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

export interface Refus { ok: false; error: string }
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;
}

/** Les cibles nommees. `ns`/`cls` servent a RESOUDRE LA CLASSE ; `voie` dit comment on obtient
 *  l'instance -- et `statique` dit qu'il n'en faut aucune. */
const CIBLES = {
    executor: { ns: "idun.shared.commands", cls: "ViewCommandExecutor", voie: "champNomme" },
    mainview: { ns: "idun", cls: "IdunMainView", voie: "unityFind" },
    statique: { ns: "idun", cls: "IdunMainView", voie: "aucune" },
} as const;
type NomCible = keyof typeof CIBLES;

/** Instances epinglees, par cible. Une `NativePointer` cote Frida n'est pas scannee par le GC :
 *  sans `gcRoot.add`, l'objet peut etre deplace ou libere entre la resolution et l'appel. */
const epingles = new Map<NomCible, NativePointer>();

function retenir(nom: NomCible, obj: NativePointer): void {
    const deja = epingles.get(nom);
    if (deja && deja.equals(obj)) return;
    if (deja) { try { gcRoot.remove(deja); } catch { /* best effort */ } }
    try { gcRoot.add(obj); epingles.set(nom, obj); } catch { /* best effort */ }
}

function chaineHeritage(klass: NativePointer): string[] {
    const out: string[] = [];
    let k = klass;
    for (let i = 0; i < 12 && !k.isNull(); i++) {
        try { out.push(s(class_get_name(k) as NativePointer)); } catch { break; }
        try { k = class_get_parent(k) as NativePointer; } catch { break; }
    }
    return out;
}

/** Premiere instance vivante d'une classe MonoBehaviour.
 *
 *  ⚠ SURCHARGE A 3 ARGUMENTS (`FindObjectsInactive.Include = 1`). Celle a 2 arguments EXCLUT
 *  les inactifs -- mesure de `ui-windows.ts` : elle rendait **0 ecran** sur une classe qui
 *  resout parfaitement. Un objet desactive est exactement ce qu'on cherche ici. */
export function premiereInstance(klass: NativePointer): NativePointer | Refus {
    const kObj = findClassAnywhere("UnityEngine", "Object");
    if (!kObj) return { ok: false, error: "UnityEngine.Object introuvable" };
    const mi3 = findMethodByParamCount(kObj, "FindObjectsByType", 3);
    const mi2 = findMethodByParamCount(kObj, "FindObjectsByType", 2);
    const tri = Memory.alloc(4); tri.writeS32(0);
    const inclure = Memory.alloc(4); inclure.writeS32(1);
    let arr: NativePointer;
    try {
        arr = mi3
            ? invokeMethod(mi3.info, null, [getSystemType(klass), inclure, tri])
            : (mi2
                ? invokeMethod(mi2.info, null, [getSystemType(klass), tri])
                : ptr(0));
    } catch (e) { return { ok: false, error: "FindObjectsByType a leve : " + (e as Error).message }; }
    if (arr.isNull()) return { ok: false, error: "FindObjectsByType a rendu null" };
    const n = arr.add(0x18).readS32();
    if (n <= 0) {
        return { ok: false, error: "0 instance vivante -- la scene qui la porte n'est pas "
            + "montee (hors bataille ?), ou la classe n'est pas un MonoBehaviour" };
    }
    return arr.add(0x20).readPointer();
}

/** Resout l'instance d'une cible. Rend un REFUS NOMME, jamais `null` -- un `null` se lirait
 *  comme « pas d'instance » alors que la cause peut etre « champ absent de ce build ». */
function instanceDe(nom: NomCible): NativePointer | null | Refus {
    const c = CIBLES[nom];
    if (c.voie === "aucune") return null;              // statique : pas d'instance, par nature
    const deja = epingles.get(nom);
    if (deja) return deja;

    if (c.voie === "unityFind") {
        const k = findClassAnywhere(c.ns, c.cls);
        if (!k) return { ok: false, error: `classe ${c.ns}.${c.cls} introuvable` };
        const r = premiereInstance(k);
        if (estRefus(r)) return r;
        retenir(nom, r);
        return r;
    }

    // `champNomme` : la nav vivante, puis SON champ -- resolu PAR NOM, jamais par offset
    // (les offsets bougent d'un build a l'autre ; mesure d'`auto-boot.ts` : 0x1F0 -> 0x1D8).
    const kNav = findClassAnywhere("idun.UI", "IdunNavigation");
    if (!kNav) return { ok: false, error: "classe idun.UI.IdunNavigation introuvable" };
    const nav = premiereInstance(kNav);
    if (estRefus(nav)) {
        return { ok: false, error: "aucune IdunNavigation vivante -- " + nav.error };
    }
    const off = getFieldOffset(kNav, "_viewCommandExecutor");
    if (off < 0) {
        return { ok: false, error: "_viewCommandExecutor absent d'IdunNavigation sur ce build "
            + "-- le champ a ete renomme, le chemin est PERIME (ne pas replier sur un offset)" };
    }
    const exec = nav.add(off).readPointer();
    if (exec.isNull()) {
        return { ok: false, error: "IdunNavigation._viewCommandExecutor est NUL -- la nav "
            + "existe mais n'a pas encore recu ses dependances (Init pas passe)" };
    }
    retenir(nom, exec);
    return exec;
}

/** Le `ViewCommandExecutor` VIVANT, pour les modules qui ont besoin de SES champs.
 *
 *  EXPOSE parce que l'executeur est le porteur de toutes les `*Progression` du compte (44
 *  champs mesures), et qu'un module qui en veut une n'a pas a re-marcher la chaine
 *  `IdunNavigation._viewCommandExecutor`. La resolution reste ICI, foyer unique : ce fichier
 *  porte deja le rappel de ce qu'une resolution de champ dupliquee a coute.
 *
 *  Rend un REFUS NOMME, jamais `null` : « pas d'instance » et « champ absent de ce build »
 *  ne doivent pas se confondre. */
export function executeurVivant(): NativePointer | Refus {
    const r = instanceDe("executor");
    if (estRefus(r)) return r;
    if (r === null) return { ok: false, error: "executor sans instance -- voie `aucune` ?" };
    return r;
}

/** ⛔ La famille tricheur. Refus INCONDITIONNEL : elle mute le compte, et aucun `confirmer`
 *  ne doit pouvoir l'ouvrir -- une garde qu'un drapeau desarme n'est pas une garde. */
function estTricheur(nom: string): boolean {
    return /^cheat/i.test(nom);
}

/** Resout l'objet sur lequel agir : soit une CIBLE nommee, soit un POINTEUR deja obtenu.
 *
 *  ⚠ POURQUOI `surPointeur` EXISTE. Une surface « requetable » qui ne sait viser que deux objets
 *  racines ne repond qu'aux questions qu'on a prevues. Mesure du 2026-08-12 : pour lire la
 *  stamina courante il faut descendre `executeur._campaignProgressions` ->
 *  `GetCampaign(type, id)` -> `<champ>` -> `GetCurrentAmount()`. Aucun de ces pas n'est
 *  exprimable avec une cible fixe, et deux d'entre eux sont des CHAMPS, pas des methodes.
 *  En rendant les pointeurs et en les acceptant en entree, l'appelant COMPOSE le chemin --
 *  sans qu'on ait a deviner d'avance lesquels comptent.
 *
 *  Le pointeur est VALIDE avant usage : on lit sa classe. Un pointeur invalide se refuse ici,
 *  pas au milieu d'un `runtime_invoke`. */
function objetVise(
    cible: string | undefined, surPointeur: string | undefined,
): { obj: NativePointer | null; klass: NativePointer; nom: string } | Refus {
    if (typeof surPointeur === "string" && surPointeur.length > 0) {
        if (!/^0x[0-9a-fA-F]+$/.test(surPointeur)) {
            return { ok: false, error: "`surPointeur` doit etre hexadecimal (0x...)" };
        }
        const p = ptr(surPointeur);
        try {
            const k = p.readPointer();
            const n = s(class_get_name(k) as NativePointer);
            return { obj: p, klass: k, nom: n };
        } catch {
            return { ok: false, error: "`surPointeur` " + surPointeur + " illisible -- ce n'est "
                + "pas un objet manage vivant (deja libere ? pointeur d'une autre session ?)" };
        }
    }
    const nom = (cible ?? "executor") as NomCible;
    if (!(nom in CIBLES)) {
        return { ok: false, error: "cible inconnue -- " + Object.keys(CIBLES).join(", ") };
    }
    const c = CIBLES[nom];
    const k = findClassAnywhere(c.ns, c.cls);
    if (!k) return { ok: false, error: `classe ${c.ns}.${c.cls} introuvable` };
    const inst = instanceDe(nom);
    if (estRefus(inst)) return inst;
    return { obj: inst, klass: k, nom: c.cls };
}

/** APPELER une commande -- LE FOYER, dont `viewInvoke` n'est que l'exposition.
 *
 *  body: { cible, surPointeur?, methode, args?: unknown[], confirmer: true }
 *
 *  `cible: "statique"` invoque SANS instance (`obj = null`) -- la voie des 7 statiques
 *  d'`IdunMainView`, dont `get_IsBattleActive`.
 *
 *  ⚠ La surcharge est choisie PAR ARITE, jamais par nom seul : mesure de `fsm-input.ts`,
 *  `Menu<T>` porte `Get()` ET `Get(Transform)`, et `findMethod` rend la PREMIERE trouvee --
 *  la mauvaise une fois sur deux.
 *
 *  ⚠ La valeur de retour est DECODEE et le decodeur DIT ce qu'il ne sait pas lire. Jeter le
 *  retour rendrait « a refuse » et « a marche » indiscernables.
 *
 *  EXTRAIT DU RPC AU #993 : le cycle d'amorce lance sa bataille par
 *  `ViewCommandExecutor$$StartCampaignMatch`, et doit passer par CE corps -- avec sa resolution
 *  de cible, sa coercition d'arguments et son refus inconditionnel de `Cheat*`. Une seconde
 *  table de coercition divergerait en silence, comme le rappelle deja l'import d'`argIl2cpp`. */
export function invoquerCommande(body?: {
    cible?: string; surPointeur?: string; methode?: string;
    args?: unknown[]; confirmer?: boolean;
}): Promise<unknown> | unknown {
    const methode = body?.methode;
    if (!methode) return { ok: false, error: "`methode` manquante" };
    if (estTricheur(methode)) {
        return { ok: false, error: "REFUS INCONDITIONNEL : la famille `Cheat*` mute le "
            + "COMPTE. Aucun `confirmer` ne l'ouvre -- une garde qu'un drapeau desarme "
            + "n'est pas une garde." };
    }
    if (body?.confirmer !== true) {
        return { ok: false, error: "REFUS : `confirmer: true` exige. Ce n'est pas un "
            + "lecteur mais un EXECUTEUR DE COMMANDES : selon la methode, l'appel lance "
            + "une vraie bataille, en termine une, ou desarme un garde. Utilise `viewList` "
            + "pour OBSERVER d'abord." };
    }
    const v = objetVise(body?.cible, body?.surPointeur);
    if (estRefus(v)) return v;
    const k = v.klass;

    const bruts = body?.args ?? [];
    const args: NativePointer[] = [];
    for (const brut of bruts) {
        const a = argIl2cpp(brut);
        if (estRefus(a)) return a;
        args.push(a as NativePointer);
    }
    const mr = findMethodByParamCount(k, methode, args.length);
    if (!mr) {
        return { ok: false, error: "aucune surcharge de " + JSON.stringify(methode)
            + " a " + args.length + " parametre(s) sur " + v.nom
            + " -- `viewList` avec un `filtre` liste ce qui existe et son arite." };
    }
    const obj = v.obj;
    return queueOnMainThread(() => {
        let res: NativePointer;
        try {
            res = invokeMethod(mr.info, obj, args.length ? args : null);
        } catch (e) {
            return { ok: false, error: "invoke a leve : " + (e as Error).message };
        }
        return { ok: true, sur: v.nom, statique: obj === null,
                 methode, arite: args.length,
                 retour: decoderRetour(mr.info, res) };
    });
}

export function register(ctx: Ctx): void {

    /** LIRE un chemin de champs NOMMES, et rendre le pointeur + la classe REELLE de l'arrivee.
     *
     *  body: { cible?, surPointeur?, chemin: "_a._b" }
     *
     *  Resolution PAR NOM a chaque pas, sur la classe REELLE de l'objet courant (pas sur le type
     *  DECLARE du champ) : un champ declare `IFoo` porte une implementation concrete dont les
     *  methodes ne sont pas celles de l'interface. */
    ctx.rpc.viewField = (body?: {
        cible?: string; surPointeur?: string; chemin?: string;
    }): Promise<unknown> => queueOnMainThread(() => {
        const v = objetVise(body?.cible, body?.surPointeur);
        if (estRefus(v)) return v;
        let cur = v.obj;
        if (cur === null) return { ok: false, error: "cible sans instance (statique)" };
        const pas: Array<Record<string, unknown>> = [];
        for (const brut of (body?.chemin ?? "").split(".")) {
            const seg = brut.trim();
            if (!seg) continue;
            const klass = cur.readPointer();
            const off = getFieldOffset(klass, seg);
            if (off < 0) {
                return { ok: false, error: "champ " + JSON.stringify(seg) + " absent de "
                    + s(class_get_name(klass) as NativePointer)
                    + " (ni sur ses parents) -- `classFields` liste ce qui existe",
                    parcouru: pas };
            }
            const suivant = cur.add(off).readPointer();
            if (suivant.isNull()) {
                return { ok: false, error: "champ " + seg + " est NUL -- le chemin s'arrete la",
                         parcouru: pas };
            }
            cur = suivant;
            let cn: string | null = null;
            try { cn = s(class_get_name(cur.readPointer()) as NativePointer); } catch { /* null */ }
            pas.push({ champ: seg, offset: off, valeur: cur.toString(), classeReelle: cn });
        }
        let fin: string | null = null;
        try { fin = s(class_get_name(cur.readPointer()) as NativePointer); } catch { /* null */ }
        return { ok: true, depart: v.nom, pointeur: cur.toString(), classeReelle: fin, pas };
    });

    /** LE MEME CHEMIN QUE `viewField`, mais on SERIALISE l'arrivee (Newtonsoft).
     *
     *  body: { cible?, surPointeur?, chemin?, max? } -> { ok, classeReelle, len, json }
     *
     *  POURQUOI ICI ET GENERIQUE. `viewField` rend un POINTEUR : pour en tirer un contenu il
     *  fallait jusqu'ici connaitre la disposition et la marcher a la main -- ce que chaque
     *  module a fini par reecrire pour SON objet (`expedition-board`, `battle-config`,
     *  `campaign-builder`, `mow-builder`, ... : 8 fichiers appellent `serializeToJson`, aucun
     *  ne l'expose). Or l'executeur porte 44 champs de progression : un lecteur par champ ne
     *  passe pas a l'echelle. Le chemin etant deja resolu PAR NOM a chaque pas, il n'y a
     *  qu'a brancher le serialiseur au bout.
     *
     *  ⚠ LECTURE PURE : aucun `invoke`, aucune commande de vue jouee. Ce n'est pas
     *  `viewInvoke`, et ca n'exige donc pas de `confirmer`.
     *  ⚠ La sortie est BORNEE et le DIT : au-dela de `max` (defaut 200 000 caracteres) le
     *  JSON est tronque et `tronque: true` -- un JSON coupe en silence se relit comme un
     *  objet incomplet, pas comme une troncature. */
    ctx.rpc.viewJson = (body?: {
        cible?: string; surPointeur?: string; chemin?: string; max?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const v = objetVise(body?.cible, body?.surPointeur);
        if (estRefus(v)) return v;
        let cur = v.obj;
        if (cur === null) return { ok: false, error: "cible sans instance (statique)" };
        for (const brut of (body?.chemin ?? "").split(".")) {
            const seg = brut.trim();
            if (!seg) continue;
            const klass = cur.readPointer();
            const off = getFieldOffset(klass, seg);
            if (off < 0) {
                return { ok: false, error: "champ " + JSON.stringify(seg) + " absent de "
                    + s(class_get_name(klass) as NativePointer) + " (ni sur ses parents)" };
            }
            const suivant = cur.add(off).readPointer();
            if (suivant.isNull()) {
                return { ok: false, error: "champ " + seg + " est NUL -- le chemin s'arrete la" };
            }
            cur = suivant;
        }
        let cn: string | null = null;
        try { cn = s(class_get_name(cur.readPointer()) as NativePointer); } catch { /* null */ }
        if (!isSerializerReady()) {
            return { ok: false, classeReelle: cn, error: "serialiseur Newtonsoft NON RESOLU" };
        }
        let json: string | null = null;
        try { json = serializeToJson(cur); }
        catch (e) {
            return { ok: false, classeReelle: cn,
                     error: "serialisation a leve : "
                          + String((e as Error).message || e).slice(0, 160) };
        }
        if (json === null) return { ok: false, classeReelle: cn, error: "serialisation en echec" };
        const max = typeof body?.max === "number" && body.max > 0 ? body.max : 200000;
        return {
            ok: true, classeReelle: cn, pointeur: cur.toString(), len: json.length,
            tronque: json.length > max,
            json: json.length > max ? json.slice(0, max) : json,
        };
    });

    /** TOUTES les instances vivantes d'une classe UNITY, par (ns, cls) -- pas seulement la
     *  premiere.
     *
     *  body: { ns, cls, max? } -> { ok, chaine, instances: [{ptr, classeReelle}] }
     *
     *  ⚠ POURQUOI CE RPC EXISTE. Les trois cibles nommees repondent aux questions PREVUES ; tout
     *  le reste du graphe de vue etait hors de portee, faute d'un point d'entree. Mesure du
     *  2026-08-19 : diagnostiquer une file visuelle figee exigeait de lire un
     *  `Loki_NormalAttackVisuals` VIVANT (`Status`, `_weaponWeaponVisualConfig`) -- objet qu'aucun
     *  chemin de champs n'atteint, parce qu'il n'est stocke NULLE PART : il vit le temps d'un pas
     *  de flux. Seule l'enumeration Unity le trouve.
     *
     *  ⚠ ET IL REND LA LISTE, PAS LA PREMIERE. Meme mesure : apres une retraite suivie d'un
     *  remontage, DEUX `IdunMainView` coexistent et `FindObjectsByType` rend d'abord la MORTE
     *  (celle dont `gameViews` est nul). Un lecteur bati sur « la premiere » conclut « pas de
     *  bataille » alors qu'elle tourne. Ici l'appelant voit les N et tranche lui-meme.
     *
     *  ⚠ CE QU'IL NE PEUT PAS TROUVER, et il le DIT : une classe qui ne derive pas
     *  d'`UnityEngine.Object` rend `instances: []` avec `chaine` publiee -- c'est la chaine
     *  d'heritage qui explique le zero, pas une absence d'instance. Un `Update()` ne fait pas un
     *  MonoBehaviour (`IdunGameViews`, `ViewCommandExecutor`, `thor.Menu.MenuSystems`).
     *
     *  LECTURE PURE : `FindObjectsByType` n'ecrit rien. */
    ctx.rpc.viewInstances = (body?: {
        ns?: string; cls?: string; max?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const ns = body?.ns ?? "";
        const cls = body?.cls ?? "";
        if (!cls) return { ok: false, error: "`cls` requis (et `ns`, sauf namespace global)" };
        const klass = findClassAnywhere(ns, cls);
        if (!klass) return { ok: false, error: `classe introuvable : ${ns}.${cls}` };
        const chaine = chaineHeritage(klass);
        const kObj = findClassAnywhere("UnityEngine", "Object");
        if (!kObj) return { ok: false, error: "UnityEngine.Object introuvable", chaine };
        const mi3 = findMethodByParamCount(kObj, "FindObjectsByType", 3);
        const mi2 = findMethodByParamCount(kObj, "FindObjectsByType", 2);
        if (!mi3 && !mi2) {
            return { ok: false, chaine,
                     error: "`FindObjectsByType` INTROUVABLE (2 et 3 parametres) -- chemin PERIME" };
        }
        const tri = Memory.alloc(4); tri.writeS32(0);
        const inclure = Memory.alloc(4); inclure.writeS32(1);
        let arr: NativePointer;
        try {
            arr = mi3
                ? invokeMethod(mi3.info, null, [getSystemType(klass), inclure, tri])
                : invokeMethod(mi2!.info, null, [getSystemType(klass), tri]);
        } catch (e) {
            return { ok: false, chaine,
                     error: "`FindObjectsByType` a leve : " + (e as Error).message };
        }
        // `null` et « 0 instance » sont deux etats DIFFERENTS : le premier veut dire que la classe
        // n'est pas enumerable (pas un `UnityEngine.Object`), le second qu'elle l'est et qu'il
        // n'y en a aucune de vivante. Les confondre a deja fait conclure a tort.
        if (arr.isNull()) {
            return { ok: true, chaine, instances: null, total: null,
                     note: "`FindObjectsByType` a rendu NULL -- classe NON ENUMERABLE (elle ne "
                         + "derive pas d'`UnityEngine.Object`). Voir `chaine`." };
        }
        const n = arr.add(0x18).readS32();
        const max = Math.max(1, Math.min(body?.max ?? 32, 256));
        const instances: Array<Record<string, unknown>> = [];
        for (let i = 0; i < Math.min(n, max); i += 1) {
            let p: NativePointer;
            try { p = arr.add(0x20 + i * Process.pointerSize).readPointer(); } catch { continue; }
            if (p.isNull()) continue;
            let cn: string | null = null;
            try { cn = s(class_get_name(p.readPointer()) as NativePointer); } catch { /* null */ }
            instances.push({ ptr: p.toString(), classeReelle: cn });
        }
        return { ok: true, chaine, total: n, rendues: instances.length, tronque: n > max,
                 instances };
    });

    /** QUI est joignable, et par quelle voie. Publie la CHAINE D'HERITAGE : c'est elle qui
     *  explique pourquoi l'un s'enumere et l'autre non. */
    ctx.rpc.viewSurface = (): Promise<unknown> => queueOnMainThread(() => {
        const out: Record<string, unknown> = { ok: true, cibles: {} };
        for (const nom of Object.keys(CIBLES) as NomCible[]) {
            const c = CIBLES[nom];
            const k = findClassAnywhere(c.ns, c.cls);
            const r = k ? instanceDe(nom) : { ok: false as const, error: "classe introuvable" };
            (out.cibles as Record<string, unknown>)[nom] = {
                classe: `${c.ns}.${c.cls}`, voie: c.voie,
                classeResolue: k !== null,
                chaine: k ? chaineHeritage(k) : null,
                instance: r === null ? null : (estRefus(r) ? null : r.toString()),
                refus: estRefus(r) ? r.error : null,
            };
        }
        return out;
    });

    /** QUOI existe sur une cible. `filtre` est une sous-chaine insensible a la casse.
     *
     *  `statique: true` marque les methodes appelables SANS instance -- c'est la moitie utile
     *  de la reponse, et elle n'est lisible nulle part ailleurs a chaud. */
    ctx.rpc.viewList = (body?: {
        cible?: string; surPointeur?: string; filtre?: string; max?: number;
    }): unknown => {
        // `surPointeur` accepte ici AUSSI : apres un `viewField`, on veut lister ce qui existe
        // sur la classe REELLE de l'arrivee -- sans quoi on invoquerait a l'aveugle.
        const v = objetVise(body?.cible, body?.surPointeur);
        if (estRefus(v)) return v;
        const k = v.klass;
        const filtre = (body?.filtre ?? "").toLowerCase();
        const max = Math.max(1, Math.min(body?.max ?? 120, 600));
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        const methodes: Array<Record<string, unknown>> = [];
        let total = 0;
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            let mn: string;
            try { mn = s(method_get_name(m) as NativePointer); } catch { continue; }
            total++;
            if (filtre && !mn.toLowerCase().includes(filtre)) continue;
            if (methodes.length >= max) continue;
            const np = method_get_param_count(m) as number;
            const params: string[] = [];
            for (let i = 0; i < np; i++) {
                params.push(methodParamClassName(m, i) ?? "?");
            }
            methodes.push({ nom: mn, params, tricheur: estTricheur(mn) });
        }
        return { ok: true, classe: v.nom, total, rendues: methodes.length, methodes };
    };

    /** APPELER une commande. Corps dans `invoquerCommande` -- ce n'est ici qu'une exposition,
     *  parce que le cycle d'amorce appelle le MEME corps (#993). */
    ctx.rpc.viewInvoke = (body?: {
        cible?: string; surPointeur?: string; methode?: string;
        args?: unknown[]; confirmer?: boolean;
    }): Promise<unknown> | unknown => invoquerCommande(body);
}
