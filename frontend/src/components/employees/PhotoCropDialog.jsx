import React, { useCallback, useEffect, useRef, useState } from "react";
import Cropper from "react-easy-crop";
import { Loader2, Minus, Plus, RotateCcw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";

/*
 * Upgrade 01C carry-over - editor posisi/crop foto profil.
 * Alur: Pilih Foto -> Atur Posisi Wajah (drag) -> Zoom -> Preview lingkaran -> Simpan Foto.
 * - rasio 1:1, tanpa stretch (crop area selalu persegi dari piksel asli);
 * - orientasi foto HP: browser modern menerapkan EXIF orientation saat decode <img>/canvas;
 * - posisi awal: FaceDetector bawaan browser bila tersedia (hanya posisi awal, bukan identifikasi),
 *   selain itu heuristik potret -> sepertiga atas (area kepala + sedikit ruang di atas kepala).
 */
const OUTPUT_MAX = 800;
const MIN_ZOOM = 1;
const MAX_ZOOM = 4;

const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Gambar tidak dapat dibaca."));
    img.src = src;
  });

/* posisi awal crop (persentase) — kepala/wajah diprioritaskan */
async function initialArea(img) {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const side = Math.min(w, h);
  const pct = { width: (side / w) * 100, height: (side / h) * 100 };
  const clamp = (v, max) => Math.max(0, Math.min(v, max));
  try {
    if (typeof window !== "undefined" && "FaceDetector" in window) {
      const faces = await new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 }).detect(img);
      const box = faces?.[0]?.boundingBox;
      if (box) {
        const size = Math.min(side, Math.max(box.width, box.height) * 2.2);
        const cx = box.x + box.width / 2;
        const cy = box.y + box.height / 2 + box.height * 0.15; // sedikit turun -> ruang di atas kepala + bahu
        const x = clamp(cx - size / 2, w - size);
        const y = clamp(cy - size / 2, h - size);
        return { x: (x / w) * 100, y: (y / h) * 100, width: (size / w) * 100, height: (size / h) * 100 };
      }
    }
  } catch (_e) {
    /* deteksi opsional; abaikan kegagalan */
  }
  if (h > w) {
    // potret: wajah biasanya di sepertiga atas -> geser crop ke atas, sisakan sedikit ruang di atas kepala
    const y = clamp((h - side) * 0.18, h - side);
    return { x: 0, y: (y / h) * 100, ...pct };
  }
  return { x: ((w - side) / 2 / w) * 100, y: 0, ...pct };
}

async function renderCrop(img, area, size) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff"; // PNG/WEBP transparan -> latar putih (output JPEG)
  ctx.fillRect(0, 0, size, size);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, size, size);
  return canvas;
}

