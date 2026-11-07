import { Eye, Layers, Maximize, Minimize, Minus, Plus, RotateCcw, ScanSearch, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useAuthedImage } from "../hooks/useApi";
import type { DetectedObject, Finding } from "../types";
import { categoryLabel } from "../utils/format";

interface Props {
  imageId: string;
  width: number;
  height: number;
  hasProcessed: boolean;
  objects: DetectedObject[];
  findings: Finding[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  initialOpacity?: number;
}

const OBJECT_COLOUR = "#3cc6dd";
const FINDING_COLOUR = "#ff8a5c";
const MANUAL_COLOUR = "#f2c94c";

function IconButton({ icon: Icon, label, onClick, active }: { icon: LucideIcon; label: string; onClick: () => void; active?: boolean }) {
  return (
    <button type="button" aria-label={label} title={label} aria-pressed={active} onClick={onClick}
      className={`flex h-7 w-7 items-center justify-center rounded ${active ? "bg-accent-dim text-accent-strong" : "text-text-2 hover:bg-ink-700 hover:text-text-1"}`}>
      <Icon className="h-4 w-4" />
    </button>
  );
}

export function ImageViewer({ imageId, width, height, hasProcessed, objects, findings, selectedId, onSelect, initialOpacity = 0.45 }: Props) {
  const [mode, setMode] = useState<"original" | "processed">("original");
  const [showObjects, setShowObjects] = useState(true);
  const [showFindings, setShowFindings] = useState(true);
  const [opacity, setOpacity] = useState(initialOpacity);
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const shell = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  const variant = mode === "processed" && hasProcessed ? "processed" : "display";
  const { src, failed } = useAuthedImage(`/images/${imageId}/file?variant=${variant}`);
  const overlaysVisible = mode === "original" || !hasProcessed;

  const computeFit = useCallback(() => {
    const element = viewport.current;
    if (!element) return 1;
    return Math.min((element.clientWidth - 16) / width, (element.clientHeight - 16) / height);
  }, [width, height]);

  const fitToScreen = useCallback(() => {
    const value = computeFit();
    setFit(value);
    setZoom(value);
  }, [computeFit]);

  useLayoutEffect(fitToScreen, [fitToScreen, imageId, fullscreen]);
  useEffect(() => {
    const observer = new ResizeObserver(() => setFit(computeFit()));
    if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, [computeFit]);
  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === shell.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  // Bring the selected finding into view when it is off-screen.
  useEffect(() => {
    const element = viewport.current;
    const target = [...findings, ...objects].find((item) => item.id === selectedId);
    if (!element || !target) return;
    element.scrollTo({
      left: (target.x + target.width / 2) * zoom - element.clientWidth / 2,
      top: (target.y + target.height / 2) * zoom - element.clientHeight / 2,
      behavior: "smooth",
    });
    // Only selection changes should scroll, not every zoom step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void shell.current?.requestFullscreen?.();
  };
  const changeZoom = (factor: number) => setZoom((z) => Math.min(8, Math.max(0.05, z * factor)));

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    const element = viewport.current;
    if (!element || (event.target as Element).closest("[data-region]")) return;
    drag.current = { x: event.clientX, y: event.clientY, left: element.scrollLeft, top: element.scrollTop };
    element.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const element = viewport.current;
    if (!element || !drag.current) return;
    element.scrollLeft = drag.current.left - (event.clientX - drag.current.x);
    element.scrollTop = drag.current.top - (event.clientY - drag.current.y);
  };

  const strokeWidth = 2 / zoom;
  const fontSize = 12 / zoom;
  const percent = Math.round(zoom * 100);

  return (
    <div ref={shell} className="flex h-full min-h-0 flex-col bg-ink-950">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-ink-700 bg-ink-850 px-2 py-1.5">
        <div className="flex items-center gap-0.5">
          <IconButton icon={Minus} label="Zoom out" onClick={() => changeZoom(1 / 1.25)} />
          <span className="data w-11 text-center text-xs text-text-2" aria-live="polite">{percent}%</span>
          <IconButton icon={Plus} label="Zoom in" onClick={() => changeZoom(1.25)} />
          <IconButton icon={ScanSearch} label="Fit to screen" onClick={fitToScreen} active={Math.abs(zoom - fit) < 0.001} />
          <IconButton icon={RotateCcw} label="Reset zoom to 100%" onClick={() => setZoom(1)} />
          <IconButton icon={fullscreen ? Minimize : Maximize} label={fullscreen ? "Exit full screen" : "Full screen"} onClick={toggleFullscreen} />
        </div>
        <div className="flex items-center gap-1 rounded bg-ink-900 p-0.5 text-xs" role="group" aria-label="Image shown">
          {(["original", "processed"] as const).map((value) => (
            <button key={value} type="button" disabled={value === "processed" && !hasProcessed} aria-pressed={mode === value} onClick={() => setMode(value)}
              className={`rounded px-2 py-0.5 disabled:opacity-40 ${mode === value ? "bg-ink-700 text-text-1" : "text-text-3 hover:text-text-1"}`}>
              {value === "original" ? "Original" : "Processed"}
            </button>
          ))}
        </div>
        <div className={`flex flex-wrap items-center gap-2 text-xs text-text-2 ${overlaysVisible ? "" : "opacity-40"}`}>
          <label className="flex items-center gap-1"><input type="checkbox" className="accent-accent" disabled={!overlaysVisible} checked={showObjects} onChange={(e) => setShowObjects(e.target.checked)} /><Eye className="h-3 w-3" style={{ color: OBJECT_COLOUR }} />Objects</label>
          <label className="flex items-center gap-1"><input type="checkbox" className="accent-accent" disabled={!overlaysVisible} checked={showFindings} onChange={(e) => setShowFindings(e.target.checked)} /><Layers className="h-3 w-3" style={{ color: FINDING_COLOUR }} />Findings</label>
          <label className="flex items-center gap-1.5">Mask<input aria-label="Mask opacity" type="range" min={0} max={1} step={0.05} value={opacity} disabled={!overlaysVisible} onChange={(e) => setOpacity(Number(e.target.value))} className="w-20 accent-accent" /></label>
        </div>
      </div>
      <div ref={viewport} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null; }}
        className="relative min-h-0 flex-1 cursor-grab overflow-auto active:cursor-grabbing"
        onClick={(e) => { if (!(e.target as Element).closest("[data-region]")) onSelect(null); }}>
        <div className="relative m-2 mx-auto" style={{ width: width * zoom, height: height * zoom }}>
          {failed && <div className="p-6 text-sm text-red-300">The image could not be loaded.</div>}
          {src ? <img src={src} alt="Inspection view" draggable={false} className="block h-full w-full select-none" /> : !failed && <div className="h-full w-full animate-pulse bg-ink-800" />}
          {overlaysVisible && (
            <svg viewBox={`0 0 ${width} ${height}`} className="absolute inset-0 h-full w-full" role="img" aria-label="Detection overlays">
              {showObjects && objects.map((o) => {
                const selected = o.id === selectedId;
                return (
                  <g key={o.id} data-region className="cursor-pointer" onClick={() => onSelect(o.id)}>
                    {o.polygon && <polygon points={o.polygon.map((p) => p.join(",")).join(" ")} fill={OBJECT_COLOUR} fillOpacity={opacity * 0.6} stroke="none" />}
                    <rect x={o.x} y={o.y} width={o.width} height={o.height} fill="transparent" stroke={OBJECT_COLOUR} strokeWidth={selected ? strokeWidth * 2 : strokeWidth} />
                    <text x={o.x + 3 / zoom} y={o.y + fontSize + 1 / zoom} fontSize={fontSize} fill="#fff" stroke="#0a111d" strokeWidth={3 / zoom} paintOrder="stroke" fontWeight={600}>
                      {o.label} {o.confidence.toFixed(2)}
                    </text>
                  </g>
                );
              })}
              {showFindings && findings.map((f) => {
                const selected = f.id === selectedId;
                const colour = f.finding_type === "manual_inspection" ? MANUAL_COLOUR : FINDING_COLOUR;
                const dimmed = f.review_status === "false_positive";
                return (
                  <g key={f.id} data-region className="cursor-pointer" opacity={dimmed ? 0.35 : 1} onClick={() => onSelect(f.id)}>
                    {f.polygon && <polygon points={f.polygon.map((p) => p.join(",")).join(" ")} fill={colour} fillOpacity={opacity} stroke={colour} strokeWidth={strokeWidth / 2} />}
                    <rect x={f.x} y={f.y} width={f.width} height={f.height} fill="transparent" stroke={colour} strokeWidth={selected ? strokeWidth * 2 : strokeWidth} strokeDasharray={selected ? undefined : `${6 / zoom} ${4 / zoom}`} />
                    <text x={f.x + 3 / zoom} y={f.y - 4 / zoom > fontSize ? f.y - 4 / zoom : f.y + fontSize + 2 / zoom} fontSize={fontSize} fill="#fff" stroke="#0a111d" strokeWidth={3 / zoom} paintOrder="stroke" fontWeight={600}>
                      {categoryLabel(f.category)}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>
      </div>
    </div>
  );
}
