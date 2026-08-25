// L'ETAGE PREFAB — le chargement << a la demande >> des vues d'unite, et la fabrication d'une
// entree de dictionnaire quand le prefab manque.
//
// Extrait de `deployment-draft.ts` le 2026-08-26. La coupe s'est faite par PROPRIETE DE SYMBOLE,
// pas par intervalle de lignes : les diagnostics `Show` / `ClearWidgets` du HUD sont poses AU
// MILIEU du bloc prefab, et une coupe par plage les aurait emportes.
//
// ⚠ `preEmprunt` N'EST PAS IMPORTE, IL EST INJECTE. Il appartient a l'etage POOL, qui vit encore
// dans `deployment-draft` -- lequel importe ce module. L'importer en retour fermerait un cycle
// pour une seule lecture. `deployment-draft` nous passe donc un LECTEUR, et le sens des imports
// reste unique (meme inversion que le fournisseur de placeholders).

import {
    findClassAnywhere, findMethodByParamCount, getFieldOffset, readIl2cppString,
    class_get_name, s, class_get_fields, field_get_type, type_get_class_or_element_class,
    field_get_name, field_get_offset,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, il2cpp_object_new } from "../il2cpp/invoke.js";
import { premiereInstance } from "./view-command.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { elementsDeListe, estRefus as estRefusLecture } from "./lecture-champs.js";
import { Refus, refus, lireTete, teteTriviale, taille, boolBoxe } from "./deployment-socle.js";

/** Le LECTEUR de `preEmprunt`, pose par `deployment-draft` -- cf. l'en-tete. `null` = pas encore
 *  injecte, ce qui n'est PAS la meme chose qu'un pre-emprunt absent. */
let lirePreEmprunt: (() => NativePointer | null) | null = null;
export function enregistrerLecteurPreEmprunt(fn: () => NativePointer | null): void {
    lirePreEmprunt = fn;
}

// ============================================================================
// L'ÉTAGE PREFAB — ET LE CHARGEMENT « À LA DEMANDE » EXISTE DÉJÀ DANS LE JEU.
//
// Symptôme : on sélectionne une unité du roster, elle se GRISE (`TryMarkUnitAsPlaced` rend
// `true`), et le plateau ne bouge pas. `IdunGameViews$$AddPlaceholderUnit` sort en `false` sur
// `UnitIdToPrefabDictionary$$Get` -> `NullableRefExtensions$$TryGet` -> `false`.
//
// CE QUE `Get` FAIT VRAIMENT, et c'est le fait qui commande tout ce bloc :
//
//     ref = dico[GetUnitIdForUniverse(unitId)]      // AssetBundleBattleReference
//     si ref.prefab == null :                       // <-- LE CHARGEMENT PARESSEUX
//         ref.prefab = ref.loader.Invoke()          //     EST DÉJÀ LÀ, dans le jeu
//     return NullableRefUnity(ref.prefab)
//
// ⇒ Il n'y a donc RIEN à charger : il y a une ENTRÉE à créer. Le prefab sera tiré par le jeu
// lui-même, au premier `Get`, exactement là où il le tire pour les unités de `bc.Units`. On
// ne déclenche aucun chargement de bundle depuis un thread Frida — ce qui écarte au passage
// le profil de gel qu'on redoutait.
//
// POURQUOI L'ENTRÉE MANQUE. `UnitIdToPrefabDictionary$$Add` n'a qu'UN SEUL appelant :
// `idun.IdunMainView$$StartBattle`, qui itère `BattleConfiguration.Units`. Notre roster est
// EMPRUNTÉ à la campagne et n'est dans aucune BC — il ne pouvait donc pas avoir de prefab.
//
// LA SÉQUENCE NATIVE, mirroir 1:1 de `StartBattle` :
//
//     holder = new <classe porteuse>()                    // { visualConfig, effectPool }
//     holder.effectPool = thor.Game.Board.EffectPool$$GetInstance()
//     IdunUniverse$$TryGetUnitVisualConfig(univers, visualId, &holder.visualConfig)
//     del = new WidgetPoolReuseHelper.CreateWidget<T>(holder, <méthode du holder>)
//     ref = new AssetBundleBattleReference(del)
//     dico.Add(unitId, ref)
//
// ⚠ AUCUNE de ces classes n'est nommée ici, et c'est le cœur du dispositif. Ghidra ne les
// nomme pas non plus : le ctor d'`AssetBundleBattleReference` s'y appelle
// `UnityEngine.EventSystems.BaseEventData$$.ctor` (corps DÉDUPLIQUÉ — son absence de
// `methods.tsv` ne prouvait rien, cf. le CLAUDE.md), et la classe porteuse n'est qu'un `DAT_`.
// On CAPTURE donc un exemplaire VIVANT : `sandboxModeStart` fait tourner `StartBattle`, donc
// `Add` tire pour chaque unité de la BC. Le patron ainsi capturé porte les trois classes, le
// `m_target` du délégué et l'`EffectPool` — sans une seule adresse en dur, et re-capturé à
// chaque montage, donc insensible au changement de build.
//
// ⚠ ON CLONE, ON NE RECONSTRUIT PAS. Copier l'instance capturée puis n'écraser que le champ
// qui change préserve tout ce que le runtime a calculé (l'`invoke_impl` et le `method_code` du
// délégué, notamment) et évite d'invoquer trois ctors dont un prend un `IntPtr`. Le seul piège
// est en face : le `ref` capturé a SON prefab déjà résolu, donc le clone doit REMETTRE CE SLOT
// À NUL — sans quoi chaque unité ajoutée afficherait le modèle de l'unité capturée, et ça se
// verrait comme un bug de jeu, pas comme un bug de patron.
//
// ⚠ Les slots sont résolus PAR LE TYPE du champ (même doctrine que `bucket-decode`), jamais par
// un offset écrit ici, et le diagnostic PUBLIE le nom réellement trouvé pour que la péremption
// se voie.

