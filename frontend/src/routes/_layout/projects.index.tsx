import { createFileRoute } from "@tanstack/react-router"
import { Workspace } from "@/research/Workspace"
export const Route = createFileRoute("/_layout/projects/")({
  component: () => <Workspace listing />,
  head: () => ({ meta: [{ title: "项目 · Research Manager" }] }),
})
