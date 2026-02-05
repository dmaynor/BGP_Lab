# MIT License
#
# Copyright (c) 2024 BGP Lab contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Docker client using the official Docker SDK for Python."""

import docker
from docker.models.containers import Container
from typing import Tuple


class DockerClient:
    """Client for interacting with Docker containers using the Docker SDK."""

    def __init__(self) -> None:
        """Initialize the Docker client.

        Connects to the Docker daemon using the socket mounted at
        /var/run/docker.sock.
        """
        self.client = docker.from_env()

    def get_container(self, container_name: str) -> Container:
        """Get a Docker container by name.

        Parameters
        ----------
        container_name:
            Name of the container (e.g., "r3").

        Returns
        -------
        Container
            The Docker container object.

        Raises
        ------
        docker.errors.NotFound
            If the container does not exist.
        """
        return self.client.containers.get(container_name)

    def exec_in_container(
        self, container_name: str, command: list[str]
    ) -> Tuple[int, str]:
        """Execute a command in a Docker container.

        Parameters
        ----------
        container_name:
            Name of the container (e.g., "r3").
        command:
            Command to execute as a list of strings.

        Returns
        -------
        tuple[int, str]
            A tuple of (exit_code, output).

        Raises
        ------
        docker.errors.NotFound
            If the container does not exist.
        docker.errors.APIError
            If the Docker API returns an error.
        """
        container = self.get_container(container_name)
        result = container.exec_run(command, demux=False)

        # result is an ExecResult with exit_code and output
        exit_code = result.exit_code
        output = result.output.decode("utf-8") if result.output else ""

        return exit_code, output
