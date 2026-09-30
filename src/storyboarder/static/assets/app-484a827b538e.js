(function(){'use strict';
const modules={"App":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.App = void 0;
const react_1 = __importStar(require("./react"));
const api_1 = require("./api");
const Primitives_1 = require("./components/Primitives");
const ActionDialog_1 = require("./components/ActionDialog");
const Inspector_1 = require("./components/Inspector");
const Canvas_1 = require("./canvas/Canvas");
const Pages_1 = require("./pages/Pages");
const NAV = [['overview', 'Project overview', 'home'], ['intake', 'Intake queue', 'inbox'], ['library', 'Asset library', 'library'], ['outline', 'Story outline', 'outline'], ['guide', 'Story guide', 'guide'], ['editor', 'Scene & shot editor', 'edit'], ['canvas', 'Canvas & connections', 'graph'], ['frames', 'Frame comparison', 'frames'], ['composition', 'Composition & exports', 'export'], ['automation', 'External scripts', 'automation'], ['settings', 'Settings & health', 'settings']];
function App() {
    const [session, setSession] = (0, react_1.useState)(null), [meta, setMeta] = (0, react_1.useState)(null), [state, setState] = (0, react_1.useState)(null);
    const [page, setPage] = (0, react_1.useState)(location.hash.slice(1) || 'workspace'), [selected, setSelected] = (0, react_1.useState)(null), [loading, setLoading] = (0, react_1.useState)(true), [error, setError] = (0, react_1.useState)('');
    const [dialog, setDialog] = (0, react_1.useState)(null), [resultModal, setResultModal] = (0, react_1.useState)(null), [result, setResult] = (0, react_1.useState)(null), [palette, setPalette] = (0, react_1.useState)(false), [paletteQuery, setPaletteQuery] = (0, react_1.useState)(''), [toast, setToast] = (0, react_1.useState)(''), [mobileNav, setMobileNav] = (0, react_1.useState)(false), [changed, setChanged] = (0, react_1.useState)(false);
    const navRef = (0, react_1.useRef)(null);
    (0, react_1.useEffect)(() => { const media = window.matchMedia('(max-width:800px)'); const update = () => { if (navRef.current)
        navRef.current.inert = media.matches && !mobileNav; }; update(); media.addEventListener('change', update); return () => media.removeEventListener('change', update); }, [mobileNav]);
    (0, react_1.useEffect)(() => { if (mobileNav) {
        const first = navRef.current?.querySelector('button:not(:disabled)');
        first?.focus();
    } }, [mobileNav]);
    const stateRef = (0, react_1.useRef)(null);
    stateRef.current = state;
    const dialogRef = (0, react_1.useRef)(dialog);
    dialogRef.current = dialog;
    function notify(message) { setToast(message); }
    function go(next) { if (next !== page)
        location.hash = next; setPage(next); setMobileNav(false); }
    async function load(id) { const next = await (0, api_1.api)((0, api_1.projectPath)(id, '/state')); setState(next); setChanged(false); return next; }
    async function refresh() { const id = stateRef.current?.project.id; if (!id)
        throw new Error('Open a project first.'); return load(id); }
    async function refreshSession() { const s = await (0, api_1.openSession)(); setSession(s); setMeta(await (0, api_1.api)('/meta')); }
    async function open(id) { setError(''); setLoading(true); try {
        await (0, api_1.api)('/active', 'POST', { id });
        await load(id);
        setSelected(null);
        setResult(null);
        await refreshSession();
        go('overview');
    }
    catch (e) {
        setError(e.message);
    }
    finally {
        setLoading(false);
    } }
    (0, react_1.useEffect)(() => { let alive = true; (async () => { try {
        const s = await (0, api_1.openSession)();
        const m = await (0, api_1.api)('/meta');
        if (!alive)
            return;
        setSession(s);
        setMeta(m);
        if (s.active_project_id)
            await load(s.active_project_id);
        else
            go('workspace');
    }
    catch (e) {
        setError(e.message);
    }
    finally {
        if (alive)
            setLoading(false);
    } })(); const h = () => setPage(location.hash.slice(1) || 'workspace'); window.addEventListener('hashchange', h); return () => { alive = false; window.removeEventListener('hashchange', h); }; }, []);
    (0, react_1.useEffect)(() => { if (!toast)
        return; const timer = setTimeout(() => setToast(''), 6500); return () => clearTimeout(timer); }, [toast]);
    (0, react_1.useEffect)(() => { const keys = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette(v => !v);
    } if (e.key === 'Escape')
        setMobileNav(false); }; window.addEventListener('keydown', keys); return () => window.removeEventListener('keydown', keys); }, []);
    // A background read only marks stale UI. It never overwrites a modal's unsaved edits.
    (0, react_1.useEffect)(() => { let running = false; const check = async () => { const current = stateRef.current; if (!current || document.hidden || running)
        return; running = true; try {
        const next = await (0, api_1.api)((0, api_1.projectPath)(current.project.id, '/state'));
        if (stateRef.current?.project.id !== current.project.id)
            return;
        const signature = (s) => JSON.stringify([s.entities.map(r => [r.id, r.revision, r.archived]), s.events[0]?.id, s.layouts.map(r => [r.id, r.revision]), s.jobs.map(r => [r.id, r.revision])]);
        if (signature(next) !== signature(current))
            setChanged(true);
    }
    catch { }
    finally {
        running = false;
    } }; const timer = setInterval(check, 6500); window.addEventListener('focus', check); return () => { clearInterval(timer); window.removeEventListener('focus', check); }; }, []);
    function action(name, defaults = {}) { const command = meta?.commands.find(c => c.name === name); if (!command) {
        notify(`The command ${name} is not available in this interface.`);
        return;
    } if (!state) {
        notify('Open a project first.');
        return;
    } setDialog({ command, defaults }); }
    async function done(data, name) { await refresh(); if (name.startsWith('export.')) {
        setResult(data);
        setResultModal({ title: 'Export ready', data });
    }
    else if (meta?.commands.find(c => c.name === name)?.read_only) {
        setResultModal({ title: meta?.commands.find(c => c.name === name)?.label || name, data });
    }
    else if (data?.status === 'failed' || data?.status === 'cancelled') {
        notify(`External run ${data.status}. Open its logs in External scripts.`);
    }
    else {
        notify(`${meta?.commands.find(c => c.name === name)?.label || name}: saved locally.`);
    } }
    const props = state && session && meta ? { state, session, meta, action, select: setSelected, selected, refresh, notify, go, result, setResult } : null;
    const screens = { overview: Pages_1.OverviewPage, intake: Pages_1.IntakePage, library: Pages_1.LibraryPage, outline: Pages_1.OutlinePage, guide: Pages_1.GuidePage, editor: Pages_1.EditorPage, frames: Pages_1.FramesPage, composition: Pages_1.CompositionPage, settings: Pages_1.SettingsPage, automation: Pages_1.AutomationPage };
    const Page = screens[page];
    return react_1.default.createElement("div", { className: "app-shell" },
        react_1.default.createElement("a", { className: "skip-link", href: "#main-content", onClick: (e) => { e.preventDefault(); document.getElementById('main-content')?.focus(); } }, "Skip to workspace"),
        react_1.default.createElement("aside", { ref: navRef, className: `navigation ${mobileNav ? 'is-open' : ''}`, "aria-label": "Main navigation" },
            react_1.default.createElement("button", { className: "wordmark", disabled: loading, onClick: () => go('workspace'), "aria-label": "Storyboarder workspace" },
                react_1.default.createElement("span", { className: "brand-mark" },
                    react_1.default.createElement(Primitives_1.Icon, { name: "grid", size: 23 })),
                react_1.default.createElement("span", null,
                    "Storyboarder",
                    react_1.default.createElement("small", null, "LOCAL PRODUCTION DESK"))),
            react_1.default.createElement("button", { disabled: loading, className: `workspace-switch ${page === 'workspace' ? 'active' : ''}`, onClick: () => go('workspace') },
                react_1.default.createElement(Primitives_1.Icon, { name: "grid" }),
                react_1.default.createElement("span", null, "Workspace")),
            react_1.default.createElement("div", { className: "nav-project" },
                react_1.default.createElement("span", { className: "eyebrow" }, "Current project"),
                react_1.default.createElement("strong", { title: state?.project.title }, state?.project.title || 'No project open'),
                react_1.default.createElement("small", null, state ? 'Saved in a portable folder' : 'Create a project to begin')),
            react_1.default.createElement("nav", null, NAV.map(([key, label, icon]) => react_1.default.createElement("button", { key: key, "aria-label": label, className: page === key ? 'active' : '', disabled: loading || !state, onClick: () => go(key), "aria-current": page === key ? 'page' : undefined },
                react_1.default.createElement(Primitives_1.Icon, { name: icon }),
                react_1.default.createElement("span", null, label),
                key === 'intake' && state?.project.counts.intake ? react_1.default.createElement("span", { className: "nav-count" }, state.project.counts.intake) : null))),
            react_1.default.createElement("div", { className: "nav-bottom" },
                react_1.default.createElement("button", { onClick: () => setPalette(true), disabled: !state },
                    react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                    "All actions ",
                    react_1.default.createElement("kbd", null, "\u2318/Ctrl K")),
                react_1.default.createElement("p", null,
                    react_1.default.createElement("span", { className: "local-dot" }),
                    "Local only \u00B7 v",
                    session?.version || '1.0.0'))),
        mobileNav && react_1.default.createElement("button", { className: "nav-scrim", onClick: () => setMobileNav(false), "aria-label": "Close navigation" }),
        react_1.default.createElement("div", { className: "app-column" },
            react_1.default.createElement("header", { className: "topbar" },
                react_1.default.createElement("button", { className: "mobile-menu icon-button", "aria-label": "Open navigation", onClick: () => setMobileNav(true) },
                    react_1.default.createElement(Primitives_1.Icon, { name: "menu" })),
                react_1.default.createElement("div", { className: "breadcrumbs" },
                    react_1.default.createElement("button", { onClick: () => go('workspace') }, "Workspace"),
                    state && react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement("span", null, "/"),
                        react_1.default.createElement("button", { onClick: () => go('overview') }, state.project.title)),
                    page !== 'workspace' && react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement("span", null, "/"),
                        react_1.default.createElement("strong", null, NAV.find(n => n[0] === page)?.[1] || 'Overview'))),
                react_1.default.createElement("div", { className: "topbar-actions" },
                    state && react_1.default.createElement("button", { className: "text-button", onClick: () => refresh().then(() => notify('Reloaded current project records.')).catch(e => setError(e.message)) },
                        react_1.default.createElement(Primitives_1.Icon, { name: "refresh" }),
                        react_1.default.createElement("span", null, "Refresh")),
                    react_1.default.createElement("span", { className: "local-indicator" }, "On this computer"))),
            changed && react_1.default.createElement("div", { className: "external-change", role: "status" },
                "This project changed in another interface. Current forms have not been overwritten. ",
                react_1.default.createElement("button", { onClick: () => refresh().catch(e => setError(e.message)) }, "Reload records")),
            react_1.default.createElement("div", { className: `work-area ${selected && page !== 'workspace' ? 'with-inspector' : ''}` },
                react_1.default.createElement("main", { id: "main-content", tabIndex: -1, className: `main-content ${page === 'canvas' ? 'canvas-main' : ''}` },
                    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error },
                        react_1.default.createElement("button", { onClick: () => location.reload() }, "Reconnect to local app")),
                    loading ? react_1.default.createElement("div", { className: "loading-state", role: "status" },
                        react_1.default.createElement(Primitives_1.Icon, { name: "grid", size: 30 }),
                        react_1.default.createElement("h2", null, "Opening the production desk\u2026")) : session && meta && (page === 'workspace' || !state) ? react_1.default.createElement(Pages_1.WorkspacePage, { session: session, projects: session.projects, onOpen: open, onRefresh: refreshSession }) : props && page === 'canvas' ? react_1.default.createElement(Canvas_1.Canvas, { state: props.state, selected: selected, onSelect: setSelected, action: action, refresh: refresh, notify: notify }) : props && Page ? react_1.default.createElement(Page, { ...props }) : props ? react_1.default.createElement(Pages_1.OverviewPage, { ...props }) : !error ? react_1.default.createElement(Primitives_1.Empty, { title: "Open a local workspace" },
                        "Launch with ",
                        react_1.default.createElement("code", null, "storyboarder ui --workspace PATH"),
                        ".") : null),
                state && selected && page !== 'workspace' && react_1.default.createElement(Inspector_1.Inspector, { state: state, id: selected, onClose: () => setSelected(null), onSelect: setSelected, action: action })),
            react_1.default.createElement("footer", { className: "app-footer" },
                react_1.default.createElement("span", null, "Story records are canonical. Canvas positions are presentation only."),
                state && react_1.default.createElement("span", null,
                    state.media.length,
                    " managed images \u00B7 ",
                    state.frames.filter(f => f.state === 'approved').length,
                    " approved frames"))),
        toast && react_1.default.createElement("div", { className: "toast", role: "status" },
            react_1.default.createElement(Primitives_1.Icon, { name: "check" }),
            react_1.default.createElement("span", null, toast),
            react_1.default.createElement("button", { "aria-label": "Dismiss notification", onClick: () => setToast('') },
                react_1.default.createElement(Primitives_1.Icon, { name: "close", size: 16 }))),
        dialog && state && meta && react_1.default.createElement(ActionDialog_1.ActionDialog, { key: dialog.command.name + JSON.stringify(dialog.defaults), command: dialog.command, defaults: dialog.defaults, state: state, meta: meta, onClose: () => setDialog(null), onDone: done, onReload: refresh }),
        resultModal && react_1.default.createElement(Primitives_1.Modal, { title: resultModal.title, onClose: () => setResultModal(null), wide: true },
            react_1.default.createElement("div", { className: "modal-body" }, resultModal.data?.archive && state ? react_1.default.createElement(Primitives_1.ExportLinks, { project: state.project.id, result: resultModal.data }) : resultModal.data?.chain ? react_1.default.createElement(Primitives_1.ContextView, { value: resultModal.data }) : react_1.default.createElement("pre", { className: "code-preview" }, JSON.stringify(resultModal.data, null, 2)))),
        palette && meta && react_1.default.createElement(Primitives_1.Modal, { title: "All application actions", onClose: () => setPalette(false), wide: true },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("label", { className: "search" },
                    react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                    react_1.default.createElement("input", { autoFocus: true, placeholder: "Find an action\u2026", "aria-label": "Find an action", value: paletteQuery, onChange: (e) => setPaletteQuery(e.target.value) })),
                react_1.default.createElement("div", { className: "command-list" }, meta.commands.filter(c => (c.label + ' ' + c.name).toLowerCase().includes(paletteQuery.toLowerCase())).map(c => react_1.default.createElement("button", { key: c.name, onClick: () => { setPalette(false); action(c.name); } },
                    react_1.default.createElement("span", null, c.label),
                    react_1.default.createElement("small", null,
                        c.name,
                        c.destructive ? ' · confirmation required' : '')))))));
}
exports.App = App;

},
"api":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runCommand = exports.jobImageUrl = exports.exportUrl = exports.originalUrl = exports.mediaUrl = exports.projectPath = exports.openSession = exports.api = exports.ApiError = void 0;
let launchToken = '';
class ApiError extends Error {
    constructor(code, message, details = {}, status = 0) {
        super(message);
        this.code = code;
        this.details = details;
        this.status = status;
    }
}
exports.ApiError = ApiError;
async function api(path, method = 'GET', data) {
    const headers = {};
    if (method !== 'GET')
        headers['X-Storyboarder-Token'] = launchToken;
    const multipart = data instanceof FormData;
    if (data !== undefined && !multipart)
        headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/v1' + path, { method, headers, body: data === undefined ? undefined : multipart ? data : JSON.stringify(data), credentials: 'same-origin' });
    let result;
    try {
        result = await response.json();
    }
    catch {
        throw new ApiError('connection', 'The local service did not return a valid response. Check the launch terminal.', {}, response.status);
    }
    if (!response.ok)
        throw new ApiError(result.error?.code || 'request', result.error?.message || 'The request could not be completed.', result.error?.details, response.status);
    return result;
}
exports.api = api;
async function openSession() { const session = await api('/session'); launchToken = session.token; return session; }
exports.openSession = openSession;
const projectPath = (id, path = '') => `/projects/${encodeURIComponent(id)}${path}`;
exports.projectPath = projectPath;
const mediaUrl = (project, media, size = 480) => `/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}?size=${size}`;
exports.mediaUrl = mediaUrl;
const originalUrl = (project, media) => `/api/v1/projects/${encodeURIComponent(project)}/media/${encodeURIComponent(media)}`;
exports.originalUrl = originalUrl;
const exportUrl = (project, path, download = false) => `/api/v1/projects/${encodeURIComponent(project)}/files/${path.split('/').map(encodeURIComponent).join('/')}${download ? '?download=true' : ''}`;
exports.exportUrl = exportUrl;
const jobImageUrl = (project, job, key) => `/api/v1/projects/${encodeURIComponent(project)}/jobs/${encodeURIComponent(job)}/outputs/${encodeURIComponent(key)}`;
exports.jobImageUrl = jobImageUrl;
const runCommand = (project, name, payload = {}) => api((0, exports.projectPath)(project, `/commands/${encodeURIComponent(name)}`), 'POST', payload);
exports.runCommand = runCommand;

},
"canvas/Canvas":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.Canvas = void 0;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("../components/Primitives");
const geometry_1 = require("./geometry");
function Canvas({ state, selected, onSelect, action, refresh, notify }) {
    const [newKind, setNewKind] = (0, react_1.useState)('sequence');
    const [mode, setMode] = (0, react_1.useState)('story'), [scene, setScene] = (0, react_1.useState)(''), [sequence, setSequence] = (0, react_1.useState)('');
    const [query, setQuery] = (0, react_1.useState)(''), [assetType, setAssetType] = (0, react_1.useState)(''), [tag, setTag] = (0, react_1.useState)(''), [relation, setRelation] = (0, react_1.useState)('');
    const [graph, setGraph] = (0, react_1.useState)({ nodes: [], edges: [], mode: 'story', total: 0, truncated: false });
    const [positions, setPositions] = (0, react_1.useState)({}), [view, setView] = (0, react_1.useState)({ x: 50, y: 50, scale: .7 });
    const [hidden, setHidden] = (0, react_1.useState)([]), [collapsed, setCollapsed] = (0, react_1.useState)([]), [multi, setMulti] = (0, react_1.useState)([]);
    const [error, setError] = (0, react_1.useState)(''), [loading, setLoading] = (0, react_1.useState)(false), [dirty, setDirty] = (0, react_1.useState)(false), [linkFrom, setLinkFrom] = (0, react_1.useState)(null);
    const [layoutName, setLayoutName] = (0, react_1.useState)('Working layout'), [layoutRevision, setLayoutRevision] = (0, react_1.useState)(undefined), [layoutId, setLayoutId] = (0, react_1.useState)('');
    const [selectedEdge, setSelectedEdge] = (0, react_1.useState)(null), [deleteId, setDeleteId] = (0, react_1.useState)(null), [usage, setUsage] = (0, react_1.useState)(null);
    const stage = (0, react_1.useRef)(null);
    const drag = (0, react_1.useRef)(null);
    const moved = (0, react_1.useRef)(false);
    const positionsRef = (0, react_1.useRef)(positions);
    positionsRef.current = positions;
    (0, react_1.useEffect)(() => { if (!scene)
        setScene((0, utils_1.activeEntities)(state, 'scene')[0]?.id || ''); }, [state.entities]);
    (0, react_1.useEffect)(() => {
        const cancel = new AbortController();
        let active = true;
        setLoading(true);
        const params = new URLSearchParams({ mode, query, limit: '250' });
        if (mode === 'assets') {
            if (assetType)
                params.set('asset_type', assetType);
            if (tag)
                params.set('tag', tag);
            if (relation)
                params.set('relation', relation);
        }
        if (mode === 'scene' && scene)
            params.set('scene_id', scene);
        if (mode === 'story' && sequence)
            params.set('sequence_id', sequence);
        const timer = setTimeout(() => { (0, api_1.api)((0, api_1.projectPath)(state.project.id, '/graph?' + params)).then(next => { if (!active)
            return; setGraph(next); const base = (0, geometry_1.tidy)(next.nodes, next.edges, mode); const merged = { ...base, ...positionsRef.current }; setPositions(merged); const rect = stage.current?.getBoundingClientRect(); if (rect && query)
            setView((0, geometry_1.fit)(Object.fromEntries(next.nodes.map(n => [n.id, merged[n.id]])), rect.width, rect.height)); setError(''); }).catch(e => active && setError(e.message)).finally(() => active && setLoading(false)); }, query ? 150 : 0);
        return () => { active = false; cancel.abort(); clearTimeout(timer); };
    }, [state, mode, scene, sequence, query, assetType, tag, relation]);
    (0, react_1.useEffect)(() => { const before = (e) => { if (dirty) {
        e.preventDefault();
        e.returnValue = '';
    } }; window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before); }, [dirty]);
    const suppressed = (0, react_1.useMemo)(() => new Set([...hidden, ...(0, geometry_1.descendants)(graph.nodes, collapsed)]), [hidden, collapsed, graph]);
    const visible = graph.nodes.filter(n => !suppressed.has(n.id)), visibleIds = new Set(visible.map(n => n.id));
    const edges = graph.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));
    const bounds = () => stage.current?.getBoundingClientRect();
    const fitView = () => { const rect = bounds(); if (rect)
        setView((0, geometry_1.fit)(Object.fromEntries(visible.map(n => [n.id, positions[n.id] || { x: 0, y: 0 }])), rect.width, rect.height)); };
    function switchMode(next) { if (dirty && !window.confirm('Change canvas view? Save the named layout first to keep its current arrangement.'))
        return; setMode(next); setNewKind(next === 'assets' ? 'asset' : next === 'scene' ? 'shot' : 'sequence'); setPositions({}); setHidden([]); setCollapsed([]); setLayoutId(''); setLayoutRevision(undefined); setDirty(false); setSelectedEdge(null); setView({ x: 50, y: 50, scale: .65 }); }
    function select(node, event) {
        if (moved.current) {
            moved.current = false;
            return;
        }
        if (linkFrom) {
            const source = state.entities.find(n => n.id === linkFrom);
            setLinkFrom(null);
            if (!source)
                return;
            if (source.id === node.id) {
                setError('Choose two different endpoints. A record cannot connect to itself.');
                return;
            }
            if (source.kind === 'asset' && node.kind === 'asset')
                action('link.create', { source_id: source.id, target_id: node.id });
            else if (source.kind === 'shot' && node.kind === 'asset')
                action('assignment.create', { shot_id: source.id, asset_id: node.id });
            else if ((source.kind === 'sequence' && node.kind === 'scene') || (source.kind === 'scene' && node.kind === 'shot'))
                action('story.move', { id: node.id, revision: node.revision, parent_id: source.id, position: 0 });
            else
                setError(`A ${source.kind} cannot connect to a ${node.kind} in that direction. Use asset → asset, shot → asset, sequence → scene, or scene → shot.`);
            return;
        }
        onSelect(node.id);
        setSelectedEdge(null);
        setMulti(event?.shiftKey ? (multi.includes(node.id) ? multi.filter(id => id !== node.id) : [...multi, node.id]) : [node.id]);
    }
    function startDrag(e, node) { if (e.button !== 0 && e.button !== 1)
        return; if (e.target.closest('button,a,input,select'))
        return; if (linkFrom && node)
        return; const rect = bounds(); if (!rect)
        return; e.currentTarget.setPointerCapture(e.pointerId); moved.current = false; const ids = node ? (multi.includes(node.id) ? multi : [node.id]) : []; if (node) {
        onSelect(node.id);
        if (!multi.includes(node.id))
            setMulti([node.id]);
    } drag.current = { kind: node ? 'node' : 'pan', pointer: e.pointerId, x: e.clientX, y: e.clientY, view: { ...view }, positions: { ...positions }, ids }; e.preventDefault(); e.stopPropagation(); }
    function move(e) { const d = drag.current; if (!d || d.pointer !== e.pointerId)
        return; const dx = e.clientX - d.x, dy = e.clientY - d.y; if (Math.abs(dx) + Math.abs(dy) > 3)
        moved.current = true; if (d.kind === 'pan') {
        setView({ ...d.view, x: d.view.x + dx, y: d.view.y + dy });
    }
    else {
        setPositions(old => { const next = { ...old }; d.ids.forEach((id) => { const p = d.positions[id] || { x: 0, y: 0 }; next[id] = { x: p.x + dx / d.view.scale, y: p.y + dy / d.view.scale }; }); return next; });
    } setDirty(true); }
    function end(e) { if (drag.current?.pointer === e.pointerId) {
        drag.current = null;
        try {
            e.currentTarget.releasePointerCapture(e.pointerId);
        }
        catch { }
    } }
    function wheel(e) { if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const r = bounds();
        if (r)
            setView(v => (0, geometry_1.zoomAt)(v, { x: e.clientX - r.left, y: e.clientY - r.top }, Math.exp(-e.deltaY * .002)));
    }
    else {
        e.preventDefault();
        setView(v => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
    } setDirty(true); }
    (0, react_1.useEffect)(() => { const el = stage.current; if (!el)
        return; el.addEventListener('wheel', wheel, { passive: false }); return () => el.removeEventListener('wheel', wheel); }, []);
    function key(e, node) { if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        select(node, e);
        return;
    } if (e.key.toLowerCase() === 'l') {
        e.preventDefault();
        setLinkFrom(node.id);
        notify('Choose an eligible destination, then press Enter or click it.');
        return;
    } if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        requestDelete(node.id);
        return;
    } const delta = { ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 }, ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 } }; if (delta[e.key]) {
        e.preventDefault();
        const d = delta[e.key], step = e.shiftKey ? 50 : 10;
        setPositions(old => ({ ...old, [node.id]: { x: (old[node.id]?.x || 0) + d.x * step, y: (old[node.id]?.y || 0) + d.y * step } }));
        setDirty(true);
    } }
    function requestDelete(id) { setDeleteId(id); setUsage(null); (0, api_1.runCommand)(state.project.id, 'entity.usage', { id }).then(setUsage).catch(e => setError(e.message)); }
    async function save() { try {
        const result = await (0, api_1.runCommand)(state.project.id, 'canvas.save', { name: layoutName, mode, positions, settings: { hidden, collapsed, viewport: view, filters: { query, asset_type: assetType, tag, relation }, scene_id: scene, sequence_id: sequence }, ...(layoutRevision ? { revision: layoutRevision } : {}) });
        setLayoutId(result.id);
        setLayoutRevision(result.revision);
        setDirty(false);
        await refresh();
        notify('Named canvas layout saved. Story order and relationships were not changed.');
    }
    catch (e) {
        setError(e.message);
    } }
    function load(id) { const saved = state.layouts.find(l => l.id === id); if (!saved)
        return; if (dirty && !window.confirm('Replace the unsaved arrangement with this saved layout?'))
        return; setLayoutId(id); setLayoutName(saved.name); setLayoutRevision(saved.revision); setPositions(saved.positions); setHidden(saved.settings.hidden || []); setCollapsed(saved.settings.collapsed || []); if (saved.settings.viewport)
        setView(saved.settings.viewport); setScene(saved.settings.scene_id || scene); setSequence(saved.settings.sequence_id || ''); const filters = saved.settings.filters || {}; setQuery(filters.query || ''); setAssetType(filters.asset_type || ''); setTag(filters.tag || ''); setRelation(filters.relation || ''); setDirty(false); }
    const selectedNode = state.entities.find(n => n.id === selected);
    const tags = [...new Set(state.entities.flatMap(e => e.tags))].sort();
    return react_1.default.createElement("div", { className: "canvas-page" },
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Connected workspace", title: "Canvas", description: "Arrange the view. Author the relationships.", actions: react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("select", { "aria-label": "New canvas record type", value: newKind, onChange: (e) => setNewKind(e.target.value) },
                    react_1.default.createElement("option", { value: "asset" }, "Asset"),
                    react_1.default.createElement("option", { value: "sequence" }, "Sequence"),
                    react_1.default.createElement("option", { value: "scene" }, "Scene"),
                    react_1.default.createElement("option", { value: "shot" }, "Shot")),
                react_1.default.createElement("button", { onClick: () => action(newKind + '.create', newKind === 'shot' && scene ? { parent_id: scene } : newKind === 'scene' && sequence ? { parent_id: sequence } : {}) },
                    react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                    "New ",
                    newKind),
                react_1.default.createElement("button", { onClick: () => action('link.create') }, "Connect assets")) }),
        react_1.default.createElement("div", { className: "canvas-controls" },
            react_1.default.createElement("div", { className: "segmented", "aria-label": "Canvas view" }, [['story', 'Story flow'], ['assets', 'Asset network'], ['scene', 'Scene board']].map(([value, label]) => react_1.default.createElement("button", { key: value, "aria-pressed": mode === value, onClick: () => switchMode(value) }, label))),
            react_1.default.createElement("label", { className: "search" },
                react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                react_1.default.createElement("input", { "aria-label": "Search canvas nodes", placeholder: "Find a node\u2026", value: query, onChange: (e) => setQuery(e.target.value) })),
            mode === 'scene' && react_1.default.createElement("select", { "aria-label": "Scene board scene", value: scene, onChange: (e) => setScene(e.target.value) },
                react_1.default.createElement("option", { value: "" }, "Choose a scene"),
                (0, utils_1.activeEntities)(state, 'scene').map(n => react_1.default.createElement("option", { key: n.id, value: n.id }, n.title))),
            mode === 'story' && react_1.default.createElement("select", { "aria-label": "Sequence filter", value: sequence, onChange: (e) => setSequence(e.target.value) },
                react_1.default.createElement("option", { value: "" }, "All sequences"),
                (0, utils_1.activeEntities)(state, 'sequence').map(n => react_1.default.createElement("option", { key: n.id, value: n.id }, n.title))),
            mode === 'assets' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("select", { "aria-label": "Asset type filter", value: assetType, onChange: (e) => setAssetType(e.target.value) },
                    react_1.default.createElement("option", { value: "" }, "All asset types"),
                    ['character', 'location', 'prop', 'reference'].map(t => react_1.default.createElement("option", { key: t }, t))),
                react_1.default.createElement("select", { "aria-label": "Tag filter", value: tag, onChange: (e) => setTag(e.target.value) },
                    react_1.default.createElement("option", { value: "" }, "All tags"),
                    tags.map(t => react_1.default.createElement("option", { key: t }, t))),
                react_1.default.createElement("select", { "aria-label": "Relationship filter", value: relation, onChange: (e) => setRelation(e.target.value) },
                    react_1.default.createElement("option", { value: "" }, "All relationships"),
                    ['appears-at', 'alternate-view-of', 'wears', 'part-of', 'related-to'].map(t => react_1.default.createElement("option", { key: t }, t))))),
        error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
        " ",
        linkFrom && react_1.default.createElement("div", { className: "notice" },
            "Link from ",
            react_1.default.createElement("strong", null, state.entities.find(n => n.id === linkFrom)?.title),
            ". Tab to a destination and press Enter, or click a node. ",
            react_1.default.createElement("button", { onClick: () => setLinkFrom(null) }, "Cancel link")),
        react_1.default.createElement("div", { className: "canvas-layout-bar" },
            react_1.default.createElement("select", { "aria-label": "Saved layout", value: layoutId, onChange: (e) => load(e.target.value) },
                react_1.default.createElement("option", { value: "" }, "Unsaved layout"),
                state.layouts.filter(l => l.mode === mode).map(l => react_1.default.createElement("option", { key: l.id, value: l.id },
                    l.name,
                    " \u00B7 r",
                    l.revision))),
            react_1.default.createElement("input", { "aria-label": "Layout name", value: layoutName, onChange: (e) => { setLayoutName(e.target.value); if (e.target.value !== state.layouts.find(l => l.id === layoutId)?.name) {
                    setLayoutRevision(undefined);
                    setLayoutId('');
                } setDirty(true); } }),
            react_1.default.createElement("button", { onClick: save, disabled: !layoutName.trim() }, dirty ? 'Save layout *' : 'Save layout'),
            react_1.default.createElement("button", { onClick: () => { setPositions((0, geometry_1.tidy)(graph.nodes, graph.edges, mode)); setDirty(true); } }, "Tidy layout"),
            react_1.default.createElement("button", { onClick: fitView }, "Fit view"),
            hidden.length > 0 && react_1.default.createElement("button", { onClick: () => { setHidden([]); setDirty(true); } },
                "Show ",
                hidden.length,
                " hidden")),
        react_1.default.createElement("div", { ref: stage, className: `graph-stage ${linkFrom ? 'linking' : ''}`, tabIndex: 0, "aria-label": "Interactive story canvas. Tab selects cards. Arrow keys arrange, L links, Delete reviews removal.", onPointerDown: (e) => startDrag(e), onPointerMove: move, onPointerUp: end, onPointerCancel: end, onKeyDown: (e) => { if (e.key === 'Escape') {
                setLinkFrom(null);
                setSelectedEdge(null);
            } } },
            react_1.default.createElement("div", { className: "canvas-world", style: { transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` } },
                react_1.default.createElement("svg", { className: "edge-layer", width: "1", height: "1", "aria-label": "Story and reference connections" },
                    react_1.default.createElement("defs", null,
                        react_1.default.createElement("marker", { id: "edge-arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" },
                            react_1.default.createElement("path", { d: "M 0 0 L 10 5 L 0 10 z" }))),
                    edges.map(edge => { const a = positions[edge.source], b = positions[edge.target]; if (!a || !b)
                        return null; const curve = (0, geometry_1.edgePath)(a, b); return react_1.default.createElement("g", { key: edge.id, className: `graph-edge ${edge.kind} ${selectedEdge?.id === edge.id ? 'is-selected' : ''}` },
                        react_1.default.createElement("path", { d: curve.path, markerEnd: "url(#edge-arrow)" }),
                        react_1.default.createElement("path", { d: curve.path, className: "edge-hit", onClick: (e) => { e.stopPropagation(); setSelectedEdge(edge); } }),
                        react_1.default.createElement("g", { transform: `translate(${curve.label.x}, ${curve.label.y})`, role: "button", tabIndex: 0, "aria-label": `${edge.label} connection: select for controls`, onPointerDown: (e) => e.stopPropagation(), onClick: () => setSelectedEdge(edge), onKeyDown: (e) => { if (e.key === 'Enter') {
                                e.preventDefault();
                                e.stopPropagation();
                                setSelectedEdge(edge);
                            } } },
                            react_1.default.createElement("rect", { x: -Math.max(18, edge.label.length * 3.7 + 8), y: "-12", width: Math.max(36, edge.label.length * 7.4 + 16), height: "24", rx: "4" }),
                            react_1.default.createElement("text", { textAnchor: "middle", dominantBaseline: "central" },
                                edge.kind === 'order' ? '# ' : edge.kind === 'assignment' ? '↳ ' : '',
                                edge.label))); })),
                visible.map(node => {
                    const pos = positions[node.id] || { x: 0, y: 0 }, type = (0, utils_1.kindLabel)(node);
                    const thumbnail = node.thumbnail_media_id || node.reference_media_ids?.[0];
                    return react_1.default.createElement("article", { key: node.id, "data-node-id": node.id, className: `graph-node ${type} ${selected === node.id || multi.includes(node.id) ? 'is-selected' : ''} ${linkFrom === node.id ? 'link-source' : ''}`, style: { width: geometry_1.NODE_W, height: geometry_1.NODE_H, transform: `translate(${pos.x}px,${pos.y}px)` }, tabIndex: 0, role: "button", "aria-label": `${type}: ${node.title}. ${node.reference_count || 0} references.`, "aria-pressed": selected === node.id, onPointerDown: (e) => startDrag(e, node), onPointerMove: move, onPointerUp: end, onClick: (e) => { e.stopPropagation(); select(node, e); }, onKeyDown: (e) => key(e, node) },
                        react_1.default.createElement("div", { className: "node-type" },
                            react_1.default.createElement("span", null, type),
                            react_1.default.createElement("span", null, node.kind === 'asset' ? `${node.media_count || 0} images` : `${String(node.position + 1).padStart(2, '0')}`)),
                        thumbnail ? react_1.default.createElement("img", { className: "node-image", src: (0, api_1.mediaUrl)(state.project.id, thumbnail), alt: `${node.title} ${node.frame_state ? 'frame' : 'reference'}`, draggable: false }) : react_1.default.createElement("div", { className: "node-text-preview" }, String(node.fields.action || node.fields.summary || node.fields.arc || node.description || 'Awaiting direction')),
                        react_1.default.createElement("div", { className: "node-content" },
                            react_1.default.createElement("h3", null, node.title),
                            react_1.default.createElement("p", null, node.kind === 'shot' ? `${node.fields.framing || 'Framing not set'} · ${node.reference_count || 0} references` : node.kind === 'asset' ? `${node.link_count || 0} links · ${node.reference_count || 0} shot uses` : `${node.child_count || 0} ${node.kind === 'sequence' ? 'scenes' : 'shots'}`),
                            react_1.default.createElement("div", { className: "node-footer" },
                                node.frame_state ? react_1.default.createElement(Primitives_1.Badge, { kind: node.frame_state },
                                    node.frame_state,
                                    " frame") : node.tags.slice(0, 2).map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)),
                                node.child_count > 0 && node.kind !== 'asset' && react_1.default.createElement("button", { "aria-label": `${collapsed.includes(node.id) ? 'Expand' : 'Collapse'} ${node.title}`, onClick: (e) => { e.stopPropagation(); setCollapsed(v => v.includes(node.id) ? v.filter(id => id !== node.id) : [...v, node.id]); setDirty(true); } }, collapsed.includes(node.id) ? '+' : '−'))));
                })),
            !visible.length && !loading && react_1.default.createElement(Primitives_1.Empty, { title: mode === 'scene' ? 'Choose a scene to build its board' : 'Your canvas starts with the story', action: react_1.default.createElement("button", { onClick: () => action(mode === 'assets' ? 'asset.create' : mode === 'scene' ? 'scene.create' : 'sequence.create') },
                    "Create a ",
                    mode === 'assets' ? 'reference asset' : mode === 'scene' ? 'scene' : 'sequence') }, "Create records here or in the outline. Their valid connections will appear automatically."),
            react_1.default.createElement("div", { className: "canvas-zoom", onPointerDown: (e) => e.stopPropagation() },
                react_1.default.createElement("button", { "aria-label": "Zoom out", onClick: () => setView(v => (0, geometry_1.zoomAt)(v, { x: 200, y: 200 }, .8)) }, "\u2212"),
                react_1.default.createElement("span", null,
                    Math.round(view.scale * 100),
                    "%"),
                react_1.default.createElement("button", { "aria-label": "Zoom in", onClick: () => setView(v => (0, geometry_1.zoomAt)(v, { x: 200, y: 200 }, 1.25)) }, "+"))),
        react_1.default.createElement("div", { className: "canvas-status" },
            react_1.default.createElement("span", null,
                loading ? 'Loading…' : `${visible.length} nodes · ${edges.length} connections`,
                graph.truncated && ` · ${graph.total} match; refine filters to see more (250-node view limit)`),
            react_1.default.createElement("span", null, "Drag background to pan \u00B7 Ctrl + scroll to zoom \u00B7 Arrow keys to arrange \u00B7 L to link")),
        selectedNode && react_1.default.createElement("div", { className: "selection-tools" },
            react_1.default.createElement("strong", null, selectedNode.title),
            react_1.default.createElement("button", { onClick: () => action(selectedNode.kind + '.update', (0, utils_1.commandDefaults)(selectedNode)) }, "Edit"),
            react_1.default.createElement("button", { onClick: () => setLinkFrom(selectedNode.id) }, "Link from this node"),
            ['sequence', 'scene', 'shot'].includes(selectedNode.kind) && react_1.default.createElement("button", { onClick: () => action('story.move', (0, utils_1.commandDefaults)(selectedNode)) }, "Move / reorder"),
            react_1.default.createElement("button", { onClick: () => requestDelete(selectedNode.id) }, "Remove\u2026")),
        selectedEdge && react_1.default.createElement("div", { className: "selection-tools" },
            react_1.default.createElement("strong", null, selectedEdge.label),
            react_1.default.createElement("span", null, selectedEdge.kind === 'order' ? 'Canonical story order' : selectedEdge.kind === 'assignment' ? 'Shot reference assignment' : 'Typed asset relationship'),
            selectedEdge.kind === 'order' ? react_1.default.createElement("button", { onClick: () => { const child = state.entities.find(n => n.id === selectedEdge.target); if (child)
                    action('story.move', (0, utils_1.commandDefaults)(child)); } }, "Move / reorder child") : react_1.default.createElement("button", { onClick: () => action(selectedEdge.kind === 'assignment' ? 'assignment.remove' : 'link.remove', { id: selectedEdge.id, revision: selectedEdge.revision }) }, "Remove connection\u2026"),
            react_1.default.createElement("button", { onClick: () => setSelectedEdge(null) }, "Close")),
        deleteId && react_1.default.createElement(Primitives_1.Modal, { title: "Remove from view or change the record?", onClose: () => setDeleteId(null) },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("p", null, "Hiding a card changes only this named layout. Archiving or deleting changes the canonical record in every interface."),
                usage ? react_1.default.createElement("pre", { className: "code-preview" }, JSON.stringify(usage, null, 2)) : react_1.default.createElement("p", null, "Checking record references\u2026"),
                react_1.default.createElement("div", { className: "form-stack" },
                    react_1.default.createElement("button", { onClick: () => { setHidden([...hidden, deleteId]); setDirty(true); setDeleteId(null); } }, "Hide from this canvas view"),
                    react_1.default.createElement("button", { onClick: () => { const n = state.entities.find(n => n.id === deleteId); if (n)
                            action('entity.archive', (0, utils_1.commandDefaults)(n)); setDeleteId(null); } }, "Archive underlying record\u2026"),
                    react_1.default.createElement("button", { className: "danger", disabled: !usage?.can_delete, onClick: () => { const n = state.entities.find(n => n.id === deleteId); if (n)
                            action('entity.delete', (0, utils_1.commandDefaults)(n)); setDeleteId(null); } }, "Delete unreferenced record\u2026")))));
}
exports.Canvas = Canvas;

},
"canvas/geometry":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.descendants = exports.edgePath = exports.fit = exports.tidy = exports.hitTest = exports.zoomAt = exports.screenToWorld = exports.clamp = exports.NODE_H = exports.NODE_W = void 0;
exports.NODE_W = 238, exports.NODE_H = 222;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
exports.clamp = clamp;
function screenToWorld(point, view) { return { x: (point.x - view.x) / view.scale, y: (point.y - view.y) / view.scale }; }
exports.screenToWorld = screenToWorld;
function zoomAt(view, point, factor) { const scale = (0, exports.clamp)(view.scale * factor, .15, 3); const world = screenToWorld(point, view); return { scale, x: point.x - world.x * scale, y: point.y - world.y * scale }; }
exports.zoomAt = zoomAt;
function hitTest(point, positions) { return Object.keys(positions).reverse().find(id => { const p = positions[id]; return point.x >= p.x && point.x <= p.x + exports.NODE_W && point.y >= p.y && point.y <= p.y + exports.NODE_H; }) || null; }
exports.hitTest = hitTest;
function tidy(nodes, edges, mode) {
    const result = {};
    const sorted = [...nodes].sort((a, b) => a.position - b.position || a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
    if (mode === 'assets') {
        const types = ['character', 'location', 'prop', 'reference'];
        types.forEach((type, column) => sorted.filter(n => n.fields.type === type).forEach((n, row) => { result[n.id] = { x: column * 320, y: row * 280 }; }));
        return result;
    }
    if (mode === 'scene') {
        let row = 0;
        sorted.filter(n => n.kind === 'scene').forEach(n => { result[n.id] = { x: 0, y: -300 }; });
        sorted.filter(n => n.kind === 'shot').forEach((n, i) => { result[n.id] = { x: i * 310, y: 0 }; });
        sorted.filter(n => n.kind === 'asset').forEach((n, i) => { result[n.id] = { x: (i % 5) * 310, y: 330 + Math.floor(i / 5) * 280 }; });
        return result;
    }
    const children = (id) => sorted.filter(n => n.parent_id === id);
    const visit = (node, depth, top) => { const kids = children(node.id); let cursor = top; for (const child of kids)
        cursor = visit(child, depth + 1, cursor); const height = Math.max(280, cursor - top); result[node.id] = { x: depth * 340, y: top + (height - 280) / 2 }; return top + height; };
    const ids = new Set(nodes.map(n => n.id));
    let cursor = 0;
    for (const root of sorted.filter(n => !n.parent_id || !ids.has(n.parent_id))) {
        cursor = visit(root, root.kind === 'sequence' ? 0 : root.kind === 'scene' ? 1 : 2, cursor) + 60;
    }
    return result;
}
exports.tidy = tidy;
function fit(positions, width, height) { const points = Object.values(positions); if (!points.length)
    return { x: 60, y: 60, scale: 1 }; const x = Math.min(...points.map(p => p.x)), y = Math.min(...points.map(p => p.y)); const w = Math.max(...points.map(p => p.x)) + exports.NODE_W - x, h = Math.max(...points.map(p => p.y)) + exports.NODE_H - y; const scale = (0, exports.clamp)(Math.min((width - 100) / w, (height - 100) / h), .15, 1.2); return { scale, x: (width - w * scale) / 2 - x * scale, y: (height - h * scale) / 2 - y * scale }; }
exports.fit = fit;
function edgePath(a, b) { const start = { x: a.x + exports.NODE_W, y: a.y + exports.NODE_H / 2 }, end = { x: b.x, y: b.y + exports.NODE_H / 2 }; const bend = Math.max(65, Math.abs(end.x - start.x) * .5); return { path: `M ${start.x} ${start.y} C ${start.x + bend} ${start.y}, ${end.x - bend} ${end.y}, ${end.x} ${end.y}`, label: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 } }; }
exports.edgePath = edgePath;
function descendants(nodes, collapsed) { const result = new Set(); const visit = (id) => nodes.filter(n => n.parent_id === id).forEach(n => { result.add(n.id); visit(n.id); }); collapsed.forEach(visit); return result; }
exports.descendants = descendants;

},
"components/ActionDialog":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ActionDialog = void 0;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("./Primitives");
function ActionDialog({ command, state, meta, defaults = {}, onClose, onDone, onReload }) {
    const initialize = (initial) => ({ ...Object.fromEntries(command.fields.map(f => [f.name, initial[f.name] ?? f.default ?? (f.type === 'boolean' ? false : f.type === 'json' ? '{}' : '')])), ...(initial.asset_id ? { asset_id: initial.asset_id } : {}) });
    const [values, setValues] = (0, react_1.useState)(() => initialize(defaults));
    const [busy, setBusy] = (0, react_1.useState)(false);
    const [error, setError] = (0, react_1.useState)(null);
    const [confirmed, setConfirmed] = (0, react_1.useState)(false);
    const set = (name, value) => {
        setValues(previous => {
            const next = { ...previous, [name]: value };
            const record = (0, utils_1.allRecords)(state).find(r => r.id === value);
            if (record && ['id', 'source_id'].includes(name)) {
                next.revision = record.revision;
                if (command.name.endsWith('.update')) {
                    Object.assign(next, (0, utils_1.commandDefaults)(record));
                }
            }
            if (record && name === 'target_id' && 'target_revision' in next)
                next.target_revision = record.revision;
            if (name === 'asset_id')
                next.media_id = '';
            return next;
        });
    };
    async function submit(e) {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
            const payload = {};
            for (const f of command.fields) {
                let v = values[f.name];
                if (v === '' && !f.required) {
                    if (command.name.endsWith('.update') && ['location_id', 'duration', 'media_id'].includes(f.name)) {
                        payload[f.name] = null;
                        continue;
                    }
                    if (f.source || ['integer', 'number', 'json', 'select'].includes(f.type))
                        continue;
                    if (!command.name.endsWith('.update') && !['content', 'notes'].includes(f.name) && f.type !== 'tags')
                        continue;
                }
                if (f.type === 'integer')
                    v = Number.parseInt(v, 10);
                if (f.type === 'number')
                    v = v === '' ? null : Number(v);
                if (f.type === 'json')
                    v = typeof v === 'string' ? JSON.parse(v) : v;
                if (f.type === 'tags')
                    v = Array.isArray(v) ? v : String(v).split(',').map(s => s.trim()).filter(Boolean);
                payload[f.name] = v;
            }
            const result = await (0, api_1.runCommand)(state.project.id, command.name, payload);
            await onDone(result, command.name);
            onClose();
        }
        catch (e) {
            setError(e instanceof api_1.ApiError ? e : new api_1.ApiError('invalid', e instanceof Error ? e.message : String(e)));
        }
        finally {
            setBusy(false);
        }
    }
    async function cancelRun() { try {
        const fresh = await onReload();
        const job = fresh.jobs.find(j => j.id === values.id);
        if (job && ['queued', 'running'].includes(job.status))
            await (0, api_1.runCommand)(state.project.id, 'job.cancel', { id: job.id, revision: job.revision });
    }
    catch (e) {
        setError(e instanceof api_1.ApiError ? e : new api_1.ApiError('invalid', String(e)));
    } }
    async function reload() { const fresh = await onReload(); const current = (0, utils_1.allRecords)(fresh).find(r => r.id === values.id); if (current) {
        setValues(initialize((0, utils_1.commandDefaults)(current)));
        setError(null);
    } }
    return react_1.default.createElement(Primitives_1.Modal, { title: command.label, onClose: () => { if (!busy)
            onClose(); }, wide: command.fields.length > 10 },
        react_1.default.createElement("form", { onSubmit: submit },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("p", { className: "muted" }, command.read_only ? 'Read the same records used by the CLI and terminal app.' : 'Changes are written to your local project. Other interfaces will see the same records.'),
                command.name === 'job.run' && react_1.default.createElement("div", { className: "notice warning" }, "This explicitly launches a registered program with your operating-system permissions. The adapter protocol is not a security sandbox."),
                error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error.message }, error.status === 409 && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("p", null, "Your unsaved fields are still here. Copy any edits to keep, then reload the current record."),
                    react_1.default.createElement("button", { type: "button", onClick: reload }, "Reload current record"))),
                react_1.default.createElement("div", { className: command.fields.length > 10 ? 'form-grid' : 'form-stack' }, command.fields.map(f => {
                    const opts = (0, utils_1.selectOptions)(f, state, meta, values);
                    const isSource = !!f.source || !!f.options.length;
                    if (f.name === 'revision' || f.name === 'target_revision')
                        return react_1.default.createElement("label", { className: "field revision-field", key: f.name },
                            react_1.default.createElement("span", null, f.label),
                            react_1.default.createElement("input", { type: "number", value: values[f.name] ?? '', readOnly: !!defaults.id || !!values.id, min: "1", onChange: (e) => set(f.name, e.target.value), required: f.required }),
                            react_1.default.createElement("small", null, f.help || 'Checked against the current database revision.'));
                    if (f.type === 'boolean')
                        return react_1.default.createElement("label", { className: "check-field", key: f.name },
                            react_1.default.createElement("input", { type: "checkbox", checked: !!values[f.name], onChange: (e) => set(f.name, e.target.checked) }),
                            react_1.default.createElement("span", null, f.label));
                    return react_1.default.createElement("label", { className: `field ${f.type === 'textarea' || f.type === 'json' ? 'full' : ''}`, key: f.name },
                        react_1.default.createElement("span", null,
                            f.label,
                            f.required && react_1.default.createElement("span", { "aria-hidden": "true" }, " *")),
                        isSource ? react_1.default.createElement("select", { value: values[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required },
                            react_1.default.createElement("option", { value: "" }, f.required ? 'Choose…' : 'Not set / inherit'),
                            opts.map(o => react_1.default.createElement("option", { key: o.value, value: o.value }, o.label))) : f.type === 'textarea' || f.type === 'json' ? react_1.default.createElement("textarea", { rows: f.type === 'json' ? 5 : 3, value: typeof values[f.name] === 'object' ? JSON.stringify(values[f.name], null, 2) : values[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required, spellCheck: f.type !== 'json' }) : react_1.default.createElement("input", { type: f.type === 'integer' || f.type === 'number' ? 'number' : 'text', step: f.type === 'number' ? 'any' : undefined, value: Array.isArray(values[f.name]) ? values[f.name].join(', ') : values[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required }),
                        " ",
                        f.help && react_1.default.createElement("small", null, f.help),
                        isSource && !opts.length && f.required && react_1.default.createElement("small", { className: "warning-text" }, "No eligible records yet. Create the prerequisite record first."));
                })),
                command.destructive && react_1.default.createElement("label", { className: "confirm-field" },
                    react_1.default.createElement("input", { type: "checkbox", checked: confirmed, onChange: (e) => setConfirmed(e.target.checked), required: true }),
                    "I have reviewed this action and its effect on this project.")),
            react_1.default.createElement("div", { className: "modal-footer" },
                busy && command.name === 'job.run' && react_1.default.createElement("button", { type: "button", className: "danger", onClick: cancelRun }, "Cancel running job"),
                react_1.default.createElement("button", { type: "button", onClick: onClose, disabled: busy }, "Cancel"),
                react_1.default.createElement("button", { className: command.destructive ? 'danger' : 'primary', type: "submit", disabled: busy || (command.destructive && !confirmed) }, busy ? 'Working…' : command.read_only ? 'Show result' : command.label))));
}
exports.ActionDialog = ActionDialog;

},
"components/Inspector":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.Inspector = void 0;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("./Primitives");
function shotTitle(entity) {
    const number = String(entity.fields.number || '');
    return number && entity.title.startsWith(number)
        ? entity.title.slice(number.length).replace(/^\s*[·—:-]\s*/, '') || entity.title
        : entity.title;
}
function labeledRows(value) {
    return String(value || '').split(/\n+/).flatMap(line => {
        const colon = line.indexOf(':');
        if (colon < 1)
            return [];
        const label = line.slice(0, colon).trim(), text = line.slice(colon + 1).trim();
        return label && text ? [{ label, value: text }] : [];
    });
}
function SpecList({ rows, className = '' }) {
    return react_1.default.createElement("dl", { className: `shot-spec-list ${className}` }, rows.map((row, index) => react_1.default.createElement("div", { className: "shot-spec", key: `${row.label}-${index}` },
        react_1.default.createElement("dt", null, row.label),
        react_1.default.createElement("dd", null, row.value))));
}
function ShotDetails({ entity, state }) {
    const fields = entity.fields;
    const cameraRows = labeledRows(fields.camera);
    const noteRows = labeledRows(fields.notes);
    const framing = String(fields.framing || '');
    const framingBreak = framing.indexOf(' — ');
    const framingLabel = framingBreak < 0 ? framing : framing.slice(0, framingBreak);
    const framingDetail = framingBreak < 0 ? '' : framing.slice(framingBreak + 3);
    const location = state.entities.find(e => e.id === fields.location_id)?.title;
    const scene = state.entities.find(e => e.id === entity.parent_id);
    const sequence = scene && state.entities.find(e => e.id === scene.parent_id);
    const frames = state.frames.filter(frame => frame.shot_id === entity.id);
    const special = new Set(['number', 'action', 'framing', 'duration', 'time', 'location_id', 'camera', 'notes', 'continuity', 'constraints']);
    const otherFields = Object.entries(fields).filter(([key, value]) => !special.has(key) && value !== null && value !== '');
    const action = String(fields.action || entity.description || 'No shot action has been written yet.');
    const displayBeat = shotTitle(entity);
    const summary = action.endsWith(` — ${displayBeat}`) ? action.slice(0, -displayBeat.length - 3) : action;
    const duration = fields.duration == null ? '' : `${Number(fields.duration)} sec`;
    return react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement("div", { className: "shot-detail-hero" },
            (sequence || scene) && react_1.default.createElement("div", { className: "shot-path" },
                sequence?.title,
                sequence && scene ? ' / ' : '',
                scene?.title),
            react_1.default.createElement("p", { className: "shot-action" }, summary),
            react_1.default.createElement("div", { className: "shot-facts" },
                framing && react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Framing"),
                    react_1.default.createElement("strong", null, framingLabel),
                    framingDetail && react_1.default.createElement("small", null, framingDetail)),
                fields.time && react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Time"),
                    react_1.default.createElement("strong", null, String(fields.time))),
                duration && react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Duration"),
                    react_1.default.createElement("strong", null, duration)),
                react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Location"),
                    react_1.default.createElement("strong", null, location || 'Not assigned')),
                react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Storyboard"),
                    react_1.default.createElement("strong", null, frames.length ? `${frames.length} frame${frames.length === 1 ? '' : 's'}` : 'No frame yet')))),
        fields.camera && react_1.default.createElement("section", { className: "detail-field shot-camera-field" },
            react_1.default.createElement("div", { className: "shot-section-heading" },
                react_1.default.createElement("h4", null, "Camera plan"),
                cameraRows.length > 0 && react_1.default.createElement("small", null,
                    cameraRows.length,
                    " settings")),
            cameraRows.length ? react_1.default.createElement(SpecList, { rows: cameraRows }) : react_1.default.createElement("p", { className: "prose" }, String(fields.camera))),
        fields.continuity && react_1.default.createElement("section", { className: "detail-field shot-callout" },
            react_1.default.createElement("h4", null, "Continuity"),
            react_1.default.createElement("p", { className: "prose" }, String(fields.continuity))),
        fields.constraints && react_1.default.createElement("section", { className: "detail-field shot-callout" },
            react_1.default.createElement("h4", null, "Production constraints"),
            react_1.default.createElement("p", { className: "prose" }, String(fields.constraints))),
        fields.notes && react_1.default.createElement("details", { className: "shot-notes-block" },
            react_1.default.createElement("summary", null,
                react_1.default.createElement("span", null, "Image, sound & story notes"),
                react_1.default.createElement("small", null, noteRows.length ? `${noteRows.length} notes` : 'Show notes')),
            noteRows.length ? react_1.default.createElement(SpecList, { rows: noteRows, className: "shot-note-list" }) : react_1.default.createElement("p", { className: "prose" }, String(fields.notes))),
        otherFields.map(([key, value]) => react_1.default.createElement("section", { className: "detail-field", key: key },
            react_1.default.createElement("h4", null, (0, utils_1.human)(key)),
            react_1.default.createElement("p", { className: "prose" }, String(value)))));
}
function Inspector({ state, id, onClose, onSelect, action }) {
    const entity = state.entities.find(e => e.id === id);
    const [tab, setTab] = (0, react_1.useState)('details'), [context, setContext] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)('');
    (0, react_1.useEffect)(() => { setContext(null); setError(''); if (entity && entity.kind !== 'asset')
        (0, api_1.runCommand)(state.project.id, 'context.resolve', { owner_id: id }).then(setContext).catch(e => setError(e.message)); }, [state, id]);
    const panel = (0, react_1.useRef)(null);
    const closeRef = (0, react_1.useRef)(onClose);
    closeRef.current = onClose;
    (0, react_1.useEffect)(() => { if (entity?.kind === 'asset' && tab === 'context')
        setTab('details'); }, [entity?.kind, tab]);
    (0, react_1.useEffect)(() => {
        const narrow = window.matchMedia('(max-width:800px)');
        const el = panel.current;
        let previous = null;
        const sync = () => {
            const main = document.getElementById('main-content');
            if (main)
                main.inert = narrow.matches;
            if (el) {
                el.setAttribute('role', narrow.matches ? 'dialog' : 'complementary');
                if (narrow.matches) {
                    el.setAttribute('aria-modal', 'true');
                    previous = document.activeElement;
                    el.querySelector('button')?.focus();
                }
                else
                    el.removeAttribute('aria-modal');
            }
        };
        const key = (e) => {
            if (!narrow.matches)
                return;
            if (e.key === 'Escape') {
                e.preventDefault();
                closeRef.current();
            }
            if (e.key === 'Tab') {
                const items = Array.from(el?.querySelectorAll('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]') || []).filter(i => i.offsetParent !== null);
                const first = items[0], last = items[items.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last?.focus();
                }
                else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first?.focus();
                }
            }
        };
        sync();
        narrow.addEventListener('change', sync);
        el?.addEventListener('keydown', key);
        return () => { narrow.removeEventListener('change', sync); el?.removeEventListener('keydown', key); const main = document.getElementById('main-content'); if (main)
            main.inert = false; previous?.focus(); };
    }, []);
    if (!entity)
        return null;
    const members = state.asset_media.filter(m => m.asset_id === id), assignments = state.assignments.filter(a => a.shot_id === id || a.asset_id === id), links = state.links.filter(l => l.source_id === id || l.target_id === id), frames = state.frames.filter(f => f.shot_id === id);
    return react_1.default.createElement("aside", { ref: panel, className: "inspector", "aria-label": "Record inspector" },
        react_1.default.createElement("div", { className: "inspector-top" },
            react_1.default.createElement("span", { className: "eyebrow" }, "Inspector"),
            react_1.default.createElement("button", { className: "icon-button", onClick: onClose, "aria-label": "Close inspector" },
                react_1.default.createElement(Primitives_1.Icon, { name: "close" }))),
        react_1.default.createElement("div", { className: "inspector-title" },
            react_1.default.createElement(Primitives_1.Badge, { kind: (0, utils_1.kindLabel)(entity) }, (0, utils_1.kindLabel)(entity)),
            !!entity.archived && react_1.default.createElement(Primitives_1.Badge, null, "archived"),
            react_1.default.createElement("h2", null, entity.kind === 'shot' ? shotTitle(entity) : entity.title),
            entity.kind === 'shot' && react_1.default.createElement("span", { className: "shot-code" },
                String(entity.fields.number || String(entity.position + 1).padStart(2, '0')),
                " \u00B7 shot ",
                String(entity.position + 1).padStart(2, '0')),
            react_1.default.createElement("small", null,
                "Revision ",
                entity.revision,
                " \u00B7 ",
                id.slice(0, 8)),
            react_1.default.createElement("button", { className: "full-button", onClick: () => action(entity.kind + '.update', (0, utils_1.commandDefaults)(entity)) },
                react_1.default.createElement(Primitives_1.Icon, { name: "edit" }),
                "Edit ",
                entity.kind)),
        react_1.default.createElement("div", { className: "tabs", role: "tablist", "aria-label": "Inspector sections" }, ['details', 'references', 'context'].filter(t => t !== 'context' || entity.kind !== 'asset').map(t => react_1.default.createElement("button", { key: t, role: "tab", "aria-selected": tab === t, onClick: () => setTab(t) }, (0, utils_1.human)(t)))),
        react_1.default.createElement("div", { className: "inspector-body" },
            tab === 'details' && react_1.default.createElement(react_1.default.Fragment, null,
                entity.kind === 'shot' ? react_1.default.createElement(ShotDetails, { entity: entity, state: state }) : react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("p", { className: "prose" }, entity.description || 'No description yet.'),
                    Object.entries(entity.fields).filter(([k, v]) => v !== null && v !== '' && k !== 'type').map(([key, value]) => react_1.default.createElement("section", { className: "detail-field", key: key },
                        react_1.default.createElement("h4", null, (0, utils_1.human)(key)),
                        react_1.default.createElement("p", { className: "prose" }, key === 'location_id' ? state.entities.find(e => e.id === value)?.title || String(value) : String(value))))),
                entity.tags.length > 0 && react_1.default.createElement("section", null,
                    react_1.default.createElement("h4", null, "Tags"),
                    react_1.default.createElement("div", { className: "tags" }, entity.tags.map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)))),
                entity.aliases.length > 0 && react_1.default.createElement("section", null,
                    react_1.default.createElement("h4", null, "Also known as"),
                    react_1.default.createElement("p", null, entity.aliases.join(', '))),
                entity.parent_id && react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(entity.parent_id) },
                    "Parent: ",
                    state.entities.find(n => n.id === entity.parent_id)?.title,
                    " \u2192"),
                react_1.default.createElement("h4", null, "Connections"),
                links.map(l => react_1.default.createElement("div", { key: l.id, className: "neighbor-row" },
                    react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(l.source_id === id ? l.target_id : l.source_id) },
                        l.source_id === id ? '→' : '←',
                        " ",
                        state.entities.find(n => n.id === (l.source_id === id ? l.target_id : l.source_id))?.title),
                    react_1.default.createElement("small", null, l.relation),
                    react_1.default.createElement("button", { onClick: () => action('link.remove', (0, utils_1.commandDefaults)(l)) }, "Remove\u2026"))),
                entity.kind === 'asset' && react_1.default.createElement("button", { onClick: () => action('link.create', { source_id: id }) }, "Connect to another asset"),
                ['sequence', 'scene', 'shot'].includes(entity.kind) && react_1.default.createElement("button", { onClick: () => action('story.move', (0, utils_1.commandDefaults)(entity)) }, "Move / reorder\u2026"),
                react_1.default.createElement("details", { className: "record-actions" },
                    react_1.default.createElement("summary", null, "Record lifecycle"),
                    react_1.default.createElement("p", { className: "muted" }, "Changes here affect the record everywhere, not just this view."),
                    react_1.default.createElement("button", { onClick: () => action('entity.usage', { id }) }, "Inspect all references"),
                    react_1.default.createElement("button", { onClick: () => action(entity.archived ? 'entity.restore' : 'entity.archive', (0, utils_1.commandDefaults)(entity)) }, entity.archived ? 'Restore archived record' : 'Archive record…'),
                    react_1.default.createElement("button", { className: "danger", onClick: () => action('entity.delete', (0, utils_1.commandDefaults)(entity)) }, "Delete unreferenced record\u2026"),
                    entity.kind === 'asset' && react_1.default.createElement("button", { onClick: () => action('asset.merge', { source_id: id, revision: entity.revision }) }, "Merge into another asset\u2026"))),
            tab === 'references' && react_1.default.createElement(react_1.default.Fragment, null,
                entity.kind === 'asset' && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("div", { className: "section-heading" },
                        react_1.default.createElement("h3", null, "Reference images"),
                        react_1.default.createElement("button", { onClick: () => action('asset.attach', { asset_id: id }) }, "Attach")),
                    members.map(m => { const image = state.media.find(media => media.id === m.media_id); return react_1.default.createElement("div", { className: "inspector-image", key: m.id },
                        react_1.default.createElement("a", { href: (0, api_1.originalUrl)(state.project.id, m.media_id), target: "_blank", rel: "noreferrer" },
                            react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, m.media_id), alt: image?.original_name || 'Asset reference' })),
                        react_1.default.createElement("strong", null, image?.original_name),
                        react_1.default.createElement("small", null,
                            image?.width,
                            " \u00D7 ",
                            image?.height,
                            " \u00B7 ",
                            image?.format),
                        react_1.default.createElement("div", { className: "button-row" },
                            m.is_primary ? react_1.default.createElement(Primitives_1.Badge, null, "Primary reference") : react_1.default.createElement("button", { onClick: () => action('asset.primary', (0, utils_1.commandDefaults)(m)) }, "Make primary"),
                            react_1.default.createElement("button", { onClick: () => action('asset.detach', (0, utils_1.commandDefaults)(m)) }, "Detach\u2026"))); }),
                    !members.length && react_1.default.createElement("p", { className: "muted" }, "No reference images attached. Import images into intake, then accept them into this asset.")),
                react_1.default.createElement("h3", null, entity.kind === 'asset' ? 'Used by shots' : 'Shot reference assignments'),
                assignments.map(a => { const other = state.entities.find(n => n.id === (entity.kind === 'asset' ? a.shot_id : a.asset_id)); return react_1.default.createElement("div", { className: "reference-row", key: a.id },
                    a.media_id && react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, a.media_id, 160), alt: `Exact ${a.role} reference` }),
                    react_1.default.createElement("div", null,
                        react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(other.id) }, other?.title),
                        react_1.default.createElement("small", null,
                            a.role,
                            " \u00B7 ",
                            a.media_id ? 'exact image selected' : 'no exact image'),
                        react_1.default.createElement("div", { className: "button-row" },
                            react_1.default.createElement("button", { onClick: () => action('assignment.update', { ...(0, utils_1.commandDefaults)(a), asset_id: a.asset_id }) }, "Edit"),
                            react_1.default.createElement("button", { onClick: () => action('assignment.remove', (0, utils_1.commandDefaults)(a)) }, "Remove\u2026")))); }),
                entity.kind === 'shot' && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("button", { onClick: () => action('assignment.create', { shot_id: id }) }, "Assign exact reference"),
                    react_1.default.createElement("h3", null, "Storyboard frames"),
                    frames.map(f => react_1.default.createElement("div", { className: "frame-mini", key: f.id },
                        react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, f.media_id), alt: `Frame candidate ${f.version}` }),
                        react_1.default.createElement("span", null,
                            "Version ",
                            f.version),
                        react_1.default.createElement(Primitives_1.Badge, { kind: f.state }, f.state))),
                    react_1.default.createElement("button", { onClick: () => action('frame.attach', { shot_id: id }) }, "Attach managed frame"))),
            tab === 'context' && react_1.default.createElement(react_1.default.Fragment, null,
                error && react_1.default.createElement("p", { role: "alert" }, error),
                context ? react_1.default.createElement(Primitives_1.ContextView, { value: context }) : react_1.default.createElement("p", null, "Resolving direction\u2026"),
                react_1.default.createElement("button", { onClick: () => action('context.put', { owner_id: id }) }, "Add / override direction block"))));
}
exports.Inspector = Inspector;

},
"components/Primitives":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ExportLinks = exports.ContextView = exports.Validation = exports.Modal = exports.ErrorNotice = exports.Badge = exports.PageHeading = exports.Empty = exports.Icon = void 0;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
function Icon({ name, size = 18 }) {
    const paths = {
        grid: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("rect", { x: "3", y: "3", width: "7", height: "7", rx: "1" }),
            react_1.default.createElement("rect", { x: "14", y: "3", width: "7", height: "7", rx: "1" }),
            react_1.default.createElement("rect", { x: "3", y: "14", width: "7", height: "7", rx: "1" }),
            react_1.default.createElement("rect", { x: "14", y: "14", width: "7", height: "7", rx: "1" })),
        home: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "m3 10 9-7 9 7v11H3z" }),
            react_1.default.createElement("path", { d: "M9 21v-8h6v8" })),
        inbox: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M4 4h16l2 13v4H2v-4z" }),
            react_1.default.createElement("path", { d: "M2 15h6l2 3h4l2-3h6" })),
        library: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }),
            react_1.default.createElement("path", { d: "m4 17 5-6 4 3 3-4 5 7" }),
            react_1.default.createElement("circle", { cx: "8", cy: "7", r: "1" })),
        graph: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("rect", { x: "2", y: "8", width: "6", height: "6", rx: "1" }),
            react_1.default.createElement("rect", { x: "16", y: "2", width: "6", height: "6", rx: "1" }),
            react_1.default.createElement("rect", { x: "16", y: "16", width: "6", height: "6", rx: "1" }),
            react_1.default.createElement("path", { d: "m8 11 8-6M8 11l8 8" })),
        outline: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M5 4v16M5 7h14M5 13h14M5 19h14" }),
            react_1.default.createElement("circle", { cx: "5", cy: "7", r: "1" }),
            react_1.default.createElement("circle", { cx: "5", cy: "13", r: "1" })),
        guide: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M3 4h7l2 2 2-2h7v16h-7l-2 1-2-1H3zM12 6v15" })),
        edit: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "m4 16 12-12 4 4L8 20l-5 1zM13 7l4 4" })),
        frames: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("rect", { x: "2", y: "5", width: "14", height: "14", rx: "1" }),
            react_1.default.createElement("path", { d: "M19 3h3v18h-3M2 15l4-4 4 4 3-2 3 4" })),
        export: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M12 3v12m-5-5 5 5 5-5M3 17v4h18v-4" })),
        settings: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M3 6h18M3 12h18M3 18h18" }),
            react_1.default.createElement("circle", { cx: "8", cy: "6", r: "2" }),
            react_1.default.createElement("circle", { cx: "16", cy: "12", r: "2" }),
            react_1.default.createElement("circle", { cx: "10", cy: "18", r: "2" })),
        automation: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "m9 4-6 8 6 8M15 4l6 8-6 8M14 3l-4 18" })),
        plus: react_1.default.createElement("path", { d: "M12 4v16M4 12h16" }),
        close: react_1.default.createElement("path", { d: "m6 6 12 12M6 18 12-12" }),
        chevron: react_1.default.createElement("path", { d: "m9 5 7 7-7 7" }),
        search: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("circle", { cx: "10", cy: "10", r: "6" }),
            react_1.default.createElement("path", { d: "m15 15 6 6" })),
        check: react_1.default.createElement("path", { d: "m4 12 5 5L20 6" }),
        arrow: react_1.default.createElement("path", { d: "M3 12h18m-7-7 7 7-7 7" }),
        refresh: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M20 8a8 8 0 1 0 1 7M20 3v5h-5" })),
        menu: react_1.default.createElement("path", { d: "M3 5h18M3 12h18M3 19h18" }),
    };
    return react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true" }, paths[name] || paths.grid);
}
exports.Icon = Icon;
function Empty({ title, children, action }) { return react_1.default.createElement("div", { className: "empty" },
    react_1.default.createElement("span", { className: "empty-mark" },
        react_1.default.createElement(Icon, { name: "outline", size: 28 })),
    react_1.default.createElement("h3", null, title),
    react_1.default.createElement("p", null, children),
    action); }
exports.Empty = Empty;
function PageHeading({ eyebrow, title, description, actions }) { return react_1.default.createElement("header", { className: "page-heading" },
    react_1.default.createElement("div", null,
        react_1.default.createElement("p", { className: "eyebrow" }, eyebrow),
        react_1.default.createElement("h1", null, title),
        description && react_1.default.createElement("p", { className: "lede" }, description)),
    actions && react_1.default.createElement("div", { className: "heading-actions" }, actions)); }
exports.PageHeading = PageHeading;
function Badge({ kind, children }) { return react_1.default.createElement("span", { className: `badge ${kind || ''}` }, children); }
exports.Badge = Badge;
function ErrorNotice({ error, children }) { return react_1.default.createElement("div", { className: "notice error", role: "alert" },
    react_1.default.createElement("strong", null, "Could not complete this action."),
    react_1.default.createElement("p", null, error),
    children); }
exports.ErrorNotice = ErrorNotice;
function Modal({ title, children, onClose, wide = false }) {
    const dialog = (0, react_1.useRef)(null);
    const closeRef = (0, react_1.useRef)(onClose);
    closeRef.current = onClose;
    (0, react_1.useEffect)(() => {
        const previous = document.activeElement;
        const el = dialog.current;
        const focusable = () => Array.from(el?.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]') || []).filter(x => x.offsetParent !== null);
        (focusable()[0] || el)?.focus();
        const handler = (event) => { if (event.key === 'Escape') {
            event.preventDefault();
            closeRef.current();
        } if (event.key === 'Tab') {
            const items = focusable();
            const first = items[0], last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            }
            else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        } };
        el?.addEventListener('keydown', handler);
        return () => { el?.removeEventListener('keydown', handler); previous?.focus(); };
    }, []);
    return react_1.default.createElement("div", { className: "modal-backdrop", onMouseDown: (e) => { if (e.target === e.currentTarget)
            onClose(); } },
        react_1.default.createElement("div", { ref: dialog, className: `modal ${wide ? 'wide' : ''}`, role: "dialog", "aria-modal": "true", "aria-labelledby": "modal-title", tabIndex: -1 },
            react_1.default.createElement("div", { className: "modal-heading" },
                react_1.default.createElement("h2", { id: "modal-title" }, title),
                react_1.default.createElement("button", { className: "icon-button", onClick: onClose, "aria-label": "Close dialog" },
                    react_1.default.createElement(Icon, { name: "close" }))),
            children));
}
exports.Modal = Modal;
function Validation({ issues }) { if (!issues.length)
    return react_1.default.createElement("p", { className: "success-line" },
        react_1.default.createElement(Icon, { name: "check" }),
        " All selected media is available."); return react_1.default.createElement("div", { className: "validation" },
    react_1.default.createElement("h3", null,
        "Production checks ",
        react_1.default.createElement("span", { className: "count" }, issues.length)),
    issues.map((i, n) => react_1.default.createElement("div", { key: `${i.code}-${n}`, className: `check-row ${i.severity}` },
        react_1.default.createElement(Badge, null, i.severity),
        react_1.default.createElement("span", null, i.message)))); }
exports.Validation = Validation;
function ContextView({ value }) { return react_1.default.createElement("div", { className: "context-view" },
    react_1.default.createElement("div", { className: "scope-chain" }, value.chain.map((c, i) => react_1.default.createElement("span", { key: c.id },
        i > 0 && ' / ',
        c.title))),
    Object.entries(value.scalars).map(([key, entry]) => react_1.default.createElement("div", { className: "context-value", key: key },
        react_1.default.createElement("span", { className: "eyebrow" }, (0, utils_1.human)(key)),
        react_1.default.createElement("strong", null, entry.label || entry.value),
        react_1.default.createElement("small", null,
            "From ",
            entry.source.kind,
            ": ",
            entry.source.title))),
    Object.entries(value.blocks).map(([key, entries]) => react_1.default.createElement("section", { className: "direction-block", key: key },
        react_1.default.createElement("h4", null, (0, utils_1.human)(key)),
        entries.map((e, i) => react_1.default.createElement("div", { key: e.block_id || `${e.source.id}-${i}` },
            react_1.default.createElement("p", { className: "prose" }, e.text),
            react_1.default.createElement("small", null,
                "From ",
                e.source.kind,
                ": ",
                e.source.title))))),
    !Object.keys(value.blocks).length && !Object.keys(value.scalars).length && react_1.default.createElement("p", { className: "muted" }, "No direction is authored at this scope yet. Start with the project guide."),
    value.history.filter(h => h.operation !== 'append').map((h, i) => react_1.default.createElement("p", { className: "context-rule", key: `${h.key}-${i}` },
        react_1.default.createElement(Badge, null, h.operation),
        " ",
        (0, utils_1.human)(h.key),
        " at ",
        h.source.title,
        h.removed_sources.length ? ` · replaces/excludes ${h.removed_sources.length} inherited entries` : ''))); }
exports.ContextView = ContextView;
function ExportLinks({ project, result }) { return react_1.default.createElement("div", { className: "export-result" },
    react_1.default.createElement("p", { className: "success-line" },
        react_1.default.createElement(Icon, { name: "check" }),
        " Export saved in your project folder."),
    react_1.default.createElement("code", null, result.path),
    react_1.default.createElement("div", { className: "button-row" },
        result.archive && react_1.default.createElement("a", { className: "button primary", href: (0, api_1.exportUrl)(project, result.archive, true) },
            "Download self-contained ZIP ",
            react_1.default.createElement(Icon, { name: "export" })),
        result.view && react_1.default.createElement("a", { className: "button", href: (0, api_1.exportUrl)(project, result.view), target: "_blank", rel: "noreferrer" },
            "Open board ",
            react_1.default.createElement(Icon, { name: "arrow" }))),
    react_1.default.createElement("details", null,
        react_1.default.createElement("summary", null, "Individual files"),
        react_1.default.createElement("div", { className: "file-links" }, result.files?.filter(p => !p.endsWith('.zip')).map(path => react_1.default.createElement("a", { key: path, href: (0, api_1.exportUrl)(project, path, true) }, path.split('/').pop())))),
    result.validation && react_1.default.createElement(Validation, { issues: result.validation })); }
exports.ExportLinks = ExportLinks;

},
"main":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
const react_1 = __importStar(require("./react"));
const App_1 = require("./App");
class Boundary extends react_1.default.Component {
    constructor() {
        super(...arguments);
        this.state = { error: null };
    }
    static getDerivedStateFromError(error) { return { error }; }
    render() { if (this.state.error)
        return react_1.default.createElement("main", { className: "fatal-error" },
            react_1.default.createElement("h1", null, "The workspace view could not render."),
            react_1.default.createElement("p", null, "Your project records are still stored locally. Reload the app, or use the CLI to check the project."),
            react_1.default.createElement("pre", null, this.state.error.message),
            react_1.default.createElement("button", { onClick: () => location.reload() }, "Reload application")); return this.props.children; }
}
const root = document.getElementById('root');
if (!root)
    throw new Error('Storyboarder root element is missing.');
(0, react_1.createRoot)(root).render(react_1.default.createElement(Boundary, null,
    react_1.default.createElement(App_1.App, null)));

},
"pages/OutlinePage":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.OutlinePage = void 0;
const react_1 = __importStar(require("../react"));
const utils_1 = require("../utils");
const Primitives_1 = require("../components/Primitives");
function shotTitle(entity) {
    const number = String(entity.fields.number || '');
    return number && entity.title.startsWith(number)
        ? entity.title.slice(number.length).replace(/^\s*[·—:-]\s*/, '') || entity.title
        : entity.title;
}
function outlineTitle(entity) {
    if (entity.kind === 'shot')
        return shotTitle(entity);
    return entity.title.replace(/^\d{2}\s*[·—:-]\s*/, '') || entity.title;
}
function shotAction(entity) {
    const action = String(entity.fields.action || entity.description || 'No shot direction yet.');
    const title = shotTitle(entity);
    return action.endsWith(` — ${title}`) ? action.slice(0, -title.length - 3) : action;
}
function repeatsShotSummaries(entity, shots) {
    const lines = String(entity.fields.summary || '').split(/\n+/).map(line => line.trim()).filter(Boolean);
    return shots.length > 0 && lines.length === shots.length && lines.every((line, index) => {
        const title = shotTitle(shots[index]);
        return line.toLowerCase().startsWith(`${title.toLowerCase()}:`);
    });
}
function framingParts(entity) {
    const framing = String(entity.fields.framing || '');
    const split = framing.indexOf(' — ');
    return split < 0 ? { label: framing, detail: '' } : { label: framing.slice(0, split), detail: framing.slice(split + 3) };
}
function OutlinePage(p) {
    const [query, setQuery] = (0, react_1.useState)('');
    const [collapsed, setCollapsed] = (0, react_1.useState)([]);
    const records = (0, utils_1.activeEntities)(p.state).filter(e => ['sequence', 'scene', 'shot'].includes(e.kind));
    const byId = new Map(records.map(e => [e.id, e]));
    const childrenByParent = new Map();
    for (const record of records) {
        if (!record.parent_id)
            continue;
        const siblings = childrenByParent.get(record.parent_id) || [];
        siblings.push(record);
        childrenByParent.set(record.parent_id, siblings);
    }
    for (const siblings of childrenByParent.values())
        siblings.sort((a, b) => a.position - b.position);
    const visibleIds = new Set(records.filter(e => [
        e.title, e.fields.action || '', e.fields.summary || '', e.fields.number || '', e.fields.framing || '',
    ].join(' ').toLowerCase().includes(query.toLowerCase())).map(e => e.id));
    for (const id of [...visibleIds]) {
        let current = byId.get(id);
        while (current?.parent_id) {
            visibleIds.add(current.parent_id);
            current = byId.get(current.parent_id);
        }
    }
    const children = (id) => (childrenByParent.get(id) || []).filter(e => visibleIds.has(e.id));
    const sequenceShotCounts = new Map();
    for (const shot of records.filter(e => e.kind === 'shot')) {
        const scene = byId.get(shot.parent_id || '');
        if (scene?.parent_id)
            sequenceShotCounts.set(scene.parent_id, (sequenceShotCounts.get(scene.parent_id) || 0) + 1);
    }
    const totals = {
        sequences: records.filter(e => e.kind === 'sequence').length,
        scenes: records.filter(e => e.kind === 'scene').length,
        shots: records.filter(e => e.kind === 'shot').length,
    };
    const render = (entity) => {
        const nested = children(entity.id);
        const isCollapsed = collapsed.includes(entity.id);
        const sceneCount = nested.filter(e => e.kind === 'scene').length;
        const shotCount = entity.kind === 'sequence'
            ? sequenceShotCounts.get(entity.id) || 0
            : nested.filter(e => e.kind === 'shot').length;
        const sceneShots = (childrenByParent.get(entity.id) || []).filter(child => child.kind === 'shot');
        const rawSummary = entity.kind === 'shot'
            ? shotAction(entity)
            : entity.kind === 'scene'
                ? String(entity.fields.summary || entity.description || '')
                : String(entity.fields.arc || entity.description || 'No direction yet.');
        const summary = entity.kind === 'scene' && (repeatsShotSummaries(entity, sceneShots) || /^Grouped from source scene\b/.test(rawSummary)) ? '' : rawSummary;
        const frame = entity.kind === 'shot' ? framingParts(entity) : null;
        const number = String(entity.fields.number || String(entity.position + 1).padStart(2, '0'));
        const title = outlineTitle(entity);
        return react_1.default.createElement("div", { key: entity.id, className: `story-node node-${entity.kind}` },
            react_1.default.createElement("div", { className: `story-row ${p.selected === entity.id ? 'is-selected' : ''}` },
                entity.kind === 'shot'
                    ? react_1.default.createElement("span", { className: "shot-order" }, number)
                    : react_1.default.createElement("button", { className: "collapse-button", "aria-label": `${isCollapsed ? 'Expand' : 'Collapse'} ${entity.title}`, "aria-expanded": !isCollapsed, onClick: () => setCollapsed(value => isCollapsed ? value.filter(id => id !== entity.id) : [...value, entity.id]) }, isCollapsed ? '+' : '−'),
                react_1.default.createElement("div", { className: "story-main" },
                    react_1.default.createElement("div", { className: "story-heading-line" },
                        react_1.default.createElement("span", { className: "eyebrow" },
                            entity.kind,
                            " \u00B7 ",
                            String(entity.position + 1).padStart(2, '0')),
                        entity.kind === 'sequence' && react_1.default.createElement("span", { className: "story-count" },
                            sceneCount,
                            " scenes \u00B7 ",
                            shotCount,
                            " shots"),
                        entity.kind === 'scene' && react_1.default.createElement("span", { className: "story-count" },
                            shotCount,
                            " ",
                            shotCount === 1 ? 'shot' : 'shots')),
                    react_1.default.createElement("button", { className: "title-button", onClick: () => p.select(entity.id) }, title),
                    summary && react_1.default.createElement("p", null, summary),
                    frame && react_1.default.createElement("div", { className: "shot-meta-strip" },
                        frame.label && react_1.default.createElement("span", { className: "shot-meta-kind" }, frame.label),
                        entity.fields.duration != null && react_1.default.createElement("span", null,
                            Number(entity.fields.duration),
                            " sec"),
                        entity.fields.time && react_1.default.createElement("span", null, String(entity.fields.time)))),
                react_1.default.createElement("div", { className: "row-actions" },
                    entity.kind !== 'shot' && react_1.default.createElement("button", { onClick: () => p.action(entity.kind === 'sequence' ? 'scene.create' : 'shot.create', { parent_id: entity.id }) },
                        react_1.default.createElement(Primitives_1.Icon, { name: "plus", size: 14 }),
                        entity.kind === 'sequence' ? 'Scene' : 'Shot'),
                    react_1.default.createElement("button", { onClick: () => p.action(entity.kind + '.update', (0, utils_1.commandDefaults)(entity)) }, "Edit"),
                    react_1.default.createElement("button", { onClick: () => p.action('story.move', (0, utils_1.commandDefaults)(entity)) }, "Move / reorder"))),
            !isCollapsed && nested.length > 0 && react_1.default.createElement("div", { className: `story-children children-${entity.kind} ${entity.kind === 'scene' && shotCount === 1 ? 'single-shot' : ''}` }, nested.map(render)));
    };
    const sequences = children(p.state.project.id).filter(e => e.kind === 'sequence');
    return react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Story outline", title: "Build the order of things.", description: "Sequences contain scenes; scenes contain shots. Reordering changes the story, never the identity of a record.", actions: react_1.default.createElement("button", { className: "primary", onClick: () => p.action('sequence.create') },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New sequence") }),
        react_1.default.createElement("div", { className: "outline-toolbar" },
            react_1.default.createElement("div", { className: "outline-totals", "aria-label": "Story records" },
                react_1.default.createElement("span", null,
                    react_1.default.createElement("strong", null, totals.sequences),
                    " sequences"),
                react_1.default.createElement("i", null),
                react_1.default.createElement("span", null,
                    react_1.default.createElement("strong", null, totals.scenes),
                    " scenes"),
                react_1.default.createElement("i", null),
                react_1.default.createElement("span", null,
                    react_1.default.createElement("strong", null, totals.shots),
                    " shots")),
            react_1.default.createElement("div", { className: "list-toolbar" },
                react_1.default.createElement("label", { className: "search" },
                    react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                    react_1.default.createElement("input", { "aria-label": "Search story outline", value: query, onChange: (e) => setQuery(e.target.value), placeholder: "Find a scene or shot\u2026" })),
                react_1.default.createElement("button", { onClick: () => setCollapsed([]) }, "Expand all"),
                react_1.default.createElement("button", { onClick: () => p.go('canvas') }, "View on canvas"))),
        react_1.default.createElement("div", { className: "story-outline" }, sequences.map(render)),
        !records.length && react_1.default.createElement(Primitives_1.Empty, { title: "First, a sequence", action: react_1.default.createElement("button", { onClick: () => p.action('sequence.create') }, "Create a sequence") }, "The outline keeps the canonical order shared by the canvas, TUI, CLI, and exports."));
}
exports.OutlinePage = OutlinePage;

},
"pages/Pages":function(require,module,exports){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AutomationPage = exports.SettingsPage = exports.CompositionPage = exports.FramesPage = exports.EditorPage = exports.GuidePage = exports.ScopeSelect = exports.OutlinePage = exports.LibraryPage = exports.IntakePage = exports.UploadControl = exports.OverviewPage = exports.WorkspacePage = void 0;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("../components/Primitives");
function recordButtons(p, e) { return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement("button", { onClick: () => p.select(e.id) }, "Inspect"),
    react_1.default.createElement("button", { onClick: () => p.action(e.kind + '.update', (0, utils_1.commandDefaults)(e)) }, "Edit")); }
function WorkspacePage({ session, projects, onOpen, onRefresh }) {
    const [creating, setCreating] = (0, react_1.useState)(false), [title, setTitle] = (0, react_1.useState)(''), [slug, setSlug] = (0, react_1.useState)(''), [search, setSearch] = (0, react_1.useState)(''), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false);
    async function create(e) { e.preventDefault(); setBusy(true); setError(''); try {
        const p = await (0, api_1.api)('/projects', 'POST', { title, ...(slug ? { slug } : {}) });
        await onRefresh();
        await onOpen(p.id);
        setCreating(false);
    }
    catch (e) {
        setError(e.message);
    }
    finally {
        setBusy(false);
    } }
    return react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Local production desk", title: "Your work, in one place.", description: "A portable folder for each story. No account, no cloud dependency.", actions: session.can_create ? react_1.default.createElement("button", { className: "primary", onClick: () => setCreating(true) },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New project") : react_1.default.createElement(Primitives_1.Badge, null, "Standalone project") }),
        react_1.default.createElement("div", { className: "workspace-intro" },
            react_1.default.createElement("span", { className: "eyebrow" }, "Workspace"),
            react_1.default.createElement("code", null, session.workspace || 'Direct project launch'),
            react_1.default.createElement("p", null, "Images stay on disk. Story records stay in their project database. Open a project to begin.")),
        react_1.default.createElement("div", { className: "list-toolbar" },
            react_1.default.createElement("label", { className: "search" },
                react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                react_1.default.createElement("input", { "aria-label": "Find a project", placeholder: "Find a project\u2026", value: search, onChange: (e) => setSearch(e.target.value) })),
            react_1.default.createElement("button", { onClick: onRefresh },
                react_1.default.createElement(Primitives_1.Icon, { name: "refresh" }),
                "Refresh projects")),
        react_1.default.createElement("div", { className: "project-list" }, projects.filter(p => p.title.toLowerCase().includes(search.toLowerCase())).map((p, i) => react_1.default.createElement("button", { className: "project-row", key: p.id, disabled: !p.available, onClick: () => onOpen(p.id) },
            react_1.default.createElement("span", { className: "project-number" }, String(i + 1).padStart(2, '0')),
            react_1.default.createElement("div", null,
                react_1.default.createElement("h2", null, p.title),
                react_1.default.createElement("p", null, p.description || 'A story waiting to take shape.'),
                react_1.default.createElement("small", null, p.path)),
            react_1.default.createElement("span", { className: "project-stats" },
                p.counts?.scene || 0,
                " scenes",
                react_1.default.createElement("br", null),
                p.counts?.asset || 0,
                " assets"),
            react_1.default.createElement("span", { className: "project-status" },
                p.recent ? react_1.default.createElement(Primitives_1.Badge, null, "Recent") : p.available ? react_1.default.createElement(Primitives_1.Badge, null, "Local") : react_1.default.createElement(Primitives_1.Badge, null, "Unavailable"),
                react_1.default.createElement(Primitives_1.Icon, { name: "arrow" }))))),
        !projects.length && react_1.default.createElement(Primitives_1.Empty, { title: "Start with an empty folder", action: session.can_create ? react_1.default.createElement("button", { className: "primary", onClick: () => setCreating(true) }, "Create your first project") : undefined }, "Create a project in this workspace. References, sequences, shots, and exports will all live together."),
        react_1.default.createElement("p", { className: "footnote" },
            "To open a project outside this workspace, launch ",
            react_1.default.createElement("code", null, "storyboarder ui --project /path/to/project"),
            " from your terminal."),
        creating && react_1.default.createElement(Primitives_1.Modal, { title: "Create a project", onClose: () => setCreating(false) },
            react_1.default.createElement("form", { onSubmit: create },
                react_1.default.createElement("div", { className: "modal-body form-stack" },
                    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Project title"),
                        react_1.default.createElement("input", { autoFocus: true, value: title, onChange: (e) => { setTitle(e.target.value); setSlug(e.target.value.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')); }, required: true, maxLength: 200 })),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Folder name"),
                        react_1.default.createElement("input", { value: slug, onChange: (e) => setSlug(e.target.value), pattern: "[a-z0-9]+(?:-[a-z0-9]+)*", required: true }),
                        react_1.default.createElement("small", null, "Created inside this workspace\u2019s projects/ folder."))),
                react_1.default.createElement("div", { className: "modal-footer" },
                    react_1.default.createElement("button", { type: "button", onClick: () => setCreating(false) }, "Cancel"),
                    react_1.default.createElement("button", { className: "primary", disabled: busy }, busy ? 'Creating…' : 'Create project')))));
}
exports.WorkspacePage = WorkspacePage;
function OverviewPage(p) { const { state } = p; const [health, setHealth] = (0, react_1.useState)(null); (0, react_1.useEffect)(() => { (0, api_1.runCommand)(state.project.id, 'project.doctor').then(setHealth).catch(() => setHealth(null)); }, [state]); const seq = (0, utils_1.activeEntities)(state, 'sequence'); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Project overview", title: state.project.title, description: String(state.project.fields.premise || state.project.description || 'Give the story a shape. Gather references, build the outline, and make each shot intentional.'), actions: react_1.default.createElement("button", { onClick: () => p.action('project.update', (0, utils_1.commandDefaults)(state.project)) }, "Edit project guide") }),
    react_1.default.createElement("div", { className: "metrics" }, [['Scenes', 'scene'], ['Shots', 'shot'], ['Reference assets', 'asset'], ['Awaiting review', 'intake']].map(([label, key]) => react_1.default.createElement("button", { key: key, onClick: () => p.go(key === 'asset' ? 'library' : key === 'intake' ? 'intake' : 'outline') },
        react_1.default.createElement("strong", null, state.project.counts[key] || 0),
        react_1.default.createElement("span", null, label),
        react_1.default.createElement(Primitives_1.Icon, { name: "arrow", size: 16 })))),
    react_1.default.createElement("div", { className: "overview-columns" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "The story so far"),
                react_1.default.createElement("button", { onClick: () => p.action('sequence.create') }, "New sequence")),
            seq.length ? seq.map(s => react_1.default.createElement("div", { className: "outline-summary", key: s.id },
                react_1.default.createElement("span", { className: "order-number" }, String(s.position + 1).padStart(2, '0')),
                react_1.default.createElement("div", null,
                    react_1.default.createElement("button", { className: "title-button", onClick: () => p.select(s.id) }, s.title),
                    react_1.default.createElement("p", null, s.fields.arc || s.description || 'Sequence direction not yet authored.'),
                    react_1.default.createElement("small", null,
                        state.entities.filter(e => !e.archived && e.parent_id === s.id).length,
                        " scenes")),
                react_1.default.createElement("button", { onClick: () => p.action('scene.create', { parent_id: s.id }) }, "Add scene"))) : react_1.default.createElement(Primitives_1.Empty, { title: "Begin with a sequence", action: react_1.default.createElement("button", { onClick: () => p.action('sequence.create') }, "Create a sequence") }, "A sequence holds scenes. Each scene holds the shots that carry it."),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Direction"),
                react_1.default.createElement("button", { className: "text-button", onClick: () => p.go('guide') }, "Open guide \u2192")),
            react_1.default.createElement("p", { className: "prose" }, state.project.fields.visual_style || 'Set the visual style, global constraints, and reusable direction in the story guide.')),
        react_1.default.createElement("aside", { className: "overview-notes" },
            react_1.default.createElement("h2", null, "At the desk"),
            health && react_1.default.createElement("div", { className: `health-summary ${health.healthy ? 'healthy' : 'warning'}` },
                react_1.default.createElement(Primitives_1.Icon, { name: health.healthy ? 'check' : 'settings' }),
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, health.healthy ? 'Project files are in order' : 'Project needs attention'),
                    react_1.default.createElement("p", null, health.issues.length ? `${health.issues.length} item(s) to review.` : 'Database and media paths passed the current check.'),
                    react_1.default.createElement("button", { className: "text-button", onClick: () => p.go('settings') }, "View health report \u2192"))),
            react_1.default.createElement("h3", null, "Recent changes"),
            react_1.default.createElement("ol", { className: "event-list" }, state.events.slice(0, 10).map(e => react_1.default.createElement("li", { key: e.id },
                react_1.default.createElement("span", null, (0, utils_1.human)(e.action.replaceAll('.', ' '))),
                react_1.default.createElement("small", null, (0, utils_1.niceDate)(e.created_at))))),
            react_1.default.createElement("div", { className: "notice" }, "This is a local workspace. Back up the project folder regularly; there is no remote copy unless you make one.")))); }
exports.OverviewPage = OverviewPage;
function UploadControl({ project, shot, done }) { const [recursive, setRecursive] = (0, react_1.useState)(false), [status, setStatus] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false), [failures, setFailures] = (0, react_1.useState)([]); async function upload(files) { if (!files)
    return; setBusy(true); setFailures([]); const eligible = Array.from(files).filter(f => recursive || !f.webkitRelativePath || f.webkitRelativePath.split('/').length <= 2); const errors = []; let accepted = 0; for (let i = 0; i < eligible.length; i++) {
    const file = eligible[i];
    setStatus(`Importing ${i + 1} of ${eligible.length}: ${file.name}`);
    try {
        const data = new FormData();
        data.append('file', file);
        data.append('original_path', file.webkitRelativePath || file.name);
        if (shot)
            data.append('shot_id', shot);
        await (0, api_1.api)((0, api_1.projectPath)(project, '/upload'), 'POST', data);
        accepted++;
    }
    catch (e) {
        errors.push(`${file.name}: ${e.message}`);
    }
} setStatus(`${accepted} imported; ${errors.length} rejected${files.length !== eligible.length ? `; ${files.length - eligible.length} nested files skipped` : ''}.`); setFailures(errors); setBusy(false); await done(); } return react_1.default.createElement("div", { className: "upload-control" },
    react_1.default.createElement("div", { className: "button-row" },
        react_1.default.createElement("label", { className: `button ${busy ? 'disabled' : ''}` },
            react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
            shot ? 'Attach frame image' : 'Import images',
            react_1.default.createElement("input", { type: "file", accept: ".jpg,.jpeg,.png,.webp,.tif,.tiff,.bmp", multiple: true, hidden: true, disabled: busy, onChange: (e) => { upload(e.target.files); e.target.value = ''; } })),
        !shot && react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("label", { className: `button ${busy ? 'disabled' : ''}` },
                "Import folder",
                react_1.default.createElement("input", { type: "file", webkitdirectory: "", multiple: true, hidden: true, disabled: busy, onChange: (e) => { upload(e.target.files); e.target.value = ''; } })),
            react_1.default.createElement("label", { className: "inline-check" },
                react_1.default.createElement("input", { type: "checkbox", checked: recursive, onChange: (e) => setRecursive(e.target.checked) }),
                "Include nested folders"))),
    react_1.default.createElement("small", null, "JPEG, PNG, WebP, TIFF, BMP \u00B7 single images \u00B7 up to 50 MiB / 50 megapixels each."),
    status && react_1.default.createElement("p", { role: "status" }, status),
    failures.length > 0 && react_1.default.createElement("details", { open: true },
        react_1.default.createElement("summary", null,
            failures.length,
            " files not imported"),
        failures.map((f, i) => react_1.default.createElement("p", { className: "warning-text", key: i }, f)))); }
exports.UploadControl = UploadControl;
function IntakePage(p) { const [filter, setFilter] = (0, react_1.useState)('pending'), [query, setQuery] = (0, react_1.useState)(''), [checked, setChecked] = (0, react_1.useState)([]), [bulk, setBulk] = (0, react_1.useState)(''), [bulkTags, setBulkTags] = (0, react_1.useState)(''), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false); const items = p.state.intake.filter(i => (!filter || i.state === filter) && i.original_name.toLowerCase().includes(query.toLowerCase())).sort((a, b) => a.media_id.localeCompare(b.media_id)); async function acceptBulk() { setBusy(true); try {
    for (const id of checked) {
        const item = p.state.intake.find(i => i.id === id);
        if (item && item.state === 'pending')
            await (0, api_1.runCommand)(p.state.project.id, 'intake.accept', { id, revision: item.revision, ...(bulk ? { asset_id: bulk } : {}), tags: bulkTags.split(',').map(s => s.trim()).filter(Boolean) });
    }
    setChecked([]);
    await p.refresh();
    p.notify('Selected intake items accepted.');
}
catch (e) {
    setError(e.message);
    await p.refresh();
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Reference intake", title: "Give each image a place.", description: "Review imported files, group exact duplicates, and connect the useful ones to the story." }),
    react_1.default.createElement(UploadControl, { project: p.state.project.id, done: p.refresh }),
    react_1.default.createElement("div", { className: "list-toolbar" },
        react_1.default.createElement("label", { className: "search" },
            react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
            react_1.default.createElement("input", { value: query, onChange: (e) => setQuery(e.target.value), placeholder: "Find imported files\u2026", "aria-label": "Search intake" })),
        react_1.default.createElement("select", { "aria-label": "Intake state", value: filter, onChange: (e) => { setFilter(e.target.value); setChecked([]); } }, ['pending', 'accepted', 'discarded', ''].map(s => react_1.default.createElement("option", { key: s, value: s }, s ? (0, utils_1.human)(s) : 'All states')))),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    " ",
    checked.length > 0 && react_1.default.createElement("div", { className: "bulk-bar" },
        react_1.default.createElement("strong", null,
            checked.length,
            " selected"),
        react_1.default.createElement("select", { "aria-label": "Bulk destination asset", value: bulk, onChange: (e) => setBulk(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "Accept as managed media"),
            (0, utils_1.activeEntities)(p.state, 'asset').map(a => react_1.default.createElement("option", { key: a.id, value: a.id }, a.title))),
        react_1.default.createElement("input", { "aria-label": "Bulk tags", value: bulkTags, onChange: (e) => setBulkTags(e.target.value), placeholder: "Tags, comma-separated" }),
        react_1.default.createElement("button", { onClick: acceptBulk, disabled: busy }, "Accept selected"),
        react_1.default.createElement("button", { onClick: () => setChecked([]) }, "Clear selection")),
    react_1.default.createElement("div", { className: "intake-list" }, items.map(item => { const m = p.state.media.find(m => m.id === item.media_id); const duplicates = p.state.intake.filter(i => i.media_id === item.media_id).length; return react_1.default.createElement("article", { className: "intake-row", key: item.id },
        react_1.default.createElement("input", { type: "checkbox", "aria-label": `Select ${item.original_name}`, checked: checked.includes(item.id), disabled: item.state !== 'pending', onChange: () => setChecked(v => v.includes(item.id) ? v.filter(id => id !== item.id) : [...v, item.id]) }),
        react_1.default.createElement("a", { href: (0, api_1.originalUrl)(p.state.project.id, m.id), target: "_blank", rel: "noreferrer" },
            react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, m.id, 160), alt: item.original_name })),
        react_1.default.createElement("div", { className: "intake-info" },
            react_1.default.createElement("h3", null, item.original_name),
            react_1.default.createElement("p", null,
                m.width,
                " \u00D7 ",
                m.height,
                " \u00B7 ",
                m.format,
                " \u00B7 ",
                (m.size / 1024 / 1024).toFixed(1),
                " MiB"),
            react_1.default.createElement("small", { title: item.original_path }, item.original_path),
            react_1.default.createElement("div", { className: "tags" },
                react_1.default.createElement(Primitives_1.Badge, null, item.state),
                duplicates > 1 && react_1.default.createElement(Primitives_1.Badge, { kind: "warning" },
                    "Exact hash group \u00B7 ",
                    duplicates,
                    " imports"),
                m.tags.map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)))),
        react_1.default.createElement("div", { className: "row-actions" },
            item.state === 'pending' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("button", { onClick: () => p.action('intake.accept', (0, utils_1.commandDefaults)(item)) }, "Accept / assign"),
                react_1.default.createElement("button", { onClick: () => p.action('intake.accept', { ...(0, utils_1.commandDefaults)(item), create_title: item.original_name.replace(/\.[^.]+$/, '') }) }, "Create asset"),
                react_1.default.createElement("button", { onClick: () => p.action('intake.discard', (0, utils_1.commandDefaults)(item)) }, "Discard\u2026")),
            react_1.default.createElement("button", { onClick: () => p.action('media.tags', (0, utils_1.commandDefaults)(m)) }, "Tag image"))); })),
    !items.length && react_1.default.createElement(Primitives_1.Empty, { title: filter === 'pending' ? 'Intake is clear' : 'No matching intake items' }, "Import individual files or a folder. Exact hash duplicates share one stored file and remain separately reviewable.")); }
exports.IntakePage = IntakePage;
function LibraryPage(p) { const [query, setQuery] = (0, react_1.useState)(''), [type, setType] = (0, react_1.useState)(''), [tag, setTag] = (0, react_1.useState)(''), [page, setPage] = (0, react_1.useState)(0); const records = (0, utils_1.activeEntities)(p.state, 'asset').filter(e => (!type || e.fields.type === type) && (!tag || e.tags.includes(tag)) && [e.title, e.description, ...e.aliases].join(' ').toLowerCase().includes(query.toLowerCase())); const visible = records.slice(page * 48, (page + 1) * 48); (0, react_1.useEffect)(() => setPage(0), [query, type, tag]); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Asset library", title: "The people, places, and things.", description: "One asset can hold many images. Shot assignments preserve the exact reference you choose.", actions: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("button", { onClick: () => p.go('intake') }, "Import references"),
            react_1.default.createElement("button", { className: "primary", onClick: () => p.action('asset.create') },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New asset")) }),
    react_1.default.createElement("div", { className: "list-toolbar" },
        react_1.default.createElement("label", { className: "search" },
            react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
            react_1.default.createElement("input", { "aria-label": "Search assets", value: query, onChange: (e) => setQuery(e.target.value), placeholder: "Search names, aliases, descriptions\u2026" })),
        react_1.default.createElement("select", { "aria-label": "Filter asset type", value: type, onChange: (e) => setType(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "All types"),
            ['character', 'location', 'prop', 'reference'].map(t => react_1.default.createElement("option", { key: t }, t))),
        react_1.default.createElement("select", { "aria-label": "Filter asset tag", value: tag, onChange: (e) => setTag(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "All tags"),
            [...new Set(p.state.entities.flatMap(e => e.tags))].sort().map(t => react_1.default.createElement("option", { key: t }, t))),
        react_1.default.createElement("span", { className: "muted" },
            records.length,
            " assets")),
    react_1.default.createElement("div", { className: "asset-grid" }, visible.map(a => { const members = p.state.asset_media.filter(m => m.asset_id === a.id), primary = members.find(m => m.is_primary) || members[0]; return react_1.default.createElement("article", { className: `asset-card ${p.selected === a.id ? 'is-selected' : ''}`, key: a.id },
        react_1.default.createElement("button", { className: "asset-preview", onClick: () => p.select(a.id), "aria-label": `Inspect ${a.title}` }, primary ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, primary.media_id), alt: a.title, loading: "lazy" }) : react_1.default.createElement("span", { className: "media-placeholder" },
            react_1.default.createElement(Primitives_1.Icon, { name: "library", size: 32 }),
            "No reference image")),
        react_1.default.createElement("div", { className: "asset-meta" },
            react_1.default.createElement(Primitives_1.Badge, { kind: (0, utils_1.kindLabel)(a) }, (0, utils_1.kindLabel)(a)),
            react_1.default.createElement("small", null,
                members.length,
                " images")),
        react_1.default.createElement("button", { className: "title-button", onClick: () => p.select(a.id) }, a.title),
        react_1.default.createElement("p", null, a.description || 'No description yet.'),
        react_1.default.createElement("div", { className: "tags" }, a.tags.slice(0, 5).map(t => react_1.default.createElement("span", { className: "tag", key: t }, t))),
        react_1.default.createElement("div", { className: "button-row" },
            react_1.default.createElement("button", { onClick: () => p.action('asset.update', (0, utils_1.commandDefaults)(a)) }, "Edit"),
            react_1.default.createElement("button", { onClick: () => p.action('asset.attach', { asset_id: a.id }) }, "Attach image"))); })),
    !records.length && react_1.default.createElement(Primitives_1.Empty, { title: "A reference library, not a loose folder", action: react_1.default.createElement("button", { onClick: () => p.action('asset.create') }, "Create an asset") }, "Start with a character, location, prop, or general reference. Import an image when you have one."),
    records.length > 48 && react_1.default.createElement("div", { className: "pagination" },
        react_1.default.createElement("button", { disabled: page === 0, onClick: () => setPage(page - 1) }, "Previous"),
        react_1.default.createElement("span", null,
            "Page ",
            page + 1,
            " of ",
            Math.ceil(records.length / 48)),
        react_1.default.createElement("button", { disabled: (page + 1) * 48 >= records.length, onClick: () => setPage(page + 1) }, "Next"))); }
exports.LibraryPage = LibraryPage;
var OutlinePage_1 = require("./OutlinePage");
Object.defineProperty(exports, "OutlinePage", { enumerable: true, get: function () { return OutlinePage_1.OutlinePage; } });
function ScopeSelect({ state, value, onChange, label = 'Story scope', shotsOnly = false }) { const choices = (0, utils_1.activeEntities)(state).filter(e => shotsOnly ? e.kind === 'shot' : e.kind !== 'asset').sort((a, b) => a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title)); return react_1.default.createElement("label", { className: "field scope-select" },
    react_1.default.createElement("span", null, label),
    react_1.default.createElement("select", { "aria-label": label, value: value, onChange: (e) => onChange(e.target.value) },
        !choices.some(e => e.id === value) && react_1.default.createElement("option", { value: "" }, "Choose\u2026"),
        choices.map(e => react_1.default.createElement("option", { key: e.id, value: e.id },
            (0, utils_1.human)(e.kind),
            " \u00B7 ",
            e.title)))); }
exports.ScopeSelect = ScopeSelect;
function GuidePage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind !== 'asset' ? p.selected : p.state.project.id), [context, setContext] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''); const record = p.state.entities.find(e => e.id === scope) || p.state.project; (0, react_1.useEffect)(() => { let alive = true; (0, api_1.runCommand)(p.state.project.id, 'context.resolve', { owner_id: scope }).then(r => alive && setContext(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [scope, p.state]); const blocks = p.state.context_blocks.filter(b => b.owner_id === scope); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Story guide", title: "Direction, with a clear source.", description: "Project \u2192 sequence \u2192 scene \u2192 shot. Scalar defaults inherit; named direction blocks append, replace, or explicitly exclude.", actions: react_1.default.createElement("button", { onClick: () => p.action(record.kind + '.update', (0, utils_1.commandDefaults)(record)) },
            "Edit ",
            record.kind,
            " direction") }),
    react_1.default.createElement(ScopeSelect, { state: p.state, value: scope, onChange: setScope }),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    react_1.default.createElement("div", { className: "guide-columns" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Authored at this scope"),
                react_1.default.createElement("button", { onClick: () => p.action('context.put', { owner_id: scope }) }, "Add direction block")),
            Object.entries(record.fields).filter(([k, v]) => v !== '' && v != null).map(([key, value]) => react_1.default.createElement("section", { className: "detail-field", key: key },
                react_1.default.createElement("h3", null, (0, utils_1.human)(key)),
                react_1.default.createElement("p", { className: "prose" }, key === 'location_id' ? p.state.entities.find(e => e.id === value)?.title : String(value)))),
            blocks.map(b => react_1.default.createElement("section", { className: "authored-block", key: b.id },
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h3", null, b.key),
                    react_1.default.createElement(Primitives_1.Badge, null, b.operation)),
                react_1.default.createElement("p", { className: "prose" }, b.text || 'This block is explicitly excluded.'),
                react_1.default.createElement("div", { className: "button-row" },
                    react_1.default.createElement("button", { onClick: () => p.action('context.put', (0, utils_1.commandDefaults)(b)) }, "Edit rule"),
                    react_1.default.createElement("button", { onClick: () => p.action('context.remove', (0, utils_1.commandDefaults)(b)) }, "Remove\u2026")))),
            !blocks.length && react_1.default.createElement("p", { className: "muted" }, "No named blocks authored here. Inherited direction is shown alongside.")),
        react_1.default.createElement("section", { className: "resolved-panel" },
            react_1.default.createElement("h2", null, "Resolved direction"),
            context ? react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement(Primitives_1.ContextView, { value: context }),
                Object.keys(context.blocks).length > 0 && react_1.default.createElement("div", { className: "optout-list" },
                    react_1.default.createElement("h3", null, "Override inherited direction"),
                    Object.keys(context.blocks).filter(key => !blocks.some(b => b.key === key)).map(key => react_1.default.createElement("button", { key: key, onClick: () => p.action('context.put', { owner_id: scope, key, operation: 'exclude', content: '' }) },
                        "Exclude \u201C",
                        (0, utils_1.human)(key),
                        "\u201D here\u2026")))) : react_1.default.createElement("p", null, "Resolving\u2026")))); }
exports.GuidePage = GuidePage;
function EditorPage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && ['scene', 'shot'].includes(p.state.entities.find(e => e.id === p.selected)?.kind || '') ? p.selected : (0, utils_1.activeEntities)(p.state, 'shot')[0]?.id || (0, utils_1.activeEntities)(p.state, 'scene')[0]?.id || ''); const record = p.state.entities.find(e => e.id === scope); const [composition, setComposition] = (0, react_1.useState)(null); (0, react_1.useEffect)(() => { if (scope)
    (0, api_1.runCommand)(p.state.project.id, 'composition.preview', { owner_id: scope }).then(setComposition).catch(() => setComposition(null)); }, [scope, p.state]); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Scene & shot editor", title: "Make the shot specific.", description: "Keep action, dialogue, camera direction, continuity, and exact source images separate and deliberate.", actions: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("button", { onClick: () => p.action('scene.create') }, "New scene"),
            react_1.default.createElement("button", { onClick: () => p.action('shot.create') }, "New shot")) }),
    react_1.default.createElement("label", { className: "field scope-select" },
        react_1.default.createElement("span", null, "Scene or shot"),
        react_1.default.createElement("select", { value: scope, onChange: (e) => setScope(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "Choose a record"),
            (0, utils_1.activeEntities)(p.state).filter(e => ['scene', 'shot'].includes(e.kind)).map(e => react_1.default.createElement("option", { key: e.id, value: e.id },
                (0, utils_1.human)(e.kind),
                " \u00B7 ",
                e.title)))),
    record ? react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement("div", { className: "editor-document" },
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("div", null,
                    react_1.default.createElement(Primitives_1.Badge, null, record.kind),
                    react_1.default.createElement("h2", null, record.title)),
                react_1.default.createElement("button", { className: "primary", onClick: () => p.action(record.kind + '.update', (0, utils_1.commandDefaults)(record)) }, "Edit authored fields")),
            react_1.default.createElement("p", { className: "prose" }, record.description),
            react_1.default.createElement("div", { className: "authored-fields" }, Object.entries(record.fields).map(([key, value]) => react_1.default.createElement("section", { key: key },
                react_1.default.createElement("h3", null, (0, utils_1.human)(key)),
                react_1.default.createElement("p", { className: `prose ${value == null || value === '' ? 'muted' : ''}` }, value == null || value === '' ? 'Not authored / inherit' : key === 'location_id' ? p.state.entities.find(e => e.id === value)?.title : String(value))))),
            record.kind === 'shot' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h2", null, "Exact references"),
                    react_1.default.createElement("button", { onClick: () => p.action('assignment.create', { shot_id: record.id }) }, "Assign reference")),
                react_1.default.createElement("div", { className: "reference-grid" }, p.state.assignments.filter(a => a.shot_id === record.id).map(a => react_1.default.createElement("article", { key: a.id },
                    a.media_id ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, a.media_id), alt: `Exact ${a.role} reference` }) : react_1.default.createElement("div", { className: "media-placeholder" }, "No exact image selected"),
                    react_1.default.createElement("h3", null, p.state.entities.find(e => e.id === a.asset_id)?.title),
                    react_1.default.createElement(Primitives_1.Badge, null, a.role),
                    react_1.default.createElement("p", null, a.media_id ? p.state.media.find(m => m.id === a.media_id)?.original_name : 'Semantic link only. No silent primary-image substitution.'),
                    react_1.default.createElement("div", { className: "button-row" },
                        react_1.default.createElement("button", { onClick: () => p.action('assignment.update', { ...(0, utils_1.commandDefaults)(a), asset_id: a.asset_id }) }, "Change selection"),
                        react_1.default.createElement("button", { onClick: () => p.action('assignment.remove', (0, utils_1.commandDefaults)(a)) }, "Remove\u2026"))))))),
        composition && react_1.default.createElement("details", { className: "context-preview" },
            react_1.default.createElement("summary", null, "Resolved direction and validation"),
            react_1.default.createElement(Primitives_1.ContextView, { value: composition.context }),
            react_1.default.createElement(Primitives_1.Validation, { issues: composition.validation }))) : react_1.default.createElement(Primitives_1.Empty, { title: "Select a scene or shot" }, "Create a sequence in the outline first, then build its scenes and shots.")); }
exports.EditorPage = EditorPage;
function FramesPage(p) { const [shot, setShot] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind === 'shot' ? p.selected : (0, utils_1.activeEntities)(p.state, 'shot')[0]?.id || ''), [compare, setCompare] = (0, react_1.useState)([]), [archived, setArchived] = (0, react_1.useState)(false); (0, react_1.useEffect)(() => { setCompare([]); }, [shot]); const frames = p.state.frames.filter(f => f.shot_id === shot && (archived || f.state !== 'archived')).sort((a, b) => b.version - a.version); const visible = compare.length >= 2 ? frames.filter(f => compare.includes(f.id)) : frames; return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Storyboard frames", title: "A candidate is not a reference.", description: "Attach panel images made in an external art tool. Compare versions and explicitly select or approve the preferred frame.", actions: shot ? react_1.default.createElement("button", { onClick: () => p.action('frame.attach', { shot_id: shot }) }, "Use managed image as candidate") : undefined }),
    react_1.default.createElement(ScopeSelect, { state: p.state, value: shot, onChange: setShot, label: "Shot", shotsOnly: true }),
    shot ? react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(UploadControl, { project: p.state.project.id, shot: shot, done: p.refresh }),
        react_1.default.createElement("div", { className: "list-toolbar" },
            react_1.default.createElement("label", { className: "inline-check" },
                react_1.default.createElement("input", { type: "checkbox", checked: archived, onChange: (e) => setArchived(e.target.checked) }),
                "Include archived candidates"),
            compare.length > 0 && react_1.default.createElement("button", { onClick: () => setCompare([]) },
                "Clear comparison (",
                compare.length,
                ")"),
            react_1.default.createElement("small", null, "Choose two or more \u201CCompare\u201D checkboxes for a side-by-side review.")),
        react_1.default.createElement("div", { className: `frames-grid ${compare.length ? 'comparison' : ''}` }, visible.map(f => react_1.default.createElement("article", { className: `frame-card ${f.state}`, key: f.id },
            react_1.default.createElement("a", { href: (0, api_1.originalUrl)(p.state.project.id, f.media_id), target: "_blank", rel: "noreferrer" },
                react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, f.media_id, 960), alt: `Storyboard frame version ${f.version}` })),
            react_1.default.createElement("div", { className: "frame-caption" },
                react_1.default.createElement("h3", null,
                    "Version ",
                    f.version),
                react_1.default.createElement(Primitives_1.Badge, { kind: f.state }, f.state)),
            react_1.default.createElement("p", { className: "prose" }, f.notes || 'No candidate notes.'),
            react_1.default.createElement("small", null, p.state.media.find(m => m.id === f.media_id)?.original_name),
            react_1.default.createElement("div", { className: "button-row" }, ['draft', 'selected', 'approved', 'archived'].filter(s => s !== f.state).map(status => react_1.default.createElement("button", { key: status, onClick: () => p.action('frame.state', { id: f.id, revision: f.revision, state: status }) }, status === 'selected' ? 'Select' : status === 'approved' ? 'Approve' : status === 'archived' ? 'Archive…' : 'Return to draft'))),
            react_1.default.createElement("label", { className: "inline-check" },
                react_1.default.createElement("input", { type: "checkbox", checked: compare.includes(f.id), onChange: () => setCompare(v => v.includes(f.id) ? v.filter(id => id !== f.id) : [...v, f.id]) }),
                "Compare v",
                f.version),
            Object.keys(f.provenance || {}).length > 0 && react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Candidate provenance"),
                react_1.default.createElement("pre", null, JSON.stringify(f.provenance, null, 2)))))),
        !frames.length && react_1.default.createElement(Primitives_1.Empty, { title: "No frame candidates yet" }, "Attach an image for this shot. Imported source references remain separate from frame revisions.")) : react_1.default.createElement(Primitives_1.Empty, { title: "A frame belongs to a shot" }, "Create a shot in the outline before attaching a storyboard candidate.")); }
exports.FramesPage = FramesPage;
function CompositionPage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind !== 'asset' ? p.selected : (0, utils_1.activeEntities)(p.state, 'scene')[0]?.id || p.state.project.id), [document, setDocument] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false), [approved, setApproved] = (0, react_1.useState)(false); (0, react_1.useEffect)(() => { let alive = true; setError(''); (0, api_1.runCommand)(p.state.project.id, 'composition.preview', { owner_id: scope }).then(r => alive && setDocument(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [scope, p.state]); async function exportTo(format) { setBusy(true); try {
    const r = await (0, api_1.runCommand)(p.state.project.id, format === 'bundle' ? 'export.bundle' : 'export.board', { owner_id: scope, ...(format === 'bundle' ? { include_media: true } : { format, approved_only: approved }) });
    p.setResult(r);
    p.notify('Self-contained export written.');
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Composition & delivery", title: "From working material to a board.", description: "Review the inherited direction, chosen references, and frame candidates before writing a portable package." }),
    react_1.default.createElement("div", { className: "composition-toolbar" },
        react_1.default.createElement(ScopeSelect, { state: p.state, value: scope, onChange: setScope }),
        react_1.default.createElement("label", { className: "inline-check" },
            react_1.default.createElement("input", { type: "checkbox", checked: approved, onChange: (e) => setApproved(e.target.checked) }),
            "Use only approved storyboard frames"),
        react_1.default.createElement("div", { className: "button-row" },
            react_1.default.createElement("button", { className: "primary", disabled: busy || !document?.valid, onClick: () => exportTo('bundle') }, "Export scene bundle"),
            react_1.default.createElement("button", { disabled: busy || !document?.valid, onClick: () => exportTo('all') }, "Export HTML + PDF + PNG")),
        busy && react_1.default.createElement("p", { role: "status" }, "Writing and checking export files\u2026")),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    " ",
    p.result && react_1.default.createElement(Primitives_1.ExportLinks, { project: p.state.project.id, result: p.result }),
    " ",
    document && react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(Primitives_1.Validation, { issues: document.validation }),
        react_1.default.createElement("details", { className: "context-preview" },
            react_1.default.createElement("summary", null, "Resolved scope direction and provenance"),
            react_1.default.createElement(Primitives_1.ContextView, { value: document.context })),
        react_1.default.createElement("div", { className: "presentation-board" },
            react_1.default.createElement("header", null,
                react_1.default.createElement("span", { className: "eyebrow" },
                    "Storyboard / ",
                    p.state.project.title),
                react_1.default.createElement("h2", null, document.owner.title),
                react_1.default.createElement("p", null,
                    document.scenes.reduce((n, s) => n + s.shots.length, 0),
                    " shots \u00B7 references and frames labelled separately")),
            document.scenes.map(scene => react_1.default.createElement("section", { key: scene.id, className: "board-scene" },
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h3", null,
                        scene.sequence.title,
                        " / ",
                        scene.title),
                    react_1.default.createElement("button", { onClick: () => p.select(scene.id) }, "Inspect scene")),
                react_1.default.createElement("div", { className: "board-panels" }, scene.shots.map(shot => { const preferred = shot.frames.find(f => f.state === 'approved') || (!approved ? shot.frames.find(f => f.state === 'selected') : null); const image = preferred?.media_id || shot.assignments.find(a => a.media_id)?.media_id; return react_1.default.createElement("article", { className: "board-panel", key: shot.id },
                    react_1.default.createElement("div", { className: "board-image" },
                        image ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, image, 960), alt: `${shot.title}: ${preferred ? 'storyboard frame' : 'source reference'}` }) : react_1.default.createElement("span", null, "No panel image selected"),
                        react_1.default.createElement("span", null, preferred ? `${preferred.state} frame · v${preferred.version}` : image ? 'Reference image — not a storyboard frame' : 'No image')),
                    react_1.default.createElement("div", { className: "board-shot-title" },
                        react_1.default.createElement("span", null, shot.fields.number || String(shot.position + 1).padStart(2, '0')),
                        react_1.default.createElement("h4", null, shot.title)),
                    react_1.default.createElement("p", { className: "board-framing" },
                        shot.context.scalars.framing?.value || 'Framing not set',
                        shot.fields.duration != null ? ` · ${shot.fields.duration}s` : ''),
                    react_1.default.createElement("p", { className: "prose" }, shot.fields.action || 'Action not yet authored.'),
                    shot.fields.dialogue && react_1.default.createElement("blockquote", null, shot.fields.dialogue),
                    shot.fields.camera && react_1.default.createElement("p", null,
                        react_1.default.createElement("strong", null, "Camera"),
                        " \u00B7 ",
                        shot.fields.camera),
                    react_1.default.createElement("div", { className: "board-reference-strip" }, shot.assignments.filter(a => a.media_id).map(a => react_1.default.createElement("a", { key: a.id, href: (0, api_1.originalUrl)(p.state.project.id, a.media_id), target: "_blank", rel: "noreferrer" },
                        react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, a.media_id, 160), alt: `${a.asset?.title}: exact ${a.role} reference` }),
                        react_1.default.createElement("small", null, a.role)))),
                    react_1.default.createElement("div", { className: "button-row" },
                        react_1.default.createElement("button", { onClick: () => p.action('shot.update', (0, utils_1.commandDefaults)(shot)) }, "Edit shot"),
                        react_1.default.createElement("button", { onClick: () => p.action('context.resolve', { owner_id: shot.id }) }, "Direction provenance"))); })),
                !scene.shots.length && react_1.default.createElement("p", { className: "muted" }, "No shots in this scene yet."))),
            !document.scenes.length && react_1.default.createElement(Primitives_1.Empty, { title: "No scenes to compose" }, "Build a sequence, scene, and shot in the story outline.")))); }
exports.CompositionPage = CompositionPage;
function SettingsPage(p) { const [health, setHealth] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false), [backup, setBackup] = (0, react_1.useState)(null), [restoreSlug, setRestoreSlug] = (0, react_1.useState)('restored-project'), [restoreFile, setRestoreFile] = (0, react_1.useState)(null), [confirmed, setConfirmed] = (0, react_1.useState)(false); async function check(hashes = false) { setBusy(true); try {
    setHealth(await (0, api_1.runCommand)(p.state.project.id, 'project.doctor', { hashes }));
    setError('');
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } (0, react_1.useEffect)(() => { check(false); }, [p.state.project.id]); async function makeBackup() { setBusy(true); try {
    setBackup(await (0, api_1.runCommand)(p.state.project.id, 'project.backup'));
    p.notify('Consistent database and media backup written.');
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } async function restore(e) { e.preventDefault(); if (!restoreFile)
    return; setBusy(true); try {
    const form = new FormData();
    form.append('file', restoreFile);
    form.append('slug', restoreSlug);
    const r = await (0, api_1.api)('/restore', 'POST', form);
    p.notify(`Backup restored to ${r.path || restoreSlug}. Open it from the workspace dashboard.`);
    await p.refresh();
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Project settings & health", title: "Keep the work dependable.", description: "Check integrity, rebuild derived previews, and make complete portable backups.", actions: react_1.default.createElement("button", { onClick: () => p.action('project.update', (0, utils_1.commandDefaults)(p.state.project)) }, "Edit project settings") }),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    react_1.default.createElement("div", { className: "settings-grid" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Project paths"),
            react_1.default.createElement("dl", { className: "key-values" },
                react_1.default.createElement("dt", null, "Project root"),
                react_1.default.createElement("dd", null,
                    react_1.default.createElement("code", null, p.state.project.path)),
                react_1.default.createElement("dt", null, "Database"),
                react_1.default.createElement("dd", null,
                    react_1.default.createElement("code", null, ".storyboarder/storyboard.sqlite3")),
                react_1.default.createElement("dt", null, "Project / API version"),
                react_1.default.createElement("dd", null, "1 / v1"),
                react_1.default.createElement("dt", null, "Database schema"),
                react_1.default.createElement("dd", null, p.session.schema_version),
                react_1.default.createElement("dt", null, "Media"),
                react_1.default.createElement("dd", null, "Project-relative managed files, referenced by immutable ID."),
                react_1.default.createElement("dt", null, "Concurrency"),
                react_1.default.createElement("dd", null, "WAL + short transactions + explicit record revisions.")),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Integrity report"),
                react_1.default.createElement("div", { className: "button-row" },
                    react_1.default.createElement("button", { disabled: busy, onClick: () => check(false) }, "Check paths"),
                    react_1.default.createElement("button", { disabled: busy, onClick: () => check(true) }, "Verify every hash"))),
            health && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("p", { className: health.healthy ? 'success-line' : 'warning-text' },
                    health.healthy ? '✓ Healthy' : '! Attention needed',
                    " \u00B7 ",
                    health.media_checked,
                    " media files checked"),
                react_1.default.createElement(Primitives_1.Validation, { issues: health.issues }),
                react_1.default.createElement("details", null,
                    react_1.default.createElement("summary", null, "Migration history"),
                    react_1.default.createElement("pre", null, JSON.stringify(health.migrations, null, 2)))),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Rebuildable cache")),
            react_1.default.createElement("p", null, "Thumbnails are derived from original media. Clearing this cache never removes source images or frames."),
            react_1.default.createElement("div", { className: "button-row" },
                react_1.default.createElement("button", { onClick: () => p.action('cache.rebuild') }, "Rebuild thumbnails"),
                react_1.default.createElement("button", { onClick: () => p.action('cache.clear') }, "Clear thumbnails"))),
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Back up the whole project"),
            react_1.default.createElement("p", null, "A backup includes a consistent SQLite snapshot, manifest, original media, and job provenance. Cache and existing exports can be recreated."),
            react_1.default.createElement("button", { className: "primary", disabled: busy, onClick: makeBackup }, "Create full backup"),
            backup && react_1.default.createElement("div", { className: "notice" },
                react_1.default.createElement("p", null, "Backup created."),
                react_1.default.createElement("pre", null, JSON.stringify(backup, null, 2)),
                (backup.path || backup.archive) && react_1.default.createElement("a", { className: "button", href: (0, api_1.exportUrl)(p.state.project.id, backup.path || backup.archive, true) }, "Download backup")),
            react_1.default.createElement("h2", null, "Restore into a new folder"),
            p.session.can_create ? react_1.default.createElement("form", { className: "form-stack", onSubmit: restore },
                react_1.default.createElement("p", null, "The original project is never overwritten. The backup is validated before the restored folder becomes available."),
                react_1.default.createElement("label", { className: "field" },
                    react_1.default.createElement("span", null, "Backup ZIP (up to 1 GiB)"),
                    react_1.default.createElement("input", { type: "file", accept: ".zip", required: true, onChange: (e) => setRestoreFile(e.target.files?.[0] || null) })),
                react_1.default.createElement("label", { className: "field" },
                    react_1.default.createElement("span", null, "New folder name"),
                    react_1.default.createElement("input", { required: true, pattern: "[a-z0-9]+(?:-[a-z0-9]+)*", value: restoreSlug, onChange: (e) => setRestoreSlug(e.target.value) })),
                react_1.default.createElement("label", { className: "inline-check" },
                    react_1.default.createElement("input", { type: "checkbox", checked: confirmed, onChange: (e) => setConfirmed(e.target.checked), required: true }),
                    "Restore only into this new workspace folder."),
                react_1.default.createElement("button", { disabled: busy || !confirmed || !restoreFile }, "Validate and restore backup")) : react_1.default.createElement("p", null,
                "For a standalone project, use ",
                react_1.default.createElement("code", null, "storyboarder restore backup.zip /new/project/path"),
                ". The destination must not exist."),
            react_1.default.createElement("h2", null, "Archived records"),
            p.state.entities.filter(e => e.archived).map(e => react_1.default.createElement("div", { className: "archive-row", key: e.id },
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, e.title),
                    react_1.default.createElement("small", null,
                        (0, utils_1.kindLabel)(e),
                        " \u00B7 r",
                        e.revision)),
                react_1.default.createElement("button", { onClick: () => p.action('entity.restore', (0, utils_1.commandDefaults)(e)) }, "Restore record"),
                react_1.default.createElement("button", { onClick: () => p.select(e.id) }, "Inspect"))),
            !p.state.entities.some(e => e.archived) && react_1.default.createElement("p", { className: "muted" }, "No archived story records.")))); }
exports.SettingsPage = SettingsPage;
function AutomationPage(p) { const [selected, setSelected] = (0, react_1.useState)(null), [preview, setPreview] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''); (0, react_1.useEffect)(() => { let alive = true; if (selected)
    (0, api_1.api)((0, api_1.projectPath)(p.state.project.id, `/jobs/${selected}/preview`)).then(r => alive && setPreview(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [selected, p.state]); const job = selected ? p.state.jobs.find(j => j.id === selected) : null; return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "External script handoff", title: "An explicit, reviewable seam.", description: "Registered programs receive a versioned request, copied references, and resolved context. Outputs stay pending until you approve their import.", actions: react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.create'), disabled: !p.meta.scripts.length }, "Create output request") }),
    react_1.default.createElement("div", { className: "notice warning" },
        react_1.default.createElement("strong", null, "Trusted scripts only."),
        " Running a job is an explicit action. Scripts run with your operating-system permissions; the request protocol is not an OS sandbox. Projects cannot register or launch their own scripts."),
    react_1.default.createElement("section", null,
        react_1.default.createElement("h2", null, "Registered on this computer"),
        p.meta.scripts.length ? react_1.default.createElement("div", { className: "script-list" }, p.meta.scripts.map(s => react_1.default.createElement("div", { className: "script-row", key: s.name },
            react_1.default.createElement("strong", null, s.name),
            react_1.default.createElement("p", null, s.description || 'No script description.'),
            react_1.default.createElement("small", null,
                "Timeout ",
                s.timeout,
                "s \u00B7 ",
                s.env_keys.length,
                " explicitly allowed environment keys")))) : react_1.default.createElement("div", { className: "empty compact" },
            react_1.default.createElement("h3", null, "No external scripts registered"),
            react_1.default.createElement("p", null, "Register the included offline sample from your terminal. The core authoring tools do not require a provider or credentials."),
            react_1.default.createElement("code", null, "storyboarder script register sample --command '[\"/absolute/path/to/python\", \"/absolute/path/to/sample_adapter.py\"]'"))),
    react_1.default.createElement("div", { className: "automation-columns" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Requests and runs"),
            p.state.jobs.map(j => react_1.default.createElement("button", { key: j.id, className: `job-row ${j.id === selected ? 'is-selected' : ''}`, onClick: () => setSelected(j.id) },
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, j.title),
                    react_1.default.createElement("small", null,
                        j.script,
                        " \u00B7 ",
                        j.target,
                        " \u00B7 attempt ",
                        j.attempt)),
                react_1.default.createElement(Primitives_1.Badge, { kind: j.status }, j.approved ? 'Imported' : j.status === 'succeeded' ? 'Pending review' : j.status))),
            !p.state.jobs.length && react_1.default.createElement("p", { className: "muted" }, "No jobs yet. A request never launches itself.")),
        react_1.default.createElement("section", null, job && preview ? react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, job.title),
                react_1.default.createElement(Primitives_1.Badge, null, job.status)),
            react_1.default.createElement("div", { className: "button-row" },
                job.status === 'queued' && react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.run', (0, utils_1.commandDefaults)(job)) }, "Explicitly run script\u2026"),
                ['queued', 'running'].includes(job.status) && react_1.default.createElement("button", { onClick: () => p.action('job.cancel', (0, utils_1.commandDefaults)(job)) }, "Cancel\u2026"),
                ['failed', 'cancelled'].includes(job.status) && react_1.default.createElement("button", { onClick: () => p.action('job.retry', (0, utils_1.commandDefaults)(job)) }, "Queue explicit retry"),
                job.status === 'succeeded' && !job.approved && react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.approve', (0, utils_1.commandDefaults)(job)) }, "Approve and import outputs\u2026")),
            error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
            react_1.default.createElement("div", { className: "generated-output-grid" }, (preview.outputs || preview.result?.outputs || job.result?.outputs || []).map((o) => react_1.default.createElement("article", { key: o.key },
                react_1.default.createElement("img", { src: (0, api_1.jobImageUrl)(p.state.project.id, job.id, o.key), alt: `Pending external output ${o.key}` }),
                react_1.default.createElement("h3", null, o.title || o.key),
                react_1.default.createElement("p", null, o.notes),
                react_1.default.createElement("small", null,
                    o.width,
                    " \u00D7 ",
                    o.height,
                    " \u00B7 SHA-256 ",
                    o.sha256.slice(0, 12),
                    "\u2026")))),
            react_1.default.createElement("details", { open: true },
                react_1.default.createElement("summary", null, "Captured logs"),
                react_1.default.createElement("pre", null, typeof preview.logs === 'string' ? preview.logs : JSON.stringify(preview.logs || preview.log || {}, null, 2))),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Versioned request and context snapshot"),
                react_1.default.createElement("pre", null, JSON.stringify(job.request, null, 2))),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Output manifest and provenance"),
                react_1.default.createElement("pre", null, JSON.stringify(job.result, null, 2)))) : react_1.default.createElement(Primitives_1.Empty, { title: "Choose a request" }, "Review its exact inputs, status, output hashes, and captured logs before importing a result.")))); }
exports.AutomationPage = AutomationPage;

},
"react":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createRoot = exports.useRef = exports.useCallback = exports.useMemo = exports.useLayoutEffect = exports.useEffect = exports.useState = void 0;
const React = window.React;
exports.useState = React.useState;
exports.useEffect = React.useEffect;
exports.useLayoutEffect = React.useLayoutEffect;
exports.useMemo = React.useMemo;
exports.useCallback = React.useCallback;
exports.useRef = React.useRef;
exports.createRoot = window.ReactDOM.createRoot;
exports.default = React;

},
"types":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });

},
"utils":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.selectOptions = exports.commandDefaults = exports.allRecords = exports.activeEntities = exports.kindLabel = exports.niceDate = exports.fieldText = exports.shortId = exports.human = void 0;
const human = (value) => value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
exports.human = human;
const shortId = (id) => id.slice(0, 8);
exports.shortId = shortId;
const fieldText = (value) => value == null ? '' : String(value);
exports.fieldText = fieldText;
const niceDate = (value) => new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value));
exports.niceDate = niceDate;
const kindLabel = (e) => e.kind === 'asset' ? (0, exports.fieldText)(e.fields.type) : e.kind;
exports.kindLabel = kindLabel;
const activeEntities = (state, kind) => state.entities.filter(e => !e.archived && (!kind || e.kind === kind));
exports.activeEntities = activeEntities;
function allRecords(state) { return [...state.entities, ...state.media, ...state.intake, ...state.asset_media, ...state.links, ...state.assignments, ...state.context_blocks, ...state.frames, ...state.layouts, ...state.jobs]; }
exports.allRecords = allRecords;
function commandDefaults(entity) {
    if (!entity)
        return {};
    return { ...entity, ...(entity.fields || {}), id: entity.id, revision: entity.revision, ...(entity.kind && entity.kind !== 'asset' ? { owner_id: entity.id } : {}), ...(entity.kind === 'shot' ? { shot_id: entity.id } : {}), ...(entity.kind === 'asset' ? { asset_id: entity.id, source_id: entity.id } : {}), ...(entity.key ? { content: entity.text } : {}), tags: entity.tags || [], aliases: entity.aliases || [] };
}
exports.commandDefaults = commandDefaults;
function selectOptions(field, state, meta, values) {
    if (field.options.length)
        return field.options.map(o => ({ value: o, label: (0, exports.human)(o) }));
    const source = field.source;
    if (source === 'scripts')
        return meta.scripts.map(s => ({ value: s.name, label: s.name + (s.description ? ' — ' + s.description : '') }));
    const kinds = { assets: 'asset', sequences: 'sequence', scenes: 'scene', shots: 'shot', projects: 'project' };
    let records = [];
    const byId = Object.fromEntries(state.entities.map(e => [e.id, e]));
    if (kinds[source])
        records = (0, exports.activeEntities)(state, kinds[source]);
    else if (source === 'locations')
        records = (0, exports.activeEntities)(state, 'asset').filter(e => e.fields.type === 'location');
    else if (source === 'story' || source === 'parents')
        records = (0, exports.activeEntities)(state).filter(e => e.kind !== 'asset' && (source !== 'parents' || e.kind !== 'shot'));
    else
        records = state[source] || [];
    if (source === 'asset_images')
        records = state.media;
    if (source === 'asset_images' && values.asset_id) {
        const allowed = new Set(state.asset_media.filter(m => m.asset_id === values.asset_id).map(m => m.media_id));
        records = records.filter(r => allowed.has(r.id));
    }
    if (source === 'asset_media' && values.asset_id)
        records = records.filter(r => r.asset_id === values.asset_id);
    return records.map(r => {
        let label = r.title || r.original_name || r.name || r.key || (0, exports.shortId)(r.id);
        if (source === 'frames')
            label = `${byId[r.shot_id]?.title || 'Shot'} / v${r.version} · ${r.state}`;
        if (source === 'asset_media')
            label = `${byId[r.asset_id]?.title || 'Asset'} / ${state.media.find(m => m.id === r.media_id)?.original_name || (0, exports.shortId)(r.media_id)}${r.is_primary ? ' · primary' : ''}`;
        if (source === 'links')
            label = `${byId[r.source_id]?.title || '?'} → ${r.relation} → ${byId[r.target_id]?.title || '?'}`;
        if (source === 'assignments')
            label = `${byId[r.shot_id]?.title || '?'} → ${r.role} → ${byId[r.asset_id]?.title || '?'}`;
        if (source === 'intake')
            label = `${r.original_name} · ${r.state}${r.duplicate ? ' · duplicate' : ''}`;
        return { value: r.id, label: `${label} [${(0, exports.shortId)(r.id)}]` };
    });
}
exports.selectOptions = selectOptions;

}};
const cache={};function load(id){if(cache[id])return cache[id].exports;if(!modules[id])throw Error('Missing app module '+id);const m=cache[id]={exports:{}};function req(relative){const parts=id.split('/');parts.pop();for(const p of relative.split('/')){if(p==='.'||!p)continue;if(p==='..')parts.pop();else parts.push(p)}return load(parts.join('/').replace(/\.js$/,''));}modules[id](req,m,m.exports);return m.exports;}load('main');})();
