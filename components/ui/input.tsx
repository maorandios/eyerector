import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-xl border border-zinc-700 bg-zinc-900 px-3 text-zinc-100 outline-none ring-blue-400 placeholder:text-zinc-500 focus:ring-2",
        className,
      )}
      {...props}
    />
  );
}
