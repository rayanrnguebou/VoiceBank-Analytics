// Mode découverte (visiteur en essai, abonné) : l'interface montre tout, mais désactive ce qui
// modifierait les données partagées. Le serveur refuse de toute façon ces actions (403).
import { createContext, useContext } from "react";

export const LectureSeule = createContext(false);
export const useLectureSeule = () => useContext(LectureSeule);
export const TITRE_LECTURE_SEULE = "Lecture seule en mode découverte";
