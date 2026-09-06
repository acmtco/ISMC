import * as React from "react";

import { cn } from "@/lib/utils";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted",
      "focus:outline-none focus:ring-1 focus:ring-text/30",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";
