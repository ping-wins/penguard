# XDR Agent Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make Windows endpoint onboarding usable from the cockpit instead of relying on one-off CLI commands.

**Architecture:** The cockpit creates a one-time `xdr_rico` enrollment through the BFF, shows a copyable PowerShell bootstrap command, and tracks the endpoint as pending until the first heartbeat appears in the endpoint inventory. `agent_private` gains a foreground `run` loop that repeatedly posts heartbeat, process, connection and optional Windows Security telemetry through the existing BFF endpoint.

**Tech Stack:** Vue 3, Pinia, Vitest, FastAPI BFF endpoints already present, Python 3.12, `agent_private`, Pytest, Ruff.

---

## File Structure

- Modify `apps/web/src/services/endpointsClient.ts`: add enrollment request/response types, CSRF helper use, enrollment creation and PowerShell command builder.
- Modify `apps/web/src/stores/useEndpointsStore.ts`: track pending enrollments in memory and resolve them when a matching endpoint appears.
- Create `apps/web/src/components/endpoints/AgentEnrollmentModal.vue`: wizard for display name, hostname hint, enrollment result and copyable command.
- Modify `apps/web/src/components/endpoints/EndpointsPanel.vue`: add "Add Windows Agent" entry point, render pending cards and mount the modal.
- Modify `apps/web/src/i18n/messages/en-US.ts`: add onboarding copy.
- Modify `apps/web/tests/unit/endpointsClient.test.ts`: cover enrollment POST and command generation.
- Modify `apps/web/tests/unit/endpointsPanel.test.ts`: cover wizard submission, command rendering and pending-to-online state.
- Create `apps/agent_private/agent_private/runner.py`: foreground loop orchestration with injectable sleep/post functions for tests.
- Modify `apps/agent_private/agent_private/cli.py`: add `agent-private run` parser and wire it to `runner.py`.
- Modify `apps/agent_private/tests/test_cli.py`: cover parser wiring for `run`.
- Create `apps/agent_private/tests/test_runner.py`: cover loop scheduling, masked logs, backoff behavior and optional Windows Security collection.
- Modify `apps/agent_private/README.md`: document cockpit-driven onboarding and `agent-private run`.
- Modify `AGENTS.md`: mark the onboarding and foreground loop cut as implemented once tests pass.

Out of scope for this cut:

- Windows Scheduled Task install/uninstall command.
- MSI/EXE packaging.
- True Windows Service behavior.
- Any hidden persistence or destructive endpoint action.

## Task 1: Frontend Enrollment Contract

**Files:**
- Modify: `apps/web/src/services/endpointsClient.ts`
- Test: `apps/web/tests/unit/endpointsClient.test.ts`

- [x] Add endpoint enrollment types:

```ts
export type EndpointEnrollmentRequest = {
  displayName?: string
  hostnameHint?: string
}

export type EndpointEnrollment = {
  id: string
  displayName: string | null
  hostnameHint: string | null
  createdAt: string
  token: string
}
```

- [x] Add a test proving `createEndpointEnrollment()` sends credentials and CSRF:

```ts
it('creates endpoint enrollment through the BFF with CSRF', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_01' }))
    .mockResolvedValueOnce(jsonResponse({
      id: 'enr_01',
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
      createdAt: '2026-05-13T18:00:00.000Z',
      token: 'enrollment-token',
    }))

  await expect(createEndpointEnrollment({
    displayName: 'Windows Server Lab',
    hostnameHint: 'WIN-LAB-01',
  }, fetcher)).resolves.toMatchObject({ id: 'enr_01', token: 'enrollment-token' })

  expect(fetcher).toHaveBeenNthCalledWith(1, '/api/auth/csrf', { credentials: 'include' })
  expect(fetcher).toHaveBeenNthCalledWith(2, '/api/weapons/enrollments', expect.objectContaining({
    method: 'POST',
    credentials: 'include',
    headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
  }))
})
```

- [x] Implement `getCsrfToken(fetcher)` locally in `endpointsClient.ts` using `/api/auth/csrf`.
- [x] Implement `createEndpointEnrollment(payload, fetcher = fetch)` against `POST /api/weapons/enrollments`.
- [x] Add and test `buildAgentRunCommand(enrollment, apiUrl = window.location.origin)` returning a PowerShell-safe command:

