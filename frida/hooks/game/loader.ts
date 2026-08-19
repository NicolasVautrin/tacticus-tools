// loader — l'etat du CHARGEUR DE SCENES du jeu (`thor.Loader`), lisible sans rien invoquer.
//
// POURQUOI CETTE LIB EXISTE (#993). `thor.Loader$$LoadScene` REFUSE EN SILENCE de charger quand
// un chargement est deja en cours : il teste `_scenesToLoad.Count >= 1` ou `IsLoadingInternal`
// (c.-a-d. `_loadingStep > 0`), journalise par `IdunViewLogger$$Log`, et RETOURNE. Aucun code de
// retour, aucune exception. Tout geste qui declenche un changement de scene pendant cette fenetre
// est donc ANNULE sans un mot -- et le symptome est trompeur : le jeu reste vivant, repond aux
// RPC, mais n'affiche plus rien.
//
// C'est ce qui a bloque le jeu TROIS fois pendant #993 : l'amorce se retirait de bataille entre
// 8 et 10 s apres le lancement, le retour au meta etait refuse, et il fallait relancer le jeu.
//
// MESURE DU 2026-08-13 (statique relue toutes les ~900 ms apres `StartCampaignMatch`) :
//
//     t=1,1 s   __loadingStep = 1
//     t=3,1 s   __loadingStep = 6
//     t=9,8 s   __loadingStep = 10
//     t=10,8 s  __loadingStep = 0     <- chargement TERMINE
//
// ⚠ ET AUCUN AUTRE SIGNAL NE REPOND A CETTE QUESTION -- cinq mesures, cinq ecarts :
//   `IdunMainView$$get_IsBattleActive()` bascule des 6,8 s ; l'instance d'`IdunMainView` est
//   vivante avant ; `UnitSelectionFsm` rend `UnitDeploymentState` des 1,2 s ; les objets d'UI du
//   deploiement sont la a 8,8 s ; et le popup de confirmation de retraite s'affiche PAR-DESSUS
//   une bataille encore en chargement. Chacun de ces signaux dit « la bataille existe » ; aucun
//   ne dit « le chargeur a fini ».
//
// PORTEE. Rien ici n'est propre a l'amorce : c'est l'etat du chargeur, et il conditionne TOUT
// changement de scene (entree en bataille, retour au meta, navigation qui recharge). Tout geste
// qui en declenche un devrait le consulter d'abord.
//
// ⚠ TRI-ETAT PARTOUT. `null` = NON MESURE (classe non initialisee, export absent, champ renomme
// au prochain build), jamais rabattu sur « rien ne charge » -- c'est cette confusion-la qui
// casse le jeu, puisqu'elle autorise le geste au pire moment.

import { staticFieldProbe } from "../probes/static-field-probe.js";
import { Ctx } from "../controller.js";

const NS = "thor";
const CLS = "Loader";

/** Le champ statique qui porte l'etape de chargement. Le nom est ce qu'on resout -- jamais
 *  l'offset : `staticFieldProbe` passe par `il2cpp_field_static_get_value`, la voie NOMMEE, donc
 *  un renommage au prochain build se lit comme « champ absent » et non comme une valeur fausse. */
const CHAMP_ETAPE = "__loadingStep";

interface LigneStatique { name: string; asInt32: number | null; typeName: string | null }
interface RetourProbe {
    ok?: boolean;
    error?: string;
    initialized?: boolean;
    fields?: LigneStatique[];
}

function lire(champs: string[]): RetourProbe | null {
    try {
        return staticFieldProbe({ ns: NS, cls: CLS, fields: champs }) as RetourProbe;
    } catch {
        return null;
    }
}

/** L'ETAPE DE CHARGEMENT COURANTE, brute. `0` = aucun chargement en cours.
 *
 *  `null` = NON MESUREE. Trois causes, toutes traitees pareil parce qu'aucune n'autorise a
 *  conclure : le probe a echoue, la classe n'est pas initialisee (son bloc de statiques est alors
 *  a ZERO -- un zero qui se lirait « rien ne charge »), ou le champ n'existe plus. */
export function etapeDeChargement(): number | null {
    const r = lire([CHAMP_ETAPE]);
    if (r?.ok !== true || r.initialized !== true) return null;
    const f = (r.fields ?? []).find((x) => x.name === CHAMP_ETAPE);
    return f && f.asInt32 !== null ? f.asInt32 : null;
}

/** UN CHANGEMENT DE SCENE EST-IL EN COURS ? `true` ⇒ tout geste qui en declencherait un autre
 *  sera refuse EN SILENCE. `null` = non mesure : ne pas agir. */
export function chargementEnCours(): boolean | null {
    const e = etapeDeChargement();
    return e === null ? null : e !== 0;
}

/** L'etat complet, pour un lecteur humain ou un diagnostic. Publie la RAISON quand il ne peut
 *  pas mesurer, plutot qu'un champ vide. */
export function etatDuChargeur(): Record<string, unknown> {
    const r = lire([CHAMP_ETAPE]);
    if (r === null) {
        return { ok: false, error: "staticFieldProbe a leve", etape: null, chargementEnCours: null };
    }
    if (r.ok !== true) {
        return { ok: false, error: r.error ?? "?", etape: null, chargementEnCours: null };
    }
    const f = (r.fields ?? []).find((x) => x.name === CHAMP_ETAPE);
    const etape = r.initialized === true && f && f.asInt32 !== null ? f.asInt32 : null;
    return {
        ok: true,
        classe: `${NS}.${CLS}`,
        initialisee: r.initialized === true,
        champ: CHAMP_ETAPE,
        etape,
        chargementEnCours: etape === null ? null : etape !== 0,
        note: r.initialized === true
            ? undefined
            : "classe NON INITIALISEE -- son bloc de statiques est a zero, donc `etape` est "
              + "rendue `null` et non `0` : un zero lu ici se lirait « rien ne charge »",
    };
}

export function register(ctx: Ctx): void {
    /** L'etat du chargeur, a la demande. Lecture PURE -- aucun invoke, aucun ancrage. */
    ctx.rpc.loaderStatus = (): unknown => etatDuChargeur();
}
