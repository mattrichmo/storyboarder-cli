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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.App = App;
const react_1 = __importStar(require("./react"));
const api_1 = require("./api");
const utils_1 = require("./utils");
const Primitives_1 = require("./components/Primitives");
const ActionDialog_1 = require("./components/ActionDialog");
const Inspector_1 = require("./components/Inspector");
const Canvas_1 = require("./canvas/Canvas");
const Pages_1 = require("./pages/Pages");
const NAV = [['overview', 'Project overview', 'home'], ['intake', 'Image intake', 'inbox'], ['library', 'Reference library', 'library'], ['outline', 'Story outline', 'outline'], ['guide', 'Story guide', 'guide'], ['editor', 'Scene & shot editor', 'edit'], ['canvas', 'Story canvas', 'graph'], ['frames', 'Storyboard frames', 'frames'], ['composition', 'Board & exports', 'export'], ['automation', 'Image tools', 'automation'], ['settings', 'Project care', 'settings']];
function App() {
    const [session, setSession] = (0, react_1.useState)(null), [meta, setMeta] = (0, react_1.useState)(null), [state, setState] = (0, react_1.useState)(null);
    const [page, setPage] = (0, react_1.useState)(location.hash.slice(1) || 'workspace'), [selected, setSelected] = (0, react_1.useState)(null), [loading, setLoading] = (0, react_1.useState)(true), [error, setError] = (0, react_1.useState)('');
    const [dialog, setDialog] = (0, react_1.useState)(null), [resultModal, setResultModal] = (0, react_1.useState)(null), [result, setResult] = (0, react_1.useState)(null), [palette, setPalette] = (0, react_1.useState)(false), [paletteQuery, setPaletteQuery] = (0, react_1.useState)(''), [toast, setToast] = (0, react_1.useState)(null), [mobileNav, setMobileNav] = (0, react_1.useState)(false), [changed, setChanged] = (0, react_1.useState)(false), [writeRefreshError, setWriteRefreshError] = (0, react_1.useState)(null);
    const canvasDrafts = (0, react_1.useRef)({});
    (0, react_1.useEffect)(() => { const before = (e) => { if (Object.values(canvasDrafts.current).some(draft => draft.dirty)) {
        e.preventDefault();
        e.returnValue = '';
    } }; window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before); }, []);
    const navRef = (0, react_1.useRef)(null), mobileNavOpener = (0, react_1.useRef)(null), mobileNavWasOpen = (0, react_1.useRef)(false);
    (0, react_1.useEffect)(() => { const media = window.matchMedia('(max-width:800px)'); const update = () => { if (navRef.current)
        navRef.current.inert = media.matches && !mobileNav; }; update(); media.addEventListener('change', update); return () => media.removeEventListener('change', update); }, [mobileNav]);
    (0, react_1.useEffect)(() => { if (mobileNav) {
        mobileNavWasOpen.current = true;
        const first = navRef.current?.querySelector('button:not(:disabled)');
        first?.focus();
        return;
    } if (mobileNavWasOpen.current) {
        mobileNavWasOpen.current = false;
        const opener = mobileNavOpener.current;
        mobileNavOpener.current = null;
        if (opener?.isConnected && !opener.matches(':disabled') && !opener.closest('[inert]') && opener.getClientRects().length > 0)
            opener.focus({ preventScroll: true });
    } }, [mobileNav]);
    const stateRef = (0, react_1.useRef)(null);
    stateRef.current = state;
    const dialogRef = (0, react_1.useRef)(dialog);
    dialogRef.current = dialog;
    const pageRef = (0, react_1.useRef)(page);
    pageRef.current = page;
    const canvasNavigationGuard = (0, react_1.useRef)(null);
    const registerCanvasNavigationGuard = (0, react_1.useCallback)((guard) => { canvasNavigationGuard.current = guard; return () => { if (canvasNavigationGuard.current === guard)
        canvasNavigationGuard.current = null; }; }, []);
    function notify(message, outcome = 'success') { setToast({ message, outcome }); }
    function commitNavigation(next) { if (next !== pageRef.current) {
        if (location.hash !== `#${next}`)
            location.hash = next;
        pageRef.current = next;
        setPage(next);
    } setMobileNav(false); }
    function go(next) { if (next === pageRef.current) {
        setMobileNav(false);
        return;
    } const commit = () => commitNavigation(next); const guard = canvasNavigationGuard.current; if (guard && !guard(commit)) {
        setMobileNav(false);
        return;
    } commit(); }
    async function load(id) { const next = await (0, api_1.api)((0, api_1.projectPath)(id, '/state')); setState(next); setChanged(false); return next; }
    async function refresh() { const id = stateRef.current?.project.id; if (!id)
        throw new Error('Open a project first.'); const next = await load(id); setWriteRefreshError(current => current?.projectId === id ? null : current); return next; }
    async function refreshSession() { const s = await (0, api_1.openSession)(); setSession(s); setMeta(await (0, api_1.api)('/meta')); }
    async function open(id) { setError(''); setLoading(true); try {
        await (0, api_1.api)('/active', 'POST', { id });
        const previousId = stateRef.current?.project.id;
        await load(id);
        if (previousId !== id)
            setWriteRefreshError(null);
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
    } })(); const h = () => { const next = location.hash.slice(1) || 'workspace'; if (next === pageRef.current)
        return; const previous = pageRef.current; const commit = () => commitNavigation(next); const guard = canvasNavigationGuard.current; if (guard && !guard(commit)) {
        history.replaceState(null, '', `${location.pathname}${location.search}${previous ? `#${previous}` : ''}`);
        return;
    } commit(); }; window.addEventListener('hashchange', h); return () => { alive = false; window.removeEventListener('hashchange', h); }; }, []);
    (0, react_1.useEffect)(() => { if (!toast)
        return; const timer = setTimeout(() => setToast(null), 6500); return () => clearTimeout(timer); }, [toast]);
    (0, react_1.useEffect)(() => { const keys = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette(v => !v);
    } if (e.key === 'Escape')
        setMobileNav(false); }; window.addEventListener('keydown', keys); return () => window.removeEventListener('keydown', keys); }, []);
    // A background read only marks stale UI. It never overwrites a modal's unsaved edits.
    (0, react_1.useEffect)(() => { let running = false; const check = async () => { const current = stateRef.current; if (!current || document.hidden || running)
        return; running = true; try {
        const next = await (0, api_1.api)((0, api_1.projectPath)(current.project.id, '/changes'));
        if (stateRef.current?.project.id !== current.project.id)
            return;
        if (next.event_id !== (current.events[0]?.id || 0))
            setChanged(true);
    }
    catch { }
    finally {
        running = false;
    } }; const timer = setInterval(check, 6500); window.addEventListener('focus', check); return () => { clearInterval(timer); window.removeEventListener('focus', check); }; }, []);
    function action(name, defaults = {}) { const command = meta?.commands.find(c => c.name === name); if (!command) {
        notify('That action is not available here.');
        return;
    } if (!state) {
        notify('Open a project first.');
        return;
    } setDialog({ command, defaults }); }
    async function done(data, name) { const command = meta?.commands.find(c => c.name === name), label = command?.label || 'Changes', projectId = stateRef.current?.project.id; const readOnly = !!command?.read_only, exportAction = name.startsWith('export.'), failed = data?.status === 'failed', cancelled = data?.status === 'cancelled', inProgress = ['queued', 'running'].includes(data?.status); const outcomeMessage = failed ? 'The image tool run needs attention.' : cancelled ? 'The image tool run was stopped.' : name === 'job.run' && inProgress ? 'The image tool is still running.' : name === 'job.run' && data?.status === 'succeeded' ? 'The image tool run finished.' : 'Your changes were saved.'; let refreshFailure = ''; if (!readOnly && !exportAction && projectId) {
        try {
            await refresh();
        }
        catch (e) {
            refreshFailure = e?.message || 'The project view could not be refreshed.';
            if (stateRef.current?.project.id === projectId)
                setWriteRefreshError({ projectId, message: refreshFailure, summary: outcomeMessage });
        }
    } if (exportAction) {
        setResult(data);
        setResultModal({ title: 'Export ready', data });
    }
    else if (readOnly) {
        setResultModal({ title: label || 'Project details', data });
    }
    else if (refreshFailure) {
        const outcome = failed ? 'failed' : cancelled ? 'cancelled' : name === 'job.run' && inProgress ? 'running' : 'success';
        notify(`${outcomeMessage} The project view could not refresh; use Retry project refresh.`, outcome);
    }
    else if (failed) {
        notify('The image tool needs attention. Review its run details.', 'failed');
    }
    else if (cancelled) {
        notify('The image tool run was stopped.', 'cancelled');
    }
    else if (name === 'job.run' && inProgress) {
        notify('The image tool is still running. You can review its status in Recent activity.', 'running');
    }
    else if (name === 'job.run' && data?.status === 'succeeded') {
        notify('The image tool run finished. Review its results.');
    }
    else {
        notify(`${label} saved to the project.`);
    } }
    async function retryWriteRefresh(warning) { if (stateRef.current?.project.id !== warning.projectId)
        return; try {
        await refresh();
    }
    catch (e) {
        if (stateRef.current?.project.id === warning.projectId)
            setWriteRefreshError({ ...warning, message: e?.message || 'The project view could not be refreshed.' });
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
                react_1.default.createElement("strong", { title: state?.project.title }, state ? (0, utils_1.displayTitle)(state.project.title) : 'No project open'),
                react_1.default.createElement("small", null, state ? 'Saved on this computer' : 'Create a project to begin')),
            react_1.default.createElement("nav", null, NAV.map(([key, label, icon]) => react_1.default.createElement("button", { key: key, "aria-label": label, className: page === key ? 'active' : '', disabled: loading || !state, onClick: () => go(key), "aria-current": page === key ? 'page' : undefined },
                react_1.default.createElement(Primitives_1.Icon, { name: icon }),
                react_1.default.createElement("span", null, label),
                key === 'intake' && state?.project.counts.intake ? react_1.default.createElement("span", { className: "nav-count" }, state.project.counts.intake) : null))),
            react_1.default.createElement("div", { className: "nav-bottom" },
                react_1.default.createElement("button", { "data-action-search": true, onClick: () => setPalette(true), disabled: !state },
                    react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                    "Search actions ",
                    react_1.default.createElement("kbd", null, "\u2318/Ctrl K")),
                react_1.default.createElement("p", null,
                    react_1.default.createElement("span", { className: "local-dot" }),
                    "On this computer \u00B7 v",
                    session?.version || '1.0.0'))),
        mobileNav && react_1.default.createElement("button", { className: "nav-scrim", onClick: () => setMobileNav(false), "aria-label": "Close navigation" }),
        react_1.default.createElement("div", { className: "app-column" },
            react_1.default.createElement("header", { className: "topbar" },
                react_1.default.createElement("button", { className: "mobile-menu icon-button", "aria-label": "Open navigation", onClick: (e) => { mobileNavOpener.current = e.currentTarget; setMobileNav(true); } },
                    react_1.default.createElement(Primitives_1.Icon, { name: "menu" })),
                react_1.default.createElement("div", { className: "breadcrumbs" },
                    react_1.default.createElement("button", { onClick: () => go('workspace') }, "Workspace"),
                    state && react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement("span", null, "/"),
                        react_1.default.createElement("button", { onClick: () => go('overview') }, (0, utils_1.displayTitle)(state.project.title))),
                    page !== 'workspace' && react_1.default.createElement(react_1.default.Fragment, null,
                        react_1.default.createElement("span", null, "/"),
                        react_1.default.createElement("strong", null, NAV.find(n => n[0] === page)?.[1] || 'Project overview'))),
                react_1.default.createElement("div", { className: "topbar-actions" },
                    state && react_1.default.createElement("button", { className: "text-button", onClick: () => refresh().then(() => notify('Project refreshed.')).catch(e => setError(e.message)) },
                        react_1.default.createElement(Primitives_1.Icon, { name: "refresh" }),
                        react_1.default.createElement("span", null, "Refresh")),
                    react_1.default.createElement("span", { className: "local-indicator" }, "On this computer"))),
            changed && react_1.default.createElement("div", { className: "external-change", role: "status" },
                "This project was updated in the terminal or another window. Your unsaved edits are safe. ",
                react_1.default.createElement("button", { onClick: () => refresh().catch(e => setError(e.message)) }, "Refresh project")),
            react_1.default.createElement("div", { className: `work-area ${selected && page !== 'workspace' ? 'with-inspector' : ''}` },
                react_1.default.createElement("main", { id: "main-content", tabIndex: -1, className: `main-content ${page === 'canvas' ? 'canvas-main' : ''}` },
                    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error },
                        react_1.default.createElement("button", { onClick: () => location.reload() }, "Try again")),
                    writeRefreshError && state && writeRefreshError.projectId === state.project.id && react_1.default.createElement("div", { className: "external-change", role: "status" },
                        writeRefreshError.summary,
                        " The project view could not refresh. ",
                        writeRefreshError.message,
                        react_1.default.createElement("button", { onClick: () => void retryWriteRefresh(writeRefreshError) }, "Retry project refresh")),
                    loading ? react_1.default.createElement("div", { className: "loading-state", role: "status" },
                        react_1.default.createElement(Primitives_1.Icon, { name: "grid", size: 30 }),
                        react_1.default.createElement("h2", null, "Opening your project\u2026")) : session && meta && (page === 'workspace' || !state) ? react_1.default.createElement(Pages_1.WorkspacePage, { session: session, projects: session.projects, onOpen: open, onRefresh: refreshSession }) : props && page === 'canvas' ? react_1.default.createElement(Canvas_1.Canvas, { key: props.state.project.id, draft: canvasDrafts.current[props.state.project.id], onDraftChange: draft => { canvasDrafts.current[props.state.project.id] = draft; }, state: props.state, selected: selected, onSelect: setSelected, action: action, refresh: refresh, notify: notify, registerNavigationGuard: registerCanvasNavigationGuard }) : props && Page ? react_1.default.createElement(Page, { ...props }) : props ? react_1.default.createElement(Pages_1.OverviewPage, { ...props }) : !error ? react_1.default.createElement(Primitives_1.Empty, { title: "Open a project" }, "Choose a project from Workspace or create a new one.") : null),
                state && selected && page !== 'workspace' && react_1.default.createElement(Inspector_1.Inspector, { state: state, id: selected, onClose: () => setSelected(null), onSelect: setSelected, action: action })),
            react_1.default.createElement("footer", { className: "app-footer" },
                page === 'canvas' && react_1.default.createElement("span", null, "Drag cards to arrange this view. The story sequence stays the same."),
                state && react_1.default.createElement("span", null,
                    state.media.length,
                    " reference images \u00B7 ",
                    state.frames.filter(f => f.state === 'approved').length,
                    " approved storyboard frames"))),
        toast && react_1.default.createElement("div", { className: "toast", role: "status", "data-outcome": toast.outcome },
            react_1.default.createElement(Primitives_1.Icon, { name: toast.outcome === 'cancelled' ? 'stop' : toast.outcome === 'failed' ? 'warning' : toast.outcome === 'running' ? 'refresh' : 'check' }),
            react_1.default.createElement("span", null, toast.message),
            react_1.default.createElement("button", { "aria-label": "Dismiss notification", onClick: () => setToast(null) },
                react_1.default.createElement(Primitives_1.Icon, { name: "close", size: 16 }))),
        dialog && state && meta && react_1.default.createElement(ActionDialog_1.ActionDialog, { key: dialog.command.name + JSON.stringify(dialog.defaults), command: dialog.command, defaults: dialog.defaults, state: state, meta: meta, onClose: () => setDialog(null), onDone: done, onReload: refresh }),
        resultModal && react_1.default.createElement(Primitives_1.Modal, { title: resultModal.title, onClose: () => setResultModal(null), wide: true },
            react_1.default.createElement("div", { className: "modal-body" }, resultModal.data?.archive && state ? react_1.default.createElement(Primitives_1.ExportLinks, { project: state.project.id, result: resultModal.data }) : resultModal.data?.chain ? react_1.default.createElement(Primitives_1.ContextView, { value: resultModal.data }) : resultModal.data?.can_delete !== undefined ? react_1.default.createElement("div", { className: "usage-summary" },
                react_1.default.createElement("p", null, resultModal.data.can_delete ? 'This item is not used elsewhere.' : 'This item is used in these places:'),
                react_1.default.createElement("ul", null, Object.entries(resultModal.data).filter(([key, value]) => key !== 'can_delete' && Array.isArray(value) && value.length > 0).map(([key, value]) => react_1.default.createElement("li", { key: key },
                    (0, utils_1.human)(key),
                    " \u00B7 ",
                    value.length)))) : react_1.default.createElement("div", { className: "muted" },
                react_1.default.createElement("p", null, "Open the related project page to review these details.")))),
        palette && meta && react_1.default.createElement(Primitives_1.Modal, { title: "Search actions", onClose: () => setPalette(false), wide: true },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("label", { className: "search" },
                    react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                    react_1.default.createElement("input", { autoFocus: true, placeholder: "Find an action\u2026", "aria-label": "Find an action", value: paletteQuery, onChange: (e) => setPaletteQuery(e.target.value) })),
                react_1.default.createElement("div", { className: "command-list" }, meta.commands.filter(c => !c.read_only && c.browser && !['entity.update', 'canvas.save', 'project.sync'].includes(c.name) && c.label.toLowerCase().includes(paletteQuery.toLowerCase())).map(c => react_1.default.createElement("button", { key: c.name, onClick: () => { setPalette(false); action(c.name); } },
                    react_1.default.createElement("span", null, c.label),
                    react_1.default.createElement("small", null, c.destructive ? 'Confirmation required' : '')))),
                !meta.commands.some(c => !c.read_only && c.browser && !['entity.update', 'canvas.save', 'project.sync'].includes(c.name) && c.label.toLowerCase().includes(paletteQuery.toLowerCase())) && react_1.default.createElement("p", { className: "muted" }, "No matching actions."))));
}

},
"api":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runCommand = exports.jobImageUrl = exports.exportUrl = exports.originalUrl = exports.mediaUrl = exports.projectPath = exports.ApiError = void 0;
exports.api = api;
exports.openSession = openSession;
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
async function api(path, method = 'GET', data, signal) {
    const headers = {};
    if (method !== 'GET')
        headers['X-Storyboarder-Token'] = launchToken;
    const multipart = data instanceof FormData;
    if (data !== undefined && !multipart)
        headers['Content-Type'] = 'application/json';
    let response;
    try {
        response = await fetch('/api/v1' + path, { method, headers, body: data === undefined ? undefined : multipart ? data : JSON.stringify(data), credentials: 'same-origin', signal });
    }
    catch (error) {
        if (error instanceof Error && error.name === 'AbortError')
            throw error;
        throw new ApiError('connection', 'Couldn’t reach Storyboarder on this computer. Check that the app is still running, then try again.');
    }
    let result;
    try {
        result = await response.json();
    }
    catch {
        throw new ApiError('connection', 'Storyboarder returned an unreadable response. Refresh the page and try again.', {}, response.status);
    }
    if (!response.ok) {
        const code = result.error?.code || 'request';
        const messages = { revision_conflict: 'This item changed elsewhere. Your edits are still here; refresh the project before saving again.', not_found: 'This item is no longer available. Refresh the project and try again.', unsafe_path: 'Choose a file inside the project folder.', in_use: 'This item is still connected to the story. Remove or change those connections first, or archive the item instead.', invalid_request: 'Some details need attention. Review the form and try again.', internal: 'Storyboarder couldn’t finish that action. Try again, then check Project care if the problem continues.' };
        throw new ApiError(code, messages[code] || result.error?.message || 'The request could not be completed.', result.error?.details, response.status);
    }
    return result;
}
async function openSession() { const session = await api('/session'); launchToken = session.token; return session; }
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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.Canvas = Canvas;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("../components/Primitives");
const geometry_1 = require("./geometry");
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function flatten(value, path = [], result = new Map()) {
    const isObject = value !== null && typeof value === 'object' && !Array.isArray(value);
    const entries = isObject ? Object.entries(value) : [];
    if (entries.length) {
        for (const [key, child] of entries)
            flatten(child, [...path, key], result);
    }
    else if (path.length)
        result.set(JSON.stringify(path), { path, value: { present: true, value: clone(value) } });
    return result;
}
function valueAt(fields, key) { return fields.get(key)?.value || { present: false }; }
function stableValue(value) { if (Array.isArray(value))
    return value.map(stableValue); if (value && typeof value === 'object')
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, stableValue(value[key])])); return value; }
function sameValue(a, b) { return a.present === b.present && (!a.present || JSON.stringify(stableValue(a.value)) === JSON.stringify(stableValue(b.value))); }
function writePath(target, path, entry) { let parent = target; for (const key of path.slice(0, -1)) {
    if (!parent[key] || typeof parent[key] !== 'object' || Array.isArray(parent[key]))
        parent[key] = {};
    parent = parent[key];
} const leaf = path[path.length - 1]; if (!entry.present)
    delete parent[leaf];
else
    parent[leaf] = clone(entry.value); }
