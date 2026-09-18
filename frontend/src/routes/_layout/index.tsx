import { createFileRoute } from "@tanstack/react-router"
import { Workspace } from "@/research/Workspace"
export const Route = createFileRoute("/_layout/")({
  component: Workspace,
  head: () => ({ meta: [{ title: "研究总览 · Research Manager" }] }),
})
