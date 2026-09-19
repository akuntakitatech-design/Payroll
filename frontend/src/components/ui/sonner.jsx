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
            "group toast group-[.toaster]:rounded-md group-[.toaster]:bg-card group-[.toaster]:text-foreground group-[.toaster]:border group-[.toaster]:border-border group-[.toaster]:shadow-md group-[.toaster]:text-[13px]",
          title: "group-[.toast]:text-[13px] group-[.toast]:font-semibold",
          description: "group-[.toast]:text-[12px] group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground group-[.toast]:rounded-md",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground group-[.toast]:rounded-md",
          closeButton:
            "group-[.toast]:bg-card group-[.toast]:text-muted-foreground group-[.toast]:border-border",
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
