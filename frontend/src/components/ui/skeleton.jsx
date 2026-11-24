import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}) {
  return (
    <div
      className={cn(
        "animate-shimmer rounded-md bg-[linear-gradient(90deg,hsl(var(--muted))_25%,hsl(var(--surface-1))_50%,hsl(var(--muted))_75%)] bg-[length:200%_100%]",
        className
      )}
      {...props} />
  );
}

export { Skeleton }