export const NS_PREFAB = "IdunBattle.View.Game";

export const CLS_DICO = "UnitIdToPrefabDictionary";

export const CLS_VIEWS_PREFAB = "IdunGameViews";

export interface Champ { nom: string; off: number; type: string }

/** Champs d'instance d'une classe, avec le NOM DE TYPE — la clé de la résolution par type. */
export function champsDe(klass: NativePointer): Champ[] {
    const out: Champ[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let type = "?";
        try {
            const t = field_get_type(f) as NativePointer;
            const k = type_get_class_or_element_class(t) as NativePointer;
            if (!k.isNull()) type = s(class_get_name(k) as NativePointer);
        } catch { /* type illisible : le champ reste listé, avec `?` */ }
        try {
            out.push({ nom: s(field_get_name(f) as NativePointer),
                       off: field_get_offset(f) as number, type });
        } catch { /* champ illisible : on continue plutôt que de tout perdre */ }
    }
    return out;
}

/** Le premier champ dont le type porte `type`. Rend `-1` si absent — jamais un offset deviné. */
export function offsetParType(champs: Champ[], type: string): number {
    const c = champs.find((x) => x.type === type);
    return c ? c.off : -1;
}

/** Ce qu'un `Add` VIVANT nous a appris. Tout est capturé, rien n'est écrit en dur. */
export interface Patron {
    dico: string;
    refClasse: NativePointer; refClasseNom: string;
    offPrefab: number; nomPrefab: string;
    offLoader: number; nomLoader: string;
    delClasse: NativePointer; delClasseNom: string;
    offTarget: number;
    /** ⚠ LE SLOT QUE `Get` LIT VRAIMENT. Le décompilé invoque le loader par
     *  `invoke_impl(delegue->method_code, &retour, delegue->method)` — donc `method_code`,
     *  PAS `m_target`. Ne réécrire que `m_target` laisse le délégué cloné pointer sur la
     *  fermeture DU PATRON : mesuré, deux unités distinctes se sont affichées avec le modèle du
     *  patron, sans la moindre erreur. Les deux champs sont donc écrits, et relus. */
    offMethodCode: number;
    holderClasse: NativePointer; holderClasseNom: string;
    offConfig: number; nomConfig: string;
    /** TOUS les champs du porteur. Publiés : c'est en choisissant le champ « par élimination »
     *  qu'on a écrit la config dans le mauvais slot, et que deux unités distinctes se sont
     *  affichées avec le modèle du patron. Le slot se choisit désormais par le TYPE RÉEL de la
     *  config, à l'écriture — pas par une devinette à la capture. */
    champsHolder: Champ[];
    /** Le corps que le délégué appelle : c'est LUI qui fabrique le prefab. Lu sur le délégué
     *  capturé (`method_ptr`, champ NOMMÉ de `System.Delegate`), donc jamais une adresse écrite. */
    loaderPtr: NativePointer | null;
    /** ⚠ CE QUE `Delegate..ctor` ATTEND, et ce n'est PAS `method_ptr`. En IL2CPP, `ldftn` rend un
     *  `MethodInfo*` déguisé en `IntPtr` : le second argument du ctor est donc le champ `method`
     *  (+0x28), pas le pointeur de code (+0x10). Lui passer le code construit un délégué dont
     *  l'invocateur part sur une sentinelle — mesuré : « access violation accessing
     *  0xffffffffffffffff ». */
    loaderMethodInfo: NativePointer | null;
    tailleRef: number; tailleDel: number; tailleHolder: number;
    exemplaireRef: NativePointer; exemplaireDel: NativePointer; exemplaireHolder: NativePointer;
    unitIdVu: string | null;
}

