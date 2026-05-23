# This file is part of yle-dl.
#
# Copyright 2010-2026 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

import ctypes
import ctypes.util
import logging
import os
import os.path
import platform
import signal
import shlex
import subprocess
from subprocess import Popen
from typing import Sequence, Mapping, Optional
from .errors import ExternalApplicationNotFoundError
from .exitcodes import RD_SUCCESS, RD_INCOMPLETE

logger = logging.getLogger('yledl')


def execute_pipe(
    commands: Sequence[Sequence[str]],
    extra_environment: Optional[Mapping[str, str]] = None,
) -> int:
    """Start external processes connected with pipes and wait completion.

    commands is a list commands to execute. commands[i] is a list of shell
    command and arguments.

    extra_environment is a dict of environment variables that are combined
    with os.environ.
    """
    if not commands:
        return RD_SUCCESS

    logger.debug('Executing:')
    shell_command_string = ' | '.join(shlex.join(args) for args in commands)
    logger.debug(shell_command_string)

    env = _combine_envs(extra_environment)
    process = _start_process(commands, env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        try:
            os.kill(process.pid, signal.SIGINT)
            process.wait()
        except OSError:
            # The process died before we killed it.
            pass
        return RD_INCOMPLETE
    except OSError as exc:
        logger.error(f'Failed to execute {shell_command_string}')
        logger.error(exc.strerror)
        raise ExternalApplicationNotFoundError(
            f'Failed to execute {shell_command_string}'
        )


def _combine_envs(
    extra_environment: Optional[Mapping[str, str]],
) -> Optional[dict[str, str]]:
    if extra_environment:
        env = dict(os.environ)
        env.update(extra_environment)
        return env
    else:
        return None


def _start_process(
    commands: Sequence[Sequence[str]], env: Optional[Mapping[str, str]]
) -> Popen:
    """Start all commands and setup pipes."""
    if not commands:
        raise ValueError('command required')

    processes: list[Popen] = []
    for i, args in enumerate(commands):
        if i == 0 and platform.system() != 'Windows':
            preexec_fn = _sigterm_when_parent_dies
        else:
            preexec_fn = None

        stdin = processes[-1].stdout if processes else None
        stdout = None if i == len(commands) - 1 else subprocess.PIPE
        processes.append(
            subprocess.Popen(
                args, stdin=stdin, stdout=stdout, env=env, preexec_fn=preexec_fn
            )
        )

    # Causes the first process to receive SIGPIPE if the seconds
    # process exists
    for p in processes[:-1]:
        if p.stdout:
            p.stdout.close()

    return processes[0]


def _sigterm_when_parent_dies() -> None:
    PR_SET_PDEATHSIG = 1

    libcname = ctypes.util.find_library('c')
    if not libcname:
        return

    try:
        libc = ctypes.CDLL(libcname)
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except AttributeError:
        # libc is None or libc does not contain prctl
        pass
