import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import {
  forceSimulation,
  forceManyBody,
  forceCenter,
  forceCollide,
} from 'd3-force';
import { apiFetch } from '../api/client';

interface Node {
  id: string;
  name: string;
  type: 'character' | 'location' | 'object' | 'event';
  icon: string;
  subtype: string;
  degree: number;
  properties: Record<string, any>;
  x: number;
  y: number;
}

interface Edge {
  id: string;
  from: string;
  to: string;
  type: string;
  color: string;
  dashed?: boolean;
}

export const WorldGraph: React.FC = () => {
  const { worldId } = useParams<{ worldId: string }>();
  const { setActiveEntity, manuscripts } = useWorldStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState({
    character: true,
    location: true,
    object: true,
    event: true,
  });

  // Time-slice state: null means "latest" (§16)
  const [asOfChapter, setAsOfChapter] = useState<number | null>(null);

  // Available chapters for time slider
  const chapters = manuscripts.flatMap((m) => m.chapters || []).sort((a, b) => a.number - b.number);
  const maxChapter = chapters.length > 0 ? Math.max(...chapters.map((c) => c.number)) : 2;

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(false);

  // Canvas Pan & Zoom state
  const [zoomScale, setZoomScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  // Node Dragging state
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const nodeStartPos = useRef({ x: 0, y: 0 });
  const dragDistanceRef = useRef(0);

  // Canvas Panning state
  const [isPanning, setIsPanning] = useState(false);
  const panStartPos = useRef({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Hovered node state for highlighting connections
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    if (!worldId) return;
    setLoading(true);
    try {
      const query = asOfChapter !== null ? `?as_of_chapter=${asOfChapter}` : '';
      const data = await apiFetch<any>(`/worlds/${worldId}/graph${query}`);
      if (data && data.nodes) {
        const containerW = containerRef.current?.clientWidth || 900;
        const containerH = containerRef.current?.clientHeight || 600;
        const centerX = containerW / 2;
        const centerY = containerH / 2;

        const fetchedNodes: Node[] = data.nodes.map((ent: any) => {
          const t = (ent.type || ent.entity_type || 'character').toLowerCase();
          return {
            id: ent.id,
            name: ent.label || ent.canonical_name || 'Entity',
            type: t as Node['type'],
            icon:
              t === 'character'
                ? 'group'
                : t === 'location'
                ? 'location_on'
                : t === 'object'
                ? 'category'
                : 'event_note',
            subtype: t,
            degree: ent.degree || 0,
            properties: ent.properties || {},
            x: centerX + (Math.random() - 0.5) * 450,
            y: centerY + (Math.random() - 0.5) * 350,
          };
        });

        const fetchedEdges: Edge[] = (data.edges || []).map((rel: any) => ({
          id: rel.id,
          from: rel.source,
          to: rel.target,
          type: rel.type || 'RELATED_TO',
          color: rel.type === 'ENEMY_OF' ? '#ffb4ab' : '#E6A27E',
          dashed: rel.type === 'ENEMY_OF',
        }));

        const simulation = forceSimulation(fetchedNodes)
          .force('charge', forceManyBody().strength(-450))
          .force('center', forceCenter(centerX, centerY))
          .force('collide', forceCollide().radius(70))
          .stop();

        for (let i = 0; i < 300; ++i) {
          simulation.tick();
        }

        setNodes([...fetchedNodes]);
        setEdges(fetchedEdges);
      }
    } catch (err) {
      console.error('Failed to fetch graph data:', err);
    } finally {
      setLoading(false);
    }
  }, [worldId, asOfChapter]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // Non-passive wheel listener for Ctrl + Scroll zoom & trackpad pinch
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
        setZoomScale((prevScale) => {
          const newScale = Math.min(Math.max(prevScale * zoomFactor, 0.25), 3.0);
          setPan((prevPan) => ({
            x: mouseX - ((mouseX - prevPan.x) / prevScale) * newScale,
            y: mouseY - ((mouseY - prevPan.y) / prevScale) * newScale,
          }));
          return newScale;
        });
      } else {
        // Standard wheel pans canvas
        setPan((prev) => ({
          x: prev.x - e.deltaX,
          y: prev.y - e.deltaY,
        }));
      }
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, []);

  // Keyboard navigation (+, -, 0, Arrow keys)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        setZoomScale((z) => Math.min(z * 1.15, 3.0));
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        setZoomScale((z) => Math.max(z / 1.15, 0.25));
      } else if (e.key === '0' || e.key === 'Escape') {
        e.preventDefault();
        setZoomScale(1);
        setPan({ x: 0, y: 0 });
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setPan((p) => ({ ...p, x: p.x + 40 }));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setPan((p) => ({ ...p, x: p.x - 40 }));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setPan((p) => ({ ...p, y: p.y + 40 }));
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setPan((p) => ({ ...p, y: p.y - 40 }));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Node Dragging Handlers
  const handleNodeMouseDown = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent canvas pan
    e.preventDefault();
    const node = nodes.find((n) => n.id === nodeId);
    if (node) {
      setDraggingNodeId(nodeId);
      dragDistanceRef.current = 0;
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      nodeStartPos.current = { x: node.x, y: node.y };
    }
  };

  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    panStartPos.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingNodeId) {
      const dx = (e.clientX - dragStartPos.current.x) / zoomScale;
      const dy = (e.clientY - dragStartPos.current.y) / zoomScale;
      dragDistanceRef.current += Math.hypot(e.movementX || 0, e.movementY || 0);

      setNodes((prev) =>
        prev.map((n) =>
          n.id === draggingNodeId
            ? { ...n, x: nodeStartPos.current.x + dx, y: nodeStartPos.current.y + dy }
            : n
        )
      );
    } else if (isPanning) {
      setPan({
        x: e.clientX - panStartPos.current.x,
        y: e.clientY - panStartPos.current.y,
      });
    }
  };

  const handleMouseUp = () => {
    setDraggingNodeId(null);
    setIsPanning(false);
  };

  // Node Click: Only open info tab if NOT dragging (> 5px traveled)
  const handleNodeClick = (nodeId: string) => {
    if (dragDistanceRef.current > 5) {
      return; // Was dragging, don't open info tab
    }
    setActiveEntity(nodeId);
  };

  const getNodeColor = (type: Node['type']) => {
    switch (type) {
      case 'character':
        return 'border-copper-glow text-copper-glow shadow-[0_0_15px_rgba(230,162,126,0.1)]';
      case 'location':
        return 'border-secondary text-secondary shadow-[0_0_15px_rgba(194,198,214,0.1)]';
      case 'object':
        return 'border-tertiary text-tertiary shadow-[0_0_15px_rgba(200,198,197,0.1)]';
      case 'event':
        return 'border-error text-error shadow-[0_0_15px_rgba(255,180,171,0.1)]';
      default:
        return 'border-outline text-on-surface-variant';
    }
  };

  const isEdgeActive = (edge: Edge) => {
    if (!hoveredNodeId) return true;
    return edge.from === hoveredNodeId || edge.to === hoveredNodeId;
  };

  // Filter nodes & edges
  const visibleNodes = nodes.filter((n) => {
    const matchesFilter = filters[n.type];
    const matchesSearch =
      n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.subtype.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));

  const visibleEdges = edges.filter((e) => {
    return visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to);
  });

  const handleZoomIn = () => setZoomScale((prev) => Math.min(prev * 1.15, 3.0));
  const handleZoomOut = () => setZoomScale((prev) => Math.max(prev / 1.15, 0.25));
  const handleZoomFit = () => {
    setZoomScale(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <AppShell>
      <main className="flex-1 w-full h-full flex relative select-none overflow-hidden">
        {/* Left Control Sidebar */}
        <aside className="w-72 bg-surface-container-low/70 backdrop-blur-md border-r border-starlight-white/10 h-full flex flex-col z-10 shrink-0 select-none">
          <div className="p-gutter flex flex-col gap-6 h-full overflow-y-auto pt-8">
            {/* Search */}
            <div className="relative group">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-base group-focus-within:text-primary transition-colors font-light">
                search
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search network entities..."
                className="w-full bg-surface-container-highest/50 border border-starlight-white/10 rounded-lg px-9 py-2 font-body-md text-xs text-on-surface focus:border-primary focus:ring-0 focus:bg-surface-container-highest transition-all placeholder:text-on-surface-variant/40"
              />
            </div>

            {/* Time-Slice Slider Section (§16) */}
            <div className="bg-surface-container/50 border border-starlight-white/10 rounded-xl p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-[10px] text-primary uppercase tracking-wider font-semibold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm">history_toggle_off</span>
                  Time-Slice State
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary font-medium">
                  {asOfChapter !== null ? `Ch. ${asOfChapter}` : 'Latest'}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between text-[11px] text-on-surface-variant">
                  <span>As of Chapter:</span>
                  <span className="text-starlight-white font-medium">
                    {asOfChapter !== null ? `End of Chapter ${asOfChapter}` : 'Latest (End of Story)'}
                  </span>
                </div>

                <input
                  type="range"
                  min="1"
                  max={maxChapter}
                  step="1"
                  value={asOfChapter ?? maxChapter}
                  onChange={(e) => setAsOfChapter(parseInt(e.target.value, 10))}
                  className="w-full h-1.5 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-primary"
                />

                <div className="flex items-center justify-between text-[9px] text-on-surface-variant/60">
                  <span>Ch. 1</span>
                  <span>Ch. {maxChapter}</span>
                </div>

                <div className="flex gap-2 mt-1">
                  <button
                    onClick={() => setAsOfChapter(1)}
                    className={`flex-1 py-1 px-2 rounded text-[10px] transition-colors border ${
                      asOfChapter === 1
                        ? 'bg-primary/20 text-primary border-primary/40 font-semibold'
                        : 'bg-surface-container-high/60 text-on-surface-variant border-transparent hover:border-white/10'
                    }`}
                  >
                    Ch. 1
                  </button>
                  <button
                    onClick={() => setAsOfChapter(maxChapter)}
                    className={`flex-1 py-1 px-2 rounded text-[10px] transition-colors border ${
                      asOfChapter === maxChapter
                        ? 'bg-primary/20 text-primary border-primary/40 font-semibold'
                        : 'bg-surface-container-high/60 text-on-surface-variant border-transparent hover:border-white/10'
                    }`}
                  >
                    Ch. {maxChapter}
                  </button>
                  <button
                    onClick={() => setAsOfChapter(null)}
                    className={`flex-1 py-1 px-2 rounded text-[10px] transition-colors border ${
                      asOfChapter === null
                        ? 'bg-primary/20 text-primary border-primary/40 font-semibold'
                        : 'bg-surface-container-high/60 text-on-surface-variant border-transparent hover:border-white/10'
                    }`}
                  >
                    Latest
                  </button>
                </div>
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col gap-3">
              <h3 className="font-label-sm text-[10px] text-on-surface-variant uppercase tracking-widest border-b border-starlight-white/5 pb-2">
                Filter Network
              </h3>
              <div className="flex flex-col gap-2">
                {/* Characters */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input
                    type="checkbox"
                    checked={filters.character}
                    onChange={(e) => setFilters({ ...filters, character: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-primary focus:ring-primary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#E6A27E] shadow-[0_0_8px_rgba(230,162,126,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-primary transition-colors">Characters</span>
                </label>

                {/* Locations */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input
                    type="checkbox"
                    checked={filters.location}
                    onChange={(e) => setFilters({ ...filters, location: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-secondary focus:ring-secondary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#c2c6d6] shadow-[0_0_8px_rgba(194,198,214,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-secondary transition-colors">Locations</span>
                </label>

                {/* Objects */}
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group text-xs font-label-sm uppercase tracking-wider">
                  <input
                    type="checkbox"
                    checked={filters.object}
                    onChange={(e) => setFilters({ ...filters, object: e.target.checked })}
                    className="form-checkbox rounded bg-surface border-outline-variant/30 text-tertiary focus:ring-tertiary focus:ring-offset-surface-container-low w-4 h-4"
                  />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#c8c6c5] shadow-[0_0_8px_rgba(200,198,197,0.5)]"></div>
                  <span className="text-on-surface group-hover:text-tertiary transition-colors">Objects</span>
                </label>
              </div>
            </div>

            {/* Controls Guide */}
            <div className="mt-auto bg-surface-container-low p-4 rounded-lg border border-starlight-white/5 text-[11px] text-on-surface-variant/70 leading-relaxed font-body-md select-none space-y-1.5">
              <div className="font-semibold text-primary flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">keyboard</span>
                Canvas Navigation
              </div>
              <div>• <b>Ctrl + Scroll</b>: Zoom in/out at cursor</div>
              <div>• <b>Drag Background</b>: Pan canvas</div>
              <div>• <b>Drag Node</b>: Rearrange layout</div>
              <div>• <b>Single Click Node</b>: Open details</div>
              <div>• <b>+ / - / 0</b>: Zoom in/out/reset</div>
              <div>• <b>Arrow Keys</b>: Pan view</div>
            </div>
          </div>
        </aside>

        {/* Network Canvas */}
        <div
          ref={containerRef}
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className={`flex-1 relative bg-grid overflow-hidden h-full ${
            isPanning ? 'cursor-grabbing' : 'cursor-grab'
          }`}
        >
          {/* Top Right Floating bar */}
          <div className="absolute top-gutter right-gutter z-30 flex items-center gap-3.5 bg-surface-dim/80 backdrop-blur-md border border-starlight-white/10 rounded-full px-4 py-2 shadow-lg text-xs pointer-events-auto">
            <span className="text-on-surface-variant/80 font-label-sm uppercase tracking-wider">
              {asOfChapter !== null ? `Time Slice: Ch. ${asOfChapter}` : 'Chronicle Graph'}
            </span>
            <div className={`w-2 h-2 rounded-full ${loading ? 'bg-copper-glow animate-spin' : 'bg-primary animate-pulse'}`}></div>
          </div>

          {/* Unified Pan/Zoom Graph Container */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoomScale})`,
              transformOrigin: '0 0',
            }}
          >
            {/* SVG Edges Layer with overflow: visible to eliminate cutoff */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none z-0 overflow-visible"
              style={{ overflow: 'visible' }}
            >
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="28"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(230,162,126,0.6)" />
                </marker>
              </defs>
              {visibleEdges.map((edge) => {
                const fromNode = visibleNodes.find((n) => n.id === edge.from);
                const toNode = visibleNodes.find((n) => n.id === edge.to);

                if (!fromNode || !toNode) return null;

                const isHoveredRelated = isEdgeActive(edge);
                const opacity = hoveredNodeId ? (isHoveredRelated ? 0.9 : 0.15) : 0.45;
                const strokeWidth = hoveredNodeId && isHoveredRelated ? 2.2 : 1.4;

                return (
                  <line
                    key={edge.id}
                    x1={fromNode.x}
                    y1={fromNode.y}
                    x2={toNode.x}
                    y2={toNode.y}
                    stroke={edge.color}
                    strokeWidth={strokeWidth}
                    strokeDasharray={edge.dashed ? '4 4' : undefined}
                    opacity={opacity}
                    markerEnd="url(#arrow)"
                    className="transition-opacity duration-200"
                  />
                );
              })}
            </svg>

            {/* Nodes Layer */}
            {visibleNodes.map((node) => {
              const isHovered = hoveredNodeId === node.id;
              const isDimmed =
                hoveredNodeId &&
                hoveredNodeId !== node.id &&
                !edges.some(
                  (edge) =>
                    (edge.from === node.id && edge.to === hoveredNodeId) ||
                    (edge.to === node.id && edge.from === hoveredNodeId)
                );

              return (
                <div
                  key={node.id}
                  onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={() => handleNodeClick(node.id)}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 z-10 pointer-events-auto cursor-grab active:cursor-grabbing transition-opacity duration-200 select-none ${
                    isDimmed ? 'opacity-25 scale-95' : 'opacity-100 scale-100'
                  }`}
                  style={{ left: node.x, top: node.y }}
                >
                  <div className="relative group/node">
                    {/* Node Halo Ring on Hover */}
                    <div
                      className={`absolute -inset-4 rounded-full blur-lg opacity-0 transition-opacity duration-300 pointer-events-none ${
                        isHovered ? 'opacity-30 bg-primary' : 'group-hover/node:opacity-10 bg-primary/20'
                      }`}
                    />

                    {/* Core Circle */}
                    <div
                      className={`w-12 h-12 rounded-full bg-surface-container-high/95 border-2 flex items-center justify-center relative z-10 ${getNodeColor(
                        node.type
                      )} ${isHovered ? 'scale-110 border-primary' : 'group-hover/node:scale-105'} transition-transform duration-200`}
                    >
                      <span className="material-symbols-outlined text-xl font-light">{node.icon}</span>

                      {/* Degree Badge */}
                      {node.degree > 0 && (
                        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-surface-container-highest border border-starlight-white/20 text-[9px] text-primary flex items-center justify-center font-bold">
                          {node.degree}
                        </span>
                      )}
                    </div>

                    {/* Label */}
                    <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 whitespace-nowrap text-center pointer-events-none select-none">
                      <p
                        className={`font-body-md text-[11px] font-medium leading-none ${
                          isHovered ? 'text-starlight-white' : 'text-on-surface-variant'
                        }`}
                      >
                        {node.name}
                      </p>
                      <p className="font-label-sm text-[8px] text-on-surface-variant/40 uppercase tracking-widest mt-0.5 leading-none">
                        {node.subtype}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Canvas Zoom & Pan Navigation Controls (Bottom Right) */}
          <div className="absolute bottom-gutter right-gutter flex items-center gap-2 z-30 select-none">
            <button
              onClick={handleZoomIn}
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom In (+)"
            >
              <span className="material-symbols-outlined font-light">zoom_in</span>
            </button>
            <button
              onClick={handleZoomOut}
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container"
              title="Zoom Out (-)"
            >
              <span className="material-symbols-outlined font-light">zoom_out</span>
            </button>
            <button
              onClick={handleZoomFit}
              className="w-10 h-10 bg-surface-container-high/90 border border-starlight-white/10 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary/50 transition-all shadow-lg hover:bg-surface-container ml-1"
              title="Reset View (0)"
            >
              <span className="material-symbols-outlined font-light">fit_screen</span>
            </button>
          </div>
        </div>
      </main>
    </AppShell>
  );
};
