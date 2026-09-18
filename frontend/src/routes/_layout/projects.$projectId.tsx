import { createFileRoute } from "@tanstack/react-router"
import { ProjectDetail } from "@/research/Workspace"
export const Route = createFileRoute("/_layout/projects/$projectId")({
  component: Detail,
  head: () => ({ meta: [{ title: "项目详情 · Research Manager" }] }),
})
function Detail() {
  const { projectId } = Route.useParams()
  return <ProjectDetail id={projectId} />
}
