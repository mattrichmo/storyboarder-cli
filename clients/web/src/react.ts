/** Typed bridge to the checked-in, licensed React production runtime. */
export type ReactNode = any;
export type SetStateAction<T> = T | ((previous:T)=>T);
export type Dispatch<T> = (value:T)=>void;
export type RefObject<T> = {current:T};
export type CSSProperties = Record<string,string|number|undefined>;
export type PointerEvt<T=HTMLElement> = PointerEvent & {currentTarget:T};
export type KeyEvt<T=HTMLElement> = KeyboardEvent & {currentTarget:T};
const React = (window as any).React;
export const useState: <T>(initial:T|(()=>T))=>[T,Dispatch<SetStateAction<T>>] = React.useState;
export const useEffect: (effect:()=>void|(()=>void),deps?:unknown[])=>void = React.useEffect;
export const useLayoutEffect: typeof useEffect = React.useLayoutEffect;
export const useMemo: <T>(factory:()=>T,deps:unknown[])=>T = React.useMemo;
export const useCallback: <T extends (...args:any[])=>any>(callback:T,deps:unknown[])=>T = React.useCallback;
export const useRef: <T>(initial:T)=>RefObject<T> = React.useRef;
export const createRoot: (element:HTMLElement)=>{render:(node:ReactNode)=>void;unmount:()=>void} = (window as any).ReactDOM.createRoot;
export default React;
