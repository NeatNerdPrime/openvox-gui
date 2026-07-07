"""
Sudo command runner with pseudo-TTY support.

Many RHEL/enterprise systems set 'Defaults requiretty' in sudoers,
which rejects sudo calls from processes without a controlling terminal
(like systemd services). This module provides a helper that allocates
a PTY on stdin to satisfy that requirement.
"""
import asyncio
import fcntl
import logging
import os
import pty
import termios
from typing import Dict, List

logger = logging.getLogger(__name__)


async def run_sudo(cmd: List[str], timeout: int = 30, env: dict = None) -> Dict[str, object]:
    """Run a command (typically prefixed with 'sudo') with a pseudo-TTY.

    Uses the 'script' utility (if available) to guarantee a controlling
    terminal for the command. This reliably satisfies 'Defaults requiretty'
    even when the calling process (systemd service) has no TTY.

    Falls back to direct PTY allocation with explicit controlling terminal
    setup if 'script' is not found.

    Returns a dict with 'returncode', 'stdout', and 'stderr' keys.
    """
    if env is None:
        env = os.environ.copy()

    script_bin = "/usr/bin/script"
    if os.path.exists(script_bin):
        import shlex
        inner = shlex.join(cmd)
        wrapped_cmd = [script_bin, "-q", "-c", inner, "/dev/null"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *wrapped_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            logger.error("Command timed out after %ss: %s", timeout, cmd[:6])
            return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except (OSError, ValueError) as e:
            logger.error("Error running %s: %s", cmd[0:3], e, exc_info=True)
            return {"returncode": -1, "stdout": "", "stderr": str(e)}
        except Exception as e:
            logger.error("Unexpected error running %s: %s", cmd[0:3], e, exc_info=True)
            return {"returncode": -1, "stdout": "", "stderr": "Internal error running privileged command"}
    else:
        # Fallback to manual PTY
        master_fd, slave_fd = pty.openpty()
        try:
            def preexec() -> None:
                os.setsid()
                try:
                    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 1)
                except OSError:
                    pass

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=slave_fd,
                preexec_fn=preexec,
                start_new_session=True,
                env=env,
            )
            os.close(slave_fd)
            slave_fd = -1
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            logger.error("Command timed out after %ss: %s", timeout, cmd[:6])
            return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except (OSError, ValueError) as e:
            logger.error("Error running %s: %s", cmd[0:3], e, exc_info=True)
            return {"returncode": -1, "stdout": "", "stderr": str(e)}
        except Exception as e:
            logger.error("Unexpected error running %s: %s", cmd[0:3], e, exc_info=True)
            return {"returncode": -1, "stdout": "", "stderr": "Internal error running privileged command"}
        finally:
            if slave_fd >= 0:
                os.close(slave_fd)
            try:
                os.close(master_fd)
            except OSError:
                pass
        return {"returncode": -1, "stdout": "", "stderr": str(e)}
    except Exception as e:
        # Last-resort: privileged runner must never raise into FastAPI uncaught,
        # but always log full traceback (srdev1 S1).
        logger.error("Unexpected error running %s: %s", cmd[0:3], e, exc_info=True)
        return {"returncode": -1, "stdout": "", "stderr": "Internal error running privileged command"}
    finally:
        if slave_fd >= 0:
            os.close(slave_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass
