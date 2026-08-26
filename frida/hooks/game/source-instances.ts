// LE REGISTRE DES INSTANCES DE SOURCE, PAR CLASSE — et il VALIDE avant de rendre.
//
// POURQUOI CE MODULE EXISTE (mesure du 2026-08-26, session 148, build `t6dpr4k06g`)
// ---------------------------------------------------------------------------------
// `ciblesAuto: "moi"` a besoin de l'INSTANCE de la source : la composition du joueur n'est PAS
// dans la BC hors campagne (elle entre au déploiement par `AddUnitMessage`). Sur la voie LIVE —
// la bataille que le joueur lance lui-même — personne ne DÉCLARE cette instance : un `onEnter`
// sur l'ancrage de `LoadBattle` en tuerait le tir (mesuré deux fois). On se rabattait donc sur le
// pointeur global capté par `campaign-builder`, SANS VÉRIFIER SA CLASSE.
//
// Effet mesuré : ce pointeur pointait sur un `SummonUnitModel` à l'application, puis sur un
// `MachinesOfWarEventTokenWidgetVisuals` une heure plus tard. L'objet capté avait été libéré et
// son ADRESSE RECYCLÉE par un autre objet managé. `lineupDeLaSource` a refusé de lire (tri-état,
// il ne devine pas un plafond) ⇒ `voie=aucune`, 0 cible ⇒ le buff et l'Immune posés SUR PERSONNE,
// sans la moindre erreur. Seul le debuff, qui se dérive de la BC, est parti.
//
// ⛔ LA VALIDATION EST LE CŒUR, PAS LA CAPTURE. La voie déclarée avait déjà son cran
// (`sourceConcordante` : classe confrontée, instance ignorée si elle ne concorde pas) ; le repli
// n'en avait AUCUN. C'est cette asymétrie qu'on supprime : ici, un pointeur dont la classe ne
// concorde plus est OUBLIÉ et rendu `null` AVEC SA RAISON, jamais servi tel quel.
//
// ⚠ ET CE N'EST PAS UN PROBLÈME DE PvP. `repliSourceCaptee` ne connaissait que quatre préfixes
// (`Pvp`, `Campaign`, `MachinesOfWarEvent`, `Sandbox`) : pour l'ONSLAUGHT, l'incursion, la guerre
// de guilde, le mode endless — toutes ancrées — il n'existait AUCUN repli, donc `moi` y rendait 0
// sans même un pointeur périmé à accuser. Le registre est ici keyé par la CLASSE RÉELLE lue sur
// l'objet : il couvre toute source qu'un capteur traverse, présente ou future, sans liste à tenir.
//
// ⚠ LES CAPTEURS ÉVITENT LES GETTERS CHAUDS. Un hook permanent sur un getter consulté par le
// rendu ou les sérialisations Newtonsoft déstabilise IL2CPP (27 000 appels/s mesurés ailleurs
// dans ce dépôt). On ne pose donc QUE sur des méthodes de CHARGEMENT, appelées une poignée de
// fois par bataille — et jamais sur `LoadBattle`/`LoadBattleInternal` (déjà ancrés par le patch)
// ni sur `GetBattleLineup` (ancré par `lineup-poser` : l'invoquer depuis notre propre trampoline
// est le gel mesuré trois fois sur trois).
//
// ⚠ ON RANGE SOUS LA CLASSE LUE SUR L'OBJET, PAS SOUS CELLE QU'ON A ANCRÉE. IL2CPP déduplique les
// corps triviaux : un capteur posé pour `X` peut tirer avec un `this` de classe `Y`. Ranger sous
// `X` fabriquerait exactement le mensonge que ce module existe pour empêcher.

import { class_get_name, cstr, findMethod } from "../il2cpp/helpers.js";

/** Classe réelle de l'objet managé, ou `null` si illisible. Tri-état : `null` = PAS MESURÉ. */
function classeDe(obj: NativePointer): string | null {
    try {
        if (obj.isNull()) return null;
        return cstr(class_get_name(obj.readPointer()) as NativePointer);
    } catch { return null; }
}

/** Dernière instance vue pour chaque classe de source. */
const registre = new Map<string, NativePointer>();
/** Combien de fois un capteur a rangé une instance — un 0 dit « aucun capteur n'a tiré ». */
let retenues = 0;
/** Combien de fois une lecture a jeté un pointeur périmé. C'est la mesure du gisement. */
let perimes = 0;
const capteursPoses: string[] = [];

/** RANGER une instance sous sa classe RÉELLE. Un objet dont la classe est illisible est ignoré. */
export function retenirInstanceDeSource(obj: NativePointer): void {
    const classe = classeDe(obj);
    if (classe === null) return;
    const deja = registre.get(classe);
    if (deja !== undefined && deja.equals(obj)) return;
    registre.set(classe, obj);
    retenues += 1;
}

/**
 * L'instance connue pour `classe`, SEULEMENT si elle porte encore cette classe.
 *
 * Rend `{ src: null, note }` quand le pointeur est périmé — la `note` NOMME la classe trouvée à
 * la place, parce que « aucune instance » et « instance recyclée » se corrigent autrement : la
 * première demande d'ouvrir l'écran du mode, la seconde est un bug de capture.
 */
