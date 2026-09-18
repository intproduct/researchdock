import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  ArrowRight,
  Check,
  CircleDot,
  Copy,
  FolderGit2,
  GitBranch,
  Monitor,
  Plus,
  RefreshCw,
  Search,
  Terminal,
  TriangleAlert,
  Unplug,
} from "lucide-react"
import { type FormEvent, type ReactNode, useId, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  api,
  comparisons,
  type Device,
  date,
  isApiError,
  online,
  type Project,
  stages,
  type WorkingCopy,
} from "./api"
import { HistoryPanel } from "./HistoryPanel"

const inputStyle =
  "w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
function Failure({ error, retry }: { error: Error | null; retry: () => void }) {
  return error ? (
    <div
      role="alert"
      className="my-5 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm"
    >
      {error.message}
      <Button variant="outline" size="sm" onClick={retry} className="ml-4">
        重试
      </Button>
    </div>
  ) : null
}
function Pill({
  children,
  warn = false,
}: {
  children: ReactNode
  warn?: boolean
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${warn ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" : "bg-primary/10 text-primary"}`}
    >
      {children}
    </span>
  )
}
function Metric({
  label,
  value,
  sub,
  icon,
}: {
  label: string
  value: number
  sub: string
  icon: ReactNode
}) {
  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        {label}
        {icon}
      </div>
      <div className="mt-4 text-3xl font-semibold tracking-tight">
        {value}
        <span className="ml-3 text-xs font-normal text-muted-foreground">
          {sub}
        </span>
      </div>
    </div>
  )
}
async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success("已复制")
  } catch {
    toast.error("复制失败，请手动选择文本")
  }
}
function ConnectionGuide({ projectId }: { projectId?: string }) {
  const server = import.meta.env.VITE_API_URL || window.location.origin
  const command = `python -m research_agent login --server ${server} --email YOUR_EMAIL\npython -m research_agent projects\npython -m research_agent link --project ${projectId ?? "PROJECT_ID"} --path "YOUR_REPOSITORY_PATH"\npython -m research_agent scan --watch 30`
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Terminal size={16} />
          连接本地副本
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>让这台设备加入工作空间</DialogTitle>
          <DialogDescription>
            先在新系统仓库运行安装命令，再输入账户密码配对。仅扫描你明确登记的
            Git 根目录。
          </DialogDescription>
        </DialogHeader>
        <ol className="space-y-4 text-sm">
          <li>
            <strong>01 · 安装客户端</strong>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-muted p-3">
              python -m pip install ./agent
            </pre>
          </li>
          <li>
            <strong>02 · 配对设备并登记目录</strong>
            <pre className="mt-2 whitespace-pre-wrap break-all rounded-lg bg-muted p-3 text-xs leading-6">
              {command}
            </pre>
            <Button
              className="mt-2"
              variant="ghost"
              size="sm"
              onClick={() => copyText(command)}
            >
              <Copy size={14} />
              复制命令
            </Button>
          </li>
          <li className="text-muted-foreground">
            替换 YOUR_EMAIL 和
            YOUR_REPOSITORY_PATH。客户端不会上传文件正文，也不会执行 fetch、push
            或覆盖本地文件。
          </li>
        </ol>
      </DialogContent>
    </Dialog>
  )
}
function CreateProject() {
  const formId = useId()
  const [open, setOpen] = useState(false)
  const cache = useQueryClient()
  const mutation = useMutation({
    mutationFn: (body: unknown) => api<Project>("/projects", body),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ["projects"] })
      setOpen(false)
      toast.success("项目已创建，可以连接本地副本了")
    },
    onError: (e: Error) => toast.error(e.message),
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    mutation.mutate({
      name: form.get("name"),
      description: form.get("description"),
      stage: form.get("stage"),
      next_step: form.get("next_step"),
    })
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus size={16} />
          新建项目
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>为一项研究建立工作空间</DialogTitle>
          <DialogDescription>
            项目可以关联多台机器上的目录，原有文件位置保持不变。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <label htmlFor={`${formId}-name`} className="block text-sm">
            项目名称
            <Input
              id={`${formId}-name`}
              autoFocus
              name="name"
              required
              maxLength={120}
              placeholder="例如：量子多体动力学"
              className="mt-2"
            />
          </label>
          <label className="block text-sm">
            研究简介
            <textarea
              name="description"
              maxLength={2000}
              rows={3}
              className={`${inputStyle} mt-2`}
              placeholder="这项研究希望回答什么问题？"
            />
          </label>
          <label className="block text-sm">
            当前阶段
            <select name="stage" className={`${inputStyle} mt-2`}>
              {Object.entries(stages).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={`${formId}-next`} className="block text-sm">
            下一步
            <Input
              id={`${formId}-next`}
              name="next_step"
              maxLength={2000}
              className="mt-2"
              placeholder="最值得推进的一件事"
            />
          </label>
          <Button
            disabled={mutation.isPending}
            className="w-full"
            type="submit"
          >
            {mutation.isPending ? "正在创建…" : "创建项目"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Workspace({ listing = false }: { listing?: boolean }) {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  })
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api<Device[]>("/devices"),
    refetchInterval: 30_000,
  })
  const copies = useQuery({
    queryKey: ["copies"],
    queryFn: () => api<WorkingCopy[]>("/copies"),
    refetchInterval: 30_000,
  })
  const [search, setSearch] = useState("")
  const [stage, setStage] = useState("")
  const filtered = (projects.data ?? []).filter(
    (p) =>
      (!stage || p.stage === stage) &&
      `${p.name} ${p.description}`.toLowerCase().includes(search.toLowerCase()),
  )
  const refresh = () => {
    projects.refetch()
    devices.refetch()
    copies.refetch()
  }
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-3 text-[11px] font-semibold tracking-[.24em] text-primary">
            YOUR RESEARCH, CONNECTED
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            {listing ? "你的研究项目" : "把分散的研究，连接起来。"}
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            项目、设备与版本的全局视图。下一次开始，从上一次的进展出发。
          </p>
        </div>
        <CreateProject />
      </header>
      <Failure
        error={projects.error || devices.error || copies.error}
        retry={refresh}
      />
      {!listing && (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="研究项目"
            value={projects.data?.length ?? 0}
            sub="统一管理"
            icon={<FolderGit2 size={18} />}
          />
          <Metric
            label="已连接副本"
            value={copies.data?.length ?? 0}
            sub="保留本地工作方式"
            icon={<GitBranch size={18} />}
          />
          <Metric
            label="最近在线设备"
            value={devices.data?.filter(online).length ?? 0}
            sub="2 分钟内上报"
            icon={<Monitor size={18} />}
          />
          <Metric
            label="有本地修改"
            value={copies.data?.filter((c) => c.dirty).length ?? 0}
            sub="待提交的工作"
            icon={<CircleDot size={18} />}
          />
        </section>
      )}
      <section>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">
            项目工作区{" "}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {filtered.length}
            </span>
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search
                className="absolute left-3 top-2.5 text-muted-foreground"
                size={16}
              />
              <Input
                aria-label="搜索项目"
                placeholder="搜索项目或研究主题"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-56 bg-card pl-9"
              />
            </div>
            <select
              aria-label="筛选阶段"
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className={`${inputStyle} w-auto bg-card`}
            >
              <option value="">全部阶段</option>
              {Object.entries(stages).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
            <Button
              aria-label="刷新"
              size="icon"
              variant="outline"
              onClick={refresh}
            >
              <RefreshCw size={16} />
            </Button>
          </div>
        </div>
        {projects.isPending ? (
          <p className="py-16 text-center text-muted-foreground">
            正在加载项目…
          </p>
        ) : filtered.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {filtered.map((p, index) => {
              const pc = (copies.data ?? []).filter(
                (c) => c.project_id === p.id,
              )
              return (
                <Link
                  to="/projects/$projectId"
                  params={{ projectId: p.id }}
                  key={p.id}
                  className="group flex flex-col rounded-2xl border bg-card p-6 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                >
                  <div className="flex items-start justify-between">
                    <span className="grid size-11 place-items-center rounded-xl bg-primary/8 text-primary">
                      <FolderGit2 size={23} />
                    </span>
                    <Pill>{stages[p.stage] ?? p.stage}</Pill>
                  </div>
                  <p className="mt-5 text-[10px] tracking-[.18em] text-muted-foreground">
                    RESEARCH / {String(index + 1).padStart(2, "0")}
                  </p>
                  <h3 className="mt-1 text-xl font-semibold">{p.name}</h3>
                  <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-6 text-muted-foreground">
                    {p.description || "补充研究主题，让每次接续更清晰。"}
                  </p>
                  <div className="my-5 rounded-lg bg-muted/55 px-3 py-2.5 text-sm">
                    <span className="mr-2 text-xs text-primary">下一步</span>
                    {p.next_step || "尚未记录下一步"}
                  </div>
                  <div className="mt-auto flex items-center justify-between border-t pt-4 text-xs text-muted-foreground">
                    <span>
                      {pc.length} 份副本 · 更新于 {date(p.updated_at)}
                    </span>
                    <ArrowRight
                      size={16}
                      className="text-primary transition group-hover:translate-x-1"
                    />
                  </div>
                </Link>
              )
            })}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed bg-card p-12 text-center">
            <FolderGit2 className="mx-auto mb-5 text-primary" size={38} />
            <h3 className="text-lg font-semibold">
              {search || stage
                ? "没有符合条件的项目"
                : "从你的第一个研究项目开始"}
            </h3>
            <p className="mx-auto mb-6 mt-3 max-w-md text-sm leading-6 text-muted-foreground">
              {search || stage
                ? "调整搜索词或阶段筛选后重试。"
                : "先创建项目，再连接电脑上的 Git 仓库。副本位置、未提交工作与版本差异会汇总在这里。"}
            </p>
            {!search && !stage && <CreateProject />}
          </div>
        )}
      </section>
      <aside className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-primary/5 p-6">
        <div>
          <h3 className="font-medium">把另一台电脑上的进展带回来</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            通过轻量客户端上报状态，断网后仍可继续本地研究。
          </p>
        </div>
        <ConnectionGuide />
      </aside>
    </div>
  )
}