export const PhotoCropDialog = ({ file, open, onOpenChange, onSave, saving }) => {
  const [src, setSrc] = useState(null);
  const [img, setImg] = useState(null);
  const [initial, setInitial] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [areaPx, setAreaPx] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [resetKey, setResetKey] = useState(0);
  const timer = useRef(null);

  useEffect(() => {
    if (!file) return undefined;
    const url = URL.createObjectURL(file);
    let cancelled = false;
    setSrc(null);
    setImg(null);
    setPreview(null);
    setError(null);
    setZoom(1);
    setCrop({ x: 0, y: 0 });
    loadImage(url)
      .then(async (loaded) => {
        const area = await initialArea(loaded);
        if (cancelled) return;
        setInitial(area);
        setImg(loaded);
        setSrc(url);
      })
      .catch(() => !cancelled && setError("Gambar tidak dapat dibaca. Pilih file JPG, PNG, atau WEBP lain."));
    return () => {
      cancelled = true;
      URL.revokeObjectURL(url);
    };
  }, [file]);

  const onCropComplete = useCallback(
    (_pct, px) => {
      setAreaPx(px);
      if (!img) return;
      clearTimeout(timer.current);
      timer.current = setTimeout(async () => {
        const canvas = await renderCrop(img, px, 160);
        setPreview(canvas.toDataURL("image/jpeg", 0.85));
      }, 80);
    },
    [img],
  );

  useEffect(() => () => clearTimeout(timer.current), []);

  const save = async () => {
    if (!img || !areaPx) return;
    const size = Math.max(1, Math.min(OUTPUT_MAX, Math.round(areaPx.width)));
    const canvas = await renderCrop(img, areaPx, size);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) {
      setError("Foto gagal diproses. Coba lagi.");
      return;
    }
    const base = (file?.name || "foto").replace(/\.[^.]+$/, "");
    await onSave(new File([blob], `${base}-profil.jpg`, { type: "image/jpeg" }));
  };

  const step = (delta) => setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, +(z + delta).toFixed(2))));

  return (
    <Dialog open={open} onOpenChange={(v) => !saving && onOpenChange(v)}>
      <DialogContent className="max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-2xl overflow-y-auto p-4 sm:p-6" data-testid="photo-crop-dialog">
        <DialogHeader>
          <DialogTitle>Atur Posisi Foto Profil</DialogTitle>
          <DialogDescription>
            Geser foto agar wajah berada di tengah lingkaran, lalu atur zoom. Sisakan sedikit ruang di atas kepala.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert" data-testid="photo-crop-error">
            {error}
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-[1fr,10rem]">
          <div
            className="relative h-72 w-full touch-none overflow-hidden rounded-lg bg-muted sm:h-80"
            data-testid="photo-crop-area"
          >
            {src && initial ? (
              <Cropper
                key={resetKey}
                image={src}
                crop={crop}
                zoom={zoom}
                minZoom={MIN_ZOOM}
                maxZoom={MAX_ZOOM}
                aspect={1}
                cropShape="round"
                showGrid={false}
                objectFit="contain"
                restrictPosition
                initialCroppedAreaPercentages={resetKey === 0 ? initial : undefined}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            ) : (
              !error && (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Memuat foto...
                </div>
              )
            )}
          </div>

          <div className="flex flex-row items-center gap-4 sm:flex-col sm:items-start">
            <div className="text-center sm:text-left">
              <p className="mb-2 text-[12px] text-muted-foreground">Preview</p>
              {preview ? (
                <img
                  src={preview}
                  alt="Preview foto profil"
                  className="h-24 w-24 rounded-full border border-border object-cover sm:h-32 sm:w-32"
                  data-testid="photo-crop-preview"
                />
              ) : (
                <div className="h-24 w-24 rounded-full border border-dashed border-border bg-muted sm:h-32 sm:w-32" />
              )}
            </div>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              Tampilan ini sama dengan avatar di Profile 360.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3" data-testid="photo-crop-zoom">
          <Button type="button" size="icon" variant="outline" className="h-11 w-11 shrink-0 sm:h-9 sm:w-9"
            onClick={() => step(-0.2)} disabled={zoom <= MIN_ZOOM || !src} aria-label="Perkecil" data-testid="photo-crop-zoom-out">
            <Minus className="h-4 w-4" />
          </Button>
          <Slider
            value={[zoom]}
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={0.05}
            onValueChange={(v) => setZoom(v[0])}
            disabled={!src}
            aria-label="Zoom foto"
            data-testid="photo-crop-zoom-slider"
          />
          <Button type="button" size="icon" variant="outline" className="h-11 w-11 shrink-0 sm:h-9 sm:w-9"
            onClick={() => step(0.2)} disabled={zoom >= MAX_ZOOM || !src} aria-label="Perbesar" data-testid="photo-crop-zoom-in">
            <Plus className="h-4 w-4" />
          </Button>
          <span className="w-12 shrink-0 text-right text-[12px] tabular-nums text-muted-foreground" data-testid="photo-crop-zoom-value">
            {zoom.toFixed(1)}x
          </span>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button type="button" variant="ghost" disabled={!src || saving}
            onClick={() => { setZoom(1); setCrop({ x: 0, y: 0 }); setResetKey((k) => k + 1); }}
            data-testid="photo-crop-reset">
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Atur Ulang
          </Button>
          <Button type="button" variant="outline" disabled={saving} onClick={() => onOpenChange(false)} data-testid="photo-crop-cancel">
            Batal
          </Button>
          <Button type="button" disabled={!areaPx || saving} onClick={save} data-testid="photo-crop-save">
            {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Simpan Foto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PhotoCropDialog;