function compareLayouts(base, local, saved) {
    const baseFields = flatten(base || {}), localFields = flatten(local), savedFields = flatten(saved), keys = new Set([...baseFields.keys(), ...localFields.keys(), ...savedFields.keys()]);
    const merged = clone(base || local), changes = [];
    for (const key of keys) {
        const path = (localFields.get(key) || savedFields.get(key) || baseFields.get(key)).path;
        const before = valueAt(baseFields, key), ours = valueAt(localFields, key), theirs = valueAt(savedFields, key);
        const localChanged = !sameValue(ours, before), savedChanged = !sameValue(theirs, before), conflict = base ? localChanged && savedChanged && !sameValue(ours, theirs) : !sameValue(ours, theirs);
        const selected = conflict ? ours : localChanged ? ours : theirs;
        writePath(merged, path, selected);
        if (!sameValue(ours, theirs) || localChanged || savedChanged) {
            changes.push({ key, path, base: before, local: ours, saved: theirs, conflict, label: path.join('.') });
        }
    }
    return { merged, changes };
}
function applyNewLocalEdits(reference, current, saved) { const before = flatten(reference), now = flatten(current), result = clone(saved); for (const key of new Set([...before.keys(), ...now.keys()])) {
    const old = valueAt(before, key), next = valueAt(now, key);
    if (!sameValue(old, next)) {
        const path = (now.get(key) || before.get(key)).path;
        writePath(result, path, next);
    }
} return result; }
function asLayoutDraft(layout) { return { name: layout.name, mode: layout.mode, positions: clone(layout.positions), settings: clone(layout.settings) }; }
function draftFromLayoutResult(layout) { return { id: layout.id, name: layout.name, mode: layout.mode, positions: clone(layout.positions), settings: clone(layout.settings), revision: layout.revision, updated_at: layout.updated_at }; }
function edgeLabel(edge) {
    if (edge.kind === 'relationship')
        return (0, utils_1.human)(edge.label);
    if (edge.kind === 'assignment') {
        const [role, selection] = edge.label.split(' · ');
        return `${(0, utils_1.roleLabel)(role)} · ${selection === 'specific image selected' ? 'Specific image selected' : 'No specific image selected'}`;
    }
    if (edge.kind === 'location_default')
        return 'Location';
    return edge.label;
}
function Canvas({ state, draft, onDraftChange, selected, onSelect, action, refresh, notify, registerNavigationGuard }) {
    const [newKind, setNewKind] = (0, react_1.useState)(draft?.mode === 'assets' ? 'asset' : draft?.mode === 'scene' ? 'shot' : 'sequence');
    const [mode, setMode] = (0, react_1.useState)(draft?.mode || 'story'), [scene, setScene] = (0, react_1.useState)(draft?.scene || ''), [sequence, setSequence] = (0, react_1.useState)(draft?.sequence || '');
    const [query, setQuery] = (0, react_1.useState)(draft?.query || ''), [assetType, setAssetType] = (0, react_1.useState)(draft?.assetType || ''), [tag, setTag] = (0, react_1.useState)(draft?.tag || ''), [relation, setRelation] = (0, react_1.useState)(draft?.relation || '');
    const [graph, setGraph] = (0, react_1.useState)({ nodes: [], edges: [], mode: 'story', total: 0, truncated: false });
    const [positions, setPositions] = (0, react_1.useState)(draft?.positions || {}), [view, setView] = (0, react_1.useState)(draft?.view || { x: 50, y: 50, scale: .7 });
    const [hidden, setHidden] = (0, react_1.useState)(draft?.hidden || []), [collapsed, setCollapsed] = (0, react_1.useState)(draft?.collapsed || []), [multi, setMulti] = (0, react_1.useState)([]);
    const [error, setError] = (0, react_1.useState)(draft?.error || ''), [loading, setLoading] = (0, react_1.useState)(false), [dirty, setDirty] = (0, react_1.useState)(draft?.dirty || false), [saving, setSaving] = (0, react_1.useState)(false), [layoutConflict, setLayoutConflict] = (0, react_1.useState)(draft?.layoutConflict || false), [layoutUnavailable, setLayoutUnavailable] = (0, react_1.useState)(draft?.layoutUnavailable || false), [conflictId, setConflictId] = (0, react_1.useState)(draft?.conflictId || null), [review, setReview] = (0, react_1.useState)(draft?.review || null), [refreshingConflict, setRefreshingConflict] = (0, react_1.useState)(false), [pendingNavigation, setPendingNavigation] = (0, react_1.useState)(null), [linkFrom, setLinkFrom] = (0, react_1.useState)(null);
    const [layoutName, setLayoutName] = (0, react_1.useState)(draft?.layoutName || 'Working arrangement'), [layoutRevision, setLayoutRevision] = (0, react_1.useState)(draft?.layoutRevision), [layoutId, setLayoutId] = (0, react_1.useState)(draft?.layoutId || '');
    const layoutNameRef = (0, react_1.useRef)(layoutName);
    layoutNameRef.current = layoutName;
    const [selectedEdge, setSelectedEdge] = (0, react_1.useState)(null), [deleteId, setDeleteId] = (0, react_1.useState)(null), [usage, setUsage] = (0, react_1.useState)(null), [usageLoading, setUsageLoading] = (0, react_1.useState)(false), [usageError, setUsageError] = (0, react_1.useState)('');
    const usageRequest = (0, react_1.useRef)(0), deleteTarget = (0, react_1.useRef)(null);
    const stage = (0, react_1.useRef)(null);
    const drag = (0, react_1.useRef)(null);
    const moved = (0, react_1.useRef)(false);
    const positionsRef = (0, react_1.useRef)(positions);
    positionsRef.current = positions;
    const layoutBaseline = (0, react_1.useRef)(draft?.baseline || null);
    const restoreView = (0, react_1.useRef)(!!draft);
    const currentDraft = { name: layoutName, mode, positions, settings: { hidden, collapsed, viewport: view, filters: { query, asset_type: assetType, tag, relation }, scene_id: scene, sequence_id: sequence } };
    const draftRef = (0, react_1.useRef)(currentDraft);
    draftRef.current = currentDraft;
    const dirtyRef = (0, react_1.useRef)(draft?.dirty || false), editVersion = (0, react_1.useRef)(draft?.editVersion || 0), savePromise = (0, react_1.useRef)(null);
    function markDirty() { editVersion.current += 1; dirtyRef.current = true; setDirty(true); }
    (0, react_1.useEffect)(() => registerNavigationGuard(commit => { if (!savePromise.current)
        return true; setPendingNavigation(() => commit); return false; }), [registerNavigationGuard]);
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
        const timer = setTimeout(() => { (0, api_1.api)((0, api_1.projectPath)(state.project.id, '/graph?' + params), 'GET', undefined, cancel.signal).then(next => { if (!active)
            return; setGraph(next); const base = (0, geometry_1.tidy)(next.nodes, next.edges, mode); const merged = { ...base, ...positionsRef.current }; setPositions(merged); const rect = stage.current?.getBoundingClientRect(); if (rect && query && !restoreView.current)
            setView((0, geometry_1.fit)(Object.fromEntries(next.nodes.map(n => [n.id, merged[n.id]])), rect.width, rect.height)); restoreView.current = false; }).catch(e => active && setError(e.message)).finally(() => active && setLoading(false)); }, query ? 150 : 0);
        return () => { active = false; cancel.abort(); clearTimeout(timer); };
    }, [state, mode, scene, sequence, query, assetType, tag, relation]);
    // Capture before the next navigation event; preserve the exact CAS baseline and conflict choices.
    function publishDraft(overrides = {}) { onDraftChange({ mode, scene, sequence, query, assetType, tag, relation, positions, view, hidden, collapsed, layoutName, layoutRevision, layoutId, dirty, baseline: layoutBaseline.current, layoutConflict, layoutUnavailable, conflictId, review, editVersion: editVersion.current, error, ...overrides }); }
    function snapshotFields(next) { const settings = next.settings, filters = settings.filters || {}; return { layoutName: next.name, mode: next.mode, positions: next.positions, hidden: settings.hidden || [], collapsed: settings.collapsed || [], view: settings.viewport || view, query: filters.query || '', assetType: filters.asset_type || '', tag: filters.tag || '', relation: filters.relation || '', scene: settings.scene_id || '', sequence: settings.sequence_id || '' }; }
    (0, react_1.useLayoutEffect)(() => { publishDraft(); }, [onDraftChange, mode, scene, sequence, query, assetType, tag, relation, positions, view, hidden, collapsed, layoutName, layoutRevision, layoutId, dirty, layoutConflict, layoutUnavailable, conflictId, review, error]);
    const suppressed = (0, react_1.useMemo)(() => new Set([...hidden, ...(0, geometry_1.descendants)(graph.nodes, collapsed)]), [hidden, collapsed, graph]);
    const visible = graph.nodes.filter(n => !suppressed.has(n.id)), visibleIds = new Set(visible.map(n => n.id));
    const edges = graph.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));
    const bounds = () => stage.current?.getBoundingClientRect();
    const fitView = () => { const rect = bounds(); if (rect) {
        setView((0, geometry_1.fit)(Object.fromEntries(visible.map(n => [n.id, positions[n.id] || { x: 0, y: 0 }])), rect.width, rect.height));
        markDirty();
    } };
    function restoreSaved(saved) { layoutBaseline.current = draftFromLayoutResult(saved); setLayoutId(saved.id); setLayoutName(saved.name); layoutNameRef.current = saved.name; setLayoutRevision(saved.revision); setLayoutConflict(false); setLayoutUnavailable(false); setConflictId(null); setReview(null); setPositions(saved.positions); setHidden(saved.settings.hidden || []); setCollapsed(saved.settings.collapsed || []); if (saved.settings.viewport)
        setView(saved.settings.viewport); setScene(saved.settings.scene_id || scene); setSequence(saved.settings.sequence_id || ''); const filters = saved.settings.filters || {}; setQuery(filters.query || ''); setAssetType(filters.asset_type || ''); setTag(filters.tag || ''); setRelation(filters.relation || ''); dirtyRef.current = false; setDirty(false); }
    function switchMode(next) { if (next === mode)
        return; const change = () => { setMode(next); setNewKind(next === 'assets' ? 'asset' : next === 'scene' ? 'shot' : 'sequence'); const sameName = state.layouts.find(layout => layout.mode === next && layout.name === layoutName); if (sameName)
        restoreSaved(sameName);
    else {
        layoutBaseline.current = null;
        setPositions({});
        setHidden([]);
        setCollapsed([]);
        setLayoutId('');
        setLayoutName('Working arrangement');
        layoutNameRef.current = 'Working arrangement';
        setLayoutRevision(undefined);
        setLayoutConflict(false);
        setLayoutUnavailable(false);
        setConflictId(null);
        setReview(null);
        dirtyRef.current = false;
        setDirty(false);
        setView({ x: 50, y: 50, scale: .65 });
    } setSelectedEdge(null); }; if (dirtyRef.current) {
        setPendingNavigation(() => change);
        return;
    } change(); }
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
                setError('Choose a different item to connect to.');
                return;
            }
            if (source.kind === 'asset' && node.kind === 'asset')
                action('link.create', { source_id: source.id, target_id: node.id });
            else if (source.kind === 'shot' && node.kind === 'asset')
                action('assignment.create', { shot_id: source.id, asset_id: node.id });
            else if ((source.kind === 'sequence' && node.kind === 'scene') || (source.kind === 'scene' && node.kind === 'shot'))
                action('story.move', { id: node.id, revision: node.revision, parent_id: source.id, position: 0 });
            else
                setError(`These items can’t be connected in that way. Connect library items to each other, add a reference to a shot, or place a scene or shot in the story.`);
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
    } markDirty(); }
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
    } markDirty(); }
    (0, react_1.useEffect)(() => { const el = stage.current; if (!el)
        return; el.addEventListener('wheel', wheel, { passive: false }); return () => el.removeEventListener('wheel', wheel); }, []);
    function key(e, node) { const target = e.target; if (target && target !== e.currentTarget && target.closest('button,a,input,select,textarea,[contenteditable="true"]'))
        return; if (e.key === 'Enter' || e.key === ' ' || e.code === 'Space') {
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
        markDirty();
    } }
    async function refreshUsage(id) { const request = ++usageRequest.current; deleteTarget.current = id; setUsage(null); setUsageError(''); setUsageLoading(true); try {
        const result = await (0, api_1.runCommand)(state.project.id, 'entity.usage', { id });
        if (request === usageRequest.current && deleteTarget.current === id)
            setUsage(result);
    }
    catch (e) {
        if (request === usageRequest.current && deleteTarget.current === id)
            setUsageError(e.message || 'Could not check where this item is used.');
    }
    finally {
        if (request === usageRequest.current && deleteTarget.current === id)
            setUsageLoading(false);
    } }
    function closeDelete() { usageRequest.current += 1; deleteTarget.current = null; setDeleteId(null); setUsage(null); setUsageError(''); setUsageLoading(false); }
    function requestDelete(id) { deleteTarget.current = id; setDeleteId(id); void refreshUsage(id); }
    async function refreshConflict() { setRefreshingConflict(true); try {
        const latestState = await refresh();
        const stableId = conflictId || layoutId;
        const latest = stableId ? latestState.layouts.find(item => item.id === stableId) : latestState.layouts.find(item => item.name === layoutName && item.mode === mode);
        if (!latest) {
            setReview(null);
            setLayoutUnavailable(true);
            setError('This saved arrangement is no longer available. Your local Canvas edits remain. Use Save as new to keep them under a new name.');
            return;
        }
        setLayoutUnavailable(false);
        const local = clone(draftRef.current);
        const base = layoutBaseline.current?.id === latest.id ? asLayoutDraft(layoutBaseline.current) : null;
        const compared = compareLayouts(base, local, asLayoutDraft(latest));
        setReview({ remote: draftFromLayoutResult(latest), local, merged: compared.merged, changes: compared.changes, choices: {}, editVersion: editVersion.current });
        setConflictId(latest.id);
        setError('Latest saved revision loaded. Compare the saved and local fields, choose each conflicting value, then reapply.');
    }
    catch (e) {
        setError(`Could not refresh the saved arrangement. Your local Canvas edits remain: ${e.message}`);
    }
    finally {
        setRefreshingConflict(false);
    } }
    function labelChange(path) { if (path[0] === 'positions') {
        const id = path[1], node = state.entities.find(item => item.id === id);
        return `Card ${node ? (0, utils_1.displayTitle)(node.title) : 'removed card'} (${id}) · ${path[2] === 'x' ? 'horizontal position (x)' : 'vertical position (y)'}`;
    } if (path[0] === 'settings')
        return `Canvas setting · ${path.slice(1).join(' · ')}`; if (path[0] === 'name')
        return 'Arrangement name'; if (path[0] === 'mode')
        return 'Canvas view'; return path.join(' · '); }
    function resolvedReviewDraft(active) { const next = clone(active.merged); for (const change of active.changes) {
        if (!change.conflict)
            continue;
        const choice = active.choices[change.key];
        if (choice)
            writePath(next, change.path, choice === 'local' ? change.local : change.saved);
    } return next; }
    function setCanvasDraft(next) { setLayoutName(next.name); layoutNameRef.current = next.name; setMode(next.mode); setPositions(clone(next.positions)); const settings = next.settings || {}; setHidden(settings.hidden || []); setCollapsed(settings.collapsed || []); if (settings.viewport)
        setView(settings.viewport); const filters = settings.filters || {}; setQuery(filters.query || ''); setAssetType(filters.asset_type || ''); setTag(filters.tag || ''); setRelation(filters.relation || ''); setScene(settings.scene_id || ''); setSequence(settings.sequence_id || ''); }
    function saveAsNew() { const base = `${layoutName.trim() || 'Working arrangement'} copy`; let next = base, index = 2; while (state.layouts.some(item => item.mode === mode && item.name === next)) {
        next = `${base} ${index++}`;
    } setLayoutId(''); setLayoutRevision(undefined); layoutBaseline.current = null; setLayoutConflict(false); setLayoutUnavailable(false); setConflictId(null); setReview(null); setLayoutName(next); layoutNameRef.current = next; setError(''); markDirty(); }
    async function save(approved) { if (savePromise.current)
        return savePromise.current; if (!layoutName.trim() || (layoutConflict && !approved))
        return false; if (approved && review?.changes.some(change => change.conflict && !review.choices[change.key]))
        return false; const version = editVersion.current, requested = approved ? applyNewLocalEdits(approved.reference, draftRef.current, approved.draft) : clone(draftRef.current), snapshot = { name: requested.name, mode: requested.mode, positions: requested.positions, settings: requested.settings, ...((approved?.revision ?? layoutRevision) !== undefined ? { revision: approved?.revision ?? layoutRevision } : {}), ...(approved?.id || layoutId ? { layout_id: approved?.id || layoutId } : {}) }; setSaving(true); setError(''); const operation = (async () => { try {
        const result = await (0, api_1.runCommand)(state.project.id, 'canvas.save', snapshot);
        const saved = draftFromLayoutResult(result);
        const current = editVersion.current === version ? saved : applyNewLocalEdits(requested, draftRef.current, asLayoutDraft(result));
        if (approved)
            setCanvasDraft(current);
        layoutBaseline.current = saved;
        setLayoutId(result.id);
        setLayoutName(current.name);
        layoutNameRef.current = current.name;
        setLayoutRevision(result.revision);
        setLayoutConflict(false);
        setLayoutUnavailable(false);
        setConflictId(null);
        setReview(null);
        const hasNewerEdits = editVersion.current !== version;
        if (!hasNewerEdits) {
            dirtyRef.current = false;
            setDirty(false);
        }
        else {
            dirtyRef.current = true;
            setDirty(true);
        }
        publishDraft({ ...snapshotFields(current), baseline: saved, layoutId: result.id, layoutRevision: result.revision, dirty: hasNewerEdits, layoutConflict: false, layoutUnavailable: false, conflictId: null, review: null, error: '' });
        let refreshFailure = '';
        try {
            await refresh();
        }
        catch (e) {
            refreshFailure = e.message;
            setError(`Arrangement saved, but the project view could not refresh: ${e.message}`);
        }
        notify(refreshFailure ? 'Arrangement saved, but the project view could not refresh.' : 'Canvas arrangement saved. Story order and connections stay the same.');
        return true;
    }
    catch (e) {
        setError(e.message);
        if (e.code === 'revision_conflict') {
            setLayoutConflict(true);
            setLayoutUnavailable(false);
            setConflictId(e.details?.id ? String(e.details.id) : layoutId || null);
            setReview(null);
        }
        return false;
    }
    finally {
        savePromise.current = null;
        setSaving(false);
    } })(); savePromise.current = operation; return operation; }
    async function reapplyConflict() { if (!review)
        return; const active = review; if (active.changes.some(change => change.conflict && !active.choices[change.key]))
        return; const draft = resolvedReviewDraft(active); const saved = await save({ draft, id: active.remote.id, revision: active.remote.revision, reference: active.local }); if (saved && pendingNavigation && !dirtyRef.current) {
        const commit = pendingNavigation;
        setPendingNavigation(null);
        commit();
    } }
    async function saveAndNavigate() { if (layoutConflict && review) {
        await reapplyConflict();
        return;
    } const saved = await save(); if (saved && pendingNavigation && !dirtyRef.current) {
        const commit = pendingNavigation;
        setPendingNavigation(null);
        commit();
    }
    else if (saved && dirtyRef.current)
        setError('Canvas changed while the save was pending. Save again to keep those edits before leaving.'); }
    function discardAndNavigate() { if (savePromise.current)
        return; const baseline = layoutBaseline.current; const next = baseline ? asLayoutDraft(baseline) : { name: layoutName, mode, positions: {}, settings: { viewport: { x: 50, y: 50, scale: .7 } } }; setCanvasDraft(next); dirtyRef.current = false; setDirty(false); setLayoutConflict(false); setLayoutUnavailable(false); setConflictId(null); setReview(null); setError(''); publishDraft({ ...snapshotFields(next), dirty: false, layoutConflict: false, layoutUnavailable: false, conflictId: null, review: null, error: '' }); const commit = pendingNavigation; setPendingNavigation(null); commit?.(); }
    function load(id) { if (savePromise.current)
        return; const saved = state.layouts.find(l => l.id === id); if (!saved)
        return; const restore = () => restoreSaved(saved); if (dirtyRef.current) {
        setPendingNavigation(() => restore);
        return;
    } restore(); }
    const conflictPanel = layoutConflict ? react_1.default.createElement("div", { className: "notice warning", role: "status" },
        react_1.default.createElement("p", null, layoutUnavailable ? 'This saved arrangement is no longer available. Your local Canvas edits remain. Save them as a new arrangement to keep them.' : 'The saved arrangement changed elsewhere. Your local Canvas edits remain. Refresh the latest saved version, compare the changed fields, and choose how to resolve each overlap.'),
        react_1.default.createElement("button", { onClick: () => void refreshConflict(), disabled: saving || refreshingConflict }, refreshingConflict ? 'Refreshing saved version…' : 'Refresh latest saved revision'),
        layoutUnavailable && react_1.default.createElement("button", { onClick: saveAsNew, disabled: saving }, "Save as new arrangement"),
        review && react_1.default.createElement("div", { className: "layout-conflict-review", "aria-label": "Saved and local arrangement changes" },
            react_1.default.createElement("h3", null,
                "Saved version ",
                review.remote.revision,
                " \u00B7 compare changes"),
            review.changes.length ? react_1.default.createElement("ul", null, review.changes.map(change => react_1.default.createElement("li", { key: change.key, "data-conflict-path": change.key },
                react_1.default.createElement("strong", null, labelChange(change.path)),
                react_1.default.createElement("div", { className: "layout-conflict-values" },
                    react_1.default.createElement("span", null,
                        "Saved: ",
                        change.saved.present ? JSON.stringify(change.saved.value) : 'Not set'),
                    react_1.default.createElement("span", null,
                        "Local: ",
                        change.local.present ? JSON.stringify(change.local.value) : 'Not set')),
                change.conflict ? react_1.default.createElement("div", { className: "layout-conflict-choices" },
                    react_1.default.createElement("button", { "aria-pressed": review.choices[change.key] === 'local', onClick: () => setReview(old => old ? { ...old, choices: { ...old.choices, [change.key]: 'local' } } : old) }, "Keep local"),
                    react_1.default.createElement("button", { "aria-pressed": review.choices[change.key] === 'saved', onClick: () => setReview(old => old ? { ...old, choices: { ...old.choices, [change.key]: 'saved' } } : old) }, "Use saved")) : react_1.default.createElement("small", null, "These edits do not overlap and will be merged automatically.")))) : react_1.default.createElement("p", null, "The saved and local arrangement fields match. You can safely reapply the current draft."),
            react_1.default.createElement("button", { className: "primary", onClick: () => void reapplyConflict(), disabled: saving || review.changes.some(change => change.conflict && !review.choices[change.key]) }, "Reapply merged arrangement"))) : null;
    const selectedNode = state.entities.find(n => n.id === selected);
    const tags = [...new Set(state.entities.flatMap(e => e.tags))].sort();
    return react_1.default.createElement("div", { className: "canvas-page" },
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Story map", title: "Canvas", description: "Arrange story cards and connect people, places, shots, and references.", actions: react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("select", { "aria-label": "Item to create", value: newKind, onChange: (e) => setNewKind(e.target.value) },
                    react_1.default.createElement("option", { value: "asset" }, "Library item"),
                    react_1.default.createElement("option", { value: "sequence" }, "Sequence"),
                    react_1.default.createElement("option", { value: "scene" }, "Scene"),
                    react_1.default.createElement("option", { value: "shot" }, "Shot")),
                react_1.default.createElement("button", { onClick: () => action(newKind + '.create', newKind === 'shot' && scene ? { parent_id: scene } : newKind === 'scene' && sequence ? { parent_id: sequence } : {}) },
                    react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                    "Create ",
                    (0, utils_1.human)(newKind).toLowerCase()),
                react_1.default.createElement("button", { onClick: () => action('link.create') }, "Connect items")) }),
        react_1.default.createElement("div", { className: "canvas-controls" },
            react_1.default.createElement("div", { className: "segmented", "aria-label": "Canvas view" }, [['story', 'Story flow'], ['assets', 'Reference map'], ['scene', 'Scene board']].map(([value, label]) => react_1.default.createElement("button", { key: value, "aria-pressed": mode === value, onClick: () => switchMode(value), disabled: saving }, label))),
            react_1.default.createElement("label", { className: "search" },
                react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
                react_1.default.createElement("input", { "aria-label": "Search canvas cards", placeholder: "Find a card\u2026", value: query, onChange: (e) => { setQuery(e.target.value); markDirty(); } })),
            mode === 'scene' && react_1.default.createElement("select", { "aria-label": "Scene to show", value: scene, onChange: (e) => { setScene(e.target.value); markDirty(); } },
                react_1.default.createElement("option", { value: "" }, "Choose a scene"),
                (0, utils_1.activeEntities)(state, 'scene').map(n => react_1.default.createElement("option", { key: n.id, value: n.id }, n.title))),
            mode === 'story' && react_1.default.createElement("select", { "aria-label": "Show sequence", value: sequence, onChange: (e) => { setSequence(e.target.value); markDirty(); } },
                react_1.default.createElement("option", { value: "" }, "All sequences"),
                (0, utils_1.activeEntities)(state, 'sequence').map(n => react_1.default.createElement("option", { key: n.id, value: n.id }, n.title))),
            mode === 'assets' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("select", { "aria-label": "Filter by item type", value: assetType, onChange: (e) => { setAssetType(e.target.value); markDirty(); } },
                    react_1.default.createElement("option", { value: "" }, "All item types"),
                    ['character', 'location', 'prop', 'reference'].map(t => react_1.default.createElement("option", { key: t, value: t }, (0, utils_1.human)(t)))),
                react_1.default.createElement("select", { "aria-label": "Tag filter", value: tag, onChange: (e) => { setTag(e.target.value); markDirty(); } },
                    react_1.default.createElement("option", { value: "" }, "All tags"),
                    tags.map(t => react_1.default.createElement("option", { key: t, value: t }, (0, utils_1.human)(t)))),
                react_1.default.createElement("select", { "aria-label": "Filter by connection", value: relation, onChange: (e) => { setRelation(e.target.value); markDirty(); } },
                    react_1.default.createElement("option", { value: "" }, "All connections"),
                    ['appears-at', 'alternate-view-of', 'wears', 'part-of', 'related-to'].map(t => react_1.default.createElement("option", { key: t, value: t }, (0, utils_1.human)(t)))))),
        error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
        " ",
        linkFrom && react_1.default.createElement("div", { className: "notice" },
            "Link from ",
            react_1.default.createElement("strong", null, (0, utils_1.displayTitle)(state.entities.find(n => n.id === linkFrom)?.title || 'Selected item')),
            ". Tab to a destination and press Enter, or click a node. ",
            react_1.default.createElement("button", { onClick: () => setLinkFrom(null) }, "Cancel link")),
        react_1.default.createElement("div", { className: "canvas-layout-bar" },
            react_1.default.createElement("select", { "aria-label": "Saved arrangement", value: layoutId, disabled: saving, onChange: (e) => load(e.target.value) },
                react_1.default.createElement("option", { value: "" }, "New arrangement"),
                layoutId && !state.layouts.some(l => l.id === layoutId) && react_1.default.createElement("option", { value: layoutId }, "Unavailable arrangement"),
                state.layouts.filter(l => l.mode === mode).map(l => react_1.default.createElement("option", { key: l.id, value: l.id }, l.name))),
            react_1.default.createElement("input", { "aria-label": "Arrangement name", value: layoutName, onChange: (e) => { layoutNameRef.current = e.target.value; setLayoutName(e.target.value); markDirty(); } }),
            react_1.default.createElement("button", { onClick: () => void save(), disabled: !layoutName.trim() || saving || layoutConflict }, saving ? 'Saving…' : 'Save arrangement'),
            layoutId && react_1.default.createElement("button", { onClick: saveAsNew, disabled: saving }, "Save as new"),
            react_1.default.createElement("button", { onClick: () => { setPositions((0, geometry_1.tidy)(graph.nodes, graph.edges, mode)); markDirty(); } }, "Arrange cards"),
            react_1.default.createElement("button", { onClick: fitView }, "Fit canvas"),
            dirty && react_1.default.createElement("span", { role: "status" }, "Unsaved changes"),
            hidden.length > 0 && react_1.default.createElement("button", { onClick: () => { setHidden([]); markDirty(); } },
                "Show ",
                hidden.length,
                " hidden cards")),
        conflictPanel,
        react_1.default.createElement("div", { ref: stage, className: `graph-stage ${linkFrom ? 'linking' : ''}`, tabIndex: 0, "aria-label": "Interactive story canvas. Use Tab to select a card, arrow keys to move it, L to connect it, and Delete to review removal.", onPointerDown: (e) => startDrag(e), onPointerMove: move, onPointerUp: end, onPointerCancel: end, onKeyDown: (e) => { if (e.key === 'Escape') {
                setLinkFrom(null);
                setSelectedEdge(null);
            } } },
            react_1.default.createElement("div", { className: "canvas-world", style: { transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` } },
                react_1.default.createElement("svg", { className: "edge-layer", width: "1", height: "1", "aria-label": "Story and image connections" },
                    react_1.default.createElement("defs", null,
                        react_1.default.createElement("marker", { id: "edge-arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" },
                            react_1.default.createElement("path", { d: "M 0 0 L 10 5 L 0 10 z" }))),
                    edges.map(edge => { const a = positions[edge.source], b = positions[edge.target]; if (!a || !b)
                        return null; const label = edgeLabel(edge); const curve = (0, geometry_1.edgePath)(a, b); return react_1.default.createElement("g", { key: edge.id, className: `graph-edge ${edge.kind} ${selectedEdge?.id === edge.id ? 'is-selected' : ''}` },
                        react_1.default.createElement("path", { d: curve.path, markerEnd: "url(#edge-arrow)" }),
                        react_1.default.createElement("path", { d: curve.path, className: "edge-hit", onClick: (e) => { e.stopPropagation(); setSelectedEdge(edge); } }),
                        react_1.default.createElement("g", { transform: `translate(${curve.label.x}, ${curve.label.y})`, role: "button", tabIndex: 0, "aria-label": `${label} connection. Select to see options.`, onPointerDown: (e) => e.stopPropagation(), onClick: () => setSelectedEdge(edge), onKeyDown: (e) => { if (e.key === 'Enter') {
                                e.preventDefault();
                                e.stopPropagation();
                                setSelectedEdge(edge);
                            } } },
                            react_1.default.createElement("rect", { x: -Math.max(18, label.length * 3.7 + 8), y: "-12", width: Math.max(36, label.length * 7.4 + 16), height: "24", rx: "4" }),
                            react_1.default.createElement("text", { textAnchor: "middle", dominantBaseline: "central" },
                                edge.kind === 'order' ? '# ' : edge.kind === 'assignment' ? '↳ ' : '',
                                label))); })),
                visible.map(node => {
                    const pos = positions[node.id] || { x: 0, y: 0 }, type = (0, utils_1.kindLabel)(node);
                    const thumbnail = node.thumbnail_media_id || node.reference_media_ids?.[0];
                    return react_1.default.createElement("article", { key: node.id, "data-node-id": node.id, className: `graph-node ${type} ${selected === node.id || multi.includes(node.id) ? 'is-selected' : ''} ${linkFrom === node.id ? 'link-source' : ''}`, style: { width: geometry_1.NODE_W, height: geometry_1.NODE_H, transform: `translate(${pos.x}px,${pos.y}px)` }, tabIndex: 0, role: "button", "aria-label": `${type}: ${node.title}. Used ${node.reference_count || 0} times.`, "aria-pressed": selected === node.id, onPointerDown: (e) => startDrag(e, node), onPointerMove: move, onPointerUp: end, onClick: (e) => { e.stopPropagation(); select(node, e); }, onKeyDown: (e) => key(e, node) },
                        react_1.default.createElement("div", { className: "node-type" },
                            react_1.default.createElement("span", null, type),
                            react_1.default.createElement("span", null, node.kind === 'asset' ? `${node.media_count || 0} images` : `${String(node.position + 1).padStart(2, '0')}`)),
                        thumbnail ? react_1.default.createElement("img", { className: "node-image", src: (0, api_1.mediaUrl)(state.project.id, thumbnail), alt: `${(0, utils_1.displayTitle)(node.title)} ${node.frame_state ? 'storyboard image' : 'reference image'}`, draggable: false }) : react_1.default.createElement("div", { className: "node-text-preview" }, String(node.fields.action || node.fields.summary || node.fields.arc || node.description || 'Add a description or story direction')),
                        react_1.default.createElement("div", { className: "node-content" },
                            react_1.default.createElement("h3", null, (0, utils_1.displayTitle)(node.title)),
                            react_1.default.createElement("p", null, node.kind === 'shot' ? `${node.fields.framing || 'Framing not set'} · ${node.reference_count || 0} references` : node.kind === 'asset' ? `${node.link_count || 0} connections · used in ${node.reference_count || 0} shots` : `${node.child_count || 0} ${node.kind === 'sequence' ? 'scenes' : 'shots'}`),
                            react_1.default.createElement("div", { className: "node-footer" },
                                node.frame_state ? react_1.default.createElement(Primitives_1.Badge, { kind: node.frame_state },
                                    (0, utils_1.statusLabel)(node.frame_state),
                                    " image") : node.tags.slice(0, 2).map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)),
                                node.child_count > 0 && node.kind !== 'asset' && react_1.default.createElement("button", { "aria-label": `${collapsed.includes(node.id) ? 'Expand' : 'Collapse'} ${(0, utils_1.displayTitle)(node.title)}`, onClick: (e) => { e.stopPropagation(); setCollapsed(v => v.includes(node.id) ? v.filter(id => id !== node.id) : [...v, node.id]); markDirty(); } }, collapsed.includes(node.id) ? '+' : '−'))));
                })),
            !visible.length && !loading && react_1.default.createElement(Primitives_1.Empty, { title: mode === 'scene' ? 'Choose a scene to build its board' : mode === 'assets' ? 'Build your reference library' : 'Start your story map', action: react_1.default.createElement("button", { onClick: () => action(mode === 'assets' ? 'asset.create' : mode === 'scene' ? 'scene.create' : 'sequence.create') },
                    "Create a ",
                    mode === 'assets' ? 'reference item' : mode === 'scene' ? 'scene' : 'sequence') }, mode === 'assets' ? 'Add characters, places, props, and other references here. Their connections will appear as your library grows.' : 'Create items here or in the story outline. Story order and reference connections will appear as you build.'),
            react_1.default.createElement("div", { className: "canvas-zoom", onPointerDown: (e) => e.stopPropagation() },
                react_1.default.createElement("button", { "aria-label": "Zoom out", onClick: () => { setView(v => (0, geometry_1.zoomAt)(v, { x: 200, y: 200 }, .8)); markDirty(); } }, "\u2212"),
                react_1.default.createElement("span", null,
                    Math.round(view.scale * 100),
                    "%"),
                react_1.default.createElement("button", { "aria-label": "Zoom in", onClick: () => { setView(v => (0, geometry_1.zoomAt)(v, { x: 200, y: 200 }, 1.25)); markDirty(); } }, "+"))),
        react_1.default.createElement("div", { className: "canvas-status" },
            dirty && react_1.default.createElement("span", { role: "status" }, "Unsaved arrangement \u00B7 kept while you navigate"),
            react_1.default.createElement("span", null,
                loading ? 'Loading…' : `${visible.length} cards · ${edges.length} connections`,
                graph.truncated && ` · ${graph.total} matches; narrow your search to see more (up to 250 cards at a time)`),
            react_1.default.createElement("span", null, "Drag the background to move \u00B7 Ctrl + scroll to zoom \u00B7 Arrow keys to arrange \u00B7 L to connect")),
        selectedNode && react_1.default.createElement("div", { className: "selection-tools" },
            react_1.default.createElement("strong", null, (0, utils_1.displayTitle)(selectedNode.title)),
            react_1.default.createElement("button", { onClick: () => action(selectedNode.kind + '.update', (0, utils_1.commandDefaults)(selectedNode)) }, "Edit"),
            react_1.default.createElement("button", { onClick: () => setLinkFrom(selectedNode.id) }, "Connect from here"),
            ['sequence', 'scene', 'shot'].includes(selectedNode.kind) && react_1.default.createElement("button", { onClick: () => action('story.move', (0, utils_1.commandDefaults)(selectedNode)) }, "Move / reorder"),
            react_1.default.createElement("button", { onClick: () => requestDelete(selectedNode.id) }, "Remove\u2026")),
        selectedEdge && react_1.default.createElement("div", { className: "selection-tools" },
            react_1.default.createElement("strong", null, edgeLabel(selectedEdge)),
            react_1.default.createElement("span", null, selectedEdge.kind === 'order' ? 'Story order' : selectedEdge.kind === 'assignment' ? 'Shot reference' : selectedEdge.kind === 'location_default' ? `Location from ${(0, utils_1.human)(selectedEdge.source_scope?.kind || 'project').toLowerCase()}` : 'Connection between library items'),
            selectedEdge.kind === 'order' ? react_1.default.createElement("button", { onClick: () => { const child = state.entities.find(n => n.id === selectedEdge.target); if (child)
                    action('story.move', (0, utils_1.commandDefaults)(child)); } }, "Move in story") : selectedEdge.kind === 'location_default' ? react_1.default.createElement("button", { onClick: () => { const owner = state.entities.find(n => n.id === selectedEdge.source); if (owner)
                    action(owner.kind + '.update', (0, utils_1.commandDefaults)(owner)); } }, "Edit location\u2026") : react_1.default.createElement("button", { onClick: () => action(selectedEdge.kind === 'assignment' ? 'assignment.remove' : 'link.remove', { id: selectedEdge.id, revision: selectedEdge.revision }) }, "Remove connection\u2026"),
            react_1.default.createElement("button", { onClick: () => setSelectedEdge(null) }, "Close")),
        deleteId && react_1.default.createElement(Primitives_1.Modal, { title: "Remove this card?", onClose: closeDelete },
            react_1.default.createElement("div", { className: "modal-body", "data-removal-id": deleteId },
                react_1.default.createElement("p", null, "Hiding a card removes it from this arrangement. Archiving takes the item out of the active story; deleting removes it permanently."),
                usage ? react_1.default.createElement("div", { className: "usage-summary" },
                    react_1.default.createElement("p", null, usage.can_delete ? 'This item is not used elsewhere.' : 'This item is used in these places:'),
                    Object.entries(usage).filter(([key, value]) => key !== 'can_delete' && Array.isArray(value) && value.length > 0).length > 0 && react_1.default.createElement("ul", null, Object.entries(usage).filter(([key, value]) => key !== 'can_delete' && Array.isArray(value) && value.length > 0).map(([key, value]) => react_1.default.createElement("li", { key: key },
                        (0, utils_1.human)(key),
                        " \u00B7 ",
                        value.length)))) : usageLoading ? react_1.default.createElement("p", { role: "status" }, "Checking where this item is used\u2026") : usageError ? react_1.default.createElement("div", { className: "notice error", role: "alert" },
                    react_1.default.createElement("strong", null, "We couldn\u2019t check where this item is used."),
                    react_1.default.createElement("p", null, usageError),
                    react_1.default.createElement("button", { onClick: () => void refreshUsage(deleteId) }, "Retry usage check")) : react_1.default.createElement("p", { role: "status" }, "Usage details are unavailable."),
                react_1.default.createElement("div", { className: "form-stack" },
                    react_1.default.createElement("button", { onClick: () => { setHidden([...hidden, deleteId]); markDirty(); closeDelete(); } }, "Hide from this arrangement"),
                    react_1.default.createElement("button", { disabled: !usage || usageLoading, onClick: () => { const n = state.entities.find(n => n.id === deleteId); if (n)
                            action('entity.archive', (0, utils_1.commandDefaults)(n)); closeDelete(); } }, "Archive item\u2026"),
                    react_1.default.createElement("button", { className: "danger", disabled: !usage?.can_delete || usageLoading, onClick: () => { const n = state.entities.find(n => n.id === deleteId); if (n)
                            action('entity.delete', (0, utils_1.commandDefaults)(n)); closeDelete(); } }, "Delete item\u2026")))),
        pendingNavigation && react_1.default.createElement(Primitives_1.Modal, { title: "Unsaved canvas arrangement", onClose: () => setPendingNavigation(null) },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("p", null, "Your Canvas changes have not been saved. Save them to this arrangement, discard them, or stay on this view. Page and project navigation keep your draft. This action replaces the current arrangement, or waits for an active save. The current geometry remains available while you decide."),
                error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
                " ",
                conflictPanel),
            react_1.default.createElement("div", { className: "modal-footer" },
                react_1.default.createElement("button", { onClick: () => setPendingNavigation(null) }, "Stay"),
                react_1.default.createElement("button", { onClick: discardAndNavigate, disabled: saving }, "Discard changes"),
                react_1.default.createElement("button", { className: "primary", disabled: !layoutName.trim() || saving || layoutConflict, onClick: () => void saveAndNavigate() }, saving ? 'Saving…' : 'Save and continue'))));
}

},
"canvas/geometry":function(require,module,exports){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.clamp = exports.NODE_H = exports.NODE_W = void 0;
exports.screenToWorld = screenToWorld;
exports.zoomAt = zoomAt;
exports.hitTest = hitTest;
exports.tidy = tidy;
exports.fit = fit;
exports.edgePath = edgePath;
exports.descendants = descendants;
exports.NODE_W = 238, exports.NODE_H = 222;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
exports.clamp = clamp;
function screenToWorld(point, view) { return { x: (point.x - view.x) / view.scale, y: (point.y - view.y) / view.scale }; }
function zoomAt(view, point, factor) { const scale = (0, exports.clamp)(view.scale * factor, .15, 3); const world = screenToWorld(point, view); return { scale, x: point.x - world.x * scale, y: point.y - world.y * scale }; }
function hitTest(point, positions) { return Object.keys(positions).reverse().find(id => { const p = positions[id]; return point.x >= p.x && point.x <= p.x + exports.NODE_W && point.y >= p.y && point.y <= p.y + exports.NODE_H; }) || null; }
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
function fit(positions, width, height) { const points = Object.values(positions); if (!points.length)
    return { x: 60, y: 60, scale: 1 }; const x = Math.min(...points.map(p => p.x)), y = Math.min(...points.map(p => p.y)); const w = Math.max(...points.map(p => p.x)) + exports.NODE_W - x, h = Math.max(...points.map(p => p.y)) + exports.NODE_H - y; const scale = (0, exports.clamp)(Math.min((width - 100) / w, (height - 100) / h), .15, 1.2); return { scale, x: (width - w * scale) / 2 - x * scale, y: (height - h * scale) / 2 - y * scale }; }
function edgePath(a, b) { const start = { x: a.x + exports.NODE_W, y: a.y + exports.NODE_H / 2 }, end = { x: b.x, y: b.y + exports.NODE_H / 2 }; const bend = Math.max(65, Math.abs(end.x - start.x) * .5); return { path: `M ${start.x} ${start.y} C ${start.x + bend} ${start.y}, ${end.x - bend} ${end.y}, ${end.x} ${end.y}`, label: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 } }; }
function descendants(nodes, collapsed) { const result = new Set(); const visit = (id) => nodes.filter(n => n.parent_id === id).forEach(n => { result.add(n.id); visit(n.id); }); collapsed.forEach(visit); return result; }

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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ActionDialog = ActionDialog;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("./Primitives");
const remoteSources = new Set(['documents', 'document_nodes', 'versions', 'provenance_edges', 'annotations', 'provenance_endpoints', 'provenance_source', 'provenance_target', 'provenance_typed_endpoint']);
function ActionDialog({ command, state, meta, defaults = {}, onClose, onDone, onReload }) {
    const initialize = (initial) => ({ ...Object.fromEntries(command.fields.map(f => [f.name, initial[f.name] ?? f.default ?? (f.type === 'boolean' ? false : f.type === 'json' ? '{}' : '')])), ...(initial.asset_id ? { asset_id: initial.asset_id } : {}) });
    const [values, setValues] = (0, react_1.useState)(() => initialize(defaults));
    const [busy, setBusy] = (0, react_1.useState)(false);
    const busyRef = (0, react_1.useRef)(false);
    const [cancelBusy, setCancelBusy] = (0, react_1.useState)(false);
    const [error, setError] = (0, react_1.useState)(null);
    const [confirmed, setConfirmed] = (0, react_1.useState)(false);
    const [choices, setChoices] = (0, react_1.useState)({});
    const [queries, setQueries] = (0, react_1.useState)({});
    const [choiceRecords, setChoiceRecords] = (0, react_1.useState)({});
    const [choiceLoading, setChoiceLoading] = (0, react_1.useState)({});
    const [resolving, setResolving] = (0, react_1.useState)({});
    const valuesRef = (0, react_1.useRef)(values);
    valuesRef.current = values;
    const queriesRef = (0, react_1.useRef)(queries);
    queriesRef.current = queries;
    const alive = (0, react_1.useRef)(true);
    const requests = (0, react_1.useRef)({});
    const stateRef = (0, react_1.useRef)(state);
    stateRef.current = state;
    const contextFields = ['id', 'document_id', 'version_id', 'source_type', 'target_type', 'endpoint_type', 'kind', 'record_id', 'endpoint_id'];
    const context = Object.fromEntries(command.fields.filter(f => ['id', 'document_id', 'version_id', 'source_type', 'target_type', 'endpoint_type', 'kind', 'record_id', 'endpoint_id'].includes(f.name)).map(f => [f.name, values[f.name]]));
    const contextKey = JSON.stringify(context);
    function contextFor(current) { return JSON.stringify(Object.fromEntries(command.fields.filter(f => contextFields.includes(f.name)).map(f => [f.name, current[f.name]]))); }
    function selectionKey(current) { return JSON.stringify(Object.fromEntries(command.fields.filter(f => remoteSources.has(f.source) || f.name.endsWith('_id')).map(f => [f.name, current[f.name]]))); }
    function scopedRequestKey(current) { return JSON.stringify({ project: stateRef.current.project.id, command: command.name, context: contextFor(current), selection: selectionKey(current) }); }
    function scopedRequestIsCurrent(name, controller, key, current = valuesRef.current) { return alive.current && !controller.signal.aborted && requests.current[name] === controller && scopedRequestKey(current) === key; }
    function invalidateScopedRequests(previous, next) {
        const changed = command.fields.some(f => (remoteSources.has(f.source) || f.name.endsWith('_id') || contextFields.includes(f.name)) && previous[f.name] !== next[f.name]);
        if (changed)
            for (const name of ['reload', 'cancelRun']) {
                requests.current[name]?.abort();
                delete requests.current[name];
            }
    }
    function fieldContext(name, current = valuesRef.current) {
        const source = command.fields.find(f => f.name === name)?.source;
        const names = source === 'document_nodes' ? ['document_id', 'version_id'] : source === 'versions' ? ['document_id', 'id'] : source === 'provenance_source' ? ['source_type'] : source === 'provenance_target' ? ['target_type'] : source === 'provenance_typed_endpoint' ? ['kind', 'endpoint_type'] : source === 'provenance_endpoints' ? ['source_type', 'target_type', 'kind', 'endpoint_type'] : [];
        return JSON.stringify(Object.fromEntries(names.filter(key => command.fields.some(f => f.name === key)).map(key => [key, current[key]])));
    }
    function requestKey(name) { return fieldContext(name) + '|' + (queriesRef.current[name] || ''); }
    function dependentFields(name) {
        if (name === 'document_id' || name === 'id' && command.fields.find(f => f.name === name)?.source === 'documents')
            return ['version_id', 'node_id', 'parent_id'];
        return { version_id: ['parent_id', 'node_id'], source_type: ['source_id'], target_type: ['target_id'], kind: ['record_id'], endpoint_type: ['endpoint_id'] }[name] || [];
    }
    function clearDependents(name, value) {
        const cleared = valuesRef.current[name] !== value ? dependentFields(name) : [];
        for (const field of cleared) {
            requests.current['record:' + field]?.abort();
            delete requests.current['record:' + field];
        }
        if (cleared.length) {
            invalidateScopedRequests(valuesRef.current, { ...valuesRef.current, ...Object.fromEntries(cleared.map(field => [field, ''])) });
            setResolving(previous => ({ ...previous, ...Object.fromEntries(cleared.map(field => [field, false])) }));
            setChoiceRecords(previous => { const next = { ...previous }; for (const field of cleared)
                delete next[field]; return next; });
        }
        return cleared;
    }
    (0, react_1.useEffect)(() => { alive.current = true; return () => { alive.current = false; for (const controller of Object.values(requests.current))
        controller.abort(); }; }, []);
    function choicePath(name, id) { return (0, api_1.projectPath)(stateRef.current.project.id, `/commands/${encodeURIComponent(command.name)}/fields/${encodeURIComponent(name)}/choices${id ? '/' + encodeURIComponent(id) : ''}`); }
    function asError(e) { return e instanceof api_1.ApiError ? e : new api_1.ApiError('invalid', e instanceof Error ? e.message : String(e)); }
    function recordValues(previous, name, record, preserveDraft = false) {
        const next = { ...previous };
        if (['id', 'document_id', 'node_id', 'edge_id', 'annotation_id'].includes(name) && record.revision !== undefined)
            next.revision = record.revision;
        if (!preserveDraft && command.name === 'annotation.update' && name === 'annotation_id') {
            next.content = record.text;
            next.state = record.state;
        }
        return next;
    }
    (0, react_1.useEffect)(() => {
        const controller = new AbortController();
        for (const field of command.fields.filter(f => remoteSources.has(f.source))) {
            requests.current['page:' + field.name]?.abort();
            delete requests.current['page:' + field.name];
            const key = requestKey(field.name);
            setChoiceLoading(previous => ({ ...previous, [field.name]: true }));
            const params = new URLSearchParams({ values: contextKey, query: queries[field.name] || '', limit: '100', offset: '0' });
            (0, api_1.api)(choicePath(field.name) + '?' + params, 'GET', undefined, controller.signal)
                .then(page => { if (alive.current && !controller.signal.aborted && requestKey(field.name) === key)
                setChoices(previous => ({ ...previous, [field.name]: page })); })
                .catch(e => { if (alive.current && e.name !== 'AbortError' && !controller.signal.aborted)
                setError(asError(e)); })
                .finally(() => { if (!controller.signal.aborted)
                setChoiceLoading(previous => ({ ...previous, [field.name]: false })); });
        }
        return () => controller.abort();
    }, [command.name, state.project.id, contextKey, JSON.stringify(queries)]);
    (0, react_1.useEffect)(() => { for (const field of command.fields.filter(f => remoteSources.has(f.source) && valuesRef.current[f.name]))
        void selectRemote(field.name, valuesRef.current[field.name]); }, [command.name, state.project.id]);
    async function selectRemote(name, value) {
        requests.current['record:' + name]?.abort();
        const before = valuesRef.current;
        const cleared = clearDependents(name, value);
        const nextValues = { ...before, ...Object.fromEntries(cleared.map(field => [field, ''])), [name]: value, ...(['id', 'document_id', 'node_id', 'edge_id', 'annotation_id'].includes(name) ? { revision: '' } : {}) };
        invalidateScopedRequests(before, nextValues);
        setValues(previous => ({ ...previous, ...Object.fromEntries(cleared.map(field => [field, ''])), [name]: value, ...(['id', 'document_id', 'node_id', 'edge_id', 'annotation_id'].includes(name) ? { revision: '' } : {}) }));
        setChoiceRecords(previous => { const next = { ...previous }; delete next[name]; return next; });
        if (!value) {
            delete requests.current['record:' + name];
            setResolving(previous => ({ ...previous, [name]: false }));
            return;
        }
        const controller = new AbortController();
        requests.current['record:' + name] = controller;
        const key = fieldContext(name);
        setResolving(previous => ({ ...previous, [name]: true }));
        try {
            const record = await (0, api_1.api)(choicePath(name, value) + '?' + new URLSearchParams({ values: contextKey }), 'GET', undefined, controller.signal);
            if (!alive.current || controller.signal.aborted || requests.current['record:' + name] !== controller || fieldContext(name) !== key || valuesRef.current[name] !== value)
                return;
            setValues(previous => previous[name] === value ? recordValues(previous, name, record) : previous);
            setChoiceRecords(previous => ({ ...previous, [name]: record }));
        }
        catch (e) {
            if (alive.current && !controller.signal.aborted)
                setError(asError(e));
        }
        finally {
            if (alive.current && requests.current['record:' + name] === controller) {
                delete requests.current['record:' + name];
                setResolving(previous => ({ ...previous, [name]: false }));
            }
        }
    }
    async function moreChoices(name) {
        const offset = choices[name]?.next_offset;
        if (offset == null)
            return;
        requests.current['page:' + name]?.abort();
        const controller = new AbortController();
        requests.current['page:' + name] = controller;
        const key = requestKey(name);
        setChoiceLoading(previous => ({ ...previous, [name]: true }));
        try {
            const page = await (0, api_1.api)(choicePath(name) + '?' + new URLSearchParams({ values: contextKey, query: queries[name] || '', limit: '100', offset: String(offset) }), 'GET', undefined, controller.signal);
            if (!alive.current || controller.signal.aborted || requestKey(name) !== key)
                return;
            setChoices(previous => ({ ...previous, [name]: { ...page, items: [...(previous[name]?.items || []), ...page.items] } }));
        }
        catch (e) {
            if (alive.current && !controller.signal.aborted)
                setError(asError(e));
        }
        finally {
            if (alive.current && requests.current['page:' + name] === controller) {
                delete requests.current['page:' + name];
                setChoiceLoading(previous => ({ ...previous, [name]: false }));
            }
        }
    }
    const set = (name, value) => {
        const before = valuesRef.current, cleared = clearDependents(name, value), next = { ...before, ...Object.fromEntries(cleared.map(field => [field, ''])), [name]: value };
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
        invalidateScopedRequests(before, next);
        setValues(next);
    };
    async function submit(e) {
        e.preventDefault();
        if (busyRef.current || Object.values(resolving).some(Boolean) || !alive.current)
            return;
        busyRef.current = true;
        setBusy(true);
        setError(null);
        const controller = new AbortController();
        requests.current.submit?.abort();
        requests.current.submit = controller;
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
            const result = await (0, api_1.api)((0, api_1.projectPath)(stateRef.current.project.id, `/commands/${encodeURIComponent(command.name)}`), 'POST', payload, controller.signal);
            if (!alive.current || controller.signal.aborted || requests.current.submit !== controller)
                return;
            await onDone(result, command.name);
            if (alive.current && !controller.signal.aborted && requests.current.submit === controller)
                onClose();
        }
        catch (e) {
            if (alive.current && !controller.signal.aborted && requests.current.submit === controller)
                setError(e instanceof api_1.ApiError ? e : new api_1.ApiError('invalid', e instanceof Error ? e.message : String(e)));
        }
        finally {
            busyRef.current = false;
            if (alive.current && requests.current.submit === controller) {
                delete requests.current.submit;
                setBusy(false);
            }
        }
    }
    async function cancelRun() {
        if (!alive.current || cancelBusy)
            return;
        requests.current.cancelRun?.abort();
        const controller = new AbortController();
        requests.current.cancelRun = controller;
        const key = scopedRequestKey(valuesRef.current);
        setCancelBusy(true);
        const current = () => scopedRequestIsCurrent('cancelRun', controller, key);
        try {
            const fresh = await onReload();
            if (!current())
                return;
            const job = fresh.jobs.find(j => j.id === valuesRef.current.id);
            if (job && ['queued', 'running'].includes(job.status)) {
                await (0, api_1.api)((0, api_1.projectPath)(stateRef.current.project.id, '/commands/job.cancel'), 'POST', { id: job.id, revision: job.revision }, controller.signal);
            }
        }
        catch (e) {
            if (current())
                setError(asError(e));
        }
        finally {
            if (requests.current.cancelRun === controller) {
                delete requests.current.cancelRun;
                if (alive.current && !controller.signal.aborted)
                    setCancelBusy(false);
            }
        }
    }
    async function reload() {
        requests.current.reload?.abort();
        const controller = new AbortController();
        requests.current.reload = controller;
        const selected = { ...valuesRef.current };
        const key = scopedRequestKey(selected);
        const serializedContext = contextFor(selected);
        const current = () => scopedRequestIsCurrent('reload', controller, key);
        try {
            const fresh = await onReload();
            if (!current())
                return;
            const field = command.fields.find(f => remoteSources.has(f.source) && ['id', 'document_id', 'node_id', 'edge_id', 'annotation_id'].includes(f.name) && selected[f.name]);
            if (field) {
                const recordId = selected[field.name];
                const record = await (0, api_1.api)(choicePath(field.name, recordId) + '?' + new URLSearchParams({ values: serializedContext }), 'GET', undefined, controller.signal);
                if (!current() || valuesRef.current[field.name] !== recordId)
                    return;
                setValues(previous => scopedRequestKey(previous) === key && previous[field.name] === recordId ? recordValues(previous, field.name, record, true) : previous);
                setChoiceRecords(previous => scopedRequestKey(valuesRef.current) === key && valuesRef.current[field.name] === recordId ? ({ ...previous, [field.name]: record }) : previous);
                if (current())
                    setError(null);
                return;
            }
            const currentRecord = (0, utils_1.allRecords)(fresh).find(record => record.id === selected.id);
            if (currentRecord) {
                setValues(previous => scopedRequestKey(previous) === key && previous.id === selected.id ? recordValues(previous, 'id', currentRecord, true) : previous);
                if (current())
                    setError(null);
            }
        }
        catch (e) {
            if (current())
                setError(asError(e));
        }
        finally {
            if (requests.current.reload === controller)
                delete requests.current.reload;
        }
    }
    return react_1.default.createElement(Primitives_1.Modal, { title: command.label, returnFocusSelector: "[data-action-search]", onClose: () => { if (!busy)
            onClose(); }, wide: command.fields.length > 10 },
        react_1.default.createElement("form", { onSubmit: submit },
            react_1.default.createElement("div", { className: "modal-body" },
                react_1.default.createElement("p", { className: "muted" }, command.read_only ? 'View information saved in this project.' : 'Changes are saved to this project and appear throughout Storyboarder.'),
                command.name === 'job.run' && react_1.default.createElement("div", { className: "notice warning" }, "Only run tools you trust. They run on this computer with the access allowed to your account."),
                busy && react_1.default.createElement("div", { className: "notice", role: "status" }, "Saving this action. Editing is paused until the request finishes."),
                error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error.message }, error.status === 409 && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("p", null, "Your edits are still here. Refresh the project to see the latest saved details, then reapply your changes."),
                    react_1.default.createElement("button", { type: "button", onClick: reload }, "Refresh project details"))),
                react_1.default.createElement("fieldset", { className: "action-fields", disabled: busy },
                    react_1.default.createElement("div", { className: command.fields.length > 10 ? 'form-grid' : 'form-stack' }, command.fields.map(f => {
                        const remote = remoteSources.has(f.source);
                        const records = choices[f.name]?.items || [];
                        const opts = remote ? records.map(r => ({ value: r.id, label: r.label })) : (0, utils_1.selectOptions)(f, state, meta, values);
                        const chosen = choiceRecords[f.name];
                        if (remote && chosen && chosen.id === values[f.name] && !opts.some(o => o.value === chosen.id))
                            opts.push({ value: chosen.id, label: chosen.label || chosen.title || chosen.id });
                        const isSource = !!f.source || !!f.options.length;
                        const label = (0, utils_1.fieldLabel)(f.name, f.label);
                        if (f.name === 'revision' || f.name === 'target_revision')
                            return react_1.default.createElement("input", { type: "hidden", key: f.name, value: values[f.name] ?? '' });
                        if (f.type === 'boolean')
                            return react_1.default.createElement("label", { className: "check-field", key: f.name },
                                react_1.default.createElement("input", { type: "checkbox", checked: !!values[f.name], onChange: (e) => set(f.name, e.target.checked) }),
                                react_1.default.createElement("span", null, label));
                        return react_1.default.createElement("div", { className: `field ${f.type === 'textarea' || f.type === 'json' ? 'full' : ''}`, key: f.name },
                            remote && react_1.default.createElement("input", { "aria-label": `Search ${label}`, type: "search", placeholder: `Search ${label.toLowerCase()}…`, value: queries[f.name] || '', onChange: (e) => setQueries(previous => ({ ...previous, [f.name]: e.target.value })) }),
                            react_1.default.createElement("label", { className: "field" },
                                react_1.default.createElement("span", null,
                                    label,
                                    f.required && react_1.default.createElement("span", { "aria-hidden": "true" }, " *")),
                                isSource ? react_1.default.createElement("select", { value: values[f.name] ?? '', onChange: (e) => remote ? void selectRemote(f.name, e.target.value) : set(f.name, e.target.value), required: f.required },
                                    react_1.default.createElement("option", { value: "" }, f.required ? 'Choose…' : f.name === 'location_id' ? 'Use location from above' : 'Not set'),
                                    opts.map(o => react_1.default.createElement("option", { key: o.value, value: o.value }, o.label))) : f.type === 'textarea' || f.type === 'json' ? react_1.default.createElement("textarea", { rows: f.type === 'json' ? 5 : 3, value: typeof values[f.name] === 'object' ? JSON.stringify(values[f.name], null, 2) : values[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required, spellCheck: f.type !== 'json' }) : react_1.default.createElement("input", { type: f.type === 'integer' || f.type === 'number' ? 'number' : 'text', step: f.type === 'number' ? 'any' : undefined, value: Array.isArray(values[f.name]) ? values[f.name].join(', ') : values[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required })),
                            remote && choiceLoading[f.name] && react_1.default.createElement("small", { role: "status" }, "Loading choices\u2026"),
                            remote && choices[f.name]?.next_offset != null && react_1.default.createElement("button", { type: "button", disabled: choiceLoading[f.name], onClick: () => void moreChoices(f.name) },
                                "Load more ",
                                label.toLowerCase(),
                                " choices"),
                            " ",
                            f.help && react_1.default.createElement("small", null, f.help),
                            isSource && !opts.length && !choiceLoading[f.name] && f.required && react_1.default.createElement("small", { className: "warning-text" }, (0, utils_1.emptySourceMessage)(f.source)));
                    }))),
                command.destructive && react_1.default.createElement("label", { className: "confirm-field" },
                    react_1.default.createElement("input", { type: "checkbox", checked: confirmed, onChange: (e) => setConfirmed(e.target.checked), required: true, disabled: busy }),
                    "I understand this will change the project.")),
            react_1.default.createElement("div", { className: "modal-footer" },
                busy && command.name === 'job.run' && react_1.default.createElement("button", { type: "button", className: "danger", disabled: cancelBusy, onClick: cancelRun }, "Stop this run"),
                react_1.default.createElement("button", { type: "button", onClick: onClose, disabled: busy }, "Cancel"),
                react_1.default.createElement("button", { className: command.destructive ? 'danger' : 'primary', type: "submit", disabled: busy || Object.values(resolving).some(Boolean) || (command.destructive && !confirmed) }, busy ? 'Working…' : command.read_only ? 'Show result' : command.label))));
}

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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.Inspector = Inspector;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("./Primitives");
const ShotIntent_1 = require("./ShotIntent");
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
    const action = String(fields.action || entity.description || 'No action has been added yet.');
    const displayBeat = shotTitle(entity);
    const summary = action.endsWith(` — ${displayBeat}`) ? action.slice(0, -displayBeat.length - 3) : action;
    const duration = fields.duration == null ? '' : `${Number(fields.duration)} sec`;
    return react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement("div", { className: "shot-detail-hero" },
            (sequence || scene) && react_1.default.createElement("div", { className: "shot-path" },
                sequence ? (0, utils_1.displayTitle)(sequence.title) : '',
                sequence && scene ? ' / ' : '',
                scene ? (0, utils_1.displayTitle)(scene.title) : ''),
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
                    react_1.default.createElement("strong", null, location ? (0, utils_1.displayTitle)(location) : 'Not assigned')),
                react_1.default.createElement("div", { className: "shot-fact" },
                    react_1.default.createElement("span", null, "Storyboard"),
                    react_1.default.createElement("strong", null, frames.length ? `${frames.length} storyboard image${frames.length === 1 ? '' : 's'}` : 'No storyboard image yet')))),
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
            react_1.default.createElement("h4", null, "Production notes"),
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
    const contextRefreshRevision = state.events[0]?.id;
    const [tab, setTab] = (0, react_1.useState)('details'), [context, setContext] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''), [contextLoading, setContextLoading] = (0, react_1.useState)(false);
    const contextRequest = (0, react_1.useRef)(0), contextOwner = (0, react_1.useRef)({ id, projectId: state.project.id });
    contextOwner.current = { id, projectId: state.project.id };
    async function loadContext(ownerId, projectId) { const request = ++contextRequest.current; setContextLoading(true); setError(''); try {
        const value = await (0, api_1.runCommand)(projectId, 'context.resolve', { owner_id: ownerId });
        if (request === contextRequest.current && contextOwner.current.id === ownerId && contextOwner.current.projectId === projectId)
            setContext(value);
    }
    catch (e) {
        if (request === contextRequest.current && contextOwner.current.id === ownerId && contextOwner.current.projectId === projectId)
            setError(e.message || 'Could not load story direction.');
    }
    finally {
        if (request === contextRequest.current && contextOwner.current.id === ownerId && contextOwner.current.projectId === projectId)
            setContextLoading(false);
    } }
    (0, react_1.useEffect)(() => { setContext(null); setError(''); if (entity && entity.kind !== 'asset')
        void loadContext(id, state.project.id);
    else
        setContextLoading(false); return () => { contextRequest.current += 1; }; }, [state.project.id, id, entity?.kind, contextRefreshRevision]);
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
    const tabs = ['details', 'references', ...(entity.kind === 'shot' ? ['shot-intent'] : []), ...(entity.kind === 'asset' ? [] : ['context'])];
    const activeTab = tabs.includes(tab) ? tab : 'details';
    const tabPrefix = `inspector-${encodeURIComponent(id)}`;
    function moveTab(event, index) { let next = null; if (event.key === 'ArrowRight')
        next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft')
        next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home')
        next = 0;
    else if (event.key === 'End')
        next = tabs.length - 1; if (next === null)
        return; event.preventDefault(); const nextTab = tabs[next]; setTab(nextTab); document.getElementById(`${tabPrefix}-tab-${nextTab}`)?.focus(); }
    const members = state.asset_media.filter(m => m.asset_id === id), assignments = state.assignments.filter(a => a.shot_id === id || a.asset_id === id), links = state.links.filter(l => l.source_id === id || l.target_id === id), frames = state.frames.filter(f => f.shot_id === id);
    return react_1.default.createElement("aside", { ref: panel, className: "inspector", "aria-label": "Item details" },
        react_1.default.createElement("div", { className: "inspector-top" },
            react_1.default.createElement("span", { className: "eyebrow" }, "Details"),
            react_1.default.createElement("button", { className: "icon-button", onClick: onClose, "aria-label": "Close inspector" },
                react_1.default.createElement(Primitives_1.Icon, { name: "close" }))),
        react_1.default.createElement("div", { className: "inspector-title" },
            react_1.default.createElement(Primitives_1.Badge, { kind: (0, utils_1.kindLabel)(entity) }, (0, utils_1.kindLabel)(entity)),
            !!entity.archived && react_1.default.createElement(Primitives_1.Badge, null, "Archived"),
            react_1.default.createElement("h2", null, entity.kind === 'shot' ? (0, utils_1.displayTitle)(shotTitle(entity)) : (0, utils_1.displayTitle)(entity.title)),
            entity.kind === 'shot' && react_1.default.createElement("span", { className: "shot-code" },
                "Shot ",
                String(entity.fields.number || String(entity.position + 1).padStart(2, '0'))),
            react_1.default.createElement("details", { className: "technical-meta" },
                react_1.default.createElement("summary", null, "Technical details"),
                react_1.default.createElement("small", null,
                    "Internal ID ",
                    id,
                    " \u00B7 saved version ",
                    entity.revision)),
            react_1.default.createElement("button", { className: "full-button", onClick: () => action(entity.kind + '.update', (0, utils_1.commandDefaults)(entity)) },
                react_1.default.createElement(Primitives_1.Icon, { name: "edit" }),
                "Edit ",
                (0, utils_1.kindLabel)(entity).toLowerCase(),
                " details")),
        react_1.default.createElement("div", { className: "tabs", role: "tablist", "aria-label": "Item details sections" }, tabs.map((t, index) => react_1.default.createElement("button", { key: t, id: `${tabPrefix}-tab-${t}`, type: "button", role: "tab", "aria-selected": activeTab === t, "aria-controls": `${tabPrefix}-panel-${t}`, tabIndex: activeTab === t ? 0 : -1, onClick: () => setTab(t), onKeyDown: (event) => moveTab(event, index) }, t === 'shot-intent' ? 'Shot intent' : (0, utils_1.human)(t)))),
        tabs.filter(t => t !== activeTab).map(t => react_1.default.createElement("div", { key: t, hidden: true, role: "tabpanel", id: `${tabPrefix}-panel-${t}`, "aria-labelledby": `${tabPrefix}-tab-${t}`, tabIndex: 0 })),
        react_1.default.createElement("div", { className: "inspector-body", role: "tabpanel", id: `${tabPrefix}-panel-${activeTab}`, "aria-labelledby": `${tabPrefix}-tab-${activeTab}`, tabIndex: 0 },
            activeTab === 'details' && react_1.default.createElement(react_1.default.Fragment, null,
                entity.kind === 'shot' ? react_1.default.createElement(ShotDetails, { entity: entity, state: state }) : react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("p", { className: "prose" }, entity.description || 'No description yet.'),
                    Object.entries(entity.fields).filter(([k, v]) => v !== null && v !== '' && k !== 'type').map(([key, value]) => react_1.default.createElement("section", { className: "detail-field", key: key },
                        react_1.default.createElement("h4", null, (0, utils_1.human)(key)),
                        react_1.default.createElement("p", { className: "prose" }, key === 'location_id' ? (0, utils_1.displayTitle)(state.entities.find(e => e.id === value)?.title || String(value)) : String(value))))),
                entity.tags.length > 0 && react_1.default.createElement("section", null,
                    react_1.default.createElement("h4", null, "Tags"),
                    react_1.default.createElement("div", { className: "tags" }, entity.tags.map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)))),
                entity.aliases.length > 0 && react_1.default.createElement("section", null,
                    react_1.default.createElement("h4", null, "Also known as"),
                    react_1.default.createElement("p", null, entity.aliases.join(', '))),
                entity.parent_id && react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(entity.parent_id) },
                    "Part of: ",
                    (0, utils_1.displayTitle)(state.entities.find(n => n.id === entity.parent_id)?.title || ''),
                    " \u2192"),
                links.length > 0 && react_1.default.createElement("h4", null, "Connected to"),
                links.map(l => react_1.default.createElement("div", { key: l.id, className: "neighbor-row" },
                    react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(l.source_id === id ? l.target_id : l.source_id) },
                        l.source_id === id ? '→' : '←',
                        " ",
                        state.entities.find(n => n.id === (l.source_id === id ? l.target_id : l.source_id))?.title ? (0, utils_1.displayTitle)(state.entities.find(n => n.id === (l.source_id === id ? l.target_id : l.source_id)).title) : 'Connected item'),
                    react_1.default.createElement("small", null, (0, utils_1.human)(l.relation)),
                    react_1.default.createElement("button", { onClick: () => action('link.remove', (0, utils_1.commandDefaults)(l)) }, "Remove\u2026"))),
                entity.kind === 'asset' && react_1.default.createElement("button", { onClick: () => action('link.create', { source_id: id }) }, "Connect to another library item"),
                ['sequence', 'scene', 'shot'].includes(entity.kind) && react_1.default.createElement("button", { onClick: () => action('story.move', (0, utils_1.commandDefaults)(entity)) }, "Move / reorder\u2026"),
                react_1.default.createElement("details", { className: "record-actions" },
                    react_1.default.createElement("summary", null, "More options"),
                    react_1.default.createElement("p", { className: "muted" }, "Changes affect this item wherever it appears."),
                    react_1.default.createElement("button", { onClick: () => action('entity.usage', { id }) }, "See where it\u2019s used"),
                    react_1.default.createElement("button", { onClick: () => action(entity.archived ? 'entity.restore' : 'entity.archive', (0, utils_1.commandDefaults)(entity)) }, entity.archived ? 'Restore item' : 'Archive item…'),
                    react_1.default.createElement("button", { className: "danger", onClick: () => action('entity.delete', (0, utils_1.commandDefaults)(entity)) }, "Delete item\u2026"),
                    entity.kind === 'asset' && react_1.default.createElement("button", { onClick: () => action('asset.merge', { source_id: id, revision: entity.revision }) }, "Combine with another library item\u2026"))),
            activeTab === 'references' && react_1.default.createElement(react_1.default.Fragment, null,
                entity.kind === 'asset' && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("div", { className: "section-heading" },
                        react_1.default.createElement("h3", null, "Reference images"),
                        react_1.default.createElement("button", { onClick: () => action('asset.attach', { asset_id: id }) }, "Add image")),
                    members.map(m => { const image = state.media.find(media => media.id === m.media_id); return react_1.default.createElement("div", { className: "inspector-image", key: m.id },
                        react_1.default.createElement("a", { href: (0, api_1.originalUrl)(state.project.id, m.media_id), target: "_blank", rel: "noreferrer" },
                            react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, m.media_id), alt: image?.original_name || 'Library image' })),
                        react_1.default.createElement("strong", null, image?.original_name),
                        react_1.default.createElement("small", null,
                            image?.width,
                            " \u00D7 ",
                            image?.height,
                            " \u00B7 ",
                            image?.format?.toUpperCase()),
                        react_1.default.createElement("div", { className: "button-row" },
                            m.is_primary ? react_1.default.createElement(Primitives_1.Badge, null, "Cover image") : react_1.default.createElement("button", { onClick: () => action('asset.primary', (0, utils_1.commandDefaults)(m)) }, "Set as cover image"),
                            react_1.default.createElement("button", { onClick: () => action('asset.detach', (0, utils_1.commandDefaults)(m)) }, "Remove\u2026"))); }),
                    !members.length && react_1.default.createElement("p", { className: "muted" }, "No images here yet. Import one, then add it to this library item.")),
                assignments.length > 0 && react_1.default.createElement("h3", null, entity.kind === 'asset' ? 'Used by shots' : 'References in this shot'),
                assignments.map(a => { const other = state.entities.find(n => n.id === (entity.kind === 'asset' ? a.shot_id : a.asset_id)); return react_1.default.createElement("div", { className: "reference-row", key: a.id },
                    a.media_id && react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, a.media_id, 160), alt: `${(0, utils_1.roleLabel)(a.role)} reference` }),
                    react_1.default.createElement("div", null,
                        react_1.default.createElement("button", { className: "text-button", onClick: () => onSelect(other.id) }, other ? (0, utils_1.displayTitle)(other.title) : 'Library item'),
                        react_1.default.createElement("small", null,
                            (0, utils_1.roleLabel)(a.role),
                            " \u00B7 ",
                            a.media_id ? 'specific image selected' : 'no specific image selected'),
                        react_1.default.createElement("div", { className: "button-row" },
                            react_1.default.createElement("button", { onClick: () => action('assignment.update', { ...(0, utils_1.commandDefaults)(a), asset_id: a.asset_id }) }, "Edit"),
                            react_1.default.createElement("button", { onClick: () => action('assignment.remove', (0, utils_1.commandDefaults)(a)) }, "Remove\u2026")))); }),
                entity.kind === 'shot' && react_1.default.createElement(react_1.default.Fragment, null,
                    react_1.default.createElement("button", { onClick: () => action('assignment.create', { shot_id: id }) }, "Add a reference"),
                    react_1.default.createElement("h3", null, "Storyboard frames"),
                    frames.map(f => react_1.default.createElement("div", { className: "frame-mini", key: f.id },
                        react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(state.project.id, f.media_id), alt: `Storyboard image ${f.version}` }),
                        react_1.default.createElement("span", null,
                            "Image ",
                            f.version),
                        react_1.default.createElement(Primitives_1.Badge, { kind: f.state }, (0, utils_1.statusLabel)(f.state)))),
                    react_1.default.createElement("button", { onClick: () => action('frame.attach', { shot_id: id }) }, "Add storyboard image"))),
            activeTab === 'context' && react_1.default.createElement(react_1.default.Fragment, null,
                error && react_1.default.createElement("div", { role: "alert", className: "notice error" },
                    react_1.default.createElement("strong", null, "Could not load story direction."),
                    react_1.default.createElement("p", null, error),
                    react_1.default.createElement("button", { onClick: () => void loadContext(id, state.project.id) }, "Retry loading direction")),
                contextLoading && !context && !error && react_1.default.createElement("p", { role: "status" }, "Loading story direction\u2026"),
                context && react_1.default.createElement(Primitives_1.ContextView, { value: context }),
                react_1.default.createElement("button", { onClick: () => action('context.put', { owner_id: id }) }, "Add direction note")),
            activeTab === 'shot-intent' && entity.kind === 'shot' && react_1.default.createElement(ShotIntent_1.ShotIntent, { key: id, projectId: state.project.id, shot: entity })));
}

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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.Icon = Icon;
exports.Empty = Empty;
exports.PageHeading = PageHeading;
exports.Badge = Badge;
exports.ErrorNotice = ErrorNotice;
exports.Modal = Modal;
exports.Validation = Validation;
exports.ContextView = ContextView;
exports.ExportLinks = ExportLinks;
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
        close: react_1.default.createElement("path", { d: "m6 6 12 12M18 6 6 18" }),
        chevron: react_1.default.createElement("path", { d: "m9 5 7 7-7 7" }),
        search: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("circle", { cx: "10", cy: "10", r: "6" }),
            react_1.default.createElement("path", { d: "m15 15 6 6" })),
        check: react_1.default.createElement("path", { d: "m4 12 5 5L20 6" }),
        warning: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("circle", { cx: "12", cy: "12", r: "9" }),
            react_1.default.createElement("path", { d: "M12 7v6m0 4h.01" })),
        stop: react_1.default.createElement("rect", { x: "5", y: "5", width: "14", height: "14", rx: "2" }),
        arrow: react_1.default.createElement("path", { d: "M3 12h18m-7-7 7 7-7 7" }),
        refresh: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("path", { d: "M20 8a8 8 0 1 0 1 7M20 3v5h-5" })),
        menu: react_1.default.createElement("path", { d: "M3 5h18M3 12h18M3 19h18" }),
    };
    return react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true" }, paths[name] || paths.grid);
}
function Empty({ title, children, action }) { return react_1.default.createElement("div", { className: "empty" },
    react_1.default.createElement("span", { className: "empty-mark" },
        react_1.default.createElement(Icon, { name: "outline", size: 28 })),
    react_1.default.createElement("h3", null, title),
    react_1.default.createElement("p", null, children),
    action); }
function PageHeading({ eyebrow, title, description, actions }) { return react_1.default.createElement("header", { className: "page-heading" },
    react_1.default.createElement("div", null,
        react_1.default.createElement("p", { className: "eyebrow" }, eyebrow),
        react_1.default.createElement("h1", null, title),
        description && react_1.default.createElement("p", { className: "lede" }, description)),
    actions && react_1.default.createElement("div", { className: "heading-actions" }, actions)); }
function Badge({ kind, children }) { return react_1.default.createElement("span", { className: `badge ${kind || ''}` }, children); }
function ErrorNotice({ error, children }) { return react_1.default.createElement("div", { className: "notice error", role: "alert" },
    react_1.default.createElement("strong", null, "We couldn\u2019t complete that."),
    react_1.default.createElement("p", null, error),
    children); }
function Modal({ title, children, onClose, wide = false, returnFocusSelector }) {
    const dialog = (0, react_1.useRef)(null);
    const closeRef = (0, react_1.useRef)(onClose);
    closeRef.current = onClose;
    // Capture the opener during render: React may already have applied an input's
    // autoFocus prop by the time this component's passive effect runs.
    const opener = (0, react_1.useRef)(document.activeElement instanceof HTMLElement ? document.activeElement : null);
    (0, react_1.useEffect)(() => {
        const el = dialog.current;
        const visible = (node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden' && !node.closest('[inert]');
        const focusable = () => Array.from(el?.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]') || []).filter(visible);
        const active = document.activeElement instanceof HTMLElement && el?.contains(document.activeElement) ? document.activeElement : null;
        const requested = el?.querySelector('[autofocus]');
        // Preserve React's native autoFocus result if it focused an element even when
        // the renderer did not leave an [autofocus] attribute in the DOM.
        (requested && visible(requested) ? requested : active && active !== el ? active : focusable()[0] || el)?.focus({ preventScroll: true });
        const handler = (event) => { if (event.key === 'Escape') {
            event.preventDefault();
            closeRef.current();
        } if (event.key === 'Tab') {
            const items = focusable();
            const first = items[0], last = items[items.length - 1];
            if (!items.length) {
                event.preventDefault();
                el?.focus();
            }
            else if (event.shiftKey && (document.activeElement === first || !el?.contains(document.activeElement))) {
                event.preventDefault();
                last?.focus();
            }
            else if (!event.shiftKey && (document.activeElement === last || !el?.contains(document.activeElement))) {
                event.preventDefault();
                first?.focus();
            }
        } };
        el?.addEventListener('keydown', handler);
        return () => { el?.removeEventListener('keydown', handler); const saved = opener.current; const target = saved?.isConnected ? saved : returnFocusSelector ? document.querySelector(returnFocusSelector) : null; if (target?.isConnected && !target.matches(':disabled') && !target.closest('[inert]') && visible(target))
            target.focus({ preventScroll: true }); };
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
function Validation({ issues }) { if (!issues.length)
    return react_1.default.createElement("p", { className: "success-line" },
        react_1.default.createElement(Icon, { name: "check" }),
        " All selected images are available."); return react_1.default.createElement("div", { className: "validation" },
    react_1.default.createElement("h3", null,
        "Production checks ",
        react_1.default.createElement("span", { className: "count" }, issues.length)),
    issues.map((i, n) => react_1.default.createElement("div", { key: `${i.code}-${n}`, className: `check-row ${i.severity}` },
        react_1.default.createElement(Badge, null, (0, utils_1.human)(i.severity)),
        react_1.default.createElement("span", null, i.message)))); }
function ContextView({ value }) { return react_1.default.createElement("div", { className: "context-view" },
    react_1.default.createElement("div", { className: "scope-chain" }, value.chain.map((c, i) => react_1.default.createElement("span", { key: c.id },
        i > 0 && ' / ',
        (0, utils_1.displayTitle)(c.title)))),
    Object.entries(value.scalars).map(([key, entry]) => react_1.default.createElement("div", { className: "context-value", key: key },
        react_1.default.createElement("span", { className: "eyebrow" }, (0, utils_1.human)(key)),
        react_1.default.createElement("strong", null, entry.label || entry.value),
        react_1.default.createElement("small", null,
            (0, utils_1.sourceLabel)(entry.source.kind),
            " \u00B7 ",
            (0, utils_1.displayTitle)(entry.source.title)))),
    Object.entries(value.blocks).map(([key, entries]) => react_1.default.createElement("section", { className: "direction-block", key: key },
        react_1.default.createElement("h4", null, (0, utils_1.human)(key)),
        entries.map((e, i) => react_1.default.createElement("div", { key: e.block_id || `${e.source.id}-${i}` },
            react_1.default.createElement("p", { className: "prose" }, e.text),
            react_1.default.createElement("small", null,
                (0, utils_1.sourceLabel)(e.source.kind),
                " \u00B7 ",
                (0, utils_1.displayTitle)(e.source.title)))))),
    !Object.keys(value.blocks).length && !Object.keys(value.scalars).length && react_1.default.createElement("p", { className: "muted" }, "No direction has been added yet. Add a note here or at a higher story level."),
    value.history.filter(h => h.operation !== 'append').map((h, i) => react_1.default.createElement("p", { className: "context-rule", key: `${h.key}-${i}` },
        react_1.default.createElement(Badge, null, (0, utils_1.operationLabel)(h.operation)),
        " ",
        (0, utils_1.human)(h.key),
        " \u00B7 ",
        (0, utils_1.displayTitle)(h.source.title),
        h.removed_sources.length ? ` · ${h.removed_sources.length} earlier ${h.removed_sources.length === 1 ? 'note was changed' : 'notes were changed'}` : ''))); }
function ExportLinks({ project, result }) { return react_1.default.createElement("div", { className: "export-result" },
    react_1.default.createElement("p", { className: "success-line" },
        react_1.default.createElement(Icon, { name: "check" }),
        " Export saved in your project folder."),
    react_1.default.createElement("code", null, result.path),
    react_1.default.createElement("div", { className: "button-row" },
        result.archive && react_1.default.createElement("a", { className: "button primary", href: (0, api_1.exportUrl)(project, result.archive, true) },
            "Download project package (.zip) ",
            react_1.default.createElement(Icon, { name: "export" })),
        result.view && react_1.default.createElement("a", { className: "button", href: (0, api_1.exportUrl)(project, result.view), target: "_blank", rel: "noreferrer" },
            "Open board ",
            react_1.default.createElement(Icon, { name: "arrow" }))),
    react_1.default.createElement("details", null,
        react_1.default.createElement("summary", null, "Individual files"),
        react_1.default.createElement("div", { className: "file-links" }, result.files?.filter(p => !p.endsWith('.zip')).map(path => react_1.default.createElement("a", { key: path, href: (0, api_1.exportUrl)(project, path, true) }, path.split('/').pop())))),
    result.validation && react_1.default.createElement(Validation, { issues: result.validation })); }

},
"components/ShotIntent":function(require,module,exports){
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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ShotIntent = ShotIntent;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const draftCache = new Map();
const pendingDrafts = new Set();
const draftListeners = new Map();
const dirtyDraftOwners = new Set();
const acceptedRecordEpochs = new Map();
function acceptedRecordEpoch(key) { return acceptedRecordEpochs.get(key) || 0; }
function noteAcceptedRecordWrite(key) { acceptedRecordEpochs.set(key, acceptedRecordEpoch(key) + 1); }
function guardUnsavedUnload(event) { if (!dirtyDraftOwners.size && !pendingDrafts.size)
    return; event.preventDefault(); event.returnValue = ''; }
function updateUnloadGuard() { if (typeof window === 'undefined')
    return; if (dirtyDraftOwners.size || pendingDrafts.size)
    window.addEventListener('beforeunload', guardUnsavedUnload);
else
    window.removeEventListener('beforeunload', guardUnsavedUnload); }
function setDraftDirty(key, dirty) { if (dirty)
    dirtyDraftOwners.add(key);
else
    dirtyDraftOwners.delete(key); updateUnloadGuard(); }
function notifyDraft(key, event, origin) { for (const listener of draftListeners.get(key) || [])
    listener(event, origin); }
function storeDraft(key, entry, origin) { const previous = draftCache.get(key); const accepted = { ...entry, validation: Object.prototype.hasOwnProperty.call(entry, 'validation') ? entry.validation ?? null : previous?.validation ?? null, recoveryBaseRecord: Object.prototype.hasOwnProperty.call(entry, 'recoveryBaseRecord') ? entry.recoveryBaseRecord ?? null : previous?.recoveryBaseRecord ?? null }; draftCache.set(key, accepted); setDraftDirty(key, JSON.stringify(accepted.baseRecord?.contract || emptyBody()) !== JSON.stringify(accepted.body)); notifyDraft(key, { entry: accepted, pending: pendingDrafts.has(key) }, origin); }
function setDraftPending(key, pending, origin) { if (pending)
    pendingDrafts.add(key);
else
    pendingDrafts.delete(key); updateUnloadGuard(); notifyDraft(key, { pending }, origin); }
const emptyBody = () => ({ schema: 'storyboarder.observation-contract/v1', source_pins: [], script_intents: [], requirements: [], references: [], continuity: [], notes: '' });
const copy = (value) => JSON.parse(JSON.stringify(value));
async function showAndValidateRecord(projectId, initial, active = () => true) {
    let record = initial;
    for (let attempt = 0; attempt < 2; attempt++) {
        if (!active())
            return { record, validation: null, unstable: false, stopped: true };
        const validation = await (0, api_1.runCommand)(projectId, 'observation.validate', { contract_id: record.id, version_id: record.selected_version_id });
        if (!active())
            return { record, validation: null, unstable: false, stopped: true };
        const tupleMatches = validation.revision === record.revision && validation.version_id === record.selected_version_id;
        if (tupleMatches)
            return { record, validation, unstable: false, stopped: false };
        if (attempt === 1)
            return { record, validation: null, unstable: true, stopped: false };
        record = await (0, api_1.runCommand)(projectId, 'observation.show', { contract_id: record.id });
        if (!active())
            return { record, validation: null, unstable: false, stopped: true };
    }
    return { record, validation: null, unstable: true, stopped: false };
}
function recordValidation(record) { return { ...record.validation, revision: record.revision, version_id: record.selected_version_id }; }
function listItem(record, shotTitle) { return { id: record.id, shot_id: record.shot_id, current_version_id: record.current_version_id, revision: record.revision, shot_title: shotTitle, version_number: record.version.number }; }
function stableId() { const bytes = new Uint8Array(16); crypto.getRandomValues(bytes); bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128; const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join(''); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
function sourceScope(row) { return row.inherited ? 'scene-context' : 'direct-element'; }
function sourceName(row, details) { const kind = details?.nodeType || row.node_type; const title = details?.nodeTitle || row.title; return `${row.inherited ? 'Scene context' : 'Direct shot link'} · ${kind === 'scene' ? 'Scene node' : kind} · ${title || 'Untitled source'}`; }
function readablePath(path) { return path.replace(/^\//, '').split('/').map(part => part.replace(/_id$/, ' ID').replace(/_/g, ' ')).join(' · '); }
function displayValue(value) { if (value && typeof value === 'object')
    return JSON.stringify(value); if (value === undefined)
    return 'Not present'; return String(value); }
function contractBodyChanges(before, after) {
    const changes = [];
    const stableArrayKey = (value) => { if (!value || typeof value !== 'object' || Array.isArray(value))
        return null; const row = value; const key = typeof row.id === 'string' ? row.id : typeof row.edge_id === 'string' ? row.edge_id : null; return key ? `${typeof row.id === 'string' ? 'id' : 'edge_id'}=${key}` : null; };
    const visit = (left, right, path) => {
        if (Object.is(left, right))
            return;
        if (Array.isArray(left) && Array.isArray(right)) {
            const leftKeys = left.map(stableArrayKey), rightKeys = right.map(stableArrayKey);
            if (leftKeys.every(Boolean) && rightKeys.every(Boolean)) {
                const leftByKey = new Map(left.map((value, index) => [leftKeys[index], value]));
                const rightByKey = new Map(right.map((value, index) => [rightKeys[index], value]));
                for (const key of Array.from(new Set([...leftByKey.keys(), ...rightByKey.keys()])).sort())
                    visit(leftByKey.get(key), rightByKey.get(key), `${path}/${key}`);
            }
            else {
                for (let index = 0; index < Math.max(left.length, right.length); index++)
                    visit(left[index], right[index], `${path}/${index}`);
            }
            return;
        }
        if (left && right && typeof left === 'object' && typeof right === 'object' && !Array.isArray(left) && !Array.isArray(right)) {
            const leftRow = left, rightRow = right;
            for (const key of Array.from(new Set([...Object.keys(leftRow), ...Object.keys(rightRow)])).sort())
                visit(leftRow[key], rightRow[key], `${path}/${key}`);
            return;
        }
        changes.push({ path: path || '/contract', before: left, after: right });
    };
    visit(before, after, '/contract');
    return changes;
}
function ShotIntent({ projectId, shot }) {
    const ownerKey = `${projectId}:${shot.id}`;
    const instance = (0, react_1.useRef)({});
    const [sources, setSources] = (0, react_1.useState)([]), [sourceDetails, setSourceDetails] = (0, react_1.useState)({});
    const [items, setItems] = (0, react_1.useState)([]), [selectedContract, setSelectedContract] = (0, react_1.useState)('');
    const [saved, setSaved] = (0, react_1.useState)(null), [latest, setLatest] = (0, react_1.useState)(null), [draft, setDraft] = (0, react_1.useState)(emptyBody);
    const [validation, setValidation] = (0, react_1.useState)(null), [remoteDiff, setRemoteDiff] = (0, react_1.useState)(null), [historyDiff, setHistoryDiff] = (0, react_1.useState)(null), [recoveryBaseRecord, setRecoveryBaseRecord] = (0, react_1.useState)(null);
    const [review, setReview] = (0, react_1.useState)(null), [reviewGeneration, setReviewGeneration] = (0, react_1.useState)(-1), [retargetPreview, setRetargetPreview] = (0, react_1.useState)(null);
    const [loading, setLoading] = (0, react_1.useState)(true), [refreshing, setRefreshing] = (0, react_1.useState)(false), [busy, setBusy] = (0, react_1.useState)(false), [ownerPending, setOwnerPending] = (0, react_1.useState)(pendingDrafts.has(ownerKey)), [error, setError] = (0, react_1.useState)(''), [sourceError, setSourceError] = (0, react_1.useState)(''), [notice, setNotice] = (0, react_1.useState)(''), [ready, setReady] = (0, react_1.useState)(false), [conflicted, setConflicted] = (0, react_1.useState)(false), [rebaseNeedsReview, setRebaseNeedsReview] = (0, react_1.useState)(false);
    const editGeneration = (0, react_1.useRef)(0), loadSequence = (0, react_1.useRef)(0), initialShotRevision = (0, react_1.useRef)(shot.revision), [latestShotRevision, setLatestShotRevision] = (0, react_1.useState)(shot.revision);
    const dirty = !!saved ? JSON.stringify(saved.contract) !== JSON.stringify(draft) : JSON.stringify(emptyBody()) !== JSON.stringify(draft);
    async function hydrateSources(rows, active) {
        if (active())
            setSources(rows);
        const documents = Array.from(new Set(rows.map(row => row.document_id)));
        const documentDetails = {};
        await Promise.all(documents.map(async (documentId) => {
            const [documentResult, versionsResult] = await Promise.allSettled([
                (0, api_1.runCommand)(projectId, 'document.show', { id: documentId }),
                (0, api_1.runCommand)(projectId, 'document.versions', { document_id: documentId, limit: 100, offset: 0 }),
            ]);
            documentDetails[documentId] = { document: documentResult.status === 'fulfilled' ? documentResult.value : null, versions: versionsResult.status === 'fulfilled' ? versionsResult.value?.items || [] : [], failed: documentResult.status === 'rejected' || versionsResult.status === 'rejected' };
        }));
        const next = {};
        await Promise.all(rows.map(async (row) => {
            const nodeResult = await Promise.allSettled([(0, api_1.runCommand)(projectId, 'document.node', { id: row.node_id })]);
            const node = nodeResult[0].status === 'fulfilled' ? nodeResult[0].value : null;
            const parent = documentDetails[row.document_id];
            const version = parent?.versions.find((entry) => entry.id === row.version_id);
            next[row.edge_id] = { documentTitle: parent?.document?.title, versionNumber: version?.number, versionLabel: version?.label || row.version_label, nodeTitle: node?.title || row.title, nodeType: node?.node_type || row.node_type, currentVersionId: parent?.document?.current_version_id || row.current_version_id, contentSha256: node?.content_sha256 || row.content_sha256,
                error: parent?.failed || nodeResult[0].status === 'rejected' ? 'Some exact source details could not be loaded.' : '' };
        }));
        if (active())
            setSourceDetails(old => ({ ...old, ...next }));
        if (documents.length && active())
            setSourceError('');
    }
    async function initialLoad() {
        const sequence = ++loadSequence.current, acceptedEpoch = acceptedRecordEpoch(ownerKey);
        const stillCurrent = () => loadSequence.current === sequence && acceptedRecordEpoch(ownerKey) === acceptedEpoch;
        const stopStaleLoad = () => { if (loadSequence.current === sequence) {
            setReady(true);
            setLoading(false);
        } };
        const cachedAtStart = draftCache.get(ownerKey);
        editGeneration.current = cachedAtStart?.generation || 0;
        initialShotRevision.current = cachedAtStart?.shotRevision ?? shot.revision;
        setLatestShotRevision(shot.revision);
        setOwnerPending(pendingDrafts.has(ownerKey));
        setRecoveryBaseRecord(cachedAtStart?.recoveryBaseRecord || null);
        setLoading(true);
        setReady(false);
        setError('');
        setSourceError('');
        setNotice('');
        setSaved(null);
        setLatest(null);
        setValidation(null);
        setDraft(copy(cachedAtStart?.body || emptyBody()));
        setItems([]);
        setSelectedContract('');
        setReview(null);
        setRemoteDiff(null);
        setHistoryDiff(null);
        setConflicted(false);
        setRebaseNeedsReview(false);
        const [sourceResult, listResult] = await Promise.allSettled([
            (0, api_1.runCommand)(projectId, 'shot.sources', { id: shot.id }),
            (0, api_1.runCommand)(projectId, 'observation.list', { shot_id: shot.id, limit: 100, offset: 0 }),
        ]);
        if (!stillCurrent()) {
            stopStaleLoad();
            return;
        }
        if (sourceResult.status === 'fulfilled')
            void hydrateSources(sourceResult.value.items || [], () => loadSequence.current === sequence);
        else
            setSourceError(messageOf(sourceResult.reason));
        if (listResult.status === 'rejected') {
            setError(messageOf(listResult.reason));
            setLoading(false);
            return;
        }
        const rows = listResult.value.items || [];
        setItems(rows);
        setReady(true);
        const cached = draftCache.get(ownerKey);
        const first = rows.find(item => item.id === cached?.baseRecord?.id) || rows[0];
        if (!first) {
            const cached = draftCache.get(ownerKey);
            setSaved(null);
            setLatest(null);
            setSelectedContract('');
            setDraft(copy(cached?.body || emptyBody()));
            setValidation(null);
            setConflicted(false);
            setRecoveryBaseRecord(null);
            setLoading(false);
            if (cached)
                storeDraft(ownerKey, { ...cached, body: copy(cached.body), baseRecord: null, latestRecord: null, validation: null, recoveryBaseRecord: null }, instance.current);
            return;
        }
        setSelectedContract(first.id);
        try {
            const shown = await (0, api_1.runCommand)(projectId, 'observation.show', { contract_id: first.id });
            if (!stillCurrent())
                return;
            const read = await showAndValidateRecord(projectId, shown, stillCurrent);
            if (read.stopped || !stillCurrent())
                return;
            const record = read.record, checked = read.validation;
            const acceptedItem = listItem(record, shot.title);
            setItems(old => old.some(item => item.id === record.id) ? old.map(item => item.id === record.id ? acceptedItem : item) : [acceptedItem, ...old]);
            setSelectedContract(record.id);
            const cached = draftCache.get(ownerKey);
            if (cached) {
                const base = cached.baseRecord;
                const pendingOwnCreate = !cached.baseRecord && pendingDrafts.has(ownerKey);
                const hasExternal = (!cached.baseRecord && !pendingOwnCreate) || !!cached.baseRecord && (cached.baseRecord.revision !== record.revision || cached.baseRecord.current_version_id !== record.current_version_id);
                const conflict = hasExternal || cached.conflicted || read.unstable;
                setSaved(base);
                setLatest(record);
                setDraft(copy(cached.body));
                setValidation(checked);
                setConflicted(conflict);
                let difference = null;
                if (cached.baseRecord && hasExternal) {
                    try {
                        difference = await (0, api_1.runCommand)(projectId, 'observation.diff', { contract_id: record.id, before_version_id: cached.baseRecord.current_version_id, after_version_id: record.current_version_id });
                    }
                    catch (reason) {
                        if (stillCurrent())
                            setError(messageOf(reason));
                    }
                }
                if (!stillCurrent())
                    return;
                setRemoteDiff(difference);
                storeDraft(ownerKey, { ...cached, baseRecord: base, latestRecord: record, conflicted: conflict, validation: checked }, instance.current);
                if (read.unstable)
                    setNotice('The saved contract changed while validation was running. No mismatched validation is shown; your local draft and exact pins are retained. Refresh status before saving.');
            }
            else {
                setSaved(record);
                setLatest(record);
                setDraft(copy(record.contract));
                setValidation(checked);
                setConflicted(read.unstable);
                storeDraft(ownerKey, { body: copy(record.contract), baseRecord: record, latestRecord: record, shotRevision: initialShotRevision.current, generation: editGeneration.current, conflicted: read.unstable, validation: checked }, instance.current);
                if (read.unstable)
                    setNotice('The saved contract changed while validation was running. No mismatched validation is shown. Refresh status before saving.');
            }
        }
        catch (reason) {
            if (stillCurrent())
                setError(messageOf(reason));
        }
        finally {
            if (loadSequence.current === sequence)
                setLoading(false);
        }
    }
    (0, react_1.useEffect)(() => {
        let listeners = draftListeners.get(ownerKey);
        if (!listeners) {
            listeners = new Set();
            draftListeners.set(ownerKey, listeners);
        }
        const listener = (event, origin) => { if (origin === instance.current)
            return; setOwnerPending(event.pending); if (event.entry) {
            editGeneration.current = event.entry.generation;
            initialShotRevision.current = event.entry.shotRevision;
            setDraft(copy(event.entry.body));
            setSaved(event.entry.baseRecord);
            setLatest(event.entry.latestRecord);
            setConflicted(event.entry.conflicted);
            setValidation(event.entry.validation || null);
            setRecoveryBaseRecord(event.entry.recoveryBaseRecord || null);
            const record = event.entry.latestRecord || event.entry.baseRecord;
            if (record) {
                const item = listItem(record, shot.title);
                setItems(old => old.some(row => row.id === record.id) ? old.map(row => row.id === record.id ? item : row) : [item, ...old]);
                setSelectedContract(record.id);
            }
        } };
        listeners.add(listener);
        setOwnerPending(pendingDrafts.has(ownerKey));
        void initialLoad();
        return () => { listeners?.delete(listener); if (!listeners?.size)
            draftListeners.delete(ownerKey); loadSequence.current += 1; };
    }, [projectId, shot.id]);
    function changeDraft(next) { editGeneration.current += 1; setDraft(next); storeDraft(ownerKey, { body: copy(next), baseRecord: saved, latestRecord: latest, shotRevision: initialShotRevision.current, generation: editGeneration.current, conflicted, validation }, instance.current); setReview(null); setReviewGeneration(-1); setHistoryDiff(null); setNotice(''); }
    function patchDraft(update) { changeDraft(update(draft)); }
    function patchIntent(id, update) { patchDraft(body => ({ ...body, script_intents: body.script_intents.map(item => item.id === id ? update(item) : item) })); }
    function patchRequirement(id, update) { patchDraft(body => ({ ...body, requirements: body.requirements.map(item => item.id === id ? update(item) : item) })); }
    function addIntent() { if (!draft.source_pins.length) {
        setNotice('Select an exact linked screenplay source before adding its purpose.');
        return;
    } const pin = draft.source_pins[0]; patchDraft(body => ({ ...body, script_intents: [...body.script_intents, { id: stableId(), source_edge_id: pin.edge_id, source_scope: pin.source_scope, purpose: '', communication: '', basis: 'unknown' }] })); }
    function addRequirement() { patchDraft(body => ({ ...body, requirements: [...body.requirements, { id: stableId(), priority: 'must', basis: 'unknown', source_edge_ids: draft.source_pins.slice(0, 1).map(pin => pin.edge_id), statement: '', topic: null }] })); }
    function togglePin(row, selected) {
        const edge = row.edge_id;
        if (!selected) {
            const used = draft.script_intents.some(item => item.source_edge_id === edge) || draft.requirements.some(item => item.source_edge_ids.includes(edge));
            if (used) {
                setNotice('Remove or retarget the purpose and requirements that use this source before unpinning it.');
                return;
            }
        }
        patchDraft(body => ({ ...body, source_pins: selected ? [...body.source_pins, { edge_id: edge, source_scope: sourceScope(row) }] : body.source_pins.filter(pin => pin.edge_id !== edge) }));
    }
    function previewRetarget(oldEdgeId, newEdgeId) { const target = sourceByEdge.get(newEdgeId); if (!target || target.stale || oldEdgeId === newEdgeId)
        return; setRetargetPreview({ oldEdgeId, newEdgeId }); }
    function confirmRetarget() { if (!retargetPreview)
        return; const { oldEdgeId, newEdgeId } = retargetPreview; const target = sourceByEdge.get(newEdgeId); if (!target || target.stale)
        return; const scope = sourceScope(target); patchDraft(body => ({ ...body, source_pins: body.source_pins.some(pin => pin.edge_id === newEdgeId) ? body.source_pins.filter(pin => pin.edge_id !== oldEdgeId) : body.source_pins.map(pin => pin.edge_id === oldEdgeId ? { edge_id: newEdgeId, source_scope: scope } : pin), script_intents: body.script_intents.map(item => item.source_edge_id === oldEdgeId ? { ...item, source_edge_id: newEdgeId, source_scope: scope } : item), requirements: body.requirements.map(item => ({ ...item, source_edge_ids: Array.from(new Set(item.source_edge_ids.map(edge => edge === oldEdgeId ? newEdgeId : edge))) })) })); setRetargetPreview(null); }
    async function refreshStatus(fromConflict = false) {
        const sequence = ++loadSequence.current;
        setRefreshing(true);
        setError('');
        setNotice(fromConflict ? 'The write conflicted. Refreshing the saved record while keeping your draft…' : 'Refreshing saved status and exact linked sources…');
        try {
            const [sourceRows, list, projectState] = await Promise.all([
                (0, api_1.runCommand)(projectId, 'shot.sources', { id: shot.id }),
                (0, api_1.runCommand)(projectId, 'observation.list', { shot_id: shot.id, limit: 100, offset: 0 }),
                (0, api_1.api)((0, api_1.projectPath)(projectId, '/state')),
            ]);
            const rows = sourceRows.items || [];
            if (loadSequence.current !== sequence)
                return;
            setSources(rows);
            void hydrateSources(rows, () => loadSequence.current === sequence);
            setItems(list.items || []);
            const refreshedShot = projectState.entities.find(entity => entity.id === shot.id);
            const observedShotRevision = refreshedShot?.revision ?? shot.revision;
            setLatestShotRevision(observedShotRevision);
            const candidate = (list.items || []).find(item => item.id === selectedContract) || (list.items || [])[0];
            if (!candidate) {
                if (loadSequence.current !== sequence)
                    return;
                const cached = draftCache.get(ownerKey);
                const hasConflict = !!saved || observedShotRevision !== initialShotRevision.current;
                setLatest(null);
                setValidation(null);
                setRemoteDiff(null);
                setConflicted(hasConflict);
                setRecoveryBaseRecord(null);
                storeDraft(ownerKey, { body: copy(cached?.body || draft), baseRecord: cached ? cached.baseRecord : saved, latestRecord: null, shotRevision: cached?.shotRevision ?? initialShotRevision.current, generation: cached?.generation ?? editGeneration.current, conflicted: hasConflict, validation: null, recoveryBaseRecord: null }, instance.current);
                setNotice(saved ? 'The saved contract is no longer listed. Your draft and exact pins remain here.' : 'Linked sources refreshed. Your selected exact pins were left unchanged.');
                return;
            }
            const shown = await (0, api_1.runCommand)(projectId, 'observation.show', { contract_id: candidate.id });
            const read = await showAndValidateRecord(projectId, shown, () => loadSequence.current === sequence);
            if (read.stopped || loadSequence.current !== sequence)
                return;
            const record = read.record, checked = read.validation;
            const acceptedItem = listItem(record, shot.title);
            setItems(old => old.some(item => item.id === record.id) ? old.map(item => item.id === record.id ? acceptedItem : item) : [acceptedItem, ...old]);
            setLatest(record);
            setValidation(checked);
            setSelectedContract(record.id);
            const hasExternalChange = read.unstable || !saved || saved.revision !== record.revision || saved.current_version_id !== record.current_version_id;
            setConflicted(hasExternalChange);
            if (read.unstable) {
                setRemoteDiff(null);
                setNotice('The latest saved header could not be matched to a validation result after one retry. Your draft and exact source pins are retained; validation is not checked. Refresh status to try again.');
            }
            else if (hasExternalChange) {
                if (saved) {
                    const difference = await (0, api_1.runCommand)(projectId, 'observation.diff', { contract_id: candidate.id, before_version_id: saved.current_version_id, after_version_id: record.current_version_id });
                    if (loadSequence.current !== sequence)
                        return;
                    setRemoteDiff(difference);
                }
                setNotice(saved ? 'A newer saved revision is available. Your editor draft and exact source pins were kept unchanged. Compare it or explicitly load it.' : 'A contract now exists for this shot. Your create draft and exact pins are retained; compare the saved record before choosing how to continue.');
            }
            else {
                setRemoteDiff(null);
                setNotice(fromConflict ? 'The current saved revision is loaded for comparison. Your draft is unchanged.' : 'Status refreshed. Your draft and exact source pins were unchanged.');
            }
            const cached = draftCache.get(ownerKey);
            storeDraft(ownerKey, { body: copy(cached?.body || draft), baseRecord: cached ? cached.baseRecord : saved, latestRecord: record, shotRevision: cached?.shotRevision ?? initialShotRevision.current, generation: cached?.generation ?? editGeneration.current, conflicted: hasExternalChange, validation: checked }, instance.current);
        }
        catch (reason) {
            setError(messageOf(reason));
        }
        finally {
            setRefreshing(false);
        }
    }
    function loadLatestIntoDraft() {
        if (!latest)
            return;
        setSaved(latest);
        setDraft(copy(latest.contract));
        setValidation(validation);
        setConflicted(false);
        setRemoteDiff(null);
        setReview(null);
        setRecoveryBaseRecord(null);
        editGeneration.current += 1;
        storeDraft(ownerKey, { body: copy(latest.contract), baseRecord: latest, latestRecord: latest, shotRevision: initialShotRevision.current, generation: editGeneration.current, conflicted: false, validation, recoveryBaseRecord: null }, instance.current);
        setNotice(`Draft replaced with saved contract revision ${latest.revision}.`);
        setError('');
    }
    function keepDraftOnExistingContract() {
        if (!latest || saved || latest.shot_id !== shot.id || !validation || validation.revision !== latest.revision || validation.version_id !== latest.selected_version_id || busy || ownerPending)
            return;
        const record = latest;
        setSelectedContract(record.id);
        setSaved(record);
        setLatest(record);
        setValidation(validation);
        setConflicted(false);
        setRemoteDiff(null);
        setReview(null);
        setRecoveryBaseRecord(record);
        storeDraft(ownerKey, { body: copy(draft), baseRecord: record, latestRecord: record, shotRevision: initialShotRevision.current, generation: editGeneration.current, conflicted: false, validation, recoveryBaseRecord: record }, instance.current);
        setNotice(JSON.stringify(record.contract) === JSON.stringify(draft) ? `Your draft already matches contract ${record.id}, revision ${record.revision}. It is saved; no second contract or revision is needed.` : `Your draft and exact pins are preserved on contract ${record.id}, revision ${record.revision}. Compare the saved values below. Save draft will create a new revision on this contract, not a second contract.`);
        setError('');
    }
    function useLatestShotRevision() { initialShotRevision.current = latestShotRevision; setConflicted(false); setRecoveryBaseRecord(null); storeDraft(ownerKey, { body: copy(draft), baseRecord: saved, latestRecord: latest, shotRevision: latestShotRevision, generation: editGeneration.current, conflicted: false, validation, recoveryBaseRecord: null }, instance.current); setNotice(`Create will use the refreshed shot revision ${latestShotRevision}. Your draft and exact pins are unchanged.`); setError(''); }
    async function loadContract(id) {
        if (id === selectedContract || !id)
            return;
        if (dirty && !window.confirm('Discard this local shot intent draft and open the selected contract?'))
            return;
        setLoading(true);
        setError('');
        setNotice('');
        setReview(null);
        setRemoteDiff(null);
        setConflicted(false);
        setRecoveryBaseRecord(null);
        try {
            const shown = await (0, api_1.runCommand)(projectId, 'observation.show', { contract_id: id });
            const read = await showAndValidateRecord(projectId, shown);
            const record = read.record;
            const acceptedItem = listItem(record, shot.title);
            setItems(old => old.some(item => item.id === record.id) ? old.map(item => item.id === record.id ? acceptedItem : item) : [acceptedItem, ...old]);
            setSaved(record);
            setLatest(record);
            setDraft(copy(record.contract));
            setValidation(read.validation);
            setConflicted(read.unstable);
            setSelectedContract(id);
            editGeneration.current += 1;
            storeDraft(ownerKey, { body: copy(record.contract), baseRecord: record, latestRecord: record, shotRevision: initialShotRevision.current, generation: editGeneration.current, conflicted: read.unstable, validation: read.validation, recoveryBaseRecord: null }, instance.current);
            if (read.unstable)
                setNotice('The latest saved header could not be matched to a validation result after one retry. No validation status is shown. Refresh status before saving.');
        }
        catch (reason) {
            setError(messageOf(reason));
        }
        finally {
            setLoading(false);
        }
    }
    async function submit(operation) {
        if (busy || pendingDrafts.has(ownerKey))
            return;
        const generation = editGeneration.current, body = copy(draft), shotRevision = initialShotRevision.current;
        setBusy(true);
        setOwnerPending(true);
        setDraftPending(ownerKey, true, instance.current);
        setError('');
        setNotice('');
        try {
            let record;
            if (operation === 'create')
                record = await (0, api_1.runCommand)(projectId, 'observation.create', { shot_id: shot.id, expected_shot_revision: initialShotRevision.current, contract: body });
            else if (operation === 'rebase') {
                if (!review || reviewGeneration !== generation)
                    throw new Error('Review this exact draft again before rebasing.');
                record = await (0, api_1.runCommand)(projectId, 'observation.rebase', { contract_id: saved.id, revision: review.revision, contract: body, expected_basis_sha256: review.expected_basis_sha256 });
            }
            else
                record = await (0, api_1.runCommand)(projectId, 'observation.revise', { contract_id: saved.id, revision: saved.revision, contract: body });
            noteAcceptedRecordWrite(ownerKey);
            const acceptedItem = listItem(record, shot.title);
            setItems(old => old.some(item => item.id === record.id) ? old.map(item => item.id === record.id ? acceptedItem : item) : [acceptedItem, ...old]);
            const accepted = recordValidation(record);
            setSelectedContract(record.id);
            setSaved(record);
            setLatest(record);
            setValidation(accepted);
            setConflicted(false);
            setRemoteDiff(null);
            setReview(null);
            setReviewGeneration(-1);
            setRecoveryBaseRecord(null);
            const cached = draftCache.get(ownerKey);
            const newer = cached && cached.generation !== generation;
            const nextBody = newer ? copy(cached.body) : copy(record.contract);
            const nextGeneration = newer ? cached.generation : generation;
            editGeneration.current = nextGeneration;
            setDraft(nextBody);
            storeDraft(ownerKey, { body: nextBody, baseRecord: record, latestRecord: record, shotRevision, generation: nextGeneration, conflicted: false, validation: accepted, recoveryBaseRecord: null }, instance.current);
            if (!newer) {
                setNotice(`Shot intent saved as contract revision ${record.revision}.`);
            }
            else
                setNotice('The submitted version was saved. Newer edits remain in the editor.');
        }
        catch (reason) {
            setError(messageOf(reason));
            if (reason?.status === 409 || reason?.code === 'contract_rebase_required') {
                setReview(null);
                setReviewGeneration(-1);
                setConflicted(true);
                const cached = draftCache.get(ownerKey);
                storeDraft(ownerKey, { body: copy(cached?.body || draft), baseRecord: saved, latestRecord: latest, shotRevision: initialShotRevision.current, generation: cached?.generation ?? generation, conflicted: true }, instance.current);
                if (operation === 'rebase' || reason?.code === 'contract_rebase_required')
                    setRebaseNeedsReview(true);
                await refreshStatus(true);
            }
        }
        finally {
            setBusy(false);
            setOwnerPending(false);
            setDraftPending(ownerKey, false, instance.current);
        }
    }
    async function reviewRebase() {
        if (!saved || busy)
            return;
        const generation = editGeneration.current;
        setError('');
        setNotice('Reviewing the exact proposed contract against the current saved basis…');
        setReview(null);
        try {
            const result = await (0, api_1.runCommand)(projectId, 'observation.rebase-preview', { contract_id: saved.id, contract: copy(draft) });
            if (editGeneration.current !== generation) {
                setNotice('The proposed contract changed during review. Review the current draft again.');
                return;
            }
            setReview(result);
            setReviewGeneration(generation);
            setRebaseNeedsReview(false);
            setNotice('Review complete. Confirm the rebase only if these exact changes and source pins are intended.');
        }
        catch (reason) {
            setError(messageOf(reason));
        }
    }
    async function compareVersion(versionId) {
        if (!saved)
            return;
        try {
            const result = await (0, api_1.runCommand)(projectId, 'observation.diff', { contract_id: saved.id, before_version_id: versionId, after_version_id: saved.current_version_id });
            setHistoryDiff(result);
        }
        catch (reason) {
            setError(messageOf(reason));
        }
    }
    const sourceByEdge = new Map(sources.map(row => [row.edge_id, row]));
    const validationStatus = validation?.status || 'not checked';
    const validationRevision = validation?.revision ?? latest?.revision ?? saved?.revision;
    const draftNeedsValidationDisclaimer = dirty || conflicted;
    const validationLabel = draftNeedsValidationDisclaimer ? `Saved revision ${validationRevision} validation: ${validationStatus}` : `Current saved revision ${validationRevision}: ${validationStatus}`;
    const validationScope = draftNeedsValidationDisclaimer ? `This status covers saved revision ${validationRevision} only; the current local draft has not been checked.` : 'This status covers the current saved contract revision.';
    const latestCanBeRecoveryBase = !!latest && latest.shot_id === shot.id && !!validation && validation.revision === latest.revision && validation.version_id === latest.selected_version_id;
    const recoveryBaseline = recoveryBaseRecord && saved?.id === recoveryBaseRecord.id ? recoveryBaseRecord : null;
    const missingSourcePins = draft.source_pins.filter(pin => !sourceByEdge.has(pin.edge_id) || !!validation?.source_pins?.find(item => item.edge_id === pin.edge_id && item.stale));
    const canSubmit = ready && !busy && !ownerPending && !loading && !refreshing && !!draft.script_intents.length && draft.source_pins.length > 0;
    return react_1.default.createElement("section", { className: "shot-intent-panel", "aria-label": "Shot intent contract" },
        react_1.default.createElement("div", { className: "shot-intent-heading" },
            react_1.default.createElement("div", null,
                react_1.default.createElement("h3", null, "Shot intent"),
                react_1.default.createElement("p", { className: "muted" }, "Record what the screenplay asks this shot to communicate. Pins name exact source links; validation does not judge rendered images."),
                react_1.default.createElement("p", { className: "shot-intent-draft-scope" }, "Unsaved edits stay in this open app session and follow this shot across tabs and shots. Create, Save draft, or confirm rebase to store them. Reloading or closing the app will prompt while edits remain unsaved.")),
            react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: loading || refreshing || busy || ownerPending }, "Refresh status")),
        ownerPending && react_1.default.createElement("p", { role: "status" }, "A save for this shot is still in progress. Its draft is preserved and editing is paused until it finishes."),
        react_1.default.createElement("label", { className: "field" },
            react_1.default.createElement("span", null, "Observation contract"),
            react_1.default.createElement("select", { "aria-label": "Observation contract", value: selectedContract, onChange: (event) => void loadContract(event.target.value), disabled: loading || busy || ownerPending || items.length < 2 },
                !items.length && react_1.default.createElement("option", { value: "" }, "New contract for this shot"),
                items.map(item => react_1.default.createElement("option", { key: item.id, value: item.id },
                    "Revision ",
                    item.revision,
                    " \u00B7 ",
                    item.id))),
            react_1.default.createElement("small", null,
                "Selected shot: ",
                shot.title,
                " \u00B7 latest shot revision ",
                latestShotRevision,
                !saved ? ` · create will use revision ${initialShotRevision.current}` : ` · contract ${saved.id} · header revision ${saved.revision}`)),
        loading && react_1.default.createElement("p", { role: "status" }, "Loading exact sources and saved contract\u2026"),
        error && react_1.default.createElement("div", { role: "alert", className: "notice error" },
            react_1.default.createElement("strong", null, "Shot intent could not be updated."),
            react_1.default.createElement("p", null, error),
            react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: refreshing || busy || ownerPending }, "Retry refresh")),
        sourceError && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "Linked source details are unavailable."),
            react_1.default.createElement("p", null, sourceError),
            react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: refreshing || busy }, "Retry source refresh")),
        notice && react_1.default.createElement("p", { role: "status", className: "shot-intent-status" }, notice),
        rebaseNeedsReview && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "The reviewed basis changed."),
            react_1.default.createElement("p", null, "Your draft, exact pins, and previous header CAS are retained. The prior review token is invalid. Review the current proposal again before any rebase."),
            react_1.default.createElement("button", { type: "button", onClick: () => void reviewRebase(), disabled: busy || loading }, "Review this draft again")),
        conflicted && !latest && !saved && latestShotRevision !== initialShotRevision.current && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "The selected shot revision changed."),
            react_1.default.createElement("p", null,
                "Create still uses shot revision ",
                initialShotRevision.current,
                "; the latest saved shot revision is ",
                latestShotRevision,
                ". Your local draft and exact pins are retained."),
            react_1.default.createElement("button", { type: "button", onClick: useLatestShotRevision, disabled: busy },
                "Use shot revision ",
                latestShotRevision,
                " for create")),
        conflicted && latest && !saved && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "A contract already exists for this shot."),
            react_1.default.createElement("p", null,
                "The first-create request conflicted with saved contract ",
                latest.id,
                " at revision ",
                latest.revision,
                ". Your entered content and exact pins are retained. Review the comparison, then explicitly choose this existing contract as the draft base or load its saved content."),
            react_1.default.createElement(DiffView, { title: "Saved contract vs retained create draft", changes: contractBodyChanges(latest.contract, draft), ariaLabel: "Retained draft comparison" }),
            react_1.default.createElement("div", { className: "button-row" },
                react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: refreshing || busy || ownerPending }, "Refresh comparison"),
                react_1.default.createElement("button", { type: "button", onClick: loadLatestIntoDraft, disabled: busy || ownerPending },
                    "Discard draft and load revision ",
                    latest.revision),
                react_1.default.createElement("button", { type: "button", className: "primary", onClick: keepDraftOnExistingContract, disabled: !latestCanBeRecoveryBase || busy || ownerPending }, "Use existing contract and keep my draft"))),
        saved && react_1.default.createElement("div", { className: `notice ${validationStatus === 'consistent' ? '' : 'warning'}` },
            react_1.default.createElement("strong", null, validationLabel),
            react_1.default.createElement("p", null, validationScope),
            react_1.default.createElement("p", null, validation?.findings?.length ? `${validation.findings.length} finding${validation.findings.length === 1 ? '' : 's'} · authored basis ${validation.basis_current ? 'current' : 'changed'}` : 'Deterministic source, identity, and authored-basis checks.'),
            react_1.default.createElement("div", { className: "shot-intent-meta" },
                react_1.default.createElement("span", null,
                    "Contract ID ",
                    react_1.default.createElement("code", null, saved.id)),
                react_1.default.createElement("span", null,
                    "Checked header revision ",
                    react_1.default.createElement("code", null, validation?.revision ?? 'Not checked')),
                react_1.default.createElement("span", null,
                    "Checked version ",
                    react_1.default.createElement("code", null, validation?.version_id || 'Not checked')),
                react_1.default.createElement("span", null,
                    "Editor CAS revision ",
                    react_1.default.createElement("code", null, saved.revision)),
                react_1.default.createElement("span", null,
                    "Draft base version ",
                    react_1.default.createElement("code", null, saved.current_version_id)))),
        conflicted && latest && saved && (latest.revision !== saved.revision || latest.current_version_id !== saved.current_version_id) && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "A newer saved revision is available."),
            react_1.default.createElement("p", null,
                "The editor still uses header revision ",
                saved.revision,
                "; latest is revision ",
                latest.revision,
                ". Your local draft and exact pins are retained."),
            react_1.default.createElement("div", { className: "button-row" },
                react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: refreshing || busy || ownerPending }, "Refresh comparison"),
                react_1.default.createElement("button", { type: "button", onClick: loadLatestIntoDraft, disabled: busy || ownerPending },
                    "Discard draft and load revision ",
                    latest.revision))),
        conflicted && latest && saved && latest.revision === saved.revision && latest.current_version_id === saved.current_version_id && !validation && react_1.default.createElement("div", { role: "alert", className: "notice warning" },
            react_1.default.createElement("strong", null, "The saved header could not be matched to validation."),
            react_1.default.createElement("p", null,
                "No validation status is shown. Your local draft, exact pins, and editor CAS revision ",
                saved.revision,
                " remain unchanged."),
            react_1.default.createElement("button", { type: "button", onClick: () => void refreshStatus(), disabled: refreshing || busy || ownerPending }, "Retry status refresh")),
        recoveryBaseline && react_1.default.createElement(DiffView, { title: "Saved contract vs retained create draft", changes: contractBodyChanges(recoveryBaseline.contract, draft), ariaLabel: "Retained draft comparison" }),
        remoteDiff && react_1.default.createElement(DiffView, { title: "Saved revision changes", changes: remoteDiff.changes.map(change => ({ path: change.path, before: change.before, after: change.after })) }),
        ready && !loading && react_1.default.createElement("fieldset", { className: "shot-intent-fields", disabled: busy || ownerPending },
            react_1.default.createElement("section", { className: "shot-intent-section" },
                react_1.default.createElement("div", { className: "shot-intent-section-heading" },
                    react_1.default.createElement("div", null,
                        react_1.default.createElement("h4", null, "Exact screenplay links"),
                        react_1.default.createElement("p", null, "Select active links already connected to this shot or its scene. Refresh reports changes without replacing these pins."))),
                !sources.length ? react_1.default.createElement("p", { className: "muted" }, "No screenplay source links are connected to this shot yet. Add a link in the source-document workflow, then refresh.") : sources.map(row => {
                    const checked = draft.source_pins.some(pin => pin.edge_id === row.edge_id);
                    const detail = sourceDetails[row.edge_id];
                    const validationPin = validation?.source_pins?.find(pin => pin.edge_id === row.edge_id);
                    const stale = row.stale || !!validationPin?.stale;
                    const stalePins = draft.source_pins.filter(pin => { const previous = sourceByEdge.get(pin.edge_id); const pinned = saved?.source_pins?.find(item => item.edge_id === pin.edge_id); return pin.edge_id !== row.edge_id && (!previous || previous.stale || !!validation?.source_pins?.find(item => item.edge_id === pin.edge_id)?.stale || !!pinned && pinned.source_version_id !== previous.version_id); });
                    return react_1.default.createElement("div", { className: "shot-source-row", key: row.edge_id },
                        react_1.default.createElement("label", { className: "shot-source-option" },
                            react_1.default.createElement("input", { type: "checkbox", checked: checked, onChange: (event) => togglePin(row, event.target.checked) }),
                            react_1.default.createElement("span", null,
                                react_1.default.createElement("strong", null, sourceName(row, detail)),
                                react_1.default.createElement("small", null,
                                    detail?.documentTitle || 'Screenplay',
                                    " \u00B7 ",
                                    detail?.versionLabel || row.version_label,
                                    detail?.versionNumber ? ` (version ${detail.versionNumber})` : '',
                                    stale ? ' · source version is stale' : ''),
                                react_1.default.createElement("small", null,
                                    "Edge ",
                                    react_1.default.createElement("code", null, row.edge_id)),
                                react_1.default.createElement("small", null,
                                    "Version ",
                                    react_1.default.createElement("code", null, row.version_id),
                                    " \u00B7 node ",
                                    react_1.default.createElement("code", null, row.node_id)),
                                react_1.default.createElement("small", null,
                                    "Source SHA-256 ",
                                    react_1.default.createElement("code", null, detail?.contentSha256 || row.content_sha256 || 'Unavailable')),
                                detail?.error && react_1.default.createElement("small", { className: "warning-text" }, detail.error))),
                        stalePins.length > 0 && !checked && !stale && react_1.default.createElement("div", { className: "shot-retarget-shortcuts" }, stalePins.map(pin => { const oldRow = sourceByEdge.get(pin.edge_id); const oldName = oldRow ? sourceName(oldRow, sourceDetails[pin.edge_id]) : `Saved source ${pin.edge_id}`; return react_1.default.createElement("button", { type: "button", key: pin.edge_id, onClick: () => previewRetarget(pin.edge_id, row.edge_id) },
                            "Preview retarget from ",
                            oldName,
                            " to ",
                            sourceName(row, detail)); })));
                }),
                !!draft.source_pins.length && missingSourcePins.map(pin => react_1.default.createElement("div", { className: "shot-source-stale", key: pin.edge_id },
                    react_1.default.createElement("strong", null, "Saved exact pin is unavailable or stale"),
                    react_1.default.createElement("small", null,
                        "Edge ",
                        react_1.default.createElement("code", null, pin.edge_id),
                        " \u00B7 scope ",
                        pin.source_scope === 'scene-context' ? 'Scene context' : 'Direct shot link'),
                    react_1.default.createElement("small", null, "This pin remains in the draft until you explicitly choose a new source during rebase."))),
                !!draft.source_pins.length && react_1.default.createElement("section", { className: "shot-pin-comparison", "aria-label": "Saved and current exact pin details" },
                    react_1.default.createElement("h5", null, "Saved and current exact pins"),
                    draft.source_pins.map(pin => { const current = sourceByEdge.get(pin.edge_id); const detail = sourceDetails[pin.edge_id]; const previous = saved?.source_pins?.find(item => item.edge_id === pin.edge_id); return react_1.default.createElement("div", { className: "shot-pin-comparison-row", key: pin.edge_id },
                        react_1.default.createElement("strong", null, current ? sourceName(current, detail) : `Saved exact source ${pin.edge_id}`),
                        react_1.default.createElement("dl", null,
                            react_1.default.createElement("div", null,
                                react_1.default.createElement("dt", null, "Scope"),
                                react_1.default.createElement("dd", null, pin.source_scope === 'scene-context' ? 'Scene context' : 'Direct shot link')),
                            react_1.default.createElement("div", null,
                                react_1.default.createElement("dt", null, "Saved pin"),
                                react_1.default.createElement("dd", null, previous ? react_1.default.createElement(react_1.default.Fragment, null,
                                    "Version ",
                                    react_1.default.createElement("code", null, previous.source_version_id),
                                    " \u00B7 node ",
                                    react_1.default.createElement("code", null, previous.node_id),
                                    " \u00B7 source SHA-256 ",
                                    react_1.default.createElement("code", null, previous.source_sha256 || 'Unavailable'),
                                    previous.scope_sha256 && react_1.default.createElement(react_1.default.Fragment, null,
                                        " \u00B7 scope SHA-256 ",
                                        react_1.default.createElement("code", null, previous.scope_sha256))) : 'Not saved yet')),
                            react_1.default.createElement("div", null,
                                react_1.default.createElement("dt", null, "Current linked source"),
                                react_1.default.createElement("dd", null, current ? react_1.default.createElement(react_1.default.Fragment, null,
                                    "Version ",
                                    react_1.default.createElement("code", null, current.version_id),
                                    " \u00B7 node ",
                                    react_1.default.createElement("code", null, current.node_id),
                                    " \u00B7 source SHA-256 ",
                                    react_1.default.createElement("code", null, detail?.contentSha256 || current.content_sha256 || 'Unavailable'),
                                    (current.stale || previous && previous.source_version_id !== current.version_id) && ' · differs from the saved pin') : 'Unavailable; saved pin retained in this draft')))); })),
                retargetPreview && react_1.default.createElement(RetargetReview, { preview: retargetPreview, body: draft, saved: saved, rows: sourceByEdge, details: sourceDetails, onCancel: () => setRetargetPreview(null), onConfirm: confirmRetarget, disabled: busy || ownerPending })),
            react_1.default.createElement("section", { className: "shot-intent-section" },
                react_1.default.createElement("div", { className: "shot-intent-section-heading" },
                    react_1.default.createElement("div", null,
                        react_1.default.createElement("h4", null, "Purpose and communication"),
                        react_1.default.createElement("p", null, "Keep each purpose attached to one exact source edge.")),
                    react_1.default.createElement("button", { type: "button", onClick: addIntent, disabled: !draft.source_pins.length }, "Add purpose")),
                draft.script_intents.map(intent => react_1.default.createElement("article", { className: "shot-intent-card", key: intent.id, "data-intent-id": intent.id },
                    react_1.default.createElement("div", { className: "shot-intent-card-heading" },
                        react_1.default.createElement("strong", null,
                            "Purpose ",
                            react_1.default.createElement("small", null,
                                "Stable ID ",
                                react_1.default.createElement("code", null, intent.id))),
                        react_1.default.createElement("button", { type: "button", className: "text-button", "aria-label": `Remove purpose ${intent.purpose || intent.id}`, onClick: () => patchDraft(body => ({ ...body, script_intents: body.script_intents.filter(item => item.id !== intent.id) })) }, "Remove")),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Exact source link"),
                        react_1.default.createElement("select", { "aria-label": `Source for purpose ${intent.id}`, value: intent.source_edge_id, onChange: (event) => { const row = sourceByEdge.get(event.target.value); if (row)
                                patchIntent(intent.id, value => ({ ...value, source_edge_id: row.edge_id, source_scope: sourceScope(row) })); } }, draft.source_pins.map(pin => { const row = sourceByEdge.get(pin.edge_id); return react_1.default.createElement("option", { key: pin.edge_id, value: pin.edge_id }, row ? sourceName(row, sourceDetails[row.edge_id]) : `${pin.source_scope} · saved pin ${pin.edge_id}`); }))),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Purpose"),
                        react_1.default.createElement("input", { "aria-label": `Purpose ${intent.id}`, value: intent.purpose, maxLength: 120, onChange: (event) => patchIntent(intent.id, value => ({ ...value, purpose: event.target.value })), placeholder: "e.g. establish the handoff" })),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Communication"),
                        react_1.default.createElement("textarea", { "aria-label": `Communication ${intent.id}`, value: intent.communication, maxLength: 4000, rows: 3, onChange: (event) => patchIntent(intent.id, value => ({ ...value, communication: event.target.value })), placeholder: "What should the audience understand from this source?" })),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, "Basis"),
                        react_1.default.createElement("select", { "aria-label": `Purpose basis ${intent.id}`, value: intent.basis, onChange: (event) => patchIntent(intent.id, value => ({ ...value, basis: event.target.value })) },
                            react_1.default.createElement("option", { value: "direct" }, "Direct"),
                            react_1.default.createElement("option", { value: "interpreted" }, "Interpreted"),
                            react_1.default.createElement("option", { value: "unknown" }, "Unknown"))))),
                !draft.script_intents.length && react_1.default.createElement("p", { className: "muted" }, "No purpose statements yet.")),
            react_1.default.createElement("section", { className: "shot-intent-section" },
                react_1.default.createElement("div", { className: "shot-intent-section-heading" },
                    react_1.default.createElement("div", null,
                        react_1.default.createElement("h4", null, "Source-specific requirements"),
                        react_1.default.createElement("p", null, "Requirements keep their stable IDs and point to one or more selected exact links.")),
                    react_1.default.createElement("button", { type: "button", onClick: addRequirement }, "Add requirement")),
                draft.requirements.map(item => react_1.default.createElement("article", { className: "shot-intent-card", key: item.id, "data-requirement-id": item.id },
                    react_1.default.createElement("div", { className: "shot-intent-card-heading" },
                        react_1.default.createElement("strong", null,
                            "Requirement ",
                            react_1.default.createElement("small", null,
                                "Stable ID ",
                                react_1.default.createElement("code", null, item.id))),
                        react_1.default.createElement("button", { type: "button", className: "text-button", "aria-label": `Remove requirement ${item.id}`, onClick: () => patchDraft(body => ({ ...body, requirements: body.requirements.filter(row => row.id !== item.id) })) }, "Remove")),
                    react_1.default.createElement("div", { className: "shot-intent-grid" },
                        react_1.default.createElement("label", { className: "field" },
                            react_1.default.createElement("span", null, "Priority"),
                            react_1.default.createElement("select", { "aria-label": `Priority ${item.id}`, value: item.priority, onChange: (event) => { const priority = event.target.value; patchRequirement(item.id, value => priority === 'unknown' ? { ...value, priority, topic: value.statement || value.topic || '', statement: null } : { ...value, priority, statement: value.topic || value.statement || '', topic: null }); } },
                                react_1.default.createElement("option", { value: "must" }, "Must"),
                                react_1.default.createElement("option", { value: "prefer" }, "Prefer"),
                                react_1.default.createElement("option", { value: "unknown" }, "Unknown"))),
                        react_1.default.createElement("label", { className: "field" },
                            react_1.default.createElement("span", null, "Basis"),
                            react_1.default.createElement("select", { "aria-label": `Requirement basis ${item.id}`, value: item.basis, onChange: (event) => patchRequirement(item.id, value => ({ ...value, basis: event.target.value })) },
                                react_1.default.createElement("option", { value: "direct" }, "Direct"),
                                react_1.default.createElement("option", { value: "interpreted" }, "Interpreted"),
                                react_1.default.createElement("option", { value: "unknown" }, "Unknown")))),
                    react_1.default.createElement("label", { className: "field" },
                        react_1.default.createElement("span", null, item.priority === 'unknown' ? 'Topic' : 'Requirement statement'),
                        react_1.default.createElement("textarea", { "aria-label": `${item.priority === 'unknown' ? 'Topic' : 'Requirement statement'} ${item.id}`, rows: 3, maxLength: 4000, value: item.priority === 'unknown' ? item.topic || '' : item.statement || '', onChange: (event) => patchRequirement(item.id, value => item.priority === 'unknown' ? { ...value, topic: event.target.value, statement: null } : { ...value, statement: event.target.value, topic: null }) })),
                    react_1.default.createElement("fieldset", { className: "shot-edge-select" },
                        react_1.default.createElement("legend", null, "Exact source links"),
                        draft.source_pins.map(pin => { const row = sourceByEdge.get(pin.edge_id); return react_1.default.createElement("label", { key: pin.edge_id },
                            react_1.default.createElement("input", { type: "checkbox", checked: item.source_edge_ids.includes(pin.edge_id), onChange: (event) => patchRequirement(item.id, value => ({ ...value, source_edge_ids: event.target.checked ? [...value.source_edge_ids, pin.edge_id] : value.source_edge_ids.filter(edge => edge !== pin.edge_id) })) }),
                            react_1.default.createElement("span", null, row ? sourceName(row, sourceDetails[row.edge_id]) : `Saved exact pin · ${pin.edge_id}`)); }),
                        !draft.source_pins.length && react_1.default.createElement("small", null, "Select an exact screenplay link above.")))),
                !draft.requirements.length && react_1.default.createElement("p", { className: "muted" }, "No source-specific requirements yet.")),
            saved && react_1.default.createElement("section", { className: "shot-intent-section" },
                react_1.default.createElement("h4", null, "Saved contract history"),
                react_1.default.createElement("p", null, "Each revision is immutable. Comparing history does not change the editor."),
                react_1.default.createElement("div", { className: "shot-history" }, saved.history.map(version => react_1.default.createElement("div", { className: "shot-history-row", key: version.id },
                    react_1.default.createElement("span", null,
                        react_1.default.createElement("strong", null,
                            "Revision ",
                            version.number),
                        react_1.default.createElement("small", null,
                            version.operation,
                            " \u00B7 ",
                            new Date(version.created_at).toLocaleString()),
                        react_1.default.createElement("small", null,
                            "Version ",
                            react_1.default.createElement("code", null, version.id))),
                    react_1.default.createElement("button", { type: "button", onClick: () => void compareVersion(version.id), disabled: version.id === saved.current_version_id }, "Compare")))))),
        historyDiff && react_1.default.createElement(DiffView, { title: "Contract version comparison", changes: historyDiff.changes.map(change => ({ path: change.path, before: change.before, after: change.after })) }),
        review && react_1.default.createElement("section", { className: "shot-intent-review", "aria-label": "Rebase review" },
            react_1.default.createElement("h4", null, "Reviewed basis changes"),
            react_1.default.createElement("p", null,
                "Saved basis ",
                react_1.default.createElement("code", null, review.saved_basis_sha256),
                " \u00B7 current basis ",
                react_1.default.createElement("code", null, review.current_basis_sha256)),
            react_1.default.createElement(DiffView, { title: review.basis_changed ? 'The saved authored basis changed' : 'The current basis matches the saved basis', changes: review.changes.map(change => ({ path: change.path, before: change.saved_value, after: change.current_value })) }),
            review.changes_truncated && react_1.default.createElement("p", { role: "status" }, "Additional basis differences were omitted by the service."),
            react_1.default.createElement("p", null,
                "Review token ",
                react_1.default.createElement("code", null, review.expected_basis_sha256),
                " \u00B7 contract revision ",
                review.revision),
            react_1.default.createElement("button", { type: "button", className: "primary", onClick: () => void submit('rebase'), disabled: !canSubmit || reviewGeneration !== editGeneration.current }, "Confirm reviewed rebase")),
        ready && !loading && react_1.default.createElement("div", { className: "button-row shot-intent-actions" }, !saved ? react_1.default.createElement("button", { type: "button", className: "primary", onClick: () => void submit('create'), disabled: !canSubmit || conflicted }, "Create observation contract") : react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("button", { type: "button", className: "primary", onClick: () => void submit('revise'), disabled: !canSubmit || !dirty || conflicted }, "Save draft"),
            react_1.default.createElement("button", { type: "button", onClick: () => void reviewRebase(), disabled: busy || ownerPending || loading }, "Review rebase"))),
        saved && react_1.default.createElement("div", { className: "shot-intent-cas" },
            react_1.default.createElement("small", null,
                "Shot revision used for contract creation: ",
                react_1.default.createElement("code", null, initialShotRevision.current)),
            react_1.default.createElement("small", null,
                "Contract header CAS revision for edit: ",
                react_1.default.createElement("code", null, saved.revision)),
            react_1.default.createElement("small", null,
                "Exact source pins in draft: ",
                draft.source_pins.length,
                " \u00B7 linked sources now available: ",
                sources.length)));
}
function DiffView({ title, changes, ariaLabel }) {
    return react_1.default.createElement("section", { className: "shot-intent-diff", role: ariaLabel ? 'region' : undefined, "aria-label": ariaLabel },
        react_1.default.createElement("h4", null, title),
        !changes.length ? react_1.default.createElement("p", null, "No field changes.") : changes.map((change, index) => react_1.default.createElement("div", { className: "shot-intent-diff-row", key: `${change.path}-${index}` },
            react_1.default.createElement("strong", null, readablePath(change.path)),
            react_1.default.createElement("dl", null,
                react_1.default.createElement("div", null,
                    react_1.default.createElement("dt", null, "Saved"),
                    react_1.default.createElement("dd", null, displayValue(change.before))),
                react_1.default.createElement("div", null,
                    react_1.default.createElement("dt", null, "Current or proposed"),
                    react_1.default.createElement("dd", null, displayValue(change.after)))))));
}
function RetargetReview({ preview, body, saved, rows, details, onCancel, onConfirm, disabled }) {
    const oldPin = body.source_pins.find(pin => pin.edge_id === preview.oldEdgeId), oldRow = rows.get(preview.oldEdgeId), nextRow = rows.get(preview.newEdgeId);
    if (!oldPin || !nextRow)
        return null;
    const oldSaved = saved?.source_pins.find(item => item.edge_id === preview.oldEdgeId), oldDetail = details[preview.oldEdgeId], nextDetail = details[nextRow.edge_id];
    return react_1.default.createElement("section", { className: "shot-retarget-preview", "aria-label": "Retarget preview", role: "group" },
        react_1.default.createElement("h5", null, "Retarget preview"),
        react_1.default.createElement("p", null, "This explicit draft edit changes the source edge used by linked purposes and requirements. Nothing changes until you choose Retarget draft pin."),
        react_1.default.createElement("div", null,
            react_1.default.createElement("strong", null, "Saved/local source"),
            react_1.default.createElement("small", null,
                oldRow ? sourceName(oldRow, oldDetail) : `Saved source ${preview.oldEdgeId}`,
                " \u00B7 ",
                oldPin.source_scope === 'scene-context' ? 'Scene context' : 'Direct shot link'),
            react_1.default.createElement("small", null,
                "Version ",
                react_1.default.createElement("code", null, oldSaved?.source_version_id || oldRow?.version_id || 'Unavailable'),
                " \u00B7 node ",
                react_1.default.createElement("code", null, oldSaved?.node_id || oldRow?.node_id || 'Unavailable'),
                " \u00B7 source SHA-256 ",
                react_1.default.createElement("code", null, oldSaved?.source_sha256 || oldDetail?.contentSha256 || 'Unavailable'))),
        react_1.default.createElement("div", null,
            react_1.default.createElement("strong", null, "Proposed current source"),
            react_1.default.createElement("small", null,
                sourceName(nextRow, nextDetail),
                " \u00B7 ",
                sourceScope(nextRow) === 'scene-context' ? 'Scene context' : 'Direct shot link'),
            react_1.default.createElement("small", null,
                "Version ",
                react_1.default.createElement("code", null, nextRow.version_id),
                " \u00B7 node ",
                react_1.default.createElement("code", null, nextRow.node_id),
                " \u00B7 source SHA-256 ",
                react_1.default.createElement("code", null, nextDetail?.contentSha256 || nextRow.content_sha256 || 'Unavailable'))),
        react_1.default.createElement("div", { className: "button-row" },
            react_1.default.createElement("button", { type: "button", onClick: onCancel }, "Cancel"),
            react_1.default.createElement("button", { type: "button", className: "primary", onClick: onConfirm, disabled: disabled }, "Retarget draft pin")));
}
function messageOf(reason) { const value = reason; return value?.message || 'The request could not be completed. Your draft remains in the editor.'; }

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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
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
            react_1.default.createElement("h1", null, "Your project couldn\u2019t open."),
            react_1.default.createElement("p", null, "Your work is still saved on this computer. Refresh the app, or check the launch terminal if the problem continues."),
            react_1.default.createElement("button", { onClick: () => location.reload() }, "Refresh app")); return this.props.children; }
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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.OutlinePage = OutlinePage;
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
    return (0, utils_1.displayTitle)(entity.title.replace(/^\d{2}\s*[·—:-]\s*/, '') || entity.title);
}
function shotAction(entity) {
    const action = String(entity.fields.action || entity.description || 'No action added yet.');
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
                : String(entity.fields.arc || entity.description || 'Add a short story direction.');
        const summary = entity.kind === 'scene' && (repeatsShotSummaries(entity, sceneShots) || /^Grouped from source scene\b/.test(rawSummary)) ? '' : rawSummary;
        const frame = entity.kind === 'shot' ? framingParts(entity) : null;
        const number = String(entity.fields.number || String(entity.position + 1).padStart(2, '0'));
        const title = outlineTitle(entity);
        return react_1.default.createElement("div", { key: entity.id, className: `story-node ${entity.kind}` },
            react_1.default.createElement("div", { className: `story-row ${p.selected === entity.id ? 'is-selected' : ''}` },
                entity.kind === 'shot'
                    ? react_1.default.createElement("span", { className: "shot-order" }, number)
                    : react_1.default.createElement("button", { className: "collapse-button", "aria-label": `${isCollapsed ? 'Expand' : 'Collapse'} ${entity.title}`, "aria-expanded": !isCollapsed, onClick: () => setCollapsed(value => isCollapsed ? value.filter(id => id !== entity.id) : [...value, entity.id]) }, isCollapsed ? '+' : '−'),
                react_1.default.createElement("div", { className: "story-main" },
                    react_1.default.createElement("div", { className: "story-heading-line" },
                        react_1.default.createElement("span", { className: "eyebrow" },
                            (0, utils_1.human)(entity.kind),
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
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Story outline", title: "Build the story, scene by scene.", description: "Organize scenes and shots into sequences, then rearrange them as the story changes.", actions: react_1.default.createElement("button", { className: "primary", onClick: () => p.action('sequence.create') },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New sequence") }),
        react_1.default.createElement("div", { className: "outline-toolbar" },
            react_1.default.createElement("div", { className: "outline-totals", "aria-label": "Story outline items" },
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
                react_1.default.createElement("button", { onClick: () => p.go('canvas') }, "Open story canvas"))),
        react_1.default.createElement("div", { className: "story-outline" }, sequences.map(render)),
        !records.length && react_1.default.createElement(Primitives_1.Empty, { title: "Start with a sequence", action: react_1.default.createElement("button", { onClick: () => p.action('sequence.create') }, "Create a sequence") }, "Add scenes and shots to shape the story. Reorder them here whenever the story changes."));
}

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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.OutlinePage = void 0;
exports.WorkspacePage = WorkspacePage;
exports.OverviewPage = OverviewPage;
exports.UploadControl = UploadControl;
exports.IntakePage = IntakePage;
exports.LibraryPage = LibraryPage;
exports.ScopeSelect = ScopeSelect;
exports.GuidePage = GuidePage;
exports.EditorPage = EditorPage;
exports.FramesPage = FramesPage;
exports.CompositionPage = CompositionPage;
exports.SettingsPage = SettingsPage;
exports.AutomationPage = AutomationPage;
const react_1 = __importStar(require("../react"));
const api_1 = require("../api");
const utils_1 = require("../utils");
const Primitives_1 = require("../components/Primitives");
function recordButtons(p, e) { return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement("button", { onClick: () => p.select(e.id) }, "Details"),
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
        react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Local production desk", title: "Your work, in one place.", description: "Each project keeps its story, images, and exports together on this computer.", actions: session.can_create ? react_1.default.createElement("button", { className: "primary", onClick: () => setCreating(true) },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New project") : react_1.default.createElement(Primitives_1.Badge, null, "Project folder") }),
        react_1.default.createElement("div", { className: "workspace-intro" },
            react_1.default.createElement("span", { className: "eyebrow" }, "Projects folder"),
            react_1.default.createElement("code", null, session.workspace || 'Current project folder'),
            react_1.default.createElement("p", null, "Your story, reference images, and exports stay together in each project folder.")),
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
                react_1.default.createElement("h2", null, (0, utils_1.displayTitle)(p.title)),
                react_1.default.createElement("p", null, p.description || 'A story waiting to take shape.'),
                react_1.default.createElement("small", null, p.path)),
            react_1.default.createElement("span", { className: "project-stats" },
                p.counts?.scene || 0,
                " scenes",
                react_1.default.createElement("br", null),
                p.counts?.asset || 0,
                " library items"),
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
                        react_1.default.createElement("small", null, "Created inside this workspace folder."))),
                react_1.default.createElement("div", { className: "modal-footer" },
                    react_1.default.createElement("button", { type: "button", onClick: () => setCreating(false) }, "Cancel"),
                    react_1.default.createElement("button", { className: "primary", disabled: busy }, busy ? 'Creating…' : 'Create project')))));
}
function OverviewPage(p) { const { state } = p; const [health, setHealth] = (0, react_1.useState)(null); (0, react_1.useEffect)(() => { (0, api_1.runCommand)(state.project.id, 'project.doctor').then(setHealth).catch(() => setHealth(null)); }, [state]); const seq = (0, utils_1.activeEntities)(state, 'sequence'); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Project overview", title: (0, utils_1.displayTitle)(state.project.title), description: String(state.project.fields.premise || state.project.description || 'Give the story a shape. Gather references, build the outline, and make each shot intentional.'), actions: react_1.default.createElement("button", { onClick: () => p.action('project.update', (0, utils_1.commandDefaults)(state.project)) }, "Edit project details") }),
    react_1.default.createElement("div", { className: "metrics" }, [['Scenes', 'scene'], ['Shots', 'shot'], ['Reference items', 'asset'], ['Awaiting review', 'intake']].map(([label, key]) => react_1.default.createElement("button", { key: key, onClick: () => p.go(key === 'asset' ? 'library' : key === 'intake' ? 'intake' : 'outline') },
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
                    react_1.default.createElement("button", { className: "title-button", onClick: () => p.select(s.id) }, (0, utils_1.displayTitle)(s.title)),
                    react_1.default.createElement("p", null, s.fields.arc || s.description || 'Add a short description for this sequence.'),
                    react_1.default.createElement("small", null,
                        state.entities.filter(e => !e.archived && e.parent_id === s.id).length,
                        " scenes")),
                react_1.default.createElement("button", { onClick: () => p.action('scene.create', { parent_id: s.id }) }, "Add scene"))) : react_1.default.createElement(Primitives_1.Empty, { title: "Begin with a sequence", action: react_1.default.createElement("button", { onClick: () => p.action('sequence.create') }, "Create a sequence") }, "A sequence holds scenes. Each scene holds the shots that carry it."),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Story direction"),
                react_1.default.createElement("button", { className: "text-button", onClick: () => p.go('guide') }, "Open guide \u2192")),
            react_1.default.createElement("p", { className: "prose" }, state.project.fields.visual_style || 'Set the visual style, production notes, and story direction in the Story guide.')),
        react_1.default.createElement("aside", { className: "overview-notes" },
            react_1.default.createElement("h2", null, "At the desk"),
            health && react_1.default.createElement("div", { className: `health-summary ${health.healthy ? 'healthy' : 'warning'}` },
                react_1.default.createElement(Primitives_1.Icon, { name: health.healthy ? 'check' : 'settings' }),
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, health.healthy ? 'Project files are in order' : 'Project needs attention'),
                    react_1.default.createElement("p", null, health.issues.length ? `${health.issues.length} ${health.issues.length === 1 ? 'item needs' : 'items need'} review.` : 'Project files and reference images passed the current check.'),
                    react_1.default.createElement("button", { className: "text-button", onClick: () => p.go('settings') }, "View health report \u2192"))),
            react_1.default.createElement("h3", null, "Recent changes"),
            react_1.default.createElement("ol", { className: "event-list" }, state.events.slice(0, 10).map(e => react_1.default.createElement("li", { key: e.id },
                react_1.default.createElement("span", null, p.meta.commands.find(c => c.name === e.action)?.label || (0, utils_1.human)(e.action.replaceAll('.', ' '))),
                react_1.default.createElement("small", null, (0, utils_1.niceDate)(e.created_at))))),
            react_1.default.createElement("div", { className: "notice" }, "Your project is saved on this computer. Back up its folder regularly to keep a second copy.")))); }
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
} setStatus(`${accepted} image${accepted === 1 ? '' : 's'} added to intake; ${errors.length} couldn’t be imported${files.length !== eligible.length ? `; ${files.length - eligible.length} image${files.length - eligible.length === 1 ? '' : 's'} in subfolders skipped` : ''}.`); setFailures(errors); setBusy(false); await done(); } return react_1.default.createElement("div", { className: "upload-control" },
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
                "Include subfolders"))),
    react_1.default.createElement("small", null, "JPEG, PNG, WebP, TIFF, BMP \u00B7 single images \u00B7 up to 50 MiB / 50 megapixels each."),
    status && react_1.default.createElement("p", { role: "status" }, status),
    failures.length > 0 && react_1.default.createElement("details", { open: true },
        react_1.default.createElement("summary", null,
            failures.length,
            " files not imported"),
        failures.map((f, i) => react_1.default.createElement("p", { className: "warning-text", key: i }, f)))); }
function IntakePage(p) { const [filter, setFilter] = (0, react_1.useState)('pending'), [query, setQuery] = (0, react_1.useState)(''), [checked, setChecked] = (0, react_1.useState)([]), [bulk, setBulk] = (0, react_1.useState)(''), [bulkTags, setBulkTags] = (0, react_1.useState)(''), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false); const items = p.state.intake.filter(i => (!filter || i.state === filter) && i.original_name.toLowerCase().includes(query.toLowerCase())).sort((a, b) => a.media_id.localeCompare(b.media_id)); async function acceptBulk() { setBusy(true); try {
    for (const id of checked) {
        const item = p.state.intake.find(i => i.id === id);
        if (item && item.state === 'pending')
            await (0, api_1.runCommand)(p.state.project.id, 'intake.accept', { id, revision: item.revision, ...(bulk ? { asset_id: bulk } : {}), tags: bulkTags.split(',').map(s => s.trim()).filter(Boolean) });
    }
    setChecked([]);
    await p.refresh();
    p.notify('Selected images added to the library.');
}
catch (e) {
    setError(e.message);
    await p.refresh();
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Image intake", title: "Give every image a place.", description: "Review imported images, group identical copies, and add useful images to your library." }),
    react_1.default.createElement(UploadControl, { project: p.state.project.id, done: p.refresh }),
    react_1.default.createElement("div", { className: "list-toolbar" },
        react_1.default.createElement("label", { className: "search" },
            react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
            react_1.default.createElement("input", { value: query, onChange: (e) => setQuery(e.target.value), placeholder: "Find imported files\u2026", "aria-label": "Search intake" })),
        react_1.default.createElement("select", { "aria-label": "Imported image status", value: filter, onChange: (e) => { setFilter(e.target.value); setChecked([]); } }, ['pending', 'accepted', 'discarded', ''].map(s => react_1.default.createElement("option", { key: s, value: s }, s ? (0, utils_1.human)(s) : 'All statuses')))),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    " ",
    checked.length > 0 && react_1.default.createElement("div", { className: "bulk-bar" },
        react_1.default.createElement("strong", null,
            checked.length,
            " selected"),
        react_1.default.createElement("select", { "aria-label": "Add selected images to", value: bulk, onChange: (e) => setBulk(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "Add to a library item"),
            (0, utils_1.activeEntities)(p.state, 'asset').map(a => react_1.default.createElement("option", { key: a.id, value: a.id }, (0, utils_1.displayTitle)(a.title)))),
        react_1.default.createElement("input", { "aria-label": "Bulk tags", value: bulkTags, onChange: (e) => setBulkTags(e.target.value), placeholder: "Tags, comma-separated" }),
        react_1.default.createElement("button", { onClick: acceptBulk, disabled: busy }, "Add selected"),
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
                react_1.default.createElement(Primitives_1.Badge, null, (0, utils_1.human)(item.state)),
                duplicates > 1 && react_1.default.createElement(Primitives_1.Badge, { kind: "warning" },
                    "Identical image \u00B7 ",
                    duplicates,
                    " imports"),
                m.tags.map(t => react_1.default.createElement("span", { key: t, className: "tag" }, t)))),
        react_1.default.createElement("div", { className: "row-actions" },
            item.state === 'pending' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("button", { onClick: () => p.action('intake.accept', (0, utils_1.commandDefaults)(item)) }, "Add to library"),
                react_1.default.createElement("button", { onClick: () => p.action('intake.accept', { ...(0, utils_1.commandDefaults)(item), create_title: item.original_name.replace(/\.[^.]+$/, '') }) }, "Create item from image"),
                react_1.default.createElement("button", { onClick: () => p.action('intake.discard', (0, utils_1.commandDefaults)(item)) }, "Remove from intake\u2026")),
            react_1.default.createElement("button", { onClick: () => p.action('media.tags', (0, utils_1.commandDefaults)(m)) }, "Tag image"))); })),
    !items.length && react_1.default.createElement(Primitives_1.Empty, { title: filter === 'pending' ? 'Intake is clear' : 'No matching intake items' }, "Import individual images or a folder. Identical images are grouped, and each import remains available to review.")); }
function LibraryPage(p) { const [query, setQuery] = (0, react_1.useState)(''), [type, setType] = (0, react_1.useState)(''), [tag, setTag] = (0, react_1.useState)(''), [page, setPage] = (0, react_1.useState)(0); const records = (0, utils_1.activeEntities)(p.state, 'asset').filter(e => (!type || e.fields.type === type) && (!tag || e.tags.includes(tag)) && [e.title, e.description, ...e.aliases].join(' ').toLowerCase().includes(query.toLowerCase())); const visible = records.slice(page * 48, (page + 1) * 48); (0, react_1.useEffect)(() => setPage(0), [query, type, tag]); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Reference library", title: "The people, places, and things.", description: "Keep each character, location, or prop in one place with its reference images. Choose the specific image you want for each shot.", actions: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("button", { onClick: () => p.go('intake') }, "Import references"),
            react_1.default.createElement("button", { className: "primary", onClick: () => p.action('asset.create') },
                react_1.default.createElement(Primitives_1.Icon, { name: "plus" }),
                "New library item")) }),
    react_1.default.createElement("div", { className: "list-toolbar" },
        react_1.default.createElement("label", { className: "search" },
            react_1.default.createElement(Primitives_1.Icon, { name: "search" }),
            react_1.default.createElement("input", { "aria-label": "Search the library", value: query, onChange: (e) => setQuery(e.target.value), placeholder: "Search names, aliases, descriptions\u2026" })),
        react_1.default.createElement("select", { "aria-label": "Filter by item type", value: type, onChange: (e) => setType(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "All types"),
            ['character', 'location', 'prop', 'reference'].map(t => react_1.default.createElement("option", { key: t }, t))),
        react_1.default.createElement("select", { "aria-label": "Filter by tag", value: tag, onChange: (e) => setTag(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "All tags"),
            [...new Set(p.state.entities.flatMap(e => e.tags))].sort().map(t => react_1.default.createElement("option", { key: t }, t))),
        react_1.default.createElement("span", { className: "muted" },
            records.length,
            " items")),
    react_1.default.createElement("div", { className: "asset-grid" }, visible.map(a => { const members = p.state.asset_media.filter(m => m.asset_id === a.id), primary = members.find(m => m.is_primary) || members[0]; return react_1.default.createElement("article", { className: `asset-card ${p.selected === a.id ? 'is-selected' : ''}`, key: a.id },
        react_1.default.createElement("button", { className: "asset-preview", onClick: () => p.select(a.id), "aria-label": `View ${a.title}` }, primary ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, primary.media_id), alt: a.title, loading: "lazy" }) : react_1.default.createElement("span", { className: "media-placeholder" },
            react_1.default.createElement(Primitives_1.Icon, { name: "library", size: 32 }),
            "No image yet")),
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
    !records.length && react_1.default.createElement(Primitives_1.Empty, { title: "Build your reference library", action: react_1.default.createElement("button", { onClick: () => p.action('asset.create') }, "Create a library item") }, "Start with a character, location, prop, or other reference. Add images whenever you have them."),
    records.length > 48 && react_1.default.createElement("div", { className: "pagination" },
        react_1.default.createElement("button", { disabled: page === 0, onClick: () => setPage(page - 1) }, "Previous"),
        react_1.default.createElement("span", null,
            "Page ",
            page + 1,
            " of ",
            Math.ceil(records.length / 48)),
        react_1.default.createElement("button", { disabled: (page + 1) * 48 >= records.length, onClick: () => setPage(page + 1) }, "Next"))); }
var OutlinePage_1 = require("./OutlinePage");
Object.defineProperty(exports, "OutlinePage", { enumerable: true, get: function () { return OutlinePage_1.OutlinePage; } });
function ScopeSelect({ state, value, onChange, label = 'Applies to', shotsOnly = false }) { const choices = (0, utils_1.activeEntities)(state).filter(e => shotsOnly ? e.kind === 'shot' : e.kind !== 'asset').sort((a, b) => a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title)); return react_1.default.createElement("label", { className: "field scope-select" },
    react_1.default.createElement("span", null, label),
    react_1.default.createElement("select", { "aria-label": label, value: value, onChange: (e) => onChange(e.target.value) },
        !choices.some(e => e.id === value) && react_1.default.createElement("option", { value: "" }, "Choose\u2026"),
        choices.map(e => react_1.default.createElement("option", { key: e.id, value: e.id },
            (0, utils_1.human)(e.kind),
            " \u00B7 ",
            (0, utils_1.displayTitle)(e.title))))); }
function GuidePage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind !== 'asset' ? p.selected : p.state.project.id), [context, setContext] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''); const record = p.state.entities.find(e => e.id === scope) || p.state.project; (0, react_1.useEffect)(() => { let alive = true; (0, api_1.runCommand)(p.state.project.id, 'context.resolve', { owner_id: scope }).then(r => alive && setContext(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [scope, p.state]); const blocks = p.state.context_blocks.filter(b => b.owner_id === scope); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Story guide", title: "A guide for every part of the story.", description: "Set direction for the whole project, then add notes for a sequence, scene, or shot when needed.", actions: react_1.default.createElement("button", { onClick: () => p.action(record.kind + '.update', (0, utils_1.commandDefaults)(record)) },
            "Edit ",
            record.kind === 'project' ? 'project' : (0, utils_1.human)(record.kind).toLowerCase(),
            " direction") }),
    react_1.default.createElement(ScopeSelect, { state: p.state, value: scope, onChange: setScope }),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    react_1.default.createElement("div", { className: "guide-columns" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Direction at this level"),
                react_1.default.createElement("button", { onClick: () => p.action('context.put', { owner_id: scope }) }, "Add direction note")),
            Object.entries(record.fields).filter(([k, v]) => v !== '' && v != null).map(([key, value]) => react_1.default.createElement("section", { className: "detail-field", key: key },
                react_1.default.createElement("h3", null, (0, utils_1.human)(key)),
                react_1.default.createElement("p", { className: "prose" }, key === 'location_id' ? (0, utils_1.displayTitle)(p.state.entities.find(e => e.id === value)?.title || String(value)) : String(value)))),
            blocks.map(b => react_1.default.createElement("section", { className: "authored-block", key: b.id },
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h3", null, (0, utils_1.human)(b.key)),
                    b.operation !== 'append' && react_1.default.createElement(Primitives_1.Badge, null, (0, utils_1.operationLabel)(b.operation))),
                react_1.default.createElement("p", { className: "prose" }, b.text || 'Direction from above is hidden here.'),
                react_1.default.createElement("div", { className: "button-row" },
                    react_1.default.createElement("button", { onClick: () => p.action('context.put', (0, utils_1.commandDefaults)(b)) }, "Edit direction note"),
                    react_1.default.createElement("button", { onClick: () => p.action('context.remove', (0, utils_1.commandDefaults)(b)) }, "Remove\u2026")))),
            !blocks.length && react_1.default.createElement("p", { className: "muted" }, "No direction notes here yet. Notes from the project and story above still apply.")),
        react_1.default.createElement("section", { className: "resolved-panel" },
            react_1.default.createElement("h2", null, "Direction in effect"),
            context ? react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement(Primitives_1.ContextView, { value: context }),
                Object.keys(context.blocks).length > 0 && react_1.default.createElement("div", { className: "optout-list" },
                    react_1.default.createElement("h3", null, "Direction hidden here"),
                    Object.keys(context.blocks).filter(key => !blocks.some(b => b.key === key)).map(key => react_1.default.createElement("button", { key: key, onClick: () => p.action('context.put', { owner_id: scope, key, operation: 'exclude', content: '' }) },
                        "Turn off \u201C",
                        (0, utils_1.human)(key),
                        "\u201D here\u2026")))) : react_1.default.createElement("p", null, "Loading story direction\u2026")))); }
function EditorPage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && ['scene', 'shot'].includes(p.state.entities.find(e => e.id === p.selected)?.kind || '') ? p.selected : (0, utils_1.activeEntities)(p.state, 'shot')[0]?.id || (0, utils_1.activeEntities)(p.state, 'scene')[0]?.id || ''); const record = p.state.entities.find(e => e.id === scope); const [composition, setComposition] = (0, react_1.useState)(null); (0, react_1.useEffect)(() => { if (scope)
    (0, api_1.runCommand)(p.state.project.id, 'composition.preview', { owner_id: scope }).then(setComposition).catch(() => setComposition(null)); }, [scope, p.state]); return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Scene & shot editor", title: "Shape the scene and shot.", description: "Add action, dialogue, camera notes, continuity, and image references to every scene and shot.", actions: react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("button", { onClick: () => p.action('scene.create') }, "New scene"),
            react_1.default.createElement("button", { onClick: () => p.action('shot.create') }, "New shot")) }),
    react_1.default.createElement("label", { className: "field scope-select" },
        react_1.default.createElement("span", null, "Scene or shot"),
        react_1.default.createElement("select", { value: scope, onChange: (e) => setScope(e.target.value) },
            react_1.default.createElement("option", { value: "" }, "Choose a scene or shot"),
            (0, utils_1.activeEntities)(p.state).filter(e => ['scene', 'shot'].includes(e.kind)).map(e => react_1.default.createElement("option", { key: e.id, value: e.id },
                (0, utils_1.human)(e.kind),
                " \u00B7 ",
                (0, utils_1.displayTitle)(e.title))))),
    record ? react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement("div", { className: "editor-document" },
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("div", null,
                    react_1.default.createElement(Primitives_1.Badge, null, (0, utils_1.human)(record.kind)),
                    react_1.default.createElement("h2", null, (0, utils_1.displayTitle)(record.title))),
                react_1.default.createElement("button", { className: "primary", onClick: () => p.action(record.kind + '.update', (0, utils_1.commandDefaults)(record)) }, "Edit details")),
            react_1.default.createElement("p", { className: "prose" }, record.description),
            react_1.default.createElement("div", { className: "authored-fields" }, Object.entries(record.fields).map(([key, value]) => react_1.default.createElement("section", { key: key },
                react_1.default.createElement("h3", null, (0, utils_1.human)(key)),
                react_1.default.createElement("p", { className: `prose ${value == null || value === '' ? 'muted' : ''}` }, value == null || value === '' ? 'Not set' : key === 'location_id' ? (0, utils_1.displayTitle)(p.state.entities.find(e => e.id === value)?.title || String(value)) : String(value))))),
            record.kind === 'shot' && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h2", null, "References in this shot"),
                    react_1.default.createElement("button", { onClick: () => p.action('assignment.create', { shot_id: record.id }) }, "Add a reference")),
                react_1.default.createElement("div", { className: "reference-grid" }, p.state.assignments.filter(a => a.shot_id === record.id).map(a => react_1.default.createElement("article", { key: a.id },
                    a.media_id ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, a.media_id), alt: `${(0, utils_1.human)(a.role)} reference` }) : react_1.default.createElement("div", { className: "media-placeholder" }, "No specific image selected"),
                    react_1.default.createElement("h3", null, (0, utils_1.displayTitle)(p.state.entities.find(e => e.id === a.asset_id)?.title || 'Library item')),
                    react_1.default.createElement(Primitives_1.Badge, null, (0, utils_1.human)(a.role)),
                    react_1.default.createElement("p", null, a.media_id ? p.state.media.find(m => m.id === a.media_id)?.original_name : 'No specific image selected. Choose an image if this shot needs one.'),
                    react_1.default.createElement("div", { className: "button-row" },
                        react_1.default.createElement("button", { onClick: () => p.action('assignment.update', { ...(0, utils_1.commandDefaults)(a), asset_id: a.asset_id }) }, "Change reference"),
                        react_1.default.createElement("button", { onClick: () => p.action('assignment.remove', (0, utils_1.commandDefaults)(a)) }, "Remove\u2026"))))))),
        composition && react_1.default.createElement("details", { className: "context-preview" },
            react_1.default.createElement("summary", null, "Direction and production checks"),
            react_1.default.createElement(Primitives_1.ContextView, { value: composition.context }),
            react_1.default.createElement(Primitives_1.Validation, { issues: composition.validation }))) : react_1.default.createElement(Primitives_1.Empty, { title: "Select a scene or shot" }, "Create a sequence in the outline first, then build its scenes and shots.")); }
function FramesPage(p) { const [shot, setShot] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind === 'shot' ? p.selected : (0, utils_1.activeEntities)(p.state, 'shot')[0]?.id || ''), [compare, setCompare] = (0, react_1.useState)([]), [archived, setArchived] = (0, react_1.useState)(false); (0, react_1.useEffect)(() => { setCompare([]); }, [shot]); const frames = p.state.frames.filter(f => f.shot_id === shot && (archived || f.state !== 'archived')).sort((a, b) => b.version - a.version); const visible = compare.length >= 2 ? frames.filter(f => compare.includes(f.id)) : frames; return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Storyboard frames", title: "Compare storyboard images", description: "Add storyboard images for a shot, compare versions, then select or approve the one you want to use.", actions: shot ? react_1.default.createElement("button", { onClick: () => p.action('frame.attach', { shot_id: shot }) }, "Add storyboard image") : undefined }),
    react_1.default.createElement(ScopeSelect, { state: p.state, value: shot, onChange: setShot, label: "Shot", shotsOnly: true }),
    shot ? react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(UploadControl, { project: p.state.project.id, shot: shot, done: p.refresh }),
        react_1.default.createElement("div", { className: "list-toolbar" },
            react_1.default.createElement("label", { className: "inline-check" },
                react_1.default.createElement("input", { type: "checkbox", checked: archived, onChange: (e) => setArchived(e.target.checked) }),
                "Include archived images"),
            compare.length > 0 && react_1.default.createElement("button", { onClick: () => setCompare([]) },
                "Clear comparison (",
                compare.length,
                ")"),
            react_1.default.createElement("small", null, "Choose two or more \u201CCompare\u201D checkboxes for a side-by-side review.")),
        react_1.default.createElement("div", { className: `frames-grid ${compare.length ? 'comparison' : ''}` }, visible.map(f => react_1.default.createElement("article", { className: `frame-card ${f.state}`, key: f.id },
            react_1.default.createElement("a", { href: (0, api_1.originalUrl)(p.state.project.id, f.media_id), target: "_blank", rel: "noreferrer" },
                react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, f.media_id, 960), alt: `Storyboard image ${f.version}` })),
            react_1.default.createElement("div", { className: "frame-caption" },
                react_1.default.createElement("h3", null,
                    "Image ",
                    f.version),
                react_1.default.createElement(Primitives_1.Badge, { kind: f.state }, (0, utils_1.human)(f.state))),
            react_1.default.createElement("p", { className: "prose" }, f.notes || 'No notes for this image.'),
            react_1.default.createElement("small", null, p.state.media.find(m => m.id === f.media_id)?.original_name),
            react_1.default.createElement("div", { className: "button-row" }, ['draft', 'selected', 'approved', 'archived'].filter(s => s !== f.state).map(status => react_1.default.createElement("button", { key: status, onClick: () => p.action('frame.state', { id: f.id, revision: f.revision, state: status }) }, status === 'selected' ? 'Select' : status === 'approved' ? 'Approve' : status === 'archived' ? 'Archive…' : 'Return to draft'))),
            react_1.default.createElement("label", { className: "inline-check" },
                react_1.default.createElement("input", { type: "checkbox", checked: compare.includes(f.id), onChange: () => setCompare(v => v.includes(f.id) ? v.filter(id => id !== f.id) : [...v, f.id]) }),
                "Compare v",
                f.version),
            Object.keys(f.provenance || {}).length > 0 && react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Technical details"),
                react_1.default.createElement("pre", null, JSON.stringify(f.provenance, null, 2)))))),
        !frames.length && react_1.default.createElement(Primitives_1.Empty, { title: "No storyboard images yet" }, "Add an image for this shot. Reference images remain in the library, separate from storyboard images.")) : react_1.default.createElement(Primitives_1.Empty, { title: "Choose a shot" }, "Create a shot in the outline before adding a storyboard image.")); }
function CompositionPage(p) { const [scope, setScope] = (0, react_1.useState)(p.selected && p.state.entities.find(e => e.id === p.selected)?.kind !== 'asset' ? p.selected : (0, utils_1.activeEntities)(p.state, 'scene')[0]?.id || p.state.project.id), [document, setDocument] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''), [busy, setBusy] = (0, react_1.useState)(false), [approved, setApproved] = (0, react_1.useState)(false); (0, react_1.useEffect)(() => { let alive = true; setError(''); (0, api_1.runCommand)(p.state.project.id, 'composition.preview', { owner_id: scope }).then(r => alive && setDocument(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [scope, p.state]); async function exportTo(format) { setBusy(true); try {
    const r = await (0, api_1.runCommand)(p.state.project.id, format === 'bundle' ? 'export.bundle' : 'export.board', { owner_id: scope, ...(format === 'bundle' ? { include_media: true } : { format, approved_only: approved }) });
    p.setResult(r);
    p.notify('Project package created.');
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Boards & exports", title: "Turn the outline into a board.", description: "Review the story direction and chosen images, then create a board or a package to share." }),
    react_1.default.createElement("div", { className: "composition-toolbar" },
        react_1.default.createElement(ScopeSelect, { state: p.state, value: scope, onChange: setScope }),
        react_1.default.createElement("label", { className: "inline-check" },
            react_1.default.createElement("input", { type: "checkbox", checked: approved, onChange: (e) => setApproved(e.target.checked) }),
            "Use only approved storyboard frames"),
        react_1.default.createElement("div", { className: "button-row" },
            react_1.default.createElement("button", { className: "primary", disabled: busy || !document?.valid, onClick: () => exportTo('bundle') }, "Download project package"),
            react_1.default.createElement("button", { disabled: busy || !document?.valid, onClick: () => exportTo('all') }, "Export HTML + PDF + PNG")),
        busy && react_1.default.createElement("p", { role: "status" }, "Preparing your files\u2026")),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    " ",
    p.result && react_1.default.createElement(Primitives_1.ExportLinks, { project: p.state.project.id, result: p.result }),
    " ",
    document && react_1.default.createElement(react_1.default.Fragment, null,
        react_1.default.createElement(Primitives_1.Validation, { issues: document.validation }),
        react_1.default.createElement("details", { className: "context-preview" },
            react_1.default.createElement("summary", null, "Story direction"),
            react_1.default.createElement(Primitives_1.ContextView, { value: document.context })),
        react_1.default.createElement("div", { className: "presentation-board" },
            react_1.default.createElement("header", null,
                react_1.default.createElement("span", { className: "eyebrow" },
                    "Storyboard / ",
                    (0, utils_1.displayTitle)(p.state.project.title)),
                react_1.default.createElement("h2", null, (0, utils_1.displayTitle)(document.owner.title)),
                react_1.default.createElement("p", null,
                    document.scenes.reduce((n, s) => n + s.shots.length, 0),
                    " shots \u00B7 references and storyboard images")),
            document.scenes.map(scene => react_1.default.createElement("section", { key: scene.id, className: "board-scene" },
                react_1.default.createElement("div", { className: "section-heading" },
                    react_1.default.createElement("h3", null,
                        (0, utils_1.displayTitle)(scene.sequence.title),
                        " / ",
                        (0, utils_1.displayTitle)(scene.title)),
                    react_1.default.createElement("button", { onClick: () => p.select(scene.id) }, "Scene details")),
                react_1.default.createElement("div", { className: "board-panels" }, scene.shots.map(shot => { const preferred = shot.frames.find(f => f.state === 'approved') || (!approved ? shot.frames.find(f => f.state === 'selected') : null); const image = preferred?.media_id || shot.assignments.find(a => a.media_id)?.media_id; return react_1.default.createElement("article", { className: "board-panel", key: shot.id },
                    react_1.default.createElement("div", { className: "board-image" },
                        image ? react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, image, 960), alt: `${(0, utils_1.displayTitle)(shot.title)}: ${preferred ? 'storyboard frame' : 'source reference'}` }) : react_1.default.createElement("span", null, "No storyboard image yet"),
                        react_1.default.createElement("span", null, preferred ? `${(0, utils_1.human)(preferred.state)} storyboard image · ${preferred.version}` : image ? 'Reference image' : 'No storyboard image yet')),
                    react_1.default.createElement("div", { className: "board-shot-title" },
                        react_1.default.createElement("span", null, shot.fields.number || String(shot.position + 1).padStart(2, '0')),
                        react_1.default.createElement("h4", null, (0, utils_1.displayTitle)(shot.title))),
                    react_1.default.createElement("p", { className: "board-framing" },
                        shot.context.scalars.framing?.value || 'Framing not set',
                        shot.fields.duration != null ? ` · ${shot.fields.duration}s` : ''),
                    react_1.default.createElement("p", { className: "prose" }, shot.fields.action || 'No action added yet.'),
                    shot.fields.dialogue && react_1.default.createElement("blockquote", null, shot.fields.dialogue),
                    shot.fields.camera && react_1.default.createElement("p", null,
                        react_1.default.createElement("strong", null, "Camera"),
                        " \u00B7 ",
                        shot.fields.camera),
                    react_1.default.createElement("div", { className: "board-reference-strip" }, shot.assignments.filter(a => a.media_id).map(a => react_1.default.createElement("a", { key: a.id, href: (0, api_1.originalUrl)(p.state.project.id, a.media_id), target: "_blank", rel: "noreferrer" },
                        react_1.default.createElement("img", { src: (0, api_1.mediaUrl)(p.state.project.id, a.media_id, 160), alt: `${a.asset?.title}: ${(0, utils_1.human)(a.role).toLowerCase()} reference` }),
                        react_1.default.createElement("small", null, (0, utils_1.human)(a.role))))),
                    react_1.default.createElement("div", { className: "button-row" },
                        react_1.default.createElement("button", { onClick: () => p.action('shot.update', (0, utils_1.commandDefaults)(shot)) }, "Edit shot"),
                        react_1.default.createElement("button", { onClick: () => p.action('context.resolve', { owner_id: shot.id }) }, "View story direction"))); })),
                !scene.shots.length && react_1.default.createElement("p", { className: "muted" }, "No shots in this scene yet."))),
            !document.scenes.length && react_1.default.createElement(Primitives_1.Empty, { title: "Start your storyboard with a scene" }, "Create a sequence, then add scenes and shots in the Story outline.")))); }
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
    p.notify('Project backup created.');
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
    p.notify(`Project restored. Open the new copy from Workspace.`);
    await p.refresh();
}
catch (e) {
    setError(e.message);
}
finally {
    setBusy(false);
} } return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Project care", title: "Keep the work dependable.", description: "Check project files, rebuild image previews, and make a backup you can restore later.", actions: react_1.default.createElement("button", { onClick: () => p.action('project.update', (0, utils_1.commandDefaults)(p.state.project)) }, "Edit project details") }),
    error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
    react_1.default.createElement("div", { className: "settings-grid" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Project folder"),
            react_1.default.createElement("p", null,
                "Saved on this computer at ",
                react_1.default.createElement("code", null, p.state.project.path),
                "."),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Technical details"),
                react_1.default.createElement("dl", { className: "key-values" },
                    react_1.default.createElement("dt", null, "Project index"),
                    react_1.default.createElement("dd", null,
                        react_1.default.createElement("code", null, ".storyboarder/storyboard.sqlite3")),
                    react_1.default.createElement("dt", null, "App version"),
                    react_1.default.createElement("dd", null, "1 / v1"),
                    react_1.default.createElement("dt", null, "Project format"),
                    react_1.default.createElement("dd", null, p.session.schema_version))),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Project health"),
                react_1.default.createElement("div", { className: "button-row" },
                    react_1.default.createElement("button", { disabled: busy, onClick: () => check(false) }, "Check project files"),
                    react_1.default.createElement("button", { disabled: busy, onClick: () => check(true) }, "Check image contents"))),
            health && react_1.default.createElement(react_1.default.Fragment, null,
                react_1.default.createElement("p", { className: health.healthy ? 'success-line' : 'warning-text' },
                    health.healthy ? '✓ Healthy' : '! Attention needed',
                    " \u00B7 ",
                    health.media_checked,
                    " media files checked"),
                react_1.default.createElement(Primitives_1.Validation, { issues: health.issues }),
                react_1.default.createElement("details", null,
                    react_1.default.createElement("summary", null, "Technical details \u00B7 project updates"),
                    react_1.default.createElement("pre", null, JSON.stringify(health.migrations, null, 2)))),
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, "Image previews")),
            react_1.default.createElement("p", null, "Previews can be rebuilt from the original images. Clearing them does not remove images from your project."),
            react_1.default.createElement("div", { className: "button-row" },
                react_1.default.createElement("button", { onClick: () => p.action('cache.rebuild') }, "Rebuild image previews"),
                react_1.default.createElement("button", { onClick: () => p.action('cache.clear') }, "Clear image previews"))),
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Back up the whole project"),
            react_1.default.createElement("p", null, "Create a copy of the project, including its story and reference images, so you can restore it later."),
            react_1.default.createElement("button", { className: "primary", disabled: busy, onClick: makeBackup }, "Create project backup"),
            backup && react_1.default.createElement("div", { className: "notice" },
                react_1.default.createElement("p", null,
                    "Project backup created \u00B7 ",
                    (backup.size / 1024 / 1024).toFixed(1),
                    " MB"),
                react_1.default.createElement("code", null, backup.path),
                (backup.path || backup.archive) && react_1.default.createElement("a", { className: "button", href: (0, api_1.exportUrl)(p.state.project.id, backup.path || backup.archive, true) }, "Download backup")),
            react_1.default.createElement("h2", null, "Restore a project copy"),
            p.session.can_create ? react_1.default.createElement("form", { className: "form-stack", onSubmit: restore },
                react_1.default.createElement("p", null, "The original project is never overwritten. The backup is validated before the restored folder becomes available."),
                react_1.default.createElement("label", { className: "field" },
                    react_1.default.createElement("span", null, "Project backup file (up to 1 GiB)"),
                    react_1.default.createElement("input", { type: "file", accept: ".zip", required: true, onChange: (e) => setRestoreFile(e.target.files?.[0] || null) })),
                react_1.default.createElement("label", { className: "field" },
                    react_1.default.createElement("span", null, "New project folder name"),
                    react_1.default.createElement("input", { required: true, pattern: "[a-z0-9]+(?:-[a-z0-9]+)*", value: restoreSlug, onChange: (e) => setRestoreSlug(e.target.value) })),
                react_1.default.createElement("label", { className: "inline-check" },
                    react_1.default.createElement("input", { type: "checkbox", checked: confirmed, onChange: (e) => setConfirmed(e.target.checked), required: true }),
                    "Restore into a new project folder."),
                react_1.default.createElement("button", { disabled: busy || !confirmed || !restoreFile }, "Validate and restore backup")) : react_1.default.createElement("p", null, "To restore a standalone project, use the Storyboarder command line and choose a new, empty destination folder."),
            react_1.default.createElement("h2", null, "Archived items"),
            p.state.entities.filter(e => e.archived).map(e => react_1.default.createElement("div", { className: "archive-row", key: e.id },
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, e.title),
                    react_1.default.createElement("small", null, (0, utils_1.kindLabel)(e))),
                react_1.default.createElement("button", { onClick: () => p.action('entity.restore', (0, utils_1.commandDefaults)(e)) }, "Restore item"),
                react_1.default.createElement("button", { onClick: () => p.select(e.id) }, "Details"))),
            !p.state.entities.some(e => e.archived) && react_1.default.createElement("p", { className: "muted" }, "No archived items.")))); }
function AutomationPage(p) { const [selected, setSelected] = (0, react_1.useState)(null), [preview, setPreview] = (0, react_1.useState)(null), [error, setError] = (0, react_1.useState)(''); (0, react_1.useEffect)(() => { let alive = true; if (selected)
    (0, api_1.api)((0, api_1.projectPath)(p.state.project.id, `/jobs/${selected}/preview`)).then(r => alive && setPreview(r)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, [selected, p.state]); const job = selected ? p.state.jobs.find(j => j.id === selected) : null; return react_1.default.createElement(react_1.default.Fragment, null,
    react_1.default.createElement(Primitives_1.PageHeading, { eyebrow: "Image tools", title: "Create images with your tools.", description: "Choose story details and reference images, then review the results before adding them to your project.", actions: react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.create'), disabled: !p.meta.scripts.length }, "Prepare image request") }),
    react_1.default.createElement("div", { className: "notice warning" },
        react_1.default.createElement("strong", null, "Only run tools you trust."),
        " A tool runs on this computer and may access files available to your account. Review the tool before running it."),
    react_1.default.createElement("section", null,
        react_1.default.createElement("h2", null, "Available image tools"),
        p.meta.scripts.length ? react_1.default.createElement("div", { className: "script-list" }, p.meta.scripts.map(s => react_1.default.createElement("div", { className: "script-row", key: s.name },
            react_1.default.createElement("strong", null, s.name),
            react_1.default.createElement("p", null, s.description || 'No description provided.'),
            react_1.default.createElement("small", null,
                "Maximum run time ",
                s.timeout,
                " seconds")))) : react_1.default.createElement("div", { className: "empty compact" },
            react_1.default.createElement("h3", null, "No image tools available"),
            react_1.default.createElement("p", null, "Add a trusted image tool to use it here. You can create and organize the rest of your project without one."),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Advanced setup"),
                react_1.default.createElement("p", null, "Connect a compatible image tool by registering its command with the Storyboarder CLI."),
                react_1.default.createElement("code", null, "storyboarder script register sample --command '[\"/path/to/python\", \"/path/to/image_tool.py\"]'")))),
    react_1.default.createElement("div", { className: "automation-columns" },
        react_1.default.createElement("section", null,
            react_1.default.createElement("h2", null, "Recent activity"),
            p.state.jobs.map(j => react_1.default.createElement("button", { key: j.id, className: `job-row ${j.id === selected ? 'is-selected' : ''}`, onClick: () => setSelected(j.id) },
                react_1.default.createElement("div", null,
                    react_1.default.createElement("strong", null, j.title),
                    react_1.default.createElement("small", null,
                        j.script,
                        " \u00B7 ",
                        (0, utils_1.human)(j.target))),
                react_1.default.createElement(Primitives_1.Badge, { kind: j.status }, j.approved ? 'Added to project' : j.status === 'succeeded' ? 'Ready for review' : (0, utils_1.human)(j.status)))),
            !p.state.jobs.length && react_1.default.createElement("p", { className: "muted" }, "Nothing to review yet. Prepare an image request to get started.")),
        react_1.default.createElement("section", null, job && preview ? react_1.default.createElement(react_1.default.Fragment, null,
            react_1.default.createElement("div", { className: "section-heading" },
                react_1.default.createElement("h2", null, job.title),
                react_1.default.createElement(Primitives_1.Badge, null, (0, utils_1.human)(job.status))),
            react_1.default.createElement("div", { className: "button-row" },
                job.status === 'queued' && react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.run', (0, utils_1.commandDefaults)(job)) }, "Run tool\u2026"),
                ['queued', 'running'].includes(job.status) && react_1.default.createElement("button", { onClick: () => p.action('job.cancel', (0, utils_1.commandDefaults)(job)) }, "Cancel\u2026"),
                ['failed', 'cancelled'].includes(job.status) && react_1.default.createElement("button", { onClick: () => p.action('job.retry', (0, utils_1.commandDefaults)(job)) }, "Run again\u2026"),
                job.status === 'succeeded' && !job.approved && react_1.default.createElement("button", { className: "primary", onClick: () => p.action('job.approve', (0, utils_1.commandDefaults)(job)) }, "Add reviewed images to project\u2026")),
            error && react_1.default.createElement(Primitives_1.ErrorNotice, { error: error }),
            react_1.default.createElement("div", { className: "generated-output-grid" }, (preview.outputs || preview.result?.outputs || job.result?.outputs || []).map((o, index) => react_1.default.createElement("article", { key: o.key },
                react_1.default.createElement("img", { src: (0, api_1.jobImageUrl)(p.state.project.id, job.id, o.key), alt: o.title ? `Image result ${o.title}` : `Image result ${index + 1}` }),
                react_1.default.createElement("h3", null, o.title || `Image ${index + 1}`),
                react_1.default.createElement("p", null, o.notes),
                react_1.default.createElement("small", null,
                    o.width,
                    " \u00D7 ",
                    o.height)))),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Technical details \u00B7 run log"),
                react_1.default.createElement("pre", null, typeof preview.logs === 'string' ? preview.logs : JSON.stringify(preview.logs || preview.log || {}, null, 2))),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Technical details \u00B7 tool inputs"),
                react_1.default.createElement("pre", null, JSON.stringify(job.request, null, 2))),
            react_1.default.createElement("details", null,
                react_1.default.createElement("summary", null, "Technical details \u00B7 tool results"),
                react_1.default.createElement("pre", null, JSON.stringify(job.result, null, 2)))) : react_1.default.createElement(Primitives_1.Empty, { title: "Choose an image request" }, "Review its images and notes before adding the results to the project.")))); }

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
exports.activeEntities = exports.kindLabel = exports.niceDate = exports.fieldText = exports.shortId = exports.sourceLabel = exports.operationLabel = exports.roleLabel = exports.statusLabel = exports.emptySourceMessage = exports.fieldLabel = exports.displayTitle = exports.human = void 0;
exports.allRecords = allRecords;
exports.commandDefaults = commandDefaults;
exports.selectOptions = selectOptions;
const labels = {
    asset: 'Library item', context: 'Story direction', scene: 'Scene', location_id: 'Location', visual_style: 'Visual style', premise: 'Story premise',
    arc: 'Sequence direction', tone: 'Tone', framing: 'Framing', camera: 'Camera plan', time: 'Time of day',
    constraints: 'Production notes', owner_id: 'Apply direction to', key: 'Topic', content: 'Direction notes',
    operation: 'How this changes earlier direction', revision: 'Version check', target_revision: 'Version check',
    parent_id: 'Place under', position: 'Order', shot_id: 'Shot', asset_id: 'Library item', media_id: 'Image',
    accepted: 'Added', discarded: 'Removed from intake', pending: 'Needs review', running: 'In progress', succeeded: 'Complete', failed: 'Needs attention', cancelled: 'Stopped',
    selected: 'Selected', approved: 'Approved', archived: 'Archived', queued: 'Ready to run', draft: 'Draft',
    append: 'Add to earlier notes', replace: 'Replace earlier notes', exclude: 'Hide earlier notes here',
    order: 'Story order', relationship: 'Library connection', assignment: 'Shot reference', location_default: 'Default location',
    story: 'Story flow', assets: 'Reference map', frame: 'Storyboard image', record: 'Item',
    character: 'Character', location: 'Location', prop: 'Prop', reference: 'General reference',
    'same-person-as': 'Same person as', 'appears-at': 'Appears at', 'alternate-view-of': 'Alternate view of',
    'setting-reference': 'Location reference', 'part-of': 'Part of', 'inspired-by': 'Inspired by', 'related-to': 'Related to', 'wears': 'Wears',
    create_title: 'New item name', create_type: 'Item type', include_media: 'Include images in package',
    approved_only: 'Use approved frames only', recursive: 'Include images in subfolders',
};
const human = (value) => labels[value] || value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
exports.human = human;
const displayTitle = (value) => /^[A-Z0-9]+(?:_[A-Z0-9]+)+$/.test(value) ? value.split('_').map(part => /^\d+$/.test(part) ? part : part.charAt(0) + part.slice(1).toLowerCase()).join(' ') : value;
exports.displayTitle = displayTitle;
const fieldLabel = (name, fallback) => labels[name] || fallback || (0, exports.human)(name);
exports.fieldLabel = fieldLabel;
const emptySourceMessage = (source) => ({
    assets: 'No library items to choose from yet. Create one first.',
    sequences: 'No sequences to choose from yet. Create one first.',
    scenes: 'No scenes to choose from yet. Create one first.',
    shots: 'No shots to choose from yet. Create one first.',
    locations: 'No locations to choose from yet. Add one to the reference library first.',
    media: 'No project images yet. Import an image first.',
    asset_images: 'No images in this library item yet. Add one first.',
    story: 'No story levels to choose from yet. Create a sequence, scene, or shot first.',
    parents: 'No suitable place to add this yet. Create a sequence or scene first.',
    scripts: 'No image tools are connected yet. Use the Storyboarder CLI to add a trusted tool.',
}[source] || 'Nothing to choose from yet. Add the item first.');
exports.emptySourceMessage = emptySourceMessage;
const statusLabel = (value) => (0, exports.human)(value);
exports.statusLabel = statusLabel;
const roleLabel = (value) => ({ subject: 'Subject', 'setting-reference': 'Location', costume: 'Wardrobe', prop: 'Prop', reference: 'General reference' }[value] || (0, exports.human)(value));
exports.roleLabel = roleLabel;
const operationLabel = (value) => ({ append: 'Added here', replace: 'Earlier direction replaced here', exclude: 'Earlier direction hidden here' }[value] || (0, exports.human)(value));
exports.operationLabel = operationLabel;
const sourceLabel = (kind) => ({ project: 'Project', sequence: 'Sequence', scene: 'Scene', shot: 'Shot', asset: 'Library item' }[kind] || (0, exports.human)(kind));
exports.sourceLabel = sourceLabel;
const shortId = (id) => id.slice(0, 8);
exports.shortId = shortId;
const fieldText = (value) => value == null ? '' : String(value);
exports.fieldText = fieldText;
const niceDate = (value) => new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value));
exports.niceDate = niceDate;
const kindLabel = (e) => e.kind === 'asset' ? (0, exports.human)((0, exports.fieldText)(e.fields.type)) : (0, exports.sourceLabel)(e.kind);
exports.kindLabel = kindLabel;
const activeEntities = (state, kind) => state.entities.filter(e => !e.archived && (!kind || e.kind === kind));
exports.activeEntities = activeEntities;
function allRecords(state) { return [...state.entities, ...state.media, ...state.intake, ...state.asset_media, ...state.links, ...state.assignments, ...state.context_blocks, ...state.frames, ...state.layouts, ...state.jobs]; }
function commandDefaults(entity) {
    if (!entity)
        return {};
    return { ...entity, ...(entity.fields || {}), id: entity.id, revision: entity.revision, ...(entity.kind && entity.kind !== 'asset' ? { owner_id: entity.id } : {}), ...(entity.kind === 'shot' ? { shot_id: entity.id } : {}), ...(entity.kind === 'asset' ? { asset_id: entity.id, source_id: entity.id } : {}), ...(entity.key ? { content: entity.text } : {}), tags: entity.tags || [], aliases: entity.aliases || [] };
}
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
        let label = (0, exports.displayTitle)(r.title || r.original_name || r.name || r.key || 'Untitled item');
        if (source === 'frames')
            label = `${(0, exports.displayTitle)(byId[r.shot_id]?.title || 'Shot')} · image ${r.version} · ${(0, exports.statusLabel)(r.state)}`;
        if (source === 'asset_media')
            label = `${(0, exports.displayTitle)(byId[r.asset_id]?.title || 'Library item')} / ${state.media.find(m => m.id === r.media_id)?.original_name || 'Image'}${r.is_primary ? ' · cover image' : ''}`;
        if (source === 'links')
            label = `${(0, exports.displayTitle)(byId[r.source_id]?.title || 'Item')} → ${(0, exports.human)(r.relation)} → ${(0, exports.displayTitle)(byId[r.target_id]?.title || 'Item')}`;
        if (source === 'assignments')
            label = `${(0, exports.displayTitle)(byId[r.shot_id]?.title || 'Shot')} → ${(0, exports.roleLabel)(r.role)} → ${(0, exports.displayTitle)(byId[r.asset_id]?.title || 'Library item')}`;
        if (source === 'intake')
            label = `${r.original_name} · ${(0, exports.statusLabel)(r.state)}${r.duplicate ? ' · identical image' : ''}`;
        return { value: r.id, label };
    });
}

}};
const cache={};function load(id){if(cache[id])return cache[id].exports;if(!modules[id])throw Error('Missing app module '+id);const m=cache[id]={exports:{}};function req(relative){const parts=id.split('/');parts.pop();for(const p of relative.split('/')){if(p==='.'||!p)continue;if(p==='..')parts.pop();else parts.push(p)}return load(parts.join('/').replace(/\.js$/,''));}modules[id](req,m,m.exports);return m.exports;}load('main');})();