```powershell
$env:AGENT_PRIVATE_API_URL="http://localhost:8000"; $env:AGENT_PRIVATE_ENDPOINT_ID="enr_01"; $env:AGENT_PRIVATE_ENROLLMENT_TOKEN="enrollment-token"; uv run agent-private run
```

- [x] Run:

```bash
cd apps/web && pnpm test -- endpointsClient.test.ts
```

Expected: the new enrollment tests pass.

## Task 2: Endpoint Store Pending State

**Files:**
- Modify: `apps/web/src/stores/useEndpointsStore.ts`
- Test: `apps/web/tests/unit/endpointsClient.test.ts`

- [x] Add a `PendingEnrollment` type:

```ts
export type PendingEnrollment = {
  enrollmentId: string
  displayName: string
  hostnameHint: string | null
  createdAt: string
  command: string
  status: 'pending' | 'online'
}
```

- [x] Add store state: `pendingEnrollments = ref<PendingEnrollment[]>([])`.
- [x] Add `createEnrollment(payload)` that calls `createEndpointEnrollment()`, stores the command, and returns the enrollment.
- [x] Add `resolvePendingEnrollments()` inside `refresh()` after `endpoints.value = await listEndpoints()`:

```ts
pendingEnrollments.value = pendingEnrollments.value.filter((pending) => {
  return !endpoints.value.some((endpoint) => {
    if (endpoint.id === pending.enrollmentId) return true
    if (pending.hostnameHint && endpoint.hostname?.toLowerCase() === pending.hostnameHint.toLowerCase()) return true
    return false
  })
})
```

- [x] Add a store test that creates an enrollment, sees one pending record, then refreshes with a matching endpoint and sees the pending record disappear.
- [x] Run:

```bash
cd apps/web && pnpm test -- endpointsClient.test.ts
```

Expected: client and store tests pass.

## Task 3: Cockpit Onboarding Modal

**Files:**
- Create: `apps/web/src/components/endpoints/AgentEnrollmentModal.vue`
- Modify: `apps/web/src/components/endpoints/EndpointsPanel.vue`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Test: `apps/web/tests/unit/endpointsPanel.test.ts`

- [x] Create `AgentEnrollmentModal.vue` with props and emits:

```ts
const props = defineProps<{
  open: boolean
  command: string | null
  isCreating: boolean
  error: string | null
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: { displayName?: string; hostnameHint?: string }]
  copy: [command: string]
}>()
```

- [x] The modal must render:
  - `Display name` input.
  - `Hostname hint` input.
  - `Generate enrollment` button.
  - One-time secret warning after command generation.
  - Read-only command block with `data-test="agent-enrollment-command"`.
  - Copy button with `data-test="copy-agent-command"`.
- [x] In `EndpointsPanel.vue`, add a primary toolbar button with `data-test="add-windows-agent"` next to refresh.
- [x] Wire modal submit to `store.createEnrollment()`.
- [x] Render pending enrollments above the inventory list with `data-test="pending-endpoint"` and copy text `Waiting for first heartbeat`.
- [x] Add Vitest coverage that:
  - Opens the modal.
  - Submits display name and hostname.
  - Mocks `/api/auth/csrf` and `/api/weapons/enrollments`.
  - Asserts the command appears.
  - Asserts a pending card appears before the endpoint inventory returns the matching hostname.
- [x] Run:

```bash
cd apps/web && pnpm test -- endpointsPanel.test.ts endpointsClient.test.ts
```

Expected: onboarding UX tests pass.

## Task 4: Agent Foreground Runner

**Files:**
- Create: `apps/agent_private/agent_private/runner.py`
- Modify: `apps/agent_private/agent_private/cli.py`
- Create: `apps/agent_private/tests/test_runner.py`
- Modify: `apps/agent_private/tests/test_cli.py`

- [x] Create a runner configuration dataclass:

```python
@dataclass(frozen=True)
class AgentRunConfig:
    api_url: str
    endpoint_id: str
    enrollment_token: str
    heartbeat_interval: float = 30.0
    connection_interval: float = 60.0
    process_interval: float = 300.0
    windows_security_interval: float | None = None
    process_limit: int | None = None
    windows_security_limit: int = 50
```

