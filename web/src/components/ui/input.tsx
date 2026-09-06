import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded border border-border bg-surface px-3 text-sm text-text placeholder:text-text-muted",
        "focus:outline-none focus:ring-1 focus:ring-text/30",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
