import asyncio
import logging
import os
import pathlib
import platform
import subprocess

import aiohttp

import aioxmpp
import aioxmpp.httpupload

import jclib.tasks


logger = logging.getLogger(__name__)


def stream_file_with_status(
        writer,
        annotation,
        file_object,
        size):
    annotation.progress_ratio = 0
    ctr = 0

    while True:
        data = file_object.read(4096)
        if not data:
            return

        yield from writer.write(data)
        ctr += len(data)
        annotation.progress_ratio = ctr / size


try:
    stream_file_with_status = aiohttp.streamer(stream_file_with_status)
except AttributeError:
    # not supported by this version of aiohttp
    stream_file_with_status = None


async def guess_mime_type(path: pathlib.Path):
    if platform.system() == 'Windows':
        return None

    proc = await asyncio.create_subprocess_exec(
        "xdg-mime", "query", "filetype", str(path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    try:
        stdout = stdout.decode().strip()
        stderr = stderr.decode().strip()
    except UnicodeDecodeError:
        logger.warning(
            "failed to determine MIME type of %r: "
            "failed to decode response from subprocess",
            path,
            exc_info=True
        )
        return None

    if proc.returncode != 0:
        logger.warning(
            "failed to determine MIME type of %r: "
            "subprocess returned error (stderr=%r)",
            path,
            stderr,
            exc_info=True,
        )
        return None

    if stdout:
        return stdout

    return None


async def upload_file(client: aioxmpp.Client,
                      service: aioxmpp.JID,
                      path: pathlib.Path,
                      size: int = None,
                      content_type: str = "application/octet-stream",
                      *,
                      session: aiohttp.ClientSession = None):
    filename = path.name

    if size is None:
        size = os.stat(str(path)).st_size

    if session is None:
        async with aiohttp.ClientSession() as session:
            return (await upload_file(client, service, path,
                                      size=size,
                                      content_type=content_type,
                                      session=session))

    slot = await aioxmpp.httpupload.request_slot(
        client,
        service,
        filename,
        size,
        content_type,
    )

    headers = slot.put.headers
    headers["Content-Type"] = content_type
    headers["Content-Length"] = str(size)

    task_annotation = jclib.tasks.manager.current()
    with path.open("rb") as file_:
        if task_annotation is not None and stream_file_with_status is not None:
            data = stream_file_with_status(
                annotation=task_annotation,
                file_object=file_,
                size=size,
            )
        else:
            data = file_

        async with session.put(slot.put.url,
                               data=data,
                               headers=headers) as response:
            if response.status not in (200, 201):
                raise RuntimeError("upload failed: {} {}".format(
                    response.status,
                    response.reason,
                ))

    return slot.get.url
