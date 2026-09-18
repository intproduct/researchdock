import { createFileRoute } from "@tanstack/react-router"
import { Devices } from "@/research/Workspace"
export const Route = createFileRoute("/_layout/devices")({
  component: Devices,
  head: () => ({ meta: [{ title: "设备 · Research Manager" }] }),
})
