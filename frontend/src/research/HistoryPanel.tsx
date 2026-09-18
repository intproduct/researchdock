import { useInfiniteQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, History } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  api,
  date,
  type ProjectHistoryPage,
  type ProjectRevision,
  stages,
} from "./api"

const PAGE_SIZE = 10

const origins: Record<ProjectRevision["origin"], string> = {
  created: "创建",
  updated: "更新",
  migrated_baseline: "迁移基线",
}

function RevisionRow({ item }: { item: ProjectRevision }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="border-t first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left text-sm hover:bg-muted/40"
      >
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <span className="font-medium">修订 {item.revision}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${item.origin === "migrated_baseline" ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" : "bg-primary/10 text-primary"}`}
        >
          {origins[item.origin]}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          记录于 {date(item.recorded_at)}
        </span>
      </button>
      {open && (
        <dl className="space-y-3 border-t bg-muted/20 px-5 py-4 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">项目名称</dt>
            <dd className="mt-1">{item.snapshot.name}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">研究简介</dt>
            <dd className="mt-1 whitespace-pre-wrap">
              {item.snapshot.description || "（空）"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">研究阶段</dt>
            <dd className="mt-1">
              {stages[item.snapshot.stage] ?? item.snapshot.stage}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">当前进展</dt>
            <dd className="mt-1 whitespace-pre-wrap">
              {item.snapshot.status_note || "（空）"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">下一步</dt>
            <dd className="mt-1 whitespace-pre-wrap">
              {item.snapshot.next_step || "（空）"}
            </dd>
          </div>
          <p className="border-t pt-3 text-xs text-muted-foreground">
            项目更新于 {date(item.project_updated_at)}
            {item.origin === "migrated_baseline" &&
              " · 迁移时补录的基线，更早版本未保留"}
          </p>
        </dl>
      )}
    </li>
  )
}

export function HistoryPanel({ projectId }: { projectId: string }) {
  const history = useInfiniteQuery({
    queryKey: ["history", projectId],
    queryFn: ({ pageParam }) =>
      api<ProjectHistoryPage>(
        `/projects/${projectId}/history?limit=${PAGE_SIZE}${
          pageParam ? `&before_revision=${pageParam}` : ""
        }`,
      ),
    initialPageParam: null as number | null,
    getNextPageParam: (page) => page.next_before_revision,
  })
  const items = history.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <section className="overflow-hidden rounded-2xl border bg-card">
      <div className="flex items-center gap-2 border-b p-5">
        <History size={17} className="text-primary" />
        <h2 className="font-semibold">修订历史</h2>
        <span className="text-xs text-muted-foreground">
          每次保存的完整快照，只追加、不修改
        </span>
      </div>
      {history.isPending ? (
        <p className="p-8 text-sm text-muted-foreground">正在加载历史…</p>
      ) : history.error ? (
        <div className="p-6 text-sm">
          <p className="text-destructive">{history.error.message}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => history.refetch()}
          >
            重试
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="p-8 text-sm text-muted-foreground">还没有历史记录。</p>
      ) : (
        <>
          <ul>
            {items.map((item) => (
              <RevisionRow key={item.id} item={item} />
            ))}
          </ul>
          {history.hasNextPage && (
            <div className="border-t p-4 text-center">
              <Button
                variant="outline"
                size="sm"
                disabled={history.isFetchingNextPage}
                onClick={() => history.fetchNextPage()}
              >
                {history.isFetchingNextPage ? "加载中…" : "加载更早的修订"}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
