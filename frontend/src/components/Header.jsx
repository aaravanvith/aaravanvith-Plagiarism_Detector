import { Activity, BookOpen, Database, FileSearch, History, Menu, ShieldCheck, Wifi, WifiOff, X } from "lucide-react";
import { useEffect, useState } from "react";
import { coreStatus } from "../api";

export default function Header({ view, setView }) {
  const [open, setOpen] = useState(false);
  const [core, setCore] = useState(null);
  useEffect(() => { coreStatus().then(setCore).catch(() => setCore({ configured: false })); }, []);
  const pages = {
    analyze: ["Analyze Report", "Submit a report and review explainable academic-integrity evidence."],
    history: ["Analysis History", "Review previously analyzed academic submissions."],
    repository: ["Academic Repository", "Manage the local research reference corpus."],
  };
  const nav = [["analyze", "Analyze Report", FileSearch], ["history", "Analysis History", History], ["repository", "Academic Repository", Database]];
  const changeView = (next) => { setView(next); setOpen(false); };
  return (
    <>
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-ink-900 px-5 py-6 text-white transition-transform lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-start justify-between"><div className="flex gap-3"><div className="grid h-11 w-11 place-items-center rounded-xl bg-seal-500"><ShieldCheck className="h-6 w-6" /></div><div><h1 className="font-display text-lg font-semibold">VTU Academic Integrity</h1><p className="mt-0.5 text-[10px] uppercase tracking-[.14em] text-ink-200">Healthcare Research Platform</p></div></div><button onClick={() => setOpen(false)} aria-label="Close navigation" className="lg:hidden"><X /></button></div>
        <nav className="mt-12 space-y-1" aria-label="Main navigation">{nav.map(([id, label, Icon]) => <button key={id} onClick={() => changeView(id)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-medium transition ${view === id ? "bg-white/12 text-white" : "text-ink-200 hover:bg-white/8 hover:text-white"}`}><Icon className="h-4 w-4 text-seal-400" />{label}</button>)}</nav>
        <div className="mt-auto space-y-3 border-t border-white/10 pt-5 text-xs"><div className="flex items-center gap-2 text-ink-200"><Activity className="h-3.5 w-3.5 text-risk-low" />System operational</div><div className="flex items-center gap-2 text-ink-200">{core?.configured ? <Wifi className="h-3.5 w-3.5 text-seal-400" /> : <WifiOff className="h-3.5 w-3.5 text-ink-400" />}CORE {core?.configured ? "configured" : "not configured"}</div><div className="flex items-center gap-2 text-ink-200"><BookOpen className="h-3.5 w-3.5 text-seal-400" />Local repository available</div></div>
      </aside>
      {open && <button onClick={() => setOpen(false)} aria-label="Close navigation overlay" className="fixed inset-0 z-40 bg-ink-900/40 lg:hidden" />}
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-white/95 backdrop-blur lg:ml-72"><div className="flex min-h-[82px] items-center justify-between px-5 sm:px-8"><div className="flex items-center gap-3"><button onClick={() => setOpen(true)} aria-label="Open navigation" className="rounded-md p-2 text-ink-600 lg:hidden"><Menu /></button><div><p className="font-display text-xl font-semibold text-ink-900">{pages[view][0]}</p><p className="hidden text-sm text-ink-400 md:block">{pages[view][1]}</p></div></div><div className="hidden items-center gap-3 sm:flex"><div className="h-9 w-9 rounded-full bg-seal-400/15 text-center leading-9 text-sm font-semibold text-seal-600">VT</div><div className="text-right text-xs"><p className="font-medium text-ink-800">VTU Workspace</p><p className="text-ink-400">Academic portal</p></div></div></div></header>
    </>
  );
}
