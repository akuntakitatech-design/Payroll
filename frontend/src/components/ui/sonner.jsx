import { useTheme } from "next-themes"
import { Toaster as Sonner, toast } from "sonner"

/**
 * Notifikasi mengikuti tema aplikasi: latar putih, border netral,
 * dan ikon status memakai warna semantik terkendali (bukan hijau/merah mentah).
 */
const Toaster = ({
  ...props
}) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      offset={20}
      closeButton
      visibleToasts={3}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:rounded-xl group-[.toaster]:border group-[.toaster]:border-border-strong group-[.toaster]:bg-card group-[.toaster]:text-foreground group-[.toaster]:shadow-[var(--shadow-overlay)] group-[.toaster]:text-[13px]",
          title: "group-[.toast]:text-[13px] group-[.toast]:font-bold",
          description: "group-[.toast]:text-[12px] group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:rounded-lg group-[.toast]:border group-[.toast]:border-[hsl(var(--primary-active))] group-[.toast]:bg-[image:var(--gradient-primary)] group-[.toast]:text-white group-[.toast]:shadow-[var(--shadow-button-primary)]",
          cancelButton:
            "group-[.toast]:rounded-lg group-[.toast]:border group-[.toast]:border-border-strong group-[.toast]:bg-muted group-[.toast]:text-ink-2",
          closeButton:
            "group-[.toast]:border-border group-[.toast]:bg-card group-[.toast]:text-muted-foreground",
          success: "group-[.toaster]:[&_[data-icon]]:text-success",
          error: "group-[.toaster]:[&_[data-icon]]:text-danger",
          warning: "group-[.toaster]:[&_[data-icon]]:text-warning",
          info: "group-[.toaster]:[&_[data-icon]]:text-info",
        },
      }}
      {...props} />
  );
}

export { Toaster, toast }
