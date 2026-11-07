import { UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

export const ACCEPTED = ".jpg,.jpeg,.png,.webp";
const ALLOWED_EXTENSIONS = /\.(jpe?g|png|webp)$/i;
export const MAX_FILE_MB = 20;

/** Client-side checks are a convenience for fast feedback; the server validates every file again. */
export function clientRejection(file: File): string | null {
  if (!ALLOWED_EXTENSIONS.test(file.name)) return "Use JPEG, PNG or WebP.";
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `Larger than ${MAX_FILE_MB} MB.`;
  if (file.size === 0) return "The file is empty.";
  return null;
}

export function Dropzone({ onFiles, multiple = true, label, compact }: { onFiles: (files: File[]) => void; multiple?: boolean; label?: string; compact?: boolean }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    const files = [...event.dataTransfer.files];
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  };
  return (
    <button type="button"
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex w-full flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed text-center transition-colors ${compact ? "p-4" : "p-8"} ${over ? "border-accent bg-accent-dim/40" : "border-ink-600 hover:border-accent/60 hover:bg-ink-800"}`}>
      <UploadCloud className="h-6 w-6 text-text-3" />
      <span className="text-sm text-text-1">{label ?? "Drop images here, or click to browse"}</span>
      <span className="text-xs text-text-3">JPEG, PNG or WebP, up to {MAX_FILE_MB} MB each</span>
      <input ref={input} data-testid="file-input" type="file" accept={ACCEPTED} multiple={multiple} className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFiles([...e.target.files]);
          e.target.value = "";
        }} />
    </button>
  );
}