export function ProjectDetail({ id }: { id: string }) {
  const cache = useQueryClient()
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  })
  const copies = useQuery({
    queryKey: ["copies", id],
    queryFn: () => api<WorkingCopy[]>(`/projects/${id}/copies`),
    refetchInterval: 30_000,
  })
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api<Device[]>("/devices"),
    refetchInterval: 30_000,
  })
  const project = projects.data?.find((p) => p.id === id)
  // Draft state is owned here, not by the query cache: background refetches
  // must never overwrite what the user is typing. `draft` is null until the
  // user first edits, then holds their text; `baseRevision` pins the revision
  // the draft started from so a stale base is never attached to a new draft.
  const [draft, setDraft] = useState<{
    status_note: string
    next_step: string
    stage: string
  } | null>(null)
  const [baseRevision, setBaseRevision] = useState<number | null>(null)
  const [conflict, setConflict] = useState(false)
  // Pin the draft to the revision it started from, so a background refetch
  // can never attach a newer revision to an older draft.
  function edit(next: {
    status_note: string
    next_step: string
    stage: string
  }) {
    if (draft === null) setBaseRevision(project?.revision ?? null)
    setDraft(next)
  }
  const save = useMutation({
    mutationFn: (body: unknown) => api<Project>(`/projects/${id}`, body, "PUT"),
    onSuccess: (saved) => {
      setDraft(null)
      setBaseRevision(saved.revision)
      setConflict(false)
      cache.invalidateQueries({ queryKey: ["projects"] })
      cache.invalidateQueries({ queryKey: ["history", id] })
      toast.success("研究进展已保存")
    },
    onError: (e: Error) => {
      if (isApiError(e, 409)) {
        // Keep the whole draft; only flag that another session saved first.
        // Refetching reveals the newer revision without touching the draft.
        setConflict(true)
        projects.refetch()
        cache.invalidateQueries({ queryKey: ["history", id] })
      } else {
        toast.error(e.message)
      }
    },
  })
  if (projects.isPending) return <p>正在加载项目…</p>
  if (projects.error)
    return <Failure error={projects.error} retry={() => projects.refetch()} />
  if (!project)
    return (
      <div>
        <h1>项目不存在或无权访问</h1>
        <Link to="/projects">返回项目列表</Link>
      </div>
    )
  const base = baseRevision ?? project.revision
  const values = {
    status_note: draft?.status_note ?? project.status_note,
    next_step: draft?.next_step ?? project.next_step,
    stage: draft?.stage ?? project.stage,
  }
  const dirty =
    draft !== null &&
    (draft.status_note !== project.status_note ||
      draft.next_step !== project.next_step ||
      draft.stage !== project.stage)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!project) return
    save.mutate({
      name: project.name,
      description: project.description,
      revision: base,
      ...values,
    })
  }
  function adoptLatest() {
    if (
      !draft ||
      window.confirm("采用最新内容会丢弃当前未保存的草稿，确定继续吗？")
    ) {
      setDraft(null)
      setBaseRevision(project!.revision)
      setConflict(false)
    }
  }
  return (
    <div className="space-y-7">
      <Link
        to="/projects"
        className="text-sm text-muted-foreground hover:text-primary"
      >
        ← 所有项目
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-semibold">{project.name}</h1>
            <Pill>{stages[project.stage]}</Pill>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {project.description || "尚未填写研究简介"}
          </p>
          <button
            type="button"
            onClick={() => copyText(project.id)}
            className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"
          >
            <Copy size={12} />
            复制项目 ID
          </button>
        </div>
        <ConnectionGuide projectId={id} />
      </header>
      <section className="overflow-hidden rounded-2xl border bg-card">
        <div className="border-b p-5">
          <h2 className="font-semibold">设备副本与版本</h2>
          <p className="mt-2 text-xs text-muted-foreground">
            比较基准是各设备本地缓存的跟踪分支，并非实时远端状态。提交一致也可能存在未提交修改。
          </p>
        </div>
        <Failure
          error={copies.error || devices.error}
          retry={() => {
            copies.refetch()
            devices.refetch()
          }}
        />
        {copies.isPending ? (
          <p className="p-8">加载副本…</p>
        ) : !copies.data?.length ? (
          <div className="p-10 text-center">
            <Monitor className="mx-auto mb-4 text-muted-foreground" size={30} />
            <p className="mb-4 text-sm text-muted-foreground">
              还没有连接副本。复制项目 ID，在客户端登记仓库即可。
            </p>
            <ConnectionGuide projectId={id} />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  {[
                    "设备 / 路径",
                    "分支 / 提交",
                    "版本关系",
                    "本地修改",
                    "观察时间",
                  ].map((label) => (
                    <th key={label} className="px-5 py-3 font-medium">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {copies.data.map((c) => {
                  const d = devices.data?.find((x) => x.id === c.device_id)
                  return (
                    <tr key={c.id} className="border-t align-top">
                      <td className="max-w-72 px-5 py-5">
                        <div className="font-medium">
                          {d?.name ?? "设备"}{" "}
                          <span className="text-xs font-normal text-muted-foreground">
                            {d?.revoked
                              ? "已撤销"
                              : d && online(d)
                                ? "最近在线"
                                : "离线 / 未上报"}
                          </span>
                        </div>
                        <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                          {c.local_path}
                        </p>
                      </td>
                      <td className="px-5 py-5">
                        <span className="flex items-center gap-1">
                          <GitBranch size={13} />
                          {c.branch ?? "无分支"}
                        </span>
                        <code className="mt-2 block text-xs text-muted-foreground">
                          {c.head?.slice(0, 10) ?? "无提交"}
                        </code>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {c.upstream ?? "无跟踪分支"}
                        </span>
                      </td>
                      <td className="max-w-60 px-5 py-5">
                        <Pill warn={c.comparison !== "synced"}>
                          {comparisons[c.comparison] ?? c.comparison}
                        </Pill>
                        {c.ahead !== null && (
                          <p className="mt-2 text-xs">
                            领先 {c.ahead} · 落后 {c.behind}
                          </p>
                        )}
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          {c.reason}
                        </p>
                      </td>
                      <td className="px-5 py-5">
                        {!c.observed_at ? (
                          <span className="text-xs text-muted-foreground">
                            尚未扫描
                          </span>
                        ) : c.dirty ? (
                          <>
                            <Pill warn>有未提交工作</Pill>
                            <p className="mt-2 text-xs text-muted-foreground">
                              {c.changed_files} 已跟踪 · {c.untracked_files}{" "}
                              未跟踪
                            </p>
                          </>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-primary">
                            <Check size={14} />
                            观察时工作区干净
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-5 text-xs text-muted-foreground">
                        {date(c.observed_at)}
                        <p className="mt-2">接收于 {date(c.received_at)}</p>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="rounded-2xl border bg-card p-6">
        <h2 className="mb-2 font-semibold">留给下一次研究的接续记录</h2>
        <p className="mb-5 text-xs text-muted-foreground">
          保存时校验修订版本，避免覆盖另一处刚更新的进展。
        </p>
        {conflict && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/40"
          >
            <p className="flex items-center gap-2 font-medium">
              <TriangleAlert size={16} className="text-amber-600" />
              另一处已更新到修订 {project.revision}，你的草稿仍保留在下方。
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              当前草稿基于修订 {base}
              。查看最新内容后，可以放弃草稿采用最新版本再编辑，或直接保存覆盖。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => projects.refetch()}
              >
                查看最新版本
              </Button>
              {project.revision !== base && (
                <Button variant="outline" size="sm" onClick={adoptLatest}>
                  采用最新内容（丢弃草稿）
                </Button>
              )}
            </div>
          </div>
        )}
        <form onSubmit={submit} className="grid gap-5 md:grid-cols-2">
          <label className="block text-sm md:col-span-2">
            当前进展
            <textarea
              name="status_note"
              value={values.status_note}
              onChange={(e) => edit({ ...values, status_note: e.target.value })}
              maxLength={10000}
              rows={5}
              className={`${inputStyle} mt-2`}
              placeholder="已经确认了什么？还有哪些问题？"
            />
          </label>
          <label htmlFor="project-next-step" className="text-sm">
            下一步
            <Input
              id="project-next-step"
              name="next_step"
              value={values.next_step}
              onChange={(e) => edit({ ...values, next_step: e.target.value })}
              maxLength={2000}
              className="mt-2"
            />
          </label>
          <label className="text-sm">
            研究阶段
            <select
              name="stage"
              value={values.stage}
              onChange={(e) => edit({ ...values, stage: e.target.value })}
              className={`${inputStyle} mt-2`}
            >
              {Object.entries(stages).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center justify-between md:col-span-2">
            <span className="text-xs text-muted-foreground">
              {dirty ? `草稿基于修订 ${base} · ` : ""}当前修订{" "}
              {project.revision} · {date(project.updated_at)}
            </span>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "保存中…" : "保存进展"}
            </Button>
          </div>
        </form>
      </section>
      <HistoryPanel projectId={id} />
    </div>
  )
}

export function Devices() {
  const cache = useQueryClient()
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api<Device[]>("/devices"),
    refetchInterval: 30_000,
  })
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/devices/${id}/revoke`, {}),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ["devices"] })
      toast.success("设备凭据已撤销，历史观察仍保留")
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mb-3 text-[11px] tracking-[.2em] text-primary">
            CONNECTED DEVICES
          </p>
          <h1 className="text-3xl font-semibold">你的研究设备</h1>
          <p className="mt-3 text-sm text-muted-foreground">
            每台设备独立配对。两分钟内收到上报才标记为最近在线。
          </p>
        </div>
        <ConnectionGuide />
      </header>
      <Failure error={devices.error} retry={() => devices.refetch()} />
      {devices.isPending ? (
        <p>正在加载设备…</p>
      ) : !devices.data?.length ? (
        <div className="rounded-2xl border border-dashed bg-card p-12 text-center">
          <Monitor className="mx-auto mb-4 text-primary" size={36} />
          <h2 className="mb-3 font-medium">连接你的第一台设备</h2>
          <p className="mb-6 text-sm text-muted-foreground">
            配对后，电脑会出现在这里。只扫描你选择的仓库目录。
          </p>
          <ConnectionGuide />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {devices.data.map((d) => (
            <article key={d.id} className="rounded-2xl border bg-card p-6">
              <div className="flex items-center justify-between">
                <Monitor className="text-primary" size={24} />
                <Pill warn={!online(d)}>
                  {d.revoked
                    ? "已撤销"
                    : online(d)
                      ? "最近在线"
                      : "离线 / 未上报"}
                </Pill>
              </div>
              <h2 className="mt-5 text-lg font-semibold">{d.name}</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {d.platform} · 最后上报 {date(d.last_seen)}
              </p>
              <div className="mt-5 border-t pt-4">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={d.revoked || revoke.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `撤销设备“${d.name}”的连接权限？历史记录将保留。`,
                      )
                    )
                      revoke.mutate(d.id)
                  }}
                >
                  <Unplug size={14} />
                  撤销设备权限
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
