import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Цвет — только здесь: статусы (светофор, критичность, доверие). Everywhere
 * else in the UI stays neutral gray/white by design. */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        neutral: "bg-surface-hover text-text-muted",
        green: "bg-status-green/15 text-status-green",
        yellow: "bg-status-yellow/15 text-status-yellow",
        red: "bg-status-red/15 text-status-red",
        gray: "bg-status-gray/15 text-status-gray",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
