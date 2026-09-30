"""
Orchestration engine.

Responsibilities (mapped directly to assignment requirements):
  - Task sequencing & dependency management  -> topological execution over a DAG
  - Cross-step coordination                  -> Context object shared/mutated across agents
  - Error handling & recovery                -> per-task retry with backoff + critical/non-critical
                                                 failure semantics + downstream skip propagation
  - Controlled autonomy                      -> approval gates (auto-approved but logged in
                                                 non-interactive mode; real input() prompt in
                                                 --interactive mode)
"""
from __future__ import annotations
import time
from .models import Task, TaskStatus, Context, WorkflowResult


class Orchestrator:
    def __init__(self, tasks: list[Task], context: Context):
        self.tasks = {t.id: t for t in tasks}
        self.context = context
        self._validate_dag()

    def _validate_dag(self):
        ids = set(self.tasks)
        for t in self.tasks.values():
            for dep in t.depends_on:
                if dep not in ids:
                    raise ValueError(f"Task '{t.id}' depends on unknown task '{dep}'")
        # cycle check via simple DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in self.tasks}

        def dfs(tid):
            color[tid] = GRAY
            for dep in self.tasks[tid].depends_on:
                if color[dep] == GRAY:
                    raise ValueError(f"Cycle detected involving task '{tid}'")
                if color[dep] == WHITE:
                    dfs(dep)
            color[tid] = BLACK

        for tid in self.tasks:
            if color[tid] == WHITE:
                dfs(tid)

    def _ready_tasks(self) -> list[Task]:
        """Tasks whose dependencies are all DONE (or SKIPPED-non-blocking) and are still PENDING."""
        ready = []
        for t in self.tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            deps = [self.tasks[d] for d in t.depends_on]
            if all(d.status == TaskStatus.DONE for d in deps):
                ready.append(t)
            elif any(d.status == TaskStatus.FAILED or d.status == TaskStatus.SKIPPED for d in deps):
                # a dependency failed/was skipped -> this task cannot run
                t.status = TaskStatus.SKIPPED
                t.error = "Skipped: upstream dependency did not complete successfully."
                self.context.log(f"SKIP  {t.id} ({t.name}) — {t.error}")
        return ready

    def _request_approval(self, task: Task) -> bool:
        """Controlled autonomy checkpoint before a gated task executes."""
        task.status = TaskStatus.AWAITING_APPROVAL
        if self.context.interactive:
            resp = input(
                f"\n>>> APPROVAL REQUIRED for task '{task.id}' ({task.name}). Proceed? [y/N]: "
            ).strip().lower()
            approved = resp == "y"
        else:
            # Non-interactive demo mode: auto-approve but log it explicitly so the
            # checkpoint is auditable rather than silently skipped.
            approved = True
        self.context.log(
            f"APPROVAL {'GRANTED' if approved else 'DENIED'} for '{task.id}' "
            f"(mode={'interactive' if self.context.interactive else 'auto (logged)'})"
        )
        return approved

    def run(self) -> WorkflowResult:
        self.context.log(f"Workflow started with {len(self.tasks)} tasks.")
        overall_ok = True

        while True:
            ready = self._ready_tasks()
            if not ready:
                break

            for task in ready:
                if task.requires_approval:
                    if not self._request_approval(task):
                        task.status = TaskStatus.SKIPPED
                        task.error = "Not approved by reviewer."
                        overall_ok = False
                        continue

                self._execute_with_retry(task)
                if task.status == TaskStatus.FAILED and task.critical:
                    overall_ok = False

        # anything left PENDING means an unresolved dependency graph issue
        for t in self.tasks.values():
            if t.status == TaskStatus.PENDING:
                t.status = TaskStatus.SKIPPED
                t.error = "Never became ready (unresolved dependency)."
                overall_ok = False

        self.context.log(f"Workflow finished. success={overall_ok}")
        return WorkflowResult(
            tasks=list(self.tasks.values()),
            context=self.context,
            success=overall_ok,
        )

    def _execute_with_retry(self, task: Task):
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        attempt = 0
        while attempt <= task.max_retries:
            attempt += 1
            task.attempts = attempt
            try:
                self.context.log(f"RUN   {task.id} ({task.name}) attempt {attempt}/{task.max_retries + 1}")
                result = task.agent(task, self.context)
                task.result = result or {}
                task.status = TaskStatus.DONE
                task.finished_at = time.time()
                self.context.log(f"DONE  {task.id} in {task.duration()}s")
                return
            except Exception as exc:  # noqa: BLE001 - agent errors are data, not crashes
                task.error = str(exc)
                task.log.append(f"attempt {attempt} failed: {exc}")
                self.context.log(f"ERROR {task.id} attempt {attempt}: {exc}")
                if attempt > task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.finished_at = time.time()
                    self.context.log(f"FAILED {task.id} after {attempt} attempt(s). critical={task.critical}")
                    return
                # simple backoff before retry
                time.sleep(0.05)