export let patron: Patron | null = null;

export let patronRefus: string | null = null;

export let listenerAdd: InvocationListener | null = null;

export let addFires = 0;

export const prefabCharges: Array<{ unitId: string; ok: boolean; detail: string }> = [];

// ⚠ LES POINTEURS QUE LE JEU UTILISE VRAIMENT — la seule autorité.
//
// Mesuré session 52 : `HasPrefabForUnitId` rend `true` pour `spaceBlackmane` alors que le `Get`
// du jeu rend NUL pour la même unité. Or les deux corps font le MÊME `ContainsKey`, sur le MÊME
// champ, avec la MÊME clé — sur une seule et même instance ils ne PEUVENT pas diverger. Donc ils
// portent sur DEUX objets différents, et c'est ma lecture qui visait le mauvais.
//
// La cause est la voie d'accès : aller CHERCHER la vue (`FindObjectsByType`, ou le dernier `this`
// vu par le pump) rend *une* vue, pas *celle que le déploiement utilise*. On enregistre donc les
// pointeurs tels qu'ils passent dans les appels du jeu, et tout le reste s'y adosse.
export const dicosVusParAdd = new Map<string, number>();

/** Les unitIds que `Add` a inscrits — donc ceux dont le prefab EXISTE, sans rien fabriquer. */
export const idsAvecPrefab: string[] = [];

export let dicoDeGet: NativePointer | null = null;     // le `this` du dernier `Get` -- l'AUTORITÉ

export let vuesDePose: NativePointer | null = null;    // le `this` d'`Enable` / `AddPlaceholderUnit`

export let listenerVue: InvocationListener | null = null;

export const listenersVue: InvocationListener[] = [];

/** Ce qu'a donné chaque tentative de capture de la vue. Publié — jamais avalé. */
export const captureVue: string[] = [];

/**
 * Le dictionnaire ET la vue que LE JEU utilise pour le déploiement.
 *
 * ⚠ ORDRE DE PRÉFÉRENCE, et il n'est pas cosmétique : on prend d'abord ce qu'on a VU PASSER dans
 * les appels du jeu (`Get`, `AddPlaceholderUnit`), puis seulement à défaut une vue qu'on va
 * chercher. C'est exactement l'erreur qui a produit la contradiction `HasPrefabForUnitId=true` /
 * `Get=NUL` : une vue trouvée n'est pas la vue employée. La SOURCE est publiée à chaque appel,
 * pour qu'un résultat obtenu par le repli ne se lise jamais comme un résultat autoritaire.
 */
export function dicoVivant(): { dico: NativePointer; vues: NativePointer; source: string } | Refus {
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!kv) return refus(`\`${NS_PREFAB}.${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
    const off = offsetParType(champsDe(kv), CLS_DICO);
    if (off < 0) {
        return refus(`aucun champ de type \`${CLS_DICO}\` sur \`${CLS_VIEWS_PREFAB}\` -- `
            + "chemin PÉRIMÉ, pas de repli sur un offset");
    }
    // (1) L'AUTORITÉ : la vue sur laquelle le jeu vient d'appeler `AddPlaceholderUnit`.
    if (vuesDePose !== null && !vuesDePose.isNull()) {
        const dico = vuesDePose.add(off).readPointer();
        if (!dico.isNull()) {
            return { dico, vues: vuesDePose, source: "vue OBSERVÉE dans `AddPlaceholderUnit`" };
        }
    }
    // (2) Le dictionnaire vu dans `Get` : autoritaire lui aussi, mais il ne donne pas la vue,
    // donc il ne suffit pas pour `GetUnitVisualConfig`.
    if (dicoDeGet !== null && !dicoDeGet.isNull() && vuesDePose === null) {
        return refus("le dictionnaire du jeu est connu (" + dicoDeGet
            + ") mais AUCUNE vue n'a encore été observée : `GetUnitVisualConfig` a besoin de la "
            + "vue. Tenter une pose d'abord (elle échouera, et elle publiera la vue).");
    }
    // (3) Repli : une vue qu'on va chercher. Peut viser à côté -- on le DIT.
    const trouve = premiereInstance(kv);
    if (!(trouve instanceof NativePointer)) return refus(trouve.error + " (repli)");
    if (trouve.isNull()) return refus("`FindObjectsByType` a rendu un pointeur NUL (repli)");
    const dico = trouve.add(off).readPointer();
    if (dico.isNull()) return refus("le champ dictionnaire est NUL sur la vue trouvée (repli)");
    return { dico, vues: trouve,
             source: "REPLI `FindObjectsByType` -- PAS forcément la vue du déploiement" };
}