- [x] Create `run_agent(config, *, once=False, sleep=time.sleep, post=post_endpoint_event, log=print)`.
- [x] The runner must post:
  - `heartbeat` every heartbeat interval.
  - `connection.snapshot` every connection interval.
  - `process.snapshot` every process interval.
  - Windows Security payloads only when `windows_security_interval` is set.
- [x] Log success and failures without printing the enrollment token.
- [x] On post failure, keep running and retry on the next due interval.
- [x] Add tests with fake collectors/poster/sleeper proving:
  - `once=True` posts heartbeat, connection and process once.
  - Windows Security is skipped when interval is absent.
  - A raised post exception is logged and does not expose the token.
- [x] Add CLI parser:

```python
subparsers.add_parser("run", help="Open the interactive setup TUI and run the agent from there.")
run_parser = subparsers.add_parser("run-headless", parents=[common], help="Run the foreground endpoint sensor loop without the TUI.")
run_parser.add_argument("--heartbeat-interval", type=float, default=30.0)
run_parser.add_argument("--connection-interval", type=float, default=60.0)
run_parser.add_argument("--process-interval", type=float, default=300.0)
run_parser.add_argument("--windows-security-interval", type=float)
run_parser.add_argument("--windows-security-limit", type=int, default=50)
run_parser.add_argument("--once", action="store_true")
```

- [x] In `main()`, route `run` to the TUI and require `--api-url`, `--endpoint-id`
  and `--enrollment-token` for `run-headless`, then call `run_agent()`.
- [x] Run:

```bash
cd apps/agent_private && uv run pytest tests/test_runner.py tests/test_cli.py -q
cd apps/agent_private && uv run ruff check agent_private tests
```

Expected: agent tests and lint pass.

## Task 5: Documentation And Backlog

**Files:**
- Modify: `apps/agent_private/README.md`
- Modify: `AGENTS.md`

- [x] Update README with the cockpit-first flow:

```powershell
cd apps\agent_private
$env:AGENT_PRIVATE_API_URL="http://<fortidashboard-host>:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID="<enrollment-id>"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN="<token-returned-once>"
uv run agent-private run
```

- [x] State that `run` is TUI-first and safe by default.
- [x] Document **Stop agent** and `Ctrl+C` as stop paths.
- [x] Mention that Scheduled Task installation is the next cut, not part of this cut.
- [x] Update `AGENTS.md` current implementation status after tests pass:
  - Cockpit enrollment wizard implemented.
  - Pending/online endpoint UX implemented.
  - `agent-private run` TUI and `run-headless` foreground loop implemented.
  - Scheduled Task installation remains pending.

## Task 6: Full Verification

- [x] Run frontend tests:

```bash
cd apps/web && pnpm test -- endpointsClient.test.ts endpointsPanel.test.ts
```

- [x] Run agent tests:

```bash
cd apps/agent_private && uv run pytest -q
```

- [x] Run lint:

```bash
cd apps/agent_private && uv run ruff check agent_private tests
```

- [x] Run whitespace/config checks:

```bash
git diff --check
docker compose config >/tmp/fortidashboard-compose.yml
```

Expected: all commands pass.

## Manual Smoke Test

1. Start the stack:

```bash
docker compose up --build
```

2. Open the cockpit, go to **Endpoints**, click **Add Windows Agent**, enter:

```txt
Display name: Windows Server Lab
Hostname hint: WIN-LAB
```

3. Copy the generated command.
4. On the Windows VM, from `apps/agent_private`, run the copied command.
5. Confirm the cockpit shows the endpoint moving from pending to inventory after the first heartbeat.
6. Confirm timeline receives heartbeat, connection snapshot, process snapshot and Windows Security events when enabled.

## Self-Review

- Spec coverage: onboarding wizard, one-time token display, copyable PowerShell, pending/online state and foreground loop are covered.
- Deliberate gap: Windows Scheduled Task install/uninstall is documented as the next cut because the loop must be stable first.
- Security check: token is displayed only in the command result, never returned by inventory, never logged by the runner, and never committed.
