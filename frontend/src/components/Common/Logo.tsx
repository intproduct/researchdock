import { Link } from "@tanstack/react-router"
import { Orbit } from "lucide-react"
import { cn } from "@/lib/utils"
export function Logo({ variant = "full", className, asLink = true }: { variant?: "full" | "icon" | "responsive"; className?: string; asLink?: boolean }) {
  const content = <span className={cn("inline-flex items-center gap-3", className)}><span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Orbit size={22}/></span>{variant !== "icon" && <span className={variant === "responsive" ? "group-data-[collapsible=icon]:hidden" : ""}><strong className="block text-sm tracking-tight">Research Manager</strong><span className="text-[10px] tracking-[.2em] text-muted-foreground">科研工作台</span></span>}</span>
  return asLink ? <Link to="/">{content}</Link> : content
}