/** Arme la CAPTURE du patron sur `Add`. Observation pure : n'écrit rien, ne remplace rien. */
export function armerPrefab(): true | Refus {
    if (listenerAdd) return true;
    const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
    if (!kd) return refus(`\`${NS_PREFAB}.${CLS_DICO}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(kd, "Add", 2);
    if (!mi) return refus(`\`${CLS_DICO}$$Add\` INTROUVABLE (2 paramètres)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`Add\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_DICO}$$Add\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE par déduplication. Cf. §8.`);
    }
    // La VUE, captée au montage plutôt qu'à la première pose. Le `this` de ces méthodes EST la
    // vue employée — donc autoritaire, au même titre que celui d'`AddPlaceholderUnit`, mais
    // disponible sans attendre un clic de l'utilisateur.
    //
    // ⚠ DEUX candidates, et le RÉSULTAT DE CHACUNE EST PUBLIÉ. La version précédente n'en tentait
    // qu'une et AVALAIT l'échec : le hook n'a pas tiré, `vuesDePose` est resté nul, et il a fallu
    // un aller-retour avec l'utilisateur pour découvrir que le capteur n'était pas armé. Un
    // capteur qui échoue en silence coûte plus cher que pas de capteur du tout.
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!listenerVue && kv) {
        // ⚠ DEUX CORRECTIFS ICI, ET LE SECOND EST CELUI QUI COMPTE.
        //
        // (1) L'affectation était CONDITIONNELLE (`if (vuesDePose === null)`) : un verrou. Une
        //     fois posée, elle ne suivait plus jamais.
        // (2) L'armement s'ARRÊTAIT AU PREMIER trouvé — `Continue` — qui ne tire PAS d'une
        //     bataille à l'autre. Corriger (1) seul ne changeait donc RIEN : mesuré, second
        //     montage encore à `total=0` avec le pointeur figé pendant 12 s.
        //
        // On en arme donc PLUSIEURS. `Initialize` tire à chaque mise en place de plateau ;
        // `AddUnit` est l'autorité absolue, puisque l'objet qui la reçoit EST celui qui porte
        // les vues qu'on compte ensuite.
        //
        // ⚠ Le symptôme était MUET et TROMPEUR : `0 unité` se lit « plateau vide » alors que
        // l'écran montrait les unités. C'est l'observation de l'utilisateur qui a tranché,
        // pas mes chiffres.
        for (const [nom, np] of
             [["Initialize", 2], ["AddUnit", 7], ["Continue", 0], ["Enable", 1]] as const) {
            const mv = findMethodByParamCount(kv, nom, np);
            if (!mv) { captureVue.push(`${nom}(${np}) : INTROUVABLE`); continue; }
            const tv = lireTete(mv.ptr);
            if (tv.erreur !== null) { captureVue.push(`${nom} : tête ILLISIBLE`); continue; }
            if (teteTriviale(tv)) { captureVue.push(`${nom} : corps TRIVIAL, refusé`); continue; }
            listenersVue.push(Interceptor.attach(mv.ptr, {
                onEnter(args) { if (!args[0].isNull()) vuesDePose = args[0]; },
            }));
            captureVue.push(`${nom} : ARMÉ`);
        }
        listenerVue = listenersVue.length > 0 ? listenersVue[0] : null;
        if (listenersVue.length === 0) captureVue.push("AUCUN capteur de vue armé -- `vuesDePose` "
            + "ne suivra PAS les changements de bataille");
    }
    listenerAdd = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            addFires++;
            // QUEL dictionnaire a été rempli, et combien de fois chacun. C'est ce comptage qui
            // distingue « 68 prefabs chargés » de « 68 prefabs chargés AILLEURS ».
            const cle = args[0].toString();
            dicosVusParAdd.set(cle, (dicosVusParAdd.get(cle) ?? 0) + 1);
            // LES IDS QUI ONT UN PREFAB, par construction : ce sont ceux que le jeu vient de
            // charger. C'est la bonne source pour le roster -- inutile d'en fabriquer d'autres.
            try {
                const nom = readIl2cppString(args[1]);
                if (nom !== null && nom !== "" && idsAvecPrefab.indexOf(nom) < 0) {
                    idsAvecPrefab.push(nom);
                }
            } catch { /* best effort */ }
            if (patron !== null) return;          // un seul patron suffit
            try { patronRefus = capturerPatron(args[0], args[1], args[2]); }
            catch (e) { patronRefus = "capture levée : " + (e as Error).message; }
        },
    });
    Interceptor.flush();
    return true;
}

/** Décortique un `Add` réel. Rend `null` si le patron est complet, sinon la RAISON du refus. */
export function capturerPatron(dico: NativePointer, unitId: NativePointer,
                        ref: NativePointer): string | null {
    if (ref.isNull()) return "la référence passée à `Add` est NULLE";
    const kRef = ref.readPointer();
    const nomRef = s(class_get_name(kRef) as NativePointer);
    const champsRef = champsDe(kRef);
    // Le prefab est le champ `GameObject` ; le loader est le SEUL autre champ référence.
    const offPrefab = offsetParType(champsRef, "GameObject");
    if (offPrefab < 0) {
        return `aucun champ de type \`GameObject\` sur \`${nomRef}\` -- champs vus : `
            + champsRef.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    const cLoader = champsRef.find((c) => c.off !== offPrefab && c.type !== "?");
    if (!cLoader) return `aucun champ loader identifiable sur \`${nomRef}\``;
    const del = ref.add(cLoader.off).readPointer();
    if (del.isNull()) return "le champ loader est NUL sur l'exemplaire capturé";
    const kDel = del.readPointer();
    const nomDel = s(class_get_name(kDel) as NativePointer);
    // `m_target` est un champ NOMMÉ de `System.Delegate` : on le résout par son nom, pas par
    // la disposition supposée d'`Il2CppDelegate`.
    const offTarget = getFieldOffset(kDel, "m_target");
    if (offTarget < 0) return `\`m_target\` absent de \`${nomDel}\``;
    const holder = del.add(offTarget).readPointer();
    if (holder.isNull()) return "le `m_target` du délégué capturé est NUL";
    const kHolder = holder.readPointer();
    const nomHolder = s(class_get_name(kHolder) as NativePointer);
    const champsHolder = champsDe(kHolder);
    // La config visuelle est ce que `TryGetUnitVisualConfig` écrit ; on la repère par le champ
    // dont le type n'est PAS le pool d'effets.
    const cConfig = champsHolder.find((c) => c.type.indexOf("EffectPool") < 0 && c.type !== "?");
    if (!cConfig) {
        return `aucun champ de config visuelle sur \`${nomHolder}\` -- champs vus : `
            + champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    patron = {
        dico: dico.toString(),
        refClasse: kRef, refClasseNom: nomRef,
        offPrefab, nomPrefab: champsRef.find((c) => c.off === offPrefab)?.nom ?? "?",
        offLoader: cLoader.off, nomLoader: cLoader.nom,
        delClasse: kDel, delClasseNom: nomDel, offTarget,
        offMethodCode: getFieldOffset(kDel, "method_code"),
        holderClasse: kHolder, holderClasseNom: nomHolder,
        offConfig: cConfig.off, nomConfig: cConfig.nom, champsHolder,
        loaderPtr: (() => {
            const o = getFieldOffset(kDel, "method_ptr");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        loaderMethodInfo: (() => {
            const o = getFieldOffset(kDel, "method");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        tailleRef: taille(kRef), tailleDel: taille(kDel), tailleHolder: taille(kHolder),
        exemplaireRef: ref, exemplaireDel: del, exemplaireHolder: holder,
        unitIdVu: (() => { try { return readIl2cppString(unitId); } catch { return null; } })(),
    };
    // Le patron sert de gabarit BIEN APRÈS le `Add` qui l'a fourni : sans racine, le GC peut
    // ramasser les trois exemplaires entre la capture et la première fabrication.
    gcRoot.add(ref); gcRoot.add(del); gcRoot.add(holder);
    return null;
}

/** Clone une instance managée : même classe, mêmes octets, en-tête neuf. */
export function cloner(source: NativePointer, klass: NativePointer, taille: number): NativePointer {
    const copie = il2cpp_object_new(klass) as NativePointer;
    if (copie.isNull()) throw new Error("`il2cpp_object_new` a rendu NUL");
    // L'en-tête (klass + monitor, 2 pointeurs) vient de l'allocation ; on ne copie QUE le corps.
    const debut = Process.pointerSize * 2;
    Memory.copy(copie.add(debut), source.add(debut), Math.max(0, taille - debut));
    return copie;
}

/**
 * Les ids du roster, lus dans la liste PRÉ-EMPRUNTÉE à la campagne.
 *
 * ⚠ POURQUOI C'EST NÉCESSAIRE, ET PAS UN CONFORT. Charger « les unités qu'on croit utiles »
 * fait porter à l'utilisateur la traduction portrait -> identifiant : il a cliqué
 * `admecMarshall` en pensant désigner un héros de la liste que j'avais chargée, et l'essai n'a
 * rien mesuré du tout. Un écran est utilisable quand TOUT ce qu'il montre est posable.
 *
 * La liste est un `PooledListElement\`1` : on descend dans `_object` (le `List\`1` réel), puis on
 * lit `_size` et `_items` PAR LEUR NOM. Aucun offset écrit ici.
 */
export function listeDuRoster(): string[] | Refus {
    // ⚠ LU PAR L'INJECTION, jamais importe -- cf. l'en-tete du module. `null` couvre les DEUX
    // cas (lecteur pas encore pose, pre-emprunt absent) et le refus ci-dessous les nomme.
    const preEmprunt = lirePreEmprunt ? lirePreEmprunt() : null;
    if (preEmprunt === null || preEmprunt.isNull()) {
        return refus("aucun pré-emprunt en main -- jouer `deploymentPoolPreEmprunt` d'abord");
    }
    try {
        const kWrap = preEmprunt.readPointer();
        let liste = preEmprunt;
        const offObj = getFieldOffset(kWrap, "_object");
        if (offObj > 0) {
            const interne = preEmprunt.add(offObj).readPointer();
            if (interne.isNull()) return refus("`_object` du wrapper de pool est NUL");
            liste = interne;
        }
        const kListe = liste.readPointer();
        const offItems = getFieldOffset(kListe, "_items");
        const offSize = getFieldOffset(kListe, "_size");
        if (offItems < 0 || offSize < 0) {
            return refus(`\`_items\`/\`_size\` absents de \`${s(class_get_name(kListe) as
                NativePointer)}\` -- chemin PÉRIMÉ`);
        }
        const n = liste.add(offSize).readS32();
        const items = liste.add(offItems).readPointer();
        if (items.isNull()) return refus("`_items` est NUL");
        if (n < 0 || n > 4096) return refus(`taille invraisemblable (${n}) -- on ne lit RIEN`);
        const out: string[] = [];
        // ⚠ LES ÉLÉMENTS NE SONT PAS FORCÉMENT DES CHAÎNES. `GetUnitsForDeploymentHUD` MAPPE la
        // liste : ses éléments sont des MODÈLES d'unité. `readIl2cppString` dessus ne rend rien,
        // et la première version rendait donc une liste VIDE -- que l'appelant a rapportée comme
        // « `tout` non demandé ». Un vide silencieux vaut pire qu'une erreur.
        let classeElement: string | null = null;
        let offId = -1;
        for (let i = 0; i < n; i++) {
            // Tableau managé : longueur à +0x18, premier élément à +0x20.
            const el = items.add(0x20 + i * Process.pointerSize).readPointer();
            if (el.isNull()) continue;
            const ke = el.readPointer();
            if (classeElement === null) {
                classeElement = s(class_get_name(ke) as NativePointer);
                if (classeElement !== "String") {
                    // L'id se trouve sur le modèle : champ String nommé, résolu PAR SON NOM.
                    for (const nom of ["unitId", "UnitId", "id", "Id",
                                       "<UnitId>k__BackingField", "<unitId>k__BackingField"]) {
                        const o = getFieldOffset(ke, nom);
                        if (o >= 0) { offId = o; break; }
                    }
                    if (offId < 0) {
                        return refus(`les éléments sont des \`${classeElement}\`, et aucun champ `
                            + "d'id n'y est reconnu -- champs : "
                            + champsDe(ke).map((c) => `${c.nom}:${c.type}`).join(", "));
                    }
                }
            }
            const v = classeElement === "String"
                ? readIl2cppString(el)
                : readIl2cppString(el.add(offId).readPointer());
            if (v !== null && v !== "") out.push(v);
        }
        if (out.length === 0) {
            return refus(`liste lue (taille ${n}, éléments \`${classeElement ?? "?"}\`) mais AUCUN `
                + "id extrait -- on refuse plutôt que de rendre un vide qui se lirait comme "
                + "« rien à charger »");
        }
        return out;
    } catch (e) { return refus("lecture du roster levée : " + (e as Error).message); }
}

/**
 * Fabrique l'entrée manquante d'UNE unité, sur le patron capturé. Rend le détail — jamais un
 * booléen nu : chaque refus doit se lire.
 *
 * ⚠ N'appelle AUCUN chargement d'asset. Elle pose un triplet PARESSEUX (`_prefab` à nul) ;
 * c'est le corps natif de `Get` qui invoquera le loader ensuite, exactement comme il le fait
 * pour les unités de la BC. Le coût reste donc proportionnel à ce qui est RÉELLEMENT posé.
 */
export function fabriquerEntree(
    p: Patron, dico: NativePointer, vues: NativePointer, id: string,
    mHas: MethodRefLike, mAdd: MethodRefLike, mCfg: MethodRefLike,
): { ok: boolean; detail: string; ref?: NativePointer } {
    try {
        const sid = createManagedString(id);
        // `Add` LÈVE sur clé dupliquée : on ne tente que ce qui manque vraiment.
        if (boolBoxe(invokeMethod(mHas.info, dico, [sid]))) {
            return { ok: true, detail: "déjà présent -- rien fait" };
        }
        // Lecture pure (`UnitConfigMap.TryGetValue`), aucun asset touché.
        const cfg = invokeMethod(mCfg.info, vues, [sid]);
        if (cfg.isNull()) {
            return { ok: false, detail: "`GetUnitVisualConfig` rend NUL -- pas de config visuelle "
                + "dans l'univers chargé ; on n'invente rien" };
        }
        // LE SLOT SE CHOISIT PAR LE TYPE RÉEL DE `cfg`, pas par élimination. Mesuré : le choix
        // « le premier champ qui n'est pas l'EffectPool » visait un autre membre de la fermeture,
        // la config du patron restait en place, et DEUX unités s'affichaient avec SON modèle.
        const nomCfg = s(class_get_name(cfg.readPointer()) as NativePointer);
        const cible = p.champsHolder.find((c) => c.type === nomCfg);
        if (!cible) {
            return { ok: false, detail: `aucun champ de type \`${nomCfg}\` sur `
                + `\`${p.holderClasseNom}\` -- champs : `
                + p.champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ")
                + " ; on n'écrit RIEN plutôt qu'à côté" };
        }
        if (p.loaderMethodInfo === null) {
            return { ok: false, detail: "`method` (le `MethodInfo*`) du délégué capturé "
                + "ILLISIBLE -- on ne construit pas de délégué sans lui" };
        }
        const ctorDel = findMethodByParamCount(p.delClasse, ".ctor", 2);
        if (!ctorDel) {
            return { ok: false, detail: `\`${p.delClasseNom}..ctor\` (2 paramètres) INTROUVABLE` };
        }
        const holder = cloner(p.exemplaireHolder, p.holderClasse, p.tailleHolder);
        holder.add(cible.off).writePointer(cfg);
        // RELECTURE : une écriture non vérifiée est ce qui a produit deux modèles identiques
        // sans la moindre erreur.
        if (!holder.add(cible.off).readPointer().equals(cfg)) {
            return { ok: false, detail: `écriture NON CONFIRMÉE dans \`${cible.nom}\`` };
        }
        // ⚠ ON CONSTRUIT LE DÉLÉGUÉ, ON NE LE CLONE PAS — et les deux tentatives précédentes
        // établissent pourquoi. `method_code` (+0x40), que `Get` passe à l'invocateur, n'est pas
        // la CIBLE mais un pointeur de CODE, vers un trampoline où la cible est déjà scellée :
        //   * ne réécrire que `m_target` -> pas de crash, mais le trampoline appelle toujours la
        //     fermeture du PATRON (mesuré : deux unités affichées avec SON modèle) ;
        //   * écrire le porteur dans `method_code` -> l'invocateur saute sur des données
        //     (mesuré : « access violation accessing 0x... » levée par `Get`).
        // Un délégué ne se re-cible donc pas par écriture de champ. `StartBattle` l'instancie par
        // `.ctor(cible, pointeur_de_méthode)` — on fait pareil, et le runtime bâtit le trampoline.
        const del = il2cpp_object_new(p.delClasse) as NativePointer;
        if (del.isNull()) return { ok: false, detail: "`il2cpp_object_new` (délégué) a rendu NUL" };
        // Un `IntPtr` est un TYPE VALEUR : `runtime_invoke` en attend l'ADRESSE, pas la valeur.
        const boiteFn = Memory.alloc(Process.pointerSize);
        boiteFn.writePointer(p.loaderMethodInfo);
        invokeMethod(ctorDel.info, del, [holder, boiteFn]);
        const cibleRelue = del.add(p.offTarget).readPointer();
        if (!cibleRelue.equals(holder)) {
            return { ok: false, detail: `délégué construit mais \`m_target\` vaut ${cibleRelue} `
                + `au lieu de ${holder} -- on n'inscrit RIEN` };
        }
        const ref = cloner(p.exemplaireRef, p.refClasse, p.tailleRef);
        // ⚠ LE SLOT QUI DOIT REPARTIR À NUL : le patron a son prefab déjà résolu ; le laisser
        // afficherait le modèle de l'unité capturée.
        ref.add(p.offPrefab).writePointer(ptr(0));
        ref.add(p.offLoader).writePointer(del);
        gcRoot.add(holder); gcRoot.add(del); gcRoot.add(ref);
        invokeMethod(mAdd.info, dico, [sid, ref]);
        return { ok: true, ref, detail: `entrée créée -- config ${nomCfg} @ \`${cible.nom}\`` };
    } catch (e) { return { ok: false, detail: "LEVÉ : " + (e as Error).message }; }
}

/** Ce dont `fabriquerEntree` a besoin d'une méthode : son `MethodInfo*`. */
export interface MethodRefLike { info: NativePointer }

export function etatPrefab(): Record<string, unknown> {
    return {
        arme: listenerAdd !== null,
        addFires,
        patron: patron === null ? null : {
            reference: patron.refClasseNom,
            champPrefab: `${patron.nomPrefab}@+0x${patron.offPrefab.toString(16)}`,
            champLoader: `${patron.nomLoader}@+0x${patron.offLoader.toString(16)}`,
            delegue: patron.delClasseNom,
            porteur: patron.holderClasseNom,
            champConfig: `${patron.nomConfig}@+0x${patron.offConfig.toString(16)}`,
            champsDuPorteur: patron.champsHolder.map((c) => `${c.nom}:${c.type}`),
            unitIdVu: patron.unitIdVu,
        },
        // LE COMPTAGE QUI TRANCHE : si `Add` a rempli un dictionnaire et que `Get` en lit un
        // AUTRE, « N prefabs chargés » ne dit rien sur ce que le déploiement voit.
        dicosRemplisParAdd: Array.from(dicosVusParAdd, ([p, n]) => ({ dico: p, adds: n })),
        dicoLuParGet: dicoDeGet === null ? null : dicoDeGet.toString(),
        idsAvecPrefab,
        vueDePose: vuesDePose === null ? null : vuesDePose.toString(),
        captureVue,
        dicoDuPatron: patron === null ? null : patron.dico,
        // TRI-ÉTAT : `null` = aucun refus ENREGISTRÉ, ce qui n'est pas « tout va bien » tant
        // qu'`addFires` vaut 0.
        refusDeCapture: patronRefus,
        charges: prefabCharges.slice(-24),
    };
}

// --- LES TROIS ETATS QUE `deployment-draft` MUTE ---------------------------------------------
//
// ⚠ ESM INTERDIT D'ASSIGNER UN IMPORT (`TS2632`), et c'est une bonne contrainte : elle rend
// visible que ces trois pointeurs appartiennent a CE module alors qu'ils sont ecrits par les
// capteurs de l'autre. Tant que les capteurs n'auront pas suivi, l'ecriture passe par un
// accesseur nomme -- ce qui laisse au moins une trace greppable de la dependance.
export function definirVuesDePose(p: NativePointer | null): void { vuesDePose = p; }
export function definirDicoDeGet(p: NativePointer | null): void { dicoDeGet = p; }
export function definirListenerAdd(l: InvocationListener | null): void { listenerAdd = l; }
