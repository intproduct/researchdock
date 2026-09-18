export interface Project {
  id: string
  name: string
  description: string
  stage: string
  status_note: string
  next_step: string
  revision: number
  created_at: string
  updated_at: string
}
export interface Device {
  id: string
  name: string
  platform: string
  revoked: boolean
  last_seen: string | null
}
export interface WorkingCopy {
  id: string
  project_id: string
  device_id: string
  local_path: string
  branch: string | null
  head: string | null
  upstream: string | null
  remote_url: string | null
  dirty: boolean
  changed_files: number
  untracked_files: number
  ahead: number | null
  behind: number | null
  comparison: string
  reason: string
  observed_at: string | null
  received_at: string | null
}
export async function api<T>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const res = await fetch(
    `${import.meta.env.VITE_API_URL ?? ""}/api/v1${path}`,
    {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
  )
  if (res.status === 401) {
    localStorage.removeItem("access_token")
    window.location.assign("/login")
  }
  const data = await res.json()
  if (!res.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "请求未完成，请检查输入或稍后重试",
    )
  return data as T
}
export const stages: Record<string, string> = {
  exploring: "探索中",
  active: "进行中",
  writing: "撰写中",
  paused: "已暂停",
  archived: "已归档",
}
export const comparisons: Record<string, string> = {
  synced: "提交一致",
  ahead: "本地领先",
  behind: "本地落后",
  diverged: "历史分叉",
  unknown: "待确认",
  unrelated: "无共同历史",
}
export function date(value: string | null) {
  if (!value) return "尚无记录"
  return new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`,
  ).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
export function online(device: Device) {
  if (device.revoked || !device.last_seen) return false
  const time =
    device.last_seen.endsWith("Z") || /[+-]\d\d:\d\d$/.test(device.last_seen)
      ? device.last_seen
      : `${device.last_seen}Z`
  return Date.now() - new Date(time).getTime() < 120_000
}
