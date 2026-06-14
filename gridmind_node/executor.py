"""
GridMind Node — Task Executor
==============================
Runs Python scripts in isolated subprocesses, streams stdout line-by-line,
handles timeout kills, and supports emergency abort.

Key design decisions:
  - asyncio.create_subprocess_exec avoids the shell for security.
  - Whole-tree kills: POSIX via os.killpg on a new session; Windows via
    `taskkill /F /T` (CREATE_NEW_PROCESS_GROUP alone does not kill grandchildren).
  - stdout and stderr are drained concurrently to avoid a full-pipe deadlock.
  - The timeout is enforced on every stdout read (wall-clock deadline), so an
    infinite-print or output-then-hang script is still bounded.
  - _aborted is checked after the process exits so we don't race the normal path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import tempfile
import shutil
import zipfile
from typing import AsyncGenerator

import httpx

logger = logging.getLogger("gridmind.executor")

# ── State ──────────────────────────────────────────────────────────────────────
# Maps task_id → live Process; cleared on exit/abort.
_running: dict[str, asyncio.subprocess.Process] = {}
_aborted: set[str] = set()

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_result(task_id: str, *, stdout: str = "", stderr: str = "",
                 exit_code: int = -1, status: str = "running",
                 duration_secs: float = 0.0) -> dict:
    """Construct a uniform result dict for yielding up the chain."""
    return {
        "task_id":      task_id,
        "stdout":       stdout,
        "stderr":       stderr,
        "exit_code":    exit_code,
        "status":       status,
        "duration_secs": duration_secs,
    }


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    """Force-kill the whole process tree, swallowing race-condition errors."""
    try:
        if sys.platform == "win32":
            # proc.terminate() only kills the direct child, orphaning grandchildren.
            # taskkill /T kills the entire tree.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


# ── Public API ─────────────────────────────────────────────────────────────────

async def run_script(
    task_id: str,
    script: str,
    timeout_s: int = 300,
    has_artifact: bool = False,
    server_host: str = "localhost",
    chunk_index: int = 0,
    chunk_count: int = 1,
) -> AsyncGenerator[dict, None]:
    """
    Write *script* to a temp file, execute it, stream stdout line-by-line,
    then yield a final result dict.

    Yields
    ------
    dict with keys: task_id, stdout, stderr, exit_code, status, duration_secs
    """
    # Workspace Setup
    workspace_dir = None
    loop = asyncio.get_running_loop()
    
    if has_artifact:
        workspace_dir = tempfile.mkdtemp(prefix=f"gm_ws_{task_id[:8]}_")
        zip_path = os.path.join(workspace_dir, "workspace.zip")
        url = f"http://{server_host}:8000/api/v1/tasks/{task_id}/artifact"
        
        logger.info("Downloading artifact from %s to %s", url, zip_path)
        yield _make_result(task_id, stdout="[GridMind] Downloading workspace artifact...\n")
        
        try:
            def download():
                # httpx (not urlretrieve): raise_for_status() turns a 404/500 into a
                # clear error instead of silently saving an HTML/JSON error body as
                # "workspace.zip" and failing later with a misleading "not a zip file".
                r = httpx.get(url, timeout=60)
                r.raise_for_status()
                with open(zip_path, "wb") as fh:
                    fh.write(r.content)

            await loop.run_in_executor(None, download)
            yield _make_result(task_id, stdout="[GridMind] Extracting workspace...\n")
            
            def extract():
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(workspace_dir)
                os.remove(zip_path) # cleanup zip
            
            await loop.run_in_executor(None, extract)
            yield _make_result(task_id, stdout="[GridMind] Workspace ready.\n")
            
            # Save the script into the workspace
            path = os.path.join(workspace_dir, "gridmind_entry.py")
            with open(path, "w") as fh:
                fh.write(script)
                
        except Exception as e:
            logger.error("Failed to download/extract artifact: %s", e)
            yield _make_result(task_id, stderr=f"Artifact fetch failed: {e}", exit_code=1, status="failed")
            if workspace_dir:
                shutil.rmtree(workspace_dir, ignore_errors=True)
            return
            
    else:
        # Legacy single-script mode
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix=f"gm_{task_id[:8]}_"
        ) as fh:
            fh.write(script)
            path = fh.name

    # Platform-specific subprocess isolation
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    else:
        kwargs["preexec_fn"] = os.setsid   # new session = new process group

    # Data-parallel context: the script reads these to process only its slice.
    child_env = {
        **os.environ,
        "GRIDMIND_CHUNK_INDEX": str(chunk_index),
        "GRIDMIND_CHUNK_COUNT": str(max(1, chunk_count)),
        # Force UTF-8 stdout so a task can print unicode/emojis without dying on a
        # Windows cp1252 console (the default for a piped child process).
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, path,           # use the same Python that runs the agent
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_dir,              # executes inside the workspace if present
            env=child_env,
            **kwargs,
        )
    except Exception as exc:
        logger.error("Failed to start subprocess: %s", exc)
        # The try/finally that normally cleans these up is below; on spawn failure we
        # never enter it, so clean up here to avoid leaking the temp file/workspace.
        if not has_artifact:
            try:
                os.unlink(path)
            except OSError:
                pass
        if workspace_dir:
            shutil.rmtree(workspace_dir, ignore_errors=True)
        yield _make_result(task_id, stderr=f"Subprocess creation failed: {exc}", exit_code=1, status="failed")
        return

    try:
        _running[task_id] = proc
        logger.info("Started task %s (pid=%d)", task_id, proc.pid)

        # ── Status: running ──────────────────────────────────────────────────
        assert proc.stdout is not None and proc.stderr is not None
        yield _make_result(task_id, status="running")

        # Drain stderr concurrently. If we read all of stdout first (as before) a
        # child writing >~64KB to stderr would block on a full stderr pipe while we
        # block on stdout → deadlock until the timeout. Reading both at once fixes it.
        stderr_task = asyncio.create_task(proc.stderr.read())

        # ── Stream stdout under a wall-clock timeout budget ──────────────────
        # The old `async for` + post-loop wait_for never bounded an infinite-print
        # or output-then-hang script. Enforce the deadline on every read.
        deadline = loop.time() + float(timeout_s)
        timed_out = False
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                timed_out = True
                break
            try:
                raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if not raw_line:          # EOF — process closed stdout
                break
            yield _make_result(task_id, stdout=raw_line.decode(errors="replace"), status="running")

        if not timed_out:
            # stdout closed; give the process a brief bounded window to actually exit.
            try:
                await asyncio.wait_for(proc.wait(), timeout=max(0.5, deadline - loop.time()))
            except asyncio.TimeoutError:
                timed_out = True

        if timed_out:
            _kill_proc(proc)
            stderr_task.cancel()
            logger.warning("Task %s timed out after %ds — killed.", task_id, timeout_s)
            yield _make_result(
                task_id,
                stderr=f"TIMEOUT — task killed after {timeout_s}s",
                exit_code=124,          # conventional timeout exit code
                status="failed",
                duration_secs=float(timeout_s),
            )
            return

        # ── Gather stderr (already draining concurrently) ────────────────────
        try:
            err_bytes = await stderr_task
        except BaseException:
            err_bytes = b""
        err = err_bytes.decode(errors="replace")

        rc = proc.returncode if proc.returncode is not None else -1
        if task_id in _aborted:
            status = "aborted"
            err = "Task aborted due to user activity or explicit abort request."
            logger.info("Task %s marked as aborted.", task_id)
        elif rc == 0:
            status = "completed"
        else:
            status = "failed"
            logger.warning("Task %s finished with exit_code=%d", task_id, rc)

        yield _make_result(
            task_id, stderr=err, exit_code=rc, status=status
        )

        # ── Zip and Upload Artifacts ──────────────────────────────────────────
        if has_artifact and proc.returncode == 0 and status != "aborted":
            yield _make_result(task_id, stdout="[GridMind] Packaging output artifact...\n")
            out_zip = os.path.join(tempfile.gettempdir(), f"gm_out_{task_id}.zip")

            def zip_and_upload():
                # make_archive wants the path WITHOUT the .zip suffix.
                shutil.make_archive(os.path.splitext(out_zip)[0], 'zip', workspace_dir)
                upload_url = f"http://{server_host}:8000/api/v1/tasks/{task_id}/artifact/output"
                # httpx multipart upload (no dependency on `curl` being on PATH).
                with open(out_zip, "rb") as fh:
                    resp = httpx.post(upload_url, files={"file": (os.path.basename(out_zip), fh)}, timeout=60)
                    resp.raise_for_status()
                os.remove(out_zip)

            try:
                await loop.run_in_executor(None, zip_and_upload)
                yield _make_result(task_id, stdout="[GridMind] Output workspace uploaded successfully.\n")
            except Exception as e:
                logger.error("Output upload failed: %s", e)
                yield _make_result(task_id, stdout=f"[GridMind] Warning: Output upload failed: {e}\n")

    finally:
        proc_running = _running.pop(task_id, None)
        if proc_running:
            _kill_proc(proc_running)
        _aborted.discard(task_id)
        if not has_artifact:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        if workspace_dir:
            shutil.rmtree(workspace_dir, ignore_errors=True)


async def abort_task(task_id: str) -> bool:
    """
    Signal a running task to terminate. Marks it as aborted so the
    final status is distinguishable from a regular failure.

    Returns True if the process was found and signalled, False otherwise.
    """
    proc = _running.get(task_id)
    if proc is None:
        logger.debug("abort_task: no running proc for task_id=%s", task_id)
        return False

    if task_id in _aborted:
        return True
        
    _aborted.add(task_id)
    try:
        if sys.platform == "win32":
            # Kill the whole tree (proc.terminate() leaves grandchildren orphaned).
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        logger.info("Abort signalled to task %s", task_id)
        return True
    except (ProcessLookupError, OSError) as exc:
        logger.warning("abort_task: signal failed for %s: %s", task_id, exc)
        _aborted.discard(task_id)
        return False
