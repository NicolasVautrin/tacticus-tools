/** #982-r6 — FORÇAGE D'INITIALISATION d'une classe IL2CPP, et l'état qui rend la lecture
 *  interprétable.
 *
 *  ## Le résidu
 *
 *  IL2CPP ne remplit la VTABLE (ni le bloc de statiques) d'une classe qu'à son INITIALISATION.
 *  Une classe d'effet jamais instanciée dans la session rend donc des slots à ZÉRO —
 *  indiscernables d'un « aucun override ». Mesuré : `probe_916r1_effect_slots.py` range
 *  **221 classes sur 465** en `NON MESUREE`, ce qui est le bon tri-état mais laisse le trou
 *  entier. `resolveVtableSlot` (`features/introspect.ts`) n'avait **aucun** moyen de le combler ;
 *  `probes/static-field-probe.ts`, lui, savait déjà forcer sous drapeau explicite.
 *
 *  Ce module est le FOYER UNIQUE de ce geste — au lieu de la copie de cinq lignes qui aurait
 *  propagé le motif d'un module à l'autre. Les deux consommateurs en héritent la même
 *  discipline, et le contrôle hors Frida (`tools/probe-1072-capteurs-fenetre.ts`) les couvre
 *  tous les deux d'un coup.
 *
 *  ## L'ORDRE EST LE CRAN, ET C'EST LUI QUE LE CONTRÔLE GARDE
 *
 *  `initializedBefore` se lit **AVANT** le forçage. Le forcer d'abord détruirait la seule
 *  information qui dise au lecteur ce qu'il tient : une classe déjà chaude mesure l'état RÉEL du
 *  jeu ; une classe forcée mesure un état que le capteur a lui-même créé. Les deux sont utiles,
 *  les confondre ne l'est pas — c'est la version « vtable » du piège que `static-field-probe.ts`
 *  documente sur les statiques (« un lecteur qui voit `initialized: false` ne tient pas une
 *  mesure »).
 *
 *  ## Discipline
 *
 *  Le forçage est le SEUL appel de cette chaîne qui ait un effet, il est sous drapeau explicite,
 *  et c'est littéralement ce que le jeu fait lui-même au premier accès. `runtimeClassInitAvailable`
 *  et `forceInitError` existent pour qu'un forçage IMPOSSIBLE se lise comme tel, jamais comme un
 *  forçage réussi.
 */
import { runtime_class_init } from "./helpers.js";

/** Façade des primitives dont dépend le forçage. Elle existe pour rendre `classInitState`
 *  EXÉCUTABLE hors du process de jeu (mêmes motifs que `RarityProbe` / `TertiaryProbe`). */
export interface ClassInitProbe {
    /** `Il2CppClass.initialized_and_no_error`, ou `null` si l'offset ne se lit pas.
     *  `null` = PAS MESURÉ — jamais rabattu sur `false`, qui est une valeur du domaine. */
    readInitialized(klass: NativePointer): boolean | null;
    /** `il2cpp_runtime_class_init`, ou `null` si l'export manque sur ce build. */
    forceInit: ((klass: NativePointer) => void) | null;
}

export interface ClassInitState {
    /** L'état AVANT toute action de ce capteur. C'est la seule valeur qui décrive le JEU. */
    initializedBefore: boolean | null;
    /** `true` seulement si le forçage a été demandé ET a effectivement tourné. */
    forcedInit: boolean;
    /** L'état APRÈS. Égal à `initializedBefore` quand on n'a rien forcé. */
    initialized: boolean | null;
    runtimeClassInitAvailable: boolean;
    /** Pourquoi le forçage demandé n'a pas eu lieu. `null` = rien à signaler (soit il n'a pas
     *  été demandé, soit il a réussi). Un forçage impossible doit se LIRE, pas se deviner. */
    forceInitError: string | null;
}

/** `Il2CppClass.initialized_and_no_error` vit à `+0xe4` sur ce build — c'est LITTÉRALEMENT
 *  l'offset que tout corps décompilé teste. On ne s'en sert QUE pour RAPPORTER l'état, jamais
 *  pour décider d'une lecture : si l'offset devenait faux, on publierait un état faux, pas une
 *  valeur fausse. */
export const CLASS_INITIALIZED_OFF = 0xe4;

/** L'implémentation de PRODUCTION. Les deux consommateurs passent par elle — c'est ce qui fait
 *  qu'ils ne peuvent pas diverger. */
const RCI = runtime_class_init;

export const LIVE_CLASS_INIT_PROBE: ClassInitProbe = {
    readInitialized: (klass) => {
        try { return klass.add(CLASS_INITIALIZED_OFF).readS32() !== 0; }
        catch { return null; }   // offset hors structure : `null`, jamais un booleen invente
    },
    forceInit: RCI === null ? null : (klass) => { RCI(klass); },
};

/** Lit l'état, force si (et seulement si) on le demande, relit. Ne lève jamais. */
export function classInitState(
    probe: ClassInitProbe, klass: NativePointer, force: boolean,
): ClassInitState {
    const available = probe.forceInit !== null;
    // 1. AVANT toute action — cf. « L'ORDRE EST LE CRAN » ci-dessus.
    const initializedBefore = probe.readInitialized(klass);
    let forcedInit = false;
    let forceInitError: string | null = null;
    if (force) {
        if (probe.forceInit === null) {
            forceInitError = "`il2cpp_runtime_class_init` n'est pas exporte par ce build --"
                + " l'initialisation n'a PAS ete forcee ; les slots a zero restent"
                + " indiscernables d'une absence d'override";
        } else {
            try { probe.forceInit(klass); forcedInit = true; }
            catch (e) { forceInitError = "forcage en echec: " + (e as Error).message; }
        }
    }
    // 2. APRÈS. Une relecture même sans forçage : elle ne coûte rien et rend le contrat uniforme.
    const initialized = probe.readInitialized(klass);
    return {
        initializedBefore, forcedInit, initialized,
        runtimeClassInitAvailable: available, forceInitError,
    };
}
