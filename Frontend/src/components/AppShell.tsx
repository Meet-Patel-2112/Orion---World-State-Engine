import React, { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useNavigate } from 'react-router-dom';
import { useWorldStore } from '../store/useWorldStore';
import { AnimatePresence, motion } from 'framer-motion';
import { EntityPanel } from './EntityPanel';
import { ErrorBoundary } from './ErrorBoundary';
import { CreatorProfileModal } from './CreatorProfileModal';
import { SettingsModal } from './SettingsModal';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { worldId, manuscriptId } = useParams<{ worldId: string; manuscriptId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  
  const { 
    activeEntityId, 
    isEntityPanelOpen, 
    setEntityPanelOpen,
    setActiveWorld,
    activeWorldId,
    contradictions,
    worlds,
    manuscripts,
    activeChapterId
  } = useWorldStore();

  // The URL decides the world (a reload or a pasted link has no earlier selection in the store)
  useEffect(() => {
    if (worldId && worldId !== activeWorldId) setActiveWorld(worldId);
  }, [worldId, activeWorldId, setActiveWorld]);

  const currentPath = location.pathname;
  const currentWorldId = worldId;

  // Count open contradictions to show a badge on the navigation rail (rejected ones don't count)
  const unresolvedContradictionsCount = contradictions.filter(c => !c.resolved && c.status !== 'DISMISSED').length;
  const [openPanel, setOpenPanel] = useState<'profile' | 'settings' | null>(null);

  const navItems = [
    {
      path: `/worlds/${currentWorldId}`,
      icon: 'home',
      label: 'Home'
    },
    {
      path: `/worlds/${currentWorldId}/manuscripts`,
      icon: 'menu_book',
      label: 'Manuscripts'
    },
    {
      path: `/worlds/${currentWorldId}/world`,
      icon: 'public',
      label: 'World Ledger'
    },
    {
      path: `/worlds/${currentWorldId}/graph`,
      icon: 'bubble_chart',
      label: 'Network Graph'
    },
    {
      path: `/worlds/${currentWorldId}/timeline`,
      icon: 'timeline',
      label: 'Timeline'
    },
    {
      path: `/worlds/${currentWorldId}/contradictions`,
      icon: 'rule',
      label: 'Contradictions',
      badge: unresolvedContradictionsCount > 0 ? unresolvedContradictionsCount : undefined
    },
    {
      path: `/worlds/${currentWorldId}/assistant`,
      icon: 'chat_bubble_outline',
      label: 'AI Assistant'
    },
  ];

  const activeNavItem = navItems.find(item => currentPath === item.path ||
    (item.label === 'Manuscripts' && currentPath.startsWith(`${item.path}/`)));
  const manuscript = manuscripts.find(item => item.id === manuscriptId);
  const chapter = manuscript?.chapters.find(item => item.id === activeChapterId) || manuscript?.chapters[0];
  const pageTitle = manuscriptId ? 'Chapter Editor' : currentPath.endsWith('/processing') ? 'Processing World' : activeNavItem?.label || 'World';
  const worldName = worlds.find(item => item.id === worldId)?.name || 'World';

  useEffect(() => {
    document.title = `${pageTitle} · ${worldName} · Orion`;
  }, [pageTitle, worldName]);

  if (!worldId) return null;

  const handleReturnToArchive = () => {
    setActiveWorld(null);
    navigate('/worlds');
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-void-black text-on-surface select-none">
      
      {/* Labeled navigation stays visible on every world page. */}
      <nav aria-label="World navigation" className="fixed left-0 top-0 h-full w-[104px] bg-void-black border-r border-starlight-white/10 z-50 flex flex-col items-center py-4 justify-between select-none overflow-y-auto">
        
        {/* Brand/Logo Constellation Icon */}
        <div className="flex flex-col items-center gap-1 group cursor-pointer" onClick={handleReturnToArchive} title="Return to Archive">
          <div className="w-10 h-10 rounded-full border border-primary/30 flex items-center justify-center bg-surface-container overflow-hidden relative group-hover:border-primary transition-all duration-300">
            <span className="material-symbols-outlined text-primary text-2xl group-hover:scale-110 transition-transform font-extralight">bubble_chart</span>
          </div>
          <span className="font-label-sm text-[9px] text-on-surface-variant/40 uppercase tracking-wider group-hover:text-primary transition-colors">Orion</span>
        </div>

        {/* Primary Navigation Tabs */}
        <div className="flex-1 w-full flex flex-col gap-2 mt-8">
          {navItems.map((item) => {
            const isActive = currentPath === item.path || (item.path.includes('/manuscripts') && currentPath.includes('/manuscripts'));
            return (
              <Link 
                key={item.path} 
                to={item.path}
                aria-label={item.label}
                aria-current={isActive ? 'page' : undefined}
                className={`relative flex flex-col items-center justify-center py-4 transition-colors duration-300 w-full group ${
                  isActive 
                    ? 'text-primary bg-primary/5' 
                    : 'text-on-surface-variant/60 hover:text-primary hover:bg-white/5'
                }`}
                title={item.label}
              >
                {/* Active Indicator bar */}
                {isActive && (
                  <span className="absolute left-0 h-8 w-[2px] bg-primary shadow-[0_0_12px_rgba(254,182,141,0.6)]" />
                )}
                
                {/* Icon with hover scaling */}
                <span className={`material-symbols-outlined text-[22px] transition-transform duration-300 ${isActive ? 'fill font-light' : 'font-light group-hover:scale-110'}`}>
                  {item.icon}
                </span>
                <span className="text-[10px] leading-tight text-center mt-1 px-2">{item.label}</span>

                {/* Optional Badge */}
                {item.badge !== undefined && (
                  <span className="absolute top-2 right-2 w-4 h-4 rounded-full bg-error text-void-black text-[9px] font-label-sm font-bold flex items-center justify-center border border-void-black shadow-[0_0_8px_rgba(255,180,171,0.5)]">
                    {item.badge}
                  </span>
                )}
                
                {/* Tooltip on hover */}
                <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
                  {item.label}
                </span>
              </Link>
            );
          })}
        </div>

        {/* Secondary Actions / Footer */}
        <div className="w-full flex flex-col gap-1 border-t border-starlight-white/10 pt-4 mt-auto">

          <button
            onClick={() => setOpenPanel('profile')}
            className="flex flex-col items-center justify-center py-4 text-on-surface-variant/60 hover:text-primary hover:bg-white/5 transition-colors duration-300 w-full group relative"
            title="Profile"
          >
            <span className="material-symbols-outlined text-[22px] font-light group-hover:scale-110 transition-transform">person_outline</span>
            <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
              Creator Profile
            </span>
          </button>
          <button
            onClick={() => setOpenPanel('settings')}
            className="flex flex-col items-center justify-center py-4 text-on-surface-variant/60 hover:text-primary hover:bg-white/5 transition-colors duration-300 w-full group relative"
            title="Archive Settings"
          >
            <span className="material-symbols-outlined text-[22px] font-light group-hover:rotate-45 transition-transform duration-500">settings</span>
            <span className="opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 absolute left-full ml-4 bg-surface-container-high border border-starlight-white/10 px-3 py-1 rounded text-starlight-white text-xs font-label-sm pointer-events-none transition-all duration-200 z-50 whitespace-nowrap shadow-xl">
              Archive settings
            </span>
          </button>
        </div>
      </nav>

      {openPanel === 'profile' && <CreatorProfileModal onClose={() => setOpenPanel(null)} />}
      {openPanel === 'settings' && <SettingsModal worldId={worldId ?? null} onClose={() => setOpenPanel(null)} />}

      {/* Primary Stage */}
      <div className="flex-1 ml-[104px] min-w-0 h-full relative flex flex-col z-10 overflow-hidden bg-void-black">
        <header className="shrink-0 flex items-center gap-3 px-4 md:px-6 py-3 border-b border-starlight-white/10 bg-surface-container-lowest">
          <button
            onClick={() => window.history.state?.idx > 0 ? navigate(-1) : navigate('/worlds')}
            aria-label="Go back"
            title="Go back"
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-white/5 hover:text-primary"
          ><span className="material-symbols-outlined text-lg">arrow_back</span></button>
          <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-xs min-w-0">
            <Link to="/worlds" className="text-on-surface-variant/70 hover:text-primary">Worlds</Link>
            <span aria-hidden="true" className="text-on-surface-variant/30">/</span>
            <Link to={`/worlds/${worldId}`} className="text-on-surface-variant/70 hover:text-primary truncate max-w-48">{worldName}</Link>
            <span aria-hidden="true" className="text-on-surface-variant/30">/</span>
            {manuscriptId && <><Link to={`/worlds/${worldId}/manuscripts`} className="text-on-surface-variant/70 hover:text-primary">Manuscripts</Link><span aria-hidden="true" className="text-on-surface-variant/30">/</span></>}
            <span aria-current="page" className="text-primary font-medium">{pageTitle}</span>
            {manuscriptId && chapter && <span className="text-on-surface-variant/60 truncate">· Chapter {chapter.number}: {chapter.title}</span>}
          </nav>
        </header>
        <div className="flex flex-1 min-h-0 min-w-0 relative overflow-hidden [&>main]:min-h-0 [&>main]:h-full">{children}</div>
      </div>

      {/* Contextual Side Panel (Wings) */}
      <AnimatePresence>
        {isEntityPanelOpen && activeEntityId && (
          <>
            {/* Dark blur backdrop overlay */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setEntityPanelOpen(false)}
              className="fixed inset-0 bg-void-black/20 backdrop-blur-[2px] z-30 ml-[104px] cursor-pointer"
            />
            {/* Sidebar content container */}
            <motion.aside 
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 220 }}
              className="fixed right-0 top-0 bottom-0 w-[440px] sm:w-[480px] max-w-[100vw] z-40 h-full shrink-0"
            >
              <ErrorBoundary 
                fallbackTitle="Could not display entity"
                onReset={() => setEntityPanelOpen(false)}
              >
                <EntityPanel 
                  key={activeEntityId}
                  entityId={activeEntityId} 
                  onClose={() => setEntityPanelOpen(false)} 
                />
              </ErrorBoundary>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