export function instanceDeSource(classe: string): { src: NativePointer | null; note: string | null } {
    const p = registre.get(classe);
    if (p === undefined || p.isNull()) return { src: null, note: null };
    const reelle = classeDe(p);
    if (reelle === classe) return { src: p, note: null };
    registre.delete(classe);
    perimes += 1;
    return {
        src: null,
        note: `instance CAPTEE de \`${classe}\` PERIMEE (${p} porte aujourd'hui `
            + `\`${reelle ?? "?"}\`) -- adresse recyclee par un autre objet manage, OUBLIEE. `
            + `\`ciblesAuto: "moi"\` n'a donc pas de composition a lire.`,
    };
}

/** Le même contrôle, pour un pointeur qui vient d'ailleurs (les capteurs historiques). */
export function siConcordante(
    p: NativePointer | null, classe: string,
): { src: NativePointer | null; note: string | null } {
    if (p === null || p.isNull()) return { src: null, note: null };
    const reelle = classeDe(p);
    if (reelle === classe) return { src: p, note: null };
    perimes += 1;
    return {
        src: null,
        note: `repli capte pour \`${classe}\` PERIME (${p} porte aujourd'hui \`${reelle ?? "?"}\`) `
            + `-- ignore plutot que servi.`,
    };
}

/**
 * Les méthodes sur lesquelles on capture. TOUTES sont des méthodes de CHARGEMENT ou de
 * PRÉPARATION, appelées une poignée de fois par bataille.
 *
 * ⛔ NE JAMAIS Y METTRE : `LoadBattle`/`LoadBattleInternal` (le patch y est ancré, un second
 * listener avec `onEnter` a déjà rendu 17 ancrages muets), `GetBattleLineup` (ancré par
 * `lineup-poser`), ni un getter consulté par le rendu.
 */
const METHODES_DE_CAPTURE: readonly string[] = [
    // ⛔ CEUX-CI TIRENT AVANT LE CHARGEMENT, ET C'EST LA CORRECTION DU 2026-08-26 (2e passe).
    // Mesure : avec les seules méthodes ci-dessous, l'onslaught a rendu `repli capte : NON` à
    // l'application alors que le registre portait bien `OnslaughtGameModeSource` juste après --
    // les capteurs avaient tiré au HUD de déploiement, donc APRÈS le `LoadBattle.onLeave` où le
    // patch mord. Un capteur qui tire trop tard vaut zéro capteur pour la bataille en cours.
    // `.ctor` est le seul point garanti AVANT tout chargement, et il tire une fois par instance.
    ".ctor",
    "Init",
    "StartLocation",
    // Appelées PENDANT `LoadBattle` pour construire la BC — le filet si l'instance a été
    // construite avant l'injection (le `.ctor` ne rejouera pas pour elle).
    "GetWaveBattleConfigDto",
    "GetRuleSetBattleConfig",
    "SendLoadBattleGameEventInternal",
    "GetBoardId",
    // Après le chargement : inutiles pour la bataille en cours, mais elles peuplent le registre
    // pour la SUIVANTE, et c'est ce qui rend le repli fiable en régime établi.
    "GetUnitsForDeploymentHUD",
    "GetUnlockedUnits",
    "GetUnlockedUnitsPooled",
    "ShouldShowUnitDeployment",
    "GetDifficultyIndex",
];

/**
 * Poser les capteurs passifs sur UNE classe de source. Appelé pour chaque source que le patch
 * ancre — donc l'onslaught, l'incursion et la guerre de guilde en héritent sans qu'on les nomme.
 *
 * Rend le nombre de capteurs réellement posés. Zéro n'est pas une panne : une source peut
 * n'exposer aucune de ces méthodes en propre (elle les hérite, et le corps hérité est capté par
 * la classe qui le déclare — on range sous la classe LUE, donc ça reste juste).
 */
export function poserCapteursDInstance(klass: NativePointer, classe: string): number {
    let poses = 0;
    for (const nom of METHODES_DE_CAPTURE) {
        const mi = findMethod(klass, nom);
        if (!mi || mi.ptr.isNull()) continue;
        try {
            Interceptor.attach(mi.ptr, nom === ".ctor" ? {
                // ⚠ SUR UN `.ctor`, ON RANGE À L'`onLeave`. À l'`onEnter` l'objet est alloué mais
                // pas construit : lire sa classe y est déjà possible, mais le retenir avant que
                // ses champs existent inviterait à l'interroger trop tôt. Même patron que la
                // capture historique de `campaign-builder`.
                onEnter(args) { (this as { obj?: NativePointer }).obj = args[0]; },
                onLeave() {
                    const o = (this as { obj?: NativePointer }).obj;
                    if (o !== undefined) retenirInstanceDeSource(o);
                },
            } : {
                onEnter(args) {
                    // Le plus court chemin possible : c'est le seul coût que ce module impose au
                    // jeu, et il est payé à chaque chargement de bataille.
                    retenirInstanceDeSource(args[0]);
                },
            });
            poses += 1;
            capteursPoses.push(`${classe}.${nom}`);
        } catch { /* une méthode qu'on ne peut pas ancrer n'est pas une panne du registre */ }
    }
    return poses;
}

/** Ce que le registre SAIT — pour un diagnostic, jamais pour décider. */
export function etatDuRegistre(): Record<string, unknown> {
    const classes: Record<string, string> = {};
    for (const [c, p] of registre) classes[c] = p.toString();
    return { retenues, perimes, capteurs: capteursPoses.length, capteursPoses, classes };
}
