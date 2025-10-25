# ./lib/command_runner.py
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from itertools import count
from typing import Callable, Dict, Optional, Tuple, List

from PyQt6.QtCore import QObject, QProcess, pyqtSignal, QCoreApplication


# -------------------------
# Public data structures
# -------------------------

@dataclass
class ProcHandle:
    """Handle you can keep to manage/inspect a running command."""
    id: int
    process: QProcess
    command_str: str
    elevate: bool
    method: str  # 'pkexec' | 'sudo' | 'none'
    pid: Optional[int] = None
    stdout_buffer: List[str] = field(default_factory=list)
    stderr_buffer: List[str] = field(default_factory=list)

    def kill(self) -> None:
        self.process.kill()

    def terminate(self) -> None:
        self.process.terminate()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def exit_code(self) -> Optional[int]:
        code = self.process.exitCode()
        return code if self.process.state() == QProcess.ProcessState.NotRunning else None

    def output_text(self) -> str:
        return "".join(self.stdout_buffer)

    def error_text(self) -> str:
        return "".join(self.stderr_buffer)


# -------------------------
# Command Manager (Qt-based)
# -------------------------

class CommandManager(QObject):
    """
    Manage multiple shell commands using QProcess (non-UI).
    Hooks:
      - on_output:  callable(id, text)  -> merged stdout/stderr text (if merge=True)
      - on_stdout:  callable(id, text)  -> stdout chunks (if merge=False)
      - on_stderr:  callable(id, text)  -> stderr chunks (if merge=False)
      - on_finished: callable(id, exit_code)
      - on_error:   callable(id, qprocess_error_string)
    """

    # Optional app-wide signals if you prefer connecting to Qt signals
    sig_output = pyqtSignal(int, str)
    sig_stdout = pyqtSignal(int, str)
    sig_stderr = pyqtSignal(int, str)
    sig_finished = pyqtSignal(int, int)
    sig_error = pyqtSignal(int, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._id_gen = count(1)
        self._procs: Dict[int, ProcHandle] = {}

    # ---------- Public API ----------

    def run(
        self,
        command: str | List[str],
        *,
        elevate: bool = False,
        method: str = "pkexec",     # or 'sudo'
        sudo_password: Optional[str] = None,
        shell: bool = True,         # True -> use bash -lc to allow pipes, globs
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        merge_output: bool = True,  # True = merged stdout/stderr via on_output
        on_output: Optional[Callable[[int, str], None]] = None,
        on_stdout: Optional[Callable[[int, str], None]] = None,
        on_stderr: Optional[Callable[[int, str], None]] = None,
        on_finished: Optional[Callable[[int, int], None]] = None,
        on_error: Optional[Callable[[int, str], None]] = None,
    ) -> ProcHandle:
        """
        Start a command. Returns a ProcHandle immediately. Use callbacks or buffers to monitor.
        """

        # Normalize to a display string (for logging/handle)
        if isinstance(command, list):
            cmd_str = " ".join(shlex.quote(x) for x in command)
        else:
            cmd_str = command.strip()

        # Build program/args for QProcess
        program, args = self._prepare_invocation(cmd_str, elevate, method, sudo_password, shell)

        # Create/process + wire signals
        pid = next(self._id_gen)
        proc = QProcess(self)
        if cwd:
            proc.setWorkingDirectory(cwd)
        if env:
            # Convert mapping to QProcessEnvironment if needed, but setting via system env is OK too
            from PyQt6.QtCore import QProcessEnvironment
            pe = QProcessEnvironment.systemEnvironment()
            for k, v in env.items():
                pe.insert(k, v)
            proc.setProcessEnvironment(pe)

        # Channel mode
        if merge_output:
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        else:
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        handle = ProcHandle(
            id=pid, process=proc, command_str=cmd_str,
            elevate=elevate, method=('pkexec' if elevate and method.startswith('pkexec') else 'sudo' if elevate else 'none'),
        )
        self._procs[pid] = handle

        # Connect IO
        if merge_output:
            proc.readyReadStandardOutput.connect(lambda pid=pid: self._on_chunk_merged(pid, on_output))
        else:
            proc.readyReadStandardOutput.connect(lambda pid=pid: self._on_chunk_stdout(pid, on_stdout))
            proc.readyReadStandardError.connect(lambda pid=pid: self._on_chunk_stderr(pid, on_stderr))

        proc.errorOccurred.connect(lambda err, pid=pid: self._on_error(pid, err, on_error))
        proc.finished.connect(lambda code, _status, pid=pid: self._on_finished(pid, code, on_finished))

        # If sudo needs a password via stdin, write it after start (only for sudo -S path we build)
        needs_password_write = elevate and method.lower().startswith("sudo") and (sudo_password is not None) and (shell is True)
        if needs_password_write:
            # We'll include a small wrapper that reads from stdin in our prepared command,
            # so no extra write is needed here. If you prefer sending to stdin:
            proc.started.connect(lambda pid=pid, pw=sudo_password: self._write_sudo_password(pid, pw))

        # Start the process
        proc.start(program, args)

        return handle

    def get(self, pid: int) -> Optional[ProcHandle]:
        return self._procs.get(pid)

    def list_running(self) -> List[ProcHandle]:
        return [h for h in self._procs.values() if h.is_running()]

    def kill(self, pid: int) -> bool:
        h = self._procs.get(pid)
        if not h:
            return False
        h.kill()
        return True

    def terminate(self, pid: int) -> bool:
        h = self._procs.get(pid)
        if not h:
            return False
        h.terminate()
        return True

    def kill_all(self) -> None:
        for h in list(self._procs.values()):
            if h.is_running():
                h.kill()

    # ---------- Internals ----------

    def _prepare_invocation(
        self, cmd_str: str, elevate: bool, method: str, sudo_password: Optional[str], shell: bool
    ) -> Tuple[str, List[str]]:
        """
        Return (program, args) for QProcess.start(). We keep quoting safe.
        """
        if shell:
            # Use bash -lc so pipes/globs/&& work
            inner = cmd_str
            if elevate:
                if method.lower().startswith("pkexec"):
                    # pkexec bash -lc '<cmd>'
                    return "pkexec", ["bash", "-lc", inner]
                else:
                    # sudo path: if password provided, we'll echo it into sudo -S
                    if sudo_password is not None:
                        # echo 'pwd' | sudo -S bash -lc '<cmd>'
                        shell_cmd = f"echo {shlex.quote(sudo_password)} | sudo -S bash -lc {shlex.quote(inner)}"
                        return "bash", ["-lc", shell_cmd]
                    else:
                        # interactive sudo (will prompt on TTY—usually fails in GUI apps). Still provided.
                        sudo_cmd = f"sudo bash -lc {shlex.quote(inner)}"
                        return "bash", ["-lc", sudo_cmd]
            else:
                return "bash", ["-lc", inner]
        else:
            # Exec directly without shell
            parts = shlex.split(cmd_str)
            if elevate:
                if method.lower().startswith("pkexec"):
                    return "pkexec", parts
                else:
                    if sudo_password is not None:
                        # echo pwd | sudo -S <prog> args...
                        full = " ".join(shlex.quote(p) for p in parts)
                        shell_cmd = f"echo {shlex.quote(sudo_password)} | sudo -S {full}"
                        return "bash", ["-lc", shell_cmd]
                    else:
                        return "sudo", parts
            else:
                return parts[0], parts[1:]

    def _on_chunk_merged(self, pid: int, cb: Optional[Callable[[int, str], None]]) -> None:
        h = self._procs.get(pid)
        if not h:
            return
        data = bytes(h.process.readAllStandardOutput()).decode(errors="replace")
        if data:
            h.stdout_buffer.append(data)  # merged into stdout_buffer
            if cb:
                cb(pid, data)
            self.sig_output.emit(pid, data)

    def _on_chunk_stdout(self, pid: int, cb: Optional[Callable[[int, str], None]]) -> None:
        h = self._procs.get(pid)
        if not h:
            return
        data = bytes(h.process.readAllStandardOutput()).decode(errors="replace")
        if data:
            h.stdout_buffer.append(data)
            if cb:
                cb(pid, data)
            self.sig_stdout.emit(pid, data)

    def _on_chunk_stderr(self, pid: int, cb: Optional[Callable[[int, str], None]]) -> None:
        h = self._procs.get(pid)
        if not h:
            return
        data = bytes(h.process.readAllStandardError()).decode(errors="replace")
        if data:
            h.stderr_buffer.append(data)
            if cb:
                cb(pid, data)
            self.sig_stderr.emit(pid, data)

    def _on_finished(self, pid: int, exit_code: int, cb: Optional[Callable[[int, int], None]]) -> None:
        h = self._procs.get(pid)
        if h:
            h.pid = h.process.processId()
        if cb:
            cb(pid, exit_code)
        self.sig_finished.emit(pid, exit_code)
        # keep handle in dict for inspection after finish; caller can remove if desired

    def _on_error(self, pid: int, err: QProcess.ProcessError, cb: Optional[Callable[[int, str], None]]) -> None:
        msg = err.name if hasattr(err, "name") else str(err)
        if cb:
            cb(pid, msg)
        self.sig_error.emit(pid, msg)

    def _write_sudo_password(self, pid: int, password: str) -> None:
        # (Not used in current wrapping, since we pipe via 'echo | sudo -S ...')
        h = self._procs.get(pid)
        if not h:
            return
        try:
            h.process.write((password + "\n").encode())
            h.process.flush()
        except Exception:
            pass


# -------------------------
# Simple synchronous helper
# -------------------------

def run_command_sync(
    command: str | List[str],
    *,
    elevate: bool = False,
    method: str = "pkexec",            # or 'sudo'
    sudo_password: Optional[str] = None,
    shell: bool = True,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,     # seconds
) -> Tuple[int, str, str]:
    """
    Blocking helper using Python's subprocess for quick use cases.
    Returns (exit_code, stdout, stderr).
    """
    import subprocess, os

    if isinstance(command, list):
        cmd_str = " ".join(shlex.quote(x) for x in command)
    else:
        cmd_str = command.strip()

    if shell:
        inner = cmd_str
        if elevate:
            if method.lower().startswith("pkexec"):
                full = f"pkexec bash -lc {shlex.quote(inner)}"
            else:
                if sudo_password is not None:
                    full = f"bash -lc \"echo {shlex.quote(sudo_password)} | sudo -S bash -lc {shlex.quote(inner)}\""
                else:
                    full = f"sudo bash -lc {shlex.quote(inner)}"
        else:
            full = f"bash -lc {shlex.quote(inner)}"

        p = subprocess.Popen(
            full,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            shell=True,  # running a single string
        )
    else:
        parts = shlex.split(cmd_str)
        if elevate:
            if method.lower().startswith("pkexec"):
                parts = ["pkexec", *parts]
            else:
                if sudo_password is not None:
                    # echo pwd | sudo -S <prog> ...
                    full = "echo {} | sudo -S {}".format(shlex.quote(sudo_password), " ".join(shlex.quote(p) for p in parts))
                    p = subprocess.Popen(
                        full,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=cwd,
                        env=env,
                        shell=True
                    )
                    out, err = p.communicate(timeout=timeout)
                    return p.returncode, out, err
                else:
                    parts = ["sudo", *parts]

        p = subprocess.Popen(
            parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
            shell=False
        )

    out, err = p.communicate(timeout=timeout)
    return p.returncode, out, err
